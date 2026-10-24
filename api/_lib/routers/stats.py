"""routes กลุ่ม stats — แยกจาก api/index.py"""
from _lib import line
from _lib import supa
from _lib.auth import current_admin
from fastapi import Depends
from fastapi import HTTPException
import datetime as dt
import os
from fastapi import APIRouter
from _lib.core import (NOW, PIPELINE_STAGES, _STAGE_LABEL, _day, _day_series, _gather_dict, _get_setting, _iso_ago, _make_backup)

router = APIRouter()


@router.get("/api/dashboard")
async def dashboard(admin=Depends(current_admin), range: int = 30):
    days = max(7, min(range, 90))
    d7, d30, dN = _iso_ago(days=7), _iso_ago(days=30), _iso_ago(days=days)
    today0 = dt.date.today().isoformat()

    # ---------- headline counts (ขนานกันหมด) ----------
    c = await _gather_dict(
        total=supa.count("line_users"),
        following=supa.count("line_users", {"is_following": "eq.true"}),
        not_following=supa.count("line_users", {"is_following": "eq.false"}),
        no_menu=supa.count("line_users", {"is_following": "eq.true", "current_rich_menu_id": "is.null"}),
        active7=supa.count("line_users", {"is_following": "eq.true", "last_message_at": f"gte.{d7}"}),
        active30=supa.count("line_users", {"is_following": "eq.true", "last_message_at": f"gte.{d30}"}),
        unread=supa.count("line_users", {"unread": "gt.0"}),
        new7=supa.count("line_users", {"first_followed_at": f"gte.{d7}"}),
        new30=supa.count("line_users", {"first_followed_at": f"gte.{d30}"}),
        msg_in_7=supa.count("messages", {"direction": "eq.in", "created_at": f"gte.{d7}"}),
        msg_out_7=supa.count("messages", {"direction": "eq.out", "created_at": f"gte.{d7}"}),
        wh_today=supa.count("webhook_events", {"created_at": f"gte.{today0}"}),
        slip_total=supa.count("slips"),
        slip_new=supa.count("slips", {"status": "eq.new"}),
        slip_review=supa.count("slips", {"status": "eq.review"}),
        slip_verified=supa.count("slips", {"status": "eq.verified"}),
        slip_rejected=supa.count("slips", {"status": "eq.rejected"}),
        slip_today=supa.count("slips", {"created_at": f"gte.{today0}"}),
        slip_week=supa.count("slips", {"created_at": f"gte.{d7}"}),
        err24=supa.count("operations", {"status": "eq.error", "created_at": f"gte.{_iso_ago(hours=24)}"}),
        rows_users=supa.count("line_users"),
        rows_msg=supa.count("messages"),
        rows_wh=supa.count("webhook_events"),
        rows_ev_pending=supa.count("automation_runs", {"status": "eq.pending"}),
        msg_today=supa.count("messages", {"created_at": f"gte.{today0}"}),
        wh_7=supa.count("webhook_events", {"created_at": f"gte.{d7}"}),
        gemini_7=supa.count("messages", {"by": "eq.gemini", "created_at": f"gte.{d7}"}),
        gemini_today=supa.count("messages", {"by": "eq.gemini", "created_at": f"gte.{today0}"}),
        ar_total=supa.count("auto_replies"),
        ar_on=supa.count("auto_replies", {"enabled": "eq.true"}),
        pb_total=supa.count("postback_actions"),
        pb_on=supa.count("postback_actions", {"enabled": "eq.true"}),
        seg_total=supa.count("segments"),
        tpl_total=supa.count("message_templates"),
        link_total=supa.count("short_links"),
        menu_total=supa.count("rich_menus"),
        auto_total=supa.count("automations"),
        auto_on=supa.count("automations", {"enabled": "eq.true"}),
        sched_pending=supa.count("scheduled_jobs", {"status": "eq.pending"}),
        blocked=supa.count("line_users", {"block_count": "gt.0", "is_following": "eq.false"}),
        tasks_open=supa.count("tasks", {"status": "eq.open"}),
        tasks_overdue=supa.count("tasks", {"status": "eq.open", "due_at": f"lt.{_iso_ago(days=0)}"}),
        **{f"stg_{s}": supa.count("line_users", {"stage": f"eq.{s}", "is_following": "eq.true"})
           for s in PIPELINE_STAGES},
    )

    # ---------- LINE API ----------
    line_data = await _gather_dict(bot=line.bot_info(), quota=line.message_quota())
    bot = line_data.get("bot") or {"error": "ดึงข้อมูลบอทไม่ได้"}
    quota = line_data.get("quota") or {}

    # ---------- growth: follow_history (real-time) ----------
    fh = await supa.select_all("follow_history", params={"select": "action,is_unblocked,event_ts,created_at"})
    gkeys = _day_series(days)
    gmap = {k: {"day": k, "follow": 0, "unfollow": 0, "unblock": 0} for k in gkeys}
    for r in fh:
        k = _day(r.get("event_ts") or r.get("created_at"))
        if k in gmap:
            if r["action"] == "follow":
                gmap[k]["follow"] += 1
                if r.get("is_unblocked"):
                    gmap[k]["unblock"] += 1
            elif r["action"] == "unfollow":
                gmap[k]["unfollow"] += 1
    growth = []
    run = 0
    for k in gkeys:
        g = gmap[k]
        g["net"] = g["follow"] - g["unfollow"]
        run += g["net"]
        g["cumulative"] = run
        growth.append(g)
    tot_follow = sum(g["follow"] for g in growth)
    tot_unfollow = sum(g["unfollow"] for g in growth)

    # ---------- new followers / day (first_followed_at) ----------
    lu = await supa.select_all("line_users", params={
        "select": "first_followed_at,source,current_rich_menu_id,is_following"})
    nmap = {k: 0 for k in gkeys}
    src_map: dict[str, int] = {}
    menu_count: dict[str, int] = {}
    for u in lu:
        k = _day(u.get("first_followed_at"))
        if k in nmap:
            nmap[k] += 1
        src_map[u.get("source") or "unknown"] = src_map.get(u.get("source") or "unknown", 0) + 1
        if u.get("is_following"):
            mk = u.get("current_rich_menu_id") or "__none__"
            menu_count[mk] = menu_count.get(mk, 0) + 1
    new_daily = [{"day": k, "count": nmap[k]} for k in gkeys]
    source_breakdown = sorted(
        [{"source": k, "count": v} for k, v in src_map.items()], key=lambda x: -x["count"])

    # ---------- menu distribution ----------
    menu_names = {m["rich_menu_id"]: m.get("name") for m in await supa.select(
        "rich_menus", params={"select": "rich_menu_id,name"})}
    try:
        default_menu = await line.richmenu_get_default()
    except Exception:
        default_menu = None
    menu_dist = sorted([{
        "name": "— ไม่มีเมนู —" if k == "__none__" else (menu_names.get(k) or "(เมนูถูกลบ)"),
        "rich_menu_id": None if k == "__none__" else k,
        "count": v, "is_default": k == default_menu,
    } for k, v in menu_count.items()], key=lambda x: -x["count"])

    # ---------- slips: revenue ----------
    slips = await supa.select_all("slips", params={
        "select": "status,amount,expected_course,created_at,reviewed_at"})
    rev_total = sum(float(s.get("amount") or 0) for s in slips if s.get("status") == "verified")
    rev_week = sum(float(s.get("amount") or 0) for s in slips
                   if s.get("status") == "verified" and _day(s.get("reviewed_at") or s.get("created_at")) >= _day(d7))
    course_map: dict[str, dict] = {}
    skeys = _day_series(days)
    sdaily = {k: {"day": k, "verified": 0, "review": 0, "rejected": 0, "new": 0} for k in skeys}
    for s in slips:
        co = s.get("expected_course") or "ไม่ระบุ"
        cm = course_map.setdefault(co, {"course": co, "count": 0, "verified": 0, "amount": 0.0})
        cm["count"] += 1
        if s.get("status") == "verified":
            cm["verified"] += 1
            cm["amount"] += float(s.get("amount") or 0)
        k = _day(s.get("created_at"))
        if k in sdaily and s.get("status") in sdaily[k]:
            sdaily[k][s["status"]] += 1
    slip_courses = sorted(course_map.values(), key=lambda x: -x["amount"])

    # ---------- system: cron health ----------
    ops = await supa.select("operations", params={
        "select": "action,status,created_at", "order": "created_at.desc", "limit": "80"})
    cron_jobs = {}
    for o in ops:
        a = o.get("action") or ""
        if "cron" in a or a.startswith(("richmenu.sync", "automation.run", "stats.snapshot", "backup")):
            base = a.split(".cron")[0]
            if base not in cron_jobs:
                cron_jobs[base] = {"job": base, "last_run": o["created_at"], "status": o.get("status")}
    recent_ops = await supa.select("operations", params={
        "select": "id,actor,action,status,created_at", "order": "created_at.desc", "limit": "10"})
    recent_bc = await supa.select("broadcasts", params={
        "select": "id,kind,target_count,status,created_at", "order": "created_at.desc", "limit": "6"})

    # ---------- สลิปล่าสุด + follow ล่าสุด ----------
    recent_slips = await supa.select("slips", params={
        "select": "id,line_user_id,amount,status,expected_course,auto_note,created_at",
        "order": "created_at.desc", "limit": "8"})
    recent_follows = await supa.select("follow_history", params={
        "select": "line_user_id,action,is_unblocked,event_ts", "order": "created_at.desc", "limit": "10"})
    _uids = list({r["line_user_id"] for r in recent_slips + recent_follows if r.get("line_user_id")})
    _names = {}
    if _uids:
        for r in await supa.select("line_users", params={
                "select": "line_user_id,display_name,picture_url",
                "line_user_id": f"in.({','.join(_uids)})", "limit": "50"}):
            _names[r["line_user_id"]] = r
    for r in recent_slips + recent_follows:
        u = _names.get(r.get("line_user_id"), {})
        r["display_name"] = u.get("display_name")
        r["picture_url"] = u.get("picture_url")

    # quota projection
    qv = (quota.get("quota") or {})
    q_limit = qv.get("value") if isinstance(qv, dict) else None
    q_used = quota.get("totalUsage")
    day_of_month = dt.date.today().day
    q_proj = round(q_used / day_of_month * 30) if (q_used and day_of_month) else None

    return {
        "generated_at": NOW(),
        "range_days": days,
        "commit": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "?")[:7],
        "users": {
            "total": c["total"], "following": c["following"], "not_following": c["not_following"],
            "no_menu": c["no_menu"], "with_menu": (c["following"] or 0) - (c["no_menu"] or 0),
            "active_7d": c["active7"], "active_30d": c["active30"],
            "new_7d": c["new7"], "new_30d": c["new30"], "unread_threads": c["unread"],
            "follow_rate": round((c["following"] or 0) / (c["total"] or 1) * 100),
            "active_rate": round((c["active30"] or 0) / (c["following"] or 1) * 100),
            "source_breakdown": source_breakdown,
            "pipeline": [{"key": s, "label": _STAGE_LABEL.get(s, s), "count": c.get(f"stg_{s}") or 0}
                         for s in PIPELINE_STAGES],
        },
        "growth": growth,
        "growth_totals": {"follow": tot_follow, "unfollow": tot_unfollow,
                          "net": tot_follow - tot_unfollow},
        "new_daily": new_daily,
        "menu_distribution": menu_dist,
        "slips": {
            "total": c["slip_total"], "today": c["slip_today"], "week": c["slip_week"],
            "by_status": {"new": c["slip_new"], "review": c["slip_review"],
                          "verified": c["slip_verified"], "rejected": c["slip_rejected"]},
            "pending_action": (c["slip_new"] or 0) + (c["slip_review"] or 0),
            "revenue_verified": round(rev_total), "revenue_week": round(rev_week),
            "by_course": slip_courses,
            "daily": [sdaily[k] for k in skeys],
        },
        "messages": {"in_7d": c["msg_in_7"], "out_7d": c["msg_out_7"],
                     "today": c["msg_today"], "gemini_7d": c["gemini_7"],
                     "gemini_today": c["gemini_today"], "ai_daily_limit": await _get_setting("ai_daily_limit", 0) or 0,
                     "webhook_7d": c["wh_7"]},
        "bot": bot, "quota": quota,
        "counts": {
            "auto_replies": c["ar_total"], "auto_replies_on": c["ar_on"],
            "postbacks": c["pb_total"], "postbacks_on": c["pb_on"],
            "automations": c["auto_total"], "automations_on": c["auto_on"],
            "segments": c["seg_total"], "templates": c["tpl_total"],
            "links": c["link_total"], "rich_menus": c["menu_total"],
            "scheduled_pending": c["sched_pending"], "blocked_ever": c["blocked"],
        },
        "system": {
            "quota_limit": q_limit, "quota_used": q_used,
            "quota_pct": round((q_used or 0) / (q_limit or 1) * 100) if q_limit else None,
            "quota_projected": q_proj,
            "webhook_today": c["wh_today"], "errors_24h": c["err24"],
            "automations_pending": c["rows_ev_pending"],
            "tasks_open": c["tasks_open"], "tasks_overdue": c["tasks_overdue"],
            "cron": sorted(cron_jobs.values(), key=lambda x: x["job"]),
            "db_rows": {"line_users": c["rows_users"], "messages": c["rows_msg"],
                        "webhook_events": c["rows_wh"], "slips": c["slip_total"]},
        },
        "recent_operations": recent_ops,
        "recent_broadcasts": recent_bc,
        "recent_slips": recent_slips,
        "recent_follows": recent_follows,
    }


@router.get("/api/dashboard/analytics")
async def dashboard_analytics(admin=Depends(current_admin), range: int = 30):
    days = max(7, min(range, 90))
    dkeys = _day_series(days)
    dN = _iso_ago(days=days)

    # ---------- messages: type / source / daily / heatmap / top talkers ----------
    msgs = await supa.select_all("messages", params={
        "select": "direction,by,msg_type,created_at,line_user_id", "created_at": f"gte.{dN}"})
    in_daily = {k: 0 for k in dkeys}
    out_daily = {k: 0 for k in dkeys}
    type_map: dict[str, int] = {}
    out_src: dict[str, int] = {}
    talk: dict[str, int] = {}
    # heatmap: 7 weekday rows x 24 hour cols (นับ inbound)
    heat = [[0] * 24 for _ in range(7)]
    for m in msgs:
        k = _day(m.get("created_at"))
        if m.get("direction") == "in":
            if k in in_daily:
                in_daily[k] += 1
            type_map[m.get("msg_type") or "?"] = type_map.get(m.get("msg_type") or "?", 0) + 1
            if m.get("line_user_id"):
                talk[m["line_user_id"]] = talk.get(m["line_user_id"], 0) + 1
            try:
                ts = dt.datetime.fromisoformat(m["created_at"].replace("Z", "+00:00"))
                heat[ts.weekday()][ts.hour] += 1
            except Exception:
                pass
        else:
            if k in out_daily:
                out_daily[k] += 1
            b = m.get("by") or "?"
            b = b if b in ("auto", "manual", "postback", "automation", "system", "broadcast", "gemini") else "admin"
            out_src[b] = out_src.get(b, 0) + 1

    top_talk_ids = sorted(talk, key=lambda u: -talk[u])[:10]
    talk_names = {}
    if top_talk_ids:
        for r in await supa.select("line_users", params={
                "select": "line_user_id,display_name,picture_url",
                "line_user_id": f"in.({','.join(top_talk_ids)})", "limit": "20"}):
            talk_names[r["line_user_id"]] = r
    top_talkers = [{
        "line_user_id": u, "count": talk[u],
        "display_name": (talk_names.get(u) or {}).get("display_name"),
        "picture_url": (talk_names.get(u) or {}).get("picture_url"),
    } for u in top_talk_ids]

    # ---------- webhook events by type / day ----------
    whe = await supa.select_all("webhook_events", params={
        "select": "event_type,created_at", "created_at": f"gte.{dN}"})
    wh_type: dict[str, int] = {}
    wh_daily = {k: 0 for k in dkeys}
    for w in whe:
        wh_type[w.get("event_type") or "?"] = wh_type.get(w.get("event_type") or "?", 0) + 1
        k = _day(w.get("created_at"))
        if k in wh_daily:
            wh_daily[k] += 1

    # ---------- bot: top auto-replies / postbacks ----------
    rules = await supa.select("auto_replies", params={
        "select": "name,trigger,hits,enabled,last_hit_at", "order": "hits.desc", "limit": "12"})
    pbs = await supa.select("postback_actions", params={
        "select": "data,label,hits,enabled,last_hit_at", "order": "hits.desc", "limit": "12"})
    autos = await supa.select("automations", params={"select": "name,enabled,trigger,runs"})
    ar_runs = await supa.select_all("automation_runs", params={"select": "status"})
    ar_stat: dict[str, int] = {}
    for r in ar_runs:
        ar_stat[r.get("status") or "?"] = ar_stat.get(r.get("status") or "?", 0) + 1

    # ---------- links ----------
    links = await supa.select("short_links", params={
        "select": "code,label,clicks,target", "order": "clicks.desc", "limit": "12"})
    lc = await supa.select_all("link_clicks", params={
        "select": "clicked_at", "clicked_at": f"gte.{dN}"})
    lc_daily = {k: 0 for k in dkeys}
    for x in lc:
        k = _day(x.get("clicked_at"))
        if k in lc_daily:
            lc_daily[k] += 1

    # ---------- scheduled upcoming ----------
    sched = await supa.select("scheduled_jobs", params={
        "select": "kind,run_at,label,repeat,status", "status": "eq.pending",
        "order": "run_at.asc", "limit": "8"})

    # ---------- LINE insight (demographic + delivery) ----------
    li = await _gather_dict(
        demo=line.insight_demographic(),
        delivery=line.insight_message_delivery((dt.date.today() - dt.timedelta(days=2)).strftime("%Y%m%d")),
    )
    demo = li.get("demo") or {}
    delivery = li.get("delivery") or {}
    hist = await supa.select("stats_daily", params={
        "select": "day,followers,targeted_reaches,blocks", "order": "day.desc", "limit": str(days)})

    # ---------- funnel ----------
    fu = await _gather_dict(
        total=supa.count("line_users"),
        following=supa.count("line_users", {"is_following": "eq.true"}),
        messaged=supa.count("line_users", {"is_following": "eq.true", "last_message_at": "not.is.null"}),
        slipped=supa.count("slips"),
        verified=supa.count("slips", {"status": "eq.verified"}),
    )

    TYPE_LABEL = {"text": "ข้อความ", "image": "รูป", "sticker": "สติกเกอร์", "video": "วิดีโอ",
                  "audio": "เสียง", "location": "ตำแหน่ง", "file": "ไฟล์"}
    SRC_LABEL = {"auto": "ตอบอัตโนมัติ", "manual": "แอดมินพิมพ์", "admin": "แอดมินพิมพ์",
                 "postback": "ปุ่ม/Postback", "automation": "Automation",
                 "broadcast": "Broadcast", "system": "ระบบ", "gemini": "Gemini AI"}
    return {
        "range_days": days,
        "messages": {
            "in_daily": [{"day": k, "count": in_daily[k]} for k in dkeys],
            "out_daily": [{"day": k, "count": out_daily[k]} for k in dkeys],
            "by_type": sorted([{"type": TYPE_LABEL.get(k, k), "count": v}
                               for k, v in type_map.items()], key=lambda x: -x["count"]),
            "out_by_source": sorted([{"source": SRC_LABEL.get(k, k), "count": v}
                                     for k, v in out_src.items()], key=lambda x: -x["count"]),
            "heatmap": heat,
            "top_talkers": top_talkers,
        },
        "delivery": delivery,
        "webhook": {
            "by_type": sorted([{"type": k, "count": v} for k, v in wh_type.items()], key=lambda x: -x["count"]),
            "daily": [{"day": k, "count": wh_daily[k]} for k in dkeys],
        },
        "bot": {
            "top_rules": rules, "top_postbacks": pbs,
            "automations": autos, "automation_runs": ar_stat,
        },
        "links": {
            "top": links,
            "daily": [{"day": k, "count": lc_daily[k]} for k in dkeys],
        },
        "scheduled": sched,
        "demographic": demo,
        "history": list(reversed(hist)),
        "funnel": [
            {"step": "ผู้ใช้ทั้งหมด", "count": fu["total"] or 0},
            {"step": "กำลังติดตาม", "count": fu["following"] or 0},
            {"step": "เคยทักแชท", "count": fu["messaged"] or 0},
            {"step": "ส่งสลิป", "count": fu["slipped"] or 0},
            {"step": "ยืนยันชำระ", "count": fu["verified"] or 0},
        ],
    }


# STATS
@router.get("/api/stats/quota")
async def stats_quota(admin=Depends(current_admin)):
    return await line.message_quota()


@router.get("/api/stats/insight")
async def stats_insight(admin=Depends(current_admin), date: str = ""):
    if not date:
        date = (dt.date.today() - dt.timedelta(days=2)).strftime("%Y%m%d")
    followers = await line.insight_followers(date)
    demo = await line.insight_demographic()
    delivery = await line.insight_message_delivery(date)
    # snapshot
    try:
        await supa.upsert("stats_daily", {
            "day": f"{date[:4]}-{date[4:6]}-{date[6:]}",
            "followers": followers.get("followers"),
            "targeted_reaches": followers.get("targetedReaches"),
            "blocks": followers.get("blocks"),
            "raw": {"followers": followers, "delivery": delivery},
            "captured_at": NOW(),
        }, on_conflict="day")
    except Exception:
        pass
    return {"date": date, "followers": followers, "demographic": demo, "delivery": delivery}


@router.get("/api/stats/funnel")
async def stats_funnel(admin=Depends(current_admin), tag: str = ""):
    total = await supa.count("line_users")
    following = await supa.count("line_users", {"is_following": "eq.true"})
    messaged = await supa.count("line_users", {"is_following": "eq.true", "last_message_at": "not.is.null"})
    has_menu = await supa.count("line_users", {"is_following": "eq.true", "current_rich_menu_id": "not.is.null"})
    tagged = await supa.count("line_users", {"is_following": "eq.true", "tags": "cs.{" + tag + "}"}) if tag else None

    # cohort: follow แต่ละสัปดาห์ (8 สัปดาห์) -> ยัง follow กี่ %
    fh = await supa.select_all("follow_history", params={"select": "line_user_id,action,event_ts"})
    first_follow: dict[str, str] = {}
    for r in sorted(fh, key=lambda x: x.get("event_ts") or ""):
        if r["action"] == "follow" and r["line_user_id"] not in first_follow:
            first_follow[r["line_user_id"]] = (r.get("event_ts") or "")[:10]
    still = {u["line_user_id"] for u in await supa.select_all("line_users", params={
        "select": "line_user_id", "is_following": "eq.true"})}
    cohorts: dict[str, dict] = {}
    for uid, d in first_follow.items():
        if not d:
            continue
        wk = d[:7]  # เดือน
        c = cohorts.setdefault(wk, {"month": wk, "joined": 0, "retained": 0})
        c["joined"] += 1
        if uid in still:
            c["retained"] += 1
    cohort_list = sorted(cohorts.values(), key=lambda x: x["month"])[-8:]
    for c in cohort_list:
        c["rate"] = round(c["retained"] / c["joined"] * 100) if c["joined"] else 0

    return {
        "funnel": [
            {"step": "ผู้ใช้ในระบบ", "count": total},
            {"step": "กำลังติดตาม", "count": following},
            {"step": "เคยทักเข้ามา", "count": messaged},
            {"step": "มี Rich Menu", "count": has_menu},
            *([{"step": f"tag: {tag}", "count": tagged}] if tag else []),
        ],
        "cohorts": cohort_list,
    }


@router.get("/api/stats/history")
async def stats_history(admin=Depends(current_admin), days: int = 30):
    return {"days": await supa.select("stats_daily", params={
        "select": "*", "order": "day.desc", "limit": str(days),
    })}


@router.get("/api/stats/follows")
async def stats_follows(admin=Depends(current_admin), days: int = 14):
    """สรุป follow/unfollow จาก webhook (real-time) รายวัน"""
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    rows = await supa.select_all("follow_history", params={
        "select": "action,is_unblocked,event_ts,created_at",
    })
    by_day: dict[str, dict] = {}
    unblocked = newfollow = unfollow = 0
    for r in rows:
        d = (r.get("event_ts") or r["created_at"])[:10]
        b = by_day.setdefault(d, {"day": d, "follow": 0, "unfollow": 0, "unblock": 0})
        if r["action"] == "follow":
            b["follow"] += 1
            if r.get("is_unblocked"):
                b["unblock"] += 1
                unblocked += 1
            else:
                newfollow += 1
        else:
            b["unfollow"] += 1
            unfollow += 1
    series = sorted(by_day.values(), key=lambda x: x["day"])[-days:]
    for s in series:
        s["net"] = s["follow"] - s["unfollow"]
    return {"series": series,
            "totals": {"new_follow": newfollow, "unblock": unblocked, "unfollow": unfollow,
                       "net": newfollow + unblocked - unfollow}}


@router.post("/api/backup/now")
async def backup_now(admin=Depends(current_admin)):
    res = await _make_backup()
    await supa.log_operation(admin["userId"], "backup.manual", None, res)
    return {"ok": True, **res}


@router.get("/api/backup/list")
async def backup_list(admin=Depends(current_admin)):
    rows = await supa.select("backups", params={
        "select": "id,day,size_kb,created_at", "order": "day.desc", "limit": "30"})
    for r in rows:
        try:
            r["storage_url"] = await supa.storage_sign_url(
                "db-backups", f"{r['day']}.json.gz", 7 * 86400)
        except Exception:
            r["storage_url"] = None
    return {"backups": rows}


@router.get("/api/backup/{bid}")
async def backup_get(bid: int, admin=Depends(current_admin)):
    rows = await supa.select("backups", params={"id": f"eq.{bid}", "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบ")
    return rows[0]

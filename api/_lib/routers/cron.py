"""routes กลุ่ม cron — แยกจาก api/index.py"""
from _lib import line
from _lib import supa
from _lib.config import ALERT_USER_IDS
from _lib.config import ANTHROPIC_API_KEY
from _lib.config import APP_URL
from _lib.config import ENFORCE_EXCLUDE_MENUS
from _lib.config import ENFORCE_RICHMENU_ID
from _lib.config import GEMINI_API_KEY
from _lib.config import GEMINI_TRIGGER_MENU_NAME
from _lib.config import SLIP_SUCCESS_RICHMENU_ID
from fastapi import HTTPException
from fastapi import Request
import asyncio
import datetime as dt
from fastapi import APIRouter
from _lib.core import (NOW, _ai_baseline, _backfill_users, _broadcast_begin, _broadcast_finish, _check_cron_key, _cron_authorized, _cron_last_run, _cron_stale, _dev_commands_list, _enroll_inactive_automations, _fetch_current_menu_map, _flag_nonfriend_registrants, _get_setting, _health_digest_lines, _iso_ago, _json_obj, _kb_autogen_batch, _log_richmenu_diffs, _make_backup, _mark_registrations_paid_by_ids, _norm_question, _normalize_messages, _reconcile_data, _reprocess_slips, _retag_from_registrations, _richmenu_auto_unregistered, _richmenu_usage_data, _run_webhook_jobs, _slips_summary, _sync_richmenu_for, _triage_recall_check, _triage_refresh_notes, _triage_slips, alert_admin, health)

router = APIRouter()


@router.api_route("/api/internal/run-jobs", methods=["GET", "POST"])
@router.api_route("/api/cron/run-jobs", methods=["GET", "POST"])
async def run_jobs_endpoint(request: Request):
    _check_cron_key(request)
    return {"ok": True, **await _run_webhook_jobs()}


@router.api_route("/api/cron/slips-reprocess", methods=["GET", "POST"])
async def cron_slips_reprocess(request: Request):
    """?apply=1 = ตรวจซ้ำจริง (ไม่ใส่ = แค่นับผู้สมัคร ไม่เสียโควต้า) &limit=N (ค่าเริ่ม 40) — ไม่มีข้อมูลส่วนบุคคลในผลลัพธ์"""
    _check_cron_key(request)
    apply = request.query_params.get("apply") == "1"
    try:
        limit = max(1, min(int(request.query_params.get("limit", "40")), 80))
    except ValueError:
        limit = 40
    res = await _reprocess_slips(apply, limit)
    if apply:
        await supa.log_operation("cron", "slips.reprocess", {"limit": limit},
                                 {k: v for k, v in res.items() if k != "items"})
    return {"ok": True, "applied": apply, **res}


@router.get("/api/cron/dev-commands")
async def cron_dev_commands_list(request: Request, status: str = "pending"):
    """คิวคำสั่งพัฒนาระบบที่เจ้าของส่งมาทาง LINE (ดู migration 0021) — ให้ Claude มาเช็คตอนเปิดเซสชันดูแลระบบ"""
    _check_cron_key(request)
    return await _dev_commands_list(status)


@router.post("/api/cron/dev-commands/{cid}/complete")
async def cron_dev_commands_complete(cid: int, request: Request):
    """ปิดงานคำสั่ง + ส่งผลสรุปกลับให้ผู้สั่งทาง LINE (ถ้า notify=true) — body: {result, notify, status}"""
    _check_cron_key(request)
    b = await _json_obj(request)
    status = b.get("status") if b.get("status") in ("done", "failed") else "done"
    result = str(b.get("result") or "")[:1500]
    row = await supa.select("dev_commands", params={"id": f"eq.{cid}", "select": "line_user_id", "limit": "1"})
    await supa.update("dev_commands", {"status": status, "result": result, "processed_at": NOW()}, {"id": f"eq.{cid}"})
    if b.get("notify", True) and row:
        emoji = "✅" if status == "done" else "⚠️"
        try:
            await line.push(row[0]["line_user_id"], [{"type": "text", "text": f"{emoji} คำสั่ง #{cid} {('เสร็จแล้ว' if status == 'done' else 'ทำไม่สำเร็จ')}ครับ\n{result}"}])
        except Exception as e:
            print("dev command notify push error:", e)
    return {"ok": True}


@router.get("/api/cron/slips-triage-report")
async def cron_slips_triage_report(request: Request):
    """ตรวจย้อนหลังผลคัดแยก (อ่านอย่างเดียว ไม่มีข้อมูลส่วนบุคคล): ที่ตีกลับว่า 'ไม่ใช่สลิป' เป็นของใคร (ลงทะเบียน/จ่ายแล้วไหม)
    และรายการที่ Gemini ว่าเป็นสลิปแต่ต้องคนตรวจ"""
    _check_cron_key(request)
    rows = await supa.select_all("slips", params={
        "select": "id,line_user_id,status,amount,bank,auto_note,created_at", "ocr->>triage": "eq.true"})
    regs = await supa.select_all("registrations", params={"select": "line_user_id,paid"})
    paid_by_uid: dict[str, bool] = {}
    for r in regs:
        if r.get("line_user_id"):
            paid_by_uid[r["line_user_id"]] = paid_by_uid.get(r["line_user_id"], False) or bool(r.get("paid"))

    def owner(uid):
        return "ไม่ได้ลงทะเบียน" if uid not in paid_by_uid else ("ลงทะเบียน-จ่ายแล้ว" if paid_by_uid[uid] else "ลงทะเบียน-ยังไม่จ่าย")

    rej = [r for r in rows if r["status"] == "rejected"]
    ann = [r for r in rows if r["status"] == "review"]
    rej_by_owner: dict[str, int] = {}
    for r in rej:
        rej_by_owner[owner(r["line_user_id"])] = rej_by_owner.get(owner(r["line_user_id"]), 0) + 1
    return {
        "rejected_not_slip": len(rej), "rejected_by_owner": rej_by_owner,
        "rejected_unpaid_registrant_ids": [r["id"] for r in rej if owner(r["line_user_id"]) == "ลงทะเบียน-ยังไม่จ่าย"][:80],
        "likely_slips_for_human": [
            {"id": r["id"], "amount": r.get("amount"), "bank": r.get("bank"), "owner": owner(r["line_user_id"]),
             "note": (r.get("auto_note") or "")[:220]} for r in ann][:60],
    }


@router.api_route("/api/cron/slips-triage", methods=["GET", "POST"])
async def cron_slips_triage(request: Request):
    """?recall=1 = วัดความแม่นของตัวจำแนกกับสลิปที่ยืนยันแล้ว (ไม่เขียนอะไร) · ?apply=1&limit=N = คัดแยกจริง
    ไม่ใส่อะไร = นับผู้เข้าข่ายเฉย ๆ — เงียบเสมอ ไม่ส่งข้อความหาลูกค้า"""
    _check_cron_key(request)
    if request.query_params.get("recall") == "1":
        try:
            n = max(3, min(int(request.query_params.get("n", "10")), 11))
            off = max(0, int(request.query_params.get("offset", "0")))
        except ValueError:
            n, off = 10, 0
        return {"ok": True, "offset": off, **await _triage_recall_check(n, off)}
    if request.query_params.get("refresh_notes") == "1":
        return {"ok": True, **await _triage_refresh_notes()}
    apply = request.query_params.get("apply") == "1"
    try:
        limit = max(1, min(int(request.query_params.get("limit", "10")), 11))   # 1 คำขอ/4.5 วิ -> ต้องจบใน ~50 วิ
    except ValueError:
        limit = 10
    res = await _triage_slips(apply, limit)
    if apply:
        await supa.log_operation("cron", "slips.triage", {"limit": limit}, {k: v for k, v in res.items() if k != "items"})
    return {"ok": True, "applied": apply, **res}


@router.get("/api/cron/ai-baseline")
async def cron_ai_baseline(request: Request):
    """อ่านอย่างเดียว (?key=CRON_SECRET&days=30) — ตัวเลขว่าใครตอบลูกค้า + คำถามที่ซ้ำบ่อย"""
    _check_cron_key(request)
    try:
        days = max(3, min(int(request.query_params.get("days", "30")), 90))
    except ValueError:
        days = 30
    if request.query_params.get("gaps") == "1":
        # คำถามจริงที่ AI ตอบโดยไม่มีความรู้ใน KB รองรับ (จัดกลุ่มตามข้อความที่ย่อแล้ว) — ไว้ดูว่าควรเติมความรู้เรื่องอะไร
        ops = await supa.select_all("operations", params={
            "select": "params,created_at", "action": "like.gemini.kb_gap*",
            "created_at": f"gte.{_iso_ago(days=days)}", "order": "created_at.desc"})
        groups: dict[str, list] = {}
        for o in ops:
            q = ((o.get("params") or {}).get("q") or "").strip()
            if q:
                groups.setdefault(_norm_question(q) or q[:20], []).append(q[:90])
        rows = sorted(((len(v), v[0]) for v in groups.values()), reverse=True)
        return {"total_gap_questions": len(ops), "distinct": len(groups),
                "top": [{"count": c, "example": q} for c, q in rows[:80]]}
    return await _ai_baseline(days)


@router.api_route("/api/cron/kb-autogen", methods=["GET", "POST"])
async def cron_kb_autogen(request: Request):
    """สร้างบทความ KB เรื่องจัดซื้อจัดจ้างภาครัฐเพิ่มทีละน้อยแบบอัตโนมัติ (ค่าเริ่ม 2 บทความ/ครั้ง)
    เพื่อไม่ให้ยิง AI รัวเกินไป — ทุกบทความ enabled=false ต้องให้แอดมินตรวจก่อนเปิดใช้เสมอ"""
    _check_cron_key(request)
    if not (ANTHROPIC_API_KEY or GEMINI_API_KEY):
        return {"ok": True, "skipped": "no AI key set"}
    count = int(request.query_params.get("count") or 2)
    res = await _kb_autogen_batch(count, "cron")
    await supa.log_operation("cron", "kb.autogen.cron", {"count": count}, res)
    return {"ok": True, **res}


@router.get("/api/cron/richmenu-usage")
async def cron_richmenu_usage(request: Request):
    """สรุปการใช้ Rich Menu แบบอ่านอย่างเดียว (ต้องมี ?key=CRON_SECRET) — ตัวเลขรวม ไม่มีข้อมูลส่วนบุคคล
    แนบค่าตั้งค่าที่เกี่ยวกับ Rich Menu (ไม่ใช่ความลับ: เป็นแค่ richMenuId) และเวลา sync ล่าสุดด้วย"""
    _check_cron_key(request)
    data = await _richmenu_usage_data()
    data["config"] = {
        "unregistered_richmenu_id": await _get_setting("unregistered_richmenu_id", None),
        "reg_richmenu_map": await _get_setting("reg_richmenu_map", None),
        "slip_success_richmenu_id": SLIP_SUCCESS_RICHMENU_ID or None,
        "enforce_richmenu_id": ENFORCE_RICHMENU_ID or None,
        "gemini_trigger_menu_name": GEMINI_TRIGGER_MENU_NAME,
    }
    data["last_sync"] = await _cron_last_run("*richmenu.sync*")
    return data


@router.api_route("/api/cron/sync-richmenu", methods=["GET", "POST"])
async def cron_sync_richmenu(request: Request):
    """เรียกโดย scheduler (Supabase pg_cron) — auth ด้วย ?key=CRON_SECRET
    sync แบบ rolling: เอา user ที่ถูกเช็คนานสุดก่อน batch ละ ?limit (default 1500)"""
    if not _cron_authorized(request):
        raise HTTPException(403, "bad cron key")
    try:
        limit = min(int(request.query_params.get("limit", "1000")), 1000)  # 1 หน้า PostgREST, พอดี < 60s
    except ValueError:
        limit = 1000

    rows = await supa.select("line_users", params={
        "select": "line_user_id", "is_following": "eq.true",
        "order": "rich_menu_checked_at.asc.nullsfirst",
        "limit": str(limit),
    })
    uids = [r["line_user_id"] for r in rows]
    summary = await _sync_richmenu_for(uids, source="cron", actor="cron")
    await supa.log_operation("cron", "richmenu.sync.cron", {"limit": limit}, summary)
    return {"ok": True, **summary}


@router.api_route("/api/cron/enforce-richmenu", methods=["GET", "POST"])
async def cron_enforce_richmenu(request: Request):
    """(ปิดโดย default) บังคับ user ที่ current_rich_menu_id ไม่ตรงเป้าหมายให้ผูกกลับเป็น ENFORCE_RICHMENU_ID
    ยกเว้น user ที่อยู่ในเมนูที่ระบุใน ENFORCE_EXCLUDE_MENUS (เช่นเมนูแคมเปญที่ตั้งใจให้อยู่ต่อ)
    เปิดใช้งานโดยตั้ง env ENFORCE_RICHMENU_ID — ถ้าไม่ตั้ง endpoint นี้จะไม่ทำอะไรเลย (no-op ปลอดภัย)"""
    if not _cron_authorized(request):
        raise HTTPException(403, "bad cron key")
    if not ENFORCE_RICHMENU_ID:
        return {"ok": True, "skipped": "ENFORCE_RICHMENU_ID ไม่ได้ตั้งค่า — enforce ปิดอยู่"}
    try:
        limit = min(int(request.query_params.get("limit", "500")), 1000)
    except ValueError:
        limit = 500

    rows = await supa.select("line_users", params={
        "select": "line_user_id,current_rich_menu_id", "is_following": "eq.true",
        "current_rich_menu_id": f"not.eq.{ENFORCE_RICHMENU_ID}",
        "order": "rich_menu_checked_at.asc.nullsfirst",
        "limit": str(limit),
    })
    uids = [r["line_user_id"] for r in rows
            if (r.get("current_rich_menu_id") or "") not in ENFORCE_EXCLUDE_MENUS]
    if not uids:
        return {"ok": True, "total": 0, "assigned": 0, "fail": 0}

    old_map = await _fetch_current_menu_map(uids)
    sem = asyncio.Semaphore(8)
    results = {"ok": 0, "fail": 0}

    async def one(uid):
        async with sem:
            ok, code = await line.user_richmenu_link(uid, ENFORCE_RICHMENU_ID)
            results["ok" if ok else "fail"] += 1
            return uid, ok

    done = await asyncio.gather(*[one(u) for u in uids])
    ts = NOW()
    patch = [{
        "line_user_id": u,
        "current_rich_menu_id": ENFORCE_RICHMENU_ID if ok else old_map.get(u, {}).get("current_rich_menu_id"),
        "rich_menu_status": "assigned" if ok else old_map.get(u, {}).get("rich_menu_status"),
        "rich_menu_checked_at": ts, "updated_at": ts,
    } for u, ok in done]
    try:
        await supa.upsert("line_users", patch, on_conflict="line_user_id")
    except Exception as e:
        results["db_error"] = str(e)

    await _log_richmenu_diffs(old_map, patch, "enforce", "cron")
    await supa.log_operation("cron", "richmenu.enforce.cron",
                             {"richMenuId": ENFORCE_RICHMENU_ID, "limit": limit}, results,
                             "ok" if results["fail"] == 0 else "partial")
    return {"ok": True, "total": len(uids), "assigned": results["ok"], "fail": results["fail"]}


@router.api_route("/api/cron/richmenu-unregistered", methods=["GET", "POST"])
async def cron_richmenu_unregistered(request: Request):
    """ตั้งเวลาให้ทำงานเองต่อเนื่อง (migration 0016) — no-op ถ้ายังไม่ได้ตั้ง unregistered_richmenu_id"""
    _check_cron_key(request)
    try:
        limit = min(int(request.query_params.get("limit", "300")), 1000)
    except ValueError:
        limit = 300
    res = await _richmenu_auto_unregistered(limit=limit)
    await supa.log_operation("cron", "richmenu.auto_unregistered", {"limit": limit}, res,
                             "ok" if res.get("fail", 0) == 0 else "partial")
    return {"ok": True, **res}


@router.api_route("/api/cron/registrations-retag", methods=["GET", "POST"])
async def cron_registrations_retag(request: Request):
    _check_cron_key(request)
    res = await _retag_from_registrations()
    await supa.log_operation("cron", "registrations.retag", None, res)
    return {"ok": True, **res}


@router.api_route("/api/cron/backup", methods=["GET", "POST"])
async def cron_backup(request: Request):
    _check_cron_key(request)
    try:
        res = await _make_backup()
        await supa.log_operation("cron", "backup", None, res)
        return {"ok": True, **res}
    except Exception as e:
        await alert_admin("Backup ล้มเหลว", str(e), "backup")
        raise HTTPException(500, str(e))


@router.api_route("/api/cron/snapshot-stats", methods=["GET", "POST"])
async def cron_snapshot_stats(request: Request):
    _check_cron_key(request)
    date = (dt.date.today() - dt.timedelta(days=1)).strftime("%Y%m%d")
    try:
        followers = await line.insight_followers(date)
        delivery = await line.insight_message_delivery(date)
        quota = await line.message_quota()
    except Exception as e:
        raise HTTPException(400, f"insight error: {e}")

    q = quota.get("quota", {}).get("quota") or quota.get("quota", {})
    await supa.upsert("stats_daily", {
        "day": f"{date[:4]}-{date[4:6]}-{date[6:]}",
        "followers": followers.get("followers"),
        "targeted_reaches": followers.get("targetedReaches"),
        "blocks": followers.get("blocks"),
        "quota_type": q.get("type") if isinstance(q, dict) else None,
        "quota_limit": q.get("value") if isinstance(q, dict) else None,
        "quota_used": quota.get("totalUsage"),
        "raw": {"followers": followers, "delivery": delivery},
        "captured_at": NOW(),
    }, on_conflict="day")
    await supa.log_operation("cron", "stats.snapshot", {"date": date}, followers)
    return {"ok": True, "date": date, "followers": followers.get("followers")}


@router.api_route("/api/cron/heartbeat", methods=["GET", "POST"])
async def cron_heartbeat(request: Request):
    """เช็คว่า cron จำเป็นยังทำงานอยู่ไหม — แจ้งแอดมินถ้าเงียบเกินกำหนด"""
    _check_cron_key(request)
    stale = await _cron_stale()
    if stale:
        await alert_admin("⚠️ Cron ไม่ทำงาน", "\n".join(stale), throttle_key="cron_stale")
    await supa.log_operation("cron", "heartbeat", None, {"stale": stale})
    return {"ok": not stale, "stale": stale}


@router.get("/api/cron/users-backfill")
async def cron_users_backfill(request: Request, apply: int = 0):
    _check_cron_key(request)
    return await _backfill_users(bool(apply))


@router.get("/api/cron/slips-summary")
async def cron_slips_summary(request: Request):
    """อ่านอย่างเดียว (?key=CRON_SECRET) — ไว้ตรวจว่าทำไมสลิปค้าง"""
    _check_cron_key(request)
    return await _slips_summary()


@router.api_route("/api/cron/daily-digest", methods=["GET", "POST"])
async def cron_daily_digest(request: Request):
    """สรุปประจำวันส่งเข้า LINE แอดมิน"""
    _check_cron_key(request)
    y0 = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    t0 = dt.date.today().isoformat()

    async def _cnt(tb, extra=None):
        p = {"and": f"(created_at.gte.{y0},created_at.lt.{t0})"}
        if extra:
            p.update(extra)
        try:
            return await supa.count(tb, p)
        except Exception:
            return 0

    new_follow = await _cnt("follow_history", {"action": "eq.follow"})
    unfollow = await _cnt("follow_history", {"action": "eq.unfollow"})
    new_reg = await _cnt("registrations")
    msg_in = await _cnt("messages", {"direction": "eq.in"})
    slip_new = await supa.count("slips", {"status": "eq.new"})
    slip_review = await supa.count("slips", {"status": "eq.review"})
    tasks_overdue = 0
    try:
        tasks_overdue = await supa.count("tasks", {"status": "eq.open", "due_at": f"lt.{NOW()}"})
    except Exception:
        pass
    # รายได้เมื่อวาน
    rev = 0.0
    try:
        for s in await supa.select("slips", params={
                "select": "amount,reviewed_at,created_at", "status": "eq.verified",
                "and": f"(reviewed_at.gte.{y0},reviewed_at.lt.{t0})", "limit": "500"}):
            rev += float(s.get("amount") or 0)
    except Exception:
        pass

    ai_y = await _cnt("messages", {"by": "eq.gemini"})
    health, warn = await _health_digest_lines()

    lines = [f"📊 สรุปวันที่ {y0} · {'🟡 มีเรื่องต้องดู' if warn else '🟢 ระบบปกติ'}",
             f"👥 เพิ่มเพื่อน {new_follow} · เลิกติดตาม {unfollow}",
             f"📝 สมัครใหม่ {new_reg}",
             f"💬 ข้อความเข้า {msg_in} · 🤖 AI ตอบ {ai_y}",
             f"🧾 สลิปรอตรวจ {slip_new + slip_review} · ยืนยันแล้ว ฿{round(rev):,}"]
    if tasks_overdue:
        lines.append(f"⏰ งานเกินกำหนด {tasks_overdue}")
    lines.append("\n🩺 สุขภาพระบบ")
    lines.extend(health)
    lines.append(f"\nเปิดดู: {APP_URL}")
    text = "\n".join(lines)
    if request.query_params.get("dry") == "1":   # ดูตัวอย่างเฉย ๆ ไม่ส่งเข้า LINE ไม่บันทึก log
        return {"ok": True, "dry": True, "sent": 0, "preview": text}
    sent = 0
    for uid in ALERT_USER_IDS:
        try:
            code, *_ = await line.push(uid, [{"type": "text", "text": text}])
            sent += (code == 200)
        except Exception:
            pass
    await supa.log_operation("cron", "daily.digest", None, {"sent": sent})
    return {"ok": True, "sent": sent, "preview": text}


@router.api_route("/api/cron/run-automations", methods=["GET", "POST"])
async def cron_run_automations(request: Request):
    _check_cron_key(request)
    try:
        await _run_webhook_jobs(limit=10)  # backup drain (เผื่อ fire-and-forget ไม่ถึง)
    except Exception as e:
        print("webhook jobs drain error:", e)
    try:
        await _enroll_inactive_automations()
    except Exception as e:
        print("inactive enroll error:", e)
    due = await supa.select("automation_runs", params={
        "select": "*", "status": "eq.pending", "run_at": f"lte.{NOW()}",
        "order": "run_at.asc", "limit": "200"})
    if not due:
        await supa.log_operation("cron", "automation.run", None, {"ran": 0})  # heartbeat
        return {"ok": True, "ran": 0}
    autos = {a["id"]: a for a in await supa.select("automations", params={"select": "*"})}
    sent = failed = 0
    for run in due:
        a = autos.get(run["automation_id"])
        if not a or not a.get("enabled"):
            await supa.update("automation_runs", {"status": "skipped"}, {"id": f"eq.{run['id']}"})
            continue
        steps = a.get("steps") or []
        idx = run["step_idx"]
        if idx >= len(steps):
            await supa.update("automation_runs", {"status": "done"}, {"id": f"eq.{run['id']}"})
            continue
        # ยังตามอยู่ไหม
        u = await supa.select("line_users", params={
            "select": "is_following", "line_user_id": f"eq.{run['line_user_id']}", "limit": "1"})
        if not u or not u[0].get("is_following"):
            await supa.update("automation_runs", {"status": "skipped"}, {"id": f"eq.{run['id']}"})
            continue
        msgs = _normalize_messages(steps[idx].get("messages", []))
        code, _, _ = await line.push(run["line_user_id"], msgs)
        ok = code == 200
        sent += ok
        failed += (not ok)
        try:
            await supa.insert("messages", [{"line_user_id": run["line_user_id"], "direction": "out",
                                            "by": "automation", "msg_type": m.get("type"),
                                            "text": m.get("text"), "payload": m} for m in msgs])
        except Exception:
            pass
        await supa.update("automation_runs", {"status": "done" if ok else "failed"}, {"id": f"eq.{run['id']}"})
        # step ถัดไป
        if ok and idx + 1 < len(steps):
            nxt = steps[idx + 1]
            delay = int(nxt.get("delayHours", 0)) * 3600 + int(nxt.get("delayMinutes", 0)) * 60
            run_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=max(delay, 60))).isoformat()
            try:
                await supa.insert("automation_runs", {
                    "automation_id": a["id"], "line_user_id": run["line_user_id"],
                    "step_idx": idx + 1, "run_at": run_at, "status": "pending"})
            except Exception:
                pass
        if ok and idx == 0:
            await supa.update("automations", {"runs": (a.get("runs") or 0) + 1}, {"id": f"eq.{a['id']}"})
    await supa.log_operation("cron", "automation.run", {"due": len(due)}, {"sent": sent, "failed": failed})
    return {"ok": True, "ran": len(due), "sent": sent, "failed": failed}


@router.api_route("/api/cron/run-scheduled", methods=["GET", "POST"])
async def cron_run_scheduled(request: Request):
    _check_cron_key(request)
    due = await supa.select("scheduled_jobs", params={
        "select": "*", "status": "eq.pending", "run_at": f"lte.{NOW()}",
        "order": "run_at.asc", "limit": "10",
    })
    ran = []
    for job in due:
        p = job["payload"] or {}
        try:
            kind = job["kind"]
            if kind == "broadcast":
                sched_msgs = _normalize_messages(p.get("messages", []))
                sbid, sched_msgs = await _broadcast_begin(job.get("created_by"), "broadcast", sched_msgs, None)
                code, txt, rid = await line.broadcast(sched_msgs)
                ok = code == 200
                await _broadcast_finish(sbid, status="sent" if ok else "failed", line_request_id=rid,
                                        error=None if ok else txt[:300])
                res = {"code": code, "requestId": rid}
            elif kind == "richmenu_default":
                ok, txt = await line.richmenu_set_default(p["richMenuId"])
                res = {"ok": ok, "resp": txt[:150]}
            else:
                ok, res = False, {"error": "unknown kind"}
            await supa.update("scheduled_jobs",
                              {"status": "done" if ok else "failed", "result": res},
                              {"id": f"eq.{job['id']}"})
            ran.append({"id": job["id"], "ok": ok})

            # recurring -> ตั้ง job รอบถัดไป
            rep = job.get("repeat")
            if ok and rep:
                delta = {"daily": 1, "weekly": 7, "biweekly": 14, "monthly": 30}.get(rep)
                if delta:
                    nxt = dt.datetime.fromisoformat(job["run_at"]) + dt.timedelta(days=delta)
                    await supa.insert("scheduled_jobs", {
                        "kind": kind, "run_at": nxt.isoformat(), "payload": p,
                        "repeat": rep, "label": job.get("label"),
                        "created_by": job.get("created_by"),
                    })
        except Exception as e:
            await supa.update("scheduled_jobs", {"status": "failed", "result": {"error": str(e)}},
                              {"id": f"eq.{job['id']}"})
    return {"ok": True, "ran": ran}


@router.api_route("/api/cron/registrations-nonfriends", methods=["GET", "POST"])
async def cron_registrations_nonfriends(request: Request):
    """?apply=1 = ติดธงจริง (ไม่ใส่ = ดูตัวเลขเฉย ๆ) คืนเฉพาะตัวเลข ไม่มีรายชื่อ"""
    _check_cron_key(request)
    apply = request.query_params.get("apply") == "1"
    res = await _flag_nonfriend_registrants(apply, detail=False)
    if apply:
        await supa.log_operation("cron", "registrations.flag_nonfriends", None, res)
    return {"ok": True, "applied": apply, **res}


@router.api_route("/api/cron/task-reminders", methods=["GET", "POST"])
async def cron_task_reminders(request: Request):
    """แจ้งเตือนแอดมินแต่ละคนถ้ามีงานเกินกำหนด (push เข้า LINE)"""
    _check_cron_key(request)
    overdue = await supa.select("tasks", params={
        "select": "assigned_to,title,due_at", "status": "eq.open", "due_at": f"lt.{NOW()}", "limit": "500"})
    by_admin: dict[str, list] = {}
    for t in overdue:
        if t.get("assigned_to"):
            by_admin.setdefault(t["assigned_to"], []).append(t)
    sent = 0
    for uid, items in by_admin.items():
        txt = f"⏰ งานเกินกำหนด {len(items)} รายการ\n" + "\n".join(
            f"• {i['title']}" for i in items[:8]) + (f"\n…และอีก {len(items)-8}" if len(items) > 8 else "")
        txt += f"\n\nดูทั้งหมด: {APP_URL}/tasks"
        try:
            code, *_ = await line.push(uid, [{"type": "text", "text": txt}])
            sent += (code == 200)
        except Exception:
            pass
    return {"ok": True, "admins_notified": sent, "overdue": len(overdue)}


@router.api_route("/api/cron/reconcile-auto-mark", methods=["GET", "POST"])
async def cron_reconcile_auto_mark(request: Request):
    """ทุกวัน: มี slip status=verified ตรงคอร์สกับทะเบียนอยู่แล้ว แต่ registrations.paid ยังเป็น false
    (เคส 'paid_not_marked' ในหน้ากระทบยอด) -> mark paid=true ให้อัตโนมัติ (ข้อมูลยืนยันแล้วอยู่แล้ว แค่ sync flag)
    ไม่แตะเคส unpaid (ไม่มีสลิปเลย) หรือ slip_no_reg (จับคู่คอร์สไม่ได้) — สองเคสนั้นยังต้องให้แอดมินตรวจเอง"""
    _check_cron_key(request)
    data = await _reconcile_data()
    ids = [x["id"] for x in data["issues"]["paid_not_marked"]]
    marked = await _mark_registrations_paid_by_ids(ids)
    res = {"marked": marked, "candidate_ids": ids[:50]}
    await supa.log_operation("cron", "reconcile.auto_mark", {"count": marked}, res)
    return {"ok": True, **res}

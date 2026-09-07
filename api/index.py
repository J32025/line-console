"""
LINE Console API — FastAPI บน Vercel Python runtime
ทุก endpoint (ยกเว้น /api/webhook, /api/health) ต้องมี  Authorization: Bearer <LIFF id_token>
"""
import asyncio
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from _lib import line, supa
from _lib.auth import current_admin
from _lib.config import (LINE_CHANNEL_SECRET, CRON_SECRET, ALERT_USER_IDS,
                         LINE_CHANNEL_ACCESS_TOKEN, LIFF_CHANNEL_ID,
                         SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
                         LINE_LOGIN_CHANNEL_TOKEN, APP_URL)
import httpx

app = FastAPI(title="LINE Console API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

NOW = lambda: dt.datetime.now(dt.timezone.utc).isoformat()


# ============================================================
# rate limit (in-memory, ต่อ instance) + alert
# ============================================================
_hits: dict[str, list[float]] = {}


def _rate_limit(key: str, limit: int, window: float):
    now = time.time()
    q = _hits.setdefault(key, [])
    while q and q[0] < now - window:
        q.pop(0)
    if len(q) >= limit:
        raise HTTPException(429, "เรียกถี่เกินไป ลองใหม่อีกครั้ง")
    q.append(now)


_alert_last: dict[str, float] = {}


async def alert_admin(subject: str, detail: str = "", throttle_key: str | None = None):
    """แจ้ง error เข้า LINE ของแอดมิน (throttle 10 นาที/key)"""
    if not ALERT_USER_IDS:
        print("ALERT:", subject, detail)
        return
    k = throttle_key or subject
    if time.time() - _alert_last.get(k, 0) < 600:
        return
    _alert_last[k] = time.time()
    text = f"⚠️ LINE Console\n{subject}"
    if detail:
        text += f"\n\n{detail[:400]}"
    for uid in ALERT_USER_IDS:
        try:
            await line.push(uid, [{"type": "text", "text": text}])
        except Exception:
            pass


# ============================================================
# health / me
# ============================================================
@app.api_route("/r/{code}", methods=["GET"])
async def short_redirect(code: str, request: Request):
    from fastapi.responses import RedirectResponse
    rows = await supa.select("short_links", params={"code": f"eq.{code}", "select": "*", "limit": "1"})
    if not rows:
        return RedirectResponse(APP_URL, status_code=302)
    sl = rows[0]
    try:
        await supa.insert("link_clicks", {
            "code": code, "target": sl["target"], "broadcast_id": sl.get("broadcast_id"),
            "line_user_id": request.query_params.get("u"),
        })
        await supa.update("short_links", {"clicks": (sl.get("clicks") or 0) + 1}, {"code": f"eq.{code}"})
    except Exception:
        pass
    return RedirectResponse(sl["target"], status_code=302)


@app.get("/api/links")
async def links_list(admin=Depends(current_admin)):
    return {"links": await supa.select("short_links", params={
        "select": "*", "order": "created_at.desc", "limit": "100"})}


@app.post("/api/links")
async def link_create(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    target = (b.get("target") or "").strip()
    if not re.match(r"^https?://", target):
        raise HTTPException(400, "target ต้องเป็น URL")
    code = b.get("code") or os.urandom(4).hex()[:7]
    await supa.upsert("short_links", {
        "code": code, "target": target, "label": b.get("label"),
        "broadcast_id": b.get("broadcastId"), "created_by": admin["userId"],
    }, on_conflict="code")
    return {"ok": True, "code": code, "shortUrl": f"{APP_URL}/r/{code}"}


@app.get("/api/links/{code}/stats")
async def link_stats(code: str, admin=Depends(current_admin)):
    clicks = await supa.select("link_clicks", params={
        "code": f"eq.{code}", "select": "clicked_at,line_user_id", "order": "clicked_at.desc", "limit": "1000"})
    by_day: dict[str, int] = {}
    for c in clicks:
        by_day[c["clicked_at"][:10]] = by_day.get(c["clicked_at"][:10], 0) + 1
    return {"total": len(clicks), "unique_users": len({c["line_user_id"] for c in clicks if c["line_user_id"]}),
            "by_day": [{"day": k, "clicks": v} for k, v in sorted(by_day.items())]}


@app.delete("/api/links/{code}")
async def link_delete(code: str, admin=Depends(current_admin)):
    await supa.delete("short_links", {"code": f"eq.{code}"})
    return {"ok": True}


@app.get("/api/health")
async def health(deep: int = 0):
    out = {"ok": True, "time": NOW()}
    if not deep:
        return out
    # deep check
    checks = {}
    checks["env"] = {
        "line_token": bool(LINE_CHANNEL_ACCESS_TOKEN),
        "line_secret": bool(LINE_CHANNEL_SECRET),
        "liff_channel_id": bool(LIFF_CHANNEL_ID),
        "supabase": bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        "alerts": bool(ALERT_USER_IDS),
    }
    try:
        await supa.count("admins")
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e}"; out["ok"] = False
    try:
        q = await line.message_quota()
        checks["line_quota"] = q.get("quota", {}).get("quota", q.get("quota"))
        checks["line_usage"] = q.get("totalUsage")
    except Exception as e:
        checks["line_quota"] = f"error: {e}"; out["ok"] = False
    try:
        rows = await supa.select("operations", params={
            "select": "action,created_at", "action": "like.*cron*",
            "order": "created_at.desc", "limit": "5"})
        checks["last_cron"] = rows
    except Exception:
        pass
    out["checks"] = checks
    return out


@app.get("/api/me")
async def me(admin=Depends(current_admin)):
    return admin


# ============================================================
# webhook — รับ event จาก LINE (ไม่ต้อง auth, verify signature)
# ============================================================
@app.post("/api/webhook")
async def webhook(request: Request):
    ip = request.headers.get("x-forwarded-for", "?").split(",")[0].strip()
    _rate_limit(f"wh:{ip}", limit=120, window=60)  # 120 req/นาที/ip (LINE ยิงเป็น batch อยู่แล้ว)
    body = await request.body()
    sig = request.headers.get("x-line-signature", "")
    if LINE_CHANNEL_SECRET:
        mac = hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(base64.b64encode(mac).decode(), sig):
            raise HTTPException(403, "bad signature")
    elif sig:
        pass  # ยังไม่ตั้ง secret

    data = json.loads(body or "{}")
    events = data.get("events", [])
    # ข้าม event ที่ LINE ส่งซ้ำ (redelivery) — เราประมวลผลรอบแรกไปแล้ว
    events = [e for e in events if not e.get("deliveryContext", {}).get("isRedelivery")]
    rows_ev, user_patches, follow_rows, in_msgs = [], {}, [], []
    follow_uids, unfollow_uids = [], []

    for ev in events:
        et = ev.get("type")
        src = ev.get("source", {})
        uid = src.get("userId")
        msg = ev.get("message", {})
        pb = ev.get("postback", {})
        ts_ms = ev.get("timestamp")
        event_ts = dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc).isoformat() if ts_ms else NOW()
        dc = ev.get("deliveryContext", {})

        rows_ev.append({
            "event_type": et, "line_user_id": uid,
            "message_type": msg.get("type"), "text": msg.get("text") or pb.get("data"),
            "reply_token": ev.get("replyToken"),
            "postback_data": pb.get("data"),
            "webhook_event_id": ev.get("webhookEventId"),
            "event_ts": event_ts,
            "is_redelivery": bool(dc.get("isRedelivery")),
            "payload": ev,
        })
        if not uid:
            continue

        if et == "follow":
            follow_uids.append(uid)
            is_unblocked = bool(ev.get("follow", {}).get("isUnblocked"))
            follow_rows.append({"line_user_id": uid, "action": "follow",
                                "is_unblocked": is_unblocked, "event_ts": event_ts})
            user_patches[uid] = {
                "line_user_id": uid, "is_following": True, "unfollowed_at": None,
                "followed_at": event_ts, "last_event_at": event_ts,
                "source": "webhook", "updated_at": NOW(),
            }
        elif et == "unfollow":
            unfollow_uids.append(uid)
            follow_rows.append({"line_user_id": uid, "action": "unfollow", "event_ts": event_ts})
            user_patches[uid] = {
                "line_user_id": uid, "is_following": False,
                "unfollowed_at": event_ts, "last_event_at": event_ts,
                "source": "webhook", "updated_at": NOW(),
            }
        else:
            user_patches.setdefault(uid, {
                "line_user_id": uid, "is_following": True,
                "last_event_at": event_ts, "source": "webhook", "updated_at": NOW(),
            })

        # ---- inbox: บันทึกข้อความเข้า ----
        if et == "message":
            mt = msg.get("type")
            preview = msg.get("text") or {"image": "[รูปภาพ]", "video": "[วิดีโอ]", "audio": "[เสียง]",
                                          "file": f"[ไฟล์] {msg.get('fileName', '')}", "location": "[ตำแหน่ง]",
                                          "sticker": "[สติกเกอร์]"}.get(mt, f"[{mt}]")
            in_msgs.append({"line_user_id": uid, "direction": "in", "by": "user",
                            "msg_type": mt, "text": msg.get("text"), "payload": msg,
                            "created_at": event_ts})
            up = user_patches.get(uid, {"line_user_id": uid, "updated_at": NOW()})
            up["last_message_at"] = event_ts
            up["last_message_text"] = preview[:200]
            up["unread"] = None  # จะ increment ทีหลัง
            user_patches[uid] = up

    try:
        if rows_ev:
            await supa.insert("webhook_events", rows_ev)
        if in_msgs:
            await supa.insert("messages", in_msgs)
        if follow_rows:
            await supa.insert("follow_history", follow_rows)  # noqa

        # increment unread สำหรับคนที่ทักเข้ามา
        for uid in {m["line_user_id"] for m in in_msgs}:
            ex = await supa.select("line_users", params={
                "select": "unread", "line_user_id": f"eq.{uid}", "limit": "1"})
            cur_un = (ex[0].get("unread") if ex else 0) or 0
            n = sum(1 for m in in_msgs if m["line_user_id"] == uid)
            user_patches[uid]["unread"] = cur_un + n

        # อัปเดต counter + first_followed_at (ต้องอ่านค่าเดิมก่อน)
        touched = set(follow_uids) | set(unfollow_uids)
        if touched:
            existing = {r["line_user_id"]: r for r in await supa.select("line_users", params={
                "select": "line_user_id,follow_count,block_count,first_followed_at",
                "line_user_id": f"in.({','.join(touched)})", "limit": "1000",
            })}
            for uid in touched:
                old = existing.get(uid, {})
                p = user_patches[uid]
                if uid in follow_uids:
                    p["follow_count"] = (old.get("follow_count") or 0) + 1
                    if not old.get("first_followed_at"):
                        p["first_followed_at"] = p["followed_at"]
                if uid in unfollow_uids:
                    p["block_count"] = (old.get("block_count") or 0) + 1

        if user_patches:
            await supa.upsert("line_users", list(user_patches.values()), on_conflict="line_user_id")
    except Exception as e:
        print("webhook store error:", e)
        await alert_admin("webhook เก็บข้อมูลไม่สำเร็จ", str(e), "wh_store")

    # ---- ดึงโปรไฟล์คนที่เพิ่ง follow (จังหวะที่ดีที่สุด) ----
    if follow_uids:
        try:
            patch = []
            for uid in list(set(follow_uids))[:20]:
                p = await line.get_profile(uid)
                if p:
                    patch.append({
                        "line_user_id": uid,
                        "display_name": _clean_str(p.get("displayName")),
                        "picture_url": _clean_str(p.get("pictureUrl")),
                        "status_message": _clean_str(p.get("statusMessage")),
                        "language": _clean_str(p.get("language")),
                        "updated_at": NOW(),
                    })
            if patch:
                await supa.upsert("line_users", patch, on_conflict="line_user_id")
        except Exception as e:
            print("follow profile fetch error:", e)

    # ---- auto-reply (ห้าม block webhook เกิน 12 วิ, ห้าม 500) ----
    try:
        await asyncio.wait_for(_handle_auto_replies(events), timeout=12)
    except BaseException as e:  # noqa: BLE001 — webhook ต้องตอบ 200 เสมอ
        print("auto-reply error:", repr(e))

    # ---- automation: trigger=follow ----
    if follow_uids:
        try:
            await _enroll_automations("follow", list(set(follow_uids)))
        except Exception as e:
            print("automation enroll error:", e)
    return {"ok": True}


async def _enroll_automations(trigger: str, uids: list[str]):
    autos = await supa.select("automations", params={
        "select": "id,steps", "enabled": "eq.true", "trigger": f"eq.{trigger}"})
    if not autos:
        return
    rows = []
    for a in autos:
        steps = a.get("steps") or []
        if not steps:
            continue
        delay = int(steps[0].get("delayHours", 0)) * 3600 + int(steps[0].get("delayMinutes", 0)) * 60
        run_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=delay)).isoformat()
        for uid in uids:
            rows.append({"automation_id": a["id"], "line_user_id": uid, "step_idx": 0,
                         "run_at": run_at, "status": "pending"})
    if rows:
        # on_conflict = ไม่ลง run ซ้ำถ้าคน ๆ นั้นเคยเข้า step 0 ของ automation นี้แล้ว
        try:
            await supa.upsert("automation_runs", rows, on_conflict="automation_id,line_user_id,step_idx")
        except Exception:
            for r in rows:
                try:
                    await supa.insert("automation_runs", r)
                except Exception:
                    pass


def _match(rule: dict, text: str) -> bool:
    t = (text or "").lower().strip()
    kws = [k.lower().strip() for k in (rule.get("keywords") or []) if k.strip()]
    mt = rule.get("match_type", "contains")
    if mt in ("any", "welcome"):
        return mt == "any"  # welcome จับที่ event follow แยกต่างหาก
    if not kws:
        return False
    if mt == "exact":
        return t in kws
    if mt == "prefix":
        return any(t.startswith(k) for k in kws)
    return any(k in t for k in kws)  # contains / postback


# trigger -> ประเภท event/message ที่ทำให้กฎทำงาน
TEXT_TRIGGERS = ("text", "fallback")
MSG_TYPE_TRIGGERS = ("sticker", "image", "video", "audio", "file", "location")

_PLACEHOLDERS = ("{name}", "{displayName}", "{{name}}", "{{displayName}}", "{ชื่อ}")


def _has_placeholder(messages: list) -> bool:
    return any(isinstance(m, dict) and m.get("type") == "text"
              and any(p in (m.get("text") or "") for p in _PLACEHOLDERS)
              for m in messages)


def _personalize(messages: list, name: str) -> list:
    name = name or "เพื่อน"
    out = []
    for m in messages:
        m2 = dict(m) if isinstance(m, dict) else m
        if isinstance(m2, dict) and m2.get("type") == "text" and m2.get("text"):
            txt = m2["text"]
            for p in _PLACEHOLDERS:
                txt = txt.replace(p, name)
            m2["text"] = txt
        out.append(m2)
    return out


async def _reply_rule(reply_token: str, rule: dict, name: str | None = None):
    msgs = rule["messages"][:5]
    if name is not None and _has_placeholder(msgs):
        msgs = _personalize(msgs, name)
    code, _ = await line.reply(reply_token, msgs)
    if code == 200:
        await supa.update("auto_replies",
                          {"hits": (rule.get("hits") or 0) + 1, "last_hit_at": NOW()},
                          {"id": f"eq.{rule['id']}"})
    return code == 200


def _pick_rule(event: dict, rules: list):
    """เลือกกฎแรกที่ตรงกับ event (rules เรียง priority.desc แล้ว)"""
    et = event["type"]
    if et == "follow":
        return next((r for r in rules if r["trigger"] == "follow"), None)
    if et == "postback":
        data = event.get("postback", {}).get("data", "")
        return next((r for r in rules if r["trigger"] == "postback" and _match(r, data)), None)
    if et == "beacon":
        return next((r for r in rules if r["trigger"] == "beacon"), None)
    if et == "message":
        mtype = event.get("message", {}).get("type")
        if mtype == "text":
            text = event["message"]["text"]
            r = next((r for r in rules if r["trigger"] == "text" and _match(r, text)), None)
            if r:
                return r
            # ไม่มีคีย์เวิร์ดไหนตรง -> fallback
            return next((r for r in rules if r["trigger"] == "fallback"), None)
        if mtype in MSG_TYPE_TRIGGERS:
            return next((r for r in rules if r["trigger"] == mtype), None)
    return None


async def _handle_auto_replies(events: list):
    repliable = [e for e in events if e.get("replyToken") and e.get("type") in
                 ("message", "follow", "postback", "beacon")]
    if not repliable:
        return
    rules = await supa.select("auto_replies", params={
        "select": "*", "enabled": "eq.true", "order": "priority.desc,id.asc", "limit": "300",
    })
    for r in rules:
        r.setdefault("trigger", "text")
    if not rules:
        return

    # หา user ที่ปิด auto-reply ไว้ (แอดมินกำลังคุยเอง)
    uids = {e.get("source", {}).get("userId") for e in repliable if e.get("source", {}).get("userId")}
    paused = set()
    if uids:
        rows = await supa.select("line_users", params={
            "select": "line_user_id,auto_reply_paused", "line_user_id": f"in.({','.join(uids)})",
            "auto_reply_paused": "eq.true", "limit": "1000"})
        paused = {r["line_user_id"] for r in rows}

    name_cache: dict[str, str] = {}
    async def name_of(uid):
        if not uid:
            return None
        if uid not in name_cache:
            p = await line.get_profile(uid)
            name_cache[uid] = (p or {}).get("displayName") or "เพื่อน"
        return name_cache[uid]

    out_msgs = []
    for e in repliable:
        try:
            uid = e.get("source", {}).get("userId")
            if uid in paused:
                continue
            rule = _pick_rule(e, rules)
            if not rule:
                continue
            nm = await name_of(uid) if _has_placeholder(rule["messages"]) else None
            if await _reply_rule(e["replyToken"], rule, nm):
                for m in rule["messages"][:5]:
                    out_msgs.append({"line_user_id": uid, "direction": "out", "by": "auto",
                                     "msg_type": m.get("type"), "text": m.get("text"), "payload": m})
        except Exception as ex:
            print("auto-reply one error:", repr(ex))
    if out_msgs:
        try:
            await supa.insert("messages", out_msgs)
        except Exception:
            pass


# ============================================================
# dashboard
# ============================================================
@app.get("/api/dashboard")
async def dashboard(admin=Depends(current_admin)):
    total = await supa.count("line_users")
    following = await supa.count("line_users", {"is_following": "eq.true"})
    no_menu = await supa.count("line_users", {"is_following": "eq.true", "rich_menu_status": "eq.none"})
    bot = {}
    quota = {}
    try:
        bot = await line.bot_info()
        quota = await line.message_quota()
    except Exception as e:
        bot = {"error": str(e)}
    recent_ops = await supa.select("operations", params={
        "select": "id,actor,action,status,created_at", "order": "created_at.desc", "limit": "8",
    })
    recent_bc = await supa.select("broadcasts", params={
        "select": "id,kind,target_count,status,created_at", "order": "created_at.desc", "limit": "5",
    })
    trend = await supa.select("stats_daily", params={
        "select": "day,followers,targeted_reaches,blocks", "order": "day.desc", "limit": "30",
    })
    # นับ event 7 วันล่าสุด แยกชนิด
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
    ev7 = {}
    for et in ("follow", "unfollow", "message"):
        ev7[et] = await supa.count("webhook_events", {"event_type": f"eq.{et}", "created_at": f"gte.{since}"})
    return {
        "users": {"total": total, "following": following, "no_menu": no_menu},
        "bot": bot, "quota": quota,
        "recent_operations": recent_ops, "recent_broadcasts": recent_bc,
        "trend": list(reversed(trend)),
        "events_7d": ev7,
    }


# ============================================================
# RICH MENU
# ============================================================
@app.get("/api/richmenus")
async def richmenus(admin=Depends(current_admin)):
    menus = await line.richmenu_list()
    default_id = await line.richmenu_get_default()
    aliases = await line.richmenu_alias_list()
    # cache ลง DB
    try:
        await supa.upsert("rich_menus", [{
            "rich_menu_id": m["richMenuId"], "name": m.get("name"),
            "chat_bar_text": m.get("chatBarText"), "selected": m.get("selected"),
            "size": m.get("size"), "areas": m.get("areas"),
            "is_default": m["richMenuId"] == default_id, "synced_at": NOW(),
        } for m in menus], on_conflict="rich_menu_id")
    except Exception:
        pass
    return {"menus": menus, "defaultRichMenuId": default_id, "aliases": aliases}


@app.get("/api/richmenu/usage")
async def richmenu_usage(admin=Depends(current_admin)):
    """นับจำนวน user ที่ผูกแต่ละ rich menu อยู่ (จาก DB) เรียงมาก→น้อย"""
    rows = await supa.select_all("line_users", params={
        "select": "current_rich_menu_id", "is_following": "eq.true",
    })
    counts: dict[str, int] = {}
    for r in rows:
        k = r.get("current_rich_menu_id") or "__none__"
        counts[k] = counts.get(k, 0) + 1

    names = {m["richMenuId"]: m.get("name") for m in await line.richmenu_list()}
    try:
        default_id = await line.richmenu_get_default()
    except Exception:
        default_id = None

    items = [{
        "richMenuId": None if k == "__none__" else k,
        "name": "— ไม่มีเมนู —" if k == "__none__" else (names.get(k) or "(เมนูถูกลบแล้ว)"),
        "count": v,
        "isDefault": k == default_id,
        "exists": k == "__none__" or k in names,
    } for k, v in counts.items()]
    items.sort(key=lambda x: -x["count"])
    return {"total": len(rows), "items": items, "defaultRichMenuId": default_id}


@app.post("/api/richmenu/default")
async def set_default(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    rid = b.get("richMenuId")
    if not rid:
        raise HTTPException(400, "ต้องระบุ richMenuId")
    ok, txt = await line.richmenu_set_default(rid)
    await supa.log_operation(admin["userId"], "richmenu.set_default", {"richMenuId": rid},
                             {"ok": ok, "resp": txt[:200]}, "ok" if ok else "error")
    if not ok:
        raise HTTPException(400, txt)
    return {"ok": True}


@app.delete("/api/richmenu/default")
async def clear_default(admin=Depends(current_admin)):
    ok = await line.richmenu_clear_default()
    await supa.log_operation(admin["userId"], "richmenu.clear_default", None, {"ok": ok})
    return {"ok": ok}


@app.post("/api/richmenu/create")
async def create_menu(req: Request, admin=Depends(current_admin)):
    """สร้าง rich menu + (ถ้าส่ง imageBase64 มา) อัปโหลดรูปให้เลย"""
    b = await req.json()
    payload = b.get("richMenu") or {k: v for k, v in b.items() if k != "imageBase64"}
    menu = await line.richmenu_create(payload)
    rid = menu.get("richMenuId")

    img = b.get("imageBase64")
    if img and rid:
        if "," in img:
            header, img = img.split(",", 1)
            ctype = "image/jpeg" if "jpeg" in header or "jpg" in header else "image/png"
        else:
            ctype = "image/png"
        content = base64.b64decode(img)
        ok, txt = await line.richmenu_upload_image(rid, content, ctype)
        if not ok:
            await line.richmenu_delete(rid)
            raise HTTPException(400, f"อัปโหลดรูปไม่ผ่าน: {txt[:200]}")

    if b.get("setDefault") and rid:
        await line.richmenu_set_default(rid)
    await supa.log_operation(admin["userId"], "richmenu.create", payload, menu)
    return menu


@app.post("/api/richmenu/{rid}/image")
async def upload_menu_image(rid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    img = b.get("imageBase64", "")
    if "," in img:
        header, img = img.split(",", 1)
        ctype = "image/jpeg" if "jpeg" in header or "jpg" in header else "image/png"
    else:
        ctype = "image/png"
    ok, txt = await line.richmenu_upload_image(rid, base64.b64decode(img), ctype)
    if not ok:
        raise HTTPException(400, txt)
    return {"ok": True}


@app.delete("/api/richmenu/{rid}")
async def delete_menu(rid: str, admin=Depends(current_admin)):
    ok = await line.richmenu_delete(rid)
    await supa.log_operation(admin["userId"], "richmenu.delete", {"richMenuId": rid}, {"ok": ok})
    return {"ok": ok}


@app.post("/api/richmenu/alias")
async def create_alias(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    ok, txt = await line.richmenu_alias_create(b["richMenuAliasId"], b["richMenuId"])
    if not ok:
        raise HTTPException(400, txt)
    return {"ok": True}


@app.delete("/api/richmenu/alias/{alias_id}")
async def delete_alias(alias_id: str, admin=Depends(current_admin)):
    return {"ok": await line.richmenu_alias_delete(alias_id)}


@app.post("/api/richmenu/assign")
async def assign(req: Request, admin=Depends(current_admin)):
    """bulk assign: mode = 'link' (default/link/unlink) + target = 'all'|'none'|'list'|'tag'"""
    b = await req.json()
    rid = b.get("richMenuId")
    mode = b.get("mode", "link")           # link | unlink
    target = b.get("target", "list")       # list | all | none | tag
    set_default_too = b.get("setDefault", False)

    if mode == "link" and not rid:
        raise HTTPException(400, "ต้องระบุ richMenuId")

    # หา userIds
    if target == "list":
        uids = [u.strip() for u in b.get("userIds", []) if u.strip()]
    elif target == "segment":
        seg = await supa.select("segments", params={"id": f"eq.{b.get('segmentId')}", "select": "filter", "limit": "1"})
        uids = await _uids_by_filter(seg[0]["filter"] if seg else {})
    elif target == "filter":
        uids = await _uids_by_filter(b.get("filter", {}))
    elif target == "none":
        uids = await _uids_by_filter({"noMenu": True})
    elif target == "tag":
        uids = await _uids_by_filter({"tag": b.get("tag", "")})
    else:  # all
        uids = await _uids_by_filter({})

    if not uids:
        raise HTTPException(400, "ไม่มี userId ปลายทาง")

    if set_default_too and rid:
        await line.richmenu_set_default(rid)

    # ยิงแบบ concurrent มี retry
    sem = asyncio.Semaphore(8)
    results = {"ok": 0, "fail": 0, "errors": []}

    async def one(uid):
        async with sem:
            if mode == "unlink":
                ok = await line.user_richmenu_unlink(uid)
                code = 200 if ok else 0
            else:
                ok, code = await line.user_richmenu_link(uid, rid)
            if ok:
                results["ok"] += 1
            else:
                results["fail"] += 1
                if len(results["errors"]) < 50:
                    results["errors"].append({"userId": uid, "code": code})
            return uid, ok

    done = await asyncio.gather(*[one(u) for u in uids])

    # อัปเดต DB
    ts = NOW()
    patch_rows = [{
        "line_user_id": u, "is_following": True,
        "current_rich_menu_id": (rid if (ok and mode == "link") else None),
        "rich_menu_status": ("assigned" if (ok and mode == "link") else "none"),
        "rich_menu_checked_at": ts, "updated_at": ts,
    } for u, ok in done]
    try:
        await supa.upsert("line_users", patch_rows, on_conflict="line_user_id")
    except Exception as e:
        results["db_error"] = str(e)

    await supa.log_operation(admin["userId"], f"richmenu.{mode}",
                             {"richMenuId": rid, "target": target, "count": len(uids)}, results,
                             "ok" if results["fail"] == 0 else "partial")
    return {"total": len(uids), **results}


async def _sync_richmenu_for(uids: list[str]) -> dict:
    if not uids:
        return {"total": 0, "assigned": 0, "none": 0, "error": 0}
    menus = {m["richMenuId"]: m.get("name") for m in await line.richmenu_list()}
    sem = asyncio.Semaphore(10)
    summary = {"assigned": 0, "none": 0, "error": 0}
    patch = []

    async def one(uid):
        async with sem:
            try:
                rid = await line.user_richmenu_get(uid)
                st = "assigned" if rid else "none"
            except Exception:
                rid, st = None, "error"
            summary[st] = summary.get(st, 0) + 1
            patch.append({
                "line_user_id": uid, "current_rich_menu_id": rid or None,
                "rich_menu_name": menus.get(rid) if rid else None,
                "rich_menu_status": st, "rich_menu_checked_at": NOW(), "updated_at": NOW(),
            })

    await asyncio.gather(*[one(u) for u in uids])
    try:
        for i in range(0, len(patch), 500):
            await supa.upsert("line_users", patch[i:i + 500], on_conflict="line_user_id")
    except Exception as e:
        summary["db_error"] = str(e)
    return {"total": len(uids), **summary}


@app.post("/api/richmenu/sync")
async def richmenu_sync(req: Request, admin=Depends(current_admin)):
    """เช็ค richmenu ปัจจุบันของ user แล้วบันทึกลง DB"""
    b = await req.json()
    if b.get("target") == "list":
        uids = [u.strip() for u in b.get("userIds", []) if u.strip()]
    else:
        rows = await supa.select_all("line_users", params={
            "select": "line_user_id", "is_following": "eq.true",
        })
        uids = [r["line_user_id"] for r in rows]
    if not uids:
        raise HTTPException(400, "ไม่มี user ให้ sync")
    summary = await _sync_richmenu_for(uids)
    await supa.log_operation(admin["userId"], "richmenu.sync", {"count": len(uids)}, summary)
    return summary


@app.api_route("/api/cron/sync-richmenu", methods=["GET", "POST"])
async def cron_sync_richmenu(request: Request):
    """เรียกโดย scheduler (Supabase pg_cron) — auth ด้วย ?key=CRON_SECRET
    sync แบบ rolling: เอา user ที่ถูกเช็คนานสุดก่อน batch ละ ?limit (default 1500)"""
    if CRON_SECRET:
        key = request.query_params.get("key") or request.headers.get("x-cron-key", "")
        if key != CRON_SECRET:
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
    summary = await _sync_richmenu_for(uids)
    await supa.log_operation("cron", "richmenu.sync.cron", {"limit": limit}, summary)
    return {"ok": True, **summary}


# ============================================================
# USERS
# ============================================================
# ---------- custom field defs ----------
@app.get("/api/fields")
async def list_fields(admin=Depends(current_admin)):
    return {"fields": await supa.select("field_defs", params={"select": "*", "order": "sort,key"})}


@app.post("/api/fields")
async def save_field(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    key = re.sub(r"[^a-z0-9_]", "", (b.get("key") or "").lower())
    if not key:
        raise HTTPException(400, "key ต้องเป็น a-z 0-9 _")
    await supa.upsert("field_defs", {
        "key": key, "label": b.get("label") or key, "type": b.get("type", "text"),
        "options": b.get("options", []), "sort": int(b.get("sort", 0)),
    }, on_conflict="key")
    return {"ok": True, "key": key}


@app.delete("/api/fields/{key}")
async def del_field(key: str, admin=Depends(current_admin)):
    await supa.delete("field_defs", {"key": f"eq.{key}"})
    return {"ok": True}


@app.get("/api/users")
async def users(admin=Depends(current_admin), limit: int = 100, offset: int = 0,
                q: str = "", following: str = "", menu: str = "", tag: str = ""):
    params = {
        "select": "line_user_id,display_name,picture_url,is_following,current_rich_menu_id,"
                  "rich_menu_name,rich_menu_status,source,tags,note,custom,updated_at",
        "order": "updated_at.desc",
        "limit": str(min(limit, 1000)), "offset": str(offset),
    }
    if q:
        params["or"] = f"(line_user_id.ilike.*{q}*,display_name.ilike.*{q}*,note.ilike.*{q}*)"
    if following in ("true", "false"):
        params["is_following"] = f"eq.{following}"
    if menu == "none":
        params["current_rich_menu_id"] = "is.null"
    elif menu:
        params["current_rich_menu_id"] = f"eq.{menu}"
    if tag:
        params["tags"] = "cs.{" + tag + "}"
    rows = await supa.select("line_users", params=params, headers={"Prefer": "count=exact"})
    total = await supa.count("line_users", {k: v for k, v in params.items()
                                            if k in ("is_following", "current_rich_menu_id", "or", "tags")})
    return {"users": rows, "total": total, "limit": limit, "offset": offset}


@app.post("/api/users/bulk-tag")
async def users_bulk_tag(req: Request, admin=Depends(current_admin)):
    """ใส่/ลบ tag หลายคนพร้อมกัน — target: list | filter | segment"""
    b = await req.json()
    add = [t.strip() for t in b.get("add", []) if t.strip()]
    remove = set(t.strip() for t in b.get("remove", []) if t.strip())
    if b.get("target") == "segment":
        seg = await supa.select("segments", params={"id": f"eq.{b.get('segmentId')}", "select": "filter", "limit": "1"})
        uids = await _uids_by_filter(seg[0]["filter"] if seg else {})
    elif b.get("target") == "filter":
        uids = await _uids_by_filter(b.get("filter", {}))
    else:
        uids = [u.strip() for u in b.get("userIds", []) if u.strip()]
    if not uids:
        raise HTTPException(400, "ไม่มีปลายทาง")

    n = 0
    for i in range(0, len(uids), 400):
        chunk = uids[i:i + 400]
        rows = await supa.select("line_users", params={
            "select": "line_user_id,tags", "line_user_id": f"in.({','.join(chunk)})", "limit": "500"})
        patch = []
        for r in rows:
            cur = set(r.get("tags") or [])
            new = (cur | set(add)) - remove
            if new != cur:
                patch.append({"line_user_id": r["line_user_id"], "tags": sorted(new), "updated_at": NOW()})
        if patch:
            await supa.upsert("line_users", patch, on_conflict="line_user_id")
            n += len(patch)
    await supa.log_operation(admin["userId"], "users.bulk_tag", {"count": len(uids), "add": add, "remove": list(remove)}, {"changed": n})
    return {"ok": True, "target": len(uids), "changed": n}


@app.get("/api/export/users")
async def export_users(admin=Depends(current_admin), following: str = "", tag: str = ""):
    f = {}
    if following in ("true", "false"):
        f["following"] = following
    if tag:
        f["tags"] = [tag]
    else:
        f["following"] = f.get("following", None)
    params = {"select": "line_user_id,display_name,status_message,language,is_following,"
                        "current_rich_menu_id,rich_menu_name,rich_menu_status,source,tags,note,"
                        "custom,follow_count,block_count,first_followed_at,last_message_at,updated_at"}
    if following in ("true", "false"):
        params["is_following"] = f"eq.{following}"
    if tag:
        params["tags"] = "cs.{" + tag + "}"
    rows = await supa.select_all("line_users", params=params)
    fields = await supa.select("field_defs", params={"select": "key,label", "order": "sort"})
    cols = ["line_user_id", "display_name", "status_message", "language", "is_following",
            "rich_menu_name", "rich_menu_status", "source", "tags", "note",
            "follow_count", "block_count", "first_followed_at", "last_message_at", "updated_at"]
    ck = [f["key"] for f in fields]
    header = cols + [f"custom.{k}" for k in ck]

    def esc(v):
        if v is None:
            return ""
        if isinstance(v, list):
            v = "|".join(map(str, v))
        s = str(v)
        return f'"{s.replace(chr(34), chr(34) * 2)}"' if any(c in s for c in ',"\n') else s

    lines = [",".join(header)]
    for r in rows:
        row = [esc(r.get(c)) for c in cols] + [esc((r.get("custom") or {}).get(k)) for k in ck]
        lines.append(",".join(row))
    from fastapi.responses import Response
    return Response("﻿" + "\r\n".join(lines), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="users-{dt.date.today()}.csv"'})


@app.post("/api/users/import")
async def users_import(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    raw = b.get("userIds", [])
    tag = b.get("tag")
    note = b.get("note")
    uids, seen = [], set()
    for u in raw:
        u = str(u).strip().split(",")[0]
        if u.startswith("U") and len(u) == 33 and u not in seen:
            seen.add(u)
            uids.append(u)
    if not uids:
        raise HTTPException(400, "ไม่พบ userId ที่ถูกต้อง (U + 32 hex)")

    existing = set()
    for i in range(0, len(uids), 800):
        chunk = uids[i:i + 800]
        existing |= {r["line_user_id"] for r in await supa.select("line_users", params={
            "select": "line_user_id", "line_user_id": f"in.({','.join(chunk)})", "limit": "1000",
        })}
    new = [u for u in uids if u not in existing]
    ts = NOW()
    rows = [{
        "line_user_id": u, "source": "import", "is_following": True,
        "tags": [tag] if tag else [], "note": note, "updated_at": ts,
    } for u in new]
    if rows:
        for i in range(0, len(rows), 500):
            await supa.upsert("line_users", rows[i:i + 500], on_conflict="line_user_id")
    await supa.log_operation(admin["userId"], "users.import",
                             {"submitted": len(raw)}, {"new": len(new), "dup": len(uids) - len(new)})
    return {"submitted": len(raw), "valid": len(uids), "new": len(new),
            "duplicate": len(uids) - len(new), "duplicates": list(existing & set(uids))}


def _clean_str(s):
    if not s:
        return s
    s = "".join(ch for ch in s if ch in "\n\t" or ord(ch) >= 0x20)
    return s or None


@app.post("/api/users/refresh-profile")
async def refresh_profile(req: Request, admin=Depends(current_admin)):
    """ดึง displayName/รูป/statusMessage/ภาษา จาก LINE
    target: 'list' (userIds), 'missing' (ที่ยังไม่มีชื่อ, default), 'all' (ทุกคน)
    เรียกซ้ำจนกว่า remaining = 0 (batch ละ ~limit คน)"""
    b = await req.json()
    target = b.get("target", "missing")
    limit = min(int(b.get("limit", 400)), 800)

    if target == "list":
        uids = [u.strip() for u in b.get("userIds", []) if u.strip()]
        remaining_after = 0
    else:
        params = {"select": "line_user_id", "is_following": "eq.true",
                  "order": "updated_at.asc", "limit": str(limit)}
        if target == "missing":
            params["display_name"] = "is.null"
        rows = await supa.select("line_users", params=params)
        uids = [r["line_user_id"] for r in rows]
        remaining_after = 0
        if target == "missing":
            remaining_after = max(0, await supa.count(
                "line_users", {"is_following": "eq.true", "display_name": "is.null"}) - len(uids))

    sem = asyncio.Semaphore(12)
    got = [0]
    unfollow = [0]
    patch = []

    async def one(uid):
        async with sem:
            p = await line.get_profile(uid)
            if p:
                got[0] += 1
                patch.append({
                    "line_user_id": uid,
                    "display_name": _clean_str(p.get("displayName")),
                    "picture_url": _clean_str(p.get("pictureUrl")),
                    "status_message": _clean_str(p.get("statusMessage")),
                    "language": _clean_str(p.get("language")),
                    "is_following": True, "updated_at": NOW(),
                })
            else:
                unfollow[0] += 1
                patch.append({"line_user_id": uid, "is_following": False, "updated_at": NOW()})

    await asyncio.gather(*[one(u) for u in uids])
    for i in range(0, len(patch), 400):
        await supa.upsert("line_users", patch[i:i + 400], on_conflict="line_user_id")
    await supa.log_operation(admin["userId"], "users.refresh_profile",
                             {"count": len(uids)}, {"got": got[0], "unfollow": unfollow[0]})
    return {"processed": len(uids), "profiles_fetched": got[0],
            "not_following": unfollow[0], "remaining": remaining_after}


@app.post("/api/users/sync-followers")
async def sync_followers(admin=Depends(current_admin)):
    """ต้องเป็น Verified/Premium OA — วน /followers/ids"""
    ids, cursor, pages = [], None, 0
    try:
        while True:
            data = await line.followers_ids(1000, cursor)
            ids.extend(data.get("userIds", []))
            pages += 1
            cursor = data.get("next")
            if not cursor or pages > 60:
                break
    except Exception as e:
        raise HTTPException(400, f"followers/ids ใช้ไม่ได้ (ต้อง Verified/Premium OA): {e}")

    ts = NOW()
    rows = [{"line_user_id": u, "source": "followers_api", "is_following": True, "updated_at": ts}
            for u in dict.fromkeys(ids)]
    for i in range(0, len(rows), 500):
        await supa.upsert("line_users", rows[i:i + 500], on_conflict="line_user_id")
    await supa.log_operation(admin["userId"], "users.sync_followers", None, {"count": len(rows)})
    return {"followers": len(rows), "pages": pages}


# ============================================================
# INBOX (แชต + human takeover)
# ============================================================
@app.get("/api/inbox")
async def inbox_list(admin=Depends(current_admin), limit: int = 40, offset: int = 0,
                     filter: str = "all"):
    params = {
        "select": "line_user_id,display_name,picture_url,last_message_at,last_message_text,"
                  "unread,auto_reply_paused,assigned_to,is_following",
        "order": "last_message_at.desc.nullslast",
        "limit": str(min(limit, 100)), "offset": str(offset),
        "last_message_at": "not.is.null",
    }
    if filter == "unread":
        params["unread"] = "gt.0"
    elif filter == "mine":
        params["assigned_to"] = f"eq.{admin['userId']}"
    elif filter == "paused":
        params["auto_reply_paused"] = "eq.true"
    rows = await supa.select("line_users", params=params)
    total_unread = await supa.count("line_users", {"unread": "gt.0"})
    return {"conversations": rows, "total_unread": total_unread}


@app.get("/api/inbox/{uid}")
async def inbox_thread(uid: str, admin=Depends(current_admin), before: str = "", limit: int = 50):
    urows = await supa.select("line_users", params={
        "select": "line_user_id,display_name,picture_url,status_message,is_following,"
                  "auto_reply_paused,assigned_to,current_rich_menu_id,rich_menu_name,tags,note,unread",
        "line_user_id": f"eq.{uid}", "limit": "1"})
    if not urows:
        raise HTTPException(404, "ไม่พบผู้ใช้")
    params = {"select": "*", "line_user_id": f"eq.{uid}",
              "order": "created_at.desc", "limit": str(min(limit, 100))}
    if before:
        params["created_at"] = f"lt.{before}"
    msgs = await supa.select("messages", params=params)
    msgs.reverse()
    return {"user": urows[0], "messages": msgs}


@app.post("/api/inbox/{uid}/read")
async def inbox_read(uid: str, admin=Depends(current_admin)):
    await supa.update("line_users", {"unread": 0}, {"line_user_id": f"eq.{uid}"})
    return {"ok": True}


@app.post("/api/inbox/{uid}/pause")
async def inbox_pause(uid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    paused = bool(b.get("paused", True))
    await supa.update("line_users", {
        "auto_reply_paused": paused,
        "assigned_to": admin["userId"] if paused else None,
    }, {"line_user_id": f"eq.{uid}"})
    await supa.insert("messages", {
        "line_user_id": uid, "direction": "out", "by": "system", "msg_type": "note",
        "text": f"— {'ปิด' if paused else 'เปิด'}ตอบอัตโนมัติ โดย {admin['name'] or admin['userId'][:8]} —",
    })
    return {"ok": True, "paused": paused}


@app.post("/api/inbox/{uid}/assign")
async def inbox_assign(uid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    await supa.update("line_users", {"assigned_to": b.get("to") or None}, {"line_user_id": f"eq.{uid}"})
    return {"ok": True}


@app.post("/api/inbox/{uid}/send")
async def inbox_send(uid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    msgs = _normalize_messages(b.get("messages", []))
    code, txt, rid = await line.push(uid, msgs)
    if code != 200:
        raise HTTPException(400, txt)
    rows = [{"line_user_id": uid, "direction": "out", "by": admin["userId"],
             "msg_type": m.get("type"), "text": m.get("text"), "payload": m} for m in msgs]
    await supa.insert("messages", rows)
    await supa.update("line_users", {
        "unread": 0, "last_message_at": NOW(),
        "last_message_text": (msgs[-1].get("text") or f"[{msgs[-1].get('type')}]")[:200],
    }, {"line_user_id": f"eq.{uid}"})
    return {"ok": True, "requestId": rid}


@app.get("/api/users/{uid}")
async def user_detail(uid: str, admin=Depends(current_admin)):
    rows = await supa.select("line_users", params={"line_user_id": f"eq.{uid}", "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบผู้ใช้")
    user = rows[0]
    events = await supa.select("webhook_events", params={
        "line_user_id": f"eq.{uid}", "select": "event_type,message_type,text,postback_data,created_at",
        "order": "created_at.desc", "limit": "20",
    })
    follows = await supa.select("follow_history", params={
        "line_user_id": f"eq.{uid}", "select": "action,is_unblocked,event_ts",
        "order": "created_at.desc", "limit": "20",
    })
    # ดึงสด LINE profile + rich menu ปัจจุบัน
    live = {}
    try:
        p = await line.get_profile(uid)
        if p:
            live["profile"] = p
        rid = await line.user_richmenu_get(uid)
        live["richMenuId"] = rid
    except Exception as e:
        live["error"] = str(e)
    return {"user": user, "events": events, "follow_history": follows, "live": live}


@app.patch("/api/users/{uid}")
async def update_user(uid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    patch = {k: b[k] for k in ("note", "tags") if k in b}
    if "custom" in b:
        cur = await supa.select("line_users", params={"select": "custom", "line_user_id": f"eq.{uid}", "limit": "1"})
        merged = {**((cur[0].get("custom") if cur else {}) or {}), **b["custom"]}
        patch["custom"] = {k: v for k, v in merged.items() if v not in (None, "")}
    patch["updated_at"] = NOW()
    await supa.update("line_users", patch, {"line_user_id": f"eq.{uid}"})
    return {"ok": True}


@app.post("/api/users/import-mapped")
async def users_import_mapped(req: Request, admin=Depends(current_admin)):
    """นำเข้าจาก CSV ที่ map คอลัมน์แล้ว
    rows: [{userId, displayName?, tags?, note?, custom: {...}}]  """
    b = await req.json()
    rows = b.get("rows", [])
    ts = NOW()
    valid, patch = 0, []
    for r in rows:
        uid = str(r.get("userId", "")).strip()
        if not re.fullmatch(r"U[0-9a-f]{32}", uid):
            continue
        valid += 1
        row = {"line_user_id": uid, "source": "import", "updated_at": ts}
        if r.get("displayName"):
            row["display_name"] = _clean_str(r["displayName"])
        if r.get("note"):
            row["note"] = r["note"]
        if r.get("tags"):
            row["tags"] = r["tags"] if isinstance(r["tags"], list) else [t.strip() for t in str(r["tags"]).replace("|", ",").split(",") if t.strip()]
        if r.get("custom"):
            row["custom"] = {k: v for k, v in r["custom"].items() if v not in (None, "")}
        patch.append(row)
    for i in range(0, len(patch), 400):
        await supa.upsert("line_users", patch[i:i + 400], on_conflict="line_user_id")
    await supa.log_operation(admin["userId"], "users.import_mapped",
                             {"submitted": len(rows)}, {"valid": valid})
    return {"ok": True, "submitted": len(rows), "valid": valid}


# ============================================================
# MESSAGING
# ============================================================
def _normalize_messages(raw):
    """รับ string / list[str] / list[obj] -> list[LINE message obj] (max 5)"""
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for m in raw[:5]:
        out.append({"type": "text", "text": m} if isinstance(m, str) else m)
    return out


@app.post("/api/message/recipients-preview")
async def recipients_preview(req: Request, admin=Depends(current_admin)):
    """นับปลายทาง + ตัวอย่าง 12 คน (รูป+ชื่อ) ก่อนกดส่งจริง"""
    b = await req.json()
    if b.get("mode") == "broadcast":
        cnt = await supa.count("line_users", {"is_following": "eq.true"})
        sample = await supa.select("line_users", params={
            "select": "line_user_id,display_name,picture_url", "is_following": "eq.true",
            "order": "updated_at.desc", "limit": "12",
        })
        return {"count": cnt, "sample": sample, "exact": True}

    if b.get("segmentId"):
        seg = await supa.select("segments", params={"id": f"eq.{b['segmentId']}", "select": "filter", "limit": "1"})
        f = seg[0]["filter"] if seg else {}
    elif b.get("filter"):
        f = b["filter"]
    elif b.get("mode") == "push":
        uids = [u.strip() for u in (b.get("to") or "").replace("\n", ",").split(",") if u.strip()]
        sample = await supa.select("line_users", params={
            "select": "line_user_id,display_name,picture_url",
            "line_user_id": f"in.({','.join(uids[:12])})", "limit": "12",
        }) if uids else []
        return {"count": len(uids), "sample": sample, "exact": True}
    else:
        f = {"tag": b.get("tag"), "menu": b.get("menu")}

    params = _filter_to_params(f)
    uids = await _uids_by_filter(f)
    sample_ids = uids[:12]
    sample = await supa.select("line_users", params={
        "select": "line_user_id,display_name,picture_url",
        "line_user_id": f"in.({','.join(sample_ids)})", "limit": "12",
    }) if sample_ids else []
    return {"count": len(uids), "sample": sample, "exact": True}


# ---------- message templates ----------
@app.get("/api/message-templates")
async def list_msg_templates(admin=Depends(current_admin)):
    return {"templates": await supa.select("message_templates", params={
        "select": "*", "order": "updated_at.desc",
    })}


@app.post("/api/message-templates")
async def save_msg_template(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    row = {"name": b["name"], "messages": _normalize_messages(b.get("messages", [])),
           "created_by": admin["userId"], "updated_at": NOW()}
    if b.get("id"):
        await supa.update("message_templates", row, {"id": f"eq.{b['id']}"})
        return {"ok": True, "id": b["id"]}
    r = await supa.insert("message_templates", row)
    return {"ok": True, "template": r[0] if r else None}


@app.delete("/api/message-templates/{tid}")
async def del_msg_template(tid: int, admin=Depends(current_admin)):
    await supa.delete("message_templates", {"id": f"eq.{tid}"})
    return {"ok": True}


@app.get("/api/broadcasts/{bid}")
async def get_broadcast(bid: int, admin=Depends(current_admin)):
    rows = await supa.select("broadcasts", params={"id": f"eq.{bid}", "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบ")
    return rows[0]


@app.post("/api/message/validate")
async def msg_validate(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    ok, txt = await line.validate_messages(_normalize_messages(b.get("messages", [])))
    return {"ok": ok, "detail": txt}


@app.post("/api/message/test")
async def msg_test(req: Request, admin=Depends(current_admin)):
    """ส่งข้อความหาตัวเอง (ผู้ที่ล็อกอินอยู่) เพื่อทดสอบก่อนส่งจริง"""
    b = await req.json()
    msgs = _normalize_messages(b.get("messages", []))
    code, txt, rid = await line.push(admin["userId"], msgs)
    if code != 200:
        raise HTTPException(400, txt)
    return {"ok": True, "requestId": rid, "to": admin["userId"]}


@app.post("/api/message/push")
async def msg_push(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    to = b.get("to")
    nd = bool(b.get("notificationDisabled"))
    msgs = _normalize_messages(b.get("messages", []))
    if isinstance(to, list):
        if len(to) == 1:
            code, txt, rid = await line.push(to[0], msgs, nd)
            kind, cnt = "push", 1
        else:
            code, txt, rid = await line.multicast(to, msgs, nd)
            kind, cnt = "multicast", len(to)
    else:
        code, txt, rid = await line.push(to, msgs, nd)
        kind, cnt = "push", 1
    status = "sent" if code == 200 else "failed"
    await supa.insert("broadcasts", {
        "actor": admin["userId"], "kind": kind, "target_count": cnt,
        "messages": msgs, "line_request_id": rid, "status": status,
        "error": None if status == "sent" else txt[:300],
    })
    if code != 200:
        raise HTTPException(400, txt)
    return {"ok": True, "requestId": rid, "sent": cnt}


@app.post("/api/message/bulk")
async def msg_bulk(req: Request, admin=Depends(current_admin)):
    """ส่งหา userId จำนวนมากพร้อมกัน — แบ่ง batch ละ 500 ยิง multicast ขนานกัน
    body: { userIds: [...] | "…\\n…", messages, notificationDisabled }"""
    b = await req.json()
    raw = b.get("userIds", [])
    if isinstance(raw, str):
        raw = re.split(r"[\s,]+", raw)

    seen, uids, invalid = set(), [], []
    for u in raw:
        u = str(u).strip()
        if not u:
            continue
        if re.fullmatch(r"U[0-9a-f]{32}", u):
            if u not in seen:
                seen.add(u)
                uids.append(u)
        else:
            invalid.append(u)
    if not uids:
        raise HTTPException(400, "ไม่มี userId ที่ถูกต้อง (ต้องเป็น U + 32 hex)")

    msgs = _normalize_messages(b.get("messages", []))
    nd = bool(b.get("notificationDisabled"))
    chunks = [uids[i:i + 500] for i in range(0, len(uids), 500)]

    sem = asyncio.Semaphore(5)
    res = {"total": len(uids), "sent": 0, "failed": 0, "batches": len(chunks),
           "ok_batches": 0, "errors": [], "duplicate": len(raw) - len(uids) - len(invalid),
           "invalid": invalid[:30], "invalid_count": len(invalid)}
    last_rid = [None]

    async def one(idx, ch):
        async with sem:
            code, txt, rid = await line.multicast(ch, msgs, nd)
            if rid:
                last_rid[0] = rid
            if code == 200:
                res["sent"] += len(ch)
                res["ok_batches"] += 1
            else:
                res["failed"] += len(ch)
                if len(res["errors"]) < 20:
                    res["errors"].append({"batch": idx, "n": len(ch), "code": code, "msg": txt[:150]})

    await asyncio.gather(*[one(i, c) for i, c in enumerate(chunks)])

    status = "sent" if res["failed"] == 0 else ("partial" if res["sent"] else "failed")
    await supa.insert("broadcasts", {
        "actor": admin["userId"], "kind": "multicast", "target_count": len(uids),
        "messages": msgs, "line_request_id": last_rid[0],
        "status": "sent" if status == "sent" else "failed",
        "error": None if status == "sent" else f"{res['failed']} ล้มเหลว",
    })
    await supa.log_operation(admin["userId"], "message.bulk",
                             {"total": len(uids), "batches": len(chunks)}, res, status)
    return res


@app.post("/api/message/broadcast")
async def msg_broadcast(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    msgs = _normalize_messages(b.get("messages", []))
    code, txt, rid = await line.broadcast(msgs)
    status = "sent" if code == 200 else "failed"
    following = await supa.count("line_users", {"is_following": "eq.true"})
    await supa.insert("broadcasts", {
        "actor": admin["userId"], "kind": "broadcast", "target_count": following,
        "messages": msgs, "line_request_id": rid, "status": status,
        "error": None if status == "sent" else txt[:300],
    })
    if code != 200:
        raise HTTPException(400, txt)
    return {"ok": True, "requestId": rid}


@app.post("/api/message/multicast-from-db")
async def msg_multicast_db(req: Request, admin=Depends(current_admin)):
    """ส่งหา user ใน DB ตาม filter / segmentId / tag+menu"""
    b = await req.json()
    if b.get("segmentId"):
        seg = await supa.select("segments", params={"id": f"eq.{b['segmentId']}", "select": "filter", "limit": "1"})
        f = seg[0]["filter"] if seg else {}
    elif b.get("filter"):
        f = b["filter"]
    else:
        f = {"tag": b.get("tag"), "menu": b.get("menu")}
    uids = await _uids_by_filter(f)
    if not uids:
        raise HTTPException(400, "ไม่มีปลายทาง")
    msgs = _normalize_messages(b.get("messages", []))
    last_rid, sent, failed = None, 0, 0
    for i in range(0, len(uids), 500):
        code, txt, rid = await line.multicast(uids[i:i + 500], msgs)
        last_rid = rid
        if code == 200:
            sent += len(uids[i:i + 500])
        else:
            failed += len(uids[i:i + 500])
    await supa.insert("broadcasts", {
        "actor": admin["userId"], "kind": "multicast", "target_count": len(uids),
        "messages": msgs, "line_request_id": last_rid,
        "status": "sent" if failed == 0 else "failed",
    })
    return {"ok": failed == 0, "target": len(uids), "sent": sent, "failed": failed}


@app.get("/api/broadcasts")
async def list_broadcasts(admin=Depends(current_admin), limit: int = 50):
    return {"broadcasts": await supa.select("broadcasts", params={
        "select": "*", "order": "created_at.desc", "limit": str(limit),
    })}


# ============================================================
# STATS
# ============================================================
@app.get("/api/stats/quota")
async def stats_quota(admin=Depends(current_admin)):
    return await line.message_quota()


@app.get("/api/stats/insight")
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


@app.get("/api/stats/funnel")
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


@app.get("/api/stats/history")
async def stats_history(admin=Depends(current_admin), days: int = 30):
    return {"days": await supa.select("stats_daily", params={
        "select": "*", "order": "day.desc", "limit": str(days),
    })}


@app.get("/api/stats/follows")
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


# ============================================================
# EVENTS / LOGS
# ============================================================
@app.get("/api/events")
async def events(admin=Depends(current_admin), limit: int = 100, type: str = "", uid: str = ""):
    params = {"select": "id,event_type,line_user_id,message_type,text,reply_token,postback_data,auto_replied,created_at",
              "order": "created_at.desc", "limit": str(min(limit, 500))}
    if type:
        params["event_type"] = f"eq.{type}"
    if uid:
        params["line_user_id"] = f"eq.{uid}"
    return {"events": await supa.select("webhook_events", params=params)}


@app.post("/api/events/{eid}/reply")
async def reply_to_event(eid: int, req: Request, admin=Depends(current_admin)):
    """ตอบกลับด้วย replyToken ของ event นั้น (ใช้ได้ ~1 นาทีหลัง event เข้ามา)"""
    b = await req.json()
    rows = await supa.select("webhook_events", params={
        "id": f"eq.{eid}", "select": "reply_token,line_user_id,created_at", "limit": "1"})
    if not rows or not rows[0].get("reply_token"):
        raise HTTPException(400, "event นี้ไม่มี reply token")
    ev = rows[0]
    age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ev["created_at"])).total_seconds()
    msgs = _normalize_messages(b.get("messages", []))
    code, txt = await line.reply(ev["reply_token"], msgs)
    if code != 200:
        # reply token หมดอายุ -> fallback เป็น push
        if ev.get("line_user_id"):
            pc, ptxt, prid = await line.push(ev["line_user_id"], msgs)
            if pc == 200:
                await supa.update("webhook_events", {"auto_replied": True}, {"id": f"eq.{eid}"})
                return {"ok": True, "via": "push", "note": f"reply token ใช้ไม่ได้ (อายุ {int(age)}s) เลยส่ง push แทน"}
        raise HTTPException(400, f"reply ไม่สำเร็จ: {txt[:150]}")
    await supa.update("webhook_events", {"auto_replied": True}, {"id": f"eq.{eid}"})
    return {"ok": True, "via": "reply"}


@app.get("/api/operations")
async def operations(admin=Depends(current_admin), limit: int = 100):
    return {"operations": await supa.select("operations", params={
        "select": "*", "order": "created_at.desc", "limit": str(min(limit, 500)),
    })}


# ============================================================
# AUTO-REPLY (keyword responder)
# ============================================================
@app.get("/api/auto-replies")
async def list_auto_replies(admin=Depends(current_admin)):
    return {"rules": await supa.select("auto_replies", params={
        "select": "*", "order": "priority.desc,id.asc",
    })}


@app.post("/api/auto-replies")
async def create_auto_reply(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    row = {
        "name": b.get("name"),
        "enabled": b.get("enabled", True),
        "trigger": b.get("trigger", "text"),
        "match_type": b.get("match_type", "contains"),
        "keywords": b.get("keywords", []),
        "messages": _normalize_messages(b.get("messages", [])),
        "priority": int(b.get("priority", 0)),
        "created_by": admin["userId"],
    }
    if b.get("id"):
        await supa.update("auto_replies", row, {"id": f"eq.{b['id']}"})
        return {"ok": True, "id": b["id"]}
    r = await supa.insert("auto_replies", row)
    return {"ok": True, "rule": r[0] if r else None}


@app.delete("/api/auto-replies/{rid}")
async def delete_auto_reply(rid: int, admin=Depends(current_admin)):
    await supa.delete("auto_replies", {"id": f"eq.{rid}"})
    return {"ok": True}


# ============================================================
# CRON: snapshot สถิติรายวัน + รัน scheduled jobs
# ============================================================
def _check_cron_key(request: Request):
    ip = request.headers.get("x-forwarded-for", "?").split(",")[0].strip()
    _rate_limit(f"cron:{ip}", limit=30, window=60)
    if CRON_SECRET:
        key = request.query_params.get("key") or request.headers.get("x-cron-key", "")
        if key != CRON_SECRET:
            raise HTTPException(403, "bad cron key")


BACKUP_TABLES = ("admins", "line_users", "auto_replies", "segments",
                 "message_templates", "rich_menus", "scheduled_jobs")


async def _make_backup():
    day = dt.date.today().isoformat()
    dump = {}
    for tb in BACKUP_TABLES:
        try:
            dump[tb] = await supa.select_all(tb, params={"select": "*"})
        except Exception as e:
            dump[tb] = {"error": str(e)}
    size_kb = len(json.dumps(dump)) // 1024
    await supa.upsert("backups", {"day": day, "tables": dump, "size_kb": size_kb},
                      on_conflict="day")
    # เก็บ 21 วันล่าสุด
    old = await supa.select("backups", params={"select": "id", "order": "day.desc", "limit": "50"})
    for r in old[21:]:
        await supa.delete("backups", {"id": f"eq.{r['id']}"})
    return {"day": day, "size_kb": size_kb, "rows": {k: (len(v) if isinstance(v, list) else 0) for k, v in dump.items()}}


@app.api_route("/api/cron/backup", methods=["GET", "POST"])
async def cron_backup(request: Request):
    _check_cron_key(request)
    try:
        res = await _make_backup()
        await supa.log_operation("cron", "backup", None, res)
        return {"ok": True, **res}
    except Exception as e:
        await alert_admin("Backup ล้มเหลว", str(e), "backup")
        raise HTTPException(500, str(e))


@app.post("/api/backup/now")
async def backup_now(admin=Depends(current_admin)):
    res = await _make_backup()
    await supa.log_operation(admin["userId"], "backup.manual", None, res)
    return {"ok": True, **res}


@app.get("/api/backup/list")
async def backup_list(admin=Depends(current_admin)):
    return {"backups": await supa.select("backups", params={
        "select": "id,day,size_kb,created_at", "order": "day.desc", "limit": "30"})}


@app.get("/api/backup/{bid}")
async def backup_get(bid: int, admin=Depends(current_admin)):
    rows = await supa.select("backups", params={"id": f"eq.{bid}", "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบ")
    return rows[0]


@app.api_route("/api/cron/snapshot-stats", methods=["GET", "POST"])
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


@app.api_route("/api/cron/run-automations", methods=["GET", "POST"])
async def cron_run_automations(request: Request):
    _check_cron_key(request)
    due = await supa.select("automation_runs", params={
        "select": "*", "status": "eq.pending", "run_at": f"lte.{NOW()}",
        "order": "run_at.asc", "limit": "200"})
    if not due:
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


@app.get("/api/automations")
async def list_automations(admin=Depends(current_admin)):
    return {"automations": await supa.select("automations", params={"select": "*", "order": "id.desc"})}


@app.post("/api/automations")
async def save_automation(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    steps = []
    for s in b.get("steps", []):
        steps.append({
            "delayHours": int(s.get("delayHours", 0)),
            "delayMinutes": int(s.get("delayMinutes", 0)),
            "messages": _normalize_messages(s.get("messages", [])),
        })
    row = {"name": b["name"], "enabled": b.get("enabled", True),
           "trigger": b.get("trigger", "follow"), "trigger_config": b.get("triggerConfig", {}),
           "steps": steps, "created_by": admin["userId"]}
    if b.get("id"):
        await supa.update("automations", row, {"id": f"eq.{b['id']}"})
        return {"ok": True, "id": b["id"]}
    r = await supa.insert("automations", row)
    return {"ok": True, "automation": r[0] if r else None}


@app.delete("/api/automations/{aid}")
async def del_automation(aid: int, admin=Depends(current_admin)):
    await supa.delete("automations", {"id": f"eq.{aid}"})
    await supa.delete("automation_runs", {"automation_id": f"eq.{aid}", "status": "eq.pending"})
    return {"ok": True}


@app.api_route("/api/cron/run-scheduled", methods=["GET", "POST"])
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
                code, txt, rid = await line.broadcast(_normalize_messages(p.get("messages", [])))
                ok = code == 200
                await supa.insert("broadcasts", {
                    "actor": job.get("created_by"), "kind": "broadcast",
                    "messages": p.get("messages"), "line_request_id": rid,
                    "status": "sent" if ok else "failed",
                })
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


@app.get("/api/scheduled")
async def list_scheduled(admin=Depends(current_admin)):
    return {"jobs": await supa.select("scheduled_jobs", params={
        "select": "*", "order": "run_at.desc", "limit": "50",
    })}


@app.post("/api/scheduled")
async def create_scheduled(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    kind = b.get("kind", "broadcast")
    payload = {}
    if kind == "broadcast":
        payload = {"messages": _normalize_messages(b.get("messages", []))}
    elif kind == "richmenu_default":
        payload = {"richMenuId": b["richMenuId"]}
    r = await supa.insert("scheduled_jobs", {
        "kind": kind, "run_at": b["runAt"], "payload": payload,
        "repeat": b.get("repeat"), "label": b.get("label"),
        "created_by": admin["userId"],
    })
    return {"ok": True, "job": r[0] if r else None}


@app.delete("/api/scheduled/{jid}")
async def cancel_scheduled(jid: int, admin=Depends(current_admin)):
    await supa.update("scheduled_jobs", {"status": "cancelled"}, {"id": f"eq.{jid}", "status": "eq.pending"})
    return {"ok": True}


# ============================================================
# SEGMENTS (บันทึก filter เป็นกลุ่ม)
# ============================================================
def _filter_to_params(f: dict) -> dict:
    p = {"select": "line_user_id"}
    following = f.get("following")
    if following in ("true", "false", True, False):
        p["is_following"] = f"eq.{str(following).lower()}"
    else:
        p["is_following"] = "eq.true"
    if f.get("menu") == "none" or f.get("noMenu"):
        p["current_rich_menu_id"] = "is.null"
    elif f.get("menu"):
        p["current_rich_menu_id"] = f"eq.{f['menu']}"
    if f.get("source"):
        p["source"] = f"eq.{f['source']}"
    tags = f.get("tags") or ([f["tag"]] if f.get("tag") else [])
    if tags:
        p["tags"] = "cs.{" + ",".join(tags) + "}"
    if f.get("search"):
        s = f["search"]
        p["or"] = f"(line_user_id.ilike.*{s}*,display_name.ilike.*{s}*,note.ilike.*{s}*)"
    return p


async def _uids_by_filter(f: dict) -> list[str]:
    rows = await supa.select_all("line_users", params=_filter_to_params(f))
    return [r["line_user_id"] for r in rows]


_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp",
        "video/mp4": "mp4", "audio/mp4": "m4a", "audio/x-m4a": "m4a"}


@app.post("/api/upload")
async def upload_media(req: Request, admin=Depends(current_admin)):
    """รับ base64 (dataURL) -> เก็บ Supabase Storage -> คืน public URL"""
    b = await req.json()
    data = b.get("dataUrl") or b.get("base64") or ""
    ctype = "image/png"
    if data.startswith("data:"):
        head, data = data.split(",", 1)
        ctype = head[5:].split(";")[0] or ctype
    if ctype not in _EXT:
        raise HTTPException(400, f"ไม่รองรับไฟล์ชนิด {ctype}")
    raw = base64.b64decode(data)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(400, "ไฟล์ใหญ่เกิน 10MB")
    name = f"{dt.date.today().isoformat()}/{int(time.time()*1000)}-{os.urandom(3).hex()}.{_EXT[ctype]}"
    url = await supa.storage_upload("media", name, raw, ctype)
    await supa.log_operation(admin["userId"], "upload", {"type": ctype, "kb": len(raw) // 1024}, {"url": url})
    return {"ok": True, "url": url, "path": name, "size": len(raw)}


@app.get("/api/media")
async def list_media(admin=Depends(current_admin)):
    try:
        items = await supa.storage_list("media")
    except Exception:
        return {"items": []}
    base = f"{SUPABASE_URL}/storage/v1/object/public/media/"
    out = []
    for it in items:
        if it.get("name") and not it["name"].endswith("/"):
            out.append({"name": it["name"], "url": base + it["name"],
                        "size": (it.get("metadata") or {}).get("size"),
                        "created": it.get("created_at")})
    return {"items": out}


# ============================================================
# LIFF
# ============================================================
def _liff_meta(liff_id: str) -> dict:
    """ข้อมูลที่คำนวณได้จาก LIFF ID เอง"""
    channel = liff_id.split("-")[0] if "-" in liff_id else ""
    return {
        "liffId": liff_id,
        "channelId": channel,
        "permanentLink": f"https://liff.line.me/{liff_id}",
        "shortLink": f"line://app/{liff_id}",
        "consoleUrl": f"https://developers.line.biz/console/channel/{channel}/liff" if channel else None,
    }


@app.get("/api/liff")
async def liff_list(admin=Depends(current_admin)):
    stored = await supa.select("liff_apps", params={"select": "*", "order": "is_primary.desc,updated_at.desc"})
    # sync จาก LINE ถ้ามี token
    line_apps, sync_err = [], None
    if LINE_LOGIN_CHANNEL_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get("https://api.line.me/liff/v1/apps",
                                headers={"Authorization": f"Bearer {LINE_LOGIN_CHANNEL_TOKEN}"})
            if r.status_code == 200:
                line_apps = r.json().get("apps", [])
            else:
                sync_err = f"{r.status_code}: {r.text[:150]}"
        except Exception as e:
            sync_err = str(e)

    stored_ids = {s["liff_id"] for s in stored}
    merged = []
    for s in stored:
        m = {**_liff_meta(s["liff_id"]), **s, "source": "stored"}
        la = next((a for a in line_apps if a["liffId"] == s["liff_id"]), None)
        if la:
            m["line"] = la
        merged.append(m)
    for a in line_apps:
        if a["liffId"] not in stored_ids:
            merged.append({**_liff_meta(a["liffId"]), "name": a.get("description"),
                           "line": a, "source": "line"})

    env_liff = os.environ.get("VITE_LIFF_ID") or (LIFF_CHANNEL_ID and "")
    return {
        "apps": merged,
        "env": {
            "VITE_LIFF_ID": os.environ.get("VITE_LIFF_ID"),
            "LIFF_CHANNEL_ID": LIFF_CHANNEL_ID,
            "recommendedEndpoint": APP_URL,
        },
        "syncEnabled": bool(LINE_LOGIN_CHANNEL_TOKEN),
        "syncError": sync_err,
    }


@app.post("/api/liff")
async def liff_save(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    lid = (b.get("liffId") or "").strip()
    if not re.fullmatch(r"\d{9,12}-[0-9a-zA-Z]{6,12}", lid):
        raise HTTPException(400, "LIFF ID ผิดรูปแบบ (เช่น 2009830584-koG1QjOD)")
    row = {
        "liff_id": lid,
        "name": b.get("name"),
        "size": b.get("size"),
        "endpoint_url": b.get("endpointUrl"),
        "description": b.get("description"),
        "scopes": b.get("scopes", []),
        "bot_prompt": b.get("botPrompt"),
        "features": b.get("features", {}),
        "module_mode": bool(b.get("moduleMode")),
        "is_primary": bool(b.get("isPrimary")),
        "channel_id": lid.split("-")[0],
        "note": b.get("note"),
        "created_by": admin["userId"],
        "updated_at": NOW(),
    }
    if b.get("isPrimary"):
        await supa.update("liff_apps", {"is_primary": False}, {"is_primary": "eq.true"})
    await supa.upsert("liff_apps", row, on_conflict="liff_id")
    return {"ok": True, **_liff_meta(lid)}


@app.delete("/api/liff/{liff_id}")
async def liff_delete(liff_id: str, admin=Depends(current_admin)):
    await supa.delete("liff_apps", {"liff_id": f"eq.{liff_id}"})
    return {"ok": True}


@app.post("/api/target/resolve")
async def resolve_target(req: Request, admin=Depends(current_admin)):
    """คืน userId list ตาม target (all/none/tag/segment/filter) — ให้ frontend เอาไป chunk + แสดง %"""
    b = await req.json()
    tg = b.get("target", "all")
    if tg == "segment":
        seg = await supa.select("segments", params={"id": f"eq.{b.get('segmentId')}", "select": "filter", "limit": "1"})
        uids = await _uids_by_filter(seg[0]["filter"] if seg else {})
    elif tg == "filter":
        uids = await _uids_by_filter(b.get("filter", {}))
    elif tg == "none":
        uids = await _uids_by_filter({"noMenu": True})
    elif tg == "tag":
        uids = await _uids_by_filter({"tag": b.get("tag", "")})
    elif tg == "list":
        uids = [u.strip() for u in b.get("userIds", []) if u.strip()]
    else:
        uids = await _uids_by_filter({})
    return {"count": len(uids), "userIds": uids}


@app.get("/api/segments")
async def list_segments(admin=Depends(current_admin)):
    return {"segments": await supa.select("segments", params={"select": "*", "order": "updated_at.desc"})}


@app.post("/api/segments")
async def save_segment(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    cnt = len(await _uids_by_filter(b.get("filter", {})))
    row = {"name": b["name"], "description": b.get("description"),
           "filter": b.get("filter", {}), "last_count": cnt,
           "created_by": admin["userId"], "updated_at": NOW()}
    if b.get("id"):
        await supa.update("segments", row, {"id": f"eq.{b['id']}"})
        return {"ok": True, "id": b["id"], "count": cnt}
    r = await supa.insert("segments", row)
    return {"ok": True, "segment": r[0] if r else None, "count": cnt}


@app.get("/api/segments/{sid}/count")
async def segment_count(sid: int, admin=Depends(current_admin)):
    rows = await supa.select("segments", params={"id": f"eq.{sid}", "select": "filter", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบ segment")
    uids = await _uids_by_filter(rows[0]["filter"])
    await supa.update("segments", {"last_count": len(uids)}, {"id": f"eq.{sid}"})
    return {"count": len(uids)}


@app.delete("/api/segments/{sid}")
async def delete_segment(sid: int, admin=Depends(current_admin)):
    await supa.delete("segments", {"id": f"eq.{sid}"})
    return {"ok": True}


# ============================================================
# NARROWCAST (ส่งตาม demographic ของ LINE)
# ============================================================
@app.post("/api/message/narrowcast")
async def msg_narrowcast(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    msgs = _normalize_messages(b.get("messages", []))
    demo = b.get("demographic")   # LINE filter object (age/gender/area/...)
    recipient = b.get("recipient")  # audience / redelivery object
    limit = b.get("limit")
    filter_ = {"demographic": demo} if demo else None
    code, txt, rid = await line.narrowcast(msgs, recipient=recipient, filter_=filter_, limit=limit)
    status = "sent" if code in (200, 202) else "failed"
    await supa.insert("broadcasts", {
        "actor": admin["userId"], "kind": "narrowcast", "target_count": None,
        "messages": msgs, "line_request_id": rid, "status": status,
        "error": None if status == "sent" else txt[:300],
    })
    if code not in (200, 202):
        raise HTTPException(400, txt)
    return {"ok": True, "requestId": rid}


@app.get("/api/message/narrowcast/progress")
async def narrowcast_progress(admin=Depends(current_admin), requestId: str = ""):
    r = await line._req("GET", "/v2/bot/message/progress/narrowcast", params={"requestId": requestId})
    return r.json()


@app.get("/api/admins")
async def list_admins(admin=Depends(current_admin)):
    return {"admins": await supa.select("admins", params={"select": "*", "order": "added_at"})}


@app.post("/api/admins")
async def add_admin(req: Request, admin=Depends(current_admin)):
    if admin.get("role") not in ("owner", "admin"):
        raise HTTPException(403, "ต้องเป็น owner/admin")
    b = await req.json()
    await supa.upsert("admins", {
        "line_user_id": b["lineUserId"], "name": b.get("name"), "role": b.get("role", "admin"),
    }, on_conflict="line_user_id")
    return {"ok": True}


@app.delete("/api/admins/{uid}")
async def del_admin(uid: str, admin=Depends(current_admin)):
    if admin.get("role") != "owner":
        raise HTTPException(403, "ต้องเป็น owner")
    await supa.delete("admins", {"line_user_id": f"eq.{uid}"})
    return {"ok": True}

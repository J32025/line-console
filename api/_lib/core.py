"""โค้ดกลางที่ใช้ร่วมกัน (helper / webhook handler / state) — แยกจาก api/index.py
routes อยู่ใน _lib/routers/*.py"""
from _lib import line
from _lib import supa
from _lib.auth import current_admin
from _lib.config import ALERT_USER_IDS
from _lib.config import ANTHROPIC_API_KEY
from _lib.config import ANTHROPIC_MODEL
from _lib.config import APP_URL
from _lib.config import CRON_SECRET
from _lib.config import EASYSLIP_TOKEN
from _lib.config import GEMINI_API_KEY
from _lib.config import GEMINI_MODEL
from _lib.config import GEMINI_TRIGGER_MENU_NAME
from _lib.config import LIFF_CHANNEL_ID
from _lib.config import LINE_CHANNEL_ACCESS_TOKEN
from _lib.config import LINE_CHANNEL_SECRET
from _lib.config import LINE_LOGIN_ASSERTION_KID
from _lib.config import LINE_LOGIN_ASSERTION_PRIVATE_KEY
from _lib.config import LINE_LOGIN_CHANNEL_ID
from _lib.config import LINE_LOGIN_CHANNEL_SECRET
from _lib.config import LINE_LOGIN_CHANNEL_TOKEN
from _lib.config import REG_LIFF_CHANNEL_ID
from _lib.config import SLIP_SUCCESS_RICHMENU_ID
from _lib.config import SUPABASE_SERVICE_ROLE_KEY
from _lib.config import SUPABASE_URL
from _lib.registrations import _REG_PRICES_DEFAULT, _course_base, _norm_course, _reconcile_data  # noqa: F401  (ย้ายไป registrations.py)
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
import anthropic
import asyncio
import base64
import copy
import datetime as dt
import gzip
import hashlib
import hmac
import httpx
import json
import os
import re
import time


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


def _rate_ok(key: str, limit: int, window: float) -> bool:
    """เหมือน _rate_limit แต่คืน False แทนการ raise — ใช้ในลูปที่ไม่อยากให้ 1 คนล้มทั้ง batch"""
    now = time.time()
    q = _hits.setdefault(key, [])
    while q and q[0] < now - window:
        q.pop(0)
    if len(q) >= limit:
        return False
    q.append(now)
    return True


# ---- rate limit แบบใช้ได้จริง: นับใน Postgres (migration 0019) ใช้ร่วมกันทุก instance ----
# fail-open: ตาราง/function ยังไม่มี หรือ DB ช้า -> ถอยไปใช้ตัวนับในหน่วยความจำข้างบน แล้วพัก DB 5 นาที
# (คำขอจริงต้องไม่ล่มเพราะระบบกันสแปมเอง)
_rl_db_down_until = 0.0


def _client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "?").split(",")[0].strip() or "?"


async def _json_obj(req: Request) -> dict:
    """อ่าน body ของ endpoint สาธารณะ — ไม่ใช่ JSON object (เช่น ตัวเลข/ลิสต์/ขยะ) ให้ 400 แทนที่จะ 500"""
    try:
        b = await req.json()
    except Exception:
        raise HTTPException(400, "ข้อมูลที่ส่งมาไม่ใช่ JSON")
    if not isinstance(b, dict):
        raise HTTPException(400, "ข้อมูลที่ส่งมาต้องเป็น JSON object")
    return b


async def _rl_db(key: str, limit: int, window: int):
    """True = ยังไม่เกิน, False = เกิน, None = ใช้ DB ไม่ได้"""
    global _rl_db_down_until
    if time.time() < _rl_db_down_until:
        return None
    try:
        return bool(await supa.rpc("rate_limit_hit", {
            "p_key": key, "p_window_seconds": int(window), "p_limit": int(limit)}))
    except Exception as e:
        _rl_db_down_until = time.time() + 300
        print("rate limit db unavailable, falling back to in-memory for 5min:", str(e)[:150])
        return None


async def _rate_limit_db(key: str, limit: int, window: int):
    ok = await _rl_db(key, limit, window)
    if ok is None:
        _rate_limit(key, limit, window)
    elif not ok:
        raise HTTPException(429, "เรียกถี่เกินไป ลองใหม่อีกครั้ง")


async def _rate_ok_db(key: str, limit: int, window: int) -> bool:
    ok = await _rl_db(key, limit, window)
    return _rate_ok(key, limit, window) if ok is None else ok


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


async def _deep_health_allowed(request: Request) -> bool:
    """deep=1 เรียก LINE/EasySlip/Gemini/DB จริงหลายตัว (2-3 วินาที/ครั้ง) — ห้ามเปิดสาธารณะ ใครยิงรัวก็เผาโควต้าได้
    อนุญาตเฉพาะ: ?key=CRON_SECRET (หรือ header x-cron-key) หรือแอดมินที่ login แล้ว (หน้า ผู้ดูแล ส่ง Bearer token มาอยู่แล้ว)"""
    key = request.query_params.get("key") or request.headers.get("x-cron-key", "")
    if CRON_SECRET and key and hmac.compare_digest(key.encode(), CRON_SECRET.encode()):
        return True
    auth = request.headers.get("authorization", "")
    tok = auth[7:] if auth.lower().startswith("bearer ") else auth
    # กรองก่อนเรียก LINE verify (คำขอภายนอก): id_token จริงเป็น JWT 3 ท่อน + จำกัดต่อ IP
    if tok.count(".") == 2 and len(tok) > 100 and await _rate_ok_db(f"health:{_client_ip(request)}", 20, 60):
        try:
            await current_admin(authorization=auth)
            return True
        except Exception:
            return False
    return False


async def health(request: Request, deep: int = 0, test_gemini: int = 0, test_uid: str = "", test_ask: str = ""):
    out = {"ok": True, "time": NOW(),
           "commit": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "?")[:7],
           "deployed_at": os.environ.get("VERCEL_DEPLOYMENT_ID", "?")}
    if not deep:
        return out
    if not await _deep_health_allowed(request):
        out["deep"] = "locked — ต้องใช้ ?key=<CRON_SECRET> หรือ login แอดมิน"
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
    # เช็คว่า migration 0002/0003/0004 รันครบใน DB ไหม
    checks["schema"] = {}
    for tb in ("slips", "payment_accounts", "postback_actions", "app_settings",
               "richmenu_history", "registrations", "webhook_jobs", "tasks",
               "contact_notes", "classes", "attendance", "kb_articles", "postback_clicks"):
        try:
            n = await supa.count(tb)
            checks["schema"][tb] = f"ok ({n} rows)"
        except Exception as e:
            checks["schema"][tb] = f"MISSING — {str(e)[:100]}"
            out["ok"] = False
    try:
        await supa.select("rich_menus", params={"select": "gemini_enabled,gemini_temperature", "limit": "1"})
        checks["schema"]["rich_menus.gemini_*"] = "ok"
    except Exception as e:
        checks["schema"]["rich_menus.gemini_*"] = f"MISSING — {str(e)[:100]}"
        out["ok"] = False
    # EasySlip
    if EASYSLIP_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=12) as _c:
                _r = await _c.get("https://developer.easyslip.com/api/v1/me",
                                  headers={"Authorization": f"Bearer {EASYSLIP_TOKEN}"})
            _j = _r.json()
            if _r.status_code == 200:
                _q = (_j.get("data") or {}).get("quota") or _j.get("data") or {}
                _used = _q.get("usedQuota", _q.get("used"))
                _max = _q.get("maxQuota", _q.get("max", _q.get("limit")))
                _remain = _q.get("remainingQuota")
                if _used is None and _max is None:
                    # เผื่อ EasySlip เปลี่ยนชื่อ field อีก — โชว์ raw ไว้ดูเอง แทนที่จะขึ้น ?/? เฉยๆ
                    checks["easyslip"] = f"ok — quota (raw): {str(_q)[:150]}"
                else:
                    prefix = "⚠️ QUOTA หมด — " if _remain == 0 else "ok — "
                    reset_at = _q.get("expiredAt")
                    suffix = f" (รีเซ็ต {reset_at})" if reset_at else ""
                    checks["easyslip"] = f"{prefix}quota ใช้ {_used}/{_max}{suffix}"
            else:
                checks["easyslip"] = f"token error {_r.status_code}: {str(_j)[:120]}"
        except Exception as e:
            checks["easyslip"] = f"error: {str(e)[:120]}"
    else:
        checks["easyslip"] = "off (ยังไม่ตั้ง EASYSLIP_TOKEN)"

    # LIFF sync
    try:
        _tok, _terr = await _liff_channel_token()
        if _terr:
            checks["liff_sync"] = f"error: {_terr[:150]}"
        elif _tok:
            async with httpx.AsyncClient(timeout=12) as _c:
                _r = await _c.get("https://api.line.me/liff/v1/apps",
                                  headers={"Authorization": f"Bearer {_tok}"})
            checks["liff_sync"] = (f"ok ({len(_r.json().get('apps', []))} apps)"
                                   if _r.status_code == 200 else f"{_r.status_code}: {_r.text[:100]}")
        else:
            checks["liff_sync"] = "off (ยังไม่ตั้ง LINE_LOGIN_CHANNEL_SECRET / KID)"
    except Exception as e:
        checks["liff_sync"] = f"error: {str(e)[:120]}"
    _active_provider = "anthropic" if ANTHROPIC_API_KEY else ("google" if GEMINI_API_KEY else "none")
    checks["gemini"] = {
        "provider": _active_provider,  # ชื่อ key "gemini" คงไว้เพื่อ compat กับของเดิม — เลือกผู้ให้บริการอัตโนมัติ
        "api_key_set": bool(ANTHROPIC_API_KEY or GEMINI_API_KEY),
        "model": ANTHROPIC_MODEL if _active_provider == "anthropic" else GEMINI_MODEL,
        "trigger_menu_name": GEMINI_TRIGGER_MENU_NAME,
    }
    try:
        rows = await supa.select("rich_menus", params={
            "select": "rich_menu_id,name", "name": f"eq.{GEMINI_TRIGGER_MENU_NAME}"})
        checks["gemini"]["matching_menu_ids"] = [r["rich_menu_id"] for r in rows]
        all_names = await supa.select("rich_menus", params={"select": "name"})
        checks["gemini"]["all_menu_names_in_cache"] = [r["name"] for r in all_names]
    except Exception as e:
        checks["gemini"]["error"] = str(e)

    if test_uid:
        try:
            rid = await line.user_richmenu_get(test_uid)
            checks["gemini"]["test_uid"] = test_uid
            checks["gemini"]["test_uid_live_rich_menu_id"] = rid
            checks["gemini"]["test_uid_matches_trigger"] = rid in set(checks["gemini"].get("matching_menu_ids") or [])
        except Exception as e:
            checks["gemini"]["test_uid_error"] = str(e)

    if test_gemini:
        try:
            if _active_provider == "anthropic":
                _cl = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
                resp = await _cl.messages.create(
                    model=ANTHROPIC_MODEL, max_tokens=200,
                    messages=[{"role": "user", "content": "สวัสดี ทดสอบระบบ"}])
                checks["gemini"]["live_test_status"] = 200
                checks["gemini"]["live_test_body"] = "".join(
                    b.text for b in resp.content if b.type == "text")[:1000]
            elif _active_provider == "google":
                async with httpx.AsyncClient(timeout=20) as c:
                    gr = await c.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
                        json={"contents": [{"role": "user", "parts": [{"text": "สวัสดี ทดสอบระบบ"}]}],
                              "generationConfig": {"maxOutputTokens": 200}})
                checks["gemini"]["live_test_status"] = gr.status_code
                checks["gemini"]["live_test_body"] = gr.text[:1000]
            else:
                checks["gemini"]["live_test_error"] = "ไม่ได้ตั้งคีย์ผู้ให้บริการใดเลย"
        except anthropic.APIStatusError as e:
            checks["gemini"]["live_test_status"] = e.status_code
            checks["gemini"]["live_test_body"] = str(e.message)[:1000]
        except Exception as e:
            checks["gemini"]["live_test_error"] = str(e)

    if test_ask:
        try:
            ctx = await _gemini_context()
            kb = await _gemini_retrieve(test_ask)
            ans = await _gemini_answer(test_ask, context=(ctx + ("\n\n" + kb if kb else "")),
                                       uid=(test_uid or None), user_facts="(ทดสอบระบบ)")
            checks["gemini"]["ask_q"] = test_ask
            checks["gemini"]["ask_kb_hit"] = bool(kb)
            checks["gemini"]["ask_answer"] = ans
            if ans is None:
                # debug: ยิงตรงดูว่า model คืนอะไร (ไม่ใช้ tools กันเคส tool loop ตัน)
                try:
                    if _active_provider == "anthropic":
                        _cl = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
                        dr = await _cl.messages.create(
                            model=ANTHROPIC_MODEL, max_tokens=1024,
                            messages=[{"role": "user", "content": test_ask}])
                        checks["gemini"]["ask_debug"] = dr.to_json()[:800]
                    elif _active_provider == "google":
                        async with httpx.AsyncClient(timeout=25) as c:
                            dr = await c.post(
                                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
                                json={"contents": [{"role": "user", "parts": [{"text": test_ask}]}],
                                      "generationConfig": {"maxOutputTokens": 8192}})
                        checks["gemini"]["ask_debug"] = dr.text[:800]
                    else:
                        checks["gemini"]["ask_debug"] = "ไม่ได้ตั้งคีย์ผู้ให้บริการใดเลย"
                except Exception as e2:
                    checks["gemini"]["ask_debug"] = f"debug call error: {e2}"
        except Exception as e:
            checks["gemini"]["ask_error"] = repr(e)

    out["checks"] = checks
    return out


async def _fire_and_forget(path: str):
    """ยิง request ไปที่ตัวเอง โดยไม่รอผล — ให้ invocation ใหม่ทำงานหนักแทน (budget 60s ของตัวเอง)"""
    url = f"{APP_URL}{path}" + ("?" if "?" not in path else "&") + f"key={CRON_SECRET}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0, connect=2.0)) as c:
            await c.post(url)
    except Exception:
        pass  # ไม่รอผล — ถ้าไม่ถึงก็มี cron 5 นาที drain ให้


async def _run_webhook_jobs(limit: int = 15) -> dict:
    try:
        jobs = await supa.select("webhook_jobs", params={
            "select": "*", "status": "eq.pending", "order": "created_at.asc", "limit": str(limit)})
    except Exception as e:
        return {"error": str(e)[:120], "ran": 0}
    done = failed = 0
    for j in jobs:
        await supa.update("webhook_jobs", {"attempts": (j.get("attempts") or 0) + 1},
                          {"id": f"eq.{j['id']}"})
        try:
            if j["kind"] == "slips":
                evs = (j.get("payload") or {}).get("events") or []
                await asyncio.wait_for(_handle_slips(evs), timeout=45)
            await supa.update("webhook_jobs", {"status": "done", "processed_at": NOW()},
                              {"id": f"eq.{j['id']}"})
            done += 1
        except Exception as e:
            st = "failed" if (j.get("attempts") or 0) + 1 >= 3 else "pending"
            await supa.update("webhook_jobs", {"status": st, "error": str(e)[:200]},
                              {"id": f"eq.{j['id']}"})
            failed += 1
    return {"ran": len(jobs), "done": done, "failed": failed}


_OPTOUT_KW = ("ยกเลิกรับข่าว", "หยุดส่งข่าว", "หยุดส่งข้อความ", "ไม่รับข่าวสาร", "unsubscribe", "เลิกรับข่าว", "ขอหยุดรับข่าว")
_OPTIN_KW = ("รับข่าวสาร", "สมัครรับข่าว", "subscribe", "เปิดรับข่าว")


async def _handle_consent_keywords(events: list) -> set:
    handled: set = set()
    for e in events:
        if e.get("type") != "message" or e.get("message", {}).get("type") != "text":
            continue
        uid = e.get("source", {}).get("userId")
        rtok = e.get("replyToken")
        if not uid:
            continue
        txt = (e["message"].get("text") or "").lower().strip()
        if any(k in txt for k in _OPTOUT_KW):
            handled.add(uid)
            await supa.update("line_users", {"consent": False, "consent_at": NOW(), "updated_at": NOW()},
                              {"line_user_id": f"eq.{uid}"})
            if rtok:
                await line.reply(rtok, [{"type": "text", "text":
                    "รับทราบครับ ระบบจะไม่ส่งข่าวสาร/โปรโมชันให้อีก\n(ยังตอบข้อความที่คุณถามเข้ามาตามปกติ) "
                    "พิมพ์ 'รับข่าวสาร' เพื่อเปิดรับใหม่"}])
        elif any(k in txt for k in _OPTIN_KW):
            handled.add(uid)
            await supa.update("line_users", {"consent": True, "consent_at": NOW(), "updated_at": NOW()},
                              {"line_user_id": f"eq.{uid}"})
            if rtok:
                await line.reply(rtok, [{"type": "text", "text": "เปิดรับข่าวสารเรียบร้อยครับ 🙏"}])
    return handled


_DEV_CMD_PREFIX = "/dev"


async def _handle_dev_commands(events: list) -> set:
    """รับคำสั่ง 'พัฒนาระบบ' ที่เจ้าของพิมพ์คุยกับบอทโดยตรง ขึ้นต้นด้วย /dev — เก็บคิวไว้ให้ Claude มาอ่านทีหลัง
    ทำงานเฉพาะตอนเปิดใช้ (dev_command_enabled) และเฉพาะ userId ใน allow-list (dev_command_uids) เท่านั้น
    ไม่ได้แก้โค้ด/deploy เองอัตโนมัติ — แค่รับคำสั่งเก็บคิว + ตอบรับทันทีว่ารับแล้ว"""
    handled: set = set()
    text_events = [e for e in events if e.get("type") == "message"
                  and e.get("message", {}).get("type") == "text"
                  and (e["message"].get("text") or "").strip().lower().startswith(_DEV_CMD_PREFIX)]
    if not text_events:
        return handled
    if not await _get_setting("dev_command_enabled", False):
        return handled
    allow = set(await _get_setting("dev_command_uids", []) or [])
    if not allow:
        return handled
    for e in text_events:
        uid = e.get("source", {}).get("userId")
        if not uid or uid not in allow:
            continue
        handled.add(uid)
        cmd = (e["message"].get("text") or "").strip()[len(_DEV_CMD_PREFIX):].strip(": ").strip()
        rtok = e.get("replyToken")
        if not cmd:
            if rtok:
                await line.reply(rtok, [{"type": "text", "text":
                    "พิมพ์คำสั่งต่อท้าย /dev ด้วยครับ เช่น '/dev เพิ่มปุ่มในหน้า Users ให้ดาวน์โหลด CSV'"}])
            continue
        try:
            res = await supa.insert("dev_commands", {"line_user_id": uid, "command": cmd[:2000]})
            cid = res[0]["id"] if res else "?"
        except Exception as ex:
            print("dev_commands insert error (รัน migration 0021 หรือยัง?):", ex)
            if rtok:
                await line.reply(rtok, [{"type": "text", "text": "รับคำสั่งไม่สำเร็จ (ระบบคิวยังไม่พร้อม) — แจ้งแอดมินช่วยตรวจสอบ"}])
            continue
        if rtok:
            await line.reply(rtok, [{"type": "text", "text":
                f"📥 รับคำสั่ง #{cid} แล้วครับ: {cmd[:120]}\nสถานะ: รอดำเนินการ — ต้องรอให้เปิดเซสชันดูแลระบบมาอ่านคิวนี้ก่อนถึงจะเริ่มทำ ไม่ใช่อัตโนมัติทันที"}])
        await alert_admin("🛠 คำสั่งพัฒนาระบบใหม่", f"#{cid}: {cmd[:300]}", throttle_key=f"devcmd_{cid}")
    return handled


_STATUS_CMD = "/ตรวจข้อมูล"


async def _status_check_text(uid: str) -> tuple[str, bool]:
    """สร้างข้อความสถานะลงทะเบียน/การจ่ายเงิน/สลิปล่าสุดของ uid นี้ (ให้ user พิมพ์คำสั่งมาถามเอง
    แทนการ push แจ้งอัตโนมัติ — ประหยัดโควต้า) คืนคู่ (ข้อความ, มีรายการจ่ายแล้วไหม — ใช้ตัดสินใจแนบปุ่มดูใบเสร็จ)"""
    regs = await supa.select("registrations", params={
        "line_user_id": f"eq.{uid}", "select": "course,course_raw,paid", "order": "created_at.desc"})
    if not regs:
        return "ยังไม่พบข้อมูลการลงทะเบียนของคุณครับ ลงทะเบียนได้ที่เมนูด้านล่างเลยครับ 🙏", False
    lines = ["📋 สถานะของคุณ"]
    any_paid = False
    for r in regs:
        course = r.get("course_raw") or r.get("course") or "-"
        if r.get("paid"):
            any_paid = True
            lines.append(f"• {course}: 🟢 โอนเงินเรียบร้อยแล้ว รอติวตามเวลาที่กำหนด")
        else:
            lines.append(f"• {course}: 🟡 รอโอนเงิน")
            pay = _pay_lines(await _pay_account_for(r.get("course") or course))
            if pay:
                lines.append(pay)
    # สลิปล่าสุด (ถ้ามี) — โชว์สถานะ/เหตุผลแทนที่จะ push แจ้งตอนตรวจเสร็จแบบเดิม
    try:
        slip = await supa.select("slips", params={
            "line_user_id": f"eq.{uid}", "select": "status,auto_note", "order": "id.desc", "limit": "1"})
        if slip and slip[0]["status"] in ("new", "review"):
            lines.append("🔎 มีสลิปที่คุณส่งมาอยู่ระหว่างตรวจสอบ รอสักครู่นะครับ")
        elif slip and slip[0]["status"] == "rejected" and not any_paid:
            lines.append(f"⚠️ สลิปล่าสุดยังไม่ผ่าน: {slip[0].get('auto_note') or 'กรุณาส่งใหม่หรือติดต่อแอดมิน'}")
    except Exception:
        pass
    return "\n".join(lines), any_paid


async def _handle_status_check(events: list) -> set:
    """คำสั่ง /ตรวจข้อมูล — user พิมพ์เองเมื่ออยากรู้สถานะ ตอบผ่าน reply token (ฟรี) แทนการ push แจ้งอัตโนมัติ"""
    handled: set = set()
    for e in events:
        if e.get("type") != "message" or e.get("message", {}).get("type") != "text":
            continue
        if (e["message"].get("text") or "").strip() != _STATUS_CMD:
            continue
        uid = e.get("source", {}).get("userId")
        rtok = e.get("replyToken")
        if not uid or not rtok:
            continue
        handled.add(uid)
        text, any_paid = await _status_check_text(uid)
        msg = {"type": "text", "text": text}
        if any_paid and await _get_setting("send_receipt", True) is not False:
            msg["quickReply"] = {"items": [{"type": "action", "action": {
                "type": "postback", "label": "📄 ดูใบเสร็จ", "data": _RECEIPT_POSTBACK, "displayText": "ขอดูใบเสร็จ"}}]}
        await line.reply(rtok, [msg])
    return handled


async def _get_setting(key: str, default=None):
    try:
        rows = await supa.select("app_settings", params={"key": f"eq.{key}", "select": "value", "limit": "1"})
        return rows[0]["value"] if rows else default
    except Exception:
        return default


def _digits(s):
    return re.sub(r"\D", "", str(s or ""))


_MASK_CHARS = "xX*•"


def _acct_matches(receiver, account_no) -> bool:
    """เลขบัญชีปลายทางที่สลิปแสดงตรงกับบัญชีที่ตั้งไว้ไหม
    1) กติกาเดิม: 4 หลักท้ายตรง (สลิปที่โชว์เลขท้ายครบ)
    2) สลิปที่ธนาคารปิดเลขบางหลัก เช่น xxx-x-x5432-x / XXXXX7942XXX — หลักที่เห็นต้องตรงตำแหน่งเดียวกับเลขจริง
       (ถ้าความยาวเท่ากัน) หรือเป็นเลขติดกัน >=4 หลักที่อยู่ในเลขจริง (ถ้ารูปแบบความยาวไม่เท่า)"""
    real = _digits(account_no)
    if not real or not receiver:
        return False
    rd = _digits(receiver)
    if len(rd) >= 4 and rd[-4:] == real[-4:]:
        return True
    chars = re.sub(rf"[^0-9{re.escape(_MASK_CHARS)}]", "", str(receiver))
    if sum(c.isdigit() for c in chars) < 3:
        return False
    if len(chars) == len(real):
        return all(c in _MASK_CHARS or c == r for c, r in zip(chars, real))
    runs = re.findall(r"\d{4,}", re.sub(rf"[{re.escape(_MASK_CHARS)}]", " ", chars))
    return any(run in real for run in runs)


async def _easyslip_verify(image_bytes: bytes):
    """เรียก EasySlip -> คืน dict (verified, amount, receiver_acc, receiver_bank, ref, date) หรือ None"""
    if not EASYSLIP_TOKEN:
        return None
    b64 = base64.b64encode(image_bytes).decode()
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post("https://developer.easyslip.com/api/v1/verify",
                             headers={"Authorization": f"Bearer {EASYSLIP_TOKEN}"},
                             json={"image": b64})
        j = r.json()
        if j.get("status") != 200:
            return {"verified": False, "error": j.get("message") or j.get("status"), "raw": j}
        d = j.get("data") or {}
        amt = d.get("amount")
        amount = amt.get("amount") if isinstance(amt, dict) else amt
        recv = d.get("receiver") or {}
        racc = (recv.get("account") or {})
        return {
            "verified": True,
            "amount": amount,
            "receiver_acc": racc.get("bank", {}).get("account") or racc.get("proxy", {}).get("account") or racc.get("value"),
            "receiver_name": racc.get("name", {}).get("th") or racc.get("name", {}).get("en") if isinstance(racc.get("name"), dict) else racc.get("name"),
            "receiver_bank": (recv.get("bank") or {}).get("short") or (recv.get("bank") or {}).get("name"),
            "ref": d.get("transRef") or d.get("ref"),
            "date": d.get("date") or d.get("transDate"),
            "raw": j,
        }
    except Exception as e:
        print("easyslip error:", e)
        return None


_SLIP_CLASSIFY_PROMPT = (
    "ดูรูปนี้แล้วบอกว่าเป็น \"สลิปโอนเงิน/หลักฐานการชำระเงิน\" (สลิปธนาคาร, mobile banking, "
    "พร้อมเพย์ ใบเสร็จโอนเงิน ฯลฯ) หรือไม่ ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่นนอก JSON ห้ามมี markdown "
    "code fence ตามโครงสร้างนี้เป๊ะ ๆ:\n"
    '{"is_slip": true หรือ false, "confidence": ตัวเลข 0 ถึง 1 (ความมั่นใจในคำตอบ is_slip), '
    '"amount": จำนวนเงิน (ตัวเลขล้วน) หรือ null, "bank": ชื่อธนาคาร หรือ null, '
    '"receiver_account": เลขบัญชี/พร้อมเพย์ปลายทางที่อ่านได้ หรือ null, '
    '"ref": เลขที่อ้างอิงธุรกรรม หรือ null, "date": วันที่ทำรายการ รูปแบบ YYYY-MM-DD หรือ null}\n'
    "ถ้าไม่ใช่สลิป (เช่น รูปคน, สติกเกอร์, สกรีนช็อตแชท, การ์ตูน) ให้ is_slip=false และ field อื่น "
    "เป็น null ทั้งหมด"
)


def _parse_slip_classify_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    data = json.loads(text)
    return {
        "is_slip": bool(data.get("is_slip")),
        "confidence": float(data.get("confidence") or 0),
        "amount": data.get("amount"),
        "bank": data.get("bank"),
        "receiver_account": data.get("receiver_account"),
        "ref": data.get("ref"),
        "date": data.get("date"),
    }


async def _claude_classify_slip(image_bytes: bytes, mime: str) -> dict | None:
    """ใช้ Claude (vision) เดาว่ารูปนี้เป็นสลิปโอนเงินไหม — ดู _gemini_classify_slip (dispatcher) สำหรับคำอธิบายเต็ม"""
    if not ANTHROPIC_API_KEY or not image_bytes:
        return None
    b64 = base64.b64encode(image_bytes).decode()
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=8)
        resp = await client.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=400, temperature=0.1,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                 "media_type": mime or "image/jpeg", "data": b64}},
                {"type": "text", "text": _SLIP_CLASSIFY_PROMPT},
            ]}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return _parse_slip_classify_json(text)
    except Exception as e:
        print("claude slip classify error:", e)
        return None


async def _google_classify_slip(image_bytes: bytes, mime: str) -> dict | None:
    """ใช้ Gemini (vision) เดาว่ารูปนี้เป็นสลิปโอนเงินไหม — ดู _gemini_classify_slip (dispatcher) สำหรับคำอธิบายเต็ม"""
    if not GEMINI_API_KEY or not image_bytes:
        return None
    b64 = base64.b64encode(image_bytes).decode()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    body = {
        "contents": [{"role": "user", "parts": [
            {"text": _SLIP_CLASSIFY_PROMPT},
            {"inlineData": {"mimeType": mime or "image/jpeg", "data": b64}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": 400},
    }
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(url, json=body)
        j = r.json()
        if r.status_code != 200:
            print("gemini slip classify http error:", r.status_code, str(j)[:300])
            return None
        cand = (j.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        return _parse_slip_classify_json(text)
    except Exception as e:
        print("gemini slip classify error:", e)
        return None


async def _gemini_classify_slip(image_bytes: bytes, mime: str) -> dict | None:
    """เดาว่ารูปนี้เป็นสลิปโอนเงิน/หลักฐานชำระเงินไหม + อ่านข้อมูลคร่าว ๆ (ยอด/ธนาคาร/เลขบัญชี/ref/วันที่)
    เป็นแค่ตัวช่วยกรอง+อ่านเบื้องต้น ไม่ใช่การยืนยันที่เชื่อถือได้ 100% (ไม่มี fraud-check เหมือน EasySlip)
    เลือกผู้ให้บริการอัตโนมัติ: Claude ก่อนถ้ามี ANTHROPIC_API_KEY ไม่งั้นใช้ Gemini ถ้ามี GEMINI_API_KEY
    คืน None ถ้าไม่ได้ตั้งคีย์ใดเลย หรือ error ทั้งคู่"""
    if ANTHROPIC_API_KEY:
        return await _claude_classify_slip(image_bytes, mime)
    if GEMINI_API_KEY:
        return await _google_classify_slip(image_bytes, mime)
    return None


# ---------- ดูรูปที่ user ส่งมาก่อนตอบ: สลิป -> "ขอตรวจสอบ" · รูปทั่วไป -> วิเคราะห์แล้วตอบ ----------
_IMAGE_ANALYZE_PROMPT = (
    'คุณคือ "น้องพัสดุ" ผู้ช่วยของติวเตอร์สอบมาตรฐานวิชาชีพด้านการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ (e-CPP) '
    "ตอบลูกค้าทาง LINE ลูกค้าส่งรูปมา 1 รูป ให้ทำ 2 อย่างในคำตอบเดียว:\n"
    '1) ตัดสินว่ารูปนี้คือ "สลิปโอนเงิน/หลักฐานการชำระเงิน" (สลิปธนาคาร, mobile banking, พร้อมเพย์, ใบเสร็จโอนเงิน) หรือไม่\n'
    "2) ถ้าไม่ใช่สลิป ให้วิเคราะห์ว่าเป็นรูปอะไร แล้วเขียนข้อความตอบลูกค้า\n\n"
    "ตอบเป็น JSON เท่านั้น ห้ามมี markdown code fence ห้ามมีข้อความนอก JSON ตามโครงสร้างนี้:\n"
    '{"kind": "slip" หรือ "other", "confidence": ตัวเลข 0 ถึง 1 (ความมั่นใจใน kind), '
    '"slip": {"amount": ตัวเลขล้วน หรือ null, "bank": ชื่อธนาคาร หรือ null, "receiver_account": เลขบัญชี/พร้อมเพย์ปลายทาง หรือ null, '
    '"ref": เลขอ้างอิงธุรกรรม หรือ null, "date": "YYYY-MM-DD" หรือ null} เมื่อ kind=slip ไม่งั้นเป็น null, '
    '"reply": "ข้อความภาษาไทยตอบลูกค้า" เมื่อ kind=other ไม่งั้นเป็น null}\n\n'
    "กติกาของ reply (เมื่อ kind=other):\n"
    '- ภาษาไทยสุภาพ ลงท้าย "ครับ" สั้นกระชับ ไม่เกิน 5 บรรทัด ห้ามใช้ markdown (** # หรือขีดนำหน้า) ใช้อีโมจิได้เล็กน้อย\n'
    '- เริ่มด้วยการบอกสั้น ๆ ว่าเห็นเป็นรูปอะไร (เช่น "เป็นรูปสกรีนช็อตโจทย์ข้อสอบ...", "เป็นรูปถ่ายอาหาร...") แล้วช่วยตามประเภท:\n'
    "  • โจทย์/ข้อสอบ/เนื้อหาเกี่ยวกับการจัดซื้อจัดจ้างและพัสดุภาครัฐ: อ่านโจทย์ ตอบสั้น ๆ พร้อมเหตุผล 1-2 ประโยค "
    "และแนะนำให้ทวนกับเอกสารติวอีกครั้ง (ไม่ใช่คำวินิจฉัยทางกฎหมาย)\n"
    "  • สกรีนช็อตปัญหาการลงทะเบียน/ชำระเงิน/ระบบ: สรุปสั้น ๆ ว่าเห็นอะไร แล้วบอกว่าแอดมินจะช่วยดู ให้พิมพ์ 'ติดต่อแอดมิน'\n"
    "  • เอกสารส่วนตัว (บัตรประชาชน ทะเบียนบ้าน สมุดบัญชี ฯลฯ): บอกแค่ประเภทเอกสาร ห้ามอ่านหรือทวนเลข/ที่อยู่/ชื่อออกมา "
    "และแนะนำไม่ให้ส่งเอกสารส่วนตัวในแชท (การลงทะเบียนทำผ่านฟอร์ม)\n"
    "  • รูปอื่น (คน สัตว์ อาหาร สถานที่ มีม สติกเกอร์): ตอบเป็นกันเองสั้น ๆ ว่าเห็นอะไร แล้วถามว่ามีอะไรให้ช่วยเรื่องการติว/สมัครเรียนไหม\n"
    "  • รูปไม่เหมาะสม/อนาจาร/รุนแรง: ตอบสุภาพว่าไม่สามารถตอบรูปแบบนี้ได้\n"
    "  • รูปเบลอ/ไม่ชัด: บอกว่าดูไม่ชัด ขอให้ส่งใหม่หรือพิมพ์บอกว่าต้องการอะไร\n"
    "- ห้ามอ้างว่าตรวจการชำระเงินหรือยืนยันการสมัครให้ ห้ามเดาสิ่งที่ไม่เห็นในรูป ห้ามให้เลขบัญชีหรือราคา "
    "(ถ้าลูกค้าอยากรู้ ให้พิมพ์ข้อความมาถาม)"
)


def _parse_image_analysis(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        d = json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except Exception:
            return None
    kind = d.get("kind")
    if kind not in ("slip", "other"):
        return None
    slip = d.get("slip") if isinstance(d.get("slip"), dict) else None
    reply = d.get("reply")
    reply = reply.strip()[:900] if isinstance(reply, str) and reply.strip() else None
    try:
        conf = float(d.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    return {"kind": kind, "confidence": max(0.0, min(conf, 1.0)),
            "slip": ({k: slip.get(k) for k in ("amount", "bank", "receiver_account", "ref", "date")} if slip else None),
            "reply": reply}


async def _claude_analyze_image(image_bytes: bytes, mime: str) -> dict | None:
    if not ANTHROPIC_API_KEY or not image_bytes:
        return None
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=20)
        resp = await client.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=900, temperature=0.3,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime or "image/jpeg",
                                             "data": base64.b64encode(image_bytes).decode()}},
                {"type": "text", "text": _IMAGE_ANALYZE_PROMPT}]}])
        return _parse_image_analysis("".join(b.text for b in resp.content if b.type == "text"))
    except Exception as e:
        print("claude image analyze error:", repr(e)[:200])
        return None


async def _google_analyze_image(image_bytes: bytes, mime: str) -> dict | None:
    if not GEMINI_API_KEY or not image_bytes:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    body = {
        "contents": [{"role": "user", "parts": [
            {"text": _IMAGE_ANALYZE_PROMPT},
            {"inlineData": {"mimeType": mime or "image/jpeg", "data": base64.b64encode(image_bytes).decode()}}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3, "maxOutputTokens": 900},
    }
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, json=body)
        j = r.json()
        if r.status_code != 200:
            print("gemini image analyze http error:", r.status_code, str(j)[:300])
            return None
        parts = ((j.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return _parse_image_analysis("".join(p.get("text", "") for p in parts))
    except Exception as e:
        print("gemini image analyze error:", repr(e)[:200])
        return None


async def _analyze_image(image_bytes: bytes, mime: str) -> dict | None:
    """ดูรูปครั้งเดียวได้ทั้ง 'เป็นสลิปไหม (+ข้อมูลที่อ่านได้)' และ 'ถ้าไม่ใช่ เป็นรูปอะไร + ข้อความตอบ' (ประหยัดโควต้า AI)
    เลือกผู้ให้บริการอัตโนมัติเหมือน _gemini_classify_slip; คืน None ถ้า AI ใช้ไม่ได้/ตอบผิดรูปแบบ"""
    if ANTHROPIC_API_KEY:
        return await _claude_analyze_image(image_bytes, mime)
    if GEMINI_API_KEY:
        return await _google_analyze_image(image_bytes, mime)
    return None


_ACK_SLIP = "ขอตรวจสอบสลิปสักครู่นะครับ 🙏 เช็คผลได้ทันทีโดยพิมพ์ /ตรวจข้อมูล"
_ACK_MAYBE = "ขอตรวจสอบรูปนี้สักครู่นะครับ 🙏"
_ACK_UNSURE = "ได้รับรูปแล้วครับ ทีมงานจะตรวจสอบให้นะครับ 🙏"
_GENERIC_IMAGE_REPLY = "ได้รับรูปแล้วครับ 🙏 มีอะไรให้ช่วยเรื่องการติวหรือการสมัครเรียน พิมพ์บอกได้เลยนะครับ"


async def _image_ai_on() -> bool:
    """โหมด 'ดูรูปก่อนแล้วค่อยตอบ' — เปิดโดย default ถ้ามี AI; ปิดได้ด้วย setting image_ai_reply=false (กลับไปใช้กฎตอบอัตโนมัติชนิดรูปภาพเดิม)"""
    if not (ANTHROPIC_API_KEY or GEMINI_API_KEY):
        return False
    return bool(await _get_setting("image_ai_reply", True))


async def _reply_image(e: dict, uid: str, mid: str, text: str, by: str = "auto") -> bool:
    """ตอบรูปที่ user ส่งมา — ผ่าน reply token (ฟรี) ถ้าใช้ไม่ได้ค่อย push (นับโควต้าข้อความ)
    ไม่ตอบถ้าแอดมินกำลังคุยเอง (auto_reply_paused) หรือเคยตอบรูปนี้ไปแล้ว (กันคิวงานรันซ้ำแล้วตอบซ้ำ)"""
    if not text:
        return False
    try:
        u = await supa.select("line_users", params={
            "select": "auto_reply_paused", "line_user_id": f"eq.{uid}", "limit": "1"})
        if u and u[0].get("auto_reply_paused"):
            return False
        done = await supa.select("messages", params={
            "select": "id", "line_user_id": f"eq.{uid}", "direction": "eq.out",
            "payload->>reply_to": f"eq.{mid}", "limit": "1"})
        if done:
            return False
    except Exception as ex:
        print("reply_image pre-check error:", repr(ex)[:120])
    msgs = [{"type": "text", "text": text[:4900]}]
    code = 0
    if e.get("replyToken"):
        code, _ = await line.reply(e["replyToken"], msgs)
    if code != 200:
        try:
            code, *_ = await line.push(uid, msgs)
        except Exception:
            code = 0
    if code != 200:
        return False
    try:
        await supa.insert("messages", {"line_user_id": uid, "direction": "out", "by": by, "msg_type": "text",
                                       "text": text, "payload": {"type": "text", "text": text, "reply_to": mid}})
    except Exception as ex:
        print("reply_image log error:", repr(ex)[:120])
    return True


async def _reply_general_image(e: dict, uid: str, mid: str, text: str | None) -> bool:
    if not await _rate_ok_db(f"imgai:{uid}", 3, 60):   # ส่งรูปรัว ๆ ตอบไม่เกิน 3 ครั้ง/นาที/คน
        return False
    return await _reply_image(e, uid, mid, text or _GENERIC_IMAGE_REPLY, by="gemini")


async def _evaluate_slip(ocr, exp_course, slip_id) -> dict:
    """ตัดสินสถานะสลิปจากผลอ่าน (EasySlip/Gemini) + จับคู่บัญชี/ยอด/หลักสูตร/ref ซ้ำ
    ใช้ร่วมกันทั้ง webhook (_handle_slips) และการตรวจซ้ำสลิปค้าง (_reprocess_slips) — กฎต้องเป็นชุดเดียวกัน"""
    status, matched, auto_note, dup_ref = "new", None, None, None
    amount = ocr.get("amount") if ocr else None
    ref = ocr.get("ref") if ocr else None

    # ---- ตรวจ ref ซ้ำ (ทุก source ไม่ใช่แค่ EasySlip) ----
    if ref:
        exist = await supa.select("slips", params={
            "ref": f"eq.{ref}", "id": f"neq.{slip_id or 0}",
            "select": "id", "limit": "1"})
        if exist:
            status, dup_ref = "rejected", ref
            auto_note = "สลิปนี้เคยส่งมาแล้ว (ref ซ้ำ)"

    if status != "rejected" and ocr and ocr.get("verified"):
        accounts = await supa.select("payment_accounts", params={"select": "*", "active": "eq.true"})
        candidates = [a for a in accounts if _acct_matches(ocr.get("receiver_acc"), a["account_no"])]
        # ถ้ารู้หลักสูตรที่ลงทะเบียนไว้แล้ว (จากทะเบียนจริง) ให้เลือกบัญชีที่ตรงหลักสูตรนั้นก่อน
        # กันเลือกบัญชีผิดตัวตอนมีหลายคอร์สใช้เลขบัญชีท้าย 4 ตัวซ้ำกัน
        known_course = exp_course  # มาจากทะเบียนจริงเท่านั้น (ถ้ามี) — ก่อนจะ fallback เป็นคอร์สของบัญชีที่ match
        acc = None
        if known_course:
            acc = next((a for a in candidates
                       if str(a["course"]).upper().startswith(known_course.upper()[:2])), None)
        if not acc:
            acc = candidates[0] if candidates else None
        if not acc:
            status, auto_note = "review", f"บัญชีปลายทางไม่ตรงรายการ ({ocr.get('receiver_acc')})"
        else:
            def _near(target):
                return target not in (None, "") and abs(float(amount or 0) - float(target)) < 1
            matched = _near(acc.get("price")) or _near(acc.get("full_price"))
            mismatch_course = bool(known_course) and not str(acc["course"]).upper().startswith(known_course.upper()[:2])
            exp_course = exp_course or acc["course"]
            if mismatch_course:
                # ลงทะเบียนไว้คอร์สหนึ่ง แต่ยอด/บัญชีที่ตรงกลับเป็นอีกคอร์ส -> ให้แอดมินเช็คเอง ไม่ auto-verify
                status, auto_note = "review", f"⚠️ ลงทะเบียน {known_course} แต่ยอด/บัญชีตรงกับคอร์ส {acc['course']} — รบกวนแอดมินเช็ค"
            elif matched:
                status, auto_note = "verified", f"✓ {acc['course']} · {amount} บาท · {acc['bank']}"
            else:
                status, auto_note = "review", f"ยอดไม่ตรง: โอน {amount} / ราคา {acc['price']} ({acc['course']})"
    elif status != "rejected" and ocr and ocr.get("source") == "gemini":
        conf_pct = round((ocr.get("confidence") or 0) * 100)
        extra = f" (EasySlip: {ocr.get('easyslip_error')})" if ocr.get("easyslip_error") else ""
        status, auto_note = "review", f"🤖 Gemini เดาว่าอาจเป็นสลิป (มั่นใจ {conf_pct}%){extra} — ยังไม่ตรวจยอด/ธนาคารจริง รบกวนแอดมินเช็คเอง"
    elif status != "rejected" and ocr and not ocr.get("verified"):
        status, auto_note = "review", f"ตรวจสลิปไม่ผ่าน: {ocr.get('error')}"
    elif status != "rejected" and EASYSLIP_TOKEN:
        status, auto_note = "review", "อ่านสลิปไม่ได้"
    return {"status": status, "matched": matched, "auto_note": auto_note, "dup_ref": dup_ref,
            "amount": amount, "ref": ref, "exp_course": exp_course}


async def _handle_slips(img_events: list):
    notify_all = bool(await _get_setting("slip_notify_all_images", True))
    image_ai = await _image_ai_on()
    acked: set = set()   # ส่งข้อความ "ขอตรวจสอบ" ให้ user คนละ 1 ครั้งต่อ batch (ส่งหลายรูปพร้อมกันไม่ต้องตอบซ้ำหลายรอบ)

    for e in img_events:
        uid = e.get("source", {}).get("userId")
        mid = e.get("message", {}).get("id")
        mtype = e.get("message", {}).get("type")
        if not uid or not mid:
            continue

        content, ctype = await line.get_message_content(mid)
        media_url = None
        if content:
            ext = {"image/png": "png", "image/jpeg": "jpg"}.get(ctype, "jpg" if mtype == "image" else "bin")
            path = f"slips/{dt.date.today().isoformat()}/{mid}.{ext}"
            try:
                media_url = await supa.storage_upload("media", path, content, ctype or "image/jpeg")
                await supa.update("messages", {"media_url": media_url},
                                  {"line_user_id": f"eq.{uid}", "payload->>id": f"eq.{mid}"})
            except Exception as ex:
                print("slip upload error:", ex)

        # เป็นสลิปไหม — ดูจาก context: เคยคุยเรื่องชำระเงินใน 24 ชม.ล่าสุด (heuristic แบบเดิม)
        pay_ctx = False
        blob = ""
        try:
            since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).isoformat()
            recent = await supa.select("messages", params={
                "select": "text", "line_user_id": f"eq.{uid}",
                "created_at": f"gte.{since}", "order": "created_at.desc", "limit": "15"})
            blob = " ".join((r.get("text") or "") for r in recent)
            pay_ctx = any(w in blob for w in ("ชำระ", "โอน", "สลิป", "สมัคร", "ค่าติว", "บัญชี", "หลักสูตร"))
        except Exception:
            blob = ""

        # ---- gate: รูปนี้เป็น "สลิป" ไหม ----
        gclass = None
        is_slip = pay_ctx
        maybe_slip = False   # ไม่แน่ใจ -> สร้างแถวให้แอดมินเห็น แต่ยังไม่สลับเมนู
        ack = None           # ข้อความตอบ user ทันที (ก่อนตรวจต่อ)
        if image_ai and mtype == "image" and content:
            # ดูรูปก่อนแล้วค่อยตอบ: สลิป -> "ขอตรวจสอบ" + ตรวจต่อ · รูปทั่วไป -> วิเคราะห์แล้วตอบ ไม่ถือเป็นสลิป
            analysis = await _analyze_image(content, ctype)
            if analysis:
                conf = analysis["confidence"]
                if analysis["kind"] == "slip" and conf >= 0.55:
                    is_slip, ack = True, _ACK_SLIP
                    gclass = {"is_slip": True, "confidence": conf, **(analysis.get("slip") or {})}
                elif analysis["kind"] == "other" and conf >= (0.8 if pay_ctx else 0.6):
                    await _reply_general_image(e, uid, mid, analysis.get("reply"))
                    continue   # รูปทั่วไป: ไม่สร้างแถวสลิป ไม่แจ้งแอดมินว่าเป็นสลิป (รูปยังอยู่ในกล่องข้อความ)
                else:
                    # ไม่แน่ใจ -> ปฏิบัติเหมือนอาจเป็นสลิป (พลาดสลิปจริงแย่กว่าตรวจเกิน) แต่ไม่สลับเมนูถ้าไม่มีบริบทเรื่องเงิน
                    maybe_slip, ack = True, _ACK_MAYBE
            else:
                ack = _ACK_UNSURE   # AI ใช้ไม่ได้: ตอบกลาง ๆ แล้วทำตามกติกาเดิม (pay_ctx / notify_all)
        elif content and not pay_ctx:
            # ปิดโหมด AI ดูรูป หรือเป็นไฟล์ (ไม่ใช่รูปภาพ): กติกาเดิม — ถาม Gemini เฉพาะเมื่อไม่มีบริบทเรื่องเงิน
            gclass = await _gemini_classify_slip(content, ctype)
            is_slip = bool(gclass and gclass.get("is_slip") and (gclass.get("confidence") or 0) >= 0.55)

        if ack and uid not in acked:
            acked.add(uid)
            await _reply_image(e, uid, mid, ack, by="auto")

        if not (is_slip or maybe_slip or notify_all):
            continue  # ไม่ใช่สลิป + ไม่ได้ตั้งให้แจ้งทุกรูป -> ข้าม (ไม่สร้าง row)

        # ---- หาหลักสูตรที่คาดว่าจะจ่าย: ใช้ทะเบียนจริงก่อน (แม่นสุด — คนละ 1 หลักสูตรเท่านั้น)
        # ถ้ายังไม่พบทะเบียนเลย (เช่น ส่งสลิปมาก่อนลงทะเบียน) ค่อย fallback ไปเดาจากบทสนทนา ----
        exp_course = None
        try:
            reg = await supa.select("registrations", params={
                "line_user_id": f"eq.{uid}", "select": "course", "limit": "1"})
            if reg:
                exp_course = reg[0]["course"]
        except Exception:
            pass
        if not exp_course:
            for c in ("FC", "IC", "PC", "AC"):
                if f"หลักสูตร {c}" in blob or f"course={c}" in blob or f"{c}70" in blob:
                    exp_course = c
                    break

        # ============ ทำสิ่งที่สำคัญต่อเวลาก่อน (ก่อนอ่านสลิปที่ช้า) ============
        # 1) สร้าง slip row ทันที (status=new) จะได้ไม่หายถ้า handler ถูกตัดกลางคัน
        slip_id = None
        try:
            slip_row = await supa.insert("slips", {
                "line_user_id": uid, "message_id": mid, "media_url": media_url,
                "status": "new", "expected_course": exp_course})
            slip_id = (slip_row[0]["id"] if slip_row else None)
        except Exception as ex:
            print("slip pre-insert error:", ex)

        # 2) สลับ rich menu ทันที — เฉพาะเมื่อมั่นใจว่าเป็นสลิป (notify_all อย่างเดียวไม่สลับ)
        #    ล้มเหลวแล้วแจ้งแอดมิน + ลองซ้ำ (เดิมเงียบ) ดู _link_slip_menu
        menu_ok = False
        if is_slip and SLIP_SUCCESS_RICHMENU_ID:
            menu_ok = bool((await _link_slip_menu(uid)).get("ok"))

        # ============ ตอนนี้ค่อยอ่านสลิป (ช้า) แล้ว update row ============
        ocr = await _easyslip_verify(content) if content else None
        easyslip_err = ocr.get("error") if ocr and not ocr.get("verified") else None
        if not ocr or easyslip_err:
            # EasySlip อ่านไม่ได้ หรือ error (เช่น quota_exceeded/rate_limit) -> ใช้ Gemini อ่านแทน
            # (ถ้ายังไม่ได้เรียกใน gate) กันไม่ให้ตกไป "ตรวจสลิปไม่ผ่าน" เฉยๆ ทั้งที่ยังพอเดาข้อมูลได้
            if gclass is None and content:
                gclass = await _gemini_classify_slip(content, ctype)
            if gclass and gclass.get("is_slip"):
                ocr = {"verified": False, "amount": gclass.get("amount"),
                       "receiver_acc": gclass.get("receiver_account"), "receiver_bank": gclass.get("bank"),
                       "ref": gclass.get("ref"), "date": gclass.get("date"),
                       "source": "gemini", "confidence": gclass.get("confidence"),
                       "easyslip_error": easyslip_err}

        ev = await _evaluate_slip(ocr, exp_course, slip_id)
        status, matched, auto_note, dup_ref = ev["status"], ev["matched"], ev["auto_note"], ev["dup_ref"]
        amount, ref, exp_course = ev["amount"], ev["ref"], ev["exp_course"]

        # 2b) ตาข่ายนิรภัย: ประตูด้านบนไม่แน่ใจ/AI ล่ม จึงยังไม่สลับเมนู แต่ EasySlip ยืนยันแล้วว่าเป็นสลิปโอนเงินจริง
        #     (หรือผ่านตรวจจนเป็น verified) -> สลับเมนูให้ตอนนี้ กันคนจ่ายจริงแต่เมนูไม่เปลี่ยน
        if (not menu_ok and SLIP_SUCCESS_RICHMENU_ID
                and (status == "verified" or (ocr and ocr.get("verified") and ocr.get("source") != "gemini"))):
            menu_ok = bool((await _link_slip_menu(uid, source="slip_verified")).get("ok"))

        # 3) update slip row ด้วยผลที่อ่านได้
        patch = {"ocr": ocr, "amount": amount, "ref": None if dup_ref else ref,
                 "bank": ocr.get("receiver_bank") if ocr else None,
                 "slip_date": str(ocr.get("date")) if ocr and ocr.get("date") else None,
                 "status": status, "matched": matched, "auto_note": auto_note,
                 "dup_ref": dup_ref, "expected_course": exp_course}
        try:
            if slip_id:
                await supa.update("slips", patch, {"id": f"eq.{slip_id}"})
            else:
                await supa.insert("slips", {**patch, "line_user_id": uid, "message_id": mid, "media_url": media_url})
        except Exception as ex:
            print("slip update error:", ex)

        # ผลตรวจอัตโนมัติ — ไม่ push แจ้งผลให้ user เองแล้ว (ประหยัดโควต้า) ผลลัพธ์ดูได้ทันทีเมื่อพิมพ์ /ตรวจข้อมูล
        # (ตอบผ่าน reply token ฟรี, ดู _status_check_text) ก่อนหน้านี้ตอนรับรูปแล้วตอบ _ACK_SLIP ด้วย reply token
        # ไปแล้วว่าให้พิมพ์คำสั่งมาดูผล — ตรงนี้แค่ทำงานหลังบ้าน (mark จ่าย/automation) ไม่ต้องแจ้งซ้ำ
        if status == "verified":
            try:
                await _enroll_automations("slip_verified", [uid], {"course": exp_course})
                await _mark_registration_paid(uid, exp_course)
            except Exception as ex:
                print("slip_verified post error:", ex)

        # แจ้งแอดมิน
        prof = await line.get_profile(uid)
        name = (prof or {}).get("displayName") or uid[:10]
        emoji = {"verified": "✅", "rejected": "⛔", "review": "⚠️"}.get(status, "🧾")
        detail = f"จาก: {name}\n" + (auto_note + "\n" if auto_note else "") + f"เปิดดู: {APP_URL}/slips"
        await alert_admin(f"{emoji} สลิป: {status}", detail, throttle_key=f"slip_{mid}")


# ---------- ตรวจซ้ำสลิปที่ค้าง (เงียบ: ไม่ส่งข้อความ/ใบเสร็จ/automation/สลับเมนูหาลูกค้าย้อนหลัง) ----------
_REPROCESS_RETRY_NOTES = ("quota_exceeded", "rate_limit")   # ค้างเพราะ EasySlip โควต้าเต็ม/ถูกจำกัด — ลองใหม่ได้
_EASYSLIP_RESERVE = 40   # กันโควต้า EasySlip ไว้ให้สลิปใหม่ที่เข้ามาจริง ไม่ใช้จนหมดกับกองเก่า


async def _fetch_image(url: str):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(url)
    if r.status_code != 200 or not r.content:
        return None, None
    return r.content, r.headers.get("content-type", "image/jpeg")


async def _easyslip_remaining():
    if not EASYSLIP_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get("https://developer.easyslip.com/api/v1/me",
                            headers={"Authorization": f"Bearer {EASYSLIP_TOKEN}"})
        d = r.json().get("data") or {}
        q = d.get("quota") or d
        rem = q.get("remainingQuota")
        return int(rem) if rem is not None else None
    except Exception:
        return None


async def _reprocess_candidates() -> dict:
    """สลิปค้างที่ 'ควรลองใหม่ได้': (ก) ไม่เคยถูกประมวลผลเลย (new ไม่มีหมายเหตุ) (ข) review เพราะ EasySlip โควต้าเต็ม
    ไม่รวม qrcode_not_found/บัญชีไม่ตรง/ยอดไม่ตรง — ตรวจซ้ำก็ได้ผลเดิม เสียโควต้าเปล่า ต้องให้คนดู"""
    rows = await supa.select_all("slips", params={
        "select": "id,line_user_id,media_url,status,auto_note,expected_course,created_at,ocr",
        "status": "in.(new,review)", "order": "created_at.desc"})
    never, retry, rematch, no_media = [], [], [], 0
    for r in rows:
        note = r.get("auto_note") or ""
        if (r["status"] == "review" and note.startswith("บัญชีปลายทางไม่ตรงรายการ")
                and isinstance(r.get("ocr"), dict) and r["ocr"].get("verified")):
            # EasySlip อ่านสลิปสำเร็จแล้ว แต่จับคู่บัญชีไม่ได้ (เช่น เลขบัญชีถูกปิดบางหลัก) — ประเมินใหม่จากผล OCR ที่เก็บไว้
            # ไม่ต้องดึงรูป ไม่เรียก EasySlip ไม่เสียโควต้า
            r["_offline"] = True
            rematch.append(r)
            continue
        if r["status"] == "new" and not note:
            bucket = never
        elif r["status"] == "review" and any(k in note for k in _REPROCESS_RETRY_NOTES):
            bucket = retry
        else:
            continue
        if not r.get("media_url"):
            no_media += 1
            continue
        bucket.append(r)
    return {"never_processed": never, "quota_retry": retry, "rematch": rematch, "no_media": no_media}


async def _reprocess_slips(apply: bool, limit: int = 40, offline: bool = True) -> dict:
    c = await _reprocess_candidates()
    todo = c["quota_retry"] + c["never_processed"]   # ที่รู้แน่ว่าเป็นสลิปจริง (โควต้าเต็ม) ก่อน — ต้องเรียก EasySlip
    out = {"never_processed": len(c["never_processed"]), "quota_retry": len(c["quota_retry"]),
           "rematch_offline": len(c["rematch"]), "no_media": c["no_media"],
           "candidates": len(todo) + len(c["rematch"])}
    if not apply:
        return out   # ดูอย่างเดียว — ไม่เรียก EasySlip ไม่เสียโควต้า
    remaining = await _easyslip_remaining()
    budget = limit if remaining is None else max(0, min(limit, remaining - _EASYSLIP_RESERVE))
    out.update({"easyslip_remaining": remaining, "budget": budget})
    # rematch ใช้ผลที่เก็บไว้ ไม่กินงบ EasySlip — offline=False ตอนหน้าเว็บเรียกวนหลายชุด (ทำรอบแรกรอบเดียว กันวนซ้ำใบที่ยังไม่ตรง)
    batch = (c["rematch"][:200] if offline else []) + todo[:budget]
    counts = {"verified": 0, "review": 0, "rejected": 0, "no_image": 0, "error": 0}
    items = []
    sem, lock = asyncio.Semaphore(4), asyncio.Lock()

    async def one(r):
        uid = r["line_user_id"]
        try:
            async with sem:   # ส่วนช้า (ดึงรูป/EasySlip/Gemini) ทำขนานได้
                if r.get("_offline"):
                    ocr = r["ocr"]   # ประเมินใหม่จากผล OCR เดิม
                else:
                    content, mime = await _fetch_image(r["media_url"])
                    if not content:
                        counts["no_image"] += 1
                        return
                    ocr = await _easyslip_verify(content)
                    easyslip_err = ocr.get("error") if ocr and not ocr.get("verified") else None
                    if not ocr or easyslip_err:
                        g = await _gemini_classify_slip(content, mime)
                        if g and g.get("is_slip"):
                            ocr = {"verified": False, "amount": g.get("amount"), "receiver_acc": g.get("receiver_account"),
                                   "receiver_bank": g.get("bank"), "ref": g.get("ref"), "date": g.get("date"),
                                   "source": "gemini", "confidence": g.get("confidence"), "easyslip_error": easyslip_err}
            async with lock:   # ประเมิน+บันทึกทีละใบ — สลิปซ้ำในกองเดียวกันจะเห็นกันและกัน (เช็ค ref ซ้ำ)
                exp = r.get("expected_course")
                try:
                    reg = await supa.select("registrations", params={
                        "line_user_id": f"eq.{uid}", "select": "course", "limit": "1"})
                    if reg:
                        exp = reg[0]["course"]
                except Exception:
                    pass
                ev = await _evaluate_slip(ocr, exp, r["id"])
                await supa.update("slips", {
                    "ocr": ocr, "amount": ev["amount"], "ref": None if ev["dup_ref"] else ev["ref"],
                    "bank": ocr.get("receiver_bank") if ocr else None,
                    "slip_date": str(ocr.get("date")) if ocr and ocr.get("date") else None,
                    "status": ev["status"], "matched": ev["matched"], "auto_note": ev["auto_note"],
                    "dup_ref": ev["dup_ref"], "expected_course": ev["exp_course"]}, {"id": f"eq.{r['id']}"})
                counts[ev["status"] if ev["status"] in counts else "review"] += 1
                if ev["status"] == "verified":
                    await _mark_registration_paid(uid, ev["exp_course"])
                if len(items) < 40:
                    items.append({"id": r["id"], "status": ev["status"], "note": ev["auto_note"]})
        except Exception as e:
            counts["error"] += 1
            print("slip reprocess error:", r.get("id"), repr(e)[:150])

    await asyncio.gather(*[one(r) for r in batch])
    out.update({"processed": len(batch), "result": counts, "items": items,
                "left": max(0, len(todo) - min(len(todo), budget))})
    return out


def _require_slip_tools_role(admin):
    if admin.get("role") not in ("owner", "admin"):
        raise HTTPException(403, "ต้องเป็น owner/admin (เครื่องมือนี้แก้สถานะสลิปเป็นชุด)")


# ---------- คัดแยกสลิปที่ EasySlip อ่าน QR ไม่ได้: รูปที่ไม่ใช่สลิป vs สลิปที่ต้องให้คนตรวจ ----------
_TRIAGE_NOTES = ("qrcode_not_found", "slip_not_found")
_TRIAGE_REJECT_CONF = 0.8   # ตีกลับอัตโนมัติต่อเมื่อ Gemini มั่นใจว่า "ไม่ใช่สลิป" อย่างน้อยเท่านี้
_TRIAGE_SLIP_CONF = 0.55    # ถือว่า "น่าจะเป็นสลิป" (เกณฑ์เดียวกับ gate ใน webhook)
_TRIAGE_GAP_SEC = 4.5       # เว้นระหว่างคำขอ Gemini ~13 ครั้ง/นาที — รุ่นฟรีจำกัดต่อนาที ยิงรัวแล้วโดนปฏิเสธ (ตัวจำแนกคืน None)
_gemini_pace = {"last": 0.0}
_gemini_pace_lock = asyncio.Lock()


async def _paced_classify(content: bytes, mime: str):
    async with _gemini_pace_lock:   # เว้นจังหวะ "เริ่มคำขอ" (ตัวคำขอเองซ้อนกันได้)
        wait = _gemini_pace["last"] + _TRIAGE_GAP_SEC - time.time()
        if wait > 0:
            await asyncio.sleep(wait)
        _gemini_pace["last"] = time.time()
    return await _gemini_classify_slip(content, mime)


async def _triage_candidates() -> list:
    rows = await supa.select_all("slips", params={
        "select": "id,line_user_id,media_url,auto_note,ocr,created_at", "status": "eq.review",
        "order": "created_at.desc"})
    out = []
    for r in rows:
        note = r.get("auto_note") or ""
        # เฉพาะที่ EasySlip ล้มอย่างเดียว ยังไม่มีความเห็นจาก Gemini (ที่มี Gemini แล้วขึ้นต้นด้วย 🤖)
        if r.get("media_url") and any(k in note for k in _TRIAGE_NOTES) and not note.startswith("🤖"):
            out.append(r)
    return out


async def _triage_recall_check(n: int = 10, offset: int = 0) -> dict:
    """วัดความแม่นของตัวจำแนก: ให้จำแนกสลิปที่ EasySlip ยืนยันแล้ว (ของจริงแน่นอน) — ควรตอบ is_slip ทุกใบ"""
    rows = await supa.select("slips", params={
        "select": "id,media_url", "status": "eq.verified", "media_url": "not.is.null",
        "order": "created_at.desc", "limit": str(n), "offset": str(offset)})
    sem = asyncio.Semaphore(5)
    res = []
    unavailable = []

    async def one(r):
        async with sem:
            content, mime = await _fetch_image(r["media_url"])
            if not content:
                unavailable.append(r["id"])
                return
            g = await _paced_classify(content, mime)
            res.append(g)

    await asyncio.gather(*[one(r) for r in rows])
    ok = [g for g in res if g and g.get("is_slip") and (g.get("confidence") or 0) >= _TRIAGE_SLIP_CONF]
    confident_wrong = [g for g in res if g and not g.get("is_slip") and (g.get("confidence") or 0) >= _TRIAGE_REJECT_CONF]
    return {"asked": len(rows), "image_unavailable": len(unavailable),
            "checked": len(res), "recognized_as_slip": len(ok),
            "no_answer": sum(1 for g in res if not g),
            "confidently_said_not_slip": len(confident_wrong)}   # ตัวเลขนี้ต้องเป็น 0 ถึงจะปลอดภัยที่จะตีกลับอัตโนมัติ


async def _triage_note(slip_id, amt, bank, receiver, date, conf, ref, accounts) -> str:
    """หมายเหตุสำหรับสลิปที่ Gemini ว่า 'น่าจะเป็นสลิป' — บอกทุกหลักสูตรที่ยอดตรงราคา (ยอดเดียวอาจตรงหลายคอร์ส เช่น
    FC 1,499 = PC ราคาเต็ม 1,499) + เตือนถ้า ref ที่ Gemini อ่านตรงกับสลิปอื่น (เตือนอย่างเดียว ไม่เก็บลงคอลัมน์ ref)"""
    courses = []
    try:
        for a in accounts:
            for target in (a.get("price"), a.get("full_price")):
                if (amt not in (None, "") and target not in (None, "") and abs(float(amt) - float(target)) < 1
                        and a["course"] not in courses):
                    courses.append(a["course"])
    except (TypeError, ValueError):
        pass
    hint = f" · ยอดตรงราคา {'/'.join(courses)}" if courses else ""
    dup = ""
    if ref:
        ex = await supa.select("slips", params={"ref": f"eq.{ref}", "id": f"neq.{slip_id}",
                                                "select": "id,status", "limit": "1"})
        if ex:
            dup = f" · ⚠️ ref ตรงกับสลิป #{ex[0]['id']} ({ex[0]['status']}) น่าจะซ้ำ"
    return (f"🤖 Gemini อ่านได้ (EasySlip อ่าน QR ไม่ได้): ยอด {amt} · {bank or '-'}"
            f" · ผู้รับ {receiver or '-'} · {date or '-'} (มั่นใจ {round(float(conf) * 100)}%){hint}{dup} — ต้องเช็คเอง")


async def _triage_refresh_notes() -> dict:
    """สร้างหมายเหตุของสลิปที่คัดแยกไปแล้วใหม่จากผลอ่านที่เก็บไว้ (ไม่เรียก Gemini) — ใช้ตอนปรับรูปแบบหมายเหตุ"""
    rows = await supa.select_all("slips", params={
        "select": "id,ocr,status", "status": "eq.review", "ocr->>triage": "eq.true"})
    accounts = await supa.select("payment_accounts", params={"select": "course,price,full_price", "active": "eq.true"})
    n = 0
    for r in rows:
        o = r.get("ocr") or {}
        if o.get("source") != "gemini" or o.get("is_slip") is False:
            continue
        note = await _triage_note(r["id"], o.get("amount"), o.get("receiver_bank"), o.get("receiver_acc"),
                                  o.get("date"), o.get("confidence") or 0, o.get("ref"), accounts)
        await supa.update("slips", {"auto_note": note}, {"id": f"eq.{r['id']}"})
        n += 1
    return {"refreshed": n}


async def _triage_slips(apply: bool, limit: int = 25, offset: int = 0) -> dict:
    cands = await _triage_candidates()
    out = {"candidates": len(cands)}
    if not apply:
        return out
    accounts = await supa.select("payment_accounts", params={"select": "course,price,full_price", "active": "eq.true"})
    batch = cands[offset:offset + limit]
    counts = {"rejected_not_slip": 0, "annotated_slip": 0, "left_unclear": 0, "no_image": 0, "error": 0}
    items = []
    sem = asyncio.Semaphore(5)

    async def one(r):
        try:
            async with sem:
                content, mime = await _fetch_image(r["media_url"])
                if not content:
                    counts["no_image"] += 1
                    return
                g = await _paced_classify(content, mime)
            if not g:
                counts["left_unclear"] += 1
                return
            conf = float(g.get("confidence") or 0)
            pct = round(conf * 100)
            prior = r.get("auto_note") or ""
            if not g.get("is_slip") and conf >= _TRIAGE_REJECT_CONF:
                await supa.update("slips", {
                    "status": "rejected",
                    "auto_note": f"ไม่ใช่สลิปโอนเงิน (Gemini มั่นใจ {pct}%) — {prior}",
                    "ocr": {"source": "gemini", "is_slip": False, "confidence": conf, "triage": True},
                }, {"id": f"eq.{r['id']}"})
                counts["rejected_not_slip"] += 1
                decision = "rejected_not_slip"
            elif g.get("is_slip") and conf >= _TRIAGE_SLIP_CONF:
                amt = g.get("amount")
                ref = g.get("ref")
                note = await _triage_note(r["id"], amt, g.get("bank"), g.get("receiver_account"), g.get("date"),
                                          conf, ref, accounts)
                await supa.update("slips", {
                    "auto_note": note, "amount": amt, "bank": g.get("bank"),
                    "slip_date": str(g["date"]) if g.get("date") else None,
                    "ocr": {"verified": False, "source": "gemini", "confidence": conf, "amount": amt,
                            "receiver_acc": g.get("receiver_account"), "receiver_bank": g.get("bank"),
                            "ref": ref, "date": g.get("date"), "triage": True},
                }, {"id": f"eq.{r['id']}"})
                counts["annotated_slip"] += 1
                decision = "annotated_slip" + ("_dup" if "น่าจะซ้ำ" in note else "")
            else:
                counts["left_unclear"] += 1
                return
            if len(items) < 60:
                items.append({"id": r["id"], "decision": decision})
        except Exception as e:
            counts["error"] += 1
            print("slip triage error:", r.get("id"), repr(e)[:150])

    await asyncio.gather(*[one(r) for r in batch])
    # ใบที่ตัดสินไม่ได้ (Gemini ไม่ตอบ/ไม่มั่นใจ/ไม่มีรูป/error) ยังเป็นผู้เข้าข่ายอยู่ — ชุดถัดไปต้องข้ามไป ไม่งั้นหยิบใบเดิมวนไม่จบ
    skipped = counts["left_unclear"] + counts["no_image"] + counts["error"]
    out.update({"processed": len(batch), "result": counts, "items": items,
                "next_offset": offset + skipped, "left": max(0, len(cands) - offset - len(batch))})
    return out


async def _dev_commands_list(status: str) -> dict:
    params = {"select": "*", "order": "created_at.asc", "limit": "50"}
    if status in ("pending", "done", "failed"):
        params["status"] = f"eq.{status}"
    try:
        rows = await supa.select("dev_commands", params=params)
    except Exception as e:
        return {"schema_missing": True, "hint": f"ยังไม่ได้รัน migration 0021_dev_commands.sql — {e}", "commands": []}
    return {"commands": rows}


_RECEIPT_POSTBACK = "ACT_VIEW_RECEIPT"   # ปุ่ม quick reply "ดูใบเสร็จ" แนบกับข้อความยืนยันสลิป — กดแล้วตอบผ่าน reply token


async def _receipt_text(s: dict) -> str | None:
    """สร้างข้อความใบเสร็จจากข้อมูลสลิป — คืน None ถ้าปิด setting send_receipt ไว้
    ใช้ร่วมกันทั้งตอนแอดมินกดยืนยันเอง (push) และตอน user กดปุ่ม "ดูใบเสร็จ" เอง (reply, ดู _RECEIPT_POSTBACK)"""
    try:
        if await _get_setting("send_receipt", True) is False:
            return None
    except Exception:
        pass
    acc = None
    try:
        c = str(s.get("course") or "")[:2].upper()
        accts = await supa.select("payment_accounts", params={"select": "*", "active": "eq.true"})
        acc = next((a for a in accts if str(a.get("course") or "").upper().startswith(c)), None)
    except Exception:
        pass
    org = ""
    try:
        org = str(await _get_setting("receipt_org", "") or "")
    except Exception:
        pass
    lines = ["📄 ใบเสร็จรับเงิน" + (f" — {org}" if org else ""),
             f"เลขที่: R{s.get('id') or '-'}",
             f"วันที่: {str(s.get('date') or dt.date.today().isoformat())[:10]}",
             f"หลักสูตร: {s.get('course') or '-'}",
             f"จำนวนเงิน: {s.get('amount') or '-'} บาท"]
    if acc:
        lines.append(f"ชำระเข้า: {acc.get('bank')} {acc.get('account_no')} ({acc.get('account_name')})")
    if s.get("ref"):
        lines.append(f"อ้างอิง: {s['ref']}")
    lines.append("\nขอบคุณที่ชำระเงินครับ 🙏 เก็บข้อความนี้ไว้เป็นหลักฐาน")
    return "\n".join(lines)




async def _mark_registration_paid(uid: str, course_hint: str | None = None):
    """สลิป verified -> mark registration ของ user คนนั้นเป็นจ่ายแล้ว
    ระบบรองรับคนละ 1 หลักสูตรเท่านั้น -> ถ้ามี registration ที่ยังไม่จ่ายอยู่แถวเดียว mark แถวนั้นเลย
    ไม่ต้องพึ่ง course_hint (กันเคส hint เดามาผิด/เดาไม่ได้ แล้ว update ไม่โดนแถวไหนเลยแบบเงียบๆ)
    เหลือใช้ course_hint เป็นตัวช่วยแยกเฉพาะกรณี legacy ที่มีมากกว่า 1 แถว (นำเข้าจากระบบเก่าก่อนเปลี่ยนกฎ)"""
    if not uid:
        return
    try:
        unpaid = await supa.select("registrations", params={
            "line_user_id": f"eq.{uid}", "paid": "eq.false", "select": "id,course"})
        if not unpaid:
            return
        if len(unpaid) == 1:
            await supa.update("registrations", {"paid": True, "updated_at": NOW()},
                              {"id": f"eq.{unpaid[0]['id']}"})
            return
        # legacy: มากกว่า 1 แถว -> ต้องพึ่ง course_hint แยกว่าจ่ายคอร์สไหน
        params = {"line_user_id": f"eq.{uid}", "paid": "eq.false"}
        if course_hint:
            params["course"] = f"like.{course_hint.upper()}*"
        await supa.update("registrations", {"paid": True, "updated_at": NOW()}, params)
    except Exception as e:
        print("mark registration paid error:", e)


async def _enroll_automations(trigger: str, uids: list[str], ctx: dict | None = None):
    ctx = ctx or {}
    autos = await supa.select("automations", params={
        "select": "id,steps,trigger_config", "enabled": "eq.true", "trigger": f"eq.{trigger}"})
    if not autos or not uids:
        return
    rows = []
    for a in autos:
        cfg = a.get("trigger_config") or {}
        # กรองตาม trigger_config
        if trigger == "slip_verified" and cfg.get("course"):
            if str(cfg["course"]).upper() != str(ctx.get("course") or "").upper():
                continue
        if trigger == "tag_added" and cfg.get("tag"):
            if cfg["tag"] not in (ctx.get("tags") or []):
                continue
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
    if rule.get("trigger") in ("text", "fallback"):
        msgs = await _attach_course_qr(msgs)   # ผู้ใช้สอบถามเข้ามา -> แนบปุ่มดูรายละเอียดหลักสูตร
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


_gemini_ctx_cache: dict = {"text": None, "exp": 0.0}


async def _gemini_context() -> str:
    """รวมข้อมูลอ้างอิงให้ Gemini: ข้อความธุรกิจที่ตั้งเอง + ราคาคอร์ส/บัญชี + FAQ จากกฎ auto-reply
    cache 5 นาที"""
    if _gemini_ctx_cache["text"] is not None and time.time() < _gemini_ctx_cache["exp"]:
        return _gemini_ctx_cache["text"]
    parts: list[str] = []
    try:
        bi = await _get_setting("gemini_context", "")
        if bi and str(bi).strip():
            parts.append(str(bi).strip())
    except Exception:
        pass
    try:
        accts = await supa.select("payment_accounts", params={
            "select": "course,bank,account_no,account_name,price,full_price", "active": "eq.true"})
        if accts:
            lines = ["ราคาคอร์สและบัญชีโอนเงิน:"]
            for a in accts:
                lines.append(f"- คอร์ส {a['course']}: ราคา {a.get('price')} บาท (เต็ม {a.get('full_price')}) "
                             f"โอนเข้า {a.get('bank')} เลขบัญชี {a.get('account_no')} ชื่อ {a.get('account_name')}")
            parts.append("\n".join(lines))
    except Exception:
        pass
    text = "\n\n".join(parts)[:4000]
    _gemini_ctx_cache["text"] = text
    _gemini_ctx_cache["exp"] = time.time() + 300
    return text


_gemini_kb_cache: dict = {"items": None, "exp": 0.0}


async def _gemini_kb_items() -> list:
    """คลังความรู้ + FAQ จาก auto_replies — [{title, body, kw:set}] cache 5 นาที"""
    if _gemini_kb_cache["items"] is not None and time.time() < _gemini_kb_cache["exp"]:
        return _gemini_kb_cache["items"]
    items: list = []
    try:
        for a in await supa.select("kb_articles", params={
                "select": "title,body,keywords", "enabled": "eq.true", "limit": "300"}):
            items.append({"title": a["title"], "body": a["body"],
                          "kw": set((a.get("keywords") or []) + a["title"].lower().split())})
    except Exception:
        pass
    try:
        for r in await supa.select("auto_replies", params={
                "select": "keywords,messages", "enabled": "eq.true",
                "trigger": "in.(text,fallback)", "order": "priority.desc", "limit": "80"}):
            kws = [k for k in (r.get("keywords") or []) if k]
            ans = " ".join(m.get("text", "") for m in (r.get("messages") or [])
                           if isinstance(m, dict) and m.get("type") == "text" and m.get("text"))
            if kws and ans:
                items.append({"title": ", ".join(kws), "body": ans[:400],
                              "kw": set(k.lower() for k in kws)})
    except Exception:
        pass
    _gemini_kb_cache["items"] = items
    _gemini_kb_cache["exp"] = time.time() + 300
    return items


def _tok(s: str) -> set:
    return set(w for w in re.findall(r"[ก-๙a-zA-Z0-9]{2,}", (s or "").lower()))


# คำพ้องความหมายที่ลูกค้ามักใช้ต่างจากคำในคลังความรู้ — ขยายฝั่งคำถามก่อนให้คะแนน
# ช่วยให้ "เท่าไหร่/กี่บาท" เจอบทความที่เขียนว่า "ราคา" ได้ แม้คำไม่ตรงเป๊ะ
_SYN_GROUPS = [
    {"ราคา", "เท่าไหร่", "เท่าไร", "ค่าเรียน", "ค่าลงทะเบียน", "กี่บาท", "ค่าใช้จ่าย", "แพง", "ถูก"},
    {"โอน", "จ่าย", "ชำระ", "จ่ายเงิน", "ชำระเงิน", "โอนเงิน", "โอนแล้ว"},
    {"เรียน", "คอร์ส", "หลักสูตร", "คลาส", "รุ่น"},
    {"สมัคร", "ลงทะเบียน", "ลงชื่อ", "สมัครเรียน", "สมัครติว"},
    {"ผ่อน", "แบ่งจ่าย", "แบ่งชำระ", "ผ่อนชำระ", "ผ่อนได้ไหม"},
    {"ยกเลิก", "เลิก", "ขอคืนเงิน", "คืนเงิน", "ไม่เรียนแล้ว", "ไม่เอาแล้ว"},
    {"ซูม", "zoom", "ลิงก์เรียน", "ลิงค์เรียน", "ห้องเรียน", "ห้องซูม"},
    {"เอกสาร", "pdf", "ไฟล์", "สรุป", "ชีท", "เนื้อหา"},
    {"เริ่มเรียน", "เปิดเรียน", "วันเริ่ม", "วันที่เริ่ม", "ตารางเรียน", "ตาราง", "เมื่อไหร่", "วันไหน"},
    {"สลิป", "หลักฐานโอน", "ใบเสร็จ", "receipt", "สลิปโอน"},
    {"ที่อยู่", "สถานที่", "ที่ไหน", "location", "เรียนที่ไหน"},
    {"ผล", "ประกาศผล", "ผลสอบ", "ติดไหม", "ผ่านไหม"},
    # คำถามเรื่องกฎหมาย/ระเบียบจัดซื้อจัดจ้างภาครัฐ (เนื้อหาวิชาที่ติว ไม่ใช่การสมัครเรียน)
    {"เฉพาะเจาะจง", "จัดซื้อจัดจ้างโดยตรง", "เจรจาราคา", "ห้าแสน", "วงเงิน"},
    {"คัดเลือก", "วิธีคัดเลือก", "เชิญเฉพาะราย"},
    {"ประกาศเชิญชวน", "e-bidding", "อีบิดดิ้ง", "ประกวดราคา", "e-market", "อีมาร์เก็ต", "ตลาดอิเล็กทรอนิกส์"},
    {"อุทธรณ์", "ร้องเรียน", "ไม่เป็นธรรม", "โต้แย้งผล", "ค้านผล"},
    {"ฮั้ว", "ฮั้วประมูล", "สมยอมราคา", "ทุจริตจัดซื้อ"},
    {"ผู้ทิ้งงาน", "บัญชีดำ", "แบล็กลิสต์", "ถูกตัดสิทธิ"},
    {"ราคากลาง", "price standard", "ประมาณราคา"},
    {"หลักประกันสัญญา", "แบงก์การันตี", "bank guarantee", "หลักค้ำประกัน"},
    {"มาตรา", "ข้อกฎหมาย", "อ้างอิงกฎหมาย", "ระเบียบข้อไหน"},
    {"พรบ", "พระราชบัญญัติ", "กฎหมายจัดซื้อ"},
]
_SYN_MAP: dict = {}
for _grp in _SYN_GROUPS:
    for _w in _grp:
        _SYN_MAP.setdefault(_w, set()).update(_grp)


def _expand_syn(tokens: set) -> set:
    out = set(tokens)
    for t in tokens:
        out |= _SYN_MAP.get(t, set())
    return out


async def _gemini_retrieve(question: str, k: int = 6) -> str:
    """ดึงบทความ KB/FAQ ที่เกี่ยวกับคำถามนี้มากสุด k อัน (ขยายคำพ้องความหมายฝั่งคำถามก่อนให้คะแนน)"""
    items = await _gemini_kb_items()
    if not items:
        return ""
    qt = _expand_syn(_tok(question))
    scored = []
    for it in items:
        body_t = _tok(it["body"])
        score = len(qt & it["kw"]) * 3 + len(qt & _tok(it["title"])) * 2 + len(qt & body_t)
        if score:
            scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    top = scored[:k]
    if not top:
        return ""
    return "ข้อมูลที่เกี่ยวข้อง (ใช้ตอบ):\n" + "\n\n".join(
        f"[{it['title']}]\n{it['body'][:900]}" for _s, it in top)


# tool schema แบบ Anthropic (name/description/input_schema) — ใช้กับ Claude ผ่าน _gemini_answer
# tool schema แบบ Anthropic (name/description/input_schema) — ใช้กับ Claude
_CLAUDE_TOOLS = [
    {
        "name": "get_my_account",
        "description": "ดูข้อมูลการลงทะเบียนเรียนและการชำระเงินของผู้ใช้ที่กำลังคุยอยู่ "
                       "(หลักสูตรที่ลงทะเบียน, จ่ายแล้ว/ยัง, สถานะสลิปล่าสุด)",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_course_details",
        "description": "ดูรายละเอียดหลักสูตร: ราคา ราคาเต็ม ธนาคาร เลขบัญชี ชื่อบัญชีสำหรับโอนเงิน",
        "input_schema": {"type": "object", "properties": {
            "course": {"type": "string", "description": "รหัสหลักสูตร เช่น FC IC PC AC"}}, "required": ["course"]},
    },
    {
        "name": "get_class_info",
        "description": "ดูข้อมูลคลาส/รุ่นของหลักสูตร: วันเริ่มเรียน ตารางเรียน ลิงก์ Zoom ลิงก์เอกสาร",
        "input_schema": {"type": "object", "properties": {
            "course": {"type": "string", "description": "รหัสหลักสูตร เช่น FC IC PC"}}, "required": ["course"]},
    },
    {
        "name": "search_knowledge",
        "description": "ค้นหาข้อมูลเพิ่มเติมในคลังความรู้ของเพจ ใช้เมื่อยังตอบคำถามไม่ได้จากข้อมูลที่มี",
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "คำค้น"}}, "required": ["query"]},
    },
    {
        "name": "note_interest",
        "description": "บันทึกว่าผู้ใช้สนใจหลักสูตรนี้ (ยังไม่ได้ลงทะเบียน) เรียกเมื่อผู้ใช้แสดงความสนใจอยากเรียน/สมัคร",
        "input_schema": {"type": "object", "properties": {
            "course": {"type": "string", "description": "รหัสหลักสูตรที่สนใจ"}}, "required": ["course"]},
    },
    {
        "name": "escalate_to_admin",
        "description": "เรียกแอดมินมาช่วย — ใช้เมื่อผู้ใช้ต้องการคุยกับคน, ร้องเรียน, หรือคำถามที่ต้องให้คนตัดสินใจ",
        "input_schema": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "สรุปสั้น ๆ ว่าผู้ใช้ต้องการอะไร"}}, "required": ["reason"]},
    },
]

# tool schema แบบ Gemini (functionDeclarations/parameters) — เนื้อหาเดียวกับ _CLAUDE_TOOLS แค่โครง JSON ต่างกัน
_GOOGLE_TOOLS = [{"functionDeclarations": [
    {"name": t["name"], "description": t["description"],
     "parameters": t["input_schema"]} for t in _CLAUDE_TOOLS
]}]

_gemini_escalations: dict = {}   # uid -> reason (อ่านหลัง reply เพื่อ bump unread/tag)

# คำที่บ่งชี้ว่าควรส่งต่อคนโดยไม่พึ่งดุลพินิจโมเดลอย่างเดียว (safety net ธุรกิจ)
_URGENT_KW = ("ร้องเรียน", "ไม่พอใจ", "โกง", "หลอกลวง", "ฟ้อง", "แจ้งความ", "แจ้งจับ", "ทนาย",
              "ขอเงินคืน", "คืนเงิน", "เร่งด่วน", "ด่วนมาก", "ผิดพลาดร้ายแรง", "เสียหาย")


def _is_urgent(text: str) -> bool:
    low = (text or "").lower()
    return any(k in low for k in _URGENT_KW)


async def _gemini_tool_exec(name: str, args: dict, uid: str) -> dict:
    try:
        if name == "get_my_account":
            regs = await supa.select("registrations", params={
                "line_user_id": f"eq.{uid}", "select": "course,course_raw,paid,approved"})
            slips = await supa.select("slips", params={
                "line_user_id": f"eq.{uid}", "select": "status,amount,expected_course,auto_note,created_at",
                "order": "created_at.desc", "limit": "3"})
            if not regs and not slips:
                return {"note": "ยังไม่พบข้อมูลการลงทะเบียนของผู้ใช้คนนี้ในระบบ"}
            return {
                "registrations": [{"course": r.get("course_raw") or r.get("course"),
                                   "paid": bool(r.get("paid")),
                                   "approved": r.get("approved")} for r in regs],
                "recent_slips": [{"status": s.get("status"), "amount": s.get("amount"),
                                  "course": s.get("expected_course"), "note": s.get("auto_note"),
                                  "date": (s.get("created_at") or "")[:16]} for s in slips],
            }
        if name == "get_course_details":
            c = re.sub(r"[^A-Za-z]", "", str(args.get("course") or "")).upper()[:2]
            accts = await supa.select("payment_accounts", params={"select": "*", "active": "eq.true"})
            m = next((a for a in accts if str(a.get("course") or "").upper().startswith(c)), None)
            if not m:
                return {"error": f"ไม่พบหลักสูตร {args.get('course')}"}
            return {"course": m["course"], "price": m.get("price"), "full_price": m.get("full_price"),
                    "bank": m.get("bank"), "account_no": m.get("account_no"), "account_name": m.get("account_name")}
        if name == "get_class_info":
            c = re.sub(r"[^A-Za-z]", "", str(args.get("course") or "")).upper()[:2]
            cls = await supa.select("classes", params={
                "select": "name,course,cohort,start_date,schedule,zoom_url,materials_url,status,capacity",
                "course": f"like.{c}*", "status": "in.(open,running)",
                "order": "start_date.asc", "limit": "5"})
            if not cls:
                return {"note": f"ยังไม่มีคลาส {args.get('course')} ที่เปิดอยู่ตอนนี้"}
            return {"classes": cls}
        if name == "search_knowledge":
            snip = await _gemini_retrieve(str(args.get("query") or ""), k=5)
            return {"result": snip or "ไม่พบข้อมูลที่เกี่ยวข้องในคลังความรู้"}
        if name == "note_interest":
            course = re.sub(r"[^A-Za-z0-9]", "", str(args.get("course") or "")).upper()
            try:
                u = await supa.select("line_users", params={
                    "select": "stage,tags", "line_user_id": f"eq.{uid}", "limit": "1"})
                cur = u[0] if u else {}
                patch = {"tags": sorted(set(cur.get("tags") or []) | {f"สนใจ-{course}" if course else "สนใจ"}),
                         "updated_at": NOW()}
                if not cur.get("stage") or cur.get("stage") == "lead":
                    patch["stage"] = "interested"
                    patch["stage_at"] = NOW()
                await supa.update("line_users", patch, {"line_user_id": f"eq.{uid}"})
            except Exception as e:
                print("note_interest err:", e)
            return {"ok": True}
        if name == "escalate_to_admin":
            _gemini_escalations[uid] = str(args.get("reason") or "ผู้ใช้ขอคุยกับแอดมิน")[:200]
            return {"ok": True, "message": "แจ้งแอดมินแล้ว จะรีบติดต่อกลับ"}
    except Exception as e:
        return {"error": str(e)[:120]}
    return {"error": "unknown tool"}


def _ai_sys_text(user_facts: str, context: str) -> str:
    sys_text = (
        "คุณเป็นผู้ช่วยของเพจติวสอบ ตอบสมาชิกทางไลน์ เป็นภาษาไทย เป็นกันเอง กระชับ ไม่เกิน 4-5 ประโยค "
        "ห้ามขึ้นต้นว่า 'สวัสดีครับ/ค่ะ' ทุกครั้ง (คุยต่อเนื่องอยู่) "
        "ห้ามใช้ markdown เช่น **ตัวหนา** #หัวข้อ หรือ bullet ที่ขึ้นต้นด้วย * เพราะไลน์แสดงตัวอักษรดิบ ให้เขียนเป็นประโยคปกติหรือขึ้นบรรทัดใหม่แทน "
        "ตอบตามข้อมูลอ้างอิง/ผลลัพธ์จากเครื่องมือเท่านั้น ห้ามเดาราคา วันที่ หรือสถานะที่ไม่มีในข้อมูลที่ได้รับ "
        "เมื่อผู้ใช้ถามเรื่องการลงทะเบียน/การจ่ายเงิน/สลิปของตัวเอง ให้เรียก get_my_account ก่อนตอบเสมอ "
        "ถ้าเครื่องมือบอกว่ายังไม่พบข้อมูล ให้ขอชื่อ-เบอร์โทรที่ใช้ตอนสมัครเพื่อส่งต่อแอดมินตรวจสอบ ห้ามเดาว่าจ่ายแล้วหรือยัง "
        "เมื่อถามราคา/บัญชีโอนเงินของหลักสูตร ให้เรียก get_course_details "
        "เมื่อถามวันเริ่มเรียน/ตารางเรียน/ลิงก์ซูมของคลาส ให้เรียก get_class_info "
        "ถ้าผู้ใช้ขอคุยกับคน/ร้องเรียน/แสดงความไม่พอใจ/เรื่องเร่งด่วน/เรื่องที่ต้องให้คนตัดสิน ให้เรียก escalate_to_admin ทันทีโดยไม่ต้องพยายามแก้ปัญหาเอง "
        "ถ้าไม่มีข้อมูลและเครื่องมือช่วยไม่ได้ ให้บอกตรง ๆ ว่าไม่แน่ใจ แนะนำพิมพ์ 'ติดต่อแอดมิน' ห้ามแต่งคำตอบขึ้นเอง\n\n"
        "เมื่อตอบคำถามเกี่ยวกับกฎหมาย/ระเบียบจัดซื้อจัดจ้างภาครัฐ (เช่น วิธีจัดซื้อจัดจ้าง เกณฑ์วงเงิน สัญญา การอุทธรณ์ บทลงโทษ): "
        "ให้ใช้เฉพาะเนื้อหาที่มีในข้อมูลอ้างอิงเท่านั้น ถ้าบทความมีบรรทัด 'อ้างอิง กฎหมาย:' ให้คัดลอกมาตรา/ข้อ/ชื่อกฎหมายนั้นแนบท้ายคำตอบเสมอ เช่น "
        "'(อ้างอิง: มาตรา 56 วรรคหนึ่ง (2)(ข) แห่ง พ.ร.บ.จัดซื้อจัดจ้างฯ 2560)' ห้ามคิดเลขมาตราขึ้นเองหรือเดามาตราที่ไม่มีในข้อมูลอ้างอิงเด็ดขาด "
        "ถ้าค้นไม่เจอมาตราที่ตรงคำถาม ให้ตอบเท่าที่มีแล้วบอกว่าไม่พบเลขมาตราที่แน่ชัด แนะนำให้ตรวจกับตัวบทฉบับเต็มหรือถามแอดมิน "
        "ปิดท้ายคำตอบเชิงกฎหมายทุกครั้งด้วยประโยคสั้น ๆ ว่ากฎหมาย/ระเบียบอาจมีการแก้ไขเพิ่มเติมภายหลัง ควรตรวจสอบฉบับล่าสุดก่อนใช้ตอบข้อสอบจริง\n\n"
        "ตัวอย่างคำตอบที่ดี — ถาม 'ราคาคอร์สเท่าไหร่': เรียก get_course_details ก่อน แล้วตอบ "
        "'คอร์ส FC ราคา 1,499 บาทครับ โอนเข้าธนาคารกรุงเทพ เลขบัญชี 080-0-154320 ชื่อบัญชี ธีรภัทร์ นุ้ยเล็ก "
        "โอนแล้วส่งสลิปแจ้งได้เลยครับ' (สั้น ตรงคำถาม มีตัวเลขจริงจากเครื่องมือ ไม่มี markdown)\n"
        "ตัวอย่างคำตอบที่ไม่ดี ห้ามทำแบบนี้: '**คอร์ส FC** ราคาประมาณ 1,500 บาทครับ ลองสอบถามแอดมินอีกทีนะครับ' "
        "(เดาราคาโดยไม่เรียกเครื่องมือ + มี markdown + ตอบกำกวมทั้งที่มีเครื่องมือหาคำตอบชัดเจนได้)")
    if user_facts:
        sys_text += f"\n\nข้อมูลผู้ใช้ที่กำลังคุย: {user_facts}"
    if context:
        sys_text += "\n\n=== ข้อมูลอ้างอิง ===\n" + context
    return sys_text


async def _claude_answer(question: str, temperature: float = 0.7, context: str = "",
                         history: list | None = None, uid: str | None = None,
                         user_facts: str = "") -> str | None:
    """ตอบด้วย Claude (Anthropic) — ดู _gemini_answer (dispatcher) สำหรับคำอธิบายเต็ม"""
    if not ANTHROPIC_API_KEY or not question.strip():
        return None
    sys_text = _ai_sys_text(user_facts, context)
    messages: list = []
    for m in (history or [])[-8:]:
        role = "assistant" if m["role"] in ("model", "assistant") else "user"
        messages.append({"role": role, "content": m["text"][:800]})
    messages.append({"role": "user", "content": question[:2000]})

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=25)
    kwargs = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 1024,
        "temperature": max(0.0, min(1.0, temperature if temperature is not None else 0.7)),
        "system": sys_text,
        "messages": messages,
    }
    if uid:
        kwargs["tools"] = _CLAUDE_TOOLS

    def _text_of(resp):
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    try:
        last_text = ""
        for _round in range(5):
            resp = await client.messages.create(**kwargs)
            txt = _text_of(resp)
            if txt:
                last_text = txt
            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls:
                if txt:
                    return txt
                break  # จบแต่ไม่มีข้อความ -> ลองอีกรอบไม่ใช้ tool
            kwargs["messages"].append({"role": "assistant", "content": resp.content})
            tool_results = []
            for tu in calls:
                res = await _gemini_tool_exec(tu.name, tu.input or {}, uid or "")
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id,
                                     "content": json.dumps(res, ensure_ascii=False)})
            kwargs["messages"].append({"role": "user", "content": tool_results})

        if last_text:
            return last_text
        # รอบสุดท้าย: บังคับให้ตอบเป็นข้อความ ไม่มี tool
        kwargs.pop("tools", None)
        kwargs["messages"].append({"role": "user", "content": "สรุปคำตอบเป็นข้อความสั้น ๆ ให้ลูกค้าเลย"})
        resp = await client.messages.create(**kwargs)
        return _text_of(resp) or None
    except anthropic.APIStatusError as e:
        print("claude http error:", e.status_code, str(e.message)[:400])
        return None
    except Exception as e:
        print("claude error:", repr(e))
        return None


async def _google_answer(question: str, temperature: float = 0.7, context: str = "",
                         history: list | None = None, uid: str | None = None,
                         user_facts: str = "") -> str | None:
    """ตอบด้วย Gemini (Google) — ดู _gemini_answer (dispatcher) สำหรับคำอธิบายเต็ม"""
    if not GEMINI_API_KEY or not question.strip():
        return None
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    sys_text = _ai_sys_text(user_facts, context)

    contents: list = []
    for m in (history or [])[-8:]:
        role = "model" if m["role"] in ("model", "assistant") else "user"
        contents.append({"role": role, "parts": [{"text": m["text"][:800]}]})
    contents.append({"role": "user", "parts": [{"text": question[:2000]}]})

    body = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": sys_text}]},
        "generationConfig": {
            "maxOutputTokens": 8192,   # กันโมเดล thinking กินโควตาจนไม่เหลือให้ตอบ
            "temperature": max(0.0, min(2.0, temperature if temperature is not None else 0.7)),
        },
    }
    if uid:
        body["tools"] = _GOOGLE_TOOLS

    def _text_of(cand):
        parts = (cand.get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()

    try:
        async with httpx.AsyncClient(timeout=25) as c:
            last_text = ""
            for _round in range(5):
                r = await c.post(url, json=body)
                j = r.json()
                if r.status_code != 200:
                    print("gemini http error:", r.status_code, str(j)[:400])
                    return None
                cand = (j.get("candidates") or [{}])[0]
                parts = (cand.get("content") or {}).get("parts") or []
                txt = _text_of(cand)
                if txt:
                    last_text = txt
                calls = [p["functionCall"] for p in parts if isinstance(p, dict) and p.get("functionCall")]
                if not calls:
                    if txt:
                        return txt
                    break  # จบแต่ไม่มีข้อความ -> ลองอีกรอบไม่ใช้ tool
                body["contents"].append({"role": "model", "parts": parts})
                fresp = []
                for fc in calls:
                    res = await _gemini_tool_exec(fc.get("name", ""), fc.get("args") or {}, uid or "")
                    fresp.append({"functionResponse": {"name": fc.get("name", ""), "response": {"result": res}}})
                body["contents"].append({"role": "user", "parts": fresp})

            if last_text:
                return last_text
            body.pop("tools", None)
            body["contents"].append({"role": "user", "parts": [{"text": "สรุปคำตอบเป็นข้อความสั้น ๆ ให้ลูกค้าเลย"}]})
            r = await c.post(url, json=body)
            if r.status_code == 200:
                return _text_of((r.json().get("candidates") or [{}])[0]) or None
        return None
    except Exception as e:
        print("gemini error:", repr(e))
        return None


async def _gemini_answer(question: str, temperature: float = 0.7, context: str = "",
                         history: list | None = None, uid: str | None = None,
                         user_facts: str = "") -> str | None:
    """ตอบคำถาม + ประวัติการคุย + เครื่องมือดูข้อมูลบัญชี/หลักสูตร — คืน None ถ้า error/ว่าง
    เลือกผู้ให้บริการอัตโนมัติ: Claude ก่อนถ้ามี ANTHROPIC_API_KEY ไม่งั้นใช้ Gemini ถ้ามี GEMINI_API_KEY"""
    if ANTHROPIC_API_KEY:
        return await _claude_answer(question, temperature, context, history, uid, user_facts)
    if GEMINI_API_KEY:
        return await _google_answer(question, temperature, context, history, uid, user_facts)
    return None


def _norm_question(t: str) -> str:
    """ย่อข้อความให้จับกลุ่มคำถามซ้ำได้ (ตัดเว้นวรรค/ตัวเลข/คำลงท้าย/เครื่องหมาย)"""
    t = re.sub(r"[\d\s\W_]+", "", (t or "").lower())
    return re.sub(r"(ครับ|ค่ะ|คะ|นะครับ|นะคะ|นะ|จ้า|จ๊ะ)$", "", t)[:60]


async def _ai_baseline(days: int = 30) -> dict:
    """วัดว่าตอนนี้ 'ใครตอบลูกค้า' — กฎ/AI/แอดมิน — และมีคำถามอะไรซ้ำบ่อย (ฐานตัวเลขสำหรับวัดว่า AI เก่งขึ้นจริงไหม)
    ตัวตอบ: กฎ = by auto/postback/automation · AI = by gemini · แอดมิน = by เป็น LINE userId (U...) · ข้ามโน้ตระบบ"""
    rows = await supa.select_all("messages", params={
        "select": "line_user_id,direction,by,msg_type,text,created_at",
        "created_at": f"gte.{_iso_ago(days=days)}", "order": "created_at.asc"})

    def kind(r):
        b = r.get("by") or ""
        if b == "gemini":
            return "ai"
        if b in ("auto", "postback", "automation"):
            return "rule"
        if b in ("user", "system", ""):
            return None
        return "admin"

    def ts(r):
        return dt.datetime.fromisoformat(r["created_at"])

    threads: dict[str, list] = {}
    for r in rows:
        threads.setdefault(r["line_user_id"], []).append(r)

    first = {"rule": 0, "ai": 0, "admin_fast": 0, "admin_late": 0, "none": 0}
    bot_then_human = {"rule": 0, "ai": 0}
    bot_only = {"rule": 0, "ai": 0}
    questions: dict[str, list] = {}
    per_day: dict[str, dict] = {}
    n_in = 0
    admin_out = 0
    users_in: set = set()

    def day(r):
        return r["created_at"][:10]

    for uid, th in threads.items():
        for i, r in enumerate(th):
            k = kind(r)
            d = per_day.setdefault(day(r), {"in": 0, "rule": 0, "ai": 0, "admin": 0})
            if r["direction"] == "out" and k:
                d[k] += 1
                admin_out += (k == "admin")
            if not (r["direction"] == "in" and r.get("msg_type") in (None, "text") and (r.get("text") or "").strip()):
                continue
            n_in += 1
            d["in"] += 1
            users_in.add(uid)
            nq = _norm_question(r["text"])
            if len(nq) >= 3:
                questions.setdefault(nq, []).append((r["text"].strip()[:60]))
            t0 = ts(r)
            resp = next((x for x in th[i + 1:] if x["direction"] == "out" and kind(x)), None)
            if not resp:
                first["none"] += 1
                continue
            gap = (ts(resp) - t0).total_seconds()
            rk = kind(resp)
            if rk == "admin":
                first["admin_fast" if gap <= 180 else "admin_late"] += 1
                continue
            if gap > 180:
                first["none"] += 1
                continue
            first[rk] += 1
            human_after = any(x["direction"] == "out" and kind(x) == "admin" and 0 < (ts(x) - ts(resp)).total_seconds() <= 86400
                              for x in th[i + 1:])
            (bot_then_human if human_after else bot_only)[rk] += 1

    repeated = sorted(((len(v), v[0]) for v in questions.values() if len(v) >= 3), reverse=True)[:25]
    try:
        gaps = await supa.count("operations", {"action": "like.gemini.kb_gap*", "created_at": f"gte.{_iso_ago(days=days)}"})
    except Exception:
        gaps = None
    ndays = max(1, len(per_day))
    answered_by_bot = first["rule"] + first["ai"]
    return {
        "days": days, "inbound_text": n_in, "users": len(users_in), "inbound_per_day": round(n_in / ndays, 1),
        "first_responder": first,
        "bot_first_answer_kept": {"rule": bot_only["rule"], "ai": bot_only["ai"]},
        "bot_first_then_human_followed_up": {"rule": bot_then_human["rule"], "ai": bot_then_human["ai"]},
        "admin_messages": admin_out, "admin_messages_per_day": round(admin_out / ndays, 1),
        "bot_answer_share_pct": round(answered_by_bot * 100 / n_in, 1) if n_in else None,
        "kb_gaps_logged": gaps,
        "top_repeated_questions": [{"count": c, "example": q} for c, q in repeated],
        "last_14_days": {k: per_day[k] for k in sorted(per_day)[-14:]},
    }


async def _gemini_enabled_menu_ids() -> set:
    """rich_menu_id ทั้งหมดที่เปิด Gemini/AI (gemini_enabled=true หรือชื่อตรง GEMINI_TRIGGER_MENU_NAME)"""
    if not (ANTHROPIC_API_KEY or GEMINI_API_KEY):
        return set()
    ids: set = set()
    try:
        for m in await supa.select("rich_menus", params={
                "select": "rich_menu_id", "gemini_enabled": "eq.true"}):
            ids.add(m["rich_menu_id"])
    except Exception as e:
        print("gemini menu ids error:", e)
    if GEMINI_TRIGGER_MENU_NAME:
        try:
            for m in await supa.select("rich_menus", params={
                    "select": "rich_menu_id", "name": f"eq.{GEMINI_TRIGGER_MENU_NAME}"}):
                ids.add(m["rich_menu_id"])
        except Exception:
            pass
    return ids


async def _handle_gemini_replies(events: list) -> set:
    """ตอบข้อความที่ไม่ตรงกฎไหน ด้วย AI (Claude หรือ Gemini แล้วแต่ตั้งคีย์ไหนไว้) — เรียกหลัง _handle_auto_replies แล้ว
    (events ถูกกรองมาแล้วว่าเป็น text ของ user บนเมนู AI ที่ยังไม่มีใครตอบ)"""
    if not (ANTHROPIC_API_KEY or GEMINI_API_KEY):
        return set()
    text_events = [e for e in events if e.get("type") == "message"
                   and e.get("message", {}).get("type") == "text"
                   and e.get("replyToken") and e.get("source", {}).get("userId")]
    if not text_events:
        return set()

    # menu_temp: {rich_menu_id: temperature} เฉพาะเมนูที่เปิด gemini_enabled ไว้
    menu_temp: dict[str, float] = {}
    try:
        menus = await supa.select("rich_menus", params={
            "select": "rich_menu_id,gemini_temperature", "gemini_enabled": "eq.true"})
        for m in menus:
            try:
                menu_temp[m["rich_menu_id"]] = float(m.get("gemini_temperature") or 0.7)
            except (TypeError, ValueError):
                menu_temp[m["rich_menu_id"]] = 0.7
    except Exception as e:
        print("gemini: read rich_menus error:", e)

    # backward-compat: เมนูที่ชื่อตรง GEMINI_TRIGGER_MENU_NAME (ตั้งค่าเก่าแบบ env var) ก็ยังนับด้วย
    if GEMINI_TRIGGER_MENU_NAME:
        try:
            legacy = await supa.select("rich_menus", params={
                "select": "rich_menu_id", "name": f"eq.{GEMINI_TRIGGER_MENU_NAME}"})
            for m in legacy:
                menu_temp.setdefault(m["rich_menu_id"], 0.7)
        except Exception:
            pass

    if not menu_temp:
        return set()

    ctx = await _gemini_context()
    _gemini_escalations.clear()
    handled: set = set()
    out_msgs = []

    # ---- โควต้า AI ต่อวัน (กันโดน 429 กลางบทสนทนา + เตือนแอดมินก่อนหมดจริง) ----
    # ai_daily_limit ตั้งได้ในหน้าแอดมิน (0 = ไม่จำกัด) — นับจากข้อความที่ AI ตอบไปแล้ววันนี้ (by=gemini)
    ai_limit = 0
    ai_used_today = 0
    try:
        ai_limit = int(await _get_setting("ai_daily_limit", 0) or 0)
        if ai_limit > 0:
            today0 = dt.date.today().isoformat()
            ai_used_today = await supa.count("messages", {"by": "eq.gemini", "created_at": f"gte.{today0}"})
            if ai_used_today >= int(ai_limit * 0.8):
                await alert_admin("⚠️ โควต้า AI ใกล้เต็ม",
                                  f"ตอบไปแล้ว {ai_used_today}/{ai_limit} ครั้งวันนี้ — เกินขีดจะขึ้นข้อความ 'รอแอดมิน' แทน",
                                  throttle_key=f"ai_quota_{today0}")
    except Exception as e:
        print("ai quota check error:", e)

    for e in text_events:
        uid = e["source"]["userId"]
        if uid in handled:
            continue
        try:
            rid = await line.user_richmenu_get(uid)
        except Exception:
            rid = None
        if rid not in menu_temp:
            continue
        # ข้อความรับทราบ/ขอบคุณ/ปุ่มระบบ ไม่ต้องให้ AI ตอบ (ไม่เสียโควต้า ไม่ตอบซ้ำซ้อนให้ดูเป็นบอท)
        if _norm_question(e["message"].get("text") or "") in _TEACH_NOISE_PLAIN:
            continue
        # เช็คหลังตรวจสิทธิ์เมนู: จ่ายค่า DB เฉพาะข้อความที่ AI จะตอนจริง (ไม่ใช่ทุกข้อความของทุกคน)
        if not await _rate_ok_db(f"gemini:{uid}", 6, 60):  # กันสแปม/ต้นทุนบานปลาย
            continue
        question = e["message"].get("text") or ""

        # ประวัติการคุย 8 ข้อความล่าสุด (in=user, out=model) + ข้อมูลผู้ใช้
        history, user_facts = [], ""
        try:
            recent = await supa.select("messages", params={
                "select": "direction,by,text,msg_type", "line_user_id": f"eq.{uid}",
                "order": "created_at.desc", "limit": "9"})
            for m in reversed(recent):
                txt = (m.get("text") or "").strip()
                if not txt or m.get("msg_type") not in (None, "text"):
                    continue
                role = "user" if m.get("direction") == "in" else "model"
                if role == "model" and m.get("by") == "gemini" and txt == "":
                    continue
                history.append({"role": role, "text": txt})
            history = history[:-1] if history and history[-1]["role"] == "user" and history[-1]["text"] == question.strip() else history
            prof = await line.get_profile(uid)
            regs = await supa.select("registrations", params={
                "line_user_id": f"eq.{uid}", "select": "course_raw,course,paid", "limit": "10"})
            facts = []
            if prof and prof.get("displayName"):
                facts.append(f"ชื่อ LINE: {prof['displayName']}")
            if regs:
                facts.append("ลงทะเบียน: " + ", ".join(
                    f"{r.get('course_raw') or r.get('course')}({'จ่ายแล้ว' if r.get('paid') else 'ค้างจ่าย'})" for r in regs))
            user_facts = " · ".join(facts)
        except Exception as ex:
            print("gemini history/facts error:", ex)

        try:
            kb = await _gemini_retrieve(question)
        except Exception:
            kb = ""
        if not kb:
            # ไม่เจอบทความ/FAQ ที่เกี่ยวข้องเลย -> บันทึกไว้ให้แอดมินเห็นว่าควรเพิ่มความรู้เรื่องอะไร
            # เก็บ uid ด้วย -> ใช้จับคู่กับตอนแอดมินตอบเองทีหลัง (ดู inbox_send) เพื่อร่างบทความ KB ให้อัตโนมัติ
            try:
                await supa.insert("operations", {"actor": "gemini", "action": "gemini.kb_gap",
                                                 "params": {"q": question[:200], "uid": uid}, "status": "ok"})
            except Exception:
                pass
        full_ctx = (ctx + ("\n\n" + kb if kb else "")).strip()
        if ai_limit > 0 and ai_used_today >= ai_limit:
            # ชนโควต้าที่ตั้งไว้เอง -> ไม่ยิง API เลย (กันรอ error 429 เปล่าๆ) ตกไปข้อความ "รอแอดมิน" ทันที
            answer = None
        else:
            answer = await _gemini_answer(question, menu_temp[rid], context=full_ctx,
                                          history=history, uid=uid, user_facts=user_facts)
        gemini_ok = bool(answer)
        if not answer:
            # AI ตอบไม่ได้ (quota/error) -> อย่าปล่อยเงียบ: ข้อความค้างไว้ + ให้แอดมินเห็น
            answer = "ได้รับข้อความแล้วครับ 🙏 เดี๋ยวแอดมินมาตอบให้นะครับ"
        else:
            ai_used_today += 1  # นับต่อในแบทช์เดียวกัน กันยิงเกิน limit ถ้าคนถามพร้อมกันหลายคน
        if _is_urgent(question) and uid not in _gemini_escalations:
            # safety net: ข้อความมีลักษณะร้องเรียน/เร่งด่วน -> ส่งต่อแอดมินเสมอ ไม่ปล่อยให้โมเดลตัดสินใจเองอย่างเดียว
            _gemini_escalations[uid] = f"ข้อความอาจร้องเรียน/เร่งด่วน: {question[:100]}"
        code, _ = await line.reply(e["replyToken"], await _attach_course_qr([{"type": "text", "text": answer[:4900]}]))
        if code == 200:
            handled.add(uid)
            out_msgs.append({"line_user_id": uid, "direction": "out", "by": "gemini",
                             "msg_type": "text", "text": answer,
                             "payload": {"question": question,
                                        "model": ANTHROPIC_MODEL if ANTHROPIC_API_KEY else GEMINI_MODEL}})
            # Gemini เรียก escalate_to_admin หรือ AI ตอบไม่ได้ -> bump unread + tag ให้แอดมินเห็น
            if uid in _gemini_escalations or not gemini_ok:
                try:
                    ex = await supa.select("line_users", params={
                        "select": "unread,tags", "line_user_id": f"eq.{uid}", "limit": "1"})
                    cur = ex[0] if ex else {}
                    await supa.update("line_users", {
                        "unread": (cur.get("unread") or 0) + 1,
                        "tags": sorted(set(cur.get("tags") or []) | {"รอแอดมิน"}),
                        "updated_at": NOW(),
                    }, {"line_user_id": f"eq.{uid}"})
                    reason = _gemini_escalations.get(uid) or f"AI ตอบไม่ได้: {question[:80]}"
                    await alert_admin("🙋 ลูกค้ารอแอดมิน", f"{user_facts or uid[:12]}\n{reason}",
                                      throttle_key=f"esc_{uid}")
                except Exception as ex2:
                    print("escalation error:", ex2)
    if out_msgs:
        try:
            await supa.insert("messages", out_msgs)
        except Exception:
            pass
    return handled


async def _handle_auto_replies(events: list, gemini_uids: set = frozenset()) -> set:
    """ตอบกฎ auto-reply / postback / ต้อนรับ. คืน set ของ uid ที่ตอบไปแล้ว.
    user ใน gemini_uids: ข้ามกฎ fallback (ปล่อยให้ Gemini ตอบแทน) — กฎอื่น ๆ ทำงานปกติ"""
    repliable = [e for e in events if e.get("replyToken") and e.get("type") in
                 ("message", "follow", "postback", "beacon")]
    if not repliable:
        return set()
    rules = await supa.select("auto_replies", params={
        "select": "*", "enabled": "eq.true", "order": "priority.desc,id.asc", "limit": "300",
    })
    for r in rules:
        r.setdefault("trigger", "text")
    has_course_pb = any(e.get("type") == "postback" and
                        (e.get("postback", {}).get("data") or "").startswith(_COURSE_QR_PREFIX) for e in repliable)
    if not rules and not has_course_pb:
        return set()

    # หา user ที่ปิด auto-reply ไว้ (แอดมินกำลังคุยเอง)
    uids = {e.get("source", {}).get("userId") for e in repliable if e.get("source", {}).get("userId")}
    paused = set()
    if uids:
        rows = await supa.select("line_users", params={
            "select": "line_user_id,auto_reply_paused", "line_user_id": f"in.({','.join(uids)})",
            "auto_reply_paused": "eq.true", "limit": "1000"})
        paused = {r["line_user_id"] for r in rows}

    # postback actions (routing table exact/prefix) — เช็คก่อน auto_replies
    pb_actions = []
    if any(e["type"] == "postback" for e in repliable):
        pb_actions = await supa.select("postback_actions", params={
            "select": "*", "enabled": "eq.true", "order": "match.asc"})

    def _pick_postback(data: str):
        for pa in pb_actions:
            if pa["match"] == "prefix" and data.startswith(pa["data"]):
                return pa
            if pa["match"] == "exact" and data == pa["data"]:
                return pa
        return None

    # รูปภาพ: ให้ตัวจัดการรูป (_handle_slips) ดูรูปก่อนแล้วตอบเอง — ไม่ตอบด้วยกฎ "ได้รับรูป/สลิปแล้ว" ทันที
    skip_images = False
    if any(e.get("type") == "message" and e.get("message", {}).get("type") == "image" for e in repliable):
        skip_images = await _image_ai_on()

    name_cache: dict[str, str] = {}
    async def name_of(uid):
        if not uid:
            return None
        if uid not in name_cache:
            p = await line.get_profile(uid)
            name_cache[uid] = (p or {}).get("displayName") or "เพื่อน"
        return name_cache[uid]

    out_msgs = []
    replied_uids: set[str] = set()   # กันตอบซ้ำใน batch เดียว (เช่น ปุ่ม rich menu ส่ง message + postback)
    for e in repliable:
        try:
            uid = e.get("source", {}).get("userId")
            if uid in paused or uid in replied_uids:
                continue
            if skip_images and e["type"] == "message" and e.get("message", {}).get("type") == "image":
                continue

            # ---- ปุ่ม "ดูใบเสร็จ" (แนบ quick reply ตอน slip verified) — ตอบสดด้วย reply token ไม่ใช่ push ----
            if e["type"] == "postback" and e.get("postback", {}).get("data") == _RECEIPT_POSTBACK:
                srow = await supa.select("slips", params={
                    "select": "id,amount,expected_course,bank,ref,slip_date", "line_user_id": f"eq.{uid}",
                    "status": "eq.verified", "order": "id.desc", "limit": "1"})
                text = await _receipt_text({
                    "id": srow[0]["id"], "amount": srow[0]["amount"], "course": srow[0]["expected_course"],
                    "bank": srow[0]["bank"], "ref": srow[0]["ref"], "date": srow[0]["slip_date"]}) if srow else None
                await line.reply(e["replyToken"], [{"type": "text", "text": text or "ยังไม่เจอรายการที่ยืนยันแล้วของคุณครับ ลองพิมพ์ 'ติดต่อแอดมิน' ได้เลย"}])
                replied_uids.add(uid)
                continue

            # ---- ปุ่ม quick reply "รายละเอียดหลักสูตร" (course_info:FC) — ตอบสดจากข้อมูลจริงใน DB ----
            if e["type"] == "postback" and (e.get("postback", {}).get("data") or "").startswith(_COURSE_QR_PREFIX):
                pfx = e["postback"]["data"][len(_COURSE_QR_PREFIX):]
                msgs = await _course_info_messages(pfx)
                code, _ = await line.reply(e["replyToken"], msgs)
                if code == 200:
                    replied_uids.add(uid)
                    out_msgs.append({"line_user_id": uid, "direction": "out", "by": "postback",
                                     "msg_type": "text", "text": msgs[0].get("text"), "payload": msgs[0]})
                continue

            # ---- postback action (routing table) มาก่อน ----
            if e["type"] == "postback":
                pa = _pick_postback(e.get("postback", {}).get("data", ""))
                if pa and pa.get("messages"):
                    msgs = pa["messages"][:5]
                    if _has_placeholder(msgs):
                        msgs = _personalize(msgs, await name_of(uid))
                    code, _ = await line.reply(e["replyToken"], msgs)
                    if code == 200:
                        replied_uids.add(uid)
                        await supa.update("postback_actions",
                                          {"hits": (pa.get("hits") or 0) + 1, "last_hit_at": NOW()},
                                          {"id": f"eq.{pa['id']}"})
                        for m in msgs:
                            out_msgs.append({"line_user_id": uid, "direction": "out", "by": "postback",
                                             "msg_type": m.get("type"), "text": m.get("text"), "payload": m})
                    continue

            rule = _pick_rule(e, rules)
            if not rule:
                continue
            # user บนเมนู Gemini + กฎที่เจอคือ fallback -> ไม่ตอบ ปล่อยให้ Gemini จัดการ
            if rule.get("trigger") == "fallback" and uid in gemini_uids:
                continue
            nm = await name_of(uid) if _has_placeholder(rule["messages"]) else None
            if await _reply_rule(e["replyToken"], rule, nm):
                replied_uids.add(uid)
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
    return replied_uids


# ============================================================
# dashboard
# ============================================================
def _day(s):
    return (s or "")[:10]


def _day_series(n: int) -> list[str]:
    today = dt.date.today()
    return [(today - dt.timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _iso_ago(**kw):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(**kw)).isoformat()


async def _gather_dict(**coros):
    keys = list(coros.keys())
    vals = await asyncio.gather(*coros.values(), return_exceptions=True)
    return {k: (None if isinstance(v, Exception) else v) for k, v in zip(keys, vals)}


_GAP_STOP = {"ครับ", "ค่ะ", "คะ", "นะ", "น่ะ", "ที่", "การ", "ของ", "และ", "หรือ", "ไหม", "มั้ย",
             "อยู่", "ได้", "จะ", "ให้", "มา", "ไป", "ว่า", "คือ", "กับ", "ใน", "เป็น", "ก็", "ๆ",
             "ผม", "หนู", "เรา", "ยัง", "แล้ว", "ด้วย", "ค่ะ", "อ่ะ", "อะ", "เอา", "มี", "ไม่",
             "ทำ", "ต้อง", "นี้", "นั้น", "อัน", "ตัว", "เลย", "จ้า", "จ้ะ", "งับ", "hello", "hi"}


# ---------- knowledge base: auto-generate เนื้อหาจัดซื้อจัดจ้างภาครัฐ ----------
_KB_TOPIC_SETTING_KEY = "kb_autogen_done_topics"

_PROCUREMENT_TOPICS = [
    "หลักประกันการเสนอราคาและหลักประกันสัญญา: ประเภทและอัตรา",
    "การขึ้นทะเบียนผู้ประกอบการงานก่อสร้าง",
    "ราคากลางและหลักเกณฑ์การคำนวณราคากลาง",
    "การจัดทำแผนการจัดซื้อจัดจ้างประจำปีและการเผยแพร่แผน",
    "ระบบจัดซื้อจัดจ้างภาครัฐด้วยอิเล็กทรอนิกส์ (e-GP)",
    "บทบาทหน้าที่คณะกรรมการตรวจรับพัสดุ",
    "บทบาทหน้าที่คณะกรรมการซื้อหรือจ้างในแต่ละวิธี",
    "ผู้มีผลประโยชน์ร่วมกันและคุณสมบัติต้องห้ามของผู้เสนอราคา",
    "ข้อห้ามการแบ่งซื้อแบ่งจ้างเพื่อหลีกเลี่ยงวิธีการที่กำหนด",
    "บัญชีรายชื่อผู้ทิ้งงาน",
    "หลักเกณฑ์เฉพาะของงานจ้างที่ปรึกษา",
    "หลักเกณฑ์เฉพาะของงานจ้างออกแบบหรือควบคุมงานก่อสร้าง",
    "บัญชีนวัตกรรมไทยและการส่งเสริมผู้ประกอบการ SME",
    "การยกเลิกการจัดซื้อจัดจ้างและเหตุแห่งการยกเลิก",
    "การขอขยายเวลา งดหรือลดค่าปรับให้คู่สัญญา",
    "การจำหน่ายพัสดุ: แลกเปลี่ยน โอน แปรสภาพ ทำลาย",
    "กฎกระทรวงกำหนดวงเงินการจัดซื้อจัดจ้างพัสดุโดยวิธีเฉพาะเจาะจง",
    "ระเบียบกระทรวงการคลังว่าด้วยการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ. 2560",
    "เปรียบเทียบวิธี e-market แบบใบเสนอราคา (RFQ) กับแบบประมูลอิเล็กทรอนิกส์ (e-Auction)",
    "ข้อยกเว้นการใช้บังคับ พ.ร.บ. สำหรับหน่วยงานที่ใช้เงินกู้/เงินช่วยเหลือจากต่างประเทศ",
    "การจัดทำรายงานขอซื้อขอจ้าง",
    "หลักเกณฑ์การพิจารณาผลการเสนอราคา: ราคาต่ำสุด กับ คุณภาพและราคา (Price Performance)",
    "เหตุที่ไม่อาจอุทธรณ์ผลการจัดซื้อจัดจ้างได้",
    "จรรยาบรรณของเจ้าหน้าที่พัสดุ",
    "การตรวจสอบพัสดุประจำปีและการรายงานผล",
    "การยืมพัสดุระหว่างหน่วยงานของรัฐ",
    "ความแตกต่างระหว่างวิธีประกาศเชิญชวนทั่วไป วิธีคัดเลือก และวิธีเฉพาะเจาะจง (เปรียบเทียบเชิงปฏิบัติ)",
    "การอุทธรณ์: ขั้นตอนและระยะเวลาโดยละเอียด",
    "หน้าที่และความรับผิดของเจ้าหน้าที่พัสดุตามกฎหมาย",
    "การจัดซื้อจัดจ้างที่เกี่ยวกับความมั่นคงของชาติ (ข้อยกเว้นพิเศษ)",
]

_KB_GEN_SYS_PROMPT = (
    "คุณคือผู้เชี่ยวชาญกฎหมายการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐไทย "
    "(อ้างอิงพระราชบัญญัติการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ. 2560 "
    "และระเบียบ/กฎกระทรวงที่เกี่ยวข้อง) ทำหน้าที่ร่างบทความความรู้สั้น กระชับ "
    "สำหรับสอนนักเรียนที่เตรียมสอบตำแหน่งเจ้าหน้าที่พัสดุ/นักวิชาการพัสดุ\n"
    "ตอบเป็น JSON เท่านั้น ห้ามมี markdown code fence ห้ามมีข้อความอื่นนอก JSON "
    'รูปแบบ: {"title": "หัวข้อสั้นไม่เกิน 60 ตัวอักษร", '
    '"body": "เนื้อหา 200-450 คำ ภาษาไทย กระชับเข้าใจง่าย ไม่ใช้ markdown", '
    '"keywords": ["คำ/วลีที่เกี่ยวข้อง 8-12 คำ"], '
    '"category": "เลือกหมวดที่ใกล้เคียงที่สุด: ภาพรวมกฎหมาย, วิธีจัดซื้อจัดจ้าง, สัญญาและการตรวจรับ, บริหารพัสดุ, บทลงโทษ, ระเบียบและหนังสือเวียน"}\n'
    "ถ้าไม่มั่นใจตัวเลข/มาตรา/วันที่ที่แม่นยำ ให้เขียนเชิงหลักการกว้าง ๆ แทนการเดาตัวเลขที่ไม่แน่ใจ "
    "ห้ามระบุตัวเลขมาตราที่ไม่มั่นใจว่าถูกต้อง"
)


def _parse_kb_gen_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title or not body:
        return None
    kws = data.get("keywords") or []
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(",") if k.strip()]
    return {
        "title": title[:120],
        "body": body[:3000],
        "keywords": [str(k).strip() for k in kws if str(k).strip()][:14],
        "category": (data.get("category") or "ระเบียบและหนังสือเวียน").strip(),
    }


async def _ai_generate_kb_article(topic: str) -> dict | None:
    """ให้ AI (Claude ก่อนถ้ามี ANTHROPIC_API_KEY ไม่งั้น Gemini) ร่างบทความความรู้ 1 หัวข้อ
    คืน dict {title,body,keywords,category} หรือ None ถ้าล้มเหลว/ไม่ได้ตั้งคีย์ใดเลย
    ใช้เฉพาะความรู้ที่โมเดลมีอยู่แล้ว (ไม่ได้ค้นเว็บสด) — ผลลัพธ์จึงยังต้องให้แอดมินตรวจก่อนเปิดใช้เสมอ"""
    user_prompt = f"หัวข้อบทความ: {topic}"
    try:
        if ANTHROPIC_API_KEY:
            client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=25)
            resp = await client.messages.create(
                model=ANTHROPIC_MODEL, max_tokens=1200, temperature=0.3,
                system=_KB_GEN_SYS_PROMPT,
                messages=[{"role": "user", "content": user_prompt}])
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
        elif GEMINI_API_KEY:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
            body = {
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "systemInstruction": {"parts": [{"text": _KB_GEN_SYS_PROMPT}]},
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3, "maxOutputTokens": 1200},
            }
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.post(url, json=body)
            j = r.json()
            if r.status_code != 200:
                print("kb autogen gemini http error:", r.status_code, str(j)[:300])
                return None
            cand = (j.get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
        else:
            return None
        return _parse_kb_gen_json(text)
    except Exception as e:
        print("kb autogen error:", topic, e)
        return None


async def _kb_autogen_batch(count: int, actor: str) -> dict:
    done = set(await _get_setting(_KB_TOPIC_SETTING_KEY, []) or [])
    pending = [t for t in _PROCUREMENT_TOPICS if t not in done]
    if not pending:
        return {"created": [], "failed_topics": [], "remaining": 0}
    batch = pending[:max(1, min(count, 10))]
    created, failed_topics = [], []
    for topic in batch:
        art = await _ai_generate_kb_article(topic)
        if not art:
            failed_topics.append(topic)
            continue
        row = {**art, "enabled": False, "updated_by": actor, "updated_at": NOW()}
        try:
            res = await supa.insert("kb_articles", row)
            created.append({"id": (res[0]["id"] if res else None), "title": art["title"], "category": art["category"]})
            done.add(topic)
        except Exception as e:
            print("kb autogen insert error:", e)
            failed_topics.append(topic)
    if created:
        await supa.upsert("app_settings", {"key": _KB_TOPIC_SETTING_KEY, "value": sorted(done), "updated_at": NOW()},
                          on_conflict="key")
        _gemini_kb_cache["items"] = None
    remaining = len(_PROCUREMENT_TOPICS) - len(done)
    return {"created": created, "failed_topics": failed_topics, "remaining": remaining}


# ---------- สอนน้องพัสดุ: เจ้าของตอบคำถามจริงที่ลูกค้าถามบ่อยแต่ยังไม่มีคำตอบ ครั้งเดียว -> เป็นความรู้ที่ AI ใช้ทันที ----------
_TEACH_TTL = 6 * 3600
# ข้อความที่ไม่ใช่ "คำถามที่ต้องสอน": ปุ่ม/คำสั่งของระบบ และการรับทราบ/ขอบคุณเฉย ๆ (ซ้ำเยอะจนบดบังคำถามจริง)
_TEACH_NOISE = {_norm_question(x) for x in (
    "ลงทะเบียนที่เมนูด้านล่าง", "ติดต่อแอดมิน", "ค่ะ", "คะ", "ครับ", "ค่า", "จ้า", "โอเค", "ok", "รับทราบ",
    "ขอบคุณที่ให้น้องพัสดุดูแล แล้วพบกันนะครับ", "ขอบคุณ", "ขอบคุณค่ะ", "ขอบคุณครับ", "ขอบคุณมากค่ะ", "ขอบคุณมากครับ",
    "ขอบคุณนะคะ", "ขอบคุณนะครับ", "สวัสดี", "สวัสดีค่ะ", "สวัสดีครับ", "สวัสดีคะ")}
# ข้อความที่ AI ไม่ควรตอบเลย: การรับทราบ/ขอบคุณ/ทักทายสั้น ๆ (คำถามจริงต้องมีสาระกว่านี้)
_TEACH_NOISE_PLAIN = _TEACH_NOISE - {_norm_question(x) for x in ("ติดต่อแอดมิน", "ลงทะเบียนที่เมนูด้านล่าง", "สวัสดี", "สวัสดีค่ะ", "สวัสดีครับ", "สวัสดีคะ")}
_PII_RE = re.compile(r"\d[\d\-\s]{6,}\d|userid|@|(?:^|\s)(?:นาย|นางสาว|นาง|น\.ส\.|คุณ)\s*\S+|(?:ต\.|อ\.|จ\.|หมู่|ซอย|ถนน)\s*\S*\d")


def _teach_clean(q: str) -> str | None:
    """คืนคำถามที่สะอาดพอส่งให้ AI จัดกลุ่ม หรือ None ถ้าควรทิ้ง (ข้อมูลส่วนตัว/ปุ่มระบบ/ไม่มีสาระ)"""
    q = re.sub(r"[​‌‍]", "", (q or "")).strip()
    if not (4 <= len(q) <= 140) or q.count("\n") >= 1:
        return None
    if _PII_RE.search(q.lower()):
        return None
    n = _norm_question(q)
    if len(n) < 3 or n in _TEACH_NOISE:
        return None
    return q


def _parse_json_loose(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def _ai_text_json(system: str, user: str, max_tokens: int = 3000, timeout: int = 45):
    """เรียก AI (Claude ก่อน ไม่มีค่อย Gemini) ให้ตอบ JSON จากข้อความล้วน — คืน object/None"""
    try:
        if ANTHROPIC_API_KEY:
            client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=timeout)
            resp = await client.messages.create(model=ANTHROPIC_MODEL, max_tokens=max_tokens, temperature=0.2,
                                                system=system, messages=[{"role": "user", "content": user}])
            return _parse_json_loose("".join(b.text for b in resp.content if b.type == "text"))
        if GEMINI_API_KEY:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            body = {"contents": [{"role": "user", "parts": [{"text": user}]}],
                    "systemInstruction": {"parts": [{"text": system}]},
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2, "maxOutputTokens": max_tokens}}
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.post(url, json=body)
            if r.status_code != 200:
                print("ai json http error:", r.status_code, r.text[:200])
                return None
            parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            return _parse_json_loose("".join(p.get("text", "") for p in parts))
    except Exception as e:
        print("ai json error:", repr(e)[:200])
    return None


_TEACH_SYS = (
    "คุณช่วยจัดกลุ่มข้อความจริงที่ลูกค้าพิมพ์ถามเพจติวสอบ e-CPP (ติวสอบมาตรฐานวิชาชีพด้านการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ "
    "หลักสูตร FC IC PC AC) ให้แต่ละกลุ่มคือ 'เรื่องเดียวกันที่เจ้าของต้องตอบครั้งเดียวแล้วใช้ได้กับทุกคน'\n"
    'ตอบเป็น JSON เท่านั้น: {"themes":[{"title":"หัวข้อสั้น ไม่เกิน 40 ตัวอักษร เขียนเป็นเรื่องที่ต้องตอบ เช่น วันเริ่มเรียน/เริ่มติวเมื่อไหร่",'
    '"kind":"knowledge|status|escalate|chitchat|other","ids":[เลขข้อที่อยู่ในกลุ่มนี้]}]}\n'
    "kind: knowledge = ต้องการข้อมูล/นโยบายที่ผู้สอนต้องเป็นคนบอก (ตารางเรียน วันเริ่ม กำหนดเวลา เอกสาร/ชีท/คลิป การเปลี่ยนรุ่น เงื่อนไข วิธีสมัคร "
    "เนื้อหาสอบ) · status = ถามสถานะการสมัคร/การชำระเงิน/สลิปของตัวเอง (ระบบตอบจากข้อมูลจริงได้) · escalate = ร้องเรียน ขอเงินคืน ต้องให้คนตัดสินใจ · "
    "chitchat = ทักทาย ขอบคุณ แจ้งข่าวส่วนตัวที่ไม่ต้องตอบข้อมูล · other = ที่เหลือ\n"
    "กติกา: ทุกข้อต้องอยู่ในกลุ่มเดียว ห้ามแต่งข้อความขึ้นเอง อ้างเฉพาะเลขข้อที่ให้มา รวมข้อที่ความหมายเดียวกันเข้ากลุ่มเดียว (เช่น เริ่มเรียนวันไหน/เริ่มติวเมื่อไหร่/จะติวช่วงไหน) "
    "ไม่เกิน 25 กลุ่ม"
)


async def _teach_handled() -> set:
    return set(await _get_setting("kb_teach_handled", []) or [])


async def _teach_build() -> dict | None:
    """ดึงคำถามที่ AI ตอบโดยไม่มีความรู้รองรับ -> กรองข้อมูลส่วนตัว/ปุ่ม -> ให้ AI จัดกลุ่ม -> คืน themes"""
    ops = await supa.select_all("operations", params={
        "select": "params", "action": "like.gemini.kb_gap*", "created_at": f"gte.{_iso_ago(days=90)}"})
    handled = await _teach_handled()
    counts: dict[str, dict] = {}
    for o in ops:
        q = _teach_clean(str((o.get("params") or {}).get("q") or ""))
        if not q:
            continue
        n = _norm_question(q)
        if n in handled:
            continue
        g = counts.setdefault(n, {"q": q, "n": 0})
        g["n"] += 1
    items = sorted(counts.items(), key=lambda kv: -kv[1]["n"])[:120]
    if not items:
        return {"themes": [], "total_questions": 0}
    listing = "\n".join(f"{i + 1}. [{v['n']}x] {v['q']}" for i, (_n, v) in enumerate(items))
    res = await _ai_text_json(_TEACH_SYS, "ข้อความลูกค้า:\n" + listing)
    if not isinstance(res, dict) or not isinstance(res.get("themes"), list):
        return None
    themes, seen = [], set()
    for t in res["themes"]:
        ids = [i for i in (t.get("ids") or []) if isinstance(i, int) and 1 <= i <= len(items) and i not in seen]
        if not ids:
            continue
        seen.update(ids)
        norms = [items[i - 1][0] for i in ids]
        themes.append({
            "key": hashlib.sha1("|".join(sorted(norms)).encode()).hexdigest()[:12],
            "title": str(t.get("title") or "")[:60] or items[ids[0] - 1][1]["q"][:40],
            "kind": t.get("kind") if t.get("kind") in ("knowledge", "status", "escalate", "chitchat", "other") else "other",
            "count": sum(items[i - 1][1]["n"] for i in ids),
            "examples": [items[i - 1][1]["q"] for i in ids][:5],
            "norms": norms,
        })
    themes.sort(key=lambda t: (t["kind"] != "knowledge", -t["count"]))
    return {"themes": themes, "total_questions": sum(v["n"] for _n, v in items)}


async def _teach_state(refresh: bool = False) -> dict:
    cache = await _get_setting("kb_teach_cache", None)
    if not refresh and isinstance(cache, dict) and time.time() - float(cache.get("at") or 0) < _TEACH_TTL:
        return cache
    built = await _teach_build()
    if built is None:
        if isinstance(cache, dict):
            return {**cache, "stale": True}
        return {"themes": [], "total_questions": 0, "at": time.time(), "error": "AI จัดกลุ่มไม่สำเร็จ ลองใหม่อีกครั้ง"}
    built["at"] = time.time()
    await supa.upsert("app_settings", {"key": "kb_teach_cache", "value": built, "updated_at": NOW()}, on_conflict="key")
    return built


async def _teach_mark(theme: dict):
    handled = await _teach_handled() | set(theme.get("norms") or [])
    await supa.upsert("app_settings", {"key": "kb_teach_handled", "value": sorted(handled)[-3000:], "updated_at": NOW()},
                      on_conflict="key")
    cache = await _get_setting("kb_teach_cache", None)
    if isinstance(cache, dict):
        cache["themes"] = [t for t in cache.get("themes", []) if t.get("key") != theme.get("key")]
        await supa.upsert("app_settings", {"key": "kb_teach_cache", "value": cache, "updated_at": NOW()}, on_conflict="key")


def _teach_public(state: dict) -> dict:
    return {"themes": [{k: t[k] for k in ("key", "title", "kind", "count", "examples")} for t in state.get("themes", [])],
            "total_questions": state.get("total_questions", 0), "generated_at": state.get("at"),
            "stale": bool(state.get("stale")), "error": state.get("error"),
            "ai_ready": bool(ANTHROPIC_API_KEY or GEMINI_API_KEY)}


async def _teach_find(key: str) -> dict:
    cache = await _get_setting("kb_teach_cache", None) or {}
    theme = next((t for t in cache.get("themes", []) if t.get("key") == key), None)
    if not theme:
        raise HTTPException(404, "ไม่พบหัวข้อนี้แล้ว (อาจถูกจัดการไปแล้ว) — กดรีเฟรชรายการ")
    return theme


async def _richmenu_usage_data() -> dict:
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


def _cron_authorized(request: Request) -> bool:
    """รองรับทั้ง ?key=, header x-cron-key และ Authorization: Bearer <CRON_SECRET>
    (Vercel Cron จะแนบ Authorization: Bearer <CRON_SECRET> ให้อัตโนมัติถ้าตั้ง env CRON_SECRET ไว้)"""
    if not CRON_SECRET:
        return True
    key = request.query_params.get("key") or request.headers.get("x-cron-key", "")
    auth = request.headers.get("authorization", "")
    return key == CRON_SECRET or auth == f"Bearer {CRON_SECRET}"


async def _fetch_current_menu_map(uids: list[str]) -> dict:
    """ดึงค่าปัจจุบันใน DB ของ uids ก่อนเขียนทับ ใช้เทียบหา diff สำหรับ richmenu_history"""
    out: dict = {}
    for i in range(0, len(uids), 200):
        chunk = uids[i:i + 200]
        rows = await supa.select("line_users", params={
            "select": "line_user_id,current_rich_menu_id,rich_menu_status",
            "line_user_id": f"in.({','.join(chunk)})",
        })
        for r in rows:
            out[r["line_user_id"]] = r
    return out


async def _log_richmenu_diffs(old_map: dict, new_rows: list[dict], source: str, actor: str | None):
    """เทียบ old vs new แล้วบันทึกเฉพาะแถวที่เปลี่ยนจริงลง richmenu_history"""
    history_rows = []
    for row in new_rows:
        uid = row["line_user_id"]
        old = old_map.get(uid, {})
        old_rid, old_status = old.get("current_rich_menu_id"), old.get("rich_menu_status")
        new_rid, new_status = row.get("current_rich_menu_id"), row.get("rich_menu_status")
        if old_rid != new_rid or old_status != new_status:
            history_rows.append({
                "line_user_id": uid, "old_rich_menu_id": old_rid, "new_rich_menu_id": new_rid,
                "old_status": old_status, "new_status": new_status,
                "source": source, "actor": actor,
            })
    if history_rows:
        try:
            for i in range(0, len(history_rows), 500):
                await supa.insert("richmenu_history", history_rows[i:i + 500])
        except Exception as e:
            print("richmenu_history insert error:", e)
    return len(history_rows)


async def _sync_richmenu_for(uids: list[str], source: str = "sync", actor: str | None = None) -> dict:
    if not uids:
        return {"total": 0, "assigned": 0, "none": 0, "error": 0}
    old_map = await _fetch_current_menu_map(uids)
    menus = {m["richMenuId"]: m.get("name") for m in await line.richmenu_list()}
    sem = asyncio.Semaphore(25)  # งาน I/O ล้วน (รอ LINE API) — ขนานมากขึ้น = wall time สั้นลง = กิน GB-hrs ของ Vercel น้อยลง
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
    summary["history_logged"] = await _log_richmenu_diffs(old_map, patch, source, actor)
    return {"total": len(uids), **summary}


async def _link_slip_menu(uid: str, source: str = "slip", actor: str = "system") -> dict:
    """ผูก rich menu 'หลังส่งสลิป' (SLIP_SUCCESS_RICHMENU_ID) ให้ user — ลองซ้ำ 1 ครั้งเมื่อ LINE ล่ม/429
    ล้มเหลวแล้วต้องไม่เงียบ: บันทึก operations + แจ้งแอดมิน (throttle ตามรหัสผิดพลาด) · สำเร็จ = เขียน line_users + richmenu_history"""
    rid = SLIP_SUCCESS_RICHMENU_ID
    if not rid or not uid:
        return {"ok": False, "reason": "disabled"}
    code = None
    ok = False
    try:
        old_map = await _fetch_current_menu_map([uid])
    except Exception:
        old_map = {}
    for attempt in range(2):
        try:
            ok, code = await line.user_richmenu_link(uid, rid)
        except Exception as ex:  # noqa: BLE001
            ok, code = False, f"exc:{type(ex).__name__}"
        if ok:
            break
        if isinstance(code, int) and 400 <= code < 500 and code != 429:
            break   # 4xx (เมนูไม่มี/ไม่ได้เป็นเพื่อน) ลองซ้ำก็ไม่หาย
        if attempt == 0:
            await asyncio.sleep(0.6)
    if not ok:
        print("slip richmenu link failed:", uid[:10], code)
        try:
            await supa.log_operation(actor, "richmenu.slip_link_failed", {"uid": uid, "source": source},
                                     {"code": str(code), "richMenuId": rid}, status="error")
        except Exception:
            pass
        hint = {404: "ไม่พบ Rich Menu ID นี้ใน LINE — ตรวจ SLIP_SUCCESS_RICHMENU_ID",
                400: "LINE ปฏิเสธ (ผู้ใช้อาจบล็อก/ไม่ใช่เพื่อน หรือ ID ผิด)"}.get(code, "")
        await alert_admin("สลับ Rich Menu หลังส่งสลิปไม่สำเร็จ",
                          f"LINE ตอบ {code} {hint}\nuser {uid[:10]}…", throttle_key=f"slipmenu_{code}")
        return {"ok": False, "reason": f"line {code}"}
    try:
        ts = NOW()
        row = {"line_user_id": uid, "current_rich_menu_id": rid, "rich_menu_status": "assigned",
               "rich_menu_checked_at": ts, "updated_at": ts}
        await supa.upsert("line_users", [row], on_conflict="line_user_id")
        await _log_richmenu_diffs(old_map, [row], source, actor)
    except Exception as ex:  # noqa: BLE001
        print("slip richmenu db write error:", ex)   # เมนูเปลี่ยนที่ LINE แล้ว — แค่บันทึกลง DB พลาด
    return {"ok": True}


async def _slip_menu_repair(apply: bool, limit: int = 60) -> dict:
    """ซ่อมย้อนหลัง: คนที่ส่งสลิปแล้ว (verified/review) แต่ 'ไม่เคยได้' เมนูหลังส่งสลิปเลย
    ตั้งใจแตะเฉพาะคนที่ไม่เคยมีแถว richmenu_history ที่ new = เมนูนี้ — ไม่ดึงคนที่เคยได้แล้วถูกย้ายไปเมนูอื่นทีหลัง
    (เช่น ห้อง Zoom/ตามคอร์ส) กลับมา · dry-run เป็นค่าเริ่มต้น เช็คเมนูสดจาก LINE ก่อนทุกคน"""
    rid = SLIP_SUCCESS_RICHMENU_ID
    if not rid:
        return {"skipped": "SLIP_SUCCESS_RICHMENU_ID ว่าง"}
    slips = await supa.select_all("slips", params={"select": "line_user_id,status", "status": "in.(verified,review)"})
    slip_uids = {s["line_user_id"] for s in slips if s.get("line_user_id")}
    users = await supa.select_all("line_users", params={
        "select": "line_user_id,current_rich_menu_id", "is_following": "eq.true"})
    following = {u["line_user_id"]: u.get("current_rich_menu_id") for u in users}
    got = await supa.select_all("richmenu_history", params={
        "select": "line_user_id", "new_rich_menu_id": f"eq.{rid}"})
    got_uids = {h["line_user_id"] for h in got}
    cands = sorted(u for u in slip_uids if u in following and u not in got_uids and following[u] != rid)
    batch = cands[:max(1, limit)]
    out = {"richMenuId": rid, "slip_users": len(slip_uids), "never_received_candidates": len(cands),
           "batch": len(batch), "remaining_after": max(0, len(cands) - len(batch)),
           "already_on_menu": 0, "linked": 0, "failed": 0, "would_link": 0, "applied": apply}
    sem = asyncio.Semaphore(8)

    async def one(uid):
        async with sem:
            try:
                live = await line.user_richmenu_get(uid)
            except Exception:
                live = "?"
            if live == rid:
                out["already_on_menu"] += 1
                return
            if not apply:
                out["would_link"] += 1
                return
            r = await _link_slip_menu(uid, source="slip_repair", actor="admin")
            out["linked" if r.get("ok") else "failed"] += 1

    await asyncio.gather(*[one(u) for u in batch])
    return out


async def _richmenu_auto_unregistered(limit: int = 300) -> dict:
    """หา follower ที่ยังไม่เคยถูกตั้งเมนูเฉพาะ (rich_menu_status none/ว่าง — แปลว่ายังใช้เมนู default ของบอทอยู่)
    และยังไม่มีแถวใน registrations เลย -> สลับเป็นเมนู unregistered_richmenu_id (ตั้งค่าที่หน้า Admins)
    ตั้งใจไม่แตะคนที่เคยถูกตั้งเมนูเฉพาะไปแล้ว กันชนกับโฟลว์อื่น (เช่น ห้อง Zoom/รอผลสอบ/ริชเมนูตามคอร์ส)
    เป็น rolling batch เหมือน sync-richmenu (เอาคนที่เช็คนานสุดก่อน) — เผื่อ follower ใหม่ทยอยเข้ามาเรื่อย ๆ"""
    rid = await _get_setting("unregistered_richmenu_id")
    if not rid:
        return {"skipped": "ยังไม่ได้ตั้งค่า unregistered_richmenu_id", "total": 0, "ok": 0, "fail": 0}

    rows = await supa.select("line_users", params={
        "select": "line_user_id,current_rich_menu_id,rich_menu_status", "is_following": "eq.true",
        "or": "(rich_menu_status.eq.none,rich_menu_status.is.null)",
        "order": "rich_menu_checked_at.asc.nullsfirst",
        "limit": str(limit),
    })
    uids = [r["line_user_id"] for r in rows if r.get("current_rich_menu_id") != rid]
    if uids:
        reg_rows = await supa.select_all("registrations", params={"select": "line_user_id"})
        registered = {r["line_user_id"] for r in reg_rows if r.get("line_user_id")}
        uids = [u for u in uids if u not in registered]
    if not uids:
        return {"total": 0, "ok": 0, "fail": 0}

    old_map = await _fetch_current_menu_map(uids)
    sem = asyncio.Semaphore(8)
    results = {"ok": 0, "fail": 0}

    async def one(uid):
        async with sem:
            ok, code = await line.user_richmenu_link(uid, rid)
            results["ok" if ok else "fail"] += 1
            return uid, ok

    done = await asyncio.gather(*[one(u) for u in uids])
    ts = NOW()
    patch = [{
        "line_user_id": u,
        "current_rich_menu_id": rid if ok else old_map.get(u, {}).get("current_rich_menu_id"),
        "rich_menu_status": "assigned" if ok else old_map.get(u, {}).get("rich_menu_status"),
        "rich_menu_checked_at": ts, "updated_at": ts,
    } for u, ok in done]
    try:
        await supa.upsert("line_users", patch, on_conflict="line_user_id")
    except Exception as e:
        results["db_error"] = str(e)

    await _log_richmenu_diffs(old_map, patch, "auto-unregistered", "cron")
    return {"total": len(uids), **results}


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


def _clean_str(s):
    if not s:
        return s
    s = "".join(ch for ch in s if ch in "\n\t" or ord(ch) >= 0x20)
    return s or None


# ============================================================
# INBOX (แชต + human takeover)
# ============================================================
_INBOX_SELECT = ("line_user_id,display_name,picture_url,last_message_at,last_message_text,"
                 "unread,auto_reply_paused,assigned_to,is_following,tags,stage,"
                 "current_rich_menu_id,rich_menu_name,consent")


async def _inbox_slip_counts() -> dict[str, int]:
    """นับสลิปค้างตรวจ (new/review) ต่อ userId — ใช้ทั้งจัดลำดับคิวและ badge บนแถวแชท"""
    rows = await supa.select_all("slips", params={
        "select": "line_user_id", "status": "in.(new,review)"})
    counts: dict[str, int] = {}
    for r in rows:
        uid = r.get("line_user_id")
        if uid:
            counts[uid] = counts.get(uid, 0) + 1
    return counts


async def _reply_or_push(uid: str, msgs: list) -> tuple[int, str, str | None]:
    """ตอบผ่าน reply token ล่าสุดของ uid นี้ก่อนถ้ายังสดพอ (ฟรี ไม่กินโควต้า) — ใช้ไม่ได้/หมดอายุ/ไม่มี
    ค่อย fallback ไป push (ของเดิม) เสมอ ไม่กระทบความน่าเชื่อถือการส่ง เป็นแค่ fast path ประหยัดโควต้า"""
    try:
        row = await supa.select("line_users", params={
            "select": "last_reply_token,last_reply_token_at", "line_user_id": f"eq.{uid}", "limit": "1"})
        tok = row[0].get("last_reply_token") if row else None
        at = row[0].get("last_reply_token_at") if row else None
        if tok and at and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(at)).total_seconds() < 60:
            code, txt = await line.reply(tok, msgs)
            if code == 200:
                await supa.update("line_users", {"last_reply_token": None}, {"line_user_id": f"eq.{uid}"})
                return 200, txt, None
    except Exception as e:
        print("reply-token fast path error (fallback to push):", e)
    return await line.push(uid, msgs)


PIPELINE_STAGES = ["lead", "interested", "registered", "paid", "enrolled", "completed", "alumni", "lost"]
_STAGE_LABEL = {"lead": "Lead", "interested": "สนใจ", "registered": "ลงทะเบียน", "paid": "จ่ายแล้ว",
                "enrolled": "เข้าเรียน", "completed": "เรียนจบ", "alumni": "ศิษย์เก่า", "lost": "หลุด"}


def _parse_ts(s):
    try:
        return dt.datetime.fromisoformat(s) if s else None
    except Exception:
        return None


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


# ============================================================
# broadcast postback click tracking — รู้ว่าใคร (userId) คลิกปุ่ม postback ที่มาจาก broadcast ไหน
# วิธีทำ: แนบรหัส broadcast ต่อท้าย data ด้วยตัวคั่นที่มองไม่เห็น (\x1f) ตอนส่ง
# แล้วแกะออกตอนรับ postback event กลับมา (ก่อนเข้ากฎ postback_actions/auto_reply เดิม)
# เพื่อไม่ให้กระทบการ match แบบ exact/prefix ของ data เดิมที่แอดมินตั้งไว้
# ============================================================
_BC_TAG_SEP = "\x1f"


def _walk_actions(node, fn):
    """เดินทุก dict/list หา key 'type'=='postback' เรียก fn(node) ให้ (ใช้กับทั้ง template.actions/columns และ flex ที่ซ้อนลึก)"""
    if isinstance(node, dict):
        if node.get("type") == "postback":
            fn(node)
        for v in node.values():
            _walk_actions(v, fn)
    elif isinstance(node, list):
        for v in node:
            _walk_actions(v, fn)


def _has_postback_action(messages: list) -> bool:
    found = []
    _walk_actions(messages, lambda a: found.append(a))
    return bool(found)


def _tag_broadcast_postbacks(messages: list, broadcast_id) -> list:
    """คืนสำเนาข้อความที่แนบรหัส broadcast ไว้ในทุกปุ่ม postback"""
    if not broadcast_id:
        return messages
    msgs = copy.deepcopy(messages)

    def _tag(a):
        d = a.get("data")
        if d and _BC_TAG_SEP not in d:
            a["data"] = f"{d}{_BC_TAG_SEP}bc{broadcast_id}"
    _walk_actions(msgs, _tag)
    return msgs


def _split_postback_data(data: str):
    """แยก postback data จริงออกจากรหัส broadcast ที่แนบท้าย (ถ้ามี) -> (clean_data, broadcast_id|None)"""
    if data and _BC_TAG_SEP in data:
        clean, _, tag = data.rpartition(_BC_TAG_SEP)
        if tag.startswith("bc") and tag[2:].isdigit():
            return clean, int(tag[2:])
    return data, None


async def _broadcast_begin(actor: str | None, kind: str, messages: list, target_count: int | None) -> tuple[int, list]:
    """สร้างแถว broadcasts (status=sending) ก่อนส่งจริง -> คืน (id, ข้อความที่แนบรหัส postback แล้ว)"""
    row = (await supa.insert("broadcasts", {
        "actor": actor, "kind": kind, "target_count": target_count,
        "messages": messages, "status": "sending",
    }))[0]
    bid = row["id"]
    return bid, _tag_broadcast_postbacks(messages, bid)


async def _broadcast_finish(bid: int, *, status: str, line_request_id: str | None = None,
                            error: str | None = None, target_count: int | None = None) -> None:
    patch = {"status": status, "line_request_id": line_request_id, "error": error}
    if target_count is not None:
        patch["target_count"] = target_count
    await supa.update("broadcasts", patch, {"id": f"eq.{bid}"})


# ============================================================
# EVENTS / LOGS
# ============================================================
async def events(admin=Depends(current_admin), limit: int = 100, type: str = "", uid: str = ""):
    params = {"select": "id,event_type,line_user_id,message_type,text,reply_token,postback_data,auto_replied,created_at",
              "order": "created_at.desc", "limit": str(min(limit, 500))}
    if type:
        params["event_type"] = f"eq.{type}"
    if uid:
        params["line_user_id"] = f"eq.{uid}"
    return {"events": await supa.select("webhook_events", params=params)}


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


BACKUP_TABLES = ("admins", "line_users", "auto_replies", "segments", "message_templates",
                 "rich_menus", "scheduled_jobs", "registrations", "slips", "payment_accounts",
                 "postback_actions", "automations", "app_settings", "liff_apps",
                 "tasks", "classes", "attendance", "contact_notes", "kb_articles",
                 "richmenu_history", "follow_history")


async def _make_backup():
    day = dt.date.today().isoformat()
    dump = {}
    for tb in BACKUP_TABLES:
        try:
            dump[tb] = await supa.select_all(tb, params={"select": "*"})
        except Exception as e:
            dump[tb] = {"error": str(e)}
    raw = json.dumps(dump, ensure_ascii=False).encode()
    size_kb = len(raw) // 1024
    blob = gzip.compress(raw, 6)
    row_counts = {k: (len(v) if isinstance(v, list) else 0) for k, v in dump.items()}
    # ข้อมูลเต็มเก็บที่ Storage เท่านั้น (แยกจาก DB — DB ล่มก็ยังกู้ได้)
    ext_url = None
    storage_err = None
    try:
        await supa.storage_ensure_bucket("db-backups", public=False)
        await supa.storage_upload("db-backups", f"{day}.json.gz", blob, "application/gzip")
        ext_url = await supa.storage_sign_url("db-backups", f"{day}.json.gz", 7 * 86400)
    except Exception as e:
        storage_err = str(e)
        print("backup storage upload error:", e)
    # เก็บแค่ metadata + จำนวนแถวต่อตารางลง Postgres (คอลัมน์ tables เดิม แต่ไม่ใส่ข้อมูลเต็มแล้ว —
    # ตารางที่โตขึ้นเรื่อย ๆ (richmenu_history, line_users ฯลฯ) ทำให้ payload ใหญ่จนพัง 500 ตอน upsert)
    await supa.upsert("backups", {"day": day, "tables": row_counts, "size_kb": size_kb},
                      on_conflict="day")
    old = await supa.select("backups", params={"select": "id,day", "order": "day.desc", "limit": "60"})
    for r in old[30:]:
        await supa.delete("backups", {"id": f"eq.{r['id']}"})
        try:
            await supa.storage_delete("db-backups", f"{r['day']}.json.gz")
        except Exception:
            pass
    return {"day": day, "size_kb": size_kb, "gz_kb": len(blob) // 1024,
            "storage": bool(ext_url), "storage_url": ext_url, "storage_err": storage_err,
            "rows": row_counts}


async def _retag_from_registrations() -> dict:
    """อ่าน registrations ทั้งหมด -> tag line_users (คอร์ส + ลงทะเบียน + จ่ายแล้ว)"""
    regs = await supa.select_all("registrations", params={"select": "line_user_id,course,paid"})
    by_uid: dict[str, dict] = {}
    for r in regs:
        if not r.get("line_user_id"):
            continue
        u = by_uid.setdefault(r["line_user_id"], {"courses": set(), "paid": False})
        if r.get("course"):
            u["courses"].add(r["course"])
        if r.get("paid"):
            u["paid"] = True
    uids = list(by_uid)
    touched = 0
    for i in range(0, len(uids), 80):
        chunk = uids[i:i + 80]
        try:
            existing = {x["line_user_id"]: x for x in await supa.select("line_users", params={
                "select": "line_user_id,tags", "line_user_id": f"in.({','.join(chunk)})", "limit": "200"})}
            patch = []
            for uid in chunk:
                info = by_uid[uid]
                cur = set((existing.get(uid) or {}).get("tags") or [])
                new = set(cur) | {"ลงทะเบียน"} | info["courses"]
                if info["paid"]:
                    new.add("จ่ายแล้ว")
                row = {"line_user_id": uid, "tags": sorted(new), "updated_at": NOW()}
                if uid not in existing:
                    row["source"] = "registration"
                    row["is_following"] = True
                if new != cur or uid not in existing:
                    patch.append(row)
            if patch:
                await supa.upsert("line_users", patch, on_conflict="line_user_id")
                touched += len(patch)
        except Exception as e:
            print("retag chunk error:", e)
    return {"registrations": len(regs), "people": len(uids), "users_tagged": touched}


async def _cron_last_run(action_like: str) -> str | None:
    rows = await supa.select("operations", params={
        "select": "created_at", "action": f"like.{action_like}",
        "order": "created_at.desc", "limit": "1"})
    return rows[0]["created_at"] if rows else None


async def _cron_stale() -> list[str]:
    """รายการ cron ที่เงียบเกินกำหนด (ว่าง = ปกติ) — ใช้ร่วมกันทั้ง heartbeat และสรุปประจำวัน"""
    checks = {
        "richmenu.sync": 14 * 3600,  # sync รันวันละ 2 รอบ (08:00 / 19:00 น.) ห่างสุด ~13 ชม.
        "automation.run": 2 * 3600,
        "stats.snapshot": 30 * 3600,
        "backup": 30 * 3600,
        "reconcile.auto_mark": 30 * 3600,
    }
    # richmenu.auto_unregistered เฝ้าดูแยก — เป็น no-op ปกติถ้ายังไม่ตั้ง unregistered_richmenu_id
    # (ใส่ใน checks ตายตัวจะ false-positive กับ user ที่ไม่ได้ใช้ฟีเจอร์นี้)
    if await _get_setting("unregistered_richmenu_id"):
        checks["richmenu.auto_unregistered"] = 6 * 3600
    stale = []
    for act, limit in checks.items():
        last = await _cron_last_run(f"*{act}*")
        if not last:
            stale.append(f"{act}: ไม่เคยรัน")
            continue
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last)).total_seconds()
        if age > limit:
            stale.append(f"{act}: {int(age // 3600)} ชม.ที่แล้ว")
    return stale


# ---- หมวด "สุขภาพระบบ" ในสรุปประจำวัน: แต่ละข้อแยกกัน ข้อไหนเช็คไม่ได้ก็ไม่ล้มทั้งสรุป ----
async def _dg_cron():
    stale = await _cron_stale()
    return "⚙️ Cron: ปกติ ✅" if not stale else "⚠️ Cron ค้าง: " + "; ".join(stale)


async def _dg_line_quota():
    import calendar
    q = await line.message_quota()
    lim = q.get("quota", {}).get("quota", q.get("quota")) or {}
    used = q.get("totalUsage")
    if not isinstance(lim, dict) or lim.get("type") != "limited" or not lim.get("value") or used is None:
        return None   # แผนไม่จำกัด/อ่านไม่ได้ — ไม่ต้องรายงาน
    limit, used = int(lim["value"]), int(used)
    today = dt.date.today()
    projected = used / max(today.day, 1) * calendar.monthrange(today.year, today.month)[1]
    pct, ppct = used / limit * 100, projected / limit * 100
    warn = pct >= 80 or ppct >= 100
    return (f"{'⚠️' if warn else '💌'} โควต้าข้อความ LINE: {used:,}/{limit:,} ({pct:.0f}%)"
            f" · คาดสิ้นเดือน ~{ppct:.0f}%")


async def _dg_easyslip():
    if not EASYSLIP_TOKEN:
        return None
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.get("https://developer.easyslip.com/api/v1/me",
                        headers={"Authorization": f"Bearer {EASYSLIP_TOKEN}"})
    if r.status_code != 200:
        return f"⚠️ EasySlip: token มีปัญหา (HTTP {r.status_code})"
    d = r.json().get("data") or {}
    q = d.get("quota") or d
    used, mx, remain = q.get("usedQuota", q.get("used")), q.get("maxQuota", q.get("max", q.get("limit"))), q.get("remainingQuota")
    if used is None or mx is None:
        return "🧾 EasySlip: เชื่อมต่อได้"
    try:
        warn = remain is not None and (int(remain) <= 0 or int(remain) <= int(mx) * 0.2)
    except (TypeError, ValueError):
        warn = False
    return f"{'⚠️' if warn else '🧾'} EasySlip: ใช้ {used}/{mx}" + (" — ใกล้เต็ม" if warn else "")


async def _slips_summary() -> dict:
    """สรุปสลิปแบบไม่มีข้อมูลส่วนบุคคล: จำนวนตามสถานะ, เหตุผลที่ค้าง (auto_note), อายุของที่ค้าง"""
    rows = await supa.select_all("slips", params={
        "select": "status,auto_note,matched,amount,expected_course,created_at"})
    now = dt.datetime.now(dt.timezone.utc)
    by_status: dict[str, int] = {}
    reasons: dict[str, int] = {}
    ages = {"<1 วัน": 0, "1-3 วัน": 0, "3-7 วัน": 0, ">7 วัน": 0}
    pending = no_amount = no_course = 0
    for r in rows:
        st = r.get("status") or "?"
        by_status[st] = by_status.get(st, 0) + 1
        if st not in ("new", "review"):
            continue
        pending += 1
        note = re.sub(r"\d+", "#", (r.get("auto_note") or "(ไม่มีหมายเหตุ)"))[:70]
        reasons[note] = reasons.get(note, 0) + 1
        no_amount += r.get("amount") is None
        no_course += not r.get("expected_course")
        try:
            age = (now - dt.datetime.fromisoformat(r["created_at"])).days
        except Exception:
            age = 0
        ages["<1 วัน" if age < 1 else "1-3 วัน" if age < 3 else "3-7 วัน" if age < 7 else ">7 วัน"] += 1
    return {"total": len(rows), "by_status": by_status, "pending": pending,
            "pending_no_amount": no_amount, "pending_no_expected_course": no_course,
            "pending_age": ages,
            "pending_reasons": sorted(reasons.items(), key=lambda x: -x[1])[:12]}


# userId ทุกคนที่เคยโต้ตอบ (ข้อความ/กดปุ่ม/ลงทะเบียน/ส่งสลิป) ต้องอยู่ใน line_users — เก็บตกคนที่ตกหล่น
_UID_SOURCES = (("messages", {}), ("webhook_events", {"event_type": "eq.postback"}),
                ("postback_clicks", {}), ("registrations", {}), ("slips", {}))


async def _backfill_users(apply: bool) -> dict:
    seen: dict = {}
    for tb, flt in _UID_SOURCES:
        try:
            rows = await supa.select_all(tb, params={"select": "line_user_id", **flt}, cap=300000)
        except Exception as e:
            seen.setdefault("_errors", []).append(f"{tb}: {repr(e)[:80]}")
            continue
        n = 0
        for r in rows:
            u = r.get("line_user_id")
            if u and u.startswith("U") and u not in seen:
                seen[u] = tb
                n += 1
        seen.setdefault("_by_table", {})[tb] = n
    errors, by_table = seen.pop("_errors", []), seen.pop("_by_table", {})
    known = {r["line_user_id"] for r in await supa.select_all("line_users", params={"select": "line_user_id"}, cap=300000)}
    missing = [u for u in seen if u not in known]
    if apply and missing:
        ts = NOW()
        rows = [{"line_user_id": u, "source": "backfill_" + seen[u], "updated_at": ts} for u in missing]
        for i in range(0, len(rows), 500):
            await supa.upsert("line_users", rows[i:i + 500], on_conflict="line_user_id")
    return {"apply": apply, "distinct_userids_seen": len(seen), "already_in_line_users": len(seen) - len(missing),
            "missing_added" if apply else "missing_would_add": len(missing), "new_by_first_table": by_table, "errors": errors}


async def _dg_slips():
    s = await _slips_summary()
    old = s["pending_age"]["3-7 วัน"] + s["pending_age"][">7 วัน"]
    if s["pending"] >= 30 or old:
        return f"⚠️ สลิปค้างตรวจ {s['pending']} ใบ (ค้างเกิน 3 วัน {old}) — เปิดหน้าสลิป > ต้องตรวจเอง"
    return f"✅ สลิปค้างตรวจ {s['pending']} ใบ"


_DG_NONFRIENDS_TTL = 6 * 3600


async def _dg_nonfriends():
    # งานนี้แพงสุดในสรุปประจำวัน (เช็คเพื่อนกับ LINE สดทีละคนสำหรับผู้ลงทะเบียนทุกคน ~1,000 คน ~10 วิ)
    # แต่สถานะเพื่อนของคนส่วนใหญ่ไม่เปลี่ยนรายวัน — cache ผลไว้ 6 ชม. กันรันซ้ำโดยไม่จำเป็น
    # (ปุ่ม "ตรวจสอบ" ที่หน้ากระทบยอดยังคงเรียก _flag_nonfriend_registrants ตรง ๆ แบบสดเสมอ ไม่ผ่าน cache นี้)
    cache = await _get_setting("dg_nonfriends_cache", None)
    if isinstance(cache, dict) and time.time() - float(cache.get("at") or 0) < _DG_NONFRIENDS_TTL:
        r = cache["r"]
    else:
        r = await _flag_nonfriend_registrants(False)
        await supa.upsert("app_settings", {"key": "dg_nonfriends_cache", "value": {"r": r, "at": time.time()}, "updated_at": NOW()},
                          on_conflict="key")
    n = r["non_friends"]
    extra = f" (เช็คไม่ได้ {r['unknown']})" if r.get("unknown") else ""
    if n:
        return f"⚠️ ลงทะเบียนแล้วแต่ไม่เป็นเพื่อน {n} คน{extra} — ดูรายชื่อที่หน้าลงทะเบียน > กระทบยอด"
    return f"✅ ผู้ลงทะเบียน {r['registrants']:,} คน เป็นเพื่อนครบทุกคน{extra}"


async def _dg_kb():
    total = await supa.count("kb_articles")
    pending = await supa.count("kb_articles", {"enabled": "eq.false"})
    done = set(await _get_setting(_KB_TOPIC_SETTING_KEY, []) or [])
    remain = len([t for t in _PROCUREMENT_TOPICS if t not in done])
    return (f"📚 KB: {total} บทความ" + (f" (ปิดอยู่/รอตรวจ {pending})" if pending else "")
            + (f" · ร่างอัตโนมัติเหลือ {remain} หัวข้อ" if remain else " · ร่างครบทุกหัวข้อแล้ว"))


async def _health_digest_lines() -> tuple[list[str], bool]:
    names = ["Cron", "โควต้า LINE", "EasySlip", "สลิป", "ผู้ลงทะเบียน/เพื่อน", "KB"]
    res = await asyncio.gather(
        *[asyncio.wait_for(j, 28) for j in (_dg_cron(), _dg_line_quota(), _dg_easyslip(), _dg_slips(),
                                            _dg_nonfriends(), _dg_kb())],
        return_exceptions=True)
    lines = []
    for n, r in zip(names, res):
        if isinstance(r, BaseException):
            print(f"digest health [{n}] error:", repr(r)[:150])
            lines.append(f"⚠️ เช็ค {n} ไม่ได้ ({type(r).__name__})")
        elif r:
            lines.append(r)
    return lines, any(l.startswith("⚠️") for l in lines)


async def _enroll_inactive_automations():
    """automation trigger=inactive — หา user ที่ไม่ทักมานานตาม trigger_config.days แล้ว enroll
    (dedup ด้วย unique constraint automation_runs) — เรียกจาก cron run-automations"""
    autos = await supa.select("automations", params={
        "select": "id,trigger_config", "enabled": "eq.true", "trigger": "eq.inactive"})
    for a in autos:
        cfg = a.get("trigger_config") or {}
        try:
            days = max(1, int(cfg.get("days", 14)))
        except (TypeError, ValueError):
            days = 14
        cutoff = _iso_ago(days=days)
        floor = _iso_ago(days=days + 30)  # ไม่ backfill คนที่หายไปนานมาก
        rows = await supa.select("line_users", params={
            "select": "line_user_id", "is_following": "eq.true",
            "and": f"(last_message_at.lt.{cutoff},last_message_at.gt.{floor})",
            "limit": "400"})
        uids = [r["line_user_id"] for r in rows]
        if uids:
            await _enroll_automations("inactive", uids)


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
    if f.get("stage"):
        p["stage"] = f"eq.{f['stage']}"
    # PDPA: ไม่ส่งหาคนที่ขอหยุดข่าวสาร (consent=false) เว้นแต่ระบุ includeOptOut
    if not f.get("includeOptOut"):
        p["consent"] = "not.is.false"
    return p


async def _uids_by_filter(f: dict) -> list[str]:
    rows = await supa.select_all("line_users", params=_filter_to_params(f))
    return [r["line_user_id"] for r in rows]


_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp",
        "video/mp4": "mp4", "audio/mp4": "m4a", "audio/x-m4a": "m4a"}


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


_liff_token_cache: dict = {"token": None, "exp": 0.0}


async def _liff_channel_token() -> tuple[str | None, str | None]:
    """channel access token สำหรับเรียก LIFF API — คืน (token, error)
    ลำดับ: LINE_LOGIN_CHANNEL_TOKEN ตรง ๆ > JWT assertion (Login channel) > client_credentials (Messaging API)"""
    if LINE_LOGIN_CHANNEL_TOKEN:
        return LINE_LOGIN_CHANNEL_TOKEN, None
    if _liff_token_cache["token"] and time.time() < _liff_token_cache["exp"]:
        return _liff_token_cache["token"], None

    # --- JWT assertion (LINE Login channel) ---
    if LINE_LOGIN_CHANNEL_ID and LINE_LOGIN_ASSERTION_KID and LINE_LOGIN_ASSERTION_PRIVATE_KEY:
        try:
            import jwt as _jwt
            now = int(time.time())
            assertion = _jwt.encode(
                {"iss": LINE_LOGIN_CHANNEL_ID, "sub": LINE_LOGIN_CHANNEL_ID,
                 "aud": "https://api.line.me/", "exp": now + 60 * 25,
                 "token_exp": 60 * 60 * 24 * 30},
                LINE_LOGIN_ASSERTION_PRIVATE_KEY, algorithm="RS256",
                headers={"kid": LINE_LOGIN_ASSERTION_KID})
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post("https://api.line.me/oauth2/v2.1/token", data={
                    "grant_type": "client_credentials",
                    "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                    "client_assertion": assertion,
                })
            j = r.json()
            if r.status_code == 200 and j.get("access_token"):
                _liff_token_cache["token"] = j["access_token"]
                _liff_token_cache["exp"] = time.time() + max(600, int(j.get("expires_in", 2592000)) - 86400)
                return j["access_token"], None
            return None, f"JWT assertion ไม่ผ่าน ({r.status_code}): {j.get('error_description') or j.get('error') or r.text[:150]}"
        except Exception as e:
            return None, f"JWT assertion error: {e}"

    # --- client_credentials (Messaging API channel เท่านั้น) ---
    if LINE_LOGIN_CHANNEL_ID and LINE_LOGIN_CHANNEL_SECRET:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post("https://api.line.me/v2/oauth/accessToken",
                                 data={"grant_type": "client_credentials",
                                       "client_id": LINE_LOGIN_CHANNEL_ID,
                                       "client_secret": LINE_LOGIN_CHANNEL_SECRET})
            j = r.json()
            if r.status_code == 200 and j.get("access_token"):
                _liff_token_cache["token"] = j["access_token"]
                _liff_token_cache["exp"] = time.time() + max(600, int(j.get("expires_in", 2592000)) - 86400)
                return j["access_token"], None
            err = j.get("error_description") or j.get("error") or r.text[:120]
            if "client_secret" in str(err).lower():
                err += " — channel นี้เป็น LINE Login channel: ต้องตั้ง LINE_LOGIN_ASSERTION_KID + LINE_LOGIN_ASSERTION_PRIVATE_KEY"
            return None, f"ขอ token ไม่สำเร็จ ({r.status_code}): {err}"
        except Exception as e:
            return None, str(e)

    return None, "ยังไม่ได้ตั้งค่าเชื่อม LINE Login channel (LINE_LOGIN_ASSERTION_KID + PRIVATE_KEY)"


# ============================================================
# REGISTRATIONS (รายชื่อผู้ลงทะเบียนเรียน)
# ============================================================
_REG_COLS = {
    "timestamp": "form_ts", "regid": "reg_id", "uid": "line_user_id", "name": "name",
    "tel": "tel", "สังกัด": "org", "หลักสูตร": "course_raw", "email": "email", "job": "job",
    "file": "slip_url", "ผ่าน": "passed",
}

_REG_COURSES_DEFAULT = ["FC70", "IC70", "PC70-1", "PC70-2"]
_member_tok_cache: dict = {}


async def _reg_courses() -> list:
    v = await _get_setting("reg_courses", None)
    if isinstance(v, list) and v:
        return [str(x) for x in v]
    return _REG_COURSES_DEFAULT


async def _pay_account_for(course: str) -> dict | None:
    """บัญชี/ราคาที่ตรงกับหลักสูตร (จับคู่ 2 ตัวอักษรแรก FC/IC/PC/AC) — ใช้แจ้งยอด+เลขบัญชีให้ผู้ลงทะเบียน"""
    try:
        prefix = str(course or "")[:2].upper()
        accts = await supa.select("payment_accounts", params={"select": "*", "active": "eq.true"})
        return next((a for a in accts if str(a.get("course") or "").upper().startswith(prefix)), None)
    except Exception:
        return None


async def _reg_payment_accounts_public() -> list:
    """รายการบัญชี/ราคาแบบเปิดเผยได้ (ไม่มีข้อมูลอ่อนไหว) ให้หน้าลงทะเบียนแสดงตอนเลือกหลักสูตร"""
    try:
        accts = await supa.select("payment_accounts", params={
            "select": "course,bank,account_no,account_name,price,full_price", "active": "eq.true"})
        return accts
    except Exception:
        return []


_COURSE_QR_PREFIX = "course_info:"
_course_qr_cache: dict = {"exp": 0.0, "courses": []}


def _course_prefix(s) -> str:
    return re.sub(r"[^A-Za-z]", "", str(s or "")).upper()[:2]


async def _open_courses() -> list[dict]:
    """หลักสูตรที่เปิดขาย (payment_accounts ที่ active) ไม่ซ้ำตามอักษร 2 ตัวแรก — cache 5 นาที"""
    if _course_qr_cache["exp"] > time.time():
        return _course_qr_cache["courses"]
    out: list[dict] = []
    try:
        accts = await supa.select("payment_accounts", params={
            "select": "course", "active": "eq.true", "order": "id.asc"})
        seen: set = set()
        for a in accts:
            p = _course_prefix(a.get("course"))
            if p and p not in seen:
                seen.add(p)
                out.append({"prefix": p, "label": str(a.get("course") or p)})
    except Exception as ex:  # noqa: BLE001
        print("open courses error:", ex)
        return _course_qr_cache["courses"]   # DB ล่ม -> ใช้ค่าเก่า
    _course_qr_cache.update(exp=time.time() + 300, courses=out)
    return out


async def _course_quick_reply(exclude: str | None = None, extra: list | None = None) -> dict | None:
    """quick reply ปุ่ม 'ดูรายละเอียดหลักสูตร' ของทุกหลักสูตรที่เปิด (ปิดได้ที่ setting course_quick_reply=false)
    ปุ่มส่ง postback course_info:<FC|IC|..> -> _handle_auto_replies ตอบรายละเอียดกลับ (LINE จำกัด 13 ปุ่ม)"""
    if (await _get_setting("course_quick_reply", True)) is False:
        return None
    items = []
    for c in await _open_courses():
        if c["prefix"] == exclude:
            continue
        items.append({"type": "action", "action": {
            "type": "postback", "label": f"📘 {c['label']}"[:20],
            "data": f"{_COURSE_QR_PREFIX}{c['prefix']}",
            "displayText": f"ขอดูรายละเอียดหลักสูตร {c['label']}"[:300]}})
    items = (items + list(extra or []))[:13]
    return {"items": items} if items else None


async def _attach_course_qr(msgs: list) -> list:
    """แนบ quick reply หลักสูตรกับข้อความสุดท้าย (LINE ให้ quickReply อยู่ที่ข้อความสุดท้ายเท่านั้น)
    ไม่ทับ quick reply ที่กฎ/ข้อความมีอยู่แล้ว"""
    try:
        if not msgs or not isinstance(msgs[-1], dict) or msgs[-1].get("quickReply"):
            return msgs
        qr = await _course_quick_reply()
        if not qr:
            return msgs
        return list(msgs[:-1]) + [{**msgs[-1], "quickReply": qr}]
    except Exception as ex:  # noqa: BLE001
        print("attach course qr error:", ex)
        return msgs


def _thai_date(s) -> str:
    try:
        d = dt.date.fromisoformat(str(s)[:10])
        return f"{d.day}/{d.month}/{d.year + 543}"
    except Exception:
        return str(s or "")


async def _course_info_messages(prefix: str) -> list:
    """ข้อความรายละเอียดหลักสูตร (ราคา/คลาสที่เปิด/วิธีโอน) + quick reply หลักสูตรอื่น/ลงทะเบียน/แอดมิน
    ไม่แสดงลิงก์ Zoom/เอกสาร (เป็นของผู้ลงทะเบียนแล้ว)"""
    prefix = _course_prefix(prefix)
    accts = [a for a in await supa.select("payment_accounts", params={"select": "*", "active": "eq.true"})
             if _course_prefix(a.get("course")) == prefix]
    if not accts:
        text = "ยังไม่พบรายละเอียดหลักสูตรนี้ในระบบครับ 🙏 เดี๋ยวแอดมินช่วยแจ้งให้นะครับ"
    else:
        lines = [f"📘 หลักสูตร {accts[0].get('course') or prefix}"]
        for a in accts:
            price, full = a.get("price"), a.get("full_price")
            tag = f"{a['course']}: " if len(accts) > 1 else ""
            if price is not None and full is not None and float(full) > float(price):
                lines.append(f"💰 {tag}{float(price):,.0f} บาท (ราคาเต็ม {float(full):,.0f} บาท)")
            elif price is not None or full is not None:
                lines.append(f"💰 {tag}{float(price if price is not None else full):,.0f} บาท")
        try:
            cls = await supa.select("classes", params={
                "select": "name,cohort,start_date,schedule,capacity", "course": f"like.{prefix}*",
                "status": "in.(open,running)", "order": "start_date.asc", "limit": "3"})
        except Exception:
            cls = []
        if cls:
            lines.append("")
            lines.append("📅 คลาสที่เปิด")
            for c in cls:
                title = c.get("name") or (f"รุ่น {c['cohort']}" if c.get("cohort") else "คลาส")
                start = f" · เริ่ม {_thai_date(c['start_date'])}" if c.get("start_date") else ""
                lines.append(f"• {title}{start}")
                if c.get("schedule"):
                    lines.append(f"  ตารางเรียน: {c['schedule']}")
        else:
            lines.append("")
            lines.append("📅 ยังไม่มีคลาสที่เปิดรับในตอนนี้ ติดตามประกาศได้เลยครับ")
        a0 = accts[0]
        if a0.get("account_no"):
            lines.append("")
            lines.append(f"💳 โอนเข้าบัญชี: {a0.get('bank') or '-'} {a0['account_no']} ({a0.get('account_name') or '-'})")
        text = "\n".join(lines)[:4900]
    extra = []
    reg_url = await _get_setting("reg_liff_url", None)
    if reg_url:
        extra.append({"type": "action", "action": {"type": "uri", "label": "📝 ลงทะเบียน", "uri": str(reg_url)}})
    extra.append({"type": "action", "action": {"type": "message", "label": "🙋 ติดต่อแอดมิน", "text": "ติดต่อแอดมิน"}})
    qr = await _course_quick_reply(exclude=prefix, extra=extra)
    msg = {"type": "text", "text": text}
    if qr:
        msg["quickReply"] = qr
    return [msg]


def _pay_lines(acc: dict | None) -> str:
    if not acc:
        return ""
    price = acc.get("price") or acc.get("full_price")
    out = [f"ยอดที่ต้องชำระ: {price:,.0f} บาท" if price is not None else "ยอดที่ต้องชำระ: ติดต่อแอดมิน"]
    if acc.get("bank") or acc.get("account_no"):
        out.append(f"โอนเข้าบัญชี: {acc.get('bank') or '-'} {acc.get('account_no') or ''} ({acc.get('account_name') or '-'})")
    return "\n".join(out)


async def _verify_member_token(id_token: str) -> dict | None:
    """ตรวจ LIFF id_token ของหน้าลงทะเบียนสมาชิก (channel REG_LIFF_CHANNEL_ID) — cache 5 นาที"""
    if not id_token:
        return None
    hit = _member_tok_cache.get(id_token)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post("https://api.line.me/oauth2/v2.1/verify",
                             data={"id_token": id_token, "client_id": REG_LIFF_CHANNEL_ID})
        if r.status_code != 200:
            return None
        p = r.json()
        if str(p.get("aud")) != str(REG_LIFF_CHANNEL_ID):
            return None
        if p.get("exp") and time.time() > p["exp"]:
            return None
        u = {"userId": p["sub"], "name": p.get("name", ""), "picture": p.get("picture", "")}
        _member_tok_cache[id_token] = (time.time() + 300, u)
        return u
    except Exception as e:
        print("member token verify error:", e)
        return None


_REREG_TAG = "ต้องลงทะเบียนใหม่"   # ติดที่ line_users.tags — ลงทะเบียนไว้แต่ไม่ได้เป็นเพื่อนกับบัญชี (ส่งข้อความ/สลับเมนูให้ไม่ได้)


async def _oa_add_friend_url() -> str:
    """ลิงก์เพิ่มเพื่อน — ตั้งเองได้ที่ setting oa_add_friend_url ไม่งั้นใช้ basic ID ของบัญชี (@886acdfn)"""
    return (await _get_setting("oa_add_friend_url", None)) or "https://line.me/R/ti/p/@886acdfn"


async def _user_tags(uid: str):
    """tags ของ user (list) หรือ None ถ้ายังไม่มีแถวใน line_users"""
    ex = await supa.select("line_users", params={"select": "tags", "line_user_id": f"eq.{uid}", "limit": "1"})
    return ((ex[0].get("tags") or []) if ex else None)


async def _set_rereg_flag(uid: str, on: bool):
    cur = await _user_tags(uid)
    tags = set(cur or [])
    new = (tags | {_REREG_TAG}) if on else (tags - {_REREG_TAG})
    if cur is not None and new == tags:
        return
    row = {"line_user_id": uid, "tags": sorted(new), "updated_at": NOW()}
    if cur is None:   # ยังไม่มีแถว — คนที่ไม่ได้เป็นเพื่อน จึงไม่ใช่ผู้ติดตาม
        row.update({"source": "registration", "is_following": False})
    await supa.upsert("line_users", [row], on_conflict="line_user_id")


async def _flag_nonfriend_registrants(apply: bool, detail: bool = False) -> dict:
    """ไล่เช็คกับ LINE ตรง ๆ ว่าใครที่มีแถวใน registrations ตอนนี้ไม่ได้เป็นเพื่อน (404) — ค่า is_following ใน DB
    เชื่อไม่ได้ เพราะ import/retag เคยสร้างแถวให้คนที่ไม่ได้เป็นเพื่อนด้วย is_following=true
    apply=True: ติดธง "ต้องลงทะเบียนใหม่" + แก้ is_following=false (ไม่ลบ/ไม่แตะแถว registrations และสถานะชำระเงิน)
    คนที่เช็คไม่ได้ (LINE error/429) ไม่ถูกนับเป็นไม่ใช่เพื่อน"""
    regs = await supa.select_all("registrations", params={
        "select": "id,line_user_id,course,paid,name,tel,org,created_at", "order": "created_at.desc"})
    by_uid: dict[str, list] = {}
    for r in regs:
        if r.get("line_user_id"):
            by_uid.setdefault(r["line_user_id"], []).append(r)
    uids = list(by_uid)
    status: dict = {}
    sem = asyncio.Semaphore(50)   # งาน I/O ล้วน ~900 คำขอ — ต้องจบใน ~10 วินาทีเพราะถูกเรียกจากสรุปประจำวันด้วย

    async def one(uid):
        async with sem:
            status[uid] = await line.is_friend(uid)

    await asyncio.gather(*[one(x) for x in uids])
    non = [x for x in uids if status.get(x) is False]
    by_course: dict[str, int] = {}
    for x in non:
        c = by_uid[x][0].get("course") or "?"
        by_course[c] = by_course.get(c, 0) + 1
    out = {
        "registrants": len(uids),
        "friends": sum(1 for x in uids if status.get(x) is True),
        "non_friends": len(non),
        "non_friends_paid": sum(1 for x in non if any(r.get("paid") for r in by_uid[x])),
        "unknown": sum(1 for x in uids if status.get(x) is None),
        "by_course": by_course,
    }
    if detail:
        out["items"] = [{
            "userId": x, "name": by_uid[x][0].get("name"), "tel": by_uid[x][0].get("tel"),
            "org": by_uid[x][0].get("org"), "course": by_uid[x][0].get("course"),
            "paid": any(r.get("paid") for r in by_uid[x]),
        } for x in non[:1000]]
    if apply and non:
        flagged = 0
        for i in range(0, len(non), 80):
            chunk = non[i:i + 80]
            existing = {x["line_user_id"]: x for x in await supa.select("line_users", params={
                "select": "line_user_id,tags", "line_user_id": f"in.({','.join(chunk)})", "limit": "200"})}
            patch = []
            for uid in chunk:
                cur = set((existing.get(uid) or {}).get("tags") or [])
                row = {"line_user_id": uid, "tags": sorted(cur | {_REREG_TAG}),
                       "is_following": False, "updated_at": NOW()}
                if uid not in existing:
                    row["source"] = "registration"
                patch.append(row)
            await supa.upsert("line_users", patch, on_conflict="line_user_id")
            flagged += len(patch)
        out["flagged"] = flagged
    return out


async def _mark_registrations_paid_by_ids(ids: list[int]) -> int:
    if not ids:
        return 0
    await supa.update("registrations", {"paid": True, "updated_at": NOW()},
                      {"id": f"in.({','.join(map(str, ids))})"})
    # tag จ่ายแล้ว
    regs = await supa.select("registrations", params={
        "select": "line_user_id", "id": f"in.({','.join(map(str, ids))})", "limit": "500"})
    uids = list({r["line_user_id"] for r in regs if r.get("line_user_id")})
    for i in range(0, len(uids), 60):
        chunk = uids[i:i + 60]
        try:
            ex = {u["line_user_id"]: set(u.get("tags") or []) for u in await supa.select("line_users", params={
                "select": "line_user_id,tags", "line_user_id": f"in.({','.join(chunk)})", "limit": "200"})}
            patch = [{"line_user_id": u, "tags": sorted(ex.get(u, set()) | {"จ่ายแล้ว"}), "updated_at": NOW()}
                     for u in chunk if "จ่ายแล้ว" not in ex.get(u, set())]
            if patch:
                await supa.upsert("line_users", patch, on_conflict="line_user_id")
        except Exception as e:
            print("mark-paid tag error:", e)
    return len(ids)

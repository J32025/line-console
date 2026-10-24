"""routes กลุ่ม webhook — แยกจาก api/index.py"""
from _lib import line
from _lib import supa
from _lib.auth import current_admin
from _lib.config import LINE_CHANNEL_SECRET
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
import asyncio
import base64
import datetime as dt
import hashlib
import hmac
import json
from fastapi import APIRouter
from _lib.core import (NOW, _clean_str, _dev_commands_list, _enroll_automations, _fire_and_forget, _gemini_enabled_menu_ids, _handle_auto_replies, _handle_consent_keywords, _handle_dev_commands, _handle_gemini_replies, _handle_slips, _handle_status_check, _normalize_messages, _split_postback_data, alert_admin, events)

router = APIRouter()


# webhook — รับ event จาก LINE (ไม่ต้อง auth, verify signature)
@router.post("/api/webhook")
async def webhook(request: Request):
    # ไม่มี rate limit ที่นี่ตั้งใจ: คำขอปลอมโดน 403 จากการตรวจลายเซ็น (HMAC ไม่มี I/O) ก็ไม่ทำงานต่ออยู่แล้ว
    # จำกัดอัตราไม่ได้ลดจำนวน invocation แต่จะเสี่ยงตีกลับ event จริงของ LINE ตอนแคมเปญคนคลิกพร้อมกันเยอะ
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

    # แสดง "กำลังพิมพ์…" ทันทีสำหรับ message/postback (ไม่ block)
    loading_uids = {e.get("source", {}).get("userId") for e in events
                    if e.get("type") in ("message", "postback")
                    and e.get("source", {}).get("type") == "user"
                    and e.get("source", {}).get("userId")}
    if loading_uids:
        await asyncio.gather(*[line.start_loading(u, 20) for u in loading_uids], return_exceptions=True)
    rows_ev, user_patches, follow_rows, in_msgs = [], {}, [], []
    follow_uids, unfollow_uids = [], []
    bc_clicks = []   # คลิก postback ที่มาจาก broadcast (มีรหัสแนบท้าย data)

    for ev in events:
        et = ev.get("type")
        src = ev.get("source", {})
        uid = src.get("userId")
        msg = ev.get("message", {})
        pb = ev.get("postback", {})
        if et == "postback" and pb.get("data"):
            # แกะรหัส broadcast ที่แนบท้าย data ออกก่อน (ถ้ามี) แล้วแทนที่ด้วย data สะอาด
            # -> downstream (postback_actions/auto_reply matching, events log) เห็นแต่ data เดิมเป๊ะ ไม่กระทบ match
            clean, bcid = _split_postback_data(pb["data"])
            if bcid:
                pb["data"] = clean
                if uid:
                    bc_clicks.append({"broadcast_id": bcid, "line_user_id": uid, "data": clean})
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

        # เก็บ reply token ล่าสุดของ user นี้ไว้ — ถ้าแอดมินมาตอบใน Inbox ทันช่วงที่ยังไม่หมดอายุ
        # จะได้ตอบผ่าน reply token (ฟรี) แทน push (ดู inbox_send) ไม่ทันก็ fallback ไป push ตามปกติ
        if ev.get("replyToken"):
            user_patches[uid]["last_reply_token"] = ev["replyToken"]
            user_patches[uid]["last_reply_token_at"] = event_ts

    try:
        if rows_ev:
            await supa.insert("webhook_events", rows_ev)
        if in_msgs:
            await supa.insert("messages", in_msgs)
        if follow_rows:
            await supa.insert("follow_history", follow_rows)  # noqa
        if bc_clicks:
            try:
                await supa.insert("postback_clicks", bc_clicks)
            except Exception as e:
                print("postback click log error (migration 0012 รันหรือยัง?):", e)

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
            try:
                await supa.upsert("line_users", list(user_patches.values()), on_conflict="line_user_id")
            except Exception as e:
                # คอลัมน์ last_reply_token/_at (migration 0022) อาจยังไม่ได้รัน — ตัดสองคีย์นี้ออกแล้วลองใหม่
                # กันไม่ให้การเก็บข้อมูล user ทั้งหมด (is_following/last_message ฯลฯ) พังไปด้วยจากฟีเจอร์เสริม
                print("line_users upsert error, retry without reply-token fields:", e)
                stripped = [{k: v for k, v in p.items() if k not in ("last_reply_token", "last_reply_token_at")}
                           for p in user_patches.values()]
                await supa.upsert("line_users", stripped, on_conflict="line_user_id")
    except Exception as e:
        print("webhook store error:", e)
        await alert_admin("webhook เก็บข้อมูลไม่สำเร็จ", str(e), "wh_store")

    # ---- PDPA: คำสั่งขอหยุด/รับข่าวสาร ----
    consent_uids: set = set()
    try:
        consent_uids = await _handle_consent_keywords(events)
    except Exception as e:
        print("consent kw error:", e)
    if consent_uids:
        events = [e for e in events if e.get("source", {}).get("userId") not in consent_uids]

    # ---- คำสั่งพัฒนาระบบผ่าน LINE (เฉพาะ userId ที่กำหนด, ปิดโดย default) ----
    dev_uids: set = set()
    try:
        dev_uids = await _handle_dev_commands(events)
    except Exception as e:
        print("dev command error:", e)
    if dev_uids:
        events = [e for e in events if e.get("source", {}).get("userId") not in dev_uids]

    # ---- คำสั่ง /ตรวจข้อมูล (ทุกคนใช้ได้ — เช็คสถานะตัวเองแทนรอ push แจ้งอัตโนมัติ) ----
    status_uids: set = set()
    try:
        status_uids = await _handle_status_check(events)
    except Exception as e:
        print("status check error:", e)
    if status_uids:
        events = [e for e in events if e.get("source", {}).get("userId") not in status_uids]

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

    # ---- หา user ที่อยู่บนเมนูที่เปิด Gemini (เช็ค rich menu สดทีละคน) ----
    # Gemini เป็น "ตัวสำรอง" เท่านั้น — กฎคีย์เวิร์ด/ปุ่ม/ต้อนรับ ทำงานปกติเสมอ
    # Gemini จะตอบเฉพาะ "ข้อความที่ไม่ตรงกฎไหนเลย" (แทน fallback) ของ user บนเมนู Gemini
    gemini_uids: set = set()
    text_uids = {e["source"]["userId"] for e in events
                 if e.get("type") == "message" and e.get("message", {}).get("type") == "text"
                 and e.get("replyToken") and e.get("source", {}).get("userId")}
    try:
        gmenu_ids = await _gemini_enabled_menu_ids() if text_uids else set()
        if gmenu_ids:
            async def _chk(u):
                try:
                    return u, await line.user_richmenu_get(u)
                except Exception:
                    return u, None
            for u, rid in await asyncio.gather(*[_chk(u) for u in text_uids]):
                if rid in gmenu_ids:
                    gemini_uids.add(u)
    except BaseException as e:  # noqa: BLE001
        print("gemini menu check error:", repr(e))

    # ---- auto-reply ก่อน (คีย์เวิร์ด/ปุ่ม/ต้อนรับ) — ข้าม fallback ให้ user บนเมนู Gemini ----
    replied_uids: set = set()
    try:
        replied_uids = await asyncio.wait_for(
            _handle_auto_replies(events, gemini_uids=gemini_uids), timeout=12) or set()
    except BaseException as e:  # noqa: BLE001 — webhook ต้องตอบ 200 เสมอ
        print("auto-reply error:", repr(e))

    # ---- Gemini: ตอบข้อความที่ไม่ตรงกฎ ของ user บนเมนู Gemini ----
    if gemini_uids:
        try:
            g_targets = [e for e in events
                         if e.get("type") == "message" and e.get("message", {}).get("type") == "text"
                         and e.get("source", {}).get("userId") in gemini_uids
                         and e.get("source", {}).get("userId") not in replied_uids]
            if g_targets:
                await asyncio.wait_for(_handle_gemini_replies(g_targets), timeout=28)
        except BaseException as e:  # noqa: BLE001
            print("gemini reply error:", repr(e))

    # ---- automation: trigger=follow ----
    if follow_uids:
        try:
            await _enroll_automations("follow", list(set(follow_uids)))
        except Exception as e:
            print("automation enroll error:", e)

    # ---- สลิปโอนเงิน: เข้าคิว webhook_jobs แล้วประมวลผลนอก request (webhook ตอบเร็ว ไม่ timeout) ----
    img_events = [e for e in events if e.get("type") == "message"
                  and e.get("message", {}).get("type") in ("image", "file")]
    if img_events:
        queued = False
        try:
            await supa.insert("webhook_jobs", {"kind": "slips", "payload": {"events": img_events}})
            queued = True
        except Exception as e:
            print("webhook_jobs insert failed, processing inline:", e)
        if queued:
            await _fire_and_forget("/api/internal/run-jobs")  # กระตุ้นให้รันทันที (cron เป็น backup)
        else:
            try:
                await asyncio.wait_for(_handle_slips(img_events), timeout=25)
            except BaseException as e:
                print("slip handler error:", repr(e))
    return {"ok": True}


@router.get("/api/dev-commands")
async def dev_commands_list(status: str = "", admin=Depends(current_admin)):
    """เหมือน /api/cron/dev-commands แต่ auth แบบแอดมิน — ให้หน้า ผู้ดูแล แสดงคิวได้"""
    return await _dev_commands_list(status)


router.get('/api/events')(events)


@router.post("/api/events/{eid}/reply")
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


@router.get("/api/operations")
async def operations(admin=Depends(current_admin), limit: int = 100):
    return {"operations": await supa.select("operations", params={
        "select": "*", "order": "created_at.desc", "limit": str(min(limit, 500)),
    })}

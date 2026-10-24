"""routes กลุ่ม messaging — แยกจาก api/index.py"""
from _lib import line
from _lib import supa
from _lib.auth import current_admin
from _lib.config import SUPABASE_URL
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
import asyncio
import base64
import datetime as dt
import os
import re
import time
from fastapi import APIRouter
from _lib.core import (NOW, _EXT, _broadcast_begin, _broadcast_finish, _filter_to_params, _iso_ago, _normalize_messages, _uids_by_filter, users)

router = APIRouter()


@router.post("/api/message/recipients-preview")
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
@router.get("/api/message-templates")
async def list_msg_templates(admin=Depends(current_admin)):
    return {"templates": await supa.select("message_templates", params={
        "select": "*", "order": "updated_at.desc",
    })}


@router.post("/api/message-templates")
async def save_msg_template(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    row = {"name": b["name"], "messages": _normalize_messages(b.get("messages", [])),
           "created_by": admin["userId"], "updated_at": NOW()}
    if b.get("id"):
        await supa.update("message_templates", row, {"id": f"eq.{b['id']}"})
        return {"ok": True, "id": b["id"]}
    r = await supa.insert("message_templates", row)
    return {"ok": True, "template": r[0] if r else None}


@router.delete("/api/message-templates/{tid}")
async def del_msg_template(tid: int, admin=Depends(current_admin)):
    await supa.delete("message_templates", {"id": f"eq.{tid}"})
    return {"ok": True}


@router.get("/api/broadcasts/{bid}")
async def get_broadcast(bid: int, admin=Depends(current_admin)):
    rows = await supa.select("broadcasts", params={"id": f"eq.{bid}", "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบ")
    return rows[0]


@router.get("/api/postbacks/clicks")
async def postback_clicks_summary(admin=Depends(current_admin), days: int = 30, data: str = ""):
    """สรุปการกดปุ่ม postback ทุกที่ (rich menu / broadcast / flex) จาก webhook_events
    ไม่ระบุ data = สรุปรายปุ่ม · ระบุ data = รายชื่อคนที่กดปุ่มนั้น (userId + ชื่อ + จำนวนครั้ง + ล่าสุด)"""
    days = max(1, min(days, 365))
    params = {"select": "line_user_id,postback_data,event_ts,created_at", "event_type": "eq.postback",
              "created_at": f"gte.{_iso_ago(days=days)}", "order": "created_at.desc"}
    if data:
        params["postback_data"] = f"eq.{data}"
    rows = await supa.select_all("webhook_events", params=params, cap=100000)
    rows = [r for r in rows if r.get("line_user_id") and r.get("postback_data")]
    if not data:
        agg: dict = {}
        for r in rows:
            a = agg.setdefault(r["postback_data"], {"data": r["postback_data"], "clicks": 0, "uids": set(), "last": r["created_at"]})
            a["clicks"] += 1
            a["uids"].add(r["line_user_id"])
        buttons = sorted(({"data": a["data"], "clicks": a["clicks"], "users": len(a["uids"]), "last": a["last"]}
                          for a in agg.values()), key=lambda x: -x["clicks"])
        return {"days": days, "total_clicks": len(rows), "unique_users": len({r["line_user_id"] for r in rows}),
                "buttons": buttons[:200]}
    per: dict = {}
    for r in rows:
        u = per.setdefault(r["line_user_id"], {"line_user_id": r["line_user_id"], "clicks": 0, "last": r["created_at"]})
        u["clicks"] += 1
    uids = list(per)
    for i in range(0, len(uids), 80):
        chunk = uids[i:i + 80]
        try:
            for u in await supa.select("line_users", params={
                    "select": "line_user_id,display_name", "line_user_id": f"in.({','.join(chunk)})", "limit": "80"}):
                per[u["line_user_id"]]["display_name"] = u.get("display_name")
        except Exception:
            pass
    users = sorted(per.values(), key=lambda x: -x["clicks"])
    return {"days": days, "data": data, "total_clicks": len(rows), "unique_users": len(users), "users": users[:1000]}


@router.get("/api/broadcasts/{bid}/clicks")
async def broadcast_clicks(bid: int, admin=Depends(current_admin)):
    """ใครคลิกปุ่ม postback ใน broadcast นี้บ้าง (userId + ชื่อ + ข้อมูลปุ่มที่กด + เวลา)"""
    try:
        rows = await supa.select_all("postback_clicks", params={
            "select": "line_user_id,data,clicked_at", "broadcast_id": f"eq.{bid}",
            "order": "clicked_at.desc"})
    except Exception as e:
        return {"schema_missing": True, "hint": f"ยังไม่ได้รัน migration 0012_postback_clicks.sql — {e}",
                "clicks": [], "unique_users": 0, "by_data": []}
    uids = list({r["line_user_id"] for r in rows if r.get("line_user_id")})
    names = {}
    registered: set = set()
    for i in range(0, len(uids), 80):
        chunk = uids[i:i + 80]
        try:
            for u in await supa.select("line_users", params={
                    "select": "line_user_id,display_name,picture_url,tags,stage,is_following,"
                              "last_message_at,current_rich_menu_id,rich_menu_name",
                    "line_user_id": f"in.({','.join(chunk)})", "limit": "80"}):
                names[u["line_user_id"]] = u
        except Exception:
            pass
        try:
            for r in await supa.select("registrations", params={
                    "select": "line_user_id", "line_user_id": f"in.({','.join(chunk)})", "limit": "80"}):
                if r.get("line_user_id"):
                    registered.add(r["line_user_id"])
        except Exception:
            pass
    by_data: dict = {}
    for r in rows:
        by_data.setdefault(r.get("data") or "(ไม่ระบุ)", 0)
        by_data[r.get("data") or "(ไม่ระบุ)"] += 1
    for r in rows:
        u = names.get(r["line_user_id"], {})
        r["display_name"] = u.get("display_name")
        r["picture_url"] = u.get("picture_url")
        r["tags"] = u.get("tags")
        r["stage"] = u.get("stage")
        r["is_following"] = u.get("is_following")
        r["last_message_at"] = u.get("last_message_at")
        r["rich_menu_name"] = u.get("rich_menu_name")
        r["registered"] = r["line_user_id"] in registered
    return {
        "total_clicks": len(rows), "unique_users": len(uids),
        "registered_count": len(registered), "unregistered_count": len(uids) - len(registered),
        "by_data": sorted([{"data": k, "count": v} for k, v in by_data.items()], key=lambda x: -x["count"]),
        "clicks": rows[:500],
    }


@router.post("/api/message/validate")
async def msg_validate(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    ok, txt = await line.validate_messages(_normalize_messages(b.get("messages", [])))
    return {"ok": ok, "detail": txt}


@router.post("/api/message/test")
async def msg_test(req: Request, admin=Depends(current_admin)):
    """ส่งข้อความหาตัวเอง (ผู้ที่ล็อกอินอยู่) เพื่อทดสอบก่อนส่งจริง"""
    b = await req.json()
    msgs = _normalize_messages(b.get("messages", []))
    code, txt, rid = await line.push(admin["userId"], msgs)
    if code != 200:
        raise HTTPException(400, txt)
    return {"ok": True, "requestId": rid, "to": admin["userId"]}


@router.post("/api/message/push")
async def msg_push(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    to = b.get("to")
    nd = bool(b.get("notificationDisabled"))
    msgs = _normalize_messages(b.get("messages", []))
    kind, cnt = ("multicast", len(to)) if isinstance(to, list) and len(to) > 1 else ("push", 1)
    bid, msgs = await _broadcast_begin(admin["userId"], kind, msgs, cnt)
    if isinstance(to, list):
        if len(to) == 1:
            code, txt, rid = await line.push(to[0], msgs, nd)
        else:
            code, txt, rid = await line.multicast(to, msgs, nd)
    else:
        code, txt, rid = await line.push(to, msgs, nd)
    status = "sent" if code == 200 else "failed"
    await _broadcast_finish(bid, status=status, line_request_id=rid,
                            error=None if status == "sent" else txt[:300])
    if code != 200:
        raise HTTPException(400, txt)
    return {"ok": True, "requestId": rid, "sent": cnt}


@router.post("/api/message/bulk")
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

    bid, msgs = await _broadcast_begin(admin["userId"], "multicast", msgs, len(uids))
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
    await _broadcast_finish(bid, status="sent" if status == "sent" else "failed",
                            line_request_id=last_rid[0],
                            error=None if status == "sent" else f"{res['failed']} ล้มเหลว")
    await supa.log_operation(admin["userId"], "message.bulk",
                             {"total": len(uids), "batches": len(chunks)}, res, status)
    return res


@router.post("/api/message/broadcast")
async def msg_broadcast(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    msgs = _normalize_messages(b.get("messages", []))
    following = await supa.count("line_users", {"is_following": "eq.true"})
    bid, msgs = await _broadcast_begin(admin["userId"], "broadcast", msgs, following)
    code, txt, rid = await line.broadcast(msgs)
    status = "sent" if code == 200 else "failed"
    await _broadcast_finish(bid, status=status, line_request_id=rid,
                            error=None if status == "sent" else txt[:300])
    if code != 200:
        raise HTTPException(400, txt)
    return {"ok": True, "requestId": rid}


@router.post("/api/message/multicast-from-db")
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
    bid, msgs = await _broadcast_begin(admin["userId"], "multicast", msgs, len(uids))
    last_rid, sent, failed = None, 0, 0
    for i in range(0, len(uids), 500):
        code, txt, rid = await line.multicast(uids[i:i + 500], msgs)
        last_rid = rid
        if code == 200:
            sent += len(uids[i:i + 500])
        else:
            failed += len(uids[i:i + 500])
    await _broadcast_finish(bid, status="sent" if failed == 0 else "failed", line_request_id=last_rid)
    return {"ok": failed == 0, "target": len(uids), "sent": sent, "failed": failed}


@router.get("/api/broadcasts")
async def list_broadcasts(admin=Depends(current_admin), limit: int = 50):
    return {"broadcasts": await supa.select("broadcasts", params={
        "select": "*", "order": "created_at.desc", "limit": str(limit),
    })}


# ---------- postback actions ----------
@router.get("/api/postbacks")
async def list_postbacks(admin=Depends(current_admin)):
    return {"actions": await supa.select("postback_actions", params={
        "select": "*", "order": "data"})}


@router.post("/api/postbacks")
async def save_postback(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    data = (b.get("data") or "").strip()
    if not data:
        raise HTTPException(400, "ต้องระบุ postback data")
    row = {
        "data": data, "label": b.get("label"), "enabled": b.get("enabled", True),
        "match": b.get("match", "exact"),
        "messages": _normalize_messages(b.get("messages", [])),
        "note": b.get("note"), "created_by": admin["userId"], "updated_at": NOW(),
    }
    if b.get("id"):
        await supa.update("postback_actions", row, {"id": f"eq.{b['id']}"})
        return {"ok": True, "id": b["id"]}
    await supa.upsert("postback_actions", row, on_conflict="data")
    return {"ok": True}


@router.post("/api/postbacks/import")
async def import_postbacks(req: Request, admin=Depends(current_admin)):
    """รับ list ของ postback code -> สร้าง stub (ปิดไว้) ถ้ายังไม่มี"""
    b = await req.json()
    codes = []
    for c in b.get("codes", []):
        c = str(c).strip()
        if c:
            codes.append(c)
    codes = list(dict.fromkeys(codes))
    if not codes:
        raise HTTPException(400, "ไม่มี code")
    existing = {r["data"] for r in await supa.select("postback_actions", params={
        "select": "data", "data": f"in.({','.join(codes)})", "limit": "1000"})}
    new = [{"data": c, "label": c, "enabled": False, "match": "exact",
            "messages": [{"type": "text", "text": f"[ตั้งข้อความตอบสำหรับ {c}]"}],
            "created_by": admin["userId"]} for c in codes if c not in existing]
    if new:
        for i in range(0, len(new), 100):
            await supa.insert("postback_actions", new[i:i + 100])
    return {"ok": True, "total": len(codes), "created": len(new), "existing": len(existing)}


@router.delete("/api/postbacks/{pid}")
async def delete_postback(pid: int, admin=Depends(current_admin)):
    await supa.delete("postback_actions", {"id": f"eq.{pid}"})
    return {"ok": True}


@router.get("/api/scheduled")
async def list_scheduled(admin=Depends(current_admin)):
    return {"jobs": await supa.select("scheduled_jobs", params={
        "select": "*", "order": "run_at.desc", "limit": "50",
    })}


@router.post("/api/scheduled")
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


@router.delete("/api/scheduled/{jid}")
async def cancel_scheduled(jid: int, admin=Depends(current_admin)):
    await supa.update("scheduled_jobs", {"status": "cancelled"}, {"id": f"eq.{jid}", "status": "eq.pending"})
    return {"ok": True}


@router.post("/api/upload")
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


@router.get("/api/media")
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


@router.post("/api/target/resolve")
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
    elif tg == "unregistered":
        # คนที่ติดตามอยู่ แต่ยังไม่มีแถวใน registrations เลย (ยังไม่เคยลงทะเบียนหลักสูตรไหน)
        all_uids = set(await _uids_by_filter({}))
        reg_rows = await supa.select_all("registrations", params={"select": "line_user_id"})
        registered = {r["line_user_id"] for r in reg_rows if r.get("line_user_id")}
        uids = [u for u in all_uids if u not in registered]
    elif tg == "tag":
        uids = await _uids_by_filter({"tag": b.get("tag", "")})
    elif tg == "list":
        uids = [u.strip() for u in b.get("userIds", []) if u.strip()]
    else:
        uids = await _uids_by_filter({})
    return {"count": len(uids), "userIds": uids}


@router.get("/api/segments")
async def list_segments(admin=Depends(current_admin)):
    return {"segments": await supa.select("segments", params={"select": "*", "order": "updated_at.desc"})}


@router.post("/api/segments")
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


@router.get("/api/segments/{sid}/count")
async def segment_count(sid: int, admin=Depends(current_admin)):
    rows = await supa.select("segments", params={"id": f"eq.{sid}", "select": "filter", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบ segment")
    uids = await _uids_by_filter(rows[0]["filter"])
    await supa.update("segments", {"last_count": len(uids)}, {"id": f"eq.{sid}"})
    return {"count": len(uids)}


@router.delete("/api/segments/{sid}")
async def delete_segment(sid: int, admin=Depends(current_admin)):
    await supa.delete("segments", {"id": f"eq.{sid}"})
    return {"ok": True}


# NARROWCAST (ส่งตาม demographic ของ LINE)
@router.post("/api/message/narrowcast")
async def msg_narrowcast(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    msgs = _normalize_messages(b.get("messages", []))
    demo = b.get("demographic")   # LINE filter object (age/gender/area/...)
    recipient = b.get("recipient")  # audience / redelivery object
    limit = b.get("limit")
    filter_ = {"demographic": demo} if demo else None
    bid, msgs = await _broadcast_begin(admin["userId"], "narrowcast", msgs, None)
    code, txt, rid = await line.narrowcast(msgs, recipient=recipient, filter_=filter_, limit=limit)
    status = "sent" if code in (200, 202) else "failed"
    await _broadcast_finish(bid, status=status, line_request_id=rid,
                            error=None if status == "sent" else txt[:300])
    if code not in (200, 202):
        raise HTTPException(400, txt)
    return {"ok": True, "requestId": rid}


@router.get("/api/message/narrowcast/progress")
async def narrowcast_progress(admin=Depends(current_admin), requestId: str = ""):
    r = await line._req("GET", "/v2/bot/message/progress/narrowcast", params={"requestId": requestId})
    return r.json()

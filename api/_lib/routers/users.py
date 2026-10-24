"""routes กลุ่ม users — แยกจาก api/index.py"""
from _lib import line
from _lib import supa
from _lib.auth import current_admin
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
import asyncio
import datetime as dt
import re
from fastapi import APIRouter
from _lib.core import (NOW, PIPELINE_STAGES, _INBOX_SELECT, _STAGE_LABEL, _backfill_users, _clean_str, _enroll_automations, _gather_dict, _inbox_slip_counts, _iso_ago, _normalize_messages, _parse_ts, _reply_or_push, _tok, _uids_by_filter, events, users)

router = APIRouter()


# USERS
# ---------- custom field defs ----------
@router.get("/api/fields")
async def list_fields(admin=Depends(current_admin)):
    return {"fields": await supa.select("field_defs", params={"select": "*", "order": "sort,key"})}


@router.post("/api/fields")
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


@router.delete("/api/fields/{key}")
async def del_field(key: str, admin=Depends(current_admin)):
    await supa.delete("field_defs", {"key": f"eq.{key}"})
    return {"ok": True}


router.get('/api/users')(users)


@router.post("/api/users/bulk-tag")
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
    newly: dict[str, list] = {}
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
                for tg in (set(add) - cur):
                    newly.setdefault(tg, []).append(r["line_user_id"])
        if patch:
            await supa.upsert("line_users", patch, on_conflict="line_user_id")
            n += len(patch)
    for tg, tg_uids in newly.items():
        try:
            await _enroll_automations("tag_added", tg_uids, {"tags": [tg]})
        except Exception as e:
            print("tag_added enroll error:", e)
    await supa.log_operation(admin["userId"], "users.bulk_tag", {"count": len(uids), "add": add, "remove": list(remove)}, {"changed": n})
    return {"ok": True, "target": len(uids), "changed": n}


@router.get("/api/export/users")
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


@router.post("/api/users/import")
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


@router.post("/api/users/refresh-profile")
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


@router.post("/api/users/sync-followers")
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


@router.get("/api/inbox")
async def inbox_list(admin=Depends(current_admin), limit: int = 40, offset: int = 0,
                     filter: str = "all", q: str = "", tag: str = "", stage: str = "",
                     menu: str = "", assigned: str = "", following: str = "",
                     consent: str = "", sort: str = "recent"):
    slip_counts = await _inbox_slip_counts()  # uid -> จำนวนสลิปค้างตรวจ (ใช้ทั้ง badge และคิวสลิป)

    # ---- preset พิเศษ: คิวสลิปรอตรวจ — เรียงตามสลิปล่าสุดก่อน ไม่ใช่ข้อความล่าสุด ----
    if filter == "slips":
        try:
            slip_rows = await supa.select_all("slips", params={
                "select": "line_user_id,created_at", "status": "in.(new,review)",
                "order": "created_at.desc"})
        except Exception:
            slip_rows = []
        seen, slip_uids = set(), []
        for r in slip_rows:
            uid = r.get("line_user_id")
            if uid and uid not in seen:
                seen.add(uid); slip_uids.append(uid)
        page_uids = slip_uids[offset:offset + limit]
        rows = []
        if page_uids:
            by_uid: dict[str, dict] = {}
            for i in range(0, len(page_uids), 80):
                chunk = page_uids[i:i + 80]
                for u in await supa.select("line_users", params={
                        "select": _INBOX_SELECT, "line_user_id": f"in.({','.join(chunk)})", "limit": "80"}):
                    by_uid[u["line_user_id"]] = u
            rows = [by_uid[u] for u in page_uids if u in by_uid]
        for r in rows:
            r["slip_pending"] = slip_counts.get(r["line_user_id"], 0)
        total_unread = await supa.count("line_users", {"unread": "gt.0"})
        counts = await _gather_dict(
            all=supa.count("line_users", {"last_message_at": "not.is.null"}),
            unread=supa.count("line_users", {"last_message_at": "not.is.null", "unread": "gt.0"}),
            mine=supa.count("line_users", {"last_message_at": "not.is.null", "assigned_to": f"eq.{admin['userId']}"}),
            paused=supa.count("line_users", {"last_message_at": "not.is.null", "auto_reply_paused": "eq.true"}),
            unfollowed=supa.count("line_users", {"last_message_at": "not.is.null", "is_following": "eq.false"}),
        )
        counts = {k: (v or 0) for k, v in counts.items()}
        counts["slips"] = len(slip_uids)
        return {"conversations": rows, "total_unread": total_unread, "counts": counts}

    base = {"last_message_at": "not.is.null"}

    # ---- quick preset (แถบปุ่มด้านบน) ----
    if filter == "unread":
        base["unread"] = "gt.0"
    elif filter == "mine":
        base["assigned_to"] = f"eq.{admin['userId']}"
    elif filter == "paused":
        base["auto_reply_paused"] = "eq.true"
    elif filter == "unfollowed":
        base["is_following"] = "eq.false"

    # ---- ตัวกรองละเอียด (override preset ได้ถ้าระบุ) ----
    if q.strip():
        like = f"*{q.strip()}*"
        base["or"] = f"(display_name.ilike.{like},line_user_id.ilike.{like},note.ilike.{like})"
    if tag.strip():
        base["tags"] = "cs.{" + tag.strip() + "}"
    if stage:
        base["stage"] = "is.null" if stage == "none" else f"eq.{stage}"
    if menu:
        base["current_rich_menu_id"] = "is.null" if menu == "none" else f"eq.{menu}"
    if assigned:
        base["assigned_to"] = "is.null" if assigned == "none" else f"eq.{assigned}"
    if following in ("true", "false"):
        base["is_following"] = f"eq.{following}"
    if consent in ("true", "false"):
        base["consent"] = f"eq.{consent}"
    elif consent == "unknown":
        base["consent"] = "is.null"

    order = {"recent": "last_message_at.desc.nullslast",
             "oldest": "last_message_at.asc.nullslast",
             "unread_first": "unread.desc,last_message_at.desc.nullslast"}.get(sort, "last_message_at.desc.nullslast")
    params = {
        "select": _INBOX_SELECT,
        "order": order, "limit": str(min(limit, 100)), "offset": str(offset),
        **base,
    }
    rows = await supa.select("line_users", params=params)
    for r in rows:
        r["slip_pending"] = slip_counts.get(r["line_user_id"], 0)

    total_unread = await supa.count("line_users", {"unread": "gt.0"})
    counts = await _gather_dict(
        all=supa.count("line_users", {"last_message_at": "not.is.null"}),
        unread=supa.count("line_users", {"last_message_at": "not.is.null", "unread": "gt.0"}),
        mine=supa.count("line_users", {"last_message_at": "not.is.null", "assigned_to": f"eq.{admin['userId']}"}),
        paused=supa.count("line_users", {"last_message_at": "not.is.null", "auto_reply_paused": "eq.true"}),
        unfollowed=supa.count("line_users", {"last_message_at": "not.is.null", "is_following": "eq.false"}),
    )
    counts = {k: (v or 0) for k, v in counts.items()}
    counts["slips"] = len(slip_counts)
    return {"conversations": rows, "total_unread": total_unread, "counts": counts}


@router.get("/api/inbox/meta/tags")
async def inbox_tag_list(admin=Depends(current_admin)):
    """แท็กทั้งหมดที่มีคนใช้อยู่ (ไว้ทำ autocomplete ในตัวกรอง)"""
    rows = await supa.select_all("line_users", params={
        "select": "tags", "tags": "neq.{}", "last_message_at": "not.is.null"})
    tags = sorted({t for r in rows for t in (r.get("tags") or [])})
    return {"tags": tags}


@router.get("/api/inbox/{uid}")
async def inbox_thread(uid: str, admin=Depends(current_admin), before: str = "", limit: int = 50):
    urows = await supa.select("line_users", params={
        "select": "line_user_id,display_name,picture_url,status_message,is_following,"
                  "auto_reply_paused,assigned_to,current_rich_menu_id,rich_menu_name,tags,note,unread,"
                  "stage,consent",
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


@router.post("/api/inbox/{uid}/read")
async def inbox_read(uid: str, admin=Depends(current_admin)):
    await supa.update("line_users", {"unread": 0}, {"line_user_id": f"eq.{uid}"})
    return {"ok": True}


@router.post("/api/inbox/{uid}/pause")
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


@router.post("/api/inbox/{uid}/assign")
async def inbox_assign(uid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    await supa.update("line_users", {"assigned_to": b.get("to") or None}, {"line_user_id": f"eq.{uid}"})
    return {"ok": True}


@router.post("/api/inbox/{uid}/send")
async def inbox_send(uid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    msgs = _normalize_messages(b.get("messages", []))
    code, txt, rid = await _reply_or_push(uid, msgs)
    if code != 200:
        raise HTTPException(400, txt)
    rows = [{"line_user_id": uid, "direction": "out", "by": admin["userId"],
             "msg_type": m.get("type"), "text": m.get("text"), "payload": m} for m in msgs]
    await supa.insert("messages", rows)
    await supa.update("line_users", {
        "unread": 0, "last_message_at": NOW(),
        "last_message_text": (msgs[-1].get("text") or f"[{msgs[-1].get('type')}]")[:200],
    }, {"line_user_id": f"eq.{uid}"})

    # ---- AI เรียนรู้จากคำตอบแอดมิน: ถ้าคนนี้เพิ่งถามอะไรที่ AI ตอบไม่ได้ (kb_gap) แล้วแอดมินมาตอบเองสดๆ
    # ร่างเป็นบทความ KB ให้อัตโนมัติ (ปิดใช้งานไว้ก่อน — แอดมินต้องกดเปิดเองในหน้าคลังความรู้) ----
    kb_draft_hint = None
    reply_text = next((m.get("text") for m in msgs if m.get("type") == "text" and m.get("text")), None)
    if reply_text and len(reply_text.strip()) >= 12:
        try:
            gaps = await supa.select("operations", params={
                "select": "id,params", "action": "eq.gemini.kb_gap", "status": "eq.ok",
                "created_at": f"gte.{_iso_ago(hours=6)}", "order": "created_at.desc", "limit": "50"})
            gap = next((g for g in gaps if (g.get("params") or {}).get("uid") == uid), None)
            if gap:
                question = (gap["params"].get("q") or "").strip()
                await supa.insert("kb_articles", {
                    "title": question[:60] or "คำถามจากลูกค้า", "body": reply_text.strip()[:2000],
                    "keywords": sorted(_tok(question))[:12], "category": "ร่างจาก AI (รอตรวจ)",
                    "enabled": False})
                await supa.update("operations", {"status": "used"}, {"id": f"eq.{gap['id']}"})
                kb_draft_hint = "ร่างบทความ KB จากคำตอบนี้ให้แล้ว (ปิดใช้งานไว้) — ไปตรวจ/เปิดใช้ที่หน้าคลังความรู้ AI"
        except Exception as e:
            print("kb auto-draft error:", e)

    return {"ok": True, "requestId": rid, "kb_draft_hint": kb_draft_hint}


@router.get("/api/users/{uid}")
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
    regs, slips_rows, tasks_rows, notes_n = [], [], [], 0
    try:
        regs = await supa.select("registrations", params={
            "line_user_id": f"eq.{uid}", "select": "id,course,course_raw,paid,approved,class_id", "limit": "10"})
        slips_rows = await supa.select("slips", params={
            "line_user_id": f"eq.{uid}", "select": "id,status,amount,expected_course,created_at,media_url",
            "order": "created_at.desc", "limit": "6"})
        tasks_rows = await supa.select("tasks", params={
            "line_user_id": f"eq.{uid}", "select": "id,title,status,due_at", "status": "eq.open", "limit": "10"})
        notes_n = await supa.count("contact_notes", {"line_user_id": f"eq.{uid}"})
    except Exception:
        pass
    return {"user": user, "events": events, "follow_history": follows, "live": live,
            "registrations": regs, "slips": slips_rows, "open_tasks": tasks_rows, "notes_count": notes_n,
            "stages": [{"key": s, "label": _STAGE_LABEL.get(s, s)} for s in PIPELINE_STAGES]}


@router.patch("/api/users/{uid}")
async def update_user(uid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    patch = {k: b[k] for k in ("note", "tags", "assigned_to") if k in b}
    if "stage" in b:
        patch["stage"] = b["stage"] or None
        patch["stage_at"] = NOW()
    if "consent" in b:
        patch["consent"] = b["consent"]
        patch["consent_at"] = NOW()
    if "custom" in b:
        cur = await supa.select("line_users", params={"select": "custom", "line_user_id": f"eq.{uid}", "limit": "1"})
        merged = {**((cur[0].get("custom") if cur else {}) or {}), **b["custom"]}
        patch["custom"] = {k: v for k, v in merged.items() if v not in (None, "")}
    patch["updated_at"] = NOW()
    await supa.update("line_users", patch, {"line_user_id": f"eq.{uid}"})
    return {"ok": True}


@router.get("/api/pipeline")
async def pipeline(admin=Depends(current_admin)):
    counts = {}
    for s in PIPELINE_STAGES:
        counts[s] = await supa.count("line_users", {"stage": f"eq.{s}", "is_following": "eq.true"})
    counts["_none"] = await supa.count("line_users", {"stage": "is.null", "is_following": "eq.true"})
    return {"stages": [{"key": s, "label": _STAGE_LABEL[s], "count": counts[s]} for s in PIPELINE_STAGES],
            "unstaged": counts["_none"]}


@router.get("/api/analytics/behavior")
async def analytics_behavior(admin=Depends(current_admin), days: int = 30):
    """วิเคราะห์พฤติกรรม follow/unfollow โดยละเอียด — ใครหลุด เมื่อไหร่ อยู่เมนูไหน แท็ก/สถานะอะไร
    เกี่ยวกับ broadcast ล่าสุดไหม และข้อความสุดท้ายก่อนเลิกติดตามคืออะไร"""
    days = max(7, min(days, 180))
    since = _iso_ago(days=days)

    fh = await supa.select_all("follow_history", params={
        "select": "line_user_id,action,is_unblocked,event_ts",
        "event_ts": f"gte.{since}", "order": "event_ts.asc"})

    # ---- 1) เทรนด์รายวัน ----
    daily: dict[str, dict] = {}
    for r in fh:
        k = (r.get("event_ts") or "")[:10]
        if not k:
            continue
        d = daily.setdefault(k, {"day": k, "follow": 0, "unfollow": 0, "unblock": 0})
        if r["action"] == "follow":
            d["follow"] += 1
            if r.get("is_unblocked"):
                d["unblock"] += 1
        elif r["action"] == "unfollow":
            d["unfollow"] += 1
    trend = sorted(daily.values(), key=lambda x: x["day"])

    unfollow_events = [r for r in fh if r["action"] == "unfollow" and r.get("line_user_id")]
    unfollow_uids = list({r["line_user_id"] for r in unfollow_events})

    # ---- 2) ข้อมูลผู้ใช้ที่เลิกติดตาม (เมนู/แท็ก/สถานะ/แหล่งที่มา/วันที่เริ่มติดตาม) ----
    users_by_uid: dict[str, dict] = {}
    for i in range(0, len(unfollow_uids), 80):
        chunk = unfollow_uids[i:i + 80]
        try:
            for u in await supa.select("line_users", params={
                    "select": "line_user_id,tags,stage,source,first_followed_at,followed_at,"
                              "rich_menu_name,current_rich_menu_id,follow_count,block_count",
                    "line_user_id": f"in.({','.join(chunk)})", "limit": "80"}):
                users_by_uid[u["line_user_id"]] = u
        except Exception as e:
            print("behavior analytics user chunk error:", e)

    from collections import Counter
    time_buckets = Counter()
    menu_ct: Counter = Counter()
    tag_ct: Counter = Counter()
    stage_ct: Counter = Counter()
    source_ct: Counter = Counter()
    repeat_unfollowers = 0

    for ev in unfollow_events:
        u = users_by_uid.get(ev["line_user_id"], {})
        ff = _parse_ts(u.get("first_followed_at") or u.get("followed_at"))
        et = _parse_ts(ev.get("event_ts"))
        if ff and et:
            delta = (et - ff).total_seconds()
            if delta < 3600:
                time_buckets["ภายใน 1 ชม. หลังเพิ่มเพื่อน"] += 1
            elif delta < 86400:
                time_buckets["ภายใน 1 วัน"] += 1
            elif delta < 7 * 86400:
                time_buckets["ภายใน 1 สัปดาห์"] += 1
            elif delta < 30 * 86400:
                time_buckets["ภายใน 1 เดือน"] += 1
            else:
                time_buckets["นานกว่า 1 เดือน"] += 1
        menu_ct[u.get("rich_menu_name") or "(ไม่มีเมนู)"] += 1
        stage_ct[_STAGE_LABEL.get(u.get("stage"), u.get("stage") or "(ไม่มีสถานะ)")] += 1
        source_ct[u.get("source") or "(ไม่ทราบ)"] += 1
        tags = u.get("tags") or []
        if not tags:
            tag_ct["(ไม่มีแท็ก)"] += 1
        for tg in tags:
            tag_ct[tg] += 1
        if (u.get("block_count") or 0) > 1:
            repeat_unfollowers += 1

    # ---- 3) ตัวอย่างล่าสุด: ข้อความก่อนเลิกติดตาม ----
    samples = []
    for ev in sorted(unfollow_events, key=lambda x: x.get("event_ts") or "", reverse=True)[:20]:
        uid = ev["line_user_id"]
        u = users_by_uid.get(uid, {})
        try:
            msgs = await supa.select("messages", params={
                "select": "direction,text,msg_type,created_at", "line_user_id": f"eq.{uid}",
                "order": "created_at.desc", "limit": "3"})
        except Exception:
            msgs = []
        samples.append({
            "line_user_id": uid, "unfollowed_at": ev.get("event_ts"),
            "tags": u.get("tags") or [], "stage": u.get("stage"),
            "rich_menu": u.get("rich_menu_name"),
            "last_messages": [{"dir": m["direction"], "text": (m.get("text") or f"[{m.get('msg_type')}]")[:150],
                               "at": m["created_at"]} for m in reversed(msgs)],
        })

    # ---- 4) เทียบกับ broadcast ที่เพิ่งส่งไป — เลิกติดตามภายใน 72 ชม. หลังส่งกี่คน ----
    broadcast_impact = []
    try:
        bcs = await supa.select("broadcasts", params={
            "select": "id,kind,created_at,target_count", "created_at": f"gte.{since}",
            "order": "created_at.desc", "limit": "30"})
        for bc in bcs:
            bt = _parse_ts(bc.get("created_at"))
            if not bt:
                continue
            window_end = bt + dt.timedelta(hours=72)
            cnt = sum(1 for ev in unfollow_events
                     if (et := _parse_ts(ev.get("event_ts"))) and bt <= et <= window_end)
            if cnt:
                broadcast_impact.append({
                    "broadcast_id": bc["id"], "kind": bc.get("kind"), "sent_at": bc["created_at"],
                    "target_count": bc.get("target_count"), "unfollowed_within_72h": cnt,
                    "pct": round(cnt / bc["target_count"] * 100, 1) if bc.get("target_count") else None,
                })
        broadcast_impact.sort(key=lambda x: -x["unfollowed_within_72h"])
    except Exception as e:
        print("behavior analytics broadcast error:", e)

    total_follow = sum(d["follow"] for d in trend)
    total_unfollow = sum(d["unfollow"] for d in trend)
    return {
        "days": days,
        "trend": trend,
        "totals": {"follow": total_follow, "unfollow": total_unfollow,
                   "net": total_follow - total_unfollow,
                   "churn_rate_pct": round(total_unfollow / total_follow * 100, 1) if total_follow else None,
                   "repeat_unfollowers": repeat_unfollowers},
        "time_to_unfollow": [{"bucket": k, "count": v} for k, v in time_buckets.items()],
        "by_rich_menu": sorted([{"menu": k, "count": v} for k, v in menu_ct.items()], key=lambda x: -x["count"])[:10],
        "by_tag": sorted([{"tag": k, "count": v} for k, v in tag_ct.items()], key=lambda x: -x["count"])[:15],
        "by_stage": sorted([{"stage": k, "count": v} for k, v in stage_ct.items()], key=lambda x: -x["count"]),
        "by_source": sorted([{"source": k, "count": v} for k, v in source_ct.items()], key=lambda x: -x["count"]),
        "broadcast_impact": broadcast_impact[:10],
        "recent_samples": samples,
    }


@router.get("/api/users/{uid}/timeline")
async def user_timeline(uid: str, admin=Depends(current_admin)):
    """รวมทุกกิจกรรมของลูกค้าคนนี้ เรียงตามเวลา"""
    ev: list = []

    def add(ts, kind, text, meta=None):
        if ts:
            ev.append({"at": str(ts), "kind": kind, "text": text, "meta": meta or {}})

    try:
        for m in await supa.select("messages", params={
                "select": "direction,by,msg_type,text,created_at", "line_user_id": f"eq.{uid}",
                "order": "created_at.desc", "limit": "40"}):
            who = "ลูกค้า" if m["direction"] == "in" else ({"auto": "บอท", "gemini": "Gemini",
                   "automation": "Automation", "postback": "ปุ่ม", "system": "ระบบ", "broadcast": "Broadcast"}
                   .get(m.get("by"), "แอดมิน"))
            t = (m.get("text") or f"[{m.get('msg_type')}]")[:200]
            add(m["created_at"], "message", f"{who}: {t}", {"dir": m["direction"]})
    except Exception:
        pass
    for tb, fn in (
        ("follow_history", lambda r: ("follow", "ปลดบล็อก/เพิ่มเพื่อน" if r["action"] == "follow" else "บล็อก/ลบเพื่อน")),
        ("slips", lambda r: ("slip", f"สลิป {r.get('status')} {r.get('amount') or ''} {r.get('expected_course') or ''}")),
        ("registrations", lambda r: ("registration", f"ลงทะเบียน {r.get('course_raw') or r.get('course')}"
                                     + (" (จ่ายแล้ว)" if r.get("paid") else ""))),
        ("richmenu_history", lambda r: ("richmenu", f"เปลี่ยนเมนู → {r.get('new_rich_menu_id') or 'ไม่มี'} ({r.get('source')})")),
        ("contact_notes", lambda r: (r.get("kind") or "note", f"{r.get('author') or ''}: {r.get('body')}")),
        ("tasks", lambda r: ("task", f"งาน: {r.get('title')} [{r.get('status')}]")),
    ):
        try:
            for r in await supa.select(tb, params={
                    "select": "*", "line_user_id": f"eq.{uid}", "order": "created_at.desc", "limit": "25"}):
                k, txt = fn(r)
                add(r.get("event_ts") or r.get("created_at"), k, txt)
        except Exception:
            pass
    ev.sort(key=lambda x: x["at"], reverse=True)
    return {"timeline": ev[:120]}


@router.get("/api/users/{uid}/notes")
async def user_notes(uid: str, admin=Depends(current_admin)):
    return {"notes": await supa.select("contact_notes", params={
        "line_user_id": f"eq.{uid}", "select": "*", "order": "created_at.desc", "limit": "100"})}


@router.post("/api/users/{uid}/notes")
async def user_note_add(uid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    body = (b.get("body") or "").strip()
    if not body:
        raise HTTPException(400, "โน้ตว่าง")
    r = await supa.insert("contact_notes", {
        "line_user_id": uid, "body": body, "kind": b.get("kind", "note"),
        "author": admin.get("name") or admin["userId"][:8]})
    return {"ok": True, "note": r[0] if r else None}


@router.delete("/api/users/{uid}/notes/{nid}")
async def user_note_del(uid: str, nid: int, admin=Depends(current_admin)):
    await supa.delete("contact_notes", {"id": f"eq.{nid}"})
    return {"ok": True}


@router.get("/api/users/{uid}/export")
async def user_export(uid: str, admin=Depends(current_admin)):
    """PDPA — ข้อมูลทั้งหมดของลูกค้าคนนี้ (สำหรับคำขอเข้าถึงข้อมูล)"""
    out: dict = {"exported_at": NOW(), "line_user_id": uid}
    for tb in ("line_users", "registrations", "slips", "contact_notes", "tasks", "messages",
               "webhook_events", "follow_history", "richmenu_history", "attendance", "link_clicks"):
        try:
            out[tb] = await supa.select(tb, params={
                "line_user_id": f"eq.{uid}", "select": "*", "limit": "2000"})
        except Exception as e:
            out[tb] = {"error": str(e)[:80]}
    return out


@router.post("/api/users/{uid}/forget")
async def user_forget(uid: str, req: Request, admin=Depends(current_admin)):
    """PDPA — ลบข้อมูลส่วนบุคคล (anonymize) เก็บเฉพาะสถิติรวม"""
    b = await req.json()
    if b.get("confirm") != uid:
        raise HTTPException(400, "ต้องยืนยันด้วย userId")
    await supa.update("line_users", {
        "display_name": None, "picture_url": None, "status_message": None,
        "note": None, "custom": {}, "tags": [], "consent": False, "consent_at": NOW(),
        "stage": "lost", "updated_at": NOW(),
    }, {"line_user_id": f"eq.{uid}"})
    await supa.update("registrations", {"name": None, "tel": None, "email": None, "org": None},
                     {"line_user_id": f"eq.{uid}"})
    for tb in ("contact_notes", "messages"):
        try:
            await supa.delete(tb, {"line_user_id": f"eq.{uid}"})
        except Exception:
            pass
    await supa.log_operation(admin["userId"], "users.forget", {"uid": uid}, None)
    return {"ok": True}


@router.post("/api/users/merge")
async def users_merge(req: Request, admin=Depends(current_admin)):
    """รวมบัญชีซ้ำ: ย้าย registrations/slips/tasks/notes จาก 'from' -> 'into', mark from.merged_into"""
    b = await req.json()
    src, dst = (b.get("from") or "").strip(), (b.get("into") or "").strip()
    if not (src.startswith("U") and dst.startswith("U") and src != dst):
        raise HTTPException(400, "ต้องระบุ from / into เป็น userId คนละอัน")
    moved = {}
    for tb in ("registrations", "slips", "tasks", "contact_notes", "messages", "webhook_events",
               "follow_history", "richmenu_history", "attendance"):
        try:
            r = await supa.update(tb, {"line_user_id": dst}, {"line_user_id": f"eq.{src}"})
            moved[tb] = len(r or [])
        except Exception as e:
            moved[tb] = f"err: {str(e)[:60]}"
    # รวม tags + note
    su = await supa.select("line_users", params={"select": "tags,note", "line_user_id": f"eq.{src}", "limit": "1"})
    du = await supa.select("line_users", params={"select": "tags,note", "line_user_id": f"eq.{dst}", "limit": "1"})
    if su and du:
        tags = sorted(set((su[0].get("tags") or []) + (du[0].get("tags") or [])))
        note = "\n".join(x for x in [du[0].get("note"), su[0].get("note")] if x)
        await supa.update("line_users", {"tags": tags, "note": note or None, "updated_at": NOW()},
                          {"line_user_id": f"eq.{dst}"})
    await supa.update("line_users", {"is_following": False, "merged_into": dst, "updated_at": NOW()},
                      {"line_user_id": f"eq.{src}"})
    await supa.log_operation(admin["userId"], "users.merge", {"from": src, "into": dst}, moved)
    return {"ok": True, "moved": moved}


@router.post("/api/users/import-mapped")
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


@router.post("/api/users/backfill")
async def users_backfill(admin=Depends(current_admin)):
    r = await _backfill_users(True)
    await supa.log_operation(admin["userId"], "users.backfill", None, r)
    return r

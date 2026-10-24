"""คลาส / รุ่น + เช็คชื่อ — แยกออกจาก api/index.py (ใช้ APIRouter)"""
import datetime as dt
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from _lib import line, supa
from _lib.auth import current_admin

router = APIRouter()
NOW = lambda: dt.datetime.now(dt.timezone.utc).isoformat()


# ============================================================
# CLASSES (คลาส / รุ่น) + ATTENDANCE (เช็คชื่อ)
# ============================================================
@router.get("/api/classes")
async def classes_list(admin=Depends(current_admin), course: str = "", status: str = ""):
    params = {"select": "*", "order": "start_date.desc.nullslast,id.desc", "limit": "200"}
    if course:
        params["course"] = f"eq.{course}"
    if status:
        params["status"] = f"eq.{status}"
    try:
        classes = await supa.select("classes", params=params)
    except Exception:
        return {"classes": [], "schema_missing": True,
                "hint": "ยังไม่ได้สร้างตาราง classes — รัน migration 0009 ใน Supabase SQL Editor"}
    if classes:
        ids = [c["id"] for c in classes]
        counts: dict = {}
        for r in await supa.select("registrations", params={
                "select": "class_id", "class_id": f"in.({','.join(map(str, ids))})", "limit": "5000"}):
            counts[r["class_id"]] = counts.get(r["class_id"], 0) + 1
        for c in classes:
            c["enrolled"] = counts.get(c["id"], 0)
    return {"classes": classes}


@router.post("/api/classes")
async def class_save(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    row = {k: b[k] for k in ("course", "name", "cohort", "start_date", "end_date", "schedule",
                             "zoom_url", "materials_url", "capacity", "status", "note") if k in b}
    if not row.get("course"):
        raise HTTPException(400, "ต้องระบุหลักสูตร")
    row["updated_at"] = NOW()
    if b.get("id"):
        await supa.update("classes", row, {"id": f"eq.{b['id']}"})
        return {"ok": True, "id": b["id"]}
    row["created_by"] = admin["userId"]
    r = await supa.insert("classes", row)
    return {"ok": True, "class": r[0] if r else None}


@router.delete("/api/classes/{cid}")
async def class_delete(cid: int, admin=Depends(current_admin)):
    await supa.update("registrations", {"class_id": None}, {"class_id": f"eq.{cid}"})
    await supa.delete("classes", {"id": f"eq.{cid}"})
    return {"ok": True}


@router.get("/api/classes/{cid}")
async def class_detail(cid: int, admin=Depends(current_admin)):
    rows = await supa.select("classes", params={"id": f"eq.{cid}", "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบ")
    cls = rows[0]
    base = (cls.get("course") or "")[:2].upper()
    roster = await supa.select("registrations", params={
        "select": "id,line_user_id,name,tel,course,course_raw,paid,class_id,exam_passed",
        "class_id": f"eq.{cid}", "order": "name.asc", "limit": "1000"})
    # ผู้ที่ยังไม่ถูก assign เข้าคลาสไหน แต่คอร์สตรง
    avail = await supa.select("registrations", params={
        "select": "id,line_user_id,name,tel,course_raw,paid", "class_id": "is.null",
        "course": f"like.{base}*", "limit": "500"})
    att = await supa.select("attendance", params={
        "select": "line_user_id,session,present", "class_id": f"eq.{cid}", "limit": "5000"})
    sessions = sorted({a["session"] for a in att})
    att_map: dict = {}
    for a in att:
        att_map.setdefault(a["line_user_id"], {})[a["session"]] = a["present"]
    return {"class": cls, "roster": roster, "available": avail,
            "sessions": sessions, "attendance": att_map}


@router.post("/api/classes/{cid}/assign")
async def class_assign(cid: int, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    ids = [int(x) for x in b.get("registrationIds", []) if str(x).isdigit()]
    if not ids:
        raise HTTPException(400, "ไม่มีรายการ")
    val = cid if b.get("mode") != "remove" else None
    await supa.update("registrations", {"class_id": val, "updated_at": NOW()},
                      {"id": f"in.({','.join(map(str, ids))})"})
    return {"ok": True, "changed": len(ids)}


@router.post("/api/classes/{cid}/attendance")
async def class_attendance(cid: int, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    session = int(b.get("session", 1))
    recs = b.get("records", [])
    rows = [{"class_id": cid, "line_user_id": r["line_user_id"], "session": session,
             "present": bool(r.get("present", True)), "marked_by": admin["userId"]}
            for r in recs if r.get("line_user_id")]
    if rows:
        await supa.upsert("attendance", rows, on_conflict="class_id,line_user_id,session")
    return {"ok": True, "marked": len(rows)}


@router.post("/api/classes/{cid}/message")
async def class_message(cid: int, req: Request, admin=Depends(current_admin)):
    rows = await supa.select("classes", params={"id": f"eq.{cid}", "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบคลาส")
    cls = rows[0]
    b = await req.json()
    roster = await supa.select("registrations", params={
        "select": "line_user_id,name,course_raw", "class_id": f"eq.{cid}", "limit": "1000"})
    uids = list({r["line_user_id"] for r in roster if r.get("line_user_id")})
    if not uids:
        raise HTTPException(400, "คลาสนี้ยังไม่มีนักเรียน")
    text = (b.get("text") or "")
    text = (text.replace("{zoom}", cls.get("zoom_url") or "")
                .replace("{materials}", cls.get("materials_url") or "")
                .replace("{class}", cls.get("name") or cls.get("course") or "")
                .replace("{schedule}", cls.get("schedule") or "")
                .replace("{start}", str(cls.get("start_date") or "")))
    msgs = [{"type": "text", "text": text}]
    sent = failed = 0
    for i in range(0, len(uids), 500):
        code, *_ = await line.multicast(uids[i:i + 500], msgs)
        if code == 200:
            sent += len(uids[i:i + 500])
        else:
            failed += len(uids[i:i + 500])
    await supa.insert("broadcasts", {"actor": admin["userId"], "kind": "multicast",
                                     "target_count": len(uids), "messages": msgs,
                                     "status": "sent" if not failed else "failed"})
    return {"ok": not failed, "sent": sent, "failed": failed}

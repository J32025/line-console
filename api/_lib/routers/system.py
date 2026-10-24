"""routes กลุ่ม system — แยกจาก api/index.py"""
from _lib import supa
from _lib.auth import current_admin
from _lib.config import APP_URL
from _lib.config import LIFF_CHANNEL_ID
from _lib.config import LINE_LOGIN_ASSERTION_KID
from _lib.config import LINE_LOGIN_ASSERTION_PRIVATE_KEY
from _lib.config import LINE_LOGIN_CHANNEL_ID
from _lib.config import LINE_LOGIN_CHANNEL_SECRET
from _lib.config import LINE_LOGIN_CHANNEL_TOKEN
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
import httpx
import os
import re
from fastapi import APIRouter
from _lib.core import (NOW, _client_ip, _liff_channel_token, _liff_meta, _rate_ok_db, health, users)

router = APIRouter()


# health / me
@router.api_route("/r/{code}", methods=["GET"])
async def short_redirect(code: str, request: Request):
    from fastapi.responses import RedirectResponse
    rows = await supa.select("short_links", params={"code": f"eq.{code}", "select": "*", "limit": "1"})
    if not rows:
        return RedirectResponse(APP_URL, status_code=302)
    sl = rows[0]
    # เกินโควต้า = ยังพาไปปลายทางตามปกติ แค่ไม่บันทึกคลิก (ไม่บล็อกคนจริง กันปั่นยอด/ปั่น DB เท่านั้น)
    if await _rate_ok_db(f"r:{_client_ip(request)}", 120, 60):
        try:
            await supa.insert("link_clicks", {
                "code": code, "target": sl["target"], "broadcast_id": sl.get("broadcast_id"),
                "line_user_id": request.query_params.get("u"),
            })
            await supa.update("short_links", {"clicks": (sl.get("clicks") or 0) + 1}, {"code": f"eq.{code}"})
        except Exception:
            pass
    return RedirectResponse(sl["target"], status_code=302)


@router.get("/api/links")
async def links_list(admin=Depends(current_admin)):
    return {"links": await supa.select("short_links", params={
        "select": "*", "order": "created_at.desc", "limit": "100"})}


@router.post("/api/links")
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


@router.get("/api/links/{code}/stats")
async def link_stats(code: str, admin=Depends(current_admin)):
    clicks = await supa.select("link_clicks", params={
        "code": f"eq.{code}", "select": "clicked_at,line_user_id", "order": "clicked_at.desc", "limit": "1000"})
    by_day: dict[str, int] = {}
    for c in clicks:
        by_day[c["clicked_at"][:10]] = by_day.get(c["clicked_at"][:10], 0) + 1
    return {"total": len(clicks), "unique_users": len({c["line_user_id"] for c in clicks if c["line_user_id"]}),
            "by_day": [{"day": k, "clicks": v} for k, v in sorted(by_day.items())]}


@router.delete("/api/links/{code}")
async def link_delete(code: str, admin=Depends(current_admin)):
    await supa.delete("short_links", {"code": f"eq.{code}"})
    return {"ok": True}


router.get('/api/health')(health)


@router.get("/api/me")
async def me(admin=Depends(current_admin)):
    return admin


@router.get("/api/search")
async def global_search(admin=Depends(current_admin), q: str = ""):
    q = (q or "").strip()
    if len(q) < 2:
        return {"users": [], "registrations": [], "tasks": []}
    like = f"*{q}*"
    users = await supa.select("line_users", params={
        "select": "line_user_id,display_name,picture_url,tags,stage,is_following",
        "or": f"(display_name.ilike.{like},line_user_id.ilike.{like},note.ilike.{like})", "limit": "20"})
    regs = await supa.select("registrations", params={
        "select": "id,line_user_id,name,tel,email,org,course_raw,paid",
        "or": f"(name.ilike.{like},tel.ilike.{like},email.ilike.{like},org.ilike.{like})", "limit": "20"})
    tasks = []
    try:
        tasks = await supa.select("tasks", params={
            "select": "id,title,status,line_user_id,due_at", "title": f"ilike.{like}", "limit": "20"})
    except Exception:
        pass
    return {"users": users, "registrations": regs, "tasks": tasks}


@router.get("/api/liff")
async def liff_list(admin=Depends(current_admin)):
    stored = await supa.select("liff_apps", params={"select": "*", "order": "is_primary.desc,updated_at.desc"})
    # sync จาก LINE — ดึงรายการ LIFF ทั้งหมดของ Login channel
    line_apps, sync_err = [], None
    token, terr = await _liff_channel_token()
    if terr:
        sync_err = terr
    elif token:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get("https://api.line.me/liff/v1/apps",
                                headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                line_apps = r.json().get("apps", [])
            elif r.status_code == 401:
                sync_err = "token ไม่ผ่าน — channel secret/id อาจผิด หรือไม่ใช่ Login channel"
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

    return {
        "apps": merged,
        "line_count": len(line_apps),
        "env": {
            "VITE_LIFF_ID": os.environ.get("VITE_LIFF_ID"),
            "LIFF_CHANNEL_ID": LIFF_CHANNEL_ID,
            "LINE_LOGIN_CHANNEL_ID": LINE_LOGIN_CHANNEL_ID,
            "recommendedEndpoint": APP_URL,
        },
        "syncEnabled": bool(token),
        "syncMode": ("token" if LINE_LOGIN_CHANNEL_TOKEN
                     else "jwt" if (LINE_LOGIN_ASSERTION_KID and LINE_LOGIN_ASSERTION_PRIVATE_KEY)
                     else "client_credentials" if LINE_LOGIN_CHANNEL_SECRET else "off"),
        "syncError": sync_err,
    }


@router.post("/api/liff")
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


@router.delete("/api/liff/{liff_id}")
async def liff_delete(liff_id: str, admin=Depends(current_admin)):
    await supa.delete("liff_apps", {"liff_id": f"eq.{liff_id}"})
    return {"ok": True}


@router.get("/api/settings")
async def get_settings(admin=Depends(current_admin)):
    rows = await supa.select("app_settings", params={"select": "*"})
    return {"settings": {r["key"]: r["value"] for r in rows}}


@router.post("/api/settings")
async def set_setting(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    await supa.upsert("app_settings", {"key": b["key"], "value": b["value"], "updated_at": NOW()},
                      on_conflict="key")
    return {"ok": True}


@router.get("/api/admins")
async def list_admins(admin=Depends(current_admin)):
    return {"admins": await supa.select("admins", params={"select": "*", "order": "added_at"})}


@router.post("/api/admins")
async def add_admin(req: Request, admin=Depends(current_admin)):
    if admin.get("role") not in ("owner", "admin"):
        raise HTTPException(403, "ต้องเป็น owner/admin")
    b = await req.json()
    await supa.upsert("admins", {
        "line_user_id": b["lineUserId"], "name": b.get("name"), "role": b.get("role", "admin"),
    }, on_conflict="line_user_id")
    return {"ok": True}


@router.delete("/api/admins/{uid}")
async def del_admin(uid: str, admin=Depends(current_admin)):
    if admin.get("role") != "owner":
        raise HTTPException(403, "ต้องเป็น owner")
    await supa.delete("admins", {"line_user_id": f"eq.{uid}"})
    return {"ok": True}

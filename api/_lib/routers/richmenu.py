"""routes กลุ่ม richmenu — แยกจาก api/index.py"""
from _lib import line
from _lib import supa
from _lib.auth import current_admin
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
import asyncio
import base64
from fastapi import APIRouter
from _lib.core import (NOW, _fetch_current_menu_map, _get_setting, _log_richmenu_diffs, _richmenu_auto_unregistered, _richmenu_usage_data, _sync_richmenu_for, _uids_by_filter)

router = APIRouter()


# RICH MENU
@router.get("/api/richmenus")
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
    # แนบค่า gemini_enabled/gemini_temperature ของแต่ละเมนู (ตั้งจากหน้าเว็บ) เข้าไปในผลลัพธ์
    try:
        gsettings = await supa.select("rich_menus", params={
            "select": "rich_menu_id,gemini_enabled,gemini_temperature"})
        gmap = {g["rich_menu_id"]: g for g in gsettings}
    except Exception:
        gmap = {}
    for m in menus:
        g = gmap.get(m["richMenuId"]) or {}
        m["geminiEnabled"] = bool(g.get("gemini_enabled"))
        try:
            m["geminiTemperature"] = float(g.get("gemini_temperature") or 0.7)
        except (TypeError, ValueError):
            m["geminiTemperature"] = 0.7
    return {"menus": menus, "defaultRichMenuId": default_id, "aliases": aliases}


@router.post("/api/richmenu/{rid}/gemini")
async def set_menu_gemini(rid: str, req: Request, admin=Depends(current_admin)):
    """เปิด/ปิด Gemini + ตั้งความเข้มข้นของคำตอบ (temperature) แยกตามเมนู"""
    b = await req.json()
    enabled = bool(b.get("enabled"))
    try:
        temperature = float(b.get("temperature", 0.7))
    except (TypeError, ValueError):
        raise HTTPException(400, "temperature ต้องเป็นตัวเลข")
    temperature = max(0.0, min(2.0, temperature))
    await supa.update("rich_menus",
                       {"gemini_enabled": enabled, "gemini_temperature": temperature},
                       params={"rich_menu_id": f"eq.{rid}"})
    await supa.log_operation(admin["userId"], "richmenu.gemini_settings",
                             {"richMenuId": rid, "enabled": enabled, "temperature": temperature},
                             {"ok": True})
    return {"ok": True, "richMenuId": rid, "enabled": enabled, "temperature": temperature}


@router.get("/api/richmenu/usage")
async def richmenu_usage(admin=Depends(current_admin)):
    return await _richmenu_usage_data()


@router.post("/api/richmenu/default")
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


@router.delete("/api/richmenu/default")
async def clear_default(admin=Depends(current_admin)):
    ok = await line.richmenu_clear_default()
    await supa.log_operation(admin["userId"], "richmenu.clear_default", None, {"ok": ok})
    return {"ok": ok}


@router.post("/api/richmenu/create")
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


@router.post("/api/richmenu/{rid}/image")
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


@router.delete("/api/richmenu/{rid}")
async def delete_menu(rid: str, admin=Depends(current_admin)):
    ok = await line.richmenu_delete(rid)
    await supa.log_operation(admin["userId"], "richmenu.delete", {"richMenuId": rid}, {"ok": ok})
    return {"ok": ok}


@router.post("/api/richmenu/alias")
async def create_alias(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    ok, txt = await line.richmenu_alias_create(b["richMenuAliasId"], b["richMenuId"])
    if not ok:
        raise HTTPException(400, txt)
    return {"ok": True}


@router.delete("/api/richmenu/alias/{alias_id}")
async def delete_alias(alias_id: str, admin=Depends(current_admin)):
    return {"ok": await line.richmenu_alias_delete(alias_id)}


@router.post("/api/richmenu/assign")
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

    old_map = await _fetch_current_menu_map(uids)
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

    await _log_richmenu_diffs(old_map, patch_rows, mode, admin["userId"])

    await supa.log_operation(admin["userId"], f"richmenu.{mode}",
                             {"richMenuId": rid, "target": target, "count": len(uids)}, results,
                             "ok" if results["fail"] == 0 else "partial")
    return {"total": len(uids), **results}


@router.post("/api/richmenu/sync")
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
    summary = await _sync_richmenu_for(uids, source="sync", actor=admin["userId"])
    await supa.log_operation(admin["userId"], "richmenu.sync", {"count": len(uids)}, summary)
    return summary


@router.get("/api/richmenu/history")
async def richmenu_history(request: Request, admin=Depends(current_admin)):
    """ประวัติการเปลี่ยน rich menu — ?userId= กรองรายคน, ?limit=&offset= pagination"""
    uid = (request.query_params.get("userId") or "").strip()
    try:
        limit = min(int(request.query_params.get("limit", "100")), 500)
        offset = max(int(request.query_params.get("offset", "0")), 0)
    except ValueError:
        limit, offset = 100, 0
    params = {"select": "*", "order": "created_at.desc", "limit": str(limit), "offset": str(offset)}
    count_params = {}
    if uid:
        params["line_user_id"] = f"eq.{uid}"
        count_params["line_user_id"] = f"eq.{uid}"
    try:
        rows = await supa.select("richmenu_history", params=params)
        total = await supa.count("richmenu_history", count_params)
    except Exception as e:
        # ตาราง richmenu_history ยังไม่ถูกสร้าง (migration 0003 ยังไม่รัน)
        return {"items": [], "total": 0, "limit": limit, "offset": offset,
                "schema_missing": True,
                "hint": "ยังไม่ได้สร้างตาราง richmenu_history — รัน migration 0003 ใน Supabase SQL Editor"}
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.post("/api/richmenu/auto-unregistered/run")
async def richmenu_auto_unregistered_run(admin=Depends(current_admin)):
    if not await _get_setting("unregistered_richmenu_id"):
        raise HTTPException(400, "ยังไม่ได้ตั้งค่า Rich Menu สำหรับคนที่ยังไม่ลงทะเบียน (หน้า ผู้ดูแล)")
    res = await _richmenu_auto_unregistered(limit=1000)
    await supa.log_operation(admin["userId"], "richmenu.auto_unregistered", {"manual": True}, res)
    return {"ok": True, **res}

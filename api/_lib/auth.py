"""ตรวจ LIFF id_token + เช็คสิทธิ์ admin"""
import time

import httpx
from fastapi import Header, HTTPException

from .config import LIFF_CHANNEL_ID, LINE_API, OPEN_SIGNUP
from . import supa

_cache: dict[str, tuple[float, dict]] = {}


async def verify_id_token(id_token: str) -> dict:
    if not id_token:
        raise HTTPException(401, "ไม่ได้ส่ง id token")
    if not LIFF_CHANNEL_ID.isdigit():
        raise HTTPException(500, f"LIFF_CHANNEL_ID ต้องเป็นตัวเลข (now: {LIFF_CHANNEL_ID!r})")

    hit = _cache.get(id_token)
    if hit and hit[0] > time.time():
        return hit[1]

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{LINE_API}/oauth2/v2.1/verify",
            data={"id_token": id_token, "client_id": LIFF_CHANNEL_ID},
        )
    if r.status_code != 200:
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise HTTPException(401, f"ตรวจ token ไม่ผ่าน: {body.get('error_description') or r.text[:120]}")
    p = r.json()
    if str(p.get("aud")) != str(LIFF_CHANNEL_ID):
        raise HTTPException(401, "token ผิด channel")
    if p.get("exp") and time.time() > p["exp"]:
        raise HTTPException(401, "token หมดอายุ")

    user = {"userId": p["sub"], "name": p.get("name", ""), "picture": p.get("picture", "")}
    _cache[id_token] = (time.time() + 300, user)
    return user


async def current_admin(authorization: str = Header(default="")) -> dict:
    token = authorization[7:] if authorization.lower().startswith("bearer ") else authorization
    user = await verify_id_token(token)

    rows = await supa.select("admins", params={
        "line_user_id": f"eq.{user['userId']}", "select": "line_user_id,name,role", "limit": "1",
    })
    if rows:
        return {**user, "role": rows[0]["role"], "is_admin": True}

    if OPEN_SIGNUP:
        # bootstrap: คนแรกที่ล็อกอินกลายเป็น owner ถ้าตาราง admins ว่าง
        any_admin = await supa.count("admins")
        role = "owner" if any_admin == 0 else "admin"
        await supa.upsert("admins", {
            "line_user_id": user["userId"], "name": user["name"], "role": role,
        }, on_conflict="line_user_id")
        return {**user, "role": role, "is_admin": True}

    raise HTTPException(403, f"บัญชีนี้ไม่มีสิทธิ์ ({user['userId']})")

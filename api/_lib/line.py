"""LINE Messaging API client"""
import asyncio

import httpx

from .config import LINE_API, LINE_DATA_API, LINE_CHANNEL_ACCESS_TOKEN


def _auth() -> dict:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        raise RuntimeError("ยังไม่ได้ตั้ง LINE_CHANNEL_ACCESS_TOKEN")
    return {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}


async def _req(method: str, path: str, *, base=LINE_API, json=None, params=None, retries=3):
    url = f"{base}{path}"
    async with httpx.AsyncClient(timeout=30) as c:
        for attempt in range(retries):
            r = await c.request(method, url, headers=_auth(), json=json, params=params)
            if r.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            return r
        return r


# ---------- bot / quota / insight ----------
async def bot_info():
    r = await _req("GET", "/v2/bot/info")
    r.raise_for_status()
    return r.json()


async def message_quota():
    r = await _req("GET", "/v2/bot/message/quota")
    q = r.json() if r.status_code == 200 else {}
    r2 = await _req("GET", "/v2/bot/message/quota/consumption")
    used = r2.json().get("totalUsage") if r2.status_code == 200 else None
    return {"quota": q, "totalUsage": used}

async def insight_followers(date: str):
    r = await _req("GET", "/v2/bot/insight/followers", params={"date": date})
    return r.json()

async def insight_demographic():
    r = await _req("GET", "/v2/bot/insight/demographic")
    return r.json()

async def insight_message_delivery(date: str):
    r = await _req("GET", "/v2/bot/insight/message/delivery", params={"date": date})
    return r.json()


# ---------- profile / followers ----------
async def get_message_content(message_id: str):
    """ดาวน์โหลดไฟล์รูป/วิดีโอที่ user ส่งมา (คืน bytes, content_type)"""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{LINE_DATA_API}/v2/bot/message/{message_id}/content", headers=_auth())
        if r.status_code != 200:
            return None, None
        return r.content, r.headers.get("content-type", "image/jpeg")


async def get_profile(user_id: str):
    r = await _req("GET", f"/v2/bot/profile/{user_id}")
    if r.status_code == 200:
        return r.json()
    return None

async def followers_ids(limit=1000, start=None):
    params = {"limit": limit}
    if start:
        params["start"] = start
    r = await _req("GET", "/v2/bot/followers/ids", params=params)
    r.raise_for_status()
    return r.json()


# ---------- rich menu ----------
async def richmenu_list():
    r = await _req("GET", "/v2/bot/richmenu/list")
    r.raise_for_status()
    return r.json().get("richmenus", [])

async def richmenu_get(rid: str):
    r = await _req("GET", f"/v2/bot/richmenu/{rid}")
    return r.json() if r.status_code == 200 else None

async def richmenu_create(payload: dict):
    r = await _req("POST", "/v2/bot/richmenu", json=payload)
    r.raise_for_status()
    return r.json()

async def richmenu_delete(rid: str):
    r = await _req("DELETE", f"/v2/bot/richmenu/{rid}")
    return r.status_code == 200

async def richmenu_upload_image(rid: str, content: bytes, content_type: str):
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{LINE_DATA_API}/v2/bot/richmenu/{rid}/content",
            headers={**_auth(), "Content-Type": content_type},
            content=content,
        )
    return r.status_code == 200, r.text

async def richmenu_get_default():
    r = await _req("GET", "/v2/bot/user/all/richmenu")
    return r.json().get("richMenuId") if r.status_code == 200 else None

async def richmenu_set_default(rid: str):
    r = await _req("POST", f"/v2/bot/user/all/richmenu/{rid}")
    return r.status_code == 200, r.text

async def richmenu_clear_default():
    r = await _req("DELETE", "/v2/bot/user/all/richmenu")
    return r.status_code == 200

async def user_richmenu_get(user_id: str):
    r = await _req("GET", f"/v2/bot/user/{user_id}/richmenu")
    if r.status_code == 200:
        return r.json().get("richMenuId", "")
    if r.status_code == 404:
        return None
    r.raise_for_status()

async def user_richmenu_link(user_id: str, rid: str):
    r = await _req("POST", f"/v2/bot/user/{user_id}/richmenu/{rid}")
    return r.status_code == 200, r.status_code

async def user_richmenu_unlink(user_id: str):
    r = await _req("DELETE", f"/v2/bot/user/{user_id}/richmenu")
    return r.status_code == 200

async def richmenu_bulk_link(user_ids: list[str], rid: str):
    r = await _req("POST", "/v2/bot/richmenu/bulk/link",
                   json={"richMenuId": rid, "userIds": user_ids})
    return r.status_code == 202, r.text

async def richmenu_bulk_unlink(user_ids: list[str]):
    r = await _req("POST", "/v2/bot/richmenu/bulk/unlink", json={"userIds": user_ids})
    return r.status_code == 202, r.text

# rich menu alias
async def richmenu_alias_list():
    r = await _req("GET", "/v2/bot/richmenu/alias/list")
    return r.json().get("aliases", []) if r.status_code == 200 else []

async def richmenu_alias_create(alias_id: str, rid: str):
    r = await _req("POST", "/v2/bot/richmenu/alias",
                   json={"richMenuAliasId": alias_id, "richMenuId": rid})
    return r.status_code == 200, r.text

async def richmenu_alias_delete(alias_id: str):
    r = await _req("DELETE", f"/v2/bot/richmenu/alias/{alias_id}")
    return r.status_code == 200


# ---------- messaging ----------
async def start_loading(user_id: str, seconds: int = 20):
    """แสดงจุดกระพริบ (กำลังพิมพ์…) ในแชตของ user"""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            await c.post(f"{LINE_API}/v2/bot/chat/loading/start", headers=_auth(),
                         json={"chatId": user_id, "loadingSeconds": max(5, min(seconds, 60))})
    except Exception:
        pass


async def reply(reply_token: str, messages: list):
    # reply token หมดอายุเร็ว — ไม่ต้อง retry, timeout สั้น
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{LINE_API}/v2/bot/message/reply", headers=_auth(),
                             json={"replyToken": reply_token, "messages": messages})
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


async def push(to: str, messages: list, notification_disabled=False):
    r = await _req("POST", "/v2/bot/message/push",
                   json={"to": to, "messages": messages,
                         "notificationDisabled": notification_disabled})
    return r.status_code, r.text, r.headers.get("x-line-request-id")

async def multicast(to: list[str], messages: list, notification_disabled=False):
    r = await _req("POST", "/v2/bot/message/multicast",
                   json={"to": to, "messages": messages,
                         "notificationDisabled": notification_disabled})
    return r.status_code, r.text, r.headers.get("x-line-request-id")

async def broadcast(messages: list):
    r = await _req("POST", "/v2/bot/message/broadcast", json={"messages": messages})
    return r.status_code, r.text, r.headers.get("x-line-request-id")

async def narrowcast(messages: list, recipient=None, filter_=None, limit=None):
    body = {"messages": messages}
    if recipient:
        body["recipient"] = recipient
    if filter_:
        body["filter"] = filter_
    if limit:
        body["limit"] = limit
    r = await _req("POST", "/v2/bot/message/narrowcast", json=body)
    return r.status_code, r.text, r.headers.get("x-line-request-id")

async def validate_messages(messages: list):
    r = await _req("POST", "/v2/bot/message/validate/push", json={"messages": messages})
    return r.status_code == 200, r.text

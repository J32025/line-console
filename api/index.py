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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from _lib import line, supa
from _lib.auth import current_admin
from _lib.config import LINE_CHANNEL_SECRET, CRON_SECRET

app = FastAPI(title="LINE Console API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

NOW = lambda: dt.datetime.now(dt.timezone.utc).isoformat()


# ============================================================
# health / me
# ============================================================
@app.get("/api/health")
async def health():
    return {"ok": True, "time": NOW()}


@app.get("/api/me")
async def me(admin=Depends(current_admin)):
    return admin


# ============================================================
# webhook — รับ event จาก LINE (ไม่ต้อง auth, verify signature)
# ============================================================
@app.post("/api/webhook")
async def webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("x-line-signature", "")
    if LINE_CHANNEL_SECRET:
        mac = hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(base64.b64encode(mac).decode(), sig):
            raise HTTPException(403, "bad signature")

    data = json.loads(body or "{}")
    events = data.get("events", [])
    rows_ev, user_patches = [], {}

    for ev in events:
        et = ev.get("type")
        src = ev.get("source", {})
        uid = src.get("userId")
        msg = ev.get("message", {})
        rows_ev.append({
            "event_type": et, "line_user_id": uid,
            "message_type": msg.get("type"), "text": msg.get("text"),
            "payload": ev,
        })
        if not uid:
            continue
        if et == "follow":
            user_patches[uid] = {
                "line_user_id": uid, "is_following": True,
                "followed_at": NOW(), "unfollowed_at": None,
                "source": "webhook", "updated_at": NOW(),
            }
        elif et == "unfollow":
            user_patches[uid] = {
                "line_user_id": uid, "is_following": False,
                "unfollowed_at": NOW(), "source": "webhook", "updated_at": NOW(),
            }
        else:
            user_patches.setdefault(uid, {
                "line_user_id": uid, "is_following": True,
                "source": "webhook", "updated_at": NOW(),
            })

    try:
        if rows_ev:
            await supa.insert("webhook_events", rows_ev)
        if user_patches:
            await supa.upsert("line_users", list(user_patches.values()), on_conflict="line_user_id")
    except Exception as e:
        # ตอบ 200 เสมอ ไม่งั้น LINE จะ retry
        print("webhook store error:", e)

    # ---- auto-reply ----
    try:
        await _handle_auto_replies(events)
    except Exception as e:
        print("auto-reply error:", e)
    return {"ok": True}


def _match(rule: dict, text: str) -> bool:
    t = (text or "").lower().strip()
    kws = [k.lower().strip() for k in (rule.get("keywords") or []) if k.strip()]
    mt = rule.get("match_type", "contains")
    if mt == "any":
        return True
    if not kws:
        return False
    if mt == "exact":
        return t in kws
    if mt == "prefix":
        return any(t.startswith(k) for k in kws)
    return any(k in t for k in kws)  # contains


async def _handle_auto_replies(events: list):
    text_events = [e for e in events
                   if e.get("type") == "message" and e.get("message", {}).get("type") == "text"
                   and e.get("replyToken")]
    if not text_events:
        return
    rules = await supa.select("auto_replies", params={
        "select": "*", "enabled": "eq.true", "order": "priority.desc,id.asc", "limit": "200",
    })
    if not rules:
        return
    for e in text_events:
        text = e["message"]["text"]
        rule = next((r for r in rules if _match(r, text)), None)
        if not rule:
            continue
        code, _ = await line.reply(e["replyToken"], rule["messages"][:5])
        if code == 200:
            await supa.update("auto_replies",
                              {"hits": (rule.get("hits") or 0) + 1, "last_hit_at": NOW()},
                              {"id": f"eq.{rule['id']}"})


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
@app.get("/api/users")
async def users(admin=Depends(current_admin), limit: int = 100, offset: int = 0,
                q: str = "", following: str = "", menu: str = ""):
    params = {
        "select": "line_user_id,display_name,picture_url,is_following,current_rich_menu_id,"
                  "rich_menu_name,rich_menu_status,source,tags,note,updated_at",
        "order": "updated_at.desc",
        "limit": str(min(limit, 1000)), "offset": str(offset),
    }
    if q:
        params["or"] = f"(line_user_id.ilike.*{q}*,display_name.ilike.*{q}*,note.ilike.*{q}*)"
    if following in ("true", "false"):
        params["is_following"] = f"eq.{following}"
    if menu:
        params["current_rich_menu_id"] = f"eq.{menu}"
    rows = await supa.select("line_users", params=params, headers={"Prefer": "count=exact"})
    total = await supa.count("line_users", {k: v for k, v in params.items()
                                            if k in ("is_following", "current_rich_menu_id", "or")})
    return {"users": rows, "total": total, "limit": limit, "offset": offset}


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


@app.get("/api/users/{uid}")
async def user_detail(uid: str, admin=Depends(current_admin)):
    rows = await supa.select("line_users", params={"line_user_id": f"eq.{uid}", "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบผู้ใช้")
    user = rows[0]
    events = await supa.select("webhook_events", params={
        "line_user_id": f"eq.{uid}", "select": "event_type,message_type,text,created_at",
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
    return {"user": user, "events": events, "live": live}


@app.patch("/api/users/{uid}")
async def update_user(uid: str, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    patch = {k: b[k] for k in ("note", "tags") if k in b}
    patch["updated_at"] = NOW()
    await supa.update("line_users", patch, {"line_user_id": f"eq.{uid}"})
    return {"ok": True}


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
    msgs = _normalize_messages(b.get("messages", []))
    if isinstance(to, list):
        code, txt, rid = await line.multicast(to, msgs)
        kind, cnt = "multicast", len(to)
    else:
        code, txt, rid = await line.push(to, msgs)
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


@app.get("/api/stats/history")
async def stats_history(admin=Depends(current_admin), days: int = 30):
    return {"days": await supa.select("stats_daily", params={
        "select": "*", "order": "day.desc", "limit": str(days),
    })}


# ============================================================
# EVENTS / LOGS
# ============================================================
@app.get("/api/events")
async def events(admin=Depends(current_admin), limit: int = 100, type: str = "", uid: str = ""):
    params = {"select": "*", "order": "created_at.desc", "limit": str(min(limit, 500))}
    if type:
        params["event_type"] = f"eq.{type}"
    if uid:
        params["line_user_id"] = f"eq.{uid}"
    return {"events": await supa.select("webhook_events", params=params)}


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
    if CRON_SECRET:
        key = request.query_params.get("key") or request.headers.get("x-cron-key", "")
        if key != CRON_SECRET:
            raise HTTPException(403, "bad cron key")


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


@app.api_route("/api/cron/run-scheduled", methods=["GET", "POST"])
async def cron_run_scheduled(request: Request):
    _check_cron_key(request)
    due = await supa.select("scheduled_jobs", params={
        "select": "*", "status": "eq.pending", "run_at": f"lte.{NOW()}",
        "order": "run_at.asc", "limit": "10",
    })
    ran = []
    for job in due:
        p = job["payload"]
        try:
            if job["kind"] == "broadcast":
                code, txt, rid = await line.broadcast(_normalize_messages(p.get("messages", [])))
                ok = code == 200
                await supa.insert("broadcasts", {
                    "actor": job.get("created_by"), "kind": "broadcast",
                    "messages": p.get("messages"), "line_request_id": rid,
                    "status": "sent" if ok else "failed",
                })
                res = {"code": code, "requestId": rid}
            else:
                ok, res = False, {"error": "unknown kind"}
            await supa.update("scheduled_jobs",
                              {"status": "done" if ok else "failed", "result": res},
                              {"id": f"eq.{job['id']}"})
            ran.append({"id": job["id"], "ok": ok})
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
    r = await supa.insert("scheduled_jobs", {
        "kind": b.get("kind", "broadcast"),
        "run_at": b["runAt"],
        "payload": {"messages": _normalize_messages(b.get("messages", []))},
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

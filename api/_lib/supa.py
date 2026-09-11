"""Supabase REST (PostgREST) client ผ่าน service_role key — bypass RLS"""
import httpx

from .config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _base() -> str:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("ยังไม่ได้ตั้ง SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    return f"{SUPABASE_URL}/rest/v1"


async def select(table: str, *, params: dict | None = None, headers: dict | None = None) -> list:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{_base()}/{table}", headers=_headers(headers), params=params or {})
        r.raise_for_status()
        return r.json()


async def select_all(table: str, *, params: dict | None = None, page: int = 1000, cap: int = 500000) -> list:
    """อ่านทั้งตาราง (ข้ามลิมิต 1000 แถวของ PostgREST) ด้วยการ page ต่อเนื่อง"""
    base = dict(params or {})
    base.pop("limit", None)
    base.pop("offset", None)
    out: list = []
    offset = 0
    async with httpx.AsyncClient(timeout=30) as c:
        while offset < cap:
            q = {**base, "limit": str(page), "offset": str(offset)}
            r = await c.get(f"{_base()}/{table}", headers=_headers(), params=q)
            r.raise_for_status()
            batch = r.json()
            out.extend(batch)
            if len(batch) < page:
                break
            offset += page
    return out


async def count(table: str, params: dict | None = None) -> int:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{_base()}/{table}",
            headers=_headers({"Prefer": "count=exact", "Range": "0-0"}),
            params=params or {},
        )
        r.raise_for_status()
        cr = r.headers.get("content-range", "*/0")
        return int(cr.split("/")[-1]) if "/" in cr else 0


async def upsert(table: str, rows: list | dict, *, on_conflict: str | None = None) -> list:
    params = {}
    if on_conflict:
        params["on_conflict"] = on_conflict
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{_base()}/{table}",
            headers=_headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
            params=params,
            json=rows if isinstance(rows, list) else [rows],
        )
        r.raise_for_status()
        return r.json()


async def insert(table: str, rows: list | dict) -> list:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{_base()}/{table}",
            headers=_headers({"Prefer": "return=representation"}),
            json=rows if isinstance(rows, list) else [rows],
        )
        r.raise_for_status()
        return r.json() if r.content else []


async def update(table: str, patch: dict, params: dict) -> list:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.patch(
            f"{_base()}/{table}",
            headers=_headers({"Prefer": "return=representation"}),
            params=params,
            json=patch,
        )
        r.raise_for_status()
        return r.json() if r.content else []


async def delete(table: str, params: dict) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.delete(f"{_base()}/{table}", headers=_headers(), params=params)
        r.raise_for_status()


async def storage_upload(bucket: str, path: str, content: bytes, content_type: str) -> str:
    """อัปโหลดไฟล์ขึ้น Supabase Storage คืน public URL"""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("ยังไม่ได้ตั้ง SUPABASE_URL / SERVICE_ROLE_KEY")
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            content=content,
        )
        r.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"


async def storage_list(bucket: str, prefix: str = "") -> list:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/list/{bucket}",
            headers=_headers(),
            json={"prefix": prefix, "limit": 100, "sortBy": {"column": "created_at", "order": "desc"}},
        )
        r.raise_for_status()
        return r.json()


async def storage_delete(bucket: str, path: str):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request("DELETE", f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}",
                            headers=_headers())
        r.raise_for_status()


async def storage_ensure_bucket(name: str, *, public: bool = False,
                                allowed_mime_types: list | None = None) -> None:
    """สร้าง bucket ถ้ายังไม่มี (idempotent) — service_role เท่านั้น"""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{SUPABASE_URL}/storage/v1/bucket/{name}", headers=_headers())
        if r.status_code == 200:
            return
        body = {"name": name, "id": name, "public": public}
        if allowed_mime_types:
            body["allowed_mime_types"] = allowed_mime_types
        r = await c.post(f"{SUPABASE_URL}/storage/v1/bucket", headers=_headers(), json=body)
        if r.status_code not in (200, 201) and "already exists" not in r.text.lower():
            r.raise_for_status()


async def storage_sign_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    """สร้าง signed URL สำหรับไฟล์ใน private bucket"""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SUPABASE_URL}/storage/v1/object/sign/{bucket}/{path}",
            headers=_headers(), json={"expiresIn": expires_in},
        )
        r.raise_for_status()
        signed = r.json().get("signedURL") or r.json().get("signedUrl") or ""
    return f"{SUPABASE_URL}/storage/v1{signed}" if signed.startswith("/") else signed


async def log_operation(actor: str | None, action: str, params=None, result=None, status="ok"):
    try:
        await insert("operations", {
            "actor": actor, "action": action,
            "params": params, "result": result, "status": status,
        })
    except Exception:
        pass

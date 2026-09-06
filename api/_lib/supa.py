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


async def log_operation(actor: str | None, action: str, params=None, result=None, status="ok"):
    try:
        await insert("operations", {
            "actor": actor, "action": action,
            "params": params, "result": result, "status": status,
        })
    except Exception:
        pass

"""ซิงค์ชื่อ LINE: ดึงไม่สำเร็จต้องไม่เปลี่ยนสถานะผู้ใช้"""
import asyncio
import pytest
from _lib import core, line


class Resp:
    def __init__(self, code, body=None):
        self.status_code, self._body = code, body
    def json(self):
        return self._body


@pytest.mark.parametrize("code,expected", [(200, "ok"), (404, "gone"), (429, "unknown"), (500, "unknown"), (401, "unknown")])
def test_fetch_profile_states(monkeypatch, code, expected):
    async def req(*a, **k):
        return Resp(code, {"displayName": "x"})
    monkeypatch.setattr(line, "_req", req)
    assert asyncio.run(line.fetch_profile("U"))[0] == expected


def test_fetch_profile_timeout_is_unknown(monkeypatch):
    async def req(*a, **k):
        raise TimeoutError()
    monkeypatch.setattr(line, "_req", req)
    assert asyncio.run(line.fetch_profile("U")) == ("unknown", None)


@pytest.fixture
def db(monkeypatch):
    calls = []
    async def upsert(t, rows, on_conflict=None):
        assert len({tuple(sorted(r)) for r in rows}) == 1, "แถวในคำขอเดียวต้องมีคีย์เหมือนกัน"
        calls.append(rows)
    async def fetch(uid):
        return {"A": ("ok", {"displayName": "ชื่อใหม่"}), "B": ("gone", None), "C": ("unknown", None)}[uid]
    monkeypatch.setattr(core.supa, "upsert", upsert)
    monkeypatch.setattr(core.line, "fetch_profile", fetch)
    return calls


def test_unknown_users_are_untouched(db):
    r = asyncio.run(core._refresh_profiles(["A", "B", "C"]))
    assert r == {"processed": 3, "profiles_fetched": 1, "not_following": 1, "errors": 1}
    rows = {x["line_user_id"]: x for g in db for x in g}
    assert "C" not in rows
    assert rows["A"]["display_name"] == "ชื่อใหม่" and rows["A"]["is_following"] is True
    assert rows["B"]["is_following"] is False and "display_name" not in rows["B"]   # ไม่ลบชื่อเดิม


def test_cron_does_not_bump_updated_at(db):
    asyncio.run(core._refresh_profiles(["A"], touch=False))
    assert "updated_at" not in db[0][0] and db[0][0]["profile_synced_at"]


def test_works_before_migration(monkeypatch):
    saved = []
    async def upsert(t, rows, on_conflict=None):
        if "profile_synced_at" in rows[0]:
            raise RuntimeError("column 'profile_synced_at' does not exist")
        saved.extend(rows)
    monkeypatch.setattr(core.supa, "upsert", upsert)
    assert asyncio.run(core._upsert_profile_rows([{"line_user_id": "A", "profile_synced_at": "x"}])) is False
    assert saved == [{"line_user_id": "A"}]


def test_auto_sync_skips_without_column_or_when_disabled(monkeypatch):
    async def on(key, default=None):
        return default
    async def off(key, default=None):
        return False
    async def sel(*a, **k):
        raise RuntimeError("column does not exist")
    monkeypatch.setattr(core.supa, "select", sel)
    monkeypatch.setattr(core, "_get_setting", on)
    assert "0025" in asyncio.run(core._sync_stale_profiles())["skipped"]
    monkeypatch.setattr(core, "_get_setting", off)
    assert "ปิดไว้" in asyncio.run(core._sync_stale_profiles())["skipped"]

"""สลับ rich menu หลังส่งสลิป: ลองซ้ำ/แจ้งเมื่อล้มเหลว + ซ่อมย้อนหลังไม่ดึงคนที่เคยได้เมนูแล้ว"""
import asyncio
import pytest
from _lib import core, line

RID = "richmenu-test"


@pytest.fixture
def env(monkeypatch):
    st = {"links": [], "alerts": [], "ops": [], "upserts": [], "hist": []}
    monkeypatch.setattr(core, "SLIP_SUCCESS_RICHMENU_ID", RID)

    async def fetch(uids):
        return {}
    async def upsert(t, rows, on_conflict=None):
        st["upserts"].append((t, rows))
    async def insert(t, rows):
        st["hist"].append((t, rows))
    async def log_op(*a, **k):
        st["ops"].append(a)
    async def alert(subject, detail="", throttle_key=None):
        st["alerts"].append((subject, detail))
    async def nosleep(_):
        pass
    monkeypatch.setattr(core, "_fetch_current_menu_map", fetch)
    monkeypatch.setattr(core.supa, "upsert", upsert)
    monkeypatch.setattr(core.supa, "insert", insert)
    monkeypatch.setattr(core.supa, "log_operation", log_op)
    monkeypatch.setattr(core, "alert_admin", alert)
    monkeypatch.setattr(core.asyncio, "sleep", nosleep)
    return st


def _link(monkeypatch, st, codes):
    seq = list(codes)
    async def link(uid, rid):
        c = seq.pop(0)
        st["links"].append((uid, rid, c))
        return c == 200, c
    monkeypatch.setattr(core.line, "user_richmenu_link", link)


def test_success_writes_db_and_history(env, monkeypatch):
    _link(monkeypatch, env, [200])
    r = asyncio.run(core._link_slip_menu("U1"))
    assert r["ok"] and len(env["links"]) == 1
    assert env["upserts"][0][1][0]["current_rich_menu_id"] == RID
    assert env["hist"] and env["hist"][0][1][0]["source"] == "slip"
    assert not env["alerts"]


def test_retry_on_5xx_then_ok(env, monkeypatch):
    _link(monkeypatch, env, [500, 200])
    assert asyncio.run(core._link_slip_menu("U1"))["ok"]
    assert len(env["links"]) == 2


def test_4xx_no_retry_and_alert(env, monkeypatch):
    _link(monkeypatch, env, [404])
    r = asyncio.run(core._link_slip_menu("U1"))
    assert not r["ok"] and len(env["links"]) == 1
    assert env["alerts"] and "SLIP_SUCCESS_RICHMENU_ID" in env["alerts"][0][1]
    assert env["ops"] and env["ops"][0][1] == "richmenu.slip_link_failed"
    assert not env["upserts"]


def test_disabled_when_no_id(env, monkeypatch):
    monkeypatch.setattr(core, "SLIP_SUCCESS_RICHMENU_ID", "")
    assert asyncio.run(core._link_slip_menu("U1")) == {"ok": False, "reason": "disabled"}


def test_repair_skips_users_who_already_had_menu(env, monkeypatch):
    tables = {
        "slips": [{"line_user_id": u, "status": "verified"} for u in ("A", "B", "C")],
        "line_users": [{"line_user_id": "A", "current_rich_menu_id": "x"},
                       {"line_user_id": "B", "current_rich_menu_id": "zoom"},
                       {"line_user_id": "C", "current_rich_menu_id": None}],
        "richmenu_history": [{"line_user_id": "B"}],   # B เคยได้เมนูแล้วถูกย้ายไป zoom -> ห้ามดึงกลับ
    }
    async def sel_all(t, params=None, **k):
        return tables[t]
    async def live(uid):
        return None
    monkeypatch.setattr(core.supa, "select_all", sel_all)
    monkeypatch.setattr(core.line, "user_richmenu_get", live)
    _link(monkeypatch, env, [200, 200])
    r = asyncio.run(core._slip_menu_repair(False))
    assert r["never_received_candidates"] == 2 and r["would_link"] == 2 and not env["links"]
    r = asyncio.run(core._slip_menu_repair(True))
    assert r["linked"] == 2 and {l[0] for l in env["links"]} == {"A", "C"}


def test_diagnose_counts(env, monkeypatch):
    tables = {
        "slips": [{"line_user_id": "A", "status": "verified", "created_at": "2099-01-01"},
                  {"line_user_id": "B", "status": "review", "created_at": "2000-01-01"}],
        "line_users": [{"line_user_id": "A", "current_rich_menu_id": RID, "is_following": True},
                       {"line_user_id": "B", "current_rich_menu_id": None, "is_following": True}],
        "richmenu_history": [{"line_user_id": "A", "source": "slip"}],
        "webhook_jobs": [{"status": "failed", "error": "boom", "created_at": "2026-01-01"}],
        "registrations": [{"line_user_id": "B", "paid": False}, {"line_user_id": "Z", "paid": False}],
    }
    async def sel_all(t, params=None, **k):
        return tables[t]
    async def sel(t, params=None, **k):
        return []
    async def rget(rid):
        return None   # เมนูไม่อยู่ใน LINE
    async def dflt():
        return "d"
    monkeypatch.setattr(core.supa, "select_all", sel_all)
    monkeypatch.setattr(core.supa, "select", sel)
    monkeypatch.setattr(core.line, "richmenu_get", rget)
    monkeypatch.setattr(core.line, "richmenu_get_default", dflt)
    r = asyncio.run(core._slip_menu_diagnose())
    assert r["menu_exists_in_line"] is False
    assert r["slip_users"] == 2 and r["slip_users_on_menu_now"] == 1
    assert r["slip_users_never_received_menu"] == 1 and r["slip_users_never_received_but_following"] == 1
    assert r["jobs_by_status"] == {"failed": 1}
    assert r["unpaid_with_slip"] == 1 and r["unpaid_without_slip"] == 1

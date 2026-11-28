"""เมนูสมาชิก/VIP (PRETEST_70): ห้ามย้ายกลับ ห้ามทวงเงิน"""
import asyncio
import pytest
from _lib import core, smart_answers as sa

VIP_MENU, WAIT = "richmenu-vip", "richmenu-wait"


@pytest.fixture
def env(monkeypatch):
    st = {"links": [], "live": {"V": VIP_MENU, "N": None}, "list_fail": False, "live_fail": set()}
    tables = {"registrations": [{"course": "FC70", "course_raw": "FC70", "paid": False, "class_id": None}],
              "payment_accounts": [{"course": "FC", "price": 1499, "account_no": "080-0-1", "bank": "x"}],
              "slips": [], "line_users": [{"current_rich_menu_id": VIP_MENU}], "richmenu_history": []}
    async def menus():
        if st["list_fail"]:
            raise RuntimeError("down")
        return [{"richMenuId": VIP_MENU, "name": "PRETEST_70"}, {"richMenuId": WAIT, "name": "แล้วพบกัน"}]
    async def live(uid):
        if uid in st["live_fail"]:
            raise RuntimeError("429")
        return st["live"].get(uid)
    async def link(uid, rid):
        st["links"].append(uid)
        return True, 200
    async def sel(t, params=None, **k):
        return tables.get(t, [])
    async def gs(key, default=None):
        return default
    async def noop(*a, **k):
        return []
    monkeypatch.setattr(core, "SLIP_SUCCESS_RICHMENU_ID", WAIT)
    monkeypatch.setattr(core.line, "richmenu_list", menus)
    monkeypatch.setattr(core.line, "user_richmenu_get", live)
    monkeypatch.setattr(core.line, "user_richmenu_link", link)
    monkeypatch.setattr(core.supa, "select", sel)
    for name in ("upsert", "insert", "log_operation"):
        monkeypatch.setattr(core.supa, name, noop)
    monkeypatch.setattr(core, "_get_setting", gs)
    monkeypatch.setattr(sa, "_get_setting", gs)
    core._member_menu_cache.update(exp=0.0, ids=set(), names=None)
    core._course_qr_cache.update(exp=0.0, courses=[])
    st["tables"] = tables
    return st


def test_slip_never_downgrades_member(env):
    assert asyncio.run(core._link_slip_menu("V"))["reason"] == "member_menu" and not env["links"]
    assert asyncio.run(core._link_slip_menu("N"))["ok"] and env["links"] == ["N"]


def test_falls_back_to_saved_menu_when_line_cannot_answer(env):
    env["live_fail"].add("V")
    assert asyncio.run(core._is_member_menu_user("V")) is True


def test_repair_skips_members_and_unknowns(env, monkeypatch):
    env["tables"].update(slips=[{"line_user_id": u, "status": "verified"} for u in ("V", "S", "N", "Q")])
    env["live"].update(S=VIP_MENU)          # DB เก่าบอกว่าไม่มีเมนู แต่ LINE บอกว่าเป็นสมาชิก
    env["live_fail"].add("Q")
    async def sel_all(t, params=None, **k):
        if t == "line_users":
            return [{"line_user_id": "V", "current_rich_menu_id": VIP_MENU}] + [
                {"line_user_id": u, "current_rich_menu_id": None} for u in ("S", "N", "Q")]
        return env["tables"].get(t, [])
    monkeypatch.setattr(core.supa, "select_all", sel_all)
    r = asyncio.run(core._slip_menu_repair(True))
    assert env["links"] == ["N"]
    assert r["never_received_candidates"] == 3 and r["member_skipped"] == 1 and r["unknown_skipped"] == 1


def test_repair_refuses_when_menu_list_unavailable(env, monkeypatch):
    env["list_fail"] = True
    async def sel_all(*a, **k):
        return []
    monkeypatch.setattr(core.supa, "select_all", sel_all)
    assert "skipped" in asyncio.run(core._slip_menu_repair(True)) and not env["links"]


@pytest.mark.parametrize("q", ["โอนแล้วค่ะ", "ค่าติวเท่าไหร่คะ", "เข้าเรียนที่ไหนคะ"])
def test_member_is_not_asked_to_pay(env, q):
    t = asyncio.run(sa.compose("V", q))["message"]["text"]
    assert "สิทธิ์" in t and "080-0-1" not in t and "รอโอนเงิน" not in t and "ยังไม่พบสลิป" not in t
    other = asyncio.run(sa.compose("N", q))["message"]["text"]
    assert "080-0-1" in other

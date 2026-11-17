"""ทดสอบตรรกะทะเบียนผู้ลงทะเบียน — รัน: py -3 -m pytest tests -q"""
import asyncio

import pytest

from _lib import registrations as R
from _lib import supa


# ---------------------------------------------------------------- หลักสูตร
@pytest.mark.parametrize("raw,expected", [
    ("FC", "FC70"), ("fc 70", "FC70"), ("IC70", "IC70"), ("PC", "PC70"),
    ("PC รุ่น 1", "PC70-1"), ("PC70 รุ่นที่ 2", "PC70-2"), ("PC รุ่น2", "PC70-2"), ("PC รุ่น๒", "PC70-2"),
    ("AC", "AC70"),
    ("VIP", "VIP"),                      # ไม่ใช่ FC/IC/PC/AC: คงข้อความเดิม
    ("", None), ("   ", None), (None, None),
])
def test_norm_course(raw, expected):
    assert R._norm_course(raw) == expected


def test_norm_course_truncates_unknown_to_24():
    assert len(R._norm_course("X" * 100)) == 24


@pytest.mark.parametrize("course,base", [("FC70", "FC"), ("PC70-2", "PC"), ("VIP", "VIP"), ("", "?"), (None, "?")])
def test_course_base(course, base):
    assert R._course_base(course) == base


# ---------------------------------------------------------------- ประวัติการแก้ไข
def test_diff_fields_only_changed():
    old = {"name": "สมชาย", "tel": "081", "org": None, "paid": False}
    assert R.diff_fields(old, {"name": "สมชาย", "tel": "082", "org": "", "paid": True, "note": "x"}) == {
        "tel": {"from": "081", "to": "082"},
        "paid": {"from": False, "to": True},
        "note": {"from": None, "to": "x"},
    }


def test_diff_fields_none_equals_empty_and_ignores_unknown_keys():
    assert R.diff_fields({"org": None}, {"org": "", "updated_at": "now", "evil": 1}) == {}


# ---------------------------------------------------------------- เรียงลำดับ
def test_order_param_whitelist_and_tiebreak():
    assert R.order_param("name", "asc") == "name.asc.nullslast,id.asc"
    assert R.order_param("paid", "desc") == "paid.desc.nullslast,id.desc"
    assert R.order_param("", "") == "created_at.desc,id.desc"


def test_order_param_rejects_injection():
    assert R.order_param("name;drop table registrations", "asc") == "created_at.desc,id.desc"
    assert R.order_param("line_user_id", "asc") == "created_at.desc,id.desc"   # ไม่อยู่ใน whitelist


# ---------------------------------------------------------------- เบอร์/อีเมล
@pytest.mark.parametrize("tel,expected", [
    ("081-234-5678", "0812345678"), ("+66 81 234 5678", "0812345678"), ("66812345678", "0812345678"),
    ("0812345678", "0812345678"), ("12345", None), ("", None), (None, None), ("-", None),
])
def test_norm_tel(tel, expected):
    assert R.norm_tel(tel) == expected


def test_norm_email():
    assert R.norm_email("  A@B.com ") == "a@b.com"
    assert R.norm_email("not-an-email") is None
    assert R.norm_email(None) is None


# ---------------------------------------------------------------- ข้อมูลซ้ำ
def reg(id_, uid, name="x", tel=None, email=None, course="FC70", paid=False):
    return {"id": id_, "line_user_id": uid, "name": name, "tel": tel, "email": email, "course": course, "paid": paid}


def test_duplicates_same_tel_different_accounts():
    g = R.find_duplicate_groups([
        reg(1, "Ua", tel="081-111-1111", course="FC70"),
        reg(2, "Ub", tel="0811111111", course="IC70"),
        reg(3, "Uc", tel="0899999999"),
    ])
    assert len(g) == 1
    assert [m["line_user_id"] for m in g[0]["members"]] == ["Ua", "Ub"]
    assert g[0]["reasons"] == ["tel"] and g[0]["conflict"] is False


def test_duplicates_same_account_multiple_courses_is_not_duplicate():
    assert R.find_duplicate_groups([reg(1, "Ua", tel="0811111111", course="FC70"), reg(2, "Ua", tel="0811111111", course="IC70")]) == []


def test_duplicates_chain_through_tel_and_email():
    g = R.find_duplicate_groups([
        reg(1, "Ua", tel="0811111111"),
        reg(2, "Ub", tel="0811111111", email="p@x.com", course="IC70"),
        reg(3, "Uc", email="P@X.com", course="PC70"),
    ])
    assert len(g) == 1 and len(g[0]["members"]) == 3
    assert g[0]["reasons"] == ["email", "tel"]


def test_duplicates_conflict_when_same_course_in_both_accounts():
    g = R.find_duplicate_groups([reg(1, "Ua", tel="0811111111", course="FC70"), reg(2, "Ub", tel="0811111111", course="FC70")])
    assert g[0]["conflict"] is True


def test_duplicates_ignore_short_or_missing_keys():
    assert R.find_duplicate_groups([reg(1, "Ua", tel="123"), reg(2, "Ub", tel="123"), reg(3, "Uc"), reg(4, "Ud")]) == []


# ---------------------------------------------------------------- กระทบยอด (เกี่ยวกับเงิน)
class FakeSupa:
    def __init__(self, regs, slips, accts, users=()):
        self.regs, self.slips, self.accts, self.users = regs, slips, accts, list(users)

    async def select_all(self, table, params=None, **kw):
        return {"registrations": self.regs, "slips": self.slips}[table]

    async def select(self, table, params=None, **kw):
        return {"payment_accounts": self.accts, "line_users": self.users}[table]


def run_reconcile(monkeypatch, regs, slips, accts=({"course": "FC", "price": 1499}, {"course": "IC", "price": 1999})):
    fake = FakeSupa(regs, slips, list(accts))
    monkeypatch.setattr(supa, "select_all", fake.select_all)
    monkeypatch.setattr(supa, "select", fake.select)
    return asyncio.run(R._reconcile_data())


def slip(id_, uid, course, amount):
    return {"id": id_, "line_user_id": uid, "expected_course": course, "amount": amount, "created_at": "2026-11-01"}


def test_reconcile_paid_and_slip_matching(monkeypatch):
    out = run_reconcile(monkeypatch,
        regs=[reg(1, "Ua", course="FC70", paid=True), reg(2, "Ub", course="FC70"), reg(3, "Uc", course="IC70")],
        slips=[slip(10, "Ua", "FC70", 1499), slip(11, "Ub", "FC70", 1499)])
    t = out["totals"]
    assert t["registered"] == 3 and t["paid_marked"] == 1 and t["slip_verified"] == 2
    assert t["revenue"] == 2998 and t["expected_revenue"] == 1499 * 2 + 1999
    # Ub: มีสลิปยืนยันแต่ทะเบียนยังไม่ mark จ่าย · Uc: ไม่มีสลิป ยังไม่จ่าย
    assert [x["line_user_id"] for x in out["issues"]["paid_not_marked"]] == ["Ub"]
    assert [x["line_user_id"] for x in out["issues"]["unpaid"]] == ["Uc"]
    assert out["issues"]["slip_no_reg_count"] == 0


def test_reconcile_slip_without_registration(monkeypatch):
    out = run_reconcile(monkeypatch, regs=[reg(1, "Ua", course="FC70", paid=True)],
                        slips=[slip(10, "Ua", "FC70", 1499), slip(11, "Ux", "IC70", 1999), slip(12, "Uy", None, 500)])
    reasons = {x["line_user_id"]: x["reason"] for x in out["issues"]["slip_no_reg"]}
    assert reasons == {"Ux": "ไม่มีทะเบียนคอร์สนี้", "Uy": "สลิปไม่ระบุคอร์ส"}


def test_reconcile_one_slip_counts_once(monkeypatch):
    # คนเดียวลงคอร์สเดียวกันสองแถว (ข้อมูลซ้ำ) มีสลิปใบเดียว — สลิปต้องไม่ถูกนับซ้ำ
    out = run_reconcile(monkeypatch, regs=[reg(1, "Ua", course="FC70-1"), reg(2, "Ua", course="FC70-2")],
                        slips=[slip(10, "Ua", "FC70", 1499)])
    assert out["by_course"][0]["slip_verified"] + out["by_course"][1]["slip_verified"] == 1


def test_reconcile_unknown_price_is_zero(monkeypatch):
    out = run_reconcile(monkeypatch, regs=[reg(1, "Ua", course="VIP")], slips=[], accts=[])
    assert out["totals"]["expected_revenue"] == 0

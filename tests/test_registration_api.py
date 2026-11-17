"""ทดสอบ endpoint ทะเบียน (PATCH / history / duplicates / sort) ด้วย Supabase จำลองในหน่วยความจำ"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from _lib import supa
from _lib.auth import current_admin
from _lib.routers import billing


class FakeDB:
    def __init__(self):
        self.regs = {1: {"id": 1, "line_user_id": "Ua", "name": "สมชาย", "tel": "0811111111", "email": None, "org": "กอง ก",
                         "job": None, "course": "FC70", "course_raw": "FC", "paid": False, "approved": None, "note": None},
                     2: {"id": 2, "line_user_id": "Ua", "name": "สมชาย", "tel": "0811111111", "email": None, "org": "กอง ก",
                         "job": None, "course": "IC70", "course_raw": "IC", "paid": False, "approved": None, "note": None},
                     3: {"id": 3, "line_user_id": "Ub", "name": "สมหญิง", "tel": "0822222222", "email": None, "org": None,
                         "job": None, "course": "FC70", "course_raw": "FC", "paid": False, "approved": None, "note": None}}
        self.ops, self.queries, self.other_updates = [], [], []

    @staticmethod
    def _eq(v):
        return v.split(".", 1)[1] if isinstance(v, str) and "." in v else v

    async def select(self, table, params=None, **kw):
        params = params or {}
        self.queries.append((table, dict(params)))
        if table == "registrations":
            rows = list(self.regs.values())
            for k in ("id", "line_user_id", "course"):
                if k in params and params[k].startswith("eq."):
                    rows = [r for r in rows if str(r[k]) == self._eq(params[k])]
                if k in params and params[k].startswith("neq."):
                    rows = [r for r in rows if str(r[k]) != self._eq(params[k])]
            return rows
        if table == "operations":
            want = self._eq(params.get("params->>id", "eq."))
            return [o for o in self.ops if str(o["params"].get("id")) == want]
        return []  # line_users / ฯลฯ

    async def select_all(self, table, params=None, **kw):
        return await self.select(table, params)

    async def count(self, table, params=None):
        return len(self.regs)

    async def update(self, table, patch, filt):
        if table != "registrations":       # line_users (tag จ่ายแล้ว) ฯลฯ — เก็บไว้ตรวจ ไม่ต้องจำลองข้อมูล
            self.other_updates.append((table, patch, filt))
            return []
        rid = int(self._eq(filt["id"]))
        self.regs[rid].update(patch)
        return [self.regs[rid]]

    async def log_operation(self, actor, action, params=None, result=None, status="ok"):
        self.ops.append({"id": len(self.ops) + 1, "actor": actor, "action": action, "params": params, "result": result,
                         "created_at": "2026-11-17T00:00:00Z"})


@pytest.fixture
def env(monkeypatch):
    db = FakeDB()
    for name in ("select", "select_all", "count", "update", "log_operation"):
        monkeypatch.setattr(supa, name, getattr(db, name))

    async def fake_retag():
        db.retagged = True
        return {}
    db.retagged = False
    monkeypatch.setattr(billing, "_retag_from_registrations", fake_retag)
    app = FastAPI()
    app.include_router(billing.router)
    app.dependency_overrides[current_admin] = lambda: {"userId": "Uadmin", "name": "แอดมิน", "is_admin": True}
    return TestClient(app), db


def test_patch_logs_only_real_changes(env):
    c, db = env
    r = c.patch("/api/registrations/1", json={"name": "สมชาย", "tel": " 0899999999 ", "org": ""})
    assert r.status_code == 200
    assert db.regs[1]["tel"] == "0899999999" and db.regs[1]["org"] is None
    assert len(db.ops) == 1 and db.ops[0]["action"] == "registration.update"
    assert db.ops[0]["actor"] == "แอดมิน"
    assert db.ops[0]["result"]["changes"] == {"tel": {"from": "0811111111", "to": "0899999999"},
                                              "org": {"from": "กอง ก", "to": None}}


def test_patch_without_change_writes_no_log(env):
    c, db = env
    assert c.patch("/api/registrations/1", json={"name": "สมชาย"}).status_code == 200
    assert db.ops == []


def test_patch_paid_is_audited(env):
    c, db = env
    c.patch("/api/registrations/3", json={"paid": True})
    assert db.ops[0]["result"]["changes"] == {"paid": {"from": False, "to": True}}
    assert db.other_updates and db.other_updates[0][0] == "line_users"     # ติด tag จ่ายแล้วด้วย


def test_patch_rejects_bad_email_and_logs_nothing(env):
    c, db = env
    r = c.patch("/api/registrations/1", json={"email": "ไม่ใช่อีเมล"})
    assert r.status_code == 400 and db.ops == [] and db.regs[1]["email"] is None


def test_patch_course_normalizes_and_retags(env):
    c, db = env
    assert c.patch("/api/registrations/3", json={"course": "PC รุ่น 2"}).status_code == 200
    assert (db.regs[3]["course"], db.regs[3]["course_raw"]) == ("PC70-2", "PC รุ่น 2")
    assert db.retagged is True
    ch = db.ops[0]["result"]["changes"]
    assert ch["course"] == {"from": "FC70", "to": "PC70-2"}


def test_patch_course_conflict_409(env):
    c, db = env
    r = c.patch("/api/registrations/2", json={"course": "FC"})   # Ua มี FC70 อยู่แล้ว (แถว 1)
    assert r.status_code == 409 and db.regs[2]["course"] == "IC70" and db.ops == []


def test_patch_empty_course_400_and_unknown_id_404(env):
    c, _ = env
    assert c.patch("/api/registrations/1", json={"course": "  "}).status_code == 400
    assert c.patch("/api/registrations/999", json={"name": "x"}).status_code == 404


def test_patch_ignores_fields_outside_whitelist(env):
    c, db = env
    c.patch("/api/registrations/1", json={"line_user_id": "Uhack", "id": 77, "name": "ใหม่"})
    assert db.regs[1]["line_user_id"] == "Ua" and db.regs[1]["id"] == 1


def test_history_returns_logged_changes(env):
    c, db = env
    c.patch("/api/registrations/1", json={"note": "โทรแล้ว"})
    c.patch("/api/registrations/3", json={"note": "คนอื่น"})
    h = c.get("/api/registrations/1/history").json()["history"]
    assert len(h) == 1 and h[0]["result"]["changes"]["note"]["to"] == "โทรแล้ว"


def test_list_passes_whitelisted_sort(env):
    c, db = env
    orders = lambda: [q[1]["order"] for q in db.queries if q[0] == "registrations" and "order" in q[1]]
    c.get("/api/registrations?sort=name&dir=desc")
    assert orders()[-1] == "name.desc.nullslast,id.desc"
    c.get("/api/registrations?sort=line_user_id;--")
    assert orders()[-1] == "created_at.desc,id.desc"


def test_duplicates_endpoint_does_not_flag_multi_course_single_account(env):
    c, db = env
    assert c.get("/api/registrations/duplicates").json() == {"groups": [], "total": 0}
    db.regs[3]["tel"] = "081-111-1111"      # Ub ใช้เบอร์เดียวกับ Ua -> ซ้ำ, และ FC70 ซ้ำข้ามบัญชี = conflict
    g = c.get("/api/registrations/duplicates").json()
    assert g["total"] == 1 and g["groups"][0]["conflict"] is True

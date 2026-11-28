"""ตอบอัตโนมัติอัจฉริยะ: จับเจตนาถูก, ไม่แต่งข้อมูล, ลิงก์เรียนไม่หลุด, กฎเจ้าของมาก่อน"""
import asyncio
import pytest
from _lib import core, smart_answers as sa

UID = "U" + "a" * 32


@pytest.mark.parametrize("text,want", [
    ("เริ่มติววันไหนคะ", ["start"]), ("เริ่มติวเมื่อไหร่คะ", ["start"]), ("เริ่ม อบรมเมื่อไรคะ", ["start"]),
    ("เริ่มเรียนวันไหนค่ะ", ["start"]),
    ("ค่าลงทะเบียนเท่าไหร่คะ", ["price"]), ("ค่าติวเท่าไหร่คะ", ["price"]), ("ค่าลงทะเบียนกี่บาทคะ", ["price"]),
    ("ทำข้อสอบตรงไหนคะ", ["access"]), ("ตอนนี้เปิดระบบข้อสอบให้ทดลองทำไหมคะ", ["access"]),
    ("มีข้อสอบให้ทดลองทำไหมคะ", ["access"]), ("หลักสูตรที่ลงทะเบียนไว้มี pretest ไหมคะ", ["access"]),
    ("ลงทะเบียนแล้ว จ่ายเงินแล้วสามารถเข้าเรียนได้ที่ไหนคะ", ["access"]), ("เข้าตรงไหนครับ", ["access"]),
    ("ลงทะเบียนได้ถึงวันไหนครับ", ["deadline"]), ("โอนได้ถึงวันไหนค่ะ", ["deadline"]), ("ยังสมัครทันไหมคะ", ["deadline"]),
    ("สมัครได้ถึงเมื่อไหร่คะ", ["deadline"]), ("เต็มหรือยังค่ะ", ["deadline"]),
    ("โอนค่าสมัครแล้วค่ะ", ["status"]), ("ส่งสลิปแล้วค่ะ", ["status"]), ("ได้รับเงินหรือยังคะ", ["status"]),
    ("ติดต่อยังไง", ["contact"]), ("ติดต่อแอดมิน", ["contact"]),
    ("ค่าติวเท่าไหร่ สมัครได้ถึงวันไหนคะ", ["deadline", "price"]),
    ("ขอเงินคืนค่ะ โอนแล้ว", ["urgent"]),
    # ต้องไม่รับตอบ
    ("ราคากลางคืออะไร", []), ("ดูคลิปย้อนหลังได้ถึงวันไหนคะ", []), ("เริ่มเรียนแล้วค่ะ", []),
    ("สอบถามค่ะ", []), ("รบกวนสอบถามค่ะ", []), ("หิวข้าว กินอะไรดี", []), ("/ตรวจข้อมูล", []), ("ขอบคุณค่ะ", []),
    ("วิธีเฉพาะเจาะจงตามมาตรา 56 วงเงินเท่าไหร่", []), ("เท่าไหร่ค่ะ", []),
])
def test_detect(text, want):
    assert sa.detect_intents(text) == want


@pytest.fixture
def db(monkeypatch):
    data = {"registrations": [], "slips": [], "classes": [], "app": {},
            "payment_accounts": [{"course": "FC", "price": 1499, "full_price": 1999, "bank": "กรุงเทพ",
                                  "account_no": "080-0-1", "account_name": "ธ"}]}
    async def sel(t, params=None, **k):
        if t == "classes" and "id" in (params or {}):
            return [{"name": "FC รุ่น 5", "zoom_url": "https://zoom/SECRET", "materials_url": None}]
        return data.get(t, [])
    async def gs(key, default=None):
        return data["app"].get(key, default)
    monkeypatch.setattr(core.supa, "select", sel)
    monkeypatch.setattr(core, "_get_setting", gs)
    monkeypatch.setattr(sa, "_get_setting", gs)
    core._course_qr_cache.update(exp=0.0, courses=[])
    return data


def ask(text, uid=UID):
    return asyncio.run(sa.compose(uid, text))


def test_price_is_live_and_personal(db):
    r = ask("ค่าติวเท่าไหร่คะ")
    assert "FC: 1,499" in r["message"]["text"] and not r["escalate"]
    db["registrations"] = [{"course": "FC70", "course_raw": "FC70", "paid": False, "class_id": None}]
    t = ask("ค่าติวเท่าไหร่คะ")["message"]["text"]
    assert "หลักสูตรที่คุณลงทะเบียน: FC70" in t and "080-0-1" in t


def test_missing_data_goes_to_admin_instead_of_guessing(db):
    for q in ("เริ่มติววันไหนคะ", "สมัครได้ถึงวันไหนคะ"):
        r = ask(q)
        assert r["escalate"] and "แอดมิน" in r["message"]["text"]


def test_owner_text_and_future_classes_only(db):
    db["app"]["smart_answers"] = {"deadline": "ปิดรับ 1 ธ.ค."}
    db["classes"] = [{"course": "FC70", "name": "รุ่นเก่า", "start_date": "2000-01-01"},
                     {"course": "FC70", "name": "รุ่นใหม่", "start_date": "2999-01-01", "schedule": "เสาร์"}]
    r = ask("เริ่มติววันไหนคะ")
    assert "รุ่นใหม่" in r["message"]["text"] and "รุ่นเก่า" not in r["message"]["text"] and not r["escalate"]
    r = ask("สมัครได้ถึงวันไหนคะ")
    assert "ปิดรับ 1 ธ.ค." in r["message"]["text"] and not r["escalate"]


@pytest.mark.parametrize("paid,class_id,share,visible", [
    (True, 7, True, True), (True, 7, False, False), (False, 7, True, False), (True, None, True, False)])
def test_class_links_only_for_paid_assigned_and_enabled(db, paid, class_id, share, visible):
    db["registrations"] = [{"course": "FC70", "course_raw": "FC70", "paid": paid, "class_id": class_id}]
    db["app"]["smart_answers"] = {"share_class_links": share}
    assert ("SECRET" in ask("เข้าเรียนที่ไหนคะ")["message"]["text"]) is visible


def test_status_asks_for_slip_when_none(db):
    db["registrations"] = [{"course": "FC70", "course_raw": "FC70", "paid": False, "class_id": None}]
    assert "ยังไม่พบสลิป" in ask("โอนแล้วค่ะ")["message"]["text"]


def test_slip_without_registration_is_acknowledged(db):
    db["slips"] = [{"id": 1}]
    assert "ได้รับรูปสลิปของคุณแล้ว" in ask("โอนแล้วค่ะ")["message"]["text"]


def test_quick_reply_limits(db):
    items = ask("ค่าติวเท่าไหร่คะ")["message"]["quickReply"]["items"]
    assert len(items) <= 13 and all(len(i["action"]["label"]) <= 20 for i in items)


def _run_pipeline(monkeypatch, db, text, rules, source_type="user"):
    sent, alerts = [], []
    db["auto_replies"] = rules
    async def reply(tok, msgs):
        sent.append(msgs)
        return 200, ""
    async def noop(*a, **k):
        return []
    async def alert(*a, **k):
        alerts.append(a)
    monkeypatch.setattr(core.line, "reply", reply)
    monkeypatch.setattr(core.supa, "insert", noop)
    monkeypatch.setattr(core.supa, "update", noop)
    monkeypatch.setattr(sa, "alert_admin", alert)
    ev = {"type": "message", "replyToken": "r", "source": {"type": source_type, "userId": UID},
          "message": {"type": "text", "text": text}}
    got = asyncio.run(core._handle_auto_replies([ev], gemini_uids={UID}))
    return got, sent, alerts


def test_pipeline_beats_fallback_and_ai_and_alerts_admin(monkeypatch, db):
    fb = {"id": 1, "trigger": "fallback", "messages": [{"type": "text", "text": "FALLBACK"}]}
    got, sent, alerts = _run_pipeline(monkeypatch, db, "สมัครได้ถึงวันไหนคะ", [fb])
    assert got == {UID} and "FALLBACK" not in sent[0][0]["text"] and alerts


def test_pipeline_owner_rule_wins(monkeypatch, db):
    rule = {"id": 2, "trigger": "text", "match_type": "contains", "keywords": ["ค่าติว"],
            "messages": [{"type": "text", "text": "OWNER"}]}
    _got, sent, _a = _run_pipeline(monkeypatch, db, "ค่าติวเท่าไหร่คะ", [rule])
    assert sent[0][0]["text"] == "OWNER"


def test_pipeline_works_without_any_rules_and_can_be_disabled(monkeypatch, db):
    got, sent, _a = _run_pipeline(monkeypatch, db, "ค่าติวเท่าไหร่คะ", [])
    assert got == {UID} and sent
    db["app"]["smart_answers"] = {"enabled": False}
    got, sent, _a = _run_pipeline(monkeypatch, db, "ค่าติวเท่าไหร่คะ", [])
    assert got == set() and not sent


def test_pipeline_never_answers_in_groups(monkeypatch, db):
    _got, sent, _a = _run_pipeline(monkeypatch, db, "โอนแล้วค่ะ", [], source_type="group")
    assert not sent

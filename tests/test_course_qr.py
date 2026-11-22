"""quick reply 'รายละเอียดหลักสูตร' หลังผู้ใช้สอบถาม"""
import asyncio
import pytest
from _lib import core

ACCTS = [
    {"course": "FC", "price": 1499, "full_price": 1999, "bank": "กรุงเทพ", "account_no": "080-0-1", "account_name": "ธ"},
    {"course": "IC", "price": 1299, "full_price": None, "bank": "กรุงเทพ", "account_no": "080-0-2", "account_name": "ธ"},
    {"course": "FC", "price": 1, "full_price": 1, "bank": "x", "account_no": "9", "account_name": "dup"},
]
CLASSES = [{"name": "FC รุ่น 5", "cohort": "5", "start_date": "2026-12-01", "schedule": "เสาร์ 9-12", "capacity": 50,
            "zoom_url": "SECRET"}]


@pytest.fixture(autouse=True)
def env(monkeypatch):
    settings = {}
    async def sel(t, params=None, **k):
        if t == "payment_accounts":
            return ACCTS
        if t == "classes":
            return CLASSES
        return []
    async def gs(key, default=None):
        return settings.get(key, default)
    monkeypatch.setattr(core.supa, "select", sel)
    monkeypatch.setattr(core, "_get_setting", gs)
    core._course_qr_cache.update(exp=0.0, courses=[])
    return settings


def test_attach_adds_one_button_per_course_on_last_message():
    msgs = asyncio.run(core._attach_course_qr([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]))
    assert "quickReply" not in msgs[0]
    items = msgs[1]["quickReply"]["items"]
    assert [i["action"]["data"] for i in items] == ["course_info:FC", "course_info:IC"]   # FC ซ้ำถูกรวม
    assert all(len(i["action"]["label"]) <= 20 for i in items)


def test_does_not_override_existing_quick_reply():
    m = [{"type": "text", "text": "a", "quickReply": {"items": ["keep"]}}]
    assert asyncio.run(core._attach_course_qr(m)) == m


def test_can_be_disabled(env):
    env["course_quick_reply"] = False
    m = [{"type": "text", "text": "a"}]
    assert asyncio.run(core._attach_course_qr(m)) == m


def test_course_info_content_and_no_private_links(env):
    env["reg_liff_url"] = "https://liff.line.me/123"
    msg = asyncio.run(core._course_info_messages("fc"))[0]
    t = msg["text"]
    assert "1,499" in t and "1,999" in t and "FC รุ่น 5" in t and "1/12/2569" in t and "080-0-1" in t
    assert "SECRET" not in t
    acts = [i["action"] for i in msg["quickReply"]["items"]]
    assert any(a.get("data") == "course_info:IC" for a in acts)
    assert not any(a.get("data") == "course_info:FC" for a in acts)      # ไม่เสนอหลักสูตรที่กำลังดูอยู่
    assert any(a["type"] == "uri" for a in acts) and any(a.get("text") == "ติดต่อแอดมิน" for a in acts)


def test_unknown_course(env):
    t = asyncio.run(core._course_info_messages("ZZ"))[0]["text"]
    assert "ยังไม่พบ" in t


def test_reply_rule_attaches_only_for_text_and_fallback(monkeypatch):
    sent = []
    async def reply(tok, msgs):
        sent.append(msgs)
        return 200, ""
    async def upd(*a, **k):
        pass
    monkeypatch.setattr(core.line, "reply", reply)
    monkeypatch.setattr(core.supa, "update", upd)
    for trig in ("text", "fallback", "follow"):
        asyncio.run(core._reply_rule("t", {"id": 1, "trigger": trig, "messages": [{"type": "text", "text": "hi"}]}))
    assert "quickReply" in sent[0][-1] and "quickReply" in sent[1][-1] and "quickReply" not in sent[2][-1]

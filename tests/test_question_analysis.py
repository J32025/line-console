"""วิเคราะห์คำถามขาเข้า: คัดคำถาม/ข้อมูลส่วนตัว และตัวเลขต้องมาจากข้อมูลจริง"""
import asyncio
from _lib import question_analysis as qa


def msgs(*pairs):
    return [{"line_user_id": u, "text": t} for u, t in pairs]


def test_collect_merges_variants_and_filters():
    d = qa.collect_questions(msgs(
        ("A", "เริ่มเรียนวันไหนครับ"), ("B", "เริ่มเรียน วันไหน คะ?"), ("B", "เริ่มเรียนวันไหน"),
        ("C", "ขอบคุณครับ"),                       # ไม่ใช่คำถาม
        ("D", "โทร 0812345678 ได้ไหม"),            # เบอร์โทร
        ("E", "คุณสมบัติผู้สมัครมีอะไรบ้าง"),        # ต้องไม่ถูกตัดเพราะคำว่า คุณ
        ("F", "/ตรวจข้อมูล หรือ"), ("G", "")))
    top = d["items"][0]
    assert top["n"] == 3 and top["users"] == {"A", "B"}
    assert {g["q"] for g in d["items"]} == {"เริ่มเรียนวันไหนครับ", "คุณสมบัติผู้สมัครมีอะไรบ้าง"}
    assert d["total_questions"] == 4 and d["skipped_pii"] == 1 and d["total_messages"] == 8


def test_ai_themes_counts_from_data_and_keeps_leftovers():
    items = qa.collect_questions(msgs(("A", "ราคาเท่าไหร่"), ("B", "ราคาเท่าไหร่"), ("A", "ค่าเรียนกี่บาท"),
                                      ("C", "มีคลิปย้อนหลังไหม")))["items"]
    ids = {g["q"]: i for i, g in enumerate(items, 1)}
    res = {"themes": [{"title": "ราคา", "action": "rule", "count": 999, "keywords": ["ราคา"], "draft": "[ระบุราคา]",
                       "ids": [ids["ราคาเท่าไหร่"], ids["ค่าเรียนกี่บาท"], 77, True, ids["ราคาเท่าไหร่"]]},
                      {"title": "ว่าง", "ids": []}, "ขยะ"]}
    th = qa.ai_themes(res, items)
    assert th[0]["count"] == 3 and th[0]["people"] == 2 and th[0]["variants"] == 2
    assert th[-1]["title"] == "ยังไม่ได้จัดกลุ่ม" and th[-1]["examples"] == ["มีคลิปย้อนหลังไหม"]
    assert qa.ai_themes(None, items) is None and qa.ai_themes({"themes": []}, items) is None


def test_fallback_when_ai_unavailable_and_not_cached(monkeypatch):
    saved = []
    async def sel_all(t, params=None, **k):
        return msgs(("A", "ราคาเท่าไหร่"), ("B", "โอนแล้วตรวจสอบหรือยัง"))
    async def no_ai(*a, **k):
        return None
    async def gs(key, default=None):
        return default
    async def upsert(*a, **k):
        saved.append(a)
    monkeypatch.setattr(qa.supa, "select_all", sel_all)
    monkeypatch.setattr(qa.supa, "upsert", upsert)
    monkeypatch.setattr(qa, "_ai_text_json", no_ai)
    monkeypatch.setattr(qa, "_get_setting", gs)
    r = asyncio.run(qa.analyze(30))
    assert r["method"] == "keyword" and {t["title"] for t in r["themes"]} == {"ราคา/วิธีชำระ", "สถานะชำระเงิน/สลิป"}
    assert r["covered_questions"] == 2 and not saved

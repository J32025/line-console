"""routes กลุ่ม autoreply — แยกจาก api/index.py"""
from _lib import supa
from _lib.auth import current_admin
from _lib.config import ANTHROPIC_API_KEY
from _lib.config import GEMINI_API_KEY
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
import re
from fastapi import APIRouter
from _lib import question_analysis
from _lib import smart_answers
from _lib.core import (NOW, _GAP_STOP, _KB_TOPIC_SETTING_KEY, _PROCUREMENT_TOPICS, _gemini_kb_cache, _get_setting, _iso_ago, _kb_autogen_batch, _match, _normalize_messages, _teach_find, _teach_mark, _teach_public, _teach_state, _tok)

router = APIRouter()


@router.get("/api/kb/autogen/status")
async def kb_autogen_status(admin=Depends(current_admin)):
    done = set(await _get_setting(_KB_TOPIC_SETTING_KEY, []) or [])
    pending = [t for t in _PROCUREMENT_TOPICS if t not in done]
    return {"total": len(_PROCUREMENT_TOPICS), "done": len(_PROCUREMENT_TOPICS) - len(pending),
            "pending": pending, "ai_ready": bool(ANTHROPIC_API_KEY or GEMINI_API_KEY)}


@router.post("/api/kb/autogen/run")
async def kb_autogen_run(req: Request, admin=Depends(current_admin)):
    if not (ANTHROPIC_API_KEY or GEMINI_API_KEY):
        raise HTTPException(400, "ยังไม่ได้ตั้งค่า AI (ANTHROPIC_API_KEY หรือ GEMINI_API_KEY)")
    b = {}
    try:
        b = await req.json()
    except Exception:
        pass
    res = await _kb_autogen_batch(int(b.get("count") or 3), admin["userId"])
    await supa.log_operation(admin["userId"], "kb.autogen", {"count": b.get("count")}, res)
    return {"ok": True, **res}


# ---------- knowledge base ----------
@router.get("/api/kb")
async def kb_list(admin=Depends(current_admin)):
    try:
        rows = await supa.select("kb_articles", params={"select": "*", "order": "category,title"})
    except Exception:
        return {"articles": [], "schema_missing": True,
                "hint": "รัน migration 0010 (kb_articles) ใน Supabase SQL Editor"}
    return {"articles": rows}


@router.post("/api/kb")
async def kb_save(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    if not (b.get("title") or "").strip() or not (b.get("body") or "").strip():
        raise HTTPException(400, "ต้องมีหัวข้อและเนื้อหา")
    row = {"title": b["title"].strip(), "body": b["body"].strip(),
           "keywords": [k.strip() for k in (b.get("keywords") or []) if k.strip()],
           "category": b.get("category"), "enabled": b.get("enabled", True),
           "updated_by": admin["userId"], "updated_at": NOW()}
    if b.get("id"):
        await supa.update("kb_articles", row, {"id": f"eq.{b['id']}"})
    else:
        await supa.insert("kb_articles", row)
    _gemini_kb_cache["items"] = None
    return {"ok": True}


@router.delete("/api/kb/{aid}")
async def kb_delete(aid: int, admin=Depends(current_admin)):
    await supa.delete("kb_articles", {"id": f"eq.{aid}"})
    _gemini_kb_cache["items"] = None
    return {"ok": True}


@router.get("/api/kb/gaps")
async def kb_gaps(admin=Depends(current_admin), days: int = 14):
    """คำถามที่ Gemini ตอบแล้วแต่ไม่เจอบทความ/FAQ ที่เกี่ยวข้องเลยในคลังความรู้ (gemini.kb_gap log)
    ใช้ดูว่าควรเพิ่มบทความอะไรเข้า /kb"""
    days = max(3, min(days, 60))
    since = _iso_ago(days=days)
    try:
        rows = await supa.select_all("operations", params={
            "select": "params,created_at", "action": "eq.gemini.kb_gap",
            "created_at": f"gte.{since}"})
    except Exception:
        rows = []
    from collections import Counter
    texts = [re.sub(r"\s+", " ", str((r.get("params") or {}).get("q") or "").strip()) for r in rows]
    texts = [t for t in texts if t]
    exact = Counter(t.lower() for t in texts)
    top_questions = [{"text": k, "count": v} for k, v in exact.most_common(40)]
    words = Counter()
    for t in texts:
        for w in re.findall(r"[ก-๙a-zA-Z]{2,}", t.lower()):
            if w not in _GAP_STOP and len(w) >= 2:
                words[w] += 1
    top_keywords = [{"word": w, "count": c} for w, c in words.most_common(30) if c >= 2]
    return {"days": days, "total": len(texts),
            "top_questions": top_questions, "top_keywords": top_keywords, "samples": texts[:60]}


@router.get("/api/smart-answers/config")
async def smart_answers_config(admin=Depends(current_admin)):
    return await smart_answers.config()


@router.post("/api/smart-answers/test")
async def smart_answers_test(req: Request, admin=Depends(current_admin)):
    """ดูคำตอบโดยไม่ส่งจริง/ไม่แจ้งเตือน — config ที่ส่งมา (ยังไม่บันทึก) ใช้ทดลองได้"""
    b = await req.json()
    uid = str(b.get("userId") or "").strip()
    if uid and not re.fullmatch(r"U[0-9a-f]{32}", uid):
        raise HTTPException(400, "userId ไม่ถูกต้อง")
    cfg = await smart_answers.config()
    draft = b.get("config")
    if isinstance(draft, dict):
        cfg.update({k: str(draft.get(k) or "")[:1500] for k in smart_answers.TEXT_FIELDS})
        cfg["share_class_links"] = draft.get("share_class_links") is True
    out = await smart_answers.compose(uid, str(b.get("text") or "")[:500], cfg)
    return {"matched": bool(out), **(out or {})}


@router.get("/api/kb/question-analysis")
async def kb_question_analysis(admin=Depends(current_admin), days: int = 30, refresh: int = 0):
    """จัดกลุ่มคำถามขาเข้าทั้งหมด (AI ถ้าใช้ได้ ไม่งั้นจัดตามคำสำคัญ)"""
    return await question_analysis.analyze(max(1, min(days, 90)), bool(refresh))


@router.get("/api/kb/teach")
async def kb_teach_list(admin=Depends(current_admin), refresh: int = 0):
    if not (ANTHROPIC_API_KEY or GEMINI_API_KEY):
        raise HTTPException(400, "ยังไม่ได้ตั้งค่า AI")
    return _teach_public(await _teach_state(bool(refresh)))


@router.post("/api/kb/teach")
async def kb_teach_save(req: Request, admin=Depends(current_admin)):
    """บันทึกคำตอบของเจ้าของเป็นบทความความรู้ที่ 'ใช้ทันที' (เจ้าของเป็นคนเขียนเอง จึงไม่ต้องรอตรวจซ้ำ)"""
    b = await req.json()
    answer = (b.get("answer") or "").strip()
    if len(answer) < 10:
        raise HTTPException(400, "คำตอบสั้นเกินไป (อย่างน้อย 10 ตัวอักษร)")
    theme = await _teach_find(str(b.get("key") or ""))
    title = (b.get("title") or theme["title"]).strip()[:120]
    kw = sorted(_tok(title) | set().union(*[_tok(x) for x in theme.get("examples", [])]))[:24]
    res = await supa.insert("kb_articles", {
        "title": title, "body": answer[:2000], "keywords": kw, "category": "สอนโดยแอดมิน",
        "enabled": True, "updated_by": admin["userId"], "updated_at": NOW()})
    await _teach_mark(theme)
    _gemini_kb_cache["items"] = None
    await supa.log_operation(admin["userId"], "kb.teach", {"title": title, "questions": theme.get("count")}, None)
    return {"ok": True, "id": (res[0]["id"] if res else None)}


@router.post("/api/kb/teach/dismiss")
async def kb_teach_dismiss(req: Request, admin=Depends(current_admin)):
    """ข้ามหัวข้อนี้ (ไม่ต้องสอน เช่น ทักทาย/ขอบคุณ) — คำถามกลุ่มนี้จะไม่โผล่มาอีก"""
    b = await req.json()
    theme = await _teach_find(str(b.get("key") or ""))
    await _teach_mark(theme)
    return {"ok": True}


@router.get("/api/insights/gaps")
async def insight_gaps(admin=Depends(current_admin), days: int = 14):
    """ข้อความที่ลูกค้าพิมพ์มาแต่ไม่ตรงกฎ auto-reply ไหนเลย — จัดกลุ่มให้เห็นว่าควรสร้างกฎอะไร"""
    days = max(3, min(days, 60))
    since = _iso_ago(days=days)
    msgs = await supa.select_all("messages", params={
        "select": "text,created_at", "direction": "eq.in", "msg_type": "eq.text",
        "created_at": f"gte.{since}"})
    rules = await supa.select("auto_replies", params={
        "select": "keywords,match_type", "enabled": "eq.true", "trigger": "eq.text", "limit": "300"})

    def _has_rule(text: str) -> bool:
        for r in rules:
            if _match({"keywords": r.get("keywords"), "match_type": r.get("match_type", "contains")}, text):
                return True
        return False

    from collections import Counter
    unmatched = [re.sub(r"\s+", " ", (m.get("text") or "").strip())
                 for m in msgs if m.get("text") and m["text"].strip()]
    unmatched = [t for t in unmatched if not _has_rule(t)]

    exact = Counter(t.lower()[:140] for t in unmatched if 2 <= len(t) <= 200)
    top_questions = [{"text": k, "count": v} for k, v in exact.most_common(40) if v >= 2]

    words = Counter()
    for t in unmatched:
        for w in re.findall(r"[ก-๙a-zA-Z]{2,}", t.lower()):
            if w not in _GAP_STOP and len(w) >= 2:
                words[w] += 1
    top_keywords = [{"word": w, "count": c} for w, c in words.most_common(30) if c >= 3]

    return {
        "days": days,
        "total_in_text": len(msgs),
        "unmatched": len(unmatched),
        "unmatched_pct": round(len(unmatched) / (len(msgs) or 1) * 100),
        "top_questions": top_questions,
        "top_keywords": top_keywords,
        "samples": unmatched[:60],
    }


# AUTO-REPLY (keyword responder)
@router.get("/api/auto-replies")
async def list_auto_replies(admin=Depends(current_admin)):
    return {"rules": await supa.select("auto_replies", params={
        "select": "*", "order": "priority.desc,id.asc",
    })}


@router.post("/api/auto-replies")
async def create_auto_reply(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    row = {
        "name": b.get("name"),
        "enabled": b.get("enabled", True),
        "trigger": b.get("trigger", "text"),
        "match_type": b.get("match_type", "contains"),
        "keywords": b.get("keywords", []),
        "messages": _normalize_messages(b.get("messages", [])),
        "priority": int(b.get("priority", 0)),
        "created_by": admin["userId"],
    }
    if b.get("id"):
        await supa.update("auto_replies", row, {"id": f"eq.{b['id']}"})
        return {"ok": True, "id": b["id"]}
    r = await supa.insert("auto_replies", row)
    return {"ok": True, "rule": r[0] if r else None}


@router.delete("/api/auto-replies/{rid}")
async def delete_auto_reply(rid: int, admin=Depends(current_admin)):
    await supa.delete("auto_replies", {"id": f"eq.{rid}"})
    return {"ok": True}


@router.get("/api/automations")
async def list_automations(admin=Depends(current_admin)):
    return {"automations": await supa.select("automations", params={"select": "*", "order": "id.desc"})}


@router.post("/api/automations")
async def save_automation(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    steps = []
    for s in b.get("steps", []):
        steps.append({
            "delayHours": int(s.get("delayHours", 0)),
            "delayMinutes": int(s.get("delayMinutes", 0)),
            "messages": _normalize_messages(s.get("messages", [])),
        })
    row = {"name": b["name"], "enabled": b.get("enabled", True),
           "trigger": b.get("trigger", "follow"), "trigger_config": b.get("triggerConfig", {}),
           "steps": steps, "created_by": admin["userId"]}
    if b.get("id"):
        await supa.update("automations", row, {"id": f"eq.{b['id']}"})
        return {"ok": True, "id": b["id"]}
    r = await supa.insert("automations", row)
    return {"ok": True, "automation": r[0] if r else None}


@router.delete("/api/automations/{aid}")
async def del_automation(aid: int, admin=Depends(current_admin)):
    await supa.delete("automations", {"id": f"eq.{aid}"})
    await supa.delete("automation_runs", {"automation_id": f"eq.{aid}", "status": "eq.pending"})
    return {"ok": True}

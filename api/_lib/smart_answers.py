"""ตอบอัตโนมัติอัจฉริยะ: จับเจตนาคำถามที่พบบ่อย แล้วตอบจากข้อมูลจริงของผู้ถาม

หลักการ
- ไม่แต่งข้อเท็จจริง: ราคา/บัญชี/สถานะ/ตารางมาจากฐานข้อมูล · เรื่องที่ไม่มีในฐานข้อมูล (หมดเขต, ทางเข้าเรียน)
  ใช้ข้อความที่เจ้าของกรอกเอง ถ้ายังไม่มี -> บอกผู้ใช้ตรง ๆ ว่าส่งต่อแอดมิน และแจ้งแอดมินจริง
- กฎคีย์เวิร์ดที่เจ้าของตั้งเองมาก่อนเสมอ โมดูลนี้ทำงานเฉพาะข้อความที่ไม่ตรงกฎไหน (ก่อน fallback/AI)
- จับเจตนาด้วยคำบ่งชี้ (ไม่เรียก AI = ไม่มีค่าใช้จ่าย ผลคงที่) จับไม่ได้ = ปล่อยให้ fallback/AI ตามเดิม
"""
import datetime as dt
import re

from _lib import line, supa
from _lib.core import (NOW, _attach_course_qr, _course_prefix, _course_quick_reply, _get_setting, _is_member_menu_user, _is_urgent,
                       _pay_account_for, _pay_lines, _status_check_text, _thai_date, alert_admin)

SETTING_KEY = "smart_answers"
TEXT_FIELDS = ("deadline", "start", "access", "contact")
INFO = ("deadline", "price", "start")   # ถามหลายเรื่องในข้อความเดียว -> ตอบรวมในข้อความเดียว

# เนื้อหาสอบ/กฎหมายพัสดุ และคลิปย้อนหลัง ไม่ใช่เรื่องที่โมดูลนี้ตอบ
_SKIP_RE = re.compile(r"ราคากลาง|ราคาอ้างอิง|พ\.?ร\.?บ|ระเบียบ|มาตรา|กฎกระทรวง|ย้อนหลัง")
_QUESTION_RE = re.compile(
    r"ไหม|มั้ย|มั๊ย|หรือ|รึ|อะไร|เมื่อไ|เมื่อใด|ยังไง|อย่างไร|เท่าไ|เท่าใด|กี่|ไหน|สอบถาม|ขอ|ตาราง|บ้าง|ทัน|\?")

_INTENTS = {
    "contact": r"ติดต่อ\s*(แอดมิน|เจ้าหน้าที่|ยังไง|อย่างไร|ได้ที่ไหน|ทางไหน)|ขอเบอร์|(คุย|พูด)กับ\s*(คน|แอดมิน|เจ้าหน้าที่)",
    "access": (r"เข้า\s*(เรียน|ระบบ|ติว|อบรม)[^\n]{0,12}(ไหน|ยังไง|อย่างไร)|เข้า(ได้)?(ที่|ตรง|ทาง)ไหน|ระบบข้อสอบ|ข้อสอบให้ทดลอง|"
               r"ทำข้อสอบ[^\n]{0,10}(ไหน|ยังไง|อย่างไร)|ทดลองทำ|pre-?test|(ลิงก์|ลิ้งค์|ลิงค์|ลิ้ง)\s*(เข้า|เรียน|ซูม|zoom|กลุ่ม)"),
    "status": (r"(โอน|จ่าย|ชำระ)[^\n]{0,14}แล้ว|ส่งสลิป[^\n]{0,12}(แล้ว|หรือยัง|ยัง|ไหม)|ตรวจ(สอบ)?\s*สลิป|"
               r"สถานะ(การ)?\s*(สมัคร|ชำระ|ลงทะเบียน|โอน|ของ)|ได้รับ\s*(เงิน|สลิป|ยอด)[^\n]{0,8}(ยัง|ไหม|มั้ย)"),
    "deadline": (r"(สมัคร|ลงทะเบียน|โอน|ชำระ|จ่าย)[^\n]{0,12}(ได้ถึง|ถึงวันไหน|ถึงเมื่อ|ก่อนวันไหน|ภายในวันไหน)|สมัครทัน|"
                 r"ยัง(สมัคร|ลงทะเบียน)(ได้|ทัน)|หมดเขต|ปิดรับ|เต็ม\s*(หรือยัง|ยัง|แล้วหรือ|แล้วไหม|ไหม)"),
    "price": (r"ค่า\s*(ลงทะเบียน|สมัคร|ติว|เรียน|ใช้จ่าย|อบรม|คอร์ส)|กี่บาท|ราคา\s*(เท่าไ|คอร์ส|ติว|เรียน)|"
              r"(สมัคร|เรียน|ติว|คอร์ส)[^\n]{0,8}เท่าไ|เลข(ที่)?บัญชี|โอน(เงิน)?(เข้า)?\s*(บัญชีไหน|บัญชีอะไร|ที่ไหน|ยังไง)"),
    "start": (r"เริ่ม\s*(ติว|เรียน|อบรม)|(ติว|เรียน|อบรม)[^\n]{0,8}(วันไหน|เมื่อไ|ช่วงไหน|กี่โมง)|ตาราง\s*(ติว|เรียน|อบรม)"),
}


def detect_intents(text: str) -> list[str]:
    """คืนเจตนาที่จะตอบ ([] = ไม่รับตอบ) · เรื่องร้องเรียน/เร่งด่วน -> ['urgent']"""
    t = (text or "").strip().lower()
    if not t or t.startswith("/") or len(t) > 160 or t.count("\n") > 1:
        return []
    if _is_urgent(t):
        return ["urgent"]
    if _SKIP_RE.search(t):
        return []
    hit = {k for k, rx in _INTENTS.items() if re.search(rx, t)}
    for k in ("contact", "access", "status"):   # เรื่องเฉพาะตัวมาก่อนและตอบเดี่ยว
        if k in hit:
            return [k]
    # คำถามข้อมูลทั่วไปต้องมีลักษณะเป็นคำถาม กันประโยคบอกเล่า เช่น "เริ่มเรียนแล้วค่ะ"
    if not _QUESTION_RE.search(t):
        return []
    return [k for k in INFO if k in hit]


async def config() -> dict:
    v = await _get_setting(SETTING_KEY, None)
    v = v if isinstance(v, dict) else {}
    return {"enabled": v.get("enabled", True) is not False,
            "share_class_links": v.get("share_class_links") is True,
            **{k: str(v.get(k) or "").strip()[:1500] for k in TEXT_FIELDS}}


async def _regs(uid: str) -> list:
    if not uid:
        return []
    return await supa.select("registrations", params={
        "line_user_id": f"eq.{uid}", "select": "course,course_raw,paid,class_id", "order": "created_at.desc"})


async def _open_classes(prefix: str | None) -> list:
    params = {"select": "course,name,cohort,start_date,schedule", "status": "in.(open,running)",
              "order": "start_date.asc", "limit": "12"}
    if prefix:
        params["course"] = f"like.{prefix}*"
    try:
        return await supa.select("classes", params=params)
    except Exception:  # noqa: BLE001
        return []


def _ask_admin(topic: str) -> str:
    return f"เรื่อง{topic} ขอส่งให้แอดมินตอบนะครับ จะรีบตอบในแชตนี้ครับ 🙏"


async def _sec_price(uid, regs, cfg):
    accts = await supa.select("payment_accounts", params={"select": "*", "active": "eq.true", "order": "id.asc"})
    unpaid = None if cfg.get("_member") else next((r for r in regs if not r.get("paid")), None)
    if unpaid:   # ลงทะเบียนแล้วยังไม่จ่าย -> ยอดและบัญชีของหลักสูตรตัวเอง
        pay = _pay_lines(await _pay_account_for(unpaid.get("course") or ""))
        if pay:
            return (f"💰 หลักสูตรที่คุณลงทะเบียน: {unpaid.get('course_raw') or unpaid.get('course')}\n{pay}\n"
                    "โอนแล้วส่งรูปสลิปในแชตนี้ได้เลยครับ"), None
    lines, seen = [], set()
    for a in accts:
        name = str(a.get("course") or "")
        price = a.get("price") if a.get("price") is not None else a.get("full_price")
        if name and name not in seen and price is not None:
            seen.add(name)
            lines.append(f"• {name}: {float(price):,.0f} บาท")
    if not lines:
        return _ask_admin("ค่าลงทะเบียน"), "ถามค่าลงทะเบียน (ไม่มีราคาในระบบ)"
    head = "💰 ค่าลงทะเบียนแต่ละหลักสูตร"
    if regs and all(r.get("paid") for r in regs):
        head = "คุณชำระหลักสูตรที่ลงทะเบียนเรียบร้อยแล้วครับ ✅\n💰 ค่าลงทะเบียนแต่ละหลักสูตร"
    if cfg.get("_member"):
        head = "คุณมีสิทธิ์เข้าใช้งานอยู่แล้วครับ ✅\n💰 ค่าลงทะเบียนแต่ละหลักสูตร"
    return head + "\n" + "\n".join(lines) + "\nกดปุ่มหลักสูตรด้านล่างเพื่อดูรายละเอียดและบัญชีโอนครับ", None


async def _sec_start(uid, regs, cfg):
    prefix = _course_prefix(regs[0].get("course")) if regs else None
    today = dt.date.today().isoformat()
    upcoming = [c for c in await _open_classes(prefix) if str(c.get("start_date") or "") >= today]
    parts = []
    if upcoming:
        rows = []
        for c in upcoming[:4]:
            title = c.get("name") or c.get("course")
            rows.append(f"• {title}: เริ่ม {_thai_date(c['start_date'])}"
                        + (f" ({c['schedule']})" if c.get("schedule") else ""))
        parts.append("📅 กำหนดเริ่มเรียน\n" + "\n".join(rows))
    if cfg["start"]:
        parts.append(cfg["start"] if upcoming else "📅 " + cfg["start"])
    if parts:
        return "\n".join(parts), None
    return _ask_admin("วันเริ่มติว"), "ถามวันเริ่มติว (ยังไม่มีคลาสที่ระบุวันเริ่ม และไม่ได้กรอกข้อความ)"


async def _sec_deadline(uid, regs, cfg):
    if cfg["deadline"]:
        return "⏰ " + cfg["deadline"], None
    return _ask_admin("กำหนดปิดรับสมัคร/ชำระเงิน"), "ถามกำหนดปิดรับสมัคร (ยังไม่ได้กรอกข้อความ)"


async def _ans_status(uid, regs, cfg):
    text, _paid = await _status_check_text(uid)
    try:
        slip = await supa.select("slips", params={"line_user_id": f"eq.{uid}", "select": "id", "limit": "1"})
    except Exception:  # noqa: BLE001
        slip = [True]
    if not slip and not cfg.get("_member") and not any(r.get("paid") for r in regs):
        text += "\n\n📎 ระบบยังไม่พบสลิปของคุณ ถ้าโอนแล้ว ส่งรูปสลิปในแชตนี้ได้เลยครับ"
    return text, None


async def _ans_access(uid, regs, cfg):
    member = bool(cfg.get("_member"))
    paid = regs if member else [r for r in regs if r.get("paid")]
    if member:
        text = "คุณมีสิทธิ์เข้าใช้งานแล้วครับ ✅ ใช้งานได้จากเมนูด้านล่าง"
    elif not regs:
        text = "ยังไม่พบข้อมูลลงทะเบียนของคุณครับ ลงทะเบียนได้ที่เมนูด้านล่าง"
    elif not paid:
        pay = _pay_lines(await _pay_account_for(regs[0].get("course") or ""))
        text = ("ลงทะเบียนแล้ว แต่ระบบยังไม่ยืนยันการชำระเงินครับ 🟡" + (f"\n{pay}" if pay else "")
                + "\nถ้าโอนแล้ว พิมพ์ /ตรวจข้อมูล เพื่อดูสถานะสลิปได้ครับ")
    else:
        text = "ระบบยืนยันการชำระเงินของคุณแล้วครับ ✅"
    shared = False
    # ลิงก์เรียนให้เฉพาะคนที่จ่ายแล้ว ถูกจัดเข้าคลาสแล้ว และเจ้าของเปิดตัวเลือกนี้เอง
    if paid and cfg["share_class_links"]:
        for r in paid:
            if not r.get("class_id"):
                continue
            rows = await supa.select("classes", params={
                "select": "name,schedule,zoom_url,materials_url", "id": f"eq.{r['class_id']}", "limit": "1"})
            c = rows[0] if rows else {}
            links = [f"{label}: {c[k]}" for k, label in (("zoom_url", "🔗 ห้องเรียน"), ("materials_url", "📚 เอกสาร"))
                     if c.get(k)]
            if links:
                shared = True
                text += "\n" + "\n".join([f"คลาส: {c.get('name') or '-'}"] + links)
    if cfg["access"]:
        return f"{text}\n\n{cfg['access']}", None
    if shared:
        return text, None
    return f"{text}\n\n{_ask_admin('ทางเข้าเรียน/ระบบข้อสอบ')}", "ถามทางเข้าเรียน/ระบบข้อสอบ"


async def _ans_contact(uid, regs, cfg):
    return (cfg["contact"] or "รับเรื่องแล้วครับ เดี๋ยวแอดมินมาตอบในแชตนี้นะครับ 🙏"), "ขอติดต่อแอดมิน"


async def _ans_urgent(uid, regs, cfg):
    return "รับเรื่องของคุณแล้วครับ 🙏 ส่งต่อให้แอดมินดูแลโดยเร็วครับ", "ข้อความอาจร้องเรียน/เร่งด่วน"


_HANDLERS = {"price": _sec_price, "start": _sec_start, "deadline": _sec_deadline, "status": _ans_status,
             "access": _ans_access, "contact": _ans_contact, "urgent": _ans_urgent}


async def _quick_reply(intents: list[str]) -> dict:
    extra = []
    if "status" not in intents:
        extra.append({"type": "action", "action": {"type": "message", "label": "🔎 ตรวจสถานะ", "text": "/ตรวจข้อมูล"}})
    if not {"contact", "urgent"} & set(intents):
        extra.append({"type": "action", "action": {"type": "message", "label": "🙋 ติดต่อแอดมิน", "text": "ติดต่อแอดมิน"}})
    url = await _get_setting("reg_liff_url", None)
    if url:
        extra.append({"type": "action", "action": {"type": "uri", "label": "📝 ลงทะเบียน", "uri": str(url)}})
    # ปุ่มหลักสูตรเฉพาะเรื่องที่เกี่ยวกับการเลือกหลักสูตร (ปิดได้ด้วย course_quick_reply เหมือนเดิม)
    if set(intents) & set(INFO):
        qr = await _course_quick_reply()
        if qr:
            extra = qr["items"][: 13 - len(extra)] + extra
    return {"items": extra[:13]}


async def compose(uid: str, text: str, cfg: dict | None = None) -> dict | None:
    """สร้างคำตอบ (ไม่ส่ง ไม่มีผลข้างเคียง — ใช้ทั้งตอบจริงและหน้าทดสอบ) · None = ไม่รับตอบ"""
    intents = detect_intents(text)
    if not intents:
        return None
    cfg = cfg or await config()
    regs = await _regs(uid)
    cfg = {**cfg, "_member": await _is_member_menu_user(uid)}
    sections, reasons = [], []
    for k in intents:
        body, reason = await _HANDLERS[k](uid, regs, cfg)
        sections.append(body)
        if reason:
            reasons.append(reason)
    msg = {"type": "text", "text": "\n\n".join(sections)[:4900]}
    try:
        qr = await _quick_reply(intents)
        if qr["items"]:
            msg["quickReply"] = qr
    except Exception as ex:  # noqa: BLE001
        print("smart quick reply error:", ex)
        msg = (await _attach_course_qr([msg]))[0]
    return {"intents": intents, "message": msg, "escalate": " · ".join(reasons) or None}


async def _escalate(uid: str, reason: str, question: str):
    """ทำให้คำว่า 'ส่งให้แอดมิน' เป็นจริง: ติดแท็กรอแอดมิน + เพิ่ม unread + แจ้งเตือน"""
    try:
        ex = await supa.select("line_users", params={"select": "unread,tags", "line_user_id": f"eq.{uid}", "limit": "1"})
        cur = ex[0] if ex else {}
        await supa.update("line_users", {"unread": (cur.get("unread") or 0) + 1,
                                         "tags": sorted(set(cur.get("tags") or []) | {"รอแอดมิน"}),
                                         "updated_at": NOW()}, {"line_user_id": f"eq.{uid}"})
    except Exception as e:  # noqa: BLE001
        print("smart escalate tag error:", e)
    try:
        await alert_admin("🙋 ลูกค้ารอแอดมิน", f"{reason}\n\"{question[:120]}\"", throttle_key=f"esc_{uid}")
    except Exception as e:  # noqa: BLE001
        print("smart escalate alert error:", e)


async def handle(event: dict) -> dict | None:
    """ตอบข้อความจริง คืนข้อความที่ส่งสำเร็จ (ให้ผู้เรียกบันทึก) หรือ None เพื่อปล่อยให้ fallback/AI ทำต่อ"""
    uid = event.get("source", {}).get("userId")
    if not uid or event.get("source", {}).get("type", "user") != "user":
        return None   # ในกลุ่ม/ห้อง ห้ามตอบข้อมูลส่วนตัว
    text = event.get("message", {}).get("text") or ""
    if not detect_intents(text):
        return None
    cfg = await config()
    if not cfg["enabled"]:
        return None
    out = await compose(uid, text, cfg)
    if not out:
        return None
    code, _ = await line.reply(event["replyToken"], [out["message"]])
    if code != 200:
        return None
    if out["escalate"]:
        await _escalate(uid, out["escalate"], text)
    return out

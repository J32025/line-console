"""routes กลุ่ม billing — แยกจาก api/index.py"""
from _lib import line
from _lib import supa
from _lib.auth import current_admin
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
import base64
import datetime as dt
import re
import time
from fastapi import APIRouter
from _lib.core import (NOW, _EASYSLIP_RESERVE, _RECEIPT_POSTBACK, _REG_COLS, _REG_PRICES_DEFAULT, _REREG_TAG, _STATUS_CMD, _broadcast_begin, _broadcast_finish, _clean_str, _client_ip, _course_base, _easyslip_remaining, _enroll_automations, _flag_nonfriend_registrants, _gather_dict, _get_setting, _json_obj, _mark_registration_paid, _mark_registrations_paid_by_ids, _norm_course, _normalize_messages, _oa_add_friend_url, _pay_account_for, _rate_limit_db, _reconcile_data, _reg_courses, _reg_payment_accounts_public, _reprocess_candidates, _reprocess_slips, _require_slip_tools_role, _retag_from_registrations, _set_rereg_flag, _triage_candidates, _triage_slips, _user_tags, _verify_member_token, alert_admin)

router = APIRouter()


@router.get("/api/slips/maintenance")
async def slips_maintenance(admin=Depends(current_admin)):
    """จำนวนสลิปที่เครื่องมือตรวจซ้ำ/คัดแยกจะทำได้ (นับเฉย ๆ ไม่เรียก EasySlip/Gemini ไม่เสียโควต้า)"""
    c = await _reprocess_candidates()
    tri = await _triage_candidates()
    return {"never_processed": len(c["never_processed"]), "quota_retry": len(c["quota_retry"]),
            "rematch_offline": len(c["rematch"]), "no_media": c["no_media"],
            "triage_candidates": len(tri),
            "easyslip_remaining": await _easyslip_remaining(), "easyslip_reserve": _EASYSLIP_RESERVE}


@router.post("/api/slips/reprocess")
async def slips_reprocess_admin(req: Request, admin=Depends(current_admin)):
    """ตรวจซ้ำสลิปที่ค้าง (เงียบ ไม่ส่งข้อความหาลูกค้า) — หน้าเว็บเรียกวนเป็นชุดละ ~25 ใบ"""
    _require_slip_tools_role(admin)
    b = {}
    try:
        b = await req.json()
    except Exception:
        pass
    limit = max(1, min(int(b.get("limit") or 25), 30))
    res = await _reprocess_slips(True, limit, offline=bool(b.get("offline", True)))
    await supa.log_operation(admin["userId"], "slips.reprocess", {"limit": limit},
                             {k: v for k, v in res.items() if k != "items"})
    return res


@router.post("/api/slips/triage")
async def slips_triage_admin(req: Request, admin=Depends(current_admin)):
    """คัดแยกรูปที่ไม่ใช่สลิปออกจากที่ EasySlip อ่านไม่ได้ (เงียบ ย้อนได้) — ชุดละ ~8 ใบ (เว้นจังหวะเรียก Gemini ~4.5 วิ/ใบ)"""
    _require_slip_tools_role(admin)
    b = {}
    try:
        b = await req.json()
    except Exception:
        pass
    limit = max(1, min(int(b.get("limit") or 8), 8))
    offset = max(0, int(b.get("offset") or 0))
    res = await _triage_slips(True, limit, offset)
    await supa.log_operation(admin["userId"], "slips.triage", {"limit": limit, "offset": offset},
                             {k: v for k, v in res.items() if k != "items"})
    return res


@router.post("/api/registrations/retag")
async def registrations_retag(admin=Depends(current_admin)):
    res = await _retag_from_registrations()
    await supa.log_operation(admin["userId"], "registrations.retag", None, res)
    return {"ok": True, **res}


# SLIPS (สลิปโอนเงิน) + SETTINGS
@router.get("/api/slips")
async def list_slips(admin=Depends(current_admin), status: str = "", limit: int = 100):
    params = {"select": "*", "order": "created_at.desc", "limit": str(min(limit, 300))}
    if status:
        params["status"] = f"eq.{status}"
    slips = await supa.select("slips", params=params)
    # แนบชื่อ user
    uids = list({s["line_user_id"] for s in slips})
    names = {}
    if uids:
        for r in await supa.select("line_users", params={
            "select": "line_user_id,display_name,picture_url",
            "line_user_id": f"in.({','.join(uids)})", "limit": "500"}):
            names[r["line_user_id"]] = r
    for s in slips:
        s["user"] = names.get(s["line_user_id"], {})
    new_count = await supa.count("slips", {"status": "eq.new"})
    return {"slips": slips, "new_count": new_count}


@router.post("/api/slips/{sid}")
async def update_slip(sid: int, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    patch = {k: b[k] for k in ("status", "note", "amount") if k in b}
    if b.get("status") in ("verified", "rejected"):
        patch["reviewed_by"] = admin["userId"]
        patch["reviewed_at"] = NOW()
    await supa.update("slips", patch, {"id": f"eq.{sid}"})
    row = None
    if b.get("replyUser") or b.get("status") == "verified":
        r = await supa.select("slips", params={
            "id": f"eq.{sid}", "select": "line_user_id,expected_course,amount,bank,ref,slip_date", "limit": "1"})
        row = r[0] if r else None
    # ตอบ user ถ้าขอ (ไม่มี reply token ให้ใช้ในจังหวะนี้ — มาจากปุ่มในคอนโซล ไม่ใช่ event จาก LINE — จึงต้อง push)
    # แนบปุ่ม "ดูใบเสร็จ" แทนการ push ใบเสร็จแยกอีกฉบับ (ลดจำนวนข้อความ push ลง 1 ฉบับ/ครั้ง)
    if b.get("replyUser") and row:
        msg = {"type": "text", "text": b.get("replyText") or
               ("✅ ตรวจสอบสลิปเรียบร้อยแล้ว\n\nสถานะ: 🟢 โอนเงินเรียบร้อยแล้ว รอติวตามเวลาที่กำหนด\nขอบคุณครับ 🙏"
                if b["status"] == "verified" else
                "สลิปที่ส่งมายังตรวจสอบไม่ผ่าน รบกวนส่งใหม่หรือติดต่อแอดมินครับ 🙏")}
        if b["status"] == "verified" and not b.get("replyText") and await _get_setting("send_receipt", True) is not False:
            msg["quickReply"] = {"items": [{"type": "action", "action": {
                "type": "postback", "label": "📄 ดูใบเสร็จ", "data": _RECEIPT_POSTBACK, "displayText": "ขอดูใบเสร็จ"}}]}
        await line.push(row["line_user_id"], [msg])
    # เข้า automation trigger=slip_verified (แอดมินกดผ่านเอง)
    if b.get("status") == "verified" and row:
        try:
            await _enroll_automations("slip_verified", [row["line_user_id"]],
                                      {"course": row.get("expected_course")})
            await _mark_registration_paid(row["line_user_id"], row.get("expected_course"))
        except Exception as e:
            print("slip_verified enroll error:", e)
    return {"ok": True}


@router.get("/api/payment-accounts")
async def list_pay_accounts(admin=Depends(current_admin)):
    return {"accounts": await supa.select("payment_accounts", params={"select": "*", "order": "course"})}


@router.post("/api/payment-accounts")
async def save_pay_account(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    row = {k: b[k] for k in ("course", "bank", "account_no", "account_name", "price", "full_price", "active") if k in b}
    if b.get("id"):
        await supa.update("payment_accounts", row, {"id": f"eq.{b['id']}"})
    else:
        await supa.insert("payment_accounts", row)
    return {"ok": True}


@router.delete("/api/payment-accounts/{aid}")
async def del_pay_account(aid: int, admin=Depends(current_admin)):
    await supa.delete("payment_accounts", {"id": f"eq.{aid}"})
    return {"ok": True}


@router.post("/api/public/reg-check")
async def public_reg_check(req: Request):
    """หน้าลงทะเบียนสมาชิกเรียก: ตรวจว่า userId นี้มีในทะเบียนแล้วหรือยัง + เป็นเพื่อนกับบัญชีแล้วหรือยัง
    - ไม่ได้เป็นเพื่อน -> isFriend=false (หน้าเว็บให้กดเพิ่มเพื่อนก่อน)
    - เคยลงทะเบียนไว้แต่ไม่ได้เป็นเพื่อน -> ติดธง needsRereg (registered=false) ให้ลงทะเบียนใหม่หลังเพิ่มเพื่อน"""
    await _rate_limit_db(f"regchk:{_client_ip(req)}", 60, 60)  # ก่อนเรียก LINE verify (คำขอภายนอก)
    b = await _json_obj(req)
    u = await _verify_member_token(b.get("idToken"))
    if not u:
        raise HTTPException(401, "ยืนยันตัวตน LINE ไม่สำเร็จ")
    uid = u["userId"]
    regs = await supa.select("registrations", params={
        "line_user_id": f"eq.{uid}",
        "select": "id,course,course_raw,paid,name,tel,org,email,approved,created_at",
        "order": "created_at.desc"})
    is_friend = (await line.is_friend(uid)) is not False   # เช็คไม่ได้ (None) = ไม่บล็อก
    needs_rereg = False
    if regs:
        flagged = _REREG_TAG in (await _user_tags(uid) or [])
        if not is_friend and not flagged:
            # ลงทะเบียนไว้แล้วแต่ตอนนี้ไม่ได้เป็นเพื่อน -> ติดธงให้ลงทะเบียนใหม่ (เก็บแถวเดิม/สถานะชำระไว้ ไม่ลบ)
            try:
                await _set_rereg_flag(uid, True)
                flagged = True
            except Exception as e:
                print("reg-check rereg flag error:", e)
        needs_rereg = flagged
    old = regs[0] if (regs and needs_rereg) else None
    return {
        "registered": bool(regs) and not needs_rereg,
        "isFriend": is_friend, "needsRereg": needs_rereg,
        "addFriendUrl": await _oa_add_friend_url(),
        "prefill": ({"name": old.get("name"), "tel": old.get("tel"), "org": old.get("org"),
                     "email": old.get("email"), "course": old.get("course")} if old else None),
        "userId": uid, "displayName": u.get("name"), "picture": u.get("picture"),
        "registrations": regs,
        "courses": await _reg_courses(),
        "paymentAccounts": await _reg_payment_accounts_public(),
        "nextUrl": await _get_setting("reg_next_url", ""),
    }


@router.post("/api/public/reg-submit")
async def public_reg_submit(req: Request):
    """หน้าลงทะเบียนสมาชิกส่งฟอร์ม -> upsert registration + อัปโหลดรูป (ถ้ามี) + สลับ rich menu
    ตามคอร์ส (ถ้าตั้ง setting reg_richmenu_map ไว้) + tag user + แจ้งแอดมิน"""
    b = await _json_obj(req)
    u = await _verify_member_token(b.get("idToken"))
    if not u:
        raise HTTPException(401, "ยืนยันตัวตน LINE ไม่สำเร็จ")
    name = (b.get("name") or "").strip()
    tel = (b.get("tel") or "").strip()
    course_raw = (b.get("course") or "").strip()
    course = _norm_course(course_raw)
    if not name or not tel or not course:
        raise HTTPException(400, "กรอก ชื่อ-นามสกุล / เบอร์โทร / หลักสูตร ให้ครบ")
    await _rate_limit_db(f"reg:{u['userId']}", 6, 300)
    await _rate_limit_db(f"regip:{_client_ip(req)}", 30, 300)  # กันคนเดียวหลายบัญชี LINE ยิงรัวจาก IP เดียว

    # ต้องเป็นเพื่อนกับบัญชีก่อน — ไม่งั้นส่งข้อความ/สลับ Rich Menu ให้ไม่ได้เลย (LINE ไม่อนุญาต)
    # เช็คไม่ได้ (None) ไม่บล็อก; หน้าเว็บเช็คไว้แล้วตอน reg-check นี่คือกันซ้ำเผื่อยิงตรง/เปิดฟอร์มค้างไว้
    friend = await line.is_friend(u["userId"])
    if friend is False:
        raise HTTPException(400, "กรุณาเพิ่มเพื่อนบัญชี น้องพัสดุ ก่อน แล้วกลับมาลงทะเบียนใหม่ "
                                 "(ถ้าเคยบล็อกไว้ ให้ปลดบล็อกก่อน)")

    # ระบบรองรับคนละ 1 หลักสูตรเท่านั้น — ถ้าเคยลงทะเบียนไปแล้ว (คอร์สไหนก็ตาม) ปฏิเสธทันที
    # กันซ้ำแม้ฝั่ง UI จะพยายามพาไปหน้าฟอร์มอีกรอบก็ตาม (เผื่อ token เก่า/เปิดฟอร์มค้างไว้)
    # ข้อยกเว้น: คนที่ติดธง "ต้องลงทะเบียนใหม่" (เคยลงไว้ตอนยังไม่เป็นเพื่อน) และตอนนี้เป็นเพื่อนแล้ว
    # -> อัปเดตทับแถวเดิม (ไม่สร้างแถวที่สอง ไม่แตะสถานะชำระเงิน/อนุมัติ)
    existing = await supa.select("registrations", params={
        "line_user_id": f"eq.{u['userId']}", "select": "id,course,paid",
        "order": "paid.desc,created_at.desc"})
    rereg_row = None
    if existing:
        if _REREG_TAG not in (await _user_tags(u["userId"]) or []):
            raise HTTPException(400, f"คุณลงทะเบียนหลักสูตร {existing[0]['course']} ไปแล้ว ระบบรองรับคนละ 1 หลักสูตรเท่านั้น")
        rereg_row = existing[0]
        if rereg_row.get("paid") and _norm_course(rereg_row["course"]) != course:
            raise HTTPException(400, f"คุณชำระเงินหลักสูตร {rereg_row['course']} ไว้แล้ว "
                                     "ไม่สามารถเปลี่ยนหลักสูตรได้ — กรุณาเลือกหลักสูตรเดิม")

    # อัปโหลดรูป (ถ้าแนบมา) — เก็บลง Storage แทนการฝาก base64 ไว้ในแถวข้อมูล
    photo_url = None
    if b.get("photoBase64"):
        try:
            raw = base64.b64decode(b["photoBase64"])
            if len(raw) > 8 * 1024 * 1024:
                raise HTTPException(400, "ไฟล์รูปใหญ่เกิน 8MB")
            mime = b.get("photoMime") or "image/jpeg"
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "jpg")
            path = f"registrations/{u['userId']}-{int(time.time())}.{ext}"
            photo_url = await supa.storage_upload("media", path, raw, mime)
        except HTTPException:
            raise
        except Exception as e:
            print("reg-submit photo upload error:", e)

    row = {"line_user_id": u["userId"], "course": course, "course_raw": course_raw,
           "name": name, "tel": tel, "org": (b.get("org") or "").strip() or None,
           "email": (b.get("email") or "").strip() or None,
           "passed": (b.get("examOrder") or "").strip() or None,
           "source": "liff", "updated_at": NOW()}
    if photo_url:
        row["slip_url"] = photo_url
    if rereg_row:
        try:
            await supa.update("registrations", row, {"id": f"eq.{rereg_row['id']}"})
        except Exception as e:
            print("reg-submit rereg update error:", e)
            raise HTTPException(400, "บันทึกไม่สำเร็จ (อาจมีข้อมูลหลักสูตรนี้อยู่แล้ว) — กรุณาติดต่อแอดมิน")
    else:
        await supa.upsert("registrations", row, on_conflict="line_user_id,course")
    try:
        ex = await supa.select("line_users", params={
            "select": "tags", "line_user_id": f"eq.{u['userId']}", "limit": "1"})
        cur = set((ex[0].get("tags") if ex else []) or [])
        new = (cur | {"ลงทะเบียน", course}) - {_REREG_TAG}   # ลงทะเบียนใหม่สำเร็จ -> ถอดธง
        patch = {"line_user_id": u["userId"], "tags": sorted(new), "updated_at": NOW()}
        if friend is True:
            patch["is_following"] = True    # ยืนยันกับ LINE แล้วว่าเป็นเพื่อน
        if not ex:
            patch.update({"source": "registration", "is_following": friend is not False,
                          "display_name": _clean_str(u.get("name"))})
        if new != cur or not ex or friend is True:
            await supa.upsert("line_users", [patch], on_conflict="line_user_id")
    except Exception as e:
        print("reg-submit tag error:", e)

    # สลับ rich menu ตามคอร์ส (ถ้าตั้ง mapping ไว้ใน Admins) — ปิดเงียบถ้าไม่ได้ตั้ง/ล้มเหลว
    try:
        rmap = await _get_setting("reg_richmenu_map", None) or {}
        target_rid = rmap.get(course)
        if target_rid:
            await line.user_richmenu_link(u["userId"], target_rid)
    except Exception as e:
        print("reg-submit richmenu switch error:", e)

    await alert_admin("📝 ลงทะเบียนใหม่ (LIFF)" if not rereg_row else "🔁 ลงทะเบียนใหม่ (เพิ่มเพื่อนแล้ว)",
                      f"{name}\nหลักสูตร {course} · {b.get('org') or '-'}\nโทร {tel}",
                      throttle_key=f"reg_{u['userId']}_{course}")

    # ไม่ push แจ้งสถานะอัตโนมัติอีกต่อไป (ประหยัดโควต้า) — หน้า LIFF เองแจ้งผลสำเร็จอยู่แล้ว
    # ยอด/บัญชีที่ต้องโอนดูได้จาก response นี้ (payment) ให้หน้าเว็บแสดงเลย และแจ้งให้พิมพ์ /ตรวจข้อมูล ดูซ้ำได้ทุกเมื่อ
    acc = await _pay_account_for(course)
    return {"ok": True, "course": course, "nextUrl": await _get_setting("reg_next_url", ""),
            "payment": acc, "statusCmd": _STATUS_CMD}


@router.get("/api/registrations/nonfriends")
async def registrations_nonfriends(admin=Depends(current_admin)):
    """รายชื่อคนที่ลงทะเบียนแล้วแต่ไม่ได้เป็นเพื่อนกับบัญชี (เช็คกับ LINE จริง) — ยังไม่เปลี่ยนแปลงอะไร"""
    return await _flag_nonfriend_registrants(False, detail=True)


@router.post("/api/registrations/nonfriends/flag")
async def registrations_nonfriends_flag(admin=Depends(current_admin)):
    """ติดธง "ต้องลงทะเบียนใหม่" ให้คนกลุ่มนั้นทั้งหมด — พอเปิดหน้าลงทะเบียนจะเจอหน้าให้เพิ่มเพื่อนก่อน แล้วลงทะเบียนใหม่"""
    res = await _flag_nonfriend_registrants(True, detail=True)
    await supa.log_operation(admin["userId"], "registrations.flag_nonfriends", None,
                             {k: v for k, v in res.items() if k != "items"})
    return res


@router.post("/api/registrations/import")
async def registrations_import(req: Request, admin=Depends(current_admin)):
    """วางข้อความ TSV จากฟอร์มลงทะเบียน -> upsert registrations + tag line_users ตามคอร์ส"""
    b = await req.json()
    text = b.get("text") or ""
    tag_users = b.get("tagUsers", True)
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if len(lines) < 2:
        raise HTTPException(400, "ไม่พบข้อมูล (วางทั้งหัวตารางและแถวข้อมูล)")

    header = [h.strip().lower() for h in lines[0].split("\t")]
    idx = {}
    for i, h in enumerate(header):
        for key, col in _REG_COLS.items():
            if h == key or h == key.lower():
                idx[col] = i
    if "line_user_id" not in idx:
        raise HTTPException(400, "ไม่พบคอลัมน์ UID ในหัวตาราง")
    # หา col "จ่าย" แยก (ชื่อซ้ำกับ substring)
    paid_i = next((i for i, h in enumerate(header) if h in ("จ่าย", "จ่ายแล้ว")), None)
    status_i = next((i for i, h in enumerate(header) if h == "status"), None)

    regs, seen = [], set()
    for ln in lines[1:]:
        f = ln.split("\t")
        uid = (f[idx["line_user_id"]].strip() if idx["line_user_id"] < len(f) else "")
        if not re.fullmatch(r"U[0-9a-f]{32}", uid):
            continue
        course_raw = (f[idx["course_raw"]].strip() if "course_raw" in idx and idx["course_raw"] < len(f) else "")
        course = _norm_course(course_raw)
        k = (uid, course)
        if k in seen:
            continue
        seen.add(k)
        row = {"line_user_id": uid, "course": course, "course_raw": course_raw, "source": "import",
               "updated_at": NOW()}
        for col, i in idx.items():
            if col in ("line_user_id", "course_raw"):
                continue
            row[col] = (f[i].strip() if i < len(f) else "") or None
        if paid_i is not None and paid_i < len(f):
            row["paid"] = "จ่าย" in (f[paid_i] or "")
        if status_i is not None and status_i < len(f):
            st = (f[status_i] or "").strip()
            row["approved"] = True if st in ("อนุมัติ", "ผ่าน") else (False if st == "ไม่อนุมัติ" else None)
        regs.append(row)

    if not regs:
        raise HTTPException(400, "ไม่พบแถวที่มี UID ถูกต้อง (U + 32 hex)")
    if len(regs) > 2000:
        raise HTTPException(400, "เกิน 2000 แถว/ครั้ง — แบ่งไฟล์เป็นหลายส่วน")

    # 1) upsert registrations (สำคัญสุด)
    for i in range(0, len(regs), 200):
        await supa.upsert("registrations", regs[i:i + 200], on_conflict="line_user_id,course")

    # 2) tag line_users — best effort, chunk เล็ก (URL in.() ยาวไป PostgREST ปฏิเสธ)
    users_touched, tag_err = 0, None
    if tag_users:
        by_uid: dict[str, dict] = {}
        for rr in regs:
            u = by_uid.setdefault(rr["line_user_id"], {"courses": set(), "paid": False})
            if rr.get("course"):
                u["courses"].add(rr["course"])
            if rr.get("paid"):
                u["paid"] = True
        uids = list(by_uid.keys())
        for i in range(0, len(uids), 80):
            chunk = uids[i:i + 80]
            try:
                existing = {x["line_user_id"]: x for x in await supa.select("line_users", params={
                    "select": "line_user_id,tags", "line_user_id": f"in.({','.join(chunk)})", "limit": "200"})}
                patch = []
                for uid in chunk:
                    info = by_uid[uid]
                    cur = set((existing.get(uid) or {}).get("tags") or [])
                    new = set(cur) | {"ลงทะเบียน"} | info["courses"]
                    if info["paid"]:
                        new.add("จ่ายแล้ว")
                    row = {"line_user_id": uid, "tags": sorted(new), "updated_at": NOW()}
                    if uid not in existing:
                        row["source"] = "registration"
                        row["is_following"] = True
                    if new != cur or uid not in existing:
                        patch.append(row)
                if patch:
                    await supa.upsert("line_users", patch, on_conflict="line_user_id")
                    users_touched += len(patch)
            except Exception as e:
                tag_err = str(e)[:120]

    from collections import Counter
    by_course = dict(Counter(r.get("course") or "?" for r in regs))
    try:
        await supa.log_operation(admin["userId"], "registrations.import",
                                 {"parsed": len(lines) - 1}, {"valid": len(regs), "users": users_touched})
    except Exception:
        pass
    return {"parsed": len(lines) - 1, "valid": len(regs), "by_course": by_course,
            "paid": sum(1 for r in regs if r.get("paid")), "users_tagged": users_touched,
            "tag_error": tag_err}


@router.get("/api/registrations")
async def registrations_list(admin=Depends(current_admin), course: str = "", paid: str = "",
                             q: str = "", limit: int = 100, offset: int = 0):
    params = {"select": "*", "order": "created_at.desc",
              "limit": str(min(limit, 500)), "offset": str(max(offset, 0))}
    if course:
        params["course"] = f"eq.{course}"
    if paid in ("true", "false"):
        params["paid"] = f"eq.{paid}"
    if q:
        params["or"] = f"(name.ilike.*{q}*,tel.ilike.*{q}*,email.ilike.*{q}*,org.ilike.*{q}*,line_user_id.ilike.*{q}*)"
    rows = await supa.select("registrations", params=params)
    cnt_params = {k: v for k, v in params.items() if k in ("course", "paid", "or")}
    total = await supa.count("registrations", cnt_params)
    return {"registrations": rows, "total": total, "limit": limit, "offset": offset}


# TASKS (งาน / ติดตาม)
@router.get("/api/tasks")
async def tasks_list(admin=Depends(current_admin), status: str = "open", assignee: str = "",
                     uid: str = "", overdue: int = 0, limit: int = 200):
    params = {"select": "*", "order": "due_at.asc.nullslast,created_at.desc",
              "limit": str(min(limit, 500))}
    if status and status != "all":
        params["status"] = f"eq.{status}"
    if assignee == "me":
        params["assigned_to"] = f"eq.{admin['userId']}"
    elif assignee:
        params["assigned_to"] = f"eq.{assignee}"
    if uid:
        params["line_user_id"] = f"eq.{uid}"
    if overdue:
        params["due_at"] = f"lt.{NOW()}"
        params["status"] = "eq.open"
    try:
        rows = await supa.select("tasks", params=params)
    except Exception:
        return {"tasks": [], "schema_missing": True,
                "hint": "ยังไม่ได้สร้างตาราง tasks — รัน migration 0008 ใน Supabase SQL Editor"}
    uids = list({r["line_user_id"] for r in rows if r.get("line_user_id")})
    names = {}
    if uids:
        for i in range(0, len(uids), 80):
            for u in await supa.select("line_users", params={
                    "select": "line_user_id,display_name,picture_url",
                    "line_user_id": f"in.({','.join(uids[i:i+80])})", "limit": "200"}):
                names[u["line_user_id"]] = u
    for r in rows:
        r["user"] = names.get(r.get("line_user_id"))
    return {"tasks": rows}


@router.get("/api/tasks/summary")
async def tasks_summary(admin=Depends(current_admin)):
    now = NOW()
    today0 = dt.date.today().isoformat()
    c = await _gather_dict(
        open=supa.count("tasks", {"status": "eq.open"}),
        overdue=supa.count("tasks", {"status": "eq.open", "due_at": f"lt.{now}"}),
        mine=supa.count("tasks", {"status": "eq.open", "assigned_to": f"eq.{admin['userId']}"}),
        done_today=supa.count("tasks", {"status": "eq.done", "done_at": f"gte.{today0}"}),
    )
    return c


@router.post("/api/tasks")
async def task_create(req: Request, admin=Depends(current_admin)):
    b = await req.json()
    title = (b.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "ต้องมีชื่องาน")
    row = {"title": title, "detail": b.get("detail"), "line_user_id": b.get("lineUserId") or b.get("line_user_id"),
           "due_at": b.get("dueAt") or b.get("due_at"), "priority": b.get("priority", "normal"),
           "assigned_to": b.get("assignedTo") or b.get("assigned_to") or admin["userId"],
           "tag": b.get("tag"), "created_by": admin["userId"]}
    r = await supa.insert("tasks", row)
    return {"ok": True, "task": r[0] if r else None}


@router.post("/api/tasks/bulk")
async def tasks_bulk(req: Request, admin=Depends(current_admin)):
    """สร้างงานหลายชิ้นจากรายชื่อ userId (เช่น 'ตามจ่าย' จากหน้ากระทบยอด)"""
    b = await req.json()
    title = (b.get("title") or "").strip()
    uids = [u.strip() for u in b.get("userIds", []) if u.strip()]
    if not title or not uids:
        raise HTTPException(400, "ต้องมีชื่องาน + รายชื่อ")
    rows = [{"title": title, "line_user_id": u, "detail": b.get("detail"),
             "due_at": b.get("dueAt"), "tag": b.get("tag"), "priority": b.get("priority", "normal"),
             "assigned_to": b.get("assignedTo") or admin["userId"], "created_by": admin["userId"]}
            for u in uids]
    for i in range(0, len(rows), 200):
        await supa.insert("tasks", rows[i:i + 200])
    await supa.log_operation(admin["userId"], "tasks.bulk", {"count": len(rows), "title": title}, None)
    return {"ok": True, "created": len(rows)}


@router.patch("/api/tasks/{tid}")
async def task_update(tid: int, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    patch = {k: b[k] for k in ("title", "detail", "due_at", "priority", "assigned_to", "tag", "status") if k in b}
    for camel, snake in (("dueAt", "due_at"), ("assignedTo", "assigned_to")):
        if camel in b:
            patch[snake] = b[camel]
    if b.get("status") == "done":
        patch["done_at"] = NOW()
    patch["updated_at"] = NOW()
    await supa.update("tasks", patch, {"id": f"eq.{tid}"})
    return {"ok": True}


@router.delete("/api/tasks/{tid}")
async def task_delete(tid: int, admin=Depends(current_admin)):
    await supa.delete("tasks", {"id": f"eq.{tid}"})
    return {"ok": True}


@router.get("/api/reconcile")
async def reconcile(admin=Depends(current_admin)):
    return await _reconcile_data()


@router.get("/api/reports/revenue")
async def report_revenue(admin=Depends(current_admin), frm: str = "", to: str = "",
                         group: str = "course", format: str = ""):
    """รายงานรายได้จากสลิปที่ verified — group: course | bank | day | month"""
    params = {"select": "amount,bank,expected_course,status,reviewed_at,created_at,slip_date",
              "status": "eq.verified"}
    slips = await supa.select_all("slips", params=params)
    fromd = frm or "0000"
    tod = to or "9999"

    def _d(s):
        return (s.get("reviewed_at") or s.get("slip_date") or s.get("created_at") or "")[:10]

    rows: dict[str, dict] = {}
    total = 0.0
    for s in slips:
        d = _d(s)
        if not (fromd <= d <= tod):
            continue
        amt = float(s.get("amount") or 0)
        total += amt
        if group == "bank":
            k = s.get("bank") or "ไม่ระบุ"
        elif group == "day":
            k = d
        elif group == "month":
            k = d[:7]
        else:
            k = s.get("expected_course") or "ไม่ระบุ"
        g = rows.setdefault(k, {"key": k, "count": 0, "amount": 0.0})
        g["count"] += 1
        g["amount"] += amt
    out = sorted(rows.values(), key=lambda x: (x["key"] if group in ("day", "month") else -x["amount"]))
    for r in out:
        r["amount"] = round(r["amount"])

    if format == "csv":
        lines = ["key,count,amount"] + [f'"{r["key"]}",{r["count"]},{r["amount"]}' for r in out]
        lines.append(f'"รวม",{sum(r["count"] for r in out)},{round(total)}')
        from fastapi.responses import Response
        return Response("﻿" + "\r\n".join(lines), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="revenue-{group}-{dt.date.today()}.csv"'})
    return {"group": group, "from": frm, "to": to, "rows": out,
            "total": round(total), "count": sum(r["count"] for r in out)}


@router.post("/api/reconcile/mark-paid")
async def reconcile_mark_paid(req: Request, admin=Depends(current_admin)):
    """mark registrations เป็นจ่ายแล้วเป็นชุด (จาก paid_not_marked)"""
    b = await req.json()
    ids = [int(x) for x in b.get("ids", []) if str(x).isdigit()]
    if not ids:
        raise HTTPException(400, "ไม่มี id")
    marked = await _mark_registrations_paid_by_ids(ids)
    await supa.log_operation(admin["userId"], "reconcile.mark_paid", {"count": marked}, None)
    return {"ok": True, "marked": marked}


@router.get("/api/registrations/summary")
async def registrations_summary(admin=Depends(current_admin)):
    rows = await supa.select_all("registrations", params={"select": "course,paid,approved,line_user_id"})
    courses: dict[str, dict] = {}
    for r in rows:
        c = r.get("course") or "?"
        d = courses.setdefault(c, {"course": c, "count": 0, "paid": 0, "unpaid": 0})
        d["count"] += 1
        if r.get("paid"):
            d["paid"] += 1
        else:
            d["unpaid"] += 1

    # ---- สรุปรายได้ตามหลักสูตรฐาน (FC/IC/PC ฯลฯ) — ราคาปรับได้ผ่าน setting reg_course_prices ----
    prices = await _get_setting("reg_course_prices", None) or _REG_PRICES_DEFAULT
    base_paid: dict[str, int] = {}
    for r in rows:
        if not r.get("paid"):
            continue
        base = _course_base(r.get("course") or "?")
        base_paid[base] = base_paid.get(base, 0) + 1

    rev_by_course, other = [], []
    total_revenue = 0
    for base, cnt in sorted(base_paid.items(), key=lambda x: -x[1]):
        if base in prices:
            price = prices[base]
            revenue = cnt * price
            total_revenue += revenue
            rev_by_course.append({"course": base, "paid": cnt, "price": price, "revenue": revenue})
        else:
            other.append({"course": base, "paid": cnt})

    return {
        "total": len(rows),
        "paid": sum(1 for r in rows if r.get("paid")),
        "people": len({r["line_user_id"] for r in rows if r.get("line_user_id")}),
        "by_course": sorted(courses.values(), key=lambda x: -x["count"]),
        "revenue": {
            "prices": prices,
            "by_course": rev_by_course,
            "total_revenue": total_revenue,
            "total_paid_counted": sum(c["paid"] for c in rev_by_course),
            "other": other,
            "other_paid": sum(o["paid"] for o in other),
        },
    }


@router.get("/api/registrations/{rid}")
async def registration_detail(rid: int, admin=Depends(current_admin)):
    rows = await supa.select("registrations", params={"id": f"eq.{rid}", "select": "*", "limit": "1"})
    if not rows:
        raise HTTPException(404, "ไม่พบ")
    reg = rows[0]
    uid = reg.get("line_user_id")
    user, slips_rows, other_regs = None, [], []
    if uid:
        u = await supa.select("line_users", params={
            "select": "line_user_id,display_name,picture_url,is_following,tags,last_message_at",
            "line_user_id": f"eq.{uid}", "limit": "1"})
        user = u[0] if u else None
        slips_rows = await supa.select("slips", params={
            "select": "id,status,amount,expected_course,created_at,media_url", "line_user_id": f"eq.{uid}",
            "order": "created_at.desc", "limit": "10"})
        other_regs = await supa.select("registrations", params={
            "select": "id,course,paid,created_at", "line_user_id": f"eq.{uid}",
            "id": f"neq.{rid}", "limit": "10"})
    return {"registration": reg, "user": user, "slips": slips_rows, "other_registrations": other_regs}


@router.patch("/api/registrations/{rid}")
async def registration_update(rid: int, req: Request, admin=Depends(current_admin)):
    b = await req.json()
    patch = {k: b[k] for k in ("paid", "approved", "note") if k in b}
    # ข้อมูลผู้ลงทะเบียน: ล้างอักขระควบคุม ตัดช่องว่าง ค่าว่าง = ล้างข้อมูลช่องนั้น
    for k, mx in (("name", 200), ("tel", 40), ("org", 300), ("email", 200), ("job", 200)):
        if k in b:
            v = _clean_str(str(b[k] or "").strip())
            patch[k] = v[:mx] if v else None
    if patch.get("email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", patch["email"]):
        raise HTTPException(400, "รูปแบบอีเมลไม่ถูกต้อง")
    if "course" in b:
        # แก้หลักสูตร: เก็บข้อความที่กรอกใน course_raw และคำนวณรหัสมาตรฐาน (FC70 / PC70-1 ...) ให้เอง
        raw = (_clean_str(str(b["course"] or "").strip()) or "")[:100]
        course = _norm_course(raw)
        if not course:
            raise HTTPException(400, "กรุณาระบุหลักสูตร")
        cur = await supa.select("registrations", params={"id": f"eq.{rid}", "select": "line_user_id,course", "limit": "1"})
        if not cur:
            raise HTTPException(404, "ไม่พบ")
        if cur[0].get("line_user_id") and course != cur[0].get("course"):
            dup = await supa.select("registrations", params={
                "line_user_id": f"eq.{cur[0]['line_user_id']}", "course": f"eq.{course}", "id": f"neq.{rid}",
                "select": "id", "limit": "1"})
            if dup:
                raise HTTPException(409, f"คนนี้ลงทะเบียนหลักสูตร {course} ไว้แล้ว (แถวอื่น) — แก้ซ้ำไม่ได้")
        patch["course"], patch["course_raw"] = course, raw
    patch["updated_at"] = NOW()
    await supa.update("registrations", patch, {"id": f"eq.{rid}"})
    if "course" in patch:
        await _retag_from_registrations()  # ติด tag หลักสูตรใหม่ให้ line_users
    # sync tag จ่ายแล้ว
    if b.get("paid") is True:
        r = await supa.select("registrations", params={"id": f"eq.{rid}", "select": "line_user_id", "limit": "1"})
        if r and r[0].get("line_user_id"):
            u = await supa.select("line_users", params={
                "select": "tags", "line_user_id": f"eq.{r[0]['line_user_id']}", "limit": "1"})
            cur = set((u[0].get("tags") if u else []) or [])
            if "จ่ายแล้ว" not in cur:
                await supa.update("line_users", {"tags": sorted(cur | {"จ่ายแล้ว"}), "updated_at": NOW()},
                                  {"line_user_id": f"eq.{r[0]['line_user_id']}"})
    return {"ok": True}


@router.post("/api/registrations/message")
async def registrations_message(req: Request, admin=Depends(current_admin)):
    """ส่งข้อความหาผู้ลงทะเบียนตาม filter (course / paid)"""
    b = await req.json()
    params = {"select": "line_user_id"}
    if b.get("course"):
        params["course"] = f"eq.{b['course']}"
    if b.get("paid") in ("true", "false", True, False):
        params["paid"] = f"eq.{str(b['paid']).lower()}"
    rows = await supa.select_all("registrations", params=params)
    uids = list({r["line_user_id"] for r in rows if r.get("line_user_id")})
    if not uids:
        raise HTTPException(400, "ไม่มีปลายทาง")
    msgs = _normalize_messages(b.get("messages", []))
    bid, msgs = await _broadcast_begin(admin["userId"], "multicast", msgs, len(uids))
    sent = failed = 0
    for i in range(0, len(uids), 500):
        code, _txt, _rid = await line.multicast(uids[i:i + 500], msgs)
        if code == 200:
            sent += len(uids[i:i + 500])
        else:
            failed += len(uids[i:i + 500])
    await _broadcast_finish(bid, status="sent" if failed == 0 else "failed")
    return {"ok": failed == 0, "target": len(uids), "sent": sent, "failed": failed}

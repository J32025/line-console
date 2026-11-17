"""ทะเบียนผู้ลงทะเบียนเรียน: ตรรกะที่ไม่ผูกกับ HTTP (แยกจาก core.py เพื่อให้เทสต์ได้)

- _norm_course / _course_base: แปลงข้อความหลักสูตรเป็นรหัสมาตรฐาน
- _reconcile_data: กระทบยอดทะเบียน vs สลิปที่ยืนยัน vs สถานะจ่าย
- diff_fields: หาว่าแก้อะไรบ้าง (ใช้บันทึกประวัติการแก้ไข)
- find_duplicate_groups: หาคนเดียวที่ลงทะเบียนด้วยหลายบัญชี LINE
- order_param: แปลงชื่อคอลัมน์ที่ผู้ใช้เลือกเรียงเป็นพารามิเตอร์ order ของ PostgREST (whitelist)
ห้าม import จาก core.py (core import ไฟล์นี้ — จะวนกัน)
"""
import re

from _lib import supa


# ---------------------------------------------------------------- หลักสูตร
def _norm_course(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    su = s.upper().replace(" ", "")
    base = next((c for c in ("FC", "IC", "PC", "AC") if su.startswith(c)), None)
    if not base:
        return s[:24]
    code = base + "70"
    if any(x in s for x in ("รุ่น 2", "รุ่น2", "รุ่น๒", "รุ่นที่2", "รุ่นที่ 2")):
        return code + "-2"
    if any(x in s for x in ("รุ่น 1", "รุ่น1", "รุ่น๑", "รุ่นที่1", "รุ่นที่ 1")):
        return code + "-1"
    return code


_REG_PRICES_DEFAULT = {"FC": 1499, "IC": 1999, "PC": 999}


def _course_base(course: str) -> str:
    """ตัดตัวเลข/รุ่นออก เหลือแค่รหัสหลักสูตรฐาน — FC70->FC, PC70-2->PC, VIP->VIP"""
    m = re.match(r"[A-Za-zก-๙]+", course or "")
    return (m.group(0).upper() if m else (course or "?"))


# ---------------------------------------------------------------- กระทบยอด
async def _reconcile_data() -> dict:
    """กระทบยอด: ทะเบียน vs สลิปที่ยืนยัน vs สถานะจ่าย"""
    regs = await supa.select_all("registrations", params={
        "select": "id,line_user_id,course,course_raw,name,tel,org,paid,created_at"})
    slips = await supa.select_all("slips", params={
        "select": "id,line_user_id,expected_course,amount,created_at", "status": "eq.verified"})
    accts = await supa.select("payment_accounts", params={"select": "course,price,full_price"})

    def _price(course):
        base = (course or "")[:2].upper()
        for a in accts:
            if str(a.get("course") or "").upper().startswith(base):
                return float(a.get("price") or 0)
        return 0.0

    slips_by_uid: dict[str, list] = {}
    for s in slips:
        slips_by_uid.setdefault(s["line_user_id"], []).append(s)

    def _slip_for(uid, course):
        base = (course or "")[:2].upper()
        for s in slips_by_uid.get(uid, []):
            if base and str(s.get("expected_course") or "").upper().startswith(base) and not s.get("_used"):
                return s
        return None

    course_map: dict[str, dict] = {}
    unpaid, paid_not_marked = [], []
    for r in regs:
        c = r.get("course") or "?"
        cm = course_map.setdefault(c, {"course": c, "registered": 0, "paid": 0,
                                       "slip_verified": 0, "revenue": 0.0, "unpaid": 0})
        cm["registered"] += 1
        s = _slip_for(r["line_user_id"], c)
        if s:
            s["_used"] = True
            cm["slip_verified"] += 1
            cm["revenue"] += float(s.get("amount") or 0)
        if r.get("paid"):
            cm["paid"] += 1
        else:
            cm["unpaid"] += 1
            item = {"id": r["id"], "line_user_id": r["line_user_id"], "name": r.get("name"),
                    "tel": r.get("tel"), "org": r.get("org"), "course": c}
            if s:
                item["slip_amount"] = s.get("amount")
                item["slip_date"] = s.get("created_at")
                paid_not_marked.append(item)
            else:
                unpaid.append(item)

    reg_keys = {(r["line_user_id"], (r.get("course") or "")[:2].upper()) for r in regs}
    slip_no_reg = []
    for s in slips:
        base = str(s.get("expected_course") or "").upper()[:2]
        if not base:
            slip_no_reg.append({"id": s["id"], "line_user_id": s["line_user_id"],
                                "amount": s.get("amount"), "created_at": s.get("created_at"),
                                "reason": "สลิปไม่ระบุคอร์ส"})
        elif (s["line_user_id"], base) not in reg_keys:
            slip_no_reg.append({"id": s["id"], "line_user_id": s["line_user_id"],
                                "amount": s.get("amount"), "created_at": s.get("created_at"),
                                "course": s.get("expected_course"), "reason": "ไม่มีทะเบียนคอร์สนี้"})

    # แนบชื่อ user ให้ slip_no_reg
    uids = list({x["line_user_id"] for x in slip_no_reg})
    if uids:
        for i in range(0, len(uids), 60):
            names = {u["line_user_id"]: u.get("display_name") for u in await supa.select("line_users", params={
                "select": "line_user_id,display_name", "line_user_id": f"in.({','.join(uids[i:i+60])})", "limit": "200"})}
            for x in slip_no_reg:
                if x["line_user_id"] in names:
                    x["name"] = names[x["line_user_id"]]

    for cm in course_map.values():
        cm["expected_revenue"] = round(_price(cm["course"]) * cm["registered"])
        cm["revenue"] = round(cm["revenue"])

    return {
        "by_course": sorted(course_map.values(), key=lambda x: -x["registered"]),
        "totals": {
            "registered": len(regs),
            "paid_marked": sum(1 for r in regs if r.get("paid")),
            "slip_verified": len(slips),
            "revenue": round(sum(float(s.get("amount") or 0) for s in slips)),
            "expected_revenue": round(sum(_price(r.get("course")) for r in regs)),
        },
        "issues": {
            "unpaid": unpaid[:300], "unpaid_count": len(unpaid),
            "paid_not_marked": paid_not_marked[:300], "paid_not_marked_count": len(paid_not_marked),
            "slip_no_reg": slip_no_reg[:300], "slip_no_reg_count": len(slip_no_reg),
        },
    }


# ---------------------------------------------------------------- ประวัติการแก้ไข
# ช่องที่ผู้ดูแลแก้ได้ผ่าน PATCH /api/registrations/{id} และจะถูกบันทึกลง operations (action = registration.update)
AUDITED_FIELDS = ("name", "tel", "email", "org", "job", "course", "course_raw", "paid", "approved", "note")


def diff_fields(old: dict, patch: dict, keys=AUDITED_FIELDS) -> dict:
    """คืน {ช่อง: {"from": ค่าเดิม, "to": ค่าใหม่}} เฉพาะช่องที่เปลี่ยนจริง (None กับ "" ถือว่าเท่ากัน)"""
    out = {}
    for k in keys:
        if k not in patch:
            continue
        a, b = old.get(k), patch.get(k)
        if (a in (None, "")) and (b in (None, "")):
            continue
        if a != b:
            out[k] = {"from": a, "to": b}
    return out


# ---------------------------------------------------------------- เรียงลำดับรายชื่อ
_SORTABLE = {"name", "course", "org", "tel", "paid", "created_at", "email"}


def order_param(sort: str = "", direction: str = "") -> str:
    """ค่า order ของ PostgREST จากคอลัมน์ที่เลือก (ไม่อยู่ใน whitelist = เรียงตามวันที่ลงทะเบียนล่าสุด)
    เสมอใส่ id เป็นตัวตัดสิน เพื่อให้หน้าถัดไป (offset) ไม่ซ้ำ/ตกหล่นเมื่อค่าที่เรียงเท่ากัน"""
    if sort not in _SORTABLE:
        return "created_at.desc,id.desc"
    d = "desc" if direction == "desc" else "asc"
    nulls = "nullslast"
    return f"{sort}.{d}.{nulls},id.{d}"


# ---------------------------------------------------------------- ตรวจข้อมูลซ้ำ
def norm_tel(tel) -> str | None:
    """เบอร์โทรเทียบกันได้: เหลือแต่ตัวเลข, +66/66 นำหน้า -> 0, ต้องยาว >= 9 หลัก ไม่งั้นถือว่าใช้เทียบไม่ได้"""
    d = re.sub(r"\D", "", str(tel or ""))
    if d.startswith("66") and len(d) >= 11:
        d = "0" + d[2:]
    return d if len(d) >= 9 else None


def norm_email(email) -> str | None:
    e = str(email or "").strip().lower()
    return e if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) else None


def find_duplicate_groups(regs: list[dict]) -> list[dict]:
    """จัดกลุ่มบัญชี LINE ที่น่าจะเป็นคนเดียวกัน: เบอร์โทรหรืออีเมลตรงกัน (เชื่อมต่อกันเป็นทอด เช่น A-B เบอร์เดียวกัน B-C อีเมลเดียวกัน)
    นับเฉพาะกลุ่มที่มี line_user_id ต่างกันตั้งแต่ 2 บัญชีขึ้นไป — คนเดียวกันลงหลายหลักสูตรด้วยบัญชีเดียวไม่ใช่ข้อมูลซ้ำ
    คืน [{"reasons": ["tel"|"email"], "members": [{line_user_id, name, regs:[{id,course,paid}]}], "conflict": bool}]
    conflict = มีหลักสูตรซ้ำกันข้ามบัญชี รวมบัญชีตรง ๆ ไม่ได้ (ชนดัชนี unique line_user_id+course)"""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    keys: dict[tuple[str, str], str] = {}      # (kind, value) -> uid แรกที่พบ
    uid_reasons: dict[str, set] = {}
    people: dict[str, dict] = {}
    for r in regs:
        uid = r.get("line_user_id")
        if not uid:
            continue
        find(uid)
        p = people.setdefault(uid, {"line_user_id": uid, "name": r.get("name"), "regs": []})
        p["name"] = p["name"] or r.get("name")
        p["regs"].append({"id": r.get("id"), "course": r.get("course"), "paid": bool(r.get("paid"))})
        for kind, val in (("tel", norm_tel(r.get("tel"))), ("email", norm_email(r.get("email")))):
            if not val:
                continue
            first = keys.setdefault((kind, val), uid)
            if first != uid:
                union(first, uid)
                uid_reasons.setdefault(first, set()).add(kind)
                uid_reasons.setdefault(uid, set()).add(kind)

    groups: dict[str, list[str]] = {}
    for uid in people:
        groups.setdefault(find(uid), []).append(uid)
    out = []
    for uids in groups.values():
        if len(uids) < 2:
            continue
        members = [people[u] for u in sorted(uids)]
        courses = [x["course"] for m in members for x in m["regs"] if x["course"]]
        out.append({
            "reasons": sorted(set().union(*(uid_reasons.get(u, set()) for u in uids))),
            "members": members,
            "conflict": len(courses) != len(set(courses)),
        })
    out.sort(key=lambda g: (-len(g["members"]), g["members"][0]["line_user_id"]))
    return out

# คู่มือลำดับขั้นตอนของ Webhook (line-console)

จุดรับ: `POST /api/webhook` — [api/_lib/routers/webhook.py](../api/_lib/routers/webhook.py)
ตัวจัดการย่อย: [api/_lib/core.py](../api/_lib/core.py)

> หลักใหญ่: webhook **ตอบ 200 `{"ok": true}` เสมอ** ยกเว้นลายเซ็นไม่ถูกต้อง (403)
> แต่ละขั้นครอบด้วย try/except — ขั้นใดพัง ขั้นถัดไปยังทำงานต่อ และบางขั้นแจ้งแอดมินทาง LINE (`alert_admin`)

---

## 1. ภาพรวม (ลำดับจริงในโค้ด)

```
LINE ──POST──▶ /api/webhook
  1  ตรวจลายเซ็น HMAC-SHA256            ── ไม่ผ่าน → 403 จบ
  2  แกะ events, ทิ้ง event ที่ LINE ส่งซ้ำ (isRedelivery)
  3  แสดง "กำลังพิมพ์…" 20 วินาที (message/postback จาก user)
  4  แยกประเภท event เตรียมข้อมูล (follow/unfollow/message/postback)
  5  บันทึกลงฐานข้อมูล (events, messages, follow_history, line_users ...)
  6  คำสั่งพิเศษ — ถ้าตรงจะตอบเองแล้ว "ตัด user นั้นออก" จากขั้นถัดไป
       6a ขอหยุด/รับข่าวสาร (PDPA)
       6b /dev  (ปิดโดย default)
       6c /ตรวจข้อมูล
  7  follow ใหม่ → ดึงโปรไฟล์ LINE
  8  ตรวจว่า user อยู่บน Rich Menu ที่เปิด AI ไหม
  9  Auto-reply (postback → กฎคีย์เวิร์ด → fallback)       timeout 12 วิ
 10  AI ตอบข้อความที่ไม่ตรงกฎ (เฉพาะ user บนเมนู AI)        timeout 28 วิ
 11  Automation trigger = follow
 12  รูป/ไฟล์ → เข้าคิว webhook_jobs (ประมวลผลสลิปนอก request)
 13  ตอบ 200 {"ok": true}
                                   │
                                   ▼ (เฉพาะรูป/ไฟล์)
        /api/internal/run-jobs  →  _handle_slips  (หัวข้อ 3)
```

---

## 2. อธิบายทีละขั้น

### ขั้น 1 — ตรวจลายเซ็น
- คำนวณ HMAC-SHA256 ของ body ด้วย `LINE_CHANNEL_SECRET` เทียบกับ header `x-line-signature`
- ไม่ตรง → `403 bad signature` (ไม่มี I/O ใด ๆ จึงไม่ต้องทำ rate limit)
- ถ้ายังไม่ได้ตั้ง `LINE_CHANNEL_SECRET` จะข้ามการตรวจ (ควรตั้งเสมอใน production)

### ขั้น 2 — กรอง event ซ้ำ
ทิ้ง event ที่ `deliveryContext.isRedelivery = true` เพราะรอบแรกประมวลผลไปแล้ว กันตอบซ้ำ

### ขั้น 3 — "กำลังพิมพ์…"
เรียก `start_loading` 20 วินาที ให้ทุก user ที่ส่ง message/postback (แชท 1:1) แบบขนาน ไม่รอผล

### ขั้น 4 — เตรียมข้อมูลต่อ event
| ประเภท | สิ่งที่ทำ |
|---|---|
| ทุก event | เก็บแถว `webhook_events` (type, text, postback_data, reply_token, payload เต็ม) |
| `postback` | แกะรหัส broadcast ที่แนบท้าย data ออก → ลงตาราง `postback_clicks` และใช้ data สะอาดในขั้นถัดไป |
| `follow` | `is_following=true`, เพิ่มแถว `follow_history` |
| `unfollow` | `is_following=false`, เพิ่มแถว `follow_history` |
| `message` | เก็บเข้า `messages` (direction=in), อัปเดตข้อความล่าสุด, เพิ่ม `unread` |
| มี replyToken | เก็บ `last_reply_token` ไว้ให้แอดมินตอบจาก Inbox ได้ฟรี |

### ขั้น 5 — บันทึกลงฐานข้อมูล
ลำดับเขียน: `webhook_events` → `messages` → `follow_history` → `postback_clicks` → คำนวณ `unread`/`follow_count`/`block_count` → upsert `line_users`
- ถ้า upsert พังเพราะคอลัมน์ reply-token ยังไม่มี (migration 0022) จะลองใหม่โดยตัดสองคีย์นั้นออก
- ถ้าขั้นนี้พังทั้งก้อน: แจ้งแอดมิน "webhook เก็บข้อมูลไม่สำเร็จ" แล้ว **ทำขั้นถัดไปต่อ**

### ขั้น 6 — คำสั่งพิเศษ (ตรงแล้วตอบเอง + ตัด user ออก)
ผู้ใช้ที่ถูกจัดการในขั้นนี้ จะถูกกรอง **ทุก event ของเขาใน batch นั้น** ออกจากขั้น 7–12

| ขั้น | ข้อความที่ตรง | ผล |
|---|---|---|
| 6a | "ยกเลิกรับข่าว", "หยุดส่งข่าว", "unsubscribe" ฯลฯ / "รับข่าวสาร", "subscribe" ฯลฯ | ตั้ง `consent` เป็น false/true แล้วตอบรับ |
| 6b | ขึ้นต้น `/dev` | ทำงานเมื่อเปิด `dev_command_enabled` และ userId อยู่ใน `dev_command_uids` เท่านั้น → เก็บลงคิว `dev_commands` + แจ้งแอดมิน (ไม่ได้แก้โค้ดอัตโนมัติ) |
| 6c | ข้อความ `/ตรวจข้อมูล` ตรงเป๊ะ | ตอบสถานะลงทะเบียน/จ่ายเงิน/สลิปล่าสุดผ่าน reply token (ฟรี) + ปุ่ม "ดูใบเสร็จ" ถ้าจ่ายแล้ว |

### ขั้น 7 — โปรไฟล์ผู้ติดตามใหม่
เฉพาะ `follow`: ดึง displayName/รูป/สถานะ/ภาษา (สูงสุด 20 คนต่อ batch) แล้ว upsert

### ขั้น 8 — ตรวจเมนู AI
เฉพาะข้อความตัวอักษรที่มี replyToken: ถ้ามี Rich Menu ที่เปิด `gemini_enabled` จะเช็ค rich menu **สด** ของแต่ละคน
ถ้าคนนั้นอยู่บนเมนู AI → เข้ากลุ่ม `gemini_uids` (ใช้ในขั้น 9–10)

### ขั้น 9 — Auto-reply (timeout 12 วินาที)
โหลดกฎ `auto_replies` ที่เปิดอยู่ เรียง `priority` มาก→น้อย แล้วต่อ event:

1. ข้ามถ้า user ถูกปิด auto-reply (`auto_reply_paused`) หรือได้รับคำตอบใน batch นี้แล้ว (1 คน = 1 คำตอบต่อ batch)
2. ถ้าเป็นรูปภาพและเปิด "AI ดูรูป" → ข้าม (ให้ขั้น 12 ตอบหลังดูรูป)
3. postback "ดูใบเสร็จ" → ตอบใบเสร็จของสลิป verified ล่าสุด
4. **postback** → ตาราง `postback_actions` (exact/prefix) มาก่อน
5. จากนั้นกฎ `auto_replies` ตามชนิด: `follow` / `postback` / `beacon` / ข้อความ (คีย์เวิร์ดตรงก่อน → ไม่ตรงค่อย `fallback`) / ชนิดอื่น (สติกเกอร์ ฯลฯ)
6. ถ้ากฎที่เจอคือ `fallback` แต่ user อยู่บนเมนู AI → **ไม่ตอบ** ปล่อยให้ขั้น 10
7. ตอบด้วย reply token (แทนชื่อ `{name}` ถ้ามี) แล้วบันทึกข้อความขาออก (`by=auto` หรือ `postback`)

### ขั้น 10 — AI ตอบ (timeout 28 วินาที)
เฉพาะข้อความตัวอักษรของ user บนเมนู AI ที่ **ยังไม่มีใครตอบ** ในขั้น 9
- ต้องมี `ANTHROPIC_API_KEY` หรือ `GEMINI_API_KEY`
- เคารพ `ai_daily_limit` (0 = ไม่จำกัด) เตือนแอดมินที่ 80% และเกินแล้วตอบข้อความ "รอแอดมิน"
- ตอบจากคลังความรู้/ข้อมูลของ user บันทึกเป็น `by=gemini`

### ขั้น 11 — Automation (follow)
`follow` → ลงทะเบียนเข้า automation ที่ trigger = `follow`

### ขั้น 12 — รูป/ไฟล์ → คิวงาน
- รวม event ที่เป็น `image` / `file` ใส่แถวเดียวใน `webhook_jobs` (`kind=slips`)
- ยิง `POST /api/internal/run-jobs` แบบไม่รอผล (invocation ใหม่มี budget 60 วิของตัวเอง)
- ถ้า insert คิวไม่ได้ → ประมวลผลในคำขอเดิมทันที (timeout 25 วิ)
- สำรอง: cron `/api/cron/run-jobs` ดึงงานค้างมาทำ (ในงาน cron หลักด้วย)

### ขั้น 13 — ตอบ LINE
`{"ok": true}` — จึงตอบเร็ว ไม่ติด timeout ของ LINE

---

## 3. การประมวลผลสลิป (หลังขั้น 12)

ตัวรันคิว `_run_webhook_jobs`: ดึงงาน `pending` เก่าสุด 15 งาน → เพิ่ม `attempts` → รัน `_handle_slips` (timeout 45 วิ/งาน)
สำเร็จ = `done` · พลาด = กลับ `pending` · พลาดครบ **3 ครั้ง** = `failed` (เก็บข้อความ error)

ต่อแต่ละรูป/ไฟล์ ใน `_handle_slips`:

| # | ขั้น | รายละเอียด |
|---|---|---|
| 1 | ดึงไฟล์ | ดาวน์โหลดจาก LINE → อัปโหลดเข้า Storage `media/slips/วันที่/<id>` → ผูก `media_url` กับข้อความใน Inbox |
| 2 | บริบทชำระเงิน | ดูข้อความ 15 รายการใน 24 ชม. ล่าสุด มีคำว่า ชำระ/โอน/สลิป/สมัคร/ค่าติว/บัญชี/หลักสูตร หรือไม่ (`pay_ctx`) |
| 3 | ประตูคัดสลิป | ถ้าเปิด "AI ดูรูป": วิเคราะห์รูป — **สลิป (≥0.55)** → ตอบ "ขอตรวจสอบ" และถือเป็นสลิป · **รูปทั่วไป** (≥0.8 มีบริบทเงิน / ≥0.6 ไม่มี) → ตอบเรื่องรูปนั้นแล้ว **จบ ไม่สร้างแถวสลิป** · **ไม่แน่ใจ** → ถือว่า "อาจเป็นสลิป" (ไม่สลับเมนู) · AI ใช้ไม่ได้ → ตอบกลาง ๆ ใช้กติกา pay_ctx / `slip_notify_all_images` |
| 4 | ตอบรับ | ส่งข้อความ "ขอตรวจสอบ" ให้ user **ครั้งเดียวต่อ batch** |
| 5 | หาหลักสูตรคาดหมาย | จากตาราง `registrations` ก่อน → ถ้ายังไม่เคยลงทะเบียนค่อยเดาจากบทสนทนา (FC/IC/PC/AC) |
| 6 | สร้างแถว `slips` | `status=new` ทันที (กันข้อมูลหายถ้างานถูกตัดกลางทาง) |
| 7 | สลับ Rich Menu | เฉพาะเมื่อ "แน่ใจว่าเป็นสลิป" และตั้ง `SLIP_SUCCESS_RICHMENU_ID` → ผูกเมนู (ลองซ้ำ 1 ครั้งถ้า LINE ล่ม) + บันทึก `richmenu_history` (source=`slip`) · ล้มเหลวแล้วแจ้งแอดมิน + บันทึก `operations` (`richmenu.slip_link_failed`) |
| 7b | ตาข่ายนิรภัย | ถ้าขั้น 7 ไม่ได้สลับ แต่ EasySlip ยืนยันเป็นสลิปจริงหรือสถานะ `verified` → สลับให้ตอนนี้ (source=`slip_verified`) |
| 8 | อ่านสลิป | EasySlip ก่อน → ถ้าไม่ได้/โควต้าเต็ม ใช้ Gemini เดา |
| 9 | ตัดสินผล | `_evaluate_slip` (ตารางด้านล่าง) |
| 10 | อัปเดตแถวสลิป | OCR, ยอด, ref, ธนาคาร, สถานะ, หมายเหตุอัตโนมัติ |
| 11 | ถ้า `verified` | รัน automation `slip_verified` + mark ลงทะเบียนเป็นจ่ายแล้ว (`paid=true`) |
| 12 | แจ้งแอดมิน | ✅ verified / ⚠️ review / ⛔ rejected พร้อมลิงก์ `/slips` |

> ระบบ **ไม่ push ผลตรวจให้ผู้ใช้** (ประหยัดโควต้า) ผู้ใช้พิมพ์ `/ตรวจข้อมูล` เพื่อดูผลเอง

### เกณฑ์สถานะสลิป
| เงื่อนไข (ตามลำดับ) | สถานะ |
|---|---|
| `ref` ซ้ำกับสลิปเดิม | `rejected` (สลิปเคยส่งแล้ว) |
| EasySlip ยืนยัน แต่บัญชีปลายทางไม่ตรงรายการ | `review` |
| บัญชีตรง แต่หลักสูตรที่ลงทะเบียนไม่ตรงกับยอด/บัญชี | `review` |
| บัญชีตรง และยอดเท่าราคา (±1 บาท) ทั้งราคาปกติหรือเต็ม | `verified` |
| บัญชีตรง แต่ยอดไม่ตรง | `review` |
| อ่านได้จาก Gemini เท่านั้น (ไม่ได้ตรวจจริง) | `review` |
| EasySlip ตรวจไม่ผ่าน / อ่านไม่ได้ | `review` |

---

## 4. ตัวเลขเวลาที่ควรรู้
| จุด | ค่า |
|---|---|
| Auto-reply | 12 วินาที |
| AI ตอบ | 28 วินาที |
| สลิป inline (ถ้าคิวใช้ไม่ได้) | 25 วินาที |
| สลิปในงานคิว | 45 วินาที/งาน, ลองสูงสุด 3 ครั้ง |
| โหลดดิ้ง "กำลังพิมพ์" | 20 วินาที |
| reply token | ใช้ได้สั้นมาก (ราว 1 นาที) — เกินแล้วหน้า Inbox จะ fallback เป็น push |

## 5. ตารางค่าตั้งที่มีผลกับ webhook
| ชื่อ | ที่อยู่ | ผล |
|---|---|---|
| `LINE_CHANNEL_SECRET` | env | ตรวจลายเซ็น |
| `SLIP_SUCCESS_RICHMENU_ID` | env | เมนูหลังส่งสลิป (ว่าง = ปิด) |
| `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | env | AI ตอบ/อ่านสลิป |
| `CRON_SECRET`, `APP_URL` | env | ยิง run-jobs และ cron |
| `dev_command_enabled`, `dev_command_uids` | app_settings | คำสั่ง `/dev` |
| `slip_notify_all_images` | app_settings | สร้างแถวสลิปจากรูปทุกรูป (default เปิด) |
| `ai_daily_limit` | app_settings | เพดานคำตอบ AI ต่อวัน |
| `send_receipt` | app_settings | แนบปุ่มดูใบเสร็จ |
| `auto_reply_paused` | ต่อ user | ปิดตอบอัตโนมัติ (แอดมินกำลังคุย) |

## 6. แก้ปัญหาเบื้องต้น
| อาการ | ตรวจที่ |
|---|---|
| LINE แจ้ง Webhook error 403 | `LINE_CHANNEL_SECRET` ไม่ตรงกับ Channel ที่ใช้ |
| ไม่ตอบอัตโนมัติเลย | มีกฎ `auto_replies` เปิดอยู่ไหม · user ถูก `auto_reply_paused` ไหม · ตอนนั้นถูกตัดในขั้น 6 หรือเปล่า |
| ตอบข้อความด้วยกฎ fallback ไม่ออก | user อยู่บนเมนู AI (fallback ถูกข้ามให้ AI ตอบแทน) |
| สลิปค้างสถานะ `new` | ดูตาราง `webhook_jobs` (status/error/attempts) · cron `run-jobs` ทำงานไหม |
| สลิปเป็น `review` ตลอด | EasySlip โควต้าเต็มหรือ token หมดอายุ (ดูหน้า health) |
| เมนูไม่เปลี่ยนหลังส่งสลิป | `SLIP_SUCCESS_RICHMENU_ID` ว่าง · ระบบไม่แน่ใจว่าเป็นสลิป · `ENFORCE_RICHMENU_ID` เปิดอยู่และดึงกลับ |
| ผู้ใช้ไม่ได้รับคำตอบ ทั้งที่ log เห็นข้อความ | reply token หมดอายุ หรือขั้น 9 ติด timeout 12 วิ — ดู log `auto-reply error` |
| ข้อมูล user ไม่ถูกเก็บ | แจ้งเตือน "webhook เก็บข้อมูลไม่สำเร็จ" → ตรวจ Supabase/migration |

ดูย้อนหลังได้ที่หน้า **Events** (`webhook_events`), **Inbox** (`messages`), **Slips** และตาราง `webhook_jobs`

# LINE Console

เครื่องมือจัดการ LINE Official Account ครบวงจร

- **Frontend** — React 18 + Vite + React Router + Recharts
- **Backend/API** — Python (FastAPI) รันเป็น Vercel Serverless Function
- **Database** — Supabase (Postgres) — เข้าผ่าน Python API เท่านั้น (service_role, RLS ปิดหมด)
- **Auth** — LINE Login (LIFF) → Python verify id_token → เช็คตาราง `admins`
- **Deploy** — Vercel (frontend + `/api/*` ใน repo เดียว)

## ฟีเจอร์

| กลุ่ม | ทำอะไรได้ |
|---|---|
| **Rich Menu** | list/create/delete, ตั้ง–ล้าง default, ผูก/ถอดเป็นชุด (ทุกคน / คนไม่มีเมนู / ระบุเอง / ตาม tag), sync สถานะรายคนลง DB, จัดการ alias, **ประวัติการเปลี่ยนเมนูรายคน**, sync/enforce อัตโนมัติผ่าน cron |
| **ส่งข้อความ** | broadcast, push, multicast, ส่งตาม filter (tag/menu) ใน DB, Flex/JSON message, validate, ประวัติการส่ง |
| **ผู้ใช้ / Webhook** | รับ webhook (follow/unfollow/message/postback) → เก็บลง DB, import userId, ดึงโปรไฟล์, sync followers (Verified OA), ค้นหา/แท็ก/โน้ต |
| **สถิติ** | insight ผู้ติดตาม/ข้อความ/demographic, โควตา + consumption, snapshot รายวัน + กราฟ 30 วัน |
| **ระบบ** | audit log ทุก action, จัดการผู้ดูแล (owner/admin/viewer) |
| **Gemini AI ตอบอัตโนมัติ** | ตอบคำถามอิสระด้วย Gemini เฉพาะ user กลุ่มที่ current rich menu ตรงชื่อที่กำหนด (default "แล้วพบกัน") — ปิดโดย default จนกว่าจะตั้ง `GEMINI_API_KEY` |

---

## ติดตั้ง

### 1. Supabase

1. สร้าง project ที่ [supabase.com](https://supabase.com) (ฟรี)
2. **SQL Editor** → วางทั้งไฟล์ [`supabase/migrations/0001_init.sql`](supabase/migrations/0001_init.sql) → Run
3. **Settings → API** เก็บค่า:
   - `Project URL` → `SUPABASE_URL`
   - `service_role` secret → `SUPABASE_SERVICE_ROLE_KEY` (⚠️ ห้ามหลุด ห้ามใส่ฝั่ง frontend)

### 2. LINE

- **Messaging API channel** → เก็บ `Channel access token` + `Channel secret`
- **LINE Login channel** → สร้าง LIFF app (Size: Full, scope `openid`+`profile`, Endpoint = URL ของ Vercel)
  → เก็บ `LIFF ID` + `Channel ID`
- Messaging API → **Webhook URL** = `https://<vercel-domain>/api/webhook` แล้วเปิด "Use webhook"

### 3. Deploy บน Vercel

```bash
cd line-console
npm install
# push ขึ้น GitHub แล้ว import ที่ vercel.com  (หรือ vercel CLI)
```

**Environment Variables** ที่ Vercel (Settings → Environment Variables):

| key | ค่า |
|---|---|
| `VITE_LIFF_ID` | LIFF ID (`2009830584-xxxx`) |
| `LINE_CHANNEL_ACCESS_TOKEN` | Messaging API token |
| `LINE_CHANNEL_SECRET` | Messaging API secret |
| `LIFF_CHANNEL_ID` | Channel ID (ตัวเลขล้วน) |
| `SUPABASE_URL` | `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | service_role key |
| `OPEN_SIGNUP` | `true` ชั่วคราว (คนแรกที่ล็อกอิน = owner) แล้วลบ/`false` |
| `CRON_SECRET` | สุ่มมายาว ๆ — กัน `/api/cron/*` โดนเรียกจากคนนอก (ตั้งใน Vercel Cron Job ด้วยจะได้ auth อัตโนมัติ) |
| `ENFORCE_RICHMENU_ID` | *(ตัวเลือก)* เปิด auto re-assign เมนูที่หลุด กลับเป็นเมนูนี้ — เว้นว่าง = ปิด |
| `ENFORCE_EXCLUDE_MENUS` | *(ตัวเลือก)* richMenuId ที่ยกเว้นไม่บังคับ คั่นด้วย `,` |
| `GEMINI_API_KEY` | *(ตัวเลือก)* เปิดฟีเจอร์ Gemini ตอบคำถามอิสระ — สมัครฟรีที่ [aistudio.google.com/apikey](https://aistudio.google.com/apikey), เว้นว่าง = ปิด |
| `GEMINI_MODEL` | *(ตัวเลือก)* default `gemini-2.5-flash` |
| `GEMINI_TRIGGER_MENU_NAME` | *(ตัวเลือก)* ชื่อ rich menu ที่จะให้ Gemini ตอบแทน auto-reply ปกติ — default `แล้วพบกัน` |

Vercel จะ build frontend (Vite) + deploy `api/index.py` เป็น Python function อัตโนมัติ
(`vercel.json` จัด rewrite `/api/*` → FastAPI, ที่เหลือ → SPA)

### 4. เริ่มใช้

1. เปิด `https://<vercel-domain>` → ล็อกอิน LINE → กลายเป็น owner (เพราะ `OPEN_SIGNUP=true`)
2. ปิด `OPEN_SIGNUP` (ลบ env หรือ `false`) แล้ว redeploy
3. เพิ่มผู้ดูแลคนอื่นในหน้า "ผู้ดูแล"
4. หน้า "ผู้ใช้" → import userId เดิม (เช่นจาก `all_userids_060969.csv`)
5. หน้า Rich Menu → sync + assign

---

## dev ในเครื่อง

```bash
npm install
npm i -g vercel && vercel dev      # รัน frontend + python api ที่ localhost:3000
# หรือแยก: `vercel dev` (api) + `npm run dev` (vite proxy /api ไป :3000)
```

## โครงสร้าง

```
line-console/
├─ api/
│  ├─ index.py            FastAPI app — ทุก endpoint
│  └─ _lib/
│     ├─ config.py        อ่าน env
│     ├─ line.py          LINE Messaging API client
│     ├─ supa.py          Supabase PostgREST client (service_role)
│     └─ auth.py          verify LIFF id_token + เช็ค admins
├─ supabase/migrations/
│  ├─ 0001_init.sql
│  ├─ 0002_slips_postbacks_settings.sql
│  └─ 0003_richmenu_history.sql   ตาราง richmenu_history (ประวัติเปลี่ยนเมนู)
├─ src/
│  ├─ App.jsx             layout + router + login gate
│  ├─ lib/{auth,api,ui}
│  └─ pages/{Dashboard,RichMenus,RichMenuHistory,Messaging,Users,Stats,Events,Admins}.jsx
├─ requirements.txt       fastapi, httpx
├─ vercel.json
└─ package.json
```

## Rich Menu — sync/enforce อัตโนมัติ + ประวัติการเปลี่ยน (cron)

**มีอยู่แล้ว** — หน้า "Rich Menu" (`/richmenus`) ทำ assign/unlink/sync แบบ manual จากเว็บได้ครบ (ปุ่ม "Sync สถานะผู้ใช้ทั้งหมด" และปุ่มผูก/ถอดเป็นชุด) และมี endpoint `/api/cron/sync-richmenu` อยู่แล้วสำหรับให้ scheduler ภายนอกเรียกเป็นระยะ — แค่ยังไม่ได้ตั้งเวลาให้รันเอง

**เพิ่มใหม่** ในรอบนี้:

1. **ตาราง `richmenu_history`** (migration `0003`) — เก็บทุกครั้งที่ `current_rich_menu_id`/`rich_menu_status` ของ user เปลี่ยนจริง (ไม่ log ถ้าเช็คซ้ำแล้วค่าเดิม) พร้อม `source` (`sync`/`cron`/`link`/`unlink`/`enforce`) และ `actor`
2. **หน้า "ประวัติ Rich Menu"** (`/richmenus/history`) — ดูประวัติทั้งหมด หรือกรองเป็นรายคน (ลิงก์จากหน้ารายละเอียด user ก็ไปตรงนี้ได้)
3. **`/api/cron/sync-richmenu` ตั้งเวลาให้รันเองแล้ว** ผ่าน Vercel Cron (ดู `vercel.json` → `crons`) — default วันละครั้ง (`0 3 * * *`, ตี 3) เพราะ **Vercel Hobby plan จำกัด cron ให้รันได้อย่างมากวันละ 1 ครั้ง** ถ้าอยากถี่กว่านั้น (เช่นทุก 5–15 นาทีเหมือนที่ `0001_init.sql` เตรียม pg_cron ไว้) ต้อง:
   - อัปเป็น **Vercel Pro** แล้วแก้ schedule ใน `vercel.json` ให้ถี่ขึ้น, **หรือ**
   - ใช้ **Supabase pg_cron** แทน (คอมเมนต์ไว้ท้าย `0001_init.sql` — แก้ `<APP_URL>`/`<CRON_SECRET>` แล้วรันใน SQL Editor) ซึ่งไม่ติดข้อจำกัดของ Vercel
4. **`/api/cron/enforce-richmenu`** (ปิดอยู่โดย default) — บังคับ user ที่เมนูปัจจุบันไม่ตรง `ENFORCE_RICHMENU_ID` (และไม่อยู่ใน `ENFORCE_EXCLUDE_MENUS`) ให้ผูกกลับเป็นเมนูนั้น ใช้แก้ปัญหากรณีเมนู "หลุด"/ถูกเปลี่ยนโดยอย่างอื่นไปเรื่อย ๆ — **ต้องตั้ง `ENFORCE_RICHMENU_ID` เองก่อนถึงจะทำงาน** (เจตนาให้ default ปลอดภัย ไม่ auto-force อะไรจนกว่าจะตัดสินใจ) ยังไม่ได้ใส่ไว้ใน `vercel.json` — เพิ่ม entry ใน `crons` เองเมื่อพร้อมใช้งาน เช่น:
   ```json
   { "path": "/api/cron/enforce-richmenu", "schedule": "0 4 * * *" }
   ```

> **หมายเหตุเรื่อง 114 คนที่เมนูหลุดกลับไปเป็น "สมัครติว"** (พบตอนตรวจระบบ) — ตรวจโค้ดใน `api/index.py` (webhook/postback handler) และ `richmenu-webapp/gas/Code.gs` แล้ว **ไม่พบ logic อัตโนมัติใดที่สั่งผูกเมนูนี้** (Code.gs เป็น read-only เช็คสถานะอย่างเดียว, ฝั่ง index.py การผูกเมนูเกิดจาก action ของแอดมินผ่าน `/api/richmenu/assign` เท่านั้น) แปลว่าการเปลี่ยนกลับน่าจะมาจาก (ก) มีคนกดผูกเมนูนี้เองผ่านหน้าเว็บ/สคริปต์อื่นในช่วงเวลานั้น หรือ (ข) มี automation ภายนอกระบบนี้ (เช่น Google Form/Zapier/Make ที่ผูกกับฟอร์มสมัครติว) — แนะนำเช็ค log ในหน้า "ปฏิบัติการล่าสุด" (`/`) หรือตาราง `operations`/`richmenu_history` (หลังใช้งานสักพัก) เพื่อดูว่าเกิดจาก actor ไหน ถ้ายืนยันว่าอยากให้ทุกคนเป็นเมนู register เสมอ ให้เปิด `/api/cron/enforce-richmenu` ตามข้อ 4

## Gemini AI ตอบคำถามอิสระ (เปิด/ปิด + ปรับความเข้มข้นได้ต่อเมนู)

**ทำอะไร** — เมื่อ user ทักข้อความ (text) เข้ามา ถ้า current rich menu **สด ๆ ตอนนั้น** (เช็คผ่าน LINE API ทุกครั้ง ไม่ใช้ค่า cache ใน DB) เป็นเมนูที่**เปิด Gemini ไว้** ระบบจะส่งคำถามไปให้ Gemini ตอบแบบอิสระ (ไม่มีข้อมูล/context เฉพาะ ตอบทั่วไปเป็นภาษาไทย) แล้วตอบกลับผ่าน LINE — **ทำงานแทน auto-reply/postback ปกติสำหรับ user กลุ่มนี้เท่านั้น** user กลุ่มอื่นไม่ถูกกระทบ ยังใช้ auto-reply/automation เดิมตามปกติ

**ปิดโดย default** — ถ้าไม่ตั้ง `GEMINI_API_KEY` endpoint นี้จะไม่ทำงานเลย (no-op) ไม่กระทบอะไรกับระบบเดิม

**เปิด/ปิด + ปรับความเข้มข้น ต่อเมนู ได้จากหน้าเว็บ** — ไปที่หน้า **Rich Menu** → กดปุ่ม **🤖 Gemini** ที่แถวของเมนูนั้น จะมี modal ให้:
- ติ๊กเปิด/ปิด Gemini สำหรับเมนูนั้นโดยเฉพาะ (ตั้งได้หลายเมนูพร้อมกัน ไม่จำกัดแค่เมนูเดียว)
- ปรับ **"ความเข้มข้นของคำตอบ"** (= `temperature` ของโมเดล) ด้วย slider 0.0–2.0 — ยิ่งสูงคำตอบยิ่งหลากหลาย/สร้างสรรค์แต่เสี่ยงหลุดประเด็นมากขึ้น ยิ่งต่ำคำตอบยิ่งนิ่ง/ตรงไปตรงมา (ค่าแนะนำ 0.7)

ค่าที่ตั้งเก็บอยู่ในตาราง `rich_menus` (คอลัมน์ `gemini_enabled`, `gemini_temperature`) — ต้องรัน migration `0004_gemini_richmenu_settings.sql` ใน Supabase ก่อนถึงจะใช้ปุ่มนี้ได้

**วิธีเปิดใช้ครั้งแรก:**
1. สมัคร API key ฟรีที่ [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (ล็อกอินด้วย Google account)
2. ตั้ง `GEMINI_API_KEY` ใน Vercel env vars → redeploy
3. รัน migration `0004_gemini_richmenu_settings.sql` ใน Supabase SQL Editor
4. ไปหน้า Rich Menu → กด 🤖 Gemini ที่เมนูที่ต้องการ → ติ๊กเปิด → เลือกความเข้มข้น → บันทึก
5. (ตัวเลือก) `GEMINI_MODEL` ปรับรุ่นโมเดลได้ผ่าน env var (default `gemini-3.6-flash` — ตัว `gemini-2.5-flash` เดิมถูก Google ยกเลิกไปแล้ว)

ยังรองรับค่าตั้งค่าแบบเก่า (`GEMINI_TRIGGER_MENU_NAME` env var, default "แล้วพบกัน") ไว้เป็น fallback ด้วย เผื่อยังไม่ได้ตั้งอะไรผ่านหน้าเว็บ — ใช้ temperature 0.7 คงที่

**ข้อจำกัด/ที่ควรรู้:**
- จำกัด **6 คำถาม/นาที/คน** กันสแปม/ต้นทุนบานปลาย (แก้ได้ในโค้ด `_handle_gemini_replies`)
- ถ้า Gemini ตอบไม่ได้/error/timeout → **เงียบไว้ ไม่ตอบอะไรเลย** (ตามที่ตกลงกันไว้ ไม่มี fallback message)
- ตอบแบบ "อิสระทั่วไป" ล้วน ๆ ไม่มีข้อมูลคอร์ส/ราคา/ตารางเรียนใด ๆ — ถ้าอยากให้ตอบแม่นขึ้นโดยอิงข้อมูลจริง ต้องเพิ่ม context ใน system prompt ที่ `_gemini_answer()` ทีหลัง
- Google AI Studio free tier มี rate limit ของตัวเอง (เปลี่ยนแปลงได้ตามนโยบาย Google) ถ้าใช้เยอะควรดู [ai.google.dev/pricing](https://ai.google.dev/pricing) ประกอบ
- แชทที่ Gemini ตอบจะถูกบันทึกลงตาราง `messages` (by = `gemini`, `payload.temperature` = ค่าที่ใช้ตอนนั้น) เหมือนข้อความอื่น ดูย้อนหลังได้ในหน้า "กล่องข้อความ"

## หมายเหตุ

- ทุก request ไป `/api/*` (ยกเว้น `/api/webhook`, `/api/health`) ต้องมี header `Authorization: Bearer <LIFF id_token>` — frontend ใส่ให้อัตโนมัติ
- `sync-followers` ใช้ได้เฉพาะ OA ที่เป็น **Verified/Premium**
- Supabase free tier: DB 500MB, พอสำหรับ userId หลักแสน + events
- แก้ Python code แล้ว push → Vercel redeploy เอง (ไม่มีขั้นตอน "new version" เหมือน GAS)

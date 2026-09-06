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
| **Rich Menu** | list/create/delete, ตั้ง–ล้าง default, ผูก/ถอดเป็นชุด (ทุกคน / คนไม่มีเมนู / ระบุเอง / ตาม tag), sync สถานะรายคนลง DB, จัดการ alias |
| **ส่งข้อความ** | broadcast, push, multicast, ส่งตาม filter (tag/menu) ใน DB, Flex/JSON message, validate, ประวัติการส่ง |
| **ผู้ใช้ / Webhook** | รับ webhook (follow/unfollow/message/postback) → เก็บลง DB, import userId, ดึงโปรไฟล์, sync followers (Verified OA), ค้นหา/แท็ก/โน้ต |
| **สถิติ** | insight ผู้ติดตาม/ข้อความ/demographic, โควตา + consumption, snapshot รายวัน + กราฟ 30 วัน |
| **ระบบ** | audit log ทุก action, จัดการผู้ดูแล (owner/admin/viewer) |

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
├─ supabase/migrations/0001_init.sql
├─ src/
│  ├─ App.jsx             layout + router + login gate
│  ├─ lib/{auth,api,ui}
│  └─ pages/{Dashboard,RichMenus,Messaging,Users,Stats,Events,Admins}.jsx
├─ requirements.txt       fastapi, httpx
├─ vercel.json
└─ package.json
```

## หมายเหตุ

- ทุก request ไป `/api/*` (ยกเว้น `/api/webhook`, `/api/health`) ต้องมี header `Authorization: Bearer <LIFF id_token>` — frontend ใส่ให้อัตโนมัติ
- `sync-followers` ใช้ได้เฉพาะ OA ที่เป็น **Verified/Premium**
- Supabase free tier: DB 500MB, พอสำหรับ userId หลักแสน + events
- แก้ Python code แล้ว push → Vercel redeploy เอง (ไม่มีขั้นตอน "new version" เหมือน GAS)

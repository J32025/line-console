import os

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
# LIFF / LINE Login channel id (ตัวเลขล้วน) — รับ LIFF id เต็มได้ ตัด -xxxx ออกให้
LIFF_CHANNEL_ID = os.environ.get("LIFF_CHANNEL_ID", "").strip().split("-")[0]

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# ถ้า true: ใครล็อกอิน LINE ก็เข้าได้ (ยังไม่เช็คตาราง admins) — ใช้ตอน bootstrap เท่านั้น
OPEN_SIGNUP = os.environ.get("OPEN_SIGNUP", "").lower() in ("1", "true", "yes")

# secret สำหรับ endpoint /api/cron/* (เรียกโดย Supabase pg_cron)
CRON_SECRET = os.environ.get("CRON_SECRET", "").strip()

# LINE userId ที่จะรับแจ้งเตือน error ของระบบ (คั่นด้วย ,) — ว่าง = ไม่แจ้ง
ALERT_USER_IDS = [u.strip() for u in os.environ.get("ALERT_USER_IDS", "").split(",") if u.strip()]

# LINE Login channel (สำหรับ LIFF) — ใส่ access token ถ้าอยาก sync รายการ LIFF จาก LINE อัตโนมัติ
LINE_LOGIN_CHANNEL_TOKEN = os.environ.get("LINE_LOGIN_CHANNEL_TOKEN", "").strip()

# EasySlip API token (ตรวจสลิปอัตโนมัติ) — ว่าง = ไม่ตรวจ OCR แค่แจ้งเตือน
EASYSLIP_TOKEN = os.environ.get("EASYSLIP_TOKEN", "").strip()

# domain ของเว็บนี้ (สำหรับแสดง endpoint แนะนำ) — auto จาก VERCEL_URL
APP_URL = (os.environ.get("APP_URL")
           or ("https://" + os.environ["VERCEL_PROJECT_PRODUCTION_URL"] if os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") else "")
           or "https://line-console-pi.vercel.app")

LINE_API = "https://api.line.me"
LINE_DATA_API = "https://api-data.line.me"

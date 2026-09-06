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

LINE_API = "https://api.line.me"
LINE_DATA_API = "https://api-data.line.me"

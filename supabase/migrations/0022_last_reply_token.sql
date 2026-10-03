-- 0022_last_reply_token.sql
-- เก็บ reply token ล่าสุดของแต่ละ user ไว้ที่ line_users — ให้แอดมินตอบใน Inbox ใช้ reply token
-- (ฟรี ไม่กินโควต้า push) แทน push ได้ ถ้าตอบทันช่วงที่ยัง "สด" อยู่ (ดู inbox_send ใน api/index.py)
-- ไม่ทันก็ fallback ไป push ตามปกติ ไม่กระทบการทำงานเดิม

alter table line_users add column if not exists last_reply_token text;
alter table line_users add column if not exists last_reply_token_at timestamptz;

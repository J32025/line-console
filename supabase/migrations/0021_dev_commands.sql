-- 0021_dev_commands.sql
-- คิวคำสั่ง "พัฒนาระบบ" ที่เจ้าของส่งเข้ามาทาง LINE แชทกับบอทโดยตรง (ขึ้นต้นด้วย /dev)
-- ทำงานเฉพาะ userId ที่อยู่ใน allow-list (setting dev_command_uids) และเปิดใช้งานไว้ (setting dev_command_enabled)
-- เท่านั้น — ปิดโดย default ทั้งสองอย่าง ต้องเข้าไปตั้งเองที่หน้า "ผู้ดูแล" ก่อนถึงจะใช้ได้
-- บอทแค่ "รับคำสั่งเก็บคิวไว้ + ตอบรับทันที" เท่านั้น — ไม่ได้แก้โค้ด/deploy เองอัตโนมัติ
-- (ต้องให้ Claude เข้ามาอ่านคิวนี้ในเซสชันที่มีคนดูแลอยู่ แล้วค่อย commit/push/deploy เองตามปกติ
--  เป็นการตั้งใจคงจุดตรวจสอบของมนุษย์ไว้ก่อนของจริงขึ้น production)

create table if not exists dev_commands (
  id bigint generated always as identity primary key,
  line_user_id text not null,
  command text not null,
  status text not null default 'pending',  -- pending | done | failed
  result text,
  created_at timestamptz not null default now(),
  processed_at timestamptz
);
create index if not exists dev_commands_status_idx on dev_commands (status, created_at);

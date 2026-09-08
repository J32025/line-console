-- ตั้งค่า Gemini AI (เปิด/ปิด + ความเข้มข้นของคำตอบ) แยกตาม rich menu แต่ละอัน
alter table rich_menus add column if not exists gemini_enabled boolean not null default false;
alter table rich_menus add column if not exists gemini_temperature numeric not null default 0.7;

-- migrate ค่าเดิมจาก GEMINI_TRIGGER_MENU_NAME (env var) มาเป็นค่าตั้งต้นในตาราง แบบ best-effort
-- (ถ้าชื่อเมนูใน DB ไม่ตรงกับ env ทุกตัวอักษร จะไม่ auto-enable ให้ — ไปเปิดเองผ่านหน้าเว็บได้)
update rich_menus set gemini_enabled = true, gemini_temperature = 0.7
where name = 'แล้วพบกัน' and not gemini_enabled;

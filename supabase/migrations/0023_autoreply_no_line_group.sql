-- 0023_autoreply_no_line_group.sql
-- FAQ ที่ลูกค้าถามบ่อย: มีกลุ่มไลน์ไหม/ขอลิงก์กลุ่ม -> ตอบว่าไม่มีไลน์กลุ่ม มีแต่ไลน์น้องพัสดุที่เดียว
-- idempotent: ลบกฎชื่อเดิมก่อน แล้วใส่ใหม่

delete from auto_replies where name = 'ไม่มีไลน์กลุ่ม';

insert into auto_replies (name, trigger, match_type, keywords, messages, priority, enabled, created_by)
values (
  'ไม่มีไลน์กลุ่ม',
  'text',
  'contains',
  array['กลุ่มไลน์', 'ไลน์กลุ่ม', 'กลุ่ม line', 'line กลุ่ม', 'ลิงก์กลุ่ม', 'ลิ้งกลุ่ม', 'ลิงค์กลุ่ม'],
  '[{"type":"text","text":"ไม่มีไลน์กลุ่มนะครับ มีแต่ไลน์น้องพัสดุที่เดียวครับ 🙏"}]'::jsonb,
  50,
  true,
  'setup'
);

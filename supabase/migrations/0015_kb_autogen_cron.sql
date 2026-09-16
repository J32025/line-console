-- 0015_kb_autogen_cron.sql
-- ตั้งเวลาให้ระบบร่างบทความคลังความรู้ (จัดซื้อจัดจ้างภาครัฐ) เพิ่มเองอัตโนมัติทีละน้อย
-- ไม่แตะตารางงานเดิม (ใช้ jobname ใหม่ เฉพาะของตัวเองเท่านั้น)
-- วิธีใช้: แทน <APP_URL> = https://line-console-pi.vercel.app และ <CRON_SECRET> = ค่าจริง
--          แล้วรันทั้งไฟล์ใน Supabase SQL Editor (รันซ้ำได้)

create extension if not exists pg_cron;
create extension if not exists pg_net;

do $$
declare
  app_url text := '<APP_URL>';
  secret  text := '<CRON_SECRET>';
begin
  perform cron.unschedule(jobname) from cron.job where jobname = 'kb-autogen-daily';

  -- ร่าง 2 บทความ/วัน (07:00 UTC = 14:00 ไทย) จนกว่าจะครบหัวข้อที่ตั้งไว้ (~29 หัวข้อ)
  -- ทุกบทความที่สร้างจะ enabled=false เสมอ ต้องไปตรวจ+เปิดใช้เองที่หน้า /kb
  perform cron.schedule('kb-autogen-daily','0 7 * * *',
    format($f$select net.http_post(url:='%s/api/cron/kb-autogen?key=%s&count=2', timeout_milliseconds:=55000)$f$, app_url, secret));
end $$;

-- ตรวจสอบ: select jobname, schedule, active from cron.job where jobname = 'kb-autogen-daily';
-- ดูความคืบหน้า: เรียก GET /api/kb/autogen/status (หรือดูในหน้า /kb การ์ด "สร้างความรู้อัตโนมัติ")
-- หยุดชั่วคราว: select cron.unschedule('kb-autogen-daily');

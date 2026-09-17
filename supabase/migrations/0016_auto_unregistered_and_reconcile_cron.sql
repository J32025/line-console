-- 0016_auto_unregistered_and_reconcile_cron.sql
-- ตั้งเวลา 2 งานอัตโนมัติใหม่ (ไม่แตะตารางงานเดิมเลย):
--   1) richmenu-unregistered-30min: สลับ Rich Menu เตือนคนที่ยังไม่ลงทะเบียนให้ follower ใหม่ต่อเนื่อง
--      (no-op ถ้ายังไม่ได้ตั้งค่า unregistered_richmenu_id ที่หน้า ผู้ดูแล)
--   2) reconcile-auto-mark-daily: mark paid=true อัตโนมัติให้ทะเบียนที่มีสลิป verified ตรงคอร์สอยู่แล้ว
--      แต่ยัง paid=false ค้างอยู่ (ข้อมูลยืนยันแล้ว แค่ sync flag ให้ตรง — ไม่แตะเคสอื่นที่ต้องให้แอดมินตรวจ)
-- วิธีใช้: แทน <APP_URL> = https://line-console-pi.vercel.app และ <CRON_SECRET> = ค่าจริง
--          แล้วรันทั้งไฟล์ใน Supabase SQL Editor (รันซ้ำได้)

create extension if not exists pg_cron;
create extension if not exists pg_net;

do $$
declare
  app_url text := '<APP_URL>';
  secret  text := '<CRON_SECRET>';
  j record;
begin
  for j in (select jobname from cron.job where jobname in
    ('richmenu-unregistered-30min','reconcile-auto-mark-daily')) loop
    perform cron.unschedule(j.jobname);
  end loop;

  perform cron.schedule('richmenu-unregistered-30min','*/30 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/richmenu-unregistered?key=%s&limit=300', timeout_milliseconds:=55000)$f$, app_url, secret));

  -- 08:00 UTC = 15:00 ไทย (หลัง reconcile ข้อมูลของเมื่อวานเข้ามาครบแล้ว)
  perform cron.schedule('reconcile-auto-mark-daily','0 8 * * *',
    format($f$select net.http_post(url:='%s/api/cron/reconcile-auto-mark?key=%s', timeout_milliseconds:=55000)$f$, app_url, secret));
end $$;

-- ตรวจสอบ: select jobname, schedule, active from cron.job where jobname like '%unregistered%' or jobname like '%reconcile%';
-- หยุดชั่วคราว: select cron.unschedule('richmenu-unregistered-30min'); select cron.unschedule('reconcile-auto-mark-daily');

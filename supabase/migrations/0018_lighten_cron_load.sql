-- 0018_lighten_cron_load.sql
-- ลดภาระ Vercel (Hobby มีโควต้าเวลารัน function ต่อเดือน — เคยโดนระงับ 402 DEPLOYMENT_DISABLED)
-- ต้นเหตุหลัก: sync-richmenu ทุก 5 นาที x 1000 คน/รอบ ใช้ ~55 วินาที/รอบ = ~4.4 ชม./วัน (~90% ของเวลารัน cron ทั้งหมด)
--   -> เปลี่ยนเป็นทุก 10 นาที x 300 คน/รอบ (~10-15 วินาที) วนครบทุกคนทุก ~2.8 ชม. (เดิม ~25 นาที)
--   run-jobs: ทุก 2 นาที -> ทุก 5 นาที (webhook ยิง run-jobs เองอยู่แล้ว cron เป็นแค่ตัวสำรอง)
-- แทน <CRON_SECRET> ด้วยค่าจริง (ห้าม commit ค่าจริงลง repo — repo เป็น public) แล้วรันใน Supabase SQL Editor

do $$
declare
  app_url text := 'https://line-console-woad.vercel.app';
  secret  text := '<CRON_SECRET>';
  j record;
begin
  for j in (select jobname from cron.job where jobname in ('sync-richmenu-5min','run-jobs-2min','sync-richmenu-10min','run-jobs-5min')) loop
    perform cron.unschedule(j.jobname);
  end loop;

  perform cron.schedule('sync-richmenu-10min','*/10 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/sync-richmenu?key=%s&limit=300', timeout_milliseconds:=58000)$f$, app_url, secret));

  perform cron.schedule('run-jobs-5min','*/5 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/run-jobs?key=%s', timeout_milliseconds:=55000)$f$, app_url, secret));
end $$;

-- ตรวจสอบ: select jobname, schedule from cron.job order by jobname;

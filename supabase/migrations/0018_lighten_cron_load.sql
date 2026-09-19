-- 0018_lighten_cron_load.sql
-- ลดภาระ Vercel (Hobby มีโควต้าเวลารัน function ต่อเดือน — เคยโดนระงับ 402 DEPLOYMENT_DISABLED)
-- ต้นเหตุหลัก: sync-richmenu ทุก 5 นาที x 1000 คน/รอบ ใช้ ~55 วินาที/รอบ = ~4.4 ชม./วัน (~90% ของเวลารัน cron ทั้งหมด)
--   -> เปลี่ยนเป็นวันละ 2 รอบ 08:00 และ 19:00 น. (เวลาไทย = 01:00 และ 12:00 UTC)
--      แต่ละรอบยิง 6 ชุดห่างกันชุดละ 2 นาที (1 request ทำได้สูงสุด 1000 คน, ชุดถัดไปหยิบคนที่เช็คนานสุดต่อ
--      = ครอบคลุมสูงสุด 6000 คน) ~25 วินาที/ชุด => ~5 นาที/วัน (เดิม ~4.4 ชม./วัน)
--   run-jobs: ทุก 2 นาที -> ทุก 5 นาที (webhook ยิง run-jobs เองอยู่แล้ว cron เป็นแค่ตัวสำรอง)
-- แทน <CRON_SECRET> ด้วยค่าจริง (ห้าม commit ค่าจริงลง repo — repo เป็น public) แล้วรันใน Supabase SQL Editor
-- pg_cron ใช้เวลา UTC

do $$
declare
  app_url text := 'https://line-console-woad.vercel.app';
  secret  text := '<CRON_SECRET>';
  j record;
  i int;
begin
  for j in (select jobname from cron.job
            where jobname in ('sync-richmenu-5min','sync-richmenu-10min','run-jobs-2min','run-jobs-5min')
               or jobname like 'sync-richmenu-batch-%') loop
    perform cron.unschedule(j.jobname);
  end loop;

  for i in 0..5 loop
    perform cron.schedule(format('sync-richmenu-batch-%s', i + 1), format('%s 1,12 * * *', i * 2),
      format($f$select net.http_post(url:='%s/api/cron/sync-richmenu?key=%s&limit=1000', timeout_milliseconds:=58000)$f$, app_url, secret));
  end loop;

  perform cron.schedule('run-jobs-5min','*/5 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/run-jobs?key=%s', timeout_milliseconds:=55000)$f$, app_url, secret));
end $$;

-- ตรวจสอบ: select jobname, schedule from cron.job order by jobname;

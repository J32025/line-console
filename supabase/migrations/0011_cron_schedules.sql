-- 0011_cron_schedules.sql
-- ตารางงาน pg_cron ทั้งหมดของระบบ (รวมของใหม่: heartbeat, daily-digest, task-reminders)
-- วิธีใช้: แทน <APP_URL> = https://line-console-pi.vercel.app และ <CRON_SECRET> = ค่าจริง
--          แล้วรันทั้งไฟล์ใน Supabase SQL Editor (รันซ้ำได้ — unschedule ก่อน schedule ใหม่)

create extension if not exists pg_cron;
create extension if not exists pg_net;

do $$
declare
  app_url text := '<APP_URL>';
  secret  text := '<CRON_SECRET>';
  j record;
begin
  -- ลบตารางงานเดิมที่ชื่อซ้ำ (กันซ้อน)
  for j in select jobname from cron.job where jobname in (
    'sync-richmenu-5min','run-scheduled-5min','run-automations-5min',
    'snapshot-stats-daily','backup-daily','heartbeat-2h',
    'daily-digest','task-reminders-hourly','run-jobs-2min'
  ) loop
    perform cron.unschedule(j.jobname);
  end loop;

  perform cron.schedule('run-jobs-2min','*/2 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/run-jobs?key=%s', timeout_milliseconds:=55000)$f$, app_url, secret));

  perform cron.schedule('sync-richmenu-5min','*/5 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/sync-richmenu?key=%s', timeout_milliseconds:=58000)$f$, app_url, secret));

  perform cron.schedule('run-scheduled-5min','*/5 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/run-scheduled?key=%s', timeout_milliseconds:=55000)$f$, app_url, secret));

  perform cron.schedule('run-automations-5min','*/5 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/run-automations?key=%s', timeout_milliseconds:=55000)$f$, app_url, secret));

  perform cron.schedule('snapshot-stats-daily','5 1 * * *',
    format($f$select net.http_post(url:='%s/api/cron/snapshot-stats?key=%s', timeout_milliseconds:=30000)$f$, app_url, secret));

  perform cron.schedule('backup-daily','15 1 * * *',
    format($f$select net.http_post(url:='%s/api/cron/backup?key=%s', timeout_milliseconds:=55000)$f$, app_url, secret));

  -- ใหม่: เช็คสุขภาพ cron ทุก 2 ชม.
  perform cron.schedule('heartbeat-2h','0 */2 * * *',
    format($f$select net.http_post(url:='%s/api/cron/heartbeat?key=%s', timeout_milliseconds:=30000)$f$, app_url, secret));

  -- ใหม่: สรุปประจำวัน 07:30 (เวลาไทย = 00:30 UTC)
  perform cron.schedule('daily-digest','30 0 * * *',
    format($f$select net.http_post(url:='%s/api/cron/daily-digest?key=%s', timeout_milliseconds:=30000)$f$, app_url, secret));

  -- ใหม่: เตือนงานถึงกำหนด ทุกชั่วโมง
  perform cron.schedule('task-reminders-hourly','0 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/task-reminders?key=%s', timeout_milliseconds:=30000)$f$, app_url, secret));
end $$;

-- ตรวจสอบ: select jobname, schedule, active from cron.job order by jobname;

-- 0017_repoint_cron_to_new_host.sql
-- ย้ายระบบจาก line-console-pi.vercel.app (บัญชี Vercel เดิม ถูกระงับเพราะบัตรจ่ายเงินไม่ผ่าน)
-- ไปโฮสต์ใหม่ https://line-console-woad.vercel.app (บัญชี Vercel ใหม่) เมื่อ 18/09
-- ไฟล์นี้รวมทุก cron job จาก 0011 + 0015 + 0016 มา unschedule+reschedule ด้วย URL ใหม่ในทีเดียว
-- (CRON_SECRET ค่าเดิม ไม่เปลี่ยน — ตั้งไว้ในบัญชีใหม่ค่าเดียวกันแล้ว)
-- วิธีใช้: แทน <CRON_SECRET> ด้วยค่าจริง แล้วรันทั้งไฟล์ใน Supabase SQL Editor

create extension if not exists pg_cron;
create extension if not exists pg_net;

do $$
declare
  app_url text := 'https://line-console-woad.vercel.app';
  secret  text := '<CRON_SECRET>';
  j record;
begin
  for j in (select jobname from cron.job where jobname in (
    'run-jobs-2min','sync-richmenu-5min','run-scheduled-5min','run-automations-5min',
    'snapshot-stats-daily','backup-daily','heartbeat-2h','daily-digest','task-reminders-hourly',
    'kb-autogen-daily','richmenu-unregistered-30min','reconcile-auto-mark-daily'
  )) loop
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

  perform cron.schedule('heartbeat-2h','0 */2 * * *',
    format($f$select net.http_post(url:='%s/api/cron/heartbeat?key=%s', timeout_milliseconds:=30000)$f$, app_url, secret));

  perform cron.schedule('daily-digest','30 0 * * *',
    format($f$select net.http_post(url:='%s/api/cron/daily-digest?key=%s', timeout_milliseconds:=30000)$f$, app_url, secret));

  perform cron.schedule('task-reminders-hourly','0 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/task-reminders?key=%s', timeout_milliseconds:=30000)$f$, app_url, secret));

  perform cron.schedule('kb-autogen-daily','0 7 * * *',
    format($f$select net.http_post(url:='%s/api/cron/kb-autogen?key=%s&count=2', timeout_milliseconds:=55000)$f$, app_url, secret));

  perform cron.schedule('richmenu-unregistered-30min','*/30 * * * *',
    format($f$select net.http_post(url:='%s/api/cron/richmenu-unregistered?key=%s&limit=300', timeout_milliseconds:=55000)$f$, app_url, secret));

  perform cron.schedule('reconcile-auto-mark-daily','0 8 * * *',
    format($f$select net.http_post(url:='%s/api/cron/reconcile-auto-mark?key=%s', timeout_milliseconds:=55000)$f$, app_url, secret));
end $$;

-- ตรวจสอบ: select jobname, schedule, active from cron.job order by jobname;

-- 0019_rate_limits.sql
-- rate limit ที่ใช้ได้จริงข้ามหลาย instance ของ Vercel serverless
-- (ตัวเดิมเก็บในหน่วยความจำของแต่ละ instance — instance ใหม่/รีไซเคิลก็เริ่มนับใหม่ จึงกันอะไรไม่ได้จริง)
-- fixed-window counter: 1 แถวต่อ (key, หน้าต่างเวลา) — นับด้วย upsert แบบ atomic ในคำสั่งเดียว
-- โค้ดฝั่งแอป fail-open: ถ้าตารางนี้ยังไม่มี/DB ช้า จะถอยไปใช้ตัวนับในหน่วยความจำเดิม (ไม่ล่ม)

create table if not exists rate_limits (
  key          text        not null,
  window_start timestamptz not null,
  hits         int         not null default 0,
  primary key (key, window_start)
);
alter table rate_limits enable row level security;   -- เหมือนทุกตาราง: เข้าผ่าน service_role เท่านั้น

create or replace function rate_limit_hit(p_key text, p_window_seconds int, p_limit int)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  w timestamptz := to_timestamp(floor(extract(epoch from now()) / p_window_seconds) * p_window_seconds);
  n int;
begin
  insert into rate_limits (key, window_start, hits) values (p_key, w, 1)
  on conflict (key, window_start) do update set hits = rate_limits.hits + 1
  returning hits into n;

  -- เก็บกวาดแถวเก่า ~1% ของการเรียก (ไม่ต้องพึ่ง cron เพิ่ม)
  if random() < 0.01 then
    delete from rate_limits where window_start < now() - interval '1 day';
  end if;

  return n <= p_limit;
end $$;

-- กันไม่ให้ anon/authenticated key เรียก function นี้ผ่าน PostgREST ตรง ๆ (ใช้ได้เฉพาะ service_role)
revoke all on function rate_limit_hit(text, int, int) from public, anon, authenticated;
grant execute on function rate_limit_hit(text, int, int) to service_role;

-- ตรวจสอบ: select rate_limit_hit('test', 60, 2), rate_limit_hit('test', 60, 2), rate_limit_hit('test', 60, 2);
--          ควรได้ true, true, false   แล้วลบ: delete from rate_limits where key = 'test';

-- ============================================================
-- Rich menu change history — บันทึกทุกครั้งที่เมนูของ user เปลี่ยน
-- (จาก sync, assign/unlink จากเว็บ, cron sync, cron enforce)
-- รันใน Supabase Dashboard > SQL Editor  หรือ  supabase db push
-- ============================================================
create table if not exists richmenu_history (
  id bigint generated always as identity primary key,
  line_user_id text not null,
  old_rich_menu_id text,
  new_rich_menu_id text,
  old_status text,
  new_status text,
  source text not null default 'sync',   -- sync | cron | assign | unlink | enforce
  actor text,                            -- admin line_user_id หรือ 'cron'
  created_at timestamptz not null default now()
);
create index if not exists richmenu_history_uid_idx     on richmenu_history (line_user_id, created_at desc);
create index if not exists richmenu_history_created_idx on richmenu_history (created_at desc);

alter table richmenu_history enable row level security;

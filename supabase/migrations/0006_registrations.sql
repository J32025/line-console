-- ============================================================
-- 0006 — registrations: รายชื่อผู้ลงทะเบียนเรียน (จากฟอร์ม)
-- รันใน Supabase SQL Editor
-- ============================================================
create table if not exists registrations (
  id bigint generated always as identity primary key,
  reg_id text,
  line_user_id text,
  name text, tel text, org text, email text, job text,
  course text,            -- normalized: FC70 / IC70 / PC70-1 / PC70-2
  course_raw text,
  slip_url text,
  form_ts text,
  paid boolean not null default false,
  approved boolean,       -- null = รอตรวจ
  passed text,
  note text,
  extra jsonb,
  source text not null default 'import',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists registrations_uid_course_uq on registrations (line_user_id, course);
create index if not exists registrations_course_idx  on registrations (course);
create index if not exists registrations_uid_idx     on registrations (line_user_id);
create index if not exists registrations_created_idx on registrations (created_at desc);
alter table registrations enable row level security;

notify pgrst, 'reload schema';

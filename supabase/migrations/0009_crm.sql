-- ============================================================
-- 0009 — CRM: โน้ต/กิจกรรม, pipeline stage, ความยินยอม, คลาส/รุ่น, เช็คชื่อ
-- ============================================================

-- โน้ต / บันทึกกิจกรรมต่อลูกค้า (หลายรายการ)
create table if not exists contact_notes (
  id bigint generated always as identity primary key,
  line_user_id text not null,
  body text not null,
  kind text not null default 'note',   -- note | call | meeting | system
  author text,
  created_at timestamptz not null default now()
);
create index if not exists contact_notes_uid_idx on contact_notes (line_user_id, created_at desc);
alter table contact_notes enable row level security;

-- pipeline stage + ความยินยอมการตลาด บน line_users
alter table line_users add column if not exists stage text;             -- lead|interested|registered|paid|enrolled|completed|alumni|lost
alter table line_users add column if not exists stage_at timestamptz;
alter table line_users add column if not exists consent boolean;        -- null=ไม่ทราบ, true/false
alter table line_users add column if not exists consent_at timestamptz;
alter table line_users add column if not exists merged_into text;       -- ถ้าถูก merge เข้าบัญชีอื่น

-- คลาส / รุ่น
create table if not exists classes (
  id bigint generated always as identity primary key,
  course text not null,
  name text,
  cohort text,
  start_date date,
  end_date date,
  schedule text,
  zoom_url text,
  materials_url text,
  capacity int,
  status text not null default 'open',   -- open | running | closed
  note text,
  created_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists classes_course_idx on classes (course, start_date);
alter table classes enable row level security;

alter table registrations add column if not exists class_id bigint;
alter table registrations add column if not exists exam_passed boolean;

-- เช็คชื่อ
create table if not exists attendance (
  id bigint generated always as identity primary key,
  class_id bigint not null,
  line_user_id text not null,
  session int not null default 1,
  present boolean not null default true,
  note text,
  marked_by text,
  created_at timestamptz not null default now()
);
create unique index if not exists attendance_uq on attendance (class_id, line_user_id, session);
create index if not exists attendance_class_idx on attendance (class_id);
alter table attendance enable row level security;

notify pgrst, 'reload schema';

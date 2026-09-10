-- ============================================================
-- 0008 — tasks: งาน/ติดตาม (follow-up) ผูกกับลูกค้าหรือไม่ก็ได้
-- ============================================================
create table if not exists tasks (
  id bigint generated always as identity primary key,
  line_user_id text,
  title text not null,
  detail text,
  due_at timestamptz,
  status text not null default 'open',    -- open | done | cancelled
  priority text default 'normal',         -- low | normal | high
  assigned_to text,
  tag text,                               -- จ่ายเงิน / ติดตาม / โทร / เอกสาร ...
  created_by text,
  done_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists tasks_status_idx   on tasks (status, due_at);
create index if not exists tasks_uid_idx      on tasks (line_user_id);
create index if not exists tasks_assignee_idx on tasks (assigned_to, status);
alter table tasks enable row level security;

notify pgrst, 'reload schema';

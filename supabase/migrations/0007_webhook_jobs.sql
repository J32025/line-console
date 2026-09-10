-- ============================================================
-- 0007 — webhook_jobs: คิวงานหนักจาก webhook (สลิป) ให้ประมวลผลนอก request
--   webhook return เร็ว -> ไม่ timeout -> LINE ไม่ retry -> ลูกค้าได้รับตอบเสมอ
-- ============================================================
create table if not exists webhook_jobs (
  id bigint generated always as identity primary key,
  kind text not null,                       -- slips
  payload jsonb not null,
  status text not null default 'pending',   -- pending | done | failed
  attempts int not null default 0,
  error text,
  created_at timestamptz not null default now(),
  processed_at timestamptz
);
create index if not exists webhook_jobs_pending_idx on webhook_jobs (status, created_at);
alter table webhook_jobs enable row level security;

notify pgrst, 'reload schema';

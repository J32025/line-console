-- ============================================================
-- 0002 — postback_actions, app_settings, payment_accounts, slips
-- ตารางเหล่านี้เดิมสร้างสดผ่าน Management API — ย้ายมาลง migration ให้ rebuild ได้
-- idempotent: รันซ้ำได้ปลอดภัย
-- ============================================================

-- ---------- postback routing table ----------
create table if not exists postback_actions (
  id bigint generated always as identity primary key,
  data text not null unique,                 -- เช่น FC70_REGISTER
  label text,
  enabled boolean not null default true,
  match text not null default 'exact',       -- exact | prefix
  messages jsonb not null default '[]'::jsonb,
  note text,
  hits int not null default 0,
  last_hit_at timestamptz,
  created_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists postback_actions_enabled_idx on postback_actions (enabled, match);

-- ---------- key/value settings ----------
create table if not exists app_settings (
  key text primary key,
  value jsonb,
  updated_at timestamptz not null default now()
);
-- ค่า default: แจ้งเตือนทุกรูปที่ส่งเข้ามา (ตั้ง false เพื่อแจ้งเฉพาะรูปหลังคุยเรื่องชำระเงิน)
insert into app_settings (key, value) values ('slip_notify_all_images', 'true'::jsonb)
  on conflict (key) do nothing;

-- ---------- บัญชีรับเงินแต่ละหลักสูตร ----------
create table if not exists payment_accounts (
  id bigint generated always as identity primary key,
  course text not null,                       -- FC | IC | PC | AC
  bank text,
  account_no text,
  account_name text,
  price numeric,                              -- ราคาโปรโมชั่น
  full_price numeric,                         -- ราคาเต็ม
  active boolean not null default true,
  created_at timestamptz not null default now()
);

-- ---------- สลิปโอนเงิน ----------
create table if not exists slips (
  id bigint generated always as identity primary key,
  line_user_id text not null,
  message_id text,
  media_url text,
  ocr jsonb,                                  -- ผลดิบจาก EasySlip
  amount numeric,
  ref text,                                   -- transRef จากสลิป (กันซ้ำ)
  bank text,
  slip_date text,
  status text not null default 'new',         -- new | review | verified | rejected
  matched boolean,                            -- ยอดตรงกับราคาหลักสูตรไหม
  auto_note text,                             -- หมายเหตุจากระบบตรวจอัตโนมัติ
  dup_ref text,                               -- ref เดิม ถ้าเป็นสลิปซ้ำ
  expected_course text,
  note text,                                  -- หมายเหตุแอดมิน
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists slips_status_idx on slips (status, created_at desc);
create index if not exists slips_user_idx on slips (line_user_id, created_at desc);
-- กันสลิปซ้ำ: ref ต้องไม่ซ้ำ (null ได้หลายแถว — เคสอ่าน ref ไม่ได้ / สลิปซ้ำ)
create unique index if not exists slips_ref_uq on slips (ref) where ref is not null;

-- ---------- RLS: ปิด (เข้าผ่าน service_role เท่านั้น) ----------
do $$ declare r record; begin
  for r in select unnest(array['postback_actions','app_settings','payment_accounts','slips']) as t loop
    execute format('alter table public.%I enable row level security', r.t);
  end loop;
end $$;

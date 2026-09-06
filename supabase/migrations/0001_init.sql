-- ============================================================
-- LINE Console — Supabase schema
-- รันใน Supabase Dashboard > SQL Editor (หรือ supabase db push)
-- ============================================================

create extension if not exists "pgcrypto";

-- ---------- admins: LINE userId ที่เข้าใช้เว็บได้ ----------
create table if not exists admins (
  line_user_id  text primary key,
  name          text,
  role          text not null default 'admin',   -- 'owner' | 'admin' | 'viewer'
  added_at      timestamptz not null default now()
);

-- ---------- line_users: เพื่อน/ผู้ติดตามทั้งหมด ----------
create table if not exists line_users (
  line_user_id          text primary key,
  display_name          text,
  picture_url           text,
  status_message        text,
  language              text,
  is_following          boolean not null default true,
  followed_at           timestamptz,
  unfollowed_at         timestamptz,
  current_rich_menu_id  text,
  rich_menu_name        text,
  rich_menu_status      text,               -- 'assigned' | 'none' | 'error:xxx'
  rich_menu_checked_at  timestamptz,
  source                text,               -- 'webhook' | 'import' | 'followers_api'
  note                  text,
  tags                  text[] default '{}',
  first_seen_at         timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create index if not exists line_users_following_idx on line_users (is_following);
create index if not exists line_users_richmenu_idx  on line_users (current_rich_menu_id);
create index if not exists line_users_tags_idx      on line_users using gin (tags);

-- ---------- webhook_events: log จาก LINE webhook ----------
create table if not exists webhook_events (
  id            bigint generated always as identity primary key,
  event_type    text not null,              -- follow | unfollow | message | postback | ...
  line_user_id  text,
  message_type  text,
  text          text,
  payload       jsonb not null,
  created_at    timestamptz not null default now()
);
create index if not exists webhook_events_user_idx on webhook_events (line_user_id, created_at desc);
create index if not exists webhook_events_type_idx on webhook_events (event_type, created_at desc);

-- ---------- rich_menus: cache รายการ rich menu ----------
create table if not exists rich_menus (
  rich_menu_id   text primary key,
  name           text,
  chat_bar_text  text,
  selected       boolean default false,
  size           jsonb,
  areas          jsonb,
  is_default     boolean default false,
  image_synced   boolean default false,
  synced_at      timestamptz not null default now()
);

-- ---------- broadcasts: ประวัติการส่งข้อความ ----------
create table if not exists broadcasts (
  id             bigint generated always as identity primary key,
  actor          text references admins(line_user_id),
  kind           text not null,             -- broadcast | multicast | push | narrowcast
  target_count   int,
  messages       jsonb not null,
  line_request_id text,
  status         text not null default 'sent',  -- sent | failed
  error          text,
  created_at     timestamptz not null default now()
);
create index if not exists broadcasts_created_idx on broadcasts (created_at desc);

-- ---------- operations: audit log ของทุก action ----------
create table if not exists operations (
  id            bigint generated always as identity primary key,
  actor         text,
  action        text not null,             -- richmenu.assign | richmenu.sync | users.import | ...
  params        jsonb,
  result        jsonb,
  status        text not null default 'ok',
  created_at    timestamptz not null default now()
);
create index if not exists operations_created_idx on operations (created_at desc);

-- ---------- stats_daily: snapshot สถิติรายวัน ----------
create table if not exists stats_daily (
  day               date primary key,
  followers         int,
  targeted_reaches  int,
  blocks            int,
  broadcast_count   int,
  push_count        int,
  quota_type        text,
  quota_limit       int,
  quota_used        int,
  raw               jsonb,
  captured_at       timestamptz not null default now()
);

-- ============================================================
-- RLS: ปิดการเข้าถึงจากภายนอกทั้งหมด
-- (ทุก access ผ่าน Python API ด้วย service_role key เท่านั้น)
-- ============================================================
alter table admins          enable row level security;
alter table line_users      enable row level security;
alter table webhook_events  enable row level security;
alter table rich_menus      enable row level security;
alter table broadcasts      enable row level security;
alter table operations      enable row level security;
alter table stats_daily     enable row level security;
-- ไม่สร้าง policy = anon/authenticated เข้าไม่ได้เลย; service_role bypass RLS อยู่แล้ว

-- ---------- seed: ใส่ owner คนแรก (แก้ค่าก่อนรัน) ----------
-- insert into admins (line_user_id, name, role) values ('Uxxxxxxxxxxxxxxxx', 'Owner', 'owner')
--   on conflict (line_user_id) do nothing;

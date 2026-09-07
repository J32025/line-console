-- ============================================================
-- LINE Console — full schema (idempotent)
-- รันใน Supabase Dashboard > SQL Editor  หรือ  supabase db push
-- ============================================================
create extension if not exists "pgcrypto";
create extension if not exists pg_cron;
create extension if not exists pg_net with schema extensions;

-- ---------- admins ----------
create table if not exists admins (
  line_user_id text primary key,
  name text, role text not null default 'admin',   -- owner | admin | viewer
  added_at timestamptz not null default now()
);

-- ---------- line_users (ผู้ติดตาม + custom fields + inbox state) ----------
create table if not exists line_users (
  line_user_id text primary key,
  display_name text, picture_url text, status_message text, language text,
  is_following boolean not null default true,
  followed_at timestamptz, unfollowed_at timestamptz, first_followed_at timestamptz,
  follow_count int not null default 0, block_count int not null default 0,
  current_rich_menu_id text, rich_menu_name text, rich_menu_status text, rich_menu_checked_at timestamptz,
  source text, note text, tags text[] default '{}', custom jsonb not null default '{}'::jsonb,
  auto_reply_paused boolean not null default false, assigned_to text,
  last_message_at timestamptz, last_message_text text, unread int not null default 0,
  last_event_at timestamptz,
  first_seen_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists line_users_following_idx on line_users (is_following);
create index if not exists line_users_richmenu_idx  on line_users (current_rich_menu_id);
create index if not exists line_users_tags_idx      on line_users using gin (tags);
create index if not exists line_users_lastmsg_idx   on line_users (last_message_at desc nulls last);

-- ---------- field_defs (นิยาม custom fields) ----------
create table if not exists field_defs (
  key text primary key, label text not null, type text not null default 'text',
  options text[] default '{}', sort int default 0, created_at timestamptz not null default now()
);

-- ---------- webhook_events ----------
create table if not exists webhook_events (
  id bigint generated always as identity primary key,
  event_type text not null, line_user_id text, message_type text, text text,
  reply_token text, postback_data text, auto_replied boolean default false,
  webhook_event_id text, event_ts timestamptz, is_redelivery boolean default false,
  payload jsonb not null, created_at timestamptz not null default now()
);
create index if not exists webhook_events_user_idx on webhook_events (line_user_id, created_at desc);
create index if not exists webhook_events_type_idx on webhook_events (event_type, created_at desc);

-- ---------- messages (inbox thread: in/out) ----------
create table if not exists messages (
  id bigint generated always as identity primary key,
  line_user_id text not null, direction text not null,   -- in | out
  by text,                                               -- user | auto | automation | system | <adminUid>
  msg_type text, text text, payload jsonb,
  created_at timestamptz not null default now()
);
create index if not exists messages_thread_idx on messages (line_user_id, created_at desc);

-- ---------- follow_history ----------
create table if not exists follow_history (
  id bigint generated always as identity primary key,
  line_user_id text not null, action text not null,      -- follow | unfollow
  is_unblocked boolean, event_ts timestamptz, created_at timestamptz not null default now()
);
create index if not exists follow_history_uid_idx on follow_history (line_user_id, created_at desc);

-- ---------- rich_menus (cache) ----------
create table if not exists rich_menus (
  rich_menu_id text primary key, name text, chat_bar_text text, selected boolean default false,
  size jsonb, areas jsonb, is_default boolean default false, image_synced boolean default false,
  synced_at timestamptz not null default now()
);

-- ---------- auto_replies ----------
create table if not exists auto_replies (
  id bigint generated always as identity primary key,
  enabled boolean not null default true, name text,
  trigger text not null default 'text',    -- text|fallback|follow|postback|sticker|image|video|audio|file|location|beacon
  match_type text not null default 'contains',
  keywords text[] not null default '{}', messages jsonb not null,
  priority int not null default 0, hits int not null default 0, last_hit_at timestamptz,
  created_by text, created_at timestamptz not null default now()
);

-- ---------- automations (drip flow) ----------
create table if not exists automations (
  id bigint generated always as identity primary key,
  name text not null, enabled boolean not null default true,
  trigger text not null default 'follow', trigger_config jsonb default '{}'::jsonb,
  steps jsonb not null default '[]'::jsonb,   -- [{delayHours, delayMinutes, messages[]}]
  runs int not null default 0, created_by text, created_at timestamptz not null default now()
);
create table if not exists automation_runs (
  id bigint generated always as identity primary key,
  automation_id bigint not null, line_user_id text not null, step_idx int not null default 0,
  run_at timestamptz not null, status text not null default 'pending',
  created_at timestamptz not null default now()
);
create index if not exists automation_runs_due_idx on automation_runs (status, run_at);
create unique index if not exists automation_runs_uq on automation_runs (automation_id, line_user_id, step_idx);

-- ---------- segments / message_templates ----------
create table if not exists segments (
  id bigint generated always as identity primary key,
  name text not null, description text, filter jsonb not null default '{}'::jsonb,
  kind text not null default 'db', last_count int, created_by text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists message_templates (
  id bigint generated always as identity primary key,
  name text not null, messages jsonb not null, created_by text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

-- ---------- broadcasts / scheduled_jobs ----------
create table if not exists broadcasts (
  id bigint generated always as identity primary key,
  actor text, kind text not null, target_count int, messages jsonb not null,
  line_request_id text, status text not null default 'sent', error text, ab_group text,
  created_at timestamptz not null default now()
);
create index if not exists broadcasts_created_idx on broadcasts (created_at desc);

create table if not exists scheduled_jobs (
  id bigint generated always as identity primary key,
  kind text not null,                       -- broadcast | richmenu_default
  run_at timestamptz not null, payload jsonb not null,
  repeat text, label text,                  -- daily | weekly | biweekly | monthly
  status text not null default 'pending', result jsonb,
  created_by text, created_at timestamptz not null default now()
);
create index if not exists scheduled_jobs_due_idx on scheduled_jobs (status, run_at);

-- ---------- link tracking ----------
create table if not exists short_links (
  code text primary key, target text not null, label text, broadcast_id bigint,
  clicks int not null default 0, created_by text, created_at timestamptz not null default now()
);
create table if not exists link_clicks (
  id bigint generated always as identity primary key,
  code text not null, line_user_id text, target text not null, broadcast_id bigint,
  clicked_at timestamptz not null default now()
);
create index if not exists link_clicks_code_idx on link_clicks (code, clicked_at desc);

-- ---------- liff_apps ----------
create table if not exists liff_apps (
  liff_id text primary key, name text, size text, endpoint_url text, description text,
  scopes text[] default '{}', bot_prompt text, features jsonb default '{}'::jsonb,
  module_mode boolean default false, is_primary boolean default false,
  channel_id text, note text, created_by text, updated_at timestamptz not null default now()
);

-- ---------- operations (audit) / stats_daily / backups ----------
create table if not exists operations (
  id bigint generated always as identity primary key,
  actor text, action text not null, params jsonb, result jsonb,
  status text not null default 'ok', created_at timestamptz not null default now()
);
create index if not exists operations_created_idx on operations (created_at desc);

create table if not exists stats_daily (
  day date primary key, followers int, targeted_reaches int, blocks int,
  broadcast_count int, push_count int, quota_type text, quota_limit int, quota_used int,
  raw jsonb, captured_at timestamptz not null default now()
);
create table if not exists backups (
  id bigint generated always as identity primary key,
  day date not null unique, tables jsonb not null, size_kb int,
  created_at timestamptz not null default now()
);

-- ============================================================
-- RLS: ปิดทุกตาราง (เข้าผ่าน Python service_role เท่านั้น)
-- ============================================================
do $$ declare r record; begin
  for r in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', r.tablename);
  end loop;
end $$;

-- ============================================================
-- pg_cron jobs — แก้ <APP_URL> และ <CRON_SECRET> ก่อนรัน
-- ============================================================
-- select cron.schedule('sync-richmenu-5min','*/5 * * * *', $$ select net.http_post(url:='<APP_URL>/api/cron/sync-richmenu?key=<CRON_SECRET>', timeout_milliseconds:=58000); $$);
-- select cron.schedule('run-scheduled-5min','*/5 * * * *', $$ select net.http_post(url:='<APP_URL>/api/cron/run-scheduled?key=<CRON_SECRET>', timeout_milliseconds:=55000); $$);
-- select cron.schedule('run-automations-5min','*/5 * * * *', $$ select net.http_post(url:='<APP_URL>/api/cron/run-automations?key=<CRON_SECRET>', timeout_milliseconds:=55000); $$);
-- select cron.schedule('snapshot-stats-daily','5 1 * * *', $$ select net.http_post(url:='<APP_URL>/api/cron/snapshot-stats?key=<CRON_SECRET>', timeout_milliseconds:=30000); $$);
-- select cron.schedule('backup-daily','15 1 * * *', $$ select net.http_post(url:='<APP_URL>/api/cron/backup?key=<CRON_SECRET>', timeout_milliseconds:=50000); $$);

-- Storage bucket 'media' (public, 10MB) — สร้างผ่าน Dashboard > Storage หรือ API

-- seed owner:
-- insert into admins (line_user_id, name, role) values ('Uxxxx','Owner','owner') on conflict do nothing;

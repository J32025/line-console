-- ============================================================
-- 0010 — kb_articles: คลังความรู้ (แหล่งข้อมูลเดียวให้ Gemini + auto-reply + inbox)
-- ============================================================
create table if not exists kb_articles (
  id bigint generated always as identity primary key,
  title text not null,
  body text not null,
  keywords text[] not null default '{}',
  category text,
  enabled boolean not null default true,
  hits int not null default 0,
  updated_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists kb_enabled_idx on kb_articles (enabled);
alter table kb_articles enable row level security;

notify pgrst, 'reload schema';

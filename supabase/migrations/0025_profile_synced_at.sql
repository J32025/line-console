-- ============================================================
-- 0025 — เวลาที่ดึงชื่อ/รูปจาก LINE ครั้งล่าสุด (ใช้ซิงค์ชื่ออัตโนมัติ) · รันซ้ำได้
-- รันใน Supabase SQL Editor
-- ============================================================
alter table line_users add column if not exists profile_synced_at timestamptz;
create index if not exists line_users_profile_sync_idx
  on line_users (profile_synced_at asc nulls first) where is_following;

notify pgrst, 'reload schema';

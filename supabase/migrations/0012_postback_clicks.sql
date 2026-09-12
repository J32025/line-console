-- 0012_postback_clicks.sql
-- เก็บว่า userId ไหนคลิกปุ่ม postback จาก broadcast ไหน (แนบรหัส broadcast ต่อท้าย data ตอนส่ง
-- แล้วแกะออกตอนรับ postback event กลับมาที่ webhook — ดู api/index.py _split_postback_data)

create table if not exists postback_clicks (
  id bigint generated always as identity primary key,
  broadcast_id bigint,
  line_user_id text not null,
  data text,
  clicked_at timestamptz not null default now()
);
create index if not exists postback_clicks_bc_idx on postback_clicks (broadcast_id);
create index if not exists postback_clicks_uid_idx on postback_clicks (line_user_id);
create index if not exists postback_clicks_created_idx on postback_clicks (clicked_at desc);

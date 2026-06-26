-- RTLCopilot — Supabase Schema
-- Run this entire file in your Supabase project's SQL editor
-- Supabase dashboard → SQL Editor → New query → paste → Run

-- ── Projects ──────────────────────────────────────────────────────────────────
-- Stores user canvas designs (nodes, edges, verilog files)

create table if not exists projects (
  id          uuid default gen_random_uuid() primary key,
  user_id     text not null,
  name        text not null default 'Untitled Project',
  description text default '',
  canvas      jsonb not null default '{}',
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

alter table projects enable row level security;

create policy "Users manage own projects" on projects
  for all using (auth.uid()::text = user_id);

create index if not exists projects_user_id_idx on projects (user_id);

-- Auto-update updated_at on every update
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger projects_updated_at
  before update on projects
  for each row execute function update_updated_at();


-- ── Custom Blocks ─────────────────────────────────────────────────────────────
-- Stores user-created custom Verilog blocks from the Custom Block builder

create table if not exists custom_blocks (
  id          uuid default gen_random_uuid() primary key,
  user_id     text not null,
  name        text not null,
  description text default '',
  schema      jsonb not null default '{}',
  verilog     text not null default '',
  ports       jsonb not null default '[]',
  block_type  text not null,
  created_at  timestamptz default now()
);

alter table custom_blocks enable row level security;

create policy "Users manage own custom blocks" on custom_blocks
  for all using (auth.uid()::text = user_id);

create index if not exists custom_blocks_user_id_idx on custom_blocks (user_id);


-- ── Feedback ──────────────────────────────────────────────────────────────────
-- Stores in-app feedback submissions

create table if not exists feedback (
  id         uuid default gen_random_uuid() primary key,
  user_id    text,
  rating     int,
  text       text default '',
  trigger    text default '',
  created_at timestamptz default now()
);

-- Feedback is write-only for users (insert only, no read)
alter table feedback enable row level security;

create policy "Anyone can submit feedback" on feedback
  for insert with check (true);


-- ── Notes ─────────────────────────────────────────────────────────────────────
-- Auth is handled by Supabase built-in auth (supabase.auth.*)
-- No additional auth tables are needed.
-- Make sure Google OAuth is enabled in your Supabase project:
-- Authentication → Providers → Google → Enable

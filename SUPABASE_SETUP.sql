-- SUPABASE_SETUP.sql
-- Jobsy — one-time database setup.
--
-- services/persistence_service.py has told users to "run SUPABASE_SETUP.sql
-- once in the Supabase SQL Editor" as step 3 of setup since commit 4.1, and
-- docs/ROADMAP.md lists it twice as referenced-but-absent. This is that file.
--
-- Run order:
--   1. This file                              — session persistence (below)
--   2. supabase/migrations/0001_reference_library.sql — the reference library
--
-- Step 2 is only needed once the reference library moves into the database
-- (Phase 0 of docs/PLAN-supabase-migration.md). Session persistence below
-- works on its own and is what the app uses today.

-- ───────────────────────────────────────────────── session persistence ──
--
-- Shape derived from persistence_service.py's own calls, which are the only
-- thing that has ever defined it:
--   save_session()  upserts {session_code, org_label, payload}
--   load_session()  selects payload, org_label, created_at  .eq(session_code)
--   health_check()  selects session_code with count='exact' limit 1
--
-- session_code is therefore the natural key: upsert needs a unique constraint
-- on it or it inserts a duplicate row every save, and .single() in
-- load_session() raises if more than one row comes back.

create table if not exists jobsy_sessions (
  id           uuid primary key default gen_random_uuid(),
  session_code text not null unique,
  org_label    text not null default '',
  payload      jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists jobsy_sessions_code_idx on jobsy_sessions (session_code);

-- load_session() reads created_at and expects it to mean "when this session was
-- saved". An upsert of an existing code updates rather than inserts, so without
-- this the timestamp would be the code's first-ever use, not the current state.
create or replace function jobsy_sessions_touch() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists jobsy_sessions_set_updated_at on jobsy_sessions;
create trigger jobsy_sessions_set_updated_at
  before update on jobsy_sessions
  for each row execute function jobsy_sessions_touch();

-- ────────────────────────────────────────────────────────────────── RLS ──
--
-- A session code is a shareable secret — anyone holding it is meant to be able
-- to load that session, and there are no user accounts to check it against. So
-- the protection here is the code's unguessability, not a policy.
--
-- RLS is on with no anon/authenticated policy, which means the app must reach
-- this table with the service key. Jobsy is server-rendered Streamlit, so its
-- SUPABASE_KEY is a server-side secret and that is a legitimate choice — unlike
-- in a browser app, where it would hand every visitor the whole table.
--
-- If you instead put an anon key in secrets.toml, every call here fails closed
-- and the app falls back to no persistence. That is the safe failure, but it is
-- silent: check the Library panel's database status if sessions stop saving.

alter table jobsy_sessions enable row level security;

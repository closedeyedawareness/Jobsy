-- 0007_partners_users_and_membership.sql
--
-- Stage 1 of docs/PLAN-whitelabel-tenancy.md: the vocabulary the fence needs.
-- No policy is written here and no behaviour changes. 0008 turns it on.
--
-- WHAT 0001 ALREADY DID, so this migration is not mistaken for a redo
--
-- The client level exists. `orgs` is a table, and `org_id uuid not null
-- references orgs(id)` is threaded through all 20 reference tables with an
-- index on each, because 0001 judged that "retrofitting a tenant key onto
-- populated tables with live foreign keys is the kind of migration that goes
-- wrong". That judgement is now worth a lot: the expensive half of tenancy was
-- paid for a year before it was needed, on empty tables.
--
-- So this migration adds only what is genuinely missing:
--
--   1. the level ABOVE a client   — partners, because the app is being resold
--   2. the level BELOW a client   — memberships, because nothing said which
--                                   human may reach which org
--   3. the table that holds the actual rosters — jobsy_sessions, which was
--      never created in this database at all (see below)
--
-- WHAT IS ACTUALLY IN THE DATABASE, checked 2026-08-31, not assumed
--
--   orgs               1     the 'default' org seeded by 0001
--   jobs              81     reference library, imported
--   salary_bands      45     reference library, imported
--   library_audit  10468     the trail of those imports
--   employees          0
--   auth.users         0     Auth has never been used
--   jobsy_sessions     —     DOES NOT EXIST
--
-- Two consequences, both good. There is no personal data in this database, so
-- the fence is being built before anything lands behind it rather than after —
-- which is the only comfortable order. And jobsy_sessions can be created
-- correctly the first time instead of altered later.
--
-- On that last point: SUPABASE_SETUP.sql defines a jobsy_sessions with no
-- tenant key and instructs the operator to run it by hand in the SQL editor.
-- It was never run here. That file is superseded by section 4 below — a table
-- the app depends on belongs in the migration series with everything else, not
-- in a manual step that can be skipped, which is demonstrably what happened.

-- ─────────────────────────────────────────────────────── 1. the partner ──
--
-- A partner is the white-label reseller: they own an instance, put their name
-- on it, and bring their own clients. `orgs` stays the client — the end company
-- whose people are analysed — so no existing column changes meaning.

create table if not exists partners (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique,
  name        text not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

drop trigger if exists partners_set_updated_at on partners;
create trigger partners_set_updated_at
  before update on partners
  for each row execute function set_updated_at();

-- Mirrors 0001's 'default' org: one partner so that every existing row has a
-- parent and the not-null below can be taken in the same migration.
insert into partners (slug, name)
values ('default', 'Default partner')
on conflict (slug) do nothing;

alter table orgs add column if not exists partner_id uuid references partners(id) on delete cascade;

update orgs
   set partner_id = (select id from partners where slug = 'default')
 where partner_id is null;

-- Safe to take now precisely because the update above ran in this transaction;
-- an org with no partner is a row nothing can authorise access to.
alter table orgs alter column partner_id set not null;

create index if not exists orgs_partner_idx on orgs (partner_id);

-- ───────────────────────────────────────────────────── 2. the membership ──
--
-- A membership is the only thing that grants a human access to data. It is
-- scoped to EITHER a partner or a client, never both:
--
--   partner-scoped  — the reseller's own staff. One row reaches every client
--                     they have. Without this a consultant with forty clients
--                     needs forty rows kept in step, and the row somebody
--                     forgets to delete is the one that matters.
--   org-scoped      — the client's own HR staff. One row, one company.
--
-- Roles are constrained to the scope that can hold them, so 'partner_admin on
-- one client' and 'viewer across an entire partner' are both unrepresentable
-- rather than merely discouraged.

create table if not exists memberships (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  partner_id  uuid references partners(id) on delete cascade,
  org_id      uuid references orgs(id)     on delete cascade,
  role        text not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  constraint memberships_one_scope
    check (num_nonnulls(partner_id, org_id) = 1),

  constraint memberships_role_fits_scope
    check (
      (partner_id is not null and role in ('partner_admin', 'partner_analyst'))
      or
      (org_id is not null and role in ('client_admin', 'analyst', 'viewer'))
    )
);

drop trigger if exists memberships_set_updated_at on memberships;
create trigger memberships_set_updated_at
  before update on memberships
  for each row execute function set_updated_at();

-- Partial uniques rather than one composite: a null in a composite unique does
-- not collide, so (user, null org) would admit unlimited duplicate partner rows.
create unique index if not exists memberships_user_org_uniq
  on memberships (user_id, org_id) where org_id is not null;
create unique index if not exists memberships_user_partner_uniq
  on memberships (user_id, partner_id) where partner_id is not null;

create index if not exists memberships_user_idx on memberships (user_id);
create index if not exists memberships_org_idx  on memberships (org_id);

-- ──────────────────────────────────────────── 3. what a policy will ask ──
--
-- These are the functions 0008's policies call. Three deliberate choices:
--
-- SECURITY DEFINER, because memberships will itself carry RLS in 0008. A policy
--   on jobs that reads memberships directly would be filtered by memberships'
--   own policy, which reads memberships — infinite recursion, and Postgres
--   reports it as a stack-depth error a long way from the cause. A definer
--   function reads the table as its owner and ends the loop.
--
-- A PRIVATE SCHEMA, because 0005 had to revoke execute on log_library_change()
--   after finding PostgREST had published it at /rest/v1/rpc/. Every function
--   in `public` is an API endpoint by default. PostgREST serves only the
--   schemas it is configured for, so `app` is unreachable over HTTP while
--   remaining perfectly callable from inside a policy.
--
-- search_path PINNED, the finding 0005 fixed on two other functions. A definer
--   function without it resolves `memberships` against the caller's
--   search_path, which the caller chooses.

create schema if not exists app;
grant usage on schema app to authenticated, service_role;

-- Every org the current user may reach: their own client memberships, plus
-- every client belonging to a partner they work for.
create or replace function app.member_org_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
  select m.org_id
    from memberships m
   where m.user_id = auth.uid()
     and m.org_id is not null
  union
  select o.id
    from memberships m
    join orgs o on o.partner_id = m.partner_id
   where m.user_id = auth.uid()
     and m.partner_id is not null
$$;

-- The predicate the policies use. Kept as its own function so the policy text
-- reads as one condition and every table asks the identical question.
create or replace function app.can_access_org(p_org uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
  select p_org is not null
     and exists (select 1 from app.member_org_ids() m where m = p_org)
$$;

-- True when the user administers the org: directly, or as staff of its partner.
create or replace function app.is_org_admin(p_org uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
  select exists (
    select 1 from memberships m
     where m.user_id = auth.uid()
       and m.org_id = p_org
       and m.role = 'client_admin'
  ) or exists (
    select 1 from memberships m
      join orgs o on o.partner_id = m.partner_id
     where m.user_id = auth.uid()
       and o.id = p_org
       and m.role = 'partner_admin'
  )
$$;

-- authenticated must EXECUTE these: a policy is evaluated as the querying role,
-- so a function it cannot call fails the query rather than denying the row.
-- anon is deliberately not granted — an unauthenticated caller has no identity
-- for auth.uid() to return and nothing here would tell it anything anyway.
grant execute on function app.member_org_ids()      to authenticated, service_role;
grant execute on function app.can_access_org(uuid)  to authenticated, service_role;
grant execute on function app.is_org_admin(uuid)    to authenticated, service_role;
revoke execute on function app.member_org_ids()     from public;
revoke execute on function app.can_access_org(uuid) from public;
revoke execute on function app.is_org_admin(uuid)   from public;

-- ────────────────────────────────────────────── 4. the sessions the app saves ──
--
-- Supersedes the definition in SUPABASE_SETUP.sql, which was never applied to
-- this database. Same shape, so persistence_service.py keeps working unchanged,
-- plus the two columns it should always have had.
--
-- This is the table that holds client rosters: _capture_session() in ui/app.py
-- serialises upload_df — employee id, name, salary, gender, birth or start date
-- — into `payload`. It is therefore the table where the fence matters most, and
-- the one where org_id must exist before a single row does. It now does.
--
-- session_code stays GLOBALLY unique rather than unique per org. The app upserts
-- on it and loads with .eq(session_code).single(), so a code that resolved to two
-- rows would raise; and a code that is unique across the whole system cannot
-- accidentally address another client's session even before 0008's policies land.

create table if not exists jobsy_sessions (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references orgs(id) on delete cascade,
  session_code text not null unique,
  org_label    text not null default '',
  payload      jsonb not null default '{}'::jsonb,
  created_by   uuid references auth.users(id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists jobsy_sessions_code_idx on jobsy_sessions (session_code);
create index if not exists jobsy_sessions_org_idx  on jobsy_sessions (org_id);

drop trigger if exists jobsy_sessions_set_updated_at on jobsy_sessions;
create trigger jobsy_sessions_set_updated_at
  before update on jobsy_sessions
  for each row execute function set_updated_at();

-- org_label is now derivable from orgs.name and is kept only because
-- load_session() selects it and save_session() writes it. It is a caption, and
-- after 0008 it stops being the only thing distinguishing one client's data
-- from another's — which is all it has ever been.

-- ───────────────────────────────────────────────────────────────── RLS ──
--
-- Enabled with no policy, for exactly the reason 0001 and 0005 both give: the
-- app still connects with the secret key, which bypasses RLS by definition, so
-- a policy written now would be untested and unenforced at the same time. It
-- lands in 0008 together with the change that stops using that key, because
-- either one alone is a false sense of security:
--
--   policy without the key change  — written, never exercised, believed
--   key change without the policy  — every query denied, app dead
--
-- Until then these tables behave exactly like the other 25: reachable by the
-- secret key, reachable by nobody else.

alter table partners        enable row level security;
alter table memberships     enable row level security;
alter table jobsy_sessions  enable row level security;

-- 0003's finding applies to every new table, not just the audit trail: Supabase
-- grants all privileges to anon, authenticated, service_role and postgres BY
-- NAME, so `revoke ... from public` would be decorative here too. anon is a
-- browser with no session; it has no business reaching any of these, and RLS
-- alone would be the only thing stopping it once policies exist. Belt and
-- braces, revoked by name.
revoke all on partners       from anon;
revoke all on memberships    from anon;
revoke all on jobsy_sessions from anon;

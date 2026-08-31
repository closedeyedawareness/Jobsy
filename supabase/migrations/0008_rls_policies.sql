-- 0008_rls_policies.sql
--
-- Stage 2 of docs/PLAN-whitelabel-tenancy.md: the fence, turned on.
--
-- This migration is HALF of a change. The other half is in the application —
-- auth_service.py connecting as the signed-in user instead of with the secret
-- key. Shipping either alone is worse than shipping neither:
--
--   policies without the key change  — written, never exercised, believed
--   key change without the policies  — every query denied, app dead
--
-- 0001 sketched what this would look like:
--
--     create policy org_isolation on <table> for all to authenticated
--       using (org_id = (auth.jwt() ->> 'org_id')::uuid)
--
-- It is not what this does, deliberately. A single org claim baked into the
-- token cannot express a consultant who works across eleven clients: every
-- switch would need a fresh token, and the claim itself becomes the fence —
-- one stale or wrongly-minted token and the boundary is gone. Here the token
-- establishes only WHO you are; the memberships table decides what that gets
-- you, and it is read fresh on every query. Revoking access is a DELETE that
-- takes effect immediately, not a wait for a token to expire.
--
-- ── THE SHARED LIBRARY PROBLEM ────────────────────────────────────────────
--
-- Naively "you see rows for orgs you belong to" breaks the product on day one.
-- The reference library — 81 jobs, 45 salary bands, the grades, the CAO
-- crosswalk — lives in the 'default' org that 0001 seeded. It is not any
-- client's data; it is the thing being sold. A new client belongs to their own
-- org, so a membership-only rule would show them an empty library and a broken
-- app.
--
-- So an org can be marked a LIBRARY SOURCE: its reference rows are readable by
-- every signed-in user, while remaining writable only through the importer.
-- Client data tables get no such exemption — employees and jobsy_sessions are
-- never shared content, and are membership-only with no way to opt out.
--
-- Per-client libraries (F-3) later become "some orgs are library sources for
-- their own partner only". The flag is where that goes; nothing else moves.

-- ────────────────────────────────────────────── 1. what is shared ──

alter table orgs add column if not exists is_library_source boolean not null default false;

comment on column orgs.is_library_source is
  'Reference rows in this org are readable by every authenticated user, not just '
  'its members. The product''s own content, not a client''s data. Client tables '
  '(employees, jobsy_sessions) ignore this flag by design.';

-- The org 0001 seeded holds the imported library, so it is the first one.
update orgs set is_library_source = true where slug = 'default';

create or replace function app.library_org_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
  select id from orgs where is_library_source
$$;

-- Read test for shared content: your orgs, plus the library.
create or replace function app.can_read_org(p_org uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
  -- auth.uid() is not null is load-bearing, not defensive noise. Without it a
  -- token carrying no subject reads the whole reference library: 81 jobs, the
  -- salary bands, the CAO crosswalk. That is not a client's personal data, but
  -- it is the product being resold, and an identity-less session has no claim
  -- on it. Caught by 0008's own test, which asserted this before it was true.
  select p_org is not null
     and auth.uid() is not null
     and (
       exists (select 1 from app.member_org_ids()  m where m = p_org)
       or
       exists (select 1 from app.library_org_ids() l where l = p_org)
     )
$$;

-- Write test for shared content: admin of the org, and never the library. The
-- library changes through the importer, which authenticates as service_role and
-- is not subject to any of this.
create or replace function app.can_write_org(p_org uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
  select app.is_org_admin(p_org)
     and not exists (select 1 from app.library_org_ids() l where l = p_org)
$$;

grant execute on function app.library_org_ids()   to authenticated, service_role;
grant execute on function app.can_read_org(uuid)  to authenticated, service_role;
grant execute on function app.can_write_org(uuid) to authenticated, service_role;
revoke execute on function app.library_org_ids()   from public;
revoke execute on function app.can_read_org(uuid)  from public;
revoke execute on function app.can_write_org(uuid) from public;

-- ──────────────────────────────────── 2. the reference tables ──
--
-- Same 20 tables 0001 threaded org_id through, minus employees, which is client
-- data and handled separately below. Written as a loop for the reason 0001 gave:
-- identical on every table, by construction, so no table can be forgotten and
-- none can quietly differ.

do $$
declare
  t text;
  ref_tables text[] := array[
    'jobs', 'job_profiles', 'salary_bands', 'title_mapping', 'career_paths',
    'levels', 'categories', 'skills', 'competency_levels',
    'role_skill_map', 'job_grades', 'industries', 'industry_salary_factors',
    'industry_skills', 'seniority_levels', 'skill_proficiency',
    'benefits_catalog', 'benefits_observations', 'level_benefits_factors'
  ];
begin
  foreach t in array ref_tables loop
    execute format('drop policy if exists %I on %I', t || '_read', t);
    execute format($p$
      create policy %I on %I for select to authenticated
        using (app.can_read_org(org_id))
    $p$, t || '_read', t);

    execute format('drop policy if exists %I on %I', t || '_write', t);
    execute format($p$
      create policy %I on %I for all to authenticated
        using      (app.can_write_org(org_id))
        with check (app.can_write_org(org_id))
    $p$, t || '_write', t);
  end loop;
end $$;

-- ─────────────────────────────────────── 3. the client data ──
--
-- No library exemption, no read/write split by content type: if you are not a
-- member of the org, the row does not exist as far as you are concerned.
--
-- `using` governs which rows are visible to select, update and delete;
-- `with check` governs what insert and update may produce. Both are required —
-- `using` alone would let a member of org A insert a row stamped org B, which is
-- the one direction people forget.

drop policy if exists employees_isolation on employees;
create policy employees_isolation on employees for all to authenticated
  using      (app.can_access_org(org_id))
  with check (app.can_access_org(org_id));

drop policy if exists jobsy_sessions_isolation on jobsy_sessions;
create policy jobsy_sessions_isolation on jobsy_sessions for all to authenticated
  using      (app.can_access_org(org_id))
  with check (app.can_access_org(org_id));

-- ──────────────────────────── 4. the tenancy tables themselves ──

-- An org is visible if you belong to it, or if it is the shared library (the
-- app joins to it for names). Nobody edits orgs through the API.
drop policy if exists orgs_read on orgs;
create policy orgs_read on orgs for select to authenticated
  using (app.can_read_org(id));

-- A partner is visible to its own staff and to the staff of its clients, so the
-- white-label name and logo can be read to brand the page.
drop policy if exists partners_read on partners;
create policy partners_read on partners for select to authenticated
  using (
    exists (select 1 from memberships m
             where m.user_id = auth.uid() and m.partner_id = partners.id)
    or
    exists (select 1 from orgs o
             where o.partner_id = partners.id and app.can_access_org(o.id))
  );

-- You may always see your own memberships — otherwise the app cannot tell you
-- which clients you have. Beyond that, only admins of the org concerned, so a
-- viewer at one client cannot enumerate that client's staff list.
drop policy if exists memberships_read on memberships;
create policy memberships_read on memberships for select to authenticated
  using (
    user_id = auth.uid()
    or (org_id is not null and app.is_org_admin(org_id))
  );

-- Granting access is an administrative act. It happens through tools/manage_users.py
-- as service_role, never from a browser session, so there is deliberately no
-- insert/update/delete policy here: the API cannot create a membership at all.

-- Provenance is readable with the content it describes.
drop policy if exists library_revisions_read on library_revisions;
create policy library_revisions_read on library_revisions for select to authenticated
  using (app.can_read_org(org_id));

-- The audit trail is readable by admins of the org it concerns. It stays
-- append-only-by-trigger from 0003; no policy grants a write, and the roles were
-- revoked by name there.
drop policy if exists library_audit_read on library_audit;
create policy library_audit_read on library_audit for select to authenticated
  using (org_id is not null and app.is_org_admin(org_id));

-- ────────────────────────────────────────────────── 5. anon ──
--
-- Not one policy above names anon, so an unauthenticated caller holding the
-- publishable key reaches nothing: RLS denies by default and there is no
-- permissive policy for that role anywhere. The revokes are belt and braces,
-- for the reason 0003 established — Supabase grants privileges to anon BY NAME,
-- so a `revoke ... from public` would not touch them.

revoke all on employees          from anon;
revoke all on orgs               from anon;
revoke all on library_revisions  from anon;
revoke all on library_audit      from anon;

do $$
declare t text;
begin
  foreach t in array array[
    'jobs', 'job_profiles', 'salary_bands', 'title_mapping', 'career_paths',
    'levels', 'categories', 'skills', 'competency_levels',
    'role_skill_map', 'job_grades', 'industries', 'industry_salary_factors',
    'industry_skills', 'seniority_levels', 'skill_proficiency',
    'benefits_catalog', 'benefits_observations', 'level_benefits_factors'
  ] loop
    execute format('revoke all on %I from anon', t);
  end loop;
end $$;

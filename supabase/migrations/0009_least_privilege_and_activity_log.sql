-- 0009_least_privilege_and_activity_log.sql
--
-- Stage 4 of docs/PLAN-whitelabel-tenancy.md: roles that mean something, and a
-- trail of who touched whose data.
--
-- ── FIRST, A DEFECT IN 0008 ───────────────────────────────────────────────
--
-- 0008 wrote this, and it is wrong:
--
--     create policy jobsy_sessions_isolation on jobsy_sessions for all
--       using (app.can_access_org(org_id))
--
-- `for all` with an access test that only asks "are you a member" means every
-- member can write. A `viewer` — the role whose entire purpose is to be
-- read-only — could insert, update and delete rosters in their client. Same on
-- employees. Demonstrated before writing this migration, not deduced:
--
--     set role authenticated;
--     select set_config('request.jwt.claim.sub', '<a viewer>', false);
--     insert into jobsy_sessions (org_id, session_code)
--       select id, 'VIEWER-WRITE-TEST' from orgs where slug='initech';
--     -- INSERT 0 1
--
-- 0008's test did catch a viewer writing REFERENCE data, because that path goes
-- through can_write_org() which requires admin. It never tried a viewer writing
-- CLIENT data, so the gap sat exactly where the test was not looking. The
-- lesson is not "write more tests" but "a role is not tested until it has been
-- tried against every table it can reach".
--
-- Fixed below by splitting read from write on client data, the way 0008 already
-- did for reference data.

-- ─────────────────────────────────────────── 1. who may change things ──
--
-- Three levels of permission now, not two:
--
--   read   can_access_org()  — any member. Viewers stop here.
--   edit   can_edit_org()    — analysts and admins. Rosters, employees.
--   admin  is_org_admin()    — admins only. Reference data, the audit trail.

create or replace function app.can_edit_org(p_org uuid)
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
       and m.role in ('client_admin', 'analyst')
  ) or exists (
    select 1 from memberships m
      join orgs o on o.partner_id = m.partner_id
     where m.user_id = auth.uid()
       and o.id = p_org
       and m.role in ('partner_admin', 'partner_analyst')
  )
$$;

grant execute on function app.can_edit_org(uuid) to authenticated, service_role;
revoke execute on function app.can_edit_org(uuid) from public;

-- Read stays open to every member; writing now requires the edit right. Both
-- `using` and `with check` on the write policy, so a row cannot be created in,
-- or moved to, an org the user may not edit.
drop policy if exists jobsy_sessions_isolation on jobsy_sessions;
drop policy if exists jobsy_sessions_read      on jobsy_sessions;
drop policy if exists jobsy_sessions_write     on jobsy_sessions;
create policy jobsy_sessions_read on jobsy_sessions for select to authenticated
  using (app.can_access_org(org_id));
create policy jobsy_sessions_write on jobsy_sessions for all to authenticated
  using      (app.can_edit_org(org_id))
  with check (app.can_edit_org(org_id));

drop policy if exists employees_isolation on employees;
drop policy if exists employees_read      on employees;
drop policy if exists employees_write     on employees;
create policy employees_read on employees for select to authenticated
  using (app.can_access_org(org_id));
create policy employees_write on employees for all to authenticated
  using      (app.can_edit_org(org_id))
  with check (app.can_edit_org(org_id));

-- ────────────────────────────────────────────────── 2. the trail ──
--
-- D-1 to D-4. library_audit has recorded changes to the shared reference
-- library since 0001 and is properly append-only after 0003. Nothing has ever
-- recorded who opened, changed or exported a CLIENT's roster — which is the
-- question actually asked after an incident, and the one a client's own DPO
-- asks before signing.

create table if not exists activity_log (
  id        bigint generated always as identity primary key,
  at        timestamptz not null default now(),
  org_id    uuid references orgs(id) on delete set null,
  actor_id  uuid,          -- auth.users, but NOT a foreign key: see below
  actor     text,          -- email captured at the time, for the same reason
  action    text not null,
  subject   text,
  detail    jsonb not null default '{}'::jsonb
);

comment on table activity_log is
  'Append-only record of access to client data. Written by trigger and by '
  'app.log(); never by application code directly.';

-- actor_id is deliberately NOT a foreign key to auth.users, and the email is
-- copied in rather than joined. Deleting a user must not delete or blank the
-- record of what they did — an audit trail that a `delete from auth.users`
-- can edit is not evidence of anything. Same reason org_id is `on delete set
-- null` rather than cascade: closing a client keeps the history that they were
-- a client.

create index if not exists activity_log_org_at_idx   on activity_log (org_id, at desc);
create index if not exists activity_log_actor_at_idx on activity_log (actor_id, at desc);
create index if not exists activity_log_action_idx   on activity_log (action);

-- What the app calls for things no trigger can see. A SELECT fires no trigger,
-- so reads, exports and sign-ins are reported by the application. That is a
-- real limitation and worth stating plainly: writes are recorded whether or not
-- anyone remembered to log them, reads are recorded only where the app says so.
create or replace function app.log(p_action text, p_org uuid,
                                   p_subject text default null,
                                   p_detail jsonb default '{}'::jsonb)
returns void
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare v_email text;
begin
  -- A caller may only write log entries against a client they can reach.
  -- Without this, any signed-in user could stuff another client's trail with
  -- invented events -- they could not forge the ACTOR, which comes from
  -- auth.uid() below rather than from an argument, but noise in an audit trail
  -- is its own kind of damage. auth.uid() is null for server-side callers
  -- (the importer, tools/manage_users.py), which are trusted by virtue of
  -- holding the secret key.
  if auth.uid() is not null and p_org is not null and not app.can_access_org(p_org) then
    raise exception 'cannot write activity for an organisation you cannot access';
  end if;

  select email into v_email from auth.users where id = auth.uid();
  insert into activity_log (org_id, actor_id, actor, action, subject, detail)
  values (p_org, auth.uid(), v_email, p_action, p_subject, coalesce(p_detail, '{}'::jsonb));
end $$;

grant execute on function app.log(text, uuid, text, jsonb) to authenticated, service_role;
revoke execute on function app.log(text, uuid, text, jsonb) from public;

-- app.* is not served over HTTP -- that is the whole point of putting it in a
-- private schema (0007). But the application legitimately needs to record the
-- things no trigger can see: a SELECT fires nothing, so reads and exports are
-- reported by the app or not at all.
--
-- So exactly ONE door into that schema is opened, and it is this. A thin
-- wrapper in `public`, which PostgREST does serve, calling straight through.
-- It adds no capability: the actor is still auth.uid(), the org is still
-- checked, and the row is still written by a definer function into a table
-- nobody holds a write grant on. What it does NOT do is expose
-- member_org_ids(), is_org_admin(), can_edit_org() or the trigger function as
-- REST endpoints, which is what moving app.log() to `public` would have cost.
create or replace function public.log_activity(p_action text, p_org uuid,
                                               p_subject text default null,
                                               p_detail jsonb default '{}'::jsonb)
returns void
language sql
set search_path = public, pg_catalog
as $$ select app.log(p_action, p_org, p_subject, p_detail) $$;

revoke execute on function public.log_activity(text, uuid, text, jsonb) from public;
revoke execute on function public.log_activity(text, uuid, text, jsonb) from anon;
grant  execute on function public.log_activity(text, uuid, text, jsonb) to authenticated, service_role;

-- Writes to client data are recorded by trigger, so they cannot be forgotten.
-- row_to_json rather than a column list, for the reason 0001 gave: a later
-- ALTER TABLE must not silently stop being audited.
create or replace function app.log_client_data_change()
returns trigger
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_org   uuid;
  v_email text;
  v_subject text;
begin
  v_org := case when tg_op = 'DELETE' then old.org_id else new.org_id end;
  select email into v_email from auth.users where id = auth.uid();
  begin
    v_subject := case when tg_op = 'DELETE' then old.session_code else new.session_code end;
  exception when others then
    v_subject := case when tg_op = 'DELETE' then old.employee_id else new.employee_id end;
  end;

  insert into activity_log (org_id, actor_id, actor, action, subject, detail)
  values (v_org, auth.uid(), v_email,
          tg_table_name || '.' || lower(tg_op),
          v_subject,
          jsonb_build_object(
            'table', tg_table_name,
            'old', case when tg_op = 'INSERT' then null else to_jsonb(old) - 'payload' end,
            'new', case when tg_op = 'DELETE' then null else to_jsonb(new) - 'payload' end));
  return case when tg_op = 'DELETE' then old else new end;
end $$;

-- The payload is stripped above. It holds the roster itself — names, salaries,
-- gender — and copying that into a second table on every save would double the
-- personal data held, in a table nobody can delete from, for no investigative
-- gain: "who changed this session, and when" is answered without it.

-- 0005 revoked execute on log_library_change() after finding PostgREST had
-- published it at /rest/v1/rpc/, and called it "precisely the wrong function to
-- leave callable". log_client_data_change() is the same kind of function and
-- arrived with the same default grant to PUBLIC — caught here by 0007's own
-- assertion that no app function is executable by anon, which failed the moment
-- this migration was added.
--
-- A trigger function needs no EXECUTE grant at all: the executor invokes it, not
-- the session role, so the triggers below keep firing. Verified by writing a row
-- afterwards and finding the log entry, which is what the test does.
revoke execute on function app.log_client_data_change() from public;
revoke execute on function app.log_client_data_change() from anon;
revoke execute on function app.log_client_data_change() from authenticated;
revoke execute on function app.log_client_data_change() from service_role;

drop trigger if exists jobsy_sessions_activity on jobsy_sessions;
create trigger jobsy_sessions_activity
  after insert or update or delete on jobsy_sessions
  for each row execute function app.log_client_data_change();

drop trigger if exists employees_activity on employees;
create trigger employees_activity
  after insert or update or delete on employees
  for each row execute function app.log_client_data_change();

-- ─────────────────────────────────────── 3. the trail is evidence ──
--
-- 0003's finding, applied again: Supabase grants every privilege on a new table
-- to anon, authenticated, service_role and postgres BY NAME, so a
-- `revoke ... from public` is decorative. Revoked by name, and verified in the
-- test rather than assumed.
--
-- service_role is revoked too. It is what tools/manage_users.py and the
-- importer authenticate as, and it bypasses RLS — so leaving it able to DELETE
-- would mean the one credential an operator holds could erase the record of an
-- operator's actions. Rows still arrive: app.log() and the trigger are SECURITY
-- DEFINER and run as the owner.

revoke insert, update, delete, truncate on activity_log from anon;
revoke insert, update, delete, truncate on activity_log from authenticated;
revoke insert, update, delete, truncate on activity_log from service_role;
revoke all on activity_log from anon;
grant select on activity_log to service_role;

alter table activity_log enable row level security;

-- Admins read their own client's trail, and nobody else's. A viewer or analyst
-- reads nothing here: who looked at the roster is a question for the person
-- accountable for the roster.
drop policy if exists activity_log_read on activity_log;
create policy activity_log_read on activity_log for select to authenticated
  using (org_id is not null and app.is_org_admin(org_id));

-- No insert, update or delete policy exists, deliberately. Even with a grant,
-- RLS would deny; without a grant, the API cannot reach it at all. Two locks,
-- because this is the table whose value is entirely in nobody being able to
-- edit it.

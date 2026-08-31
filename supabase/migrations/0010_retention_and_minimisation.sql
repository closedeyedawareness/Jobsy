-- 0010_retention_and_minimisation.sql
--
-- Stage 5 of docs/PLAN-whitelabel-tenancy.md: C-3 and C-4.
--
-- "The processor shall return or delete all personal data at the end of the
-- contract" is a standard clause in every processor agreement Jobsy will be
-- asked to sign. Until this migration it could not be honoured: sessions were
-- stored indefinitely and there was no delete path at all. A clause you cannot
-- perform is worse than one you have not signed.
--
-- ── RETENTION IS PER CLIENT, AND 365 DAYS IS A PLACEHOLDER ────────────────
--
-- The partner has not given a number yet — it is an open question in §4 of the
-- plan. A default is still better than no mechanism, because the mechanism is
-- the part that takes engineering and the number is the part that takes an
-- email. 365 days is chosen as a year of comparability: pay-equity reporting is
-- annual, so an analyst re-running last year's cohort is a real workflow, and a
-- shorter default would quietly break it.
--
-- It is per-org because retention is a contract term and contracts differ. When
-- the partner supplies their number, it is an UPDATE, not a migration.
--
-- ── WHY PSEUDONYMISATION HAPPENS ON SAVE, NOT ON UPLOAD ───────────────────
--
-- The plan said "pseudonymise names at ingest". Ingest is the wrong moment.
-- ui/app.py:2340 detects a name column and the analysis displays it: an analyst
-- looking at a pay-equity outlier needs to know who it is, and a screen full of
-- EMP-4821 makes the product useless for the job it exists to do.
--
-- What C-4 actually asks is that Jobsy not HOLD what it does not need. So names
-- are stripped when the session is written to the database — the copy that
-- persists, that sits in backups, and that a breach would expose. The browser
-- session keeps the real names for as long as the analyst is working, and they
-- were the client's data on the client's screen the whole time.
--
-- The cost is honest and worth stating: reloading a saved session shows tokens
-- rather than names. That is the point. A client who would rather keep names
-- can leave the flag off; a client whose DPO asks "do you store our people's
-- names" gets to answer no.

-- ─────────────────────────────────────────────── 1. the two settings ──

alter table orgs add column if not exists retention_days int not null default 365;
alter table orgs add column if not exists pseudonymise_names boolean not null default false;

alter table orgs drop constraint if exists orgs_retention_sane;
alter table orgs add constraint orgs_retention_sane
  check (retention_days between 1 and 3650);

comment on column orgs.retention_days is
  'Days a saved session survives after its last update, before purge_expired_sessions() '
  'removes it. A contract term, not a technical limit: set it from the DPA.';
comment on column orgs.pseudonymise_names is
  'When true the application strips employee names before writing a session to the '
  'database. The working session in the browser is unaffected. Off by default so that '
  'turning it on is a decision somebody makes, rather than a surprise.';

-- ────────────────────────── 2. the trail must outlive the client ──
--
-- activity_log.org_id is `on delete set null`, which keeps the row but loses
-- WHICH client it was about — and the row proving an end-of-contract purge
-- happened is exactly the one that must still say whose data was purged. Same
-- reasoning as actor_id/actor in 0009: an identifier that can be dissolved by
-- deleting another row is not evidence.

alter table activity_log add column if not exists org_name text;

create or replace function app.log(p_action text, p_org uuid,
                                   p_subject text default null,
                                   p_detail jsonb default '{}'::jsonb)
returns void
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_email text;
  v_org_name text;
begin
  if auth.uid() is not null and p_org is not null and not app.can_access_org(p_org) then
    raise exception 'cannot write activity for an organisation you cannot access';
  end if;

  select email into v_email from auth.users where id = auth.uid();
  select name  into v_org_name from orgs where id = p_org;

  insert into activity_log (org_id, org_name, actor_id, actor, action, subject, detail)
  values (p_org, v_org_name, auth.uid(), v_email, p_action, p_subject,
          coalesce(p_detail, '{}'::jsonb));
end $$;

create or replace function app.log_client_data_change()
returns trigger
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_org   uuid;
  v_email text;
  v_org_name text;
  v_subject text;
begin
  v_org := case when tg_op = 'DELETE' then old.org_id else new.org_id end;
  select email into v_email from auth.users where id = auth.uid();
  select name  into v_org_name from orgs where id = v_org;
  begin
    v_subject := case when tg_op = 'DELETE' then old.session_code else new.session_code end;
  exception when others then
    v_subject := case when tg_op = 'DELETE' then old.employee_id else new.employee_id end;
  end;

  insert into activity_log (org_id, org_name, actor_id, actor, action, subject, detail)
  values (v_org, v_org_name, auth.uid(), v_email,
          tg_table_name || '.' || lower(tg_op),
          v_subject,
          jsonb_build_object(
            'table', tg_table_name,
            'old', case when tg_op = 'INSERT' then null else to_jsonb(old) - 'payload' end,
            'new', case when tg_op = 'DELETE' then null else to_jsonb(new) - 'payload' end));
  return case when tg_op = 'DELETE' then old else new end;
end $$;

revoke execute on function app.log_client_data_change() from public, anon, authenticated, service_role;

-- ───────────────────────────────────── 3. what is due for deletion ──
--
-- A session's clock runs from its last UPDATE, not its creation: a roster
-- somebody is still working on is not stale. updated_at is maintained by the
-- trigger 0007 attached.

create or replace function app.expired_sessions()
returns table (id uuid, org_id uuid, session_code text, org_name text,
               updated_at timestamptz, retention_days int, days_over numeric)
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
  select s.id, s.org_id, s.session_code, o.name, s.updated_at, o.retention_days,
         round(extract(epoch from (now() - s.updated_at)) / 86400.0 - o.retention_days, 1)
    from jobsy_sessions s
    join orgs o on o.id = s.org_id
   where s.updated_at < now() - make_interval(days => o.retention_days)
$$;

-- ────────────────────────────────────────── 4. actually deleting ──
--
-- Both functions below are destructive. Their bodies live in `app`, which
-- PostgREST does not serve; narrow wrappers granted to service_role ALONE are
-- added at the end of this file, because tools/manage_users.py reaches the
-- database over the same REST API as everyone else and needs a door. An
-- authenticated user calling them gets "permission denied for function" -- no
-- policy is involved and there is nothing to get subtly wrong.
--
-- The deletions themselves are logged automatically -- jobsy_sessions and
-- employees carry the 0009 trigger, so every removed row leaves a
-- `jobsy_sessions.delete` entry naming the client. The summary rows below are
-- in addition to that, so the trail answers "was retention applied" without
-- counting individual deletions.

create or replace function app.purge_expired_sessions()
returns int
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare n int;
begin
  with gone as (
    delete from jobsy_sessions s
     using orgs o
     where o.id = s.org_id
       and s.updated_at < now() - make_interval(days => o.retention_days)
    returning s.id
  )
  select count(*) into n from gone;

  if n > 0 then
    perform app.log('retention.purge', null, null, jsonb_build_object('sessions_deleted', n));
  end if;
  return n;
end $$;

-- End of contract. Removes the client's personal data and leaves everything
-- that is evidence: the org row, the memberships (revoke those deliberately),
-- and the whole activity_log including the record of this purge.
create or replace function app.purge_client(p_org uuid)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  n_sessions int;
  n_employees int;
  v_name text;
begin
  select name into v_name from orgs where id = p_org;
  if v_name is null then
    raise exception 'no such client: %', p_org;
  end if;

  with gone as (delete from jobsy_sessions where org_id = p_org returning id)
  select count(*) into n_sessions from gone;
  with gone as (delete from employees where org_id = p_org returning id)
  select count(*) into n_employees from gone;

  -- Written AFTER the deletions so the row is proof of a completed act, not an
  -- intention. org_name is captured by app.log() from the org row, which still
  -- exists -- deleting the client's DATA is not deleting the client.
  perform app.log('retention.client_purged', p_org, v_name,
                  jsonb_build_object('sessions_deleted', n_sessions,
                                     'employees_deleted', n_employees));

  return jsonb_build_object('client', v_name,
                            'sessions_deleted', n_sessions,
                            'employees_deleted', n_employees);
end $$;

revoke execute on function app.expired_sessions()      from public, anon, authenticated;
revoke execute on function app.purge_expired_sessions() from public, anon, authenticated;
revoke execute on function app.purge_client(uuid)       from public, anon, authenticated;
grant  execute on function app.expired_sessions()       to service_role;
grant  execute on function app.purge_expired_sessions() to service_role;
grant  execute on function app.purge_client(uuid)       to service_role;

-- The operator tool reaches the database over the same REST API as everyone
-- else, just with the secret key -- and PostgREST serves only `public`. So the
-- purge functions need a door, and it must be a narrower one than
-- log_activity(): these delete personal data.
--
-- Granted to service_role ALONE. An authenticated user calling them gets
-- "permission denied for function", not an empty result -- there is no policy
-- involved and nothing to get wrong. The bodies stay in `app`, so the reachable
-- surface is three names rather than the whole schema.

create or replace function public.purge_expired_sessions()
returns int language sql set search_path = public, pg_catalog
as $$ select app.purge_expired_sessions() $$;

create or replace function public.purge_client(p_org uuid)
returns jsonb language sql set search_path = public, pg_catalog
as $$ select app.purge_client(p_org) $$;

create or replace function public.expired_sessions()
returns table (id uuid, org_id uuid, session_code text, org_name text,
               updated_at timestamptz, retention_days int, days_over numeric)
language sql set search_path = public, pg_catalog
as $$ select * from app.expired_sessions() $$;

revoke execute on function public.purge_expired_sessions() from public, anon, authenticated;
revoke execute on function public.purge_client(uuid)       from public, anon, authenticated;
revoke execute on function public.expired_sessions()       from public, anon, authenticated;
grant  execute on function public.purge_expired_sessions() to service_role;
grant  execute on function public.purge_client(uuid)       to service_role;
grant  execute on function public.expired_sessions()       to service_role;

-- SCHEDULING, which is an operator step and not something a migration should do
-- silently. Retention that only runs when somebody remembers is not retention.
-- With pg_cron enabled on the project:
--
--   select cron.schedule('jobsy-retention', '0 3 * * *',
--                        $j$ select app.purge_expired_sessions() $j$);
--
-- Until that is set up, `python tools/manage_users.py purge --due` does the same
-- thing by hand and prints what it removed.

-- Adversarial test for 0010: retention, purge, and the trail that must outlive
-- what it records.
--
-- The interesting assertions here are not "the delete worked" — they are that
-- the RECORD of the delete survives the thing it was about. A purge you cannot
-- prove happened is worth very little to a client's DPO, and an audit row that
-- dissolves when its subject is removed is not evidence.
\set ON_ERROR_STOP off
\pset format unaligned
\pset tuples_only on

create or replace function t_eq(label text, got anyelement, want anyelement) returns text
language plpgsql as $$
begin
  if got is not distinct from want then
    return 'ok    ' || label || ' = ' || coalesce(got::text, 'null');
  end if;
  return 'FAIL  ' || label || ' = ' || coalesce(got::text,'null') || ', wanted ' || coalesce(want::text,'null');
end $$;

create or replace function t_write_blocked(label text, stmt text) returns text
language plpgsql as $$
declare n int;
begin
  execute stmt;
  get diagnostics n = row_count;
  if n = 0 then
    return 'ok    0 rows       ' || label || '  [no row matched the policy]';
  end if;
  return 'FAIL  WROTE ' || n || ' ROW(S)  ' || label;
exception when others then
  return 'ok    blocked       ' || label || '  [' || split_part(sqlerrm, E'\n', 1) || ']';
end $$;

select id as org_north from orgs where slug='northwind' \gset
select id as org_conto from orgs where slug='contoso'   \gset

select '── defaults are sane, and cannot be set to nonsense ────────────────';
select t_eq('every client has a retention period',
            (select count(*)::int from orgs where retention_days is null), 0);
select t_eq('the default is a year of comparability',
            (select retention_days from orgs where slug='northwind'), 365);
select t_eq('pseudonymisation is off until somebody decides',
            (select bool_or(pseudonymise_names) from orgs), false);
select t_write_blocked('retention of zero days',
  $$update orgs set retention_days = 0 where slug='northwind'$$);
select t_write_blocked('retention of a century',
  $$update orgs set retention_days = 40000 where slug='northwind'$$);
select t_write_blocked('negative retention',
  $$update orgs set retention_days = -30 where slug='northwind'$$);

select '';
select '── what is due, and what is not ────────────────────────────────────';
-- A short retention on one client, and a session backdated past it.
--
-- Backdating needs the updated_at trigger switched off first. The first version
-- of this test just ran `update ... set updated_at = now() - 400 days` and was
-- baffled when nothing expired: 0007 attached a BEFORE UPDATE trigger that sets
-- updated_at := now(), so the fixture overwrote itself in the same statement.
--
-- That is worth keeping as a property rather than only working around, so it is
-- asserted below: a user with write access cannot move a session's clock, in
-- either direction. Otherwise an analyst could postpone their client's
-- retention indefinitely by touching a column.
update orgs set retention_days = 30 where slug='northwind';
insert into jobsy_sessions (org_id, session_code, org_label, payload)
  values (:'org_north', 'RET-OLD', 'Northwind BV', '{"upload_df":[{"name":"Old Record"}]}'::jsonb)
on conflict (session_code) do nothing;
insert into jobsy_sessions (org_id, session_code, org_label)
  values (:'org_north', 'RET-FRESH', 'Northwind BV')
on conflict (session_code) do nothing;
alter table jobsy_sessions disable trigger jobsy_sessions_set_updated_at;
update jobsy_sessions set updated_at = now() - interval '400 days' where session_code = 'RET-OLD';
alter table jobsy_sessions enable trigger jobsy_sessions_set_updated_at;

-- The fixture above had to DISABLE the updated_at trigger to backdate a row.
-- This is the assertion that that was necessary: an ordinary UPDATE, even one
-- naming updated_at explicitly, gets stamped with now() by the trigger, so a
-- client cannot quietly keep a session out of the retention sweep.
--
-- It has to be a TOP-LEVEL statement. Postgres refuses a data-modifying
-- statement inside a subquery, and the first version of this line was one:
-- psql raised, run.sh counted neither a pass nor a fail, and the assertion
-- never ran at all while the suite reported green. run.sh now counts a psql
-- error as a failure for exactly this reason.
update jobsy_sessions set updated_at = now() - interval '400 days'
  where session_code = 'RET-FRESH'
  returning (updated_at < now() - interval '300 days') as backdated \gset
-- Quoted interpolation: \gset stores the boolean as psql's raw output, 'f',
-- and :backdated unquoted would paste a bare identifier called f.
select t_eq('a normal UPDATE cannot move a session''s clock backwards',
            :'backdated'::boolean, false);

select t_eq('the stale session is listed as expired',
            (select count(*)::int from app.expired_sessions() where session_code = 'RET-OLD'), 1);
select t_eq('  and reports how far over it is',
            (select days_over > 360 from app.expired_sessions() where session_code = 'RET-OLD'), true);
select t_eq('a session touched today is NOT expired',
            (select count(*)::int from app.expired_sessions() where session_code = 'RET-FRESH'), 0);
select t_eq('another client''s sessions are not swept up',
            (select count(*)::int from app.expired_sessions() where org_id = :'org_conto'::uuid), 0);

select '';
select '── the purge removes exactly what is due ───────────────────────────';
select t_eq('purge reports what it deleted', app.purge_expired_sessions() >= 1, true);
select t_eq('the stale session is gone',
            (select count(*)::int from jobsy_sessions where session_code = 'RET-OLD'), 0);
select t_eq('the fresh one survived',
            (select count(*)::int from jobsy_sessions where session_code = 'RET-FRESH'), 1);
select t_eq('nothing is left due',
            (select count(*)::int from app.expired_sessions()), 0);
select t_eq('a second run is a no-op, not an error', app.purge_expired_sessions(), 0);

select '';
select '── and it is provable afterwards ───────────────────────────────────';
select t_eq('the deletion itself was logged by the 0009 trigger',
            (select count(*)::int from activity_log
              where action = 'jobsy_sessions.delete' and subject = 'RET-OLD'), 1);
select t_eq('  naming the client, not just an id',
            (select org_name from activity_log where subject = 'RET-OLD' limit 1), 'Northwind BV');
select t_eq('a summary row records that retention ran',
            (select count(*)::int from activity_log where action = 'retention.purge'), 1);
select t_eq('the purged roster''s contents were never copied into the trail',
            (select count(*)::int from activity_log where detail::text like '%Old Record%'), 0);

select '';
select '── end of contract ─────────────────────────────────────────────────';
insert into jobsy_sessions (org_id, session_code, org_label)
  values (:'org_conto', 'END-1', 'Contoso NV') on conflict (session_code) do nothing;
insert into employees (org_id, employee_id, name)
  values (:'org_conto', 'END-E1', 'Departing Person') on conflict do nothing;

select t_eq('purge_client reports both counts',
            (app.purge_client(:'org_conto'::uuid) ->> 'sessions_deleted')::int >= 1, true);
select t_eq('the client''s sessions are gone',
            (select count(*)::int from jobsy_sessions where org_id = :'org_conto'::uuid), 0);
select t_eq('the client''s employees are gone',
            (select count(*)::int from employees where org_id = :'org_conto'::uuid), 0);
select t_eq('the client itself still exists — deleting data is not deleting a customer',
            (select count(*)::int from orgs where id = :'org_conto'::uuid), 1);
select t_eq('another client was untouched',
            (select count(*)::int from jobsy_sessions where org_id = :'org_north'::uuid) >= 1, true);
select t_eq('the purge is recorded',
            (select count(*)::int from activity_log where action = 'retention.client_purged'), 1);
select t_eq('  naming the client whose data it was',
            (select org_name from activity_log where action='retention.client_purged' limit 1),
            'Contoso NV');

select '';
select '── the record outlives the client ──────────────────────────────────';
-- The row proving a purge happened is precisely the one that must still say
-- whose data it was, even after the org row is gone. org_id nulls out; the name
-- was copied in at write time and does not.
delete from orgs where id = :'org_conto'::uuid;
select t_eq('the purge record survives deleting the client',
            (select count(*)::int from activity_log where action = 'retention.client_purged'), 1);
select t_eq('  and still names them, with org_id now null',
            (select org_name from activity_log where action='retention.client_purged' limit 1),
            'Contoso NV');
select t_eq('  org_id was released rather than cascading the row away',
            (select org_id from activity_log where action='retention.client_purged' limit 1), null::uuid);

select '';
select '── purging is not reachable from a browser ─────────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', false) is not null as _;
select t_write_blocked('a client_admin calling purge_client',
  format($$select app.purge_client(%L)$$, :'org_north'));
select t_write_blocked('a client_admin calling purge_expired_sessions',
  $$select app.purge_expired_sessions()$$);
select t_write_blocked('a client_admin listing what is due',
  $$select * from app.expired_sessions()$$);
select t_write_blocked('a client_admin lengthening their own retention',
  $$update orgs set retention_days = 3650 where slug = 'northwind'$$);
reset role;

-- The purge wrappers DO exist in public, because the operator tool reaches the
-- database over the same REST API as everyone else. What matters is that they
-- are granted to service_role alone -- asserted here rather than assumed, since
-- "it is in a private schema" stopped being the protection the moment a wrapper
-- was needed.
select t_eq('authenticated cannot execute the purge wrappers',
            (select bool_or(has_function_privilege('authenticated', p.oid, 'execute'))
               from pg_proc p join pg_namespace n on n.oid=p.pronamespace
              where n.nspname='public'
                and p.proname in ('purge_client','purge_expired_sessions','expired_sessions')), false);
select t_eq('nor can anon',
            (select bool_or(has_function_privilege('anon', p.oid, 'execute'))
               from pg_proc p join pg_namespace n on n.oid=p.pronamespace
              where n.nspname='public'
                and p.proname in ('purge_client','purge_expired_sessions','expired_sessions')), false);
select t_eq('service_role can, because that is who runs the tool',
            (select bool_and(has_function_privilege('service_role', p.oid, 'execute'))
               from pg_proc p join pg_namespace n on n.oid=p.pronamespace
              where n.nspname='public'
                and p.proname in ('purge_client','purge_expired_sessions','expired_sessions')), true);
select t_eq('the app helpers are still NOT in public',
            (select count(*)::int from pg_proc p join pg_namespace n on n.oid=p.pronamespace
              where n.nspname='public'
                and p.proname in ('member_org_ids','is_org_admin','can_edit_org','can_access_org')), 0);

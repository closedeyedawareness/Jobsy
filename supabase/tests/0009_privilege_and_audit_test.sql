-- Adversarial test for 0009: least privilege, and a trail nobody can edit.
--
-- The first block is a regression test for a defect 0008 shipped. `for all`
-- with a membership-only test let a VIEWER insert, update and delete rosters —
-- the one role that exists to be read-only. 0008's test missed it because it
-- only tried a viewer against reference data, which goes through a different
-- function. A role is not tested until it has been tried against every table it
-- can reach.
--
-- Depends on 0007's and 0008's fixtures (partners, clients, users, rosters),
-- which run first by filename order.
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

create or replace function t_accept(label text, stmt text) returns text
language plpgsql as $$
declare n int;
begin
  execute stmt;
  get diagnostics n = row_count;
  if n = 0 then return 'FAIL  (0 rows)     ' || label; end if;
  return 'ok    allowed       ' || label;
exception when others then
  return 'FAIL  (blocked!)   ' || label || '  [' || split_part(sqlerrm, E'\n', 1) || ']';
end $$;

-- An analyst at Northwind: may edit client data, may not administer.
insert into auth.users (id, email) values
  ('55555555-5555-5555-5555-555555555555','analyst@northwind.example')
on conflict (id) do nothing;
insert into memberships (user_id, org_id, role)
  select '55555555-5555-5555-5555-555555555555', id, 'analyst' from orgs where slug='northwind'
on conflict do nothing;

select id as org_north from orgs where slug='northwind' \gset
select id as org_inite from orgs where slug='initech'   \gset

select '── the 0008 defect: a viewer could write client data ───────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '33333333-3333-3333-3333-333333333333', false) is not null as _;
select t_eq('the viewer can still READ their client''s roster',
            (select count(*)::int from jobsy_sessions where session_code = 'RLS-INITE'), 1);
select t_write_blocked('a viewer INSERTING a roster in their own client',
  format($$insert into jobsy_sessions (org_id, session_code) values (%L, 'V-INSERT')$$, :'org_inite'));
select t_write_blocked('a viewer UPDATING their client''s roster',
  $$update jobsy_sessions set org_label = 'edited by viewer' where session_code = 'RLS-INITE'$$);
select t_write_blocked('a viewer DELETING their client''s roster',
  $$delete from jobsy_sessions where session_code = 'RLS-INITE'$$);
select t_write_blocked('a viewer INSERTING an employee',
  format($$insert into employees (org_id, employee_id, name) values (%L, 'V-1', 'Ghost')$$, :'org_inite'));
select t_write_blocked('a viewer DELETING an employee',
  $$delete from employees where employee_id = 'I-1'$$);
reset role;
select t_eq('nothing the viewer attempted landed',
            (select count(*)::int from jobsy_sessions where session_code = 'V-INSERT'), 0);
select t_eq('the roster they tried to edit is untouched',
            (select org_label from jobsy_sessions where session_code = 'RLS-INITE'), 'Initech GmbH');
select t_eq('the employee they tried to delete is still there',
            (select count(*)::int from employees where employee_id = 'I-1'), 1);

select '';
select '── an analyst edits client data but administers nothing ────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '55555555-5555-5555-5555-555555555555', false) is not null as _;
select t_accept('an analyst writing a roster in their client',
  format($$insert into jobsy_sessions (org_id, session_code) values (%L, 'A-INSERT')$$, :'org_north'));
select t_accept('an analyst adding an employee',
  format($$insert into employees (org_id, employee_id, name) values (%L, 'A-1', 'Hired')$$, :'org_north'));
select t_write_blocked('an analyst editing REFERENCE data (admin only)',
  format($$insert into skills (org_id, skill_id, skill_name, category)
           values (%L, 'S-A', 'Invented', 'Core')$$, :'org_north'));
select t_write_blocked('an analyst writing to another client',
  format($$insert into jobsy_sessions (org_id, session_code) values (%L, 'A-EVIL')$$, :'org_inite'));
select t_eq('an analyst cannot read the audit trail', (select count(*)::int from activity_log), 0);
reset role;

select '';
select '── the trail records what happened, without being asked ────────────';
select t_eq('the analyst''s insert was logged by trigger',
            (select count(*)::int from activity_log
              where action = 'jobsy_sessions.insert' and subject = 'A-INSERT'), 1);
select t_eq('  attributed to the analyst',
            (select actor from activity_log where subject = 'A-INSERT' limit 1),
            'analyst@northwind.example');
select t_eq('  and stamped with the right client',
            (select org_id from activity_log where subject = 'A-INSERT' limit 1), :'org_north'::uuid);
select t_eq('the employee insert was logged too',
            (select count(*)::int from activity_log where action = 'employees.insert' and subject = 'A-1'), 1);
select t_eq('the viewer''s BLOCKED writes left no log rows',
            (select count(*)::int from activity_log where subject = 'V-INSERT'), 0);
select t_eq('the roster payload is NOT copied into the trail',
            (select count(*)::int from activity_log
              where detail::text like '%upload_df%'), 0);

select '';
select '── the trail is evidence: nobody can edit it ───────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', false) is not null as _;
select t_eq('a client_admin CAN read their own client''s trail',
            (select count(*)::int from activity_log) > 0, true);
select t_eq('  and sees only their own client',
            (select count(*)::int from activity_log where org_id = :'org_inite'::uuid), 0);
select t_write_blocked('a client_admin deleting a log row',
  $$delete from activity_log where action = 'jobsy_sessions.insert'$$);
select t_write_blocked('a client_admin rewriting a log row',
  $$update activity_log set actor = 'somebody else'$$);
select t_write_blocked('a client_admin forging a log row',
  format($$insert into activity_log (org_id, action) values (%L, 'invented')$$, :'org_north'));
reset role;

set role service_role;
-- service_role is what tools/manage_users.py and the importer authenticate as,
-- and it bypasses RLS. If it could delete here, the one credential an operator
-- holds could erase the record of that operator's own actions.
select t_write_blocked('service_role deleting the trail', $$delete from activity_log$$);
select t_write_blocked('service_role truncating the trail', $$truncate activity_log$$);
select t_write_blocked('service_role rewriting the trail', $$update activity_log set actor = 'nobody'$$);
select t_eq('service_role may still READ it', (select count(*)::int from activity_log) > 0, true);
reset role;

set role anon;
select t_write_blocked('anon reading the trail', $$select * from activity_log$$);
reset role;

select '';
select '── app.log(), for the things no trigger can see ────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '55555555-5555-5555-5555-555555555555', false) is not null as _;
select t_accept('an analyst recording an export',
  format($$select app.log('session.export', %L, 'A-INSERT', '{"format":"xlsx"}'::jsonb)$$, :'org_north'));
reset role;
select t_eq('the export is in the trail',
            (select count(*)::int from activity_log where action = 'session.export'), 1);
select t_eq('  attributed, not anonymous',
            (select actor from activity_log where action = 'session.export' limit 1),
            'analyst@northwind.example');
select t_eq('  and it cannot be attributed to someone else — actor comes from auth.uid(), not the caller',
            (select count(*)::int from activity_log
              where action = 'session.export' and actor_id = '55555555-5555-5555-5555-555555555555'), 1);

select '';
select '── the trail survives the people in it ─────────────────────────────';
delete from auth.users where id = '55555555-5555-5555-5555-555555555555';
select t_eq('deleting the user does not delete their history',
            (select count(*)::int from activity_log where actor = 'analyst@northwind.example') > 0, true);
select t_eq('  and the email is still readable, not a dangling id',
            (select actor from activity_log where subject = 'A-INSERT' limit 1),
            'analyst@northwind.example');

select '';
select '── the one door into the private schema ────────────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', false) is not null as _;
select t_accept('log_activity() works for a client you can reach',
  format($$select public.log_activity('session.open', %L, 'RLS-NORTH')$$, :'org_north'));
select t_write_blocked('log_activity() against a client you cannot reach',
  format($$select public.log_activity('session.open', %L, 'stolen')$$, :'org_inite'));
reset role;
select t_eq('the legitimate open was recorded',
            (select count(*)::int from activity_log where action='session.open'), 1);
select t_eq('the illegitimate one was not',
            (select count(*)::int from activity_log where subject='stolen'), 0);
select t_eq('only log_activity is exposed in public, not the app helpers',
            (select count(*)::int from pg_proc p join pg_namespace n on n.oid=p.pronamespace
              where n.nspname='public' and p.proname in
                ('member_org_ids','is_org_admin','can_edit_org','can_access_org','log')), 0);

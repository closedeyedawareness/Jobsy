-- Adversarial test for 0008. This is B-7.
--
-- 0007's test proved the membership FUNCTIONS answer correctly. That is a
-- different claim from this one. Here real users sit behind the `authenticated`
-- role with a real JWT subject and query the tables directly, so what is under
-- test is the policies as the database applies them — not a helper that
-- application code could forget to call.
--
-- Run as a superuser: it switches roles. Superusers bypass RLS, so every
-- assertion is made only while `set role authenticated` is in force. Forgetting
-- that would make this file pass unconditionally, which is why the first
-- assertion checks that RLS is biting before anything else is believed.
--
-- TWO TRAPS THIS FILE WAS BUILT WRONG THE FIRST TIME, AND NOW AVOIDS
--
-- 1. `insert into t select ... from orgs where slug='victim'` is not an attack.
--    The attacker cannot SEE the victim's org, so the subquery returns no rows,
--    the insert writes nothing, and psql reports success. It tests nothing while
--    looking like it tests everything. Org ids are therefore captured as
--    superuser with \gset and interpolated as literals, so every hostile write
--    genuinely attempts a row and the policy is what stops it.
--
-- 2. "No exception" is not "denied". An UPDATE whose rows are all invisible
--    affects zero rows and succeeds. So writes are judged by t_write_blocked,
--    which distinguishes "raised" from "wrote 0 rows" from "actually wrote" —
--    and the last of those is the only failure.
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

-- ── Fixtures ────────────────────────────────────────────────────────────
-- Two partners. Acme has two clients, Rival has one. The pairs that matter are
-- Northwind/Contoso (same partner, different client) and Northwind/Initech
-- (different partner altogether).
insert into partners (slug, name) values ('acme-consult','Acme Consulting'), ('rival-corp','Rival Corp')
  on conflict (slug) do nothing;
insert into orgs (slug, name, partner_id)
  select 'northwind','Northwind BV', id from partners where slug='acme-consult' on conflict (slug) do nothing;
insert into orgs (slug, name, partner_id)
  select 'contoso','Contoso NV', id from partners where slug='acme-consult' on conflict (slug) do nothing;
insert into orgs (slug, name, partner_id)
  select 'initech','Initech GmbH', id from partners where slug='rival-corp' on conflict (slug) do nothing;

insert into auth.users (id, email) values
  ('11111111-1111-1111-1111-111111111111','consultant@acme-consult.example'),
  ('22222222-2222-2222-2222-222222222222','hr@northwind.example'),
  ('33333333-3333-3333-3333-333333333333','viewer@initech.example'),
  ('44444444-4444-4444-4444-444444444444','nobody@nowhere.example')
on conflict (id) do nothing;

insert into memberships (user_id, partner_id, role)
  select '11111111-1111-1111-1111-111111111111', id, 'partner_admin' from partners where slug='acme-consult'
on conflict do nothing;
insert into memberships (user_id, org_id, role)
  select '22222222-2222-2222-2222-222222222222', id, 'client_admin' from orgs where slug='northwind'
on conflict do nothing;
insert into memberships (user_id, org_id, role)
  select '33333333-3333-3333-3333-333333333333', id, 'viewer' from orgs where slug='initech'
on conflict do nothing;

-- The shared library. Production has 81 of these in the 'default' org; one is
-- enough to prove the exemption works, and this file must not depend on an
-- import having been run.
insert into jobs (org_id, job_id, standard_title, function, level)
  select id, 'LIB-1', 'Reference Analyst', 'B', '5' from orgs where slug='default'
on conflict do nothing;

-- One roster per client. The payload stands in for what _capture_session()
-- writes in ui/app.py: names and salaries.
insert into jobsy_sessions (org_id, session_code, org_label, payload)
  select id, 'RLS-NORTH', 'Northwind BV', '{"upload_df":[{"name":"A. North","salary":61000}]}'::jsonb
    from orgs where slug='northwind' on conflict (session_code) do nothing;
insert into jobsy_sessions (org_id, session_code, org_label, payload)
  select id, 'RLS-CONTO', 'Contoso NV', '{"upload_df":[{"name":"B. Conto","salary":58000}]}'::jsonb
    from orgs where slug='contoso' on conflict (session_code) do nothing;
insert into jobsy_sessions (org_id, session_code, org_label, payload)
  select id, 'RLS-INITE', 'Initech GmbH', '{"upload_df":[{"name":"C. Init","salary":72000}]}'::jsonb
    from orgs where slug='initech' on conflict (session_code) do nothing;

insert into employees (org_id, employee_id, name, current_title)
  select id, 'N-1', 'A. North', 'Analyst' from orgs where slug='northwind' on conflict do nothing;
insert into employees (org_id, employee_id, name, current_title)
  select id, 'C-1', 'B. Conto', 'Analyst' from orgs where slug='contoso' on conflict do nothing;
insert into employees (org_id, employee_id, name, current_title)
  select id, 'I-1', 'C. Init', 'Analyst' from orgs where slug='initech' on conflict do nothing;

-- Captured as superuser so hostile writes can name a target the attacker cannot
-- see. Without this, every attack below silently degrades into a no-op.
select id as org_north from orgs where slug='northwind' \gset
select id as org_conto from orgs where slug='contoso'   \gset
select id as org_inite from orgs where slug='initech'   \gset
select id as org_libry from orgs where slug='default'   \gset

select '── the harness itself ──────────────────────────────────────────────';
select t_eq('3 seeded rosters exist (as superuser)',
            (select count(*)::int from jobsy_sessions where session_code like 'RLS-%'), 3);

set role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', false) is not null as _;
select t_eq('RLS is biting — role switch took effect',
            (select count(*)::int from jobsy_sessions where session_code like 'RLS-%'), 1);
reset role;

select '';
select '── client HR (client_admin at Northwind) ───────────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', false) is not null as _;
select t_eq('rosters visible', (select count(*)::int from jobsy_sessions where session_code like 'RLS-%'), 1);
select t_eq('  and it is their own',
            (select session_code from jobsy_sessions where session_code like 'RLS-%'), 'RLS-NORTH');
select t_eq('employees visible', (select count(*)::int from employees), 1);
select t_eq('  and it is their own', (select employee_id from employees), 'N-1');
select t_eq('SIBLING CLIENT, same partner — invisible',
            (select count(*)::int from jobsy_sessions where session_code = 'RLS-CONTO'), 0);
select t_eq('another partner''s client — invisible',
            (select count(*)::int from jobsy_sessions where session_code = 'RLS-INITE'), 0);
select t_eq('the shared library IS visible', (select count(*)::int from jobs), 1);
select t_eq('  and so is the org holding it', (select count(*)::int from orgs where slug='default'), 1);
select t_eq('but sibling and rival orgs are not',
            (select count(*)::int from orgs where slug in ('contoso','initech')), 0);

select t_write_blocked('stamping a new roster with the SIBLING client''s org id',
  format($$insert into jobsy_sessions (org_id, session_code) values (%L, 'RLS-EVIL1')$$, :'org_conto'));
select t_write_blocked('stamping a new roster with the RIVAL client''s org id',
  format($$insert into jobsy_sessions (org_id, session_code) values (%L, 'RLS-EVIL2')$$, :'org_inite'));
select t_accept('a roster in their own org',
  format($$insert into jobsy_sessions (org_id, session_code) values (%L, 'RLS-OWN1')$$, :'org_north'));
select t_write_blocked('moving their own roster into the sibling client',
  format($$update jobsy_sessions set org_id = %L where session_code = 'RLS-NORTH'$$, :'org_conto'));
select t_write_blocked('reading a sibling''s roster by deleting it',
  $$delete from jobsy_sessions where session_code = 'RLS-CONTO'$$);
select t_write_blocked('editing the shared library',
  format($$update jobs set standard_title = 'Vandalised' where org_id = %L$$, :'org_libry'));
select t_write_blocked('adding a job to the shared library',
  format($$insert into jobs (org_id, job_id, standard_title, function, level)
           values (%L, 'LIB-EVIL', 'Injected', 'B', '5')$$, :'org_libry'));
reset role;

select '';
select '── partner consultant (partner_admin at Acme) ──────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', false) is not null as _;
select t_eq('rosters visible across both their clients',
            (select count(*)::int from jobsy_sessions
              where session_code in ('RLS-NORTH','RLS-CONTO','RLS-INITE')), 2);
select t_eq('employees visible across both', (select count(*)::int from employees), 2);
select t_eq('RIVAL PARTNER''s client — invisible',
            (select count(*)::int from jobsy_sessions where session_code = 'RLS-INITE'), 0);
select t_eq('  and its employees', (select count(*)::int from employees where employee_id = 'I-1'), 0);
select t_accept('writing to their second client',
  format($$insert into jobsy_sessions (org_id, session_code) values (%L, 'RLS-OWN2')$$, :'org_conto'));
select t_write_blocked('writing to the rival partner''s client',
  format($$insert into jobsy_sessions (org_id, session_code) values (%L, 'RLS-EVIL3')$$, :'org_inite'));
select t_write_blocked('deleting the rival partner''s roster',
  $$delete from jobsy_sessions where session_code = 'RLS-INITE'$$);
reset role;

select '';
select '── viewer (read-only at Initech) ───────────────────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '33333333-3333-3333-3333-333333333333', false) is not null as _;
select t_eq('rosters visible', (select count(*)::int from jobsy_sessions where session_code like 'RLS-%'), 1);
select t_eq('  and it is theirs',
            (select session_code from jobsy_sessions where session_code like 'RLS-%'), 'RLS-INITE');
select t_eq('the shared library is visible', (select count(*)::int from jobs), 1);
select t_write_blocked('a viewer adding reference data to their own org',
  format($$insert into skills (org_id, skill_id, skill_name, category)
           values (%L, 'S-X', 'Invented', 'Core')$$, :'org_inite'));
reset role;

select '';
select '── no membership, no subject, no session ───────────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '44444444-4444-4444-4444-444444444444', false) is not null as _;
select t_eq('unaffiliated user sees no rosters', (select count(*)::int from jobsy_sessions), 0);
select t_eq('  no employees', (select count(*)::int from employees), 0);
select t_eq('  but does see the shared library', (select count(*)::int from jobs), 1);
reset role;

set role authenticated;
select set_config('request.jwt.claim.sub', '', false) is not null as _;
select t_eq('authenticated with no subject: no rosters', (select count(*)::int from jobsy_sessions), 0);
select t_eq('  and no library (can_read_org needs an identity)', (select count(*)::int from jobs), 0);
reset role;

-- anon does not get "zero rows": the grants were revoked by name in 0007/0008,
-- so it cannot reach the table at all. A harder stop than a policy, and the one
-- that matters for a browser holding only the publishable key.
set role anon;
select t_write_blocked('anon reading rosters',   $$select * from jobsy_sessions$$);
select t_write_blocked('anon reading employees', $$select * from employees$$);
select t_write_blocked('anon reading the library', $$select * from jobs$$);
select t_write_blocked('anon reading memberships', $$select * from memberships$$);
reset role;

select '';
select '── who can enumerate whom ──────────────────────────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '33333333-3333-3333-3333-333333333333', false) is not null as _;
select t_eq('a viewer sees only their own membership', (select count(*)::int from memberships), 1);
select t_write_blocked('a viewer granting themselves another client',
  format($$insert into memberships (user_id, org_id, role)
           values ('33333333-3333-3333-3333-333333333333', %L, 'client_admin')$$, :'org_north'));
select t_write_blocked('a viewer promoting themselves to admin',
  $$update memberships set role = 'client_admin' where user_id = '33333333-3333-3333-3333-333333333333'$$);
reset role;

set role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', false) is not null as _;
select t_eq('a client_admin sees their org''s memberships', (select count(*)::int from memberships), 1);
select t_write_blocked('even a client_admin cannot grant access from the app',
  format($$insert into memberships (user_id, org_id, role)
           values ('44444444-4444-4444-4444-444444444444', %L, 'viewer')$$, :'org_north'));
reset role;

select '';
select '── nothing leaked while we were testing ────────────────────────────';
select t_eq('no roster landed in a client it was aimed at illegitimately',
            (select count(*)::int from jobsy_sessions where session_code like 'RLS-EVIL%'), 0);
select t_eq('the shared library was not vandalised',
            (select count(*)::int from jobs where standard_title = 'Vandalised'), 0);
select t_eq('nothing was injected into the library',
            (select count(*)::int from jobs where job_id = 'LIB-EVIL'), 0);
select t_eq('the rival''s roster still exists',
            (select count(*)::int from jobsy_sessions where session_code = 'RLS-INITE'), 1);
select t_eq('no membership was self-granted',
            (select count(*)::int from memberships), 3);

-- Adversarial test for 0007. Every case asserts the DATABASE refuses, not that
-- the DDL reads correctly. Prints one row per case; any FAIL is a real defect.
\set ON_ERROR_STOP off
\pset format unaligned
\pset tuples_only on

create or replace function t_reject(label text, stmt text) returns text
language plpgsql as $$
begin
  execute stmt;
  return 'FAIL  (accepted!)  ' || label;
exception when others then
  return 'ok    rejected     ' || label || '  [' || split_part(sqlerrm, E'\n', 1) || ']';
end $$;

create or replace function t_accept(label text, stmt text) returns text
language plpgsql as $$
begin
  execute stmt;
  return 'ok    accepted     ' || label;
exception when others then
  return 'FAIL  (rejected!)  ' || label || '  [' || split_part(sqlerrm, E'\n', 1) || ']';
end $$;

create or replace function t_eq(label text, got anyelement, want anyelement) returns text
language plpgsql as $$
begin
  if got is not distinct from want then
    return 'ok    ' || label || ' = ' || coalesce(got::text, 'null');
  end if;
  return 'FAIL  ' || label || ' = ' || coalesce(got::text,'null') || ', wanted ' || coalesce(want::text,'null');
end $$;

-- ── Fixtures: two partners, three clients, four people ──────────────────
insert into partners (slug, name) values ('acme-consult', 'Acme Consulting') on conflict do nothing;
insert into partners (slug, name) values ('rival-corp',   'Rival Corp')      on conflict do nothing;

insert into orgs (slug, name, partner_id)
select 'northwind', 'Northwind BV', id from partners where slug='acme-consult' on conflict do nothing;
insert into orgs (slug, name, partner_id)
select 'contoso',   'Contoso NV',   id from partners where slug='acme-consult' on conflict do nothing;
insert into orgs (slug, name, partner_id)
select 'initech',   'Initech GmbH', id from partners where slug='rival-corp'   on conflict do nothing;

insert into auth.users (id, email) values
  ('11111111-1111-1111-1111-111111111111', 'consultant@acme-consult.example'),
  ('22222222-2222-2222-2222-222222222222', 'hr@northwind.example'),
  ('33333333-3333-3333-3333-333333333333', 'hr@initech.example'),
  ('44444444-4444-4444-4444-444444444444', 'nobody@nowhere.example')
on conflict do nothing;

insert into memberships (user_id, partner_id, role)
select '11111111-1111-1111-1111-111111111111', id, 'partner_admin' from partners where slug='acme-consult'
on conflict do nothing;
insert into memberships (user_id, org_id, role)
select '22222222-2222-2222-2222-222222222222', id, 'client_admin' from orgs where slug='northwind'
on conflict do nothing;
insert into memberships (user_id, org_id, role)
select '33333333-3333-3333-3333-333333333333', id, 'viewer' from orgs where slug='initech'
on conflict do nothing;
-- user 4 deliberately has no membership at all.

select '── constraints ────────────────────────────────────────────────────';

select t_reject('membership scoped to BOTH a partner and an org', $$
  insert into memberships (user_id, partner_id, org_id, role)
  select '22222222-2222-2222-2222-222222222222', p.id, o.id, 'analyst'
    from partners p, orgs o where p.slug='acme-consult' and o.slug='contoso' $$);

select t_reject('membership scoped to NEITHER', $$
  insert into memberships (user_id, role)
  values ('22222222-2222-2222-2222-222222222222', 'analyst') $$);

select t_reject('partner_admin granted at client scope', $$
  insert into memberships (user_id, org_id, role)
  select '44444444-4444-4444-4444-444444444444', id, 'partner_admin' from orgs where slug='contoso' $$);

select t_reject('viewer granted across a whole partner', $$
  insert into memberships (user_id, partner_id, role)
  select '44444444-4444-4444-4444-444444444444', id, 'viewer' from partners where slug='rival-corp' $$);

select t_reject('invented role', $$
  insert into memberships (user_id, org_id, role)
  select '44444444-4444-4444-4444-444444444444', id, 'superuser' from orgs where slug='contoso' $$);

select t_reject('second membership for the same user+org', $$
  insert into memberships (user_id, org_id, role)
  select '22222222-2222-2222-2222-222222222222', id, 'viewer' from orgs where slug='northwind' $$);

select t_reject('second membership for the same user+partner', $$
  insert into memberships (user_id, partner_id, role)
  select '11111111-1111-1111-1111-111111111111', id, 'partner_analyst' from partners where slug='acme-consult' $$);

select t_reject('membership for a user that does not exist', $$
  insert into memberships (user_id, org_id, role)
  select '99999999-9999-9999-9999-999999999999', id, 'viewer' from orgs where slug='contoso' $$);

select t_reject('org with no partner', $$
  insert into orgs (slug, name) values ('orphan', 'Orphan BV') $$);

select t_reject('session with no org', $$
  insert into jobsy_sessions (session_code) values ('JOBSY-AAAAA') $$);

select t_reject('session pointing at an org that does not exist', $$
  insert into jobsy_sessions (org_id, session_code)
  values ('88888888-8888-8888-8888-888888888888', 'JOBSY-BBBBB') $$);

select t_accept('a legitimate session', $$
  insert into jobsy_sessions (org_id, session_code, org_label, payload)
  select id, 'JOBSY-NORTH', 'Northwind BV', '{"upload_df":[{"name":"redacted"}]}'::jsonb
    from orgs where slug='northwind' $$);

select t_reject('duplicate session_code, even in a different org', $$
  insert into jobsy_sessions (org_id, session_code)
  select id, 'JOBSY-NORTH' from orgs where slug='initech' $$);

select t_accept('a second session in a different org', $$
  insert into jobsy_sessions (org_id, session_code, org_label)
  select id, 'JOBSY-INITE', 'Initech GmbH' from orgs where slug='initech' $$);

select '';
select '── who can reach what ──────────────────────────────────────────────';

-- Partner staff: both Acme clients, neither of Rival's.
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
select t_eq('acme consultant: org count', (select count(*)::int from app.member_org_ids()), 2);
select t_eq('  reaches northwind', (select app.can_access_org(id) from orgs where slug='northwind'), true);
select t_eq('  reaches contoso',   (select app.can_access_org(id) from orgs where slug='contoso'),   true);
select t_eq('  BLOCKED from initech (other partner)',
            (select app.can_access_org(id) from orgs where slug='initech'), false);
select t_eq('  admins northwind (via partner_admin)',
            (select app.is_org_admin(id) from orgs where slug='northwind'), true);

-- Client staff: exactly their own company.
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
select t_eq('northwind HR: org count', (select count(*)::int from app.member_org_ids()), 1);
select t_eq('  reaches northwind', (select app.can_access_org(id) from orgs where slug='northwind'), true);
select t_eq('  BLOCKED from contoso (same partner, other client)',
            (select app.can_access_org(id) from orgs where slug='contoso'), false);
select t_eq('  admins northwind', (select app.is_org_admin(id) from orgs where slug='northwind'), true);

-- A viewer administers nothing.
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
select t_eq('initech viewer: org count', (select count(*)::int from app.member_org_ids()), 1);
select t_eq('  reaches initech', (select app.can_access_org(id) from orgs where slug='initech'), true);
select t_eq('  does NOT admin initech (viewer)',
            (select app.is_org_admin(id) from orgs where slug='initech'), false);

-- No membership: nothing.
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
select t_eq('unaffiliated user: org count', (select count(*)::int from app.member_org_ids()), 0);
select t_eq('  reaches northwind', (select app.can_access_org(id) from orgs where slug='northwind'), false);

-- No session at all.
reset request.jwt.claim.sub;
select t_eq('anonymous: org count', (select count(*)::int from app.member_org_ids()), 0);
select t_eq('  can_access_org(null) is false, not null', app.can_access_org(null), false);

select '';
select '── the shape of the thing ──────────────────────────────────────────';
-- Stated as "none of them break the rule" rather than "there are exactly three",
-- so these keep holding as later migrations add helpers. The first version
-- counted to 3 and started failing the moment 0008 added its own -- which is a
-- test reporting its own staleness, not a defect in the code.
select t_eq('the app schema has helpers in it',
            (select count(*)::int from pg_proc p join pg_namespace n on n.oid=p.pronamespace
              where n.nspname='app') >= 3, true);
select t_eq('NO app function leaves search_path unpinned',
            (select count(*)::int from pg_proc p join pg_namespace n on n.oid=p.pronamespace
              where n.nspname='app' and p.proconfig is null), 0);
select t_eq('NO app function is SECURITY INVOKER',
            (select count(*)::int from pg_proc p join pg_namespace n on n.oid=p.pronamespace
              where n.nspname='app' and not p.prosecdef), 0);
select t_eq('anon cannot execute them',
            (select bool_or(has_function_privilege('anon', p.oid, 'execute'))
               from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='app'), false);
select t_eq('RLS on partners',       (select relrowsecurity from pg_class where relname='partners'), true);
select t_eq('RLS on memberships',    (select relrowsecurity from pg_class where relname='memberships'), true);
select t_eq('RLS on jobsy_sessions', (select relrowsecurity from pg_class where relname='jobsy_sessions'), true);
-- 0007 deliberately wrote no policies; 0008 writes them and its own test file
-- proves what they do. Asserting "zero policies" here only held until the next
-- migration landed, so what stays true is that RLS is on -- checked above.
select t_eq('anon has no grant on jobsy_sessions',
            (select bool_or(has_table_privilege('anon','jobsy_sessions', p))
               from unnest(array['select','insert','update','delete']) p), false);
select t_eq('every org has a partner',
            (select count(*)::int from orgs where partner_id is null), 0);

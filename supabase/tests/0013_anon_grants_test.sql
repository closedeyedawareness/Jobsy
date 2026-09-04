-- 0013_anon_grants_test.sql — anon reaches nothing, as a property.
--
-- 0008 asserted this by revoking from a list of 23 table names. The list was
-- already two short. A test that checks the same list would be wrong in exactly
-- the same way, so this asks the CATALOGUE instead: whatever tables exist, anon
-- must hold no grant on any of them. Add a table tomorrow and forget to revoke,
-- and this fails without anyone having to remember it exists.

-- Same psql settings as every other test file here. Without them psql prints
-- column headers and row counts, run.sh's `grep -c '^ok'` matches nothing, and
-- the file contributes ZERO assertions to the total while appearing to run --
-- the same silent-nonparticipation the runner's error check was added to catch,
-- arriving through a door that check does not cover.
\set ON_ERROR_STOP off
\pset format unaligned
\pset tuples_only on

create or replace function t_eq(label text, got anyelement, want anyelement) returns text
language plpgsql as $$
begin
  if got is not distinct from want then
    return 'ok    ' || label || ' = ' || coalesce(got::text, 'null');
  end if;
  return 'FAIL  ' || label || ' — got ' || coalesce(got::text, 'null')
                  || ', want ' || coalesce(want::text, 'null');
end $$;

create or replace function t_reject(label text, stmt text) returns text
language plpgsql as $$
begin
  execute stmt;
  return 'FAIL  ' || label || ' — the statement was ACCEPTED';
exception when others then
  return 'ok    rejected     ' || label || '  [' || sqlerrm || ']';
end $$;

select '';
select '── anon holds no grant anywhere in public ─────────────────────────';

select t_eq('no table in public grants anything to anon',
            (select count(*)::int from information_schema.role_table_grants
              where grantee = 'anon' and table_schema = 'public'), 0);

-- Named explicitly because these two are the ones 0008's hand-maintained list
-- missed, and a regression here would most likely be someone reinstating that
-- list. They carry bonus targets and pay element definitions.
select t_eq('  including pay_mix, which 0008 missed',
            (select count(*)::int from information_schema.role_table_grants
              where grantee = 'anon' and table_name = 'pay_mix'), 0);
select t_eq('  and pay_elements, which it missed too',
            (select count(*)::int from information_schema.role_table_grants
              where grantee = 'anon' and table_name = 'pay_elements'), 0);

select '';
select '── and cannot read through them either ────────────────────────────';
--
-- The grants are the second layer. This is the first: even had a grant
-- survived, RLS denies by default because no policy names anon. Both are
-- checked, because the whole point of belt and braces is that neither one
-- alone is the thing being relied on.

set role anon;
select t_reject('anon selecting pay_mix', $$select * from pay_mix$$);
select t_reject('anon selecting pay_elements', $$select * from pay_elements$$);
select t_reject('anon selecting salary_bands', $$select * from salary_bands$$);
select t_reject('anon selecting employees', $$select * from employees$$);
reset role;

select '';
select '── future tables are covered without anyone remembering ───────────';

create table if not exists anon_grant_canary (id int primary key);
-- Deliberately WITHOUT revoking: 0013's ALTER DEFAULT PRIVILEGES has to be what
-- keeps this clean. If someone replaces that with another explicit list, this
-- line starts failing and says why.
select t_eq('a table created after 0013 grants nothing to anon',
            (select count(*)::int from information_schema.role_table_grants
              where grantee = 'anon' and table_name = 'anon_grant_canary'), 0);
drop table if exists anon_grant_canary;

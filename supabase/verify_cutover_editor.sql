-- verify_cutover_editor.sql — the same eleven checks as verify_cutover.sql,
-- as ONE query you can paste into the Supabase SQL editor.
--
-- verify_cutover.sql uses psql meta-commands (\pset, \t) which the web SQL
-- editor does not understand -- it speaks SQL, not psql. Same checks, same
-- wording, one result set. Read-only, safe to run any time, any environment.
--
-- Every row must start with `ok`. Any `CHECK` row means stop.

select * from (
  select 1 as n, case when count(*)=0 then 'ok    all of 0007-0013 landed'
              else 'CHECK missing: '||string_agg(t,', ') end as result
  from (select unnest(array['partners','memberships','jobsy_sessions','activity_log','countries']) t) x
  where to_regclass('public.'||t) is null
union all
  select 2, case when bool_or(is_library_source) then 'ok    library org is flagged as shared source'
              else 'CHECK no org has is_library_source - clients will see an EMPTY app' end from orgs
union all
  select 3, case when count(*)=0 then 'ok    every org belongs to a partner'
              else 'CHECK '||count(*)||' org(s) with no partner_id' end from orgs where partner_id is null
union all
  select 4, case when count(*)>=40 then 'ok    '||count(*)||' RLS policies in place'
              else 'CHECK only '||count(*)||' policies - 0008 did not fully apply' end
  from pg_policies where schemaname='public'
union all
  select 5, case when count(*)=0 then 'ok    RLS enabled on every public table'
              else 'CHECK RLS is OFF on: '||string_agg(relname,', ') end
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relkind='r' and not c.relrowsecurity
union all
  select 6, case when count(*)=10 then 'ok    country registry seeded'
              else 'CHECK countries has '||count(*)||' rows, expected 10' end from countries
union all
  select 7, case when count(*)=1 then 'ok    NL is the only live market'
              else 'CHECK '||count(*)||' live markets' end from countries where is_live
union all
  select 8, case when count(*)>0 then 'ok    '||count(*)||' membership(s) exist'
              else 'CHECK memberships is EMPTY - after the key swap nobody can reach anything, including you' end
  from memberships
union all
  select 9, case when count(*)=0 then 'ok    nobody granted against the library org'
              else 'CHECK '||count(*)||' membership(s) point at the library org' end
  from memberships m join orgs o on o.id=m.org_id where o.is_library_source
union all
  select 10, case when count(*)=0 then 'ok    anon cannot reach any table'
              else 'CHECK anon holds grants on: '||string_agg(distinct table_name,', ') end
  from information_schema.role_table_grants where grantee='anon' and table_schema='public'
) checks order by n;

-- verify_cutover.sql — is the fence actually up?
--
-- Read-only. Safe to run at any time, against any environment, as often as you
-- like. Run it after applying 0007-0012 and before swapping the app's key:
--
--     psql "$DATABASE_URL" -f supabase/verify_cutover.sql
--
-- Every line must say `ok`. A `CHECK` line means do not proceed to the key swap.
--
-- This asks the database what is true rather than reading the DDL back, for the
-- reason the whole test suite exists: `drop constraint if exists` with a wrong
-- name applies cleanly and does nothing, so "the migration ran" is not evidence
-- that it did anything.

\pset pager off
\t on

select case when count(*) = 0 then 'ok    every migration 0007-0012 landed'
            else 'CHECK missing tables: ' || string_agg(t, ', ') end
from (select unnest(array['partners','memberships','jobsy_sessions','activity_log','countries']) as t) x
where to_regclass('public.' || t) is null;

select case when bool_and(has) then 'ok    the library org is flagged as the shared source'
            else 'CHECK no org has is_library_source — every client will see an EMPTY app' end
from (select bool_or(is_library_source) as has from orgs) x;

select case when count(*) = 0 then 'ok    every client org belongs to a partner'
            else 'CHECK ' || count(*) || ' org(s) with no partner_id' end
from orgs where partner_id is null;

select case when count(*) >= 40 then 'ok    ' || count(*) || ' row-level security policies are in place'
            else 'CHECK only ' || count(*) || ' policies — 0008 did not fully apply' end
from pg_policies where schemaname = 'public';

-- The table 0008 exists to protect. RLS enabled with no policy denies everything,
-- which is safe; RLS DISABLED is the failure that looks like success, because the
-- app keeps working while the fence is not there.
select case when count(*) = 0 then 'ok    row-level security is enabled on every public table'
            else 'CHECK RLS is OFF on: ' || string_agg(relname, ', ') end
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity;

select case when count(*) = 10 then 'ok    the country registry is seeded'
            else 'CHECK countries has ' || count(*) || ' rows, expected 10' end
from countries;

select case when count(*) = 1 then 'ok    NL is the only live market'
            else 'CHECK ' || count(*) || ' live markets — a market with no data was opened' end
from countries where is_live;

select case when count(*) = 0 then 'ok    no priced row is missing a country'
            else 'CHECK ' || count(*) || ' salary bands with no country' end
from salary_bands where country is null;

-- Not a failure on its own -- it is correct immediately after migration -- but it
-- is the single most likely reason the app appears dead after the key swap, so it
-- is worth seeing the number before you make the swap rather than after.
select case when count(*) > 0 then 'ok    ' || count(*) || ' membership(s) exist'
            else 'CHECK memberships is EMPTY — after the key swap nobody can reach '
                 'anything, including you. Run tools/manage_users.py first.' end
from memberships;

-- A grant against the library org is a real mistake and an easy one: `default`
-- looks like an ordinary org in every listing.
select case when count(*) = 0 then 'ok    nobody is granted against the library org'
            else 'CHECK ' || count(*) || ' membership(s) point at the library org, not a client' end
from memberships m join orgs o on o.id = m.org_id where o.is_library_source;

select case when count(*) = 0 then 'ok    anon cannot reach any table directly'
            else 'CHECK anon holds grants on: ' || string_agg(distinct table_name, ', ') end
from information_schema.role_table_grants
where grantee = 'anon' and table_schema = 'public';

\t off

-- The invariant the app's library cache rests on.
--
-- ui/shared.load_workbook_catalog caches the reference library per ORG and
-- shares that one object between every browser session belonging to that org.
-- Streamlit serves all sessions from one process, so this is only safe while
-- every reference table's read policy depends on ORG MEMBERSHIP ALONE. The
-- moment one of them starts consulting the member's role, two people in the
-- same client see different rows, and a cache keyed on the org would hand the
-- first person's view to the second.
--
-- That is not a hypothetical shape: activity_log and library_audit already read
-- through app.is_org_admin(org_id), and they are deliberately NOT in the list
-- below. This file exists to notice the day a reference table joins them.
--
-- Runs against the migrated database like its siblings; asserts on the
-- catalogue, because the claim is about the policies as the database holds
-- them, not about what a migration file says it created.
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

-- Every sheet SHEET_MAP loads, by its table name. Kept as a literal list rather
-- than derived, so adding a table to the library is a decision that has to be
-- taken here too.
create temporary table library_tables(name text) on commit preserve rows;
insert into library_tables(name) values
  ('jobs'), ('job_profiles'), ('salary_bands'), ('title_mapping'), ('career_paths'),
  ('levels'), ('categories'), ('skills'), ('competency_levels'), ('role_skill_map'),
  ('job_grades'), ('industries'), ('industry_salary_factors'), ('industry_skills'),
  ('seniority_levels'), ('skill_proficiency'), ('benefits_catalog'),
  ('benefits_observations'), ('level_benefits_factors'), ('pay_mix'), ('pay_elements');

-- 1. Every one of them has RLS on. A table without it is readable by anyone
--    holding any key, which no amount of policy correctness elsewhere fixes.
select t_eq('library tables with RLS disabled',
  (select count(*)::int from library_tables l
     join pg_class c on c.relname = l.name
     join pg_namespace n on n.oid = c.relnamespace and n.nspname = 'public'
    where not c.relrowsecurity), 0);

-- 2. Every one of them has exactly one SELECT policy for `authenticated`.
select t_eq('library tables without a single authenticated read policy',
  (select count(*)::int from library_tables l
    where (select count(*) from pg_policies p
            where p.schemaname = 'public' and p.tablename = l.name
              and p.cmd = 'SELECT' and p.roles::text like '%authenticated%') <> 1), 0);

-- 3. THE ONE THAT MATTERS. Each of those policies is exactly the org-membership
--    predicate — not a variation, not a superset, not something role-aware.
select t_eq('library read policies that are not app.can_read_org(org_id)',
  (select count(*)::int from library_tables l
     join pg_policies p on p.schemaname = 'public' and p.tablename = l.name
                        and p.cmd = 'SELECT'
    where p.qual <> 'app.can_read_org(org_id)'), 0);

-- 4. And the counterexample, so the test above is known to be capable of
--    failing: the audit tables ARE role-dependent, and must stay outside the
--    list. If this ever reads 0, someone has flattened the distinction.
select t_eq('audit tables still read on admin rights, not plain membership',
  (select count(*)::int from pg_policies
    where schemaname = 'public' and cmd = 'SELECT'
      and tablename in ('activity_log', 'library_audit')
      and qual like '%is_org_admin%'), 2);

drop table library_tables;

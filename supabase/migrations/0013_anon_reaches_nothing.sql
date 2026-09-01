-- 0013_anon_reaches_nothing.sql
--
-- 0008 §5 says, correctly:
--
--   "Not one policy above names anon, so an unauthenticated caller holding the
--    publishable key reaches nothing... The revokes are belt and braces, for
--    the reason 0003 established — Supabase grants privileges to anon BY NAME,
--    so a `revoke ... from public` would not touch them."
--
-- The intent is right. The implementation is a HAND-MAINTAINED LIST of 23
-- table names, and it is already out of date: `pay_mix` and `pay_elements`
-- arrived in 0004, after that list was written in 0003 and copied forward into
-- 0008, and nobody added them. So anon held grants on the two tables that carry
-- bonus targets and pay element definitions.
--
-- Found by supabase/verify_cutover.sql before the cutover, not by a person
-- reading the list -- which is the point, because reading a list of 23 names
-- and noticing the two that are absent is not something people are good at.
--
-- ── HOW BAD WAS IT ────────────────────────────────────────────────────────
--
-- Not exploitable. Demonstrated rather than assumed:
--
--     set role anon;
--     select count(*) from pay_mix;   -- 0 rows
--
-- RLS is enabled on both tables and no policy names anon, so the grant was
-- unreachable: deny-by-default held. What was broken was the second layer, and
-- the second layer is exactly what you want intact on the day somebody adds a
-- permissive policy for a good reason, or disables RLS on one table while
-- debugging and forgets. Belt and braces is worth nothing if only the belt is
-- ever checked.
--
-- ── THE FIX IS NOT TWO MORE NAMES ─────────────────────────────────────────
--
-- Adding 'pay_mix' and 'pay_elements' to the list would leave the next table to
-- be added in precisely the same position. The invariant is "anon reaches
-- NOTHING in public" -- so it is read from the catalogue, and a table created
-- tomorrow is covered the moment this runs. 0003's reasoning about grants being
-- BY NAME is preserved: this still revokes from anon specifically.
--
-- Re-runnable, like every migration here.

do $$
declare t record;
begin
  for t in
    select c.relname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relkind in ('r', 'p', 'v', 'm')     -- tables, partitions, views
  loop
    execute format('revoke all on public.%I from anon', t.relname);
  end loop;
end $$;

-- Future tables, so this does not become another list to forget. ALTER DEFAULT
-- PRIVILEGES only affects objects created by the role that runs it, which is
-- why it is a complement to the loop above and not a replacement for it.
alter default privileges in schema public revoke all on tables from anon;

-- And assert it, rather than trusting that the loop above did what it reads
-- like. A migration that applies cleanly and achieves nothing is the specific
-- failure this project has already been bitten by twice: 0012's `drop
-- constraint if exists` with an invented name, and the two SQL assertions that
-- raised instead of asserting while the suite reported them as passes.
do $$
declare leftover text;
begin
  select string_agg(distinct table_name, ', ')
    into leftover
  from information_schema.role_table_grants
  where grantee = 'anon' and table_schema = 'public';

  if leftover is not null then
    raise exception 'anon still holds grants in public on: %', leftover;
  end if;
end $$;

-- 0022 — the last table in the schema with RLS off
--
-- Applied 2026-09-06. Supabase's own advisor flagged it: library_review_policy
-- was fully exposed to the anon and authenticated roles, so anyone holding the
-- anon key could read AND rewrite the intervals that decide when reference data
-- gets looked at again. Setting review_after_months to null on every row would
-- stop the review surfacing anything, and nothing would appear broken. A
-- governance table that can be silently disarmed is worse than no governance
-- table, because it also carries the belief that something is being watched.
--
-- Two things make this table unlike its neighbours, and they pull opposite ways:
--
--   * no org_id. It is not tenant data -- it says which TABLE needs re-reading
--     and why -- so app.can_read_org() has nothing to key on and the usual
--     policy shape does not apply.
--   * ops_jobsy_review() is SECURITY INVOKER, so it runs as the caller and
--     feels this immediately. A read policy is required, not optional. Verified
--     after applying: the function still returns all 21 rows.
--
-- So: readable by any signed-in user, writable by none through the API. anon
-- reaches nothing, per 0013. Edits keep working from SQL, the dashboard and
-- migrations because service_role bypasses RLS -- which is what "editable
-- without a deploy" meant, and it stays true.

alter table public.library_review_policy enable row level security;

create policy library_review_policy_read
  on public.library_review_policy
  for select to authenticated
  using (true);

-- Deliberately no write policy. With RLS on and none for insert, update or
-- delete, all three are denied to anon and authenticated alike. Anyone who
-- should be changing a review interval is doing it as service_role or in a
-- migration, where the change is recorded and reviewable.

comment on table public.library_review_policy is
  'How often each reference-library table needs looking at again, and why. '
  'NULL months = no interval, because the table is this product''s own construct '
  'rather than a reading of a market. Editable without a deploy: ops_jobsy_review() '
  'drives entirely off these rows. RLS enabled 2026-09-06 -- readable by any '
  'signed-in user because it holds no tenant data, writable by none through the '
  'API because a silently widened review interval is a defect nobody would see.';

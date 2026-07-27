-- 0005_lock_down_functions.sql
--
-- From the Supabase security advisor, run after 0004. Three findings; two are
-- real and fixed here, the third is deliberate and stays.
--
-- 1. log_library_change() was callable over the REST API.
--
--    It is SECURITY DEFINER — it has to be, so writes reach library_audit
--    through the trigger even from roles with no privilege on that table
--    (see 0003). But PostgREST exposes every function in the `public` schema
--    as /rest/v1/rpc/<name>, and EXECUTE was granted to anon and authenticated
--    by default. So the one function specifically built to run with elevated
--    rights was reachable by anyone holding the publishable key.
--
--    In practice a direct call errors out — TG_OP and NEW are undefined
--    outside a trigger — so this is exposure rather than a demonstrated
--    exploit. It is still precisely the wrong function to leave callable, and
--    "it happens to fail" is not an access control.
--
-- 2. Mutable search_path on set_updated_at() and add_constraint_if_absent().
--
--    A function without a pinned search_path resolves its object references
--    against whatever the caller's search_path says. log_library_change()
--    already pinned it; these two were missed.
--
-- 3. RLS enabled with no policy, on every table. Intentional — see the note at
--    the end of 0001. Until auth lands there is no org claim to filter on, and
--    a permissive policy written now is a hole nobody remembers to close. The
--    advisor reports it at INFO, which is the right severity for a deliberate
--    choice: it means "reachable by nobody", and that is the intent.

revoke execute on function log_library_change() from public;
revoke execute on function log_library_change() from anon;
revoke execute on function log_library_change() from authenticated;

-- The trigger does not need this grant: a trigger function is invoked by the
-- executor, not called by the session role, so it keeps firing for every write.
-- Verified by writing a row afterwards and finding the audit entry.

-- Migration plumbing, not application surface.
revoke execute on function add_constraint_if_absent(text, text, text) from public;
revoke execute on function add_constraint_if_absent(text, text, text) from anon;
revoke execute on function add_constraint_if_absent(text, text, text) from authenticated;

alter function set_updated_at() set search_path = public;
alter function add_constraint_if_absent(text, text, text) set search_path = public;

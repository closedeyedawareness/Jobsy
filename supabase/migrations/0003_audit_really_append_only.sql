-- 0003_audit_really_append_only.sql
--
-- 0001 ended with:
--     revoke update, delete on library_audit from public;
-- and a comment claiming the audit trail was therefore append-only. It was not.
--
-- Supabase grants ALL privileges on new tables to anon, authenticated,
-- service_role and postgres EXPLICITLY. A revoke from `public` removes a grant
-- those roles never relied on, so every one of them kept DELETE and TRUNCATE.
-- RLS covers anon and authenticated (no policy exists, so they reach nothing),
-- but service_role bypasses RLS by design — and service_role is exactly what
-- the importer and the DB loader authenticate as. The tamper-evidence the
-- schema was supposed to provide was decorative.
--
-- Checked, not assumed: information_schema.role_table_grants listed
-- DELETE, TRUNCATE, UPDATE for all four roles after 0001 ran.
--
-- The trigger keeps working: log_library_change() is SECURITY DEFINER and runs
-- as its owner, so it can still insert into a table the calling role cannot
-- write to directly. That is the whole point — writes arrive only through the
-- trigger, never from application code.

revoke insert, update, delete, truncate on library_audit from anon;
revoke insert, update, delete, truncate on library_audit from authenticated;
revoke insert, update, delete, truncate on library_audit from service_role;

-- Reading the trail is fine and useful; changing it is not.
grant select on library_audit to service_role;

-- Same reasoning for the revisions table: a revision is a historical fact.
revoke update, delete, truncate on library_revisions from anon;
revoke update, delete, truncate on library_revisions from authenticated;
revoke update, delete, truncate on library_revisions from service_role;
grant select, insert on library_revisions to service_role;

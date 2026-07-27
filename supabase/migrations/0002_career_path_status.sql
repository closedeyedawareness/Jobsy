-- 0002_career_path_status.sql
--
-- CareerPaths.Status is not the governance column.
--
-- 0001 mapped every sheet's Status onto the shared governance status, whose
-- vocabulary is active | draft | retired. That is right for 19 of the 20
-- sheets. CareerPaths uses the same column name for something else entirely:
-- 8 of its 80 rows say 'Terminal', meaning this role is the top of its ladder.
-- All 8 have a null NextJobID, so it is a statement about the career structure,
-- not about whether the row is live.
--
-- Found by importing the real workbook and watching the check constraint refuse
-- it — which is the constraint doing its job. Collapsing the two meanings would
-- have either loosened the governance vocabulary for every table or silently
-- rewritten 'Terminal' to 'active' and lost the fact.
--
-- So it gets its own column. Terminality is currently implied by next_job_id
-- being null, but a derived truth and a recorded one are different things: the
-- library states it deliberately, and a role can have no successor mapped yet
-- without that meaning the ladder ends there.

alter table career_paths
  add column if not exists path_status text;

comment on column career_paths.path_status is
  'Career-structure status from the workbook (e.g. Active, Terminal). Distinct '
  'from the governance status column, which is active|draft|retired.';

-- Terminal must mean what it says: no successor.
select add_constraint_if_absent('career_paths', 'career_paths_terminal_has_no_next',
  $c$check (path_status is distinct from 'Terminal' or next_job_id is null)$c$);

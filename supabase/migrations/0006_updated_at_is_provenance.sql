-- 0006_updated_at_is_provenance.sql
--
-- updated_at holds the WORKBOOK's UpdatedAt, and a trigger was overwriting it.
--
-- 0001 mapped the sheet's UpdatedAt onto updated_at — the whole point being to
-- adopt the provenance trail somebody has been keeping by hand rather than
-- invent a parallel one. It also put a BEFORE UPDATE trigger on every table
-- setting updated_at := now(). The two cannot both be true.
--
-- The first import inserted rows, so the trigger stayed quiet and the workbook
-- dates landed correctly. The SECOND import upserted, every upsert became an
-- UPDATE, and the trigger replaced 2026-07-02 with the moment the import ran.
-- Found by comparing library_audit's old_row against new_row after Elmar ran
-- the importer twice:
--     old 2026-07-02T00:00:00  ->  new 2026-07-27T18:49:28
--
-- It matters beyond tidiness. The Data Quality page reads UpdatedAt to report
-- how stale each part of the library is, and W3 will point it at the database.
-- Every re-import would have reset every sheet to "updated today", so the one
-- signal that can say whether salary data is a year old would always have read
-- green.
--
-- Two different facts had been given one column:
--   * WHEN THE CONTENT WAS LAST REVISED — a human statement, owned by whoever
--     maintains the library. That is updated_at.
--   * WHEN THIS DATABASE ROW LAST CHANGED — a mechanical fact. That is already
--     recorded, per row and per column, in library_audit.
--
-- So the trigger is not replaced with a cleverer trigger; it is removed. The
-- second fact already had a home. jobsy_sessions keeps its own touch trigger —
-- there, updated_at genuinely does mean "when this row was last written".

do $$
declare
  t text;
  ref_tables text[] := array[
    'jobs', 'job_profiles', 'salary_bands', 'title_mapping', 'career_paths',
    'levels', 'employees', 'categories', 'skills', 'competency_levels',
    'role_skill_map', 'job_grades', 'industries', 'industry_salary_factors',
    'industry_skills', 'seniority_levels', 'skill_proficiency',
    'benefits_catalog', 'benefits_observations', 'level_benefits_factors',
    'pay_elements', 'pay_mix'
  ];
begin
  foreach t in array ref_tables loop
    execute format('drop trigger if exists %I on %I', t || '_set_updated_at', t);
  end loop;

  -- Put back what the trigger overwrote, from the audit trail's own record of
  -- it. Per row, the earliest UPDATE whose updated_at actually changed holds
  -- the value that was there before — which is the workbook's. This is the
  -- append-only trail earning its keep on the day it was written.
  foreach t in array ref_tables loop
    execute format($f$
      update %I x
         set updated_at = r.original
        from (
          select distinct on (row_id)
                 row_id,
                 (old_row->>'updated_at')::timestamptz as original
            from library_audit
           where table_name = %L
             and action = 'UPDATE'
             and old_row->>'updated_at' is distinct from new_row->>'updated_at'
           order by row_id, id asc
        ) r
       where x.id = r.row_id
    $f$, t, t);
  end loop;
end $$;

-- set_updated_at() itself stays: jobsy_sessions still uses that pattern, and
-- dropping a function another table's trigger depends on would be a different
-- kind of mistake.

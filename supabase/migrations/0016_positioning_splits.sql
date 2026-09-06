-- 0016_positioning_splits.sql
--
-- The owner's answers to §4.1, §4.2 and §4.3 of docs/country-data-tiers.md,
-- taken 6 September 2026. 0015 recorded those three as ARGUABLE, NOT YET
-- DECIDED on the objects themselves; this migration replaces the questions with
-- the answers and builds the two that are structural.
--
--   §4.1 job profiles      -> (c) SPLIT. Descriptive fields stay universal;
--                             the positioning claim becomes country-scoped.
--   §4.3 seniority levels  -> the same shape, because it is the same question.
--   §4.2 competency levels -> the product's own five-level scale STAYS.
--
-- ── WHY §4.2 CAME BACK THE OTHER WAY ──────────────────────────────────────
--
-- It was first answered "EQF", and then the question turned out to have been
-- put wrongly. It had been framed as five rungs against eight — the same axis
-- at different granularity, where the only cost is a lossy inverse. Reading the
-- five rows settles that it is not: they describe HOW WELL SOMEBODY PERFORMS A
-- SKILL ("applies with support in straightforward situations", "coaches
-- others", "recognised authority"), and the EQF describes the LEARNING OUTCOMES
-- OF A QUALIFICATION — knowledge, skills, responsibility and autonomy attaching
-- to a diploma. Two axes, not two resolutions of one.
--
-- Put back plainly, the answer was that the current levels work. So they stay,
-- and the comment on the table now records that as a decision with its reason
-- rather than leaving a question open that has been closed.
--
-- The consequence worth writing down: a proficiency rating in this product is
-- NOT a qualification level and must never be rendered as one. Anchoring it to
-- an EQF number would have put a credential claim on a performance rating.
--
-- ── SHAPE OF BOTH SPLITS ──────────────────────────────────────────────────
--
-- Additive and reversible. Two new tables; NO column is dropped from
-- job_profiles or seniority_levels, for the same reason 0015 kept statutory_nl:
-- core/models, core/repository, services/library_import_service and four
-- scripts under tools/ and projects/ read the flat shape today, and a rename
-- that breaks an import is a rename that gets reverted under pressure.
--
-- The old columns and the new tables hold the same values after this migration.
-- What must be true before the old columns may be dropped is listed at §3.
--
-- Every existing row is Dutch (measured 2026-09-06, all eight country-carrying
-- tables), so country = 'NL' on the copied rows is a statement of fact.

-- ══════════════════════════════════════════════════════════════════════════
-- 1. job_profile_positioning — §4.1(c)
-- ══════════════════════════════════════════════════════════════════════════
--
-- What a Financial Controller DOES is not a Dutch fact. Where that role SITS is.
-- `management_level` is a positioning claim against a national grading
-- instrument — the functiegroep in the Netherlands, set per CAO; ERA in
-- Germany; the conventions collectives in France — and "management level: Lead"
-- asserts a rung in a ladder that is a different ladder across the border.
--
-- So the description, responsibilities, skills, specialisms and tools stay in
-- job_profiles as one universal row, and only the positioning gets a country.
-- Option (b) — a whole profile per market — would have meant seven copies of a
-- description that would drift apart for no reason anybody could name.

create table if not exists job_profile_positioning (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references orgs(id) on delete cascade,
  country          text not null references countries(code),
  job_id           text not null,
  management_level text not null default '',

  -- The governance columns every library table carries, so this one can take
  -- part in revisions, retirement and effective dating instead of being the
  -- single table history skips.
  revision_id      uuid references library_revisions(id),
  status           text default 'active'
                     check (status in ('active', 'draft', 'retired')),
  owner            text,
  source           text,
  effective_from   date,
  effective_to     date,
  created_at       timestamptz default now(),
  updated_at       timestamptz default now(),
  updated_by       text,

  constraint jpp_dates_ordered
    check (effective_to is null or effective_from is null
           or effective_from <= effective_to),
  constraint jpp_country_job_uniq unique (org_id, country, job_id)
);

create index if not exists jpp_org_country_idx on job_profile_positioning (org_id, country);

-- ══════════════════════════════════════════════════════════════════════════
-- 2. seniority_grade_binding — §4.3
-- ══════════════════════════════════════════════════════════════════════════
--
-- The same question, so the same answer. L1..L5 and Starter/Developing/
-- Senior/Manager/Rising Star are this product's own naming and belong to no
-- country; duplicating five rows per market to restate identical text is the
-- drift 0012 was written to prevent.
--
-- What is national is the BINDING. `grade_range '7-10'` and
-- `maps_to_level 'Senior'` point into job_grades, which is keyed
-- (org_id, country, grade) and holds fourteen rows for the Netherlands. There
-- is no reason a Belgian ladder would have fourteen. Held in a table with no
-- country, "L3 covers grades 7-10" is a claim about a national grade ladder
-- that cannot say which nation — and once a second ladder exists it means
-- something else there, or nothing.
--
-- `grades` ("Grade 7-10") travels with grade_range because it is the same fact
-- spelled for a reader.

create table if not exists seniority_grade_binding (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references orgs(id) on delete cascade,
  country        text not null references countries(code),
  l_code         text not null,
  grade_range    text not null default '',
  maps_to_level  text not null default '',
  grades         text not null default '',

  revision_id    uuid references library_revisions(id),
  status         text default 'active'
                   check (status in ('active', 'draft', 'retired')),
  owner          text,
  source         text,
  effective_from date,
  effective_to   date,
  created_at     timestamptz default now(),
  updated_at     timestamptz default now(),
  updated_by     text,

  constraint sgb_dates_ordered
    check (effective_to is null or effective_from is null
           or effective_from <= effective_to),
  constraint sgb_country_lcode_uniq unique (org_id, country, l_code)
);

create index if not exists sgb_org_country_idx on seniority_grade_binding (org_id, country);

-- ══════════════════════════════════════════════════════════════════════════
-- 3. COPY THE EXISTING ROWS IN, AS DUTCH
-- ══════════════════════════════════════════════════════════════════════════
--
-- `on conflict do nothing` so re-running this migration is not a way to
-- overwrite a market's positioning with the Dutch one.
--
-- These copies run BEFORE the audit trigger is attached at §4, so they do not
-- appear in library_audit. That is deliberate: the trail records who CHANGED
-- the library, and a schema migration moving a value from one column to another
-- is not somebody's edit. The provenance of these rows is this file.  Any write
-- after the migration is audited normally.
--
-- BEFORE job_profiles.management_level OR seniority_levels.{grade_range,
-- maps_to_level, grades} MAY BE DROPPED, ALL OF THESE MUST HOLD:
--
--   (a) core/models.JobProfile and .SeniorityLevel read the new tables;
--   (b) core/repository builds them per market, the way it now builds salary
--       bands, pay elements and the benefits catalogue — country, then the EU
--       baseline, then NOTHING;
--   (c) services/library_import_service.SPECS maps the workbook headings
--       ManagementLevel / GradeRange / MapsToLevel / Grades onto the new
--       tables, or the workbook has been reissued;
--   (d) the four readers under tools/ and projects/art4-job-evaluation/ are
--       updated — build_rating_sheet.py, extract_scoring_baseline.py, rate.py
--       and enrich_reference_library.py;
--   (e) select count(*) from job_profiles p join job_profile_positioning q
--       using (org_id, job_id) where q.country = 'NL'
--         and p.management_level is distinct from q.management_level
--       returns 0, and the equivalent for seniority — i.e. no writer has
--       updated one side and not the other in the interval.
--
-- (e) is why there is no trigger keeping them in sync, exactly as in 0015 §3:
-- a trigger would force agreement and hide the writer still using the old
-- column. The check is how you find that writer. If the counts diverge, find
-- the writer — do not add the trigger.

insert into job_profile_positioning
       (org_id, country, job_id, management_level,
        revision_id, status, owner, source, effective_from, effective_to, updated_by)
select  org_id, 'NL',    job_id, coalesce(management_level, ''),
        revision_id, status, owner, source, effective_from, effective_to, updated_by
  from job_profiles
on conflict (org_id, country, job_id) do nothing;

insert into seniority_grade_binding
       (org_id, country, l_code, grade_range, maps_to_level, grades,
        revision_id, status, owner, source, effective_from, effective_to, updated_by)
select  org_id, 'NL',    l_code,
        coalesce(grade_range, ''), coalesce(maps_to_level, ''), coalesce(grades, ''),
        revision_id, status, owner, source, effective_from, effective_to, updated_by
  from seniority_levels
on conflict (org_id, country, l_code) do nothing;

-- ══════════════════════════════════════════════════════════════════════════
-- 4. RLS AND AUDIT — the same as every sibling, not a lighter version
-- ══════════════════════════════════════════════════════════════════════════
--
-- A new table in a multi-tenant database without row-level security is a
-- tenancy hole, and it is the kind that shows up as nothing at all until
-- somebody looks. Copied from job_grades rather than composed: the predicates
-- app.can_read_org / app.can_write_org already encode who may see what, and a
-- second hand-written version of that rule is a second thing to keep in step.
--
-- The audit trigger too. Writes to client data log through triggers since 0009;
-- a table that skips it is a table whose history silently does not exist.

alter table job_profile_positioning  enable row level security;
alter table seniority_grade_binding  enable row level security;

do $$
declare
  t text;
begin
  foreach t in array array['job_profile_positioning', 'seniority_grade_binding'] loop
    execute format('drop policy if exists %I on %I', t || '_read', t);
    execute format($p$create policy %I on %I for select using (app.can_read_org(org_id))$p$,
                   t || '_read', t);
    execute format('drop policy if exists %I on %I', t || '_write', t);
    execute format($p$create policy %I on %I for all
                     using (app.can_write_org(org_id))
                     with check (app.can_write_org(org_id))$p$,
                   t || '_write', t);
    execute format('grant select, insert, update, delete on %I to authenticated', t);
    execute format('drop trigger if exists %I on %I', t || '_audit', t);
    execute format($g$create trigger %I after insert or update or delete on %I
                      for each row execute function log_library_change()$g$,
                   t || '_audit', t);
  end loop;
end $$;

-- ══════════════════════════════════════════════════════════════════════════
-- 5. THE DECISIONS, RECORDED WHERE THEY ARE READ
-- ══════════════════════════════════════════════════════════════════════════

comment on table job_profile_positioning is
  'COUNTRY-CONDITIONED. The positioning half of a job profile, split out per '
  '§4.1(c) on 2026-09-06. What a role DOES is universal and stays in '
  'job_profiles; where it SITS is a claim against a national grading '
  'instrument — functiegroep in NL, ERA in DE, conventions collectives in FR — '
  'and belongs to a market. Resolves country then the ''EU'' baseline then '
  'nothing, never another market''s rows.';

comment on table seniority_grade_binding is
  'COUNTRY-CONDITIONED. The binding half of a seniority level, split out per '
  '§4.3 on 2026-09-06 — the same question as §4.1 and so the same answer. '
  'grade_range points into job_grades, which is keyed (org_id, country, grade); '
  'a Belgian ladder has no reason to have the Dutch fourteen rungs, so ''7-10'' '
  'means something else there, or nothing.';

comment on table job_profiles is
  'UNIVERSAL as to content — description, responsibilities, skills, '
  'specialisms, tools. §4.1 settled 2026-09-06. management_level is still here '
  'and still read, but it has MOVED to job_profile_positioning; both hold the '
  'same value until the conditions in migration 0016 §3 are met. Do not add a '
  'country column to this table: the split is the answer, not a widening.';

comment on table seniority_levels is
  'UNIVERSAL as to naming — L1..L5 and Starter/Developing/Senior/Manager/Rising '
  'Star are this product''s own and belong to no country. §4.3 settled '
  '2026-09-06. grade_range, maps_to_level and grades are still here and still '
  'read, but they have MOVED to seniority_grade_binding; both hold the same '
  'value until the conditions in migration 0016 §3 are met.';

comment on table competency_levels is
  'UNIVERSAL — the product''s own five-level behavioural scale, and §4.2 was '
  'settled 2026-09-06 in favour of KEEPING it. The question had been put as '
  'five rungs against the EQF''s eight, as though they were one axis at two '
  'resolutions. They are not: these five describe how well somebody performs a '
  'skill, and the EQF describes the learning outcomes of a QUALIFICATION. '
  'CONSEQUENCE: a proficiency rating here is not a qualification level and must '
  'never be rendered as one. Anchoring it to an EQF number would put a '
  'credential claim on a performance rating.';

comment on table career_paths is
  'UNIVERSAL as to sequence, with a real national exception that is not a '
  'question and was never open: progression into some roles is gated by a '
  'national licence or qualification — Germany''s Meister route, regulated '
  'professions generally — and a ladder that ignores that tells a German '
  'employee a step exists that does not. Model the gate where it is modelled; '
  'do not model it as a preference.';

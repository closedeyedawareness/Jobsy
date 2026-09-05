-- 0015_data_tiers.sql
--
-- PROPOSAL. Not applied. See docs/country-data-tiers.md for the reasoning and
-- for the four decisions this migration deliberately does NOT take.
--
-- 0012 gave the priced tables a country dimension and drew a line that still
-- holds: "a country column on a table that does not vary by country is a column
-- that will drift, get half-populated, and then be believed." This finishes the
-- line rather than moving it. Two tables belong on the country side and are not
-- there; one table is already on it and cannot use it.
--
-- Everything below is additive and reversible. Every step is a new column, a new
-- index, or a unique widened to a SUPERSET of itself — and a widened unique
-- accepts every row the narrow one accepted, so nothing that reads the database
-- today reads it differently afterwards. Nothing is dropped. Nothing is
-- backfilled with a value somebody had to guess: every existing row in this
-- database IS Dutch (measured 2026-09-06 — 1 585 rows across the eight
-- country-carrying tables, all 'NL'), so `default 'NL'` is a statement of fact
-- and not a default in the hopeful sense.
--
-- ── WHAT THIS MIGRATION IS NOT THE FIX FOR ────────────────────────────────
--
-- The urgent defect is in the READ path, not here. `core/db_loader._fetch_all`
-- applies no country predicate, and `core/repository._build_salary` keys bands
-- as (function, level) with country dropped — so a Belgian client is served the
-- 45 Dutch bands today, under a sidebar warning that says bands will be empty.
-- Applying this migration does not change that by one line. See §5 of the doc.
-- Sequence the repository fix first; this can wait behind it.

-- ══════════════════════════════════════════════════════════════════════════
-- 1. FINISH 0012 — level_benefits_factors
-- ══════════════════════════════════════════════════════════════════════════
--
-- 0012's loop gave seven tables a country column, a foreign key and an
-- (org_id, country) index. Its unique-widening section then named five of them.
-- level_benefits_factors was not one, so it still carries
--
--     UNIQUE (org_id, level, category)
--
-- which is the pre-0012 key. The column exists, the FK exists, the index exists,
-- and a second country's factor for the same (level, category) is rejected. The
-- table has a country column it cannot populate — the exact condition 0012 was
-- written to remove, surviving inside 0012 itself.
--
-- This is a repair, not a design decision. It changes no data and there is no
-- reading of the tier question under which the current constraint is right.
--
-- ASSUMES: the constraint is named `lbf_org_level_cat_key`. Verified against
-- pg_constraint on 2026-09-06, not guessed — 0012 records what happens when a
-- plausible-sounding name is used with `drop constraint if exists`: the drop
-- succeeds silently, the old unique survives, and the migration achieves
-- nothing. The assertion below turns that silence into a failure.

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'level_benefits_factors'::regclass
      and conname = 'lbf_org_level_cat_key'
  ) and not exists (
    select 1 from pg_constraint
    where conrelid = 'level_benefits_factors'::regclass
      and conname = 'lbf_country_uniq'
  ) then
    raise exception
      'level_benefits_factors: expected unique lbf_org_level_cat_key was not '
      'found and lbf_country_uniq does not exist either. The constraint has been '
      'renamed since 2026-09-06. Re-read pg_constraint before editing this step '
      'rather than adding another `if exists` that can pass by doing nothing.';
  end if;
end $$;

alter table level_benefits_factors drop constraint if exists lbf_org_level_cat_key;

do $$
begin
  perform add_constraint_if_absent('level_benefits_factors', 'lbf_country_uniq',
    $c$unique (org_id, country, level, category)$c$);
end $$;

-- benefits_observations is deliberately untouched. Its unique is
-- (org_id, obs_id) — a surrogate — so country already varies freely underneath
-- it, and `Repository._build_benefit_observations` already keys observations by
-- (industry, category, country). That table is the one thing in this family
-- that is fully correct end to end, and it is the model the others should follow.

-- ══════════════════════════════════════════════════════════════════════════
-- 2. pay_elements AND benefits_catalog BECOME COUNTRY-CONDITIONED
-- ══════════════════════════════════════════════════════════════════════════
--
-- Both tables hold a column literally named `statutory_nl` and neither has a
-- country dimension. One country baked into a column name, in a table that
-- cannot record a country. The knowledge layer already holds three different
-- answers to the question that column asks:
--
--   NL  8% of annual pay, statutory          (nl.py, WET, Wet minimumloon art. 15)
--   BE  92% of ONE MONTH's gross, white-collar (be.py, double holiday pay)
--   DE  not statutory at all — Tarifvertrag   (de.py)
--
-- So `pay_elements.PE-HOL` with typical_value '8%' and statutory_nl
-- 'Yes (statutory min 8%)' is a Dutch row wearing no label. Give it the label.
--
-- ASSUMES the tier call: these tables are country-conditioned. That much is not
-- in doubt — a statutory obligation is a national institution by definition.
--
-- DOES NOT ASSUME the SHAPE. `PE-13` "13th month / year-end" is a concept that
-- exists in several markets; what varies is its rate and its legal status, not
-- its name, category or basis. A country column on the whole row means seven
-- markets x seven elements, most of them restating identical text. The cleaner
-- alternative is a `pay_element_rates (country, element_id, typical_value,
-- statutory, taxable)` table with pay_elements staying universal. That is a
-- larger change — it reaches TableSpec, SHEET_MAP, the workbook sheet,
-- core/models.PayElement, pay_components_service and the export — and it is a
-- product decision, so it is §4.5 of the doc and not a step here. The column
-- below is the cheap reversible move that unblocks a second market; it is not
-- the considered one, and the next reader should not mistake it for one.

do $$
declare
  t text;
  tables text[] := array['pay_elements', 'benefits_catalog'];
begin
  foreach t in array tables loop
    execute format($f$
      alter table %I add column if not exists country text not null default 'NL'
    $f$, t);
    execute format($f$
      alter table %I drop constraint if exists %I
    $f$, t, t || '_country_known');
    execute format($f$
      alter table %I add constraint %I
        foreign key (country) references countries(code)
    $f$, t, t || '_country_known');
    execute format('create index if not exists %I on %I (org_id, country)',
                   t || '_org_country_idx', t);
  end loop;
end $$;

-- The uniques, widened. Names verified against pg_constraint 2026-09-06:
--   pay_elements_org_element_key   UNIQUE (org_id, element_id)
--   benefits_catalog_org_ben_key   UNIQUE (org_id, benefit_id)
-- Neither is referenced by a foreign key, so unlike 0012's pay_mix case there is
-- no FK to drop and re-add first.

do $$
begin
  if not exists (select 1 from pg_constraint
                 where conrelid = 'pay_elements'::regclass
                   and conname in ('pay_elements_org_element_key', 'pay_elements_country_uniq'))
  or not exists (select 1 from pg_constraint
                 where conrelid = 'benefits_catalog'::regclass
                   and conname in ('benefits_catalog_org_ben_key', 'benefits_catalog_country_uniq'))
  then
    raise exception
      'pay_elements / benefits_catalog: an expected unique constraint name was '
      'not found. Re-read pg_constraint; do not widen a constraint you cannot see.';
  end if;
end $$;

alter table pay_elements     drop constraint if exists pay_elements_org_element_key;
alter table benefits_catalog drop constraint if exists benefits_catalog_org_ben_key;

do $$
begin
  perform add_constraint_if_absent('pay_elements', 'pay_elements_country_uniq',
    $c$unique (org_id, country, element_id)$c$);
  perform add_constraint_if_absent('benefits_catalog', 'benefits_catalog_country_uniq',
    $c$unique (org_id, country, benefit_id)$c$);
end $$;

-- ══════════════════════════════════════════════════════════════════════════
-- 3. statutory_nl — THE FIRST HALF OF A TWO-STEP RENAME
-- ══════════════════════════════════════════════════════════════════════════
--
-- A country in a column name is a claim the schema makes on every row and can
-- never take back. `statutory` says the same thing without asserting whose law
-- it is; step 2 above gives the row a country to answer that with.
--
-- BOTH COLUMNS EXIST AFTER THIS MIGRATION, holding the same value. That is the
-- point. `statutory_nl` cannot be dropped in the same step because four things
-- still read or write it, none of them in this agent's files:
--
--   1. services/library_import_service.SPECS maps the WORKBOOK heading
--      "StatutoryNL" onto statutory_nl, for both tables. An import would fail
--      or silently drop the column.
--   2. core/models.PayElement.statutory_nl and .is_statutory read it — and
--      is_statutory is doing careful work: only a leading 'Yes' counts, because
--      'Partly (sector funds)' is not a statutory obligation and must not be
--      reported as one. That parsing has to move intact, not be reimplemented.
--   3. core/models.BenefitCatalogItem.statutory_nl, likewise.
--   4. The library export writes the workbook heading back out, and the
--      workbook in the client's hands still has that heading.
--
-- BEFORE A FOLLOW-UP MIGRATION MAY DROP statutory_nl, ALL OF THESE MUST HOLD:
--
--   (a) TableSpec for PayElements and BenefitsCatalog maps "StatutoryNL" (and
--       any new "Statutory" heading) onto `statutory`;
--   (b) both model classes read `statutory`, with is_statutory unchanged in
--       behaviour and its test still passing;
--   (c) the export emits a heading the current workbook can round-trip, or the
--       workbook has been reissued;
--   (d) `select count(*) from pay_elements where statutory is distinct from
--       statutory_nl` returns 0, and the same for benefits_catalog — i.e. no
--       writer has updated one column and not the other in the interval.
--
-- (d) is why there is no trigger keeping them in sync. A trigger would make the
--    two columns agree by force and hide the fact that some writer is still
--    using the old one; the check above is how you find that out. If the counts
--    diverge, the answer is to find the writer, not to add the trigger.

alter table pay_elements     add column if not exists statutory text;
alter table benefits_catalog add column if not exists statutory text;

update pay_elements     set statutory = statutory_nl where statutory is null;
update benefits_catalog set statutory = statutory_nl where statutory is null;

-- ══════════════════════════════════════════════════════════════════════════
-- 4. THE TIER DECISION, RECORDED WHERE IT IS READ
-- ══════════════════════════════════════════════════════════════════════════
--
-- 0012's tier reasoning lives in a migration comment, which means finding it
-- requires knowing that 0012 is where to look. These comments put the answer on
-- the object, so `\d+ skills` says why skills has no country and nobody has to
-- re-derive it or, worse, add one.
--
-- Only tables this migration touches, plus the ones most likely to be given a
-- country column by somebody being helpful.

comment on column pay_elements.country is
  'COUNTRY-CONDITIONED. Holiday allowance is 8% of annual pay in the Netherlands, '
  '92% of one month for Belgian white-collar staff, and not statutory at all in '
  'Germany — see services/country_packs/{nl,be,de}.py. Resolves country then the '
  '''EU'' baseline then nothing, per app.resolve_country() in 0012.';

comment on column pay_elements.statutory is
  'Replaces statutory_nl. Free text: only a leading ''Yes'' is a statutory '
  'obligation — ''Partly (sector funds)'' is not, and PayElement.is_statutory '
  'exists to keep that distinction. Both columns are live until the conditions '
  'in migration 0015 §3 are met.';

comment on column benefits_catalog.country is
  'COUNTRY-CONDITIONED. Whether a benefit is statutory, and what it is typically '
  'worth, is a national fact. The benefit''s DEFINITION is not, which is why the '
  'row is shared and only these fields move.';

comment on column benefits_catalog.statutory is
  'Replaces statutory_nl. See migration 0015 §3.';

comment on table skills is
  'UNIVERSAL. A skill is a description of a human capability; negotiation does not '
  'change at a border. Do not add a country column: it would force a choice where '
  'no difference exists, and somebody would then fill it with a guess. What varies '
  'by market is what a skill is PAID, and that is salary_bands.';

comment on table skill_proficiency is
  'UNIVERSAL. Behavioural anchors describing what a proficiency level looks like.';

comment on table jobs is
  'UNIVERSAL. A Data Analyst is a Data Analyst (0012). What the role is paid and '
  'where it grades are country-conditioned and live in salary_bands and job_grades.';

comment on table levels is
  'UNIVERSAL. The product''s own four-rung scale.';

comment on table industries is
  'UNIVERSAL — the sector list. Only its FACTORS move by market, and those are in '
  'industry_salary_factors, which carries the country.';

comment on table seniority_levels is
  'ARGUABLE, NOT YET DECIDED — see docs/country-data-tiers.md §4.3. The rung names '
  '(L1 Starter … L5 Rising Star) are the product''s own and read as universal. But '
  'grade_range ''7-10'' and maps_to_level point into job_grades, which IS keyed by '
  'country, so the binding is a statement about a national grade ladder held in a '
  'table with no country. Do not add a column here without settling §4.1 first: it '
  'is the same question and it probably splits the table rather than widening it.';

comment on table competency_levels is
  'ARGUABLE, NOT YET DECIDED — see docs/country-data-tiers.md §4.2. Whether these '
  'five levels anchor to the EQF the packs already hold, or stay the product''s own. '
  'The trap if EQF wins: NLQF→EQF is a function and EQF→NLQF is NOT, so a round '
  'trip does not return where it started and would quietly move people at level 4.';

comment on table job_profiles is
  'ARGUABLE, NOT YET DECIDED — see docs/country-data-tiers.md §4.1. The descriptive '
  'fields read as universal; management_level is a positioning claim against a '
  'national grading instrument (functiegroep in NL, ERA in DE, conventions '
  'collectives in FR) and does not.';

-- ══════════════════════════════════════════════════════════════════════════
-- NOT IN THIS MIGRATION, ON PURPOSE
-- ══════════════════════════════════════════════════════════════════════════
--
--   * dropping statutory_nl from either table — §3 above lists what must be true
--     first, and none of it is true today;
--   * country on job_profiles, competency_levels, seniority_levels or
--     career_paths — §4 of the doc, and they are the owner's calls, not an
--     agent's. Three of the four probably want a table split rather than a
--     column, which is not an additive step and cannot be reverted by dropping
--     something;
--   * splitting pay_elements into a rates table — §4.5;
--   * any change to a read path — the risk in §5 is `core/repository` keying
--     salary bands as (function, level) and `core/db_loader._fetch_all` applying
--     no country predicate. Neither is fixed by schema and neither is this
--     agent's file;
--   * `.order()` on _fetch_all's paged read, which it needs regardless of any of
--     this: `.range()` without an order is unspecified row order, so once two
--     countries' bands exist the one that survives the repository's dictionary
--     collision is arbitrary and can differ between runs;
--   * inserting a single non-'NL' row. Adding a market is importing rows, which
--     is the plan document's own standard and is not a migration's job.

comment on table career_paths is
  'ARGUABLE, NOT YET DECIDED — see docs/country-data-tiers.md §4.4. Which role '
  'follows which is mostly universal. It is not entirely: progression into some '
  'roles is gated by a national licence or qualification — Germany''s Meister '
  'route, regulated professions generally — and a ladder that ignores that tells '
  'a German employee a step exists that does not. Low urgency, but real.';

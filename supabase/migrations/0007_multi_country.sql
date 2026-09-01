-- 0007_multi_country.sql
--
-- Jobsy beyond the Netherlands.
--
-- WHAT THIS IS
--
-- Draft schema for the multi-country version. No data ships with it: the
-- tables are created, NL is seeded as the one live country, and every existing
-- row is stamped 'NL' because that is what it has always been. Loading a
-- second country is a separate exercise and a separate migration.
--
-- THE MODEL: ONE SPINE, MANY MARKETS
--
-- The temptation is to put country_code on all twenty reference tables and be
-- done. That would be wrong, and expensively so: it would fork the canonical
-- job library per country, so "Financial Controller" in the Netherlands and in
-- Germany become two unrelated rows that drift apart, and every cross-border
-- question ("who does this job group-wide?") stops being answerable.
--
-- So the library splits in two:
--
--   GLOBAL SPINE — what a job *is*. jobs, job_profiles, categories,
--   industries, skills, competency_levels, role_skill_map, career_paths,
--   levels, seniority_levels, skill_proficiency, industry_skills. One
--   definition, shared. A Financial Controller is the same work in Rotterdam
--   and in Antwerp; only its price and its statutory wrapper differ.
--
--   COUNTRY LAYER — what a job costs and what the law says about it.
--   salary_bands, job_grades, industry_salary_factors, pay_elements, pay_mix,
--   benefits_catalog, benefits_observations, level_benefits_factors,
--   title_mapping. These get country_code, and their natural keys widen to
--   include it.
--
-- employees gets country_code as an attribute rather than a key part: an
-- employee works in one country, but EmployeeID is already unique per org and
-- widening that key would break the person's identity when they relocate.
--
-- WHY NOW, ON POPULATED TABLES
--
-- 0001 threaded org_id through every table on the argument that "retrofitting
-- a tenant key onto populated tables with live foreign keys is the kind of
-- migration that goes wrong". Exactly the same argument applies to country,
-- and the tables are populated now — so this migration does the careful
-- version: add nullable, backfill 'NL', set not null, then widen the keys.
-- Doing it in that order on a live table is the whole point.

begin;

-- ────────────────────────────────────────────────────────────── countries ──
-- Not org-scoped. ISO 3166-1 alpha-2 is the same list for every tenant; which
-- of them a tenant has switched on is org_countries, below.

create table if not exists countries (
  code          text primary key,                    -- ISO 3166-1 alpha-2
  name_en       text not null,
  name_local    text,
  currency      text not null,                       -- ISO 4217
  locale        text,                                -- default UI/report locale
  eu_member     boolean not null default false,
  -- Directive 2023/970 is EU-wide but transposed nationally, so the reporting
  -- obligation a country actually imposes is a per-country fact, not an EU one.
  pay_transparency_regime text,
  active        boolean not null default false,      -- has reference data loaded
  sort_order    integer,
  created_at    timestamptz not null default now(),
  constraint countries_code_shape check (code ~ '^[A-Z]{2}$'),
  constraint countries_currency_shape check (currency ~ '^[A-Z]{3}$')
);

-- NL is active because it has data. The rest are seeded inactive so the
-- country picker can show a real roadmap rather than an empty list, and so
-- adding a market is a data load rather than a schema change. Ordered by where
-- the Metalektro/CAO adjacency makes the next market cheapest to reach.
insert into countries (code, name_en, name_local, currency, locale, eu_member, pay_transparency_regime, active, sort_order) values
  ('NL', 'Netherlands', 'Nederland',   'EUR', 'nl-NL', true,  'EU 2023/970 — national transposition', true,  10),
  ('BE', 'Belgium',     'België',      'EUR', 'nl-BE', true,  'EU 2023/970 — national transposition', false, 20),
  ('DE', 'Germany',     'Deutschland', 'EUR', 'de-DE', true,  'EU 2023/970 — national transposition', false, 30),
  ('FR', 'France',      'France',      'EUR', 'fr-FR', true,  'EU 2023/970 — national transposition', false, 40),
  ('LU', 'Luxembourg',  'Luxembourg',  'EUR', 'fr-LU', true,  'EU 2023/970 — national transposition', false, 50),
  ('ES', 'Spain',       'España',      'EUR', 'es-ES', true,  'EU 2023/970 — national transposition', false, 60),
  ('PL', 'Poland',      'Polska',      'PLN', 'pl-PL', true,  'EU 2023/970 — national transposition', false, 70),
  ('SE', 'Sweden',      'Sverige',     'SEK', 'sv-SE', true,  'EU 2023/970 — national transposition', false, 80),
  ('GB', 'United Kingdom', NULL,       'GBP', 'en-GB', false, 'UK gender pay gap reporting',          false, 90)
on conflict (code) do nothing;

-- Which countries a tenant has switched on, and which one their UI opens in.
create table if not exists org_countries (
  org_id       uuid not null references orgs(id) on delete cascade,
  country_code text not null references countries(code),
  is_default   boolean not null default false,
  enabled_at   timestamptz not null default now(),
  primary key (org_id, country_code)
);

-- One default per org. A partial unique index rather than a check, because the
-- constraint is across rows.
create unique index if not exists org_countries_one_default
  on org_countries (org_id) where is_default;

insert into org_countries (org_id, country_code, is_default)
select id, 'NL', true from orgs where slug = 'default'
on conflict (org_id, country_code) do nothing;

-- ───────────────────────────────────────────── country layer on the tables ──
-- Nullable → backfill → not null → key. In that order, so a populated table
-- never has to satisfy a constraint before its data can satisfy it.

do $$
declare
  t text;
  country_tables text[] := array[
    'salary_bands', 'job_grades', 'industry_salary_factors',
    'pay_elements', 'pay_mix', 'benefits_catalog', 'benefits_observations',
    'level_benefits_factors', 'title_mapping'
  ];
begin
  foreach t in array country_tables loop
    execute format('alter table %I add column if not exists country_code text', t);
    execute format('update %I set country_code = ''NL'' where country_code is null', t);
    execute format('alter table %I alter column country_code set not null', t);
    execute format('alter table %I alter column country_code set default ''NL''', t);

    perform add_constraint_if_absent(t, t || '_country_fk',
      $c$foreign key (country_code) references countries(code)$c$);

    execute format('create index if not exists %I on %I (org_id, country_code)',
                   t || '_org_country_idx', t);
  end loop;
end $$;

-- employees: an attribute, not a key part. See the header.
alter table employees add column if not exists country_code text;
update employees set country_code = 'NL' where country_code is null;
alter table employees alter column country_code set not null;
alter table employees alter column country_code set default 'NL';
select add_constraint_if_absent('employees', 'employees_country_fk',
  $c$foreign key (country_code) references countries(code)$c$);
create index if not exists employees_org_country_idx on employees (org_id, country_code);

-- ──────────────────────────────────────────────────── widened natural keys ──
-- The same function may be paid differently in two countries, so (org, function,
-- level) stops being unique the moment a second market loads. Drop the narrow
-- key and rebuild it with country in it. Dropping first is not optional: leaving
-- both would silently keep the old, narrower rule in force, and the second
-- country's first insert would fail against a constraint nobody remembered.
--
-- Three things this has to get right, each learned by running it:
--
-- 1. FIND the old constraints, do not name them. Writing the names by hand is
--    how you get a `drop constraint if exists` that matches nothing, skips with
--    a NOTICE, and reports success while leaving the constraint it existed to
--    remove. Anything unique here that does not mention country_code is, by
--    definition, the narrow version.
--
-- 2. DROP DEPENDENT FOREIGN KEYS FIRST. 0001 noted that "a foreign key needs a
--    full unique constraint on its target"; the flip side is that the target's
--    unique constraint cannot be dropped while the foreign key stands.
--    pay_mix -> salary_bands is one such today.
--
-- 3. RECREATE those foreign keys widened, not as they were. pay_mix rows are
--    country-scoped now, so a Dutch pay mix must reference the Dutch band and
--    not merely some band with the same function and level. Widening the key is
--    a correctness fix, not only a mechanical consequence.

do $$
declare
  spec record;
  con  record;
  fk   record;
  country_tables text[] := array[
    'salary_bands', 'job_grades', 'industry_salary_factors', 'title_mapping',
    'level_benefits_factors', 'benefits_catalog', 'benefits_observations',
    'pay_elements', 'pay_mix'
  ];
  dropped_fks text[] := '{}';
begin
  -- (2) Dependent foreign keys, out of the way first.
  for fk in
    select c.conrelid::regclass::text as child, c.conname
      from pg_constraint c
     where c.contype = 'f'
       and c.confrelid::regclass::text = any (country_tables)
       and pg_get_constraintdef(c.oid) not like '%country_code%'
  loop
    raise notice 'dropping dependent foreign key %.% before widening its target',
      fk.child, fk.conname;
    execute format('alter table %I drop constraint %I', fk.child, fk.conname);
    dropped_fks := dropped_fks || (fk.child || '.' || fk.conname);
  end loop;

  -- (1) The narrow unique keys, found rather than named.
  for spec in
    select * from (values
      ('salary_bands',            $c$unique (org_id, country_code, function, level)$c$),
      ('job_grades',              $c$unique (org_id, country_code, grade)$c$),
      ('industry_salary_factors', $c$unique (org_id, country_code, industry_id, function)$c$),
      ('title_mapping',           $c$unique (org_id, country_code, existing_title)$c$),
      ('level_benefits_factors',  $c$unique (org_id, country_code, level, category)$c$),
      ('benefits_catalog',        $c$unique (org_id, country_code, benefit_id)$c$),
      ('benefits_observations',   $c$unique (org_id, country_code, obs_id)$c$),
      ('pay_elements',            $c$unique (org_id, country_code, element_id)$c$),
      ('pay_mix',                 $c$unique (org_id, country_code, function, level)$c$)
    ) as t(tbl, new_ddl)
  loop
    for con in
      select conname
        from pg_constraint
       where conrelid = spec.tbl::regclass
         and contype = 'u'
         and pg_get_constraintdef(oid) not like '%country_code%'
    loop
      raise notice 'widening %: dropping narrow key %', spec.tbl, con.conname;
      execute format('alter table %I drop constraint %I', spec.tbl, con.conname);
    end loop;

    perform add_constraint_if_absent(spec.tbl, spec.tbl || '_org_country_key', spec.new_ddl);
  end loop;

  -- (3) Put the foreign keys back, country included.
  perform add_constraint_if_absent('pay_mix', 'pay_mix_salary_band_fk',
    $c$foreign key (org_id, country_code, function, level)
       references salary_bands (org_id, country_code, function, level)
       on delete cascade$c$);
  dropped_fks := array_remove(dropped_fks, 'pay_mix.pay_mix_salary_band_fk');

  -- Anything dropped and not put back is a foreign key this migration did not
  -- know about. Fail rather than leave referential integrity quietly weaker
  -- than it was before the migration ran.
  if array_length(dropped_fks, 1) > 0 then
    raise exception 'dropped foreign key(s) not recreated: %', dropped_fks;
  end if;
end $$;

-- Belt and braces: no country-scoped table may leave this migration still
-- carrying a unique key that ignores country. A silent survivor here is the
-- one failure mode that would not show up until a second market loaded.
do $$
declare
  leftover text;
begin
  select string_agg(conrelid::regclass::text || '.' || conname, ', ')
    into leftover
    from pg_constraint
   where contype = 'u'
     and conrelid::regclass::text in (
       'salary_bands', 'job_grades', 'industry_salary_factors', 'title_mapping',
       'level_benefits_factors', 'benefits_catalog', 'benefits_observations',
       'pay_elements', 'pay_mix')
     and pg_get_constraintdef(oid) not like '%country_code%';

  if leftover is not null then
    raise exception 'narrow unique key(s) survived widening: %', leftover;
  end if;
end $$;

-- pay_elements.statutory_nl is a country baked into a column name. Its
-- replacement is added here; the column itself stays until core/models.py,
-- core/repository.py and services/library_import_service.py stop reading it,
-- because a rename that outruns its callers is an outage. Drop it in the
-- migration that lands those three edits.
alter table pay_elements add column if not exists statutory text;
update pay_elements set statutory = statutory_nl where statutory is null;

-- ──────────────────────────────────────────── national classification sets ──
-- The generalisation of services/cao_crosswalk_service.py. Every country has
-- some public structure a grade has to land in — Dutch CAO salarisgroepen,
-- German ERA Entgeltgruppen, Belgian IFIC functieklassen, French coefficients.
--
-- THE HONESTY BOUNDARY IS A COLUMN, NOT A CONVENTION
--
-- The Dutch work established a distinction the schema has to carry, or someone
-- adding a country will quietly break it:
--
--   * ISF (Metalektro) publishes a numeric point-BOUNDARY table, so a grade can
--     be rank-positioned onto a published sequence. Indicative, never a
--     fabricated point score for the job.
--   * CATS publishes NO point table at all — only functiegroep→salarisgroep
--     labels. Anything numeric shown against it would be invented.
--
-- crosswalk_basis makes that machine-checkable. A system registered as
-- 'label_alignment' must have null point boundaries, and the constraint below
-- enforces it, so the UI can never render a point range that does not exist.

create table if not exists classification_systems (
  system_code     text not null,          -- 'ISF', 'CATS', 'ERA', 'IFIC'
  country_code    text not null references countries(code),
  name            text not null,
  system_owner    text,                   -- systeemhouder / rights holder
  sector_scope    text,                   -- 'Metalektro', 'Metaal en Techniek', ...
  crosswalk_basis text not null,          -- 'point_boundaries' | 'label_alignment'
  source_url      text,
  source_document text,
  verified_on     date,                   -- when a human last read the primary text
  notes           text,
  constraint classification_systems_basis_valid
    check (crosswalk_basis in ('point_boundaries', 'label_alignment'))
);

create table if not exists classification_grades (
  system_code   text not null,
  country_code  text not null references countries(code),
  grade_label   text not null,            -- 'A' … 'Q', '2' … '11'
  -- Null for a label_alignment system, by constraint. Not "unknown" — absent.
  point_min     integer,
  point_max     integer,
  sort_order    integer not null,
  -- The published scale, where one exists. Monthly for Dutch CAO tables;
  -- period says which, so a country that publishes annual figures is not
  -- silently read as monthly.
  scale_min     numeric,
  scale_max     numeric,
  scale_period  text,                     -- 'month' | 'year'
  scale_year    integer,
  currency      text,
  constraint classification_grades_points_ordered
    check (point_min is null or point_max is null or point_min <= point_max),
  constraint classification_grades_scale_ordered
    check (scale_min is null or scale_max is null or scale_min <= scale_max),
  constraint classification_grades_period_valid
    check (scale_period is null or scale_period in ('month', 'year'))
);

-- Jobsy's own grade → a national grade label. This is the crosswalk step the
-- reference doc insists stays separate from Jobsy's independent grading: the
-- app produces its grade without reference to any protected method, and this
-- table maps that output onto the public structure afterwards.
create table if not exists classification_crosswalk (
  system_code    text not null,
  country_code   text not null references countries(code),
  jobsy_grade    integer not null,
  grade_label    text not null,
  confidence     text,                    -- 'indicative' | 'aligned'
  notes          text,
  constraint classification_crosswalk_confidence_valid
    check (confidence is null or confidence in ('indicative', 'aligned'))
);

-- ────────────────────────────────────────────────────────────── fx  rates ──
-- Only needed once a non-euro market loads (PL, SE, GB above). Group-wide
-- comparison of a Polish and a Dutch band is meaningless without a rate and a
-- date attached to it, and picking "today's rate" silently makes last quarter's
-- report irreproducible — hence as_of in the key.
create table if not exists fx_rates (
  base_currency  text not null,
  quote_currency text not null,
  as_of          date not null,
  rate           numeric not null,
  source         text,
  constraint fx_rates_rate_positive check (rate > 0),
  constraint fx_rates_not_identity check (base_currency <> quote_currency)
);

-- ───────────────────────────────────────── provenance, audit, RLS, as 0001 ──
-- The new reference tables get the identical treatment every other reference
-- table has had since 0001. Identical by construction, not by copy-paste.

do $$
declare
  t text;
  new_ref_tables text[] := array[
    'classification_systems', 'classification_grades',
    'classification_crosswalk', 'fx_rates'
  ];
begin
  foreach t in array new_ref_tables loop
    execute format($f$
      alter table %I
        add column if not exists id             uuid primary key default gen_random_uuid(),
        add column if not exists org_id         uuid not null references orgs(id) on delete cascade,
        add column if not exists revision_id    uuid references library_revisions(id),
        add column if not exists status         text not null default 'active',
        add column if not exists owner          text,
        add column if not exists source         text,
        add column if not exists effective_from date,
        add column if not exists effective_to   date,
        add column if not exists created_at     timestamptz not null default now(),
        add column if not exists updated_at     timestamptz not null default now(),
        add column if not exists updated_by     text
    $f$, t);

    perform add_constraint_if_absent(t, t || '_status_valid',
      $c$check (status in ('active', 'draft', 'retired'))$c$);
    perform add_constraint_if_absent(t, t || '_effective_ordered',
      $c$check (effective_to is null or effective_from is null or effective_from <= effective_to)$c$);

    execute format('create index if not exists %I on %I (org_id)', t || '_org_idx', t);
    execute format('create index if not exists %I on %I (org_id, status)', t || '_org_status_idx', t);
    -- fx_rates is the one new table with no country_code: a rate is between
    -- two currencies, not inside a country.
    if t <> 'fx_rates' then
      execute format('create index if not exists %I on %I (org_id, country_code)',
                     t || '_org_country_idx', t);
    end if;

    execute format('drop trigger if exists %I on %I', t || '_set_updated_at', t);
    execute format($f$
      create trigger %I before update on %I
      for each row execute function set_updated_at()
    $f$, t || '_set_updated_at', t);

    execute format('drop trigger if exists %I on %I', t || '_audit', t);
    execute format($f$
      create trigger %I after insert or update or delete on %I
      for each row execute function log_library_change()
    $f$, t || '_audit', t);

    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

create index if not exists fx_rates_org_pair_idx
  on fx_rates (org_id, base_currency, quote_currency, as_of desc);

-- countries and org_countries are not reference-library rows: no provenance
-- block, no audit trigger. They are configuration. RLS still on, same posture
-- as everywhere else — reachable by service_role only until auth lands.
alter table countries enable row level security;
alter table org_countries enable row level security;

-- ──────────────────────────────────────────────────────────── natural keys ──
select add_constraint_if_absent('classification_systems', 'classification_systems_key',
  $c$unique (org_id, country_code, system_code)$c$);
select add_constraint_if_absent('classification_grades', 'classification_grades_key',
  $c$unique (org_id, country_code, system_code, grade_label)$c$);
select add_constraint_if_absent('classification_crosswalk', 'classification_crosswalk_key',
  $c$unique (org_id, country_code, system_code, jobsy_grade)$c$);
select add_constraint_if_absent('fx_rates', 'fx_rates_key',
  $c$unique (org_id, base_currency, quote_currency, as_of)$c$);

-- A label_alignment system cannot carry point boundaries. Enforced here rather
-- than trusted to the importer, because the whole IP position rests on it.
create or replace function classification_grade_respects_basis() returns trigger
  language plpgsql
  security definer
  set search_path = public
as $$
declare
  v_basis text;
begin
  select crosswalk_basis into v_basis
    from classification_systems
   where org_id = new.org_id
     and country_code = new.country_code
     and system_code = new.system_code;

  if v_basis = 'label_alignment'
     and (new.point_min is not null or new.point_max is not null) then
    raise exception
      'system %/% is registered as label_alignment and publishes no point table; '
      'point_min/point_max must stay null',
      new.country_code, new.system_code;
  end if;

  return new;
end $$;

revoke execute on function classification_grade_respects_basis() from public, anon, authenticated;

drop trigger if exists classification_grades_basis_check on classification_grades;
create trigger classification_grades_basis_check
  before insert or update on classification_grades
  for each row execute function classification_grade_respects_basis();

commit;

-- ───────────────────────────────────────────────────────────── deliberately ──
-- NOT DONE HERE, and why:
--
-- * No second country's data. The tables are shaped; loading BE or DE is a
--   sourcing exercise with its own verification trail, exactly as
--   docs/cao-metalektro-isf-reference.md was for NL.
-- * jobs / job_profiles / skills stay global. If a country genuinely needs its
--   own variant of a role, that is a localisation table hanging off the global
--   job, not a forked job row.
-- * title_mapping is country-scoped but not language-scoped. Belgium breaks
--   that — nl-BE and fr-BE titles map to the same job in one country — and it
--   should be a `language` column added when BE loads, not guessed at now.
-- * pay_elements.statutory_nl still exists. See the note above it.

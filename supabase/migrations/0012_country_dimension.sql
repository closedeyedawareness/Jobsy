-- 0012_country_dimension.sql
--
-- ROADMAP item 3.1: "Multi-country / i18n. Un-hardcode COUNTRY='NL'/EUR;
-- per-country bands, currency, locale."
--
-- This is the schema half. It adds the dimension while the tables are still
-- small, for exactly the reason 0001 gave when it threaded org_id through
-- twenty tables a year before anything needed it: "retrofitting a tenant key
-- onto populated tables with live foreign keys is the kind of migration that
-- goes wrong; carrying an unused column is cheap by comparison." The same is
-- true of a country key, and today the library is 81 jobs and 45 bands.
--
-- ── WHAT ACTUALLY BLOCKS A SECOND COUNTRY ─────────────────────────────────
--
-- Not the absence of German data. These, from 0001:
--
--     unique (org_id, function, level)   on salary_bands
--     unique (org_id, grade)             on job_grades
--     unique (org_id, level)             on levels, seniority_levels
--
-- A German band for function B, level 5 collides with the Dutch one. The
-- library cannot hold two countries at all, whatever anyone imports.
--
-- ── WHICH TABLES ARE COUNTRY-SPECIFIC, AND WHICH ARE NOT ──────────────────
--
-- Deliberately not "all of them". A country column on a table that does not
-- vary by country is a column that will drift, get half-populated, and then be
-- believed.
--
--   COUNTRY-SPECIFIC -- money, or a national institution
--     salary_bands, job_grades          pay figures
--     industry_salary_factors           sector premia differ by market
--     benefits_observations             market benefit values
--     level_benefits_factors            same
--     title_mapping                     local-language titles map to a job
--
--   COUNTRY-NEUTRAL -- structure, not price
--     jobs, job_profiles, career_paths  a Data Analyst is a Data Analyst
--     skills, role_skill_map            same
--     competency_levels, levels         the scale itself
--     seniority_levels, categories      same
--     industries                        the sector list; only its FACTORS move
--     benefits_catalog                  what a pension IS, not what it is worth
--
-- ── 'EU' IS A REAL SCOPE, NOT A NULL ──────────────────────────────────────
--
-- Rows resolve country-first, then fall back to the 'EU' baseline. That is a
-- row somebody wrote on purpose, not a NULL meaning "unknown or everywhere" --
-- which in a unique index does not even collide with itself, so two
-- contradictory "applies anywhere" rows could both exist and nobody would
-- know. See app.resolve_country() below.

-- ────────────────────────────────────────────────── 1. the registry ──

create table if not exists countries (
  code         text primary key,
  name         text not null,
  currency     text not null,
  is_live      boolean not null default false,
  notes        text,
  created_at   timestamptz not null default now()
);

comment on table countries is
  'Countries Jobsy holds reference data for. is_live gates whether the app '
  'offers it: a country can be seeded and worked on gradually without appearing '
  'in the interface half-finished.';

alter table countries drop constraint if exists countries_code_shape;
alter table countries add constraint countries_code_shape
  check (code ~ '^[A-Z]{2}$');
alter table countries drop constraint if exists countries_currency_shape;
alter table countries add constraint countries_currency_shape
  check (currency ~ '^[A-Z]{3}$');

-- NL is live because it is what the library holds. EU is the fallback scope and
-- is deliberately NOT live: nobody should be able to pick "EU" as their
-- country: it is where a Europe-wide default row lives when no national one
-- exists yet. The rest are seeded but dark, so adding Belgium is importing
-- rows and flipping a boolean rather than writing a migration.
insert into countries (code, name, currency, is_live, notes) values
  ('NL', 'Netherlands',  'EUR', true,  'The library as imported. CAO crosswalk implemented.'),
  ('EU', 'EU baseline',  'EUR', false, 'Fallback scope, not a country. Never offered as a choice.'),
  ('BE', 'Belgium',      'EUR', false, null),
  ('DE', 'Germany',      'EUR', false, null),
  ('FR', 'France',       'EUR', false, null),
  ('ES', 'Spain',        'EUR', false, null),
  ('IT', 'Italy',        'EUR', false, null),
  ('PL', 'Poland',       'PLN', false, 'Non-euro: currency handling is not decorative here.'),
  ('SE', 'Sweden',       'SEK', false, 'Non-euro.'),
  ('DK', 'Denmark',      'DKK', false, 'Non-euro.')
on conflict (code) do nothing;

-- ──────────────────────────────── 2. country on the tables that move ──

do $$
declare
  t text;
  priced_tables text[] := array[
    'salary_bands', 'job_grades', 'industry_salary_factors',
    'benefits_observations', 'level_benefits_factors', 'title_mapping',
    -- pay_mix was missing from the first version of this list and the database
    -- said so: it carries a FOREIGN KEY onto salary_bands (org_id, function,
    -- level), so the unique underneath that key cannot be widened while the FK
    -- still points at it. A pay mix describes a Function x Level cohort, and
    -- once cohorts are per-country so is the mix -- 0004 made them agree "by
    -- constraint rather than by coincidence", and that agreement has to survive
    -- the extra dimension.
    'pay_mix'
  ];
begin
  foreach t in array priced_tables loop
    -- Every existing row IS Dutch, so the default backfills correctly and the
    -- not-null can be taken in the same statement.
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

-- The uniques from 0001, widened. Dropped by name and rebuilt rather than
-- altered, because a composite unique cannot be extended in place.
--
-- The names below are 0001's, verified against pg_constraint rather than
-- guessed. The first version of this migration invented plausible ones
-- (salary_bands_uniq and friends); `drop constraint if exists` then did nothing
-- at all, quietly, and the old unique survived -- so a German band for the same
-- function and level was still rejected and this entire migration achieved
-- nothing. `if exists` turns a wrong name into silence, which is why the test
-- inserts a second country's band rather than reading the catalogue back.
-- The FK first: it depends on the index the unique creates, so the unique
-- cannot go while it stands. Re-added below against the widened key.
alter table pay_mix drop constraint if exists pay_mix_salary_band_fk;
alter table pay_mix drop constraint if exists pay_mix_org_fn_level_key;

alter table salary_bands            drop constraint if exists salary_bands_org_fn_level_key;
alter table job_grades              drop constraint if exists job_grades_org_grade_key;
alter table title_mapping           drop constraint if exists title_mapping_org_title_key;
alter table industry_salary_factors drop constraint if exists isf_org_ind_fn_key;

do $$
begin
  perform add_constraint_if_absent('salary_bands', 'salary_bands_country_uniq',
    $c$unique (org_id, country, function, level)$c$);
  perform add_constraint_if_absent('job_grades', 'job_grades_country_uniq',
    $c$unique (org_id, country, grade)$c$);
  perform add_constraint_if_absent('title_mapping', 'title_mapping_country_uniq',
    $c$unique (org_id, country, existing_title)$c$);
  perform add_constraint_if_absent('industry_salary_factors', 'isf_country_uniq',
    $c$unique (org_id, country, industry_id, function)$c$);
  perform add_constraint_if_absent('pay_mix', 'pay_mix_country_uniq',
    $c$unique (org_id, country, function, level)$c$);
  -- 0004's rule, carried forward with country in it: a pay mix still has to
  -- describe a pay cohort that actually exists, now in the same market.
  perform add_constraint_if_absent('pay_mix', 'pay_mix_salary_band_fk',
    $c$foreign key (org_id, country, function, level)
       references salary_bands (org_id, country, function, level) on delete cascade$c$);
end $$;

-- ─────────────────────────────────────── 3. who a client's people are ──
--
-- Two different things, and conflating them is the mistake this section exists
-- to prevent.

-- A client's home country: where the company is, what currency to show by
-- default, whose collective agreements apply to the organisation.
alter table orgs add column if not exists default_country text not null default 'NL';
alter table orgs drop constraint if exists orgs_country_known;
alter table orgs add constraint orgs_country_known
  foreign key (default_country) references countries(code);

-- An EMPLOYEE'S country, which is not the same thing at all. The customers
-- Jobsy is being sold to are multinationals: one client, staff in eleven
-- countries. Pay is set in the country the person works in, so a roster is a
-- mix, and every comparison that treats it as one population is wrong --
-- demonstrably so; see the note in services/pay_equity_service.py.
alter table employees add column if not exists country text;
alter table employees drop constraint if exists employees_country_known;
alter table employees add constraint employees_country_known
  foreign key (country) references countries(code);

comment on column employees.country is
  'Where this person works and is paid. NULL means not supplied -- treated as '
  'the org default for display, and as UNKNOWN for any pay comparison, because '
  'guessing it silently is how a country-mix artefact becomes a reported gap.';

create index if not exists employees_org_country_idx on employees (org_id, country);

-- ───────────────────────────────────────────── 4. resolving a lookup ──
--
-- Country first, then the EU baseline. Returns the code to read rows for, or
-- NULL when neither exists -- so a caller can say "no data for Belgium yet"
-- instead of silently showing Dutch numbers with a Belgian flag on them, which
-- is the failure mode that matters here. Wrong pay data looks exactly like
-- right pay data.

create or replace function app.resolve_country(p_table text, p_org uuid, p_country text)
returns text
language plpgsql
stable
security definer
set search_path = public, pg_catalog
as $$
declare n int;
begin
  if p_table !~ '^[a-z_]+$' then
    raise exception 'not a table name: %', p_table;   -- it is interpolated below
  end if;

  execute format('select count(*) from %I where org_id = $1 and country = $2', p_table)
    into n using p_org, p_country;
  if n > 0 then return p_country; end if;

  execute format('select count(*) from %I where org_id = $1 and country = ''EU''', p_table)
    into n using p_org;
  if n > 0 then return 'EU'; end if;

  return null;
end $$;

grant execute on function app.resolve_country(text, uuid, text) to authenticated, service_role;
revoke execute on function app.resolve_country(text, uuid, text) from public, anon;

-- ──────────────────────────────────────────────────────── 5. reading ──
--
-- countries is a reference list with nothing sensitive in it, but it is still
-- behind authentication: an unauthenticated caller has no business enumerating
-- which markets this product covers. Consistent with every other table here --
-- anon reaches nothing.

alter table countries enable row level security;
revoke all on countries from anon;

drop policy if exists countries_read on countries;
create policy countries_read on countries for select to authenticated using (true);

-- No write policy. The country list changes when an operator adds a market,
-- through tools/manage_users.py with the secret key -- not from a browser.

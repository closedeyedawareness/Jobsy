-- 0001_reference_library.sql
-- Jobsy — the reference library as a governed database.
--
-- WHAT THIS IS
--
-- Phase 0 of docs/PLAN-supabase-migration.md: move the master record out of
-- jobsy_reference_library.xlsx and into Postgres, without touching the app.
-- Catalog.load() hands Repository a dict[str -> DataFrame] keyed by SHEET_MAP;
-- everything downstream sees only that. So the migration is a loader swap, and
-- this file's job is to make the database able to produce the same 20 frames.
--
-- THE GOVERNANCE COLUMNS ARE NOT NEW
--
-- Every reference sheet in the workbook already carries Owner, Status,
-- EffectiveFrom, Source and UpdatedAt, populated for essentially every row.
-- That is a provenance trail someone has been keeping by hand. This schema
-- adopts it as-is rather than inventing a parallel one, so the importer is a
-- straight column mapping and nothing that has been recorded is thrown away:
--
--     Owner         -> owner
--     Status        -> status
--     EffectiveFrom -> effective_from
--     Source        -> source
--     UpdatedAt     -> updated_at
--
-- ONE ROW PER NATURAL KEY
--
-- History lives in library_audit (append-only, trigger-written), not in extra
-- rows here. That is a deliberate limit: a foreign key needs a full unique
-- constraint on its target, and versioned duplicate rows would make one
-- impossible — which would cost us exactly the referential integrity this
-- migration exists to gain. Snapshot-level versioning is library_revisions.
--
-- WHAT THE APP GAINS
--
-- Three checks core/validator.py performs at load time become constraints
-- enforced at write time, so bad data cannot enter the master record at all:
--   * duplicate JobID          -> unique (org_id, job_id)
--   * salary min > max         -> check (min <= max)
--   * dangling title -> job    -> foreign key
--
-- RLS: enabled everywhere, service_role only. See the note above the policies.

-- ─────────────────────────────────────────────────────────────── tenancy ──

create table if not exists orgs (
  id          uuid primary key default gen_random_uuid(),
  slug        text not null unique,
  name        text not null,
  created_at  timestamptz not null default now()
);

-- Single tenant for now. org_id is threaded through every table from day one
-- because retrofitting a tenant key onto populated tables with live foreign
-- keys is the kind of migration that goes wrong; carrying an unused column is
-- cheap by comparison. Enforcement arrives with auth (Phase 0.3).
insert into orgs (slug, name)
values ('default', 'Default organisation')
on conflict (slug) do nothing;

-- Each import or publish gets a revision, so "which version of the library was
-- this report run against" has an answer. Reference rows point at the revision
-- that last wrote them.
create table if not exists library_revisions (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references orgs(id) on delete cascade,
  label       text not null,                    -- 'import:jobsy_reference_library.xlsx'
  note        text,
  created_at  timestamptz not null default now(),
  created_by  text
);

-- Append-only change log. Written by trigger, never by the app.
create table if not exists library_audit (
  id           bigint generated always as identity primary key,
  org_id       uuid,
  table_name   text not null,
  row_id       uuid,
  action       text not null check (action in ('INSERT', 'UPDATE', 'DELETE')),
  old_row      jsonb,
  new_row      jsonb,
  changed_at   timestamptz not null default now(),
  changed_by   text not null default coalesce(current_setting('request.jwt.claims', true), current_user)
);

create index if not exists library_audit_table_time_idx
  on library_audit (table_name, changed_at desc);
create index if not exists library_audit_row_idx
  on library_audit (row_id);

-- ─────────────────────────────────────────────────────── reference tables ──
-- Natural columns only. The shared provenance block, triggers and indexes are
-- applied to every table in one pass at the bottom, so the block cannot drift
-- from one table to the next.

create table if not exists jobs (
  job_id         text not null,
  standard_title text not null,
  function       text not null,
  level          text not null,
  category       text,
  grade          integer default 0,
  isco_group     text,
  isco_title     text,
  esco_label     text
);

create table if not exists job_profiles (
  job_id               text not null,
  description          text,
  key_responsibilities text,
  required_skills      text,
  specialisms          text,
  management_level     text,
  typical_tools        text
);

create table if not exists salary_bands (
  function text not null,
  level    text not null,
  grade    integer,
  min      numeric,
  p25      numeric,
  p50      numeric,
  p75      numeric,
  max      numeric,
  currency text default 'EUR',
  -- The Validator warns about these after the fact; here they simply cannot happen.
  constraint salary_bands_min_le_max check (min is null or max is null or min <= max),
  constraint salary_bands_percentiles_ordered check (
    (p25 is null or p50 is null or p25 <= p50) and
    (p50 is null or p75 is null or p50 <= p75) and
    (min is null or p25 is null or min <= p25) and
    (p75 is null or max is null or p75 <= max)
  )
);

create table if not exists title_mapping (
  existing_title text not null,
  job_id         text not null
);

create table if not exists career_paths (
  job_id      text not null,
  next_job_id text,
  next_role   text
);

create table if not exists levels (
  level     text not null,
  "order"   integer
);

-- Customer data, not reference data: no Owner/Status/EffectiveFrom in the
-- workbook and no rows in it either. It is here because SHEET_MAP loads it and
-- the loader must be able to produce the frame. It is also the one table that
-- will hold personal data, so it is where RLS stops being theoretical.
create table if not exists employees (
  employee_id   text not null,
  name          text,
  current_title text,
  department    text
);

create table if not exists categories (
  category    text not null,
  function    text,
  description text
);

create table if not exists skills (
  skill_id   text not null,
  skill_name text not null,
  category   text,
  definition text
);

create table if not exists competency_levels (
  level       integer not null,
  name        text not null,
  description text,
  constraint competency_levels_range check (level between 1 and 5)
);

create table if not exists role_skill_map (
  job_id         text not null,
  skill_id       text not null,
  required_level integer,
  skill_type     text,
  constraint role_skill_map_level_range check (required_level is null or required_level between 1 and 5)
);

create table if not exists job_grades (
  grade            integer not null,
  grade_label      text,
  career_band      text,
  level_band       text,
  hay_min          numeric,
  hay_max          numeric,
  pay_min          numeric,
  pay_p25          numeric,
  pay_p50          numeric,
  pay_p75          numeric,
  pay_max          numeric,
  scope            text,
  complexity       text,
  autonomy         text,
  impact           text,
  leadership       text,
  span_of_control  text,
  decision_rights  text,
  responsibilities text,
  authority        text,
  constraint job_grades_pay_ordered check (pay_min is null or pay_max is null or pay_min <= pay_max)
);

create table if not exists industries (
  industry_id     text not null,
  industry_name   text not null,
  scope           text,
  characteristics text
);

create table if not exists industry_salary_factors (
  industry_id text not null,
  function    text not null,
  factor      numeric default 1.0,
  constraint industry_salary_factors_positive check (factor is null or factor > 0)
);

create table if not exists industry_skills (
  industry_id   text not null,
  skill_id      text not null,
  skill_name    text,
  category      text,
  definition    text,
  default_level integer,
  constraint industry_skills_level_range check (default_level is null or default_level between 1 and 5)
);

create table if not exists seniority_levels (
  l_code        text not null,
  l_name        text,
  maps_to_level text,
  grade_range   text,
  definition    text,
  grades        text
);

create table if not exists skill_proficiency (
  category   text not null,
  level      integer not null,
  level_name text,
  anchor     text,
  constraint skill_proficiency_range check (level between 1 and 5)
);

create table if not exists benefits_catalog (
  benefit_id                 text not null,
  category                   text not null,
  basis                      text,
  unit                       text,
  typical_value_description  text,
  statutory_nl               text,
  taxable                    text,
  description                text
);

create table if not exists benefits_observations (
  obs_id      text not null,
  industry_id text not null,
  category    text not null,
  value       numeric,
  unit        text,
  currency    text
);

create table if not exists level_benefits_factors (
  level    text not null,
  category text not null,
  factor   numeric default 1.0,
  constraint level_benefits_factors_positive check (factor is null or factor > 0)
);

-- ───────────────────────────────────────────────── provenance, in one pass ──

-- ADD CONSTRAINT has no IF NOT EXISTS. Without this the file would be half
-- idempotent — CREATE TABLE IF NOT EXISTS above, hard failure here — and a run
-- that died partway could never be retried, which is the worst state for a
-- migration nobody has been able to execute yet.
create or replace function add_constraint_if_absent(p_table text, p_name text, p_ddl text)
returns void language plpgsql as $$
begin
  if not exists (
    select 1 from pg_constraint c
    join pg_class t on t.oid = c.conrelid
    where t.relname = p_table and c.conname = p_name
  ) then
    execute format('alter table %I add constraint %I %s', p_table, p_name, p_ddl);
  end if;
end;
$$;

create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- Writes the change log. row_to_json rather than a column list so a later
-- ALTER TABLE cannot silently stop being audited.
create or replace function log_library_change() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_org uuid;
begin
  v_org := case when tg_op = 'DELETE' then old.org_id else new.org_id end;
  insert into library_audit (org_id, table_name, row_id, action, old_row, new_row)
  values (
    v_org,
    tg_table_name,
    case when tg_op = 'DELETE' then old.id else new.id end,
    tg_op,
    case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end,
    case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end
  );
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

do $$
declare
  t text;
  ref_tables text[] := array[
    'jobs', 'job_profiles', 'salary_bands', 'title_mapping', 'career_paths',
    'levels', 'employees', 'categories', 'skills', 'competency_levels',
    'role_skill_map', 'job_grades', 'industries', 'industry_salary_factors',
    'industry_skills', 'seniority_levels', 'skill_proficiency',
    'benefits_catalog', 'benefits_observations', 'level_benefits_factors'
  ];
begin
  foreach t in array ref_tables loop
    -- The block itself. Identical on every table, by construction.
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

-- ─────────────────────────────────────────────────────────── natural keys ──
-- Added after the provenance pass because they are composite with org_id.
-- These are what make the reference library a master record rather than a pile
-- of rows: the same JobID cannot be defined twice for one organisation.

select add_constraint_if_absent('jobs', 'jobs_org_job_key',
  $c$unique (org_id, job_id)$c$);
select add_constraint_if_absent('job_profiles', 'job_profiles_org_job_key',
  $c$unique (org_id, job_id)$c$);
select add_constraint_if_absent('salary_bands', 'salary_bands_org_fn_level_key',
  $c$unique (org_id, function, level)$c$);
select add_constraint_if_absent('title_mapping', 'title_mapping_org_title_key',
  $c$unique (org_id, existing_title)$c$);
select add_constraint_if_absent('career_paths', 'career_paths_org_job_key',
  $c$unique (org_id, job_id)$c$);
select add_constraint_if_absent('levels', 'levels_org_level_key',
  $c$unique (org_id, level)$c$);
select add_constraint_if_absent('employees', 'employees_org_emp_key',
  $c$unique (org_id, employee_id)$c$);
select add_constraint_if_absent('categories', 'categories_org_cat_key',
  $c$unique (org_id, category)$c$);
select add_constraint_if_absent('skills', 'skills_org_skill_key',
  $c$unique (org_id, skill_id)$c$);
select add_constraint_if_absent('competency_levels', 'competency_levels_org_level_key',
  $c$unique (org_id, level)$c$);
select add_constraint_if_absent('role_skill_map', 'role_skill_map_org_job_skill_key',
  $c$unique (org_id, job_id, skill_id)$c$);
select add_constraint_if_absent('job_grades', 'job_grades_org_grade_key',
  $c$unique (org_id, grade)$c$);
select add_constraint_if_absent('industries', 'industries_org_ind_key',
  $c$unique (org_id, industry_id)$c$);
select add_constraint_if_absent('industry_salary_factors', 'isf_org_ind_fn_key',
  $c$unique (org_id, industry_id, function)$c$);
select add_constraint_if_absent('industry_skills', 'industry_skills_org_ind_skill_key',
  $c$unique (org_id, industry_id, skill_id)$c$);
select add_constraint_if_absent('seniority_levels', 'seniority_levels_org_code_key',
  $c$unique (org_id, l_code)$c$);
select add_constraint_if_absent('skill_proficiency', 'skill_proficiency_org_cat_lvl_key',
  $c$unique (org_id, category, level)$c$);
select add_constraint_if_absent('benefits_catalog', 'benefits_catalog_org_ben_key',
  $c$unique (org_id, benefit_id)$c$);
select add_constraint_if_absent('benefits_observations', 'benefits_observations_org_obs_key',
  $c$unique (org_id, obs_id)$c$);
select add_constraint_if_absent('level_benefits_factors', 'lbf_org_level_cat_key',
  $c$unique (org_id, level, category)$c$);

-- ────────────────────────────────────────────────────────── referential ──
-- Every one of these is a dangling reference the Validator can currently only
-- warn about, after the workbook is already loaded and in use.

select add_constraint_if_absent('job_profiles', 'job_profiles_job_fk',
  $c$foreign key (org_id, job_id) references jobs (org_id, job_id) on delete cascade$c$);

select add_constraint_if_absent('title_mapping', 'title_mapping_job_fk',
  $c$foreign key (org_id, job_id) references jobs (org_id, job_id) on delete cascade$c$);

select add_constraint_if_absent('career_paths', 'career_paths_job_fk',
  $c$foreign key (org_id, job_id) references jobs (org_id, job_id) on delete cascade$c$);

-- Nullable: the top of a ladder has no next step. Restrict, not cascade —
-- deleting a job should not silently rewrite someone else's career path.
select add_constraint_if_absent('career_paths', 'career_paths_next_job_fk',
  $c$foreign key (org_id, next_job_id) references jobs (org_id, job_id) on delete restrict$c$);

select add_constraint_if_absent('role_skill_map', 'role_skill_map_job_fk',
  $c$foreign key (org_id, job_id) references jobs (org_id, job_id) on delete cascade$c$);

select add_constraint_if_absent('role_skill_map', 'role_skill_map_skill_fk',
  $c$foreign key (org_id, skill_id) references skills (org_id, skill_id) on delete restrict$c$);

select add_constraint_if_absent('industry_salary_factors', 'isf_industry_fk',
  $c$foreign key (org_id, industry_id) references industries (org_id, industry_id) on delete cascade$c$);

select add_constraint_if_absent('industry_skills', 'industry_skills_industry_fk',
  $c$foreign key (org_id, industry_id) references industries (org_id, industry_id) on delete cascade$c$);

select add_constraint_if_absent('benefits_observations', 'benefits_observations_industry_fk',
  $c$foreign key (org_id, industry_id) references industries (org_id, industry_id) on delete cascade$c$);

-- ───────────────────────────────────────────────────────────── lookup idx ──

create index if not exists title_mapping_lookup_idx on title_mapping (org_id, lower(existing_title));
create index if not exists jobs_function_level_idx  on jobs (org_id, function, level);
create index if not exists role_skill_map_job_idx   on role_skill_map (org_id, job_id);

-- ─────────────────────────────────────────────────────────────────── RLS ──
--
-- Enabled on every table above, with no policy granting anon or authenticated
-- anything. That is not an oversight and not a placeholder: until auth lands
-- (Phase 0.3) there is no org claim to filter on, and a permissive policy
-- written now would be a hole nobody remembers to close.
--
-- service_role bypasses RLS, so the importer and the DB loader work. Jobsy is
-- server-rendered Streamlit, so its Supabase key is a server-side secret and
-- using the service key is legitimate here in a way it would not be in a
-- browser app. persistence_service.py's setup notes should say so explicitly.
--
-- Phase 0.3 replaces this comment with, per table:
--   create policy org_isolation on <table> for all to authenticated
--     using  (org_id = (auth.jwt() ->> 'org_id')::uuid)
--     with check (org_id = (auth.jwt() ->> 'org_id')::uuid);

alter table orgs               enable row level security;
alter table library_revisions  enable row level security;
alter table library_audit      enable row level security;

-- WRONG, and left here as the record: this revoke does nothing. Supabase grants
-- every privilege on a new table to anon, authenticated, service_role and
-- postgres EXPLICITLY, so removing a grant from `public` leaves all four with
-- DELETE and TRUNCATE. service_role — what the importer authenticates as —
-- could erase the trail. Corrected in 0003, which revokes from the roles by
-- name and proves it by trying as service_role.
revoke update, delete on library_audit from public;

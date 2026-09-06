-- 0017_library_review_policy.sql
--
-- When the reference library needs looking at again, per table, said out loud.
--
-- ── WHY NOT ONE AGE ───────────────────────────────────────────────────────
--
-- `ops_jobsy_library` already reports an `oldest_days` and the dashboard warns
-- past 365. That number pools six tables into one, and the six age at
-- completely different rates, so the warning fires on whichever happens to be
-- oldest and then names salary data whether or not salary is what aged. A
-- pooled age is a number that is always true and never actionable.
--
-- Salary moves on a calendar: CAO rounds, the January minimum wage, the annual
-- Orden de Cotización. A skills taxonomy moves with the labour market, over
-- years. A grade ladder is partly ours and partly not — see below, because that
-- one was nearly got wrong.
--
-- ── THE SHAPE, AND WHY IT IS A TABLE ──────────────────────────────────────
--
-- The intervals are DATA, not code. They live in a table so the owner can
-- change one without a migration and without a deploy, and so the reason for
-- each is stored beside it rather than in someone's memory. This mirrors
-- `Claim.review_after_months` in services/country_packs, which already reports
-- "STALE (8 months since this was checked, against an interval of 6)". One
-- mechanism for the same idea, in both halves of the product.
--
-- NULL means NO REVIEW INTERVAL, and that is a real answer rather than an
-- omission: some of these tables are this product's own constructs. A
-- competency level does not go out of date because a year passed; it changes
-- when somebody decides to change it.
--
-- ── THE ONE THAT WAS NEARLY MISCLASSIFIED ─────────────────────────────────
--
-- `job_grades` reads like a product construct — a fourteen-rung ladder we
-- defined — and was first written down here as never-expiring on exactly that
-- reasoning. It carries pay_min, pay_p25, pay_p50, pay_p75 and pay_max, all
-- fourteen rows populated, running from 24.000 to 280.000. That is Dutch market
-- pay sitting inside a table whose NAME suggests structure, and structure was
-- the reason given for exempting it. Measured before seeding, not after.

create table if not exists library_review_policy (
  table_name           text primary key,
  review_after_months  int,
  reason               text not null,
  updated_at           timestamptz default now()
);

comment on table library_review_policy is
  'How often each reference-library table needs looking at again, and why. '
  'NULL months = no interval, because the table is this product''s own '
  'construct rather than a reading of a market. Editable without a deploy: '
  'ops_jobsy_review() drives entirely off these rows.';

insert into library_review_policy (table_name, review_after_months, reason) values
  -- Pay. Moves on a calendar, so a year is already generous.
  ('salary_bands',            12, 'Market pay. A CAO round or a January minimum wage lands every year, and a band that missed one understates every compa-ratio built on it.'),
  ('job_grades',              12, 'Carries pay_min through pay_max for all fourteen rungs, 24.000 to 280.000. The ladder is ours; the money in it is the market''s.'),
  ('pay_mix',                 12, 'Target variable pay and 13th-month percentages. Policy data that follows the same annual cycle as base pay.'),
  ('pay_elements',            12, 'Typical values and statutory status. Holiday allowance and its legal footing are restated by law and collective agreement every year.'),
  ('industry_salary_factors', 12, 'Sector multipliers applied on top of a band. Stale here multiplies a stale number by a stale factor.'),
  ('level_benefits_factors',  12, 'Benefit values by level, in money.'),

  -- Benchmarks. These do not expire, they become less representative.
  ('benefits_observations',   18, 'A benchmark is a measurement taken on a date and stays true as a measurement. What decays is how well it represents the market now.'),
  ('benefits_catalog',        18, 'What a benefit IS barely moves; whether it is statutory and what it is typically worth does.'),

  -- The labour market, which moves in years rather than seasons.
  ('jobs',                    24, 'The standard role set. New roles appear and old ones stop being asked for, but not on a yearly cycle.'),
  ('job_profiles',            24, 'What a role does. Drifts with the market slowly and visibly.'),
  ('skills',                  24, 'The skills taxonomy. Negotiation is still negotiation; what changes is which skills employers name.'),
  ('role_skill_map',          24, 'Which skills a role requires — the half of the taxonomy that actually dates.'),
  ('title_mapping',           24, 'Real-world titles seen in client files. Grows by use rather than by review, so this is a prompt to prune, not to rebuild.'),
  ('industry_skills',         24, 'Sector-specific skills.'),
  ('career_paths',            24, 'Which role follows which. Mostly stable; national licence gates are the part worth re-reading.'),

  -- Ours. These change when somebody decides to change them.
  ('levels',                  null, 'The product''s own four-rung scale.'),
  ('seniority_levels',        null, 'L1..L5 and their names are ours and belong to no market. The grade BINDING is national and lives in seniority_grade_binding, which follows job_grades.'),
  ('competency_levels',       null, 'The five-level behavioural scale. Settled 2026-09-06 as the product''s own; it does not go out of date because a year passed.'),
  ('skill_proficiency',       null, 'Behavioural anchors describing what a level looks like.'),
  ('industries',              null, 'The sector list itself. Only its FACTORS move, and those are above.'),
  ('categories',              null, 'Skill categories.')
on conflict (table_name) do nothing;

-- ══════════════════════════════════════════════════════════════════════════
-- ops_jobsy_review() — what is due, and what it would mean if nobody looked
-- ══════════════════════════════════════════════════════════════════════════
--
-- Driven entirely by the policy table, so adding a table to the review is an
-- INSERT rather than an edit to this function. Table names are validated with
-- to_regclass and quoted with %I: the rows are admin-only, but a function that
-- interpolates a name into SQL should not depend on that being true forever.
--
-- Reports `updated_at`, the content clock the existing panel already uses, NOT
-- created_at — a row imported today from a 2024 survey is not fresh, and
-- created_at would call it fresh.
--
-- Returns every policy row, including the ones with no interval and the ones
-- comfortably inside it. A panel that lists only what is overdue cannot be
-- distinguished from a panel that is broken.

create or replace function public.ops_jobsy_review()
returns json
language plpgsql
stable
set search_path to 'public', 'pg_catalog'
as $$
declare
  p        record;
  last_at  timestamptz;
  n_rows   bigint;
  out      json[] := '{}';
begin
  for p in select * from library_review_policy order by
             (review_after_months is null), review_after_months, table_name
  loop
    if to_regclass('public.' || quote_ident(p.table_name)) is null then
      -- A policy row for a table that no longer exists is a finding, not a
      -- crash: it means a rename happened and the review silently stopped
      -- covering something.
      out := out || to_json(json_build_object(
        'table_name', p.table_name, 'missing', true, 'reason', p.reason));
      continue;
    end if;

    execute format('select count(*), max(updated_at) from %I', p.table_name)
      into n_rows, last_at;

    out := out || to_json(json_build_object(
      'table_name',          p.table_name,
      'rows',                n_rows,
      'last_updated',        last_at,
      'months_old',          case when last_at is null then null
                             else floor(extract(epoch from now() - last_at) / 2629800)::int end,
      'review_after_months', p.review_after_months,
      'reason',              p.reason,
      'due',                 case
                               when p.review_after_months is null then false
                               when last_at is null then true
                               else extract(epoch from now() - last_at) / 2629800
                                    >= p.review_after_months
                             end,
      'missing',             false));
  end loop;
  return array_to_json(out);
end $$;

comment on function public.ops_jobsy_review() is
  'Per-table review state of the reference library for the PH-LiveOps '
  'dashboard. Replaces the pooled oldest_days signal, which fired on whichever '
  'of six tables happened to be oldest and then named salary regardless.';

revoke all on function public.ops_jobsy_review() from public;
grant execute on function public.ops_jobsy_review() to service_role;

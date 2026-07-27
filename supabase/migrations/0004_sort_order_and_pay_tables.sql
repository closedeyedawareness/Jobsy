-- 0004_sort_order_and_pay_tables.sql
--
-- Two changes, both cheaper now than later: the tables are still empty.
--
-- 1. levels."order" -> levels.sort_order
--
-- `order` is a reserved word, so every reference to it needed quoting, and it
-- is also PostgREST's own query parameter — the column and the API verb that
-- sorts results share a name. That is a hazard on the write path the importer
-- has not yet exercised. Removing the collision beats testing whether it bites.
-- Nothing reads this column yet; core/catalog.py's "Order" is the WORKBOOK
-- column and is untouched.
--
-- 2. pay_elements and pay_mix
--
-- SHEET_MAP has never loaded these two, which is why the structural pay-gap
-- analysis could only ever see base salary. Now that services/pay_equity_service
-- .analyze_variable_pay_exposure() reads PayMix, leaving it out of the database
-- would leave that feature depending on a workbook after the workbook stops
-- being the master — working, quietly, off whatever the file last said. That is
-- the exact failure Phase 0 exists to end.
--
-- Column types mirror the sheet rather than improving on it. lti_eligible stays
-- text holding 'Yes'/'No' instead of becoming boolean, because W5's acceptance
-- gate is that a DB-loaded frame equals an Excel-loaded one; a helpfully better
-- type here becomes a difference the parity test has to paper over.

alter table levels rename column "order" to sort_order;

create table if not exists pay_elements (
  element_id     text not null,
  name           text not null,
  category       text,          -- Fixed cash | Variable cash | Benefits | Long-term
  basis          text,
  typical_value  text,          -- free text: '8%', '0-40% by role', 'varies'
  statutory_nl   text,
  taxable        text,
  description    text
);

create table if not exists pay_mix (
  function              text not null,
  level                 text not null,
  target_variable_pct   numeric,
  thirteenth_month_pct  numeric,
  lti_eligible          text,
  notes                 text,
  constraint pay_mix_target_variable_sane
    check (target_variable_pct is null or (target_variable_pct >= 0 and target_variable_pct <= 200)),
  constraint pay_mix_thirteenth_sane
    check (thirteenth_month_pct is null or (thirteenth_month_pct >= 0 and thirteenth_month_pct <= 100))
);

-- The same provenance block every other reference table carries. Kept as a
-- loop over a one-element-per-table list for the same reason 0001 did it:
-- so the block cannot drift from one table to the next.
do $$
declare t text;
begin
  foreach t in array array['pay_elements', 'pay_mix'] loop
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
    execute format($f$create trigger %I before update on %I
                      for each row execute function set_updated_at()$f$,
                   t || '_set_updated_at', t);
    execute format('drop trigger if exists %I on %I', t || '_audit', t);
    execute format($f$create trigger %I after insert or update or delete on %I
                      for each row execute function log_library_change()$f$,
                   t || '_audit', t);

    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

select add_constraint_if_absent('pay_elements', 'pay_elements_org_element_key',
  $c$unique (org_id, element_id)$c$);
select add_constraint_if_absent('pay_mix', 'pay_mix_org_fn_level_key',
  $c$unique (org_id, function, level)$c$);

-- A pay mix describes a Function x Level that must actually exist as a pay
-- cohort. The two sheets already agree exactly — 45 keys for 45 — and the
-- variable-pay exposure analysis is only meaningful where they do, so the
-- agreement becomes a constraint rather than a coincidence that tests re-check.
select add_constraint_if_absent('pay_mix', 'pay_mix_salary_band_fk',
  $c$foreign key (org_id, function, level)
     references salary_bands (org_id, function, level) on delete cascade$c$);

-- Audit and revisions are append-only for the same reasons as 0003; the grants
-- there are table-specific, so nothing new is needed for these two.

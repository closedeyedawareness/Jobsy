-- Adversarial test for 0012: the country dimension.
--
-- The point of this migration is that adding Belgium later is importing rows,
-- not writing a migration. So what is tested is mostly that the schema now
-- ADMITS a second country -- which it could not before, because of composite
-- uniques from 0001 -- and that it still refuses the things that would make
-- country data untrustworthy.
\set ON_ERROR_STOP off
\pset format unaligned
\pset tuples_only on

create or replace function t_eq(label text, got anyelement, want anyelement) returns text
language plpgsql as $$
begin
  if got is not distinct from want then
    return 'ok    ' || label || ' = ' || coalesce(got::text, 'null');
  end if;
  return 'FAIL  ' || label || ' = ' || coalesce(got::text,'null') || ', wanted ' || coalesce(want::text,'null');
end $$;

create or replace function t_reject(label text, stmt text) returns text
language plpgsql as $$
begin
  execute stmt;
  return 'FAIL  (accepted!)  ' || label;
exception when others then
  return 'ok    rejected     ' || label || '  [' || split_part(sqlerrm, E'\n', 1) || ']';
end $$;

create or replace function t_accept(label text, stmt text) returns text
language plpgsql as $$
begin
  execute stmt;
  return 'ok    accepted     ' || label;
exception when others then
  return 'FAIL  (rejected!)  ' || label || '  [' || split_part(sqlerrm, E'\n', 1) || ']';
end $$;

select id as org_lib from orgs where slug='default' \gset

select '── the registry ───────────────────────────────────────────────────';
select t_eq('the Netherlands is live', (select is_live from countries where code='NL'), true);
select t_eq('EU exists as a fallback scope', (select count(*)::int from countries where code='EU'), 1);
select t_eq('  and is deliberately NOT offerable as a country',
            (select is_live from countries where code='EU'), false);
select t_eq('markets are seeded but dark until somebody finishes them',
            (select count(*)::int from countries where not is_live and code <> 'EU') >= 7, true);
select t_eq('non-euro markets are present, so nothing may assume EUR',
            (select count(*)::int from countries where currency <> 'EUR') >= 3, true);
select t_reject('a three-letter country code',
  $$insert into countries (code, name, currency) values ('NLD','Nope','EUR')$$);
select t_reject('a lower-case country code',
  $$insert into countries (code, name, currency) values ('be','Nope','EUR')$$);
select t_reject('a currency that is not a currency',
  $$insert into countries (code, name, currency) values ('XX','Nope','euros')$$);

select '';
select '── the thing that was actually blocked before ─────────────────────';
-- 0001 had unique (org_id, function, level). A German band for the same
-- function and level could not exist at all, whatever anyone imported.
select t_accept('a Dutch band for B/5',
  format($$insert into salary_bands (org_id, country, function, level, min, max)
           values (%L, 'NL', 'B', '5', 45000, 65000)$$, :'org_lib'));
select t_accept('a GERMAN band for the SAME function and level',
  format($$insert into salary_bands (org_id, country, function, level, min, max)
           values (%L, 'DE', 'B', '5', 52000, 74000)$$, :'org_lib'));
select t_accept('and a Polish one, in its own currency''s magnitude',
  format($$insert into salary_bands (org_id, country, function, level, min, max)
           values (%L, 'PL', 'B', '5', 90000, 140000)$$, :'org_lib'));
select t_reject('but still not TWO Dutch bands for B/5',
  format($$insert into salary_bands (org_id, country, function, level, min, max)
           values (%L, 'NL', 'B', '5', 1, 2)$$, :'org_lib'));
select t_eq('three markets now coexist for one function and level',
            (select count(*)::int from salary_bands
              where function='B' and level='5' and org_id = :'org_lib'::uuid), 3);

select t_accept('a German grade alongside the Dutch one',
  format($$insert into job_grades (org_id, country, grade, grade_label, level_band)
           values (%L, 'DE', 9, 'Referenzstufe 9', 'Senior')$$, :'org_lib'));
select t_accept('a job to map onto',
  format($$insert into jobs (org_id, job_id, standard_title, function, level)
           values (%L, 'CTRY-1', 'Data Analyst', 'B', '5')$$, :'org_lib'));
select t_accept('a German title mapping for a title Dutch also uses',
  format($$insert into title_mapping (org_id, country, existing_title, job_id)
           values (%L, 'DE', 'Data Analyst', 'CTRY-1')$$, :'org_lib'));

select '';
select '── country data cannot be invented ────────────────────────────────';
select t_reject('a band for a country that is not in the registry',
  format($$insert into salary_bands (org_id, country, function, level, min, max)
           values (%L, 'ZZ', 'B', '9', 1, 2)$$, :'org_lib'));
select t_reject('an employee in a country that does not exist',
  format($$insert into employees (org_id, country, employee_id, name)
           values (%L, 'ZZ', 'E-ZZ', 'Nobody')$$, :'org_lib'));
select t_reject('a client whose home country is not in the registry',
  $$update orgs set default_country = 'ZZ' where slug = 'default'$$);
select t_eq('every priced row carries a country',
            (select count(*)::int from salary_bands where country is null), 0);
select t_eq('existing rows were backfilled as Dutch, not left to guess',
            (select count(*)::int from salary_bands where country = 'NL') >= 1, true);

select '';
select '── an employee''s country is not the client''s country ─────────────';
-- The customers this is sold to are multinationals. A roster is a mix, and
-- treating one client as one market is the assumption that produces a reported
-- pay gap made of nothing but who works where.
select t_accept('a client based in the Netherlands',
  $$update orgs set default_country = 'NL' where slug = 'northwind'$$);
select t_accept('  with a German employee',
  format($$insert into employees (org_id, country, employee_id, name)
           select id, 'DE', 'E-DE-1', 'Someone' from orgs where slug='northwind'$$));
select t_accept('  and a Polish one',
  format($$insert into employees (org_id, country, employee_id, name)
           select id, 'PL', 'E-PL-1', 'Someone Else' from orgs where slug='northwind'$$));
select t_eq('one client, two employee countries',
            (select count(distinct country)::int from employees e
               join orgs o on o.id = e.org_id where o.slug='northwind'), 2);
select t_accept('an employee with no country stated — missing, not guessed',
  format($$insert into employees (org_id, employee_id, name)
           select id, 'E-UNKNOWN', 'Unstated' from orgs where slug='northwind'$$));
select t_eq('  and it stays null rather than inheriting the client''s',
            (select country from employees where employee_id='E-UNKNOWN'), null::text);

select '';
select '── resolution falls back to EU, then stops ────────────────────────';
select t_eq('a country with its own rows resolves to itself',
            app.resolve_country('salary_bands', :'org_lib'::uuid, 'DE'), 'DE');
select t_eq('a country with none resolves to nothing yet',
            app.resolve_country('salary_bands', :'org_lib'::uuid, 'SE'), null::text);
select t_accept('seed an EU baseline row',
  format($$insert into salary_bands (org_id, country, function, level, min, max)
           values (%L, 'EU', 'B', '7', 50000, 70000)$$, :'org_lib'));
select t_eq('  now an uncovered country falls back to it',
            app.resolve_country('salary_bands', :'org_lib'::uuid, 'SE'), 'EU');
select t_eq('  but a covered one still prefers its own',
            app.resolve_country('salary_bands', :'org_lib'::uuid, 'DE'), 'DE');
select t_reject('resolve_country cannot be used to read an arbitrary object',
  $$select app.resolve_country('orgs; drop table countries', null, 'NL')$$);

select '';
select '── who may read the market list ───────────────────────────────────';
set role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', false) is not null as _;
select t_eq('a signed-in user sees the countries',
            (select count(*)::int from countries) >= 10, true);
-- An UPDATE that matches no rows raises nothing, so t_reject would call that a
-- pass. Rows affected is what distinguishes denied from "wrote nothing" -- the
-- same trap 0008's isolation test was built wrong around the first time.
select t_eq('but cannot open a market themselves',
            (with u as (update countries set is_live = true where code = 'DE' returning 1)
             select count(*)::int from u), 0);
select t_reject('nor invent one',
  $$insert into countries (code, name, currency) values ('QQ','Freedonia','EUR')$$);
reset role;
set role anon;
select t_reject('anon cannot enumerate which markets this product covers',
  $$select code from countries$$);
reset role;
select t_eq('nothing was opened while testing',
            (select count(*)::int from countries where is_live and code <> 'NL'), 0);

-- Adversarial test for 0011: per-partner branding.
--
-- Two things are being checked, and only one of them is about looking nice.
-- The first is that malformed branding cannot be stored, because these values
-- are concatenated into codes people dictate over the phone and into CSS served
-- to a browser. The second is the reach question: a client's staff must be able
-- to read their reseller's brand, and must NOT be able to read anyone else's --
-- the partner list is a customer list.
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

create or replace function t_write_blocked(label text, stmt text) returns text
language plpgsql as $$
declare n int;
begin
  execute stmt;
  get diagnostics n = row_count;
  if n = 0 then
    return 'ok    0 rows       ' || label || '  [no row matched the policy]';
  end if;
  return 'FAIL  WROTE ' || n || ' ROW(S)  ' || label;
exception when others then
  return 'ok    blocked       ' || label || '  [' || split_part(sqlerrm, E'\n', 1) || ']';
end $$;

create or replace function t_accept(label text, stmt text) returns text
language plpgsql as $$
declare n int;
begin
  execute stmt;
  get diagnostics n = row_count;
  if n = 0 then return 'FAIL  (0 rows)     ' || label; end if;
  return 'ok    allowed       ' || label;
exception when others then
  return 'FAIL  (blocked!)   ' || label || '  [' || split_part(sqlerrm, E'\n', 1) || ']';
end $$;

select '── defaults keep an unbranded deployment working ───────────────────';
select t_eq('every partner has a product name',
            (select count(*)::int from partners where product_name is null), 0);
select t_eq('and a usable code prefix',
            (select count(*)::int from partners where code_prefix !~ '^[A-Z][A-Z0-9]{1,9}-$'), 0);
select t_eq('the default is still Jobsy until somebody changes it',
            (select product_name from partners where slug='default'), 'Jobsy');

select '';
select '── branding that would break something is refused ──────────────────';
select t_accept('a legitimate rebrand', $$
  update partners set product_name = 'Reward Insight', code_prefix = 'REWARD-',
                      primary_color = '#0F6E5C', accent_color = '#8FD6C4',
                      logo_url = 'https://cdn.example/logo.svg'
   where slug = 'acme-consult' $$);

select t_write_blocked('an empty product name — renders as a gap where the title goes',
  $$update partners set product_name = '   ' where slug='acme-consult'$$);
select t_write_blocked('a product name longer than the header can hold',
  $$update partners set product_name = repeat('x', 60) where slug='acme-consult'$$);
select t_write_blocked('a lower-case prefix (codes are dictated and typed back)',
  $$update partners set code_prefix = 'acme-' where slug='acme-consult'$$);
select t_write_blocked('a prefix with no separator',
  $$update partners set code_prefix = 'ACME' where slug='acme-consult'$$);
select t_write_blocked('a prefix of punctuation',
  $$update partners set code_prefix = '**-' where slug='acme-consult'$$);
select t_write_blocked('a colour that is not a colour',
  $$update partners set primary_color = 'darkish green' where slug='acme-consult'$$);
select t_write_blocked('a three-digit hex, which CSS accepts and this does not',
  $$update partners set accent_color = '#abc' where slug='acme-consult'$$);
select t_write_blocked('a logo over plain http — mixed content on the sign-in page',
  $$update partners set logo_url = 'http://cdn.example/logo.svg' where slug='acme-consult'$$);
select t_accept('clearing the logo entirely',
  $$update partners set logo_url = null where slug='rival-corp'$$);

select t_eq('the rebrand survived all of that',
            (select product_name from partners where slug='acme-consult'), 'Reward Insight');

select '';
select '── two partners may share a prefix, deliberately ───────────────────';
-- Uniqueness lives in the code body (31^10), not the label. A unique constraint
-- here would only fail at the moment an operator is onboarding a customer.
select t_accept('a second partner picking the same prefix',
  $$update partners set code_prefix = 'REWARD-' where slug='rival-corp'$$);
select t_eq('and session codes are still globally unique on the body',
            (select count(*)::int from pg_indexes
              where tablename='jobsy_sessions' and indexdef like '%session_code%UNIQUE%'
                 or (tablename='jobsy_sessions' and indexdef ilike '%unique%session_code%')) >= 1, true);

select '';
select '── the partner list is a customer list ─────────────────────────────';
-- A client's own staff must read their reseller's brand. They must not be able
-- to enumerate the others: who else resells this, and to whom, is commercially
-- sensitive in a way a logo is not.
set role authenticated;
select set_config('request.jwt.claim.sub', '22222222-2222-2222-2222-222222222222', false) is not null as _;
select t_eq('Northwind HR reads the brand of the reseller they are served by',
            (select product_name from partners where slug='acme-consult'), 'Reward Insight');
select t_eq('and cannot see a competing reseller at all',
            (select count(*)::int from partners where slug='rival-corp'), 0);
select t_eq('so they see exactly one partner',
            (select count(*)::int from partners), 1);
select t_write_blocked('a client_admin rebranding their own reseller',
  $$update partners set product_name = 'Hijacked' where slug='acme-consult'$$);
reset role;

set role authenticated;
select set_config('request.jwt.claim.sub', '11111111-1111-1111-1111-111111111111', false) is not null as _;
select t_eq('the reseller''s own consultant reads their brand',
            (select product_name from partners where slug='acme-consult'), 'Reward Insight');
select t_write_blocked('and still cannot change it from a browser',
  $$update partners set code_prefix = 'HIJACK-' where slug='acme-consult'$$);
reset role;

set role anon;
select t_write_blocked('anon reading the partner list — this is why the sign-in page is neutral',
  $$select product_name from partners$$);
reset role;

select t_eq('nothing was hijacked',
            (select count(*)::int from partners where product_name = 'Hijacked'), 0);
select t_eq('nor the prefix',
            (select count(*)::int from partners where code_prefix = 'HIJACK-'), 0);

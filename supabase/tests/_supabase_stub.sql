-- Local stand-in for the parts of Supabase that a plain Postgres has not got.
-- Only enough to run the real migrations unmodified: the four roles Supabase
-- creates, the auth schema, and auth.uid() reading the same GUC that Supabase's
-- own auth.uid() reads. Nothing here ships.
do $$ begin
  if not exists (select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
  if not exists (select 1 from pg_roles where rolname='authenticator') then create role authenticator noinherit login; end if;
end $$;
grant anon, authenticated, service_role to authenticator;
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;

create schema if not exists auth;
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text unique
);
-- Mirrors Supabase's own auth.uid(), which reads BOTH shapes: the legacy
-- per-claim GUC and the single JSON blob PostgREST 12 actually sets. The first
-- version of this stub read only the legacy one, which works when a test sets
-- the GUC by hand and fails the moment a real PostgREST is put in front of it.
create or replace function auth.uid() returns uuid
language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
  )::uuid;
$$;
grant usage on schema auth to anon, authenticated, service_role;
grant select on auth.users to anon, authenticated, service_role;

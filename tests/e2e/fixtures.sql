-- Fixtures for tests/e2e/journey.py.
--
-- Two resellers with different branding, three clients between them, and five
-- people with different roles. The shapes that matter are the two neighbours:
-- Northwind and Contoso share a partner, and Initech belongs to a rival — so
-- "same partner, different client" and "different partner" are both testable.
--
-- Passwords live in auth.users here because the shim checks them. GoTrue holds
-- them in the real thing; nothing in this file ships.

alter table auth.users add column if not exists password text;
alter table auth.users add column if not exists user_metadata jsonb not null default '{}'::jsonb;

insert into partners (slug, name, product_name, code_prefix, primary_color)
values ('acme','Acme Consulting','Reward Insight','REWARD-','#0F6E5C'),
       ('rival','Rival Corp','Rival People','RIVAL-','#B4451F')
on conflict (slug) do nothing;

insert into orgs (slug, name, partner_id)
  select 'northwind','Northwind BV', id from partners where slug='acme' on conflict (slug) do nothing;
insert into orgs (slug, name, partner_id)
  select 'contoso','Contoso NV', id from partners where slug='acme' on conflict (slug) do nothing;
insert into orgs (slug, name, partner_id)
  select 'initech','Initech GmbH', id from partners where slug='rival' on conflict (slug) do nothing;

-- The shared library, as production has it: owned by the seeded default org and
-- readable by everyone signed in.
insert into jobs (org_id, job_id, standard_title, function, level)
  select id, 'J-1', 'Data Analyst', 'B', '5' from orgs where slug='default' on conflict do nothing;
insert into jobs (org_id, job_id, standard_title, function, level)
  select id, 'J-2', 'Senior Data Analyst', 'B', '6' from orgs where slug='default' on conflict do nothing;
insert into salary_bands (org_id, function, level, min, max)
  select id, 'B', '5', 45000, 65000 from orgs where slug='default' on conflict do nothing;

insert into auth.users (id, email, password, user_metadata) values
 ('a0000000-0000-0000-0000-000000000001','hr@northwind.example','northwind-pw-2026','{}'),
 ('a0000000-0000-0000-0000-000000000002','viewer@northwind.example','viewer-pw-2026','{}'),
 ('a0000000-0000-0000-0000-000000000003','consultant@acme.example','acme-pw-2026','{}'),
 ('a0000000-0000-0000-0000-000000000004','hr@initech.example','initech-pw-2026','{}'),
 ('a0000000-0000-0000-0000-000000000005','newstarter@northwind.example','temp-pw-2026','{"must_change_password": true}')
on conflict (id) do nothing;

-- The consultant holds ONE partner-scoped membership and must show as
-- partner_admin on BOTH Acme clients. hr@northwind is a client_admin on one of
-- those same clients -- which is exactly the pair that exposed the defect the
-- README describes, so do not simplify this.
insert into memberships (user_id, org_id, role)
  select 'a0000000-0000-0000-0000-000000000001', id, 'client_admin' from orgs where slug='northwind' on conflict do nothing;
insert into memberships (user_id, org_id, role)
  select 'a0000000-0000-0000-0000-000000000002', id, 'viewer' from orgs where slug='northwind' on conflict do nothing;
insert into memberships (user_id, partner_id, role)
  select 'a0000000-0000-0000-0000-000000000003', id, 'partner_admin' from partners where slug='acme' on conflict do nothing;
insert into memberships (user_id, org_id, role)
  select 'a0000000-0000-0000-0000-000000000004', id, 'client_admin' from orgs where slug='initech' on conflict do nothing;
insert into memberships (user_id, org_id, role)
  select 'a0000000-0000-0000-0000-000000000005', id, 'analyst' from orgs where slug='northwind' on conflict do nothing;

-- One saved roster per client, so "can I open the other one" has an answer.
insert into jobsy_sessions (org_id, session_code, org_label, payload)
  select id, 'REWARD-NORTHWIND', 'Northwind BV',
         '{"upload_df":[{"name":"Anna de Vries","salary":61000,"gender":"F"}]}'::jsonb
    from orgs where slug='northwind' on conflict (session_code) do nothing;
insert into jobsy_sessions (org_id, session_code, org_label, payload)
  select id, 'RIVAL-INITECHXX', 'Initech GmbH',
         '{"upload_df":[{"name":"Carl Init","salary":72000,"gender":"M"}]}'::jsonb
    from orgs where slug='initech' on conflict (session_code) do nothing;

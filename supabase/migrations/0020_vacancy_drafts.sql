-- 0020 — vacancy_draft
--
-- RECONSTRUCTED 2026-09-06 from the live schema of qpprcmmdeqlbursogosu.
--
-- The table was applied directly against the database and the file was never
-- written: 4234a4e says "Migration 0020 applied", the ledger records
-- `vacancy_drafts` at 20260906180336, and there was no .sql anywhere in the
-- repo, on any branch, in the stash or on disk. So the database held an object
-- the repository could not recreate — a working environment that cannot be
-- rebuilt from source is a working environment that exists once.
--
-- This file is the DDL read back out of the running database: columns,
-- constraints, index, RLS and the table comment as they actually are. It is
-- written to match reality, not to change it. Applying it to a fresh database
-- should produce the schema that is live today; applying it to this one is a
-- no-op guarded by IF NOT EXISTS.
--
-- If the author of 4234a4e has the original text, prefer it over this and drop
-- this file — a reconstruction records what a migration DID, never why, and the
-- why is the half that matters in a year.

create table if not exists public.vacancy_draft (
  id                   uuid not null default gen_random_uuid(),
  org_id               uuid not null,
  job_id               text not null,
  country              text not null,
  -- Both texts, deliberately. generated_text is what the software proposed;
  -- approved_text is what the employer settled on. The pairing is what makes
  -- terms clause 2(b) -- "you decide what is published" -- verifiable rather
  -- than asserted, and it is the evidence behind the AI Act art. 6(3) reading
  -- that this is an additional layer to a human activity rather than a system
  -- that decides. Dropping approved_text would not simplify the table; it
  -- would remove the proof.
  generated_text       text not null,
  approved_text        text,
  approved_by          text,
  approved_at          timestamptz,
  requirements         jsonb not null default '[]'::jsonb,
  questions            jsonb not null default '[]'::jsonb,
  -- Which revision of the library the draft was composed from, so "what did
  -- the system propose" still has an answer once the library has moved on.
  library_revision_id  uuid,
  created_at           timestamptz not null default now(),
  created_by           text,
  constraint vacancy_draft_pkey primary key (id),
  constraint vacancy_draft_org_id_fkey
    foreign key (org_id) references public.orgs(id) on delete cascade,
  constraint vacancy_draft_country_fkey
    foreign key (country) references public.countries(code),
  constraint vacancy_draft_library_revision_id_fkey
    foreign key (library_revision_id) references public.library_revisions(id)
);

create index if not exists vacancy_draft_org_idx
  on public.vacancy_draft using btree (org_id, country, job_id);

alter table public.vacancy_draft enable row level security;

do $$
begin
  if not exists (select 1 from pg_policy
                 where polrelid = 'public.vacancy_draft'::regclass
                   and polname = 'vacancy_draft_read') then
    create policy vacancy_draft_read on public.vacancy_draft
      for select to authenticated
      using (app.can_read_org(org_id));
  end if;
  if not exists (select 1 from pg_policy
                 where polrelid = 'public.vacancy_draft'::regclass
                   and polname = 'vacancy_draft_write') then
    create policy vacancy_draft_write on public.vacancy_draft
      for all to authenticated
      using (app.can_write_org(org_id))
      with check (app.can_write_org(org_id));
  end if;
end $$;

comment on table public.vacancy_draft is
  'A vacancy this product DRAFTED and a person then published, or did not. Both '
  'texts are kept: generated_text is what the software proposed and '
  'approved_text is what the employer settled on. That pairing is what makes '
  'terms clause 2(b) — "you decide what is published" — verifiable rather than '
  'asserted, and it is the evidence behind the AI Act art. 6(3) reading that '
  'this is an additional layer to human activity. See docs/terms-clauses.md.';

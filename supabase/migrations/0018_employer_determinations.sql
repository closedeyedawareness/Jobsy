-- 0018_employer_determinations.sql
--
-- The judgement layer, first slice. Design: docs/employer-determinations.md.
--
-- ── WHY THIS EXISTS ───────────────────────────────────────────────────────
--
-- `bridge()` already tells a client, on screen, that "an employer may adopt an
-- internal equivalence as a business judgement — that belongs to them, marked
-- CONVENTIE, and is not a fact about the two markets." It then offers them
-- nowhere to record it. The CONVENTIE marker exists in the hardness vocabulary
-- and nothing in this product has ever written one. That is not a gap in the
-- design; it is a sentence the design wrote and never honoured.
--
-- ── WHY THIS SHAPE AND NOT A COMMENT COLUMN ──────────────────────────────
--
-- `review_service` is the prototype of this idea and gets closest: a human
-- approves a title-to-role match and it is written back to title_mapping with
-- `source = 'Approved in review by X'`. That is a LABEL. It does not carry the
-- question, the purpose the answer is valid for, what the system proposed at the
-- time, which options were rejected, who participated in which capacity, or what
-- should reopen it. This generalises that module rather than sitting beside it.
--
-- ── APPEND-ONLY, ON PURPOSE ──────────────────────────────────────────────
--
-- A determination is superseded, never edited. If the matching engine improves,
-- the record must still show what the system presented WHEN THE EMPLOYER
-- DECIDED — otherwise the dossier proves the decision was reasonable against
-- evidence that did not exist yet. `system_proposed` and `engine_version` are
-- stored for that reason and are never recomputed.
--
-- ── RETENTION, WHICH IS NOT SETTLED HERE ─────────────────────────────────
--
-- Directive (EU) 2023/970 specifies NO retention period. What it specifies
-- instead decides the question anyway: Art. 18 reverses the burden of proof, so
-- the employer must prove no discrimination, and Art. 21(1) sets limitation
-- periods of at least three years which "shall not begin to run before the
-- claimant is aware, or can reasonably be expected to be aware, of an
-- infringement" — in some member states not until the employment ends.
--
-- Three years is a floor, not an answer, and DELETING THE RECORD DOES NOT
-- REDUCE EXPOSURE; it removes the defence and leaves the claim. So nothing here
-- carries a deletion rule yet. `population_at_decision` is stored as a COUNT
-- rather than a set of people, so the determination can outlive the roster it
-- was made about without holding personal data it no longer needs.

-- ══════════════════════════════════════════════════════════════════════════
-- 1. The determination
-- ══════════════════════════════════════════════════════════════════════════

create table if not exists employer_determination (
  id                      uuid primary key default gen_random_uuid(),
  org_id                  uuid not null references orgs(id) on delete cascade,

  determination_type      text not null,
  countries               text[] not null default '{}',
  scope                   jsonb  not null default '{}'::jsonb,
  population_at_decision  int,

  -- The exact question, and what the answer is ALLOWED to mean. excluded_uses
  -- is the load-bearing field: "D4 equals C3" can be true for mobility and
  -- reporting and false for pay and promotion, and without somewhere to say so
  -- an internal convention quietly becomes an organisational fact — the exact
  -- failure the spine's refusal exists to prevent.
  question                text not null,
  permitted_uses          text[] not null default '{}',
  excluded_uses           text[] not null default '{}',

  -- What this product proposed, kept as it was. Not recomputed, ever.
  system_proposed         text,
  engine_version          text,
  library_revision_id     uuid references library_revisions(id),

  options                 jsonb not null default '[]'::jsonb,
  chosen                  text,
  rationale               jsonb not null default '{}'::jsonb,

  -- Always CONVENTIE. A determination is a convention by definition; this is
  -- the marker the country packs reserved for exactly this and never wrote.
  hardness                text not null default 'CONVENTIE'
                            check (hardness = 'CONVENTIE'),

  state                   text not null default 'decided'
                            check (state in ('draft', 'in_consultation', 'decided',
                                             'activated', 'superseded', 'withdrawn')),
  effective_from          date not null default current_date,
  review_due              date,
  review_trigger          text,
  supersedes_id           uuid references employer_determination(id),

  created_at              timestamptz not null default now(),
  created_by              text,

  constraint det_dates_ordered
    check (review_due is null or review_due >= effective_from)
);

create index if not exists det_org_type_idx on employer_determination (org_id, determination_type);
create index if not exists det_org_state_idx on employer_determination (org_id, state);

-- ══════════════════════════════════════════════════════════════════════════
-- 2. Evidence, snapshotted
-- ══════════════════════════════════════════════════════════════════════════
--
-- A live URL does not prove in 2028 what a page said in 2026. `content_hash`
-- and `excerpt` are what turn a citation into a record.
--
-- Deliberately NOT collapsed into one confidence score: a statutory source with
-- poor employee data and a weak source with clean data are different problems
-- needing different remedies, and a single number hides which one you have.

create table if not exists determination_evidence (
  id               uuid primary key default gen_random_uuid(),
  determination_id uuid not null references employer_determination(id) on delete cascade,
  kind             text not null,
  reference        text not null,
  hardness         text,
  source_url       text,
  retrieved_at     timestamptz,
  excerpt          text,
  content_hash     text,
  created_at       timestamptz not null default now()
);

create index if not exists det_evidence_idx on determination_evidence (determination_id);

-- ══════════════════════════════════════════════════════════════════════════
-- 3. Participants — one row per ACT, not per person
-- ══════════════════════════════════════════════════════════════════════════
--
-- Consulted, advised, agreed and decided are four different acts. Flattening
-- them into "approved by" destroys the one thing a works council will actually
-- want to see, and a recorded DISAGREEMENT is evidence the process was real.
--
-- An adviser row records that advice was obtained, from whom, and whether it
-- was followed. It must never render as "legally reviewed" or "compliant".

create table if not exists determination_participant (
  id               uuid primary key default gen_random_uuid(),
  determination_id uuid not null references employer_determination(id) on delete cascade,
  person           text not null,
  role_at_the_time text,
  capacity         text,
  action           text not null
                     check (action in ('reviewed', 'advised', 'agreed',
                                       'disagreed', 'decided', 'activated')),
  acted_at         timestamptz not null default now(),
  comment          text,
  conditions       text
);

create index if not exists det_participant_idx on determination_participant (determination_id);

-- ══════════════════════════════════════════════════════════════════════════
-- 4. RLS and audit — the same as every sibling, not a lighter version
-- ══════════════════════════════════════════════════════════════════════════
--
-- The child tables have no org_id of their own; they inherit the parent's
-- tenancy through the join, which is why their policies reach through it rather
-- than repeating a column that could drift out of step with the parent.

alter table employer_determination   enable row level security;
alter table determination_evidence   enable row level security;
alter table determination_participant enable row level security;

do $$
begin
  execute 'drop policy if exists employer_determination_read on employer_determination';
  execute $p$create policy employer_determination_read on employer_determination
             for select using (app.can_read_org(org_id))$p$;
  execute 'drop policy if exists employer_determination_write on employer_determination';
  execute $p$create policy employer_determination_write on employer_determination
             for all using (app.can_write_org(org_id))
             with check (app.can_write_org(org_id))$p$;

  execute 'drop policy if exists determination_evidence_read on determination_evidence';
  execute $p$create policy determination_evidence_read on determination_evidence
             for select using (exists (select 1 from employer_determination d
                                        where d.id = determination_id
                                          and app.can_read_org(d.org_id)))$p$;
  execute 'drop policy if exists determination_evidence_write on determination_evidence';
  execute $p$create policy determination_evidence_write on determination_evidence
             for all using (exists (select 1 from employer_determination d
                                     where d.id = determination_id
                                       and app.can_write_org(d.org_id)))
             with check (exists (select 1 from employer_determination d
                                  where d.id = determination_id
                                    and app.can_write_org(d.org_id)))$p$;

  execute 'drop policy if exists determination_participant_read on determination_participant';
  execute $p$create policy determination_participant_read on determination_participant
             for select using (exists (select 1 from employer_determination d
                                        where d.id = determination_id
                                          and app.can_read_org(d.org_id)))$p$;
  execute 'drop policy if exists determination_participant_write on determination_participant';
  execute $p$create policy determination_participant_write on determination_participant
             for all using (exists (select 1 from employer_determination d
                                     where d.id = determination_id
                                       and app.can_write_org(d.org_id)))
             with check (exists (select 1 from employer_determination d
                                  where d.id = determination_id
                                    and app.can_write_org(d.org_id)))$p$;
end $$;

grant select, insert, update, delete on employer_determination    to authenticated;
grant select, insert, update, delete on determination_evidence    to authenticated;
grant select, insert, update, delete on determination_participant to authenticated;

comment on table employer_determination is
  'A decision this product refused to make for the client, recorded as theirs. '
  'Append-only: superseded via supersedes_id, never edited, because a dossier '
  'must show what the system presented WHEN the employer decided rather than '
  'what today''s engine would say. hardness is always CONVENTIE — the marker the '
  'country packs reserved for an employer''s own equivalence and never wrote. '
  'See docs/employer-determinations.md.';

comment on column employer_determination.excluded_uses is
  'What this answer may NOT be used for, and the reason the table earns its '
  'keep. An equivalence can be true for mobility and reporting and false for '
  'pay and promotion; with nowhere to say so, an internal convention silently '
  'becomes an organisational fact.';

comment on column employer_determination.population_at_decision is
  'A COUNT, never a set of people. Lets the determination outlive the roster it '
  'was made about — which Art. 18''s reversed burden of proof requires — without '
  'holding personal data it no longer needs.';

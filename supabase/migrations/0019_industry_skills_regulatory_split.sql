-- 0019 — industry_skills was doing two jobs
--
-- Applied 2026-09-06 against qpprcmmdeqlbursogosu.
--
-- docs/country-data-tiers.md §3 classified industry_skills as universal: "the
-- list is universal; only its pricing moves". That was a fair reading of the
-- table AS MEASURED, when it held nothing but the fourteen NL seed rows. The
-- four foreign packs falsified it on arrival.
--
-- Nine of those fourteen cite Dutch law or a Dutch collective agreement — Wwft,
-- AFM/DNB, NZa & Wkkgz, CAO Metalektro, HSE/VCA, CAO Rijk, Aanbestedingswet,
-- CAO Ziekenhuizen, CAO Beroepsgoederenvervoer. Five do not: Agile at scale,
-- equity & ESOP literacy, omnichannel operations, utilisation & billability,
-- WMS/TMS systems. The first nine are national by construction; the last five
-- are practice and travel fine.
--
-- With BE/DE/ES/FR imported, a query for IND-FIN returned Wwft, Witwaswet, GwG,
-- Ley 10/2010 and LCB-FT together, under whichever flag the session was flying.
-- That is the failure 0012 named: wrong pay data renders exactly like right pay
-- data, and nothing on the screen distinguishes them.
--
-- A country column was tried first, in migration industry_skills_add_country,
-- and was the wrong instrument — it would have made every universal row carry a
-- country it does not have. This migration reverts that and splits instead: the
-- same answer 0016 gave for job_profiles (§4.1) and seniority_levels (§4.3),
-- because it is the same question. What a sector typically NEEDS is universal.
-- What it is legally REQUIRED to know is the country.
--
-- The cut validates itself: before it NL had 14 rows against 9 per foreign
-- market; after it every market has exactly 9, and the universal table holds
-- the 5 that were never national. The asymmetry WAS the mixture.

-- 1. undo the widening
alter table public.industry_skills
  drop constraint if exists industry_skills_country_known;
alter table public.industry_skills
  drop column if exists country;

-- 2. the country-conditioned half, shaped like its siblings
create table public.industry_regulatory_skills (
  industry_id     text not null,
  skill_id        text not null,
  skill_name      text,
  category        text,
  definition      text,
  default_level   integer,
  id              uuid not null default gen_random_uuid(),
  org_id          uuid not null,
  revision_id     uuid,
  status          text not null default 'active',
  owner           text,
  source          text,
  effective_from  date,
  effective_to    date,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  updated_by      text,
  country         text not null default 'NL',
  constraint industry_regulatory_skills_pkey primary key (id),
  constraint industry_regulatory_skills_org_ctry_ind_skill_key
    unique (org_id, country, industry_id, skill_id),
  constraint industry_regulatory_skills_status_valid
    check (status = any (array['active','draft','retired'])),
  constraint industry_regulatory_skills_effective_ordered
    check (effective_to is null or effective_from is null
           or effective_from <= effective_to),
  constraint industry_regulatory_skills_level_range
    check (default_level is null or (default_level >= 1 and default_level <= 5)),
  constraint industry_regulatory_skills_org_id_fkey
    foreign key (org_id) references public.orgs(id) on delete cascade,
  constraint industry_regulatory_skills_revision_id_fkey
    foreign key (revision_id) references public.library_revisions(id),
  constraint industry_regulatory_skills_industry_fk
    foreign key (org_id, industry_id)
    references public.industries(org_id, industry_id) on delete cascade,
  constraint industry_regulatory_skills_country_known
    foreign key (country) references public.countries(code)
);

-- 3. move the national rows. The packs (SK-IND-XX-nn) are national by
--    construction; the nine named NL rows are national because of what they
--    cite. Listed by id rather than matched on text: a skill_name is prose and
--    a LIKE over prose is how the wrong row moves.
insert into public.industry_regulatory_skills (
  industry_id, skill_id, skill_name, category, definition, default_level,
  org_id, revision_id, status, owner, source, effective_from, effective_to,
  created_at, updated_at, updated_by, country)
select industry_id, skill_id, skill_name, category, definition, default_level,
       org_id, revision_id, status, owner, source, effective_from, effective_to,
       created_at, updated_at, updated_by,
       coalesce(substring(skill_id from '^SK-IND-([A-Z]{2})-'), 'NL')
from public.industry_skills
where skill_id ~ '^SK-IND-[A-Z]{2}-'
   or skill_id in ('SK-IND-01','SK-IND-02','SK-IND-03','SK-IND-04','SK-IND-07',
                   'SK-IND-08','SK-IND-09','SK-IND-10','SK-IND-14');

delete from public.industry_skills
where skill_id ~ '^SK-IND-[A-Z]{2}-'
   or skill_id in ('SK-IND-01','SK-IND-02','SK-IND-03','SK-IND-04','SK-IND-07',
                   'SK-IND-08','SK-IND-09','SK-IND-10','SK-IND-14');

-- 4. RLS, matching industry_skills exactly. A new table without this is either
--    open to the anon key or invisible to the app, and both are silent.
alter table public.industry_regulatory_skills enable row level security;

create policy industry_regulatory_skills_read
  on public.industry_regulatory_skills
  for select to authenticated
  using (app.can_read_org(org_id));

create policy industry_regulatory_skills_write
  on public.industry_regulatory_skills
  for all to authenticated
  using (app.can_write_org(org_id))
  with check (app.can_write_org(org_id));

comment on table public.industry_regulatory_skills is
  'COUNTRY-CONDITIONED. What a sector is legally required to know. Split out of '
  'industry_skills on 2026-09-06, same answer as 4.1 and 4.3: the table was '
  'doing two jobs. Wwft is Dutch, GwG is German, PC 111/209 is Belgian; none of '
  'them travels, and a query returning all five under one flag is the failure '
  'mode 0012 named. Resolves country, never another market''s rows.';

comment on table public.industry_skills is
  'UNIVERSAL, and now actually so. Sector-typical practice: Agile at scale, '
  'omnichannel operations, utilisation management, WMS/TMS, equity literacy. '
  'The regulatory half moved to industry_regulatory_skills on 2026-09-06. Do not '
  'add a country column here -- if a row needs one it is not a practice, it is a '
  'legal requirement, and it belongs in the other table.';

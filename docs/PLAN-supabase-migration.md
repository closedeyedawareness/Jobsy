# Implementation Plan — Reference Library: Excel → Supabase

**Roadmap item:** Phase 0.1 + 0.2 (governed DB as master, record-level provenance).
**Goal:** Make the reference library a governed, versioned, auditable database — the real
single source of truth — **without rewriting the app.**
Status: **W1 done — schema applied and verified** · Effort: ~3–4 weeks · Owner: Eng

**Supabase project `Jobsy` — ref `qpprcmmdeqlbursogosu`** (eu-central-1, org `nubdeiwupcofidifrbfn`,
alongside `Solstice-Player` and `Research Agent`). $10/month. Created 2026-07-27.
`0001_reference_library.sql` applied cleanly on first run: 23 tables, RLS on all 23.

Verified by writing bad data and watching it bounce, not by reading the DDL back:

| Attempted write | Result |
|---|---|
| Duplicate JobID | rejected (unique) |
| Salary min > max | rejected (check) |
| Title mapping → non-existent job | rejected (foreign key) |
| p25 > p50 | rejected (check) |
| Competency level 9 (scale is 1–5) | rejected (check) |
| `status = 'wobbly'` | rejected (check) |
| A legitimate row | accepted — the constraints are not over-tight |
| An UPDATE | audit row captured `Data Engineer -> Senior Data Engineer` |

Reference tables are empty and ready for the W2 importer. The audit trail keeps the ten test
writes as its first entries — emptying it would be the one thing this schema exists to prevent.

---

## 0. Checked against the code, 2026-07-27

Four corrections from verifying this plan's assumptions before building W1:

- **20 tables, not 16.** `SHEET_MAP` in `core/catalog.py` is the authoritative list of what the
  app consumes: 20 sheets, of 27 in the workbook. The 7 it never reads — CareerBands,
  LevelCriteria, PayElements, PayMix, SalarySources, BenefitsSources, DataDictionary — are
  deliberately not tabled in `0001`, because a table the loader never produces a frame for is a
  table that silently rots. They need their own decision, not a default.
- **The provenance block already exists, in Excel.** Every reference sheet carries `Owner`,
  `Status`, `EffectiveFrom`, `Source` and `UpdatedAt`, populated for essentially every row.
  §3's provenance columns are not new governance — they are somebody's hand-kept trail, and
  `0001` adopts the names 1:1 so the importer is a straight mapping and nothing recorded is lost.
- **`Employees` is customer data, not reference data.** It is the one sheet with no governance
  columns and zero rows. It stays in the schema because `SHEET_MAP` loads it, but it is the
  table that will hold personal data and therefore the one where RLS stops being theoretical.
- **Confirmed: no Jobsy Supabase project exists** (only `Solstice-Player` and `Research Agent`).
  A new project on this org costs **$10/month** — W1 step 1 is a spend decision, not a task.

**One design change from §3.** The plan's provenance block implies versioned rows. `0001` keeps
**one row per natural key**, with history in an append-only `library_audit` table written by
trigger, because a foreign key requires a full unique constraint on its target and duplicate
historical rows make one impossible — costing exactly the referential integrity §3 exists to
gain. Snapshot versioning is `library_revisions`.

**Not yet verified: the SQL has never been executed.** There is no local Postgres or Docker on
this machine and no project to apply it to, so `0001` is reviewed and structurally checked but
unrun. First application is the real test.

---

## 1. The one insight that makes this cheap

`Catalog.load()` reads every sheet of `jobsy_reference_library.xlsx` into a
**`dict[str → pandas.DataFrame]`** (keys: `jobs`, `profiles`, `salary`, `titles`, …) and passes
it to `Repository(data, validate=True)`. Everything downstream — `Repository`, `SearchIndex`,
`MatchingService`, `ExportService`, `ArchitectureReportService`, and all 8 Streamlit pages —
only ever sees that dict and the typed objects built from it.

> **So the migration is a loader swap, not a rewrite.** If we produce the *same* dict of
> DataFrames from Postgres instead of from Excel, nothing downstream changes. The `Catalog`
> and `Repository` public surfaces (11 + `find_job`/`statistics` methods) stay byte-for-byte
> compatible.

This is the seam we build against. It de-risks the entire effort: no touch to `ui/app.py`.

```
        BEFORE                              AFTER
  xlsx ─► pandas.read_excel ─┐       Postgres ─► DBLoader ─┐
                             ▼                             ▼
                    dict[str→DataFrame] ──► Repository ──► (unchanged app)
                             ▲
                    xlsx read kept as import/export + offline fallback
```

## 2. Scope

**In scope**
- Provision a Supabase project for Jobsy (none exists today — only `Solstice-Player` and
  `Research Agent` are present).
- A relational schema mirroring the 16 sheets / `core/models.py`, plus provenance metadata.
- A one-time importer: existing workbook → Postgres.
- A DB-backed loader that returns the same `dict[str → DataFrame]` the Repository already expects.
- Feature-flagged cutover with Excel retained as import/export + offline fallback.
- Parity tests proving DB-loaded catalog == Excel-loaded catalog.

**Out of scope (later roadmap items)**
- Auth / RLS / multi-tenant isolation (Phase 0.3) — the schema is *designed* for it here, but
  enforcement lands with auth.
- In-app editing UI for the library (Phase 0.4 / 3.4). This plan makes the DB authoritative;
  editing initially happens via the importer + SQL, then graduates to a UI.
- AI matching, salary service, connectors (Phases 1–2).

## 3. Target schema

One table per entity, mirroring `core/models.py`. Types match the dataclasses; column names
mirror the workbook so the loader stays alias-simple. Every table carries a **provenance block**
(Phase 0.2).

Shared provenance columns on every reference table:
```sql
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null,               -- reserved for Phase 0.3 RLS; single default org for now
  status        text not null default 'active',   -- active | draft | retired
  source        text,                        -- 'import:vX.xlsx' | 'workday' | 'manual'
  effective_from date,
  effective_to   date,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  updated_by    text
```

Representative core tables (DDL sketch — full set ships in `SUPABASE_SETUP.sql`):
```sql
create table jobs (
  job_id         text not null,
  standard_title text not null,
  function       text not null,
  level          text not null,
  <provenance>,
  unique (org_id, job_id)          -- enforces the "duplicate JobID" check the Validator does today
);

create table salary_bands (
  function text not null, level text not null,
  min numeric, max numeric, currency text default 'EUR',
  <provenance>,
  check (min <= max)               -- enforces the min>max warning as a hard constraint
);

create table title_mapping (
  existing_title text not null,
  job_id text not null references jobs(job_id),   -- FK kills dangling refs the Validator only warns about
  <provenance>
);
-- + job_profiles, career_paths, levels, employees, categories, skills,
--   competency_levels, role_skill_map, job_grades, industries,
--   industry_salary_factors, industry_skills, seniority_levels
```

**Payoff:** three data-quality checks that `core/validator.py` performs at load time (unique
JobID, salary min≤max, no dangling title→job refs) become **database constraints** — enforced
at write time, so bad data can't enter the source of truth in the first place.

Delivered as versioned migrations via `mcp__Supabase__apply_migration` (and committed to
`SUPABASE_SETUP.sql`, which is currently referenced by code but missing from the repo).

## 4. Workstreams (sequenced)

### W1 — Provision + schema (2–3 days)
1. Create the Jobsy Supabase project (or select an existing org project); record `project_id`.
2. Author migration `0001_reference_library.sql`: all 16 tables + provenance + constraints +
   indexes on `(org_id, job_id)`, `title_mapping.existing_title`, `salary_bands(function,level)`.
3. Commit the same DDL to `SUPABASE_SETUP.sql` (closes the missing-file gap) and to
   `supabase/migrations/`.
4. Generate types with `mcp__Supabase__generate_typescript_types` for reference (optional).

### W2 — One-time importer (2–3 days)
- New `services/library_import_service.py`. Reuse `Catalog`'s existing Excel read to get the
  `dict[str → DataFrame]`, then bulk-upsert each frame into its table, stamping
  `source='import:<filename>'` and `updated_by='importer'`.
- Idempotent: upsert on natural keys so re-running is safe.
- Emit a summary (rows per table, rejects) and run `core/validator.py` on the frames *before*
  insert so a bad workbook never reaches the DB.
- CLI entry (`python -m services.library_import_service path/to.xlsx`) for repeatable seeding.

### W3 — DB-backed loader (3–4 days)  ← the core change
- New `core/db_loader.py` exposing `load_frames(client, org_id) -> dict[str → DataFrame]`.
  For each table, `select *` → `pandas.DataFrame`, rename columns to the workbook names the
  Repository expects, filter `status='active'` and effective-dated rows. Returns the **exact
  dict shape** `SHEET_MAP` produces today.
- Extend `Catalog` with a source strategy (constructor arg / `config.py` flag), keeping the
  public API identical:
  ```python
  Catalog(source="db")      # new: pulls via db_loader, reuses persistence client
  Catalog(source="excel")   # existing behaviour, unchanged (default until cutover)
  ```
  `Catalog.load()` branches on source, then builds `Repository(data, validate=True)` exactly as
  now. **No other file changes.**
- Reuse the Supabase client factory already in `services/persistence_service.py`
  (`_get_client()`), so secrets handling and connection logic aren't duplicated.

### W4 — Config, secrets, fallback (1–2 days)
- `core/config.py`: `LIBRARY_SOURCE = "excel" | "db"` (default `excel`; flip at cutover).
- Secrets: the same `SUPABASE_URL`/`SUPABASE_KEY` already read by `persistence_service`.
- **Graceful fallback:** if `source="db"` and the client is unavailable, log and fall back to the
  committed workbook so the app never hard-fails on a DB blip. Surface the active source in the
  sidebar Library panel.

### W5 — Tests & parity (2–3 days)
- **Parity test (the acceptance gate):** load the catalog from Excel and from a seeded DB;
  assert `Repository.statistics()`, job/salary/title counts, and a sample of
  `get_complete_job(...)` are identical. This proves the swap is behaviour-preserving.
- Importer test: seed → reload → round-trip equality on a fixture workbook.
- Constraint tests: duplicate JobID, min>max, dangling title ref are rejected at write.
- Keep existing `tests/` green (matching, validator, repository, search_index, export).

### W6 — Cutover & export path (1 day)
- Seed production DB via the importer from the current `jobsy_reference_library.xlsx`.
- Flip `LIBRARY_SOURCE="db"`.
- Keep a **"Export library to Excel"** action (the workbook becomes a snapshot/backup artifact,
  not the master) — reuse `ExportService` styling patterns.

## 5. Testing & validation strategy

| Layer | Check | Pass condition |
|---|---|---|
| Schema | Migration applies cleanly; constraints active | `list_tables` shows 16 tables + FKs |
| Import | Workbook → DB round-trips | Fixture in == out, zero rejects on clean data |
| Loader | DB catalog ≡ Excel catalog | Parity test: identical stats + sampled `get_complete_job` |
| Quality | Bad data rejected at write | Dup JobID / min>max / dangling ref all raise |
| Regression | Existing suite | All `tests/` pass unchanged |
| Manual | App runs on `source="db"` | All 8 pages render; a match + report export succeed |

## 6. Rollout & rollback

- **Rollout:** ship W1–W5 behind `LIBRARY_SOURCE="excel"` (no user-visible change), seed DB,
  then flip the flag in W6.
- **Rollback:** set `LIBRARY_SOURCE="excel"`. The committed workbook is untouched and remains a
  fully working master — zero-downtime revert, no data migration to undo.

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| DB shape drifts from what Repository expects | `db_loader` renames to workbook column names; parity test is the gate. |
| Connection blip breaks the app | Automatic fallback to the committed workbook (W4). |
| Bad data enters the new master | Validator runs pre-insert (W2) **and** constraints enforce at write (W3). |
| Column-name / alias mismatches | Reuse the existing alias-tolerant `_val`/`_find_col` helpers in the loader. |
| Scope creep into auth/editing | Schema is auth-ready (`org_id`) but enforcement is explicitly deferred to 0.3. |

## 8. Deliverables

- `supabase/migrations/0001_reference_library.sql` + `SUPABASE_SETUP.sql` (was missing).
- `services/library_import_service.py` (+ CLI).
- `core/db_loader.py`.
- `Catalog` source-strategy change + `config.LIBRARY_SOURCE`.
- Parity + constraint tests.
- Seeded Supabase project; flag flipped to `db`.

## 9. Acceptance criteria

1. The app runs identically with `LIBRARY_SOURCE="db"` — all 8 pages, a match, and a report export.
2. Parity test passes: DB-loaded catalog == Excel-loaded catalog.
3. Duplicate JobID, salary min>max, and dangling title→job references are **rejected at write**.
4. Every reference row has provenance (`source`, `updated_at`, `updated_by`).
5. Rollback to Excel is a one-line flag change.

---

*This plan delivers Phase 0's keystone: the truth moves into a governed, constrained, auditable
database while the working app stays exactly as it is. It unblocks auth/RLS (0.3), the
data-quality scorecard (0.4), and everything downstream in the roadmap.*

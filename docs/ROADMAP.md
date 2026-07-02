# Jobsy — Tool Quality Roadmap

**From a job-title matcher to the single source of truth for job architecture.**

Status: Proposed · Owner: Product/Eng · Last updated: 2026-07-02 · Horizon: ~4 quarters

---

## 1. North Star

> Jobsy becomes the **one place business users trust** for everything about roles in the
> organisation — the canonical role, its profile, its pay band, its skills, its grade, its
> career paths — with data that is **current, governed, and explainable**, capabilities that
> **answer real HR/comp questions**, and an experience that a non-technical business user can
> **self-serve** end to end.

Three quality dimensions, one goal:

| Pillar | Question it answers | "Source of truth" test |
|---|---|---|
| **Data** | Can I trust what Jobsy tells me? | Is the data current, complete, deduplicated, owned, and audit-traceable? |
| **Capability** | Can Jobsy answer the question I actually have? | Can it match, benchmark, model scenarios, and integrate with the systems I already use? |
| **Usability** | Can I do it myself without an analyst? | Can a business user get from raw titles to a defensible report unaided? |

---

## 2. Where we are today (grounded baseline)

**What exists and works:**

- **Deterministic matching pipeline** — `services/matching_service.py`: Normalize → Exact →
  Normalized → Synonym → Fuzzy (RapidFuzz), with an ordered confidence hierarchy
  (exact 100 > normalized 98 > synonym 96 > fuzzy ≤95) and a review flag at threshold 85
  (`core/config.py`). Fuzzy hits are guarded by `_seniority_mismatch`, which rejects matches
  whose seniority or function-domain keywords contradict the input — real anti-false-match logic.
- **Typed, validated reference model** — `core/repository.py` + `core/models.py` cover Jobs,
  JobProfiles, SalaryBands, TitleMapping, CareerPaths, Levels, Employees, Skills,
  CompetencyLevels, RoleSkillMap, JobGrades, Industries, IndustrySalaryFactors,
  IndustrySkills, SeniorityLevels (16 sheets, alias-tolerant column reads).
- **Load-time validation** — `core/validator.py`: two tiers (fatal errors vs. warnings),
  catching missing sheets/columns, duplicate JobIDs, salary min>max, dangling JobID references.
- **Rich analytical surface** — `ui/app.py` pages: Matching, Connect, Skills Assessment,
  Skill Gap (role gap, batch, succession planning, succession risk), 9-Box Grid,
  Architecture Report, Organisation hierarchy, Organigram.
- **Board-ready output** — `services/architecture_report_service.py` produces a formatted,
  multi-section Excel workbook with narrative recommendations.
- **One live integration** — `services/workday_connector.py` (Workday REST/OAuth) plus file upload.
- **Session persistence** — `services/persistence_service.py` shares sessions via Supabase
  (`jobsy_sessions`) using a session code.

**The structural gaps that block "source of truth" status:**

1. **The source of truth is a file in the repo.** `jobsy_reference_library.xlsx` is the master.
   No versioning of *records*, no audit trail, no concurrent editing, no ownership metadata,
   no governance. Every deploy ships the data.
2. **No identity or access control.** Sessions are shared by a guessable code; there is no
   auth, no roles, no per-organisation isolation, no audit log — table stakes for a business SSOT.
3. **Data quality is a one-shot gate, not a managed asset.** Validation runs at load; there is
   no continuous completeness/coverage scoring, no dedup beyond exact JobID, no data freshness
   or effective-dating.
4. **Salary is a stub.** `services/salary_service.py` is empty; benchmarking leans on static
   industry factors with no refresh cadence — a hard problem given EU pay-transparency pressure.
5. **AI matching is reserved but unbuilt** (`MatchType.AI` is commented out) — recall is capped
   at what fuzzy string matching can reach.
6. **No programmatic access.** Everything is UI-driven; no API means no system of record other
   tools can consume.
7. **Maintainability risk.** `ui/app.py` is a single ~152 KB module holding all 8 pages, HTML
   generation, and business logic — the highest-friction file in the repo.
8. **Broken/undelivered surface.** `services/afas_connector.py` (AFAS Profit — a key NL HRIS)
   and `SUPABASE_SETUP.sql` are both referenced by live code but **absent from the repo**, so
   one of the two advertised connectors errors out and the DB has no shipped schema. Docs are
   1–3 line stubs; tests cover the core layer but not the UI, connectors, or report services.

---

## 3. Guiding principles

- **Governed data over convenient files.** The master moves to a database; Excel becomes
  import/export, not the truth.
- **Every answer is explainable.** Match, band, and grade decisions carry provenance and a
  confidence signal a business user can defend in a meeting.
- **Human-in-the-loop, not human-replaced.** AI raises recall; people approve. A review queue,
  not silent automation.
- **Compliance is a feature, not an afterthought.** NL/EU context (EU Pay Transparency Directive)
  makes pay-gap and banding analytics a differentiator, not a nice-to-have.
- **Ship thin, ship often.** Each phase delivers standalone business value; no big-bang rewrite.

---

## 4. The roadmap

Phasing is **Now → Next → Later → Vision**. Each initiative is tagged by pillar
(🟦 Data · 🟩 Capability · 🟪 Usability) and carries a rough effort (S/M/L).

### Phase 0 — Foundation (Now, ~4–6 weeks) · *make the truth trustworthy*

| # | Initiative | Pillar | Effort |
|---|---|---|---|
| 0.1 | **Reference library → Supabase (Postgres) as the master.** Model the 16 sheets as tables; keep the workbook as a one-click import/export. Read path swaps `Catalog` from Excel to DB behind the existing facade. | 🟦 | L |
| 0.2 | **Record-level metadata**: `owner`, `source`, `updated_at`, `updated_by`, `effective_from/to`, `status` on every reference table — the backbone of provenance and freshness. | 🟦 | M |
| 0.3 | **Auth + org isolation + audit log.** SSO/email login, per-organisation row-level security in Supabase, an append-only audit trail of who changed what. Retires the shared session-code model. | 🟪 | L |
| 0.4 | **Data-quality dashboard.** Turn `Validator` from a load gate into a live scorecard: % roles with a profile, a salary band, skills, a grade, a career path; duplicate/orphan counts; freshness heatmap. | 🟦 | M |
| 0.5 | **Split `ui/app.py`.** Extract the 8 pages into modules so the rest of the roadmap ships safely. Pure refactor, no behaviour change. | 🟪 | M |
| 0.6 | **Close the broken surface.** Restore/deliver `services/afas_connector.py` and commit the `SUPABASE_SETUP.sql` schema the persistence layer already expects; add smoke tests for connectors and the report service. | 🟩🟦 | S |

**Exit criteria:** the reference library is edited and read from the database with full audit
history; a business user can see, at a glance, how complete and current the data is.

### Phase 1 — Trustworthy matching & data hygiene (Next, ~6–8 weeks)

| # | Initiative | Pillar | Effort |
|---|---|---|---|
| 1.1 | **AI semantic matching stage** (activate the reserved `MatchType.AI`). Embedding/LLM match after fuzzy to lift recall on titles string-matching misses; every AI hit shows a rationale and always routes through review. | 🟩🟦 | L |
| 1.2 | **Review queue with human approval.** A first-class "needs review" workspace: approve/reject/remap suggestions, and every approval enriches `TitleMapping` so the system compounds. | 🟪🟦 | M |
| 1.3 | **Fuzzy dedup of the library itself.** Detect near-duplicate roles/titles (not just exact JobID) and propose merges — keeps the canonical set canonical. | 🟦 | M |
| 1.4 | **Provenance surfaced in the UI.** Show, per matched role, the match type, confidence, and source record so users can defend the output. | 🟪 | S |
| 1.5 | **Effective-dated salary bands + real `salary_service`.** Fill the stub; version bands over time; support "as of" queries. | 🟦🟩 | M |

**Exit criteria:** match recall measurably up vs. fuzzy-only; nothing auto-applied without a
human; every role on screen traceable to its source.

### Phase 2 — Answering the real questions (Later, ~8–10 weeks)

| # | Initiative | Pillar | Effort |
|---|---|---|---|
| 2.1 | **Pay-equity & transparency analytics.** Compa-ratio, range penetration, gender/other pay-gap views, outliers vs. band — directly serving the **EU Pay Transparency Directive** that NL employers must meet. | 🟩 | L |
| 2.2 | **Read/write API.** REST endpoints for match, role lookup, and band lookup so downstream systems consume Jobsy as the system of record. | 🟩🟪 | L |
| 2.3 | **More connectors.** SAP SuccessFactors, and Dutch-market HR/payroll (AFAS, Nmbrs), plus a clean CSV template and Google Sheets sync — meeting business users where their data already lives. | 🟩 | M |
| 2.4 | **Scenario modelling / what-if.** Re-level a population, shift a band, re-map a function — preview cost and headcount impact before committing. | 🟩 | M |
| 2.5 | **Org-wide trend analytics.** Now that data is in a DB and time-stamped: skills coverage, 9-box drift, succession-risk trends over time. | 🟩🟦 | M |

**Exit criteria:** a comp analyst can run a pay-gap review and a re-leveling scenario in Jobsy;
another system can pull a canonical role via API.

### Phase 3 — Scale & polish (Vision, ~ongoing)

| # | Initiative | Pillar | Effort |
|---|---|---|---|
| 3.1 | **Multi-country / i18n.** Un-hardcode `COUNTRY="NL"`/EUR; per-country bands, currency, locale. | 🟩🟪 | L |
| 3.2 | **Richer output formats.** PDF reports, shareable read-only web links, scheduled/emailed reports. | 🟪 | M |
| 3.3 | **Guided onboarding & templates.** First-run wizard, starter library templates, sample-to-production path. | 🟪 | M |
| 3.4 | **RBAC granularity + approval workflows** for edits to the master library (maker/checker). | 🟪🟦 | M |
| 3.5 | **Accessibility & responsive review.** WCAG pass, mobile-friendly review flows. | 🟪 | S |

---

## 5. Quick wins (start immediately, low risk)

- **Data-quality scorecard (0.4)** — reuse `Validator`; high perceived value, low effort.
- **Provenance chips in the UI (1.4)** — surface confidence/match-type already computed by
  `MatchingService`.
- **CSV import template + validation preview (part of 2.3)** — reduces "garbage in" today.
- **Fill `salary_service.py` with the industry-factor logic already in `Catalog`** — removes a
  visible stub.
- **Ship `SUPABASE_SETUP.sql` and repair the AFAS connector** — restores a documented but
  currently broken ingestion path (0.6).

---

## 6. Success metrics

| Pillar | Metric | Baseline | Target |
|---|---|---|---|
| Data | Library completeness (roles with profile + band + skills + grade) | measure in 0.4 | ≥ 95% |
| Data | Records with owner + freshness < 12 months | ~0% (file) | ≥ 90% |
| Data | Duplicate/orphan reference records | measure in 0.4 | ≈ 0 |
| Capability | Auto-match rate at ≥85 confidence (no human touch) | fuzzy-only baseline | +15–25 pts after AI stage |
| Capability | Systems integrated (connectors + API consumers) | 1 (Workday) | ≥ 4 |
| Usability | Time for a new user: raw titles → approved report | measure | < 30 min unaided |
| Trust | Matches with visible provenance/confidence | partial | 100% |

---

## 7. Key risks & mitigations

| Risk | Mitigation |
|---|---|
| DB migration destabilises a working app | Keep `Catalog` facade; DB behind it; workbook import/export retained as fallback and escape hatch. |
| AI matching produces confident-but-wrong maps | Never auto-apply; route all AI hits through the review queue (1.2) with rationale + confidence. |
| Pay data is sensitive | Org isolation + RLS + audit log land in Phase 0 *before* pay analytics in Phase 2. |
| Scope creep across three pillars | Every phase ships standalone value; quick wins de-risk early; no big-bang rewrite. |
| Compliance targets move | Treat pay-transparency analytics as configurable rules, not hardcoded thresholds. |

---

## 8. Dependency order (why this sequence)

```
Phase 0 (governed DB + auth + audit)
        │  ── unlocks ──►  time-stamped data, per-org trust
        ▼
Phase 1 (AI match + review queue + provenance)
        │  ── unlocks ──►  trustworthy, explainable matching
        ▼
Phase 2 (pay analytics + API + connectors + scenarios)
        │  ── unlocks ──►  answering real business questions at scale
        ▼
Phase 3 (i18n + formats + onboarding + RBAC polish)
```

Data governance (Phase 0) is the gate: pay-equity analytics, scenario modelling, and an API
are only defensible once the data underneath them is governed, owned, isolated, and auditable.

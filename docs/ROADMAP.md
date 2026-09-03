# Jobsy — Tool Quality Roadmap

**From a job-title matcher to the single source of truth for job architecture.**

Status: In flight · Owner: Product/Eng · Last updated: **2026-09-03** · Horizon: ~3 quarters

> This revision is a *measured* one. The 2026-07-02 version described Phase 0 as "Now"
> months after most of it shipped, which made the document unusable for deciding what to
> do next. Every status line below was checked against the code on 2026-09-03 — the
> evidence is named next to the claim, and where the answer is "partly", it says so.

---

## 1. North Star

> Jobsy becomes the **one place business users trust** for everything about roles in the
> organisation — the canonical role, its profile, its pay band, its skills, its grade, its
> career paths — with data that is **current, governed, and explainable**, capabilities that
> **answer real HR/comp questions**, and an experience that a non-technical business user can
> **self-serve** end to end.

| Pillar | Question it answers | "Source of truth" test |
|---|---|---|
| **Data** | Can I trust what Jobsy tells me? | Is the data current, complete, deduplicated, owned, and audit-traceable? |
| **Capability** | Can Jobsy answer the question I actually have? | Can it match, benchmark, model scenarios, and integrate with the systems I already use? |
| **Usability** | Can I do it myself without an analyst? | Can a business user get from raw titles to a defensible report unaided? |

---

## 2. Where we are (measured 2026-09-03)

### Shipped since the last revision

| # | Initiative | Evidence |
|---|---|---|
| 0.1 | **Reference library → Supabase as the master** | `LIBRARY_SOURCE = "db"` since cutover `2095098`. 2,578 rows across 21 tables; `core/db_loader.py` behind the `Catalog` facade; `tests/test_library_parity.py` is the gate. Rollback is one config line. |
| 0.2 | **Record-level metadata** | `owner`, `source`, `updated_at`, `effective_from`, `status` on every reference table — the workbook's own column names, adopted 1:1. |
| 0.4 | **Data-quality dashboard** | Data Quality page: coverage per dimension, integrity counts, per-sheet freshness and provenance. Measures the *loaded* library, from whichever source. |
| 0.5 | **Split `ui/app.py`** | 5,405 lines → `ui/shared.py` + `ui/views/` (13 modules) + a 1,190-line `app.py`. Bodies verified byte-identical; all pages render under `streamlit.testing`. |
| 0.6 | **Close the broken surface** | `SUPABASE_SETUP.sql` committed; `services/afas_connector.py` written against AFAS's REST GetConnector API with 23 tests. Each connector now imports independently. |
| 1.4 | **Provenance surfaced in the UI** | Match type, confidence and the pipeline stage chips are on every matched row. |
| 1.5 | **Real `salary_service`** | `services/salary_service.py`: compa-ratio, range position, status, industry scaling, coverage accounting. *Effective dating is still open — see 1.5 below.* |
| 2.1 | **Pay-equity & transparency analytics** | `pay_equity_service` (structural gap, regression-adjusted, per-cohort 5% trigger, representation), the Art. 4 grade-assignment check, the ISF/CATS crosswalk, and a dedicated export. |
| — | **Variable-pay exposure** | PayMix/PayElements in the DB; target-variable and LTI entitlement by Function×Level in the pay-equity view. |
| — | **Library export** | Data Quality → "Export library to Excel". The workbook is a snapshot the app produces, not a second master. |

### Still open, and honestly labelled

| # | Initiative | Measured state |
|---|---|---|
| 0.3 | Auth + org isolation + audit log | **Not started.** One shared password (`_require_password`); RLS is on with no policies because there is no org claim to filter on; `service_role` bypasses it. The audit *trail* exists (`library_audit`, append-only since `d554b89`) — the *access control* does not. |
| 1.1 | AI semantic matching | **Not started.** `MatchType.AI` is still a commented-out line in `matching_service.py`. |
| 1.2 | Review queue with human approval | **Partly.** The Matching page filters to rows below the confidence threshold; there is no approve/reject workspace, and approvals do not enrich `TitleMapping`, so the system does not compound. |
| 1.3 | Fuzzy dedup of the library | **Not started.** The importer collapses byte-identical duplicates and raises on a repeated key with different values; nothing detects *near*-duplicate roles. |
| 1.5 | Effective-dated bands / "as of" queries | **Open.** `effective_from` is stored but nothing queries by date. |
| 2.2 | Read/write API | **Not started.** No HTTP surface; everything is UI-driven. |
| 2.3 | More connectors | **Partly.** Workday, AFAS Profit and file upload. No SAP SuccessFactors, no Nmbrs, no Sheets sync. |
| 2.4 | Scenario modelling | **Partly.** The pay-equity page prices a remediation scenario; there is no re-levelling or band-shift what-if. |
| 2.5 | Org-wide trend analytics | **Not started.** The data is time-stamped; nothing reads it as a series. |
| 2.6 | Unified Total Rewards centre | **Partly.** Pay and Benefits are still sibling pages sharing one snapshot tile. |
| 3.x | i18n, richer output, onboarding, RBAC, accessibility | **Not started.** `COUNTRY="NL"` is still hardcoded. |

### The structural gaps that remain

1. **No identity.** One shared password is the whole access model. Everything else in Phase 0
   landed; this did not, and it is now the single largest gap between Jobsy and a business
   system of record — pay data is already in it.
2. **Matching recall is capped at string similarity.** No semantic stage, and no loop that
   turns a human's approval into a mapping the system keeps.
3. **`Employees` is customer data in a tool with no tenancy.** The `.gitignore` blocks rosters
   from being committed; that is a guard rail, not isolation.
4. **The DB holds tables the app does not load.** `pay_mix` and `pay_elements` are read
   directly by the pay-equity page rather than through `SHEET_MAP`; five more workbook sheets
   are not tabled at all. Worth a decision, not a drift.

---

## 3. Guiding principles

- **Governed data over convenient files.** The master is the database; Excel is import/export.
- **Every answer is explainable.** Match, band, and grade decisions carry provenance and a
  confidence signal a business user can defend in a meeting.
- **Human-in-the-loop, not human-replaced.** AI raises recall; people approve.
- **Compliance is a feature.** NL/EU pay transparency makes gap and banding analytics a
  differentiator, not a nice-to-have.
- **A page states its basis.** What was compared, on which source, with whom excluded. A figure
  that does not say what it measured is not a finding.
- **Ship thin, ship often.**

---

## 4. The roadmap from here

### Phase A — Identity (Now, ~3–4 weeks) · *the last Phase 0 gate*

| # | Initiative | Pillar | Effort |
|---|---|---|---|
| A.1 | **Auth: email/SSO login, replacing the shared password.** | 🟪 | M |
| A.2 | **Org claim + RLS policies** on all 23 tables, so isolation stops depending on there being one customer. | 🟦 | L |
| A.3 | **Who-did-what audit surface** — `library_audit` already records it; nothing shows it. | 🟦🟪 | S |

**Exit:** two organisations can use the same deployment without seeing each other's data, and
every change has a name against it.

### Phase B — Matching that compounds (Next, ~6–8 weeks)

| # | Initiative | Pillar | Effort |
|---|---|---|---|
| B.1 | **Review queue with approval**, and every approval writes back to `TitleMapping`. Do this *before* the AI stage: it is the mechanism that makes AI hits safe. | 🟪🟦 | M |
| B.2 | **AI semantic matching stage** (`MatchType.AI`), every hit routed through B.1 with a rationale. | 🟩🟦 | L |
| B.3 | **Near-duplicate detection in the library itself.** | 🟦 | M |
| B.4 | **Effective-dated bands + "as of" queries.** | 🟦🟩 | M |

**Exit:** recall measurably up against the fuzzy-only baseline, nothing auto-applied, and the
library gets better every time someone uses it.

### Phase C — Reach (Later, ~8–10 weeks)

| # | Initiative | Pillar | Effort |
|---|---|---|---|
| C.1 | **Read/write API** for match, role and band lookup. | 🟩🟪 | L |
| C.2 | **More connectors** — SuccessFactors, Nmbrs, Sheets sync, a clean CSV template. | 🟩 | M |
| C.3 | **Scenario modelling** — re-level a population, shift a band, preview cost. | 🟩 | M |
| C.4 | **Trend analytics** over the time-stamped data. | 🟩🟦 | M |
| C.5 | **Unified Total Rewards centre** — one selection driving pay and benefits. | 🟩🟪 | M |

### Phase D — Scale & polish (Vision)

i18n and un-hardcoding `COUNTRY="NL"`; PDF and shareable read-only reports; guided onboarding;
maker/checker approval on library edits; a WCAG pass.

---

## 5. Quick wins available today

- **Surface the audit trail** (A.3) — the data is already being written.
- **`pay_mix` / `pay_elements` through `SHEET_MAP`** — removes the last direct table reads.
- **A CSV import template with a validation preview** — reduces "garbage in" before any
  connector work.
- **Name the sheets the app does not load** on the Data Quality page, so the 20-of-27 gap is
  visible rather than implied.

---

## 6. Success metrics

| Pillar | Metric | Baseline | Target |
|---|---|---|---|
| Data | Library completeness (roles with profile + band + skills + grade) | Data Quality page reports it live | ≥ 95% |
| Data | Records with owner + freshness < 12 months | ~100% owner; oldest content 2026-07-02 | ≥ 90% under 12 months |
| Data | Duplicate/orphan reference records | 0 orphans at import | ≈ 0 |
| Capability | Auto-match rate at ≥85 confidence | fuzzy-only baseline | +15–25 pts after B.2 |
| Capability | Systems integrated (connectors + API consumers) | 2 (Workday, AFAS — AFAS unproven against a live tenant) | ≥ 4 |
| Usability | Time for a new user: raw titles → approved report | measure | < 30 min unaided |
| Trust | Matches with visible provenance/confidence | 100% | hold |

---

## 7. Key risks & mitigations

| Risk | Mitigation |
|---|---|
| Pay data sits in a tool with no tenancy | Phase A is first for exactly this reason; rosters are already blocked from the repo. |
| AI matching produces confident-but-wrong maps | B.1 ships before B.2; nothing auto-applies. |
| A page quietly reads a source the app retired | Two did (Data Quality, Job Family) and were found by grepping for `WORKBOOK_PATH`, not by anything failing. Any new direct read of the workbook is a defect. |
| A connector written without a live environment | The AFAS module says so in its docstring and preserves unrecognised fields rather than dropping them. First live tenant is a test, not a release. |
| Scope creep across three pillars | Each phase ships standalone value. |

---

## 8. Dependency order

```
Phase A (identity + isolation)
        │  ── unlocks ──►  more than one customer, and a named change history
        ▼
Phase B (review queue → AI matching → dedup → effective dating)
        │  ── unlocks ──►  matching that compounds instead of resetting
        ▼
Phase C (API + connectors + scenarios + trends + total rewards)
        │  ── unlocks ──►  Jobsy as a system other systems consume
        ▼
Phase D (i18n + formats + onboarding + RBAC polish)
```

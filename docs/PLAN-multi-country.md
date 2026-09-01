# Implementation Plan — Multi-country Jobsy

**Status:** draft, schema only. Migration `0007_multi_country.sql` applied and verified
against a scratch Postgres 16; no second country's data ships with it.
**Owner:** Eng · **Effort:** schema done; per-country loading is the work that remains.

---

## 1. The decision this rests on

The obvious move is to put `country_code` on all twenty reference tables. That is wrong,
and expensively so: it forks the canonical job library per country, so "Financial
Controller" in the Netherlands and in Germany become two unrelated rows that drift apart,
and every cross-border question — *who does this job group-wide?* — stops being answerable.

So the library splits in two.

| Layer | Tables | Rule |
|---|---|---|
| **Global spine** — what a job *is* | `jobs`, `job_profiles`, `categories`, `industries`, `skills`, `competency_levels`, `role_skill_map`, `career_paths`, `levels`, `seniority_levels`, `skill_proficiency`, `industry_skills` | One definition, shared by every country |
| **Country layer** — what it costs, and what the law says | `salary_bands`, `job_grades`, `industry_salary_factors`, `pay_elements`, `pay_mix`, `benefits_catalog`, `benefits_observations`, `level_benefits_factors`, `title_mapping` | `country_code`, and the natural key widens to include it |

`employees` carries `country_code` as an attribute rather than a key part: someone works in
one country, but `EmployeeID` is already unique per org, and widening that key would break
a person's identity the moment they relocate.

A Financial Controller is the same work in Rotterdam and in Antwerp. Only its price and its
statutory wrapper differ. The schema now says exactly that.

## 2. Why the timing is the same argument 0001 made

Migration 0001 threaded `org_id` through every table on the grounds that *"retrofitting a
tenant key onto populated tables with live foreign keys is the kind of migration that goes
wrong"*. Country is the same shape of problem, and the tables are populated now — so 0007
does the careful version in order: add nullable → backfill `'NL'` → set not null → widen the
keys. Every existing row is Dutch, because it always was.

## 3. National classification systems

`services/cao_crosswalk_service.py` generalises into three tables — `classification_systems`,
`classification_grades`, `classification_crosswalk` — because every country has some public
structure a grade has to land in: Dutch CAO salarisgroepen, German ERA Entgeltgruppen,
Belgian IFIC functieklassen, French coefficients.

**The IP boundary is a column, not a convention.** The Dutch work established a distinction
the schema has to carry, or the first person to add a country will quietly break it:

* **ISF** (Metalektro) publishes a numeric point-**boundary** table, so a grade can be
  rank-positioned onto a published sequence — indicative, never a fabricated point score.
* **CATS** publishes **no point table at all**, only functiegroep→salarisgroep labels.
  Anything numeric shown against it would be invented.

`crosswalk_basis` is `'point_boundaries'` or `'label_alignment'`, and a trigger refuses to
store point boundaries against a `label_alignment` system. The UI therefore *cannot* render
a point range that does not exist. That was previously a property of one careful Python
module; it is now a property of the database.

## 4. What running it against a real Postgres caught

Three bugs that reading the SQL would not have found:

1. **Guessed constraint names matched nothing.** The real names are abbreviated
   (`salary_bands_org_fn_level_key`, `isf_org_ind_fn_key`, `lbf_org_level_cat_key`). A
   `drop constraint if exists` against a wrong name skips with a NOTICE and reports success
   — leaving the narrow key in force. The migration now *discovers* narrow keys (any unique
   constraint whose definition omits `country_code`) rather than naming them.
2. **A dependent foreign key blocked the drop.** `pay_mix → salary_bands(org_id, function,
   level)` had to be dropped first and recreated widened. That is also a correctness fix: a
   Dutch pay-mix row should reference the Dutch band, not merely a band with the same
   function and level.
3. **`fx_rates` has no `country_code`**, so the shared index loop failed on it. A rate is
   between two currencies, not inside a country.

Two guards were added as a result: the migration fails loudly if any dropped foreign key is
not recreated, and again if any narrow unique key survives the widening pass.

## 5. Verified, not assumed

All seven migrations applied in order to a scratch Postgres 16, then probed by behaviour:

| Check | Result |
|---|---|
| 9 countries seeded, `NL` the only active one | ✅ |
| Org default country is `NL` | ✅ |
| Global spine has no `country_code` | ✅ |
| Same function + level in two countries | accepted |
| Duplicate within one country | rejected — `salary_bands_org_country_key` |
| `label_alignment` system + point boundaries | rejected by trigger |
| `point_boundaries` system + point boundaries | accepted |
| `pay_mix` foreign key includes country | ✅ |
| Audit triggers on all four new tables | 4/4 |
| Re-running 0007 | clean; one unique key per table |
| Python suite | 214 passed, 10 skipped |

## 6. Deliberately not done

* **No second country's data.** Loading BE or DE is a sourcing exercise with its own
  verification trail, exactly as `docs/cao-metalektro-isf-reference.md` was for NL.
* **`title_mapping` is country-scoped but not language-scoped.** Belgium breaks that —
  nl-BE and fr-BE titles map to the same job in one country. It should be a `language`
  column added when BE loads, not guessed at now.
* **`pay_elements.statutory_nl` still exists.** Its country-neutral successor `statutory` is
  added and backfilled, but the old column stays until `core/models.py`,
  `core/repository.py` and `services/library_import_service.py` stop reading it. A rename
  that outruns its callers is an outage.
* **Services still read country-blind.** The picker sets `st.session_state["country_code"]`
  and the header reflects it; no service filters on it yet, because with one country loaded
  there is nothing to filter. That wiring lands with the second market.

## 7. Next

1. Thread the selected country into `db_loader` / `Catalog` as a scoping parameter.
2. Load one non-Dutch market end to end — BE is cheapest (euro, partly Dutch-language,
   IFIC is documented) and will surface the language split in `title_mapping`.
3. Drop `statutory_nl` once its three callers move.
4. `fx_rates` only earns its keep at the first non-euro market (PL, SE, GB).

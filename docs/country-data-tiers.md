# Which data is national, which is not, and which is the client's

**Status: proposal. Nothing here has been applied.** Migration `0015` writes the
part of it that is not in doubt; the rest is a set of questions for the product
owner, deliberately left open rather than settled by whoever wrote the file.

Measured against the live database on **2026-09-06**, project
`qpprcmmdeqlbursogosu`.

---

## Why this document exists

Migration `0012_country_dimension.sql` made the library able to hold two
countries and said, in a comment nobody has had to argue with since:

> Deliberately not "all of them". A country column on a table that does not vary
> by country is a column that will drift, get half-populated, and then be
> believed.

That is still the rule. This document does not soften it. What it does is
finish the sentence, because 0012 drew the line for the tables that hold *money*
and left the rest of the schema to be sorted out later — and "later" is now,
with seven markets on the roadmap and the packs at `services/country_packs/`
already holding what those markets require.

The packs are ahead of the schema. `be.py` states that Belgian double holiday
pay is **92% of one month's gross**, not 8% of the year; `de.py` states that
holiday pay in Germany **is not statutory at all** and comes from the
Tarifvertrag. The database answers that question with a single column called
`statutory_nl`, on a table with no country dimension, holding the string
`Yes (statutory min 8%)`. The knowledge layer knows three answers and the
storage layer can hold one.

The failure mode is the one 0012 named and `country_service.py` repeats: **wrong
pay data renders exactly like right pay data.** Nothing on a screen
distinguishes a Belgian band from a Dutch band shown under a Belgian flag. So
the question is not really "which tables should get a column" — it is "which
tables can be *asked* the country question and give an answer somebody could
defend", and the honest answer for several of them is *we do not know yet*.
Those are listed in §4 rather than resolved.

---

## 1. What is actually in the database today

Thirty base tables. Twenty-two carry library or reference data; eight are
platform plumbing (`orgs`, `partners`, `memberships`, `jobsy_sessions`,
`activity_log`, `library_audit`, `library_revisions`, `countries`) and are out of
scope here — they describe tenants and history, not markets.

Of the twenty-two, **eight carry a `country` column and every single row in all
eight reads `NL`**:

| table | rows | distinct countries |
|---|---:|---|
| `benefits_observations` | 1 008 | NL only |
| `title_mapping` | 325 | NL only |
| `industry_salary_factors` | 112 | NL only |
| `salary_bands` | 45 | NL only |
| `pay_mix` | 45 | NL only |
| `level_benefits_factors` | 36 | NL only |
| `job_grades` | 14 | NL only |
| `employees` | 0 | — (nullable by design; see 0012) |

The dimension exists and has never been exercised. That matters for §5: a
mechanism that has only ever been run with one value has not been tested, it has
been *unused*, and the two look identical until the second value arrives.

### Two things the measurement turned up that were not in the brief

**`benefits_catalog` also has a `statutory_nl` column.** The brief named
`pay_elements`. There are two of them, and they have the same problem for the
same reason. `core/models.py` reads both through the same shape — a
`statutory_nl` string parsed by `is_statutory`, which returns true only on a
leading `Yes`, precisely because `Partly (sector funds)` is not a statutory
obligation and must not be reported as one. That careful parsing is national law
being read out of a column whose name asserts the nationality and whose table
cannot record it.

**Migration 0012 added `country` to `level_benefits_factors` but never widened
its unique constraint.** The column, the foreign key and the `(org_id, country)`
index all landed; the unique is still `UNIQUE (org_id, level, category)` — the
pre-0012 one. 0012 widened five uniques (`salary_bands`, `job_grades`,
`title_mapping`, `industry_salary_factors`, `pay_mix`) and this table was not on
that list. So today:

```
insert into level_benefits_factors (org_id, country, level, category, factor)
values (:org, 'BE', 'Senior', 'Pension', 1.1);   -- rejected if the NL row exists
```

The table has a country column it **cannot populate with a second country**.
That is exactly the condition 0012 was written to remove, surviving inside 0012
itself, and it is the one thing in this proposal that is a defect rather than a
design question. `benefits_observations` is fine by accident: its unique is on
the surrogate `obs_id`, so country varies freely underneath it.

---

## 2. The three tiers

**UNIVERSAL.** The same everywhere, and asking the country question would force a
choice where no difference exists. A skill is a skill. Negotiation does not
change at a border, and neither does the fact that a Data Analyst analyses data.
The test is not "could a country conceivably differ here" — nearly anything
could — it is *would a national answer carry information a reader could act on*.
If the honest per-country value would be a copy of the EU row seven times over,
the column is a place for drift to live.

**COUNTRY-CONDITIONED.** Money, or a national institution. A grade, a band, a
statutory pay element, a leave entitlement, a benefit value, a local-language
title. These resolve country → `EU` → nothing, `EU` being a real row somebody
wrote and not a NULL.

**CLIENT-SPECIFIC.** The customer's own architecture and their own people. Scoped
by `org_id`, and where a country matters it is a fact about the *row* — where
this person is paid — not about the table.

The tiers are not exclusive in the way the names suggest. `employees` is
client-specific *and* carries a per-row country. `pay_elements` is
country-conditioned in its values and universal in its vocabulary. Where a table
sits in two tiers at once, that is said below rather than rounded away.

---

## 3. The classification

### Country-conditioned — already has the column

| table | why |
|---|---|
| `salary_bands` | Pay figures. The original case. |
| `job_grades` | A grade carries `pay_min`…`pay_max` and a Hay range; both are national. |
| `pay_mix` | A cohort's variable-pay entitlement, and FK-bound to `salary_bands`. |
| `industry_salary_factors` | Sector premia differ by market — a Dutch logistics premium is not a Polish one. |
| `benefits_observations` | Market benefit values, in a currency. `benefits_service` already resolves these country → EU → nothing, correctly. |
| `level_benefits_factors` | Same family. **Constraint not widened — see §1 and migration 0015 step 1.** |
| `title_mapping` | Local-language titles. See the caveat in §4.6. |
| `employees` | Per-row, nullable, and NULL means *unknown* rather than *the default* — 0012 is explicit that guessing it silently is how a country-mix artefact becomes a reported gap. |

### Country-conditioned — should have it, does not

| table | why | confident? |
|---|---|---|
| `pay_elements` | Holds `statutory_nl` and a `typical_value` of `8%`. The Belgian answer is 92% of one month; the German answer is *not statutory*. The row as stored is a Dutch row wearing no label. | **Yes** — migration 0015 step 2. The *shape* is arguable (§4.5); that the table is country-conditioned is not. |
| `benefits_catalog` | Same `statutory_nl` column, same argument. Whether a pension is statutory is a national fact. | **Yes** — step 3. |

### Universal

| table | why |
|---|---|
| `jobs` | 0012 already said it: a Data Analyst is a Data Analyst. The job *exists* identically; what it is paid does not, and that is `salary_bands`' problem. |
| `skills` | The strongest case in the schema. A skill definition is a description of a human capability. |
| `skill_proficiency` | The anchors that describe what level 3 of a category looks like. Behavioural, not legal. |
| `role_skill_map` | Which skills a role needs. Caveat in §4.7 about regulated professions. |
| `industry_skills` | Sector-typical skills. The *list* is universal; only its pricing moves, and pricing lives in `industry_salary_factors`. |
| `levels` | Junior/Medior/Senior/Lead. The product's own four-rung scale. |
| `categories` | The function taxonomy. |
| `industries` | 0012's reasoning verbatim: the sector list is universal, only its factors move. |

`career_paths` was in this list in an earlier draft and has been moved to §4.4.
The test in `tests/test_country_tiers.py` is what caught the inconsistency: the
prose called it universal and §4.4 called it arguable, and both cannot be true.
It is arguable.

### Client-specific

`orgs` (already carries `default_country`, which is the client's *home* market
and deliberately not the same thing as any employee's country), `employees`,
`memberships`, `partners`, and the audit and revision tables. No country
dimension belongs on the table; where it belongs on a row it is already there.

---

## 4. The arguable ones — ANSWERED 6 September 2026

Each of these had a defensible answer in both directions. None was in migration
0015, which recorded them as open on the objects themselves. **0016 carries the
answers**, and the table comments now state them rather than the questions.

| §   | Question | Answer |
|-----|----------|--------|
| 4.1 | Job profiles | **(c) split** — content universal, positioning country-scoped |
| 4.2 | Competency levels | **the product's own five stay** — and the question was wrongly put |
| 4.3 | Seniority levels | **same shape as 4.1**, because it is the same question |
| 4.4 | Career paths | **not a question** — the national licence gate is simply real |
| 4.5 | `pay_elements` | additive column taken in 0015; the rates split remains declinable |

One thing to notice about how 4.2 went, because it generalises: the answer came
back "EQF", and then reading the five actual rows showed the QUESTION had been
wrong. It had been framed as five rungs against eight — one axis at two
resolutions, where the only cost is a lossy inverse. The rows say otherwise.
They describe how well somebody performs a skill; the EQF describes the learning
outcomes of a qualification. A question that hides a category difference inside
a granularity difference will get a confident answer to the wrong thing, and the
answer will look fine.

### 4.1 Job profiles — ANSWERED: (c), split

`job_profiles` holds a description, key responsibilities, required skills,
specialisms, a management level and typical tools, keyed one-to-one against
`jobs`. The content half looks universal: what a Financial Controller *does* is
not a Dutch fact.

But `management_level` is a positioning claim, and positioning is exactly what
the packs say is national. `nl.py` records that the Dutch unit of grading is the
**functiegroep**, a collective-agreement construct set per CAO; `de.py` and
`fr.py` name different instruments again. A profile that says "management level:
Lead" is asserting a rung in a structure that is not the same structure across
the border.

Three options, and the choice is a product decision:

- **(a)** universal throughout — one profile, and level positioning is inferred
  from `job_grades`, which is already national;
- **(b)** country-conditioned throughout — a full profile per market, seven
  copies of a description that will drift apart for no reason;
- **(c)** split — the descriptive fields stay universal, `management_level`
  moves to a small country-scoped table keyed `(country, job_id)`.

(c) is the one that matches the tier logic, and it is the one taken. It costs a
table and a join. Built in 0016 as `job_profile_positioning`, keyed
`(org_id, country, job_id)`, with `job_profiles.management_level` still live and
still read until the five conditions in 0016 §3 hold.

### 4.2 Competency levels — ANSWERED: the product's own, and the question was wrong

`competency_levels` holds five rows. The packs already carry a real anchor:
`eu.py` describes **EQF**, eight levels, with the observation that every member
state has *referenced* its national framework to it — "a declared correspondence
rather than an equivalence anyone can appeal", which `eu.py` calls exactly the
right strength for a spine. `nl.py` carries NLQF, statutory since January 2025,
mapping 1:1 to EQF.

Anchoring the product's five levels to EQF's eight would make cross-border
comparison defensible against a public standard instead of against a Jobsy
invention. But `nl.py` also documents, in the same breath, why this is not free:
NLQF → EQF is a function and **EQF → NLQF is not**, because EQF level 4 has two
Dutch pre-images (4 and 4+) and the Instroomniveau maps to nothing. A round trip
through the spine does not return where it started, and *"any bridge that treats
this as reversible will quietly promote or demote people at level 4."*

So the question is not "is EQF better". It is: does the product want to own a
five-level scale it controls, or route through an eight-level public one and
accept a lossy inverse it must never traverse?

**AND THAT FRAMING WAS ITSELF WRONG.** It presents the two as one axis at two
resolutions, where the only cost is the inverse. The five rows say otherwise —
"applies the skill with support in straightforward situations", "coaches
others", "recognised authority". That is how well somebody PERFORMS a skill. The
EQF describes the learning outcomes of a QUALIFICATION: what a diploma attests
to in knowledge, skills, responsibility and autonomy. Two axes.

**The answer is that the five stay.** They work, and they measure something the
EQF does not. The consequence is now on the table itself: a proficiency rating
here is not a qualification level and must never be rendered as one — anchoring
it to an EQF number would put a credential claim on a performance rating.

Where the EQF anchor DOES belong is the qualification axis, which the packs
already hold and `bridge()` already routes. That is a separate build and nobody
has asked for it.

### 4.3 Seniority levels — ANSWERED: split, same shape as 4.1

The brief flagged this and the measurement bears it out. `seniority_levels` has
no country column; `job_grades` does. And the join between them is stated in the
data:

```
L1  Starter     → Junior   grade_range "1-3"
L2  Developing  → Medior   grade_range "4-6"
L3  Senior      → Senior   grade_range "7-10"
L4  Manager     → Lead     grade_range "11-14"
L5  Rising Star → (designation)  "any"
```

`grade_range` points into a fourteen-row grade set that is keyed
`(org_id, country, grade)`. So the mapping "L3 covers grades 7-10" is a statement
about a *national* grade ladder, held in a table with no country. If a Belgian
grade ladder is imported with a different number of grades — and there is no
reason it would have fourteen — then `grade_range "7-10"` means something else
there, or nothing.

The counter-argument is real: L1..L5 and "Starter/Developing/Senior/Manager" are
the product's own naming, not any country's, and duplicating five rows per market
to change one text field is the drift 0012 warned about.

The resolution splits the table — the rung names stay universal, the
`grade_range`/`maps_to_level` binding becomes country-conditioned — which is the
same shape as 4.1(c). **Migrated in 0016** as `seniority_grade_binding`, keyed
`(org_id, country, l_code)`, once 4.1 was answered, because it is the same
question and answering it twice would have been a way to answer it two ways.

### 4.4 Career paths — NOT A QUESTION

Raised as arguable; it is not. Which role follows which is mostly universal. It is not entirely: progression
into some roles is gated by a national licence or qualification — Germany's
Meister route, regulated professions generally — and a ladder that ignores that
tells a German employee a step exists that does not. Low urgency, but it is a
real difference and it should be on the record rather than assumed away. It is
not a tier decision at all: nobody has to choose whether a Meister requirement
exists. It exists. The only question is where it gets modelled, and that is
engineering rather than product. Recorded on the table.

### 4.5 `pay_elements` — a column, or a rates table?

Migration 0015 adds `country` to `pay_elements` because the table is
country-conditioned and that is not in doubt. The *shape* is.

Look at what the seven rows actually mix. `PE-13` "13th month / year-end" is a
concept that exists in several markets — the element is universal vocabulary.
Its `typical_value` (`8.33% (~1 month)`) and its `statutory_nl`
(`No (CAO/sector dependent)`) are national facts about that concept. A country
column on the whole row means seven markets × seven elements = forty-nine rows,
most of which restate an identical `name`, `category` and `basis`.

The alternative is `pay_elements` staying universal and a new
`pay_element_rates (country, element_id, typical_value, statutory, taxable)`
carrying what varies. Cleaner, and more work: `library_import_service.TableSpec`,
`SHEET_MAP`, the workbook sheet, `core/models.PayElement`,
`pay_components_service` and the export all read the flat shape today.

**Recommendation:** take the additive column now (it is reversible and unblocks a
second market), and treat the rates split as a follow-up the owner can decline.
The migration says so in a comment so the next reader does not mistake the cheap
step for the considered one.

### 4.6 `title_mapping` — country is not the same as language

`title_mapping` has a country column and it is the right dimension for *which
market's job titles these are*. But `be.py` declares `languages=("nl","fr","de")`
and no other pack declares more than one. A Belgian client's payroll export may
name the same role in Dutch or French, and `country = 'BE'` cannot say which. A
match therefore cannot be reported with the language it matched in, and the 325
Dutch rows in the library are unreachable from a Belgian file even where the
title is word-for-word identical.

This is not a blocker — different languages produce different strings, so the
`(org_id, country, existing_title)` unique does not collide — and it is not
urgent. It is a limit worth writing down before someone concludes from a clean
constraint that the problem was handled.

### 4.7 `role_skill_map` and regulated professions

Classified universal, and it mostly is. The exception is that some roles require
a nationally licensed qualification, which is a required *credential* rather than
a required *skill*. That may belong on `job_profiles` per market (4.1) rather
than here. Noted so the classification is not read as stronger than it is.

---

## 5. What happens today when a Belgian client asks for a salary band

**The question the brief asks — silence, a wrong answer, or an error — has a
worse answer than any of the three: it is both silence and a wrong answer, on
the same screen, at the same time.**

Follow the read path.

**The sidebar tells the truth.** `country_service.has_reference_data()` queries
`salary_bands` for the active country and then for `EU`, mirroring
`app.resolve_country()`, and returns False when neither exists. `ui/app.py`
renders:

> No salary reference data for Belgium yet. Bands and benchmarks will be empty
> rather than wrong.

**The page below it does not.** `core/db_loader.load_frames()` calls `_fetch_all`,
which selects every active row of `salary_bands` for the client org *and* the
shared library org, filtered on `org_id` and `status` — **and on nothing else**.
There is no country predicate anywhere in the loader. Those 45 Dutch bands load
for a Belgian client. Then `Repository._build_salary()` keys them:

```python
self.salary[(function, level)] = SalaryBand(...)
```

`(function, level)`. No country. And `Repository.get_salary(function, level)`
reads it back the same way, as do `core/catalog.py`, `ui/app.py`,
`ui/views/pay_equity.py`, `ui/views/data_quality.py` and
`architecture_report_service.py` in five places.

So a Belgian client sees Dutch bands, Dutch compa-ratios, and Dutch
below-market/above-market labels against their people — under a sidebar warning
that says the bands will be empty. The warning is not wrong about the *data*; it
is wrong about the *consequence*, and it is the more visible of the two, which
means it will be believed.

### It gets worse once Belgian rows exist

The database can hold both — `UNIQUE (org_id, country, function, level)` — but
the in-memory repository cannot. A Dutch and a Belgian band for
Engineering/Medior are one dictionary entry, and the survivor is whichever row
`_fetch_all` happened to return last. `_fetch_all` pages with `.range()` and
**never calls `.order()`**, so that is unspecified Postgres row order: not merely
wrong, but wrong differently on different days and possibly different between two
pages of the same read. The band count on the dashboard would also silently stop
matching the row count in the table.

`db_loader._merge_by_precedence` does the right thing — it adds `country` to the
merge key, with a comment explaining that merging on the spec key alone "would
fold a Dutch and a Belgian row into one". The rows survive that far. `Repository`
then folds them anyway, one layer later.

### The contrast that shows this is fixable

`benefits_service` and `Repository._build_benefit_observations` already get it
right, and the comment in `repository.py` says why in as many words:

> Country is part of the KEY, not just a field on the row. Left as a field only,
> it was captured and then dropped at grouping time, so a Polish client's
> benefits were benchmarked against a distribution that was mostly Dutch euro
> values.

That is the same defect, in the same codebase, already found and already fixed —
for benefits. Salary bands, job grades, pay mix, industry factors and level
benefit factors have not had that pass.

### What this means for urgency

**The silo work is urgent, and it is not the migration that is urgent.**

The schema half of the problem is genuinely tidy-up: no second country's rows
exist, so nothing is currently colliding, and a nullable column defaulted to `NL`
breaks nothing. The *read path* is the live risk, and it is live the moment one
Belgian org row is created with `default_country = 'BE'` — before any Belgian
data is imported at all. Setting that one field today produces Dutch pay
comparisons presented as Belgian ones, with a reassuring warning above them.

Ordering, therefore:

1. **Key `Repository` by country** — `salary`, `job_grades`, `pay_mix`,
   `title_mapping`, `level_benefits_factors` — resolving country → `EU` → nothing,
   the way `benefit_observations` already does. This is `core/` and `services/`
   work, owned by another agent; it is reported here, not attempted.
2. **Add `.order()` to `_fetch_all`** so paging is stable, independently of any of
   this.
3. Then migration 0015, which is cheap and can wait.

---

## 6. What migration 0015 does, and what it deliberately does not

**Does:**

1. Widens `level_benefits_factors`' unique to include `country`, finishing what
   0012 started. Pure repair; no data changes.
2. Adds `country` to `pay_elements`, `not null default 'NL'`, FK to
   `countries(code)`, `(org_id, country)` index, unique widened to
   `(org_id, country, element_id)`. Every existing row *is* Dutch, so the default
   backfills correctly — the same argument 0012 used.
3. The same for `benefits_catalog`.
4. Adds a country-neutral `statutory` column to both tables and backfills it from
   `statutory_nl`, **keeping `statutory_nl` in place and in sync via a trigger-free
   copy.** Both columns hold the same value after this migration.
5. Adds table and column comments recording the tier decision in the database
   itself, so the next person to look does not have to re-derive it.

**Does not:**

- **Drop `statutory_nl`.** Four things must be true first, and none is today:
  `library_import_service.SPECS` still maps the workbook column `StatutoryNL` to
  it for both tables; `core/models.PayElement.is_statutory` and
  `BenefitCatalogItem` still read it; the export writes it; and the workbook
  itself still has that heading. Dropping it in the same step would break the
  import in a way the tests would catch and the *live library round-trip* would
  not. The follow-up is listed as a comment in the migration.
- Touch `job_profiles`, `competency_levels`, `seniority_levels` or `career_paths`.
  Those are §4, and §4 is the owner's.
- Split `pay_elements` into a rates table. See §4.5.
- Change any read path. Not this agent's files, and §5 is where the risk is.
- Populate a single non-`NL` row anywhere. Adding a market is importing rows,
  which is the plan document's own standard and is not a migration's job.

Everything in 0015 is additive and reversible: every step is a new column, a new
index, or a unique widened to a superset of itself. A widened unique accepts
everything the narrow one accepted. Nothing that reads the database today reads
it differently afterwards.

---

## 7. What the tests hold

`tests/test_country_tiers.py` asserts the things that must stay true whatever the
owner decides:

- Every table with a `country` column has a unique constraint that includes it,
  or a unique on a surrogate key where country is free to vary. **This is the one
  that fails today**, on `level_benefits_factors`, and it is the test that would
  have caught 0012's omission the day it shipped.
- No table classified UNIVERSAL has acquired a `country` column — the guard
  against a column nobody can populate meaningfully.
- No column name asserts a country. `statutory_nl` fails this today; after 0015
  it fails until the drop step, which is why the test names it as a known
  exception with the condition for removing the exemption stated in the test.
- Every country value in the database is in the `countries` registry, and `EU` is
  never offered as a client's own country.

The database tests skip cleanly without credentials, matching the existing
probe-test convention. The structural ones read the migration files and the
`TableSpec` list and need nothing.

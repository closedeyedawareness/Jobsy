# Implementation Plan — Country Coverage, Gradually

**Roadmap item:** 3.1 *"Multi-country / i18n. Un-hardcode `COUNTRY="NL"`/EUR; per-country bands,
currency, locale."*
**Goal:** Make adding a market **importing rows**, not writing a migration.
Status: **Foundation done and wired to the screen (`0012`, 229 SQL assertions, 21 CI guards, 27 browser checks green) — no second market seeded**
· Owner: Eng

The trigger is the white-label deal: Jobsy is being sold to a multinational, and a multinational's
workforce does not sit in one country. That turns "EU coverage" from a growth ambition into a
correctness requirement, which is why the first thing this plan fixed was not a schema.

---

## 0. The defect this started with

Pay equity regressed `log(salary) ~ female + C(function) + C(level)` with **no country term**. Given
a roster spanning two markets that is gender-blind *by construction* inside each one:

| | |
|---|---|
| Within the Netherlands | **+0.8%** gap |
| Within Poland | **+0.7%** gap |
| **Pooled, as Jobsy reported it** | **27.0% adjusted, flagged statistically significant** |
| Notes mentioning country | **none** |

The EU Pay Transparency Directive triggers a **joint pay assessment at 5%**. So a multinational
uploading its actual workforce could be pushed into a formal remediation process over a number
produced entirely by which country people work in — with the tool showing no sign anything was
wrong. Salaries in two markets differ by more than most real pay gaps, so the artefact swamps the
signal.

Measured, not theorised: `tests/test_country_pooling.py` builds that roster and asserts it.

**Fixed.** `country_col` is detected from the upload, controlled for in the adjusted regression, and
stated in the notes and above the numbers on screen. The same roster now reports **−0.3%, not
significant**. Where a roster spans markets, the headline mean and median still pool — you cannot
adjust a headline — so the result says so in the terms someone about to file a report would act on.

---

## 1. What actually blocked a second country

Not the absence of German data. Composite uniques from `0001`:

```
unique (org_id, function, level)   on salary_bands
unique (org_id, grade)             on job_grades
unique (org_id, existing_title)    on title_mapping
```

A German band for function B, level 5 collided with the Dutch one. The library could not hold two
countries **at all**, whatever anyone imported.

`0012` widens them to include `country`. It follows `0001`'s own reasoning for threading `org_id`
through twenty tables a year early — *"retrofitting a key onto populated tables with live foreign
keys is the kind of migration that goes wrong; carrying an unused column is cheap by comparison"* —
and today the library is 81 jobs and 45 bands, which is the cheapest it will ever be.

---

## 2. The design

### Country is on the rows that move, not on everything

A country column on a table that does not vary by country is a column that drifts, gets
half-populated, and is then believed.

| Country-specific — money, or a national institution | Country-neutral — structure, not price |
|---|---|
| `salary_bands`, `job_grades` | `jobs`, `job_profiles`, `career_paths` |
| `industry_salary_factors` | `skills`, `role_skill_map` |
| `benefits_observations`, `level_benefits_factors` | `competency_levels`, `levels`, `seniority_levels` |
| `title_mapping` (local-language titles → one job) | `categories`, `industries` (the list; its *factors* move) |
| `pay_mix` | `benefits_catalog` (what a pension *is*, not what it is worth) |

### `'EU'` is a real scope, not a NULL

Rows resolve **country first, then the `EU` baseline**, via `app.resolve_country()`. `EU` is a row
somebody wrote on purpose — not a NULL meaning "unknown, or everywhere", which in a unique index does
not even collide with itself, so two contradictory "applies anywhere" rows could both exist unnoticed.

`resolve_country()` returns **null** when neither exists, so a caller can say *"no data for Belgium
yet"* rather than showing Dutch numbers under a Belgian flag. Wrong pay data looks exactly like right
pay data, which is why the absence has to be representable.

### A client's country and an employee's country are different things

- `orgs.default_country` — where the company is; what currency to show; whose collective agreements
  apply to the organisation.
- `employees.country` — **where this person is paid.** Nullable, and null means *not supplied*: it is
  used as the org default for display and as **unknown** for any pay comparison. Guessing it silently
  is precisely how a country-mix artefact becomes a reported gap.

### Markets are seeded dark

`countries` holds NL (live), the `EU` fallback, and BE/DE/FR/ES/IT/PL/SE/DK seeded with
`is_live = false`. PLN, SEK and DKK are in there deliberately, so nothing may quietly assume euro.
**Adding Belgium is importing rows and flipping a boolean.** A market can be worked on gradually
without appearing half-finished in the interface.

---

## 3. Verified — 229 SQL assertions, 0 failed

| Attempt | Result |
|---|---|
| A Dutch band for B/5, then a **German** one, then a **Polish** one | all three accepted — this was impossible before |
| A **second** Dutch band for B/5 | still rejected |
| A band, or an employee, in a country not in the registry | rejected (foreign key) |
| A three-letter or lower-case country code; a currency that is not one | rejected (check) |
| One client with employees in two countries | accepted — the multinational case |
| An employee with no country | stays null, does **not** inherit the client's |
| `resolve_country` for a covered country / an uncovered one / after an EU row exists | `DE` / `null` / `EU` |
| `resolve_country('orgs; drop table countries', …)` | rejected — the table name is interpolated |
| A signed-in user opening a market, or inventing one | blocked |
| `anon` enumerating which markets this product covers | permission denied |

Plus 9 CI guards in `tests/test_country_pooling.py` and 12 in
`tests/test_currency_display.py`, needing no database, and 27 browser checks in
`tests/e2e/journey.py` against real Postgres, real PostgREST and real RLS.

### Defects the tests found

- **`drop constraint if exists` with an invented name is silent.** The first version of `0012` guessed
  `salary_bands_uniq`; the real name is `salary_bands_org_fn_level_key`. The drop did nothing, quietly,
  the old unique survived, and **the entire migration achieved nothing** — while applying without
  error. Caught only because the test *inserts a second country's band* rather than reading the
  catalogue back.
- **`pay_mix` was missing from the country list, and the database said so.** It carries a foreign key
  onto `salary_bands (org_id, function, level)`, so the unique underneath could not be widened while
  the FK pointed at it. `0004` made the two agree *"by constraint rather than by coincidence"*, and
  that agreement had to survive the extra dimension.
- **Two assertions had never run, and the suite called them passes.** Both put a
  data-modifying statement inside a subquery, which Postgres refuses; `psql` raised,
  and `run.sh` counted neither a pass nor a fail — so the total quietly dropped by
  two while the output read "227 passed, 0 failed". The runner now fails on any
  statement that raises instead of asserting, which is how the count went to 229.
- **`None` became a country called `"NONE"`.** `.astype(str)` turns nulls into `"NONE"`, `"NAN"`,
  `"NAT"`, `"<NA>"` — each becoming a market in its own right, splitting cohorts. Blocklisting those
  spellings always misses one; nulls are now dropped *before* stringifying.

---

## 4. Adding a market — the intended path

1. `insert into countries` (already seeded for eight) — or update its currency.
2. Import `salary_bands`, `job_grades`, `pay_mix`, `industry_salary_factors`,
   `benefits_observations`, `level_benefits_factors` carrying that `country`.
3. Add `title_mapping` rows for local-language titles pointing at the **existing** job ids — job
   families are country-neutral, so this is translation, not duplication.
4. Set `is_live = true`.

No migration. No code change.

---

## 4b. What the browser found that nothing else could

The schema half landed green on every test that existed. Driving the actual UI
found two defects in the half that reads it:

- **The whole signed-in page died with `TypeError: 'str' object is not callable`.**
  `main()` already had a local called `_cur` — the currently selected *industry*.
  Adding a module-level `_cur()` for the currency collided with it, and Python
  makes a name local to the **entire** function if it is assigned anywhere in it,
  so every `_cur()` call in `main()` raised. Nothing caught it: not import, not
  lint, not 246 unit tests, because `main()` cannot be called from a test. There
  is now a structural guard for the whole class of it.
- **A Dutch client was told it had no Dutch salary data**, on a screen listing 45
  bands. The check asked for a row *count*, which PostgREST returns in a response
  header; anything that drops that header makes the count `None`, and
  `(None or 0) > 0` reads as "no data". It now asks whether the row is there,
  which the row itself answers. The e2e shim was dropping that header — a stub
  that quietly alters REST responses is the kind of fake that makes a test worse
  than no test — so it forwards it now.

## 5. Not done

- **No second market is seeded.** The schema admits one; nobody has imported one.
- **The CAO crosswalk is Netherlands-only, and is code rather than data.** `cao_crosswalk_service.py`
  encodes ISF and CATS structures directly. Germany's ERA and France's conventions collectives are
  different institutions, not different numbers, so this becomes a per-country module — the honesty
  boundary in `docs/cao-metalektro-isf-reference.md` has to be re-argued for each, not copied.
- **Currency is stored but not converted, and should probably stay that way.** Comparing a Polish
  salary to a Dutch one through an FX rate is a different claim from comparing either to its own
  market; a rate as of a date would need to be shown, not hidden.
- **i18n is untouched.** The export is Dutch or English, and the UI is English. Locale is a separate
  dimension from country — a Belgian client may want French or Dutch — and deliberately not
  conflated with it here.
- **National transpositions of the directive differ.** `pay_equity_service` carries one note about
  Dutch implementing legislation. That becomes per-country content once a second market is live.

---

## 6. The next three: Italy, Portugal, the United Kingdom

Elmar's intent, recorded 2026-09-06: **once the current gates are green, three more markets go in —
IT, PT and UK.** Written here rather than left in a conversation, because two of the three carry
consequences that have to be designed for before the data arrives, not discovered after it.

### 6.1 What "once things are in order" has to mean

Not "the suite is green". The suite was green through every one of the country defects found on
6 September. Concretely, these close first:

- the three `xfail(strict)` findings in `Repository` — `title_mapping` keyed without a country,
  `plan_write_back` ignoring its parameter, and seven builders reading `(row country or "NL")`.

They are one finding, not three: **a layer that does not carry the country dimension while the
database does.** Adding three markets on top of that does not add three problems, it multiplies the
existing one — every new market is another set of rows competing for a key that can hold only one.

### 6.2 Italy and Portugal — the known shape

Euro, EU, directive applies. Structurally these look like ES and FR, so the work is importing rows
rather than changing the model. The part that is **not** a copy is the crosswalk: Italy's **CCNL**
and Portugal's sectoral agreements are different institutions, exactly as §5 says of ERA and the
conventions collectives. The honesty boundary in `docs/cao-metalektro-isf-reference.md` has to be
re-argued for each, never inherited.

### 6.3 The United Kingdom — the one that breaks assumptions

The UK is the first market that is **not in the EU**, and three things in this codebase silently
assume it would be.

1. **Directive (EU) 2023/970 does not apply, and `vacancy_service.draft` asserts it unconditionally.**
   Verified 2026-09-06: the `requirements` tuple is built with no country test, so a UK vacancy is
   told it must state pay under art. 5(1)(a) and name a collective agreement under 5(1)(b) — citing
   an instrument that does not bind that employer. That is worse than a missing feature. It is the
   product being confidently wrong about the law, in the one module whose output is **published**.
   The requirement set becomes per-country content before a UK role can be drafted.

2. **The UK has its own regime, and it is a different instrument rather than a translation.**
   Gender pay gap reporting under the Equality Act 2010 (employers of 250+), with its own
   definitions, reference dates and published figures. Mapping art. 5 onto it would be the same
   category error §5 warns about for ERA and the CAO.

3. **GBP, and the EU-baseline fallback.** Currency is already per-country (`countries.currency`, and
   the report service handles zloty, krona, krone and koruna), and §5's decision *not* to convert is
   more right here, not less. But `_MarketRows` resolves country → EU baseline → nothing, and **a UK
   row must never fall back to an EU baseline**: for a non-member state that fallback is wrong by
   construction, not merely imprecise. The resolution order needs an explicit answer for markets
   outside the union before UK rows exist.

### 6.4 The measurement to take before, not after

Every country defect this month was found by loading **two markets with different values** and
asserting the first market's number comes back. Before IT, PT or UK are seeded, that fixture should
already contain a non-euro, non-EU market — otherwise the assumptions in 6.3 stay invisible in
exactly the way the `(row country or "NL")` default did: measured once when it was true, and never
measured again.

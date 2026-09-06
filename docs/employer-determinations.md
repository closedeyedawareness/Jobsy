# Employer determinations — the judgement layer

**Status: DESIGN. Nothing here is built and no migration is applied.**
Written 6 September 2026, against the schema as it actually stands.

---

## 1. Why

This product is unusually careful about not asserting what it cannot know. Claims
carry a hardness marker, a source and a date. The spine refuses grade and pay
outright, because no neutral unit exists for either. A market it does not hold
gets silence rather than the EU baseline.

All of that is right, and it is half a product.

> A system that only refuses is a sophisticated way of explaining why it cannot
> answer the question.

The client still has to decide. A German grade and a French one have no legal
equivalence — and the employer with sites in both still needs to run one career
architecture. That decision is legitimate. It is **theirs**, it is a convention
rather than a fact, and the useful thing this product can do is make it
*recordable, reviewable and defensible* instead of leaving it in a meeting.

**The design already anticipated this and never built it — and it says so to the
client's face.** The sentence lives twice in `bridge()`: once in the docstring,
and once in the **refusal string that renders on screen**, where a reader is
told that

> "An employer may adopt an internal equivalence as a business judgement — that
> belongs to them, marked CONVENTIE, and is not a fact about the two markets."

So the product already tells a client they may make this decision, and then
offers them nowhere to record it. The marker exists in the hardness vocabulary;
nothing in the product ever writes one. That is not an oversight in the design —
it is a sentence the design wrote and never honoured.

That is the gap this document closes.

---

## 2. What already exists, and must not be duplicated

Measured before designing, because a parallel system beside a working one is the
expensive mistake here.

| Already there | What it does | Relationship to this design |
|---|---|---|
| `services/review_service.py` | A human approves a title→role match; it is written back to `title_mapping` so the next run resolves it deterministically | **The prototype of this whole idea.** One decision type, already correct about credentials and about remap-vs-insert. Becomes the first `determination_type`. |
| `library_revisions` | Versioned library snapshots | The library version a determination was made against |
| `library_audit` | Row-level before/after on every library table, by trigger | Records the *effect* of activation. Not the reasoning. |
| `activity_log` + `app.log` | Who did what, org-scoped, SECURITY DEFINER | Records the *act*. Not the reasoning. |
| Country packs | `Claim(value, hardness, source, as_of, review_after_months)` | The evidence a determination cites, and the thing whose change should reopen it |
| `library_review_policy` (0017) | Per-table review intervals with reasons | Same idea one level up. A determination has a review date for the same reason a salary band does. |

**What none of them holds:** the question that was asked, the purpose the answer
is valid for, what the system proposed *at the time*, which options were
rejected, who participated in which capacity, and what happens when the evidence
underneath it changes.

`review_service` gets closest and stops at `source = "Approved in review by X"`.
That is a label, not a record.

---

## 3. The object

One first-class, versioned, **append-only** row. Superseded, never edited.

### `employer_determination`

**Identity and scope**

| Column | Why |
|---|---|
| `id` | Immutable. Cited in reports, minutes and later challenges. |
| `org_id` | The tenant. RLS as everywhere else. |
| `countries text[]` | A cross-country equivalence has two. Most have one. |
| `determination_type` | Structured, not free text — see §4 |
| `scope` jsonb | Which roles, jobs, grades or population the decision binds |
| `population_at_decision int` | How many people it touched **then**. Recomputing it later answers a different question. |
| `library_revision_id` | The library version this was decided against |
| `engine_version text` | What the matcher was when it proposed |
| `state` | `draft → in_consultation → decided → activated → superseded → withdrawn` |
| `effective_from`, `review_due`, `review_trigger` | When it starts, when it must be looked at again, and what else reopens it |
| `supersedes_id` | The determination this replaces. Never an UPDATE. |

**The question, and what the answer is allowed to mean**

| Column | Why |
|---|---|
| `question text` | The exact question, with its purpose in it |
| `permitted_uses text[]` | What this answer may be used for |
| `excluded_uses text[]` | **What it may not.** The load-bearing field. |

`excluded_uses` is where this design earns its keep. "German D4 and French C3 are
equivalent" is not one claim. It might be true for mobility and reporting and
false for pay, promotion eligibility and benefits. Without this column an
internal convention silently becomes an organisational fact, which is exactly
the failure the spine's refusal exists to prevent — reintroduced by the feature
meant to complete it.

**Decision and rationale**

| Column | Why |
|---|---|
| `options` jsonb | Every option considered, each with its modelled impact |
| `chosen` text | Which one |
| `system_proposed` text | What this product recommended — **stored, not recomputed** |
| `rationale` jsonb | Structured, not a free-text box: business purpose, criteria relied on, why those criteria fit the purpose, how they were applied consistently, why the rejected options were rejected, residual uncertainty, mitigations |
| `hardness` | Always `CONVENTIE`. A determination is a convention by definition; it is what the marker was reserved for. |

A blank "Reason" box produces "Aligned with leadership", which defends nothing.
Where work value is involved the rationale must carry the employer's treatment
of **skill, effort, responsibility and working conditions** — the Art. 4 factors
— because that is the shape a substantiated explanation has to take.

### `determination_evidence`

One row per piece of evidence, **snapshotted**.

`determination_id`, `kind` (pack claim / official crosswalk / client document /
collective agreement / data-quality summary), `reference`, `hardness`,
`source_url`, `retrieved_at`, `excerpt`, `content_hash`.

> A live URL does not prove in 2028 what a page said in 2026.

Hashing the retrieved text is the difference between a citation and a record.
And evidence is **not** collapsed into a single confidence score: a statutory
source with poor employee data and a weak source with clean data are different
problems needing different remedies, and one number hides which you have.

### `determination_participant`

One row per person per act. `determination_id`, `person`, `role_at_the_time`,
`capacity`, `action` (∈ reviewed · advised · agreed · disagreed · decided ·
activated), `at`, `comment`, `conditions`.

**Not everyone approves.** Consulted, advised, agreed and decided are four
different acts and flattening them into "approved by" destroys the only thing a
works council will actually want to see. A recorded *disagreement* is evidence
that the process was real.

Adviser input records that advice was obtained, from whom, on what question,
and whether it was followed — and **never** renders as "legally reviewed" or
"compliant". Privileged material stays out; the determination records that it
exists.

---

## 4. Decision types, and where they already occur

A determination should be created only where human judgement **materially
changes an outcome**. Creating one for every accepted match would bury
governance in noise — the same reasoning that keeps routine matches out of the
review queue today.

| Type | Where it already surfaces |
|---|---|
| `title_to_role` | `review_service` — exists, becomes a determination |
| `cross_country_equivalence` | `bridge()` refusal on GRADE — the refusal offers this as the next step |
| `pay_comparison_basis` | `bridge()` refusal on PAY: FX on a stated day, PPP, or a labour-cost index answer three different questions |
| `gender_code_mapping` | The Spanish `M` refusal already asks this question on screen and throws the answer away at the end of the session |
| `category_of_workers` | Pay-equity comparator definition |
| `job_value_criteria` | Art. 4 weighting |
| `pay_difference_rationale` | Where a gap is explained rather than closed |
| `architecture_exception` | A role that does not fit the grid |

The fourth row is the cheapest possible first slice and the clearest proof: the
gender-mapping question is **already asked, already answered by a human, and
already discarded**. Persisting that one answer is a determination in miniature.

---

## 5. What the interface has to do

The design objective, and everything else follows from it:

> Recording the determination is the **shortest path to finishing the work** —
> not a form to fill in afterwards.

Nobody documents from memory after the meeting. If it is a second step it will
not happen, and a governance feature nobody uses is worse than none because it
implies a record that is not there.

1. **Detect the boundary.** The product already knows where its own judgement
   runs out — every `refusal` string in `bridge()` and every `AmbiguousGenderCodes`
   raise is a decision boundary the code has already located. Those become
   determination tasks instead of dead ends.
2. **Pre-build the dossier.** Question, population, evidence, options and the
   system's own proposal are all computable. The user supplies judgement, not
   clerical reconstruction.
3. **Ask for the choice before the prose.** Select an option, confirm the
   purpose, tick the criteria relied on, then edit a rationale assembled from
   those selections — with the product's words and the employer's words stored
   distinguishably.
4. **Show the impact before activation.** *"Option B moves 43 people into a
   different comparator group and changes two reported gaps by more than a
   point."* That is analysis, not a verdict.
5. **Route by the client's own governance rule**, configured by them — never by
   this product's reading of the law. It says "your policy requires two more
   steps", not "the law requires".
6. **Emit the artefacts automatically**: decision minute, methodology appendix,
   works-council pack, change log, board-report footnote, evidence bundle. This
   is what makes recording cheaper than not recording.
7. **Reopen intelligently.** A determination becomes `review_requested` — not
   silently invalid — when a cited claim changes, a pack passes its review
   interval, the population shifts materially, or its own review date arrives.
   Show the delta; do not ask for the whole dossier again.

### Language

The status vocabulary describes **system state**, never permissibility:

> Ready for employer review · Employer determination required · Adviser input
> requested · Unsupported: evidence unavailable

Never `approved`, `compliant`, `safe` or a green shield as generic chrome.
"Approved" is reserved for a **named person approving a defined decision**.

**This product does not emit a legal conclusion.** It reports what a source
says, what the data produces, what awaits whom, what the employer determined and
what a named adviser advised. The line between those five and a sixth —
"therefore you are compliant" — is the line the whole hardness model exists to
hold, and a judgement layer is exactly where it would get crossed by accident.

---

## 6. Learning across tenants — DECIDED 6 September 2026

Decided by Elmar. Recorded here because it must be settled **before** the first
client, not after: what has already been learned cannot be un-learned, and a
sharing rule written after the fact is a rule nobody agreed to.

### The decision

Learning is shared by default, with the contributing organisation anonymised and
only its **industry** carried through — subject to one threshold, below.

### Why a threshold is still needed

Anonymising protects **language**. It does not protect **structure**.

"Boekhouder means accountant" says nothing about who said it. But a title
carrying a grade, or an equivalence between two countries, is an imprint of how
one employer is built. With eight industries in the system, "an energy company,
grade 12, these function names" is not anonymous to an HR director in that
sector — recognising a competitor's architecture is their job.

**This product already holds that position and already ships it.**
`pay_equity_service.SMALL_N = 5` suppresses exposure figures with the note:

> "Fewer than 5 of one gender with a known entitlement — exposure figures are
> suppressed as unreliable and **re-identifying**."

Small group means recognisable, with or without a name. The cross-tenant rule is
that same rule one level up, and it deliberately reuses the same number.

### The threshold

**K = 5 contributing organisations.** Not a new constant: it is
`pay_equity_service.SMALL_N`, and any implementation must import it rather than
restate it. Two thresholds that mean the same thing will drift, and the one that
drifts will be the one nobody is watching.

### The three categories

| Category | What it is | Rule |
|---|---|---|
| **Vocabulary** | title → role, with no grade and no money | Anonymised, industry attached, shared. **No threshold** — it carries no identity. |
| **Structure or money** | title *with* a grade, salary bands, benefit observations | Visible only at **K ≥ 5 contributing organisations**. Below that it stays with its source. |
| **Determinations** | the D4-equals-C3 kind | **Never shared as records**, at any K. At most counted: *"7 employers have made an equivalence between these two"* — never which, never how, never why. |

The third row is the one to hold. A determination is by definition an employer's
judgement about their own people; that is the single category where sharing is
wrong even anonymised and even at scale. It is also the smallest category, so
almost nothing is lost by excluding it.

### Why this shape is worth having

It needs no permission dialogue with a first client. Sharing vocabulary is
uncontroversial; everything genuinely sensitive waits automatically until enough
sources exist that nobody can be picked out of it. That is a rule that can go
into a contract and then enforce itself, rather than one that depends on someone
making a judgement call per row.

**What still has to be written by a person, not inferred from this document:**
the contractual clause. A technical rule the client never agreed to is not
consent, however well it behaves.

---

## 7. What this is not

**Not "court-proof".** No record can be. The honest promise:

> A contemporaneous, reproducible account of the evidence, the method, the
> participation, the employer's judgement and the implementation.

That is both more defensible and more useful than a claim nobody can stand
behind.

---

## 8. Open, and not for an agent to decide

1. **The AI Act intended-use analysis.** Read at source 6 September 2026; the
   classification itself remains counsel's call, but three things are now known
   rather than assumed.

   **Annex III(4)(b)** covers, verbatim:

   > "AI systems intended to be used to make decisions affecting terms of
   > work-related relationships, the promotion or termination of work-related
   > contractual relationships, to allocate tasks based on individual behaviour
   > or personal traits or characteristics or **to monitor and evaluate the
   > performance and behaviour of persons** in such relationships."

   *Source: Regulation (EU) 2024/1689, Annex III point 4. Hardness: WET as to the
   wording; UITLEG as to whether this product falls inside it.*

   **AND AS OF 6 SEPTEMBER 2026 THERE IS A NEARER ONE STILL.** Elmar decided
   the product will draft vacancy text. Annex III(4)(a) — the sub-point above
   the one quoted here — covers "AI systems intended to be used for the
   recruitment or selection of natural persons, **in particular to place
   targeted job advertisements**, to analyse and filter job applications, and to
   evaluate candidates". Drafting an advertisement is not obviously the same act
   as *placing a targeted* one, and that distinction may well hold — but it is
   now a question the intended-use analysis has to answer explicitly rather than
   one nobody had reason to ask. It is the closest this product has come to a
   named example in the annex.

   The chosen shape helps rather than hurts: the employer edits and approves,
   and both the generated text and the approved text are kept. That is the
   Art. 6(3) "additional layer to human activity" argument made of evidence
   instead of assertion. It does not settle the classification.

   **THE MODULE NEAREST THE LINE WAS THE 9-BOX, NOT PAY EQUITY.** That was not the
   expected answer. Matching and pay-equity analysis produce findings a human
   acts on; the operative words there are "intended to be used **to make
   decisions**", and this product proposes rather than decides. The 9-box is
   different: "monitor and evaluate the performance and behaviour of persons" is
   a description of what a 9-box grid IS. The German pack already flags §87(1)
   Nr. 6 co-determination for precisely that screen, from a different direction
   entirely — two instruments converging on the same module is worth noticing.

   **Article 6(3)** lets a system listed in Annex III fall outside high-risk
   where it performs a narrow procedural task or provides only an additional
   layer to human activity. The judgement layer is directly relevant: a
   determination that stores what the system proposed BESIDE what the employer
   decided is documentary evidence of that shape. Building it may improve the
   position; it does not settle it.

   **AND THE ANALYSIS IS REQUIRED EITHER WAY.** A provider who concludes their
   system is *not* high-risk must document that assessment **before the system
   is placed on the market** and produce it to authorities on request. So "we
   have not done one" is a gap whichever way the answer goes — it is not
   paperwork that becomes necessary only if the answer is yes.
2. ~~**Retention.**~~ **DECIDED 6 September 2026, by Elmar.** The retention
   period follows the applicable directive rather than a number this product
   invents, and PH-LiveOps signals when renewal is due — the same mechanism
   migration 0017 already uses for the reference library, so there is one place
   that says "this needs looking at again" rather than two.

   Two things that decision does **not** yet settle, and neither may be guessed:

   * **Which period, from which instrument — READ AT SOURCE 6 September 2026,
     and the answer is that the directive does not give one.**

     Directive (EU) 2023/970 **specifies no retention period at all.** What it
     specifies instead decides the question anyway:

     - **Art. 21(1):** limitation periods for bringing a claim "shall be no
       shorter than three years", and "shall not begin to run before the
       claimant is aware, or can reasonably be expected to be aware, of an
       infringement". Member States may further provide that they do not run
       while the infringement is ongoing, or before the employment relationship
       ends.
     - **Art. 18:** the burden of proof is REVERSED. Once a worker establishes
       facts suggesting discrimination, the employer must prove there was none —
       and where the employer failed its transparency obligations, it carries
       that burden outright.
     - **Art. 9(9):** an employer answers with "information from the previous
       four years, if available."

     *Hardness: WET. Source: Directive (EU) 2023/970, Arts. 9, 18 and 21, read
     from the EUR-Lex text on 6 September 2026.*

     **THREE YEARS IS A FLOOR, NOT AN ANSWER, and reading it as one would be the
     expensive mistake.** The clock may not start until the worker becomes aware,
     and in some member states not until they leave. So a determination recorded
     in 2026 about somebody who stays until 2040 may still have to be defended
     after that. There is no upper bound derivable from the directive.

     The reversed burden is what makes this urgent rather than administrative.
     The employer has to prove a negative, and a determination is the evidence
     they prove it with. **Deleting the record does not reduce exposure — it
     removes the defence while leaving the claim.**

     What is therefore still open is not "what does the directive say" but a
     policy choice for Elmar with counsel: the national limitation period that
     actually applies, and whether to keep determinations for a fixed long
     period or for the life of the employment relationship plus that period.
   * **The tension with migration 0010.** Minimisation and deletion apply to the
     roster; a determination has to outlive it. The reasoning, the criteria and
     the participants are arguably not personal data. The population snapshot
     is. The likely shape is that a determination keeps its reasoning
     indefinitely and its population figure as a COUNT rather than a set of
     people — but that is a design step, not a consequence of this decision.
3. **First slice.** `gender_code_mapping` is the cheapest and proves the shape;
   `cross_country_equivalence` is the one that carries commercial weight because
   it turns the spine's refusal from a dead end into the beginning of a
   defensible decision.

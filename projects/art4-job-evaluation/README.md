# Art. 4 Job Evaluation — Jobsy's own four-factor methodology

**Status:** project scaffold, started 2026-07-21. Methodology design NOT yet done — the
weighting scheme is deliberately unfixed (see "Design order" below).
**Origin:** the Colliers basis check (see `docs/cao-metalektro-isf-reference.md` and the
pay-equity grade-assignment gap work). The screening tool found that gender predicts grade;
answering *why* — and fixing it — needs a real job evaluation system. Art. 4 of Directive
(EU) 2023/970 requires one built on four factors, but does NOT require ISF or CATS
specifically: any gender-neutral system meeting the standard qualifies. For clients not
bound by a CAO-mandated system (Colliers, most non-industrial organisations), Jobsy's own
methodology can BE the Art. 4 system.

## The approach: seed from the 81 reference roles, don't start blank

Decision (Elmar, 2026-07-21): use the existing reference library — 81 roles with grades,
levels, structured skill requirements, management levels, responsibilities — as the
foundation, scored across the four factors within the existing system.

What the database already gives us, per factor:

| Art. 4 factor | Coverage today | Source |
|---|---|---|
| Skills | ~80% — structured | `role_skill_map` (skill × level 1–5 × Core/Adjacent/Leadership), 75-skill taxonomy in 8 categories |
| Responsibility | ~50% — prose, needs scoring | `JobProfile.management_level`, `key_responsibilities`, `JobGrade.responsibilities/authority` |
| Effort | ~0% — must be rated | inferable hints in descriptions only |
| Working conditions | ~0% — must be rated | nothing (white-collar library never needed it) |

The compounding asset: the matching service already maps client job titles onto these 81
roles. Score the reference library ONCE, and every future client whose jobs match gets
indicative four-factor scores nearly free — per-client fieldwork becomes reviewing deltas,
not scoring from blank.

## ⚠️ The circularity guard (non-negotiable)

The existing grades are the *hypothesis under test*, not the calibration target. If the
new methodology is tuned until it reproduces the current grade ladder, it launders the
status quo through a scorecard and certifies nothing. Therefore:

1. Roles are scored on the four factors **without reference to their current grade**
   (the scoring workbook deliberately puts current grade in a separate reconciliation
   sheet, not on the scoring sheet).
2. Only after scoring is complete do we reconcile score-derived rank vs current grade.
3. **Mismatches are findings, not errors.** A role whose four-factor score says grade 7
   while the ladder says grade 9 is exactly what this instrument exists to surface.

## ⚠️ IP boundary (same as the crosswalk work)

This methodology must be OUR OWN: our own factor definitions, degree levels, and
weighting. It must not reproduce ISF's kenmerken or CATS's gezichtspunten/scoring tables
(FME's / De Leeuw Consult's protected IP — see `docs/cao-metalektro-isf-reference.md`,
"IP & honesty boundary"). Reading public CAO texts for the *legal requirements* is fine;
copying a protected instrument's structure is not.

## ⚠️ Gender-neutrality of the instrument itself

Art. 4(4): the criteria must not themselves discriminate, directly or indirectly. The
classic failure mode — documented across decades of job-evaluation critique — is
overweighting factors that track male-dominated work (physical effort, technical depth)
while underweighting emotional load, care, and coordination skills. Every weighting
decision needs a written neutrality justification in `instrument/weighting-rationale.md`
(to be created WITH the weighting — not retrofitted).

## Design order

1. **Degree levels per factor** (draft in `instrument/factor-degrees.md`) — what does
   "skills level 3 of 6" concretely mean, per factor. Draft exists; needs review.
2. **Weighting scheme + neutrality rationale** — THE make-or-break piece. Deliberately
   not drafted yet; this is the part that gets cross-examined and deserves its own
   focused session, not a side quest.
3. **Score the 81 roles** — `scoring/reference-roles-scoring.csv` is pre-populated with
   everything the database already knows (skills evidence, management level,
   responsibilities) so scoring is review-and-rate, not research. Effort and working
   conditions columns are empty on purpose: they must be rated, not inferred.
4. **Reconcile** score-rank vs current grades; document every mismatch.
5. **Governance layer** — documentation standard, review/appeal procedure (every
   CAO-recognised system has one; ours needs one to be credible), maintenance cycle,
   periodic bias-testing of outcomes.

## Files

- `instrument/factor-degrees.md` — draft degree-level definitions for the four factors
- `instrument/weighting-rationale.md` — NOT YET CREATED; created with the weighting itself
- `scoring/reference-roles-scoring.csv` — the 81 roles, pre-populated evidence, empty
  rating columns
- `scoring/reconciliation.csv` — NOT YET CREATED; generated after scoring is done
- `tools/extract_scoring_baseline.py` — regenerates the scoring CSV from the reference
  library (rerun after any library update)

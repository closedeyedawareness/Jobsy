"""
jobsy/services/country_packs/eu.py — the directive itself, as the baseline pack.

Migration 0012 established that `'EU'` is a real scope and not a NULL: a row
somebody wrote on purpose, resolved after the country and before nothing.
This is the same idea one layer up. Directive (EU) 2023/970 sets numbers that
every member state must at least meet, so they are held once here rather than
copied into twenty-seven packs where twenty-seven copies can drift.

A country pack overrides a band when its own law is stricter or its dates
differ — Spain's pay register has no size threshold at all, France's Index
applies from 50, Belgium's loonkloofwet from 50 — and inherits it otherwise.

── The defect this file was written to fix ───────────────────────────────────

`services/pay_equity_service.py` has told every client since May 2026 that the
duty is *"150+ employees first report 7 June 2028 (annually thereafter);
100-149 first report 7 June 2031 (every 3 years)"*.

Article 9 says something else, and the difference matters in three ways:

  * there is a **250+** band, which that sentence does not mention;
  * the first report for 250+ **and** for 150-249 falls on **7 June 2027**,
    not 2028;
  * 150-249 reports **every three years**, not annually. Only 250+ is annual.

A 180-person client reading Jobsy today is being told they file a year later
than they do, and then every year instead of every three. Either error alone
would be a bad afternoon for whoever acts on it.

The sentence may have been describing the *Dutch bill's* proposed phase-in
rather than the directive, and one secondary source does suggest the Dutch
implementation slips a year. But it is not written that way, it cites no
source, and nobody has re-checked it in four months. That distinction is the
whole reason a claim in this package carries its hardness and its date.
"""
from __future__ import annotations

from . import (CONVENTIE, Claim, CompensationModel, CountryPack, DRAFT, LIVE,
               JobArchitecture, OCCUPATION, ONBEVESTIGD, OrgStructure,
               PayReporting, PerformanceModel, QUALIFICATION, ReportingBand,
               SkillsFramework, SpineMapping, UITLEG, WET)

OJ = "https://eur-lex.europa.eu/eli/dir/2023/970/oj"
_ASOF = "2026-09-05"

#: Article 4(4) names four criteria a pay-setting system must be assessable on,
#: and Jobsy's art4_evaluation service is right to implement them country-
#: neutrally: they are the directive's, identical wherever it is transposed.
#:
#: But they are a FLOOR, not a closed set. Art. 4(4) reads that the criteria
#: "shall include skills, effort, responsibility and working conditions, and, if
#: appropriate, any other factors which are relevant to the specific job or
#: position". An evaluation that scores these four and stops has satisfied the
#: minimum and may still have missed a factor that is relevant to the job in
#: front of it. The tuple is named for what it is so that nothing downstream can
#: read it as the whole of Art. 4.
EQUAL_VALUE_CRITERIA_MINIMUM = ("skills", "effort", "responsibility", "working conditions")

EQUAL_VALUE_CRITERIA = Claim(
    EQUAL_VALUE_CRITERIA_MINIMUM, WET, OJ, _ASOF,
    note="Art. 4(4): an open list. The four named criteria are mandatory, and any other "
         "factor relevant to the specific job or position must be included where "
         "appropriate. Treating the four as exhaustive under-implements the article.")

#: Article 9(1): what a report must actually contain. Held here because the
#: measures are defined once in the directive; a country pack adds to this
#: list, it does not replace it.
REQUIRED_MEASURES = (
    "gender_pay_gap",
    "gender_pay_gap_variable_components",
    "median_gender_pay_gap",
    "median_gender_pay_gap_variable_components",
    "proportion_receiving_variable_pay_by_sex",
    "distribution_across_quartile_pay_bands_by_sex",
    "gender_pay_gap_by_category_of_workers",
)

REPORTING = PayReporting(
    transposed=Claim(
        True, WET, OJ, _ASOF,
        note="Art. 34(1): member states had to bring implementing law into force by "
             "7 June 2026. This pack states the directive's own position; whether a "
             "given country has actually transposed is that country's pack to answer, "
             "and as of September 2026 most had not.",
    review_after_months=6),
    national_law=Claim("Directive (EU) 2023/970", WET, OJ, _ASOF),
    joint_assessment_trigger_pct=Claim(
        5.0, WET, OJ, _ASOF,
        note="Art. 10(1): a joint pay assessment is required where reporting shows an "
             "average pay difference of at least 5% in ANY CATEGORY OF WORKERS, the "
             "employer has not justified it on objective gender-neutral criteria, and "
             "has not remedied it within six months of the report. Per category, not "
             "company-wide: a small headline gap can still hide a triggering category."),
    bands=(
        ReportingBand(
            min_employees=250, max_employees=None,
            first_report=Claim("2027-06-07", WET, OJ, _ASOF),
            frequency=Claim("annually", WET, OJ, _ASOF),
        ),
        ReportingBand(
            min_employees=150, max_employees=249,
            first_report=Claim("2027-06-07", WET, OJ, _ASOF),
            frequency=Claim("every 3 years", WET, OJ, _ASOF,
                            note="Same first date as the 250+ band, different cadence. "
                                 "Collapsing the two bands into one is the error this "
                                 "file exists to correct."),
        ),
        ReportingBand(
            min_employees=100, max_employees=149,
            first_report=Claim("2031-06-07", WET, OJ, _ASOF),
            frequency=Claim("every 3 years", WET, OJ, _ASOF),
        ),
        ReportingBand(
            min_employees=0, max_employees=99,
            first_report=Claim(None, WET, OJ, _ASOF,
                               note="No mandatory reporting. Note the pinpoint: the "
                                    "absence of a duty is what Arts. 9(2)-(4) do NOT "
                                    "impose, not something Art. 9(5) says. 9(5) says only "
                                    "that member states shall not PREVENT employers with "
                                    "fewer than 100 workers from reporting voluntarily. "
                                    "A member state may still impose its own duty, and "
                                    "several have — Belgium from 50 — so a country pack "
                                    "can and does override this band upward."),
            frequency=Claim("none", WET, OJ, _ASOF),
        ),
    ),
)

# ── the spine itself ─────────────────────────────────────────────────────────
#
# EQF and ISCO-08 are the two neutral references country-to-country comparison
# runs through, so the baseline pack is where they are described. Both are real
# and official; neither is a Jobsy invention, which is the whole reason they can
# carry weight a home-made equivalence table could not.

SKILLS = SkillsFramework(
    qualification_framework=Claim(
        ("EQF", 8), WET,
        "https://europa.eu/europass/en/european-qualifications-framework-eqf", _ASOF,
        note="Eight levels, from basic general knowledge at 1 to the most advanced at 8. "
             "Every member state has formally REFERENCED its national qualifications "
             "framework to the EQF — referencing is the actual legal term, and it is a "
             "declared correspondence rather than an equivalence anyone can appeal. That "
             "is exactly the right strength for a spine: strong enough to route through, "
             "weak enough that nobody should present it as a legal equality of two "
             "diplomas."),
    occupation_taxonomy=Claim(
        ("ISCO-08", "ESCO"), UITLEG,
        "https://ilostat.ilo.org/methods/concepts-definitions/classification-occupation/",
        _ASOF,
        note="ISCO-08 is the ILO's occupational classification and the parent of every "
             "national taxonomy in these packs. ESCO is the EU's own layer over it, "
             "adding skills and competences. Marked UITLEG rather than WET because "
             "neither is legislation — they are statistical standards, which is a "
             "different kind of authority and should not be dressed as law. "
             "WHAT IT CLASSIFIES ON, AND WHAT IT THEREFORE CANNOT TELL YOU. ISCO-08 "
             "groups jobs by their MAIN TASKS and by the SKILL LEVEL AND SPECIALISATION "
             "those tasks require. It carries no prescription of its own about pay, about "
             "grading, or about automatic progression — none of that is in the standard, "
             "and none of it can be derived from a match within it. "
             "So a route through this spine says two jobs are comparable IN WHAT THEY DO "
             "and in the level of skill they demand. It does NOT say they should be paid "
             "alike, nor that they sit at the same rung of anybody's structure. "
             "THE RISK THAT CREATES IS SPECIFIC TO THIS PRODUCT: an ISCO match is exactly "
             "the kind of evidence somebody would reach for to argue that a pay "
             "difference between two countries is unjustified. It is not that evidence. "
             "Equal value under the directive turns on skills, effort, responsibility and "
             "working conditions assessed against a job-evaluation instrument — ISCO "
             "carries two of those at most, and carries them for statistical comparison "
             "rather than for valuation. Source: Elmar van Dijk, 2026-09-06."),
)

PERFORMANCE = PerformanceModel(
    codetermination=Claim(
        "indirect, and nationally conditioned", UITLEG,
        "Elmar van Dijk, domain knowledge, 2026-09-05, read against Art. 6", _ASOF,
        note="THE ANSWER IS CONDITIONAL, NOT UNKNOWN, and the difference matters: a "
             "conditional answer names what it depends on, so a reader can go and settle "
             "it for their own case. "
             "The directive says nothing directly about performance management. Art. 6 "
             "says the criteria used for pay AND PAY PROGRESSION must be objective, "
             "gender-neutral and accessible to workers. So EU rules can reach a talent or "
             "assessment grid INDIRECTLY, wherever that grid is used for decisions about "
             "pay, promotion, career development, selection or other terms of employment. "
             "A 9-box that only informs a development conversation sits further from the "
             "article than one that feeds a pay round. "
             "WHETHER AND HOW IT CARRIES THROUGH depends on three things, none of them "
             "answerable at this level: the national transposition, the local "
             "co-determination rules, and how the system actually operates in practice "
             "rather than how it is described. The German pack is the sharpest example of "
             "the second — a works council there has co-determination over pay "
             "structuring outright, so the question is settled before the directive is "
             "even reached. "
             "Marked UITLEG: this is a reading of Art. 6 against how these systems are "
             "used, not a citation to a text that names talent grids."),
)

PACK = CountryPack(
    country="EU",
    name="European Union (directive baseline)",
    currency="EUR",
    languages=("en",),
    status=LIVE,
    countersigned_by="Elmar van Dijk",
    countersigned_on="2026-09-06",
    reporting=REPORTING,
    pay_components=(
        Claim(("pay_definition", "basic wage plus any other consideration, cash or in "
               "kind, direct or indirect"), WET, OJ, _ASOF,
              note="Art. 3(1)(a). Wider than base salary, which is why a gap computed "
                   "on base pay alone does not answer the directive's question."),
    ),
    skills=SKILLS,
    performance=PERFORMANCE,
    notes=(
        "Art. 5: pay or pay range must be given to applicants before interview, and "
        "asking about pay history is prohibited.",
        "Art. 7: a worker may request their own pay level and the sex-disaggregated "
        "average for equal work, answered in writing within two months.",
        "Art. 18: where an employer has not met the transparency duties of Arts. 5, 6, "
        "7, 9 and 10, the burden of proof shifts to the employer to show there was no "
        "pay discrimination.",
        "DRAFT until somebody who is not the author of this file has read Art. 9 "
        "against these four bands. The whole point of the pack is that a legal claim "
        "gets checked by a second pair of eyes before a client sees it.",
    ),
)

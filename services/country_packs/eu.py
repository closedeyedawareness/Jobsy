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

from . import (CONVENTIE, DRAFT, ONBEVESTIGD, UITLEG, WET, Claim, CountryPack,
               PayReporting, ReportingBand)

OJ = "https://eur-lex.europa.eu/eli/dir/2023/970/oj"
_ASOF = "2026-09-05"

#: Article 4: the four criteria a pay-setting system must be able to be
#: assessed on. Jobsy's art4_evaluation service implements these, and it is
#: correct that it does so country-neutrally: the criteria are the directive's,
#: identical in every member state that transposes it.
EQUAL_VALUE_CRITERIA = ("skills", "effort", "responsibility", "working conditions")

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
             "and as of September 2026 most had not."),
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
                               note="Art. 9(5): no mandatory reporting. Member states "
                                    "may not prevent voluntary reporting and may impose "
                                    "a national duty, so a country pack can override "
                                    "this band upward — several already do."),
            frequency=Claim("none", WET, OJ, _ASOF),
        ),
    ),
)

PACK = CountryPack(
    country="EU",
    name="European Union (directive baseline)",
    currency="EUR",
    languages=("en",),
    status=DRAFT,
    reporting=REPORTING,
    pay_components=(
        Claim(("pay_definition", "basic wage plus any other consideration, cash or in "
               "kind, direct or indirect"), WET, OJ, _ASOF,
              note="Art. 3(1)(a). Wider than base salary, which is why a gap computed "
                   "on base pay alone does not answer the directive's question."),
    ),
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

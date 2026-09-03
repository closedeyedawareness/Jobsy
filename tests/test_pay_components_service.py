"""
Composing total reward out of the library instead of out of literals.

The three call sites this replaces priced a package as
`base * (1 + 0.08 + th/100 + var/100) + base * 0.12 + 2000`. Two of those
numbers contradicted the library: pension is stated as a range and had been
turned into a point, and other benefits are stated as 'varies' and had been
given a figure. So most of what is pinned here is the refusal to produce a
number the library does not state.
"""

import pytest

from core.models import PayElement, PayMixEntry
from services.pay_components_service import (
    HOLIDAY, OTHER_BENEFITS, PENSION, THIRTEENTH,
    compose, parse_rate, rate_for_element, statutory_coverage, statutory_elements,
)


class _Repo:
    """Just the two dicts the composition reads."""

    def __init__(self, elements=(), mix=()):
        self.pay_elements = {e.element_id: e for e in elements}
        self.pay_mix = {(m.function, m.level): m for m in mix}


def _library_elements():
    """The seven rows the real library ships, verbatim in the fields that matter."""
    return [
        PayElement("PE-BASE", "Base salary", "Fixed cash", "12x monthly",
                   "100% of pay reference", "No (contractual)", "Yes"),
        PayElement("PE-HOL", "Holiday allowance (vakantietoeslag)", "Fixed cash", "% of base",
                   "8%", "Yes (statutory min 8%)", "Yes"),
        PayElement("PE-13", "13th month / year-end", "Fixed cash", "% of base",
                   "8.33% (~1 month)", "No (CAO/sector dependent)", "Yes"),
        PayElement("PE-VAR", "Variable pay / bonus", "Variable cash", "% of base (on-target)",
                   "0-40% by role", "No", "Yes"),
        PayElement("PE-PENS", "Pension (employer)", "Benefits", "% of pensionable base",
                   "~10-15% (indicative)", "Partly (sector funds)", "Yes"),
        PayElement("PE-BEN", "Other benefits", "Benefits", "Fixed / typical", "varies", "No", "Yes"),
        PayElement("PE-LTI", "Long-term incentive", "Long-term", "% or grant (multi-year)",
                   "varies", "No", "Yes"),
    ]


def _repo(mix=(PayMixEntry("Data", "Lead", 18.0, 8.33, "Yes"),)):
    return _Repo(_library_elements(), mix)


# ── reading a rate out of free text ──────────────────────────────────────────

def test_a_single_percentage_is_a_rate():
    assert parse_rate("8%").pct == 8.0


def test_a_percentage_with_a_gloss_is_still_a_rate():
    r = parse_rate("8.33% (~1 month)")
    assert r.pct == 8.33 and r.is_point


def test_a_range_is_a_range_and_never_a_midpoint():
    r = parse_rate("~10-15% (indicative)")
    assert (r.low, r.high) == (10.0, 15.0)
    assert r.pct is None            # 12.5 is exactly the number that must not appear
    assert r.approximate and r.is_range


def test_a_role_dependent_range_is_not_a_rate_either():
    r = parse_rate("0-40% by role")
    assert r.pct is None and (r.low, r.high) == (0.0, 40.0)


def test_text_with_no_percentage_states_why():
    r = parse_rate("varies")
    assert not r.is_stated and "no percentage" in r.reason


def test_an_empty_value_is_not_a_zero_rate():
    assert parse_rate(None).pct is None
    assert parse_rate("").pct is None


def test_two_unrelated_percentages_are_refused_rather_than_picked_between():
    r = parse_rate("8% of base, 30% for expats")
    assert r.pct is None and "which one applies" in r.reason


def test_a_decimal_comma_reads_as_a_decimal():
    assert parse_rate("8,33%").pct == 8.33


def test_a_missing_element_says_so_instead_of_returning_zero():
    rate, cite = rate_for_element(_Repo(), "PE-HOL")
    assert rate.pct is None and "not in the library" in rate.reason
    assert "absent" in cite


# ── the composition ──────────────────────────────────────────────────────────

def test_the_cash_components_come_from_the_library_and_the_pay_mix():
    tr = compose(60000, "Data", "Lead", _repo())
    by_key = {c.key: c for c in tr.components}
    assert by_key["holiday"].pct == 8.0                  # PayElements PE-HOL
    assert by_key["thirteenth"].pct == 8.33              # PayMix, per cohort
    assert by_key["variable"].pct == 18.0                # PayMix, per cohort
    assert tr.total_target_cash == pytest.approx(60000 * (1 + 0.08 + 0.0833 + 0.18))


def test_every_component_names_where_its_number_came_from():
    tr = compose(60000, "Data", "Lead", _repo())
    for c in tr.components + tr.excluded:
        assert c.source, f"{c.key} has no citation"
    sources = {c.key: c.source for c in tr.components}
    assert "PE-HOL" in sources["holiday"]
    assert "PayMix Data/Lead" in sources["variable"]


def test_pension_stays_a_range_and_makes_the_total_a_range():
    tr = compose(60000, "Data", "Lead", _repo())
    pension = next(c for c in tr.components if c.key == "pension")
    assert (pension.low_pct, pension.high_pct) == (10.0, 15.0)
    assert pension.amount is None and pension.ranged
    assert tr.is_range
    assert tr.total_reward_low == pytest.approx(tr.total_target_cash + 6000)
    assert tr.total_reward_high == pytest.approx(tr.total_target_cash + 9000)
    # The old calculation used base * 0.12 -- a midpoint nobody had chosen.
    assert tr.total_target_cash + 7200 != tr.total_reward_low


def test_other_benefits_are_excluded_and_named_rather_than_guessed():
    tr = compose(60000, "Data", "Lead", _repo())
    other = next(c for c in tr.excluded if c.key == "benefits")
    assert other.amount is None
    assert "no percentage" in other.reason
    # The literal that used to stand here.
    assert all(c.amount != 2000 for c in tr.components)


def test_a_cohort_with_no_pay_mix_has_an_unknown_entitlement_not_a_zero_one():
    tr = compose(60000, "Sales", "Junior", _repo())
    variable = next(c for c in tr.excluded if c.key == "variable")
    assert variable.amount is None and "unknown" in variable.reason
    # Holiday still applies: it is statutory and does not depend on the cohort.
    assert any(c.key == "holiday" for c in tr.components)


def test_without_a_pay_mix_row_the_thirteenth_month_falls_back_and_says_so():
    tr = compose(60000, "Sales", "Junior", _repo())
    thirteenth = next(c for c in tr.components if c.key == "thirteenth")
    assert thirteenth.pct == 8.33
    assert "PE-13" in thirteenth.source and "no PayMix row" in thirteenth.source


def test_lti_is_eligibility_and_never_an_amount():
    tr = compose(60000, "Data", "Lead", _repo())
    assert tr.lti_eligible is True
    assert "no value" in tr.lti_note
    assert all(c.key != "lti" for c in tr.components)


def test_an_unknown_cohort_leaves_lti_eligibility_unknown():
    tr = compose(60000, "Sales", "Junior", _repo())
    assert tr.lti_eligible is None and "unknown" in tr.lti_note


def test_the_basis_sentence_names_what_is_in_and_what_is_out():
    basis = compose(60000, "Sales", "Junior", _repo()).basis()
    assert "holiday allowance" in basis
    assert "Not included" in basis and "other benefits" in basis


def test_a_library_without_pay_elements_prices_only_what_it_can():
    tr = compose(60000, "Data", "Lead", _Repo(mix=[PayMixEntry("Data", "Lead", 18.0, 8.33, "Yes")]))
    assert tr.total_target_cash == pytest.approx(60000 * (1 + 0.0833 + 0.18))
    assert {c.key for c in tr.excluded} >= {"holiday", "pension", "benefits"}


# ── statutory components ─────────────────────────────────────────────────────

def test_only_a_leading_yes_counts_as_statutory():
    ids = {e.element_id for e in statutory_elements(_repo())}
    assert ids == {"PE-HOL"}
    # 'Partly (sector funds)' is pension, and reporting it as statutory would be
    # an untruth that looks authoritative.
    assert "PE-PENS" not in ids


def test_statutory_coverage_reports_on_the_file_not_on_the_employer():
    covered = statutory_coverage(_repo(), {"PE-HOL": False})
    assert len(covered) == 1
    element, present = covered[0]
    assert element.element_id == "PE-HOL" and present is False


def test_the_real_library_composes(tmp_path):
    """Against the shipped workbook, not a fixture: the citations have to match
    rows that actually exist."""
    from core.catalog import Catalog
    repo = Catalog("jobsy_reference_library.xlsx", source="excel").load().repository
    tr = compose(60000, "Data", "Lead", repo)
    assert tr.total_target_cash > 60000
    assert tr.is_range
    assert {c.key for c in tr.excluded} == {"benefits"}

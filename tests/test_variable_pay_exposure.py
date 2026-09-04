"""
Structural variable-pay exposure — the part of the Directive's "pay" that base
salary alone cannot see.

The cases that matter are the two ways this can be wrong: reporting a widening
that isn't there, and staying silent about one that is.
"""

import pandas as pd
import pytest

from services.pay_equity_service import analyze_variable_pay_exposure


PAYMIX = pd.DataFrame([
    {"Function": "Eng", "Level": "Junior", "TargetVariablePct": 3,  "ThirteenthMonthPct": 8.33, "LTIEligible": "No"},
    {"Function": "Eng", "Level": "Lead",   "TargetVariablePct": 18, "ThirteenthMonthPct": 8.33, "LTIEligible": "Yes"},
])


def _grid(n_male_lead, n_female_lead, n_male_junior, n_female_junior, salary=60000):
    """A leveled grid with identical base pay everywhere, so any gap that shows
    up can only have come from the variable structure."""
    rows = []
    for _ in range(n_male_lead):
        rows.append({"Function": "Eng", "Level": "Lead", "Gender": "M", "Salary": salary})
    for _ in range(n_female_lead):
        rows.append({"Function": "Eng", "Level": "Lead", "Gender": "F", "Salary": salary})
    for _ in range(n_male_junior):
        rows.append({"Function": "Eng", "Level": "Junior", "Gender": "M", "Salary": salary})
    for _ in range(n_female_junior):
        rows.append({"Function": "Eng", "Level": "Junior", "Gender": "F", "Salary": salary})
    return pd.DataFrame(rows)


def _run(df, paymix=PAYMIX):
    return analyze_variable_pay_exposure(
        df, paymix, function_col="Function", level_col="Level",
        gender_col="Gender", salary_col="Salary")


def test_identical_base_pay_still_reveals_a_gap_when_men_hold_the_bonus_seats():
    # Every person earns exactly the same base. Men fill Lead, women fill Junior.
    # Base gap is zero; the scheme still pays men more.
    r = _run(_grid(n_male_lead=10, n_female_lead=0, n_male_junior=0, n_female_junior=10))
    assert r.base_mean_gap_pct == pytest.approx(0.0, abs=1e-9)
    assert r.widening_pp is not None and r.widening_pp > 0
    assert r.structure_widens_gap
    # 18% target vs 3% — men are entitled to 15 points more variable pay.
    assert r.target_var_gap_pp == pytest.approx(15.0)
    # LTI is a cliff at Lead: every man eligible, no woman.
    assert r.pct_men_lti_eligible == 100.0
    assert r.pct_women_lti_eligible == 0.0
    assert r.lti_access_gap_pp == 100.0


def test_even_representation_reports_no_widening():
    r = _run(_grid(n_male_lead=6, n_female_lead=6, n_male_junior=6, n_female_junior=6))
    assert r.widening_pp == pytest.approx(0.0, abs=1e-9)
    assert not r.structure_widens_gap
    assert r.target_var_gap_pp == pytest.approx(0.0)
    assert r.lti_access_gap_pp == pytest.approx(0.0)


def test_women_in_the_bonus_seats_narrows_rather_than_widens():
    r = _run(_grid(n_male_lead=0, n_female_lead=10, n_male_junior=10, n_female_junior=0))
    assert r.widening_pp is not None and r.widening_pp < 0
    assert not r.structure_widens_gap
    assert any("narrows" in n for n in r.notes)


def test_a_cohort_missing_from_paymix_is_excluded_and_named_not_zeroed():
    df = _grid(6, 6, 6, 6)
    df = pd.concat([df, pd.DataFrame([
        {"Function": "Sales", "Level": "Lead", "Gender": "M", "Salary": 60000}] * 4)])
    r = _run(df)
    assert r.n_unmatched == 4
    assert ("Sales", "Lead") in r.unmatched_keys
    assert r.n_matched == 24
    # Excluded, not silently treated as a 0% variable cohort — which would have
    # invented a gap out of a missing reference row.
    assert any("unknown, not zero" in n for n in r.notes)


def test_small_samples_are_suppressed_rather_than_published():
    r = _run(_grid(n_male_lead=2, n_female_lead=1, n_male_junior=1, n_female_junior=1))
    assert r.widening_pp is None
    assert r.pct_women_lti_eligible is None
    assert any("suppressed" in n for n in r.notes)


def test_dutch_m_v_labels_analyse_natively():
    df = _grid(10, 0, 0, 10)
    df["Gender"] = df["Gender"].map({"M": "Man", "F": "Vrouw"})
    r = _run(df)
    # Would silently produce an all-male analysis if the M/V fold were missing.
    assert r.n_matched == 20
    assert r.pct_men_lti_eligible == 100.0
    assert r.pct_women_lti_eligible == 0.0


def test_every_result_says_it_is_policy_not_measurement():
    r = _run(_grid(6, 6, 6, 6))
    assert any("POLICY ENTITLEMENT" in n for n in r.notes)


def test_real_library_paymix_joins_the_real_salary_band_grain():
    """The join this whole feature rests on: PayMix and SalaryBands must share
    a (Function, Level) key set, or the exposure read silently covers a subset."""
    xl = pd.ExcelFile("jobsy_reference_library.xlsx")
    pm, sb = xl.parse("PayMix"), xl.parse("SalaryBands")
    assert set(zip(pm.Function, pm.Level)) == set(zip(sb.Function, sb.Level))


# ── the typed record is the route the product uses ───────────────────────────

def test_the_typed_pay_mix_gives_the_same_answer_as_the_frame():
    """PayMix reached this analysis as a raw frame until it joined the library.
    Both routes must agree, or the screen showing exposure and the screen
    showing total reward are reading two different libraries."""
    from core.models import PayMixEntry

    df = _grid(4, 1, 1, 4)
    typed = {(r["Function"], r["Level"]): PayMixEntry(
                function=r["Function"], level=r["Level"],
                target_variable_pct=float(r["TargetVariablePct"]),
                thirteenth_month_pct=float(r["ThirteenthMonthPct"]),
                lti_eligible_text=str(r["LTIEligible"]))
             for _, r in PAYMIX.iterrows()}

    a = _run(df, PAYMIX)
    b = _run(df, typed)

    assert a.n_matched == b.n_matched
    assert a.pct_women_lti_eligible == b.pct_women_lti_eligible
    assert a.pct_men_lti_eligible == b.pct_men_lti_eligible


def test_an_empty_typed_pay_mix_says_what_is_missing():
    with pytest.raises(ValueError, match="Function and Level"):
        _run(_grid(2, 2, 2, 2), {})

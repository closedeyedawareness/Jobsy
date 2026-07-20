"""Tests for the structural (band-free) gender pay-gap engine."""

from __future__ import annotations

import pandas as pd
import pytest

from services.pay_equity_service import (
    SMALL_N,
    analyze_gender_pay_gap,
    flip_gap_sign,
    flip_gap_ci,
)


def _grid(gap_factor: float, per_gender: int = 6) -> pd.DataFrame:
    """
    A leveled grid where, at every Function x Level, women are paid
    ``gap_factor`` x the men's salary (0.90 => women earn 10% less).
    Equal head-counts per gender/cohort so the unadjusted mean gap is exact.
    """
    funcs = ["B", "P", "M", "S"]
    rows = []
    eid = 1000
    for fi, fn in enumerate(funcs):
        for lv in range(1, 7):
            base = 30000 + 5000 * lv + fi * 3000
            for _ in range(per_gender):
                eid += 1
                rows.append({"EmployeeID": f"E{eid}", "Function": fn, "Level": str(lv),
                             "Gender": "M", "Salary": base})
                eid += 1
                rows.append({"EmployeeID": f"E{eid}", "Function": fn, "Level": str(lv),
                             "Gender": "F", "Salary": round(base * gap_factor)})
    return pd.DataFrame(rows)


def _analyze(df, **kw):
    return analyze_gender_pay_gap(
        df, function_col="Function", level_col="Level",
        gender_col="Gender", salary_col="Salary", **kw,
    )


def test_recovers_a_known_10pct_gap():
    r = _analyze(_grid(0.90))
    assert r.n_m == r.n_f > 0
    # Unadjusted mean/median gap is exactly 10% (men paid more).
    assert r.mean_gap_pct == pytest.approx(10.0, abs=0.3)
    assert r.median_gap_pct == pytest.approx(10.0, abs=0.3)
    # Adjusted (function+level controlled) gap also ~10% and significant.
    assert r.adjusted_gap_pct == pytest.approx(10.0, abs=1.0)
    assert r.adjusted_significant is True
    assert r.adjusted_ci is not None and r.adjusted_ci[0] < 10.0 < r.adjusted_ci[1]
    # Every cohort is flagged (10% >= 5% trigger) and reliable (>= SMALL_N each).
    assert r.n_cohorts_tested == 24
    assert r.n_cohorts_flagged == 24
    assert r.n_cohorts_flagged_reliable == 24
    assert all(c.flagged and c.reliable for c in r.cohorts)


def test_equal_pay_shows_no_gap_and_no_flags():
    r = _analyze(_grid(1.00))
    assert r.mean_gap_pct == pytest.approx(0.0, abs=0.3)
    assert r.adjusted_gap_pct == pytest.approx(0.0, abs=0.5)
    assert r.n_cohorts_flagged == 0


def test_representation_is_balanced_in_the_grid():
    r = _analyze(_grid(0.90))
    assert r.pct_women_overall == pytest.approx(50.0, abs=0.5)
    assert all(v == pytest.approx(50.0, abs=0.5) for v in r.women_by_level.values())
    assert all(v == pytest.approx(50.0, abs=0.5) for v in r.women_by_function.values())


def test_small_cohorts_are_marked_unreliable():
    df = pd.DataFrame([
        {"Function": "B", "Level": "1", "Gender": "M", "Salary": 40000},
        {"Function": "B", "Level": "1", "Gender": "M", "Salary": 41000},
        {"Function": "B", "Level": "1", "Gender": "F", "Salary": 30000},  # only 1 woman
    ])
    r = _analyze(df)
    assert r.n_cohorts_tested == 1
    c = r.cohorts[0]
    assert c.reliable is False           # < SMALL_N of at least one gender
    assert c.flagged is True             # big gap still detected
    assert r.n_cohorts_flagged_reliable == 0
    assert SMALL_N >= 3                   # sanity: threshold is a real guard


def test_fte_normalisation_makes_a_part_timer_comparable():
    df = pd.DataFrame([
        {"Function": "P", "Level": "5", "Gender": "M", "Salary": 60000, "FTE": 1.0},
        {"Function": "P", "Level": "5", "Gender": "F", "Salary": 30000, "FTE": 0.5},  # same FTE pay
    ])
    with_fte = _analyze(df, fte_col="FTE")
    assert with_fte.fte_normalised is True
    assert with_fte.mean_gap_pct == pytest.approx(0.0, abs=0.1)   # equal once pro-rated
    without = _analyze(df)                                        # raw pay -> looks like 50% gap
    assert without.mean_gap_pct == pytest.approx(50.0, abs=0.1)


def test_non_binary_rows_are_excluded_from_the_binary_gap():
    df = _grid(0.90, per_gender=6)
    df = pd.concat([df, pd.DataFrame([
        {"EmployeeID": "E9", "Function": "B", "Level": "1", "Gender": "X", "Salary": 40000},
    ])], ignore_index=True)
    r = _analyze(df)
    assert r.n_excluded == 1
    assert r.mean_gap_pct == pytest.approx(10.0, abs=0.3)   # still computes on M/F


def test_gap_needs_both_genders():
    df = pd.DataFrame([
        {"Function": "B", "Level": "1", "Gender": "M", "Salary": 40000},
        {"Function": "B", "Level": "2", "Gender": "M", "Salary": 45000},
    ])
    r = _analyze(df)
    assert r.has_gap is False
    assert r.mean_gap_pct is None
    assert r.adjusted_gap_pct is None


def test_flip_gap_sign_negates_and_passes_through_none():
    assert flip_gap_sign(20.9) == -20.9
    assert flip_gap_sign(-1.4) == 1.4
    assert flip_gap_sign(0.0) == 0.0
    assert flip_gap_sign(None) is None


def test_flip_gap_sign_is_its_own_inverse():
    # values at the function's own 1-decimal precision -- 5.55 would itself get
    # rounded away by the first flip, which isn't what this test is checking.
    for v in (20.9, -1.4, 0.0, 5.5):
        assert flip_gap_sign(flip_gap_sign(v)) == pytest.approx(v)


def test_flip_gap_ci_negates_and_reorders():
    # a men-paid-more-convention CI of (-7.2, 4.1) becomes (-4.1, 7.2)
    assert flip_gap_ci((-7.2, 4.1)) == (-4.1, 7.2)
    assert flip_gap_ci(None) is None


def test_flip_gap_ci_matches_flip_gap_sign_on_a_real_result():
    r = _analyze(_grid(0.90))
    assert r.adjusted_ci is not None
    lo, hi = flip_gap_ci(r.adjusted_ci)
    assert lo == flip_gap_sign(r.adjusted_ci[1])
    assert hi == flip_gap_sign(r.adjusted_ci[0])
    assert lo < hi

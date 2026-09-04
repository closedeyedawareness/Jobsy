"""
Adversarial probe tests for services/pay_equity_service.py and
services/pay_equity_export_service.py.

These are NOT regression guards written after a fix landed (like
tests/test_country_pooling.py) -- they are attacks meant to surface fresh
defects. Each test that currently FAILS documents a concrete, reproduced
defect (see the module docstring of each test for the mechanism and why it
matters under the EU Pay Transparency Directive). Tests that currently PASS
document an attack that did not find a problem.

Run with:
    <scratchpad venv python> -m pytest -q tests/test_payequity_probe.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from services.pay_equity_service import (
    SMALL_N,
    analyze_gender_pay_gap,
    analyze_variable_pay_exposure,
)


def _analyze(df, **kw):
    return analyze_gender_pay_gap(
        df, function_col="Function", level_col="Level",
        gender_col="Gender", salary_col="Salary", **kw,
    )


# ═══════════════════════════════════════════════════════════════════════════
# DEFECT 1 (HIGH SEVERITY, CONFIRMED)
#
# _regression_adjusted_gap's significance test (pay_equity_service.py,
# lines 241-253) divides the estimated gender coefficient by its standard
# error. When the design is *saturated or near-saturated* -- i.e. function +
# level (+ controls) already explain salary almost perfectly, which is
# exactly what happens on a real, clean, step/banded salary grid (every
# employee at a given Function x Level earns the band's exact rate) -- the
# true residual variance is ~0. The fitted residual is then pure float64
# rounding noise (~1e-13 scale), so BOTH the coefficient and its standard
# error collapse to noise of the same tiny magnitude, and their ratio
# (the t-statistic) becomes numerically arbitrary: it can land above or
# below 1.96 by pure chance of floating-point rounding, independent of
# whether the true gap is 0.0% or 20%.
#
# Concretely: an exactly-0.1% deterministic gap on a clean banded grid is
# reported as "adjusted gap 0.1%, 95% CI (0.0, 0.1), statistically
# significant". A zero-width-adjacent CI accompanying a "significant" claim
# is a red flag that the significance test has nothing to do with real
# sampling uncertainty here.
#
# Why it matters for the Directive: this is a sibling of the fixed
# country-pooling bug (tests/test_country_pooling.py) in spirit -- an
# omitted/uncontrolled source of variance (here, "the model happens to fit
# almost perfectly") turns into a confident, headline "statistically
# significant" verdict that a client could read as backing a real,
# investigation-worthy gap when the underlying arithmetic is noise. It cuts
# both ways: the same mechanism can also swallow a real, above-threshold gap
# and call it insignificant (we reproduced both directions below), so this
# is not simply "too eager to flag" -- the verdict is just unreliable
# whenever the fit is very good, which is exactly the pay-hygiene case where
# clients most want to trust the number.
# ═══════════════════════════════════════════════════════════════════════════

def test_gender_level_collinearity_produces_a_nonsense_gap_and_a_false_not_significant_verdict():
    """
    THE flagship instance of Defect 1 -- traced from the RuntimeWarning the
    task points at (pay_equity_service.py line 247), reproduced through the
    module's OWN existing fixture, not a contrived one.

    tests/test_pay_equity_service.py's `_grade_biased_grid(1.5)` builds a
    workforce where women sit exactly 1.5 levels below equivalent men in
    every function -- i.e. real, severe level segregation, which is exactly
    the condition the grade-assignment-gap feature exists to catch. That
    same fixture is already run today by
    test_recovers_a_known_grade_assignment_gap, which triggers this
    RuntimeWarning and explicitly comments that it does NOT check
    adjusted_gap_pct because the estimate is "unreliable" there -- but
    "unreliable" undersells what actually comes out:

        adjusted_gap_pct = -364.1   (women earn 464% of men's pay??)
        adjusted_ci       = (nan, nan)
        adjusted_significant = False

    Mechanism: with a non-integer level shift, men and women never share an
    exact level string, so the female dummy and the C(level) dummies become
    NEAR-singular (not exactly singular -- np.linalg.inv does not raise).
    sigma2 * diag(inv(X'X)) then goes slightly negative from float64
    rounding, np.sqrt(negative) is nan (the observed RuntimeWarning), and:

      * adjusted_gap_pct is computed from coef_f BEFORE the CI/significance
        try-block even runs, and coef_f itself is garbage in this regime --
        so a wild, physically meaningless number is returned as if valid,
        with nothing to signal it should be distrusted.
      * `significant = abs(coef_f / se_f) > 1.96 if se_f else None` treats a
        nan se_f as truthy (bool(float('nan')) is True in Python), so it
        evaluates `nan > 1.96`, which Python resolves to False rather than
        raising -- turning "undefined" into a confident "NOT significant".

    That second part is the one the task explicitly warns about: "A NaN
    standard error must not become a confident verdict." Here it becomes the
    single most reassuring possible verdict -- False -- on a workforce that
    is, by construction, severely gender-segregated by level. A client
    reading "adjusted gap: -364.1%, not statistically significant" would
    reasonably conclude the number is a fluke and there is nothing to
    investigate; the true state is "this regression could not be fit here",
    which the code already returns correctly (None, None, None) for OTHER
    singular-design cases just a few lines up -- this is the one path where
    near- (rather than exact-) singularity slips through that guard.
    """
    from test_pay_equity_service import _grade_biased_grid  # existing, unmodified fixture
    df = _grade_biased_grid(1.5)
    r = _analyze(df)

    # The nonsense magnitude: no real adjusted gap is anywhere close to -364%.
    assert r.adjusted_gap_pct is None or abs(r.adjusted_gap_pct) < 100, (
        f"adjusted_gap_pct={r.adjusted_gap_pct} is not a credible pay gap (nothing between "
        "-100% and +100% is even dimensionally sane for this figure) -- a near-singular "
        "design produced a numerically meaningless coefficient that was returned as if valid")

    # The dangerous part: an undefined fit must not present as a confident "no".
    assert r.adjusted_significant is not False or r.adjusted_ci is not None and not any(
        v != v for v in r.adjusted_ci  # NaN check without importing math.isnan
    ), (
        f"adjusted_significant={r.adjusted_significant} with adjusted_ci={r.adjusted_ci} -- "
        "a NaN standard error (from a near-singular design) produced a confident "
        "'not significant' verdict instead of an honest None/unknown")


def _banded_grid(gap_factor: float) -> pd.DataFrame:
    """A perfectly deterministic, step-banded salary grid: every employee at
    a given (Function, Level) earns exactly base*gap_factor (women) or base
    (men) -- no noise at all, as in a real step/scale pay system. Multiple
    functions and levels give the regression plenty of rows and degrees of
    freedom; the point is the ABSENCE of residual variance, not a small n.
    """
    rows = []
    for fn in ["B", "P", "M", "S"]:
        for lv in range(1, 9):
            base = 30000 + 5000 * lv
            rows.append({"Function": fn, "Level": str(lv), "Gender": "M", "Salary": base})
            rows.append({"Function": fn, "Level": str(lv), "Gender": "F",
                         "Salary": round(base * gap_factor)})
    return pd.DataFrame(rows)


def test_trivial_gap_on_a_banded_grid_is_not_reported_as_significant():
    """A 0.05% gap -- utterly immaterial -- must not be reported as
    'statistically significant'. It currently is, because the near-perfect
    fit of a banded grid collapses the standard error to floating-point
    noise, not because there is genuine evidence of a real effect."""
    r = _analyze(_banded_grid(0.9995))  # ~0.05% "gap"
    assert abs(r.adjusted_gap_pct) < 0.5, "fixture sanity: gap should be tiny"
    assert r.adjusted_significant is not True, (
        f"a {r.adjusted_gap_pct}% gap (well under any meaningful threshold) was reported "
        f"as statistically significant with CI {r.adjusted_ci} -- the significance test is "
        "manufacturing a verdict out of floating-point rounding noise on a saturated fit, "
        "not real evidence")


def test_below_directive_threshold_gap_does_not_get_a_zero_width_ci():
    """A real, deterministic 3% gap -- BELOW the Directive's 5% trigger --
    should never come with a mathematically absurd zero-width confidence
    interval. A CI of (3.0, 3.0) is proof the 'uncertainty' behind the
    significance verdict is not real uncertainty at all."""
    r = _analyze(_banded_grid(0.97))
    assert r.adjusted_gap_pct == pytest.approx(3.0, abs=0.5)

    # Two outcomes are acceptable and one is not. This grid is noiseless by
    # construction -- every woman is exactly 0.97x her band -- so the model fits
    # perfectly and there is genuinely no residual variance to build an interval
    # from. "No interval" is then the honest answer, and it is the one the code
    # now gives. What must never happen is the third outcome: a zero-width
    # interval presented as though the gap were known exactly, with a
    # significance verdict resting on it.
    if r.adjusted_ci is None:
        assert r.adjusted_significant is None, (
            "no confidence interval could be estimated, yet a significance "
            "verdict was still reported -- the verdict has nothing behind it")
        return
    lo, hi = r.adjusted_ci
    assert hi - lo > 0.05, (
        f"adjusted gap {r.adjusted_gap_pct}% got a {hi - lo}-point-wide CI {r.adjusted_ci} -- "
        "a near-zero-width CI on real data means the standard error is degenerate, not tight")


def test_overall_adjusted_regression_has_no_minimum_sample_guard():
    """Per-cohort gaps are marked unreliable below SMALL_N (=5) per gender
    (see CohortGap.reliable / the 'low-sample' note). The population-level
    adjusted regression that produces the HEADLINE adjusted_gap_pct and
    adjusted_significant has no equivalent floor -- only the bare
    'len(y) <= X.shape[1] + 1' identifiability check, which just prevents a
    crash, not an unreliable-but-confident verdict. Here, 2 men and 2 women
    (n=4) produce a "21.8%, statistically significant" headline with a CI
    only a few points wide -- exactly the kind of number that could open a
    joint pay assessment, off 4 people."""
    df = pd.DataFrame([
        {"Function": "B", "Level": "1", "Gender": "M", "Salary": 50000},
        {"Function": "B", "Level": "1", "Gender": "M", "Salary": 51000},
        {"Function": "B", "Level": "1", "Gender": "F", "Salary": 40000},
        {"Function": "B", "Level": "1", "Gender": "F", "Salary": 39000},
    ])
    r = _analyze(df)
    assert r.n_m < SMALL_N and r.n_f < SMALL_N
    assert r.adjusted_significant is not True, (
        f"n_m={r.n_m}, n_f={r.n_f} (total n={r.n}) produced a headline adjusted gap of "
        f"{r.adjusted_gap_pct}% reported as statistically significant with CI {r.adjusted_ci} "
        "-- there is no sample-size floor on the population-level regression matching the "
        f"SMALL_N={SMALL_N} guard already applied to individual cohorts")


# ═══════════════════════════════════════════════════════════════════════════
# DEFECT 2 (HIGH SEVERITY, CONFIRMED)
#
# analyze_gender_pay_gap(..., fte_col=...), pay_equity_service.py lines
# 371-374:
#
#     fte = pd.to_numeric(d[fte_col], errors="coerce")
#     d["_sal"] = np.where((fte > 0), d["_sal"] / fte, d["_sal"])
#     fte_normalised = True
#
# Any row whose FTE value is missing, zero, negative, or unparsable is
# silently left at its RAW (non-pro-rated) salary -- while the result still
# unconditionally sets fte_normalised=True and adds no note whatsoever about
# partial FTE coverage. A part-time employee whose FTE happens to be blank
# is compared, unprorated, against fully FTE-normalised colleagues -- the
# classic false-gap mechanism the module's own docstring warns about
# ("Comparing a 0.6 FTE salary to a 1.0 FTE salary is a classic false gap"),
# except here it happens *silently* even though the client DID supply an FTE
# column, because coverage is incomplete rather than absent. Since part-time
# work is strongly gender-correlated, a few blank FTE cells for women (a
# routine data-entry gap, not a hypothetical) manufacture a large gap in
# exactly the direction that risks a Directive filing.
# ═══════════════════════════════════════════════════════════════════════════

def test_a_missing_fte_value_is_left_unprorated_and_unflagged():
    df = pd.DataFrame([
        {"Function": "P", "Level": "5", "Gender": "M", "Salary": 60000, "FTE": 1.0},
        {"Function": "P", "Level": "5", "Gender": "M", "Salary": 60000, "FTE": 1.0},
        # Correctly pro-rated part-timer: 30000 / 0.5 = 60000, true gap 0%.
        {"Function": "P", "Level": "5", "Gender": "F", "Salary": 30000, "FTE": 0.5},
        # Same true FTE-equivalent pay (60000 at 0.3 FTE = 18000 raw), but her
        # FTE value is missing -- so under the current code her RAW salary
        # (18000) is compared directly against colleagues' FTE-normalised pay.
        {"Function": "P", "Level": "5", "Gender": "F", "Salary": 18000, "FTE": None},
    ])
    r = _analyze(df, fte_col="FTE")
    # The manufactured distortion: two colleagues who are equally paid on an
    # FTE basis produce a large reported gap purely because of a blank FTE cell.
    assert abs(r.mean_gap_pct) < 15, (
        f"a single missing FTE value manufactured a {r.mean_gap_pct}% headline gap out of "
        "what should be a ~0% true (FTE-equivalent) gap")
    # The claim itself is false: not every row was actually FTE-normalised.
    assert any(
        "fte" in n.lower() and ("missing" in n.lower() or "not pro-rated" in n.lower()
                                or "not prorated" in n.lower() or "could not" in n.lower())
        for n in r.notes
    ), (
        f"fte_normalised={r.fte_normalised} with no note that 1 of {r.n} row(s) had an "
        "unusable FTE value and was left at raw (non-pro-rated) salary -- "
        f"notes were: {r.notes}")


def test_a_zero_fte_value_is_also_left_unprorated_and_unflagged():
    """Same mechanism, FTE=0 instead of missing (e.g. a data export default)."""
    df = pd.DataFrame([
        {"Function": "P", "Level": "5", "Gender": "M", "Salary": 60000, "FTE": 1.0},
        {"Function": "P", "Level": "5", "Gender": "M", "Salary": 60000, "FTE": 1.0},
        {"Function": "P", "Level": "5", "Gender": "F", "Salary": 30000, "FTE": 0.5},
        {"Function": "P", "Level": "5", "Gender": "F", "Salary": 12000, "FTE": 0},
    ])
    r = _analyze(df, fte_col="FTE")
    assert any("fte" in n.lower() and ("missing" in n.lower() or "zero" in n.lower()
                                       or "unusable" in n.lower() or "invalid" in n.lower())
               for n in r.notes), (
        f"fte_normalised={r.fte_normalised}, mean_gap_pct={r.mean_gap_pct}, but no note flags "
        f"that an FTE=0 row was left un-prorated; notes were: {r.notes}")


# ═══════════════════════════════════════════════════════════════════════════
# DEFECT 3 (HIGH SEVERITY, CONFIRMED)
#
# analyze_variable_pay_exposure, pay_equity_service.py line 706:
#
#     pm["_tv"] = pd.to_numeric(pm.get("TargetVariablePct"), errors="coerce").fillna(0.0)
#
# This fillna(0.0) runs on the PayMix reference sheet BEFORE the "did this
# row match" check (`matched = merged["_tv"].notna()`, line 713). So a
# (Function, Level) row that DOES exist in PayMix but has a blank
# TargetVariablePct -- a data-entry gap in the reference library, not a
# deliberate "this grade gets no variable pay" policy choice -- is silently
# treated as a genuine 0% entitlement and counted as "matched", rather than
# being excluded as "unknown, not zero". That is precisely the failure mode
# the code explicitly guards against for a wholly MISSING (Function, Level)
# key (see the comment immediately above n_unmatched: "Treating an unmatched
# cohort as zero-variable would manufacture a gap out of a mapping failure,
# so they are excluded and named instead") -- the same reasoning was not
# applied to a blank VALUE within an otherwise-matched row, so the same
# manufactured-gap failure mode still exists via a different door.
# ═══════════════════════════════════════════════════════════════════════════

def test_blank_target_variable_pct_in_paymix_is_excluded_not_zeroed():
    paymix = pd.DataFrame([
        # Junior's target-variable % was never filled in in the reference
        # library -- unknown, not "this grade gets nothing".
        {"Function": "Eng", "Level": "Junior", "TargetVariablePct": None,
         "ThirteenthMonthPct": 8.33, "LTIEligible": "No"},
        {"Function": "Eng", "Level": "Lead", "TargetVariablePct": 18,
         "ThirteenthMonthPct": 8.33, "LTIEligible": "Yes"},
    ])
    rows = [{"Function": "Eng", "Level": "Lead", "Gender": "M", "Salary": 60000} for _ in range(10)]
    rows += [{"Function": "Eng", "Level": "Junior", "Gender": "F", "Salary": 60000} for _ in range(10)]
    df = pd.DataFrame(rows)
    r = analyze_variable_pay_exposure(
        df, paymix, function_col="Function", level_col="Level",
        gender_col="Gender", salary_col="Salary")

    assert ("Eng", "Junior") in r.unmatched_keys, (
        f"a blank TargetVariablePct for Eng/Junior was silently treated as a genuine 0% "
        f"entitlement and counted as matched (n_matched={r.n_matched}, n_unmatched="
        f"{r.n_unmatched}) instead of being excluded as 'unknown, not zero' -- the same "
        "principle the code already applies to a wholly-missing PayMix row")
    # The manufactured consequence: an 18-point "gap" invented entirely out
    # of a blank reference-library cell, not any real policy difference.
    assert r.target_var_gap_pp is None or abs(r.target_var_gap_pp) < 18, (
        f"target_var_gap_pp={r.target_var_gap_pp} -- an 18pp gap was manufactured out of a "
        "blank policy cell rather than a real entitlement difference")


# ═══════════════════════════════════════════════════════════════════════════
# DEFECT 4 (HIGH SEVERITY, CONFIRMED -- found incidentally while probing
# missing/partial columns, not something we went looking for specifically)
#
# analyze_variable_pay_exposure, pay_equity_service.py line 706:
#
#     pm["_tv"] = pd.to_numeric(pm.get("TargetVariablePct"), errors="coerce").fillna(0.0)
#
# `pm.get("TargetVariablePct")` returns plain Python None when the PayMix
# sheet lacks that column at all (as opposed to having it with blank cells).
# `pd.to_numeric(None, errors="coerce")` does not raise and does not return
# an empty/NaN Series -- it returns a bare scalar `np.float64(nan)`. Calling
# `.fillna(0.0)` on that scalar raises `AttributeError: 'numpy.float64'
# object has no attribute 'fillna'`, an unhandled crash out of a public
# entry point. The very next line (LTIEligible) DOES guard against this
# exact situation ("... if "LTIEligible" in pm.columns else pd.Series(...)"),
# so the missing-column case was clearly anticipated for one field and
# simply not applied to TargetVariablePct or ThirteenthMonthPct.
#
# Why it matters: PayMix is a client-maintained reference sheet (per the
# module docstring, "Most cannot [supply bonus data]" -- this whole feature
# exists because clients hand over partial data). A PayMix sheet that only
# has LTIEligible filled in so far (a very plausible partial/in-progress
# reference library) takes down the entire variable-pay exposure screen with
# an internal AttributeError instead of a graceful "target-variable data not
# supplied" result.
# ═══════════════════════════════════════════════════════════════════════════

def test_paymix_missing_target_variable_column_entirely_does_not_crash():
    paymix = pd.DataFrame([{"Function": "Eng", "Level": "Lead", "LTIEligible": "Yes"}])
    rows = [{"Function": "Eng", "Level": "Lead", "Gender": "M", "Salary": 60000} for _ in range(6)]
    rows += [{"Function": "Eng", "Level": "Lead", "Gender": "F", "Salary": 60000} for _ in range(6)]
    df = pd.DataFrame(rows)
    try:
        r = analyze_variable_pay_exposure(
            df, paymix, function_col="Function", level_col="Level",
            gender_col="Gender", salary_col="Salary")
    except AttributeError as e:
        pytest.fail(
            f"analyze_variable_pay_exposure crashed on a PayMix sheet missing the "
            f"TargetVariablePct column entirely (a realistic partial reference library): "
            f"{type(e).__name__}: {e}")
    assert r.n_matched == 12


def test_paymix_missing_thirteenth_month_column_entirely_does_not_crash():
    paymix = pd.DataFrame([{"Function": "Eng", "Level": "Lead", "TargetVariablePct": 18}])
    rows = [{"Function": "Eng", "Level": "Lead", "Gender": "M", "Salary": 60000} for _ in range(6)]
    rows += [{"Function": "Eng", "Level": "Lead", "Gender": "F", "Salary": 60000} for _ in range(6)]
    df = pd.DataFrame(rows)
    try:
        r = analyze_variable_pay_exposure(
            df, paymix, function_col="Function", level_col="Level",
            gender_col="Gender", salary_col="Salary")
    except AttributeError as e:
        pytest.fail(
            f"analyze_variable_pay_exposure crashed on a PayMix sheet missing the "
            f"ThirteenthMonthPct column entirely: {type(e).__name__}: {e}")
    assert r.n_matched == 12


# ═══════════════════════════════════════════════════════════════════════════
# Attacks that HELD UP (documented briefly per the task's ground rules --
# not padding, just recording what did NOT break).
# ═══════════════════════════════════════════════════════════════════════════

def test_country_values_with_different_casing_still_pool_correctly_regression_guard():
    """Not a new defect -- confirms the already-fixed country-pooling logic
    still holds when combined with an FTE column at the same time (an
    interaction the dedicated country-pooling test file doesn't exercise)."""
    rows = []
    for country, base, fte_default in (("NL", 55000, 1.0), ("PL", 25000, 1.0)):
        for i in range(20):
            rows.append({
                "Function": "B", "Level": "5", "Gender": "M" if i % 2 == 0 else "F",
                "Salary": base, "Country": country, "FTE": fte_default,
            })
    df = pd.DataFrame(rows)
    r = _analyze(df, country_col="Country", fte_col="FTE")
    assert r.countries == ("NL", "PL")
    assert abs(r.adjusted_gap_pct) < 2.0, "country control should still neutralise the pay-market gap with FTE also supplied"


def test_single_occupant_cohort_does_not_crash_or_falsely_flag_reliable():
    """A function/level with exactly one man and one woman must not crash the
    pipeline and must never be marked reliable."""
    df = pd.DataFrame([
        {"Function": "B", "Level": "1", "Gender": "M", "Salary": 100000},
        {"Function": "B", "Level": "1", "Gender": "F", "Salary": 40000},
    ])
    r = _analyze(df)
    assert r.n_cohorts_tested == 1
    assert r.cohorts[0].reliable is False
    assert r.cohorts[0].flagged is True  # a real 60% gap, just unreliable at n=1


def test_variable_pay_exposure_with_lti_column_only_present_matches_correctly():
    """A PayMix sheet carrying only the LTIEligible column (Target/13th month
    absent) is the one missing-column combination the code already guards
    correctly -- confirms that path still works once the crashing combinations
    above (Defect 4) are set aside."""
    paymix = pd.DataFrame([{"Function": "Eng", "Level": "Lead", "LTIEligible": "Yes",
                            "TargetVariablePct": 0, "ThirteenthMonthPct": 0}])
    rows = [{"Function": "Eng", "Level": "Lead", "Gender": "M", "Salary": 60000} for _ in range(6)]
    rows += [{"Function": "Eng", "Level": "Lead", "Gender": "F", "Salary": 60000} for _ in range(6)]
    df = pd.DataFrame(rows)
    r = analyze_variable_pay_exposure(
        df, paymix, function_col="Function", level_col="Level",
        gender_col="Gender", salary_col="Salary")
    assert r.n_matched == 12
    assert r.pct_men_lti_eligible == 100.0 and r.pct_women_lti_eligible == 100.0

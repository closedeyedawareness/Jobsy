"""
jobsy/services/pay_equity_service.py

Structural (band-free) gender pay-gap analysis from a *leveled grid*.

The compa-ratio view in the UI needs job titles matched to salary bands. This
service needs none of that — it works straight from the five columns a client
can always hand over:

    employee id · function (e.g. B/P/M/S) · level (e.g. 1-12) · gender · salary

It produces, per the EU Pay Transparency Directive framing:

  * the **unadjusted** ("headline") mean and median gap,
  * the **adjusted** ("like-for-like") gap — salary controlled for function and
    level via a log-salary regression, i.e. the residual gap for people doing
    work of equal value,
  * **per Function x Level cohort** gaps with the Directive's 5% trigger and a
    small-sample guard (privacy + noise),
  * **representation** — the share of women by level and by function, because a
    headline gap is usually driven as much by *where* women sit as by unequal
    pay within a cohort, and
  * a **grade-assignment gap** — does gender predict the level itself
    (controlling for function, and tenure if supplied), independent of whether
    pay is fair within a level. This is the one that actually looks at the
    classification system Art. 4 requires to be gender-neutral, rather than
    just assuming it. A full point-factor job evaluation (skills, effort,
    responsibility, working conditions) is a bigger, separate piece of work
    this does not attempt — this is a statistical flag from data already
    collected, not a substitute for one.

Pure pandas + numpy (numpy ships with pandas); no statsmodels dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Minimum head-count per gender in a cohort before its gap is treated as
# reliable and shown (noise + re-identification guard).
SMALL_N = 5
# Directive trigger: a gap of this magnitude within a category of equal /
# equal-value work is the point at which it must be investigated/justified.
DIRECTIVE_THRESHOLD_PCT = 5.0


def flip_gap_sign(value: float | None) -> float | None:
    """
    Every gap_pct in this module is "positive = men paid more" (male_value
    is the denominator). The NL wetsvoorstel's own definition of *loonkloof*
    is the mirror image -- (vrouw - man) / man, i.e. positive = women paid
    more -- so any UI or export reporting against that definition needs this
    flip. Same magnitude, opposite sign; never call this twice on one value.
    """
    return None if value is None else round(-value, 1)


def flip_gap_ci(ci: tuple[float, float] | None) -> tuple[float, float] | None:
    """flip_gap_sign for a (low, high) CI -- negating also swaps which bound is low."""
    if ci is None:
        return None
    lo, hi = ci
    return flip_gap_sign(hi), flip_gap_sign(lo)


def _gap_pct(male_value: float, female_value: float) -> float | None:
    """Gap as a % of men's pay. Positive = men paid more."""
    if not male_value:
        return None
    return float(round((male_value - female_value) / male_value * 100, 1))


@dataclass(frozen=True)
class CohortGap:
    function: str
    level: str
    n_m: int
    n_f: int
    mean_m: float
    mean_f: float
    median_m: float
    median_f: float
    mean_gap_pct: float | None       # + = men paid more
    median_gap_pct: float | None
    reliable: bool                   # both genders have >= SMALL_N
    flagged: bool                    # |mean gap| >= DIRECTIVE_THRESHOLD_PCT


@dataclass(frozen=True)
class PayGapResult:
    n: int
    n_m: int
    n_f: int
    n_excluded: int                  # rows with a non-binary / unknown gender

    # Unadjusted (headline)
    mean_gap_pct: float | None
    median_gap_pct: float | None

    # Adjusted for function + level (the "unexplained" / like-for-like gap)
    adjusted_gap_pct: float | None
    adjusted_ci: tuple[float, float] | None
    adjusted_significant: bool | None

    # Grade-assignment gap: does gender predict the LEVEL itself (in level
    # units, not %), controlling for function -- a test of the classification
    # system, distinct from whether pay is fair within a level.
    grade_gap_levels: float | None
    grade_gap_ci: tuple[float, float] | None
    grade_gap_significant: bool | None

    # Cohorts (Function x Level)
    cohorts: list[CohortGap]
    n_cohorts_tested: int
    n_cohorts_flagged: int
    n_cohorts_flagged_reliable: int

    # Representation
    pct_women_overall: float
    women_by_level: dict[str, float]
    women_by_function: dict[str, float]

    fte_normalised: bool
    notes: list[str] = field(default_factory=list)

    @property
    def has_gap(self) -> bool:
        return self.n_m > 0 and self.n_f > 0


def _regression_adjusted_gap(
    salary: np.ndarray, is_female: np.ndarray, function: pd.Series, level: pd.Series
) -> tuple[float | None, tuple[float, float] | None, bool | None]:
    """
    Adjusted gap from  log(salary) ~ female + C(function) + C(level).

    Returns (gap_pct, ci, significant). gap_pct is men-vs-women as a % of men's
    pay: a positive number means, at the same function and level, women earn
    that much less. CI/significance are None when the design can't support them
    (too few rows, a single function/level, or a singular design matrix).
    """
    try:
        y = np.log(salary.astype(float))
        fun = pd.get_dummies(function.astype(str), prefix="fun", drop_first=True)
        lvl = pd.get_dummies(level.astype(str), prefix="lvl", drop_first=True)
        cols = [np.ones(len(y)), is_female.astype(float)]
        if fun.shape[1]:
            cols.append(fun.to_numpy(dtype=float))
        if lvl.shape[1]:
            cols.append(lvl.to_numpy(dtype=float))
        X = np.column_stack(cols)
        if len(y) <= X.shape[1] + 1:
            return None, None, None

        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        coef_f = float(beta[1])                       # effect of being female on log-pay
        gap_pct = round((1.0 - math.exp(coef_f)) * 100, 1)

        # Standard error for a CI / significance (needs a non-singular X'X).
        ci = None
        significant: bool | None = None
        try:
            dof = len(y) - X.shape[1]
            resid = y - X @ beta
            sigma2 = float(resid @ resid) / dof
            se_f = float(np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X))[1]))
            lo = (1.0 - math.exp(coef_f + 1.96 * se_f)) * 100
            hi = (1.0 - math.exp(coef_f - 1.96 * se_f)) * 100
            ci = (round(min(lo, hi), 1), round(max(lo, hi), 1))
            significant = abs(coef_f / se_f) > 1.96 if se_f else None
        except (np.linalg.LinAlgError, ZeroDivisionError, ValueError):
            pass
        return gap_pct, ci, significant
    except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
        return None, None, None


def _grade_assignment_gap(
    level: np.ndarray, is_female: np.ndarray, function: pd.Series, tenure: np.ndarray | None = None
) -> tuple[float | None, tuple[float, float] | None, bool | None, str | None]:
    """
    Tests a DIFFERENT question from the pay-adjusted gap above: not "is pay
    equal within a level", but "does gender predict the level itself" --
    i.e. is the classification system doing the sorting, before pay ever
    enters the picture. Directive Art. 4 requires the classification system
    itself to be gender-neutral; a pay-only analysis can look clean while the
    grading underneath it is not.

    OLS:  level ~ female + C(function) [+ tenure].  A negative coefficient on
    "female" means women sit at a lower level than men in the same function
    (and, if tenure is supplied, after accounting for it) -- independent of
    whether they're paid fairly for that level.

    Returns (gap_levels, ci, significant, skip_reason). gap_levels is
    men-vs-women in LEVEL UNITS (not %, levels aren't a ratio scale): positive
    means men sit higher. skip_reason explains why the test didn't run (level
    isn't numeric/ordinal, or too few rows) when the other three are None.
    """
    lvl_num = pd.to_numeric(pd.Series(level), errors="coerce")
    bad = lvl_num.isna()
    if bad.mean() > 0.05:
        return None, None, None, ("Level values aren't numeric/ordinal enough to test grade "
                                   "assignment this way (need e.g. 1-12, not free-text grades).")
    keep = ~bad
    y = lvl_num[keep].to_numpy(dtype=float)
    fem = np.asarray(is_female)[keep.to_numpy()].astype(float)
    fun = pd.get_dummies(pd.Series(function)[keep.to_numpy()].astype(str), prefix="fun", drop_first=True)

    try:
        cols = [np.ones(len(y)), fem]
        if fun.shape[1]:
            cols.append(fun.to_numpy(dtype=float))
        used_tenure = False
        if tenure is not None:
            ten = pd.to_numeric(pd.Series(tenure)[keep.to_numpy()], errors="coerce")
            if ten.notna().mean() > 0.95:
                cols.append(ten.fillna(ten.median()).to_numpy(dtype=float))
                used_tenure = True
        X = np.column_stack(cols)
        if len(y) <= X.shape[1] + 1:
            return None, None, None, "Not enough rows to test grade assignment against function (+ tenure)."

        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        coef_f = float(beta[1])                      # effect of being female on level
        gap_levels = round(-coef_f, 2)                # positive = men sit at a higher level

        ci = None
        significant: bool | None = None
        try:
            dof = len(y) - X.shape[1]
            resid = y - X @ beta
            sigma2 = float(resid @ resid) / dof
            se_f = float(np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X))[1]))
            lo, hi = -coef_f - 1.96 * se_f, -coef_f + 1.96 * se_f
            ci = (round(min(lo, hi), 2), round(max(lo, hi), 2))
            significant = abs(coef_f / se_f) > 1.96 if se_f else None
        except (np.linalg.LinAlgError, ZeroDivisionError, ValueError):
            pass
        note = None if used_tenure else ("Controls for function only, not tenure — a residual difference "
                                         "could partly reflect a genuine tenure gap rather than biased "
                                         "grading. Supply a tenure/start-date column to strengthen this.")
        return gap_levels, ci, significant, note
    except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
        return None, None, None, "Grade-assignment model could not be fit on this data."


def analyze_gender_pay_gap(
    df: pd.DataFrame,
    *,
    function_col: str,
    level_col: str,
    gender_col: str,
    salary_col: str,
    fte_col: str | None = None,
    tenure_col: str | None = None,
    male_label: str = "M",
    female_label: str = "F",
) -> PayGapResult:
    """
    Compute the structural gender pay gap from a leveled grid.

    Salary should be annual and full-time-equivalent; if an ``fte_col`` is given,
    pay is divided by FTE first (guarded against zero/blank). Rows missing
    function, level, gender or a positive salary are dropped. Gender values are
    normalised on their first letter, so "Male"/"m"/"M" all read as ``male_label``.
    """
    notes: list[str] = []
    d = df[[c for c in {function_col, level_col, gender_col, salary_col, fte_col, tenure_col} if c]].copy()

    d["_sal"] = pd.to_numeric(d[salary_col], errors="coerce")
    fte_normalised = False
    if fte_col:
        fte = pd.to_numeric(d[fte_col], errors="coerce")
        d["_sal"] = np.where((fte > 0), d["_sal"] / fte, d["_sal"])
        fte_normalised = True
    else:
        notes.append("No FTE column supplied — part-time pay is not pro-rated, "
                     "which (esp. in the Dutch context) tends to overstate the gap.")

    d["_fun"] = d[function_col].astype(str).str.strip()
    d["_lvl"] = d[level_col].astype(str).str.strip()
    d["_g"] = d[gender_col].astype(str).str.strip().str.upper().str[:1]
    if tenure_col:
        d["_ten"] = pd.to_numeric(d[tenure_col], errors="coerce")

    d = d[d["_sal"].notna() & (d["_sal"] > 0) & (d["_fun"] != "") & (d["_lvl"] != "")]

    m_lab = male_label.strip().upper()[:1]
    f_lab = female_label.strip().upper()[:1]
    n_total = len(d)
    binary = d[d["_g"].isin([m_lab, f_lab])]
    n_excluded = n_total - len(binary)
    if n_excluded:
        notes.append(f"{n_excluded} row(s) with a non-binary/unknown gender are "
                     "excluded from the binary gap but counted in representation.")

    gm = binary[binary["_g"] == m_lab]
    gf = binary[binary["_g"] == f_lab]
    n_m, n_f = len(gm), len(gf)

    mean_gap = _gap_pct(gm["_sal"].mean(), gf["_sal"].mean()) if n_m and n_f else None
    median_gap = _gap_pct(gm["_sal"].median(), gf["_sal"].median()) if n_m and n_f else None

    # Per Function x Level cohorts
    cohorts: list[CohortGap] = []
    for (fun, lvl), grp in binary.groupby(["_fun", "_lvl"], sort=True):
        a = grp[grp["_g"] == m_lab]
        b = grp[grp["_g"] == f_lab]
        if not (len(a) and len(b)):
            continue
        g_mean = _gap_pct(a["_sal"].mean(), b["_sal"].mean())
        cohorts.append(CohortGap(
            function=fun, level=lvl, n_m=len(a), n_f=len(b),
            mean_m=round(float(a["_sal"].mean())), mean_f=round(float(b["_sal"].mean())),
            median_m=round(float(a["_sal"].median())), median_f=round(float(b["_sal"].median())),
            mean_gap_pct=g_mean,
            median_gap_pct=_gap_pct(a["_sal"].median(), b["_sal"].median()),
            reliable=bool(len(a) >= SMALL_N and len(b) >= SMALL_N),
            flagged=bool(g_mean is not None and abs(g_mean) >= DIRECTIVE_THRESHOLD_PCT),
        ))
    n_flagged = sum(1 for c in cohorts if c.flagged)
    n_flagged_reliable = sum(1 for c in cohorts if c.flagged and c.reliable)

    # Adjusted (controls for function + level)
    adj_gap = adj_ci = adj_sig = None
    if n_m and n_f:
        adj_gap, adj_ci, adj_sig = _regression_adjusted_gap(
            binary["_sal"].to_numpy(), (binary["_g"] == f_lab).to_numpy(),
            binary["_fun"], binary["_lvl"],
        )

    # Grade-assignment gap: does gender predict the LEVEL itself, not pay
    # within it -- a different question, testing the classification system
    # rather than the pay decisions made on top of it.
    grade_gap = grade_gap_ci = grade_gap_sig = None
    grade_gap_note = None
    if n_m and n_f:
        grade_gap, grade_gap_ci, grade_gap_sig, grade_gap_note = _grade_assignment_gap(
            binary["_lvl"].to_numpy(), (binary["_g"] == f_lab).to_numpy(), binary["_fun"],
            tenure=binary["_ten"].to_numpy() if "_ten" in binary.columns else None,
        )
        if grade_gap_note:
            notes.append(grade_gap_note)

    # Representation (uses all rows incl. non-binary in the denominator count of people)
    def _pct_women(grp_col: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for key, grp in d.groupby(grp_col, sort=True):
            mf = grp[grp["_g"].isin([m_lab, f_lab])]
            out[key] = float(round(100 * (mf["_g"] == f_lab).mean(), 1)) if len(mf) else 0.0
        return out

    pct_women_overall = float(round(100 * n_f / (n_m + n_f), 1)) if (n_m + n_f) else 0.0

    if any(not c.reliable for c in cohorts):
        notes.append(f"Cohorts with fewer than {SMALL_N} of either gender are marked "
                     "low-sample — treat their gaps as indicative only.")
    notes.append("Adjusted gap controls for function and level only — not tenure, "
                 "hours, performance or location. A residual gap is a prompt to "
                 "investigate, not proof of an unjustified gap.")
    notes.append("The grade-assignment gap tests whether gender predicts the level itself "
                 "(a statistical flag from data already collected) — it does not replace a "
                 "full point-factor job evaluation against skills, effort, responsibility and "
                 "working conditions, which Art. 4 requires and which needs data this tool "
                 "does not currently collect. Treat a significant grade-assignment gap as reason "
                 "to commission that fuller evaluation, not as proof on its own.")
    notes.append("Dutch implementing legislation for the EU Pay Transparency Directive is not "
                 "yet in force (bill before the Tweede Kamer as of May 2026, targeted for 1 "
                 "January 2027 — later than the original June 2026 EU deadline, which the "
                 "European Commission declined to extend). Once live, the formal reporting duty "
                 "that starts the 6-month remediation clock is phased by size: 150+ employees "
                 "first report 7 June 2028 (annually thereafter); 100-149 employees first report "
                 "7 June 2031 (every 3 years); under 100 employees has no reporting duty under "
                 "this mechanism. Frame this analysis as getting ahead of the law, not as a live "
                 "compliance deadline, unless the client is already at 150+.")

    return PayGapResult(
        n=n_total, n_m=n_m, n_f=n_f, n_excluded=n_excluded,
        mean_gap_pct=mean_gap, median_gap_pct=median_gap,
        adjusted_gap_pct=adj_gap, adjusted_ci=adj_ci, adjusted_significant=adj_sig,
        grade_gap_levels=grade_gap, grade_gap_ci=grade_gap_ci, grade_gap_significant=grade_gap_sig,
        cohorts=cohorts, n_cohorts_tested=len(cohorts),
        n_cohorts_flagged=n_flagged, n_cohorts_flagged_reliable=n_flagged_reliable,
        pct_women_overall=pct_women_overall,
        women_by_level=_pct_women("_lvl"), women_by_function=_pct_women("_fun"),
        fte_normalised=fte_normalised, notes=notes,
    )

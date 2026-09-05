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


def _years_from_col(col: pd.Series, *, as_of: pd.Timestamp | None = None) -> pd.Series:
    """
    Turn a tenure/age source column into years, accepting EITHER an
    already-numeric years column (e.g. "Tenure": 4.5) OR a raw date column
    (e.g. "Datum in dienst" / "Geboortedatum"). Two traps here, not one:

    1. pd.to_numeric() on a datetime column doesn't fail or produce years --
       it silently returns nanoseconds-since-epoch, a ~1.6e18 "tenure" that
       would blow up (or worse, silently corrupt) the regression.
    2. The inverse trap, and the one that actually bit this function's first
       version: pd.to_datetime() on a plain int/float column doesn't fail
       either -- it happily reads small numbers as nanoseconds-since-epoch
       and returns real (bogus, ~1970) timestamps, so a genuine numeric years
       column got silently rerouted through the date branch and turned into
       a near-constant ~56 years for everyone. dtype is checked FIRST so a
       numeric column can never reach pd.to_datetime at all; only
       object/string columns attempt date parsing.
    """
    as_of = as_of or pd.Timestamp.now()
    if pd.api.types.is_datetime64_any_dtype(col):
        return (as_of - col).dt.days / 365.25
    if pd.api.types.is_numeric_dtype(col):
        return pd.to_numeric(col, errors="coerce")
    dt = pd.to_datetime(col, errors="coerce")
    if dt.notna().mean() > 0.8:   # object/string column that reads as dates for most rows
        return (as_of - dt).dt.days / 365.25
    return pd.to_numeric(col, errors="coerce")
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
    n_input: int                     # rows received BEFORE any dropping -- n_input - n_dropped_invalid == n
    n_dropped_invalid: int           # rows dropped for missing/zero salary or blank function/level

    # Unadjusted (headline)
    mean_gap_pct: float | None
    median_gap_pct: float | None

    # Adjusted for function + level (the "unexplained" / like-for-like gap)
    adjusted_gap_pct: float | None
    adjusted_ci: tuple[float, float] | None
    adjusted_significant: bool | None
    # Which optional continuous controls actually made it into the adjusted
    # regression -- ("tenure",), ("age",), both, or () when neither was
    # supplied or usable (>95% real values required). Lets the UI/export say
    # exactly what "adjusted" means for THIS run instead of a fixed caveat.
    adjusted_controls_used: tuple[str, ...]

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
    # Countries present in the analysed rows, and whether the adjusted figure
    # controls for them. A roster spanning two countries is two pay markets, not
    # one population -- see the module note on country pooling.
    countries: tuple[str, ...] = ()
    country_controlled: bool = False
    # Levels where every worker is one gender: no gap is computable, so they
    # never appear in the cohort table -- but 100%-one-gender levels are
    # themselves a segregation signal, so they must be visible, not silent.
    # {level: (gender_label, n)}
    single_gender_levels: dict[str, tuple[str, int]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def has_gap(self) -> bool:
        return self.n_m > 0 and self.n_f > 0


def _regression_adjusted_gap(
    salary: np.ndarray, is_female: np.ndarray, function: pd.Series, level: pd.Series,
    tenure: np.ndarray | None = None, age: np.ndarray | None = None,
    country: pd.Series | None = None,
) -> tuple[float | None, tuple[float, float] | None, bool | None, tuple[str, ...]]:
    """
    Adjusted gap from  log(salary) ~ female + C(function) + C(level)
    [+ C(country)] [+ tenure] [+ age].

    tenure/age are optional continuous controls -- each included only when
    supplied AND at least 95% of rows have a real value (missing rows get the
    column median, same guard _grade_assignment_gap uses for tenure). Skipped
    silently otherwise so a mostly-blank column can't quietly distort the fit.

    Returns (gap_pct, ci, significant, controls_used). gap_pct is men-vs-women
    as a % of men's pay: a positive number means, at the same function and
    level (and tenure/age, if included), women earn that much less. CI/
    significance are None when the design can't support them (too few rows, a
    single function/level, or a singular design matrix).
    """
    controls_used: list[str] = []
    try:
        y = np.log(salary.astype(float))
        fun = pd.get_dummies(function.astype(str), prefix="fun", drop_first=True)
        lvl = pd.get_dummies(level.astype(str), prefix="lvl", drop_first=True)
        cols = [np.ones(len(y)), is_female.astype(float)]

        # Country, when the roster spans more than one. Without it, a workforce
        # split across two pay markets produces a gap made almost entirely of
        # country mix: measured on a synthetic roster that is gender-blind BY
        # CONSTRUCTION inside each country (+0.8% NL, +0.7% PL), pooling
        # Netherlands and Poland reported a 27.0% adjusted gap and called it
        # statistically significant. The directive's joint-pay-assessment
        # trigger is 5%.
        ctry = None
        if country is not None:
            ctry = pd.get_dummies(country.astype(str), prefix="ctry", drop_first=True)
            if ctry.shape[1]:
                cols.append(ctry.to_numpy(dtype=float))
                controls_used.append("country")
        if fun.shape[1]:
            cols.append(fun.to_numpy(dtype=float))
        if lvl.shape[1]:
            cols.append(lvl.to_numpy(dtype=float))
        for name, arr in (("tenure", tenure), ("age", age)):
            if arr is None:
                continue
            s = pd.to_numeric(pd.Series(arr), errors="coerce")
            if s.notna().mean() > 0.95:
                cols.append(s.fillna(s.median()).to_numpy(dtype=float))
                controls_used.append(name)
        X = np.column_stack(cols)
        if len(y) <= X.shape[1] + 1:
            return None, None, None, ()

        beta, _resid, rank, _sv = np.linalg.lstsq(X, y, rcond=None)

        # A rank-deficient design does not identify the female coefficient at
        # all. It happens for real: when women never share an exact level with
        # men -- which is precisely the segregation the grade-assignment check
        # exists to find -- "female" is a linear combination of the level
        # dummies, and lstsq still returns numbers. They were being reported. A
        # -364% "adjusted pay gap" is not a gap, it is an unfittable model, and
        # the honest answer is that there is no adjusted figure rather than a
        # confident nonsensical one.
        # The controls are still reported: "we controlled for tenure and age and
        # still cannot separate the effect" is a different and more useful
        # statement than "we controlled for nothing".
        if rank < X.shape[1]:
            return None, None, None, tuple(controls_used)

        coef_f = float(beta[1])                       # effect of being female on log-pay
        if not math.isfinite(coef_f):
            return None, None, None, tuple(controls_used)
        gap_pct = round((1.0 - math.exp(coef_f)) * 100, 1)

        # Standard error for a CI / significance (needs a non-singular X'X).
        ci = None
        significant: bool | None = None

        # Below this there is not enough evidence for an adjusted figure to mean
        # anything, whatever the arithmetic says. Per-cohort gaps have had this
        # floor (SMALL_N) since the beginning; the population-level regression
        # had none at all, so four people -- two of each -- produced "21.8%,
        # statistically significant". A number a client may be required to act
        # on should not be available at n=4.
        n_f = int(np.sum(is_female != 0))
        n_m = int(len(is_female) - n_f)
        if min(n_f, n_m) < SMALL_N:
            return gap_pct, None, None, tuple(controls_used)

        try:
            dof = len(y) - X.shape[1]
            resid = y - X @ beta
            sigma2 = float(resid @ resid) / dof

            # A model that fits perfectly is not a certain one -- it is a
            # saturated one. Real HR data is full of clean banded salary grids
            # where every person's pay is exactly determined by their function
            # and level, so the residuals collapse to float64 noise, the
            # standard error collapses with them, and a 0.1% gap comes back
            # "statistically significant" with a confidence interval of zero
            # width. Zero width is the giveaway: it claims to know the gap
            # exactly. Scaled against the spread of y, because sigma2 is not
            # comparable across payrolls in different currencies.
            _scale = float(np.var(y))
            if sigma2 <= 1e-9 * max(_scale, 1e-12):
                raise ZeroDivisionError("saturated design: no residual variance")
            se_f = float(np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X))[1]))
            # `if se_f` was not enough, and the way it failed mattered: NaN is
            # TRUTHY in Python, so a standard error that came back NaN passed
            # the guard, and `nan > 1.96` is False -- reporting "not
            # statistically significant" for a regression that could not be fit
            # at all. Under the Directive that reads as "nothing to
            # investigate". A standard error must be finite and positive before
            # anything may be concluded from it; when it is not, the answer is
            # "we cannot say", which is what None means here.
            if not math.isfinite(se_f) or se_f <= 0:
                ci, significant = None, None
            else:
                lo = (1.0 - math.exp(coef_f + 1.96 * se_f)) * 100
                hi = (1.0 - math.exp(coef_f - 1.96 * se_f)) * 100
                ci = (round(min(lo, hi), 1), round(max(lo, hi), 1))
                significant = abs(coef_f / se_f) > 1.96
        except (np.linalg.LinAlgError, ZeroDivisionError, ValueError):
            pass
        return gap_pct, ci, significant, tuple(controls_used)
    except (np.linalg.LinAlgError, ValueError, ZeroDivisionError):
        return None, None, None, ()


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

            # A model that fits perfectly is not a certain one -- it is a
            # saturated one. Real HR data is full of clean banded salary grids
            # where every person's pay is exactly determined by their function
            # and level, so the residuals collapse to float64 noise, the
            # standard error collapses with them, and a 0.1% gap comes back
            # "statistically significant" with a confidence interval of zero
            # width. Zero width is the giveaway: it claims to know the gap
            # exactly. Scaled against the spread of y, because sigma2 is not
            # comparable across payrolls in different currencies.
            _scale = float(np.var(y))
            if sigma2 <= 1e-9 * max(_scale, 1e-12):
                raise ZeroDivisionError("saturated design: no residual variance")
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



def _reporting_duty_notes(countries: tuple, headcount: int) -> list[str]:
    """The reporting duty, read from the country packs rather than retyped.

    This used to be a paragraph of hard-coded text, and the text was wrong. It
    told every client that the duty was "150+ employees first report 7 June
    2028 (annually thereafter)". Directive (EU) 2023/970 art. 9 has a 250+ band
    the sentence never mentioned, dates the first report 7 June 2027 rather
    than 2028, and makes the 150-249 band THREE-YEARLY, not annual. A 180-
    person client was being told they filed a year late and then four times
    too often. It sat in production from May to September 2026 because a legal
    date written as prose has nothing to check it against.

    So it is not prose any more. `services/country_packs` holds each claim with
    its hardness, its source and the date somebody last looked at it, the EU
    pack holds the directive's own bands once so they cannot drift, and
    tests/test_country_packs.py asserts every boundary from both sides.

    Silence is a real answer here. A country we hold no pack for gets no
    sentence at all, because the failure worth preventing is not an unhelpful
    report — it is a confident one that understates somebody's legal duty.
    """
    try:
        from services import country_packs as cp
    except Exception:
        return []

    # No country column does not mean no country. Fall back to the client's
    # active market, so a single-market Dutch roster still gets its duty stated
    # instead of silently losing the note it had before this rewrite.
    resolved = tuple(countries or ())
    if not resolved:
        active = cp.for_country(None)
        if active is None:
            return []
        resolved = (active.country,)

    out: list[str] = []
    for country in resolved:
        pack = cp.for_country(country)
        if pack is None:
            out.append(f"No pay-reporting duty is stated for {country}: Jobsy holds no "
                       "country pack for that market yet. This is a gap in the tool, not "
                       "an absence of obligation — check the national rules directly.")
            continue

        band, source = cp.band_for(headcount, country)
        national = pack.reporting.national_law if pack.reporting else None
        origin = ("Directive (EU) 2023/970" if source == cp.BASELINE
                  else (str(national.value) if national else f"national law in {pack.country}"))
        where = (f"{pack.name}: " if len(resolved) > 1 else "")

        if band is None or band.first_report.value is None:
            out.append(f"{where}no mandatory pay-gap reporting duty applies at this size "
                       f"under {origin}.")
        else:
            # A first_report that is a date reads as a deadline; one that is a
            # phrase ("in force since 2012") reads as a duty already running.
            # Those are different sentences and a client acts differently on
            # each, so the note does not force them into one template.
            first = str(band.first_report.value)
            when = (f"first applies {first}" if first[:2].isdigit()
                    else f"has been {first}")
            out.append(
                f"{where}at roughly {headcount} people the reporting duty under {origin} "
                f"{when}, repeating {band.frequency.value}. Headcount here is the size of "
                "the analysed roster; the legal threshold counts employees, which may be "
                "a different number.")

        rep = pack.reporting
        if rep and rep.pre_existing_duty and rep.pre_existing_duty.value:
            out.append(f"{where}{rep.pre_existing_duty.note}")
        if rep and not rep.transposed.value:
            out.append(f"{where}the directive is recorded as not yet transposed "
                       f"({rep.transposed.as_of}). Frame this analysis as getting ahead of "
                       "the law rather than as a live deadline, unless a national duty "
                       "already applies.")
        if pack.status != cp.LIVE:
            # Two different warnings, because they call for two different
            # actions. A pack still holding unverified claims needs somebody to
            # go and look; a pack whose claims are all sourced but which is not
            # LIVE needs a person to countersign what an agent checked. Saying
            # "not all verified" over the second is simply untrue, and a warning
            # that is untrue is the fastest way to teach a reader to skip them.
            n = len(pack.unverified)
            if n:
                out.append(f"{where}this country pack is {pack.status.upper()}: {n} claim"
                           f"{'s' if n > 1 else ''} in it {'are' if n > 1 else 'is'} still "
                           "unverified. Confirm at source before relying on a date.")
            else:
                out.append(f"{where}this country pack is {pack.status.upper()}: every claim "
                           "carries a source, but the check was made by an agent and not "
                           "yet countersigned by a person.")
    return out



def _currency_notes(countries: tuple) -> list[str]:
    """Whether the salary column is even in one unit.

    The multi-country note below was written from a measured artefact: a roster
    built gender-blind inside each country produced a 27% adjusted gap when the
    Netherlands and Poland were pooled. That was a PAY-LEVEL artefact, and both
    columns were euros.

    Poland is not in euros. Once a pack exists for a non-euro market the same
    roster can arrive with two different UNITS in one salary column, and that is
    a worse failure than the pay-level one, because it is invisible: 8000 PLN
    beside 5000 EUR looks like a well-paid Pole. A country control absorbs a
    constant multiplicative factor, so the adjusted gap may survive it, but
    every absolute figure in the report — medians, quartile bands, the
    distribution the directive's Art. 9(1) actually asks for — is meaningless,
    and nothing on the screen would say so.

    This cannot detect the mistake; a number has no unit attached. It can only
    say that the conditions for it are present, which is the honest limit and
    still worth saying out loud.
    """
    try:
        from services import country_packs as cp
    except Exception:
        return []

    known = [(c, cp.for_country(c)) for c in (countries or ())]
    currencies = {p.currency for _, p in known if p is not None}
    if len(currencies) < 2:
        return []

    by_cur: dict[str, list[str]] = {}
    for c, pack in known:
        if pack is not None:
            by_cur.setdefault(pack.currency, []).append(c)
    shown = "; ".join(f"{cur}: {', '.join(sorted(cs))}"
                      for cur, cs in sorted(by_cur.items()))
    return [
        f"CURRENCY: this workforce spans more than one currency ({shown}). Jobsy "
        "deliberately does not convert — a Polish salary shown in euro is a different "
        "claim from the same figure in its own market, and it needs a rate as of a "
        "date, shown rather than hidden. That policy is right for DISPLAY and it "
        "means the responsibility sits on the input here: pooling amounts in "
        "different units into one gap produces a number that is not a small error "
        "but a different quantity. Every absolute figure above — medians, quartile "
        "bands, the pay distribution Art. 9(1) asks for — assumes one unit, and a "
        "salary column carries no unit to check. Analyse each currency separately, "
        "or supply the roster already converted at a rate and date you can state."]


def analyze_gender_pay_gap(
    df: pd.DataFrame,
    *,
    function_col: str,
    level_col: str,
    gender_col: str,
    salary_col: str,
    fte_col: str | None = None,
    tenure_col: str | None = None,
    age_col: str | None = None,
    country_col: str | None = None,
    male_label: str = "M",
    female_label: str = "F",
    salary_already_fte: bool = False,
) -> PayGapResult:
    """
    Compute the structural gender pay gap from a leveled grid.

    Salary should be annual and full-time-equivalent; if an ``fte_col`` is given,
    pay is divided by FTE first (guarded against zero/blank). Rows missing
    function, level, gender or a positive salary are dropped. Gender values are
    normalised on their first letter, so "Male"/"m"/"M" all read as ``male_label``.

    ``tenure_col``/``age_col`` each accept EITHER an already-numeric years
    column OR a raw date column (start date / date of birth) -- converted via
    ``_years_from_col``. When supplied and usable (>=95% real values), both
    become additional continuous controls in the adjusted-gap regression, not
    just the grade-assignment side-test.
    """
    notes: list[str] = []
    d = df[[c for c in {function_col, level_col, gender_col, salary_col, fte_col,
                        tenure_col, age_col, country_col} if c]].copy()

    d["_sal"] = pd.to_numeric(d[salary_col], errors="coerce")
    fte_normalised = False
    if salary_already_fte:
        # The source declares the salary column ALREADY full-time-equivalent
        # (e.g. Dutch intake templates' "FT salaris"). Dividing it by FTE
        # again would double-correct -- inflating part-timers' pay, and since
        # part-time skews female (esp. in NL), silently SHRINKING a real gap.
        fte_normalised = True
        notes.append("Salary supplied as full-time-equivalent by the source — "
                     "no additional FTE pro-rating applied.")
    elif fte_col:
        fte = pd.to_numeric(d[fte_col], errors="coerce")
        d["_sal"] = np.where((fte > 0), d["_sal"] / fte, d["_sal"])
        # np.where leaves rows with a blank, zero or negative FTE at their RAW
        # salary -- a part-timer's actual pay compared against everybody else's
        # full-time-equivalent. Part-time work skews female, so each such row
        # pushes the reported gap up, in the direction that triggers a filing.
        # Claiming fte_normalised=True regardless said the opposite of what had
        # happened. Report the truth, and name the rows.
        # A row whose FTE is missing, zero or negative has an UNKNOWN
        # full-time-equivalent salary, and np.where above quietly left it at its
        # raw one -- a part-timer's actual pay set beside everybody else's
        # full-time figure. Part-time work skews female, so each such row pushes
        # the reported gap up, in the direction that triggers a Directive
        # filing: one blank cell in a four-person test manufactured a 35% gap
        # out of a workforce paid identically per FTE.
        #
        # So it is excluded and counted, not guessed -- the same rule this
        # module already applies to an unknown gender, and that 0012 applies to
        # an employee with no country. Unknown is not zero and it is not the
        # average either.
        _fte_bad = int((~(fte > 0)).sum())
        if _fte_bad:
            d.loc[~(fte > 0), "_sal"] = np.nan
            notes.append(
                f"{_fte_bad} row(s) excluded: an FTE column was supplied but "
                f"theirs is missing, zero or negative, so their full-time-"
                f"equivalent pay is unknown. Comparing their raw salary against "
                f"full-time colleagues would overstate the gap — part-time work "
                f"skews female. Fill the FTE column to include them.")
        fte_normalised = True
    else:
        notes.append("No FTE column supplied — part-time pay is not pro-rated, "
                     "which (esp. in the Dutch context) tends to overstate the gap.")

    d["_fun"] = d[function_col].astype(str).str.strip()
    d["_lvl"] = d[level_col].astype(str).str.strip()
    d["_g"] = d[gender_col].astype(str).str.strip().str.upper().str[:1]
    # Dutch HR exports use M/V (Man/Vrouw). Fold the female aliases into the
    # effective female label so a Dutch file analyses natively instead of all
    # its women landing in "excluded (unknown gender)" -- which silently
    # produced an all-male "analysis" before this. "Female"/"Vrouw"/"F"/"V"
    # all normalise to the same bucket; anything else (X, blank, other) still
    # counts as non-binary/unknown, exactly as before.
    _f_lab = female_label.strip().upper()[:1]
    _m_lab = male_label.strip().upper()[:1]
    d["_g"] = d["_g"].apply(lambda g: _f_lab if g in ("F", "V") else (_m_lab if g == "M" else g))
    if tenure_col:
        d["_ten"] = _years_from_col(d[tenure_col])
    if age_col:
        d["_age"] = _years_from_col(d[age_col])

    n_input = len(d)
    _valid = d["_sal"].notna() & (d["_sal"] > 0) & (d["_fun"] != "") & (d["_lvl"] != "")
    n_dropped_invalid = int((~_valid).sum())
    if n_dropped_invalid:
        _dropped = d[~_valid]
        _drop_m = int((_dropped["_g"] == male_label.strip().upper()[:1]).sum())
        _drop_f = int((_dropped["_g"] == female_label.strip().upper()[:1]).sum())
        notes.append(f"EXCLUSIONS: {n_dropped_invalid} of {n_input} input row(s) were dropped for a "
                     f"missing/zero salary or a blank function/level ({_drop_m} male, {_drop_f} female, "
                     f"{n_dropped_invalid - _drop_m - _drop_f} other/unknown). Every figure in this "
                     "analysis covers only the remaining rows — reconcile these exclusions against the "
                     "source before treating any number as complete.")
    d = d[_valid]

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

    # Country, if the roster carries one. Uppercased and stripped so "nl", "NL "
    # and "Nl" are one market rather than three.
    if country_col and country_col in binary.columns:
        # Nulls are dropped BEFORE stringifying, not blocklisted afterwards.
        # `.astype(str)` turns None into "NONE", NaN into "NAN", NaT into "NAT"
        # and pd.NA into "<NA>" -- each of which would become a country in its
        # own right, splitting a cohort and inventing a market. A blocklist of
        # those spellings always misses one; asking pandas what is missing does
        # not. (Caught by tests/test_country_pooling.py, which grew "NONE".)
        _raw = binary[country_col]
        _known = _raw.notna()
        binary = binary.assign(
            _ctry=_raw.where(_known, "").astype(str).str.strip().str.upper())
        binary = binary[_known.to_numpy() & binary["_ctry"].ne("").to_numpy()]
    countries_present = tuple(sorted(binary["_ctry"].unique())) if "_ctry" in binary.columns else ()
    multi_country = len(countries_present) > 1

    # Adjusted (controls for function + level [+ country] [+ tenure] [+ age])
    adj_gap = adj_ci = adj_sig = None
    adj_controls: tuple[str, ...] = ()
    if n_m and n_f:
        adj_gap, adj_ci, adj_sig, adj_controls = _regression_adjusted_gap(
            binary["_sal"].to_numpy(), (binary["_g"] == f_lab).to_numpy(),
            binary["_fun"], binary["_lvl"],
            tenure=binary["_ten"].to_numpy() if "_ten" in binary.columns else None,
            age=binary["_age"].to_numpy() if "_age" in binary.columns else None,
            country=binary["_ctry"] if multi_country else None,
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

    # Single-gender levels: no gap computable, so they'd otherwise be invisible
    # in the cohort table -- but a 100%-one-gender level is itself a segregation
    # signal worth reporting explicitly.
    single_gender_levels: dict[str, tuple[str, int]] = {}
    for lvl, grp in binary.groupby("_lvl", sort=True):
        nm_ = int((grp["_g"] == m_lab).sum())
        nf_ = int((grp["_g"] == f_lab).sum())
        if (nm_ == 0) != (nf_ == 0):   # exactly one gender present
            single_gender_levels[lvl] = ((m_lab if nm_ else f_lab), nm_ or nf_)
    if single_gender_levels:
        notes.append(f"{len(single_gender_levels)} level(s) are 100% one gender and therefore have no "
                     "computable gap and do NOT appear in the cohort table — see the single-gender "
                     "levels list. Fully one-gender levels are a segregation signal in their own right; "
                     "absence from the cohort table must not read as absence of an issue.")

    if any(not c.reliable for c in cohorts):
        notes.append(f"Cohorts with fewer than {SMALL_N} of either gender are marked "
                     "low-sample — treat their gaps as indicative only.")
    if adj_controls:
        notes.append(f"Adjusted gap also controls for {' and '.join(adj_controls)} (in addition to "
                     "function and level) — not hours, performance or location. A residual gap is a "
                     "prompt to investigate, not proof of an unjustified gap.")
    else:
        notes.append("Adjusted gap controls for function and level only — not tenure, "
                     "hours, performance or location. A residual gap is a prompt to "
                     "investigate, not proof of an unjustified gap.")
    notes.append("The grade-assignment gap tests whether gender predicts the level itself "
                 "(a statistical flag from data already collected) — it does not replace a "
                 "full point-factor job evaluation against skills, effort, responsibility and "
                 "working conditions, which Art. 4 requires and which needs data this tool "
                 "does not currently collect. Treat a significant grade-assignment gap as reason "
                 "to commission that fuller evaluation, not as proof on its own.")
    notes.extend(_reporting_duty_notes(countries_present, n_total))

    # ── country, said plainly ────────────────────────────────────────────
    #
    # This block exists because of a measured result, not a theory. On a
    # synthetic roster built to be gender-blind INSIDE each country (+0.8% NL,
    # +0.7% PL), pooling the Netherlands and Poland produced a 27.0% adjusted
    # gap, reported as statistically significant, with nothing anywhere saying
    # "these are two pay markets". The directive's joint-pay-assessment trigger
    # is 5%, so that number could start a formal remediation process over an
    # artefact of who happens to work where.
    if multi_country:
        notes.extend(_currency_notes(countries_present))
        notes.append(
            f"This workforce spans {len(countries_present)} countries "
            f"({', '.join(countries_present)}). Pay is set per market, so the "
            f"HEADLINE mean and median gaps above pool different pay levels and "
            f"should not be read as a pay-fairness finding, nor reported under "
            f"the directive, which is a per-country obligation. The ADJUSTED gap "
            f"controls for country and is the only figure here comparable "
            f"across the group. Analyse each country separately for anything "
            f"you intend to act on or file.")
    elif country_col and not countries_present:
        notes.append(
            "A country column was supplied but no row carried a usable value, so "
            "the analysis treats this workforce as a single pay market. If it is "
            "not one, the gaps below mix pay levels.")
    elif not country_col:
        notes.append(
            "No country column was supplied, so this is analysed as ONE pay "
            "market. That is right for a single-country workforce and wrong for "
            "a multinational one, where a gap can be produced entirely by which "
            "country people work in.")

    return PayGapResult(
        n=n_total, n_m=n_m, n_f=n_f, n_excluded=n_excluded,
        n_input=n_input, n_dropped_invalid=n_dropped_invalid,
        mean_gap_pct=mean_gap, median_gap_pct=median_gap,
        adjusted_gap_pct=adj_gap, adjusted_ci=adj_ci, adjusted_significant=adj_sig,
        adjusted_controls_used=adj_controls,
        grade_gap_levels=grade_gap, grade_gap_ci=grade_gap_ci, grade_gap_significant=grade_gap_sig,
        cohorts=cohorts, n_cohorts_tested=len(cohorts),
        n_cohorts_flagged=n_flagged, n_cohorts_flagged_reliable=n_flagged_reliable,
        pct_women_overall=pct_women_overall,
        women_by_level=_pct_women("_lvl"), women_by_function=_pct_women("_fun"),
        fte_normalised=fte_normalised, single_gender_levels=single_gender_levels,
        countries=countries_present, country_controlled=("country" in adj_controls),
        notes=notes,
    )


# ──────────────────────────────────────────────── variable-pay exposure ──
#
# The gap above is measured on ONE salary column. Under the Pay Transparency
# Directive "pay" is basic pay plus its complementary and variable components,
# and the gap in those components is reportable in its own right — a gap can sit
# entirely in who is eligible for a bonus rather than in anyone's base.
#
# The compa-ratio view already reports total-pay and variable-pay gaps when a
# client hands over bonus/allowance/LTI columns. Most cannot. What every client
# does have, the moment their grid is leveled, is a Function x Level per person
# — and the reference library's PayMix sheet states, for exactly that key, what
# variable pay the policy ENTITLES that cohort to. Its (Function, Level) grain
# is the same one this module already groups cohorts by, so it joins directly.
#
# So this answers a question needing no pay data at all: is entitlement to
# variable pay distributed evenly between men and women? That is structural,
# measurable today, and where the Directive's "proportion of workers receiving
# complementary or variable components" actually lives.
#
# What it is NOT: a measurement of variable pay received. PayMix is policy —
# target percentages, not anyone's bonus. Every figure here is what the scheme
# promises and must be reported that way. The implied-total gap is what the
# structure produces if everyone is paid exactly on target; its distance from
# the base gap is attributable to the STRUCTURE, which is the part a client can
# actually redesign.


@dataclass(frozen=True)
class ExposureCohort:
    function: str
    level: str
    n_m: int
    n_f: int
    target_variable_pct: float
    thirteenth_month_pct: float
    lti_eligible: bool


@dataclass(frozen=True)
class VariablePayExposure:
    n: int
    n_matched: int                        # rows whose (function, level) found a PayMix row
    n_unmatched: int
    unmatched_keys: list[tuple[str, str]]

    # Access to long-term incentive. PayMix records eligibility but not value,
    # so this is reported as access and never as an amount.
    pct_women_lti_eligible: float | None
    pct_men_lti_eligible: float | None
    lti_access_gap_pp: float | None        # + = men more likely to be eligible

    # Target variable entitlement, weighted by where people actually sit
    mean_target_var_m: float | None
    mean_target_var_f: float | None
    target_var_gap_pp: float | None        # + = men entitled to more

    # What the structure does to the gap
    base_mean_gap_pct: float | None
    implied_total_mean_gap_pct: float | None
    widening_pp: float | None              # + = variable pay WIDENS the gap

    cohorts: list[ExposureCohort]
    notes: list[str]

    @property
    def structure_widens_gap(self) -> bool:
        return bool(self.widening_pp is not None and self.widening_pp > 0)


def _paymix_frame(pay_mix) -> pd.DataFrame:
    """The typed PayMix entries as the frame this analysis works in.

    PayMix used to arrive here as a raw DataFrame that the page fetched itself.
    Since it joined the library it is typed on the Repository, and one fact
    reachable two ways is how the two halves of a screen end up disagreeing —
    so the typed record is now the only route and the frame is built
    here, at the edge, where the pandas work actually happens.
    """
    if isinstance(pay_mix, pd.DataFrame):
        return pay_mix
    return pd.DataFrame([{
        "Function": e.function,
        "Level": e.level,
        "TargetVariablePct": e.target_variable_pct,
        "ThirteenthMonthPct": e.thirteenth_month_pct,
        "LTIEligible": e.lti_eligible_text,
    } for e in (pay_mix or {}).values()])


def analyze_variable_pay_exposure(
    df: pd.DataFrame,
    paymix,
    *,
    function_col: str,
    level_col: str,
    gender_col: str,
    salary_col: str,
    fte_col: str | None = None,
    male_label: str = "M",
    female_label: str = "F",
    salary_already_fte: bool = False,
) -> VariablePayExposure:
    """
    Structural exposure to variable pay, from a leveled grid + the PayMix policy.

    ``paymix`` is the Repository's typed pay_mix — {(function, level): PayMixEntry}.
    A DataFrame is still accepted so a caller holding raw sheets is not broken,
    but the typed record is the route the product uses.

    Returns entitlement by gender and the gap the pay STRUCTURE produces on top
    of base pay. No bonus data is required, and none is inferred to exist.
    """
    notes: list[str] = []

    d = df[[c for c in {function_col, level_col, gender_col, salary_col, fte_col} if c]].copy()
    d["_sal"] = pd.to_numeric(d[salary_col], errors="coerce")
    if not salary_already_fte and fte_col:
        fte = pd.to_numeric(d[fte_col], errors="coerce")
        d["_sal"] = np.where(fte > 0, d["_sal"] / fte, d["_sal"])

    d["_fun"] = d[function_col].astype(str).str.strip()
    d["_lvl"] = d[level_col].astype(str).str.strip()
    # Same normalisation as analyze_gender_pay_gap, including the Dutch M/V fold.
    # A file that analyses natively there must analyse natively here, or the two
    # numbers on one screen would be computed over different populations.
    m_lab = male_label.strip().upper()[:1]
    f_lab = female_label.strip().upper()[:1]
    d["_g"] = d[gender_col].astype(str).str.strip().str.upper().str[:1]
    d["_g"] = d["_g"].apply(lambda g: f_lab if g in ("F", "V") else (m_lab if g == "M" else g))

    d = d[d["_sal"].notna() & (d["_sal"] > 0) & (d["_fun"] != "") & (d["_lvl"] != "")]
    n = len(d)

    pm = _paymix_frame(paymix).copy()
    pm.columns = [str(c).strip() for c in pm.columns]
    if not {"Function", "Level"}.issubset(pm.columns):
        raise ValueError("PayMix must carry Function and Level columns")
    pm["_fun"] = pm["Function"].astype(str).str.strip()
    pm["_lvl"] = pm["Level"].astype(str).str.strip()
    # pm.get() on an ABSENT column returns None, and pd.to_numeric(None) is a
    # bare scalar with no .fillna -- an AttributeError that took the whole page
    # down for a client whose reference library is still being filled in. The
    # very next line already guards exactly this for LTIEligible.
    def _pm_num(col: str) -> pd.Series:
        if col not in pm.columns:
            return pd.Series([np.nan] * len(pm), index=pm.index)
        return pd.to_numeric(pm[col], errors="coerce")

    # Left as NaN rather than filled with 0.0. A blank target-variable cell is
    # an unknown bonus, not a zero one, and this module already argues that for
    # a wholly missing PayMix row ("excluded and named ... unknown, not zero").
    # Filling it manufactured a variable-pay gap out of a data-entry hole in the
    # reference library.
    pm["_tv"] = _pm_num("TargetVariablePct")
    pm["_13"] = _pm_num("ThirteenthMonthPct")
    _lti_raw = pm["LTIEligible"] if "LTIEligible" in pm.columns else pd.Series([""] * len(pm))
    pm["_lti"] = _lti_raw.astype(str).str.strip().str.lower().isin(["yes", "y", "true", "1", "ja"])
    # An explicit join indicator. "matched" means the PayMix key was FOUND --
    # a different question from whether any particular figure on that row is
    # filled in. The two were conflated: `matched` was read off _tv.notna(),
    # which only ever worked because _tv was force-filled with 0.0, so an
    # unknown bonus and a missing cohort were the same value. Separating them is
    # what lets a blank TargetVariablePct be honestly unknown without throwing
    # away the LTI and thirteenth-month facts on the same row.
    pm["_pm_hit"] = True
    pm = pm.drop_duplicates(subset=["_fun", "_lvl"], keep="first")

    merged = d.merge(pm[["_fun", "_lvl", "_tv", "_13", "_lti", "_pm_hit"]],
                     on=["_fun", "_lvl"], how="left")
    matched = merged["_pm_hit"].fillna(False).astype(bool)
    # An absent COLUMN and a blank CELL are different facts and get different
    # treatment. No TargetVariablePct column at all means the metric is
    # unavailable for everybody -- a property of the workbook, not of any
    # cohort, so nobody is singled out as unmatched. A column that exists with
    # this one cohort's cell empty means THAT cohort's entitlement is unknown,
    # and it is named in unmatched_keys so somebody can go and fill it in --
    # rather than being read as a genuine 0% bonus, which manufactures a
    # variable-pay gap out of a hole in the reference library.
    if "TargetVariablePct" in pm.columns:
        matched &= merged["_tv"].notna()
    n_matched = int(matched.sum())
    n_unmatched = int(n - n_matched)
    # zip, not itertuples: itertuples renames any column whose name starts with
    # an underscore to a positional _1/_2, and every working column here does.
    _um = merged[~matched]
    unmatched_keys = sorted(set(zip(_um["_fun"], _um["_lvl"])))
    if n_unmatched:
        # Treating an unmatched cohort as zero-variable would manufacture a gap
        # out of a mapping failure, so they are excluded and named instead.
        notes.append(
            f"{n_unmatched} of {n} row(s) sit in a Function x Level with no PayMix entry "
            f"({', '.join(f'{f}/{l}' for f, l in unmatched_keys[:6])}"
            f"{chr(8230) if len(unmatched_keys) > 6 else ''}) and are excluded from every figure "
            "below — their entitlement is unknown, not zero.")

    e = merged[matched]
    men, women = e[e["_g"] == m_lab], e[e["_g"] == f_lab]

    if len(men) < SMALL_N or len(women) < SMALL_N:
        notes.append(f"Fewer than {SMALL_N} of one gender with a known entitlement — exposure "
                     "figures are suppressed as unreliable and re-identifying.")
        return VariablePayExposure(
            n=n, n_matched=n_matched, n_unmatched=n_unmatched, unmatched_keys=unmatched_keys,
            pct_women_lti_eligible=None, pct_men_lti_eligible=None, lti_access_gap_pp=None,
            mean_target_var_m=None, mean_target_var_f=None, target_var_gap_pp=None,
            base_mean_gap_pct=None, implied_total_mean_gap_pct=None, widening_pp=None,
            cohorts=[], notes=notes)

    pct_m_lti = float(men["_lti"].mean() * 100)
    pct_f_lti = float(women["_lti"].mean() * 100)
    mean_tv_m = float(men["_tv"].mean())
    mean_tv_f = float(women["_tv"].mean())

    # Implied total = base + on-target variable + 13th month. Holiday allowance
    # is a flat statutory 8% of base for everyone, so it scales both genders
    # identically and cannot move a percentage gap — leaving it out keeps this
    # about the components that actually differ between cohorts.
    e = e.assign(_total=e["_sal"] * (1 + e["_tv"] / 100.0 + e["_13"] / 100.0))
    base_gap = _gap_pct(float(men["_sal"].mean()), float(women["_sal"].mean()))
    total_gap = _gap_pct(float(e[e["_g"] == m_lab]["_total"].mean()),
                         float(e[e["_g"] == f_lab]["_total"].mean()))
    widening = (None if base_gap is None or total_gap is None else round(total_gap - base_gap, 2))

    if widening is not None and widening > 0:
        notes.append(
            f"The pay structure adds {widening:.1f} percentage point(s) to the base-pay gap before "
            "any individual bonus is considered: men sit in cohorts entitled to more variable pay. "
            "That is a property of the scheme's design, not of individual pay decisions.")
    elif widening is not None and widening < 0:
        notes.append(f"The pay structure narrows the base-pay gap by {abs(widening):.1f} percentage "
                     "point(s): women sit in cohorts entitled to more variable pay.")

    if pct_m_lti > 0 or pct_f_lti > 0:
        notes.append(
            f"Long-term incentive eligibility: {pct_f_lti:.0f}% of women and {pct_m_lti:.0f}% of men "
            "sit in an eligible cohort. PayMix records eligibility but not value, so this is access "
            "only — the size of any LTI gap cannot be stated from policy alone.")

    cohorts = [
        ExposureCohort(
            function=fn, level=lv,
            n_m=int((grp["_g"] == m_lab).sum()), n_f=int((grp["_g"] == f_lab).sum()),
            target_variable_pct=float(grp["_tv"].iloc[0]),
            thirteenth_month_pct=float(grp["_13"].iloc[0]),
            lti_eligible=bool(grp["_lti"].iloc[0]))
        for (fn, lv), grp in e.groupby(["_fun", "_lvl"])
    ]
    cohorts.sort(key=lambda c: (-c.target_variable_pct, c.function, c.level))

    notes.append("Every figure here is POLICY ENTITLEMENT from the reference library's PayMix, not "
                 "variable pay received. To measure the actual variable-pay gap the Directive asks "
                 "for, supply bonus / allowance / LTI columns with the employee data.")

    return VariablePayExposure(
        n=n, n_matched=n_matched, n_unmatched=n_unmatched, unmatched_keys=unmatched_keys,
        pct_women_lti_eligible=round(pct_f_lti, 1), pct_men_lti_eligible=round(pct_m_lti, 1),
        lti_access_gap_pp=round(pct_m_lti - pct_f_lti, 1),
        mean_target_var_m=round(mean_tv_m, 2), mean_target_var_f=round(mean_tv_f, 2),
        target_var_gap_pp=round(mean_tv_m - mean_tv_f, 2),
        base_mean_gap_pct=base_gap, implied_total_mean_gap_pct=total_gap, widening_pp=widening,
        cohorts=cohorts, notes=notes)

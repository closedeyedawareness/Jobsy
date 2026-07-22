"""
jobsy/services/special_conditions_service.py

Reads a free-text "special conditions" column some Dutch payroll exports carry
(often an UNLABELED trailing column) and turns two specific notations into
structured, gender-cross-tabbed reasoning for the pay-equity engine:

  * Shift-work percentage toeslag -- "2 ploeg 13,3%", "3 ploeg 21%". A
    ploeg-rooster (shift rota) toeslag is legitimate extra pay for unsocial
    hours, not unequal pay for equal work BY ITSELF -- but whether it is
    already folded into the salary column supplied, or sits on top of it,
    changes what the headline gap number means. We can't tell from the
    numbers alone (verified: ratios of tagged rows to same-category peers
    scatter 0.85-1.21x, no consistent premium or discount pattern) --
    so this reports a SENSITIVITY (gap with vs without those rows) instead
    of silently assuming either reading.

  * Generatiepact ("generation pact") -- an older worker works reduced hours
    for a smaller pay cut and full pension accrual, canonically phrased
    "80-90-100" (80% hours, 90% pay, 100% pension). Whether the salary
    column reflects the discounted actual pay or a grossed-back-up nominal
    full-time rate is likewise unverifiable from the numbers alone -- same
    sensitivity treatment.

Both are ANALYTICAL REASONING AIDS: they never silently change the headline
pay-gap number. They add a same-page sensitivity view plus explicit risk
flags and next steps so the client (and the analyst) can see exactly how
much these two mechanisms could move the answer, and what to go verify.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from services.pay_equity_service import analyze_gender_pay_gap

_PLOEG_RE = re.compile(r"(\d+)\s*ploeg\D{0,12}([\d]+(?:[.,]\d+)?)\s*%", re.IGNORECASE)
_GENPACT_RE = re.compile(
    r"generatiepact\D{0,10}(\d+)\D{1,5}(\d+)\D{1,5}(\d+)", re.IGNORECASE)
_GENPACT_BARE_RE = re.compile(r"generatiepact", re.IGNORECASE)

# Keywords used to auto-detect WHICH column carries this free text -- the
# source template often leaves this column's header blank (pandas surfaces
# it as "Unnamed: N"), so header-name matching alone would miss it.
_DETECT_KEYWORDS = ("ploeg", "generatiepact", "toeslag")


@dataclass(frozen=True)
class RowConditions:
    shift_ploeg_count: int | None = None      # 2 or 3 (ploegen/shift rota size)
    shift_toeslag_pct: float | None = None    # e.g. 13.3
    generatiepact: bool = False
    gp_work_pct: float | None = None          # e.g. 80
    gp_pay_pct: float | None = None           # e.g. 90
    gp_pension_pct: float | None = None       # e.g. 100
    raw_note: str = ""


def parse_condition(note) -> RowConditions:
    """Parse one free-text cell. Unrecognised / blank text -> all-empty result."""
    text = "" if note is None or (isinstance(note, float) and pd.isna(note)) else str(note).strip()
    if not text:
        return RowConditions()

    m = _PLOEG_RE.search(text)
    ploeg_n = int(m.group(1)) if m else None
    ploeg_pct = float(m.group(2).replace(",", ".")) if m else None

    is_gp = bool(_GENPACT_BARE_RE.search(text))
    gm = _GENPACT_RE.search(text)
    gp_work = gp_pay = gp_pension = None
    if gm:
        gp_work, gp_pay, gp_pension = (float(gm.group(i)) for i in (1, 2, 3))

    return RowConditions(
        shift_ploeg_count=ploeg_n, shift_toeslag_pct=ploeg_pct,
        generatiepact=is_gp, gp_work_pct=gp_work, gp_pay_pct=gp_pay,
        gp_pension_pct=gp_pension, raw_note=text,
    )


def detect_conditions_column(df: pd.DataFrame) -> str | None:
    """
    Best-effort column detection for an unlabeled/loosely-labeled free-text
    conditions column: pick the column (by header hint or by keyword hits in
    its own values) with the most ploeg/generatiepact/toeslag matches.
    """
    best_col, best_hits = None, 0
    for col in df.columns:
        header_hint = any(k in str(col).lower() for k in ("bijzonder", "toelichting", "note", "opmerking"))
        vals = df[col].astype(str).str.lower()
        hits = sum(vals.str.contains(k, na=False).sum() for k in _DETECT_KEYWORDS)
        if hits > 0 and (hits > best_hits or (header_hint and hits >= best_hits)):
            best_col, best_hits = col, hits
    return best_col


@dataclass(frozen=True)
class ScenarioGap:
    label: str
    n: int
    n_m: int
    n_f: int
    mean_gap_pct: float | None
    adjusted_gap_pct: float | None


@dataclass(frozen=True)
class SpecialConditionsReport:
    conditions_col: str | None
    n_shift_tagged: int
    n_shift_tagged_m: int
    n_shift_tagged_f: int
    n_generatiepact: int
    n_generatiepact_m: int
    n_generatiepact_f: int
    generatiepact_peer_ratio_range: tuple[float, float] | None  # (min, max) vs same cat+function peers
    scenarios: tuple[ScenarioGap, ...]
    risk_flags: tuple[str, ...]
    next_steps: tuple[str, ...]


def analyze_special_conditions(
    df: pd.DataFrame, *, function_col: str, level_col: str, gender_col: str, salary_col: str,
    conditions_col: str | None = None, fte_col: str | None = None, tenure_col: str | None = None,
    male_label: str = "M", female_label: str = "F", salary_already_fte: bool = False,
) -> SpecialConditionsReport | None:
    """
    Parses the conditions column (auto-detected if not given) and reruns the
    gender-pay-gap engine under four scenarios so the client sees, in one
    place, how much shift-toeslag and generatiepact rows could be moving the
    headline number -- without ever silently deciding the answer for them.
    Returns None if no conditions column can be found (nothing to report).
    """
    col = conditions_col or detect_conditions_column(df)
    if not col:
        return None

    parsed = df[col].apply(parse_condition)
    is_shift = parsed.apply(lambda c: c.shift_ploeg_count is not None)
    is_gp = parsed.apply(lambda c: c.generatiepact)
    g = df[gender_col].astype(str).str.strip().str.upper().str[:1]
    is_f = g.isin((female_label.strip().upper()[:1], "V"))
    is_m = g.isin((male_label.strip().upper()[:1],))

    def _run(mask) -> ScenarioGap | None:
        sub = df[mask]
        if sub[gender_col].nunique() < 1 or len(sub) < 4:
            return None
        try:
            r = analyze_gender_pay_gap(
                sub, function_col=function_col, level_col=level_col, gender_col=gender_col,
                salary_col=salary_col, fte_col=fte_col, tenure_col=tenure_col,
                male_label=male_label, female_label=female_label, salary_already_fte=salary_already_fte,
            )
        except Exception:
            return None
        return ScenarioGap("", len(sub), r.n_m, r.n_f, r.mean_gap_pct, r.adjusted_gap_pct)

    all_mask = pd.Series(True, index=df.index)
    excl_shift = ~is_shift
    excl_gp = ~is_gp
    excl_both = (~is_shift) & (~is_gp)

    scenarios = []
    for label, mask in [
        ("All rows (as supplied)", all_mask),
        ("Excluding shift-toeslag rows", excl_shift),
        ("Excluding generatiepact rows", excl_gp),
        ("Excluding both", excl_both),
    ]:
        r = _run(mask)
        if r is not None:
            scenarios.append(ScenarioGap(label, r.n, r.n_m, r.n_f, r.mean_gap_pct, r.adjusted_gap_pct))

    # Peer-ratio sanity check for generatiepact rows (same category + function,
    # untagged peers) -- reported as a range so a reader sees there is NO
    # consistent premium or discount, hence no safe assumption either way.
    gp_ratios: list[float] = []
    if is_gp.any():
        gp_rows = df[is_gp]
        untagged = df[~is_shift & ~is_gp]
        for _, row in gp_rows.iterrows():
            peers = untagged[(untagged[level_col] == row[level_col]) & (untagged[function_col] == row[function_col])]
            if len(peers) and pd.notna(row[salary_col]):
                med = peers[salary_col].median()
                if med:
                    gp_ratios.append(float(row[salary_col]) / float(med))
    ratio_range = (round(min(gp_ratios), 2), round(max(gp_ratios), 2)) if gp_ratios else None

    n_shift, n_shift_m, n_shift_f = int(is_shift.sum()), int((is_shift & is_m).sum()), int((is_shift & is_f).sum())
    n_gp, n_gp_m, n_gp_f = int(is_gp.sum()), int((is_gp & is_m).sum()), int((is_gp & is_f).sum())

    risk: list[str] = []
    steps: list[str] = []

    if n_shift:
        skew = "men" if n_shift_m > n_shift_f else ("women" if n_shift_f > n_shift_m else None)
        risk.append(
            f"Shift-work (ploeg) toeslag tagged on {n_shift} row(s) ({n_shift_m} M, {n_shift_f} F)"
            + (f" — heavily skewed toward {skew}." if skew and max(n_shift_m, n_shift_f) >= 3 * max(1, min(n_shift_m, n_shift_f)) else ".")
            + " Whether the toeslag is already included in the salary column or sits on top of it "
              "changes what the headline gap means, and the data can't settle this on its own."
        )
        steps.append(
            "Confirm with payroll/HR whether the shift (ploeg) toeslag is already included in the "
            "supplied salary figure, or paid on top of it. If it's on top and skewed toward one "
            "gender, the true total-compensation gap differs from the base-salary gap shown here."
        )
        steps.append(
            "Separately worth asking: who is ASSIGNED shift rosters and who is not — if eligibility "
            "for shift work (and its toeslag) itself skews by gender, that's a distinct equity question "
            "from pay-for-equal-work."
        )

    if n_gp:
        risk.append(
            f"Generatiepact (generation-pact reduced-hours scheme) tagged on {n_gp} row(s), "
            f"all {'male' if n_gp_m == n_gp else f'{n_gp_m} M / {n_gp_f} F'}."
            + (f" Peer-salary ratio for these rows ranges {ratio_range[0]}–{ratio_range[1]}x same "
               "category+function untagged peers — no consistent premium or discount, so whether "
               "the pay-cushion (typically ~90% pay for ~80% hours) is already netted into the "
               "supplied salary can't be inferred from the numbers." if ratio_range else "")
        )
        steps.append(
            "Confirm with HR whether 'FT salaris' for generatiepact employees reflects their actual "
            "discounted pay grossed back up by FTE (which would embed the pact's pay cushion as an "
            "artificial premium), or a true full-time nominal rate. This affects only a handful of "
            "rows but they sit disproportionately in one gender, so it's worth resolving before citing "
            "a headline number to the client."
        )

    if n_gp and gp_ratios:
        pass  # ratio detail already folded into the risk line above

    if not risk:
        risk.append("No shift-toeslag or generatiepact rows detected in the conditions column — "
                     "this reasoning doesn't apply to this file.")

    return SpecialConditionsReport(
        conditions_col=col,
        n_shift_tagged=n_shift, n_shift_tagged_m=n_shift_m, n_shift_tagged_f=n_shift_f,
        n_generatiepact=n_gp, n_generatiepact_m=n_gp_m, n_generatiepact_f=n_gp_f,
        generatiepact_peer_ratio_range=ratio_range,
        scenarios=tuple(scenarios), risk_flags=tuple(risk), next_steps=tuple(steps),
    )

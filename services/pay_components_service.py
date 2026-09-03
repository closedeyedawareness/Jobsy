"""
pay_components_service.py — what total remuneration is made of, from the library.

Three pages priced total reward, and all three did it with literals:

    base * (1 + 0.08 + th_pct/100 + var_pct/100) + base * 0.12 + 2000

The 8% is the statutory holiday allowance, which the library states in
PayElements as `PE-HOL: "8%"`. The 0.12 is pension, which the library states as
`PE-PENS: "~10-15% (indicative)"` — a range, so 12 was a point estimate nobody
had made. The 2000 is other benefits, which the library states as
`PE-BEN: "varies"` — that is, no figure at all.

So the calculation and the library disagreed, quietly, in a money figure. This
module makes the composition one chain: every term names the row it came from,
and a term the library refuses to state as a number is reported as excluded
rather than filled in.

**A range stays a range.** `compose()` returns a point total for the cash a
cohort is entitled to — base, holiday, thirteenth month, on-target variable,
each with a stated source — and a low/high band for anything the library gives
as a range. There is no midpoint anywhere in this file. Taking one is the
decision that produced the 12.

**Zero is not unknown.** A cohort with no PayMix row has no stated variable-pay
entitlement. That component comes back `computable=False` with the reason, not
as 0.0, because a page that adds zero shows a number and a page that shows the
reason shows the truth.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

__all__ = ["Rate", "Component", "TotalReward", "parse_rate", "rate_for_element",
           "compose", "statutory_elements", "statutory_coverage"]

#: Element ids the composition asks for by name. The library may hold more.
HOLIDAY = "PE-HOL"
THIRTEENTH = "PE-13"
VARIABLE = "PE-VAR"
PENSION = "PE-PENS"
OTHER_BENEFITS = "PE-BEN"
LTI = "PE-LTI"

_PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_RANGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%\s*)?(?:-|–|—|to|tot)\s*(\d+(?:[.,]\d+)?)\s*%")
_APPROX = re.compile(r"[~≈]|\bca\.?\b|\bcirca\b|\bapprox", re.I)


@dataclass(frozen=True)
class Rate:
    """A percentage the library states — or a stated refusal to give one.

    `pct` is set only when the text carries exactly one unambiguous percentage.
    A range fills `low`/`high` and leaves `pct` None, because turning "10-15%"
    into 12.5 is an estimate, and an estimate that arrives as a plain number
    cannot be told apart from a measurement further down the page.
    """
    pct: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    approximate: bool = False
    text: str = ""
    reason: str = ""

    @property
    def is_point(self) -> bool:
        return self.pct is not None

    @property
    def is_range(self) -> bool:
        return self.low is not None and self.high is not None

    @property
    def is_stated(self) -> bool:
        return self.is_point or self.is_range


def parse_rate(text) -> Rate:
    """Read a percentage out of a TypicalValue, or say why there isn't one.

    The column is free text by design: '8%', '8.33% (~1 month)', '0-40% by
    role', '~10-15% (indicative)', '100% of pay reference', 'varies'.
    """
    raw = ("" if text is None else str(text)).strip()
    if not raw:
        return Rate(text=raw, reason="the library states no value")

    approximate = bool(_APPROX.search(raw))

    span = _RANGE.search(raw)
    if span:
        low, high = (float(v.replace(",", ".")) for v in span.groups())
        if low > high:
            low, high = high, low
        return Rate(low=low, high=high, approximate=approximate, text=raw,
                    reason="the library states a range, not a rate")

    found = {float(v.replace(",", ".")) for v in _PCT.findall(raw)}
    if len(found) == 1:
        return Rate(pct=found.pop(), approximate=approximate, text=raw)
    if len(found) > 1:
        return Rate(text=raw, reason=f"the library states {len(found)} percentages, "
                                     f"and which one applies is not said")
    return Rate(text=raw, reason="the library states no percentage")


def rate_for_element(repo, element_id: str) -> tuple[Rate, str]:
    """The rate for one PayElement, with the citation to print beside it."""
    element = (getattr(repo, "pay_elements", None) or {}).get(element_id)
    if element is None:
        return (Rate(reason=f"{element_id} is not in the library"),
                f"PayElements {element_id} — absent")
    rate = parse_rate(element.typical_value)
    return rate, f'PayElements {element_id} "{element.typical_value}"'


@dataclass
class Component:
    """One line of the composition, and where its number came from."""
    key: str
    label: str
    source: str
    element_id: str = ""
    pct: Optional[float] = None
    amount: Optional[float] = None
    low_pct: Optional[float] = None
    high_pct: Optional[float] = None
    low_amount: Optional[float] = None
    high_amount: Optional[float] = None
    statutory: bool = False
    reason: str = ""

    @property
    def computable(self) -> bool:
        return self.amount is not None

    @property
    def ranged(self) -> bool:
        return self.low_amount is not None and self.high_amount is not None


@dataclass
class TotalReward:
    """What one cohort's package is worth, and what could not be priced."""
    base: float
    function: str
    level: str
    components: list[Component] = field(default_factory=list)
    excluded: list[Component] = field(default_factory=list)
    lti_eligible: Optional[bool] = None
    lti_note: str = ""

    @property
    def total_target_cash(self) -> float:
        """Base plus every component the library states as a rate."""
        return self.base + sum(c.amount for c in self.components if c.computable)

    @property
    def total_reward_low(self) -> float:
        return self.total_target_cash + sum(c.low_amount for c in self.components if c.ranged)

    @property
    def total_reward_high(self) -> float:
        return self.total_target_cash + sum(c.high_amount for c in self.components if c.ranged)

    @property
    def is_range(self) -> bool:
        return any(c.ranged for c in self.components)

    def basis(self) -> str:
        """One sentence naming what is in the figure and what is not."""
        named = ", ".join(c.label.lower() for c in self.components
                          if c.computable or c.ranged)
        text = f"Base plus {named}." if named else "Base only."
        if self.excluded:
            text += (" Not included: "
                     + "; ".join(f"{c.label.lower()} ({c.reason})" for c in self.excluded)
                     + ".")
        return text


def compose(base: float, function: str, level: str, repo) -> TotalReward:
    """Price one cohort's entitlement, every term sourced.

    PayMix is the authority for the cohort-specific rates (variable pay, and the
    thirteenth month where it is set per Function x Level); PayElements supplies
    the rates that apply across the board and names what cannot be priced.
    """
    out = TotalReward(base=float(base), function=str(function), level=str(level))
    mix = (getattr(repo, "pay_mix", None) or {}).get((str(function), str(level)))

    # ── holiday allowance: statutory, one rate, from the library ─────────────
    rate, cite = rate_for_element(repo, HOLIDAY)
    element = (getattr(repo, "pay_elements", None) or {}).get(HOLIDAY)
    holiday = Component(key="holiday", label="Holiday allowance", element_id=HOLIDAY,
                        source=cite, statutory=bool(element and element.is_statutory))
    if rate.is_point:
        holiday.pct = rate.pct
        holiday.amount = out.base * rate.pct / 100
        out.components.append(holiday)
    else:
        holiday.reason = rate.reason
        out.excluded.append(holiday)

    # ── thirteenth month: PayMix per cohort, else the library's typical ──────
    thirteenth = Component(key="thirteenth", label="Thirteenth month", element_id=THIRTEENTH,
                           source="")
    if mix is not None and mix.thirteenth_month_pct:
        thirteenth.pct = mix.thirteenth_month_pct
        thirteenth.amount = out.base * thirteenth.pct / 100
        thirteenth.source = f"PayMix {function}/{level} — {thirteenth.pct}%"
        out.components.append(thirteenth)
    else:
        rate, cite = rate_for_element(repo, THIRTEENTH)
        thirteenth.source = cite + (" (no PayMix rate for this cohort)" if mix is not None
                                    else " (no PayMix row for this cohort)")
        if rate.is_point:
            thirteenth.pct = rate.pct
            thirteenth.amount = out.base * rate.pct / 100
            out.components.append(thirteenth)
        else:
            thirteenth.reason = rate.reason
            out.excluded.append(thirteenth)

    # ── on-target variable: PayMix only. It is a cohort fact, not a typical ──
    variable = Component(key="variable", label="On-target variable", element_id=VARIABLE,
                         source=f"PayMix {function}/{level}")
    if mix is None:
        variable.reason = "no PayMix row for this Function x Level, so the entitlement is unknown"
        variable.source = "PayMix — no row"
        out.excluded.append(variable)
    else:
        variable.pct = mix.target_variable_pct
        variable.amount = out.base * variable.pct / 100
        variable.source = f"PayMix {function}/{level} — {variable.pct}%"
        out.components.append(variable)

    # ── pension: the library gives a range, so the total gets a range ────────
    rate, cite = rate_for_element(repo, PENSION)
    pension = Component(key="pension", label="Employer pension", element_id=PENSION, source=cite)
    if rate.is_range:
        pension.low_pct, pension.high_pct = rate.low, rate.high
        pension.low_amount = out.base * rate.low / 100
        pension.high_amount = out.base * rate.high / 100
        out.components.append(pension)
    elif rate.is_point:
        pension.pct = rate.pct
        pension.amount = out.base * rate.pct / 100
        out.components.append(pension)
    else:
        pension.reason = rate.reason
        out.excluded.append(pension)

    # ── other benefits: 'varies'. Nothing to add, and that is the finding ────
    rate, cite = rate_for_element(repo, OTHER_BENEFITS)
    other = Component(key="benefits", label="Other benefits", element_id=OTHER_BENEFITS,
                      source=cite, reason=rate.reason)
    if rate.is_point:
        other.pct = rate.pct
        other.amount = out.base * rate.pct / 100
        out.components.append(other)
    else:
        out.excluded.append(other)

    # ── LTI: eligibility, never a value ─────────────────────────────────────
    if mix is not None:
        out.lti_eligible = mix.lti_eligible
        out.lti_note = (f"PayMix {function}/{level} records LTI eligibility "
                        f"({'yes' if mix.lti_eligible else 'no'}) but no value, so it is not priced.")
    else:
        out.lti_note = "No PayMix row, so LTI eligibility is unknown."

    return out


def statutory_elements(repo) -> list:
    """The pay components the library marks as statutory in the Netherlands.

    'Partly (sector funds)' is not statutory and must not be reported as one —
    see PayElement.is_statutory.
    """
    return [e for e in (getattr(repo, "pay_elements", None) or {}).values() if e.is_statutory]


def statutory_coverage(repo, present: dict[str, bool]) -> list[tuple]:
    """Which statutory components an uploaded file carries, and which it does not.

    `present` maps element id to whether the client's file has a column for it.
    The answer is about the FILE, never about the employer: a missing column
    means the analysis cannot see that component, not that it was not paid.
    """
    out = []
    for element in statutory_elements(repo):
        out.append((element, bool(present.get(element.element_id))))
    return out

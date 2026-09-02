"""
salary_service.py — where a salary is placed against a band.

Everything about "is this person paid correctly for their role" lives here:
the compa-ratio, the position in the range, the status label, the industry
scaling of a band, and the accounting of who was left out of the figures.
Until now this arithmetic sat inline in ui/app.py, which is why the Pay Equity
page and the Architecture report could drift apart without anything noticing.

ONE DELIBERATE BEHAVIOUR CHANGE, 2026-09-03 — part-time pay is now pro-rated.

  The app promises it in two places on the Data Readiness panel: "FTE →
  pro-rate part-time pay — 1.0 / 0.8 etc. lets Pay Equity compare part-timers
  fairly", and, when the column is absent, "part-timers are compared to full
  bands, not pro-rated". The compa-ratio never kept that promise: it divided
  the *actual* salary by the band midpoint whatever the FTE said. Someone at
  0.6 FTE on a proportionate salary was reported Below range, in a tool people
  use to decide whether their pay is fair.

  `position()` therefore takes an explicit `fte` and compares full-time
  equivalents. Pass `fte=None` (or 1.0) for the old behaviour. The basis used
  is carried on the result so a report can state it rather than imply it.

The thresholds (0.9 / 1.1 around the midpoint, min/max for out-of-range) are
the ones the page has always used, unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: Below this compa-ratio, pay reads as under market for the role.
BELOW_MARKET = 0.9
#: Above this compa-ratio, pay reads as over market for the role.
ABOVE_MARKET = 1.1

BELOW_RANGE = "Below range"
ABOVE_RANGE = "Above range"
BELOW_MARKET_LABEL = "Below market"
ABOVE_MARKET_LABEL = "Above market"
AT_MARKET = "At market"
NO_MATCH = "No match"


def midpoint(band) -> Optional[float]:
    """The band's P50, or the midpoint of min/max when P50 is not filled in."""
    if band is None:
        return None
    p50 = getattr(band, "p50", None)
    if p50:
        return float(p50)
    lo, hi = getattr(band, "min", None), getattr(band, "max", None)
    if lo is None or hi is None:
        return None
    return round((float(lo) + float(hi)) / 2)


def full_time_pay(actual: Optional[float], fte: Optional[float]) -> Optional[float]:
    """Scale pay to a full-time equivalent. An FTE of 0 or None means unknown.

    A zero FTE is not full-time and it is not a divisor — in a real client file
    it usually means the row holds an hourly rate (this happened in the Colliers
    basis check). Left alone rather than divided by zero.
    """
    if actual is None:
        return None
    if not fte:
        return float(actual)
    return float(actual) / float(fte)


def compa_ratio(pay: Optional[float], band) -> Optional[float]:
    """Pay ÷ band midpoint, to two decimals. None when either side is unknown."""
    mid = midpoint(band)
    if pay is None or not mid:
        return None
    return round(float(pay) / mid, 2)


def range_penetration(pay: Optional[float], band) -> Optional[int]:
    """Where in the band the pay sits, 0 = min, 100 = max.

    Not clamped: a value outside 0–100 is exactly the out-of-range signal the
    Status carries, and clamping would flatten the two apart.
    """
    if pay is None or band is None:
        return None
    lo, hi = getattr(band, "min", None), getattr(band, "max", None)
    if lo is None or hi is None or hi <= lo:
        return None
    return round((float(pay) - float(lo)) / (float(hi) - float(lo)) * 100)


def band_status(pay: Optional[float], band) -> str:
    """The label the Pay Equity page colours by. Range beats market."""
    if pay is None or band is None:
        return NO_MATCH
    lo, hi = getattr(band, "min", None), getattr(band, "max", None)
    if lo is not None and float(pay) < float(lo):
        return BELOW_RANGE
    if hi is not None and float(pay) > float(hi):
        return ABOVE_RANGE
    ratio = compa_ratio(pay, band)
    if ratio is None:
        return NO_MATCH
    if ratio < BELOW_MARKET:
        return BELOW_MARKET_LABEL
    if ratio > ABOVE_MARKET:
        return ABOVE_MARKET_LABEL
    return AT_MARKET


@dataclass
class BandPosition:
    """One person against one band, with the basis of the comparison stated."""
    compa_ratio: Optional[float]
    range_penetration: Optional[int]
    status: str
    compared_pay: Optional[float]
    fte: Optional[float]
    pro_rated: bool
    band_min: Optional[int] = None
    band_p50: Optional[int] = None
    band_max: Optional[int] = None
    grade: Optional[str] = None

    @property
    def basis(self) -> str:
        return "full-time equivalent (base ÷ FTE)" if self.pro_rated else "actual pay as supplied"


def position(actual: Optional[float], band, fte: Optional[float] = None) -> BandPosition:
    """Place one salary against one band.

    `fte` supplied and not 1.0 → the comparison is made full-time equivalent,
    because a band is a full-time band. Without it the actual figure is used
    and `pro_rated` says so.
    """
    if band is None or actual is None:
        return BandPosition(None, None, NO_MATCH, None, fte, False)

    pro_rated = bool(fte) and float(fte) != 1.0
    pay = full_time_pay(actual, fte) if pro_rated else float(actual)
    mid = midpoint(band)
    lo, hi = getattr(band, "min", None), getattr(band, "max", None)

    return BandPosition(
        compa_ratio=compa_ratio(pay, band),
        range_penetration=range_penetration(pay, band),
        status=band_status(pay, band),
        compared_pay=round(pay) if pay is not None else None,
        fte=fte,
        pro_rated=pro_rated,
        band_min=int(lo) if lo is not None else None,
        band_p50=int(mid) if mid is not None else None,
        band_max=int(hi) if hi is not None else None,
        grade=getattr(band, "grade", None) or None,
    )


def scale_band(band, factor: float):
    """A copy of the band with every money value scaled by an industry factor."""
    if band is None:
        return None
    if not factor or factor == 1.0:
        return band
    from core.models import SalaryBand
    return SalaryBand(
        function=band.function, level=band.level, grade=getattr(band, "grade", None),
        min=round(band.min * factor), max=round(band.max * factor),
        p25=round(band.p25 * factor), p50=round(band.p50 * factor),
        p75=round(band.p75 * factor), currency=band.currency,
    )


@dataclass
class Coverage:
    """Who reached the figures, and who silently did not.

    Excluded rows leave a pay analysis without trace unless something counts
    them, and a gap computed on an unstated subset is not a finding.
    """
    uploaded: int
    parsed: int
    priced: int

    @property
    def unparsed(self) -> int:
        return self.uploaded - self.parsed

    @property
    def unmatched(self) -> int:
        return self.parsed - self.priced

    def message(self) -> str:
        parts = []
        if self.unmatched:
            parts.append(f"{self.unmatched} no role match")
        if self.unparsed:
            parts.append(f"{self.unparsed} unparsed pay")
        msg = (f"Coverage: {self.priced} of {self.uploaded} uploaded employees "
               f"are included in the pay analysis")
        if parts:
            msg += " — excluded: " + ", ".join(parts)
        return msg + ". Excluded rows are left out of every figure below."

    def reconciles(self) -> bool:
        """The three counts must account for every uploaded row, or the message lies."""
        return self.priced + self.unmatched + self.unparsed == self.uploaded

"""
services/benefits_service.py

Employee Benefits Benchmarking.

Computes P25/P50/P75/P90 and the market median for a benefit category from
the self-built BenefitsObservations reference data (core/repository.py) —
percentiles are COMPUTED from raw data points at call time, the same way a
real survey vendor aggregates respondent data, rather than read from static
pre-set band columns (which is how SalaryBands/Pay Benchmarking works today).

Also compares a company's actual benefits package against that market
distribution (percentile rank, gap to median, status) and generates
rule-based advice, mirroring the pattern-detection style of
ArchitectureReportService._detect_patterns but for benefits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.models import BenefitBand

__all__ = ["BenefitComparison", "BenefitsService"]


@dataclass(frozen=True)
class BenefitComparison:
    category: str
    unit: str
    actual: float
    band: BenefitBand
    percentile_rank: float   # 0-100, share of market observations at/below actual
    status: str              # Below P25 / Below median / At market / Above P75 / Above P90
    gap_to_median: float     # actual - p50, same unit


class BenefitsService:
    """Computes benefit market bands, comparisons and advice from the reference library."""

    def __init__(self, catalog):
        self.catalog = catalog
        self.repo = catalog.repository

    # ── market data ──────────────────────────────────────────────────────
    def categories(self) -> list[str]:
        return list(self.repo.benefits_catalog.keys())

    def catalog_item(self, category: str):
        return self.repo.benefits_catalog.get(category)

    def get_band(self, category: str, industry_id: Optional[str],
                 level: Optional[str]) -> Optional[BenefitBand]:
        """P25/P50/P75/P90 computed from raw observations for (industry, category),
        scaled by the level factor. With no industry, pools all industries (national baseline)."""
        obs = self._observations(category, industry_id)
        if not obs:
            return None
        factor = self.repo.level_benefit_factors.get((level, category), 1.0) if level else 1.0
        values = pd.Series([o.value for o in obs]) * factor
        q = values.quantile([0.25, 0.5, 0.75, 0.9])
        return BenefitBand(
            category=category, industry_id=industry_id or "ALL", level=level or "ALL",
            unit=obs[0].unit,
            p25=round(float(q[0.25]), 2), p50=round(float(q[0.5]), 2),
            p75=round(float(q[0.75]), 2), p90=round(float(q[0.9]), 2),
            n_observations=len(obs),
        )

    def _observations(self, category: str, industry_id: Optional[str]):
        if industry_id:
            return self.repo.benefit_observations.get((industry_id, category), [])
        pooled = []
        for (_iid, cat), obs in self.repo.benefit_observations.items():
            if cat == category:
                pooled.extend(obs)
        return pooled

    def named_companies(self, category: str, industry_id: Optional[str]) -> list[str]:
        """Company names behind real (non-synthetic) observations for a band, if any."""
        obs = self._observations(category, industry_id)
        seen, names = set(), []
        for o in obs:
            if o.company_name and o.company_name not in seen:
                seen.add(o.company_name)
                names.append(o.company_name)
        return names

    # ── comparison vs. an actual package ─────────────────────────────────
    def compare(self, category: str, actual: float, industry_id: Optional[str],
                level: Optional[str]) -> Optional[BenefitComparison]:
        band = self.get_band(category, industry_id, level)
        if band is None:
            return None
        obs = self._observations(category, industry_id)
        factor = self.repo.level_benefit_factors.get((level, category), 1.0) if level else 1.0
        scaled = [o.value * factor for o in obs]
        rank = round(sum(1 for v in scaled if v <= actual) / len(scaled) * 100, 1) if scaled else 0.0
        if actual < band.p25:
            status = "Below P25"
        elif actual < band.p50:
            status = "Below median"
        elif actual <= band.p75:
            status = "At market"
        elif actual <= band.p90:
            status = "Above P75"
        else:
            status = "Above P90"
        return BenefitComparison(
            category=category, unit=band.unit, actual=actual, band=band,
            percentile_rank=rank, status=status, gap_to_median=round(actual - band.p50, 2),
        )

    def compare_package(self, package: dict, industry_id: Optional[str],
                         level: Optional[str]) -> list[BenefitComparison]:
        """package: {category: actual_value}. Categories absent from the dict are
        treated as 'not offered' (surfaced separately via generate_advice), not as zero."""
        out = []
        for category in self.categories():
            value = package.get(category)
            if value is None:
                continue
            comp = self.compare(category, float(value), industry_id, level)
            if comp:
                out.append(comp)
        return out

    def benefits_richness_index(self, comparisons: list[BenefitComparison]) -> float:
        """0-100 composite: ~50 = at market median across categories, on average."""
        if not comparisons:
            return 0.0
        return round(sum(c.percentile_rank for c in comparisons) / len(comparisons), 1)

    # ── advice (rule-based, mirrors ArchitectureReportService pattern detection) ──
    def generate_advice(self, comparisons: list[BenefitComparison], offered_categories: set) -> list[dict]:
        advice = []
        for comp in comparisons:
            if comp.status == "Below P25":
                advice.append({
                    "severity": "high", "category": comp.category,
                    "title": f"{comp.category} is below the market P25",
                    "detail": (f"Your {comp.category.lower()} value ({comp.actual:g} {comp.band.unit}) sits in the "
                               f"bottom quartile for this industry/level (P25={comp.band.p25:g}, "
                               f"median={comp.band.p50:g}). This is a competitive risk for retention and offers."),
                })
            elif comp.status == "Below median":
                advice.append({
                    "severity": "medium", "category": comp.category,
                    "title": f"{comp.category} trails the market median",
                    "detail": (f"Your value ({comp.actual:g} {comp.band.unit}) is below the market median "
                               f"({comp.band.p50:g} {comp.band.unit}). Consider moving toward P50 at the next review."),
                })
        missing = set(self.categories()) - offered_categories
        for category in sorted(missing):
            band = self.get_band(category, None, None)
            if band is None:
                continue
            advice.append({
                "severity": "low", "category": category,
                "title": f"No {category.lower()} offered",
                "detail": (f"Market median is {band.p50:g} {band.unit} for {category.lower()} "
                           f"(n={band.n_observations}). Consider introducing it, even at a modest level."),
            })
        order = {"high": 0, "medium": 1, "low": 2}
        advice.sort(key=lambda a: order.get(a["severity"], 9))
        return advice

    # ── Total Rewards (bridges Pay + Benefits into one snapshot) ────────
    def total_rewards_snapshot(self, benefits_index: float, pay_compa_ratio: Optional[float]) -> dict:
        """Combine the Benefits Richness Index with a Pay compa-ratio into one Total
        Rewards position — a first step toward a unified Pay + Benefits 'Total Rewards'
        center (see docs/ROADMAP.md)."""
        pay_score = round(min(pay_compa_ratio, 1.5) / 1.0 * 100, 1) if pay_compa_ratio else None
        combined = round((benefits_index + pay_score) / 2, 1) if pay_score is not None else benefits_index
        return {"pay_score": pay_score, "benefits_score": benefits_index, "total_rewards_score": combined}

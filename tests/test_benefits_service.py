"""tests/test_benefits_service.py"""

import pandas as pd
import pytest

from core.repository import Repository
from services.benefits_service import BenefitsService


class _FakeCatalog:
    def __init__(self, repository):
        self.repository = repository


@pytest.fixture
def benefits_repo() -> Repository:
    # Two industries, one category with a clean, hand-picked distribution so
    # the percentile math is easy to assert exactly.
    observations = pd.DataFrame(
        [{"IndustryID": "IND-A", "Category": "Wellness", "Value": v, "Unit": "EUR"}
         for v in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]]
        + [{"IndustryID": "IND-B", "Category": "Wellness", "Value": v, "Unit": "EUR"}
           for v in [10, 20, 30, 40, 50]]
    )
    catalog_df = pd.DataFrame([
        {"BenefitID": "BEN-01", "Category": "Wellness", "Unit": "EUR", "Basis": "Fixed annual budget"},
    ])
    level_factors = pd.DataFrame([
        {"Level": "Junior", "Category": "Wellness", "Factor": 0.5},
        {"Level": "Senior", "Category": "Wellness", "Factor": 2.0},
    ])
    data = {
        # SearchIndex.build() expects these unconditionally; empty is fine.
        "jobs": pd.DataFrame(columns=["JobID", "StandardTitle", "Function", "Level"]),
        "titles": pd.DataFrame(columns=["ExistingTitle", "JobID"]),
        "benefitscatalog": catalog_df,
        "benefitsobservations": observations,
        "levelbenefitsfactors": level_factors,
    }
    return Repository(data, validate=False)


@pytest.fixture
def catalog(benefits_repo) -> _FakeCatalog:
    return _FakeCatalog(benefits_repo)


@pytest.fixture
def service(catalog) -> BenefitsService:
    return BenefitsService(catalog)


def test_observation_company_name_and_notes_are_optional_and_read(catalog):
    repo = catalog.repository
    obs = repo.benefit_observations[("IND-A", "Wellness")]
    assert all(o.company_name == "" and o.notes == "" for o in obs)  # synthetic rows: blank is fine


def test_real_company_observation_carries_provenance():
    df = pd.DataFrame([
        {"IndustryID": "IND-A", "Category": "Pension", "Value": 15.8, "Unit": "%",
         "CompanyName": "Shell Nederland Raffinaderij", "Notes": "Derived from CAO text."},
    ])
    data = {
        "jobs": pd.DataFrame(columns=["JobID", "StandardTitle", "Function", "Level"]),
        "titles": pd.DataFrame(columns=["ExistingTitle", "JobID"]),
        "benefitsobservations": df,
    }
    repo = Repository(data, validate=False)
    obs = repo.benefit_observations[("IND-A", "Pension")][0]
    assert obs.company_name == "Shell Nederland Raffinaderij"
    assert obs.notes == "Derived from CAO text."


def test_categories_and_catalog_item(service):
    assert service.categories() == ["Wellness"]
    item = service.catalog_item("Wellness")
    assert item.unit == "EUR"


def test_get_band_computes_percentiles_from_observations(service):
    band = service.get_band("Wellness", "IND-A", None)
    assert band.n_observations == 10
    assert band.p50 == pytest.approx(550.0)  # median of 100..1000
    assert band.p25 < band.p50 < band.p75 < band.p90


def test_get_band_pools_across_industries_when_none_given(service):
    band = service.get_band("Wellness", None, None)
    assert band.n_observations == 15  # 10 + 5


def test_get_band_applies_level_factor(service):
    base = service.get_band("Wellness", "IND-A", None)
    senior = service.get_band("Wellness", "IND-A", "Senior")
    assert senior.p50 == pytest.approx(base.p50 * 2.0)


def test_get_band_unknown_category_returns_none(service):
    assert service.get_band("Nonexistent", "IND-A", None) is None


def test_compare_status_thresholds(service):
    below = service.compare("Wellness", 50, "IND-A", None)
    assert below.status == "Below P25"
    at_market = service.compare("Wellness", 550, "IND-A", None)
    assert at_market.status == "At market"
    above = service.compare("Wellness", 1200, "IND-A", None)
    assert above.status == "Above P90"


def test_compare_package_skips_unoffered_categories(service):
    comps = service.compare_package({"Wellness": 550}, "IND-A", None)
    assert len(comps) == 1 and comps[0].category == "Wellness"
    assert service.compare_package({}, "IND-A", None) == []


def test_benefits_richness_index(service):
    comps = service.compare_package({"Wellness": 550}, "IND-A", None)
    idx = service.benefits_richness_index(comps)
    assert 0 <= idx <= 100
    assert service.benefits_richness_index([]) == 0.0


def test_generate_advice_flags_low_value_high_severity(service):
    comps = service.compare_package({"Wellness": 50}, "IND-A", None)
    advice = service.generate_advice(comps, offered_categories={"Wellness"})
    assert advice[0]["severity"] == "high"
    assert "Wellness" in advice[0]["title"]


def test_generate_advice_flags_missing_category_low_severity(service):
    advice = service.generate_advice([], offered_categories=set())
    assert len(advice) == 1
    assert advice[0]["severity"] == "low"
    assert "wellness" in advice[0]["title"].lower()


def test_total_rewards_snapshot_combines_pay_and_benefits(service):
    snap = service.total_rewards_snapshot(80.0, 1.0)
    assert snap["pay_score"] == 100.0
    assert snap["total_rewards_score"] == pytest.approx(90.0)


def test_total_rewards_snapshot_without_pay_falls_back_to_benefits(service):
    snap = service.total_rewards_snapshot(42.0, None)
    assert snap["pay_score"] is None
    assert snap["total_rewards_score"] == 42.0

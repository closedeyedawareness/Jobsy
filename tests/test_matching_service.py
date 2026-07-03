"""tests/test_matching_service.py"""

import pandas as pd
import pytest

from services.matching_service import MatchingService, MatchType


@pytest.mark.parametrize(
    "title,expected_type,expected_conf",
    [
        ("HR Business Partner", MatchType.EXACT, 100),
        ("hr business partner", MatchType.EXACT, 100),
        ("HR-Business Partner!", MatchType.NORMALIZED, 98),
        ("HRBP", MatchType.SYNONYM, 96),
        ("Boekhouder", MatchType.SYNONYM, 96),
    ],
)
def test_deterministic_stages(service, title, expected_type, expected_conf):
    r = service.match(title)
    assert r.match_type is expected_type
    assert r.confidence == expected_conf
    assert r.matched is True


def test_no_match(service):
    r = service.match("Underwater Basket Weaver")
    assert r.matched is False
    assert r.match_type is MatchType.NONE
    assert r.requires_review is True


def test_empty_input(service):
    r = service.match("   ")
    assert r.matched is False
    assert r.confidence == 0


def test_enrichment_fields(service):
    r = service.match("HRBP")
    assert r.standard_title == "HR Business Partner"
    assert r.function == "HR" and r.level == "Senior"
    assert r.description == "Partners with leaders on people strategy."
    assert r.salary_range == (60000, 82000)
    assert r.currency == "EUR"


def test_enrichment_handles_missing_band_and_profile(service):
    r = service.match("Boekhouder")  # Accountant: no salary band, no profile
    assert r.matched is True
    assert r.standard_title == "Accountant"
    assert r.salary_range is None
    assert r.description is None


def test_review_threshold(catalog):
    strict = MatchingService(catalog, index=catalog.repository.index, review_threshold=100)
    # synonym confidence 96 < 100 -> flagged
    assert strict.match("HRBP").requires_review is True


def test_batch_and_summary(service):
    results = service.match_titles(["HRBP", "Developer", "Underwater Basket Weaver"])
    summary = service.summarize(results)
    assert summary.total == 3
    assert summary.matched == 2
    assert summary.unmatched == 1
    assert summary.review >= 1
    assert summary.by_type["synonym"] == 2


def test_match_dataframe(service):
    df = pd.DataFrame({"title": ["HRBP", "Developer", "???"]})
    out = service.match_dataframe(df, "title")
    titles = list(out["matched_title"])
    assert titles[0] == "HR Business Partner"
    assert titles[1] == "Software Engineer"
    assert titles[2] is None or pd.isna(titles[2])
    assert "confidence" in out.columns and "requires_review" in out.columns


# --- fuzzy confidence mapping, independent of rapidfuzz availability ----------
class _FakeIndex:
    def __init__(self, hit):
        self._hit = hit

    def exact(self, t):
        return None

    def normalized(self, t):
        return None

    def synonym(self, t):
        return None

    def fuzzy(self, t, score_cutoff=80.0):
        return self._hit


def test_fuzzy_confidence_passes_threshold(catalog):
    svc = MatchingService(catalog, index=_FakeIndex(("J-SE", 92.0)))
    r = svc.match("Sofware Enginer")
    assert r.match_type is MatchType.FUZZY
    assert r.confidence == 92
    assert r.requires_review is False


def test_fuzzy_confidence_below_threshold_flags_review(catalog):
    svc = MatchingService(catalog, index=_FakeIndex(("J-SE", 60.0)))
    r = svc.match("garbled")
    assert r.match_type is MatchType.FUZZY
    assert r.confidence == 60
    assert r.requires_review is True


def test_fuzzy_never_outranks_deterministic(catalog):
    # even a perfect fuzzy score is capped below synonym/normalized/exact
    svc = MatchingService(catalog, index=_FakeIndex(("J-SE", 100.0)))
    assert svc.match("x").confidence == MatchingService.FUZZY_MAX_CONFIDENCE  # 95


def test_fuzzy_disabled(catalog):
    svc = MatchingService(catalog, index=_FakeIndex(("J-SE", 100.0)), enable_fuzzy=False)
    assert svc.match("x").matched is False

"""tests/test_search_index.py"""

import pytest


def test_exact_is_case_insensitive(repository):
    idx = repository.index
    assert idx.exact("HR Business Partner") == "J-HRBP"
    assert idx.exact("hr business partner") == "J-HRBP"
    assert idx.exact("HRBP") is None  # synonym, not a standard title


def test_normalized_handles_punctuation(repository):
    assert repository.index.normalized("HR-Business  Partner!") == "J-HRBP"


def test_synonym_lookup(repository):
    idx = repository.index
    assert idx.synonym("HRBP") == "J-HRBP"
    assert idx.synonym("Junior Developer") == "J-JSE"


def test_legacy_find_still_works(repository):
    assert repository.index.find("hrbp") == "J-HRBP"


def test_fuzzy_returns_match_when_available(repository):
    pytest.importorskip("rapidfuzz")
    hit = repository.index.fuzzy("Sofware Enginer", score_cutoff=70)
    assert hit is not None
    job_id, score = hit
    assert job_id == "J-SE"
    assert 0 < score <= 100


def test_fuzzy_below_cutoff_returns_none(repository):
    pytest.importorskip("rapidfuzz")
    assert repository.index.fuzzy("zzzzzzzz", score_cutoff=95) is None

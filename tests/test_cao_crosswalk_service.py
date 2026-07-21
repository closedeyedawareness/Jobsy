"""Tests for the ISF/CATS public-band crosswalk (no protected scoring method involved)."""

from __future__ import annotations

import pytest

from services.cao_crosswalk_service import (
    ISF_BANDS,
    crosswalk_to_cats,
    crosswalk_to_isf,
    known_cats_sectors,
)


def test_isf_lowest_grade_lands_in_band_a():
    r = crosswalk_to_isf(job_grade=1, grade_min=1, grade_max=16)
    assert r.salarisgroep == "A"
    assert r.isf_point_range == (0, 130)
    assert r.rank_fraction == 0.0
    assert r.is_hoger_personeel is False
    assert r.monthly_scale is not None


def test_isf_highest_grade_lands_in_band_q():
    r = crosswalk_to_isf(job_grade=16, grade_min=1, grade_max=16)
    assert r.salarisgroep == "Q"
    assert r.isf_point_range == (881, 940)
    assert r.rank_fraction == 1.0
    assert r.is_hoger_personeel is True
    assert r.monthly_scale is None          # HP bands have no rigid monthly step table


def test_isf_midpoint_lands_near_the_middle_band():
    # 16 bands (index 0-15); midpoint rank ~0.5 -> index 7 or 8 (H or J).
    r = crosswalk_to_isf(job_grade=8, grade_min=1, grade_max=16)
    assert r.salarisgroep in ("H", "J")


def test_isf_never_reproduces_a_point_score_only_a_band():
    r = crosswalk_to_isf(job_grade=5, grade_min=1, grade_max=10)
    # The result carries a published band range, never a single fabricated
    # "this job scored N points" number.
    assert isinstance(r.isf_point_range, tuple) and len(r.isf_point_range) == 2
    assert "geen berekende ISF-score" in r.note


def test_isf_returns_none_for_a_degenerate_grade_range():
    assert crosswalk_to_isf(job_grade=5, grade_min=5, grade_max=5) is None


def test_isf_clamps_grades_outside_the_supplied_range():
    below = crosswalk_to_isf(job_grade=-3, grade_min=1, grade_max=16)
    above = crosswalk_to_isf(job_grade=99, grade_min=1, grade_max=16)
    assert below.salarisgroep == "A"
    assert above.salarisgroep == "Q"


def test_isf_bands_are_verified_and_contiguous():
    # Guards against a future silent edit reintroducing the original
    # (wrong) N/O/P/Q figures this module replaced.
    assert ("N", 701, 760) in ISF_BANDS
    assert ("O", 761, 820) in ISF_BANDS
    assert ("P", 821, 880) in ISF_BANDS
    assert ("Q", 881, 940) in ISF_BANDS
    letters = [b[0] for b in ISF_BANDS]
    assert letters == ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K",
                        "L", "M", "N", "O", "P", "Q"]


def test_cats_label_alignment_lowest_and_highest():
    lo = crosswalk_to_cats(job_grade=1, grade_min=1, grade_max=10, sector="Metaal en Techniek")
    hi = crosswalk_to_cats(job_grade=10, grade_min=1, grade_max=10, sector="Metaal en Techniek")
    assert lo.functiegroep == 2 and lo.salarisgroep == "A"
    assert hi.functiegroep == 11 and hi.salarisgroep == "J"


def test_cats_never_claims_a_point_range():
    r = crosswalk_to_cats(job_grade=5, grade_min=1, grade_max=10)
    assert "no public point-range table" in r.note.lower()
    assert not hasattr(r, "isf_point_range")


def test_cats_unknown_sector_is_explicit_about_missing_data():
    r = crosswalk_to_cats(job_grade=5, grade_min=1, grade_max=10, sector="Grafimedia")
    assert r.salarisgroep is None
    assert "no public functiegroep/salarisgroep table on file" in r.note.lower()


def test_known_cats_sectors_lists_what_is_actually_sourced():
    assert known_cats_sectors() == ["Metaal en Techniek"]

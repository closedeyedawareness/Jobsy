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


# ── positioning by our own point range ───────────────────────────────────────
#
# JobGrades carries a point range per grade: Jobsy's own scale, 100 to 1800.
# ISF publishes point boundaries, 0 to 940. Both are called points and they are
# not the same quantity — the method that produces an ISF total is protected.
# These tests hold that line mechanically instead of in a docstring.

OWN_MIN, OWN_MAX = 100.0, 1800.0          # the real ladder, grades 1..14


def test_our_points_are_never_looked_up_in_the_isf_table():
    """Grade 7 sits at 405 of OUR points. 405 falls inside ISF band G (381-430),
    so a naive lookup would answer G. The honest answer is where 405 sits on our
    own 100-1800 scale — 18% of the way up — which is band D. If this ever
    returns G, someone has started treating our points as ISF points."""
    res = crosswalk_to_isf(7, 1, 14, points=405, points_min=OWN_MIN, points_max=OWN_MAX)
    naive_band = next(b for b, lo, hi in ISF_BANDS if lo <= 405 <= hi)
    assert naive_band == "G"
    assert res.salarisgroep == "D"
    assert res.salarisgroep != naive_band
    assert res.basis == "own point range"


def test_a_point_total_above_the_whole_isf_table_still_positions():
    """Grade 14 tops out at 1800 of our points — off the end of ISF's 940. A
    lookup has no answer at all; a proportion has the obvious one."""
    res = crosswalk_to_isf(14, 1, 14, points=1800, points_min=OWN_MIN, points_max=OWN_MAX)
    assert res.salarisgroep == "Q" and res.rank_fraction == 1.0


def test_without_points_it_behaves_exactly_as_before():
    before = crosswalk_to_isf(7, 1, 14)
    assert before.basis == "grade rank"
    assert before.salarisgroep == crosswalk_to_isf(7, 1, 14, points=None).salarisgroep


def test_points_and_grade_rank_genuinely_disagree():
    """If they always agreed, passing points would be decoration. They do not:
    the rungs are not evenly spaced — grade 3 spans 35 points, grade 14 spans 530."""
    by_rank = crosswalk_to_isf(7, 1, 14).salarisgroep
    by_points = crosswalk_to_isf(7, 1, 14, points=405,
                                 points_min=OWN_MIN, points_max=OWN_MAX).salarisgroep
    assert by_rank != by_points


def test_the_note_says_which_basis_and_that_it_is_not_an_isf_score():
    res = crosswalk_to_isf(7, 1, 14, points=405, points_min=OWN_MIN, points_max=OWN_MAX)
    assert "geen berekende ISF-score" in res.note
    assert "eigen puntenbereik" in res.note


def test_cats_takes_the_same_basis_and_still_claims_no_score():
    res = crosswalk_to_cats(7, 1, 14, points=405, points_min=OWN_MIN, points_max=OWN_MAX)
    assert res.basis == "own point range"
    assert "no public point-range table" in res.note


def test_a_degenerate_point_range_falls_back_to_grade_rank():
    res = crosswalk_to_isf(7, 1, 14, points=405, points_min=500, points_max=500)
    assert res.basis == "grade rank"

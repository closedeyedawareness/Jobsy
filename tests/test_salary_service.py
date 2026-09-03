"""
Placing a salary against a band.

The arithmetic here decides what a client is told about their own pay, so the
edges matter more than the happy path: a band with no P50, a band of zero
width, a part-timer, an FTE of 0 (which in a real client file means an hourly
rate, not a person who does not work), and a person with no matched role.

The pro-rating tests pin the 2026-09-03 behaviour change: the compa-ratio now
compares full-time equivalents when an FTE is supplied. See the module
docstring in services/salary_service.py for why.
"""

import pytest

from core.models import SalaryBand
from services.salary_service import (
    AT_MARKET, ABOVE_MARKET_LABEL, ABOVE_RANGE, BELOW_MARKET_LABEL, BELOW_RANGE,
    NO_MATCH, BandPosition, Coverage, band_status, compa_ratio, full_time_pay,
    midpoint, position, range_penetration, scale_band,
)


def band(min=40000, max=60000, p50=50000, p25=45000, p75=55000, grade="G3"):
    return SalaryBand(function="Engineering", level="Medior", grade=grade,
                      min=min, max=max, p25=p25, p50=p50, p75=p75, currency="EUR")


# ── midpoint ─────────────────────────────────────────────────────────────────

def test_midpoint_prefers_the_bands_own_p50():
    assert midpoint(band(p50=52000)) == 52000


def test_a_band_without_a_p50_falls_back_to_the_middle_of_the_range():
    assert midpoint(band(p50=0)) == 50000


def test_midpoint_of_nothing_is_nothing():
    assert midpoint(None) is None


# ── compa-ratio and range ────────────────────────────────────────────────────

def test_compa_ratio_is_pay_over_the_midpoint():
    assert compa_ratio(50000, band()) == 1.0
    assert compa_ratio(45000, band()) == 0.9


def test_compa_ratio_is_none_when_the_midpoint_is_unknown():
    assert compa_ratio(50000, band(p50=0, min=0, max=0)) is None


def test_range_penetration_runs_from_the_floor_to_the_ceiling():
    assert range_penetration(40000, band()) == 0
    assert range_penetration(50000, band()) == 50
    assert range_penetration(60000, band()) == 100


def test_range_penetration_is_not_clamped_because_out_of_range_is_the_signal():
    assert range_penetration(30000, band()) == -50
    assert range_penetration(70000, band()) == 150


def test_a_zero_width_band_has_no_position_rather_than_a_division_by_zero():
    assert range_penetration(50000, band(min=50000, max=50000)) is None


# ── status ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pay,expected", [
    (39999, BELOW_RANGE),
    (60001, ABOVE_RANGE),
    (44000, BELOW_MARKET_LABEL),   # inside the band, under 0.9 of midpoint
    (56000, ABOVE_MARKET_LABEL),   # inside the band, over 1.1 of midpoint
    (50000, AT_MARKET),
])
def test_the_status_labels_are_unchanged(pay, expected):
    assert band_status(pay, band()) == expected


def test_being_outside_the_range_outranks_being_off_market():
    # 39999 is both below the range and below market; the range must win, or the
    # page under-reports how serious it is.
    assert band_status(39999, band()) == BELOW_RANGE


def test_the_thresholds_are_exclusive_at_the_edges():
    assert band_status(45000, band()) == AT_MARKET   # exactly 0.90
    assert band_status(55000, band()) == AT_MARKET   # exactly 1.10


def test_no_band_means_no_match_not_a_crash():
    assert band_status(50000, None) == NO_MATCH
    assert position(50000, None).status == NO_MATCH
    assert position(None, band()).status == NO_MATCH


# ── part-time ────────────────────────────────────────────────────────────────

def test_a_part_timer_on_proportionate_pay_is_at_market_not_below_range():
    # THE BUG THIS SERVICE FIXES: 0.6 FTE on 30000 is exactly the midpoint pro
    # rata. Before, it was reported Below range.
    pos = position(30000, band(), fte=0.6)
    assert pos.status == AT_MARKET
    assert pos.compa_ratio == 1.0
    assert pos.pro_rated is True
    assert pos.compared_pay == 50000


def test_without_an_fte_the_old_behaviour_stands():
    pos = position(30000, band(), fte=None)
    assert pos.status == BELOW_RANGE
    assert pos.pro_rated is False


def test_a_full_time_fte_changes_nothing_and_is_not_reported_as_pro_rated():
    pos = position(50000, band(), fte=1.0)
    assert pos.compa_ratio == 1.0 and pos.pro_rated is False


def test_an_fte_of_zero_is_unknown_not_a_divisor():
    # FTE 0 rows in a real client file held hourly rates (Colliers, 33 of them).
    # Dividing by it would produce infinity in a pay report.
    assert full_time_pay(50000, 0) == 50000
    assert position(50000, band(), fte=0).pro_rated is False


def test_the_position_states_the_basis_it_used():
    assert "full-time equivalent" in position(30000, band(), fte=0.6).basis
    assert "as supplied" in position(30000, band()).basis


def test_the_band_edges_travel_with_the_position():
    pos = position(50000, band())
    assert (pos.band_min, pos.band_p50, pos.band_max, pos.grade) == (40000, 50000, 60000, "G3")


# ── industry scaling ─────────────────────────────────────────────────────────

def test_an_industry_factor_scales_every_money_value():
    scaled = scale_band(band(), 1.1)
    assert (scaled.min, scaled.p25, scaled.p50, scaled.p75, scaled.max) == (
        44000, 49500, 55000, 60500, 66000)
    assert scaled.function == "Engineering" and scaled.currency == "EUR"


def test_a_factor_of_one_returns_the_band_itself_untouched():
    b = band()
    assert scale_band(b, 1.0) is b


def test_scaling_nothing_gives_nothing():
    assert scale_band(None, 1.2) is None


# ── coverage ─────────────────────────────────────────────────────────────────

def test_coverage_counts_both_kinds_of_exclusion():
    cov = Coverage(uploaded=100, parsed=95, priced=80)
    assert cov.unparsed == 5 and cov.unmatched == 15
    msg = cov.message()
    assert "80 of 100" in msg and "15 no role match" in msg and "5 unparsed pay" in msg


def test_full_coverage_does_not_invent_an_exclusion_clause():
    assert "excluded" not in Coverage(uploaded=10, parsed=10, priced=10).message()


def test_the_counts_must_account_for_every_uploaded_row():
    assert Coverage(uploaded=100, parsed=95, priced=80).reconciles()

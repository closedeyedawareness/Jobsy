"""Tests for the shift-toeslag / generatiepact reasoning layer."""

from __future__ import annotations

import pandas as pd
import pytest

from services.special_conditions_service import (
    analyze_special_conditions,
    detect_conditions_column,
    parse_condition,
)


def test_parse_ploeg_dutch_decimal_comma():
    c = parse_condition("2 ploeg 13,3%")
    assert c.shift_ploeg_count == 2
    assert c.shift_toeslag_pct == pytest.approx(13.3)
    assert not c.generatiepact


def test_parse_ploeg_dot_decimal_and_three_shift():
    c = parse_condition("3 ploeg 21%")
    assert c.shift_ploeg_count == 3
    assert c.shift_toeslag_pct == pytest.approx(21.0)


def test_parse_generatiepact_with_numbers():
    c = parse_condition("Generatiepact 80-90-100")
    assert c.generatiepact
    assert (c.gp_work_pct, c.gp_pay_pct, c.gp_pension_pct) == (80.0, 90.0, 100.0)


def test_parse_generatiepact_bare_text_still_flagged():
    c = parse_condition("Generatiepact")
    assert c.generatiepact
    assert c.gp_work_pct is None


def test_parse_blank_and_nan_are_empty():
    assert parse_condition(None) == parse_condition("")
    assert parse_condition(float("nan")).raw_note == ""
    assert not parse_condition(None).generatiepact


def test_detect_conditions_column_finds_unlabeled_column():
    df = pd.DataFrame({
        "Gender": ["M", "F"],
        "Salary": [50000, 51000],
        8: ["2 ploeg 13,3%", None],   # unlabeled column, like pandas' "Unnamed: 9"
    })
    assert detect_conditions_column(df) == 8


def _grid_df():
    rows = []
    for i in range(6):
        rows.append({"Function": "Ops", "Level": "3", "Gender": "M", "Salary": 50000, "Note": None})
    for i in range(6):
        rows.append({"Function": "Ops", "Level": "3", "Gender": "F", "Salary": 48000, "Note": None})
    # Tag half the men with a shift toeslag — the sensitivity run should show
    # a different N (and potentially different gap) once they're excluded.
    for i in range(3):
        rows[i]["Note"] = "2 ploeg 13,3%"
    return pd.DataFrame(rows)


def test_sensitivity_scenarios_change_n_when_excluding_tagged_rows():
    df = _grid_df()
    rep = analyze_special_conditions(
        df, function_col="Function", level_col="Level", gender_col="Gender",
        salary_col="Salary", conditions_col="Note")
    assert rep is not None
    by_label = {s.label: s for s in rep.scenarios}
    assert by_label["All rows (as supplied)"].n == 12
    assert by_label["Excluding shift-toeslag rows"].n == 9
    assert rep.n_shift_tagged == 3 and rep.n_shift_tagged_m == 3 and rep.n_shift_tagged_f == 0
    assert any("shift" in f.lower() for f in rep.risk_flags)
    assert any("payroll" in s.lower() or "hr" in s.lower() for s in rep.next_steps)


def test_generatiepact_peer_ratio_range_reported_when_peers_exist():
    df = _grid_df()
    # Add one generatiepact row at a different (higher) salary than its cat/function peers
    df = pd.concat([df, pd.DataFrame([{
        "Function": "Ops", "Level": "3", "Gender": "M", "Salary": 60000, "Note": "Generatiepact 80-90-100"
    }])], ignore_index=True)
    rep = analyze_special_conditions(
        df, function_col="Function", level_col="Level", gender_col="Gender",
        salary_col="Salary", conditions_col="Note")
    assert rep.n_generatiepact == 1 and rep.n_generatiepact_m == 1
    assert rep.generatiepact_peer_ratio_range is not None
    assert rep.generatiepact_peer_ratio_range[0] > 1.0   # 60000 vs peer medians below it


def test_no_conditions_column_returns_none():
    df = pd.DataFrame({"Function": ["Ops"], "Level": ["1"], "Gender": ["M"], "Salary": [1]})
    assert analyze_special_conditions(
        df, function_col="Function", level_col="Level", gender_col="Gender", salary_col="Salary") is None


def test_no_tagged_rows_reports_not_applicable():
    df = _grid_df()
    for r in df.to_dict("records"):
        r["Note"] = None
    df = pd.DataFrame(df.to_dict("records") if hasattr(df, "to_dict") else df)
    df["Note"] = None
    rep = analyze_special_conditions(
        df, function_col="Function", level_col="Level", gender_col="Gender",
        salary_col="Salary", conditions_col="Note")
    assert rep.n_shift_tagged == 0 and rep.n_generatiepact == 0
    assert any("doesn't apply" in f for f in rep.risk_flags)

"""tests/test_pay_equity_export_service.py"""

from io import BytesIO

import pandas as pd
import pytest

from services.pay_equity_service import analyze_gender_pay_gap
from services.pay_equity_export_service import PayEquityExportService


def _grid(gap_factor: float, per_gender: int = 6) -> pd.DataFrame:
    """Same fixture shape as test_pay_equity_service._grid: a leveled grid where,
    at every Function x Level, women earn ``gap_factor`` x the men's salary."""
    funcs = ["B", "P"]
    rows = []
    eid = 1000
    for fi, fn in enumerate(funcs):
        for lv in range(1, 4):
            base = 30000 + 5000 * lv + fi * 3000
            for _ in range(per_gender):
                eid += 1
                rows.append({"EmployeeID": f"E{eid}", "Function": fn, "Level": str(lv),
                             "Gender": "M", "Salary": base})
                eid += 1
                rows.append({"EmployeeID": f"E{eid}", "Function": fn, "Level": str(lv),
                             "Gender": "F", "Salary": round(base * gap_factor)})
    return pd.DataFrame(rows)


def _analyze(df, **kw):
    return analyze_gender_pay_gap(
        df, function_col="Function", level_col="Level",
        gender_col="Gender", salary_col="Salary", **kw,
    )


def _sheets(data: bytes) -> dict:
    return pd.read_excel(BytesIO(data), sheet_name=None)


def test_workbook_has_expected_sheets():
    # "2.0" layout: Notes and Representation are folded onto Summary, not their own tabs.
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    assert set(_sheets(data)) == {"Summary", "Cohorts"}


def test_summary_sheet_carries_headline_numbers():
    # Women earn 0.90x men's pay -> PayGapResult.mean_gap_pct (men-paid-more
    # convention) is positive ~10%; the export flips sign to the wetsvoorstel's
    # (vrouw-man)/man convention, so the exported value should be negative.
    # Metrics live in columns B/C now (A is a blank left margin); pandas still
    # finds them by header name regardless, so this reads the same as before.
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    sm = _sheets(data)["Summary"]
    metrics = dict(zip(sm["Metric"], sm["Value"]))
    assert metrics["Men (M)"] == r.n_m
    assert metrics["Women (F)"] == r.n_f
    assert r.mean_gap_pct > 0  # sanity: source result uses the other sign
    assert metrics["Mean gap % — unadjusted (+ = women paid more, per wetsvoorstel (vrouw-man)/man)"] \
        == pytest.approx(-r.mean_gap_pct)
    assert metrics["Median gap % — unadjusted (+ = women paid more)"] == pytest.approx(-r.median_gap_pct)
    assert metrics["Adjusted gap % (controls for function + level; + = women paid more)"] \
        == pytest.approx(-r.adjusted_gap_pct)


def test_adjusted_ci_is_flipped_and_reordered():
    r = _analyze(_grid(0.90))
    assert r.adjusted_ci is not None and r.adjusted_ci[0] < r.adjusted_ci[1]
    data = PayEquityExportService().to_workbook_bytes(r)
    sm = _sheets(data)["Summary"]
    metrics = dict(zip(sm["Metric"], sm["Value"]))
    lo, hi = metrics["Adjusted 95% CI — low"], metrics["Adjusted 95% CI — high"]
    assert lo < hi
    assert lo == pytest.approx(-r.adjusted_ci[1])
    assert hi == pytest.approx(-r.adjusted_ci[0])


def test_low_n_cohort_count_in_summary():
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    sm = _sheets(data)["Summary"]
    metrics = dict(zip(sm["Metric"], sm["Value"]))
    expected = sum(1 for c in r.cohorts if not c.reliable)
    assert metrics["Cohorts below the n>=5-per-gender reliability threshold (low-n, indicative only)"] == expected


def test_cohorts_sheet_matches_result_cohorts():
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    tbl = _sheets(data)["Cohorts"]
    assert len(tbl) == len(r.cohorts) == r.n_cohorts_tested
    assert set(tbl["Function"]) == {"B", "P"}
    assert (tbl["Flagged (>= 5%)"] == "Yes").all()  # every cohort has a 10% gap in this fixture
    # every cohort in this fixture has men paid more -> exported (women-paid-more) sign is negative
    assert (tbl["Mean gap % (+ = women paid more)"] < 0).all()
    for c, exported in zip(r.cohorts, tbl["Mean gap % (+ = women paid more)"]):
        assert exported == pytest.approx(-c.mean_gap_pct)


def _find_header_row(ws, col: int, text: str) -> int:
    return next(row for row in range(1, ws.max_row + 1) if ws.cell(row, col).value == text)


def test_representation_tables_are_inline_on_summary():
    # By-level (I:J) and by-function (K:L) now sit side by side on Summary,
    # sharing the dashboard header row with Notes and the reliable-cohorts table.
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    from openpyxl import load_workbook
    ws = load_workbook(BytesIO(data))["Summary"]

    level_header_row = _find_header_row(ws, 9, "Level")
    assert ws.cell(level_header_row, 10).value == "% women"
    by_level = {ws.cell(level_header_row + 1 + i, 9).value: ws.cell(level_header_row + 1 + i, 10).value
                for i in range(len(r.women_by_level))}
    assert by_level == r.women_by_level

    function_header_row = _find_header_row(ws, 11, "Function")
    assert function_header_row == level_header_row  # same shared dashboard header row
    assert ws.cell(function_header_row, 12).value == "% women"
    by_function = {ws.cell(function_header_row + 1 + i, 11).value: ws.cell(function_header_row + 1 + i, 12).value
                   for i in range(len(r.women_by_function))}
    assert by_function == r.women_by_function


def test_notes_are_inline_on_summary():
    # Notes now live in column B, one per row, below the shared dashboard header.
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    from openpyxl import load_workbook
    ws = load_workbook(BytesIO(data))["Summary"]

    header_row = _find_header_row(ws, 2, "Notes")
    expected = PayEquityExportService().notes_list(r)
    actual = [ws.cell(header_row + 1 + i, 2).value for i in range(len(expected))]
    assert actual == expected
    assert "wetsvoorstel" in actual[0] and "vrouw" in actual[0]


def test_export_handles_a_result_with_no_reliable_cohorts():
    # Every cohort here is a single M/F pair -- small-n, but still exportable.
    df = pd.DataFrame([
        {"Function": "B", "Level": "1", "Gender": "M", "Salary": 40000},
        {"Function": "B", "Level": "1", "Gender": "F", "Salary": 30000},
    ])
    r = _analyze(df)
    data = PayEquityExportService().to_workbook_bytes(r)
    sheets = _sheets(data)
    assert "Cohorts" in sheets
    assert len(sheets["Cohorts"]) == 1


def test_summary_sheet_has_a_reliable_cohorts_chart():
    # _grid(0.90) with the default per_gender=6 makes all 6 B/P x 1-3 cohorts reliable.
    r = _analyze(_grid(0.90))
    assert all(c.reliable for c in r.cohorts) and len(r.cohorts) == 6
    data = PayEquityExportService().to_workbook_bytes(r)
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(data))
    ws = wb["Summary"]
    assert len(ws._charts) == 1
    chart = ws._charts[0]
    assert len(chart.series) == 2  # Mean M, Mean F


def test_reliable_cohorts_minitable_matches_source_means():
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    from openpyxl import load_workbook
    ws = load_workbook(BytesIO(data))["Summary"]
    header_row = _find_header_row(ws, 5, "Function x Level")
    assert ws.cell(header_row, 6).value == "Mean M"
    assert ws.cell(header_row, 7).value == "Mean F"
    rows = {
        ws.cell(r_, 5).value: (ws.cell(r_, 6).value, ws.cell(r_, 7).value)
        for r_ in range(header_row + 1, header_row + 1 + len(r.cohorts))
    }
    for c in r.cohorts:
        assert rows[f"{c.function}-{c.level}"] == (c.mean_m, c.mean_f)


def test_no_chart_when_no_cohort_is_reliable():
    df = pd.DataFrame([
        {"Function": "B", "Level": "1", "Gender": "M", "Salary": 40000},
        {"Function": "B", "Level": "1", "Gender": "F", "Salary": 30000},
    ])
    r = _analyze(df)
    assert not any(c.reliable for c in r.cohorts)
    data = PayEquityExportService().to_workbook_bytes(r)
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(data))
    ws = wb["Summary"]
    assert len(ws._charts) == 0
    assert any("No cohort has a reliable" in str(cell.value)
               for row in ws.iter_rows() for cell in row if cell.value)


def test_brand_colours_are_applied():
    from openpyxl import load_workbook
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    wb = load_workbook(BytesIO(data))

    sm = wb["Summary"]
    assert sm["B1"].fill.fgColor.rgb[-6:] == "53037F"  # header = Jobsy deep purple

    # women earn 10% less in this fixture -> exported mean/median gap is negative
    # and >= the 5% threshold in magnitude, so it should render in the "danger" colour.
    mean_gap_row = next(
        row for row in range(2, sm.max_row + 1)
        if str(sm.cell(row, 2).value).startswith("Mean gap")
    )
    assert sm.cell(mean_gap_row, 3).font.color.rgb[-6:] == "FF5A7A"

    coh = wb["Cohorts"]
    gap_col = next(
        c for c in range(1, coh.max_column + 1)
        if str(coh.cell(1, c).value).startswith("Mean gap")
    )
    assert coh.cell(2, gap_col).font.color.rgb[-6:] == "FF5A7A"


def test_write_workbook_to_disk():
    import tempfile
    from pathlib import Path

    r = _analyze(_grid(0.90))
    target = Path(tempfile.gettempdir()) / "jobsy_test_pay_equity_out.xlsx"
    path = PayEquityExportService().write_workbook(r, target)
    assert path.exists() and path.stat().st_size > 0

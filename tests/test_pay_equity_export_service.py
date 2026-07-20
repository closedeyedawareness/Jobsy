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
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    assert set(_sheets(data)) == {"Summary", "Cohorts", "Representation", "Notes"}


def test_summary_sheet_carries_headline_numbers():
    # Women earn 0.90x men's pay -> PayGapResult.mean_gap_pct (men-paid-more
    # convention) is positive ~10%; the export flips sign to the wetsvoorstel's
    # (vrouw-man)/man convention, so the exported value should be negative.
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


def test_representation_sheet_has_both_tables():
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    # both the level-keyed and function-keyed tables are stacked in one sheet;
    # read the raw sheet rather than pd.read_excel so the second header survives.
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(data))
    ws = wb["Representation"]
    values = [[c.value for c in row] for row in ws.iter_rows()]
    assert values[0] == ["Level", "% women"]
    n_levels = len(r.women_by_level)
    # by_level occupies rows 0..n_levels (header + data), then one blank spacer row
    assert values[n_levels + 2] == ["Function", "% women"]


def test_notes_sheet_roundtrip():
    r = _analyze(_grid(0.90))
    data = PayEquityExportService().to_workbook_bytes(r)
    notes = list(_sheets(data)["Notes"]["Notes"])
    # the export prepends a sign-convention disclaimer ahead of the analysis's own notes
    assert notes[1:] == r.notes
    assert "wetsvoorstel" in notes[0] and "vrouw" in notes[0]


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


def test_write_workbook_to_disk():
    import tempfile
    from pathlib import Path

    r = _analyze(_grid(0.90))
    target = Path(tempfile.gettempdir()) / "jobsy_test_pay_equity_out.xlsx"
    path = PayEquityExportService().write_workbook(r, target)
    assert path.exists() and path.stat().st_size > 0

"""tests/test_export_service.py"""

from io import BytesIO

import pandas as pd

from jobsy.services.export_service import ExportService


def _run(service):
    results = service.match_titles(["HRBP", "Developer", "Underwater Basket Weaver"])
    return results, service.summarize(results)


def test_workbook_has_expected_sheets(service):
    results, summary = _run(service)
    data = ExportService().to_workbook_bytes(results, summary)
    sheets = pd.read_excel(BytesIO(data), sheet_name=None)
    assert set(sheets) == {"Matches", "Needs Review", "Summary"}


def test_matches_sheet_roundtrip(service):
    results, summary = _run(service)
    data = ExportService().to_workbook_bytes(results, summary)
    matches = pd.read_excel(BytesIO(data), sheet_name="Matches")
    assert len(matches) == 3
    assert "Matched Role" in matches.columns
    assert "Confidence" in matches.columns
    assert matches.loc[matches["Input Title"] == "HRBP", "Matched Role"].iloc[0] == "HR Business Partner"


def test_needs_review_is_filtered(service):
    results, summary = _run(service)
    data = ExportService().to_workbook_bytes(results, summary)
    review = pd.read_excel(BytesIO(data), sheet_name="Needs Review")
    assert review["Needs Review"].all()  # every row in this sheet needs review


def test_summary_sheet_values(service):
    results, summary = _run(service)
    data = ExportService().to_workbook_bytes(results, summary)
    sm = pd.read_excel(BytesIO(data), sheet_name="Summary")
    metrics = dict(zip(sm["Metric"], sm["Value"]))
    assert metrics["Total titles"] == 3
    assert metrics["Matched"] == 2


def test_write_workbook_to_disk(service):
    import tempfile
    from pathlib import Path

    results, summary = _run(service)
    target = Path(tempfile.gettempdir()) / "jobsy_test_out.xlsx"
    path = ExportService().write_workbook(results, target, summary)
    assert path.exists() and path.stat().st_size > 0

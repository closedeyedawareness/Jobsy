"""
The reference library on its way back out to a workbook.

The test that matters is the round trip: export a loaded catalog, read the file
back with Catalog(source="excel"), and get the same library. That is what makes
the export a restore path rather than a report, and it is the property that
would rot silently if a sheet name or a column drifted.
"""

import pandas as pd
import pytest

from core.catalog import Catalog, SHEET_MAP
from services.library_export_service import (
    LibraryExportService, export_bytes, export_to_path,
)


@pytest.fixture
def catalog(sample_sheets):
    """A catalog built straight from the shared fixture frames, no file, no DB."""
    cat = Catalog(path="does-not-exist.xlsx", source="excel")
    cat._build(sample_sheets)
    cat.active_source = "excel"
    return cat


def test_an_unloaded_catalog_refuses_to_export():
    # An empty export is worse than no export: it is a valid-looking library file.
    with pytest.raises(ValueError, match="no frames"):
        LibraryExportService(Catalog(path="does-not-exist.xlsx"))


def test_every_loaded_sheet_is_written_under_its_workbook_name(catalog, tmp_path):
    path = export_to_path(catalog, tmp_path / "lib.xlsx")
    written = set(pd.read_excel(path, sheet_name=None).keys())
    expected = {sheet for sheet, key in SHEET_MAP.items() if key in catalog.frames}
    assert expected <= written


def test_the_export_round_trips_into_a_working_catalog(catalog, tmp_path):
    path = export_to_path(catalog, tmp_path / "lib.xlsx")

    reloaded = Catalog(path=str(path), source="excel").load()

    assert set(reloaded.repository.jobs) == set(catalog.repository.jobs)
    assert len(reloaded.repository.title_mapping) == len(catalog.repository.title_mapping)
    assert set(reloaded.repository.salary) == set(catalog.repository.salary)


def test_a_role_survives_the_round_trip_intact(catalog, tmp_path):
    path = export_to_path(catalog, tmp_path / "lib.xlsx")
    reloaded = Catalog(path=str(path), source="excel").load()

    before = catalog.get_complete_job("J-HRBP")
    after = reloaded.get_complete_job("J-HRBP")
    assert after["job"].standard_title == before["job"].standard_title
    assert after["salary"].min == before["salary"].min
    assert after["salary"].max == before["salary"].max


def test_the_info_sheet_records_what_the_snapshot_is_of(catalog, tmp_path):
    path = export_to_path(catalog, tmp_path / "lib.xlsx")
    info = pd.read_excel(path, sheet_name="ExportInfo")
    items = dict(zip(info["Item"].astype(str), info["Item"].index))
    assert "Read from" in items and "Exported at (UTC)" in items
    assert (info.loc[info["Item"] == "Read from", "Value"] == "excel").all()


def test_the_info_sheet_is_ignored_when_the_file_is_read_back(catalog, tmp_path):
    # ExportInfo is not in SHEET_MAP, so a re-import must not trip over it.
    path = export_to_path(catalog, tmp_path / "lib.xlsx")
    reloaded = Catalog(path=str(path), source="excel").load()
    assert "ExportInfo" not in reloaded.frames


def test_a_fallback_snapshot_says_it_is_not_the_master(catalog, tmp_path):
    # The database was asked for and the workbook answered: the file that comes
    # out is a copy of a file, and must not pass as a snapshot of the master.
    catalog.source = "db"
    catalog.active_source = "excel"
    info = LibraryExportService(catalog).info_frame()
    warning = info.loc[info["Item"] == "Warning", "Value"]
    assert len(warning) == 1 and "not a snapshot of the master" in warning.iloc[0]


def test_row_counts_are_reported_per_sheet(catalog):
    info = LibraryExportService(catalog).info_frame()
    jobs = info.loc[info["Item"] == "Jobs rows", "Value"]
    assert jobs.iloc[0] == str(len(catalog.frames["jobs"]))


def test_export_bytes_produces_a_real_workbook(catalog):
    data = export_bytes(catalog)
    assert data[:2] == b"PK"          # xlsx is a zip
    assert len(pd.read_excel(pd.io.common.BytesIO(data), sheet_name=None)) >= 2


def test_the_filename_names_the_source(catalog):
    assert "excel" in LibraryExportService(catalog).suggested_filename()
    assert LibraryExportService(catalog).suggested_filename().endswith(".xlsx")


def test_the_honest_limit_stays_true():
    """The docstring's HONEST LIMIT is the one place a reader is told what the
    export does NOT contain. It rotted once and nobody noticed.

    Until 6 September 2026 it said "the 20 sheets in SHEET_MAP" and named
    pay_mix and pay_elements as tables "nothing loads yet". By then the map held
    25 sheets and both of those were in it. Naming the wrong omissions makes the
    honesty decorative — a reader trusts the paragraph precisely because it
    admits something.

    So the text now names no count and no table, and this test keeps it that
    way: a hard-coded number in that paragraph is a promise that goes stale on
    the next migration.
    """
    import re

    from core.catalog import SHEET_MAP
    from services import library_export_service as svc

    doc = svc.__doc__ or ""
    start = doc.find("HONEST LIMIT")
    assert start != -1, "the HONEST LIMIT paragraph is gone"
    limit = doc[start:]

    counts = re.findall(r"\b(\d+)\s+sheets\b", limit)
    assert not counts, (
        f"HONEST LIMIT hard-codes a sheet count {counts}; SHEET_MAP holds "
        f"{len(SHEET_MAP)} and the number will rot again")

    for sheet, key in SHEET_MAP.items():
        assert key not in limit.split("library_audit")[0], (
            f"HONEST LIMIT names {key!r} as something the app does not load, "
            f"but {sheet} is in SHEET_MAP")

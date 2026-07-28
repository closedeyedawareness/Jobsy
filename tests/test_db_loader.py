"""
Reading the library back out of Postgres.

The loader's only job is fidelity: produce frames the app cannot distinguish
from the ones pd.read_excel(dtype=str) produces. These run against a fake
client so the mapping, the paging and the type rendering are all testable
without a database or a key. The real comparison is tests/test_library_parity.py.
"""

import pandas as pd
import pytest

from core.db_loader import load_frames, _to_text, _render, PAGE


class _FakeQuery:
    """Enough of supabase-py's chained builder to answer one select."""

    def __init__(self, rows):
        self._rows = rows
        self._lo, self._hi = 0, None

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def range(self, lo, hi):
        self._lo, self._hi = lo, hi
        return self

    def execute(self):
        page = self._rows[self._lo:self._hi + 1]
        return type("Resp", (), {"data": page, "count": len(self._rows)})()


class _FakeClient:
    def __init__(self, tables):
        self.tables = tables
        self.requested = []

    def table(self, name):
        self.requested.append(name)
        return _FakeQuery(self.tables.get(name, []))


def _row(**kw):
    # updated_at is timestamptz and PostgREST renders it in full; effective_from
    # is a date and comes back bare. Faking updated_at as a bare date is what let
    # the ISO-timestamp difference reach the parity run unnoticed, so the fake
    # says what the database actually says.
    base = {"id": "row-1", "org_id": "org-1", "status": "active", "owner": "Job Architecture",
            "source": "Seed v1", "effective_from": "2026-07-02",
            "updated_at": "2026-07-02T00:00:00+00:00", "updated_by": "importer"}
    base.update(kw)
    return base


# ── value rendering ───────────────────────────────────────────────────────
# Excel read with dtype=str gives "2", never "2.0". Postgres gives 2, 2.0 or
# Decimal('2.00') depending on the column. Getting this wrong fails parity on a
# difference that is not real.

@pytest.mark.parametrize("value,expected", [
    (2, "2"),
    (2.0, "2"),
    (1.05, "1.05"),
    (8.33, "8.33"),
    ("HR Advisor", "HR Advisor"),
    (None, None),
    (float("nan"), None),
    (True, "TRUE"),
])
def test_values_render_the_way_excel_would(value, expected):
    assert _to_text(value) == expected


def test_a_decimal_that_is_a_whole_number_loses_its_trailing_zero():
    from decimal import Decimal
    assert _to_text(Decimal("1.00")) == "1"
    assert _to_text(Decimal("1.15")) == "1.15"


def test_a_timestamp_column_comes_back_as_the_date_the_workbook_holds():
    """The workbook's UpdatedAt is a date; Postgres stores timestamptz and renders
    '2026-07-02T00:00:00+00:00'. The importer only ever writes date-only values,
    so the time is always midnight and truncating loses nothing — but the frames
    are not equal until it is truncated, and an ISO timestamp would otherwise
    land in anything the app exports back to Excel."""
    assert _render("updated_at", "2026-07-02T00:00:00+00:00") == "2026-07-02"
    assert _render("effective_from", "2026-07-02") == "2026-07-02"
    assert _render("updated_at", None) is None
    # Only the date columns. A value that merely contains a T is untouched.
    assert _render("standard_title", "T-Shaped Engineer") == "T-Shaped Engineer"


# ── shape ─────────────────────────────────────────────────────────────────

def test_frames_are_keyed_and_named_the_way_repository_expects():
    client = _FakeClient({"jobs": [_row(job_id="J-1", standard_title="Dev",
                                        function="Eng", level="Medior", grade=4)]})
    frames = load_frames(client, "org-1")
    # Repository reads SHEET_MAP's key, not the table name.
    assert "jobs" in frames
    df = frames["jobs"]
    # ...and the WORKBOOK's column names, not the database's.
    assert "JobID" in df.columns and "StandardTitle" in df.columns
    assert "job_id" not in df.columns
    assert df.iloc[0]["JobID"] == "J-1"
    assert df.iloc[0]["Grade"] == "4"


def test_governance_columns_come_through_for_the_data_quality_page():
    client = _FakeClient({"jobs": [_row(job_id="J-1", standard_title="Dev",
                                        function="Eng", level="Medior")]})
    df = load_frames(client, "org-1")["jobs"]
    for col in ("Owner", "Status", "EffectiveFrom", "Source", "UpdatedAt"):
        assert col in df.columns, col
    assert df.iloc[0]["UpdatedAt"] == "2026-07-02"


def test_internal_columns_never_reach_the_frame():
    client = _FakeClient({"jobs": [_row(job_id="J-1", standard_title="Dev",
                                        function="Eng", level="Medior")]})
    df = load_frames(client, "org-1")["jobs"]
    for col in ("id", "org_id", "revision_id", "created_at", "updated_by"):
        assert col not in df.columns, col


def test_min_max_are_numeric_because_catalog_makes_them_numeric():
    client = _FakeClient({"salary_bands": [
        _row(function="HR", level="Junior", min=28000, max=38000, p50=33000)]})
    df = load_frames(client, "org-1")["salary"]
    assert pd.api.types.is_numeric_dtype(df["Min"])
    assert pd.api.types.is_numeric_dtype(df["Max"])
    # P50 is NOT in Catalog's coercion list, so it stays text — matching Excel.
    assert df.iloc[0]["P50"] == "33000"


def test_career_path_status_is_restored_to_the_sheet_meaning():
    """0002 split it: the workbook's Status column holds 'Terminal', while
    governance status is 'active'. The frame has to show the workbook's."""
    client = _FakeClient({"career_paths": [
        _row(job_id="J-9", next_job_id=None, next_role=None,
             status="active", path_status="Terminal")]})
    df = load_frames(client, "org-1")["career"]
    assert df.iloc[0]["Status"] == "Terminal"


def test_an_empty_table_still_yields_a_frame_with_its_columns():
    # Employees is empty in the library. A missing frame and an empty one are
    # different things to Repository.
    client = _FakeClient({"employees": []})
    df = load_frames(client, "org-1")["employees"]
    assert len(df) == 0
    assert "EmployeeID" in df.columns


# ── paging ────────────────────────────────────────────────────────────────

def test_a_table_larger_than_one_page_is_read_completely():
    """benefits_observations has 1,008 rows and PostgREST caps a response.
    An unpaged read would return the first 1,000 and the library would come
    back quietly incomplete — the exact failure this migration exists to end."""
    rows = [_row(id=f"r{i}", obs_id=f"BO-{i:05d}", industry_id="IND-TECH",
                 category="Pension", value=10 + i % 5) for i in range(PAGE + 8)]
    client = _FakeClient({"benefits_observations": rows})
    df = load_frames(client, "org-1")["benefitsobservations"]
    assert len(df) == PAGE + 8
    assert df.iloc[-1]["ObsID"] == f"BO-{PAGE + 7:05d}"


def test_pay_mix_is_excluded_by_default_and_included_on_request():
    """Repository never asked for PayMix — SHEET_MAP has no entry. The
    variable-pay exposure analysis does."""
    client = _FakeClient({"pay_mix": [_row(function="Eng", level="Lead",
                                           target_variable_pct=18,
                                           thirteenth_month_pct=8.33,
                                           lti_eligible="Yes")]})
    assert "PayMix" not in load_frames(client, "org-1")
    frames = load_frames(client, "org-1", include_all=True)
    assert "PayMix" in frames
    assert frames["PayMix"].iloc[0]["TargetVariablePct"] == "18"
    assert frames["PayMix"].iloc[0]["LTIEligible"] == "Yes"

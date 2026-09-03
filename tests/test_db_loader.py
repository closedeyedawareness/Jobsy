"""
Reading the library back out of Postgres.

The loader's only job is fidelity: produce frames the app cannot distinguish
from the ones pd.read_excel(dtype=str) produces. These run against a fake
client so the mapping, the paging and the type rendering are all testable
without a database or a key. The real comparison is tests/test_library_parity.py.
"""

import pandas as pd
import pytest

from core.db_loader import load_frames, load_frames_from_config, _to_text, _render, PAGE


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


def test_pay_mix_arrives_with_the_rest_of_the_library():
    """It used to need include_all, because SHEET_MAP had no entry for it and
    the variable-pay analysis reached past the loader to read it. Since
    2026-09-03 it loads like any other sheet, under its repository key."""
    client = _FakeClient({"pay_mix": [_row(function="Eng", level="Lead",
                                           target_variable_pct=18,
                                           thirteenth_month_pct=8.33,
                                           lti_eligible="Yes")]})
    frames = load_frames(client, "org-1")
    assert "paymix" in frames
    assert frames["paymix"].iloc[0]["TargetVariablePct"] == "18"
    # Yes/No stays the workbook's text: the parity gate compares frames, and the
    # typing belongs on PayMixEntry, not in the loader.
    assert frames["paymix"].iloc[0]["LTIEligible"] == "Yes"


def test_pay_elements_arrive_too_and_keep_their_free_text():
    client = _FakeClient({"pay_elements": [_row(element_id="PE-PENS", name="Pension (employer)",
                                                category="Benefits", basis="% of pensionable base",
                                                typical_value="~10-15% (indicative)",
                                                statutory_nl="Partly (sector funds)")]})
    df = load_frames(client, "org-1")["payelements"]
    # A range must reach the app as a range. Rendering it as a number here would
    # be the loader inventing a point estimate the library refuses to give.
    assert df.iloc[0]["TypicalValue"] == "~10-15% (indicative)"


# ── which credential the library is read with ────────────────────────────────
#
# The default is still the project's secret key, which bypasses RLS. These pin
# the switch itself, so flipping config.LIBRARY_CLIENT is a one-line change with
# known behaviour rather than a hope.

def test_the_default_credential_is_the_configured_one(monkeypatch):
    import core.db_loader as dl
    seen = {}
    monkeypatch.setattr(dl, "_user_client_and_org", lambda: (seen.setdefault("mode", "user"), "org"))
    dl.client_and_org(mode="user")
    assert seen["mode"] == "user"


def _fake_auth_service(monkeypatch, *, db, active_org_id):
    """Stand a fake services.auth_service in front of core.db_loader.

    Patching sys.modules alone is not enough. db_loader says
    `from services import auth_service`, which resolves through the ATTRIBUTE on
    the already-imported `services` package, not through a sys.modules lookup --
    so once anything in the suite has imported the real auth_service, these
    tests silently got the real one and took a different error path. They passed
    only while they happened to run before anything that imports it, which is a
    property of alphabetical file order rather than of the code under test.
    Patching both is order-independent.
    """
    import sys, types, services
    fake = types.ModuleType("services.auth_service")
    fake.db = db
    fake.active_org_id = active_org_id
    monkeypatch.setitem(sys.modules, "services.auth_service", fake)
    monkeypatch.setattr(services, "auth_service", fake, raising=False)
    return fake


def test_user_mode_refuses_rather_than_falling_back_when_nobody_is_signed_in(monkeypatch):
    """A fall back to the secret key would read exactly the same rows and prove
    nothing — which is the failure this switch exists to remove."""
    _fake_auth_service(monkeypatch, db=lambda: None, active_org_id=lambda: None)

    import core.db_loader as dl
    with pytest.raises(RuntimeError, match="nobody is signed in"):
        dl.client_and_org(mode="user")


def test_user_mode_refuses_when_the_account_has_no_active_client(monkeypatch):
    _fake_auth_service(monkeypatch, db=lambda: object(), active_org_id=lambda: None)

    import core.db_loader as dl
    with pytest.raises(RuntimeError, match="no active client"):
        dl.client_and_org(mode="user")


def test_a_caller_that_holds_a_client_is_not_given_a_second_one():
    """The app passes the signed-in session's client straight through; building
    another one here would quietly go back to the secret key."""
    client = _FakeClient({"jobs": [_row(job_id="J-1", standard_title="Engineer",
                                        function="Eng", level="Medior")]})
    frames = load_frames_from_config(client=client, org_id="org-1")
    assert "jobs" in frames and len(frames["jobs"]) == 1


# ── the fallback, once the read is user-scoped ───────────────────────────────

def test_a_user_scoped_failure_does_not_fall_back_to_the_committed_workbook():
    """With the secret key, an unreachable database means "stay up on the
    workbook". With the user's own credential it means something else entirely:
    this account may not read that org. Answering THAT with the repo's workbook
    would hand one client the default library as if it were theirs."""
    from core.catalog import Catalog

    class _Boom:
        def table(self, *_a, **_k):
            raise RuntimeError("permission denied")

    cat = Catalog(path="jobsy_reference_library.xlsx", source="db",
                  client=_Boom(), org_id="org-1")
    with pytest.raises(RuntimeError, match="not a substitute"):
        cat.load()


def test_an_empty_user_scoped_read_is_refused_rather_than_papered_over():
    from core.catalog import Catalog

    cat = Catalog(path="jobsy_reference_library.xlsx", source="db",
                  client=_FakeClient({}), org_id="org-1")
    with pytest.raises(RuntimeError, match="policies do not let"):
        cat.load()


def test_the_secret_key_path_still_falls_back_to_the_workbook():
    """Unchanged, and deliberately so: one tenant, a key that reads everything,
    and a committed workbook that is genuinely the same library."""
    from core.catalog import Catalog

    cat = Catalog(path="jobsy_reference_library.xlsx", source="db").load()
    assert cat.active_source == "excel"
    assert cat.fell_back_to_excel is True

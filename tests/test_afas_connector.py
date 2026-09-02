"""
The AFAS Profit GetConnector connector.

These drive the connector through a fake session, so the URL shape, the auth
header, the paging and the column resolution are all testable without an AFAS
environment or a token.

What these tests CANNOT tell us: whether a real tenant's GetConnector returns
the field names in `_FIELD_ALIASES`. A fake is always more agreeable than the
system it stands in for (see tests/test_db_loader.py for the last time that bit
us). The connector is built so that being wrong about a name is survivable —
unrecognised fields keep their own name and reach the frame anyway — and these
tests pin exactly that behaviour rather than the guess.
"""

import base64

import pandas as pd
import pytest

from services.afas_connector import AfasConnector, encode_token, _resolve_columns


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    """Records every call; answers from a queue or a single canned response."""

    def __init__(self, responses=None, raises=None):
        self.headers = {}
        self.calls = []
        self._responses = list(responses or [])
        self._raises = raises

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params or {}))
        if self._raises:
            raise self._raises
        if self._responses:
            return self._responses.pop(0)
        return _FakeResponse(200, {})


def _connector(session, **kw):
    return AfasConnector("12345", "TOKEN", session=session, **kw)


# ── token encoding ───────────────────────────────────────────────────────────

def test_xml_token_is_base64_encoded_for_the_header():
    xml = "<token><version>1</version><data>ABC123</data></token>"
    assert encode_token(xml) == base64.b64encode(xml.encode()).decode()


def test_an_already_encoded_token_is_passed_through_untouched():
    already = base64.b64encode(b"<token/>").decode()
    assert encode_token(already) == already


def test_the_authorization_header_names_the_afas_scheme():
    conn = _connector(_FakeSession())
    assert conn.session.headers["Authorization"].startswith("AfasToken ")


def test_an_empty_token_does_not_crash_construction():
    # The UI can construct before the field is filled; it must fail at the call,
    # with AFAS's own 401, not at __init__ with a traceback.
    conn = AfasConnector("12345", "", session=_FakeSession())
    assert conn.session.headers["Authorization"] == "AfasToken "


# ── environments ─────────────────────────────────────────────────────────────

def test_production_and_test_environments_have_different_hosts():
    prod = _connector(_FakeSession())
    test = _connector(_FakeSession(), environment="test")
    assert prod.base_url == "https://12345.rest.afas.online/profitrestservices"
    assert test.base_url == "https://12345.resttest.afas.online/profitrestservices"


# ── connection ───────────────────────────────────────────────────────────────

def test_test_connection_asks_metainfo_and_reports_success():
    session = _FakeSession([_FakeResponse(200, {"getConnectors": []})])
    ok, msg = _connector(session).test_connection()
    assert ok and msg == "Connected"
    assert session.calls[0][0].endswith("/metainfo")


def test_a_rejected_token_says_so_rather_than_printing_a_status_code():
    session = _FakeSession([_FakeResponse(401, text="Unauthorized")])
    ok, msg = _connector(session).test_connection()
    assert not ok
    assert "token" in msg and "12345" in msg


def test_a_network_failure_is_reported_not_raised():
    ok, msg = _connector(_FakeSession(raises=OSError("dns failure"))).test_connection()
    assert not ok and "dns failure" in msg


def test_list_connectors_reads_the_getconnectors_block():
    session = _FakeSession([_FakeResponse(200, {
        "getConnectors": [{"id": "HrEmployee"}, {"id": "HrOrgunit"}],
        "updateConnectors": [{"id": "KnEmployee"}],
    })])
    assert _connector(session).list_connectors() == ["HrEmployee", "HrOrgunit"]


def test_list_connectors_is_empty_rather_than_raising_when_the_call_fails():
    assert _connector(_FakeSession(raises=OSError("down"))).list_connectors() == []


# ── fetching ─────────────────────────────────────────────────────────────────

def _rows(n, start=0):
    return [{"Medewerker": f"E{i:03d}", "Functie": "Developer"} for i in range(start, start + n)]


def test_a_short_page_ends_the_fetch():
    session = _FakeSession([_FakeResponse(200, {"rows": _rows(3)})])
    df = _connector(session).fetch_employees(take=500)
    assert len(df) == 3
    assert len(session.calls) == 1


def test_paging_continues_while_pages_come_back_full():
    session = _FakeSession([
        _FakeResponse(200, {"rows": _rows(100, 0)}),
        _FakeResponse(200, {"rows": _rows(100, 100)}),
        _FakeResponse(200, {"rows": _rows(20, 200)}),
    ])
    df = _connector(session).fetch_employees(take=500)
    assert len(df) == 220
    assert [c[1]["skip"] for c in session.calls] == [0, 100, 200]


def test_take_is_a_ceiling_not_a_suggestion():
    session = _FakeSession([_FakeResponse(200, {"rows": _rows(100)}),
                            _FakeResponse(200, {"rows": _rows(100, 100)})])
    df = _connector(session).fetch_employees(take=150)
    assert len(df) == 150
    assert session.calls[-1][1]["take"] == 50


def test_no_rows_gives_an_empty_frame_not_an_error():
    session = _FakeSession([_FakeResponse(200, {"rows": []})])
    assert _connector(session).fetch_employees().empty


def test_the_connector_name_reaches_the_url():
    session = _FakeSession([_FakeResponse(200, {"rows": []})])
    _connector(session).fetch_employees(connector_name="Jobsy_Employees")
    assert session.calls[0][0].endswith("/connectors/Jobsy_Employees")


# ── column resolution ────────────────────────────────────────────────────────

def test_recognised_dutch_fields_become_jobsy_columns():
    session = _FakeSession([_FakeResponse(200, {"rows": [{
        "Medewerker": "E001", "Voornaam": "Ada", "Achternaam": "Lovelace",
        "Functie": "Software Engineer", "Organisatorische eenheid": "Engineering",
        "Leidinggevende": "E900", "Geslacht": "V",
    }]})])
    df = _connector(session).fetch_employees()
    assert set(df.columns) >= {"EmployeeID", "FirstName", "LastName",
                               "JobTitle", "Department", "ManagerID", "Gender"}


def test_field_labels_resolve_regardless_of_case_and_spacing():
    assert _resolve_columns(["organisatorische_eenheid"]) == {"organisatorische_eenheid": "Department"}
    assert _resolve_columns(["FUNCTIEOMSCHRIJVING"]) == {"FUNCTIEOMSCHRIJVING": "JobTitle"}


def test_an_unrecognised_field_survives_under_its_own_name():
    # The whole point: a tenant-specific field must not be silently dropped.
    session = _FakeSession([_FakeResponse(200, {"rows": [
        {"Medewerker": "E001", "Kostenplaats": "KP-42"}]})])
    df = _connector(session).fetch_employees()
    assert "Kostenplaats" in df.columns
    assert df.loc[0, "Kostenplaats"] == "KP-42"


def test_two_fields_do_not_fight_over_one_jobsy_column():
    resolved = _resolve_columns(["Functie", "Functieomschrijving"])
    assert list(resolved.values()) == ["JobTitle"]
    assert "Functieomschrijving" not in resolved


def test_a_part_time_percentage_is_not_reported_as_an_fte():
    # 100 in a column called FTE would be wrong everywhere it is multiplied.
    session = _FakeSession([_FakeResponse(200, {"rows": [
        {"Medewerker": "E001", "Parttime percentage": 80}]})])
    df = _connector(session).fetch_employees()
    assert "PartTimePercentage" in df.columns
    assert "FTE" not in df.columns


def test_salary_and_hours_arrive_numeric_and_ids_arrive_as_text():
    session = _FakeSession([_FakeResponse(200, {"rows": [
        {"Medewerker": 1001, "Bruto salaris": "4500,0", "Jaarsalaris": "58500"}]})])
    df = _connector(session).fetch_employees()
    assert df["EmployeeID"].dtype == object and df.loc[0, "EmployeeID"] == "1001"
    assert pd.api.types.is_numeric_dtype(df["AnnualSalaryEUR"])
    # A Dutch decimal comma is not a number; it must read as missing, not as 45000.
    assert pd.isna(df.loc[0, "MonthlySalaryEUR"])


def test_the_resolution_is_recorded_so_the_mapping_can_be_inspected():
    session = _FakeSession([_FakeResponse(200, {"rows": [
        {"Medewerker": "E001", "Kostenplaats": "KP-42"}]})])
    conn = _connector(session)
    conn.fetch_employees()
    assert conn.resolved_columns == {"Medewerker": "EmployeeID"}


def test_an_http_error_during_fetch_is_raised_for_the_page_to_report():
    session = _FakeSession([_FakeResponse(500, text="boom")])
    with pytest.raises(RuntimeError):
        _connector(session).fetch_employees()

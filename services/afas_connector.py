"""
afas_connector.py — AFAS Profit REST (GetConnector) connector for Jobsy.

AFAS Profit exposes data through *GetConnectors*: named, tenant-defined queries
that an AFAS administrator publishes to an App Connector. There is no fixed
employee schema — the fields a connector returns are whatever that customer's
administrator put in it. This connector therefore does two separate things and
keeps them separate:

  1. fetch the rows exactly as AFAS returns them (never dropped, never renamed
     away — the original columns stay in the frame), and
  2. *propose* Jobsy column names for the fields it recognises, recording which
     ones it resolved so the mapping can be inspected rather than trusted.

Authentication: an App Connector token. AFAS issues it as XML
(``<token><version>1</version><data>ABC…</data></token>``); the header wants
that XML base64-encoded, prefixed with ``AfasToken``. Both forms are accepted
here — paste the XML or the base64, the connector works out which it got.

Endpoints used:
  GET /profitrestservices/metainfo                     → the connectors on offer
  GET /profitrestservices/connectors/{name}?skip&take  → {"rows": [...]}

HONEST LIMIT: this module is written against AFAS's published REST interface and
is covered by tests that drive it through a fake transport. It has **not** been
run against a live AFAS environment. The shape of the calls is verifiable from
the docs; the field names a real tenant returns are not, which is exactly why
unrecognised columns are preserved instead of discarded.
"""
from __future__ import annotations

import base64
from typing import Optional

import pandas as pd
import requests

# ── AFAS field name → Jobsy column ────────────────────────────────────────────
# AFAS GetConnector field labels are Dutch and configurable per tenant, so this
# is a *recognition* table, not a schema. Keys are compared case-insensitively
# and ignoring spaces/underscores. First match wins; unrecognised fields survive
# under their original name.
_FIELD_ALIASES: list[tuple[tuple[str, ...], str]] = [
    (("medewerker", "medewerkernummer", "employeeid", "nummer", "persoonsnummer"), "EmployeeID"),
    (("voornaam", "roepnaam", "firstname"), "FirstName"),
    (("achternaam", "naam", "lastname", "geslachtsnaam"), "LastName"),
    (("functie", "functieomschrijving", "functienaam", "jobtitle"), "JobTitle"),
    (("organisatorischeeenheid", "afdeling", "afdelingsomschrijving", "department"), "Department"),
    (("bedrijfsonderdeel", "businessunit"), "BusinessUnit"),
    (("leidinggevende", "manager", "managernummer", "managerid"), "ManagerID"),
    (("vestiging", "plaats", "standplaats", "location"), "Location"),
    (("dienstverband", "contracttype", "soortdienstverband"), "ContractType"),
    # AFAS's part-time field is a percentage (100 = full time), not the fraction
    # the rest of Jobsy means by FTE. Kept under its own name and not converted:
    # a 100 landing in a column called FTE would be silently wrong everywhere it
    # is multiplied. Only a field actually labelled FTE becomes FTE.
    (("fte",), "FTE"),
    (("parttimepercentage", "deeltijdfactor", "parttimefactor"), "PartTimePercentage"),
    (("salaris", "brutosalaris", "maandsalaris", "salarisbedrag"), "MonthlySalaryEUR"),
    (("jaarsalaris", "brutojaarsalaris", "annualsalary"), "AnnualSalaryEUR"),
    (("geslacht", "gender"), "Gender"),
    (("datumindienst", "indienst", "startdatum", "hiredate"), "HireDate"),
    (("geboortedatum", "birthdate"), "BirthDate"),
]

_NUMERIC_COLUMNS = ("FTE", "MonthlySalaryEUR", "AnnualSalaryEUR")
_TEXT_COLUMNS = ("EmployeeID", "ManagerID")


def _normalise(name: str) -> str:
    """Field labels differ in case, spaces and underscores between tenants."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def _resolve_columns(columns) -> dict[str, str]:
    """Map the AFAS field names we recognise onto Jobsy column names.

    A Jobsy column is claimed by the first AFAS field that resolves to it, so a
    connector carrying both ``Functie`` and ``Functieomschrijving`` does not end
    up with two JobTitle columns fighting over one name.
    """
    resolved: dict[str, str] = {}
    taken: set[str] = set()
    for col in columns:
        key = _normalise(col)
        for aliases, jobsy in _FIELD_ALIASES:
            if key in aliases and jobsy not in taken:
                resolved[col] = jobsy
                taken.add(jobsy)
                break
    return resolved


def encode_token(token: str) -> str:
    """Return the base64 the ``AfasToken`` header wants, from XML or base64.

    AFAS hands the administrator an XML token. Some people paste that; some
    paste the base64 their previous integration used. Guessing wrong produces a
    401 with no explanation, so decide it here rather than in the UI.
    """
    raw = (token or "").strip()
    if not raw:
        return ""
    if raw.lstrip().startswith("<"):
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return raw


class AfasConnector:
    """Fetch employee data from an AFAS Profit GetConnector."""

    PROD_HOST = "https://{env_id}.rest.afas.online/profitrestservices"
    TEST_HOST = "https://{env_id}.resttest.afas.online/profitrestservices"

    #: AFAS caps a single page; larger takes are paged.
    PAGE = 100

    def __init__(
        self,
        env_id: str,
        token: str,
        environment: str = "production",
        session: Optional[requests.Session] = None,
    ):
        self.env_id = str(env_id).strip()
        self.environment = environment
        host = self.TEST_HOST if environment == "test" else self.PROD_HOST
        self.base_url = host.format(env_id=self.env_id)
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"AfasToken {encode_token(token)}",
            "Accept": "application/json",
        })
        #: Filled by the last fetch: AFAS field name → Jobsy column.
        self.resolved_columns: dict[str, str] = {}

    # ── connection ───────────────────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        """Ask for the metadata. Cheap, and it proves the token, not just the host."""
        try:
            r = self.session.get(f"{self.base_url}/metainfo", timeout=15)
        except Exception as exc:                      # network, DNS, TLS
            return False, str(exc)
        if r.status_code == 200:
            return True, "Connected"
        if r.status_code in (401, 403):
            return False, (
                f"HTTP {r.status_code}: the environment rejected the token. Check the "
                f"token belongs to environment {self.env_id} and that the App Connector "
                f"is enabled for REST."
            )
        return False, f"HTTP {r.status_code}: {r.text[:200]}"

    def list_connectors(self) -> list[str]:
        """The GetConnectors this token may read. Empty on any failure."""
        try:
            r = self.session.get(f"{self.base_url}/metainfo", timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []
        names = []
        for entry in data.get("getConnectors", []) or []:
            name = entry.get("id") or entry.get("name") or entry.get("description")
            if name:
                names.append(str(name))
        return names

    # ── data ─────────────────────────────────────────────────────────────────

    def fetch_employees(
        self,
        connector_name: str = "HrEmployee",
        take: int = 500,
        skip: int = 0,
    ) -> pd.DataFrame:
        """Read up to ``take`` rows from a GetConnector, as a Jobsy frame.

        Paging is AFAS's own skip/take. A short page means the end: AFAS reports
        no total, so there is nothing else to stop on.
        """
        rows: list[dict] = []
        cursor = skip
        while len(rows) < take:
            page_size = min(self.PAGE, take - len(rows))
            r = self.session.get(
                f"{self.base_url}/connectors/{connector_name}",
                params={"skip": cursor, "take": page_size},
                timeout=30,
            )
            r.raise_for_status()
            batch = (r.json() or {}).get("rows", []) or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            cursor += page_size

        # take is a ceiling, not a request: a connector that ignores it (or a
        # page that over-delivers) must not quietly hand the app more rows than
        # the user asked to fetch.
        return self._to_jobsy(rows[:take])

    def _to_jobsy(self, rows: list[dict]) -> pd.DataFrame:
        """Rename what we recognise; keep everything else under its own name."""
        if not rows:
            self.resolved_columns = {}
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        self.resolved_columns = _resolve_columns(df.columns)
        df = df.rename(columns=self.resolved_columns)

        for col in _NUMERIC_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in _TEXT_COLUMNS:
            if col in df.columns:
                df[col] = df[col].astype(str)
        return df

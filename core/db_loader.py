"""
core/db_loader.py — the reference library, read from Postgres.

W3 of docs/PLAN-supabase-migration.md, and the one change the whole plan turns
on. `Catalog.load()` hands `Repository` a dict[str -> DataFrame] keyed by
SHEET_MAP; everything downstream — Repository, SearchIndex, MatchingService,
ExportService, all the Streamlit pages — sees only that dict. Produce the same
dict from the database and nothing else in the app has to change.

SO THIS FILE'S ONLY JOB IS FIDELITY
-----------------------------------
Not "load the data" — load it so exactly that the app cannot tell. Two things
make that harder than it sounds, and both come from how Catalog reads Excel:

    raw = pd.read_excel(path, sheet_name=None, dtype=str)

1. EVERY column arrives as a STRING. Grade 2 is "2", Factor 1.05 is "1.05".
   Postgres returns integers and Decimals, so every value is rendered back to
   text here. Only Min, Max and Order are then coerced to numeric, because
   Catalog does exactly that and nothing else.

2. Blank cells are NaN, not None. Repository's _isna() treats both as missing,
   but a parity test comparing frames does not, so nulls become NaN.

THE COLUMN NAMES COME FROM THE IMPORTER
---------------------------------------
services/library_import_service.SPECS already maps workbook column -> database
column for every table. Reading it backwards gives database -> workbook, which
is precisely what this needs. Deriving it rather than restating it means the
writer and the reader cannot drift apart: add a column to SPECS and both halves
learn about it at once.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger("jobsy")

try:
    from core.catalog import SHEET_MAP
except ImportError:  # pragma: no cover
    from jobsy.core.catalog import SHEET_MAP

# Columns Catalog turns back into numbers after reading everything as text.
# Kept identical to core/catalog.py rather than improved on: a loader that is
# more helpful than the thing it replaces is a loader that fails parity.
NUMERIC_COLUMNS = ("Min", "Max", "Order")

# Provenance and bookkeeping. Real columns, but not part of any sheet, so they
# are dropped before the frame reaches Repository — which would otherwise see
# columns the workbook never had.
INTERNAL_COLUMNS = frozenset({
    "id", "org_id", "revision_id", "status", "owner", "source",
    "effective_from", "effective_to", "created_at", "updated_at", "updated_by",
    "path_status",
})

# Governance columns the workbook holds as plain dates. Postgres stores them as
# timestamptz and PostgREST renders '2026-07-02T00:00:00+00:00' where Excel says
# '2026-07-02'. The importer writes date-only (_clean calls .date().isoformat()),
# so every one of those times is midnight and the date is the whole value —
# rendering it back as a date loses nothing and keeps an ISO timestamp out of
# anything the app exports to Excel.
DATE_COLUMNS = ("effective_from", "updated_at", "effective_to")

PAGE = 1000  # PostgREST caps a response; benefits_observations alone is 1008 rows


def _specs():
    try:
        from services.library_import_service import SPECS
    except ImportError:  # pragma: no cover
        from jobsy.services.library_import_service import SPECS
    return SPECS


def _to_text(value: Any) -> Any:
    """Render one database value the way pd.read_excel(dtype=str) would.

    Numbers are the whole difficulty. Excel reads a whole number as "2", not
    "2.0", and Postgres hands back 2, 2.0 or Decimal('2.00') depending on the
    column type — so a float that is really an integer is normalised before it
    is stringified. Anything else would put "2.0" where the workbook says "2"
    and fail parity on a difference that is not real.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value != value:                      # NaN
            return None
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    # Decimal, date, datetime, everything else
    text = str(value)
    if text.replace(".", "", 1).replace("-", "", 1).isdigit() and "." in text:
        try:
            f = float(text)
            return str(int(f)) if f.is_integer() else text
        except ValueError:
            pass
    return text


def _render(db_col: str, value: Any) -> Any:
    """_to_text(), plus the date truncation the timestamptz columns need."""
    text = _to_text(value)
    if db_col in DATE_COLUMNS and isinstance(text, str) and "T" in text:
        return text.split("T", 1)[0]
    return text


def _fetch_all(client, table: str, org_id: str) -> list[dict]:
    """Every active row of one table, paged.

    PostgREST returns at most a page per request. benefits_observations has
    1,008 rows, so a single unpaged select would silently return the first
    1,000 and the library would come back quietly incomplete — the failure
    mode this whole migration exists to stop.
    """
    rows: list[dict] = []
    start = 0
    while True:
        resp = (client.table(table)
                .select("*")
                .eq("org_id", org_id)
                .eq("status", "active")
                .range(start, start + PAGE - 1)
                .execute())
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        start += PAGE


def load_frames(client, org_id: str) -> dict[str, pd.DataFrame]:
    """Read the library from Postgres as the dict Repository expects.

    Keys are SHEET_MAP's repository keys ('jobs', 'profiles', 'salary', …) and
    columns carry the WORKBOOK's names, because that is what Repository reads.

    There used to be an include_all flag for the tables SHEET_MAP had no entry
    for — pay_mix and pay_elements — so the variable-pay analysis could reach
    past the loader and read them itself. Since 2026-09-03 both are in
    SHEET_MAP, the two sets are the same, and the flag had nothing left to
    include. A table with no entry is now logged rather than skipped in
    silence: nothing loading it is exactly the condition that made those two
    invisible to Data Quality, to the export and to the parity gate.
    """
    frames: dict[str, pd.DataFrame] = {}

    for spec in _specs():
        db_to_workbook = {db: wb for wb, db in spec.columns.items()}
        repo_key = SHEET_MAP.get(spec.sheet)
        if repo_key is None:
            logger.warning(
                "Table '%s' is in the library but has no SHEET_MAP entry, so nothing loads it "
                "and no panel can see it.", spec.table)
            continue

        rows = _fetch_all(client, spec.table, org_id)

        records = []
        for row in rows:
            rec = {}
            for db_col, wb_col in db_to_workbook.items():
                rec[wb_col] = _render(db_col, row.get(db_col))
            # The governance columns are real workbook columns too, and the
            # Data Quality page reads UpdatedAt to judge staleness.
            for db_col, wb_col in (("owner", "Owner"), ("status", "Status"),
                                   ("effective_from", "EffectiveFrom"),
                                   ("source", "Source"), ("updated_at", "UpdatedAt")):
                if db_col in row:
                    rec[wb_col] = _render(db_col, row.get(db_col))
            # CareerPaths' Status means top-of-ladder, not lifecycle — see 0002.
            if spec.status_column and spec.status_column in row:
                rec["Status"] = _to_text(row.get(spec.status_column))
            records.append(rec)

        columns = list(spec.columns.keys()) + ["Source", "Owner", "Status",
                                               "EffectiveFrom", "UpdatedAt"]
        df = pd.DataFrame(records, columns=columns)

        # Catalog coerces exactly these back to numbers, so this does too.
        for col in NUMERIC_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        frames[repo_key] = df
        logger.info("  %s: %d rows (db)", spec.table, len(df))

    return frames


def client_and_org():
    """A Supabase client and the org id, resolved from configuration.

    Split out of load_frames_from_config so anything else that needs to read
    this project — the audit-trail panel, for one — gets the same client and
    the same org, rather than a second answer to "which key, and where from"
    that can disagree with this one.
    """
    try:
        from services.library_import_service import _resolve_credentials, _require_writable_key
    except ImportError:  # pragma: no cover
        from jobsy.services.library_import_service import _resolve_credentials, _require_writable_key

    url, key = _resolve_credentials()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SECRET_KEY are required to load the library from the "
            "database. Set them, or leave LIBRARY_SOURCE as 'excel'.")
    for note in _require_writable_key(key):
        logger.warning("%s", note)

    from supabase import create_client
    client = create_client(url, key)

    org_slug = "default"
    try:
        from core.config import LIBRARY_ORG_SLUG
        org_slug = LIBRARY_ORG_SLUG
    except Exception:
        pass

    org = client.table("orgs").select("id").eq("slug", org_slug).single().execute()
    if not org.data:
        raise RuntimeError(f"No organisation with slug '{org_slug}'.")
    return client, org.data["id"]


def load_frames_from_config() -> dict[str, pd.DataFrame]:
    """load_frames() with the client and org resolved from configuration."""
    client, org_id = client_and_org()
    return load_frames(client, org_id)

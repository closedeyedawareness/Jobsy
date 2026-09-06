"""
library_export_service.py — the reference library back out as a workbook.

Since the cutover (commit 2095098) Postgres is the master and
jobsy_reference_library.xlsx is a file in the repo that nothing reads. That is
the right direction and a bad place to stop: the workbook is still how a human
reads the library, how it gets reviewed, and how it would be restored if the
database were lost. So the export exists to make the workbook a *snapshot* —
produced on demand from whatever the app is actually reading — rather than a
second master that quietly drifts.

Two properties this is built around:

  1. **It round-trips.** The sheets are written under the names SHEET_MAP
     expects, so `Catalog(path, source="excel")` can read an exported file back
     and build the same library. That is what makes it a restore path and not
     just a report, and tests/test_library_export_service.py pins it.
  2. **It says where it came from.** An extra `ExportInfo` sheet records the
     source (db or excel), the moment of export, and the row count per sheet.
     A workbook that does not say whether it is a snapshot of the database or a
     copy of an older workbook is exactly the ambiguity the migration removed.

`ExportInfo` is not in SHEET_MAP, so re-importing the file ignores it.

A note on the paragraph below, kept out of it on purpose. It once counted the
sheets and listed pay_mix and pay_elements as tables "nothing loads yet"; by
6 September 2026 the map had grown well past that count and held both of them.
A stale honest-limit is worse than none, because this is the one place a reader
is told what the export does NOT contain — name the wrong omissions and the
honesty becomes decorative. So it now names no count and no table, and
`test_the_honest_limit_stays_true` keeps it that way.

HONEST LIMIT — this is a snapshot of the LIBRARY THE APP READS, not a backup of
the database. The app loads every sheet in SHEET_MAP; what a workbook cannot
hold is the append-only library_audit and library_revisions history. Restoring
from this file restores what the app uses and loses that trail. The ExportInfo
sheet reports the sheet and row counts so the difference is visible rather than
assumed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

import pandas as pd

from core.catalog import SHEET_MAP

__all__ = ["LibraryExportService", "export_bytes", "export_to_path"]

#: repository key → workbook sheet name (SHEET_MAP the other way round)
_KEY_TO_SHEET = {key: sheet for sheet, key in SHEET_MAP.items()}

_INFO_SHEET = "ExportInfo"


class LibraryExportService:
    """Writes a loaded Catalog's frames back into a workbook."""

    def __init__(self, catalog):
        if not getattr(catalog, "frames", None):
            # An unloaded catalog would export an empty workbook that still
            # looks like a valid library file — the worst possible artifact.
            raise ValueError(
                "The catalog holds no frames. Call catalog.load() before exporting; "
                "an empty export would look like a valid but empty library."
            )
        self.catalog = catalog

    # ── frames ───────────────────────────────────────────────────────────────

    def sheets(self) -> dict[str, pd.DataFrame]:
        """The frames to write, keyed by workbook sheet name, in SHEET_MAP order."""
        out: dict[str, pd.DataFrame] = {}
        for sheet, key in SHEET_MAP.items():
            df = self.catalog.frames.get(key)
            if df is not None:
                out[sheet] = df
        return out

    def info_frame(self, sheets: Optional[dict] = None) -> pd.DataFrame:
        """Provenance: what this snapshot is of, when, and how much of it."""
        sheets = self.sheets() if sheets is None else sheets
        source = getattr(self.catalog, "active_source", None) or "unknown"
        exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        rows = [
            {"Item": "Exported at (UTC)", "Value": exported_at},
            {"Item": "Read from", "Value": source},
            {"Item": "Sheets", "Value": str(len(sheets))},
            {"Item": "Rows", "Value": str(sum(len(df) for df in sheets.values()))},
        ]
        if getattr(self.catalog, "fell_back_to_excel", False):
            rows.append({
                "Item": "Warning",
                "Value": ("The database was asked for and did not answer; this is a copy of the "
                          "workbook, not a snapshot of the master."),
            })
        rows.append({"Item": "", "Value": ""})
        for sheet, df in sheets.items():
            rows.append({"Item": f"{sheet} rows", "Value": str(len(df))})
        return pd.DataFrame(rows)

    # ── output ───────────────────────────────────────────────────────────────

    def write(self, target) -> None:
        """Write the workbook to a path or an open binary buffer."""
        sheets = self.sheets()
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            for sheet, df in sheets.items():
                # Excel sheet names cap at 31 characters; none of ours reach it,
                # but a silently truncated name would break the round trip.
                df.to_excel(writer, sheet_name=sheet[:31], index=False)
            self.info_frame(sheets).to_excel(writer, sheet_name=_INFO_SHEET, index=False)

    def to_bytes(self) -> bytes:
        """For Streamlit's download_button."""
        buf = BytesIO()
        self.write(buf)
        return buf.getvalue()

    def suggested_filename(self) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        source = getattr(self.catalog, "active_source", None) or "library"
        return f"jobsy_reference_library-{source}-{stamp}.xlsx"


def export_bytes(catalog) -> bytes:
    return LibraryExportService(catalog).to_bytes()


def export_to_path(catalog, path) -> Path:
    path = Path(path)
    LibraryExportService(catalog).write(path)
    return path

"""
jobsy/services/pay_equity_export_service.py

Turns a PayGapResult (services.pay_equity_service.analyze_gender_pay_gap) into a
formatted Excel workbook so a structural gender pay-gap run can leave the app as
a shareable report — mirrors services.export_service.ExportService, but for the
band-free Function x Level gap instead of matched titles.

Two entry points:

    to_workbook_bytes(result) -> bytes   (for Streamlit download_button)
    write_workbook(result, path) -> Path (to disk)

Workbook layout:
    Summary         headline mean/median/adjusted gap, representation, notes
    Cohorts         every Function x Level cohort with both men and women
    Representation  % women by level and by function

The export is a static snapshot of one analysis run, so it holds values rather
than formulas.

Sign convention: PayGapResult itself reports gaps as "positive = men paid
more" (matches what the live Jobsy UI shows). This export instead reports
"positive = women paid more" -- (vrouw - man) / man -- to match the NL
wetsvoorstel's own definition of "loonkloof", since that's the wording this
report gets checked against. Same magnitude, opposite sign; see _flip_sign.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

import logging
logger = logging.getLogger('jobsy')
from services.pay_equity_service import PayGapResult, DIRECTIVE_THRESHOLD_PCT

__all__ = ["PayEquityExportService"]

_GAP_PCT_FMT = '+0.0"%";-0.0"%"'  # values are already 0-100 scale, not 0-1 -- no native '%' format


def _flip_sign(value: float | None) -> float | None:
    """PayGapResult's 'positive = men paid more' -> this report's
    'positive = women paid more', per the wetsvoorstel's (vrouw-man)/man."""
    return None if value is None else round(-value, 1)


def _flip_ci(ci: tuple[float, float] | None) -> tuple[float | None, float | None]:
    """Negating an interval also reverses which bound is the low one."""
    if ci is None:
        return None, None
    lo, hi = ci
    return _flip_sign(hi), _flip_sign(lo)


class PayEquityExportService:
    """Renders a PayGapResult to a styled workbook."""

    # ------------------------------------------------------------- dataframes
    def summary_to_dataframe(self, r: PayGapResult) -> pd.DataFrame:
        ci_lo, ci_hi = _flip_ci(r.adjusted_ci)
        rows = [
            ("Employees in scope", r.n),
            ("Men (M)", r.n_m),
            ("Women (F)", r.n_f),
            ("Excluded (non-binary / unknown gender)", r.n_excluded),
            ("FTE-normalised", "Yes" if r.fte_normalised else "No"),
            (None, None),
            ("Mean gap % — unadjusted (+ = women paid more, per wetsvoorstel (vrouw-man)/man)",
             _flip_sign(r.mean_gap_pct)),
            ("Median gap % — unadjusted (+ = women paid more)", _flip_sign(r.median_gap_pct)),
            (None, None),
            ("Adjusted gap % (controls for function + level; + = women paid more)",
             _flip_sign(r.adjusted_gap_pct)),
            ("Adjusted 95% CI — low", ci_lo),
            ("Adjusted 95% CI — high", ci_hi),
            ("Adjusted gap statistically significant",
             None if r.adjusted_significant is None else ("Yes" if r.adjusted_significant else "No")),
            (None, None),
            ("Cohorts tested (Function x Level, both genders)", r.n_cohorts_tested),
            (f"Cohorts flagged (|gap| >= {DIRECTIVE_THRESHOLD_PCT:.0f}%)", r.n_cohorts_flagged),
            ("  ...of which reliable (n >= 5 each gender)", r.n_cohorts_flagged_reliable),
            ("Cohorts below the n>=5-per-gender reliability threshold (low-n, indicative only)",
             sum(1 for c in r.cohorts if not c.reliable)),
            (None, None),
            ("% women overall", r.pct_women_overall),
        ]
        return pd.DataFrame(rows, columns=["Metric", "Value"])

    def cohorts_to_dataframe(self, r: PayGapResult) -> pd.DataFrame:
        rows = [{
            "Function": c.function, "Level": c.level,
            "n Male": c.n_m, "n Female": c.n_f,
            "Mean M": c.mean_m, "Mean F": c.mean_f,
            "Median M": c.median_m, "Median F": c.median_f,
            "Mean gap % (+ = women paid more)": _flip_sign(c.mean_gap_pct),
            "Median gap % (+ = women paid more)": _flip_sign(c.median_gap_pct),
            f"Flagged (>= {DIRECTIVE_THRESHOLD_PCT:.0f}%)": "Yes" if c.flagged else "No",
            "Reliable (n>=5 each)": "Yes" if c.reliable else "No",
        } for c in r.cohorts]
        return pd.DataFrame(rows)

    def representation_to_dataframe(self, r: PayGapResult, by: str) -> pd.DataFrame:
        data = r.women_by_level if by == "level" else r.women_by_function
        label = "Level" if by == "level" else "Function"
        rows = [{label: k, "% women": v} for k, v in data.items()]
        return pd.DataFrame(rows, columns=[label, "% women"])

    def notes_to_dataframe(self, r: PayGapResult) -> pd.DataFrame:
        sign_note = ("Sign convention: figures in this report are (vrouw - man) / man, i.e. "
                     "positive = women paid more -- matching the NL wetsvoorstel's definition of "
                     "'loonkloof'. The live Jobsy screen instead shows (man - vrouw) / man "
                     "(positive = men paid more); same magnitude, opposite sign.")
        return pd.DataFrame({"Notes": [sign_note, *r.notes]})

    # --------------------------------------------------------------- exporters
    def to_workbook_bytes(self, result: PayGapResult) -> bytes:
        summary = self.summary_to_dataframe(result)
        cohorts = self.cohorts_to_dataframe(result)
        by_level = self.representation_to_dataframe(result, "level")
        by_function = self.representation_to_dataframe(result, "function")
        notes = self.notes_to_dataframe(result)

        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="Summary", index=False)
            if not cohorts.empty:
                cohorts.to_excel(writer, sheet_name="Cohorts", index=False)
            rep_split_row = None
            if not by_level.empty or not by_function.empty:
                by_level.to_excel(writer, sheet_name="Representation", index=False, startrow=0)
                rep_split_row = len(by_level) + 2  # 0-indexed row the second table's header lands on
                by_function.to_excel(writer, sheet_name="Representation", index=False, startrow=rep_split_row)
            if not notes.empty:
                notes.to_excel(writer, sheet_name="Notes", index=False)
            try:
                self._format_summary_sheet(writer.sheets["Summary"])
                if not cohorts.empty:
                    self._format_data_sheet(writer.sheets["Cohorts"], cohorts)
                if "Representation" in writer.sheets:
                    self._format_representation_sheet(writer.sheets["Representation"], rep_split_row)
                if "Notes" in writer.sheets:
                    self._format_data_sheet(writer.sheets["Notes"], notes)
            except Exception as exc:  # formatting must never break the export
                logger.warning("Pay-equity workbook formatting skipped: %s", exc)

        logger.info("Exported pay-equity report: n=%d (M=%d, F=%d), %d cohorts.",
                    result.n, result.n_m, result.n_f, result.n_cohorts_tested)
        return buffer.getvalue()

    def write_workbook(self, result: PayGapResult, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.to_workbook_bytes(result))
        return path

    # ---------------------------------------------------------------- styling
    def _header_row_style(self, ws, row: int = 1):
        from openpyxl.styles import Alignment, Font, PatternFill
        header_font = Font(name="Arial", bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="0E7C66")
        center = Alignment(horizontal="center", vertical="center")
        for cell in ws[row]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center

    def _format_summary_sheet(self, ws) -> None:
        from openpyxl.styles import Font
        self._header_row_style(ws)
        ws.freeze_panes = "A2"
        ws.column_dimensions["A"].width = 48
        ws.column_dimensions["B"].width = 16
        bold = Font(name="Arial", bold=True)
        for row in range(2, ws.max_row + 1):
            label_cell = ws.cell(row=row, column=1)
            label = label_cell.value
            if label is None:
                continue
            if "gap %" in str(label).lower() or "% women" in str(label).lower():
                ws.cell(row=row, column=2).number_format = _GAP_PCT_FMT
            if str(label).startswith(("Mean gap", "Adjusted gap %")):
                label_cell.font = bold
                ws.cell(row=row, column=2).font = bold

    def _format_data_sheet(self, ws, df: pd.DataFrame) -> None:
        from openpyxl.utils import get_column_letter
        self._header_row_style(ws)
        ws.freeze_panes = "A2"
        if ws.max_row >= 1 and ws.max_column >= 1:
            ws.auto_filter.ref = ws.dimensions
        for idx, header in enumerate(df.columns, start=1):
            lengths = df[header].fillna("").astype(str).map(len)
            longest = int(lengths.max()) if len(lengths) else 0
            width = min(60, max(len(str(header)) + 2, longest + 2))
            ws.column_dimensions[get_column_letter(idx)].width = width
            if "gap %" in str(header).lower():
                for row in range(2, ws.max_row + 1):
                    ws.cell(row=row, column=idx).number_format = _GAP_PCT_FMT

    def _format_representation_sheet(self, ws, second_header_row: int | None) -> None:
        self._header_row_style(ws, row=1)
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 12
        if second_header_row is not None:
            # startrow is 0-indexed and counts from the top of the sheet; the
            # openpyxl row housing that header is 1-indexed, hence the +1.
            self._header_row_style(ws, row=second_header_row + 1)

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
    Summary         headline mean/median/adjusted gap, representation, notes,
                     a reliable-cohorts mini-table and a Male-vs-Female bar chart
    Cohorts         every Function x Level cohort with both men and women
    Representation  % women by level and by function

The export is a static snapshot of one analysis run, so it holds values rather
than formulas.

Sign convention: PayGapResult's own fields are "positive = men paid more".
This export instead reports "positive = women paid more" -- (vrouw - man) /
man -- to match the NL wetsvoorstel's own definition of "loonkloof", since
that's the wording this report gets checked against. The live Jobsy screen
applies the same flip (see ui/app.py::_render_leveled_gap) so the two never
disagree; see services.pay_equity_service.flip_gap_sign / flip_gap_ci.

Styling is deliberately on-brand: header fill and chart series use the same
hex values as ui/theme.py's COLORS (copied here as literals rather than
imported, so this module -- pure pandas/openpyxl -- never needs streamlit
importable; keep the two in sync by hand if the Jobsy palette changes), and
gap values are colour-coded with the same danger/teal threshold logic as
_render_leveled_gap's on-screen _col().
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

import logging
logger = logging.getLogger('jobsy')
from services.pay_equity_service import PayGapResult, DIRECTIVE_THRESHOLD_PCT, flip_gap_sign, flip_gap_ci

__all__ = ["PayEquityExportService"]

_GAP_PCT_FMT = '+0.0"%";-0.0"%"'  # values are already 0-100 scale, not 0-1 -- no native '%' format

# Jobsy brand palette (ui/theme.py COLORS) -- hex without the '#', as openpyxl wants it.
_PURPLE = "6F3CFF"    # primary -- header fill, Male chart series
_PINK = "FF73D0"      # accent -- Female chart series
_TEAL = "34B5FF"      # secondary -- on-screen "fine" gap colour
_DANGER = "FF5A7A"    # clay -- on-screen "flagged" gap colour
_DANGER_SOFT = "FDE3E9"
_TEAL_SOFT = "E2F2FF"
_INK = "1A1A2E"


class PayEquityExportService:
    """Renders a PayGapResult to a styled workbook."""

    # ------------------------------------------------------------- dataframes
    def summary_to_dataframe(self, r: PayGapResult) -> pd.DataFrame:
        ci_lo, ci_hi = flip_gap_ci(r.adjusted_ci) or (None, None)
        rows = [
            ("Employees in scope", r.n),
            ("Men (M)", r.n_m),
            ("Women (F)", r.n_f),
            ("Excluded (non-binary / unknown gender)", r.n_excluded),
            ("FTE-normalised", "Yes" if r.fte_normalised else "No"),
            (None, None),
            ("Mean gap % — unadjusted (+ = women paid more, per wetsvoorstel (vrouw-man)/man)",
             flip_gap_sign(r.mean_gap_pct)),
            ("Median gap % — unadjusted (+ = women paid more)", flip_gap_sign(r.median_gap_pct)),
            (None, None),
            ("Adjusted gap % (controls for function + level; + = women paid more)",
             flip_gap_sign(r.adjusted_gap_pct)),
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
            "Mean gap % (+ = women paid more)": flip_gap_sign(c.mean_gap_pct),
            "Median gap % (+ = women paid more)": flip_gap_sign(c.median_gap_pct),
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
                     "'loonkloof'. The live Jobsy screen uses the same convention.")
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
                self._add_reliable_chart(writer.sheets["Summary"], result, start_row=len(summary) + 3)
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
    def _gap_color(self, value) -> str:
        """Same threshold logic as the on-screen _col() in ui/app.py::_render_leveled_gap.
        Guards on type, not just `is not None` -- pandas writes a blank Value cell
        (e.g. Adjusted gap % when the regression has too few rows) as '' once it
        shares a mixed-type column with strings like FTE-normalised's 'Yes'/'No',
        not as a true empty cell, so `value` can be '' here rather than None."""
        if not isinstance(value, (int, float)):
            return _TEAL
        return _DANGER if abs(value) >= DIRECTIVE_THRESHOLD_PCT else _TEAL

    def _header_row_style(self, ws, row: int = 1):
        from openpyxl.styles import Alignment, Font, PatternFill
        header_font = Font(name="Arial", bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor=_PURPLE)
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
            value_cell = ws.cell(row=row, column=2)
            if "gap %" in str(label).lower() or "% women" in str(label).lower():
                value_cell.number_format = _GAP_PCT_FMT
            if str(label).startswith(("Mean gap", "Median gap", "Adjusted gap %")):
                colour = self._gap_color(value_cell.value)
                label_cell.font = Font(name="Arial", bold=True)
                value_cell.font = Font(name="Arial", bold=True, color=colour)

    def _add_reliable_chart(self, ws, r: PayGapResult, start_row: int) -> None:
        """A small Function-x-Level table (reliable cohorts only, n>=5 each gender)
        feeding a clustered Male-vs-Female bar chart, in Jobsy's brand colours."""
        from openpyxl.chart import BarChart, Reference
        from openpyxl.styles import Font, PatternFill

        reliable = [c for c in r.cohorts if c.reliable]
        if not reliable:
            ws.cell(start_row, 1, "No cohort has a reliable (n>=5 each gender) sample -- no chart to show.")
            ws.cell(start_row, 1).font = Font(name="Arial", italic=True, color="6B7684")
            return

        ws.cell(start_row, 1, "Reliable cohorts — mean pay by gender (n>=5 each)")
        ws.cell(start_row, 1).font = Font(name="Arial", bold=True)

        hdr_row = start_row + 1
        for col, label in enumerate(["Function x Level", "Mean M", "Mean F"], start=1):
            cell = ws.cell(hdr_row, col, label)
            cell.font = Font(name="Arial", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=_PURPLE)

        for i, c in enumerate(reliable):
            row = hdr_row + 1 + i
            ws.cell(row, 1, f"{c.function}-{c.level}")
            ws.cell(row, 2, c.mean_m).number_format = "#,##0"
            ws.cell(row, 3, c.mean_f).number_format = "#,##0"
        last_row = hdr_row + len(reliable)

        chart = BarChart()
        chart.type = "col"
        chart.grouping = "clustered"
        chart.title = "Mean pay by cohort, Male vs Female (reliable cohorts only)"
        chart.y_axis.title = "Salary"
        chart.x_axis.title = "Function x Level"
        chart.height, chart.width = 8, 16
        cats = Reference(ws, min_col=1, min_row=hdr_row + 1, max_row=last_row)
        data = Reference(ws, min_col=2, max_col=3, min_row=hdr_row, max_row=last_row)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        chart.series[0].graphicalProperties.solidFill = _PURPLE  # Mean M
        chart.series[1].graphicalProperties.solidFill = _PINK    # Mean F
        ws.add_chart(chart, f"E{start_row}")

    def _format_data_sheet(self, ws, df: pd.DataFrame) -> None:
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
        self._header_row_style(ws)
        ws.freeze_panes = "A2"
        if ws.max_row >= 1 and ws.max_column >= 1:
            ws.auto_filter.ref = ws.dimensions
        status_fill = {
            "Yes": PatternFill("solid", fgColor=_DANGER_SOFT),
            "No": PatternFill("solid", fgColor=_TEAL_SOFT),
        }
        for idx, header in enumerate(df.columns, start=1):
            lengths = df[header].fillna("").astype(str).map(len)
            longest = int(lengths.max()) if len(lengths) else 0
            width = min(60, max(len(str(header)) + 2, longest + 2))
            ws.column_dimensions[get_column_letter(idx)].width = width
            header_l = str(header).lower()
            if "gap %" in header_l:
                for row in range(2, ws.max_row + 1):
                    cell = ws.cell(row=row, column=idx)
                    cell.number_format = _GAP_PCT_FMT
                    cell.font = Font(name="Arial", color=self._gap_color(cell.value))
            elif header_l.startswith("flagged"):
                for row in range(2, ws.max_row + 1):
                    cell = ws.cell(row=row, column=idx)
                    cell.fill = status_fill.get(cell.value, status_fill["No"])

    def _format_representation_sheet(self, ws, second_header_row: int | None) -> None:
        self._header_row_style(ws, row=1)
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 12
        if second_header_row is not None:
            # startrow is 0-indexed and counts from the top of the sheet; the
            # openpyxl row housing that header is 1-indexed, hence the +1.
            self._header_row_style(ws, row=second_header_row + 1)

"""
jobsy/core/validator.py

Validates the loaded reference workbook before the Repository trusts it.

Two tiers:
    errors    structural problems that make the catalog unsafe to use
              (missing sheet, missing key column, empty Jobs, duplicate JobIDs)
    warnings  data-quality issues worth surfacing but not fatal
              (salary min > max, mappings/profiles pointing at unknown jobs)

`validate(data, strict=True)` raises ValidationError when there are errors;
with strict=False it returns the report so a UI can show problems instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.exceptions import ValidationError
from core.logger import logger

__all__ = ["Validator", "ValidationReport"]


def _isna(value) -> bool:
    if value is None:
        return True
    # NaN is the only value not equal to itself
    if value != value:  # noqa: PLR0124
        return True
    return str(value).strip() == "" or str(value).strip().lower() == "nan"


def _find_col(df, *names: str):
    """Return the first matching column name present in the DataFrame, or None."""
    cols = set(df.columns)
    for name in names:
        if name in cols:
            return name
    return None


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [f"ERROR: {e}" for e in self.errors] + [f"warn:  {w}" for w in self.warnings]
        return "\n".join(lines) if lines else "OK"


class Validator:
    REQUIRED = ["jobs", "profiles", "titles", "salary", "career", "levels", "employees"]

    # one tuple of acceptable aliases per required column
    REQUIRED_COLUMNS = {
        "jobs": [("JobID", "job_id"),
                 ("StandardTitle", "standard_title", "Title", "title"),
                 ("Function", "function"),
                 ("Level", "level")],
        "profiles": [("JobID", "job_id")],
        "titles": [("ExistingTitle", "existing_title", "Title", "title")],
        "salary": [("Function", "function"), ("Level", "level")],
        "employees": [("EmployeeID", "employee_id", "ID", "id")],
    }

    def validate(self, data: dict, *, strict: bool = True) -> ValidationReport:
        report = ValidationReport()

        # 1. required sheets present
        for sheet in self.REQUIRED:
            if sheet not in data or data[sheet] is None:
                report.errors.append(f"Missing required sheet '{sheet}'.")

        # 2. required columns present (only for sheets we actually have)
        for sheet, requirements in self.REQUIRED_COLUMNS.items():
            df = data.get(sheet)
            if df is None:
                continue
            for aliases in requirements:
                if _find_col(df, *aliases) is None:
                    report.errors.append(
                        f"Sheet '{sheet}' is missing a column for {aliases[0]} "
                        f"(accepted: {', '.join(aliases)})."
                    )

        # stop here if the structure is already broken
        if report.errors:
            return self._finish(report, strict)

        # 3. content checks (guarded so a malformed frame can't crash validation)
        try:
            self._check_jobs(data, report)
            self._check_salary(data, report)
            self._check_references(data, report)
        except Exception as exc:  # pragma: no cover - defensive
            report.warnings.append(f"Validation halted early: {exc}")

        return self._finish(report, strict)

    # ------------------------------------------------------------- content
    def _check_jobs(self, data, report: ValidationReport) -> None:
        df = data["jobs"]
        if len(df) == 0:
            report.errors.append("Jobs sheet is empty.")
            return
        id_col = _find_col(df, "JobID", "job_id")
        ids = [v for v in df[id_col].tolist() if not _isna(v)]
        dupes = {x for x in ids if ids.count(x) > 1}
        if dupes:
            report.errors.append(f"Duplicate JobIDs: {', '.join(map(str, sorted(dupes)))}.")

    def _check_salary(self, data, report: ValidationReport) -> None:
        df = data["salary"]
        lo_col = _find_col(df, "Min", "min", "MinSalary", "salary_min", "Low", "low")
        hi_col = _find_col(df, "Max", "max", "MaxSalary", "salary_max", "High", "high")
        if not lo_col or not hi_col:
            report.warnings.append("SalaryBands has no recognisable Min/Max columns.")
            return
        for i, row in df.iterrows():
            lo, hi = row[lo_col], row[hi_col]
            if _isna(lo) or _isna(hi):
                continue
            try:
                if float(lo) > float(hi):
                    report.warnings.append(f"SalaryBands row {i}: min ({lo}) > max ({hi}).")
            except (TypeError, ValueError):
                report.warnings.append(f"SalaryBands row {i}: non-numeric salary.")

    def _check_references(self, data, report: ValidationReport) -> None:
        jobs_df = data["jobs"]
        id_col = _find_col(jobs_df, "JobID", "job_id")
        known = {str(v).strip() for v in jobs_df[id_col].tolist() if not _isna(v)}

        for sheet in ("profiles", "titles", "career"):
            df = data.get(sheet)
            if df is None:
                continue
            ref_col = _find_col(df, "JobID", "job_id")
            if not ref_col:
                continue  # e.g. TitleMapping keyed by StandardTitle instead
            unknown = {str(v).strip() for v in df[ref_col].tolist()
                       if not _isna(v) and str(v).strip() not in known}
            if unknown:
                report.warnings.append(
                    f"Sheet '{sheet}' references unknown JobIDs: "
                    f"{', '.join(sorted(unknown))}."
                )

    # --------------------------------------------------------------- finish
    def _finish(self, report: ValidationReport, strict: bool) -> ValidationReport:
        for w in report.warnings:
            logger.warning("Validation: %s", w)
        if report.errors:
            logger.error("Validation failed with %d error(s).", len(report.errors))
            if strict:
                raise ValidationError("Reference library failed validation:\n" + str(report))
        else:
            logger.info("Validation passed (%d warning(s)).", len(report.warnings))
        return report

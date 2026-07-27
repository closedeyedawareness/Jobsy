"""
library_import_service.py — reference workbook -> Postgres.

W2 of docs/PLAN-supabase-migration.md. Reads jobsy_reference_library.xlsx and
upserts every sheet into the tables 0001_reference_library.sql created.

    python -m services.library_import_service                       # dry run
    python -m services.library_import_service --write               # do it
    python -m services.library_import_service other.xlsx --write

TWO HALVES, ON PURPOSE
----------------------
``build_rows()`` turns the workbook into the exact row dicts the database
should hold, and touches no network. ``import_library()`` writes them. The
split is what makes the interesting half testable: everything that could
mis-map a column, drop a governance field or invent a value is in the pure
function, and a dry run exercises all of it against a real workbook without a
service key or a database.

VALIDATION RUNS BEFORE ANYTHING IS WRITTEN
------------------------------------------
core/validator.py sees the frames first. A workbook that fails validation is
refused rather than partially loaded — the schema would reject most of it
anyway, but failing at the door gives one clear error instead of a scatter of
constraint violations halfway through a table.

STATUS IS LOWERCASED
--------------------
The workbook writes "Active"; the check constraint accepts 'active'. That is
deliberate: one vocabulary in the database, and the importer is the place the
two meet. Anything unrecognised is left alone so the constraint rejects it
loudly instead of the importer quietly rewriting it to something legal.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import pandas as pd

try:
    from core.validator import Validator
    from core.catalog import SHEET_MAP
except ImportError:  # pragma: no cover - package-relative fallback
    from jobsy.core.validator import Validator
    from jobsy.core.catalog import SHEET_MAP


DEFAULT_WORKBOOK = "jobsy_reference_library.xlsx"

# Governance columns, present on every reference sheet in the workbook. These
# are not new metadata invented for the database — see the header of
# 0001_reference_library.sql.
GOVERNANCE = {
    "Owner": "owner",
    "Status": "status",
    "EffectiveFrom": "effective_from",
    "Source": "source",
    "UpdatedAt": "updated_at",
}

VALID_STATUS = {"active", "draft", "retired"}


@dataclass(frozen=True)
class TableSpec:
    sheet: str
    table: str
    key: tuple[str, ...]          # natural key, matching the unique constraint
    columns: dict[str, str]       # workbook column -> db column
    # Sheets whose Status column does NOT carry the governance vocabulary. See
    # 0002: CareerPaths says 'Terminal' to mean top-of-ladder, not a lifecycle
    # state, so its Status is routed here and governance status stays 'active'.
    status_column: str | None = None


# Order matters: a table may only appear after everything it references.
# jobs, skills and industries are the three parents in the schema.
SPECS: list[TableSpec] = [
    TableSpec("Jobs", "jobs", ("job_id",), {
        "JobID": "job_id", "StandardTitle": "standard_title", "Function": "function",
        "Level": "level", "Category": "category", "Grade": "grade",
        "IscoGroup": "isco_group", "IscoTitle": "isco_title", "EscoLabel": "esco_label"}),
    TableSpec("Skills", "skills", ("skill_id",), {
        "SkillID": "skill_id", "SkillName": "skill_name", "Category": "category",
        "Definition": "definition"}),
    TableSpec("Industries", "industries", ("industry_id",), {
        "IndustryID": "industry_id", "IndustryName": "industry_name", "Scope": "scope",
        "Characteristics": "characteristics"}),

    # No foreign keys of their own.
    TableSpec("Levels", "levels", ("level",), {"Level": "level", "Order": "order"}),
    TableSpec("Categories", "categories", ("category",), {
        "Category": "category", "Function": "function", "Description": "description"}),
    TableSpec("Employees", "employees", ("employee_id",), {
        "EmployeeID": "employee_id", "Name": "name", "CurrentTitle": "current_title",
        "Department": "department"}),
    TableSpec("SalaryBands", "salary_bands", ("function", "level"), {
        "Function": "function", "Level": "level", "Grade": "grade", "Min": "min",
        "P25": "p25", "P50": "p50", "P75": "p75", "Max": "max", "Currency": "currency"}),
    TableSpec("CompetencyLevels", "competency_levels", ("level",), {
        "Level": "level", "Name": "name", "Description": "description"}),
    TableSpec("JobGrades", "job_grades", ("grade",), {
        "Grade": "grade", "GradeLabel": "grade_label", "CareerBand": "career_band",
        "LevelBand": "level_band", "HayMin": "hay_min", "HayMax": "hay_max",
        "PayMin": "pay_min", "PayP25": "pay_p25", "PayP50": "pay_p50",
        "PayP75": "pay_p75", "PayMax": "pay_max", "Scope": "scope",
        "Complexity": "complexity", "Autonomy": "autonomy", "Impact": "impact",
        "Leadership": "leadership", "SpanOfControl": "span_of_control",
        "DecisionRights": "decision_rights", "Responsibilities": "responsibilities",
        "Authority": "authority"}),
    TableSpec("SeniorityLevels", "seniority_levels", ("l_code",), {
        "LCode": "l_code", "LName": "l_name", "MapsToLevel": "maps_to_level",
        "GradeRange": "grade_range", "Definition": "definition", "Grades": "grades"}),
    TableSpec("SkillProficiency", "skill_proficiency", ("category", "level"), {
        "Category": "category", "Level": "level", "LevelName": "level_name",
        "Anchor": "anchor"}),
    TableSpec("BenefitsCatalog", "benefits_catalog", ("benefit_id",), {
        "BenefitID": "benefit_id", "Category": "category", "Basis": "basis", "Unit": "unit",
        "TypicalValueDescription": "typical_value_description", "StatutoryNL": "statutory_nl",
        "Taxable": "taxable", "Description": "description"}),
    TableSpec("LevelBenefitsFactors", "level_benefits_factors", ("level", "category"), {
        "Level": "level", "Category": "category", "Factor": "factor"}),

    # Reference jobs / skills.
    TableSpec("JobProfiles", "job_profiles", ("job_id",), {
        "JobID": "job_id", "Description": "description",
        "KeyResponsibilities": "key_responsibilities", "RequiredSkills": "required_skills",
        "Specialisms": "specialisms", "ManagementLevel": "management_level",
        "TypicalTools": "typical_tools"}),
    TableSpec("TitleMapping", "title_mapping", ("existing_title",), {
        "ExistingTitle": "existing_title", "JobID": "job_id"}),
    TableSpec("CareerPaths", "career_paths", ("job_id",), {
        "JobID": "job_id", "NextJobID": "next_job_id", "NextRole": "next_role"},
        status_column="path_status"),
    TableSpec("RoleSkillMap", "role_skill_map", ("job_id", "skill_id"), {
        "JobID": "job_id", "SkillID": "skill_id", "RequiredLevel": "required_level",
        "SkillType": "skill_type"}),

    # Reference industries.
    TableSpec("IndustrySalaryFactors", "industry_salary_factors", ("industry_id", "function"), {
        "IndustryID": "industry_id", "Function": "function", "Factor": "factor"}),
    TableSpec("IndustrySkills", "industry_skills", ("industry_id", "skill_id"), {
        "IndustryID": "industry_id", "SkillID": "skill_id", "SkillName": "skill_name",
        "Category": "category", "Definition": "definition", "DefaultLevel": "default_level"}),
    TableSpec("BenefitsObservations", "benefits_observations", ("obs_id",), {
        "ObsID": "obs_id", "IndustryID": "industry_id", "Category": "category",
        "Value": "value", "Unit": "unit", "Currency": "currency"}),
]


@dataclass
class ImportReport:
    source: str
    rows: dict[str, int] = field(default_factory=dict)
    skipped_sheets: list[str] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    written: bool = False

    @property
    def total(self) -> int:
        return sum(self.rows.values())

    def __str__(self) -> str:
        head = f"{'WROTE' if self.written else 'DRY RUN'} — {self.source}"
        lines = [head, "-" * len(head)]
        for spec in SPECS:
            n = self.rows.get(spec.table)
            if n is None:
                continue
            drop = self.dropped.get(spec.table, 0)
            lines.append(f"  {spec.table:26s} {n:5d}" + (f"   ({drop} dropped)" if drop else ""))
        lines.append(f"  {'TOTAL':26s} {self.total:5d}")
        if self.skipped_sheets:
            lines.append("  sheets not imported: " + ", ".join(self.skipped_sheets))
        for note in self.notes:
            lines.append(f"  ! {note}")
        return "\n".join(lines)


def _clean(value):
    """One workbook cell -> something JSON/Postgres will take, or None."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.isna(value) if not isinstance(value, (list, tuple, dict)) else False:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, str):
        s = value.strip()
        return s or None
    return value


def _normalise_status(value):
    """'Active' -> 'active'. Anything unrecognised passes through untouched so
    the check constraint rejects it, rather than being quietly made legal."""
    s = _clean(value)
    if isinstance(s, str) and s.lower() in VALID_STATUS:
        return s.lower()
    return s


def build_rows(book: dict[str, pd.DataFrame], *, org_id: str,
               revision_id: str | None, source: str) -> tuple[dict[str, list[dict]], ImportReport]:
    """Workbook sheets -> row dicts per table. Pure: no network, no clock."""
    report = ImportReport(source=source)
    out: dict[str, list[dict]] = {}

    known = {s.sheet for s in SPECS}
    report.skipped_sheets = sorted(set(book) - known)

    for spec in SPECS:
        df = book.get(spec.sheet)
        if df is None:
            report.notes.append(f"sheet '{spec.sheet}' missing — {spec.table} not imported")
            continue

        rows, dropped = [], 0
        for _, src in df.iterrows():
            row: dict = {"org_id": org_id}
            if revision_id:
                row["revision_id"] = revision_id
            for wb_col, db_col in spec.columns.items():
                if wb_col in df.columns:
                    row[db_col] = _clean(src[wb_col])
            for wb_col, db_col in GOVERNANCE.items():
                if wb_col not in df.columns:
                    continue
                if db_col == "status" and spec.status_column:
                    # This sheet's Status is domain data, not governance.
                    row[spec.status_column] = _clean(src[wb_col])
                elif db_col == "status":
                    row[db_col] = _normalise_status(src[wb_col])
                else:
                    row[db_col] = _clean(src[wb_col])
            # Provenance of THIS import wins over whatever the sheet recorded:
            # the sheet's Source says where the content came from originally,
            # which matters, but the row in the database was put there by this
            # run and needs to say so.
            row["source"] = source
            row["updated_by"] = "importer"
            row.setdefault("status", "active")

            # A row with a hole in its natural key cannot be upserted and would
            # violate NOT NULL anyway. Count it, name nothing, move on.
            if any(row.get(k) in (None, "") for k in spec.key):
                dropped += 1
                continue
            rows.append(row)

        # The workbook can repeat a natural key — TitleMapping lists three
        # titles twice. Where the repeats are identical the duplicate carries no
        # information and is collapsed. Where they DISAGREE, one of them is
        # wrong and picking either would bury the question, so it is raised.
        seen: dict[tuple, dict] = {}
        deduped, conflicts = [], []
        for row in rows:
            k = tuple(row[c] for c in spec.key)
            prior = seen.get(k)
            if prior is None:
                seen[k] = row
                deduped.append(row)
                continue
            comparable = set(spec.columns.values()) | {"status", "owner", "effective_from"}
            if spec.status_column:
                comparable.add(spec.status_column)
            if all(prior.get(c) == row.get(c) for c in comparable):
                dropped += 1
            else:
                differing = sorted(c for c in comparable if prior.get(c) != row.get(c))
                conflicts.append((k, differing))
        if conflicts:
            detail = "; ".join(f"{'/'.join(map(str, k))} differs on {', '.join(cols)}"
                               for k, cols in conflicts[:4])
            raise ValueError(
                f"{spec.table}: {len(conflicts)} repeated natural key(s) hold DIFFERENT values "
                f"({detail}). The workbook has to say which is right — importing either would "
                "make the choice silently.")

        out[spec.table] = deduped
        report.rows[spec.table] = len(deduped)
        if dropped:
            report.dropped[spec.table] = dropped
            report.notes.append(
                f"{spec.table}: {dropped} row(s) dropped — blank {'/'.join(spec.key)}, "
                "or an exact duplicate of a row already read")

    return out, report


def _resolve_credentials() -> tuple[str | None, str | None]:
    """Environment first, Streamlit secrets second.

    A CLI run has no Streamlit context, and the key this needs is the SERVICE
    key: every reference table has RLS on with no anon policy, so an anon key
    reads and writes nothing at all rather than failing loudly.
    """
    url = os.environ.get("SUPABASE_URL")
    key = (os.environ.get("SUPABASE_SERVICE_KEY")
           or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("SUPABASE_KEY"))
    if url and key:
        return url, key
    try:
        from services.persistence_service import _read_secrets
    except ImportError:  # pragma: no cover
        from jobsy.services.persistence_service import _read_secrets
    s_url, s_key = _read_secrets()
    return url or s_url, key or s_key


def import_library(path: str = DEFAULT_WORKBOOK, *, write: bool = False,
                   org_slug: str = "default", note: str = "") -> ImportReport:
    """Read the workbook, validate it, and (optionally) upsert it."""
    book = pd.read_excel(path, sheet_name=None)

    # Validate on the SHEET_MAP-keyed dict the Validator expects, before a
    # single row is written.
    frames = {repo_key: book.get(sheet) for sheet, repo_key in SHEET_MAP.items()}
    Validator().validate(frames, strict=True)

    source = f"import:{os.path.basename(path)}"

    if not write:
        _, report = build_rows(book, org_id="00000000-0000-0000-0000-000000000000",
                               revision_id=None, source=source)
        report.notes.append("dry run — nothing was written; pass --write to load")
        return report

    url, key = _resolve_credentials()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and a SERVICE key are required to write. Set SUPABASE_URL and "
            "SUPABASE_SERVICE_KEY in the environment. The anon key will not work: RLS is on "
            "with no anon policy, so it would silently read and write nothing.")

    from supabase import create_client
    client = create_client(url, key)

    org = client.table("orgs").select("id").eq("slug", org_slug).single().execute()
    org_id = org.data["id"]

    rev = client.table("library_revisions").insert({
        "org_id": org_id, "label": source, "note": note or None,
        "created_by": "importer"}).execute()
    revision_id = rev.data[0]["id"]

    payload, report = build_rows(book, org_id=org_id, revision_id=revision_id, source=source)

    for spec in SPECS:                      # dependency order — see SPECS
        rows = payload.get(spec.table) or []
        if not rows:
            continue
        conflict = ",".join(("org_id",) + spec.key)
        for i in range(0, len(rows), 500):
            client.table(spec.table).upsert(rows[i:i + 500], on_conflict=conflict).execute()

    report.written = True
    report.notes.append(f"revision {revision_id}")
    return report


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    write = "--write" in argv
    argv = [a for a in argv if a != "--write"]
    path = argv[0] if argv else DEFAULT_WORKBOOK
    try:
        print(import_library(path, write=write))
    except Exception as exc:
        print(f"import failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

THE WORKBOOK'S SOURCE IS NOT OVERWRITTEN
----------------------------------------
Source records where a row's CONTENT came from. Which import run put the row in
the database is a different fact, and it already lives in library_revisions and
library_audit. An earlier version of this file wrote the import label over both,
erasing citations like "Calibrated to CBS bedrijfstak wages 2024 +
RobertHalf/RobertWalters NL 2026" — the same two-facts-one-column mistake
migration 0006 fixed for updated_at.

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
    # Where core/db_loader files this table's frame. Normally SHEET_MAP answers
    # that from the sheet name, and normally one sheet is one table — but 0016
    # split job_profiles and seniority_levels in the database while the WORKBOOK
    # IN A CLIENT'S HANDS still holds both halves on one sheet. Two specs then
    # read the same sheet, SHEET_MAP has one answer for it, and without this the
    # second frame would quietly overwrite the first under the same key.
    repo_key: str | None = None
    # The sheet this spec would RATHER read, when the workbook has it.
    #
    # 0016 split two tables in the database while the workbook in a client's
    # hands still carries both halves on one sheet. That left a choice that
    # looked like it had to be made: either the export writes a sheet the
    # import ignores — breaking the round-trip this file's docstring promises —
    # or the dedicated sheet becomes mandatory and every workbook already issued
    # stops importing its positioning.
    #
    # It does not have to be made. A spec names both: the dedicated sheet is
    # preferred where it exists, the shared one is accepted where it does not.
    # An old workbook keeps working and imports one market, which is what it can
    # honestly say; a reissued one carries Country per row and imports several.
    # Nobody has to be told to migrate on a particular day.
    prefers_sheet: str | None = None
    # Values for database columns the workbook has no heading for. Only
    # `country` needs one today: job_profile_positioning and
    # seniority_grade_binding are NOT NULL on it and the workbook predates the
    # dimension, so the import would fail at the constraint. 'NL' is a
    # statement of fact — 0016 measured every existing row as Dutch before
    # copying it — not a guess, and it applies only where the sheet says
    # nothing. A reissued workbook with a Country column overrides it per row.
    defaults: dict[str, str] = field(default_factory=dict)


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
    # sort_order, not "order": see 0004 — the reserved word collided with
    # PostgREST's own ordering parameter.
    TableSpec("Levels", "levels", ("level",), {"Level": "level", "Order": "sort_order"}),
    TableSpec("PayElements", "pay_elements", ("country", "element_id"), {
        "Country": "country", "ElementID": "element_id", "Name": "name", "Category": "category", "Basis": "basis",
        "TypicalValue": "typical_value", "StatutoryNL": "statutory_nl", "Taxable": "taxable",
        "Description": "description"},
        defaults={"country": "NL"}),
    TableSpec("Categories", "categories", ("category",), {
        "Category": "category", "Function": "function", "Description": "description"}),
    TableSpec("Employees", "employees", ("employee_id",), {
        "EmployeeID": "employee_id", "Name": "name", "CurrentTitle": "current_title",
        "Department": "department"}),
    TableSpec("SalaryBands", "salary_bands", ("country", "function", "level"), {
        "Country": "country", "Function": "function", "Level": "level", "Grade": "grade", "Min": "min",
        "P25": "p25", "P50": "p50", "P75": "p75", "Max": "max", "Currency": "currency"},
        defaults={"country": "NL"}),
    TableSpec("CompetencyLevels", "competency_levels", ("level",), {
        "Level": "level", "Name": "name", "Description": "description"}),
    TableSpec("JobGrades", "job_grades", ("country", "grade"), {
        "Country": "country", "Grade": "grade", "GradeLabel": "grade_label", "CareerBand": "career_band",
        "LevelBand": "level_band", "HayMin": "hay_min", "HayMax": "hay_max",
        "PayMin": "pay_min", "PayP25": "pay_p25", "PayP50": "pay_p50",
        "PayP75": "pay_p75", "PayMax": "pay_max", "Scope": "scope",
        "Complexity": "complexity", "Autonomy": "autonomy", "Impact": "impact",
        "Leadership": "leadership", "SpanOfControl": "span_of_control",
        "DecisionRights": "decision_rights", "Responsibilities": "responsibilities",
        "Authority": "authority"},
        defaults={"country": "NL"}),
    TableSpec("SeniorityLevels", "seniority_levels", ("l_code",), {
        "LCode": "l_code", "LName": "l_name", "MapsToLevel": "maps_to_level",
        "GradeRange": "grade_range", "Definition": "definition", "Grades": "grades"}),
    # The binding half of the sheet above — 0016 §2. It reads the SAME three
    # headings, and the spec above still writes them to seniority_levels: while
    # both columns are live, an import that fed only one of them would leave the
    # other stale and 0016 §3(e) would then report a divergence that nobody
    # caused. Both are written until the old columns are dropped.
    TableSpec("SeniorityLevels", "seniority_grade_binding", ("country", "l_code"), {
        "LCode": "l_code", "MapsToLevel": "maps_to_level", "GradeRange": "grade_range",
        "Grades": "grades", "Country": "country"},
        repo_key="senioritybinding", prefers_sheet="SeniorityGradeBinding",
        defaults={"country": "NL"}),
    TableSpec("SkillProficiency", "skill_proficiency", ("category", "level"), {
        "Category": "category", "Level": "level", "LevelName": "level_name",
        "Anchor": "anchor"}),
    TableSpec("BenefitsCatalog", "benefits_catalog", ("country", "benefit_id"), {
        "Country": "country", "BenefitID": "benefit_id", "Category": "category", "Basis": "basis", "Unit": "unit",
        "TypicalValueDescription": "typical_value_description", "StatutoryNL": "statutory_nl",
        "Taxable": "taxable", "Description": "description"},
        defaults={"country": "NL"}),
    TableSpec("LevelBenefitsFactors", "level_benefits_factors", ("country", "level", "category"), {
        "Country": "country", "Level": "level", "Category": "category", "Factor": "factor"},
        defaults={"country": "NL"}),

    # Reference jobs / skills.
    TableSpec("JobProfiles", "job_profiles", ("job_id",), {
        "JobID": "job_id", "Description": "description",
        "KeyResponsibilities": "key_responsibilities", "RequiredSkills": "required_skills",
        "Specialisms": "specialisms", "ManagementLevel": "management_level",
        "TypicalTools": "typical_tools"}),
    # The positioning half of the sheet above — 0016 §1. ManagementLevel is
    # routed to both tables on purpose, for the reason given at
    # seniority_grade_binding: the old column is still live and still read, and
    # an import that updated one side only is precisely what 0016 §3(e) is
    # looking for. When that column is dropped, drop it from the spec above.
    #
    # WHAT THIS DOES NOT DO WHEN IT FALLS BACK: a workbook that carries only
    # the shared JobProfiles sheet still imports ONE market, because that sheet's
    # universal spec is keyed on job_id alone and two rows for the same job in
    # two markets are a repeated
    # natural key there and build_rows refuses to choose between them. A
    # Belgian client's own workbook (every row Belgian, Country column or the
    # 'NL' default corrected once) imports correctly; a single workbook holding
    # several markets' positioning needs a sheet of its own, which is a
    # workbook change, not a code change.
    #
    # AND ONE THING THAT MUST HAPPEN BEFORE THE OLD COLUMN GOES. Neither new
    # table is in core.catalog.SHEET_MAP, so the library EXPORT
    # (services/library_export_service.sheets()) and the Data Quality scorecard,
    # which both walk SHEET_MAP, cannot see them. That costs nothing today —
    # ManagementLevel still rides on the JobProfiles sheet and this spec writes
    # both halves — but on the day 0016 §3 drops the old columns, an export
    # would silently lose the positioning claim altogether. Give both tables a
    # sheet of their own in SHEET_MAP first.
    TableSpec("JobProfiles", "job_profile_positioning", ("country", "job_id"), {
        "JobID": "job_id", "ManagementLevel": "management_level", "Country": "country"},
        repo_key="jobpositioning", prefers_sheet="JobProfilePositioning",
        defaults={"country": "NL"}),
    TableSpec("TitleMapping", "title_mapping", ("country", "existing_title"), {
        "Country": "country", "ExistingTitle": "existing_title", "JobID": "job_id"},
        defaults={"country": "NL"}),
    TableSpec("CareerPaths", "career_paths", ("job_id",), {
        "JobID": "job_id", "NextJobID": "next_job_id", "NextRole": "next_role"},
        status_column="path_status"),
    TableSpec("RoleSkillMap", "role_skill_map", ("job_id", "skill_id"), {
        "JobID": "job_id", "SkillID": "skill_id", "RequiredLevel": "required_level",
        "SkillType": "skill_type"}),

    # References salary_bands on (function, level) — must follow it.
    TableSpec("PayMix", "pay_mix", ("country", "function", "level"), {
        "Country": "country", "Function": "function", "Level": "level",
        "TargetVariablePct": "target_variable_pct",
        "ThirteenthMonthPct": "thirteenth_month_pct",
        "LTIEligible": "lti_eligible", "Notes": "notes"},
        defaults={"country": "NL"}),

    # Reference industries.
    TableSpec("IndustrySalaryFactors", "industry_salary_factors", ("country", "industry_id", "function"), {
        "Country": "country", "IndustryID": "industry_id", "Function": "function", "Factor": "factor"},
        defaults={"country": "NL"}),
    # Universal: sector-typical practice, no country. Deliberately still keyed
    # without one -- adding it here would recreate the column the 2026-09-06
    # split removed.
    TableSpec("IndustrySkills", "industry_skills", ("industry_id", "skill_id"), {
        "IndustryID": "industry_id", "SkillID": "skill_id", "SkillName": "skill_name",
        "Category": "category", "Definition": "definition", "DefaultLevel": "default_level"}),
    # National: what the sector is legally required to know. Keyed ON country,
    # because the same industry carries a different obligation per market and
    # without it an import would collapse five regimes onto one row.
    TableSpec("IndustryRegulatorySkills", "industry_regulatory_skills",
        ("country", "industry_id", "skill_id"), {
        "Country": "country", "IndustryID": "industry_id", "SkillID": "skill_id",
        "SkillName": "skill_name", "Category": "category",
        "Definition": "definition", "DefaultLevel": "default_level"},
        defaults={"country": "NL"}),
    # NOT keyed on country, unlike its neighbours. The unique here is
    # (org_id, obs_id) — a SURROGATE — so country varies freely underneath it
    # and adding it to the conflict target makes PostgREST refuse with 42P10.
    # Migration 0015 says so in as many words and I widened it anyway.
    TableSpec("BenefitsObservations", "benefits_observations", ("obs_id",), {
        "Country": "country", "ObsID": "obs_id", "IndustryID": "industry_id", "Category": "category",
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

    # Both names count as known, or a workbook carrying the dedicated sheet
    # would have it reported as skipped while it was in fact being read.
    known = {s.sheet for s in SPECS} | {s.prefers_sheet for s in SPECS if s.prefers_sheet}
    report.skipped_sheets = sorted(set(book) - known)

    for spec in SPECS:
        # Preferred sheet if the workbook has it, else the shared one it splits
        # from. Which one was used is recorded: a reader looking at a positioning
        # figure should be able to find out whether it came from a sheet that can
        # express a market or from one that cannot.
        sheet = spec.sheet
        if spec.prefers_sheet and spec.prefers_sheet in book:
            sheet = spec.prefers_sheet
            report.notes.append(
                f"{spec.table} read from its own sheet '{sheet}' rather than "
                f"'{spec.sheet}' — this workbook can carry more than one market")
        df = book.get(sheet)
        if df is None:
            report.notes.append(f"sheet '{sheet}' missing — {spec.table} not imported")
            continue

        rows, dropped = [], 0
        for _, src in df.iterrows():
            row: dict = {"org_id": org_id}
            if revision_id:
                row["revision_id"] = revision_id
            for wb_col, db_col in spec.columns.items():
                if wb_col in df.columns:
                    row[db_col] = _clean(src[wb_col])
            # After the sheet, never over it: a heading the workbook does have
            # wins even when the cell is blank-and-therefore-None only if the
            # column is nullable — and the two that use defaults are NOT NULL,
            # so a blank Country in a reissued workbook falls back here rather
            # than failing the insert.
            for db_col, value in spec.defaults.items():
                if row.get(db_col) in (None, ""):
                    row[db_col] = value
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
            # The sheet's Source is KEPT. It says where the content came from —
            # "Calibrated to CBS bedrijfstak wages 2024 + RobertHalf/RobertWalters
            # NL 2026" is the citation for the pay factors, and overwriting it
            # with the name of the file it arrived in destroys the only record of
            # that. Which run wrote the row is a different fact and already has a
            # home: library_revisions.label and library_audit. Two facts, one
            # column — the same mistake migration 0006 fixed for updated_at.
            #
            # Only a missing or blank Source falls back to the import label, so
            # the column is never left empty.
            if row.get("source") in (None, ""):
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


def key_kind(key: str | None) -> str:
    """Which of Supabase's API keys is this?

    The platform is retiring the legacy JWT keys (anon / service_role, the long
    'eyJ...' tokens) in favour of sb_publishable_... and sb_secret_.... They are
    not interchangeable here, and the failure mode of getting it wrong is the
    quiet one — see _require_writable_key().
    """
    if not key:
        return "missing"
    if key.startswith("sb_secret_"):
        return "secret"
    if key.startswith("sb_publishable_"):
        return "publishable"
    if key.startswith("eyJ"):
        return "legacy-jwt"
    return "unknown"


def _require_writable_key(key: str | None) -> list[str]:
    """Refuse a key that cannot write, and say why. Returns advisory notes.

    A publishable key is the dangerous one: every reference table has RLS on
    with no policy for anon, so the client would connect, accept every upsert
    and persist NOTHING — an import that reports success over an empty
    database. Better to stop at the door.
    """
    kind = key_kind(key)
    if kind == "publishable":
        raise RuntimeError(
            "That is a publishable key (sb_publishable_...). Every table has RLS on with no "
            "anon policy, so it would connect, accept every write and store nothing — an "
            "import that looks like it worked. Use the secret key (sb_secret_...).")
    if kind == "legacy-jwt":
        return ["Using a LEGACY JWT key. Supabase is retiring these in favour of "
                "sb_secret_... — switch before they are removed, and disable the legacy "
                "keys on the project once nothing depends on them."]
    if kind == "unknown":
        return ["Key format not recognised — expected sb_secret_.... Continuing, but if the "
                "import writes nothing this is the first thing to check."]
    return []


def _resolve_credentials() -> tuple[str | None, str | None]:
    """Environment first, Streamlit secrets second.

    A CLI run has no Streamlit context, and the key this needs is the SECRET
    key (sb_secret_...): every reference table has RLS on with no anon policy,
    so a publishable key reads and writes nothing rather than failing loudly.
    """
    url = os.environ.get("SUPABASE_URL")
    key = (os.environ.get("SUPABASE_SECRET_KEY")            # current naming
           or os.environ.get("SUPABASE_SERVICE_KEY")        # legacy naming, same role
           or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("SUPABASE_KEY"))
    if url and key:
        return url, key
    # auth_service, not persistence_service. `_read_secrets` moved and this
    # import was not moved with it, so BOTH branches failed — the first on the
    # missing name, the second on a `jobsy` package that does not exist — and
    # every service-key read of the library raised ModuleNotFoundError. Nothing
    # noticed, because the app itself reads as the signed-in user under RLS
    # (LIBRARY_CLIENT="user") and never comes through here. Only a script does,
    # and a script's failure was absorbed one layer up by Catalog.load(), which
    # falls back to the workbook on disk.
    #
    # WHAT COMES BACK FROM THE SECRETS FILE IS THE PUBLISHABLE KEY. That is the
    # right source for the URL and the wrong kind of key for writing, which is
    # exactly why `_require_writable_key` sits at the call site and warns. Env
    # vars are checked first above for that reason; this is the last resort.
    # THE SECRETS FILE HOLDS A WRITABLE KEY TOO, and until 6 September 2026
    # nothing looked for it. `st.secrets["SUPABASE_KEY"]` is `sb_secret_...` —
    # it was sitting there the whole time while this function returned the
    # publishable one and every script import died at `_require_writable_key`
    # with "use the secret key", which the machine already had.
    #
    # Same shape as the persistence_service import above and worth naming as a
    # pattern rather than a second accident: BOTH were credential paths that
    # could not reach a credential that existed. Neither showed up in the app,
    # because the app reads as the signed-in user and never comes here.
    #
    # Read explicitly by name rather than through `_read_secrets`, which is
    # auth's helper and deliberately returns the PUBLISHABLE key — right for
    # signing somebody in, wrong for writing the library. `_require_writable_key`
    # at the call site still decides whether what comes back can write.
    secret = None
    try:
        import streamlit as st
        for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY"):
            candidate = st.secrets.get(name)
            if candidate and str(candidate).startswith(("sb_secret_", "service_role", "eyJ")):
                secret = str(candidate)
                break
    except Exception:
        pass

    try:
        from services.auth_service import _read_secrets
    except ImportError:  # pragma: no cover
        from jobsy.services.auth_service import _read_secrets
    s_url, s_key = _read_secrets()
    if secret:
        return url or s_url, key or secret
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
            "SUPABASE_URL and a SECRET key are required to write. Set SUPABASE_URL and "
            "SUPABASE_SECRET_KEY (the sb_secret_... key) in the environment. A publishable "
            "key will not work: RLS is on with no anon policy, so it would silently write "
            "nothing.")
    key_notes = _require_writable_key(key)

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
    report.notes.extend(key_notes)

    # An import that reports 2,578 rows over an empty table is the failure this
    # guards against. Count what is actually there, from the database's answer
    # rather than from what we believed we sent.
    # `.data`, not `.count`. A count is derived from PostgREST's Content-Range
    # header, so it is None whenever anything in the path drops that header --
    # and `(None or 0) == 0` reads as "this table is empty", condemning an
    # import that had in fact just written every row. That turns the one guard
    # meant to catch a real silent-write failure into a guard that cries wolf,
    # and a guard operators learn to ignore is worse than no guard. Asking for
    # one row answers the same question and cannot be lost in transit.
    empty = [spec.table for spec in SPECS
             if (payload.get(spec.table) or [])
             and not (client.table(spec.table).select("id")
                      .limit(1).execute().data)]
    if empty:
        raise RuntimeError(
            f"The import reported rows but these tables are still empty: {', '.join(empty)}. "
            "That is the signature of a key without write access — check it is the "
            "sb_secret_... key, not the publishable one.")
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

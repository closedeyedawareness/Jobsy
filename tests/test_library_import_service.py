"""
Workbook -> database row mapping.

build_rows() is pure, so everything that could mis-map a column, lose a
governance field or invent a value is testable without a database. Two of these
cases come from importing the real library and watching the schema refuse it.
"""

import pandas as pd
import pytest

from services.library_import_service import build_rows, import_library, SPECS

ORG = "00000000-0000-0000-0000-000000000001"


def _book(**sheets):
    return {name: pd.DataFrame(rows) for name, rows in sheets.items()}


def _rows(book):
    payload, report = build_rows(book, org_id=ORG, revision_id=None, source="import:test.xlsx")
    return payload, report


def test_governance_columns_are_carried_across_not_dropped():
    payload, _ = _rows(_book(Jobs=[{
        "JobID": "J-1", "StandardTitle": "Dev", "Function": "Eng", "Level": "Medior",
        "Owner": "Job Architecture", "Status": "Active",
        "EffectiveFrom": "2026-07-02", "Source": "Seed v1", "UpdatedAt": "2026-07-02"}]))
    row = payload["jobs"][0]
    assert row["owner"] == "Job Architecture"
    assert row["effective_from"] == "2026-07-02"
    assert row["updated_at"] == "2026-07-02"
    assert row["org_id"] == ORG


def test_status_is_lowercased_to_the_one_database_vocabulary():
    payload, _ = _rows(_book(Jobs=[{
        "JobID": "J-1", "StandardTitle": "Dev", "Function": "Eng", "Level": "Medior",
        "Status": "Active"}]))
    assert payload["jobs"][0]["status"] == "active"


def test_an_unknown_status_is_left_alone_for_the_constraint_to_reject():
    # Quietly rewriting it to something legal would hide a real data problem.
    payload, _ = _rows(_book(Jobs=[{
        "JobID": "J-1", "StandardTitle": "Dev", "Function": "Eng", "Level": "Medior",
        "Status": "Wobbly"}]))
    assert payload["jobs"][0]["status"] == "Wobbly"


def test_career_path_status_is_not_the_governance_status():
    """CareerPaths says 'Terminal' to mean top-of-ladder. Folding that into the
    governance column would either lose the fact or loosen the vocabulary for
    every other table — the reason migration 0002 exists."""
    payload, _ = _rows(_book(CareerPaths=[
        {"JobID": "J-1", "NextJobID": "J-2", "NextRole": "Lead", "Status": "Active"},
        {"JobID": "J-9", "NextJobID": None, "NextRole": None, "Status": "Terminal"}]))
    rows = {r["job_id"]: r for r in payload["career_paths"]}
    assert rows["J-9"]["path_status"] == "Terminal"
    assert rows["J-9"]["status"] == "active"        # governance stays valid
    assert rows["J-1"]["path_status"] == "Active"


def test_identical_repeated_rows_collapse():
    dup = {"ExistingTitle": "VP Engineering", "JobID": "J-ENG-04", "Status": "Active"}
    payload, report = _rows(_book(TitleMapping=[dup, dict(dup)]))
    assert len(payload["title_mapping"]) == 1
    assert report.dropped["title_mapping"] == 1


def test_repeated_rows_that_disagree_are_refused_not_silently_picked():
    payload = _book(TitleMapping=[
        {"ExistingTitle": "VP Engineering", "JobID": "J-ENG-04", "Status": "Active"},
        {"ExistingTitle": "VP Engineering", "JobID": "J-ENG-99", "Status": "Active"}])
    with pytest.raises(ValueError, match="DIFFERENT values"):
        _rows(payload)


def test_a_row_with_no_natural_key_is_dropped_and_counted():
    payload, report = _rows(_book(Jobs=[
        {"JobID": "J-1", "StandardTitle": "Dev", "Function": "Eng", "Level": "Medior"},
        {"JobID": None, "StandardTitle": "Ghost", "Function": "Eng", "Level": "Medior"}]))
    assert len(payload["jobs"]) == 1
    assert report.dropped["jobs"] == 1


def test_blank_and_nan_cells_become_null_not_the_string_nan():
    payload, _ = _rows(_book(Jobs=[{
        "JobID": "J-1", "StandardTitle": "Dev", "Function": "Eng", "Level": "Medior",
        "Category": "   ", "IscoTitle": float("nan")}]))
    row = payload["jobs"][0]
    assert row["category"] is None
    assert row["isco_title"] is None


def test_this_import_stamps_its_own_provenance():
    payload, _ = _rows(_book(Jobs=[{
        "JobID": "J-1", "StandardTitle": "Dev", "Function": "Eng", "Level": "Medior",
        "Source": "Seed v1 (pay)"}]))
    row = payload["jobs"][0]
    # The sheet's Source says where the CONTENT came from; the row in the
    # database was put there by this run and has to say so.
    assert row["source"] == "import:test.xlsx"
    assert row["updated_by"] == "importer"


def test_specs_are_in_dependency_order():
    """A table may only be written after every table it references."""
    parents = {"job_profiles": ["jobs"], "title_mapping": ["jobs"], "career_paths": ["jobs"],
               "role_skill_map": ["jobs", "skills"], "industry_salary_factors": ["industries"],
               "industry_skills": ["industries"], "benefits_observations": ["industries"],
               "pay_mix": ["salary_bands"]}
    order = [s.table for s in SPECS]
    for child, needed in parents.items():
        for parent in needed:
            assert order.index(parent) < order.index(child), f"{parent} must precede {child}"


def test_dry_run_over_the_real_workbook_maps_every_sheet_and_drops_nothing_unexpected():
    report = import_library("jobsy_reference_library.xlsx", write=False)
    assert not report.written
    assert report.total > 2000
    # Only TitleMapping's three known duplicate rows should be dropped.
    assert report.dropped == {"title_mapping": 3}, report.dropped
    # PayElements and PayMix ARE imported as of 0004 — the variable-pay exposure
    # analysis reads PayMix, so leaving it in the workbook would leave that
    # feature depending on a file that is no longer the master.
    assert report.rows["pay_mix"] == 45
    assert report.rows["pay_elements"] == 7
    # What remains unimported is what the app genuinely never reads.
    assert set(report.skipped_sheets) == {
        "BenefitsSources", "CareerBands", "DataDictionary",
        "LevelCriteria", "SalarySources"}


def test_pay_mix_covers_exactly_the_salary_band_cohorts():
    """0004 makes this a foreign key. If the two sheets ever diverge the import
    fails at the database, so the mismatch should surface here first."""
    import pandas as _pd
    xl = _pd.ExcelFile("jobsy_reference_library.xlsx")
    payload, _ = build_rows({"PayMix": xl.parse("PayMix"), "SalaryBands": xl.parse("SalaryBands")},
                            org_id=ORG, revision_id=None, source="import:test.xlsx")
    mix = {(r["function"], r["level"]) for r in payload["pay_mix"]}
    bands = {(r["function"], r["level"]) for r in payload["salary_bands"]}
    assert mix <= bands, f"PayMix cohorts with no salary band: {sorted(mix - bands)}"


def test_levels_maps_to_sort_order_not_the_reserved_word():
    payload, _ = _rows(_book(Levels=[{"Level": "Junior", "Order": 1}]))
    row = payload["levels"][0]
    assert row["sort_order"] == 1
    assert "order" not in row


# ── API key format ────────────────────────────────────────────────────────
# Supabase is retiring the legacy JWT keys. The publishable key is the one that
# fails silently, so it is the one worth a test.

def test_key_kind_recognises_each_format():
    from services.library_import_service import key_kind
    assert key_kind("sb_secret_abc123") == "secret"
    assert key_kind("sb_publishable_abc123") == "publishable"
    assert key_kind("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.x.y") == "legacy-jwt"
    assert key_kind(None) == "missing"
    assert key_kind("hunter2") == "unknown"


def test_a_publishable_key_is_refused_before_it_can_write_nothing():
    from services.library_import_service import _require_writable_key
    with pytest.raises(RuntimeError, match="publishable key"):
        _require_writable_key("sb_publishable_abc123")


def test_a_legacy_jwt_key_works_but_is_called_out():
    from services.library_import_service import _require_writable_key
    notes = _require_writable_key("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.x.y")
    assert notes and "LEGACY" in notes[0]


def test_the_secret_key_passes_without_comment():
    from services.library_import_service import _require_writable_key
    assert _require_writable_key("sb_secret_abc123") == []

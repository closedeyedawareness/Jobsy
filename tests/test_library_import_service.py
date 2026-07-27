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
               "industry_skills": ["industries"], "benefits_observations": ["industries"]}
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
    # The seven sheets the app has never consumed stay unimported, deliberately.
    assert set(report.skipped_sheets) == {
        "BenefitsSources", "CareerBands", "DataDictionary", "LevelCriteria",
        "PayElements", "PayMix", "SalarySources"}

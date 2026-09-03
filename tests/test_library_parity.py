"""
W5's acceptance gate: the database-loaded catalog must equal the Excel-loaded one.

This is the test that decides whether config.LIBRARY_SOURCE can be flipped. It
needs a seeded database, so it SKIPS without credentials rather than failing —
but skipping is not passing, and the cutover is not justified by a skip.

    $env:SUPABASE_URL = "https://<ref>.supabase.co"
    $env:SUPABASE_SECRET_KEY = "sb_secret_..."
    python -m pytest tests/test_library_parity.py -v

It compares three layers, because each can be right while the next is wrong:
  1. the frames    — what the loader produces
  2. the statistics — what Repository builds from them
  3. whole records  — what the app actually asks for
"""

import os

import pandas as pd
import pytest

from core.catalog import Catalog, SHEET_MAP

pytestmark = pytest.mark.skipif(
    not (os.environ.get("SUPABASE_URL") and
         (os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_KEY"))),
    reason="needs SUPABASE_URL + SUPABASE_SECRET_KEY and a seeded database")

WORKBOOK = "jobsy_reference_library.xlsx"

# Repeated keys the loader cannot preserve, and should not: TitleMapping has
# three byte-identical duplicate rows that the import collapses on purpose.
KNOWN_ROW_DELTAS = {"titles": 3}

# The ONE value difference the cutover accepts, and it is deliberate: the
# workbook writes "Active", the check constraint takes 'active', and the
# importer lowercases at the boundary (library_import_service._normalise_status)
# so the database speaks one vocabulary. Compared case-insensitively rather than
# re-capitalised in db_loader — a loader that renders "Active" back would be
# being more helpful than the thing it replaces, which is the failure its own
# docstring warns against, and after cutover 'active' is simply the truth.
# Nothing in the app reads this column; the Status comparisons in ui/app.py are
# a computed pay-range status, unrelated.
CASE_INSENSITIVE_COLUMNS = {"Status"}

#: The sort key per sheet for the row-for-row comparison. Named up here so the
#: coverage test can see it without running the comparison.
_COMPARISON_KEYS = {
    "jobs": ["JobID"], "profiles": ["JobID"], "salary": ["Function", "Level"],
    "titles": ["ExistingTitle"], "career": ["JobID"], "levels": ["Level"],
    "categories": ["Category"], "skills": ["SkillID"],
    "competencylevels": ["Level"], "roleskillmap": ["JobID", "SkillID"],
    "jobgrades": ["Grade"], "industries": ["IndustryID"],
    "industrysalaryfactors": ["IndustryID", "Function"],
    "industryskills": ["IndustryID", "SkillID"], "senioritylevels": ["LCode"],
    "skillproficiency": ["Category", "Level"], "benefitscatalog": ["BenefitID"],
    "benefitsobservations": ["ObsID"], "levelbenefitsfactors": ["Level", "Category"],
    "paymix": ["Function", "Level"], "payelements": ["ElementID"],
}


@pytest.fixture(scope="module")
def excel_catalog():
    return Catalog(WORKBOOK, source="excel").load()


@pytest.fixture(scope="module")
def db_catalog():
    c = Catalog(WORKBOOK, source="db").load()
    if c.fell_back_to_excel:
        pytest.fail("Catalog(source='db') fell back to the workbook — the database was "
                    "unreachable or unseeded, so nothing below would actually be compared.")
    return c


@pytest.fixture(scope="module")
def frames():
    from core.db_loader import load_frames_from_config
    raw = pd.read_excel(WORKBOOK, sheet_name=None, dtype=str)
    xl = {}
    for sheet, key in SHEET_MAP.items():
        if sheet in raw:
            df = raw[sheet].apply(lambda c: c.str.strip() if c.dtype == object else c)
            for col in ("Min", "Max", "Order"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            xl[key] = df
    return xl, load_frames_from_config()


# ── 1. the frames ─────────────────────────────────────────────────────────

def test_every_sheet_the_app_reads_comes_back(frames):
    xl, db = frames
    assert set(xl) - set(db) == set(), f"missing from the database: {sorted(set(xl) - set(db))}"


def test_row_counts_match(frames):
    xl, db = frames
    for key in sorted(xl):
        expected = len(xl[key]) - KNOWN_ROW_DELTAS.get(key, 0)
        assert len(db[key]) == expected, (
            f"{key}: workbook {len(xl[key])} rows, database {len(db[key])}")


def test_the_columns_the_repository_reads_are_present(frames):
    xl, db = frames
    for key in sorted(xl):
        missing = set(xl[key].columns) - set(db[key].columns)
        assert not missing, f"{key} is missing {sorted(missing)}"


def _as_text(df, cols):
    """Stringify for comparison WITHOUT turning two spellings of "missing" into
    two different values.

    `.astype(str)` renders a workbook NaN as 'nan' and a database None as
    'None', and a later .fillna("") cannot reach either, because by then they
    are ordinary strings. That made four columns of empty cells read as a
    row-for-row mismatch — and a gate that is red for a reason nobody can act
    on is a gate that stops being read. Missing becomes "" on both sides; a
    value against an empty still fails, which is the difference that matters.
    """
    out = df[cols].copy()
    for col in cols:
        series = out[col]
        out[col] = series.astype(str).where(series.notna(), "")
    return out


#: Sheets deliberately outside the row-for-row comparison, with the reason.
NOT_COMPARED = {
    "employees": "customer data — the reference library ships it empty",
}


def test_every_loaded_sheet_is_either_compared_or_excluded_on_purpose():
    """A sheet added to SHEET_MAP and not to the comparison below would be
    loaded by the app and checked by nothing — the same silence that let PayMix
    and PayElements sit outside the library for two months."""
    uncovered = set(SHEET_MAP.values()) - set(_COMPARISON_KEYS) - set(NOT_COMPARED)
    assert not uncovered, f"not compared and not excluded on purpose: {sorted(uncovered)}"


def test_values_match_row_for_row(frames):
    """The real comparison. Sorted on a stable key, compared as text, so a
    column ordering difference or an int/str drift cannot mask a wrong value."""
    xl, db = frames
    keys = {"jobs": ["JobID"], "profiles": ["JobID"], "salary": ["Function", "Level"],
            "titles": ["ExistingTitle"], "career": ["JobID"], "levels": ["Level"],
            "categories": ["Category"], "skills": ["SkillID"],
            "competencylevels": ["Level"], "roleskillmap": ["JobID", "SkillID"],
            "jobgrades": ["Grade"], "industries": ["IndustryID"],
            "industrysalaryfactors": ["IndustryID", "Function"],
            "industryskills": ["IndustryID", "SkillID"], "senioritylevels": ["LCode"],
            "skillproficiency": ["Category", "Level"], "benefitscatalog": ["BenefitID"],
            "benefitsobservations": ["ObsID"], "levelbenefitsfactors": ["Level", "Category"],
            "paymix": ["Function", "Level"], "payelements": ["ElementID"]}
    assert keys == _COMPARISON_KEYS

    mismatches = []
    for key, sort_on in keys.items():
        if key not in xl or key not in db:
            continue
        cols = [c for c in xl[key].columns if c in db[key].columns]
        a = _as_text(xl[key].drop_duplicates(subset=sort_on)
                     .sort_values(sort_on).reset_index(drop=True), cols)
        b = _as_text(db[key].sort_values(sort_on).reset_index(drop=True), cols)
        if len(a) != len(b):
            mismatches.append(f"{key}: {len(a)} vs {len(b)} rows")
            continue
        for col in cols:
            left, right = a[col].fillna(""), b[col].fillna("")
            if col in CASE_INSENSITIVE_COLUMNS:
                left, right = left.str.lower(), right.str.lower()
            diff = left != right
            if diff.any():
                i = diff.idxmax()
                mismatches.append(
                    f"{key}.{col}: {int(diff.sum())} differ, first at "
                    f"{dict(zip(sort_on, a.loc[i, sort_on]))} — "
                    f"workbook {a.loc[i, col]!r} vs database {b.loc[i, col]!r}")
    assert not mismatches, "\n".join(mismatches)


def test_updated_at_survives_the_round_trip(frames):
    """Not covered by counts, and the reason migration 0006 exists: a trigger
    was replacing the workbook's UpdatedAt with the time of the last import,
    which would make the Data Quality freshness view read green forever."""
    xl, db = frames
    for key in ("jobs", "salary", "skills"):
        if "UpdatedAt" not in xl[key].columns:
            continue
        a = pd.to_datetime(xl[key]["UpdatedAt"], errors="coerce").max()
        b = pd.to_datetime(db[key]["UpdatedAt"], errors="coerce").max()
        assert a.date() == b.date(), f"{key}: workbook {a.date()} vs database {b.date()}"


# ── 2. what Repository builds ─────────────────────────────────────────────

def test_statistics_are_identical(excel_catalog, db_catalog):
    a = excel_catalog.repository.statistics()
    b = db_catalog.repository.statistics()
    differing = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
    # title_mappings differs by the three collapsed duplicates, and only that.
    differing.pop("title_mappings", None)
    assert not differing, differing


def test_the_collapsed_duplicates_are_the_only_mapping_difference(excel_catalog, db_catalog):
    a = excel_catalog.repository.statistics()["title_mappings"]
    b = db_catalog.repository.statistics()["title_mappings"]
    # Repository already stores title_mapping as a dict, so the workbook's
    # duplicates collapse there too — the counts should in fact agree.
    assert a == b, f"workbook {a} vs database {b}"


def test_the_validator_is_as_happy_with_the_database(db_catalog):
    report = db_catalog.repository.validation
    assert report is not None and report.ok, report.warnings if report else None


# ── 3. what the app asks for ──────────────────────────────────────────────

def test_whole_records_match(excel_catalog, db_catalog):
    for job_id in sorted(excel_catalog.repository.jobs)[:25]:
        a = excel_catalog.get_complete_job(job_id)
        b = db_catalog.get_complete_job(job_id)
        assert (a is None) == (b is None), job_id
        if a is None:
            continue
        assert a["job"] == b["job"], f"{job_id}: {a['job']} vs {b['job']}"
        assert a["salary"] == b["salary"], f"{job_id}: salary differs"
        assert a["next_role"] == b["next_role"], f"{job_id}: career step differs"


def test_title_resolution_agrees(excel_catalog, db_catalog):
    """The thing the product is actually for: a messy title in, the same
    standard job out, whichever source the library came from."""
    for title in ["HRBP", "VP Engineering", "People Partner", "Head of Revenue",
                  "Data Engineer", "HR Manager"]:
        a = excel_catalog.repository.find_job(title)
        b = db_catalog.repository.find_job(title)
        assert (a is None) == (b is None), f"{title}: {a} vs {b}"
        if a is not None:
            assert a.job_id == b.job_id, f"{title}: {a.job_id} vs {b.job_id}"

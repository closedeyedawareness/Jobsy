"""
tests/test_data_quality.py

Guards the shipped reference library (jobsy_reference_library.xlsx). A bad edit
that drops a profile, band, skill, grade, career path, ISCO code or synonym —
or introduces a dangling reference, duplicate JobID or invalid salary band —
fails here, so regressions never reach the deployed app.
"""
import pandas as pd
import pytest

from core.catalog import Catalog, SHEET_MAP
from core.validator import Validator

WB = "jobsy_reference_library.xlsx"


@pytest.fixture(scope="module")
def catalog():
    return Catalog(WB).load()


@pytest.fixture(scope="module")
def sheets():
    return pd.read_excel(WB, sheet_name=None, dtype=str)


def test_validator_clean(sheets):
    data = {SHEET_MAP[k]: v for k, v in sheets.items() if k in SHEET_MAP}
    report = Validator().validate(data, strict=False)
    assert report.ok, f"validator errors: {report.errors}"


def test_full_coverage(catalog, sheets):
    repo = catalog.repository
    jobs = list(repo.jobs.values())
    iso = {str(r["JobID"]).strip(): str(r.get("IscoGroup", "")).strip() not in ("", "nan")
           for _, r in sheets["Jobs"].iterrows()}
    syn = {}
    for _, r in sheets["TitleMapping"].iterrows():
        syn[str(r["JobID"]).strip()] = syn.get(str(r["JobID"]).strip(), 0) + 1

    missing = {k: [] for k in ("profile", "band", "skills", "grade", "career", "isco", "synonym")}
    for j in jobs:
        if not (repo.profiles.get(j.job_id) and repo.profiles[j.job_id].description):
            missing["profile"].append(j.job_id)
        if (j.function, j.level) not in repo.salary:
            missing["band"].append(j.job_id)
        if not repo.role_skill_map.get(j.job_id):
            missing["skills"].append(j.job_id)
        if not (j.grade or 0):
            missing["grade"].append(j.job_id)
        if not (j.job_id in repo.career_paths or j.standard_title == "Chief Executive Officer"):
            missing["career"].append(j.job_id)
        if not iso.get(j.job_id):
            missing["isco"].append(j.job_id)
        if not syn.get(j.job_id):
            missing["synonym"].append(j.job_id)
    problems = {k: v for k, v in missing.items() if v}
    assert not problems, f"coverage gaps: {problems}"


def test_no_dangling_titlemapping(catalog, sheets):
    ids = set(catalog.repository.jobs.keys())
    dangling = sorted({str(r["JobID"]).strip() for _, r in sheets["TitleMapping"].iterrows()
                       if str(r["JobID"]).strip() not in ids})
    assert not dangling, f"TitleMapping -> unknown JobIDs: {dangling}"


def test_salary_band_ordering(catalog):
    bad = [f"{k[0]}/{k[1]}" for k, b in catalog.repository.salary.items()
           if not (b.min <= b.p50 <= b.max)]
    assert not bad, f"salary bands violating min<=p50<=max: {bad}"


def test_no_duplicate_jobids(sheets):
    ids = [str(r["JobID"]).strip() for _, r in sheets["Jobs"].iterrows()
           if str(r["JobID"]).strip() not in ("", "nan")]
    dupes = sorted({x for x in ids if ids.count(x) > 1})
    assert not dupes, f"duplicate JobIDs: {dupes}"

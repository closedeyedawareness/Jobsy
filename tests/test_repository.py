"""tests/test_repository.py"""

import pytest

from core.models import Job, SalaryBand


def test_jobs_built_as_typed_records(repository):
    assert len(repository.jobs) == 4
    job = repository.jobs["J-HRBP"]
    assert isinstance(job, Job)
    assert job.standard_title == "HR Business Partner"
    assert job.title == "HR Business Partner"  # backward-compat alias
    assert job.function == "HR" and job.level == "Senior"


def test_find_job_is_case_insensitive(repository):
    assert repository.find_job("hr business partner").job_id == "J-HRBP"
    assert repository.find_job("HR BUSINESS PARTNER").job_id == "J-HRBP"


def test_find_job_via_synonym(repository):
    assert repository.find_job("HRBP").job_id == "J-HRBP"
    assert repository.find_job("Boekhouder").job_id == "J-ACC"


def test_find_job_unknown_returns_none(repository):
    assert repository.find_job("Wizard") is None
    assert repository.find_job("") is None


def test_title_mapping_resolves_via_standard_title(repository):
    # "Developer" maps to the standard title "Software Engineer", not a JobID
    assert repository.find_job("Developer").job_id == "J-SE"


def test_salary_band_lookup(repository):
    band = repository.get_salary("HR", "Senior")
    assert isinstance(band, SalaryBand)
    assert band.min == 60000 and band.max == 82000 and band.currency == "EUR"
    assert repository.get_salary("Finance", "Medior") is None  # intentionally absent


def test_grouping_indexes(repository):
    assert {j.job_id for j in repository.jobs_by_function["Engineering"]} == {"J-SE", "J-JSE"}
    assert "Junior" in repository.jobs_by_level
    assert repository.levels == ["Junior", "Medior", "Senior", "Lead"]


def test_statistics(repository):
    stats = repository.statistics()
    assert stats["jobs"] == 4
    assert stats["salary_bands"] == 3
    assert stats["title_mappings"] == 4


# ── 0016: positioning and the grade binding, per market ──────────────────────

import pandas as pd

from core.repository import Repository, _MarketRows


class _Market:
    """Pin the active market for the duration of a block."""

    def __init__(self, code):
        self.code = code

    def __enter__(self):
        import services.country_service as cs
        self._real = cs.active_country
        cs.active_country = lambda: self.code
        return self

    def __exit__(self, *_):
        import services.country_service as cs
        cs.active_country = self._real


def _repo(**frames) -> Repository:
    base = {
        "jobs": pd.DataFrame([{"JobID": "J-1", "StandardTitle": "Controller",
                               "Function": "Finance", "Level": "Senior"}]),
        "titles": pd.DataFrame([{"ExistingTitle": "Controller", "JobID": "J-1"}]),
    }
    base.update(frames)
    return Repository(base, validate=False)


def test_positioning_is_read_from_its_own_table_not_the_flat_column():
    """0016 §3(a): the profile's management level comes from the split table.

    The flat job_profiles.management_level is still live and still arrives in
    the frame. Reading it would give every market the Dutch answer whatever
    job_profile_positioning says, which is the whole reason the column moved.
    """
    repo = _repo(
        profiles=pd.DataFrame([{"JobID": "J-1", "Description": "d",
                                "ManagementLevel": "STALE FLAT VALUE"}]),
        jobpositioning=pd.DataFrame([{"JobID": "J-1", "ManagementLevel": "People Manager",
                                      "Country": "NL"}]),
    )
    with _Market("NL"):
        assert repo.profiles["J-1"].management_level == "People Manager"
        assert repo.management_level_for("J-1") == "People Manager"


def test_a_market_with_no_positioning_row_is_told_nothing():
    """An empty answer is the correct answer.

    "Management level: Lead" is a claim against a national grading instrument —
    the functiegroep here, ERA in Germany — so handing a Belgian client the
    Dutch rung is not a near-enough default, it is a different fact.
    """
    repo = _repo(
        profiles=pd.DataFrame([{"JobID": "J-1", "Description": "d"}]),
        jobpositioning=pd.DataFrame([{"JobID": "J-1", "ManagementLevel": "People Manager",
                                      "Country": "NL"}]),
    )
    with _Market("BE"):
        assert repo.management_level_for("J-1") == ""
        assert repo.job_positioning.get("J-1") is None
        assert len(repo.job_positioning) == 0


def test_the_eu_baseline_still_resolves_under_a_market_of_its_own():
    repo = _repo(
        profiles=pd.DataFrame([{"JobID": "J-1", "Description": "d"}]),
        jobpositioning=pd.DataFrame([
            {"JobID": "J-1", "ManagementLevel": "Manages a team", "Country": "EU"},
            {"JobID": "J-1", "ManagementLevel": "People Manager", "Country": "NL"}]),
    )
    with _Market("BE"):
        assert repo.management_level_for("J-1") == "Manages a team"
    with _Market("NL"):
        assert repo.management_level_for("J-1") == "People Manager", (
            "a market's own row should sit ON TOP of the EU baseline, not under it")


def test_without_a_positioning_frame_the_flat_column_is_read_as_dutch():
    """The workbook path, which has no positioning sheet and is still supported.

    Filed under 'NL' only: 0016 measured every row in the library as Dutch
    before copying it, so that is what those values are. Filing them under
    whichever market is active would be the original defect with a fallback's
    manners.
    """
    repo = _repo(profiles=pd.DataFrame([{"JobID": "J-1", "Description": "d",
                                         "ManagementLevel": "People Manager"}]))
    assert repo.positioning_markets() == ("NL",)
    with _Market("NL"):
        assert repo.profiles["J-1"].management_level == "People Manager"
    with _Market("BE"):
        assert repo.management_level_for("J-1") == ""


def test_the_seniority_binding_is_national_and_the_naming_is_not():
    """L1..L5 and 'Senior' belong to no country; '7-10' points into job_grades,
    which is keyed (org_id, country, grade). A Belgian ladder has no reason to
    have the Dutch fourteen rungs, so the range means something else there."""
    repo = _repo(
        senioritylevels=pd.DataFrame([{"LCode": "L3", "LName": "Senior",
                                       "Definition": "Full professional autonomy.",
                                       "MapsToLevel": "STALE", "GradeRange": "STALE",
                                       "Grades": "STALE"}]),
        senioritybinding=pd.DataFrame([{"LCode": "L3", "MapsToLevel": "Senior",
                                        "GradeRange": "7-10", "Grades": "Grade 7-10",
                                        "Country": "NL"}]),
    )
    with _Market("NL"):
        level = repo.seniority_levels["L3"]
        assert (level.l_name, level.maps_to_level, level.grade_range) == ("Senior", "Senior", "7-10")
        assert level.definition.startswith("Full professional")
    with _Market("BE"):
        assert repo.seniority_binding_for("L3") is None
        assert repo.seniority_levels["L3"].l_name == "Senior", (
            "the naming is universal and must survive a market with no binding")

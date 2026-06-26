"""tests/test_repository.py"""

import pytest

from jobsy.core.models import Job, SalaryBand


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

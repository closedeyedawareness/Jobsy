"""
tests/conftest.py

Shared fixtures. The sample reference data is deliberately small but covers the
tricky cases: a TitleMapping row that resolves via StandardTitle rather than
JobID, a job with no salary band, and a job with no profile.
"""

import pandas as pd
import pytest

from core.repository import Repository
from services.matching_service import MatchingService


@pytest.fixture
def sample_sheets() -> dict:
    jobs = [
        ("J-HRBP", "HR Business Partner", "HR", "Senior"),
        ("J-SE", "Software Engineer", "Engineering", "Medior"),
        ("J-JSE", "Junior Software Engineer", "Engineering", "Junior"),
        ("J-ACC", "Accountant", "Finance", "Medior"),  # no salary band, no profile
    ]
    profiles = [
        ("J-HRBP", "Partners with leaders on people strategy."),
        ("J-SE", "Builds and maintains software features."),
    ]
    titles = [
        {"ExistingTitle": "HRBP", "JobID": "J-HRBP"},
        {"ExistingTitle": "Developer", "StandardTitle": "Software Engineer"},  # via std title
        {"ExistingTitle": "Junior Developer", "JobID": "J-JSE"},
        {"ExistingTitle": "Boekhouder", "JobID": "J-ACC"},
    ]
    salary = [
        ("HR", "Senior", 60000, 82000),
        ("Engineering", "Medior", 55000, 75000),
        ("Engineering", "Junior", 42000, 56000),
    ]
    return {
        "jobs": pd.DataFrame(jobs, columns=["JobID", "StandardTitle", "Function", "Level"]),
        "profiles": pd.DataFrame(profiles, columns=["JobID", "Description"]),
        "titles": pd.DataFrame(titles),
        "salary": pd.DataFrame(salary, columns=["Function", "Level", "Min", "Max"]),
        "career": pd.DataFrame([{"JobID": "J-JSE", "NextJobID": "J-SE"}]),
        "levels": pd.DataFrame([{"Level": x} for x in ("Junior", "Medior", "Senior", "Lead")]),
        "employees": pd.DataFrame([{"EmployeeID": "1", "Name": "Alice", "CurrentTitle": "HRBP"}]),
    }


@pytest.fixture
def repository(sample_sheets) -> Repository:
    return Repository(sample_sheets, validate=True)


class FakeCatalog:
    """Wraps a Repository to satisfy what MatchingService needs."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def get_complete_job(self, job_id: str):
        job = self.repository.jobs.get(job_id)
        if not job:
            return None
        return {
            "job": job,
            "profile": self.repository.profiles.get(job_id),
            "salary": self.repository.salary.get((job.function, job.level)),
            "next_role": self.repository.career_paths.get(job_id),
        }


@pytest.fixture
def catalog(repository) -> FakeCatalog:
    return FakeCatalog(repository)


@pytest.fixture
def service(catalog) -> MatchingService:
    return MatchingService(catalog, index=catalog.repository.index)


# Tests read the library with the operator credential, on purpose.
#
# Since the cutover, config.LIBRARY_CLIENT is "user": the app reads the
# reference library through the signed-in person's own client so that the row
# policies decide what comes back, and it refuses rather than falling back when
# nobody is signed in. A test process has nobody signed in, and a silent fall
# back is exactly what the switch exists to remove -- so the tests say which
# credential they mean, here, before any module-scoped fixture loads a catalog.
# The user-mode behaviour itself is pinned in tests/test_db_loader.py, and the
# signed-in walk lives in tools/walk_signed_in.py.
import core.config as _cfg  # noqa: E402
_cfg.LIBRARY_CLIENT = "secret"

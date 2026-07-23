"""
tests/test_assessment_service.py

Path B — SkillAssessment loading + the AssessmentService coverage/gap/career
maths, on a small fixture whose declared skills use the canonical vocabulary
(so resolution is exact and the numbers are checkable by hand).
"""

import pandas as pd
import pytest

from core.repository import Repository
from services.assessment_service import (
    DEFAULT_CONFIDENCE, AssessmentService, service_for_assessments)


class _Cat:
    """Minimal Catalog stand-in — the service only needs `.repository`."""
    def __init__(self, repo):
        self.repository = repo


@pytest.fixture
def repo() -> Repository:
    sheets = {
        "jobs": pd.DataFrame(
            [("J-JSE", "Junior Software Engineer", "Engineering", "Junior"),
             ("J-SE", "Software Engineer", "Engineering", "Medior")],
            columns=["JobID", "StandardTitle", "Function", "Level"]),
        "titles": pd.DataFrame([
            {"ExistingTitle": "Junior Software Engineer", "JobID": "J-JSE"},
            {"ExistingTitle": "Software Engineer", "JobID": "J-SE"}]),
        "career": pd.DataFrame([{"JobID": "J-JSE", "NextJobID": "J-SE"}]),
        "levels": pd.DataFrame([{"Level": x} for x in ("Junior", "Medior", "Senior", "Lead")]),
        "skills": pd.DataFrame(
            [("SK-PY", "Python", "Technical"),
             ("SK-SQL", "SQL", "Technical"),
             ("SK-COMM", "Communication", "Human")],
            columns=["SkillID", "SkillName", "Category"]),
        "roleskillmap": pd.DataFrame([
            ("J-JSE", "SK-PY", 3, "Core"), ("J-JSE", "SK-SQL", 2, "Core"), ("J-JSE", "SK-COMM", 2, "Adjacent"),
            ("J-SE", "SK-PY", 4, "Core"), ("J-SE", "SK-SQL", 3, "Core"), ("J-SE", "SK-COMM", 3, "Adjacent")],
            columns=["JobID", "SkillID", "RequiredLevel", "SkillType"]),
        "employees": pd.DataFrame([{
            "EmployeeID": "E1", "Name": "Dev", "CurrentTitle": "Junior Software Engineer",
            "SkillProficiency": "Python:Advanced; SQL:Basic"}]),  # PY=4, SQL=2, no Communication
    }
    return Repository(sheets, validate=False)


def test_assessments_parsed_and_resolved(repo):
    assert repo.skill_assessment_resolution["resolved"] == 2      # Python, SQL both canonical
    assert repo.skill_assessment_resolution["resolution_rate"] == 1.0
    a = {x.skill_id: x for x in repo.skill_assessments["E1"]}
    assert a["SK-PY"].current_level == 4 and a["SK-PY"].source == "self"
    assert a["SK-SQL"].current_level == 2


def test_coverage_and_gaps(repo):
    svc = AssessmentService(_Cat(repo))
    cov = svc.coverage_for_employee("E1")
    assert cov.job_id == "J-JSE"
    # required PY3/SQL2/COMM2 vs held PY4/SQL2/COMM0 → met = 3+2+0 of 7
    assert cov.coverage == pytest.approx(5 / 7, abs=1e-3)
    open_ids = {g.skill_id: g.gap for g in cov.open_gaps}
    assert open_ids == {"SK-COMM": 2}          # only Communication is short
    # over-qualification never shows as a negative gap
    py = next(g for g in cov.gaps if g.skill_id == "SK-PY")
    assert py.gap == 0


def test_career_opportunity_readiness(repo):
    svc = AssessmentService(_Cat(repo))
    opps = svc.career_opportunities("E1")
    assert len(opps) == 1
    o = opps[0]
    assert o.to_job_id == "J-SE" and o.ready is False       # SQL & COMM short of the next role
    assert o.readiness == pytest.approx(6 / 10, abs=1e-3)   # met 4+2+0 of 4+3+3


def test_team_summary(repo):
    svc = AssessmentService(_Cat(repo))
    s = svc.team_summary()
    assert s["employees_matched"] == 1
    assert s["avg_coverage"] == pytest.approx(5 / 7, abs=1e-3)
    # PY & SQL are self-rated (0.5), Communication is unassessed (0.0) → mean 1/3.
    # An unmeasured skill honestly carries zero confidence.
    assert s["avg_confidence"] == pytest.approx(1 / 3, abs=1e-3)
    assert s["open_gaps"] == 1


# ------------------------------------------------------- the upload/session bridge
# The assessment page holds {employee_key: {skill_id: level}} in session state,
# keyed by a display string and carrying no source/confidence. These cover the
# bridge that presents that shape to the service without touching the reference
# repository.

def test_bridge_resolves_each_person_to_their_own_role(repo):
    svc = service_for_assessments(
        _Cat(repo),
        {"Ada Lovelace (E9)": {"SK-PY": 4, "SK-SQL": 2}},
        titles={"Ada Lovelace (E9)": "Junior Software Engineer"})
    cov = svc.coverage_for_employee("Ada Lovelace (E9)")
    assert cov.job_id == "J-JSE"                 # resolved from the title, not picked from a list
    assert cov.coverage == pytest.approx(5 / 7, abs=1e-3)
    assert {g.skill_id: g.gap for g in cov.open_gaps} == {"SK-COMM": 2}


def test_bridge_does_not_mutate_the_reference_repository(repo):
    before_emps = dict(repo.employees)
    before_rows = {k: list(v) for k, v in repo.skill_assessments.items()}
    service_for_assessments(_Cat(repo), {"Someone New": {"SK-PY": 5}},
                            titles={"Someone New": "Software Engineer"})
    assert repo.employees == before_emps
    assert {k: list(v) for k, v in repo.skill_assessments.items()} == before_rows
    assert "Someone New" not in repo.employees


def test_bridge_confidence_follows_the_source(repo):
    people = {"P": {"SK-PY": 3}}
    titles = {"P": "Junior Software Engineer"}
    for source, expected in DEFAULT_CONFIDENCE.items():
        svc = service_for_assessments(_Cat(repo), people, titles=titles, source=source)
        py = next(g for g in svc.coverage_for_employee("P").gaps if g.skill_id == "SK-PY")
        assert py.confidence == pytest.approx(expected)
    # an explicit override still wins
    svc = service_for_assessments(_Cat(repo), people, titles=titles, confidence=0.9)
    py = next(g for g in svc.coverage_for_employee("P").gaps if g.skill_id == "SK-PY")
    assert py.confidence == pytest.approx(0.9)


def test_bridge_gives_career_opportunity_through_the_overlay(repo):
    svc = service_for_assessments(
        _Cat(repo),
        {"P": {"SK-PY": 4, "SK-SQL": 2}},
        titles={"P": "Junior Software Engineer"})
    opps = svc.career_opportunities("P")
    assert len(opps) == 1 and opps[0].to_job_id == "J-SE"
    assert opps[0].ready is False
    assert opps[0].readiness == pytest.approx(6 / 10, abs=1e-3)


def test_bridge_falls_back_to_the_reference_employee_title(repo):
    # No title supplied, but E1 exists in the reference workbook.
    svc = service_for_assessments(_Cat(repo), {"E1": {"SK-PY": 4}})
    assert svc.coverage_for_employee("E1").job_id == "J-JSE"


def test_bridge_drops_unrated_skills(repo):
    svc = service_for_assessments(
        _Cat(repo), {"P": {"SK-PY": 4, "SK-SQL": 0, "SK-COMM": None}},
        titles={"P": "Junior Software Engineer"})
    cov = svc.coverage_for_employee("P")
    held = {g.skill_id: g.current_level for g in cov.gaps}
    assert held["SK-PY"] == 4
    assert held["SK-SQL"] == 0 and held["SK-COMM"] == 0   # unrated reads as unassessed, not as zero skill
    assert next(g for g in cov.gaps if g.skill_id == "SK-SQL").confidence == 0.0


def test_bridge_team_summary_covers_the_uploaded_cohort_only(repo):
    svc = service_for_assessments(
        _Cat(repo),
        {"A": {"SK-PY": 4, "SK-SQL": 2, "SK-COMM": 2},
         "B": {"SK-PY": 1}},
        titles={"A": "Junior Software Engineer", "B": "Junior Software Engineer"})
    s = svc.team_summary()
    assert s["employees_matched"] == 2          # E1 from the reference file is not counted
    assert s["open_gaps"] == 3                  # A fully covered; B short on all three

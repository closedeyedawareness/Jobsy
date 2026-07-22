"""Tests for the skills-dashboard data layer (aggregation, treemap, wheel SVG)."""

from __future__ import annotations

import math

import pytest

from services.skills_dashboard_service import (
    SkillDemand,
    build_wheel_svg,
    overlay_supply,
    skill_demand,
    squarify,
)


class _Skill:
    def __init__(self, sid, name, cat):
        self.skill_id, self.skill_name, self.category = sid, name, cat


class _Req:
    def __init__(self, sid, lvl, typ):
        self.skill_id, self.required_level, self.skill_type = sid, lvl, typ


class _Repo:
    def __init__(self):
        self.skills = {
            "S1": _Skill("S1", "Financial reporting", "Finance & Accounting"),
            "S2": _Skill("S2", "Stakeholder management", "Leadership"),
        }
        self.role_skill_map = {
            "J1": [_Req("S1", 4, "Core"), _Req("S2", 3, "Leadership")],
            "J2": [_Req("S1", 3, "Core")],
        }


class _Assessment:
    def __init__(self, sid, lvl):
        self.skill_id, self.current_level = sid, lvl


def test_skill_demand_counts_roles_and_core():
    d = skill_demand(_Repo())
    s1 = next(s for s in d if s.skill_id == "S1")
    assert s1.n_roles == 2 and s1.n_core == 2 and s1.max_required_level == 4
    s2 = next(s for s in d if s.skill_id == "S2")
    assert s2.n_roles == 1 and s2.n_core == 0


def test_overlay_supply_adds_holders_and_avg():
    d = overlay_supply(skill_demand(_Repo()), [_Assessment("S1", 3), _Assessment("S1", 5)])
    s1 = next(s for s in d if s.skill_id == "S1")
    assert s1.n_holders == 2 and s1.avg_level_held == 4.0
    s2 = next(s for s in d if s.skill_id == "S2")
    assert s2.n_holders == 0 and s2.avg_level_held is None


def test_squarify_covers_the_area_exactly():
    rects = squarify([("a", 6), ("b", 3), ("c", 1)], 0, 0, 100, 60)
    assert len(rects) == 3
    area = sum(r.w * r.h for r in rects)
    assert area == pytest.approx(6000, rel=1e-6)
    # every rect stays inside the canvas
    for r in rects:
        assert r.x >= -1e-9 and r.y >= -1e-9
        assert r.x + r.w <= 100 + 1e-6 and r.y + r.h <= 60 + 1e-6


def test_squarify_is_value_proportional():
    rects = squarify([("big", 9), ("small", 1)], 0, 0, 100, 100)
    big = next(r for r in rects if r.label == "big")
    small = next(r for r in rects if r.label == "small")
    assert (big.w * big.h) / (small.w * small.h) == pytest.approx(9, rel=1e-6)


def test_squarify_drops_nonpositive_values():
    assert squarify([("z", 0), ("n", -4)], 0, 0, 10, 10) == []


def test_wheel_svg_draws_all_spokes_and_overlay():
    reqs = [{"skill": "Financial reporting", "level": 4, "type": "Core"},
            {"skill": "Stakeholder management", "level": 3, "type": "Leadership"}]
    svg = build_wheel_svg("Financial Controller", reqs,
                          overlay_levels={"Financial reporting": 2.5})
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    # 2 spokes x 5 rings + 1 overlay arc = 11 sector paths
    assert svg.count("<path") == 11
    assert "Financial reporting" in svg and "Stakeholder manage" in svg
    assert "#FF73D0" in svg          # overlay drawn
    assert 'font-weight="700"' in svg  # Core skill bolded (and hub title)


def test_wheel_svg_empty_requirements_is_safe():
    assert build_wheel_svg("Empty", []) == "<svg></svg>"


from services.skills_dashboard_service import (
    FUTURE_SKILLS,
    function_overlaps,
    function_skill_profiles,
    future_skill_readiness,
)


class _Job:
    def __init__(self, jid, function):
        self.job_id, self.function = jid, function


class _Repo2:
    """Two functions sharing one skill (S1); one function-exclusive skill each."""
    def __init__(self):
        self.skills = {
            "S1": _Skill("S1", "Machine learning and AI", "Data & Analytics"),
            "S2": _Skill("S2", "Financial reporting", "Finance & Accounting"),
            "S3": _Skill("S3", "Team leadership and development", "Leadership"),
        }
        self.jobs = {
            "J1": _Job("J1", "Finance"),
            "J2": _Job("J2", "Data"),
        }
        self.role_skill_map = {
            "J1": [_Req("S1", 2, "Adjacent"), _Req("S2", 4, "Core")],
            "J2": [_Req("S1", 4, "Core"), _Req("S3", 3, "Leadership")],
        }


def test_function_profiles_take_max_level():
    prof = function_skill_profiles(_Repo2())
    assert prof["Finance"] == {"S1": 2, "S2": 4}
    assert prof["Data"] == {"S1": 4, "S3": 3}


def test_function_overlap_math():
    o = function_overlaps(_Repo2())[0]
    assert {o.function_a, o.function_b} == {"Data", "Finance"}
    assert o.jaccard == pytest.approx(1 / 3, abs=5e-4)  # 1 shared of 3 distinct
    # cosine = (2*4) / (sqrt(2^2+4^2) * sqrt(4^2+3^2)) = 8 / (sqrt20*5)
    assert o.cosine == pytest.approx(8 / (math.sqrt(20) * 5), abs=1e-3)
    assert o.shared_skills == ("Machine learning and AI",)


def test_future_readiness_statuses_and_transparency():
    r = future_skill_readiness(_Repo2(), emerging_role_threshold=5)
    by_name = {f.name: f for f in r}
    ai = by_name["AI & big data"]
    assert "Machine learning and AI" in ai.matched_skills   # mapping is visible
    assert ai.n_roles_requiring == 2 and ai.status == "Emerging"
    esg = by_name["Environmental stewardship / ESG"]
    assert esg.matched_skills == () and esg.status == "Not in catalogue"
    # ordering: worst first (Not in catalogue before Emerging before Covered)
    statuses = [f.status for f in r]
    assert statuses.index("Not in catalogue") < statuses.index("Emerging")


def test_future_readiness_counts_holders_from_assessments():
    r = future_skill_readiness(_Repo2(), assessments=[_Assessment("S1", 3), _Assessment("S1", 4)])
    ai = next(f for f in r if f.name == "AI & big data")
    assert ai.n_holders == 2


def test_every_future_skill_has_a_source():
    assert all(f["source"] for f in FUTURE_SKILLS)

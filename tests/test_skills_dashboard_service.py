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

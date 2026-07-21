"""
jobsy/services/skills_dashboard_service.py

Data layer for the Skills Dashboard page — the "skills-based organisation"
lens over the reference library and (when uploaded) a workforce file.

Three views, mirroring the design posters (2026-07-21):
  * headline tiles      — categories / skills / roles / assessed people
  * category treemap    — skills sized by demand (roles requiring) or supply
                          (people holding), squarified layout computed here in
                          pure python so the UI just draws rectangles
  * proficiency wheel   — per-role radial matrix: spokes = the role's required
                          skills, rings = levels 1-5, coloured to required
                          level, with a person/team overlay when assessments
                          exist. Rendered as SVG by build_wheel_svg().

Honesty rule carried over from the Path B work: DECLARED skills are not
VALIDATED skills. Wherever headcount appears next to a skill it is labelled
with its source; the earlier finding that only ~5% of free-text declared
skills resolve to the canonical catalogue is exactly why assessments must be
captured against the catalogue for any of this to be structural truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# ── aggregations ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SkillDemand:
    skill_id: str
    skill_name: str
    category: str
    n_roles: int                 # roles requiring it (reference library)
    max_required_level: int
    n_core: int                  # in how many roles it's a Core requirement
    n_holders: int = 0           # people with an assessment >= 1 (workforce, optional)
    avg_level_held: float | None = None


def skill_demand(repo) -> list[SkillDemand]:
    """Demand-side aggregation from the reference library alone."""
    per_skill: dict[str, dict] = {}
    for job_id, reqs in repo.role_skill_map.items():
        for r in reqs:
            d = per_skill.setdefault(r.skill_id, {"n_roles": 0, "max_lvl": 0, "n_core": 0})
            d["n_roles"] += 1
            d["max_lvl"] = max(d["max_lvl"], r.required_level)
            if r.skill_type == "Core":
                d["n_core"] += 1
    out = []
    for sid, d in per_skill.items():
        sk = repo.skills.get(sid)
        out.append(SkillDemand(
            skill_id=sid,
            skill_name=sk.skill_name if sk else sid,
            category=sk.category if sk else "—",
            n_roles=d["n_roles"], max_required_level=d["max_lvl"], n_core=d["n_core"],
        ))
    return sorted(out, key=lambda s: (-s.n_roles, s.skill_name))


def overlay_supply(demand: list[SkillDemand], assessments) -> list[SkillDemand]:
    """Merge workforce supply (SkillAssessment list) onto the demand rows."""
    holders: dict[str, list[int]] = {}
    for a in assessments:
        holders.setdefault(a.skill_id, []).append(a.current_level)
    out = []
    for s in demand:
        lv = holders.get(s.skill_id, [])
        out.append(SkillDemand(
            skill_id=s.skill_id, skill_name=s.skill_name, category=s.category,
            n_roles=s.n_roles, max_required_level=s.max_required_level, n_core=s.n_core,
            n_holders=len(lv), avg_level_held=(round(sum(lv) / len(lv), 1) if lv else None),
        ))
    return out


# ── squarified treemap (pure python; UI just draws the rects) ────────────────

@dataclass
class TreemapRect:
    label: str
    value: float
    x: float
    y: float
    w: float
    h: float


def squarify(items: list[tuple[str, float]], x: float, y: float, w: float, h: float) -> list[TreemapRect]:
    """
    Squarified treemap (Bruls et al. approach, simplified): lay rows of items
    along the shorter side, keeping aspect ratios near 1. items = (label, value),
    value > 0; returns rects in the same coordinate space as (x, y, w, h).
    """
    items = [(l, v) for l, v in items if v > 0]
    if not items:
        return []
    total = sum(v for _, v in items)
    scale = (w * h) / total
    scaled = sorted(((l, v * scale) for l, v in items), key=lambda t: -t[1])

    rects: list[TreemapRect] = []

    def worst(row: list[float], side: float) -> float:
        s = sum(row)
        if not row or s == 0 or side == 0:
            return math.inf
        mx, mn = max(row), min(row)
        return max((side * side * mx) / (s * s), (s * s) / (side * side * mn))

    def layout_row(row_items: list[tuple[str, float]], rx, ry, rw, rh):
        s = sum(v for _, v in row_items)
        if rw >= rh:   # lay the row vertically along the left edge
            col_w = s / rh if rh else 0
            yy = ry
            for l, v in row_items:
                hh = v / col_w if col_w else 0
                rects.append(TreemapRect(l, v, rx, yy, col_w, hh))
                yy += hh
            return rx + col_w, ry, rw - col_w, rh
        else:          # lay the row horizontally along the top edge
            row_h = s / rw if rw else 0
            xx = rx
            for l, v in row_items:
                ww = v / row_h if row_h else 0
                rects.append(TreemapRect(l, v, xx, ry, ww, row_h))
                xx += ww
            return rx, ry + row_h, rw, rh - row_h

    row: list[tuple[str, float]] = []
    rx, ry, rw, rh = x, y, w, h
    for label, val in scaled:
        side = min(rw, rh)
        if not row or worst([v for _, v in row] + [val], side) <= worst([v for _, v in row], side):
            row.append((label, val))
        else:
            rx, ry, rw, rh = layout_row(row, rx, ry, rw, rh)
            row = [(label, val)]
    if row:
        layout_row(row, rx, ry, rw, rh)
    return rects


# ── proficiency wheel (SVG) ──────────────────────────────────────────────────

# Ring palette, level 1 (inner) -> 5 (outer): Jobsy indigo->violet ramp.
_RING_FILL = ["#3B2064", "#4A2A80", "#5C35A3", "#6F3CFF", "#A77BFF"]
_EMPTY_RING = "#2C1652"
_OVERLAY = "#FF73D0"   # person/team overlay stroke (brand pink)


def build_wheel_svg(role_title: str, requirements: list[dict], *, size: int = 640,
                    overlay_levels: dict[str, float] | None = None) -> str:
    """
    Radial proficiency matrix for one role.

    requirements: [{skill, level (1-5 required), type (Core/Adjacent/Leadership)}]
    overlay_levels: optional {skill: current_level} (person or team average) —
    drawn as a pink arc on top of the required fill, so gaps are visible as
    unfilled required rings.
    """
    n = len(requirements)
    if n == 0:
        return "<svg></svg>"
    cx = cy = size / 2
    hub_r = size * 0.14
    ring_w = (size * 0.30 - hub_r) / 5   # 5 level rings between hub and label zone
    label_r = size * 0.40

    def arc_path(r_in: float, r_out: float, a0: float, a1: float) -> str:
        # annular sector path; angles in radians, clockwise from 12 o'clock
        def pt(r, a):
            return (cx + r * math.sin(a), cy - r * math.cos(a))
        large = 1 if (a1 - a0) > math.pi else 0
        x0o, y0o = pt(r_out, a0); x1o, y1o = pt(r_out, a1)
        x1i, y1i = pt(r_in, a1); x0i, y0i = pt(r_in, a0)
        return (f"M {x0o:.1f} {y0o:.1f} A {r_out:.1f} {r_out:.1f} 0 {large} 1 {x1o:.1f} {y1o:.1f} "
                f"L {x1i:.1f} {y1i:.1f} A {r_in:.1f} {r_in:.1f} 0 {large} 0 {x0i:.1f} {y0i:.1f} Z")

    gap = 0.012  # radial gap between sectors, radians
    seg = 2 * math.pi / n
    # Side padding in the viewBox so start/end-anchored labels never clip at
    # the edges (labels extend outward from label_r).
    pad = size * 0.16
    parts: list[str] = [
        f'<svg viewBox="{-pad:.0f} 0 {size + 2 * pad:.0f} {size}" xmlns="http://www.w3.org/2000/svg" '
        f'style="max-width:100%;height:auto;font-family:IBM Plex Sans,system-ui,sans-serif">'
    ]

    for i, req in enumerate(requirements):
        a0 = i * seg + gap
        a1 = (i + 1) * seg - gap
        lvl = max(0, min(5, int(req.get("level") or 0)))
        for ring in range(5):
            r_in = hub_r + ring * ring_w
            r_out = r_in + ring_w * 0.92
            fill = _RING_FILL[ring] if ring < lvl else _EMPTY_RING
            opacity = "1" if ring < lvl else "0.55"
            parts.append(f'<path d="{arc_path(r_in, r_out, a0, a1)}" fill="{fill}" opacity="{opacity}"/>')
        if overlay_levels:
            cur = overlay_levels.get(req["skill"])
            if cur is not None and cur > 0:
                r_cur = hub_r + max(0.0, min(5.0, float(cur))) * ring_w
                parts.append(f'<path d="{arc_path(r_cur - 2.5, r_cur, a0, a1)}" fill="{_OVERLAY}"/>')
        # label
        mid = (a0 + a1) / 2
        lx = cx + label_r * math.sin(mid)
        ly = cy - label_r * math.cos(mid)
        anchor = "start" if math.sin(mid) > 0.15 else ("end" if math.sin(mid) < -0.15 else "middle")
        label = req["skill"] if len(req["skill"]) <= 26 else req["skill"][:24] + "…"
        core = "700" if req.get("type") == "Core" else "400"
        parts.append(f'<text x="{lx:.0f}" y="{ly:.0f}" text-anchor="{anchor}" '
                     f'font-size="{size*0.021:.0f}" font-weight="{core}" fill="#C9B8E8">{label}</text>')

    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{hub_r}" fill="#160A2B" stroke="#4D2F75"/>')
    title = role_title if len(role_title) <= 22 else role_title[:20] + "…"
    parts.append(f'<text x="{cx}" y="{cy - 6}" text-anchor="middle" font-size="{size*0.028:.0f}" '
                 f'font-weight="700" fill="#FFFFFF">{title}</text>')
    parts.append(f'<text x="{cx}" y="{cy + size*0.03:.0f}" text-anchor="middle" '
                 f'font-size="{size*0.019:.0f}" fill="#C9B8E8">skills matrix</text>')
    parts.append("</svg>")
    return "".join(parts)

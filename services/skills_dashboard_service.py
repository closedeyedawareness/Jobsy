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


# ── departmental overlap (skills shared across functions) ───────────────────

@dataclass(frozen=True)
class FunctionOverlap:
    function_a: str
    function_b: str
    jaccard: float               # shared / union of DISTINCT skills
    cosine: float                # level-weighted profile similarity
    shared_skills: tuple[str, ...]   # names, sorted by combined weight desc


def function_skill_profiles(repo) -> dict[str, dict[str, int]]:
    """{function: {skill_id: max required_level across that function's roles}}."""
    prof: dict[str, dict[str, int]] = {}
    for job_id, reqs in repo.role_skill_map.items():
        job = repo.jobs.get(job_id)
        if not job:
            continue
        p = prof.setdefault(job.function, {})
        for r in reqs:
            p[r.skill_id] = max(p.get(r.skill_id, 0), r.required_level)
    return prof


def function_overlaps(repo) -> list[FunctionOverlap]:
    """
    Pairwise skill overlap between functions/departments -- the internal
    mobility corridors of a skills-based organisation: a big overlap means
    people can cross between those departments on capabilities they already
    share. Cosine on level-weighted profiles (same approach the Skills
    Intelligence report uses); Jaccard on distinct-skill sets for the more
    intuitive "share N of their combined skills" read.
    """
    prof = function_skill_profiles(repo)
    fns = sorted(prof.keys())
    out: list[FunctionOverlap] = []
    for i in range(len(fns)):
        for j in range(i + 1, len(fns)):
            a, b = prof[fns[i]], prof[fns[j]]
            shared_ids = set(a) & set(b)
            union = set(a) | set(b)
            jac = len(shared_ids) / len(union) if union else 0.0
            dot = sum(a[s] * b[s] for s in shared_ids)
            na = math.sqrt(sum(v * v for v in a.values()))
            nb = math.sqrt(sum(v * v for v in b.values()))
            cos = dot / (na * nb) if na and nb else 0.0
            names = sorted(shared_ids, key=lambda s: -(a[s] + b[s]))
            skill_names = tuple(
                (repo.skills[s].skill_name if s in repo.skills else s) for s in names)
            out.append(FunctionOverlap(fns[i], fns[j], round(jac, 3), round(cos, 3), skill_names))
    return sorted(out, key=lambda o: -o.cosine)


# ── skills of the future (sourced analytical overlay) ───────────────────────
# Sources -- same evidence base the Skills Intelligence report cites:
#   [WEF]  World Economic Forum, Future of Jobs Report 2025 (core skills 2025-2030)
#   [LI]   LinkedIn, Skills on the Rise 2025
# This is an ANALYTICAL OVERLAY: future skills are matched to the org's own
# catalogue by transparent keyword rules (matches shown to the user), never
# presented as a measured fact about the organisation.

FUTURE_SKILLS: list[dict] = [
    {"name": "AI & big data",                       "source": "WEF 2025 #1 fastest-growing",
     "keywords": ["machine learning", "ai", "data analysis", "statistical", "data pipeline", "business intelligence"]},
    {"name": "AI literacy (applied, non-specialist)", "source": "LinkedIn 2025 #1 rising",
     "keywords": ["machine learning and ai", "data-driven decision", "email marketing and automation"]},
    {"name": "Networks & cybersecurity",            "source": "WEF 2025 top-3 growing",
     "keywords": ["security engineering", "gdpr", "cloud infrastructure"]},
    {"name": "Technological literacy",              "source": "WEF 2025 core skill",
     "keywords": ["cloud", "api", "programming", "javascript", "sql", "frontend", "ci/cd", "container", "infrastructure"]},
    {"name": "Analytical & systems thinking",       "source": "WEF 2025 #1 core skill",
     "keywords": ["problem structuring", "requirements analysis", "data analysis", "financial modelling", "statistical"]},
    {"name": "Creative thinking",                   "source": "WEF 2025 core skill",
     "keywords": ["content strategy", "brand management", "go-to-market"]},
    {"name": "Resilience, flexibility & agility",   "source": "WEF 2025 core skill",
     "keywords": ["change management"]},
    {"name": "Curiosity & lifelong learning",       "source": "WEF 2025 core skill",
     "keywords": ["coaching and mentoring", "talent management"]},
    {"name": "Leadership & social influence",       "source": "WEF 2025 core skill",
     "keywords": ["team leadership", "stakeholder management", "board and executive"]},
    {"name": "Conflict mitigation & negotiation",   "source": "LinkedIn 2025 rising",
     "keywords": ["negotiation", "employee relations"]},
    {"name": "Process optimization",                "source": "LinkedIn 2025 rising",
     "keywords": ["process improvement", "project management"]},
    {"name": "Environmental stewardship / ESG",     "source": "WEF 2025 rising",
     "keywords": ["sustainab", "esg", "environment"]},
]


@dataclass(frozen=True)
class FutureSkillStatus:
    name: str
    source: str
    matched_skills: tuple[str, ...]   # catalogue skills the keywords hit (transparency)
    n_roles_requiring: int            # demand-side presence across matched skills
    n_holders: int                    # supply-side (assessments), 0 when none uploaded
    status: str                       # "Covered" | "Emerging" | "Missing" | "Not in catalogue"


def future_skill_readiness(repo, assessments=None, *, emerging_role_threshold: int = 5) -> list[FutureSkillStatus]:
    """
    For each sourced future skill: which catalogue skills match (shown, so the
    mapping is checkable), how many roles require any of them, how many people
    hold any of them (if assessments exist), and an honest status:
      Not in catalogue -- the org's taxonomy can't even SEE this skill yet
      Missing          -- in the taxonomy, but no role requires it
      Emerging         -- required by fewer than `emerging_role_threshold` roles
      Covered          -- structurally present across the role architecture
    """
    demand = {s.skill_id: s for s in skill_demand(repo)}
    holders_by_skill: dict[str, int] = {}
    for a in (assessments or []):
        if getattr(a, "current_level", 0) and a.current_level > 0:
            holders_by_skill[a.skill_id] = holders_by_skill.get(a.skill_id, 0) + 1

    out: list[FutureSkillStatus] = []
    for fs in FUTURE_SKILLS:
        kws = [k.lower() for k in fs["keywords"]]
        matched_ids = [
            sid for sid, sk in repo.skills.items()
            if any(k in sk.skill_name.lower() for k in kws)
        ]
        n_roles = sum(demand[sid].n_roles for sid in matched_ids if sid in demand)
        n_holds = sum(holders_by_skill.get(sid, 0) for sid in matched_ids)
        if not matched_ids:
            status = "Not in catalogue"
        elif n_roles == 0:
            status = "Missing"
        elif n_roles < emerging_role_threshold:
            status = "Emerging"
        else:
            status = "Covered"
        names = tuple(sorted(repo.skills[s].skill_name for s in matched_ids))
        out.append(FutureSkillStatus(fs["name"], fs["source"], names, n_roles, n_holds, status))
    _rank = {"Not in catalogue": 0, "Missing": 1, "Emerging": 2, "Covered": 3}
    return sorted(out, key=lambda f: (_rank[f.status], -f.n_roles_requiring))


# ── declared skills by department (from an uploaded workforce file) ─────────

@dataclass(frozen=True)
class DeclaredSkillRow:
    skill_id: str
    skill_name: str
    total_holders: int
    by_department: dict[str, float]   # department -> % of that dept's assessed people holding it


@dataclass(frozen=True)
class DeclaredSkillsHeatmap:
    departments: tuple[tuple[str, int], ...]   # (name, headcount assessed), desc by headcount
    rows: tuple[DeclaredSkillRow, ...]          # desc by total_holders


def declared_skills_heatmap(
    assessments_by_emp: dict, emp_department: dict, repo, *, max_skills: int = 18
) -> DeclaredSkillsHeatmap:
    """
    Cross-tab of SELF-DECLARED skills (from an uploaded workforce/assessment file)
    against department -- "who says they can do what, and where". Deliberately
    separate from skill_demand/overlay_supply (which read the ROLE architecture):
    this is what people claim about themselves, unresolved against any role
    requirement. Declared is not validated -- render this labelled as such.

    assessments_by_emp: {emp_key: {skill_id: level}} (session skill_assessments)
    emp_department: {emp_key: department_name}, same keys as assessments_by_emp
    """
    dept_headcount: dict[str, int] = {}
    dept_holders: dict[str, dict[str, int]] = {}
    skill_total: dict[str, int] = {}
    for emp, skills in assessments_by_emp.items():
        dept = emp_department.get(emp) or "Unassigned"
        dept_headcount[dept] = dept_headcount.get(dept, 0) + 1
        for sid, lvl in skills.items():
            if not lvl or lvl <= 0:
                continue
            bucket = dept_holders.setdefault(dept, {})
            bucket[sid] = bucket.get(sid, 0) + 1
            skill_total[sid] = skill_total.get(sid, 0) + 1

    departments = tuple(sorted(dept_headcount.items(), key=lambda kv: -kv[1]))
    top_skills = sorted(skill_total.items(), key=lambda kv: -kv[1])[:max_skills]
    rows = []
    for sid, total in top_skills:
        name = repo.skills[sid].skill_name if sid in repo.skills else sid
        by_dept = {}
        for dept, headcount in departments:
            n = dept_holders.get(dept, {}).get(sid, 0)
            by_dept[dept] = round(100 * n / headcount, 0) if headcount else 0.0
        rows.append(DeclaredSkillRow(sid, name, total, by_dept))
    return DeclaredSkillsHeatmap(departments=departments, rows=tuple(rows))


# ── shared-capability index: full matrix + redeployment narrative ──────────

@dataclass(frozen=True)
class RedeploymentLane:
    a: str
    b: str
    cosine: float
    top_skill: str | None


@dataclass(frozen=True)
class RedeploymentSummary:
    functions: tuple[str, ...]                 # axis order for the matrix, desc by avg similarity
    matrix: dict[tuple[str, str], float]       # (a,b) AND (b,a) populated; no self-pairs
    top_lanes: tuple[RedeploymentLane, ...]
    most_isolated: str | None
    most_isolated_avg: float | None


def redeployment_summary(repo, *, top_n: int = 3) -> RedeploymentSummary:
    """
    Full department x department shared-capability matrix (cosine, symmetric),
    plus the synthesis a static overlap table can't give at a glance: the
    strongest redeployment lanes (named by their biggest shared skill) and
    which department is structurally most isolated -- the one whose specialist
    skills have no natural backup anywhere else in the org.
    """
    overlaps = function_overlaps(repo)
    prof = function_skill_profiles(repo)
    fns = sorted(prof.keys())

    matrix: dict[tuple[str, str], float] = {}
    for o in overlaps:
        matrix[(o.function_a, o.function_b)] = o.cosine
        matrix[(o.function_b, o.function_a)] = o.cosine

    avg_by_fn: dict[str, float] = {}
    for f in fns:
        vals = [matrix[(f, g)] for g in fns if g != f and (f, g) in matrix]
        avg_by_fn[f] = sum(vals) / len(vals) if vals else 0.0

    ordered_fns = tuple(sorted(fns, key=lambda f: -avg_by_fn.get(f, 0.0)))
    most_isolated = min(avg_by_fn, key=lambda f: avg_by_fn[f]) if avg_by_fn else None

    top = sorted(overlaps, key=lambda o: -o.cosine)[:top_n]
    lanes = tuple(
        RedeploymentLane(o.function_a, o.function_b, o.cosine,
                        o.shared_skills[0] if o.shared_skills else None)
        for o in top
    )
    return RedeploymentSummary(
        functions=ordered_fns, matrix=matrix, top_lanes=lanes,
        most_isolated=most_isolated,
        most_isolated_avg=(round(avg_by_fn[most_isolated], 3) if most_isolated else None),
    )

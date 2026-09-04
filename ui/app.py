"""
jobsy/ui/app.py  —  Streamlit front end for Jobsy V1
Run with:  streamlit run ui/app.py

The chrome, the Matching page and the routing. Every other page lives in
ui/views/, and the shared theme and helpers in ui/shared.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ui.shared import *  # noqa: F401,F403
from ui.views.connect import connect_page
from ui.views.architecture_report import architecture_report_page
from ui.views.job_family import job_family_page
from ui.views.data_quality import data_quality_page, FRESH_DAYS, STALE_DAYS
from ui.views.pay_equity import pay_equity_page
from ui.views.benefits import benefits_benchmarking_page
from ui.views.skill_gap import skill_gap_page
from ui.views.skills_dashboard import skills_dashboard_page
from ui.views.skill_assessment import skill_assessment_page, SKILL_ALIASES, LEVEL_TEXT_MAP
from ui.views.organigram import organigram_page
from ui.views.org_hierarchy import org_hierarchy_page
from ui.views.nine_box import nine_box_page


PIPE_STAGES=[("exact","Exact"),("normalized","Norm."),("synonym","Synonym"),("fuzzy","Fuzzy")]


PIPE_ORDER={"exact":0,"normalized":1,"synonym":2,"fuzzy":3}


def _pipe_html(match_type):
    hit=PIPE_ORDER.get(match_type,-1)
    bars=""
    for i,(key,label) in enumerate(PIPE_STAGES):
        if i==hit: bar_bg=STAGE_C.get(key,"#ccc"); nm_col=STAGE_C.get(key,"#ccc")
        elif i<hit: bar_bg="#C7D1D8"; nm_col=C["muted"]
        else:       bar_bg="#EDF0F3"; nm_col="#C7D1D8"
        bars+=(f'<div style="flex:1">'
               f'<div style="height:5px;border-radius:3px;background:{bar_bg}"></div>'
               f'<div style="font-family:{FONT_MONO};font-size:9px;letter-spacing:.05em;'
               f'text-transform:uppercase;color:{nm_col};margin-top:6px;text-align:center">'
               f'{label}</div></div>')
    return f'<div style="display:flex;gap:5px;margin:15px 0 2px">{bars}</div>'


def _safe_stats(catalog) -> dict:
    """Return dashboard statistics with defensive fallbacks."""
    try:
        stats = catalog.repository.statistics()
    except Exception:
        stats = {}

    def _first(*keys, default=0):
        for key in keys:
            value = stats.get(key)
            if value is not None:
                return value
        return default

    return {
        "jobs": _first("jobs", "job_count"),
        "profiles": _first("profiles", "profile_count"),
        "skills": _first("skills", "skill_count", default="—"),
        "salary_bands": _first("salary_bands", "salary_band_count"),
        "title_mappings": _first("title_mappings", "mapping_count"),
        "functions": _first("functions", "function_count"),
    }


def _hero_dashboard_html(stats: dict) -> str:
    """Render the Jobsy V3 product hero and dashboard summary."""
    kpis = [
        ("Jobs", stats.get("jobs", "—"), "Reference roles"),
        ("Profiles", stats.get("profiles", "—"), "Job architecture"),
        ("Skills", stats.get("skills", "—"), "Capability signals"),
        ("Salary Bands", stats.get("salary_bands", "—"), "Market ranges"),
    ]

    kpi_html = ""
    for label, value, note in kpis:
        kpi_html += (
            '<div class="jobsy-v3-kpi-card">'
            f'<div class="jobsy-v3-kpi-label">{label}</div>'
            f'<div class="jobsy-v3-kpi-value">{value}</div>'
            f'<div class="jobsy-v3-kpi-note">{note}</div>'
            '</div>'
        )

    return (
        '<section class="jobsy-v3-hero">'
        '<div class="jobsy-v3-hero-top">'
        '<div>'
        '<div class="jobsy-v3-eyebrow">Workforce intelligence platform</div>'
        f'<h1 class="jobsy-v3-title">{_brand_name()}</h1>'
        '<div class="jobsy-v3-tagline">Jobs, skills &amp; talent strategy made easy.</div>'
        '<p class="jobsy-v3-copy">Standardise jobs • Map skills • Build workforce intelligence</p>'
        '</div>'
        f'<div class="jobsy-v3-badge">{COUNTRY} · V1</div>'
        '</div>'
        '<div class="jobsy-v3-actions">'
        '<a class="jobsy-v3-action primary" href="#workspace">Match Jobs</a>'
        '<a class="jobsy-v3-action secondary" href="#workspace">Upload Workforce Data</a>'
        '</div>'
        f'<div class="jobsy-v3-kpi-grid">{kpi_html}</div>'
        '</section>'
    )


def render_dashboard_intro(catalog) -> None:
    """Render the V3 dashboard intro at the top of the Matching workspace."""
    stats = _safe_stats(catalog)
    st.markdown(_hero_dashboard_html(stats), unsafe_allow_html=True)


def render_getting_started() -> None:
    """A 3-step orientation + page guide for first-time business users."""
    steps = [
        ("1", "Standardise", "Paste or upload job titles below — matched to canonical roles with salary, grade and skills."),
        ("2", "Analyse", "Explore pay & levels (Job Family), pay equity/compa-ratio (Pay Equity), and capability (Skills, Skill Gap, 9-Box)."),
        ("3", "Report", "Generate a board-ready Excel (Architecture Report) and keep the library clean (Data Quality)."),
    ]
    cards = "".join(
        f'<div style="flex:1;min-width:190px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-radius:12px;padding:14px 16px">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
        f'<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;'
        f'border-radius:50%;background:{C["fill_accent"]};color:#fff;font-family:{FONT_MONO};font-size:12px;font-weight:700">{n}</span>'
        f'<span style="font-family:{FONT_SANS};font-weight:700;font-size:14px;color:{C["ink"]}">{t}</span></div>'
        f'<div style="font-size:12.5px;color:{C["muted"]};line-height:1.5">{d}</div></div>'
        for n, t, d in steps)
    st.markdown(
        f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{C["muted"]};margin:6px 0 8px">How it works</div>'
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px">{cards}</div>',
        unsafe_allow_html=True)
    with st.expander("What each page does"):
        st.markdown(
            "- **Matching** — standardise job titles to canonical roles (paste or upload).\n"
            "- **Connect** — pull employees live from AFAS or Workday.\n"
            "- **Job Family** — leveling grid + pay range and total-reward build-up per role.\n"
            "- **Pay Equity** — compa-ratio, range position and gender pay-gap vs the bands.\n"
            "- **Skills Assessment / Skill Gap** — rate people and see gaps to target roles.\n"
            "- **9-Box Grid** — performance × potential talent grid.\n"
            "- **Architecture Report** — board-ready Excel with 10 analytical sheets.\n"
            "- **Data Quality** — live coverage & integrity scorecard for the library.\n"
            "- **Organisation / Organigram** — hierarchy and org-chart views.")


def _resp_html(r):
    """Key responsibilities as a compact inline list."""
    prof = _get_active_catalog().get_complete_job(r.job_id)["profile"] if (
        _get_active_catalog() and r.job_id) else None
    if not prof or not prof.key_responsibilities:
        return (f'<div style="font-size:14px;color:#34424F;margin-top:13px;line-height:1.55">'
                f'{r.description or ""}</div>') if r.description else ""
    items = "".join(
        f'<li style="margin:3px 0;color:#34424F">{item}</li>'
        for item in prof.key_responsibilities[:5]
    )
    desc_part = (f'<div style="font-size:14px;color:#34424F;margin-top:13px;line-height:1.55">'
                 f'{prof.description}</div>') if prof.description else ""
    return (
        desc_part +
        f'<div style="margin-top:12px">'
        f'<div style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.1em;'
        f'text-transform:uppercase;color:{C["muted"]};margin-bottom:6px">Key responsibilities</div>'
        f'<ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.5">{items}</ul></div>'
    )


def _skills_html(r):
    """Profile enrichment: skills, specialisms, management, tools + competency bars."""
    cat = _get_active_catalog()
    if not cat or not r.job_id:
        return ""
    parts = []
    try:
        complete = cat.get_complete_job(r.job_id)
        prof = complete.get("profile") if complete else None
    except Exception:
        prof = None

    # competency requirements from RoleSkillMap
    try:
        role_skills = cat.get_role_skills(r.job_id)
    except Exception:
        role_skills = []

    if role_skills:
        TYPE_COLORS = {"Core":(C["teal"],"1A"),"Adjacent":(C["blue"],"1A"),"Leadership":(C["violet"],"1A")}
        LEVEL_NAMES = {1:"Awareness",2:"Developing",3:"Proficient",4:"Advanced",5:"Expert"}
        bars_by_type = {}
        for req, skill in role_skills:
            t = req.skill_type
            bars_by_type.setdefault(t,[]).append((req,skill))
        skill_html = ""
        for stype in ["Core","Adjacent","Leadership"]:
            items = bars_by_type.get(stype,[])
            if not items:
                continue
            color,_ = TYPE_COLORS.get(stype,(C["muted"],"1A"))
            rows = ""
            for req,skill in items:
                pct = (req.required_level/5)*100
                lname = LEVEL_NAMES.get(req.required_level,"")
                rows += (
                    f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
                    f'<div style="font-family:{FONT_SANS};font-size:12px;color:{C["ink"]};'
                    f'min-width:160px;flex:1">{skill.skill_name}</div>'
                    f'<div style="flex:2;min-width:80px">'
                    f'<div style="height:6px;background:#EDF0F3;border-radius:3px;overflow:hidden">'
                    f'<div style="height:100%;width:{pct:.0f}%;background:{color};border-radius:3px"></div>'
                    f'</div></div>'
                    f'<div style="font-family:{FONT_MONO};font-size:10px;color:{color};'
                    f'min-width:70px;text-align:right">{lname}</div>'
                    f'</div>'
                )
            skill_html += (
                f'<div style="margin-top:12px">'
                f'<div style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.1em;'
                f'text-transform:uppercase;color:{color};margin-bottom:8px">{stype} skills</div>'
                f'{rows}</div>'
            )
        parts.append(skill_html)

    if prof:
        # specialisms
        if prof.specialisms:
            chips = "".join(_chip(s,C["teal"]+"1A",C["teal"]) for s in prof.specialisms[:4])
            parts.append(
                f'<div style="margin-top:12px">'
                f'<div style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.1em;'
                f'text-transform:uppercase;color:{C["muted"]};margin-bottom:5px">Specialisms</div>'
                f'<div style="display:flex;flex-wrap:wrap">{chips}</div></div>'
            )
        # management level
        if prof.management_level and str(prof.management_level).strip():
            parts.append(
                f'<div style="margin-top:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
                f'<span style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.1em;'
                f'text-transform:uppercase;color:{C["muted"]}">Management scope</span>'
                f'{_chip(prof.management_level,C["violet"]+"1A",C["violet"])}</div>'
            )
        # tools
        if prof.typical_tools:
            chips="".join(_chip(t,"#F0F2F4",C["muted"],"10px") for t in prof.typical_tools[:6])
            parts.append(
                f'<div style="margin-top:10px">'
                f'<div style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.1em;'
                f'text-transform:uppercase;color:{C["muted"]};margin-bottom:5px">Tools</div>'
                f'<div style="display:flex;flex-wrap:wrap">{chips}</div></div>'
            )
    return "".join(parts)


LEVEL_ORDER = {"Junior": 1, "Medior": 2, "Senior": 3, "Lead": 4}


LEVEL_NAMES_SHORT = {1: "Awareness", 2: "Developing", 3: "Proficient", 4: "Advanced", 5: "Expert"}


def _career_trajectory_html(r):
    """Auto career path + top skill gaps for this matched role."""
    cat = _get_active_catalog()
    if not cat or not r.job_id:
        return ""
    try:
        career = cat.repository.career_paths.get(r.job_id)
        if not career or not career.next_job_id:
            return (
                f'<div style="margin-top:14px;padding:12px;background:#F4F6F8;'
                f'border-radius:10px;font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">'
                f'This is the top of this career path.</div>'
            )
        next_job = cat.repository.jobs.get(career.next_job_id)
        if not next_job:
            return ""

        # current role skills as baseline
        current_skills = {
            req.skill_id: req.required_level
            for req, _ in cat.get_role_skills(r.job_id)
        }
        gaps = cat.skill_gap(current_skills, career.next_job_id)
        to_develop = [g for g in gaps if g["gap"] > 0][:3]

        # header
        lv_from = LEVEL_ORDER.get(r.level or "", 1)
        lv_to   = LEVEL_ORDER.get(next_job.level, 1)
        html = (
            f'<div style="margin-top:14px;padding:13px 14px;'
            f'background:linear-gradient(135deg,{C["teal"]}0D,{C["blue"]}0A);'
            f'border:1px solid {C["teal"]}33;border-radius:12px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
            f'<div style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["teal"]}">Career trajectory</div>'
            f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]}">'
            f'→ {len(to_develop)} skill{"s" if len(to_develop)!=1 else ""} to develop</div></div>'
            f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
            f'<span style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">{r.standard_title or r.input_title}</span>'
            f'<span style="color:{C["teal"]};font-size:16px">→</span>'
            f'<span style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["teal"]}">{next_job.standard_title}</span>'
            f'</div>'
        )

        if to_develop:
            html += f'<div style="margin-top:10px">'
            for g in to_develop:
                curr_pct = (g["current_level"]/5)*100
                need_pct = (g["required_level"]/5)*100
                html += (
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">'
                    f'<div style="font-family:{FONT_SANS};font-size:11.5px;color:{C["ink"]};flex:1;min-width:120px">{g["skill_name"]}</div>'
                    f'<div style="flex:2;min-width:80px;position:relative;height:6px;'
                    f'background:#E4EAF0;border-radius:3px;overflow:visible">'
                    f'<div style="position:absolute;top:0;bottom:0;left:0;width:{curr_pct:.0f}%;'
                    f'background:#C7D1D8;border-radius:3px"></div>'
                    f'<div style="position:absolute;top:-1px;bottom:-1px;border-radius:3px;'
                    f'left:{curr_pct:.0f}%;width:{need_pct-curr_pct:.0f}%;'
                    f'background:{C["teal"]}44;border:1.5px dashed {C["teal"]}"></div>'
                    f'</div>'
                    f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["teal"]};'
                    f'min-width:60px;text-align:right">{LEVEL_NAMES_SHORT.get(g["required_level"],"")}</div>'
                    f'</div>'
                )
            html += '</div>'
        html += '</div>'
        return html
    except Exception:
        return ""


def _card_html(r):
    t=r.match_type.value
    sc=STAGE_C.get(t,C["clay"])
    shadow="0 1px 3px rgba(23,33,46,.06),0 10px 28px -18px rgba(23,33,46,.4)"

    if not r.matched:
        return (f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-left:4px solid {C["clay"]};border-radius:14px;padding:18px;'
                f'margin-bottom:12px;box-shadow:{shadow}">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
                f'<div>'
                f'<div style="font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">'
                f'INPUT &nbsp;<b style="color:{C["ink"]}">{r.input_title or "(empty)"}</b></div>'
                f'<div style="font-family:{FONT_SERIF};font-size:22px;color:{C["clay"]};margin-top:5px">'
                f'No standard match</div>'
                f'<span style="display:inline-block;font-family:{FONT_MONO};font-size:11px;'
                f'background:#F6E5E3;color:{C["clay"]};border-radius:999px;padding:3px 10px;margin-top:9px">'
                f'No match</span></div>'
                f'<div style="text-align:right"><div style="font-family:{FONT_MONO};font-weight:600;'
                f'font-size:28px;color:{C["clay"]}">—</div>'
                f'<div style="font-family:{FONT_MONO};font-size:9px;color:{C["muted"]};'
                f'text-transform:uppercase;letter-spacing:.1em">conf</div></div></div>'
                f'{_pipe_html("none")}'
                f'<div style="display:flex;align-items:center;gap:8px;margin-top:13px;'
                f'font-size:12.5px;color:{C["clay"]};background:#F6E5E3;border-radius:8px;padding:8px 12px">'
                f'<span style="width:7px;height:7px;border-radius:50%;background:{C["clay"]};'
                f'display:inline-block;flex-shrink:0"></span>'
                f'{"Empty title." if not r.input_title.strip() else "Routed to review — a human picks the role."}'
                f'</div></div>')

    # level chip + L-level designation
    lvl=r.level or ""
    lc_bg,lc_fg=LEVEL_C.get(lvl,("#F4F6F8",C["muted"]))
    lvl_chip=(f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:500;'
              f'background:{lc_bg};color:{lc_fg};border-radius:7px;padding:3px 9px">{lvl}</span>'
              if lvl else "")
    # L1–L4 chip derived from base level
    _cat = _get_active_catalog()
    _lmap = {"Junior":("L1","Starter"),"Medior":("L2","Developing"),
             "Senior":("L3","Senior"),"Lead":("L4","Manager")}
    _lc, _ln = _lmap.get(lvl, ("",""))
    lvl_chip += (f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:600;'
                 f'background:{C["violet"]}1A;color:{C["violet"]};border-radius:7px;'
                 f'padding:3px 9px;margin-left:6px">{_lc} {_ln}</span>' if _lc else "")
    # L5 Rising Star — from 9-box ratings if this employee is Top×High
    _ratings = st.session_state.get("ninebox_ratings", {})
    _emp_name = getattr(r, "employee_name", None) or getattr(r, "name", None)
    if _emp_name and _emp_name in _ratings:
        _perf, _pot = _ratings[_emp_name]
        if _perf == 3 and _pot == 3:
            lvl_chip += (f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:700;'
                         f'background:{C["amber"]}22;color:{C["amber"]};border-radius:7px;'
                         f'padding:3px 9px;margin-left:6px">★ L5 Rising Star</span>')

    # salary bar with P25/P50/P75
    if r.salary_range:
        lo, hi = r.salary_range
        cat = _get_active_catalog()
        _iid = st.session_state.get("industry_id")
        if cat and _iid and hasattr(cat, "industry_adjusted_band"):
            band = cat.industry_adjusted_band(r.function, r.level, _iid)
        else:
            band = cat.repository.salary.get((r.function, r.level)) if cat else None
        MKTLO, MKTHI = 24000, 280000
        def _p(v): return min(100, max(0, (v-MKTLO)/(MKTHI-MKTLO)*100))
        if band and getattr(band,'p25',0) and getattr(band,'p75',0):
            _bg = getattr(band, "grade", 0) or 0
            grade_chip = (f'<span style="font-family:{FONT_MONO};font-size:10px;background:{C["blue"]}1A;'
                f'color:{C["blue"]};border-radius:6px;padding:2px 8px;margin-left:8px">G{_bg}</span>'
                ) if _bg else ""
            sal = (
                f'<div style="margin-top:14px">'
                f'<div style="display:flex;align-items:center;margin-bottom:5px">'
                f'<span style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.08em;'
                f'text-transform:uppercase;color:{C["muted"]}">Salary band · gross / yr</span>'
                f'{grade_chip}</div>'
                f'<div style="font-family:{FONT_MONO};font-size:13px;font-weight:600;color:{C["teal"]};margin-bottom:8px">'
                f'{_euro(lo)} – {_euro(hi)}</div>'
                f'<div style="position:relative;height:10px;background:#EDF0F3;border-radius:5px;overflow:hidden;margin-bottom:5px">'
                f'<div style="position:absolute;left:{_p(lo):.1f}%;width:{_p(hi)-_p(lo):.1f}%;height:100%;background:{C["teal"]}22;border-radius:4px"></div>'
                f'<div style="position:absolute;left:{_p(band.p25):.1f}%;width:{_p(band.p75)-_p(band.p25):.1f}%;height:100%;background:{C["teal"]}55;border-radius:4px"></div>'
                f'<div style="position:absolute;left:{_p(band.p50):.1f}%;width:3px;height:100%;background:{C["teal"]};border-radius:2px"></div>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-between;font-family:{FONT_MONO};font-size:9.5px;color:{C["muted"]}">'
                f'<span>P25 {_euro(band.p25)}</span><span>P50 {_euro(band.p50)}</span><span>P75 {_euro(band.p75)}</span>'
                f'</div></div>'
            )
        else:
            left=max(0,(lo-24000)/(280000-24000))*100
            width=max(2,(hi-lo)/(280000-24000))*100
            sal=(f'<div style="margin-top:14px">'
                 f'<div style="display:flex;justify-content:space-between;align-items:baseline;font-family:{FONT_MONO}">'
                 f'<span style="font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]}">Salary band · gross / yr</span>'
                 f'<span style="font-size:13px;font-weight:600;color:{C["teal"]}">{_euro(lo)} – {_euro(hi)}</span></div>'
                 f'<div style="height:7px;border-radius:4px;background:#F0F2F4;margin-top:7px;position:relative;overflow:hidden">'
                 f'<div style="position:absolute;top:0;bottom:0;background:{C["teal"]};left:{left:.1f}%;width:{width:.1f}%"></div></div></div>')
    else:
        sal=(f'<div style="margin-top:14px;font-family:{FONT_MONO};font-size:12px;color:{C["muted"]}">No salary band defined</div>')

    review=(f'<div style="display:flex;align-items:center;gap:8px;margin-top:13px;'
            f'font-size:12.5px;color:{C["amber"]};background:#F7EEDD;border-radius:8px;padding:8px 12px">'
            f'<span style="width:7px;height:7px;border-radius:50%;background:{C["amber"]};'
            f'display:inline-block;flex-shrink:0"></span>'
            f'Confidence below threshold — flagged for review.</div>'
            if r.requires_review else "")

    tag_bg=sc+"22"; # ~13% opacity hex approximation
    return (
        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-left:4px solid {sc};border-radius:14px;padding:18px;'
        f'margin-bottom:12px;box-shadow:{shadow}">'
        # top row
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">'
        f'<div>'
        f'<div style="font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">'
        f'INPUT &nbsp;<b style="color:{C["ink"]}">{r.input_title}</b></div>'
        f'<div style="font-family:{FONT_SERIF};font-size:22px;color:{C["ink"]};'
        f'letter-spacing:-0.01em;margin-top:5px;line-height:1.2">{r.standard_title}</div>'
        f'<span style="display:inline-block;font-family:{FONT_MONO};font-size:11px;font-weight:500;'
        f'background:{sc}1A;color:{sc};border-radius:999px;padding:3px 10px;margin-top:9px">'
        f'{t.capitalize()} match</span></div>'
        # confidence
        f'<div style="text-align:right;flex-shrink:0">'
        f'<div style="font-family:{FONT_MONO};font-weight:600;font-size:28px;color:{sc}">'
        f'{r.confidence}</div>'
        f'<div style="font-family:{FONT_MONO};font-size:9px;color:{C["muted"]};'
        f'text-transform:uppercase;letter-spacing:.1em">conf</div></div></div>'
        # pipeline
        f'{_pipe_html(t)}'
        # meta pills
        f'<div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:13px">'
        f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["muted"]};'
        f'background:#F4F6F8;border:1px solid {C["line"]};border-radius:7px;padding:3px 9px">'
        f'<b style="color:{C["ink"]}">{r.function}</b> function</span>'
        f'{lvl_chip}'
        f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};'
        f'background:#F4F6F8;border:1px solid {C["line"]};border-radius:7px;padding:3px 9px">'
        f'{r.job_id or ""}</span></div>'
        # responsibilities
        f'{_resp_html(r)}'
        # skills + specialisms + tools row
        f'{_skills_html(r)}'
        f'{_career_trajectory_html(r)}'
        f'{sal}{review}'
        f'</div>'
    )


def _capture_session() -> dict:
    """Serialise current session state to a JSON-safe dict for Supabase storage."""
    import pandas as _pdcs
    keys = ["last_results","last_summary","upload_title_col","upload_name_col",
            "skill_assessments","ninebox_ratings","session_code","org_label"]
    payload = {}
    for k in keys:
        v = st.session_state.get(k)
        if v is None:
            continue
        if isinstance(v, list):
            payload[k] = [r.__dict__ if hasattr(r,"__dict__") else str(r) for r in v]
        elif isinstance(v, _pdcs.DataFrame):
            payload[k] = v.to_dict(orient="records")
        else:
            payload[k] = v
    # Capture upload_df separately (can be large)
    df = st.session_state.get("upload_df")
    if df is not None and isinstance(df, _pdcs.DataFrame):
        payload["upload_df"] = df.to_dict(orient="records")
    return payload


def _restore_session(payload: dict) -> None:
    """Restore session state from a loaded Supabase payload."""
    import pandas as _pdrs
    simple_keys = ["upload_title_col","upload_name_col","skill_assessments",
                   "ninebox_ratings","org_label"]
    for k in simple_keys:
        if k in payload:
            st.session_state[k] = payload[k]
    if "upload_df" in payload:
        try:
            st.session_state["upload_df"] = _pdrs.DataFrame(payload["upload_df"])
        except Exception:
            pass
    # MatchResults can't be fully restored from dict (they're dataclass instances)
    # so we store only the metadata needed for display
    if "last_summary" in payload:
        st.session_state["last_summary"] = payload["last_summary"]


def _assess_import(cols, title_col=None):
    """Read the columns of an uploaded workforce file and report, per Jobsy module,
    what can be delivered now, what will be assumed from partial data, and what data
    the client should add to unlock more. Pure & testable — returns plain data, no UI.

    Returns dict: {found: {field: colname|None}, ready: [...], assumed: [...], unlock: [...]}
    where each list item is (label, detail).
    """
    d = lambda ex, co: _smart_detect(cols, ex, co)
    found = {
        "title": title_col or d(
            {"jobtitle", "job title", "title", "currenttitle", "current title",
             "functie", "functietitel", "role", "position"},
            ["title", "functie", "role", "position", "functi"]),
        "salary": d(
            {"actualsalary", "actual salary", "salary", "base salary", "basesalary",
             "grosssalary", "gross salary", "salaris", "brutosalaris", "loon", "pay"},
            ["sal", "salaris", "loon", "pay", "bruto"]),
        "gender": d({"gender", "geslacht", "sex", "m/v", "m/f"}, ["gender", "geslacht", "sex"]),
        "bonus": d({"bonus", "variable pay", "variable", "incentive", "commission", "bonus/commission"},
                   ["bonus", "incentive", "commission", "variable"]),
        "allowances": d({"allowances", "allowance", "toeslag", "toeslagen", "vergoeding",
                         "13th month", "holiday allowance", "vakantiegeld"},
                        ["allowance", "toeslag", "vergoeding", "vakantiegeld"]),
        "lti": d({"lti", "equity", "long-term incentive", "long term incentive", "rsu",
                  "stock", "aandelen", "options", "share plan"},
                 ["lti", "equity", "rsu", "aandelen"]),
        "name": d({"name", "fullname", "full name", "naam", "employee", "medewerker"}, ["name", "naam"]),
        "empid": d({"employeeid", "employee id", "empid", "id", "personeelsnummer", "medewerkernummer"},
                   ["employeeid", "empid", "personeelsn"]),
        "department": d({"department", "dept", "afdeling", "team", "business unit"},
                        ["department", "afdeling", "dept"]),
        "manager": d({"manager", "linemanager", "line manager", "leidinggevende", "supervisor"},
                     ["manager", "leidinggev", "supervisor"]),
        "fte": d({"fte", "parttime", "part-time", "werkuren", "contract hours"}, ["fte", "parttime"]),
        "performance": d({"performance", "perf", "performance rating", "prestatie"}, ["perform", "prestatie"]),
        "potential": d({"potential", "pot", "potential rating", "potentie"}, ["potential", "potentie"]),
        "skills": d({"skillproficiency", "skill proficiency", "skills", "skill", "competenties",
                     "vaardigheden", "coreskillproficiency", "softskills"},
                    ["proficiency", "skill", "competenti", "vaardighe"]),
    }
    has = {k: bool(v) for k, v in found.items()}
    has["variable"] = has["bonus"] or has["allowances"] or has["lti"]
    has["ninebox"] = has["performance"] and has["potential"]

    ready, assumed, unlock = [], [], []

    # ── What Jobsy can give now ──────────────────────────────────────────
    if has["title"]:
        ready.append(("Title standardisation & job matching",
                      "Every row is matched to a canonical role — the core output."))
        ready.append(("Job Family: levels, grades & salary bands",
                      "Derived from the matched roles — no extra columns needed."))
        ready.append(("Skill-gap & 9-Box rosters",
                      "The matched people load straight into these pages."))
    if has["ninebox"]:
        ready.append(("9-Box grid auto-placed",
                      "Performance + Potential (1-3) drop each person onto the grid — no manual rating."))
    if has["skills"]:
        ready.append(("Skills Assessment & Skill-Gap",
                      "SkillProficiency levels feed the skills pages — no separate skills upload needed."))
    if has["salary"]:
        ready.append(("Pay Equity — compa-ratio vs role band",
                      "Each person's pay ÷ band midpoint, with below-range pay flagged."))
    if has["salary"] and has["gender"]:
        ready.append(("Gender pay-gap breakdown",
                      "Pay Equity splits compa-ratios by gender."))
    if has["salary"] and has["gender"] and has["variable"]:
        ready.append(("Total-pay gender gap (EU Directive basis)",
                      "Bonus/allowances/LTI are added to base for the gap on total pay, not just base."))

    # ── What Jobsy will assume from partial data ─────────────────────────
    if has["salary"] and not has["gender"]:
        assumed.append(("Pay equity runs org-wide, no gender split",
                        "No Gender column — the gender pay-gap view is skipped."))
    if has["salary"] and has["gender"] and not has["variable"]:
        assumed.append(("Gender gap measured on base pay only",
                        "No Bonus/Allowances/LTI — variable-pay gaps aren't captured; the Directive reports on total pay."))
    if has["salary"] and not has["fte"]:
        assumed.append(("Salaries treated as full-time",
                        "No FTE column — part-timers are compared to full bands, not pro-rated."))
    if not has["department"]:
        assumed.append(("Results shown as one flat list",
                        "No Department column — results aren't grouped by team."))
    if not has["name"] and not has["empid"]:
        assumed.append(("Rows identified by position only",
                        "No Name or EmployeeID — results are keyed by row number."))

    # ── What to add to unlock more ───────────────────────────────────────
    if not has["title"]:
        unlock.append(("A job-title column — REQUIRED",
                       "Nothing can be matched without it. Add CurrentTitle."))
    if not has["salary"]:
        unlock.append(("ActualSalary → Pay Equity",
                       "Annual base salary as a number unlocks compa-ratio & below-band flags."))
    if has["salary"] and not has["gender"]:
        unlock.append(("Gender → gender pay-gap analysis",
                       "Add M/F/X to split pay equity by gender."))
    if has["salary"] and not has["variable"]:
        unlock.append(("Bonus / Allowances / LTI → total-pay gap",
                       "Add variable-pay columns to report the gender gap on total pay, per the EU Directive."))
    if has["salary"] and not has["fte"]:
        unlock.append(("FTE → pro-rate part-time pay",
                       "1.0 / 0.8 etc. lets Pay Equity compare part-timers fairly."))
    if not has["department"]:
        unlock.append(("Department → group & filter by team",
                       "Carried through so you can slice every report by department."))
    if not has["manager"]:
        unlock.append(("Manager → org & succession context",
                       "Line-manager names enrich the succession and org views."))
    if not has["ninebox"]:
        unlock.append(("Performance + Potential (1-3) → 9-Box",
                       "Add both ratings to auto-place people on the 9-Box talent grid."))
    if not has["skills"]:
        unlock.append(("SkillProficiency → Skills & Skill-Gap",
                       "Add 'Skill:Level; Skill:Level' per person to unlock skill-gap analysis."))

    return {"found": found, "has": has, "ready": ready, "assumed": assumed, "unlock": unlock}


def _require_sign_in():
    """Named sign-in, replacing the shared password that used to guard this app.

    B2B, invite-only: there is no "create account" here and no OAuth button,
    because accounts are registered by an operator against addresses the client
    has asked for (tools/manage_users.py). See services/auth_service.py.

    The old gate compared `pw != expected` against one password held in secrets.
    Everyone who got in was the same anonymous user, nobody could be revoked
    individually, and the session never expired. All three are A-1 to A-5 in
    docs/PLAN-whitelabel-tenancy.md.
    """
    from services import auth_service

    expiry_msg = auth_service.touch()

    if auth_service.current_user():
        if auth_service.must_change_password():
            _force_password_change()
        return

    from services import branding_service
    st.markdown(f"### 🔒 {branding_service.name()}")
    _logo = branding_service.logo_url()
    if _logo:
        st.image(_logo, width=180)
    if expiry_msg:
        st.info(expiry_msg)

    status = auth_service.status()
    if not status.package_installed or not status.configured:
        st.error(status.reason)
        st.stop()

    st.caption("Sign in with the account your administrator set up for you.")
    with st.form("sign_in", clear_on_submit=False):
        email = st.text_input("Email", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if submitted:
        ok, message = auth_service.sign_in(email, password)
        if ok:
            (getattr(st, "rerun", None) or getattr(st, "experimental_rerun"))()
        st.error(message)

    _support = branding_service.support_email()
    st.caption(f"No account? Accounts are created by your administrator — "
               f"{branding_service.name()} has no self-registration."
               + (f" Contact {_support}." if _support else ""))
    st.stop()


def _force_password_change():
    """The account is still on the password an operator issued by hand.

    That password was delivered out of band -- read down a phone, pasted into a
    message -- so it has existed outside the system at least once. Nothing else
    in the app renders until it is replaced.
    """
    from services import auth_service

    st.markdown("### Choose a password")
    st.caption("Your account was set up with a temporary password. "
               "Pick your own before continuing.")
    with st.form("change_password"):
        pw1 = st.text_input("New password", type="password", autocomplete="new-password")
        pw2 = st.text_input("Repeat it", type="password", autocomplete="new-password")
        submitted = st.form_submit_button("Save password", type="primary", use_container_width=True)
    if submitted:
        ok, message = auth_service.change_password(pw1, pw2)
        if ok:
            st.success(message)
            (getattr(st, "rerun", None) or getattr(st, "experimental_rerun"))()
        st.error(message)
    if st.button("Sign out instead"):
        auth_service.sign_out()
        (getattr(st, "rerun", None) or getattr(st, "experimental_rerun"))()
    st.stop()


def _activity_trail_panel():
    """Who touched this client's data, for the people answerable for it.

    activity_log has been readable by org admins since 0009, but only from a
    shell via `manage_users.py log`. An audit trail an operator can read and a
    client's own admin cannot is a trail that answers to the wrong person.

    Read-only by construction: there is no write policy on the table, and no
    grant behind one, so this cannot become an edit screen by accident.
    """
    from services import auth_service
    if not auth_service.is_admin():
        return
    client = auth_service.db()
    org = auth_service.active_org()
    if client is None or not org:
        return

    with st.expander("🧾 Activity trail", expanded=False):
        st.caption(f"Access to **{org['name']}**'s data. Append-only: nobody can "
                   f"edit or delete these entries, including us.")
        try:
            rows = (client.table("activity_log")
                    .select("at, actor, action, subject")
                    .eq("org_id", org["id"])
                    .order("at", desc=True)
                    .limit(100)
                    .execute()).data or []
        except Exception as exc:
            st.caption(f"The trail could not be read: {exc}")
            return
        if not rows:
            st.caption("Nothing recorded yet.")
            return
        import pandas as _pd
        st.dataframe(_pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _sidebar_account():
    """Who you are, which client you are working on, and the way out."""
    from services import auth_service

    user = auth_service.current_user()
    if not user:
        return
    orgs = auth_service.accessible_orgs()
    active = auth_service.active_org()

    with st.sidebar:
        st.divider()
        st.caption(user["email"])
        if len(orgs) > 1:
            # A consultant works across several clients. Which one is loaded
            # decides which roster is on screen, so it is a deliberate choice
            # rather than something inferred from a URL.
            labels = {o["id"]: f'{o["name"]}  ·  {o["role"].replace("_", " ")}' for o in orgs}
            ids = [o["id"] for o in orgs]
            current = active["id"] if active else ids[0]
            chosen = st.selectbox("Client", ids, index=ids.index(current),
                                  format_func=lambda i: labels[i], key="_org_switcher")
            if chosen != current and auth_service.set_active_org(chosen):
                # Another client's data must not stay on screen after a switch.
                for k in ("last_results", "last_summary", "upload_df", "session_code",
                          "skill_assessments", "ninebox_ratings"):
                    st.session_state.pop(k, None)
                (getattr(st, "rerun", None) or getattr(st, "experimental_rerun"))()
        elif active:
            st.caption(f'{active["name"]} · {active["role"].replace("_", " ")}')

        # Which market's money is on screen. Silent when it is the only live one
        # and its data exists -- a line that never changes is a line nobody reads.
        try:
            from services import country_service
            _ctry = country_service.active_country()
            if len(country_service.live_countries()) > 1:
                st.caption(f"Market: {country_service.name_for(_ctry)} "
                           f"({country_service.currency_for(_ctry)})")
            if not country_service.has_reference_data(_ctry):
                st.warning(f"No salary reference data for "
                           f"{country_service.name_for(_ctry)} yet. Bands and "
                           f"benchmarks will be empty rather than wrong.")
        except Exception:
            pass

        _activity_trail_panel()

        if st.button("Sign out", use_container_width=True):
            auth_service.sign_out()
            (getattr(st, "rerun", None) or getattr(st, "experimental_rerun"))()


def _review_queue(results, catalog) -> None:
    """The return path, on screen: approve a match and it becomes a mapping.

    Everything above this in the Matching page runs one way — a title comes in,
    the pipeline resolves it, somebody reads the low-confidence rows. That
    reading used to end with the session. Here it goes back into the library, so
    the next run resolves the same title at the top of the pipeline instead of
    guessing at the bottom of it again.

    Gated on can_edit() so the interface does not offer a button the write
    policy will refuse — but the policy is still the control, and a refusal is
    printed rather than swallowed.
    """
    import pandas as _pdrq
    from services import auth_service as _auth
    from services import review_service as _rev

    queue = _rev.candidates(results)
    if not queue:
        st.caption("Nothing to review — every title resolved exactly, so a mapping "
                   "would add a row and no information.")
        return

    repo = getattr(catalog, "repository", None)
    if repo is None:
        return

    if not _auth.can_edit():
        st.info(f"{len(queue)} title(s) need a decision. Your role on this client is "
                f"read-only, so the library cannot be taught from here — ask an "
                f"administrator or an analyst.")
        return

    # Ask the database whether this organisation can be written to before
    # offering a button. The answer today is no, for a reason worth reading.
    _ok, _why = _rev.writable_target(_auth.db(), _auth.active_org_id())
    if not _ok:
        st.info(f"{len(queue)} title(s) need a decision, and they cannot be saved yet. {_why}")
        with st.expander("What would happen when they can"):
            st.caption(
                "Each approval becomes a TitleMapping row in the client's own organisation, "
                "written as you, so the next upload resolves that title at the top of the "
                "pipeline instead of guessing at the bottom of it. The plan is shown before "
                "anything is written, a title that is already mapped reads as a remap rather "
                "than an insert, and the library's own audit trail records who decided.")
        return

    # role_id_by_label is what turns a human choice back into a foreign key
    role_labels, role_id_by_label = [], {}
    for job in sorted(repo.jobs.values(), key=lambda j: (j.function or "", j.standard_title or "")):
        label = f"{job.standard_title}  ·  {job.function}/{job.level}"
        role_labels.append(label)
        role_id_by_label[label] = job.job_id
    label_by_id = {v: k for k, v in role_id_by_label.items()}

    st.caption(f"{len(queue)} title(s) the pipeline was unsure about. Approving one writes "
               f"a mapping, so the next upload resolves it deterministically. "
               f"Written as you — the database records who decided.")

    rows = []
    for r in queue:
        rows.append({
            "Approve": False,
            "Input title": r.input_title,
            "Pipeline said": r.standard_title or "— no match —",
            "Conf": r.confidence,
            "Map to role": label_by_id.get(r.job_id, ""),
        })

    edited = st.data_editor(
        _pdrq.DataFrame(rows),
        use_container_width=True, hide_index=True, key="review_queue_editor",
        column_config={
            "Approve": st.column_config.CheckboxColumn("✓", help="Write this mapping", width="small"),
            "Input title": st.column_config.TextColumn(disabled=True),
            "Pipeline said": st.column_config.TextColumn(disabled=True),
            "Conf": st.column_config.NumberColumn(disabled=True, width="small"),
            "Map to role": st.column_config.SelectboxColumn(
                "Map to role", options=role_labels,
                help="The role this title should resolve to from now on"),
        },
    )

    approvals = [
        _rev.Approval(existing_title=str(row["Input title"]),
                      job_id=role_id_by_label.get(str(row["Map to role"]), ""))
        for _, row in edited.iterrows() if bool(row.get("Approve"))
    ]
    if not approvals:
        return

    plan = _rev.plan_write_back(approvals, repo, country=COUNTRY)
    st.caption(f"Plan: {plan.summary()}.")
    for w in plan.writes:
        if w.action == "remap":
            st.caption(f"↻ **{w.existing_title}** currently maps to `{w.was_job_id}` — "
                       f"approving changes it to `{w.job_id}`.")
    for title, why in plan.skipped:
        st.caption(f"— **{title}** skipped: {why}")

    if not plan.writes:
        return

    if st.button(f"Write {len(plan.writes)} mapping(s) to the library", type="primary",
                 key="review_write_back"):
        user = _auth.current_user() or {}
        res = _rev.apply_write_back(_auth.db(), _auth.active_org_id(), plan,
                                    actor=user.get("email", ""), country=COUNTRY)
        if not res.ok:
            st.error(f"Nothing was written. {res.error}")
            return
        _auth.log("library.title_mapping.approved",
                  subject=f"{res.written} mapping(s)",
                  detail={"titles": [w.existing_title for w in plan.writes]})
        # The catalog is cached for the process. Without this the library on
        # screen would still be the one from before the write, and the whole
        # point -- that the next run is different -- would be invisible.
        load_workbook_catalog.clear()
        st.success(f"{res.written} mapping(s) written. The library has changed; "
                   f"re-run the match to see these titles resolve.")
        st.rerun()


def main():
    # F-2. set_page_config runs before sign-in, so on a shared instance this is
    # the neutral default and on a dedicated deployment it is BRAND_NAME from
    # secrets. Once somebody signs in, the hero and the rest follow their
    # partner -- see services/branding_service.py for why the front door cannot.
    from services import branding_service as _brand
    st.set_page_config(page_title=_brand.name(), page_icon="📊",
                       layout="centered", initial_sidebar_state="auto")
    apply_theme()
    _css = _brand.css_overrides()
    if _css:
        st.markdown(_css, unsafe_allow_html=True)
    _require_sign_in()
    _sidebar_account()

    # page navigation
    page = st.sidebar.radio("Navigation", ["Matching", "Connect", "Skills Dashboard", "Skills Assessment", "Skill Gap", "Job Family", "Pay Equity", "Benefits Benchmarking", "9-Box Grid", "Architecture Report", "Data Quality", "Organisation", "Organigram"], label_visibility="collapsed")

    # header moved below catalog loading for dashboard statistics

    # sidebar
    with st.sidebar:
        st.subheader("Matching")
        threshold    = st.slider("Review below confidence", 50, 100, int(DEFAULT_THRESHOLD))
        enable_fuzzy = st.checkbox("Fuzzy stage (RapidFuzz)", value=True)
        st.divider()

    # ── Session persistence ───────────────────────────────────────────
    with st.sidebar:
        st.divider()
        if _ps_available():
            st.markdown(status_card("Database", "ok", badge_label="Online"), unsafe_allow_html=True)
            st.subheader("Session")
            # B-6: the session code no longer travels in the URL, and a session
            # is no longer auto-loaded from one. It used to be that holding a
            # code was sufficient to open a roster, so the code in the address
            # bar was a live key sitting in browser history, bookmarks and
            # referrer headers. Access is now decided by membership (0008), so
            # the code addresses a row rather than unlocking it -- and there is
            # no longer any reason to put it in the URL at all.
            st.query_params.pop("session", None)

            code = st.session_state.get("session_code","")
            if code:
                st.markdown(
                    f'<div style="font-family:monospace;font-size:13px;font-weight:700;'
                    f'background:#E2F1ED;color:#0E7C66;border-radius:8px;padding:8px 12px;'
                    f'text-align:center;letter-spacing:0.08em">{code}</div>',
                    unsafe_allow_html=True,
                )
                st.caption("Share this code to resume on any device.")
                from services import auth_service as _auth
                if not _auth.can_edit():
                    # A viewer reads. 0009's policy refuses the write regardless;
                    # this only avoids offering a button that would fail.
                    st.caption("Read-only access — saving is disabled for your role.")
                elif st.button("💾 Save progress", use_container_width=True):
                    _org = _auth.active_org()
                    ok = _ps_save(code, _capture_session(),
                                  (_org or {}).get("name", ""), (_org or {}).get("id"))
                    st.success("Saved.") if ok else st.error("Save failed.")
            else:
                # The organisation is no longer typed in. It is the client you
                # are signed in against, which is also the one the database will
                # accept a write for -- a free-text label could disagree with
                # both, and used to be the only thing telling two clients apart.
                from services import auth_service as _auth
                _org = _auth.active_org()
                if _org:
                    st.caption(f'New session for **{_org["name"]}**')
                if st.button("▶ Start new session", use_container_width=True, type="primary"):
                    new_code = _ps_generate()
                    st.session_state["session_code"] = new_code
                    st.rerun()

            load_code = st.text_input("Load session code", placeholder="JOBSY-XXXXXXXXXX", key="load_input")
            if st.button("Load →", use_container_width=True) and load_code.strip():
                loaded = _ps_load(load_code.strip())
                if loaded:
                    _restore_session(loaded["payload"])
                    st.session_state["session_code"] = load_code.strip().upper()
                    # A SELECT fires no trigger, so opening somebody's roster is
                    # recorded here or nowhere. This is the read half of D-1.
                    from services import auth_service as _auth
                    _auth.log("session.open", subject=load_code.strip().upper(),
                              org_id=loaded.get("org_id"))
                    st.success(f"Session restored (created {loaded['created_at'][:10]}).")
                    st.rerun()
                else:
                    # Deliberately one message for "no such code" and "not
                    # yours". Telling them apart would turn this box into a way
                    # to probe which codes exist in other clients.
                    st.error("No session with that code is available to you.")
        else:
            _db = _ps_status()
            if _db is None:
                st.markdown(status_card(
                    "Database", "off",
                    "persistence_service.py not found in services/."),
                    unsafe_allow_html=True)
            else:
                if not _db.package_installed:
                    _state, _why = "error", "supabase package missing — add <code>supabase>=2.4.0</code> to requirements.txt and reboot."
                elif not _db.configured:
                    _state, _why = "warn", "SUPABASE_URL / SUPABASE_KEY not found in Streamlit secrets."
                else:
                    _state, _why = "error", _db.reason
                st.markdown(status_card("Database", _state, _why), unsafe_allow_html=True)

        # ── Developer Diagnostics ─────────────────────────────────────────
        with st.expander("🛠 Developer diagnostics"):
            _db = _ps_status()
            if _db is None:
                st.caption("Persistence service not importable.")
            else:
                if st.button("Run health check", use_container_width=True, key="diag_health"):
                    _db = _ps_health()
                _conn_state = "ok" if _db.healthy else ("warn" if _db.available else "error")
                _lat = f"{_db.latency_ms} ms" if _db.latency_ms is not None else "—"
                _tiles = "".join([
                    info_tile("Package", "✓" if _db.package_installed else "✗",
                              color=C["success"] if _db.package_installed else C["danger"]),
                    info_tile("Secrets", "✓" if _db.configured else "✗",
                              color=C["success"] if _db.configured else C["danger"]),
                    info_tile("Client", "✓" if _db.connected else "✗",
                              color=C["success"] if _db.connected else C["danger"]),
                    info_tile("Health", "✓" if _db.healthy else "—",
                              color=C["success"] if _db.healthy else C["subtle"]),
                    info_tile("Latency", _lat, color=C["secondary"]),
                ])
                st.markdown(
                    f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">{_tiles}</div>',
                    unsafe_allow_html=True,
                )
                if _db.last_error:
                    st.caption(f"Last error ({_db.last_error_type}):")
                    st.code(_db.last_error, language=None)

    # load catalog
    path = WORKBOOK_PATH
    catalog = None
    try:
        # The active org is part of the cache key, so one client's library can
        # never be served to another out of a process-wide cache.
        _cat_org = None
        try:
            from core.config import LIBRARY_CLIENT as _lib_client
            if _lib_client == "user":
                from services import auth_service as _auth_cat
                _cat_org = _auth_cat.active_org_id()
        except Exception:
            _cat_org = None
        catalog = load_workbook_catalog(path, _workbook_sig(path), _cat_org)
    except Exception as exc:
        st.error(
            f"Could not load **{path}**. "
            f"Check the file is uploaded to the repo root with that exact name.\n\n`{exc}`"
        )
        st.stop()

    stats = catalog.repository.statistics()
    with st.sidebar:
        st.subheader("Library")
        st.metric("Roles", stats["jobs"])
        st.caption(f"{stats['title_mappings']} mappings · "
                   f"{stats['salary_bands']} salary bands · "
                   f"{stats['functions']} functions")

        # Which source answered. Only interesting once there are two of them,
        # and most interesting in the case nobody would otherwise notice: the
        # database was asked for, was unreachable, and the workbook answered.
        # The app works perfectly in that state, which is exactly the problem.
        _src = getattr(catalog, "active_source", None)
        if getattr(catalog, "fell_back_to_excel", False):
            st.warning("Reading the workbook — the database could not be reached. "
                       "This library may be out of date.", icon="⚠")
        elif _src == "db":
            st.caption("Source: database (governed, versioned)")
        elif _src == "excel":
            st.caption(f"Source: {WORKBOOK_PATH}")

    _set_active_catalog(catalog)

    # Industry context selector (scales salary + adds industry skills)
    _inds = getattr(catalog.repository, "industries", {})
    if _inds:
        with st.sidebar:
            st.subheader("Industry")
            _ind_opts = ["General (NL baseline)"] + [i.name for i in _inds.values()]
            _cur = st.session_state.get("industry_name", "General (NL baseline)")
            _ind_pick = st.selectbox("Sector context", _ind_opts,
                index=_ind_opts.index(_cur) if _cur in _ind_opts else 0,
                label_visibility="collapsed", key="industry_pick")
            st.session_state["industry_name"] = _ind_pick
            if _ind_pick == "General (NL baseline)":
                st.session_state["industry_id"] = None
            else:
                st.session_state["industry_id"] = next(
                    (iid for iid, i in _inds.items() if i.name == _ind_pick), None)
            st.caption("Scales salary bands and adds sector-specific skills.")
    service = MatchingService(catalog, review_threshold=threshold, enable_fuzzy=enable_fuzzy)
    benefits_svc = BenefitsService(catalog)

    if page == "Connect":
        connect_page()
        return

    if page == "Skills Dashboard":
        skills_dashboard_page(catalog)
        return

    if page == "Skills Assessment":
        skill_assessment_page(catalog)
        return

    if page == "Skill Gap":
        skill_gap_page(catalog, service)
        return

    if page == "Job Family":
        job_family_page(catalog)
        return

    if page == "Pay Equity":
        pay_equity_page(catalog, service)
        return

    if page == "Benefits Benchmarking":
        benefits_benchmarking_page(catalog, benefits_svc)
        return

    if page == "Data Quality":
        data_quality_page(catalog)
        return

    if page == "9-Box Grid":
        nine_box_page(catalog)
        return

    if page == "Architecture Report":
        architecture_report_page(catalog)
        return

    if page == "Organisation":
        org_hierarchy_page(catalog)
        return

    if page == "Organigram":
        organigram_page(catalog)
        return

    render_dashboard_intro(catalog)
    render_getting_started()

    # input tabs
    tab_paste, tab_upload = st.tabs(["Paste titles", "Upload file"])
    titles: list[str] = []

    with tab_paste:
        raw = st.text_area(
            "One title per line",
            value="HRBP\nhr business partner\nJunior Developer\nController\nBoekhouder\nSofware Enginer\nUnderwater Basket Weaver",
            height=160, label_visibility="collapsed",
        )
        if st.button("Match titles", type="primary"):
            titles = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    with tab_upload:
        # ── Blank import template (CSV + Excel) ──────────────────────────────
        # One comprehensive workforce file that feeds every Jobsy module:
        #   • CurrentTitle  -> Matching (the only matched field)
        #   • ActualSalary + Gender -> Pay Equity (compa-ratio & pay-gap view)
        #   • EmployeeID/Name + context columns -> carried through to results & exports
        import io as _io
        _TPL_COLS = ["EmployeeID", "Name", "CurrentTitle", "Department", "Manager",
                     "Location", "FTE", "StartDate", "Gender", "ActualSalary",
                     "Bonus", "Allowances", "LTI", "Performance", "Potential", "SkillProficiency"]
        _tpl_df = pd.DataFrame(
            [
                {"EmployeeID": "E1001", "Name": "Alice Johnson",  "CurrentTitle": "HR Business Partner",
                 "Department": "People & Culture", "Manager": "Priya Nair",  "Location": "Amsterdam",
                 "FTE": 1.0, "StartDate": "2021-03-15", "Gender": "F", "ActualSalary": 68000,
                 "Bonus": 6800, "Allowances": 4000, "LTI": 0, "Performance": 3, "Potential": 2,
                 "SkillProficiency": "Performance management:Advanced; Stakeholder management:Proficient"},
                {"EmployeeID": "E1002", "Name": "Bob Smit",       "CurrentTitle": "Financial Controller",
                 "Department": "Finance", "Manager": "Tom de Boer", "Location": "Rotterdam",
                 "FTE": 1.0, "StartDate": "2019-09-01", "Gender": "M", "ActualSalary": 82000,
                 "Bonus": 12000, "Allowances": 4000, "LTI": 15000, "Performance": 2, "Potential": 2,
                 "SkillProficiency": "Budget and resource management:Expert; Project management:Advanced"},
                {"EmployeeID": "E1003", "Name": "Sanne de Vries", "CurrentTitle": "Software Engineer",
                 "Department": "Engineering", "Manager": "Lars Bakker", "Location": "Utrecht",
                 "FTE": 0.8, "StartDate": "2022-06-20", "Gender": "F", "ActualSalary": 71000,
                 "Bonus": 5000, "Allowances": 3000, "LTI": 8000, "Performance": 3, "Potential": 3,
                 "SkillProficiency": "Change management:Proficient; Stakeholder management:Basic"},
            ],
            columns=_TPL_COLS,
        )
        _instr_df = pd.DataFrame(
            [
                {"Column": "EmployeeID", "Required": "Optional", "Used by": "Identifier (carried through)",
                 "Description": "Your own unique ID for the person. Echoed in the results & exports; not used for matching."},
                {"Column": "Name", "Required": "Optional", "Used by": "Identifier (carried through)",
                 "Description": "Person's name, for your reference. Carried through to results; not used for matching."},
                {"Column": "CurrentTitle", "Required": "REQUIRED", "Used by": "Matching",
                 "Description": ("The person's current job title — the ONLY field that gets matched. Use the real, full "
                                 "title (e.g. 'Senior HR Advisor', not 'SR HRA' or an ID code). One title per row. English "
                                 "or Dutch both work. The engine matches exact -> normalised -> synonyms -> fuzzy against "
                                 "the reference library, so clean, standard titles get the highest-confidence matches.")},
                {"Column": "Department", "Required": "Optional", "Used by": "Context (carried through)",
                 "Description": "Team / department, e.g. 'Finance'. Carried through for your own grouping & filtering of results."},
                {"Column": "Manager", "Required": "Optional", "Used by": "Context (carried through)",
                 "Description": "Line manager's name. Carried through to results; useful for succession & org views."},
                {"Column": "Location", "Required": "Optional", "Used by": "Context (carried through)",
                 "Description": "Office / city / country. Carried through for filtering; not used for matching."},
                {"Column": "FTE", "Required": "Optional", "Used by": "Context (carried through)",
                 "Description": "Full-time equivalent as a number: 1.0 = full-time, 0.8 = 4 days/week. Carried through."},
                {"Column": "StartDate", "Required": "Optional", "Used by": "Context (carried through)",
                 "Description": "Hire date in YYYY-MM-DD, e.g. 2022-06-20. Carried through (tenure context); not matched."},
                {"Column": "Gender", "Required": "Recommended", "Used by": "Pay Equity",
                 "Description": "M, F or X. Powers the gender pay-gap view on the Pay Equity page. Leave blank if not analysing pay."},
                {"Column": "ActualSalary", "Required": "Recommended", "Used by": "Pay Equity",
                 "Description": ("Actual annual BASE salary as a plain number (no currency symbol or thousands separator), "
                                 "e.g. 68000. Drives each person's compa-ratio (base / band midpoint) on the Pay Equity page. "
                                 "Leave blank if you're only standardising titles.")},
                {"Column": "Bonus", "Required": "Optional", "Used by": "Pay Equity",
                 "Description": ("Actual annual variable/incentive cash paid (bonus, commission) as a plain number. Added to "
                                 "base + allowances for the total-pay gender gap — the basis the EU Pay Transparency "
                                 "Directive reports on. Leave blank/0 if none.")},
                {"Column": "Allowances", "Required": "Optional", "Used by": "Pay Equity",
                 "Description": ("Fixed annual cash allowances as a plain number (holiday allowance, 13th month, car/travel "
                                 "allowance). Counted in total cash pay. Leave blank/0 if none.")},
                {"Column": "LTI", "Required": "Optional", "Used by": "Pay Equity",
                 "Description": ("Annualised value of long-term incentives / equity granted (RSUs, options, share plan) as a "
                                 "plain number. Counted in total pay on top of cash. Leave blank/0 if none.")},
                {"Column": "Performance", "Required": "Optional", "Used by": "9-Box Grid",
                 "Description": ("Performance rating 1-3 (1 = low, 2 = effective, 3 = top). Seeds each person's spot on the "
                                 "9-Box grid automatically. Leave blank if you're not using the 9-Box.")},
                {"Column": "Potential", "Required": "Optional", "Used by": "9-Box Grid",
                 "Description": ("Potential rating 1-3 (1 = limited, 2 = growth, 3 = high). Pairs with Performance to place "
                                 "people on the 9-Box grid. Leave blank if unused.")},
                {"Column": "SkillProficiency", "Required": "Optional", "Used by": "Skills Assessment",
                 "Description": ("Optional skills for one person in a single cell, as 'Skill:Level; Skill:Level' — e.g. "
                                 "'Project management:Advanced; Budgeting:Expert'. Levels: Basic/Proficient/Advanced/Expert. "
                                 "Feeds the Skills Assessment & Skill-Gap pages. For a guided grid with one column per skill "
                                 "and a 1-5 rubric, use the dedicated Skills Assessment template instead.")},
            ],
            columns=["Column", "Required", "Used by", "Description"],
        )
        _tips_df = pd.DataFrame(
            {"Tips for best matches": [
                "CurrentTitle is the only required field — everything else is optional context or feeds other pages.",
                "Fill CurrentTitle with a genuine job title — not a code, grade, or number.",
                "One person per row; replace the example rows with your own data.",
                "Add ActualSalary + Gender to unlock the Pay Equity page from this same file — no second upload needed.",
                "Add Bonus / Allowances / LTI to see the gender gap on TOTAL pay (base + variable), not just base — the EU Directive basis.",
                "Spelling wobbles are fine (fuzzy matching handles them), but cleaner titles score higher.",
                f"Keep these exact headers so {_brand_name()} auto-detects each column; extra columns you add are preserved too.",
                f"ActualSalary must be a plain number (68000, not '{_money(68000)}' or '68k'). FTE as 1.0 / 0.8. Dates as YYYY-MM-DD.",
                "Add Performance + Potential (1-3) to auto-place people on the 9-Box grid — no re-entry needed.",
                "Put skills in one cell as 'Skill:Level; Skill:Level' under SkillProficiency, or use the dedicated Skills template for a per-skill grid.",
                "Both .csv and .xlsx upload fine.",
            ]}
        )
        st.markdown("**New here?** Download the template, fill in **CurrentTitle** (add salary/gender for Pay Equity), then upload below.")
        _tc1, _tc2 = st.columns(2)
        with _tc1:
            _logged_download(
                "⬇ Import template (.csv)",
                _tpl_df.to_csv(index=False).encode("utf-8"),
                file_name="jobsy_import_template.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with _tc2:
            _xbuf = _io.BytesIO()
            with pd.ExcelWriter(_xbuf, engine="openpyxl") as _xl:
                _tpl_df.to_excel(_xl, index=False, sheet_name="Workforce")
                _instr_df.to_excel(_xl, index=False, sheet_name="Instructions")
                _tips_df.to_excel(_xl, index=False, sheet_name="Match tips")
            _logged_download(
                "⬇ Import template (.xlsx)",
                _xbuf.getvalue(),
                file_name="jobsy_import_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        st.caption("Only **CurrentTitle** is required for matching. **ActualSalary** + **Gender** feed the Pay Equity page from "
                   "this same file; all other columns are optional context, carried through to your results & exports.")

        st.markdown("")
        upload = st.file_uploader("Upload CSV or Excel (.csv, .xls, .xlsx)",
                                   type=["csv","xls","xlsx"],
                                   key="matching_file_upload")
        if upload:
            try:
                if upload.name.endswith(".csv"):
                    df_in = pd.read_csv(upload)
                else:
                    df_in = pd.read_excel(upload)
            except Exception as read_err:
                st.error(f"Could not read file: {read_err}")
                df_in = None

            if df_in is not None and not df_in.empty:
                col_opts = list(df_in.columns)
                # Auto-detect title and name columns
                auto_title = _smart_detect(
                    col_opts,
                    {"jobtitle","job_title","job title","title","currenttitle","current_title",
                     "current title","functie","functietitel","functieomschrijving","function",
                     "position","role","jobrole","job_role"},
                    ["title","functie","job role","jobrole","role","position", "functi"],
                ) or col_opts[0]
                col = st.selectbox("Column with job titles", col_opts,
                                   index=col_opts.index(auto_title))
                name_opts = ["— none —"] + col_opts
                auto_name = _smart_detect(
                    col_opts,
                    {"name","fullname","full_name","full name","naam","volledige naam",
                     "firstname","first_name","employeename","employee_name","medewerker"},
                    ["full name","fullname","naam","medewerker","name"],
                ) or "— none —"
                name_col = st.selectbox("Name column (optional)", name_opts,
                                        index=name_opts.index(auto_name) if auto_name in name_opts else 0)
                st.caption(f"{len(df_in)} rows · {len(col_opts)} columns detected")

                # ── Data-readiness panel: what this file unlocks, assumes, and needs ──
                _rep = _assess_import(col_opts, title_col=col)
                _sections = [
                    (f"✅ {_brand_name()} can give you now", C["success"], _rep["ready"]),
                    ("◐ Assumed from partial data", C["amber"], _rep["assumed"]),
                    ("➕ Add to unlock more", C["accent"], _rep["unlock"]),
                ]
                with st.expander(
                    f"📋 What {_brand_name()} can do with this file — "
                    f"{len(_rep['ready'])} ready · {len(_rep['assumed'])} assumed · "
                    f"{len(_rep['unlock'])} to unlock",
                    expanded=True,
                ):
                    _cols3 = st.columns(3)
                    for _cix, (_head, _clr, _items) in enumerate(_sections):
                        with _cols3[_cix]:
                            _rows = "".join(
                                f'<div style="margin:0 0 10px 0">'
                                f'<div style="font-size:13px;font-weight:600;color:{C["ink"]}">{_lbl}</div>'
                                f'<div style="font-size:12px;color:{C["muted"]};line-height:1.4">{_det}</div>'
                                f'</div>'
                                for _lbl, _det in _items
                            ) or f'<div style="font-size:12px;color:{C["muted"]}">— nothing here —</div>'
                            st.markdown(
                                f'<div style="border-top:3px solid {_clr};background:{C["surface"]};'
                                f'border:1px solid {C["line"]};border-top:3px solid {_clr};'
                                f'border-radius:10px;padding:12px 14px;height:100%">'
                                f'<div style="font-size:12px;font-weight:700;letter-spacing:.02em;'
                                f'color:{_clr};margin-bottom:10px">{_head}</div>{_rows}</div>',
                                unsafe_allow_html=True,
                            )
                    st.caption("This updates automatically from your column headers — a partly-filled "
                               "template still works; you just get fewer analyses until you add the missing fields.")

                # Guard the common failure: an ID/number column selected instead of titles.
                _sample = df_in[col].dropna().astype(str).str.strip().head(25)
                if len(_sample) and _sample.str.fullmatch(r"\d+(\.\d+)?").mean() > 0.7:
                    st.warning(
                        f"Column **{col}** looks like numbers/IDs, not job titles — "
                        "pick the column that holds the job titles above, or matching will return no results."
                    )
                if st.button("Match column", type="primary", use_container_width=True):
                    titles = df_in[col].fillna("").astype(str).tolist()
                    nm = name_col if name_col != "— none —" else None
                    st.session_state["upload_df"]        = df_in
                    st.session_state["upload_title_col"] = col
                    st.session_state["upload_name_col"]  = nm
            elif df_in is not None:
                st.warning("The file appears to be empty.")

    if not titles:
        # auto-restore from session state if results already exist
        if st.session_state.get("last_results"):
            results = st.session_state["last_results"]
            summary = st.session_state.get("last_summary") or service.summarize(results)
            st.caption("↩ Showing previous results — upload new titles to refresh.")
        else:
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-radius:12px;padding:20px;color:{C["muted"]};font-size:14px;'
                f'text-align:center;margin-top:4px">'
                f'Add some titles and tap <b>Match titles</b> to see results.</div>',
                unsafe_allow_html=True,
            )
            return

    # run matching (only if new titles were submitted)
    if titles:
        results = service.match_titles(titles)
        summary = service.summarize(results)
    # persist for Organisation page
    st.session_state["last_results"] = results
    st.session_state["last_summary"] = summary
    if "upload_df" not in st.session_state:
        st.session_state["upload_df"] = None
        st.session_state["upload_name_col"] = None

    # stat row
    st.markdown(
        f'<div style="display:flex;gap:10px;margin:18px 0">'
        f'{_stat_card(summary.total, "Total")}'
        f'{_stat_card(summary.matched, "Matched", C["teal"])}'
        f'{_stat_card(summary.review, "Review", C["amber"])}'
        f'{_stat_card(summary.unmatched, "Unmatched", C["clay"])}'
        f'{_stat_card(f"{summary.avg_confidence:.0f}%", "Avg conf")}'
        f'</div>',
        unsafe_allow_html=True,
    )

    only_review = st.checkbox("Show only titles needing review")
    shown = [r for r in results if r.requires_review] if only_review else results

    # The return path. Everything else on this page runs one way.
    with st.expander("Review queue — teach the library", expanded=False):
        _review_queue(results, catalog)

    # Pagination — show PAGE_SIZE cards at a time to keep mobile responsive
    PAGE_SIZE = 25
    total_shown = len(shown)
    if "results_page" not in st.session_state:
        st.session_state["results_page"] = 0
    page = st.session_state["results_page"]
    total_pages = max(1, (total_shown + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages - 1)

    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, total_shown)
    page_items = shown[start:end]

    if total_shown > PAGE_SIZE:
        col_prev, col_info, col_next = st.columns([1,2,1])
        with col_prev:
            if st.button("← Prev", disabled=page==0):
                st.session_state["results_page"] = page - 1
                st.rerun()
        with col_info:
            st.markdown(
                f'<div style="text-align:center;font-family:{FONT_MONO};font-size:11px;'
                f'color:{C["muted"]};padding-top:8px">'
                f'Showing {start+1}–{end} of {total_shown}</div>',
                unsafe_allow_html=True,
            )
        with col_next:
            if st.button("Next →", disabled=page>=total_pages-1):
                st.session_state["results_page"] = page + 1
                st.rerun()

    st.markdown(
        "".join(_card_html(r) for r in page_items),
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    col_dl, col_reset = st.columns([3,1])
    with col_dl:
        _logged_download(
            "⬇  Download results (.xlsx)",
            data=ExportService().to_workbook_bytes(results, summary),
            file_name="jobsy_matches.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col_reset:
        if st.button("Clear results"):
            for k in ["last_results","last_summary","upload_df","upload_title_col","upload_name_col","results_page"]:
                st.session_state.pop(k, None)
            st.rerun()


if __name__ == "__main__":
    main()


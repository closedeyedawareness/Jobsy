"""
jobsy/ui/app.py  —  Streamlit front end for Jobsy V1
Run with:  streamlit run jobsy/ui/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

try:
    from core.config import COUNTRY, DEFAULT_THRESHOLD, WORKBOOK_PATH
except ImportError:
    COUNTRY, DEFAULT_THRESHOLD, WORKBOOK_PATH = "NL", 85, "reference_library.xlsx"

from core.repository import Repository
from services.export_service import ExportService
from services.matching_service import MatchingService

# ── colours (mirrored in .streamlit/config.toml) ──────────────────────────
C = {
    "bg":      "#ECEEF0",
    "surface": "#FFFFFF",
    "ink":     "#17212E",
    "muted":   "#5E6E7C",
    "line":    "#D9E0E5",
    "teal":    "#0E7C66",
    "teal2":   "#12A085",
    "blue":    "#2B5FA6",
    "violet":  "#6A53B0",
    "amber":   "#B9791A",
    "clay":    "#A8443A",
}
STAGE_C = {"exact":C["teal"],"normalized":C["blue"],"synonym":C["violet"],"fuzzy":C["amber"],"none":C["clay"]}
LEVEL_C = {"Junior":("#E8F4FF",C["blue"]),"Medior":("#E2F1ED",C["teal"]),"Senior":("#ECE7F7",C["violet"]),"Lead":("#F7EEDD",C["amber"])}
GMIN,GMAX = 30000,140000

# ── font loader (link only — no <style> block) ─────────────────────────────
def load_fonts():
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&'
        'family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )

FONT_SERIF = "'Fraunces', Georgia, serif"
FONT_SANS  = "'IBM Plex Sans', system-ui, sans-serif"
FONT_MONO  = "'IBM Plex Mono', 'Courier New', monospace"

# ── sample catalog ─────────────────────────────────────────────────────────
class _SampleCatalog:
    def __init__(self):
        self.repository = Repository(self._sheets(), validate=False)

    def get_complete_job(self, job_id):
        job = self.repository.jobs.get(job_id)
        if not job: return None
        return {"job":job,"profile":self.repository.profiles.get(job_id),
                "salary":self.repository.salary.get((job.function,job.level)),
                "next_role":self.repository.career_paths.get(job_id)}

    @staticmethod
    def _sheets():
        jobs=[("J-HRA","HR Advisor","HR","Medior"),("J-HRBP","HR Business Partner","HR","Senior"),
              ("J-REC","Recruiter","HR","Medior"),("J-ACC","Accountant","Finance","Medior"),
              ("J-FC","Financial Controller","Finance","Senior"),
              ("J-JSE","Junior Software Engineer","Engineering","Junior"),
              ("J-SE","Software Engineer","Engineering","Medior"),
              ("J-SSE","Senior Software Engineer","Engineering","Senior"),
              ("J-DA","Data Analyst","Data","Medior"),("J-PM","Product Manager","Product","Senior")]
        profiles={"J-HRA":"Advises managers on policy, Dutch labour law, and casework.",
                  "J-HRBP":"Partners with senior leaders on workforce planning and people strategy.",
                  "J-REC":"Runs hiring end-to-end: sourcing, screening, interviewing, and offer.",
                  "J-ACC":"Maintains the ledger and prepares statutory, audit-ready accounts.",
                  "J-FC":"Owns the close, financial reporting, and the internal control framework.",
                  "J-JSE":"Ships well-scoped features with guidance from senior engineers.",
                  "J-SE":"Designs and builds features across the stack with little supervision.",
                  "J-SSE":"Leads technical design on complex systems and mentors engineers.",
                  "J-DA":"Turns raw data into dashboards and insight that inform decisions.",
                  "J-PM":"Defines product direction and aligns delivery with user needs."}
        salary=[("HR","Medior",42000,58000),("HR","Senior",60000,82000),
                ("Finance","Medior",45000,62000),("Finance","Senior",70000,95000),
                ("Engineering","Junior",42000,56000),("Engineering","Medior",55000,75000),
                ("Engineering","Senior",78000,105000),("Data","Medior",50000,68000),
                ("Product","Senior",75000,100000)]
        mapping=[("HRBP","J-HRBP"),("People Partner","J-HRBP"),("HR Manager","J-HRBP"),
                 ("HR Officer","J-HRA"),("Corporate Recruiter","J-REC"),
                 ("Talent Acquisition Specialist","J-REC"),
                 ("Controller","J-FC"),("Business Controller","J-FC"),
                 ("Boekhouder","J-ACC"),("Bookkeeper","J-ACC"),
                 ("Developer","J-SE"),("Software Developer","J-SE"),
                 ("Junior Developer","J-JSE"),("BI Analyst","J-DA"),
                 ("Productmanager","J-PM"),("Product Owner","J-PM")]
        return {"jobs":pd.DataFrame(jobs,columns=["JobID","StandardTitle","Function","Level"]),
                "profiles":pd.DataFrame([{"JobID":k,"Description":v} for k,v in profiles.items()]),
                "titles":pd.DataFrame(mapping,columns=["ExistingTitle","JobID"]),
                "salary":pd.DataFrame(salary,columns=["Function","Level","Min","Max"]),
                "career":pd.DataFrame([{"JobID":j[0]} for j in jobs]),
                "levels":pd.DataFrame([{"Level":x} for x in ("Junior","Medior","Senior","Lead")]),
                "employees":pd.DataFrame([{"EmployeeID":"1","Name":"-","CurrentTitle":"-"}])}

# ── loaders ────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading reference library…")
def load_workbook_catalog(path):
    from core.catalog import Catalog
    c=Catalog(path); c.load(); return c

@st.cache_resource(show_spinner="Building sample catalog…")
def load_sample_catalog():
    return _SampleCatalog()

# ── inline-style helpers ───────────────────────────────────────────────────
def _euro(n): return "€{:,.0f}".format(n).replace(",",".")

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


def _chip(text, bg, fg, size="11px"):
    return (f'<span style="display:inline-block;font-family:{FONT_MONO};font-size:{size};'
            f'font-weight:500;background:{bg};color:{fg};border-radius:7px;'
            f'padding:3px 9px;margin:2px 3px 2px 0">{text}</span>')

def _get_profile(r):
    """Pull profile from the MatchResult's catalog enrichment, if loaded."""
    try:
        from core.repository import Repository  # noqa
        cat = _get_active_catalog()
        if cat and r.job_id:
            complete = cat.get_complete_job(r.job_id)
            return complete.get("profile") if complete else None
    except Exception:
        pass
    return None

_active_catalog = None
def _set_active_catalog(cat): global _active_catalog; _active_catalog = cat
def _get_active_catalog(): return _active_catalog

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

    # level chip
    lvl=r.level or ""
    lc_bg,lc_fg=LEVEL_C.get(lvl,("#F4F6F8",C["muted"]))
    lvl_chip=(f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:500;'
              f'background:{lc_bg};color:{lc_fg};border-radius:7px;padding:3px 9px">{lvl}</span>'
              if lvl else "")

    # salary bar
    if r.salary_range:
        lo,hi=r.salary_range
        left=max(0,(lo-GMIN)/(GMAX-GMIN))*100
        width=max(2,(hi-lo)/(GMAX-GMIN))*100
        sal=(f'<div style="margin-top:14px">'
             f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
             f'font-family:{FONT_MONO}">'
             f'<span style="font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]}">'
             f'Salary band · gross / yr</span>'
             f'<span style="font-size:13px;font-weight:600;color:{C["teal"]}">'
             f'{_euro(lo)} – {_euro(hi)}</span></div>'
             f'<div style="height:7px;border-radius:4px;background:#F0F2F4;border:1px solid #DDE2E7;'
             f'margin-top:7px;position:relative;overflow:hidden">'
             f'<div style="position:absolute;top:0;bottom:0;border-radius:4px;'
             f'background:linear-gradient(90deg,{C["teal2"]},{C["teal"]});'
             f'left:{left:.1f}%;width:{width:.1f}%"></div></div></div>')
    else:
        sal=(f'<div style="margin-top:14px;font-family:{FONT_MONO};font-size:12px;color:{C["muted"]}">'
             f'No salary band defined</div>')

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

def _stat_card(value, label, color=C["ink"]):
    return (f'<div style="flex:1;background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:14px;padding:14px 10px;text-align:center;'
            f'box-shadow:0 1px 2px rgba(23,33,46,.04),0 8px 24px -16px rgba(23,33,46,.28)">'
            f'<div style="font-family:{FONT_MONO};font-weight:600;font-size:26px;'
            f'line-height:1;color:{color}">{value}</div>'
            f'<div style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["muted"]};margin-top:5px">{label}</div>'
            f'</div>')

# ── main ───────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Jobsy", page_icon="📊",
                       layout="centered", initial_sidebar_state="expanded")
    load_fonts()

    # page navigation
    page = st.sidebar.radio("", ["Matching", "Skill Gap", "Organisation", "Organigram"], label_visibility="collapsed")

    # header
    st.markdown(
        f'<div style="padding:8px 0 20px">'
        f'<span style="font-family:{FONT_SERIF};font-weight:700;font-size:44px;'
        f'letter-spacing:-0.03em;line-height:1;color:{C["ink"]}">Jobsy</span>'
        f'<span style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.18em;'
        f'text-transform:uppercase;color:{C["teal"]};border:1px solid {C["teal"]}33;'
        f'background:{C["teal"]}14;border-radius:999px;padding:4px 12px;'
        f'vertical-align:middle;margin-left:10px">{COUNTRY} · V1</span></div>'
        f'<p style="color:{C["muted"]};font-size:15.5px;margin:0 0 20px;'
        f'max-width:58ch;line-height:1.55">'
        f'Resolve messy job titles to <b style="color:{C["ink"]}">standard roles</b>, '
        f'<b style="color:{C["ink"]}">profiles</b>, and '
        f'<b style="color:{C["ink"]}">salary ranges</b>.</p>',
        unsafe_allow_html=True,
    )

    # sidebar
    with st.sidebar:
        st.subheader("Data source")
        source = st.radio("", ["Built-in sample", "Reference workbook"],
                          label_visibility="collapsed")
        path = WORKBOOK_PATH
        if source == "Reference workbook":
            path = st.text_input("Workbook path", value=WORKBOOK_PATH)
        st.divider()
        st.subheader("Matching")
        threshold    = st.slider("Review below confidence", 50, 100, int(DEFAULT_THRESHOLD))
        enable_fuzzy = st.checkbox("Fuzzy stage (RapidFuzz)", value=True)
        st.divider()

    # load catalog
    try:
        catalog = load_sample_catalog() if source == "Built-in sample" else load_workbook_catalog(path)
    except Exception as exc:
        st.error(f"Could not load catalog: {exc}"); st.stop()

    stats = catalog.repository.statistics()
    with st.sidebar:
        st.subheader("Library")
        st.metric("Roles", stats["jobs"])
        st.caption(f"{stats['title_mappings']} mappings · "
                   f"{stats['salary_bands']} salary bands · "
                   f"{stats['functions']} functions")

    _set_active_catalog(catalog)
    service = MatchingService(catalog, review_threshold=threshold, enable_fuzzy=enable_fuzzy)

    if page == "Skill Gap":
        skill_gap_page(catalog, service)
        return

    if page == "Organisation":
        org_hierarchy_page(catalog)
        return

    if page == "Organigram":
        organigram_page(catalog)
        return

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
        upload = st.file_uploader("CSV or Excel of titles", type=["csv","xlsx"])
        if upload:
            df_in = pd.read_csv(upload) if upload.name.endswith(".csv") else pd.read_excel(upload)
            col_opts = list(df_in.columns)
            col = st.selectbox("Column with titles", col_opts)
            name_col = st.selectbox("Name column (optional)", ["— none —"] + col_opts)
            if st.button("Match column", type="primary"):
                titles = df_in[col].fillna("").astype(str).tolist()
                nm = name_col if name_col != "— none —" else None
                st.session_state["upload_df"] = df_in
                st.session_state["upload_title_col"] = col
                st.session_state["upload_name_col"] = nm

    if not titles:
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:12px;padding:20px;color:{C["muted"]};font-size:14px;'
            f'text-align:center;margin-top:4px">'
            f'Add some titles and tap <b>Match titles</b> to see results.</div>',
            unsafe_allow_html=True,
        )
        return

    # run matching
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

    # cards
    st.markdown(
        "".join(_card_html(r) for r in shown),
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.download_button(
        "⬇  Download results (.xlsx)",
        data=ExportService().to_workbook_bytes(results, summary),
        file_name="jobsy_matches.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def skill_gap_page(catalog, service):
    """Render the Skill Gap Analysis page."""
    LEVEL_NAMES = {0:"None",1:"Awareness",2:"Developing",3:"Proficient",4:"Advanced",5:"Expert"}
    TYPE_COLORS = {"Core":C["teal"],"Adjacent":C["blue"],"Leadership":C["violet"]}

    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Skill Gap Analysis</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:20px">'
        f'Select a current role and a target role to see the skills gap and development priorities.</p>',
        unsafe_allow_html=True,
    )

    all_jobs = sorted(catalog.repository.jobs.values(), key=lambda j: (j.function, j.standard_title))
    job_options = {f"{j.standard_title} ({j.function} · {j.level})": j.job_id for j in all_jobs}

    col1, col2 = st.columns(2)
    with col1:
        from_label = st.selectbox("Current role", list(job_options.keys()), key="gap_from")
    with col2:
        to_label = st.selectbox("Target role", list(job_options.keys()), key="gap_to",
                                index=min(1, len(job_options)-1))

    from_id = job_options[from_label]
    to_id   = job_options[to_label]

    if from_id == to_id:
        st.info("Select a different target role to see the gap.")
        return

    # Use the FROM role skills as baseline
    from_skills_raw = catalog.get_role_skills(from_id)
    current = {req.skill_id: req.required_level for req,_ in from_skills_raw}

    try:
        gaps = catalog.skill_gap(current, to_id)
    except Exception as exc:
        st.error(f"Could not compute gap: {exc}"); return

    needs_dev = [g for g in gaps if g["gap"] > 0]
    matches   = [g for g in gaps if g["gap"] == 0]
    exceeds   = [g for g in gaps if g["gap"] < 0]

    # summary
    st.markdown(
        f'<div style="display:flex;gap:10px;margin:16px 0">'
        f'{_stat_card(len(needs_dev),"Develop",C["amber"])}'
        f'{_stat_card(len(matches),"Ready",C["teal"])}'
        f'{_stat_card(len(exceeds),"Exceeds","#6A53B0")}',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    def gap_card(g):
        color = C["amber"] if g["gap"]>0 else (C["teal"] if g["gap"]==0 else C["violet"])
        label = f"+{g['gap']} level{'s' if g['gap']!=1 else ''}" if g["gap"]>0 else (
                "Ready" if g["gap"]==0 else f"Exceeds by {abs(g['gap'])}")
        from_bar = (g["current_level"]/5)*100
        to_bar   = (g["required_level"]/5)*100
        return (
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-left:4px solid {color};border-radius:12px;padding:14px 16px;margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
            f'<div>'
            f'<div style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">'
            f'{g["skill_name"]}</div>'
            f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};margin-top:2px">'
            f'{g["category"]} · {g["skill_type"]}</div></div>'
            f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:600;'
            f'background:{color}1A;color:{color};border-radius:999px;padding:3px 10px">{label}</span></div>'
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};min-width:60px">'
            f'Now: {LEVEL_NAMES.get(g["current_level"],"None")}</div>'
            f'<div style="flex:1;position:relative;height:8px;background:#EDF0F3;border-radius:4px;overflow:visible">'
            f'<div style="position:absolute;top:0;bottom:0;left:0;width:{from_bar:.0f}%;'
            f'background:#C7D1D8;border-radius:4px"></div>'
            f'<div style="position:absolute;top:-1px;bottom:-1px;left:0;width:{to_bar:.0f}%;'
            f'background:{color}33;border-radius:4px;border:1.5px dashed {color}"></div>'
            f'</div>'
            f'<div style="font-family:{FONT_MONO};font-size:10px;color:{color};min-width:70px;text-align:right">'
            f'Need: {LEVEL_NAMES.get(g["required_level"],"")}</div></div></div>'
        )

    if needs_dev:
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["amber"]};margin:16px 0 8px">'
            f'Skills to develop ({len(needs_dev)})</div>',
            unsafe_allow_html=True,
        )
        st.markdown("".join(gap_card(g) for g in needs_dev), unsafe_allow_html=True)

    if matches:
        with st.expander(f"Already proficient ({len(matches)})"):
            st.markdown("".join(gap_card(g) for g in matches), unsafe_allow_html=True)

    if exceeds:
        with st.expander(f"Exceeds requirement ({len(exceeds)})"):
            st.markdown("".join(gap_card(g) for g in exceeds), unsafe_allow_html=True)

    # export gap report
    import io
    import pandas as pd
    gap_df = pd.DataFrame(gaps)
    gap_df["from_role"] = from_label
    gap_df["to_role"]   = to_label
    buf = io.BytesIO()
    gap_df.to_excel(buf, index=False)
    st.download_button(
        "⬇  Download gap report (.xlsx)",
        data=buf.getvalue(),
        file_name=f"skill_gap_{from_id}_to_{to_id}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )



def org_hierarchy_page(catalog):
    """Render the automatic organisation hierarchy from matched results."""
    LEVEL_ORDER_MAP  = {"Junior": 1, "Medior": 2, "Senior": 3, "Lead": 4}
    LEVEL_BADGE_COL  = {
        "Lead":   (C["violet"], C["violet"]+"1A"),
        "Senior": (C["teal"],   C["teal"]+"1A"),
        "Medior": (C["blue"],   C["blue"]+"1A"),
        "Junior": (C["amber"],  C["amber"]+"1A"),
    }

    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Organisation Hierarchy</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:20px">'
        f'Automatically structured by function and seniority grade from matched titles.</p>',
        unsafe_allow_html=True,
    )

    results  = st.session_state.get("last_results", [])
    df_input = st.session_state.get("upload_df")
    name_col = st.session_state.get("upload_name_col")
    title_col = st.session_state.get("upload_title_col")

    if not results:
        st.info("Run a match on the Matching page first — upload a file with employee titles to build the hierarchy.")
        return

    matched = [r for r in results if r.matched]
    if not matched:
        st.warning("No titles could be matched. Check the reference workbook is selected.")
        return

    # build name lookup — handle both single name col and FirstName/LastName split
    names = {}
    if df_input is not None:
        has_split = "FirstName" in df_input.columns and "LastName" in df_input.columns
        for idx, row in df_input.iterrows():
            if idx >= len(results):
                break
            if has_split:
                fn_v = str(row.get("FirstName","")).strip()
                ln_v = str(row.get("LastName","")).strip()
                full = (fn_v + " " + ln_v).strip()
                names[idx] = full if full else None
            elif name_col and name_col != "— none —":
                names[idx] = str(row.get(name_col,"")).strip() or None

    # detect dept column from uploaded df
    dept_col = None
    if df_input is not None:
        for candidate in ["Department","department","Dept","dept","BusinessUnit","business_unit","Function"]:
            if candidate in df_input.columns:
                dept_col = candidate
                break

    # group by department (from upload) or matched function → level
    from collections import defaultdict
    tree = defaultdict(lambda: defaultdict(list))
    for idx, r in enumerate(results):
        if not r.matched:
            continue
        # prefer uploaded department column for grouping
        if dept_col and df_input is not None and idx < len(df_input):
            fn = str(df_input.iloc[idx][dept_col]).strip() or r.function or "Other"
        else:
            fn = r.function or "Other"
        lv  = r.level    or "Medior"
        person_name = names.get(idx)
        # next step
        next_role = ""
        try:
            cp = catalog.repository.career_paths.get(r.job_id)
            if cp and cp.next_job_id:
                nj = catalog.repository.jobs.get(cp.next_job_id)
                if nj:
                    next_role = nj.standard_title
        except Exception:
            pass
        tree[fn][lv].append({
            "name":       person_name,
            "title":      r.input_title,
            "std_title":  r.standard_title,
            "confidence": r.confidence,
            "match_type": r.match_type.value,
            "next_role":  next_role,
            "job_id":     r.job_id,
        })

    # summary stats
    total   = sum(len(v) for fn in tree for v in tree[fn].values())
    n_fns   = len(tree)
    n_lead  = sum(len(tree[fn].get("Lead",[])) for fn in tree)
    n_junior = sum(len(tree[fn].get("Junior",[])) for fn in tree)
    st.markdown(
        f'<div style="display:flex;gap:10px;margin:0 0 20px">'
        f'{_stat_card(total,"Employees")}{_stat_card(n_fns,"Departments")}'
        f'{_stat_card(n_lead,"Lead roles",C["violet"])}{_stat_card(n_junior,"Junior roles",C["amber"])}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # render each function block
    fn_order = sorted(tree.keys(), key=lambda f: f)
    level_order = ["Lead","Senior","Medior","Junior"]
    cat_map = {j.function: j for j in catalog.repository.jobs.values()}

    for fn in fn_order:
        fn_levels = tree[fn]
        total_fn  = sum(len(fn_levels.get(lv,[])) for lv in level_order)

        # get category label
        cat_label = ""
        try:
            for jid, job in catalog.repository.jobs.items():
                if job.function == fn:
                    for sheet_row in []:  # placeholder
                        pass
            # look up from categories
            for cat_name, cat_fn, _ in []:
                if cat_fn == fn:
                    cat_label = cat_name
        except Exception:
            pass

        # function header
        fn_html = (
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:16px;margin-bottom:16px;overflow:hidden;'
            f'box-shadow:0 1px 3px rgba(23,33,46,.05),0 12px 28px -20px rgba(23,33,46,.35)">'
            f'<div style="background:linear-gradient(135deg,{C["teal"]},{C["teal"]}CC);'
            f'padding:14px 18px;display:flex;justify-content:space-between;align-items:center">'
            f'<div>'
            f'<div style="font-family:{FONT_SERIF};font-size:19px;font-weight:600;color:#fff;'
            f'letter-spacing:-0.01em">{fn}</div></div>'
            f'<span style="font-family:{FONT_MONO};font-size:12px;font-weight:600;'
            f'background:#ffffff33;color:#fff;border-radius:999px;padding:3px 11px">'
            f'{total_fn} people</span></div>'
        )

        # level sections
        for lv in level_order:
            people = fn_levels.get(lv, [])
            if not people:
                continue
            fg, bg = LEVEL_BADGE_COL.get(lv, (C["muted"],"#F4F6F8"))
            fn_html += (
                f'<div style="padding:12px 18px;border-bottom:1px solid {C["line-2"] if hasattr(C,"line-2") else "#EEF1F4"}">'
                f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.14em;'
                f'text-transform:uppercase;color:{fg};margin-bottom:8px;'
                f'display:flex;align-items:center;gap:8px">'
                f'<span style="width:8px;height:8px;border-radius:50%;background:{fg};display:inline-block"></span>'
                f'{lv}</div>'
                f'<div style="display:flex;flex-direction:column;gap:6px">'
            )
            for p in people:
                name_part = (
                    f'<span style="font-family:{FONT_SANS};font-size:13px;font-weight:600;'
                    f'color:{C["ink"]}">{p["name"]}</span> '
                    f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">·</span> '
                ) if p["name"] else ""
                next_part = (
                    f' <span style="font-family:{FONT_MONO};font-size:10px;color:{C["teal"]};'
                    f'margin-left:6px">→ {p["next_role"]}</span>'
                ) if p["next_role"] else ""
                conf_col = C["teal"] if p["confidence"]>=96 else (C["amber"] if p["confidence"]>=80 else C["clay"])
                fn_html += (
                    f'<div style="display:flex;align-items:center;justify-content:space-between;'
                    f'padding:7px 10px;background:{bg};border-radius:8px;flex-wrap:wrap;gap:4px">'
                    f'<div style="flex:1">'
                    f'{name_part}'
                    f'<span style="font-family:{FONT_SANS};font-size:13px;color:{C["ink"]}">{p["std_title"]}</span>'
                    f'{next_part}</div>'
                    f'<div style="display:flex;align-items:center;gap:6px;flex-shrink:0">'
                    f'<span style="font-family:{FONT_MONO};font-size:10px;font-weight:600;color:{conf_col}">'
                    f'{p["confidence"]}%</span>'
                    f'<span style="font-family:{FONT_MONO};font-size:9px;color:{C["muted"]}">{p["match_type"]}</span>'
                    f'</div></div>'
                )
            fn_html += '</div></div>'

        fn_html += '</div>'
        st.markdown(fn_html, unsafe_allow_html=True)

    # ── export ────────────────────────────────────────────────────────────
    import io, pandas as pd_exp
    rows = []
    for fn in fn_order:
        for lv in level_order:
            for p in tree[fn].get(lv,[]):
                rows.append({
                    "Function":    fn,
                    "Level":       lv,
                    "Name":        p["name"] or "",
                    "Input Title": p["title"],
                    "Matched Role":p["std_title"],
                    "Confidence":  p["confidence"],
                    "Match Type":  p["match_type"],
                    "Next Role":   p["next_role"],
                })
    if rows:
        exp_df = pd_exp.DataFrame(rows)
        buf = io.BytesIO()
        exp_df.to_excel(buf, index=False)
        st.download_button(
            "⬇  Download org structure (.xlsx)",
            data=buf.getvalue(),
            file_name="jobsy_org_hierarchy.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )



def _build_org_json(df_input, results, title_col):
    """Build a JSON tree for D3 from the uploaded dataset."""
    import json as _json
    import pandas as pd

    # detect columns
    id_col  = next((c for c in ["EmployeeID","employee_id","ID","id"] if c in df_input.columns), None)
    mgr_col = next((c for c in ["ManagerID","manager_id","ManagerId","ReportsTo"] if c in df_input.columns), None)
    dept_col = next((c for c in ["Department","department","Dept","BusinessUnit"] if c in df_input.columns), None)
    fn_col  = next((c for c in ["FirstName","first_name"] if c in df_input.columns), None)
    ln_col  = next((c for c in ["LastName","last_name"] if c in df_input.columns), None)
    nc_col  = next((c for c in ["Name","name","FullName"] if c in df_input.columns), None)

    LEVEL_SORT = {"Lead":0,"Senior":1,"Medior":2,"Junior":3}
    DEPT_COLORS = {
        "Executive":"#6A53B0","Finance":"#0E7C66","HR":"#2B5FA6",
        "IT":"#B9791A","Engineering":"#0E7C66","Sales":"#A8443A",
        "Marketing":"#6A53B0","Operations":"#5A6B7A","Warehouse":"#8B6914",
        "Legal":"#2B5FA6","Customer Service":"#0E7C66","Support":"#5A6B7A",
    }
    LEVEL_COLORS = {"Lead":"#6A53B0","Senior":"#0E7C66","Medior":"#2B5FA6","Junior":"#B9791A"}

    nodes = {}
    for idx, row in df_input.iterrows():
        eid   = str(row[id_col]) if id_col else str(idx)
        mgrid = str(row[mgr_col]) if mgr_col and pd.notna(row.get(mgr_col)) else None
        dept  = str(row[dept_col]).strip() if dept_col else "Other"
        if fn_col and ln_col:
            name = (str(row.get(fn_col,"")) + " " + str(row.get(ln_col,""))).strip()
        elif nc_col:
            name = str(row.get(nc_col,"")).strip()
        else:
            name = eid
        input_title = str(row.get(title_col,"")).strip() if title_col else ""
        r = results[idx] if idx < len(results) else None
        matched_title = r.standard_title if r and r.matched else ""
        level         = r.level          if r and r.matched else ""
        confidence    = r.confidence     if r and r.matched else 0
        nodes[eid] = {
            "id": eid, "name": name, "input_title": input_title,
            "matched_title": matched_title or input_title,
            "level": level, "dept": dept, "confidence": confidence,
            "manager_id": mgrid, "type": "employee",
            "color": LEVEL_COLORS.get(level, "#5A6B7A"),
            "children": [], "_children": None,
        }

    # detect flat structure: if >60% of employees report to same person, switch to dept grouping
    if mgr_col:
        mgr_counts = df_input[mgr_col].value_counts()
        top_mgr_share = mgr_counts.iloc[0] / len(df_input) if len(mgr_counts) else 0
        use_real_mgr = top_mgr_share < 0.5
    else:
        use_real_mgr = False

    if use_real_mgr:
        # build from real manager IDs
        roots = []
        for eid, node in nodes.items():
            mgr = node["manager_id"]
            if mgr and mgr in nodes:
                nodes[mgr]["children"].append(node)
            else:
                roots.append(node)
        if len(roots) == 1:
            tree = roots[0]
        else:
            tree = {"id":"__root__","name":"Organisation","type":"root",
                    "color":"#17212E","children":roots,"matched_title":"","level":"","dept":""}
    else:
        # flat → department-based intermediate layer
        # find the top-level person (no manager or most-senior)
        top_nodes = [n for n in nodes.values() if not n["manager_id"] or n["manager_id"] not in nodes]
        # separate C-suite from department workers
        dept_groups = {}
        exec_nodes = []
        for n in nodes.values():
            if n["level"] == "Lead" or n["dept"] == "Executive":
                exec_nodes.append(n)
            else:
                dept_groups.setdefault(n["dept"], []).append(n)

        # sort within each dept by level
        for dept in dept_groups:
            dept_groups[dept].sort(key=lambda x: (LEVEL_SORT.get(x["level"],9), x["name"]))

        # build dept nodes
        dept_node_list = []
        for dept_name, members in sorted(dept_groups.items()):
            dc = DEPT_COLORS.get(dept_name, "#5A6B7A")
            dept_node = {
                "id": f"dept-{dept_name}",
                "name": dept_name,
                "matched_title": f"{len(members)} employees",
                "level": "", "dept": dept_name, "type": "department",
                "color": dc, "children": members, "_children": None,
            }
            dept_node_list.append(dept_node)

        # sort exec by level
        exec_nodes.sort(key=lambda x: (LEVEL_SORT.get(x["level"],9), x["name"]))

        # find CEO as root
        ceo = next((n for n in exec_nodes if "CEO" in n["input_title"] or "Chief Executive" in n["input_title"]), None)
        if ceo:
            other_exec = [n for n in exec_nodes if n is not ceo]
            root_children = other_exec + dept_node_list
            ceo["children"] = root_children
            tree = ceo
        else:
            tree = {"id":"__root__","name":"Organisation","type":"root",
                    "color":"#17212E","children":exec_nodes + dept_node_list,
                    "matched_title":"","level":"","dept":""}

    return _json.dumps(tree, default=str)


def organigram_page(catalog):
    """Interactive D3 organigram with real or department-based reporting lines."""
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Organigram</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Reporting lines and hierarchy based on matched roles and seniority.</p>',
        unsafe_allow_html=True,
    )

    results   = st.session_state.get("last_results", [])
    df_input  = st.session_state.get("upload_df")
    title_col = st.session_state.get("upload_title_col", "JobTitle")

    if not results or df_input is None:
        st.info("Upload a file and run a match on the Matching page first.")
        return

    try:
        tree_json = _build_org_json(df_input, results, title_col)
    except Exception as exc:
        st.error(f"Could not build org tree: {exc}")
        return

    total = len(results)
    matched = sum(1 for r in results if r.matched)
    st.markdown(
        f'<div style="display:flex;gap:10px;margin-bottom:16px">'
        f'{_stat_card(total,"Employees")}'
        f'{_stat_card(matched,"Matched",C["teal"])}'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.caption("Tap any node to expand or collapse its subtree. Pinch or scroll to zoom. Drag to pan.")

    import streamlit.components.v1 as components
    components.html(_orgchart_html(tree_json), height=700, scrolling=True)


def _orgchart_html(tree_json: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #ECEEF0; font-family: 'Arial', sans-serif; overflow: hidden; }}
  #chart {{ width: 100%; height: 700px; }}
  svg {{ width: 100%; height: 100%; }}
  .node rect {{
    rx: 8; ry: 8;
    stroke: rgba(0,0,0,0.08);
    stroke-width: 1;
    filter: drop-shadow(0 2px 6px rgba(0,0,0,0.12));
    cursor: pointer;
    transition: opacity 0.2s;
  }}
  .node rect:hover {{ opacity: 0.85; }}
  .node text {{ pointer-events: none; font-family: Arial, sans-serif; }}
  .link {{
    fill: none;
    stroke: #C7D1D8;
    stroke-width: 1.5;
  }}
  .link-highlighted {{ stroke: #0E7C66; stroke-width: 2; }}
  #tooltip {{
    position: fixed;
    background: #17212E;
    color: #fff;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
    max-width: 200px;
    z-index: 999;
  }}
  #controls {{
    position: absolute;
    top: 10px;
    right: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .ctrl-btn {{
    width: 32px; height: 32px;
    background: #fff;
    border: 1px solid #D9E0E5;
    border-radius: 8px;
    font-size: 16px;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
    user-select: none;
  }}
  #legend {{
    position: absolute;
    bottom: 10px;
    left: 10px;
    background: #fff;
    border: 1px solid #D9E0E5;
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 11px;
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
</style>
</head>
<body>
<div id="chart">
  <svg id="svg"></svg>
  <div id="controls">
    <div class="ctrl-btn" id="zoomin" title="Zoom in">+</div>
    <div class="ctrl-btn" id="zoomout" title="Zoom out">−</div>
    <div class="ctrl-btn" id="reset" title="Reset">⌂</div>
  </div>
  <div id="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#6A53B0"></div>Lead</div>
    <div class="legend-item"><div class="legend-dot" style="background:#0E7C66"></div>Senior</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2B5FA6"></div>Medior</div>
    <div class="legend-item"><div class="legend-dot" style="background:#B9791A"></div>Junior</div>
    <div class="legend-item"><div class="legend-dot" style="background:#5A6B7A"></div>Dept</div>
  </div>
</div>
<div id="tooltip"></div>

<script>
const treeData = {tree_json};

const W = document.getElementById("chart").clientWidth || 900;
const H = 700;
const NODE_W  = 160;
const NODE_H  = 46;
const DX      = 68;
const DY      = 220;
const DURATION = 400;

const svg = d3.select("#svg");
const g   = svg.append("g");

// zoom
const zoom = d3.zoom()
  .scaleExtent([0.1, 3])
  .on("zoom", e => g.attr("transform", e.transform));
svg.call(zoom);

// reset button
document.getElementById("zoomin").onclick  = () => svg.transition().call(zoom.scaleBy, 1.3);
document.getElementById("zoomout").onclick = () => svg.transition().call(zoom.scaleBy, 0.77);
document.getElementById("reset").onclick   = () => {{
  svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity.translate(W*0.08, H*0.5).scale(0.8));
}};

const treeFn = d3.tree().nodeSize([DX, DY]);
let root = d3.hierarchy(treeData, d => d.children || []);
root.x0 = H / 2;
root.y0 = 0;

// collapse dept children initially (show only first 3 of each dept)
function collapseDeep(d, depth) {{
  if (d.children) {{
    if (d.data.type === "department") {{
      d._children = d.children;
      d.children = null;
    }} else if (depth > 1) {{
      d._children = d.children;
      d.children = null;
    }} else {{
      d.children.forEach(c => collapseDeep(c, depth+1));
    }}
  }}
}}
collapseDeep(root, 0);

// tooltip
const tip = document.getElementById("tooltip");
function showTip(evt, d) {{
  const nd = d.data;
  tip.innerHTML = `<b>${{nd.name || nd.id}}</b><br>
    ${{nd.input_title ? nd.input_title + (nd.matched_title && nd.matched_title !== nd.input_title ? '<br>→ '+nd.matched_title : '') : ''}}<br>
    ${{nd.level ? '<span style="opacity:.7">'+nd.level+'</span>' : ''}}
    ${{nd.dept && nd.type!=="department" ? ' · '+nd.dept : ''}}`;
  tip.style.opacity = 1;
  tip.style.left  = (evt.clientX + 10) + "px";
  tip.style.top   = (evt.clientY - 10) + "px";
}}
function hideTip() {{ tip.style.opacity = 0; }}

// link path (horizontal tree: y=horizontal, x=vertical)
const diagonal = d3.linkHorizontal().x(d => d.y).y(d => d.x);

let linkSel, nodeSel;

function update(source) {{
  treeFn(root);
  const nodes = root.descendants();
  const links  = root.links();

  // links
  const link = g.selectAll("path.link").data(links, d => d.target.data.id);
  const linkEnter = link.enter().append("path")
    .attr("class","link")
    .attr("d", () => {{
      const o = {{ x: source.x0, y: source.y0 }};
      return diagonal({{source:o,target:o}});
    }});
  link.merge(linkEnter).transition().duration(DURATION)
    .attr("d", diagonal);
  link.exit().transition().duration(DURATION)
    .attr("d", () => {{
      const o = {{ x: source.x, y: source.y }};
      return diagonal({{source:o,target:o}});
    }}).remove();

  // nodes
  const node = g.selectAll("g.node").data(nodes, d => d.data.id);
  const nodeEnter = node.enter().append("g")
    .attr("class","node")
    .attr("transform", () => `translate(${{source.y0}},${{source.x0}})`)
    .on("click", (e,d) => {{
      if (d.children)  {{ d._children = d.children; d.children = null; }}
      else if (d._children) {{ d.children = d._children; d._children = null; }}
      update(d);
    }})
    .on("mouseover", showTip)
    .on("mouseout", hideTip)
    .on("touchstart", showTip, {{passive:true}})
    .on("touchend", hideTip);

  // bg rect
  nodeEnter.append("rect")
    .attr("x", -NODE_W/2)
    .attr("y", -NODE_H/2)
    .attr("width", NODE_W)
    .attr("height", NODE_H)
    .attr("fill", d => d.data.color || "#5A6B7A")
    .attr("opacity", 0.92);

  // name text
  nodeEnter.append("text")
    .attr("dy", d => d.data.type === "department" ? 5 : -8)
    .attr("text-anchor","middle")
    .attr("fill","#fff")
    .attr("font-size", d => d.data.type === "department" ? 12 : 11)
    .attr("font-weight","bold")
    .text(d => {{
      const n = d.data.name || d.data.id;
      return n.length > 18 ? n.substring(0,17)+"…" : n;
    }});

  // title text (employees only)
  nodeEnter.append("text")
    .attr("dy", 8)
    .attr("text-anchor","middle")
    .attr("fill","rgba(255,255,255,0.85)")
    .attr("font-size", 10)
    .text(d => {{
      if (d.data.type === "department") return d.data.matched_title || "";
      const t = d.data.matched_title || d.data.input_title || "";
      return t.length > 22 ? t.substring(0,21)+"…" : t;
    }});

  // expand/collapse indicator
  nodeEnter.append("text")
    .attr("class","toggle")
    .attr("dy", NODE_H/2 - 4)
    .attr("text-anchor","middle")
    .attr("fill","rgba(255,255,255,0.6)")
    .attr("font-size", 9);

  // transition all nodes
  const nodeUpdate = node.merge(nodeEnter);
  nodeUpdate.transition().duration(DURATION)
    .attr("transform", d => `translate(${{d.y}},${{d.x}})`);

  nodeUpdate.select(".toggle")
    .text(d => d._children ? `▶ ${{d._children.length}}` : (d.children && d.children.length > 0 ? "▼" : ""));

  node.exit().transition().duration(DURATION)
    .attr("transform", () => `translate(${{source.y}},${{source.x}})`)
    .remove();

  nodes.forEach(d => {{ d.x0 = d.x; d.y0 = d.y; }});
}}

update(root);

// initial centering
svg.call(zoom.transform, d3.zoomIdentity.translate(80, H/2).scale(0.85));
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()

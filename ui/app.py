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

    desc=(f'<div style="font-size:14px;color:#34424F;margin-top:13px;line-height:1.55">'
          f'{r.description}</div>' if r.description else "")

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
        f'{desc}{sal}{review}'
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

    service = MatchingService(catalog, review_threshold=threshold, enable_fuzzy=enable_fuzzy)

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
            col = st.selectbox("Column with titles", list(df_in.columns))
            if st.button("Match column", type="primary"):
                titles = df_in[col].fillna("").astype(str).tolist()

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

if __name__ == "__main__":
    main()
    

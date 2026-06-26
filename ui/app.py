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

# ------------------------------------------------------------------ constants
STAGE_COLORS = {
    "exact":      "#0E7C66",
    "normalized": "#2B5FA6",
    "synonym":    "#6A53B0",
    "fuzzy":      "#B9791A",
    "none":       "#A8443A",
}
LEVEL_COLORS = {
    "Junior": ("#E8F4FF", "#2B5FA6"),
    "Medior": ("#E2F1ED", "#0E7C66"),
    "Senior": ("#ECE7F7", "#6A53B0"),
    "Lead":   ("#F7EEDD", "#B9791A"),
}


# ------------------------------------------------------------------ CSS
def inject_css() -> None:
    st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
    /* ── base ── */
    html, body, [data-testid="stAppViewContainer"] {
        background: #ECEEF0 !important;
        font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
    }
    [data-testid="stMain"] { background: #ECEEF0 !important; }
    [data-testid="stSidebar"] {
        background: #17212E !important;
        border-right: none !important;
    }
    [data-testid="stSidebar"] * { color: #C8D0D8 !important; }
    [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #FFFFFF !important;
        font-family: 'Fraunces', serif !important;
        font-size: 15px !important;
        letter-spacing: 0.01em;
    }
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color: #0E7C66 !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 28px !important;
    }
    [data-testid="stSidebar"] [data-baseweb="radio"] label { color: #C8D0D8 !important; }
    [data-testid="stSidebar"] [data-baseweb="slider"] { filter: brightness(1.4); }
    [data-testid="stSidebar"] .stDivider { border-color: #2C3A48 !important; }

    /* ── hide default streamlit chrome ── */
    #MainMenu, footer, header { visibility: hidden; }
    [data-testid="stToolbar"] { display: none; }

    /* ── tabs ── */
    [data-baseweb="tab-list"] { background: transparent !important; gap: 4px; }
    [data-baseweb="tab"] {
        background: #FFFFFF !important; border-radius: 10px 10px 0 0 !important;
        border: 1px solid #D9E0E5 !important; border-bottom: none !important;
        color: #5E6E7C !important; font-weight: 500;
        padding: 8px 20px !important;
    }
    [aria-selected="true"][data-baseweb="tab"] {
        background: #FFFFFF !important; color: #0E7C66 !important;
        border-top: 2px solid #0E7C66 !important;
    }
    [data-testid="stTabPanel"] {
        background: #FFFFFF; border-radius: 0 12px 12px 12px;
        border: 1px solid #D9E0E5; padding: 20px !important;
    }

    /* ── text area ── */
    [data-baseweb="textarea"] textarea {
        background: #F4F6F8 !important; border: 1px solid #D9E0E5 !important;
        border-radius: 10px !important; font-family: 'IBM Plex Mono', monospace !important;
        font-size: 14px !important; color: #17212E !important;
    }
    [data-baseweb="textarea"] textarea:focus {
        border-color: #0E7C66 !important;
        box-shadow: 0 0 0 3px #E2F1ED !important;
    }

    /* ── primary button ── */
    [data-testid="baseButton-primary"] {
        background: linear-gradient(180deg, #12A085, #0E7C66) !important;
        border: none !important; border-radius: 10px !important;
        font-family: 'IBM Plex Sans', sans-serif !important;
        font-weight: 600 !important; font-size: 15px !important;
        padding: 10px 28px !important; color: #FFFFFF !important;
        box-shadow: 0 6px 16px -8px rgba(14,124,102,.7) !important;
        transition: all .15s !important;
    }
    [data-testid="baseButton-primary"]:hover {
        filter: brightness(1.06) !important; transform: translateY(-1px) !important;
    }

    /* ── secondary / download button ── */
    [data-testid="baseButton-secondary"] {
        background: #FFFFFF !important; border: 1px solid #D9E0E5 !important;
        border-radius: 10px !important; color: #17212E !important;
        font-weight: 500 !important;
    }
    [data-testid="baseButton-secondary"]:hover {
        border-color: #0E7C66 !important; color: #0E7C66 !important;
    }

    /* ── dataframe ── */
    [data-testid="stDataFrame"] { border-radius: 12px !important; overflow: hidden; }

    /* ── expander ── */
    [data-testid="stExpander"] {
        background: #FFFFFF !important; border: 1px solid #D9E0E5 !important;
        border-radius: 12px !important; margin-top: 12px;
    }

    /* ── info / warning boxes ── */
    [data-testid="stAlert"] { border-radius: 10px !important; }

    /* ── custom components ── */
    .jb-header { padding: 8px 0 20px; }
    .jb-wordmark {
        font-family: 'Fraunces', serif; font-weight: 700;
        font-size: 44px; letter-spacing: -0.03em;
        line-height: 1; color: #17212E; display: inline;
    }
    .jb-tag {
        font-family: 'IBM Plex Mono', monospace; font-size: 11px;
        letter-spacing: .18em; text-transform: uppercase; color: #0E7C66;
        border: 1px solid #0E7C6633; background: #0E7C6614;
        border-radius: 999px; padding: 4px 12px;
        vertical-align: middle; margin-left: 10px;
    }
    .jb-lede {
        color: #5E6E7C; font-size: 15.5px; margin: 12px 0 0;
        max-width: 58ch; line-height: 1.55;
    }
    .jb-lede b { color: #17212E; font-weight: 600; }

    /* stat row */
    .stat-row { display: flex; gap: 10px; margin: 18px 0; }
    .stat-card {
        flex: 1; background: #FFFFFF; border: 1px solid #D9E0E5;
        border-radius: 14px; padding: 14px 10px; text-align: center;
        box-shadow: 0 1px 2px rgba(23,33,46,.04), 0 8px 24px -16px rgba(23,33,46,.3);
    }
    .stat-card .n {
        font-family: 'IBM Plex Mono', monospace; font-weight: 600;
        font-size: 26px; line-height: 1; color: #17212E;
    }
    .stat-card .n.green { color: #0E7C66; }
    .stat-card .n.amber { color: #B9791A; }
    .stat-card .n.clay  { color: #A8443A; }
    .stat-card .l {
        font-family: 'IBM Plex Mono', monospace; font-size: 9.5px;
        letter-spacing: .12em; text-transform: uppercase;
        color: #8A9AAA; margin-top: 5px;
    }

    /* result cards */
    .result-card {
        background: #FFFFFF; border: 1px solid #D9E0E5;
        border-left: 4px solid #D9E0E5; border-radius: 14px;
        padding: 18px 18px 16px; margin-bottom: 12px;
        box-shadow: 0 1px 2px rgba(23,33,46,.04), 0 12px 28px -20px rgba(23,33,46,.35);
        transition: transform .18s;
    }
    .result-card:hover { transform: translateY(-2px); }
    .result-card.exact      { border-left-color: #0E7C66; }
    .result-card.normalized { border-left-color: #2B5FA6; }
    .result-card.synonym    { border-left-color: #6A53B0; }
    .result-card.fuzzy      { border-left-color: #B9791A; }
    .result-card.none       { border-left-color: #A8443A; }

    .rc-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
    .rc-input { font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; color: #8A9AAA; }
    .rc-input b { color: #17212E; font-weight: 500; }
    .rc-title {
        font-family: 'Fraunces', serif; font-weight: 600;
        font-size: 22px; letter-spacing: -0.015em; color: #17212E;
        margin: 5px 0 0; line-height: 1.2;
    }
    .rc-title.empty { color: #A8443A; }
    .rc-conf { text-align: right; flex: none; }
    .rc-conf .num {
        font-family: 'IBM Plex Mono', monospace; font-weight: 600;
        font-size: 28px; line-height: 1;
    }
    .rc-conf .lbl {
        font-family: 'IBM Plex Mono', monospace; font-size: 9px;
        letter-spacing: .12em; text-transform: uppercase; color: #8A9AAA; margin-top: 2px;
    }
    .rc-conf.exact .num      { color: #0E7C66; }
    .rc-conf.normalized .num { color: #2B5FA6; }
    .rc-conf.synonym .num    { color: #6A53B0; }
    .rc-conf.fuzzy .num      { color: #B9791A; }
    .rc-conf.none .num       { color: #A8443A; }

    .rc-badge {
        display: inline-block; font-family: 'IBM Plex Mono', monospace;
        font-size: 11px; font-weight: 500; padding: 3px 10px;
        border-radius: 999px; margin-top: 9px;
    }
    .rc-badge.exact      { background: #E2F1ED; color: #0E7C66; }
    .rc-badge.normalized { background: #E6EDF7; color: #2B5FA6; }
    .rc-badge.synonym    { background: #ECE7F7; color: #6A53B0; }
    .rc-badge.fuzzy      { background: #F7EEDD; color: #B9791A; }
    .rc-badge.none       { background: #F6E5E3; color: #A8443A; }

    .rc-meta { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 13px; }
    .rc-pill {
        font-family: 'IBM Plex Mono', monospace; font-size: 11px;
        color: #5E6E7C; background: #F4F6F8; border: 1px solid #D9E0E5;
        border-radius: 7px; padding: 3px 9px;
    }
    .rc-pill b { color: #17212E; font-weight: 500; }
    .rc-lvl {
        font-family: 'IBM Plex Mono', monospace; font-size: 11px;
        font-weight: 500; border-radius: 7px; padding: 3px 9px; border: 1px solid transparent;
    }

    .rc-desc { font-size: 14px; color: #34424F; margin-top: 13px; line-height: 1.55; }

    .rc-salary { margin-top: 14px; }
    .rc-sal-head {
        display: flex; justify-content: space-between; align-items: baseline;
        font-family: 'IBM Plex Mono', monospace;
    }
    .rc-sal-lbl { font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: #8A9AAA; }
    .rc-sal-rng { font-size: 13px; font-weight: 600; color: #0E7C66; }
    .rc-sal-rng.na { color: #8A9AAA; font-weight: 400; }
    .rc-sal-track {
        height: 7px; border-radius: 4px; background: #F0F2F4;
        border: 1px solid #DDE2E7; margin-top: 7px; position: relative; overflow: hidden;
    }
    .rc-sal-fill {
        position: absolute; top: 0; bottom: 0; border-radius: 4px;
        background: linear-gradient(90deg, #12A085, #0E7C66);
    }

    .rc-review {
        display: flex; align-items: center; gap: 8px; margin-top: 13px;
        font-size: 12.5px; color: #B9791A; background: #F7EEDD;
        border-radius: 8px; padding: 8px 12px;
    }
    .rc-review.miss { color: #A8443A; background: #F6E5E3; }
    .rc-review .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex: none; }

    /* pipeline bar */
    .pipe { display: flex; gap: 5px; margin: 15px 0 2px; }
    .pipe-stage { flex: 1; }
    .pipe-bar { height: 5px; border-radius: 3px; background: #EDF0F3; }
    .pipe-bar.passed { background: #C7D1D8; }
    .pipe-bar.hit-exact      { background: linear-gradient(90deg,#12A085,#0E7C66); }
    .pipe-bar.hit-normalized { background: #2B5FA6; }
    .pipe-bar.hit-synonym    { background: #6A53B0; }
    .pipe-bar.hit-fuzzy      { background: #B9791A; }
    .pipe-nm {
        font-family: 'IBM Plex Mono', monospace; font-size: 9px;
        letter-spacing: .05em; text-transform: uppercase; color: #C7D1D8;
        margin-top: 6px; text-align: center;
    }
    .pipe-nm.passed { color: #8A9AAA; }
    .pipe-nm.hit-exact      { color: #0E7C66; }
    .pipe-nm.hit-normalized { color: #2B5FA6; }
    .pipe-nm.hit-synonym    { color: #6A53B0; }
    .pipe-nm.hit-fuzzy      { color: #B9791A; }

    @media (max-width: 640px) {
        .jb-wordmark { font-size: 34px; }
        .stat-row { gap: 7px; flex-wrap: wrap; }
        .stat-card { min-width: calc(50% - 4px); }
    }
    </style>
    """, unsafe_allow_html=True)


# ------------------------------------------------------------------ sample catalog
class _SampleCatalog:
    def __init__(self) -> None:
        self.repository = Repository(self._sample_sheets(), validate=False)

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

    @staticmethod
    def _sample_sheets() -> dict:
        jobs = [
            ("J-HRA",  "HR Advisor",                 "HR",          "Medior"),
            ("J-HRBP", "HR Business Partner",         "HR",          "Senior"),
            ("J-REC",  "Recruiter",                   "HR",          "Medior"),
            ("J-ACC",  "Accountant",                  "Finance",     "Medior"),
            ("J-FC",   "Financial Controller",        "Finance",     "Senior"),
            ("J-JSE",  "Junior Software Engineer",    "Engineering", "Junior"),
            ("J-SE",   "Software Engineer",           "Engineering", "Medior"),
            ("J-SSE",  "Senior Software Engineer",    "Engineering", "Senior"),
            ("J-DA",   "Data Analyst",                "Data",        "Medior"),
            ("J-PM",   "Product Manager",             "Product",     "Senior"),
        ]
        profiles = {
            "J-HRA":  "Advises managers and employees on policy, Dutch labour law, and casework.",
            "J-HRBP": "Partners with senior leaders on workforce planning and people strategy.",
            "J-REC":  "Runs hiring end-to-end: sourcing, screening, interviewing, and offer.",
            "J-ACC":  "Maintains the ledger and prepares statutory, audit-ready accounts.",
            "J-FC":   "Owns the close, financial reporting, and the internal control framework.",
            "J-JSE":  "Ships well-scoped features with guidance from senior engineers.",
            "J-SE":   "Designs and builds features across the stack with little supervision.",
            "J-SSE":  "Leads technical design on complex systems and mentors engineers.",
            "J-DA":   "Turns raw data into dashboards and insight that inform decisions.",
            "J-PM":   "Defines product direction and aligns delivery with user needs.",
        }
        salary = [
            ("HR", "Medior", 42000, 58000), ("HR", "Senior", 60000, 82000),
            ("Finance", "Medior", 45000, 62000), ("Finance", "Senior", 70000, 95000),
            ("Engineering", "Junior", 42000, 56000), ("Engineering", "Medior", 55000, 75000),
            ("Engineering", "Senior", 78000, 105000),
            ("Data", "Medior", 50000, 68000), ("Product", "Senior", 75000, 100000),
        ]
        mapping = [
            ("HRBP", "J-HRBP"), ("People Partner", "J-HRBP"), ("HR Manager", "J-HRBP"),
            ("HR Officer", "J-HRA"), ("Corporate Recruiter", "J-REC"),
            ("Talent Acquisition Specialist", "J-REC"),
            ("Controller", "J-FC"), ("Business Controller", "J-FC"),
            ("Boekhouder", "J-ACC"), ("Bookkeeper", "J-ACC"),
            ("Developer", "J-SE"), ("Software Developer", "J-SE"),
            ("Junior Developer", "J-JSE"), ("BI Analyst", "J-DA"),
            ("Productmanager", "J-PM"), ("Product Owner", "J-PM"),
        ]
        return {
            "jobs":      pd.DataFrame(jobs, columns=["JobID","StandardTitle","Function","Level"]),
            "profiles":  pd.DataFrame([{"JobID":k,"Description":v} for k,v in profiles.items()]),
            "titles":    pd.DataFrame(mapping, columns=["ExistingTitle","JobID"]),
            "salary":    pd.DataFrame(salary, columns=["Function","Level","Min","Max"]),
            "career":    pd.DataFrame([{"JobID":j[0]} for j in jobs]),
            "levels":    pd.DataFrame([{"Level":x} for x in ("Junior","Medior","Senior","Lead")]),
            "employees": pd.DataFrame([{"EmployeeID":"1","Name":"-","CurrentTitle":"-"}]),
        }


# ------------------------------------------------------------------ loaders
@st.cache_resource(show_spinner="Loading reference library…")
def load_workbook_catalog(path: str):
    from core.catalog import Catalog
    catalog = Catalog(path); catalog.load(); return catalog

@st.cache_resource(show_spinner="Building sample catalog…")
def load_sample_catalog():
    return _SampleCatalog()


# ------------------------------------------------------------------ card HTML
GMIN, GMAX = 30000, 140000
PIPE_STAGES = [("exact","Exact"),("normalized","Norm."),("synonym","Synonym"),("fuzzy","Fuzzy")]
PIPE_ORDER  = {"exact":0,"normalized":1,"synonym":2,"fuzzy":3}

def _pipe_html(match_type: str) -> str:
    hit = PIPE_ORDER.get(match_type, -1)
    bars = ""
    for i, (key, label) in enumerate(PIPE_STAGES):
        if i < hit:
            bar_cls, nm_cls = "passed", "passed"
        elif i == hit:
            bar_cls, nm_cls = f"hit-{match_type}", f"hit-{match_type}"
        else:
            bar_cls = nm_cls = ""
        bars += (
            f'<div class="pipe-stage">'
            f'<div class="pipe-bar {bar_cls}"></div>'
            f'<div class="pipe-nm {nm_cls}">{label}</div>'
            f'</div>'
        )
    return f'<div class="pipe">{bars}</div>'

def _euro(n: float) -> str:
    return "€{:,.0f}".format(n).replace(",", ".")

def _card_html(r) -> str:
    t = r.match_type.value

    if not r.matched:
        conf_html = '<div class="rc-conf none"><div class="num">—</div><div class="lbl">conf</div></div>'
        return (
            f'<div class="result-card none">'
            f'<div class="rc-top">'
            f'<div><div class="rc-input">INPUT &nbsp;<b>{r.input_title or "(empty)"}</b></div>'
            f'<div class="rc-title empty">No standard match</div>'
            f'<span class="rc-badge none">No match</span></div>'
            f'{conf_html}</div>'
            f'{_pipe_html("none")}'
            f'<div class="rc-review miss"><span class="dot"></span>'
            f'{"Empty title — nothing to match." if not r.input_title.strip() else "Routed to review — a human picks the role, or the AI stage handles it later."}'
            f'</div></div>'
        )

    color = STAGE_COLORS.get(t, "#5E6E7C")
    conf_html = (
        f'<div class="rc-conf {t}">'
        f'<div class="num">{r.confidence}</div>'
        f'<div class="lbl">conf</div></div>'
    )

    # level chip
    lvl = r.level or ""
    lc_bg, lc_fg = LEVEL_COLORS.get(lvl, ("#F4F6F8", "#5E6E7C"))
    lvl_chip = f'<span class="rc-lvl" style="background:{lc_bg};color:{lc_fg}">{lvl}</span>' if lvl else ""

    # salary bar
    if r.salary_range:
        lo, hi = r.salary_range
        left  = max(0, (lo - GMIN) / (GMAX - GMIN)) * 100
        width = max(2, (hi - lo)  / (GMAX - GMIN)) * 100
        sal_html = (
            f'<div class="rc-salary">'
            f'<div class="rc-sal-head">'
            f'<span class="rc-sal-lbl">Salary band · gross / yr</span>'
            f'<span class="rc-sal-rng">{_euro(lo)} – {_euro(hi)}</span></div>'
            f'<div class="rc-sal-track">'
            f'<div class="rc-sal-fill" style="left:{left:.1f}%;width:{width:.1f}%"></div>'
            f'</div></div>'
        )
    else:
        sal_html = (
            f'<div class="rc-salary">'
            f'<div class="rc-sal-head">'
            f'<span class="rc-sal-lbl">Salary band</span>'
            f'<span class="rc-sal-rng na">No band defined</span></div></div>'
        )

    review_html = (
        '<div class="rc-review"><span class="dot"></span>Confidence below threshold — flagged for review.</div>'
        if r.requires_review else ""
    )
    desc_html = f'<div class="rc-desc">{r.description}</div>' if r.description else ""

    return (
        f'<div class="result-card {t}">'
        f'<div class="rc-top">'
        f'<div><div class="rc-input">INPUT &nbsp;<b>{r.input_title}</b></div>'
        f'<div class="rc-title">{r.standard_title}</div>'
        f'<span class="rc-badge {t}">{t.capitalize()} match</span></div>'
        f'{conf_html}</div>'
        f'{_pipe_html(t)}'
        f'<div class="rc-meta">'
        f'<span class="rc-pill"><b>{r.function}</b> function</span>'
        f'{lvl_chip}'
        f'<span class="rc-pill" style="font-size:10px">{r.job_id or ""}</span>'
        f'</div>'
        f'{desc_html}'
        f'{sal_html}'
        f'{review_html}'
        f'</div>'
    )


# ------------------------------------------------------------------ main
def main() -> None:
    st.set_page_config(
        page_title="Jobsy",
        page_icon="📊",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    inject_css()

    # ── header ──
    st.markdown(
        f'<div class="jb-header">'
        f'<span class="jb-wordmark">Jobsy</span>'
        f'<span class="jb-tag">{COUNTRY} · V1</span>'
        f'</div>'
        f'<p class="jb-lede">Resolve messy job titles to <b>standard roles</b>, '
        f'<b>profiles</b>, and <b>salary ranges</b>.</p>',
        unsafe_allow_html=True,
    )

    # ── sidebar ──
    with st.sidebar:
        st.markdown("### Data source")
        source = st.radio("", ["Built-in sample", "Reference workbook"], label_visibility="collapsed")
        path = WORKBOOK_PATH
        if source == "Reference workbook":
            path = st.text_input("Workbook path", value=WORKBOOK_PATH)
        st.markdown("---")
        st.markdown("### Matching")
        threshold    = st.slider("Review below", 50, 100, int(DEFAULT_THRESHOLD))
        enable_fuzzy = st.checkbox("Fuzzy stage (RapidFuzz)", value=True)
        st.markdown("---")

    # ── load catalog ──
    try:
        if source == "Built-in sample":
            catalog = load_sample_catalog()
        else:
            if not Path(path).exists():
                st.warning(f"Workbook not found at `{path}`. Switch to Built-in sample.")
                st.stop()
            catalog = load_workbook_catalog(path)
    except Exception as exc:
        st.error(f"Could not load catalog: {exc}")
        st.stop()

    stats = catalog.repository.statistics()
    with st.sidebar:
        st.markdown("### Library")
        st.metric("Roles", stats["jobs"])
        st.caption(
            f"{stats['title_mappings']} title mappings · "
            f"{stats['salary_bands']} salary bands · "
            f"{stats['functions']} functions"
        )

    service = MatchingService(catalog, review_threshold=threshold, enable_fuzzy=enable_fuzzy)

    # ── input ──
    tab_paste, tab_upload = st.tabs(["Paste titles", "Upload file"])
    titles: list[str] = []

    with tab_paste:
        raw = st.text_area(
            "One title per line",
            value="HRBP\nhr business partner\nJunior Developer\nController\nBoekhouder\nSofware Enginer\nUnderwater Basket Weaver",
            height=170, label_visibility="collapsed",
        )
        if st.button("Match titles", type="primary"):
            titles = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    with tab_upload:
        upload = st.file_uploader("CSV or Excel of titles", type=["csv","xlsx"])
        if upload is not None:
            df_in = pd.read_csv(upload) if upload.name.endswith(".csv") else pd.read_excel(upload)
            column = st.selectbox("Which column holds the titles?", list(df_in.columns))
            if st.button("Match column", type="primary"):
                titles = df_in[column].fillna("").astype(str).tolist()

    if not titles:
        st.markdown(
            '<div style="background:#FFFFFF;border:1px solid #D9E0E5;border-radius:12px;'
            'padding:18px 20px;color:#8A9AAA;font-size:14px;text-align:center;margin-top:12px">'
            'Add some titles and tap <b>Match titles</b> to see results.</div>',
            unsafe_allow_html=True,
        )
        return

    # ── run ──
    results = service.match_titles(titles)
    summary = service.summarize(results)

    # stat row
    def sc(n, cls=""): return f'<div class="stat-card"><div class="n {cls}">{n}</div><div class="l">'
    st.markdown(
        f'<div class="stat-row">'
        f'{sc(summary.total)}Total</div></div>'
        f'{sc(summary.matched,"green")}Matched</div></div>'
        f'{sc(summary.review,"amber")}Review</div></div>'
        f'{sc(summary.unmatched,"clay")}Unmatched</div></div>'
        f'{sc(f"{summary.avg_confidence:.0f}%")}Avg conf</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # filter toggle
    only_review = st.checkbox("Show only titles needing review")
    shown = [r for r in results if r.requires_review] if only_review else results

    # result cards
    cards_html = "".join(_card_html(r) for r in shown)
    st.markdown(f'<div style="margin-top:4px">{cards_html}</div>', unsafe_allow_html=True)

    # download
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    workbook = ExportService().to_workbook_bytes(results, summary)
    st.download_button(
        "⬇  Download results (.xlsx)",
        data=workbook,
        file_name="jobsy_matches.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    main()

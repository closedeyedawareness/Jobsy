"""
jobsy/ui/app.py

Streamlit front end for Jobsy.  Run with:

    streamlit run jobsy/ui/app.py

Paste job titles (or upload a CSV/XLSX), match them against the reference
library, review the results, and download a formatted workbook.

Data source:
  * Reference workbook  - the real catalog, loaded from the path in config.
  * Built-in sample      - a small in-memory catalog so the app runs before the
                           Excel library is in place. Great for a quick look.

This expects the enhanced Catalog to be saved as jobsy/core/catalog.py. The
sample mode has no such dependency, so the app still launches without it.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from core.config import COUNTRY, DEFAULT_THRESHOLD, WORKBOOK_PATH
except ImportError:
    COUNTRY, DEFAULT_THRESHOLD, WORKBOOK_PATH = 'NL', 85, 'reference_library.xlsx'
from core.repository import Repository
from services.export_service import ExportService
from services.matching_service import MatchingService

PRIMARY = "#0E7C66"


# --------------------------------------------------------------------- styling
def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Mono:wght@500&display=swap');
        h1, h2, h3 {{ font-family: 'Fraunces', serif; letter-spacing: -0.01em; }}
        .stApp [data-testid="stMetricValue"] {{ font-family: 'IBM Plex Mono', monospace; }}
        .jobsy-tag {{
            display:inline-block; font-family:'IBM Plex Mono',monospace; font-size:11px;
            letter-spacing:.14em; text-transform:uppercase; color:{PRIMARY};
            border:1px solid {PRIMARY}33; background:{PRIMARY}14; border-radius:999px;
            padding:3px 10px; margin-left:8px; vertical-align:middle;
        }}
        .stage {{ font-family:'IBM Plex Mono',monospace; font-size:11px; padding:2px 8px;
            border-radius:6px; margin-right:4px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------- sample data
class _SampleCatalog:
    """Minimal in-memory catalog satisfying what MatchingService needs."""

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
            ("J-HRA", "HR Advisor", "HR", "Medior"),
            ("J-HRBP", "HR Business Partner", "HR", "Senior"),
            ("J-REC", "Recruiter", "HR", "Medior"),
            ("J-ACC", "Accountant", "Finance", "Medior"),
            ("J-FC", "Financial Controller", "Finance", "Senior"),
            ("J-JSE", "Junior Software Engineer", "Engineering", "Junior"),
            ("J-SE", "Software Engineer", "Engineering", "Medior"),
            ("J-SSE", "Senior Software Engineer", "Engineering", "Senior"),
            ("J-DA", "Data Analyst", "Data", "Medior"),
            ("J-PM", "Product Manager", "Product", "Senior"),
        ]
        profiles = {
            "J-HRA": "Advises managers and employees on policy, Dutch labour law, and casework.",
            "J-HRBP": "Partners with senior leaders on workforce planning and people strategy.",
            "J-REC": "Runs hiring end-to-end: sourcing, screening, interviewing, and offer.",
            "J-ACC": "Maintains the ledger and prepares statutory, audit-ready accounts.",
            "J-FC": "Owns the close, financial reporting, and the internal control framework.",
            "J-JSE": "Ships well-scoped features with guidance from senior engineers.",
            "J-SE": "Designs and builds features across the stack with little supervision.",
            "J-SSE": "Leads technical design on complex systems and mentors engineers.",
            "J-DA": "Turns raw data into dashboards and insight that inform decisions.",
            "J-PM": "Defines product direction and aligns delivery with user needs.",
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
            "jobs": pd.DataFrame(jobs, columns=["JobID", "StandardTitle", "Function", "Level"]),
            "profiles": pd.DataFrame(
                [{"JobID": k, "Description": v} for k, v in profiles.items()]
            ),
            "titles": pd.DataFrame(mapping, columns=["ExistingTitle", "JobID"]),
            "salary": pd.DataFrame(salary, columns=["Function", "Level", "Min", "Max"]),
            "career": pd.DataFrame([{"JobID": j[0]} for j in jobs]),
            "levels": pd.DataFrame(
                [{"Level": x} for x in ("Junior", "Medior", "Senior", "Lead")]
            ),
            "employees": pd.DataFrame([{"EmployeeID": "1", "Name": "-", "CurrentTitle": "-"}]),
        }


# ------------------------------------------------------------------- loaders
@st.cache_resource(show_spinner="Loading reference library...")
def load_workbook_catalog(path: str):
    from core.catalog import Catalog  # lazy: sample mode needs no catalog.py

    catalog = Catalog(path)
    catalog.load()
    return catalog


@st.cache_resource(show_spinner="Building sample catalog...")
def load_sample_catalog():
    return _SampleCatalog()


# ------------------------------------------------------------------- helpers
def results_table(results) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Input": r.input_title,
                "Matched role": r.standard_title or "—",
                "Function": r.function or "—",
                "Level": r.level or "—",
                "Type": r.match_type.value,
                "Confidence": int(r.confidence),
                "Review": bool(r.requires_review),
                "Salary min": r.salary_min,
                "Salary max": r.salary_max,
            }
            for r in results
        ]
    )


STAGE_COLORS = {
    "exact": "#0E7C66", "normalized": "#2B5FA6", "synonym": "#6A53B0",
    "fuzzy": "#B9791A", "none": "#A8443A",
}


def stage_badge(match_type: str) -> str:
    color = STAGE_COLORS.get(match_type, "#5E6E7C")
    return f'<span class="stage" style="background:{color}1A;color:{color}">{match_type}</span>'


# ---------------------------------------------------------------------- app
def main() -> None:
    st.set_page_config(page_title="Jobsy", page_icon="📊", layout="centered")
    inject_css()

    st.markdown(
        f"# Jobsy <span class='jobsy-tag'>{COUNTRY} · V1</span>", unsafe_allow_html=True
    )
    st.caption("Resolve messy job titles to standard roles, profiles, and salary ranges.")

    # ---- sidebar -------------------------------------------------------
    with st.sidebar:
        st.subheader("Data source")
        source = st.radio(
            "Source", ["Built-in sample", "Reference workbook"], label_visibility="collapsed"
        )
        if source == "Reference workbook":
            path = st.text_input("Workbook path", value=WORKBOOK_PATH)
        st.divider()
        st.subheader("Matching")
        threshold = st.slider("Review below confidence", 50, 100, int(DEFAULT_THRESHOLD))
        enable_fuzzy = st.checkbox("Enable fuzzy stage (RapidFuzz)", value=True)
        st.divider()

    # ---- load catalog --------------------------------------------------
    try:
        if source == "Built-in sample":
            catalog = load_sample_catalog()
        else:
            if not Path(path).exists():
                st.warning(f"Workbook not found at `{path}`. Switch to the sample to explore.")
                st.stop()
            catalog = load_workbook_catalog(path)
    except Exception as exc:
        st.error(f"Could not load the catalog: {exc}")
        st.stop()

    stats = catalog.repository.statistics()
    with st.sidebar:
        st.subheader("Library")
        st.metric("Roles", stats["jobs"])
        st.caption(
            f"{stats['title_mappings']} title mappings · {stats['salary_bands']} salary bands · "
            f"{stats['functions']} functions"
        )

    service = MatchingService(
        catalog,
        review_threshold=threshold,
        enable_fuzzy=enable_fuzzy,
    )

    # ---- input ---------------------------------------------------------
    tab_paste, tab_upload = st.tabs(["Paste titles", "Upload file"])
    titles: list[str] = []

    with tab_paste:
        raw = st.text_area(
            "One title per line",
            value="HRBP\nhr business partner\nJunior Developer\nController\nBoekhouder\nSofware Enginer\nUnderwater Basket Weaver",
            height=170,
        )
        if st.button("Match titles", type="primary"):
            titles = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    with tab_upload:
        upload = st.file_uploader("CSV or Excel of titles", type=["csv", "xlsx"])
        if upload is not None:
            df_in = pd.read_csv(upload) if upload.name.endswith(".csv") else pd.read_excel(upload)
            column = st.selectbox("Which column holds the titles?", list(df_in.columns))
            if st.button("Match column", type="primary"):
                titles = df_in[column].fillna("").astype(str).tolist()

    if not titles:
        st.info("Add some titles and run a match to see results.")
        return

    # ---- run -----------------------------------------------------------
    results = service.match_titles(titles)
    summary = service.summarize(results)

    cols = st.columns(5)
    cols[0].metric("Total", summary.total)
    cols[1].metric("Matched", summary.matched)
    cols[2].metric("Review", summary.review)
    cols[3].metric("Unmatched", summary.unmatched)
    cols[4].metric("Avg conf", f"{summary.avg_confidence:.0f}%")

    table = results_table(results)
    only_review = st.checkbox("Show only titles needing review")
    view = table[table["Review"]] if only_review else table

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Confidence": st.column_config.ProgressColumn(
                "Confidence", min_value=0, max_value=100, format="%d%%"
            ),
            "Review": st.column_config.CheckboxColumn("Review"),
            "Salary min": st.column_config.NumberColumn("Salary min", format="€%d"),
            "Salary max": st.column_config.NumberColumn("Salary max", format="€%d"),
        },
    )

    # ---- detail --------------------------------------------------------
    with st.expander("Role detail", expanded=False):
        for r in results:
            if not r.matched:
                st.markdown(
                    f"**{r.input_title}** → _no match_ &nbsp; {stage_badge('none')}",
                    unsafe_allow_html=True,
                )
                continue
            salary = (
                f"€{int(r.salary_min):,} – €{int(r.salary_max):,}"
                if r.salary_range else "no band defined"
            )
            st.markdown(
                f"**{r.input_title}** → **{r.standard_title}** "
                f"&nbsp; {stage_badge(r.match_type.value)} "
                f"<span class='stage' style='background:#eef;color:#333'>{r.confidence}%</span>",
                unsafe_allow_html=True,
            )
            st.caption(f"{r.function} · {r.level} · {salary}")
            if r.description:
                st.write(r.description)
            st.divider()

    # ---- export --------------------------------------------------------
    workbook = ExportService().to_workbook_bytes(results, summary)
    st.download_button(
        "Download results (.xlsx)",
        data=workbook,
        file_name="jobsy_matches.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    main()

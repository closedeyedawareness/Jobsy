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
    from ui.theme import COLORS as THEME_COLORS, FONT as THEME_FONT, apply_theme
except ImportError:
    from jobsy.ui.theme import COLORS as THEME_COLORS, FONT as THEME_FONT, apply_theme

try:
    from ui.components import stat_card as ui_stat_card
except ImportError:
    try:
        from jobsy.ui.components import stat_card as ui_stat_card
    except ImportError:
        ui_stat_card = None

try:
    from core.config import COUNTRY, DEFAULT_THRESHOLD, WORKBOOK_PATH
except ImportError:
    COUNTRY, DEFAULT_THRESHOLD, WORKBOOK_PATH = "NL", 85, "jobsy_reference_library.xlsx"

try:
    from services.architecture_report_service import ArchitectureReportService
except ImportError:
    ArchitectureReportService = None

try:
    from services.afas_connector    import AfasConnector
    from services.workday_connector import WorkdayConnector
    _CONNECTORS_AVAILABLE = True
except ImportError:
    _CONNECTORS_AVAILABLE = False

try:
    from services.persistence_service import (
        is_available as _ps_available,
        generate_code as _ps_generate,
        save_session  as _ps_save,
        load_session  as _ps_load,
        status        as _ps_status,
        health_check  as _ps_health,
    )
except ImportError:
    def _ps_available(): return False
    def _ps_generate(): return ""
    def _ps_save(*a,**k): return False
    def _ps_load(*a,**k): return None
    def _ps_status(*a,**k): return None
    def _ps_health(*a,**k): return None

try:
    from ui.components import status_card, status_badge, info_tile
except ImportError:
    def status_card(*a,**k): return ""
    def status_badge(*a,**k): return ""
    def info_tile(*a,**k): return ""

from core.repository import Repository
from services.benefits_service import BenefitsService
from services.export_service import ExportService
from services.matching_service import MatchingService

# ── colours (centralised in ui/theme.py and mirrored in .streamlit/config.toml) ──
C = THEME_COLORS
STAGE_C = {
    "exact": C["success"],
    "normalized": C["secondary"],
    "synonym": C["accent"],
    "fuzzy": C["warning"],
    "none": C["danger"],
}
LEVEL_C = {
    "Junior": (C["surface2"], C["secondary"]),
    "Medior": (C["surface2"], C["success"]),
    "Senior": (C["surface2"], C["accent"]),
    "Lead": (C["surface2"], C["gold"]),
}
GMIN, GMAX = 30000, 140000

# ── fonts (centralised in ui/theme.py) ──
FONT_SERIF = THEME_FONT["serif"]
FONT_SANS  = THEME_FONT["sans"]
FONT_MONO  = THEME_FONT["mono"]

# ── font loader (link only — no <style> block) ─────────────────────────────

# ── Learning pathway recommendations per skill category + gap size ─────────
LEARNING_PATHWAYS = {
    "Technical": [
        (1, "Self-directed practice",      "Online course (Coursera/Udemy/freeCodeCamp) + hands-on side project",                     "1–2 months"),
        (2, "Structured learning",         "Intensive bootcamp or vendor cert prep + code-review pairing with senior",                "3–5 months"),
        (5, "Formal certification",        "AWS/Azure/GCP cert or language certification + dedicated senior engineering mentor",       "6–9 months"),
    ],
    "Data & Analytics": [
        (1, "Platform practice",           "DataCamp track or Kaggle competition + internal reporting project",                        "1–2 months"),
        (2, "Analytics programme",         "Google Data Analytics / dbt cert + build one live dashboard from scratch",                 "2–4 months"),
        (5, "Specialist certification",    "Data engineering or ML cert (Databricks/Snowflake/AWS MLS) + peer mentoring",              "4–7 months"),
    ],
    "Finance & Accounting": [
        (1, "Supervised practice",         "Internal study with senior + shadow month-end close",                                      "1–2 months"),
        (2, "Formal module",               "CIMA/ACCA module or financial modelling course (CFI/Wall St Prep) + hands-on project",     "3–5 months"),
        (5, "Professional qualification",  "CIMA/ACCA/RA (Register Accountant NL) qualification pathway",                             "6–18 months"),
    ],
    "Commercial": [
        (1, "Deal exposure",               "Shadow senior AE/CSM on 5+ live deals + review sales playbook",                           "1–2 months"),
        (2, "Sales methodology",           "SPIN Selling, Challenger, or MEDDPICC programme + field coaching sessions",                "2–3 months"),
        (5, "Commercial academy",          "Commercial leadership programme + executive deal coaching + stretch role in key account",   "4–6 months"),
    ],
    "Marketing & Digital": [
        (1, "Platform certification",      "Google Ads / Meta Blueprint / LinkedIn Marketing cert (free, 2–4 weeks)",                  "1 month"),
        (2, "Digital marketing course",    "CXL Institute or Reforge growth programme + run one live campaign",                        "2–3 months"),
        (5, "Full qualification",          "Recognised digital marketing qualification + 3-month embedded agency or growth project",   "4–6 months"),
    ],
    "People & HR": [
        (1, "e-Learning",                  "HR Navigator / WFMD online modules + shadow an HR Advisor on casework",                   "1–2 months"),
        (2, "CIPD / HR Academy module",    "CIPD Level 3/5 module or HR Academy Nederland programme + supervised case ownership",      "3–5 months"),
        (5, "Professional qualification",  "CIPD Level 5/7, NVP register, or HR Academy NL advanced track",                           "6–12 months"),
    ],
    "Leadership": [
        (1, "Peer learning",               "Leadership reading (Start With Why, Radical Candor) + structured peer-coaching circle",    "1–2 months"),
        (2, "Management programme",        "External management development programme (e.g. Krauthammer NL) + executive coaching",     "3–6 months"),
        (5, "Senior leadership programme", "IMD / Nyenrode / Tias short executive programme + board-level mentoring",                  "6–12 months"),
    ],
    "Professional": [
        (1, "Internal workshop",           "Internal lunch-and-learn or e-learning + apply immediately in current role",               "2–4 weeks"),
        (2, "External course",             "Targeted external course (e.g. PM, risk, compliance) + project application",              "2–3 months"),
        (5, "Certification / programme",   "Recognised certification (PMP, PRINCE2, ISO, CIPP) + structured mentoring",               "3–6 months"),
    ],
}

def _get_pathway(skill_category, gap_size):
    """Return (action, method, duration) for a skill category and gap size."""
    cat = next((c for c in LEARNING_PATHWAYS if skill_category.startswith(c) or c.startswith(skill_category.split()[0])), "Professional")
    for max_gap, action, method, duration in LEARNING_PATHWAYS[cat]:
        if gap_size <= max_gap:
            return action, method, duration
    last = LEARNING_PATHWAYS[cat][-1]
    return last[1], last[2], last[3]

def _pathway_html(gap):
    """Collapsible learning pathway section for a single skill gap."""
    if gap["gap"] <= 0:
        return ""
    action, method, duration = _get_pathway(gap.get("category","Professional"), gap["gap"])
    return (
        f'<div style="margin-top:8px;padding:10px 12px;background:#F8FAFB;'
        f'border:1px solid {C["line"]};border-radius:8px">'
        f'<div style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.1em;'
        f'text-transform:uppercase;color:{C["teal"]};margin-bottom:5px">Development pathway</div>'
        f'<div style="font-family:{FONT_SANS};font-size:12.5px;font-weight:600;color:{C["ink"]};margin-bottom:3px">{action}</div>'
        f'<div style="font-family:{FONT_SANS};font-size:12px;color:#34424F;line-height:1.45;margin-bottom:5px">{method}</div>'
        f'<div style="display:flex;align-items:center;gap:6px">'
        f'<span style="font-family:{FONT_MONO};font-size:10px;background:{C["teal"]}1A;'
        f'color:{C["teal"]};border-radius:6px;padding:2px 8px">⏱ {duration}</span>'
        f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]}">Gap +{gap["gap"]} level{"s" if gap["gap"]!=1 else ""}</span>'
        f'</div></div>'
    )



# ── Short skill name → reference library SkillName mapping ────────────────
# Covers abbreviated names from real HR systems and datasets
SKILL_ALIASES = {
    # Leadership & management
    "leadership":          "Team leadership and development",
    "team leadership":     "Team leadership and development",
    "people leadership":   "Team leadership and development",
    "management":          "Team leadership and development",
    "performance":         "Performance management",
    "performance management": "Performance management",
    "coaching":            "Coaching and mentoring",
    "mentoring":           "Coaching and mentoring",
    "coach":               "Coaching and mentoring",
    "change management":   "Change management",
    "change":              "Change management",
    "org design":          "Organisational design",
    "organisational design": "Organisational design",
    "strategy":            "Strategic planning",
    "strategic planning":  "Strategic planning",
    "strategic":           "Strategic planning",
    "vision":              "Strategic planning",
    "stakeholder":         "Stakeholder management",
    "stakeholder management": "Stakeholder management",
    "influence":           "Stakeholder management",
    "influencing":         "Stakeholder management",
    "board":               "Board and executive advisory",
    "governance":          "Board and executive advisory",
    "executive":           "Board and executive advisory",
    "budget":              "Budget and resource management",
    "budgeting":           "Budget and resource management",
    "resource management": "Budget and resource management",
    # Technical
    "python":              "Python programming",
    "javascript":          "JavaScript and TypeScript",
    "typescript":          "JavaScript and TypeScript",
    "js":                  "JavaScript and TypeScript",
    "sql":                 "SQL and database querying",
    "database":            "SQL and database querying",
    "querying":            "SQL and database querying",
    "git":                 "Git and version control",
    "version control":     "Git and version control",
    "tdd":                 "Test-driven development",
    "testing":             "Test-driven development",
    "api":                 "API design and integration",
    "api design":          "API design and integration",
    "architecture":        "System and solution architecture",
    "system architecture": "System and solution architecture",
    "solution architecture": "System and solution architecture",
    "cloud":               "Cloud infrastructure",
    "aws":                 "Cloud infrastructure",
    "azure":               "Cloud infrastructure",
    "gcp":                 "Cloud infrastructure",
    "infrastructure":      "Cloud infrastructure",
    "iac":                 "Infrastructure as code",
    "terraform":           "Infrastructure as code",
    "kubernetes":          "Container orchestration",
    "docker":              "Container orchestration",
    "containers":          "Container orchestration",
    "ci/cd":               "CI/CD pipeline engineering",
    "cicd":                "CI/CD pipeline engineering",
    "devops":              "CI/CD pipeline engineering",
    "frontend":            "Frontend development",
    "react":               "Frontend development",
    "vue":                 "Frontend development",
    "cybersecurity":       "Security engineering",
    "security":            "Security engineering",
    # Data & analytics
    "data analysis":       "Data analysis and visualisation",
    "analytics":           "Data analysis and visualisation",
    "analysis":            "Data analysis and visualisation",
    "visualisation":       "Data analysis and visualisation",
    "visualization":       "Data analysis and visualisation",
    "statistics":          "Statistical modelling",
    "statistical":         "Statistical modelling",
    "machine learning":    "Machine learning and AI",
    "ml":                  "Machine learning and AI",
    "ai":                  "Machine learning and AI",
    "data engineering":    "Data pipeline engineering",
    "etl":                 "Data pipeline engineering",
    "pipelines":           "Data pipeline engineering",
    "bi":                  "Business intelligence",
    "business intelligence": "Business intelligence",
    "excel":               "Excel and spreadsheet modelling",
    "spreadsheet":         "Excel and spreadsheet modelling",
    "microsoft 365":       "Excel and spreadsheet modelling",
    "power bi":            "Power BI or Tableau",
    "tableau":             "Power BI or Tableau",
    "looker":              "Power BI or Tableau",
    "dashboards":          "Power BI or Tableau",
    "ab testing":          "A/B testing and experimentation",
    "experimentation":     "A/B testing and experimentation",
    "data governance":     "Data governance and quality",
    "accuracy":            "Data governance and quality",
    "data quality":        "Data governance and quality",
    "product analytics":   "Product and user analytics",
    # Finance
    "bookkeeping":         "Bookkeeping and ledger management",
    "accounting":          "Bookkeeping and ledger management",
    "ledger":              "Bookkeeping and ledger management",
    "financial reporting": "Financial reporting",
    "ifrs":                "Financial reporting",
    "gaap":                "Financial reporting",
    "finance":             "Financial reporting",
    "reporting":           "Financial reporting",
    "financial planning":  "Budgeting and financial planning",
    "planning":            "Budgeting and financial planning",
    "financial modelling": "Financial modelling",
    "modelling":           "Financial modelling",
    "corporate finance":   "Financial modelling",
    "tax":                 "Tax compliance",
    "vat":                 "Tax compliance",
    "btw":                 "Tax compliance",
    "audit":               "Audit coordination",
    "treasury":            "Treasury and cash management",
    "cash":                "Treasury and cash management",
    "management accounts": "Management accounting",
    "management accounting": "Management accounting",
    "sap":                 "Management accounting",
    # Commercial
    "sales":               "Sales prospecting and pipeline",
    "prospecting":         "Sales prospecting and pipeline",
    "pipeline":            "Sales prospecting and pipeline",
    "account management":  "Account management",
    "accounts":            "Account management",
    "crm":                 "Account management",
    "negotiation":         "Commercial negotiation",
    "deals":               "Commercial negotiation",
    "business development": "Business development",
    "biz dev":             "Business development",
    "bd":                  "Business development",
    "go-to-market":        "Go-to-market planning",
    "gtm":                 "Go-to-market planning",
    "forecasting":         "Revenue forecasting",
    "revenue":             "Revenue forecasting",
    "customer success":    "Customer success management",
    "cs":                  "Customer success management",
    "csm":                 "Customer success management",
    "pricing":             "Pricing and monetisation",
    "monetisation":        "Pricing and monetisation",
    "tender":              "Tender and bid management",
    "bids":                "Tender and bid management",
    # Marketing
    "seo":                 "SEO and search marketing",
    "search marketing":    "SEO and search marketing",
    "paid media":          "Digital advertising",
    "google ads":          "Digital advertising",
    "digital advertising": "Digital advertising",
    "email marketing":     "Email marketing and automation",
    "email":               "Email marketing and automation",
    "content":             "Content strategy and creation",
    "copywriting":         "Content strategy and creation",
    "brand":               "Brand management",
    "branding":            "Brand management",
    "web analytics":       "Web and campaign analytics",
    "ga4":                 "Web and campaign analytics",
    "social media":        "Social media management",
    "social":              "Social media management",
    "campaigns":           "Marketing campaign management",
    "campaign management": "Marketing campaign management",
    # HR
    "labour law":          "Dutch labour law",
    "employment law":      "Dutch labour law",
    "dutch law":           "Dutch labour law",
    "hr policy":           "HR policy and compliance",
    "policy":              "HR policy and compliance",
    "compliance":          "HR policy and compliance",
    "talent management":   "Talent management and succession",
    "succession":          "Talent management and succession",
    "talent":              "Talent management and succession",
    "workforce planning":  "Workforce planning",
    "people strategy":     "Workforce planning",
    "headcount":           "Workforce planning",
    "employee relations":  "Employee relations and casework",
    "er":                  "Employee relations and casework",
    "casework":            "Employee relations and casework",
    "compensation":        "Compensation and benefits",
    "benefits":            "Compensation and benefits",
    "total rewards":       "Compensation and benefits",
    "hris":                "HRIS and HR administration",
    "hr systems":          "HRIS and HR administration",
    "recruitment":         "Recruitment and employer branding",
    "hiring":              "Recruitment and employer branding",
    "talent acquisition":  "Recruitment and employer branding",
    "employer branding":   "Recruitment and employer branding",
    # Professional
    "project management":  "Project management",
    "projects":            "Project management",
    "pm":                  "Project management",
    "process improvement": "Process improvement",
    "lean":                "Process improvement",
    "six sigma":           "Process improvement",
    "risk management":     "Risk and compliance management",
    "risk":                "Risk and compliance management",
    "communication":       "Written and verbal communication",
    "presentation":        "Written and verbal communication",
    "writing":             "Written and verbal communication",
    "teamwork":            "Written and verbal communication",
    "data driven":         "Data-driven decision making",
    "decision making":     "Data-driven decision making",
    "problem solving":     "Problem structuring and solving",
    "problem-solving":     "Problem structuring and solving",
    "innovation":          "Problem structuring and solving",
    "adaptability":        "Change management",
    "gdpr":                "GDPR and data privacy",
    "privacy":             "GDPR and data privacy",
    "avg":                 "GDPR and data privacy",
    "contracts":           "Contract and legal advisory",
    "legal":               "Contract and legal advisory",
    "requirements":        "Requirements analysis",
    "customer focus":      "Customer success management",
    "regulatory":          "Regulatory compliance",
}

def _resolve_skill_name(raw_name, skill_name_to_id):
    """Map a raw/short skill name to a reference library skill ID."""
    raw = raw_name.strip().lower()
    # 1. exact match in reference library
    if raw in skill_name_to_id:
        return skill_name_to_id[raw]
    # 2. alias lookup
    alias_target = SKILL_ALIASES.get(raw)
    if alias_target and alias_target.lower() in skill_name_to_id:
        return skill_name_to_id[alias_target.lower()]
    # 3. partial match — raw is a substring of a skill name
    for sk_name, sk_id in skill_name_to_id.items():
        if raw in sk_name or sk_name in raw:
            return sk_id
    return None

LEVEL_TEXT_MAP = {
    "awareness":1,"beginner":1,"novice":1,"basic":1,
    "developing":2,"learning":2,"intermediate":2,"foundation":2,
    "proficient":3,"competent":3,"skilled":3,"practiced":3,
    "advanced":4,"experienced":4,"strong":4,"senior":4,
    "expert":5,"master":5,"authority":5,"distinguished":5,
    "1":1,"2":2,"3":3,"4":4,"5":5,
}


def load_fonts():
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&'
        'family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )

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

    def get_role_skills(self, job_id):
        reqs = self.repository.role_skill_map.get(job_id, [])
        return [(req, self.repository.skills[req.skill_id])
                for req in reqs if req.skill_id in self.repository.skills]

    def skill_gap(self, current_skills, target_job_id):
        gaps = []
        for req, skill in self.get_role_skills(target_job_id):
            current = current_skills.get(req.skill_id, 0)
            gap = req.required_level - current
            gaps.append({"skill_id":req.skill_id,"skill_name":skill.skill_name,
                "category":skill.category,"skill_type":req.skill_type,
                "required_level":req.required_level,"current_level":current,
                "gap":gap,"status":"gap" if gap>0 else("match" if gap==0 else"exceeds")})
        return sorted(gaps, key=lambda g:(-g["gap"],g["skill_type"]))

    def competency_level_name(self, level):
        NAMES={1:"Awareness",2:"Developing",3:"Proficient",4:"Advanced",5:"Expert"}
        cl=self.repository.competency_levels.get(level)
        return cl.name if cl else NAMES.get(level, str(level))

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
def _workbook_sig(path):
    """A cheap fingerprint of the workbook so the cache busts when it changes."""
    import os
    try:
        s = os.stat(path)
        return f"{int(s.st_mtime)}-{s.st_size}"
    except OSError:
        return "missing"


@st.cache_resource(show_spinner="Loading reference library…")
def load_workbook_catalog(path, sig=None):
    # `sig` only participates in the cache key: when the workbook file changes,
    # sig changes and Streamlit rebuilds the catalog instead of serving a stale one.
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
        '<h1 class="jobsy-v3-title">Jobsy</h1>'
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


def render_workspace_anchor() -> None:
    """Anchor used by hero quick actions."""
    st.markdown('<div id="workspace"></div>', unsafe_allow_html=True)


def render_getting_started() -> None:
    """A 3-step orientation + page guide for first-time business users."""
    steps = [
        ("1", "Standardise", "Paste or upload job titles below — Jobsy matches them to canonical roles with salary, grade and skills."),
        ("2", "Analyse", "Explore pay & levels (Job Family), pay equity/compa-ratio (Pay Equity), and capability (Skills, Skill Gap, 9-Box)."),
        ("3", "Report", "Generate a board-ready Excel (Architecture Report) and keep the library clean (Data Quality)."),
    ]
    cards = "".join(
        f'<div style="flex:1;min-width:190px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-radius:12px;padding:14px 16px">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
        f'<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;'
        f'border-radius:50%;background:{C["teal"]};color:#fff;font-family:{FONT_MONO};font-size:12px;font-weight:700">{n}</span>'
        f'<span style="font-family:{FONT_SANS};font-weight:700;font-size:14px;color:{C["ink"]}">{t}</span></div>'
        f'<div style="font-size:12.5px;color:{C["muted"]};line-height:1.5">{d}</div></div>'
        for n, t, d in steps)
    st.markdown(
        f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{C["muted"]};margin:6px 0 8px">How Jobsy works</div>'
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

def _stat_card(value, label, color=C["ink"]):
    if ui_stat_card is not None:
        return ui_stat_card(value, label, color)
    return (f'<div style="flex:1;background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:14px;padding:14px 10px;text-align:center;'
            f'box-shadow:0 1px 2px rgba(23,33,46,.04),0 8px 24px -16px rgba(23,33,46,.28)">'
            f'<div style="font-family:{FONT_MONO};font-weight:600;font-size:26px;'
            f'line-height:1;color:{color}">{value}</div>'
            f'<div style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["muted"]};margin-top:5px">{label}</div>'
            f'</div>')

# ── main ───────────────────────────────────────────────────────────────────

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




def connect_page():
    """Live data connection — AFAS Profit or Workday."""
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Live Connection</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Pull employee data directly from AFAS Profit or Workday. '
        f'Credentials are session-only and never stored.</p>',
        unsafe_allow_html=True,
    )

    if not _CONNECTORS_AVAILABLE:
        st.error("Connector modules not found. Check `services/afas_connector.py` and `services/workday_connector.py` are uploaded.")
        return

    system = st.radio("System", ["AFAS Profit", "Workday"], horizontal=True, key="conn_system")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── AFAS ──────────────────────────────────────────────────────────────
    if system == "AFAS Profit":
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.1em;'
            f'text-transform:uppercase;color:{C["muted"]};margin-bottom:12px">'
            f'AFAS Profit REST API</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            env_id = st.text_input("Environment ID", placeholder="12345",
                                   help="The number before .rest.afas.online", key="afas_env")
            connector_name = st.text_input("Connector name", value="HrEmployee",
                                           help="GetConnector configured by your AFAS admin", key="afas_conn")
        with col2:
            token = st.text_input("API token", type="password",
                                  help="Generate in AFAS → App Connector → REST services", key="afas_token")
            max_rows = st.number_input("Max employees to fetch", value=500, min_value=10, max_value=5000, step=100)

        st.caption("Your token is masked and exists only in this browser session.")

        col_test, col_fetch = st.columns(2)
        with col_test:
            if st.button("Test connection", key="afas_test"):
                if not env_id or not token:
                    st.warning("Enter Environment ID and Token first.")
                else:
                    with st.spinner("Testing..."):
                        conn = AfasConnector(env_id, token)
                        ok, msg = conn.test_connection()
                    if ok:
                        st.success(f"✓ Connected to AFAS environment {env_id}")
                        connectors = conn.list_connectors()
                        if connectors:
                            st.caption(f"Available connectors: {', '.join(connectors[:10])}")
                    else:
                        st.error(f"Connection failed: {msg}")

        with col_fetch:
            if st.button("Fetch employees", type="primary", key="afas_fetch"):
                if not env_id or not token:
                    st.warning("Enter credentials first.")
                else:
                    with st.spinner(f"Fetching from {connector_name}…"):
                        try:
                            conn = AfasConnector(env_id, token)
                            df = conn.fetch_employees(connector_name=connector_name, take=min(1000, max_rows))
                            if df.empty:
                                st.warning("No data returned. Check the connector name.")
                            else:
                                st.session_state["upload_df"]       = df
                                st.session_state["upload_title_col"] = _detect_col(df, ["JobTitle","Functieomschrijving","functie"])
                                st.session_state["upload_name_col"]  = None
                                st.success(f"✓ Fetched **{len(df)} employees** from AFAS. Switch to Matching to run analysis.")
                                st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                        except Exception as exc:
                            st.error(f"Fetch failed: {exc}")

    # ── Workday ───────────────────────────────────────────────────────────
    else:
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.1em;'
            f'text-transform:uppercase;color:{C["muted"]};margin-bottom:12px">'
            f'Workday REST API</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            tenant    = st.text_input("Tenant name", placeholder="acme_corp", key="wd_tenant")
            client_id = st.text_input("Client ID", key="wd_client_id")
        with col2:
            client_secret = st.text_input("Client secret", type="password", key="wd_secret")
            refresh_token = st.text_input("Refresh token", type="password", key="wd_refresh")

        use_raas = st.checkbox("Use Custom Report (RaaS) instead of REST workers endpoint", key="wd_raas")
        raas_name = ""
        if use_raas:
            raas_name = st.text_input("Report name", placeholder="Jobsy_Worker_Extract", key="wd_raas_name",
                                       help="Report name configured by your Workday admin")

        st.caption("Credentials are masked and exist only in this browser session.")

        col_test, col_fetch = st.columns(2)
        with col_test:
            if st.button("Test connection", key="wd_test"):
                if not all([tenant, client_id, client_secret, refresh_token]):
                    st.warning("Fill in all credential fields first.")
                else:
                    with st.spinner("Authenticating…"):
                        conn = WorkdayConnector(tenant, client_id, client_secret, refresh_token)
                        ok, msg = conn.test_connection()
                    st.success(f"✓ Connected to Workday tenant {tenant}") if ok else st.error(f"Failed: {msg}")

        with col_fetch:
            if st.button("Fetch workers", type="primary", key="wd_fetch"):
                if not all([tenant, client_id, client_secret, refresh_token]):
                    st.warning("Fill in all credential fields first.")
                else:
                    with st.spinner("Fetching workers…"):
                        try:
                            conn = WorkdayConnector(tenant, client_id, client_secret, refresh_token)
                            df = (conn.fetch_workers_raas(raas_name) if use_raas and raas_name
                                  else conn.fetch_workers())
                            if df.empty:
                                st.warning("No data returned. Check credentials and API access.")
                            else:
                                st.session_state["upload_df"]       = df
                                st.session_state["upload_title_col"] = _detect_col(df, ["JobTitle","job_title","businessTitle"])
                                st.session_state["upload_name_col"]  = None
                                st.success(f"✓ Fetched **{len(df)} workers** from Workday. Switch to Matching.")
                                st.dataframe(df.head(5), use_container_width=True, hide_index=True)
                        except Exception as exc:
                            st.error(f"Fetch failed: {exc}")


def _detect_col(df, candidates):
    """Return the first candidate column name found in df."""
    for c in candidates:
        if c in df.columns:
            return c
    return df.columns[0] if len(df.columns) > 0 else ""


def _smart_detect(cols, exacts, contains):
    """Pick a column by case-insensitive exact match first, then substring.

    Robust to non-string / numeric headers (uses str(c)). Returns None if
    nothing matches so callers can supply their own fallback.
    """
    low = [(c, str(c).strip().lower()) for c in cols]
    for c, l in low:
        if l in exacts:
            return c
    for kw in contains:
        for c, l in low:
            if kw in l:
                return c
    return None


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


def architecture_report_page(catalog):
    """Generate a board-ready Job Architecture Framework report."""
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Architecture Report</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Generate a board-ready Job Architecture Framework with grading, '
        f'pay equity, succession risk, and strategic recommendations.</p>',
        unsafe_allow_html=True,
    )
    if ArchitectureReportService is None:
        st.error("architecture_report_service.py not found in services/")
        return

    results  = st.session_state.get("last_results", [])
    df_input = st.session_state.get("upload_df")

    if not results:
        st.info("Upload a file and run a match on the Matching page first.")
        return

    matched = [r for r in results if r.matched]
    lead_c  = sum(1 for r in matched if r.level=="Lead")
    fns     = len({r.function for r in matched})

    st.markdown(
        f'<div style="display:flex;gap:10px;margin-bottom:16px">'
        f'{_stat_card(len(matched),"Employees")}{_stat_card(fns,"Functions",C["blue"])}'
        f'{_stat_card(lead_c,"Lead roles",C["violet"])}</div>',
        unsafe_allow_html=True,
    )

    org_label = st.text_input("Organisation name for the report",
                               value=st.session_state.get("org_label","Organisation"),
                               key="arch_org_label")

    st.markdown(
        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};margin:12px 0 8px">'
        f'Report includes 7 sections: Executive Summary · Job Architecture · Org Snapshot · '
        f'Grade Distribution · Career Paths · Succession Risk · Recommendations</div>',
        unsafe_allow_html=True,
    )

    if st.button("Generate Architecture Report", type="primary", use_container_width=True):
        with st.spinner("Analysing organisation and generating report…"):
            try:
                svc = ArchitectureReportService(
                    catalog=catalog,
                    results=results,
                    df_employees=df_input,
                    org_label=org_label,
                )
                report_bytes = svc.generate()
                import re
                safe_label = re.sub(r"[^a-zA-Z0-9_-]","_", org_label)[:30]
                from datetime import date
                fname = f"Jobsy_Architecture_Report_{safe_label}_{date.today().strftime('%Y%m%d')}.xlsx"
                st.success("✓ Report generated. Download below.")
                st.download_button(
                    "⬇  Download Architecture Report (.xlsx)",
                    data=report_bytes,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except Exception as exc:
                import traceback
                st.error(f"Report generation failed: {exc}")
                with st.expander("Details"):
                    st.code(traceback.format_exc())


@st.cache_data(show_spinner=False)
def _family_frames(path):
    import pandas as _pd
    return _pd.read_excel(path, sheet_name=["Jobs", "SalaryBands", "JobGrades", "JobProfiles", "PayMix"], dtype=str)


def job_family_page(catalog):
    """Leveling grid + pay range for a job family (function), Mercer/Hay style."""
    import pandas as _pd
    import altair as _alt

    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Job Family</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'A leveling grid and pay range for a job family — every role by level, with grade, '
        f'salary band and what changes as you move up the ladder.</p>',
        unsafe_allow_html=True,
    )
    try:
        fr = _family_frames(WORKBOOK_PATH)
    except Exception as exc:
        st.warning(f"Job Family needs the reference workbook. ({exc})")
        return

    jobs = fr["Jobs"].copy(); bands = fr["SalaryBands"].copy()
    grades = fr["JobGrades"].copy(); profs = fr["JobProfiles"].copy()
    jobs["Grade"] = _pd.to_numeric(jobs.get("Grade"), errors="coerce")
    for _c in ("Grade", "Min", "P25", "P50", "P75", "Max"):
        if _c in bands: bands[_c] = _pd.to_numeric(bands[_c], errors="coerce")
    grades["Grade"] = _pd.to_numeric(grades.get("Grade"), errors="coerce")

    funcs = sorted(jobs["Function"].dropna().unique())
    if not funcs:
        st.info("No roles found."); return
    fsel = st.selectbox("Job family", funcs,
                        index=funcs.index("Engineering") if "Engineering" in funcs else 0)

    fam = jobs[jobs["Function"] == fsel].dropna(subset=["Grade"]).sort_values("Grade")
    if fam.empty:
        st.info("No roles in this family."); return

    bmap = {(r["Function"], r["Level"]): r for _, r in bands.iterrows()}
    gmap = {r["Grade"]: r for _, r in grades.iterrows()}
    pmap = {r["JobID"]: r for _, r in profs.iterrows()}
    pay = fr.get("PayMix")
    if pay is not None:
        for _c in ("TargetVariablePct", "ThirteenthMonthPct"):
            if _c in pay: pay[_c] = _pd.to_numeric(pay[_c], errors="coerce")
    xmap = {(r["Function"], r["Level"]): r for _, r in pay.iterrows()} if pay is not None else {}

    def _euro0(v):
        try: return "€{:,.0f}".format(float(v)).replace(",", ".")
        except Exception: return "—"
    def _cell(v, n=170):
        s = "" if v is None else str(v)
        if not s or s.lower() == "nan": return "—"
        s = s.replace(";", " · ")
        return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"
    def _skills_for(jid):
        try:
            names = [sk.skill_name for _, sk in catalog.get_role_skills(jid)[:3]]
            return " · ".join(names) if names else "—"
        except Exception:
            return "—"

    cols = []
    for role in fam.itertuples(index=False):
        jid = getattr(role, "JobID"); lvl = getattr(role, "Level"); fn = getattr(role, "Function")
        b = bmap.get((fn, lvl)); g = gmap.get(getattr(role, "Grade")); p = pmap.get(jid)
        x = xmap.get((fn, lvl))
        base = b.get("P50") if b is not None else None
        base = None if (base is None or _pd.isna(base)) else float(base)
        var_pct = float(x.get("TargetVariablePct") or 0) if x is not None else 0.0
        th_pct  = float(x.get("ThirteenthMonthPct") or 0) if x is not None else 0.0
        if base is not None:
            hol = base * 0.08; m13 = base * th_pct / 100; varamt = base * var_pct / 100
            ttc = base + hol + m13 + varamt
            pens = base * 0.12; ben = 2000.0; treward = ttc + pens + ben
        else:
            hol = m13 = varamt = ttc = pens = ben = treward = None
        cols.append({
            "title": _cell(getattr(role, "StandardTitle"), 60), "level": _cell(lvl, 20),
            "code": _cell(jid, 20), "grade": _cell(getattr(role, "Grade"), 6),
            "band": (f'{_euro0(b.get("Min"))} – {_euro0(b.get("Max"))}' if b is not None else "—"),
            "med": (_euro0(b.get("P50")) if b is not None else "—"),
            "hol": (_euro0(hol) if hol is not None else "—"),
            "m13": (f'{_euro0(m13)} ({th_pct:.2f}%)' if (m13 is not None and th_pct) else "—"),
            "var": (f'{_euro0(varamt)} ({var_pct:.0f}%)' if (varamt is not None and var_pct) else "—"),
            "ttc": (_euro0(ttc) if ttc is not None else "—"),
            "pens": (_euro0(pens) if pens is not None else "—"),
            "ben": (_euro0(ben) if ben is not None else "—"),
            "treward": (_euro0(treward) if treward is not None else "—"),
            "lti": ((x.get("LTIEligible") if x is not None else None) or "—"),
            "knowledge": _cell(g.get("Scope") if g is not None else None),
            "problem": _cell(g.get("Complexity") if g is not None else None),
            "account": _cell(g.get("DecisionRights") if g is not None else None),
            "lead": _cell(g.get("Leadership") if g is not None else None, 60),
            "skills": _skills_for(jid),
        })

    def _th(c):
        return (f'<th style="min-width:200px;text-align:left;padding:10px 12px;'
                f'background:{C["teal"]};color:#fff;border:1px solid {C["line"]}">'
                f'<div style="font-family:{FONT_SANS};font-weight:700;font-size:13px">{c["title"]}</div>'
                f'<div style="font-family:{FONT_MONO};font-size:10px;opacity:.85;margin-top:2px">'
                f'{c["level"]} · {c["code"]}</div></th>')
    def _row(label, key, mono=False):
        cells = "".join(
            f'<td style="padding:9px 12px;border:1px solid {C["line"]};vertical-align:top;'
            f'font-size:12px;color:{C["ink"]};{"font-family:"+FONT_MONO+";" if mono else ""}">'
            f'{c[key]}</td>' for c in cols)
        return (f'<tr><td style="padding:9px 12px;border:1px solid {C["line"]};'
                f'background:{C["surface"]};font-family:{FONT_MONO};font-size:11px;'
                f'color:{C["muted"]};white-space:nowrap">{label}</td>{cells}</tr>')

    grid = (
        f'<div style="overflow-x:auto;border-radius:12px;border:1px solid {C["line"]};margin-top:6px">'
        f'<table style="border-collapse:collapse;width:100%">'
        f'<tr><th style="background:{C["surface"]};border:1px solid {C["line"]};min-width:130px"></th>'
        + "".join(_th(c) for c in cols) + "</tr>"
        + _row("Grade", "grade", mono=True) + _row("Salary band", "band", mono=True)
        + _row("Median (P50)", "med", mono=True)
        + _row("+ Holiday (8%)", "hol", mono=True)
        + _row("+ 13th month", "m13", mono=True)
        + _row("+ Variable (on-target)", "var", mono=True)
        + _row("= Total target cash", "ttc", mono=True)
        + _row("+ Pension (~12%)", "pens", mono=True)
        + _row("+ Benefits (est.)", "ben", mono=True)
        + _row("= Total reward", "treward", mono=True)
        + _row("LTI eligible", "lti", mono=True)
        + _row("Knowledge / scope", "knowledge")
        + _row("Problem solving", "problem") + _row("Accountability", "account")
        + _row("Leadership", "lead") + _row("Top skills", "skills")
        + "</table></div>"
    )
    st.markdown(grid, unsafe_allow_html=True)
    st.caption("Total target cash = base median + 8% holiday + 13th month + on-target variable. "
               "Total reward adds indicative employer pension (~12%) and benefits (~€2k). See PayElements for definitions.")

    # ── pay range chart ─────────────────────────────────────────────────
    rows, order = [], []
    for role in fam.itertuples(index=False):
        b = bmap.get((getattr(role, "Function"), getattr(role, "Level")))
        if b is None or _pd.isna(b.get("Min")): continue
        label = str(getattr(role, "StandardTitle"))
        order.append(label)
        rows.append({"Role": label, "Level": getattr(role, "Level"),
                     "Min": b.get("Min"), "P25": b.get("P25"), "Median": b.get("P50"),
                     "P75": b.get("P75"), "Max": b.get("Max")})
    if rows:
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["muted"]};margin:20px 0 4px">Pay range by level</div>',
            unsafe_allow_html=True)
        df = _pd.DataFrame(rows)
        tips = ["Role", "Level"] + [_alt.Tooltip(f"{f}:Q", format=",.0f")
                                    for f in ("Min", "P25", "Median", "P75", "Max")]
        base = _alt.Chart(df).encode(x=_alt.X("Role:N", sort=order, axis=_alt.Axis(labelAngle=-20, title=None)))
        rule = base.mark_rule(color="#6F3CFF", strokeWidth=2, opacity=0.45).encode(
            y=_alt.Y("Min:Q", title="Base salary (€)"), y2="Max:Q")
        def _pt(field, shape, color, size=70):
            return base.mark_point(shape=shape, filled=True, color=color, size=size, opacity=0.9).encode(
                y=f"{field}:Q", tooltip=tips)
        chart = (rule + _pt("P25", "triangle-down", "#34B5FF") + _pt("P75", "triangle-up", "#34B5FF")
                 + _pt("Median", "circle", "#E85BB0", 170)).properties(height=340)
        chart = chart.configure_view(strokeOpacity=0).configure_axis(
            labelColor="#C9B8E8", titleColor="#C9B8E8", gridColor="#FFFFFF14", domainColor="#FFFFFF30")
        st.altair_chart(chart, use_container_width=True)
        st.caption("● median (P50)   ▲ P75   ▼ P25   │ min–max band")


@st.cache_data(show_spinner=False)
def _dq_frames(path):
    import pandas as _pd
    return _pd.read_excel(path, sheet_name=["Jobs", "TitleMapping"], dtype=str)


def data_quality_page(catalog):
    """Live data-quality scorecard for the reference library."""
    repo = catalog.repository
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Data Quality</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'A live scorecard for the reference library — coverage, integrity and freshness. '
        f'Run it after every edit to catch gaps before they reach users.</p>',
        unsafe_allow_html=True,
    )
    jobs = list(repo.jobs.values()); n = max(len(jobs), 1)
    try:
        fr = _dq_frames(WORKBOOK_PATH)
        jraw = fr["Jobs"]; tm = fr["TitleMapping"]
    except Exception:
        jraw = None; tm = None

    iso = own = {}
    if jraw is not None:
        iso = {str(r["JobID"]).strip(): str(r.get("IscoGroup", "")).strip() not in ("", "nan")
               for _, r in jraw.iterrows()}
        own = {str(r["JobID"]).strip(): str(r.get("Owner", "")).strip() not in ("", "nan")
               for _, r in jraw.iterrows()}
    syn_ids = {}
    if tm is not None:
        for _, r in tm.iterrows():
            syn_ids[str(r["JobID"]).strip()] = syn_ids.get(str(r["JobID"]).strip(), 0) + 1

    def _profile(j):
        p = repo.profiles.get(j.job_id); return bool(p and (p.description or p.key_responsibilities))
    dims = {
        "Profile":     _profile,
        "Salary band": lambda j: (j.function, j.level) in repo.salary,
        "Skills":      lambda j: len(repo.role_skill_map.get(j.job_id, [])) > 0,
        "Grade":       lambda j: (getattr(j, "grade", 0) or 0) > 0,
        "Career path": lambda j: j.job_id in repo.career_paths or j.standard_title == "Chief Executive Officer",
        "ISCO code":   lambda j: iso.get(j.job_id, False),
        "Synonyms":    lambda j: syn_ids.get(j.job_id, 0) > 0,
        "Owner":       lambda j: own.get(j.job_id, False),
    }
    cov = {name: sum(1 for j in jobs if fn(j)) for name, fn in dims.items()}
    health = round(sum(cov.values()) / (len(dims) * n) * 100)

    # ── headline tiles ──────────────────────────────────────────────────
    hcol = C["teal"] if health >= 90 else (C["amber"] if health >= 70 else C["danger"])
    tiles = [("Health score", f"{health}%", hcol), ("Roles", str(len(jobs)), C["ink"]),
             ("Functions", str(len(repo.jobs_by_function)), C["ink"]),
             ("Title synonyms", str(len(tm)) if tm is not None else "—", C["ink"])]
    trow = "".join(
        f'<div style="flex:1;min-width:120px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-radius:12px;padding:14px 16px">'
        f'<div style="font-family:{FONT_SERIF};font-size:30px;font-weight:700;color:{col}">{val}</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.08em;text-transform:uppercase;'
        f'color:{C["muted"]};margin-top:2px">{lab}</div></div>'
        for lab, val, col in tiles)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">{trow}</div>',
                unsafe_allow_html=True)

    # ── coverage bars ───────────────────────────────────────────────────
    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:6px 0 8px">Coverage</div>',
                unsafe_allow_html=True)
    bars = ""
    for name, cnt in cov.items():
        pct = round(cnt / n * 100)
        bc = C["teal"] if pct == 100 else (C["amber"] if pct >= 80 else C["danger"])
        bars += (
            f'<div style="display:flex;align-items:center;gap:12px;margin:5px 0">'
            f'<span style="flex:0 0 130px;font-size:13px;color:{C["ink"]}">{name}</span>'
            f'<span style="flex:1;background:{C["line"]};border-radius:999px;height:10px;position:relative">'
            f'<span style="position:absolute;left:0;top:0;height:10px;width:{pct}%;background:{bc};border-radius:999px"></span></span>'
            f'<span style="flex:0 0 78px;text-align:right;font-family:{FONT_MONO};font-size:12px;color:{bc}">'
            f'{pct}% · {cnt}/{n}</span></div>')
    st.markdown(bars, unsafe_allow_html=True)

    # ── integrity checks ────────────────────────────────────────────────
    ids = [j.job_id for j in jobs]
    dupes = {x for x in ids if ids.count(x) > 1}
    bad_ord = [f"{k[0]}/{k[1]}" for k, b in repo.salary.items() if not (b.min <= b.p50 <= b.max)]
    dang_cp = [jid for jid, cs in repo.career_paths.items()
               if cs.next_job_id and cs.next_job_id not in repo.jobs]
    dang_tm = sorted({str(r["JobID"]).strip() for _, r in tm.iterrows()
                      if str(r["JobID"]).strip() not in repo.jobs}) if tm is not None else []
    checks = [
        ("No duplicate JobIDs", not dupes, ", ".join(sorted(dupes))),
        ("Salary min ≤ P50 ≤ max", not bad_ord, ", ".join(bad_ord)),
        ("Career paths resolve", not dang_cp, ", ".join(dang_cp)),
        ("Synonyms map to real roles", not dang_tm, ", ".join(dang_tm)),
    ]
    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:18px 0 8px">Integrity</div>',
                unsafe_allow_html=True)
    crows = ""
    for label, ok, detail in checks:
        icon = "✓" if ok else "✗"; col = C["teal"] if ok else C["danger"]
        crows += (f'<div style="display:flex;align-items:center;gap:10px;margin:4px 0;font-size:13px">'
                  f'<span style="color:{col};font-weight:700">{icon}</span>'
                  f'<span style="color:{C["ink"]}">{label}</span>'
                  f'<span style="color:{C["muted"]};font-size:12px">{("— "+detail) if detail else ""}</span></div>')
    st.markdown(crows, unsafe_allow_html=True)

    # ── attention list ──────────────────────────────────────────────────
    gaps = {name: [j.standard_title for j in jobs if not fn(j)]
            for name, fn in dims.items() if cov[name] < n}
    if gaps:
        with st.expander(f"⚠ Roles needing attention ({sum(len(v) for v in gaps.values())} gaps)"):
            for name, roles in gaps.items():
                st.markdown(f"**Missing {name}** ({len(roles)}): " + ", ".join(roles))
    else:
        st.success("✓ Every role is complete on all coverage dimensions.")

    # ── per-function completeness ───────────────────────────────────────
    with st.expander("Completeness by function"):
        import pandas as _pd
        rows = []
        for fnname, roles in sorted(repo.jobs_by_function.items()):
            m = len(roles) * len(dims)
            got = sum(1 for j in roles for fn in dims.values() if fn(j))
            rows.append({"Function": fnname, "Roles": len(roles),
                         "Completeness": f"{round(got/max(m,1)*100)}%"})
        st.dataframe(_pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_leveled_gap(df, *, function_col, level_col, gender_col, salary_col, fte_col=None, tenure_col=None, salary_already_fte=False):
    """
    Option A — structural gender pay gap straight from a client's leveled grid
    (Function + Level + Gender + Salary), with no job-title matching or bands.
    Backed by services.pay_equity_service.analyze_gender_pay_gap.
    """
    import pandas as pd
    try:
        from services.pay_equity_service import (
            analyze_gender_pay_gap, DIRECTIVE_THRESHOLD_PCT, flip_gap_sign, flip_gap_ci)
    except ImportError:
        from jobsy.services.pay_equity_service import (
            analyze_gender_pay_gap, DIRECTIVE_THRESHOLD_PCT, flip_gap_sign, flip_gap_ci)

    det = [("Function", function_col), ("Level", level_col), ("Gender", gender_col),
           ("Salary", salary_col), ("FTE", fte_col), ("Tenure", tenure_col)]
    st.caption("Leveled-grid mode · " + " · ".join(f"{lab}: **{c}**" for lab, c in det if c))
    if not salary_col:
        st.error("No salary column found — include an annual salary column."); return
    if not gender_col:
        st.info("➕ Add a **Gender** column (M / F — Dutch M / V is read natively) to compute the gender pay gap."); return

    r = analyze_gender_pay_gap(df, function_col=function_col, level_col=level_col,
                               gender_col=gender_col, salary_col=salary_col, fte_col=fte_col,
                               tenure_col=tenure_col, salary_already_fte=salary_already_fte)
    if not r.has_gap:
        st.info(f"Need both men and women with pay to compute a gap (M n={r.n_m}, F n={r.n_f})."); return

    # Display in the wetsvoorstel's own sign convention -- (vrouw-man)/man, positive
    # = women paid more -- rather than PayGapResult's internal "men paid more" one,
    # so this screen always matches the downloaded report (PayEquityExportService
    # applies the same flip).
    mean_gap = flip_gap_sign(r.mean_gap_pct)
    median_gap = flip_gap_sign(r.median_gap_pct)
    adjusted_gap = flip_gap_sign(r.adjusted_gap_pct)
    adjusted_ci = flip_gap_ci(r.adjusted_ci)

    def _col(v):
        return C["danger"] if (v is not None and abs(v) >= DIRECTIVE_THRESHOLD_PCT) else C["teal"]

    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:14px 0 6px">'
                f'Gender pay gap · Function × Level</div>', unsafe_allow_html=True)
    _xnote = f", other/unknown n={r.n_excluded} excluded" if r.n_excluded else ""
    st.markdown(
        f'<div style="font-size:14px;color:{C["ink"]}">'
        f'Mean gap (F vs M): <b style="color:{_col(mean_gap)}">{mean_gap:+.1f}%</b> &nbsp;·&nbsp; '
        f'Median gap: <b style="color:{_col(median_gap)}">{median_gap:+.1f}%</b> &nbsp;'
        f'<span style="color:{C["muted"]}">(M n={r.n_m}, F n={r.n_f}{_xnote})</span></div>',
        unsafe_allow_html=True)
    st.caption("Positive = women paid more (NL wetsvoorstel: (vrouw-man)/man). " +
               ("Salary read as already full-time-equivalent (source-declared FT) — no extra pro-rating."
                if salary_already_fte
                else "Full-time-equivalent (base ÷ FTE)." if r.fte_normalised
                else "⚠ No FTE column — part-time pay is not pro-rated, which tends to overstate the gap."))

    if adjusted_gap is not None:
        import math as _math
        _ci_ok = adjusted_ci and all(v is not None and not _math.isnan(v) for v in adjusted_ci)
        ci = f" (95% CI {adjusted_ci[0]:+.1f}…{adjusted_ci[1]:+.1f}%)" if _ci_ok else ""
        sig = ("statistically significant" if r.adjusted_significant
               else "not statistically significant" if r.adjusted_significant is False else "significance n/a")
        direction = "more" if (adjusted_gap or 0) >= 0 else "less"
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-left:3px solid {_col(adjusted_gap)};border-radius:10px;padding:12px 14px;'
            f'margin:10px 0;font-size:13.5px;color:{C["ink"]};line-height:1.55">'
            f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
            f'color:{C["muted"]};margin-bottom:4px">Adjusted — like-for-like</div>'
            f'At the <b>same function and level</b>, women earn '
            f'<b style="color:{_col(adjusted_gap)}">{abs(adjusted_gap):.1f}%</b> {direction} than men'
            f'{ci} — {sig}. The residual "unexplained" gap after controlling for function and level.</div>',
            unsafe_allow_html=True)

    # The grade-assignment regression treats the level column as an ORDERED
    # ladder. Some intake files (e.g. the pay-transparency basis-check
    # template) use "categorie" as NOMINAL comparison-group numbers -- "all
    # employees doing the same work share a group" -- where group 5 is not
    # "higher" than group 3, just different work. Testing whether gender
    # predicts a nominal group NUMBER is statistically meaningless, so let
    # the analyst say which kind this column is instead of silently assuming.
    _is_ladder = st.checkbox(
        "Level/Categorie is an ordered ladder (higher number = more senior) — enables the grade-assignment check",
        value=True, key="lg_level_is_ordinal",
        help="Untick for files where the category is a comparison-GROUP number "
             "(same work grouped together, numbers carry no rank). The pay-gap "
             "figures above are unaffected either way.")
    if r.grade_gap_levels is not None and _is_ladder:
        gg = flip_gap_sign(r.grade_gap_levels)          # positive = women sit at a HIGHER level, on this display
        gg_ci = flip_gap_ci(r.grade_gap_ci)
        gg_sig = ("statistically significant" if r.grade_gap_significant
                  else "not statistically significant" if r.grade_gap_significant is False else "significance n/a")
        gg_dir = "higher" if gg >= 0 else "lower"
        gg_col = C["danger"] if (r.grade_gap_significant and abs(gg) >= 0.5) else C["teal"]
        import math as _math
        _gg_ok = gg_ci and all(v is not None and not _math.isnan(v) for v in gg_ci)
        gg_ci_txt = f" (95% CI {gg_ci[0]:+.2f}…{gg_ci[1]:+.2f})" if _gg_ok else ""
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-left:3px solid {gg_col};border-radius:10px;padding:12px 14px;'
            f'margin:10px 0;font-size:13.5px;color:{C["ink"]};line-height:1.55">'
            f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
            f'color:{C["muted"]};margin-bottom:4px">Grade-assignment check</div>'
            f'At the <b>same function</b>, women sit at a level <b style="color:{gg_col}">{abs(gg):.2f}</b> '
            f'{gg_dir} than men{gg_ci_txt} — {gg_sig}. This tests whether <b>gender predicts the level itself</b>, '
            f'not just pay within it — the classification system Art. 4 requires to be gender-neutral, rather than '
            f'assumed. A significant gap here is reason to commission a full job-evaluation review '
            f'(skills, effort, responsibility, working conditions), not proof of one on its own.</div>',
            unsafe_allow_html=True)
    elif r.grade_gap_levels is not None and not _is_ladder:
        st.caption("Grade-assignment check hidden — level read as nominal comparison groups "
                   "(numbers carry no rank), so a \"sits higher/lower\" test doesn't apply. "
                   "Representation per group below still shows where women sit.")

    if r.n_cohorts_tested:
        bcol = C["danger"] if r.n_cohorts_flagged else C["teal"]
        st.markdown(
            f'<div style="font-size:13.5px;color:{C["ink"]};margin:6px 0 4px">'
            f'<b style="color:{bcol}">{r.n_cohorts_flagged} of {r.n_cohorts_tested}</b> Function×Level cohorts '
            f'(with both men and women) show a gap ≥ {DIRECTIVE_THRESHOLD_PCT:.0f}% '
            f'({r.n_cohorts_flagged_reliable} with a reliable ≥{5}-per-gender sample). Under the EU Directive a '
            f'≥5% gap within a category of equal-value work triggers a joint pay assessment unless justified by '
            f'objective, gender-neutral criteria.</div>', unsafe_allow_html=True)

    if r.cohorts:
        tbl = pd.DataFrame([{
            "Function": c.function, "Level": c.level, "M": c.n_m, "F": c.n_f,
            "M median": c.median_m, "F median": c.median_f, "Gap %": flip_gap_sign(c.mean_gap_pct),
            "≥5%?": "⚠ yes" if c.flagged else "no", "Sample": "ok" if c.reliable else "low n",
        } for c in r.cohorts])
        with st.expander(f"Per Function × Level cohort ({len(r.cohorts)} with both men and women)"):
            st.dataframe(tbl, use_container_width=True, hide_index=True)

    with st.expander("Representation — share of women by level and by function"):
        st.caption("A headline gap is usually driven as much by where women sit as by unequal pay within a cohort.")
        cA, cB = st.columns(2)
        cA.dataframe(pd.DataFrame([{"Level": k, "% women": v} for k, v in r.women_by_level.items()]),
                     use_container_width=True, hide_index=True)
        cB.dataframe(pd.DataFrame([{"Function": k, "% women": v} for k, v in r.women_by_function.items()]),
                     use_container_width=True, hide_index=True)

    # ── CAO crosswalk (ISF / CATS®, indicative, public bands only) ─────────
    # This mode has no job titles/reference-library ladder to draw on -- the
    # grade range is this file's own numeric Level column, not an org-wide
    # JobGrade ladder (see the compa-ratio path's version of this for that
    # richer case). No skill/description context here either, by design --
    # this mode doesn't collect that data.
    _lvl_num = pd.to_numeric(df[level_col], errors="coerce")
    if _lvl_num.notna().mean() > 0.9:
        try:
            from services.cao_crosswalk_service import (
                crosswalk_to_cats, crosswalk_to_isf, known_cats_sectors)
        except ImportError:
            from jobsy.services.cao_crosswalk_service import (
                crosswalk_to_cats, crosswalk_to_isf, known_cats_sectors)

        st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                    f'CAO crosswalk — ISF / CATS® (indicative)</div>', unsafe_allow_html=True)
        st.caption("Positions this file's own Level column against the PUBLIC salary-group structure "
                   "of a sector CAO — never a reproduced ISF/CATS® scoring method (FME's / De Leeuw "
                   "Consult's protected IP; see docs/cao-metalektro-isf-reference.md). Always "
                   "indicative — official classification needs a certified weging.")

        lg_min, lg_max = float(_lvl_num.min()), float(_lvl_num.max())
        st.caption(f"Rank-positioned against this file's own Level range: {lg_min:g}–{lg_max:g} "
                   "(no reference-library grade ladder available in this mode).")

        _lsys = st.radio("CAO systeem", ["ISF (Metalektro)", "CATS® (kies sector)"],
                         key="lg_cao_system", horizontal=True)
        cw = pd.DataFrame({function_col: df[function_col], level_col: df[level_col], "_lvl_num": _lvl_num})
        cw = cw[cw["_lvl_num"].notna()]

        if _lsys.startswith("ISF"):
            def _isf_row(lv):
                res = crosswalk_to_isf(lv, lg_min, lg_max)
                return (res.salarisgroep, f"{res.isf_point_range[0]}–{res.isf_point_range[1]}",
                        (f"€{res.monthly_scale[0]:,.0f}–€{res.monthly_scale[1]:,.0f}".replace(",", ".")
                         if res.monthly_scale else "— (Hoger Personeel, geen vaste schaal)")) if res else (None, None, None)
            cw[["Salarisgroep", "ISF puntenbereik", "Maandschaal 2026"]] = cw["_lvl_num"].apply(
                lambda v: pd.Series(_isf_row(v)))
            _groups = sorted(g for g in cw["Salarisgroep"].dropna().unique())
            _pick = st.multiselect("Filter op salarisgroep", _groups, default=_groups, key="lg_isf_group_filter")
            _shown = cw[cw["Salarisgroep"].isin(_pick)]
            st.dataframe(_shown[[function_col, level_col, "Salarisgroep", "ISF puntenbereik", "Maandschaal 2026"]],
                        use_container_width=True, hide_index=True)
            st.caption("Indicatief: positionering binnen de publieke ISF-bandbreedtes — geen berekende "
                       "ISF-score. Officiële ISF-indeling vereist een gecertificeerde weging.")
        else:
            _sector = st.selectbox("Sector (CATS® handboek)", known_cats_sectors(), key="lg_cats_sector")
            def _cats_row(lv):
                res = crosswalk_to_cats(lv, lg_min, lg_max, sector=_sector)
                return (res.functiegroep, res.salarisgroep)
            cw[["Functiegroep", "Salarisgroep"]] = cw["_lvl_num"].apply(lambda v: pd.Series(_cats_row(v)))
            _groups = sorted(g for g in cw["Salarisgroep"].dropna().unique())
            _pick = st.multiselect("Filter op salarisgroep", _groups, default=_groups, key="lg_cats_group_filter")
            _shown = cw[cw["Salarisgroep"].isin(_pick)]
            st.dataframe(_shown[[function_col, level_col, "Functiegroep", "Salarisgroep"]],
                        use_container_width=True, hide_index=True)
            st.caption(f"Label alignment only, {_sector} — CATS® has no public point-range table to "
                       "position against (unlike ISF). Official classification requires reading the "
                       "sector's niveaublad for the relevant functiefamilie, done by a certified CATS® user.")
    else:
        st.caption("CAO crosswalk skipped — Level column isn't numeric/ordinal enough to position "
                   "(need e.g. 1-12, not free-text grades).")

    for note in r.notes:
        st.caption("· " + note)

    try:
        from services.pay_equity_export_service import PayEquityExportService
    except ImportError:
        from jobsy.services.pay_equity_export_service import PayEquityExportService
    _report_bytes = PayEquityExportService().to_workbook_bytes(r)
    st.download_button(
        "⬇ Download pay equity report (.xlsx)",
        _report_bytes,
        file_name="jobsy_pay_equity_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def pay_equity_page(catalog, service):
    """Compa-ratio & pay-position analysis vs the role bands (EU pay transparency)."""
    import pandas as _pd, io as _io, re as _re
    repo = catalog.repository
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Pay Equity</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Upload actual salaries to see each person\'s <b>compa-ratio</b> (pay ÷ band midpoint) '
        f'and range position, plus a light <b>EU Pay Transparency Directive</b> read-out: '
        f'mean &amp; median gender gaps on base and total pay (full-time-equivalent), '
        f'per-category testing against the 5% threshold, pay-quartile split and who receives variable pay. '
        f'Below-range pay is flagged.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-left:3px solid {C["amber"]};'
        f'border-radius:10px;padding:12px 14px;margin:0 0 16px;font-size:13px;color:{C["muted"]};line-height:1.55">'
        f'<b style="color:{C["ink"]}">Where this stands legally right now:</b> Dutch implementing legislation for '
        f'the Directive is not yet in force — the bill was only submitted to the Tweede Kamer in May 2026, '
        f'targeted for 1 January 2027 (later than the original June 2026 EU deadline, which the European '
        f'Commission declined to extend). Once live, the formal reporting duty that starts the Directive\'s '
        f'6-month remediation clock is phased by employer size: <b>150+ employees</b> first report 7 June 2028 '
        f'(annually after); <b>100–149</b> first report 7 June 2031 (every 3 years); <b>under 100</b> has no '
        f'reporting duty under this mechanism at all. Read everything below as getting ahead of the law, not '
        f'as a live compliance deadline — unless the client is already at 150+ employees.</div>',
        unsafe_allow_html=True,
    )
    # template
    tmpl = _pd.DataFrame([
        {"EmployeeID": "E1001", "Name": "Alex de Vries", "JobTitle": "Software Engineer", "ActualSalary": 68000, "Gender": "F"},
        {"EmployeeID": "E1002", "Name": "Sam Jansen", "JobTitle": "Head of Sales", "ActualSalary": 118000, "Gender": "M"},
    ])
    _b = _io.BytesIO(); tmpl.to_excel(_b, index=False)
    st.download_button("⬇ Download pay template (.xlsx)", _b.getvalue(),
        file_name="jobsy_pay_equity_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    _salkeys = {"actualsalary", "actual salary", "salary", "base salary", "basesalary", "grosssalary",
                "gross salary", "salaris", "brutosalaris", "loon", "pay"}
    _salcont = ["sal", "salaris", "loon", "pay", "bruto"]
    # #2 — reuse the workforce file already uploaded on the Matching page if it carries pay
    df = None
    wf = st.session_state.get("upload_df")
    if wf is not None and _smart_detect(list(wf.columns), _salkeys, _salcont):
        if st.checkbox(f"Use the workforce data uploaded on Matching ({len(wf)} rows, has pay)", value=True):
            df = wf.copy()
    if df is None:
        up = st.file_uploader("Upload actual pay (.csv or .xlsx)", type=["csv", "xls", "xlsx"], key="pe_up")
        if not up:
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-radius:12px;'
                f'padding:16px;color:{C["muted"]};font-size:14px;margin-top:6px">'
                f'Provide columns for job title and actual annual base salary; optionally name, gender, and '
                f'variable pay (Bonus, Allowances, LTI) for the total-pay gender gap.</div>',
                unsafe_allow_html=True)
            return
        try:
            df = _pd.read_csv(up) if up.name.endswith(".csv") else _pd.read_excel(up)
        except Exception as exc:
            st.error(f"Could not read file: {exc}"); return
    if df is None or df.empty:
        st.warning("No usable data."); return

    cols = list(df.columns)
    # ── Option A: leveled-grid path — client already provides Function + Level ──
    # If both are present we can run the band-free structural gender pay gap
    # directly (no job-title matching needed). Offer it as the primary mode.
    _fun_col = _smart_detect(cols, {"function", "functie", "jobfamily", "job family", "family",
                                    "functiefamilie", "discipline", "vakgebied"},
                             ["function", "functie", "family", "discipline"])
    _lvl_col = _smart_detect(cols, {"level", "niveau", "grade", "joblevel", "job level", "career level",
                                    "functieniveau", "schaal", "salarisschaal",
                                    "categorie", "category", "werknemerscategorie", "functiegroep"},
                             ["level", "niveau", "grade", "schaal", "categorie", "category"])
    if _fun_col and _lvl_col:
        _mode = st.radio(
            "This file is already leveled (Function + Level detected) — how should Pay Equity read it?",
            ["Structural gender pay gap on Function × Level — no job titles or bands needed",
             "Match job titles to salary bands (compa-ratio)"],
            key="pe_mode",
        )
        if _mode.startswith("Structural"):
            _lg_gender = _smart_detect(cols, {"gender", "geslacht", "sex", "m/v", "m/f"},
                                       ["gender", "geslacht", "sex"])
            _lg_fte = _smart_detect(cols, {"fte", "parttime", "part-time", "part time", "werkuren", "deeltijd",
                                           "contract hours", "hours", "parttimefactor", "deeltijdfactor"},
                                    ["fte", "parttime", "deeltijd"])
            _lg_tenure = _smart_detect(cols, {"tenure", "yearsofservice", "years of service", "dienstjaren",
                                              "startdate", "start date", "hiredate", "hire date", "indiensttreding"},
                                       ["tenure", "dienstjaren", "startdate", "hiredate"])
            _lg_sal = _smart_detect(cols, _salkeys, _salcont)
            # "FT salaris" (Dutch intake templates) means the column is ALREADY
            # full-time-equivalent. Dividing it by FTE again double-corrects --
            # part-timers (mostly women, in NL) get inflated pay and a real gap
            # silently shrinks. Default from the column name; analyst can override.
            _looks_fte = bool(_lg_sal) and bool(_re.search(r"(^|\W)(ft|fte|fulltime|full-time|voltijd)($|\W)",
                                                            str(_lg_sal), _re.I))
            _sal_reading = st.radio(
                "How should the salary column be read?",
                ["Already full-time-equivalent (do not divide by FTE)",
                 "Actual paid salary (divide by FTE to compare)"],
                index=(0 if _looks_fte else 1), key="lg_sal_reading", horizontal=False)
            _already_fte = _sal_reading.startswith("Already")
            _render_leveled_gap(df, function_col=_fun_col, level_col=_lvl_col, gender_col=_lg_gender,
                                salary_col=_lg_sal, fte_col=(None if _already_fte else _lg_fte),
                                tenure_col=_lg_tenure, salary_already_fte=_already_fte)
            return
    title_col = _smart_detect(cols, {"jobtitle", "job title", "title", "currentrole", "current role",
                                     "functie", "functietitel", "role"}, ["title", "functie", "role"]) or cols[0]
    sal_col = _smart_detect(cols, _salkeys, _salcont)
    name_col = _smart_detect(cols, {"name", "fullname", "full name", "naam", "employee", "medewerker"}, ["name", "naam"])
    gender_col = _smart_detect(cols, {"gender", "geslacht", "sex", "m/v", "m/f"}, ["gender", "geslacht", "sex"])
    bonus_col = _smart_detect(cols, {"bonus", "variable pay", "variable", "incentive", "commission",
                                     "bonus/commission"}, ["bonus", "incentive", "commission", "variable"])
    allow_col = _smart_detect(cols, {"allowances", "allowance", "toeslag", "toeslagen", "vergoeding",
                                     "13th month", "holiday allowance", "vakantiegeld"},
                              ["allowance", "toeslag", "vergoeding", "vakantiegeld"])
    lti_col = _smart_detect(cols, {"lti", "equity", "long-term incentive", "long term incentive", "rsu",
                                   "stock", "aandelen", "options", "share plan"}, ["lti", "equity", "rsu", "aandelen"])
    fte_col = _smart_detect(cols, {"fte", "parttime", "part-time", "part time", "werkuren", "deeltijd",
                                   "contract hours", "hours", "parttimefactor", "deeltijdfactor"},
                            ["fte", "parttime", "deeltijd"])
    comp_cols = {"Bonus": bonus_col, "Allowances": allow_col, "LTI": lti_col}
    has_variable = any(comp_cols.values())
    if not sal_col:
        st.error("No salary column found. Include an 'ActualSalary' column."); return
    _detected = [("Title", title_col), ("Salary", sal_col), ("Name", name_col), ("Gender", gender_col),
                 ("FTE", fte_col), ("Bonus", bonus_col), ("Allowances", allow_col), ("LTI", lti_col)]
    st.caption(" · ".join(f"{lab}: **{c}**" for lab, c in _detected if c))

    def _num(v):
        s = _re.sub(r"[^\d]", "", str(v))
        return int(s) if s else None

    def _fnum(v):
        # Parse an FTE / part-time factor: accepts 1.0 / 0.8 / "0,8" / "80%" / 80.
        try:
            s = _re.sub(r"[^\d.]", "", str(v).strip().replace(",", ".").replace("%", ""))
            f = float(s) if s else None
        except Exception:
            f = None
        if f is None or f <= 0:
            return None
        if f > 2:            # given as a percentage (e.g. 80) → 0.80
            f = f / 100.0
        return round(f, 4) if f <= 1.5 else None

    rows = []
    for _, r in df.iterrows():
        actual = _num(r.get(sal_col))
        if actual is None:
            continue
        title = str(r.get(title_col, "")).strip()
        m = service.match(title)
        band = repo.salary.get((m.function, m.level)) if m.matched else None
        rec = {"Name": (str(r.get(name_col)) if name_col else str(r.get(cols[0]))),
               "Input title": title, "Matched role": m.standard_title or "— no match —",
               "Function": m.function or "", "Level": m.level or "—", "Actual": actual,
               "JobId": m.job_id, "Description": m.description or ""}
        _fte = _fnum(r.get(fte_col)) if fte_col else None
        rec["FTE"] = _fte if _fte else 1.0
        rec["Actual FT"] = round(actual / rec["FTE"]) if rec["FTE"] else actual
        if gender_col:
            rec["Gender"] = str(r.get(gender_col, "")).strip().upper()[:1]
            # Dutch M/V: read V(rouw) as F so a Dutch export analyses natively.
            if rec["Gender"] == "V":
                rec["Gender"] = "F"
        if has_variable:
            _bonus = (_num(r.get(bonus_col)) or 0) if bonus_col else 0
            _allow = (_num(r.get(allow_col)) or 0) if allow_col else 0
            _lti = (_num(r.get(lti_col)) or 0) if lti_col else 0
            rec["Bonus"] = _bonus; rec["Allowances"] = _allow; rec["LTI"] = _lti
            rec["Total cash"] = actual + _bonus + _allow
            rec["Total pay"] = actual + _bonus + _allow + _lti
            rec["Total pay FT"] = round((actual + _bonus + _allow + _lti) / rec["FTE"]) if rec["FTE"] else (actual + _bonus + _allow + _lti)
        if band is not None:
            p50 = band.p50 or round((band.min + band.max) / 2)
            rec["Band P50"] = int(p50); rec["Band min"] = int(band.min); rec["Band max"] = int(band.max)
            rec["Grade"] = getattr(band, "grade", None) or None
            rec["Compa-ratio"] = round(actual / p50, 2) if p50 else None
            rec["Range %"] = round((actual - band.min) / (band.max - band.min) * 100) if band.max > band.min else None
            if actual < band.min:
                rec["Status"] = "Below range"
            elif actual > band.max:
                rec["Status"] = "Above range"
            elif rec["Compa-ratio"] < 0.9:
                rec["Status"] = "Below market"
            elif rec["Compa-ratio"] > 1.1:
                rec["Status"] = "Above market"
            else:
                rec["Status"] = "At market"
        else:
            rec.update({"Band P50": None, "Compa-ratio": None, "Range %": None, "Status": "No match", "Grade": None})
        rows.append(rec)
    if not rows:
        st.warning("No usable rows (need a numeric salary)."); return
    res = _pd.DataFrame(rows)
    priced = res[res["Compa-ratio"].notna()]

    # coverage / exclusions (transparency — excluded rows silently leave the figures)
    _total_in = len(df); _parsed = len(res); _matched = len(priced)
    _unparsed = _total_in - _parsed; _nomatch = _parsed - _matched
    _excl = []
    if _nomatch:
        _excl.append(f"{_nomatch} no role match")
    if _unparsed:
        _excl.append(f"{_unparsed} unparsed pay")
    _covmsg = f"Coverage: {_matched} of {_total_in} uploaded employees are included in the pay analysis"
    if _excl:
        _covmsg += " — excluded: " + ", ".join(_excl)
    st.caption(_covmsg + ". Excluded rows are left out of every figure below.")

    # ── headline tiles ──────────────────────────────────────────────────
    avg_compa = round(priced["Compa-ratio"].mean(), 2) if len(priced) else 0
    below = int((res["Status"] == "Below range").sum())
    above = int((res["Status"] == "Above range").sum())
    nomatch = int((res["Status"] == "No match").sum())
    tiles = [("Employees priced", str(len(priced)), C["ink"]),
             ("Avg compa-ratio", f"{avg_compa:.2f}", C["teal"] if 0.95 <= avg_compa <= 1.05 else C["amber"]),
             ("Below range", str(below), C["danger"] if below else C["ink"]),
             ("Above range", str(above), C["blue"] if above else C["ink"]),
             ("Unmatched", str(nomatch), C["amber"] if nomatch else C["ink"])]
    trow = "".join(
        f'<div style="flex:1;min-width:110px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:28px;'
        f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
        f'letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
        for lab, val, col in tiles)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">{trow}</div>',
                unsafe_allow_html=True)

    # ── compa-ratio scatter ─────────────────────────────────────────────
    STATUS_COLOR = {"Below range": "#E0555F", "Below market": "#D9932B", "At market": "#0E9E7E",
                    "Above market": "#34B5FF", "Above range": "#8A63D6", "No match": "#8A93A5"}
    if len(priced):
        try:
            import altair as _alt
            ch = _pd.DataFrame({
                "Compa-ratio": priced["Compa-ratio"], "Role": priced["Matched role"],
                "Name": priced["Name"], "Actual": priced["Actual"], "Status": priced["Status"]})
            pts = _alt.Chart(ch).mark_circle(size=110, opacity=0.85).encode(
                x=_alt.X("Compa-ratio:Q", scale=_alt.Scale(zero=False), title="Compa-ratio (pay ÷ band midpoint)"),
                y=_alt.Y("Role:N", title=None),
                color=_alt.Color("Status:N", scale=_alt.Scale(domain=list(STATUS_COLOR), range=list(STATUS_COLOR.values())), legend=_alt.Legend(orient="bottom")),
                tooltip=["Name", "Role", _alt.Tooltip("Actual:Q", format=",.0f"), "Compa-ratio", "Status"])
            rule = _alt.Chart(_pd.DataFrame({"x": [1.0]})).mark_rule(color="#8A93A5", strokeDash=[4, 4]).encode(x="x:Q")
            chart = (rule + pts).properties(height=max(220, 26 * ch["Role"].nunique())).configure_view(strokeOpacity=0).configure_axis(labelColor="#C9B8E8", titleColor="#C9B8E8", gridColor="#FFFFFF14").configure_legend(labelColor="#C9B8E8", titleColor="#C9B8E8")
            st.altair_chart(chart, use_container_width=True)
        except Exception:
            pass

    # ── CAO crosswalk (ISF / CATS®, indicative, public bands only) ─────────
    if len(priced) and priced["Grade"].notna().any():
        try:
            from services.cao_crosswalk_service import (
                crosswalk_to_cats, crosswalk_to_isf, known_cats_sectors)
        except ImportError:
            from jobsy.services.cao_crosswalk_service import (
                crosswalk_to_cats, crosswalk_to_isf, known_cats_sectors)

        st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                    f'CAO crosswalk — ISF / CATS® (indicative)</div>', unsafe_allow_html=True)
        st.caption("Positions Jobsy's own grade against the PUBLIC salary-group structure of a "
                   "sector CAO — never a reproduced ISF/CATS® scoring method (that's FME's / De "
                   "Leeuw Consult's protected IP; see docs/cao-metalektro-isf-reference.md). "
                   "Always indicative — official classification needs a certified weging.")

        graded = priced[priced["Grade"].notna()].copy()
        grade_min_repo = min(repo.job_grades.keys()) if getattr(repo, "job_grades", None) else None
        grade_max_repo = max(repo.job_grades.keys()) if getattr(repo, "job_grades", None) else None
        g_min = grade_min_repo if grade_min_repo is not None else float(graded["Grade"].min())
        g_max = grade_max_repo if grade_max_repo is not None else float(graded["Grade"].max())
        _range_src = "org's full JobGrade ladder" if grade_min_repo is not None else "this file's own grade range"
        st.caption(f"Rank-positioned against the {_range_src}: grade {g_min}–{g_max}.")

        _system = st.radio("CAO systeem", ["ISF (Metalektro)", "CATS® (kies sector)"],
                           key="cao_crosswalk_system", horizontal=True)

        if _system.startswith("ISF"):
            def _isf_row(grade):
                r = crosswalk_to_isf(grade, g_min, g_max)
                return (r.salarisgroep, f"{r.isf_point_range[0]}–{r.isf_point_range[1]}",
                        (f"€{r.monthly_scale[0]:,.0f}–€{r.monthly_scale[1]:,.0f}".replace(",", ".")
                         if r.monthly_scale else "— (Hoger Personeel, geen vaste schaal)")) if r else (None, None, None)
            graded[["Salarisgroep", "ISF puntenbereik", "Maandschaal 2026"]] = graded["Grade"].apply(
                lambda g: _pd.Series(_isf_row(g)))
            _groups = sorted(g for g in graded["Salarisgroep"].dropna().unique())
            _pick = st.multiselect("Filter op salarisgroep", _groups, default=_groups, key="isf_group_filter")
            _shown = graded[graded["Salarisgroep"].isin(_pick)]
            st.dataframe(_shown[["Name", "Matched role", "Function", "Level", "Grade",
                                 "Salarisgroep", "ISF puntenbereik", "Maandschaal 2026"]],
                        use_container_width=True, hide_index=True)
            st.caption("Indicatief: positionering van Jobsy's eigen gradering binnen de publieke "
                       "ISF-bandbreedtes — geen berekende ISF-score. Officiële ISF-indeling vereist "
                       "een gecertificeerde weging.")
        else:
            _sector = st.selectbox("Sector (CATS® handboek)", known_cats_sectors(), key="cats_sector")
            def _cats_row(grade):
                r = crosswalk_to_cats(grade, g_min, g_max, sector=_sector)
                return (r.functiegroep, r.salarisgroep)
            graded[["Functiegroep", "Salarisgroep"]] = graded["Grade"].apply(lambda g: _pd.Series(_cats_row(g)))
            _groups = sorted(g for g in graded["Salarisgroep"].dropna().unique())
            _pick = st.multiselect("Filter op salarisgroep", _groups, default=_groups, key="cats_group_filter")
            _shown = graded[graded["Salarisgroep"].isin(_pick)]
            st.dataframe(_shown[["Name", "Matched role", "Function", "Level", "Grade",
                                 "Functiegroep", "Salarisgroep"]],
                        use_container_width=True, hide_index=True)
            st.caption(f"Label alignment only, {_sector} — CATS® has no public point-range table to "
                       "position against (unlike ISF). Official classification requires reading the "
                       "sector's niveaublad for the relevant functiefamilie, done by a certified CATS® user.")

        # Supporting context (never an input to a scoring formula): job description +
        # skill class/family, so a reviewer can sanity-check the indicative position.
        _roles = sorted(graded["Matched role"].dropna().unique())
        if _roles:
            with st.expander("Inspect a role — description & skill family (context, not a score input)"):
                _role_pick = st.selectbox("Role", _roles, key="cao_crosswalk_inspect_role")
                _rowmatch = graded[graded["Matched role"] == _role_pick].iloc[0]
                st.markdown(f"**{_role_pick}** · Function {_rowmatch.get('Function','—')} · "
                           f"Level {_rowmatch.get('Level','—')} · Grade {_rowmatch.get('Grade','—')}")
                _desc = _rowmatch.get("Description") or ""
                st.write(_desc if _desc else "_No description on file for this role._")
                _jid = _rowmatch.get("JobId")
                _reqs = repo.role_skill_map.get(_jid, []) if _jid else []
                if _reqs:
                    _skilltbl = _pd.DataFrame([{
                        "Skill": repo.skills[req.skill_id].skill_name if req.skill_id in repo.skills else req.skill_id,
                        "Class (family)": repo.skills[req.skill_id].category if req.skill_id in repo.skills else "—",
                        "Required level": req.required_level, "Type": req.skill_type,
                    } for req in _reqs])
                    st.dataframe(_skilltbl, use_container_width=True, hide_index=True)
                else:
                    st.caption("No skill requirements on file for this role.")

    # ── gender pay gap & equity reasoning (EU Pay Transparency Directive) ──
    if gender_col and "Gender" in priced.columns:
        gm = priced[priced["Gender"] == "M"]; gf = priced[priced["Gender"] == "F"]
        n_x = int((~priced["Gender"].isin(["M", "F"])).sum())
        if len(gm) and len(gf):
            _basis = "Actual FT" if "Actual FT" in priced.columns else "Actual"
            _fte_on = bool(fte_col)

            def _gap(a, b):
                return round((a - b) / a * 100, 1) if a else None

            def _c(v):
                return C["danger"] if (v is not None and abs(v) >= 5) else C["teal"]

            raw_mean = _gap(gm[_basis].mean(), gf[_basis].mean())
            raw_med = _gap(gm[_basis].median(), gf[_basis].median())
            compa_gap = round((gm["Compa-ratio"].mean() - gf["Compa-ratio"].mean()) * 100, 1)
            _xnote = f", X/other n={n_x} excluded" if n_x else ""
            st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                        f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                        f'Gender pay gap &amp; equity reasoning</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div style="font-size:14px;color:{C["ink"]}">'
                f'Mean gap (M vs F): <b style="color:{_c(raw_mean)}">{raw_mean:+.1f}%</b> &nbsp;·&nbsp; '
                f'Median gap: <b style="color:{_c(raw_med)}">{raw_med:+.1f}%</b> &nbsp;·&nbsp; '
                f'Compa-ratio gap: <b>{compa_gap:+.1f} pts</b> &nbsp;'
                f'<span style="color:{C["muted"]}">(M n={len(gm)}, F n={len(gf)}{_xnote})</span></div>',
                unsafe_allow_html=True)
            st.caption("Positive = men paid more. Mean and median are both shown, as the Directive requires "
                       "(median is less distorted by a few high earners). " +
                       ("Salaries are compared full-time-equivalent (base ÷ FTE)." if _fte_on else
                        "⚠ No FTE column supplied — part-time pay is NOT normalised; in the Dutch context "
                        "(high, strongly gendered part-time rates) this tends to overstate the gap."))
            # total-pay gap (mean + median) + who actually receives variable pay
            if has_variable:
                _tb = ("Total pay FT" if "Total pay FT" in priced.columns
                       else ("Total pay" if "Total pay" in priced.columns else None))
                if _tb:
                    tp_mean = _gap(gm[_tb].mean(), gf[_tb].mean())
                    tp_med = _gap(gm[_tb].median(), gf[_tb].median())
                    _d = (tp_mean - raw_mean) if (tp_mean is not None and raw_mean is not None) else 0.0
                    _w = "widens" if _d > 0 else "narrows" if _d < 0 else "does not change"
                    st.markdown(
                        f'<div style="font-size:14px;color:{C["ink"]};margin-top:4px">'
                        f'Total-pay gap (base + bonus + allowances + LTI): '
                        f'mean <b style="color:{_c(tp_mean)}">{tp_mean:+.1f}%</b> &nbsp;·&nbsp; '
                        f'median <b style="color:{_c(tp_med)}">{tp_med:+.1f}%</b> &nbsp;'
                        f'<span style="color:{C["muted"]}">({_d:+.1f} pts vs base — variable pay {_w} the gap)</span>'
                        f'</div>', unsafe_allow_html=True)
                # Isolated variable-pay gap (Bonus+Allowances+LTI alone, not folded into
                # total pay) -- the Directive requires this as its OWN reported metric,
                # separate from the base gap and the combined total-pay gap above.
                _varamt_col = "_var_amt"
                priced[_varamt_col] = priced["Bonus"].fillna(0) + priced["Allowances"].fillna(0) + priced["LTI"].fillna(0)
                vp_mean = _gap(gm[_varamt_col].mean(), gf[_varamt_col].mean())
                vp_med = _gap(gm[_varamt_col].median(), gf[_varamt_col].median())
                if vp_mean is not None:
                    st.markdown(
                        f'<div style="font-size:14px;color:{C["ink"]};margin-top:4px">'
                        f'Variable-pay gap (bonus + allowances + LTI only): '
                        f'mean <b style="color:{_c(vp_mean)}">{vp_mean:+.1f}%</b> &nbsp;·&nbsp; '
                        f'median <b style="color:{_c(vp_med)}">{vp_med:+.1f}%</b></div>', unsafe_allow_html=True)
                    st.caption("Reported on the variable amounts themselves (zero for anyone who receives none), "
                               "as its own figure — the Directive requires this separately from the base and "
                               "total-pay gaps above, since a gap can hide entirely inside who gets a bonus and how much.")
                _var = (priced["Bonus"].fillna(0) + priced["Allowances"].fillna(0) + priced["LTI"].fillna(0)) > 0
                pm = round(100 * _var[priced["Gender"] == "M"].mean()) if len(gm) else 0
                pf = round(100 * _var[priced["Gender"] == "F"].mean()) if len(gf) else 0
                st.caption(f"Receiving any variable pay — men {pm}% · women {pf}% "
                           "(the Directive also reports who receives variable components, not only their size).")

            # per-category gaps — the 5% trigger is per category of equal / equal-value work, not org-wide
            SMALL_N = 5
            def _cat_gaps(keycol, label):
                out = []
                for key, grp in priced.groupby(keycol):
                    a = grp[grp["Gender"] == "M"]; b = grp[grp["Gender"] == "F"]
                    if len(a) and len(b):
                        g = _gap(a[_basis].mean(), b[_basis].mean())
                        out.append({label: key, "M": len(a), "F": len(b),
                                    "M mean": round(a[_basis].mean()), "F mean": round(b[_basis].mean()),
                                    "Gap %": g, "≥5%?": "⚠ yes" if (g is not None and abs(g) >= 5) else "no",
                                    "Sample": "low n" if min(len(a), len(b)) < SMALL_N else "ok"})
                return out

            role_gaps = _cat_gaps("Matched role", "Role (equal work)")
            grade_gaps = (_cat_gaps("Grade", "Grade (equal value)")
                          if "Grade" in priced.columns and priced["Grade"].notna().any() else [])
            _flagged = [x for x in role_gaps if str(x["≥5%?"]).startswith("⚠")]
            n_breach = len(_flagged)
            n_breach_robust = sum(1 for x in _flagged if x["Sample"] == "ok")

            _reason = [f"Overall median gap {raw_med:+.1f}% (mean {raw_mean:+.1f}%)."]
            if role_gaps:
                _bcol = C["danger"] if n_breach else C["teal"]
                _rob = (f" ({n_breach_robust} with a reliable sample of ≥{SMALL_N} per gender, "
                        f"the rest small-sample)" if n_breach else "")
                _reason.append(f'<b style="color:{_bcol}">{n_breach} of {len(role_gaps)}</b> role categories '
                               f'(with both men and women) show a gap of 5% or more{_rob}.')
            else:
                _reason.append("No role category has both men and women yet — add more rows for category-level testing.")
            _reason.append('Under the Directive a gap of ≥5% <b>within a category of equal or equal-value work</b> '
                           'triggers a <b>joint pay assessment</b> — but only if it is <b>not justified</b> by '
                           'objective, gender-neutral criteria and <b>not remedied within 6 months</b>. '
                           'A high org-wide gap on its own is context, not a breach.')
            _reason.append('<b>These gaps are unadjusted</b> — not controlled for tenure, performance, location or '
                           'working hours, and small categories are noisy. Treat a flag as a prompt to investigate '
                           'that category, not proof of an unjustified gap.')
            _reason.append('Role and Grade are used here as the “equal work” / “equal value” '
                           'groupings. The Directive (Art. 4) requires these groupings to come from a '
                           '<b>gender-neutral job evaluation and classification system</b> — built on skills, '
                           'effort, responsibility and working conditions. This tool does not verify that the '
                           'client’s own role/grade structure meets that standard; if the structure itself '
                           'carries bias, a gap analysis on top of it can understate the true picture. (The '
                           'Structural gender pay gap mode on Function×Level runs a statistical grade-assignment '
                           'check for this — worth using alongside this compa-ratio view.)')
            _rcol = C["danger"] if n_breach else C["teal"]
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-left:3px solid {_rcol};border-radius:10px;padding:13px 15px;margin:12px 0;'
                f'font-size:13.5px;color:{C["ink"]};line-height:1.55">'
                f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
                f'color:{C["muted"]};margin-bottom:6px">Equity reasoning</div>' + " ".join(_reason) + '</div>',
                unsafe_allow_html=True)

            if role_gaps:
                with st.expander(f"Per-role gap — equal work ({len(role_gaps)} categories with M and F)"):
                    st.dataframe(_pd.DataFrame(role_gaps), use_container_width=True, hide_index=True)
            if grade_gaps:
                with st.expander(f"Per-grade gap — equal value ({len(grade_gaps)} grades with M and F)"):
                    st.caption("Groups different roles of the same grade — approximates 'work of equal value'.")
                    st.dataframe(_pd.DataFrame(grade_gaps), use_container_width=True, hide_index=True)

            # pay quartiles by gender (Directive Art. 9 reporting metric)
            try:
                _q = _pd.qcut(priced[_basis], 4, labels=["Q1 lowest", "Q2", "Q3", "Q4 highest"], duplicates="drop")
                _qt = _pd.crosstab(_q, priced["Gender"])
                for _g in ("M", "F"):
                    if _g not in _qt.columns:
                        _qt[_g] = 0
                _tot = _qt.sum(axis=1)
                _qt["% women"] = (100 * _qt["F"] / _tot).fillna(0).round().astype(int)
                with st.expander("Gender split across pay quartiles"):
                    st.caption("The Directive reports the share of women and men in each quartile pay band. "
                               "Few women in Q4 (or many in Q1) points to vertical segregation behind the gap.")
                    st.dataframe(_qt.reset_index().rename(columns={_basis: "Quartile"}),
                                 use_container_width=True, hide_index=True)
            except Exception:
                pass
        else:
            st.info(f"A Gender column is present, but the gap needs both men and women with matched pay "
                    f"(currently men n={len(gm)}, women n={len(gf)}). Add the missing group to compute the gender gap.")
    else:
        st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                    f'Gender pay gap &amp; equity reasoning</div>', unsafe_allow_html=True)
        st.info("➕ Add a **Gender** column (M / F — Dutch M / V is read natively) to unlock the gender pay-gap analysis — mean & median "
                "gaps on base and total pay, per-category testing against the 5% threshold, the pay-quartile "
                "split and variable-pay coverage.")

    # ── workforce cost & remediation scenario (#4) ──────────────────────
    if len(priced):
        try:
            _pm = _family_frames(WORKBOOK_PATH).get("PayMix")
        except Exception:
            _pm = None
        vmap = {}
        if _pm is not None:
            for _, pr in _pm.iterrows():
                try:
                    vmap[(str(pr["Function"]), str(pr["Level"]))] = (
                        float(pr.get("TargetVariablePct") or 0), float(pr.get("ThirteenthMonthPct") or 0))
                except Exception:
                    pass
        base_bill = float(priced["Actual"].sum())
        reward_bill = 0.0
        for _, pr in priced.iterrows():
            a = float(pr["Actual"]); vp, tp = vmap.get((str(pr.get("Function", "")), str(pr.get("Level", ""))), (0.0, 8.33))
            reward_bill += a * (1 + 0.08 + tp / 100 + vp / 100) + a * 0.12 + 2000
        rem_min = float(sum(max(0.0, float(pr["Band min"]) - float(pr["Actual"])) for _, pr in priced.iterrows()))
        rem_p50 = float(sum(max(0.0, float(pr["Band P50"]) - float(pr["Actual"])) for _, pr in priced.iterrows()))
        n_below = int((priced["Actual"] < priced["Band min"]).sum())
        _e = lambda v: "€{:,.0f}".format(v).replace(",", ".")
        st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">Workforce cost & remediation</div>',
                    unsafe_allow_html=True)
        ctiles = [("Base paybill", _e(base_bill), C["ink"]),
                  ("Est. total reward", _e(reward_bill), C["teal"]),
                  (f"Fix below-range ({n_below})", _e(rem_min), C["danger"] if rem_min else C["ink"]),
                  ("Bring all to market P50", _e(rem_p50), C["amber"] if rem_p50 else C["ink"])]
        crow = "".join(
            f'<div style="flex:1;min-width:150px;background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:22px;'
            f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
            f'letter-spacing:.06em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
            for lab, val, col in ctiles)
        st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap">{crow}</div>', unsafe_allow_html=True)
        st.caption("Total reward estimates base + holiday + 13th month + on-target variable + ~12% pension + benefits. "
                   "'Fix below-range' is the annual base cost to lift underpaid staff to their band minimum; "
                   "'to market P50' brings everyone below the midpoint up to it.")

    # ── table + export ──────────────────────────────────────────────────
    def _row_style(row):
        c = STATUS_COLOR.get(row["Status"], "#8A93A5")
        return [f"color:{c};font-weight:600" if col == "Status" else "" for col in row.index]
    show_cols = [c for c in ["Name", "Input title", "Matched role", "Level", "FTE", "Actual", "Actual FT",
                             "Total cash", "Total pay", "Total pay FT", "Band P50", "Range %", "Compa-ratio", "Status"]
                 if c in res.columns]
    st.dataframe(res[show_cols].style.apply(_row_style, axis=1), use_container_width=True, hide_index=True)
    _xb = _io.BytesIO(); res.to_excel(_xb, index=False)
    st.download_button("⬇ Download pay-equity analysis (.xlsx)", _xb.getvalue(),
        file_name="jobsy_pay_equity.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def benefits_benchmarking_page(catalog, benefits_svc):
    """Benchmark a benefits package against market percentiles (P25/median/P75/P90),
    computed from the self-built benefits reference library, with rule-based advice
    and a Total Rewards snapshot bridging Pay + Benefits."""
    import io as _io
    import pandas as _pd

    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Benefits Benchmarking</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Benchmark your employee benefits package against market percentiles and the median — '
        f'computed from a self-built reference library, by industry and level — with rule-based '
        f'advice and a report export.</p>',
        unsafe_allow_html=True,
    )
    if benefits_svc is None:
        st.error("benefits_service.py not found in services/")
        return

    repo = catalog.repository
    if not repo.benefits_catalog:
        st.warning("No BenefitsCatalog data found in the reference workbook.")
        return

    ind_id = st.session_state.get("industry_id")
    ind_name = st.session_state.get("industry_name", "General (NL baseline)")
    levels = repo.levels or ["Junior", "Medior", "Senior", "Lead"]
    level = st.selectbox("Level", levels, index=levels.index("Medior") if "Medior" in levels else 0)
    st.caption(f"Industry context: **{ind_name}** (change in the sidebar) · Level: **{level}**")

    # ── input table ──────────────────────────────────────────────────────
    cats = benefits_svc.categories()
    rows = []
    for cat in cats:
        item = benefits_svc.catalog_item(cat)
        rows.append({"Category": cat, "Unit": item.unit if item else "", "Offered": False, "Your value": 0.0})
    df_input = _pd.DataFrame(rows)
    st.markdown(
        f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
        f'text-transform:uppercase;color:{C["muted"]};margin:8px 0 6px">Your benefits package</div>',
        unsafe_allow_html=True)
    edited = st.data_editor(
        df_input, use_container_width=True, hide_index=True, num_rows="fixed",
        column_config={
            "Category":   st.column_config.TextColumn("Category", disabled=True, width="medium"),
            "Unit":       st.column_config.TextColumn("Unit", disabled=True, width="small"),
            "Offered":    st.column_config.CheckboxColumn("Offered?", width="small"),
            "Your value": st.column_config.NumberColumn("Your value", min_value=0.0, step=1.0, width="small"),
        },
        key="benefits_input_editor",
    )

    package = {r["Category"]: r["Your value"] for _, r in edited.iterrows() if r["Offered"]}
    offered = set(package.keys())

    if not package:
        st.info("Tick **Offered** and enter a value for at least one benefit to see the market comparison.")
        return

    comparisons = benefits_svc.compare_package(package, ind_id, level)
    idx = benefits_svc.benefits_richness_index(comparisons)

    # ── headline tiles ───────────────────────────────────────────────────
    below_p25 = sum(1 for c in comparisons if c.status == "Below P25")
    above_p75 = sum(1 for c in comparisons if c.status in ("Above P75", "Above P90"))
    tiles = [("Benefits Richness Index", f"{idx:.0f}/100", C["teal"] if idx >= 50 else C["amber"]),
             ("Categories compared", str(len(comparisons)), C["ink"]),
             ("Below P25", str(below_p25), C["danger"] if below_p25 else C["ink"]),
             ("Above P75", str(above_p75), C["blue"] if above_p75 else C["ink"])]
    trow = "".join(
        f'<div style="flex:1;min-width:130px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:26px;'
        f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
        f'letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
        for lab, val, col in tiles)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">{trow}</div>',
                unsafe_allow_html=True)
    st.caption("Benefits Richness Index = average percentile rank of your offered benefits vs. the "
               "market distribution for this industry/level (50 = at market median).")

    # ── chart: your value vs P25/median/P75/P90 per category ─────────────
    STATUS_COLOR = {"Below P25": "#E0555F", "Below median": "#D9932B", "At market": "#0E9E7E",
                    "Above P75": "#34B5FF", "Above P90": "#8A63D6"}
    chart_rows = [{"Category": c.category, "Your value": c.actual, "P25": c.band.p25,
                   "Median": c.band.p50, "P75": c.band.p75, "P90": c.band.p90,
                   "Status": c.status, "Unit": c.unit} for c in comparisons]
    cdf = _pd.DataFrame(chart_rows)
    try:
        import altair as _alt
        base = _alt.Chart(cdf).encode(y=_alt.Y("Category:N", title=None))
        rule = base.mark_rule(color="#6F3CFF", strokeWidth=2, opacity=0.4).encode(
            x=_alt.X("P25:Q", title="Value (category-specific unit)"), x2="P90:Q")
        median_tick = base.mark_tick(color="#E85BB0", thickness=3, size=22).encode(x="Median:Q")
        actual_pt = base.mark_point(shape="diamond", filled=True, size=140, opacity=0.95).encode(
            x="Your value:Q",
            color=_alt.Color("Status:N", scale=_alt.Scale(domain=list(STATUS_COLOR), range=list(STATUS_COLOR.values())),
                              legend=_alt.Legend(orient="bottom")),
            tooltip=["Category", "Your value", "P25", "Median", "P75", "P90", "Status"])
        chart = (rule + median_tick + actual_pt).properties(height=max(220, 40 * len(cdf)))
        chart = chart.configure_view(strokeOpacity=0).configure_axis(
            labelColor="#C9B8E8", titleColor="#C9B8E8", gridColor="#FFFFFF14", domainColor="#FFFFFF30"
        ).configure_legend(labelColor="#C9B8E8", titleColor="#C9B8E8")
        st.altair_chart(chart, use_container_width=True)
        st.caption("─ P25–P90 range   | median tick   ◆ your value, colored by status")
    except Exception:
        pass

    # ── table + export ────────────────────────────────────────────────────
    show = cdf[["Category", "Your value", "P25", "Median", "P75", "P90", "Status"]]
    def _row_style(row):
        color = STATUS_COLOR.get(row["Status"], "#8A93A5")
        return [f"color:{color};font-weight:600" if col == "Status" else "" for col in row.index]
    st.dataframe(show.style.apply(_row_style, axis=1), use_container_width=True, hide_index=True)

    _xb = _io.BytesIO(); show.to_excel(_xb, index=False)
    st.download_button("⬇ Download benefits benchmarking (.xlsx)", _xb.getvalue(),
        file_name="jobsy_benefits_benchmarking.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ── advice ─────────────────────────────────────────────────────────────
    advice = benefits_svc.generate_advice(comparisons, offered)
    if advice:
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["muted"]};margin:20px 0 6px">Advice</div>',
            unsafe_allow_html=True)
        SEV_COLOR = {"high": C["danger"], "medium": C["amber"], "low": C["muted"]}
        for a in advice[:8]:
            col = SEV_COLOR.get(a["severity"], C["muted"])
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-left:4px solid {col};'
                f'border-radius:10px;padding:10px 14px;margin-bottom:8px">'
                f'<div style="font-family:{FONT_SANS};font-weight:700;font-size:13px;color:{C["ink"]}">{a["title"]}</div>'
                f'<div style="font-family:{FONT_SANS};font-size:12.5px;color:{C["muted"]};margin-top:3px">{a["detail"]}</div>'
                f'</div>', unsafe_allow_html=True)

    # ── Total Rewards snapshot (Pay + Benefits, first step toward the unified center) ──
    st.markdown(
        f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
        f'text-transform:uppercase;color:{C["muted"]};margin:20px 0 6px">Total Rewards snapshot</div>',
        unsafe_allow_html=True)
    st.caption("Bring Pay + Benefits together: pick a function and your actual base salary to see a combined position.")
    funcs = sorted(repo.jobs_by_function.keys())
    if funcs:
        colA, colB = st.columns(2)
        with colA:
            fsel = st.selectbox("Function (for pay comparison)", funcs,
                                index=funcs.index("Engineering") if "Engineering" in funcs else 0,
                                key="tr_function")
        with colB:
            actual_pay = st.number_input("Your actual base salary (€, optional)", min_value=0.0, step=1000.0,
                                         value=0.0, key="tr_actual_pay")
        pay_compa = None
        if actual_pay:
            band = catalog.industry_adjusted_band(fsel, level, ind_id)
            if band and band.p50:
                pay_compa = round(actual_pay / band.p50, 2)
        snap = benefits_svc.total_rewards_snapshot(idx, pay_compa)
        tr_tiles = [
            ("Pay position", f"{snap['pay_score']:.0f}/100" if snap["pay_score"] is not None else "—", C["blue"]),
            ("Benefits position", f"{snap['benefits_score']:.0f}/100", C["violet"]),
            ("Total Rewards score", f"{snap['total_rewards_score']:.0f}/100",
             C["teal"] if snap["total_rewards_score"] >= 50 else C["amber"]),
        ]
        trow2 = "".join(
            f'<div style="flex:1;min-width:150px;background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:24px;'
            f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
            f'letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
            for lab, val, col in tr_tiles)
        st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap">{trow2}</div>', unsafe_allow_html=True)
        st.caption("Pay position = compa-ratio (actual ÷ market P50) rescaled to 0–100 (100 = at market). "
                   "Benefits position = Benefits Richness Index. Total Rewards score is their average — "
                   "an early step toward bringing Pay and Benefits Benchmarking together in one center.")


def _require_password():
    """Shared-password gate. Set `app_password` in Streamlit Secrets
    (Settings → Secrets on Streamlit Cloud) or a JOBSY_PASSWORD env var.
    Fail-closed: if no password is configured, the app stays locked."""
    import os
    if st.session_state.get("_auth_ok"):
        return
    try:
        expected = st.secrets.get("app_password", None)
    except Exception:
        expected = None
    if not expected:
        expected = os.environ.get("JOBSY_PASSWORD")
    st.markdown("### 🔒 Jobsy")
    if not expected:
        st.error("This app is password-protected, but no password is configured yet. "
                 "Add **app_password** under Settings → Secrets (then Reboot), "
                 "or set a JOBSY_PASSWORD environment variable for local use.")
        st.stop()
    st.caption("Enter the access password to continue.")
    pw = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
    if not pw:
        st.stop()
    if pw != expected:
        st.error("Incorrect password."); st.stop()
    st.session_state["_auth_ok"] = True
    (getattr(st, "rerun", None) or getattr(st, "experimental_rerun"))()


def main():
    st.set_page_config(page_title="Jobsy", page_icon="📊",
                       layout="centered", initial_sidebar_state="auto")
    apply_theme()
    _require_password()

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
            # Auto-load from URL param
            qp = st.query_params
            if "session" in qp and "session_loaded" not in st.session_state:
                loaded = _ps_load(qp["session"])
                if loaded:
                    _restore_session(loaded["payload"])
                    st.session_state["session_code"]   = qp["session"]
                    st.session_state["session_loaded"] = True
                    st.caption(f"✓ Session {qp['session']} restored.")

            code = st.session_state.get("session_code","")
            if code:
                st.markdown(
                    f'<div style="font-family:monospace;font-size:13px;font-weight:700;'
                    f'background:#E2F1ED;color:#0E7C66;border-radius:8px;padding:8px 12px;'
                    f'text-align:center;letter-spacing:0.08em">{code}</div>',
                    unsafe_allow_html=True,
                )
                st.caption("Share this code to resume on any device.")
                if st.button("💾 Save progress", use_container_width=True):
                    ok = _ps_save(code, _capture_session(), st.session_state.get("org_label",""))
                    st.success("Saved.") if ok else st.error("Save failed.")
            else:
                org = st.text_input("Organisation label (optional)", key="org_label",
                                    placeholder="Acme BV")
                if st.button("▶ Start new session", use_container_width=True, type="primary"):
                    new_code = _ps_generate()
                    st.session_state["session_code"] = new_code
                    st.query_params["session"] = new_code
                    st.rerun()

            load_code = st.text_input("Load session code", placeholder="JOBSY-XXXXX", key="load_input")
            if st.button("Load →", use_container_width=True) and load_code.strip():
                loaded = _ps_load(load_code.strip())
                if loaded:
                    _restore_session(loaded["payload"])
                    st.session_state["session_code"] = load_code.strip().upper()
                    st.query_params["session"] = load_code.strip().upper()
                    st.success(f"Session restored (created {loaded['created_at'][:10]}).")
                    st.rerun()
                else:
                    st.error("Code not found or expired.")
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
        catalog = load_workbook_catalog(path, _workbook_sig(path))
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
                "Keep these exact headers so Jobsy auto-detects each column; extra columns you add are preserved too.",
                "ActualSalary must be a plain number (68000, not '€68.000' or '68k'). FTE as 1.0 / 0.8. Dates as YYYY-MM-DD.",
                "Add Performance + Potential (1-3) to auto-place people on the 9-Box grid — no re-entry needed.",
                "Put skills in one cell as 'Skill:Level; Skill:Level' under SkillProficiency, or use the dedicated Skills template for a per-skill grid.",
                "Both .csv and .xlsx upload fine.",
            ]}
        )
        st.markdown("**New here?** Download the template, fill in **CurrentTitle** (add salary/gender for Pay Equity), then upload below.")
        _tc1, _tc2 = st.columns(2)
        with _tc1:
            st.download_button(
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
            st.download_button(
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
                    ("✅ Jobsy can give you now", C["success"], _rep["ready"]),
                    ("◐ Assumed from partial data", C["amber"], _rep["assumed"]),
                    ("➕ Add to unlock more", C["accent"], _rep["unlock"]),
                ]
                with st.expander(
                    f"📋 What Jobsy can do with this file — "
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
        st.download_button(
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


def skill_gap_page(catalog, service):
    """Skill Gap & Succession — three sub-tabs."""
    LEVEL_NAMES = {0:"None",1:"Awareness",2:"Developing",3:"Proficient",4:"Advanced",5:"Expert"}
    LEVEL_SORT  = {"Junior":1,"Medior":2,"Senior":3,"Lead":4}

    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Skill Gap & Succession</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Role gaps, batch overview, and succession readiness.</p>',
        unsafe_allow_html=True,
    )

    if not getattr(catalog.repository, "skills", None):
        st.warning("Skills data requires the **Reference workbook**. Switch data source in the sidebar.")
        return

    tab_role, tab_batch, tab_succ, tab_risk = st.tabs(["Role Gap", "Batch Overview", "Succession Planning", "Succession Risk"])

    def readiness_score(gaps):
        if not gaps: return 0
        return round(sum(1 for g in gaps if g["gap"]<=0) / len(gaps) * 100)

    def readiness_label(score):
        if score >= 80: return "Ready now",   C["teal"]
        if score >= 55: return "6-12 months", C["amber"]
        return               "Developing",    C["clay"]

    def gap_bar(current, required, color):
        cp = (current/5)*100; rp = (required/5)*100; gw = max(0, rp-cp)
        return (f'<div style="display:flex;align-items:center;gap:8px">'
                f'<div style="flex:1;position:relative;height:6px;background:#EDF0F3;border-radius:3px">'
                f'<div style="position:absolute;top:0;bottom:0;left:0;width:{cp:.0f}%;background:#C7D1D8;border-radius:3px"></div>'
                f'<div style="position:absolute;top:-1px;bottom:-1px;left:{cp:.0f}%;width:{gw:.0f}%;'
                f'background:{color}44;border:1.5px dashed {color};border-radius:3px"></div>'
                f'</div><span style="font-family:{FONT_MONO};font-size:10px;color:{color};min-width:64px;text-align:right">'
                f'{LEVEL_NAMES.get(required,"")}</span></div>')

    def gap_card(g, show_pathway=True):
        color = C["amber"] if g["gap"]>0 else (C["teal"] if g["gap"]==0 else C["violet"])
        badge = (f'+{g["gap"]} level{"s" if g["gap"]!=1 else ""}' if g["gap"]>0 else
                 ("Ready" if g["gap"]==0 else f'Exceeds +{abs(g["gap"])}'))
        pathway = _pathway_html(g) if show_pathway and g["gap"]>0 else ""
        return (f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-left:4px solid {color};border-radius:12px;padding:12px 14px;margin-bottom:8px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px">'
                f'<div><div style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">{g["skill_name"]}</div>'
                f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};margin-top:2px">'
                f'{g["category"]} · {g["skill_type"]}</div></div>'
                f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:600;'
                f'background:{color}1A;color:{color};border-radius:999px;padding:3px 10px">{badge}</span></div>'
                f'{gap_bar(g["current_level"],g["required_level"],color)}'
                f'{pathway}</div>')

    # ── Tab 1: Role Gap ───────────────────────────────────────────────────
    with tab_role:
        all_jobs = sorted(catalog.repository.jobs.values(), key=lambda j:(j.function,j.standard_title))
        job_opts = {f"{j.standard_title} ({j.function} · {j.level})": j.job_id for j in all_jobs}
        col1,col2 = st.columns(2)
        with col1: from_lbl = st.selectbox("Current role",list(job_opts.keys()),key="gap_from")
        with col2: to_lbl   = st.selectbox("Target role", list(job_opts.keys()),key="gap_to",index=min(1,len(job_opts)-1))
        from_id,to_id = job_opts[from_lbl],job_opts[to_lbl]
        if from_id == to_id:
            st.info("Select a different target role.")
        else:
            cur = {req.skill_id:req.required_level for req,_ in catalog.get_role_skills(from_id)}
            try: gaps = catalog.skill_gap(cur, to_id)
            except Exception as e: st.error(str(e)); gaps=[]
            develop=[g for g in gaps if g["gap"]>0]; matches=[g for g in gaps if g["gap"]==0]; exceeds=[g for g in gaps if g["gap"]<0]
            score=readiness_score(gaps); lbl,lc=readiness_label(score)
            st.markdown(f'<div style="display:flex;gap:10px;margin:12px 0">'
                f'{_stat_card(len(develop),"Develop",C["amber"])}{_stat_card(len(matches),"Ready",C["teal"])}'
                f'{_stat_card(len(exceeds),"Exceeds",C["violet"])}{_stat_card(f"{score}%","Readiness",lc)}'
                f'</div>',unsafe_allow_html=True)
            if develop:
                st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;color:{C["amber"]};margin:14px 0 8px">Skills to develop ({len(develop)})</div>',unsafe_allow_html=True)
                st.markdown("".join(gap_card(g) for g in develop),unsafe_allow_html=True)
            if matches:
                with st.expander(f"Already proficient ({len(matches)})"): st.markdown("".join(gap_card(g) for g in matches),unsafe_allow_html=True)
            if exceeds:
                with st.expander(f"Exceeds requirement ({len(exceeds)})"): st.markdown("".join(gap_card(g) for g in exceeds),unsafe_allow_html=True)
            import io as _io, pandas as _pd
            buf=_io.BytesIO(); _pd.DataFrame(gaps).to_excel(buf,index=False)
            st.download_button("⬇ Download gap report",buf.getvalue(),file_name=f"gap_{from_id}_to_{to_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ── Tab 2: Batch Overview ─────────────────────────────────────────────
    with tab_batch:
        st.markdown(f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:14px">'
            f'Gap to next career step for every matched employee.</p>',unsafe_allow_html=True)
        results_b=st.session_state.get("last_results",[]); df_b=st.session_state.get("upload_df"); nc=st.session_state.get("upload_name_col")
        if not results_b:
            st.info("Upload a file and run a match on the Matching page first.")
        else:
            import pandas as _pd2, io as _io2
            def get_nm(idx):
                if df_b is None: return ""
                row=df_b.iloc[idx] if idx<len(df_b) else None
                if row is None: return ""
                fn=next((str(row[c]) for c in ["FirstName","first_name"] if c in df_b.columns),"")
                ln=next((str(row[c]) for c in ["LastName","last_name"] if c in df_b.columns),"")
                if fn or ln: return (fn+" "+ln).strip()
                return str(row[nc]).strip() if nc and nc in df_b.columns else ""
            rows=[]
            for idx,r in enumerate(results_b):
                if not r.matched: continue
                cp=catalog.repository.career_paths.get(r.job_id)
                nr=""; nd=nr2=ne2=sv=0; tg=""
                if cp and cp.next_job_id:
                    nj=catalog.repository.jobs.get(cp.next_job_id)
                    if nj:
                        nr=nj.standard_title
                        csk={rq.skill_id:rq.required_level for rq,_ in catalog.get_role_skills(r.job_id)}
                        try:
                            gb=catalog.skill_gap(csk,cp.next_job_id)
                            nd=sum(1 for g in gb if g["gap"]>0); nr2=sum(1 for g in gb if g["gap"]==0)
                            ne2=sum(1 for g in gb if g["gap"]<0); sv=readiness_score(gb)
                            tp=[g for g in gb if g["gap"]>0]; tg=tp[0]["skill_name"] if tp else ""
                        except: pass
                rows.append({"Name":get_nm(idx) or "—","Current Role":r.standard_title,"Function":r.function,
                    "Level":r.level,"Next Role":nr or "Top of path","Readiness %":sv,
                    "Skills to Dev":nd,"Skills Ready":nr2,"Exceeds":ne2,"Top Gap":tg,"Confidence":r.confidence})
            if rows:
                df_out=_pd2.DataFrame(rows).sort_values("Readiness %",ascending=False)
                n_ready=(df_out["Readiness %"]>=80).sum()
                st.markdown(f'<div style="display:flex;gap:10px;margin-bottom:14px">'
                    f'{_stat_card(len(df_out),"Employees")}{_stat_card(n_ready,"Ready now",C["teal"])}'
                    f'{_stat_card(f"{round(df_out[chr(82)+chr(101)+chr(97)+chr(100)+chr(105)+chr(110)+chr(101)+chr(115)+chr(115)+chr(32)+chr(37)].mean())!s}%","Avg readiness",C["blue"])}'
                    f'</div>',unsafe_allow_html=True)
                st.dataframe(df_out,use_container_width=True,hide_index=True,
                    column_config={"Readiness %":st.column_config.ProgressColumn("Readiness %",min_value=0,max_value=100,format="%d%%"),
                        "Skills to Dev":st.column_config.NumberColumn("To Develop",format="%d"),
                        "Skills Ready":st.column_config.NumberColumn("Ready",format="%d")})
                buf2=_io2.BytesIO(); df_out.to_excel(buf2,index=False)
                st.download_button("⬇ Download batch overview",buf2.getvalue(),file_name="jobsy_batch_overview.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ── Tab 3: Succession Planning ────────────────────────────────────────
    with tab_succ:
        st.markdown(f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:14px">'
            f'Find the most ready candidates for any role from your employee pool.</p>',unsafe_allow_html=True)
        results_s=st.session_state.get("last_results",[])
        if not results_s:
            st.info("Upload a file and run a match on the Matching page first.")
        else:
            all_jobs_s=sorted(catalog.repository.jobs.values(),key=lambda j:(LEVEL_SORT.get(j.level,9),j.function,j.standard_title))
            job_opts_s={f"{j.standard_title} ({j.function} · {j.level})":j.job_id for j in all_jobs_s}
            target_lbl=st.selectbox("Target role to fill",list(job_opts_s.keys()),key="succ_target")
            target_id=job_opts_s[target_lbl]
            role_pool={}
            for idx,r in enumerate(results_s):
                if r.matched: role_pool.setdefault(r.job_id,[]).append(idx)
            if not role_pool:
                st.warning("No matched employees.")
            else:
                RELATED = {"HR":{"HR","Operations","Legal"},"Finance":{"Finance","Operations","Legal"},
                    "Engineering":{"Engineering","Data","Product"},"Data":{"Data","Engineering","Product"},
                    "Product":{"Product","Engineering","Data"},"Operations":{"Operations","HR","Finance"},
                    "Sales":{"Sales","Marketing","Customer"},"Marketing":{"Marketing","Sales","Customer"},
                    "Customer":{"Customer","Sales","Operations"},"Legal":{"Legal","Finance","HR"}}
                tj=catalog.repository.jobs.get(target_id)
                t_lvl=LEVEL_SORT.get(tj.level if tj else "Lead",4)
                t_fn=tj.function if tj else ""
                rel_fns=RELATED.get(t_fn,{t_fn})
                candidates=[]
                for job_id,indices in role_pool.items():
                    if job_id==target_id: continue
                    fj=catalog.repository.jobs.get(job_id)
                    if not fj: continue
                    f_lvl=LEVEL_SORT.get(fj.level,1); delta=t_lvl-f_lvl
                    same=fj.function==t_fn; rel=fj.function in rel_fns
                    if delta<=0 and not same: continue
                    if delta>2: continue
                    if not rel: continue
                    csk={rq.skill_id:rq.required_level for rq,_ in catalog.get_role_skills(job_id)}
                    try: gs=catalog.skill_gap(csk,target_id)
                    except: gs=[]
                    raw=readiness_score(gs); nd=sum(1 for g in gs if g["gap"]>0)
                    if same and delta==1: sc=min(100,int(raw*1.15)); pipe="Primary pipeline"
                    elif same and delta==0: sc=min(100,int(raw*1.05)); pipe="Lateral"
                    else: sc=max(0,int(raw*0.90)); pipe="Cross-functional"
                    lb,lc=readiness_label(sc); tg=[g["skill_name"] for g in gs if g["gap"]>0][:2]
                    candidates.append({"current_role":fj.standard_title,"function":fj.function,"level":fj.level,
                        "headcount":len(indices),"score":sc,"n_develop":nd,"label":lb,"label_col":lc,
                        "top_gaps":tg,"pipeline":pipe,"same_fn":same})
                PO={"Primary pipeline":0,"Lateral":1,"Cross-functional":2}
                candidates.sort(key=lambda c:(PO.get(c["pipeline"],9),-c["score"],c["n_develop"]))
                if not candidates:
                    st.info("No eligible candidates found for this role.")
                else:
                    cards=""
                    LVC={"Lead":("#ECE7F7","#6A53B0"),"Senior":("#E2F1ED","#0E7C66"),"Medior":("#E6EDF7","#2B5FA6"),"Junior":("#F7EEDD","#B9791A")}
                    for i,c in enumerate(candidates[:12]):
                        lb,lf=LVC.get(c["level"],("#F4F6F8","#5A6B7A"))
                        chips="".join(f'<span style="font-family:{FONT_MONO};font-size:10px;background:#F7EEDD;color:{C["amber"]};border-radius:6px;padding:2px 8px;margin:2px 3px 0 0">{s}</span>' for s in c["top_gaps"]) or f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["teal"]}">All skills met ✓</span>'
                        cards+=(f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-left:4px solid {c["label_col"]};border-radius:12px;padding:13px 14px;margin-bottom:8px">'
                            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">'
                            f'<div style="flex:1"><div style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">#{i+1} &nbsp;{c["current_role"]}</div>'
                            f'<div style="display:flex;align-items:center;gap:6px;margin-top:4px;flex-wrap:wrap">'
                            f'<span style="font-family:{FONT_MONO};font-size:10px;font-weight:500;background:{lb};color:{lf};border-radius:6px;padding:2px 7px">{c["level"]}</span>'
                            f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]}">{c["function"]} · {c["headcount"]} in pool · {c["pipeline"]}</span></div>'
                            f'<div style="margin-top:7px;display:flex;flex-wrap:wrap">{chips}</div></div>'
                            f'<div style="text-align:right;flex-shrink:0"><div style="font-family:{FONT_MONO};font-weight:700;font-size:22px;color:{c["label_col"]};line-height:1">{c["score"]}%</div>'
                            f'<div style="font-family:{FONT_MONO};font-size:10px;color:{c["label_col"]};margin-top:2px">{c["label"]}</div></div></div>'
                            f'<div style="margin-top:10px;height:6px;background:#EDF0F3;border-radius:3px;overflow:hidden">'
                            f'<div style="height:100%;width:{c["score"]}%;background:{c["label_col"]};border-radius:3px"></div></div></div>')
                    st.markdown(cards,unsafe_allow_html=True)
                    import io as _io3, pandas as _pd3
                    sbuf=_io3.BytesIO()
                    _pd3.DataFrame([{"Target":tj.standard_title if tj else "","Pool":c["current_role"],"Function":c["function"],
                        "Level":c["level"],"Headcount":c["headcount"],"Readiness %":c["score"],"Status":c["label"],
                        "Pipeline":c["pipeline"],"To Develop":c["n_develop"],"Top Gap 1":c["top_gaps"][0] if c["top_gaps"] else "",
                        "Top Gap 2":c["top_gaps"][1] if len(c["top_gaps"])>1 else ""} for c in candidates]).to_excel(sbuf,index=False)
                    st.download_button("⬇ Download succession report",sbuf.getvalue(),file_name=f"succession_{target_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


    # ══════════════════════════════════════════════════════════════════════
    # TAB 4 — SUCCESSION RISK
    # ══════════════════════════════════════════════════════════════════════
    with tab_risk:
        st.markdown(
            f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:14px">'
            f'Pipeline coverage for every Lead-level role. Flags where the organisation '
            f'has no ready successor.</p>',
            unsafe_allow_html=True,
        )
        results_r  = st.session_state.get("last_results", [])
        if not results_r:
            st.info("Upload and match a file on the Matching page first.")
        else:
            import pandas as _pdr, io as _ior

            # Build role pool from batch
            role_pool_r = {}
            for idx, r in enumerate(results_r):
                if r.matched:
                    role_pool_r.setdefault(r.job_id, []).append(idx)

            RELATED_R = {
                "HR":{"HR","Operations","Legal"},"Finance":{"Finance","Operations","Legal"},
                "Engineering":{"Engineering","Data","Product"},"Data":{"Data","Engineering","Product"},
                "Product":{"Product","Engineering","Data"},"Operations":{"Operations","HR","Finance"},
                "Sales":{"Sales","Marketing","Customer"},"Marketing":{"Marketing","Sales","Customer"},
                "Customer":{"Customer","Sales","Operations"},"Legal":{"Legal","Finance","HR"},
            }

            # Evaluate all Lead roles
            lead_roles = [j for j in catalog.repository.jobs.values() if j.level == "Lead"]
            risk_rows  = []

            for tj in sorted(lead_roles, key=lambda j: (j.function, j.standard_title)):
                ready_now = 0; near = 0; developing = 0
                for job_id, indices in role_pool_r.items():
                    if job_id == tj.job_id: continue
                    fj = catalog.repository.jobs.get(job_id)
                    if not fj: continue
                    f_lvl   = LEVEL_SORT.get(fj.level, 1)
                    t_lvl   = LEVEL_SORT.get(tj.level, 4)
                    delta   = t_lvl - f_lvl
                    same    = fj.function == tj.function
                    rel     = fj.function in RELATED_R.get(tj.function, {tj.function})
                    if delta <= 0 and not same: continue
                    if delta > 2: continue
                    if not rel: continue
                    csk = {rq.skill_id: rq.required_level for rq, _ in catalog.get_role_skills(job_id)}
                    try: gs = catalog.skill_gap(csk, tj.job_id)
                    except: gs = []
                    if same and delta == 1: sc = min(100, int(readiness_score(gs)*1.15))
                    elif same: sc = min(100, int(readiness_score(gs)*1.05))
                    else: sc = max(0, int(readiness_score(gs)*0.90))
                    n_people = len(indices)
                    if sc >= 80:   ready_now += n_people
                    elif sc >= 55: near      += n_people
                    else:          developing += n_people

                total_pipe = ready_now + near + developing
                if ready_now > 0:   risk = "Covered";  risk_col = C["teal"]
                elif total_pipe > 0: risk = "At Risk";  risk_col = C["amber"]
                else:               risk = "Critical"; risk_col = C["clay"]

                risk_rows.append({
                    "Role":         tj.standard_title,
                    "Function":     tj.function,
                    "Ready Now":    ready_now,
                    "6-12 Months":  near,
                    "Developing":   developing,
                    "Total Pipeline": total_pipe,
                    "Risk":         risk,
                    "_risk_col":    risk_col,
                })

            if not risk_rows:
                st.warning("No roles to evaluate — check data source is Reference workbook.")
            else:
                # Summary
                n_crit = sum(1 for r in risk_rows if r["Risk"]=="Critical")
                n_risk = sum(1 for r in risk_rows if r["Risk"]=="At Risk")
                n_cov  = sum(1 for r in risk_rows if r["Risk"]=="Covered")
                st.markdown(
                    f'<div style="display:flex;gap:10px;margin-bottom:16px">'
                    f'{_stat_card(n_crit,"Critical",C["clay"])}'
                    f'{_stat_card(n_risk,"At Risk",C["amber"])}'
                    f'{_stat_card(n_cov,"Covered",C["teal"])}'
                    f'</div>', unsafe_allow_html=True)

                # Risk cards
                cards_r = ""
                for row in risk_rows:
                    rc = row["_risk_col"]
                    bar_ready = (row["Ready Now"]/max(row["Total Pipeline"],1))*100 if row["Total Pipeline"] else 0
                    bar_near  = (row["6-12 Months"]/max(row["Total Pipeline"],1))*100 if row["Total Pipeline"] else 0
                    pipe_bar = (
                        f'<div style="height:8px;background:#EDF0F3;border-radius:4px;overflow:hidden;display:flex;margin-top:8px">'
                        f'<div style="height:100%;width:{bar_ready:.0f}%;background:{C["teal"]}"></div>'
                        f'<div style="height:100%;width:{bar_near:.0f}%;background:{C["amber"]}"></div>'
                        f'</div>'
                    ) if row["Total Pipeline"] > 0 else (
                        f'<div style="height:8px;background:{C["clay"]}22;border:1px dashed {C["clay"]};border-radius:4px;margin-top:8px"></div>'
                    )
                    cards_r += (
                        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                        f'border-left:4px solid {rc};border-radius:12px;padding:12px 14px;margin-bottom:8px">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center">'
                        f'<div>'
                        f'<div style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">{row["Role"]}</div>'
                        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};margin-top:2px">{row["Function"]} · Lead</div>'
                        f'</div>'
                        f'<div style="text-align:right">'
                        f'<span style="font-family:{FONT_MONO};font-size:12px;font-weight:600;'
                        f'background:{rc}1A;color:{rc};border-radius:999px;padding:3px 10px">{row["Risk"]}</span>'
                        f'</div></div>'
                        f'<div style="display:flex;gap:14px;margin-top:8px">'
                        f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["teal"]}">'
                        f'✓ {row["Ready Now"]} ready now</span>'
                        f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["amber"]}">'
                        f'◑ {row["6-12 Months"]} near</span>'
                        f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">'
                        f'○ {row["Developing"]} developing</span>'
                        f'</div>'
                        f'{pipe_bar}</div>'
                    )
                st.markdown(cards_r, unsafe_allow_html=True)

                # Export
                export_df = _pdr.DataFrame([{k:v for k,v in r.items() if k!="_risk_col"} for r in risk_rows])
                buf_r = _ior.BytesIO(); export_df.to_excel(buf_r, index=False)
                st.download_button("⬇ Download succession risk report", buf_r.getvalue(),
                    file_name="jobsy_succession_risk.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")



def skills_dashboard_page(catalog):
    """Skills-based organisation lens: org-wide skills intelligence (tiles +
    category treemap + demand/supply table) and the per-role proficiency wheel.
    Demand side = the reference library; supply side = assessments uploaded on
    the Skills Assessment page (session), honestly labelled by source."""
    import pandas as _pd
    try:
        from services.skills_dashboard_service import (
            build_wheel_svg, overlay_supply, skill_demand, squarify)
    except ImportError:
        from jobsy.services.skills_dashboard_service import (
            build_wheel_svg, overlay_supply, skill_demand, squarify)

    repo = catalog.repository
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Skills Dashboard</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'The organisation seen through <b>what people can do</b> rather than where they sit '
        f'in a hierarchy. Demand side comes from the role architecture ({len(repo.jobs)} roles); '
        f'supply side appears when assessments are uploaded on the Skills Assessment page.</p>',
        unsafe_allow_html=True,
    )

    # supply: session assessments {emp: {skill_id: level}} -> flat shim list
    _sa = st.session_state.get("skill_assessments") or {}

    class _A:  # noqa: N801 - tiny adapter
        __slots__ = ("skill_id", "current_level")
        def __init__(self, sid, lvl):
            self.skill_id, self.current_level = sid, lvl

    flat = [_A(sid, lvl) for skills in _sa.values() for sid, lvl in skills.items() if lvl and lvl > 0]
    demand = overlay_supply(skill_demand(repo), flat)

    # ── headline tiles ──────────────────────────────────────────────────
    n_cats = len({s.category for s in demand})
    tiles = [("Skill categories", str(n_cats), C["ink"]),
             ("Skills in demand", str(len(demand)), C["violet"]),
             ("Roles architected", str(len(repo.jobs)), C["teal"]),
             ("People assessed", str(len(_sa)) if _sa else "—", C["accent"] if _sa else C["muted"])]
    trow = "".join(
        f'<div style="flex:1;min-width:120px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-radius:12px;padding:14px 16px"><div style="font-family:{FONT_SERIF};font-size:28px;'
        f'font-weight:700;color:{col}">{val}</div><div style="font-family:{FONT_MONO};font-size:10px;'
        f'letter-spacing:.08em;text-transform:uppercase;color:{C["muted"]};margin-top:2px">{lab}</div></div>'
        for lab, val, col in tiles)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">{trow}</div>',
                unsafe_allow_html=True)
    if not _sa:
        st.caption("➕ Upload assessments on the **Skills Assessment** page to light up the supply side "
                   "(holders per skill, held-vs-required overlay on the wheel). Declared ≠ validated — "
                   "the source of each assessment matters and is carried through.")

    # ── category treemap ───────────────────────────────────────────────
    _sizelab = ("people holding (assessments)" if _sa else "requirement instances (role × skill)")
    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:14px 0 6px">'
                f'Skills map — size = {_sizelab}</div>', unsafe_allow_html=True)
    cats = sorted({s.category for s in demand})
    cat_pick = st.selectbox("Category", ["All categories"] + cats, key="sd_cat")
    subset = demand if cat_pick == "All categories" else [s for s in demand if s.category == cat_pick]
    if cat_pick == "All categories":
        items = []
        for c in cats:
            v = sum((s.n_holders if _sa else s.n_roles) for s in demand if s.category == c)
            items.append((c, float(v)))
    else:
        items = [(s.skill_name, float(s.n_holders if _sa else s.n_roles)) for s in subset]
    rects = squarify(items, 0, 0, 100, 56)
    _PALETTE = ["#6F3CFF", "#5C35A3", "#A77BFF", "#4A2A80", "#8850EF", "#3B2064", "#34B5FF", "#22103F"]
    cells = []
    for i, r in enumerate(sorted(rects, key=lambda r: -(r.w * r.h))):
        fs = max(9, min(15, (r.w * r.h) ** 0.5 * 0.55))
        cells.append(
            f'<div style="position:absolute;left:{r.x}%;top:{r.y / 56 * 100}%;width:{r.w}%;'
            f'height:{r.h / 56 * 100}%;background:{_PALETTE[i % len(_PALETTE)]};'
            f'border:1px solid {C["bg"]};border-radius:4px;overflow:hidden;display:flex;'
            f'align-items:center;justify-content:center;text-align:center;padding:2px">'
            f'<span style="font-size:{fs:.0f}px;color:#FFFFFF;line-height:1.15">{r.label}'
            f'<br><span style="opacity:.75;font-size:{fs*0.85:.0f}px">{r.value:.0f}</span></span></div>')
    st.markdown(f'<div style="position:relative;width:100%;aspect-ratio:100/56;'
                f'background:{C["surface"]};border-radius:10px;margin-bottom:14px">{"".join(cells)}</div>',
                unsafe_allow_html=True)

    # ── demand / supply table ──────────────────────────────────────────
    with st.expander(f"Skills table ({len(subset)} in view)"):
        st.caption("Demand = the role architecture (roles requiring, Core count, max required level). "
                   "Supply = uploaded assessments; blank until they exist rather than pretending.")
        tbl = _pd.DataFrame([{
            "Skill": s.skill_name, "Category": s.category, "Roles requiring": s.n_roles,
            "Core in": s.n_core, "Max req. level": s.max_required_level,
            "Holders": (s.n_holders if _sa else None), "Avg level held": s.avg_level_held,
        } for s in sorted(subset, key=lambda s: -(s.n_holders if _sa else s.n_roles))])
        st.dataframe(tbl, use_container_width=True, hide_index=True)

    # ── proficiency wheel ──────────────────────────────────────────────
    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:16px 0 6px">'
                f'Proficiency wheel — required profile per role</div>', unsafe_allow_html=True)
    titles = sorted(j.standard_title for j in repo.jobs.values() if repo.role_skill_map.get(j.job_id))
    role_pick = st.selectbox("Role", titles, key="sd_role")
    job = next(j for j in repo.jobs.values() if j.standard_title == role_pick)
    reqs = [{"skill": (repo.skills[r.skill_id].skill_name if r.skill_id in repo.skills else r.skill_id),
             "level": r.required_level, "type": r.skill_type}
            for r in sorted(repo.role_skill_map.get(job.job_id, []),
                            key=lambda r: (-r.required_level, r.skill_type))]

    overlay = None
    emp_pick = None
    if _sa:
        emp_pick = st.selectbox("Overlay a person (from uploaded assessments)",
                                ["— none —"] + sorted(_sa.keys()), key="sd_emp")
        if emp_pick and emp_pick != "— none —":
            _name_by_id = {sid: (repo.skills[sid].skill_name if sid in repo.skills else sid)
                           for sid in _sa[emp_pick]}
            overlay = {_name_by_id[sid]: lvl for sid, lvl in _sa[emp_pick].items() if lvl and lvl > 0}

    st.markdown(f'<div style="max-width:660px;margin:0 auto">'
                f'{build_wheel_svg(role_pick, reqs, overlay_levels=overlay)}</div>',
                unsafe_allow_html=True)
    _legend = (f'<span style="color:{C["violet"]}">■</span> required level (rings 1–5) &nbsp; '
               f'<b style="font-size:12px">bold</b> = Core skill')
    if overlay:
        _legend += f' &nbsp; <span style="color:{C["accent"]}">■</span> {emp_pick} — current level'
    st.caption(_legend, unsafe_allow_html=True)
    st.caption("Skill-based structure in one picture: the role is its required capability profile, "
               "not a box on an org chart. Overlay a person to see fit and growth edges — gaps are "
               "development conversations, not verdicts.")

    # ── departmental overlap — the mobility corridors ──────────────────
    try:
        from services.skills_dashboard_service import function_overlaps, future_skill_readiness
    except ImportError:
        from jobsy.services.skills_dashboard_service import function_overlaps, future_skill_readiness

    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:22px 0 6px">'
                f'Departmental overlap — shared skills between functions</div>', unsafe_allow_html=True)
    st.caption("Where departments already speak each other's language. High overlap = an internal "
               "mobility corridor: people can cross on capabilities they demonstrably share. "
               "Similarity is cosine on level-weighted skill profiles; 'shared' counts distinct skills.")
    overlaps = function_overlaps(repo)
    if overlaps:
        _otbl = _pd.DataFrame([{
            "Function A": o.function_a, "Function B": o.function_b,
            "Similarity": o.cosine, "Shared skills": len(o.shared_skills),
            "Top shared": ", ".join(o.shared_skills[:3]) + ("…" if len(o.shared_skills) > 3 else ""),
        } for o in overlaps])
        st.dataframe(_otbl, use_container_width=True, hide_index=True,
                     column_config={"Similarity": st.column_config.ProgressColumn(
                         "Similarity", min_value=0.0, max_value=1.0, format="%.2f")})
        _pairs = [f"{o.function_a} ↔ {o.function_b}" for o in overlaps]
        with st.expander("Inspect a corridor — every skill two functions share"):
            _pk = st.selectbox("Function pair", _pairs, key="sd_overlap_pair")
            _o = overlaps[_pairs.index(_pk)]
            if _o.shared_skills:
                st.markdown(" · ".join(f"`{s}`" for s in _o.shared_skills))
                st.caption(f"Jaccard {_o.jaccard:.2f} — these functions share "
                           f"{len(_o.shared_skills)} of their combined distinct skills. Each shared "
                           "skill is a bridge a person can cross without starting over.")
            else:
                st.caption("No shared skills — these functions currently have no direct corridor.")

    # ── skills of the future — sourced overlay vs the org ──────────────
    st.markdown(f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["muted"]};margin:22px 0 6px">'
                f'Skills of the future — what the organisation still misses</div>', unsafe_allow_html=True)
    st.caption("Analytical overlay, not measurement: future-skill demand from sourced research "
               "(WEF Future of Jobs 2025 · LinkedIn Skills on the Rise 2025), matched to this "
               "organisation's own skill catalogue by visible keyword rules — check the match, "
               "don't take it on faith.")
    _future = future_skill_readiness(repo, assessments=flat)
    _fs_color = {"Not in catalogue": C["danger"], "Missing": C["danger"],
                 "Emerging": C["amber"], "Covered": C["teal"]}
    _gaps = [f for f in _future if f.status in ("Not in catalogue", "Missing")]
    if _gaps:
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
            f'border-left:3px solid {C["danger"]};border-radius:10px;padding:12px 14px;margin:8px 0;'
            f'font-size:13.5px;color:{C["ink"]}"><b style="color:{C["danger"]}">Still missing:</b> ' +
            " · ".join(f"<b>{f.name}</b> <span style=\"color:{C['muted']}\">({f.source})</span>" for f in _gaps) +
            '<br><span style="color:' + C["muted"] + ';font-size:12.5px">"Not in catalogue" is the deeper gap: '
            'the taxonomy cannot even see the skill yet — adding it to the catalogue is step one, '
            'requiring it in roles is step two.</span></div>', unsafe_allow_html=True)
    _cards = "".join(
        f'<div style="flex:1;min-width:230px;background:{C["surface"]};border:1px solid {C["line"]};'
        f'border-left:3px solid {_fs_color[f.status]};border-radius:12px;padding:12px 14px">'
        f'<div style="font-size:.92rem;font-weight:600;color:{C["ink"]}">{f.name}</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.06em;text-transform:uppercase;'
        f'color:{C["muted"]};margin:2px 0 6px">{f.source}</div>'
        f'<div style="font-size:.8rem;color:{_fs_color[f.status]};font-weight:700">{f.status}</div>'
        f'<div style="font-size:.78rem;color:{C["muted"]};margin-top:4px">'
        + (f'{f.n_roles_requiring} roles require · ' if f.n_roles_requiring else '')
        + (f'{f.n_holders} people hold · ' if f.n_holders else '')
        + (f'matches: {", ".join(f.matched_skills[:2])}{"…" if len(f.matched_skills) > 2 else ""}'
           if f.matched_skills else 'no catalogue match') + '</div></div>'
        for f in _future)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">{_cards}</div>',
                unsafe_allow_html=True)
    with st.expander("Full match table — how each future skill maps to the catalogue"):
        st.dataframe(_pd.DataFrame([{
            "Future skill": f.name, "Source": f.source, "Status": f.status,
            "Roles requiring": f.n_roles_requiring, "People holding": (f.n_holders or None),
            "Catalogue matches": ", ".join(f.matched_skills) or "—",
        } for f in _future]), use_container_width=True, hide_index=True)


def skill_assessment_page(catalog):
    """Upload individual skill assessments — actual levels per person per skill."""
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Skills Assessment</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Upload actual assessed skill levels per person. These replace role-assumed '
        f'levels in gap analysis for a true individual view.</p>',
        unsafe_allow_html=True,
    )

    import pandas as _pdsa, io as _iosa

    if not getattr(catalog.repository, "skills", None):
        st.warning("Skills data requires the **Reference workbook**.")
        return

    # ── Template download ────────────────────────────────────────────────
    skills_list = sorted(catalog.repository.skills.values(), key=lambda s: (s.category, s.skill_name))
    tmpl_cols   = ["EmployeeID","Name","CurrentRole"] + [s.skill_name for s in skills_list]
    tmpl_df     = _pdsa.DataFrame(columns=tmpl_cols)
    # Add two sample rows
    sample_skills = {s.skill_name: "" for s in skills_list}
    tmpl_df = _pdsa.concat([tmpl_df, _pdsa.DataFrame([
        {"EmployeeID":"E1001","Name":"Eva de Vries","CurrentRole":"Chief Executive Officer", **sample_skills},
        {"EmployeeID":"E1002","Name":"Sem Meijer",  "CurrentRole":"Chief Financial Officer", **sample_skills},
    ])], ignore_index=True)
    # Behavioural rubric (1-5 anchors per skill category) — for the template + UI
    _rubric = catalog.proficiency_rubric() if hasattr(catalog, "proficiency_rubric") else {}
    _rubric_rows = [
        {"Skill Category": cat, "Level": lvl,
         "Level Name": _rubric[cat].get(lvl, {}).get("name", ""),
         "What it looks like": _rubric[cat].get(lvl, {}).get("anchor", "")}
        for cat in sorted(_rubric) for lvl in range(1, 6) if _rubric[cat].get(lvl)
    ]
    tmpl_buf = _iosa.BytesIO()
    with _pdsa.ExcelWriter(tmpl_buf, engine="openpyxl") as _xl:
        tmpl_df.to_excel(_xl, index=False, sheet_name="Assessment")
        if _rubric_rows:
            _pdsa.DataFrame(_rubric_rows).to_excel(_xl, index=False, sheet_name="Proficiency Rubric")
    st.download_button("⬇ Download assessment template (.xlsx)", tmpl_buf.getvalue(),
        file_name="jobsy_skills_assessment_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ── Proficiency rubric reference ─────────────────────────────────────
    if _rubric:
        with st.expander("📊 Proficiency rubric — what levels 1–5 mean for each skill category"):
            st.caption("Score people against these behavioural anchors so ratings stay consistent "
                       "across assessors. Included as a sheet in the template above.")
            for cat in sorted(_rubric):
                rows = "".join(
                    f'<div style="display:flex;gap:10px;margin:3px 0">'
                    f'<span style="flex:0 0 24px;font-family:{FONT_MONO};font-weight:700;color:{C["teal"]}">{lvl}</span>'
                    f'<span style="flex:0 0 92px;font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">'
                    f'{_rubric[cat].get(lvl, {}).get("name", "")}</span>'
                    f'<span style="font-size:13px;color:{C["ink"]}">'
                    f'{_rubric[cat].get(lvl, {}).get("anchor", "")}</span></div>'
                    for lvl in range(1, 6) if _rubric[cat].get(lvl)
                )
                st.markdown(
                    f'<div style="margin:10px 0 6px;font-family:{FONT_SANS};font-weight:600;'
                    f'font-size:14px;color:{C["ink"]}">{cat}</div>{rows}',
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Upload ───────────────────────────────────────────────────────────
    upload_sa = st.file_uploader("Upload completed assessment (.csv or .xlsx)",
                                  type=["csv","xlsx"], key="sa_upload")
    df_sa = None
    if upload_sa:
        df_sa = (_pdsa.read_csv(upload_sa) if upload_sa.name.endswith(".csv")
                 else _pdsa.read_excel(upload_sa))
    else:
        # Reuse the workforce file from Matching if it carries skill proficiencies.
        _wf = st.session_state.get("upload_df")
        if _wf is not None and _smart_detect(list(_wf.columns),
                {"skillproficiency", "skill proficiency", "skills", "coreskillproficiency"},
                ["proficiency", "skill"]):
            if st.checkbox(f"Use the workforce data uploaded on Matching "
                           f"({len(_wf)} rows, has skill proficiencies)", value=True, key="sa_reuse"):
                df_sa = _wf.copy()
    if df_sa is None:
        existing = st.session_state.get("skill_assessments")
        if existing:
            n_people = len(existing)
            n_skills = max((len(v) for v in existing.values()), default=0)
            st.info(
                f"✓ **{n_people} people** with up to **{n_skills} skills** loaded from your previous upload.  \n"
                f"Upload a new file to replace, or use the selector below to analyse."
            )
            _show_assessment_preview(catalog, existing)
        else:
            st.markdown(
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-radius:12px;padding:16px;color:{C["muted"]};font-size:14px;margin-top:4px">'
                f'Download the template above, fill in skill levels (1–5 or text), '
                f'then upload it here.</div>',
                unsafe_allow_html=True,
            )
        return

    skill_name_to_id = {s.skill_name.lower(): s.skill_id
                        for s in catalog.repository.skills.values()}
    assessments = {}  # {employee_key: {skill_id: level}}

    # ── Detect format ────────────────────────────────────────────────────
    lower_cols = [c.lower() for c in df_sa.columns]

    # Tagged format: columns like CoreSkillProficiency containing "SkillName:Level;..."
    proficiency_cols = [c for c in df_sa.columns
                        if any(k in c.lower() for k in ["proficiency","assessment","skills_level"])]
    plain_skill_cols = [c for c in df_sa.columns
                        if any(k in c.lower() for k in ["softskill","soft_skill"]) and "proficiency" not in c.lower()]

    is_tagged  = any(
        ":" in str(v)
        for col in proficiency_cols
        for v in df_sa[col].dropna().head(5)
    )
    is_long = ("skillname" in lower_cols or "skill_name" in lower_cols
               or "skill name" in lower_cols)

    id_col   = next((c for c in df_sa.columns if c.lower() in ["employeeid","employee_id","id"]), df_sa.columns[0])
    fn_col   = next((c for c in df_sa.columns if c.lower() in ["firstname","first_name"]), None)
    ln_col   = next((c for c in df_sa.columns if c.lower() in ["lastname","last_name"]),  None)

    def emp_key(row):
        eid = str(row[id_col]).strip()
        if fn_col and ln_col:
            name = (str(row.get(fn_col,""))+" "+str(row.get(ln_col,""))).strip()
            return f"{name} ({eid})" if name else eid
        return eid

    if is_tagged:
        # Format: CoreSkillProficiency = "Leadership:Expert;Strategy:Advanced"
        # Also SoftSkills = "Communication;Teamwork" (no levels — default to Proficient=3)
        for _, row in df_sa.iterrows():
            emp = emp_key(row)
            emp_skills = {}
            for col in proficiency_cols:
                val = str(row.get(col,"")).strip()
                if not val or val.lower() == "nan": continue
                for pair in val.split(";"):
                    pair = pair.strip()
                    if ":" in pair:
                        raw_name, raw_level = pair.rsplit(":",1)
                    else:
                        raw_name, raw_level = pair, "Proficient"
                    sid = _resolve_skill_name(raw_name.strip(), skill_name_to_id)
                    if not sid: continue
                    lv = LEVEL_TEXT_MAP.get(raw_level.strip().lower(), 3)
                    emp_skills[sid] = lv
            for col in plain_skill_cols:
                val = str(row.get(col,"")).strip()
                if not val or val.lower() == "nan": continue
                for sk in val.split(";"):
                    sid = _resolve_skill_name(sk.strip(), skill_name_to_id)
                    if sid and sid not in emp_skills:
                        emp_skills[sid] = 3  # default Proficient for unlevelled skills
            if emp_skills:
                assessments[emp] = emp_skills

    elif is_long:
        sk_col = next((c for c in df_sa.columns if "skill" in c.lower() and "name" in c.lower()), None)
        lv_col = next((c for c in df_sa.columns if "level" in c.lower() or "score" in c.lower()), None)
        if not sk_col or not lv_col:
            st.error("Long format needs columns: [EmployeeID/Name], [SkillName], [Level]"); return
        for _, row in df_sa.iterrows():
            emp = emp_key(row)
            sid = _resolve_skill_name(str(row[sk_col]).strip(), skill_name_to_id)
            if not sid: continue
            raw_lv = str(row[lv_col]).strip().lower()
            lv = LEVEL_TEXT_MAP.get(raw_lv) or (int(float(raw_lv)) if raw_lv.replace(".","").isdigit() else 3)
            assessments.setdefault(emp, {})[sid] = max(0, min(5, lv))

    else:
        # Wide format: skill names as column headers (match via alias table)
        skill_cols = [c for c in df_sa.columns
                      if _resolve_skill_name(c, skill_name_to_id) is not None]
        if not skill_cols:
            st.warning(
                "No skill columns recognised. Either:\n"
                "- Use the **Download template** above (exact skill names pre-filled), or\n"
                "- Name columns to match the reference library (e.g. *Team leadership and development*, "
                "*SQL and database querying*, *Financial modelling*), or\n"
                "- Use the tagged format in a *Proficiency* column: `Leadership:Advanced;Finance:Expert`"
            ); return
        for _, row in df_sa.iterrows():
            emp = emp_key(row)
            emp_skills = {}
            for col in skill_cols:
                val = row[col]
                if _pdsa.isna(val) or str(val).strip() == "": continue
                raw_lv = str(val).strip().lower()
                lv = LEVEL_TEXT_MAP.get(raw_lv) or int(float(raw_lv)) if raw_lv.replace(".","").isdigit() else None
                if lv is None: continue
                sid = _resolve_skill_name(col, skill_name_to_id)
                if sid: emp_skills[sid] = max(0, min(5, lv))
            if emp_skills:
                assessments[emp] = emp_skills

    if not assessments:
        st.error("No valid skill data found. Check the file matches the template format."); return

    st.session_state["skill_assessments"] = assessments
    st.success(f"✓ Loaded assessments for **{len(assessments)} people** covering "
               f"{max(len(v) for v in assessments.values())} skills each.")
    _show_assessment_preview(catalog, assessments)


def _show_assessment_preview(catalog, assessments):
    """Show a summary and per-person gap analysis using actual assessed levels."""
    import pandas as _pdp

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    emp_list = sorted(assessments.keys())
    selected = st.selectbox("View individual gap analysis for:", emp_list, key="sa_emp_sel")
    if not selected: return

    emp_skills = assessments[selected]
    assessed_count = len(emp_skills)
    avg_level = round(sum(emp_skills.values())/assessed_count, 1) if assessed_count else 0

    st.markdown(
        f'<div style="display:flex;gap:10px;margin:12px 0">'
        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-radius:12px;'
        f'padding:14px 18px;flex:1;text-align:center">'
        f'<div style="font-size:24px;font-weight:700;color:{C["teal"]}">{assessed_count}</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};letter-spacing:.1em">SKILLS ASSESSED</div></div>'
        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-radius:12px;'
        f'padding:14px 18px;flex:1;text-align:center">'
        f'<div style="font-size:24px;font-weight:700;color:{C["blue"]}">{avg_level}</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};letter-spacing:.1em">AVG LEVEL</div></div>'
        f'</div>', unsafe_allow_html=True)

    # target role selector
    all_jobs = sorted(catalog.repository.jobs.values(), key=lambda j:(j.function,j.standard_title))
    job_opts = {f"{j.standard_title} ({j.function} · {j.level})": j.job_id for j in all_jobs}
    target_lbl = st.selectbox("Assess readiness for target role:", list(job_opts.keys()), key="sa_target")
    target_id  = job_opts[target_lbl]

    try:
        gaps   = catalog.skill_gap(emp_skills, target_id)
    except Exception as e:
        st.error(str(e)); return

    develop = [g for g in gaps if g["gap"]>0]
    matches = [g for g in gaps if g["gap"]==0]
    exceeds = [g for g in gaps if g["gap"]<0]
    LEVEL_NAMES = {0:"None",1:"Awareness",2:"Developing",3:"Proficient",4:"Advanced",5:"Expert"}

    def rs(gs): return round(sum(1 for g in gs if g["gap"]<=0)/len(gs)*100) if gs else 0
    score = rs(gaps)
    lbl   = "Ready now" if score>=80 else ("6–12 months" if score>=55 else "Developing")
    lc    = C["teal"] if score>=80 else (C["amber"] if score>=55 else C["clay"])

    st.markdown(
        f'<div style="display:flex;gap:10px;margin:12px 0">'
        f'<div style="background:{C["surface"]};border:1px solid {C["line"]};border-radius:12px;'
        f'padding:14px 18px;flex:1;text-align:center">'
        f'<div style="font-size:26px;font-weight:700;color:{lc}">{score}%</div>'
        f'<div style="font-family:{FONT_MONO};font-size:10px;color:{lc};letter-spacing:.1em">{lbl.upper()}</div></div>'
        f'{_stat_card(len(develop),"To Develop",C["amber"])}'
        f'{_stat_card(len(matches),"Ready",C["teal"])}'
        f'</div>', unsafe_allow_html=True)

    if develop:
        st.markdown(
            f'<div style="font-family:{FONT_MONO};font-size:11px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{C["amber"]};margin:14px 0 8px">'
            f'Skills to develop — {selected}</div>', unsafe_allow_html=True)
        cards = ""
        for g in develop:
            color = C["amber"]
            cp=(g["current_level"]/5)*100; rp=(g["required_level"]/5)*100; gw=max(0,rp-cp)
            pathway = _pathway_html(g)
            cards += (
                f'<div style="background:{C["surface"]};border:1px solid {C["line"]};'
                f'border-left:4px solid {color};border-radius:12px;padding:12px 14px;margin-bottom:8px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px">'
                f'<div><div style="font-family:{FONT_SANS};font-size:13px;font-weight:600;color:{C["ink"]}">{g["skill_name"]}</div>'
                f'<div style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};margin-top:2px">{g["category"]} · {g["skill_type"]}</div></div>'
                f'<span style="font-family:{FONT_MONO};font-size:11px;font-weight:600;background:{color}1A;'
                f'color:{color};border-radius:999px;padding:3px 10px">+{g["gap"]} level{"s" if g["gap"]!=1 else ""}</span></div>'
                f'<div style="display:flex;align-items:center;gap:8px">'
                f'<div style="flex:1;position:relative;height:6px;background:#EDF0F3;border-radius:3px">'
                f'<div style="position:absolute;top:0;bottom:0;left:0;width:{cp:.0f}%;background:{C["teal"]};border-radius:3px"></div>'
                f'<div style="position:absolute;top:-1px;bottom:-1px;left:{cp:.0f}%;width:{gw:.0f}%;'
                f'background:{color}44;border:1.5px dashed {color};border-radius:3px"></div></div>'
                f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["muted"]};min-width:80px">'
                f'{LEVEL_NAMES.get(g["current_level"],"None")} → {LEVEL_NAMES.get(g["required_level"],"")}</span></div>'
                f'{pathway}</div>'
            )
        st.markdown(cards, unsafe_allow_html=True)
    if matches:
        with st.expander(f"Already proficient ({len(matches)})"):
            st.markdown("".join(
                f'<div style="padding:6px 0;border-bottom:1px solid {C["line"]};font-family:{FONT_SANS};font-size:13px;color:{C["ink"]}">'
                f'✓ {g["skill_name"]} <span style="font-family:{FONT_MONO};font-size:10px;color:{C["teal"]}">{LEVEL_NAMES.get(g["current_level"],"")}</span></div>'
                for g in matches), unsafe_allow_html=True)

    # Export personal development plan
    rows = [{"Skill":g["skill_name"],"Category":g["category"],"Type":g["skill_type"],
             "Current Level":LEVEL_NAMES.get(g["current_level"],"None"),
             "Required Level":LEVEL_NAMES.get(g["required_level"],""),
             "Gap":g["gap"],"Status":g["status"],
             "Development Action":_get_pathway(g["category"],g["gap"])[0] if g["gap"]>0 else "",
             "Method":_get_pathway(g["category"],g["gap"])[1] if g["gap"]>0 else "",
             "Estimated Duration":_get_pathway(g["category"],g["gap"])[2] if g["gap"]>0 else ""}
            for g in gaps]
    import io as _ioex, pandas as _pdex
    buf_ex = _ioex.BytesIO(); _pdex.DataFrame(rows).to_excel(buf_ex, index=False)
    st.download_button(f"⬇ Download development plan — {selected}", buf_ex.getvalue(),
        file_name=f"dev_plan_{selected.replace(' ','_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _build_org_json(df_input, results, title_col):
    """Build dept-first tree: Company → Departments → Employees."""
    import json as _j, pandas as _pd2
    id_col  = next((c for c in ["EmployeeID","employee_id","ID"] if c in df_input.columns), None)
    mgr_col = next((c for c in ["ManagerID","manager_id","ReportsTo"] if c in df_input.columns), None)
    dept_col= next((c for c in ["Department","department","Dept","BusinessUnit"] if c in df_input.columns), None)
    fn_col  = next((c for c in ["FirstName","first_name"] if c in df_input.columns), None)
    ln_col  = next((c for c in ["LastName","last_name"]   if c in df_input.columns), None)
    LSORT={"Lead":0,"Senior":1,"Medior":2,"Junior":3}
    LCOL={"Lead":"#6A53B0","Senior":"#0E7C66","Medior":"#2B5FA6","Junior":"#B9791A"}
    DCOL={"Executive":"#17212E","Finance":"#0E7C66","HR":"#2B5FA6","IT":"#B9791A",
          "Engineering":"#0E7C66","Sales":"#A8443A","Marketing":"#6A53B0",
          "Operations":"#5A6B7A","Warehouse":"#8B6914","Legal":"#2B5FA6",
          "Customer Service":"#0E7C66","Support":"#5A6B7A"}
    def gname(row):
        if fn_col and ln_col: return (str(row.get(fn_col,""))+" "+str(row.get(ln_col,""))).strip()
        return str(row.get("Name","")).strip()
    dept_groups={}
    for idx,row in df_input.iterrows():
        eid=str(row[id_col]) if id_col else str(idx)
        dept=str(row[dept_col]).strip() if dept_col else "Other"
        name=gname(row) or eid
        it=str(row.get(title_col,"")).strip() if title_col else ""
        r=results[int(idx)] if int(idx)<len(results) else None
        mt=r.standard_title if r and r.matched else it
        lv=r.level          if r and r.matched else ""
        emp={"id":eid,"name":name,"input_title":it,"matched_title":mt,"level":lv,
             "dept":dept,"type":"employee","color":LCOL.get(lv,"#5A6B7A"),"children":[]}
        dept_groups.setdefault(dept,[]).append(emp)
    for d in dept_groups:
        dept_groups[d].sort(key=lambda x:(LSORT.get(x["level"],9),x["name"]))
    # check for real hierarchy
    use_real=False
    if mgr_col and id_col:
        all_ids=set(str(r[id_col]) for _,r in df_input.iterrows())
        mc={}
        for _,row in df_input.iterrows():
            m=str(row[mgr_col]) if _pd2.notna(row.get(mgr_col)) else None
            if m and m in all_ids: mc[m]=mc.get(m,0)+1
        if mc: use_real=(max(mc.values())/len(df_input))<0.40
    if use_real:
        nodes={}
        for idx,row in df_input.iterrows():
            eid=str(row[id_col]); mid=str(row[mgr_col]) if _pd2.notna(row.get(mgr_col)) else None
            dept=str(row[dept_col]).strip() if dept_col else "Other"; name=gname(row) or eid
            it=str(row.get(title_col,"")).strip() if title_col else ""
            r=results[int(idx)] if int(idx)<len(results) else None
            nodes[eid]={"id":eid,"name":name,"input_title":it,
                "matched_title":r.standard_title if r and r.matched else it,
                "level":r.level if r and r.matched else "","dept":dept,"type":"employee",
                "color":LCOL.get(r.level if r and r.matched else "","#5A6B7A"),"manager_id":mid,"children":[]}
        roots=[]
        for eid,n in nodes.items():
            m=n.get("manager_id")
            if m and m in nodes: nodes[m]["children"].append(n)
            else: roots.append(n)
        root=roots[0] if len(roots)==1 else {"id":"__root__","name":"Organisation","type":"root",
            "color":"#17212E","matched_title":"","level":"","dept":"","children":roots}
        return _j.dumps(root,default=str)
    dept_nodes=[{"id":f"dept-{d}","name":d,"matched_title":f"{len(m)} employees","level":"",
        "dept":d,"type":"department","color":DCOL.get(d,"#5A6B7A"),"children":m}
        for d,m in sorted(dept_groups.items())]
    return _j.dumps({"id":"__root__","name":"Organisation","type":"root","color":"#17212E",
        "matched_title":f"{len(df_input)} employees","level":"","dept":"","children":dept_nodes},default=str)


def organigram_page(catalog):
    """Interactive D3 organigram."""
    st.markdown(f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Organigram</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Reporting lines and hierarchy based on matched roles and seniority.</p>',
        unsafe_allow_html=True)
    results=st.session_state.get("last_results",[]); df_input=st.session_state.get("upload_df")
    title_col=st.session_state.get("upload_title_col","JobTitle")
    if not results or df_input is None:
        st.info("Upload a file and run a match on the Matching page first."); return
    try:
        tree_json=_build_org_json(df_input,results,title_col)
    except Exception as exc:
        st.error(f"Could not build org tree: {exc}"); return
    total=len(results); matched=sum(1 for r in results if r.matched)
    st.markdown(f'<div style="display:flex;gap:10px;margin-bottom:16px">'
        f'{_stat_card(total,"Employees")}{_stat_card(matched,"Matched",C["teal"])}</div>',
        unsafe_allow_html=True)
    st.caption("Tap any node to expand or collapse. Pinch or scroll to zoom. Drag to pan.")
    import streamlit.components.v1 as components
    components.html(_orgchart_html(tree_json), height=700, scrolling=True)


def _orgchart_html(tree_json):
    return f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#ECEEF0;font-family:Arial,sans-serif;overflow:hidden}}
#chart{{width:100%;height:700px;position:relative}}
svg{{width:100%;height:100%}}
.node rect{{rx:8;ry:8;stroke:rgba(0,0,0,0.08);stroke-width:1;cursor:pointer;filter:drop-shadow(0 2px 6px rgba(0,0,0,0.12))}}
.node rect:hover{{opacity:0.85}}
.node text{{pointer-events:none;font-family:Arial,sans-serif}}
.link{{fill:none;stroke:#C7D1D8;stroke-width:1.5}}
#tip{{position:fixed;background:#17212E;color:#fff;border-radius:8px;padding:8px 12px;font-size:12px;pointer-events:none;opacity:0;transition:opacity .15s;max-width:200px;z-index:999}}
#ctrl{{position:absolute;top:10px;right:10px;display:flex;flex-direction:column;gap:6px}}
.cb{{width:32px;height:32px;background:#fff;border:1px solid #D9E0E5;border-radius:8px;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,0.1);user-select:none}}
#leg{{position:absolute;bottom:10px;left:10px;background:#fff;border:1px solid #D9E0E5;border-radius:10px;padding:8px 12px;font-size:11px;display:flex;gap:10px;flex-wrap:wrap}}
.li{{display:flex;align-items:center;gap:4px}}
.ld{{width:10px;height:10px;border-radius:50%}}
</style>
</head>
<body>
<div id="chart">
<svg id="svg"></svg>
<div id="ctrl">
  <div class="cb" id="zi">+</div>
  <div class="cb" id="zo">−</div>
  <div class="cb" id="zr">⌂</div>
</div>
<div id="leg">
  <div class="li"><div class="ld" style="background:#6A53B0"></div>Lead</div>
  <div class="li"><div class="ld" style="background:#0E7C66"></div>Senior</div>
  <div class="li"><div class="ld" style="background:#2B5FA6"></div>Medior</div>
  <div class="li"><div class="ld" style="background:#B9791A"></div>Junior</div>
  <div class="li"><div class="ld" style="background:#5A6B7A"></div>Dept</div>
</div>
</div>
<div id="tip"></div>
<script>
const D={tree_json};
const W=document.getElementById("chart").clientWidth||900,H=700;
const NW=175,NH=48,DX=62,DY=225,DUR=380;
const svg=d3.select("#svg");
const g=svg.append("g");
const zoom=d3.zoom().scaleExtent([0.1,3]).on("zoom",e=>g.attr("transform",e.transform));
svg.call(zoom);
document.getElementById("zi").onclick=()=>svg.transition().call(zoom.scaleBy,1.3);
document.getElementById("zo").onclick=()=>svg.transition().call(zoom.scaleBy,0.77);
document.getElementById("zr").onclick=()=>svg.transition().duration(400).call(zoom.transform,d3.zoomIdentity.translate(60,H/2).scale(0.9));
const treeFn=d3.tree().nodeSize([DX,DY]);
let root=d3.hierarchy(D,d=>d.children||[]);
root.x0=H/2; root.y0=0;
function collapse(d,md,cd){{
  if(!d.children)return;
  if(cd>=md){{d._children=d.children;d.children=null;}}
  else d.children.forEach(c=>collapse(c,md,cd+1));
}}
collapse(root,1,0);
const tip=document.getElementById("tip");
function showTip(e,d){{
  const n=d.data;
  tip.innerHTML=`<b>${{n.name||n.id}}</b><br>${{n.input_title||""}}${{n.matched_title&&n.matched_title!==n.input_title?"<br>→ "+n.matched_title:""}}${{n.level?"<br><span style='opacity:.7'>"+n.level+"</span>":""}}`;
  tip.style.opacity=1;tip.style.left=(e.clientX+10)+"px";tip.style.top=(e.clientY-10)+"px";
}}
const diag=d3.linkHorizontal().x(d=>d.y).y(d=>d.x);
function update(src){{
  treeFn(root);
  const nodes=root.descendants(),links=root.links();
  const link=g.selectAll("path.link").data(links,d=>d.target.data.id);
  const lE=link.enter().append("path").attr("class","link").attr("d",()=>{{const o={{x:src.x0,y:src.y0}};return diag({{source:o,target:o}});}});
  link.merge(lE).transition().duration(DUR).attr("d",diag);
  link.exit().transition().duration(DUR).attr("d",()=>{{const o={{x:src.x,y:src.y}};return diag({{source:o,target:o}});}}).remove();
  const node=g.selectAll("g.node").data(nodes,d=>d.data.id);
  const nE=node.enter().append("g").attr("class","node")
    .attr("transform",()=>`translate(${{src.y0}},${{src.x0}})`)
    .on("click",(e,d)=>{{if(d.children){{d._children=d.children;d.children=null;}}else if(d._children){{d.children=d._children;d._children=null;}}update(d);}})
    .on("mouseover",showTip).on("mouseout",()=>tip.style.opacity=0)
    .on("touchstart",showTip,{{passive:true}}).on("touchend",()=>tip.style.opacity=0);
  nE.append("rect").attr("x",-NW/2).attr("y",-NH/2).attr("width",NW).attr("height",NH)
    .attr("fill",d=>d.data.color||"#5A6B7A").attr("opacity",0.92);
  nE.append("text").attr("dy",d=>d.data.type==="department"?5:-8).attr("text-anchor","middle")
    .attr("fill","#fff").attr("font-size",d=>d.data.type==="department"?12:11).attr("font-weight","bold")
    .text(d=>{{const n=d.data.name||d.data.id;return n.length>20?n.substring(0,19)+"…":n;}});
  nE.append("text").attr("class","sub").attr("dy",8).attr("text-anchor","middle")
    .attr("fill","rgba(255,255,255,0.82)").attr("font-size",10);
  nE.append("text").attr("class","tog").attr("dy",NH/2-4).attr("text-anchor","middle")
    .attr("fill","rgba(255,255,255,0.6)").attr("font-size",9);
  const nU=node.merge(nE);
  nU.transition().duration(DUR).attr("transform",d=>`translate(${{d.y}},${{d.x}})`);
  nU.select(".sub").text(d=>{{
    if(d.data.type==="department"){{const k=(d.children||d._children||[]);return k.length+" people";}}
    const t=d.data.matched_title||d.data.input_title||"";return t.length>24?t.substring(0,23)+"…":t;
  }});
  nU.select(".tog").text(d=>d._children?`▶ ${{(d._children||[]).length}}`:(d.children&&d.children.length?"▼":""));
  node.exit().transition().duration(DUR).attr("transform",()=>`translate(${{src.y}},${{src.x}})`).remove();
  nodes.forEach(d=>{{d.x0=d.x;d.y0=d.y;}});
}}
update(root);
svg.call(zoom.transform,d3.zoomIdentity.translate(60,H/2).scale(0.9));
</script>
</body>
</html>"""


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


def nine_box_page(catalog):
    """9-box grid: Performance × Potential for succession weighting."""
    st.markdown(
        f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">9-Box Grid</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Plot employees on the performance × potential matrix. '
        f'Scores feed succession weighting.</p>',
        unsafe_allow_html=True,
    )

    results   = st.session_state.get("last_results",[])
    df_input  = st.session_state.get("upload_df")
    title_col = st.session_state.get("upload_title_col","JobTitle")

    import pandas as _pd9, io as _io9

    fn_col = next((c for c in (df_input.columns if df_input is not None else [])
                   if c.lower() in ["firstname","first_name"]), None)
    ln_col = next((c for c in (df_input.columns if df_input is not None else [])
                   if c.lower() in ["lastname","last_name"]), None)
    id_col = next((c for c in (df_input.columns if df_input is not None else [])
                   if c.lower() in ["employeeid","employee_id","id"]), None)

    def get_name(idx):
        if df_input is None or idx >= len(df_input): return f"Employee {idx+1}"
        row = df_input.iloc[idx]
        if fn_col and ln_col: return (str(row.get(fn_col,""))+" "+str(row.get(ln_col,""))).strip()
        return str(row.get(id_col,f"Employee {idx+1}"))

    # ── Load or initialise ratings ───────────────────────────────────────
    if "ninebox_ratings" not in st.session_state:
        st.session_state["ninebox_ratings"] = {}
    ratings = st.session_state["ninebox_ratings"]

    tab_input, tab_grid, tab_export = st.tabs(["Rate Employees","View Grid","Export"])

    PERF_LABELS = {1:"Low performer",2:"Effective performer",3:"Top performer"}
    POT_LABELS  = {1:"Limited potential",2:"Growth potential",3:"High potential"}
    BOX_LABELS  = {
        (3,3):"Star","(3,2)":"High performer","(3,1)":"Solid professional",
        (2,3):"Future star","(2,2)":"Core contributor","(2,1)":"Effective specialist",
        (1,3):"Rough diamond","(1,2)":"Inconsistent player","(1,1)":"Underperformer",
    }
    BOX_COLORS = {
        (3,3):"#0E7C66",(3,2):"#2B9E7E",(3,1):"#4DB89A",
        (2,3):"#2B5FA6",(2,2):"#5A7FC5",(2,1):"#8EA8DC",
        (1,3):"#B9791A",(1,2):"#D4955E",(1,1):"#E8B894",
    }

    def box_label(perf, pot):
        return BOX_LABELS.get((perf,pot), BOX_LABELS.get(f"({perf},{pot})", ""))

    # ── Tab 1: Rate ──────────────────────────────────────────────────────
    with tab_input:
        if not results:
            st.info("Run a match on the Matching page first.")
        else:
            matched_all = [(i,r) for i,r in enumerate(results) if r.matched]

            # Auto-seed ratings from the workforce file if it carries Performance/Potential
            # columns (keyed by row index so it always aligns with get_name).
            if df_input is not None and not ratings:
                _pc = next((c for c in df_input.columns if "perf" in c.lower()), None)
                _ptc = next((c for c in df_input.columns if "pot" in c.lower()), None)
                if _pc and _ptc:
                    _seeded = 0
                    for _i, _r in matched_all:
                        if _i < len(df_input):
                            try:
                                _p = max(1, min(3, int(float(df_input.iloc[_i][_pc]))))
                                _pt = max(1, min(3, int(float(df_input.iloc[_i][_ptc]))))
                                ratings[get_name(_i)] = (_p, _pt)
                                _seeded += 1
                            except Exception:
                                pass
                    if _seeded:
                        st.session_state["ninebox_ratings"] = ratings
                        st.caption(f"↩ Seeded **{_seeded}** ratings from Performance/Potential columns "
                                   "in your uploaded workforce file — edit below if needed.")

            col_a, col_b = st.columns([1,1])
            with col_a:
                # Download template pre-filled with all employees
                tmpl_rows = [{"Employee": get_name(i), "Role": r.standard_title,
                              "Performance (1-3)": "", "Potential (1-3)": ""}
                             for i,r in matched_all]
                tmpl_r = _pd9.DataFrame(tmpl_rows)
                tbuf = _io9.BytesIO(); tmpl_r.to_excel(tbuf, index=False)
                st.download_button("⬇ Download template", tbuf.getvalue(),
                    file_name="jobsy_9box_template.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            with col_b:
                upload_r = st.file_uploader("Upload completed ratings",
                                             type=["csv","xlsx"], key="nb_upload",
                                             label_visibility="collapsed")

            if upload_r:
                df_r = _pd9.read_csv(upload_r) if upload_r.name.endswith(".csv") else _pd9.read_excel(upload_r)
                ic  = next((c for c in df_r.columns if c.lower() in ["employee","employeeid","name","id"]), df_r.columns[0])
                pc  = next((c for c in df_r.columns if "perf" in c.lower()), None)
                ptc = next((c for c in df_r.columns if "pot" in c.lower()), None)
                if pc and ptc:
                    loaded = 0
                    for _, row in df_r.iterrows():
                        key = str(row[ic]).strip()
                        try:
                            p  = max(1, min(3, int(float(row[pc]))))
                            pt = max(1, min(3, int(float(row[ptc]))))
                            ratings[key] = (p, pt)
                            loaded += 1
                        except: pass
                    st.session_state["ninebox_ratings"] = ratings
                    st.success(f"✓ Loaded ratings for **{loaded}** employees.")
                else:
                    st.error("File needs: Employee/Name column, Performance (1-3), Potential (1-3)")

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

            # Build editable table — only pre-fill employees already in ratings
            # New employees start blank (not auto-(2,2))
            table_rows = []
            for i, r in matched_all:
                emp = get_name(i)
                if emp in ratings:
                    p, pt = ratings[emp]
                else:
                    p, pt = None, None
                table_rows.append({
                    "Employee":    emp,
                    "Role":        r.standard_title,
                    "Performance": p,
                    "Potential":   pt,
                })
            df_edit = _pd9.DataFrame(table_rows)

            st.caption(f"{len(ratings)} of {len(matched_all)} employees rated — edit the table below then tap **Save ratings**")

            edited = st.data_editor(
                df_edit,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config={
                    "Employee": st.column_config.TextColumn("Employee", disabled=True, width="medium"),
                    "Role":     st.column_config.TextColumn("Role",     disabled=True, width="medium"),
                    "Performance": st.column_config.NumberColumn(
                        "Performance (1–3)",
                        help="1 = Low, 2 = Effective, 3 = Top performer",
                        min_value=1, max_value=3, step=1, width="small"),
                    "Potential": st.column_config.NumberColumn(
                        "Potential (1–3)",
                        help="1 = Limited, 2 = Growth, 3 = High potential",
                        min_value=1, max_value=3, step=1, width="small"),
                },
                key="nb_editor",
            )

            if st.button("Save ratings", type="primary"):
                saved = 0
                for _, row in edited.iterrows():
                    emp = str(row["Employee"]).strip()
                    p_v = row["Performance"]
                    pt_v= row["Potential"]
                    if p_v is not None and pt_v is not None:
                        try:
                            ratings[emp] = (max(1,min(3,int(p_v))), max(1,min(3,int(pt_v))))
                            saved += 1
                        except: pass
                st.session_state["ninebox_ratings"] = ratings
                st.success(f"✓ Saved ratings for **{saved}** employees. Switch to View Grid.")
                st.rerun()

    # ── Tab 2: Grid ──────────────────────────────────────────────────────
    with tab_grid:
        if not ratings:
            st.info("Rate some employees in the Rate tab first.")
        else:
            # Build grid HTML
            grid_w, grid_h = 3, 3
            cells = {(p,pt):[] for p in range(1,4) for pt in range(1,4)}
            for emp, (p,pt) in ratings.items():
                cells[(p,pt)].append(emp)

            total_rated = len(ratings)
            stars = len(cells.get((3,3),[]))
            rough = len(cells.get((1,3),[]))
            under = len(cells.get((1,1),[]))
            st.markdown(
                f'<div style="display:flex;gap:10px;margin-bottom:16px">'
                f'{_stat_card(total_rated,"Rated")}'
                f'{_stat_card(stars,"Stars",C["teal"])}'
                f'{_stat_card(rough,"Rough diamonds",C["amber"])}'
                f'{_stat_card(under,"Underperformers",C["clay"])}'
                f'</div>', unsafe_allow_html=True)

            # Render 3x3 grid
            html = (
                f'<div style="overflow-x:auto">'
                f'<div style="display:grid;grid-template-columns:28px repeat(3,1fr);'
                f'grid-template-rows:repeat(3,1fr) 28px;gap:4px;min-width:300px">'
            )
            # Y-axis labels (potential, top to bottom: 3→1)
            pot_labels_ord = [3,2,1]
            for pt in pot_labels_ord:
                html += (f'<div style="display:flex;align-items:center;justify-content:center;'
                    f'font-family:{FONT_MONO};font-size:9px;color:{C["muted"]};'
                    f'writing-mode:vertical-lr;transform:rotate(180deg)">'
                    f'{POT_LABELS[pt][:8]}</div>')
                for p in [1,2,3]:
                    emps = cells.get((p,pt),[])
                    bc   = BOX_COLORS.get((p,pt),"#EDF0F3")
                    bl   = box_label(p,pt)
                    emp_chips = "".join(
                        f'<div style="font-family:{FONT_SANS};font-size:10px;color:#fff;'
                        f'background:rgba(0,0,0,0.2);border-radius:4px;padding:2px 5px;'
                        f'margin:1px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
                        f'max-width:100%">{e}</div>'
                        for e in emps[:6]
                    )
                    more = f'<div style="font-family:{FONT_MONO};font-size:9px;color:rgba(255,255,255,0.7)">+{len(emps)-6} more</div>' if len(emps)>6 else ""
                    html += (
                        f'<div style="background:{bc};border-radius:8px;padding:8px 10px;min-height:80px;">'
                        f'<div style="font-family:{FONT_MONO};font-size:9px;font-weight:600;'
                        f'color:rgba(255,255,255,0.8);letter-spacing:.08em;margin-bottom:4px">'
                        f'{bl}</div>'
                        f'{emp_chips}{more}'
                        f'</div>'
                    )
            # X-axis labels
            html += '<div></div>'
            for lbl in ["Low","Effective","Top"]:
                html += (f'<div style="text-align:center;font-family:{FONT_MONO};font-size:9px;'
                    f'color:{C["muted"]};padding-top:4px">{lbl} performer</div>')
            html += '</div></div>'

            # Axis titles
            st.markdown(
                f'<div style="display:flex;justify-content:center;font-family:{FONT_MONO};'
                f'font-size:10px;color:{C["muted"]};letter-spacing:.1em;margin-bottom:4px">'
                f'PERFORMANCE →</div>',
                unsafe_allow_html=True,
            )
            st.markdown(html, unsafe_allow_html=True)

    # ── Tab 3: Export ────────────────────────────────────────────────────
    with tab_export:
        if not ratings:
            st.info("Rate some employees first.")
        else:
            rows_ex = []
            for emp,(p,pt) in ratings.items():
                rows_ex.append({"Employee":emp,"Performance":p,"Potential":pt,
                    "Performance Label":PERF_LABELS[p],"Potential Label":POT_LABELS[pt],
                    "Box":box_label(p,pt)})
            df_ex = _pd9.DataFrame(rows_ex).sort_values(["Performance","Potential"],ascending=[False,False])
            st.dataframe(df_ex, use_container_width=True, hide_index=True)
            buf_ex = _io9.BytesIO(); df_ex.to_excel(buf_ex,index=False)
            st.download_button("⬇ Download 9-box report", buf_ex.getvalue(),
                file_name="jobsy_9box_grid.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")



if __name__ == "__main__":
    main()

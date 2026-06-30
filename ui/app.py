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
    )
except ImportError:
    def _ps_available(): return False
    def _ps_generate(): return ""
    def _ps_save(*a,**k): return False
    def _ps_load(*a,**k): return None

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

    # salary bar with P25/P50/P75
    if r.salary_range:
        lo, hi = r.salary_range
        cat = _get_active_catalog()
        band = cat.repository.salary.get((r.function, r.level)) if cat else None
        MKTLO, MKTHI = 24000, 280000
        def _p(v): return min(100, max(0, (v-MKTLO)/(MKTHI-MKTLO)*100))
        if band and getattr(band,'p25',0) and getattr(band,'p75',0):
            grade_chip = (f'<span style="font-family:{FONT_MONO};font-size:10px;background:{C["blue"]}1A;'
                f'color:{C["blue"]};border-radius:6px;padding:2px 8px;margin-left:8px">G{band.grade}</span>'
                ) if band.grade else ""
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


def main():
    st.set_page_config(page_title="Jobsy", page_icon="📊",
                       layout="centered", initial_sidebar_state="expanded")
    load_fonts()

    # page navigation
    page = st.sidebar.radio("", ["Matching", "Connect", "Skills Assessment", "Skill Gap", "9-Box Grid", "Architecture Report", "Organisation", "Organigram"], label_visibility="collapsed")

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
        st.subheader("Matching")
        threshold    = st.slider("Review below confidence", 50, 100, int(DEFAULT_THRESHOLD))
        enable_fuzzy = st.checkbox("Fuzzy stage (RapidFuzz)", value=True)
        st.divider()

    # ── Session persistence ───────────────────────────────────────────
    with st.sidebar:
        st.divider()
        if _ps_available():
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
            st.caption("💾 Session saving disabled — add SUPABASE_URL and SUPABASE_KEY to Streamlit secrets to enable.")

    # load catalog
    path = WORKBOOK_PATH
    catalog = None
    try:
        catalog = load_workbook_catalog(path)
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
    service = MatchingService(catalog, review_threshold=threshold, enable_fuzzy=enable_fuzzy)

    if page == "Connect":
        connect_page()
        return

    if page == "Skills Assessment":
        skill_assessment_page(catalog)
        return

    if page == "Skill Gap":
        skill_gap_page(catalog, service)
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
        upload = st.file_uploader("Upload CSV or Excel (.csv, .xls, .xlsx)",
                                   type=["csv","xls","xlsx"])
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
                auto_title = next((c for c in col_opts if c.lower() in
                    ["jobtitle","job_title","title","functie","functietitel","function","position"]), col_opts[0])
                col = st.selectbox("Column with job titles", col_opts,
                                   index=col_opts.index(auto_title))
                name_opts = ["— none —"] + col_opts
                auto_name = next((c for c in col_opts if c.lower() in
                    ["name","fullname","naam","firstname","first_name"]), "— none —")
                name_col = st.selectbox("Name column (optional)", name_opts,
                                        index=name_opts.index(auto_name) if auto_name in name_opts else 0)
                st.caption(f"{len(df_in)} rows · {len(col_opts)} columns detected")
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
    tmpl_buf = _iosa.BytesIO(); tmpl_df.to_excel(tmpl_buf, index=False)
    st.download_button("⬇ Download assessment template (.xlsx)", tmpl_buf.getvalue(),
        file_name="jobsy_skills_assessment_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Upload ───────────────────────────────────────────────────────────
    upload_sa = st.file_uploader("Upload completed assessment (.csv or .xlsx)",
                                  type=["csv","xlsx"], key="sa_upload")
    if not upload_sa:
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

    df_sa = (_pdsa.read_csv(upload_sa) if upload_sa.name.endswith(".csv")
             else _pdsa.read_excel(upload_sa))

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

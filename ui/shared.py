"""
ui/shared.py — the chrome every Jobsy page draws on.

The imports, the colour and font tokens, and the handful of helpers used by
more than one page. Split out of ui/app.py on 2026-09-03: the module had grown
to 5,400 lines holding all thirteen pages, which made every change to one page
a change to the file all the others live in.

Pages do `from ui.shared import *`, which is why __all__ at the bottom is
explicit about the underscore-prefixed helpers — a star import would skip them,
and the pages call them by the names they have always used.
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

import services.salary_service as _salary

try:
    from services.architecture_report_service import ArchitectureReportService
except ImportError:
    ArchitectureReportService = None

# One try per connector: importing them together meant a missing module took
# down the connector that was fine, and the page reported both as absent.
try:
    from services.afas_connector import AfasConnector
    _AFAS_AVAILABLE = True
except ImportError:
    _AFAS_AVAILABLE = False

try:
    from services.workday_connector import WorkdayConnector
    _WORKDAY_AVAILABLE = True
except ImportError:
    _WORKDAY_AVAILABLE = False

_CONNECTORS_AVAILABLE = _AFAS_AVAILABLE or _WORKDAY_AVAILABLE

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
from services.assessment_service import service_for_assessments
from services.benefits_service import BenefitsService
from services.export_service import ExportService
from services.matching_service import MatchingService

# ── colours (centralised in ui/theme.py and mirrored in .streamlit/config.toml) ──
C = THEME_COLORS


def _brand_name() -> str:
    """The product's name for whoever is signed in. F-2: never hard-code it in
    something a user reads."""
    try:
        from services import branding_service
        return branding_service.name()
    except Exception:
        return "Jobsy"
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
FONT_SERIF = THEME_FONT["display"]
FONT_SANS  = THEME_FONT["sans"]
FONT_MONO  = THEME_FONT["mono"]


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
        # This card is near-white, so every colour on it comes from the
        # on-light ramp. The dark-theme tokens are unreadable here: C["ink"]
        # is #EDE6FF, which on #F8FAFB is white on white.
        f'<div style="margin-top:8px;padding:10px 12px;background:#F8FAFB;'
        f'border:1px solid {C["on_light_line"]};border-radius:8px">'
        f'<div style="font-family:{FONT_MONO};font-size:9.5px;letter-spacing:.1em;'
        f'text-transform:uppercase;color:{C["on_light_accent"]};margin-bottom:5px">Development pathway</div>'
        f'<div style="font-family:{FONT_SANS};font-size:12.5px;font-weight:600;color:{C["on_light_ink"]};margin-bottom:3px">{action}</div>'
        f'<div style="font-family:{FONT_SANS};font-size:12px;color:{C["on_light_body"]};line-height:1.45;margin-bottom:5px">{method}</div>'
        f'<div style="display:flex;align-items:center;gap:6px">'
        f'<span style="font-family:{FONT_MONO};font-size:10px;background:{C["on_light_tint"]};'
        f'color:{C["on_light_accent"]};border-radius:6px;padding:2px 8px">⏱ {duration}</span>'
        f'<span style="font-family:{FONT_MONO};font-size:10px;color:{C["on_light_muted"]}">Gap +{gap["gap"]} level{"s" if gap["gap"]!=1 else ""}</span>'
        f'</div></div>'
    )


def load_fonts():
    """Second copy of theme.load_fonts(), kept in step with it deliberately.

    Both exist and both run; if they disagree the page fetches two display faces
    and renders whichever loses the race, which is how Fraunces could linger
    after the theme moved on. Change them together.
    """
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@500;600;700&'
        'family=Sacramento&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">',
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
def load_workbook_catalog(path, sig=None, org_id=None):
    """The reference library, cached for the life of the process.

    `sig` only participates in the cache key: when the workbook file changes,
    sig changes and Streamlit rebuilds the catalog instead of serving a stale one.

    `org_id` is in the key for a harder reason. st.cache_resource is shared by
    every browser session in this process, so without it two clients would share
    one catalog — the failure auth_service warns about, arriving through the
    cache instead of through a global. It is safe to share a catalog WITHIN an
    org only because all 22 reference tables read through
    `app.can_read_org(org_id)`, which depends on membership and not on the
    member's role. If that ever becomes role-dependent, this key has to grow;
    supabase/tests/0014_library_read_is_org_only.sql is what would notice.
    """
    from core.catalog import Catalog
    client = None
    try:
        from core.config import LIBRARY_CLIENT
        if LIBRARY_CLIENT == "user":
            from services import auth_service
            client = auth_service.db()
    except Exception:
        client = None
    c = Catalog(path, client=client, org_id=org_id); c.load(); return c


@st.cache_resource(show_spinner="Building sample catalog…")
def load_sample_catalog():
    return _SampleCatalog()


# ── money ──────────────────────────────────────────────────────────────────
#
# This was `_euro()`, and it was right for the Netherlands and silently wrong
# for Poland, Sweden and Denmark -- all seeded in `countries` precisely so that
# nothing may assume euro. A salary rendered "€90.000" when it is 90,000 zloty
# is not a formatting bug; it is a number that means something else, on a screen
# somebody sets pay from. See services/country_service.py and migration 0012.

def _money(n, decimals=0):
    """Format an amount in the ACTIVE CLIENT'S currency."""
    try:
        from services import country_service
        return country_service.money(n, decimals=decimals)
    except Exception:
        # No session to ask: euro is the deployment default. This fallback and
        # _cur()'s are the only places in the UI where a euro sign is correct.
        try:
            return "\u20ac{:,.{}f}".format(float(n), decimals).replace(",", ".")
        except (TypeError, ValueError):
            return "\u2014"


def _cur():
    """The active market's currency symbol, for labels and axis titles."""
    try:
        from services import country_service
        return country_service.symbol_for()
    except Exception:
        return "\u20ac"


def _country():
    """The active client's market code, for services that must be told one.

    Returns "" rather than guessing when there is no session, so the service
    applies its own default instead of being handed a country nobody chose.
    """
    try:
        from services import country_service
        return country_service.active_country()
    except Exception:
        return ""


# Kept as an alias: call sites across ui/views read _euro(...) and renaming them
# all would bury the actual change in noise. It no longer means euro.
_euro = _money


def _logged_download(*args, audit: bool = True, **kwargs):
    """st.download_button, plus a record that client data left the building.

    Every export is somebody's roster leaving in a file nobody can recall. 0009
    gave us activity_log; this is the UI half. `audit=False` marks the blank
    templates -- recording those would bury the real exports in noise.
    """
    clicked = st.download_button(*args, **kwargs)
    if clicked and audit:
        try:
            from services import auth_service
            name = kwargs.get("file_name")
            if name is None and len(args) > 2:
                name = args[2]
            auth_service.log("export.download", subject=str(name or "unnamed"),
                             detail={"label": str(args[0]) if args else ""})
        except Exception as exc:
            # An export that happened must not fail because the note about it
            # did. The trail is evidence, not a gate.
            print(f"[audit] export not recorded: {exc}")
    return clicked



def _template_download(*args, **kwargs):
    """A blank template leaving is not client data leaving.

    Separate name rather than `audit=False` at the call site, because the label
    is the first positional argument and a keyword cannot precede it.
    """
    return _logged_download(*args, audit=False, **kwargs)


# ── inline-style helpers ───────────────────────────────────────────────────


def _chip(text, bg, fg, size="11px"):
    return (f'<span style="display:inline-block;font-family:{FONT_MONO};font-size:{size};'
            f'font-weight:500;background:{bg};color:{fg};border-radius:7px;'
            f'padding:3px 9px;margin:2px 3px 2px 0">{text}</span>')


_active_catalog = None


def _set_active_catalog(cat): global _active_catalog; _active_catalog = cat


def _get_active_catalog(): return _active_catalog


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


def render_workspace_anchor() -> None:
    """Anchor used by hero quick actions."""
    st.markdown('<div id="workspace"></div>', unsafe_allow_html=True)


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


#: The concepts a country pack's VOCABULARY is keyed by. Each call site already
#: spells its concept in English inside `exacts` ({"gender", "geslacht", ...}),
#: so the concept can be inferred from the call rather than threaded through
#: twenty signatures in files this change does not own.
_PACK_CONCEPTS = ("salary", "gender", "function", "level", "fte", "tenure",
                  "country", "variable", "holiday", "employee", "non_pay")


def _pack_vocabulary(concept):
    """The active market's column words for one concept, or ()."""
    if not concept:
        return ()
    try:
        try:
            from services import country_packs
        except ImportError:
            from jobsy.services import country_packs
        pack = country_packs.for_country(None)
    except Exception:
        return ()
    if pack is None or not pack.vocabulary:
        return ()
    return tuple(str(t).strip().lower() for t in pack.vocabulary.get(concept, ()) if t)


#: Working time stored as a FRACTION across two integer columns, per market.
#:
#: Poland's dominant payroll systems export no FTE number at all. They export
#: `Licznik_wymiaru_etatu` (numerator) and `Mianownik_wymiaru_etatu`
#: (denominator): a half-timer is 1 and 2, a three-quarter timer 3 and 4. A
#: detector that grabs one of them reads a half-timer's FTE as **1**, raises
#: nothing, and leaves their raw part-time pay standing beside everybody else's
#: full-time figure -- which inflates the gap, and lands that inflation on
#: part-time staff, who skew female. It is the FTE-blank failure this codebase
#: already documents, except silent, because the cell is not blank.
#:
#: Computing the ratio needs a two-column consumer this change does not own, so
#: what is implemented here is the refusal: when the pair is present, neither
#: half is offered as "the FTE column", and the caller falls through to its
#: no-FTE path, which says so on screen. `_detect_fte_pair` is the seam for the
#: real fix. This table belongs in the country pack (pl.py holds both names in
#: VOCABULARY["fte"] but does not mark them as a pair); the pack is another
#: decision path's to change.
_FTE_RATIO_PAIRS = (
    ("licznik", "mianownik"),   # PL
)


def _detect_fte_pair(cols):
    """The (numerator, denominator) columns of a fractional FTE, or None."""
    low = [(c, str(c).strip().lower()) for c in cols]
    for num_kw, den_kw in _FTE_RATIO_PAIRS:
        n = next((c for c, l in low if num_kw in l), None)
        d = next((c for c, l in low if den_kw in l), None)
        if n is not None and d is not None:
            return (n, d)
    return None


def _smart_detect(cols, exacts, contains, concept=None):
    """Pick a column by case-insensitive exact match first, then substring.

    The word lists the callers pass are English + Dutch, which is what a header
    detector written in the Netherlands looks like: a Polish "Wynagrodzenie" or
    a Spanish "Jornada" column is simply not found, and the page then reports
    "no salary column" against a file that has one. So the ACTIVE MARKET's pack
    vocabulary is consulted too.

    It is consulted *in addition to* the caller's lists, not instead of them.
    Deleting the inline lists in the same change would swap one untested
    detector for another; the pack path has to be proved first, and until it is,
    an English or Dutch header must keep resolving exactly as it does today.
    Exact matches are order-independent (the loop walks columns, not keywords),
    and the pack's substrings are appended after the caller's, so nothing that
    resolves today can start resolving elsewhere.

    Robust to non-string / numeric headers (uses str(c)). Returns None if
    nothing matches so callers can supply their own fallback.
    """
    if concept is None:
        for _c in _PACK_CONCEPTS:
            if _c in exacts:
                concept = _c
                break
    vocab = _pack_vocabulary(concept)

    if concept == "fte":
        # A fraction split over two integer columns is not an FTE column. See
        # _FTE_RATIO_PAIRS: returning either half reads a half-timer as
        # full-time, silently, in the direction that overstates the gap.
        _pair = _detect_fte_pair(cols)
        if _pair:
            cols = [c for c in cols if c not in _pair]

    low = [(c, str(c).strip().lower()) for c in cols]
    for c, l in low:
        if l in exacts or l in vocab:
            return c
    for kw in tuple(contains) + vocab:
        for c, l in low:
            if kw in l:
                return c
    return None


# Everything above is what a page may import, private helpers included.
__all__ = [n for n in dir() if not n.startswith("__")]

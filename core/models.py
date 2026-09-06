"""
jobsy/core/models.py

Canonical typed records for the reference library. These are the single source
of truth for shape, so the rest of the codebase stops disagreeing about whether
a job has `.title` or `.standard_title`:

    Job.standard_title  is the canonical field (matches the workbook column and
                        Catalog.search_jobs); `.title` stays as a read-only alias
                        so older call sites keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = ["Job", "JobProfile", "JobPositioning", "SalaryBand", "CareerStep", "Employee",
           "Skill", "RoleSkillRequirement", "CompetencyLevel", "SkillAssessment",
           "BenefitCatalogItem", "BenefitObservation", "LevelBenefitFactor", "BenefitBand",
           "PayMixEntry", "PayElement", "SeniorityLevel", "SeniorityGradeBinding"]


@dataclass(frozen=True)
class Job:
    job_id: str
    standard_title: str
    function: str
    level: str
    grade: int = 0
    category: str = ""
    # The public occupational taxonomies. ISCO is the ILO's, ESCO the EU's; the
    # library fills both for all 81 roles. The CODE was already consulted by the
    # Data Quality scorecard while the LABELS were loaded and read by nothing —
    # and the labels are the half a person can check.
    isco_group: str = ""
    isco_title: str = ""
    esco_label: str = ""

    @property
    def title(self) -> str:
        """Backward-compatible alias for `standard_title`."""
        return self.standard_title


@dataclass(frozen=True)
class JobProfile:
    """What a role DOES. Universal — see migration 0016 §1.

    `management_level` is the one field here that is NOT universal, and it no
    longer comes from job_profiles: since 0016 it is read out of
    job_profile_positioning for the market being looked at, resolved through
    repository._MarketRows like every other national fact. It is kept ON this
    record because a JobProfile is what the UI and the Art. 4 tooling are handed,
    and moving the attribute would have meant editing call sites in ui/ to fix a
    data question — but it is a SNAPSHOT taken when the Repository was built, and
    a snapshot cannot follow a market change.

    So: read it here when you already hold a profile and the market cannot have
    moved under you. Read `repository.job_positioning` — a JobPositioning per
    job_id, country then EU then nothing — when correctness across markets is the
    point. The two agree by construction; only their staleness differs.
    """
    job_id: str
    description: str = ""
    key_responsibilities: tuple[str, ...] = ()
    required_skills: tuple[str, ...] = ()
    specialisms: tuple[str, ...] = ()
    management_level: str = ""
    typical_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class JobPositioning:
    """Where a role SITS, in ONE market. The country-carrying half of a profile.

    Split out of job_profiles by migration 0016 §1, whose reasoning is worth
    repeating where it is read: "management level: Lead" is a claim against a
    national grading instrument — the functiegroep set per CAO in the
    Netherlands, ERA in Germany, the conventions collectives in France — and the
    same words assert a different rung across the border. What the role does
    stays on JobProfile as one row for everybody; only this travels per market.

    `country` is on the record, not merely the key it was filed under, so a
    positioning claim that gets passed around can still say which ladder it is
    about. A value that cannot name its market is the shape that let Dutch
    numbers end up under a Belgian client's name.
    """
    job_id: str
    management_level: str = ""
    country: str = "NL"


@dataclass(frozen=True)
class SalaryBand:
    function: str
    level: str
    min: float
    max: float
    currency: str = "EUR"
    grade: int = 0
    p25: float = 0.0
    p50: float = 0.0
    p75: float = 0.0

    @property
    def range(self) -> tuple[float, float]:
        return (self.min, self.max)

    # aliases so callers can use either naming
    @property
    def min_salary(self) -> float:
        return self.min

    @property
    def max_salary(self) -> float:
        return self.max


@dataclass(frozen=True)
class CareerStep:
    job_id: str
    next_job_id: Optional[str] = None
    next_title: Optional[str] = None


@dataclass(frozen=True)
class Employee:
    employee_id: str
    name: str
    current_title: str

@dataclass(frozen=True)
class Skill:
    skill_id: str
    skill_name: str
    category: str
    definition: str = ""


@dataclass(frozen=True)
class RoleSkillRequirement:
    job_id: str
    skill_id: str
    required_level: int          # 1–5
    skill_type: str              # Core | Adjacent | Leadership


@dataclass(frozen=True)
class CompetencyLevel:
    level: int
    name: str
    description: str = ""


@dataclass(frozen=True)
class SkillAssessment:
    """A person's actual level on a skill — the piece the reference library never
    held. Joined to RoleSkillRequirement it turns "declared strengths" into a real
    coverage-and-gap. `source`/`confidence` keep it honest (a self-rating is not a
    validated one) and feed the HRS "Trust in the Reading" register."""
    employee_id: str
    skill_id: str
    current_level: int             # 1–5, on the CompetencyLevel scale
    source: str = "self"           # self | manager | validated
    confidence: float = 0.5        # 0–1
    assessed_at: str = ""          # ISO date, optional
    evidence_ref: str = ""         # certification / project / assessment id, optional


@dataclass(frozen=True)
class JobGrade:
    """One rung of the grade ladder, with the factor language that defines it.

    The point range (hay_min/hay_max) is Jobsy's OWN scale — 100 to 1800 across
    the fourteen grades. It is not an ISF score and must never be looked up in
    ISF's published boundary table, which runs 0 to 940 and belongs to a
    protected method. See services/cao_crosswalk_service.
    """
    grade: int
    label: str
    level_band: str
    pay_min: float = 0
    pay_p25: float = 0
    pay_p50: float = 0
    pay_p75: float = 0
    pay_max: float = 0
    responsibilities: str = ""
    authority: str = ""
    career_band: str = ""
    hay_min: float = 0
    hay_max: float = 0
    # The factor descriptors. Four of these were already on screen, read out of
    # a raw frame; autonomy and span_of_control were in the library and read by
    # nothing at all. They are Art. 4 material — effort, responsibility,
    # autonomy — so they belong on the typed record rather than in a DataFrame
    # a page happens to hold.
    scope: str = ""
    complexity: str = ""
    autonomy: str = ""
    impact: str = ""
    leadership: str = ""
    span_of_control: str = ""
    decision_rights: str = ""

    @property
    def hay_mid(self) -> float:
        """The middle of this grade's own point range, or 0 if it has none."""
        if not self.hay_min and not self.hay_max:
            return 0
        return (float(self.hay_min) + float(self.hay_max)) / 2


@dataclass(frozen=True)
class Industry:
    industry_id: str
    name: str
    scope: str = ""
    characteristics: str = ""


@dataclass(frozen=True)
class IndustrySalaryFactor:
    industry_id: str
    function: str
    factor: float = 1.0


#: The nine NL seed rows that cite Dutch law or a Dutch collective agreement.
#: Named by id and not matched on text: a skill_name is prose, and a LIKE over
#: prose is how the wrong row moves. Same list as migration 0019.
_NL_REGULATORY_SKILL_IDS = frozenset({
    "SK-IND-01", "SK-IND-02", "SK-IND-03", "SK-IND-04", "SK-IND-07",
    "SK-IND-08", "SK-IND-09", "SK-IND-10", "SK-IND-14",
})


def is_regulatory_skill_id(skill_id: str) -> bool:
    """Does this industry skill belong to a country rather than to practice?

    0019 split industry_skills in two. The database was split by this exact
    rule; a workbook already in a client's hands still carries both halves on
    one IndustrySkills sheet, and both the import and the Excel reader have to
    make the same cut. One function, so they cannot drift: two copies of a
    classification rule is how the halves quietly diverge.

    Country packs are SK-IND-XX-nn and national by construction. The nine NL
    rows are named because their ids carry no marker.
    """
    sid = (skill_id or "").strip().upper()
    if sid in _NL_REGULATORY_SKILL_IDS:
        return True
    parts = sid.split("-")
    return (len(parts) == 4 and parts[0] == "SK" and parts[1] == "IND"
            and len(parts[2]) == 2 and parts[2].isalpha())


@dataclass(frozen=True)
class IndustrySkill:
    industry_id: str
    skill_id: str
    skill_name: str
    category: str = ""
    definition: str = ""
    default_level: int = 3
    #: Empty for the universal rows in industry_skills; set for the national
    #: ones in industry_regulatory_skills. A regulatory skill IS its country --
    #: Wwft is Dutch, GwG is German, PC 111/209 is Belgian -- so this is not
    #: decoration: a row carrying a country must never render under another
    #: market's flag, which is the failure 0012 named.
    country: str = ""


@dataclass(frozen=True)
class SeniorityLevel:
    """One rung of the product's own ladder. L1..L5 and their names are
    UNIVERSAL — 0016 §2 — and belong to no country.

    `maps_to_level`, `grade_range` and `grades` are not. They point into
    job_grades, which is keyed (org_id, country, grade), so "L3 covers grades
    7-10" is a claim about ONE national ladder. Since 0016 those three are read
    from seniority_grade_binding for the market being looked at, the same way
    JobProfile.management_level is, and with the same caveat: they are a
    snapshot of the market at build time. `repository.seniority_bindings` is the
    live read.
    """
    l_code: str          # L1..L5
    l_name: str          # Starter, Developing, Senior, Manager, Rising Star
    maps_to_level: str   # Junior/Medior/Senior/Lead or "(designation)"
    grade_range: str = ""
    definition: str = ""
    grades: str = ""


@dataclass(frozen=True)
class SeniorityGradeBinding:
    """What an L-code binds to, in ONE market — 0016 §2.

    Held without a country, "L3 = grades 7-10" cannot say whose grades: the
    Dutch ladder has fourteen rungs and there is no reason a Belgian one would.
    `grades` ("Grade 7-10") travels with `grade_range` because it is the same
    fact spelled out for a reader, and letting them separate would give the
    screen and the export two answers.
    """
    l_code: str
    grade_range: str = ""
    maps_to_level: str = ""
    grades: str = ""
    country: str = "NL"


@dataclass(frozen=True)
class BenefitCatalogItem:
    benefit_id: str
    category: str
    basis: str = ""
    unit: str = ""
    typical_value_description: str = ""
    statutory_nl: str = ""
    taxable: str = ""
    description: str = ""


@dataclass(frozen=True)
class BenefitObservation:
    industry_id: str
    category: str
    value: float
    unit: str = ""
    currency: str = ""
    # Where this observation was collected. A benefit value is a market price
    # like a salary is, so pooling one country's with another's is the same
    # mistake as pooling their pay -- see services/pay_equity_service.py, where
    # exactly that produced a 27% gap out of nothing. Defaults to the Dutch
    # library, which is what every existing row is; 0012 backfills the column
    # the same way and for the same reason.
    country: str = "NL"


@dataclass(frozen=True)
class LevelBenefitFactor:
    level: str
    category: str
    factor: float = 1.0


@dataclass(frozen=True)
class BenefitBand:
    """Computed (not stored) — percentiles derived from BenefitObservations at runtime."""
    category: str
    industry_id: str
    level: str
    unit: str
    p25: float
    p50: float
    p75: float
    p90: float
    n_observations: int
    # Which market these percentiles describe, and the money they are in. A
    # band that cannot say either is a band nobody can check.
    country: str = ""
    currency: str = ""

    @property
    def median(self) -> float:
        """Alias for P50 — the market median."""
        return self.p50


@dataclass(frozen=True)
class PayMixEntry:
    """Pay policy for one Function x Level: what that cohort is entitled to.

    Target, not actual. It says what the policy grants, never what anyone was
    paid — the distinction the variable-pay exposure analysis rests on.

    The frame keeps LTIEligible as the workbook's 'Yes'/'No' text, because the
    database-versus-workbook parity gate compares frames; the typing happens
    here, where it costs nothing.
    """
    function: str
    level: str
    target_variable_pct: float = 0.0
    thirteenth_month_pct: float = 0.0
    lti_eligible_text: str = ""
    notes: str = ""

    @property
    def lti_eligible(self) -> bool:
        return str(self.lti_eligible_text).strip().lower() in ("yes", "y", "true", "ja", "1")


@dataclass(frozen=True)
class PayElement:
    """One component of total remuneration, as the library defines it.

    TypicalValue is deliberately free text: some elements have a rate ('8%'),
    and some have a range or nothing at all ('0-40% by role', '~10-15%
    (indicative)', 'varies'). Parsing lives in services/pay_components_service,
    which refuses to turn a range into a point.
    """
    element_id: str
    name: str
    category: str = ""
    basis: str = ""
    typical_value: str = ""
    statutory_nl: str = ""
    taxable: str = ""
    description: str = ""

    @property
    def is_statutory(self) -> bool:
        """The StatutoryNL column reads 'Yes (statutory min 8%)', 'No (CAO...)',
        'Partly (sector funds)'. Only a leading Yes is a statutory obligation;
        'Partly' is not, and must not be reported as one."""
        return str(self.statutory_nl).strip().lower().startswith("yes")

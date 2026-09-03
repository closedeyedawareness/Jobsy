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

__all__ = ["Job", "JobProfile", "SalaryBand", "CareerStep", "Employee",
           "Skill", "RoleSkillRequirement", "CompetencyLevel", "SkillAssessment",
           "BenefitCatalogItem", "BenefitObservation", "LevelBenefitFactor", "BenefitBand",
           "PayMixEntry", "PayElement"]


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
    job_id: str
    description: str = ""
    key_responsibilities: tuple[str, ...] = ()
    required_skills: tuple[str, ...] = ()
    specialisms: tuple[str, ...] = ()
    management_level: str = ""
    typical_tools: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class IndustrySkill:
    industry_id: str
    skill_id: str
    skill_name: str
    category: str = ""
    definition: str = ""
    default_level: int = 3


@dataclass(frozen=True)
class SeniorityLevel:
    l_code: str          # L1..L5
    l_name: str          # Starter, Developing, Senior, Manager, Rising Star
    maps_to_level: str   # Junior/Medior/Senior/Lead or "(designation)"
    grade_range: str = ""
    definition: str = ""
    grades: str = ""


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

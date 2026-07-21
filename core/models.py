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
           "BenefitCatalogItem", "BenefitObservation", "LevelBenefitFactor", "BenefitBand"]


@dataclass(frozen=True)
class Job:
    job_id: str
    standard_title: str
    function: str
    level: str
    grade: int = 0
    category: str = ""

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

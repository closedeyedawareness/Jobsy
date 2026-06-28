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

__all__ = ["Job", "JobProfile", "SalaryBand", "CareerStep", "Employee"]


@dataclass(frozen=True)
class Job:
    job_id: str
    standard_title: str
    function: str
    level: str

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

    @property
    def range(self) -> tuple[float, float]:
        return (self.min, self.max)


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

"""
jobsy/core/repository.py

Owns the in-memory reference data. Turns the loader's raw DataFrames into typed
records (models.py), validates them (validator.py), builds the resolution index
(search_index.py), and exposes exactly what the Catalog facade needs:

    jobs               dict[job_id -> Job]
    profiles           dict[job_id -> JobProfile]
    salary             dict[(function, level) -> SalaryBand]
    title_mapping      dict[normalized existing title -> job_id]
    career_paths       dict[job_id -> CareerStep]
    levels             list[str]   (seniority ladder, in sheet order)
    employees          dict[employee_id -> Employee]
    jobs_by_function   dict[function -> list[Job]]
    jobs_by_level      dict[level -> list[Job]]
    index              SearchIndex
    find_job(title)    deterministic Job lookup
    statistics()       counts for health/dashboards

Column access is alias-tolerant: the workbook may use StandardTitle or
standard_title, JobID or job_id, etc., and the build still works.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

import logging
logger = logging.getLogger('jobsy')
from core.models import CareerStep, CompetencyLevel, Employee, Job, JobProfile, RoleSkillRequirement, SalaryBand, Skill
from core.search_index import SearchIndex
from core.utils import normalize_title
from core.validator import Validator

__all__ = ["Repository"]


def _val(row, *names: str) -> Optional[str]:
    """First present, non-empty attribute on a namedtuple row, as a stripped str."""
    for name in names:
        if hasattr(row, name):
            value = getattr(row, name)
            if value is not None and not (isinstance(value, float) and pd.isna(value)):
                text = str(value).strip()
                if text and text.lower() != "nan":
                    return text
    return None


def _num(row, *names: str) -> Optional[float]:
    for name in names:
        if hasattr(row, name):
            value = getattr(row, name)
            if value is None or (isinstance(value, float) and pd.isna(value)):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


class Repository:
    """Typed, validated, indexed view of the reference library."""

    def __init__(self, data: dict, *, validate: bool = True) -> None:
        if validate:
            Validator().validate(data, strict=True)

        self.jobs: dict[str, Job] = {}
        self.profiles: dict[str, JobProfile] = {}
        self.salary: dict[tuple[str, str], SalaryBand] = {}
        self.title_mapping: dict[str, str] = {}
        self.career_paths: dict[str, CareerStep] = {}
        self.levels: list[str] = []
        self.employees: dict[str, Employee] = {}
        self.jobs_by_function: dict[str, list[Job]] = {}
        self.jobs_by_level: dict[str, list[Job]] = {}
        self.skills: dict[str, Skill] = {}
        self.competency_levels: dict[int, CompetencyLevel] = {}
        self.role_skill_map: dict[str, list[RoleSkillRequirement]] = {}

        self._build_jobs(data.get("jobs"))
        self._build_profiles(data.get("profiles"))
        self._build_salary(data.get("salary"))
        self._build_titles(data.get("titles"))
        self._build_career(data.get("career"))
        self._build_levels(data.get("levels"))
        self._build_employees(data.get("employees"))

        def _get(d, *keys):
            for k in keys:
                v = d.get(k)
                if v is not None:
                    return v
            return None

        self._build_skills(data.get("skills"))
        self._build_competency_levels(_get(data, "competencylevels", "CompetencyLevels", "competency_levels"))
        self._build_role_skill_map(_get(data, "roleskillmap", "RoleSkillMap", "role_skill_map"))

        self.index = SearchIndex()
        self.index.build(data.get("jobs"), data.get("titles"))

        logger.info(
            "Repository built: %d jobs, %d profiles, %d salary bands, %d mappings",
            len(self.jobs), len(self.profiles), len(self.salary), len(self.title_mapping),
        )

    # --------------------------------------------------------------- builders
    def _build_jobs(self, df) -> None:
        if df is None:
            return
        for row in df.itertuples(index=False):
            job_id = _val(row, "JobID", "job_id")
            title = _val(row, "StandardTitle", "standard_title", "Title", "title")
            if not job_id or not title:
                continue
            function = _val(row, "Function", "function") or ""
            level = _val(row, "Level", "level") or ""
            job = Job(job_id=job_id, standard_title=title, function=function, level=level)
            self.jobs[job_id] = job
            self.jobs_by_function.setdefault(function, []).append(job)
            self.jobs_by_level.setdefault(level, []).append(job)

    def _build_profiles(self, df) -> None:
        if df is None:
            return
        def _split(row, *names):
            raw = _val(row, *names) or ""
            if not raw or str(raw).lower() in ("nan", "none", ""):
                return ()
            return tuple(s.strip() for s in str(raw).split(";") if s.strip())
        for row in df.itertuples(index=False):
            job_id = _val(row, "JobID", "job_id")
            if not job_id:
                continue
            desc  = _val(row, "Description", "description", "Summary", "summary") or ""
            mgmt  = _val(row, "ManagementLevel", "management_level") or ""
            if str(mgmt).lower() in ("nan", "none"):
                mgmt = ""
            self.profiles[job_id] = JobProfile(
                job_id=job_id,
                description=desc,
                key_responsibilities=_split(row, "KeyResponsibilities", "key_responsibilities"),
                required_skills=_split(row, "RequiredSkills", "required_skills"),
                specialisms=_split(row, "Specialisms", "specialisms"),
                management_level=mgmt,
                typical_tools=_split(row, "TypicalTools", "typical_tools"),
            )

    def _build_salary(self, df) -> None:
        if df is None:
            return
        for row in df.itertuples(index=False):
            function = _val(row, "Function", "function")
            level = _val(row, "Level", "level")
            if not function or not level:
                continue
            low = _num(row, "Min", "min", "MinSalary", "salary_min", "Low", "low")
            high = _num(row, "Max", "max", "MaxSalary", "salary_max", "High", "high")
            if low is None or high is None:
                continue
            currency = _val(row, "Currency", "currency") or "EUR"
            self.salary[(function, level)] = SalaryBand(
                function=function, level=level, min=low, max=high, currency=currency
            )

    def _build_titles(self, df) -> None:
        if df is None:
            return
        for row in df.itertuples(index=False):
            existing = _val(row, "ExistingTitle", "existing_title", "Title", "title")
            if not existing:
                continue
            job_id = _val(row, "JobID", "job_id")
            if not job_id:
                std = _val(row, "StandardTitle", "standard_title")
                if std:
                    job_id = self._job_id_for_title(std)
            if not job_id:
                continue
            self.title_mapping[normalize_title(existing)] = job_id

    def _build_career(self, df) -> None:
        if df is None:
            return
        for row in df.itertuples(index=False):
            job_id = _val(row, "JobID", "job_id", "FromJobID", "from_job_id")
            if not job_id:
                continue
            self.career_paths[job_id] = CareerStep(
                job_id=job_id,
                next_job_id=_val(row, "NextJobID", "next_job_id", "ToJobID", "to_job_id"),
                next_title=_val(row, "NextRole", "next_role", "NextTitle", "next_title"),
            )

    def _build_levels(self, df) -> None:
        if df is None:
            return
        for row in df.itertuples(index=False):
            level = _val(row, "Level", "level", "Name", "name")
            if level and level not in self.levels:
                self.levels.append(level)

    def _build_employees(self, df) -> None:
        if df is None:
            return
        for row in df.itertuples(index=False):
            emp_id = _val(row, "EmployeeID", "employee_id", "ID", "id")
            if not emp_id:
                continue
            self.employees[emp_id] = Employee(
                employee_id=emp_id,
                name=_val(row, "Name", "name") or "",
                current_title=_val(row, "CurrentTitle", "current_title", "Title", "title") or "",
            )

    def _job_id_for_title(self, title: str) -> Optional[str]:
        target = normalize_title(title)
        for job_id, job in self.jobs.items():
            if normalize_title(job.standard_title) == target:
                return job_id
        return None


    def _build_skills(self, df) -> None:
        if df is None:
            return
        for row in df.itertuples(index=False):
            sid = _val(row, "SkillID", "skill_id")
            if not sid:
                continue
            self.skills[sid] = Skill(
                skill_id=sid,
                skill_name=_val(row, "SkillName", "skill_name") or "",
                category=_val(row, "Category", "category") or "",
                definition=_val(row, "Definition", "definition") or "",
            )

    def _build_competency_levels(self, df) -> None:
        if df is None:
            return
        for row in df.itertuples(index=False):
            raw = _val(row, "Level", "level")
            if raw is None:
                continue
            try:
                level = int(float(raw))
            except (TypeError, ValueError):
                continue
            self.competency_levels[level] = CompetencyLevel(
                level=level,
                name=_val(row, "Name", "name") or "",
                description=_val(row, "Description", "description") or "",
            )

    def _build_role_skill_map(self, df) -> None:
        if df is None:
            return
        for row in df.itertuples(index=False):
            job_id  = _val(row, "JobID", "job_id")
            skill_id = _val(row, "SkillID", "skill_id")
            if not job_id or not skill_id:
                continue
            try:
                level = int(float(_val(row, "RequiredLevel", "required_level") or 0))
            except (TypeError, ValueError):
                level = 1
            req = RoleSkillRequirement(
                job_id=job_id,
                skill_id=skill_id,
                required_level=max(1, min(5, level)),
                skill_type=_val(row, "SkillType", "skill_type") or "Core",
            )
            self.role_skill_map.setdefault(job_id, []).append(req)

    # ------------------------------------------------------------------- API
    def find_job(self, title: str) -> Optional[Job]:
        """Deterministic lookup (exact -> normalized -> synonym). No fuzzy here."""
        if not title:
            return None
        job_id = (
            self.index.exact(title)
            or self.index.normalized(title)
            or self.index.synonym(title)
        )
        return self.jobs.get(job_id) if job_id else None

    def get_profile(self, job_id: str) -> Optional[JobProfile]:
        return self.profiles.get(job_id)

    def get_salary(self, function: str, level: str) -> Optional[SalaryBand]:
        return self.salary.get((function, level))

    def statistics(self) -> dict:
        return {
            "jobs": len(self.jobs),
            "profiles": len(self.profiles),
            "salary_bands": len(self.salary),
            "title_mappings": len(self.title_mapping),
            "career_paths": len(self.career_paths),
            "levels": len(self.levels),
            "employees": len(self.employees),
            "functions": len(self.jobs_by_function),
            "skills": len(self.skills),
            "role_skill_mappings": sum(len(v) for v in self.role_skill_map.values()),
        }

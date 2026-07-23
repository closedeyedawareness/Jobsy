"""
jobsy/services/assessment_service.py

Path B — the rigorous baseline for Skills Intelligence.

The v1 briefing approximated capability from ~3 self-declared skills per person.
This service runs on the real competency data model instead: it joins each
person's SkillAssessment (their actual level) to their role's
RoleSkillRequirements (the level the job needs) and produces coverage, gaps and
career opportunity as *measured* numbers, not proxies.

Honesty guarantees, by construction:
  * Coverage = current_level vs required_level. A gap is their difference. There
    is no fabricated percentage.
  * Every reading carries the assessment's `confidence`, so the downstream HRS
    "Room to Grow" / "Trust in the Reading" feed can weight it rather than trust
    a self-rating as if it were validated.
  * Title -> role resolution reuses the tested MatchingService / SearchIndex; it
    never invents a job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import logging
logger = logging.getLogger('jobsy')

from core.models import Employee, SkillAssessment

__all__ = ["SkillGap", "EmployeeCoverage", "CareerOpportunity", "AssessmentService",
           "DEFAULT_CONFIDENCE", "service_for_assessments"]


# A self-rating and a validated one are not the same fact. These are the weights
# the rest of the system reads as "how much of this picture is earned" -- they are
# the only reason `confidence` is a dial rather than a constant.
DEFAULT_CONFIDENCE = {"self": 0.5, "manager": 0.75, "validated": 0.95}


# ------------------------------------------------------------------ result types
@dataclass
class SkillGap:
    skill_id: str
    skill_name: str
    skill_type: str          # Core | Adjacent | Leadership
    required_level: int      # 1–5
    current_level: int       # 0 if the person has no assessment for this skill
    gap: int                 # max(0, required - current)
    confidence: float        # confidence of the current reading (0 if unassessed)


@dataclass
class EmployeeCoverage:
    employee_id: str
    job_id: Optional[str]
    job_title: Optional[str]
    gaps: list[SkillGap]

    @property
    def coverage(self) -> float:
        """Share of the role's required competency actually met (0–1),
        weighted by required level so a Core-5 gap counts more than an Adjacent-2."""
        req = sum(g.required_level for g in self.gaps)
        if not req:
            return 1.0
        have = sum(min(g.current_level, g.required_level) for g in self.gaps)
        return round(have / req, 3)

    @property
    def open_gaps(self) -> list[SkillGap]:
        return sorted((g for g in self.gaps if g.gap > 0),
                      key=lambda g: (-g.gap, 0 if g.skill_type == "Core" else 1))


@dataclass
class CareerOpportunity:
    from_job_id: str
    to_job_id: str
    to_title: Optional[str]
    ready: bool              # meets every Core requirement of the next role
    gaps: list[SkillGap]     # ALL of the next role's requirements (met and open)

    @property
    def open_gaps(self) -> list[SkillGap]:
        return sorted((g for g in self.gaps if g.gap > 0),
                      key=lambda g: (-g.gap, 0 if g.skill_type == "Core" else 1))

    @property
    def readiness(self) -> float:
        """Share of the next role's requirements already met (0–1) — over ALL
        requirements, so skills you already have count toward being ready."""
        req = sum(g.required_level for g in self.gaps)
        if not req:
            return 1.0
        have = sum(min(g.current_level, g.required_level) for g in self.gaps)
        return round(have / req, 3)


# ----------------------------------------------------------------------- service
class AssessmentService:
    """Coverage, gaps and career opportunity from SkillAssessment × RoleSkillRequirement."""

    def __init__(self, catalog, matcher=None) -> None:
        self._catalog = catalog
        self._repo = getattr(catalog, "repository", None)
        if self._repo is None:
            raise ValueError("AssessmentService needs a Catalog with a .repository")
        self._matcher = matcher  # optional MatchingService for title→job resolution

    # -------------------------------------------------------------- resolution
    def _job_id_for(self, title: Optional[str]) -> Optional[str]:
        repo, title = self._repo, (title or "").strip()
        if not title:
            return None
        fn = getattr(repo, "_job_id_for_title", None)
        if callable(fn):
            jid = fn(title)
            if jid:
                return jid
        if self._matcher is not None:
            try:
                res = self._matcher.match(title)
                if getattr(res, "matched", False):
                    return res.job_id
            except Exception as exc:  # resolution must never crash a report
                logger.warning("Matcher failed for %r: %s", title, exc)
        idx = getattr(repo, "index", None)
        for stage in ("exact", "normalized", "synonym"):
            fn = getattr(idx, stage, None)
            if callable(fn):
                jid = fn(title)
                if jid:
                    return jid
        return None

    def _best_levels(self, employee_id: str) -> dict[str, tuple[int, float]]:
        """skill_id -> (highest assessed level, its confidence)."""
        best: dict[str, tuple[int, float]] = {}
        for a in (self._repo.skill_assessments.get(employee_id) or []):
            cur = best.get(a.skill_id)
            if cur is None or a.current_level > cur[0]:
                best[a.skill_id] = (a.current_level, a.confidence)
        return best

    def _gaps_for_job(self, employee_id: str, job_id: str) -> list[SkillGap]:
        have = self._best_levels(employee_id)
        gaps: list[SkillGap] = []
        for r in self._repo.role_skill_map.get(job_id, []):
            cur, conf = have.get(r.skill_id, (0, 0.0))
            sk = self._repo.skills.get(r.skill_id)
            gaps.append(SkillGap(
                skill_id=r.skill_id,
                skill_name=(sk.skill_name if sk else r.skill_id),
                skill_type=r.skill_type,
                required_level=r.required_level,
                current_level=cur,
                gap=max(0, r.required_level - cur),
                confidence=conf,
            ))
        return gaps

    # ------------------------------------------------------------------ public
    def coverage_for_employee(self, employee_id: str) -> EmployeeCoverage:
        emp = self._repo.employees.get(employee_id)
        title = emp.current_title if emp else None
        job_id = self._job_id_for(title)
        job = self._repo.jobs.get(job_id) if job_id else None
        return EmployeeCoverage(
            employee_id=employee_id,
            job_id=job_id,
            job_title=(job.standard_title if job else title),
            gaps=(self._gaps_for_job(employee_id, job_id) if job_id else []),
        )

    def career_opportunities(self, employee_id: str) -> list[CareerOpportunity]:
        emp = self._repo.employees.get(employee_id)
        if not emp:
            return []
        job_id = self._job_id_for(emp.current_title)
        if not job_id:
            return []
        step = self._repo.career_paths.get(job_id)
        if not step or not step.next_job_id:
            return []
        gaps = self._gaps_for_job(employee_id, step.next_job_id)
        core_open = [g for g in gaps if g.skill_type == "Core" and g.gap > 0]
        job = self._repo.jobs.get(step.next_job_id)
        return [CareerOpportunity(
            from_job_id=job_id,
            to_job_id=step.next_job_id,
            to_title=(job.standard_title if job else step.next_title),
            ready=(len(core_open) == 0),
            gaps=gaps,
        )]

    def team_summary(self, function: Optional[str] = None) -> dict:
        """Aggregate coverage across matched employees (optionally one function).
        `avg_confidence` is how validated the picture is — the honesty dial."""
        rows: list[EmployeeCoverage] = []
        for emp in self._repo.employees.values():
            cov = self.coverage_for_employee(emp.employee_id)
            if not cov.job_id:
                continue
            if function:
                job = self._repo.jobs.get(cov.job_id)
                if not job or job.function != function:
                    continue
            rows.append(cov)
        n = len(rows)
        all_gaps = [g for c in rows for g in c.gaps]
        avg_cov = round(sum(c.coverage for c in rows) / n, 3) if n else 0.0
        avg_conf = round(sum(g.confidence for g in all_gaps) / len(all_gaps), 3) if all_gaps else 0.0
        return {
            "employees_matched": n,
            "avg_coverage": avg_cov,
            "avg_confidence": avg_conf,
            "open_gaps": sum(1 for g in all_gaps if g.gap > 0),
        }


# ------------------------------------------------------- session/upload bridge
class _OverlayRepository:
    """A read-only view of the reference repository with an uploaded cohort's
    people and assessments laid over it.

    Uploaded assessments live in the UI session, not in the reference workbook,
    and the two must not be confused: mutating the shared repository would leak
    one client's file into every other view. Everything except `employees` and
    `skill_assessments` proxies straight through to the real repository, so the
    canonical taxonomy, role requirements and career steps stay authoritative.
    """

    def __init__(self, base, employees, skill_assessments) -> None:
        self._base = base
        self.employees = employees
        self.skill_assessments = skill_assessments

    def __getattr__(self, name):          # only called for attrs not set above
        return getattr(self._base, name)


class _OverlayCatalog:
    """Catalog whose `.repository` is the overlay; everything else is the real one."""

    def __init__(self, base, repository) -> None:
        self._base = base
        self.repository = repository

    def __getattr__(self, name):
        return getattr(self._base, name)


def service_for_assessments(catalog, assessments, *, titles=None, source="self",
                            confidence=None, assessed_at="", matcher=None) -> AssessmentService:
    """Build an AssessmentService over assessments captured from an upload.

    `assessments` is the shape the assessment page already produces --
    ``{employee_key: {skill_id: level}}`` -- and `titles` maps the same keys to
    the person's current job title, which is what lets the service resolve each
    person to their *own* role rather than making someone pick one from a list.

    A key with no title falls back to the reference repository's employee record
    if one exists under that key, so this works for both an uploaded cohort and
    the built-in demo data.
    """
    repo = getattr(catalog, "repository", None)
    if repo is None:
        raise ValueError("service_for_assessments needs a Catalog with a .repository")

    titles = titles or {}
    conf = DEFAULT_CONFIDENCE.get(source, 0.5) if confidence is None else float(confidence)

    employees: dict[str, Employee] = {}
    rows: dict[str, list[SkillAssessment]] = {}

    for key, skills in (assessments or {}).items():
        known = repo.employees.get(key)
        title = (titles.get(key) or (known.current_title if known else "") or "").strip()
        employees[key] = Employee(
            employee_id=key,
            name=(known.name if known else key),
            current_title=title,
        )
        rows[key] = [
            SkillAssessment(employee_id=key, skill_id=sid, current_level=int(level),
                            source=source, confidence=conf, assessed_at=assessed_at)
            for sid, level in (skills or {}).items()
            if level is not None and int(level) > 0
        ]

    overlay = _OverlayRepository(repo, employees, rows)
    return AssessmentService(_OverlayCatalog(catalog, overlay), matcher=matcher)

"""
core/catalog.py

Loads the jobsy_reference_library.xlsx workbook and exposes it as a typed catalog
that MatchingService and the Streamlit app can query.

Usage:
    catalog = Catalog("jobsy_reference_library.xlsx")
    catalog.load()
    result = catalog.get_complete_job("J-HR-03")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger("jobsy")

# Sheet name in workbook -> key the Repository expects
SHEET_MAP = {
    "Jobs":        "jobs",
    "JobProfiles": "profiles",
    "SalaryBands": "salary",
    "TitleMapping":"titles",
    "CareerPaths": "career",
    "Levels":      "levels",
    "Employees":   "employees",
    "Categories":  "categories",
    "Skills":      "skills",
    "CompetencyLevels": "competencylevels",
    "RoleSkillMap":"roleskillmap",
    "JobGrades":   "jobgrades",
    "Industries":  "industries",
    "IndustrySalaryFactors": "industrysalaryfactors",
    "IndustrySkills": "industryskills",
    "SeniorityLevels": "senioritylevels",
    "SkillProficiency": "skillproficiency",
    "BenefitsCatalog": "benefitscatalog",
    "BenefitsObservations": "benefitsobservations",
    "LevelBenefitsFactors": "levelbenefitsfactors",
    # Added 2026-09-03. These two were in the database and read past this map by
    # whoever needed them, which made the variable-pay figures a second chain:
    # invisible to Data Quality, absent from the export, outside the parity gate.
    "PayMix":      "paymix",
    "PayElements": "payelements",
    # Added 2026-09-06, and the reason is the one three lines above verbatim.
    # 0016 split these two out of JobProfiles and SeniorityLevels; until now
    # neither was in this map, so the library EXPORT and the Data Quality
    # freshness scorecard — which both walk it — could not see them. It cost
    # nothing while ManagementLevel still rode along on the JobProfiles sheet,
    # and on the day 0016 §3 drops the old columns an export would have lost
    # the positioning claim in silence. That is the same shape as PayMix: not a
    # wrong number, an absent one, which is the harder kind to notice.
    #
    # The import prefers these sheets and falls back to the shared ones, so a
    # workbook already in a client's hands keeps importing — see
    # TableSpec.prefers_sheet.
    "JobProfilePositioning": "jobpositioning",
    "SeniorityGradeBinding": "senioritybinding",
    # Added 2026-09-06 for the same reason again, and this time the gap was
    # measurable: 0019 split industry_skills, 0023 gave the new table a review
    # interval, and this map did not know it existed. The freshness scorecard
    # therefore listed it and the export could not write it — the two halves of
    # governance disagreeing about whether a table is there.
    #
    # A workbook in a client's hands still has all fifty rows on IndustrySkills.
    # The import reads this sheet when the workbook has it and falls back to
    # splitting the shared one by is_regulatory_skill_id().
    "IndustryRegulatorySkills": "industryregulatoryskills",
}


class Catalog:
    """Reads the Excel reference library and builds a typed Repository."""

    def __init__(self, path: str = "jobsy_reference_library.xlsx",
                 source: str | None = None, client=None, org_id: str | None = None) -> None:
        self.path = Path(path)
        self.repository = None
        self.frames: dict = {}
        self._loaded = False
        # "excel" | "db". None takes config.LIBRARY_SOURCE, so the cutover is a
        # one-line config change and every existing Catalog(path) call site
        # keeps working untouched.
        if source is None:
            try:
                from core.config import LIBRARY_SOURCE
                source = LIBRARY_SOURCE
            except Exception:
                source = "excel"
        self.source = source
        # A caller that already holds a database client passes it in — the app
        # does exactly that once it reads the library as the signed-in user, so
        # 0008's policies decide what comes back instead of the loader deciding
        # for itself. None means "resolve from configuration", which is the
        # secret key until LIBRARY_CLIENT says otherwise.
        self._client = client
        self._org_id = org_id
        #: sheet -> how many library rows this client's own rows replaced.
        #: Empty on a single-organisation deployment. Surfaced rather than
        #: silent: precedence nobody can see is precedence nobody can check.
        self.overrides: dict = {}
        # What the library was ACTUALLY read from, which is not always what was
        # asked for — see the fallback in _load_from_db(). The sidebar shows
        # this, because "which source am I looking at" stops being obvious the
        # moment a fallback exists.
        self.active_source = None

    def _user_scoped(self) -> bool:
        """Is the library being read with the signed-in user's own credential?"""
        if self._client is not None:
            return True
        try:
            from core.config import LIBRARY_CLIENT
            return LIBRARY_CLIENT == "user"
        except Exception:
            return False

    def _load_from_db(self) -> dict | None:
        """Frames from Postgres, or None to fall back to the workbook.

        A database that is unreachable must not take the app down: the
        committed workbook is a complete, working master and staying up on it
        beats failing hard. But falling back SILENTLY would be worse than
        either — a stale library that looks live is the exact thing this
        migration is meant to end — so it is logged loudly and surfaced.

        THE FALLBACK IS OFF WHEN THE READ IS USER-SCOPED, and that is not a
        detail. Once the library is read through the signed-in user's client,
        the reason it can come back empty is no longer "the database is down" —
        it is "this account may not read that org". Answering that with the
        workbook committed to this repo would hand one client the default
        library as though it were theirs: a tenancy leak wearing the clothes of
        a resilience feature. There is nothing safe to fall back TO, so it
        fails, loudly, and the app says whose data could not be read.
        """
        user_scoped = self._user_scoped()
        try:
            from core.db_loader import load_frames_from_config
            self.overrides = {}
            frames = load_frames_from_config(client=self._client, org_id=self._org_id,
                                             overrides=self.overrides)
        except Exception as exc:
            if user_scoped:
                raise RuntimeError(
                    f"The reference library could not be read for this account "
                    f"({type(exc).__name__}: {exc}). The workbook in this repo is not a "
                    f"substitute — it belongs to no client."
                ) from exc
            logger.error("Could not load the library from the database (%s: %s). "
                         "Falling back to the workbook at %s — this data may be stale.",
                         type(exc).__name__, exc, self.path)
            return None

        missing = [k for k in ("jobs", "titles", "salary")
                   if k not in frames or frames[k] is None or len(frames[k]) == 0]
        if missing:
            # An empty database reads as a successful load of nothing, which
            # would build an empty catalog and look like a data disaster rather
            # than a configuration one. Refuse it and use the workbook.
            if user_scoped:
                raise RuntimeError(
                    f"The database returned no rows for {', '.join(missing)} as this account. "
                    f"Either the client's library is not seeded, or the policies do not let "
                    f"this account read it — the workbook is not the answer to either."
                )
            logger.error("The database returned no rows for %s — it is probably not seeded. "
                         "Falling back to the workbook.", ", ".join(missing))
            return None
        return frames

    def load(self) -> "Catalog":
        if self._loaded:
            return self

        data = None
        if self.source == "db":
            data = self._load_from_db()
            if data is not None:
                self.active_source = "db"

        if data is not None:
            return self._build(data)

        if not self.path.exists():
            raise FileNotFoundError(
                f"Reference library not found at '{self.path}'. "
                "Place jobsy_reference_library.xlsx at the repo root or update WORKBOOK_PATH in core/config.py."
            )

        logger.info("Loading reference library from %s", self.path)

        # read all sheets that exist in the workbook
        try:
            raw = pd.read_excel(str(self.path), sheet_name=None, dtype=str)
        except Exception as exc:
            import traceback
            raise RuntimeError(f"Could not read workbook: {exc}\n{traceback.format_exc()}") from exc

        # map sheet names to repository keys; missing optional sheets stay None
        data: dict = {}
        for sheet_name, repo_key in SHEET_MAP.items():
            df = raw.get(sheet_name)
            if df is not None:
                # strip whitespace from all string columns
                df = df.apply(
                    lambda col: col.str.strip() if col.dtype == object else col
                )
                # convert numeric columns back to numbers where appropriate
                for col in ("Min", "Max", "Order"):
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                data[repo_key] = df
                logger.info("  %s: %d rows", sheet_name, len(df))
            else:
                logger.warning("  Sheet '%s' not found in workbook — skipped.", sheet_name)

        self.active_source = "excel"
        return self._build(data)

    def _build(self, data: dict) -> "Catalog":
        """Validate the frames and build the Repository.

        Shared by both sources deliberately: the Excel path and the database
        path must go through the same checks and the same Repository call, or
        "the app behaves identically" stops being something the code enforces.
        """
        # ensure required sheets are present
        for required in ("jobs", "titles", "salary"):
            if required not in data or data[required] is None or len(data[required]) == 0:
                raise ValueError(
                    f"Reference library is missing required data for '{required}' "
                    f"(source: {self.active_source}). "
                    "Check that Jobs, TitleMapping, and SalaryBands are present."
                )

        # Keep the frames as they were read. The Repository is a typed view and
        # cannot be turned back into the library; the export path needs what
        # actually arrived, from whichever source it arrived from.
        self.frames = dict(data)

        # build the repository (lazy import to keep circular imports clean)
        from core.repository import Repository

        try:
            self.repository = Repository(data, validate=True)
        except Exception as exc:
            import traceback
            raise RuntimeError(
                f"Repository build failed: {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            ) from exc
        self._loaded = True
        logger.info(
            "Catalog loaded from %s: %d roles, %d mappings, %d salary bands",
            self.active_source,
            len(self.repository.jobs),
            len(self.repository.title_mapping),
            len(self.repository.salary),
        )
        return self

    @property
    def fell_back_to_excel(self) -> bool:
        """The database was asked for and the workbook answered.

        Worth surfacing rather than inferring: the app works perfectly in this
        state, which is exactly why nobody would notice they are reading a file
        that stopped being the master.
        """
        return self.source == "db" and self.active_source == "excel"

    def get_complete_job(self, job_id: str) -> Optional[dict]:
        """Return job + profile + salary + career step for a given JobID."""
        if not self._loaded:
            self.load()

        job = self.repository.jobs.get(job_id)
        if not job:
            return None

        return {
            "job":      job,
            "profile":  self.repository.profiles.get(job_id),
            "salary":   self.repository.salary.get((job.function, job.level)),
            "next_role": self.repository.career_paths.get(job_id),
        }


    def get_role_skills(self, job_id: str) -> list:
        """Return list of (RoleSkillRequirement, Skill) tuples for a role, sorted by type then level desc."""
        if not self._loaded:
            self.load()
        reqs = self.repository.role_skill_map.get(job_id, [])
        TYPE_ORDER = {"Core": 0, "Adjacent": 1, "Leadership": 2}
        reqs_sorted = sorted(reqs, key=lambda r: (TYPE_ORDER.get(r.skill_type, 9), -r.required_level))
        result = []
        for req in reqs_sorted:
            skill = self.repository.skills.get(req.skill_id)
            if skill:
                result.append((req, skill))
        return result


    def industry_adjusted_band(self, function: str, level: str, industry_id: str = None):
        """Return a SalaryBand with values scaled by the industry factor (or baseline)."""
        band = self.repository.salary.get((function, level))
        if not band:
            return None
        if not industry_id:
            return band
        factor = self.repository.industry_factors.get((industry_id, function), 1.0)
        from services.salary_service import scale_band
        return scale_band(band, factor)

    def industry_factor(self, function: str, industry_id: str) -> float:
        return self.repository.industry_factors.get((industry_id, function), 1.0)

    def get_industry_skills(self, industry_id: str):
        """Sector-typical practice plus what this market legally requires.

        Two tables since the 2026-09-06 split, one answer here, so no caller had
        to learn about it. The regulatory half resolves through _MarketRows, so
        a Belgian session gets PC 111/209 and never Wwft.
        """
        universal = self.repository.industry_skills.get(industry_id, [])
        regulatory = self.repository.industry_regulatory_skills.get(industry_id, [])
        return list(universal) + list(regulatory)

    def l_level_for(self, level: str) -> tuple:
        """Map a base level (Junior/Medior/Senior/Lead) to (L-code, L-name)."""
        mapping = {"Junior": ("L1","Starter"), "Medior": ("L2","Developing"),
                   "Senior": ("L3","Senior"), "Lead": ("L4","Manager")}
        return mapping.get(level, ("", ""))

    def seniority_level(self, l_code: str):
        return self.repository.seniority_levels.get(l_code)

    def skill_gap(self, current_skills: dict, target_job_id: str) -> list:
        """
        Compute the skill gap between a person's current skills and a target role.

        current_skills: dict of {skill_id: current_level (1-5)}
        Returns list of dicts with gap info, sorted by gap size desc.
        """
        if not self._loaded:
            self.load()
        role_skills = self.get_role_skills(target_job_id)
        gaps = []
        for req, skill in role_skills:
            current = current_skills.get(req.skill_id, 0)
            gap = req.required_level - current
            gaps.append({
                "skill_id":       req.skill_id,
                "skill_name":     skill.skill_name,
                "category":       skill.category,
                "skill_type":     req.skill_type,
                "required_level": req.required_level,
                "current_level":  current,
                "gap":            gap,
                "status":         "gap" if gap > 0 else ("match" if gap == 0 else "exceeds"),
            })
        gaps.sort(key=lambda g: (-g["gap"], g["skill_type"]))
        return gaps

    def competency_level_name(self, level: int) -> str:
        if not self._loaded:
            self.load()
        cl = self.repository.competency_levels.get(level)
        return cl.name if cl else str(level)

    def proficiency_rubric(self, category: str = None) -> dict:
        """Behavioural anchors per proficiency level (1-5).

        With a category → {level: {"name","anchor"}} for that category.
        Without → {category: {level: {...}}} for all categories.
        """
        if not self._loaded:
            self.load()
        rub = self.repository.skill_proficiency
        return rub.get(category, {}) if category else rub

    def proficiency_anchor(self, category: str, level: int) -> str:
        """The behavioural anchor text for a category at a given level (or '')."""
        entry = self.proficiency_rubric(category).get(int(level)) if level else None
        return entry["anchor"] if entry else ""

    def search_jobs(self, query: str = "", function: str = "", level: str = "") -> list:
        """Simple filtered search over standard titles."""
        if not self._loaded:
            self.load()
        results = list(self.repository.jobs.values())
        if query:
            q = query.lower()
            results = [j for j in results if q in j.standard_title.lower()]
        if function:
            results = [j for j in results if j.function == function]
        if level:
            results = [j for j in results if j.level == level]
        return results

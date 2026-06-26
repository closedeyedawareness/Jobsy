"""
core/catalog.py

Loads the reference_library.xlsx workbook and exposes it as a typed catalog
that MatchingService and the Streamlit app can query.

Usage:
    catalog = Catalog("reference_library.xlsx")
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
}


class Catalog:
    """Reads the Excel reference library and builds a typed Repository."""

    def __init__(self, path: str = "reference_library.xlsx") -> None:
        self.path = Path(path)
        self.repository = None
        self._loaded = False

    def load(self) -> "Catalog":
        if self._loaded:
            return self

        if not self.path.exists():
            raise FileNotFoundError(
                f"Reference library not found at '{self.path}'. "
                "Place reference_library.xlsx at the repo root or update WORKBOOK_PATH in core/config.py."
            )

        logger.info("Loading reference library from %s", self.path)

        # read all sheets that exist in the workbook
        try:
            raw = pd.read_excel(str(self.path), sheet_name=None, dtype=str)
        except Exception as exc:
            raise RuntimeError(f"Could not read workbook: {exc}") from exc

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

        # ensure required sheets are present
        for required in ("jobs", "titles", "salary"):
            if required not in data or data[required] is None or len(data[required]) == 0:
                raise ValueError(
                    f"Workbook is missing required sheet for '{required}'. "
                    "Check that Jobs, TitleMapping, and SalaryBands sheets exist."
                )

        # build the repository (lazy import to keep circular imports clean)
        from core.repository import Repository

        self.repository = Repository(data, validate=True)
        self._loaded = True
        logger.info(
            "Catalog loaded: %d roles, %d mappings, %d salary bands",
            len(self.repository.jobs),
            len(self.repository.title_mapping),
            len(self.repository.salary),
        )
        return self

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

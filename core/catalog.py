"""
Jobsy Catalog
Enhanced Catalog facade for the Jobsy reference library.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Optional

from jobsy.core.loader import Loader
from jobsy.core.repository import Repository
from jobsy.core.logger import logger
from jobsy.core.utils import normalize_title


class CatalogNotLoadedError(RuntimeError):
    """Raised when the catalog is accessed before load()."""


class Catalog:
    """Public API for the Jobsy reference library."""

    def __init__(self, workbook: str | Path):
        self.workbook = Path(workbook)
        self.repository: Optional[Repository] = None
        self.loaded = False
        self.loaded_at: Optional[datetime] = None
        self._lock = RLock()

    @property
    def is_loaded(self) -> bool:
        return self.loaded

    def load(self) -> None:
        logger.info("Loading reference library...")
        loader = Loader(self.workbook)
        data = loader.load()
        self.repository = Repository(data)
        self.loaded = True
        self.loaded_at = datetime.now()
        self.list_functions.cache_clear()
        self.list_levels.cache_clear()
        logger.info("Catalog ready.")

    def reload(self) -> None:
        with self._lock:
            self.load()

    def _ensure_loaded(self) -> None:
        if not self.loaded or self.repository is None:
            raise CatalogNotLoadedError("Catalog has not been loaded.")

    def health(self) -> dict:
        self._ensure_loaded()
        stats = self.repository.statistics() if hasattr(self.repository, "statistics") else {}
        return {
            "status": "OK",
            "loaded": self.loaded,
            "loaded_at": self.loaded_at,
            **stats,
        }

    def statistics(self) -> dict:
        self._ensure_loaded()
        if hasattr(self.repository, "statistics"):
            return self.repository.statistics()
        return {}

    def get_job(self, job_id: str):
        self._ensure_loaded()
        return self.repository.jobs.get(job_id)

    def find_job(self, title: str):
        self._ensure_loaded()
        logger.debug("Finding job: %s", title)
        return self.repository.find_job(title) if hasattr(self.repository, "find_job") else None

    def search_jobs(self, text: str):
        self._ensure_loaded()
        logger.debug("Searching jobs: %s", text)
        key = normalize_title(text)
        return sorted(
            [j for j in self.repository.jobs.values()
             if key in normalize_title(j.standard_title)],
            key=lambda j: j.standard_title,
        )

    @lru_cache(maxsize=None)
    def list_functions(self):
        self._ensure_loaded()
        if hasattr(self.repository, "jobs_by_function"):
            return sorted(self.repository.jobs_by_function.keys())
        return sorted({j.function for j in self.repository.jobs.values()})

    @lru_cache(maxsize=None)
    def list_levels(self):
        self._ensure_loaded()
        if hasattr(self.repository, "jobs_by_level"):
            return sorted(self.repository.jobs_by_level.keys())
        return sorted({j.level for j in self.repository.jobs.values()})

    def count_jobs(self): return len(self.repository.jobs)
    def count_profiles(self): return len(getattr(self.repository, "profiles", {}))
    def count_salary_bands(self): return len(getattr(self.repository, "salary", {}))
    def count_title_mappings(self): return len(getattr(self.repository, "title_mapping", {}))

    def get_complete_job(self, job_id: str):
        self._ensure_loaded()
        job = self.get_job(job_id)
        if not job:
            return None
        profile = getattr(self.repository, "profiles", {}).get(job_id)
        salary = getattr(self.repository, "salary", {}).get((job.function, job.level))
        next_role = getattr(self.repository, "career_paths", {}).get(job_id)
        return {
            "job": job,
            "profile": profile,
            "salary": salary,
            "next_role": next_role,
        }
      

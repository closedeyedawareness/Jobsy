"""
jobsy/services/matching_service.py

Consolidated matching service.

Takes a free-text job title (from a form) and returns the advised standard
role, its profile description, and its salary range -- plus a confidence score
and a review flag. Runs the deterministic pipeline:

    Normalize -> Exact -> Normalized -> Synonym -> Fuzzy (RapidFuzz) -> [AI: future]

Design notes
------------
* Resolution (string -> JobID) is delegated to a TitleIndex (the core
  SearchIndex). Enrichment (JobID -> profile + salary) goes through the
  Catalog's public `get_complete_job`. The service owns only the pipeline
  ordering, confidence scoring, and the review decision.
* Enrichment is defensive: the data layer currently disagrees about whether a
  job exposes `title` (models.Job) or `standard_title` (Catalog.search_jobs),
  so we read whichever is present rather than hard-coding one.
* Fuzzy degrades gracefully: if `rapidfuzz` is not installed the stage is
  skipped and the rest of the pipeline still works.

Confidence hierarchy is intentional and ordered:
    exact 100 > normalized 98 > synonym 96 > fuzzy <= 95
so a fuzzy hit can never outrank a deterministic one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol, Sequence, runtime_checkable

import logging
logger = logging.getLogger('jobsy')
from core.search_index import SearchIndex  # noqa: F401  (type/default use)

__all__ = ["MatchType", "MatchResult", "MatchingSummary", "MatchingService"]


class MatchType(str, Enum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    SYNONYM = "synonym"
    FUZZY = "fuzzy"
    NONE = "none"
    # AI = "ai"  # reserved for the future stage


# --------------------------------------------------------------------- ports
@runtime_checkable
class TitleIndex(Protocol):
    """What the service needs from a resolver (satisfied by core.SearchIndex)."""
    def exact(self, title: str) -> Optional[str]: ...
    def normalized(self, title: str) -> Optional[str]: ...
    def synonym(self, title: str) -> Optional[str]: ...
    def fuzzy(self, title: str, score_cutoff: float = ...) -> Optional[tuple[str, float]]: ...


@runtime_checkable
class JobCatalog(Protocol):
    """What the service needs from the Catalog for enrichment."""
    def get_complete_job(self, job_id: str) -> Optional[dict]: ...


# --------------------------------------------------------------------- result
@dataclass
class MatchResult:
    input_title: str
    match_type: MatchType
    confidence: int
    requires_review: bool
    matched: bool
    job_id: Optional[str] = None
    standard_title: Optional[str] = None
    function: Optional[str] = None
    level: Optional[str] = None
    description: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: str = "EUR"

    @property
    def salary_range(self) -> Optional[tuple[float, float]]:
        if self.salary_min is None or self.salary_max is None:
            return None
        return (self.salary_min, self.salary_max)


@dataclass
class MatchingSummary:
    total: int
    matched: int
    review: int
    unmatched: int
    avg_confidence: float
    by_type: dict[str, int]


# --------------------------------------------------- enrichment helpers (tolerant)
def _attr(obj, *names: str):
    if obj is None:
        return None
    if isinstance(obj, dict):
        for name in names:
            if obj.get(name) is not None:
                return obj[name]
        return None
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _profile_description(profile) -> Optional[str]:
    text = _attr(profile, "description", "Description", "summary", "Summary",
                 "profile", "Profile")
    return str(text) if text is not None else None


def _salary_bounds(salary, currency: str):
    if salary is None:
        return None, None, currency
    if isinstance(salary, (tuple, list)) and len(salary) >= 2:
        try:
            return float(salary[0]), float(salary[1]), currency
        except (TypeError, ValueError):
            return None, None, currency
    low = _attr(salary, "min", "Min", "salary_min", "MinSalary", "low", "Low")
    high = _attr(salary, "max", "Max", "salary_max", "MaxSalary", "high", "High")
    cur = _attr(salary, "currency", "Currency") or currency
    try:
        low = float(low) if low is not None else None
        high = float(high) if high is not None else None
    except (TypeError, ValueError):
        low = high = None
    return low, high, cur


# --------------------------------------------------------------------- service
class MatchingService:
    """Deterministic title-matching pipeline with optional RapidFuzz stage."""

    EXACT_CONFIDENCE = 100
    NORMALIZED_CONFIDENCE = 98
    SYNONYM_CONFIDENCE = 96
    FUZZY_MAX_CONFIDENCE = 95

    def __init__(
        self,
        catalog: JobCatalog,
        index: Optional[TitleIndex] = None,
        *,
        review_threshold: int = 85,
        fuzzy_score_cutoff: float = 80.0,
        enable_fuzzy: bool = True,
    ) -> None:
        self._catalog = catalog
        self._index = index or self._index_from_catalog(catalog)
        self.review_threshold = review_threshold
        self.fuzzy_score_cutoff = fuzzy_score_cutoff
        self.enable_fuzzy = enable_fuzzy

        if self.enable_fuzzy and not getattr(self._index, "fuzzy", None):
            logger.warning("Fuzzy enabled but the index exposes no fuzzy(); disabling.")
            self.enable_fuzzy = False

    @staticmethod
    def _index_from_catalog(catalog: JobCatalog) -> TitleIndex:
        repo = getattr(catalog, "repository", None)
        index = getattr(repo, "index", None)
        if index is None or not isinstance(index, TitleIndex):
            raise ValueError(
                "Catalog has no staged SearchIndex. Upgrade core/search_index.py "
                "or pass an index= explicitly."
            )
        return index

    # ----------------------------------------------------------------- public
    def match(self, title: str) -> MatchResult:
        raw = (title or "").strip()
        if not raw:
            return self._no_match(raw)

        resolution = self._resolve(raw)
        if resolution is None:
            return self._no_match(raw)

        job_id, match_type, confidence = resolution
        return self._enrich(raw, job_id, match_type, confidence)

    def match_titles(self, titles: Sequence[str]) -> list[MatchResult]:
        return [self.match(t) for t in titles]

    def match_dataframe(self, df, column: str = "title"):
        """Return a copy of `df` with match columns appended."""
        if column not in df.columns:
            raise KeyError(f"Column '{column}' not found in DataFrame.")
        results = self.match_titles(df[column].fillna("").astype(str).tolist())
        out = df.copy()
        out["matched_job_id"] = [r.job_id for r in results]
        out["matched_title"] = [r.standard_title for r in results]
        out["function"] = [r.function for r in results]
        out["level"] = [r.level for r in results]
        out["confidence"] = [r.confidence for r in results]
        out["match_type"] = [r.match_type.value for r in results]
        out["requires_review"] = [r.requires_review for r in results]
        out["salary_min"] = [r.salary_min for r in results]
        out["salary_max"] = [r.salary_max for r in results]
        return out

    def summarize(self, results: Sequence[MatchResult]) -> MatchingSummary:
        total = len(results)
        matched = sum(1 for r in results if r.matched)
        review = sum(1 for r in results if r.requires_review)
        avg = round(sum(r.confidence for r in results) / total, 1) if total else 0.0
        by_type: dict[str, int] = {}
        for r in results:
            by_type[r.match_type.value] = by_type.get(r.match_type.value, 0) + 1
        return MatchingSummary(total, matched, review, total - matched, avg, by_type)

    # ---------------------------------------------------------------- internal
    def _resolve(self, title: str) -> Optional[tuple[str, MatchType, int]]:
        job_id = self._index.exact(title)
        if job_id:
            return job_id, MatchType.EXACT, self.EXACT_CONFIDENCE

        job_id = self._index.normalized(title)
        if job_id:
            return job_id, MatchType.NORMALIZED, self.NORMALIZED_CONFIDENCE

        job_id = self._index.synonym(title)
        if job_id:
            return job_id, MatchType.SYNONYM, self.SYNONYM_CONFIDENCE

        if self.enable_fuzzy:
            hit = self._index.fuzzy(title, self.fuzzy_score_cutoff)
            if hit is not None:
                job_id, score = hit
                confidence = min(self.FUZZY_MAX_CONFIDENCE, int(round(score)))
                return job_id, MatchType.FUZZY, confidence

        return None

    def _enrich(self, input_title: str, job_id: str,
                match_type: MatchType, confidence: int) -> MatchResult:
        requires_review = confidence < self.review_threshold

        complete = None
        try:
            complete = self._catalog.get_complete_job(job_id)
        except Exception as exc:  # enrichment must never break matching
            logger.warning("Enrichment failed for %s: %s", job_id, exc)

        std_title = function = level = description = None
        salary_min = salary_max = None
        currency = "EUR"

        if complete:
            job = complete.get("job") if isinstance(complete, dict) else None
            std_title = _attr(job, "standard_title", "title", "StandardTitle", "Title")
            function = _attr(job, "function", "Function")
            level = _attr(job, "level", "Level")
            description = _profile_description(complete.get("profile"))
            salary_min, salary_max, currency = _salary_bounds(
                complete.get("salary"), currency
            )

        return MatchResult(
            input_title=input_title,
            match_type=match_type,
            confidence=confidence,
            requires_review=requires_review,
            matched=True,
            job_id=job_id,
            standard_title=str(std_title) if std_title is not None else None,
            function=str(function) if function is not None else None,
            level=str(level) if level is not None else None,
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
        )

    def _no_match(self, input_title: str) -> MatchResult:
        return MatchResult(
            input_title=input_title,
            match_type=MatchType.NONE,
            confidence=0,
            requires_review=True,
            matched=False,
        )

"""
jobsy/core/search_index.py

Resolves free-text job titles to canonical JobIDs in deterministic stages.

Stages, in descending order of trust:
    exact       case-insensitive match on a standard title
    normalized  match after lowercasing + stripping punctuation/whitespace
    synonym     match against the TitleMapping (existing title -> standard)
    fuzzy       RapidFuzz approximate match (optional; needs `rapidfuzz`)

The index is built once from the reference DataFrames and owns no business
logic -- it only answers "which JobID does this string point to?". Confidence
scoring, review thresholds, and enrichment live in the MatchingService.

Backward compatible: the original `build(jobs_df, titles_df)` and `find(x)`
methods still work, so the existing Repository call site needs no change.
"""

from __future__ import annotations

from typing import Optional

from .utils import normalize_title

try:  # fuzzy is optional; the service degrades gracefully without it
    from rapidfuzz import fuzz, process
    _HAS_RAPIDFUZZ = True
except ImportError:  # pragma: no cover
    _HAS_RAPIDFUZZ = False

__all__ = ["SearchIndex"]


def _pick(row, *names: str):
    """Return the first present, non-empty attribute on a row (column-tolerant)."""
    for name in names:
        value = getattr(row, name, None)
        if value is not None:
            text = str(value).strip()
            if text and text.lower() != "nan":
                return value
    return None


class SearchIndex:
    """Staged title -> JobID resolver built from the reference library."""

    def __init__(self) -> None:
        self._exact: dict[str, str] = {}        # lower(standard_title) -> job_id
        self._normalized: dict[str, str] = {}   # normalize(standard_title) -> job_id
        self._synonym: dict[str, str] = {}      # normalize(existing_title) -> job_id
        self._fuzzy_choices: list[str] = []     # normalized candidate strings
        self._fuzzy_jobs: list[str] = []        # parallel job_ids (same index)
        self.i: dict[str, str] = {}             # legacy combined index

    # ------------------------------------------------------------------ build
    def build(self, jobs_df, titles_df=None) -> "SearchIndex":
        """Populate the index from the Jobs and TitleMapping DataFrames."""
        for row in jobs_df.itertuples(index=False):
            job_id = _pick(row, "JobID", "job_id")
            title = _pick(row, "StandardTitle", "standard_title", "title", "Title")
            if job_id is None or title is None:
                continue
            job_id, title = str(job_id), str(title)
            self._exact.setdefault(title.strip().lower(), job_id)
            self._normalized.setdefault(normalize_title(title), job_id)
            self.i.setdefault(normalize_title(title), job_id)
            self._add_fuzzy(title, job_id)

        if titles_df is not None:
            for row in titles_df.itertuples(index=False):
                existing = _pick(row, "ExistingTitle", "existing_title", "Title", "title")
                if existing is None:
                    continue
                job_id = _pick(row, "JobID", "job_id")
                if job_id is None:  # mapping references a standard title, not an id
                    std = _pick(row, "StandardTitle", "standard_title")
                    if std is not None:
                        job_id = self._normalized.get(normalize_title(str(std)))
                if job_id is None:
                    continue
                key = normalize_title(str(existing))
                self._synonym.setdefault(key, str(job_id))
                self.i.setdefault(key, str(job_id))
                self._add_fuzzy(str(existing), str(job_id))

        return self

    def _add_fuzzy(self, title: str, job_id: str) -> None:
        key = normalize_title(title)
        if key:
            self._fuzzy_choices.append(key)
            self._fuzzy_jobs.append(job_id)

    # --------------------------------------------------------------- resolvers
    def exact(self, title: str) -> Optional[str]:
        """Case-insensitive exact match on a standard title."""
        return self._exact.get(title.strip().lower())

    def normalized(self, title: str) -> Optional[str]:
        """Match after normalization (lowercase, punctuation/whitespace collapsed)."""
        return self._normalized.get(normalize_title(title))

    def synonym(self, title: str) -> Optional[str]:
        """Match against the TitleMapping (existing title -> standard)."""
        return self._synonym.get(normalize_title(title))

    def fuzzy(self, title: str, score_cutoff: float = 80.0) -> Optional[tuple[str, float]]:
        """Approximate match via RapidFuzz. Returns (job_id, score) or None."""
        if not _HAS_RAPIDFUZZ or not self._fuzzy_choices:
            return None
        query = normalize_title(title)
        if not query:
            return None
        hit = process.extractOne(
            query, self._fuzzy_choices, scorer=fuzz.WRatio, score_cutoff=score_cutoff
        )
        if hit is None:
            return None
        _choice, score, idx = hit
        return self._fuzzy_jobs[idx], float(score)

    # ------------------------------------------------------------------ legacy
    def find(self, x: str) -> Optional[str]:
        """Original single-lookup behaviour (standard + synonym, normalized)."""
        return self.i.get(normalize_title(x))

    @property
    def fuzzy_available(self) -> bool:
        return _HAS_RAPIDFUZZ

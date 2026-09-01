"""
core/countries.py — which country the app is looking at.

Jobsy was single-country by assumption, not by decision: `config.COUNTRY = "NL"`
and a badge in the header. Migration 0007 splits the reference library into a
global spine (what a job *is*) and a country layer (what it costs and what the
law says about it), and this module is the app's side of that seam — the one
place that answers "which country are we in, and which ones could we be in".

WHY A FALLBACK LIST LIVES HERE

The countries table is the master, but the picker has to render before the
database is reached, and `LIBRARY_SOURCE` can be "excel" entirely. So the seed
from 0007 is mirrored here as a literal. The two are checked against each other
by `verify_against_db()` rather than trusted to stay in step by hand: a copy
that nothing compares is a copy that silently rots.

ACTIVE MEANS "HAS DATA", NOT "IS SUPPORTED"

A country is active when reference data has been loaded for it. Everything else
is visible in the picker but disabled, which is deliberate — an empty dropdown
tells a prospect nothing, and a list of greyed-out markets tells them where this
is going. No country is ever silently absent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Country:
    code: str            # ISO 3166-1 alpha-2
    name_en: str
    name_local: str | None
    currency: str        # ISO 4217
    locale: str | None
    eu_member: bool
    active: bool         # reference data loaded
    sort_order: int

    @property
    def label(self) -> str:
        """What the picker shows. Local name where it differs — a Dutch HR lead
        reading 'Nederland' is a smaller thing than it sounds, and free."""
        if self.name_local and self.name_local != self.name_en:
            return f"{self.name_local} ({self.code})"
        return f"{self.name_en} ({self.code})"


# Mirrors the seed in supabase/migrations/0007_multi_country.sql. Keep in step;
# verify_against_db() is what catches you when you don't.
_SEED: tuple[Country, ...] = (
    Country("NL", "Netherlands",    "Nederland",   "EUR", "nl-NL", True,  True,  10),
    Country("BE", "Belgium",        "België",      "EUR", "nl-BE", True,  False, 20),
    Country("DE", "Germany",        "Deutschland", "EUR", "de-DE", True,  False, 30),
    Country("FR", "France",         "France",      "EUR", "fr-FR", True,  False, 40),
    Country("LU", "Luxembourg",     "Luxembourg",  "EUR", "fr-LU", True,  False, 50),
    Country("ES", "Spain",          "España",      "EUR", "es-ES", True,  False, 60),
    Country("PL", "Poland",         "Polska",      "PLN", "pl-PL", True,  False, 70),
    Country("SE", "Sweden",         "Sverige",     "SEK", "sv-SE", True,  False, 80),
    Country("GB", "United Kingdom", None,          "GBP", "en-GB", False, False, 90),
)

DEFAULT_COUNTRY = "NL"


def all_countries() -> list[Country]:
    """Every country the product knows about, live or not, in picker order."""
    return sorted(_SEED, key=lambda c: (c.sort_order, c.code))


def active_countries() -> list[Country]:
    """Only those with reference data loaded. Today: the Netherlands."""
    return [c for c in all_countries() if c.active]


def get(code: str | None) -> Country:
    """Look up a country, falling back to the default rather than raising.

    A bad country code in a URL parameter or a stale session should not take the
    page down — it should land the reader somewhere real and let the picker
    correct it.
    """
    if code:
        wanted = code.strip().upper()
        for c in _SEED:
            if c.code == wanted:
                return c
        logger.warning("Unknown country %r; falling back to %s", code, DEFAULT_COUNTRY)
    return get_default()


def get_default() -> Country:
    for c in _SEED:
        if c.code == DEFAULT_COUNTRY:
            return c
    return _SEED[0]


def is_active(code: str | None) -> bool:
    return get(code).active


def verify_against_db(rows: list[dict]) -> list[str]:
    """Compare the literal above against the countries table.

    Returns a list of human-readable differences — empty when the two agree.
    Called from the Data Quality page rather than at import time, because a
    drifted copy is a thing to report, not a reason to refuse to start.
    """
    problems: list[str] = []
    seeded = {c.code: c for c in _SEED}
    from_db = {str(r.get("code", "")).upper(): r for r in rows if r.get("code")}

    for code in sorted(set(seeded) | set(from_db)):
        if code not in from_db:
            problems.append(f"{code}: in core/countries.py but not in the database")
            continue
        if code not in seeded:
            problems.append(f"{code}: in the database but not in core/countries.py")
            continue
        local, remote = seeded[code], from_db[code]
        if local.currency != str(remote.get("currency", "")).upper():
            problems.append(
                f"{code}: currency {local.currency} here, "
                f"{remote.get('currency')} in the database"
            )
        if local.active != bool(remote.get("active")):
            problems.append(
                f"{code}: active={local.active} here, "
                f"active={remote.get('active')} in the database"
            )
    return problems

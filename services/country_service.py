"""
country_service.py — which market's money is on screen.

Migration 0012 made country a dimension: priced reference rows carry one,
`orgs.default_country` says where a client is, `employees.country` says where a
person is paid. This is the half that reads it.

WHY THIS EXISTS AT ALL

`ui/app.py` had `_euro()` and twenty-three other places that wrote "€" directly.
That is correct for the Netherlands and silently wrong for Poland, Sweden and
Denmark — all of which are in the `countries` table precisely so that nothing
may assume euro. A salary rendered as "€90.000" when it is 90,000 złoty is not a
formatting bug; it is a number that means something else.

WHAT THIS DELIBERATELY DOES NOT DO

It does not convert. A Polish salary shown in euro through an FX rate is a
different claim from the same figure shown in its own market, and one that needs
a rate as of a date, shown rather than hidden. Money is displayed in the currency
it was recorded in, full stop.

It also does not carry locale. Number and date conventions belong to a language,
not to a country — a Belgian client may want French or Dutch — and conflating
the two is how a product ends up unable to offer either. The thousands
separator here follows the existing Dutch convention for every currency, which
is a known simplification recorded in docs/PLAN-country-coverage.md §5 rather
than an oversight.
"""
from __future__ import annotations

from typing import Optional

try:
    from core.config import DEFAULT_COUNTRY, DEFAULT_CURRENCY
except Exception:            # config is importable in every real path; be safe anyway
    DEFAULT_COUNTRY, DEFAULT_CURRENCY = "NL", "EUR"

# Symbols for the currencies in the seeded registry. A currency with no symbol
# here renders as its ISO code, which is unambiguous and never wrong — better
# than guessing a glyph and being subtly misleading about which krone it is.
_SYMBOLS = {
    "EUR": "€",
    "PLN": "zł",
    "SEK": "kr",
    "DKK": "kr",
    "GBP": "£",
    "CHF": "CHF",
    "NOK": "kr",
    "CZK": "Kč",
}

_SS_COUNTRIES = "_country_registry"


def _ss() -> dict:
    import streamlit as st
    return st.session_state


def registry(refresh: bool = False) -> list[dict]:
    """Every country Jobsy knows about, read through the signed-in user.

    Cached per browser session: it changes when an operator opens a market, not
    while somebody is working. Returns [] when there is no session — callers
    fall back to the default rather than failing.
    """
    ss = _ss()
    if not refresh and _SS_COUNTRIES in ss:
        return ss[_SS_COUNTRIES]
    rows: list[dict] = []
    try:
        from services import auth_service
        client = auth_service.db()
        if client is not None:
            resp = (client.table("countries")
                    .select("code, name, currency, is_live")
                    .order("name")
                    .execute())
            rows = resp.data or []
    except Exception:
        rows = []
    ss[_SS_COUNTRIES] = rows
    return rows


def reset() -> None:
    _ss().pop(_SS_COUNTRIES, None)


def live_countries() -> list[dict]:
    """Countries a user may actually choose.

    `EU` is filtered out even if somebody flips its flag: it is a fallback scope
    for reference rows, not a place anyone works, and offering it would let a
    client file a pay report for a country that does not exist.
    """
    return [c for c in registry() if c.get("is_live") and c.get("code") != "EU"]


def active_country() -> str:
    """The country whose money and bands should be on screen.

    The client's home country. NOT the country of any particular employee —
    a multinational's roster spans several, and that distinction is the whole
    reason `employees.country` exists separately.
    """
    try:
        from services import auth_service
        org = auth_service.active_org() or {}
        code = org.get("default_country")
        if code:
            return str(code).strip().upper()
    except Exception:
        pass
    return DEFAULT_COUNTRY


def currency_for(country: Optional[str] = None) -> str:
    code = (country or active_country()).strip().upper()
    for row in registry():
        if row.get("code") == code:
            return str(row.get("currency") or DEFAULT_CURRENCY).upper()
    return DEFAULT_CURRENCY


def symbol_for(country: Optional[str] = None) -> str:
    cur = currency_for(country)
    return _SYMBOLS.get(cur, cur)


def name_for(country: Optional[str] = None) -> str:
    code = (country or active_country()).strip().upper()
    for row in registry():
        if row.get("code") == code:
            return str(row.get("name") or code)
    return code


def money(value, country: Optional[str] = None, decimals: int = 0) -> str:
    """Format an amount in the market's own currency.

    A blank or unparseable value renders as an em dash rather than "€0", because
    zero and unknown are different facts about somebody's pay.
    """
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    # NaN survives float() and would render as "€nan". It arrives from an empty
    # spreadsheet cell via pandas, which is exactly the case this guard is for:
    # a missing salary is missing, not zero and not a word.
    if n != n:
        return "—"
    sym = symbol_for(country)
    formatted = f"{n:,.{decimals}f}".replace(",", ".")
    # A symbol that is a word (zł, kr, Kč) reads better after the number, the
    # way those currencies are actually written; € and £ lead.
    return f"{sym}{formatted}" if sym in ("€", "£") else f"{formatted} {sym}"


def has_reference_data(country: Optional[str] = None) -> bool:
    """Whether priced reference rows exist for this market at all.

    The point is to be able to say "no data for Belgium yet" instead of
    rendering Dutch numbers with a Belgian label on them. Wrong pay data looks
    exactly like right pay data, so its absence has to be visible.

    Falls back to the EU baseline, mirroring app.resolve_country() in 0012.
    Returns True when it cannot tell — an unreachable database is a different
    problem, already reported elsewhere, and this must not add a second scary
    message about it.
    """
    code = (country or active_country()).strip().upper()
    try:
        from services import auth_service
        client = auth_service.db()
        if client is None:
            return True
        for candidate in (code, "EU"):
            resp = (client.table("salary_bands")
                    .select("country")
                    .eq("country", candidate)
                    .limit(1)
                    .execute())
            # Deliberately `resp.data` and not `resp.count`. The question here
            # is "does a single row exist", which the row itself answers; a
            # count is derived from PostgREST's Content-Range header, so it is
            # None whenever anything between here and the database drops that
            # header -- and `(None or 0) > 0` is False, which reads as "no data
            # for the Netherlands" on a screen where 45 bands are loaded. The
            # browser test caught exactly that. Asking for one row is also
            # cheaper than asking for an exact count of all of them.
            if resp.data:
                return True
        return False
    except Exception:
        return True

"""
branding_service.py — what the product calls itself, for whom.

Stage 6 of docs/PLAN-whitelabel-tenancy.md (F-1, F-2). Jobsy is being resold, so
"Jobsy" has to be a default rather than a fact. Every user-visible name, the
logo, the accent colours and the session-code prefix come from here.

RESOLUTION ORDER, and why it is this way

  1. The signed-in user's partner, read from the database.
     A client's HR staff see the reseller's brand, not ours. The partners_read
     policy from 0008 already permits exactly this read.

  2. Instance defaults from Streamlit secrets.
     Before sign-in there is no identity and therefore no partner. Resolving one
     from the URL would mean letting an unauthenticated caller read the partners
     table, which hands anyone a list of who the resellers are. So a DEDICATED
     deployment brands its own sign-in page from its own configuration:

         BRAND_NAME    = "Reward Insight"
         BRAND_LOGO    = "https://.../logo.svg"
         BRAND_PRIMARY = "#0F6E5C"
         BRAND_PREFIX  = "REWARD-"

  3. The built-in default.
     A shared instance with several partners on it shows a neutral front door
     and picks up the right brand the moment somebody signs in.

Never raises. A branding failure must degrade to the default, not to a stack
trace on the sign-in page: the whole point of this module is what people see
before anything else works.
"""
from __future__ import annotations

from typing import Optional

# The People Harmonics palette, matching ui/theme.py. These are the values a
# deployment with no branding configured falls back to.
DEFAULT = {
    "product_name": "Jobsy",
    "code_prefix": "JOBSY-",
    "logo_url": None,
    "primary_color": "#8850EF",
    "accent_color": "#67E8F9",
    "support_email": None,
}

_SS_CACHE = "_brand_cache"


def _ss() -> dict:
    import streamlit as st
    return st.session_state


def _from_secrets() -> dict:
    """Instance-level branding, for a deployment dedicated to one partner."""
    out = {}
    try:
        import streamlit as st
        for key, field in (("BRAND_NAME", "product_name"),
                           ("BRAND_LOGO", "logo_url"),
                           ("BRAND_PRIMARY", "primary_color"),
                           ("BRAND_ACCENT", "accent_color"),
                           ("BRAND_PREFIX", "code_prefix"),
                           ("BRAND_SUPPORT_EMAIL", "support_email")):
            value = st.secrets.get(key)
            if value:
                out[field] = str(value).strip()
    except Exception:
        pass
    return out


def _from_partner() -> dict:
    """The signed-in user's partner. Read through the user's own client, so RLS
    decides what comes back — a partner they have no relationship with returns
    nothing rather than being filtered out here."""
    try:
        from services import auth_service
        client = auth_service.db()
        org = auth_service.active_org()
        if client is None or not org:
            return {}
        resp = (client.table("orgs")
                .select("partners(product_name, code_prefix, logo_url, "
                        "primary_color, accent_color, support_email)")
                .eq("id", org["id"])
                .limit(1)
                .execute())
        rows = resp.data or []
        partner = (rows[0] or {}).get("partners") if rows else None
        if not partner:
            return {}
        return {k: v for k, v in partner.items() if v is not None}
    except Exception:
        return {}


def current(refresh: bool = False) -> dict:
    """The brand in force for this session.

    Cached per browser session because it is read on every rerun and every
    render, and it changes only when the user switches client — which clears the
    cache through reset().
    """
    ss = _ss()
    if not refresh and _SS_CACHE in ss:
        return ss[_SS_CACHE]

    brand = dict(DEFAULT)
    brand.update(_from_secrets())      # a dedicated deployment overrides the default
    brand.update(_from_partner())      # a signed-in user overrides both
    ss[_SS_CACHE] = brand
    return brand


def reset() -> None:
    """Forget the cached brand. Called on sign-in, sign-out and client switch,
    because all three can change whose product this is."""
    _ss().pop(_SS_CACHE, None)


def name() -> str:
    return current().get("product_name") or DEFAULT["product_name"]


def code_prefix() -> str:
    """Prefix for new session codes.

    Validated here as well as in the database: this value is concatenated into a
    code that people read aloud and type back, and a malformed prefix from a
    misconfigured secret would produce codes nobody can dictate. The database
    constraint covers partner rows; this covers BRAND_PREFIX in secrets, which
    no constraint can reach.
    """
    import re
    value = (current().get("code_prefix") or "").strip().upper()
    if re.fullmatch(r"[A-Z][A-Z0-9]{1,9}-", value):
        return value
    return DEFAULT["code_prefix"]


def logo_url() -> Optional[str]:
    url = current().get("logo_url")
    # https only, for the same reason the database constraint says so: a logo is
    # fetched by the browser, and mixed content on a sign-in page is a bad look
    # on the one screen that is entirely about looking trustworthy.
    return url if (url and str(url).startswith("https://")) else None


def colors() -> tuple[str, str]:
    import re
    brand = current()
    primary = brand.get("primary_color") or DEFAULT["primary_color"]
    accent = brand.get("accent_color") or DEFAULT["accent_color"]
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(primary)):
        primary = DEFAULT["primary_color"]
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(accent)):
        accent = DEFAULT["accent_color"]
    return primary, accent


def support_email() -> Optional[str]:
    return current().get("support_email")


def css_overrides() -> str:
    """A CSS block repointing the accent tokens at the partner's colours.

    Only the accents move. The surface ramp stays put, because
    .streamlit/config.toml paints Streamlit's own widget internals from a block
    read once at server start — it cannot vary per request, so a per-partner
    background would put branded panels next to unbranded sliders. Accents on a
    shared ground is the honest limit of theming a shared instance, and it is
    the part that actually reads as somebody's brand.
    """
    primary, accent = colors()
    if (primary, accent) == (DEFAULT["primary_color"], DEFAULT["accent_color"]):
        return ""
    return (
        "<style>:root{"
        f"--ac:{primary};--accent:{primary};--primary:{primary};"
        f"--ac2:{accent};--secondary:{accent};"
        "}"
        f".jobsy-v3-title,h1,h2{{color:inherit}}"
        f"a{{color:{primary}}}"
        "</style>"
    )

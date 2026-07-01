"""
persistence_service.py — database-backed session persistence for Jobsy.

Sessions are identified by a short human-readable code (e.g. JOBSY-X7K2M).
All session data is stored as a single JSONB payload so no schema migrations
are needed for new features.

Setup:
  1. Create the table in your database project.
  2. Add to .streamlit/secrets.toml:
       SUPABASE_URL = "https://your-project.supabase.co"
       SUPABASE_KEY = "your-anon-key"
"""

from __future__ import annotations

import json
import random
import string
from typing import Any, Optional

_client = None
_available: Optional[bool] = None
_last_error: Optional[str] = None


def _set_error(message: str) -> None:
    global _last_error
    _last_error = message


def last_error() -> Optional[str]:
    """Return the last database error, if any."""
    return _last_error


def reset_connection_cache() -> None:
    """Reset cached database client state."""
    global _client, _available, _last_error
    _client = None
    _available = None
    _last_error = None


def _get_secret(name: str) -> Optional[str]:
    """Read a Streamlit secret using uppercase or lowercase key variants."""
    try:
        import streamlit as st
        return st.secrets.get(name) or st.secrets.get(name.lower())
    except Exception as exc:
        _set_error(f"Could not read Streamlit secrets: {exc}")
        return None


def _get_client():
    """Lazy-load the database client. Use last_error() for diagnostics."""
    global _client, _available

    if _available is False:
        return None

    if _client is not None:
        return _client

    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")

    if not url or not key:
        _available = False
        _set_error(
            "Database secrets are missing. Add SUPABASE_URL and SUPABASE_KEY "
            "to Streamlit secrets."
        )
        return None

    try:
        from supabase import create_client
    except Exception as exc:
        _available = False
        _set_error(
            "Database client package is unavailable. Install the 'supabase' "
            f"Python package. Original error: {exc}"
        )
        return None

    try:
        _client = create_client(url, key)
        _available = True
        _set_error("")
        return _client
    except Exception as exc:
        _available = False
        _set_error(f"Could not create database client: {exc}")
        return None


def is_available() -> bool:
    """Return True if the database client is configured and can be created."""
    return _get_client() is not None


def status() -> dict[str, Any]:
    """Return database connection status for UI diagnostics."""
    available = is_available()
    return {
        "available": available,
        "label": "Database connected" if available else "Database unavailable",
        "error": last_error() or "",
    }


def generate_code() -> str:
    """Generate a short human-readable session code like JOBSY-X7K2M."""
    chars = random.choices(string.ascii_uppercase + string.digits, k=5)
    return "JOBSY-" + "".join(chars)


def save_session(code: str, payload: dict, org_label: str = "") -> bool:
    """Upsert a session. Returns True on success, False on failure."""
    client = _get_client()
    if not client:
        return False

    try:
        data = {
            "session_code": code.strip().upper(),
            "org_label": org_label or "",
            "payload": _safe_json(payload),
        }
        client.table("jobsy_sessions").upsert(data).execute()
        _set_error("")
        return True
    except Exception as exc:
        _set_error(f"Could not save session: {exc}")
        return False


def load_session(code: str) -> Optional[dict]:
    """Load a session by code. Returns the saved session or None."""
    client = _get_client()
    if not client:
        return None

    try:
        resp = (
            client.table("jobsy_sessions")
            .select("payload,org_label,created_at")
            .eq("session_code", code.strip().upper())
            .single()
            .execute()
        )

        if resp.data:
            _set_error("")
            return {
                "payload": resp.data.get("payload", {}),
                "org_label": resp.data.get("org_label", ""),
                "created_at": resp.data.get("created_at", ""),
            }

        _set_error("Session code not found.")
        return None
    except Exception as exc:
        _set_error(f"Could not load session: {exc}")
        return None


def _safe_json(obj) -> dict:
    """Convert session state objects to JSON-safe dictionaries/lists."""
    import pandas as pd

    def convert(o):
        if isinstance(o, pd.DataFrame):
            return o.to_dict(orient="records")
        if isinstance(o, pd.Series):
            return o.tolist()
        if hasattr(o, "__dict__"):
            return str(o)
        return o

    raw = json.dumps(obj, default=convert)
    return json.loads(raw)

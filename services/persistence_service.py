"""
persistence_service.py — Supabase-backed session persistence for Jobsy.

Sessions are identified by a short human-readable code (e.g. JOBSY-X7K2M).
All session data is stored as a single JSONB payload so no schema migrations
are needed for new features.

Setup:
  1. Create the table in your Supabase project (SQL below).
  2. Add to .streamlit/secrets.toml:
       SUPABASE_URL = "https://your-project.supabase.co"
       SUPABASE_KEY = "your-anon-key"

SQL to run once in Supabase SQL Editor:
  CREATE TABLE IF NOT EXISTS jobsy_sessions (
      session_code TEXT PRIMARY KEY,
      created_at   TIMESTAMPTZ DEFAULT NOW(),
      updated_at   TIMESTAMPTZ DEFAULT NOW(),
      org_label    TEXT,
      payload      JSONB
  );
  -- Optional: auto-expire sessions after 90 days
  -- (run as a scheduled function or cron)
"""
from __future__ import annotations

import json
import random
import string
from typing import Optional

_client = None
_available = None


def _get_client():
    """Lazy-load the Supabase client. Returns None if not configured."""
    global _client, _available
    if _available is False:
        return None
    if _client is not None:
        return _client
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL") or st.secrets.get("supabase_url")
        key = st.secrets.get("SUPABASE_KEY") or st.secrets.get("supabase_key")
        if not url or not key:
            _available = False
            return None
        from supabase import create_client
        _client   = create_client(url, key)
        _available = True
        return _client
    except Exception:
        _available = False
        return None


def is_available() -> bool:
    """Returns True if Supabase is configured and reachable."""
    return _get_client() is not None


def generate_code() -> str:
    """Generate a short human-readable session code like JOBSY-X7K2M."""
    chars = random.choices(string.ascii_uppercase + string.digits, k=5)
    return "JOBSY-" + "".join(chars)


def save_session(
    code: str,
    payload: dict,
    org_label: str = "",
) -> bool:
    """
    Upsert a session. payload should be JSON-serialisable.
    Returns True on success, False on failure.
    """
    client = _get_client()
    if not client:
        return False
    try:
        # Sanitise payload — remove non-serialisable objects
        data = {
            "session_code": code,
            "org_label":    org_label or "",
            "payload":      _safe_json(payload),
            "updated_at":   "now()",
        }
        client.table("jobsy_sessions").upsert(data).execute()
        return True
    except Exception:
        return False


def load_session(code: str) -> Optional[dict]:
    """
    Load a session by code. Returns the payload dict or None.
    """
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
            return {
                "payload":    resp.data.get("payload", {}),
                "org_label":  resp.data.get("org_label", ""),
                "created_at": resp.data.get("created_at", ""),
            }
    except Exception:
        pass
    return None


def _safe_json(obj) -> dict:
    """Convert session state objects to JSON-safe dict."""
    import pandas as pd

    def convert(o):
        if isinstance(o, pd.DataFrame):
            return o.to_dict(orient="records")
        if isinstance(o, (pd.Series,)):
            return o.tolist()
        if hasattr(o, "__dict__"):
            return str(o)
        return o

    raw = json.dumps(obj, default=convert)
    return json.loads(raw)

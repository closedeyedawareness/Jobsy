"""
persistence_service.py — Supabase-backed session persistence for Jobsy.

Commit 4.1:
  - DatabaseStatus dataclass (backwards-compatible: also behaves like a dict)
  - health_check() with lightweight query against jobsy_sessions
  - Connection latency recording
  - Original exceptions retained for diagnostics
  - Public API unchanged: is_available(), save_session(), load_session()

Setup:
  1. requirements.txt must include:  supabase>=2.4.0
  2. .streamlit/secrets.toml (or Streamlit Cloud → Settings → Secrets):
       SUPABASE_URL = "https://your-project.supabase.co"
       SUPABASE_KEY = "your-anon-key"
  3. Run SUPABASE_SETUP.sql once in the Supabase SQL Editor.
"""
from __future__ import annotations

import json
import random
import string
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

_client = None
_status_cache: Optional["DatabaseStatus"] = None


# ── Status model ──────────────────────────────────────────────────────────
@dataclass
class DatabaseStatus:
    """Connection status snapshot. Dict-compatible for backwards compatibility."""
    available: bool = False
    configured: bool = False           # secrets present
    package_installed: bool = False    # supabase importable
    connected: bool = False            # client created successfully
    healthy: bool = False              # health_check query succeeded
    latency_ms: Optional[float] = None
    last_error: Optional[str] = None
    last_error_type: Optional[str] = None
    checked_at: Optional[float] = None

    # ── dict-compat layer so existing callers using status()["available"] keep working
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return asdict(self).keys()

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def reason(self) -> str:
        """Human-readable explanation of the current state."""
        if self.healthy:
            return "Connected and healthy"
        if not self.package_installed:
            return "supabase package not installed — add `supabase>=2.4.0` to requirements.txt"
        if not self.configured:
            return "SUPABASE_URL / SUPABASE_KEY not found in Streamlit secrets"
        if not self.connected:
            return f"Client creation failed: {self.last_error or 'unknown error'}"
        if not self.healthy and self.last_error:
            return f"Health check failed: {self.last_error}"
        return "Not connected"


# ── Internal helpers ──────────────────────────────────────────────────────
def _read_secrets() -> tuple[Optional[str], Optional[str]]:
    """Read Supabase credentials from Streamlit secrets, tolerating both flat and nested layouts."""
    try:
        import streamlit as st
        # Flat layout
        url = st.secrets.get("SUPABASE_URL") or st.secrets.get("supabase_url")
        key = st.secrets.get("SUPABASE_KEY") or st.secrets.get("supabase_key")
        # Nested layout: [supabase] url = ... / key = ...
        if (not url or not key) and "supabase" in st.secrets:
            section = st.secrets["supabase"]
            url = url or section.get("url") or section.get("SUPABASE_URL")
            key = key or section.get("key") or section.get("SUPABASE_KEY")
        # Nested layout: [connections.supabase]
        if (not url or not key) and "connections" in st.secrets:
            conn = st.secrets["connections"]
            if "supabase" in conn:
                url = url or conn["supabase"].get("url")
                key = key or conn["supabase"].get("key")
        return (str(url).strip() if url else None,
                str(key).strip() if key else None)
    except Exception:
        return None, None


def _build_status(force: bool = False) -> DatabaseStatus:
    """Build (and cache) a full status snapshot, creating the client if possible."""
    global _client, _status_cache
    if _status_cache is not None and not force:
        return _status_cache

    status = DatabaseStatus(checked_at=time.time())

    # 1. Package check
    try:
        from supabase import create_client  # noqa: F401
        status.package_installed = True
    except Exception as exc:
        status.last_error = str(exc)
        status.last_error_type = type(exc).__name__
        _status_cache = status
        return status

    # 2. Secrets check
    url, key = _read_secrets()
    if not url or not key:
        status.last_error = "SUPABASE_URL and/or SUPABASE_KEY missing from st.secrets"
        status.last_error_type = "ConfigurationError"
        _status_cache = status
        return status
    status.configured = True

    # 3. Client creation
    try:
        from supabase import create_client
        _client = create_client(url, key)
        status.connected = True
    except Exception as exc:
        status.last_error = str(exc)
        status.last_error_type = type(exc).__name__
        _client = None
        _status_cache = status
        return status

    status.available = True
    _status_cache = status
    return status


def _get_client():
    status = _build_status()
    return _client if status.connected else None


# ── Public API ────────────────────────────────────────────────────────────
def status(force_refresh: bool = False) -> DatabaseStatus:
    """Return the current DatabaseStatus (cached unless force_refresh=True)."""
    return _build_status(force=force_refresh)


def health_check() -> DatabaseStatus:
    """
    Perform a lightweight query against jobsy_sessions to verify end-to-end
    connectivity. Records latency in ms. Returns the updated DatabaseStatus.
    """
    st_obj = _build_status(force=True)
    client = _client
    if not client:
        return st_obj
    try:
        t0 = time.perf_counter()
        # HEAD-style count query — cheapest possible round trip
        client.table("jobsy_sessions").select("session_code", count="exact").limit(1).execute()
        st_obj.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        st_obj.healthy = True
        st_obj.last_error = None
        st_obj.last_error_type = None
    except Exception as exc:
        st_obj.healthy = False
        st_obj.last_error = str(exc)
        st_obj.last_error_type = type(exc).__name__
    st_obj.checked_at = time.time()
    global _status_cache
    _status_cache = st_obj
    return st_obj


def is_available() -> bool:
    """True if Supabase is configured, importable, and the client was created."""
    return _build_status().available


def generate_code() -> str:
    """Generate a short human-readable session code like JOBSY-X7K2M."""
    chars = random.choices(string.ascii_uppercase + string.digits, k=5)
    return "JOBSY-" + "".join(chars)


def save_session(code: str, payload: dict, org_label: str = "") -> bool:
    """Upsert a session. Returns True on success. Retains error in status on failure."""
    client = _get_client()
    if not client:
        return False
    try:
        data = {
            "session_code": code,
            "org_label":    org_label or "",
            "payload":      _safe_json(payload),
        }
        client.table("jobsy_sessions").upsert(data).execute()
        return True
    except Exception as exc:
        global _status_cache
        if _status_cache:
            _status_cache.last_error = str(exc)
            _status_cache.last_error_type = type(exc).__name__
        return False


def load_session(code: str) -> Optional[dict]:
    """Load a session by code. Returns {'payload','org_label','created_at'} or None."""
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
    except Exception as exc:
        global _status_cache
        if _status_cache:
            _status_cache.last_error = str(exc)
            _status_cache.last_error_type = type(exc).__name__
    return None


def _safe_json(obj) -> dict:
    """Convert session state objects to a JSON-safe dict."""
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

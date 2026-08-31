"""
persistence_service.py — saving and restoring a Jobsy working session.

Stage 2 of docs/PLAN-whitelabel-tenancy.md rewrote this module. What changed and
why, because the diff touches almost every line:

1. NO MORE MODULE-LEVEL CLIENT.

   This file used to hold `_client` as a module global. Streamlit serves every
   browser session from one Python process, so once that client carries a user's
   token it is shared state — whoever signed in most recently supplies the
   identity for everyone, and two clients' rosters meet in one connection. The
   app would look perfectly healthy while doing it.

   The client now comes from auth_service.db(), which keeps it in
   st.session_state, keyed per browser session. There is no global here. Do not
   add one.

2. NO MORE SECRET KEY.

   The old docstring argued the secret key was safe because Streamlit is
   server-rendered. That is true of EXPOSURE — the key never reaches a browser —
   and irrelevant to isolation: the secret key is defined as the thing that
   bypasses row-level security, so it reaches every client's data no matter what
   migration 0008 says. Traffic now runs as the signed-in user, and 0008's
   policies are what keep one client out of another's rows.

3. A SESSION BELONGS TO A CLIENT.

   save_session() takes an org_id. jobsy_sessions.org_id is NOT NULL, so there
   is no way to write a roster that belongs to nobody.

4. THE CODE IS NO LONGER THE ACCESS CONTROL.

   It used to be: hold the code, load the session. Now the code addresses a row
   and RLS decides whether you may have it, so a leaked code out of context is
   worth nothing. generate_code() is still hardened (B-5) because defence in
   depth is cheap, but it is no longer the fence.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, asdict
from typing import Any, Optional

# Unambiguous alphabet: no O/0, no I/1/L. These codes get read down a phone and
# typed by hand, and a code that cannot be transcribed is a support ticket.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 10
_CODE_PREFIX = "JOBSY-"   # Fallback only. The live value comes from branding_service.

# Column names that hold a person's name, across the languages this app is used
# in. Matched case-insensitively against the keys of the uploaded rows.
_NAME_KEYS = {
    "name", "naam", "fullname", "full name", "full_name", "employee",
    "employee name", "employee_name", "medewerker", "werknemer",
    "first name", "last name", "voornaam", "achternaam", "surname",
}


@dataclass
class DatabaseStatus:
    """Connection status snapshot. Dict-compatible for backwards compatibility."""
    available: bool = False
    configured: bool = False
    package_installed: bool = False
    connected: bool = False
    healthy: bool = False
    latency_ms: Optional[float] = None
    last_error: Optional[str] = None
    last_error_type: Optional[str] = None
    checked_at: Optional[float] = None

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
        if self.healthy:
            return "Connected and healthy"
        if not self.package_installed:
            return "supabase package not installed — add `supabase>=2.4.0` to requirements.txt"
        if not self.configured:
            return "Not signed in"
        if not self.connected:
            return f"No database session: {self.last_error or 'unknown error'}"
        if not self.healthy and self.last_error:
            return f"Health check failed: {self.last_error}"
        return "Not connected"


def _client():
    """The signed-in user's client for THIS browser session, or None.

    Every database call in this module goes through here. It is a function
    rather than a global on purpose — see point 1 in the module docstring.
    """
    try:
        from services import auth_service
    except Exception:
        return None
    return auth_service.db()


def _active_org_id() -> Optional[str]:
    try:
        from services import auth_service
    except Exception:
        return None
    return auth_service.active_org_id()


# ── Public API ────────────────────────────────────────────────────────────
def status(force_refresh: bool = False) -> DatabaseStatus:
    """Current state. Cheap: it asks the session, not the network.

    `force_refresh` is accepted and ignored — there is no cache to invalidate
    now that the client lives in session state. Kept so existing callers in
    ui/app.py do not have to change.
    """
    st_obj = DatabaseStatus(checked_at=time.time())
    try:
        import supabase  # noqa: F401
        st_obj.package_installed = True
    except Exception as exc:
        st_obj.last_error = str(exc)
        st_obj.last_error_type = type(exc).__name__
        return st_obj

    client = _client()
    st_obj.configured = client is not None
    st_obj.connected = client is not None
    st_obj.available = client is not None
    return st_obj


def health_check() -> DatabaseStatus:
    """One real round trip, so "connected" means something.

    Counts rows the CURRENT USER can see. Zero is a healthy answer — a new
    client has no sessions yet — so this asserts reachability, not content.
    """
    st_obj = status()
    client = _client()
    if not client:
        return st_obj
    try:
        t0 = time.perf_counter()
        client.table("jobsy_sessions").select("session_code", count="exact").limit(1).execute()
        st_obj.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        st_obj.healthy = True
    except Exception as exc:
        st_obj.healthy = False
        st_obj.last_error = str(exc)
        st_obj.last_error_type = type(exc).__name__
    return st_obj


def is_available() -> bool:
    """True when there is a signed-in session to save through."""
    return _client() is not None


def generate_code() -> str:
    """A session code that cannot be guessed or enumerated.

    Was `random.choices` over 5 characters — the Mersenne Twister, which is not
    a cryptographic generator, across 36^5 ≈ 60 million possibilities with no
    rate limit. That was the entire protection on a client's roster.

    Now `secrets` over 31^10 ≈ 8.2e14. The real fix is that the code stopped
    being the access control at all (see the module docstring); this is the
    belt to that pair of braces.
    """
    body = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))

    # F-2: a partner reselling this does not hand their client codes that say
    # JOBSY. The prefix is theirs; the body and its entropy are not negotiable.
    try:
        from services import branding_service
        prefix = branding_service.code_prefix()
    except Exception:
        prefix = _CODE_PREFIX
    return prefix + body


def _pseudonymise_names(payload: dict, salt: str, name_col: Optional[str] = None) -> dict:
    """Replace people's names with stable tokens before the payload is stored.

    C-4. The analysis does not need names — pay equity works on id, function,
    level, gender and salary — but the ANALYST does: ui/app.py detects a name
    column and shows it, and somebody looking at an outlier needs to know who it
    is. So names are not stripped at upload; they are stripped on the way to the
    database, which is the copy that persists, sits in backups, and is what a
    breach would reach. The browser session keeps the real thing for as long as
    the work is happening.

    Tokens are stable WITHIN a session, so the same person reads the same on
    every row and a table still makes sense. They are salted with the session
    code, so the same person in two different sessions does not produce the same
    token — otherwise the tokens themselves would become a way to correlate one
    client's staff list against another's.

    This is one-way. There is no un-pseudonymise, and no key kept anywhere that
    would allow one; a reversible mapping stored beside the data would simply be
    the names again, wearing a hat.
    """
    def token(value: str) -> str:
        digest = hashlib.blake2b(str(value).strip().lower().encode("utf-8"),
                                 key=salt.encode("utf-8")[:64], digest_size=4)
        return "EMP-" + digest.hexdigest().upper()

    def is_name_key(key: str) -> bool:
        k = str(key).strip().lower()
        return k in _NAME_KEYS or (name_col is not None and k == str(name_col).strip().lower())

    def walk(node):
        if isinstance(node, dict):
            return {k: (token(v) if (is_name_key(k) and isinstance(v, str) and v.strip())
                        else walk(v))
                    for k, v in node.items()}
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(payload)


def save_session(code: str, payload: dict, org_label: str = "",
                 org_id: Optional[str] = None) -> bool:
    """Upsert a session for a client. True on success.

    org_id defaults to the client the user is currently working on. It is never
    optional in the database: jobsy_sessions.org_id is NOT NULL, so a roster
    that belongs to nobody cannot be written. If the caller passes an org the
    user has no membership for, 0008's `with check` rejects it — the UI is not
    trusted to have offered only legitimate options.
    """
    client = _client()
    if not client:
        return False
    org = org_id or _active_org_id()
    if not org:
        return False

    body = _safe_json(payload)

    # Per-client, and off unless somebody turned it on — see 0010. Read from the
    # org record rather than a local setting, so it is a property of the client
    # and travels with them rather than with whoever happens to be signed in.
    try:
        from services import auth_service
        active = auth_service.active_org() or {}
    except Exception:
        active = {}
    if active.get("pseudonymise_names"):
        body = _pseudonymise_names(body, salt=code,
                                   name_col=body.get("upload_name_col"))

    try:
        client.table("jobsy_sessions").upsert({
            "session_code": code,
            "org_id":       org,
            "org_label":    org_label or "",
            "payload":      body,
        }, on_conflict="session_code").execute()
        return True
    except Exception:
        return False


def load_session(code: str) -> Optional[dict]:
    """Load a session by code, if the signed-in user may have it.

    No org filter is applied here on purpose. The policy does it, so a mistake
    in this function cannot widen access, and the isolation test in
    supabase/tests/0008_rls_isolation_test.sql is what proves that. A user
    holding a code for another client's session gets nothing back — which is
    the behaviour B-5 and B-6 were about.
    """
    client = _client()
    if not client:
        return None
    try:
        resp = (client.table("jobsy_sessions")
                .select("payload,org_label,org_id,created_at")
                .eq("session_code", (code or "").strip().upper())
                .limit(1)
                .execute())
        rows = resp.data or []
        if rows:
            row = rows[0]
            return {
                "payload":    row.get("payload", {}),
                "org_label":  row.get("org_label", ""),
                "org_id":     row.get("org_id"),
                "created_at": row.get("created_at", ""),
            }
    except Exception:
        return None
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

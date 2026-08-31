"""
auth_service.py — who is using Jobsy, and what that gets them.

Stage 2 of docs/PLAN-whitelabel-tenancy.md. Replaces the shared password in
ui/app.py with named accounts, and replaces the secret-key database connection
with one that carries the signed-in user's token — which is what makes the RLS
policies in migration 0008 mean anything. Neither half works alone.

THIS IS A B2B PRODUCT. THERE IS NO SIGN-UP.

Accounts are created by an operator through tools/manage_users.py, against a
list of addresses the client has asked for. Billing is invoiced, not
subscribed. So this module deliberately has no register(), no OAuth provider,
no "continue with Google", no password self-service that could create an
account, and no code path anywhere that turns an unknown email into a user.
Adding one would not be a feature; it would be the hole.

Two settings in the Supabase dashboard back this up, and both should be checked
before go-live — the code cannot enforce either:

  Authentication -> Providers   : email only, every OAuth provider disabled
  Authentication -> Sign-Ups    : "Allow new users to sign up" OFF

With sign-ups off, the anon key cannot mint a user even if someone calls the
endpoint directly with it.

WHY THE CLIENT IS PER SESSION AND NEVER A MODULE GLOBAL

persistence_service.py held its client in a module-level global. Streamlit
serves every browser session from ONE Python process, so a global holding a
user's token is shared state: whoever signed in most recently supplies the
identity for everybody, and two clients' data meets in one connection. That is
the exact failure this project exists to prevent, and it is invisible when it
happens — the app works perfectly, for the wrong tenant.

So every client here is built inside a session and stored in st.session_state,
which Streamlit keys per browser session. There is no module-level client in
this file, and there must never be one. Search for `global ` before adding
anything: the answer is no.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

# How long a session survives. Both are enforced on every rerun, because
# Streamlit reruns the script constantly and that is the natural checkpoint.
IDLE_TIMEOUT_SEC = 60 * 60          # an hour with no interaction
ABSOLUTE_TIMEOUT_SEC = 60 * 60 * 12  # half a day regardless of activity

_SS_CLIENT = "_auth_client"      # the per-session Supabase client
_SS_USER = "_auth_user"          # {id, email}
_SS_ORGS = "_auth_orgs"          # [{id, name, slug, role, partner_name}]
_SS_ACTIVE = "_auth_active_org"  # the org id currently being worked on
_SS_LAST_SEEN = "_auth_last_seen"
_SS_SIGNED_IN_AT = "_auth_signed_in_at"
_SS_MUST_CHANGE = "_auth_must_change_password"


@dataclass
class AuthStatus:
    """Why sign-in is or is not possible. Mirrors persistence_service's
    DatabaseStatus so the sidebar can report both the same way."""
    configured: bool = False
    package_installed: bool = False
    signed_in: bool = False
    email: Optional[str] = None
    org_count: int = 0
    last_error: Optional[str] = None

    @property
    def reason(self) -> str:
        if self.signed_in:
            return f"Signed in as {self.email}"
        if not self.package_installed:
            return "supabase package not installed — add `supabase>=2.4.0` to requirements.txt"
        if not self.configured:
            return ("SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY not found in Streamlit secrets. "
                    "The PUBLISHABLE key, not the secret one — see the module docstring.")
        return self.last_error or "Not signed in"


# ── Secrets ───────────────────────────────────────────────────────────────
def _read_secrets() -> tuple[Optional[str], Optional[str]]:
    """URL and PUBLISHABLE key for user-facing traffic.

    The secret key is deliberately not read here and must never be. It bypasses
    RLS, so a session holding it can reach every client's data no matter what
    0008 says. It has exactly one legitimate home left: tools/manage_users.py
    and the importer, neither of which serves a browser request.
    """
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL") or st.secrets.get("supabase_url")
        key = (st.secrets.get("SUPABASE_PUBLISHABLE_KEY")
               or st.secrets.get("supabase_publishable_key"))
        if (not url or not key) and "supabase" in st.secrets:
            section = st.secrets["supabase"]
            url = url or section.get("url") or section.get("SUPABASE_URL")
            key = key or section.get("publishable_key") or section.get("SUPABASE_PUBLISHABLE_KEY")
        return (str(url).strip() if url else None,
                str(key).strip() if key else None)
    except Exception:
        return None, None


def _looks_like_secret_key(key: str) -> bool:
    """A secret key pasted where the publishable one belongs is a silent
    catastrophe: everything works, and RLS is off for every user. Cheap to
    catch, so catch it."""
    return key.startswith("sb_secret_") or key.startswith("service_role")


def status() -> AuthStatus:
    st_status = AuthStatus()
    try:
        import supabase  # noqa: F401
        st_status.package_installed = True
    except Exception as exc:
        st_status.last_error = str(exc)
        return st_status

    url, key = _read_secrets()
    st_status.configured = bool(url and key)
    if key and _looks_like_secret_key(key):
        st_status.configured = False
        st_status.last_error = (
            "SUPABASE_PUBLISHABLE_KEY holds a SECRET key. That key bypasses row-level "
            "security, so every signed-in user would reach every client's data. "
            "Replace it with the publishable key."
        )
        return st_status

    user = current_user()
    if user:
        st_status.signed_in = True
        st_status.email = user.get("email")
        st_status.org_count = len(accessible_orgs())
    return st_status


# ── Session plumbing ──────────────────────────────────────────────────────
def _ss() -> dict:
    import streamlit as st
    return st.session_state


def _new_client():
    """A fresh Supabase client. Not cached anywhere outside session state."""
    from supabase import create_client
    url, key = _read_secrets()
    if not url or not key or _looks_like_secret_key(key):
        return None
    return create_client(url, key)


def _expired() -> Optional[str]:
    """Why the session should end, or None. Checked on every rerun."""
    ss = _ss()
    now = time.time()
    started = ss.get(_SS_SIGNED_IN_AT)
    seen = ss.get(_SS_LAST_SEEN)
    if started and now - started > ABSOLUTE_TIMEOUT_SEC:
        return "Signed out — sessions end after 12 hours."
    if seen and now - seen > IDLE_TIMEOUT_SEC:
        return "Signed out after an hour of inactivity."
    return None


def touch() -> Optional[str]:
    """Record activity and enforce expiry. Returns a message if the session was
    ended, so the caller can show it on the sign-in screen."""
    if not _ss().get(_SS_USER):
        return None
    why = _expired()
    if why:
        sign_out()
        return why
    _ss()[_SS_LAST_SEEN] = time.time()
    return None


# ── The public surface ────────────────────────────────────────────────────
def sign_in(email: str, password: str) -> tuple[bool, str]:
    """Sign in an existing account. Cannot create one — see the module docstring.

    The failure message is deliberately identical for a wrong password and an
    address that has no account. Distinguishing them turns the sign-in form into
    a way to ask "does this person work here", which for a client's HR system is
    a question worth not answering.
    """
    email = (email or "").strip()
    if not email or not password:
        return False, "Enter your email address and password."

    client = _new_client()
    if client is None:
        return False, status().reason

    try:
        result = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        return False, "That email address and password do not match an account."

    session = getattr(result, "session", None)
    user = getattr(result, "user", None)
    if not session or not user:
        return False, "That email address and password do not match an account."

    ss = _ss()
    ss[_SS_CLIENT] = client
    ss[_SS_USER] = {"id": str(user.id), "email": user.email}
    ss[_SS_SIGNED_IN_AT] = time.time()
    ss[_SS_LAST_SEEN] = time.time()
    ss.pop(_SS_ORGS, None)
    ss.pop(_SS_ACTIVE, None)

    orgs = accessible_orgs(refresh=True)
    if not orgs:
        # A real account with no membership. Signing them into an empty app
        # would look like a bug; saying so is honest and points at the fix.
        sign_out()
        return False, ("This account has no client assigned to it yet. "
                       "Ask your administrator to grant access.")
    ss[_SS_ACTIVE] = orgs[0]["id"]

    # Set by tools/manage_users.py when it creates the account with a temporary
    # password. The password was handed over out of band, so it has been spoken
    # aloud or typed into a chat window at least once; it should not stay valid.
    meta = getattr(user, "user_metadata", None) or {}
    ss[_SS_MUST_CHANGE] = bool(meta.get("must_change_password"))

    # Signing in may change whose product this is.
    try:
        from services import branding_service
        branding_service.reset()
    except Exception:
        pass

    log("auth.sign_in", subject=user.email)
    return True, f"Signed in as {user.email}"


def must_change_password() -> bool:
    """True while the account is still on the password an operator issued."""
    return bool(_ss().get(_SS_MUST_CHANGE))


def change_password(new_password: str, confirm: str) -> tuple[bool, str]:
    """Set a new password and clear the rotation flag.

    The length floor is deliberately the only rule. Composition requirements
    (an uppercase, a digit, a symbol) measurably push people toward
    Password1! and its cousins; length is what actually costs an attacker.
    """
    if new_password != confirm:
        return False, "The two passwords do not match."
    if len(new_password or "") < 12:
        return False, "Use at least 12 characters. Length beats punctuation."

    client = db()
    if client is None:
        return False, "Your session has expired. Sign in again."
    try:
        client.auth.update_user({
            "password": new_password,
            "data": {"must_change_password": False},
        })
    except Exception as exc:
        # Supabase rejects a password identical to the current one, among other
        # things; passing its reason through is more use than a generic failure.
        return False, f"Could not change the password: {exc}"

    _ss()[_SS_MUST_CHANGE] = False
    log("auth.password_changed")
    return True, "Password changed."


def can_edit() -> bool:
    """May this user change client data, or only read it?

    A `viewer` reads. The database enforces this too — migration 0009 splits
    read from write on jobsy_sessions and employees — and that is the boundary
    that actually holds. This function exists so the interface does not offer
    buttons that will fail, not to be the control.
    """
    org = active_org()
    return bool(org) and org["role"] in (
        "partner_admin", "partner_analyst", "client_admin", "analyst")


def log(action: str, subject: Optional[str] = None,
        detail: Optional[dict] = None, org_id: Optional[str] = None) -> None:
    """Record something no database trigger can see.

    Writes to client data log themselves through triggers (0009). A SELECT fires
    nothing, so opening and exporting a roster are recorded here or not at all —
    which is the honest limit of D-1 and worth knowing when reading the trail.

    Never raises. A failure to log must not take the app down, but it also must
    not pass unnoticed, so it goes to the console rather than being swallowed.
    """
    client = db()
    if client is None:
        return
    try:
        client.rpc("log_activity", {
            "p_action": action,
            "p_org": org_id or active_org_id(),
            "p_subject": subject,
            "p_detail": detail or {},
        }).execute()
    except Exception as exc:
        print(f"[audit] failed to record {action!r}: {exc}")


def sign_out() -> None:
    """End the session and drop the client with it. The client holds the access
    token, so leaving it behind would leave a usable connection in memory."""
    ss = _ss()
    client = ss.get(_SS_CLIENT)
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass  # the local session is going regardless
    for k in (_SS_CLIENT, _SS_USER, _SS_ORGS, _SS_ACTIVE, _SS_LAST_SEEN,
              _SS_SIGNED_IN_AT, _SS_MUST_CHANGE):
        ss.pop(k, None)
    try:
        from services import branding_service
        branding_service.reset()
    except Exception:
        pass


def current_user() -> Optional[dict]:
    return _ss().get(_SS_USER)


def db():
    """The database client for THIS browser session, or None.

    Every query in the app should go through this. It carries the signed-in
    user's token, so 0008's policies apply to it — which is the entire point.
    Anything that reaches the database another way is outside the fence.
    """
    return _ss().get(_SS_CLIENT)


def accessible_orgs(refresh: bool = False) -> list[dict]:
    """Clients this user may work on, newest membership rules applied.

    Read through the user's own client, so RLS decides what comes back rather
    than this function doing its own filtering. If the policies are wrong, this
    returns the wrong list and the isolation test catches it — better than a
    Python-side filter that would quietly paper over a broken policy.
    """
    ss = _ss()
    if not refresh and _SS_ORGS in ss:
        return ss[_SS_ORGS]
    client = db()
    if client is None:
        return []
    try:
        # .eq("user_id", ...) is NOT redundant with RLS, and leaving it out was a
        # bug that only browser testing caught. memberships_read (0009)
        # deliberately lets an ORG ADMIN read other people's membership rows --
        # they have to, to administer their client. So an unfiltered select
        # returns colleagues' rows too, and this function labelled a client with
        # somebody ELSE'S role: a partner_admin was shown "client admin" for one
        # of their own clients, because a client_admin's row came back first.
        #
        # No data leaked -- the database is still the enforcement point, and role
        # here only decides which buttons are offered -- but "what am I on this
        # client" has to be answered from THIS user's row, so it is asked for
        # rather than inferred from whatever RLS happens to permit.
        resp = (client.table("memberships")
                .select("role, org_id, partner_id, orgs(id, name, slug, pseudonymise_names, retention_days), partners(id, name)")
                .eq("user_id", (current_user() or {}).get("id"))
                .execute())
    except Exception:
        return []

    orgs: list[dict] = []
    seen: set[str] = set()
    for row in (resp.data or []):
        if row.get("org_id") and row.get("orgs"):
            o = row["orgs"]
            if o["id"] not in seen:
                seen.add(o["id"])
                orgs.append({"id": o["id"], "name": o["name"], "slug": o["slug"],
                             "role": row["role"], "partner_name": None,
                             "pseudonymise_names": o.get("pseudonymise_names", False),
                             "retention_days": o.get("retention_days")})
        elif row.get("partner_id"):
            # Partner-scoped membership: one row, many clients. The orgs it
            # reaches are whatever RLS lets us read for that partner.
            try:
                sub = (client.table("orgs")
                       .select("id, name, slug, pseudonymise_names, retention_days")
                       .eq("partner_id", row["partner_id"])
                       .execute())
            except Exception:
                continue
            pname = (row.get("partners") or {}).get("name")
            for o in (sub.data or []):
                if o["id"] not in seen:
                    seen.add(o["id"])
                    orgs.append({"id": o["id"], "name": o["name"], "slug": o["slug"],
                                 "role": row["role"], "partner_name": pname,
                                 "pseudonymise_names": o.get("pseudonymise_names", False),
                                 "retention_days": o.get("retention_days")})

    orgs.sort(key=lambda o: (o["name"] or "").lower())
    ss[_SS_ORGS] = orgs
    return orgs


def active_org() -> Optional[dict]:
    """The client currently being worked on."""
    ss = _ss()
    org_id = ss.get(_SS_ACTIVE)
    for o in accessible_orgs():
        if o["id"] == org_id:
            return o
    return None


def set_active_org(org_id: str) -> bool:
    """Switch client. Only to one the user actually holds — a UI that offers a
    list is not an access control, so this checks rather than trusts."""
    if any(o["id"] == org_id for o in accessible_orgs()):
        _ss()[_SS_ACTIVE] = org_id
        # Two clients can belong to different partners, so the brand moves too.
        try:
            from services import branding_service
            branding_service.reset()
        except Exception:
            pass
        return True
    return False


def active_org_id() -> Optional[str]:
    org = active_org()
    return org["id"] if org else None


def is_admin() -> bool:
    org = active_org()
    return bool(org) and org["role"] in ("partner_admin", "client_admin")

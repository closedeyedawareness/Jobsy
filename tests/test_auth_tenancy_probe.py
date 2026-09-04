"""
Adversarial probe of auth_service.py, persistence_service.py and
branding_service.py — the tenancy fence itself, not the pages built on it.

Streamlit gives every browser session its own `st.session_state`, which is
where this app is told the client boundary must live (see the module
docstrings of auth_service.py and persistence_service.py). That only holds if
every place identity-shaped or client-shaped data can end up is actually
inside that fence, and is actually torn down when identity changes. This file
goes looking for a corner that is not.

`st.session_state` behaves like a plain dict outside a real `streamlit run`
(with a harmless "missing ScriptRunContext" warning on stderr), so it is used
directly rather than faked.
"""
from __future__ import annotations

import sys
import pathlib
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from services import auth_service, persistence_service, branding_service  # noqa: E402


@pytest.fixture(autouse=True)
def clean_session_state():
    """Every test starts and ends with an empty session — otherwise a leak one
    test proves would be masked by state left behind by another."""
    st.session_state.clear()
    yield
    st.session_state.clear()


class _FakeAuthClient:
    """Just enough of the supabase client surface for auth_service.sign_out()
    and sign_in() to run without a network."""

    def __init__(self):
        self.auth = SimpleNamespace(sign_out=lambda: None)


def _sign_in_user(email="alice@clienta.example", org_id="org-A", role="client_admin"):
    """Populate session_state the way a successful auth_service.sign_in() would,
    without going over the network — mirrors exactly the keys sign_in() sets."""
    st.session_state[auth_service._SS_CLIENT] = _FakeAuthClient()
    st.session_state[auth_service._SS_USER] = {"id": "user-1", "email": email}
    st.session_state[auth_service._SS_ORGS] = [
        {"id": org_id, "name": "Client A", "slug": "clienta", "role": role,
         "partner_name": None, "pseudonymise_names": False,
         "retention_days": None, "default_country": "NL"}
    ]
    st.session_state[auth_service._SS_ACTIVE] = org_id
    st.session_state[auth_service._SS_SIGNED_IN_AT] = 1000.0
    st.session_state[auth_service._SS_LAST_SEEN] = 1000.0
    st.session_state[auth_service._SS_MUST_CHANGE] = False


# ─────────────────────────────────────────────────────────────────────────
# FINDING 1 (HIGH): sign_out() clears identity but not the workspace that was
# built under that identity, so it survives into whoever's session comes next.
# ─────────────────────────────────────────────────────────────────────────
def test_sign_out_wipes_the_previous_users_roster_from_session_state():
    """A shared machine — a kiosk, a shared workstation, one browser left open
    between two people at the same HR outsourcing desk — is exactly the
    scenario a 12-hour absolute timeout and an hour idle timeout in this same
    file are for. Whoever uses the tab next must not inherit what the last
    person was looking at.

    sign_out() (auth_service.py) pops exactly seven session-state keys: the
    client, the user, the org list, the active org, the two timers and the
    must-change flag. Nothing else. But `_capture_session()` /
    `_restore_session()` in ui/app.py, and the 9-box and skills-assessment
    pages, all keep the actual client data — names, salaries, gender, a
    session code that addresses a specific client's row — directly in
    st.session_state under keys sign_out() never touches: upload_df,
    last_results, last_summary, session_code, skill_assessments,
    ninebox_ratings, org_label.

    Concretely: Alice, signed into Client A, uploads a roster (names and
    salaries land in st.session_state["upload_df"]) and signs out. Bob signs
    in next, on the SAME browser tab. Before Bob clicks anything, Client A's
    roster is still sitting in the session he has just inherited.
    """
    _sign_in_user()

    # Client A's actual roster, the way the app holds it while working.
    roster = [
        {"employee_id": "E-1", "name": "Anna de Vries", "salary": 61000, "gender": "F"},
        {"employee_id": "E-2", "name": "Bram Jansen", "salary": 67000, "gender": "M"},
    ]
    st.session_state["upload_df"] = roster
    st.session_state["last_results"] = [{"name": "Anna de Vries", "matched": "Data Analyst"}]
    st.session_state["last_summary"] = {"n": 2}
    st.session_state["session_code"] = "JOBSY-ABCDEFGHJK"
    st.session_state["org_label"] = "Client A"
    st.session_state["skill_assessments"] = {"Anna de Vries": {"communication": 3}}
    st.session_state["ninebox_ratings"] = {"Anna de Vries": (2, 3)}

    auth_service.sign_out()

    assert auth_service.current_user() is None  # the auth half does clear

    leaked = {k: st.session_state[k] for k in
              ("upload_df", "last_results", "last_summary", "session_code",
               "org_label", "skill_assessments", "ninebox_ratings")
              if k in st.session_state}
    assert not leaked, (
        "sign_out() left a previous user's client data in st.session_state: "
        f"{sorted(leaked)}. On a browser tab reused by a second person, this "
        "roster (names, salaries, gender) is visible to them before they do "
        "anything — services/auth_service.py sign_out() must clear it, or "
        "ui/app.py must, and currently neither does."
    )


def test_sign_in_does_not_scrub_a_predecessors_leftover_workspace():
    """The companion path: even if nobody expects sign_out() to be a full
    wipe, sign_in() is the one place guaranteed to run before a new identity
    does anything — and it is the natural place to guarantee a clean slate.
    It resets branding and country (see its own comment: "Signing in may
    change whose product this is") but not the workspace data a previous
    occupant of this session left behind, so the same leak reaches Bob even
    if Alice's sign-out is skipped entirely (an idle timeout firing
    auth_service.touch() -> sign_out(), then Bob simply typing his own
    credentials into the form that is already on screen).
    """
    st.session_state["upload_df"] = [{"employee_id": "E-9", "name": "Carla Smit", "salary": 90000}]
    st.session_state["session_code"] = "JOBSY-LEFTOVER01"

    client = _FakeAuthClient()
    client.auth.sign_in_with_password = lambda creds: SimpleNamespace(
        session=SimpleNamespace(),
        user=SimpleNamespace(id="user-2", email="bob@clientb.example", user_metadata={}),
    )

    def fake_new_client():
        return client

    def fake_accessible_orgs(refresh=False):
        orgs = [{"id": "org-B", "name": "Client B", "slug": "clientb", "role": "viewer",
                 "partner_name": None, "pseudonymise_names": False,
                 "retention_days": None, "default_country": "NL"}]
        st.session_state[auth_service._SS_ORGS] = orgs
        return orgs

    import services.auth_service as _mod
    orig_new_client, orig_accessible = _mod._new_client, _mod.accessible_orgs
    _mod._new_client = fake_new_client
    _mod.accessible_orgs = fake_accessible_orgs
    try:
        ok, msg = auth_service.sign_in("bob@clientb.example", "correct horse battery staple")
    finally:
        _mod._new_client = orig_new_client
        _mod.accessible_orgs = orig_accessible

    assert ok, msg
    assert st.session_state.get("upload_df") is None, (
        "auth_service.sign_in() left Client A's roster "
        f"({st.session_state.get('upload_df')!r}) in st.session_state under "
        "the newly-signed-in Bob (Client B, viewer). A fresh sign-in is the "
        "one guaranteed checkpoint before a new identity touches the app, "
        "and it does not clear it."
    )


# ─────────────────────────────────────────────────────────────────────────
# FINDING 2 (MEDIUM/HIGH): save_session() will happily re-home an existing
# session code under a different org, with no check against what the code
# already belongs to.
# ─────────────────────────────────────────────────────────────────────────
class _FakeSessionsTable:
    """Mimics client.table("jobsy_sessions") enough for save_session()/
    load_session(): tracks one dict of rows keyed by session_code and records
    every upsert it is asked to perform."""

    def __init__(self, rows):
        self._rows = rows          # {code: {"org_id":..., "payload":...}}
        self.upserts = []
        self._filter = None
        self._mode = None

    def select(self, *_a, **_k):
        self._mode = "select"
        return self

    def eq(self, col, val):
        self._filter = (col, val)
        return self

    def limit(self, _n):
        return self

    def upsert(self, row, on_conflict=None):
        self._mode = "upsert"
        self.upserts.append(dict(row))
        self._rows[row["session_code"]] = {"org_id": row["org_id"], "payload": row["payload"]}
        return self

    def execute(self):
        if self._mode == "upsert":
            return SimpleNamespace(data=self.upserts[-1:])
        col, val = self._filter
        assert col == "session_code"
        row = self._rows.get(val)
        if row is None:
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[{
            "payload": row["payload"], "org_label": "", "org_id": row["org_id"],
            "created_at": "2026-01-01T00:00:00+00:00",
        }])


class _FakeDbClient:
    def __init__(self, table):
        self._table = table

    def table(self, name):
        assert name == "jobsy_sessions"
        return self._table


def test_save_session_refuses_to_repoint_a_code_at_a_different_org(monkeypatch):
    """The scenario this reaches for: a partner_analyst (or partner_admin) with
    edit rights on more than one client — an ordinary shape for a reseller's
    staff, and exactly who the sidebar's "a consultant works across several
    clients" org switcher is for.

    ui/app.py's "Load session code" box (main(), around the Session sidebar)
    loads ANY code the signed-in user can read, restores its payload
    (including upload_df — the roster itself) into st.session_state, and sets
    session_state["session_code"] to it — all without touching the ACTIVE
    org. If that consultant is currently active on Client B and loads a code
    that belongs to Client A, then clicks "Save progress", save_session() is
    called with Client A's code, Client A's roster still sitting in
    st.session_state (from the load), and org_id = Client B (the active
    org). The database is asked to upsert on session_code — an UPDATE — so
    Client A's row is silently repointed to org_id = Client B, carrying
    whatever payload the browser currently holds.

    persistence_service.py leans entirely on RLS for this ("the code is no
    longer the access control... the isolation test... is what proves that")
    — a defence that requires app.can_edit_org() to hold for BOTH orgs
    involved, which it does for exactly the role (partner-scoped edit access
    to many clients) most likely to trigger this by accident. There is no
    check inside save_session() itself that the org_id passed in matches the
    org the code already belongs to, so this test constructs precisely that
    call and shows it goes through unchallenged.
    """
    rows = {"JOBSY-SHARED001": {"org_id": "org-A", "payload": {"upload_df": [
        {"employee_id": "E-1", "name": "Anna de Vries", "salary": 61000}]}}}
    table = _FakeSessionsTable(rows)
    client = _FakeDbClient(table)

    monkeypatch.setattr(persistence_service, "_client", lambda: client)
    monkeypatch.setattr(auth_service, "active_org", lambda: {"id": "org-B", "pseudonymise_names": False})

    # Client B's own payload (from st.session_state after the load above) is
    # actually still Client A's roster -- that is the point of the scenario --
    # but even a payload save_session() builds itself demonstrates the gap:
    # nothing here refuses org_id="org-B" for a code that already belongs to
    # "org-A".
    ok = persistence_service.save_session(
        "JOBSY-SHARED001",
        {"upload_df": [{"employee_id": "E-1", "name": "Anna de Vries", "salary": 61000}]},
        org_label="Client B",
        org_id="org-B",
    )

    # The save must be REFUSED, and -- more importantly than the return value --
    # client A's row must be exactly as it was. Asserting only `ok is False`
    # would still pass if the write went through and then reported failure.
    assert ok is False, (
        "save_session() accepted a write that moves session code "
        "JOBSY-SHARED001 from org-A to org-B. RLS cannot catch this: it asks "
        "whether the caller may write to org-B, which for a partner_analyst "
        "with several clients it may. What RLS cannot know is that this row "
        "was never org-B's to take."
    )
    assert rows["JOBSY-SHARED001"]["org_id"] == "org-A", (
        "client A's session was reparented under client B's org_id"
    )
    assert table.upserts == [], (
        "the upsert was sent anyway -- the refusal has to happen before the "
        "write, not be reported after it"
    )


# ─────────────────────────────────────────────────────────────────────────
# Regression guard: accessible_orgs() really does scope memberships to the
# signed-in user (the fix the module docstring describes), not to whatever
# RLS happens to also allow the caller to read. Proves the fix holds rather
# than assuming it from reading the comment.
# ─────────────────────────────────────────────────────────────────────────
class _FakeMembershipsTable:
    def __init__(self, rows):
        self._rows = rows
        self._filters = {}

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        rows = self._rows
        for col, val in self._filters.items():
            rows = [r for r in rows if r.get(col) == val]
        return SimpleNamespace(data=rows)


class _FakeMembershipsClient:
    def __init__(self, rows):
        self._table = _FakeMembershipsTable(rows)

    def table(self, name):
        assert name == "memberships"
        return self._table


def test_accessible_orgs_is_scoped_to_the_caller_not_every_readable_row(monkeypatch):
    """The historical defect: an unfiltered select on `memberships` returns
    every row an org admin's RLS grant lets them read -- including
    colleagues' rows for the same org -- and the first one back decided what
    role was displayed. Here two different users hold two different roles on
    the SAME org; the row that must win for user-1 is user-1's own."""
    membership_rows = [
        {"user_id": "user-1", "role": "client_admin", "org_id": "org-A", "partner_id": None,
         "orgs": {"id": "org-A", "name": "Client A", "slug": "clienta",
                  "pseudonymise_names": False, "retention_days": None, "default_country": "NL"}},
        # A colleague's row for the same org, readable under 0009's
        # memberships_read policy because user-1 administers this org --
        # and, before the fix, returned by an unfiltered select too.
        {"user_id": "user-99", "role": "partner_admin", "org_id": "org-A", "partner_id": None,
         "orgs": {"id": "org-A", "name": "Client A", "slug": "clienta",
                  "pseudonymise_names": False, "retention_days": None, "default_country": "NL"}},
    ]
    client = _FakeMembershipsClient(membership_rows)
    monkeypatch.setattr(auth_service, "db", lambda: client)
    monkeypatch.setattr(auth_service, "current_user", lambda: {"id": "user-1", "email": "a@x.test"})

    st.session_state.pop(auth_service._SS_ORGS, None)
    orgs = auth_service.accessible_orgs(refresh=True)

    assert len(orgs) == 1
    assert orgs[0]["role"] == "client_admin", (
        "accessible_orgs() must resolve 'what am I on this client' from the "
        "caller's OWN membership row, not from whichever row of a colleague's "
        "came back first."
    )

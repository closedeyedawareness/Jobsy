"""
Two properties that are invisible when broken, so a test holds them.

Neither needs a database. They read the source, because what they guard is a
shape the code must keep, and the failure mode in both cases is an app that
works perfectly while doing the wrong thing.
"""
from __future__ import annotations

import ast
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTH = ROOT / "services" / "auth_service.py"
PERSIST = ROOT / "services" / "persistence_service.py"


def _module_level_assignments(path: pathlib.Path) -> set[str]:
    """Module-level names bound to something that could hold a connection.

    String and numeric constants are excluded: `_SS_CLIENT = "_auth_client"` is
    the NAME of a session-state key, not a client, and flagging it would make
    this test noise that someone eventually deletes. What it must still catch is
    the real shape — `_client = None` later filled in by a factory.
    """
    tree = ast.parse(path.read_text())
    names: set[str] = set()

    def interesting(value: ast.AST | None) -> bool:
        return not (isinstance(value, ast.Constant) and isinstance(value.value, (str, int, float)))

    for node in tree.body:            # module level only, not inside functions
        if isinstance(node, ast.Assign) and interesting(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and interesting(node.value):
            names.add(node.target.id)
    return names


def _global_statements(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text())
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            found.extend(node.names)
    return found


def test_no_module_level_database_client():
    """B-4. Streamlit serves every browser session from one Python process, so a
    module-level global holding a Supabase client is shared by every signed-in
    user at once. Once that client carries a token, whoever signed in most
    recently supplies the identity for everybody and two clients' rosters meet
    on one connection — with no error, no log line, and no symptom.

    This module used to hold exactly that (`_client = None`, plus `global
    _client`). The client now lives in st.session_state, which Streamlit keys
    per browser session.
    """
    for path in (AUTH, PERSIST):
        assigned = _module_level_assignments(path)
        offenders = {n for n in assigned if "client" in n.lower() or "_status_cache" in n}
        assert not offenders, (
            f"{path.name} has module-level state that looks like a database client: "
            f"{sorted(offenders)}. One process serves every browser session, so this "
            f"would be shared across tenants. Keep it in st.session_state."
        )
        globals_used = _global_statements(path)
        assert not globals_used, (
            f"{path.name} uses `global {', '.join(globals_used)}`. Module-level mutable "
            f"state is shared by every browser session in this process."
        )


def test_the_app_cannot_create_an_account():
    """Jobsy is sold B2B: contracts are invoiced and accounts are registered by
    an operator against addresses the client asked for. No sign-up page, no
    social login. A registration path reachable from a browser would not be a
    feature — it would let anyone mint an identity against a system holding
    salary and gender data for other people's staff.

    Accounts come from tools/manage_users.py, which runs with the secret key on
    a machine an operator controls.
    """
    source = AUTH.read_text()
    forbidden = ["sign_up", "signUp", "sign_in_with_oauth", "sign_in_with_o_auth"]
    for token in forbidden:
        # The docstring says these must not exist; that mention is not a call.
        code_only = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        tree = ast.parse(source)
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert token not in called, (
            f"auth_service calls {token}(). Jobsy has no self-registration: accounts are "
            f"created by an operator through tools/manage_users.py."
        )
        del code_only


def test_the_app_never_reads_the_secret_key():
    """The secret key bypasses row-level security by definition, so a session
    holding it reaches every client's data no matter what migration 0008 says.
    It has one legitimate home left, and it is not the web app."""
    for path in (AUTH, PERSIST):
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                # A key NAME being looked up, not the prose that explains why not.
                if v in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_KEY", "supabase_secret_key"):
                    raise AssertionError(
                        f"{path.name} reads {v}. That key ignores RLS; user traffic must "
                        f"run as the signed-in user."
                    )


def test_session_codes_are_not_guessable():
    """B-5. The code was 5 characters from `random.choices` — the Mersenne
    Twister, not a cryptographic generator — across 36^5 ≈ 60 million, with no
    rate limit, and it was the only thing protecting a client's roster."""
    source = PERSIST.read_text()
    tree = ast.parse(source)
    imported = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert "secrets" in imported, "persistence_service must generate codes with `secrets`."
    assert "random" not in imported, (
        "persistence_service imports `random`. Session codes must come from `secrets`."
    )

    import sys
    sys.path.insert(0, str(ROOT))
    from services.persistence_service import generate_code, _CODE_ALPHABET, _CODE_LENGTH

    assert _CODE_LENGTH >= 10, "a 5-character code is enumerable"
    codes = {generate_code() for _ in range(500)}
    assert len(codes) == 500, "generate_code collided within 500 draws"
    for c in codes:
        body = c.split("-", 1)[1]
        assert len(body) == _CODE_LENGTH
        assert set(body) <= set(_CODE_ALPHABET)
        # Unambiguous alphabet: these get read down a phone and typed by hand.
        assert not (set(body) & set("O0I1L")), f"ambiguous character in {c}"


# ── C-4: what reaches the database ────────────────────────────────────────
def _ps():
    import sys
    sys.path.insert(0, str(ROOT))
    from services import persistence_service
    return persistence_service


def test_pseudonymisation_removes_names_and_keeps_the_analysis():
    """Names go; everything the pay-equity analysis needs stays.

    Stripping too much would be as bad as stripping nothing — a payload with no
    salary or gender is not a session anyone can reload.
    """
    ps = _ps()
    payload = {
        "upload_name_col": "Naam",
        "upload_df": [
            {"Naam": "Anna de Vries", "Titel": "Analist", "salary": 61000,
             "gender": "F", "employee_id": "E-1"},
            {"Naam": "Bram Jansen", "Titel": "Analist", "salary": 67000,
             "gender": "M", "employee_id": "E-2"},
        ],
        "last_results": [{"name": "Anna de Vries", "matched": "Data Analyst", "score": 91}],
    }
    out = ps._pseudonymise_names(payload, salt="JOBSY-ABCDEFGHJK", name_col="Naam")
    blob = json.dumps(out)

    assert "Anna de Vries" not in blob and "Bram Jansen" not in blob
    assert out["upload_df"][0]["Naam"].startswith("EMP-")
    assert out["last_results"][0]["name"].startswith("EMP-")   # matched by _NAME_KEYS
    # Everything the analysis runs on survives untouched.
    assert out["upload_df"][0]["salary"] == 61000
    assert out["upload_df"][0]["gender"] == "F"
    assert out["upload_df"][0]["employee_id"] == "E-1"
    assert out["upload_df"][0]["Titel"] == "Analist"
    assert out["upload_name_col"] == "Naam"


def test_pseudonyms_are_stable_within_a_session_and_not_across_them():
    """Stable inside one session, or a table stops making sense. Different
    across sessions, or the tokens themselves become a way to correlate one
    client's staff against another's."""
    ps = _ps()
    row = {"name": "Anna de Vries"}
    a1 = ps._pseudonymise_names({"r": [row]}, salt="JOBSY-AAAAAAAAAA")["r"][0]["name"]
    a2 = ps._pseudonymise_names({"r": [row]}, salt="JOBSY-AAAAAAAAAA")["r"][0]["name"]
    b1 = ps._pseudonymise_names({"r": [row]}, salt="JOBSY-BBBBBBBBBB")["r"][0]["name"]
    assert a1 == a2, "the same person must read the same way across a session"
    assert a1 != b1, "the same person must NOT be linkable across sessions"


def test_pseudonymisation_is_not_reversible_by_a_stored_mapping():
    """A reversible mapping kept beside the data is the names again, wearing a
    hat. There must be no un-pseudonymise anywhere."""
    ps = _ps()
    assert not any(hasattr(ps, n) for n in
                   ("_depseudonymise", "depseudonymise", "unpseudonymise", "_name_map")), \
        "persistence_service exposes a reversal path"
    out = ps._pseudonymise_names({"r": [{"name": "Anna de Vries"}]}, salt="s")
    assert "Vries" not in json.dumps(out)

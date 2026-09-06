"""
Two properties that are invisible when broken, so a test holds them.

Neither needs a database. They read the source, because what they guard is a
shape the code must keep, and the failure mode in both cases is an app that
works perfectly while doing the wrong thing.


Every read here names its encoding. Without it, read_text() uses the platform
default — cp1252 on a Dutch Windows machine — and ui/app.py contains characters
it cannot decode, so these guards raised UnicodeDecodeError before testing
anything. They passed in CI and could never run locally, which is the worst
place for an invariant to be: green where nobody is looking and silent where
the code is written.
"""
from __future__ import annotations

import ast

import pytest
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
    tree = ast.parse(path.read_text(encoding="utf-8"))
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
    tree = ast.parse(path.read_text(encoding="utf-8"))
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
    source = AUTH.read_text(encoding="utf-8")
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
        source = path.read_text(encoding="utf-8")
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
    source = PERSIST.read_text(encoding="utf-8")
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


# ── F-1/F-2: branding must degrade, never break ───────────────────────────
def _brand(monkeypatch, **overrides):
    """branding_service with a fixed brand, bypassing Streamlit session state."""
    import sys
    sys.path.insert(0, str(ROOT))
    from services import branding_service
    brand = dict(branding_service.DEFAULT)
    brand.update(overrides)
    monkeypatch.setattr(branding_service, "current", lambda refresh=False: brand)
    return branding_service


def test_a_malformed_prefix_falls_back_instead_of_producing_undictatable_codes(monkeypatch):
    """The prefix is concatenated into a code somebody reads down a phone. The
    database constrains partner rows; BRAND_PREFIX in Streamlit secrets is
    reachable by no constraint, so it is validated here too."""
    # Note "acme-" is NOT here: code_prefix() upper-cases before validating, so
    # lower case in a secret is a typo it fixes rather than a value it rejects.
    for bad in ("ACME", "**-", "", "A-", "TOOLONGAPREFIX-", "AC ME-", None):
        b = _brand(monkeypatch, code_prefix=bad)
        assert b.code_prefix() == "JOBSY-", f"{bad!r} should have fallen back"
    assert _brand(monkeypatch, code_prefix="REWARD-").code_prefix() == "REWARD-"
    # Lower case in a secret is a typo, not a rejection.
    assert _brand(monkeypatch, code_prefix="reward-").code_prefix() == "REWARD-"


def test_a_branded_prefix_reaches_the_generated_code(monkeypatch):
    """F-2 is only done if the code a client is handed stops saying JOBSY."""
    import sys
    sys.path.insert(0, str(ROOT))
    from services import branding_service, persistence_service
    monkeypatch.setattr(branding_service, "code_prefix", lambda: "REWARD-")
    code = persistence_service.generate_code()
    assert code.startswith("REWARD-"), code
    assert "JOBSY" not in code
    # The body is not negotiable: branding changes the label, not the entropy.
    body = code.split("-", 1)[1]
    assert len(body) == persistence_service._CODE_LENGTH
    assert set(body) <= set(persistence_service._CODE_ALPHABET)


def test_an_insecure_or_broken_logo_is_dropped_not_rendered(monkeypatch):
    """A logo is fetched by the browser. Mixed content on the sign-in page is a
    bad look on the one screen that is entirely about looking trustworthy."""
    for bad in ("http://cdn.example/logo.svg", "javascript:alert(1)",
                "//cdn.example/logo.svg", "", None):
        assert _brand(monkeypatch, logo_url=bad).logo_url() is None, bad
    ok = "https://cdn.example/logo.svg"
    assert _brand(monkeypatch, logo_url=ok).logo_url() == ok


def test_bad_colours_fall_back_rather_than_emitting_broken_css(monkeypatch):
    """These values are interpolated into a <style> block. A malformed one would
    either break the rule or, worse, escape it."""
    b = _brand(monkeypatch, primary_color="darkish green", accent_color="#abc")
    assert b.colors() == ("#8850EF", "#67E8F9")
    b = _brand(monkeypatch, primary_color="#0F6E5C", accent_color="#8FD6C4")
    assert b.colors() == ("#0F6E5C", "#8FD6C4")
    css = b.css_overrides()
    assert "#0F6E5C" in css and "<style>" in css
    # An unbranded deployment emits nothing at all, rather than a no-op block.
    assert _brand(monkeypatch).css_overrides() == ""


def _ui_sources():
    """Every module that can put a string in front of a user.

    app.py alone was the whole UI when this guard was written. The 2026-09-03
    split moved twelve pages into ui/views/ and the shared chrome into
    ui/shared.py, which would have taken most of the user-facing strings out
    from under this test without a single line of it failing. An invariant has
    to follow the code it is about.
    """
    ui = ROOT / "ui"
    sources = [ui / "app.py", ui / "shared.py"] + sorted((ui / "views").glob("*.py"))

    # AND THE SERVICES, because a user-facing string is not defined by which
    # directory it lives in. This test scanned ui/ alone until 6 September 2026,
    # and three real leaks were sitting outside its reach the whole time: an
    # action line in the architecture REPORT ("Use the Jobsy Skills Assessment
    # template"), two Dutch sentences in the CAO crosswalk note that render on
    # the pay-equity screen, and one in the market notes. A reseller's client
    # would have read the vendor's name in a document the reseller put their own
    # logo on — which is the entire failure white-labelling exists to prevent,
    # arriving through the one path nobody was watching.
    #
    # The lesson is not "add services/". It is that a guard scoped to a
    # DIRECTORY guards a directory, and this invariant is about a property of
    # strings. Scoped to where strings are built, it follows the code.
    sources += sorted((ROOT / "services").glob("*.py"))
    sources += sorted((ROOT / "services" / "country_packs").glob("*.py"))
    return sources


@pytest.mark.parametrize("path", _ui_sources(), ids=lambda p: p.name)
def test_no_user_facing_string_hard_codes_the_product_name(path):
    """F-2. Every remaining "Jobsy" in a user-facing string must be a comment, a
    docstring, or the single fallback in _brand_name() — never something a user
    reads.

    Covers ui/ AND services/: a note built in a service and rendered on a screen
    is exactly as visible as one written in the view, and for a while three of
    them were. See `_ui_sources` for what was found outside the old scope.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Docstrings are for whoever maintains this, not for whoever uses it. They
    # are collected by identity rather than by value, so a docstring that happens
    # to match a real UI string does not excuse the real one.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))

    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            if "Jobsy" in node.value and node.value.strip() != "Jobsy":
                offenders.append((node.lineno, node.value[:70]))
    # A bare "Jobsy" is the fallback; anything longer is a sentence somebody sees.
    assert not offenders, (
        f"user-visible strings in {path.name} still hard-code the product name: "
        + "; ".join(f"line {ln}: {t!r}" for ln, t in offenders)
        + " — route them through _brand_name()"
    )


# ── the library is the product, and it had a download button on it ────────

@pytest.mark.parametrize("role, may", [
    ("partner_admin",   True),    # the account that maintains the library
    ("partner_analyst", False),
    ("client_admin",    False),   # the customer's own admin — the point of this
    ("analyst",         False),
    ("viewer",          False),
])
def test_only_the_partner_admin_may_export_the_library(role, may):
    """81 roles, 45 salary bands, a grade ladder and 571 role-to-skill links.

    A client who exports that once does not need the product again. Until 6
    September 2026 the navigation list was unfiltered, so every signed-in
    account reached the Data Quality page, and the export button sat on it with
    no check at all.

    Narrower than `is_admin()` deliberately: that helper includes client_admin,
    which is the customer's own administrator and the role this exists to stop.
    """
    from unittest.mock import patch
    from services import auth_service

    with patch.object(auth_service, "active_org", lambda: {"role": role}):
        assert auth_service.can_export_library() is may


def test_no_signed_out_session_can_export():
    from unittest.mock import patch
    from services import auth_service
    with patch.object(auth_service, "active_org", lambda: None):
        assert auth_service.can_export_library() is False


def test_the_export_button_is_behind_that_check_and_not_merely_beside_it():
    """Structural, because the failure is a button that renders anyway.

    A permission helper that exists and is never consulted reads exactly like
    one that is — the pay-equity `country_col` and the report's `currency` were
    both that shape this week.
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "ui" / "views" / "data_quality.py").read_text(encoding="utf-8")

    assert "can_export_library()" in src, "nothing decides who may export the library"
    guard = src.index("can_export_library()")
    button = src.index("Export library to Excel")
    assert guard < button, "the check is declared after the button it should gate"

    # And the button must sit inside the allowed branch, not merely below the
    # check: `if not _may_export` followed by an unguarded call would pass the
    # ordering test above while rendering for everybody.
    between = src[guard:button]
    assert "else:" in between, (
        "the export is not inside the branch the permission check opens")


def test_a_client_keeps_the_exports_that_are_about_their_own_data():
    """The gate must not become a general refusal to let clients have anything.

    Their roster, their matches, their pay-equity report and the architecture
    report are theirs. Only the reference set is withheld.
    """
    import pathlib
    ui = pathlib.Path(__file__).resolve().parents[1] / "ui"
    others = [p for p in ui.rglob("*.py")
              if "_logged_download(" in p.read_text(encoding="utf-8")
              and p.name != "shared.py"]
    gated = [p for p in others
             if "can_export_library" in p.read_text(encoding="utf-8")]
    assert len(others) > len(gated), (
        "every download in the product is now behind the library gate, which "
        "withholds a client's own data along with ours")

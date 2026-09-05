"""
Money is displayed in the market's own currency, or not at all.

`ui/app.py` had `_euro()` and twenty-three other places writing "€" directly.
That is right for the Netherlands and silently wrong for Poland, Sweden and
Denmark — all seeded in `countries` precisely so nothing may assume euro. A
salary rendered "€90.000" when it is 90,000 złoty is not a formatting bug; it is
a number that means something else, on a screen someone makes pay decisions from.

These tests need no database: `registry()` is patched, which is also how they
prove the fallbacks work when there is no session at all.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

REGISTRY = [
    {"code": "NL", "name": "Netherlands", "currency": "EUR", "is_live": True},
    {"code": "PL", "name": "Poland", "currency": "PLN", "is_live": True},
    {"code": "SE", "name": "Sweden", "currency": "SEK", "is_live": False},
    {"code": "EU", "name": "EU baseline", "currency": "EUR", "is_live": True},
    {"code": "XX", "name": "Nowhere", "currency": "XYZ", "is_live": True},
]


@pytest.fixture
def cs(monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT))
    from services import country_service
    monkeypatch.setattr(country_service, "registry", lambda refresh=False: REGISTRY)
    monkeypatch.setattr(country_service, "active_country", lambda: "NL")
    return country_service


def test_each_market_gets_its_own_currency(cs):
    assert cs.currency_for("NL") == "EUR"
    assert cs.currency_for("PL") == "PLN"
    assert cs.currency_for("SE") == "SEK"


def test_money_is_never_silently_euro(cs):
    """The whole point. Same number, three markets, three different meanings."""
    assert cs.money(90000, country="NL") == "€90.000"
    assert cs.money(90000, country="PL") == "90.000 zł"
    assert cs.money(90000, country="SE") == "90.000 kr"
    # No two of them may render identically, or the display has lost the fact
    # that distinguishes them.
    rendered = {cs.money(90000, country=c) for c in ("NL", "PL", "SE")}
    assert len(rendered) == 3


def test_a_currency_with_no_symbol_shows_its_code_rather_than_a_guess(cs):
    """Guessing a glyph is how "kr" ends up meaning the wrong krone. An ISO
    code is never wrong, only plainer."""
    assert cs.money(1000, country="XX") == "1.000 XYZ"


def test_an_unknown_country_falls_back_rather_than_failing(cs):
    """A country not in the registry must not take the screen down; it gets the
    deployment default, which is euro."""
    assert cs.currency_for("ZZ") == "EUR"
    assert cs.money(1000, country="ZZ") == "€1.000"


@pytest.mark.parametrize("bad", [None, "", "n/a", float("nan")])
def test_a_missing_amount_is_a_dash_not_a_zero(cs, bad):
    """Zero pay and unknown pay are different facts about a person, and one of
    them is a data-quality problem rather than a salary."""
    assert cs.money(bad) == "—", f"{bad!r} rendered as a number"


def test_eu_is_never_offered_as_a_place_anyone_works(cs):
    """EU is a fallback scope for reference rows. Offering it would let a client
    file a pay report for a country that does not exist — and the registry here
    deliberately marks it live to prove the filter is on the CODE, not the flag."""
    codes = [c["code"] for c in cs.live_countries()]
    assert "EU" not in codes
    assert "NL" in codes and "PL" in codes
    assert "SE" not in codes, "a market that is not live must not be offered"


def test_the_app_has_no_hard_coded_currency_left():
    """A regression guard with teeth: every euro sign in ui/app.py must be in a
    comment or docstring explaining why there are none, not in a format string.

    This is the check that would have failed before this change, on 24 sites.
    """
    import ast
    # The UI was one file until the page split moved thirteen pages into
    # ui/views/. Scanning only ui/app.py would have quietly stopped checking
    # almost everything it was written to check -- a guard that passes because
    # it is looking at the wrong place is worse than no guard.
    offenders = []
    for path in sorted((ROOT / "ui").rglob("*.py")):
        offenders.extend(_euros_in(path))
    assert not offenders, (
        "hard-coded euro in user-visible strings: "
        + "; ".join(f"{f}:{ln}: {t!r}" for f, ln, t in offenders)
        + " — route it through _money() / _cur()")


def _euros_in(path):
    """Euro signs in a file, excluding docstrings and the documented fallbacks."""
    import ast
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))

    # _money() and _cur() are the fallback path itself: when there is no session
    # to ask which market this is, euro is the deployment default. Their own
    # euro constants are the design, not a violation of it — everywhere else,
    # a euro sign means somebody assumed.
    exempt = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("_money", "_cur"):
            for inner in ast.walk(node):
                exempt.add(id(inner))

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings and id(node) not in exempt \
                and "€" in node.value:
            found.append((path.name, node.lineno, node.value[:60]))
    return found


def test_the_workbook_export_does_not_assume_euro_either():
    """The Excel report is what a client forwards to their works council. It
    takes the symbol as a parameter rather than reading a session, because a
    service that builds a workbook must also work from a script."""
    import ast, inspect, sys
    sys.path.insert(0, str(ROOT))
    from services.architecture_report_service import ArchitectureReportService

    params = inspect.signature(ArchitectureReportService.__init__).parameters
    assert "currency" in params, "the report cannot be told which market it is for"

    source = (ROOT / "services" / "architecture_report_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    # The constructor's DEFAULT is allowed to be euro -- a caller that says
    # nothing gets the deployment default. What must not exist is a euro sign
    # anywhere a cell is written.
    # __init__ may default to euro (a caller that says nothing gets the
    # deployment default), and _money() is the placement rule itself: it has to
    # name the two symbols that lead rather than trail. Everywhere else, a euro
    # sign means somebody assumed.
    exempt = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("__init__", "_money"):
            for inner in ast.walk(node):
                exempt.add(id(inner))
    bad = [n.lineno for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and id(n) not in exempt and "€" in n.value]
    assert not bad, f"hard-coded euro remains in the report service at lines {bad}"


def test_no_local_variable_shadows_a_module_level_helper():
    """The bug this exists for cost a whole signed-in page.

    `main()` already had a local called `_cur` — the currently selected
    *industry*. Adding a module-level `_cur()` for the currency did not collide
    at import, at lint, or in any unit test: Python makes a name local to the
    ENTIRE function if it is assigned anywhere in it, so every `_cur()` call in
    `main()` raised `TypeError: 'str' object is not callable` — and would have
    raised `UnboundLocalError` instead had that branch not run.

    Only the browser saw it, because `main()` is not callable from a test. So
    the cheap structural check is the one worth keeping: a helper meant to be
    called from inside a function must not share a name with anything that
    function assigns.
    """
    import ast
    tree = ast.parse((ROOT / "ui" / "app.py").read_text(encoding="utf-8"))

    module_functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}

    offenders = []
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            # A nested def legitimately rebinds its own name; only plain
            # assignments and loop targets can shadow a helper by accident.
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            elif isinstance(node, ast.For):
                targets = [node.target]
            for t in targets:
                for name in ast.walk(t):
                    if isinstance(name, ast.Name) and name.id in module_functions \
                            and name.id != fn.name:
                        offenders.append((fn.name, name.id, name.lineno))

    assert not offenders, (
        "a local assignment shadows a module-level helper for its whole function: "
        + "; ".join(f"{f}() rebinds {n}() at line {ln}" for f, n, ln in offenders)
        + " — rename the local"
    )

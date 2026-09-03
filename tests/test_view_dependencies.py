"""
A view names the services it uses.

WHY THIS EXISTS. The page modules do `from ui.shared import *`, which is what
let twelve pages move out of app.py without a line of their code changing. The
cost is that a dependency arriving that way is invisible to the import graph —
and on 2026-09-03 that graph was used to decide what was wired and what was not.
It reported `ui/views/connect.py` as depending on nothing while the module used
AfasConnector and WorkdayConnector.

So: anything a view uses from core/ or services/ directly, it imports directly.
Theme tokens and layout helpers stay with the star import; they are chrome, not
architecture.

WHAT THIS CANNOT FIX, and it is the larger half. Most view dependencies are
INJECTED, not imported — `benefits_benchmarking_page(catalog, benefits_svc)`
receives its service as an argument, and no import statement will ever show
that. The real dependency graph of this app is the call-signature graph. This
test keeps the import graph honest about the part it can see, and does not
pretend to see the rest.
"""

import ast
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent.parent / "ui"
VIEWS = sorted(p for p in (UI / "views").glob("*.py") if p.name != "__init__.py")


def _shared_reexports():
    """name -> module, for everything ui/shared.py pulls from core/ or services/."""
    tree = ast.parse((UI / "shared.py").read_text(encoding="utf-8"))
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] in ("core", "services"):
            for a in n.names:
                out[a.asname or a.name] = n.module
    return out


@pytest.mark.parametrize("path", VIEWS, ids=lambda p: p.name)
def test_a_view_names_the_services_it_uses(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}

    declared = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                declared.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                declared.add((a.asname or a.name).split(".")[0])

    reexports = _shared_reexports()
    hidden = sorted((used & set(reexports)) - declared)
    assert not hidden, (
        f"{path.name} uses {', '.join(hidden)} through `import *`, so no import graph can "
        f"see the dependency. Import it by name: "
        + "; ".join(f"from {reexports[h]} import {h}" for h in hidden)
    )

"""
The map has to be right about the things it was wrong about.

Every assertion here is one of the four blind spots that made the 2026-09-03
wiring reads wrong. A measurement used to decide what to build needs its own
tests more than the code it measures does — a wrong instrument does not fail
loudly, it just tells you a story you like.
"""

from pathlib import Path

import pytest

from tools import dependency_map as dm


def test_it_sees_from_package_import_module():
    """`from services import auth_service` resolves to the PACKAGE, and the
    module hides in the name list. Missing this form reported the entire auth
    layer as reached by nothing."""
    app = dm.ROOT / "ui" / "app.py"
    assert "services/auth_service.py" in dm.imports_of(app)


def test_it_sees_imports_that_live_inside_functions():
    """Most imports in this codebase are deferred into function bodies."""
    dq = dm.ROOT / "ui" / "views" / "data_quality.py"
    found = dm.imports_of(dq)
    assert any(f.endswith("library_history_service.py") for f in found)


def test_an_aliased_call_is_not_reported_as_dead():
    """`from x import is_available as _ps_available` then `_ps_available()`.
    Reading the literal name only reported five live functions as dead."""
    dead = dm.uncalled_surfaces()
    assert not [d for d in dead if d.endswith("::is_available")]
    assert not [d for d in dead if d.endswith("::save_session")]


def test_it_finds_dependencies_that_arrive_as_arguments():
    """The graph that actually carries this product. compose(…, repo) is a
    dependency on the Repository that no import statement records."""
    pcs = dm.ROOT / "services" / "pay_components_service.py"
    got = dict(dm.injections_of(pcs))
    assert "repo" in got["compose(…)"]


def test_a_page_receiving_its_service_is_recorded():
    benefits = dm.ROOT / "ui" / "views" / "benefits.py"
    got = dict(dm.injections_of(benefits))
    assert "benefits_svc" in got["benefits_benchmarking_page(…)"]


def test_the_two_graphs_are_reported_separately():
    """Merging them would hide that one is a heuristic on parameter names. A
    parameter called `svc` holding a matcher is missed, and a map that quietly
    overstates is worse than one that admits its blind spot."""
    src = (dm.ROOT / "tools" / "dependency_map.py").read_text(encoding="utf-8")
    assert "None of these appear above" in src
    assert "heuristic" in src


def test_the_orphans_are_the_two_known_ones():
    mods = dm.modules()
    importers = set()
    for p in mods:
        importers |= dm.imports_of(p)
    orphans = sorted(
        p.relative_to(dm.ROOT).as_posix() for p in mods
        if p.relative_to(dm.ROOT).as_posix() not in importers
        and p.parts[-2] != "tools" and p.name != "app.py")
    assert orphans == ["core/loader.py", "core/logger.py"]


def test_it_runs_end_to_end():
    assert dm.main([]) == 0

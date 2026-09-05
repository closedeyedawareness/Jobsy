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


#: Modules nothing imports, each with the reason it is allowed to stay that way.
#: A new entry here has to be argued for, which is the point: this list is a
#: statement of intent, not a snapshot of whatever happens to be unwired.
DELIBERATE_ORPHANS = {
    "core/loader.py": "one line, a placeholder comment — dead, and named so the count is known",
    "core/logger.py": "two lines; every module calls logging.getLogger('jobsy') itself",
    "services/art4_evaluation.py":
        "the Art. 4 engine. No role is rated and no weighting is decided, so wiring an "
        "unvalidated job evaluation into a product that prints pay findings would be worse "
        "than not having one. Unreached is the correct state until the instrument is real.",
    # The four below are one argument, not four. country_packs discovers its
    # members with pkgutil rather than a hand-kept list, for the same reason
    # this file exists: a register you must remember to update is the first
    # thing to go stale, and what it forgets is the market nobody tested. A
    # static import graph cannot see a dynamic import, so every pack reads as an
    # orphan by construction. Wiring them in by name would satisfy this test and
    # reintroduce exactly the register the design removes.
    "services/country_packs/eu.py": "country pack, loaded by pkgutil discovery in country_packs/__init__",
    "services/country_packs/nl.py": "country pack, loaded by pkgutil discovery in country_packs/__init__",
    "services/country_packs/be.py": "country pack, loaded by pkgutil discovery in country_packs/__init__",
    "services/country_packs/de.py": "country pack, loaded by pkgutil discovery in country_packs/__init__",
    "services/country_packs/es.py": "country pack, loaded by pkgutil discovery in country_packs/__init__",
    "services/country_packs/fr.py": "country pack, loaded by pkgutil discovery in country_packs/__init__",
    "services/country_packs/pl.py": "country pack, loaded by pkgutil discovery in country_packs/__init__",
}


def test_every_orphan_is_one_we_argued_for():
    """The guard that caught art4_evaluation the moment it landed — which is the
    signal working, not the test being brittle."""
    mods = dm.modules()
    importers = set()
    for p in mods:
        importers |= dm.imports_of(p)
    orphans = sorted(
        p.relative_to(dm.ROOT).as_posix() for p in mods
        if p.relative_to(dm.ROOT).as_posix() not in importers
        and p.parts[-2] != "tools" and p.name != "app.py")
    unexplained = [o for o in orphans if o not in DELIBERATE_ORPHANS]
    assert not unexplained, (
        f"reached by nothing and not argued for: {unexplained}. Either wire it, delete it, "
        f"or add it to DELIBERATE_ORPHANS with the reason.")
    stale = [o for o in DELIBERATE_ORPHANS if o not in orphans]
    assert not stale, f"listed as a deliberate orphan but now reachable: {stale}"


def test_it_runs_end_to_end():
    assert dm.main([]) == 0

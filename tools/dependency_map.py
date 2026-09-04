#!/usr/bin/env python3
"""
dependency_map.py — what is wired to what, measured rather than remembered.

    python tools/dependency_map.py            # the whole map
    python tools/dependency_map.py --imports  # just the import graph
    python tools/dependency_map.py --injected # just the injection graph
    python tools/dependency_map.py --dead     # surfaces nothing calls

WHY THIS IS A FILE AND NOT A NOTE

On 2026-09-03 the wiring of this codebase was measured four separate times, and
four times the first answer was wrong because the measurement was:

  * an import graph that could not see `from services import auth_service`,
    so it called the whole auth layer unreachable;
  * a session_state scan that could not see keys moved as a list, so it
    reported a wire connected at one end that was connected at both;
  * a fan-in count that could not see an argument, so the Repository — which
    nineteen services run on — looked peripheral;
  * a column search that counted "mentioned in the loader" as "consumed".

Every one of those errors pointed the same way: toward something being broken.
That direction is not random. A finding flatters the finder, so the reading to
distrust first is the one that makes the work look valuable.

An instrument used that often should not be retyped from memory each time.

WHAT IT MEASURES, AND WHAT IT CANNOT

`imports` is the graph everybody draws, and it is the thinnest of the three.

`injected` is the one that carries this product. Pages and services receive
what they depend on as arguments — `benefits_benchmarking_page(catalog,
benefits_svc)`, `compose(base, function, level, repo)` — and no import
statement records that. This walks parameter names instead, which is a
heuristic: it recognises a dependency by what the parameter is CALLED. A
parameter named `svc` that holds a matcher will be missed. It is reported as a
separate graph rather than merged, so nobody mistakes it for complete.

Neither graph sees `st.session_state`, which is how client data actually moves
between pages. That is a third graph and it is not in here; see the picture.
"""
from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKGS = ("core", "services", "ui", "tools")
PKG_NAMES = set(PKGS) | {"jobsy"}

#: Parameter names that mean "a dependency was handed in". Deliberately short
#: and explicit: guessing more widely would inflate the graph with false edges,
#: and a map that overstates is worse than one that admits its blind spot.
INJECTED = {
    "repo": "core.repository", "repository": "core.repository",
    "catalog": "core.catalog", "cat": "core.catalog",
    "client": "supabase client", "service": "a service", "svc": "a service",
    "matcher": "services.matching_service", "index": "core.search_index",
    "benefits_svc": "services.benefits_service",
    "assessments": "services.assessment_service",
}


def modules() -> list[Path]:
    return [p for pkg in PKGS for p in sorted((ROOT / pkg).rglob("*.py"))
            if "__pycache__" not in p.parts and p.name != "__init__.py"]


def _resolve(target: str) -> str | None:
    parts = [x for x in target.split(".") if x != "jobsy"]
    while parts:
        cand = "/".join(parts) + ".py"
        if (ROOT / cand).exists():
            return cand
        parts.pop()
    return None


def imports_of(path: Path) -> set[str]:
    """Every module this file imports, including inside functions.

    Handles `from services import auth_service`, which resolves to the PACKAGE
    and hides the module in the name list. Missing that form is what made the
    auth layer look unreachable.
    """
    out: set[str] = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            for a in n.names:
                r = _resolve(a.name)
                if r:
                    out.add(r)
        elif isinstance(n, ast.ImportFrom) and n.module:
            r = _resolve(n.module)
            if r:
                out.add(r)
            base = [x for x in n.module.split(".") if x != "jobsy"]
            if base and base[0] in PKG_NAMES:
                for a in n.names:
                    r2 = _resolve(".".join(base + [a.name]))
                    if r2:
                        out.add(r2)
    return out


def injections_of(path: Path) -> list[tuple[str, list[str]]]:
    """Public callables that receive a dependency, and which ones."""
    found = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and not n.name.startswith("_"):
            init = next((f for f in n.body
                         if isinstance(f, ast.FunctionDef) and f.name == "__init__"), None)
            args = [a.arg for a in init.args.args[1:]] if init else []
            name = f"{n.name}(…)"
        elif isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
            args = [a.arg for a in n.args.args]
            name = f"{n.name}(…)"
        else:
            continue
        got = [a for a in args if a in INJECTED]
        if got:
            found.append((name, got))
    return found


def uncalled_surfaces() -> list[str]:
    """Public functions no other module calls, with aliases resolved.

    `from x import is_available as _ps_available` then `_ps_available()` is a
    call. Reading only the literal name reported five live functions as dead.
    """
    mods = modules()
    alias: dict[str, set[str]] = defaultdict(set)
    for p in mods:
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.ImportFrom):
                for a in n.names:
                    if a.asname:
                        alias[a.asname].add(a.name)
    called: set[str] = set()
    for p in mods:
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call):
                f = n.func
                nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if nm:
                    called.add(nm)
                    called |= alias.get(nm, set())
    dead = []
    for p in mods:
        if p.parts[-2] == "tools":
            continue                      # entry points; their surface is the CLI
        for n in ast.parse(p.read_text(encoding="utf-8")).body:
            if isinstance(n, ast.FunctionDef) and not n.name.startswith("_") and n.name not in called:
                dead.append(f"{p.relative_to(ROOT).as_posix()}::{n.name}")
    return dead


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--imports", action="store_true")
    ap.add_argument("--injected", action="store_true")
    ap.add_argument("--dead", action="store_true")
    a = ap.parse_args(argv)
    everything = not (a.imports or a.injected or a.dead)

    mods = modules()

    if a.imports or everything:
        edges = {p: imports_of(p) for p in mods}
        importers: dict[str, set[str]] = defaultdict(set)
        for src, dsts in edges.items():
            for d in dsts:
                importers[d].add(src.relative_to(ROOT).as_posix())
        print(f"IMPORT GRAPH — {len(mods)} modules, "
              f"{sum(len(v) for v in edges.values())} edges\n")
        orphans = [p.relative_to(ROOT).as_posix() for p in mods
                   if not importers.get(p.relative_to(ROOT).as_posix())
                   and p.parts[-2] != "tools" and p.name != "app.py"]
        for o in sorted(orphans):
            print(f"  reached by nothing: {o}")
        if not orphans:
            print("  every module is reached by something.")
        print()

    if a.injected or everything:
        print("INJECTION GRAPH — dependencies handed in, invisible to imports\n")
        total = 0
        for p in mods:
            got = injections_of(p)
            if not got:
                continue
            print(f"  {p.relative_to(ROOT).as_posix()}")
            for name, args in got:
                total += len(args)
                print(f"      {name:<40}{', '.join(args)}")
        print(f"\n  {total} injected dependencies. None of these appear above.\n")

    if a.dead or everything:
        dead = uncalled_surfaces()
        print(f"PUBLIC SURFACES NOTHING CALLS — {len(dead)}\n")
        for d in sorted(dead):
            print(f"  {d}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

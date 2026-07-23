"""
Assemble a dated provenance inventory: what can be shown to have existed, when,
and how strongly each date can be relied on.

Written for the same adversarial reader as tools/delivery_log.py, and with the
same discipline: every item is graded by the strength of its evidence, and the
weak grades are labelled weak rather than quietly presented alongside the strong
ones. A document that treats a file mtime as equivalent to a third-party
timestamp is worth less than no document.

Evidence grades
---------------
  A  Third party, server-side. Not derived from this machine and not editable
     from it. GitHub repository creation and push events.
  B  Embedded document metadata. Travels inside the file (OOXML docProps, PDF
     CreationDate), so it survives copying - but the author can set it.
  C  Local git author timestamps. Written by the committer's own clock.
  D  Filesystem timestamps. Reset by copying, syncing, restoring or unzipping.
     Near-worthless alone; included only for completeness.

The report also states plainly what is NOT evidenced, because the gap is the
first thing an opponent will look for, and naming it first is worth more than
having it found.

Usage
    python tools/provenance_inventory.py
    python tools/provenance_inventory.py --cutoff 2026-06-24 --out prov.md
    python tools/provenance_inventory.py --roots "C:\\Jobsy,C:\\People-Harmonics"
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOTS = [r"C:\Jobsy", r"C:\People-Harmonics", r"C:\ResearchAgent",
                 r"C:\Sheetz", r"C:\KFA", r"C:\SocialPoster"]
DOC_EXT = {".xlsx", ".docx", ".pptx", ".odt", ".ods"}
PDF_EXT = {".pdf"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", ".pytest_cache", ".next", "site-packages"}

# GitHub web-UI bulk operations - not authorship (see tools/delivery_log.py)
ADMIN_RE = re.compile(
    r"^(add files via upload|delete\s|create git\b|initial commit|merge\s|"
    r"update [\w/.\-]+$|create [\w/.\-]+$)", re.I)


def run(cmd, cwd=None) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


# ------------------------------------------------------------------ grade A
def github_repos() -> list[dict]:
    out = run(["gh", "repo", "list", "--limit", "200", "--json",
               "name,createdAt,pushedAt,isPrivate,url,description"])
    if not out:
        return []
    try:
        repos = json.loads(out)
    except json.JSONDecodeError:
        return []
    repos.sort(key=lambda r: r["createdAt"])
    return repos


# ------------------------------------------------------------------ grade C
def local_repo_history(path: Path) -> dict | None:
    if not (path / ".git").exists():
        return None
    fmt = "%ad\x1f%s"
    log = run(["git", "log", "--all", "--no-merges", f"--pretty=format:{fmt}",
               "--date=format:%Y-%m-%d"], cwd=path)
    if not log.strip():
        return None
    all_dates, authored = [], []
    for line in log.splitlines():
        if "\x1f" not in line:
            continue
        d, subj = line.split("\x1f", 1)
        all_dates.append(d)
        if not ADMIN_RE.match(subj):
            authored.append(d)
    origin = run(["git", "remote", "get-url", "origin"], cwd=path).strip()
    return {
        "path": str(path), "origin": origin, "commits": len(all_dates),
        "first_commit": min(all_dates), "last_commit": max(all_dates),
        "authored_commits": len(authored),
        "first_authored": min(authored) if authored else None,
    }


# ------------------------------------------------------------------ grade B
def ooxml_created(p: Path) -> str | None:
    try:
        with zipfile.ZipFile(p) as z:
            xml = z.read("docProps/core.xml").decode("utf-8", "replace")
        m = re.search(r"<dcterms:created[^>]*>([^<]+)</dcterms:created>", xml)
        return m.group(1) if m else None
    except Exception:
        return None


def pdf_created(p: Path) -> str | None:
    try:
        blob = p.read_bytes()[:400_000]
        m = re.search(rb"/CreationDate\s*\(D:(\d{14})", blob)
        if not m:
            return None
        s = m.group(1).decode()
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:14]}"
    except Exception:
        return None


def scan_documents(roots: list[Path], cutoff: str) -> list[dict]:
    found = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in DOC_EXT | PDF_EXT:
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            created = (ooxml_created(p) if p.suffix.lower() in DOC_EXT
                       else pdf_created(p))
            if not created:
                continue
            found.append({
                "path": str(p), "embedded_created": created[:19],
                "predates_cutoff": created[:10] < cutoff,
                "fs_modified": datetime.fromtimestamp(
                    p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d"),
            })
    found.sort(key=lambda f: f["embedded_created"])
    return found


# -------------------------------------------------------------------- report
def build(repos, locals_, docs, cutoff) -> tuple[str, dict]:
    L: list[str] = []
    add = L.append
    add("# People Harmonics / Jobsy — provenance inventory")
    add("")
    add(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}. "
        f"Cutoff for \"pre-existing\": **{cutoff}**.")
    add("")
    add("Every item is graded by how much weight its date can carry. "
        "Grades are defined at the end; **A** is third-party and server-side, "
        "**D** is a filesystem timestamp and proves almost nothing.")
    add("")

    add("## A — Third-party timestamps (GitHub, server-side)")
    add("")
    if repos:
        add("Created and last-push times recorded by GitHub, not by this machine:")
        add("")
        add("| Repository | Created (UTC) | Last push | Visibility |")
        add("| --- | --- | --- | --- |")
        for r in repos:
            add(f"| `{r['name']}` | **{r['createdAt'][:19]}** | {r['pushedAt'][:19]} | "
                f"{'private' if r['isPrivate'] else 'public'} |")
        add("")
        earliest = repos[0]
        add(f"**Earliest independently recorded activity: {earliest['createdAt'][:10]}** "
            f"(`{earliest['name']}`) — {len(repos)} repositories in total.")
        pre = [r for r in repos if r["createdAt"][:10] < cutoff]
        add("")
        add(f"{len(pre)} of {len(repos)} repositories were created before {cutoff}.")
    else:
        add("_`gh` returned nothing — GitHub timestamps not collected. "
            "This is the strongest available evidence; re-run once authenticated._")
    add("")

    add("## B — Embedded document metadata")
    add("")
    add("Creation timestamps stored *inside* the file (OOXML `docProps`, PDF "
        "`CreationDate`). These survive copying, unlike filesystem dates, but the "
        "author can set them — corroborating, not conclusive.")
    add("")
    pre_docs = [d for d in docs if d["predates_cutoff"]]
    if pre_docs:
        add(f"**{len(pre_docs)} document(s) carry an embedded creation date before {cutoff}:**")
        add("")
        add("| Embedded created | File |")
        add("| --- | --- |")
        for d in pre_docs[:60]:
            add(f"| **{d['embedded_created']}** | `{d['path']}` |")
        if len(pre_docs) > 60:
            add(f"| … | _and {len(pre_docs)-60} more_ |")
    else:
        add(f"_No document carries an embedded creation date before {cutoff}._ "
            f"({len(docs)} document(s) scanned.)")
    add("")

    add("## C — Local git history (self-reported clock)")
    add("")
    add("Author dates come from the committing machine and can be set to any "
        "value. Useful for sequence and volume; weak as standalone proof.")
    add("")
    add("| Repository | First commit | First *authored* commit | Commits | Origin |")
    add("| --- | --- | --- | ---: | --- |")
    for r in locals_:
        origin = r["origin"].replace("https://github.com/", "").replace(".git", "") or "—"
        add(f"| `{Path(r['path']).name}` | {r['first_commit']} | "
            f"{r['first_authored'] or '—'} | {r['commits']} | {origin} |")
    add("")
    add("\"First authored\" excludes bulk `Add files via upload` / `Delete <file>` "
        "operations, which record when a codebase was moved into GitHub — not when "
        "it was written.")
    add("")

    add("## What is NOT evidenced")
    add("")
    add(f"- Work done before **{cutoff}** that was later bulk-uploaded carries **no "
        "authorship date in git**. The upload commit dates the transfer, not the work.")
    add("- Filesystem timestamps across these directories are unreliable: copying, "
        "syncing, restoring from backup and unzipping all reset them. They are "
        "deliberately excluded from the tables above rather than presented as evidence.")
    add("- Nothing here speaks to *where* work was done or *on whose equipment*. "
        "That has to be established separately.")
    add("")

    add("## Third-party anchors worth obtaining")
    add("")
    add("These outrank everything above, because none of them is under the "
        "author's control. Fill in as they are obtained:")
    add("")
    add("| Anchor | Why it carries weight | Date |")
    add("| --- | --- | --- |")
    add("| **i-DEPOT (BOIP)** | The Benelux IP Office's sealed, dated deposit — "
        "purpose-built as dated proof of what you held on a given day. Deposit the "
        "current codebase now: it stops the clock running against you. | _to obtain_ |")
    add("| **KvK registration** | Chamber of Commerce record of the venture, "
        "third-party and dated | _to obtain_ |")
    add("| **Domain WHOIS creation** | Registrar record for the project domains | _to obtain_ |")
    add("| **Bank account opening** | Business account, dated by the bank | _to obtain_ |")
    add("| **Client contracts / invoices** | Counterparty-dated, hard to dispute | _to obtain_ |")
    add("| **Cloud version history** | Drive/OneDrive per-file revision timestamps, "
        "server-side | _to export_ |")
    add("")

    add("## Evidence grades")
    add("")
    add("| Grade | Source | Reliability |")
    add("| --- | --- | --- |")
    add("| A | Third-party server-side records (GitHub, registrars, registries) | "
        "Not under the author's control |")
    add("| B | Metadata embedded in a file | Survives copying; author-editable |")
    add("| C | Local git author timestamps | Written by the author's own clock |")
    add("| D | Filesystem mtime/ctime | Reset by copy, sync, restore, unzip |")
    add("")
    add("Generated by `tools/provenance_inventory.py`. This is an evidence "
        "inventory, not legal advice.")
    add("")

    data = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "cutoff": cutoff,
        "github_repos": repos,
        "local_repos": locals_,
        "documents_predating_cutoff": pre_docs,
        "documents_scanned": len(docs),
    }
    return "\n".join(L), data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="2026-06-24",
                    help="Date before which artefacts count as pre-existing "
                         "(default: the Jobsy repository's creation date)")
    ap.add_argument("--roots", default=",".join(DEFAULT_ROOTS))
    ap.add_argument("--out", default="provenance-inventory.md")
    ap.add_argument("--json", dest="json_out", default="provenance-inventory.json")
    a = ap.parse_args()

    roots = [Path(r.strip()) for r in a.roots.split(",") if r.strip()]
    present = [r for r in roots if r.exists()]
    print(f"scanning {len(present)} of {len(roots)} root(s)…")

    repos = github_repos()
    locals_ = [h for r in present if (h := local_repo_history(r))]
    docs = scan_documents(present, a.cutoff)

    md, data = build(repos, locals_, docs, a.cutoff)
    Path(a.out).write_text(md, encoding="utf-8")
    print(f"wrote {a.out}")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"wrote {a.json_out}")
    print(f"\ngithub repos: {len(repos)} | local repos: {len(locals_)} | "
          f"documents predating {a.cutoff}: {len(data['documents_predating_cutoff'])}")


if __name__ == "__main__":
    main()

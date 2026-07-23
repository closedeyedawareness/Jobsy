"""
Generate a dated, sourced record of what shipped in Jobsy and when.

Written for one specific purpose: producing evidence that has to survive an
adversarial reader. That constraint drives every design decision below.

  * The full record is always reported. Every filtered view carries its
    denominator alongside it, so a subset can never be mistaken for the whole.
    The repository is public; anyone can reproduce the complete history in
    minutes, and a document that quietly omitted half of it would discredit the
    half that is accurate.

  * "Working hours" is a parameter, not an assumption. A 09:00-18:00 Mon-Fri
    default fits a full-time office contract and fits little else. Set
    --days/--start/--end (and --off-dates for leave, holidays, non-working days)
    to the actual contract before reading anything into the split.

  * Local git author timestamps are recorded but flagged: they come from the
    committer's own clock and can be set to any value. GitHub's repository
    creation and push events are server-side and are collected separately via
    `gh` when available. Where the two disagree, the server-side record is the
    stronger evidence and the report says so.

  * The method section is emitted into the report itself, so the output can be
    handed to someone who did not run it and still be checked.

Usage
    python tools/delivery_log.py                          # default 09:00-18:00, Mon-Fri
    python tools/delivery_log.py --start 8 --end 16 --days 2,3,4,5
    python tools/delivery_log.py --off-dates 2026-07-06,2026-07-08
    python tools/delivery_log.py --out docs/delivery-log.md --json docs/delivery-log.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEP = "\x1f"          # unit separator - safe against any character in a subject line
REC = "\x1e"          # record separator

DOW_NAME = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}

# Commit-subject prefixes -> the deliverable they belong to. Anything unmatched
# is grouped under "Other", never silently dropped.
STREAMS = [
    ("Pay equity",            r"pay[- ]equity|gender pay|art\.? ?4|job evaluation|isf|cats|"
                              r"salary|shift-toeslag|generatiepact|grade[- ]assignment"),
    ("Skills Intelligence",   r"skills? dashboard|skills? assessment|path b|skill gap|"
                              r"competenc|skillproficiency|proficiency"),
    ("Matching engine",       r"match|search index|title[- ]column|title mapping"),
    ("Benefits benchmarking", r"benefit"),
    ("Job architecture",      r"job famil|career|organigram|org hierarch|reference library|"
                              r"grade|esco|isco|job architecture|nine[- ]?box|9-box"),
    ("Reporting & export",    r"export|report|excel|pdf|dutch|language|roadmap|plan\b"),
    ("Data quality",          r"data quality|validation|loader|repository|supabase|migration"),
    ("UI & theme",            r"^ui\b|theme|mobile|layout|styling|garbled"),
    ("Infrastructure",        r"test|ci\b|deploy|requirements|packaging|refactor|gitignore|"
                              r"syntax error|f-string"),
]

# GitHub web-UI bulk operations: seeding the repository from an existing codebase,
# not authoring it. Kept in every total, but reported separately, because an
# adversarial reader will otherwise (correctly) point out that a commit called
# "Add files via upload" is not a unit of development work.
ADMIN_RE = re.compile(
    r"^(add files via upload|delete\s|create git\b|initial commit|merge\s|"
    r"update [\w/.\-]+$|create [\w/.\-]+$)", re.I)


# --------------------------------------------------------------------- collect
def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def collect_commits() -> list[dict]:
    """Every commit on every branch, with both author and committer dates."""
    fmt = SEP.join(["%H", "%an", "%ae", "%ad", "%cd", "%s"]) + REC
    raw = git("log", "--all", "--no-merges", f"--pretty=format:{fmt}",
              "--date=format:%Y-%m-%d %H:%M:%S %u")
    out = []
    for rec in raw.split(REC):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split(SEP)
        if len(parts) != 6:
            continue
        sha, name, email, adate, cdate, subject = parts
        d, t, dow = adate.split(" ")
        out.append({
            "sha": sha[:10], "author": name, "email": email,
            "date": d, "time": t, "hour": int(t[:2]), "dow": int(dow),
            "committer_date": cdate, "subject": subject,
        })
    return out


def github_facts() -> dict | None:
    """Server-side timestamps. These do not come from the committer's clock."""
    url = git("remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[:/]+([^/]+)/([^/.]+)", url)
    if not m:
        return None
    slug = f"{m.group(1)}/{m.group(2)}"
    r = subprocess.run(
        ["gh", "api", f"repos/{slug}", "--jq",
         "{created_at,pushed_at,updated_at,visibility,default_branch}"],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        return {"slug": slug, "error": r.stderr.strip()[:200] or "gh unavailable"}
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"slug": slug, "error": "unparseable gh response"}
    data["slug"] = slug
    return data


# ---------------------------------------------------------------------- classify
def stream_for(subject: str) -> str:
    s = subject.lower()
    for name, pattern in STREAMS:
        if re.search(pattern, s):
            return name
    return "Other"


def is_working_time(c: dict, days: set[int], start: int, end: int,
                    off_dates: set[str]) -> bool:
    if c["date"] in off_dates:
        return False
    return c["dow"] in days and start <= c["hour"] < end


# ------------------------------------------------------------------------ report
def build(commits: list[dict], gh: dict | None, days: set[int], start: int,
          end: int, off_dates: set[str]) -> tuple[str, dict]:
    total = len(commits)
    for c in commits:
        c["working"] = is_working_time(c, days, start, end, off_dates)
        # Admin commits get their own stream so bulk file operations can't crowd
        # out the actual deliverables in the table someone will read first.
        c["kind"] = "admin" if ADMIN_RE.match(c["subject"]) else "authored"
        c["stream"] = ("Repository administration" if c["kind"] == "admin"
                       else stream_for(c["subject"]))

    inside = [c for c in commits if c["working"]]
    outside = [c for c in commits if not c["working"]]
    admin = [c for c in commits if c["kind"] == "admin"]
    authored = [c for c in commits if c["kind"] == "authored"]
    dates = sorted({c["date"] for c in commits})
    window = f"{sorted(DOW_NAME[d] for d in days)} {start:02d}:00-{end:02d}:00"

    L: list[str] = []
    add = L.append

    add("# Jobsy — delivery log")
    add("")
    add(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} from the git history "
        f"of `{gh['slug'] if gh and 'slug' in gh else 'this repository'}`.")
    add("")

    # ---- server-side facts first: the part that is not self-reported
    add("## Independently timestamped facts")
    add("")
    if gh and "error" not in gh:
        add("From the GitHub API — these are server-side and are **not** derived from "
            "the committer's local clock:")
        add("")
        add("| Fact | Value |")
        add("| --- | --- |")
        add(f"| Repository | `{gh['slug']}` |")
        add(f"| Created | **{gh.get('created_at','?')}** |")
        add(f"| Last push | **{gh.get('pushed_at','?')}** |")
        add(f"| Visibility | {gh.get('visibility','?')} |")
    else:
        add("_GitHub API not reachable when this was generated, so no server-side "
            "timestamps are included. Local git dates below are self-reported._")
        if gh and gh.get("error"):
            add("")
            add(f"> {gh['error']}")
    add("")

    # ---- the complete record
    add("## The complete record")
    add("")
    add(f"- **{total} commits** across **{len(dates)} active days**")
    add(f"- First: **{dates[0]}** · Last: **{dates[-1]}**")
    add("")
    add("Contributors, as recorded in the commit metadata:")
    add("")
    add("| Author | Commits |")
    add("| --- | ---: |")
    for (name, email), n in Counter((c["author"], c["email"]) for c in commits).most_common():
        add(f"| {name} &lt;{email}&gt; | {n} |")
    add("")

    # ---- the split, with both sides always shown
    add("## Split against the stated working pattern")
    add("")
    add(f"Working pattern applied: **{window}**"
        + (f", excluding {len(off_dates)} specified non-working date(s)" if off_dates else "")
        + ".")
    add("")
    add("| | Commits | Share |")
    add("| --- | ---: | ---: |")
    add(f"| Inside working hours | {len(inside)} | {len(inside)/total*100:.1f}% |")
    add(f"| **Outside working hours** | **{len(outside)}** | **{len(outside)/total*100:.1f}%** |")
    add(f"| Total | {total} | 100% |")
    add("")
    add("> Both rows are reported deliberately. This split is only as meaningful as "
        "the working pattern above; if that pattern does not match the actual "
        "contract, re-run with the correct one rather than reading anything into "
        "these figures.")
    add("")

    add("### Repository administration vs authored development")
    add("")
    add("Not every commit is a unit of work. Seeding a repository from an existing "
        "codebase produces bulk `Add files via upload` / `Delete <file>` commits "
        "through the GitHub web interface. They are counted everywhere in this "
        "report, and separated here so the distinction is explicit rather than "
        "left for someone else to point out.")
    add("")
    add("| | Commits | Outside hours | Share outside |")
    add("| --- | ---: | ---: | ---: |")
    for label, grp in (("Repository administration", admin),
                       ("Authored development", authored),
                       ("**All commits**", commits)):
        if not grp:
            continue
        o = sum(1 for c in grp if not c["working"])
        add(f"| {label} | {len(grp)} | {o} | {o/len(grp)*100:.1f}% |")
    add("")
    if authored:
        ad = sorted(c["date"] for c in authored)
        add(f"Authored development in this repository runs **{ad[0]} to {ad[-1]}**. "
            f"Anything written before {ad[0]} entered the repository as a bulk upload, "
            f"so git carries no authorship dates for it; earlier provenance has to come "
            f"from outside this repository.")
        add("")

    add("### By day of week")
    add("")
    add("| Day | Total | Outside hours |")
    add("| --- | ---: | ---: |")
    per_dow = Counter(c["dow"] for c in commits)
    out_dow = Counter(c["dow"] for c in outside)
    for d in range(1, 8):
        if per_dow[d]:
            mark = "" if d in days else " *(non-working day)*"
            add(f"| {DOW_NAME[d]}{mark} | {per_dow[d]} | {out_dow[d]} |")
    add("")

    add("### By hour")
    add("")
    add("| Hour | Total | Outside hours |")
    add("| --- | ---: | ---: |")
    per_h = Counter(c["hour"] for c in commits)
    out_h = Counter(c["hour"] for c in outside)
    for h in range(24):
        if per_h[h]:
            add(f"| {h:02d}:00 | {per_h[h]} | {out_h[h]} |")
    add("")

    # ---- deliverables
    add("## Deliverables")
    add("")
    add("Commits grouped into workstreams by subject line. Each row shows the full "
        "count and the portion falling outside the stated working pattern.")
    add("")
    add("| Deliverable | First | Last | Commits | Outside hours |")
    add("| --- | --- | --- | ---: | ---: |")
    by_stream: dict[str, list[dict]] = defaultdict(list)
    for c in commits:
        by_stream[c["stream"]].append(c)
    for name, cs in sorted(by_stream.items(), key=lambda kv: -len(kv[1])):
        ds = sorted(c["date"] for c in cs)
        n_out = sum(1 for c in cs if not c["working"])
        add(f"| {name} | {ds[0]} | {ds[-1]} | {len(cs)} | {n_out} |")
    add("")

    # ---- full chronological appendix
    add("## Appendix — every commit, in order")
    add("")
    add("| Date | Time | Day | Hours | Kind | Deliverable | Subject | SHA |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for c in sorted(commits, key=lambda c: (c["date"], c["time"])):
        flag = "inside" if c["working"] else "**outside**"
        subj = c["subject"].replace("|", "\\|")[:90]
        add(f"| {c['date']} | {c['time'][:5]} | {DOW_NAME[c['dow']]} | {flag} | "
            f"{c['kind']} | {c['stream']} | {subj} | `{c['sha']}` |")
    add("")

    # ---- method, emitted so the report can be checked by someone who didn't run it
    add("## Method and limitations")
    add("")
    add("1. Commits are read with `git log --all --no-merges`. Every commit on every "
        "branch is included; none are filtered out of the totals.")
    add("2. Times shown are **git author timestamps in the committing machine's local "
        "timezone**. These are written by the committer's own clock and can be set "
        "to an arbitrary value. They are not independent evidence on their own.")
    add("3. The GitHub creation and push timestamps in the first section are recorded "
        "server-side and are the stronger record where the two disagree.")
    add("4. Workstream grouping is a keyword match on commit subjects and is "
        "presentational only; it does not affect any count. Unmatched commits are "
        "grouped as \"Other\" rather than dropped.")
    add("5. The working-hours split reflects the pattern stated above and nothing "
        "else. It carries no view on what any contract requires.")
    add("")
    add(f"Reproduce with: `python tools/delivery_log.py --start {start} --end {end} "
        f"--days {','.join(str(d) for d in sorted(days))}"
        + (f" --off-dates {','.join(sorted(off_dates))}" if off_dates else "") + "`")
    add("")

    data = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "github": gh,
        "pattern": {"days": sorted(days), "start": start, "end": end,
                    "off_dates": sorted(off_dates)},
        "totals": {"commits": total, "active_days": len(dates),
                   "inside": len(inside), "outside": len(outside),
                   "first": dates[0], "last": dates[-1],
                   "admin": len(admin), "authored": len(authored),
                   "authored_outside": sum(1 for c in authored if not c["working"]),
                   "authored_first": (min(c["date"] for c in authored) if authored else None),
                   "authored_last": (max(c["date"] for c in authored) if authored else None)},
        "streams": {k: {"commits": len(v),
                        "outside": sum(1 for c in v if not c["working"]),
                        "first": min(c["date"] for c in v),
                        "last": max(c["date"] for c in v)}
                    for k, v in by_stream.items()},
        "commits": commits,
    }
    return "\n".join(L), data


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--days", default="1,2,3,4,5",
                   help="Contracted working days, 1=Mon..7=Sun (default 1,2,3,4,5)")
    p.add_argument("--start", type=int, default=9, help="Working day start hour (default 9)")
    p.add_argument("--end", type=int, default=18, help="Working day end hour, exclusive (default 18)")
    p.add_argument("--off-dates", default="",
                   help="Comma-separated YYYY-MM-DD dates that were leave/holiday/non-working")
    p.add_argument("--out", default="docs/delivery-log.md", help="Markdown output path")
    p.add_argument("--json", dest="json_out", default="", help="Optional JSON output path")
    a = p.parse_args()

    days = {int(d) for d in a.days.split(",") if d.strip()}
    off = {d.strip() for d in a.off_dates.split(",") if d.strip()}

    commits = collect_commits()
    if not commits:
        raise SystemExit("No commits found — is this a git repository?")

    md, data = build(commits, github_facts(), days, a.start, a.end, off)

    out = REPO / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out}  ({len(commits)} commits, "
          f"{data['totals']['outside']} outside the stated pattern)")

    if a.json_out:
        j = REPO / a.json_out
        j.parent.mkdir(parents=True, exist_ok=True)
        j.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"wrote {j}")


if __name__ == "__main__":
    main()

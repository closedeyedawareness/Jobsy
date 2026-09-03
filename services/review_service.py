"""
review_service.py — the return path. An approved match becomes a mapping.

Until now the matching workflow ran one way. A title came in, the pipeline
resolved it, somebody looked at the low-confidence rows and decided what they
meant — and that decision died with the browser session. The next upload of the
same roster did exactly the same work and asked exactly the same questions. The
library could not improve from being used, because nothing was ever written back
to it.

This is that edge. Approving a match writes a TitleMapping row, so the next run
resolves the same title deterministically — at the top of the pipeline instead
of the bottom of it.

THREE THINGS THIS MODULE REFUSES TO DO

1. **It does not write with the secret key.** The library has been read-only from
   the app, so the credential question never arose; a write makes it arise. This
   takes the signed-in user's own client, which means 0008's write policy
   (`app.can_write_org`) decides, the trigger records `changed_by`, and a viewer
   cannot write no matter what the interface offers. Passing the secret key here
   would work and would prove nothing.

2. **It does not invent a role.** `title_mapping.job_id` is a foreign key onto
   `jobs (org_id, job_id)`. The plan checks the role exists before sending
   anything, so a mistyped id comes back as a sentence rather than a 400 from
   PostgREST — but the database is still the thing that enforces it.

3. **It does not overwrite a mapping silently.** The unique key is
   `(org_id, country, existing_title)`, so approving a title that is already
   mapped is a REMAP, not an insert. That is a legitimate act — the first answer
   can be wrong — but it is a different act, and the plan says which is which
   before anything is written.

WHAT THE ROW SAYS ABOUT ITSELF

`source` carries content provenance, not the mechanism: "Approved in review by
<who>". That column has been clobbered once before by a writer that put its own
label over the workbook's citations, and the lesson stuck — here the content
genuinely originates in a review, so saying so is the accurate value rather than
a label. `updated_at` is the moment the content was decided, which for a row born
now is now. Both are what the Data Quality freshness panel reads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Optional

__all__ = ["Approval", "PlannedWrite", "WritePlan", "WriteResult",
           "candidates", "plan_write_back", "apply_write_back", "writable_target"]

TABLE = "title_mapping"
CONFLICT = "org_id,country,existing_title"


@dataclass(frozen=True)
class Approval:
    """A human decision: this input title means this role."""
    existing_title: str
    job_id: str


@dataclass(frozen=True)
class PlannedWrite:
    existing_title: str
    job_id: str
    action: str          # "insert" | "remap"
    was_job_id: Optional[str] = None


@dataclass
class WritePlan:
    """What would be written, and what would not, with the reason."""
    writes: list[PlannedWrite] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def inserts(self) -> int:
        return sum(1 for w in self.writes if w.action == "insert")

    @property
    def remaps(self) -> int:
        return sum(1 for w in self.writes if w.action == "remap")

    def summary(self) -> str:
        parts = []
        if self.inserts:
            parts.append(f"{self.inserts} new mapping(s)")
        if self.remaps:
            parts.append(f"{self.remaps} remapped")
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped")
        return ", ".join(parts) if parts else "nothing to write"


@dataclass
class WriteResult:
    written: int = 0
    plan: Optional[WritePlan] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def writable_target(client, org_id: str) -> tuple[bool, str]:
    """Can approvals be written to this organisation at all?

    Found by probing the real policy rather than by reading the DDL, and it is
    not what I expected:

        can_write_org(org) = is_org_admin(org) AND NOT is_library_source(org)

    The shared reference library is readable by every tenant *because* it is the
    library source, and writable by nobody through the app. That is deliberate —
    one library, many clients, and no client may edit what the others read. So an
    approval is a CLIENT-specific mapping and belongs in the client's own
    organisation, never in the library it inherits.

    Today `default` is the only organisation and it IS the library source, which
    means there is nowhere for an approval to go yet. Asking the database rather
    than assuming keeps this honest when that changes: the moment a real client
    org exists, this returns True for it with no code change.
    """
    if client is None:
        return False, ("Not signed in, so there is no credential to write with.")
    if not org_id:
        return False, "No active client organisation."
    try:
        resp = (client.table("orgs").select("slug,name,is_library_source")
                .eq("id", org_id).limit(1).execute())
        rows = getattr(resp, "data", None) or []
    except Exception as exc:
        return False, f"Could not check the organisation: {type(exc).__name__}: {exc}"
    if not rows:
        return False, "That organisation is not visible to this account."
    row = rows[0]
    if row.get("is_library_source"):
        return False, (
            f"“{row.get('name') or row.get('slug')}” is the shared reference library, and the "
            f"write policy forbids editing it from the app — every client reads it, so no "
            f"client may change it. Approvals belong to a client's own organisation. "
            f"There isn't one yet.")
    return True, ""


def candidates(results: Iterable) -> list:
    """The match results where a mapping would actually change the next run.

    An exact hit already resolves at the top of the pipeline; writing a mapping
    for it adds a row and no information. What is worth a decision is everything
    the pipeline was unsure about — flagged for review — and everything it could
    not place at all.
    """
    out = []
    for r in results:
        if getattr(r, "requires_review", False) or not getattr(r, "matched", False):
            out.append(r)
    return out


def plan_write_back(approvals: Iterable[Approval], repo, *, country: str = "NL") -> WritePlan:
    """Decide what each approval would do, before anything is sent.

    Mirrors the constraints the database will apply, so a bad approval is a
    sentence on screen instead of a rejected request — without pretending the
    check here is the enforcement.
    """
    plan = WritePlan()
    from core.utils import normalize_title

    jobs = getattr(repo, "jobs", {}) or {}
    # Repository keys title_mapping by normalize_title() and stores the job id.
    # Asking "is this already mapped" with a different normaliser would answer a
    # different question from the one the pipeline asks at lookup time, so this
    # uses the same function rather than one that merely resembles it.
    current = dict(getattr(repo, "title_mapping", {}) or {})
    seen: set[str] = set()

    for a in approvals:
        title = (a.existing_title or "").strip()
        job_id = (a.job_id or "").strip()

        if not title:
            plan.skipped.append(("(blank)", "no title"))
            continue
        if not job_id:
            plan.skipped.append((title, "no role chosen"))
            continue
        if job_id not in jobs:
            plan.skipped.append((title, f"{job_id} is not a role in this library"))
            continue

        key = normalize_title(title)
        if key in seen:
            plan.skipped.append((title, "approved twice in one batch"))
            continue
        seen.add(key)

        was_id = current.get(key)
        if was_id == job_id:
            plan.skipped.append((title, "already mapped to that role"))
            continue

        plan.writes.append(PlannedWrite(
            existing_title=title, job_id=job_id,
            action="remap" if was_id else "insert",
            was_job_id=was_id,
        ))
    return plan


def _rows(plan: WritePlan, org_id: str, actor: str, country: str) -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    today = date.today().isoformat()
    who = actor or "review"
    return [{
        "org_id": org_id,
        "country": country,
        "existing_title": w.existing_title,
        "job_id": w.job_id,
        "status": "active",
        "owner": who,
        # Content provenance: where this mapping came FROM, not which run wrote it.
        "source": f"Approved in review by {who}",
        "effective_from": today,
        "updated_at": now,
        "updated_by": who,
    } for w in plan.writes]


def apply_write_back(client, org_id: str, plan: WritePlan, *,
                     actor: str = "", country: str = "NL") -> WriteResult:
    """Send the plan. The client must be the signed-in user's own.

    Returns rather than raises, because this is called from a button: the page
    has to be able to say what happened either way. A refusal by the write
    policy arrives here as an error string, which is the correct outcome for a
    viewer and must be shown, not swallowed.
    """
    if client is None:
        return WriteResult(plan=plan, error=(
            "Not signed in, so there is no credential to write with. The library "
            "is written as you, not by the application."))
    if not org_id:
        return WriteResult(plan=plan, error="No active client organisation to write to.")
    if not plan.writes:
        return WriteResult(plan=plan, written=0)

    try:
        client.table(TABLE).upsert(
            _rows(plan, org_id, actor, country), on_conflict=CONFLICT
        ).execute()
    except Exception as exc:
        return WriteResult(plan=plan, error=f"{type(exc).__name__}: {exc}")
    return WriteResult(plan=plan, written=len(plan.writes))

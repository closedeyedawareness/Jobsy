"""
tests/test_career_ladder.py

Structural invariants for the CareerPaths ladder.

These exist because the ladder failed silently once: 21 of 80 steps pointed at
Chief Executive Officer, because CEO is defined purely by generic leadership
skills and is therefore the nearest neighbour of every senior role in skill
space. Nothing caught it. These tests catch it.

They assert structure, not opinion — a step must go up, must not loop, and a
head-of-function must not skip its own C-level to land on the CEO.
"""
from pathlib import Path

import pytest

from core.catalog import Catalog

WORKBOOK = Path(__file__).resolve().parent.parent / "jobsy_reference_library.xlsx"
LEVEL_ORDER = {"Junior": 1, "Medior": 2, "Senior": 3, "Lead": 4}

# The only two roles evidenced as progressing into the chief executive seat.
CEO_PREDECESSORS = {"Chief Operating Officer", "Chief Financial Officer"}


@pytest.fixture(scope="module")
def repo():
    if not WORKBOOK.exists():
        pytest.skip("reference workbook not present")
    cat = Catalog(str(WORKBOOK))
    cat.load()
    return cat.repository


def _title(repo, job_id):
    job = repo.jobs.get(job_id)
    return job.standard_title if job else None


def test_only_evidenced_roles_progress_to_ceo(repo):
    """The fallback that started this: everything senior pointing at CEO."""
    ceo_ids = {jid for jid, j in repo.jobs.items()
               if j.standard_title == "Chief Executive Officer"}
    offenders = sorted(
        _title(repo, jid) for jid, step in repo.career_paths.items()
        if step.next_job_id in ceo_ids and _title(repo, jid) not in CEO_PREDECESSORS)
    assert offenders == [], (
        f"{len(offenders)} role(s) still default to Chief Executive Officer: {offenders}. "
        "A step into the CEO seat needs an evidence base; see tools/fix_career_ladder.py.")


def test_a_head_of_function_does_not_skip_its_own_c_level(repo):
    """Head of X progresses to the C-level of X, never straight past it."""
    bad = []
    for jid, step in repo.career_paths.items():
        title = _title(repo, jid) or ""
        if not (title.startswith("Head of") or title in ("Engineering Lead", "General Counsel")):
            continue
        if not step.next_job_id:
            continue
        nxt = repo.jobs.get(step.next_job_id)
        if nxt and not nxt.standard_title.startswith("Chief"):
            bad.append((title, nxt.standard_title))
    assert bad == [], f"head-of-function roles not progressing to a C-level: {bad}"


def test_no_step_goes_down_a_level(repo):
    downward = []
    for jid, step in repo.career_paths.items():
        if not step.next_job_id:
            continue
        a, b = repo.jobs.get(jid), repo.jobs.get(step.next_job_id)
        if not a or not b:
            continue
        if LEVEL_ORDER.get(b.level, 0) < LEVEL_ORDER.get(a.level, 0):
            downward.append((a.standard_title, a.level, b.standard_title, b.level))
    assert downward == [], f"career steps that go backwards: {downward}"


def test_no_self_loops(repo):
    loops = [_title(repo, jid) for jid, step in repo.career_paths.items()
             if step.next_job_id == jid]
    assert loops == [], f"roles whose next step is themselves: {loops}"


def test_no_cycles(repo):
    """Following next_job_id must always terminate."""
    for start in repo.career_paths:
        seen, cur = [], start
        while cur:
            if cur in seen:
                pytest.fail(f"cycle: {' -> '.join(_title(repo, j) or j for j in seen + [cur])}")
            seen.append(cur)
            step = repo.career_paths.get(cur)
            cur = step.next_job_id if step else None
            if len(seen) > len(repo.jobs) + 1:
                pytest.fail(f"runaway chain from {_title(repo, start)}")


def test_every_next_job_id_resolves(repo):
    dangling = [(_title(repo, jid), step.next_job_id)
                for jid, step in repo.career_paths.items()
                if step.next_job_id and step.next_job_id not in repo.jobs]
    assert dangling == [], f"next_job_id values with no matching job: {dangling}"


def test_terminal_roles_are_deliberate_not_missing(repo):
    """A blank next step is a decision. The C-suite is where they belong."""
    terminal = sorted(_title(repo, jid) for jid, step in repo.career_paths.items()
                      if not step.next_job_id)
    assert terminal, "no terminal roles at all — the ladder cannot be a DAG"
    non_chief = [t for t in terminal if t and not t.startswith("Chief")]
    assert non_chief == [], (
        f"non-C-level roles with no onward step: {non_chief}. "
        "Either give them a step or record why they terminate.")


def test_ceo_itself_is_terminal(repo):
    ceo = next((jid for jid, j in repo.jobs.items()
                if j.standard_title == "Chief Executive Officer"), None)
    assert ceo, "no Chief Executive Officer in the library"
    step = repo.career_paths.get(ceo)
    assert step is None or not step.next_job_id, "the CEO has no onward internal step"

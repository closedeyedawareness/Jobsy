"""
The return path: an approved match becomes a mapping.

The test that carries the feature is `test_an_approval_changes_the_next_run` —
everything else guards an edge. Without that one, this module writes rows that
nobody has shown make the next match better, which is the whole claim.

Driven through a fake client, so the upsert's shape, its conflict target and its
governance columns are all checked without touching a real library.
"""

import pandas as pd
import pytest

from core.repository import Repository
from services.matching_service import MatchingService
from services.review_service import (
    Approval, apply_write_back, candidates, plan_write_back, writable_target,
)


class _FakeTable:
    def __init__(self, log, raises=None):
        self.log, self.raises = log, raises

    def upsert(self, rows, on_conflict=None):
        self.log.append({"rows": rows, "on_conflict": on_conflict})
        return self

    def execute(self):
        if self.raises:
            raise self.raises
        return type("Resp", (), {"data": self.log[-1]["rows"]})()


class _FakeClient:
    def __init__(self, raises=None):
        self.log, self.raises = [], raises

    def table(self, name):
        self.log.append({"table": name})
        return _FakeTable(self.log, self.raises)


class _Result:
    """Just the fields review_service reads off a MatchResult."""
    def __init__(self, input_title, matched=True, requires_review=False, job_id=None):
        self.input_title, self.matched = input_title, matched
        self.requires_review, self.job_id = requires_review, job_id


@pytest.fixture
def repo(sample_sheets):
    return Repository(sample_sheets, validate=False)


# ── which rows are worth a decision ──────────────────────────────────────────

def test_only_the_rows_a_mapping_would_change_are_offered():
    rows = [
        _Result("HR Business Partner"),                              # exact, resolves already
        _Result("HRBP-ish", requires_review=True),                   # low confidence
        _Result("Chief Vibes Officer", matched=False),               # nothing found
    ]
    titles = [r.input_title for r in candidates(rows)]
    assert titles == ["HRBP-ish", "Chief Vibes Officer"]


def test_an_exact_match_is_not_offered_because_a_mapping_adds_nothing():
    assert candidates([_Result("HR Business Partner")]) == []


# ── the plan, before anything is sent ────────────────────────────────────────

def test_a_new_title_plans_an_insert(repo):
    plan = plan_write_back([Approval("People Person", "J-HRBP")], repo)
    assert plan.inserts == 1 and plan.remaps == 0
    assert plan.writes[0].job_id == "J-HRBP"


def test_a_title_already_mapped_elsewhere_plans_a_remap(repo):
    # 'HRBP' is mapped to J-HRBP in the fixture library.
    plan = plan_write_back([Approval("HRBP", "J-SE")], repo)
    assert plan.remaps == 1 and plan.inserts == 0
    assert plan.writes[0].was_job_id == "J-HRBP"


def test_approving_what_is_already_true_writes_nothing(repo):
    plan = plan_write_back([Approval("HRBP", "J-HRBP")], repo)
    assert plan.writes == []
    assert plan.skipped == [("HRBP", "already mapped to that role")]


def test_the_already_mapped_check_uses_the_pipeline_s_own_normaliser(repo):
    """'HRBP,' and 'HRBP' are one key to the matcher — punctuation goes. A check
    that merely lower-cased would read 'hrbp,' as new, plan an insert, and put a
    second row under a different spelling of a title that is already mapped.

    ('H R B P' is NOT the same key, and should not be: the normaliser keeps word
    boundaries. The first version of this test asserted it was, which was the
    test being wrong rather than the code.)"""
    plan = plan_write_back([Approval("  HRBP,  ", "J-HRBP")], repo)
    assert plan.writes == [] and plan.skipped[0][1] == "already mapped to that role"

    spaced = plan_write_back([Approval("H R B P", "J-HRBP")], repo)
    assert spaced.inserts == 1


def test_a_role_that_is_not_in_the_library_is_refused_by_name(repo):
    plan = plan_write_back([Approval("Whatever", "J-NOPE")], repo)
    assert plan.writes == []
    assert "not a role in this library" in plan.skipped[0][1]


def test_a_blank_title_or_an_unchosen_role_is_skipped_with_a_reason(repo):
    plan = plan_write_back([Approval("", "J-SE"), Approval("Something", "")], repo)
    assert len(plan.skipped) == 2
    assert plan.skipped[0][1] == "no title"
    assert plan.skipped[1][1] == "no role chosen"


def test_the_same_title_twice_in_one_batch_is_written_once(repo):
    plan = plan_write_back(
        [Approval("Developer II", "J-SE"), Approval("developer ii", "J-JSE")], repo)
    assert len(plan.writes) == 1
    assert plan.skipped[0][1] == "approved twice in one batch"


def test_the_summary_reads_as_a_sentence(repo):
    plan = plan_write_back(
        [Approval("A Person", "J-SE"), Approval("HRBP", "J-SE"), Approval("", "J-SE")], repo)
    assert plan.summary() == "1 new mapping(s), 1 remapped, 1 skipped"


# ── the write itself ─────────────────────────────────────────────────────────

def test_the_upsert_targets_the_unique_key_the_table_actually_has(repo):
    client = _FakeClient()
    plan = plan_write_back([Approval("People Person", "J-HRBP")], repo)
    res = apply_write_back(client, "org-1", plan, actor="you@example.com")
    assert res.ok and res.written == 1
    sent = [e for e in client.log if "rows" in e][0]
    # (org_id, country, existing_title) — not existing_title alone, which would
    # collide across countries the moment a second one exists.
    assert sent["on_conflict"] == "org_id,country,existing_title"


def test_the_row_says_where_it_came_from_and_who_decided(repo):
    client = _FakeClient()
    plan = plan_write_back([Approval("People Person", "J-HRBP")], repo)
    apply_write_back(client, "org-1", plan, actor="you@example.com")
    row = [e for e in client.log if "rows" in e][0]["rows"][0]
    assert row["existing_title"] == "People Person" and row["job_id"] == "J-HRBP"
    assert row["org_id"] == "org-1" and row["country"] == "NL"
    assert row["status"] == "active"
    assert row["source"] == "Approved in review by you@example.com"
    assert row["updated_by"] == "you@example.com"
    assert row["effective_from"] and row["updated_at"]


def test_no_client_means_no_write_and_a_sentence_about_why(repo):
    plan = plan_write_back([Approval("People Person", "J-HRBP")], repo)
    res = apply_write_back(None, "org-1", plan)
    assert not res.ok and "written as you" in res.error


def test_no_active_org_means_no_write(repo):
    plan = plan_write_back([Approval("People Person", "J-HRBP")], repo)
    res = apply_write_back(_FakeClient(), "", plan)
    assert not res.ok and "organisation" in res.error


def test_a_policy_refusal_is_reported_not_swallowed(repo):
    """A viewer hitting the button must see the refusal. Swallowing it would
    show a success toast over a library that did not change."""
    client = _FakeClient(raises=RuntimeError("new row violates row-level security policy"))
    plan = plan_write_back([Approval("People Person", "J-HRBP")], repo)
    res = apply_write_back(client, "org-1", plan)
    assert not res.ok and "row-level security" in res.error
    assert res.written == 0


def test_an_empty_plan_sends_nothing_at_all(repo):
    client = _FakeClient()
    plan = plan_write_back([Approval("HRBP", "J-HRBP")], repo)   # a no-op approval
    res = apply_write_back(client, "org-1", plan)
    assert res.ok and res.written == 0
    assert not [e for e in client.log if "rows" in e]


# ── the claim ────────────────────────────────────────────────────────────────

def test_an_approval_changes_the_next_run(sample_sheets):
    """THE POINT. A title the pipeline could not place resolves deterministically
    once the approval is in the library — which is what "the library improves
    from being used" has to mean to be worth writing."""
    repo = Repository(sample_sheets, validate=False)
    service = MatchingService(repo, index=repo.index)

    before = service.match("People Person")
    assert not before.matched or before.requires_review

    # the approval, as the write-back would leave it in the library
    titles = sample_sheets["titles"].copy()
    plan = plan_write_back([Approval("People Person", "J-HRBP")], repo)
    assert plan.inserts == 1
    titles = pd.concat([titles, pd.DataFrame(
        [{"ExistingTitle": w.existing_title, "JobID": w.job_id} for w in plan.writes]
    )], ignore_index=True)

    reloaded = dict(sample_sheets); reloaded["titles"] = titles
    repo2 = Repository(reloaded, validate=False)
    after = MatchingService(repo2, index=repo2.index).match("People Person")

    assert after.matched and after.job_id == "J-HRBP"
    assert after.confidence >= before.confidence
    assert not after.requires_review


# ── where an approval is allowed to go ───────────────────────────────────────
#
# Probing the live policy is what produced these: the write is refused on any
# org that is a library source, which is every org there is today.

class _OrgsClient:
    """Enough of the client to answer the one question writable_target asks."""

    def __init__(self, rows, raises=None):
        self._rows, self._raises = rows, raises

    def table(self, name):
        assert name == "orgs"
        return self

    def select(self, *_a, **_k): return self
    def eq(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self

    def execute(self):
        if self._raises:
            raise self._raises
        return type("Resp", (), {"data": self._rows})()


def test_the_shared_library_is_not_a_write_target_and_says_why():
    ok, why = writable_target(
        _OrgsClient([{"slug": "default", "name": "Default organisation",
                      "is_library_source": True}]), "org-1")
    assert not ok
    assert "every client reads it" in why


def test_a_client_organisation_is_a_write_target():
    ok, why = writable_target(
        _OrgsClient([{"slug": "northwind", "name": "Northwind BV",
                      "is_library_source": False}]), "org-2")
    assert ok and why == ""


def test_an_invisible_organisation_is_not_a_write_target():
    ok, why = writable_target(_OrgsClient([]), "org-3")
    assert not ok and "not visible" in why


def test_without_a_client_or_an_org_there_is_no_target():
    assert writable_target(None, "org-1")[0] is False
    assert writable_target(_OrgsClient([]), "")[0] is False


def test_a_failed_check_does_not_claim_the_target_is_writable():
    ok, why = writable_target(_OrgsClient([], raises=RuntimeError("boom")), "org-1")
    assert not ok and "Could not check" in why

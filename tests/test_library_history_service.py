"""
Reading the library's audit trail.

Driven through a fake client, like tests/test_db_loader.py, so the query shape
and the rendering are testable without a database. The fake answers exactly what
PostgREST answers — a list of dicts with jsonb columns already parsed — because
the last time a fake was more agreeable than the database it cost a parity run.
"""

import pandas as pd
import pytest

from services.library_history_service import (
    changed_fields, recent_changes, summarise, _short_actor,
)


class _FakeQuery:
    def __init__(self, rows, log):
        self._rows, self._log = rows, log
        self._limit = None

    def select(self, cols):
        self._log["select"] = cols
        return self

    def eq(self, col, val):
        self._log.setdefault("eq", []).append((col, val))
        return self

    def order(self, col, desc=False):
        self._log["order"] = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        return type("Resp", (), {"data": self._rows[: self._limit]})()


class _FakeClient:
    def __init__(self, rows=(), raises=None):
        self.rows, self.raises, self.log = list(rows), raises, {}

    def table(self, name):
        self.log["table"] = name
        if self.raises:
            raise self.raises
        return _FakeQuery(self.rows, self.log)


def _audit(**kw):
    row = {"changed_at": "2026-07-27T18:31:04+00:00", "table_name": "salary_bands",
           "action": "UPDATE", "changed_by": "service_role",
           "old_row": {"id": "1", "min": "40000"}, "new_row": {"id": "1", "min": "42000"}}
    row.update(kw)
    return row


# ── which fields moved ───────────────────────────────────────────────────────

def test_only_the_fields_that_actually_moved_are_named():
    assert changed_fields({"min": 1, "max": 9}, {"min": 2, "max": 9}) == ["min"]


def test_bookkeeping_columns_are_not_reported_as_changes():
    # A new revision_id on every write would make every row look edited.
    assert changed_fields({"id": "a", "revision_id": "r1", "min": 1},
                          {"id": "a", "revision_id": "r2", "min": 1}) == []


def test_a_field_that_appears_or_disappears_counts_as_a_change():
    assert changed_fields({"min": 1}, {"min": 1, "grade": "G3"}) == ["grade"]


def test_an_insert_or_delete_names_no_fields_because_the_action_says_it():
    assert changed_fields(None, {"min": 1}) == []
    assert changed_fields({"min": 1}, None) == []


# ── the query ────────────────────────────────────────────────────────────────

def test_the_trail_is_read_newest_first_and_capped():
    client = _FakeClient([_audit() for _ in range(5)])
    recent_changes(client, limit=3)
    assert client.log["table"] == "library_audit"
    assert client.log["order"] == ("changed_at", True)


def test_an_org_filters_the_trail_and_no_org_does_not():
    client = _FakeClient([_audit()])
    recent_changes(client, org_id="org-1")
    assert client.log["eq"] == [("org_id", "org-1")]

    client2 = _FakeClient([_audit()])
    recent_changes(client2)
    assert "eq" not in client2.log


def test_an_empty_trail_gives_an_empty_frame_not_an_error():
    assert recent_changes(_FakeClient([])).empty


def test_a_failing_query_does_not_take_the_page_down():
    # A history panel that raises is worse than one that says there is nothing.
    assert recent_changes(_FakeClient(raises=RuntimeError("no such table"))).empty


# ── rendering ────────────────────────────────────────────────────────────────

def test_a_change_row_reads_as_a_sentence():
    df = recent_changes(_FakeClient([_audit()]))
    row = df.iloc[0]
    assert row["When"] == "2026-07-27 18:31:04"
    assert row["Table"] == "salary_bands" and row["Action"] == "UPDATE"
    assert row["Fields changed"] == "min" and row["Field count"] == 1


def test_an_insert_shows_a_dash_rather_than_every_column():
    df = recent_changes(_FakeClient([_audit(action="INSERT", old_row=None)]))
    assert df.iloc[0]["Fields changed"] == "—"


def test_a_jwt_claims_blob_is_shown_as_who_not_as_json():
    assert _short_actor('{"role":"service_role","sub":"abc"}') == "abc"
    assert _short_actor('{"role":"authenticated"}') == "authenticated"
    assert _short_actor("postgres") == "postgres"
    assert _short_actor(None) == "—"


def test_unparseable_actor_text_is_truncated_rather_than_lost():
    assert _short_actor("{not json at all") == "{not json at all"


# ── summary ──────────────────────────────────────────────────────────────────

def test_the_summary_counts_actions_and_tables():
    rows = [_audit(), _audit(action="INSERT", table_name="jobs", old_row=None),
            _audit(action="DELETE", new_row=None)]
    s = summarise(recent_changes(_FakeClient(rows)))
    assert s == {"rows": 3, "tables": 2, "inserts": 1, "updates": 1, "deletes": 1,
                 "latest": "2026-07-27 18:31:04"}


def test_summarising_nothing_is_zeroes_not_a_crash():
    assert summarise(pd.DataFrame())["rows"] == 0

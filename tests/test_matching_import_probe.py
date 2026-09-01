"""
tests/test_matching_import_probe.py

Adversarial probe of services/matching_service.py and
services/library_import_service.py.

Each test either (a) demonstrates a real defect by encoding the CORRECT
expected behaviour and watching it fail against the current code, or (b)
is a regression guard for behaviour that was attacked and held up. Which is
which is stated in each test's docstring.
"""

from __future__ import annotations

import types

import pandas as pd
import pytest

import services.library_import_service as lis
from core.repository import Repository
from services.matching_service import MatchingService, MatchType


# =====================================================================
# PART 1 — the confirmed lead: `.count or 0) == 0` in library_import_service
#          around line 448, exercised through import_library()'s write path.
# =====================================================================

class _Resp:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _FakeQuery:
    """Minimal chainable stand-in for a supabase-py PostgrestQueryBuilder."""

    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self._op = None
        self._payload = None
        self._count_kw = None

    # chain methods — all return self except execute()
    def select(self, *a, **kw):
        self._op = "select"
        self._count_kw = kw.get("count")
        return self

    def eq(self, *a, **kw):
        return self

    def single(self):
        return self

    def limit(self, *a, **kw):
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._op = "upsert"
        self._payload = payload
        if self.client.fail_upsert_for == self.table_name:
            raise RuntimeError(f"simulated network failure writing {self.table_name}")
        self.client.upserts.append((self.table_name, list(payload)))
        return self

    def execute(self):
        if self._op == "insert":
            if self.table_name == "library_revisions":
                self.client.revision_inserts.append(self._payload)
                return _Resp(data=[{"id": self.client.revision_id}])
            return _Resp(data=[{"id": "generated"}])
        if self._op == "select":
            if self.table_name == "orgs":
                return _Resp(data={"id": self.client.org_id})
            # `data` and `count` are modelled SEPARATELY and on purpose. They
            # are two different channels: rows come back in the body, the count
            # comes from the Content-Range header, and the whole point of these
            # tests is what happens when the header is lost while the body is
            # fine. A fake that derived one from the other could not express
            # that, and would silently pass whichever implementation it happened
            # to match.
            rows = self.client.rows.get(self.table_name, [])
            return _Resp(data=list(rows),
                         count=self.client.counts.get(self.table_name, 0))
        if self._op == "upsert":
            return _Resp(data=self._payload)
        return _Resp(data=None)


class FakeSupabaseClient:
    """Records every upsert and revision insert; lets the test script the
    per-table `.count` PostgREST would normally report."""

    def __init__(self, counts=None, fail_upsert_for=None, rows=None):
        self.counts = counts or {}
        # What a `select ... limit 1` actually returns for each table. Defaults
        # to "one row exists wherever a count was scripted as nonzero, or where
        # the count was scripted as None" -- the None case being precisely
        # "the rows are there, the header telling us how many is not".
        if rows is None:
            rows = {t: ([{"id": "r-1"}] if (c is None or c) else [])
                    for t, c in self.counts.items()}
        self.rows = rows
        self.org_id = "11111111-1111-1111-1111-111111111111"
        self.revision_id = "22222222-2222-2222-2222-222222222222"
        self.upserts: list[tuple[str, list[dict]]] = []
        self.revision_inserts: list[dict] = []
        self.fail_upsert_for = fail_upsert_for

    def table(self, name):
        return _FakeQuery(self, name)


def _one_job_book():
    return {"Jobs": pd.DataFrame([{"JobID": "J-1", "StandardTitle": "Engineer"}])}


def _two_table_book():
    """A book that produces rows for two tables in dependency order, so a
    mid-loop upsert failure has an earlier table to have already committed."""
    return {
        "Jobs": pd.DataFrame([{"JobID": "J-1", "StandardTitle": "Engineer"}]),
        "Skills": pd.DataFrame([{"SkillID": "S-1", "SkillName": "Python"}]),
    }


@pytest.fixture(autouse=True)
def _bypass_validation_and_workbook_read(monkeypatch):
    """Isolate the write path under test from validation and disk I/O — both
    are covered elsewhere (test_validator.py, the dry-run tests)."""
    monkeypatch.setattr(lis, "Validator",
                         lambda: types.SimpleNamespace(validate=lambda *a, **k: None))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test000000000000000000")
    for var in ("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY"):
        monkeypatch.delenv(var, raising=False)


def _install_book(monkeypatch, book):
    monkeypatch.setattr(lis.pd, "read_excel", lambda path, sheet_name=None: book)


def _install_client(monkeypatch, client):
    import supabase as supabase_pkg
    monkeypatch.setattr(supabase_pkg, "create_client", lambda url, key: client)


def test_a_dropped_content_range_no_longer_condemns_a_successful_write(monkeypatch):
    """THE CONFIRMED LEAD (library_import_service.py ~L446-449).

    The upsert for 'jobs' succeeds (the fake client records the row). But the
    verification re-query's `.count` comes back None — exactly what happens
    when something between the app and Postgres drops PostgREST's
    Content-Range header, per tests/e2e/supabase_shim.py's own comment and
    the identical, already-fixed bug in services/country_service.py
    (`has_reference_data`, which deliberately uses `resp.data` instead of
    `resp.count` for this exact reason).

    `(None or 0) == 0` is True, so the table that just received a row is
    placed in `empty`, and import_library raises RuntimeError claiming data
    was NOT written and the caller should suspect a bad key.

    FIXED: the guard now asks for a row (`resp.data`) rather than a count, so a
    lost header cannot turn a successful import into a reported data loss. The
    guard itself is kept -- a genuinely empty table still raises, which
    test_the_empty_check_still_catches_a_genuinely_empty_table proves.
    """
    client = FakeSupabaseClient(counts={"jobs": None})  # header dropped
    _install_book(monkeypatch, _one_job_book())
    _install_client(monkeypatch, client)

    report = lis.import_library("fake.xlsx", write=True, org_slug="default")

    # The write really did happen -- so the guard had nothing to complain about.
    wrote_the_row = any(t == "jobs" and rows for t, rows in client.upserts)
    assert wrote_the_row, "setup bug: the row was never even sent"
    assert report is not None, (
        "import_library did not return its report: a successful import was "
        "reported to the operator as a failure because the row COUNT could not "
        "be read, even though the ROWS came back fine. The guard now reads "
        "resp.data, which travels in the body and cannot be lost with a header."
    )


def test_empty_check_passes_when_the_header_is_present_with_real_rows(monkeypatch):
    """Regression guard: when PostgREST's Content-Range header survives (the
    normal case), a nonzero count is reported and import_library returns the
    report normally instead of raising. Contrast with the test above, which
    fails ONLY because count came back None, not because the check is wrong
    in general."""
    client = FakeSupabaseClient(counts={"jobs": 1})
    _install_book(monkeypatch, _one_job_book())
    _install_client(monkeypatch, client)

    report = lis.import_library("fake.xlsx", write=True, org_slug="default")
    assert report.written is True
    assert report.rows["jobs"] == 1


def test_empty_check_still_catches_a_genuinely_empty_table(monkeypatch):
    """Regression guard: a real silent-failure (e.g. a publishable key that
    accepts the upsert but RLS persists nothing) with the Content-Range
    header intact and reporting an honest 0 must still raise. This is the
    scenario the check exists for, and it must keep working once `.count` is
    fixed to not conflate None with 0."""
    client = FakeSupabaseClient(counts={"jobs": 0})
    _install_book(monkeypatch, _one_job_book())
    _install_client(monkeypatch, client)

    with pytest.raises(RuntimeError, match="still empty"):
        lis.import_library("fake.xlsx", write=True, org_slug="default")


# =====================================================================
# PART 2 — import atomicity
# =====================================================================

@pytest.mark.xfail(strict=True, reason=(
    "KNOWN DEFECT, not yet fixed. import_library() inserts the library_revisions "
    "row before build_rows() has validated the workbook, so a workbook that "
    "cannot be built -- a natural-key conflict, say -- leaves a permanent "
    "revision record with no data behind it. Every rejected workbook adds "
    "debris to the audit trail. The fix is to build first and insert the "
    "revision only once the rows exist, which reorders enough of the import "
    "that it wants doing deliberately rather than alongside other work. "
    "Audit-trail hygiene: it corrupts no pay data."))
def test_a_conflicting_workbook_leaves_an_orphaned_revision_row(monkeypatch):
    """import_library() inserts into library_revisions BEFORE calling
    build_rows(). If the workbook has a natural-key conflict (two rows for
    the same key with different values), build_rows() raises ValueError —
    but only after the revision row has already been committed to the real
    database via client.table('library_revisions').insert(...).execute().

    EXPECTED: a workbook that fails to build should leave no trace — no
    orphaned library_revisions row pointing at a revision that carries zero
    actual data.
    ACTUAL: the revision insert already happened (recorded on the fake
    client) by the time the ValueError propagates, and nothing in
    import_library cleans it up or defers the insert until build_rows()
    has proven the workbook is loadable.
    """
    book = {
        "TitleMapping": pd.DataFrame([
            {"ExistingTitle": "Software Engineer", "JobID": "J-1"},
            {"ExistingTitle": "Software Engineer", "JobID": "J-2"},  # same key, differs
        ])
    }
    client = FakeSupabaseClient()
    _install_book(monkeypatch, book)
    _install_client(monkeypatch, client)

    with pytest.raises(ValueError, match="DIFFERENT values"):
        lis.import_library("fake.xlsx", write=True, org_slug="default")

    assert client.upserts == [], "no data should have been written — and none was"
    # EXPECTED: a workbook that fails to build should leave no trace at all.
    # ACTUAL: a library_revisions row was already committed (see setup above:
    # the insert happens before build_rows() is even called), so this is 1,
    # not 0 -- a permanent audit-trail row pointing at a revision that holds
    # zero rows in every table, for every workbook that fails this check.
    assert len(client.revision_inserts) == 0, (
        "DEFECT CONFIRMED: import_library committed a library_revisions row "
        f"({client.revision_inserts!r}) for a workbook that then failed to "
        "build at all. The insert happens before build_rows() has validated "
        "the workbook can be built, so every workbook that fails this check "
        "leaves a permanent orphaned revision record with zero data behind it."
    )


def test_upsert_failure_partway_leaves_earlier_tables_committed(monkeypatch):
    """import_library() upserts one table per HTTP call, in dependency order,
    with no surrounding transaction. If table N's upsert fails (network
    blip, transient PostgREST error, anything), tables before it in SPECS
    order are already committed under the new revision_id and tables after
    it never run — a half-updated library tagged with one revision.

    This test documents that behaviour empirically (it is architecturally
    inherent to per-table REST upserts, not a one-line bug like Part 1), so
    it is reported as a confirmed characteristic/risk rather than asserted
    as something a one-line fix should prevent.
    """
    client = FakeSupabaseClient(fail_upsert_for="skills")
    _install_book(monkeypatch, _two_table_book())
    _install_client(monkeypatch, client)

    with pytest.raises(RuntimeError, match="simulated network failure"):
        lis.import_library("fake.xlsx", write=True, org_slug="default")

    committed_tables = [t for t, _ in client.upserts]
    assert committed_tables == ["jobs"], (
        "'jobs' committed before 'skills' blew up, and nothing rolled it back "
        "-- the library is now half-updated under a revision_id that a caller "
        "has no way to distinguish from a fully-applied one."
    )
    assert len(client.revision_inserts) == 1  # the same orphaned-revision issue as above


# =====================================================================
# PART 3 — accented (Dutch/Polish) titles in the matching pipeline
# =====================================================================

def _sample_sheets_with(job_row, titles_extra=None):
    jobs = [
        ("J-HRBP", "HR Business Partner", "HR", "Senior"),
        job_row,
    ]
    return {
        "jobs": pd.DataFrame(jobs, columns=["JobID", "StandardTitle", "Function", "Level"]),
        "profiles": pd.DataFrame([], columns=["JobID", "Description"]),
        "titles": pd.DataFrame(titles_extra or [], columns=["ExistingTitle", "JobID"]),
        "salary": pd.DataFrame([], columns=["Function", "Level", "Min", "Max"]),
        "career": pd.DataFrame([], columns=["JobID", "NextJobID"]),
        "levels": pd.DataFrame([{"Level": x} for x in ("Junior", "Medior", "Senior", "Lead")]),
        "employees": pd.DataFrame([], columns=["EmployeeID", "Name", "CurrentTitle"]),
    }


class _StubCatalog:
    def __init__(self, repository):
        self.repository = repository

    def get_complete_job(self, job_id):
        return None


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN DEFECT, not yet fixed. core.utils.normalize_title() blanks any "
    "character outside [a-z0-9 ] instead of folding it to its base letter, so "
    "'Ksiegowosc' with Polish diacritics normalises to 'ksi gowo' and scores "
    "77.78 against the canonical ASCII title -- below the 80.0 fuzzy cutoff. "
    "The person gets NO salary band, indistinguishable in the review queue "
    "from a title with no relationship to the library. It fails safe (a "
    "dropped match, not a wrong one), but it will bite on the first non-Dutch "
    "market, and the fix changes normalisation for the whole search index, so "
    "it needs its own pass with the parity tests in front of it."))
def test_polish_diacritics_fail_to_match_the_ascii_canonical_title():
    """core/utils.normalize_title() (used by SearchIndex, which
    MatchingService is built on) strips any character outside [a-z0-9 ]
    rather than folding it to its ASCII base letter. For a short,
    single-word title, replacing 2-3 diacritics with blanks can shave the
    RapidFuzz score below MatchingService's own fuzzy_score_cutoff
    (80.0, matching SearchIndex.fuzzy's default) -- so the match is not
    merely downgraded, it is DROPPED entirely, before the review-threshold
    logic ever sees a score.

    Concretely: the reference library records the role as "Ksiegowosc"
    (ASCII). A Polish client's own payroll export spells it correctly,
    "Księgowość". A human reading both would call this the same job in two
    seconds. MatchingService calls it MatchType.NONE, confidence 0,
    unmatched=True, requires_review=True -- exactly the same result as a
    string with no relationship to the library at all ("Underwater Basket
    Weaver"). The person doesn't get a wrong salary band; they get no
    salary band, silently, and only a manual reviewer paging through
    "unmatched" rows would ever notice this one wasn't like the others.

    EXPECTED: a title that differs from its canonical counterpart only by
    correct native-language diacritics should resolve (at least via fuzzy).
    ACTUAL: it does not.
    """
    sheets = _sample_sheets_with(("J-ACC", "Ksiegowosc", "Finance", "Medior"))
    repo = Repository(sheets, validate=True)
    service = MatchingService(_StubCatalog(repo), index=repo.index)

    result = service.match("Księgowość")

    assert result.matched, (
        "DEFECT CONFIRMED: 'Księgowość' (correct Polish spelling of the "
        "canonical 'Ksiegowosc') did not match at all -- MatchType.NONE, "
        "confidence 0 -- identical to a string with no relationship to the "
        "library. normalize_title() turns each diacritic into a blank instead "
        "of folding it to its base letter, which for a short title drops the "
        "RapidFuzz score below the 80.0 fuzzy cutoff before the fuzzy stage "
        "even runs."
    )


def test_dutch_diacritic_title_still_matches_but_only_via_the_probabilistic_stage():
    """Softer companion to the Polish case above: for a longer phrase the
    diacritic-driven score drop does not cross the fuzzy cutoff, so the
    title still resolves -- but only through MatchType.FUZZY at a score in
    the low-to-mid 90s, never through the deterministic MatchType.NORMALIZED
    stage the same string would hit if it had no diacritic at all. This is a
    real behaviour difference (regression guard: it does still match), but
    it means every accented title in a batch is quietly downgraded to the
    least-trusted resolution stage and a lower confidence number than an
    ASCII-spelled colleague with the exact same job would get.
    """
    sheets = _sample_sheets_with(("J-FIN", "Hoofd Financien", "Finance", "Lead"))
    repo = Repository(sheets, validate=True)
    service = MatchingService(_StubCatalog(repo), index=repo.index)

    ascii_result = service.match("Hoofd Financien")
    accented_result = service.match("Hoofd Financiën")

    assert ascii_result.match_type is MatchType.EXACT
    assert ascii_result.confidence == 100

    assert accented_result.matched
    assert accented_result.job_id == ascii_result.job_id  # still the right job, at least
    assert accented_result.match_type is MatchType.FUZZY, (
        "if this starts failing because match_type became NORMALIZED, "
        "normalize_title() has been fixed to fold diacritics -- good, update "
        "the docstring/this assertion rather than treating it as a new defect"
    )
    assert accented_result.confidence < ascii_result.confidence


# =====================================================================
# PART 4 — fuzzy tie-break determinism
# =====================================================================

def test_fuzzy_ties_resolve_deterministically_by_build_order_not_by_chance():
    """Two canonical roles equidistant (by RapidFuzz score) from the input
    must resolve to the same winner every time the same workbook is
    imported -- otherwise the same upload run twice could file the same
    person under two different salary bands. RapidFuzz's process.extractOne
    returns the first-encountered best match for tied scores, and
    SearchIndex's fuzzy choices are appended in DataFrame row order, so the
    winner should track insertion order deterministically rather than dict/
    set iteration order. Regression guard: this holds today.
    """
    # "Support Engineer" is equidistant from both of these by construction
    # (same length, same single-character edit distance from the query).
    sheets = _sample_sheets_with(
        ("J-A", "Supqort Engineer", "Engineering", "Medior"),
    )
    # add a second, equally-close candidate directly into the same frame
    sheets["jobs"] = pd.concat([
        sheets["jobs"],
        pd.DataFrame([("J-B", "Suppprt Engineer", "Engineering", "Medior")],
                     columns=["JobID", "StandardTitle", "Function", "Level"]),
    ], ignore_index=True)
    repo = Repository(sheets, validate=True)
    service = MatchingService(_StubCatalog(repo), index=repo.index)

    winners = {service.match("Support Engineer").job_id for _ in range(20)}
    assert len(winners) == 1, (
        f"non-deterministic fuzzy tie-break: got {winners} across repeated "
        "calls against the same built index -- the same upload could file "
        "the same title under two different jobs/salary bands run to run."
    )

"""
tests/test_architecture_report.py

The report a client actually receives, and until 6 September 2026 the only
service in this product with a client-facing artefact and NO tests at all.

That combination is the wrong way round. This file builds a workbook nobody
in the product sees before the client does: it is downloaded, forwarded to a
works council, and opened on somebody else's machine. Everything else here is
checked on a screen where a person might notice; this is checked by nobody.

Two properties carry most of the risk, and they are the two tested hardest:
what happens to a client's own text when Excel reads it, and how money is
written for a market that does not write it the way the Netherlands does.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from services.architecture_report_service import (
    ArchitectureReportService, _defuse, _grade)


# ── a client's own data is not a program ──────────────────────────────────

@pytest.mark.parametrize("hostile", [
    '=HYPERLINK("http://evil.example","click")',
    "=1+1",
    "+1234",
    "-lookup()",
    "@SUM(A1:A9)",
])
def test_a_cell_that_would_execute_is_defused(hostile):
    """Excel runs a cell beginning with =, +, - or @ as a formula.

    Almost everything in this workbook is the client's own upload — employee
    names, job titles typed by whoever filled in the spreadsheet. A name of
    `=HYPERLINK(...)` becomes a LIVE FORMULA in a file a board opens, and the
    file arrives carrying our name on it.

    The apostrophe is Excel's own "treat this as text" marker and does not show
    in the cell, so the reader sees what the client typed and Excel does not run
    it.
    """
    out = _defuse(hostile)
    assert out.startswith("'"), f"{hostile!r} would execute"
    assert out[1:] == hostile, "the text itself must survive intact"


@pytest.mark.parametrize("harmless", [
    "Software Engineer", "HR Business Partner", "", "1234", "€50.000",
    "Müller, Anne-Sophie", "R&D", "Team lead (a/b)",
])
def test_ordinary_text_is_left_exactly_alone(harmless):
    """A defuser that quotes everything is a defuser nobody keeps: every name
    in the workbook would grow an apostrophe and the client would ask us to
    remove it."""
    assert _defuse(harmless) == harmless


@pytest.mark.parametrize("value", [None, 42, 3.14, True])
def test_non_text_passes_through_untouched(value):
    """Numbers must stay numbers. Prefixing a number turns a column Excel can
    sum into a column of text that silently totals zero."""
    assert _defuse(value) is value


# ── money is not written the same way everywhere ──────────────────────────

@pytest.mark.parametrize("symbol, value, expected", [
    ("€", 50000, "€50.000"),      # euro: symbol in front
    ("£", 50000, "£50.000"),      # pound: in front
    ("zł", 50000, "50.000 zł"),   # zloty: AFTER, with a space
    ("kr", 60000, "60.000 kr"),             # krona/krone: after
    ("Kč", 60000, "60.000 Kč"),   # koruna: after
])
def test_the_symbol_goes_where_that_market_puts_it(symbol, value, expected):
    """"zl50.000" is what a Polish works council would have received.

    Every money cell used to put the symbol in front unconditionally, which is
    right for the euro and the pound and wrong for every other currency this
    product covers. The rule follows country_service.money(); this service
    cannot call it, because a report must build from a script with no session.
    """
    svc = ArchitectureReportService(catalog=None, results=[], currency=symbol)
    assert svc._money(value) == expected


@pytest.mark.parametrize("bad", [None, "", "n/a", float("nan"),
                                 float("inf"), float("-inf"), "not a number"])
def test_an_amount_that_is_not_one_renders_as_a_dash(bad):
    """A blank is a fact about the data; "€nan" is a fact about our code, and
    only one of them belongs in a document a board reads."""
    svc = ArchitectureReportService(catalog=None, results=[], currency="€")
    assert svc._money(bad) == "—"


def test_an_empty_currency_falls_back_to_the_euro_rather_than_to_nothing():
    """A missing symbol must not produce a bare number that looks like a count.
    "50.000" next to a headcount column is a different claim from "€50.000"."""
    svc = ArchitectureReportService(catalog=None, results=[], currency="")
    assert svc._money(50000) == "€50.000"


# ── the caller has to tell it which market ────────────────────────────────

def test_the_service_can_be_told_a_currency_and_a_market():
    """Structural, and the reason is a defect found the same day next door.

    `analyze_gender_pay_gap` accepted a `country_col` for weeks that no screen
    ever passed, so its per-market behaviour existed and was unreachable. The
    same shape is possible here: `_money` handles zloty correctly and is only
    ever right if somebody hands the constructor the symbol.
    """
    import inspect
    params = inspect.signature(ArchitectureReportService.__init__).parameters
    assert "currency" in params and "country" in params


def test_the_screen_passes_the_market_through():
    """The other half, and the half that was missing.

    ui/views/architecture_report.py built every report in euro, for the
    deployment's default market, whatever the client's own market was — so a
    Polish client's board pack said "€" over Polish salaries.
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "ui" / "views" / "architecture_report.py").read_text(encoding="utf-8")
    # Balanced to the CLOSING paren, not to the first one. The call now
    # contains symbol_for(_market), and slicing at the first ")" cut the
    # argument list in half and made this test assert about a fragment.
    start = src.index("ArchitectureReportService(")
    depth, end = 0, start
    for i in range(start, len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    call = src[start:end]
    assert "currency=" in call, "every report is built in euro whatever the market"
    assert "country=" in call, "benefit benchmarks come from the wrong market"


# ── it builds at all ──────────────────────────────────────────────────────

def test_the_report_builds_a_readable_workbook(catalog):
    """The plainest test in the file and the one that was most missing.

    Twelve sheets are assembled by twelve methods and the whole thing is
    handed to a client. Nothing anywhere confirmed it produces a file that
    opens.
    """
    openpyxl = pytest.importorskip("openpyxl")
    svc = ArchitectureReportService(
        catalog=catalog, results=[], org_label="Test Org", currency="€")
    data = svc.generate()

    assert data[:2] == b"PK", "not a valid xlsx container"
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames[0].startswith("1. Overview"), (
        "the cover is built last and moved to the front; it did not arrive there")
    assert len(wb.sheetnames) >= 10


def test_an_empty_roster_produces_a_report_rather_than_an_exception(catalog):
    """A client with nothing matched yet still gets a document.

    An exception here reaches them as a failed download with no explanation,
    which is worse than a thin report that says what is missing.
    """
    pytest.importorskip("openpyxl")
    svc = ArchitectureReportService(
        catalog=catalog, results=[], df_employees=pd.DataFrame(),
        org_label="Empty Org")
    assert svc.generate()[:2] == b"PK"


def test_a_stale_cached_object_without_a_grade_does_not_break_the_build():
    """`_grade` exists because objects from an older cache reach this service.
    A report that raises on one is a download that fails for one client and
    works for the next, with nothing to point at."""
    class Old:                       # no `grade` attribute at all
        pass
    assert _grade(Old()) == 0
    assert _grade(None) == 0

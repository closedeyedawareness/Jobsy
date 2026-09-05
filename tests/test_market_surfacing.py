"""
Findings that took real work to establish must reach a screen.

WHY THIS FILE EXISTS, separately from test_country_packs.py. A grep across the
product found ZERO readers for `job_architecture` and `compensation` outside
`services/country_packs` itself. The packs held the Elternzeit finding, the
62,84% Spanish seniority prevalence, and the fact that a grupo profesional is
not a pay grade — and none of them could be reached by anybody who was not
reading the source. Written down and unreachable is the same as not written
down, and it is worse than a gap, because it looks like the work is done.

So these tests deliberately do two things that a service-level test does not:

1. They assert the CALL SITES. The whole defect being fixed was a function
   nothing invoked. A test exercising `market_notes` alone would have passed
   every day while the screen stayed empty, which is exactly the failure that
   already happened once here.

2. They assert the SHAPE OF A NUMBER, not just its presence. `0.6284` reaching
   a screen is not the same as the reader learning that two thirds of Spanish
   collective agreements carry a seniority component. A fraction rendered raw
   is a fact that technically arrived and practically did not.
"""

import ast
import pathlib

import pytest

from services import country_packs as cp
from services import market_notes


VIEWS = pathlib.Path(cp.__file__).resolve().parent.parent.parent / "ui" / "views"


# ── the call sites ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("view, kind, helper", [
    ("benefits.py", "compensation", "compensation_notes"),
    ("job_family.py", "job_architecture", "job_architecture_notes"),
    # The two that were already wired, kept here so this file is the one place
    # that answers "is every slot on a screen?" rather than half of it.
    ("nine_box.py", "performance", "performance_notes"),
    ("organigram.py", "org_structure", "org_structure_notes"),
])
def test_the_view_calls_the_panel_and_the_panel_calls_the_helper(view, kind, helper):
    """Both hops. A panel nobody calls and a panel that calls nothing both fail."""
    text = (VIEWS / view).read_text(encoding="utf-8")
    assert f'_market_panel("{kind}")' in text, (
        f"{view} never calls the market panel for {kind}, so the slot renders nowhere")
    assert f"market_notes.{helper}(" in text, (
        f"{view} calls a panel that never reaches market_notes.{helper}")


def test_the_panel_is_reached_before_the_page_can_return_early():
    """A note placed after a `return` is a note nobody sees.

    Both pages bail out early on missing data — benefits when the service or
    the catalog is absent, job family when the library sheets are not loaded.
    The market panel has to sit above every one of those exits that would
    otherwise leave a reader on a page with content but no note.
    """
    for view, kind in (("benefits.py", "compensation"),
                       ("job_family.py", "job_architecture")):
        tree = ast.parse((VIEWS / view).read_text(encoding="utf-8"))
        page = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name.endswith("_page"))

        call_lines = [n.lineno for n in ast.walk(page)
                      if isinstance(n, ast.Call)
                      and getattr(n.func, "id", "") == "_market_panel"]
        assert call_lines, f"{view}: the page function never calls _market_panel"

        # There must be page content BELOW the panel, or it has been parked at
        # the bottom where the early exits skip it.
        below = [n.lineno for n in ast.walk(page)
                 if isinstance(n, ast.Call)
                 and getattr(getattr(n.func, "value", None), "id", "") == "st"
                 and n.lineno > call_lines[0]]
        assert below, (
            f"{view}: _market_panel({kind!r}) sits below all the page's own output, so "
            "every early return reaches the screen without it")


# ── every market can speak, or says plainly that it cannot ───────────────────

@pytest.mark.parametrize("fn", [market_notes.compensation_notes,
                                market_notes.job_architecture_notes])
def test_every_pack_renders_or_admits_the_gap(fn):
    for code in cp.load():
        if code == cp.BASELINE:
            continue
        notes = fn(code)
        if not notes:
            continue
        assert notes[0].endswith("."), f"{code}: the heading should be a sentence"
        if len(notes) == 1:
            assert "no answer is held" in notes[0], (
                f"{code}/{fn.__name__} produced a heading and nothing under it. Either "
                "say something, or say plainly that nothing is held.")


def test_an_unknown_market_says_nothing_at_all():
    """Silence for a market we hold no pack for, as the reporting notes do.

    The failure worth preventing is not an unhelpful screen — it is a confident
    one about a country nobody researched.
    """
    assert market_notes.compensation_notes("ZZ") == []
    assert market_notes.job_architecture_notes("ZZ") == []


# ── the numbers ──────────────────────────────────────────────────────────────

def test_a_fraction_never_reaches_the_screen_as_a_fraction():
    """No rendered line may contain a bare 0,x — the defect being designed out."""
    for code in cp.load():
        for note in market_notes.compensation_notes(code):
            assert "0.6284" not in note and "0.9209" not in note, note
            # The heading is prose; every other line that mentions a coverage
            # or prevalence figure must carry the percent sign with it.
            assert not note.startswith("0."), note


@pytest.mark.parametrize("value, expected", [
    (0.6284, "62,84%"),
    (0.9209, "92,09%"),
    (0.49, "49%"),        # trailing zeros stripped: a survey figure is not 49,00%
    (0.116, "11,6%"),
    (1.0, "100%"),
    (0.0, "0%"),
])
def test_a_fraction_reads_as_a_percentage(value, expected):
    assert market_notes._as_percentage(value) == expected


@pytest.mark.parametrize("value", ["a phrase", None, ("a", "tuple"), 12.5, True])
def test_only_a_fraction_is_treated_as_one(value):
    """`seniority_progression` is a share in Spain and a sentence everywhere else.

    A percentage formatter that guesses would turn "public sector only" into
    nothing, or a headcount of 250 into 25000%. It has to decline anything that
    is not a number between 0 and 1 — booleans included, since bool is an int.
    """
    assert market_notes._as_percentage(value) is None


def test_the_spanish_prevalence_arrives_labelled_and_unranked():
    """62,84% is the only measured seniority figure in the set.

    It must reach the screen as a share, must say that its denominator is not
    the coverage figure's, and must NOT be dressed up as a position in a
    ranking — there is exactly one comparable number, so a ranking would be
    manufactured rather than found.
    """
    notes = market_notes.compensation_notes("ES")
    line = next(n for n in notes if "Automatic progression with service" in n)
    assert "62,84%" in line
    assert "denominator" in line, "the share needs its basis pointed at"
    assert "nothing sound to rank it against" in line
    assert "highest of the" not in line, "seniority must not borrow coverage's ranking"


def test_a_phrase_in_the_same_field_reads_as_a_phrase():
    """The Dutch answer is a mechanism, not a share, and must not be forced."""
    line = next(n for n in market_notes.compensation_notes("NL")
                if "Automatic progression with service" in n)
    assert "%" not in line.split("—")[0], "no invented figure in the label"
    assert "voldoende functioneert" in line, (
        "the Dutch step is gated on functioning, and that gate is the auditable "
        "half of the gender correlation — it cannot be dropped")


def test_coverage_is_placed_against_the_other_markets():
    """Where a figure IS comparable, showing the position beats the bare number."""
    ranking = market_notes._coverage_ranking()
    assert len(ranking) >= 3, "premise: there is a set to rank against"
    assert ranking == sorted(ranking, key=lambda row: -row[2]), "high to low"

    top, bottom = ranking[0], ranking[-1]
    assert top[0] == "BE" and bottom[0] == "PL", (
        "the endpoints are the two the placement claim rests on: effectively total "
        "coverage in Belgium against 11,6% in Poland")

    de = next(n for n in market_notes.compensation_notes("DE")
              if "Collective-agreement coverage" in n)
    assert "49%" in de
    assert "11,6% (Poland)" in de and "100% (Belgium)" in de
    assert "not one harmonised series" in de, (
        "six national sources at three hardnesses are not a comparable series and the "
        "line has to say so, or the ranking claims more than it holds")


def test_the_extreme_markets_are_named_as_extremes_not_ordinals():
    """"the 6th highest of 6" is arithmetic; "the lowest" is the finding."""
    pl = next(n for n in market_notes.compensation_notes("PL")
              if "Collective-agreement coverage" in n)
    assert "the lowest of the" in pl, pl
    be = next(n for n in market_notes.compensation_notes("BE")
              if "Collective-agreement coverage" in n)
    assert "the highest of the" in be and "1st highest" not in be, be


def test_the_ranking_is_computed_and_not_typed_in():
    """A hard-coded league table would silently go wrong when a pack changes.

    This is the same failure mode as the reporting duty that sat in production
    as prose for four months: a fact retyped away from its source has nothing
    to check it against.
    """
    covered = {row[0] for row in market_notes._coverage_ranking()}
    from_packs = {code for code, pack in cp.load().items()
                  if getattr(getattr(pack, "compensation", None),
                             "bargaining_coverage", None) is not None
                  and isinstance(pack.compensation.bargaining_coverage.value, float)}
    assert covered == from_packs, (
        "the ranking must be derived from whatever packs currently hold a figure")


# ── the register ─────────────────────────────────────────────────────────────

def test_the_weight_and_the_age_stay_in_front_of_the_label():
    """A label must not push UNVERIFIED or STALE into the middle of a sentence.

    Somebody skimming a list of bullets reads the first few words. If a lead
    like "Collective-agreement coverage:" lands before the hardness marker, the
    marker is buried exactly where it stops being read.
    """
    from datetime import date

    claim = cp.Claim(0.5, cp.ONBEVESTIGD, "", "2026-09-06", note="a claim")
    assert market_notes._line(claim, lead="Label: ") == "UNVERIFIED — Label: a claim"

    old = cp.Claim(0.5, cp.WET, "src", "2026-01-01", note="a claim",
                   review_after_months=6)
    line = market_notes._line(old, date(2026, 9, 5), lead="Label: ")
    assert line.startswith("STALE ("), line
    assert "Label: a claim" in line


def test_the_belgian_coverage_reading_is_still_marked_as_a_reading():
    """100% is an OECD series read, not a Belgian statute, and dressing a
    number in a percent sign must not quietly promote it to fact."""
    be = next(n for n in market_notes.compensation_notes("BE")
              if "Collective-agreement coverage" in n)
    assert be.startswith("Reading of the law rather than its words — "), be


def test_there_is_exactly_one_not_advice_statement():
    """Reuse `market_caveat`; a second one would drift from the first.

    The pay-equity service already carries its own standing statement for its
    own screens. What must not happen is a THIRD sentence written here saying
    roughly the same thing slightly differently, because then a change to the
    product's legal posture has to find all of them.
    """
    source = pathlib.Path(market_notes.__file__).read_text(encoding="utf-8")
    assert source.count("NOT legal advice") == 1, (
        "market_notes should hold one not-advice statement, in market_caveat()")

    for view in ("benefits.py", "job_family.py"):
        text = (VIEWS / view).read_text(encoding="utf-8")
        assert "market_notes.market_caveat()" in text, (
            f"{view} renders market notes without the framing they are read under")
        assert "legal advice" not in text.replace("market_caveat", ""), (
            f"{view} writes its own not-advice sentence instead of reusing the one")


def test_no_note_tells_an_employer_what_it_must_do():
    """The register is: report what the source provides.

    "You must" and "you are required to" are sentences this product cannot
    carry — they turn on facts it does not hold, starting with a headcount that
    means a different unit in every one of these markets. The packs quote
    statutes that say what employers must do, which is a different act, so this
    only guards the sentences THIS module composes.
    """
    composed = [market_notes.market_caveat()]
    for code in cp.load():
        for fn in (market_notes.compensation_notes,
                   market_notes.job_architecture_notes):
            for note in fn(code):
                # Everything after the pack's own words is the pack's; the
                # module's contribution is the heading and the leads.
                composed.append(note.split("—")[0])
                composed.append(note.split(".")[0])

    for text in composed:
        lowered = text.lower()
        for banned in ("you must", "you should", "you are required",
                       "we recommend", "make sure you"):
            assert banned not in lowered, f"{banned!r} in: {text}"

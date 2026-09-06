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
    """Both hops. A panel nobody calls and a panel that calls nothing both fail.

    The second hop moved. Each view carried its own copy of the panel while
    three agents worked in parallel and none could edit another's files — the
    ownership rule working, and a debt to settle once it lifted. There is one
    `market_panel` in `ui/shared.py` now, so hop one is still checked in the
    view and hop two is checked where the panel actually lives.
    """
    text = (VIEWS / view).read_text(encoding="utf-8")
    assert f'market_panel("{kind}")' in text, (
        f"{view} never calls the market panel for {kind}, so the slot renders nowhere")
    assert "def market_panel" not in text, (
        f"{view} has grown its own copy of the panel again — there is one in ui/shared.py")

    shared = (VIEWS.parent / "shared.py").read_text(encoding="utf-8")
    assert f"market_notes.{helper}" in shared, (
        f"the shared panel never reaches market_notes.{helper}, so {kind} renders nothing")


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
                      and getattr(n.func, "id", "") == "market_panel"]
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

    # The caveat now lives once, in the shared panel, and that is a stronger
    # guarantee than one assertion per view: a page cannot render market notes
    # without it by forgetting a line, because it no longer writes the line.
    shared = (VIEWS.parent / "shared.py").read_text(encoding="utf-8")
    assert "market_notes.market_caveat()" in shared, (
        "the shared panel renders market notes without the framing they are read under")

    # What each view must still not do is write a SECOND one of its own.
    for view in ("benefits.py", "job_family.py", "nine_box.py", "organigram.py"):
        text = (VIEWS / view).read_text(encoding="utf-8")
        assert "legal advice" not in text, (
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


# ── a share that carries what it counts ───────────────────────────────────

@pytest.mark.parametrize("value, basis, percentage", [
    (("share_of_agreements", 0.6284), "collective agreements", "62,84%"),
    (("share_of_employees", 0.5), "employees", "50%"),
    (0.5, None, "50%"),                       # a bare fraction stays legal
    (("share_of_widgets", 0.25), "widgets", "25%"),   # unmapped, still readable
])
def test_a_measured_share_can_carry_its_denominator(value, basis, percentage):
    """A fraction may say what it is a fraction OF, and must not lose the figure.

    An unmapped basis is un-slugged rather than dropped. A denominator nobody
    wrote a phrase for still reads as something; a denominator that silently
    vanishes leaves a percentage floating, which is the failure the pair exists
    to prevent.
    """
    assert market_notes._fraction_of(value)[0] == basis
    assert market_notes._as_percentage(value) == percentage


def test_the_spanish_denominator_is_on_the_line_not_only_in_the_note():
    """62,84% of WHAT has to survive being quoted on its own.

    The note underneath says 908 of 1.445 convenios, but a reader who copies the
    labelled line into a slide takes the figure and leaves the note. Spain counts
    a share of AGREEMENTS where the coverage figure two lines up counts a share
    of EMPLOYEES, and two percentages side by side on one screen read as one
    scale unless the line itself says otherwise.
    """
    line = next(n for n in market_notes.compensation_notes("ES")
                if "Automatic progression with service" in n)
    assert "62,84% of collective agreements" in line


# ── the coverage view ────────────────────────────────────────────────────────
#
# `capability_gaps()` had ZERO callers. It is the function that knows which
# capability slots a market has not answered for, and the difference it exists
# to keep — an unanswered slot is "we do not know", an empty one is "we know
# there is nothing" — had therefore never reached a person. These tests hold
# the two halves of the fix: that the function is called, and that the
# distinction survives being rendered.
#
# Nothing here asserts a TALLY. The packs are being written in parallel with
# this module: a Belgian qualification mapping or a new field lands and every
# hard-coded "12 of 30" becomes a lie that a green test defends. Every count in
# these tests is computed from the packs on both sides.

def test_capability_gaps_finally_has_a_caller():
    """The measured defect: a function nothing invoked.

    Both hops, as above. The service must call it, and every slot it names must
    arrive at the view's own structure as NOT ANSWERED — not as a missing row,
    which is how a gap becomes invisible again one layer up.
    """
    source = pathlib.Path(market_notes.__file__).read_text(encoding="utf-8")
    assert "capability_gaps(" in source, (
        "market_notes never calls capability_gaps, so unanswered slots reach no screen")

    for code in cp.load():
        report = market_notes.market_coverage(code)
        named = {s["slot"] for s in report["slots"] if s["state"] == "not answered"}
        assert named == set(cp.capability_gaps(code)), (
            f"{code}: the view's unanswered slots must be exactly what capability_gaps "
            f"reports, computed live rather than restated")


def test_every_capability_slot_is_accounted_for_on_every_market():
    """A slot that is simply absent from the list is a gap nobody can see.

    The failure this guards is subtler than a wrong state: a view that only
    lists what it holds shows a complete-looking screen for a pack that answers
    two capabilities out of six.
    """
    for code in cp.load():
        report = market_notes.market_coverage(code)
        assert {s["slot"] for s in report["slots"]} == set(market_notes._CAPABILITY_SLOTS)
        for slot in report["slots"]:
            assert slot["state"] in ("answered", "held and empty", "not answered")
            assert slot["question"], f"{code}/{slot['slot']}: no statement of what is lost"


def test_an_unanswered_slot_and_an_empty_one_never_read_the_same():
    """The whole reason `capability_gaps()` exists, held at the last step.

    Built from a stand-in rather than a real pack on purpose: every capability
    dataclass in the package currently requires at least one Claim, so no pack
    can reach the empty state today. The branch is still the one that decides
    whether a future optional field renders as a finding or as a blank, and a
    test that waits for that field to exist is a test that arrives after the
    damage.
    """
    from types import SimpleNamespace

    stand_in = SimpleNamespace(performance=None, skills=object())
    states = market_notes._slot_states(stand_in, {"performance": "not answered"})
    by_slot = {s["slot"]: s for s in states}

    assert by_slot["performance"]["state"] == "not answered"
    assert by_slot["skills"]["state"] == "held and empty"

    first = market_notes.slot_state_meaning("not answered")
    second = market_notes.slot_state_meaning("held and empty")
    assert first and second and first != second
    assert "nobody" in first.lower(), "an unanswered slot must say nobody has looked"
    assert "nothing was recorded" in second, (
        "an empty slot must read as a recorded finding, not as a missing answer")


def test_coverage_is_never_presented_as_a_score():
    """No percentage, no ratio, no "n of six" in anything this module composes.

    "Germany 71% covered" invites a reader to trust the 71% and stop, and the
    missing 29% is not uniform — one unanswered reporting duty is a filing
    somebody misses. The claims' own words may contain percentages (Spain's
    62,84% is a real measurement), so this checks the sentences the MODULE
    writes: the heading, the slot lines and the evidence line.
    """
    for code in cp.load():
        report = market_notes.market_coverage(code)
        composed = [market_notes.coverage_notes(code)[0]]
        composed += [n for n in market_notes.coverage_notes(code)
                     if n.startswith("Evidence held:")]
        for slot in report["slots"]:
            composed += [f"{slot['label']} {slot['question']} {slot['state']}"]
        for text in composed:
            assert "%" not in text, f"{code}: a percentage in {text!r}"
            for banned in ("covered", "complete", "score", " of 6", " of six"):
                assert banned not in text.lower(), f"{code}: {banned!r} in {text!r}"

        assert all(isinstance(v, int) for v in report["hardness"].values()), (
            "the evidence mix must be counts; a share would be the same trap in "
            "another shape")


def test_the_evidence_mix_is_counted_from_the_pack():
    """Every claim in the pack is weighed, whatever new field it arrives in.

    The walk is generic over dataclass fields rather than over a list of names,
    because this module and the packs are being written at the same time. A
    field added tonight must be counted tonight.
    """
    for code, pack in cp.load().items():
        report = market_notes.market_coverage(code)
        assert sum(report["hardness"].values()) == report["claims"] > 0
        assert set(report["hardness"]) <= set(cp.HARDNESS)
        # Every claim the pack itself cannot stand behind is one of the walk's.
        assert len(report["unverified"]) == sum(
            1 for _, c in market_notes._labelled_claims(pack) if not c.verified)


def test_unverified_and_stale_stay_in_front_where_they_are_read():
    """Both markers lead the line, and neither is filed under a heading.

    A coverage screen that tucks ONBEVESTIGD into a footnote has done the thing
    the hardness vocabulary was borrowed to prevent: a gap that no longer says
    so.
    """
    for code in cp.load():
        report = market_notes.market_coverage(code)
        for line in report["unverified"]:
            assert line.startswith("UNVERIFIED"), line
        for line in report["stale"]:
            assert line.startswith("STALE"), line
        # And they are in the sentences, not only in the structure.
        for line in report["unverified"] + report["stale"]:
            assert line in market_notes.coverage_notes(code)


def test_a_claim_with_no_words_is_still_reported_as_unverified(monkeypatch):
    """The emptiest claim must not be the invisible one.

    `_line` returns None for a claim carrying neither a value nor a note — right
    for a market panel, wrong here, because on a coverage screen that claim IS
    the finding. `CrosswalkSpec` defaults its source to exactly that shape, so
    the first pack to declare a crosswalk without citing one would otherwise
    lose the only sentence saying so.
    """
    blank = cp.CrosswalkSpec("X", False)
    assert market_notes._line(blank.source) is None, "premise: nothing to render"

    stand_in = cp.CountryPack(country="ZZ", name="Nowhere", currency="EUR",
                              languages=("xx",), crosswalks=(blank,))
    monkeypatch.setattr(cp, "for_country", lambda country=None: stand_in)
    report = market_notes.market_coverage("ZZ")
    assert len(report["unverified"]) == 1
    assert report["unverified"][0].startswith("UNVERIFIED")
    assert "no value and no words" in report["unverified"][0]


def test_a_claim_on_a_review_clock_is_shown_before_it_lapses():
    """Waiting for STALE means this tool only ever reports being late.

    The claims that carry an interval are negatives about the state of
    legislation — "no implementing law has been published" — which stop being
    true the moment a parliament acts, so the useful moment to re-check is
    before the interval runs out.
    """
    on_clock, stale = [], []
    for code in cp.load():
        report = market_notes.market_coverage(code)
        on_clock += report["on_clock"]
        stale += report["stale"]
    assert on_clock or stale, (
        "premise: some claim in some pack carries review_after_months. If this fails "
        "the review mechanism has been removed from the packs, not from here")
    for line in on_clock:
        assert "due again in" in line, line


def test_the_routes_are_asked_of_bridge_and_not_typed_in():
    """Every crossing named must be one `bridge()` actually returns.

    Occupation reaches every held market and qualification reaches under half —
    a shape that will change the day a pack gains a mapping, which is exactly
    why no count of it may live in this file or in that module.
    """
    packs = cp.load()
    for code in packs:
        lines = market_notes._route_lines(code)
        joined = " ".join(lines)
        for other, pack in packs.items():
            if other in (code, cp.BASELINE):
                continue
            for dimension in (cp.OCCUPATION, cp.QUALIFICATION):
                ok = cp.bridge(code, other, dimension)["ok"]
                label = "Occupation" if dimension == cp.OCCUPATION else "Qualification"
                relevant = [n for n in lines if n.startswith(label)]
                where = [n for n in relevant if pack.name in n]
                assert where, f"{code}->{other} {dimension}: not stated either way"
                assert any(("NO ROUTE" in n) != ok for n in where), (
                    f"{code}->{other} {dimension}: rendered as the opposite of what "
                    f"bridge() answers")
        assert joined, f"{code}: no crossing line at all"


def test_a_refusal_reaches_the_screen_whole():
    """"No route" is not the finding; WHY there is none is.

    `bridge()` distinguishes a market nobody has mapped yet from a market where
    no authoritative correspondence exists to map — Germany is absent from the
    qualification spine because the DQR is a joint declaration rather than a
    statute, which is a finished answer and not a backlog item. A coverage view
    that reduced either to a red cross would be asserting the one thing the
    package refuses to assert.

    Checked as an identity against whatever `bridge()` currently says, not
    against a phrase: the refusals are being rewritten in the packs while this
    is written, and a test pinned to their wording would fail on an improvement
    and pass on a truncation.
    """
    packs = cp.load()
    seen = 0
    for code in packs:
        lines = market_notes._route_lines(code)
        for other in packs:
            if other in (code, cp.BASELINE):
                continue
            for dimension in (cp.OCCUPATION, cp.QUALIFICATION):
                result = cp.bridge(code, other, dimension)
                if result.get("ok") or not result.get("refusal"):
                    continue
                seen += 1
                assert any(result["refusal"] in line for line in lines), (
                    f"{code}->{other} {dimension}: the refusal reaches the screen "
                    f"summarised or cut, and the reason is the whole content of it")
    assert seen, "premise: at least one pair does not cross today"


def test_an_uncovered_market_is_answered_with_silence():
    """The rule `reporting_for()` already enforces, kept at this layer too.

    Several member states are stricter than the directive, so lending an
    unresearched market the EU baseline understates a duty that already exists.
    An empty answer is the safe one.
    """
    assert market_notes.market_coverage("ZZ") is None
    assert market_notes.coverage_notes("ZZ") == []
    assert market_notes.uncovered_markets(["ZZ", "zz", "NL", ""]) == ["ZZ"]
    for code in cp.load():
        assert market_notes.uncovered_markets([code]) == []


def test_the_coverage_panel_is_on_a_screen_and_reaches_the_service():
    """Both hops again, because one function with no caller is why this exists.

    Placed on the data-quality page: the one screen whose subject is already
    what this tool does not know, and therefore the one where somebody is in a
    position to plan coverage rather than meet it as a missing answer.
    """
    shared = (VIEWS.parent / "shared.py").read_text(encoding="utf-8")
    assert "def market_coverage_panel" in shared
    assert "market_notes.market_coverage(" in shared, (
        "the panel never reaches the service, so it renders nothing")
    assert "market_notes.slot_state_meaning(" in shared, (
        "the panel explains the slot states in its own words, which will drift from "
        "the service's")

    page = (VIEWS / "data_quality.py").read_text(encoding="utf-8")
    assert "market_coverage_panel()" in page, "the panel is on no screen"
    assert "def market_coverage_panel" not in page, (
        "the page has grown its own copy — there is one in ui/shared.py")


def test_the_panel_sits_above_everything_that_can_fail():
    """A gap report that vanishes when the library is broken is missing twice.

    Everything else on the data-quality page needs a loaded catalog. Market
    coverage needs only the packs, so it must render before the first thing that
    can raise — including the repository handle the page opens with.
    """
    tree = ast.parse((VIEWS / "data_quality.py").read_text(encoding="utf-8"))
    page = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "data_quality_page")
    calls = [n.lineno for n in ast.walk(page)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "market_coverage_panel"]
    assert calls, "data_quality_page never calls the coverage panel"

    catalog_use = [n.lineno for n in ast.walk(page)
                   if isinstance(n, ast.Attribute)
                   and getattr(getattr(n, "value", None), "id", "") == "catalog"]
    assert catalog_use, "premise: the page reads the catalog somewhere"
    assert calls[0] < min(catalog_use), (
        "the coverage panel sits below the page's first catalog access, so a library "
        "that fails to load takes the gap report down with it")


def test_the_coverage_view_names_no_product():
    """White-label: the sentences say "this tool", never a brand.

    Guarded on the sentences THIS module composes — the packs quote sources and
    their words are theirs. Checked here as well as in test_tenancy_invariants
    because these strings live in services/, which that file does not read.
    """
    composed = [market_notes.slot_state_meaning(s)
                for s in ("answered", "held and empty", "not answered")]
    for code in cp.load():
        report = market_notes.market_coverage(code)
        notes = market_notes.coverage_notes(code)
        composed.append(notes[0])
        composed += [n for n in notes if n.startswith("Evidence held:")]
        composed += [f"{s['label']} {s['question']}" for s in report["slots"]]
    for text in composed:
        assert "Jobsy" not in text, text


# ── the parameter that existed and was never passed ───────────────────────

def test_the_pay_equity_screen_detects_a_country_column_and_passes_it_to_both():
    """A per-market capability is only real once a screen reaches it.

    `analyze_gender_pay_gap` has accepted a `country_col` since the packs
    landed, and no screen in this product ever passed one. So the per-market
    gender normalisation — the thing that stops a Spanish `M` (*mujer*, a woman)
    being folded as a man under the session's Dutch pack — existed in the
    service and was unreachable from the interface. On a Dutch-only roster that
    changes nothing, which is exactly why it survived unnoticed.

    Both analyses must receive the SAME column. They render two figures on one
    screen; normalising them differently produces a gap and an exposure computed
    over different populations, with nothing on the screen saying so.

    Structural, because the failure is silent: the analysis returns a perfectly
    plausible number either way.
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "ui" / "views" / "pay_equity.py").read_text(encoding="utf-8")

    assert "_lg_country = _smart_detect(" in src, (
        "no country column is detected, so every roster is read under the "
        "session's market whatever it actually spans")

    for call in ("analyze_gender_pay_gap(", "analyze_variable_pay_exposure("):
        start = src.index(call)
        args = src[start:src.index(")", src.index("salary_already_fte", start))]
        assert "country_col" in args, (
            f"{call.rstrip('(')} is called without the country column, so it "
            "normalises the whole roster under one market")

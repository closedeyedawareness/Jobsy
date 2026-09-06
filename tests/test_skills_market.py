"""
tests/test_skills_market.py

The skills module against the country dimension.

Until today the three skills screens were the only module group in the product
with no country awareness at all — no market panel, no caveat, not one mention
of a country in either the service or the views. That was never a judgement
that skills are universal; the question had simply not been asked.

The position these tests lock in is narrower than "skills are national". A
skill mostly IS universal — negotiating is negotiating on both sides of a
border, which is why the catalogue is not being split. What is national is what
a skill and a qualification are READ AGAINST: the qualification framework and
the occupation taxonomy, both instruments with law behind them.
"""
from __future__ import annotations

import pytest

from services import country_packs as cp
from services import market_notes


PACKS = sorted(cp.load())


# ── every market answers, or says it does not ─────────────────────────────

@pytest.mark.parametrize("code", PACKS)
def test_every_pack_says_what_a_skill_is_read_against(code):
    notes = market_notes.skills_notes(code)
    assert notes, f"{code} renders nothing at all"
    assert notes[0].startswith("WHAT A SKILL IS READ AGAINST HERE")


# ── the licence boundary, made structural ─────────────────────────────────

def test_no_pack_ships_an_occupation_crosswalk_it_may_not_redistribute():
    """The narrow question must stay narrow.

    Several official occupation crosswalks are free to read and restricted to
    redistribute — Germany's requires the agency's permission for commercial
    use. A product that SHIPS the table is redistributing it; one that says
    "the official correspondence lives here" is not. As long as no occupation
    mapping carries a table, the restriction is not engaged, and the open legal
    question shrinks from "may we sell this product" to "may we ship this
    particular file".

    The one exemption is an identity: Belgium codes occupations in ISCO-08
    directly, and there is nothing to hold.

    A test rather than a docstring because this is one careless commit away
    from being untrue, and the commit would look like an improvement.
    """
    shipped = []
    for code, pack in cp.load().items():
        for slot in (pack.skills, pack.job_architecture):
            for m in getattr(slot, "mappings", ()) or ():
                if m.dimension == cp.OCCUPATION and m.mapping:
                    shipped.append(f"{code}: {m.local_scheme} -> {m.spine}")
    assert not shipped, (
        "these packs ship an occupation crosswalk rather than citing it, which "
        "engages a redistribution restriction nobody has cleared: "
        + "; ".join(shipped))


def test_a_qualification_table_is_only_held_where_the_law_states_it():
    """Qualification tables ARE held, and the reason is different in kind.

    Every one of them is a correspondence set out level by level in a statute —
    the Dutch Besluit NLQF, the French décret, the Spanish real decreto, the
    Polish ZSK act. Reproducing what a statute says is not reproducing somebody
    else's dataset. So the guard here is not "hold nothing" but "hold it only on
    the strength of law": a qualification table resting on UITLEG or weaker is
    somebody's reading of a correspondence rather than the correspondence.
    """
    weak = [f"{code}: {m.local_scheme} ({m.source.hardness})"
            for code, pack in cp.load().items()
            for m in (getattr(pack.skills, "mappings", ()) or ())
            if m.dimension == cp.QUALIFICATION and m.mapping and m.source.hardness != cp.WET]
    assert not weak, (
        "a qualification correspondence is held as a table on less than statutory "
        "authority: " + "; ".join(weak))


# ── bridge() finally has a caller ─────────────────────────────────────────

def test_a_route_is_labelled_by_its_weaker_half():
    """A chain is exactly as sound as its softest link.

    Reporting the stronger hardness would flatter the answer, and the
    flattering version is the one that gets quoted.
    """
    order = (cp.ONBEVESTIGD, cp.CONVENTIE, cp.UITLEG, cp.WET)
    checked = 0
    for a in PACKS:
        for b in PACKS:
            r = cp.bridge(a, b, cp.OCCUPATION)
            if not r["ok"]:
                continue
            checked += 1
            hops = [h["hardness"] for h in r["route"]]
            assert r["hardness"] == min(hops, key=order.index), (a, b, hops)
    assert checked, "no route was exercised at all"


def test_the_refusals_reach_the_screen_rather_than_only_existing():
    """The load-bearing half of bridge() is the part that says no.

    Grade and pay are refused outright — no neutral unit exists for either —
    and an unmapped pack is refused too. Before this panel, none of those
    sentences had ever been rendered anywhere, which makes a refusal
    indistinguishable from a feature nobody built.
    """
    lines = market_notes.crossing_notes("DE", source="BE")
    joined = " ".join(lines)
    assert "NO ROUTE" in joined, "an unmapped dimension must say so on screen"
    assert "no legal equivalence" in joined, "the grade refusal is not shown"
    assert "no neutral unit" in joined, "the pay refusal is not shown"


def test_crossing_a_market_with_itself_is_not_dressed_up_as_a_route():
    lines = market_notes.crossing_notes("NL", source="NL")
    assert len(lines) == 1 and "nothing to cross" in lines[0]


def test_an_uncovered_market_is_answered_with_silence():
    lines = market_notes.crossing_notes("SE", source="NL")
    assert any("silence rather than a guess" in n for n in lines)
    assert not any("via" in n for n in lines), "a route was offered into a market we do not hold"


# ── what the reference does NOT do ────────────────────────────────────────

def test_the_screen_says_that_a_reference_does_not_convert():
    """The assumption a reader is most likely to make for us.

    Knowing that KldB reaches ISCO-08 does not put a German roster into
    ISCO-08. If that sentence is not on the page, "a correspondence exists"
    quietly becomes "the tool handles it".
    """
    notes = market_notes.skills_notes("DE")
    assert any("A REFERENCE DOES NOT CONVERT" in n for n in notes)


def test_a_cited_crosswalk_says_it_is_cited_and_not_held():
    notes = " ".join(market_notes.skills_notes("DE"))
    assert "CITES IT AND DOES NOT HOLD IT" in notes


def test_an_identity_is_named_as_an_identity_not_as_a_crossing():
    """Belgium's occupation coding IS ISCO-08. Presenting that as a route
    would invent a hop, and a hop is where error enters."""
    notes = " ".join(market_notes.skills_notes("BE"))
    assert "there is no crossing to get wrong" in notes


def test_the_belgian_two_framework_finding_survives_to_the_screen():
    """The sharpest case in the set, and it is not even cross-border.

    Qualifications are a Community competence in Belgium, so one employer with
    sites in Flanders and Wallonia faces two frameworks — and the EQF level is
    the only reliable join between them. That is the spine earning its keep
    inside a single country.
    """
    notes = " ".join(market_notes.skills_notes("BE"))
    assert "ONLY RELIABLE JOIN KEY" in notes.upper()


def test_an_absent_mapping_is_not_reported_as_a_to_do():
    """Two different absences look identical from inside bridge().

    A market nobody has mapped yet, and a market where no authoritative
    correspondence EXISTS to map, produce the same empty tuple. Germany is the
    second kind and it is not obvious: the DQR is a joint declaration by two
    ministries and two Länder conferences, its own pages say it has
    orientierenden Charakter and keine regulierende Funktion, and a DQR level
    confers no entitlement. Its absence from the spine may be the correct
    answer rather than a gap.

    The refusal used to read "this pack has not been mapped to it yet", which
    asserts the first kind. A backlog item is a promise, and promising to map
    something that has no authoritative correspondence is a promise that can
    only be kept by inventing one.
    """
    refusal = cp.bridge("DE", "NL", cp.QUALIFICATION)["refusal"]
    assert "has not been mapped to it yet" not in refusal
    assert "cannot tell you which" in refusal

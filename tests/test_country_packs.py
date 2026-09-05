"""
Tests for services/country_packs.

These are compliance tests more than unit tests. Each one exists because the
rule it checks is easy to break by accident and expensive to break in front of
a client, and because a rule that lives only in a docstring is a rule that
lasts until the next person is in a hurry.

The suite is deliberately written against `load()` rather than against a list
of packs, so a pack added next year is held to the same standard the day it
appears, without anyone remembering to add it here.
"""
from __future__ import annotations

import pytest

from services import country_packs as cp

ALL_PACKS = sorted(cp.load().items())
PACK_IDS = [c for c, _ in ALL_PACKS]

#: Several tests need "a real EU market we hold no pack for". France used to be
#: that example, chosen because its Index applies from 50 employees and so makes
#: the point vividly. Then France got a pack and three tests broke — which is
#: the suite noticing coverage grew, not a fault. Rather than rename the country
#: every time and eventually pick one that is also about to land, the stand-in
#: is now resolved from whatever is genuinely still uncovered.
_CANDIDATES = ("IT", "SE", "DK", "PT", "IE", "AT", "FI", "CZ", "RO", "GR")
UNCOVERED = next((c for c in _CANDIDATES if c not in cp.load()), None)


# ── the rules every pack must satisfy ────────────────────────────────────────

@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_pack_validates(code, pack):
    """No pack in the package may carry a validation problem.

    `validate()` returns sentences rather than raising, so that a half-written
    pack can be inspected. This test is what stops one being shipped.
    """
    problems = cp.validate(pack)
    assert not problems, f"{code}: " + "; ".join(problems)


@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_live_packs_carry_no_unverified_claims(code, pack):
    """LIVE is a promise that a human checked the sources.

    A pack goes LIVE when its claims are evidenced, not when its fields are
    full. If this ever fails, the fix is to verify the claim or drop the pack
    back to DRAFT, never to relax the test.
    """
    if pack.status != cp.LIVE:
        pytest.skip(f"{code} is {pack.status}")
    assert not pack.unverified, (
        f"{code} is LIVE but still holds unverified claims: "
        + "; ".join(str(c) for c in pack.unverified))


@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_reporting_bands_do_not_overlap(code, pack):
    """Two bands matching one headcount means one of them never fires.

    Whichever is written first silently wins, which is how a client ends up
    reading a duty that belongs to a company twice their size.
    """
    if not (pack.reporting and pack.reporting.bands):
        pytest.skip(f"{code} holds no bands of its own")
    seen: list[tuple[int, int, str]] = []
    for b in pack.reporting.bands:
        hi = b.max_employees if b.max_employees is not None else 10 ** 9
        assert b.min_employees <= hi, f"{code}: band {b.min_employees}-{hi} is inverted"
        for lo2, hi2, _ in seen:
            assert hi < lo2 or b.min_employees > hi2, (
                f"{code}: bands {b.min_employees}-{hi} and {lo2}-{hi2} overlap")
        seen.append((b.min_employees, hi, str(b.frequency.value)))


@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_point_bands_require_a_published_table(code, pack):
    """The IP boundary, as a test rather than a good intention.

    ISF publishes its point boundaries, so Jobsy may show them. CATS, PC 200
    and ERA do not, so any point table attributed to them would have been
    re-derived from a protected method. `validate()` refuses that combination;
    this asserts it stays refused.
    """
    for cw in pack.crosswalks:
        if cw.point_bands:
            assert cw.publishes_point_table, (
                f"{code}/{cw.system} holds point bands but does not publish a point "
                "table. Either the flag is wrong or the data should not be here.")


@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_gender_codes_are_unambiguous(code, pack):
    """One code may not mean two sexes.

    The live hazard is single letters across languages: Dutch `v` is vrouw,
    French `f` is femme, German `w` is weiblich, and an English-shaped parser
    can read any of them as a male variant. If a code ever appeared in two
    buckets the resulting gap would be wrong in a direction nobody checks,
    because the number would still look plausible.
    """
    seen: dict[str, str] = {}
    for label, codes in (pack.gender_codes or {}).items():
        for raw in codes:
            key = raw.strip().lower()
            assert key not in seen or seen[key] == label, (
                f"{code}: gender code {key!r} maps to both {seen[key]!r} and {label!r}")
            seen[key] = label


# ── the resolver ─────────────────────────────────────────────────────────────

def test_unknown_country_is_answered_with_silence():
    """No pack means no answer — not the EU baseline.

    The directive does apply Union-wide, which makes inheritance tempting, but
    several member states are stricter than it, and the packs written since have
    proved it three times over rather than hypothetically: France's Index
    applies from 50, Belgium's 2012 law from 50, and Spain's registro
    retributivo from ONE employee. Any of those clients handed the EU bands
    would have been told they had no duty while sitting on a live one.
    Understating an obligation is the worst answer available.
    """
    if UNCOVERED is None:
        pytest.skip("every candidate market now has a pack — a good problem")
    reporting, source = cp.reporting_for(UNCOVERED)
    assert reporting is None and source == ""
    band, source = cp.band_for(180, UNCOVERED)
    assert band is None and source == ""


def test_a_known_pack_without_bands_inherits_the_directive():
    """NL holds no bands of its own, on purpose, and must reach the EU ones."""
    band, source = cp.band_for(180, "NL")
    assert source == "EU", "NL should inherit rather than hold a copy"
    assert band is not None


@pytest.mark.parametrize(
    "headcount,first_report,frequency",
    [
        (600, "2027-06-07", "annually"),
        (250, "2027-06-07", "annually"),
        (249, "2027-06-07", "every 3 years"),
        (150, "2027-06-07", "every 3 years"),
        (149, "2031-06-07", "every 3 years"),
        (100, "2031-06-07", "every 3 years"),
        (99, None, "none"),
    ],
)
def test_directive_article_9_bands(headcount, first_report, frequency):
    """Directive (EU) 2023/970 art. 9, boundary by boundary.

    This is the test that would have caught the defect the package was written
    to fix. `pay_equity_service` told clients for four months that the duty was
    "150+ first report 7 June 2028, annually" — which merges the 250+ and
    150-249 bands, dates the first report a year late, and turns a three-yearly
    duty into an annual one. Every boundary is asserted from both sides,
    because the failure was a boundary that had quietly moved.
    """
    band, source = cp.band_for(headcount, "EU")
    assert band is not None, f"no band for {headcount}"
    assert source == "EU"
    assert band.first_report.value == first_report
    assert band.frequency.value == frequency


def test_no_pack_repeats_the_2028_error():
    """A regression guard against the specific wrong date coming back.

    Cheap, blunt, and aimed at one string. The directive names 2027 and 2031;
    2028 appeared once, from a copy nobody re-read, and stayed for four months.
    """
    for code, pack in cp.load().items():
        if not (pack.reporting and pack.reporting.bands):
            continue
        for b in pack.reporting.bands:
            assert b.first_report.value != "2028-06-07", (
                f"{code}: 2028-06-07 is the miscopied Article 9 date. If a national "
                "implementing act genuinely sets it, cite that act here and delete "
                "this assertion deliberately.")


# ── the crosswalk gate ───────────────────────────────────────────────────────

def test_has_crosswalk_is_about_data_not_nationality():
    """`has_crosswalk` replaced `_is_dutch_client`, and the difference matters.

    The question was never "is this client Dutch". It was "do we hold a
    crosswalk we can honestly render", and those stopped being one question the
    moment a second pack existed.
    """
    assert cp.has_crosswalk("NL") is True
    if UNCOVERED is not None:
        assert cp.has_crosswalk(UNCOVERED) is False
    assert cp.has_crosswalk(None) in (True, False)   # must not raise on no country


@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_every_pack_declares_its_currency_and_languages(code, pack):
    """Small, but it is the field a report formats money with."""
    assert len(pack.currency) == 3 and pack.currency.isupper(), code
    assert pack.languages, f"{code} declares no language"


def test_the_dutch_crosswalk_renderer_is_not_offered_another_market():
    """The landmine this test exists to hold down.

    `_is_dutch_client()` now delegates to `has_crosswalk`, which is the right
    question. But the renderer behind that gate draws ISF and CATS, which are
    Dutch Metalektro institutions. An unnarrowed `has_crosswalk("BE")` answers
    True the day the Belgian pack leaves STUB, and the screen would then put a
    Belgian client's staff onto Dutch salarisgroepen beside euro monthly scales.
    That is the original failure returning through a more general door, so the
    call site passes system="ISF" and this asserts no other market can claim it.
    """
    for code, pack in cp.load().items():
        allowed = cp.has_crosswalk(code, system="ISF")
        if code == "NL":
            assert allowed, "the Dutch pack must still reach its own crosswalk"
        else:
            assert not allowed, (
                f"{code} would be offered the Dutch ISF/CATS renderer. Either that pack "
                "genuinely holds an ISF crosswalk, or the gate has widened too far.")


def test_the_gate_is_actually_narrowed_at_the_call_site():
    """A guard on the call site, not just on the helper.

    The helper defaults `system=None`, which is the permissive answer. If a
    future edit drops the argument the tests above still pass and the bug is
    live, so the source is checked directly — the same tactic the dependency
    map tests use.
    """
    import pathlib
    src = pathlib.Path(cp.__file__).parent.parent.parent / "ui" / "views" / "pay_equity.py"
    text = src.read_text(encoding="utf-8")
    assert 'has_crosswalk(system="ISF")' in text, (
        "the Dutch crosswalk gate must name the system it renders")


# ── what the independent verification pass corrected ─────────────────────────
#
# An agent checked every legal claim in these packs against primary sources on
# 2026-09-05 and found four factual errors and five over-strong hardness
# markers. The tests below hold down the corrections that could plausibly be
# re-broken, because each one was wrong in a way that looked entirely
# reasonable on the page.


def test_german_tarifbindung_earns_the_longer_reporting_cycle():
    """EntgTranspG section 22, which this pack first had backwards.

    Written from secondary sources as "every 3 years if bound by a collective
    agreement, otherwise every 5". Para 22(1) gives tarifgebunden and
    tarifanwendend employers *alle fuenf Jahre*; para 22(2) gives everybody else
    *alle drei Jahre*. Tarifbindung earns the LONGER cycle.

    The intuition that being covered by a collective agreement means more
    obligation, not less, is what made the inversion easy to write and easy to
    read past. So it is asserted rather than trusted.
    """
    band, source = cp.band_for(600, "DE")
    assert source == "DE"
    freq = band.frequency.value.lower()
    five = freq.index("5") if "5" in freq else -1
    three = freq.index("3") if "3" in freq else -1
    assert five >= 0 and three >= 0, f"expected both cycles named: {freq!r}"
    assert "tarif" in freq, f"the cycle depends on Tarifbindung and must say so: {freq!r}"
    assert five < three, (
        "the five-year cycle must be the one attached to Tarifbindung. "
        f"got {freq!r} — check EntgTranspG section 22 before changing this test.")


def test_article_4_criteria_are_a_floor_not_a_closed_set():
    """Art. 4(4) is an open list, and the constant must not read as closed.

    The article says the criteria "shall include skills, effort, responsibility
    and working conditions, and, if appropriate, any other factors which are
    relevant to the specific job or position". A four-item tuple presented as
    "the four criteria" invites an evaluation that scores those and stops,
    which under-implements the article while looking complete.
    """
    from services.country_packs import eu

    assert eu.EQUAL_VALUE_CRITERIA_MINIMUM == (
        "skills", "effort", "responsibility", "working conditions")
    claim = eu.EQUAL_VALUE_CRITERIA
    assert isinstance(claim, cp.Claim), (
        "the criteria must carry a hardness and a source like every other legal claim, "
        "not sit outside the package's own discipline as a bare tuple")
    assert claim.hardness == cp.WET and claim.source
    assert "open" in claim.note.lower() or "any other factor" in claim.note.lower(), (
        "the note must say the list is open, or the constant reads as exhaustive")


@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_hard_law_claims_cite_something_a_reader_can_open(code, pack):
    """A WET marker whose source cannot be reached is unfalsifiable.

    Belgium failed this in substance: the 2012 law was cited by an ELI
    permalink that resolves to the ELI help page rather than to the statute,
    and the neighbouring numac reaches an unrelated traffic law. The claim was
    correct and the citation was not, which is the worst combination — it reads
    as checked and cannot be checked. This asserts the shape of a citation, not
    that the URL resolves, which no offline test can know.
    """
    def claims(obj):
        rep = obj.reporting
        if rep:
            yield rep.transposed
            for c in (rep.national_law, rep.joint_assessment_trigger_pct,
                      rep.pre_existing_duty):
                if c is not None:
                    yield c
            for b in rep.bands:
                yield b.first_report
                yield b.frequency
        for cw in obj.crosswalks:
            yield cw.source
        for c in obj.pay_components:
            yield c

    for c in claims(pack):
        if c.hardness != cp.WET:
            continue
        src = (c.source or "").strip()
        assert src, f"{code}: a WET claim with no source: {c.value!r}"
        assert src.startswith("http") or "/" in src or ".md" in src, (
            f"{code}: WET claim cites {src!r}, which is not a document anybody can open")


# ── the currency guard ───────────────────────────────────────────────────────

def test_currency_warning_is_silent_while_every_pack_is_euro():
    """It must not cry wolf. Today NL, BE, DE and EU are all EUR."""
    from services.pay_equity_service import _currency_notes
    assert _currency_notes(("NL", "BE", "DE")) == []
    assert _currency_notes(("NL",)) == []
    assert _currency_notes(()) == []


def test_currency_warning_fires_when_units_differ(monkeypatch):
    """Proven with a stand-in market, because the real one does not exist yet.

    The guard is written for Poland and every pack today is EUR, so shipping it
    unexercised would mean the first time it ever runs is in front of a client
    with a Polish roster. A fake PL pack costs nothing and turns "it should
    fire" into "it fires, and this is the sentence it produces".

    The stand-in is deliberately minimal: only `currency` matters to this code
    path, and inventing a plausible-looking Polish legal claim to pad it out
    would be exactly the thing test_only_what_was_seen warns about.
    """
    from services import country_packs as cp
    from services import pay_equity_service as pes

    fake_pl = cp.CountryPack(country="PL", name="Poland (stand-in)",
                             currency="PLN", languages=("pl",), status=cp.STUB)
    real = cp.for_country

    def patched(country=None):
        if (country or "").upper() == "PL":
            return fake_pl
        return real(country)

    monkeypatch.setattr(cp, "for_country", patched)

    notes = pes._currency_notes(("NL", "PL"))
    assert len(notes) == 1
    note = notes[0]
    assert note.startswith("CURRENCY:")
    assert "EUR: NL" in note and "PLN: PL" in note, (
        f"the note must name which country is in which unit, got: {note}")
    assert "does not convert" in note, (
        "the note must stay consistent with country_service, which refuses to convert")

    # Two euro countries alongside the non-euro one still warn, and the euro
    # group is listed together rather than one line per country.
    grouped = pes._currency_notes(("NL", "BE", "PL"))[0]
    assert "EUR: BE, NL" in grouped, grouped


def test_currency_warning_ignores_markets_we_hold_no_pack_for():
    """An unknown country has no currency we can claim to know.

    Guessing that an uncovered EU market is EUR would often be right and would
    still be a guess, and the same guess about Poland, Sweden or Denmark would
    be wrong. Silence on what we do not hold is the rule the reporting resolver
    follows too.
    """
    from services.pay_equity_service import _currency_notes
    if UNCOVERED is None:
        pytest.skip("every candidate market now has a pack — a good problem")
    assert _currency_notes(("NL", UNCOVERED)) == []


# ── what France and Spain added to the picture ───────────────────────────────

def test_spain_has_a_duty_at_one_employee():
    """The finding that breaks "you grow into a reporting duty".

    RD 902/2020 art. 5.1 requires the registro retributivo of every employer
    "al margen de su tamano". A screen that gates a register behind a headcount
    tells a twelve-person Spanish employer they are out of scope when they have
    been in default since 2020. Asserted at 1 employee because that is the
    number the statute actually reaches.
    """
    for headcount in (1, 3, 12, 49, 99):
        band, source = cp.band_for(headcount, "ES")
        assert source == "ES" and band is not None, headcount
        assert band.first_report.value is not None, (
            f"Spain must report a live duty at {headcount} employees")


def test_france_covers_the_band_the_directive_would_have_got_wrong():
    """France is why the resolver refuses to inherit.

    The EU baseline says no duty below 100. The Index applies from 50, annually,
    with a penalty of up to 1% of payroll. A French client at 80 handed the
    directive's bands would have been told they were out of scope.
    """
    band, source = cp.band_for(80, "FR")
    assert source == "FR", "France must answer from its own law, not the baseline"
    assert band.first_report.value is not None
    assert band.frequency.value == "annually"

    eu_band, _ = cp.band_for(80, "EU")
    assert eu_band.first_report.value is None, (
        "premise: the directive imposes no duty at 80, which is exactly why "
        "inheriting it for France would understate the obligation")


@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_point_bands_are_contiguous_and_ordered(code, pack):
    """A gap or an overlap in a point table silently misgrades somebody.

    Métallurgie is the first crosswalk outside ISF that may show real points:
    the joint branch publishes the cotation-to-groupe table openly, so the
    numbers here were transcribed rather than derived. Transcription is where
    an off-by-one lives, and a job scoring 42 landing in no groupe at all, or
    in two, would be a quiet wrong answer about somebody's classification.
    """
    for cw in pack.crosswalks:
        if not cw.point_bands:
            continue
        bands = list(cw.point_bands)
        for name, lo, hi in bands:
            assert lo <= hi, f"{code}/{cw.system}: {name} runs {lo}-{hi}"
        for (n1, _, hi1), (n2, lo2, _) in zip(bands, bands[1:]):
            assert lo2 == hi1 + 1, (
                f"{code}/{cw.system}: {n1} ends {hi1} and {n2} starts {lo2} — "
                "a point score between them belongs to no group")


def test_metallurgie_point_table_matches_the_published_grid():
    """Nine groupes A-I over 6 to 60 points, transcribed from the branch PDF.

    Secondary sources widely say EIGHT groupes. The convention says nine, and
    the joint UIMM/CFDT/CFE-CGC/FO grid agrees. This asserts the endpoints and
    the count so the majority-but-wrong version cannot drift back in.
    """
    fr = cp.load()["FR"]
    metal = next(c for c in fr.crosswalks if "métallurgie" in c.system.lower())
    assert metal.publishes_point_table is True, (
        "the whole point of Métallurgie is that the table IS public, unlike CATS, "
        "PC 200 and ERA")
    assert metal.groups == ("A", "B", "C", "D", "E", "F", "G", "H", "I")
    assert len(metal.point_bands) == 9, "nine groupes, not the widely repeated eight"
    assert metal.point_bands[0][1] == 6, "the scale starts at 6, not 0 or 1"
    assert metal.point_bands[-1][2] == 60, "and ends at 60"


# ── Poland: the first non-euro pack ──────────────────────────────────────────

def test_the_letter_m_means_opposite_things_in_two_packs_and_both_are_right():
    """The clearest argument for holding gender codes per country.

    In Poland `M` is mężczyzna — male. In Spain the same letter is undecidable:
    *mujer* in an H/M file, *masculino* in a Masculino/Femenino file, with both
    vocabularies appearing inside one official ministry workbook. So the Spanish
    pack maps `m` to NEITHER sex on purpose while the Polish pack maps it to
    male, and a single global lookup table could not be right about both.

    This asserts the divergence deliberately, so that a later tidy-up that
    "harmonises" the tables has to argue with a test instead of silently
    inverting one country's results.
    """
    pl = cp.load()["PL"].gender_codes
    es = cp.load()["ES"].gender_codes

    assert "m" in pl["male"], "Polish M is mężczyzna"
    assert "k" in pl["female"], "Polish K is kobieta, and nothing else recognises it"

    assert "m" not in es["male"] and "m" not in es["female"], (
        "Spanish M is undecidable and must stay unmapped — see es.py. If this ever "
        "fails, a file with an unresolved M is being guessed at rather than refused.")
    assert "h" in es["male"], "Spanish H is hombre, which is how H/M files resolve"


def test_poland_makes_the_currency_warning_real():
    """The guard was written for this and shipped silent. Now it fires.

    Until Poland landed, every pack was EUR and the only exercise of this code
    path was a stand-in. This is the same assertion against a real pack, which
    is what the earlier test was standing in for.
    """
    from services.pay_equity_service import _currency_notes

    assert cp.load()["PL"].currency == "PLN"
    notes = _currency_notes(("NL", "PL"))
    assert len(notes) == 1
    assert "EUR: NL" in notes[0] and "PLN: PL" in notes[0]


def test_a_market_with_a_live_duty_is_never_told_it_is_ahead_of_the_law():
    """The most expensive sentence this product could produce.

    Belgium, France, Spain and Poland all bind employers today under law that
    predates or bypasses Directive 2023/970. Telling those clients to treat the
    analysis as "getting ahead of the law" would say they are early when they
    are in fact behind an existing obligation.
    """
    from services.pay_equity_service import _reporting_duty_notes

    for code in ("BE", "FR", "ES", "PL"):
        pack = cp.load()[code]
        assert pack.reporting.pre_existing_duty, f"premise: {code} has a national duty"
        text = " ".join(_reporting_duty_notes((code,), 300))
        assert "getting ahead of the law" not in text or "Do NOT read this" in text, (
            f"{code} has a live national duty and must not be framed as early")

    # And the inverse still works: a market with no national duty of its own
    # keeps the framing that is correct for it.
    nl = " ".join(_reporting_duty_notes(("NL",), 300))
    assert "getting ahead of the law" in nl


def test_poland_says_no_reporting_duty_positively_rather_than_by_silence():
    """Absence and non-coverage must not look identical on screen.

    Poland genuinely has no pay-gap reporting duty at any size — verified by
    searching the Kodeks pracy for the words that would create one. An uncovered
    market also produces no duty. Those are completely different answers for a
    client, so Poland carries an explicit 0-and-up band that says "none" instead
    of simply having no bands and falling silent.
    """
    band, source = cp.band_for(300, "PL")
    assert source == "PL", "Poland must answer for itself, not inherit the directive"
    assert band is not None, "the answer is 'none', which is not the same as no answer"
    assert band.first_report.value is None and band.frequency.value == "none"

    if UNCOVERED is not None:
        other, other_source = cp.band_for(300, UNCOVERED)
        assert other is None and other_source == "", (
            "an uncovered market gives no band at all — that is the distinction")


# ── the capability slots and the spine ───────────────────────────────────────
#
# The packs were first built around one question — what must this employer
# report about pay — and that was too narrow. Jobsy also does job architecture,
# skills, compensation, the 9-box and the org chart, and each lands differently
# per market. These tests hold the seam that carries the rest.


def test_the_spine_refuses_the_two_dimensions_that_have_no_reference():
    """The refusals are the design, not a gap in it.

    Grades and money have no neutral unit. ISF, ERA, PC 200 and the Metallurgie
    groupes are separate institutions with no legal equivalence, and a euro
    figure next to a zloty one means three different things depending on
    whether you convert at an FX rate, at purchasing power parity, or against a
    labour-cost index. `bridge()` must decline both and say why, because a
    confident arrow between two grades is precisely the invention this whole
    package exists to prevent.
    """
    for dimension in (cp.GRADE, cp.PAY):
        assert cp.SPINE[dimension] is None
        result = cp.bridge("NL", "DE", dimension)
        assert result["ok"] is False
        assert result["refusal"] and len(result["refusal"]) > 80, (
            f"{dimension} must be refused WITH a reason a reader can act on")

    grade = cp.bridge("NL", "DE", cp.GRADE)["refusal"].lower()
    assert "no legal equivalence" in grade
    pay = cp.bridge("NL", "PL", cp.PAY)["refusal"].lower()
    assert "purchasing power" in pay and "rate" in pay


def test_the_spine_exists_for_the_two_dimensions_that_have_one():
    """Occupation and qualification route through real, official references."""
    assert cp.SPINE[cp.OCCUPATION] == "ISCO-08"
    assert cp.SPINE[cp.QUALIFICATION] == "EQF"


def test_a_bridge_is_two_hops_and_reports_the_weaker_one():
    """A chain is exactly as sound as its softest link.

    Reporting the stronger hardness of the two hops would flatter the answer,
    and a route whose second leg is ONBEVESTIGD is an unverified route however
    solid the first leg was.
    """
    result = cp.bridge("FR", "ES", cp.OCCUPATION)
    assert result["ok"] is True, result.get("refusal")
    assert result["spine"] == "ISCO-08"
    assert len(result["route"]) == 2
    hardnesses = [h["hardness"] for h in result["route"]]
    order = (cp.ONBEVESTIGD, cp.CONVENTIE, cp.UITLEG, cp.WET)
    assert result["hardness"] == min(hardnesses, key=order.index)


def test_bridging_an_uncovered_market_is_refused_not_guessed():
    if UNCOVERED is None:
        pytest.skip("every candidate market now has a pack")
    result = cp.bridge("NL", UNCOVERED, cp.OCCUPATION)
    assert result["ok"] is False and "No country pack" in result["refusal"]


def test_the_employer_unit_differs_per_country_and_each_pack_says_which():
    """The finding that recurred in every pack and was different every time.

    Germany counts per Betrieb, Spain per empresa regardless of centros, Poland
    per pracodawca which follows how the employer organises itself, France per
    entreprise or UES but never per etablissement. "Headcount" has meant four
    different things, and every threshold in the product depends on which one
    applies — so it belongs on the org-structure slot rather than in an
    assumption nobody wrote down.
    """
    expected = {"DE": "betrieb", "ES": "empresa", "PL": "pracodawca",
                "FR": "entreprise"}
    for code, word in expected.items():
        org = cp.load()[code].org_structure
        assert org is not None, f"{code} must answer the org-structure question"
        assert word in str(org.employer_unit.value).lower(), (
            f"{code} employer unit should mention {word!r}, got "
            f"{org.employer_unit.value!r}")

    units = {c: str(p.org_structure.employer_unit.value).lower()
             for c, p in cp.load().items() if p.org_structure}
    assert len(set(units.values())) > 1, (
        "if every pack agreed on the employer unit, this slot would be pointless — "
        "the whole point is that they do not")


def test_an_unanswered_capability_is_visible_rather_than_silent():
    """None means "we have not answered", which is not "there is nothing".

    Coverage should be plannable from the code rather than discovered by a
    client hitting an empty screen.
    """
    gaps = cp.capability_gaps("NL")
    assert isinstance(gaps, dict)
    assert all(v == "not answered" for v in gaps.values())
    # Every pack answers the reporting question by now; that is the one slot
    # the earlier work filled everywhere.
    for code in cp.load():
        assert "reporting" not in cp.capability_gaps(code), code


@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_capability_claims_count_toward_unverified(code, pack):
    """LIVE is a promise about the whole pack, not the pay half.

    If the capability slots were skipped, a pack could be promoted while its
    org-structure or skills claims were guesswork. The Dutch pack is the live
    example: its employer-unit claim is ONBEVESTIGD because nobody checked the
    home market, and that must be enough to keep NL out of LIVE.
    """
    unverified = pack.unverified
    for slot_name in ("job_architecture", "skills", "compensation", "performance",
                      "org_structure"):
        slot = getattr(pack, slot_name)
        if slot is None:
            continue
        for field_name in slot.__dataclass_fields__:
            value = getattr(slot, field_name)
            claims = ([value] if isinstance(value, cp.Claim)
                      else [c for c in (value or ()) if isinstance(c, cp.Claim)]
                      if isinstance(value, tuple) else [])
            for c in claims:
                if not c.verified:
                    assert c in unverified, (
                        f"{code}.{slot_name}.{field_name} holds an unverified claim "
                        "that `unverified` does not report")


# ── what putting six markets on one field revealed ───────────────────────────

def test_bargaining_coverage_spans_a_real_range_and_every_figure_is_sourced():
    """The reason coverage is a field and not a note.

    Belgium is effectively universal, Poland is 11,6%, and the rest sit between.
    That spread is not trivia: at 49% Germany makes "no collective agreement"
    the MODAL case, so a model that assumes a pay scale exists is a Dutch model
    being applied to a market where it fails half the time.

    France is deliberately absent. DARES was unreachable and a coverage rate is
    exactly the kind of number a client quotes back, so it stays None rather
    than being filled with the figure that circulates.
    """
    known = {}
    for code, pack in cp.load().items():
        comp = pack.compensation
        if not (comp and comp.bargaining_coverage):
            continue
        claim = comp.bargaining_coverage
        if claim.value is None:
            assert claim.note, f"{code}: an absent coverage figure must say why"
            continue
        assert 0.0 < claim.value <= 1.0, f"{code}: coverage {claim.value} is not a share"
        assert claim.source, f"{code}: a coverage figure must cite where it came from"
        known[code] = claim.value

    assert len(known) >= 4, "at least four markets should have answered by now"
    assert max(known.values()) - min(known.values()) > 0.5, (
        "if every market clustered, this field would not be earning its place; "
        f"got {known}")


def test_every_market_answers_how_a_sector_agreement_reaches_a_non_member():
    """Similar coverage, completely different machinery — and that is the point.

    The Netherlands extends by ministerial declaration, France by arrêté,
    Belgium by royal decree with a criminal sanction behind it, Germany has the
    mechanism and barely uses it, Poland has none at all, and SPAIN NEEDS NO
    EXTENSION STEP: a statutory convenio binds everyone in scope by force of the
    statute itself. Two markets can reach the same coverage by opposite routes,
    and the route is what decides whether a non-member employer is bound.
    """
    answered = {code: pack.compensation.extension_mechanism
                for code, pack in cp.load().items()
                if pack.compensation and pack.compensation.extension_mechanism}
    assert len(answered) >= 5

    # A None value is a real answer here — it means no mechanism exists — so it
    # has to carry a note, exactly like an absent number.
    for code, claim in answered.items():
        assert claim.note, f"{code}: the mechanism claim must explain itself"
        if claim.value is None:
            assert "none" in claim.note.lower() or "no" in claim.note.lower()

    described = {str(c.value).lower() for c in answered.values() if c.value}
    assert len(described) >= 4, (
        f"the mechanisms should differ market to market; got {described}")


def test_seniority_progression_is_answered_or_explicitly_unknown():
    """The field exists because it is a fairness question, not a compliance one.

    Automatic seniority steps are gender-correlated through career breaks, so a
    market whose scales advance by tenure produces a gap from the structure
    rather than from any decision about a person. Spain measures it — 62,84% of
    convenios — Germany's is in the statute, and France is honestly unknown
    because answering would mean reading 200 conventions. Unknown is allowed;
    silence is not.
    """
    for code, pack in cp.load().items():
        comp = pack.compensation
        if comp is None:
            continue
        claim = comp.seniority_progression
        assert claim is not None, (
            f"{code} has a compensation model but does not say whether pay advances "
            "with tenure — that is the one pay-structure fact that is directly a "
            "fairness question")
        assert claim.note, f"{code}: seniority claim needs its reasoning"
        if claim.value is None:
            assert not claim.verified or "unknown" in claim.note.lower(), (
                f"{code}: an unanswered seniority question must say so plainly")


# ── guarding a hand-transcribed pay table ────────────────────────────────────

def test_salary_scales_are_checked_before_anyone_reads_a_number_off_them():
    """These tables are copied by hand out of a PDF annex.

    Spain's química grid and Poland's local-government ladder are transcribed
    from official annexes, group by group. The two ways that goes wrong both
    look entirely plausible on screen — a key matching no group, and a range
    whose ends are reversed — and both misprice a real person. So `validate()`
    refuses them, and this asserts it keeps refusing.
    """
    def _pack(scales, groups=("1", "2")):
        return cp.CountryPack(
            country="ZZ", name="fixture", currency="EUR", languages=("en",),
            crosswalks=(cp.CrosswalkSpec(
                system="fixture", publishes_point_table=False,
                groups=groups, scales=scales,
                source=cp.Claim("fixture", cp.CONVENTIE, "test", "2026-09-05")),))

    assert not cp.validate(_pack({"1": (100.0, 200.0)})), "a sane scale must pass"

    unknown = cp.validate(_pack({"9": (100.0, 200.0)}))
    assert any("unknown group" in m for m in unknown), unknown

    backwards = cp.validate(_pack({"1": (200.0, 100.0)}))
    assert any("backwards" in m for m in backwards), backwards

    zero = cp.validate(_pack({"1": (0.0, 200.0)}))
    assert any("transcription error" in m for m in zero), zero


@pytest.mark.parametrize("code,pack", ALL_PACKS, ids=PACK_IDS)
def test_a_partial_pay_table_says_it_is_partial(code, pack):
    """Fewer scales than groups is fine. Not saying why is not.

    There are two legitimate reasons a crosswalk holds fewer salary scales than
    it lists groups, and a reader has to be able to tell them apart:

      * The rest of the table exists and we have not captured it yet. Spain's
        química and Poland's samorząd currently hold only the first and last
        rows of a longer published annex.
      * The rest of the table does not exist. The Dutch ISF groups L to Q are
        Hoger Personeel and have no rigid step table at all, so there is
        nothing to hold.

    Both are honest; confusing them is not. Someone who finds two scales against
    nine groups will otherwise assume those two are all there is, and price a
    person off a table they did not know was truncated. This test was written
    for the first case and immediately caught the second, which is the more
    useful outcome — the rule is not "say it is incomplete", it is "account for
    the shortfall".
    """
    for cw in pack.crosswalks:
        if not cw.scales or not cw.groups:
            continue
        if len(cw.scales) >= len(cw.groups):
            continue
        note = (cw.source.note or "").lower()
        accounted_for = (
            # the table continues and we have not transcribed it
            "only", "endpoint", "intermediate", "not captured", "must be read",
            # or the table genuinely stops there
            "no scales", "no rigid", "have no",
        )
        assert any(word in note for word in accounted_for), (
            f"{code}/{cw.system} holds {len(cw.scales)} scales for {len(cw.groups)} "
            "groups and its source note does not account for the shortfall — say either "
            "that the rest was not captured, or that it does not exist")


# ── the transcribed tables, and an invariant that checks one of them ──────────

def test_the_polish_pay_ladder_is_complete_and_monotonic():
    """Twenty categories, twenty figures, each at least the one below it.

    Transcribed from the annex to the 2026 amending regulation. Monotonicity is
    not decoration: a pay ladder that dips would mean a higher category paying
    less than a lower one, which is either a typo or a finding so unusual it
    would need saying out loud. This asserts it is a typo.
    """
    pl = cp.load()["PL"]
    ladder = next(c for c in pl.crosswalks if "zaszeregowania" in c.system)

    assert len(ladder.groups) == 20
    assert len(ladder.scales) == 20, "every category must carry its floor"

    amounts = [ladder.scales[g][0] for g in ladder.groups]
    for lower, higher in zip(amounts, amounts[1:]):
        assert higher >= lower, (
            f"the ladder dips: {lower} then {higher}. Check the transcription against "
            "the annex before assuming it is real.")
    assert amounts[0] < amounts[-1], "a twenty-step ladder should actually climb"


def test_polish_category_one_equals_the_national_minimum_wage():
    """An invariant the regulation itself creates, so it can check the pack.

    The bottom rung of the local-government ladder is set to exactly the
    statutory minimum wage — 4.806 złoty for 2026 — and both numbers were read
    from separate regulations by separate routes. That makes them a free
    cross-check on each other: if a future uplift is transcribed into one and
    not the other, this fails, and it fails on the transcription rather than on
    a client's payslip.

    If Poland ever decouples the two, this test should be changed deliberately
    with the source that shows it — not quietly relaxed.
    """
    pl = cp.load()["PL"]
    ladder = next(c for c in pl.crosswalks if "zaszeregowania" in c.system)
    bottom = ladder.scales[ladder.groups[0]][0]

    minimum = next(c for c in pl.pay_components
                   if isinstance(c.value, tuple) and c.value[0] == "minimum_wage_monthly_pln")
    assert bottom == minimum.value[1], (
        f"category I is {bottom} but the minimum wage is {minimum.value[1]}. One of the "
        "two was updated without the other, or Poland has decoupled them — check which "
        "before changing this test.")


def test_the_spanish_shift_grid_sits_above_the_general_one_at_every_grade():
    """Two national floors for the same eight grades, and the order is fixed.

    Spain's chemical convenio publishes a second guaranteed annual minimum for
    continuous shift work, and it is higher at every grupo because it absorbs
    night pay that the general grid excludes. If a transcription ever put a
    shift figure below its general counterpart, the row was misaligned — which
    is the exact failure the published PDFs invite, since their group labels sit
    one row off from the values.

    The two grids are also why shift share matters to a fairness reading: shift
    work is not evenly distributed by sex, so part of a within-grade gap can be
    a shift-pattern artefact, and the two are only separable if somebody knows
    the share.
    """
    es = cp.load()["ES"]
    general = next(c for c in es.crosswalks if "general" in c.system)
    shift = next(c for c in es.crosswalks if "continuo" in c.system)

    assert general.groups == shift.groups, "the two grids must cover the same grades"
    assert len(general.scales) == len(general.groups) == 8, (
        "eight published rows — grupo 0 is a real grade with no national floor and is "
        "deliberately absent rather than carried as a null")

    for g in general.groups:
        assert shift.scales[g][0] > general.scales[g][0], (
            f"grupo {g}: shift floor {shift.scales[g][0]} is not above the general "
            f"floor {general.scales[g][0]} — check the row alignment before believing it")


def test_the_spanish_floor_is_not_a_base_salary_and_the_pack_says_so():
    """The figure means something other than what its column name suggests.

    The Spanish grid publishes a salario mínimo garantizado: an all-in annual
    floor covering the totality of pay concepts for normal work, explicitly
    excluding seniority, shift, night and holiday premiums, position complements
    and variable incentives. Put beside a client's "salario base" column it
    compares two different quantities and the comparison looks entirely
    reasonable while being wrong.

    That is a note, not a number, so it cannot be asserted arithmetically — but
    it can be asserted that the note exists, because the risk here is that a
    future edit tidies the explanation away and leaves the figure looking
    self-explanatory.
    """
    es = cp.load()["ES"]
    for cw in es.crosswalks:
        note = (cw.source.note or "").lower()
        assert "salario minimo garantizado" in note or "salario mínimo garantizado" in note, (
            f"{cw.system}: the note must name what the figure actually measures")
        assert "not salario base" in note or "not comparable" in note, (
            f"{cw.system}: the note must warn that this is not a base-salary figure")


# ── the reference posture, made enforceable ──────────────────────────────────


def test_occupation_mappings_reference_a_crosswalk_rather_than_carrying_one():
    """A legal position that only holds while the tables stay empty.

    Several of the official occupation crosswalks are free to read and
    restricted to redistribute — the German one requires the employment
    agency's permission for commercial use. This package stays on the reference
    side of that line: it records THAT a correspondence exists and cites where
    the official one is published, and holds none of them.

    While that is true, the permission question is not "may we sell this
    product" but the far narrower "may we ship this particular file", and it
    only arises if somebody decides to ship it. The moment an occupation
    mapping starts carrying rows, that changes — quietly, in a diff that looks
    like an improvement. So it is asserted rather than trusted.

    If a table genuinely needs to be held one day, this test should be changed
    deliberately, with the licence position for that specific file recorded
    alongside it. Do not delete it to make a build pass.
    """
    carrying = []
    for code, pack in cp.load().items():
        for slot in (pack.job_architecture, pack.skills):
            for m in getattr(slot, "mappings", ()) or ():
                if m.dimension == cp.OCCUPATION and m.mapping:
                    carrying.append(f"{code}/{m.local_scheme} ({len(m.mapping)} rows)")
    assert not carrying, (
        "these occupation mappings now carry a crosswalk table rather than citing one: "
        + "; ".join(carrying)
        + ". Check the licence for each file before this ships.")


def test_qualification_mappings_carry_only_what_a_statute_states():
    """The one place a table is legitimate, and why.

    Every qualification mapping here does hold rows, and that is fine for a
    different reason: the correspondence is set out level by level in the law
    itself — the Dutch Besluit NLQF, the French décret, the Spanish real
    decreto, the Polish ZSK act. Reproducing what a statute says is not
    reproducing somebody's dataset.

    So the test is not "no table" but "the table is small, and its source is
    law". A qualification mapping that grew to hundreds of rows would no longer
    be a statutory correspondence; it would be a dataset, and it would need the
    same licence question as an occupation crosswalk.
    """
    found = 0
    for code, pack in cp.load().items():
        for slot in (pack.job_architecture, pack.skills):
            for m in getattr(slot, "mappings", ()) or ():
                if m.dimension != cp.QUALIFICATION or not m.mapping:
                    continue
                found += 1
                assert len(m.mapping) <= 20, (
                    f"{code}/{m.local_scheme} holds {len(m.mapping)} rows. A national "
                    "qualification framework has single-digit levels; this is a dataset "
                    "wearing a statute's clothes.")
                assert m.source.hardness == cp.WET and m.source.source, (
                    f"{code}/{m.local_scheme}: a qualification table is only defensible "
                    "because a statute states it — so it must cite that statute.")
    assert found >= 3, "at least three markets should map qualifications by now"


def test_the_spine_hands_back_a_route_and_never_a_converted_code():
    """`bridge()` answers "how would you get there", not "here is the answer".

    That is the same posture one level up: it composes two documented hops and
    reports the weaker hardness, so a caller can see what the conversion would
    rest on before trusting it. It deliberately does not perform the
    conversion, because performing it would mean holding the tables this
    package does not hold.
    """
    result = cp.bridge("FR", "ES", cp.OCCUPATION)
    assert result["ok"] is True, result.get("refusal")
    assert set(result) == {"ok", "spine", "hardness", "route", "refusal"}
    for hop in result["route"]:
        assert "scheme" in hop and "hardness" in hop
        assert "value" not in hop and "code" not in hop, (
            "a hop describes a correspondence; it does not carry a translated code")


# ── three registers, and the line between them ───────────────────────────────
#
# Elmar asked whether the countersignature on a country pack needs somebody with
# a certification. It does not — verifying that a pack repeats what a statute
# says is fact-checking, and anyone with the text in front of them can do it.
#
# But the question exposed something the packs had not separated. The notes were
# being written as determinations — "at roughly 300 people the reporting duty
# first applies 2027-06-07" — which is not reporting what a directive says, it is
# telling a specific employer what they must do. Nobody here can carry that.
#
# So the notes now run in three registers, and these tests hold the line between
# them: what the source PROVIDES, what the roster LOOKS LIKE against it, and a
# DIRECTION that is worth following whatever the legal answer turns out to be.


def _notes(country, headcount=300):
    from services.pay_equity_service import _reporting_duty_notes
    return _reporting_duty_notes((country,), headcount)


def test_every_reading_opens_with_what_it_is_and_is_not():
    """The statement leads, because a caveat at the bottom is decoration.

    Whatever else the notes say, the first thing a reader meets has to be that
    this reports sources rather than settling a position — and that the
    headcount it just used is not the headcount any of these laws count with.
    """
    for code in cp.load():
        notes = _notes(code)
        assert notes, f"{code} produced no notes at all"
        first = notes[0]
        assert "NOT legal advice" in first
        assert "roster is not any of those counts" in first
        assert "confirm anything you act on" in first


@pytest.mark.parametrize("code", sorted(cp.load()))
def test_the_duty_is_reported_never_determined(code):
    """The register test, and the one that would fail if this slid back.

    A note may say what a text provides for employers of a given size. It may
    not tell this employer what their duty is. The difference is invisible in
    tone and total in consequence, so it is asserted on the actual strings.
    """
    joined = " ".join(_notes(code)).lower()

    for determination in ("your duty", "you must", "you are required",
                          "your obligation", "your deadline"):
        assert determination not in joined, (
            f"{code}: a note says {determination!r}. That settles a position this tool "
            "cannot settle — report what the source provides instead.")

    # And where a duty exists, it is attributed to the instrument rather than
    # attached to the reader.
    if any("provides that employers of" in n for n in _notes(code)):
        assert "a roster is not the count the law uses" in joined, (
            f"{code}: states a bracket without saying the roster is not that count")


@pytest.mark.parametrize("code", sorted(cp.load()))
def test_every_reading_offers_a_direction(code):
    """Descriptive is not the same as useless, and Elmar was right to say so.

    Refusing to say anything actionable would be safe for us and worthless for
    the client — a different kind of dishonesty. The third register carries
    work that is worth doing whatever the legal answer turns out to be, which
    is exactly the class of statement nobody needs a certification to make.
    """
    notes = _notes(code)
    direction = next((n for n in notes if "WHERE THE WORK PAYS OFF" in n), None)
    assert direction, f"{code}: no direction offered — the reading is a citation, not help"

    assert "MEDIAN" in direction, "the median is the measure most exports do not compute"
    assert "BY CATEGORY OF WORKERS" in direction

    # A direction points; it does not instruct.
    low = direction.lower()
    for instruction in ("you must", "you are required", "your duty"):
        assert instruction not in low, (
            f"{code}: the direction instructs rather than points — {instruction!r}")


def test_a_pack_holds_one_mapping_per_dimension():
    """Two mappings for the same hop is how a verified fact got hidden.

    Four markets carried both an early sketch on the job-architecture slot and
    a later sourced mapping on the skills slot, written weeks apart. `bridge()`
    took whichever was declared first, which was reliably the older one — so
    routes reported ONBEVESTIGD while a WET mapping sat unused two slots away.

    Nothing errored. The route simply understated its own evidence, which
    punishes exactly the caller who is doing the right thing by checking the
    hardness before trusting the hop. That is worse than a loud failure.
    """
    for code, pack in cp.load().items():
        seen: dict[str, list[str]] = {}
        for slot in (pack.job_architecture, pack.skills):
            for m in getattr(slot, "mappings", ()) or ():
                seen.setdefault(m.dimension, []).append(m.local_scheme)
        for dimension, schemes in seen.items():
            assert len(schemes) == 1, (
                f"{code} holds {len(schemes)} {dimension} mappings: {schemes}. Keep the "
                "best-evidenced one and delete the rest — a superseded claim also sits "
                "in `unverified` forever and asks somebody to re-check a settled fact.")


def test_the_bridge_prefers_the_best_evidenced_hop():
    """Belt as well as braces, since the test above can only see today's packs.

    Deleting the duplicates fixes what exists; sorting by hardness stops the
    next one winning on declaration order. Either alone leaves the trap set.
    """
    order = (cp.ONBEVESTIGD, cp.CONVENTIE, cp.UITLEG, cp.WET)
    for code, pack in cp.load().items():
        got = cp._mappings_for(pack, cp.OCCUPATION)
        if len(got) < 2:
            continue
        ranks = [order.index(m.source.hardness) for m in got]
        assert ranks == sorted(ranks, reverse=True), (
            f"{code}: mappings are not offered best-first, so bridge() may route "
            "through weaker evidence than the pack holds")


# ── the slots reach a screen ─────────────────────────────────────────────────
#
# Four capability slots sat in the packs for a day with nothing reading them.
# A grep across services, ui, core and tools found zero references to
# job_architecture, compensation, performance or org_structure outside the
# package itself — so the German works-council finding, the Elternzeit finding
# and the four meanings of "headcount" existed only in the code. Written down
# and unreachable is the same as not written down.


def test_the_market_notes_render_for_every_pack():
    """Every market must be able to say what it changes about how you work."""
    from services import market_notes

    for code in cp.load():
        if code == cp.BASELINE:
            continue
        for fn in (market_notes.org_structure_notes, market_notes.performance_notes):
            notes = fn(code)
            if not notes:
                continue
            assert notes[0].endswith("."), f"{code}: the heading should be a sentence"

            # One line is legitimate, but only when it is the line that says so.
            # Belgium holds no performance slot, and admitting that is the
            # designed answer — it tells a reader the silence is ours and not
            # the market's. A bare heading with nothing under it is the failure.
            if len(notes) == 1:
                assert "no answer is held" in notes[0], (
                    f"{code}/{fn.__name__} produced a heading and nothing under it. "
                    "Either say something, or say plainly that nothing is held.")


def test_a_note_carries_its_own_weight():
    """A reader who never opens the source still has to know what they have.

    The packs carry hardness on every claim; the screen is where that becomes
    visible to somebody who will never read the code. An UNVERIFIED claim and a
    statutory one must not look alike in a list of bullets.
    """
    from services import market_notes

    from services.market_notes import _line

    # Test the mechanism, not today's contents. The first version of this test
    # asserted that Germany HAD an unverified performance claim — and then broke
    # the moment somebody answered it, which is the wrong thing to defend. What
    # must hold is that each weight is marked, whichever pack happens to carry it.
    for hardness, expected in (
        (cp.ONBEVESTIGD, "UNVERIFIED — "),
        (cp.UITLEG, "Reading of the law rather than its words — "),
        (cp.CONVENTIE, "Collective-agreement practice, not statute — "),
    ):
        claim = cp.Claim("v", hardness, "src" if hardness != cp.ONBEVESTIGD else "",
                         "2026-09-06", note="a claim")
        assert _line(claim) == expected + "a claim", hardness

    # Statute gets no prefix, which is the only reason the others mean anything.
    assert _line(cp.Claim("v", cp.WET, "src", "2026-09-06", note="a claim")) == "a claim"

    # And the real German reading is still labelled as a reading.
    de = market_notes.performance_notes("DE")
    assert any(n.startswith("Reading of the law rather than its words — ") for n in de), (
        "the §87 readings are UITLEG and must not be dressed as statute")


def test_a_stale_claim_says_so_on_the_screen():
    """The decay policy has to be visible, not just modelled.

    A claim that has outlived its review interval keeps speaking — silence
    would throw away information that is usually still correct — but it says
    how old it is, so the reader can weigh it.
    """
    from datetime import date
    from services.market_notes import _line

    fresh = cp.Claim("x", cp.WET, "src", "2026-09-01", note="a fact",
                     review_after_months=6)
    assert _line(fresh, date(2026, 9, 5)) == "a fact"

    old = cp.Claim("x", cp.WET, "src", "2026-01-01", note="a fact",
                   review_after_months=6)
    line = _line(old, date(2026, 9, 5))
    assert line.startswith("STALE (8 months"), line
    assert line.endswith("a fact"), "the claim must still be readable, not suppressed"


def test_both_views_actually_call_the_panel():
    """Guarding the call site, not just the helper.

    The whole defect was a function nothing invoked. A test that only exercises
    market_notes would have passed all day while the screen stayed empty.
    """
    import pathlib
    views = pathlib.Path(cp.__file__).parent.parent.parent / "ui" / "views"
    for name, kind in (("nine_box.py", "performance"), ("organigram.py", "org_structure")):
        text = (views / name).read_text(encoding="utf-8")
        assert f'_market_panel("{kind}")' in text, (
            f"{name} defines or imports the panel but never calls it for {kind}")


def test_an_occupation_bridge_is_not_evidence_about_pay():
    """ISCO classifies what a job DOES, not what it is worth.

    ISCO-08 groups jobs by their main tasks and by the skill level and
    specialisation those tasks require. It prescribes nothing about pay,
    grading or progression. So a successful occupation bridge says two jobs are
    comparable in what they do — not that they should be paid alike.

    That distinction is a live risk in THIS product specifically, because an
    ISCO match is exactly the evidence somebody would reach for to argue that a
    cross-border pay difference is unjustified. It is not that evidence: equal
    value under the directive turns on skills, effort, responsibility and
    working conditions assessed against a job-evaluation instrument, and ISCO
    carries at most two of those, for statistical comparison rather than
    valuation.

    The refusal of the pay and grade dimensions is what enforces it, so this
    asserts the two cannot be reached even when the occupation hop succeeds.
    """
    occupation = cp.bridge("NL", "DE", cp.OCCUPATION)
    assert occupation["ok"], "premise: the occupation hop works between these two"

    for dimension in (cp.PAY, cp.GRADE):
        blocked = cp.bridge("NL", "DE", dimension)
        assert not blocked["ok"], (
            f"{dimension} became bridgeable. A working occupation route must not open a "
            "pay or grade one — ISCO carries neither.")

    spine_note = (cp.load()["EU"].skills.occupation_taxonomy.note or "").lower()
    assert "main tasks" in spine_note and "skill level" in spine_note, (
        "the EU pack must say what ISCO classifies ON, or a reader cannot tell what a "
        "match does and does not establish")
    assert "pay" in spine_note

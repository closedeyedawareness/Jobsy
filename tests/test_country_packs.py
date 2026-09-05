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

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
    several member states are stricter than it. France's Index applies from 50
    employees, so a French client handed the EU bands would be told they have
    no duty at 60 when they have one. Understating an obligation is the worst
    available answer, and worse than saying France is not covered yet.
    """
    assert "FR" not in cp.load(), "this test's premise is that FR has no pack yet"
    reporting, source = cp.reporting_for("FR")
    assert reporting is None and source == ""
    band, source = cp.band_for(180, "FR")
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
    assert cp.has_crosswalk("FR") is False
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

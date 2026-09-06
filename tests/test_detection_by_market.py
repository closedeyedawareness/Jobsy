"""
tests/test_detection_by_market.py

Does the code read the codes the market actually ships?

The defect these tests were written against was a gender rule shaped like one
country: `F`/`V` -> female, `M` -> male, first letter only. That is a Dutch M/V
export written out in Python, and against the real code sets it fails four
different ways -- Polish `K` and German `W` disappear into "unknown", French
`H` disappears into "unknown", and Spanish `M` (*Mujer*) is read as a man,
which does not tilt the gap, it deletes one sex and analyses the other against
nobody.

So the tests are table-driven over the six live markets and they use the REAL
packs. Fixtures would only prove this file agrees with itself; the claim worth
holding is that the code and the knowledge layer agree, and that the day a pack
changes its codes the analysis changes with it.
"""

import pandas as pd
import pytest

from services import country_packs
from services.pay_equity_service import (
    AmbiguousGenderCodes,
    analyze_gender_pay_gap,
)
from ui.shared import _detect_fte_pair, _smart_detect


@pytest.fixture(autouse=True)
def _no_pack_cache_bleed():
    country_packs.load(refresh=True)
    yield


def _use_market(monkeypatch, code):
    """Point `country_packs.for_country(None)` at one market.

    The seam under test: nothing gets a `country=` parameter, the active
    country resolves through `country_service.active_country()`, and both the
    analyser and the column detector follow it.
    """
    from services import country_service
    monkeypatch.setattr(country_service, "active_country", lambda: code)


# ── the codes each market's own pack says its files use ──────────────────────
#
# (country, female code, male code) -- taken from what a payroll export in that
# market really contains, and each one must be present in that pack.
MARKET_CODES = [
    ("NL", "V", "M"),      # Man / Vrouw
    ("BE", "V", "M"),      # Dutch-speaking Belgium
    ("BE", "F", "H"),      # French-speaking Belgium: Femme / Homme
    ("DE", "W", "M"),      # Weiblich / Maennlich
    ("FR", "F", "H"),      # Femme / Homme
    ("PL", "K", "M"),      # Kobieta / Mezczyzna
    ("ES", "Mujer", "Hombre"),   # spelled out: the only unambiguous Spanish form
]


@pytest.mark.parametrize("country,f_code,m_code", MARKET_CODES)
def test_pack_holds_the_codes_its_market_ships(country, f_code, m_code):
    pack = country_packs.for_country(country)
    assert pack is not None, f"no pack for {country}"
    assert f_code.lower() in pack.gender_codes["female"], (
        f"{country}: {f_code!r} is what this market calls a woman")
    assert m_code.lower() in pack.gender_codes["male"], (
        f"{country}: {m_code!r} is what this market calls a man")


def _roster(f_code, m_code, *, n=6):
    """A workforce paid identically per grade, half women, half men.

    Identically paid on purpose: any gap this produces is a reading error, not
    a pay difference, so the assertion can be exact rather than directional.
    """
    rows = []
    for i in range(n):
        rows.append({"Function": "P", "Level": "3",
                     "Gender": f_code if i % 2 else m_code,
                     "Salary": 50_000})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("country,f_code,m_code", MARKET_CODES)
def test_every_market_resolves_its_own_codes(monkeypatch, country, f_code, m_code):
    _use_market(monkeypatch, country)
    r = analyze_gender_pay_gap(_roster(f_code, m_code),
                               function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")
    assert r.n_f == 3, f"{country} {f_code}: women lost to 'unknown' ({r.n_f} found)"
    assert r.n_m == 3, f"{country} {m_code}: men lost to 'unknown' ({r.n_m} found)"
    assert r.n_excluded == 0
    assert r.mean_gap_pct == 0.0


@pytest.mark.parametrize("country,f_code,m_code", MARKET_CODES)
def test_the_woman_is_not_counted_as_a_man(monkeypatch, country, f_code, m_code):
    """The Spanish failure, stated as a property that must hold everywhere.

    One woman among five men must read as one woman. The old rule made her a
    man in Spain and made her nothing in Poland and Germany; both show up here
    as `n_f == 0`, which is the shape of every wrong answer this can give.
    """
    _use_market(monkeypatch, country)
    df = _roster(f_code, m_code, n=6).copy()
    df["Gender"] = [m_code] * 5 + [f_code]
    r = analyze_gender_pay_gap(df, function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")
    assert (r.n_m, r.n_f) == (5, 1), f"{country}: read as {r.n_m} men / {r.n_f} women"


def test_the_dutch_rule_would_have_failed_these(monkeypatch):
    """Name the bug, so a revert cannot pass quietly.

    Under `F/V -> female, M -> male`, every one of these lands in 'unknown' or
    in the wrong bucket. If someone restores that rule these assertions are the
    ones that fail, with the market named.
    """
    for country, f_code in (("PL", "K"), ("DE", "W")):
        _use_market(monkeypatch, country)
        r = analyze_gender_pay_gap(_roster(f_code, "M"),
                                   function_col="Function", level_col="Level",
                                   gender_col="Gender", salary_col="Salary")
        assert r.n_f == 3, f"{country}: {f_code} must be a woman, not an unknown"

    _use_market(monkeypatch, "FR")
    r = analyze_gender_pay_gap(_roster("F", "H"),
                               function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")
    assert r.n_m == 3, "FR: H (homme) must be a man, not an unknown"


def test_full_words_read_as_well_as_letters(monkeypatch):
    _use_market(monkeypatch, "PL")
    r = analyze_gender_pay_gap(_roster("Kobieta", "Mezczyzna"),
                               function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")
    assert (r.n_m, r.n_f) == (3, 3)


# ── the Spanish refusal ──────────────────────────────────────────────────────

def test_spanish_M_is_refused_not_guessed(monkeypatch):
    """`M` in a Spanish file is *Mujer* or *male*, and both appear officially.

    es.py leaves `m` out of both lists deliberately and says such a column must
    be rejected to a prompt. Guessing produces a gap of the right magnitude and
    the wrong sign -- filed with a regulator, that is not recoverable, and a
    lost import is.
    """
    _use_market(monkeypatch, "ES")
    with pytest.raises(AmbiguousGenderCodes) as exc:
        analyze_gender_pay_gap(_roster("M", "H"),
                               function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")
    assert exc.value.country == "ES"
    assert exc.value.codes == ("m",)


def test_spanish_M_against_F_is_refused_too(monkeypatch):
    """The other Spanish vocabulary: M/F, where M is *masculino*.

    Same letter, opposite sex, and the file carries nothing that decides it.
    """
    _use_market(monkeypatch, "ES")
    with pytest.raises(AmbiguousGenderCodes):
        analyze_gender_pay_gap(_roster("F", "M"),
                               function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")


def test_spelled_out_spanish_is_accepted(monkeypatch):
    """The refusal must be narrow. Mujer / Hombre decides itself, so it runs."""
    _use_market(monkeypatch, "ES")
    r = analyze_gender_pay_gap(_roster("Mujer", "Hombre"),
                               function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")
    assert (r.n_m, r.n_f) == (3, 3)


def test_only_spain_refuses(monkeypatch):
    """No other live pack has an undecidable letter, and none may acquire one
    by accident: a pack that starts refusing ordinary files is a regression as
    real as one that guesses."""
    refusing = []
    for country in ("NL", "BE", "DE", "FR", "PL"):
        _use_market(monkeypatch, country)
        for codes in (("F", "M"), ("V", "M"), ("W", "M"), ("K", "M"), ("F", "H")):
            try:
                analyze_gender_pay_gap(_roster(*codes),
                                       function_col="Function", level_col="Level",
                                       gender_col="Gender", salary_col="Salary")
            except AmbiguousGenderCodes as e:
                refusing.append((country, codes, e.codes))
    assert refusing == [], f"unexpected refusals: {refusing}"


def test_unknown_codes_stay_unknown_not_ambiguous(monkeypatch):
    """`X` is an answer, not a collision. It must keep being excluded and
    counted, exactly as before, in every market."""
    for country in ("NL", "DE", "ES", "PL"):
        _use_market(monkeypatch, country)
        df = _roster("Mujer" if country == "ES" else "F",
                     "Hombre" if country == "ES" else "M", n=6)
        df.loc[0, "Gender"] = "X"
        r = analyze_gender_pay_gap(df, function_col="Function", level_col="Level",
                                   gender_col="Gender", salary_col="Salary")
        assert r.n_excluded == 1, country


def test_german_divers_is_not_read_as_a_truncated_word(monkeypatch):
    """`D` (divers) must not fall through to the initial-letter pass. It is a
    third answer the pack states, not a shortened Frau."""
    _use_market(monkeypatch, "DE")
    df = _roster("W", "M", n=6)
    df.loc[0, "Gender"] = "D"
    r = analyze_gender_pay_gap(df, function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")
    assert r.n_excluded == 1
    assert (r.n_m, r.n_f) == (2, 3)


def test_a_market_with_no_pack_is_no_worse_than_before(monkeypatch):
    """An uncovered market keeps today's M/F/V behaviour. Adding markets must
    not be paid for by breaking the one that already worked."""
    _use_market(monkeypatch, "ZZ")
    assert country_packs.for_country("ZZ") is None
    r = analyze_gender_pay_gap(_roster("V", "M"),
                               function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")
    assert (r.n_m, r.n_f) == (3, 3)


def test_a_pooled_roster_reads_each_row_in_its_own_market(monkeypatch):
    """A multinational roster is several markets, not one.

    With the active country NL, a Polish `K` read under the Dutch pack is an
    unknown. The roster carries its own country column, so each market's rows
    are read with that market's pack -- otherwise the pooled file reproduces
    the original defect for every row that is not Dutch.
    """
    _use_market(monkeypatch, "NL")
    df = pd.DataFrame([
        {"Function": "P", "Level": "3", "Gender": g, "Salary": 50_000, "Country": c}
        for c, g in [("NL", "V"), ("NL", "M"), ("NL", "V"), ("NL", "M"),
                     ("PL", "K"), ("PL", "M"), ("PL", "K"), ("PL", "M")]
    ])
    r = analyze_gender_pay_gap(df, function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary",
                               country_col="Country")
    assert (r.n_m, r.n_f) == (4, 4), "Polish women fell into 'unknown' under the NL pack"


def test_the_analysis_says_which_pack_it_used(monkeypatch):
    """A number produced under a market's rules should say so; the reader
    cannot check a normalisation they were never told about."""
    _use_market(monkeypatch, "PL")
    r = analyze_gender_pay_gap(_roster("K", "M"),
                               function_col="Function", level_col="Level",
                               gender_col="Gender", salary_col="Salary")
    assert any("country pack" in n for n in r.notes)


# ── column detection ─────────────────────────────────────────────────────────

#: The header a real export in each market carries, and the concept it is.
#: Every one of these is invisible to the English+Dutch inline lists.
MARKET_HEADERS = [
    ("PL", "gender", "Płeć"),
    ("PL", "salary", "Wynagrodzenie zasadnicze"),
    ("PL", "function", "Stanowisko"),
    ("ES", "gender", "Sexo"),
    ("ES", "salary", "Salario base"),
    ("DE", "gender", "Geschlecht"),
    ("FR", "gender", "Sexe"),
]

#: What each concept's call site passes today, copied from ui/views/pay_equity.py.
_CALLSITE = {
    "gender": ({"gender", "geslacht", "sex", "m/v", "m/f"},
               ["gender", "geslacht", "sex"]),
    "salary": ({"salary", "salaris", "pay", "basesalary", "base salary"},
               ["salary", "salaris", "pay"]),
    "function": ({"function", "functie", "jobfamily", "job family", "family"},
                 ["function", "functie", "family"]),
    "fte": ({"fte", "parttime", "part-time", "part time", "werkuren", "deeltijd"},
            ["fte", "deeltijd", "parttime"]),
}


@pytest.mark.parametrize("country,concept,header", MARKET_HEADERS)
def test_smart_detect_finds_the_market_its_own_headers(monkeypatch, country, concept, header):
    _use_market(monkeypatch, country)
    exacts, contains = _CALLSITE[concept]
    cols = ["Employee", header, "Amount"]
    found = _smart_detect(cols, exacts, contains)
    if header.strip().lower() in country_packs.for_country(country).vocabulary.get(concept, ()):
        assert found == header, f"{country}: {header!r} is in the pack and was not found"
    else:
        pytest.skip(f"{country} pack does not list {header!r} for {concept} — "
                    f"a pack gap, not a code defect")


def test_pack_path_does_not_disturb_the_existing_lists(monkeypatch):
    """The inline English/Dutch lists still win where they always did.

    Deleting them in the same change would swap one untested detector for
    another. The pack is additive until it is proved, so every header that
    resolves today must resolve to the same column.
    """
    exacts, contains = _CALLSITE["gender"]
    for country in ("NL", "DE", "ES", "PL", "FR", "BE", "ZZ"):
        _use_market(monkeypatch, country)
        assert _smart_detect(["Name", "Geslacht", "Salaris"], exacts, contains) == "Geslacht"
        assert _smart_detect(["Name", "Gender", "Salary"], exacts, contains) == "Gender"


def test_concept_can_be_named_explicitly(monkeypatch):
    """The inferred concept is a convenience for call sites this change does
    not own; a caller that knows should be able to say so."""
    _use_market(monkeypatch, "PL")
    assert _smart_detect(["Płeć"], set(), [], concept="gender") == "Płeć"
    assert _smart_detect(["Płeć"], set(), []) is None


# ── the Polish FTE trap ──────────────────────────────────────────────────────

def test_polish_fte_pair_is_detected():
    cols = ["Nazwisko", "Licznik_wymiaru_etatu", "Mianownik_wymiaru_etatu", "Brutto"]
    assert _detect_fte_pair(cols) == ("Licznik_wymiaru_etatu", "Mianownik_wymiaru_etatu")


def test_a_half_of_the_pair_is_never_offered_as_the_fte_column(monkeypatch):
    """1 and 2 mean half time. Handing back the `1` reads a half-timer as
    full-time -- no error, no blank cell, and the resulting overstatement lands
    on part-time staff, who skew female. No FTE is the honest answer until the
    ratio has a consumer; the caller then says "no FTE column" on screen.
    """
    _use_market(monkeypatch, "PL")
    exacts, contains = _CALLSITE["fte"]
    cols = ["Nazwisko", "Licznik_wymiaru_etatu", "Mianownik_wymiaru_etatu", "Brutto"]
    assert _smart_detect(cols, exacts, contains) is None


def test_a_real_polish_fte_column_is_still_found(monkeypatch):
    """The refusal is only for the split pair. `Wymiar etatu` is a number."""
    _use_market(monkeypatch, "PL")
    exacts, contains = _CALLSITE["fte"]
    assert _smart_detect(["Nazwisko", "Wymiar etatu"], exacts, contains) == "Wymiar etatu"


# ── the pair comes from the pack, not from a second copy ─────────────────────

def test_the_pair_is_read_from_the_country_pack():
    """One fact, one place.

    Until 6 September 2026 this lived twice: `pl.py` held
    `FTE_RATIO_PAIRS` with the vendor's full column names and a note saying
    nothing read it, while `ui/shared.py` held its own `licznik`/`mianownik`
    under a comment claiming the pack "does not mark them as a pair". That
    comment was true when written and false by the time it mattered. Two
    hand-written lists of one fact drift, and the half that drifts is the one
    nobody opens.
    """
    from services.country_packs import pl
    from ui.shared import _pack_fte_pairs

    pairs = _pack_fte_pairs()
    assert pairs, "no pack is offering an FTE ratio pair"
    for numerator, denominator in pl.FTE_RATIO_PAIRS:
        assert (numerator.lower(), denominator.lower()) in pairs, (
            f"{numerator}/{denominator} is in the Polish pack but the detector "
            "does not see it -- the pack is talking and nothing is listening")


def test_a_shortened_column_name_is_still_caught():
    """The pack holds `licznik_wymiaru_etatu`; an export may say `Licznik`.

    The hand-written list this replaces matched on the short fragment, so
    switching to the pack's full names could have narrowed the refusal without
    anything failing -- a regression hidden inside a tidy-up. Both directions
    are tested because only one of them was ever exercised before.
    """
    assert _detect_fte_pair(["Nazwisko", "Licznik", "Mianownik", "Brutto"]) == (
        "Licznik", "Mianownik")


def test_half_a_pair_is_not_a_pair():
    """A numerator with no denominator is not a fraction, and refusing there
    would hide a column that may genuinely be something else."""
    assert _detect_fte_pair(["Nazwisko", "Licznik_wymiaru_etatu", "Brutto"]) is None
    assert _detect_fte_pair(["Nazwisko", "FTE", "Brutto"]) is None


def test_the_refusal_does_not_depend_on_the_active_market(monkeypatch):
    """A Polish column name is a fact about the FILE, not about the session.

    The two mistakes here do not cost the same. Refusing a Polish numerator
    while the market is set to NL costs one sentence on screen; failing to
    refuse reads a half-timer as full-time and moves the gap. So the detector
    reads the union over every pack, and this test is what stops a later
    "only the active market" tidy-up from looking harmless.
    """
    cols = ["Naam", "Licznik_wymiaru_etatu", "Mianownik_wymiaru_etatu", "Brutto"]
    _use_market(monkeypatch, "NL")
    assert _detect_fte_pair(cols) == ("Licznik_wymiaru_etatu", "Mianownik_wymiaru_etatu")
    exacts, contains = _CALLSITE["fte"]
    assert _smart_detect(cols, exacts, contains) is None

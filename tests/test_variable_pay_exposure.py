"""
Structural variable-pay exposure — the part of the Directive's "pay" that base
salary alone cannot see.

The cases that matter are the two ways this can be wrong: reporting a widening
that isn't there, and staying silent about one that is.
"""

import pandas as pd
import pytest

from services.pay_equity_service import analyze_variable_pay_exposure


PAYMIX = pd.DataFrame([
    {"Function": "Eng", "Level": "Junior", "TargetVariablePct": 3,  "ThirteenthMonthPct": 8.33, "LTIEligible": "No"},
    {"Function": "Eng", "Level": "Lead",   "TargetVariablePct": 18, "ThirteenthMonthPct": 8.33, "LTIEligible": "Yes"},
])


def _grid(n_male_lead, n_female_lead, n_male_junior, n_female_junior, salary=60000):
    """A leveled grid with identical base pay everywhere, so any gap that shows
    up can only have come from the variable structure."""
    rows = []
    for _ in range(n_male_lead):
        rows.append({"Function": "Eng", "Level": "Lead", "Gender": "M", "Salary": salary})
    for _ in range(n_female_lead):
        rows.append({"Function": "Eng", "Level": "Lead", "Gender": "F", "Salary": salary})
    for _ in range(n_male_junior):
        rows.append({"Function": "Eng", "Level": "Junior", "Gender": "M", "Salary": salary})
    for _ in range(n_female_junior):
        rows.append({"Function": "Eng", "Level": "Junior", "Gender": "F", "Salary": salary})
    return pd.DataFrame(rows)


def _run(df, paymix=PAYMIX):
    return analyze_variable_pay_exposure(
        df, paymix, function_col="Function", level_col="Level",
        gender_col="Gender", salary_col="Salary")


def test_identical_base_pay_still_reveals_a_gap_when_men_hold_the_bonus_seats():
    # Every person earns exactly the same base. Men fill Lead, women fill Junior.
    # Base gap is zero; the scheme still pays men more.
    r = _run(_grid(n_male_lead=10, n_female_lead=0, n_male_junior=0, n_female_junior=10))
    assert r.base_mean_gap_pct == pytest.approx(0.0, abs=1e-9)
    assert r.widening_pp is not None and r.widening_pp > 0
    assert r.structure_widens_gap
    # 18% target vs 3% — men are entitled to 15 points more variable pay.
    assert r.target_var_gap_pp == pytest.approx(15.0)
    # LTI is a cliff at Lead: every man eligible, no woman.
    assert r.pct_men_lti_eligible == 100.0
    assert r.pct_women_lti_eligible == 0.0
    assert r.lti_access_gap_pp == 100.0


def test_even_representation_reports_no_widening():
    r = _run(_grid(n_male_lead=6, n_female_lead=6, n_male_junior=6, n_female_junior=6))
    assert r.widening_pp == pytest.approx(0.0, abs=1e-9)
    assert not r.structure_widens_gap
    assert r.target_var_gap_pp == pytest.approx(0.0)
    assert r.lti_access_gap_pp == pytest.approx(0.0)


def test_women_in_the_bonus_seats_narrows_rather_than_widens():
    r = _run(_grid(n_male_lead=0, n_female_lead=10, n_male_junior=10, n_female_junior=0))
    assert r.widening_pp is not None and r.widening_pp < 0
    assert not r.structure_widens_gap
    assert any("narrows" in n for n in r.notes)


def test_a_cohort_missing_from_paymix_is_excluded_and_named_not_zeroed():
    df = _grid(6, 6, 6, 6)
    df = pd.concat([df, pd.DataFrame([
        {"Function": "Sales", "Level": "Lead", "Gender": "M", "Salary": 60000}] * 4)])
    r = _run(df)
    assert r.n_unmatched == 4
    assert ("Sales", "Lead") in r.unmatched_keys
    assert r.n_matched == 24
    # Excluded, not silently treated as a 0% variable cohort — which would have
    # invented a gap out of a missing reference row.
    assert any("unknown, not zero" in n for n in r.notes)


def test_small_samples_are_suppressed_rather_than_published():
    r = _run(_grid(n_male_lead=2, n_female_lead=1, n_male_junior=1, n_female_junior=1))
    assert r.widening_pp is None
    assert r.pct_women_lti_eligible is None
    assert any("suppressed" in n for n in r.notes)


def test_dutch_m_v_labels_analyse_natively():
    df = _grid(10, 0, 0, 10)
    df["Gender"] = df["Gender"].map({"M": "Man", "F": "Vrouw"})
    r = _run(df)
    # Would silently produce an all-male analysis if the M/V fold were missing.
    assert r.n_matched == 20
    assert r.pct_men_lti_eligible == 100.0
    assert r.pct_women_lti_eligible == 0.0


def test_every_result_says_it_is_policy_not_measurement():
    r = _run(_grid(6, 6, 6, 6))
    assert any("POLICY ENTITLEMENT" in n for n in r.notes)


def test_real_library_paymix_joins_the_real_salary_band_grain():
    """The join this whole feature rests on: PayMix and SalaryBands must share
    a (Function, Level) key set, or the exposure read silently covers a subset."""
    xl = pd.ExcelFile("jobsy_reference_library.xlsx")
    pm, sb = xl.parse("PayMix"), xl.parse("SalaryBands")
    assert set(zip(pm.Function, pm.Level)) == set(zip(sb.Function, sb.Level))


# ── the typed record is the route the product uses ───────────────────────────

def test_the_typed_pay_mix_gives_the_same_answer_as_the_frame():
    """PayMix reached this analysis as a raw frame until it joined the library.
    Both routes must agree, or the screen showing exposure and the screen
    showing total reward are reading two different libraries."""
    from core.models import PayMixEntry

    df = _grid(4, 1, 1, 4)
    typed = {(r["Function"], r["Level"]): PayMixEntry(
                function=r["Function"], level=r["Level"],
                target_variable_pct=float(r["TargetVariablePct"]),
                thirteenth_month_pct=float(r["ThirteenthMonthPct"]),
                lti_eligible_text=str(r["LTIEligible"]))
             for _, r in PAYMIX.iterrows()}

    a = _run(df, PAYMIX)
    b = _run(df, typed)

    assert a.n_matched == b.n_matched
    assert a.pct_women_lti_eligible == b.pct_women_lti_eligible
    assert a.pct_men_lti_eligible == b.pct_men_lti_eligible


def test_an_empty_typed_pay_mix_says_what_is_missing():
    with pytest.raises(ValueError, match="Function and Level"):
        _run(_grid(2, 2, 2, 2), {})


# ── the mixed roster, which the two analyses used to disagree about ───────

def _mixed_nl_es_roster():
    """One roster, two markets, and a letter that means opposite things.

    `M` is *mujer* in a Spanish H/M file and `man` in a Dutch M/V one. A single
    normalisation over both rows therefore has to be wrong about one of them,
    and the direction of the error is a reversal rather than a blur: the Spanish
    women are counted as men and the Spanish men vanish.
    """
    import pandas as pd
    return pd.DataFrame([
        {"Function": "Finance", "Level": "Senior", "Gender": "M",
         "Salary": 70000, "FTE": 1.0, "Country": "NL"},   # Dutch M = man
        {"Function": "Finance", "Level": "Senior", "Gender": "V",
         "Salary": 60000, "FTE": 1.0, "Country": "NL"},   # Dutch V = vrouw
        {"Function": "Finance", "Level": "Senior", "Gender": "H",
         "Salary": 70000, "FTE": 1.0, "Country": "ES"},   # hombre = man
        {"Function": "Finance", "Level": "Senior", "Gender": "M",
         "Salary": 60000, "FTE": 1.0, "Country": "ES"},   # mujer = WOMAN
    ])


def test_a_mixed_roster_is_read_market_by_market_once_the_country_is_passed():
    """The last gap between the two figures that share a screen.

    `analyze_gender_pay_gap` learned to read each row with its own market's
    pack; this function did not, because no country column was threaded into
    it. On a single-market roster that made no difference — which is why the
    earlier fix looked finished — but on a mixed one the exposure figure and the
    gap figure were computed over differently-normalised populations, with
    nothing on the screen saying so.

    The contrast IS the harm, and it is measured here rather than described.
    Given the same four rows:

        without a country   ['male', 'female', '', 'male']
        with a country      refuses

    Read under the session's Dutch pack, the Spanish `M` — *mujer*, a woman —
    is counted as a man, and the Spanish `H` — *hombre*, a man — resolves to
    nothing at all and is dropped. One woman becomes a man and one man
    disappears, in a variable-pay exposure analysis whose entire output is a
    comparison between the sexes.

    Read per market, the Spanish rows raise instead: `M` is genuinely
    undecidable in that market's payroll exports, and this file gives no way to
    tell which convention produced it. A refusal is the correct answer and a
    plausible number is not.
    """
    import pandas as pd
    import pytest
    from services.pay_equity_service import (_gender_classes, FEMALE, MALE,
                                             AmbiguousGenderCodes)

    df = _mixed_nl_es_roster()

    # Without the country column: silently wrong, in the direction that matters.
    blind = list(_gender_classes(df["Gender"], None)[0])
    assert blind[2] != MALE, "the Spanish hombre used to survive; this test is stale"
    assert blind[3] == MALE, (
        "the Spanish mujer used to be counted as a man — if that no longer "
        "happens the defect this guards is gone and the test should be reread")

    # With it: the Spanish half is read with the Spanish pack, which refuses.
    with pytest.raises(AmbiguousGenderCodes) as refusal:
        _gender_classes(df["Gender"], df["Country"])
    assert "ES" in str(refusal.value), (
        "the refusal does not name the market it came from, so a reader cannot "
        "tell which half of their roster is the problem")

    # And the Dutch half on its own still resolves, so this is a per-market
    # refusal and not a whole-file one.
    dutch = df[df["Country"] == "NL"]
    assert list(_gender_classes(dutch["Gender"], dutch["Country"])[0]) == [MALE, FEMALE]


def test_the_country_column_survives_the_column_subset():
    """A parameter that is accepted and then dropped is worse than one that is
    absent: the signature promises per-market normalisation and the function
    quietly delivers the session's.

    The subset inside the function keeps only the columns it was told about, so
    country_col has to be in that set. It is asserted separately because the
    failure is silent — the analysis still returns a perfectly plausible number.
    """
    import inspect
    from services import pay_equity_service as pes

    src = inspect.getsource(pes.analyze_variable_pay_exposure)
    subset = next(line for line in src.splitlines() if "d = df[[" in line
                  or (line.strip().startswith("d = df[[")))
    following = src[src.index("d = df[["):]
    assert "country_col" in following.split("]].copy()")[0], (
        "country_col is accepted by the signature but filtered out before use")

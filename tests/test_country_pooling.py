"""
A workforce in two countries is two pay markets, not one population.

This is a regression test for a measured defect, not a hypothetical one. Before
`country_col` existed, a roster split between the Netherlands and Poland —
built so that pay is gender-blind INSIDE each country — was reported as a
**27.0% adjusted gender pay gap, statistically significant**, with nothing
anywhere mentioning country.

That matters beyond a wrong number. The EU Pay Transparency Directive triggers a
joint pay assessment at a 5% gap, so a multinational could be pushed into formal
remediation over an artefact of who happens to work where. Jobsy is being sold
to multinationals, so a mixed roster is the expected input, not an edge case.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.pay_equity_service import analyze_gender_pay_gap


def _two_country_roster(seed: int = 7) -> pd.DataFrame:
    """A roster where pay is gender-blind BY CONSTRUCTION inside each country.

    Salary is a function of country and level only — gender never enters it. Any
    gender gap this produces is therefore an artefact, and the size of the
    artefact comes from the two countries paying very differently while employing
    different proportions of women.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for country, base, n, female_share in (("NL", 55_000, 300, 0.35),
                                           ("PL", 25_000, 300, 0.70)):
        for _ in range(n):
            level = rng.choice(["4", "5", "6"])
            rows.append({
                "country": country,
                "function": rng.choice(["B", "P"]),
                "level": level,
                "gender": "F" if rng.random() < female_share else "M",
                "salary": round(base * (1 + 0.12 * int(level)) * rng.normal(1.0, 0.03)),
            })
    return pd.DataFrame(rows)


def _analyse(df, **kw):
    return analyze_gender_pay_gap(
        df, function_col="function", level_col="level",
        gender_col="gender", salary_col="salary", **kw)


def test_each_country_alone_shows_no_gap():
    """The premise. If either country showed a gap on its own, the rest of this
    file would be testing the fixture rather than the code."""
    df = _two_country_roster()
    for country in ("NL", "PL"):
        r = _analyse(df[df.country == country])
        assert abs(r.adjusted_gap_pct) < 2.0, (
            f"{country} alone shows {r.adjusted_gap_pct:+.1f}% — the fixture is "
            f"not gender-blind, so nothing below means what it claims")


def test_country_is_controlled_for_and_the_artefact_disappears():
    """The fix. With country supplied, the adjusted gap tells the truth."""
    df = _two_country_roster()
    r = _analyse(df, country_col="country")

    assert r.countries == ("NL", "PL")
    assert r.country_controlled is True
    assert "country" in r.adjusted_controls_used
    assert abs(r.adjusted_gap_pct) < 2.0, (
        f"adjusted gap is {r.adjusted_gap_pct:+.1f}% on gender-blind data; "
        f"country is not actually being controlled for")
    assert not r.adjusted_significant, (
        "a gap that does not exist is being reported as statistically significant")


def test_the_headline_gap_still_pools_and_therefore_must_say_so():
    """The mean and median gaps are what they are — you cannot 'adjust' a
    headline. So the requirement is that the result SAYS the number pools two
    pay markets, in terms someone about to file a report would act on."""
    df = _two_country_roster()
    r = _analyse(df, country_col="country")

    assert r.mean_gap_pct > 10, (
        "the fixture no longer produces a large pooled headline gap, so this "
        "test is not exercising the situation it was written for")

    country_notes = [n for n in r.notes if "countr" in n.lower()]
    assert country_notes, "a two-country roster produced no note about country"
    joined = " ".join(country_notes).lower()
    assert "2 countries" in joined
    assert "nl" in joined and "pl" in joined
    # The two things a reader must not miss.
    assert "per-country" in joined or "per country" in joined, \
        "the note does not say the directive obligation is per country"
    assert "should not be read" in joined or "not be read" in joined, \
        "the note does not warn against reading the headline as a finding"


def test_a_single_country_roster_is_not_burdened_with_the_warning():
    """Most clients are in one country. They should not be told their data
    spans markets, and the adjusted figure should not gain a useless control."""
    df = _two_country_roster()
    r = _analyse(df[df.country == "NL"], country_col="country")

    assert r.countries == ("NL",)
    assert r.country_controlled is False
    assert "country" not in r.adjusted_controls_used
    assert not [n for n in r.notes if "spans" in n.lower()]


def test_omitting_the_country_column_is_stated_rather_than_assumed():
    """Silence is the failure this whole file is about. If nobody said which
    country anyone works in, the result must say that it assumed one market."""
    df = _two_country_roster()
    r = _analyse(df)

    assert r.countries == ()
    assert r.country_controlled is False
    notes = " ".join(r.notes).lower()
    assert "one pay market" in notes or "single pay market" in notes, \
        "analysing without a country column made no statement about it"


def test_country_values_are_normalised_not_multiplied():
    """'nl', 'NL ' and 'Nl' are one market. Treating them as three would split
    a country into fragments and silently weaken every cohort."""
    df = _two_country_roster()
    messy = df.copy()
    rng = np.random.default_rng(3)
    messy["country"] = [
        rng.choice([c, c.lower(), f" {c} ", c.title()]) for c in messy["country"]
    ]
    r = _analyse(messy, country_col="country")
    assert r.countries == ("NL", "PL"), f"got {r.countries}"


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_rows_with_no_country_do_not_become_a_country(blank):
    """A blank is missing information, not a market called ''."""
    df = _two_country_roster()
    df.loc[df.index[:20], "country"] = blank
    r = _analyse(df, country_col="country")
    assert "" not in r.countries and "NAN" not in r.countries
    assert set(r.countries) <= {"NL", "PL"}

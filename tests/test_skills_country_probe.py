"""
tests/test_skills_country_probe.py

Adversarial probe of the skills/assessment/benefits/CAO/country area, written
fresh against the current code rather than derived from it. Two kinds of
result live here on purpose:

  * tests that FAIL against current code -- each one is a demonstrated defect,
    documented in its docstring with the concrete input, the actual output,
    and what a correct answer would have been.
  * tests that PASS -- adversarial cases that were attacked and held up,
    kept here as regression guards.

country_service.py is the newest file in the area (written today) and gets
the most attack surface. cao_crosswalk_service.py and benefits_service.py are
probed specifically for the "silently gives Dutch/single-market answers to a
non-Dutch client" failure mode, which is the country-dimension equivalent of
the pooling bug already found in pay equity (tests/test_country_pooling.py).

Per the ground rules for this probe: nothing here edits an existing file,
and country_service is exercised by monkeypatching `registry()` /
`active_country()`, the same pattern tests/test_currency_display.py uses,
rather than standing up Streamlit.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ═════════════════════════════════════════════════════════════════════════
# country_service.money() -- adversarial numeric inputs
# ═════════════════════════════════════════════════════════════════════════

@pytest.fixture
def cs(monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT))
    from services import country_service
    registry = [
        {"code": "NL", "name": "Netherlands", "currency": "EUR", "is_live": True},
        {"code": "PL", "name": "Poland", "currency": "PLN", "is_live": True},
    ]
    monkeypatch.setattr(country_service, "registry", lambda refresh=False: registry)
    monkeypatch.setattr(country_service, "active_country", lambda: "NL")
    return country_service


def test_money_with_decimals_emits_two_periods_not_dutch_convention(cs):
    """services/country_service.py:156

        formatted = f"{n:,.{decimals}f}".replace(",", ".")

    This blanket ',' -> '.' replace is fine at decimals=0 (every call site in
    ui/app.py today uses the default), but `decimals` is a real, documented
    parameter of the public function, and Python's own thousands-comma AND
    the decimal point both get rewritten to '.', producing two periods with
    no way to tell which one is the decimal marker.

    Input: money(1234.56, country="NL", decimals=2)
    Actual:   '€1.234.56'   -- ambiguous; could be misread as 1,234,560-ish
    Expected: '€1.234,56'   -- the Dutch convention the module's own
              docstring claims to follow ("thousands separator here follows
              the existing Dutch convention... for every currency").

    Human consequence: any screen that shows cents -- an hourly rate, a
    benefit value, a CAO scale figure -- renders a number a reader cannot
    parse unambiguously. This is not the documented "known simplification"
    (single thousands separator); it is the decimal separator itself going
    missing.
    """
    assert cs.money(1234.56, country="NL", decimals=2) == "€1.234,56"


def test_money_positive_infinity_is_not_caught_by_the_nan_guard(cs):
    """services/country_service.py:146-154

    The function already guards NaN explicitly (`n != n`) because "NaN
    survives float() and would render as €nan" -- a bug this file's own
    comment says was already found once. Infinity survives the same
    float() conversion, is not NaN (`inf == inf` is True), and is not
    caught by any guard here.

    Input: money(float('inf'))
    Actual:   '€inf'
    Expected: '—' (same treatment as NaN -- a non-finite value is not a
              salary any more than a missing one is).

    Human consequence: a spreadsheet formula error (e.g. #DIV/0! coerced to
    inf, or a runaway pandas computation) reaching this function renders as
    a plausible-looking salary string on a real report instead of the dash
    that flags "this is not usable data" -- exactly the failure mode the
    NaN guard exists to prevent, just for infinity instead of NaN.
    """
    assert cs.money(float("inf")) == "—", "positive infinity rendered as a number"


def test_money_negative_infinity_is_not_caught_either(cs):
    """Same defect, other sign. Actual: '€-inf'."""
    assert cs.money(float("-inf")) == "—", "negative infinity rendered as a number"


def test_money_refuses_booleans_rather_than_treating_them_as_amounts(cs):
    """services/country_service.py:146-147

        n = float(value)

    `float(True) == 1.0` and `float(False) == 0.0` in Python, so a stray
    boolean -- a checkbox column read wrong, a truthy/falsy flag passed by
    mistake -- is silently accepted as a valid amount.

    Actual:   money(True)  == '€1'
              money(False) == '€0'
    Expected: '—' for both -- a bool was never a salary, and per this
              module's own stated philosophy ("zero and unknown are
              different facts about somebody's pay"), False rendering as
              '€0' is indistinguishable on screen from an actual zero salary.

    Human consequence: lower confidence than the infinity/decimal findings
    (whether callers can ever pass a real bool here is a data-pipeline
    question this test doesn't answer), but if a boolean column value ever
    reaches money(), a person's pay would silently read as "€0" instead of
    surfacing as bad input.
    """
    assert cs.money(True) == "—", f"True rendered as {cs.money(True)!r}"
    assert cs.money(False) == "—", f"False rendered as {cs.money(False)!r}"


# ── things that were attacked and held up (regression guards) ──────────────

@pytest.mark.parametrize("bad", [
    float("nan"), None, "", "   ", "n/a", "1,000", "not a number",
])
def test_money_still_refuses_the_original_bad_inputs(cs, bad):
    assert cs.money(bad) == "—", f"{bad!r} rendered as {cs.money(bad)!r}"


def test_money_accepts_strings_with_stray_whitespace_and_underscores(cs):
    """float() itself tolerates these, and money() should too."""
    assert cs.money(" 90000 ") == "€90.000"
    assert cs.money("90_000") == "€90.000"


def test_money_handles_decimal_and_negative_and_large_values_without_crashing(cs):
    import decimal
    assert cs.money(decimal.Decimal("90000")) == "€90.000"
    assert cs.money(-5000).startswith("€")
    assert cs.money(1e20).endswith("000")


def test_currency_for_normalizes_case_and_whitespace(cs):
    assert cs.currency_for("pl") == "PLN"
    assert cs.currency_for(" PL ") == "PLN"
    assert cs.currency_for(" pl ") == "PLN"


def test_currency_for_unknown_code_falls_back_without_raising(cs):
    assert cs.currency_for("ZZ") == "EUR"
    assert cs.symbol_for("ZZ") == "€"
    assert cs.name_for("ZZ") == "ZZ"


# ═════════════════════════════════════════════════════════════════════════
# country_service.has_reference_data() -- exception-path reachability
# ═════════════════════════════════════════════════════════════════════════

class _FakeResp:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data_by_country, raise_on=()):
        self._data_by_country = data_by_country
        self._raise_on = raise_on
        self._country = None

    def select(self, *_a, **_k):
        return self

    def eq(self, _col, value):
        self._country = value
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        if self._country in self._raise_on:
            raise RuntimeError("simulated PostgREST failure")
        return _FakeResp(self._data_by_country.get(self._country, []))


class _FakeTable:
    def __init__(self, query):
        self._query = query

    def table(self, _name):
        return self._query


@pytest.fixture
def hrd(monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT))
    from services import country_service
    monkeypatch.setattr(country_service, "active_country", lambda: "NL")
    return country_service


def test_has_reference_data_true_when_the_country_itself_has_rows(hrd, monkeypatch):
    from services import auth_service
    fake = _FakeTable(_FakeQuery({"NL": [{"country": "NL"}]}))
    monkeypatch.setattr(auth_service, "db", lambda: fake)
    assert hrd.has_reference_data("NL") is True


def test_has_reference_data_false_when_neither_country_nor_eu_has_rows(hrd, monkeypatch):
    """This is the exact case the module's own comment says a browser test
    caught before: a naive `resp.count` check reads a dropped Content-Range
    header as falsy and says "no data" even when 45 bands are loaded. The
    current code deliberately checks `resp.data` instead -- confirm that
    holds for the genuine "nothing at all" case too."""
    from services import auth_service
    fake = _FakeTable(_FakeQuery({"BE": [], "EU": []}))
    monkeypatch.setattr(auth_service, "db", lambda: fake)
    assert hrd.has_reference_data("BE") is False


def test_has_reference_data_falls_back_to_eu_baseline(hrd, monkeypatch):
    from services import auth_service
    fake = _FakeTable(_FakeQuery({"BE": [], "EU": [{"country": "EU"}]}))
    monkeypatch.setattr(auth_service, "db", lambda: fake)
    assert hrd.has_reference_data("BE") is True


def test_has_reference_data_fails_open_when_the_client_is_unreachable(hrd, monkeypatch):
    from services import auth_service
    monkeypatch.setattr(auth_service, "db", lambda: None)
    assert hrd.has_reference_data("NL") is True


def test_has_reference_data_fails_open_when_the_query_itself_raises(hrd, monkeypatch):
    from services import auth_service
    fake = _FakeTable(_FakeQuery({}, raise_on=("NL", "EU")))
    monkeypatch.setattr(auth_service, "db", lambda: fake)
    assert hrd.has_reference_data("NL") is True


# ═════════════════════════════════════════════════════════════════════════
# live_countries() -- filter integrity
# ═════════════════════════════════════════════════════════════════════════

def test_live_countries_never_offers_eu_even_when_flagged_live(cs, monkeypatch):
    from services import country_service
    monkeypatch.setattr(country_service, "registry", lambda refresh=False: [
        {"code": "EU", "name": "EU baseline", "currency": "EUR", "is_live": True},
        {"code": "NL", "name": "Netherlands", "currency": "EUR", "is_live": True},
    ])
    codes = [c["code"] for c in country_service.live_countries()]
    assert "EU" not in codes
    assert codes == ["NL"]


# ═════════════════════════════════════════════════════════════════════════
# cao_crosswalk_service -- Netherlands-only by design; does it know that?
# ═════════════════════════════════════════════════════════════════════════

def test_the_dutch_crosswalk_is_gated_on_the_client_being_dutch():
    """ISF and CATS are Dutch collective agreements -- Metalektro / FME / De
    Leeuw Consult -- encoded in cao_crosswalk_service as CODE precisely because
    they are Netherlands-specific institutions rather than numbers that vary by
    country. Germany's ERA and France's conventions collectives are different
    institutions again, not different constants.

    The functions themselves still take no `country`, and that is fine: they are
    Dutch functions and answering a Dutch question is all they claim to do. What
    matters is that nothing ASKS them a non-Dutch question. Both render sites
    gate on _is_dutch_client(), which is what this asserts. It lives in
    ui/views/pay_equity.py -- the page split moved the pay-equity screens out of
    ui/app.py, and the two sites share one predicate so they cannot drift.

    Before the gate, a Polish or Swedish client saw their grades positioned onto
    Dutch salarisgroepen with "Maandschaal 2026" euro figures beside them and
    nothing on screen saying the structure was Dutch -- implying a legal
    classification, and so misstating what a non-Dutch worker is owed.
    """
    from ui.views import pay_equity as pe
    assert hasattr(pe, "_is_dutch_client"), (
        "nothing decides whether the Dutch crosswalk applies to this client"
    )

    from unittest.mock import patch
    from services import country_service
    for code, expected in (("NL", True), ("PL", False), ("SE", False), ("DE", False)):
        with patch.object(country_service, "active_country", lambda c=code: c):
            assert pe._is_dutch_client() is expected, (
                f"a client in {code} is {'not ' if expected else ''}being offered "
                f"the Dutch CAO crosswalk"
            )


def _cao_crosswalk_render_block(source: str, marker: str) -> str:
    """Extract the source text of one '# ── CAO crosswalk ...' UI section,
    from its marker comment up to (not including) the next '# ──' section
    marker at the same indentation. Anchored on the marker text rather than
    line numbers, so it survives unrelated edits elsewhere in the file."""
    lines = source.splitlines()
    start = next(i for i, l in enumerate(lines) if marker in l)
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("# ──")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def test_both_ui_crosswalk_sites_are_behind_the_market_gate():
    """The gate has to be on BOTH render sites, and a structural check is the
    right kind: ui/app.py renders the crosswalk in the leveled-gap mode and
    again in the compa-ratio / pay_equity path, and it would be easy to guard
    one and forget the other -- which is how the screens diverged in the first
    place.

    Extracted by each section's own marker comment rather than by line number,
    so this survives unrelated edits above it.
    """
    # Searched across the whole UI tree rather than one file: the page split
    # moved the pay-equity screens into ui/views/, and a guard pinned to
    # ui/app.py would have gone on passing while checking nothing.
    marker = "# ── CAO crosswalk (ISF / CATS®, indicative, public bands only) ──"
    sites = []
    for path in sorted((ROOT / "ui").rglob("*.py")):
        lines = path.read_text().splitlines()
        for i, l in enumerate(lines):
            if marker.rstrip("─") in l:
                sites.append((path.name, i, lines))
    assert len(sites) >= 2, (
        f"expected both CAO crosswalk render sites somewhere under ui/, found {len(sites)}")

    ungated = []
    for name, idx, lines in sites:
        end = next((j for j in range(idx + 1, len(lines))
                    if lines[j].lstrip().startswith("# ──")), len(lines))
        block = "\n".join(lines[idx:end])
        if "_is_dutch_client" not in block:
            ungated.append(f"{name}:{idx + 1}")
    assert not ungated, (
        "these CAO crosswalk render sites are not behind the market gate, so a "
        "non-Dutch client would be shown Dutch collective-agreement salary "
        "groups as though they applied to them: " + "; ".join(ungated)
    )

def test_known_cats_sectors_and_isf_are_not_labelled_as_dutch_only_anywhere_checkable():
    """Weaker structural check, kept as a second signal: known_cats_sectors()
    and the ISF band table expose nothing a caller could use to ask "is this
    even the right country for this data" -- there is no NL marker on the
    data itself, only in prose docstrings a runtime check can't see."""
    from services import cao_crosswalk_service as cw
    assert not hasattr(cw, "COUNTRY"), "unexpected: a country constant exists but isn't used above"
    assert not hasattr(cw, "APPLIES_TO_COUNTRY")


# ═════════════════════════════════════════════════════════════════════════
# benefits_service -- country/currency-blind pooling
# ═════════════════════════════════════════════════════════════════════════

class _FakeBenefitsCatalog:
    def __init__(self, repository):
        self.repository = repository


def _repo_with_mixed_currency_observations():
    """Two 'markets' worth of benefit observations filed under the SAME
    (industry_id, category) key -- exactly how core/repository.py actually
    stores them (services/benefits_service.py:75, core/repository.py:517
    key on (industry_id, category) only, never currency or country)."""
    import pandas as pd
    from core.repository import Repository

    # Ten NL/EUR observations, all in the 900-1000 range (a rich package),
    # and ten PL/PLN observations, numerically similar (900-1000) but a
    # completely different, much smaller real value once currency is
    # accounted for. Nothing in the data model or the service tells them
    # apart.
    observations = pd.DataFrame(
        [{"IndustryID": "IND-A", "Category": "Wellness", "Value": v, "Unit": "EUR", "Currency": "EUR"}
         for v in [900, 920, 940, 960, 980, 1000, 1020, 1040, 1060, 1080]]
        + [{"IndustryID": "IND-A", "Category": "Wellness", "Value": v, "Unit": "PLN", "Currency": "PLN"}
           for v in [900, 920, 940, 960, 980, 1000, 1020, 1040, 1060, 1080]]
    )
    catalog_df = pd.DataFrame([
        {"BenefitID": "BEN-01", "Category": "Wellness", "Unit": "EUR", "Basis": "Fixed annual budget"},
    ])
    data = {
        "jobs": pd.DataFrame(columns=["JobID", "StandardTitle", "Function", "Level"]),
        "titles": pd.DataFrame(columns=["ExistingTitle", "JobID"]),
        "benefitscatalog": catalog_df,
        "benefitsobservations": observations,
    }
    return Repository(data, validate=False)


def _repo_with_two_real_markets():
    """The same category priced in two markets, each row carrying its country.

    This is what the library looks like once a second market is imported --
    the case the product is being sold into, not a hypothetical.
    """
    import pandas as pd
    from core.repository import Repository

    observations = pd.DataFrame(
        [{"IndustryID": "IND-A", "Category": "Wellness", "Value": v,
          "Unit": "EUR", "Currency": "EUR", "Country": "NL"}
         for v in [900, 920, 940, 960, 980, 1000, 1020, 1040, 1060, 1080]]
        + [{"IndustryID": "IND-A", "Category": "Wellness", "Value": v,
            "Unit": "PLN", "Currency": "PLN", "Country": "PL"}
           for v in [3900, 3920, 3940, 3960, 3980, 4000, 4020, 4040, 4060, 4080]]
    )
    catalog_df = pd.DataFrame([
        {"BenefitID": "BEN-01", "Category": "Wellness", "Unit": "EUR", "Basis": "Fixed annual budget"},
    ])
    data = {
        "jobs": pd.DataFrame(columns=["JobID", "StandardTitle", "Function", "Level"]),
        "titles": pd.DataFrame(columns=["ExistingTitle", "JobID"]),
        "benefitscatalog": catalog_df,
        "benefitsobservations": observations,
    }
    return Repository(data, validate=False)


def test_country_is_part_of_the_observation_key_not_just_a_field_on_the_row():
    """The defect was that currency was captured and then dropped at grouping
    time. Country is now part of the key, so two markets cannot land in one
    distribution however similar their numbers look."""
    repo = _repo_with_two_real_markets()
    keys = set(repo.benefit_observations.keys())
    assert keys == {("IND-A", "Wellness", "NL"), ("IND-A", "Wellness", "PL")}, keys
    assert len(repo.benefit_observations[("IND-A", "Wellness", "NL")]) == 10
    assert len(repo.benefit_observations[("IND-A", "Wellness", "PL")]) == 10


def test_each_market_is_benchmarked_against_its_own_distribution():
    """A Polish client's wellness budget must be ranked against Polish
    observations. Before this, it was ranked against a ladder that was half
    Dutch euro values -- so whether the verdict came out "Below P25" or "At
    market" depended on what other countries happened to share the key."""
    from services.benefits_service import BenefitsService
    repo = _repo_with_two_real_markets()

    nl = BenefitsService(_FakeBenefitsCatalog(repo), country="NL").get_band("Wellness", "IND-A", None)
    pl = BenefitsService(_FakeBenefitsCatalog(repo), country="PL").get_band("Wellness", "IND-A", None)

    assert nl.n_observations == 10 and pl.n_observations == 10, "a market got the other's rows"
    assert nl.currency == "EUR" and pl.currency == "PLN"
    assert nl.country == "NL" and pl.country == "PL"
    # The medians must be the medians of their OWN market, not of the pool.
    assert nl.p50 == 990 and pl.p50 == 3990, (nl.p50, pl.p50)

    # And the comparison that a client actually sees follows the same split:
    # 4000 is mid-market in Poland and far above market in the Netherlands.
    pl_cmp = BenefitsService(_FakeBenefitsCatalog(repo), country="PL").compare("Wellness", 4000.0, "IND-A", None)
    nl_cmp = BenefitsService(_FakeBenefitsCatalog(repo), country="NL").compare("Wellness", 4000.0, "IND-A", None)
    assert pl_cmp.status == "At market", pl_cmp.status
    assert nl_cmp.status == "Above P90", nl_cmp.status


def test_a_market_that_has_no_observations_gets_none_rather_than_another_markets():
    """The absence has to be representable, or a client sees another country's
    numbers under their own label. Mirrors app.resolve_country() returning null
    in 0012 rather than falling through to the Dutch rows."""
    from services.benefits_service import BenefitsService
    repo = _repo_with_two_real_markets()
    band = BenefitsService(_FakeBenefitsCatalog(repo), country="SE").get_band("Wellness", "IND-A", None)
    assert band is None, "a Swedish client was shown another market's benefit band"


def test_two_currencies_inside_one_market_refuse_to_form_a_band():
    """Country keying should make this impossible, so it means the library
    itself is inconsistent -- two currencies filed under one market. No band is
    the honest answer: a percentile across zloty and euro is not a number about
    anything, and it would look exactly like a real one.

    The original fixture has no Country column at all, so both currencies land
    under the default market -- which is precisely the inconsistent case.
    """
    from services.benefits_service import BenefitsService
    repo = _repo_with_mixed_currency_observations()
    service = BenefitsService(_FakeBenefitsCatalog(repo), country="NL")
    assert service.get_band("Wellness", "IND-A", None) is None
    # And the comparison built on it refuses too, rather than ranking against
    # a ladder it could not compute.
    assert service.compare("Wellness", 1000.0, "IND-A", None) is None


def test_the_service_must_be_told_which_market_it_is_for():
    """Structural guard. The country is taken on the constructor rather than
    per call, for the reason ArchitectureReportService takes a currency there:
    it is a property of the client, fixed for the life of the report, and a
    per-call argument is one a caller can forget on one path out of five."""
    from services.benefits_service import BenefitsService
    params = inspect.signature(BenefitsService.__init__).parameters
    assert "country" in params, "the service cannot be told which market it is for"
    # Defaulted, so a script that says nothing gets the deployment default
    # rather than a crash or a silent pool across every market.
    assert params["country"].default is None

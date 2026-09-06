"""
The tier invariants: which tables may be asked the country question.

Migration 0012 drew a line — money and national institutions carry a country,
structure does not — and gave the reason: "a country column on a table that does
not vary by country is a column that will drift, get half-populated, and then be
believed." docs/country-data-tiers.md finishes that line for the rest of the
schema. This file holds the parts of it that must stay true whatever the product
owner decides about the arguable cases, so that a decision taken in a document
survives the next person who is in a hurry.

Most of these read the migration files rather than a database, for the reason
test_tenancy_invariants gives: what they guard is a SHAPE the schema must keep,
and both failure modes look like a working app. The two that genuinely need the
database skip without credentials — skipping is not passing, and nothing here
should be read as a green light for a cutover.

    $env:SUPABASE_URL = "https://<ref>.supabase.co"
    $env:SUPABASE_SECRET_KEY = "sb_secret_..."
    .venv/Scripts/python.exe -m pytest tests/test_country_tiers.py -v

Every read names its encoding. Without it read_text() uses the platform default,
cp1252 on a Dutch Windows machine, and these files contain characters it cannot
decode — a guard that is green in CI and cannot run where the code is written is
in the worst possible place.
"""
from __future__ import annotations

import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"

_HAS_DB = bool(os.environ.get("SUPABASE_URL") and
               (os.environ.get("SUPABASE_SECRET_KEY") or
                os.environ.get("SUPABASE_SERVICE_KEY")))
needs_db = pytest.mark.skipif(not _HAS_DB,
                             reason="needs SUPABASE_URL + SUPABASE_SECRET_KEY")


# ── the classification, as the tests understand it ───────────────────────────
#
# These lists are the ASSERTION, not a description of the current schema. If the
# owner moves a table between them the list changes here and the test then holds
# the new answer. What must never happen is a table quietly acquiring a country
# column without appearing in the top list, which is the whole point.

#: Tables that vary by market: money, or a national institution.
COUNTRY_CONDITIONED = {
    "salary_bands", "job_grades", "pay_mix", "industry_salary_factors",
    "benefits_observations", "level_benefits_factors", "title_mapping",
    # per-row, nullable: where a person is paid, which is not the org's country
    "employees",
    # added by 0015
    "pay_elements", "benefits_catalog",
}

#: Tables that are the same everywhere. A country column on any of these is the
#: defect 0012 named, and the test below is the thing that would catch it.
UNIVERSAL = {
    "jobs", "skills", "skill_proficiency", "role_skill_map", "industry_skills",
    "levels", "categories", "industries",
}

#: Genuinely open — docs/country-data-tiers.md §4. Neither list may claim them.
#: A country column appearing on one of these is not automatically wrong; it
#: means a decision was taken, and the decision has to land in this file and in
#: the doc at the same time. The test asserts the DECISION IS RECORDED, not
#: which way it went.
ARGUABLE = {
    "job_profiles", "competency_levels", "seniority_levels", "career_paths",
}

#: Tenancy, history and the country registry itself. No market dimension.
PLATFORM = {
    "orgs", "partners", "memberships", "jobsy_sessions", "activity_log",
    "library_audit", "library_revisions", "countries",
}


def _sql() -> str:
    """Every migration, concatenated in order. The schema as declared."""
    return "\n".join(p.read_text(encoding="utf-8")
                     for p in sorted(MIGRATIONS.glob("*.sql")))


# ═══════════════════════════════════════════════════════════════════════════
# 1. A country column nobody can populate
# ═══════════════════════════════════════════════════════════════════════════

def test_level_benefits_factors_unique_admits_a_second_country():
    """0012 gave this table a country column and left it unable to hold one.

    The loop in 0012 added `country`, the foreign key and the (org_id, country)
    index to seven tables. Its unique-widening section then named five. This was
    the one that fell between, so the constraint is still the pre-0012
    `UNIQUE (org_id, level, category)` and a Belgian factor for a level the
    Dutch library already covers is rejected by the database.

    A column that cannot take a second value is worse than no column: it looks
    like the dimension is there. This is the test that would have caught the
    omission on the day 0012 shipped.

    NOTE ON WHAT IT MEASURES. It reads the migration FILES — the schema as
    declared — so it passes as soon as 0015 exists on disk, which it does. It is
    therefore green while the LIVE DATABASE still carries the narrow constraint,
    because 0015 has not been applied. That is the right scope for a shape guard
    and the wrong thing to read as "the database is fixed": what is applied is
    the main session's call, and §6 below is where the live checks are.
    """
    sql = _sql()
    widened = re.search(
        r"lbf_country_uniq[^;]*?unique\s*\([^)]*\bcountry\b[^)]*\)",
        sql, re.I | re.S)
    assert widened, (
        "level_benefits_factors carries a country column (0012) but no unique "
        "constraint that includes it. Until migration 0015 is applied, a second "
        "country's row for an existing (level, category) is rejected — the table "
        "has a dimension it cannot use. See docs/country-data-tiers.md §1.")


@pytest.mark.parametrize("table,constraint", [
    ("salary_bands", "salary_bands_country_uniq"),
    ("job_grades", "job_grades_country_uniq"),
    ("pay_mix", "pay_mix_country_uniq"),
    ("industry_salary_factors", "isf_country_uniq"),
    ("title_mapping", "title_mapping_country_uniq"),
])
def test_country_tables_have_a_country_bearing_unique(table, constraint):
    """0012's five, held so a later migration cannot narrow one back.

    benefits_observations is deliberately absent: its unique is on the surrogate
    obs_id, so country varies freely underneath it without being in the key.
    That is a legitimate second shape, not an omission.
    """
    sql = _sql()
    found = re.search(rf"{constraint}[^;]*?unique\s*\([^)]*\bcountry\b[^)]*\)",
                      sql, re.I | re.S)
    assert found, (
        f"{table}: {constraint} does not include country. A unique without it "
        f"folds two markets' rows into one key and the second import fails.")


# ═══════════════════════════════════════════════════════════════════════════
# 2. No country column on a table that cannot answer the question
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("table", sorted(UNIVERSAL))
def test_universal_tables_have_no_country_column(table):
    """The guard 0012 asked for, made mechanical.

    A skill is a skill. If somebody adds `country` to `skills`, seven near-identical
    copies of every skill definition follow, they drift, and then somebody
    believes the drift. The fix when this fails is not to add the table to
    COUNTRY_CONDITIONED — it is to ask what a per-country value would MEAN and
    whether anyone could defend it.
    """
    sql = _sql()
    added = re.search(
        rf"alter\s+table\s+{table}\s+add\s+column\s+(?:if\s+not\s+exists\s+)?country\b",
        sql, re.I)
    assert not added, (
        f"{table} is classified UNIVERSAL in docs/country-data-tiers.md and has "
        f"acquired a country column. Either the classification changed — in which "
        f"case move it in this file and say why in the doc — or a column was added "
        f"that nobody can populate meaningfully.")


@pytest.mark.parametrize("table", sorted(ARGUABLE))
def test_arguable_tables_carry_their_open_question(table):
    """An open decision has to be visible where the table is.

    These four are genuinely undecided (doc §4.1-§4.4). A reader running \\d+ on
    one of them must find out that it is undecided, otherwise the absence of a
    country column reads as a settled answer — which is how an open question
    becomes a silent default.
    """
    sql = _sql()
    commented = re.search(
        rf"comment\s+on\s+table\s+{table}\s+is\s*\n?\s*'ARGUABLE", sql, re.I)
    assert commented, (
        f"{table} is an open tier decision and its table comment does not say so. "
        f"Migration 0015 records these; if the decision has since been TAKEN, move "
        f"the table into COUNTRY_CONDITIONED or UNIVERSAL here and replace the "
        f"comment with the reasoning rather than deleting it.")


# ═══════════════════════════════════════════════════════════════════════════
# 3. No column name may assert a country
# ═══════════════════════════════════════════════════════════════════════════

#: `statutory_nl` on pay_elements and benefits_catalog. 0015 adds a neutral
#: `statutory` beside it and deliberately does NOT drop it, because four things
#: still read or write the old name. The exemption is named here, with its exit
#: condition, so that it expires by being noticed rather than by being forgotten.
KNOWN_COUNTRY_NAMED_COLUMNS = {
    ("pay_elements", "statutory_nl"),
    ("benefits_catalog", "statutory_nl"),
}


def test_no_new_column_name_bakes_in_a_country():
    """A country in a column name is a claim the schema cannot take back.

    Two are grandfathered. A third means somebody has done it again, in a schema
    whose whole current project is removing the first two.
    """
    sql = _sql()
    hits = set()
    pattern = re.compile(
        r"alter\s+table\s+(\w+)\s+add\s+column\s+(?:if\s+not\s+exists\s+)?"
        r"(\w*_(?:nl|be|de|fr|es|pl|it|se|dk))\b",
        re.I)
    for table, column in pattern.findall(sql):
        hits.add((table.lower(), column.lower()))
    unexpected = hits - KNOWN_COUNTRY_NAMED_COLUMNS
    assert not unexpected, (
        f"column names asserting a country: {sorted(unexpected)}. A column called "
        f"<something>_nl states the nationality of every row it will ever hold, "
        f"including the Belgian ones. Put the country in a country column.")


def test_the_statutory_rename_keeps_both_columns_until_the_readers_move():
    """0015 adds `statutory` and leaves `statutory_nl` standing. Both, on purpose.

    Dropping it in the same step would break the import: TableSpec still maps the
    workbook heading "StatutoryNL" onto it, and models.PayElement.is_statutory
    still reads it — including the distinction that only a leading 'Yes' is a
    statutory obligation and 'Partly (sector funds)' is not. The conditions for a
    follow-up drop are listed in 0015 §3.
    """
    sql = _sql()
    for table in ("pay_elements", "benefits_catalog"):
        assert re.search(
            rf"alter\s+table\s+{table}\s+add\s+column\s+if\s+not\s+exists\s+statutory\s+text",
            sql, re.I), f"{table}: the neutral `statutory` column is not added"
    assert not re.search(r"drop\s+column\s+(?:if\s+exists\s+)?statutory_nl", sql, re.I), (
        "a migration drops statutory_nl. Before that is safe, TableSpec, both "
        "model classes, the export and the workbook must read `statutory`, and "
        "`statutory is distinct from statutory_nl` must return no rows. See 0015 §3.")


# ═══════════════════════════════════════════════════════════════════════════
# 4. 'EU' is a scope, never somebody's country
# ═══════════════════════════════════════════════════════════════════════════

def test_eu_is_seeded_but_never_live():
    """0012's rule, held. EU is where a Europe-wide default row lives.

    Offering it as a choice would let a client file a pay report for a country
    that does not exist.
    """
    sql = _sql()
    assert re.search(r"\('EU',\s*'EU baseline',\s*'EUR',\s*false", sql), (
        "the EU row is missing or is_live is not false. It is the fallback scope "
        "in app.resolve_country(), not a place anyone works.")


def test_country_service_filters_eu_out_of_the_choices():
    """The schema flag is not the only guard, and should not be.

    country_service.live_countries() drops EU even if somebody flips is_live —
    two independent guards, because the consequence of a client picking 'EU' as
    their market is a legal filing against a jurisdiction.
    """
    src = (ROOT / "services" / "country_service.py").read_text(encoding="utf-8")
    assert '!= "EU"' in src or "!= 'EU'" in src, (
        "live_countries() no longer excludes EU. The database flag alone is not "
        "enough: is_live is data and can be edited.")


# ═══════════════════════════════════════════════════════════════════════════
# 5. The read path — the thing that actually breaks first
# ═══════════════════════════════════════════════════════════════════════════
#
# These two are xfail rather than fail, because the files they guard belong to
# another agent and the finding is a report, not a patch. xfail(strict=True)
# means they will FAIL LOUDLY the moment the fix lands, which is the reminder to
# turn them into ordinary assertions. A skip would go quiet forever.

def test_repository_keys_salary_bands_by_country():
    """A band belongs to a market, and the key has to say so.

    repository.py already learned this once, for benefit observations, and wrote
    the reason down: "Country is part of the KEY, not just a field on the row.
    Left as a field only, it was captured and then dropped at grouping time, so a
    Polish client's benefits were benchmarked against a distribution that was
    mostly Dutch euro values." Salary bands have not had that pass. The database
    can hold both countries; the dictionary cannot, and the survivor is whichever
    row the loader returned last.
    """
    src = (ROOT / "core" / "repository.py").read_text(encoding="utf-8")
    build = src.split("def _build_salary", 1)[1].split("\n    def ", 1)[0]
    assert "country" in build, (
        "_build_salary never mentions country: two markets' bands for the same "
        "Function x Level collapse into one entry.")


def test_paged_reads_are_ordered():
    """`.range()` without `.order()` is unspecified row order in Postgres.

    That is a latent bug on its own — a paged read can repeat or miss a row — and
    it is what makes the collision above nondeterministic rather than merely
    wrong: which country's band survives can differ between two runs against
    identical data.
    """
    src = (ROOT / "core" / "db_loader.py").read_text(encoding="utf-8")
    fetch = src.split("def _fetch_all", 1)[1].split("\ndef ", 1)[0]
    assert ".order(" in fetch, "paged read has no stable order"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Against the live database
# ═══════════════════════════════════════════════════════════════════════════

def _client():
    from services import persistence_service  # noqa: F401  (import shape check)
    import supabase
    return supabase.create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_SECRET_KEY") or os.environ["SUPABASE_SERVICE_KEY"])


@needs_db
@pytest.mark.parametrize("table", sorted(COUNTRY_CONDITIONED - {"employees"}))
def test_every_stored_country_is_in_the_registry(table):
    """A country value the registry does not know is a typo with a flag on it.

    The foreign key should make this impossible. It is asserted anyway because a
    constraint that was never exercised — every row in this database is 'NL' —
    has not been tested, it has been unused, and the two look identical until the
    second value arrives.
    """
    client = _client()
    known = {r["code"] for r in
             (client.table("countries").select("code").execute().data or [])}
    assert known, "the countries registry is empty; nothing below means anything"
    rows = client.table(table).select("country").execute().data or []
    seen = {r.get("country") for r in rows if r.get("country") is not None}
    assert seen <= known, f"{table} holds countries not in the registry: {seen - known}"


@needs_db
def test_no_client_org_has_eu_as_its_home_country():
    """orgs.default_country is where a company IS. Nobody is in 'EU'."""
    client = _client()
    rows = client.table("orgs").select("slug, default_country").execute().data or []
    offenders = [r["slug"] for r in rows if r.get("default_country") == "EU"]
    assert not offenders, (
        f"orgs with default_country 'EU': {offenders}. EU is a fallback scope for "
        f"reference rows, not a jurisdiction anyone files in.")


# ── the read path, proved rather than assumed ────────────────────────────────

def test_a_market_without_bands_gets_silence_not_another_markets_numbers():
    """The defect, reproduced against the fix.

    Before this, `_fetch_all` filtered on org and status and nothing else, and
    `_build_salary` keyed bands (function, level) with country dropped. A
    Belgian client therefore received the library's Dutch bands, Dutch
    compa-ratios and Dutch above/below-market labels against their own people —
    underneath a sidebar warning promising that bands "will be empty rather than
    wrong".

    An empty answer is the correct answer here. Falling back to whatever bands
    happen to exist is the whole failure.
    """
    from core.repository import _MarketRows

    bands = _MarketRows({
        "NL": {("Finance", "Senior"): "dutch band"},
        "EU": {("Finance", "Junior"): "eu baseline"},
    })

    class _Market:
        def __init__(self, code): self.code = code
        def __enter__(self):
            import services.country_service as cs
            self._real = cs.active_country
            cs.active_country = lambda: self.code
            return self
        def __exit__(self, *_):
            import services.country_service as cs
            cs.active_country = self._real

    with _Market("BE"):
        assert bands.get(("Finance", "Senior")) is None, (
            "Belgium was served the Dutch band — the defect is back")
        assert ("Finance", "Senior") not in bands
        # The EU baseline still resolves, because 0012 made it a real scope.
        assert bands.get(("Finance", "Junior")) == "eu baseline"

    with _Market("NL"):
        assert bands.get(("Finance", "Senior")) == "dutch band"
        assert bands.get(("Finance", "Junior")) == "eu baseline", (
            "a country's own rows should sit ON TOP of the EU baseline, not replace it")


def test_the_library_can_say_which_markets_it_covers():
    """"We have bands, none of them yours" is not "we have no bands".

    Through an empty mapping those look identical and mean completely different
    things to somebody deciding whether to trust a blank screen. One is a
    coverage gap that can be named; the other is an empty library.
    """
    from core.repository import Repository

    repo = Repository.__new__(Repository)
    repo._salary_by_country = {"NL": {("a", "b"): 1}, "EU": {}}
    assert repo.salary_markets() == ("EU", "NL")

    repo._salary_by_country = {}
    assert repo.salary_markets() == ()


# ── 0015 gave two more tables a country, which made two more holes reachable ──

def _repo_with_two_markets_of_library_rows():
    """pay_elements and benefits_catalog in two markets, built through the
    real Repository rather than by hand, so the builders are what is tested."""
    import pandas as pd
    from core.repository import Repository

    pay = pd.DataFrame([
        {"ElementID": "PE-HOL", "Name": "Holiday allowance", "Category": "Statutory",
         "Basis": "Annual", "TypicalValue": "8%", "StatutoryNL": "Yes (statutory min 8%)",
         "Taxable": "Yes", "Description": "", "Country": "NL"},
        {"ElementID": "PE-HOL", "Name": "Dubbel vakantiegeld", "Category": "Statutory",
         "Basis": "Annual", "TypicalValue": "92% of one month", "StatutoryNL": "Yes",
         "Taxable": "Yes", "Description": "", "Country": "BE"},
    ])
    ben = pd.DataFrame([
        {"BenefitID": "BEN-01", "Category": "Pension", "Basis": "Annual", "Unit": "EUR",
         "TypicalValueDescription": "Dutch second pillar", "StatutoryNL": "Partly (sector funds)",
         "Taxable": "No", "Description": "", "Country": "NL"},
        {"BenefitID": "BEN-01", "Category": "Pension", "Basis": "Annual", "Unit": "EUR",
         "TypicalValueDescription": "Belgian group insurance", "StatutoryNL": "No",
         "Taxable": "No", "Description": "", "Country": "BE"},
    ])
    data = {
        "jobs": pd.DataFrame(columns=["JobID", "StandardTitle", "Function", "Level"]),
        "titles": pd.DataFrame(columns=["ExistingTitle", "JobID"]),
        "payelements": pay,
        "benefitscatalog": ben,
    }
    return Repository(data, validate=False)


def test_holiday_allowance_is_read_from_the_client_s_own_market():
    """The sharpest instance of the pattern, and it is a real number.

    Holiday allowance is 8% of annual pay in the Netherlands, 92% of ONE
    MONTH's gross for Belgian white-collar staff, and not statutory at all in
    Germany — all three are in the packs. Keyed on element_id alone, one of
    those answers silently becomes everybody's, and it reads as a fact about
    the reader's own country.
    """
    repo = _repo_with_two_markets_of_library_rows()

    class _Market:
        def __init__(self, code): self.code = code
        def __enter__(self):
            import services.country_service as cs
            self._real = cs.active_country
            cs.active_country = lambda: self.code
            return self
        def __exit__(self, *_):
            import services.country_service as cs
            cs.active_country = self._real

    with _Market("NL"):
        assert repo.pay_elements["PE-HOL"].typical_value == "8%"
    with _Market("BE"):
        assert repo.pay_elements["PE-HOL"].typical_value == "92% of one month", (
            "a Belgian client was told their holiday allowance is 8% of annual pay")
    with _Market("DE"):
        assert repo.pay_elements.get("PE-HOL") is None, (
            "Germany, where this is not statutory at all, was handed another "
            "market's rate rather than nothing")


def test_a_benefit_s_national_facts_do_not_leak_between_markets():
    repo = _repo_with_two_markets_of_library_rows()

    class _Market:
        def __init__(self, code): self.code = code
        def __enter__(self):
            import services.country_service as cs
            self._real = cs.active_country
            cs.active_country = lambda: self.code
            return self
        def __exit__(self, *_):
            import services.country_service as cs
            cs.active_country = self._real

    with _Market("NL"):
        assert repo.benefits_catalog["Pension"].statutory_nl == "Partly (sector funds)"
    with _Market("BE"):
        assert repo.benefits_catalog["Pension"].statutory_nl == "No"
    with _Market("SE"):
        assert len(repo.benefits_catalog) == 0, (
            "a Swedish client read another market's catalogue")


def test_one_rule_in_one_place_for_all_three_tables():
    """Structural. Salary bands, pay elements and the benefits catalogue all
    resolve country then EU then nothing, and they do it through the SAME
    object — a rule enforced once and reimplemented twice is a rule with two
    chances to drift apart."""
    from core.repository import _MarketRows
    repo = _repo_with_two_markets_of_library_rows()
    for name in ("salary", "pay_elements", "benefits_catalog"):
        assert isinstance(getattr(repo, name), _MarketRows), (
            f"{name} resolves its market some other way")

"""
tests/test_vacancy_service.py

The first thing this product writes for an external audience.

Everything else it makes is an internal analysis a professional reads. A
vacancy is published, and what it says can be unlawful — so what is tested here
is not "does it produce nice text" but whether it carries what Directive (EU)
2023/970 art. 5 entitles an applicant to, and whether it stays on the right
side of the line between raising a question and reaching a verdict.
"""
from __future__ import annotations

import pytest

from services import vacancy_service as vs


class _Job:
    def __init__(self, jid, title, fn="HR", lvl="Senior"):
        self.job_id, self.standard_title, self.function, self.level = jid, title, fn, lvl


class _Profile:
    def __init__(self, desc="Partners with leaders on people strategy.",
                 resp=("Advise the business", "Run the review cycle")):
        self.description, self.key_responsibilities = desc, resp


class _Band:
    def __init__(self, lo=60000, hi=82000, cur="EUR"):
        self.min, self.max, self.currency = lo, hi, cur


class _Requirement:
    """Shaped like core.models.RoleSkillRequirement, which carries an ID and not
    a name. The first version of this fixture invented `.skill_name`, the tests
    passed, and the service broke on the first real repository it met — an
    invented fixture attribute is a test that agrees with itself."""
    def __init__(self, skill_id):
        self.skill_id, self.skill_type, self.required_level = skill_id, "Core", 3


class _Skill:
    def __init__(self, name):
        self.skill_name = name


class _Repo:
    """Two markets, deliberately.

    The earlier single-market fixture is why the Dutch band reached a Spanish
    advertisement: with one country loaded, honouring the requested market and
    ignoring it produce identical output, and the test cannot tell them apart.
    The Spanish figures are the real ones from the incident.
    """

    def __init__(self, band=_Band(), title="HR Business Partner"):
        self.jobs = {"J-HR-03": _Job("J-HR-03", title)}
        self.profiles = {"J-HR-03": _Profile()}
        self.salary = {("HR", "Senior"): band} if band else {}
        self._by_market = {
            "NL": {("HR", "Senior"): band} if band else {},
            "ES": {("HR", "Senior"): _Band(33100, 46700)} if band else {},
        }
        self.role_skill_map = {"J-HR-03": [_Requirement("SK-01")]}
        self.skills = {"SK-01": _Skill("Coaching and mentoring")}

    def salary_for(self, function, level, country):
        """What the real repository does: answer for the market it was ASKED
        about, not the one the session happens to be on."""
        market = (country or "NL").strip().upper()
        return self._by_market.get(market, {}).get((function, level))


class _Pack:
    class compensation:
        class structure:
            value = "CAO, extended by ministerial declaration"


# ── the fallback that used to hide the bug ───────────────────────────────────

def test_a_repository_without_salary_for_raises_rather_than_guessing():
    """The first version guarded this call with hasattr and fell back to
    repo.salary, which resolves on the SESSION's market. That fallback is how a
    Dutch band reached a Spanish advertisement, and a stub repository took it
    silently — the branch even carried `pragma: no cover`, so nothing reported
    it as untested.

    A repository that cannot answer for a named market must stop the draft. The
    assertion is deliberately that it RAISES: no vacancy is a recoverable
    outcome, and the wrong country's pay in a published one is not.
    """
    class _Bare:
        """Everything draft() needs EXCEPT salary_for -- the stub, the rename,
        the half-built double."""
        def __init__(self):
            full = _Repo()
            self.jobs, self.profiles = full.jobs, full.profiles
            self.salary = full.salary          # the tempting wrong answer
            self.role_skill_map, self.skills = full.role_skill_map, full.skills

    with pytest.raises(AttributeError):
        vs.draft(_Bare(), "J-HR-03", country="ES")


def test_the_named_market_is_honoured_not_the_session():
    """The regression itself, stated once: ask for ES and the ES band appears,
    whatever market the session happens to be on."""
    seen = {}

    class _TwoMarket(_Repo):
        def salary_for(self, function, level, country):
            seen["country"] = country
            return super().salary_for(function, level, country)

    vs.draft(_TwoMarket(), "J-HR-03", country="ES")
    assert seen["country"] == "ES"


# ── art. 5(1)(a): the pay, and what happens when there is none ────────────

def test_the_pay_range_is_in_the_draft_and_placed_high():
    """The applicant is entitled to it, and a range buried under "salary
    negotiable" is the shape that entitlement exists to remove."""
    d = vs.draft(_Repo(), "J-HR-03", country="NL")
    assert "60.000" in d.text and "82.000" in d.text
    assert d.text.index("Pay for this role") < d.text.index("What you will do")
    assert next(r for r in d.requirements if r.article == "5(1)(a)").met


def test_a_market_with_no_band_still_gets_a_draft_and_an_unmet_requirement():
    """The requirement does not disappear because we cannot fill it in.

    Silently omitting the pay line would hide the one thing the applicant is
    entitled to. Reporting it as unmet, with the reason, is the useful answer —
    and art. 5(1) expressly allows the employer to supply it before the
    interview instead, which is why this does not block.
    """
    d = vs.draft(_Repo(band=None), "J-HR-03", country="BE")
    assert d is not None and d.text
    unmet = d.unmet
    assert any(r.article == "5(1)(a)" for r in unmet)
    detail = next(r for r in unmet if r.article == "5(1)(a)").detail
    assert "still entitled" in detail
    assert "Pay for this role" not in d.text, "an empty pay line is worse than none"


def test_the_collective_agreement_comes_from_the_country_pack():
    """5(1)(b). The packs already hold this per market; nothing is retyped."""
    d = vs.draft(_Repo(), "J-HR-03", country="NL", pack=_Pack())
    assert "ministerial declaration" in d.text
    assert next(r for r in d.requirements if r.article == "5(1)(b)").met


# ── art. 5(2): the question that may not be asked ─────────────────────────

def test_the_draft_says_the_pay_history_question_will_not_be_asked():
    """5(2) forbids the employer to ask. Saying so in the notice is not
    required — it is included because a candidate reading it learns they do not
    have to answer, which is the point of the prohibition."""
    d = vs.draft(_Repo(), "J-HR-03", country="NL")
    assert "will not ask you what you earn" in d.text
    assert next(r for r in d.requirements if r.article == "5(2)").met


# ── art. 5(3): a title that names a sex ───────────────────────────────────

@pytest.mark.parametrize("title", ["Salesman", "Verkoopster", "Directrice",
                                   "Buchhalterin"])
def test_a_sex_marked_title_is_flagged(title):
    d = vs.draft(_Repo(title=title), "J-HR-03", country="NL")
    assert not next(r for r in d.requirements if r.article == "5(3)").met
    assert any(q.where == "title" for q in d.questions)


@pytest.mark.parametrize("title", ["HR Business Partner", "Director/a de RRHH",
                                   "Buchhalter(in)", "Data Analyst"])
def test_a_neutral_or_paired_title_is_not_flagged(title):
    """The Spanish and German inclusive forms are the CORRECT shape, not the
    problem — "Director/a" is what a neutral Spanish notice looks like. A
    checker that flagged them would push an employer towards the masculine
    form, which is the opposite of what 5(3) asks."""
    d = vs.draft(_Repo(title=title), "J-HR-03", country="ES")
    assert next(r for r in d.requirements if r.article == "5(3)").met, title


# ── questions, never verdicts ─────────────────────────────────────────────

def test_age_coded_language_is_raised_as_a_question():
    from services.vacancy_service import compose
    text = compose(title="Developer", description="We want a young, energetic team.",
                   responsibilities=(), skills=(), pay="", collective_agreement="",
                   country="NL")
    qs = vs._text_questions(text)
    assert qs and any("young" in q.phrase for q in qs)


def test_the_product_own_level_words_are_not_treated_as_age():
    """"Junior" is a level in this product's own four-rung ladder and entirely
    legitimate. A checker that flagged it would fight the rest of the product."""
    from services.vacancy_service import compose
    text = compose(title="Junior Software Engineer", description="A junior role.",
                   responsibilities=(), skills=(), pay="", collective_agreement="",
                   country="NL")
    assert not vs._text_questions(text)


@pytest.mark.parametrize("forbidden", ["compliant", "lawful", "discriminatory",
                                       "illegal", "violates", "approved"])
def test_nothing_this_module_says_reaches_a_legal_conclusion(forbidden):
    """A Question says "this may read as X — did you mean it?". A verdict says
    "this is unlawful". Only one of those is this product's to make, and a
    module that writes advertisements is exactly where the line would slip."""
    d = vs.draft(_Repo(title="Salesman"), "J-HR-03", country="NL")
    said = " ".join([q.why for q in d.questions]
                    + [r.what + " " + r.detail for r in d.requirements]).lower()
    assert forbidden not in said


# ── composed, not generated ───────────────────────────────────────────────

def test_a_core_skill_is_named_by_looking_it_up_rather_than_assumed():
    """The requirement holds an ID; the name is on the Skill.

    Pinned because the first version read `.skill_name` off the requirement,
    which no such object has — and the fixture had invented it, so the tests
    agreed with the bug all the way to the first real repository.
    """
    d = vs.draft(_Repo(), "J-HR-03", country="NL")
    assert "Coaching and mentoring" in d.text


def test_a_skill_id_with_no_matching_skill_is_dropped_not_printed():
    """A bare ID in a published advertisement is worse than a shorter list."""
    repo = _Repo()
    repo.skills = {}
    d = vs.draft(repo, "J-HR-03", country="NL")
    assert "SK-01" not in d.text


def test_the_draft_is_reproducible():
    """The same role and version produce the same text, so "what did the system
    propose" has an answer in 2028. A model in this path would not."""
    a = vs.draft(_Repo(), "J-HR-03", country="NL", pack=_Pack())
    b = vs.draft(_Repo(), "J-HR-03", country="NL", pack=_Pack())
    assert a.text == b.text


def test_no_model_is_called_from_this_module():
    """Structural. A template cannot invent a requirement that is not in the
    role, and an invented requirement in a published advertisement is the
    failure that matters most here."""
    import inspect
    src = inspect.getsource(vs)
    for hint in ("openai", "OpenAI", "anthropic", "completion", "chat.completions"):
        assert hint not in src, f"a model reached the vacancy path ({hint})"


def test_an_unknown_role_produces_nothing_rather_than_an_empty_advert():
    assert vs.draft(_Repo(), "J-NOPE", country="NL") is None


def test_a_pack_value_that_is_a_tuple_reads_as_words_not_as_a_repr():
    """('WML', 'CAO', 'company') in a published advertisement.

    The Dutch collective-agreement answer is a three-layer tuple, and str() on
    it produces a Python repr. Same class of defect as a bare fraction or a
    literal None reaching a screen — except this one lands in text an employer
    publishes, where nobody from this company will ever see it again.
    """
    class _Claim:
        value = ("WML", "CAO", "company")

    class _P:
        class compensation:
            structure = _Claim()

    d = vs.draft(_Repo(), "J-HR-03", country="NL", pack=_P())
    assert "WML, CAO, company" in d.text
    assert "('WML'" not in d.text and "[" not in d.text.split("## What you will do")[0]


def test_a_plain_string_value_passes_through_unchanged():
    class _Claim:
        value = "CAO, extended by ministerial declaration"

    class _P:
        class compensation:
            structure = _Claim()

    d = vs.draft(_Repo(), "J-HR-03", country="NL", pack=_P())
    assert "extended by ministerial declaration" in d.text


# ── the market named, not the market in session ───────────────────────────

class _MultiMarketRepo(_Repo):
    """Two markets with different bands, and a session pointing at the first.

    Shaped like the real Repository: `salary` resolves through the session and
    `salary_for` takes an explicit country. A fixture with only one market
    could not have caught what this is here for.
    """
    def __init__(self):
        super().__init__()
        self._by_country = {
            "NL": {("HR", "Senior"): _Band(58000, 82000)},
            "ES": {("HR", "Senior"): _Band(33100, 46700)},
        }
        self.salary = self._by_country["NL"]        # what the session sees

    def salary_for(self, function, level, country):
        return self._by_country.get((country or "").upper(), {}).get((function, level))


def test_a_spanish_vacancy_carries_the_spanish_band_not_the_session_market():
    """The defect this caught, reproduced.

    The composer accepted a `country` argument and looked the band up through
    `repo.salary`, which resolves on the SESSION's market. A Spanish vacancy
    therefore advertised the Dutch HR/Senior range of 58.000–82.000 when Spain's
    is 33.100–46.700 — a published advertisement carrying another country's pay,
    which is the exact harm _MarketRows exists to prevent, walked back in
    through a parameter that was accepted and not honoured.
    """
    repo = _MultiMarketRepo()
    es = vs.draft(repo, "J-HR-03", country="ES")
    nl = vs.draft(repo, "J-HR-03", country="NL")

    assert "33.100" in es.text and "46.700" in es.text
    assert "58.000" not in es.text, "the Spanish advert carries the Dutch band"
    assert "58.000" in nl.text


def test_a_market_with_no_band_of_its_own_does_not_borrow_one():
    """An unmet requirement is the correct answer. Borrowing a neighbour's band
    would satisfy art. 5(1)(a) with a number about somebody else."""
    repo = _MultiMarketRepo()
    d = vs.draft(repo, "J-HR-03", country="PL")
    assert d.pay_shown == ""
    assert any(r.article == "5(1)(a)" for r in d.unmet)

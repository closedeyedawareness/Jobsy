"""
vacancy_service.py — a vacancy draft, and what the law already asks of it.

The first thing this product writes for an EXTERNAL audience. Everything else
it makes is an internal analysis a professional reads; a vacancy is published,
and what it says can be unlawful. So this module is deliberately narrower than
"generate me a job ad".

── WHAT "COMPLIANT" CAN HONESTLY MEAN HERE ──────────────────────────────────

Not "this text is lawful". Nobody can say that about text they have not seen in
the market it will run in, and the terms say so — see docs/terms-clauses.md
clause 2(c). What this module does instead is narrower and actually true:

  * it SUPPLIES what Directive (EU) 2023/970 art. 5 requires an applicant to be
    given, from data the product already holds;
  * it RAISES QUESTIONS where a phrase is a known risk, as questions rather
    than verdicts;
  * and it never publishes.

Art. 5, read at source on 6 September 2026:

  5(1)(a)  the applicant must be given "the initial pay or its range, based on
           objective, gender-neutral criteria" — in the notice, before the
           interview, "or otherwise";
  5(1)(b)  and "the relevant provisions of the collective agreement applied by
           the employer" where applicable;
  5(2)     the employer "shall not ask applicants about their pay history";
  5(3)     "job vacancy notices and job titles" must be GENDER-NEUTRAL and the
           process led non-discriminatorily.

Three of those four are things this product already has the material for: the
band is in salary_bands per market, the collective agreement is in the country
pack, and the title is a string it can inspect.

── COMPOSED, NOT GENERATED ──────────────────────────────────────────────────

The text is assembled from the role's own fields by template. No model writes
it. Three reasons, in order of weight:

  1. A template cannot invent a requirement that is not in the role, and an
     invented requirement in a published advertisement is the failure that
     matters most here.
  2. It is reproducible. The same role and version produce the same draft, so
     "what did the system propose" has an answer in 2028.
  3. It is far easier to argue as a narrow procedural task under AI Act art.
     6(3) than a generative one. That is not the reason to do it, but it is a
     real consequence of doing it.

The employer supplies the voice. That is what the write-back is for.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

__all__ = ["VacancyDraft", "Requirement", "Question", "draft",
           "GENDERED_TITLE_PATTERNS", "AGE_CODED", "compose"]


# ── art. 5(3): titles that carry a sex ────────────────────────────────────
#
# Not a spell-checker. These are the forms that MARK a title for one sex in
# each of the five live markets, which is what 5(3) is about. The Spanish and
# German inclusive forms are here because they are the correct fix as well as
# the thing to detect: "Director/a" and "Buchhalter(in)" are what a neutral
# Spanish or German notice looks like, so a title WITHOUT one is the flag.
GENDERED_TITLE_PATTERNS = (
    (r"\b(salesman|saleswoman|foreman|chairman|craftsman|handyman)\b",
     "English titles ending in -man or -woman name a sex"),
    (r"\b(verkoopster|secretaresse|verpleegster|werkster)\b",
     "Dutch feminine forms (-ster, -esse) name a sex"),
    (r"\b(\w+euse|\w+trice)\b",
     "French feminine forms (-euse, -trice) name a sex unless paired"),
    (r"\b(\w+erin)\b",
     "German feminine form (-erin) names a sex unless written (in)"),
)

#: Age-coded language. Not unlawful in itself anywhere here, and that is exactly
#: why these are questions: "junior" is a level in this product's own ladder and
#: entirely legitimate, while "young and dynamic" is a description of a person.
AGE_CODED = (
    ("digital native", "describes an age group rather than a skill"),
    ("young", "describes the person rather than the work"),
    ("energetic team", "commonly read as an age signal"),
    ("recent graduate", "excludes career changers and returners"),
    ("jong", "beschrijft de persoon, niet het werk"),
    ("pas afgestudeerd", "sluit zij-instromers en herintreders uit"),
)


@dataclass(frozen=True)
class Requirement:
    """Something the law asks the notice to carry, and whether it is there."""
    article: str
    what: str
    met: bool
    detail: str = ""


@dataclass(frozen=True)
class Question:
    """A phrase worth a second look. NOT a verdict.

    The distinction is the whole posture of this product: it reports what a
    source says and what the data shows, and it does not settle anybody's legal
    position. "This may read as age-coded — did you mean it?" is a question a
    recruiter can answer. "This is discriminatory" is a conclusion this product
    is not entitled to reach.
    """
    where: str
    phrase: str
    why: str


@dataclass(frozen=True)
class VacancyDraft:
    job_id: str
    country: str
    title: str
    text: str
    requirements: tuple[Requirement, ...] = ()
    questions: tuple[Question, ...] = ()
    pay_shown: str = ""

    @property
    def unmet(self) -> tuple[Requirement, ...]:
        return tuple(r for r in self.requirements if not r.met)


def _money(low, high, currency: str) -> str:
    if low is None and high is None:
        return ""
    fmt = lambda n: f"{n:,.0f}".replace(",", ".")
    if low is not None and high is not None and low != high:
        return f"{currency} {fmt(low)} – {fmt(high)}"
    return f"{currency} {fmt(low if low is not None else high)}"


def _readable(claim) -> str:
    """A pack value as something a job applicant can read.

    `compensation.structure` is a tuple in most packs — ('WML', 'CAO',
    'company') is the Dutch three-layer answer — and `str()` on it produces a
    Python repr. That is the same class of defect as a bare fraction or a
    literal None reaching a screen, except that this one lands in a PUBLISHED
    ADVERTISEMENT, where nobody from this company will ever see it again.

    A tuple here is an ordered set of layers, so it reads as a list. Anything
    else is passed through as its own words.
    """
    if claim is None or not getattr(claim, "value", None):
        return ""
    value = claim.value
    if isinstance(value, (tuple, list)):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(parts)
    return str(value).strip()



def _title_questions(title: str) -> list[Question]:
    out = []
    for pattern, why in GENDERED_TITLE_PATTERNS:
        m = re.search(pattern, title, flags=re.IGNORECASE)
        if m:
            out.append(Question("title", m.group(0), why))
    return out


def _text_questions(text: str) -> list[Question]:
    low = text.lower()
    return [Question("body", phrase, why) for phrase, why in AGE_CODED
            if phrase in low]


def compose(*, title: str, description: str, responsibilities, skills,
            pay: str, collective_agreement: str, country: str) -> str:
    """The draft itself, assembled from the role's own words.

    The pay line is NOT optional and is placed high on purpose. Art. 5(1)(a)
    entitles the applicant to it, and a range buried at the bottom under
    "salary negotiable" is the shape that requirement exists to remove.
    """
    parts = [f"# {title}", ""]
    if description:
        parts += [description.strip(), ""]
    if pay:
        parts += [f"**Pay for this role:** {pay}", ""]
    if collective_agreement:
        parts += [f"**Collective agreement:** {collective_agreement}", ""]
    if responsibilities:
        parts += ["## What you will do", ""]
        parts += [f"- {r}" for r in responsibilities]
        parts += [""]
    if skills:
        parts += ["## What we are looking for", ""]
        parts += [f"- {s}" for s in skills]
        parts += [""]
    parts += [
        "## How we handle pay",
        "",
        "We state the pay for this role up front. We will not ask you what you "
        "earn or have earned — under EU pay-transparency rules that question is "
        "not ours to ask, and your pay here is set by the role rather than by "
        "your history.",
    ]
    return "\n".join(parts).strip()


def draft(repo, job_id: str, *, country: str, pack=None) -> Optional[VacancyDraft]:
    """One role, one market, one draft — with what art. 5 asks for.

    Returns None for a role that does not exist. A role with no salary band in
    THIS market still produces a draft: the requirement to state pay does not
    go away because we cannot fill it in, and reporting it as unmet is the
    useful answer. Silently omitting the pay line would hide the one thing the
    applicant is entitled to.
    """
    job = repo.jobs.get(job_id)
    if job is None:
        return None
    profile = repo.profiles.get(job_id)
    country = (country or "").strip().upper()

    # Named market, NOT the session's. `repo.salary` resolves through
    # country_service.active_country(), which is right for a screen and wrong
    # here: this function is handed a country and must honour it. The first
    # version did not, and put a Dutch salary band into a Spanish vacancy.
    if hasattr(repo, "salary_for"):
        band = repo.salary_for(job.function, job.level, country)
    else:                                                  # pragma: no cover
        band = repo.salary.get((job.function, job.level))
    pay = _money(getattr(band, "min", None), getattr(band, "max", None),
                 getattr(band, "currency", "") or "") if band else ""

    agreement = _readable(
        getattr(getattr(pack, "compensation", None), "structure", None))

    responsibilities = tuple(getattr(profile, "key_responsibilities", ()) or ())
    # A RoleSkillRequirement carries a skill_id, not a name — the name lives on
    # the Skill. The first version of this line read `.skill_name` off the
    # requirement and passed its tests, because the fixture had invented that
    # attribute. It broke the moment it met the real repository.
    skills = []
    for req in (repo.role_skill_map.get(job_id) or ()):
        if getattr(req, "skill_type", "") != "Core":
            continue
        skill = repo.skills.get(getattr(req, "skill_id", None))
        name = getattr(skill, "skill_name", None)
        if name:
            skills.append(name)
    skills = tuple(skills[:8])

    title = job.standard_title
    text = compose(title=title,
                   description=getattr(profile, "description", "") or "",
                   responsibilities=responsibilities, skills=skills,
                   pay=pay, collective_agreement=agreement, country=country)

    requirements = (
        Requirement(
            "5(1)(a)", "The initial pay or its range is stated",
            met=bool(pay),
            detail=pay or (f"No salary band is held for {job.function}/{job.level} "
                           f"in {country}. The applicant is still entitled to this "
                           f"before interview — supply it another way.")),
        Requirement(
            "5(1)(b)", "The applicable collective agreement is named",
            met=bool(agreement),
            detail=agreement or (f"No collective-agreement structure is held for "
                                 f"{country}. If one applies to this role, name it.")),
        Requirement(
            "5(2)", "The notice does not ask for pay history",
            met="pay history" not in text.lower() or "will not ask" in text.lower(),
            detail="The draft says explicitly that the question will not be asked."),
        Requirement(
            "5(3)", "The job title is gender-neutral",
            met=not _title_questions(title),
            detail="; ".join(q.why for q in _title_questions(title))
                   or "No sex-marked form found in the title."),
    )

    return VacancyDraft(
        job_id=job_id, country=country, title=title, text=text,
        requirements=requirements,
        questions=tuple(_title_questions(title) + _text_questions(text)),
        pay_shown=pay,
    )

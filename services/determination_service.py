"""
determination_service.py — a decision this product refused to make, kept.

The product is careful about not asserting what it cannot know. Claims carry a
hardness marker, a source and a date; the spine refuses grade and pay outright;
a market it does not hold gets silence. All of that is right and it is half a
product, because the client still has to decide.

`bridge()` already says so to the client's face — its refusal string tells a
reader that "an employer may adopt an internal equivalence as a business
judgement — that belongs to them, marked CONVENTIE, and is not a fact about the
two markets" — and then offers nowhere to record it. This is that place.

── WHAT THIS IS A GENERALISATION OF ─────────────────────────────────────────

`review_service` does exactly this for one decision type: a human approves a
title-to-role match and it is written back so the next run resolves it. It is
already right about the things that are easy to get wrong — it writes as the
signed-in user so the row policies decide, and it distinguishes a remap from an
insert. What it does not keep is the reasoning: `source = "Approved in review by
X"` is a label. This module keeps the dossier, and review_service should become
one `determination_type` rather than a second system beside this one.

── WHAT IT MUST NEVER DO ────────────────────────────────────────────────────

Emit a legal conclusion. It records what a source said, what the data produced,
what the employer determined and — where relevant — that a named adviser
advised. It never renders "compliant", "approved" as chrome, or a green shield.
"Approved" belongs to a named person approving a defined decision, and nothing
else.

See docs/employer-determinations.md for the full design and for the three things
still open: the AI Act intended-use classification, the retention period, and
the contractual clause.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

__all__ = ["Determination", "Evidence", "Participant", "GENDER_CODE_MAPPING",
           "CROSS_COUNTRY_EQUIVALENCE", "PAY_COMPARISON_BASIS", "TITLE_TO_ROLE",
           "gender_code_determination", "cross_country_equivalence",
           "pay_comparison_basis", "record", "recorded",
           "EQUIVALENCE_USES", "REVIEW_MONTHS", "PAY_BASES", "FX_REVIEW_MONTHS"]

#: What an employer might want a cross-country equivalence to be good FOR.
#:
#: A closed list rather than a free-text box, because the whole point of the
#: field is that a reader must be able to tell later which uses were agreed and
#: which were not. "Mobility" typed one way in 2026 and another in 2028 defeats
#: that. Offered on screen as checkboxes; whatever is NOT ticked becomes an
#: excluded use explicitly, rather than merely being absent.
EQUIVALENCE_USES = (
    ("reporting",  "Internal and statutory reporting"),
    ("mobility",   "Moving people between the two markets"),
    ("career",     "Career paths and progression planning"),
    ("pay",        "Setting or comparing pay"),
    ("promotion",  "Promotion eligibility"),
    ("benefits",   "Benefit entitlement"),
)

#: How long before an equivalence should be looked at again.
#:
#: 12 months, and NOT a new number: it is the interval migration 0017 already
#: sets for `job_grades`, on the ground that the ladder is the employer's and
#: the money in it is the market's. An equivalence rests on TWO such ladders and
#: cannot be sounder than the shorter-lived of them.
REVIEW_MONTHS = 12

#: The three ways two salaries in different currencies can be compared, and the
#: DIFFERENT QUESTION each one answers.
#:
#: `bridge()` refuses PAY on exactly this ground: these are not three routes to
#: one number, they are three numbers answering three questions. Recording which
#: question was asked is the whole content of this determination — a basis
#: without its question is a rate with no meaning attached.
PAY_BASES = (
    ("fx", "Exchange rate on a stated date",
     "What would this salary be worth today if converted and taken home?"),
    ("ppp", "Purchasing power parity",
     "What can this salary buy where the person actually lives?"),
    ("lci", "Labour-cost index",
     "What does this person cost the employer, relative to that market?"),
)

#: An exchange rate is a fact about ONE DAY.
#:
#: 1 month, not 12, and the difference is not a preference. A grade equivalence
#: rests on institutions that move with collective agreements; an FX rate can
#: move several percent in a fortnight, and a pay gap computed on a stale one is
#: wrong by exactly that much with nothing on screen to say so. Purchasing power
#: parity and labour-cost indices are annual publications and keep REVIEW_MONTHS.
FX_REVIEW_MONTHS = 1

TABLE = "employer_determination"

#: Decision types. Structured rather than free text, so that a screen can find
#: every determination of one kind and a report can group them. Each names a
#: place where this product already stops and hands the question back.
GENDER_CODE_MAPPING = "gender_code_mapping"            # the Spanish M/H refusal
CROSS_COUNTRY_EQUIVALENCE = "cross_country_equivalence"  # bridge() on GRADE
PAY_COMPARISON_BASIS = "pay_comparison_basis"          # bridge() on PAY
TITLE_TO_ROLE = "title_to_role"                        # review_service today


@dataclass(frozen=True)
class Evidence:
    """One thing that was true, and provably so, at the moment of deciding.

    `content_hash` is what separates a citation from a record. A live URL does
    not prove in 2028 what a page said in 2026, and every source in the country
    packs is a URL.
    """
    kind: str
    reference: str
    hardness: Optional[str] = None
    source_url: Optional[str] = None
    excerpt: Optional[str] = None
    retrieved_at: Optional[str] = None

    @property
    def content_hash(self) -> Optional[str]:
        if not self.excerpt:
            return None
        return hashlib.sha256(self.excerpt.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Participant:
    """One ACT by one person — not one person.

    Consulted, advised, agreed and decided are four different things, and
    flattening them into "approved by" destroys the one thing a works council
    will want to see. A recorded DISAGREEMENT is evidence the process was real,
    which is why `disagreed` is a first-class action rather than an absence.
    """
    person: str
    action: str                      # reviewed·advised·agreed·disagreed·decided·activated
    role_at_the_time: Optional[str] = None
    capacity: Optional[str] = None
    comment: Optional[str] = None
    conditions: Optional[str] = None


@dataclass(frozen=True)
class Determination:
    """The employer's answer to a question this product declined to answer."""
    determination_type: str
    question: str
    chosen: str
    permitted_uses: tuple[str, ...] = ()
    excluded_uses: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    scope: dict = field(default_factory=dict)
    population_at_decision: Optional[int] = None
    system_proposed: Optional[str] = None
    options: tuple[dict, ...] = ()
    rationale: dict = field(default_factory=dict)
    review_due: Optional[date] = None
    review_trigger: Optional[str] = None
    evidence: tuple[Evidence, ...] = ()
    participants: tuple[Participant, ...] = ()

    def row(self, org_id: str, actor: str) -> dict:
        return {
            "org_id": org_id,
            "determination_type": self.determination_type,
            "countries": list(self.countries),
            "scope": self.scope,
            "population_at_decision": self.population_at_decision,
            "question": self.question,
            "permitted_uses": list(self.permitted_uses),
            "excluded_uses": list(self.excluded_uses),
            "system_proposed": self.system_proposed,
            "options": list(self.options),
            "chosen": self.chosen,
            "rationale": self.rationale,
            # Never anything else. A determination is a convention by
            # definition, and this is the marker the packs reserved for it.
            "hardness": "CONVENTIE",
            "state": "decided",
            "effective_from": date.today().isoformat(),
            "review_due": self.review_due.isoformat() if self.review_due else None,
            "review_trigger": self.review_trigger,
            "created_by": actor,
        }


def gender_code_determination(*, country: str, column: str, codes,
                              female_value: str, male_value: str,
                              population: Optional[int] = None,
                              actor: str = "") -> Determination:
    """The first slice, and the cheapest possible proof of the whole shape.

    This question is ALREADY asked. When a Spanish file uses `M`, the engine
    raises rather than guessing — because `M` is *Mujer* in an H/M file and male
    in a Masculino/Femenino one, and both appear inside one ministry workbook, so
    reading it either way inverts the gap for half the country rather than
    blurring it. The screen puts the question to a person, they answer it, and at
    the end of the session the answer is thrown away. The next upload asks again.

    Nothing new has to be invented to record it. What was missing is a place.

    THE PERMITTED AND EXCLUDED USES MATTER HERE MORE THAN THEY LOOK. "M means
    woman" is true of THIS file, from THIS payroll export. It is not a fact about
    Spanish payroll in general and must never be applied to another client's
    file, which is exactly what a shared lookup table would quietly do.
    """
    listed = ", ".join(sorted(str(c).upper() for c in (codes or ())))
    return Determination(
        determination_type=GENDER_CODE_MAPPING,
        countries=(country.upper(),),
        scope={"column": column, "codes": listed},
        population_at_decision=population,
        question=(
            f"In this file, column '{column}' uses {listed}, which cannot be read "
            f"unambiguously in {country.upper()}. Which value denotes women and "
            f"which denotes men, for the purpose of analysing THIS upload?"),
        system_proposed=(
            "None. The engine refused rather than guessing: reading this column "
            "either way would invert the pay gap for part of the population "
            "rather than blur it."),
        options=(
            {"option": f"{female_value} = women, {male_value} = men"},
            {"option": f"{male_value} = women, {female_value} = men"},
            {"option": "Re-export the column spelled out (Mujer / Hombre) and "
                       "remove the ambiguity at source"},
        ),
        chosen=f"{female_value} = women, {male_value} = men",
        permitted_uses=(
            "Reading the gender column of this file for this analysis",),
        excluded_uses=(
            "Any other client's file",
            "Any assertion about how this code is used in this market generally",
            "Any inference about an individual whose row is not in this file",),
        rationale={
            "business_purpose": "Produce a gender pay gap analysis from an "
                                "upload whose gender coding is ambiguous.",
            "criteria": "The employer's own knowledge of how their payroll "
                        "system writes this column.",
            "residual_uncertainty": "The coding convention was supplied by the "
                                    "employer and not verified against the "
                                    "source system.",
        },
        review_trigger="A new upload from the same source system with different codes",
        evidence=(Evidence(
            kind="pack_claim",
            reference=f"country_packs.{country.lower()}.GENDER_CODES",
            hardness="UITLEG",
            excerpt=(f"{country.upper()} gender codes are ambiguous for {listed}; "
                     "the engine raises AmbiguousGenderCodes rather than "
                     "resolving to a guess."),
        ),),
        participants=(Participant(
            person=actor or "unknown",
            action="decided",
            capacity="Supplied the coding convention for their own file",
        ),) if actor else (),
    )


def _add_months(start: date, months: int) -> date:
    """Calendar arithmetic that does not fall over on 29 February.

    `start.replace(year=+1)` raises on a leap day, and a review date that raises
    once every four years is a review date that fails in production and nowhere
    else.
    """
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    last = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(start.day, last))


def cross_country_equivalence(*, source_country: str, target_country: str,
                              source_grade: str, target_grade: str,
                              purposes, refusal: str = "",
                              population: Optional[int] = None,
                              actor: str = "", reason: str = "") -> Determination:
    """The slice that turns a refusal into the start of a decision.

    `bridge()` refuses GRADE outright and is right to: ISF, CATS, ERA, PC 200
    and the Metallurgie groupes are separate institutions negotiated by
    different parties under different law, with no legal equivalence between
    them. A table claiming a Dutch schaal 9 "is" an Entgeltgruppe 11 would be an
    invention with a product's authority behind it.

    But the employer with sites in both still has to run one career
    architecture. Until now the product said "that judgement belongs to them"
    and stopped — which is exactly where a client is left holding a real problem
    with nowhere to put the answer.

    WHAT MAKES THIS DIFFERENT FROM THE TABLE WE REFUSE TO SHIP: it is scoped to
    one employer, marked CONVENTIE, dated, attributed, carries the uses it is
    NOT good for, and is never visible to another client. It does not become a
    fact about the two countries.

    `purposes` is the load-bearing argument. Everything in EQUIVALENCE_USES not
    chosen is written into `excluded_uses` explicitly, because "we did not tick
    pay" and "pay is excluded" look identical in a record that lists only what
    was agreed — and only one of them is defensible two years later.
    """
    src, tgt = source_country.upper(), target_country.upper()
    chosen_keys = {str(p) for p in (purposes or ())}
    permitted = tuple(label for key, label in EQUIVALENCE_USES if key in chosen_keys)
    excluded = tuple(label for key, label in EQUIVALENCE_USES if key not in chosen_keys)

    return Determination(
        determination_type=CROSS_COUNTRY_EQUIVALENCE,
        countries=(src, tgt),
        scope={"source_grade": source_grade, "target_grade": target_grade},
        population_at_decision=population,
        question=(
            f"For this employer's internal purposes only, should {src} "
            f"{source_grade} and {tgt} {target_grade} be treated as equivalent — "
            f"and for which uses?"),
        system_proposed=(
            refusal or
            "None. Grades cannot be bridged between countries: they are separate "
            "institutions negotiated by different parties under different law, "
            "with no legal equivalence between them."),
        options=(
            {"option": f"Treat {src} {source_grade} as equivalent to {tgt} "
                       f"{target_grade} for the selected uses"},
            {"option": "Treat them as not equivalent for any purpose"},
            {"option": "Defer, and handle each case individually"},
        ),
        chosen=f"{src} {source_grade} = {tgt} {target_grade}",
        permitted_uses=permitted,
        excluded_uses=excluded + (
            "Any assertion that these grades are legally equivalent",
            "Any other employer",),
        rationale={
            "business_purpose": reason or "Run one career architecture across "
                                          "both markets.",
            "criteria": "The employer's own comparison of the two roles' scope, "
                        "responsibility and place in their organisation.",
            "residual_uncertainty": (
                "No legal equivalence exists between these grading instruments. "
                "This is the employer's convention and is not evidence about "
                "either national system."),
        },
        review_trigger=(f"A change to either grading instrument, or to this "
                        f"employer's own ladder in {src} or {tgt}"),
        review_due=_add_months(date.today(), REVIEW_MONTHS),
        evidence=(Evidence(
            kind="engine_refusal",
            reference="country_packs.bridge(grade)",
            hardness="WET",
            excerpt=(refusal or "Grades cannot be bridged between countries."),
        ),),
        participants=(Participant(
            person=actor or "unknown", action="decided",
            capacity="Set an internal equivalence for their own organisation",
        ),) if actor else (),
    )


def pay_comparison_basis(*, countries, basis: str, rate: str = "",
                         rate_date: Optional[date] = None, source: str = "",
                         refusal: str = "", population: Optional[int] = None,
                         actor: str = "", reason: str = "") -> Determination:
    """The employer's answer to a question this product will not choose for them.

    `bridge()` refuses PAY, and the refusal is not squeamishness: an FX rate on a
    stated day, purchasing power parity and a labour-cost index answer THREE
    DIFFERENT QUESTIONS and produce three different numbers. "Convert to euro" is
    not a technical step with one right answer; it is a choice about what is
    being asked.

    ── WHAT THIS DOES NOT DO, AND MUST NEVER START DOING ────────────────────

    RECORDING A BASIS IS NOT APPLYING ONE. This product still does not convert.
    The employer converts, or supplies the roster already in one unit, and this
    records which basis they used so a reader in 2028 can tell what the number
    they are looking at actually means. The moment the engine starts converting
    on the strength of a recorded basis, the refusal has been dissolved by the
    feature meant to complete it — and the number would carry this product's
    authority instead of the employer's judgement.

    `rate` and `rate_date` are therefore DESCRIPTIVE. Nothing multiplies by them.

    ── WHY THE REVIEW DATE IS DIFFERENT HERE ────────────────────────────────

    A grade equivalence rests on institutions that move with collective
    agreements, so 12 months. An exchange rate is a fact about one day and can
    move several percent in a fortnight, so an FX determination is reviewed in
    ONE month. Reusing the equivalence interval here would have been consistent
    and wrong.
    """
    codes = tuple(str(c).upper() for c in (countries or ()))
    label, question = "", ""
    for key, lab, q in PAY_BASES:
        if key == basis:
            label, question = lab, q
    if not label:
        raise ValueError(
            f"Unknown comparison basis {basis!r}. Known: "
            + ", ".join(k for k, _, _ in PAY_BASES))

    is_fx = basis == "fx"
    stated = ""
    if is_fx:
        stated = f" at {rate}" if rate else ""
        stated += f" as at {rate_date.isoformat()}" if rate_date else ""

    return Determination(
        determination_type=PAY_COMPARISON_BASIS,
        countries=codes,
        scope={"basis": basis, "rate": rate,
               "rate_date": rate_date.isoformat() if rate_date else "",
               "source": source},
        population_at_decision=population,
        question=(
            f"On what basis are pay figures across {', '.join(codes)} being "
            f"compared, and therefore what question do the resulting numbers "
            f"answer?"),
        system_proposed=(
            refusal or
            "None. Pay cannot be bridged without an explicit basis: an exchange "
            "rate on a stated day, purchasing power parity and a labour-cost "
            "index answer three different questions and produce three different "
            "numbers."),
        options=tuple({"option": lab, "answers": q} for _, lab, q in PAY_BASES),
        chosen=f"{label}{stated}",
        permitted_uses=(f"Comparisons that ask: {question}",),
        excluded_uses=(
            "Any comparison asking one of the other two questions",
            "Any figure produced on a different basis or a different date",
            "Any assertion that this is the correct or only basis",
            "Any other employer",),
        rationale={
            "business_purpose": reason or f"Compare pay across {', '.join(codes)}.",
            "criteria": f"The employer selected {label} because the question "
                        f"being asked is: {question}",
            "residual_uncertainty": (
                "An exchange rate is a fact about a single day and moves; the "
                "figures are only as current as the rate."
                if is_fx else
                "Purchasing power and labour-cost indices are published "
                "periodically and lag the market they describe."),
        },
        review_trigger=("A materially different exchange rate, or any re-run of "
                        "this analysis" if is_fx else
                        "A new publication of the index used"),
        review_due=_add_months(rate_date or date.today(),
                               FX_REVIEW_MONTHS if is_fx else REVIEW_MONTHS),
        evidence=(Evidence(
            kind="engine_refusal",
            reference="country_packs.bridge(pay)",
            hardness="WET",
            excerpt=(refusal or "Pay cannot be bridged without an explicit basis."),
        ),) + ((Evidence(
            kind="rate_source", reference=source, hardness="CONVENTIE",
            excerpt=f"{label}: {rate}"
                    + (f" as at {rate_date.isoformat()}" if rate_date else ""),
        ),) if source else ()),
        participants=(Participant(
            person=actor or "unknown", action="decided",
            capacity="Chose the basis on which their own pay figures are compared",
        ),) if actor else (),
    )



def recorded(client, org_id: str, determination_type: str, *,
             countries=None) -> list:
    """Determinations this employer has already made. Read-only.

    THE HALF THAT MAKES THIS A FEATURE RATHER THAN A FILING CABINET. A record
    nobody reads back is a compliance gesture. The point is that the next person
    to meet the same refusal sees that their organisation already answered it —
    when, by whom, and for which uses — instead of deciding it again slightly
    differently and leaving two conventions in the same company.

    Superseded and withdrawn rows are excluded: a replaced determination is
    history, and showing it beside the live one invites somebody to act on the
    wrong answer. It stays in the table, because the dossier is the point.

    Never raises. A read failure must not take down the analysis it decorates.
    """
    if client is None:
        return []
    try:
        q = (client.table(TABLE).select("*")
             .eq("org_id", org_id)
             .eq("determination_type", determination_type)
             .in_("state", ["decided", "activated"])
             .order("created_at", desc=True))
        if countries:
            q = q.contains("countries", [c.upper() for c in countries])
        return (q.execute().data or [])
    except Exception:                              # noqa: BLE001 — decoration, not data
        return []



def record(client, org_id: str, determination: Determination, *,
           actor: str = "") -> tuple[Optional[str], Optional[str]]:
    """Write one determination and its children. Returns (id, error).

    Takes the SIGNED-IN USER'S client, never the secret key — the same rule
    review_service states and for the same reason: `app.can_write_org` should
    decide, so a viewer cannot record a determination however the interface is
    arranged. Passing the secret key here would work and would prove nothing.

    Never raises. A determination that cannot be written must not take down the
    analysis that produced it — the analysis is the thing the user asked for and
    the record is the thing we owe them. It returns the reason instead, so a
    caller can say so rather than swallow it.
    """
    if client is None:
        return None, "not signed in"
    try:
        resp = (client.table(TABLE)
                .insert(determination.row(org_id, actor))
                .execute())
        det_id = (resp.data or [{}])[0].get("id")
        if not det_id:
            return None, "the determination was written but returned no id"

        for e in determination.evidence:
            client.table("determination_evidence").insert({
                "determination_id": det_id,
                "kind": e.kind, "reference": e.reference, "hardness": e.hardness,
                "source_url": e.source_url, "excerpt": e.excerpt,
                "content_hash": e.content_hash,
                "retrieved_at": e.retrieved_at or datetime.now(timezone.utc)
                                                          .replace(microsecond=0).isoformat(),
            }).execute()

        for p in determination.participants:
            client.table("determination_participant").insert({
                "determination_id": det_id,
                "person": p.person, "action": p.action,
                "role_at_the_time": p.role_at_the_time, "capacity": p.capacity,
                "comment": p.comment, "conditions": p.conditions,
            }).execute()

        return det_id, None
    except Exception as exc:                       # noqa: BLE001 — reported, not raised
        return None, f"{type(exc).__name__}: {exc}"

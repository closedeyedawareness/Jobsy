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
           "gender_code_determination", "record"]

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

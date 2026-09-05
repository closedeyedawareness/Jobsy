"""
jobsy/services/market_notes.py — what a market changes about how you work.

The country packs grew a slot for each capability the product has: job
architecture, skills, compensation, the 9-box and the org chart. Then a grep
found that NOTHING READ FOUR OF THEM. Zero references to `job_architecture`,
`compensation`, `performance` or `org_structure` outside the package itself.
The reporting notes reached a screen; the rest existed only in the code.

That was worst for the findings that are not about a client's report at all but
about how the product may be used. Germany's works council has co-determination
over the introduction and use of technical systems objectively suitable to
evaluate behaviour or performance — which reaches Jobsy itself, not only the
talent grid inside it. Nobody preparing a German conversation would have met
that anywhere.

So this module turns two of those slots into sentences. It returns plain strings
and knows nothing about Streamlit, for the same reason `_reporting_duty_notes`
does: a note that can only be seen by running the app cannot be tested, and a
compliance sentence that cannot be tested is one nobody checks.

── The register is the same as the pay-equity notes ────────────────────────

Report what a source provides; say what it depends on; point at what is worth
doing. Never tell an employer what they must do — that turns on facts this tool
does not hold and on advice nobody here can carry.
"""
from __future__ import annotations

from typing import Optional

from services import country_packs as cp

#: Prefixed to any claim that is not hard law, so a reader can weigh it without
#: opening the source. The packs already carry hardness; this is where it
#: becomes visible to somebody who will never read the code.
_WEIGHT = {
    cp.WET: "",
    cp.UITLEG: "Reading of the law rather than its words — ",
    cp.CONVENTIE: "Collective-agreement practice, not statute — ",
    cp.ONBEVESTIGD: "UNVERIFIED — ",
}


def _line(claim, today=None) -> Optional[str]:
    """One claim as a sentence, carrying its own weight and age."""
    if claim is None:
        return None
    body = (claim.note or "").strip()
    if not body:
        value = claim.value
        if value in (None, "", ()):
            return None
        body = str(value)
    text = _WEIGHT.get(claim.hardness, "") + body
    if claim.needs_review(today):
        months = claim.months_old(today)
        text = (f"STALE ({months} months since this was checked, against an interval of "
                f"{claim.review_after_months}) — " + text)
    return text


def _slot_notes(country, slot_name, fields, heading) -> list[str]:
    pack = cp.for_country(country)
    if pack is None:
        return []
    slot = getattr(pack, slot_name, None)
    if slot is None:
        return [f"{heading} — no answer is held for {pack.name} yet. That is a gap in "
                "this tool, not a finding that there is nothing to say."]

    out = [f"{heading} — {pack.name}."]
    for field in fields:
        value = getattr(slot, field, None)
        claims = ([value] if isinstance(value, cp.Claim)
                  else [c for c in (value or ()) if isinstance(c, cp.Claim)])
        for claim in claims:
            line = _line(claim)
            if line:
                out.append(line)
    return out


def org_structure_notes(country: Optional[str] = None) -> list[str]:
    """Who the employer is here, and who has to be at the table.

    The single most repeated finding across the packs, and different in every
    one: Germany counts per Betrieb, Spain per empresa regardless of sites,
    Poland per pracodawca which follows how the employer organises itself,
    France per entreprise or UES but never per établissement. "Headcount" has
    meant four different things across seven markets, and every threshold in
    this product rests on which one applies.

    It belongs on the org chart because that is where somebody is already
    looking at the shape of the organisation and is in a position to notice
    that the shape is the answer.
    """
    return _slot_notes(country, "org_structure",
                       ("employer_unit", "employee_representation", "constraints"),
                       "WHAT COUNTS AS THE EMPLOYER HERE")


def performance_notes(country: Optional[str] = None) -> list[str]:
    """What a talent grid is, legally, in this market.

    A 9-box is a neutral instrument in one country and a co-determined one in
    the next. This is the slot carrying the finding that reaches furthest: in
    Germany the works council's right covers the introduction and use of
    technical systems OBJECTIVELY SUITABLE to evaluate behaviour or performance,
    so intent does not decide it and the product itself is in scope, not only
    the grid it displays.

    Rendered on the 9-box page because that is the moment somebody is about to
    place real people in boxes.
    """
    return _slot_notes(country, "performance",
                       ("codetermination", "constraints"),
                       "WHAT A TALENT GRID IS HERE, LEGALLY")


def market_caveat() -> str:
    """The framing both of the above are read under."""
    return (
        "These notes report what published law and collective agreements say, with the "
        "source and its weight named. They are NOT legal advice and do not settle your "
        "position — and several of them turn on how a system is actually used rather than "
        "how it is described, which is a question about your deployment and not about "
        "this screen. Confirm anything you act on with someone who can carry that advice."
    )

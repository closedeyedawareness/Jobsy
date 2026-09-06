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

So this module turns those slots into sentences. `org_structure` and
`performance` were done first; `compensation` and `job_architecture` followed,
because the grep result was still true of them — the Elternzeit finding, the
62,84% Spanish prevalence and the fact that a grupo profesional is not a pay
grade all sat in the packs with nothing rendering them. It returns plain strings
and knows nothing about Streamlit, for the same reason `_reporting_duty_notes`
does: a note that can only be seen by running the app cannot be tested, and a
compliance sentence that cannot be tested is one nobody checks.

── The register is the same as the pay-equity notes ────────────────────────

Report what a source provides; say what it depends on; point at what is worth
doing. Never tell an employer what they must do — that turns on facts this tool
does not hold and on advice nobody here can carry.
"""
from __future__ import annotations

from functools import partial
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


#: What a measured share is a share OF, in words a reader can check.
#:
#: Unmapped slugs are not dropped — they are un-slugged and printed. A basis
#: nobody added a phrase for still reads as something; a basis that vanishes
#: leaves a percentage floating with no denominator, which is the exact failure
#: this whole mechanism exists to prevent.
_BASIS = {
    "share_of_agreements": "collective agreements",
    "share_of_employees": "employees",
    "share_of_pay": "the pay bill",
    "share_of_employers": "employers",
}


def _fraction_of(value) -> tuple[Optional[str], object]:
    """Split a measurement into what it counts and how much.

    A pack may store a share either as a bare fraction or as a
    `(basis, fraction)` pair. The pair exists because 0,6284 on its own cannot
    say whether it counts agreements, employees or pay — and the moment a second
    market publishes a prevalence, a screen lining the two up would compare
    different denominators with neither of them saying so.

    Bare fractions stay legal: most fields have only ever had one sensible
    denominator, and forcing a basis onto them would be ceremony rather than
    information.
    """
    if (isinstance(value, tuple) and len(value) == 2
            and isinstance(value[0], str) and not isinstance(value[1], str)):
        basis = _BASIS.get(value[0], value[0].removeprefix("share_of_").replace("_", " "))
        return basis, value[1]
    return None, value


def _as_percentage(value) -> Optional[str]:
    """A fraction rendered as what it is, or None if it is not one.

    `bargaining_coverage` is 0.9209 and `seniority_progression` is sometimes
    0.6284, because the packs store the measurement and not its presentation.
    Putting `0.6284` on a screen asks a reader to do arithmetic to find out
    they are looking at two thirds of Spanish collective agreements, and most
    will not — so a bare fraction is a fact that technically reached the
    screen and practically did not.

    Decimal comma, because these figures are quoted from Spanish, German and
    Dutch sources that write them that way and the packs' own notes already do.
    Trailing zeros are stripped so 0.49 reads as 49% and not 49,00% — spurious
    precision is its own kind of dishonesty about a survey figure.
    """
    value = _fraction_of(value)[1]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0 <= value <= 1:
        return None
    text = f"{value * 100:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") + "%"


def _line(claim, today=None, lead="") -> Optional[str]:
    """One claim as a sentence, carrying its own weight and age.

    `lead` is inserted AFTER the hardness and staleness prefixes and before the
    claim's own words, so a caller can name what a number measures without
    pushing "UNVERIFIED" or "STALE" into the middle of the sentence where
    somebody skimming would miss it.
    """
    if claim is None:
        return None
    body = (claim.note or "").strip()
    if not body:
        value = claim.value
        if value in (None, "", ()):
            return None
        # A fraction with no note is the one case where the raw value WOULD
        # have reached a reader, so it is formatted here rather than str()'d.
        body = _as_percentage(value) or str(value)
    text = _WEIGHT.get(claim.hardness, "") + lead + body
    if claim.needs_review(today):
        months = claim.months_old(today)
        text = (f"STALE ({months} months since this was checked, against an interval of "
                f"{claim.review_after_months}) — " + text)
    return text


def _claims_in(value) -> list:
    """Every Claim reachable from one slot field, whatever shape it takes.

    A field is a Claim, a tuple of Claims, or a tuple of SpineMappings — and a
    SpineMapping's evidence lives on its `.source`, so unwrapping it here is
    what stops the job-architecture mappings from being silently dropped the
    day a pack starts carrying one. Every pack's `mappings` is empty today;
    the point is that it does not have to stay that way for the note to work.
    """
    if isinstance(value, cp.Claim):
        return [value]
    out = []
    for item in (value or ()):
        if isinstance(item, cp.Claim):
            out.append(item)
        elif isinstance(getattr(item, "source", None), cp.Claim):
            out.append(item.source)
    return out


def _slot_notes(country, slot_name, fields, heading, renderers=None) -> list[str]:
    """One slot as a list of sentences, heading first.

    `renderers` maps a field name to a function that turns its claim into a
    line, for the fields where `_line` alone is not enough — a fraction needs
    to be told what it measures before it means anything. Everything else goes
    through `_line` exactly as it always did.
    """
    pack = cp.for_country(country)
    if pack is None:
        return []
    slot = getattr(pack, slot_name, None)
    if slot is None:
        return [f"{heading} — no answer is held for {pack.name} yet. That is a gap in "
                "this tool, not a finding that there is nothing to say."]

    out = [f"{heading} — {pack.name}."]
    for field in fields:
        render = (renderers or {}).get(field, _line)
        for claim in _claims_in(getattr(slot, field, None)):
            line = render(claim)
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


def _coverage_ranking() -> list[tuple]:
    """(country, name, fraction) for every pack holding a numeric coverage, high to low.

    Bargaining coverage is the one figure in the compensation slot that is
    genuinely comparable across these markets: every pack answers the same
    question — what share of employees a collective agreement reaches — and
    the answers span 11,6% to effectively 100%. A reader told "49%" learns
    much less than a reader told that 49% is the second LOWEST of the set,
    because the number only becomes actionable next to the alternative
    assumption they arrived with.

    What is NOT claimed is that these are one harmonised series. They are six
    national sources at three different hardnesses, and the rendered sentence
    says so. That is why this ranks and states the endpoints rather than, say,
    averaging them or computing a distance from the mean — those would be
    arithmetic on figures that do not share a denominator.
    """
    out = []
    for country, pack in cp.load().items():
        compensation = getattr(pack, "compensation", None)
        claim = getattr(compensation, "bargaining_coverage", None) if compensation else None
        value = getattr(claim, "value", None)
        if _as_percentage(value) is not None:
            out.append((country, pack.name, float(value)))
    out.sort(key=lambda row: -row[2])
    return out


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _coverage_context(country: str) -> str:
    """Where this market sits among the others, or nothing if there is no set."""
    ranking = _coverage_ranking()
    if len(ranking) < 3:
        return ""
    codes = [row[0] for row in ranking]
    if country not in codes:
        return ""
    place = codes.index(country) + 1
    where = ("the highest" if place == 1
             else "the lowest" if place == len(ranking)
             else f"the {_ordinal(place)} highest")
    top, bottom = ranking[0], ranking[-1]
    return (
        f"That is {where} of the {len(ranking)} markets Jobsy holds "
        f"a figure for, which run from {_as_percentage(bottom[2])} ({bottom[1]}) to "
        f"{_as_percentage(top[2])} ({top[1]}). Those are separately sourced national "
        f"figures at differing evidential weight and not one harmonised series, so the "
        f"position is worth more than the decimals."
    )


def _measured(claim, label: str, context: str = "") -> Optional[str]:
    """A field whose value is sometimes a number and sometimes a phrase.

    `seniority_progression` is 0.6284 in Spain and "conditional annual step" in
    the Netherlands, and the same field has to read correctly as both. When it
    is a fraction the label says what is being counted before the figure lands;
    when it is a phrase the label just introduces it.
    """
    if claim is None:
        return None
    percentage = _as_percentage(getattr(claim, "value", None))
    if percentage is None:
        return _line(claim, lead=f"{label} — ")
    if not (claim.note or "").strip():
        # No note to carry the figure's basis, so do not dress it up as one.
        return _line(claim, lead=f"{label}: ")
    basis = _fraction_of(getattr(claim, "value", None))[0]
    lead = f"{label}: {percentage} of {basis}. " if basis else f"{label}: {percentage}. "
    if context:
        lead += context + " "
    return _line(claim, lead=lead)


def _coverage_line(claim, country=None) -> Optional[str]:
    return _measured(claim, "Collective-agreement coverage",
                     _coverage_context(country) if country else "")


def _seniority_measured() -> list[tuple]:
    """The markets whose seniority answer is a figure rather than a description."""
    out = []
    for country, pack in cp.load().items():
        compensation = getattr(pack, "compensation", None)
        claim = getattr(compensation, "seniority_progression", None) if compensation else None
        if _as_percentage(getattr(claim, "value", None)) is not None:
            out.append((country, pack.name))
    return out


def _seniority_line(claim, country=None) -> Optional[str]:
    """Seniority pay, which is a fraction in one market and a phrase in the rest.

    Deliberately NOT ranked the way coverage is. Spain's 62,84% is a share of
    collective AGREEMENTS carrying an antigüedad complement; every other pack
    answers the same field with a description of a mechanism. Lining those up
    would put a measured prevalence next to four things that are not
    prevalences, and produce a ranking out of one comparable number. So the
    figure is labelled, its basis is pointed at, and its solitude is stated —
    which is the honest version of the comparison the reader wants.
    """
    context = ""
    if _as_percentage(getattr(claim, "value", None)) is not None:
        context = ("That denominator is not the one the coverage figure above uses, "
                   "so the two percentages are not on one scale.")
        if len(_seniority_measured()) == 1:
            context += (" It is also the only market here that answers this with a "
                        "measured prevalence rather than a description of the "
                        "mechanism, so there is nothing sound to rank it against.")
    return _measured(claim, "Automatic progression with service", context)


def compensation_notes(country: Optional[str] = None) -> list[str]:
    """How pay is set here, and what that does to a comparison against a band.

    PLACED ON THE BENEFITS / TOTAL REWARDS PAGE, and specifically because of
    what that page ends with: a Total Rewards snapshot that divides an actual
    salary by a market P50 and shows the result as a compa-ratio out of 100.
    Every field in this slot changes how that single number should be read,
    and the benefits page is the only screen where somebody is holding it.

    - Coverage decides whether "the market" is even the right comparator. At
      49% in Germany, HALF of employees sit under no collective scale at all,
      so "no Tarifvertrag" is the modal case rather than an exception; at
      92,09% in Spain a convenio floor almost certainly governs and a
      compa-ratio below it is not a market position, it is a floor breach.
    - The extension mechanism decides whether a sector agreement reaches THIS
      employer, which is a Dutch assumption that is wrong in Germany about
      half the time.
    - Seniority progression decides how to read a residual. Where scales
      advance by tenure, part of any gap is produced by the structure and not
      by a decision about a person — which is a different finding, and Spain
      is the only market here that publishes how prevalent it is.

    The job-family page shows the same bands, but it shows them as a design:
    nobody there is asserting a position for a real person. The benefits page
    is where a number about somebody gets produced, so that is where the note
    that changes its meaning belongs.
    """
    # Resolved here as well as in `_slot_notes` so the two numeric renderers
    # know WHICH market they are placing — `country` may be None, meaning the
    # session's active market, and a renderer must not re-resolve it differently.
    pack = cp.for_country(country)
    code = pack.country if pack else None
    return _slot_notes(
        country, "compensation",
        ("structure", "bargaining_coverage", "extension_mechanism",
         "seniority_progression", "market_data", "constraints"),
        "HOW PAY IS SET IN THIS MARKET",
        renderers={
            "bargaining_coverage": partial(_coverage_line, country=code),
            "seniority_progression": partial(_seniority_line, country=code),
        },
    )


def job_architecture_notes(country: Optional[str] = None) -> list[str]:
    """What a "level" is here before Jobsy imposes its own.

    PLACED ON THE JOB FAMILY PAGE, which draws a levelling grid — every role
    by level, with a Grade number and a salary band — and is therefore the
    screen that most invites the mistake this slot exists to prevent. Jobsy's
    Grade is a construct of the loaded library; the market's unit is something
    else, and it does not always behave like a ladder.

    Spain is the sharp case: ET art. 22.1 makes the grupo profesional the
    statutory classification unit, but a grupo IS NOT A PAY GRADE. Hostelería
    has three of them for roughly 1,3 million workers and química has nine, so
    grupos cannot be ranked against each other or compared across convenios —
    while the grid on this page reads top to bottom as though they could be.
    Germany is the same shape for a different reason: an Entgeltgruppe 11 in
    Baden-Württemberg and in Nordrhein-Westfalen are not the same thing,
    because there is no national German grade at all.

    Not on the skills dashboard: that page is about the skills taxonomy, which
    is the `skills` slot's question and has its own spine. Levels are what the
    job-family grid is made of.
    """
    return _slot_notes(country, "job_architecture",
                       ("level_concept", "families", "mappings"),
                       "WHAT A LEVEL MEANS IN THIS MARKET")


def market_caveat() -> str:
    """The framing both of the above are read under."""
    return (
        "These notes report what published law and collective agreements say, with the "
        "source and its weight named. They are NOT legal advice and do not settle your "
        "position — and several of them turn on how a system is actually used rather than "
        "how it is described, which is a question about your deployment and not about "
        "this screen. Confirm anything you act on with someone who can carry that advice."
    )

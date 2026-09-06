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
        f"That is {where} of the {len(ranking)} markets this tool holds "
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



# ── skills ────────────────────────────────────────────────────────────────

def _reference_line(mapping) -> Optional[str]:
    """One spine mapping as a sentence that says what we DO and DO NOT hold.

    Rendered here rather than through `_claims_in`, which unwraps a mapping to
    its `.source` Claim and by doing so drops the two facts a reader of this
    page actually needs: which scheme, and whether the correspondence itself is
    in our hands or somebody else's.

    Three shapes, and the difference between them is the whole posture:

      * IDENTITY — the market's coding IS the spine (Belgium codes occupations
        in ISCO-08 with no national adaptation). Nothing to cross, so nothing
        can be got wrong crossing it.
      * A REFERENCE — we record THAT a correspondence exists and WHERE the
        official one is published, and hold no table. This is the normal case
        and it is deliberate: several of those official files are free to read
        and restricted to redistribute, so a product that ships one is
        redistributing it and a product that cites it is not.
      * A TABLE — held only where the correspondence is set out in the law
        itself, level by level. Reproducing what a statute says is not
        reproducing anybody's dataset.
    """
    if mapping is None or not mapping.spine:
        return None
    scheme = (mapping.local_scheme or "").strip()
    spine = mapping.spine
    weight = _WEIGHT.get(mapping.source.hardness, "")
    where = (mapping.source.source or "").strip()

    if not mapping.mapping:
        if scheme.startswith(spine):
            body = (f"{scheme} — this market's coding IS {spine}, so there is no "
                    f"crossing to get wrong.")
        else:
            body = (f"{scheme} reaches {spine} through a correspondence published by "
                    f"the issuing body. THIS PRODUCT CITES IT AND DOES NOT HOLD IT"
                    + (f" ({where})" if where else "") + ".")
    else:
        body = (f"{scheme} to {spine} is set out level by level in law, so the "
                f"correspondence is held here"
                + (f" ({where})" if where else "")
                + f": {_pairs(mapping.mapping)}.")
    return weight + f"{mapping.dimension.capitalize()} — " + body


def _pairs(table: dict, limit: int = 4) -> str:
    """A small correspondence table as text, truncated honestly.

    Truncated with a count rather than an ellipsis: "and 4 more" tells a reader
    the table is complete somewhere, where a trailing "…" invites them to
    wonder whether the rest exists.
    """
    items = list(table.items())
    shown = ", ".join(f"{k}={v}" for k, v in items[:limit])
    rest = len(items) - limit
    return shown + (f", and {rest} more" if rest > 0 else "")


def skills_notes(country: Optional[str] = None) -> list[str]:
    """The taxonomies a skill and a qualification are read against here.

    PLACED ON THE THREE SKILLS SCREENS, which until now were the only module
    group in the product with no country awareness at all — no market panel, no
    caveat, not one mention of a country in either the service or the views.
    That was not a judgement that skills are universal; it was simply never
    asked.

    And the honest position is that skills mostly ARE universal — negotiating
    is negotiating on both sides of a border, which is why the catalogue itself
    is not being split. What is NOT universal is the two things this slot holds:
    the QUALIFICATION framework a level is anchored to, and the OCCUPATION
    taxonomy a role is coded in. Those are national instruments with national
    law behind them, and they are what a cross-market reading has to travel
    through.

    THE COST OF THE POSTURE IS STATED ON THE SCREEN, because it is the thing a
    reader is most likely to assume away: a reference does not convert. Knowing
    that KldB reaches ISCO-08 does not put a German roster into ISCO-08. Either
    the data already carries ISCO, or the client runs the official free file
    themselves, or nothing crosses — and the third is a real answer here rather
    than a failure.

    Deliberately silent on Jobsy's own five proficiency levels. Whether those
    anchor to EQF's eight or stay the product's own is an open decision, and a
    page that quietly implied either answer would be settling it by rendering.
    """
    pack = cp.for_country(country)
    if pack is None:
        return []
    slot = pack.skills
    if slot is None:
        return ["WHAT A SKILL IS READ AGAINST HERE — no answer is held for "
                f"{pack.name} yet. That is a gap in this tool, not a finding that "
                "there is nothing to say."]

    out = [f"WHAT A SKILL IS READ AGAINST HERE — {pack.name}."]
    for claim, lead in ((slot.qualification_framework, "Qualification framework — "),
                        (slot.occupation_taxonomy, "Occupation taxonomy — ")):
        line = _line(claim, lead=lead)
        if line:
            out.append(line)

    routes = [line for line in (_reference_line(m) for m in slot.mappings) if line]
    out.extend(routes)

    if routes:
        out.append(
            "A REFERENCE DOES NOT CONVERT. Every route above records that a "
            "correspondence exists and where the official one is published; it does "
            "not move a code across on its own. A roster in a national coding still "
            "has to reach the reference somehow — because it already carries it, or "
            "because you run the official file yourself — and where neither is true, "
            "nothing crosses. That is an answer, not a failure: an invented "
            "equivalence with a product's authority behind it would be worse than a "
            "blank."
        )
    return out


def crossing_notes(target: str, source: Optional[str] = None) -> list[str]:
    """Reading this market's skills data against another one, hop by hop.

    THE FIRST CALLER `bridge()` HAS EVER HAD. It was written with the spine,
    tested, and then read by nothing for as long as it existed — which meant its
    refusals, the part that carries the most weight, had never once reached a
    person. A refusal nobody is shown is indistinguishable from a feature nobody
    built.

    Both dimensions this page can ask about are rendered, including the one that
    says no, because "there is no route" is the answer more often than not and a
    reader needs to see it stated rather than infer it from an empty panel.

    The two hops are shown SEPARATELY and the weaker hardness is what labels the
    whole route, because a chain is exactly as sound as its softest link.
    Reporting the stronger one would flatter the answer — and the flattering
    version is the one that gets quoted.

    Note what is NOT offered here: grade and pay. `bridge()` refuses both
    outright and this page does not ask, because putting them on screen as
    greyed-out options would suggest they are coming.
    """
    src = cp.for_country(source)
    dst = cp.for_country(target)
    if src is None or dst is None:
        missing = [c for c, p in ((source, src), (target, dst)) if p is None]
        return [f"No country pack for {', '.join(str(m) for m in missing)}. An "
                "uncovered market is answered with silence rather than a guess."]
    if src.country == dst.country:
        return [f"{src.name} and {dst.name} are the same market — nothing to cross."]

    out = [f"READING {src.name.upper()} AGAINST {dst.name.upper()}."]
    for dimension, label in ((cp.OCCUPATION, "Occupation"),
                             (cp.QUALIFICATION, "Qualification")):
        result = cp.bridge(src.country, dst.country, dimension)
        if not result["ok"]:
            out.append(f"{label} — NO ROUTE. {result['refusal']}")
            continue
        weight = _WEIGHT.get(result["hardness"], "")
        out.append(
            f"{weight}{label} — {src.name} to {dst.name} via {result['spine']}, "
            f"and the route is only as sound as its weaker half:")
        for hop in result["route"]:
            out.append(
                f"    · {hop['from']} to {hop['to']}"
                + (f" ({hop['scheme']})" if hop.get("scheme") else "")
                + (f" — {hop['source']}" if hop.get("source") else ""))
    out.append(
        "Grade and pay are not offered here and will not be. Grades are separate "
        "institutions negotiated by different parties under different law, with no "
        "legal equivalence between them; pay has no neutral unit, and an FX rate on "
        "a stated day, purchasing power parity and a labour-cost index answer three "
        "different questions with three different numbers. Either can be decided "
        "deliberately by an employer — that judgement belongs to them and is not a "
        "fact about the two markets."
    )
    return out

def market_caveat() -> str:
    """The framing both of the above are read under."""
    return (
        "These notes report what published law and collective agreements say, with the "
        "source and its weight named. They are NOT legal advice and do not settle your "
        "position — and several of them turn on how a system is actually used rather than "
        "how it is described, which is a question about your deployment and not about "
        "this screen. Confirm anything you act on with someone who can carry that advice."
    )


# ── what this tool holds about a market, and what it does not ─────────────
#
# `capability_gaps()` was written with the slots and then called by nothing for
# as long as it existed. Its whole subject is the difference between a slot
# holding None ("nobody has answered this") and a slot holding an empty
# structure ("we looked and there is nothing to say"), and a distinction that
# reaches no screen is a distinction nobody has. The functions below are its
# first caller, and they keep that difference in words rather than collapsing
# both into a blank.

#: The six capability slots, in the order a gap in them costs money. Reporting
#: first: a duty missed is a filing missed, where every other slot changes how
#: a number should be READ rather than whether something must be filed at all.
_CAPABILITY_SLOTS = (
    "reporting", "org_structure", "compensation",
    "job_architecture", "skills", "performance",
)

#: What each slot answers, and what is lost on this product's screens without
#: it. The second half is the part worth writing down: "skills: not answered"
#: tells a reader nothing they can act on, where "no taxonomy a role is coded
#: in" tells them which screen goes quiet and what to go and find.
_SLOT_QUESTION = {
    "reporting": ("Pay-reporting duty",
                  "what must be filed, from when, and how often"),
    "org_structure": ("What counts as the employer",
                      "the unit every headcount threshold is counted in"),
    "compensation": ("How pay is set",
                     "whether a market comparison and a compa-ratio mean anything here"),
    "job_architecture": ("What a level is",
                         "the market's own grading unit, before this tool imposes one"),
    "skills": ("What a skill is read against",
               "the qualification and occupation taxonomies a role is coded in"),
    "performance": ("What a talent grid is, legally",
                    "whether a 9-box is a neutral instrument or a co-determined one"),
    "pay_components": ("Statutory pay components",
                       "the components that are law here rather than an employer's choice"),
    "crosswalks": ("Collective-agreement crosswalk",
                   "whether a grade may be positioned against a published scale at all"),
    "vocabulary": ("Payroll column vocabulary",
                   "the words a payroll export in this market actually uses"),
}

#: Hardness in three words, for a line that already carries a market name and
#: cannot afford `_WEIGHT`'s full clause. Never used INSTEAD of `_WEIGHT` on a
#: claim's own sentence — only to mark a route, which is not itself a claim.
_WEIGHT_SHORT = {
    cp.WET: "in law",
    cp.UITLEG: "a reading",
    cp.CONVENTIE: "practice",
    cp.ONBEVESTIGD: "UNVERIFIED",
}


def _walk_claims(value) -> list:
    """Every Claim anywhere inside one field, however deeply it is wrapped.

    Walks dataclass fields generically rather than by name, and that is the
    whole point rather than a convenience: this module and the packs are being
    written at the same time, so a Belgian qualification mapping or a new field
    saying "no authoritative correspondence exists" has to be counted by this
    walk on the day it lands, not on the day somebody remembers to add its name
    to a list in here. A hand-kept list of fields fails the same way a hand-kept
    country register does — what it forgets is the thing nobody tested.
    """
    import dataclasses

    if isinstance(value, cp.Claim):
        return [value]
    out: list = []
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            out += _walk_claims(getattr(value, f.name, None))
    elif isinstance(value, (tuple, list, set)):
        for item in value:
            out += _walk_claims(item)
    elif isinstance(value, dict):
        for item in value.values():
            out += _walk_claims(item)
    return out


def _labelled_claims(pack) -> list:
    """(where it lives, the claim) for every claim in a pack.

    The label is what makes an UNVERIFIED or a STALE line actionable. "UNVERIFIED
    — works councils are consulted in practice" leaves a reader hunting for which
    part of the market that touches; the same sentence under "What a talent grid
    is, legally" says which screen is affected and therefore who to ask.
    """
    import dataclasses

    out: list = []
    if pack is None or not dataclasses.is_dataclass(pack):
        return out
    for f in dataclasses.fields(pack):
        label = _SLOT_QUESTION.get(f.name, (f.name.replace("_", " ").capitalize(), ""))[0]
        for claim in _walk_claims(getattr(pack, f.name, None)):
            out.append((label, claim))
    return out


#: What each of the three slot states MEANS, written once.
#:
#: A view needs these words as a legend and `coverage_notes` needs them as
#: sentences, and the failure to avoid is two slightly different explanations of
#: "held and empty" drifting apart until one of them is wrong. The distinction
#: is the reason `capability_gaps()` exists at all; it does not get to be
#: paraphrased.
_STATE_MEANING = {
    "not answered": ("Nobody has established this market's answer yet. That is a gap in "
                     "this tool, not a finding that there is nothing to say."),
    "held and empty": ("This market was looked at and nothing was recorded under it, "
                       "which is an answer rather than a question nobody asked."),
    "answered": "Claims are held, each with its source and its evidential weight.",
}


def slot_state_meaning(state: str) -> str:
    """The one explanation of a slot state, for a caller that renders its own grid."""
    return _STATE_MEANING.get(state, "")


def _slot_states(pack, unanswered: dict) -> list:
    """Each capability slot as one of three states, never as a blank.

    THE THREE STATES ARE THE POINT, and two of them would render identically if
    this returned booleans:

      * NOT ANSWERED — the slot holds None. Nobody has established this market's
        answer yet, and `capability_gaps()` is what says so.
      * HELD AND EMPTY — the slot exists and carries no claims. That is a
        recorded finding that there is nothing to say here: an answer, not a
        to-do.
      * ANSWERED — the slot carries claims, and how many is stated, so a reader
        can tell one sentence from a researched slot.

    A caller that draws the first two the same way has destroyed the distinction
    the whole mechanism exists for, so the state travels as a word rather than
    as the absence of one.

    NO PACK REACHES THE MIDDLE STATE TODAY: every capability dataclass in the
    package requires at least one Claim, so a slot that exists always carries
    something. It is implemented anyway, because the day one of those fields
    gains a default is the day an empty slot would otherwise start rendering as
    a blank — which is the failure this function was written to prevent, arriving
    through a change nobody would connect to it.
    """
    states = []
    for name in _CAPABILITY_SLOTS:
        label, question = _SLOT_QUESTION.get(name, (name, ""))
        if name in unanswered:
            states.append({"slot": name, "label": label, "question": question,
                           "state": "not answered", "claims": 0})
            continue
        claims = _walk_claims(getattr(pack, name, None))
        states.append({
            "slot": name, "label": label, "question": question,
            "state": "answered" if claims else "held and empty",
            "claims": len(claims),
        })
    return states


def _route_lines(country: str) -> list:
    """Which markets this one's data can be read against, and where it cannot.

    Every pair is put to `bridge()` and nothing is counted by hand. The two
    dimensions answer very differently today — occupation reaches every other
    market held, qualification under half of them — and an asymmetry like that
    is exactly what gets typed into a sentence once and goes quietly wrong the
    first time a pack gains a mapping.

    THE REFUSAL IS CARRIED THROUGH VERBATIM rather than reduced to "no route".
    It used to be that `bridge()` could not tell two absences apart — a market
    nobody had mapped yet, and a market where no authoritative correspondence
    exists to map — and carrying the prose was how that honesty survived to a
    reader. IT CAN TELL THEM APART NOW: a pack may declare
    `no_correspondence` for a dimension, and the result carries a structured
    `absence` alongside the prose. Germany declares it for qualification, on the
    evidence already in its own pack — the DQR is a joint declaration rather
    than a statute, has orientierenden Charakter, and confers no entitlement.

    The prose still goes through verbatim, for a different reason than before:
    the structured key says WHICH KIND of absence, and the sentence says WHY,
    and a reader deciding whether to trust a blank needs the second. Turning
    that into a red cross on a grid would be inventing the answer it
    refused to give.
    """
    packs = cp.load()
    others = [c for c in sorted(packs) if c != country and c != cp.BASELINE]
    out: list = []
    for dimension, label in ((cp.OCCUPATION, "Occupation"),
                             (cp.QUALIFICATION, "Qualification")):
        spine = cp.SPINE.get(dimension)
        reached: list = []
        refused: dict = {}
        for other in others:
            result = cp.bridge(country, other, dimension)
            name = packs[other].name
            if result.get("ok"):
                weight = _WEIGHT_SHORT.get(result.get("hardness"), "weight unstated")
                reached.append(f"{name} ({weight})")
            else:
                refused.setdefault(result.get("refusal") or "No route.", []).append(name)
        if reached:
            out.append(f"{label} — reads against {', '.join(reached)} through {spine}. "
                       f"Each route is two hops and is labelled with the weaker of them.")
        for refusal, names in refused.items():
            out.append(f"{label} — NO ROUTE to {', '.join(names)}. {refusal}")
        if not reached and not refused:
            out.append(f"{label} — no other market is held to read this one against.")
    return out


def market_coverage(country: Optional[str] = None) -> Optional[dict]:
    """What this tool holds about one market, and what it does not.

    Returns None for a market no pack exists for, which is the rule
    `reporting_for()` already enforces one layer down: an uncovered market is
    answered with silence and never with the EU baseline. Several member states
    are stricter than the directive — France's Index Egapro starts at 50
    employees — so lending a stranger the baseline understates a duty that
    already exists, and understating a legal obligation is the worst answer
    available.

    DELIBERATELY NOT A SCORE. Nothing that comes back is a percentage, because
    "Germany 71% covered" invites a reader to trust the 71% and stop reading,
    and the missing 29% is not uniform: one unanswered reporting duty is a
    filing somebody misses, five unanswered conventions are context. What is
    returned is WHICH slots are unanswered, WHICH claims are unverified, WHICH
    sit on a review clock and WHICH crossings exist — names a reader can act on
    instead of an arithmetic they can trust and stop at.
    """
    pack = cp.for_country(country)
    if pack is None:
        return None
    code = pack.country
    unanswered = cp.capability_gaps(code)

    labelled = _labelled_claims(pack)
    mix: dict = {}
    for _, claim in labelled:
        mix[claim.hardness] = mix.get(claim.hardness, 0) + 1

    unverified, stale, on_clock = [], [], []
    for label, claim in labelled:
        # `_line` returns None for a claim with no value and no words, and that
        # claim is exactly the one that must not vanish here: an unverified or
        # lapsed statement with nothing written in it is the emptiest thing in
        # the pack, and silently dropping it would make it the invisible one.
        if not claim.verified:
            unverified.append(_line(claim, lead=f"{label} — ")
                              or f"UNVERIFIED — {label} — held with no value and no "
                                 f"words, so what was looked for is not recorded.")
        if claim.needs_review():
            stale.append(_line(claim, lead=f"{label} — ")
                         or f"STALE — {label} — its review interval has lapsed and it "
                            f"carries no words to re-check it against.")
        elif getattr(claim, "review_after_months", None):
            # A claim that has NOT lapsed but is on a clock. Shown because the
            # useful moment to re-check "no implementing law has been published"
            # is before it goes stale, not after — and because a reader who only
            # ever sees STALE learns that this tool checks nothing until it is
            # already late.
            age = claim.months_old()
            if age is not None:
                left = claim.review_after_months - age
                body = (claim.note or str(claim.value)).strip()
                when = ("checked this month" if age == 0 else
                        f"checked {age} month{'' if age == 1 else 's'} ago")
                on_clock.append(
                    f"{label} — {when}, due again in {left} "
                    f"month{'' if left == 1 else 's'}: {body[:160]}")

    return {
        "country": code,
        "name": pack.name,
        "status": pack.status,
        "baseline": code == cp.BASELINE,
        "slots": _slot_states(pack, unanswered),
        "claims": len(labelled),
        "hardness": mix,
        "unverified": unverified,
        "stale": stale,
        "on_clock": on_clock,
        "routes": _route_lines(code),
    }


def coverage_notes(country: Optional[str] = None) -> list:
    """One market's coverage as sentences, for anywhere a table will not do.

    Same posture as every other note in this module: it returns strings and
    knows nothing about Streamlit, so the sentences that carry the weight can be
    tested without running the app. A market with no pack returns an empty list
    — silence, rather than a heading standing over nothing.
    """
    report = market_coverage(country)
    if report is None:
        return []
    out = [f"WHAT THIS TOOL HOLDS ABOUT {report['name'].upper()}."]
    if report["baseline"]:
        out.append("This is the directive baseline and not a market anyone works in. A "
                   "covered market's pack falls back to it for reporting bands; a market "
                   "no pack exists for is never lent it.")

    for slot in report["slots"]:
        state = slot["state"]
        if state == "answered":
            out.append(f"{slot['label']} — ANSWERED, {slot['claims']} claim"
                       f"{'' if slot['claims'] == 1 else 's'} on {slot['question']}.")
        else:
            out.append(f"{slot['label']} — {state.upper()} ({slot['question']}). "
                       + slot_state_meaning(state))

    mix = ", ".join(f"{n} {h}" for h, n in sorted(report["hardness"].items(),
                                                  key=lambda kv: -kv[1]))
    if mix:
        out.append(f"Evidence held: {mix}. Counts, not a proportion — a market carrying "
                   f"one unverified sentence about a filing duty is in worse shape than "
                   f"one carrying six about custom, and a ratio would hide that.")
    out.extend(report["unverified"])
    out.extend(report["stale"])
    out.extend(report["on_clock"])
    out.extend(report["routes"])
    return out


def uncovered_markets(codes) -> list:
    """Of the markets a user may be offered, the ones no pack exists for.

    Named so they can be shown as HOLDING NOTHING, which is a different screen
    from being shown the directive. The country registry can offer a market
    before anyone has researched it — that is how a market gets opened — and the
    honest report of that state is that this tool says nothing here, not an
    inherited table that reads like an answer.
    """
    held = cp.load()
    seen, out = set(), []
    for code in codes or ():
        upper = str(code or "").strip().upper()
        if upper and upper not in held and upper not in seen:
            seen.add(upper)
            out.append(upper)
    return out

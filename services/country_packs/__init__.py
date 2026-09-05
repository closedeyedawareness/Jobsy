"""
jobsy/services/country_packs/__init__.py

A country pack is everything Jobsy needs to know about ONE market that is not
already true everywhere: the language its payroll exports are written in, the
pay components its law makes statutory, the reporting duty its employers are
under, and the collective-agreement structure its grades can honestly be
positioned against.

The plan document set the bar: *"make adding a market importing rows, not
writing a migration."* This module is the other half of that. Migration 0012
made the reference LIBRARY hold two countries. This makes the KNOWLEDGE hold
two countries, so that adding Belgium is writing `be.py` against a schema a
test enforces, rather than editing six call sites and hoping none was missed.

── Why every claim carries its evidence ──────────────────────────────────────

A pay-analytics tool that states a threshold is making a legal claim on behalf
of whoever reads it. Get a Dutch date wrong and a client files late; get a
German one wrong and they file when they did not have to. Neither error looks
wrong on screen, which is the whole problem: wrong pay law renders exactly like
right pay law.

So a pack does not hold bare values. It holds `Claim`s, and a claim carries
where it came from and how hard it is:

    WET          in a statute, a directive or a collective agreement, cited
    UITLEG       official guidance or an explanatory memorandum
    CONVENTIE    market or professional practice, no legal force
    ONBEVESTIGD  we looked and could not verify it

`ONBEVESTIGD` is the important one, and it is the reason this vocabulary is
borrowed from Waterpas rather than invented here. A gap that says so is safe.
A gap filled with a plausible number is a liability that compounds silently,
and the person who would be held to it is the client, not us.

── The IP boundary, as a rule instead of a comment ───────────────────────────

`cao_crosswalk_service` documents a distinction that took real work to get
right: ISF publishes a point-BOUNDARY table, so positioning a grade against it
is honest; CATS publishes no point table at all, so only the functiegroep →
salarisgroep LABEL alignment can be shown, with no implied score. Reproducing
a protected scoring method would be neither legal nor honest.

Today that lives in a docstring, which the next country pack cannot inherit.
Here it is a field: a crosswalk declares `publishes_point_table`, and
`validate()` refuses a pack that carries point ranges without one. Germany's
ERA and France's conventions collectives will meet the same rule before they
reach a screen.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "WET", "UITLEG", "CONVENTIE", "ONBEVESTIGD", "HARDNESS",
    "Claim", "ReportingBand", "PayReporting", "CrosswalkSpec", "CountryPack",
    "validate", "load", "for_country", "available", "has_crosswalk",
]

# ── hardness ─────────────────────────────────────────────────────────────────

WET = "WET"
UITLEG = "UITLEG"
CONVENTIE = "CONVENTIE"
ONBEVESTIGD = "ONBEVESTIGD"
HARDNESS = (WET, UITLEG, CONVENTIE, ONBEVESTIGD)

#: A pack may be shown to a client only at these statuses. `draft` is visible
#: to us and to tests; `stub` means the country exists in the registry and we
#: have nothing to say about it yet, which is a legitimate answer.
LIVE, DRAFT, STUB = "live", "draft", "stub"
STATUSES = (LIVE, DRAFT, STUB)


@dataclass(frozen=True)
class Claim:
    """One statement about a market, with the evidence that backs it.

    `value` may be anything: a number, a date, a string, a tuple. What matters
    is that it never travels without `hardness` and, unless it is ONBEVESTIGD,
    without a `source` somebody can open and check.

    `as_of` is the date the claim was last verified, not the date the law was
    passed. Pay legislation across the EU is moving every quarter at the
    moment, so a claim that was true in March is not self-evidently true now,
    and the screen should be able to say when we last looked.
    """
    value: Any
    hardness: str
    source: str = ""
    as_of: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.hardness not in HARDNESS:
            raise ValueError(
                f"hardness {self.hardness!r} is not one of {HARDNESS}. "
                "A claim with no hardness is a claim nobody can weigh.")

    @property
    def verified(self) -> bool:
        return self.hardness != ONBEVESTIGD

    def __str__(self) -> str:
        return f"{self.value}" if self.verified else f"{self.value} (ONBEVESTIGD)"


@dataclass(frozen=True)
class ReportingBand:
    """One employer-size band of a pay-reporting duty.

    Bands are held separately rather than as one 'threshold' number because
    the directive phases the duty in by size and the phases carry different
    frequencies. A tool that flattens that into "reports from 2028" tells a
    120-person employer something false in both directions at once.
    """
    min_employees: int
    max_employees: Optional[int]      # None = no upper bound
    first_report: Claim
    frequency: Claim                  # e.g. "annually", "every 3 years", "none"


@dataclass(frozen=True)
class PayReporting:
    """What this country's employers must actually do, and from when."""
    transposed: Claim                       # has Directive (EU) 2023/970 landed here
    national_law: Optional[Claim] = None    # the local statute, if one exists
    bands: tuple[ReportingBand, ...] = ()
    joint_assessment_trigger_pct: Optional[Claim] = None
    pre_existing_duty: Optional[Claim] = None  # a national pay-gap law predating the directive

    def band_for(self, headcount: int) -> Optional[ReportingBand]:
        for b in self.bands:
            if headcount >= b.min_employees and (b.max_employees is None
                                                 or headcount <= b.max_employees):
                return b
        return None


@dataclass(frozen=True)
class CrosswalkSpec:
    """How this country's collective-agreement structure may be shown.

    `publishes_point_table` is the honesty switch. True means the system
    publishes the point boundaries that separate its groups, so positioning
    our own grade against that published sequence is an indicative crosswalk
    against public information. False means it does not, and then the only
    honest output is a label alignment with no number attached — because the
    only way to produce a number would be to re-derive a scoring method that
    is somebody's protected IP.

    `system` is the institution's own name (ISF, CATS, ERA, TVöD, CP 200).
    Never translate it: a Belgian reader looking for "paritair comité 200"
    will not recognise "collective agreement committee 200".
    """
    system: str
    publishes_point_table: bool
    groups: tuple[str, ...] = ()
    point_bands: tuple[tuple[str, int, int], ...] = ()   # (group, min, max)
    scales: dict[str, tuple[float, float]] = field(default_factory=dict)
    sectors: tuple[str, ...] = ()
    source: Claim = field(default_factory=lambda: Claim(None, ONBEVESTIGD))


@dataclass(frozen=True)
class CountryPack:
    """Everything Jobsy knows about one market."""
    country: str                    # ISO-3166 alpha-2, or 'EU' for the baseline
    name: str
    currency: str
    languages: tuple[str, ...]
    status: str = STUB
    #: concept -> the column names a payroll export in this country actually
    #: uses. This is what stops `_smart_detect` from being a pile of Dutch
    #: words scattered across five files.
    vocabulary: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: statutory or near-universal pay components, each with its evidence
    pay_components: tuple[Claim, ...] = ()
    reporting: Optional[PayReporting] = None
    crosswalks: tuple[CrosswalkSpec, ...] = ()
    gender_codes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    @property
    def unverified(self) -> tuple[Claim, ...]:
        """Every claim in this pack we could not stand behind."""
        out: list[Claim] = list(c for c in self.pay_components if not c.verified)
        r = self.reporting
        if r is not None:
            for c in (r.transposed, r.national_law, r.joint_assessment_trigger_pct,
                      r.pre_existing_duty):
                if c is not None and not c.verified:
                    out.append(c)
            for b in r.bands:
                out += [c for c in (b.first_report, b.frequency) if not c.verified]
        out += [x.source for x in self.crosswalks if not x.source.verified]
        return tuple(out)


# ── validation ───────────────────────────────────────────────────────────────

def validate(pack: CountryPack) -> list[str]:
    """Everything wrong with a pack, as a list of sentences. Empty means clean.

    Returns rather than raises, because the useful output is *all* the
    problems at once — a pack author fixing one thing at a time, six times,
    is how the sixth one gets skipped.
    """
    problems: list[str] = []
    p = pack

    if not p.country or not p.country.isupper() or len(p.country) not in (2, 3):
        problems.append(f"country {p.country!r} should be an ISO alpha-2 code, or 'EU'.")
    if p.status not in STATUSES:
        problems.append(f"status {p.status!r} is not one of {STATUSES}.")
    if not p.currency:
        problems.append("currency is required; a pay pack without a currency prices nothing.")
    if not p.languages:
        problems.append("languages is required; column detection needs to know what to look for.")

    def _claim(c: Optional[Claim], where: str) -> None:
        if c is None:
            return
        if c.hardness in (WET, UITLEG) and not c.source:
            problems.append(
                f"{where}: hardness {c.hardness} without a source. A claim presented as "
                f"law must cite the law, or it is an opinion wearing a uniform.")
        if c.verified and not c.as_of:
            problems.append(f"{where}: verified claim without an as_of date.")
        if c.hardness == ONBEVESTIGD and c.value not in (None, "", ()) and not c.note:
            problems.append(
                f"{where}: ONBEVESTIGD but carries a value and no note saying what was "
                f"looked for. An unverified number that looks like a fact is the failure "
                f"mode this whole module exists to prevent.")

    for i, c in enumerate(p.pay_components):
        _claim(c, f"pay_components[{i}]")

    r = p.reporting
    if r is not None:
        _claim(r.transposed, "reporting.transposed")
        _claim(r.national_law, "reporting.national_law")
        _claim(r.joint_assessment_trigger_pct, "reporting.joint_assessment_trigger_pct")
        _claim(r.pre_existing_duty, "reporting.pre_existing_duty")
        for i, b in enumerate(r.bands):
            _claim(b.first_report, f"reporting.bands[{i}].first_report")
            _claim(b.frequency, f"reporting.bands[{i}].frequency")
            if b.max_employees is not None and b.max_employees < b.min_employees:
                problems.append(f"reporting.bands[{i}]: max below min.")
        edges = sorted((b.min_employees, b.max_employees) for b in r.bands)
        for (lo1, hi1), (lo2, _) in zip(edges, edges[1:]):
            if hi1 is not None and lo2 <= hi1:
                problems.append(
                    f"reporting bands overlap at {lo2}: an employer of that size would "
                    f"match two duties, and the tool would pick whichever comes first.")

    for x in p.crosswalks:
        _claim(x.source, f"crosswalk[{x.system}].source")
        if x.point_bands and not x.publishes_point_table:
            problems.append(
                f"crosswalk[{x.system}] carries point bands but declares that the system "
                f"publishes no point table. Showing a point position derived from a "
                f"method that is not public re-derives protected IP and states a "
                f"classification the client cannot defend. Label alignment only.")
        if x.scales and not x.groups:
            problems.append(f"crosswalk[{x.system}] has salary scales for groups it does not list.")
        for g, _lo, _hi in x.point_bands:
            if x.groups and g not in x.groups:
                problems.append(f"crosswalk[{x.system}] has a point band for unknown group {g!r}.")

    if p.status == LIVE:
        if p.reporting is None:
            problems.append("a live pack must state the reporting duty, even if the answer "
                            "is that there is none yet.")
        for c in p.unverified:
            problems.append(
                f"live pack carries an ONBEVESTIGD claim ({c.note or c.value!r}). "
                f"Move it to draft, or verify it. A market goes live when we can stand "
                f"behind every sentence it will put on a client's screen.")
    return problems


# ── the registry ─────────────────────────────────────────────────────────────

_CACHE: dict[str, CountryPack] = {}


def load(refresh: bool = False) -> dict[str, CountryPack]:
    """Every pack in this package, keyed by country code.

    Discovery is by module, not by a hand-kept list, for the same reason
    `alle_regelcodes()` in Waterpas reads the source rather than a list: a
    register you must remember to update is the first thing that goes stale,
    and the thing it forgets is the market nobody tested.
    """
    global _CACHE
    if _CACHE and not refresh:
        return _CACHE
    found: dict[str, CountryPack] = {}
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{mod.name}")
        pack = getattr(module, "PACK", None)
        if isinstance(pack, CountryPack):
            found[pack.country.upper()] = pack
    _CACHE = found
    return found


def available(status: Optional[str] = None) -> list[str]:
    """Country codes we hold a pack for, optionally filtered by status."""
    return sorted(c for c, p in load().items() if status is None or p.status == status)


def for_country(country: Optional[str] = None) -> Optional[CountryPack]:
    """The pack for a market, or None.

    None is a real answer and callers must handle it: showing another
    country's numbers under this country's flag is the failure the country
    dimension was introduced to stop.
    """
    if not country:
        try:
            from services import country_service
            country = country_service.active_country()
        except Exception:
            return None
    return load().get((country or "").upper())


def has_crosswalk(country: Optional[str] = None, system: Optional[str] = None) -> bool:
    """Whether a collective-agreement crosswalk may be rendered for this market.

    This replaces `_is_dutch_client()`. The question was never "is the client
    Dutch" — it was "do we hold a crosswalk we can honestly show", and those
    two stopped being the same question the moment a second pack existed.

    `system` narrows the question further, and callers that render one specific
    crosswalk must pass it. The renderer in ui/views/pay_equity.py draws ISF and
    CATS, which are Dutch Metalektro institutions; asking only "does this market
    have a crosswalk" would answer True for Belgium the day its PC 200 pack
    leaves STUB, and the screen would then put a Belgian client's staff onto
    Dutch salarisgroepen beside euro monthly scales — implying a legal
    classification that does not apply to them. That is the exact failure the
    original nationality check was written to prevent, so it must not come back
    through the door marked "more general".
    """
    pack = for_country(country)
    if not (pack and pack.status in (LIVE, DRAFT) and pack.crosswalks):
        return False
    if system is None:
        return True
    want = system.strip().lower()
    return any(want in cw.system.lower() for cw in pack.crosswalks)


BASELINE = "EU"


def reporting_for(country: Optional[str] = None) -> tuple[Optional[PayReporting], str]:
    """The reporting duty that applies, and which pack it came from.

    Resolution mirrors migration 0012: the country's own answer wins, and the
    'EU' pack is the fallback — a row somebody wrote on purpose, not a NULL.
    A country pack that holds no bands of its own is not incomplete; it is
    saying the directive's bands apply unchanged, which for most member states
    is the true answer and is far safer than twenty-seven hand-copied tables
    drifting apart.

    The second element of the tuple is the source, because a screen that shows
    a legal date owes the reader the difference between "your national law says
    this" and "the directive says this and your country has not legislated
    yet". Those are not the same sentence.
    """
    pack = for_country(country)
    if pack is None:
        # A market we hold no pack for gets silence, not the directive.
        # The directive does apply across the Union, so answering with the EU
        # baseline is tempting and wrong: several member states are stricter
        # than it. France's Index Egapro starts at 50 employees, so a French
        # client handed the EU bands would be told they have no duty until 100
        # when in fact they have one at 60. Understating a legal obligation is
        # the worst answer available, and it is worse than admitting we do not
        # cover France yet. Inheritance is for countries somebody has looked at.
        return None, ""
    if pack.reporting and pack.reporting.bands:
        return pack.reporting, pack.country
    baseline = load().get(BASELINE)
    if baseline and baseline.reporting:
        return baseline.reporting, BASELINE
    return pack.reporting, pack.country


def band_for(headcount: int, country: Optional[str] = None):
    """The reporting band for a headcount, with the pack it was resolved from.

    Returns (band, source_country). Both may be None/'' — an unknown market is
    answered with silence, never with the Dutch numbers under another flag.
    """
    reporting, source = reporting_for(country)
    if not reporting:
        return None, ""
    return reporting.band_for(headcount), source

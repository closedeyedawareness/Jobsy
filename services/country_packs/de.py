"""
jobsy/services/country_packs/de.py — Germany.

Germany breaks an assumption the schema inherited from the Netherlands, and
recording that is worth more than any number in this file.

**Headcount is not a company number here.** The Entgelttransparenzgesetz
counts per *Betrieb* — establishment — not per legal entity. A German client
with 900 people across four sites may have no Betrieb over 200 and therefore no
individual information right anywhere in the company, while a 600-person
single-site client has both duties. `PayReporting.band_for(headcount)` takes
one integer and cannot express that. It is not fixed here, because quietly
feeding it a company total would produce a confident wrong answer, which is
exactly the failure this package was built to stop. It is written down instead,
at the top of the file, so the next person meets it before they trust the API.

Two more things that a Dutch-shaped reading gets wrong:

  * **"divers" is a real legal option.** Since the 2018 Personenstandsgesetz
    change, German records carry m/w/d. A binary gender field does not throw
    on a `d` — it drops the person, silently, from a fairness analysis. Being
    dropped from the count is a poor outcome for someone whose recognition in
    that register was fought for.

  * **The Betriebsrat co-determines pay structuring** under BetrVG section 87(1)
    no. 10. A pay-structure recommendation that a Dutch client could simply
    implement is, in Germany, subject to works-council agreement. Jobsy should
    not present a German structural change as something the employer decides
    alone.

── On the hardness markers ──────────────────────────────────────────────────

As in the Belgian pack: assembled from web research on 2026-09-05, with no
primary text read. WET is used only where the statute itself is cited and its
existence is not in doubt; the thresholds and frequencies are UITLEG or
ONBEVESTIGD until somebody opens gesetze-im-internet.de. STUB.
"""
from __future__ import annotations

from . import (CONVENTIE, ONBEVESTIGD, STUB, UITLEG, WET, Claim, CountryPack,
               CrosswalkSpec, PayReporting, ReportingBand)

_ENTGTRANSPG = "Entgelttransparenzgesetz (EntgTranspG), in force since 6 July 2017"
_ENTGTRANSPG_URL = "https://www.gesetze-im-internet.de/entgtranspg/"
_BETRVG_URL = "https://www.gesetze-im-internet.de/betrvg/__87.html"
_ASOF = "2026-09-05"
_RESEARCH = "web research 2026-09-05; NOT yet checked against the primary text"

# ── vocabulary ───────────────────────────────────────────────────────────────
#
# German payroll exports lean on compounds, so detection has to match on a
# substring rather than a whole heading: "Bruttomonatsentgelt" and
# "Jahresbruttogehalt" are both salary and neither is "Gehalt".
VOCABULARY: dict[str, tuple[str, ...]] = {
    "salary":   ("gehalt", "bruttogehalt", "entgelt", "bruttoentgelt", "grundentgelt",
                 "grundvergutung", "vergutung", "lohn", "bruttolohn", "monatsentgelt",
                 "jahresgehalt", "tabellenentgelt"),
    "gender":   ("geschlecht", "gender", "m/w/d", "geschlechtsangabe"),
    "function": ("funktion", "stelle", "stellenbezeichnung", "taetigkeit", "tatigkeit",
                 "position", "berufsbezeichnung"),
    "level":    ("entgeltgruppe", "eg", "entgeltstufe", "stufe", "tarifgruppe",
                 "lohngruppe", "gehaltsgruppe", "verguetungsgruppe", "eingruppierung",
                 "era-stufe", "tarifgebiet"),
    "fte":      ("vollzeitaequivalent", "vzae", "vze", "beschaeftigungsgrad",
                 "arbeitszeitfaktor", "wochenarbeitszeit", "teilzeit", "teilzeitfaktor"),
    "tenure":   ("eintrittsdatum", "betriebszugehoerigkeit", "eintritt",
                 "beschaeftigt seit", "dienstjahre"),
    "variable": ("bonus", "praemie", "pramie", "zulage", "zuschlag",
                 "leistungszulage", "variable verguetung", "tantieme"),
    "holiday":  ("urlaubsgeld", "weihnachtsgeld", "sonderzahlung", "jahressonderzahlung"),
    "employee": ("mitarbeiter", "beschaeftigter", "arbeitnehmer", "personalnummer"),
    "country":  ("land", "arbeitsland", "standort"),
    "establishment": ("betrieb", "betriebsstaette", "standort", "niederlassung"),
}

#: Three values, not two. `d` is *divers*, a legal civil-status option since
#: the Personenstandsgesetz change of 2018, and it must reach the analysis as
#: itself rather than as an unparsed blank.
GENDER_CODES: dict[str, tuple[str, ...]] = {
    "female":  ("w", "weiblich", "f", "frau", "female"),
    "male":    ("m", "maennlich", "mannlich", "mann", "male"),
    "diverse": ("d", "divers", "x", "ohne angabe", "keine angabe"),
}

# ── the reporting duty ───────────────────────────────────────────────────────

_TRANSPOSED = Claim(
    value=False, hardness=ONBEVESTIGD, as_of=_ASOF,
    note="Research indicates Germany had not transposed Directive (EU) 2023/970 by the "
         "7 June 2026 deadline and that a Referentenentwurf amending the EntgTranspG was "
         "the expected route. Verify on gesetze-im-internet.de and in the BMAS "
         "publications before stating a client's directive position. The 2017 Act "
         "applies regardless of the directive's status.")

REPORTING = PayReporting(
    transposed=_TRANSPOSED,
    national_law=Claim(_ENTGTRANSPG, WET, _ENTGTRANSPG_URL, _ASOF,
                       note="Germany legislated on pay transparency in 2017. This is the "
                            "live duty, and its thresholds are nothing like the EU's."),
    pre_existing_duty=Claim(
        True, WET, _ENTGTRANSPG_URL, _ASOF,
        note="The Act creates several separate duties, not one duty with size bands. "
             "The individual RIGHT TO INFORMATION (Auskunftsanspruch) is understood to "
             "apply in establishments with more than 200 employees; the voluntary "
             "internal AUDIT (betriebliches Pruefverfahren) and the mandatory REPORT "
             "(Bericht zur Gleichstellung und Entgeltgleichheit) attach above 500. The "
             "bands below describe the REPORT only. Do not present the 200 threshold as "
             "a reporting threshold: they are different obligations with different "
             "consequences."),
    joint_assessment_trigger_pct=None,   # no percentage trigger in the 2017 Act
    bands=(
        ReportingBand(
            min_employees=501, max_employees=None,
            first_report=Claim("in force since 2017", UITLEG, _RESEARCH, _ASOF,
                               note="Report duty understood to attach to employers with "
                                    "more than 500 employees who are required to produce "
                                    "a Lagebericht under the HGB. Counted per Betrieb, "
                                    "which the headcount argument cannot express."),
            frequency=Claim("every 3 years if bound by a collective agreement, otherwise "
                            "every 5", ONBEVESTIGD, _RESEARCH, _ASOF,
                            note="The tarifgebunden / non-tarifgebunden split in the "
                                 "reporting cycle is reported by secondary sources and "
                                 "must be read in the Act before it is shown. A client "
                                 "told the wrong cycle files in the wrong year."),
        ),
        ReportingBand(
            min_employees=0, max_employees=500,
            first_report=Claim(None, UITLEG, _RESEARCH, _ASOF,
                               note="No report duty. An establishment over 200 may still "
                                    "owe the individual Auskunftsanspruch — see "
                                    "pre_existing_duty. 'No report' does not mean "
                                    "'no obligations'."),
            frequency=Claim("none", UITLEG, _RESEARCH, _ASOF),
        ),
    ),
)

# ── pay components ───────────────────────────────────────────────────────────

PAY_COMPONENTS = (
    Claim(("urlaubsgeld", None), CONVENTIE, "", _ASOF,
          note="Holiday pay is not statutory in Germany. It comes from the Tarifvertrag "
               "or the individual contract, so there is no national percentage to apply "
               "and none should be invented. Read it from the client's PayMix rows."),
    Claim(("weihnachtsgeld", None), CONVENTIE, "", _ASOF,
          note="Likewise collectively agreed rather than statutory."),
    Claim(("tarifbindung", None), UITLEG, _RESEARCH, _ASOF,
          note="Whether the employer is bound by a collective agreement changes both the "
               "pay structure and, apparently, the reporting cycle. It is a property of "
               "the employer that the analysis needs, not a pay component as such, and it "
               "is recorded here because there is nowhere better for it yet."),
)

# ── crosswalk ────────────────────────────────────────────────────────────────

ERA = CrosswalkSpec(
    system="ERA (Entgeltrahmenabkommen, Metall- und Elektroindustrie)",
    publishes_point_table=False,
    groups=(),           # deliberately empty: see the source note
    point_bands=(),
    sectors=("Metall- und Elektroindustrie",),
    source=Claim("no single national ERA table exists", ONBEVESTIGD, _RESEARCH, _ASOF,
                 note="ERA is not one agreement. Research reports roughly eleven regional "
                      "Tarifgebiete (Baden-Wuerttemberg, Bayern, NRW and so on) with "
                      "DIFFERENT NUMBERS OF ENTGELTGRUPPEN and different money in them. "
                      "There is therefore no honest national group list to publish, and "
                      "the empty tuple above is the correct value rather than a gap "
                      "waiting to be filled. A German crosswalk has to be keyed on the "
                      "Tarifgebiet, which is a schema change: CrosswalkSpec currently "
                      "assumes one national table per system, and Germany is the "
                      "counter-example. Build the region key before building the data."),
)

PACK = CountryPack(
    country="DE",
    name="Germany",
    currency="EUR",
    languages=("de",),
    status=STUB,
    vocabulary=VOCABULARY,
    gender_codes=GENDER_CODES,
    pay_components=PAY_COMPONENTS,
    reporting=REPORTING,
    crosswalks=(ERA,),
    notes=(
        "STRUCTURAL: EntgTranspG thresholds count per Betrieb, not per company. The "
        "headcount-in, band-out API cannot express this and will mislead if handed a "
        "company total. Ask for establishment sizes, or say nothing.",
        "STRUCTURAL: gender has three values here. A binary field drops 'divers' rather "
        "than failing on it, which is the quiet kind of wrong.",
        "STRUCTURAL: BetrVG section 87(1) no. 10 gives the Betriebsrat co-determination "
        "over pay structuring. A German pay-structure recommendation is a proposal to a "
        "negotiation, not an instruction to an employer. Source: " + _BETRVG_URL,
        "STRUCTURAL: ERA is regional. One national group table would be a fiction, so the "
        "crosswalk holds no groups at all until CrosswalkSpec can key on a Tarifgebiet.",
        "STUB: the four structural findings above are the usable output of this pack "
        "today. The thresholds and cycles are research, not verified law.",
    ),
)

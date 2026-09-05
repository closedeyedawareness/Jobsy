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

Written from web research on 2026-09-05, then checked the same day against
gesetze-im-internet.de, which is the primary text. That check earned the WET
markers on sections 12, 21 and 22, and caught a real error on the way.

The reporting cycle had been written here as "every 3 years if bound by a
collective agreement, otherwise every 5", from secondary sources. Section 22
says the opposite: para 22(1) gives tarifgebunden and tarifanwendend employers
alle fuenf Jahre, and para 22(2) gives everybody else alle drei Jahre.
Tarifbindung earns the LONGER cycle. That claim was marked ONBEVESTIGD, which
is why it never reached a client, and it is the clearest argument this package
makes for itself: the marker did the work the prose could not.

DRAFT rather than LIVE, because LIVE means a person checked, and so far only an
agent has.
"""
from __future__ import annotations

from . import (CONVENTIE, Claim, CompensationModel, CountryPack,
               CrosswalkSpec, DRAFT, JobArchitecture, OCCUPATION,
               ONBEVESTIGD, OrgStructure, PayReporting, PerformanceModel,
               QUALIFICATION, ReportingBand, SkillsFramework, SpineMapping,
               UITLEG, WET)

_ENTGTRANSPG = "the Entgelttransparenzgesetz (EntgTranspG)"
_ENTGTRANSPG_URL = "https://www.gesetze-im-internet.de/entgtranspg/"
_BETRVG_URL = "https://www.gesetze-im-internet.de/betrvg/__87.html"
_PARA21_URL = "https://www.gesetze-im-internet.de/entgtranspg/__21.html"
_PARA22_URL = "https://www.gesetze-im-internet.de/entgtranspg/__22.html"
_ASOF = "2026-09-05"
_VERIFIED = "2026-09-05"   # read against gesetze-im-internet.de, the primary text
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
         "7 June 2026 deadline, that amending the EntgTranspG is the expected route, and "
         "that an Expertenkommission delivered its final report on 7 November 2025 with "
         "no Referentenentwurf public since. The lead ministry is the BMBFSFJ, not the "
         "BMAS. Re-check on gesetze-im-internet.de before stating a client position; the "
         "2017 Act applies regardless of the directive status.")

REPORTING = PayReporting(
    transposed=_TRANSPOSED,
    national_law=Claim(_ENTGTRANSPG, WET, _ENTGTRANSPG_URL, _ASOF,
                       note="In force since 6 July 2017. Germany legislated on pay "
                            "transparency long before the directive, and this is the live "
                            "duty; its thresholds are nothing like the EU's."),
    pre_existing_duty=Claim(
        True, WET, _ENTGTRANSPG_URL, _ASOF,
        note="The Act creates several separate duties, not one duty with size bands. "
             "Section 12 gives the individual RIGHT TO INFORMATION (Auskunftsanspruch) "
             "in Betrieben mit in der Regel mehr als 200 Beschaeftigten bei demselben "
             "Arbeitgeber. Section 21 attaches the mandatory REPORT (Bericht zur "
             "Gleichstellung und Entgeltgleichheit) to employers with more than 500 "
             "employees who are ALSO required to produce a Lagebericht under HGB "
             "sections 264 and 289 - both conditions, not either. The bands below "
             "describe the report only. Do not present the 200 threshold as a reporting "
             "threshold: they are different obligations with different consequences."),
    joint_assessment_trigger_pct=None,   # no percentage trigger in the 2017 Act
    bands=(
        ReportingBand(
            min_employees=501, max_employees=None,
            first_report=Claim("in force since 2017", WET, _PARA21_URL, _VERIFIED,
                               note="Section 21: more than 500 employees AND subject to "
                                    "the HGB Lagebericht duty. Counted per Betrieb, which "
                                    "the headcount argument cannot express."),
            frequency=Claim("every 5 years if tarifgebunden or tarifanwendend, "
                            "otherwise every 3 years", WET, _PARA22_URL, _VERIFIED,
                            note="EntgTranspG section 22. Tarifbindung earns the LONGER "
                                 "cycle, not the shorter one: para 22(1) gives employers "
                                 "who are tarifgebunden under section 5(4) or "
                                 "tarifanwendend under section 5(5) alle fuenf Jahre, and "
                                 "para 22(2) gives all others alle drei Jahre. This file "
                                 "first stated it the other way round, from secondary "
                                 "sources; the ONBEVESTIGD marker it carried is what kept "
                                 "it away from a client. A wrong cycle means filing in "
                                 "the wrong year."),
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
    source=Claim("no single national ERA table exists", UITLEG, _RESEARCH, _VERIFIED,
                 note="ERA is not one agreement. There are currently FIFTEEN regional "
                      "Tarifgebiete, with DIFFERENT NUMBERS OF ENTGELTGRUPPEN and "
                      "different money in them: Baden-Wuerttemberg runs to EG 17, "
                      "Nordrhein-Westfalen to EG 14, others to EG 11 or 13. "
                      "There is therefore no honest national group list to publish, and "
                      "the empty tuple above is the correct value rather than a gap "
                      "waiting to be filled. A German crosswalk has to be keyed on the "
                      "Tarifgebiet, which is a schema change: CrosswalkSpec currently "
                      "assumes one national table per system, and Germany is the "
                      "counter-example. Build the region key before building the data."),
)

# ── capability slots ─────────────────────────────────────────────────────────

ORG_STRUCTURE = OrgStructure(
    employer_unit=Claim(
        "Betrieb", WET, _ENTGTRANSPG_URL, _VERIFIED,
        note="THE finding of this pack. Section 12 counts in Betrieben mit in der Regel "
             "mehr als 200 Beschaeftigten — establishments, not legal entities. A company "
             "of 900 across four sites may have no Betrieb over 200 and therefore no "
             "information right anywhere in it, while a 600-person single-site employer "
             "has both duties. Every headcount threshold in a German analysis has to ask "
             "which Betrieb, and the org chart is where that question is answered."),
    employee_representation=Claim(
        "Betriebsrat", WET, _BETRVG_URL, _VERIFIED,
        note="Constituted per Betrieb, which is why the org chart and the threshold "
             "question are the same question here."),
)

PERFORMANCE = PerformanceModel(
    codetermination=Claim(
        True, WET, _BETRVG_URL, _VERIFIED,
        note="BetrVG section 87(1) no. 10 gives the Betriebsrat co-determination over "
             "betriebliche Lohngestaltung — the setting of pay principles and the "
             "introduction, application and change of pay methods. A 9-box that feeds pay "
             "progression is therefore not a neutral HR instrument in Germany; it is part "
             "of a system the works council must agree to. Implemented without that "
             "agreement it is not merely bad practice, it is unenforceable."),
    constraints=(
        Claim("technische Einrichtungen", ONBEVESTIGD, "", _VERIFIED,
              note="Section 87(1) no. 6 is widely understood to give the Betriebsrat "
                   "co-determination over technical systems capable of monitoring "
                   "employee performance or behaviour, which in practice is the hook that "
                   "catches HR software itself rather than only the policy it implements. "
                   "NOT verified in this round, unlike no. 10. Read the provision before "
                   "telling a client their Jobsy rollout needs a Betriebsvereinbarung — "
                   "and note that if it is right, it applies to the tool and not just to "
                   "the talent grid inside it."),
        Claim("section 87(1) no. 11", ONBEVESTIGD, "", _VERIFIED,
              note="Believed to cover performance-related pay rates (Akkord- und "
                   "Praemiensaetze and comparable performance-based pay). Unverified."),
    ),
)

JOB_ARCHITECTURE = JobArchitecture(
    level_concept=Claim(
        "Entgeltgruppe", CONVENTIE, _RESEARCH, _VERIFIED,
        note="Set per Tarifvertrag and per Tarifgebiet, so an Entgeltgruppe 11 in "
             "Baden-Wuerttemberg and in Nordrhein-Westfalen are not the same thing. "
             "There is no national German grade."),
    mappings=(
        SpineMapping(
            dimension=OCCUPATION, local_scheme="KldB 2010", spine="ISCO-08",
            source=Claim("Klassifikation der Berufe 2010 carries an ISCO-08 "
                         "correspondence", ONBEVESTIGD, "", _VERIFIED,
                         note="The federal employment agency's KldB 2010 is understood to "
                              "publish an official crosswalk to ISCO-08. Confirm at the "
                              "Bundesagentur fuer Arbeit before routing through it."),
        ),
    ),
)

PACK = CountryPack(
    country="DE",
    name="Germany",
    currency="EUR",
    languages=("de",),
    status=DRAFT,
    vocabulary=VOCABULARY,
    gender_codes=GENDER_CODES,
    pay_components=PAY_COMPONENTS,
    reporting=REPORTING,
    crosswalks=(ERA,),
    org_structure=ORG_STRUCTURE,
    performance=PERFORMANCE,
    job_architecture=JOB_ARCHITECTURE,
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
        "DRAFT since 2026-09-05: sections 12, 21 and 22 were read against "
        "gesetze-im-internet.de, so the thresholds and the reporting cycle now carry WET. "
        "Not LIVE, because that marker means a person checked the sources and so far only "
        "an agent has.",
    ),
)

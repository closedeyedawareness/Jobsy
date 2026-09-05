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
    note="AS AT 5 SEPTEMBER 2026 A SEARCH FOUND NO GERMAN IMPLEMENTING ACT for Directive "
         "(EU) 2023/970, and the 7 June 2026 deadline had passed. Note the shape of that "
         "sentence: it reports a search on a date, not a state of the world. Nobody can "
         "verify that a law does not exist, only that they looked and did not find one, "
         "so this claim carries a review interval instead of pretending to be settled. "
         "What the search did find: amending the EntgTranspG is the expected route, an "
         "Expertenkommission reported on 7 November 2025, and no Referentenentwurf has "
         "been public since. The lead ministry is the BMBFSFJ, not the BMAS. "
         "WHY IT MATTERS IF THIS GOES STALE: the German 2017 Act starts reporting above "
         "500 employees and the directive starts at 250. If Germany transposes and nobody "
         "re-checks, a 300-person employer is told they sit outside a duty that by then "
         "reaches them. The 2017 Act applies either way. "
         "STATUS: OPEN, deliberately. Elmar reviewed this on 2026-09-05 and confirmed the "
         "handling rather than the answer: with the transposition deadline three months "
         "past, do not assume the 2017 Act still stands alone — check whether an amending "
         "or replacing instrument has come into force. The six-month re-check is the "
         "right treatment for a claim this time-sensitive, so the claim stays ONBEVESTIGD "
         "on purpose. It is not waiting to be filled in; it is waiting to be looked at "
         "again, and the screen will say so when the interval lapses.",
    review_after_months=6)

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
        Claim("BetrVG §87(1) Nr. 6 — technische Einrichtungen", UITLEG, _BETRVG_URL,
              _VERIFIED,
              note="THIS ONE IS ABOUT JOBSY ITSELF, NOT ABOUT THE CLIENT'S PAY POLICY, "
                   "and it is the most commercially consequential line in any pack. "
                   "The provision gives the Betriebsrat co-determination over the "
                   "EINFUEHRUNG UND ANWENDUNG von technischen Einrichtungen, die dazu "
                   "bestimmt sind, das Verhalten oder die Leistung der Arbeitnehmer zu "
                   "ueberwachen — the introduction AND the use of technical devices "
                   "intended to monitor behaviour or performance. "
                   "GERMAN PRACTICE READS THAT BROADLY, and the breadth is the point. It "
                   "is not confined to classic surveillance. A system can fall under it "
                   "where it is OBJECTIVELY SUITABLE to collect, record, combine or "
                   "evaluate person-related data about behaviour or performance — so "
                   "INTENT DOES NOT SAVE YOU. Dashboards, individual performance scores, "
                   "rankings, productivity measures and certain HR and AI systems are all "
                   "potentially in scope. "
                   "So do NOT record this as 'relevant only if the system is meant to "
                   "monitor staff'. The safer statement, and the one this pack now makes: "
                   "co-determination is LIKELY TO APPLY wherever Jobsy can technically "
                   "process person-related data from which an employee's behaviour or "
                   "performance could be followed or assessed. Jobsy holds per-person pay, "
                   "grade and rating-adjacent data, so on that reading a German rollout at "
                   "an employer with a works council is a matter for a "
                   "Betriebsvereinbarung, not an IT decision. That is a fact about SELLING "
                   "AND DEPLOYING the product, not about advising on someone's pay. "
                   "Source: Elmar van Dijk, domain knowledge, 2026-09-05, against the text "
                   "of the provision. Marked UITLEG rather than WET because the breadth of "
                   "application is settled case law and practice rather than something the "
                   "sentence itself says — which is exactly the kind of thing a German "
                   "employment lawyer should confirm before it is put to a client."),
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
    # Superseded: the crosswalk was confirmed at the Bundesagentur and the
    # sourced mapping now lives on the skills slot, with the licence position
    # recorded alongside it.
    mappings=(),
)

# ── skills ───────────────────────────────────────────────────────────────────

_DQR = "https://www.dqr.de/dqr/de/der-dqr/der-dqr_node.html"
_DQR_LISTE = ("https://www.dqr.de/dqr/shareddocs/downloads/media/content/"
              "2025_dqr_liste_zugeordnete_qualifik_01082025.pdf")
_KLDB_ISCO = ("https://statistik.arbeitsagentur.de/DE/Navigation/Grundlagen/Klassifikationen/"
              "Klassifikation-der-Berufe/KldB2010-Fassung2020/Arbeitsmittel/Arbeitsmittel-Nav.html")
_SGB4_28A = "https://www.gesetze-im-internet.de/sgb_4/__28a.html"
_TVL = ("https://www.tdl-online.de/fileadmin/downloads/TV-L/"
        "260812_TV-L__i.d.F._des_%C3%84TV_Nr._14_VT.pdf")

SKILLS = SkillsFramework(
    qualification_framework=Claim(
        ("DQR", 8, "referenced 2013"), UITLEG, _DQR, _VERIFIED,
        note="Eight levels, referenced to the EQF in a report dated 8 May 2013. Marked "
             "UITLEG rather than WET DELIBERATELY: the DQR is a joint declaration by the "
             "BMBF, BMWi and the two Länder conferences, NOT a statute. Its own pages say "
             "it has orientierenden Charakter and keine regulierende Funktion, and that "
             "the system of access rights does not change because of it. A DQR level "
             "confers no entitlement. Only the official assignment list is authoritative "
             "— the governing body explicitly disclaims placements found elsewhere, so a "
             "vendor's 'DQR level' tag is not evidence of anything."),
    occupation_taxonomy=Claim(
        ("KldB 2010", "überarbeitete Fassung 2020"), WET,
        "https://statistik.arbeitsagentur.de/DE/Navigation/Grundlagen/Klassifikationen/"
        "Klassifikation-der-Berufe/KldB2010-Fassung2020/KldB2010-Fassung2020-Nav.html",
        _VERIFIED,
        note="Valid from reporting year 2021 and still maintained — the occupation index "
             "carries a Stand of 1 January 2026. More useful than the classification "
             "itself: SGB IV section 28a requires every employer to report an occupation "
             "key from the BA's Schlüsselverzeichnis in the social-insurance Meldung, so "
             "EVERY GERMAN EMPLOYER ALREADY HOLDS A CODED OCCUPATION PER EMPLOYEE BY LAW. "
             "That is the highest-coverage occupation field available in this market, and "
             "it beats asking a client for job titles. Note the digit layout of the "
             "nine-character Tätigkeitsschlüssel could NOT be sourced, so do not hard-code "
             "positions within it."),
    mappings=(
        SpineMapping(
            dimension=OCCUPATION, local_scheme="KldB 2010 üF2020", spine="ISCO-08",
            source=Claim("Umsteigeschlüssel KldB 5-Steller to ISCO-08 4-Steller", WET,
                         _KLDB_ISCO, _VERIFIED,
                         note="An official crosswalk exists and was downloaded and parsed. "
                              "TWO THINGS BEFORE ANYONE BUILDS ON IT. First, the BA says "
                              "plainly that Umsteigeschlüssel sind oftmals nicht "
                              "eindeutig, and the data bears it out — KldB 11101 maps to "
                              "ISCO 9211 AND 9213. It is one-to-many, so it is a "
                              "distribution and not a lookup. Second, the file's own "
                              "terms require the BA's permission for gewerbliche Zwecke — "
                              "BUT NOTE WHAT THAT DOES AND DOES NOT REACH. It restricts "
                              "redistributing THEIR FILE. This pack does not hold it: the "
                              "mapping below records that the correspondence exists and "
                              "cites where the official one is published, and its table is "
                              "empty on purpose. So the permission question is not 'may we "
                              "sell the product' but the far narrower 'may we ship this "
                              "particular table', and it only arises if someone decides to "
                              "ship it. The cost of staying on the reference side is that "
                              "a reference does not convert — see the SpineMapping "
                              "docstring for the routes that make the hop without "
                              "redistributing anything."),
        ),
    ),
)

# ── compensation ─────────────────────────────────────────────────────────────

COMPENSATION = CompensationModel(
    structure=Claim(
        ("MiLoG", "Tarifvertrag", "Betriebsvereinbarung", "Arbeitsvertrag"), WET,
        "https://www.gesetze-im-internet.de/tvg/__3.html", _VERIFIED,
        note="TVG section 3(1) binds the members of the contracting parties and any "
             "employer that is itself a party. Above the statutory minimum wage, "
             "everything else is a Tarifvertrag at sector or company level, then works "
             "agreement, then contract."),
    bargaining_coverage=Claim(
        0.49, WET,
        "https://www.destatis.de/DE/Themen/Arbeit/Verdienste/Tarifverdienste-Tarifbindung/"
        "_inhalt.html", _VERIFIED,
        note="49% of employees in 2025, unchanged from 2024, split 41% sector agreement "
             "and 8% company agreement. The IAB series shows how far it has fallen: "
             "sectoral coverage went from 69% to 43% in the West and 56% to 34% in the "
             "East over 29 years. THE PRODUCT CONSEQUENCE IS LARGE — for about half of "
             "German employees there is no collective pay scale at all, so 'no "
             "Tarifvertrag' is the MODAL case here, not the exception, and it "
             "concentrates in the East and in small firms. A model that assumes a scale "
             "exists is a Dutch model."),
    extension_mechanism=Claim(
        "Allgemeinverbindlicherklärung (rare)", WET,
        "https://www.bmas.de/SharedDocs/Downloads/DE/Arbeitsrecht/ave-verzeichnis.pdf",
        _VERIFIED,
        note="Germany has an extension mechanism and barely uses it: 225 declarations in "
             "force on 1 January 2026, across narrow named sectors — construction, "
             "building cleaning, chimney sweeps, security, hospitality, hairdressing, "
             "care. Compare the Netherlands, where extension is the ordinary route by "
             "which a sector agreement reaches non-members. So 'there is a sector "
             "agreement, therefore it applies to the sector' is a Dutch assumption and is "
             "wrong in Germany about half the time."),
    seniority_progression=Claim(
        "Stufenlaufzeit, 15 years to the top", WET, _TVL, _VERIFIED,
        note="TV-L section 16(3): six Stufen, reached after 1, then 2, then 3, then 4, "
             "then 5 years of uninterrupted service in the same Entgeltgruppe with the "
             "same employer — fifteen years cumulatively. Performance can shorten or "
             "lengthen only the steps to 4, 5 and 6; the first two are pure time. "
             "See the constraints below for what does and does not stop the clock, which "
             "is the part that matters. NOTE THE SCOPE: this is TV-L, read in full. TVöD "
             "could not be obtained — the ministry refused every fetch — so do not quote "
             "TVöD numbers to a client on the strength of this."),
    market_data=(
        Claim("Destatis Verdiensterhebung", WET,
              "https://www.destatis.de/DE/Themen/Arbeit/Verdienste/"
              "Verdienste-Branche-Berufe/_inhalt.html", _VERIFIED,
              note="Annual since 2022, April reference month, individual-level, with gross "
                   "monthly earnings published by occupation. The statutory variable list "
                   "in VerdStatG section 4 is worth knowing because it names the fields a "
                   "German employer is already required to be able to produce: ausgeübte "
                   "Tätigkeit, höchster Bildungsabschluss, Geschlecht, Art des "
                   "Beschäftigungsverhältnisses, Zahl der bezahlten Arbeitsstunden, "
                   "Bruttomonatsverdienst."),
        Claim("FDZ microdata is genuinely accessible", WET,
              "https://www.forschungsdatenzentrum.de/de/sonstige-wirtschaftsstatistiken/vse",
              _VERIFIED,
              note="Unlike CBS in the Netherlands, the German research data centre offers "
                   "Scientific Use Files and on-site access for the Verdiensterhebung "
                   "2022-2025 and the four-yearly Verdienststrukturerhebung, and the "
                   "AFiD-Modul Verdienste can be linked to firm-level data. Access is "
                   "fee-based and application-gated. Occupation appears as the social "
                   "insurance Berufsschlüssel, though the FDZ metadata does not name KldB "
                   "explicitly."),
    ),
    constraints=(
        Claim("Elternzeit does not advance the Stufenlaufzeit", WET, _TVL, _VERIFIED,
              note="THE MOST IMPORTANT FINDING IN THIS PACK, and the clearest example "
                   "anywhere of the thing this product exists to see. TV-L section 17(3) "
                   "splits interruptions finely: MUTTERSCHUTZ COUNTS as service, and so "
                   "do paid leave and sickness up to 39 weeks. ELTERNZEIT DOES NOT. It is "
                   "unschädlich, meaning you do not lose the Stufe you reached, but "
                   "explicitly nicht auf die Stufenlaufzeit angerechnet — so a "
                   "three-year parental break delays every subsequent step by three "
                   "years. A break longer than three years moves the employee DOWN one "
                   "Stufe. Part-time, by contrast, is counted in full, deliberately. "
                   "So the gap this produces sits INSIDE a formally gender-neutral "
                   "scale: same Entgeltgruppe, different Stufe, entirely lawful on its "
                   "face, and invisible to any comparison made at grade level. Compare "
                   "within Entgeltgruppe AND Stufe, and treat Stufe as an OUTCOME "
                   "variable rather than a control — controlling for it would subtract "
                   "exactly the effect worth measuring."),
        Claim("Vorweggewährte Stufen", WET, _TVL, _VERIFIED,
              note="Section 16(5) lets the employer grant up to two Stufen above "
                   "entitlement to attract or retain qualified staff. A discretionary, "
                   "negotiable lever sitting on top of the scale — so expect Stufe not to "
                   "be fully explained by tenure, and expect the residual to be where the "
                   "interesting variance is."),
        Claim("the minimum wage is not in the Act", WET,
              "https://www.recht.bund.de/eli/bund/bgbl-1/2025/268", _VERIFIED,
              note="13,90 euro per hour from 1 January 2026 and 14,60 from 1 January "
                   "2027, set by the fifth Mindestlohnanpassungsverordnung. THE TRAP: "
                   "MiLoG section 1 still reads 12 euro, its 2022 base figure, because "
                   "the live value lives in successive regulations. Anyone scraping the "
                   "statute gets a number four years stale."),
        Claim("Entgeltumwandlung and the 15% subsidy", WET,
              "https://www.gesetze-im-internet.de/betravg/__1a.html", _VERIFIED,
              note="An employee is entitled to convert up to 4% of the contribution "
                   "ceiling into occupational pension, and the employer must add 15% of "
                   "the converted amount — BUT ONLY to the extent the employer actually "
                   "saves social-security contributions by the conversion. Above the "
                   "Beitragsbemessungsgrenze that saving can be nil and so can the "
                   "subsidy. Do not model it as a flat 15%: doing so overstates total "
                   "reward for exactly the highest earners."),
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
    skills=SKILLS,
    compensation=COMPENSATION,
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

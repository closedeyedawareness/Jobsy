"""
jobsy/services/country_packs/be.py — Belgium.

Belgium is the pack that shows the country dimension was necessary rather than
tidy, because almost nothing here is the Dutch answer in different words.
Three things in particular would produce a wrong number in a system that
quietly treated a Belgian client as Dutch:

  * The reporting duty starts at **50 employees**, not 100. It predates the
    directive by eleven years and is still the operative law, so a Belgian
    client with 80 people has a duty today while the EU baseline says they
    have none at all.

  * **Double holiday pay is 92% of one month's gross**, not 8% of the year.
    Those are close enough to look interchangeable and are not: the Belgian
    figure sits on a different base with its own exclusions, so a Dutch-shaped
    "times 1.08" on Belgian payroll is wrong twice over.

  * **Automatic indexation.** Belgian pay moves by mechanism, on a date, for
    everyone in the joint committee at once. A year-on-year pay comparison
    that does not know this reads an index jump as a pay decision.

── On the hardness markers in this file ─────────────────────────────────────

Assembled from web research on 2026-09-05 and checked the same day against
IGVM/IEFH, the FOD WASO model forms and the PC 200 sector fund. That check
confirmed the biennial cycle, the 50 and 100 thresholds and the two model
forms, and it corrected something this file had wrong: the 0-49 band said "below
the ondernemingsraad threshold", but that threshold is 100, not 50. The outcome
was right and the reason was not, which is its own kind of error — a reader who
trusts the reason will misapply it at 60 employees.

Two things stay unverified and say so: the exclusion list behind the 92% double
holiday pay, and the often-quoted "69 ORBA-evaluated reference functions" for
PC 200, which no primary source would confirm.

── The qualification join, closed on 2026-09-06 ─────────────────────────────

This file said for a day that the EQF level is the only reliable join key
between Flanders and Wallonia, and then held no qualification mapping to the
EQF at all — the tool could not do the thing its own note called the only way
to do it. Closing that meant opening both Belgian instruments and finding that
NEITHER STATES THE CORRESPONDENCE. The Flemish decreet of 30 April 2009 does
not mention the EQF anywhere; the francophone samenwerkingsakkoord of
26 February 2015 says only that the CFC is "compatible avec le Cadre européen
des Certifications". The level-by-level correspondence lives in the two EQF
referencing reports, which are official and endorsed and are not law — so the
mapping is a reference marked UITLEG with an empty table, not a WET table like
the Dutch or French ones. The full reasoning is on the mapping itself.

The same pass corrected this file: the German-speaking Community's QDG exists,
eight levels, decree of 18 November 2013. The earlier note called it
unconfirmed.

DRAFT rather than LIVE, because LIVE means a person checked, and so far only an
agent has.
"""
from __future__ import annotations

from . import (CONVENTIE, Claim, CompensationModel, CountryPack,
               CrosswalkSpec, DRAFT, LIVE, JobArchitecture, OCCUPATION,
               ONBEVESTIGD, OrgStructure, PayReporting, PerformanceModel,
               QUALIFICATION, ReportingBand, SkillsFramework, SpineMapping,
               UITLEG, WET)

_LOONKLOOFWET = ("Wet van 22 april 2012 ter bestrijding van de loonkloof tussen mannen "
                 "en vrouwen (Belgisch Staatsblad 28-08-2012)")
_LOONKLOOFWET_URL = "https://igvm-iefh.belgium.be/nl/themas/werk/loonkloof/wetgeving"
# The ELI permalink for the 2012 law does not resolve to the statute (it lands on
# the ELI help page, and the neighbouring numac reaches an unrelated 2012 traffic
# law), so a WET marker pointed at it would be unfalsifiable by the next reader.
# The Institute for the Equality of Women and Men is the official source for this
# law and its model forms, and it resolves.
_MODEL_FORM_URL = ("https://werk.belgie.be/sites/default/files/content/documents/"
                   "analysebezoldigingsstructuur_volledig.pdf")
_ASOF = "2026-09-05"
_VERIFIED = "2026-09-05"   # checked against IGVM/IEFH, FOD WASO and the sector fund
_RESEARCH = "web research 2026-09-05; NOT yet checked against the primary text"

# ── vocabulary ───────────────────────────────────────────────────────────────
#
# Belgium is trilingual and a payroll export follows the language of the
# establishment, not of the company. One Brussels client can hand over a single
# file with Dutch and French headers in it, which is why these lists are merged
# rather than split by language.
VOCABULARY: dict[str, tuple[str, ...]] = {
    "salary":   ("loon", "brutoloon", "bezoldiging", "wedde", "maandwedde", "barema",
                 "salaire", "salaire brut", "remuneration", "traitement",
                 "gehalt", "bruttolohn"),
    "gender":   ("geslacht", "sekse", "sexe", "genre", "geschlecht", "m/v", "h/f"),
    "function": ("functie", "functietitel", "fonction", "intitule de fonction",
                 "funktion", "referentiefunctie", "fonction de reference"),
    "level":    ("klasse", "functieklasse", "categorie", "classe", "classe de fonction",
                 "baremaklasse", "niveau", "paritair comite", "commission paritaire"),
    "fte":      ("vte", "voltijds equivalent", "deeltijds", "arbeidsregime",
                 "etp", "equivalent temps plein", "temps partiel",
                 "regime de travail", "tewerkstellingsbreuk"),
    "tenure":   ("ancienniteit", "anciennete", "datum indiensttreding",
                 "date d'entree en service", "in dienst"),
    "variable": ("premie", "bonus", "prime", "variabel", "variable",
                 "cao 90", "loonbonus", "bonus salarial"),
    "holiday":  ("vakantiegeld", "dubbel vakantiegeld", "pecule de vacances",
                 "double pecule"),
    "employee": ("werknemer", "medewerker", "travailleur", "employe",
                 "stamnummer", "personeelsnummer", "matricule"),
    "country":  ("land", "pays", "werkland"),
}

#: Belgian systems write gender in whichever language the file is in. `V` is
#: vrouw and `F` is femme; a parser that reads either as a male variant flips
#: the sign of the entire gap and reports the opposite of the truth.
GENDER_CODES: dict[str, tuple[str, ...]] = {
    "female": ("v", "vrouw", "f", "femme", "feminin", "w", "weiblich"),
    "male":   ("m", "man", "h", "homme", "masculin", "mannlich"),
}

# ── the reporting duty ───────────────────────────────────────────────────────

_TRANSPOSED = Claim(
    value=False, hardness=UITLEG, source=_LOONKLOOFWET_URL, as_of=_VERIFIED,
    note="Belgium had not transposed Directive (EU) 2023/970 at federal level by the "
         "7 June 2026 deadline. There is no federal draft law for the private sector, "
         "and Belgium asked the Commission for six months forbearance on infringement. "
         "Only regional decrees covering their own public sectors (Flemish, and "
         "Federation Wallonie-Bruxelles) are in force. None of this touches the 2012 "
         "law, which applies either way and is the duty a private-sector client has.",
    review_after_months=6)

REPORTING = PayReporting(
    transposed=_TRANSPOSED,
    national_law=Claim(_LOONKLOOFWET, WET, _LOONKLOOFWET_URL, _ASOF,
                       note="Belgium legislated on the pay gap in 2012 and did not wait "
                            "for Europe. This, not the directive, is the live duty."),
    pre_existing_duty=Claim(
        True, WET, _LOONKLOOFWET_URL, _ASOF,
        note="The 2012 law requires a BIENNIAL analyseverslag van de bezoldigingsstructuur "
             "/ rapport d'analyse sur la structure des remunerations, drawn up by the "
             "employer and submitted to the ondernemingsraad, or failing one to the "
             "vakbondsafvaardiging. It is not an EU obligation and does not go away if "
             "the directive is transposed late."),
    joint_assessment_trigger_pct=None,   # the 2012 law has no percentage trigger
    bands=(
        ReportingBand(
            min_employees=100, max_employees=None,
            first_report=Claim("in force since 2012", WET, _MODEL_FORM_URL, _VERIFIED,
                               note="Full (volledig) analyseverslag. Covers the two "
                                    "preceding boekjaren and is due within three months "
                                    "of the close of the financial year."),
            frequency=Claim("every 2 years", WET, _LOONKLOOFWET_URL, _VERIFIED),
        ),
        ReportingBand(
            min_employees=50, max_employees=99,
            first_report=Claim("in force since 2012", WET, _MODEL_FORM_URL, _VERIFIED,
                               note="Abbreviated (verkort / simplifie) form; a separate "
                                    "official model form exists for it. Lighter, but a "
                                    "real legal duty, and this is the band a Dutch-shaped "
                                    "rule would wrongly report as exempt."),
            frequency=Claim("every 2 years", WET, _LOONKLOOFWET_URL, _VERIFIED),
        ),
        ReportingBand(
            min_employees=0, max_employees=49,
            first_report=Claim(None, UITLEG, _MODEL_FORM_URL, _VERIFIED,
                               note="No analyseverslag below 50 employees. NOT because of "
                                    "the ondernemingsraad threshold, which is 100, not 50 "
                                    "— the 50-99 band has no works council and reports to "
                                    "the vakbondsafvaardiging instead. The outcome and "
                                    "the reason are separate facts and this file had the "
                                    "reason wrong."),
            frequency=Claim("none", UITLEG, _RESEARCH, _ASOF),
        ),
    ),
)

# ── pay components ───────────────────────────────────────────────────────────

PAY_COMPONENTS = (
    Claim(("double_holiday_pay", 0.92), UITLEG, "Securex / Acerta / Liantis payroll "
          "guidance, 2026-09-05; primary is KB 30 March 1967, not opened", _VERIFIED,
          note="92% of the gross MONTHLY salary of the month in which it is paid, "
               "including fixed premiums, pro-rated by months worked in the "
               "vakantiedienstjaar. BEDIENDEN ONLY: for arbeiders the RJV pays single and "
               "double together as a percentage of the reference-year gross, which is a "
               "different mechanism and not this number. Either way it is NOT the Dutch "
               "8% of annual pay, so a Belgian total-reward figure must never be computed "
               "with the Dutch formula. The rate is corroborated; the EXCLUSION LIST is "
               "still unverified, so check it before a client sees a total."),
    Claim(("thirteenth_month", None), CONVENTIE, "", _ASOF,
          note="Eindejaarspremie / prime de fin d'annee is set per joint committee, not by "
               "statute. Take it from the client's own PayMix rows, never assume it."),
    Claim(("indexation", None), UITLEG, _RESEARCH, _ASOF,
          note="Automatic wage indexation applies per joint committee on set dates. A "
               "year-on-year pay comparison that does not separate the index movement "
               "measures inflation and calls it a pay decision. A real analysis hazard "
               "for Belgium, with no Dutch equivalent."),
)

# ── crosswalk ────────────────────────────────────────────────────────────────

PC200 = CrosswalkSpec(
    system="PC 200 / CP 200 (Aanvullend Paritair Comite voor de Bedienden)",
    publishes_point_table=False,
    groups=("A", "B", "C", "D"),
    point_bands=(),      # deliberately empty; see the source note
    sectors=("Aanvullend Paritair Comite voor de Bedienden",),
    source=Claim("four function classes A-D", UITLEG,
                 "https://www.sfonds200.be/sociaal-fonds/sectorinformatie/beroepsindeling",
                 _VERIFIED,
                 note="The sector fund publishes the four-class structure: A executing, "
                      "B supporting, C managing, D advisory. The often-quoted figure of "
                      "69 reference functions and the attribution to ORBA appear "
                      "consistently in secondary sources but could NOT be confirmed "
                      "against the PC 200 convention itself, so they are not stated here "
                      "as fact. No point-boundary table is published anywhere that could "
                      "be found, so class alignment is the only honest output — the same "
                      "boundary as CATS in the Dutch pack. Read the barema scales from "
                      "the current convention before showing them: PC 200 is the largest "
                      "joint committee in the country, so a wrong class here is wrong for "
                      "a very large number of people at once."),
)

# ── capability slots ─────────────────────────────────────────────────────────

ORG_STRUCTURE = OrgStructure(
    employer_unit=Claim(
        "onderneming / technische bedrijfseenheid", UITLEG, _RESEARCH, _VERIFIED,
        note="The ondernemingsraad threshold is 100, not 50 — and there is a "
             "SECOND-ORDER RULE that a simple flag at 100 still gets wrong. The OR is "
             "CREATED at 100 but RENEWED at 50, so a firm of 50 to 99 has one only if it "
             "already had one. The correct rule is 'OR at 100, or 50 if one already "
             "exists'. The comité voor preventie en bescherming op het werk sits at 50 "
             "for both creation and renewal and is what the 50-99 band has instead; where "
             "there is no comité either, the duties cascade to the vakbondsafvaardiging, "
             "which has NO statutory headcount at all — its threshold is set per joint "
             "committee, so do not model a single national number. The unit is understood "
             "to be the technische bedrijfseenheid, a Belgian construct that can be "
             "narrower or wider than the legal entity; that part is still unverified."),
    employee_representation=Claim(
        "ondernemingsraad, of vakbondsafvaardiging", WET, _MODEL_FORM_URL, _VERIFIED,
        note="TWO different recipients depending on size, and two different official "
             "report forms to match. The org chart decides which."),
)

JOB_ARCHITECTURE = JobArchitecture(
    level_concept=Claim(
        "functieklasse per paritair comite", UITLEG, _RESEARCH, _VERIFIED,
        note="PC 200 alone uses four classes A-D for the largest employee population in "
             "the country. The joint committee, not the employer, is the unit that sets "
             "pay, and ONE CLIENT CAN SIT IN SEVERAL AT ONCE — so a Belgian org chart "
             "must carry the paritair comite per population, not once per company."),
    # No occupation mapping here: the sourced one lives on the skills slot.
    # What stood here was an early guess that Belgium used ISCO-08 directly. The
    # guess was right and is now confirmed at Statbel — but leaving both meant
    # the route ran through the guess and reported ONBEVESTIGD for a fact that
    # had been verified.
    mappings=(),
)

# ── skills ───────────────────────────────────────────────────────────────────

_VKS = "https://data-onderwijs.vlaanderen.be/edulex/document.aspx?docid=14111"
_CFC = "https://cfc.cfwb.be/fr/"
#: The two EQF referencing reports, both read in full on 2026-09-06. These are
#: the documents that actually state the level-by-level correspondence — NOT the
#: decreet and NOT the samenwerkingsakkoord, both of which were opened and
#: neither of which says it. See the mapping note.
_VKS_REFREPORT = ("https://europass.europa.eu/system/files/2024-01/"
                  "REFERENCING%20REPORT%20BENL%20-%20UPDATE%202023.pdf")
_CFC_REFREPORT = ("https://europass.europa.eu/system/files/2022-05/"
                  "French-Speaking_Community_of_Belgium_Referencing_Report%5B1%5D.pdf")
#: The samenwerkingsakkoord of 26 February 2015 itself, as published by the
#: Communauté française. Read on 2026-09-06.
_CFC_AKKOORD = "https://www.gallilex.cfwb.be/document/pdf/41289_000.pdf"
_CFC_CADRE_LEGAL = "https://cfc.cfwb.be/fr/ressources/cadre-legal/"
_REFCHECK = "2026-09-06"
_STATBEL_ISCO = ("https://statbel.fgov.be/nl/over-statbel/methodologie/classificaties/"
                 "internationale-standaard-beroepen-classificatie-isco-08")
_INDEX = "https://werk.belgie.be/nl/themas/verloning/automatische-loonindexering"
_LOONNORM = "https://werk.belgie.be/nl/themas/verloning/loonnorm"
_PC200_LOON = "https://www.sfonds200.be/nl/sectorinformatie/verloning/"
_OR = "https://werk.belgie.be"

SKILLS = SkillsFramework(
    qualification_framework=Claim(
        ("VKS", "CFC", 8), WET, _VKS, _VERIFIED,
        note="THERE IS NO SINGLE BELGIAN QUALIFICATION FRAMEWORK, and that is the finding. "
             "Labour law is federal but qualifications are a Community competence, so "
             "Flanders has the Vlaamse Kwalificatiestructuur under the decree of 30 April "
             "2009 and the Fédération Wallonie-Bruxelles has the Cadre francophone des "
             "certifications under a cooperation accord of 26 February 2015. A Belgian "
             "employer with sites in Flanders and Wallonia genuinely faces TWO "
             "qualification systems. Both run 1 to 8 and both are EQF-referenced, so THE "
             "EQF LEVEL IS THE ONLY RELIABLE JOIN KEY BETWEEN THE TWO REGIONS — which is "
             "the spine earning its keep inside a single country rather than between "
             "countries. No official VKS-to-CFC crosswalk could be found, and the join is "
             "now recorded as a mapping through the EQF rather than left as a sentence — "
             "see mappings below for what each framework's referencing report actually "
             "says and why it is UITLEG. "
             "THERE ARE THREE FRAMEWORKS, NOT TWO. This note previously said a "
             "German-speaking Community framework could not be confirmed either way. The "
             "francophone referencing report confirms it on 2026-09-06: the QDG has eight "
             "levels with its own descriptors, and its establishing decree was adopted by "
             "the Parliament of the German-speaking Community on 18 November 2013. Small "
             "community, real framework — and the pack's mapping does NOT cover it."),
    occupation_taxonomy=Claim(
        ("ISCO-08", "no national adaptation"), WET, _STATBEL_ISCO, _VERIFIED,
        note="Belgium uses ISCO-08 DIRECTLY for occupation — 435 four-digit codes, in use "
             "since 1 January 2011, downloadable as XLS and CSV. There is no Belgian "
             "adaptation, which makes this the only market in the set where the national "
             "taxonomy IS the spine and the hop is an identity. Worth contrasting: "
             "Belgium does maintain a national adaptation for industry, NACE-BEL, so the "
             "absence for occupation is a choice rather than an oversight. Practical "
             "note, the English Statbel classifications page omits ISCO — use the Dutch "
             "one."),
    mappings=(
        SpineMapping(
            dimension=OCCUPATION, local_scheme="ISCO-08 (used directly)", spine="ISCO-08",
            source=Claim("Statbel codes occupations in ISCO-08 with no intermediate "
                         "national classification", WET, _STATBEL_ISCO, _VERIFIED,
                         note="An identity hop. The earlier guess in this pack said "
                              "Belgium probably used ISCO-08 directly and marked it "
                              "ONBEVESTIGD; that guess was right and is now sourced."),
        ),
        SpineMapping(
            dimension=QUALIFICATION,
            local_scheme="VKS (Vlaanderen) and CFC (Fédération Wallonie-Bruxelles)",
            spine="EQF",
            # EMPTY ON PURPOSE, and for a different reason than the occupation
            # crosswalks. Those are withheld because somebody else's file may not
            # be redistributed. This one is withheld because NO STATUTE STATES IT.
            # Both Belgian instruments were opened on 2026-09-06 and neither
            # carries the correspondence:
            #
            #   * the decreet van 30 april 2009 betreffende de kwalificatiestructuur
            #     does not contain the string "Europ" at all. Art. 3 defines the
            #     kwalificatiestructuur, art. 5 gives eight niveaus and art. 6
            #     describes them — with no reference to the EQF anywhere.
            #   * the samenwerkingsakkoord of 26 February 2015 mentions the CEC
            #     twice and says only that the CFC is "un cadre à huit niveaux ...
            #     compatible avec le Cadre européen des Certifications". Compatible
            #     is not level-by-level. Its recitals point outward, to the
            #     referencing report.
            #
            # The rule this package holds itself to is that a qualification TABLE
            # may be carried only where a statute sets the correspondence out
            # level by level, as the Dutch Besluit NLQF and the French décret do.
            # Belgium does not, so Belgium gets a reference and not a table, and
            # the hardness says UITLEG rather than WET. That distinction is the
            # whole point: a client who needs the conversion must read the
            # referencing report, not this file.
            mapping={},
            source=Claim(
                "VKS 1-8 and CFC 1-8 each reference one-to-one to EQF 1-8",
                UITLEG, _VKS_REFREPORT, _REFCHECK,
                note="THE JOIN THIS PACK ALREADY SAID WAS THE ONLY ONE, now recorded. "
                     "Qualifications are a Community competence, so a Belgian employer "
                     "with sites in Flanders and Wallonia faces TWO frameworks and the EQF "
                     "level is the only reliable key between them — and until now the pack "
                     "held no way to reach the EQF at all. "
                     "WHAT WAS READ. Flanders: the FQF-EQF referencing report, update 2023, "
                     "Table 5 'Alignment of FQF and EQF levels', which sets out level 1 to "
                     "level 1 through level 8 to level 8 and states that the alignment "
                     "'as defined in the Flemish referencing report in 2011 and confirmed "
                     "in its update in 2014, holds up until today'. Francophone: the "
                     "French-Speaking Community of Belgium Referencing Report, criterion 2, "
                     "which states that 'the eight levels of the VKS refer directly to the "
                     "eight levels of the EQF. This is also the case for the CFC', and "
                     "prints CFC, CEC, VKS and QDG side by side at 8 down to 1. The "
                     "samenwerkingsakkoord records that the EQF Advisory Group approved the "
                     "francophone report on 16 December 2013; the CFC's own cadre-legal page "
                     "dates the report 22 November 2011. Those two dates are report and "
                     "approval, not a contradiction, but neither was cross-checked against "
                     "the EQF-AG minutes. "
                     "WHY UITLEG AND NOT WET. Both correspondences live in referencing "
                     "reports, which are official documents endorsed at EU level but are "
                     "not law. The decreet and the samenwerkingsakkoord were both opened "
                     "and neither states a level-by-level correspondence — see the comment "
                     "above for exactly what each does say. Do not upgrade this to WET "
                     "without a Belgian instrument that sets the levels out. "
                     "BEST FIT, NOT EQUALITY. The Flemish report applies the EQF's own "
                     "'best fit' principle and says in terms that 'a perfect fit between "
                     "two sets of qualification levels is probably not possible and some "
                     "judgement or approximation is necessary'. So a Belgian level 6 and a "
                     "Dutch level 6 meeting at EQF 6 are comparable, not equal, and the "
                     "hop must never be presented as a conversion of one person's "
                     "qualification into another country's. "
                     "THE THIRD FRAMEWORK IS REAL. This pack previously said a "
                     "German-speaking Community framework could not be confirmed either "
                     "way. The francophone report confirms it: the QDG has eight levels "
                     "with its own descriptors and its establishing decree was adopted by "
                     "the Parliament of the German-speaking Community on 18 November 2013. "
                     "It is NOT covered by this mapping — whether the QDG has itself been "
                     "formally referenced to the EQF was not verified, so a Belgian client "
                     "with an Eupen site is outside what this hop can answer."),
        ),
    ),
)

# ── compensation ─────────────────────────────────────────────────────────────

COMPENSATION = CompensationModel(
    structure=Claim(
        ("NAR/CNT interprofessional", "paritair comité", "company"), WET,
        "https://werk.belgie.be/nl/themas/paritaire-comites-en-collectieve-"
        "arbeidsovereenkomsten-caos/collectieve", _VERIFIED,
        note="Three layers, and a company CAO binds ALL the employer's staff regardless "
             "of union membership and regardless of whether the signatory organisation "
             "was in the majority. Every private employer sits in a joint committee, with "
             "PC 200 as the residual catch-all for white-collar staff."),
    bargaining_coverage=Claim(
        1.0, UITLEG, "OECD/AIAS ICTWSS via the OECD SDMX API", _VERIFIED,
        review_after_months=24,
        note="The OECD series returns 100% for Belgium for every year from 1995 to 2024 — "
             "effectively universal. The figure of about 96% that circulates could not be "
             "sourced anywhere, so it is not used here. For scale from the same pull: "
             "Germany 52, Netherlands 70,5, France 98, United States 11,6. Marked UITLEG "
             "rather than WET because the measure code behind the series could not be "
             "verified. "
             "IT ALSO ANCHORS A COMPARISON, which is why it now carries a review "
             "interval where no other coverage figure does. Belgium sits at the top of "
             "the cross-market ranking the benefits screen renders, so every other "
             "market's position is read against a number that is an OECD estimate rather "
             "than a Belgian measurement. A flat 100 for thirty consecutive years is a "
             "series that has stopped moving, not a country that has stopped changing — "
             "the same shape as the French 98 sitting two lines above it. Two years is "
             "long enough not to nag and short enough that nobody inherits it "
             "unexamined."),
    extension_mechanism=Claim(
        "koninklijk besluit (algemeen verbindend verklaring)", WET,
        "https://werk.belgie.be/nl/themas/paritaire-comites-en-collectieve-"
        "arbeidsovereenkomsten-caos/collectieve", _VERIFIED,
        note="A CAO declared generally binding is published in full in the Belgisch "
             "Staatsblad as an annex to a royal decree, binds all employers in scope "
             "fifteen days later, removes the possibility of individual deviation unless "
             "the CAO itself allows it, and NON-COMPLIANCE IS CRIMINALLY SANCTIONABLE. "
             "That last point is the difference from the Dutch AVV, where the sanction is "
             "nullity of the deviating term rather than a criminal offence."),
    seniority_progression=Claim(
        "baremieke verhogingen, experience-based", WET, _PC200_LOON, _VERIFIED,
        note="PC 200 pays on job class times YEARS OF EXPERIENCE, with schaal I in the "
             "first year of service and schaal II from one year after hiring, so the step "
             "is automatic on the service anniversary. The age-based youth scale was "
             "ABOLISHED with effect from 1 January 2024, which is a real, dated move from "
             "age to experience. Two things are NOT established and should not be "
             "asserted: the year CP 218 made the same switch, and any prevalence figure "
             "for automatic progression across Belgian sectors. Strong indirect evidence "
             "that it is general: the wage-norm law carves out baremieke verhogingen "
             "separately, which it would not need to do if they were rare."),
    market_data=(
        Claim("two official pay gaps, a factor of 28 apart, both correct", WET,
              "https://statbel.fgov.be/nl/themas/werk-opleiding/lonen-en-arbeidskosten/"
              "loonkloof", _VERIFIED,
              note="THE METHODOLOGY TRAP, and it is the sharpest in any pack. Statbel "
                   "publishes the Eurostat-harmonised HOURLY gap for 2023 at 0,7%, second "
                   "lowest in the EU. IGVM/IEFH publishes the GROSS ANNUAL gap for 2022 "
                   "at 19,9% raw, or 7,0% corrected for working time, and 41,9% raw for "
                   "blue-collar workers in the private sector. These are not "
                   "contradictory — hourly against annual, time-corrected against raw — "
                   "and both are official. A product quoting 0,7% and one quoting 19,9% "
                   "are describing the same country. Never mix them in one narrative, and "
                   "never show either without its basis."),
        Claim("Statbel Structure of Earnings Survey", UITLEG,
              "https://statbel.fgov.be/nl/themas/werk-opleiding/lonen-en-arbeidskosten",
              _VERIFIED,
              note="Annual since 1999, latest published reference year 2022, downloadable "
                   "1999 to 2022, broken down by sex, occupational category, seniority, "
                   "sector, education level, age and region. Note the caveat: the "
                   "published crosstable uses Statbel's own beroepscategorie rather than "
                   "explicit ISCO codes, so pay by true ISCO code and sex is not "
                   "available as a ready-made table."),
    ),
    constraints=(
        Claim("indexation is CAO-based, NOT statutory", WET, _INDEX, _VERIFIED,
              note="A CORRECTION TO A COMMON BELIEF, and the ministry says it plainly: "
                   "er bestaat geen algemene Belgische wet die bepaalt dat alle lonen "
                   "automatisch geindexeerd moeten worden. Indexation is set in SECTORAL "
                   "collective agreements and is near-universal only because coverage is "
                   "near-universal. Two mechanism families exist: threshold-triggered, "
                   "where wages move when the smoothed health index crosses a pivot at "
                   "unpredictable times, and fixed-interval, most commonly annual. PC 200 "
                   "indexes every 1 January using the smoothed health index for November "
                   "and December against the same months a year earlier."),
        Claim(("pc200_indexation", {"2022": 3.58, "2023": 11.08, "2024": 1.48,
                                    "2025": 3.58, "2026": 2.21}), WET,
              _PC200_LOON, _VERIFIED,
              note="THE NUMBERS THAT MAKE THE HAZARD CONCRETE. On 1 January 2023 every PC "
                   "200 employee received 11,08% with zero managerial discretion. An "
                   "unadjusted year-on-year comparison will report inflation as a pay "
                   "decision, make 2023 look like an extraordinary reward year and 2024 "
                   "at 1,48% look like a freeze, and destroy comparability across joint "
                   "committees, because a January-indexing PC and a threshold PC that "
                   "crossed in October will show a spurious gap purely from timing. THE "
                   "DECOMPOSITION THIS COUNTRY MAKES POSSIBLE: indexation, then scale "
                   "progression, then the conventional sectoral increase, then the "
                   "residual. ONLY THE RESIDUAL IS A PAY DECISION. Belgium is the market "
                   "where those four are explicitly separable, which is an advantage if "
                   "modelled and a defect if not."),
        Claim("de loonnorm", WET, _LOONNORM, _VERIFIED,
              note="Under the law of 26 July 1996 as amended in 2017, the maximum "
                   "increase in labour cost per employee over a two-year period is "
                   "capped, and the cap binds at interprofessional, sectoral, company AND "
                   "INDIVIDUAL level — it constrains individual pay deals, not only "
                   "collective agreements. There is no Dutch or German equivalent. "
                   "THE CRITICAL POINT: indexation and baremieke verhogingen sit OUTSIDE "
                   "the cap by art. 6 para 4, so A ZERO LOONNORM DOES NOT MEAN ZERO PAY "
                   "GROWTH. The norm was 0% for 2023-2024 and 0% again for 2025-2026, "
                   "while PC 200 wages rose 11,08% and then 1,48%, entirely lawfully. "
                   "Sanctions run from 250 to 5.000 euro per employee concerned, capped "
                   "at a hundred; structurally more potent, a sectoral CAO that exceeds "
                   "the norm cannot be submitted for algemeen verbindend verklaring."),
        Claim("blue-collar contributions run on a 108% base", WET,
              "https://www.socialsecurity.be/employer/instructions/dmfa/nl/latest/"
              "instructions/socialsecuritycontributions/contributions/"
              "basiccontributions.html", _VERIFIED,
              note="Employer social contributions in 2026 are 24,92% basic, reduced to "
                   "19,88% for ordinary private employment, which is the operative rate. "
                   "The modelling detail that will bite: contributions for ARBEIDERS are "
                   "computed on the gross wage INCREASED BY 8%, while bedienden are "
                   "computed on 100%. Employer cost for the same gross wage therefore "
                   "differs by worker status, and status correlates with sex."),
        Claim("the Federal Learning Account is abolished", WET,
              "https://careerpro.be/nl/", _VERIFIED,
              note="LIVE RISK, worth checking against anything on the roadmap. The "
                   "repealing law was voted on 18 December 2025: since 1 January 2026 no "
                   "new training can be registered in the Federal Learning Account, "
                   "existing data can be consulted only until 31 December 2026, and is "
                   "deleted after that. Anything treating the FLA as a Belgian training "
                   "data source is building on something being switched off."),
        Claim("no qualification field exists in Belgian payroll declarations", WET,
              "https://www.socialsecurity.be/docu_xml/dmfa/DmfAOriginal_20263.html",
              _VERIFIED,
              note="A documented ABSENCE rather than a gap in the research. Neither DmfA "
                   "nor Dimona carries any qualification, education, diploma, competency, "
                   "certificate or training field; the worker blocks are occupation, "
                   "service, scale salary and remuneration. The largest payroll vendor's "
                   "public API publishes no training, education, skill, competence, "
                   "qualification or certificate resource either. SO ASSUME BELGIAN "
                   "QUALIFICATION DATA ARRIVES AS CUSTOMER-NAMED FREE FIELDS. There is no "
                   "canonical Belgian export column to target, and inventing a plausible "
                   "Dutch or French heading would be a fabrication."),
    ),
)


PACK = CountryPack(
    country="BE",
    name="Belgium",
    currency="EUR",
    languages=("nl", "fr", "de"),
    status=LIVE,
    countersigned_by="Elmar van Dijk",
    countersigned_on="2026-09-06",
    vocabulary=VOCABULARY,
    gender_codes=GENDER_CODES,
    pay_components=PAY_COMPONENTS,
    reporting=REPORTING,
    crosswalks=(PC200,),
    org_structure=ORG_STRUCTURE,
    job_architecture=JOB_ARCHITECTURE,
    skills=SKILLS,
    compensation=COMPENSATION,
    notes=(
        "DRAFT since 2026-09-05: the biennial cycle, the 50/100 thresholds, the two "
        "model forms and the ondernemingsraad route were confirmed against IGVM/IEFH and "
        "the FOD WASO forms. Not LIVE: the double holiday pay exclusion list is still "
        "unverified, and LIVE means a person checked rather than an agent.",
        "A Belgian export may mix Dutch and French column headers in one file, because "
        "language follows the establishment rather than the company.",
        "STRUCTURAL: qualifications are a Community competence, so this market has THREE "
        "frameworks — VKS in Flanders, CFC in the Fédération Wallonie-Bruxelles, QDG in "
        "the German-speaking Community. The pack's EQF mapping covers the first two and "
        "explicitly not the third, and it is a reference rather than a table because "
        "neither Belgian instrument states the correspondence level by level; the "
        "referencing reports do, and they are not law.",
        "The joint committee (paritair comite / commission paritaire) is the unit that "
        "sets pay, and one client can sit in several at once. Treat it as part of the "
        "client's structure, not as a single lookup key.",
    ),
)

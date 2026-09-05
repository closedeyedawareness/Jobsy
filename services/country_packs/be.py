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

DRAFT rather than LIVE, because LIVE means a person checked, and so far only an
agent has.
"""
from __future__ import annotations

from . import (CONVENTIE, DRAFT, ONBEVESTIGD, UITLEG, WET, Claim, CountryPack,
               CrosswalkSpec, PayReporting, ReportingBand)

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
         "law, which applies either way and is the duty a private-sector client has.")

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

PACK = CountryPack(
    country="BE",
    name="Belgium",
    currency="EUR",
    languages=("nl", "fr", "de"),
    status=DRAFT,
    vocabulary=VOCABULARY,
    gender_codes=GENDER_CODES,
    pay_components=PAY_COMPONENTS,
    reporting=REPORTING,
    crosswalks=(PC200,),
    notes=(
        "DRAFT since 2026-09-05: the biennial cycle, the 50/100 thresholds, the two "
        "model forms and the ondernemingsraad route were confirmed against IGVM/IEFH and "
        "the FOD WASO forms. Not LIVE: the double holiday pay exclusion list is still "
        "unverified, and LIVE means a person checked rather than an agent.",
        "A Belgian export may mix Dutch and French column headers in one file, because "
        "language follows the establishment rather than the company.",
        "The joint committee (paritair comite / commission paritaire) is the unit that "
        "sets pay, and one client can sit in several at once. Treat it as part of the "
        "client's structure, not as a single lookup key.",
    ),
)

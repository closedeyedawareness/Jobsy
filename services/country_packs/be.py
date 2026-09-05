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

Most claims here are UITLEG or ONBEVESTIGD, and that is not modesty. It is the
honest state of the evidence: this pack was assembled from web research on
2026-09-05, not from reading the Belgisch Staatsblad or the PC 200 convention.
The Dutch pack's crosswalk carries WET because somebody sat with the primary
FNV texts on 2026-07-21 and cited page numbers. Nobody has done that for
Belgium yet, and writing WET here would make the two look equally sound on a
screen where they are not. Each unverified claim carries the document to open.

STUB, therefore. The vocabulary and the structural warnings are usable today;
the numbers are not client-facing until somebody reads the source.
"""
from __future__ import annotations

from . import (CONVENTIE, ONBEVESTIGD, STUB, UITLEG, WET, Claim, CountryPack,
               CrosswalkSpec, PayReporting, ReportingBand)

_LOONKLOOFWET = ("Wet van 22 april 2012 ter bestrijding van de loonkloof tussen mannen "
                 "en vrouwen (Belgisch Staatsblad 28-08-2012)")
_LOONKLOOFWET_URL = "https://www.ejustice.just.fgov.be/eli/wet/2012/04/22/2012203263"
_ASOF = "2026-09-05"
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
    value=False, hardness=ONBEVESTIGD, as_of=_ASOF,
    note="Research indicates Belgium had not transposed Directive (EU) 2023/970 at "
         "federal level by the 7 June 2026 deadline, and that only regional decrees "
         "covering their own public sectors (Flemish, and Fedederation Wallonie-"
         "Bruxelles) were in force. Verify against the Kamer/Chambre dossier and the "
         "Staatsblad before telling a client they have no directive duty. Note that "
         "this changes nothing about the 2012 law, which applies either way.")

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
            first_report=Claim("in force since 2012", UITLEG, _RESEARCH, _ASOF,
                               note="Full analyseverslag, per financial year, biennial."),
            frequency=Claim("every 2 years", UITLEG, _RESEARCH, _ASOF),
        ),
        ReportingBand(
            min_employees=50, max_employees=99,
            first_report=Claim("in force since 2012", UITLEG, _RESEARCH, _ASOF,
                               note="Abbreviated (verkort / simplifie) form of the report. "
                                    "Lighter, but a real legal duty. This is the band a "
                                    "Dutch-shaped rule would wrongly report as exempt."),
            frequency=Claim("every 2 years", UITLEG, _RESEARCH, _ASOF),
        ),
        ReportingBand(
            min_employees=0, max_employees=49,
            first_report=Claim(None, UITLEG, _RESEARCH, _ASOF,
                               note="Below the ondernemingsraad threshold; no analyseverslag."),
            frequency=Claim("none", UITLEG, _RESEARCH, _ASOF),
        ),
    ),
)

# ── pay components ───────────────────────────────────────────────────────────

PAY_COMPONENTS = (
    Claim(("double_holiday_pay", 0.92), ONBEVESTIGD, "", _ASOF,
          note="Understood to be 92% of one month's gross for employees, on its own base "
               "and with its own exclusion list. This is NOT the Dutch 8% of annual pay. "
               "Do not compute a Belgian total-reward figure with the Dutch formula. "
               "Verify the rate and the exclusions against the RJV/ONVA rules and the "
               "applicable CAO before any client sees a number."),
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
    source=Claim("four function classes A-D over ORBA-evaluated reference functions",
                 ONBEVESTIGD, _RESEARCH, _ASOF,
                 note="Research reports roughly 69 reference functions classified into four "
                      "classes using ORBA. As with CATS in the Dutch pack, the scoring "
                      "method is proprietary and no public point-boundary table is "
                      "available, so class alignment is the only honest output. The class "
                      "list and the barema scales must be read from the current PC 200 "
                      "convention before this is shown to anyone: PC 200 is the largest "
                      "joint committee in the country, so a wrong class here is wrong for "
                      "a very large number of people at once."),
)

PACK = CountryPack(
    country="BE",
    name="Belgium",
    currency="EUR",
    languages=("nl", "fr", "de"),
    status=STUB,
    vocabulary=VOCABULARY,
    gender_codes=GENDER_CODES,
    pay_components=PAY_COMPONENTS,
    reporting=REPORTING,
    crosswalks=(PC200,),
    notes=(
        "STUB rather than DRAFT: the structure is right and the vocabulary is usable, but "
        "the legal and pay figures came from one round of web research on 2026-09-05 and "
        "no primary text has been read. Promote to DRAFT once the 2012 law's thresholds "
        "and the double holiday pay rate are confirmed at source.",
        "A Belgian export may mix Dutch and French column headers in one file, because "
        "language follows the establishment rather than the company.",
        "The joint committee (paritair comite / commission paritaire) is the unit that "
        "sets pay, and one client can sit in several at once. Treat it as part of the "
        "client's structure, not as a single lookup key.",
    ),
)

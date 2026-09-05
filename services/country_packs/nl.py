"""
jobsy/services/country_packs/nl.py — the Netherlands.

The first pack, and therefore the one that had to prove the schema fits real
knowledge rather than a shape invented for it. Everything here already existed
somewhere in the codebase; what is new is that it now carries its evidence and
sits in one place instead of five.

Where each part came from:

  * the ISF and CATS crosswalks: `services/cao_crosswalk_service.py`, verified
    2026-07-21 against the primary FNV CAO texts, with page citations in
    `docs/cao-metalektro-isf-reference.md`.
  * the reporting duty: the notes block in `services/pay_equity_service.py`,
    written May 2026.
  * the column vocabulary: the Dutch words that were inlined at `_smart_detect`
    call sites in `ui/app.py`, `ui/views/pay_equity.py`, `ui/views/connect.py`,
    `services/architecture_report_service.py` and `services/afas_connector.py`.

Two things the move surfaced, which is the point of the exercise.

The transposition status had been stated to every client since May and nobody
had re-checked it in four months. Checked on 2026-09-05: bill 36 949 is still
before the Tweede Kamer, so the substance held — but the "1 January 2027" that
came with it is a ministerial target, not the bill's commencement clause, which
leaves the date to koninklijk besluit. Stating it as a commencement date was
always more certainty than the source supports.

And the ISF and CATS crosswalks were marked WET. They are not. A CAO is a
collective agreement, which this package calls CONVENTIE, and the CATS entry is
a label alignment somebody reasoned out, which is UITLEG. The sourcing behind
them is the most careful in the package and that is exactly what made the
over-marking easy: careful is not the same as hard law.

DRAFT rather than LIVE, because LIVE means a person checked, and so far only an
agent has.
"""
from __future__ import annotations

from . import (CONVENTIE, Claim, CompensationModel, CountryPack,
               CrosswalkSpec, DRAFT, JobArchitecture, OCCUPATION,
               ONBEVESTIGD, OrgStructure, PayReporting, PerformanceModel,
               QUALIFICATION, ReportingBand, SkillsFramework, SpineMapping,
               UITLEG, WET)

_EU_DIRECTIVE = "https://eur-lex.europa.eu/eli/dir/2023/970/oj"
_ISF_DOC = "docs/cao-metalektro-isf-reference.md (page citations to the primary FNV CAO texts)"

# ── how a Dutch payroll export actually names things ─────────────────────────
#
# Not a translation table. These are the column headings that turn up in real
# exports from Dutch payroll systems, which is why "bruto", "vast" and
# "werkland" are here next to the tidy ones. Detection reads content as well as
# names, so a wrong guess here costs a prompt, not a wrong number.
VOCABULARY: dict[str, tuple[str, ...]] = {
    "salary":     ("salaris", "brutosalaris", "bruto", "jaarsalaris", "maandsalaris",
                   "loon", "brutoloon", "bezoldiging", "vast salaris"),
    "gender":     ("geslacht", "sekse", "m/v", "man/vrouw"),
    "function":   ("functie", "functietitel", "functienaam", "rol", "vakgebied"),
    "level":      ("niveau", "schaal", "salarisschaal", "functiegroep",
                   "functieschaal", "werknemerscategorie", "categorie"),
    "fte":        ("fte", "deeltijd", "deeltijdfactor", "parttime", "parttimefactor",
                   "werkuren", "contracturen", "dienstverband"),
    "tenure":     ("dienstjaren", "indiensttreding", "datum in dienst", "startdatum",
                   "in dienst sinds"),
    "country":    ("land", "werkland", "vestigingsland"),
    "variable":   ("bonus", "variabel", "toeslag", "toelage", "gratificatie"),
    "holiday":    ("vakantiegeld", "vakantietoeslag"),
    "employee":   ("medewerker", "werknemer", "personeelsnummer", "medewerkernummer"),
}

#: How Dutch systems write gender. `V` is the one that catches an English-shaped
#: parser out: it reads as "vrouw", never as a variant of "V for male".
GENDER_CODES: dict[str, tuple[str, ...]] = {
    "female": ("v", "vrouw", "f", "female", "w"),
    "male":   ("m", "man", "male"),
}

# ── the reporting duty ───────────────────────────────────────────────────────

_TRANSPOSED = Claim(
    value=False,
    hardness=UITLEG,
    source="https://www.eerstekamer.nl/wetsvoorstel/36949_wet_implementatie_richtlijn",
    as_of="2026-09-05",
    note=("Wetsvoorstel 36 949, Wet implementatie Richtlijn loontransparantie mannen en "
          "vrouwen, submitted 20 May 2026 and still 'in behandeling bij de Tweede Kamer' "
          "as of 2 September 2026 (nota naar aanleiding van het verslag). NOT in force. "
          "The 1 January 2027 date that has been repeated in this codebase is a "
          "MINISTERIAL TARGET, not a statutory one: the bill's own commencement clause is "
          "'op een bij koninklijk besluit te bepalen tijdstip', which can differ per "
          "article. Nothing client-facing may present 1 January 2027 as a commencement "
          "date."),
)

REPORTING = PayReporting(
    transposed=_TRANSPOSED,
    national_law=None,
    joint_assessment_trigger_pct=Claim(
        value=5.0, hardness=WET, source=_EU_DIRECTIVE, as_of="2026-09-05",
        note="Directive (EU) 2023/970 art. 10: a joint pay assessment is triggered where "
             "an unjustified gap of at least 5% in a CATEGORY OF WORKERS is not remedied "
             "within six months of the report."),
    # Deliberately empty: the directive's bands apply, and they are held once in
    # the EU pack rather than copied here. `reporting_for('NL')` resolves to them
    # and tells the caller the numbers came from the directive, not from Dutch law.
    #
    # What used to sit here was a copy, and the copy was wrong. It read
    # "150+ first report 2028-06-07, annually" — which merges the directive's
    # 250+ and 150-249 bands, moves the date a year late, and turns a
    # three-yearly duty into an annual one. That text is still live in
    # pay_equity_service.py and is the reason this package exists.
    #
    # It stays empty until the Dutch implementing act is in force and someone
    # has read its own phase-in. If that act genuinely gives a later Dutch date,
    # THAT is what belongs here — sourced, dated, and as a deliberate override.
    bands=(),
)

# ── statutory and near-universal pay components ──────────────────────────────

PAY_COMPONENTS = (
    Claim(("holiday_allowance", 0.08), WET,
          "https://wetten.overheid.nl/BWBR0002638 (Wet minimumloon en minimumvakantiebijslag, art. 15)",
          "2026-09-05",
          note="8% statutory minimum holiday allowance. Flat for everyone, which is why "
               "pay_equity_service excludes it from implied total pay: a component every "
               "employee receives at the same rate cannot create a gap."),
    Claim(("thirteenth_month", None), CONVENTIE, "", "2026-09-05",
          note="Common in Dutch CAOs but not statutory; value comes from the client's "
               "own PayMix rows, never assumed."),
)

# ── the collective-agreement crosswalks ──────────────────────────────────────
#
# The distinction between these two is the whole reason CrosswalkSpec has a
# `publishes_point_table` field. See the module docstring of the package.

ISF = CrosswalkSpec(
    system="ISF (Metalektro, systeemhouder FME)",
    publishes_point_table=True,
    groups=("A", "B", "C", "D", "E", "F", "G", "H", "J", "K",
            "L", "M", "N", "O", "P", "Q"),
    point_bands=(
        ("A", 0, 130), ("B", 131, 180), ("C", 181, 230), ("D", 231, 280),
        ("E", 281, 330), ("F", 331, 380), ("G", 381, 430), ("H", 431, 480),
        ("J", 481, 535), ("K", 536, 590), ("L", 591, 645), ("M", 646, 700),
        ("N", 701, 760), ("O", 761, 820), ("P", 821, 880), ("Q", 881, 940),
    ),
    scales={
        "A": (2768.86, 2803.01), "B": (2809.65, 2897.15), "C": (2869.64, 3030.46),
        "D": (2954.58, 3195.36), "E": (3057.10, 3398.63), "F": (3178.77, 3637.77),
        "G": (3318.71, 3922.71), "H": (3487.83, 4255.92), "J": (3702.73, 4655.03),
        "K": (3950.20, 5121.58),
    },
    source=Claim("ISF point boundaries A-Q and 2026 monthly scales A-K", CONVENTIE,
                 _ISF_DOC, "2026-07-21",
                 note="Point BOUNDARIES are published; the scoring method that produces a "
                      "job's point total is protected IP and is not reproduced. Groups L-Q "
                      "(Hoger Personeel) have no rigid step table, so no scales are held "
                      "for them."),
)

CATS = CrosswalkSpec(
    system="CATS (De Leeuw Consult)",
    publishes_point_table=False,
    groups=("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"),
    point_bands=(),          # deliberately empty: see source note
    sectors=("Metaal en Techniek",),
    source=Claim("functiegroep to salarisgroep label alignment, Metaal en Techniek", UITLEG,
                 _ISF_DOC, "2026-07-21",
                 note="No public point-boundary table exists for CATS. Classification is a "
                      "qualitative comparison against roughly 95 functiefamilies. Label "
                      "alignment is therefore the only honest output; a point position "
                      "would have to be re-derived from a protected method. Other sectors "
                      "are added only once sourced the same way."),
)

# ── capability slots ─────────────────────────────────────────────────────────

ORG_STRUCTURE = OrgStructure(
    employer_unit=Claim(
        "onderneming", WET, "https://wetten.overheid.nl/BWBR0002747", "2026-09-05",
        note="VERIFIED, having been the weakest claim in the product for a day: WOR "
             "art. 2 attaches to the ondernemer who maintains an onderneming with IN DE "
             "REGEL at least 50 people. The unit is the onderneming, and the test is "
             "habitual rather than a count on a given date. Worth remembering how this "
             "went: Germany, Spain, Poland and France were all sourced first, and the "
             "home market was the one nobody thought to check."),
    employee_representation=Claim(
        "ondernemingsraad", WET, "https://wetten.overheid.nl/BWBR0002747", "2026-09-05",
        note="Confirmed at source. The consent rights are in WOR art. 27 lid 1 sub c and "
             "sub g, and the CAO carve-out is in lid 3 — see the performance slot, where "
             "both are set out with the qualification that matters."),
)

JOB_ARCHITECTURE = JobArchitecture(
    level_concept=Claim(
        "functiegroep / salarisschaal", CONVENTIE, _ISF_DOC, "2026-07-21",
        note="The Dutch unit of grading is the functiegroep, set per CAO and paired with "
             "a salarisschaal. It is a collective-agreement construct, not a statutory "
             "one, so CONVENTIE is the correct marker."),
    # Superseded. This guessed that the Dutch classifications were ISCO-derived;
    # CBS confirms it and says more besides — SBC is dead, BRC 2014 is current,
    # and the inverse hop is lossy. All of that sits on the skills slot now.
    mappings=(),
)

# ── skills ───────────────────────────────────────────────────────────────────

_WET_NLQF = "https://wetten.overheid.nl/BWBR0050058/2025-01-01"
_BESLUIT_NLQF = "https://wetten.overheid.nl/BWBR0050303/2025-01-01"
_BRC = "https://www.cbs.nl/-/media/_excel/2026/17/brc2014.xlsx"
_WOR = "https://wetten.overheid.nl/BWBR0002747"

SKILLS = SkillsFramework(
    qualification_framework=Claim(
        ("NLQF", 8), WET, _BESLUIT_NLQF, "2026-09-05",
        note="Statutory since 1 January 2025 under the Wet NLQF; the level table itself "
             "sits in the Besluit NLQF art. 2, because the Act delegates it. Eight "
             "numbered levels mapping 1:1 to EQF 1-8, PLUS an Instroomniveau that maps to "
             "nothing and a level 4+ that also maps to EQF 4. Classification is compulsory "
             "for government-regulated qualifications and opt-in for non-formal ones, so "
             "the register is not a census of Dutch learning."),
    occupation_taxonomy=Claim(
        ("BRC 2014", "editie 2025"), WET,
        "https://www.cbs.nl/nl-nl/onze-diensten/methoden/classificaties/onderwijs-en-beroepen/"
        "beroepenclassificatie--isco-en-sbc--", "2026-09-05",
        note="CBS states that from reporting year 2013 it uses only ISCO-2008 and the "
             "Beroepenindeling ROA-CBS 2014 derived from it, and that the older national "
             "SBC classifications are neither used nor maintained. So SBC 1992 and SBC "
             "2010 are dead and anything still mapping to them is mapping to a corpse."),
    mappings=(
        SpineMapping(
            dimension=OCCUPATION, local_scheme="BRC 2014 ed. 2025", spine="ISCO-08",
            source=Claim("CBS publishes the codelists, and the most detailed BRC level IS "
                         "the ISCO-08 unit group", WET, _BRC, "2026-09-05",
                         note="THE HOP IS DIRECTIONAL AND THE DIRECTION MATTERS. The "
                              "published mapping runs ISCO to BRC and inverting it is "
                              "lossy: 588 ISCO unit groups collapse into 115 "
                              "beroepsgroepen, so going back reaches a unique 4-digit "
                              "ISCO code for only 22 of the 115, and one beroepsgroep "
                              "spans 35 of them. At ISCO MAJOR-GROUP level the inverse "
                              "does resolve, 113 of 115, the two exceptions being Koks "
                              "and a residual Overig bucket. So route NL to ISCO at "
                              "one-digit level on published evidence, and do not claim "
                              "four-digit precision the file cannot support. Better "
                              "route: the same workbook carries a free index of 4.715 "
                              "Dutch job titles onto 424 four-digit ISCO codes, which "
                              "reaches the precision the code path cannot."),
        ),
        SpineMapping(
            dimension=QUALIFICATION, local_scheme="NLQF", spine="EQF",
            mapping={"1": "1", "2": "2", "3": "3", "4": "4", "4+": "4",
                     "5": "5", "6": "6", "7": "7", "8": "8"},
            source=Claim("Besluit NLQF art. 2", WET, _BESLUIT_NLQF, "2026-09-05",
                         note="NLQF to EQF is a function; EQF to NLQF is NOT, because EQF "
                              "level 4 has two Dutch pre-images, 4 and 4+, and the "
                              "Instroomniveau maps to nothing at all. A round trip "
                              "through the spine therefore does not return where it "
                              "started, and any bridge that treats this as reversible "
                              "will quietly promote or demote people at level 4."),
        ),
    ),
)

# ── compensation ─────────────────────────────────────────────────────────────

COMPENSATION = CompensationModel(
    structure=Claim(
        ("WML", "CAO", "company"), WET,
        "https://wetten.overheid.nl/BWBR0001937", "2026-09-05",
        note="Three floors, each binding only upward. Wet op de CAO art. 12 makes any "
             "individual term conflicting with the CAO VOID rather than merely "
             "unenforceable, and art. 13 substitutes the CAO term where the contract is "
             "silent. Note who may invoke that nullity: art. 12 gives it to any party to "
             "the collective agreement, so the union can, not only the employee."),
    bargaining_coverage=Claim(
        0.725, WET,
        "https://zoek.officielebekendmakingen.nl/kst-29544-1304.html", "2026-09-05",
        note="72,5% in 2024, down from 76,7% in 2010, against union density of 15,3% in "
             "2025 — coverage is roughly 4,7 times membership and the difference is the "
             "extension machinery. PRODUCT-RELEVANT: the directive's action-plan trigger "
             "is 80% bargaining coverage, and the Netherlands is below it, so it owes an "
             "action plan. That is why SZW is writing letters about the CAO system."),
    extension_mechanism=Claim(
        "algemeenverbindendverklaring (AVV)", WET,
        "https://wetten.overheid.nl/BWBR0001987", "2026-09-05",
        note="The minister may declare CAO provisions generally binding, and a "
             "conflicting term between employer and employee is then VOID. About 998.600 "
             "of the 6.182.400 CAO-covered employees are bound this way rather than "
             "through membership, roughly 16%, and it is highly sectoral: horeca around "
             "39%, public administration zero. So a non-member employer who signed "
             "nothing can still be unable to agree pay below the scale, bounded from "
             "outside the contract entirely — and because an AVV runs only for its "
             "declared period, that constraint lapses and revives. The AVV split comes "
             "from the SZW CAO register; CBS explicitly does NOT know whether a given "
             "employee is covered by membership or by AVV, so never attribute it to CBS."),
    seniority_progression=Claim(
        "conditional annual step", WET,
        "https://www.caogemeenten.nl/cao-gemeenten-2025-2027/"
        "salaris-salaristoeslagen-en-vergoedingen", "2026-09-05",
        note="NOT the pure years-of-service lookup this product assumed. Both CAOs read "
             "in full make the annual periodiek conditional on adequate functioning: the "
             "CAO Rijk requires that the manager considers the employee to be functioning "
             "sufficiently, and the Cao Gemeenten grants the step if the employee "
             "voldoende functioneert and is not yet at the scale maximum. So model it as "
             "DEFAULT-YES BUT WITHHOLDABLE. That matters for fairness work, because the "
             "structural gender correlation then runs through TWO channels rather than "
             "one: career breaks stopping the clock, and a discretionary sufficiency "
             "gate. The second is the one a pay-equity product can actually audit — a "
             "withheld step is a decision about a person, and decisions about people can "
             "be compared. Evidence is two public-sector CAOs only; do not generalise to "
             "the market without reading private-sector texts."),
    market_data=(
        Claim("CBS StatLine 86355NED", WET,
              "https://opendata.cbs.nl/statline/#/CBS/nl/dataset/86355NED", "2026-09-05",
              note="Hourly wage by occupation, 2013-2025, classified on BRC 2014 editie "
                   "2025 — the SAME edition as the ISCO routing above, so benchmark and "
                   "classification agree for once. But its wage definition EXCLUDES "
                   "bijzondere beloningen and overtime, so it will not match a client's "
                   "total-cash figure, and that mismatch has to be stated in any "
                   "comparison against the market rather than absorbed silently."),
        Claim("CBS microdata is not available to us", WET,
              "https://www.cbs.nl/nl-nl/onze-diensten/maatwerk-en-microdata", "2026-09-05",
              note="Access is limited to universities, scientific organisations and "
                   "planning agencies whose PRIMARY ACTIVITY is research and who publish "
                   "publicly, and every output must be publicly released when the project "
                   "ends. A Dutch BV does not qualify, and mandatory publication is "
                   "incompatible with a proprietary benchmark. This is a "
                   "university-partnership route, not a product data source — worth "
                   "knowing before anyone plans around it."),
        Claim("EBB collects no earnings", WET,
              "https://www.cbs.nl/nl-nl/onze-diensten/methoden/onderzoeksomschrijvingen/"
              "korte-onderzoeksbeschrijvingen/enquete-beroepsbevolking--ebb--", "2026-09-05",
              note="Income enters the Enquete Beroepsbevolking only through the "
                   "weighting. Do not use it as a pay source."),
    ),
    constraints=(
        Claim("Waadi art. 8", WET, "https://wetten.overheid.nl/BWBR0009616", "2026-09-05",
              note="An agency worker placed with a hirer is entitled to at least the same "
                   "terms as employees in equal or equivalent roles at that hirer. So a "
                   "pay-equity dataset that excludes the hirer's agency staff is "
                   "measuring an incomplete population BY THE LAW'S OWN DEFINITION, not "
                   "merely by preference. Payrolling is carved out and sits under a "
                   "stricter regime."),
        Claim("verplichtstelling bedrijfstakpensioenfonds", WET,
              "https://wetten.overheid.nl/BWBR0012092", "2026-09-05",
              note="A sector-level erga omnes device parallel to the AVV but a separate "
                   "instrument: the minister can make participation in a sector pension "
                   "fund compulsory, binding employers to that fund's rules. Around 90% "
                   "of employees have a supplementary scheme. How much of that 90% runs "
                   "through a verplichtstelling could NOT be sourced — the widely quoted "
                   "figure has no primary basis and must not be repeated. Separately, the "
                   "Wtp transition to 1 January 2028 is restructuring pension cost as a "
                   "share of pay right now, which makes it an unstable component for any "
                   "equity comparison spanning 2026 to 2028."),
        Claim("WKR vrije ruimte 2026", WET,
              "https://zoek.officielebekendmakingen.nl/kst-36812-129.html", "2026-09-05",
              note="2% over the first 400.000 euro of the fiscal wage bill plus 1,18% "
                   "above it. Relevant because the Netherlands values benefits in kind "
                   "inside this regime at actual value, where France for example uses an "
                   "administrative forfait — so the same benefit produces different "
                   "numbers in the two countries by construction."),
    ),
)

# ── performance ──────────────────────────────────────────────────────────────

PERFORMANCE = PerformanceModel(
    codetermination=Claim(
        True, WET, _WOR, "2026-09-05",
        note="WOR art. 27 lid 1 gives the ondernemingsraad a CONSENT right — "
             "instemmingsrecht, not consultation — over sub c, a belonings- or "
             "functiewaarderingssysteem, and separately over sub g, a regeling op het "
             "gebied van de personeelsbeoordeling. So both a pay structure and an "
             "appraisal system need the works council's agreement. Sub l also covers "
             "arrangements for observing or monitoring attendance, behaviour or "
             "performance, which is likely to reach the tooling itself and not only the "
             "policy."),
    constraints=(
        Claim("WOR art. 27 lid 3", WET, _WOR, "2026-09-05",
              note="THE CARVE-OUT, and it is large. Consent is not required to the extent "
                   "the matter is already substantively regulated in a collective "
                   "agreement. With CAO coverage at 72,5%, the instemmingsrecht over pay "
                   "and job evaluation bites hardest in the uncovered quarter of the "
                   "market. Any feature built on 'your OR must consent to your pay "
                   "system' has to pass through this gate first, or it will tell most "
                   "Dutch clients something untrue about their own situation."),
        Claim("WOR ladder by size", WET, _WOR, "2026-09-05",
              note="Under 10 people nothing is mandatory; from 10 to 49 the employer must "
                   "convene a personeelsvergadering at least twice a year, with a "
                   "personeelsvertegenwoordiging of at least three elected members as the "
                   "alternative; from 50 an ondernemingsraad is compulsory. Art. 2 says "
                   "IN DE REGEL ten minste 50 — habitually, not a headcount on any given "
                   "day, so a roster snapshot is the wrong instrument for this test."),
    ),
)


PACK = CountryPack(
    country="NL",
    name="Netherlands",
    currency="EUR",
    languages=("nl",),
    status=DRAFT,
    vocabulary=VOCABULARY,
    gender_codes=GENDER_CODES,
    pay_components=PAY_COMPONENTS,
    reporting=REPORTING,
    crosswalks=(ISF, CATS),
    org_structure=ORG_STRUCTURE,
    job_architecture=JOB_ARCHITECTURE,
    skills=SKILLS,
    compensation=COMPENSATION,
    performance=PERFORMANCE,
    notes=(
        "DRAFT rather than LIVE only because the transposition claim is stale, not "
        "because the crosswalk data is in doubt: that was verified against primary "
        "texts on 2026-07-21 and is the best-evidenced part of this pack.",
    ),
)

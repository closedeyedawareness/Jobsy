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
        "onderneming", ONBEVESTIGD, "", "2026-09-05",
        note="Dutch thresholds are believed to attach to the onderneming, and the "
             "ondernemingsraad becomes mandatory at 50 people under the Wet op de "
             "ondernemingsraden. NEITHER WAS CHECKED against the statute in this round, "
             "which is why this is the weakest claim in the Dutch pack while the German, "
             "Spanish, Polish and French equivalents are all sourced. Read WOR art. 2 "
             "before relying on the 50. The irony is deliberate and worth keeping: the "
             "home market is the one nobody thought to verify."),
    employee_representation=Claim(
        "ondernemingsraad", ONBEVESTIGD, "", "2026-09-05",
        note="Consultation and consent rights over pay and appraisal systems are believed "
             "to sit in WOR art. 27. Unverified. Do not tell a Dutch client what their OR "
             "must agree to on the strength of this line."),
)

JOB_ARCHITECTURE = JobArchitecture(
    level_concept=Claim(
        "functiegroep / salarisschaal", CONVENTIE, _ISF_DOC, "2026-07-21",
        note="The Dutch unit of grading is the functiegroep, set per CAO and paired with "
             "a salarisschaal. It is a collective-agreement construct, not a statutory "
             "one, so CONVENTIE is the correct marker."),
    mappings=(
        SpineMapping(
            dimension=OCCUPATION, local_scheme="BRC / SBC (CBS)", spine="ISCO-08",
            source=Claim("CBS occupational classifications derive from ISCO", ONBEVESTIGD,
                         "", "2026-09-05",
                         note="The Beroepenindeling ROA-CBS and the older SBC are "
                              "understood to be ISCO-derived, which would make the hop to "
                              "the spine structural rather than a lookup. Confirm against "
                              "the CBS classification documentation before routing "
                              "anything through it."),
        ),
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
    notes=(
        "DRAFT rather than LIVE only because the transposition claim is stale, not "
        "because the crosswalk data is in doubt: that was verified against primary "
        "texts on 2026-07-21 and is the best-evidenced part of this pack.",
    ),
)

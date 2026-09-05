"""
jobsy/services/country_packs/es.py — Spain.

Spain is the pack that breaks the product's central assumption, which is that a
pay-reporting duty is something you grow into. There is no size threshold. The
registro retributivo is due at **one employee**, and it has been since 2020.

RD 902/2020 art. 5.1 says the register covers "toda su plantilla, incluido el
personal directivo y los altos cargos ... al margen de su tamaño", and art. 4.1
binds the equal-pay duty "independientemente del número de personas
trabajadoras". So a screen that gates the register behind a headcount is not
merely unhelpful for a Spanish client — it tells a 12-person employer they are
out of scope when they have been in default for six years.

Three duties, three different scopes, and they must not be collapsed:

  * **registro retributivo** — every employer, from one worker.
  * **auditoría retributiva** — employers with a plan de igualdad, i.e. 50+
    since 7 March 2022, or any size where the convenio imposes one.
  * **the 25% justification** — 50+, on company-wide totals.

── The two findings most likely to produce a wrong number ───────────────────

**Spain's mandatory basis is the UN-normalised one.** The official register
tool defines *importes efectivos* — what was actually paid, no FTE grossing, no
annualising — as obligatory, and *importes equiparados* — normalised to a full
jornada and a full year — as voluntary. A Dutch-shaped engine normalises by
reflex. Report the wrong basis and the numbers will not reconcile with the
register the client actually filed.

**Not every concept may be normalised even when you do normalise.** The tool
carries a per-concept `Normalizable` flag because some items are paid in full
regardless of hours: the guide names the transport allowance paid whole to
someone on reduced hours, and company allowances paid whole during maternity
leave. Blanket FTE-grossing inflates precisely the allowances that protect
part-timers, who are disproportionately women. This one can flip the sign of a
gap.

── On hardness ──────────────────────────────────────────────────────────────

Unusually well-evidenced for a new pack: RD 902/2020, RD 901/2020, the
Estatuto de los Trabajadores, Orden PCM/1047/2022, RD 126/2026 and Orden
ESS/2098/2014 were all read as full text on boe.es, and the official ministry
tools were parsed directly. What is NOT confirmed is flagged, and the vendor
half of the vocabulary rests on secondary sources and says so.

DRAFT rather than LIVE, because LIVE means a person checked, and so far only an
agent has.
"""
from __future__ import annotations

from . import (CONVENTIE, DRAFT, ONBEVESTIGD, UITLEG, WET, Claim, CountryPack,
               CrosswalkSpec, PayReporting, ReportingBand)

_RD902 = "https://www.boe.es/buscar/act.php?id=BOE-A-2020-12215"   # igualdad retributiva
_RD901 = "https://www.boe.es/buscar/act.php?id=BOE-A-2020-12214"   # planes de igualdad
_ET = "https://www.boe.es/buscar/act.php?id=BOE-A-2015-11430"      # Estatuto de los Trabajadores
_LO32007 = "https://www.boe.es/buscar/act.php?id=BOE-A-2007-6115"
_ORDEN_SVPT = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2022-18040"  # PCM/1047/2022
_SMI2026 = "https://www.boe.es/buscar/act.php?id=BOE-A-2026-3815"  # RD 126/2026
_PAYSLIP = "https://www.boe.es/boe/dias/2014/11/11/pdfs/BOE-A-2014-11637.pdf"
_QUIMICA = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-3083"  # XXI Convenio general
_VERIFIED = "2026-09-05"   # read as full text on boe.es
_SECONDARY = "vendor documentation, 2026-09-05; not an official source"

#: The government's own job-evaluation instrument, and the reason Spain is not
#: the Dutch situation. Orden PCM/1047/2022 approved a free 1,000-point
#: analytical scheme with published weights, agreed with CCOO, UGT, CEOE and
#: CEPYME. Using it is VOLUNTARY, but art. 2 gives it a safe harbour: a
#: valuation made with the tool "reúne los requisitos formales establecidos"
#: under RD 902/2020.
#:
#: The distinction that matters for a crosswalk is not proprietary-versus-public
#: — Spain's method is entirely public — but CROSS-EMPLOYER COMPARABILITY. The
#: tool sorts one employer's own jobs into equal-value bands (ESCALA 01..30). It
#: does not place a job on a national grade the way ISF does, so it grounds an
#: Art. 4 evaluation and still yields no crosswalk.
JOB_EVALUATION_TOOL = Claim(
    ("SVPT", 1000), WET, _ORDEN_SVPT, _VERIFIED,
    note="Sistema de Valoración de Puestos de Trabajo, 1000 points over four weighted "
         "categories: naturaleza de las funciones 40%, condiciones educativas 20%, "
         "condiciones profesionales y de formación 25%, condiciones laborales y "
         "desempeño 15%. Deliberately built against the usual bias: emotional effort is "
         "weighted level with mental effort, and responsibility for people's wellbeing "
         "carries the largest share of its subfactor. Voluntary, with a formal safe "
         "harbour under art. 2 of the Orden. Within-employer only.")

# ── vocabulary ───────────────────────────────────────────────────────────────
#
# Two sources, and they behave differently. The payslip model (Orden
# ESS/2098/2014) is a legal anchor: employers may add fields and reformat, but
# under the 1994 Orden they may NOT rename or drop the official concepts, so
# those strings are high-precision. Everything else drifts.
#
# Note what the payslip does NOT carry: no Sexo, no Puesto, no Centro de
# trabajo, no Antigüedad. Gender and job title cannot be derived from a Spanish
# payslip at all. If ingestion is payslip-driven, the two fields the entire
# analysis depends on are structurally absent and must come from the HR master.
VOCABULARY: dict[str, tuple[str, ...]] = {
    "salary":   ("salario base", "s.base", "salario", "sueldo", "retribucion",
                 "retribución", "total devengado", "total salario", "salbase",
                 "percepciones salariales", "salario en especie"),
    "gender":   ("sexo", "genero", "género"),
    "function": ("puesto", "puesto-empresa", "puesto de trabajo", "ocupacion",
                 "ocupación", "cargo"),
    "level":    ("grupo profesional", "grupo", "nivel", "categoria profesional",
                 "categoría profesional", "escala-empresa", "grupo de cotizacion",
                 "grupo de cotización", "convenio", "convenio/area", "convenio/área"),
    "fte":      ("jornada", "% de jornada", "porcentaje de jornada", "tipojor",
                 "coeficiente tiempo parcial", "jornada reducida", "% jornada reducida",
                 "reduccion de jornada", "reducción de jornada", "tiempo parcial"),
    "tenure":   ("antiguedad", "antigüedad", "fecha de antiguedad",
                 "fecha de antigüedad", "fecha de contratacion",
                 "fecha de contratación", "anoanti"),
    "variable": ("complementos salariales", "complemento", "conc.sal", "prima",
                 "incentivo", "bonus", "comsal", "participacion en beneficios",
                 "participación en beneficios"),
    "holiday":  ("pagas extraordinarias", "paga extra", "gratificaciones extraordinarias",
                 "gextra", "extraorm", "importe prorrata pagas extraordinarias"),
    "employee": ("id", "trabajador", "nif", "num. afil. seguridad social",
                 "codigo de empleado", "código de empleado"),
    "country":  ("pais", "país", "centro de trabajo"),
    # Not a synonym for pay: these are reimbursements and must be carried
    # separately rather than folded into either of the two pay tiers.
    "non_pay":  ("percepciones no salariales", "extrasalarial", "c.extra",
                 "retrinoin", "dietas", "plus de transporte", "plus de distancia",
                 "indemnizaciones", "suplidos"),
}

#: Spain has the worst gender-code situation of any pack so far, and the
#: dangerous letter is deliberately ABSENT below.
#:
#: `M` is undecidable. In an H/M file it is *Mujer* — female — and a3nom, the
#: most widely deployed Spanish payroll engine, accepts only H or M. In a
#: Masculino/Femenino file the same letter is *male*, and both vocabularies
#: appear inside one official ministry workbook. A parser that picks either
#: reading is right about half of Spain and silently inverts the other half,
#: producing a gap of the correct magnitude and the wrong sign.
#:
#: So `m` is not mapped here at all. A file whose gender column contains `M`
#: plus one letter this table does not resolve must be REJECTED to a prompt,
#: not guessed. Losing an import is recoverable; reporting a reversed pay gap
#: to a regulator is not.
#:
#: The numeric codes come from two different official lineages that happen not
#: to collide: Seguridad Social uses 1=hombre, 2=mujer, while INE uses 1=Hombre
#: and 6=Mujer. A `6` is the only positive signal of INE provenance; its
#: absence proves nothing.
GENDER_CODES: dict[str, tuple[str, ...]] = {
    "female": ("mujer", "femenino", "f", "2", "6"),
    "male":   ("hombre", "masculino", "h", "1"),
}

# ── the reporting duty ───────────────────────────────────────────────────────

_TRANSPOSED = Claim(
    value=False, hardness=UITLEG,
    source="https://expinterweb.mites.gob.es/participa/listado?tramite=2&estado=2",
    as_of=_VERIFIED,
    note="Spain missed the 7 June 2026 deadline. The only step taken is a consulta "
         "publica previa on a PROYECTO DE REAL DECRETO, open 24 April to 8 May 2026; the "
         "next stage, audiencia e informacion publica, has not been opened. Note the "
         "instrument: a real decreto is secondary legislation, and several directive "
         "requirements (burden of proof, remedies, sanctions) sit at statute level, so "
         "an RD alone may not suffice. Whether an accompanying law is intended is "
         "unconfirmed. Spain's existing register and audit are unaffected and remain the "
         "live duty.")

REPORTING = PayReporting(
    transposed=_TRANSPOSED,
    national_law=Claim("Real Decreto 902/2020 de igualdad retributiva entre mujeres y "
                       "hombres", WET, _RD902, _VERIFIED),
    pre_existing_duty=Claim(
        True, WET, _RD902, _VERIFIED,
        note="THREE duties with three different scopes, which must not be collapsed into "
             "one threshold. (1) The REGISTRO RETRIBUTIVO under art. 5: every employer, "
             "from one worker, recording the arithmetic MEAN AND MEDIAN by sex for the "
             "salario base, EACH complemento and EACH percepcion extrasalarial "
             "separately (the guide says sin agruparlos, so a single total-bonus column "
             "does not satisfy it), broken down by grupo profesional, categoria, nivel or "
             "puesto. Workers' representatives must be consulted at least 10 days before "
             "it is drawn up. (2) The AUDITORIA RETRIBUTIVA under art. 7: employers with "
             "a plan de igualdad, so 50+ since 7 March 2022, OR any size where the "
             "convenio imposes one. (3) The 25% JUSTIFICATION under ET art. 28.3: 50+ "
             "only. See the notes for why that 25% is not the directive's 5%."),
    # Deliberately None. The field means the directive's Art. 10 joint pay
    # assessment, and Spain has no equivalent mechanism. Spain's 25% rule looks
    # like a neighbour and is not one: different threshold, different unit
    # (company-wide totals rather than per category of workers), and a different
    # consequence — a written justification rather than a joint assessment with
    # a six-month cure clock. RD 902/2020 art. 10.2 goes further and says the
    # justification "no puede aplicarse para descartar la existencia de indicios
    # de discriminacion", so passing it is not even a defence. Putting 25.0 in
    # this field would make a screen say Spain's trigger is five times looser
    # than the directive's, when in truth Spain has no trigger of this kind at
    # all and will acquire the 5% one on transposition.
    joint_assessment_trigger_pct=None,
    bands=(
        ReportingBand(
            min_employees=0, max_employees=None,
            first_report=Claim("in force since 2020", WET, _RD902, _VERIFIED,
                               note="No size threshold: RD 902/2020 art. 5.1 requires the "
                                    "register of every employer al margen de su tamano. "
                                    "This is the band that breaks a headcount-gated "
                                    "screen, and it is the whole population."),
            frequency=Claim("continuous, per calendar year", WET, _RD902, _VERIFIED,
                            note="Art. 5.4: the reference period is the calendar year, but "
                                 "the register must also be updated on any alteracion "
                                 "sustancial. It is a maintained document, not an event."),
        ),
    ),
)

# ── pay components ───────────────────────────────────────────────────────────

PAY_COMPONENTS = (
    Claim(("pagas_extraordinarias", 2), WET, _ET, _VERIFIED,
          note="ET art. 31: a statutory MINIMUM of two per year. Only the Christmas one "
               "has a fixed occasion; the second month, and the AMOUNT of both, are set "
               "by convenio, and convenios routinely add a third or fourth. Prorrateo "
               "across twelve months is permitted but requires a convenio clause — it is "
               "not an employer election. The trap runs in both directions: monthly x 12 "
               "UNDERSTATES when pagas are separate, and DOUBLE-COUNTS when they are "
               "prorrateadas and a pagas line is added on top. Worse, prorrateo is a "
               "convenio-level fact, so one Spanish population can mix both conventions "
               "across provinces. Take the annual sum actually paid; never reconstruct "
               "from a monthly rate."),
    Claim(("smi_annual_floor", 17094.0), WET, _SMI2026, _VERIFIED,
          note="RD 126/2026: 40,70 EUR/day or 1.221 EUR/month. Encode the ANNUAL FLOOR, "
               "not a x14 multiplier: the operative text sets a floor en computo anual "
               "and does not state a payment count. Two consequences — in-kind pay is "
               "excluded, and compensacion y absorcion works annually, so an employee "
               "whose base pay sits below the monthly figure can still be lawful if "
               "annual pay clears the floor."),
    Claim(("extrasalariales", None), WET, _ET, _VERIFIED,
          note="ET art. 26.2 excludes from pay: indemnizaciones and suplidos for costs "
               "incurred, Social Security benefits, and compensation for transfers, "
               "suspensions or dismissals. In practice that means dietas and the pluses "
               "de transporte y distancia are NOT pay and must not enter a gap. But the "
               "register must still record each of them separately, so the model needs "
               "THREE tiers: salario base, complementos salariales, percepciones "
               "extrasalariales — carry all three, gap-test the first two, disclose all "
               "three. And do not trust the source system's own flag: the official guide "
               "warns that an employer's classification no prejuzga la naturaleza de la "
               "retribucion. A transport allowance paid to everyone regardless of "
               "commuting is pay in law whatever payroll calls it."),
)

# ── crosswalk ────────────────────────────────────────────────────────────────
#
# Spain publishes its convenio salary tables by law — ET art. 90.3 requires
# "publicacion obligatoria y gratuita" in the BOE or the relevant autonomous or
# provincial boletin — and REGCON gives anonymous public access. So unlike the
# Dutch case there is no IP boundary here at all.
#
# The obstacle is different and more mundane: for the four largest sectors the
# money is not in the state text. Hostelería, metal and construcción defer pay
# to provincial bargaining, so the real grain is province x área funcional x
# grupo, scattered across some fifty boletines in heterogeneous PDF layouts.
# Química is the exception and the only sector held here.

QUIMICA = CrosswalkSpec(
    system="XXI Convenio general de la industria química",
    publishes_point_table=False,
    groups=("0", "1", "2", "3", "4", "5", "6", "7", "8"),
    point_bands=(),
    scales={"1": (19145.50, 19145.50), "8": (50735.56, 50735.56)},
    sectors=("Industria química",),
    source=Claim("9 grupos (0-8) x 6 divisiones orgánicas funcionales, with a national "
                 "annual salary table", WET, _QUIMICA, _VERIFIED,
                 note="The closest Spain comes to a nationally published grade-level pay "
                      "grid, which is why it is the one sector encoded. Only the two "
                      "endpoints of the 2024 table are held (grupo 1 at 19.145,50 and "
                      "grupo 8 at 50.735,56 EUR/year); the intermediate grupos were not "
                      "captured and must be read from the BOE text before any figure is "
                      "shown per grupo. The convenio's art. 22 does name weighted "
                      "factors, but whether it yields numeric scores is unconfirmed, so "
                      "no point table is claimed."),
)

PACK = CountryPack(
    country="ES",
    name="Spain",
    currency="EUR",
    languages=("es",),
    status=DRAFT,
    vocabulary=VOCABULARY,
    gender_codes=GENDER_CODES,
    pay_components=PAY_COMPONENTS,
    reporting=REPORTING,
    crosswalks=(QUIMICA,),
    notes=(
        "SCOPE: everything is counted per EMPRESA, never per centro de trabajo. RD "
        "901/2020 art. 3.1 says the plantilla total de la empresa counts cualquiera que "
        "sea el numero de centros de trabajo. A system that aggregates by site will "
        "under-count and mis-scope. This is the opposite of Germany, where the unit is "
        "the Betrieb — so 'headcount' means a different thing in each pack.",

        "HEADCOUNT: the 50-threshold is not an FTE count. Every part-timer counts as one "
        "whole person regardless of hours; fijos discontinuos, temporary and agency "
        "workers all count; and terminated fixed-term contracts from the preceding six "
        "months add one person per hundred days worked. Measured at 30 June and 31 "
        "December, and once crossed the duty RATCHETS: it survives dropping back below "
        "50 for the life of the plan or four years. An FTE-based threshold will "
        "systematically under-trigger.",

        "BASIS: importes efectivos (actually paid, un-normalised) are MANDATORY; importes "
        "equiparados (normalised to full jornada and full year) are voluntary. A "
        "Dutch-shaped engine normalises by reflex and will produce figures that do not "
        "reconcile with the register the client filed.",

        "NORMALISATION: the official tool flags concepts individually as Normalizable "
        "and Anualizable, because some are paid in full regardless of hours — the "
        "transport allowance for someone on reduced hours, company allowances during "
        "maternity leave. Blanket FTE-grossing inflates exactly the allowances that "
        "protect part-timers. This can flip the sign of a gap.",

        "ROW GRAIN: the register's row is a person AND a situacion contractual, not a "
        "person. One employee can appear on several rows in one year, and a new "
        "situacion is created by a change of puesto, contract type, jornada, reduction, "
        "antigüedad, training level or pay. A one-row-per-employee schema cannot "
        "represent it. In the equiparados view only the last situacion of the year is "
        "used, so the two bases have different row counts.",

        "FIJO DISCONTINUO will look like a large pay gap that is not one. These are "
        "permanent contracts worked for part of the year, so annual pay is a fraction of "
        "a full-year figure while the contract is indefinite and the jornada may be "
        "100%. They cluster by sex in hostelería and comercio, so a raw annual "
        "comparison reports a calendar artefact as a fairness finding.",

        "CLASSIFICATION: two axes, always. Company structure (Area, Dpto, Puesto, "
        "Escala-empresa) and convenio structure (Convenio/Area, Categoria, Grupo, Nivel) "
        "are separate and both must be carried. In construccion, grupo and nivel "
        "retributivo are orthogonal rather than nested. A single grade column loses the "
        "legally operative one.",

        "GRUPO PROFESIONAL IS NOT A PAY GRADE. Hostelería has 3 grupos for roughly 1.3 "
        "million workers; química has 9. Pay lives at province x area funcional x grupo. "
        "Ranking or comparing grupos across convenios is meaningless.",

        "VOCABULARY: categorias profesionales were abolished as the classification unit "
        "by the 2012 reform (RDL 3/2012 and Ley 3/2012 art. 8, with convenios given "
        "until 8 July 2013 to adapt), but the WORD survives — ET art. 28.2 still names "
        "it, and the official register tool ships both a Grupo and a Categoria column. "
        "So 'categorias were abolished' is true of art. 22 and false about live column "
        "headings.",

        "PUBLICITY: a plan de igualdad, including its pay audit, must be registered in "
        "REGCON even when it was adopted voluntarily, and registration makes it publicly "
        "readable. Anything this product generates that feeds a plan de igualdad should "
        "be built on the assumption that it will be public.",

        "NOT CONFIRMED: that no transposition RD has appeared in the BOE since May 2026 "
        "(the BOE legislation search endpoint could not be queried; the absent audiencia "
        "publica stage is indirect evidence only); per-convenio covered headcount, which "
        "the ECCT does not publish; and the vendor column headings, which rest on "
        "secondary sources. Sage, Cegid/Meta4, Nominaplus and Zucchetti yielded nothing "
        "sourced at all.",

        "DRAFT rather than LIVE: the statutes were read as full text on boe.es, but LIVE "
        "means a person checked and so far only an agent has.",
    ),
)

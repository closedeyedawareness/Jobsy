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

from . import (CONVENTIE, Claim, CompensationModel, CountryPack,
               CrosswalkSpec, DRAFT, JobArchitecture, OCCUPATION,
               ONBEVESTIGD, OrgStructure, PayReporting, PerformanceModel,
               QUALIFICATION, ReportingBand, SkillsFramework, SpineMapping,
               UITLEG, WET)

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

_QUIMICA_2025 = "https://www.boe.es/boe/dias/2026/02/19/pdfs/BOE-A-2026-3870.pdf"

#: EIGHT published rows, not nine. Grupo 0 is a real professional group — the
#: directive staff — but it carries NO published salary figure and is expressly
#: kept out of the pay machinery: the convenio excludes grupo 0 from the masa
#: salarial used to apply and distribute increases, while still requiring its
#: pay to appear in the employer's own registro salarial. And senior management
#: is outside the convenio altogether.
#:
#: So grupo 0 is a named grade with no national floor, and listing it as a ninth
#: scale would invent one. It is left out of `groups` deliberately rather than
#: carried with a null.
_QUIMICA_GRUPOS = ("1", "2", "3", "4", "5", "6", "7", "8")

#: In force from 1 January 2026. The convenio publishes only the 2024 table and
#: then uplifts it 3% a year by agreement of the negotiating committee, so these
#: are the 2026 figures from the committee's published act.
_QUIMICA_SMG_2026 = (20311.46, 21733.25, 23561.31, 26201.81,
                     29856.97, 34935.76, 42450.95, 53825.35)

#: The SAME grades on continuous shift work, which is a second national grid the
#: pack did not know existed. It runs roughly 20% above the general one at the
#: bottom and includes night-work pay, and it is pro-rated by the share of days
#: actually worked on shift.
_QUIMICA_SMG_TURNO_2026 = (25023.72, 26445.52, 28273.56, 30914.04,
                           34570.13, 39648.00, 47163.22, 58537.63)

QUIMICA = CrosswalkSpec(
    system="XXI Convenio general de la industria química — régimen general",
    publishes_point_table=False,
    groups=_QUIMICA_GRUPOS,
    point_bands=(),
    scales={g: (v, v) for g, v in zip(_QUIMICA_GRUPOS, _QUIMICA_SMG_2026)},
    sectors=("Industria química",),
    source=Claim("8 grupos with a published national annual floor, 2026 figures", WET,
                 _QUIMICA_2025, _VERIFIED,
                 note="COMPLETE for 2026, cross-checked arithmetically against the 2024 "
                      "base at 3% a year. "
                      "WHAT THE FIGURE MEASURES, WHICH MATTERS MORE THAN THE FIGURE: it "
                      "is the SALARIO MINIMO GARANTIZADO, an ALL-IN ANNUAL FLOOR made up "
                      "of the totality of pay concepts for normal work — NOT salario base "
                      "in the narrow sense. It EXCLUDES antiguedad, shift, night and "
                      "holiday premiums, position complements including hazard and "
                      "toxicity pay, and sales commissions and incentives unless the "
                      "incentive is a fixed concept. So it is comparable across employers "
                      "and NOT comparable to a base-salary field that sits beside a "
                      "bonus. Putting it next to a client's 'salario base' column would "
                      "compare two different quantities. "
                      "TRANSCRIPTION TRAP: in the published PDFs the group labels sit one "
                      "row off from the values because of the column layout, so a naive "
                      "text extraction shifts the whole grid by one grade. These figures "
                      "were realigned and every cell checked against the 3% uplift. "
                      "The convenio's art. 22 names weighted factors but whether it "
                      "yields numeric scores is still unconfirmed, so no point table is "
                      "claimed."),
)

QUIMICA_TURNO = CrosswalkSpec(
    system="XXI Convenio general de la industria química — proceso continuo (turnos)",
    publishes_point_table=False,
    groups=_QUIMICA_GRUPOS,
    point_bands=(),
    scales={g: (v, v) for g, v in zip(_QUIMICA_GRUPOS, _QUIMICA_SMG_TURNO_2026)},
    sectors=("Industria química",),
    source=Claim("a second national grid for continuous shift work, 2026 figures", WET,
                 _QUIMICA_2025, _VERIFIED,
                 note="THE SAME EIGHT GRADES ON A SECOND FLOOR, and the same warning "
                      "applies: this is a SALARIO MINIMO GARANTIZADO, an all-in annual "
                      "floor, and is NOT SALARIO BASE — putting it beside a client's base-"
                      "pay column compares two different quantities. Continuous-shift "
                      "workers have their own guaranteed annual minimum, about 20% above "
                      "the "
                      "general one at grupo 1 and still about 9% above it at grupo 8, and "
                      "this one DOES include night-work pay where the general grid "
                      "excludes it. It is applied PRO RATA to the share of days actually "
                      "worked on shift over the year, so it is not a flat alternative "
                      "scale — an employee can sit between the two. "
                      "WHY THIS MATTERS FOR A PAY-EQUITY READING: shift work is not "
                      "evenly distributed by sex, so a raw comparison within one grupo "
                      "will show a gap that is partly a shift-pattern artefact and "
                      "partly not, and the two are separable only if the shift share is "
                      "known. Note also a stale cross-reference in the official uplift "
                      "acts: their prose cites article 44 for this table, but in the XXI "
                      "convenio it is article 47.6 — article 44 is weekend and holiday "
                      "work. The acts' own table headings have it right."),
)

# ── capability slots ─────────────────────────────────────────────────────────

ORG_STRUCTURE = OrgStructure(
    employer_unit=Claim(
        "empresa", WET, _RD901, _VERIFIED,
        note="RD 901/2020 art. 3.1: the plantilla total de la empresa counts cualquiera "
             "que sea el numero de centros de trabajo. The exact opposite of Germany. A "
             "system that aggregates Spanish staff by site will under-count and "
             "mis-scope every threshold."),
    employee_representation=Claim(
        "representacion legal de las personas trabajadoras (RLT)", WET, _RD902, _VERIFIED,
        note="Whether an RLT exists changes what the employer must DISCLOSE, not just who "
             "they consult: with an RLT workers reach the register's full amounts through "
             "it, without one they get percentage differences only. So the org chart "
             "determines the shape of the disclosure product, and the pack needs a flag "
             "for it."),
)

PERFORMANCE = PerformanceModel(
    codetermination=Claim(
        False, WET, _RD902, _VERIFIED,
        note="No general co-determination over performance systems as in Germany. But the "
             "auditoria retributiva under RD 902/2020 art. 8 expressly covers the "
             "PROMOTION system alongside the pay system, so a 9-box that drives promotion "
             "falls inside the audit's diagnosis whether or not anyone intended it to. "
             "That is a stronger hook than it looks: the audit is a legal document and, "
             "once it feeds a plan de igualdad, a public one."),
    constraints=(
        Claim("publicity", WET, _RD901, _VERIFIED,
              note="A plan de igualdad, audit included, must be registered in REGCON even "
                   "when adopted voluntarily, and registration makes it publicly "
                   "readable. Anything a talent or promotion analysis contributes to a "
                   "plan should be written on the assumption it will be read by "
                   "outsiders."),
    ),
)

JOB_ARCHITECTURE = JobArchitecture(
    level_concept=Claim(
        "grupo profesional", WET, _ET, _VERIFIED,
        note="ET art. 22.1 makes the grupo profesional the statutory classification unit, "
             "and categorias were abolished as that unit in 2012 though the word "
             "survives. Crucially a grupo IS NOT A PAY GRADE: hosteleria has three for "
             "roughly 1,3 million workers and quimica has nine, so grupos cannot be "
             "ranked or compared across convenios."),
    mappings=(
        SpineMapping(
            dimension=OCCUPATION, local_scheme="CNO-11 (INE)", spine="ISCO-08",
            source=Claim("the INE earnings survey carries a CNO1 field and CNO is the "
                         "Spanish ISCO derivative", UITLEG,
                         "https://www.ine.es/", _VERIFIED,
                         note="CNO-11 appears as a field in the Encuesta de Estructura "
                              "Salarial, which was read directly, and CNO is the national "
                              "adaptation of ISCO-08. The correspondence itself was not "
                              "read at source, hence UITLEG rather than WET."),
        ),
    ),
)

# ── skills ───────────────────────────────────────────────────────────────────

_MECU = "https://www.boe.es/eli/es/rd/2022/04/12/272/con"
_LO32022 = "https://www.boe.es/eli/es/lo/2022/03/31/3/con"
_RD69_2025 = "https://www.boe.es/buscar/doc.php?id=BOE-A-2025-2039"
_CNO_ISCO = "https://www.ine.es/daco/daco42/clasificaciones/corr_cno11_ciuo08.xls"
_CCT2024 = "https://www.mites.gob.es/estadisticas/cct/cct24def/cct_2024_def.xls"
_EES_MICRO = "https://www.ine.es/ftp/microdatos/salarial/datos_2022.zip"

SKILLS = SkillsFramework(
    qualification_framework=Claim(
        ("MECU", 8), WET, _MECU, _VERIFIED,
        note="RD 272/2022 sets eight levels and states level by level that each "
             "corresponds to the same EQF level, so MECU to EQF is a clean 1:1. Levels 5 "
             "to 8 were already regulated by the MECES for higher education, which has "
             "its own four-level numbering — MECU 5A is MECES 1, 6 is 2, 7 is 3, 8 is 4 — "
             "so two numbering systems coexist and a bare 'nivel 3' is ambiguous without "
             "knowing which. "
             "REFERENCED IN NOVEMBER 2024, and this pack's earlier suspicion was right "
             "about the past and wrong about the present. The decrees really did describe "
             "the certification as pending, and it really was — Spain was the LAST of the "
             "twenty-seven member states to complete it. The report was endorsed by the "
             "EQF Advisory Group in November 2024, and the international-expert step the "
             "decrees promised in the future tense was actually performed, by experts "
             "from France and Portugal. So the hypothesis that Spain was an EU state with "
             "an EQF correspondence in law but no completed referencing was TRUE UNTIL "
             "ROUGHLY DECEMBER 2024 and is no longer. "
             "ONE CAVEAT THAT SURVIVES AND MATTERS: referencing is complete, but EQF "
             "LABELLING ON CERTIFICATES IS NOT. Levels appear on only some qualifications "
             "at level 3 and above, and the report's own final criterion still speaks in "
             "the future tense about assessing the legal changes needed to put the level "
             "on diplomas. Do not assume a Spanish diploma carries an EQF level."),
    occupation_taxonomy=Claim(
        ("CNO-11",), WET,
        "https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177033",
        _VERIFIED,
        note="Established by RD 1591/2010 and still current; no successor was announced on "
             "the pages read, which is an absence of evidence rather than proof none is "
             "planned."),
    mappings=(
        SpineMapping(
            dimension=OCCUPATION, local_scheme="CNO-11", spine="ISCO-08",
            source=Claim("INE publishes corr_cno11_ciuo08.xls", WET, _CNO_ISCO, _VERIFIED,
                         note="Downloaded and parsed: 555 rows, four-digit CNO-11 against "
                              "four-digit ISCO-08, MANY-TO-MANY, with frequency columns "
                              "giving the cardinality of each side and a comment column "
                              "explaining the splits. It also carries ISCO codes with NO "
                              "Spanish counterpart, flagged as no aplicable a Espana — "
                              "subsistence agricultural workers, community health "
                              "workers, associate-professional nurses, because in Spain "
                              "nursing is a degree profession in major group 2. Those "
                              "rows have a blank CNO side and a loader must not read them "
                              "as CNO entries. CORRECTION TO AN EARLIER ASSUMPTION IN "
                              "THIS PACK: the CNO1 field in the INE earnings microdata is "
                              "the ONE-DIGIT gran grupo, not four-digit, so this "
                              "crosswalk cannot be joined to that microdata without "
                              "collapsing to major group first."),
        ),
        SpineMapping(
            dimension=QUALIFICATION, local_scheme="MECU", spine="EQF",
            mapping={str(n): str(n) for n in range(1, 9)},
            source=Claim("RD 272/2022 art. 4 states the correspondence level by level",
                         WET, _MECU, _VERIFIED),
        ),
    ),
)

#: The competence catalogue, and it changed underneath the assumption this pack
#: was written on. Ley Orgánica 5/2002 is REPEALED by LO 3/2022, and the five
#: niveles de cualificación profesional went with it: RD 1128/2003 has been a
#: derogated norm since 6 February 2025. What exists now is the Catálogo
#: Nacional de Estándares de Competencias Profesionales with THREE levels, and
#: "unidad de competencia" is superseded by "estándar de competencia" built from
#: elementos de competencia with indicadores de calidad.
#:
#: RD 69/2025 Anexo II publishes the correspondence, which chains to the EQF
#: through the MECU: ECP level 1 is MECU 3, level 2 is MECU 4, level 3 is MECU 5
#: and MECES 1. Note what is NOT covered — the old CNCP levels 4 and 5 never had
#: a certificado de profesionalidad and appear in no correspondence table, so any
#: "five Spanish levels onto eight EQF levels" mapping is defined only for 1 to 3.
COMPETENCE_CATALOGUE = Claim(
    ("CNECP", 3), WET, _RD69_2025, _VERIFIED,
    note="Public and free — each standard is an unauthenticated PDF, and 28 professional "
         "families are listed including a new Inteligencia Artificial y Data. There is "
         "still NO dataset, no API and no bulk download: the national open-data portal "
         "returns nothing for the catalogue, and the listing document linked from "
         "INCUAL's own page is a dead link on their own site. "
         "BUT THE SITUATION IS FAR BETTER THAN SCRAPING THOUSANDS OF PDFS BLIND. A single "
         "133-page master catalogue PDF carries the whole skeleton — 2.627 standard codes "
         "with title, family and level, from one request — and 83 per-family index pages "
         "add the ones published since. Neither is complete alone: the PDF holds retired "
         "standards the site has dropped and the site holds newer ones, so the union of "
         "about 2.661 is the real catalogue. The per-standard PDF URLs are then "
         "ENUMERABLE from the code alone, with a single constant folder id and no UUID "
         "needed, and a wrong code returns a clean 404 rather than a soft success. "
         "ON THE LICENCE, AND A CORRECTION TO AN EARLIER OVERSTATEMENT IN THIS PACK. "
         "INCUAL's notice authorises reproduction, whole or partial, provided integrity "
         "is kept and INCUAL is cited as the source, and it prohibits TRANSFORMATION "
         "without permission. That was first written up here as though a skills product "
         "necessarily does the prohibited thing. It does not, and the difference is a "
         "design choice rather than a legal accident. "
         "REFERENCING A STANDARD IS NOT TRANSFORMING IT. Storing the identifier, keeping "
         "the title intact, citing INCUAL and pointing at their document is squarely "
         "within what the notice permits — and the computation then happens on OUR data, "
         "on what a client's own roles and pay mean relative to that standard, not on the "
         "catalogue's content. What would engage the restriction is ingesting the "
         "elementos de competencia and reshaping them into a different taxonomy of our "
         "own. So the line to hold is concrete and ours to hold: carry the code and the "
         "citation, compute on our side of it. A legal read is worth having before "
         "anything crosses that line, but nothing here has to. Separately, "
         "LO 3/2022 art. 92 creates a PERMANENTLY OPEN administrative procedure to "
         "accredit competences acquired through work experience, resolved within six "
         "months, and art. 93 makes such an accreditation partial and cumulative. Arts. "
         "15 and 17 give every citizen the right to obtain their own formative and "
         "accreditation record from two state registers — which is a real, rights-based "
         "route to an individual skills profile that has no equivalent in the other packs.")

# ── compensation ─────────────────────────────────────────────────────────────

COMPENSATION = CompensationModel(
    structure=Claim(
        ("SMI", "convenio sectorial", "convenio de empresa"), WET, _ET, _VERIFIED,
        note="And the hierarchy CHANGED in a way that reversed an earlier reform. RDL "
             "32/2021 rewrote ET art. 84.2 and REMOVED salary from the list of matters "
             "where a company convenio beats the sector: the pre-2021 letter (a), la "
             "cuantia del salario base y de los complementos salariales, is simply gone. "
             "The sector floor on pay is restored. Verified against the consolidated "
             "Estatuto whose header reads last modified 4 December 2025, so this is "
             "current and not merely enacted. What company convenios still win on is "
             "overtime and shift pay, working time, ADAPTING the classification system "
             "locally, contract modalities and work-life measures. Note too that arts. "
             "84.3 and 84.4 make regional and provincial agreements able to take priority "
             "when MORE FAVOURABLE to workers, so which convenio governs pay is not "
             "resolvable from the company's own convenio alone."),
    bargaining_coverage=Claim(
        0.9209, WET, _CCT2024, _VERIFIED,
        note="92,09% at 31 December 2024, of which 86,11% through sector convenios and "
             "11,17% through company ones. AND THE COVERAGE ITSELF HAS A GENDER GAP THAT "
             "SPAIN PUBLISHES: 95,04% of men against 88,83% of women, 6,2 points. That is "
             "a pay-equity signal in its own right and it sits in official statistics — "
             "women are measurably less likely to be covered by the instrument that sets "
             "pay floors, before any question about the floors themselves."),
    extension_mechanism=Claim(
        "erga omnes by operation of law — no extension act at all", WET, _ET, _VERIFIED,
        note="THE STRUCTURAL OUTLIER OF THE SET. ET art. 82.3: convenios regulated by the "
             "statute OBLIGE ALL EMPLOYERS AND WORKERS within their scope for their whole "
             "term. There is no ministerial declaration, no royal decree, no opt-in — a "
             "statutory convenio binds by force of the statute itself. Compare the "
             "Netherlands, France, Belgium and Germany, which all need a positive act of "
             "extension. Spain gets high coverage without any extension machinery, which "
             "means there is nothing to look up: if the employer is in scope, they are "
             "bound. The escape hatch to model is the descuelgue in the same article, "
             "which lets a company disapply the convenio's pay terms on economic or "
             "organisational grounds by agreement with worker representatives."),
    seniority_progression=Claim(
        0.6284, WET, _CCT2024, _VERIFIED,
        note="THE ONLY HARD PREVALENCE FIGURE FOR SENIORITY PAY IN ANY PACK, and it is "
             "official: 908 of 1.445 convenios signed in 2024 carry an antiguedad "
             "complement — 62,84% of agreements and 65,68% of covered workers, at "
             "essentially the same rate for company and sector convenios. It is NOT "
             "statutory: ET art. 25.1 says a worker MAY have a right to economic "
             "progression on the terms fixed by collective agreement or contract. So in "
             "Spain about two thirds of covered employees have an automatic, "
             "structurally gender-correlated pay component, and unlike every other market "
             "here that share is measured rather than guessed. Named trienios and "
             "quinquenios could not be confirmed at source — MITES does not break the "
             "complement down by period length."),
    market_data=(
        Claim("EES microdata is free and needs no registration", WET, _EES_MICRO, _VERIFIED,
              note="The Encuesta de Estructura Salarial microdata downloads directly at "
                   "about 77 MB with no authentication, in CSV, SPSS, Stata, SAS, R and "
                   "Parquet, for 2002, 2006, 2010, 2014, 2018 and 2022. Compare the "
                   "Netherlands, where CBS microdata requires being a research "
                   "institution and publishing your results. THE VARIABLE THAT MAKES IT "
                   "unusually valuable is REGULACION, which tags every worker with WHICH "
                   "CONVENIO LAYER GOVERNS THEM — state sector, lower-tier sector, "
                   "company or group, workplace, or other. Nothing in the Dutch, German "
                   "or French equivalents carries that, and it allows the sector-versus-"
                   "company pay differential to be measured by sex on official data. "
                   "ANOANTI and MESANTI alongside SEXO and SALBASE likewise allow the "
                   "seniority-gender correlation to be measured rather than assumed. Note "
                   "the granularity limit: CNO1 is one-digit only."),
        Claim("pay by occupation and sex is published, but coarse", UITLEG,
              "https://www.ine.es/jaxiT3/Tabla.htm?t=10916", _VERIFIED,
              note="INE publishes mean annual salary by occupation group and sex with the "
                   "female-to-male ratio built in, but across roughly seventeen "
                   "aggregated groups rather than four-digit CNO. There is no published "
                   "pay table at four-digit CNO. Headline for reference year 2024, "
                   "published 28 May 2026: mean annual salary 29.540,26 euro, women "
                   "26.904,90 and men 32.057,55."),
    ),
    constraints=(
        Claim("ultraactividad is indefinite again", WET, _ET, _VERIFIED,
              note="RDL 32/2021 rewrote ET art. 86 and the 2012 one-year guillotine is "
                   "gone: where negotiation has run without agreement, the convenio "
                   "REMAINS IN FORCE. The one-year mark is now only a trigger for "
                   "compulsory mediation, not an expiry. PRACTICAL CONSEQUENCE FOR THE "
                   "PRODUCT: do not build a fallback-to-SMI path when a Spanish convenio "
                   "passes its end date. An expired, unrenewed convenio still governs "
                   "pay, and treating it as lapsed would understate the floor."),
        Claim(("salario_en_especie_max", 0.30), WET, _ET, _VERIFIED,
              note="ET art. 26.1: pay in kind may never exceed 30% of the worker's salary "
                   "perceptions, and may not reduce the full cash amount of the minimum "
                   "wage. Two LABOUR-law limits that cap a flexible-pay plan independently "
                   "of anything in tax law."),
        Claim(("irpf_exempt_limits", {
                  "vales_comida_per_day": 11.0,
                  "comedor_directo": None,
                  "transporte_publico_per_month": 136.36,
                  "transporte_publico_per_year": 1500.0,
                  "guarderia": None,
                  "seguro_salud_per_person_per_year": 500.0,
                  "seguro_salud_discapacidad": 1500.0,
                  "acciones_general": 12000.0,
                  "acciones_empresa_emergente": 50000.0,
              }), WET,
              "https://www.boe.es/buscar/act.php?id=BOE-A-2006-20764 (Ley 35/2006 IRPF) "
              "and https://www.boe.es/buscar/act.php?id=BOE-A-2007-6820 (RD 439/2007)",
              _VERIFIED,
              note="Read from the consolidated texts in force September 2026. A None value "
                   "means NO CAP, not unknown: a directly run company canteen and a "
                   "first-cycle childcare place are exempt without any euro limit — the 11 "
                   "euro a day bites only on indirect formulas such as vouchers and cards. "
                   "The health-insurance allowance is PER PERSON, so a worker with a "
                   "spouse and two children carries 2.000 euro of exemption, but the scope "
                   "is spouse and descendants only — ascendants and unmarried partners are "
                   "outside the text. The transport allowance has been unchanged for "
                   "fifteen years, and the general 500 for health cover has stood since "
                   "2006; any 2026 figure higher than these is unsupported. Meal vouchers "
                   "expressly cover teleworking days at the place the worker chooses. "
                   "THE WARNING THAT MATTERS MOST: THESE ARE INCOME-TAX EXEMPTIONS AND "
                   "SAY NOTHING ABOUT SOCIAL INSURANCE. Cotización is governed by a "
                   "different statute that was not read, and exemption from one does not "
                   "generally imply exemption from the other. Do not price an employer's "
                   "cost off this table."),
        Claim("occupational pension is not universally mandatory", UITLEG,
              "https://www.boe.es/eli/es/l/2022/06/30/12/con", _VERIFIED,
              note="Ley 12/2022 creates publicly promoted employment pension funds and "
                   "simplified sectoral plans, but there is no general auto-enrolment "
                   "mandate. Adhesion becomes binding only derivatively, where a "
                   "statutory sectoral convenio contains a pension commitment. The "
                   "conclusion is sound; the specific article number was taken from a "
                   "summarising read and should be re-checked before it is cited."),
    ),
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
    crosswalks=(QUIMICA, QUIMICA_TURNO),
    org_structure=ORG_STRUCTURE,
    performance=PERFORMANCE,
    job_architecture=JOB_ARCHITECTURE,
    skills=SKILLS,
    compensation=COMPENSATION,
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

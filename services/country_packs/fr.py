"""
jobsy/services/country_packs/fr.py — France.

France is the pack that justifies the resolver's refusal to inherit. The EU
baseline says an employer under 100 has no duty; the Index de l'égalité
professionnelle has applied from **50 employees** since 2019, is published every
1 March, and carries a penalty of up to 1% of payroll. A French client handed
the directive's bands would have been told they were out of scope while sitting
on a live obligation with a three-year clock already running.

── The Index is not a pay-gap calculation, and that is the central fact ─────

A raw gender pay gap and an Index score will legitimately disagree, and a
product that presents one as the other is wrong in a way nobody can see:

  * **Prime d'ancienneté is excluded from the Index's rémunération**, along with
    overtime, intéressement and participation. Seniority pay is often the most
    structurally gendered component in a French convention, and the official
    score is built to leave it out.
  * **Gaps are forgiven up to a seuil de pertinence** — 5% when grouping by CSP,
    2% by coefficient — applied asymmetrically, so it never pushes a gap
    negative.
  * **Only groups with at least three men and three women count**, and indicator
    1 is not calculable at all if the retained population falls under 40% of
    headcount.
  * **The employer chooses the grouping**, after consulting the CSE. CSP or
    coefficient changes the seuil and therefore the score. The Index is not a
    deterministic function of the payroll.
  * **"No score" is a valid legal state.** If the maximum obtainable points fall
    below 75, no overall Index exists and the indicators are published
    individually. A data model with an integer score and no null cannot
    represent a compliant French employer.

── On hardness ──────────────────────────────────────────────────────────────

The Index articles, the Rixain dates and the Métallurgie classification were
read on Légifrance and code.travail.gouv.fr, and the Métallurgie tables were
extracted from the joint branch PDFs directly. Two government sites were
unreachable for the whole research session — travail-emploi.gouv.fr behind a
CAPTCHA and urssaf.fr refusing connections — so nothing here rests on URSSAF,
and the effectif question below stayed open because the page that settles it
could not be opened.

DRAFT rather than LIVE, because LIVE means a person checked, and so far only an
agent has.
"""
from __future__ import annotations

from . import (CONVENTIE, DRAFT, ONBEVESTIGD, UITLEG, WET, Claim, CountryPack,
               CrosswalkSpec, PayReporting, ReportingBand)

_L1142_8 = "https://code.travail.gouv.fr/code-du-travail/l1142-8"
_D1142_4 = "https://code.travail.gouv.fr/code-du-travail/d1142-4"
_L1142_10 = "https://code.travail.gouv.fr/code-du-travail/l1142-10"
_D1142_6_1 = "https://code.travail.gouv.fr/code-du-travail/d1142-6-1"
_ANNEXE_I = "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000047548258"
_ANNEXE_II = "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000047548249"
_L3221_4 = "https://code.travail.gouv.fr/code-du-travail/l3221-4"
_SENAT = "https://www.senat.fr/questions/base/2026/qSEQ260207716.html"
_METALLURGIE = "https://www.legifrance.gouv.fr/conv_coll/article/KALIARTI000046315193"
_METALLURGIE_PDF = ("https://www.convention-collective-branche-metallurgie.fr/documents/"
                    "Grille-de-classement.pdf")
_SYNTEC = "https://www.legifrance.gouv.fr/conv_coll/id/KALITEXT000005679905"
_DSN = "https://www.net-entreprises.fr/media/documentation/dsn-cahier-technique-2026.1.pdf"
_SMIC = "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000054126589"
_VERIFIED = "2026-09-05"

#: The Index's own scoring, held here because a product that shows an Index
#: number must be able to say what it is made of. Weights sum to 100 in both
#: bands, but the bands are not the same instrument: the 50-250 version merges
#: augmentations and promotions into one 35-point indicator, so a company that
#: crosses 250 does not simply gain an indicator — its score is recomputed on a
#: different scale and can move without anything about its pay changing.
INDEX_INDICATORS = {
    "250+": Claim(
        (("ecart_remuneration", 40), ("ecart_augmentations_hors_promotions", 20),
         ("ecart_promotions", 15), ("retour_conge_maternite", 15),
         ("dix_plus_hautes_remunerations", 10)),
        WET, _ANNEXE_I, _VERIFIED,
        note="Annexe I. Indicator 4 is binary (100% or nothing) and indicator 5 is a "
             "three-step function, so two of the five move in jumps and cannot be "
             "improved incrementally."),
    "50-250": Claim(
        (("ecart_remuneration", 40), ("ecart_augmentations_et_promotions", 35),
         ("retour_conge_maternite", 15), ("dix_plus_hautes_remunerations", 10)),
        WET, _ANNEXE_II, _VERIFIED,
        note="Annexe II. Indicator 2 scores on the BETTER of a percentage-point gap or a "
             "headcount gap (at most 2 points or at most 2 employees), which in a small "
             "company is a materially easier test than the 250+ equivalent."),
}

# ── vocabulary ───────────────────────────────────────────────────────────────
#
# A structural warning first, because it governs everything below. The arrêté
# of 25 February 2016 standardises ONLY the deductions table, from MONTANT BRUT
# downward. R. 3243-1 requires the earnings items to exist but prescribes no
# wording for any of them, nor for the header block. So every payslip earnings
# heading is a variant to match and none is a canonical key.
#
# The DSN cahier technique is the one place French pay vocabulary is actually
# standardised, and its names are not the payslip's names.
VOCABULARY: dict[str, tuple[str, ...]] = {
    "salary":   ("salaire de base", "salaire", "remuneration brute non plafonnee",
                 "remuneration", "rémunération", "brut", "salaire brut",
                 "remuneration nette fiscale", "montant net social", "montant brut"),
    "gender":   ("sexe", "genre", "civilite", "civilité"),
    "function": ("emploi", "libelle de l'emploi", "libellé de l'emploi", "poste",
                 "intitule de poste", "fonction"),
    "level":    ("coefficient", "coefficient hierarchique", "coefficient hiérarchique",
                 "niveau", "niveau de remuneration", "echelon", "échelon", "position",
                 "classification", "grade", "statut", "idcc",
                 "code convention collective applicable", "cotation", "classe", "groupe",
                 "code statut categoriel retraite complementaire", "pcs-ese"),
    "fte":      ("quotite de travail du contrat", "quotité de travail",
                 "quotite de travail de reference de l'entreprise", "temps partiel",
                 "modalite d'exercice du temps de travail", "forfait jour",
                 "unite de mesure de la quotite de travail", "temps plein"),
    "tenure":   ("anciennete", "ancienneté", "date de debut du contrat",
                 "date de début du contrat", "date d'entree", "date d'entrée"),
    "variable": ("prime", "primes", "prime, gratification et indemnite", "gratification",
                 "bonus", "variable", "interessement", "intéressement", "participation",
                 "ppv", "prime de partage de la valeur"),
    "holiday":  ("conges payes", "congés payés", "indemnite de conges payes",
                 "prime de vacances"),
    "employee": ("matricule", "matricule de l'individu dans l'entreprise", "nir",
                 "numero de securite sociale", "identifiant"),
    "country":  ("pays", "code pays"),
}

#: DSN carries two encodings at once: the `Sexe` rubrique uses 01/02, while the
#: NIR's own first digit is 1 or 2. Both are primary-verified, and they agree.
#:
#: `H`/`F` and `M`/`F` are universal practice in real exports and were confirmed
#: from no primary artefact, so they are included but the pack says plainly that
#: they are convention rather than standard. The genuine hazard is `M`: in a
#: French file it usually means *masculin*, but it is also the first letter of
#: *monsieur* and, in a Spanish file, of *mujer*. Because `m` is mapped to male
#: HERE and deliberately unmapped in the Spanish pack, a misrouted file resolves
#: differently in each — which is the country dimension doing its job rather
#: than an inconsistency.
GENDER_CODES: dict[str, tuple[str, ...]] = {
    "female": ("f", "femme", "femmes", "feminin", "féminin", "2", "02", "mme"),
    "male":   ("h", "homme", "hommes", "m", "masculin", "1", "01", "mr"),
}

# ── the reporting duty ───────────────────────────────────────────────────────

_TRANSPOSED = Claim(
    value=False, hardness=WET, source=_SENAT, as_of=_VERIFIED,
    note="Not transposed. The Senat was told on 18 June 2026 that the 7 June 2026 "
         "deadline had been missed, that the bill had gone to the Conseil d'Etat, and "
         "that the directive will REFONDRE the existing Index rather than sit beside it "
         "permanently. Press reported a projet de loi due at the Conseil des ministres "
         "on 9 SEPTEMBER 2026 — four days after this pack was written, so this claim has "
         "a known expiry date and should be re-read then. Until it lands, the Index is "
         "fully in force and unchanged; the March 2026 cycle ran normally.")

REPORTING = PayReporting(
    transposed=_TRANSPOSED,
    national_law=Claim("Index de l'égalité professionnelle (art. L1142-8 et s. du code "
                       "du travail)", WET, _L1142_8, _VERIFIED),
    pre_existing_duty=Claim(
        True, WET, _D1142_4, _VERIFIED,
        note="Published every year by 1 MARCH for the preceding year: visibly on the "
             "company's own website where one exists, to the CSE broken down by category "
             "and with the methodology, and to the ministry by teledeclaration. The "
             "ministry republishes every result as open data by 31 December, so a French "
             "client's score is a public number that anyone can look up — including "
             "their staff and their competitors. TWO SEPARATE consequence thresholds: "
             "below 85 the employer must publish objectifs de progression for each "
             "indicator not at maximum; below 75 they must publish corrective measures, "
             "negotiate financial catch-up, and have three years to reach 75 before a "
             "penalty of up to 1% of the preceding year's remunerations. A score of 80 "
             "triggers the first and not the second."),
    joint_assessment_trigger_pct=None,   # France has no Art. 10 equivalent yet
    bands=(
        ReportingBand(
            min_employees=250, max_employees=None,
            first_report=Claim("annually by 1 March, in force since 2019", WET,
                               _D1142_4, _VERIFIED,
                               note="Five indicators, Annexe I."),
            frequency=Claim("annually", WET, _D1142_4, _VERIFIED),
        ),
        ReportingBand(
            min_employees=50, max_employees=249,
            first_report=Claim("annually by 1 March, in force since 2019", WET,
                               _D1142_4, _VERIFIED,
                               note="Four indicators, Annexe II — a different instrument, "
                                    "not a reduced one. See INDEX_INDICATORS."),
            frequency=Claim("annually", WET, _D1142_4, _VERIFIED),
        ),
        ReportingBand(
            min_employees=0, max_employees=49,
            first_report=Claim(None, WET, _L1142_8, _VERIFIED,
                               note="Below the Index threshold. Note this is the band the "
                                    "EU baseline would have covered wrongly: it says no "
                                    "duty below 100, and France has one from 50."),
            frequency=Claim("none", WET, _L1142_8, _VERIFIED),
        ),
    ),
)

# ── pay components ───────────────────────────────────────────────────────────

PAY_COMPONENTS = (
    Claim(("thirteenth_month", None), CONVENTIE, "https://www.service-public.gouv.fr/"
          "particuliers/vosdroits/F2301", _VERIFIED,
          note="NOT statutory. It exists only through a contract, a collective accord, a "
               "custom or a unilateral undertaking. The DSN confirms the shape by "
               "excluding le 13eme mois from salaire de base, so it must be read from the "
               "client's own rows and never assumed."),
    Claim(("prime_anciennete", None), CONVENTIE,
          "https://www.service-public.gouv.fr/particuliers/vosdroits/F718", _VERIFIED,
          note="Also NOT statutory — the code du travail imposes no seniority premium. "
               "It matters here for a different reason: where a convention does provide "
               "one, the Index EXCLUDES it from remuneration, so a total-reward gap and "
               "the official score diverge by exactly the component most likely to be "
               "structurally gendered. No branch percentage is held; the figures in "
               "circulation could not be sourced and must not be published."),
    Claim(("smic_monthly", 1867.02), WET, _SMIC, _VERIFIED,
          note="12,31 EUR/hour, 1.867,02 EUR/month at 35 hours, in force since 1 JUNE "
               "2026. France had an automatic mid-year uprating that year, so anyone "
               "still carrying the 1 January figure of 1.823,03 is about 44 EUR/month "
               "wrong. Three mechanisms can move it: the annual January formula, an "
               "automatic re-set whenever the reference index rises 2% since the last "
               "setting, and a discretionary government coup de pouce on top — the "
               "formula is a floor, not a ceiling. The index is not headline CPI but "
               "prices excluding tobacco for the first quintile of households."),
    Claim(("participation", 50), WET,
          "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000038613208", _VERIFIED,
          note="Mandatory profit-sharing from 50 employees, but only after FIVE "
               "CONSECUTIVE calendar years at that size — and it counts them under the "
               "social-security effectif rule of L130-1 CSS, not the code du travail's. "
               "Since the Index's own effectif basis is unresolved (see notes), one "
               "client can carry two different definitions of fifty employees at once. "
               "Do not model a single threshold function."),
    Claim(("conges_payes_weeks", 5), WET,
          "https://code.travail.gouv.fr/code-du-travail/l3141-3", _VERIFIED,
          note="Two and a half ouvrable days per month, capped at thirty, which is five "
               "weeks against the Dutch statutory four. A total-reward comparison that "
               "prices leave will read the difference as generosity rather than law."),
)

# ── crosswalks ───────────────────────────────────────────────────────────────
#
# Classification in France is reserved to the branch — L2253-1 lists "les
# classifications" among the topics where the branch prevails over a company
# accord — so there is no national point system to hold. That is a NEGATIVE
# claim: the architecture making it branch-specific is verified, but no official
# source states "there is none", and it is recorded at UITLEG for that reason.
#
# Métallurgie is the exception that matters, and it is the strongest crosswalk
# case in any pack including the Dutch one.

METALLURGIE = CrosswalkSpec(
    system="CCN de la métallurgie du 7 février 2022 (IDCC 3248)",
    publishes_point_table=True,
    groups=("A", "B", "C", "D", "E", "F", "G", "H", "I"),
    point_bands=(
        ("A", 6, 12), ("B", 13, 18), ("C", 19, 24), ("D", 25, 30), ("E", 31, 36),
        ("F", 37, 42), ("G", 43, 48), ("H", 49, 54), ("I", 55, 60),
    ),
    sectors=("Métallurgie",),
    source=Claim("six critères classants, ten degrees each, 6-60 points, 18 classes, "
                 "9 groupes A-I", WET, _METALLURGIE_PDF, _VERIFIED,
                 note="In force since 1 January 2024. The six criteria are complexite de "
                      "l'activite, connaissances, autonomie, contribution, encadrement-"
                      "cooperation and communication; each is scored 1 to 10 "
                      "independently and the points are ADDED, giving 55 possible "
                      "cotations between 6 and 60. Two classes per groupe, except that "
                      "classe 1 spans four points and the rest span three. Cadre status "
                      "is groupes F to I and is DERIVED FROM THE SCORE rather than "
                      "assigned — which makes it, unusually, an auditable status. "
                      "THE POINT TABLE IS FREELY AND PUBLICLY PUBLISHED, in the extended "
                      "convention on Legifrance and in the joint UIMM/CFDT/CFE-CGC/FO "
                      "PDF, both open and agreeing row for row. So unlike CATS, PC 200 "
                      "or ERA, a numeric points-to-classe-to-groupe crosswalk is "
                      "defensible here and not merely label alignment. The evaluation "
                      "rubric is public too, but note that the rotated table extracts "
                      "column-scrambled and needs hand-checking before any individual "
                      "descriptor is reproduced. Secondary sources widely say EIGHT "
                      "groupes; the text says nine."),
)

SYNTEC = CrosswalkSpec(
    system="Bureaux d'études techniques / Syntec (IDCC 1486)",
    publishes_point_table=False,
    groups=("1.1", "1.2", "2.1", "2.2", "2.3", "3.1", "3.2", "3.3"),
    point_bands=(),
    sectors=("Bureaux d'études techniques",),
    source=Claim("Ingénieurs et Cadres: 8 positions, coefficients 95-270", WET,
                 _SYNTEC, _VERIFIED,
                 note="The largest branch in France by covered headcount — about 1.4 "
                      "million at the end of 2023, not the 820.200 figure that circulates "
                      "widely and is roughly 40% low. Coefficients are NOT points: there "
                      "is no cotation, no additive score and no scale common to ETAM and "
                      "cadres, so publishes_point_table is False and the coefficient is a "
                      "label. Cadre positions verified: 1.1=95, 1.2=100, 2.1=105 and 115 "
                      "on an age split, 2.2=130, 2.3=150, 3.1=170, 3.2=210, 3.3=270. The "
                      "ETAM grid is a separate structure of three fonctions subdivided "
                      "into positions; its structure is verified but its coefficient "
                      "range is NOT and is therefore not held here. Two branch texts "
                      "signed 22 October 2025 may or may not reform the classification — "
                      "check before shipping anything on IDCC 1486."),
)

PACK = CountryPack(
    country="FR",
    name="France",
    currency="EUR",
    languages=("fr",),
    status=DRAFT,
    vocabulary=VOCABULARY,
    gender_codes=GENDER_CODES,
    pay_components=PAY_COMPONENTS,
    reporting=REPORTING,
    crosswalks=(METALLURGIE, SYNTEC),
    notes=(
        "THE INDEX IS NOT A PAY-GAP CALCULATION. It excludes prime d'anciennete, "
        "overtime, interessement, participation and severance from remuneration; it "
        "forgives gaps up to a seuil de pertinence of 5% by CSP or 2% by coefficient, "
        "applied asymmetrically so it never turns a gap negative; it counts only groups "
        "holding at least three men and three women; and indicator 1 is not calculable "
        "if the retained population falls below 40% of headcount. A raw gap and the "
        "Index will legitimately differ. Never present one as the other.",

        "THE EMPLOYER CHOOSES THE GROUPING, after consulting the CSE — by CSP or by "
        "niveau/coefficient. That choice changes the seuil de pertinence and therefore "
        "the score, so the Index is not a deterministic function of the payroll. Model "
        "the grouping as an input and record that the CSE was consulted.",

        "NO SCORE IS A VALID STATE. Where the maximum obtainable points fall below 75 "
        "the Index is incalculable: no overall score exists and the indicators are "
        "published individually and rescaled. A model with a non-nullable integer score "
        "cannot represent a compliant French employer.",

        "SCOPE: thresholds count at ENTREPRISE or UES level, never at etablissement. A "
        "multi-site company computes once at company level; where a CSE exists at UES "
        "level across legally distinct companies it computes at UES level, and a UES of "
        "50+ is in scope whatever its member companies' sizes — but the publication duty "
        "still rests on each company. A model keyed on legal entity both under-scopes "
        "and mis-scopes. Compare Germany, which counts per Betrieb, and Spain, which "
        "counts per empresa: the word headcount means three different things.",

        "CADRE IS THREE DIFFERENT POPULATIONS. The DSN pension-scheme flag, the Index's "
        "CSP 'ingenieurs et cadres', and Metallurgie's groupes F-I are not the same set "
        "of people. Cadre status carries a mandatory 1,50% prevoyance charge on tranche "
        "A and usually forfait-jours eligibility, so it is a cost attached to a STATUS "
        "rather than to a job or a salary — and the flag is itself gender-correlated.",

        "FTE BREAKS HERE. The legal week is 35 hours, so a Dutch 40-hour full-time "
        "assumption skews every derived hourly rate. Worse, an employee on a forfait "
        "annuel en jours (capped at 218 days) has NO contractual hours at all, and the "
        "DSN records the working-time unit as possibly 'forfait jour'. Since the Index "
        "requires pay reconstituted en equivalent temps plein, an hours-based pipeline "
        "will fail or silently fabricate a denominator for exactly the population where "
        "pay dispersion is widest. Cadres dirigeants sit outside working-time rules "
        "entirely.",

        "COHORT: the Index excludes apprentis, contrats de professionnalisation, workers "
        "made available including interimaires, expatriates, pre-retirement, and anyone "
        "absent more than half the reference period — so most of a maternity cohort drops "
        "out of the pay indicator while driving the all-or-nothing maternity indicator. "
        "Characteristics are assessed on the last day of the reference period or the "
        "employee's last day present, and the reference period is ANY 12 consecutive "
        "months chosen by the employer. Do not assume a calendar-year snapshot.",

        "FLAT-EURO BENEFITS INVERT THE DIRECTION. Complementaire sante (employer funds at "
        "least 50%, mandatory) and titres-restaurant are flat amounts, so they are a "
        "larger share of a low salary: including them narrows a measured gap and "
        "excluding them loses real employer cost. Transport reimbursement is half a local "
        "season ticket, so Paris and a small town differ on geography alone, and "
        "titres-restaurant accrue per worked day, so part-timers accrue fewer by "
        "construction.",

        "LOI RIXAIN is a separate instrument that looks confusingly similar: 1000+ "
        "employees for a third consecutive year, at least 30% of each sex among cadres "
        "dirigeants and members of governing bodies, BINDING SINCE 1 MARCH 2026 and "
        "rising to 40% on 1 March 2029. Same 1 March date and same 1% headline as the "
        "Index, but a different population, a headcount denominator rather than pay, a "
        "two-year clock rather than three, and a penalty paid to the State budget rather "
        "than to social security. Carry it as a flag, never as a calculation.",

        "France already had the directive's Art. 4 test: L3221-4 defines equal value on "
        "professional knowledge, capacities from experience, responsibilities, and "
        "physical or nervous load. It predates 2023/970 and matches it closely.",

        "NOT CONFIRMED: which effectif rule governs the Index's 50-threshold — the code "
        "du travail's L1111-2 or the social-security L130-1 with its five-year crossing "
        "rule where a single year below resets the clock. Secondary sources contradict "
        "each other and the ministry page that settles it was CAPTCHA-gated. This "
        "matters: participation definitively uses L130-1, so one client can have two "
        "different definitions of fifty employees.",

        "NOT CONFIRMED: the Syntec ETAM coefficient range, and whether the two branch "
        "texts of 22 October 2025 reform that classification. Nothing from URSSAF was "
        "obtainable at all, so no 2026 contribution rates and no avantages en nature "
        "figures appear in this pack — note that France values benefits in kind by "
        "administrative forfait where the Netherlands uses actual value inside the "
        "werkkostenregeling, so the same company car yields different numbers by "
        "construction. Two employer costs also vary by SITE rather than by person, AT/MP "
        "and versement mobilite, so two identical employees can cost different amounts "
        "for reasons unrelated to them.",

        "EXPIRES SOON: the transposition claim was written on 2026-09-05 with a projet de "
        "loi reported for the Conseil des ministres on 9 September 2026. Re-read it "
        "after that date rather than trusting it.",

        "DRAFT rather than LIVE: LIVE means a person checked, and so far only an agent "
        "has.",
    ),
)

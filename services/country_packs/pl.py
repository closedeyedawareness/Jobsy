"""
jobsy/services/country_packs/pl.py — Poland.

The first pack outside the euro, and the market that produced the measured
artefact this whole country dimension was built for: a roster made gender-blind
inside each country reported a 27% adjusted gap once the Netherlands and Poland
were pooled. That number was never about fairness. Dutch hourly labour costs
run about 2.2 times Polish ones, and the pooled figure was measuring that.

── "Not transposed" would be wrong twice ────────────────────────────────────

Poland missed the 7 June 2026 deadline and the transposition bill (UC127) has
not even reached the Sejm. A pack keyed to that fact alone would report Poland
as having nothing, and it would be wrong in both directions, because two
directive-shaped duties arrive through entirely different statutes:

  * **Already live since 24 December 2025.** Art. 18(3ca) gives an applicant the
    right to be told the starting pay or its range, on objective and
    sex-neutral criteria, and art. 22(1) bans asking about pay history. That is
    the directive's Art. 5, in force, with no size threshold — and with no
    penalty attached, which matters just as much (see below).

  * **Enacted, in force 5 November 2026.** Art. 18(3g) requires an employer to
    counter unequal treatment "systematycznie", expressly including
    **WYKRYWANIE** — detecting — breaches. A statutory duty to *look*. It is the
    strongest legal hook in Poland for routine pay-gap analytics, and it does
    not come from the pay-transparency bill at all.

── The three things most likely to be silently wrong ────────────────────────

**FTE is not a number here.** Poland's most widely deployed payroll system
stores the working-time fraction as two integer columns, `Licznik_wymiaru_etatu`
and `Mianownik_wymiaru_etatu` — 1 and 2 for a half-timer. There is no FTE field
to find. A parser looking for `Etat` finds nothing; one grabbing a single column
reads 1 for a half-timer or 2 for a full-timer's denominator, throws no
exception, and lands the error squarely on part-time staff, who skew female.

**`K` is female.** Kobieta. An English- or Dutch-shaped parser does not
recognise it at all, and `M` — mężczyzna — is male, so a parser carrying a
Spanish or Dutch habit of reading M as female inverts the entire result.

**Thresholds count per pracodawca, and that is not the legal entity.** KP art. 3
defines the employer as an *organisational unit*, so a branch or plant that
employs people is itself the employer. A 300-person Polish company organised as
four units can sit below every 50-employee threshold in the system.

── On hardness ──────────────────────────────────────────────────────────────

Unusually strong: the statutes were read as official Dziennik Ustaw texts, and
the exchange rate came from the NBP's own table. One standing warning from the
research: the consolidated Kodeks pracy text Dz.U. 2025 poz. 277 is a 2025
snapshot and was out of date twice during this work. It is not current law.

DRAFT rather than LIVE, because LIVE means a person checked, and so far only an
agent has.
"""
from __future__ import annotations

from . import (CONVENTIE, Claim, CompensationModel, CountryPack,
               CrosswalkSpec, DRAFT, JobArchitecture, OCCUPATION,
               ONBEVESTIGD, OrgStructure, PayReporting, PerformanceModel,
               QUALIFICATION, ReportingBand, SkillsFramework, SpineMapping,
               UITLEG, WET)

_ELI = "https://api.sejm.gov.pl/eli/acts/DU"
_POZ807 = f"{_ELI}/2025/807"      # transparency amendment, in force 24 Dec 2025
_POZ1046 = f"{_ELI}/2026/1046"    # burden of proof + duty to detect, in force 5 Nov 2026
_POZ1661 = f"{_ELI}/2025/1661"    # collective agreements act, repealed KP dzial XI
_POZ1242 = f"{_ELI}/2025/1242"    # minimum wage 2026
_POZ560 = f"{_ELI}/2025/560"      # trzynastka, public sector
_ZFSS = f"{_ELI}/2024/288"
_NBP = "https://api.nbp.pl/api/exchangerates/tables/a"
_ICTWSS = "OECD/AIAS ICTWSS Poland country note, v. 1 October 2025"
_COMARCH = "Comarch ERP Optima import specification (vendor documentation)"
_VERIFIED = "2026-09-05"

#: Dz.U. 2026 poz. 1046, art. 18(3g), in force 5 November 2026. Held as its own
#: constant because it is the single most product-relevant sentence in Polish
#: employment law: an employer must act "systematycznie" against unequal
#: treatment, expressly including WYKRYWANIE — detection — of breaches, plus
#: prevention, proper response and remedial action. Employers have six months
#: to adapt their regulamin pracy, so roughly 5 May 2027.
#:
#: It is not a reporting duty and must never be presented as one. It is a duty
#: to look, which is a different and in some ways broader thing.
DUTY_TO_DETECT = Claim(
    "2026-11-05", WET, _POZ1046, _VERIFIED,
    note="Art. 18(3g) KP: the employer must systematically counter breaches of equal "
         "treatment through prevention, DETECTION of breaches, proper response and "
         "remedial action. Enacted 19 June 2026, in force 5 November 2026, with six "
         "months to adapt the regulamin pracy. Arrives outside the transposition bill "
         "entirely, so a check for 'has Poland transposed 2023/970' will miss it.")

# ── vocabulary ───────────────────────────────────────────────────────────────
#
# Two conventions that a Western-European parser gets wrong before it reads a
# single value.
#
# First, headers arrive DIACRITIC-STRIPPED and underscore-joined in the vendor's
# own specification — `Plec`, `Imie`, `Data_zatrudnienia`. A stripped header is
# normal here, not corruption, so both spellings are listed.
#
# Second, and worse: `Stawka zaszeregowania` looks like a grade and is a złoty
# AMOUNT. Mapping it to level puts the dependent variable on both sides of the
# regression. It is deliberately absent from "level" below and named in the
# notes so nobody adds it back.
VOCABULARY: dict[str, tuple[str, ...]] = {
    "salary":   ("wynagrodzenie", "wynagrodzenie brutto", "wynagrodzenie zasadnicze",
                 "placa zasadnicza", "płaca zasadnicza", "brutto", "stawka",
                 "stawka zaszeregowania", "kwota"),
    "gender":   ("plec", "płeć"),
    "function": ("stanowisko", "nazwa stanowiska", "funkcja"),
    # Deliberately thin. Poland has no private-sector grade vocabulary to speak
    # of, because it has no private-sector classification system — see the
    # crosswalk section. The public-sector terms are here because that is where
    # a grade genuinely exists.
    "level":    ("kategoria zaszeregowania", "grupa zawodowa", "wspolczynnik pracy",
                 "współczynnik pracy", "stopien sluzbowy", "stopień służbowy"),
    "fte":      ("wymiar etatu", "etat", "licznik_wymiaru_etatu",
                 "mianownik_wymiaru_etatu", "wymiar czasu pracy", "niepelny etat"),
    "tenure":   ("staz pracy", "staż pracy", "data zatrudnienia", "data_zatrudnienia",
                 "data zawarcia umowy", "data_zawarcia_umowy",
                 "data rozpoczecia pracy", "data_rozpoczecia_pracy"),
    "variable": ("premia", "nagroda", "dodatek", "prowizja", "premia regulaminowa",
                 "premia uznaniowa"),
    "holiday":  ("trzynastka", "dodatkowe wynagrodzenie roczne", "swiadczenie urlopowe",
                 "świadczenie urlopowe", "zfss", "zfśs"),
    "employee": ("numer ewidencyjny", "nr akt", "pesel", "nip", "identyfikator"),
    "country":  ("kraj", "panstwo", "państwo"),
}

#: `K` is kobieta — FEMALE — and no English- or Dutch-shaped parser recognises
#: it. `M` is mężczyzna — MALE — which is the opposite of the Spanish H/M
#: convention where M is mujer. This is exactly why gender codes live on a
#: country pack rather than in one global table: the same letter means opposite
#: things two markets apart, and both meanings are correct.
#:
#: Two encodings coexist in the country. HR systems use K/M; the statutory GUS
#: Z-12 return uses 1 = mężczyzna, 2 = kobieta. They do not collide, but they
#: must not share a decoder.
#:
#: One import note worth carrying: the vendor spec accepts K and M in UPPERCASE
#: ONLY, so a file written with lowercase will fail its import even though
#: detection here is case-insensitive. Not our bug, but our client's afternoon.
GENDER_CODES: dict[str, tuple[str, ...]] = {
    "female": ("k", "kobieta", "kobiety", "2"),
    "male":   ("m", "mezczyzna", "mężczyzna", "mezczyzni", "1"),
}

# ── the reporting duty ───────────────────────────────────────────────────────

_TRANSPOSED = Claim(
    value=False, hardness=WET, source="https://legislacja.rcl.gov.pl/projekt/12405300",
    as_of=_VERIFIED,
    note="The transposition bill UC127 sat at opiniowanie with a last modification of "
         "4 May 2026: not adopted by the Rada Ministrow and never sent to the Sejm. All "
         "3.275 prints of the current term were searched and none matches. The 7 June "
         "2026 deadline passed with nothing in Dziennik Ustaw. BUT SEE pre_existing_duty "
         "AND DUTY_TO_DETECT: two directive-shaped obligations arrive through other "
         "statutes, so 'not transposed' does NOT mean Poland has nothing. Draft "
         "thresholds circulating in commentary (250+ annual, 100-249 triennial, first "
         "report 2028) come from secondary sources that disagree with one another, and "
         "the disagreement is itself the finding: the draft is still moving. Do not "
         "build to it.",
    review_after_months=6)

REPORTING = PayReporting(
    transposed=_TRANSPOSED,
    national_law=Claim("Kodeks pracy art. 18(3ca) (Dz.U. 2025 poz. 807)", WET,
                       _POZ807, _VERIFIED),
    pre_existing_duty=Claim(
        True, WET, _POZ807, _VERIFIED,
        note="LIVE SINCE 24 DECEMBER 2025, and it is the directive's Art. 5 arriving "
             "early. Art. 18(3ca) para 1: an applicant receives the starting pay OR ITS "
             "RANGE — the employer chooses which, so do not tell a client a band is "
             "required — based on objective, sex-neutral criteria, together with the "
             "relevant provisions of any uklad zbiorowy or regulamin wynagradzania. "
             "Para 2 gives THREE ALTERNATIVE MOMENTS: in the advertisement, or before "
             "the interview where the employer did not advertise or did not include it, "
             "or before the employment relationship begins. So it is not strictly a "
             "pay-in-every-ad rule, which is how most commentary states it. Para 3 also "
             "requires advertisements AND JOB TITLES to be gender-neutral. Art. 22(1) "
             "separately bars asking about pay in current or previous employment. NO "
             "SIZE THRESHOLD: it binds every pracodawca. AND NO PENALTY: the act creates "
             "no offence and none of KP arts. 281-283 covers art. 18(3ca), so "
             "enforcement is general PIP oversight plus the candidate's own claim. The "
             "2.000-60.000 zloty figure in circulation is the GENERAL Kodeks pracy "
             "offence range as doubled on 8 July 2026, not a transparency penalty. Never "
             "promise a client a fine that does not exist. "
             "AND FROM 5 NOVEMBER 2026, art. 18(3g) requires the employer to counter "
             "unequal treatment systematically, expressly including WYKRYWANIE — "
             "DETECTING — breaches, with six months to adapt the regulamin pracy. That "
             "is a statutory duty to LOOK rather than to report, it is already enacted, "
             "and it arrives outside the transposition bill, so any check for 'has "
             "Poland transposed 2023/970' will miss it entirely."),
    joint_assessment_trigger_pct=None,   # no Art. 10 mechanism in Polish law yet
    bands=(
        ReportingBand(
            min_employees=0, max_employees=None,
            first_report=Claim(None, WET, _POZ807, _VERIFIED,
                               note="There is NO pay-gap reporting duty in Poland at any "
                                    "size — verified by text-searching the consolidated "
                                    "Kodeks pracy for luka, jawnosc, sprawozdanie and "
                                    "raportowanie, all zero. No register, no filing to "
                                    "PIP, which is an inspectorate and not a filing "
                                    "counter. This band exists to say that positively "
                                    "rather than by silence, because silence here would "
                                    "be indistinguishable from an uncovered market — and "
                                    "Poland is covered, it simply has no such duty. What "
                                    "it does have is the applicant duty above and the "
                                    "duty to DETECT from 5 November 2026."),
            frequency=Claim("none", WET, _POZ807, _VERIFIED),
        ),
    ),
)

# ── pay components ───────────────────────────────────────────────────────────

PAY_COMPONENTS = (
    Claim(("minimum_wage_monthly_pln", 4806.0), WET, _POZ1242, _VERIFIED,
          note="4.806 zloty per month and 31,40 per hour from 1 January 2026. It has "
               "risen 37,7% since January 2023, and in 2023 and 2024 it moved TWICE in "
               "one year, because the statute requires a second step on 1 July whenever "
               "forecast inflation is at least 105%. So a Polish year-on-year pay "
               "comparison measures minimum-wage movement unless it controls for it, and "
               "a mid-year window can straddle a July step. Set annually in the Rada "
               "Dialogu Spolecznego, by rozporzadzenie whenever the council does not "
               "agree — which is every year from 2020 to 2026."),
    Claim(("trzynastka_public_sector", 0.085), WET, _POZ560, _VERIFIED,
          note="The thirteenth salary is STATUTORY FOR THE PUBLIC SECTOR ONLY, at 8,5% "
               "of annual pay, needing a full calendar year or at least six months pro "
               "rata. Art. 1 para 2 enumerates state and local budget units, courts and "
               "parliamentary offices; no private employer appears. In the private "
               "sector it is purely contractual. Getting this backwards misstates total "
               "reward by about 8,5% of annual pay for a whole sector."),
    Claim(("zfss_threshold", 50), WET, _ZFSS, _VERIFIED,
          note="The social fund is mandatory at 50+ employees measured in FTE terms on "
               "1 January, and at 20-49 if a union asks; budget units carry it at any "
               "size. Opt-out is broad — a collective agreement, or a regulamin "
               "wynagradzania where there is none, may simply provide that no fund is "
               "created. WHETHER IT IS PAY IS GENUINELY CONTESTED and must not be "
               "resolved silently. Against: art. 8 para 1 makes benefits depend on the "
               "recipient's life, family and material situation, with no reference "
               "anywhere to work, performance, seniority or position. For: KP art. "
               "18(3c) para 2 sweeps in other work-related benefits, and the employer's "
               "contribution itself varies with job type and disability, which correlate "
               "with pay. Recommendation: track separately, exclude from base-pay "
               "comparison, never fold silently into total reward."),
)

# ── currency ─────────────────────────────────────────────────────────────────

EXCHANGE_RATE = Claim(
    ("EUR", 4.3179, "2026-09-04"), WET, _NBP, _VERIFIED,
    note="NBP table 172/A/NBP/2026. Held with its DATE because the date is a material "
         "parameter, not metadata: across 2026 the rate ranged from 4,2009 to 4,3465, so "
         "the same roster converted on two different days of one year moves by several "
         "percentage points with nobody's pay changing. Any converted figure must state "
         "the rate and the day it was taken. For scale, the minimum wage of 4.806 zloty "
         "is about 1.113 euro.")

# ── crosswalk ────────────────────────────────────────────────────────────────
#
# A confirmed absence, which is a real finding rather than a gap in the work.
#
# Collective bargaining covers 11,6% of Polish employees, happens at company
# level, and there is NO extension mechanism and no functional equivalent — so
# no sectoral pay floor reaches a typical private employer. On top of that, the
# November 2025 collective-agreements act repealed the whole collective-
# agreements title of the Kodeks pracy and replaced registration with a public
# register called KEUZP, which the minister has until 13 December 2027 to build.
# So as of today there is not even a queryable public register to ask whether an
# employer is covered.
#
# There is therefore NO private-sector crosswalk to build for Poland, and none
# should be invented. What does exist is public-sector, statutory, and genuinely
# encodable — which is the opposite of every other pack, where the public sector
# is the part nobody has data for.

#: Roman numerals, because that is what the regulation uses and what a Polish
#: local-government payroll file will actually carry. Do not normalise them to
#: arabic on the way in: a column holding "XII" is unambiguous, and a column
#: holding "12" could be a category, a month or a pay period.
_SAMORZAD_CATEGORIES = (
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
)

#: The complete table, in force for pay DUE FROM 1 January 2026. Each figure is
#: a floor, not a range, so both bounds are the same number.
_SAMORZAD_MINIMA = (
    4806.0, 4830.0, 4850.0, 4870.0, 4890.0, 4910.0, 4940.0, 4970.0, 5000.0, 5030.0,
    5060.0, 5090.0, 5200.0, 5310.0, 5410.0, 5630.0, 5850.0, 6070.0, 6400.0, 6750.0,
)

SAMORZAD = CrosswalkSpec(
    system="Samorządowe kategorie zaszeregowania (rozporządzenie RM)",
    publishes_point_table=False,
    groups=_SAMORZAD_CATEGORIES,
    point_bands=(),
    scales={cat: (amount, amount)
            for cat, amount in zip(_SAMORZAD_CATEGORIES, _SAMORZAD_MINIMA)},
    sectors=("Administracja samorządowa",),
    source=Claim("20 categories I-XX with minimum monthly amounts, plus a named-position "
                 "to minimum-category table", WET,
                 "https://api.sejm.gov.pl/eli/acts/DU/2026/246", _VERIFIED,
                 note="COMPLETE, from Dz.U. 2026 poz. 246 annex 3 table I, extracted twice "
                      "by independent methods with identical results. Category I is 4.806 "
                      "zloty, EXACTLY the national minimum wage — a useful invariant to "
                      "assert rather than a coincidence. WATCH THE DATE: the regulation "
                      "itself commences 16 March 2026, but its own paragraph 3 back-"
                      "applies the amounts to pay DUE FROM 1 JANUARY 2026, so the "
                      "effective date is January and not the commencement date. The "
                      "previous version ran I=4.666 to XX=6.510 in the same twenty-step "
                      "shape, so this was an across-the-board uplift and not a "
                      "restructure; it is amended roughly annually and anything derived "
                      "from it must be version-dated."),
)

# ── capability slots ─────────────────────────────────────────────────────────

ORG_STRUCTURE = OrgStructure(
    employer_unit=Claim(
        "pracodawca (organisational unit)", WET, _POZ807, _VERIFIED,
        note="KP art. 3 defines the employer as a jednostka organizacyjna, so a branch or "
             "plant employing workers IS the employer. A 300-person company in four units "
             "can sit below every 50-employee threshold. A third distinct answer after "
             "Germany's Betrieb and Spain's empresa — and unlike those two, it is not "
             "even a stable unit, because it follows how the employer organises itself."),
    employee_representation=Claim(
        "zwiazki zawodowe / rada pracownikow", UITLEG,
        "Elmar van Dijk, domain knowledge, 2026-09-05; the ustawa o informowaniu "
        "pracownikow i przeprowadzaniu z nimi konsultacji has NOT been read",
        _VERIFIED,
        note="THE THRESHOLD IS 50, AND IT IS NOT A FLAG. Below 50 there is no statutory "
             "right to a rada pracownikow under the general employee-information act. At "
             "50 and above the arrangement CAN apply — but a council does not come into "
             "being simply because the fiftieth employee is hired. The statutory election "
             "and establishment procedure has to be triggered by somebody. "
             "So a Polish employer of 200 may lawfully have no rada pracownikow at all, "
             "and a boolean derived from headcount would assert one that does not exist. "
             "This is the same shape as Belgium, where the works council is created at "
             "100 but renewed at 50 — in both markets the number ENABLES a body rather "
             "than producing one, and the product must ask whether it was actually "
             "constituted rather than infer it. "
             "Marked UITLEG rather than WET deliberately: this came from Elmar's own "
             "knowledge of the market and the statute has not been read. What would "
             "upgrade it is opening that act and citing the article that sets the "
             "threshold and the procedure. "
             "Context that is separately sourced: union density is 9,4% and bargaining "
             "coverage 11,6%, so most Polish employers have no union counterparty either, "
             "which leaves the regulamin wynagradzania as the practical instrument. Where "
             "a union does exist the employer must AGREE the regulamin with it, not "
             "merely consult."),
)

PERFORMANCE = PerformanceModel(
    codetermination=Claim(
        False, ONBEVESTIGD, "", _VERIFIED,
        note="No co-determination over performance systems is known, and with 11,6% "
             "bargaining coverage there is usually no counterparty for one. The real "
             "constraint arrives from a different direction: art. 18(3g) from 5 November "
             "2026 requires the employer to DETECT unequal treatment systematically. A "
             "9-box is one of the places unequal treatment becomes visible, so in Poland "
             "the talent grid is closer to evidence than to exposure. Unverified whether "
             "any Polish law reaches appraisal systems directly."),
)

JOB_ARCHITECTURE = JobArchitecture(
    level_concept=Claim(
        None, WET, _ICTWSS, _VERIFIED,
        note="THERE IS NO PRIVATE-SECTOR GRADE CONCEPT IN POLAND, and that is a finding "
             "rather than a gap. Bargaining covers 11,6% of employees, at company level, "
             "with no extension mechanism, and the collective-agreements title of the "
             "Kodeks pracy was repealed in December 2025 with its replacement register "
             "not due until December 2027. Private employers grade internally or with a "
             "vendor scheme. The public sector is the exception and does have statutory "
             "tables. Do not look for a Polish equivalent of a functiegroep; there isn't "
             "one to find."),
    # The occupation mapping moved to the skills slot once the real crosswalk was
    # found. What stood here was a guess marked ONBEVESTIGD, and it has been
    # replaced rather than upgraded in place, because the scheme it named was
    # also superseded: KZiS was wholly replaced on 27 November 2025.
    mappings=(),
)

# ── skills ───────────────────────────────────────────────────────────────────

_ZSK = f"{_ELI}/2024/1606"          # ustawa o Zintegrowanym Systemie Kwalifikacji
_KZIS = f"{_ELI}/2025/1534"         # klasyfikacja zawodow i specjalnosci, 27 Nov 2025
_KZIS_ISCO = ("https://psz.praca.gov.pl/documents/d/global/"
              "klucz-powiazan-pomiedzy-kzis-z-2025-r-a-standardem-isco-08-"
              "_-wg-stanu-na-dzien-27-listopada-2025-r-2-xls")
_ZRK_API = "https://zrk-api.ibe.edu.pl/pl/v1"
_PPK = f"{_ELI}/2026/192"
_MINWAGE_ACT = f"{_ELI}/2024/1773"
_GUS_Z12 = ("https://stat.gov.pl/obszary-tematyczne/rynek-pracy/"
            "pracujacy-zatrudnieni-wynagrodzenia-koszty-pracy/"
            "struktura-wynagrodzen-wedlug-zawodow-za-pazdziernik-2024-r-,4,12.html")

SKILLS = SkillsFramework(
    qualification_framework=Claim(
        ("PRK", 8), WET, _ZSK, _VERIFIED,
        note="Ustawa o Zintegrowanym Systemie Kwalifikacji of 22 December 2015, "
             "consolidated at Dz.U. 2024 poz. 1606 and genuinely current — unlike the "
             "Kodeks pracy, nothing has amended it since 1 January 2024. Eight levels, "
             "stated twice in the statute, with universal first-degree descriptors in the "
             "annex, second-degree descriptors per education type, and sectoral "
             "frameworks on top. REFERENCED TO THE EQF IN 2013 — the circulating year is "
             "right and now has a source: the referencing report published by the "
             "Instytut Badan Edukacyjnych, Warsaw 2013, approved on the government's "
             "behalf by the Committee for European Affairs on 15 May 2013 and stating "
             "that Poland meets the ten referencing criteria. Note the sequence, which is "
             "unusual: Poland referenced its framework in 2013 and only gave it force of "
             "law in 2016. One thing to check before this pack goes LIVE: Cedefop "
             "reported an UPDATED referencing report as expected in 2022, then 2023 or "
             "2024, following amendments to the ZSK act. It could not be found, so the "
             "2013 report may no longer be the latest."),
    occupation_taxonomy=Claim(
        ("KZiS", "2025", "mandatory on every ZUS registration"), WET, _KZIS, _VERIFIED,
        note="THE CLASSIFICATION WAS WHOLLY REPLACED ON 27 NOVEMBER 2025 by Dz.U. 2025 "
             "poz. 1534, which repealed the entire 2014 chain and sits under a new "
             "statute. Anything citing Dz.U. 2014 poz. 1145 is now out of date, and "
             "historic data needs the separately published KZiS-2014 to KZiS-2025 "
             "migration key to cross the break. Five levels: 10 major groups, 43, 134, "
             "445 elementary groups, and 2.583 six-digit occupations — the six-digit "
             "level does not exist in ISCO and is Poland's own extension. Usefully, the "
             "regulation itself maps each major group to an ISCO competence level, an "
             "ISCED-F range AND a PRK range in one table, which is a ready-made levelling "
             "anchor. "
             "AND EVERY POLISH EMPLOYEE ALREADY CARRIES ONE. Art. 36 ust. 10 of the "
             "social insurance act makes WYKONYWANY ZAWOD a mandatory content element of "
             "every registration, and the ZUS ZUA and ZZA forms implement it as a "
             "six-character field whose own footnote defines it as the six-digit code "
             "from the KZiS annex. Mandatory since 16 May 2021, and still worded "
             "identically in the April 2026 forms regulation. That is the "
             "highest-coverage occupation field in the country and it joins straight to "
             "the ISCO crosswalk below. "
             "TWO HONEST LIMITS. It is occupation AT REGISTRATION: nothing obliges an "
             "employer to update it when someone's job changes without a change of "
             "insurance title, so it DRIFTS and should be treated as a starting position "
             "rather than a current one. And this establishes the reporting obligation "
             "only — whether ZUS publishes or licenses anything derived from the field is "
             "a separate question that was not tested. "
             "Footnote for whoever searches next: the statute says wykonywany zawod and "
             "never kod wykonywanego zawodu, which is why an earlier pass grepping for "
             "the full phrase concluded it was not there. It was added by a COVID "
             "omnibus act of 14 May 2020 with a year's deferred commencement, which is "
             "why it is also missing from any amendment history keyed to social-insurance "
             "legislation."),
    mappings=(
        SpineMapping(
            dimension=OCCUPATION, local_scheme="KZiS 2025", spine="ISCO-08",
            source=Claim("official ministry crosswalk, 3.577 rows", WET,
                         _KZIS_ISCO, _VERIFIED,
                         note="THE LAST UNCONFIRMED HOP IN THE SET, NOW CLOSED. The "
                              "regulation's own explanatory notes say the classification "
                              "was built on ISCO-08, and the employment service publishes "
                              "a crosswalk file dated 27 November 2025 which was "
                              "downloaded and reconciled: 3.577 mapped rows, every "
                              "six-digit KZiS code reaching a four-digit ISCO unit group, "
                              "ZERO DUPLICATE KZiS CODES. That is a cleaner hop than "
                              "France's probabilistic matrix or Germany's one-to-many "
                              "key. ONE CAVEAT ON THE FILE ITSELF, printed on it: nie "
                              "jest zrodlem obowiazujacego prawa i ma wylacznie charakter "
                              "pomocniczy — it is an official auxiliary document, not "
                              "law. Fine to map with, not citable as an obligation."),
        ),
        SpineMapping(
            dimension=QUALIFICATION, local_scheme="PRK", spine="EQF",
            mapping={str(n): str(n) for n in range(1, 9)},
            source=Claim("art. 2 pkt 16 defines PRK levels as corresponding to EQF levels",
                         WET, _ZSK, _VERIFIED,
                         note="The correspondence is in the statute's own definition, "
                              "which is stronger than most: in several other markets the "
                              "framework is a declaration rather than law."),
        ),
    ),
)

#: The Zintegrowany Rejestr Kwalifikacji, and the best skills artefact found in
#: any of the seven markets — with a caveat that has to travel with it.
#:
#: It is a statutory public register served by an OPEN, UNAUTHENTICATED JSON API
#: with no key and no rate documentation, holding 20.817 qualifications, each
#: carrying its PRK level, and decomposing three levels deep: learning outcome
#: sets, then learning outcomes, then verification criteria. It also carries KZiS
#: codes, ISCED codes and an internal skills vocabulary.
#:
#: THE CAVEAT IS THE COMPOSITION, WHICH WAS MEASURED RATHER THAN ASSUMED. About
#: 85% of the register — 17.605 records — is individual university degree
#: programmes carrying a level and nothing else. The genuinely skills-decomposed
#: core is roughly 313 qualifications: 266 wolnorynkowe and 47 sektorowe, plus
#: the craft and regulated ones. On those the density is high, averaging about
#: three outcome sets, ten learning outcomes and forty-seven verification
#: criteria each. So this is a rich seam, not a rich mine, and a plan that
#: assumes twenty thousand decomposed qualifications would be wrong by two
#: orders of magnitude.
QUALIFICATION_REGISTER = Claim(
    ("ZRK", 20817, 313), WET, _ZRK_API, _VERIFIED,
    note="Note the terminology change: kwalifikacje RYNKOWE no longer exists as a "
         "category. Since 1 January 2024 it is split into wolnorynkowe, awarded by "
         "commercial bodies granted certifying rights, and sektorowe, awarded by bodies "
         "operating statutorily in a sector. Any filter matching on 'rynkowe' returns "
         "nothing. A private body genuinely can register a qualification, through "
         "application to the minister, formal review, consultation and a PRK level "
         "assignment. Two operational notes: rapid sequential requests get connection "
         "resets and need throttling, and NO TERMS OF USE PAGE COULD BE FOUND — worth "
         "resolving before a product depends on it. "
         "RESOLVED, AND BETTER THAN EXPECTED: the operator has declared CC0 1.0 on the "
         "national open-data portal against this exact endpoint, with every conditions "
         "field left empty. Three supports stack up. The CC0 permits commercial use, "
         "redistribution and derivatives with no attribution duty. The open-data act "
         "gives a general statutory reuse right that is unconditional and free by "
         "default. And art. 11 ust. 5 of that act converts the ABSENCE of published terms "
         "into reuse WITHOUT CONDITIONS — so the silence found earlier resolves in our "
         "favour rather than leaving exposure, and the database-right worry is answered "
         "the same way: the operator could have imposed conditions and demonstrably did "
         "not. "
         "FOUR RESIDUAL RISKS WORTH CARRYING. The licence lives on the portal and not on "
         "the operator's own hosts, and that record is only months old — snapshot it as "
         "dated evidence, because continued use counts as accepting whatever terms stand "
         "at the time. There is still NO documented rate limit and no 429 contract, so we "
         "run on unstated tolerance: the dataset updates daily, so backfill once and poll "
         "deltas rather than crawling. The register is flagged as high-value data, which "
         "pushes toward mandatory free open provision and strengthens the position. And "
         "CC0 DOES NOT DISPOSE OF GDPR — the register exposes person endpoints, and the "
         "open-data act expressly reserves conditions for information carrying personal "
         "data, so anything beyond qualifications and the dictionaries needs its own "
         "assessment.")

# ── compensation ─────────────────────────────────────────────────────────────

COMPENSATION = CompensationModel(
    structure=Claim(
        ("uklad zbiorowy", "regulamin wynagradzania", "umowa"), WET, _POZ1661, _VERIFIED,
        note="With bargaining at 11,6% and no extension mechanism, the instrument that "
             "actually sets pay for most Polish employers is the REGULAMIN WYNAGRADZANIA "
             "under KP art. 77(2): mandatory at 50 employees or more, optional below 50, "
             "and mandatory at 20 to 49 ONLY IF a workplace union asks for it. Note the "
             "threshold moved from 20 to 50 on 1 January 2017. Where a union exists the "
             "employer must AGREE it with them — uzgadnia, not consult — and with no "
             "union the employer sets it unilaterally, which is the common case. It takes "
             "effect two weeks after being made available to staff."),
    bargaining_coverage=Claim(
        0.116, UITLEG, _ICTWSS, _VERIFIED,
        note="11,6% in 2023, at company level, with union density 9,4%. The lowest in the "
             "set by a wide margin — compare Belgium at effectively 100%, Spain 92%, the "
             "Netherlands 72,5%, Germany 49%."),
    extension_mechanism=Claim(
        None, WET, _POZ1661, _VERIFIED,
        note="THERE IS NONE, and there is now not even a register to consult. The "
             "collective-agreements title of the Kodeks pracy was repealed on 13 December "
             "2025 and replaced by a standalone act whose new register, the KEUZP, is "
             "CONSTITUTIVE rather than administrative: art. 16 says an agreement takes "
             "effect no earlier than the day it is properly registered, and that the "
             "provisions of an unregistered agreement ARE NOT APPLIED. The minister has "
             "until 13 December 2027 to build it, with employers given a further year "
             "after that, so the register does not exist yet and filing runs directly to "
             "the ministry in the meantime. Note the driver: that act implements the "
             "MINIMUM WAGE directive 2022/2041, not the pay transparency one."),
    seniority_progression=Claim(
        "public sector only", WET, _VERIFIED and _ELI, _VERIFIED,
        note="The dodatek stazowy is statutory in the PUBLIC sector and absent from the "
             "private one, where it exists only if someone put it in a regulamin or a "
             "contract. The standard public formula is 5% of base pay after five years "
             "rising 1% a year to a maximum of 20%, in local government, the civil "
             "service, state offices and healthcare alike. TEACHERS ARE THE EXCEPTION and "
             "the exception was miscarried in earlier notes: the Karta Nauczyciela gives "
             "1% per year of service payable FROM THE FOURTH YEAR, not from the first. So "
             "Poland is the one market in the set where the structurally "
             "gender-correlated seniority component is a SECTOR fact rather than a market "
             "fact, and a mixed public-private roster will show it in one half only."),
    market_data=(
        Claim("GUS Z-12 gives median, deciles and the gap by occupation AND sex", WET,
              _GUS_Z12, _VERIFIED,
              note="Table 13 of the annex publishes all nine decile cut-offs including "
                   "the median, by major, large and medium occupation group AND by sex; "
                   "table 17 publishes the pay gap the same way. GUS says outright that "
                   "this is the ONLY survey producing pay data by occupation in Poland. "
                   "THREE LIMITS THAT BIND. Depth stops at THREE DIGITS in every "
                   "publication, so the six-digit KZiS mapping can go deeper than the "
                   "official benchmark ever will. Detail lands about sixteen months after "
                   "the reference month, because the signal release carries one-digit "
                   "groups only. And the gap is computed on FIXED PAY ONLY — profit "
                   "distributions, annual bonuses and discretionary awards are excluded — "
                   "so it is not comparable to a total-cash gap."),
        Claim(("gpg_2024", 0.041), WET, _GUS_Z12, _VERIFIED,
              note="4,1% overall for October 2024, and the aggregate hides everything "
                   "worth seeing: 1,1% in the public sector against 11,8% in the private "
                   "one, 18,8% among managers, 24,7% in one management sub-group, and "
                   "NEGATIVE for clerical staff. A headline this low invites the "
                   "conclusion that Poland has solved something. It has not; the number "
                   "is an average over a wide and structured spread."),
        Claim("GUS microdata is closed to companies", WET,
              "https://nauka.stat.gov.pl/Data", _VERIFIED,
              note="Supplied for a fee to universities, higher education institutions and "
                   "research institutes only, under contract with the institution, "
                   "delivered through a controlled channel or on site. There is no "
                   "public-use file and no self-service. Like the Netherlands and unlike "
                   "Spain, this is not a route a product can take."),
    ),
    constraints=(
        Claim("the minimum-wage exclusion list is closed and dated", WET,
              _MINWAGE_ACT, _VERIFIED,
              note="Six components are excluded from the minimum-wage calculation and "
                   "nothing else is: the jubilee award, the retirement severance, "
                   "overtime pay, the night-work supplement since 1 January 2017, the "
                   "SENIORITY supplement since 1 January 2020, and the difficult-"
                   "conditions supplement SINCE 1 JANUARY 2024 — not 2023, which is the "
                   "common misdating because the amending act was announced in August "
                   "2023. A rule dated 2023 is wrong by a year. Because the list is "
                   "closed, a dodatek funkcyjny and both kinds of premia DO count toward "
                   "the minimum. One subtlety: the difficult-conditions exclusion only "
                   "applies where the supplement has a basis in law, a collective "
                   "agreement, the regulamin or the contract — an ad-hoc payment is not "
                   "excluded."),
        Claim(("ppk_employer", 0.015), WET, _PPK, _VERIFIED,
              note="The employer must set up a PPK FROM ONE EMPLOYEE, on penalty of a "
                   "fine up to 1,5% of the previous year's payroll. Employer pays 1,5% "
                   "basic and may add up to 2,5%; the employee pays 2% and may add up to "
                   "2%, reduced to as little as 0,5% where pay FROM ALL SOURCES is under "
                   "1,2 times the minimum wage — an all-source test the employer cannot "
                   "verify, and one they must ignore in any month where pay at their own "
                   "firm exceeds the threshold. Auto-enrolment with opt-out, and "
                   "RE-ENROLMENT EVERY FOUR YEARS: the next cycle means informing staff "
                   "by 28 February 2027 with contributions resuming 1 April 2027. "
                   "Modelling detail: the employer contribution sits OUTSIDE the social "
                   "insurance base but IS taxable income for the employee, and the "
                   "employee's own share is deducted after tax."),
        Claim(("zus_employer_typical", 0.2048), UITLEG, f"{_ELI}/2026/199", _VERIFIED,
              note="Roughly 20,5% on top of gross for a small employer in 2026: pension "
                   "9,76, disability 6,50, accident about 1,67 for employers with nine or "
                   "fewer insured, labour and solidarity funds 2,45 remitted as one line, "
                   "and the guaranteed benefits fund 0,10. THE STEP CHANGE TO MODEL: the "
                   "2026 annual cap of 282.600 zloty applies ONLY to the pension and "
                   "disability contributions. Everything else is uncapped, so crossing it "
                   "mid-year changes both net pay and employer cost discontinuously — a "
                   "high earner's marginal cost drops partway through the year."),
        Claim("ulga dla mlodych", WET, "https://www.podatki.gov.pl/pit/", _VERIFIED,
              note="THE SINGLE LARGEST GROSS-TO-NET DISTORTION IN POLAND. Employment "
                   "income of people UNDER 26 is exempt from income tax up to 85.528 "
                   "zloty a year. Two employees on identical gross pay take home "
                   "materially different amounts purely by age. Any net-pay comparison, "
                   "any total-reward statement, and any fairness narrative built on net "
                   "figures has to carry age or it is measuring the tax code. It also "
                   "interacts with sex through age structure, so it is not neutral noise."),
        Claim("benefit loading depends on a document, not a benefit type", WET,
              f"{_ELI}/2025/316", _VERIFIED,
              note="Material benefits arising from a collective agreement, a regulamin "
                   "wynagradzania or pay rules, consisting of the right to buy BELOW "
                   "RETAIL PRICE, are excluded from the social insurance base. That is "
                   "why Polish benefits — medical cover, sports cards, group life — are "
                   "structured with a token employee co-payment plus a regulamin basis: "
                   "taxable for income tax, free of social insurance. So whether a "
                   "benefit carries employer cost turns on a DOCUMENT FACT rather than on "
                   "what kind of benefit it is, and two employers offering the identical "
                   "benefit can face different costs."),
    ),
)


#: The second half of the same annex, and the part that turns a pay ladder into
#: a genuine job-to-grade crosswalk: it maps NAMED POSITIONS to a minimum
#: category, a required education level and required years of service.
#:
#: It is not encoded here yet, because encoding it wrongly is worse than not
#: having it, and the structure has three row grammars that a naive parser will
#: flatten:
#:
#:   * a simple row — one position, one category, one education, one staż;
#:   * a SIZE-BANDED row — one position, an inline list of unit-size bands, and
#:     a PARALLEL list of categories positionally paired with them (a deputy
#:     treasurer is XVI, XV or XIV depending on the population served);
#:   * an ALTERNATIVE-QUALIFICATION row — one category but two education routes
#:     with different service requirements, so column three is scalar while
#:     columns four and five are vectors.
#:
#: And a fourth pattern that must not be coerced: many rows carry "według
#: odrębnych przepisów" where the qualification would be. That is not an unknown
#: education — it means the requirement is set by a different statute, and
#: recording it as missing would lose the distinction.
#:
#: Two sections of the consolidated text are already stale and must be taken
#: from their amending regulations instead: employment offices (D.III) was
#: replaced in full in 2025 and several rows changed category, and one social-care
#: row gained a second qualification route. Reading the 2024 consolidation alone
#: would produce wrong grades in both.
SAMORZAD_POSITIONS = Claim(
    ("wykaz stanowisk", "A-D", "D.I-D.XXIV"), WET,
    "https://api.sejm.gov.pl/eli/acts/DU/2024/1638", _VERIFIED,
    note="Structured in three levels: lettered parts A to D by employer type (municipal, "
         "county, regional, and other units), then within part D twenty-four numbered "
         "subsections by kind of unit, then within each a band of stanowiska kierownicze "
         "urzędnicze, stanowiska urzędnicze, and stanowiska pomocnicze i obsługi. That "
         "band is itself worth encoding — it is a statutory supervisory / professional / "
         "support split, which is exactly the kind of level a job architecture needs and "
         "which most markets leave to the employer to invent.")

PACK = CountryPack(
    country="PL",
    name="Poland",
    currency="PLN",
    languages=("pl",),
    status=DRAFT,
    vocabulary=VOCABULARY,
    gender_codes=GENDER_CODES,
    pay_components=PAY_COMPONENTS,
    reporting=REPORTING,
    crosswalks=(SAMORZAD,),
    org_structure=ORG_STRUCTURE,
    performance=PERFORMANCE,
    job_architecture=JOB_ARCHITECTURE,
    skills=SKILLS,
    compensation=COMPENSATION,
    notes=(
        "CURRENCY: PLN, the first non-euro pack. Raw zloty beside raw euro is the most "
        "dangerous mistake available here and it fails SILENTLY, because 4806 is a "
        "plausible salary in either unit. Beyond the unit, Dutch hourly labour costs run "
        "roughly 2,2 times Polish ones (NL 47,9 EUR against PL about 22, EU-27 34,9), so "
        "even correctly converted, country belongs in the model as a STRATUM rather than "
        "a covariate. This is what the measured 27% pooled gap was made of.",

        "FTE IS TWO INTEGER COLUMNS. Poland's most deployed payroll system stores the "
        "working-time fraction as Licznik_wymiaru_etatu and Mianownik_wymiaru_etatu — 1 "
        "and 2 for a half-timer — and holds no FTE number at all. A parser looking for "
        "Etat finds nothing; one grabbing a single column reads 1 for a half-timer or 2 "
        "for a full-timer's denominator, raises no exception, and puts the error on "
        "part-time staff, who skew female. The statutory GUS return by contrast wants a "
        "comma-decimal to three places, so the conversion between the two is where this "
        "breaks.",

        "SALARY IS A RATE PLUS A RATE-TYPE. Stawka must be read with Rodzaj_stawki "
        "(1 monthly, 2 hourly, 0 no contract); reading Stawka alone silently mixes "
        "monthly and hourly figures in one column.",

        "DO NOT MAP `Stawka zaszeregowania` TO LEVEL. It looks like a grade and is a "
        "zloty amount — mapping it puts the dependent variable on both sides of the "
        "regression. The vendor has no kategoria zaszeregowania field at all; its only "
        "hierarchy field is free-text Stanowisko.",

        "THRESHOLDS COUNT PER PRACODAWCA, WHICH IS NOT THE LEGAL ENTITY. KP art. 3 "
        "defines the employer as an organisational unit, so a branch or plant employing "
        "workers is itself the employer. A 300-person company organised as four units "
        "can sit below every 50-employee threshold. This is the item most likely to be "
        "silently wrong in a design that assumes per-entity counting — and it is a third "
        "distinct answer, after Germany's Betrieb and Spain's empresa.",

        "EQUAL VALUE NAMES THREE FACTORS, NOT FOUR. Art. 18(3c) para 3 compares "
        "qualifications, responsibility and effort. WORKING CONDITIONS ARE ABSENT, "
        "unlike the directive's Art. 4(4), so a Dutch-calibrated equal-value engine is "
        "testing a slightly different statutory question here.",

        "PREMIA IS NOT NAGRODA, and the label does not decide it. A nagroda is "
        "discretionary with no claim to payment; a premia regulaminowa is enforceable. "
        "Keep them as separate variables, because the discretionary component is where "
        "unexplained gap concentrates. But PIP's own doctrine is that a premia uznaniowa "
        "paid systematically is legally a premia, so classification cannot come from the "
        "column name.",

        "THREE PLAUSIBLE HIRE DATES exist side by side — data zatrudnienia, data "
        "zawarcia umowy, data rozpoczecia pracy — so seniority differs by which one is "
        "chosen, and the choice must be recorded.",

        "MINIMUM-WAGE MOVEMENT READS AS EQUITY IMPROVEMENT: up 37,7% in three years, "
        "with two steps within 2023 and again within 2024.",

        "GUS Z-12 IS NOT PAY REPORTING. It is a statistical transmission duty under the "
        "public statistics act, biennial, on EVEN reference years filed in ODD years, "
        "drawn from a sample of roughly 15% of the 10+ employee population and as few as "
        "one employee in fourteen inside a drawn firm. Statistical secrecy forbids GUS "
        "passing a return to PIP or a claimant, and nothing requires the employer to "
        "compute a gap, compare sexes, explain, remedy or tell anyone. Calling it pay "
        "reporting is a category error.",

        "THE MEASURED POPULATION IS INCOMPLETE, AND THE DIRECTION OF THE BIAS IS "
        "UNKNOWN. About 1,5 million people work exclusively on civil-law contracts, "
        "roughly 9% of the counted workforce and a hard floor; in IT the B2B share is far "
        "higher, so an employee-only analysis may see only 55-70% of the people doing the "
        "work at a Polish IT employer. NOBODY PUBLISHES THE SEX COMPOSITION OF THE B2B "
        "POPULATION. For a product whose whole claim is measuring a gender gap, that is "
        "the most uncomfortable finding in this pack and it must not be softened into "
        "'the effect is probably small'. It is unknown.",

        "NO PRIVATE-SECTOR CROSSWALK EXISTS, and this is confirmed rather than missing: "
        "bargaining coverage is 11,6%, at company level, with no extension mechanism. "
        "The collective-agreements title of the Kodeks pracy was repealed in December "
        "2025 and its replacement register KEUZP is not due until 13 December 2027, so "
        "there is not even a way to look up whether an employer is covered. From about "
        "2028 that register will publish coverage headcount BROKEN DOWN BY SEX, which "
        "will be Poland's first public sex-disaggregated coverage dataset.",

        "NOT CONFIRMED: the exact Eurostat hourly labour cost for Poland (reads of 21,8 "
        "and 22,2, almost certainly whole-economy against business-economy), so the ~22 "
        "figure above must not be printed to one decimal; why Poland's headline gap is "
        "low, which GUS itself declines to explain; the thresholds and penalties in the "
        "UC127 draft; whether a Polish implementation will treat the social fund as pay; "
        "and payroll conventions for any vendor other than the one cited.",

        "DRAFT rather than LIVE: LIVE means a person checked, and so far only an agent "
        "has.",
    ),
)

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

from . import (CONVENTIE, DRAFT, ONBEVESTIGD, UITLEG, WET, Claim, CountryPack,
               CrosswalkSpec, PayReporting, ReportingBand)

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
         "build to it.")

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

SAMORZAD = CrosswalkSpec(
    system="Samorządowe kategorie zaszeregowania (rozporządzenie RM)",
    publishes_point_table=False,
    groups=tuple(str(i) for i in range(1, 21)),   # categories I-XX
    point_bands=(),
    scales={"1": (4806.0, 4806.0), "20": (6750.0, 6750.0)},
    sectors=("Administracja samorządowa",),
    source=Claim("20 categories I-XX with minimum monthly amounts, plus a named-position "
                 "to minimum-category table", WET,
                 "https://api.sejm.gov.pl/eli/acts/DU/2026/246", _VERIFIED,
                 note="Local-government pay, annex updated from 1 January 2026. Category "
                      "I is 4.806 zloty, which is exactly the national minimum wage, and "
                      "category XX is 6.750. The regulation also maps named positions to "
                      "a minimum category, required education and required years of "
                      "service across roughly two dozen unit types, so this is a genuine "
                      "encodable crosswalk. Only the two endpoint scales are held; the "
                      "intermediate categories must be read from the annex before any "
                      "per-category figure is shown. It is amended roughly annually, so "
                      "version-date anything derived from it."),
)

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

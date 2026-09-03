"""
jobsy/services/cao_crosswalk_service.py

Crosswalks Jobsy's OWN independent grading (grade, level, job description,
skill class/family -- never a reproduced third-party scoring method) onto
PUBLIC CAO salary-group structures. Full verification trail and the IP/
honesty boundary this design follows: docs/cao-metalektro-isf-reference.md.

Two systems, two different public shapes -- this matters for what's honest
to show:

  * ISF (Metalektro, systeemhouder FME): publishes a numeric point-BOUNDARY
    table (A-Q) even though the scoring method that produces a job's point
    total is protected IP. We rank-position Jobsy's own grade onto that
    published boundary sequence -- an indicative crosswalk, never a
    fabricated "ISF-puntenscore" for the job itself.
  * CATS (De Leeuw Consult; Metaal en Techniek, Grafimedia, and other sector
    CAOs each with their own table): has NO public point-boundary table at
    all. Classification is a qualitative comparison against ~95
    "functiefamilies", each with its own niveaublad. All that's honest to
    show is the functiegroep-to-salarisgroep LABEL alignment, with no
    implied point score and no pretence that a number backs it.

Job descriptions and skill class/family are NOT inputs to a scoring formula
here (that would risk re-deriving the protected method) -- they're surfaced
as context alongside the crosswalk so a human reviewer can sanity-check
whether the indicative position looks right for what the job actually is.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── ISF: verified 2026-07-21 against the primary FNV CAO texts ──────────────
# (docs/cao-metalektro-isf-reference.md has the exact page citations)
ISF_BANDS: list[tuple[str, int, int]] = [
    ("A", 0, 130), ("B", 131, 180), ("C", 181, 230), ("D", 231, 280),
    ("E", 281, 330), ("F", 331, 380), ("G", 381, 430), ("H", 431, 480),
    ("J", 481, 535), ("K", 536, 590),
    ("L", 591, 645), ("M", 646, 700), ("N", 701, 760), ("O", 761, 820),
    ("P", 821, 880), ("Q", 881, 940),
]
_HP_LETTERS = {"L", "M", "N", "O", "P", "Q"}

# 2026 monthly base salary, step 0 (min) and max step -- Basis groups A-K only.
# Hoger Personeel (L-Q) isn't a rigid step table (see the reference doc).
ISF_MONTHLY_SCALES_2026: dict[str, tuple[float, float]] = {
    "A": (2768.86, 2803.01), "B": (2809.65, 2897.15), "C": (2869.64, 3030.46),
    "D": (2954.58, 3195.36), "E": (3057.10, 3398.63), "F": (3178.77, 3637.77),
    "G": (3318.71, 3922.71), "H": (3487.83, 4255.92), "J": (3702.73, 4655.03),
    "K": (3950.20, 5121.58),
}
ISF_HP_INCOME_CAP_2026 = 131_256.0
ISF_HP_ANNUALISE_MULTIPLIER = 12.96  # monthly base x this ~= gross annual incl. holiday allowance

# ── CATS: researched 2026-07-21 -- label alignment ONLY, no public point table exists ──
# functiegroep -> salarisgroep, per sector CAO handbook (each sector publishes
# its own table). Add more sectors here only once sourced the same way.
CATS_FUNCTIEGROEP_TO_SALARISGROEP: dict[str, dict[int, str]] = {
    "Metaal en Techniek": {
        2: "A", 3: "B", 4: "C", 5: "D", 6: "E",
        7: "F", 8: "G", 9: "H", 10: "I", 11: "J",
    },
}


@dataclass(frozen=True)
class IsfCrosswalkResult:
    salarisgroep: str
    isf_point_range: tuple[int, int]
    monthly_scale: tuple[float, float] | None  # None for L-Q (no rigid step table)
    is_hoger_personeel: bool
    rank_fraction: float          # 0-1: this job's position in the org's own grade range
    note: str
    basis: str = "grade rank"     # "grade rank" | "own point range"


@dataclass(frozen=True)
class CatsCrosswalkResult:
    sector: str
    functiegroep: int | None
    salarisgroep: str | None
    rank_fraction: float | None
    note: str
    basis: str = "grade rank"


def _position(job_grade: float, grade_min: float, grade_max: float,
              points: float | None, points_min: float | None,
              points_max: float | None) -> tuple[float, str] | None:
    """Where this job sits on the org's own ladder, 0 to 1, and on what basis.

    THE LINE THIS FUNCTION EXISTS TO HOLD. JobGrades carries a point range per
    grade — Jobsy's own scale, 100 to 1800. ISF publishes point BOUNDARIES,
    0 to 940. Both are called points and they are not the same quantity: the
    scoring method that produces an ISF total is protected, so a job's own
    point figure is not an ISF figure and must never be looked up in the ISF
    table. A grade at 405 of our points is not "ISF group G because 405 falls
    in 381-430".

    What the points ARE good for is spacing. Ranking by grade number assumes
    every rung is the same distance from the next; the point ranges say they
    are not — grade 3 spans 35 points and grade 14 spans 530. So points give a
    truer POSITION on our own ladder, and that proportion is what gets carried
    across to the public sequence, exactly as the grade rank was before.
    """
    if points is not None and points_min is not None and points_max is not None             and points_max > points_min:
        return (max(0.0, min(1.0, (points - points_min) / (points_max - points_min))),
                "own point range")
    if grade_max <= grade_min:
        return None
    return (max(0.0, min(1.0, (job_grade - grade_min) / (grade_max - grade_min))),
            "grade rank")


def crosswalk_to_isf(job_grade: float, grade_min: float, grade_max: float,
                     *, points: float | None = None,
                     points_min: float | None = None,
                     points_max: float | None = None) -> IsfCrosswalkResult | None:
    """
    Positions Jobsy's OWN grade proportionally onto the PUBLIC ISF
    salary-group sequence -- never computes a fake ISF point score for the
    job itself. grade_min/grade_max should span the full grade range
    actually in use (e.g. from the org's JobGrade ladder), so the rank
    position is meaningful rather than arbitrary to whatever subset of rows
    happens to be loaded.
    """
    placed = _position(job_grade, grade_min, grade_max, points, points_min, points_max)
    if placed is None:
        return None
    frac, basis = placed
    idx = round(frac * (len(ISF_BANDS) - 1))
    letter, lo, hi = ISF_BANDS[idx]
    is_hp = letter in _HP_LETTERS
    scale = None if is_hp else ISF_MONTHLY_SCALES_2026.get(letter)
    return IsfCrosswalkResult(
        salarisgroep=letter, isf_point_range=(lo, hi), monthly_scale=scale,
        is_hoger_personeel=is_hp, rank_fraction=round(frac, 3), basis=basis,
        note=(f"Indicatief: salarisgroep {letter} — officiële ISF-indeling vereist een "
              f"gecertificeerde weging. Dit positioneert Jobsy's eigen gradering binnen de "
              f"publieke ISF-bandbreedtes; het is geen berekende ISF-score."
              + (" De positie volgt Jobsy's eigen puntenbereik per graad — een eigen schaal "
                 "(100–1800), niet de ISF-puntenschaal en er niet in opgezocht."
                 if basis == "own point range" else
                 " De positie volgt de rangorde van de graad; het puntenbereik per graad is "
                 "niet meegegeven.")),
    )


def crosswalk_to_cats(
    job_grade: float, grade_min: float, grade_max: float, sector: str = "Metaal en Techniek",
    *, points: float | None = None, points_min: float | None = None,
    points_max: float | None = None,
) -> CatsCrosswalkResult:
    """
    Label alignment only. CATS has no public point-boundary table (see
    module docstring), so there is nothing to rank-position a job's points
    against the way ISF allows -- this only positions the grade ordinally
    onto the sector's published functiegroep sequence and reads off the
    label, with no implied score.
    """
    table = CATS_FUNCTIEGROEP_TO_SALARISGROEP.get(sector)
    if not table:
        return CatsCrosswalkResult(sector=sector, functiegroep=None, salarisgroep=None, rank_fraction=None,
                                    note=f"No public functiegroep/salarisgroep table on file for '{sector}' yet.")
    placed = _position(job_grade, grade_min, grade_max, points, points_min, points_max)
    if placed is None:
        return CatsCrosswalkResult(sector=sector, functiegroep=None, salarisgroep=None, rank_fraction=None,
                                    note="Grade range too narrow to position (grade_max <= grade_min).")
    frac, basis = placed
    fgs = sorted(table.keys())
    idx = round(frac * (len(fgs) - 1))
    fg = fgs[idx]
    return CatsCrosswalkResult(
        sector=sector, functiegroep=fg, salarisgroep=table[fg], rank_fraction=round(frac, 3), basis=basis,
        note=("Label alignment only — CATS® has no public point-range table to position "
              "against (unlike ISF). Official classification requires reading the sector's "
              "niveaublad for the relevant functiefamilie, done by a certified CATS® user."),
    )


def known_cats_sectors() -> list[str]:
    return sorted(CATS_FUNCTIEGROEP_TO_SALARISGROEP.keys())

# ── the indicator ──────────────────────────────────────────────────────────
#
# OUR GRADE IS THE ANSWER. It is our own independent, gender-neutral system and
# it is what a client is classified on. ISF is an INDICATOR beside it — useful
# for the conversation "where would this sit in the sector CAO", never the
# classification itself, which needs a certified weging nobody here can perform.
#
# So this does not pick a basis and present one letter. It reports the letter
# each basis gives, whether they agree, how much of our pay range actually
# falls inside that group's published scale, and whether the job is inside the
# published table at all.
#
# THE ONLY PERCENTAGE HERE IS A MEASUREMENT. Pay overlap is computable from two
# published figures and can be checked by anyone. There is deliberately no
# blended "confidence score": averaging an agreement flag, an overlap and a
# scope into one number would manufacture a precision none of the three has,
# and it is exactly the kind of figure that survives into a slide unchallenged.


@dataclass(frozen=True)
class IsfIndicator:
    """Our grade, with an ISF reading beside it and the quality of that reading."""
    our_grade: float
    our_pay: tuple[float, float] | None

    group_by_rank: str | None
    group_by_points: str | None
    bases_agree: bool | None          # None when only one basis was available

    indicated_group: str | None       # the letter to show, or None when out of scope
    published_scale: tuple[float, float] | None   # annualised, A-K only
    pay_overlap_pct: float | None     # share of OUR range inside that scale
    overlap_reason: str               # why the overlap is None, when it is

    scope: str                        # "published table" | "hoger personeel" | "above the cap"
    summary: str

    @property
    def is_indicative_only(self) -> bool:
        return True                   # always. There is no certified weging here.


def _annualised(letter: str) -> tuple[float, float] | None:
    scale = ISF_MONTHLY_SCALES_2026.get(letter)
    if not scale:
        return None
    return (scale[0] * ISF_HP_ANNUALISE_MULTIPLIER, scale[1] * ISF_HP_ANNUALISE_MULTIPLIER)


def _overlap_pct(ours: tuple[float, float], theirs: tuple[float, float]) -> float:
    """How much of OUR pay range falls inside THEIR published scale.

    Deliberately asymmetric: the question a client asks is "how much of what we
    pay is covered by this group", not the reverse. 0.0 is a real answer and
    means the ranges touch at most at a point.
    """
    lo, hi = ours
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        # A single salary, not a range — one person in the cohort, or everyone
        # paid the same. It is wholly inside the scale or wholly outside; 0%
        # for a value that sits squarely in the band would be a measurement
        # artefact reported as a finding.
        return 100.0 if theirs[0] <= lo <= theirs[1] else 0.0
    inter = max(0.0, min(hi, theirs[1]) - max(lo, theirs[0]))
    return round(inter / (hi - lo) * 100, 1)


def isf_indicator(our_grade: float, grade_min: float, grade_max: float, *,
                  our_pay: tuple[float, float] | None = None,
                  points: float | None = None,
                  points_min: float | None = None,
                  points_max: float | None = None) -> IsfIndicator:
    """Our grade first; ISF beside it, with the quality of the reading stated."""
    by_rank = crosswalk_to_isf(our_grade, grade_min, grade_max)
    by_points = (crosswalk_to_isf(our_grade, grade_min, grade_max, points=points,
                                  points_min=points_min, points_max=points_max)
                 if points is not None and points_min is not None and points_max is not None
                 else None)

    g_rank = by_rank.salarisgroep if by_rank else None
    g_pts = by_points.salarisgroep if (by_points and by_points.basis == "own point range") else None
    agree = None if g_pts is None else (g_rank == g_pts)
    indicated = g_rank

    scope = "published table"
    scale = _annualised(indicated) if indicated else None
    overlap: float | None = None
    reason = ""

    if indicated and indicated in _HP_LETTERS:
        scope = "hoger personeel"
        reason = ("Hoger Personeel has no rigid step table in the CAO, so there is no published "
                  "scale to measure a pay overlap against.")
    elif scale is None:
        reason = "No published scale on file for that group."
    elif our_pay is None:
        reason = "No pay range supplied for this job, so the overlap cannot be measured."
    else:
        overlap = _overlap_pct(our_pay, scale)

    if our_pay and our_pay[0] > ISF_HP_INCOME_CAP_2026:
        scope = "above the cap"
        indicated = None
        overlap, scale = None, None
        reason = (f"This pay range starts above the Hoger Personeel income cap "
                  f"(€{ISF_HP_INCOME_CAP_2026:,.0f}), so the ISF structure does not reach it. "
                  f"No salarisgroep is indicated — that is the honest answer, not group Q.")

    # The summary names each measured part. It never blends them.
    bits = [f"Grade {our_grade:g} — our own classification"]
    if indicated:
        bits.append(f"indicatief ISF {indicated}")
        if agree is False:
            bits.append(f"the two bases differ ({g_rank} by rank, {g_pts} by points)")
        elif agree is True:
            bits.append("both bases agree")
        if overlap is not None:
            bits.append(f"{overlap:g}% of our pay range falls inside that group's published scale")
        elif reason:
            bits.append(reason.rstrip("."))
    else:
        bits.append(reason.rstrip("."))
    return IsfIndicator(
        our_grade=our_grade, our_pay=our_pay,
        group_by_rank=g_rank, group_by_points=g_pts, bases_agree=agree,
        indicated_group=indicated, published_scale=scale,
        pay_overlap_pct=overlap, overlap_reason=reason,
        scope=scope, summary=" · ".join(bits),
    )

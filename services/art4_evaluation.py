"""
art4_evaluation.py — the four-factor scoring engine, and what it refuses to do.

Art. 4 of Directive (EU) 2023/970 requires pay structures built on a
gender-neutral job evaluation across four factors: skills, effort,
responsibility, working conditions. It does not require ISF or CATS; any system
meeting the standard qualifies, which is why Jobsy's own instrument can be the
system for clients not bound by a CAO-mandated one.

NOT WIRED TO ANY PAGE, ON PURPOSE. No role has been rated yet — all four rating
columns in projects/art4-job-evaluation/scoring are empty — and no weighting has
been decided. Wiring an unvalidated evaluation into a product that prints pay
findings would be worse than not having one. The dependency map will report this
module as reached by nothing; that is the correct signal, not an oversight.

THREE REFUSALS, AND THEY ARE THE POINT

1. **It does not score a role it has not been told about.** A role missing any
   of the four degrees is returned as unrated, naming which factors are absent.
   Effort and working conditions have no structural evidence anywhere in the
   library — the white-collar reference set never needed them — so today that is
   every role. Filling them with a default would produce a complete-looking
   instrument built on two invented factors.

2. **It cannot be fitted to the existing ladder.** There is deliberately no
   calibrate() or fit() here, and a test asserts none appears. If the weighting
   were tuned until the scores reproduced the current grades, the instrument
   would launder the status quo through a scorecard and certify nothing. The
   grades are the hypothesis under test.

3. **It does not choose the weights.** They are an input. Which factor counts for
   how much is the decision Art. 4(4) makes consequential — overweighting
   factors that track male-dominated work is the documented failure mode — and it
   is a decision that has to be made by a person who can then justify it in
   writing.

WHAT IT DOES GIVE YOU: a score, a ranking, a reconciliation against the current
ladder where mismatches are findings rather than errors, and a sensitivity view
showing which weighting choices actually change anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

__all__ = ["FACTORS", "Degrees", "Weights", "Evaluation", "Mismatch",
           "Rationale", "Weighting", "FactorSeparation",
           "evaluate", "reconcile", "sensitivity", "equal_weights",
           "separation", "factor_influence"]

FACTORS = ("skills", "effort", "responsibility", "working_conditions")

#: The degree scale from instrument/factor-degrees.md. Six, because the ladder
#: spans intern to C-suite: fewer cannot separate the middle, more invites false
#: precision.
MIN_DEGREE, MAX_DEGREE = 1, 6


@dataclass(frozen=True)
class Degrees:
    """One role's rating. None means not rated — never a zero, never a default."""
    skills: Optional[int] = None
    effort: Optional[int] = None
    responsibility: Optional[int] = None
    working_conditions: Optional[int] = None

    def missing(self) -> list[str]:
        return [f for f in FACTORS if getattr(self, f) is None]

    def out_of_range(self) -> list[str]:
        bad = []
        for f in FACTORS:
            v = getattr(self, f)
            if v is not None and not (MIN_DEGREE <= v <= MAX_DEGREE):
                bad.append(f)
        return bad


@dataclass(frozen=True)
class Weights:
    """How much each factor counts. Supplied, never derived."""
    skills: float
    effort: float
    responsibility: float
    working_conditions: float

    def __post_init__(self):
        for f in FACTORS:
            if getattr(self, f) < 0:
                raise ValueError(f"{f} weight is negative")
        if self.total() <= 0:
            raise ValueError("weights sum to zero — nothing would be measured")

    def total(self) -> float:
        return sum(getattr(self, f) for f in FACTORS)

    def normalised(self) -> "Weights":
        t = self.total()
        return Weights(**{f: getattr(self, f) / t for f in FACTORS})

    def as_percentages(self) -> dict[str, float]:
        n = self.normalised()
        return {f: round(getattr(n, f) * 100, 1) for f in FACTORS}


def equal_weights() -> Weights:
    """25% each. A starting point for a conversation, NOT a recommendation.

    Equal weighting is a decision like any other: it says a degree of working
    conditions is worth exactly a degree of skills. That may be defensible and it
    is not neutral, because nothing is.
    """
    return Weights(0.25, 0.25, 0.25, 0.25)


@dataclass
class Evaluation:
    job_id: str
    degrees: Degrees
    score: Optional[float] = None
    rank: Optional[int] = None
    missing: list[str] = field(default_factory=list)

    @property
    def rated(self) -> bool:
        return self.score is not None


def evaluate(roles: Mapping[str, Degrees], weights: Weights) -> list[Evaluation]:
    """Score and rank every fully rated role; report the rest as unrated.

    Ranking is dense and highest-score-first: two roles with the same score hold
    the same rank, because a job evaluation that separates equal work by a tie
    break is doing the opposite of its job.
    """
    w = weights.normalised()
    out: list[Evaluation] = []
    for job_id, d in roles.items():
        bad = d.out_of_range()
        if bad:
            raise ValueError(f"{job_id}: degree outside 1–6 for {', '.join(bad)}")
        missing = d.missing()
        if missing:
            out.append(Evaluation(job_id=job_id, degrees=d, missing=missing))
            continue
        score = sum(getattr(d, f) * getattr(w, f) for f in FACTORS)
        out.append(Evaluation(job_id=job_id, degrees=d, score=round(score, 4)))

    scored = sorted([e for e in out if e.rated], key=lambda e: -e.score)
    rank, prev = 0, None
    for i, e in enumerate(scored):
        if e.score != prev:
            rank, prev = i + 1, e.score
        e.rank = rank
    return out


@dataclass(frozen=True)
class Mismatch:
    job_id: str
    score_rank: int
    current_grade: int
    grade_rank: int
    delta: int          # positive: the evaluation places it HIGHER than the ladder does

    @property
    def direction(self) -> str:
        return "under-graded today" if self.delta > 0 else "over-graded today"


def reconcile(evaluations: Iterable[Evaluation],
              current_grades: Mapping[str, int]) -> list[Mismatch]:
    """Score-derived order against the ladder in use. Mismatches are FINDINGS.

    This runs after scoring and never before it. The existing grades do not enter
    the scoring sheet at all — that separation is the whole circularity guard: a
    role the evaluation puts at rank 30 while the ladder calls it grade 12 is
    precisely what the instrument exists to surface, not a bug in the scoring.
    """
    rated = [e for e in evaluations if e.rated and e.job_id in current_grades]
    if not rated:
        return []

    # The ladder as a ranking, so two orderings can be compared without
    # pretending a grade number and a score are the same quantity.
    by_grade = sorted(rated, key=lambda e: -current_grades[e.job_id])
    grade_rank: dict[str, int] = {}
    rank, prev = 0, None
    for i, e in enumerate(by_grade):
        g = current_grades[e.job_id]
        if g != prev:
            rank, prev = i + 1, g
        grade_rank[e.job_id] = rank

    out = []
    for e in rated:
        gr = grade_rank[e.job_id]
        if gr != e.rank:
            out.append(Mismatch(job_id=e.job_id, score_rank=e.rank,
                                current_grade=current_grades[e.job_id],
                                grade_rank=gr, delta=gr - e.rank))
    return sorted(out, key=lambda m: -abs(m.delta))


def sensitivity(roles: Mapping[str, Degrees],
                options: Mapping[str, Weights]) -> dict[str, dict[str, Optional[int]]]:
    """Each role's rank under each candidate weighting.

    The point of a weighting session is to see which choices change anything. A
    factor whose weight can move from 10% to 40% without reordering a single
    role is not carrying the decision people think it is.
    """
    ranks: dict[str, dict[str, Optional[int]]] = {}
    for name, w in options.items():
        for e in evaluate(roles, w):
            ranks.setdefault(e.job_id, {})[name] = e.rank
    return ranks


def roles_moved(sens: Mapping[str, Mapping[str, Optional[int]]]) -> int:
    """How many roles change rank across the candidate weightings at all."""
    moved = 0
    for _job, by_option in sens.items():
        seen = {r for r in by_option.values() if r is not None}
        if len(seen) > 1:
            moved += 1
    return moved


# ── a weight cannot exist without its reason ────────────────────────────────
#
# Recital 26: "each of the four factors should be weighed by the employer
# depending on the relevance of those criteria for the specific job or position
# concerned." So the number is the employer's, and it is bounded — it has to
# follow relevance, which means somebody has to be able to say why.
#
# Art. 4(4) adds two things a number alone cannot carry: the criteria must be
# "agreed with workers' representatives where such representatives exist", and
# they must not discriminate directly or indirectly. Both are properties of a
# DECISION, not of a float, so the decision is what gets recorded.
#
# Weights stay usable bare, because exploring a weighting you have not yet
# justified is exactly what a sensitivity run is for. What cannot happen quietly
# is adopting one.


@dataclass(frozen=True)
class Rationale:
    """Why this factor carries this weight, in the two terms the law uses."""
    relevance: str        # recital 26 — relevance to the jobs being evaluated
    neutrality: str       # Art. 4(4) — why this does not disadvantage indirectly

    def complete(self) -> bool:
        return bool(self.relevance.strip()) and bool(self.neutrality.strip())


@dataclass(frozen=True)
class Weighting:
    """A weighting as a decision: the numbers, the reasons, and who agreed.

    `agreed_with` is free text naming the workers' representatives who agreed
    the criteria. `no_representatives_exist` is the other lawful state, and it
    has to be asserted rather than inferred from an empty string — silence is
    not the same as "there is nobody to ask", and only one of those is a defence.
    """
    weights: Weights
    rationale: Mapping[str, Rationale] = field(default_factory=dict)
    agreed_with: str = ""
    agreed_on: Optional[str] = None          # ISO date
    no_representatives_exist: bool = False

    def unjustified(self) -> list[str]:
        out = []
        for f in FACTORS:
            r = self.rationale.get(f)
            if r is None or not r.complete():
                out.append(f)
        return out

    def blockers(self) -> list[str]:
        """Everything standing between this weighting and being adoptable."""
        why = []
        missing = self.unjustified()
        if missing:
            why.append("no relevance and neutrality note for: " + ", ".join(missing))
        if not self.agreed_with and not self.no_representatives_exist:
            why.append("Art. 4(4) requires the criteria to be agreed with workers' "
                       "representatives where such representatives exist — record the "
                       "agreement, or state that there are none")
        if self.agreed_with and not self.agreed_on:
            why.append("agreement recorded without a date")
        return why

    @property
    def adoptable(self) -> bool:
        return not self.blockers()


# ── a factor that separates nobody ──────────────────────────────────────────


@dataclass(frozen=True)
class FactorSeparation:
    factor: str
    n_rated: int
    degrees_used: tuple[int, ...]
    note: str

    @property
    def separates(self) -> bool:
        return len(self.degrees_used) > 1


def separation(roles: Mapping[str, Degrees]) -> dict[str, FactorSeparation]:
    """Which factors actually distinguish the roles from one another.

    A factor on which every role scores the same degree contributes an identical
    amount to every total. Its weight then cannot change any ranking — not
    "barely", not "a little": mathematically cannot, at any weight from 1% to
    99%. Arguing about it is arguing about nothing, and worse, the argument
    looks like diligence.

    That is the measurable form of recital 26's "not all factors are equally
    relevant", and it belongs in the neutrality justification as evidence
    instead of an assertion about the population.
    """
    out: dict[str, FactorSeparation] = {}
    for f in FACTORS:
        vals = [getattr(d, f) for d in roles.values() if getattr(d, f) is not None]
        used = tuple(sorted(set(vals)))
        if not vals:
            note = "no role is rated on this factor, so it distinguishes nothing yet"
        elif len(used) == 1:
            note = (f"every rated role scores {used[0]} — this factor cannot change any "
                    f"ranking at any weight. Either the scale is wrong for this population, "
                    f"or the factor genuinely does not vary here and the weighting should "
                    f"say so out loud rather than carry a number that does nothing")
        else:
            note = f"{len(used)} distinct degrees in use — this factor separates roles"
        out[f] = FactorSeparation(factor=f, n_rated=len(vals), degrees_used=used, note=note)
    return out


def factor_influence(roles: Mapping[str, Degrees], weights: Weights, factor: str,
                     low: float = 0.05, high: float = 0.45) -> dict:
    """Does moving one factor's weight across a range reorder anything?

    The empirical companion to separation(): a factor may vary across roles and
    still not move the ranking, because the other three already order them the
    same way. Reported as a count of roles whose rank changes, so "this factor
    is carrying the decision" stops being something anyone has to take on faith.
    """
    if factor not in FACTORS:
        raise ValueError(f"unknown factor {factor!r}")

    def _with(value: float) -> Weights:
        kw = {f: getattr(weights, f) for f in FACTORS}
        kw[factor] = value
        return Weights(**kw)

    sens = sensitivity(roles, {"low": _with(low), "high": _with(high)})
    moved = [job for job, by in sens.items()
             if len({r for r in by.values() if r is not None}) > 1]
    return {"factor": factor, "low": low, "high": high,
            "roles_moved": len(moved), "moved": sorted(moved),
            "note": (f"moving {factor} from {low:.0%} to {high:.0%} reorders "
                     f"{len(moved)} role(s)")}

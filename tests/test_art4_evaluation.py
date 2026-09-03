"""
The four-factor engine, and the three things it refuses to do.

Most of these test a refusal rather than a computation. That is deliberate: the
failure modes of a job-evaluation instrument are not arithmetic errors, they are
an instrument that looks complete while resting on invented ratings, or one
quietly fitted to the ladder it was supposed to test.
"""

import pytest

from services.art4_evaluation import (
    FACTORS, Degrees, Evaluation, Weights, equal_weights, evaluate, reconcile,
    roles_moved, sensitivity,
)


def _rated(s, e, r, w):
    return Degrees(skills=s, effort=e, responsibility=r, working_conditions=w)


# ── refusal 1: it does not score what it has not been told ───────────────────

def test_an_unrated_factor_makes_the_role_unrated_not_zero():
    out = evaluate({"J-1": Degrees(skills=4, responsibility=3)}, equal_weights())
    assert out[0].score is None
    assert out[0].missing == ["effort", "working_conditions"]


def test_todays_library_would_be_entirely_unrated():
    """Effort and working conditions have no structural evidence anywhere in the
    reference library, so a real run today rates nothing. An instrument that
    filled them with a default would look finished and measure two fictions."""
    roles = {f"J-{i}": Degrees(skills=3, responsibility=3) for i in range(5)}
    out = evaluate(roles, equal_weights())
    assert all(not e.rated for e in out)
    assert all(set(e.missing) == {"effort", "working_conditions"} for e in out)


def test_a_degree_outside_the_scale_is_refused_loudly():
    with pytest.raises(ValueError, match="outside 1"):
        evaluate({"J-1": _rated(7, 3, 3, 1)}, equal_weights())


# ── refusal 2: it cannot be fitted to the ladder ─────────────────────────────

def test_there_is_no_way_to_fit_the_weights_to_the_existing_grades():
    """If the weighting could be tuned until the scores reproduced the current
    ladder, the instrument would launder the status quo through a scorecard."""
    import services.art4_evaluation as m
    assert not [n for n in dir(m) if n.startswith(("fit", "calibrate", "tune", "solve"))]


def test_reconcile_runs_after_scoring_and_never_feeds_it():
    """The grades reach reconcile() and nothing else. evaluate() takes degrees
    and weights — there is no parameter through which a grade could enter."""
    import inspect
    sig = inspect.signature(evaluate)
    assert "grade" not in " ".join(sig.parameters)


# ── refusal 3: it does not choose the weights ────────────────────────────────

def test_weights_are_an_input_with_no_default():
    import inspect
    assert inspect.signature(evaluate).parameters["weights"].default is inspect.Parameter.empty


def test_equal_weights_is_offered_as_a_starting_point_not_a_recommendation():
    from services.art4_evaluation import equal_weights as ew
    assert "NOT a recommendation" in ew.__doc__
    assert ew().as_percentages() == {f: 25.0 for f in FACTORS}


def test_weights_that_measure_nothing_are_refused():
    with pytest.raises(ValueError, match="sum to zero"):
        Weights(0, 0, 0, 0)
    with pytest.raises(ValueError, match="negative"):
        Weights(-1, 1, 1, 1)


def test_weights_need_not_sum_to_one_and_are_normalised():
    w = Weights(2, 1, 1, 1).normalised()
    assert round(w.skills, 3) == 0.4
    assert Weights(2, 1, 1, 1).as_percentages()["skills"] == 40.0


# ── the computation itself ───────────────────────────────────────────────────

def test_the_score_is_the_weighted_sum_of_the_degrees():
    out = evaluate({"J-1": _rated(4, 2, 5, 1)}, Weights(0.4, 0.1, 0.4, 0.1))
    assert out[0].score == pytest.approx(4 * .4 + 2 * .1 + 5 * .4 + 1 * .1)


def test_equal_work_holds_equal_rank():
    """A job evaluation that separates identical work by a tie break is doing
    the opposite of its job."""
    out = evaluate({"A": _rated(3, 3, 3, 3), "B": _rated(3, 3, 3, 3),
                    "C": _rated(4, 4, 4, 4)}, equal_weights())
    by = {e.job_id: e.rank for e in out}
    assert by["C"] == 1 and by["A"] == by["B"] == 2


# ── the reconciliation, where mismatches are findings ────────────────────────

def test_a_role_the_ladder_and_the_evaluation_disagree_on_is_reported():
    roles = {"HIGH": _rated(6, 6, 6, 6), "LOW": _rated(1, 1, 1, 1)}
    out = evaluate(roles, equal_weights())
    # the ladder says the opposite of the evaluation
    ms = reconcile(out, {"HIGH": 2, "LOW": 12})
    assert {m.job_id for m in ms} == {"HIGH", "LOW"}
    high = next(m for m in ms if m.job_id == "HIGH")
    assert high.delta > 0 and high.direction == "under-graded today"


def test_agreement_produces_no_findings():
    roles = {"HIGH": _rated(6, 6, 6, 6), "LOW": _rated(1, 1, 1, 1)}
    out = evaluate(roles, equal_weights())
    assert reconcile(out, {"HIGH": 12, "LOW": 2}) == []


def test_unrated_roles_are_left_out_of_the_reconciliation_entirely():
    out = evaluate({"A": Degrees(skills=3)}, equal_weights())
    assert reconcile(out, {"A": 5}) == []


# ── sensitivity: which choices actually change anything ──────────────────────

def test_sensitivity_shows_where_a_weighting_choice_matters():
    roles = {"CARE": _rated(3, 6, 3, 2), "TECH": _rated(6, 2, 3, 2)}
    sens = sensitivity(roles, {
        "equal": equal_weights(),
        "skills-heavy": Weights(0.55, 0.15, 0.20, 0.10),
        "effort-heavy": Weights(0.15, 0.55, 0.20, 0.10),
    })
    assert sens["CARE"]["effort-heavy"] == 1
    assert sens["CARE"]["skills-heavy"] == 2
    assert roles_moved(sens) == 2


def test_a_weight_that_reorders_nothing_is_visible_as_such():
    """A factor whose weight can move a long way without changing a single rank
    is not carrying the decision people think it is."""
    roles = {"A": _rated(5, 3, 3, 3), "B": _rated(2, 3, 3, 3)}
    sens = sensitivity(roles, {"low_wc": Weights(.4, .3, .29, .01),
                               "high_wc": Weights(.4, .3, .1, .2)})
    assert roles_moved(sens) == 0


# ── a weight cannot be adopted without its reason ────────────────────────────

from services.art4_evaluation import (
    FactorSeparation, Rationale, Weighting, factor_influence, separation,
)


def _full_rationale():
    return {f: Rationale(relevance=f"why {f} is relevant here",
                         neutrality=f"why weighting {f} this way disadvantages nobody")
            for f in FACTORS}


def test_a_bare_weighting_is_usable_for_exploration_but_not_adoptable():
    """Exploring a weighting you have not justified is exactly what a
    sensitivity run is for. Adopting one quietly is the thing to stop."""
    w = Weighting(weights=equal_weights())
    assert not w.adoptable
    assert w.unjustified() == list(FACTORS)


def test_every_factor_needs_both_a_relevance_and_a_neutrality_note():
    """Recital 26 asks why this weight; Art. 4(4) asks who it disadvantages.
    They are different questions and one does not answer the other."""
    half = {f: Rationale(relevance="relevant", neutrality="") for f in FACTORS}
    w = Weighting(weights=equal_weights(), rationale=half, no_representatives_exist=True)
    assert w.unjustified() == list(FACTORS)


def test_agreement_with_representatives_is_required_or_their_absence_asserted():
    w = Weighting(weights=equal_weights(), rationale=_full_rationale())
    assert any("agreed with workers" in b for b in w.blockers())


def test_silence_is_not_the_same_as_there_being_nobody_to_ask():
    """An empty agreed_with could mean 'no OR exists' or 'nobody asked'. Only one
    of those is a defence, so the lawful one has to be asserted."""
    w = Weighting(weights=equal_weights(), rationale=_full_rationale(),
                  no_representatives_exist=True)
    assert w.adoptable


def test_an_agreement_without_a_date_is_incomplete():
    w = Weighting(weights=equal_weights(), rationale=_full_rationale(),
                  agreed_with="OR Northwind BV")
    assert not w.adoptable
    assert any("without a date" in b for b in w.blockers())


def test_a_fully_recorded_weighting_is_adoptable():
    w = Weighting(weights=equal_weights(), rationale=_full_rationale(),
                  agreed_with="OR Northwind BV", agreed_on="2026-11-04")
    assert w.adoptable and w.blockers() == []


# ── a factor that separates nobody ───────────────────────────────────────────

def test_a_factor_every_role_scores_the_same_cannot_change_any_ranking():
    """Not 'barely' — mathematically cannot, at any weight. Arguing about it
    looks like diligence and is arguing about nothing."""
    roles = {"A": _rated(2, 3, 4, 1), "B": _rated(5, 3, 2, 1), "C": _rated(4, 3, 6, 1)}
    sep = separation(roles)
    assert not sep["working_conditions"].separates
    assert sep["working_conditions"].degrees_used == (1,)
    assert "cannot change any ranking" in sep["working_conditions"].note

    # and prove it: the weight can travel a long way and reorder nothing
    infl = factor_influence(roles, equal_weights(), "working_conditions")
    assert infl["roles_moved"] == 0


def test_a_factor_in_genuine_use_is_reported_as_separating():
    roles = {"A": _rated(2, 3, 4, 1), "B": _rated(5, 1, 2, 4)}
    sep = separation(roles)
    assert sep["skills"].separates
    assert "separates roles" in sep["skills"].note


def test_an_unrated_factor_says_it_distinguishes_nothing_YET():
    """Different from 'does not vary': one is a finding, the other is unfinished
    work, and reporting them the same way would hide 324 blank ratings."""
    roles = {"A": Degrees(skills=3, responsibility=2)}
    sep = separation(roles)
    assert sep["effort"].n_rated == 0
    assert "no role is rated" in sep["effort"].note
    assert sep["effort"].note.endswith("yet")        # unfinished, not a finding
    assert not sep["effort"].separates


def test_a_factor_can_vary_and_still_move_nothing():
    """The empirical companion: the other three already order the roles the same
    way, so this one varies without carrying the decision."""
    roles = {"A": _rated(6, 6, 6, 1), "B": _rated(2, 2, 2, 6)}
    infl = factor_influence(roles, Weights(.3, .3, .3, .1), "working_conditions",
                            low=0.02, high=0.10)
    assert infl["roles_moved"] == 0
    assert "reorders 0 role" in infl["note"]


def test_influence_on_an_unknown_factor_is_refused():
    with pytest.raises(ValueError, match="unknown factor"):
        factor_influence({}, equal_weights(), "charisma")

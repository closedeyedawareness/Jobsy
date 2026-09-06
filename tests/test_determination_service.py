"""
tests/test_determination_service.py

The judgement layer, first slice.

The product refuses to assert what it cannot know, and that is right and it is
half a product: the client still has to decide. `bridge()` already tells them so
on screen — an employer may adopt an internal equivalence, "marked CONVENTIE" —
and until now offered nowhere to record it. These tests hold the shape of that
record.

The gender-code case was chosen as the first slice because nothing new had to be
invented: the question is already asked, already answered by a person, and
already thrown away at the end of the session.
"""
from __future__ import annotations

import pytest

from services import determination_service as det


def _example(actor="elmar@example.com"):
    return det.gender_code_determination(
        country="ES", column="Sexo", codes=("m", "h"),
        female_value="M", male_value="H", population=120, actor=actor)


# ── the marker the packs reserved and never wrote ─────────────────────────

def test_a_determination_is_always_a_convention_and_never_a_fact():
    """CONVENTIE is not one option among four.

    The hardness vocabulary has WET for statute, UITLEG for a reading of it,
    ONBEVESTIGD for unverified — and CONVENTIE for an employer's own judgement.
    A determination is that by definition. Anything else would be this product
    asserting the client's decision as a fact about the world, which is the one
    thing the whole hardness model exists to prevent.

    The database enforces it too (a CHECK constraint), because a rule held only
    in Python is a rule a script can walk around.
    """
    row = _example().row("org-1", "someone")
    assert row["hardness"] == "CONVENTIE"


# ── the field the table earns its keep with ───────────────────────────────

def test_the_answer_says_what_it_may_not_be_used_for():
    """`excluded_uses` is the load-bearing column.

    "M means woman" is true of THIS file from THIS payroll export. It is not a
    fact about Spanish payroll, and applying it to another client's upload is
    exactly what a shared lookup table would quietly do — reintroducing, through
    the feature meant to complete the design, the error the refusal exists to
    prevent.
    """
    d = _example()
    joined = " ".join(d.excluded_uses).lower()
    assert d.excluded_uses, "a determination with no excluded uses is a fact wearing a decision's clothes"
    assert "other client" in joined
    assert "generally" in joined, "it must not be read as a claim about the market"


def test_the_question_carries_its_own_purpose():
    """Not "what does M mean" but "what does it mean FOR THIS UPLOAD".

    The same two values could be read one way for one file and another way for
    the next; a question without its purpose in it produces an answer that
    travels further than it should.
    """
    q = _example().question.lower()
    assert "this" in q and ("upload" in q or "file" in q)


# ── what the system showed, kept as it was ────────────────────────────────

def test_what_the_system_proposed_is_stored_rather_than_recomputed():
    """A dossier must show what the employer was looking at when they decided.

    If the engine improves later, recomputing would prove the decision
    reasonable against evidence that did not exist yet. Here the honest value is
    that the engine proposed NOTHING — it refused — and that refusal is itself
    the thing worth recording.
    """
    d = _example()
    assert d.system_proposed
    assert "refused" in d.system_proposed.lower()


def test_the_rejected_options_survive_alongside_the_chosen_one():
    d = _example()
    assert len(d.options) >= 2, "an option with no alternatives is not a decision"
    assert any("Mujer" in o["option"] for o in d.options), (
        "the option that removes the ambiguity at source is the one a client "
        "should be able to see they declined")


# ── evidence, not citation ────────────────────────────────────────────────

def test_evidence_is_hashed_so_it_can_be_proved_later():
    """A live URL does not prove in 2028 what a page said in 2026."""
    e = _example().evidence[0]
    assert e.excerpt and e.content_hash
    assert len(e.content_hash) == 64
    import hashlib
    assert e.content_hash == hashlib.sha256(e.excerpt.encode()).hexdigest()


def test_evidence_without_text_has_no_hash_rather_than_a_hash_of_nothing():
    """Hashing an empty excerpt would produce a real-looking hash of nothing —
    a record that claims to be provable and proves an absence."""
    assert det.Evidence(kind="k", reference="r").content_hash is None


# ── one row per act, not per person ───────────────────────────────────────

def test_a_participant_records_an_act_and_not_an_approval():
    """Consulted, advised, agreed and decided are four different things.

    Flattening them into "approved by" destroys the one thing a works council
    will want to see — and `disagreed` is deliberately a first-class action,
    because a recorded disagreement is evidence the process was real.
    """
    p = _example().participants[0]
    assert p.action == "decided"
    assert p.capacity, "the capacity somebody acted in is the point of the row"


def test_no_actor_means_no_participant_rather_than_an_invented_one():
    """An unattributed decision must look unattributed. Filling in "system" or
    "unknown" as a participant would put a name on an act nobody performed."""
    assert _example(actor="") .participants == ()


# ── the boundary this module must not cross ───────────────────────────────

@pytest.mark.parametrize("forbidden", ["compliant", "compliance", "lawful",
                                       "legally", "permitted", "approved",
                                       "safe", "cleared"])
def test_a_determination_never_states_a_legal_conclusion(forbidden):
    """The line the whole hardness model exists to hold, and the judgement layer
    is exactly where it would get crossed by accident.

    This product reports what a source says, what the data produces, what awaits
    whom and what the employer determined. It does not produce a sixth thing:
    "therefore you are compliant".
    """
    d = _example()
    text = " ".join([d.question, d.chosen, d.system_proposed or "",
                     *d.permitted_uses, *d.excluded_uses,
                     *(str(v) for v in d.rationale.values())]).lower()
    assert forbidden not in text, (
        f"a determination's own words contain {forbidden!r}, which reads as a "
        "verdict on the client's legal position")


# ── failure must not cost the user their analysis ─────────────────────────

def test_a_write_failure_is_returned_and_not_raised():
    """The analysis is what the user asked for; the record is what we owe them.
    Losing the second must not cost them the first — and must not pass in
    silence either, which is why the reason comes back rather than being
    swallowed."""
    class _Boom:
        def table(self, _):
            raise RuntimeError("no database today")

    det_id, err = det.record(_Boom(), "org-1", _example())
    assert det_id is None
    assert err and "no database today" in err


def test_no_client_is_reported_rather_than_treated_as_success():
    det_id, err = det.record(None, "org-1", _example())
    assert det_id is None and err

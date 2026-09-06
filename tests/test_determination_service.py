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


# ── the slice that turns a refusal into the start of a decision ───────────

def _equiv(purposes=("reporting", "mobility"), actor="elmar@example.com"):
    return det.cross_country_equivalence(
        source_country="nl", target_country="de",
        source_grade="schaal 9", target_grade="EG 11",
        purposes=purposes, actor=actor, population=43)


def test_what_was_not_chosen_is_excluded_explicitly_not_merely_absent():
    """The whole reason this record is worth keeping.

    "We did not tick pay" and "pay is excluded" look identical in a record that
    lists only what was agreed — and only one of them is defensible in 2028. So
    every use in the closed list that was not chosen is written down as excluded.
    """
    chosen = ("reporting",)
    d = _equiv(purposes=chosen)
    labels = dict(det.EQUIVALENCE_USES)

    # Compared by LABEL, not by keyword: "mobility" renders as "Moving people
    # between the two markets", and a substring test would have passed on a
    # record that said nothing.
    assert set(d.permitted_uses) == {labels[k] for k in chosen}
    for key, label in det.EQUIVALENCE_USES:
        if key in chosen:
            continue
        assert label in d.excluded_uses, (
            f"{key!r} was not chosen and is not excluded either — absence and "
            "exclusion must not look the same in the record")


def test_an_equivalence_can_never_claim_to_be_a_legal_one():
    """It is the employer's convention. Two exclusions are unconditional and are
    added whatever the reader ticks: it is not a statement of law, and it does
    not travel to another employer."""
    joined = " ".join(_equiv(purposes=tuple(k for k, _ in det.EQUIVALENCE_USES)).excluded_uses).lower()
    assert "legally equivalent" in joined
    assert "any other employer" in joined


def test_the_refusal_itself_is_the_evidence():
    """What the system said when the employer decided, kept as it was.

    Here the honest value is that the engine proposed nothing — it refused — and
    the refusal is the evidence that the decision was taken knowing no legal
    equivalence exists.
    """
    d = det.cross_country_equivalence(
        source_country="NL", target_country="DE", source_grade="9",
        target_grade="EG 11", purposes=("reporting",),
        refusal="Grades cannot be bridged between countries. ISF, CATS, ERA...")
    e = d.evidence[0]
    assert e.kind == "engine_refusal"
    assert "cannot be bridged" in (e.excerpt or "")
    assert e.content_hash, "the refusal must be hashed like any other evidence"
    assert "cannot be bridged" in (d.system_proposed or "")


def test_the_review_date_reuses_the_grade_interval_rather_than_inventing_one():
    """An equivalence rests on two grade ladders and cannot be sounder than the
    shorter-lived of them. 12 months is migration 0017's interval for
    job_grades, not a second number that will drift away from it."""
    from datetime import date
    assert det.REVIEW_MONTHS == 12
    d = _equiv()
    assert d.review_due == det._add_months(date.today(), 12)


def test_the_review_date_survives_a_leap_day():
    """`date.replace(year=+1)` raises on 29 February — a review date that fails
    once every four years and nowhere else."""
    from datetime import date
    assert det._add_months(date(2028, 2, 29), 12) == date(2029, 2, 28)
    assert det._add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


# ── reading it back is the half that makes it a feature ───────────────────

class _FakeQuery:
    def __init__(self, rows, sink): self._rows, self._sink = rows, sink
    def select(self, *_a, **_k): return self
    def eq(self, col, val): self._sink.setdefault("eq", []).append((col, val)); return self
    def in_(self, col, vals): self._sink["in"] = (col, list(vals)); return self
    def contains(self, col, vals): self._sink["contains"] = (col, list(vals)); return self
    def order(self, *_a, **_k): return self
    def execute(self): return type("R", (), {"data": self._rows})()


class _FakeClient:
    def __init__(self, rows=None): self.rows, self.calls = rows or [], {}
    def table(self, _n): return _FakeQuery(self.rows, self.calls)


def test_superseded_determinations_are_not_read_back():
    """A replaced determination is history. Showing it beside the live one
    invites somebody to act on the answer that was withdrawn — so the query asks
    for decided and activated only. It stays in the table; the dossier is the
    point."""
    c = _FakeClient()
    det.recorded(c, "org-1", det.CROSS_COUNTRY_EQUIVALENCE)
    col, states = c.calls["in"]
    assert col == "state"
    assert set(states) == {"decided", "activated"}
    assert "superseded" not in states and "withdrawn" not in states


def test_reading_back_is_scoped_to_the_org_and_the_two_markets():
    c = _FakeClient()
    det.recorded(c, "org-1", det.CROSS_COUNTRY_EQUIVALENCE, countries=("nl", "de"))
    assert ("org_id", "org-1") in c.calls["eq"]
    assert c.calls["contains"] == ("countries", ["NL", "DE"])


def test_a_read_failure_decorates_nothing_rather_than_breaking_the_page():
    """This read decorates an analysis. Losing it must cost the reader a panel,
    never the answer they came for."""
    class _Boom:
        def table(self, _): raise RuntimeError("gone")
    assert det.recorded(_Boom(), "org-1", det.CROSS_COUNTRY_EQUIVALENCE) == []
    assert det.recorded(None, "org-1", det.CROSS_COUNTRY_EQUIVALENCE) == []


# ── pay: three questions, not three routes to one number ─────────────────

def test_each_basis_records_which_question_it_answers():
    """The content of this determination IS the question.

    bridge() refuses pay because an FX rate, purchasing power parity and a
    labour-cost index are not three routes to one number — they are three
    numbers answering three questions. A basis recorded without its question is
    a rate with no meaning attached.
    """
    from datetime import date
    seen = set()
    for key, label, question in det.PAY_BASES:
        d = det.pay_comparison_basis(countries=("NL", "PL"), basis=key,
                                     rate_date=date(2026, 9, 1))
        permitted = " ".join(d.permitted_uses)
        assert question in permitted, f"{key} does not say what it answers"
        seen.add(question)
        # And the other two questions are explicitly out of bounds.
        assert any("other two questions" in u for u in d.excluded_uses)
    assert len(seen) == 3, "two bases claim to answer the same question"


def test_an_unknown_basis_is_refused_rather_than_stored():
    """A determination whose basis nobody can interpret is worse than none: it
    looks like an answer in a dossier and cannot be read back."""
    with pytest.raises(ValueError, match="Unknown comparison basis"):
        det.pay_comparison_basis(countries=("NL",), basis="whatever")


def test_an_exchange_rate_is_reviewed_in_a_month_and_an_index_in_a_year():
    """Not a preference — the two age at completely different speeds.

    A grade equivalence rests on institutions that move with collective
    agreements. An exchange rate can move several percent in a fortnight, and a
    gap computed on a stale one is wrong by exactly that much with nothing on
    screen to say so. Reusing the equivalence interval here would have been
    consistent and wrong.
    """
    from datetime import date
    taken = date(2026, 9, 1)
    fx = det.pay_comparison_basis(countries=("NL", "PL"), basis="fx",
                                  rate="1 EUR = 4,28 PLN", rate_date=taken)
    ppp = det.pay_comparison_basis(countries=("NL", "PL"), basis="ppp")

    assert det.FX_REVIEW_MONTHS == 1
    # Measured from the DATE OF THE RATE, not from today: a rate supplied late
    # is already old, and dating its review from now would hide that.
    assert fx.review_due == det._add_months(taken, 1)
    assert ppp.review_due == det._add_months(date.today(), det.REVIEW_MONTHS)


def test_the_rate_and_its_date_are_both_in_the_recorded_answer():
    """The same rate is right on one day and wrong the next. A rate without its
    date cannot be checked or reproduced."""
    from datetime import date
    d = det.pay_comparison_basis(countries=("NL", "PL"), basis="fx",
                                 rate="1 EUR = 4,28 PLN", rate_date=date(2026, 9, 1),
                                 source="ECB reference rate")
    assert "4,28" in d.chosen and "2026-09-01" in d.chosen
    assert any(e.kind == "rate_source" and "ECB" in e.reference for e in d.evidence)


def test_recording_a_basis_is_not_applying_one():
    """THE LINE THIS SLICE MUST NOT CROSS.

    The product does not convert. The employer converts, or analyses each
    currency separately; this records which of three questions their numbers
    answer. If the engine ever multiplies by a recorded rate, the refusal has
    been dissolved by the feature meant to complete it — and the figure would
    carry this product's authority instead of the employer's judgement.

    Structural, because the failure would look like a helpful improvement.
    """
    import inspect
    from services import determination_service as m

    src = inspect.getsource(m)
    for arithmetic in ("float(rate", "* rate", "rate *", "/ rate", "Decimal(rate"):
        assert arithmetic not in src, (
            f"determination_service does arithmetic on a rate ({arithmetic!r}); "
            "recording a basis has become applying one")

    # And the record says so in its own words, so a reader is not left to infer it.
    d = det.pay_comparison_basis(countries=("NL", "PL"), basis="fx")
    assert any("different basis" in u for u in d.excluded_uses)

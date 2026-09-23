"""`DEC-41` / `CTX-001` — every concept has a home, and level 4 is never a shortcut.

**WHY THESE TESTS AND NOT MORE COVERAGE OF THE LEVELS THEMSELVES.** The level is derived
from paths the registry already declares and that ``registry_paths_exist`` already checks
against the vendored schema, so "is concept X level 3" is a restatement of the row rather
than a fact a test can independently establish. What a test CAN establish, and what the
decision actually turns on, is the two rules `DEC-41` states in words — never skip a
level to reach 4 when a real field exists, and level 4 never gates export — plus the
honesty of the reconciled domain packet. Those are what is here.

The export half of "level 4 never gates export" is in
``test_extended_context.py``, where the companion that would have to do the gating lives.
"""

from __future__ import annotations

import json

import pytest

from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import mapping as mp


# --- every concept lands somewhere ------------------------------------------


def test_every_examined_concept_has_a_placement_level_and_they_sum_to_the_whole():
    """45 concepts, four levels, nothing unplaced.

    **This is the number `CTX-001` exists to change.** Before it, 40 of the 45 concepts
    carried a refusal reason and no home at all, which is the shrug `DEC-41` replaces.
    The sum is asserted rather than the per-level figures alone, because a level count
    that did not add up to the concept total would mean a concept had fallen out of the
    hierarchy — which is exactly the state this task was created to end.
    """
    levels = [m.placement_level for m in mp.MAPPINGS.values()]
    # 45 -> 47 on 2026-09-22: `temperature_statement` (level 4 — a source's WORDS about
    # temperature have no numeric home) and `contributor_statement` (level 1 —
    # `attribution.contributors` genuinely fits, and the judgement about identity is
    # what keeps it unproposable). Both landed somewhere; nothing fell out.
    assert len(levels) == len(ev.CONCEPTS) == 47
    assert set(levels) <= set(mp.PLACEMENT_LEVELS)
    placement = mp.placement_coverage()
    assert sum(placement[str(level)] for level in mp.PLACEMENT_LEVELS) == 47
    # ~~Measured 2026-09-17: {1: 18, 2: 9, 3: 6, 4: 12, open 8, concepts-with-open 9}~~
    # RE-MEASURED 2026-09-22 by deriving over the whole registry. Level 1 and level 4
    # each rose by one (the two new concepts); the open-question count fell from 8 to 3
    # because the domain owner's reply that day closed Q9, Q11, Q14, Q15 and Q16 — each
    # in its own recorded way — and left Q6, Q7 and Q8 open, which now touch three
    # concepts (dry_state, beamtime_purpose, echem_procedure).
    assert placement == {
        "1": 19,
        "2": 9,
        "3": 6,
        "4": 13,
        "open_domain_questions": 3,
        "concepts_with_an_open_question": 3,
    }


def test_the_registry_breaks_no_placement_rule():
    """`DEC-41`'s rules over the registry as it stands. Empty is correct."""
    assert mp.placement_violations() == ()


def test_a_level_4_placement_is_refused_when_the_schema_has_a_field():
    """**`DEC-41`'s FIRST RULE, and the test the decision asks for by name.**

    *"Never skip a level to reach 4 when a real field exists."* ``potential_magnitude``
    has one — ``context.electrochemistry.potential_setpoint_V`` — so recording it as
    extended context is the defect, not the preservation, and it raises.

    The message has to name the field, because a refusal that only said "wrong level"
    would leave the author guessing where the value belongs.
    """
    with pytest.raises(mp.PlacementSkipError) as excinfo:
        mp.check_placement(
            ev.CONCEPT_POTENTIAL_MAGNITUDE, mp.PLACEMENT_EXTENDED_CONTEXT
        )
    message = str(excinfo.value)
    assert "context.electrochemistry.potential_setpoint_V" in message
    assert "level 4" in message

    # and the correct level for the same concept is accepted silently
    assert mp.check_placement(
        ev.CONCEPT_POTENTIAL_MAGNITUDE, mp.PLACEMENT_OFFICIAL_FIELD
    ) is None


def test_claiming_a_native_field_for_a_concept_that_has_none_is_also_refused():
    """The rule bites in both directions, and the second direction matters too.

    Level 4 for a level-1 concept hides a field. Level 1 for a level-4 concept asserts a
    home that does not exist, which is the `CLAUDE.md` §5 failure one layer along: a path
    nobody can write to, offered to a scientist as though they could.
    """
    with pytest.raises(mp.PlacementSkipError):
        mp.check_placement(ev.CONCEPT_TRIGGER, mp.PLACEMENT_OFFICIAL_FIELD)
    with pytest.raises(mp.PlacementSkipError):
        mp.check_placement(ev.CONCEPT_TRIGGER, 7)


def test_an_unexamined_concept_may_only_be_placed_at_level_4():
    """Nobody has established a home for it, and level 4 is the level that claims none."""
    assert mp.check_placement("a_concept_no_registry_row_covers", 4) is None
    with pytest.raises(mp.PlacementSkipError):
        mp.check_placement("a_concept_no_registry_row_covers", 1)


def test_the_level_is_derived_from_the_schema_and_not_transcribed():
    """A row states no level, so a schema refresh moves the levels with the paths.

    Proven by moving a path rather than by reading the source: the same concept, with
    its ``official_path`` removed and only the extension namespace named, derives level
    2 instead of level 1. Nothing was edited to make that happen.
    """
    native = mp.mapping_for(ev.CONCEPT_PH)
    assert native.placement_level == mp.PLACEMENT_OFFICIAL_FIELD

    moved = mp.ConceptMapping(
        concept=ev.CONCEPT_PH,
        status=mp.STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason="synthetic row for this test only",
        candidate_homes=(mp.EXTENSION_NAMESPACE,),
    )
    assert moved.placement_level == mp.PLACEMENT_SCHEMA_EXTENSION_POINT

    conditions_only = mp.ConceptMapping(
        concept=ev.CONCEPT_PH,
        status=mp.STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason="synthetic row for this test only",
        candidate_homes=(mp.SERIES_CONDITIONS_HOME,),
    )
    assert conditions_only.placement_level == mp.PLACEMENT_RUN_SERIES_CONDITION

    nowhere = mp.ConceptMapping(
        concept=ev.CONCEPT_PH,
        status=mp.STATUS_NOT_EXPRESSIBLE,
        official_path=None,
        reason="synthetic row for this test only",
    )
    assert nowhere.placement_level == mp.PLACEMENT_EXTENDED_CONTEXT


def test_a_candidate_home_alone_never_reaches_level_1():
    """The first draft of the derivation got this wrong, so it is pinned.

    It read any non-extension candidate home as a native field and returned level 1 for
    ``beamtime_purpose``, ``beamtime_dates`` and ``loading_or_thickness``. All three are
    wrong on the registry's own words — ``tags`` *"would reduce a paragraph to keywords"*
    and the loading row says the schema has *"a natural home for neither"*. `DEC-41`'s
    level 1 is a field *"where one genuinely fits"*, and a ``candidate_homes`` entry is
    by this registry's definition *"named, never applied"*.
    """
    for concept in (
        ev.CONCEPT_BEAMTIME_PURPOSE,
        ev.CONCEPT_BEAMTIME_DATES,
        ev.CONCEPT_LOADING_OR_THICKNESS,
    ):
        entry = mp.mapping_for(concept)
        assert entry.official_path is None, concept
        assert entry.candidate_homes, concept
        assert entry.placement_level == mp.PLACEMENT_EXTENDED_CONTEXT, concept


def test_a_build_blocker_is_not_recorded_as_a_schema_fact():
    """``blocked_by_build`` places at level 1, because the field genuinely fits.

    ``assets[].uri`` exists and the obstacle is a publishing decision this application
    made (``ASSETS_BLOCKED_REASON``). Placing it at level 4 would say the schema has
    nowhere for a scan command, which is false, and would make an application decision
    look permanent.
    """
    entry = mp.mapping_for(ev.CONCEPT_SCAN_COMMAND)
    assert entry.status == mp.STATUS_BLOCKED_BY_BUILD
    assert entry.placement_level == mp.PLACEMENT_OFFICIAL_FIELD


# --- the reconciled packet: 17 closed, 3 open -------------------------------


def test_exactly_three_questions_remain_with_the_domain_owner_and_they_are_these():
    """**The 3 that stay Angel's, named.** ~~The 8 that stay Angel's; twelve closed on
    2026-09-17~~ — the eight became three on 2026-09-22, when the domain owner's reply
    (relayed by the project owner) materially addressed Q9, Q11, Q14, Q15 and Q16 and did
    NOT address Q6, Q7 or Q8. Renamed from ``test_exactly_eight_...`` rather than
    deleted: the pin is the same kind of statement at a new value, and the struck
    sentence is the history.

    Pinned as a set rather than a count, because a count would keep passing if one
    question closed and another re-opened — and the identities are what a future session
    needs in order not to re-ask a closed one.
    """
    assert mp.open_domain_questions() == ("Q6", "Q7", "Q8")
    assert len(mp.DOMAIN_QUESTIONS) == 20
    closed = [q for q in mp.DOMAIN_QUESTIONS.values() if not q.is_open]
    assert len(closed) == 17


def test_the_2026_09_22_answers_each_record_their_own_kind_of_closed():
    """Five answers, four different dispositions — never flattened into "answered".

    Q11 is a RULE that depends on each Run; Q9 and Q14 are "leave it missing"; Q15 is a
    policy with an advisory layer; Q16 is "I do not know", and the conflict is kept
    forever. Each carries the attribution that says who answered and how it arrived.
    """
    expected = {
        "Q9": mp.QUESTION_INTENTIONALLY_LEFT_MISSING,
        "Q11": mp.QUESTION_CONDITIONALLY_RESOLVED,
        "Q14": mp.QUESTION_INTENTIONALLY_LEFT_MISSING,
        "Q15": mp.QUESTION_POLICY_ADOPTED,
        "Q16": mp.QUESTION_DOMAIN_OWNER_DOES_NOT_KNOW,
    }
    for qid, disposition in expected.items():
        question = mp.DOMAIN_QUESTIONS[qid]
        assert question.disposition == disposition, qid
        assert not question.is_open, qid
        assert question.attribution == mp.ANGEL_2026_09_22, qid
        assert question.to_state()["attribution"] == mp.ANGEL_2026_09_22
    for qid in ("Q6", "Q7", "Q8"):
        assert "NOT addressed by" in mp.DOMAIN_QUESTIONS[qid].note, qid


def test_a_closed_question_records_WHICH_KIND_of_closed_it_is():
    """Three evidentiary classes, kept apart on purpose.

    A domain owner's answer, a document read in full, and a product decision are not
    interchangeable — `CLAUDE.md` §15 keeps the same distinction for Dean's answers, and
    for the same reason: a reader weighing the evidence is owed which kind it is. Q1 is
    the only one Angel answered, and conflating it with the eleven others would
    overstate how much of this the domain owner has seen.
    """
    assert (
        mp.DOMAIN_QUESTIONS["Q1"].disposition == mp.QUESTION_CLOSED_BY_DOMAIN_OWNER
    )
    by_owner = [
        qid
        for qid, q in mp.DOMAIN_QUESTIONS.items()
        if q.disposition == mp.QUESTION_CLOSED_BY_DOMAIN_OWNER
    ]
    # STILL ONLY Q1 under this disposition — and that is now a statement about the
    # DISPOSITION, not about Angel: his 2026-09-22 reply closed five more questions, and
    # each carries the finer disposition that says HOW (see the test above), because
    # "closed_by_domain_owner" would have flattened five different answers into one.
    assert by_owner == ["Q1"], "only Q1 closed as a plain domain-owner answer"
    assert mp.DOMAIN_QUESTIONS["Q5"].disposition == mp.QUESTION_CLOSED_BY_DOCUMENT
    assert (
        mp.DOMAIN_QUESTIONS["Q10"].disposition
        == mp.QUESTION_CLOSED_BY_PRODUCT_DECISION
    )
    assert (
        mp.DOMAIN_QUESTIONS["Q12"].disposition == mp.QUESTION_CLOSED_BY_EXISTING_RULE
    )


def test_a_concept_is_never_presented_as_blocked_on_a_question_that_closed():
    """The defect `CTX-001` names: telling a scientist to wait for an arrived answer.

    ``sample_or_electrode_number`` still carries ``needs_domain_review`` — legitimately,
    because which official path an instance number lands at is unsettled — and its
    packet question `Q1` is CLOSED. So its open-question list must be empty, and a
    surface reading ``unresolved_questions`` shows nothing to wait for.
    """
    entry = mp.mapping_for(ev.CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER)
    assert entry.domain_questions == ("Q1",)
    assert entry.unresolved_questions == ()
    assert entry.status == mp.STATUS_NEEDS_DOMAIN_REVIEW

    # and a concept whose question IS open says so. ~~`potential_reference_basis` ->
    # ("Q9",)~~ — Q9 closed on 2026-09-22 (the unstated basis stays missing), so the
    # example moves to a concept whose question is still open, and the old example now
    # proves the other half: its question is recorded and nothing is waited for.
    dry = mp.mapping_for(ev.CONCEPT_DRY_STATE)
    assert dry.unresolved_questions == ("Q6",)
    basis = mp.mapping_for(ev.CONCEPT_POTENTIAL_REFERENCE)
    assert basis.domain_questions == ("Q9",)
    assert basis.unresolved_questions == ()


def test_every_open_question_is_reachable_from_at_least_one_concept():
    """Otherwise an open question would be invisible on every concept surface.

    Q15 and Q16 are the interesting cases: the packet itself records that they are about
    CONFLICTS and never corresponded to a registry row. They are attached to the
    concepts that anchor those conflicts — the internal file declaration and the legacy
    number — so a scientist meeting either concept sees the open question.
    """
    reachable = {
        q for m in mp.MAPPINGS.values() for q in m.unresolved_questions
    }
    assert reachable == set(mp.open_domain_questions())
    # Q15 and Q16 CLOSED on 2026-09-22 and are still ATTACHED to the concepts that
    # anchor their conflicts, so a scientist meeting either concept still finds the
    # question — now with the answer beside it, not a wait.
    assert mp.mapping_for(ev.CONCEPT_LEGACY_NUMBER).domain_questions == ("Q16",)
    assert mp.mapping_for(ev.CONCEPT_LEGACY_NUMBER).unresolved_questions == ()
    assert mp.mapping_for(ev.CONCEPT_SPEC_FILE_DECLARATION).domain_questions == ("Q15",)
    assert mp.mapping_for(
        ev.CONCEPT_SPEC_FILE_DECLARATION
    ).unresolved_questions == ()


def test_the_review_rows_that_no_numbered_question_covers_are_named():
    """**A measured finding, not a gap in the function.**

    The packet's own reconciliation says it: *"20 questions, 15 registry rows, and they
    are different sets."* Four ``needs_domain_review`` rows correspond to no numbered
    question — one of them (``acquisition_method``) because it changed status on
    2026-09-16, AFTER the packet was written. Naming them beats leaving a reader to
    subtract two numbers, because a row whose remaining judgement belongs to nobody in
    particular is the row that gets "fixed" by pointing it at a nearby field.
    """
    # FOUR -> SIX on 2026-09-22, and the two new rows are the two concepts added that
    # day. Neither corresponds to a packet question: temperature was a BOUNDARY in the
    # packet (§2.2), not a question, and a named contributor was never asked about. Both
    # are governed by the domain owner's general rule (missing stays missing) and by
    # the identity boundary, and naming them here is what stops either being "fixed" by
    # pointing it at a nearby question.
    assert mp.needs_review_without_a_question() == (
        "acquisition_method",
        "beamtime_dates",
        "contributor_statement",
        "gas_condition",
        "repeat_marker",
        "temperature_statement",
    )
    for concept in mp.needs_review_without_a_question():
        assert mp.MAPPINGS[concept].status == mp.STATUS_NEEDS_DOMAIN_REVIEW


def test_an_unknown_question_id_on_a_row_is_refused_at_construction():
    with pytest.raises(ValueError):
        mp.ConceptMapping(
            concept=ev.CONCEPT_FILTER,
            status=mp.STATUS_NOT_EXPRESSIBLE,
            official_path=None,
            reason="x" * 60,
            domain_questions=("Q99",),
        )


def test_an_unresolved_question_is_never_given_a_placement_level():
    """`DEC-41`'s own wording: the ``-`` row is *"NOT a placement"*.

    So an open question renders as ``"-"`` while every CONCEPT keeps a level 1-4. The
    two facts move independently and a surface must be able to say both at once —
    ``potential_reference_basis`` sits at level 1, with a real native field, and its
    enum member is blocked on Q9.
    """
    # ~~Q9~~ -> Q6: Q9 closed on 2026-09-22, so the open-question example moves to one
    # that is still open. The property is unchanged.
    assert mp.DOMAIN_QUESTIONS["Q6"].placement == mp.PLACEMENT_UNRESOLVED
    assert mp.DOMAIN_QUESTIONS["Q9"].placement != mp.PLACEMENT_UNRESOLVED
    assert mp.PLACEMENT_UNRESOLVED not in mp.PLACEMENT_LEVELS
    basis = mp.mapping_for(ev.CONCEPT_POTENTIAL_REFERENCE)
    assert basis.placement_level == mp.PLACEMENT_OFFICIAL_FIELD
    dry = mp.mapping_for(ev.CONCEPT_DRY_STATE)
    assert dry.unresolved_questions == ("Q6",)


def test_the_placement_block_round_trips_as_json():
    for m in mp.MAPPINGS.values():
        state = m.to_state()
        assert state["placement_level"] in mp.PLACEMENT_LEVELS
        assert state["placement_name"] == mp.PLACEMENT_NAMES[state["placement_level"]]
        json.dumps(state)
    json.dumps(mp.placement_coverage())
    json.dumps([q.to_state() for q in mp.DOMAIN_QUESTIONS.values()])

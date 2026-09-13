"""One sentence, more than one value — and the seven-utterance acceptance suite.

WHY THIS FILE EXISTS
====================
``transcript_capture.read_transcript`` matched each rule with ``re.search``, which
returns the FIRST match and nothing else. A sentence stating two values for one
field therefore produced ONE candidate and lost the other **in silence** — no
candidate, no clarification, no abstention, no ``review_required`` entry. The
transcript text survived as a note (rule (4)), so nothing was destroyed; what was
lost was the *reading*, and with it the scientist's chance to accept either value.

The project owner stated the requirement directly: *"Temperature is around 425,
maybe 430"* must not silently become 425.

WHAT THE MEASUREMENT SHOWED, AND WHERE IT DIFFERED FROM THE BRIEF
=================================================================
Measured on the unmodified module, and both halves matter:

* ``"Temperature is around 425, maybe 430."`` — the owner's literal words, with no
  unit — produced **ZERO** candidates, not 425. ``_TEMPERATURE_K`` REQUIRES kelvin,
  so the unitless form never proposed anything and the silent-preference defect was
  not reachable through it. That is still the correct behaviour and is pinned below.
* ``"The temperature was around 425 K, maybe 430 K."`` — the same sentence with the
  unit the rule requires — produced **ONE** candidate, 425, with
  ``review_required: []``. **That is where 430 was silently lost**, and it is the
  case the negative control in this file drives.

The second finding is that ``search`` -> ``finditer`` alone does **not** fix it.
``_TEMPERATURE_K.finditer`` on that sentence returns exactly one match, because the
pattern is anchored on the literal word ``temperature`` and the sentence says it
once. ``finditer`` fixes a DIFFERENT member of the same family — a sentence that
repeats the label (``"the temperature was 425 K and the temperature at the end was
430 K"``) — and both halves were needed.

WHAT IS NOT BEING BUILT HERE, STATED SO IT IS NOT MISTAKEN FOR AN OVERSIGHT
===========================================================================
No range, interval or ``bounds`` is ever constructed. ``425 maybe 430`` is two
statements, and ``[425, 430]`` asserts a continuous interval **nobody said**; the
official schema's only uncertainty representation is
``$.descriptors.outputs[].descriptors[].uncertainty``, which ``context.temperature_K``
has no sibling of. No confidence, no score, no ranking and no auto-selection: the
reader returns both candidates and prefers neither, which is the outcome
``AMBIGUITY_POLICY``'s ``conflicting_values_for_one_field`` row already declares.

Everything here is synthetic. Nothing connects to a database and no network call is
made.
"""

from __future__ import annotations

import pytest

import isaac_api.transcript_capture as tc

from conftest import client_ws, tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def experiment_id(client):
    store = client_ws(client)
    exp = store.create_experiment(
        "Multi-value fixture",
        {"kind": "synthetic"},
        {"meta": {}, "fields": {}, "pending": []},
    )
    return exp.id


# --- helpers ------------------------------------------------------------------

RUN = tc.RunRef(id="run-1", label="Run 1", ordinal=1)
RUNS = (RUN,)


def _read(text: str, *, selected_run: str | None = "run-1", known_runs=RUNS):
    return tc.read_transcript(text, selected_run=selected_run, known_runs=known_runs)


def _values(reading, field_path: str | None = None) -> list:
    return [
        candidate.proposed_value
        for candidate in reading.candidates
        if field_path is None or candidate.field_path == field_path
    ]


def _etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _make_run(client, experiment_id: str) -> dict:
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]


def _finalize(client, experiment_id: str, text: str, *, run_id: str | None = None):
    body: dict = {"text": text, "finalized": True}
    if run_id is not None:
        body["run_id"] = run_id
    return client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json=body,
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _runs(client, experiment_id: str) -> list[dict]:
    response = client.get(f"/api/experiments/{experiment_id}/runs")
    assert response.status_code == 200, response.text
    return response.json()["runs"]


def _notes(client, experiment_id: str) -> list[dict]:
    response = client.get(f"/api/experiments/{experiment_id}/notes")
    assert response.status_code == 200, response.text
    return response.json()["notes"]


#: A run row's identity and bookkeeping keys — everything that is NOT scientific
#: content. Named as an exclusion list rather than an inclusion list so that a key
#: added to the run payload later is treated as CONTENT and scanned, which is the
#: fail-safe direction.
_RUN_BOOKKEEPING_KEYS = frozenset(
    {
        "id",
        "experiment_id",
        "record_id",
        "label",
        "ordinal",
        "created_utc",
        "updated_utc",
        "rev",
        "version",
    }
)


def _run_content(row: dict) -> dict:
    """The scientific content of a run row, with identity and bookkeeping removed.

    WHY THIS EXISTS, AND IT IS A FLAKE THIS FILE ACTUALLY PRODUCED. An earlier
    version of the two "the run still holds neither value" assertions below read
    ``assert "425" not in repr(stored_row)``. A run row carries TWO ULIDs, and a
    ULID is Crockford base32 — so it contains decimal digits, and roughly **0.19%**
    of them contain the literal ``425`` or ``430`` (measured over 200,000). The
    assertion therefore failed at about the rate you would predict: once in ~35
    whole-file runs, naming a value that had not been written, for a reason with
    nothing to do with what it was testing.

    Scanning the CONTENT is both deterministic and the thing the test means.
    """
    return {key: value for key, value in row.items() if key not in _RUN_BOOKKEEPING_KEYS}


#: The owner's sentence, in the unit-bearing form the rule can read. This exact
#: string is the negative control: measured against the unmodified module it gives
#: one candidate of 425 and an empty `review_required`.
OWNER_SENTENCE = "The temperature was around 425 K, maybe 430 K."

TEMPERATURE = "context.temperature_K"


# =============================================================================
# CAP-001 — the negative control
# =============================================================================


def test_one_sentence_stating_two_values_loses_neither():
    """THE NEGATIVE CONTROL. RED on the unmodified module.

    Measured before the fix: ``candidates == [425]`` and ``review_required == []``
    — 430 was gone with nothing anywhere recording that it had been said.

    MUTATION: reverting either half of the match strategy (``finditer`` back to
    ``search``, or removing the same-sentence restatement read) turns this RED.
    """
    reading = _read(OWNER_SENTENCE)
    assert _values(reading, TEMPERATURE) == [425, 430], [
        (c.field_path, c.proposed_value) for c in reading.candidates
    ]


def test_neither_of_the_two_values_is_preferred():
    """Both are grouped for review and NEITHER is selected, dropped or ranked.

    This is the half that makes the fix honest rather than merely complete: a
    reading that returned both and then nominated one would still be guessing.
    """
    reading = _read(OWNER_SENTENCE)
    assert len(reading.review_required) == 1
    entry = reading.review_required[0]
    assert entry.kind == "conflicting_values_for_one_field"
    assert entry.outcome == tc.OUTCOME_NEEDS_REVIEW
    assert entry.field_path == TEMPERATURE
    # EVERY candidate is in the group. None was dropped to make the group smaller.
    assert sorted(entry.candidate_indexes) == [0, 1]
    assert len(reading.candidates) == 2


def test_the_note_records_neither_of_the_two_candidates():
    """A note carries at most one ``candidate_field_path``; recording one of two
    would state the preference the previous test proves is absent.

    ``candidate_for_segment`` already documented exactly this. It was unreachable
    for a single-sentence pair until now.
    """
    reading = _read(OWNER_SENTENCE)
    assert reading.candidate_for_segment(0) is None
    assert 0 not in reading.candidate_by_segment
    assert reading.unmapped_segment_indexes == (0,)


def test_no_range_interval_or_bounds_is_ever_constructed():
    """425 maybe 430 is TWO statements. ``[425, 430]`` is an interval nobody said.

    MUTATION: collapsing the pair into a list, tuple, dict or ``{"min":…,"max":…}``
    turns this RED. ``context.temperature_K`` has no uncertainty sibling in the
    official schema; the only uncertainty the schema defines is on a descriptor
    output, which this reader cannot write.
    """
    reading = _read(OWNER_SENTENCE)
    for candidate in reading.candidates:
        assert isinstance(candidate.proposed_value, (int, float)), candidate
        assert not isinstance(candidate.proposed_value, bool)
    assert _values(reading, TEMPERATURE) == [425, 430]


def test_no_confidence_score_or_ranking_is_attached_to_either_candidate():
    """MUTATION: adding a confidence/probability/score to provenance turns this RED
    — and ``FieldCandidate.__post_init__`` would refuse to construct it at all."""
    reading = _read(OWNER_SENTENCE)
    for candidate in reading.candidates:
        keys = {str(key).lower() for key in candidate.provenance}
        assert not keys & {"confidence", "probability", "score", "rank", "uncertainty"}
        assert candidate.verified is False
        assert candidate.requires_user_confirmation is True


def test_both_values_are_quoted_from_the_transcript_and_not_interpreted():
    reading = _read(OWNER_SENTENCE)
    for candidate in reading.candidates:
        assert str(candidate.proposed_value) in OWNER_SENTENCE
        assert candidate.quote in OWNER_SENTENCE
        assert candidate.provenance["matched_text"] in OWNER_SENTENCE


def test_three_HEDGED_values_in_one_sentence_are_all_preserved():
    """Three alternatives chain, because each is hedged against the one before it.

    ~~``test_three_values_in_one_sentence_are_all_preserved``, over
    ``"Temperature ramped 300 K, then 350 K, then 400 K."``, asserting
    ``[300, 350, 400]`` and one ``review_required`` row.~~ — **INVERTED
    2026-09-12, and the sentence was changed, not the assertion loosened.** That
    test pinned the C-1 defect. ``then`` is a temporal sequencer, not a hedge: the
    sentence says the temperature WENT 300 → 350 → 400, and
    ``context.temperature_K`` is one scalar, so reading the three as *alternative*
    values for it — grouped under ``conflicting_values_for_one_field``, whose own
    served reason says *"Accept at most one"* — states something about the
    transcript the transcript does not state. It is the same sentence family as
    the reviewer's first measured row, ``"The temperature was 425 K, ramped at
    3 K/min"``, which is now refused: a ramp is not a disagreement.

    **The old test's reasoning was RIGHT and is kept**, which is why this is an
    inversion rather than a deletion: truncating a scientist's statements IS the
    silent discard this feature exists to end, and a cap that kept the first two
    of three genuinely-alternative values would still be that defect. So the
    capability is pinned here on a sentence that actually states three
    alternatives, and ``test_a_ramp_is_not_a_disagreement`` pins the ramp. What is
    NOT truncation is declining to read 350 and 400 as alternatives at all: they
    are never proposed and never counted.

    ~~"and the whole sentence survives verbatim as an Unmapped Note under rule
    (4)"~~ — **CORRECTED 2026-09-12: FALSE IN THE SENSE THAT MATTERS HERE, and it
    was the stated mitigation for the whole refusal, so it is struck rather than
    reworded.** The sentence does survive verbatim — rule (4) stores every segment
    — but it does not survive as an *Unmapped* note. Exactly one candidate survives
    the gate, so ``len(produced) == 1`` records the segment in
    ``candidate_by_segment`` and the note is presented as **MAPPED to that one
    value**. Measured at ``c9a4c6e8``: *"Temperature ramped 300 K, then 350 K, then
    400 K."* gave ``candidates=[temperature_K=300]``, ``abstentions=[]``,
    ``review_required=()``, ``candidate_by_segment={0: 0}`` — a sentence saying the
    temperature went to 400, filed as a note about 300 with no disclosure anywhere
    that anything had been declined. The refusal is correct; its invisibility was
    not. An ``unhedged_further_values`` abstention now names the field whose
    further values were withheld, which is what this claim was reaching for.

    MUTATION: a cap that keeps the first two turns this RED; so does dropping the
    anchor advance in ``_segment_readings``, which would leave 435 unread.
    """
    reading = _read("The temperature was 425 K, maybe 430 K, or perhaps 435 K.")
    assert _values(reading, TEMPERATURE) == [425, 430, 435]
    assert len(reading.review_required) == 1
    assert sorted(reading.review_required[0].candidate_indexes) == [0, 1, 2]
    restated = [
        candidate.provenance["restated_in_same_sentence"]
        for candidate in reading.candidates
    ]
    assert restated == [False, True, True]


def test_a_ramp_is_not_a_disagreement():
    """The sentence the inverted test above used to assert three candidates for.

    It is here so the change of behaviour is pinned in its own right rather than
    only implied by the absence of the old assertion, and so that re-admitting
    ``then`` to the hedge list turns a test RED instead of quietly restoring a §5
    violation.
    """
    reading = _read("Temperature ramped 300 K, then 350 K, then 400 K.")
    assert _values(reading, TEMPERATURE) == [300]
    assert reading.review_required == ()
    # And the words survive: rule (4) stores every segment regardless.
    assert [segment.text for segment in reading.segments] == [
        "Temperature ramped 300 K, then 350 K, then 400 K."
    ]


def test_the_same_value_restated_in_one_sentence_is_one_candidate_not_two():
    """"425, and again 425" is one value stated twice, not a disagreement.

    WHY DEDUPE, AND WHY ONLY WITHIN A SENTENCE. Two identical candidates would mint
    two durable proposals — ``_mint_transcript_proposals`` keys on the candidate
    INDEX, so they do not collapse — giving one fact two independently acceptable
    rows, which is the duplicate authoritative mutation the acceptance suite's case
    3 forbids. It is scoped to one segment because
    ``test_the_same_value_said_twice_is_not_a_conflict`` in
    ``test_transcript_capture.py`` pins the ACROSS-sentence case as two candidates,
    and that is right: two sentences are two statements. This file does not change
    it.
    """
    reading = _read("Temperature was 425 K, and again 425 K.")
    assert _values(reading, TEMPERATURE) == [425]
    assert reading.review_required == ()
    # One candidate, so the segment CAN record it — there is no preference to state.
    assert reading.candidate_for_segment(0) is not None


def test_two_labelled_statements_in_one_sentence_are_both_read():
    """Measured before the fix: one candidate, 425.

    ~~"MUTATION: ``finditer`` back to ``search`` turns this RED, and this is the
    only test here that it alone turns RED."~~ — **WITHDRAWN. Measured, and it is
    FALSE: that mutation leaves this test GREEN.** Both values are still read,
    because the restatement pass scans from the end of the FIRST labelled match and
    picks 430 up as a restatement. The two halves of the fix overlap on this
    sentence, so the VALUES here discriminate nothing.

    What they do assert is still worth asserting, and the provenance below is what
    ``finditer`` is actually load-bearing for — see the two tests that follow.
    """
    reading = _read(
        "The temperature was 425 K and the temperature at the end was 430 K."
    )
    assert _values(reading, TEMPERATURE) == [425, 430]


def test_a_second_LABELLED_statement_is_not_reported_as_a_restatement():
    """``finditer``'s first load-bearing job: provenance that is not a lie.

    This sentence says "temperature" TWICE. Both readings are label-anchored, so
    both must carry ``restated_in_same_sentence: False`` and the label-anchored
    ``rule`` sentence. Under ``search`` the second one is found by the restatement
    pass instead and claims it was a restatement — a candidate explaining itself
    with the wrong reason, which is the class of defect this module's ``rule``
    sentences exist to prevent.

    MUTATION: ``finditer`` back to ``search`` turns this RED.
    """
    reading = _read(
        "The temperature was 425 K and the temperature at the end was 430 K."
    )
    assert [c.provenance["restated_in_same_sentence"] for c in reading.candidates] == [
        False,
        False,
    ]
    for candidate in reading.candidates:
        assert "restat" not in candidate.rule.lower()


def test_a_fourth_instant_labelled_ended_is_never_read_as_a_start():
    """``finditer``'s second and more serious job: the cross-rule guard's REACH.

    ``claimed_value_spans`` is what stops a restatement scan from swallowing a value
    another rule read under its own label. Built from ``search`` it holds only the
    FIRST match of each rule, so in a sentence with two starts and two ends the
    later ones are unclaimed — and the scan then proposes the instant explicitly
    labelled *"ended"* as an acquisition START, and the one labelled *"started"* as
    an END.

    MEASURED under that mutation: ``acquired_start_utc`` came back as
    ``[01, 03, 04]`` and ``acquired_end_utc`` as ``[02, 03, 04]`` — six candidates
    from four statements, two of them contradicting the word in front of them. That
    is worse than the defect being fixed: losing a value is a silent omission, while
    this is a silent ASSERTION about a field the scientist addressed differently.

    MUTATION: ``finditer`` back to ``search`` turns this RED.
    """
    reading = _read(
        "The run started 2026-01-01T00:00:00Z and ended 2026-01-02T00:00:00Z "
        "and started 2026-01-03T00:00:00Z and ended 2026-01-04T00:00:00Z."
    )
    assert _values(reading, "timestamps.acquired_start_utc") == [
        "2026-01-01T00:00:00Z",
        "2026-01-03T00:00:00Z",
    ]
    assert _values(reading, "timestamps.acquired_end_utc") == [
        "2026-01-02T00:00:00Z",
        "2026-01-04T00:00:00Z",
    ]
    # Every reading here was labelled. None is a restatement.
    assert not any(
        c.provenance["restated_in_same_sentence"] for c in reading.candidates
    )


def test_a_value_stated_before_the_label_is_still_not_read():
    """The rule requires the label to PRECEDE the value, and that is unchanged.

    Reading "300 K" here would mean reading a bare number in a sentence whose only
    temperature claim is 425 — an unlabelled guess. Nothing is proposed for it and
    the words are kept as a note.

    MUTATION: scanning the whole segment for unit-bearing numbers regardless of the
    label's position turns this RED.
    """
    reading = _read("At 300 K the temperature was 425 K.")
    assert _values(reading, TEMPERATURE) == [425]


def test_an_explicitly_labelled_end_instant_is_not_read_as_a_start_too():
    """The multi-rule collision, and the reason the restatement read is span-guarded.

    "started X and ended Y" states two DIFFERENT fields. A restatement read that
    looked only for "another instant after the start label" would propose Y as a
    second acquisition START — contradicting the word "ended" that sits in front of
    it. A value another rule already read under its own label is not an unlabelled
    restatement of this one.

    MUTATION: dropping the cross-rule span guard turns this RED.
    """
    reading = _read(
        "The run started 2026-01-01T00:00:00Z and ended 2026-01-02T00:00:00Z."
    )
    assert _values(reading, "timestamps.acquired_start_utc") == [
        "2026-01-01T00:00:00Z"
    ]
    assert _values(reading, "timestamps.acquired_end_utc") == ["2026-01-02T00:00:00Z"]
    assert reading.review_required == ()


def test_an_unlabelled_second_instant_is_read_as_an_alternative_start():
    """The timestamp rules have the same defect and the same fix as temperature."""
    reading = _read(
        "The run started 2026-01-01T00:00:00Z, or maybe 2026-01-02T00:00:00Z."
    )
    assert _values(reading, "timestamps.acquired_start_utc") == [
        "2026-01-01T00:00:00Z",
        "2026-01-02T00:00:00Z",
    ]
    assert len(reading.review_required) == 1
    assert reading.review_required[0].field_path == "timestamps.acquired_start_utc"


def test_a_second_temperature_in_another_unit_is_disclosed_not_proposed():
    """A SECOND defect of the same family, measured on the unmodified module.

    ``"Temperature was 425 K, maybe 430 C."`` produced candidate 425 and **no
    abstention at all**: the non-kelvin guard asked "does this segment contain any
    kelvin reading?" and a kelvin reading anywhere suppressed the disclosure for a
    non-kelvin statement elsewhere in the same sentence. So 430 C vanished from the
    reading exactly as 430 K did.

    The fix asks the narrower, correct question — is this non-kelvin statement the
    one the kelvin rule already read? — by comparing the VALUE spans.

    MUTATION: restoring the segment-wide suppression turns this RED.
    """
    reading = _read("Temperature was 425 K, maybe 430 C.")
    # 430 C is NOT proposed: converting it would put a number nobody said in the
    # record. It is DISCLOSED instead.
    assert _values(reading, TEMPERATURE) == [425]
    assert [abstention.kind for abstention in reading.abstentions] == [
        "temperature_not_in_kelvin"
    ]
    assert "430" in reading.abstentions[0].quote


def test_a_lone_kelvin_statement_still_raises_no_abstention():
    """The negative control for the test above: the span guard must not start
    inventing abstentions on clean sentences."""
    reading = _read("Temperature was 425 K.")
    assert _values(reading, TEMPERATURE) == [425]
    assert reading.abstentions == ()


def test_the_phrase_rules_are_unchanged_by_the_new_match_strategy():
    """``_ATMOSPHERE``/``_ENVIRONMENT`` are anchored to the end of the segment, so
    they can match at most once and have no self-identifying value form to restate.

    A free phrase is not restatable: unlike "430 K" it carries nothing that says
    what it is, so a second phrase in the same sentence could be anything. They get
    no restatement read, deliberately.
    """
    reading = _read("Atmosphere was: dry nitrogen")
    assert _values(reading, "context.thermodynamics.atmosphere") == ["dry nitrogen"]
    # Two phrases in one segment still read exactly one — the `$` anchor decides it,
    # and that is unchanged from before this slice.
    repeated = _read("atmosphere was dry nitrogen, atmosphere was air")
    assert _values(repeated, "context.thermodynamics.atmosphere") == ["air"]


def test_a_restated_value_says_in_its_rule_that_it_was_restated():
    """A candidate's ``rule`` sentence is how a scientist checks WHY it was read.

    The label-anchored sentence claims the label and the value appeared in one
    clause. That is not true of a restatement, so it must not carry that sentence.
    """
    reading = _read(OWNER_SENTENCE)
    first, second = reading.candidates
    assert first.provenance["restated_in_same_sentence"] is False
    assert second.provenance["restated_in_same_sentence"] is True
    assert "restat" in second.rule.lower()
    # And it says what it is NOT, because that is the guess a reader would make.
    assert "range" in second.rule.lower()


def test_a_rule_with_a_restatement_pattern_always_has_a_restatement_SENTENCE():
    """The two fields go together or a candidate explains itself with ``None``.

    MUTATION: adding ``restatement=`` to a rule and forgetting
    ``restated_sentence=`` turns this RED, instead of shipping a ``rule`` string
    reading "in the sentence '…', None; the value is quoted…".
    """
    for rule in tc._RULES:
        assert (rule.restatement is None) == (rule.restated_sentence is None), rule.name
        if rule.restated_sentence is not None:
            # It must not be the label-anchored claim, which would be false of it.
            assert rule.restated_sentence != rule.sentence
            assert "restates" in rule.restated_sentence


def test_the_phrase_rules_deliberately_have_no_restatement_pattern():
    """A free phrase is not self-identifying, so a second one could be anything.

    MUTATION: giving ``atmosphere`` or ``environment`` a restatement pattern turns
    this RED. The reason is in ``_Rule``'s docstring and is a no-guessing decision,
    not an omission.
    """
    by_name = {rule.name: rule for rule in tc._RULES}
    assert by_name["atmosphere"].restatement is None
    assert by_name["environment"].restatement is None
    assert by_name["temperature_kelvin"].restatement is not None
    assert by_name["acquisition_start"].restatement is not None
    assert by_name["acquisition_end"].restatement is not None


def test_the_reader_DOES_need_its_own_ceilings_and_the_durable_write_is_not_where_the_cost_is():
    """The inversion of this file's own vacuous test. See ``test_transcript_capture_ceilings.py``.

    ~~``test_the_reader_adds_no_ceiling_because_the_durable_write_already_has_one``:
    "WHY NO PER-SEGMENT CANDIDATE CEILING WAS ADDED, pinned rather than argued.
    Letting one sentence produce many candidates raises write amplification, and
    this module's own idiom is a ceiling that REFUSES rather than truncates
    (MAX_SEGMENTS). A new one here would have needed a new AMBIGUITY_POLICY kind
    and a new abstention — new surface for a bound the repository already has.
    routes._MAX_PROPOSALS_PER_RECORD bounds the DURABLE rows and discloses each
    candidate it could not store as too_many_proposals, dropping nothing in
    silence. So the reader stays unbounded per segment and the write stays
    bounded, which is where the cost actually is."~~

    **INVERTED 2026-09-12. The reasoning is kept struck in place because it is
    the more instructive half: every sentence of it is about the DURABLE WRITE,
    and the durable write was never where the cost was.** Measured through the
    real route on the code that shipped it, a 27,025-byte single segment naming
    3,000 kelvin values produced 3,001 candidates and a **165,828,285-byte**
    response, with ``proposals_too_large`` refusing all 3,001 rows and minting
    **none**. The bound this test pointed at worked perfectly and the request
    still cost 165 MB, assembled and serialised inside ``record_lock``.

    **And the assertions were worse than the reasoning.** ``isinstance(int)`` and
    ``> 0`` measure no size, no count and no time — a ceiling of ``1`` passes
    them. The last line, ``assert not [name for name in dir(tc) if "MAX" in name
    and name != "MAX_SEGMENTS"]``, did not merely fail to detect the defect: it
    **mechanically forbade the fix**, so the repository was enforcing the absence
    of the bound it needed, in a test whose name asserted that absence was a
    decision.

    Two claims in the struck text are also simply wrong. A new ceiling needed **no**
    ``AMBIGUITY_POLICY`` kind and **no** abstention — ``MAX_SEGMENTS`` has neither,
    because a refusal is not an ambiguity: nothing is read, so there is nothing to
    be ambiguous about. And "the reader stays unbounded per segment" was the defect
    stated as a property.

    What replaces it: ``test_transcript_capture_ceilings.py`` MEASURES candidate
    count, response bytes and elapsed time through the real route, and proves each
    of the two ceilings binds on its own.
    """
    import isaac_api.routes as routes

    # The durable-write bound still exists and is still correct — it was never the
    # wrong bound, only the wrong ANSWER to "is the reader bounded?".
    assert isinstance(routes._MAX_PROPOSALS_PER_RECORD, int)
    assert routes._MAX_PROPOSALS_PER_RECORD > 0

    # AND THE READER NOW DECLARES ITS OWN, which the struck assertion forbade.
    assert isinstance(tc.MAX_CANDIDATES, int) and tc.MAX_CANDIDATES > 0
    assert (
        isinstance(tc.MAX_CANDIDATE_QUOTE_BYTES, int)
        and tc.MAX_CANDIDATE_QUOTE_BYTES > 0
    )
    # Both are exported, so a route refusing on them is not reaching into a private.
    assert {"MAX_CANDIDATES", "MAX_CANDIDATE_QUOTE_BYTES"} <= set(tc.__all__)
    # A refusal is not an ambiguity, so neither gets an `AMBIGUITY_POLICY` row —
    # exactly as `MAX_SEGMENTS` does not. Pinned so a later slice does not add one
    # on the strength of the struck reasoning above.
    kinds = {entry["kind"] for entry in tc.AMBIGUITY_POLICY}
    assert not {kind for kind in kinds if "too" in kind or "ceiling" in kind}


def test_the_candidates_are_stable_across_two_identical_readings():
    """The reader stays pure. MUTATION: any ordering that depends on a set or dict
    iteration of values turns this flaky rather than RED, which is why the values
    are compared as an ORDERED list."""
    first = _read(OWNER_SENTENCE)
    second = _read(OWNER_SENTENCE)
    assert [c.to_dict() for c in first.candidates] == [
        c.to_dict() for c in second.candidates
    ]


def test_candidates_are_still_withheld_when_the_run_is_unsettled():
    """The new reads are inside the settled gate, exactly as the old one was.

    MUTATION: moving the restatement read outside the ``settled`` check turns this
    RED, and would offer a scientist two values to accept against a run nobody
    chose.
    """
    reading = _read(OWNER_SENTENCE, selected_run=None)
    assert reading.candidates == ()
    assert reading.review_required == ()
    assert reading.run_target is None
    assert {c.kind for c in reading.clarifications} == {"run_target_required"}


# --- the same sentence, over HTTP, through the durable proposal path ----------


def test_both_values_reach_durable_proposals_and_neither_is_applied(
    client, experiment_id
):
    """The reading is only half the promise: both values must survive the tab
    closing, and NEITHER may become a field value.

    MUTATION: applying either value turns this RED at the run assertion.
    """
    run = _make_run(client, experiment_id)
    response = _finalize(client, experiment_id, OWNER_SENTENCE, run_id=run["id"])
    assert response.status_code == 200, response.text
    payload = response.json()

    assert [entry["proposed_value"] for entry in payload["candidates"]] == [425, 430]
    assert payload["unproposable"] == []
    assert len(payload["proposals"]) == 2
    assert [entry["candidate_index"] for entry in payload["proposals"]] == [0, 1]
    assert [entry["deduplicated"] for entry in payload["proposals"]] == [False, False]

    review = payload["review_required"]
    assert len(review) == 1
    assert review[0]["kind"] == "conflicting_values_for_one_field"
    assert sorted(review[0]["candidate_indexes"]) == [0, 1]

    # TWO DISTINCT durable rows, both OPEN, neither accepted.
    listed = client.get(f"/api/experiments/{experiment_id}/proposals")
    assert listed.status_code == 200, listed.text
    rows = [
        row
        for row in listed.json()["proposals"]
        if row["target_field_path"] == TEMPERATURE
    ]
    assert len(rows) == 2
    assert {row["proposed_value"] for row in rows} == {425, 430}
    assert {row["state"] for row in rows} == {"open"}
    assert len({row["proposal_id"] for row in rows}) == 2
    assert {row["applied"] for row in rows} == {False}
    assert {row["accepted_value"] for row in rows} == {None}

    # AND THE RUN STILL HOLDS NEITHER.
    stored = next(row for row in _runs(client, experiment_id) if row["id"] == run["id"])
    assert _run_content(stored) == {"fields": {}, "inherited": {}}, stored
    assert "425" not in repr(_run_content(stored)), stored
    assert "430" not in repr(_run_content(stored)), stored


def test_neither_candidate_reaches_the_official_record(client, experiment_id):
    """THE CANDIDATE SET IS ASSISTANT-SIDE. It must not reach an official record.

    THE ASSERTION IS THE RUN'S CONTENT, AND THE TWO OBVIOUS-LOOKING ALTERNATIVES
    WERE MEASURED AND ARE VACUOUS. This is recorded rather than quietly dropped,
    because both are what a later reader would reach for first:

    * **A substring scan of the export RESPONSE — vacuous.** The first version of
      this test asserted ``"425" not in json.dumps(export.json())``. Positive
      control: write 425 to the run through ``PATCH .../runs/{id}`` with
      ``confirmed_by_user: true``, then export — and ``"425"`` is STILL absent from
      the body, because the export refuses on an incomplete record and echoes no
      record content at all. The assertion passed whether or not the value had been
      written, which is precisely the equivalent mutant this repository has shipped
      before.
    * **The experiment's derived state — also vacuous.** ``draft_ok``,
      ``pending_count``, ``exported``, ``evidenced_field_count`` and ``status`` are
      byte-identical before and after a REAL confirmed write of 425. Comparing them
      across a capture therefore establishes nothing.

    What DOES discriminate, measured by the same positive control: the run's own
    content. A real write turns ``fields`` from ``{}`` into a full
    ``{"value": 425, "status": "verified", "evidence": [...]}`` envelope. So that is
    the assertion, and the export call is kept only to prove a capture does not make
    an unfinished record exportable.

    MUTATION: applying either candidate to the run turns this RED.
    """
    run = _make_run(client, experiment_id)
    assert (
        _finalize(client, experiment_id, OWNER_SENTENCE, run_id=run["id"]).status_code
        == 200
    )

    stored = next(row for row in _runs(client, experiment_id) if row["id"] == run["id"])
    assert _run_content(stored) == {"fields": {}, "inherited": {}}, stored

    export = client.post(
        f"/api/experiments/{experiment_id}/export",
        json={},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert export.status_code == 200, export.text
    # A capture cannot make an unfinished record exportable, and the proposals are
    # inert to export by construction: they live at `state["proposals"]`, outside
    # `draft`, which is the property that location was chosen for.
    assert export.json()["ok"] is False
    assert client.get(f"/api/experiments/{experiment_id}").json()["exported"] is False

    # And the run STILL holds neither, after the export attempt as before it.
    stored = next(row for row in _runs(client, experiment_id) if row["id"] == run["id"])
    assert _run_content(stored) == {"fields": {}, "inherited": {}}, stored


def test_the_whole_sentence_is_stored_verbatim_as_one_note(client, experiment_id):
    """Rule (4) is unchanged: the segment that produced TWO candidates is still
    stored, and still records neither of them."""
    run = _make_run(client, experiment_id)
    assert (
        _finalize(client, experiment_id, OWNER_SENTENCE, run_id=run["id"]).status_code
        == 200
    )
    stored = _notes(client, experiment_id)
    assert [note["text"] for note in stored] == [OWNER_SENTENCE]
    assert stored[0]["candidate_field_path"] is None
    assert stored[0]["is_field_value"] is False


# =============================================================================
# CAP-009 — the seven-utterance acceptance suite
# =============================================================================
#
# EACH CASE ASSERTS WHAT THE SYSTEM ACTUALLY DOES. Where the expected behaviour is
# not implemented, the test documents the REAL behaviour and the docstring names the
# gap. A test asserting an aspiration would be a failing test, not a specification.
#
#   1 satisfied, with a correction to the case as written
#   2 SATISFIED — this is the case this slice exists for
#   3 GAP     — no correction / anaphora model exists
#   4 satisfied — kept as a note, because no pressure path is readable
#   5 GAP     — read as a run REFERENCE, not as an operation, and it withholds
#               every candidate in the transcript
#   6 satisfied — nothing is overridden; GAP on "inheritance understood"
#   7 partly  — nothing is accepted, but a distrust clause is inert


def test_cap009_case_1_a_single_explicit_value_is_read_with_its_source():
    """CASE 1 — "Temperature is 425 C."

    **THE CASE AS WRITTEN IS NOT SATISFIED, AND MUST NOT BE.** A celsius
    temperature yields NO candidate: the field is ``context.temperature_K`` and
    converting 425 C would place a number in the record that nobody stated, which
    ``CLAUDE.md`` §5 forbids. The reader ABSTAINS and says why — the outcome
    ``AMBIGUITY_POLICY``'s ``temperature_not_in_kelvin`` row already declares.

    The case's INTENT — one explicit statement, one candidate, explicit source,
    correct scope — is satisfied for the kelvin form, asserted second.
    """
    celsius = _read("Temperature is 425 C.")
    assert celsius.candidates == ()
    assert [a.kind for a in celsius.abstentions] == ["temperature_not_in_kelvin"]

    kelvin = _read("Temperature is 425 K.")
    assert len(kelvin.candidates) == 1
    candidate = kelvin.candidates[0]
    assert candidate.field_path == TEMPERATURE
    assert candidate.proposed_value == 425
    # EXPLICIT SOURCE: the sentence, its character span, the rule, the origin.
    assert candidate.quote == "Temperature is 425 K."
    assert candidate.origin == "transcript"
    assert candidate.produced_by == tc.PRODUCED_BY
    assert candidate.rule
    assert candidate.provenance["segment_index"] == 0
    # SCOPE, SAFELY KNOWN: the run the scientist SELECTED, never one inferred.
    assert candidate.provenance["run_id"] == "run-1"
    assert kelvin.run_target == "run-1"
    assert candidate.verified is False


def test_cap009_case_2_around_425_maybe_430_is_unresolved_with_both_kept():
    """CASE 2 — "Temperature is around 425, maybe 430." **SATISFIED.**

    Two readings, and the distinction is the thing this slice measured:

    * The owner's literal words carry NO unit. ``_TEMPERATURE_K`` requires kelvin,
      so the sentence proposes NOTHING — 425 never became a candidate, so it could
      not silently become the value either. The requirement holds here by refusal.
    * With the unit the rule requires, the sentence used to propose 425 ALONE. That
      is where the silent preference lived, and it is now two candidates, grouped,
      neither preferred.
    """
    unitless = _read("Temperature is around 425, maybe 430.")
    assert unitless.candidates == ()
    assert unitless.review_required == ()
    assert unitless.abstentions == ()
    # Nothing is proposed, and the words are still a segment that becomes a note.
    assert unitless.unmapped_segment_indexes == (0,)

    with_unit = _read("Temperature is around 425 K, maybe 430 K.")
    assert _values(with_unit, TEMPERATURE) == [425, 430]
    assert with_unit.review_required[0].kind == "conflicting_values_for_one_field"
    assert with_unit.candidate_for_segment(0) is None


def test_cap009_case_3_a_correction_is_preserved_but_not_applied():
    """CASE 3 — "Actually, make that 430." **GAP: no correction model exists.**

    Measured: the sentence alone proposes nothing, and in context after a
    temperature statement the reading STILL proposes only 425 — the correction is
    inert, because "that" is an anaphor and no rule resolves one. The reader has no
    notion of a later statement superseding an earlier one.

    WHAT IS SATISFIED: it is preserved (every segment becomes a note), and there is
    **no duplicate authoritative mutation** — exactly one proposal is minted and it
    is the one the labelled sentence produced, not a second one for 430.

    WHAT IS NOT: the scientist's correction is not proposable, so accepting it means
    typing 430 by hand. Closing this needs a correction/supersession model the
    reader does not have and that this slice deliberately does not invent — deciding
    that a later sentence overrides an earlier one is a preference, and rule (3)
    refuses to resolve ambiguity by preference.
    """
    alone = _read("Actually, make that 430.")
    assert alone.candidates == ()
    assert alone.review_required == ()

    in_context = _read("Temperature was 425 K. Actually, make that 430.")
    assert _values(in_context, TEMPERATURE) == [425]
    assert in_context.review_required == ()
    assert in_context.unmapped_segment_indexes == (1,)

    # Even with the unit present, the correction is not read: the second sentence
    # carries no label, and no rule spans a sentence boundary.
    with_unit = _read("Temperature was 425 K. Actually, make that 430 K.")
    assert _values(with_unit, TEMPERATURE) == [425]


def test_cap009_case_4_a_free_text_observation_is_kept_as_a_note():
    """CASE 4 — "Pressure looked unstable halfway through." **SATISFIED.**

    Mapped nowhere, because no safe path exists: ``READABLE_FIELD_PATHS`` holds five
    run-level paths and NONE of them is a pressure, so there is no address to
    propose at. It is not an abstention either — the reader does not recognise the
    subject at all; it is the default ``unmatched_text`` outcome, stored verbatim.

    The gap this documents is a capability gap, not a correctness one: a pressure
    statement has no readable field, and inventing one would be a schema decision
    nobody made.
    """
    reading = _read("Pressure looked unstable halfway through.")
    assert reading.candidates == ()
    assert reading.abstentions == ()
    assert reading.clarifications == ()
    assert reading.unmapped_segment_indexes == (0,)
    assert "pressure" not in " ".join(tc.READABLE_FIELD_PATHS).lower()


def test_cap009_case_4_the_observation_is_stored_verbatim(client, experiment_id):
    run = _make_run(client, experiment_id)
    text = "Pressure looked unstable halfway through."
    payload = _finalize(client, experiment_id, text, run_id=run["id"]).json()
    assert payload["candidates"] == []
    assert payload["proposals"] == []
    stored = _notes(client, experiment_id)
    assert [note["text"] for note in stored] == [text]
    assert stored[0]["candidate_field_path"] is None


def test_cap009_case_5_start_run_19_is_not_a_scientific_claim_but_is_not_an_operation():
    """CASE 5 — "Start Run 19." **GAP, and it costs more than it looks.**

    WHAT IS SATISFIED: it produces no candidate, so it is never mistaken for a
    scientific value.

    WHAT IS NOT: it is not recognised as an application operation either. There is
    no command/operation vocabulary in this reader — ``_RUN_REFERENCE`` matches
    ``Run 19``, the record has no such run, and the result is an
    ``unknown_run_reference`` clarification.

    THE CONSEQUENCE IS THE PART TO CARRY FORWARD: a run clarification leaves the run
    target UNSETTLED, and an unsettled target withholds **every candidate in the
    whole transcript**. So one operational utterance suppresses the readings of
    every other sentence, as the second assertion measures. Nothing is lost — every
    word is still stored — but a scientist who dictates "Start Run 19" before
    describing the run gets no proposals at all and is not told why in those terms.
    """
    reading = _read("Start Run 19.")
    assert reading.candidates == ()
    assert [c.kind for c in reading.clarifications] == ["unknown_run_reference"]
    assert reading.clarifications[0].outcome == tc.OUTCOME_CLARIFICATION

    # THE COST, MEASURED: the temperature in the next sentence is withheld too.
    mixed = _read("Start Run 19. Temperature was 425 K.")
    assert mixed.candidates == ()
    assert mixed.run_target is None
    assert [c.kind for c in mixed.clarifications] == ["unknown_run_reference"]
    # Every word survives regardless.
    assert mixed.unmapped_segment_indexes == (0, 1)


def test_cap009_case_6_an_inherited_value_produces_no_override():
    """CASE 6 — "We're still using catalyst batch B." **SATISFIED in the one way
    that matters; GAP on the rest.**

    WHAT IS SATISFIED, and it is the requirement's operative half: **no unnecessary
    override.** Nothing is proposed, nothing is written, and no run override is
    created — so an experiment-level value keeps being inherited rather than being
    shadowed by a run-level copy of itself.

    WHAT IS NOT: the reader has no model of inheritance and does not "understand"
    the sentence. There is no catalyst/sample field in ``READABLE_FIELD_PATHS`` and
    no rule that compares a spoken value against an inherited one, so the correct
    outcome here is reached because the subject is unreadable, not because
    inheritance was reasoned about. If a sample field ever becomes readable, this
    case needs its own inheritance comparison and this test will not cover it.
    """
    reading = _read("We're still using catalyst batch B.")
    assert reading.candidates == ()
    assert reading.abstentions == ()
    assert reading.clarifications == ()
    assert reading.unmapped_segment_indexes == (0,)


def test_cap009_case_6_no_run_override_is_created(client, experiment_id):
    run = _make_run(client, experiment_id)
    before = [(row["fields"], row["inherited"]) for row in _runs(client, experiment_id)]
    payload = _finalize(
        client, experiment_id, "We're still using catalyst batch B.", run_id=run["id"]
    ).json()
    assert payload["candidates"] == []
    assert payload["proposals"] == []
    after = [(row["fields"], row["inherited"]) for row in _runs(client, experiment_id)]
    assert after == before
    assert after == [({}, {})]


def test_cap009_case_7_a_distrusted_reading_is_never_silently_accepted():
    """CASE 7 — "Pressure is 2 torr... actually I don't trust that reading."
    **SATISFIED for the case as written; PARTLY for its intent.**

    As written it is satisfied twice over: there is no readable pressure path, so no
    value is proposed, and both sentences are stored.

    THE HONEST VERSION OF THE CASE uses a field the reader CAN read, and there the
    intent is only partly met: the value IS proposed and the distrust clause is
    inert. Nothing is silently *accepted* — a candidate is not a value, it carries
    ``verified: False`` and ``requires_user_confirmation: True``, and a person must
    accept its proposal — but the reader does not connect "I don't trust that" to
    the candidate, so it neither withdraws it nor flags it.

    GAP: no retraction/hedge model. Closing it means deciding that a later sentence
    invalidates an earlier one, which is the same preference case 3 declines.
    """
    as_written = _read("Pressure is 2 torr... actually I don't trust that reading.")
    assert as_written.candidates == ()
    assert as_written.unmapped_segment_indexes == (0, 1)

    readable = _read("Temperature is 425 K... actually I don't trust that reading.")
    assert _values(readable, TEMPERATURE) == [425]
    # NOT silently accepted: it is a candidate, not a value.
    only = readable.candidates[0]
    assert only.verified is False
    assert only.requires_user_confirmation is True
    assert only.status == "needs_confirmation"
    assert only.is_evidence is False
    assert readable.applied is False
    # The distrust clause is preserved, and it is inert.
    assert readable.unmapped_segment_indexes == (1,)


def test_cap009_case_7_the_distrusted_value_is_not_written_anywhere(
    client, experiment_id
):
    """The strongest form of "never silently accepted": the run still holds nothing.

    MUTATION: applying a candidate at capture time turns this RED.
    """
    run = _make_run(client, experiment_id)
    payload = _finalize(
        client,
        experiment_id,
        "Temperature is 425 K... actually I don't trust that reading.",
        run_id=run["id"],
    ).json()
    assert [entry["proposed_value"] for entry in payload["candidates"]] == [425]
    stored = next(row for row in _runs(client, experiment_id) if row["id"] == run["id"])
    assert _run_content(stored) == {"fields": {}, "inherited": {}}, stored
    assert "425" not in repr(_run_content(stored)), stored
    # Both sentences are stored, including the one that retracts. Asserted as a
    # SET: the retraction's presence is the claim, and notes are ordered by
    # ``(captured_utc, id)`` over a second-granularity clock, so a positional
    # index would be asserting an ordering this test is not about.
    stored_notes = _notes(client, experiment_id)
    assert len(stored_notes) == 2
    assert {note["text"] for note in stored_notes} == {
        "Temperature is 425 K...",
        "actually I don't trust that reading.",
    }


# =============================================================================
# C-1 — THE ADJACENCY GATE. Independent review, 2026-09-12.
# =============================================================================
#
# THE DEFECT, AND WHY IT IS WORSE THAN THE ONE THIS FILE WAS WRITTEN TO FIX.
# ``read_transcript``'s pass two applied ``rule.restatement.finditer`` over the
# WHOLE remainder of the segment, with no clause bound and no adjacency test. So a
# bare ``<number> K`` or a bare instant ANYWHERE later in the sentence became an
# "alternative value for the same field" — and shipped a ``rule`` string saying the
# sentence had restated the quantity. Measured at `47fdbe30`, in-process:
#
#   "The temperature was 425 K, ramped at 3 K/min"              -> 425 AND 3
#   "The temperature was 425 K and the step size was 0.5 K"     -> 425 AND 0.5
#   "Sample temperature 425 K, cryostat setpoint 80 K, base 4 K"-> 425, 80, 4
#   "The temperature was 425 K and the pressure was 3 K"        -> 425 AND 3
#   "...started ...01-01T00:00:00Z, ran until ...01-02T00:00:00Z" -> END as START
#   "...started ...01-01T00:00:00Z and we will repeat it ...02-01T00:00:00Z"
#                                                               -> a FUTURE instant
#
# ``main`` proposes only the labelled value in every one of them. A silent omission
# (the defect this file fixed) loses a reading; a silent assertion INVENTS one, and
# ``CLAUDE.md`` §5 forbids the second in terms. The cross-rule
# ``claimed_value_spans`` guard could not see any of it: it catches a value another
# RULE matched under its OWN label, and "ran until", "pressure", "K/min" and
# "repeat it" are not rules.
#
# THE GATE: the text between the end of the previous accepted reading of that rule
# and the start of this restatement's VALUE must consist ENTIRELY of an optional
# comma, optional whitespace, and exactly one connective from a closed hedge list.

#: The six sentences above, each of which must now yield exactly ONE candidate.
#: Written out rather than generated, so the corpus is readable in the failure.
FALSE_RESTATEMENTS: tuple[tuple[str, str, object], ...] = (
    ("ramp rate", "The temperature was 425 K, ramped at 3 K/min", 425),
    ("step size", "The temperature was 425 K and the step size was 0.5 K", 425),
    (
        "two other instruments",
        "Sample temperature 425 K, cryostat setpoint 80 K, base 4 K",
        425,
    ),
    ("a pressure", "The temperature was 425 K and the pressure was 3 K", 425),
    (
        "the END instant read as a START",
        "The scan started 2026-01-01T00:00:00Z, ran until 2026-01-02T00:00:00Z",
        "2026-01-01T00:00:00Z",
    ),
    (
        "a FUTURE run's instant read as this one's START",
        "The scan started 2026-01-01T00:00:00Z and we will repeat it "
        "2026-02-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
    ),
)

#: Every hedged form that must still read both values, including the owner's.
HEDGED_RESTATEMENTS: tuple[tuple[str, list], ...] = (
    ("The temperature was around 425 K, maybe 430 K", [425, 430]),
    ("The temperature was 425 K or perhaps 430 K", [425, 430]),
    ("The temperature was 425 K, or maybe 430 K", [425, 430]),
    ("The temperature was 425 K and again 430 K", [425, 430]),
    # ~~("The temperature was about 425 K, about 430 K", [425, 430]),~~ —
    # **WITHDRAWN 2026-09-12 by the project owner's own instruction, and kept here
    # struck rather than deleted because it was a MUST-PASS and a future session
    # would otherwise read its absence as an oversight.** A BARE `about` no longer
    # bridges: it is an approximation modifier of what FOLLOWS it, so admitting it
    # also admitted `"425 K, about 3 K above target"` -> an offset read as a
    # temperature. `"or about 430 K"` still reads. The withdrawn sentence is now
    # expected residue and is pinned as such in
    # `test_transcript_capture_hedge_and_unit_gate.py`.
    ("The temperature was 425 K, or about 430 K", [425, 430]),
    (
        "The run started 2026-01-01T00:00:00Z, or maybe 2026-01-02T00:00:00Z",
        ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
    ),
    ("The temperature was 425 K, maybe 430 K, or perhaps 435 K", [425, 430, 435]),
)


@pytest.mark.parametrize(
    "label,sentence,only", FALSE_RESTATEMENTS, ids=[row[0] for row in FALSE_RESTATEMENTS]
)
def test_an_unhedged_second_value_is_NOT_read_as_a_restatement(label, sentence, only):
    """Exactly ONE candidate — the label-anchored one — and it is not a restatement.

    MUTATION: deleting the ``_HEDGE_BRIDGE.fullmatch`` guard from
    ``_segment_readings`` turns all six of these RED.
    """
    reading = _read(sentence)
    assert len(reading.candidates) == 1, [
        (candidate.field_path, candidate.proposed_value)
        for candidate in reading.candidates
    ]
    candidate = reading.candidates[0]
    assert candidate.proposed_value == only
    assert candidate.provenance["restated_in_same_sentence"] is False
    # No contradiction was manufactured either: one value is not a disagreement.
    assert reading.review_required == ()


@pytest.mark.parametrize(
    "sentence,expected", HEDGED_RESTATEMENTS, ids=[row[0][:44] for row in HEDGED_RESTATEMENTS]
)
def test_a_hedged_second_value_IS_read_as_a_restatement(sentence, expected):
    """The requirement the gate had to preserve, including the owner's sentence.

    MUTATION: dropping any connective from ``_HEDGE_CONNECTIVES`` turns one of
    these RED; dropping the ``(?:or\\s+)?`` prefix turns two RED.
    """
    reading = _read(sentence)
    assert [candidate.proposed_value for candidate in reading.candidates] == expected
    restated = [
        candidate.provenance["restated_in_same_sentence"]
        for candidate in reading.candidates
    ]
    # The first is label-anchored; every later one is a hedged restatement.
    assert restated == [False] + [True] * (len(expected) - 1)
    # And every restatement's own `rule` string states the MECHANISM, because that
    # is what a scientist reads to check why the value was proposed.
    for candidate in reading.candidates[1:]:
        assert "HEDGING WORD" in candidate.rule
        assert "immediately between" in candidate.rule


def test_bare_and_is_not_a_hedge_because_it_is_conjunctive():
    """``and`` joins two quantities as readily as it restates one.

    Half the measured defect table is a bare ``and``. ``and again`` IS admitted,
    because ``again`` is what makes it one quantity said twice.

    MUTATION: adding ``and`` to ``_HEDGE_CONNECTIVES`` turns this RED, and would
    reopen "425 K and the pressure was 3 K".
    """
    assert "and" not in tc._HEDGE_CONNECTIVES
    assert "and again" in tc._HEDGE_CONNECTIVES
    assert tc._HEDGE_BRIDGE.fullmatch(" and ") is None
    assert tc._HEDGE_BRIDGE.fullmatch(" and again ") is not None
    assert _values(_read("The temperature was 425 K and 430 K"), TEMPERATURE) == [425]
    assert _values(
        _read("The temperature was 425 K and again 430 K"), TEMPERATURE
    ) == [425, 430]


def test_a_BARE_or_bridges_on_its_own():
    """``or`` is a connective in its own right, not only the optional prefix.

    **THIS TEST EXISTS BECAUSE A MUTATION SURVIVED.** Removing ``"or"`` from
    ``_HEDGE_CONNECTIVES`` left all 174 transcript tests GREEN: every ``or`` case
    in the parametrised corpus above is ``"or maybe"`` or ``"or perhaps"``, which
    the ``(?:or\\s+)?`` PREFIX handles without the connective. So the corpus looked
    like it covered ``or`` and covered only the prefix. Measured with ``"or"``
    dropped: ``"425 K or 430 K"`` and ``"425 K, or 430 K"`` both fall back to
    ``[425]``.

    ``or`` alone IS alternation — "it was 425 or 430" is a person naming two
    candidate values for one quantity — so reading both is the intended behaviour
    and this pins it.

    MUTATION: dropping ``"or"`` from ``_HEDGE_CONNECTIVES`` now turns this RED.
    """
    assert _values(_read("The temperature was 425 K or 430 K"), TEMPERATURE) == [
        425,
        430,
    ]
    assert _values(_read("The temperature was 425 K, or 430 K"), TEMPERATURE) == [
        425,
        430,
    ]
    # And the prefix is genuinely separate from the connective: BOTH spellings of
    # "or perhaps" must work, which is what concealed the gap.
    assert _values(
        _read("The temperature was 425 K or perhaps 430 K"), TEMPERATURE
    ) == [425, 430]


#: The reviewed closed hedge list, written out so the tuple below is a RATCHET in
#: BOTH directions rather than a list that checks itself.
#:
#: **RE-ORDERED 2026-09-12, MEMBERSHIP UNCHANGED, and that distinction is the whole
#: point of keeping this literal.** All eleven connectives are still admitted. Six
#: of them — ``about``, ``around``, ``roughly``, ``approximately``, ``possibly``,
#: ``again`` — moved from bridging BARE to bridging only behind a mandatory ``or``,
#: because they modify what FOLLOWS them rather than hedging what came before. The
#: module now DERIVES this union from ``_BARE_HEDGES + _OR_REQUIRED_HEDGES +
#: ("or",)`` so it cannot disagree with the pattern about membership; the SPLIT is
#: the thing a test has to pin separately, and ``REVIEWED_BARE_HEDGES`` /
#: ``REVIEWED_OR_REQUIRED_HEDGES`` below do that.
#:
#: **THIS LITERAL EXISTS BECAUSE A MUTATION SURVIVED A TEST THAT WALKED THE LIST.**
#: ``test_every_declared_connective_actually_bridges`` iterates
#: ``tc._HEDGE_CONNECTIVES``, so deleting ``"approximately"`` from it left all 176
#: transcript tests GREEN — the loop simply stopped checking the entry that had
#: been removed. A self-referential test detects an entry that does not WORK; it
#: cannot detect an entry that is GONE. Duplicating the list is the cost of
#: catching that, and it buys the right thing: widening or narrowing the set a
#: scientist's sentence is read under becomes a reviewed two-line change instead of
#: a one-line one.
REVIEWED_HEDGE_CONNECTIVES = (
    "maybe",
    "perhaps",
    "alternatively",
    "and again",
    "about",
    "around",
    "roughly",
    "approximately",
    "possibly",
    "again",
    "or",
)

#: The SPLIT, written out for the same reason the union is: a test that walks
#: ``tc._BARE_HEDGES`` cannot see a connective that has MOVED out of it, and moving
#: one is exactly the change that widens or narrows the set of sentences a
#: scientific value is read out of.
REVIEWED_BARE_HEDGES = ("maybe", "perhaps", "alternatively", "and again")
REVIEWED_OR_REQUIRED_HEDGES = (
    "about",
    "around",
    "roughly",
    "approximately",
    "possibly",
    "again",
)


def test_the_hedge_list_is_exactly_the_reviewed_closed_set():
    """A two-way ratchet on the set that decides whether a value is read at all,
    and on the SPLIT that decides how each member may appear.

    ~~"Order is asserted too, not just membership: the alternation is built by
    joining this tuple, and ``and again`` must precede ``again`` or the shorter
    alternative would win — which ``fullmatch`` would then reject, silently
    dropping ``and again``. So the ORDER is load-bearing and is pinned."~~ —
    **WITHDRAWN 2026-09-12: THE HAZARD WAS NEVER REAL, and the index comparison
    that pinned it proved nothing.** Two measurements retire it:

    * neither string is a prefix of the other — ``"again"`` begins ``ag`` and
      ``"and again"`` begins ``an`` — so ``again`` could never match where ``and
      again`` was intended; and
    * ``fullmatch`` does the OPPOSITE of what the claim says. It is exhaustive, so
      a short alternative that matches and then fails on the remainder causes the
      engine to BACKTRACK into the longer one. On ``("maybe", "maybe not")``, where
      one string genuinely IS a prefix of the other, ``" maybe not "`` bridges
      under BOTH orders.

    **A first attempt at this correction was itself wrong and is recorded because
    it is the more instructive error:** it said "the hazard was real; what changed
    is the mechanism holding it", and added a longest-first ``sorted()`` to
    ``_alternation`` as that mechanism. Mutation testing measured the sort to be an
    **equivalent mutant** — inverting it to shortest-first left all 249 transcript
    tests GREEN — so the sort was removed rather than kept with a false rationale.

    The assertions below therefore pin BEHAVIOUR, not order: ``and again`` bridges
    while bare ``again`` does not, which is a property of the SPLIT and is the thing
    that actually matters.

    MUTATION: adding OR removing any connective turns this RED; so does MOVING one
    between the bare and the ``or``-required branch, which is the change that
    widens or narrows what a scientific value is read out of. Removing
    ``"approximately"`` was GREEN across all 176 transcript tests before the union
    ratchet existed.
    """
    assert tc._HEDGE_CONNECTIVES == REVIEWED_HEDGE_CONNECTIVES
    assert tc._BARE_HEDGES == REVIEWED_BARE_HEDGES
    assert tc._OR_REQUIRED_HEDGES == REVIEWED_OR_REQUIRED_HEDGES
    # The union is DERIVED, so membership cannot drift from the pattern; the split
    # is what the two literals above exist to pin. Asserted as a partition: no
    # connective may sit in both branches, and none may be dropped from both.
    assert set(tc._BARE_HEDGES) & set(tc._OR_REQUIRED_HEDGES) == set()
    assert set(tc._BARE_HEDGES) | set(tc._OR_REQUIRED_HEDGES) | {"or"} == set(
        tc._HEDGE_CONNECTIVES
    )
    # The property that replaced the retired index assertion: `and again` bridges
    # while bare `again` does not. That is the SPLIT, and it is what a reader of
    # this tuple actually needs to know.
    assert tc._HEDGE_BRIDGE.fullmatch(" and again ") is not None
    assert tc._HEDGE_BRIDGE.fullmatch(" again ") is None


def test_every_declared_connective_actually_bridges():
    """A connective nobody exercises is a connective nobody has checked.

    The ``or`` gap was one entry of a hand-written list that no test walked. This
    walks the whole list, so an entry cannot be added inert. It deliberately
    iterates ``tc._HEDGE_CONNECTIVES`` rather than the reviewed literal, so the two
    tests fail for different reasons: this one for an entry that does not work, the
    ratchet above for an entry that should not be there or has gone missing.

    **SPLIT 2026-09-12, because the old single loop asserted something that is now
    FALSE for six of the eleven entries.** It required every connective to bridge
    BARE *and* behind ``or``. ``about``, ``around``, ``roughly``,
    ``approximately``, ``possibly`` and ``again`` now bridge ONLY behind ``or``, so
    the loop is two loops and the second one asserts the REFUSAL as well as the
    acceptance — a connective that was supposed to move branches and did not is
    then not silently green.

    MUTATION: adding a connective the pattern cannot match turns this RED; so does
    moving one between branches without moving it in the module.
    """
    assert tc._BARE_HEDGES, "an empty list would make this vacuous"
    assert tc._OR_REQUIRED_HEDGES, "an empty list would make this vacuous"

    for connective in tc._BARE_HEDGES:
        bare = f"The temperature was 425 K, {connective} 430 K"
        assert _values(_read(bare), TEMPERATURE) == [425, 430], bare
        prefixed = f"The temperature was 425 K, or {connective} 430 K"
        assert _values(_read(prefixed), TEMPERATURE) == [425, 430], prefixed

    for connective in tc._OR_REQUIRED_HEDGES:
        # BARE is refused — this half is the point of the split.
        bare = f"The temperature was 425 K, {connective} 430 K"
        assert _values(_read(bare), TEMPERATURE) == [425], bare
        prefixed = f"The temperature was 425 K, or {connective} 430 K"
        assert _values(_read(prefixed), TEMPERATURE) == [425, 430], prefixed

    # And the bare `or`, which is neither: it IS the prefix, standing alone.
    assert _values(
        _read("The temperature was 425 K, or 430 K"), TEMPERATURE
    ) == [425, 430]


def test_the_hedge_bridge_admits_no_clause_terminator_so_clause_bounding_is_free():
    """``_TEMPERATURE_K`` refuses to cross ``.;:`` and the restatement pass now
    cannot either — not by a second check, but because the bridge pattern admits
    only a comma, whitespace and letters.

    Stated as a test rather than only as a comment because the reviewer's
    alternative fix was clause-bounding, and the reason it was insufficient ALONE
    (two defect rows carry no punctuation) is easy to misread as "clause-bounding
    is not needed".

    MUTATION: widening ``_HEDGE_BRIDGE`` to admit ``[^;]`` turns this RED.
    """
    for terminator in (".", ";", ":"):
        assert tc._HEDGE_BRIDGE.fullmatch(f",{terminator} maybe ") is None
        assert tc._HEDGE_BRIDGE.fullmatch(f", maybe{terminator} ") is None
    # A LINE BREAK IS NOT A BRIDGE, and this assertion was RED on the first
    # implementation: the pattern used `\s*`, which admits `\n`, and `fullmatch`
    # rather than `$` does NOT close that — `$`'s before-a-trailing-newline laxity
    # is a different hole. `_H_SPACE` is the fix. Nothing live depended on it (a
    # segment cannot contain a newline), which is exactly why only a test found it.
    assert tc._HEDGE_BRIDGE.fullmatch(", maybe \n") is None
    assert tc._HEDGE_BRIDGE.fullmatch("\n maybe ") is None
    assert tc._HEDGE_BRIDGE.fullmatch(", maybe ") is not None
    # A non-breaking space still bridges: dictated text is not typed text, and
    # `[ \t]` would have refused this while `[^\S\n]` admits it.
    assert tc._HEDGE_BRIDGE.fullmatch(",\u00a0maybe\u00a0") is not None


def test_clause_bounding_alone_would_have_caught():
    """How much of the defect the REJECTED alternative fix would have closed.

    The review offered clause-bounding as an alternative and said it was
    insufficient because *"two of the rows above have no punctuation"*. Measured,
    it is insufficient by a wider margin, and in a different way:

    * on ``.;:`` — the bound ``_TEMPERATURE_K`` already imposes on itself — **0 of
      6** gaps contain any such character, so it refuses NOTHING;
    * breaking at a comma as well refuses **3 of 6**, not 4, and the three that
      survive are the bare-``and`` rows.

    Recorded as a test rather than a comment because it is the evidence for
    choosing the hedge gate over the cheaper fix, and because a reader who trusts
    the "two rows" phrasing would conclude clause-bounding was most of the answer.
    It was none of it.
    """
    rows = [
        ("The temperature was 425 K, ramped at 3 K/min", tc._TEMPERATURE_K, tc._TEMPERATURE_K_RESTATED),
        ("The temperature was 425 K and the step size was 0.5 K", tc._TEMPERATURE_K, tc._TEMPERATURE_K_RESTATED),
        ("Sample temperature 425 K, cryostat setpoint 80 K, base 4 K", tc._TEMPERATURE_K, tc._TEMPERATURE_K_RESTATED),
        ("The temperature was 425 K and the pressure was 3 K", tc._TEMPERATURE_K, tc._TEMPERATURE_K_RESTATED),
        ("The scan started 2026-01-01T00:00:00Z, ran until 2026-01-02T00:00:00Z", tc._ACQUIRED_START, tc._INSTANT_RESTATED),
        ("The scan started 2026-01-01T00:00:00Z and we will repeat it 2026-02-01T00:00:00Z", tc._ACQUIRED_START, tc._INSTANT_RESTATED),
    ]
    gaps = []
    for text, label_pattern, restatement in rows:
        labelled = label_pattern.search(text)
        assert labelled is not None, text
        extra = restatement.search(text, labelled.end())
        assert extra is not None, f"there IS a later value to be refused: {text}"
        gaps.append(text[labelled.end() : extra.start(1)])

    assert len(gaps) == 6
    assert sum(any(ch in gap for ch in ".;:") for gap in gaps) == 0
    assert sum("," in gap for gap in gaps) == 3
    # And the hedge gate refuses all six, which is the comparison that matters.
    assert sum(tc._HEDGE_BRIDGE.fullmatch(gap) is None for gap in gaps) == 6
    # A comma is NOT a clause break for this purpose: the owner's own sentence
    # bridges across one, so the cheaper fix would have broken the requirement.
    assert "," in "The temperature was around 425 K, maybe 430 K"
    assert _values(_read("The temperature was around 425 K, maybe 430 K"),
                   TEMPERATURE) == [425, 430]


def test_both_restatement_guards_refuse_started_A_and_ended_B():
    """The reviewer asked that the two independent guards be proven to AGREE here.

    ``"started A and ended B"`` is the one sentence both guards see: the overlap
    guard refuses B because ``acquisition_end`` claimed it under its own label, and
    the hedge guard refuses it because the gap is ``" and ended "``. They are
    measured separately rather than inferred from the outcome, because an outcome
    that two guards produce says nothing about either one.
    """
    text = "The scan started 2026-01-01T00:00:00Z and ended 2026-01-02T00:00:00Z"

    start = tc._ACQUIRED_START.search(text)
    end = tc._ACQUIRED_END.search(text)
    assert start is not None and end is not None

    # GUARD 1 — the cross-rule overlap guard. B's value span is claimed by the END
    # rule, so the START rule's restatement scan must see an overlap.
    restatement = tc._INSTANT_RESTATED.search(text, start.end())
    assert restatement is not None, "there IS a later instant to be refused"
    assert tc._spans_overlap(restatement.span(1), end.span(1)) is True

    # GUARD 2 — the hedge bridge, measured on the same gap, independently.
    bridge = text[start.end() : restatement.start(1)]
    assert bridge == " and ended "
    assert tc._HEDGE_BRIDGE.fullmatch(bridge) is None

    # AND THE READING AGREES WITH BOTH: two fields, one value each, neither restated.
    reading = _read(text)
    assert [
        (candidate.field_path, candidate.proposed_value) for candidate in reading.candidates
    ] == [
        ("timestamps.acquired_start_utc", "2026-01-01T00:00:00Z"),
        ("timestamps.acquired_end_utc", "2026-01-02T00:00:00Z"),
    ]
    assert all(
        candidate.provenance["restated_in_same_sentence"] is False
        for candidate in reading.candidates
    )


def test_a_refused_restatement_does_not_advance_the_adjacency_anchor():
    """The chain is a chain of HEDGES, not of positions.

    If a refused restatement advanced the anchor, then in "425 K, cryostat setpoint
    80 K, maybe 4 K" the gap before 4 would be measured from 80 and read as hedged
    — inventing a value two clauses away from anything that introduced it.

    MUTATION: moving ``anchor = extra.end()`` out of the accepted branch in
    ``_segment_readings`` turns this RED.
    """
    reading = _read("Sample temperature 425 K, cryostat setpoint 80 K, maybe 4 K")
    assert _values(reading, TEMPERATURE) == [425]


def test_the_anchor_DOES_advance_across_a_deduplicated_restatement():
    """Adjacency is a fact about the text, so a dropped duplicate still bridges.

    "425 K, maybe 425 K, or perhaps 430 K": the middle reading is accepted by the
    gate and then dropped as an identical value, and 430 must still be read.

    MUTATION: advancing the anchor only for readings that survive de-duplication
    turns this RED.
    """
    reading = _read("The temperature was 425 K, maybe 425 K, or perhaps 430 K")
    assert _values(reading, TEMPERATURE) == [425, 430]


def test_the_restatement_still_requires_the_label_to_come_first():
    """Unchanged by the gate: a hedged value BEFORE the label is not a restatement
    of it. Pass two still scans only from the end of the last labelled match."""
    assert _values(_read("At 300 K, maybe 310 K, the temperature was 425 K"),
                   TEMPERATURE) == [425]


def test_a_hedged_value_with_no_labelled_match_at_all_reads_nothing():
    """Pass two is still gated on pass one. A bare hedged number is never read."""
    assert _read("It was around 425 K, maybe 430 K").candidates == ()

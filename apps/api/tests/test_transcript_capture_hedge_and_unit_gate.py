"""The restatement gate is TWO conditions, and the C-1 fix shipped with one.

WHY THIS FILE EXISTS
====================
``c9a4c6e8`` closed C-1 by requiring a connective from a closed list to sit
immediately between the previous accepted reading and a restatement's value
(``_HEDGE_BRIDGE``, ``fullmatch``ed over the gap). It correctly refuses *"The
temperature was 425 K, ramped at 3 K/min"*.

**It was not sufficient, and the same §5 violation still shipped — through two
independent entrances.** Both were measured at ``c9a4c6e8`` in-process, through
``read_transcript(text, selected_run='r1', known_runs=(RunRef('r1','Run 1',1),))``:

**ENTRANCE ONE — six of the eleven connectives are not hedges at all.**
``about``, ``around``, ``roughly``, ``approximately``, ``possibly`` and ``again``
are **approximation modifiers of whatever FOLLOWS them**, not hedges on the value
before. *"about 3 K"* does not mean "the value I just gave might be 3 K"; it means
"3 K, approximately" — of *something*, named by the words after it. So the gap read
as a hedge while the value was a different quantity:

=========================================================================  ==============
sentence                                                                   falsely read
=========================================================================  ==============
``The temperature was 425 K, about 3 K above target``                      an OFFSET
``The temperature was 425 K, around 80 K colder than before``              a DIFFERENCE
``The temperature was 425 K, about 5 K of drift``                          a DRIFT
``The temperature was 425 K, roughly 2 K of scatter``                      a SCATTER
``The temperature was 425 K, approximately 10 K below the setpoint``       an OFFSET
``The temperature was 425 K, about 1 K per minute``                        a ramp RATE
``The temperature was 425 K, about 3 K.``                                  an OFFSET
``The temperature was 425 K, about 0.5 K per step``                        a STEP SIZE
``…started 2026-01-01T00:00:00Z, again 2026-01-02T00:00:00Z.``             a REPEAT
``…started 2026-01-01T00:00:00Z, about 2025-12-31T00:00:00Z plus one day`` an ARITHMETIC BASE
=========================================================================  ==============

**ENTRANCE TWO — the unit was not required to be the whole unit.** ``K\\b`` treats
``K/`` as a word boundary, so a ramp rate matched as kelvin behind a perfectly good
connective:

==========================================================  ==============
sentence                                                    falsely read
==========================================================  ==============
``The temperature was 425 K or 3 K/min``                    a ramp RATE
``The temperature was 425 K and again 3 K/min``             a ramp RATE
``The temperature was 425 K, alternatively 3 K/min``        a ramp RATE
==========================================================  ==============

**Those three are the ORIGINAL ramp-rate defect with a different connective**, and
two of them (``or``, ``and again``) survive the entrance-one correction entirely,
which is why neither half of the gate closes the other's cases.

THE FIX, AND A REJECTED FIX THAT IS WORTH RECORDING
===================================================
1. the six ambiguous connectives bridge ONLY behind a mandatory ``or``
   (``_OR_REQUIRED_HEDGES``) — ``or`` coordinates the new value WITH the old one,
   so the modifier is scoped inside an alternative for the same quantity;
2. the unit must be complete: the character after the match must be end-of-segment,
   whitespace, or one of a small closed punctuation set (``_UNIT_TERMINATORS``).

**A TERMINAL RULE WAS IMPLEMENTED FIRST, MEASURED, AND WITHDRAWN.** It required the
restatement to END the statement or continue a hedged chain. It is recorded here
with its measurements because it looked obviously right, it closes cases this gate
does not, and it was refuted on three counts:

* **it does not close the defect** — ``"425 K, about 3 K."`` is terminal, and read
  3; ``"425 K, about 3 K or 400 K."`` read 3 AND 400;
* **it costs six natural sentences their restatement** — all six are pinned below
  as still working, and the worst is ``"…maybe 430 K and the atmosphere was dry
  nitrogen"``, where the segment-end-anchored atmosphere rule's own text is the
  non-terminal tail;
* **it silently breaks an unrelated C-2 proof** — ``_bytes_only()`` needs FIVE
  candidates to exceed ``MAX_CANDIDATE_QUOTE_BYTES``; the terminal rule takes it to
  four (999,996 B against a 1,048,576 B cap), so the byte-ceiling test stops firing.
  **The C-1 gate and the C-2 proof are coupled and nobody expected that**; it is
  pinned below so the next person to touch either finds out from a test.

ONE CLASS IS STILL OPEN, AND IT IS PINNED AS OPEN
=================================================
A BARE hedge followed by a complete unit and then a modifying phrase still reads:
``"425 K, maybe 3 K of drift"`` proposes 3. ``_RESTATEMENT_RESIDUE`` carries the
four measured sentences and the argument that closing it is a DECISION between
error classes rather than a patch. The tests below assert the defect still occurs,
deliberately, so that closing it requires deleting a row rather than discovering a
surprise.

Everything here is synthetic. Nothing connects to a database and no network call is
made.
"""

from __future__ import annotations

import pytest

import isaac_api.routes as routes
import isaac_api.transcript_capture as tc

RUN = tc.RunRef(id="r1", label="Run 1", ordinal=1)
TEMPERATURE = "context.temperature_K"
START = "timestamps.acquired_start_utc"
END = "timestamps.acquired_end_utc"


def _read(text: str) -> tc.TranscriptReading:
    return tc.read_transcript(text, selected_run="r1", known_runs=(RUN,))


def _rows(text: str, field_path: str = TEMPERATURE) -> list[tuple]:
    """``(value, restated_in_same_sentence)`` per candidate at one field path."""
    return [
        (candidate.proposed_value, candidate.provenance["restated_in_same_sentence"])
        for candidate in _read(text).candidates
        if candidate.field_path == field_path
    ]


def _values(text: str, field_path: str = TEMPERATURE) -> list:
    return [value for value, _ in _rows(text, field_path)]


def _rule_for(field_path: str) -> tc._Rule:
    return next(entry for entry in tc._RULES if entry.field_path == field_path)


# =============================================================================
# 1. THE THIRTEEN SENTENCES. Each must yield exactly the label-anchored value.
# =============================================================================

#: The measured defect corpus, written out rather than generated, so it is readable
#: in the failure and so a row cannot be dropped from it silently. The fourth
#: element names WHICH HALF of the gate refuses the row, and it is asserted, because
#: an outcome two guards could produce says nothing about either one.
FALSE_RESTATEMENTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "an offset above target",
        "The temperature was 425 K, about 3 K above target",
        TEMPERATURE,
        "hedge",
    ),
    (
        "a difference from before",
        "The temperature was 425 K, around 80 K colder than before",
        TEMPERATURE,
        "hedge",
    ),
    ("a drift", "The temperature was 425 K, about 5 K of drift", TEMPERATURE, "hedge"),
    (
        "a scatter",
        "The temperature was 425 K, roughly 2 K of scatter",
        TEMPERATURE,
        "hedge",
    ),
    (
        "an offset below the setpoint",
        "The temperature was 425 K, approximately 10 K below the setpoint",
        TEMPERATURE,
        "hedge",
    ),
    (
        "a rate spelled per minute",
        "The temperature was 425 K, about 1 K per minute",
        TEMPERATURE,
        "hedge",
    ),
    (
        "an offset that ENDS the sentence",
        "The temperature was 425 K, about 3 K.",
        TEMPERATURE,
        "hedge",
    ),
    (
        "a step size",
        "The temperature was 425 K, about 0.5 K per step",
        TEMPERATURE,
        "hedge",
    ),
    (
        "a ramp rate behind a bare or",
        "The temperature was 425 K or 3 K/min",
        TEMPERATURE,
        "unit",
    ),
    (
        "a ramp rate behind and again",
        "The temperature was 425 K and again 3 K/min",
        TEMPERATURE,
        "unit",
    ),
    (
        "a ramp rate behind alternatively",
        "The temperature was 425 K, alternatively 3 K/min",
        TEMPERATURE,
        "unit",
    ),
    (
        "a REPEATED scan read as this one's start",
        "The scan started 2026-01-01T00:00:00Z, again 2026-01-02T00:00:00Z.",
        START,
        "hedge",
    ),
    (
        "an arithmetic base read as a start",
        "The scan started 2026-01-01T00:00:00Z, about 2025-12-31T00:00:00Z plus "
        "one day",
        START,
        "hedge",
    ),
)


@pytest.mark.parametrize(
    "label,sentence,field_path,refused_by",
    FALSE_RESTATEMENTS,
    ids=[row[0] for row in FALSE_RESTATEMENTS],
)
def test_a_non_restatement_is_NOT_read_as_a_restatement(
    label, sentence, field_path, refused_by
):
    """Exactly ONE candidate — the label-anchored one — and it is not a restatement.

    MUTATION: reverting ``_OR_REQUIRED_HEDGES`` into ``_BARE_HEDGES`` turns the ten
    ``hedge`` rows RED; deleting the ``_unit_is_complete`` guard turns the three
    ``unit`` rows RED. Neither mutation touches the other's rows, which is the
    independence of the two halves measured rather than asserted.
    """
    reading = _read(sentence)
    assert len(reading.candidates) == 1, [
        (candidate.field_path, candidate.proposed_value)
        for candidate in reading.candidates
    ]
    candidate = reading.candidates[0]
    assert candidate.field_path == field_path
    assert candidate.provenance["restated_in_same_sentence"] is False
    # No contradiction was manufactured either: one value is not a disagreement.
    assert reading.review_required == ()
    # AND THE WORDS ARE NOT LOST — rule (4) stores every segment verbatim. That is
    # the whole basis for preferring a fail-closed gate, so it is asserted here and
    # not merely asserted in prose.
    assert [segment.text for segment in reading.segments] == [sentence]


@pytest.mark.parametrize(
    "label,sentence,field_path,refused_by",
    FALSE_RESTATEMENTS,
    ids=[row[0] for row in FALSE_RESTATEMENTS],
)
def test_which_HALF_of_the_gate_refuses_each_row(label, sentence, field_path, refused_by):
    """The two halves, measured separately on every row.

    This is the discipline ``test_both_restatement_guards_refuse_started_A_and_ended_B``
    established in the sibling file: an outcome that two guards agree on says nothing
    about either one, so each row records which half does the work and that is
    checked against the guards directly rather than inferred from the reading.
    """
    rule = _rule_for(field_path)
    assert rule.restatement is not None
    labelled = list(rule.pattern.finditer(sentence))
    assert labelled, sentence
    anchor = max(match.end() for match in labelled)
    extra = rule.restatement.search(sentence, anchor)
    assert extra is not None, f"there IS a later value to be refused: {sentence}"

    bridged = tc._HEDGE_BRIDGE.fullmatch(sentence[anchor : extra.start(1)]) is not None
    unit_complete = tc._unit_is_complete(sentence, extra)

    if refused_by == "hedge":
        assert bridged is False, "the hedge half must be the one refusing this row"
        # The unit half would NOT have caught it, which is why both are needed.
        assert unit_complete is True
    else:
        assert refused_by == "unit"
        assert bridged is True, "the connective here is a perfectly good one"
        assert unit_complete is False


def test_every_one_of_the_thirteen_was_admitted_by_the_FIRST_gate():
    """The evidence that the shipped C-1 gate was necessary and NOT sufficient.

    Reconstructs the pre-correction bridge — every reviewed connective admitted
    BARE, no unit check — and shows all thirteen gaps bridging under it. Without
    this, "the first gate was insufficient" is a claim about a commit nobody can
    run from here.
    """
    old_bridge = tc.re.compile(
        r",?[^\S\n]*(?:or[^\S\n]+)?(?:"
        + "|".join(
            connective.replace(" ", "[^\\S\n]+")
            for connective in ("and again",) + tuple(
                entry for entry in tc._HEDGE_CONNECTIVES if entry != "and again"
            )
        )
        + r")[^\S\n]*",
        tc.re.IGNORECASE,
    )
    admitted = 0
    for _, sentence, field_path, _ in FALSE_RESTATEMENTS:
        rule = _rule_for(field_path)
        assert rule.restatement is not None
        labelled = list(rule.pattern.finditer(sentence))
        anchor = max(match.end() for match in labelled)
        extra = rule.restatement.search(sentence, anchor)
        assert extra is not None
        if old_bridge.fullmatch(sentence[anchor : extra.start(1)]) is not None:
            admitted += 1
    assert admitted == 13, "the old gate admitted every measured row"


# =============================================================================
# 2. THE PRODUCT REQUIREMENT, UNCHANGED. The owner's sentence still reads both.
# =============================================================================

TRUE_RESTATEMENTS: tuple[tuple[str, list, str], ...] = (
    # THE OWNER'S SENTENCE.
    ("The temperature was around 425 K, maybe 430 K", [425, 430], TEMPERATURE),
    ("The temperature was 425 K or perhaps 430 K", [425, 430], TEMPERATURE),
    ("The temperature was 425 K, or maybe 430 K", [425, 430], TEMPERATURE),
    ("The temperature was 425 K and again 430 K", [425, 430], TEMPERATURE),
    ("The temperature was 425 K, alternatively 430 K", [425, 430], TEMPERATURE),
    ("The temperature was 425 K or 430 K", [425, 430], TEMPERATURE),
    # The withdrawn bare-`about` form, admitted behind an explicit `or`.
    ("The temperature was 425 K, or about 430 K", [425, 430], TEMPERATURE),
    ("The temperature was 425 K, or around 430 K", [425, 430], TEMPERATURE),
    # THE CHAIN.
    (
        "The temperature was 425 K, maybe 430 K, or perhaps 435 K",
        [425, 430, 435],
        TEMPERATURE,
    ),
    ("The temperature was 425 K, maybe 430 K.", [425, 430], TEMPERATURE),
    (
        "The run started 2026-01-01T00:00:00Z, or maybe 2026-01-02T00:00:00Z",
        ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
        START,
    ),
)


@pytest.mark.parametrize(
    "sentence,expected,field_path",
    TRUE_RESTATEMENTS,
    ids=[row[0][:48] for row in TRUE_RESTATEMENTS],
)
def test_a_genuine_hedged_restatement_IS_still_read(sentence, expected, field_path):
    """The requirement the correction had to preserve.

    MUTATION: moving any connective out of ``_BARE_HEDGES`` turns one of these RED;
    dropping the ``or`` + hedge branch turns four RED.
    """
    assert _values(sentence, field_path) == expected
    restated = [flag for _, flag in _rows(sentence, field_path)]
    assert restated == [False] + [True] * (len(expected) - 1)
    # And every restatement's own `rule` string states BOTH conditions, because that
    # is what a scientist reads to check why the value was proposed — and because
    # the previous two versions of that string each stated a gate smaller than the
    # one in force.
    for candidate in _read(sentence).candidates[1:]:
        assert "TWO conditions" in candidate.rule
        assert "HEDGING WORD" in candidate.rule
        assert "immediately between" in candidate.rule


def test_a_bare_or_is_alternation_and_still_bridges_even_before_an_instant():
    """``or`` alone is kept, deliberately, and it is the one connective the
    correction did NOT move.

    *"started A, or B"* is a person naming two candidate instants for one event,
    which is exactly what ``ReviewRequired`` exists to surface. ``or`` cannot
    modify a following noun phrase into a different quantity — it coordinates — so
    it carries none of the ambiguity ``about``/``again`` carry, and the ramp-rate
    sentence that reaches it (``"425 K or 3 K/min"``) is refused by the UNIT half
    instead.
    """
    assert _values("The temperature was 425 K or 430 K") == [425, 430]
    assert _values(
        "The scan started 2026-01-01T00:00:00Z, or 2026-01-02T00:00:00Z.", START
    ) == ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"]
    assert _values("The temperature was 425 K or 3 K/min") == [425]


# =============================================================================
# 3. THE REJECTED TERMINAL RULE. Its cost, measured, so it is not re-proposed.
# =============================================================================

#: Natural sentences whose restatement a TERMINAL rule would have refused. Each
#: reads both values today, and that is asserted — so a future slice that adopts a
#: terminal rule finds out from a test what it costs, rather than from a scientist.
TERMINAL_RULE_WOULD_HAVE_LOST: tuple[tuple[str, str, list, str], ...] = (
    (
        "a trailing aside",
        "The temperature was 425 K, maybe 430 K, I am not sure",
        [425, 430],
        TEMPERATURE,
    ),
    (
        "a trailing prepositional phrase",
        "The temperature was 425 K, maybe 430 K at the end",
        [425, 430],
        TEMPERATURE,
    ),
    (
        "a trailing attribution",
        "The temperature was 425 K, maybe 430 K according to the log",
        [425, 430],
        TEMPERATURE,
    ),
    (
        "a second field in the same sentence",
        "The temperature was 425 K, maybe 430 K and the atmosphere was dry nitrogen",
        [425, 430],
        TEMPERATURE,
    ),
    (
        "a trailing scan reference",
        "The temperature was 425 K, maybe 430 K on the second scan",
        [425, 430],
        TEMPERATURE,
    ),
    (
        "a trailing aside after an instant",
        "The scan started 2026-01-01T00:00:00Z, or maybe 2026-01-02T00:00:00Z, I "
        "would have to check",
        ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
        START,
    ),
)


@pytest.mark.parametrize(
    "label,sentence,expected,field_path",
    TERMINAL_RULE_WOULD_HAVE_LOST,
    ids=[row[0] for row in TERMINAL_RULE_WOULD_HAVE_LOST],
)
def test_the_rejected_terminal_rule_would_have_lost_these(
    label, sentence, expected, field_path
):
    """Six sentences that read correctly and would not under a terminal rule.

    The fourth is the one that settles it: a sentence stating a temperature
    alternative AND an atmosphere loses the alternative, because ``_ATMOSPHERE`` is
    anchored to the end of the segment and its own text is therefore the
    non-terminal tail. A gate cannot require a restatement to end the sentence in a
    reader whose other rules require their value to end the sentence.
    """
    assert _values(sentence, field_path) == expected


def test_the_C1_GATE_AND_THE_C2_BYTE_CEILING_PROOF_ARE_COUPLED():
    """``_bytes_only()`` needs FIVE candidates, and a terminal rule leaves four.

    **THIS COUPLING IS THE REASON THE TERMINAL RULE WAS REJECTED RATHER THAN
    FIXED-UP, AND IT WAS FOUND BY MEASUREMENT, NOT BY READING.** The C-2 byte
    ceiling is proved by a payload whose third temperature is a hedged restatement
    followed by an unrelated clause. Refuse that restatement and the payload drops
    under the cap, ``pytest.raises(TranscriptTooDense)`` never fires, and a
    currently-green ceiling test passes for a reason that has nothing to do with
    ceilings.

    Asserted as arithmetic on the real fixture rather than on quoted numbers, so it
    cannot rot: if someone changes the payload or either constant, this recomputes.
    """
    from test_transcript_capture_ceilings import _bytes_only

    text = _bytes_only()
    assert len(tc.segment_transcript(text)) == 1
    segment_bytes = len(text.encode("utf-8"))
    assert segment_bytes <= routes._MAX_TRANSCRIPT_BYTES

    # FIVE is what the fixture actually reads under the gate in force.
    with pytest.raises(tc.TranscriptTooDense) as raised:
        _read(text)
    assert raised.value.candidates == 5

    # And the margin is entirely the fifth candidate.
    assert segment_bytes * 5 > tc.MAX_CANDIDATE_QUOTE_BYTES
    assert segment_bytes * 4 <= tc.MAX_CANDIDATE_QUOTE_BYTES, (
        "at four candidates this payload is UNDER the cap, so a gate that refuses "
        "one of its restatements silently disarms the byte-ceiling proof"
    )


# =============================================================================
# 4. THE CLASS THAT IS STILL OPEN. Pinned AS OPEN, on purpose.
# =============================================================================


@pytest.mark.parametrize("sentence", tc._RESTATEMENT_RESIDUE)
def test_the_recorded_residue_is_still_a_FALSE_POSITIVE(sentence):
    """A KNOWN-OPEN §5 defect, asserted to still occur.

    **THIS TEST IS DELIBERATELY THE WRONG WAY ROUND, and that is the point.** A
    bare hedge followed by a complete unit and then a modifying phrase still reads,
    so ``_RESTATEMENT_RESIDUE``'s four sentences each propose a value the transcript
    does not state for that field. Asserting the defect means that closing it
    requires DELETING a row here — a reviewed change — rather than discovering that
    a documented open item quietly went away, or that a documented open item is
    still being published after it was fixed.

    ``_RESTATEMENT_RESIDUE``'s own comment carries the four mechanical proxies that
    were measured and rejected, and the reason this is a decision between error
    classes rather than a patch.
    """
    assert len(_values(sentence)) == 2, (
        "if this now reads ONE value the residue is CLOSED — delete the row from "
        "_RESTATEMENT_RESIDUE and say so, do not weaken this assertion"
    )
    assert _rows(sentence)[1][1] is True


def test_the_residue_list_is_a_two_way_ratchet():
    """A test that iterates the list it checks cannot see a REMOVAL from that list.

    This repository has been caught by exactly that: deleting ``"approximately"``
    from ``_HEDGE_CONNECTIVES`` left 176 transcript tests GREEN, because the only
    test that checked it walked the list.
    """
    assert len(tc._RESTATEMENT_RESIDUE) == 4
    assert "The temperature was 425 K, maybe 3 K of drift" in tc._RESTATEMENT_RESIDUE
    assert (
        "The temperature was 425 K, alternatively 3 K per minute"
        in tc._RESTATEMENT_RESIDUE
    ), "the one residue row that uses a connective other than maybe/perhaps"


def test_the_defect_corpus_and_the_must_pass_corpus_are_both_ratcheted():
    """The same protection for the two corpora the parametrised tests walk."""
    assert len(FALSE_RESTATEMENTS) == 13
    assert len(TRUE_RESTATEMENTS) == 11
    assert len(TERMINAL_RULE_WOULD_HAVE_LOST) == 6
    sentences = {row[1] for row in FALSE_RESTATEMENTS}
    # The three rows that are the ORIGINAL ramp-rate defect with a new connective.
    assert "The temperature was 425 K or 3 K/min" in sentences
    assert "The temperature was 425 K and again 3 K/min" in sentences
    assert "The temperature was 425 K, alternatively 3 K/min" in sentences
    # The row that refutes the terminal rule on its own terms.
    assert "The temperature was 425 K, about 3 K." in sentences
    # Both halves are exercised, so neither parametrisation can become vacuous.
    assert {row[3] for row in FALSE_RESTATEMENTS} == {"hedge", "unit"}
    assert sum(row[3] == "unit" for row in FALSE_RESTATEMENTS) == 3


# =============================================================================
# 5. THE DISCLOSURE. A refusal is no longer silent.
# =============================================================================


def test_a_refused_restatement_now_produces_a_disclosure():
    """The gate was silent, and the note read as MAPPED rather than unmapped.

    Measured at ``c9a4c6e8``: *"Temperature ramped 300 K, then 350 K, then 400 K."*
    gave one candidate (300), ``abstentions=[]``, ``review_required=()`` and
    ``candidate_by_segment={0: 0}`` — a sentence saying the temperature went to 400,
    filed as a note about 300, with nothing anywhere saying a value had been
    declined. The refusal is CORRECT; its invisibility was the defect.

    MUTATION: deleting the abstention loop from ``read_transcript`` turns this RED.
    """
    reading = _read("Temperature ramped 300 K, then 350 K, then 400 K.")
    assert [candidate.proposed_value for candidate in reading.candidates] == [300]
    assert [entry.kind for entry in reading.abstentions] == ["unhedged_further_values"]
    disclosure = reading.abstentions[0]
    assert disclosure.segment_index == 0
    assert "context.temperature_K" in disclosure.reason
    # IT ASSERTS NOTHING ABOUT THE WITHHELD NUMBERS. Not a count, not a value, not
    # a classification — not knowing what they are is why they were withheld.
    for withheld in ("350", "400"):
        assert withheld not in disclosure.reason
        assert withheld not in disclosure.quote
    # The quote is the LABEL-ANCHORED statement, which identifies the sentence
    # without reproducing the segment. Quoting the segment took the route's
    # response to 226,673 B on the 27 KB single-segment payload and tripped
    # `test_the_bare_dense_transcript_is_now_harmless_because_C1_refuses_it`.
    assert disclosure.quote == "Temperature ramped 300 K"
    assert len(disclosure.quote) < len(reading.segments[0].text)


def test_the_disclosure_is_deduplicated_and_bounded_by_construction():
    """At most ONE disclosure per segment per rule, whatever the transcript says.

    ``"temperature 1 C"`` repeated 16,384 times is one fact, and a disclosure that
    scaled with the text would add to an accumulator neither density ceiling sees
    (``_DISCLOSURE_CEILING_GAP``). This one cannot: the refusal set is keyed on the
    rule NAME.

    MUTATION: changing ``refused`` from a per-rule mapping to a list turns this RED.
    """
    many = "The temperature was 425 K, " + ", ".join(
        f"{value} K" for value in range(10000, 11000)
    )
    reading = _read(many)
    assert len(reading.segments) == 1
    assert [candidate.proposed_value for candidate in reading.candidates] == [425]
    assert len(reading.abstentions) == 1

    # And the ceiling that follows from it, stated as arithmetic over the real
    # constants rather than as a quoted number.
    assert len(tc._RULES) == 5
    assert tc.MAX_SEGMENTS * len(tc._RULES) == 500


def test_a_cross_rule_overlap_is_NOT_disclosed_as_a_withheld_value():
    """``"started A and ended B"`` withholds nothing, so it must claim nothing.

    B WAS read — by the end rule, under its own label — so a disclosure saying "a
    value here was not read" would be false. Only the two gates withhold a reading,
    and only they disclose.

    MUTATION: recording the overlap skip as a refusal turns this RED.
    """
    reading = _read(
        "The scan started 2026-01-01T00:00:00Z and ended 2026-01-02T00:00:00Z"
    )
    assert [
        (candidate.field_path, candidate.proposed_value)
        for candidate in reading.candidates
    ] == [
        (START, "2026-01-01T00:00:00Z"),
        (END, "2026-01-02T00:00:00Z"),
    ]
    assert reading.abstentions == ()


def test_a_clean_sentence_raises_no_disclosure():
    """The disclosure must not fire on a sentence with nothing to disclose,
    or it becomes noise a reader learns to ignore."""
    for clean in (
        "The temperature was 425 K",
        "The temperature was around 425 K, maybe 430 K",
        "The temperature was 425 K, maybe 430 K, or perhaps 435 K",
        "The atmosphere was dry nitrogen",
    ):
        assert _read(clean).abstentions == (), clean


# =============================================================================
# 6. THE UNIT-COMPLETENESS HALF, tested directly.
# =============================================================================


def test_the_unit_check_measures_from_the_UNIT_and_not_from_the_NUMBER():
    """``/min`` is a tail only because the check starts after ``K``.

    ``_TEMPERATURE_K_RESTATED`` matches ``3 K`` while group 1 is ``3``, so a check
    written against ``match.end(1)`` would see ``" K/min"`` — still refused here by
    luck, but it would refuse every legitimate restatement too, since ``" K"``
    begins with a space and the check would then be reading the unit as the tail.
    The two offsets are one character apart in the source and the wrong one is
    GREEN on the defect corpus, which is why this is pinned.
    """
    bad = "The temperature was 425 K or 3 K/min"
    match = tc._TEMPERATURE_K_RESTATED.search(bad, bad.index("or"))
    assert match is not None and match.group(1) == "3"
    assert bad[match.end() :] == "/min"
    assert bad[match.end(1) :] == " K/min"
    assert tc._unit_is_complete(bad, match) is False

    good = "The temperature was 425 K, maybe 430 K"
    ok = tc._TEMPERATURE_K_RESTATED.search(good, good.index("maybe"))
    assert ok is not None and ok.group(1) == "430"
    assert good[ok.end() :] == ""
    assert tc._unit_is_complete(good, ok) is True


def test_alternation_order_cannot_change_whether_a_gap_bridges():
    """The retired ordering claim, measured in both directions.

    ``_alternation``'s docstring and this file's sibling both used to assert that a
    longer connective must precede a shorter one "or the shorter alternative would
    win — which ``fullmatch`` would then reject". ``fullmatch`` does the OPPOSITE:
    it is exhaustive, so the engine backtracks out of the short alternative into the
    long one. A longest-first ``sorted()`` written on the strength of that claim was
    measured to be an **equivalent mutant** (inverting it left all 249 transcript
    tests green) and was removed.

    This pins the property so the sort is not re-added with a rationale nobody
    measured. It is stated on ``("maybe", "maybe not")`` — where one string
    genuinely IS a prefix of the other — because the pair the claim named,
    ``("again", "and again")``, shares no prefix at all and so could never have
    exhibited the hazard.
    """
    assert not "again".startswith("and again")
    assert not "and again".startswith("again")

    for order in (("maybe", "maybe not"), ("maybe not", "maybe")):
        pattern = tc.re.compile(
            rf",?{tc._H_SPACE}*(?:{tc._alternation(order)}){tc._H_SPACE}*",
            tc.re.IGNORECASE,
        )
        assert pattern.fullmatch(" maybe not ") is not None, order
        assert pattern.fullmatch(" maybe ") is not None, order

    # And the builder does not reorder: it preserves the tuple it is given, which
    # is what makes the two reviewed literals readable as the sets they are.
    assert tc._alternation(("b", "aa")) == "b|aa"


def test_the_unit_terminator_set_is_an_ALLOWLIST_and_is_ratcheted():
    """A closed punctuation set, so an unrecognised compound unit fails CLOSED.

    Written out here rather than iterated from the module, for the reason the hedge
    ratchet exists: a test that walks the set cannot see a member that has gone.

    MUTATION: adding ``"/"`` to ``_UNIT_TERMINATORS`` turns the three ``unit`` rows
    of ``FALSE_RESTATEMENTS`` RED as well as this.
    """
    assert tc._UNIT_TERMINATORS == frozenset(",.;:!?)]}\"'")
    assert len(tc._UNIT_TERMINATORS) == 11
    # The characters a compound unit is built from are all absent, which is the
    # property that matters and is stated as such.
    for composer in "/*^-·×%":
        assert composer not in tc._UNIT_TERMINATORS, composer


@pytest.mark.parametrize(
    "tail,complete",
    [
        ("", True),
        (" and the atmosphere was dry nitrogen", True),
        (".", True),
        (",", True),
        (";", True),
        (")", True),
        (" more text", True),
        ("/min", False),
        ("-edge", False),
        ("^-1", False),
        ("·s", False),
    ],
    ids=lambda value: repr(value) if isinstance(value, str) else str(value),
)
def test_what_may_follow_a_complete_unit(tail, complete):
    """Stated over whole sentences, not only over the predicate, so the allowlist is
    connected to the behaviour it decides."""
    sentence = f"The temperature was 425 K, maybe 430 K{tail}"
    expected = [425, 430] if complete else [425]
    assert _values(sentence) == expected, sentence


# =============================================================================
# 7. THE REFERRED C-2 GAP. Measured here, not fixed here.
# =============================================================================


def test_the_density_ceilings_still_do_not_bound_the_DISCLOSURES():
    """A pre-existing defect this slice deliberately did NOT close, pinned with its
    measurements so the next slice does not have to rediscover it.

    ``abstentions`` and ``clarifications`` are appended per regex MATCH, above the
    ``if not settled: continue`` that feeds the ceiling accumulators, so neither
    ceiling sees them and ``MAX_SEGMENTS`` does not bind because the payload is one
    segment. ``_DISCLOSURE_CEILING_GAP`` carries the specification for the fix and
    the reason per-segment deduplication is NOT one.

    **Asserted as the defect, like the residue above**: if a future slice bounds
    these, this test goes RED and must be inverted, which is the reviewed change.
    """
    assert "not bounded by either density ceiling" in tc._DISCLOSURE_CEILING_GAP

    unit = "temperature 1 C "
    text = unit * (routes._MAX_TRANSCRIPT_BYTES // len(unit))
    assert len(text.encode("utf-8")) <= routes._MAX_TRANSCRIPT_BYTES
    reading = _read(text)
    assert len(reading.segments) == 1
    assert len(reading.abstentions) == 16384
    assert reading.candidates == ()

    unit = "run zzz at 1 K "
    text = unit * (routes._MAX_TRANSCRIPT_BYTES // len(unit))
    assert len(text.encode("utf-8")) <= routes._MAX_TRANSCRIPT_BYTES
    reading = _read(text)
    assert len(reading.segments) == 1
    assert len(reading.clarifications) == 17476


def test_the_cap_comment_no_longer_claims_an_arithmetic_link_it_does_not_have():
    """``MAX_CANDIDATE_QUOTE_BYTES`` is a bare literal, and the invariant is held by
    a TEST rather than by the expression.

    A real import would be circular — ``routes`` imports ``transcript_capture`` —
    so the fix was the comment, not the constant. The INVARIANT is unchanged and
    ``test_transcript_capture_ceilings.py`` still holds it; what is pinned here is
    that the module no longer describes a mechanism it does not have.
    """
    import inspect

    source = inspect.getsource(tc)
    assert "so it follows that constant\n#: instead of drifting from it" not in source
    assert "it does not reference" in source
    assert "would be circular" in source
    # The invariant itself, re-derived rather than quoted.
    assert tc.MAX_CANDIDATE_QUOTE_BYTES == 4 * routes._MAX_TRANSCRIPT_BYTES

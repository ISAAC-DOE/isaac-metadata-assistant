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

3. **ADDED 2026-09-12, SECOND PASS** — a restatement behind a hedge that stands
   ALONE (no ``or`` in front of it) must END the statement: no WORD may follow it,
   unless what follows is another hedge bridge introducing a restatement that was
   itself ACCEPTED. ``_STATEMENT_END`` and ``_statement_ends_after``.

**THE TERMINAL RULE WAS IMPLEMENTED FIRST, MEASURED, WITHDRAWN — AND THEN ADOPTED
IN A NARROWER FORM.** The withdrawal is kept in full below, struck where it has
expired and marked where it still holds, because it was refuted on three counts and
the three did not all survive:

* ~~**it does not close the defect** — ``"425 K, about 3 K."`` is terminal, and
  read 3; ``"425 K, about 3 K or 400 K."`` read 3 AND 400~~ — **EXPIRED, not
  answered.** Both were measured against a gate in which ``about`` bridged BARE.
  Since correction 1 it does not, so both are refused by the FIRST condition and
  the first is a row of ``FALSE_RESTATEMENTS`` today. The objection was correct
  when it was written and is no longer about a reachable state;
* **it costs six natural sentences their restatement** — **STILL TRUE of the
  UNIVERSAL rule, and true of FIVE of the six under the narrowed one.** All five
  use a bare ``maybe``; the sixth uses ``or maybe`` and is untouched. The five are
  pinned below as ACCEPTED LOSSES, each with the disclosure that is the condition
  on which the loss was accepted — including ``"…maybe 430 K and the atmosphere was
  dry nitrogen"``, where the atmosphere value itself still reads;
* **it silently breaks an unrelated C-2 proof** — ``_bytes_only()`` needs FIVE
  candidates to exceed ``MAX_CANDIDATE_QUOTE_BYTES``; the UNIVERSAL rule takes it to
  ~~four (999,996 B against a 1,048,576 B cap)~~ **THREE (750,000 B against a
  1,048,576 B cap) — the inherited pair was measured against a gate without the
  chain-continuation clause, and is corrected here from a fresh mutation run**, so
  the byte-ceiling test stops firing.
  **The C-1 gate and the C-2 proof are coupled and nobody expected that**; it is
  pinned below so the next person to touch either finds out from a test.
  **THE NARROWED RULE DOES NOT BREAK IT, AND THAT IS MEASURED HERE RATHER THAN
  REASONED**: that payload's ``430 K`` is followed by another accepted restatement
  and its ``435 K`` sits behind an explicit ``or``, so the fixture still reads FIVE.

THE FOUR MEASURED RESIDUE SENTENCES ARE CLOSED; A NARROWER CLASS IS STILL OPEN
=============================================================================
``"425 K, maybe 3 K of drift"`` and its three siblings proposed 3 with **no
abstention at all**. All four now read 425 alone and each raises a
``trailing_text_after_further_values`` abstention; they are pinned as CLOSED in
``tc._RESTATEMENT_RESIDUE_CLOSED`` rather than deleted, so "the residue is closed"
stays a checkable claim.

**WHAT IS STILL OPEN IS THE SAME SHAPE BEHIND AN EXPLICIT ``or``** —
``"425 K or 3 K of drift"``, ``"425 K, or about 3 K of drift"`` and three more,
measured AFTER the fix and now carried by ``tc._RESTATEMENT_RESIDUE``. The tests
below assert that defect still occurs, deliberately, so that closing it requires
deleting a row rather than discovering a surprise. Why it was not also closed is in
that constant's own comment: extending condition 3 to the ``or`` branch disarms
C-2, and extending it to the bare-``or`` branch alone is a split whose only
justification would be which branch a fixture happens to use.

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
        # ~~`assert "TWO conditions" in candidate.rule`~~ — the gate has THREE
        # conditions since 2026-09-12 (second pass), and a `rule` string claiming
        # two would be the third version of this string to understate the gate it
        # describes. The module's `_Rule` docstring records all three corrections.
        assert "THREE conditions" in candidate.rule
        assert "TWO conditions" not in candidate.rule
        assert "HEDGING WORD" in candidate.rule
        assert "immediately between" in candidate.rule
        # The third condition is stated, and stated WITH ITS SCOPE — a string that
        # said "must end the statement" without "stood ALONE" would describe a gate
        # stricter than the one in force, which is the mirror of the two errors
        # already recorded.
        assert "ENDED the statement" in candidate.rule
        assert "stood ALONE" in candidate.rule


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

#: Natural sentences whose restatement a TERMINAL rule refuses. Each USED to read
#: both values; five of the six now read one, and the fifth element of each row is
#: what the slice that adopted the narrowed rule accepted losing.
#:
#: ~~"Each reads both values today, and that is asserted — so a future slice that
#: adopts a terminal rule finds out from a test what it costs, rather than from a
#: scientist."~~ — **the future slice was the next one, it did find out from this
#: test, and the cost is now the SUBJECT of the test rather than a warning about
#: it.** Five rows are ACCEPTED LOSSES and one is untouched, and the distinguishing
#: fact is mechanical: the untouched row bridges with ``or maybe``, so condition 3
#: does not reach it.
#:
#: **EVERY LOSS IS ASSERTED TO BE DISCLOSED.** That is the whole of why the trade
#: was takeable under §5 — *"If a value is not supported by evidence: leave it
#: missing, mark it needs_confirmation, ask a targeted question"* — and if a
#: refusal here could be silent the trade does not hold. The fourth row also
#: asserts that the ATMOSPHERE value it states still reads, because the loss must
#: be the restatement and not the sentence.
TERMINAL_RULE_WOULD_HAVE_LOST: tuple[tuple[str, str, list, str, list], ...] = (
    (
        "a trailing aside",
        "The temperature was 425 K, maybe 430 K, I am not sure",
        [425],
        TEMPERATURE,
        ["trailing_text_after_further_values"],
    ),
    (
        "a trailing prepositional phrase",
        "The temperature was 425 K, maybe 430 K at the end",
        [425],
        TEMPERATURE,
        ["trailing_text_after_further_values"],
    ),
    (
        "a trailing attribution",
        "The temperature was 425 K, maybe 430 K according to the log",
        [425],
        TEMPERATURE,
        ["trailing_text_after_further_values"],
    ),
    (
        "a second field in the same sentence",
        "The temperature was 425 K, maybe 430 K and the atmosphere was dry nitrogen",
        [425],
        TEMPERATURE,
        ["trailing_text_after_further_values"],
    ),
    (
        "a trailing scan reference",
        "The temperature was 425 K, maybe 430 K on the second scan",
        [425],
        TEMPERATURE,
        ["trailing_text_after_further_values"],
    ),
    (
        "a trailing aside after an instant, behind an explicit or — UNTOUCHED",
        "The scan started 2026-01-01T00:00:00Z, or maybe 2026-01-02T00:00:00Z, I "
        "would have to check",
        ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
        START,
        [],
    ),
)


@pytest.mark.parametrize(
    "label,sentence,expected,field_path,expected_abstentions",
    TERMINAL_RULE_WOULD_HAVE_LOST,
    ids=[row[0] for row in TERMINAL_RULE_WOULD_HAVE_LOST],
)
def test_the_terminal_rule_loses_these_and_DISCLOSES_every_loss(
    label, sentence, expected, field_path, expected_abstentions
):
    """Six sentences that read both values before the narrowed terminal rule. Five
    now read one, and every one of the five says so.

    The fourth is the one that was argued hardest, and it is still the interesting
    one: a sentence stating a temperature alternative AND an atmosphere loses the
    alternative, because ``_ATMOSPHERE`` is anchored to the end of the segment and
    its own text is therefore the non-terminal tail. The previous slice read that as
    a refutation — *"a gate cannot require a restatement to end the sentence in a
    reader whose other rules require their value to end the sentence"* — and it is
    instead the PRICE, paid knowingly: the atmosphere value still reads, the
    temperature alternative is reported as withheld, and the sentence survives
    verbatim as a note.

    MUTATION: removing the disclosure leaves the five VALUE assertions green and
    turns the five ABSTENTION assertions red, which is the point — a silent refusal
    passes the first half of this test and the trade does not hold without the
    second.
    """
    assert _values(sentence, field_path) == expected
    reading = _read(sentence)
    assert [entry.kind for entry in reading.abstentions] == expected_abstentions
    if expected_abstentions:
        # The reason must be TRUE of this refusal, which is why it is not the
        # `unhedged_further_values` sentence: the hedge was present.
        disclosure = reading.abstentions[0]
        assert "behind a hedging word" in disclosure.reason
        assert "does not\nstop there" not in disclosure.reason
        assert "ENDS the" in disclosure.reason
        assert field_path in disclosure.reason
        assert disclosure.segment_index == 0
    if label == "a second field in the same sentence":
        # THE LOSS IS THE RESTATEMENT, NOT THE SENTENCE.
        assert _values(sentence, "context.thermodynamics.atmosphere") == [
            "dry nitrogen"
        ]


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


@pytest.mark.parametrize("sentence", tc._RESTATEMENT_RESIDUE_CLOSED)
def test_the_four_recorded_residue_SENTENCES_ARE_NOW_CLOSED(sentence):
    """The §5 defect the previous slice measured and referred. **CLOSED.**

    ~~"A KNOWN-OPEN §5 defect, asserted to still occur. THIS TEST IS DELIBERATELY
    THE WRONG WAY ROUND … Asserting the defect means that closing it requires
    DELETING a row here — a reviewed change — rather than discovering that a
    documented open item quietly went away."~~ — the reviewed change is this one.
    The rows were NOT deleted; they moved to ``_RESTATEMENT_RESIDUE_CLOSED`` and
    the assertion was inverted, which keeps the four sentences themselves as the
    evidence that the class is shut rather than merely unmentioned.

    Each now reads ONE value and DISCLOSES the one it withheld. Both halves are
    asserted, because a silent refusal here would close the false positive and open
    a silent discard — rule (4) of the module docstring — in its place.
    """
    assert _values(sentence) == [425], (
        "if this reads TWO values again the residue has REOPENED; the second value "
        "is a drift, an offset or a rate, not a temperature"
    )
    assert [entry.kind for entry in _read(sentence).abstentions] == [
        "trailing_text_after_further_values"
    ]


@pytest.mark.parametrize("sentence", tc._RESTATEMENT_RESIDUE)
def test_the_residue_THAT_REMAINS_is_still_a_FALSE_POSITIVE(sentence):
    """A KNOWN-OPEN §5 defect, asserted to still occur. **NOT rounded down.**

    Condition 3 is scoped to the BARE-hedge branch, so the same shape behind an
    explicit ``or`` still proposes a drift figure as a temperature, and still does
    it silently. These five sentences were measured AFTER the fix, in-process, and
    are not inherited from the previous slice's corpus — which contained none of
    them, because it was assembled from sentences a scientist might plausibly say
    and none of these is one. That is an argument about likelihood, not about
    correctness, and it is recorded as such in ``_RESTATEMENT_RESIDUE``'s comment
    rather than used to call the class closed.

    Asserting the defect means that closing it requires DELETING a row here — a
    reviewed change — rather than discovering that a documented open item quietly
    went away, or that a documented open item is still being published after it was
    fixed.
    """
    assert len(_values(sentence)) == 2, (
        "if this now reads ONE value the residue is CLOSED — delete the row from "
        "_RESTATEMENT_RESIDUE and say so, do not weaken this assertion"
    )
    assert _rows(sentence)[1][1] is True
    # AND IT IS SILENT, which is the half that makes it a §5 defect rather than a
    # disclosed omission. Pinned so that a future slice which makes it merely
    # disclosed has to come through here.
    assert _read(sentence).abstentions == ()


def test_the_residue_lists_are_two_way_ratchets():
    """A test that iterates the list it checks cannot see a REMOVAL from that list.

    This repository has been caught by exactly that: deleting ``"approximately"``
    from ``_HEDGE_CONNECTIVES`` left 176 transcript tests GREEN, because the only
    test that checked it walked the list.

    Both lists are ratcheted, and the CLOSED one matters more: a slice that deleted
    a row from it would delete the evidence that the row is closed, and the
    parametrised test above would then pass by iterating fewer cases.
    """
    assert len(tc._RESTATEMENT_RESIDUE_CLOSED) == 4
    assert (
        "The temperature was 425 K, maybe 3 K of drift"
        in tc._RESTATEMENT_RESIDUE_CLOSED
    )
    assert (
        "The temperature was 425 K, alternatively 3 K per minute"
        in tc._RESTATEMENT_RESIDUE_CLOSED
    ), "the one closed row that uses a connective other than maybe/perhaps"

    assert len(tc._RESTATEMENT_RESIDUE) == 5
    assert "The temperature was 425 K or 3 K of drift" in tc._RESTATEMENT_RESIDUE
    assert (
        "The temperature was 425 K, or perhaps 2 K of scatter"
        in tc._RESTATEMENT_RESIDUE
    ), "the open row that pairs a bare hedge WITH an or, which is what exempts it"
    # The two lists are disjoint: a sentence cannot be both closed and open, and an
    # edit that moved one without removing it from the other would say it is.
    assert not (
        set(tc._RESTATEMENT_RESIDUE) & set(tc._RESTATEMENT_RESIDUE_CLOSED)
    )


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


def test_the_chain_LOSES_ITS_TAIL_AND_NOT_A_LINK():
    """The cascade. A ``while``, not an ``if``, and this is the difference.

    Condition 3 says a bare-hedged restatement is read when it ends the statement
    OR when another ACCEPTED restatement follows it. So dropping the last link can
    make the one before it non-terminal too, and the walk has to continue. With a
    single pass, *"425 K, maybe 430 K, and again 3 K of drift"* keeps 430 — whose
    only claim to being terminal is a restatement that was just refused.

    MUTATION: ``while`` -> ``if`` in ``_segment_readings`` turns the second case RED
    and leaves every other test in this file green.
    """
    # THE WALK STOPS AT THE FIRST SURVIVING LINK, which is what makes it a walk
    # inward from the tail and not a rule about the chain. 3 is dropped for its own
    # trailing phrase; 430 sits behind an explicit `or`, so condition 3 never
    # reaches it and it survives even though something now follows it.
    assert _values(
        "The temperature was 425 K, or perhaps 430 K, and again 3 K of drift"
    ) == [425, 430]
    # A BARE-hedged link cannot survive that, and the difference is only the
    # connective: with `maybe` in place of `or perhaps`, dropping 3 makes 430
    # non-terminal too.
    # TWO refusals cascading: 3 goes for its trailing phrase, and 430 goes because
    # what follows IT is now a bridge to a refusal rather than to a reading.
    assert _values(
        "The temperature was 425 K, maybe 430 K, and again 3 K of drift"
    ) == [425]
    # The chain is never broken in the MIDDLE: a link behind an explicit `or`
    # survives, and everything before it is terminal-by-chain.
    assert _values(
        "The temperature was 425 K, maybe 430 K, or perhaps 435 K"
    ) == [425, 430, 435]


def test_both_refusal_kinds_can_fire_for_one_rule_in_one_sentence():
    """Two different things were withheld, so two different things are said.

    The refusal map is keyed on ``(rule, kind)`` rather than on ``rule``, because a
    sentence can both state an unhedged further value AND hedge one that does not
    end the statement — and a single entry would report one of them and drop the
    other, which is the silent-refusal defect this disclosure exists to end.

    The order is ``_RULES`` order then kind order, never the order the gates
    happened to fire in, so the list is deterministic.

    MUTATION: keying ``refused`` on ``rule.name`` alone turns this RED.
    """
    reading = _read("The temperature was 425 K, maybe 430 K at the end, then 500 K")
    assert [candidate.proposed_value for candidate in reading.candidates] == [425]
    assert [entry.kind for entry in reading.abstentions] == [
        "unhedged_further_values",
        "trailing_text_after_further_values",
    ]


@pytest.mark.parametrize("sentence", tc._RESTATEMENT_RESIDUE_CLOSED)
def test_the_new_disclosure_asserts_nothing_about_the_withheld_VALUE(sentence):
    """Same discipline as ``unhedged_further_values``: not a count, not a value, not
    a classification. Not knowing what it is IS why it was withheld.

    The reason deliberately carries no numeric example either — see
    ``_REFUSAL_REASONS`` — because every digit that would read naturally there
    appears in these very sentences, so an example would be indistinguishable from
    a leak.
    """
    disclosure = _read(sentence).abstentions[0]
    assert disclosure.kind == "trailing_text_after_further_values"
    withheld = next(token for token in ("3 K", "2 K") if token in sentence)
    assert withheld not in disclosure.reason
    assert withheld not in disclosure.quote
    assert withheld[0] not in disclosure.reason
    # The quote is the LABEL-ANCHORED statement, not the segment: short, and it
    # identifies the sentence without reproducing it.
    assert disclosure.quote == "temperature was 425 K"
    assert len(disclosure.quote) < len(sentence)


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

    # AND THE SAME TRAP FOR CONDITION 3, which reads from the same offset and
    # whose docstring claims a test pins both. ``end(1)`` leaves ``" K"`` in the
    # remainder, and ``K`` is a letter, so the predicate would call every
    # legitimate restatement non-terminal and condition 3 would refuse the whole
    # product requirement — green on the defect corpus, which is why it is pinned.
    assert tc._statement_ends_after(good, ok.end()) is True
    assert tc._statement_ends_after(good, ok.end(1)) is False
    assert tc._statement_ends_after(bad, match.end()) is False


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


#: ``(tail, unit_is_complete, statement_ends)``. The two predicates are pinned
#: SEPARATELY and then against the reading, because three rows disagree between
#: them and an outcome two guards could produce says nothing about either one.
#:
#: ~~`(" and the atmosphere was dry nitrogen", True)`, and the non-breaking-space
#: text row~~ —
#: those rows asserted the READING, and the reading changed: the unit is still
#: complete (that is what the second column now says) and condition 3 refuses the
#: restatement anyway. Splitting the columns is what makes the change visible as
#: "a different guard refuses it" rather than as "the unit check broke".
UNIT_TAILS: tuple[tuple[str, bool, bool], ...] = (
    ("", True, True),
    (" and the atmosphere was dry nitrogen", True, False),
    (".", True, True),
    (",", True, True),
    (";", True, True),
    (")", True, True),
    (" more text", True, False),
    ("/min", False, False),
    ("-edge", False, False),
    ("^-1", False, False),
    ("·s", False, False),
)


@pytest.mark.parametrize(
    "tail,unit_complete,statement_ends",
    UNIT_TAILS,
    ids=[repr(row[0]) for row in UNIT_TAILS],
)
def test_what_may_follow_a_complete_unit(tail, unit_complete, statement_ends):
    """Stated over whole sentences AND over each predicate, so the allowlists are
    each connected to the behaviour they decide.

    A bare-hedged restatement is read only when BOTH columns are true, which is why
    the two punctuation-only tails — a trailing comma and a trailing bracket — are
    the interesting rows: they are the two that a first, tighter
    ``_STATEMENT_END`` (whitespace plus at most ONE sentence terminator) refused
    for no §5 gain, and they are the measurement that widened it.
    """
    sentence = f"The temperature was 425 K, maybe 430 K{tail}"
    match = tc._TEMPERATURE_K_RESTATED.search(sentence, sentence.index("maybe"))
    assert match is not None and match.group(1) == "430"
    assert tc._unit_is_complete(sentence, match) is unit_complete, sentence
    assert tc._statement_ends_after(sentence, match.end()) is statement_ends, sentence
    expected = [425, 430] if (unit_complete and statement_ends) else [425]
    assert _values(sentence) == expected, sentence


def test_the_statement_end_set_is_the_unit_terminator_set():
    """One reviewed punctuation allowlist, used by two predicates. See
    ``_STATEMENT_END``.

    Pinned character by character rather than by comparing two expressions, so a
    slice that re-spells either one has to come through here. The ``\n``
    exclusion is asserted too: a hedge or a tail on the far side of a line break is
    not "immediately after", and ``_H_SPACE`` exists for exactly that.
    """
    for character in tc._UNIT_TERMINATORS:
        assert tc._statement_ends_after(f"X{character}", 1) is True, character
    for character in " \t\xa0":
        assert tc._statement_ends_after(f"X{character}", 1) is True, repr(character)
    assert tc._statement_ends_after("X\n", 1) is False
    # ``\r`` IS admitted, and that is stated rather than left to be discovered: the
    # module's whitespace class is ``_H_SPACE`` = ``[^\S\n]``, which excludes the
    # line FEED and nothing else, and this predicate reuses it unchanged. A bare
    # ``\r`` with no word after it withholds nothing, so it is not a hole — but a
    # test asserting it were refused would be asserting a rule the module does not
    # have.
    assert tc._statement_ends_after("X\r", 1) is True
    assert tc._statement_ends_after("X\rmore text", 1) is False
    # And the composers the unit ratchet refuses are refused here too, which is the
    # coupling being defence in depth rather than a weakening.
    for composer in "/*^-·×%":
        assert tc._statement_ends_after(f"X{composer}", 1) is False, composer


def test_the_bare_hedge_bridge_is_exactly_branch_two():
    """``_BARE_HEDGE_BRIDGE`` admits a gap iff ``_HEDGE_BRIDGE`` does AND the
    connective came from ``_BARE_HEDGES`` with no ``or`` in front of it.

    Asserted in BOTH directions over every reviewed connective, because the whole
    load-bearing use of this pattern is deciding which branch admitted a gap, and a
    pattern that merely admitted MORE would silently widen condition 3 into the
    ``or`` branch — the exact extension ``_RESTATEMENT_RESIDUE`` records as NOT
    taken.

    MUTATION: building it from ``_HEDGE_CONNECTIVES`` instead of ``_BARE_HEDGES``
    turns this RED on six rows.
    """
    for connective in tc._HEDGE_CONNECTIVES:
        bare_gap = f", {connective} "
        or_gap = f", or {connective} "
        bare_admitted = tc._HEDGE_BRIDGE.fullmatch(bare_gap) is not None
        assert bare_admitted is (connective in tc._BARE_HEDGES + (tc._BARE_OR,)), (
            connective
        )
        # `_BARE_OR` is skipped here, and the skip is the measurement: `", or or "`
        # is NOT admitted (branch 1 requires a HEDGE after the `or`, and `or` is not
        # one), so an unconditional assertion over `_HEDGE_CONNECTIVES` would be
        # asserting something false about the reviewed set rather than about this
        # pattern.
        if connective != tc._BARE_OR:
            assert tc._HEDGE_BRIDGE.fullmatch(or_gap) is not None, connective
            # An `or` in front always takes it out of branch 2, including for a
            # connective that would have bridged bare.
            assert tc._BARE_HEDGE_BRIDGE.fullmatch(or_gap) is None, connective

        assert (tc._BARE_HEDGE_BRIDGE.fullmatch(bare_gap) is not None) is (
            connective in tc._BARE_HEDGES
        ), connective
    # A bare `or` is NOT branch 2, and that is the exemption the residue rests on.
    assert tc._BARE_HEDGE_BRIDGE.fullmatch(" or ") is None
    assert tc._HEDGE_BRIDGE.fullmatch(" or ") is not None


# =============================================================================
# 7. THE REFERRED C-2 GAP. Measured here, not fixed here.
# =============================================================================


def test_the_referred_disclosure_gap_is_CLOSED_by_MAX_DISCLOSURES():
    """The pre-existing defect the previous slice measured and referred. **CLOSED.**

    ~~"A pre-existing defect this slice deliberately did NOT close … Asserted as the
    defect, like the residue above: if a future slice bounds these, this test goes
    RED and must be inverted, which is the reviewed change."~~ — this is the
    reviewed change. Both payloads now RAISE, and the exact counts the previous
    slice measured are re-measured here from the refusal rather than quoted from its
    comment: **16,384** abstentions and **17,476** clarifications, on one segment
    each, at the transcript byte ceiling.

    The reason they were unbounded is unchanged and is why a third ceiling was
    needed rather than a widening of the first two: ``abstentions`` and
    ``clarifications`` are appended per regex MATCH, above the ``if not settled:
    continue`` that feeds the candidate accumulators, and ``MAX_SEGMENTS`` does not
    bind because the payload is ONE segment.

    MUTATION: removing ``MAX_DISCLOSURES`` from the ceiling check turns both
    ``pytest.raises`` RED; raising it above 17,476 turns both RED.
    """
    assert "CLOSED" in tc._DISCLOSURE_CEILING_GAP
    assert "not bounded by either density ceiling" not in tc._DISCLOSURE_CEILING_GAP

    unit = "temperature 1 C "
    text = unit * (routes._MAX_TRANSCRIPT_BYTES // len(unit))
    assert len(text.encode("utf-8")) <= routes._MAX_TRANSCRIPT_BYTES
    assert len(tc.segment_transcript(text)) == 1
    with pytest.raises(tc.TranscriptTooDense) as raised:
        _read(text)
    assert raised.value.disclosures == 16384
    assert raised.value.maximum_disclosures == tc.MAX_DISCLOSURES
    # The two OLDER ceilings are inside their limits on this payload, which is the
    # whole reason the third one had to exist and is asserted rather than implied.
    assert raised.value.candidates == 0
    assert raised.value.candidate_quote_bytes == 0

    unit = "run zzz at 1 K "
    text = unit * (routes._MAX_TRANSCRIPT_BYTES // len(unit))
    assert len(text.encode("utf-8")) <= routes._MAX_TRANSCRIPT_BYTES
    assert len(tc.segment_transcript(text)) == 1
    with pytest.raises(tc.TranscriptTooDense) as raised:
        _read(text)
    assert raised.value.disclosures == 17476
    assert raised.value.candidates == 0
    assert raised.value.candidate_quote_bytes == 0


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

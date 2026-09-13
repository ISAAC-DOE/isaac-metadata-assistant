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
* **it costs six natural sentences their restatement** — **TRUE, and it is the
  price that was paid.** The narrowed rule cost five of the six (all five bridge
  with a bare ``maybe``); the UNIVERSAL rule, in force since 2026-09-12 (third
  pass), costs all six, and a seventh (``"425 K or 430 K at the end"``) was added
  to the table for the bare-``or`` branch. All seven are pinned below as ACCEPTED
  LOSSES, each with the disclosure that is the condition on which the loss was
  accepted — including ``"…maybe 430 K and the atmosphere was dry nitrogen"``,
  where the atmosphere value itself still reads;
* ~~**it silently breaks an unrelated C-2 proof** — ``_bytes_only()`` needs FIVE
  candidates to exceed ``MAX_CANDIDATE_QUOTE_BYTES``; the UNIVERSAL rule takes it
  to THREE (750,000 B against a 1,048,576 B cap), so the byte-ceiling test stops
  firing. **The C-1 gate and the C-2 proof are coupled and nobody expected that.**~~
  — **EVERY WORD OF THAT WAS TRUE OF THE OLD FIXTURE, AND TREATING IT AS A FACT
  ABOUT THE GATE COST TWO SLICES.** It was a FIXTURE coupling: three of
  ``_bytes_only()``'s five candidates came from the restatement scan, so a
  resource-ceiling proof moved whenever a semantic decision moved, and the cheapest
  way to keep a ceiling test green was to keep admitting restatements.
  ``_bytes_only()`` is now built from LABEL-ANCHORED matches only — pass one, which
  no hedge, unit or terminal rule gates — and it reads FIVE under the universal
  rule, under a maximally strict condition 1, under a maximally strict condition 3
  and under a maximally permissive one.
  ``test_the_C1_GATE_AND_THE_C2_BYTE_CEILING_PROOF_ARE_NO_LONGER_COUPLED`` is the
  inversion of the test that pinned the coupling, and
  ``test_the_C2_BYTE_CEILING_PROOF_IS_DECOUPLED_FROM_THE_C1_GATE`` (beside the
  fixture) asserts the mechanism. **A resource-ceiling proof must not be hostage to
  a semantic gate.**

ALL NINE MEASURED RESTATEMENT SENTENCES ARE CLOSED; A DIFFERENT ENTRANCE IS OPEN
================================================================================
``"425 K, maybe 3 K of drift"`` and its three siblings proposed 3 with **no
abstention at all**; ``"425 K or 3 K of drift"`` and its four siblings, measured
after that fix, did the same behind an explicit ``or``. **All nine now read 425
alone and each raises a ``trailing_text_after_further_values`` abstention**, and all
nine are pinned as CLOSED in ``tc._RESTATEMENT_RESIDUE_CLOSED`` rather than deleted,
so "the residue is closed" stays a checkable claim.

**WHAT IS STILL OPEN IS NOT A RESTATEMENT AT ALL, AND THAT IS THE FINDING OF THE
THIRD PASS.** Three passes treated *"the reader proposes values the transcript does
not state"* as a property of pass two. The LABEL-ANCHORED rule of pass one has the
same defect: ``_TEMPERATURE_K`` bridges label to value with ``[^.;:]{0,40}?``, so
*"The temperature drift was 3 K"* proposes ``context.temperature_K = 3``, silently,
and has done since the rule was written. Seven such sentences are carried by
``tc._LABEL_OVERREACH_CLOSED`` and asserted BELOW to still occur, deliberately, so
closing the class requires deleting a row rather than discovering a surprise. They
are **pre-existing and measured as such** — identical readings against the pristine
module at ``ebc5c331`` — and are **not** what the three restatement conditions are
for; see that constant's comment for why every obvious proxy is worse than the
defect.

Everything here is synthetic. Nothing connects to a database and no network call is
made.
"""

from __future__ import annotations

import re

import pytest

import isaac_api.routes as routes
import isaac_api.transcript_capture as tc

RUN = tc.RunRef(id="r1", label="Run 1", ordinal=1)
TEMPERATURE = "context.temperature_K"
START = "timestamps.acquired_start_utc"
END = "timestamps.acquired_end_utc"
# The two FREE-PHRASE paths, added 2026-09-13 so scope item 8 of the closing brief
# -- "apply the same analysis to the other four readable fields" -- is asserted
# here rather than only reasoned about in a comment.
ATMOSPHERE = "context.thermodynamics.atmosphere"
ENVIRONMENT = "context.environment"


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
        # ~~"unit"~~ -> **"both" (2026-09-12, fourth pass), and a THIRD label was
        # added rather than the row relabelled "hedge".** `and again` moved to
        # `_OR_REQUIRED_HEDGES`, so condition 1 now refuses this row as well as
        # condition 2 — the unit is `K/min`, which was always incomplete. Calling it
        # "hedge" would have asserted `unit_complete is True`, which is FALSE here
        # (measured), and calling it "unit" asserts `bridged is True`, which is now
        # false. Only "both" is true of it, and a label that overstates which guard
        # does the work is exactly what this parametrisation exists to prevent. The
        # row is kept because it is one of the thirteen measured rows and
        # `test_every_one_of_the_thirteen_was_admitted_by_the_FIRST_gate` needs it.
        "a ramp rate behind and again",
        "The temperature was 425 K and again 3 K/min",
        TEMPERATURE,
        "both",
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


#: The rows of ``FALSE_RESTATEMENTS`` on which the SEQUENCE GATE (2026-09-13)
#: ADDITIONALLY withholds the label-anchored value, so the reading has ZERO
#: candidates rather than one.
#:
#: **NAMED AS A SET RATHER THAN BY RELABELLING THE ROW**, deliberately. The
#: ``refused_by`` column answers *"which half of the RESTATEMENT gate refuses the
#: second value?"* and the answer for this row is still ``hedge`` — bare ``again``
#: is in ``_OR_REQUIRED_HEDGES`` and that is unchanged and is still what
#: ``test_which_HALF_of_the_gate_refuses_each_row`` measures. What changed is a
#: DIFFERENT question about the FIRST value, and folding the two into one column
#: would make a label overstate which guard does the work — which is exactly the
#: mistake the "both" row's own comment records.
#:
#: Only ONE row qualifies, and the reason is the sequence gate's own conditions:
#: every other row puts an approximation (``about``), a rate (``per minute``,
#: ``K/min``) or a qualifying phrase after the second value, so the second value is
#: positively identified as a different quantity and the first survives. Here the
#: gap is ``, again `` — pure coordination — and the second instant is a complete,
#: unqualified instant, so the sentence states the field twice and says nothing
#: about which statement is the field's.
_ALSO_SEQUENCE_GATED: frozenset[str] = frozenset(
    {"The scan started 2026-01-01T00:00:00Z, again 2026-01-02T00:00:00Z."}
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

    ~~"Exactly ONE candidate"~~ — **true of 12 of the 13 rows since 2026-09-13.**
    See ``_ALSO_SEQUENCE_GATED`` for the one row where the sequence gate withholds
    the label value too, and for why it is expressed as a set rather than as a new
    ``refused_by`` label. The property this test exists for is unchanged on every
    row: **the SECOND value is never read**, and nothing is manufactured.

    MUTATION: reverting ``_OR_REQUIRED_HEDGES`` into ``_BARE_HEDGES`` turns the ten
    ``hedge`` rows RED; deleting the ``_unit_is_complete`` guard turns the three
    ``unit`` rows RED. Neither mutation touches the other's rows, which is the
    independence of the two halves measured rather than asserted.
    """
    reading = _read(sentence)
    if sentence in _ALSO_SEQUENCE_GATED:
        assert reading.candidates == ()
        # AND IT IS DISCLOSED, which is the whole basis for the trade.
        assert [entry.kind for entry in reading.abstentions] == [
            "several_values_and_none_selected"
        ]
        assert field_path in reading.abstentions[0].reason
        assert reading.review_required == ()
        assert [segment.text for segment in reading.segments] == [sentence]
        return
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
    elif refused_by == "unit":
        assert bridged is True, "the connective here is a perfectly good one"
        assert unit_complete is False
    else:
        # THE THIRD LABEL, added 2026-09-12 (fourth pass). A row BOTH halves refuse
        # says nothing about either one on its own, which is why it is named rather
        # than filed under whichever half is checked first — see the row's own
        # comment in `FALSE_RESTATEMENTS`. It is still worth a row: it is one of the
        # thirteen measured sentences, and `test_every_one_of_the_thirteen_was_
        # admitted_by_the_FIRST_gate` proves the pre-correction bridge admitted it.
        assert refused_by == "both", refused_by
        assert bridged is False
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
    # ~~("The temperature was 425 K and again 430 K", [425, 430], TEMPERATURE),~~
    # **WITHDRAWN 2026-09-12 (fourth pass), and kept struck because it was a
    # MUST-PASS.** `and again` is a REPEAT marker, not a hedge, and left in the bare
    # branch it silently proposed a second acquisition instant for
    # `"...started 2026-01-01T00:00:00Z, and again 2026-01-02T00:00:00Z."` — minting
    # a durable OPEN proposal on a `timestamps` field. The temperature form now
    # reads 425 alone and DISCLOSES the withholding; it is pinned as residue in
    # `AND_AGAIN_RESIDUE` below.
    ("The temperature was 425 K, or and again 430 K", [425, 430], TEMPERATURE),
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
#: both values; **all seven now read one**, and the fifth element of each row is
#: what the slice that adopted the rule accepted losing.
#:
#: ~~"Each reads both values today, and that is asserted — so a future slice that
#: adopts a terminal rule finds out from a test what it costs, rather than from a
#: scientist."~~ — **the future slice was the next one, it did find out from this
#: test, and the cost is now the SUBJECT of the test rather than a warning about
#: it.**
#:
#: ~~"Five rows are ACCEPTED LOSSES and one is untouched, and the distinguishing
#: fact is mechanical: the untouched row bridges with ``or maybe``, so condition 3
#: does not reach it."~~ — **SUPERSEDED 2026-09-12 (third pass): condition 3 is
#: UNIVERSAL, so the sixth row is a loss too and there is no untouched row.** A
#: SEVENTH row was added in the same change for the bare-``or`` branch, so all three
#: branches of ``_HEDGE_BRIDGE`` are represented and none of the three can be
#: widened or narrowed without a row here moving.
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
        # ~~"— UNTOUCHED"~~ — **IT IS A LOSS SINCE 2026-09-12 (third pass)**, when
        # condition 3 became universal. It was the sixth of the six the universal
        # rule was measured to cost, and the one the SCOPED rule spared; the scope
        # is gone, so the row moves from "untouched" to "accepted loss, disclosed"
        # and the label is corrected rather than the row deleted.
        "a trailing aside after an instant, behind an explicit or — NOW A LOSS",
        "The scan started 2026-01-01T00:00:00Z, or maybe 2026-01-02T00:00:00Z, I "
        "would have to check",
        ["2026-01-01T00:00:00Z"],
        START,
        ["trailing_text_after_further_values"],
    ),
    (
        # ADDED 2026-09-12 (third pass). The BARE-`or` branch's own cost, which the
        # residue comment named as the price of extending condition 3 to it. It is
        # the seventh row and the only one whose connective is a bare `or`, so all
        # three branches of `_HEDGE_BRIDGE` are now represented in this table.
        "a trailing prepositional phrase behind a BARE or — the third branch",
        "The temperature was 425 K or 430 K at the end",
        [425],
        TEMPERATURE,
        ["trailing_text_after_further_values"],
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
    """Seven sentences that read both values before the terminal rule. **All seven
    now read one, and every one of the seven says so.**

    ~~"Six sentences … Five now read one, and every one of the five says so."~~ —
    that described the SCOPED rule, which spared the sixth row because it bridges
    with ``or maybe``. Condition 3 is universal since 2026-09-12 (third pass), so
    the sixth is a loss; the seventh was added then to cover the bare-``or`` branch.
    **The scope it describes is what left five silent §5 false positives behind the
    ``or`` branch for one commit**, and the trade recorded here is the cost of
    closing them.

    The fourth is the one that was argued hardest, and it is still the interesting
    one: a sentence stating a temperature alternative AND an atmosphere loses the
    alternative, because ``_ATMOSPHERE`` is anchored to the end of the segment and
    its own text is therefore the non-terminal tail. The previous slice read that as
    a refutation — *"a gate cannot require a restatement to end the sentence in a
    reader whose other rules require their value to end the sentence"* — and it is
    instead the PRICE, paid knowingly: the atmosphere value still reads, the
    temperature alternative is reported as withheld, and the sentence survives
    verbatim as a note.

    MUTATION: removing the disclosure leaves the seven VALUE assertions green and
    turns the seven ABSTENTION assertions red, which is the point — a silent refusal
    passes the first half of this test and the trade does not hold without the
    second. Restoring ``accepted[-1][1]`` to the ``while`` in ``_segment_readings``
    turns rows six and seven RED.
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


def test_the_C1_GATE_AND_THE_C2_BYTE_CEILING_PROOF_ARE_NO_LONGER_COUPLED():
    """~~``_bytes_only()`` needs FIVE candidates, and a terminal rule leaves four.~~

    **INVERTED IN PLACE 2026-09-12 (third pass). The coupling was real, it was
    found by measurement, and it was then allowed to decide a §5 question — which
    is why it is inverted rather than deleted.** What this test used to assert:

        *"THIS COUPLING IS THE REASON THE TERMINAL RULE WAS REJECTED RATHER THAN
        FIXED-UP … The C-2 byte ceiling is proved by a payload whose third
        temperature is a hedged restatement followed by an unrelated clause.
        Refuse that restatement and the payload drops under the cap,
        ``pytest.raises(TranscriptTooDense)`` never fires, and a currently-green
        ceiling test passes for a reason that has nothing to do with ceilings."*

    Every clause of that was true of the OLD fixture. The error was treating it as
    a fact about the GATE. **A resource-ceiling proof must not be hostage to a
    semantic gate**, and this one was: three of its five candidates came from pass
    two, so the cheapest way to keep a byte-ceiling test green was to keep admitting
    restatements, and the class stayed open for one more release because of it.

    ``_bytes_only()`` is now built from LABEL-ANCHORED matches only. The mechanism
    assertions live beside the fixture
    (``test_the_C2_BYTE_CEILING_PROOF_IS_DECOUPLED_FROM_THE_C1_GATE``); what is
    asserted HERE is the strongest form of the same claim, and it is the form the
    coupled test could not make: **disable the C-1 gate entirely, in both
    directions, and the fixture's candidate count does not move.**

    MUTATION: reverting ``_bytes_only()`` to its hedged-chain head turns every
    branch of this RED — the strict arm reads 3, the permissive arm reads 5.
    """
    from test_transcript_capture_ceilings import _bytes_only

    text = _bytes_only()
    assert len(tc.segment_transcript(text)) == 1
    segment_bytes = len(text.encode("utf-8"))
    assert segment_bytes <= routes._MAX_TRANSCRIPT_BYTES

    def measured() -> int:
        with pytest.raises(tc.TranscriptTooDense) as raised:
            _read(text)
        assert raised.value.candidate_quote_bytes == segment_bytes * 5
        return raised.value.candidates

    # (a) The gate in force.
    assert measured() == 5

    # (b) A MAXIMALLY STRICT condition 3 — no restatement anywhere ends a
    #     statement. This is the mutation that took the old fixture to THREE.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tc, "_statement_ends_after", lambda text, position: False)
        assert measured() == 5

    # (c) A MAXIMALLY STRICT condition 1 — no gap bridges at all, so no restatement
    #     is even considered. The other direction of the same independence.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tc, "_HEDGE_BRIDGE", re.compile(r"(?!x)x"))
        assert measured() == 5

    # (d) And a MAXIMALLY PERMISSIVE condition 3, which is the direction a coupled
    #     fixture would have been sensitive to in the other sense.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tc, "_statement_ends_after", lambda text, position: True)
        assert measured() == 5

    # The margin is the fifth candidate and nothing wider, so the proof is tight.
    assert segment_bytes * 5 > tc.MAX_CANDIDATE_QUOTE_BYTES
    assert segment_bytes * 4 <= tc.MAX_CANDIDATE_QUOTE_BYTES, (
        "at four candidates this payload is UNDER the cap, so the byte ceiling "
        "would stop being proved by this fixture at all"
    )


# =============================================================================
# 4. THE CLASS THAT IS STILL OPEN. Pinned AS OPEN, on purpose.
# =============================================================================


@pytest.mark.parametrize("sentence", tc._RESTATEMENT_RESIDUE_CLOSED)
def test_the_NINE_recorded_residue_SENTENCES_ARE_NOW_CLOSED(sentence):
    """Every §5 restatement false positive this reader has ever measured. **CLOSED.**

    ~~"the four recorded residue sentences"~~ — **NINE since 2026-09-12 (third
    pass).** Four were closed by condition 3 scoped to the bare-hedge branch; the
    other five, behind an explicit ``or``, were measured AFTER that fix, pinned AS
    OPEN by their own test, and closed when condition 3 became universal. They moved
    into this tuple rather than being deleted, so both closures stay checkable.

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


@pytest.mark.parametrize("sentence", tc._LABEL_OVERREACH_CLOSED)
def test_the_LABEL_ANCHORED_overreach_is_still_a_FALSE_POSITIVE(sentence):
    """~~A KNOWN-OPEN §5 defect, asserted to still occur. **NOT rounded down.**~~

    **INVERTED 2026-09-13. THE CLASS IS CLOSED AND THIS TEST NOW ASSERTS THE
    REFUSAL.** The constant it parametrises over is renamed
    ``_LABEL_OVERREACH_CLOSED`` and every row is KEPT, following the precedent
    ``_RESTATEMENT_RESIDUE_CLOSED`` set: a tuple whose rows were deleted on being
    fixed cannot answer the question *"is the class still closed?"*, and this
    module's own comment records why an emptied ratcheted tuple is worse than
    either state — it makes a parametrised test vacuous.

    **THE OLD ASSERTIONS, KEPT VERBATIM BECAUSE THEY ARE THE RECORD OF WHAT WAS
    SHIPPING:**

    ~~``assert len(rows) == 1``~~ with the message *"if this reads nothing the
    class is CLOSED — delete the row from _LABEL_OVERREACH_RESIDUE and say so, do
    not weaken this assertion"*; ~~``assert rows[0][1] is False``~~ (it came from
    pass ONE); ~~``assert _read(sentence).abstentions == ()``~~ (*"AND IT IS
    SILENT, which is what makes it a §5 defect rather than a disclosed
    omission"*); ~~``assert rows[0][0] not in (425, 430, 435)``~~ (the value
    proposed was the modifier's figure, so a scientist reviewing the proposal saw
    a plausible kelvin number).

    **The old test's reasoning was RIGHT IN EVERY PARTICULAR and is the reason
    this is an inversion rather than a rewrite.** Three passes over this reader
    treated *"the reader proposes values the transcript does not state"* as a
    property of the RESTATEMENT scan; it was not. ``_TEMPERATURE_K`` bridged label
    to value with ``[^.;:]{0,40}?``, so ~40 characters of anything could sit
    between the word ``temperature`` and the number it read, and *"The temperature
    drift was 3 K"* proposed 3 K as an absolute temperature with no abstention at
    all. Every row here is more natural dictation than any of the five
    ``or``-branch sentences that were argued about at length.

    **WHAT CLOSED IT, and why it is not the proxy the old comment rejected.** The
    old comment named three proxies and rejected all three: a denylist of
    ``drift``/``error``/``step`` (fails OPEN), a shorter bridge (kills *"Sample
    temperature at the second scan was 425 K"*), and requiring a copula (kills
    *"temperature 425 K"*). All three rejections were correct. What was missing is
    that the bridge's SHAPE can be constrained without constraining its LENGTH:
    :data:`~isaac_api.transcript_capture._ASSERTION_BRIDGE` is an ALLOWLIST
    grammar — prepositional modifiers of the label, a closed set of assertions, an
    approximation — so the 40-character bridge is unchanged and *"at the second
    scan was"* still parses, while a bare nominal head never can.

    **EVERY ROW IS NOW REFUSED AND DISCLOSED, which is the §5 requirement rather
    than merely the absence of the defect.** A silent refusal would be a different
    defect of the same rank; this asserts the abstention exists and names the
    field, so a future change that turns a refusal silent comes through here.
    """
    assert _rows(sentence) == [], (
        "if this reads a value again the class has REOPENED; the value is a "
        "drift, an error, a step, a tolerance, a delta or a rate, not a "
        "temperature -- do not weaken this assertion"
    )
    reading = _read(sentence)
    # REFUSED AND DISCLOSED, never silent: the whole point of the inversion.
    assert [entry.kind for entry in reading.abstentions] == [
        "label_does_not_assert_this_value"
    ]
    disclosure = reading.abstentions[0]
    assert "context.temperature_K" in disclosure.reason
    # The quote points at the clause the scientist has to re-read, and it does NOT
    # assert what the withheld number is -- this reader does not know.
    assert disclosure.quote in sentence
    # AND THE WORDS SURVIVE. Rule (4) stores every segment regardless.
    assert [segment.text for segment in reading.segments] == [sentence]


def test_the_LABEL_ANCHORED_instant_overreach_is_CLOSED_TOO():
    """The one row of the class's own table that was never in the tuple.

    ``_LABEL_OVERREACH_RESIDUE`` was temperature-only while the table documenting
    the class named an INSTANT row too — *"It started drifting at
    2026-01-01T00:00:00Z"* proposing an acquisition START for a DRIFT ONSET — and
    the old comment said so explicitly, "named so a reader does not count the two
    and conclude one is stale". It is asserted here rather than added to the tuple,
    because the tuple's parametrised test asserts a TEMPERATURE field path.

    MUTATION: dropping ``label_head`` from the ``acquisition_start`` rule turns
    this RED, and so does admitting a bare gerund to ``_ASSERTION_AT_VERB``.
    """
    for sentence in (
        "It started drifting at 2026-01-01T00:00:00Z",
        "It started warming at 2026-01-01T00:00:00Z",
        "The scan started logging at 2026-01-01T00:00:00Z",
        "It ended cooling at 2026-01-01T00:00:00Z",
    ):
        reading = _read(sentence)
        assert reading.candidates == (), sentence
        assert [entry.kind for entry in reading.abstentions] == [
            "label_does_not_assert_this_value"
        ], sentence
    # AND THE LEGITIMATE FORMS THE SAME RULE EXISTS FOR ARE UNTOUCHED.
    for sentence, path in (
        ("The scan started 2026-01-01T00:00:00Z", "timestamps.acquired_start_utc"),
        ("The scan started at 2026-01-01T00:00:00Z", "timestamps.acquired_start_utc"),
        ("The scan started around 2026-01-01T00:00:00Z", "timestamps.acquired_start_utc"),
        ("The scan ended 2026-01-01T00:00:00Z", "timestamps.acquired_end_utc"),
        ("The scan ended at 2026-01-01T00:00:00Z", "timestamps.acquired_end_utc"),
    ):
        reading = _read(sentence)
        assert [
            candidate.proposed_value
            for candidate in reading.candidates
            if candidate.field_path == path
        ] == ["2026-01-01T00:00:00Z"], sentence
        assert reading.abstentions == (), sentence


def test_the_residue_lists_are_two_way_ratchets():
    """A test that iterates the list it checks cannot see a REMOVAL from that list.

    This repository has been caught by exactly that: deleting ``"approximately"``
    from ``_HEDGE_CONNECTIVES`` left 176 transcript tests GREEN, because the only
    test that checked it walked the list.

    Both lists are ratcheted, and the CLOSED one matters more: a slice that deleted
    a row from it would delete the evidence that the row is closed, and the
    parametrised test above would then pass by iterating fewer cases.
    """
    assert len(tc._RESTATEMENT_RESIDUE_CLOSED) == 9
    assert len(set(tc._RESTATEMENT_RESIDUE_CLOSED)) == 9, "no row is duplicated"
    assert (
        "The temperature was 425 K, maybe 3 K of drift"
        in tc._RESTATEMENT_RESIDUE_CLOSED
    )
    assert (
        "The temperature was 425 K, alternatively 3 K per minute"
        in tc._RESTATEMENT_RESIDUE_CLOSED
    ), "the one closed row that uses a connective other than maybe/perhaps"
    # THE FIVE THAT ARRIVED IN THE THIRD PASS, named individually. They were pinned
    # AS OPEN by their own parametrised test, so a slice that dropped them while
    # deleting that test would delete the evidence that they are shut.
    for row in (
        "The temperature was 425 K or 3 K of drift",
        "The temperature was 425 K or 3 K above target",
        "The temperature was 425 K, or about 3 K of drift",
        "The temperature was 425 K, or maybe 3 K of drift",
        "The temperature was 425 K, or perhaps 2 K of scatter",
    ):
        assert row in tc._RESTATEMENT_RESIDUE_CLOSED, row
    # Two of the five use a BARE `or` and three an `or` + hedge, so both of the
    # branches the old scope exempted are represented and neither can be re-exempted
    # without a row here going red.
    assert sum(
        " or " in row and ", or " not in row
        for row in tc._RESTATEMENT_RESIDUE_CLOSED
    ) == 2

    # ~~`_RESTATEMENT_RESIDUE`~~ IS GONE. An empty ratcheted tuple would make the
    # parametrised test that walks it vacuous — pytest reports one skipped
    # "empty parameter set" and nothing fails — which is exactly the silent loss of
    # coverage this repository has been caught by before. The open-class test was
    # repointed at `_LABEL_OVERREACH_RESIDUE` instead.
    assert not hasattr(tc, "_RESTATEMENT_RESIDUE")
    # AND THE SAME DISCIPLINE APPLIED AGAIN ON 2026-09-13: that class is now closed
    # too, the constant is RENAMED `_LABEL_OVERREACH_CLOSED` with all 13 rows kept,
    # and its parametrised test is INVERTED to assert the refusal. The old name is
    # asserted gone, for the same reason `_RESTATEMENT_RESIDUE` is: a stale name
    # left as an alias is how a reader concludes a closed class is still open.
    assert not hasattr(tc, "_LABEL_OVERREACH_RESIDUE")
    # ~~7~~ **13 (2026-09-12, fourth pass).** Six rows of the identical class were
    # measured by independent review and added; ~~the class is described, not
    # closed, and the OPEN-class test below still asserts every row STILL
    # fabricates~~ — **the class is CLOSED as of 2026-09-13 and that test now
    # asserts every row is REFUSED AND DISCLOSED.** The rows are kept so "is it
    # still closed?" stays a checkable question.
    assert len(tc._LABEL_OVERREACH_CLOSED) == 13
    assert len(set(tc._LABEL_OVERREACH_CLOSED)) == 13
    assert "The temperature drift was 3 K" in tc._LABEL_OVERREACH_CLOSED
    assert (
        "temperature resolution 0.5 K" in tc._LABEL_OVERREACH_CLOSED
    ), "the row with no copula, which a 'require a copula' proxy would not reach"
    # The six added in the fourth pass, named individually for the reason the
    # third pass's five are: a slice that dropped them while editing this test
    # would delete the evidence that the class is wider than seven rows.
    for row in (
        "The temperature uncertainty was 2 K",
        "The temperature offset was 4 K",
        "The temperature fell by 12 K",
        "temperature stability 0.2 K",
        "The temperature gradient was 5 K",
        "We corrected the temperature by 7 K",
    ):
        assert row in tc._LABEL_OVERREACH_CLOSED, row
    # `fell by` and `corrected ... by` are the two shapes no earlier row had: a
    # DECREASE, and a label that is not the subject of the sentence.
    assert "The temperature fell by 12 K" in tc._LABEL_OVERREACH_CLOSED
    assert "We corrected the temperature by 7 K" in tc._LABEL_OVERREACH_CLOSED
    # The two lists are disjoint: a sentence cannot be both closed and open, and an
    # edit that moved one without removing it from the other would say it is.
    assert not (
        set(tc._LABEL_OVERREACH_CLOSED) & set(tc._RESTATEMENT_RESIDUE_CLOSED)
    )


def test_the_defect_corpus_and_the_must_pass_corpus_are_both_ratcheted():
    """The same protection for the two corpora the parametrised tests walk."""
    assert len(FALSE_RESTATEMENTS) == 13
    assert len(TRUE_RESTATEMENTS) == 11
    assert len(TERMINAL_RULE_WOULD_HAVE_LOST) == 7
    sentences = {row[1] for row in FALSE_RESTATEMENTS}
    # The three rows that are the ORIGINAL ramp-rate defect with a new connective.
    assert "The temperature was 425 K or 3 K/min" in sentences
    assert "The temperature was 425 K and again 3 K/min" in sentences
    assert "The temperature was 425 K, alternatively 3 K/min" in sentences
    # The row that refutes the terminal rule on its own terms.
    assert "The temperature was 425 K, about 3 K." in sentences
    # Both halves are exercised, so neither parametrisation can become vacuous.
    # ~~{"hedge", "unit"}~~ — a THIRD label `"both"` arrived 2026-09-12 (fourth
    # pass) when `and again` moved branch and its row became one both halves refuse.
    assert {row[3] for row in FALSE_RESTATEMENTS} == {"hedge", "unit", "both"}
    assert sum(row[3] == "both" for row in FALSE_RESTATEMENTS) == 1
    # ~~3~~ **2**: the third of the three ramp-rate rows is the `and again` one,
    # which is now `"both"`. 2 + 1 = 3, so the three ramp-rate rows asserted above
    # are all still present and only their LABELS moved.
    assert sum(row[3] == "unit" for row in FALSE_RESTATEMENTS) == 2
    assert sum(row[3] in {"unit", "both"} for row in FALSE_RESTATEMENTS) == 3


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

    **THE SENTENCE THIS TEST USES NOW FAILS AN EARLIER GATE, AND THE OLD
    ASSERTION IS KEPT RATHER THAN MOVED — added 2026-09-13.** ~~``assert [... for
    candidate in reading.candidates] == [300]``~~ and ~~``== ["unhedged_further_
    values"]``~~ and ~~``disclosure.quote == "Temperature ramped 300 K"``~~.
    *"Temperature ramped 300 K"* never asserted 300 as the temperature in the first
    place: ``ramped`` is a bare verb between the label and the value, so a ramp of
    300 K and a ramp TO 300 K are both readings of it and this reader cannot tell
    which. The PASS-ONE ASSERTION GATE refuses the bridge, so the disclosure this
    test exists for is now ``label_does_not_assert_this_value`` — reached one gate
    earlier, for a stricter reason.

    **What the test is FOR is unchanged and is still what is asserted: a refusal is
    not silent, the disclosure names the field, it asserts nothing about the
    withheld numbers, and the quote is short.** A second sentence — same shape,
    legitimate bridge — is added so the RESTATEMENT disclosure this test was
    originally written for is still exercised.

    MUTATION: deleting the abstention loop from ``read_transcript`` turns this RED.
    """
    reading = _read("Temperature ramped 300 K, then 350 K, then 400 K.")
    assert reading.candidates == ()
    assert [entry.kind for entry in reading.abstentions] == [
        "label_does_not_assert_this_value"
    ]
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

    # THE SAME SHAPE WITH A BRIDGE THE GATE ADMITS, so the restatement disclosure
    # this test was written for is still exercised rather than only described. Here
    # the SEQUENCE GATE fires, because three progressive values with pure
    # coordination between them are three values of one scalar field.
    ramp = _read("The temperature was 300 K, then 350 K, then 400 K.")
    assert ramp.candidates == ()
    assert [entry.kind for entry in ramp.abstentions] == [
        "several_values_and_none_selected"
    ]
    for withheld in ("350", "400"):
        assert withheld not in ramp.abstentions[0].reason
        assert withheld not in ramp.abstentions[0].quote
    assert ramp.abstentions[0].quote == "temperature was 300 K"


def test_the_disclosure_is_deduplicated_and_bounded_by_construction():
    """At most ONE disclosure per segment per rule, whatever the transcript says.

    ``"temperature 1 C"`` repeated 16,384 times is one fact, and a disclosure that
    scaled with the text would add to an accumulator neither density ceiling sees
    (``_DISCLOSURE_CEILING_GAP``). This one cannot: the refusal set is keyed on the
    rule NAME.

    ~~``assert [candidate.proposed_value for candidate in reading.candidates] ==
    [425]``~~ — **the payload is 1,000 comma-separated kelvin values after a
    labelled one, so the SEQUENCE GATE withholds 425 too (2026-09-13).** The
    DEDUPLICATION property this test exists for is unchanged and is what is still
    asserted: one disclosure, not a thousand.

    MUTATION: changing ``refused`` from a per-rule mapping to a list turns this RED.
    """
    many = "The temperature was 425 K, " + ", ".join(
        f"{value} K" for value in range(10000, 11000)
    )
    reading = _read(many)
    assert len(reading.segments) == 1
    assert reading.candidates == ()
    assert len(reading.abstentions) == 1

    # And a payload whose further values are a DIFFERENT quantity, so the label
    # reading survives and the single disclosure is the restatement gate's. Both
    # shapes must deduplicate, and only this one used to be covered.
    other = "The temperature was 425 K, " + ", ".join(
        f"cryostat setpoint {value} K" for value in range(10000, 11000)
    )
    survives = _read(other)
    assert len(survives.segments) == 1
    assert [candidate.proposed_value for candidate in survives.candidates] == [425]
    assert len(survives.abstentions) == 1

    # And the ceiling that follows from it, stated as arithmetic over the real
    # constants rather than as a quoted number.
    #
    # ~~`MAX_SEGMENTS * len(_RULES) == 500`~~ is still true and is still a bound,
    # but it is no longer the TIGHT one: the PASS-ONE ASSERTION GATE added three
    # refusal kinds on 2026-09-13, so the per-segment worst case is the three
    # label-gated rules x FIVE kinds = 15, and the construction bound is 1,500.
    # Both are stated because `MAX_DISCLOSURES` is set against them and a bound
    # nobody can re-derive is not a bound. 1,500 < MAX_DISCLOSURES, so the ceiling
    # still admits the by-construction worst case without being raised.
    assert len(tc._RULES) == 5
    assert tc.MAX_SEGMENTS * len(tc._RULES) == 500
    gated = [rule for rule in tc._RULES if rule.label_head is not None]
    assert len(gated) == 3
    assert tc.MAX_SEGMENTS * len(gated) * 5 == 1500 <= tc.MAX_DISCLOSURES


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

    Condition 3 says a restatement is read when it ends the statement OR when
    another ACCEPTED restatement follows it. So dropping the last link can make the
    one before it non-terminal too, and the walk has to continue. With a single
    pass, *"425 K, maybe 430 K, and again 3 K of drift"* keeps 430 — whose only
    claim to being terminal is a restatement that was just refused.

    ~~"THE WALK STOPS AT THE FIRST SURVIVING LINK … 430 sits behind an explicit
    ``or``, so condition 3 never reaches it and it survives even though something
    now follows it."~~ — **CORRECTED 2026-09-12 (third pass): condition 3 is
    universal, so an ``or``-bridged link is popped like any other and the cascade
    runs through it.** The walk still stops at the first link that IS terminal;
    what changed is that being behind an ``or`` is no longer a way of being
    terminal. The old row is kept as the first assertion below, with its measured
    result corrected, because it was the exemption that let five sentences fabricate.

    MUTATION: ``while`` -> ``if`` in ``_segment_readings`` turns the second case RED
    and leaves every other test in this file green.
    """
    # The cascade runs through an `or`-bridged link too: 3 is dropped for its own
    # trailing phrase, and 430 then has a bridge-to-a-refusal behind it.
    assert _values(
        "The temperature was 425 K, or perhaps 430 K, and again 3 K of drift"
    ) == [425]
    # The same sentence with a BARE hedge. It reads identically, and THAT is the
    # symmetry the universal rule buys: before this change these two lines
    # disagreed, for no reason a reader of the sentences could state.
    assert _values(
        "The temperature was 425 K, maybe 430 K, and again 3 K of drift"
    ) == [425]
    # The chain is never broken in the MIDDLE: a terminal tail keeps every link in
    # front of it, whichever branch bridged each one.
    assert _values(
        "The temperature was 425 K, maybe 430 K, or perhaps 435 K"
    ) == [425, 430, 435]
    assert _values(
        "The temperature was 425 K or 430 K, maybe 435 K"
    ) == [425, 430, 435]


def test_condition_three_is_SYMMETRIC_across_all_three_hedge_branches():
    """One sentence, one modifier tail, three connectives — one outcome.

    **THIS IS THE INVARIANT THE SCOPED RULE DID NOT HAVE, AND ITS ABSENCE WAS THE
    DEFECT.** ``", maybe 3 K of drift"`` was refused while ``" or 3 K of drift"``
    and ``", or maybe 3 K of drift"`` were read as temperatures, for a reason about
    the words BEFORE the value applied to a question about the words AFTER it. A
    reader of the three sentences could not have predicted which two fabricated.

    Asserted over the branches directly rather than over a sentence list, so a
    future change to ``_BARE_HEDGES`` or ``_OR_REQUIRED_HEDGES`` membership cannot
    make it vacuous.

    MUTATION: restoring ``accepted[-1][1]`` to the ``while`` in
    ``_segment_readings`` turns this RED on both ``or`` branches.
    """
    branches = {
        "bare hedge": ", maybe",
        "or + hedge": ", or maybe",
        "bare or": " or",
    }
    for label, connective in branches.items():
        # Terminal: read, no disclosure. Non-terminal: refused, disclosed.
        assert _values(f"The temperature was 425 K{connective} 430 K") == [
            425,
            430,
        ], label
        assert _read(f"The temperature was 425 K{connective} 430 K").abstentions == (), label

        trailing = f"The temperature was 425 K{connective} 3 K of drift"
        assert _values(trailing) == [425], label
        assert [entry.kind for entry in _read(trailing).abstentions] == [
            "trailing_text_after_further_values"
        ], label
    # And the three branches really are three: each connective is admitted by
    # `_HEDGE_BRIDGE` through a different clause.
    assert branches["bare hedge"].lstrip(", ") in tc._BARE_HEDGES
    assert branches["or + hedge"].split()[-1] in tc._BARE_HEDGES + tc._OR_REQUIRED_HEDGES
    assert branches["bare or"].strip() == tc._BARE_OR


#: Every connective the gate admits, spelled as it appears in a gap.
_ALL_CONNECTIVES: tuple[str, ...] = (
    tc._BARE_HEDGES
    + tuple(f"or {hedge}" for hedge in tc._OR_REQUIRED_HEDGES)
    + tuple(f"or {hedge}" for hedge in tc._BARE_HEDGES)
    + (tc._BARE_OR,)
)

#: Phrases that turn a kelvin figure into a DIFFERENT quantity. Seventeen, written
#: out rather than generated, and deliberately including shapes no earlier corpus
#: had — ``"rms"``, ``"either way"``, ``"give or take"``, ``"on the cold finger"`` —
#: because the only method that has ever found a new row here is writing NEW
#: sentences rather than re-running the measured ones.
_MODIFIER_TAILS: tuple[str, ...] = (
    "of drift",
    "above target",
    "below the setpoint",
    "per minute",
    "per step",
    "of scatter",
    "colder than before",
    "warmer than the last scan",
    "of uncertainty",
    "either way",
    "give or take",
    "over the hour",
    "of ramp",
    "rms",
    "plus the offset",
    "on the cold finger",
    "of noise",
)


def test_the_WHOLE_CROSS_PRODUCT_fabricates_nothing_and_refuses_nothing_in_silence():
    """The step that found the five ``or``-branch rows, run again over a wider grid.

    ``len(_ALL_CONNECTIVES)`` x ``len(_MODIFIER_TAILS)`` x two separators =
    ~~**510**~~ **476 (2026-09-12, fourth pass)**
    constructed sentences, each stating a labelled 425 K and then a 3 K figure that
    a trailing phrase makes into a drift, an offset, a rate or a tolerance.

    **WHY THE NUMBER WENT DOWN, AND WHY THAT IS NOT A LOSS OF COVERAGE.**
    ``_ALL_CONNECTIVES`` is DERIVED from the module's own split, and ``and again``
    moved from ``_BARE_HEDGES`` to ``_OR_REQUIRED_HEDGES``, so the grid lost the row
    ``"425 K, and again 3 K <tail>"`` and kept ``"425 K, or and again 3 K <tail>"``
    (17 tails x 2 separators = 34 cells). The bare form is now covered by
    ``test_the_INSTANT_AND_EMPTY_TAIL_SWEEP_fabricates_nothing_in_silence``, which
    exercises every non-bridging bare connective explicitly — the shape this grid
    structurally cannot reach, because it only ever builds forms that DO bridge.

    **THE SCOPE OF THIS GRID, STATED BESIDE ITS NUMBER, because a sweep whose shape
    excludes a rule cannot clear that rule and 510 read as though it had.** Every
    cell is ``f"The temperature was 425 K{separator}{connective} 3 K {tail}"``: ONE
    rule of five, and a NON-EMPTY tail in every cell. So the two INSTANT rules and
    the terminal (empty-tail) case are both structurally outside it — which is
    exactly how the ``and again`` fabrication reached ``main`` with this grid green.
    The sibling sweep named above covers both.

    Two
    properties, and the second is as load-bearing as the first:

    1. **NOTHING but 425 is proposed.** A second value here would be a §5 assertion
       the transcript does not support.
    2. **NO refusal is SILENT.** §5 ranks a disclosed omission above an assertion
       and both above a silent one, so a grid that closed (1) by withholding
       quietly would have moved the defect rather than fixed it.

    A generated grid cannot replace the written-out corpora above — it says nothing
    about sentences nobody thought to parameterise — which is why both exist. What
    it adds is coverage of every branch x tail COMBINATION, of which the measured
    corpora cover fifteen.

    MUTATION: restoring the bare-hedge scope turns this RED with **374** of the 510
    rows fabricating — measured, not estimated; a first guess of "170" was wrong by
    more than a factor of two. 374 is exactly the eleven ``or``-bearing connectives
    (six ``or`` + approximation, four ``or`` + bare hedge, one bare ``or``) x 17
    tails x 2 separators, which is the whole of what the scope exempted.
    """
    assert len(_ALL_CONNECTIVES) == 14
    assert len(_MODIFIER_TAILS) == 17
    fabricated: list[tuple[str, list]] = []
    silent: list[str] = []
    checked = 0
    for connective in _ALL_CONNECTIVES:
        for tail in _MODIFIER_TAILS:
            for separator in (", ", " "):
                sentence = (
                    f"The temperature was 425 K{separator}{connective} 3 K {tail}"
                )
                checked += 1
                values = _values(sentence)
                if values != [425]:
                    fabricated.append((sentence, values))
                elif not _read(sentence).abstentions:
                    silent.append(sentence)
    assert checked == 476, checked
    assert fabricated == [], fabricated[:5]
    assert silent == [], silent[:5]


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
    slice that re-spells either one has to come through here.

    ~~"The ``\n`` exclusion is asserted too: a hedge or a tail on the far side of a
    line break is not 'immediately after', and ``_H_SPACE`` exists for exactly
    that."~~ — **WITHDRAWN 2026-09-12 (fourth pass). THE TWO PREDICATES ASK
    OPPOSITE QUESTIONS ABOUT A LINE BREAK AND SHARING ONE CLASS WAS A
    COINCIDENCE.** ``_HEDGE_BRIDGE`` asks whether the connective is IMMEDIATELY
    BETWEEN two values, where a line break means it is not; this asks whether the
    statement ENDS, where a line break means it plainly does. While ``_H_SPACE``
    was ``[^\\S\\n]`` the disagreement was visible only for ``\\n`` and cost nothing;
    narrowing it to all TEN line-boundary characters turned it into a false
    refusal — ``"...maybe 430 K\r"`` withheld 430. ``_STATEMENT_END`` now uses
    ``\\s``.

    **BOTH ROWS BELOW ARE THEREFORE INVERTED, and ``\n`` is the one worth naming**:
    ``_statement_ends_after("X\n", 1)`` is now ``True``. That is the right answer
    and not an accepted cost — a value followed by nothing but a newline ends its
    statement as plainly as one followed by a full stop. It is also inert:
    ``_SEGMENT_BOUNDARY`` splits on ``\n+``, so no segment contains one.

    MUTATION: putting ``_H_SPACE`` back into ``_STATEMENT_END`` turns the ``\r``
    row RED, which is the live half.
    """
    for character in tc._UNIT_TERMINATORS:
        assert tc._statement_ends_after(f"X{character}", 1) is True, character
    for character in " \t\xa0":
        assert tc._statement_ends_after(f"X{character}", 1) is True, repr(character)
    # EVERY line-boundary character ends a statement, including the nine that no
    # longer bridge a hedge. The two sets are asserted against each other below.
    for character in tc._LINE_BREAKS:
        assert tc._statement_ends_after(f"X{character}", 1) is True, repr(character)
        assert tc._statement_ends_after(f"X{character}more text", 1) is False, repr(
            character
        )
    # And NONE of them bridges a hedge, which is the other half of the split.
    for character in tc._LINE_BREAKS:
        assert tc._HEDGE_BRIDGE.fullmatch(f",{character}maybe ") is None, repr(character)
    assert tc._HEDGE_BRIDGE.fullmatch(",\xa0maybe ") is not None
    # And the composers the unit ratchet refuses are refused here too, which is the
    # coupling being defence in depth rather than a weakening.
    for composer in "/*^-·×%":
        assert tc._statement_ends_after(f"X{composer}", 1) is False, composer


def test_the_hedge_bridge_has_exactly_three_branches():
    """Which connectives bridge BARE and which need an explicit ``or``, asserted in
    both directions over every reviewed connective. That split is CONDITION 1 and it
    is fully live.

    ~~"``_BARE_HEDGE_BRIDGE`` admits a gap iff ``_HEDGE_BRIDGE`` does AND the
    connective came from ``_BARE_HEDGES`` with no ``or`` in front of it … a pattern
    that merely admitted MORE would silently widen condition 3 into the ``or``
    branch — the exact extension ``_RESTATEMENT_RESIDUE`` records as NOT taken."~~ —
    **``_BARE_HEDGE_BRIDGE`` IS DELETED (2026-09-12, third pass), and the extension
    it guarded against is the one that was TAKEN.** Condition 3 is universal, so
    nothing asks which branch admitted a gap; the pattern's only consumer was a
    boolean that ``_segment_readings`` then discarded, and keeping it would have
    been a guard with a rationale describing a decision no longer in force. Its
    assertions are removed from this test rather than rewritten, because the split
    they were about is decided by ``_HEDGE_BRIDGE`` and always was.

    MUTATION: moving any connective between ``_BARE_HEDGES`` and
    ``_OR_REQUIRED_HEDGES`` turns this RED.
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
    # Branch 3: a bare `or`, standing alone.
    assert tc._HEDGE_BRIDGE.fullmatch(" or ") is not None
    # And the pattern that used to narrow this to branch 2 is gone, deliberately.
    assert not hasattr(tc, "_BARE_HEDGE_BRIDGE")


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


# =============================================================================
# 9. THE FOURTH PASS (2026-09-12). `and again`, the line-break class, and a
#    sweep whose SHAPE reaches the two rules and the terminal case the 476-cell
#    grid above structurally cannot.
# =============================================================================


#: The sentences `and again` used to read a second value out of, with the field the
#: second value was falsely proposed for. Ratcheted: a slice that put `and again`
#: back into `_BARE_HEDGES` turns every row red.
AND_AGAIN_RESIDUE: tuple[tuple[str, str, object], ...] = (
    (
        "The scan started 2026-01-01T00:00:00Z, and again 2026-01-02T00:00:00Z.",
        START,
        "2026-01-01T00:00:00Z",
    ),
    (
        "The scan ended 2026-01-01T00:00:00Z, and again 2026-01-02T00:00:00Z.",
        END,
        "2026-01-01T00:00:00Z",
    ),
    (
        "The scan started 2026-01-01T00:00:00Z, and again 2026-01-02T00:00:00Z, "
        "and again 2026-01-03T00:00:00Z.",
        START,
        "2026-01-01T00:00:00Z",
    ),
    ("The temperature was 425 K, and again 430 K.", TEMPERATURE, 425),
)


@pytest.mark.parametrize(
    "sentence,field_path,only",
    AND_AGAIN_RESIDUE,
    ids=["started", "ended", "chain of three", "temperature"],
)
def test_a_BARE_and_again_now_SELECTS_NO_VALUE_and_DISCLOSES(
    sentence, field_path, only
):
    """`and again` is a REPEAT marker, so a second value is a second EVENT.

    ~~``test_a_BARE_and_again_reads_one_value_and_DISCLOSES_the_rest``~~ —
    **INVERTED 2026-09-13 BY THE SEQUENCE GATE, and the `only` column of
    ``AND_AGAIN_RESIDUE`` is now the value that is NO LONGER SELECTED.** The old
    assertions are kept here verbatim, because this is a genuine change of
    behaviour and not a tidy-up:

        ~~``assert [c.proposed_value for c in reading.candidates
        if c.field_path == field_path] == [only]``~~
        ~~``assert [c.field_path for c in reading.candidates] == [field_path]``~~
        ~~``assert [e.kind for e in reading.abstentions] ==
        ["unhedged_further_values"]``~~

    **WHY IT CHANGED, AND WHY THE OLD BEHAVIOUR WAS THE DEFECT DEFECT-B NAMES.**
    Reading the FIRST value of *"the scan started A, and again B"* let a scientist
    accept A as the run's start while the sentence says the scan ran twice. The
    reader has no grounds to prefer A: nothing in the gap between the two values
    characterises either — `and` and `again` are pure coordination — so both are
    values of the field and neither is THE value. That is exactly the condition
    ``_SIBLING_GAP`` tests, and the outcome is that NO value is selected and the
    sentence is disclosed once.

    **THE LIKELIHOOD ARGUMENT FOR KEEPING A IS DELIBERATELY NOT TAKEN**, and this
    module has already recorded why: *"`again` before a full instant most naturally
    means the scan was REPEATED, which is a different run's instant"* is an argument
    about LIKELIHOOD, and ``_RESTATEMENT_RESIDUE_CLOSED``'s own comment records that
    a likelihood argument is not a §5 argument — it was the reason five silent
    fabrications shipped.

    **THE DEFECT THIS ROW ORIGINALLY PINNED SHUT IS UNCHANGED AND IS STILL PINNED.**
    `and again` sat in `_BARE_HEDGES` while bare `again` sat in
    `_OR_REQUIRED_HEDGES` *because* before a full instant `again` means the scan was
    REPEATED — two justifications, one module, opposite conclusions about the same
    word, with `and again` the STRONGER marker. Measured at `22d794a5`, the first
    two rows proposed BOTH instants as one field's value,
    `restated_in_same_sentence is True`, with `abstentions == ()`.
    `routes._mint_transcript_proposals` mints one durable OPEN proposal per
    candidate, so a scientist could accept a `timestamps` value nobody stated into a
    record that reaches an official export. §5 forbids an assertion in terms. That
    is now refused twice over, by the hedge gate and by the sequence gate.

    MUTATION: moving `and again` back into `_BARE_HEDGES` turns every row RED (two
    candidates instead of none). Removing `again` from `_SIBLING_COORDINATOR` turns
    every row RED by restoring `[only]`. Dropping the disclosure turns every row
    RED on the abstention assertion.
    """
    reading = _read(sentence)
    # NO value is selected -- including the one the old test asserted.
    assert reading.candidates == ()
    assert only not in [candidate.proposed_value for candidate in reading.candidates]
    # THE WITHHOLDING IS DISCLOSED EXACTLY ONCE, and names exactly the field.
    assert [entry.kind for entry in reading.abstentions] == [
        "several_values_and_none_selected"
    ]
    assert field_path in reading.abstentions[0].reason
    # And the words survive whatever the reader proposed — rule (4).
    assert [segment.text for segment in reading.segments] == [sentence]


def test_the_SAME_value_said_again_is_NOT_a_sequence_and_keeps_its_reading():
    """The cost the SEQUENCE GATE was briefed with, and the condition that avoids it.

    The orchestrator's brief named *"The temperature was 425 K, still 425 K at the
    end"* as a known consequence of withholding on "more than one UNHEDGED value",
    and asked whether disclosure made it acceptable. It does not have to be
    acceptable: the gate tests for more than one DISTINCT value, so a value restated
    identically is emphasis rather than a progression and keeps its reading. Two
    statements of the same number say the same thing about the field, so there is
    nothing to choose between.

    MUTATION: deleting the `_value_of(rule, extra) != _value_of(rule, match)`
    condition turns every row here RED.
    """
    for sentence in (
        "The temperature was 425 K, still 425 K at the end",
        "The temperature was 425 K, and again 425 K.",
        "The temperature was 425 K and 425 K",
        "The temperature was 425 K, then 425 K",
    ):
        assert _values(sentence) == [425], sentence
        # 425.0 and 425 must not count as two values to one test and one to the
        # other -- `_value_of` is shared with the de-duplication for that reason.
        assert _values("temperature 425 K, then 425.0 K") == [425], "int vs float"


def test_an_explicit_or_still_rescues_and_again():
    """The reason it was PARKED in `_OR_REQUIRED_HEDGES` and not deleted.

    `or` coordinates the new value WITH the old one, so an approximation modifier or
    a repeat marker behind it is scoped inside an alternative for the same quantity
    — the same argument `_OR_REQUIRED_HEDGES` already rests on for `or about`.
    `or and again` is not idiomatic English, so this is rare rather than
    theoretical; refusing it would be a second, smaller omission for no gain.

    MUTATION: deleting `and again` from `_HEDGE_CONNECTIVES` altogether turns this
    RED, which is what distinguishes parking it from removing it.
    """
    assert _values("The temperature was 425 K, or and again 430 K") == [425, 430]
    assert _read("The temperature was 425 K, or and again 430 K").abstentions == ()


def test_H_SPACE_excludes_exactly_the_line_boundary_whitespace():
    """`_LINE_BREAKS` is re-derived from `str.splitlines()`, never trusted as a list.

    **THE DOCUMENTED INVARIANT WAS FALSE FOR NINE OF TEN CHARACTERS.** `_H_SPACE`
    was `[^\\S\\n]` under a comment reading *"every whitespace character EXCEPT a
    line break"*, because *"a hedge on the far side of a line break is not
    'immediately between' two values."* It excluded ONE. Measured at `22d794a5` on
    `f"The temperature was 425 K,{c}maybe 430 K."`, all nine of `\\r`, `\\v`, `\\f`,
    `\\x1c`, `\\x1d`, `\\x1e`, `\\x85`, U+2028 and U+2029 bridged and read a second
    value SILENTLY; only `\\n` refused, and only because `_SEGMENT_BOUNDARY` splits
    the sentence in two before the gate is reached.

    **THEY WERE LIVE OVER HTTP, not hypothetical.** `_SEGMENT_BOUNDARY` splits on
    `\\n+` and on `\\s+` only after `[.!?]`, so a lone `\\r` survives inside one
    segment, and the transcript route applies no control-character filter — proved
    by the segment assertion below.

    A LIST WOULD HAVE BEEN GUESSED WRONG: a first attempt named five characters and
    the answer is ten. So the set is derived here from a definition rather than
    compared against a literal.

    MUTATION: restoring `[^\\S\\n]` turns this RED on nine characters. Adding
    `\\xa0` to `_LINE_BREAKS` turns the NBSP assertion RED.
    """
    whitespace = [
        chr(point) for point in range(0x110000) if re.fullmatch(r"\s", chr(point))
    ]
    boundaries = [c for c in whitespace if len(f"a{c}b".splitlines()) == 2]
    assert len(whitespace) == 29
    assert tuple(boundaries) == tuple(sorted(tc._LINE_BREAKS, key=ord))
    assert len(tc._LINE_BREAKS) == 10

    pattern = re.compile(tc._H_SPACE)
    for character in tc._LINE_BREAKS:
        assert pattern.fullmatch(character) is None, repr(character)
    assert sum(pattern.fullmatch(c) is not None for c in whitespace) == 19

    # END TO END, through the reader, on every one of the ten.
    for character in tc._LINE_BREAKS:
        sentence = f"The temperature was 425 K,{character}maybe 430 K."
        reading = _read(sentence)
        values = [
            candidate.proposed_value
            for candidate in reading.candidates
            if candidate.field_path == TEMPERATURE
        ]
        assert values == [425], (repr(character), values)
        if character == "\n":
            # The only one segmentation reaches: two sentences, so the second has no
            # label and there is nothing for this rule to withhold.
            assert len(reading.segments) == 2
            assert reading.abstentions == ()
        else:
            # THE NINE THAT WERE LIVE. One segment — so the route really did hand
            # this to the gate — and the withholding is disclosed.
            assert len(reading.segments) == 1, repr(character)
            assert [entry.kind for entry in reading.abstentions] == [
                "unhedged_further_values"
            ], repr(character)

    # NBSP IS NOT A LINE BOUNDARY AND STILL BRIDGES, deliberately: dictated text
    # contains it and the sentence is one line and one statement.
    assert "\xa0" not in tc._LINE_BREAKS
    assert _values("The temperature was 425 K,\xa0maybe 430 K.") == [425, 430]


#: Every connective form that must NOT bridge on its own — the shape the 476-cell
#: grid above structurally cannot build, because it only ever constructs forms that
#: DO bridge. Derived, so a connective that changes branch changes this set too.
_NON_BRIDGING_BARE: tuple[str, ...] = tc._OR_REQUIRED_HEDGES

#: Trailing phrases that make a following INSTANT belong to something else. Written
#: out rather than generated, for the reason `_MODIFIER_TAILS` gives.
#: **NO TAIL MAY NAME A RUN, and a first draft of this tuple did.** `" for the
#: second run"` trips `_VAGUE_RUN`, which raises a clarification, which leaves the
#: run target UNSETTLED, which withholds EVERY candidate — so 84 cells reported
#: `values == []` and property (2) read as satisfied for a reason that had nothing to
#: do with the tail. The sweep now asserts `clarifications == ()` on every cell, so
#: the trap fails loudly instead of flattering the result.
#: No leading space: the template below inserts one only for a non-empty tail, so
#: the empty row really is terminal. A first draft carried the spaces here and
#: `_MODIFIER_TAILS` does not, which produced `"430 Kof drift"` — a sentence no rule
#: matches at all, in 714 cells that then read as silent withholdings.
_INSTANT_TAILS: tuple[str, ...] = (
    "",
    "for the second acquisition",
    "after the restart",
    "in the previous scan",
    "plus one day",
)


#: The temperature row's tails, WITH THE TERMINAL (empty) CASE — added 2026-09-13
#: after an independent review measured that neither committed sweep built it.
#:
#: The claim was *"tails including the EMPTY one … all three restatement-carrying
#: rules"*, and it was true of TWO of three: `_MODIFIER_TAILS` has a non-empty tail
#: in every entry by construction, and the tuple that DOES contain `""` —
#: `_INSTANT_TAILS` — was handed only to the two instant rules. So the 42
#: temperature terminal cells (21 connectives x 2 separators) existed in no sweep.
#: The review built them and found them clean; they are added here so the coverage
#: claim is true MECHANICALLY rather than by having been checked once.
_TEMPERATURE_TAILS: tuple[str, ...] = ("",) + _MODIFIER_TAILS


#: How many of the cells the SEQUENCE GATE withholds, MEASURED rather than
#: predicted. Named as a constant so the number appears once and so the assertion
#: that reads it cannot be mistaken for arithmetic. ~~36~~ at 17 temperature tails;
#: the 42 terminal cells added on 2026-09-13 moved it.
_SEQUENCE_GATE_CELLS = 40


def test_the_INSTANT_AND_EMPTY_TAIL_SWEEP_fabricates_nothing_in_silence():
    """The sweep the 476-cell grid's SHAPE excludes, and stating that is the fix.

    **WHAT THE OTHER GRID CANNOT SEE.** Every one of its cells is
    `f"The temperature was 425 K{sep}{connective} 3 K {tail}"` — ONE of the five
    rules, and a NON-EMPTY tail in every cell, built only from connectives that DO
    bridge. So the two INSTANT rules and the terminal (empty-tail) case are both
    structurally outside it, and that is exactly how the `and again` fabrication
    reached `main` with 510 cells green. A sweep whose shape excludes a rule cannot
    clear that rule.

    **THE SCOPE OF THIS ONE, STATED BESIDE ITS NUMBER.** Three rules (the three that
    HAVE a restatement pattern), `_ALL_CONNECTIVES` + every non-bridging BARE form,
    tails including the EMPTY one **for all three rules — corrected 2026-09-13, when
    an independent review measured that the empty tail reached only the two INSTANT
    rules.** `_MODIFIER_TAILS` has a non-empty tail in every entry by construction
    and was the temperature row's whole tail set, so the 42 temperature terminal
    cells were in no committed sweep at all; `_TEMPERATURE_TAILS` adds them. Two
    separators. The phrase rules
    (`atmosphere`, `environment`) are absent because they carry no restatement and
    can refuse nothing.

    **THE THREE PROPERTIES, and none of them re-derives the implementation.**

    1. **Nothing is invented.** Every proposed value appears verbatim in the
       sentence.
    2. **A trailing phrase always wins.** With a NON-EMPTY tail, only the FIRST
       value is ever proposed — a later instant behind `for the second run` is
       another run's, and a later kelvin figure behind `of drift` is a drift.
    3. **A non-bridging BARE connective never yields a second value**, whatever the
       tail. This is the `and again` property, generalised over all seven.
    4. **No withholding is silent.** If the second stated value was not proposed,
       the reading discloses.

    MUTATION: moving any member of `_OR_REQUIRED_HEDGES` into `_BARE_HEDGES` turns
    property 3 RED. Scoping condition 3 back to the bare-hedge branch turns property
    2 RED. Deleting either refusal `pending.append` turns property 4 RED.
    """
    grid = (
        (
            TEMPERATURE,
            "The temperature was 425 K",
            "430 K",
            425,
            430,
            _TEMPERATURE_TAILS,
        ),
        (
            START,
            "The scan started 2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
            "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
            _INSTANT_TAILS,
        ),
        (
            END,
            "The scan ended 2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
            "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
            _INSTANT_TAILS,
        ),
    )
    connectives = _ALL_CONNECTIVES + _NON_BRIDGING_BARE
    assert len(connectives) == 21
    invented: list[tuple[str, list]] = []
    read_behind_a_tail: list[tuple[str, list]] = []
    read_behind_a_bare_repeat: list[tuple[str, list]] = []
    silent: list[str] = []
    #: Cells where the SEQUENCE GATE selected NO value. Collected and asserted
    #: below rather than merely tolerated, so the gate's reach over this grid is a
    #: measured number and a later change to it moves a visible assertion.
    none_selected: list[str] = []
    checked = 0
    for field_path, head, second, first_value, second_value, tails in grid:
        for connective in connectives:
            for tail in tails:
                for separator in (", ", " "):
                    spaced = f" {tail}" if tail else ""
                    sentence = f"{head}{separator}{connective} {second}{spaced}."
                    checked += 1
                    reading = _read(sentence)
                    # NOT A PROPERTY UNDER TEST — a GUARD ON THE FIXTURE. A run
                    # clarification withholds every candidate, so a cell that
                    # accidentally names a run satisfies properties 2 and 3
                    # vacuously. See `_INSTANT_TAILS`.
                    assert reading.clarifications == (), sentence
                    values = [
                        candidate.proposed_value
                        for candidate in reading.candidates
                        if candidate.field_path == field_path
                    ]
                    # ~~`assert values, sentence`~~ — **WITHDRAWN 2026-09-13.**
                    # It required every cell to propose SOMETHING, which the
                    # SEQUENCE GATE deliberately stops doing: when the second
                    # value is an indistinguishable sibling of the first (complete
                    # unit, clean continuation, pure coordination in the gap, and a
                    # different value) the sentence states the field twice and says
                    # nothing about which statement is the field's, so NO value is
                    # selected. Withdrawing it does not weaken the sweep, because
                    # property (4) below is what carried the §5 content — every
                    # withholding is DISCLOSED — and it now covers the first value
                    # as well as the second. Counted and asserted instead, so the
                    # size of the change is visible rather than absorbed.
                    if not values:
                        none_selected.append(sentence)
                        assert [
                            entry.kind for entry in reading.abstentions
                        ] == ["several_values_and_none_selected"], sentence
                    # (1) nothing invented
                    if any(str(value) not in sentence for value in values):
                        invented.append((sentence, values))
                    # (2) a trailing phrase always wins -- restated 2026-09-13 as
                    # "the SECOND value is never proposed behind a tail", which is
                    # the §5 half. The first value may additionally be withheld by
                    # the sequence gate, and when it is, the cell is in
                    # `none_selected` and its disclosure is asserted above.
                    if tail and values not in ([first_value], []):
                        read_behind_a_tail.append((sentence, values))
                    # (3) a non-bridging BARE connective never yields a second value
                    if connective in _NON_BRIDGING_BARE and values not in (
                        [first_value],
                        [],
                    ):
                        read_behind_a_bare_repeat.append((sentence, values))
                    # (4) no withholding is silent
                    if second_value not in values and not reading.abstentions:
                        silent.append(sentence)
    assert checked == 21 * 2 * (
        len(_TEMPERATURE_TAILS) + 2 * len(_INSTANT_TAILS)
    )
    # ~~1134~~ at 17 temperature tails. The 42 terminal cells added 2026-09-13 take
    # it to 1,176, and the arithmetic above is what holds the relationship.
    assert checked == 1176, checked
    assert len(_TEMPERATURE_TAILS) == len(_MODIFIER_TAILS) + 1 == 18
    assert invented == [], invented[:5]
    assert read_behind_a_tail == [], read_behind_a_tail[:5]
    assert read_behind_a_bare_repeat == [], read_behind_a_bare_repeat[:5]
    assert silent == [], silent[:5]
    # THE SEQUENCE GATE'S REACH OVER THIS GRID, as an exact number rather than as
    # a tolerated absence. MEASURED at the commit that added the gate. Every one of
    # these cells is asserted above to carry exactly one
    # `several_values_and_none_selected` disclosure, so a change that grew this set
    # silently would have to make a withholding silent first — which property (4)
    # refuses — and a change that SHRANK it moves this line.
    assert len(none_selected) == _SEQUENCE_GATE_CELLS, len(none_selected)
    # It is a MINORITY of the grid: the gate fires only where the gap between the
    # two values is pure coordination, and most of these 1,134 cells put a hedging
    # or approximating connective there instead.
    assert 0 < len(none_selected) < checked // 2


def test_the_option_ceilings_derivation_is_held_by_this_test_not_by_arithmetic():
    """`MAX_DISCLOSURE_OPTIONS` is a bare literal and its comment says a TEST holds
    the derivation. This is that test.

    The same shape as
    `test_the_cap_comment_no_longer_claims_an_arithmetic_link_it_does_not_have`
    above, and for the same reason: the constant CANNOT reference `routes`, because
    `routes` imports this module. So the derivation it claims —
    `MAX_SEGMENTS` x `routes.RUN_PAGE_MAX`, a transcript at the segment ceiling
    naming one unresolvable run per sentence on a record at the largest run page
    this application serves — is not enforced by the expression and has to be
    enforced here.

    **THIS TEST EXISTS BECAUSE A MUTANT SURVIVED.** Changing the constant
    20,000 -> 20,001 left all 305 transcript tests GREEN: the boundary test's
    admitted/refused pair only pins the interval (19,990, 21,989], because its
    margin is one RUN and a run is worth 1,999 options. An interval that wide is not
    a pinned constant, and a comment claiming a derivation nothing checks is the
    "guard with a false rationale" this module has already had to delete once.

    MUTATION: any change to `MAX_DISCLOSURE_OPTIONS`, `MAX_SEGMENTS` or
    `routes.RUN_PAGE_MAX` that breaks the product turns this RED.
    """
    assert tc.MAX_DISCLOSURE_OPTIONS == tc.MAX_SEGMENTS * routes.RUN_PAGE_MAX
    assert tc.MAX_DISCLOSURE_OPTIONS == 20_000
    # And it is NOT redundant with the disclosure ceiling in either direction: it is
    # far above it (so a bounded disclosure count does not imply a bounded option
    # total only because the numbers happen to be close) and far below the product
    # of the two (so it is not merely `MAX_DISCLOSURES` restated).
    assert tc.MAX_DISCLOSURE_OPTIONS > tc.MAX_DISCLOSURES
    assert tc.MAX_DISCLOSURE_OPTIONS < tc.MAX_DISCLOSURES * routes.RUN_PAGE_MAX


# =============================================================================
# 11. THE FIFTH PASS (2026-09-13). The PASS-ONE ASSERTION GATE, the SEQUENCE
#     GATE, and the parity guard the served policy has never had.
# =============================================================================


#: The twenty members of the label-overreach class an INDEPENDENT REVIEW found on
#: 2026-09-13, none of which was in `_LABEL_OVERREACH_CLOSED`'s thirteen rows.
#:
#: **THIS TUPLE IS THE EVIDENCE THAT THE FIX IS A CLASS AND NOT A TABLE, which is
#: the one thing a table of known reproductions cannot establish about itself.**
#: Nineteen of the twenty are refused by `_ASSERTION_BRIDGE` without any of them
#: having been known to it when it was written. The twentieth is in
#: `tc._PRE_LABEL_OVERREACH_CLOSED` and was asserted STILL OPEN below, because its
#: re-subjecting word is to the LEFT of the label where the bridge has no reach.
#: **IT IS NOW CLOSED TOO, by GATE (4) — and by a grammar rather than by naming it,
#: which is the same argument one level up: `_PRE_LABEL` admits no verb of change in
#: the pre-label slot, so `lowered` is refused without appearing anywhere.**
_REVIEW_CORPUS_2026_09_13: tuple[str, ...] = (
    "The temperature setpoint was 350 K",
    "The temperature tolerance was 1 K",
    "The temperature noise was 0.3 K",
    "The temperature ramp was 5 K",
    "The temperature range was 300 K",
    "The temperature spread was 4 K",
    "temperature FWHM 2 K",
    "We raised the temperature by 40 K",
    "The temperature differed by 6 K",
    "The temperature is accurate to 0.5 K",
    "The temperature was within 3 K of target",
    "Temperature control was good to 1 K",
    "The temperature scale is calibrated to 2 K",
    "The cryostat temperature offset is 9 K",
    "The temperature drifted 2 K over the hour",
    "The second temperature step was 5 K",
    "It finished drifting at 2026-01-01T00:00:00Z",
    "The beam started tripping at 2026-01-01T00:00:00Z",
    "The cooldown ended dripping at 2026-01-01T00:00:00Z",
)


@pytest.mark.parametrize("sentence", _REVIEW_CORPUS_2026_09_13)
def test_an_INDEPENDENTLY_FOUND_member_of_the_class_is_also_closed(sentence):
    """A corpus the gate was NOT built against, refused by the gate anyway.

    Nineteen rows, found by a reviewer hunting the same class from scratch. Not one
    of them appears in `_LABEL_OVERREACH_CLOSED`, in the bridge grammar, or in the
    adversarial generator the fix was developed against — so each is an out-of-sample
    test of the grammar rather than a confirmation of a list.

    **THREE OF THEM ARE THE INSTANT SUB-CLASS** (`finished drifting at`,
    `started tripping at`, `ended dripping at`), which the module's own comment
    records its temperature-only tuple has never covered.

    MUTATION: replacing `_ASSERTION_BRIDGE` with a denylist of the thirteen closed
    rows' nouns (`drift|error|step|…`) leaves the thirteen green and turns MOST of
    these RED — which is precisely why the fix is a grammar.
    """
    reading = _read(sentence)
    assert reading.candidates == (), [
        (candidate.field_path, candidate.proposed_value)
        for candidate in reading.candidates
    ]
    # AND IT IS DISCLOSED. A silent refusal would be a different defect of the same
    # §5 rank, so this is asserted and not assumed.
    assert [entry.kind for entry in reading.abstentions] == [
        "label_does_not_assert_this_value"
    ]
    assert [segment.text for segment in reading.segments] == [sentence]


@pytest.mark.parametrize("sentence", tc._PRE_LABEL_OVERREACH_CLOSED)
def test_the_PRE_LABEL_overreach_is_CLOSED(sentence):
    """**INVERTED IN PLACE, not deleted.** This test asserted these nine sentences
    STILL FABRICATED, deliberately the wrong way round, and its own failure message
    named the remedy: *"if this reads nothing the PRE-LABEL sub-class is CLOSED —
    delete the row … and say so, do not weaken this"*. Gate (4)
    (:data:`tc._PRE_LABEL`) closed them, so the assertion is turned over rather than
    relaxed, and the constant is RENAMED rather than emptied — the precedent
    `_LABEL_OVERREACH_CLOSED` and `_RESTATEMENT_RESIDUE_CLOSED` both set. The whole
    original docstring is kept below, because the reasoning that referred the class
    three times is the most useful thing here.

    **WHAT NOW HOLDS:** each row proposes NOTHING and raises exactly one
    `words_before_the_label_name_something_else` abstention. Both halves are
    asserted: a silent refusal would be a §5 defect of the same rank as the
    fabrication, which is exactly what the pre-inversion version of this test
    pinned (`assert _read(sentence).abstentions == ()`).

    MUTATION: deleting the `_label_is_the_subject` call from the reading loop turns
    every row here RED on the candidate assertion; leaving the call but dropping the
    `gate_refusals.append` turns every row RED on the abstention assertion — so the
    two assertions are independently load-bearing and neither is decoration.

    ── THE ORIGINAL, KEPT ──────────────────────────────────────────────────────

    KNOWN-OPEN §5 defects of a DIFFERENT sub-class, asserted to still occur.

    ── TWO FORMS, AND THE TUPLE GREW FROM ONE TO NINE ON 2026-09-13 ───────────

    What they share is the only thing that matters here: **the word that
    re-subjects the quantity sits to the LEFT of the label, where a bridge grammar
    has no reach by construction.** Both allowlists look rightward —
    `_ASSERTION_BRIDGE` reads label -> value, `_VALUE_CONTINUATION` reads value ->
    end — so neither can see upstream of the label at all.

    1. THE DELTA FORM (`"We lowered the temperature 15 K"`), the original row. Its
       bridge is EMPTY: the value is juxtaposed, exactly as in
       `"temperature 425 K"`, which this reader must keep reading.

    2. THE MODIFIER FAMILY (eight rows, added after an independent review found
       them), e.g. `"The setpoint temperature was 425 K"`. Here the bridge is
       `" was "` — **the very bridge the gate exists to ADMIT**, and correctly so.
       There is nothing wrong with what the gate sees; the disqualifying word is
       somewhere it never looks.

    ── WHY THIS TEST'S OWN PREVIOUS DOCSTRING WAS PART OF THE DEFECT ─────────

    It said "The twentieth row of the reviewer's corpus", describing ONE sentence,
    while the constant it parametrises over claimed to hold *"THE ONE MEMBER OF THE
    CLASS"*. Both were overclaims: the family above was never hunted for. The
    lesson the module records — that a corpus generated from the same mental model
    as the fix tests the fix's REACH and not its PREMISE — applied to this file too.

    Asserted the WRONG WAY ROUND on purpose, the same discipline
    `_LABEL_OVERREACH_CLOSED` was held to before it was closed: shutting any of
    these requires DELETING a row from `tc._PRE_LABEL_OVERREACH_CLOSED` — a
    reviewed change — rather than discovering that a documented open item quietly
    went away.

    See that constant for why no proxy works: a denylist of nouns or verbs fails
    OPEN, and the real distinction is between a modifier that RE-SUBJECTS the
    quantity and one that merely LOCATES it (`"Sample temperature at the second
    scan was 425 K"` must keep reading), which is not decidable by bridge shape.

    ── AND THE LAST SENTENCE OF THAT ORIGINAL IS WHERE IT WENT WRONG ───────────

    "Not decidable by bridge SHAPE" is true and is why gate (4) is a fourth gate.
    "A denylist of nouns fails OPEN" is true and settles the DENYLIST only. The
    POLARITY was never examined across three referrals: an ALLOWLIST of the same
    nouns fails CLOSED, costing a disclosed reading instead of minting a silent
    value. `"Sample temperature at the second scan was 425 K"` still reads, because
    `sample` is an admitted locator — so the reading the referrals protected was
    never actually in tension with closing the class.
    """
    rows = _rows(sentence)
    assert rows == [], (
        "gate (4) must refuse every row of _PRE_LABEL_OVERREACH_CLOSED; a reading "
        "here means the pre-label class has REOPENED"
    )
    reading = _read(sentence)
    assert reading.candidates == (), [
        (candidate.field_path, candidate.proposed_value)
        for candidate in reading.candidates
    ]
    # AND IT IS DISCLOSED. The pre-inversion version of this test asserted
    # `abstentions == ()` — that the fabrication was SILENT — so this line is the
    # exact inversion of the pinned defect, not an addition beside it.
    assert [entry.kind for entry in reading.abstentions] == [
        "words_before_the_label_name_something_else"
    ]
    assert [segment.text for segment in reading.segments] == [sentence]


@pytest.mark.parametrize("sentence", tc._RUN_MISATTRIBUTION_CLOSED)
def test_the_RUN_MISATTRIBUTION_on_the_instant_rules_is_CLOSED(sentence):
    """**INVERTED IN PLACE, not deleted**, exactly as its sibling above was, and for
    the same reason: this test asserted the misattribution STILL HAPPENED and told a
    future slice to delete the row and say so. Gate (4) closed it.

    **THE REFERRAL'S PREMISE WAS FALSE, AND THAT IS WORTH MORE THAN THE FIX.** It
    said closing this needs REFERENT RESOLUTION — knowing WHICH scan the sentence is
    about. It does not. This reader never had to decide what `"the previous scan"`
    names; it had only to notice that the sentence does not say it is THIS one, and
    refuse. **Deciding a referent and declining to decide it are different acts, and
    only the first is the hard problem.** The general form: *"fixing this requires
    knowing X"* is a claim about a fix that ASSERTS, and a refusal asserts nothing,
    so the requirement usually does not transfer.

    And the fear the referral was right to have — that a guess would replace one
    misattribution with another — is answered by measurement rather than intent:
    nothing is proposed at all, and the transcript is retained in full.

    MUTATION: removing `previous`/`last`/`calibration`/`reference` handling is not
    possible, because the gate never names them — it admits `scan`/`run` and refuses
    every other pre-modifier. Deleting `_label_is_the_subject` from the loop, or
    adding an open `[A-Za-z]+` to `_PRE_LABEL_NOUN`, turns every row here RED.

    ── THE ORIGINAL, KEPT ──────────────────────────────────────────────────────

    A KNOWN-OPEN §5 defect of a SECOND, DISTINCT class — and arguably the worst
    one this module has, which is why it is pinned separately rather than folded in.

    Found by independent review, 2026-09-13, and re-measured before being pinned.

    **THE INSTANT RULES DO NOT ANCHOR ON `"scan"` AT ALL.** The pattern is
    `\b(?:ended|end|finished|stopped)\b[^.;:]{0,40}?<instant>` — it anchors on the
    VERB. So it never asks WHICH scan ended, and a sentence about a previous,
    calibration, dark or reference scan yields an instant for **the run currently
    selected**.

    That is worse than reading the wrong QUANTITY, and the difference is worth
    stating: the value is a real acquisition time, correctly parsed, of a different
    measurement — attributed to this one. A scientist reviewing the proposal sees a
    plausible timestamp and no signal at all that it belongs elsewhere.

    PRE-EXISTING: `git show 2f9a1133:apps/api/isaac_api/transcript_capture.py`
    carries the same verb-anchored pattern, so this gate neither introduced nor
    worsened it.

    NOT FIXED because it is a REFERENT-RESOLUTION problem rather than a
    pattern-shape one. Deciding that "the previous scan" is not "this run" requires
    knowing which scan the sentence is about; guessing would substitute one
    misattribution for another. Asserted the wrong way round, like its sibling
    above, so closing it is a reviewed deletion rather than a silent disappearance.
    """
    reading = _read(sentence)
    assert reading.candidates == (), [
        (candidate.field_path, candidate.proposed_value)
        for candidate in reading.candidates
    ]
    # AND IT IS DISCLOSED — the exact inversion of the pinned defect, which asserted
    # `reading.abstentions == ()`. A real acquisition time belonging to a different
    # measurement is the worst fabrication this module had; it is now a refusal the
    # scientist can see and act on.
    assert [entry.kind for entry in reading.abstentions] == [
        "words_before_the_label_name_something_else"
    ]
    # AND THE INSTANT FIELDS ARE STILL READ WHEN THE SENTENCE IS ABOUT THIS RUN.
    # A negative control in the same test, so a gate that refused every instant
    # would pass the two assertions above and fail here.
    this_run = sentence.replace("previous ", "").replace("last ", "")
    this_run = this_run.replace("calibration ", "").replace("reference ", "")
    control = _read(this_run)
    assert [candidate.field_path for candidate in control.candidates] == [
        "timestamps.acquired_end_utc"
        if "ended" in this_run
        else "timestamps.acquired_start_utc"
    ], (this_run, control.candidates)


def test_the_PREPOSITIONAL_forms_of_the_same_sentence_ARE_closed():
    """The pre-label residue is one FORM, not one family, and this is the boundary.

    Every version of that sentence whose re-subjecting word reaches INSIDE the
    bridge is refused. It is here so the open row above cannot be read as "verbs of
    change before the label are unhandled" — they are handled whenever a preposition
    puts them in the bridge's reach, which is the commoner phrasing.
    """
    for sentence in (
        "We lowered the temperature by 15 K",
        "We raised the temperature by 40 K",
        "We corrected the temperature by 7 K",
        "We dropped the temperature by 5 K",
        "We brought the temperature down by 5 K",
    ):
        reading = _read(sentence)
        assert reading.candidates == (), sentence
        assert [entry.kind for entry in reading.abstentions] == [
            "label_does_not_assert_this_value"
        ], sentence


def test_the_instant_VALUE_BOUNDARY_overreach_is_refused_AND_disclosed():
    """A sub-class the review separates explicitly: the value's own boundaries.

    `_INSTANT` carries neither of the boundary guards `_TEMPERATURE_K_RESTATED` was
    deliberately given, so a five-digit year matched the SUBSTRING and a trailing
    `ulu` matched with an overreach — each proposing an instant the transcript does
    not state AS A TOKEN. Both are refused, and **neither is refused by a
    lookbehind**: the review's suggested `(?<![\\d.])` was added, measured and
    REVERTED, because with it the rule stops matching and the leading-digit form
    produces NO abstention at all. §5 ranks a disclosed omission above a silent one.

    This test is what makes that choice safe: it pins the outcomes rather than the
    mechanism, so if the pass-one gate ever stops covering them it goes RED here.

    MUTATION: admitting a digit to `_ASSERTION_BRIDGE` turns the first row RED;
    admitting a bare unknown word to `_VALUE_CONTINUATION` turns the second RED.
    """
    leading = _read("The scan started 12026-01-01T00:00:00Z")
    assert leading.candidates == ()
    assert [entry.kind for entry in leading.abstentions] == [
        "label_does_not_assert_this_value"
    ]
    trailing = _read("The scan started 2026-01-01T00:00:00Zulu")
    assert trailing.candidates == ()
    assert [entry.kind for entry in trailing.abstentions] == [
        "value_qualified_by_what_follows"
    ]
    # AND THE CALENDAR IS DELIBERATELY NOT RANGE-CHECKED. Asserted so the decision
    # is visible rather than implied by an absence — see `_INSTANT`'s comment for
    # the three reasons, of which the load-bearing one is that CLAUDE.md §15's Q20
    # ruling keeps `format` enforcement non-gating and OUTSIDE the truth plane, so
    # an extraction-time calendar check would be stricter than the official
    # validator is authorized to be.
    absurd = _read("The scan started 2026-13-45T99:99:99Z")
    assert [candidate.proposed_value for candidate in absurd.candidates] == [
        "2026-13-45T99:99:99Z"
    ]
    # It is a VERBATIM quote of what the scientist wrote, which is the whole basis
    # for not refusing it: they are shown their own typo, not a reader's guess.
    assert absurd.candidates[0].proposed_value in absurd.segments[0].text


# =============================================================================
# 12. C-1: THE SERVED POLICY AGAINST THE HEDGE LISTS. The parity guard that has
#     never existed, on a claim that has now been wrong five times.
# =============================================================================


def test_the_SERVED_policy_enumeration_is_DERIVED_from_the_hedge_lists():
    """The served `ambiguity_policy` versus `_BARE_HEDGES`/`_OR_REQUIRED_HEDGES`.

    **THE DEFECT THIS CLOSES WAS A SINGLE RESPONSE BODY CONTRADICTING ITSELF.**
    `7afbe633` moved `and again` out of `_BARE_HEDGES` into `_OR_REQUIRED_HEDGES`,
    correctly updated all three `_RULES.restated_sentence` strings, and did not
    sweep the two `AMBIGUITY_POLICY` rows — which are SERVED (`routes.py:15406`),
    TYPED (`apps/web/src/lib/types.ts`), and whose route docstring says
    `ambiguity_policy` "states each rule". Measured at the route by an independent
    review: one response carried a candidate, a policy string saying `and again`
    bridges on its own, and an abstention saying it did not. A client rendering that
    policy promises a reader that a second value WILL be read when it will not.

    **TWO GUARDS WERE WRITTEN FOR THIS AND BOTH WERE DECORATIVE, WHICH IS WHY THE
    TEST NOW CHECKS DERIVATION RATHER THAN WORDING. Recording both failures, because
    each is the exact defect class this module keeps producing:**

    1. `"or" in clause` — the word **"word"** contains `or`, and the clause this
       guard selected rows by is *"a hedging word from a closed list"*. It passed
       every row for a reason having nothing to do with the claim. Caught only by
       `test_the_parity_guard_can_report_RED`.
    2. `re.search(r"\bor\b", clause)` — correct as a word test, and STILL GREEN on
       the exact pre-fix text, measured. That enumeration is ONE clause and it ends
       *"a bare 'or', or an approximation behind an explicit 'or'"*, so `or` is
       always present in the window. **A guard that cannot fail on the defect it
       was written for is worse than no guard**, because it reads as coverage.

    So the served strings are now BUILT from the two lists (`_BARE_BRIDGING_WORDS`,
    `_OR_ONLY_BRIDGING_WORDS`), and this test asserts that derivation. The class of
    defect is removed rather than detected: the served text cannot place a
    connective in the wrong group because it does not name them individually.

    MUTATION: retyping either enumeration as a literal turns this RED. Moving a
    connective between the two lists changes the served text automatically, so the
    drift C-1 was cannot recur — proved by
    `test_the_derivation_tracks_a_connective_moving_between_the_lists`.
    """
    import re

    rows = [
        row
        for row in tc.AMBIGUITY_POLICY
        if tc._OR_ONLY_BRIDGING_WORDS in row["rule"]
    ]
    assert {row["kind"] for row in rows} == {
        "conflicting_values_for_one_field",
        "unhedged_further_values",
    }, "the two rows that enumerate the connectives, by derivation not by name"

    for row in rows:
        text = row["rule"]
        # BOTH derived strings, so a row cannot serve one group and retype the other.
        assert tc._BARE_BRIDGING_WORDS in text, row["kind"]
        assert tc._OR_ONLY_BRIDGING_WORDS in text, row["kind"]
        # AND NO OR-REQUIRED CONNECTIVE IS QUOTED OUTSIDE THE DERIVED SEGMENT. This
        # is the assertion the two failed guards were reaching for, and it is exact
        # rather than windowed: a position test, not a keyword search.
        span = text.index(tc._OR_ONLY_BRIDGING_WORDS)
        derived = range(span, span + len(tc._OR_ONLY_BRIDGING_WORDS))
        for connective in tc._OR_REQUIRED_HEDGES:
            # The mechanical truth the row must not contradict.
            assert tc._HEDGE_BRIDGE.fullmatch(f" {connective} ") is None, connective
            for occurrence in re.finditer(rf"'{re.escape(connective)}'", text):
                assert occurrence.start() in derived, (
                    f"{row['kind']}: {connective!r} is quoted OUTSIDE the derived "
                    f"or-required enumeration, which is how C-1 read as a promise "
                    f"that a bare {connective!r} bridges"
                )
        # The bare-bridging words ARE allowed to appear on their own, and each one
        # genuinely does bridge on its own.
        for connective in tc._BARE_HEDGES:
            assert tc._HEDGE_BRIDGE.fullmatch(f" {connective} ") is not None


def test_the_derivation_tracks_a_connective_moving_between_the_lists():
    """The property C-1 violated, proved by MOVING one rather than by reasoning.

    `and again` moved between the two lists and five copies of the claim had to be
    swept by hand; two were missed. This rebuilds the derived strings from mutated
    lists and asserts the served enumeration would have followed automatically —
    which is what makes the derivation a fix and not a restatement.
    """
    moved_bare = tuple(
        word for word in tc._OR_REQUIRED_HEDGES if word != "and again"
    )
    rebuilt_or_only = ", ".join(f"'{word}'" for word in moved_bare)
    # The CURRENT served text contains `and again` in the or-only group...
    assert "'and again'" in tc._OR_ONLY_BRIDGING_WORDS
    # ...and a rebuild after the move would not, without any prose being edited.
    assert "'and again'" not in rebuilt_or_only
    assert rebuilt_or_only != tc._OR_ONLY_BRIDGING_WORDS
    # And the two groups are disjoint, so no connective can be in both.
    assert not set(tc._BARE_HEDGES) & set(tc._OR_REQUIRED_HEDGES)


def test_the_parity_guard_can_report_RED():
    """The guard above, proved falsifiable ON THE REAL PRE-FIX TEXT.

    **THIS TEST IS THE REASON TWO EARLIER GUARDS WERE THROWN AWAY, so it asserts
    against the actual strings that shipped rather than against a hand-made mutant
    that happens to trip it.** The two rows are quoted verbatim as they read before
    the fix, and all three candidate predicates are run over them:

    * `"or" in clause` — GREEN on both (vacuous: "word" contains "or");
    * `\bor\b` — GREEN on both (the enumeration is one clause and mentions "or");
    * the DERIVED check — RED on both, which is the one that shipped.
    """
    import re

    pre_fix = (
        "A sentence states more than one value of the same form for one field, and "
        "only the labelled one was read. A second value is read as an alternative "
        "for the same field only when THREE things hold, and this row is the first "
        "two of them: a hedging word from a closed list links it to the first with "
        "nothing else in the gap - 'maybe', 'perhaps', 'and again', "
        "'alternatively', a bare 'or', or an approximation behind an explicit 'or' "
        "such as 'or about' - and the value is not part of a larger unit such as "
        "K/min",
        "Inside ONE sentence a second value is read only when a hedging word - "
        "'maybe', 'perhaps', 'or', 'about', 'and again' and the like, from a closed "
        "list - sits immediately between the two, with nothing else in the gap",
    )

    def clause_of(text: str, at: int) -> str:
        start = text.rfind(".", 0, at) + 1
        end = text.find(".", at)
        return text[start : end if end != -1 else len(text)]

    def substring_guard(text: str) -> bool:
        for connective in tc._OR_REQUIRED_HEDGES:
            for occ in re.finditer(rf"'{re.escape(connective)}'", text):
                if "or" not in clause_of(text, occ.start()):
                    return False
        return True

    def word_guard(text: str) -> bool:
        for connective in tc._OR_REQUIRED_HEDGES:
            for occ in re.finditer(rf"'{re.escape(connective)}'", text):
                if not re.search(r"\bor\b", clause_of(text, occ.start())):
                    return False
        return True

    def derived_guard(text: str) -> bool:
        if tc._OR_ONLY_BRIDGING_WORDS not in text:
            return False
        span = text.index(tc._OR_ONLY_BRIDGING_WORDS)
        derived = range(span, span + len(tc._OR_ONLY_BRIDGING_WORDS))
        for connective in tc._OR_REQUIRED_HEDGES:
            for occ in re.finditer(rf"'{re.escape(connective)}'", text):
                if occ.start() not in derived:
                    return False
        return True

    for text in pre_fix:
        # BOTH REJECTED GUARDS PASS THE DEFECT. This is the measurement, committed.
        assert substring_guard(text), "recorded: the substring guard was vacuous"
        assert word_guard(text), "recorded: \\bor\\b was GREEN on the real defect"
        # AND THE ONE THAT SHIPPED FAILS IT.
        assert not derived_guard(text), "the derived check must reject the pre-fix row"

    # And it PASSES every row actually served, so it is not merely strict.
    for row in tc.AMBIGUITY_POLICY:
        if tc._OR_ONLY_BRIDGING_WORDS in row["rule"]:
            assert derived_guard(row["rule"]), row["kind"]


def test_no_refusal_reason_CONTAINS_A_DIGIT_at_all():
    """The module's own standing rule, applied to all five reasons mechanically.

    `_REFUSAL_REASONS`' comment states it for one entry: *"every digit that would
    read naturally there ('3 K of drift') also appears in the measured sentences
    this closes, so an example would look like a leak of the withheld value and a
    test asserting it was not one would be asserting a coincidence."*

    **THAT RULE WAS THEN BROKEN BY THE NEXT THREE REASONS ADDED AFTER IT, TWICE IN
    ONE SLICE.** `several_values_and_none_selected` shipped illustrating itself with
    *"was 300 K, then 350 K, then 400 K"* and an existing test caught it, because on
    that very sentence the illustration IS the withheld values.
    `label_does_not_assert_this_value` and `value_qualified_by_what_follows` then
    shipped with the same defect (*"rose by 30 K"*, *"3 K above target"*) and were
    caught by a sweep rather than by a test. So the rule is now MECHANICAL and
    applies to every reason, present and future: no digit, anywhere.

    It is a stronger assertion than "does not leak the withheld value", and
    deliberately so — the leaking version is unprovable in general (it depends on
    which sentence fired the reason) while this one is decidable by reading the
    string. The named constructions ("a drift, an error, a step") carry the same
    information to the scientist without the coincidence.

    MUTATION: putting any numeric example back into any reason turns this RED.
    """
    import re

    # 5 -> 6 on 2026-09-13: GATE (4) added `words_before_the_label_name_something
    # _else`. The ratchet is what forced its reason through this sweep at all, and
    # the sweep below is what forced a sentence FIRING it to be added — a new kind
    # cannot be admitted here while going unexercised.
    assert len(tc._REFUSAL_REASONS) == 6
    for kind, reason in tc._REFUSAL_REASONS.items():
        digits = sorted(set(re.findall(r"[0-9]", reason)))
        assert digits == [], f"{kind} names digit(s) {digits}: {reason!r}"
        # And each is still parameterised on the field path, so a disclosure always
        # says WHICH field withheld -- the half that makes the omission §5-acceptable.
        assert "{field_path}" in reason, kind

    # AND THE SAME SWEEP OVER WHAT IS ACTUALLY SERVED, on sentences that fire every
    # one of the five kinds, because a digit-free template could still be formatted
    # with one.
    fired: set[str] = set()
    for sentence in (
        "The temperature drift was 3 K.",
        "The temperature was 3 K above target.",
        "The temperature was 300 K, then 350 K, then 400 K.",
        "The temperature was 425 K, ramped at 3 K/min",
        "The temperature was 425 K, maybe 3 K of drift",
        # GATE (4). This row is the one that matters most for the leak check, and
        # not by coincidence: its reason enumerates "a setpoint, a target, ... a
        # maximum, a minimum, an average", so the reason literally NAMES the
        # construction while the sentence supplies the number — which is exactly the
        # shape in which a digit would sit beside the value it withheld.
        "The setpoint temperature was 425 K.",
    ):
        reading = _read(sentence)
        numbers = set(re.findall(r"[0-9]+(?:\.[0-9]+)?", sentence))
        for entry in reading.abstentions:
            fired.add(entry.kind)
            leaked = sorted(n for n in numbers if n in entry.reason)
            assert leaked == [], (sentence, entry.kind, leaked)
    assert fired == set(tc._REFUSAL_REASONS), (
        "this sweep must fire every refusal kind, or it clears kinds it never ran"
    )


def test_every_label_head_matches_at_offset_zero_and_before_the_value():
    """The invariant `_label_bridge` rests on, asserted rather than assumed.

    `_LABEL_HEAD_*` recovers where a rule's LABEL ends inside its own whole match,
    which is what makes the bridge extractable without renumbering a capture group.
    It is a mirror of each pattern's leading alternation, so it can drift from the
    pattern it mirrors — and the drift is silent in the dangerous direction: an
    alternation ordered `start|started` would match three characters of a
    four-character label and leave `ed` in the bridge, which no assertion grammar
    admits, so EVERY instant would quietly stop being read.

    **THE MODULE'S COMMENT CLAIMED THIS TEST EXISTED BEFORE IT DID.** It was written
    as "a test asserts, over every rule and every measured sentence, that the head
    matches at offset 0 and ends at or before the value" — which is the kind of
    claim this file has been caught publishing unchecked. It is now true.

    MUTATION: reordering any `_LABEL_HEAD_*` alternation so a prefix precedes its
    longer form turns this RED; so does pointing a rule at another rule's head.
    """
    sentences = (
        "The temperature was 425 K",
        "temperature 425 K",
        "Sample temperature at the second scan was 425 K",
        "temperatures were 425 K",
        "The scan started 2026-01-01T00:00:00Z",
        "The scan start 2026-01-01T00:00:00Z",
        "The beginning was 2026-01-01T00:00:00Z",
        "The scan began 2026-01-01T00:00:00Z",
        "The scan ended 2026-01-01T00:00:00Z",
        "At the end 2026-01-01T00:00:00Z",
        "The scan finished 2026-01-01T00:00:00Z",
        "The scan stopped 2026-01-01T00:00:00Z",
    )
    checked = 0
    gated = [rule for rule in tc._RULES if rule.label_head is not None]
    assert len(gated) == 3, "the three label-anchored value rules"
    for rule in gated:
        for sentence in sentences:
            for match in rule.pattern.finditer(sentence):
                checked += 1
                whole = match.group(0)
                head = rule.label_head.match(whole)
                assert head is not None, (rule.name, whole)
                # At offset zero: every pattern begins with `\b` + its label.
                assert head.start() == 0, (rule.name, whole)
                # And ending at or before the value, so the bridge slice is valid.
                value_start = match.start(1) - match.start()
                assert head.end() <= value_start, (rule.name, whole, head.group(0))
                # The head is the WHOLE label word, never a prefix of it: the
                # character after it is not a letter.
                rest = whole[head.end() :]
                assert not rest[:1].isalpha(), (
                    f"{rule.name}: `{head.group(0)}` is a PREFIX of the label in "
                    f"`{whole}` -- the alternation is ordered wrong and every "
                    f"reading of this rule would silently stop"
                )
                # And the bridge that comes out of it really does parse, on these
                # deliberately-legitimate sentences.
                assert tc._asserts_the_value(rule, match), (rule.name, whole)
    assert checked >= 12, checked


def test_the_sequence_gate_is_PER_REGION_and_not_per_segment():
    """One sloppy clause must not delete a clean one in the same sentence.

    The claim is written into `_segment_readings` as prose — *"'The temperature was
    425 K and 430 K and the temperature was 500 K' withholds the first clause and
    still reads 500"* — so it is pinned here rather than left as a comment.

    Each label match owns a REGION, and the gate decides over that region alone. A
    segment-wide gate would be simpler and would be wrong: the ambiguity belongs to
    the clause that contains it, and the second clause asserts 500 with its own
    label and its own copula.

    MUTATION: hoisting the `siblings` check out of the region loop to a per-rule or
    per-segment decision turns this RED on the 500.
    """
    sentence = "The temperature was 425 K and 430 K and the temperature was 500 K."
    reading = _read(sentence)
    # `_values` in THIS file takes TEXT (it takes a READING in
    # `test_transcript_capture_multiple_values.py`) -- a trap this test fell into
    # once, with a `TypeError` rather than a wrong answer, which is the good case.
    assert _values(sentence, TEMPERATURE) == [500]
    assert [entry.kind for entry in reading.abstentions] == [
        "several_values_and_none_selected"
    ]
    # NOT a conflict: only one value was read, so there is nothing to choose between.
    assert reading.review_required == ()

    # And a gated match next to an accepted one, in both orders, so neither
    # position is privileged.
    for sentence in (
        "The temperature drift was 3 K and the temperature was 425 K.",
        "The temperature was 425 K and the temperature drift was 3 K.",
    ):
        both = _read(sentence)
        assert _values(sentence, TEMPERATURE) == [425], sentence
        assert "label_does_not_assert_this_value" in [
            entry.kind for entry in both.abstentions
        ], sentence

    # The instant rules likewise: a drift ONSET is refused beside a real start.
    instants = _read(
        "It started drifting at 2026-01-01T00:00:00Z and the scan started "
        "2026-01-02T00:00:00Z."
    )
    assert [
        candidate.proposed_value
        for candidate in instants.candidates
        if candidate.field_path == START
    ] == ["2026-01-02T00:00:00Z"]
    assert "label_does_not_assert_this_value" in [
        entry.kind for entry in instants.abstentions
    ]


#: Natural ways of asserting a temperature, written INDEPENDENTLY of the bridge
#: grammar rather than derived from it — which is the whole point of them.
#:
#: **THE FIRST VERSION OF `_ASSERTION_BRIDGE` REFUSED THIRTEEN OF THESE FIFTEEN,
#: and the adversarial corpus it was developed against reported 1,365 legitimate
#: sentences read and ZERO lost.** That corpus drew its bridges from the same list
#: the grammar was built from, so it measured the grammar's REACH and not its
#: PREMISE. These are here so a future narrowing of the grammar costs a test rather
#: than costing a scientist their reading.
_BENIGN_BRIDGE_FORMS: tuple[str, ...] = (
    "The temperature here was 425 K.",
    "The temperature today was 425 K.",
    "The temperature throughout was 425 K.",
    "The temperature read 425 K.",
    "The temperature showed 425 K.",
    "The temperature registered 425 K.",
    "The temperature came out at 425 K.",
    "The temperature settled at 425 K.",
    "The temperature stayed at 425 K.",
    "The temperature remained at 425 K.",
    "The temperature stabilised around 425 K.",
    "The temperature sat around 425 K.",
    "The sample temperature was 425 K.",
    "The temperature on the sensor was 425 K.",
    "The temperature according to the log was 425 K.",
    "The temperature we recorded was 425 K.",
    "The temperature I measured was 425 K.",
    "The temperature was held at 425 K.",
    "The temperature was set to 425 K.",
    "The temperature reached 425 K.",
)


@pytest.mark.parametrize("sentence", _BENIGN_BRIDGE_FORMS)
def test_a_natural_way_of_asserting_the_field_is_still_READ(sentence):
    """The false-negative side of the gate, measured on an INDEPENDENT list.

    A fail-closed gate is only acceptable if what it closes on is genuinely
    unreadable. Measured on this list, the first version was at **86%** loss — a
    reader that refuses most of the ways a person says a thing is not usable, and
    "every loss is disclosed" is not a defence against that. It is now at one
    (`"The temperature, measured carefully, was 425 K"`, a parenthetical, named as
    residue).

    MUTATION: reverting any of `_ASSERTION_AT_VERB`'s 2026-09-13 additions,
    `_ASSERTION_REPORT_VERB`, `_LABEL_ADVERB` or `_LABEL_CLAUSE` turns rows here
    RED.
    """
    assert _values(sentence) == [425], sentence
    assert _read(sentence).abstentions == (), sentence


def test_widening_the_bridge_did_NOT_reopen_the_nominal_head_class():
    """The structural argument for the widening, asserted rather than reasoned.

    Every verb added to the bridge grammar on 2026-09-13 is safe for ONE reason: a
    NOMINAL HEAD still fails, wherever the verb after it comes from. `drift` is
    neither a modifier preposition nor an assertion, so it cannot reach the value
    however the clause continues. That is the claim, and these are the controls.

    MUTATION: admitting an open `[A-Za-z]+` anywhere in `_LABEL_ADVERB` or
    `_LABEL_MODIFIER` turns every row here RED, which is exactly the failure the
    closed lists exist to prevent.
    """
    for sentence in (
        "The temperature drift read 3 K",
        "The temperature error settled at 2 K",
        "The temperature step showed 5 K",
        "The temperature noise read 0.3 K",
        "The temperature spread registered 4 K",
        "The temperature setpoint came out at 350 K",
        "The temperature tolerance remained at 1 K",
        "The temperature ramp stayed at 5 K",
    ):
        reading = _read(sentence)
        assert reading.candidates == (), sentence
        assert [entry.kind for entry in reading.abstentions] == [
            "label_does_not_assert_this_value"
        ], sentence
    # AND THE THIRTEEN CLOSED ROWS ARE RE-CHECKED HERE TOO, so a widening that
    # reopened one could not hide behind the parametrised test above passing.
    for row in tc._LABEL_OVERREACH_CLOSED:
        assert _rows(row) == [], f"the widening REOPENED {row!r}"


@pytest.mark.parametrize("sentence", tc._PARENTHETICAL_BRIDGE_RESIDUE)
def test_the_PARENTHETICAL_bridge_is_STILL_REFUSED(sentence):
    """The one benign bridge form the gate still costs, asserted so it is visible.

    A parenthetical between the label and its copula. It is a DISCLOSED omission
    rather than a fabrication, so it is a cost and not a §5 defect — but it is a
    cost, and a percentage hides it. Admitting it means admitting arbitrary text
    inside `, … ,`, and *"the temperature, which was a drift of, was 3 K"* is why
    that needs its own allowlist grammar rather than a wildcard.

    Asserted the WRONG WAY ROUND, like the two residue tuples: reading it requires
    DELETING a row here.
    """
    reading = _read(sentence)
    assert reading.candidates == (), (
        "if this now READS, the parenthetical form is handled -- delete the row "
        "from _PARENTHETICAL_BRIDGE_RESIDUE and say so"
    )
    # AND IT IS DISCLOSED, which is the difference between this and the pre-label row.
    assert [entry.kind for entry in reading.abstentions] == [
        "label_does_not_assert_this_value"
    ]


def test_the_two_PHRASE_rules_do_not_share_the_label_overreach_defect():
    """Scope item 8 of the closing brief: the OTHER readable fields, measured.

    `_ATMOSPHERE`/`_ENVIRONMENT` were already fail-closed in the shape
    `_ASSERTION_BRIDGE` gives the other three — `_LABEL_SEPARATOR` requires a
    copula, colon or equals sign IMMEDIATELY after the label, and the phrase is
    anchored to the end of the segment. So they carry no `label_head` and this
    slice changed neither. Asserted rather than asserted-about, because "the other
    rules are fine" is exactly the kind of claim this file has published unchecked.
    """
    for sentence in (
        "The atmosphere change was dry nitrogen",
        "The atmosphere drift was dry nitrogen",
        "The environment control was ambient air",
        "The atmosphere step was argon",
    ):
        assert _read(sentence).candidates == (), sentence
    for sentence, path, value in (
        ("The atmosphere was dry nitrogen", ATMOSPHERE, "dry nitrogen"),
        ("atmosphere: dry nitrogen", ATMOSPHERE, "dry nitrogen"),
        ("The environment was ambient air", ENVIRONMENT, "ambient air"),
    ):
        assert [
            candidate.proposed_value
            for candidate in _read(sentence).candidates
            if candidate.field_path == path
        ] == [value], sentence
    # And they are UNGATED by construction, which is what makes the above a
    # property of those rules rather than a coincidence of these sentences.
    for rule in tc._RULES:
        if rule.field_path in (ATMOSPHERE, ENVIRONMENT):
            assert rule.label_head is None, rule.name
            assert rule.restatement is None, rule.name


@pytest.mark.parametrize("sentence,proposed", tc._PHRASE_BOUNDARY_RESIDUE)
def test_the_PHRASE_BOUNDARY_imperfection_is_STILL_OPEN(sentence, proposed):
    """A DIFFERENT imperfection in the phrase rules, asserted the wrong way round.

    `_LABEL_SEPARATOR` admits `of`, so *"The atmosphere OF THE GLOVEBOX was dry
    nitrogen"* proposes the sentence's whole tail as the atmosphere.

    **It is not the class this slice closes and the difference is the point:** no
    quantity is re-subjected and no number is invented — the value is a VERBATIM
    substring of the scientist's own sentence, shown to them for confirmation — so
    what is wrong is the phrase BOUNDARY, not the claim. A scalar fabrication
    offers a plausible number nobody stated; this offers an obviously-wrong string.

    Pinned so closing it is a reviewed change. `of` is measured UNUSED by every
    phrase bridge in this repository's corpus, so dropping it from
    `_LABEL_SEPARATOR` is a plausible fix — for its own slice, since that constant
    governs two rules this slice deliberately left untouched.
    """
    values = [
        candidate.proposed_value
        for candidate in _read(sentence).candidates
        if candidate.field_path == ATMOSPHERE
    ]
    assert values == [proposed], (
        "if this changed, the phrase-boundary imperfection moved -- update or "
        "delete the row in _PHRASE_BOUNDARY_RESIDUE and say which"
    )


def test_the_gate_ledger_constants_are_not_DEAD():
    """`_GATE_FALSE_NEGATIVES` and the three residue tuples must be reachable.

    This module already carries `_DISCLOSURE_CEILING_GAP`, a prose constant whose
    only protection is a test asserting its content — the pattern exists because a
    documentation constant nothing reads is a claim that can go stale without any
    test noticing. The 2026-09-13 ledger gets the same treatment: the numbers it
    publishes are the ones asserted elsewhere in this file, so they cannot drift
    apart, and each residue tuple has a parametrised test that walks it.

    MUTATION: editing a figure in `_GATE_FALSE_NEGATIVES` without editing the
    corresponding assertion turns this RED.
    """
    ledger = tc._GATE_FALSE_NEGATIVES
    # The two measured rates, as they are published.
    assert "1 of 15" in ledger
    assert "16 of 57" in ledger
    # GATE (4)'s two rates, and the reviewer figure that corrects gate (1)'s.
    assert "2 of 51" in ledger
    assert "20 of 51 (39%)" in ledger
    assert "28% (14 of 50)" in ledger
    assert "13 of 15 before the 2026-09-13 widening" in ledger
    # And the claim that makes the trade §5-acceptable at all.
    assert "Every loss is DISCLOSED" in ledger
    # The 20-form tuple this file walks matches the ledger's own parenthetical.
    assert len(_BENIGN_BRIDGE_FORMS) == 20

    # Each residue tuple is non-empty AND walked by a parametrised test, so none
    # can become a vacuous parameter set -- the exact failure mode
    # `_RESTATEMENT_RESIDUE` was deleted to avoid.
    for name, tup in (
        ("_PRE_LABEL_OVERREACH_CLOSED", tc._PRE_LABEL_OVERREACH_CLOSED),
        ("_RUN_MISATTRIBUTION_CLOSED", tc._RUN_MISATTRIBUTION_CLOSED),
        ("_PRE_LABEL_RESIDUE", tc._PRE_LABEL_RESIDUE),
        ("_MODIFIER_OBJECT_OVERREACH_RESIDUE",
         tc._MODIFIER_OBJECT_OVERREACH_RESIDUE),
        ("_PARENTHETICAL_BRIDGE_RESIDUE", tc._PARENTHETICAL_BRIDGE_RESIDUE),
        ("_PHRASE_BOUNDARY_RESIDUE", tc._PHRASE_BOUNDARY_RESIDUE),
        ("_LABEL_OVERREACH_CLOSED", tc._LABEL_OVERREACH_CLOSED),
        ("_RESTATEMENT_RESIDUE_CLOSED", tc._RESTATEMENT_RESIDUE_CLOSED),
    ):
        assert tup, f"{name} is EMPTY, which makes its parametrised test vacuous"
        assert len(set(tup)) == len(tup), f"{name} has a duplicate row"

    # The three residue tuples are DISJOINT from the closed one: a sentence cannot
    # be both open and closed, and an edit that moved one without removing it from
    # the other would say it is.
    closed = set(tc._LABEL_OVERREACH_CLOSED) | set(tc._RESTATEMENT_RESIDUE_CLOSED)
    open_rows = (
        set(tc._PRE_LABEL_OVERREACH_CLOSED)
        | set(tc._MODIFIER_OBJECT_OVERREACH_RESIDUE)
        | set(tc._PARENTHETICAL_BRIDGE_RESIDUE)
        | {row[0] for row in tc._PHRASE_BOUNDARY_RESIDUE}
    )
    assert not (closed & open_rows)


@pytest.mark.parametrize("sentence", tc._MODIFIER_OBJECT_OVERREACH_RESIDUE)
def test_the_MODIFIER_OBJECT_overreach_is_STILL_OPEN(sentence):
    """A third open sub-class, found by SELF-REVIEW of this slice's own grammar.

    `_LABEL_MODIFIER` admits a preposition + DETERMINER + up to three words,
    because that is what makes `"Sample temperature at the second scan was 425 K"`
    readable. When the modifier's OBJECT is itself a quantity noun the bridge
    parses and the value is read, silently.

    **The BARE forms are all closed** (`"The temperature drift was 3 K"` is
    refused), so what is open is specifically the determiner-led genitive — and
    telling `"of the SAMPLE"` from `"of the DRIFT"` needs a lexicon of which nouns
    name a thing that HAS a temperature versus a quantity DERIVED from one. That is
    the same wall as `per the log` versus `per minute`.

    Asserted the WRONG WAY ROUND, so closing it requires deleting a row.

    **Recorded because a slice that finds a hole in its own fix and does not pin it
    has published a stronger result than it measured** — which is the defect class
    this whole file exists to document.
    """
    rows = _rows(sentence)
    assert len(rows) == 1, (
        "if this reads nothing the MODIFIER-OBJECT sub-class is CLOSED -- delete "
        "the row from _MODIFIER_OBJECT_OVERREACH_RESIDUE and say so"
    )
    assert rows[0][1] is False, "pass ONE"
    assert _read(sentence).abstentions == (), "and it is SILENT, which is the defect"


def test_the_BARE_forms_of_the_modifier_object_class_ARE_closed():
    """The boundary of the sub-class above, so it is not read as wider than it is.

    Remove the determiner and every one of them is refused. That is what makes the
    open rows a determiner-led GENITIVE problem rather than "the gate does not
    handle quantity nouns".
    """
    for sentence in (
        "The temperature drift was 3 K",
        "The temperature error was 2 K",
        "The temperature ramp was 5 K",
        "The temperature tolerance was 1 K",
        "The temperature of drift was 3 K",
        "The temperature for tolerance was 1 K",
    ):
        reading = _read(sentence)
        assert reading.candidates == (), sentence
        assert reading.abstentions, f"{sentence!r} must at least DISCLOSE"

"""GATE (4) — THE PRE-LABEL GATE — measured as a CLASS rather than as a table.

**WHY THIS FILE IS GENERATIVE AND NOT A LIST OF ROWS.** The §5 label-overreach class
has now been closed in three passes, and each of the first two published a table of
the entrances it knew about. The module's own record of what that cost is the reason
for this file's shape:

* pass one closed thirteen rows, and *"an independent review hunted this class from
  scratch on the same day and produced **twenty** members, not one of which appears
  in the thirteen rows"*;
* the adversarial generator pass one was developed against *"crossed 43 nominal heads
  and 20 verbs of change against the label; it produced **not one** of the review's
  twenty rows verbatim"*, because *"its change-verb table held ``raised by``,
  ``lowered by``, ``dropped by`` and seventeen more — **every one with a
  preposition**"*;
* and the module's verdict on that: *"a corpus generated from the same mental model
  as the fix tests the fix's reach and not its premise."*

So a fixed table is not evidence that a class is closed — it is evidence about the
rows in the table. This file composes {modifier} × {label} × {value} × {clause shape}
and asserts the INVARIANT over the product, which is the only thing that can fail on
a sentence nobody thought of.

**AND IT IS AN ORACLE, NOT A SAMPLE, which is the assertion that makes a clean sweep
mean something.** Every family below declares the verdict its rows must receive, and
a refusal family requires the refusal to be **DISCLOSED** — so a row that quietly
matches nothing at all FAILS here rather than reading as a pass. That is the specific
way a generated sweep lies: 1,645 rows each reading nothing produce a perfect score.

**THE SEED IS FIXED AND EVERY FAILURE PRINTS ITS GENERATED INPUT.** A property test
whose counterexample cannot be reproduced is a flake, and one whose message does not
name the sentence costs a session.

**WHAT IT DOES NOT COVER, stated so its count is not read as more than it is:** it
produces single-segment English sentences over the two numeric/instant label
families. It does NOT produce multi-sentence transcripts, run references, the two
free-phrase rules (`_ATMOSPHERE`/`_ENVIRONMENT`, which carry no `label_head` and are
ungated by construction), non-English, or unicode digit forms.
"""

from __future__ import annotations

import itertools
import random

import pytest

import isaac_api.transcript_capture as tc

#: Deterministic. Every sampled family draws from this and nothing else, so a
#: counterexample reported by CI reproduces byte-for-byte on a laptop.
SEED = 20260913

RUN = tc.RunRef(id="run-1", label="Run 1", ordinal=1)
TEMPERATURE = "context.temperature_K"
START = "timestamps.acquired_start_utc"
END = "timestamps.acquired_end_utc"
INSTANT = "2026-01-01T00:00:00Z"


def _read(text: str) -> tc.TranscriptReading:
    return tc.read_transcript(text, selected_run="run-1", known_runs=(RUN,))


def _values(text: str) -> list:
    return [candidate.proposed_value for candidate in _read(text).candidates]


def _explain(text: str) -> str:
    """The failure message. It prints the GENERATED INPUT and what the reader did."""
    reading = _read(text)
    return (
        f"\n  generated input: {text!r}"
        f"\n  candidates:      "
        f"{[(c.field_path, c.proposed_value) for c in reading.candidates]}"
        f"\n  abstentions:     {[a.kind for a in reading.abstentions]}"
        f"\n  clarifications:  {[c.kind for c in reading.clarifications]}"
        f"\n  seed:            {SEED}"
    )


# --- the families, each with the verdict its rows must receive -----------------

#: **THE PRE-LABEL MODIFIER FAMILY.** A noun or adjective between the determiner and
#: the label. Grammatically the label is still the compound's HEAD — *"setpoint
#: temperature"* IS a kind of temperature, unlike *"temperature setpoint"* — so no
#: shape test separates these from the locators below and the lexicon decides.
#:
#: **THE SCHEMA, NOT A SCIENTIFIC JUDGEMENT, IS WHY THE FIRST GROUP IS REFUSED.**
#: The official schema gives an as-commanded value its OWN path wherever it speaks
#: about the distinction at all (`context.electrochemistry.potential_setpoint_V`,
#: *"PRIMARY, immutable: the as-commanded potential"*, and `current_setpoint_mA_cm2`)
#: and `context.temperature_K` has **no setpoint sibling** — so a stated setpoint
#: temperature has no path here. `maximum`/`average` name a reduction over
#: temperatures, for which the schema likewise carries no path.
#:
#: **AND FOR `ambient`/`room` THE REFUSAL IS AN ABSTENTION, NOT A RULING.** This
#: reader is NOT deciding that an ambient temperature is not the field's value; §5
#: forbids that judgement just as surely as it forbids the opposite one. It is
#: declining to decide, and the served reason says so.
RESUBJECTING_MODIFIERS = (
    # as-commanded
    "setpoint", "set-point", "target", "requested", "planned", "commanded",
    "demanded", "intended", "desired", "programmed",
    # reductions over temperatures
    "maximum", "minimum", "peak", "average", "mean", "median", "highest",
    "lowest", "upper", "lower",
    # an estimate rather than a reading
    "nominal", "expected", "estimated", "predicted", "projected", "typical",
    "approximate", "assumed",
    # a different body or a different moment
    "ambient", "room", "baseline", "base", "initial", "final", "starting",
    "ending", "outer", "external",
)

#: **THE LOCATOR FAMILY — the false-negative side, and the one to guard hardest.**
#: A gate that traded a fabrication class for a silent-loss class would make the
#: product worse. `sample` is pinned as a must-read by `_BENIGN_BRIDGE_FORMS`, and is
#: the schema's own word for the measured thing.
#:
#: **`run` IS IN `tc._PRE_LABEL_NOUN` AND IS DELIBERATELY ABSENT FROM EVERY CORPUS IN
#: THIS FILE, and the reason is a measured interaction rather than a doubt about the
#: gate.** `tc._RUN_REFERENCE` is `\brun\s+(?:number\s+|#\s*)?(<token>)`, so the
#: words `"run temperature"` parse as a reference to a run NAMED "temperature", and
#: `"the second run"` matches `tc._VAGUE_RUN`. Either raises a clarification, which
#: leaves the run target unsettled, which withholds every candidate in the transcript
#: — **before gate (4) is consulted at all.** A row like `"The previous run ended at
#: <instant>"` therefore reads nothing for a reason that has nothing to do with this
#: slice, and including it would let the run-reference rule clear a family that exists
#: to test the pre-label gate. It is pinned on its own instead, in
#: `test_the_RUN_REFERENCE_rule_PRE_EMPTS_this_gate_and_that_is_PRE_EXISTING`.
LOCATING_MODIFIERS = (
    "sample", "specimen", "scan", "measurement", "acquisition",
    "collection", "dataset", "exposure", "spectrum",
)

#: **THE RUN-MISATTRIBUTION FAMILY**, on the instant rules. Worse than reading the
#: wrong quantity: the value is a real acquisition time, correctly parsed, of a
#: DIFFERENT measurement, attributed to this one.
OTHER_SCAN_MODIFIERS = (
    "previous", "last", "first", "second", "third", "earlier", "prior",
    "preceding", "calibration", "dark", "reference", "blank", "background",
    "test", "practice", "aborted", "failed", "next", "following", "upcoming",
)

#: **THE NOMINAL-HEAD FAMILY**, closed by gate (1) and generated here anyway — a
#: fourth gate must not reopen the third's class, and that is measurable rather than
#: arguable.
RESUBJECTING_HEADS = (
    "drift", "error", "offset", "difference", "delta", "step", "resolution",
    "tolerance", "uncertainty", "gradient", "stability", "spread", "noise",
    "range", "ramp", "scatter", "fluctuation", "variation", "jitter",
    "deviation", "correction", "rise", "fall", "increase", "decrease",
    "excursion", "overshoot", "undershoot", "margin", "budget", "window",
)

#: **THE TAIL FAMILY**, closed by gate (2). Every one of these makes the number
#: measure a relation, a rate or a bound.
QUALIFYING_TAILS = (
    "above target", "below target", "above the setpoint", "below the setpoint",
    "hotter than before", "colder than before", "hotter than at the start",
    "colder than the last scan", "per minute", "per step", "per hour",
    "of drift", "of scatter", "of error", "of spread", "of uncertainty",
    "at most", "at least", "either way", "peak to peak", "RMS",
    "from the setpoint", "off target", "over ambient", "under ambient",
)

#: Bridges that ASSERT the value as the field's. Every row built with one of these
#: and a clean pre-label context MUST read.
ASSERTING_BRIDGES = (
    "was", "is", "was around", "was about", "was roughly", "read", "showed",
    "registered", "reached", "came out at", "settled at", "stayed at",
    "remained at", "was held at", "was set to", "sat around", "was measured at",
    "logged", "indicated", "hit",
)

#: Bridges that do NOT assert it. Refused by gate (1), generated so the fourth gate
#: cannot be shown to have taken over the third's job.
NON_ASSERTING_BRIDGES = (
    "rose by", "fell by", "dropped by", "increased by", "decreased by",
    "was stable to", "was accurate to", "drifted by", "varied by",
    "ramped to", "went to", "climbed to", "was within", "differed by",
)


def _pytest_ids(prefix: str, rows):
    return [f"{prefix}-{index}" for index, _ in enumerate(rows)]


# --- NEGATIVE DIRECTION: nothing sharing the unit is promoted ------------------


def _resubjecting_prelabel_rows() -> list[str]:
    """{determiner} × {re-subjecting modifier} × {asserting bridge} × {value}.

    The bridge is deliberately drawn from the ASSERTING set: the whole point of this
    family is that everything gate (1) inspects is correct and correctly admitted,
    and the disqualifying word is upstream of everything it looks at.
    """
    rng = random.Random(SEED)
    rows = []
    for modifier in RESUBJECTING_MODIFIERS:
        for determiner in ("The", "the", "Our", "This", "That", "Each"):
            bridge = rng.choice(ASSERTING_BRIDGES)
            value = rng.choice((295, 300, 400, 425, 500, 77.4))
            rows.append(f"{determiner} {modifier} temperature {bridge} {value} K.")
    return rows


def _other_scan_rows() -> list[str]:
    rng = random.Random(SEED + 1)
    rows = []
    for modifier in OTHER_SCAN_MODIFIERS:
        # `run` is excluded — see `LOCATING_MODIFIERS`. `tc._RUN_REFERENCE` would
        # pre-empt the gate under test.
        for noun in ("scan", "measurement", "acquisition", "exposure"):
            verb = rng.choice(("ended at", "finished at", "started at", "began at"))
            rows.append(f"The {modifier} {noun} {verb} {INSTANT}.")
            rows.append(f"The {modifier} {noun} temperature was 425 K.")
    return rows


def _change_verb_rows() -> list[str]:
    """The BARE form — no preposition — which is the single entrance the previous
    generator could not produce and the single row it therefore left open.

    Generated WITHOUT `by` on purpose. The prepositional forms are covered by
    `_non_asserting_bridge_rows` below, and pairing them here is exactly the mistake
    the module records: *"a generator that only ever puts the re-subjecting word
    where the bridge can see it cannot discover that the bridge has a blind side."*

    ── `took` WAS IN THIS LIST AND THE ORACLE, NOT THE GATE, WAS WRONG ──────────

    **This generator's first run reported three failures and all three were its own
    fault, which is the most useful thing it did.** It listed `took` as a verb of
    change ("took the temperature down 15 K") while `tc._PRE_LABEL_REPORT` lists it
    as a verb of report ("took the temperature" = measured it). Both readings of the
    word exist, so the oracle and the gate disagreed and neither was obviously right.

    **Measured, and that settles it: the CHANGE reading of `took` requires a
    PARTICLE, and every particle form is already refused by gate (1)** —
    `"We took the temperature DOWN 15 K"`, `"UP 15 K"`, `"DOWN BY 15 K"` and
    `"OFF 15 K"` all yield `label_does_not_assert_this_value`, because `down`/`up`/
    `off` are not in any assertion grammar. So the bare form `"We took the
    temperature 15 K"` genuinely IS the report reading, it is read, and it should be.
    `took` is removed from the ORACLE and kept in the gate, and
    `_change_verb_particle_rows` below now pins the measurement that decided it — so
    the disagreement is resolved by evidence in the tree rather than by whoever edits
    this file next.

    **The transferable part: when a generated corpus fails, the corpus is a suspect
    too.** Twelve of the other nineteen verbs here are not report verbs in ANY
    reading and refuse on the bare form, which is what makes this family worth
    keeping rather than deleting.
    """
    rows = []
    for verb in (
        "lowered", "raised", "dropped", "lifted", "cut", "bumped", "nudged",
        "pushed", "pulled", "moved", "shifted", "brought", "corrected",
        "trimmed", "backed", "wound", "stepped", "ramped", "swung",
    ):
        for subject in ("We", "I", "They"):
            rows.append(f"{subject} {verb} the temperature 15 K.")
    return rows


def _change_verb_particle_rows() -> list[str]:
    """The PARTICLE forms — the measurement that resolved the oracle disagreement
    above, committed so it cannot be re-litigated from memory.

    Every one of these is a genuine delta and every one is refused by gate (1),
    because a particle is not an assertion. This is the family that makes it safe for
    `tc._PRE_LABEL_REPORT` to keep `took`, `read`, `found` and the rest: whatever the
    pre-label verb, a direction word between the label and the value refuses.
    """
    rows = []
    for verb in ("took", "brought", "wound", "backed", "nudged", "moved", "read"):
        for particle in ("down", "up", "off", "back", "down by", "up by"):
            rows.append(f"We {verb} the temperature {particle} 15 K.")
    return rows


def _nominal_head_rows() -> list[str]:
    rng = random.Random(SEED + 2)
    rows = []
    for head in RESUBJECTING_HEADS:
        bridge = rng.choice(ASSERTING_BRIDGES)
        rows.append(f"The temperature {head} {bridge} 3 K.")
        rows.append(f"temperature {head} 3 K")
    return rows


def _qualifying_tail_rows() -> list[str]:
    rng = random.Random(SEED + 3)
    rows = []
    for tail in QUALIFYING_TAILS:
        bridge = rng.choice(ASSERTING_BRIDGES)
        rows.append(f"The temperature {bridge} 3 K {tail}.")
    return rows


def _non_asserting_bridge_rows() -> list[str]:
    rows = []
    for bridge in NON_ASSERTING_BRIDGES:
        rows.append(f"The temperature {bridge} 30 K.")
        rows.append(f"The sample temperature {bridge} 30 K.")
    return rows


def _two_kelvin_quantities_rows() -> list[str]:
    """**TWO OR MORE QUANTITIES SHARING KELVIN IN ONE CLAUSE**, which is the shape
    where a reader is likeliest to pick the wrong one and call it the field.

    Each row states a real temperature AND a second kelvin-valued quantity that is
    not one. The invariant asserted is the strong one: whatever is read, the
    NON-temperature number is never among the proposed values.
    """
    rows = []
    for other in (
        "3 K of drift", "3 K above target", "2 K of scatter", "1 K of error",
        "5 K per minute", "0.5 K resolution", "2 K tolerance",
        "4 K peak to peak", "3 K/min", "1 K per step", "2 K uncertainty",
        "6 K colder than before",
    ):
        rows.append(f"The temperature was 425 K with {other}.")
        rows.append(f"The temperature was 425 K, {other}.")
        rows.append(f"The temperature was 425 K and {other}.")
    return rows


NEGATIVE_FAMILIES: dict[str, list[str]] = {
    "prelabel-modifier": _resubjecting_prelabel_rows(),
    "other-scan": _other_scan_rows(),
    "change-verb-bare": _change_verb_rows(),
    "change-verb-particle": _change_verb_particle_rows(),
    "nominal-head": _nominal_head_rows(),
    "qualifying-tail": _qualifying_tail_rows(),
    "non-asserting-bridge": _non_asserting_bridge_rows(),
}

_NEGATIVE_ROWS = [
    (family, row) for family, rows in NEGATIVE_FAMILIES.items() for row in rows
]


@pytest.mark.parametrize(
    "family,sentence",
    _NEGATIVE_ROWS,
    ids=[f"{family}-{index}" for index, (family, _) in enumerate(_NEGATIVE_ROWS)],
)
def test_a_quantity_that_merely_SHARES_the_unit_is_never_promoted(family, sentence):
    """THE NEGATIVE DIRECTION. Nothing here is asserted as the field's value, so
    nothing may be proposed — AND the refusal must be DISCLOSED.

    **THE SECOND ASSERTION IS WHAT MAKES THE FIRST MEAN ANYTHING.** A row that
    matched no pattern at all would satisfy `candidates == ()` while measuring
    nothing, which is precisely how a large generated corpus produces a perfect
    score without exercising the gate. Requiring a disclosure requires the DETECTOR
    to have fired and a gate to have refused it, which is the behaviour under test.

    MUTATION: removing `_label_is_the_subject` from the reading loop turns the
    `prelabel-modifier`, `other-scan` and `change-verb-bare` families RED on the
    candidates assertion; removing `_asserts_the_value` turns `nominal-head` and
    `non-asserting-bridge` RED; removing `_continuation_is_clean` turns
    `qualifying-tail` RED. So the three gates are independently load-bearing here.
    """
    reading = _read(sentence)
    assert reading.candidates == (), _explain(sentence)
    assert reading.abstentions != (), (
        "SILENT refusal — §5 ranks a disclosed omission above a silent one, and a "
        "row that discloses nothing may simply have matched nothing, which would "
        "make this whole sweep vacuous." + _explain(sentence)
    )


@pytest.mark.parametrize("sentence", _two_kelvin_quantities_rows())
def test_the_OTHER_kelvin_quantity_in_the_clause_is_never_the_value(sentence):
    """Two kelvin-valued quantities in one clause. Whatever is read, the one that is
    NOT a temperature must not be among the proposed values.

    Asserted this way rather than as a fixed expected list on purpose: the point is
    not which of these clause shapes survives gate (2) — that is gate (2)'s own
    business and is pinned elsewhere — but that the reader never mistakes the drift,
    the rate or the offset for the field.

    MUTATION: admitting `of`, `per`, `above` or `than` to `_CONTINUATION_WORD` turns
    rows here RED, which is the measured reason those tokens are absent.
    """
    values = _values(sentence)
    assert values in ([], [425]), _explain(sentence)


# --- POSITIVE DIRECTION: a real temperature is still detected -----------------


def _positive_rows() -> list[str]:
    """{pre-label shape} × {asserting bridge}, over both label families.

    **THIS IS THE RISK TO GUARD HARDEST.** A fix that silently stopped reading real
    temperatures would have traded a fabrication class for a silent-loss class and
    made the product worse — and the loss would be invisible, because a reading that
    never happens produces no signal at all.
    """
    rng = random.Random(SEED + 4)
    rows = []
    prelabels = (
        # `run` is absent from `LOCATING_MODIFIERS` for the run-reference reason
        # recorded there, so no `The run …` row is generated here either.
        "", "The ", "the ", "Our ", "This ",
        *(f"The {word} " for word in LOCATING_MODIFIERS),
        *(f"{word.capitalize()} " for word in LOCATING_MODIFIERS),
        "Later the ", "Initially the ", "Overnight the ", "Today the ",
        "Here the ", "Throughout the ", "Again the ", "Now the ",
        "At the second scan the ", "In the cryostat the ", "On the stage the ",
        "During the run the ", "At 300 K the ", "We recorded the ",
        "I measured the ", "We logged the ", "They observed the ",
    )
    for prelabel in prelabels:
        for bridge in ASSERTING_BRIDGES:
            value = rng.choice((77.4, 295, 300, 425, 500))
            rows.append(f"{prelabel}temperature {bridge} {value} K.")
    return rows


_POSITIVE_ROWS = _positive_rows()


@pytest.mark.parametrize("sentence", _POSITIVE_ROWS)
def test_a_legitimate_temperature_assertion_is_STILL_READ(sentence):
    """THE POSITIVE DIRECTION, and the direction a fail-closed gate is most likely to
    break. One candidate, the stated value, and NO abstention — a reading that fires
    a disclosure beside it is a half-refusal and is not what these sentences deserve.

    MUTATION: dropping `sample` (or any row of `_PRE_LABEL_NOUN`) turns the locator
    rows RED; dropping `_PRE_LABEL_ADVERB` turns `Later the …` RED; dropping
    `_PRE_LABEL_PREP_PHRASE` turns `At 300 K the …` and `At the second scan the …`
    RED; dropping `_PRE_LABEL_SUBJECT`/`_PRE_LABEL_REPORT` turns `We recorded the …`
    RED; and dropping the optional `{_DETERMINER}` turns every `The …` row RED.
    """
    reading = _read(sentence)
    assert [candidate.field_path for candidate in reading.candidates] == [
        TEMPERATURE
    ], _explain(sentence)
    assert reading.abstentions == (), _explain(sentence)


def _positive_instant_rows() -> list[str]:
    rows = []
    for prelabel in (
        # `The run ` is excluded for the `tc._RUN_REFERENCE` reason recorded on
        # `LOCATING_MODIFIERS`, NOT because gate (4) refuses it: measured,
        # `"The run stopped at <instant>"` yields `unknown_run_reference` and
        # withholds every candidate, at `d3473414` and here alike.
        "", "The ", "It ", "We ", "The scan ",
        "The measurement ", "The acquisition ", "The exposure ",
        "Later the scan ", "Initially the measurement ",
    ):
        for verb, field in (
            ("started at", START), ("started", START), ("began at", START),
            ("ended at", END), ("finished at", END), ("stopped at", END),
        ):
            rows.append((f"{prelabel}{verb} {INSTANT}.", field))
    return rows


@pytest.mark.parametrize("sentence,field", _positive_instant_rows())
def test_a_legitimate_instant_assertion_is_STILL_READ(sentence, field):
    """The same, for the two instant rules — the family the run-misattribution fix
    touches, so its positive control has to be separate and explicit.

    MUTATION: removing `scan`/`run` from `_PRE_LABEL_NOUN` turns the `The scan …`
    rows RED, which is what proves the gate refuses `The PREVIOUS scan …` by the
    modifier and not by the noun.
    """
    reading = _read(sentence)
    assert [candidate.field_path for candidate in reading.candidates] == [
        field
    ], _explain(sentence)
    assert reading.abstentions == (), _explain(sentence)


# --- AMBIGUITY DIRECTION: genuine alternatives stay visible -------------------


def _ambiguity_rows() -> list[str]:
    """**THE CONNECTIVES ARE DERIVED FROM THE MODULE'S OWN TUPLES, NOT TRANSCRIBED.**

    The first version of this generator hardcoded nine connectives and four of them
    were wrong: `possibly`, `about`, `around` and `roughly` are `_OR_REQUIRED_HEDGES`
    members, which pass two reads ONLY behind an explicit `or` — measured, documented
    and deliberate in `_OR_REQUIRED_HEDGES`' own comment. A hardcoded list asserted
    the opposite and produced four failures that looked like gate (4) collapsing an
    ambiguity and were nothing of the kind.

    Deriving both groups from `tc._BARE_HEDGES` and `tc._OR_REQUIRED_HEDGES` means
    this corpus cannot drift from the behaviour it asserts, and means a future
    widening of either tuple is exercised here for free.
    """
    rows = []
    connectives = [
        *tc._BARE_HEDGES,
        *(f"{tc._BARE_OR} {hedge}" for hedge in tc._OR_REQUIRED_HEDGES),
    ]
    for connective in connectives:
        for prelabel in ("The ", "The sample ", "", "Sample "):
            rows.append(
                f"{prelabel}temperature was around 425 K, {connective} 430 K."
            )
    return rows


@pytest.mark.parametrize("sentence", _ambiguity_rows())
def test_a_genuine_ALTERNATIVE_keeps_BOTH_candidates(sentence):
    """THE AMBIGUITY DIRECTION. Ambiguity must stay VISIBLE: both values survive and
    neither is chosen.

    **A GATE THAT RESOLVED THIS WOULD BE A WORSE DEFECT THAN THE ONE IT CLOSED**, and
    it is the failure most easily mistaken for an improvement — one candidate looks
    tidier than two. `CAP-001` exists because `finditer` alone left the second value
    unread, and this asserts gate (4) did not undo it. Note the `The sample …` rows:
    they pass through the new gate's locator branch on the way to pass two, so the
    two mechanisms are exercised together rather than separately.

    MUTATION: making `_PRE_LABEL` reject the locator branch turns the `The sample …`
    rows RED at ZERO candidates; anything that collapses the pair turns every row RED
    at ONE.
    """
    assert _values(sentence) == [425, 430], _explain(sentence)
    assert [entry.kind for entry in _read(sentence).review_required] == [
        "conflicting_values_for_one_field"
    ], _explain(sentence)


# --- the corpus's own honesty --------------------------------------------------


def test_the_generated_corpus_is_an_ORACLE_and_not_a_SAMPLE():
    """The assertion that makes every count above mean something.

    **A GENERATED SWEEP LIES IN ONE SPECIFIC WAY: rows that read nothing at all
    produce a perfect negative score.** The module records this as the reason its
    1,645-row corpus is described as an oracle. So this test pins the three
    properties a bare count cannot carry:

    1. every declared family is NON-EMPTY, so no parametrised set is vacuous;
    2. the families are DISJOINT as sentence sets, so no row is double-counted into
       two verdicts;
    3. the positive corpus actually READS — measured here, not assumed — which is
       what stops "all negatives refuse" from being satisfiable by a gate that
       refuses everything.

    MUTATION: emptying any family turns (1) RED; making `_PRE_LABEL` refuse
    everything turns (3) RED while leaving every negative assertion in this file
    GREEN, which is exactly the blind spot (3) exists to cover.
    """
    families = dict(NEGATIVE_FAMILIES)
    families["two-kelvin"] = _two_kelvin_quantities_rows()
    families["positive"] = _POSITIVE_ROWS
    families["positive-instant"] = [row for row, _ in _positive_instant_rows()]
    families["ambiguity"] = _ambiguity_rows()

    for name, rows in families.items():
        assert rows, f"family {name!r} is EMPTY, which makes its sweep vacuous"

    for left, right in itertools.combinations(families, 2):
        overlap = set(families[left]) & set(families[right])
        assert overlap == set(), (left, right, sorted(overlap)[:3])

    # (3) The positive corpus reads. A gate that refused everything would pass every
    # negative assertion in this file and fail here.
    read = sum(1 for row in _POSITIVE_ROWS if _values(row))
    assert read == len(_POSITIVE_ROWS), (
        f"{len(_POSITIVE_ROWS) - read} of {len(_POSITIVE_ROWS)} positive rows "
        "read NOTHING — the gate has traded a fabrication class for a silent-loss "
        "class"
    )

    # And the corpus is big enough to have a chance of surprising its author, which
    # is the only reason to generate one. Stated as a floor, not as a headline: the
    # number proves nothing on its own and is here so a future edit that guts the
    # generator fails rather than quietly shrinking the sweep.
    total = sum(len(rows) for rows in families.values())
    assert total >= 700, total


def test_the_pre_label_gate_is_FAIL_CLOSED_and_that_is_asserted_not_argued():
    """An unanticipated word before the label costs a READING, never a fabrication.

    This is the whole argument for inverting the polarity of the proxy three
    referrals rejected, and it is checkable rather than rhetorical: feed the gate
    words that appear in NO list in the module and assert the outcome is a disclosed
    refusal in every case.

    MUTATION: replacing `_PRE_LABEL_NOUN` with an open `[A-Za-z]+` turns this RED on
    every row — which is the failure `_LABEL_ADVERB`'s own comment predicts for an
    open pattern in a pre-value slot.
    """
    for invented in ("zorblatt", "quuxified", "frobnicated", "widgety", "blorp"):
        for sentence in (
            f"The {invented} temperature was 425 K.",
            f"The {invented} scan ended at {INSTANT}.",
            f"We {invented} the temperature 15 K.",
        ):
            reading = _read(sentence)
            assert reading.candidates == (), _explain(sentence)
            assert reading.abstentions != (), _explain(sentence)


def test_the_RUN_REFERENCE_rule_PRE_EMPTS_this_gate_and_that_is_PRE_EXISTING():
    """**RESIDUE FOUND BY THIS SLICE'S OWN GENERATOR, MEASURED, AND DELIBERATELY NOT
    FIXED.** It is pinned rather than described because a run-reference interaction
    that nobody has written down is one a future slice will rediscover as a gate
    defect — which is exactly how it presented here.

    `tc._RUN_REFERENCE` is `\\brun\\s+(?:number\\s+|#\\s*)?(<token>)` and
    `tc._VAGUE_RUN` matches `the second run` and friends. Either raises a
    clarification; a clarification leaves the run target unsettled; and an unsettled
    target withholds every candidate in the transcript **and every abstention with
    them**. So:

    * `"The run temperature was 425 K"` reads NOTHING — the words `run temperature`
      parse as a reference to a run NAMED "temperature";
    * `"The run stopped at <instant>"` reads NOTHING, for the same reason;
    * `"The second run ended at <instant>"` reads nothing via `_VAGUE_RUN`.

    **IT IS NOT A §5 FABRICATION AND IS THEREFORE OUT OF THIS SLICE'S SCOPE.** Every
    case is a DISCLOSED withholding with an answerable question attached, which is the
    direction §5 asks for; what is lost is a reading, and the loss is visible. It is
    also PRE-EXISTING: `run` reached `_PRE_LABEL_NOUN` in this slice, but the
    pre-emption is entirely the run-reference rule's and reproduces at `d3473414`
    without gate (4) existing.

    **WHY IT MATTERS ANYWAY:** `run` sits in `tc._PRE_LABEL_NOUN` and can never be
    exercised there through `read_transcript`, so that one entry is effectively
    unreachable at this level. It is kept, and asserted reachable at the GATE level
    below, so the constant is not carrying a dead member unknowingly.

    MUTATION: this test is a pin on behaviour this slice did not change; removing
    gate (4) entirely leaves it GREEN, which is the point — it isolates what is NOT
    this gate's doing.
    """
    for sentence in (
        "The run temperature was 425 K.",
        "The run stopped at 2026-01-01T00:00:00Z.",
        "The second run ended at 2026-01-01T00:00:00Z.",
        "The previous run began at 2026-01-01T00:00:00Z.",
    ):
        reading = _read(sentence)
        assert reading.candidates == (), _explain(sentence)
        assert reading.clarifications != (), (
            "the withholding here must be a DISCLOSED run question, not silence"
            + _explain(sentence)
        )
        # And it is the run machinery, not gate (4): no gate abstention is raised,
        # because an unsettled target withholds those too.
        assert reading.abstentions == (), _explain(sentence)

    # `run` IS reachable at the gate itself, so the tuple holds no dead member.
    assert tc._PRE_LABEL.fullmatch("The run ") is not None
    assert tc._PRE_LABEL.fullmatch("The previous run ") is None


def test_a_bad_pre_label_context_cannot_escape_through_the_RESTATEMENT_pass():
    """Pass two reads a bare kelvin value only AFTER the label-anchored rule matched
    in the same segment. If gate (4) refused the only label match, there is nothing
    for a restatement to restate — and that has to be measured, because pass two's
    own pattern is `<number> K` and would match happily on its own.

    MUTATION: moving the `_label_is_the_subject` check below the `labelled` list
    construction turns this RED at two candidates.
    """
    for sentence in (
        "The setpoint temperature was around 425 K, maybe 430 K.",
        "The previous scan ended at 2026-01-01T00:00:00Z, or 2026-01-02T00:00:00Z.",
        "We lowered the temperature 15 K, maybe 20 K.",
    ):
        reading = _read(sentence)
        assert reading.candidates == (), _explain(sentence)
        assert reading.abstentions != (), _explain(sentence)


# --- the FALSE-NEGATIVE side, which is where a fail-closed gate does its damage ---

#: Natural ways a scientist puts words in FRONT of the label, written **without
#: consulting the grammar while writing them** and BEFORE `tc._PRE_LABEL_NOUN` was
#: widened to its three groups.
#:
#: **THE INDEPENDENCE OF THIS LIST IS LIMITED AND THE LIMIT IS THE POINT.** The
#: module records that gate (1)'s `86% -> 7%` widening was re-measured against *"an
#: independently-written list of fifteen forms"* which was **written by the same
#: author as the grammar**, and that an independent reviewer then measured the true
#: rate at ~3x the published one. This list has the same weakness: one author, who
#: also wrote gate (4). It is therefore **a FLOOR on the loss rate, never an estimate
#: of it** — and it is quoted in `tc._GATE_FALSE_NEGATIVES` beside two figures that
#: genuinely are independent of this slice (`_BENIGN_BRIDGE_FORMS`, written for gate
#: (1) by an earlier slice; and this repository's own 232 pre-existing sentences).
#:
#: Measured on it: **20 of 51 lost (39%)** by the first version of the gate, **2 of 51
#: (4%)** after the widening the 41% forced. Both numbers are in the ledger so neither
#: reads as the other.
BENIGN_PRE_LABEL: tuple[str, ...] = (
    # nothing, or a bare determiner
    "The temperature was 425 K.",
    "Temperature 425 K.",
    "Our temperature was 425 K.",
    # the measured thing
    "The sample temperature was 425 K.",
    "Sample temperature 425 K.",
    "The specimen temperature was 425 K.",
    # the apparatus -- the group whose exclusion was measured INCONSISTENT with the
    # prepositional forms the module already reads
    "The cryostat temperature was 80 K.",
    "The stage temperature was 300 K.",
    "The cell temperature was 350 K.",
    "The chamber temperature was 300 K.",
    "The holder temperature was 300 K.",
    "The substrate temperature was 700 K.",
    "The furnace temperature was 900 K.",
    "The bath temperature was 77 K.",
    "The sensor temperature was 300 K.",
    "The thermocouple temperature was 300 K.",
    # clause-opening adverbials
    "Later the temperature was 320 K.",
    "Initially the temperature was 300 K.",
    "Overnight the temperature was 300 K.",
    "Throughout the temperature was 425 K.",
    "Here the temperature was 425 K.",
    "Anyway the temperature was 425 K.",
    "OK the temperature was 425 K.",
    "Right, the temperature was 425 K.",
    "So the temperature was 425 K.",
    "Then the temperature was 425 K.",
    # opening prepositional phrases
    "At the second scan the temperature was 425 K.",
    "During the run the temperature was 425 K.",
    "In the cryostat the temperature was 80 K.",
    "For this scan the temperature was 425 K.",
    "On the second scan the temperature was 425 K.",
    "After the anneal the temperature was 425 K.",
    # subject + report verb
    "We recorded the temperature at 425 K.",
    "I measured the temperature at 425 K.",
    "They logged the temperature at 425 K.",
    "We saw the temperature at 425 K.",
    # participial pre-modifiers -- HOW the value was obtained
    "The measured temperature was 425 K.",
    "The recorded temperature was 425 K.",
    "The observed temperature was 425 K.",
    "The reported temperature was 425 K.",
    "The logged temperature was 425 K.",
    # affirming adjectives -- the antonyms of the estimate family
    "The actual temperature was 425 K.",
    "The real temperature was 425 K.",
    "The true temperature was 425 K.",
    # TWO stacked modifiers. Added after a mutation exposed that the `{0,2}` bound in
    # `tc._PRE_LABEL` was an EQUIVALENT MUTANT -- the comment justifying it cited
    # exactly this sentence and no corpus contained one, so the bound was asserted by
    # prose and measured by nothing.
    "The measured sample temperature was 425 K.",
    "The recorded cryostat temperature was 80 K.",
    # the instant rules
    "The scan ended at 2026-01-01T00:00:00Z.",
    "The measurement started at 2026-01-01T00:00:00Z.",
    "It started at 2026-01-01T00:00:00Z.",
    "We started at 2026-01-01T00:00:00Z.",
    "Later the scan ended at 2026-01-01T00:00:00Z.",
)


def test_the_BENIGN_PRE_LABEL_loss_rate_is_MEASURED_and_RATCHETED():
    """The other side of the ledger: what fail-closed actually costs, as a number.

    **A GATE THAT REFUSES MOST OF HOW PEOPLE TALK IS NOT USABLE, and "every loss is
    disclosed" is not a defence against that** — the module's own words about gate
    (1)'s first version, which refused 86% of benign bridge forms and shipped
    measuring 0.

    Ratcheted rather than merely asserted: the rate may go DOWN freely and cannot go
    UP without this test failing, and each surviving loss must be a NAMED row of
    `tc._PRE_LABEL_RESIDUE` rather than an anonymous percentage point.

    MUTATION: reverting any of the three widening groups in `tc._PRE_LABEL_NOUN`
    turns this RED and prints every form it cost.
    """
    lost = [row for row in BENIGN_PRE_LABEL if not _values(row)]
    assert len(lost) <= len(tc._PRE_LABEL_RESIDUE), (
        f"benign pre-label loss rose to {len(lost)} of {len(BENIGN_PRE_LABEL)}; "
        f"_PRE_LABEL_RESIDUE names {len(tc._PRE_LABEL_RESIDUE)}. Either the gate "
        f"narrowed or a loss went unnamed:\n  "
        + "\n  ".join(repr(row) for row in lost)
    )
    # And every surviving loss is a NAMED row, so the percentage can never hide one.
    named = {row.rstrip(".") for row in tc._PRE_LABEL_RESIDUE}
    for row in lost:
        assert row.rstrip(".") in named, (
            f"an UNNAMED benign loss: {row!r} — add it to _PRE_LABEL_RESIDUE or "
            "widen the gate" + _explain(row)
        )
    # Every loss is DISCLOSED, which is the half that makes the trade §5-acceptable.
    for row in lost:
        assert _read(row).abstentions != (), _explain(row)


@pytest.mark.parametrize("sentence", tc._PRE_LABEL_RESIDUE)
def test_the_named_PRE_LABEL_residue_is_STILL_LOST(sentence):
    """Asserted the WRONG WAY ROUND, the discipline this module holds every open item
    to: closing one of these requires DELETING a row from `tc._PRE_LABEL_RESIDUE` — a
    reviewed change — rather than discovering that a documented cost quietly went away.

    These are spoken DISCOURSE MARKERS (`anyway`, `OK`), an OPEN class whose next
    member is unguessable, which is exactly why an allowlist cannot chase them. Each
    is recoverable with punctuation the speaker would probably use anyway, and the
    negative control below measures that rather than asserting it.
    """
    assert _values(sentence) == [], (
        "if this now reads, the discourse-marker cost is CLOSED — delete the row "
        "from _PRE_LABEL_RESIDUE and say so, do not weaken this" + _explain(sentence)
    )
    assert _read(sentence).abstentions != (), _explain(sentence)
    # THE RECOVERY, MEASURED: a comma is a clause bound, so the same words read.
    marker, rest = sentence.split(" the ", 1)
    recovered = f"{marker}, the {rest}"
    assert _values(recovered) == [425], (
        "the documented recovery must actually work" + _explain(recovered)
    )


@pytest.mark.parametrize(
    "sentence",
    (
        "The final temperature was 425 K.",
        "The starting temperature was 300 K.",
        "The initial temperature was 300 K.",
        "The ending temperature was 400 K.",
    ),
)
def test_a_temperature_at_ONE_POINT_of_a_progression_is_refused_DELIBERATELY(sentence):
    """**NOT residue. A decision, pinned so a future slice does not "fix" it.**

    These were listed as benign losses for one commit and that was wrong — counting a
    deliberate refusal as a false negative inflates the gate's cost and implies
    somebody means to admit it.

    Each states a temperature at ONE POINT of a progression, and which point
    `context.temperature_K` should hold is precisely the question
    `_KIND_NONE_SELECTED` refuses to answer for `"300 K, then 350 K, then 400 K"`.
    Admitting these would decide by PHRASING what the sequence gate declines to decide
    by MEASUREMENT: the same experiment would yield a value if the scientist said
    "the initial temperature" and no value if they said "300 K, then 350 K".

    MUTATION: adding `initial`/`final`/`starting`/`ending` to `tc._PRE_LABEL_NOUN`
    turns this RED, which is the guard against exactly that "fix".
    """
    reading = _read(sentence)
    assert reading.candidates == (), _explain(sentence)
    assert [entry.kind for entry in reading.abstentions] == [
        "words_before_the_label_name_something_else"
    ], _explain(sentence)


# --- RAMP / SEQUENCE SEMANTICS: measured as ALREADY SATISFIED, no code written ----


@pytest.mark.parametrize(
    "sentence",
    (
        "The temperature was 300 K, then 350 K, then 400 K.",
        "Temperature 300 K, then 350 K, then 400 K.",
        "The sample temperature was 300 K, then 350 K, then 400 K.",
        "The temperature was 300 K, then 350 K.",
    ),
)
def test_a_RAMP_is_neither_collapsed_nor_asserted_and_that_was_ALREADY_TRUE(sentence):
    """**MEASURED AS ALREADY SATISFIED. NO CODE WAS WRITTEN FOR THIS, AND THAT IS THE
    FINDING** — the `VAL-001` outcome, which this repository records as a legitimate
    and valuable result rather than a slice that did nothing.

    `CAP-001` and `4d6c74d9` claim the ramp/sequence work is done. Measured at
    `d3473414` BEFORE gate (4) existed, and re-measured here after it: all five
    required semantics already held, so this test pins them rather than implementing
    them.

    1. NOT silently collapsed to the first value — zero candidates, not `300`.
    2. NOT all three emitted as simultaneous authoritative scalars — zero, not three.
    3. The complete source statement is PRESERVED — the segment text round-trips
       verbatim, and the segment produces no candidate so it becomes a note.
    4. That a SEQUENCE was stated is preserved — the served reason says so in words.
    5. An unresolved review item is exposed — as an ABSTENTION.

    **(5) IS AN ABSTENTION AND NOT A `ReviewRequired`, AND THAT IS STRUCTURAL RATHER
    THAN A SHORTFALL.** `ReviewRequired.candidate_indexes` indexes into
    `TranscriptReading.candidates`, and its docstring is explicit that it *"groups
    them, it never removes them"* — so a `ReviewRequired` over ZERO candidates would
    be an empty grouping of nothing. The abstention is the unresolved item, it carries
    the quote and the instruction, and it is surfaced on the same response.

    **AND NO SCHEMA SEMANTICS WERE INVENTED, which `CAP-008` forbids.** No
    `bounds: [300, 400]` and no uncertainty: the schema carries uncertainty at exactly
    `$.descriptors.outputs[].descriptors[].uncertainty`, descriptor-only, and
    `context.temperature_K` has no sibling — so an interval here would assert
    something nobody stated.

    MUTATION: this pins behaviour this slice did not change; removing gate (4)
    entirely leaves it GREEN. That is the point — it isolates what was already true
    from what this slice did.
    """
    reading = _read(sentence)
    # (1) and (2)
    assert reading.candidates == (), _explain(sentence)
    # (3) the statement survives, verbatim, and becomes a note
    assert [segment.text for segment in reading.segments] == [sentence]
    assert reading.unmapped_segment_indexes == (0,), _explain(sentence)
    # (4) and (5): disclosed, and the reason names the sequence in words
    assert [entry.kind for entry in reading.abstentions] == [
        "several_values_and_none_selected"
    ], _explain(sentence)
    reason = reading.abstentions[0].reason
    assert "sequencing" in reason and "ONE value" in reason, reason
    # ... and states no value, which is what "no value was selected" has to mean.
    assert "300" not in reason and "350" not in reason and "400" not in reason, reason
    # No ReviewRequired: there are no candidates to group. See the docstring.
    assert reading.review_required == (), _explain(sentence)


def test_every_abstention_kind_the_reader_can_PRODUCE_has_a_served_policy_row():
    """**THE GUARD WHOSE ABSENCE LET GATE (4) SHIP WITHOUT A SERVED POLICY ROW.**

    `tc.AMBIGUITY_POLICY` is SERVED to clients (`routes.py:16309`), and for two
    commits it enumerated three pass-one outcomes while the reader produced four. A
    scientist receiving a `words_before_the_label_name_something_else` abstention
    would have found no rule for it in the one document that exists to explain the
    reader's refusals — a surface publishing completeness it did not have.

    **IT IS MEASURED FROM PRODUCED OUTPUT, NOT FROM A CONSTANT, AND THAT IS THE WHOLE
    DESIGN.** Three weaker versions of this test were available and each would have
    passed over the real gap:

    * comparing `AMBIGUITY_POLICY` against `_REFUSAL_REASONS` — passes for a kind
      that has a reason and no row, which is precisely the state that shipped;
    * comparing it against a hand-written list of kinds — a third place to forget;
    * asserting a COUNT — passes whenever one row is added and another removed.

    So this walks real sentences, collects the `kind` of every abstention the reader
    actually emits, and requires a served row for each. A new refusal kind cannot be
    added without either a policy row or a corpus that never fires it — and the
    second is caught by the emptiness assertion below.

    MUTATION: deleting the `words_before_the_label_name_something_else` row from
    `tc.AMBIGUITY_POLICY` turns this RED and names the kind.
    """
    corpus = [
        # gate (4) — both families
        "The setpoint temperature was 425 K.",
        "The previous scan ended at 2026-01-01T00:00:00Z.",
        # gate (1)
        "The temperature drift was 3 K.",
        # gate (2)
        "The temperature was 3 K above target.",
        # the sequence gate
        "The temperature was 300 K, then 350 K, then 400 K.",
        # pass two, both conditions
        "The temperature was 425 K, maybe 3 K of drift.",
        "The temperature was 425 K, ramped at 3 K/min",
        # the non-kelvin and implicit-subject abstentions
        "The temperature was 20 C.",
        "The absorbing element was iron.",
    ]
    produced: set[str] = set()
    for sentence in corpus:
        produced.update(entry.kind for entry in _read(sentence).abstentions)

    assert produced, "the corpus fired NO abstention at all, so this proves nothing"

    served = {row["kind"] for row in tc.AMBIGUITY_POLICY}
    missing = sorted(produced - served)
    assert missing == [], (
        f"the reader emits abstention kind(s) {missing} with no row in the SERVED "
        f"AMBIGUITY_POLICY — a scientist gets a refusal the published policy does "
        f"not explain. Add a row; do not delete this test."
    )

    # And every pass-one gate kind has BOTH a served row and a served reason, so the
    # two documents cannot drift apart in either direction.
    for kind in (
        tc._KIND_NOT_ASSERTED,
        tc._KIND_QUALIFIED,
        tc._KIND_NOT_THIS_SUBJECT,
        tc._KIND_NONE_SELECTED,
    ):
        assert kind in served, kind
        assert kind in tc._REFUSAL_REASONS, kind


@pytest.mark.parametrize("sentence", tc._VALUE_BEFORE_LABEL_RESIDUE)
def test_the_VALUE_BEFORE_LABEL_class_is_STILL_SILENT(sentence):
    """**A PRE-EXISTING class found by an independent adversarial hunt AFTER gate (4)
    shipped, asserted the WRONG WAY ROUND. It is a silent LOSS, which §5 ranks worse
    than the silent refusal gate (4) closed.**

    Every label-anchored pattern is label-then-value, so a sentence putting the
    quantity in FRONT of the label produces no match — hence no candidate AND no
    abstention. The reader never says it saw anything.

    **The tuple deliberately mixes the two halves**, because a fix has to satisfy both
    at once: `"A 425 K temperature was used"` is a real temperature that ought to
    read, and `"We saw a 3 K temperature drift"` is a drift that ought not to — and
    today they are indistinguishable, both silent, for the same reason.

    PRE-EXISTING, verified mechanically rather than assumed: `_TEMPERATURE_K` is
    byte-identical to `d3473414`, so this slice neither introduced nor worsened it.

    NOT FIXED: it is the DETECTOR, not a gate. See `tc._VALUE_BEFORE_LABEL_RESIDUE`
    for why that makes it a different shape of change — `_label_bridge` and
    `_pre_label_text` both slice on the assumption that `match.start(1)` sits after
    the label, and it is the one change here that can only ADD candidates.

    MUTATION: this pins behaviour this slice did not change; removing gate (4)
    entirely leaves it GREEN, which isolates it as pre-existing.
    """
    reading = _read(sentence)
    assert reading.candidates == (), (
        "if this now READS, the value-before-label class has moved — delete the row "
        "from _VALUE_BEFORE_LABEL_RESIDUE and say which half it closed"
        + _explain(sentence)
    )
    assert reading.abstentions == (), (
        "if this now DISCLOSES, the silence is closed — a strict improvement. "
        "Delete the row and say so; do not weaken this." + _explain(sentence)
    )
    # The cause, asserted rather than described: no detector matches at all.
    assert not any(
        rule.pattern.search(sentence)
        for rule in tc._RULES
        if rule.label_head is not None
    ), _explain(sentence)

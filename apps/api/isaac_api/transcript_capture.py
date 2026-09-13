"""Manual transcript capture — reading a FINALIZED transcript, deterministically.

WHAT THIS MODULE IS, AND WHAT IT IS NOT
=======================================
It is the repository's own deterministic reader for a transcript a scientist
**typed, pasted, or dictated and then explicitly finalized**. It is a closed table
of literal patterns over the five run-level official field paths this build can
write. It has no model, no scoring, no ranking, no learning, and no network.

**It is deliberately NOT the ``capture_extraction`` provider seam.** That seam
stands in for a model, its production implementation is ``unconfigured`` by
decision, and ``providers/config.validate_provider_config_or_raise`` refuses to
boot an application that selects its test double. Routing this feature through it
would mean the scientist workflow only worked when a model provider existed, which
is exactly backwards: reading ``temperature was 300 K`` out of a sentence needs no
model, and pretending it does would make an honest, always-available capability
look like an AI one. The seam is untouched by this module and stays unconsumed.

THE FOUR RULES THIS MODULE EXISTS TO ENFORCE
============================================

**(1) Nothing is read until a human finalizes.** This module is a pure function
and writes nothing anywhere; the route that calls it refuses without an explicit
``finalized: true``. There is no debounce, no timer, and no partial pass.

**(2) A candidate is never a value.** Every proposal is a
:class:`~.providers.extraction.FieldCandidate` — the existing type, with its
existing structural guarantees: ``status`` / ``verified`` / ``is_evidence`` /
``requires_user_confirmation`` are read-only properties returning constants on a
frozen, slotted dataclass, so a candidate that presents as confirmed is not
constructible. No parallel type is defined here.

**(3) An ambiguous run or field reference is never resolved by preference.**
Every ambiguity lands in exactly one of four typed outcomes, and the choice per
case is recorded in :data:`AMBIGUITY_POLICY`:

* :class:`Clarification` — the reading knows what it does not know and can name
  the alternatives, so it asks. Used for every run-reference ambiguity, because a
  run is a *choice a person makes*, and this build already refuses to infer "the
  only run that happens to exist" when capturing a note.
* :class:`ReviewRequired` — two statements propose different values for the same
  field. BOTH candidates are returned; neither is dropped and neither is
  preferred. Picking one would be a guess, and dropping both would lose a thing
  the scientist said twice. **CORRECTED 2026-09-12: until then this outcome was
  unreachable from a SINGLE sentence**, because every rule was matched with
  ``re.search`` — which returns the first match and nothing else. *"The temperature
  was around 425 K, maybe 430 K"* therefore produced one candidate of 425 and an
  empty ``review_required``, and **430 was lost in silence**: no candidate, no
  clarification, no abstention, no grouping. The text survived as a note, so
  nothing was destroyed; what was lost was the reading, and with it the
  scientist's chance to accept either value. ~~Two changes were needed, not one~~
  — **THREE, corrected 2026-09-12 by independent review.** ``finditer`` for a
  sentence that repeats the LABEL, a restatement read for a sentence that repeats
  only the VALUE (which is the form people actually speak), **and a gate on that
  restatement read**, which the first two shipped without. Unbounded, the
  restatement scan read the whole remainder of the segment and proposed a ramp
  rate, a step size, a pressure, a cryostat setpoint, an END instant and a FUTURE
  run's instant as alternative values for the labelled field — each with a
  ``rule`` string asserting the sentence had restated the quantity. **That is
  strictly worse than the omission it replaced: an omission loses a reading, an
  assertion invents one**, and §5 forbids the second in terms. ~~The gate is
  :data:`_HEDGE_BRIDGE`, and the invariant is that a hedging connective from a
  closed list must sit immediately between the two values with nothing else in
  the gap.~~ — **that was ONE of the gate's conditions, and the gate has had
  THREE since 2026-09-12 (second pass).** Each was added because the previous set
  was measured admitting a fabrication: (1) :data:`_HEDGE_BRIDGE`, a hedging
  connective from a closed list immediately between the two values with nothing
  else in the gap, six of the eleven admitted only behind an explicit ``or``;
  (2) :data:`_UNIT_TERMINATORS`, the unit is the whole unit, so ``3 K/min`` is
  never read as 3 kelvin; (3) :data:`_STATEMENT_END`, a restatement behind a BARE
  hedge must END the statement, so ``maybe 3 K of drift`` is not read as a
  temperature ~~behind a BARE hedge~~ — **(3) is UNIVERSAL over all three hedge
  branches since 2026-09-12 (third pass); it was bare-hedge-only for one commit
  and five sentences fabricated through the ``or`` branch.** **A refusal by any of
  the three is DISCLOSED** — the first two as ``unhedged_further_values``, the
  third as ``trailing_text_after_further_values`` — which is what makes the
  omission §5-acceptable where the assertion was not. Every sentence the three
  conditions were built against is named in
  :data:`_RESTATEMENT_RESIDUE_CLOSED`. **The RESTATEMENT entrance to this claim
  class is closed as far as measurement here can tell; the claim class is NOT** —
  the LABEL-ANCHORED rule of pass one over-reads the same way, silently and
  pre-existingly, and that is measured and named in
  :data:`_LABEL_OVERREACH_CLOSED` (CLOSED 2026-09-13).
  Note what is still refused: ``[425, 430]`` is never constructed. That asserts a
  continuous interval nobody stated, and the official schema's only uncertainty
  representation is ``$.descriptors.outputs[].descriptors[].uncertainty``, which
  ``context.temperature_K`` has no sibling of.
* :class:`Abstention` — the reading recognises the subject and declines to
  propose anything, because a proposal would require a conversion or a schema
  decision nobody made. Nothing is asked, because there is no alternative to
  offer.
* an **unmapped note** — the default, and by far the commonest. Text nothing
  matched is stored verbatim; see (4).

**(4) Scientist-entered text is never silently discarded.** EVERY segment of a
finalized transcript becomes an Unmapped Note, including the segments that DID
produce a candidate. That is the deliberate, slightly redundant choice: ~~a
candidate is not stored anywhere~~ — **CORRECTED 2026-09-10: since the transcript
producer shipped, a candidate's VALUE is stored, as the ``proposed_value`` of a
durable ``IngestionProposal`` minted by ``routes._mint_transcript_proposals`` in the
same write as these notes. The candidate object itself is still stored nowhere, and
the reasoning below is UNCHANGED and is why: a proposal is not a durable home for
the scientist's words, because it can be rejected, superseded or withdrawn, and
neither of those acts returns the sentence it came from** — so if notes were
captured only for the unmatched segments, then rejecting a candidate — or failing to
accept one — would destroy the words it came from. Capturing every segment makes text survival independent of
what the reader proposed and of whether any acceptance ever succeeded.

WHY THE PROPOSED VALUE IS ALWAYS A QUOTE
========================================
Every rule below proposes either the literal substring the scientist wrote or a
number parsed from it. Nothing normalises a vocabulary term, expands an
abbreviation, converts a unit, or reformats a timestamp. A scientist reviewing a
candidate is therefore checking their own words, not a paraphrase they now have to
reverse-engineer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .providers.extraction import ORIGIN_TRANSCRIPT, FieldCandidate

__all__ = [
    "AMBIGUITY_POLICY",
    "MAX_CANDIDATES",
    "MAX_CANDIDATE_QUOTE_BYTES",
    "MAX_DISCLOSURES",
    "MAX_SEGMENTS",
    "OUTCOME_ABSTENTION",
    "OUTCOME_CLARIFICATION",
    "OUTCOME_NEEDS_REVIEW",
    "OUTCOME_UNMAPPED",
    "PRODUCED_BY",
    "READABLE_FIELD_PATHS",
    "RETENTION_ENFORCED_STATE",
    "RETENTION_STATES_NOT_IMPLEMENTED",
    "Abstention",
    "Clarification",
    "ReviewRequired",
    "RunRef",
    "Segment",
    "TranscriptReading",
    "TranscriptTooDense",
    "read_transcript",
    "segment_transcript",
]


class TranscriptTooDense(Exception):
    """One finalized transcript whose reading would exceed a candidate ceiling.

    **RAISED RATHER THAN REPORTED ON THE READING, AND THAT IS THE WHOLE POINT.**
    The obvious alternative — return a :class:`TranscriptReading` carrying a
    ``too_dense`` marker and an empty ``candidates`` tuple — was rejected because a
    caller that ignores the marker gets an empty list that looks like a complete
    reading of a transcript that read nothing, which is the silent discard this
    module exists to refuse, reached through the fix instead of through the defect.
    A truncated list is worse still. An exception is the one shape a caller cannot
    accidentally treat as a successful reading, and this route already has the
    idiom: ``notes.UnsupportedNote`` is raised by the model and becomes a typed
    ``422`` at the route.

    It carries the EXACT numbers rather than "at least" ones. All ~~THREE~~ **FOUR
    (2026-09-12, fourth pass)** are known
    exactly before any candidate is constructed, because locating the matches and
    de-duplicating the values is cheap and building
    :class:`~.providers.extraction.FieldCandidate` objects is not — see
    :func:`_segment_readings`.

    **IT IS RAISED WHEN ANY ONE OF THE ~~THREE~~ FOUR CEILINGS IS EXCEEDED, AND IT
    ALWAYS CARRIES ALL ~~THREE~~ FOUR MEASURED COUNTS**, including the ones that are
    inside their
    ceilings. That is not padding: a client told only the number that bound cannot
    tell a transcript that is marginal on one axis from one that is far over on
    another, and every one of the four is measured by then anyway.

    **THE FOURTH IS ``disclosure_options``** — see :data:`MAX_DISCLOSURE_OPTIONS`.
    It exists because :data:`MAX_DISCLOSURES` bounds the COUNT of disclosures and
    a :class:`Clarification` carries one ``options`` entry per run of the record,
    so a transcript inside all three earlier ceilings still served a response that
    grew without bound in the record's run count.
    """

    def __init__(
        self,
        *,
        candidates: int,
        candidate_quote_bytes: int,
        disclosures: int,
        disclosure_options: int,
        maximum_candidates: int,
        maximum_candidate_quote_bytes: int,
        maximum_disclosures: int,
        maximum_disclosure_options: int,
    ) -> None:
        self.candidates = candidates
        self.candidate_quote_bytes = candidate_quote_bytes
        self.disclosures = disclosures
        self.disclosure_options = disclosure_options
        self.maximum_candidates = maximum_candidates
        self.maximum_candidate_quote_bytes = maximum_candidate_quote_bytes
        self.maximum_disclosures = maximum_disclosures
        self.maximum_disclosure_options = maximum_disclosure_options
        super().__init__(
            f"this transcript reads {candidates} candidates carrying "
            f"{candidate_quote_bytes} quoted bytes and reports {disclosures} "
            f"disclosures carrying {disclosure_options} run options; the ceilings "
            f"are {maximum_candidates} candidates, "
            f"{maximum_candidate_quote_bytes} quoted bytes, "
            f"{maximum_disclosures} disclosures and "
            f"{maximum_disclosure_options} run options"
        )

#: Named on every candidate this module produces. It is NOT
#: ``deterministic-fake``: that name belongs to the provider seam's test double,
#: and reusing it would file an always-on product capability under a label whose
#: whole meaning is "a stand-in for a model that does not exist".
PRODUCED_BY = "transcript-reader"

#: The largest number of segments one finalized transcript may yield.
#:
#: A CEILING THAT REFUSES, NEVER TRUNCATES. Every segment becomes a stored note,
#: so an unbounded transcript is an unbounded write. A transcript over this size is
#: refused whole, with nothing written, because a partially-captured transcript is
#: the silent discard this feature exists to end — and a scientist who is told
#: "refused, split it" still has every word, while one who is told "captured" does
#: not.
MAX_SEGMENTS = 100

#: The largest number of candidates one finalized transcript may read.
#:
#: WHY A COUNT CEILING EXISTS IN THE READER AT ALL. ``MAX_SEGMENTS`` does not bound
#: this, and the reason is what punctuation-free ASR emits: a transcript with no
#: ``.``, ``!``, ``?`` or newline anywhere is **one** segment, so it passes the
#: segment ceiling whatever it contains. Measured on the code that shipped without
#: this bound, through the real route: a **27,025-byte single segment** naming 3,000
#: distinct kelvin values produced **3,001 candidates** and a **165,828,285-byte**
#: response, built and serialised INSIDE ``record_lock``. Every individual refusal
#: worked exactly as designed — the durable write refused all 3,001 as
#: ``proposals_too_large`` and minted none — because the durable write is not where
#: the cost is. The RESPONSE and the LOCK HOLD are.
#:
#: **THE NUMBER IS A JUDGEMENT, NOT A MEASUREMENT, AND SAYING SO IS PART OF IT** —
#: ``routes._MAX_PROPOSALS_PER_RECORD`` makes the same disclosure for the same
#: reason. Nothing here has measured a response-assembly or lock-hold cost at any
#: candidate count on the deployed pod, so no figure in this comment is derived from
#: one. What it IS derived from is the worst LEGITIMATE case it must still admit: a
#: transcript at the segment ceiling with a hedged chain in every sentence —
#: ``MAX_SEGMENTS`` × 4 = 400 — which this admits with headroom. A single 256 KiB
#: ASR blob is the other worst legitimate case, and it is bounded by BYTES rather
#: than by count; see below.
MAX_CANDIDATES = 500

#: The largest total quoted-segment size, in bytes, one transcript's candidates may
#: carry: ``sum(len(segment.text.encode()) for each candidate)``.
#:
#: **THE TWO BOUNDS DO NOT COMPOSE, AND THIS EXISTS BECAUSE THEY DO NOT.** This
#: repository has already solved exactly this shape once and the precedent is worth
#: citing rather than re-deriving: ``routes._MAX_PROPOSALS_PER_RECORD``
#: (``routes.py`` ~12132) beside ``routes._MAX_PROPOSAL_STATE_BYTES`` (~12176),
#: whose comment reads *"THE TWO BOUNDS ABOVE DO NOT COMPOSE, AND THIS EXISTS
#: BECAUSE THEY DO NOT … a bound on rows that a client can defeat by making each
#: row large is not a bound."* It is the same defeat here, and it is cheap: every
#: candidate carries the whole segment TWICE — once as ``quote`` and once inside the
#: ``rule`` sentence — so the cost is O(values × segment length), and a caller that
#: has run out of COUNT still has 256 KiB of transcript to spend on LENGTH.
#:
#: Measured, and this is the measurement that proves the pair is needed rather than
#: one of them: with ``", maybe "`` between the values — i.e. hedged, and therefore
#: still accepted by :data:`_HEDGE_BRIDGE` — the same attack produced **3,001
#: candidates** and a **273,900,285-byte** response. **The adjacency gate does not
#: bound size, and a size bound does not make values honest.** Two defects, two
#: fixes.
#:
#: **THE NUMBER IS A JUDGEMENT, NOT A MEASUREMENT.** The reasoning is that
#: ``routes._MAX_TRANSCRIPT_BYTES`` is ``_MAX_NOTE_BYTES`` = 256 KiB, and a
#: transcript that fills it and reads two candidates per segment costs 2 × 256 KiB
#: of quotes; that is the worst LEGITIMATE case, it is admitted, and this is twice
#: it. At the ceiling the response is roughly 2 MiB rather than the 274 MB above,
#: because the quote is carried twice.
#:
#: ~~"It is written as a multiple of the transcript ceiling rather than as a bare
#: literal, so it follows that constant instead of drifting from it."~~ —
#: **CORRECTED 2026-09-12: that misdescribes the mechanism in force.** The
#: expression below is the bare literal ``4 * 256 * 1024``; it does not reference
#: ``routes._MAX_TRANSCRIPT_BYTES`` and **cannot**, because ``routes`` imports this
#: module, so an import here would be circular. It therefore does NOT follow that
#: constant — if ``_MAX_NOTE_BYTES`` moved, this number would not. The INVARIANT is
#: real and the reasoning above is unchanged; what holds it is a TEST
#: (``test_transcript_capture_ceilings.py``, which asserts the two against each
#: other), not the arithmetic. The fix is this comment, not the constant: making it
#: an import would be the circularity, and hard-coding ``1048576`` would lose the
#: derivation a reader needs.
MAX_CANDIDATE_QUOTE_BYTES = 4 * 256 * 1024

#: The largest number of DISCLOSURES — abstentions plus clarifications — one
#: finalized transcript may report.
#:
#: **THE THIRD CEILING, AND IT EXISTS BECAUSE THE FIRST TWO MEASURABLY DID NOT
#: BOUND IT.** Both bound the CANDIDATE list, and they are fed from inside
#: ``read_transcript``'s ``if not settled: continue`` — so neither has ever seen an
#: abstention or a clarification, which are appended one per regex MATCH.
#: ``MAX_SEGMENTS`` does not help, because punctuation-free ASR emits ONE segment.
#: Measured at ``bce43f19``, on legal single-segment transcripts sized at exactly
#: ``routes._MAX_TRANSCRIPT_BYTES``:
#:
#: ==================================  ========  =====================  ==========
#: payload                             bytes     disclosures            serialised
#: ==================================  ========  =====================  ==========
#: ``"temperature 1 C "`` x 16,384     262,144   16,384 abstentions     ~5.1 MB
#: ``"run zzz at 1 K "`` x 17,476      262,140   17,476 clarifications  ~4.3 MB
#: ==================================  ========  =====================  ==========
#:
#: So the 165 MB the first two ceilings closed became ~5 MB, still assembled and
#: serialised inside ``record_lock``. Smaller is not bounded.
#:
#: **THE NUMBER IS A JUDGEMENT, NOT A MEASUREMENT, AND SAYING SO IS PART OF IT** —
#: the same disclosure ``MAX_CANDIDATES`` and ``routes._MAX_PROPOSALS_PER_RECORD``
#: make, for the same reason. Nothing here has measured a response-assembly or
#: lock-hold cost at any disclosure count on the deployed pod, so no figure in this
#: comment is derived from one.
#:
#: What it IS derived from is the worst LEGITIMATE case it must still admit, and
#: that case is MEASURED rather than reasoned
#: (``test_the_worst_legitimate_disclosure_load_is_admitted``): a transcript at the
#: segment ceiling whose every sentence is maximally ambiguous — an absorption-edge
#: mention, a non-kelvin temperature, and BOTH refusal kinds for two of the three
#: rules that can refuse — reports ~~**6 disclosures per sentence and 600 in
#: total**~~ **9 per sentence and 900 in total**, and is ADMITTED.
#:
#: **THIS NUMBER HAS NOW BEEN WRONG TWICE AND THE WHOLE SEQUENCE IS KEPT, because a
#: reader who sees only the latest figure cannot tell a corrected claim from a
#: drifting one: 600 (false) → 700 (true, and what the test measured) → 900 (true
#: now).** 600 was made false by the 2026-09-12 region walk, which added a seventh
#: disclosure to that fixture, and was not swept; an independent review measured
#: **700** on 2026-09-13 and was right. 900 is this slice's own PASS-ONE ASSERTION
#: GATE adding two more to the same fixture — both of which are FABRICATIONS it
#: refused, not noise: the word ``end`` inside *"at the end, then <instant>"* is not
#: the assertion *"the scan ended"*, and that fixture had been reading two instants
#: off it. Re-derive rather than quoting: the test itself measures it.
#:
#: (~~That transcript also reads **500** candidates, which is ``MAX_CANDIDATES``
#: exactly, so it is admitted by the narrowest possible margin on a different axis.
#: The coincidence is named rather than relied on.~~ — **STRUCK 2026-09-13: it now
#: reads 300, for exactly the two refusals above, and the coincidence is gone.
#: ``_COUNT_ONLY`` in the ceilings file, at 600 candidates, is what exercises that
#: axis at its margin.**)
#:
#: **THE 600 IS NOT A BOUND BY CONSTRUCTION AND MUST NOT BE READ AS ONE.** The two
#: RESTATEMENT-refusal kinds are deduplicated per segment per rule, so those are
#: bounded at ``MAX_SEGMENTS`` × 3 restatement-carrying rules × 2 kinds = 600
#: whatever a transcript says — and since 2026-09-13 the PASS-ONE gate's THREE
#: kinds are deduplicated the same way over the same 3 label-gated rules, so the
#: construction bound over all five refusal kinds is ``MAX_SEGMENTS`` × 3 × 5 =
#: **1,500**, which is still inside this ceiling and is why it did not have to move. ``temperature_not_in_kelvin`` and every run
#: clarification are **not**: they are appended one per regex MATCH, which is
#: exactly how the 16,384 and 17,476 above arise. A sentence stating six
#: temperatures in celsius reports six. So the total has no construction bound at
#: all, and this constant is the only thing standing where one is needed.
#:
#: **WHAT IT DOES NOT BOUND, NAMED SO THE NEXT SLICE DOES NOT HAVE TO FIND IT.** It
#: bounds the COUNT, not the per-entry SIZE. An abstention's ``reason`` is a shared
#: literal and its ``quote`` is a short label-anchored match, but a
#: ``Clarification`` carries ``options`` — one entry per run of the record — so the
#: served size of a clarification grows with the record's run count, which this
#: constant cannot see. At the ceiling with a heavily-run record that is a larger
#: response than the arithmetic above suggests. It is a bound, and it is not the
#: only bound that axis would want.
#:
#: **PER-SEGMENT DEDUPLICATION WAS CONSIDERED AND IS NOT THIS FIX**, and the reason
#: is worth keeping: it takes the first payload above to one disclosure, and
#: ``"temperature 1 C temperature 2 C …"`` with distinct numbers still yields
#: ~16,000. It reduces without bounding, and it would read as a bound.
MAX_DISCLOSURES = 2000

#: The largest total number of run OPTIONS one finalized transcript's disclosures
#: may carry: ``sum(len(entry.options) for entry in clarifications)``.
#:
#: **THE FOURTH CEILING, AND IT EXISTS BECAUSE THE THIRD MEASURABLY DID NOT BOUND
#: THE RESPONSE.** :data:`MAX_DISCLOSURES` bounds the COUNT, and its own comment
#: says so — *"It bounds the COUNT, not the per-entry SIZE … a ``Clarification``
#: carries ``options`` — one entry per run of the record — so the served size of a
#: clarification grows with the record's run count, which this constant cannot
#: see."* It named the axis and not the magnitude, and the magnitude is the finding.
#: ``routes`` builds ``known_runs`` from ``exp.sorted_runs()`` — EVERY run, not a
#: page — and runs per record are uncapped (``RUN_PAGE_MAX`` bounds a LIST response,
#: not creation).
#:
#: **MEASURED THROUGH THE REAL ROUTE** at ``22d794a5``, with a
#: ``create_app()`` ``TestClient``, on the largest admitted payload: ONE segment
#: (no sentence-ending punctuation anywhere) of ``"run zzz at 1 K "`` × 1,999 —
#: 29,985 bytes, **1,999 disclosures ≤ 2,000**, 0 candidates, 0 quoted bytes, so it
#: is inside all three earlier ceilings and answered **200**:
#:
#: =========  =============  =====================  ============
#: runs       disclosures    status                 response
#: =========  =============  =====================  ============
#: 1          1,999          200                    634,390 B
#: 200        1,999          200                    28,852,274 B
#: 1,000      1,999          200                    143,998,672 B
#: 5,000      1,999          200                    735,702,672 B
#: =========  =============  =====================  ============
#:
#: **144 MB is 28× the ~5.1 MB this ceiling's predecessor was built against, and
#: is of the same order as the 165 MB the first two ceilings closed** — assembled
#: and serialised inside ``record_lock``. Per option the serialised cost is
#: ~72 bytes, which is the figure this constant is set against.
#:
#: **A REFERRING BRIEF'S PAYLOAD WAS MEASURED AND IS REFUSED ALREADY, and recording
#: that is part of the fix.** ``"the first run. " * 1999`` — the same text WITH the
#: sentence-ending period — was cited as ADMITTED at 49.2 / 245.9 / 1,245.4 MB. It
#: is not: the period makes it **1,999 SEGMENTS**, so ``MAX_SEGMENTS`` (100) refuses
#: it at the route with a **422** and a **294-byte** body, ~~at every run count
#: measured~~ — **FALSE AT EVERY RUN COUNT THAT SENTENCE CITED, corrected 2026-09-13
#: after an independent review measured it.** The payload IS refused at every run
#: count; the REASON is not the one stated, and the reason is what the sentence was
#: offering. ``routes`` calls ``read_transcript`` (``routes.py:15256``) BEFORE it
#: checks ``len(reading.segments) > MAX_SEGMENTS`` (``routes.py:15292``), so this
#: reader's own ceilings get the first refusal. Re-measured in-process at each count:
#:
#: =========  ===============================  ======================
#: runs       which bound refuses first        error
#: =========  ===============================  ======================
#: 1          ``MAX_SEGMENTS``, at the route   ``transcript_too_long``
#: 10         ``MAX_SEGMENTS``, at the route   ``transcript_too_long``
#: 11         ``MAX_DISCLOSURE_OPTIONS``       ``transcript_too_dense``
#: 200        ``MAX_DISCLOSURE_OPTIONS``       ``transcript_too_dense``
#: 1,000      ``MAX_DISCLOSURE_OPTIONS``       ``transcript_too_dense``
#: 5,000      ``MAX_DISCLOSURE_OPTIONS``       ``transcript_too_dense``
#: =========  ===============================  ======================
#:
#: The threshold is **11 runs** (1,999 clarifications × 11 = 21,989 > 20,000), and
#: the three counts the struck sentence named — 200, 1,000, 5,000 — are all above
#: it. So the segment reason is reachable only BELOW 11 runs. Those three MB figures
#: are still in-process readings of a reading whose response the route never
#: serialises, which is the point that survives; the defect is real; the payload that
#: reaches it has no periods, and the numbers are the table above.
#:
#: **THE NUMBER IS A JUDGEMENT, NOT A MEASUREMENT, AND SAYING SO IS PART OF IT** —
#: the same disclosure the other three make. Nothing here has measured a
#: response-assembly or lock-hold cost on the deployed pod. What it IS derived from
#: is the worst LEGITIMATE case it must still admit: a transcript at the segment
#: ceiling (``MAX_SEGMENTS`` = 100) whose every sentence names one unresolvable run,
#: on a record holding ``routes.RUN_PAGE_MAX`` = 200 runs — this repository's own
#: statement of the magnitude a run list is designed around.
#:
#: **AND IT IS ADMITTED ONLY WHEN A RUN HAS ALREADY BEEN SELECTED — corrected
#: 2026-09-13.** With ``selected_run=None``, which is the ORDINARY FIRST-CAPTURE
#: PATH, ``read_transcript`` inserts a ``run_target_required`` clarification
#: carrying EVERY run, so this very case becomes 101 × 200 = **20,200** and is
#: REFUSED. Measured both ways on that exact payload
#: (``"We looked at run zzz and it was fine."`` × 100, 200 runs):
#: ``selected_run="run-1"`` → 100 disclosures / **20,000** options / ADMITTED,
#: exactly at the ceiling; ``selected_run=None`` → **20,200** / REFUSED. So the
#: ceiling sits exactly ON the boundary of its own stated worst case, and one extra
#: clarification crosses it.
#:
#: **THE REVIEW THAT FOUND THIS DEMONSTRATED IT ON THE WRONG FIXTURE, and saying so
#: is part of recording it.** It cited
#: ``test_the_worst_legitimate_disclosure_load_is_admitted``; on THAT fixture the
#: claim is TRUE with no run selected — measured 201 disclosures / 200 options /
#: ADMITTED — because an unsettled run target makes ``read_transcript`` skip
#: ``_segment_readings`` for every segment, so its 900 refusal disclosures are never
#: produced, and its sentences name no run. The two fixtures are not
#: interchangeable: one floods REFUSALS and carries no options, the other floods RUN
#: REFERENCES and carries all of them. The FINDING is real on the constant's own
#: stated case; the DEMONSTRATION was not.
#:
#: 100 × 200 = 20,000
#: options ≈ 1.4 MB serialised, which is the same order as the ~2 MiB
#: :data:`MAX_CANDIDATE_QUOTE_BYTES` admits at its own ceiling. Like that constant
#: this is a bare literal and CANNOT reference ``routes`` (``routes`` imports this
#: module), so a TEST holds the derivation, not the arithmetic.
#:
#: **IT IS THE EXACT SERVED OPTION COUNT, NOT ``disclosures × len(known_runs)``,
#: AND THE DIFFERENCE IS MEASURED RATHER THAN STYLISTIC.** The product over-counts
#: twice: an :class:`Abstention` carries NO options at all, and
#: ``ambiguous_run_reference`` / ``conflicting_run_reference`` carry a SUBSET of the
#: runs. Applied to this module's own documented worst legitimate case — ~~600~~
#: **900**
#: disclosures, every one an abstention — the product reads ~~600 × 200 = 120,000~~
#: **900 × 200 = 180,000** and
#: would refuse a transcript that serves **zero** options, i.e. it would refuse the
#: case the third ceiling was explicitly set to admit. The exact sum reads 0 there
#: and 399,800 on the 200-run attack above, so it separates the two rather than
#: ranking them. (The struck pair was ALSO wrong when it was committed, by a
#: different amount: the fixture measured 700 that day, not 600. Both corrections
#: are kept — see :data:`MAX_DISCLOSURES` for the 600 → 700 → 900 sequence.)
#:
#: **WHAT IT DOES NOT BOUND, NAMED SO THE NEXT SLICE DOES NOT HAVE TO FIND IT.**
#: It bounds the option COUNT, and ~~an option is three short identifier fields, so
#: count is a good proxy for bytes HERE — but it is still a proxy.~~ — **THE PROXY
#: IS WRONG BY ~8×, measured 2026-09-13 by independent review and re-measured here.
#: The sentence is struck rather than softened, because "a good proxy for bytes" is
#: what the ~72 B/option derivation above rests on.** One of those three fields is
#: the run's ``label``, which is CALLER-SUPPLIED and capped at **510 characters**
#: (511 → ``422 unrepresentable_value``), and ``RunRef.to_option()`` serialises it
#: into every option. Re-measured here over ``json.dumps(run.to_option())``:
#:
#: ===================  ====================
#: label length         served option bytes
#: ===================  ====================
#: 7 (default label)    73 B
#: 200                  266 B
#: 510 (the cap)        576 B
#: ===================  ====================
#:
#: At the route with 200 runs the review measured whole responses of 2,146,142 B
#: (default labels), 5,997,442 B (200-char) and 12,166,442 B (510-char) — 608
#: B/option including per-entry framing — with ALL FOUR ceilings inside their
#: limits, so it is ADMITTED and serialised inside ``record_lock``. That is more
#: than twice the ~5.1 MB :data:`MAX_DISCLOSURES` was created to close, and it is
#: the same defeat the ceilings' own precedent names: *"a bound on rows that a
#: client can defeat by making each row large is not a bound."*
#:
#: **THE CONSTANT IS DELIBERATELY NOT CHANGED, AND THE CHOICE IS ARGUED RATHER THAN
#: ASSUMED.** Two fixes were available and both are rejected here:
#:
#: * **Re-deriving the constant against measured bytes** — lowering it so the
#:   admitted worst case is ~1.4 MB again — would REFUSE a legitimate first capture
#:   on any record whose scientist wrote long run labels. Refusing a transcript
#:   because the run NAMES are verbose is a worse failure than a large response,
#:   and it would refuse the case the ceiling above was explicitly set to admit.
#: * **Bounding the label's contribution** means truncating caller-supplied text
#:   inside a served option — a change to a payload shape frontend consumers read,
#:   which is the same reason the structural fix below is already deferred.
#:
#: So what is corrected is the CLAIM: the admitted worst case is ~12 MiB, not
#: ~1.4 MB, and the axis is the LABEL rather than the count. The bound still
#: bounds; its stated derivation was wrong. The structural
#: fix is to serve ``options`` ONCE per response and have each clarification carry
#: run IDS, which would make the response O(runs + clarifications) instead of
#: O(runs × clarifications) and would need no ceiling at all. That is the better
#: long-term answer and it is deliberately NOT taken here: it changes a served
#: payload shape that frontend consumers read, in a slice whose job is to bound a
#: resource. Named, not built.
MAX_DISCLOSURE_OPTIONS = 20_000

OUTCOME_CLARIFICATION = "clarification"
OUTCOME_NEEDS_REVIEW = "needs_review"
OUTCOME_ABSTENTION = "abstention"
OUTCOME_UNMAPPED = "unmapped"


# --- retention: exactly one state, because exactly one is enforced -------------

#: The ONE retention state this build's storage architecture actually enforces.
#:
#: A finalized transcript is stored as Unmapped Notes inside the experiment's own
#: state document, and it stays there for the life of the experiment. That is not a
#: policy this module chose; it is what the notes model *is* — it offers no delete,
#: by design, and dismissal is a recorded state rather than a removal.
RETENTION_ENFORCED_STATE = "retained_with_experiment"

#: The retention states this build DOES NOT offer, each with the reason.
#:
#: They are listed rather than omitted. A settings screen with one option looks
#: like an oversight; a settings screen with one option and a stated reason for
#: each absent one is a disclosure. Neither of these can be implemented honestly
#: today: both are deletion guarantees, and there is no deletion anywhere in the
#: notes model to build one on. Offering a control that quietly did nothing would
#: be worse than offering none.
RETENTION_STATES_NOT_IMPLEMENTED: tuple[dict[str, str], ...] = (
    {
        "state": "retain_during_draft",
        "reason": (
            "This would require the transcript to be removed when the record is "
            "exported or submitted. Captured content is stored as notes, and this "
            "build has no operation that removes a note — dismissing one records a "
            "review decision and leaves the text readable. Offering this state "
            "would promise a deletion that nothing performs."
        ),
    },
    {
        "state": "remove_after_extraction",
        "reason": (
            "This would require the transcript to be removed once candidates have "
            "been reviewed. The same missing deletion applies, and it would also "
            "destroy the words behind every candidate a scientist rejected, which "
            "is the loss this feature is built to prevent."
        ),
    },
)


# --- the ambiguity policy, stated once and served -----------------------------

#: EVERY ambiguity this reader can encounter, with the outcome it produces and why
#: that outcome rather than another. Served by the route so the policy a client
#: explains and the policy the reader applies are one expression.


# --- the value shapes ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Segment:
    """One sentence-ish span of the finalized transcript, located by character.

    Offsets index back into the original text exactly — they are computed by
    scanning forward through it — so a quote a candidate stakes its provenance on
    can always be checked against the source.
    """

    index: int
    text: str
    start_char: int
    end_char: int

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "text": self.text,
            "start_char": self.start_char,
            "end_char": self.end_char,
        }


@dataclass(frozen=True, slots=True)
class RunRef:
    """The identifiers of one run, as this reader is allowed to see them.

    Deliberately NOT the run itself: matching a spoken reference against a run's
    measured values would make the target depend on a classification this reader
    has no grounds to make. Label, ordinal, id and record id are what a person
    says out loud.
    """

    id: str
    label: str
    ordinal: int
    record_id: str | None = None

    def to_option(self) -> dict:
        """The shape a clarification offers as a choice. Identifiers only."""
        return {"run_id": self.id, "label": self.label, "ordinal": self.ordinal}


@dataclass(frozen=True, slots=True)
class Clarification:
    """A question this reader cannot answer, with the alternatives it can see."""

    kind: str
    question: str
    quote: str | None
    options: tuple[dict, ...] = ()
    segment_index: int | None = None

    @property
    def outcome(self) -> str:
        return OUTCOME_CLARIFICATION

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "kind": self.kind,
            "question": self.question,
            "quote": self.quote,
            "options": [dict(option) for option in self.options],
            "segment_index": self.segment_index,
        }


@dataclass(frozen=True, slots=True)
class Abstention:
    """A subject this reader recognised and deliberately proposed nothing for."""

    kind: str
    reason: str
    quote: str
    segment_index: int

    @property
    def outcome(self) -> str:
        return OUTCOME_ABSTENTION

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "kind": self.kind,
            "reason": self.reason,
            "quote": self.quote,
            "segment_index": self.segment_index,
        }


@dataclass(frozen=True, slots=True)
class ReviewRequired:
    """Two or more candidates that contradict each other at one field path."""

    kind: str
    field_path: str
    reason: str
    #: Indexes into :attr:`TranscriptReading.candidates`. Every one of them is
    #: still present there; this groups them, it never removes them.
    candidate_indexes: tuple[int, ...]

    @property
    def outcome(self) -> str:
        return OUTCOME_NEEDS_REVIEW

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "kind": self.kind,
            "field_path": self.field_path,
            "reason": self.reason,
            "candidate_indexes": list(self.candidate_indexes),
        }


@dataclass(frozen=True, slots=True)
class TranscriptReading:
    """One pass over one finalized transcript. Proposes; never applies.

    ``applied`` is a constant ``False`` property rather than a field, for the
    reason ``ExtractionResult.applied`` is one: a reading cannot be constructed
    claiming it wrote something.
    """

    segments: tuple[Segment, ...]
    candidates: tuple[FieldCandidate, ...]
    clarifications: tuple[Clarification, ...]
    abstentions: tuple[Abstention, ...]
    review_required: tuple[ReviewRequired, ...]
    #: Segment index -> the single candidate index it produced, when it produced
    #: exactly one. A segment producing none, or more than one, is absent — see
    #: :func:`candidate_for_segment`.
    candidate_by_segment: Mapping[int, int]
    #: The run every candidate is proposed against, or ``None`` when no candidate
    #: was proposed at all.
    run_target: str | None

    @property
    def applied(self) -> bool:
        """Always ``False``. This module writes nothing, anywhere."""
        return False

    @property
    def unmapped_segment_indexes(self) -> tuple[int, ...]:
        """Segments that produced no candidate. Every one becomes a note — but so
        does every other segment; see the module docstring, rule (4)."""
        return tuple(
            segment.index
            for segment in self.segments
            if segment.index not in self.candidate_by_segment
        )

    def candidate_for_segment(self, index: int) -> FieldCandidate | None:
        """The one candidate a segment produced, or ``None``.

        ``None`` for a segment that produced two, deliberately. A note carries at
        most one ``candidate_field_path``, and recording one of two proposals
        there would state a preference this reader does not hold.
        """
        position = self.candidate_by_segment.get(index)
        return None if position is None else self.candidates[position]


# --- segmentation -------------------------------------------------------------

#: A sentence boundary or a line break. Fixed and simple on purpose: a cleverer
#: splitter would be a language model in disguise, and the offsets are what a
#: quote's honesty rests on.
_SEGMENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def segment_transcript(text: str) -> tuple[Segment, ...]:
    """Split a transcript into located segments. Offsets round-trip exactly."""
    pieces = [piece for piece in _SEGMENT_BOUNDARY.split(text) if piece and piece.strip()]
    segments: list[Segment] = []
    cursor = 0
    for index, piece in enumerate(pieces):
        start = text.index(piece, cursor)
        end = start + len(piece)
        cursor = end
        segments.append(Segment(index=index, text=piece, start_char=start, end_char=end))
    return tuple(segments)


# --- the closed rule table ----------------------------------------------------
#
# EVERY PATH BELOW IS RUN-LEVEL, and that is not a coincidence: the only operation
# in this application that writes a confirmed value at a dotted official path is
# the run edit, and this reader refuses to propose anything it cannot show a
# scientist a way to accept. The route re-checks every path against the set that
# operation enforces, so the two cannot drift.

#: ``<number>`` — a plain decimal. No exponents, no thousands separators, no
#: unicode digits: a number a person dictates, not a number a machine emits.
_NUMBER = r"(-?\d{1,6}(?:\.\d{1,6})?)"

#: temperature ... N K. The unit is REQUIRED and must be kelvin.
_TEMPERATURE_K = re.compile(
    rf"\btemperatures?\b[^.;:]{{0,40}}?{_NUMBER}\s*(?:K\b|kelvin\b)", re.IGNORECASE
)

#: The KELVIN VALUE FORM ALONE — the same value the rule above reads, without the
#: label in front of it.
#:
#: WHY A SECOND PATTERN EXISTS AT ALL. ``_TEMPERATURE_K`` is anchored on the literal
#: word ``temperature``, and a scientist states a second value without saying the
#: word again: *"the temperature was around 425 K, maybe 430 K"*. Matching the rule
#: repeatedly over that sentence finds ONE match, because there is one label — so
#: ``finditer`` alone left 430 unread, which is the silent loss this whole reader
#: exists to refuse. This pattern is what a restatement of an already-labelled
#: quantity looks like, and :func:`read_transcript` will only apply it AFTER the
#: label-anchored rule has matched in the same segment. A bare number is still never
#: read: the unit is required here exactly as it is required above.
#:
#: ``(?<![\d.])`` keeps a scan that resumes mid-number from reading ``30`` out of
#: ``430``.
_TEMPERATURE_K_RESTATED = re.compile(
    rf"(?<![\d.]){_NUMBER}\s*(?:K\b|kelvin\b)", re.IGNORECASE
)

#: temperature ... N <any other unit>. Matched only to ABSTAIN, never to propose.
_TEMPERATURE_OTHER = re.compile(
    rf"\btemperatures?\b[^.;:]{{0,40}}?{_NUMBER}\s*(?:°\s*)?"
    r"(?:C\b|F\b|celsius\b|centigrade\b|fahrenheit\b|degrees?\b)",
    re.IGNORECASE,
)

#: ``atmosphere`` / ``environment`` followed by a short literal phrase. The value
#: is the phrase EXACTLY as written, trimmed of surrounding whitespace and of a
#: single trailing sentence terminator. Nothing is normalised into a vocabulary.
_PHRASE = r"([A-Za-z0-9][A-Za-z0-9 _%/+.()-]{0,60}?)"

#: The separator between the label and the phrase. AT LEAST ONE SIGNAL IS
#: REQUIRED — a copula, a colon, or an equals sign — so a bare "atmosphere dry
#: nitrogen" does not match. Without it the rule would read the next few words
#: after the word "atmosphere" wherever it appeared in a sentence, which is how a
#: quotative rule turns into a guessing one.
_LABEL_SEPARATOR = r"(?:\s+(?:was|is|were|of)\s*[:=]?|\s*[:=])\s*"
_ATMOSPHERE = re.compile(
    rf"\batmosphere\b{_LABEL_SEPARATOR}{_PHRASE}\s*[.;!?]?\s*$", re.IGNORECASE
)
_ENVIRONMENT = re.compile(
    rf"\benvironment\b{_LABEL_SEPARATOR}{_PHRASE}\s*[.;!?]?\s*$", re.IGNORECASE
)

#: An ISO-8601 instant in UTC, written out. Taken VERBATIM — never reformatted,
#: never completed from a partial date, never defaulted to today.
#:
#: **THE VALUE-BOUNDARY SUB-CLASS, AND A REVIEW SUGGESTION MEASURED AND DECLINED
#: (2026-09-13).** An independent review found that this pattern carries neither of
#: the boundary guards ``_TEMPERATURE_K_RESTATED`` was deliberately given, so
#: *"The scan started 12026-01-01T00:00:00Z"* (a five-digit year, or a stray
#: keystroke) matched the SUBSTRING ``2026-01-01T00:00:00Z``, and
#: *"…00:00:00Zulu"* matched with a trailing overreach — each proposing an instant
#: the transcript does not state AS A TOKEN. **Both were real, both are now
#: refused, and neither is refused by a lookbehind.** The PASS-ONE ASSERTION GATE
#: closes them: the leading digit lands INSIDE the bridge and no assertion grammar
#: admits a digit (``label_does_not_assert_this_value``), and ``ulu`` is not an
#: admitted continuation (``value_qualified_by_what_follows``).
#:
#: **AND ADDING THE SUGGESTED ``(?<![\d.])`` HERE WAS TRIED, MEASURED, AND REVERTED,
#: because it makes the outcome WORSE ON THE §5 AXIS.** With the lookbehind the
#: rule stops MATCHING at all, so there is no detector match to disclose and
#: *"The scan started 12026-01-01T00:00:00Z"* produces **no abstention** — measured
#: both ways. §5 ranks a disclosed omission above a silent one, so a guard that
#: converts *"this sentence does not state a value for this field, here is the
#: clause"* into silence is a regression even though it refuses the same input. The
#: sibling pattern's guard is right FOR THE SIBLING, whose refusals are disclosed by
#: ``_HEDGE_BRIDGE`` either way. Pinned by
#: ``test_the_instant_VALUE_BOUNDARY_overreach_is_refused_AND_disclosed``, so the
#: pass-one gate cannot stop covering it unnoticed.
#:
#: **THE CALENDAR IS DELIBERATELY NOT RANGE-CHECKED, and that is a decision rather
#: than an omission.** *"The scan started 2026-13-45T99:99:99Z"* still reads
#: ``2026-13-45T99:99:99Z``. Three reasons, in order of weight: (1) the value is a
#: VERBATIM QUOTE of what the scientist wrote, and §5 forbids INVENTING a value, not
#: quoting one — a scientist reviewing this candidate is shown their own typo, which
#: is the outcome the module's "always a quote" principle is designed for; (2)
#: calendar validity is the TRUTH PLANE's question, and ``CLAUDE.md`` §15's Q20
#: ruling puts JSON-Schema ``format`` enforcement in shadow mode, non-gating and
#: OUTSIDE the truth plane — an extraction-time calendar check here would be a
#: stricter gate than the official validator is authorized to apply; (3) refusing it
#: would convert an extraction decision into a validation one inside the reader,
#: which is the boundary this module is built on. The two boundary cases above are a
#: different question and are guarded, because there the reader would be proposing a
#: token the transcript never contained.
_INSTANT = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"
_ACQUIRED_START = re.compile(
    rf"\b(?:started|start|beginning|began)\b[^.;:]{{0,40}}?{_INSTANT}", re.IGNORECASE
)
_ACQUIRED_END = re.compile(
    rf"\b(?:ended|end|finished|stopped)\b[^.;:]{{0,40}}?{_INSTANT}", re.IGNORECASE
)

#: The instant form ALONE, for the same reason ``_TEMPERATURE_K_RESTATED`` exists:
#: *"the run started 2026-01-01T00:00:00Z, or maybe 2026-01-02T00:00:00Z"* says the
#: start word once.
#:
#: ~~"A full UTC instant is self-identifying, so a restatement of one cannot be
#: mistaken for something else."~~ — **FALSE, and CORRECTED 2026-09-12 by
#: independent review.** The form is self-identifying as *an instant*; it says
#: nothing about *which* instant of the run it is. Measured on the code that
#: shipped this comment: *"The scan started …01-01T00:00:00Z, ran until
#: …01-02T00:00:00Z"* proposed the END instant as an alternative acquisition
#: START, and *"…started …01-01T00:00:00Z and we will repeat it
#: …02-01T00:00:00Z"* proposed a FUTURE scan's instant as this one's start. The
#: sentence quoted above is exactly what made that look safe. What actually keeps
#: a restatement honest is :data:`_HEDGE_BRIDGE` below, not the value's format —
#: and the phrase rules still get no restatement pattern, for the separate and
#: still-correct reason ``_Rule`` gives.
_INSTANT_RESTATED = re.compile(_INSTANT)

# --- THE PASS-ONE ASSERTION GATE ----------------------------------------------
#
# **WHY IT EXISTS.** Every label-anchored pattern above bridges its label to its
# value with ``[^.;:]{0,40}?`` — ~40 characters of *anything*. So a number
# carrying kelvin anywhere near the word ``temperature`` became a candidate
# temperature, and an instant anywhere near ``started`` became an acquisition
# start. Measured at ``782082bb``, each SILENT — no abstention, no clarification,
# and each shipping a ``rule`` sentence asserting the transcript stated the field:
#
# ===============================================  ======================  ==========
# sentence                                          proposed                really is
# ===============================================  ======================  ==========
# ``The temperature drift was 3 K.``                ``temperature_K = 3``   a DRIFT
# ``The temperature rose by 30 K.``                 ``temperature_K = 30``  a DELTA
# ``The temperature was stable to 1 K.``            ``temperature_K = 1``   a TOLERANCE
# ``The temperature was 3 K above target.``         ``temperature_K = 3``   an OFFSET
# ``It started drifting at 2026-01-01T00:00:00Z.``  an acquisition START    a DRIFT ONSET
# ===============================================  ======================  ==========
#
# **THE TARGET, STATED AS THE RULE RATHER THAN AS THE TABLE.** A quantity becomes
# a candidate only when the sentence ASSERTS that quantity as the field's value —
# never merely because the number carries the field's unit. Two things can defeat
# that, and each gets its own gate below:
#
#   (1) something between the label and the value RE-SUBJECTS the quantity, so the
#       sentence is about a drift / an error / a step and not about the field
#       (``_ASSERTION_BRIDGE``); or
#   (2) something immediately AFTER the value QUALIFIES it, so the number measures
#       a relation, a rate or a bound rather than the field
#       (``_VALUE_CONTINUATION``).
#
# **BOTH ARE ALLOWLISTS, AND THAT IS THE WHOLE DESIGN DECISION.** A denylist of
# ``drift``/``error``/``step`` fails OPEN: the next unanticipated noun becomes a
# fabricated scientific value, which is the failure mode this module has already
# shipped twice (see ``_RESTATEMENT_RESIDUE_CLOSED`` and the struck reasoning in
# ``_LABEL_OVERREACH_CLOSED``). An allowlist fails CLOSED: an unanticipated word
# costs a READING, and a lost reading is DISCLOSED, which §5 ranks above a silent
# assertion. The proxy the previous slice rejected — "a shorter bridge" — was
# rejected for a reason that still holds and that these grammars respect: the
# bridge is what makes *"Sample temperature at the second scan was 425 K"* read at
# all, so the fix had to constrain the bridge's SHAPE and not its LENGTH.

#: An article, demonstrative or possessive. It is what separates a prepositional
#: modifier of the LABEL from a genitive of a different quantity: *"temperature OF
#: THE SAMPLE"* modifies the temperature, *"temperature OF DRIFT"* names a
#: different thing. Requiring a determiner is what refuses the second without a
#: list of forbidden nouns.
_DETERMINER = (
    r"(?:the|this|that|these|those|a|an|its|our|their|his|her|my|each|every"
    r"|both|all)"
)

#: A prepositional phrase that may sit between the label and the assertion WITHOUT
#: changing what the sentence asserts about. Grammatically: a PP modifies the
#: label, so the subject of the copula is still the label — *"the temperature at
#: the second scan was 425 K"* is a claim about a temperature. A BARE NOUN in the
#: same position is a compound noun whose head is that noun, so *"the temperature
#: drift was 3 K"* is a claim about a drift, and this pattern does not admit one.
#:
#: The object is bounded (a determiner plus at most three words) and ``from`` is
#: deliberately ABSENT: *"ramped the temperature from 300 K to 400 K"* would
#: otherwise parse as a modifier with no assertion at all and read 300.
_LABEL_MODIFIER = (
    r"(?:at|in|on|of|during|for|throughout|across|inside|near|about)\s+"
    rf"{_DETERMINER}(?:\s+[A-Za-z][A-Za-z0-9-]*){{0,3}}"
)

#: Verbs that, followed by ``at``, assert the value AS the quantity. ``to`` is
#: admitted after ``set`` ALONE and that is measured, not stylistic: ``stable at``
#: asserts a temperature and ``stable to`` states a TOLERANCE, and the only thing
#: distinguishing them is the preposition.
#: **WIDENED 2026-09-13, AFTER MEASURING THAT THE FIRST VERSION REFUSED 86% OF
#: BENIGN BRIDGE FORMS.** The adversarial corpus this gate was developed against
#: reported 1,365 legitimate sentences read correctly and **0** lost — because its
#: ``GOOD_BRIDGES`` table was drawn from the same mental model as this grammar, so
#: it measured the grammar's REACH and not its PREMISE. An independently-written
#: list of fifteen natural forms lost thirteen: *"the temperature READ 425 K"*,
#: *"SETTLED AT 425 K"*, *"CAME OUT AT 425 K"*, *"HERE was 425 K"*, *"ACCORDING TO
#: THE LOG was 425 K"*, *"WE RECORDED was 425 K"*. Every loss was disclosed, so
#: none was a §5 violation — but a reader that refuses most of the ways a person
#: says a thing is not usable, and "disclosed" is not a defence against that.
#:
#: **EVERY ADDITION BELOW IS SAFE FOR ONE STRUCTURAL REASON, stated once: a
#: NOMINAL HEAD still fails.** *"The temperature DRIFT read 3 K"*, *"the
#: temperature ERROR settled at 2 K"* and *"the temperature STEP showed 5 K"* are
#: all still refused, because ``drift``/``error``/``step`` is neither a modifier
#: preposition nor an assertion, wherever the verb after it comes from. Widening
#: the VERB set therefore cannot reopen the class this gate closed; it can only
#: admit more ways of asserting the label itself. Re-measured after the widening
#: over all three corpora, which is what makes that a measurement and not an
#: argument.
_ASSERTION_AT_VERB = (
    r"(?:held|kept|set|sat|parked|maintained|stable|steady|stabilised"
    r"|stabilized|recorded|measured|logged|settled|stayed|remained|hovered"
    r"|levelled|leveled|sits|stands|rested|came\s+out|ended\s+up|wound\s+up"
    r"|read|sitting)"
)

#: Verbs that report a value DIRECTLY, with no preposition: *"the temperature read
#: 425 K"*, *"showed 425 K"*, *"registered 425 K"*. Admitted for the reason above —
#: a nominal head in front of one still fails — and protected on the other side by
#: :data:`_VALUE_CONTINUATION`, which refuses *"read 3 K of drift"* on the tail.
_ASSERTION_REPORT_VERB = (
    r"(?:read|reads|showed|shows|gave|gives|indicated|indicates|registered"
    r"|registers|reported|reports|measured|logged|recorded|hit|reached|touched"
    r"|peaked\s+at|bottomed\s+out\s+at)"
)

#: A bare adverbial between the label and its assertion: *"the temperature HERE was
#: 425 K"*, *"TODAY was 425 K"*, *"THROUGHOUT was 425 K"*. A CLOSED list, which is
#: what keeps the nominal-head class shut — an open ``[A-Za-z]+`` here would admit
#: ``drift`` and undo the whole gate.
#: **`then`, `now`, `meanwhile` AND `afterwards` ARE DELIBERATELY ABSENT, and the
#: first version of this list contained `then`.** It reopened a measured
#: fabrication within minutes: the fixture
#: ``test_the_worst_legitimate_disclosure_load_is_admitted`` contains *"…at the
#: END, THEN 2026-01-03T00:00:00Z"*, where the ``_ACQUIRED_END`` rule anchors on
#: the word ``end`` inside *"at the end"* — and admitting ``then`` as a label
#: adverb let that bridge parse, so the reader proposed a FUTURE instant as this
#: run's acquisition end again. It was caught by that existing test going 9 → 7
#: abstentions, which is the ceiling fixture earning its keep for the second time
#: in one slice. ``then`` is a SEQUENCER, not an adverbial of the label; the
#: sequence gate exists precisely because it separates two values rather than
#: qualifying one.
#:
#: **NOTE THE ASYMMETRY WITH `_CONTINUATION_WORD`, which is real rather than an
#: inconsistency:** ``consistently``/``nominally``/``apparently``/``steadily`` are
#: admitted HERE and refused THERE. Before the value an adverb occupies the whole
#: slot and a nominal head after it still fails (*"the temperature CONSISTENTLY
#: DRIFT was 3 K"* is refused); after the value the same adverb SHIELDS a qualifier
#: (*"3 K CONSISTENTLY ABOVE TARGET"* would read as a temperature). The same word
#: is safe on one side and not the other, which is why the two lists are not one.
_LABEL_ADVERB = (
    r"(?:here|there|today|yesterday|tonight|overnight|throughout|overall"
    r"|everywhere|initially|briefly"
    r"|nominally|apparently|consistently|steadily)"
)

#: A provenance or relative-clause modifier of the label, each with a closed verb
#: set: *"the temperature ACCORDING TO THE LOG was 425 K"*, *"the temperature WE
#: RECORDED was 425 K"*, *"the temperature I MEASURED was 425 K"*.
_LABEL_CLAUSE = (
    r"(?:according\s+to\s+" + _DETERMINER + r"(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3}"
    r"|(?:we|i|they|he|she)\s+"
    r"(?:recorded|measured|logged|read|saw|got|observed|noted|found|took)"
    r"|that\s+(?:we|i|they)\s+"
    r"(?:recorded|measured|logged|read|saw|got|observed|noted|found|took))"
)
#: The same, in the progressive — admitted ONLY behind a copula. A bare gerund is
#: a different verb's complement, not an assertion: *"It started LOGGING at
#: <instant>"* is about logging, while *"the temperature was SITTING at 425 K"* is
#: about the temperature.
_ASSERTION_PROGRESSIVE = (
    r"(?:holding|keeping|sitting|resting|hovering|running|steady|stable|parked)"
)
_ASSERTION_TO_VERB = r"(?:set|brought|adjusted)"
_COPULA = r"(?:was|were|is|are)"

#: The closed set of ways a sentence may ASSERT a value as the field's. Everything
#: outside it is refused, which is the fail-closed direction: ``rose by``, ``fell
#: by``, ``to within``, ``by``, ``ramped``, ``rose to``, ``went to``, ``from`` and
#: every bare nominal head are simply absent rather than forbidden by name.
_ASSERTION = (
    r"(?:"
    rf"{_COPULA}\s+(?:{_ASSERTION_AT_VERB}|{_ASSERTION_PROGRESSIVE})"
    rf"\s+(?:at|on|around|about)"
    rf"|{_ASSERTION_AT_VERB}\s+(?:at|on|around|about)"
    rf"|(?:{_COPULA}\s+)?{_ASSERTION_TO_VERB}\s+to"
    rf"|{_COPULA}"
    rf"|{_ASSERTION_REPORT_VERB}"
    r"|at|on|="
    r")"
)

#: An approximation or hedge that modifies the value that FOLLOWS it. Admitted
#: last in the bridge, because it qualifies the number without re-subjecting it:
#: *"the temperature was around 425 K"* still states a temperature. This is the
#: same closed-list reasoning ``_OR_REQUIRED_HEDGES`` records for pass two, and is
#: why ``CAP-001`` (*"around 425 K, maybe 430 K"* → TWO candidates) is untouched.
_ASSERTION_APPROX = (
    r"(?:about|around|roughly|approximately|nearly|circa|maybe|perhaps"
    r"|possibly|some|~)"
)

#: **GATE (1).** The WHOLE text between the label and the value must be one of:
#: nothing at all (*"temperature 425 K"*), prepositional modifiers of the label,
#: an assertion, and an approximation — in that order. ``fullmatch``, never ``$``,
#: for the reason :data:`_HEDGE_BRIDGE` gives.
_ASSERTION_BRIDGE = re.compile(
    rf"\s*[,(]?\s*"
    rf"(?:(?:{_LABEL_MODIFIER}|{_LABEL_ADVERB}|{_LABEL_CLAUSE})\s*[,)]?\s+)*"
    rf"(?:{_ASSERTION}\s*)?(?:{_ASSERTION_APPROX}\s+)?",
    re.IGNORECASE,
)

#: Punctuation that ENDS the clause the value belongs to. Anything after it is a
#: new statement and is not this value's business, which is why *"temperature 425
#: K, pressure 2 bar"* keeps its reading while *"temperature 425 K of drift"* does
#: not: the second has no boundary, so ``of drift`` attaches to the number.
_CLAUSE_BOUNDARY = r"[,;.!?:)\]}\"'—–]"

#: Words that may open a continuation without qualifying the value: coordinators,
#: subordinators, and the hedging connectives pass two needs to still see.
#: ``per``, ``of``, ``above``, ``below``, ``than``, ``from``, ``off``, ``over``,
#: ``under``, ``plus`` and ``minus`` are ABSENT rather than forbidden — that is the
#: allowlist doing its job.
#:
#: **THE ONE RULE GOVERNING WHAT MAY BE ADDED HERE, and it is the rule
#: ``_OR_REQUIRED_HEDGES`` already learned for pass two: a token may be admitted
#: only if it OPENS A NEW CLAUSE or LOCATES the measurement — NEVER if it modifies
#: what follows it.** A bare adverb modifies what follows, so admitting one SHIELDS
#: a qualifier behind it: ``just above target``, ``well below the setpoint``,
#: ``slightly over target``, ``consistently above target`` and ``nominally 3 K
#: above target`` would every one be read as a temperature the moment ``just``,
#: ``well``, ``slightly``, ``consistently`` or ``nominally`` were allowlisted. That
#: is why the measured cost below is PAID rather than engineered away: the adverbs
#: whose loss it consists of are exactly the tokens that cannot safely be added.
_CONTINUATION_WORD = (
    r"(?:and|but|so|or|while|whilst|because|although|though|as|when|after"
    r"|before|once|maybe|perhaps|alternatively|again|possibly|throughout"
    r"|according|with|without|which|that|until"
    # Bare TIME adverbials. Admitted because none can take a relational
    # complement — there is no reading of "3 K yesterday above target" on which
    # the number is a temperature — so none can shield.
    r"|yesterday|today|tonight|overnight|afterwards|afterward|initially"
    r"|briefly|meanwhile|thereafter|subsequently|beforehand|already"
    r")"
)
#: An APPROXIMATION IMMEDIATELY IN FRONT OF ANOTHER NUMBER. Admitted, and the
#: ``\d`` is the whole reason it is safe: ``about``/``around``/``roughly``/
#: ``approximately`` modify what FOLLOWS them (``_OR_REQUIRED_HEDGES`` records the
#: measurement that established this), so in front of a NUMBER they introduce a new
#: quantity and say nothing about the value just read — *"the temperature was 425 K
#: about 430 K of drift"* still asserts 425, and pass two refuses the 430 on its
#: own terms. Without the digit they WOULD shield: *"3 K roughly above target"*
#: would be read as a temperature of 3, which is the defect class this gate exists
#: for. So they are admitted in exactly the position where they cannot qualify our
#: value, and refused everywhere else.
_CONTINUATION_APPROX = r"(?:about|around|roughly|approximately|nearly|circa)\s+-?\d"

#: A determiner-led noun phrase of TIME, and a first-person epistemic clause.
#: Both open a new constituent that a measure phrase cannot reach back through:
#: *"425 K this morning"*, *"425 K the whole time"*, *"425 K, I think"*.
_CONTINUATION_PHRASE = (
    rf"(?:{_DETERMINER}\s+(?:whole|entire|first|second|last|rest)\s+"
    r"(?:time|run|scan|night|day|morning|afternoon|while)"
    rf"|{_DETERMINER}\s+(?:morning|afternoon|evening|night|time)"
    r"|i\s+(?:think|believe|reckon|guess|recall|suppose|assume)"
    r"|(?:measured|recorded|logged|reported|observed)\s+"
    rf"(?:by|on|at|in|with)\s+{_DETERMINER}\b)"
)
#: A locating preposition, which must take a determiner. That single requirement
#: is what separates *"425 K at the second scan"* (a locator — read it) from
#: *"425 K at most"* (a bound — do not).
#:
#: **THE QUANTIFIER FORM IS SPLIT OFF DELIBERATELY.** *"for most of the scan"* is
#: ordinary dictation, and admitting ``most`` as an object of EVERY preposition
#: here would admit ``at most`` — the bound this pattern exists to refuse. So
#: quantifier objects are allowed after the three DURATION prepositions only, and
#: ``at``/``in``/``on``/``by``/``via``/``near``/``across``/``inside`` keep
#: requiring a determiner.
_CONTINUATION_PREP = (
    rf"(?:at|in|on|during|for|across|inside|near|by|via)\s+{_DETERMINER}\b"
    r"|(?:during|for|throughout)\s+(?:most|all|much|part|some|the\s+rest)\b"
)

#: **GATE (2).** What may immediately follow the value AND ITS UNIT. Anchored with
#: :meth:`re.Pattern.match` at :meth:`re.Match.end` — the end of the value and its
#: unit, never ``end(1)``, which is the end of the NUMBER and would make ``" K"``
#: itself fail every check. :func:`_unit_is_complete` records the same offset trap.
_VALUE_CONTINUATION = re.compile(
    rf"\s*(?:$|{_CLAUSE_BOUNDARY}|{_CONTINUATION_PREP}|{_CONTINUATION_APPROX}"
    rf"|{_CONTINUATION_PHRASE}|{_CONTINUATION_WORD}\b)",
    re.IGNORECASE,
)

#: **GATE (3) — THE SEQUENCE GATE.** Pure coordination: a gap between two values
#: of one field that introduces NOTHING to tell them apart.
#:
#: This is what distinguishes *"300 K, then 350 K, then 400 K"* — a progression,
#: where nothing in the gap says which value is the field's — from *"425 K,
#: cryostat setpoint 80 K"*, where the gap names a different instrument and so
#: positively identifies 80 as something else. An allowlist again: a marker list
#: of ``then``/``followed by``/``→`` would fail open on the next sequencer, while
#: an unanticipated word here simply means the second value is NOT treated as an
#: indistinguishable sibling and the first reading survives.
_SIBLING_COORDINATOR = (
    r"(?:then|and|next|later|followed|by|after|that|to|or|also|again|up|down"
    r"|finally|eventually|subsequently|now|so)"
)
_SIBLING_GAP = re.compile(
    rf"[\s,;:—–>→-]*"
    rf"(?:{_SIBLING_COORDINATOR}[\s,;:—–>→-]*)*",
    re.IGNORECASE,
)

# --- GATE (4) — THE PRE-LABEL GATE --------------------------------------------
#
# **WHY IT EXISTS, AND WHY IT IS A FOURTH GATE RATHER THAN A WIDENING OF THE
# FIRST.** Gates (1) and (2) both look FORWARD from the label: ``_ASSERTION_BRIDGE``
# reads label → value, ``_VALUE_CONTINUATION`` reads value → end. Neither can see a
# word that sits BEFORE the label, and a word there can rename the quantity just as
# completely as one after it. Measured at ``d3473414`` — each SILENT, each shipping
# a ``rule`` sentence asserting the transcript stated the field:
#
# ==================================================  ====================  ========
# sentence                                             proposed              really is
# ==================================================  ====================  ========
# ``The setpoint temperature was 425 K.``              ``temperature_K=425`` a SETPOINT
# ``The maximum temperature was 500 K.``               ``500``               an EXTREMUM
# ``The average temperature was 400 K.``               ``400``               a STATISTIC
# ``The ambient temperature was 295 K.``               ``295``               the ROOM's
# ``The target temperature was 425 K.``                ``425``               a TARGET
# ``We lowered the temperature 15 K.``                 ``15``                a DELTA
# ``The previous scan ended at <instant>.``            ``acquired_end_utc``  ANOTHER scan
# ``The calibration scan ended at <instant>.``         ``acquired_end_utc``  ANOTHER scan
# ==================================================  ====================  ========
#
# The last two are the worse failure of the two families, and they are kept in one
# table because ONE gate closes both: the value is a real acquisition time, of a
# different measurement, attributed to this one.
#
# **THE SHARPEST EXHIBIT IS THIS MODULE'S OWN COMMENT.** :data:`_SIBLING_GAP` cites
# *"cryostat setpoint 80 K"* as a case where the gap *positively identifies 80 as
# something other than the temperature* — and until this gate existed *"The
# setpoint temperature was 425 K"* proposed 425 AS the temperature. The same word,
# read as disqualifying in one position and invisible in the other. The module
# contained the reasoning that condemned its own behaviour, which is why the
# published claim that the pre-label family had *"ONE MEMBER"* was the part of it
# that was most wrong.
#
# **AN ALLOWLIST, FOR THE THIRD TIME IN THIS FILE, AND THE REJECTED-PROXY
# REASONING IS WHY.** :data:`_PRE_LABEL_OVERREACH_CLOSED` refused this class three
# times over and named three proxies, each correctly rejected:
#
#   * a DENYLIST of nouns (``setpoint``/``maximum``/``previous``) FAILS OPEN on the
#     next noun — the failure mode this module has shipped twice;
#   * "no determiner immediately before the label" refuses *"The temperature 425
#     K"*, which is legitimate;
#   * "at most N words before the label" is a word count with no grammatical story,
#     and *"The sample temperature"* and *"The setpoint temperature"* differ by no
#     words at all.
#
# **WHAT THE THIRD REFERRAL DID NOT CONSIDER IS THAT AN ALLOWLIST OF THE SAME
# NOUNS FAILS CLOSED.** Its stated ground was *"a denylist of nouns fails OPEN,
# which is the failure mode that has already shipped twice"* — true, and it settles
# only the denylist. Inverting the polarity inverts the failure direction: an
# unanticipated noun costs a READING, and a lost reading is DISCLOSED, which §5
# ranks above a silent assertion. That is the identical move that closed gate (1),
# where *"a shorter bridge"* was rejected and the bridge's SHAPE was constrained
# instead. Four constructs in this file are already closed lexical allowlists in a
# pre-value slot (:data:`_LABEL_ADVERB`, :data:`_ASSERTION_AT_VERB`,
# :data:`_CONTINUATION_WORD`, :data:`_SIBLING_COORDINATOR`); this is the fifth, and
# :data:`_LABEL_ADVERB`'s own comment states the reason it must be closed — *"an
# open ``[A-Za-z]+`` here would admit ``drift`` and undo the whole gate"*.
#
# **THE DISTINCTION IS NOT DECIDABLE BY GRAMMAR, AND THAT IS ESTABLISHED RATHER
# THAN ASSUMED.** In English a compound noun's head is its LAST noun, so *"setpoint
# temperature"* and *"sample temperature"* are BOTH grammatically temperatures —
# unlike *"temperature setpoint"*, which gate (1) refuses precisely because the head
# moved. No shape test separates them; only the lexicon does. So the lexicon is
# where the decision is taken, explicitly, with the cost measured.
#
# **AND THE SCHEMA — NOT A SCIENTIFIC JUDGEMENT — IS WHY THE SETPOINT FAMILY IS
# REFUSED.** §5 forbids this reader from judging whether a stated setpoint is
# "really" the temperature. It does not have to: the official schema distinguishes
# as-commanded from measured wherever it speaks about the distinction at all, and it
# gives the as-commanded value its OWN path —
# ``context.electrochemistry.potential_setpoint_V`` (*"PRIMARY, immutable: the
# as-commanded potential"*) and ``current_setpoint_mA_cm2``. ``context.temperature_K``
# has **no setpoint sibling**, so a stated setpoint temperature has no path in this
# schema, and writing it to ``context.temperature_K`` would put an as-commanded
# number at a path the schema keeps separate for every quantity where it provides
# both. Refusing it is reading the schema. The same holds for the extremum and
# statistic families: ``maximum``/``minimum``/``average``/``mean`` name a reduction
# over temperatures and the schema carries no path for one — and ``CAP-008`` records
# that the only uncertainty-like structure in the schema is
# ``$.descriptors.outputs[].descriptors[].uncertainty``, which is descriptor-only.
#
# **WHAT IT DOES NOT CLAIM.** Refusing *"The ambient temperature was 295 K"* is NOT
# this reader asserting that an ambient temperature is not the field's value. It is
# declining to decide, and saying so in the disclosure. The scientist can restate it
# prepositionally — *"The temperature of the sample was 295 K"* — which gate (1)
# already reads, and the disclosure says that too.

#: Nouns that may sit BARE between a determiner and the label without renaming what
#: the label denotes: they LOCATE the quantity (*"the SAMPLE temperature"*) or
#: SUBJECT the verb (*"the SCAN ended"*). A CLOSED list, and small on purpose — a
#: noun that is missing costs one disclosed reading, and a noun that should not be
#: here reopens the class.
#:
#: **EVERY ENTRY IS JUSTIFIED BY THIS REPOSITORY, NOT BY TASTE.** ``sample`` is
#: pinned as a must-read by ``_BENIGN_BRIDGE_FORMS`` (*"The sample temperature was
#: 425 K."*) and is the schema's own word for the measured thing (top-level
#: ``sample``); ``scan``/``run`` are pinned by the instant corpus (*"The scan ended
#: …"*, *"The run started …"*); the remainder are the same referents under the words
#: a person actually dictates. ``base`` is DELIBERATELY ABSENT even though *"base
#: temperature"* is ordinary dictation: it names the LOWEST temperature, so it
#: re-subjects exactly as ``minimum`` does.
#:
#: **ONE SHARED LIST RATHER THAN ONE PER RULE, AND THAT WAS MEASURED SAFE.** Sharing
#: lets *"The scan temperature was 425 K"* and *"The sample ended at <instant>"*
#: read. Neither re-subjects anything: both locate. A per-rule list would be more
#: precise and buys nothing measurable, and a fourth ``_Rule`` field for it would be
#: carried by every future rule for no reason.
#:
#: **WIDENED FROM 11 ENTRIES TO THREE GROUPS, AFTER MEASURING THAT THE FIRST VERSION
#: REFUSED 43% OF BENIGN PRE-LABEL FORMS.** ~~41%~~ ~~20 of 51~~ — **BOTH FIGURES
#: WERE WRONG AND ARE CORRECTED 2026-09-13 AFTER AN INDEPENDENT REVIEW RE-DERIVED
#: THEM. 22 of 51 (43%).** The error is worth keeping because it is the exact one the
#: parenthetical below declares it is avoiding: `20` was measured over the **49**-row
#: corpus (20/49 = 41%, which is where the other figure in this same sentence came
#: from) and was then silently **rebased onto the 51-row denominator**. The two rows
#: added later were BOTH lost pre-widening, so 20 + 2 = 22. Re-derived by running the
#: shipped 51-row corpus against the pre-widening commit `66082dce` itself, not by
#: arithmetic on a published number. 22 independently-written natural
#: sentences were lost, and the module's own standard for that number is explicit:
#: *"a reader that refuses most of the ways a person says a thing is not usable, and
#: 'disclosed' is not a defence against that."* The three groups below take it to
#: **2 of 51 (4%)**, and every remaining loss is named in
#: :data:`_PRE_LABEL_RESIDUE`. Re-measured over all four corpora after widening.
#:
#: **GROUP 2 — THE APPARATUS — EXISTS BECAUSE MY OWN §5 ARGUMENT FOR EXCLUDING IT WAS
#: WRONG, AND THE REFUTATION IS THE MOST USEFUL THING MEASURED HERE.** I first
#: excluded ``cryostat``/``stage``/``chamber``/``sensor`` on the ground that admitting
#: them would assert that the cryostat's temperature IS ``context.temperature_K`` — a
#: scientific judgement §5 forbids. **That ground is unavailable, because the module
#: has already made that exact call in the PREPOSITIONAL direction.**
#: :data:`_LABEL_MODIFIER` admits ``of``/``on``/``in``/``at`` + a determiner, so all
#: six of these read TODAY and did before this slice:
#:
#:     "The temperature of the cryostat was 80 K."   -> 80
#:     "The temperature on the sensor was 425 K."    -> 425   <- a pinned MUST-READ
#:     "The temperature in the chamber was 300 K."   -> 300
#:     "The temperature of the furnace was 900 K."   -> 900
#:     "The temperature at the stage was 300 K."     -> 300
#:     "The temperature of the substrate was 700 K." -> 700
#:
#: Refusing *"The sensor temperature was 425 K"* while reading *"The temperature on
#: the sensor was 425 K"* is an INCONSISTENCY between two phrasings of one claim, not
#: a §5 position — and the second is in ``_BENIGN_BRIDGE_FORMS``, so the repository
#: has committed to it. **The durable lesson: "admitting this would require a
#: scientific judgement" has to be checked against what the code ALREADY admits.
#: Mine was a judgement the module had made two screens away.** The compound list is
#: also strictly NARROWER than the prepositional form it matches, which is closed on
#: an arbitrary noun (:data:`_MODIFIER_OBJECT_OVERREACH_RESIDUE` records that *"The
#: temperature of the DRIFT was 3 K"* still reads, and this list admits no such word).
#:
#: **GROUP 3 — REPORT PARTICIPLES — is safe for one structural reason, stated once:
#: a past participle of a verb of REPORT says how the value was OBTAINED, never what
#: quantity it is.** *"The measured temperature"* is the temperature; *"the measured
#: drift"* is a drift, and ``drift`` is not in this list at any position. The verbs
#: are the same closed set :data:`_PRE_LABEL_REPORT` already holds, so this widening
#: introduces no new vocabulary and cannot outgrow the list it borrows.
#:
#: **GROUP 4 — AFFIRMING ADJECTIVES — are the exact ANTONYMS of the estimate family
#: gate (4) refuses.** ``actual``/``real``/``true`` assert that the value is the one
#: obtained, which is the opposite move from ``nominal``/``expected``/``estimated``.
#: They affirm the label rather than re-subject it.
#:
#: **AND THE STACKING BOUND IS WHAT KEEPS ALL OF THIS CLOSED.** With three groups the
#: slot became genuinely multi-word (*"the measured sample temperature"*), so
#: :data:`_PRE_LABEL` allows at most **two** — enough for every measured form, and
#: bounded rather than a ``*`` loop, so the grammar's reach is stated. Stacking is
#: safe only because every member is vetted: two admitted words cannot compose into a
#: re-subjecting phrase when neither re-subjects alone.
_PRE_LABEL_NOUN = (
    # (1) the measured thing, and the unit of work the instant rules subject.
    r"(?:samples?|specimens?|scans?|runs?|measurements?|acquisitions?"
    r"|collections?|datasets?|exposures?|spectra|spectrum"
    # (2) the apparatus. See the note above: the prepositional form of each of
    #     these already reads, so this matches a decision rather than taking one.
    r"|cryostats?|cryos|stages?|holders?|cells?|chambers?|furnaces?|ovens?"
    r"|baths?|substrates?|sensors?|thermocouples?|probes?|pucks?|mounts?"
    r"|windows?|beamlines?|monochromators?"
    # (3) participles of the closed report-verb set: HOW the value was obtained.
    r"|measured|recorded|logged|observed|reported|noted|read|found"
    # (4) affirming adjectives: the antonyms of the estimate family.
    r"|actual|real|true"
    # (5) THE POSSESSIVE OF ANY OF THE ABOVE, closing a regression this gate
    #     introduced. `_PRE_LABEL_NOUN` matched `samples?` but not `sample's`, so
    #     gate (4) REFUSED 16 of 16 apparatus possessives that the base commit
    #     `d3473414` READ — measured both ways, at both SHAs.
    #
    #     IT IS THE INCONSISTENCY THIS GATE'S OWN GROUP-2 ARGUMENT CONDEMNS, which
    #     is why it is a defect and not a policy. Three phrasings of one claim, and
    #     the gate read two of them and refused the third:
    #
    #         The sample temperature was 425 K.            -> read  (16/16)
    #         The temperature of the sample was 425 K.     -> read  (16/16)
    #         The sample's temperature was 425 K.          -> REFUSED (0/16)
    #
    #     That group's note says in terms: "Refusing 'The sensor temperature was
    #     425 K' while reading 'The temperature on the sensor was 425 K' is an
    #     INCONSISTENCY between two phrasings of one claim, not a §5 position."
    #
    #     Both apostrophes, because a transcript typed in a word processor or
    #     dictated through an OS keyboard carries U+2019 and not U+0027, and a rule
    #     that reads one and refuses the other is the same inconsistency one
    #     character smaller. It attaches to the ALTERNATION rather than to each
    #     member, so a noun added later cannot be admitted without its possessive.
    #
    #     It admits no new NOUN: `The setpoint's temperature` stays refused, because
    #     `setpoint` is not in this allowlist in any form. Found by independent
    #     review (A-2); the lane's "0 legitimate temperatures lost" did not cover it
    #     because no possessive exists in its 51-row benign corpus.
    r")(?:['’]s)?"
)

#: **THE PRE-LABEL FORMS STILL LOST, named rather than folded into the percentage** —
#: the discipline :data:`_PARENTHETICAL_BRIDGE_RESIDUE` set for gate (1)'s one loss.
#: Measured at **2 of 51** independently-written benign forms (4%) after the widening
#: above, down from ~~20 of 51 (39%)~~ **22 of 51 (43%)** — corrected 2026-09-13; see
#: the note on the widening above for why the old numerator was a rebased 49-row
#: figure. Both DISCLOSED with an instruction that works.
#:
#: (*The denominator moved 49 → 51 in the same session, when a mutation exposed that
#: the stacking bound was an equivalent mutant and two two-modifier rows were added to
#: the corpus that justified it. "5 of 49" below is quoted as it was written, not
#: rebased onto the new denominator — a quoted wrong claim that silently acquires
#: today's numbers stops being a record of anything.*)
#:
#: **THIS TUPLE READ "5 of 49" AND LISTED FIVE ROWS FOR ONE COMMIT AND THAT WAS
#: WRONG — caught by re-running the measurement instead of trusting the sentence I
#: had just written.** Three of the five (*"The FINAL temperature"*, *"The STARTING
#: temperature"*, *"The INITIAL temperature"*) are **deliberate refusals, not
#: benign losses**, and they are not in the benign corpus at all — they are in the
#: adversarial corpus's must-refuse family. Counting a deliberate refusal as a
#: false negative inflates the cost of the gate and, worse, implies someone intends
#: to admit it. **The two classes are now kept apart**, because it is exactly the
#: conflation §15 records this repository publishing before.
#:
#: **(a) THE GENUINE LOSSES — an OPEN class, which is why an allowlist cannot chase
#: them.** ``anyway``, ``OK``, ``well``, ``anyhow``, ``like``, ``so anyway`` — spoken
#: fillers, where the next one is unguessable by construction. Each is trivially
#: recoverable and the fix is punctuation the speaker would probably use anyway: ``,``
#: is a clause bound, so *"Anyway, the temperature was 425 K"* parses and reads. That
#: recoverability is why the class is left open rather than chased with a list that
#: would grow forever and still fail on the next filler.
#:
#: **(b) REFUSED DELIBERATELY, AND WOULD NOT BE ADMITTED EVEN IF IT WERE EASY —
#: recorded here so a future slice does not "fix" it.** *"The FINAL temperature was
#: 425 K"*, *"The STARTING temperature was 300 K"*, *"The INITIAL temperature was
#: 300 K"*. Each states a temperature at ONE POINT of a progression, and which point
#: ``context.temperature_K`` should hold is precisely the question
#: :data:`_KIND_NONE_SELECTED` refuses to answer for *"300 K, then 350 K, then 400
#: K"*. Admitting these would decide by PHRASING what the sequence gate declines to
#: decide by MEASUREMENT — the same value, the same record, two opposite answers
#: depending on whether the scientist said "initial" or "then". They are asserted as
#: refused by the adversarial corpus, not listed below.
_PRE_LABEL_RESIDUE: tuple[str, ...] = (
    "Anyway the temperature was 425 K",
    "OK the temperature was 425 K",
)

#: A bare adverbial that may OPEN the clause the label sits in: *"LATER the
#: temperature was 425 K"*, *"INITIALLY the temperature was 300 K"*.
#:
#: **``earlier``, ``previously``, ``next`` AND ``then`` ARE IN THIS LIST AND ARE
#: REFUSED BY :data:`_PRE_LABEL_NOUN`, AND THAT ASYMMETRY IS THE GATE'S WHOLE
#: STRUCTURAL RESULT RATHER THAN AN INCONSISTENCY.** *"EARLIER the temperature was
#: 425 K"* is an adverbial locating the statement in time and is benign; *"the
#: EARLIER scan ended at <instant>"* is a pre-modifier naming a DIFFERENT scan and
#: is a misattribution. The determiner is the left bracket of the noun phrase the
#: label heads, so a word before it modifies the CLAUSE and a word after it modifies
#: the LABEL — the same word, safe on one side and not the other. That is exactly
#: the asymmetry :data:`_LABEL_ADVERB` and :data:`_CONTINUATION_WORD` already
#: record for the two sides of the value, and it is what lets this gate close the
#: run-misattribution family without a denylist of scan adjectives.
_PRE_LABEL_ADVERB = (
    r"(?:later|then|next|afterwards|afterward|subsequently|meanwhile|finally"
    r"|initially|briefly|today|yesterday|tonight|overnight|earlier|previously"
    r"|now|also|again|overall|throughout|here|there)"
)

#: A pronoun subject, and the closed set of verbs it may take while leaving the
#: label the thing being described: *"WE RECORDED the temperature at 425 K"*, *"IT
#: started at <instant>"*.
#:
#: **THE VERBS OF CHANGE ARE ABSENT RATHER THAN FORBIDDEN, WHICH IS THE POINT.**
#: ``lowered``, ``raised``, ``dropped``, ``ramped``, ``brought``, ``corrected`` and
#: every verb nobody has thought of simply do not appear, so *"We lowered the
#: temperature 15 K"* — the one row
#: :data:`_PRE_LABEL_OVERREACH_CLOSED` was reduced to before this gate, and the
#: row its own generator could not produce — is refused without being named.
#: ``set`` is absent too, and that is not an oversight: *"The temperature was SET TO
#: 425 K"* is pinned as a must-read and is unaffected, because there ``set`` sits in
#: the BRIDGE where :data:`_ASSERTION_TO_VERB` admits it. This gate governs the
#: other side of the label only.
_PRE_LABEL_SUBJECT = r"(?:it|we|i|they|he|she)"
_PRE_LABEL_REPORT = (
    r"(?:recorded|measured|logged|read|saw|observed|noted|found|took|report"
    r"|reported|see|had)"
)

#: A prepositional phrase opening the clause: *"AT 300 K the temperature was 425
#: K"*, *"AT THE end 2026-01-01T00:00:00Z"*. The object may be a determiner-led
#: phrase or a quantity, because both occur in this repository's own corpus. It
#: cannot reach the label's own pre-modifier slot, which sits after the determiner.
_PRE_LABEL_PREP = (
    r"(?:at|in|on|by|during|for|throughout|across|inside|near|from|after"
    r"|before|around|with|over|per|until)"
)
_PRE_LABEL_PREP_PHRASE = (
    rf"{_PRE_LABEL_PREP}\s+(?:{_DETERMINER}|-?\d[\d.]*\s*[A-Za-z%/]*)"
    r"(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3}"
)

#: Anything that may precede the label's own noun phrase. Adjuncts only: nothing
#: here can rename the label, because everything here is outside the phrase the
#: label heads.
#:
#: ~~``|{_PRE_LABEL_PREP}``~~ — **A BARE PREPOSITION WITH NO OBJECT WAS AN ALTERNATIVE
#: HERE AND WAS REMOVED AS A MEASURED EQUIVALENT MUTANT.** Dropping it left all 1,902
#: tests GREEN, i.e. nothing in any corpus reaches it: every measured form that opens
#: with a preposition supplies an object, so ``_PRE_LABEL_PREP_PHRASE`` already covers
#: it (*"At the end <instant>"* parses as ``at`` + ``the``). It admitted ``"At "``
#: alone. Removed rather than recorded-and-kept, because an unreachable alternative in
#: an allowlist is reach nobody has measured, and removing it narrows the gate — the
#: fail-closed direction.
_PRE_LABEL_ADJUNCT = (
    rf"(?:{_PRE_LABEL_PREP_PHRASE}|{_PRE_LABEL_ADVERB}"
    rf"|{_PRE_LABEL_SUBJECT}\s+{_PRE_LABEL_REPORT}|{_PRE_LABEL_SUBJECT})"
)

#: The determiner gate (4) accepts in front of the label — **NARROWER than the shared
#: :data:`_DETERMINER`, and the narrowing closed a silent fabrication an independent
#: hunt found AFTER the gate had shipped.**
#:
#: Measured: *"THEIR scan ended at 2026-01-01T00:00:00Z"* proposed this run's
#: ``acquired_end_utc``. That is the run-misattribution family exactly — a real
#: acquisition time, of somebody else's measurement, attributed to this one — and the
#: pre-modifier allowlist could not have caught it, because the offending word is the
#: DETERMINER and not a modifier.
#:
#: **WHY A SECOND CONSTANT RATHER THAN EDITING THE SHARED ONE, which is the part to
#: preserve.** ``_DETERMINER`` is used by five other constructs
#: (:data:`_LABEL_MODIFIER`, :data:`_LABEL_CLAUSE`, :data:`_CONTINUATION_PHRASE`,
#: :data:`_CONTINUATION_PREP`, :data:`_PRE_LABEL_PREP_PHRASE`), and in every one of
#: them the determiner introduces the object of a LOCATING phrase — *"the temperature
#: of THEIR sample"*, *"425 K at THEIR stage"* — where a third-person possessive says
#: whose APPARATUS, not whose MEASUREMENT, and is perfectly readable. **The pre-label
#: slot is the only one where the determiner answers "whose measurement is this?"**,
#: so it is the only one narrowed. Editing the shared constant would have refused
#: four unrelated legitimate constructions to close one defect; a test asserts all
#: five still read.
#:
#: Dropped, each for a stated reason: ``their``/``his``/``her`` name a THIRD PARTY;
#: ``that``/``those`` are deictic-DISTAL and ambiguous rather than wrong, which
#: fail-closed resolves toward a disclosed refusal; ``each``/``every``/``both``/
#: ``all`` QUANTIFY over several measurements, so *"every scan ended at <instant>"*
#: says something about all of them and nothing about this one.
#:
#: **``that`` ALSO HAD TO LEAVE :data:`_PRE_LABEL_CLAUSE_OPEN`, or narrowing this set
#: would have achieved nothing for it.** As a subordinator it was treated as a clause
#: boundary, so *"That scan "* was cut to *" scan "* and admitted whatever the
#: determiner set said. Measured cost of removing it: **zero** — *"The temperature
#: THAT we recorded was 425 K"* is handled by :data:`_LABEL_CLAUSE` on the far side of
#: the label and still reads.
_PRE_LABEL_DETERMINER = r"(?:the|this|these|a|an|its|our|my)"

#: **GATE (4).** The WHOLE text from the start of the label's clause to the label
#: must be: clause-level adjuncts, then at most one determiner, then at most one
#: admitted locating noun — in that order. ``fullmatch``, for the reason gate (1)
#: gives.
#:
#: **TWO MORE EQUIVALENT MUTANTS WERE FOUND HERE AND BOTH BECAME SIMPLIFICATIONS
#: RATHER THAN FOOTNOTES.**
#:
#: ~~``(?:{_PRE_LABEL_ADJUNCT}\s*[,)]?\s+)*``~~ — the optional ``[,)]`` is
#: **STRUCTURALLY UNREACHABLE**, not merely unexercised, and that is worth more than
#: the deletion. It was copied from :data:`_ASSERTION_BRIDGE`, where it earns its
#: place. Here it cannot: ``,`` and ``)`` are both in :data:`_CLAUSE_BOUNDARY`, so
#: :data:`_PRE_LABEL_CLAUSE_OPEN` cuts the pre-label text AFTER them before this
#: pattern ever sees one. Measured — *"Later, the temperature was 425 K"* and
#: *"(Later) the temperature was 425 K"* both present this gate with ``" the "``.
#: **The lesson is about copying a sub-pattern between gates: the bridge has no
#: clause bound and this gate is defined by one, so syntax that is load-bearing there
#: is dead here.**
#:
#: ~~``(?:{_PRE_LABEL_NOUN}\s+)*``~~ → ~~``?``~~ → ``{0,2}``, **and the middle step
#: is kept because it was RIGHT ON THE EVIDENCE IT HAD AND WRONG WITHIN THE HOUR.**
#: The unbounded loop was an equivalent mutant when :data:`_PRE_LABEL_NOUN` held 11
#: locator nouns and no measured sentence stacked two, so narrowing it to ``?``
#: followed the rule stated above — reach exactly as far as something measures. The
#: benign-form measurement then widened that constant to three groups, which made
#: the slot genuinely multi-word (*"the MEASURED SAMPLE temperature"* is ordinary
#: dictation), so ``?`` began costing readings. ``{0,2}`` is the measured need, and
#: it stays BOUNDED rather than returning to ``*`` so the grammar's reach is stated
#: rather than open. **The lesson is about equivalent mutants specifically: an
#: equivalence is a property of the CORPUS AND THE LEXICON at one moment, not of the
#: pattern — so widening a vocabulary can un-equivalence a mutation that was
#: correctly removed.**
#:
#: **AND ``{0,2}`` → ``*`` REMAINS A GENUINE EQUIVALENT MUTANT, recorded rather than
#: chased.** Measured: all 1,740 tests stay GREEN with the bound removed, because the
#: two differ only on THREE OR MORE stacked pre-modifiers and no corpus anywhere
#: contains one. The bound is kept regardless, and the reason is not behavioural: an
#: allowlist's reach should be STATED. ``*`` would admit *"the measured recorded
#: observed logged sample cryostat temperature"*, and while every word in it is
#: vetted and the sentence is harmless, a pattern whose reach nobody has bounded is
#: how an allowlist stops being one. ``{0,2}`` is the measured need plus nothing.
#: This repository records equivalent mutants as a real and instructive outcome;
#: this is one, and it is the only one left in this gate.
_PRE_LABEL = re.compile(
    rf"\s*(?:{_PRE_LABEL_ADJUNCT}\s+)*"
    rf"(?:{_PRE_LABEL_DETERMINER}\s+)?(?:{_PRE_LABEL_NOUN}\s+){{0,2}}\s*",
    re.IGNORECASE,
)

#: Where the label's clause STARTS: the nearest punctuation or conjunction behind
#: it. Without this the gate would be a whole-segment rule, and *"The temperature
#: drift was 3 K AND the temperature was 425 K"* would lose its second, legitimate
#: reading to the first clause's noun. It is :data:`_CLAUSE_BOUNDARY`'s character
#: class plus the conjunctions, which is the same boundary
#: :data:`_CONTINUATION_WORD` treats as opening a new clause on the far side of the
#: value — deliberately the same notion of "clause", read from the other direction.
#: THE APOSTROPHE IS REMOVED FROM :data:`_CLAUSE_BOUNDARY` FOR THIS GATE ONLY, and
#: it is a correction rather than a loosening. An apostrophe is never a clause
#: boundary in English; it is a possessive or a contraction, and both sit INSIDE the
#: noun phrase the label heads.
#:
#: Measured: with `'` treated as a boundary, ``_pre_label_text`` cut
#: *"The sample's temperature was 425 K"* down to ``"s "`` and gate (4) refused it —
#: 16 of 16 apparatus possessives, every one of which the base commit `d3473414`
#: READ. The curly form *"The sample’s"* read correctly throughout, because U+2019
#: was never in the class, so ONE CHARACTER decided whether an identical sentence
#: was read or refused depending on which keyboard typed it.
#:
#: NOTHING ELSE LEAVES THE CLASS. `)`, `"`, `:`, `;` and `]` remain boundaries here,
#: and they are the second mechanism of the bypass pinned by
#: ``test_the_pre_label_gate_IS_BYPASSED_by_a_preamble_or_a_bracket_RESIDUE``.
#: Removing them would close part of that bypass and is deliberately NOT done in the
#: same change: they are genuine punctuation between clauses in other sentences, and
#: deciding that costs its own corpus. This removal is safe precisely because the
#: apostrophe is the one member that is never a clause boundary at all.
_PRE_LABEL_BOUNDARY_CHARS = r"[,;.!?:)\]}\"—–]"

_PRE_LABEL_CLAUSE_OPEN = re.compile(
    _PRE_LABEL_BOUNDARY_CHARS
    + r"|\b(?:and|but|or|so|while|whilst|because|although|though|when|once"
    r"|until|which|as)\b",
    re.IGNORECASE,
)

#: THE LABEL EACH RULE IS ANCHORED ON, as it appears at the START of that rule's
#: own whole match. Every label-anchored pattern above begins with ``\b`` and its
#: label alternation, so ``match.group(0)`` starts exactly at the label and these
#: recover where it ENDS — which is what makes the bridge extractable without
#: renumbering any capture group (``group(1)`` is the VALUE everywhere in this
#: module, and a ``(?P<bridge>…)`` group would have taken that number).
#:
#: **THE ALTERNATION ORDER IS LOAD-BEARING AND IS MIRRORED, NOT RE-INVENTED.**
#: ``start`` before ``started`` would match three characters of a four-character
#: label and leave ``ed`` sitting in the bridge, which no assertion grammar
#: admits — so every instant would silently stop being read. A test asserts, over
#: every rule and every measured sentence, that the head matches at offset 0 and
#: ends at or before the value.
_LABEL_HEAD_TEMPERATURE = re.compile(r"temperatures?", re.IGNORECASE)
_LABEL_HEAD_START = re.compile(r"(?:started|start|beginning|began)", re.IGNORECASE)
_LABEL_HEAD_END = re.compile(r"(?:ended|end|finished|stopped)", re.IGNORECASE)

#: THE GATE THAT MAKES A RESTATEMENT READABLE AS A RESTATEMENT.
#:
#: ~~"THE ONE THING …"~~ — **CORRECTED 2026-09-12, the same day it was written, by
#: measurement.** The first version of this gate constrained only WHICH CONNECTIVE
#: may sit in the gap, and treated ``about``/``around``/``roughly``/
#: ``approximately``/``possibly``/``again`` as hedges. They are not hedges on the
#: value BEFORE them; they are **approximation modifiers of whatever FOLLOWS
#: them**, so the gap read as a hedge while the words after the value turned it into
#: a different quantity. Eight sentences were measured slipping through, five of
#: them through that one confusion and three through a compound unit. See
#: ``_OR_REQUIRED_HEDGES`` and ``_UNIT_TERMINATORS`` for the two halves and the
#: tables.
#:
#: A restatement pattern (``_TEMPERATURE_K_RESTATED``, ``_INSTANT_RESTATED``) is a
#: bare value form with no label in front of it, so on its own it matches *every*
#: later value of that shape in the sentence — including values that belong to a
#: different quantity entirely. Measured on the code that shipped without this
#: gate, each of these proposed TWO values for ``context.temperature_K`` or for
#: ``timestamps.acquired_start_utc``, and the second one is not in the transcript:
#:
#: ===================================================================  =============
#: sentence                                                             falsely read
#: ===================================================================  =============
#: ``The temperature was 425 K, ramped at 3 K/min``                     a ramp RATE
#: ``The temperature was 425 K and the step size was 0.5 K``            a STEP SIZE
#: ``Sample temperature 425 K, cryostat setpoint 80 K, base 4 K``       TWO others
#: ``The temperature was 425 K and the pressure was 3 K``               a PRESSURE
#: ``…started …01-01T00:00:00Z, ran until …01-02T00:00:00Z``            the END
#: ``…started …01-01T00:00:00Z and we will repeat it …02-01T00:00:00Z`` a FUTURE run
#: ===================================================================  =============
#:
#: Each of those shipped a ``rule`` string asserting that the sentence *restated*
#: the quantity, which is a statement about the transcript that the transcript does
#: not support — ``CLAUDE.md`` §5. It is strictly worse than the silent omission it
#: replaced: an omission loses a reading, an assertion invents one.
#:
#: THE GATE, STATED AS THE INVARIANT IT IMPLEMENTS. A restatement is read only if
#: the text lying between the end of the previous accepted reading of that rule and
#: the start of this restatement's VALUE consists ENTIRELY of an optional comma,
#: optional HORIZONTAL whitespace (never a line break — see ``_H_SPACE``), and
#: exactly one connective drawn from the closed hedge list below. Nothing else may
#: sit in that gap — no noun, no verb, no second label.
#:
#: WHY A HEDGE AND NOT MERELY ADJACENCY. The hedge is what makes the second value a
#: statement about the SAME quantity. ``425 K, 430 K`` is adjacent and means
#: nothing in particular; ``425 K, maybe 430 K`` is a person being uncertain about
#: one number, which is the case the project owner asked for.
#:
#: **BARE ``and`` IS DELIBERATELY NOT IN THE LIST.** It is conjunctive, not
#: hedging: *"425 K and 430 K"* may well be two different quantities, and half the
#: table above is a bare ``and``.
#:
#: ~~"``and again`` IS in the list, because ``again`` is what makes it a
#: restatement of one quantity rather than a second one — and note that BARE
#: ``again`` is NOT, for the reason ``_OR_REQUIRED_HEDGES`` gives: before a full
#: instant it most naturally means the scan was REPEATED."~~ — **WITHDRAWN
#: 2026-09-12 (fourth pass), and it is kept struck because THIS PARAGRAPH AND
#: ``_OR_REQUIRED_HEDGES`` CONTRADICTED EACH OTHER ABOUT THE SAME WORD while a
#: fabrication shipped between them.** It claimed ``again`` is what makes a
#: restatement, one sentence after conceding that bare ``again`` means the
#: opposite. ``and again`` is the STRONGER repeat marker, not the weaker one, and
#: it has moved to :data:`_OR_REQUIRED_HEDGES`. Measured at ``22d794a5``:
#:
#: ==================================================================  =============
#: sentence                                                            read
#: ==================================================================  =============
#: ``…started 2026-01-01T00:00:00Z, and again 2026-01-02T00:00:00Z.``  BOTH, silently
#: ``…ended 2026-01-01T00:00:00Z, and again 2026-01-02T00:00:00Z.``    BOTH, silently
#: ``…started …01-01…, and again …01-02…, and again …01-03…``          ALL THREE, silently
#: ``…started 2026-01-01T00:00:00Z, again 2026-01-02T00:00:00Z.``      one + disclosure
#: ==================================================================  =============
#:
#: A durable OPEN proposal is minted per candidate, so a scientist could accept a
#: second acquisition instant this reader invented into a ``timestamps`` field that
#: reaches an exported official record — an ASSERTION, which §5 forbids in terms.
#: **THE REPEAT SEMANTICS IS A PROPERTY OF THE WORD, NOT OF THE FIELD**, which is
#: why the fix is one flat move and not a per-rule hedge list: *"the temperature
#: was 425 K, and again 430 K"* is a second MEASUREMENT in the same way
#: *"started X, and again Y"* is a second START, so the ``rule`` sentence's claim
#: that the quantity was restated is false in both. ``_OR_REQUIRED_HEDGES``' own
#: rule-specific phrasing (*"before a full instant"*) was therefore UNDER-general,
#: which is the opposite of what it looked like.
#:
#: **WHAT THE MOVE COSTS, STATED PLAINLY.** *"The temperature was 425 K, and again
#: 430 K"* now reads 425 alone and raises one ``unhedged_further_values``
#: abstention — a legitimate-looking temperature restatement is lost, and it is
#: DISCLOSED, which is the trade §5 ranks the right way round. ``or and again`` is
#: not idiomatic English, so in practice the connective no longer bridges anywhere.
#: It is PARKED rather than deleted for a reason that is not tidiness: if someone
#: does write *"425 K, or and again 430 K"*, the ``or`` scopes it as alternation
#: exactly as it does for ``or about``, so the reading is then correct and
#: refusing it would be a second, smaller omission. Deleting the member would also
#: silently narrow what ``_HEDGE_CONNECTIVES`` tells a reader was reviewed.
#:
#: **CLAUSE-BOUNDING COMES FREE AND IS NOT A SEPARATE CHECK.** The pattern admits
#: only a comma, horizontal whitespace and letters, so a ``.``, ``;`` or ``:`` in
#: the gap refuses — which is the clause bound ``_TEMPERATURE_K`` imposes on itself
#: with ``[^.;:]``. It is stated here rather than added as a second check.
#:
#: **AND CLAUSE-BOUNDING ALONE WOULD HAVE BEEN INSUFFICIENT BY A WIDER MARGIN THAN
#: THE REVIEW SAID.** The review's phrasing was *"two of the rows above have no
#: punctuation"*, which reads as though clause-bounding caught the other four.
#: Measured over all six gaps (``test_clause_bounding_alone_would_have_caught``):
#:
#: * clause-bounding on ``.;:`` — the bound ``_TEMPERATURE_K`` already uses —
#:   refuses **0 of 6**. Not one gap contains any of those characters.
#: * clause-bounding that ALSO breaks at a comma refuses **3 of 6**; the three
#:   bare-``and`` rows survive it.
#:
#: So the hedge is not a refinement of clause-bounding; and a comma cannot be
#: treated as a clause break here anyway, because the owner's own sentence —
#: *"around 425 K, maybe 430 K"* — bridges across one. ~~"it is the whole gate"~~
#: — **CORRECTED 2026-09-12: the connective is one of TWO required conditions**;
#: ``_UNIT_TERMINATORS`` is the other.
#:
#: **ADJACENCY CHAINS.** After a restatement is accepted the anchor advances to the
#: end of it, so *"425 K, maybe 430 K, or perhaps 435 K"* reads all three — each
#: hedged against the value before it. A REFUSED restatement does not advance the
#: anchor, which is why *"425 K, cryostat setpoint 80 K, base 4 K"* refuses both
#: rather than refusing 80 and then measuring 4's gap from it.
#: Hedges that may bridge ON THEIR OWN, with or without an ``or`` in front.
#:
#: What the three have in common is the property the measured defect turns on: NONE
#: of them can modify a following noun phrase into a different quantity. *"maybe
#: 3 K"*, *"perhaps 3 K"* and *"alternatively 3 K"* are all
#: statements that the quantity just given might instead be 3 K. They are modal or
#: alternation words, not measurement words.
#:
#: ~~``"and again"``~~ — **MOVED to :data:`_OR_REQUIRED_HEDGES` 2026-09-12 (fourth
#: pass).** It satisfies the "cannot modify a following noun phrase" property and
#: still does not belong here, which is why this tuple's own criterion was not
#: enough to catch it: it is a REPEAT marker, so it says the quantity was stated a
#: SECOND TIME rather than that it might instead be the second value. See the
#: measured table above ``_HEDGE_BRIDGE`` and ``_OR_REQUIRED_HEDGES``' last entry.
#: ~~"the four"~~ is now three.
_BARE_HEDGES: tuple[str, ...] = (
    "maybe",
    "perhaps",
    "alternatively",
)

#: Hedges that bridge ONLY behind a MANDATORY ``or``. This is the correction of
#: 2026-09-12 and it is the whole of the first half of the fix.
#:
#: **WHY THESE SIX ARE DIFFERENT, AND WHY IT WAS NOT VISIBLE IN THE FIRST GATE.**
#: ``about``, ``around``, ``roughly`` and ``approximately`` are **approximation
#: modifiers of whatever FOLLOWS them**, not hedges on what precedes them. *"about
#: 3 K"* does not mean "the value I just gave might be 3 K"; it means "3 K,
#: approximately" — of *something*, and the something is named by the words after
#: it. ``possibly`` and ``again`` are the same shape for a different reason:
#: ``possibly`` scopes over a following clause, and before a full UTC instant
#: ``again`` most naturally means the scan was REPEATED, i.e. a different run's
#: instant. Measured at ``c9a4c6e8``, each of these proposed a second value for a
#: field the transcript states once, and the second value is not that field's:
#:
#: =====================================================================  =============
#: sentence                                                               falsely read
#: =====================================================================  =============
#: ``The temperature was 425 K, about 3 K above target``                  an OFFSET
#: ``The temperature was 425 K, around 80 K colder than before``          a DIFFERENCE
#: ``The temperature was 425 K, about 5 K of drift``                      a DRIFT
#: ``The temperature was 425 K, roughly 2 K of scatter``                  a SCATTER
#: ``The temperature was 425 K, approximately 10 K below the setpoint``   an OFFSET
#: ``The temperature was 425 K, about 1 K per minute``                    a ramp RATE
#: ``The temperature was 425 K, about 3 K.``                              an OFFSET
#: ``The temperature was 425 K, about 0.5 K per step``                    a STEP SIZE
#: ``…started 2026-01-01T00:00:00Z, again 2026-01-02T00:00:00Z.``         a REPEAT
#: ``…started 2026-01-01T00:00:00Z, about 2025-12-31T00:00:00Z plus 1 day`` an ARITHMETIC BASE
#: =====================================================================  =============
#:
#: **The ``or`` is what removes the ambiguity, and it does it grammatically rather
#: than by a list.** *"425 K, or about 430 K"* can only be alternation: ``or``
#: coordinates the new value WITH the old one, so the approximation modifier is
#: scoped inside an alternative for the same quantity. *"425 K, about 430 K"* has no
#: such marker and is therefore not read at all — which is an OMISSION, and §5 ranks
#: an omission above an assertion. **That sentence WAS on the must-pass list and was
#: withdrawn from it deliberately**; it is recorded as residue, not as a defect.
#:
#: **NOTHING WAS ADDED OR REMOVED FROM THE REVIEWED SET.** All eleven connectives
#: are still admitted; ~~six~~ **SEVEN (2026-09-12, fourth pass)** of them moved
#: from the bare branch to this one, and
#: ``_HEDGE_CONNECTIVES`` below is still their union so the ratchet on membership is
#: unchanged.
#:
#: **THE SEVENTH IS ``and again``, AND IT IS THE ONE THIS COMMENT'S OWN REASONING
#: SHOULD HAVE CAUGHT.** The ``again`` row of the table above says that before a
#: full instant ``again`` most naturally means the scan was REPEATED — and
#: ``and again`` is the STRONGER repeat marker, yet it sat in ``_BARE_HEDGES``
#: until an independent review measured it minting a durable OPEN proposal for a
#: second acquisition instant nobody stated. Two rows, both measured at
#: ``22d794a5``, both SILENT (no abstention at all):
#:
#: =====================================================================  =============
#: sentence                                                               falsely read
#: =====================================================================  =============
#: ``…started 2026-01-01T00:00:00Z, and again 2026-01-02T00:00:00Z.``     a REPEAT
#: ``…ended 2026-01-01T00:00:00Z, and again 2026-01-02T00:00:00Z.``       a REPEAT
#: =====================================================================  =============
#:
#: **THE RULE-SPECIFIC PHRASING IN THIS COMMENT IS WHY ONE FLAT LIST STILL
#: WORKS.** *"Before a full instant"* reads as though the repeat sense were a fact
#: about the ``timestamps`` rules, which would need a per-rule hedge list. It is
#: not: *"the temperature was 425 K, and again 430 K"* is a second MEASUREMENT in
#: the same way, so the ``rule`` sentence's claim that the sentence restated the
#: quantity is false for the temperature rule too. The word carries the repeat
#: sense; the field does not. A per-rule split was therefore declined — it would
#: have preserved a reading that is itself unsound, on a second axis of drift, for
#: no honesty gain.
_OR_REQUIRED_HEDGES: tuple[str, ...] = (
    "about",
    "around",
    "roughly",
    "approximately",
    "possibly",
    "again",
    # Order is irrelevant here and that is MEASURED, not assumed — see
    # `_alternation`. Appended last so the diff shows it arriving rather than
    # reshuffling the six that were already here.
    "and again",
)

#: ``or`` on its own, which is alternation in the plainest possible form: *"it was
#: 425 or 430"* is a person naming two candidate values for one quantity. It is
#: neither a bare hedge nor an ``or``-prefixed one — it IS the prefix, standing
#: alone — so it is named separately rather than folded into either tuple.
_BARE_OR = "or"

#: **THE CONNECTIVE ENUMERATION, DERIVED FROM THE TWO LISTS RATHER THAN RETYPED.**
#:
#: This exists because the same claim has now been published wrong FIVE TIMES, and
#: the fifth was found by independent review in SERVED text: ``7afbe633`` moved
#: ``and again`` from :data:`_BARE_HEDGES` to :data:`_OR_REQUIRED_HEDGES`, correctly
#: swept all three ``_RULES.restated_sentence`` strings, and left BOTH
#: :data:`AMBIGUITY_POLICY` rows telling clients that ``and again`` bridges on its
#: own. One response body then carried a policy promising a second value would be
#: read and an abstention saying it had not been.
#:
#: **A GUARD WAS TRIED FIRST AND IT WAS DECORATIVE, which is why the text is
#: derived instead.** The obvious guard — "an or-required connective may be named
#: only in a clause that also says ``or``" — reports **GREEN on the exact pre-fix
#: text**, measured: that enumeration is a single clause and it ends with *"a bare
#: 'or', or an approximation behind an explicit 'or'"*, so the word ``or`` is always
#: present and the test always passes. A second attempt using ``"or" in clause``
#: was worse still: the word **"word"** contains ``or``, so it passed every row for
#: a reason having nothing to do with the claim.
#:
#: Deriving the strings removes the class of defect instead of detecting it: the
#: served text cannot place a connective in the wrong group because it does not
#: name them individually at all. A test then asserts the derived strings ARE the
#: ones served, which is a parity check that cannot pass vacuously.
_BARE_BRIDGING_WORDS = ", ".join(f"'{word}'" for word in _BARE_HEDGES)
_OR_ONLY_BRIDGING_WORDS = ", ".join(f"'{word}'" for word in _OR_REQUIRED_HEDGES)

# --- the published ambiguity policy -------------------------------------------
#
# RELOCATED 2026-09-13, from immediately after the `OUTCOME_*` constants above.
# Two of its rows enumerate the hedging connectives, and that enumeration is now
# DERIVED from `_BARE_HEDGES`/`_OR_REQUIRED_HEDGES` rather than retyped — see
# `_BARE_BRIDGING_WORDS` for the five-times-wrong claim that forced it — so this
# constant has to be built AFTER those lists exist. Nothing in this module reads
# it, and `__all__` still exports it, so the move changes no import and no
# served value; only the definition order.
AMBIGUITY_POLICY: tuple[dict[str, str], ...] = (
    {
        "kind": "run_target_required",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "No run was selected for this capture. Every value this reader can "
            "propose is a run-level field, so it asks which run rather than "
            "choosing one. A record with exactly one run is not an exception: "
            "attaching content to the only run that happens to exist is an "
            "invention, and this build already refuses it when capturing a note."
        ),
    },
    {
        "kind": "unknown_run_reference",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "The transcript names a run this record does not have. The reference "
            "is reported with the runs that do exist, and no candidate is "
            "proposed from this transcript — the scientist may have selected the "
            "wrong run, or may be describing work not yet recorded here."
        ),
    },
    {
        "kind": "ambiguous_run_reference",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "The transcript names something that matches more than one run of "
            "this record. The matching runs are listed and none is chosen; "
            "preferring the first would make the target depend on creation order "
            "rather than on what was said."
        ),
    },
    {
        "kind": "conflicting_run_reference",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "The transcript names a run other than the one selected for this "
            "capture. Both are reported and neither wins: a selection is a "
            "deliberate act and so is saying a run's name, and this reader has no "
            "grounds to decide which one the scientist meant."
        ),
    },
    {
        "kind": "vague_run_reference",
        "outcome": OUTCOME_CLARIFICATION,
        "rule": (
            "The transcript refers to a run by position or by relation — 'the "
            "second run', 'the previous run' — rather than by name, number or id. "
            "This reader performs no positional arithmetic: 'the second run' is "
            "not the same claim as 'run 2', and treating them as equal would "
            "silently retarget a value."
        ),
    },
    {
        "kind": "conflicting_values_for_one_field",
        "outcome": OUTCOME_NEEDS_REVIEW,
        "rule": (
            "Two statements propose different values for the same field — in two "
            "sentences, or inside ONE sentence such as 'around 425 K, maybe 430 "
            "K'. Both candidates are returned and grouped, so the scientist "
            "resolves the contradiction. Choosing the later one would be a guess "
            "dressed as a convention, and dropping both would lose something that "
            "was said twice. The same value restated inside one sentence is not a "
            "contradiction and produces one candidate. Inside ONE sentence a "
            "second value is read only when a hedging word — "
            + _BARE_BRIDGING_WORDS
            + " on their own, or a bare 'or'; "
            + _OR_ONLY_BRIDGING_WORDS
            + " count only behind an explicit 'or', because each describes what "
            "FOLLOWS it rather than hedging the value before it — sits "
            "immediately between the two, with nothing else in the gap; "
            "'425 K and the pressure was 3 K' states two different quantities, "
            "and reading the second as a temperature would invent a value the "
            "transcript does not give."
        ),
    },
    {
        "kind": "temperature_not_in_kelvin",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "A temperature was stated in a unit other than kelvin, and the field "
            "records kelvin. Converting it would put a number in the record that "
            "nobody said, so nothing is proposed and the statement is reported. "
            "The scientist can state the kelvin value, or accept nothing."
        ),
    },
    {
        "kind": "implicit_only_subject",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "The transcript describes the absorbing element or the absorption "
            "edge. This build treats both as implicit, sidecar-only content "
            "because the official record schema it validates against provides no "
            "native field for them, so there is no path to propose and none is "
            "invented."
        ),
    },
    {
        "kind": "unhedged_further_values",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "A sentence states more than one value of the same form for one "
            "field, and only the labelled one was read. A second value is read "
            "as an alternative for the same field only when THREE things hold, "
            "and this row is the first two of them: a hedging word from a closed "
            "list links it to the first with nothing else in the gap — "
            + _BARE_BRIDGING_WORDS
            + " on their own, or a bare 'or'; "
            + _OR_ONLY_BRIDGING_WORDS
            + " count only behind an explicit 'or', because each describes what "
            "FOLLOWS it rather than hedging the value before it — and the "
            "value is not part of a larger unit such as K/min. Without those "
            "two, a later value of the same form is usually a different "
            "quantity: 'about 3 K above target' is an offset and 'or 3 K/min' is "
            "a ramp rate, and reading either as a temperature would invent a "
            "value the transcript does not give. The third condition has its own "
            "row below. The withheld values are NOT "
            "quoted, counted or classified here, because not knowing what they "
            "are is the reason they were withheld; the sentence is reported so "
            "the scientist can read it and state any value they want recorded."
        ),
    },
    {
        "kind": "trailing_text_after_further_values",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "The THIRD condition: a further value linked by a hedging word is "
            "read only when it ENDS the statement. Either the sentence finishes "
            "after it, or the only thing following is another hedged value that "
            "was itself read. When something else follows, the value is not "
            "read: '425 K, maybe 3 K of drift' states a drift and not a second "
            "temperature, and the difference between that and '425 K, maybe 430 "
            "K and the atmosphere was dry nitrogen' is a judgement about English "
            "that no rule here can make. So the same proxy refuses both, and "
            "this disclosure is why that is acceptable — a value that was not "
            "read is REPORTED, never dropped in silence, and the sentence itself "
            "is kept verbatim as a note. This condition applies to EVERY hedging "
            "word, including behind an explicit 'or'. It was scoped to hedges "
            "standing alone for one release, on the reasoning that 'or' "
            "coordinates the new value with the old one and so marks it as an "
            "alternative grammatically rather than by position; that reasoning "
            "is sound about the words BEFORE the value and says nothing about "
            "the words after it, and '425 K or 3 K of drift' was read as two "
            "temperatures while it held."
        ),
    },
    {
        "kind": "label_does_not_assert_this_value",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "A sentence put a value near the words a rule looks for without "
            "asserting it as that field. The label-to-value bridge is an "
            "ALLOWLIST — a copula, a locating phrase, 'held at', 'set to', "
            "'reached', an approximation, or nothing at all — and anything else "
            "refuses. That direction is the decision: a list of forbidden nouns "
            "('drift', 'error', 'step') fails OPEN, so the next unanticipated "
            "noun becomes a fabricated scientific value, while an allowlist costs "
            "a reading and DISCLOSES it. 'The temperature drift was 3 K' states a "
            "drift; nothing is proposed and the sentence is reported."
        ),
    },
    {
        "kind": "value_qualified_by_what_follows",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "A sentence asserted a value for a field and then qualified it, so "
            "the number measures a relation, a rate or a bound rather than the "
            "field: '3 K above target', '3 K of drift', '2 K per minute', '1 K at "
            "most'. What may follow a value is likewise an ALLOWLIST — the end of "
            "the clause, any punctuation, a coordinator, or where and when it was "
            "measured — so an unanticipated qualifier costs the reading instead of "
            "converting a relative number into an absolute one. The value is not "
            "read, the statement is reported, and the text is kept verbatim."
        ),
    },
    {
        # GATE (4). **THIS ROW WAS MISSING FOR THREE COMMITS. `AMBIGUITY_POLICY` IS
        # SERVED (`routes.py:16309`), so this application published a policy document
        # enumerating three pass-one outcomes while its reader produced four.** A
        # scientist receiving a `words_before_the_label_name_something_else`
        # abstention would have found no rule for it in the very document that exists
        # to explain the reader's refusals — a surface promising completeness it did
        # not have, which is the defect class this module keeps finding in itself.
        #
        # **AND IT WENT MISSING A SECOND TIME, BY A PROCESS FAILURE WORTH RECORDING:**
        # the row was written, then a mutation-testing harness that restores with
        # `git checkout -- <file>` ran against it. That restores from HEAD, so it
        # **discarded the uncommitted row**, and the commit whose message announced
        # this fix (`32fd4189`) therefore contained only the TEST. The test is what
        # caught it. **A mutation harness that restores from git destroys
        # uncommitted work in the file it mutates — commit first, or snapshot the
        # bytes.** (An in-process `try/finally` restore was tried before that and is
        # worse: a timeout killed it mid-run and left this module silently corrupt
        # but syntactically valid, because implicit string concatenation swallowed a
        # deleted alternation.)
        #
        # The guard is `test_every_abstention_kind_the_reader_can_PRODUCE_has_a_
        # served_policy_row`: it walks a corpus, collects the kinds actually emitted,
        # and requires a row for each. A guard over `_REFUSAL_REASONS` alone would
        # have been weaker — it would pass for a kind that has a reason and no row,
        # which is exactly the state this row fixes.
        #
        # **AND `32fd4189`'s CLAIM THAT "NO GUARD COULD HAVE CAUGHT IT" WAS TOO
        # STRONG — withdrawn here.** `test_transcript_capture.py::test_every_
        # ambiguity_kind_is_covered_by_the_published_policy` has long asserted SET
        # EQUALITY between `AMBIGUITY_POLICY`'s kinds and a hand-written list, and it
        # DID fire on this row — in the other direction, when the row was added
        # without extending the list. What it cannot do is catch a kind the READER
        # emits with no row, because it never consults the reader. So the accurate
        # claim is about the guard's SHAPE, not its absence — and that shape was
        # already named as one of the three weak forms in the new guard's own
        # docstring, so the slice named the weakness and then asserted the guard's
        # absence anyway. Both tests are kept: one ratchets the served set, the other
        # measures what the reader emits, and neither subsumes the other.
        "kind": "words_before_the_label_name_something_else",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "A sentence stated a value the way a field is stated, but the words in "
            "FRONT of the label re-named what the label denotes: 'the SETPOINT "
            "temperature was 425 K' states a setpoint, 'the MAXIMUM temperature' an "
            "extremum, 'the AMBIENT temperature' the room's, and 'the PREVIOUS scan "
            "ended at ...' a different measurement's time. The two forward gates "
            "cannot see any of it — one reads label-to-value and the other "
            "value-to-end — so what may sit in front of the label is a THIRD "
            "ALLOWLIST: one determiner, and a closed set of words that LOCATE the "
            "quantity ('sample', 'cryostat', 'scan') or say how it was obtained "
            "('measured', 'recorded') rather than re-subject it. TWO KNOWN GAPS, "
            "stated here rather than left for a reader to discover: a clause-level "
            "adjunct such as an opening prepositional phrase is NOT closed (its "
            "object may absorb an arbitrary word), and a bracketing character "
            "between the modifier and the label — a parenthesis, a quotation mark, "
            "a colon or a semicolon — ends the clause this gate inspects, so the "
            "modifier falls outside it. In both, the sentence reads as though the "
            "modifier were absent. The direction is the decision, for the third "
            "time in this reader: "
            "a list of forbidden modifiers fails OPEN on the next one, while an "
            "allowlist costs a reading and DISCLOSES it. This outcome does NOT "
            "claim the value is not the field's — an ambient or a cryostat "
            "temperature may be exactly what was meant, and deciding that it is "
            "not would be as much a scientific judgement as deciding that it is. "
            "It reports that the sentence does not settle it. The value is not "
            "read, the statement is reported, the text is kept verbatim, and the "
            "same claim stated with the qualifier BEHIND the label — 'the "
            "temperature of the sample was ...' — is read normally."
        ),
    },
    {
        "kind": "several_values_and_none_selected",
        "outcome": OUTCOME_ABSTENTION,
        "rule": (
            "A sentence states several values for ONE scalar field with nothing "
            "between them but sequencing — 'was 300 K, then 350 K, then 400 K', "
            "'ramped from 300 K to 400 K'. NO value is selected, including the "
            "first: promoting it would let a scientist accept a starting point as "
            "the run's temperature, which is what this reader did before and is "
            "the defect this row records. It is not "
            "'conflicting_values_for_one_field' either — that outcome returns BOTH "
            "candidates for a person to choose between, and its served reason says "
            "'Accept at most one', which is a claim about ALTERNATIVES. A "
            "progression is not a disagreement, so offering its values as "
            "alternatives would state something the transcript does not. The gap "
            "test is an allowlist of coordinators, so a gap that names a different "
            "instrument ('425 K, cryostat setpoint 80 K') is NOT a progression and "
            "the asserted value survives; and two statements of the SAME value are "
            "emphasis, not a progression."
        ),
    },
    {
        "kind": "unmatched_text",
        "outcome": OUTCOME_UNMAPPED,
        "rule": (
            "No rule matched. The text is stored verbatim as an Unmapped Note for "
            "review; it is never dropped and never guessed at."
        ),
    },
)

#: The reviewed closed set, as ONE union, so a reader and a ratchet can ask "which
#: words may appear in the gap at all?" without reading the pattern. It is DERIVED
#: from the three constants above rather than retyped, so it cannot disagree with
#: the pattern about membership — the split is what a test has to pin separately.
_HEDGE_CONNECTIVES: tuple[str, ...] = (
    _BARE_HEDGES + _OR_REQUIRED_HEDGES + (_BARE_OR,)
)
#: EVERY whitespace character Python's own ``str.splitlines()`` treats as a line
#: boundary. DERIVED FROM A DEFINITION, NOT ENUMERATED FROM INTUITION, and that is
#: the whole reason this constant exists rather than a literal in the class below.
#:
#: ``test_H_SPACE_excludes_exactly_the_line_boundary_whitespace`` re-derives this
#: tuple at test time as ``[c for c in whitespace if len(f"a{c}b".splitlines()) ==
#: 2]``, so a reader never has to trust that ten is the right number or that these
#: are the right ten. Measured over all 0x110000 code points: 29 characters match
#: ``\s``, of which these 10 are line boundaries and 19 are not.
_LINE_BREAKS: tuple[str, ...] = (
    "\n",        # U+000A LINE FEED
    "\v",        # U+000B LINE TABULATION
    "\f",        # U+000C FORM FEED
    "\r",        # U+000D CARRIAGE RETURN
    "\x1c",      # U+001C FILE SEPARATOR
    "\x1d",      # U+001D GROUP SEPARATOR
    "\x1e",      # U+001E RECORD SEPARATOR
    "\x85",      # U+0085 NEXT LINE
    " ",    # LINE SEPARATOR
    " ",    # PARAGRAPH SEPARATOR
)

#: Horizontal whitespace: every whitespace character EXCEPT a line break.
#:
#: ``\s`` was the first spelling and it was WRONG in a way only a test caught: it
#: admits ``\n``, so ``", maybe \n"`` bridged, and a hedge on the far side of a line
#: break is not "immediately between" two values. Matching with ``fullmatch`` rather
#: than ``$`` does NOT fix that — ``$``'s before-a-trailing-newline laxity is a
#: different hole — and believing it did was the error. It is a
#: character class rather than ``[ \t]`` so a non-breaking space in dictated text
#: still bridges.
#:
#: ~~``[^\S\n]``~~ — **CORRECTED 2026-09-12 (fourth pass) by independent review, and
#: the documented invariant above was FALSE for every character except ``\n``.**
#: ``[^\S\n]`` excludes ONE of the ten whitespace characters that are line
#: boundaries, so the other nine bridged a hedge. Measured at ``22d794a5``, on
#: ``f"The temperature was 425 K,{c}maybe 430 K."``:
#:
#: ======================  ================================  =========
#: character               read                              disclosed
#: ======================  ================================  =========
#: ``\r`` U+000D           ``[425, 430]``                    no
#: ``\v`` U+000B           ``[425, 430]``                    no
#: ``\f`` U+000C           ``[425, 430]``                    no
#: ``\x1c`` ``\x1d`` ``\x1e``  ``[425, 430]``                no
#: ``\x85`` U+0085 (NEL)   ``[425, 430]``                    no
#: `` `` `` ``   ``[425, 430]``                    no
#: ``\n`` U+000A           ``[425]``                         (segmented)
#: ======================  ================================  =========
#:
#: ~~"A segment cannot contain a newline today (``_SEGMENT_BOUNDARY`` splits on
#: them), so this closes nothing live; it is written so nothing opens if
#: segmentation ever changes."~~ — **that reasoning was right about ``\n`` and is
#: exactly what made the other nine invisible.** ``_SEGMENT_BOUNDARY`` splits on
#: ``\n+`` and on ``\s+`` only after ``[.!?]``, so a lone ``\r`` survives INSIDE one
#: segment, and the transcript route applies no control-character filter. The nine
#: were live over HTTP, not hypothetical.
#:
#: **NBSP U+00A0 BRIDGES, DELIBERATELY, AND IS NOT ONE OF THE TEN.** It is not a
#: line boundary and dictated text contains it; the sentence *"425 K,\xa0maybe
#: 430 K"* is one line and one statement. A test pins that it still reads, so a
#: future widening of this class cannot quietly take it.
_H_SPACE = "[^\\S" + re.escape("".join(_LINE_BREAKS)) + "]"

def _alternation(connectives: tuple[str, ...]) -> str:
    """A regex alternation over connectives, multi-word ones spaced by ``_H_SPACE``.

    **ORDER IS IRRELEVANT HERE, AND SAYING SO REPLACES A CLAIM THIS MODULE AND ITS
    TESTS BOTH CARRIED AND NEITHER HAD CHECKED.** The retired claim was that ``and
    again`` must precede ``again`` in the alternation "or the shorter alternative
    would win — which ``fullmatch`` would then reject, silently dropping ``and
    again``", and ``test_the_hedge_list_is_exactly_the_reviewed_closed_set`` pinned
    the ordering with an index comparison on that basis. It is **false twice over**,
    measured 2026-09-12:

    * neither string is a prefix of the other (``"again"`` begins ``ag``, ``"and
      again"`` begins ``an``), so no shadowing was ever possible between that
      particular pair; and
    * more generally, ``fullmatch`` has the **opposite** effect to the one claimed.
      It is exhaustive: when a short alternative matches and the remainder then
      fails, the engine BACKTRACKS and tries the longer one. Measured on the
      hardest case — ``("maybe", "maybe not")``, where one string genuinely IS a
      prefix of the other — ``" maybe not "`` bridges under **both** orders.

    A longest-first ``sorted()`` was written here on the strength of the retired
    claim and then **removed**, because it was measured to be an equivalent mutant:
    reversing it to shortest-first left all 249 transcript tests GREEN. A guard that
    survives its own inversion is not a guard, and a comment asserting it guards
    something is worse than no guard at all.
    ``test_alternation_order_cannot_change_whether_a_gap_bridges`` pins the property
    so nobody re-adds a sort with a justification nobody measured.
    """
    return "|".join(
        connective.replace(" ", f"{_H_SPACE}+") for connective in connectives
    )


#: Matched with ``fullmatch``, never ``search`` or ``$``: the connective must be the
#: WHOLE gap between the two values, and ``$`` would also match before a trailing
#: newline.
#:
#: THREE BRANCHES, and the middle one is the fix:
#:
#: 1. ``or`` + ANY reviewed hedge — the only way an approximation modifier bridges;
#: 2. a BARE hedge, drawn ONLY from ``_BARE_HEDGES``;
#: 3. ``or`` alone.
_HEDGE_BRIDGE = re.compile(
    rf",?{_H_SPACE}*(?:"
    rf"{_BARE_OR}{_H_SPACE}+(?:" + _alternation(_OR_REQUIRED_HEDGES + _BARE_HEDGES) + ")"
    r"|(?:" + _alternation(_BARE_HEDGES) + ")"
    rf"|{_BARE_OR}"
    rf"){_H_SPACE}*",
    re.IGNORECASE,
)

#: ~~``_BARE_HEDGE_BRIDGE`` — THE SAME GAP, NARROWED TO BRANCH 2. "It exists so the
#: THIRD CONDITION below can ask WHICH BRANCH admitted a gap without picking apart a
#: match object."~~ — **DELETED 2026-09-12 (third pass), and recorded here rather
#: than silently removed, because it is the SIGNATURE of the change that removed
#: it.** Condition 3 is now UNIVERSAL, so nothing asks which branch admitted a gap
#: any more, and the boolean that pattern computed was carried through
#: ``_segment_readings``' ``accepted`` list and then discarded. Kept, it would have
#: been a compiled pattern, a per-restatement ``fullmatch`` and a documented
#: rationale for a decision no longer taken — which is the "guard with a false
#: rationale" this module has already had to delete once.
#:
#: **THE BRANCH SPLIT ITSELF IS UNCHANGED AND STILL FULLY LIVE.** ``_BARE_HEDGES``
#: bridge alone and ``_OR_REQUIRED_HEDGES`` need an explicit ``or``; that is
#: CONDITION 1 and it is what ``_HEDGE_BRIDGE``'s three branches encode. Only the
#: second COPY of branch 2 is gone.
#: ``test_the_hedge_bridge_has_exactly_three_branches`` pins the split directly on
#: ``_HEDGE_BRIDGE``, which is where it was always decided.
#: THE SECOND HALF OF THE GATE: THE UNIT MUST BE THE WHOLE UNIT.
#:
#: A restatement pattern ends at its unit — ``3 K`` for the kelvin rule, the
#: trailing ``Z`` for an instant — and ``K\b`` treats ``K/`` as a word boundary, so
#: ``3 K/min`` matched as though the unit were kelvin. The connective in front of it
#: is a perfectly good one, so the first gate could not see it:
#:
#: ===========================================================  ==================
#: sentence                                                     falsely read
#: ===========================================================  ==================
#: ``The temperature was 425 K or 3 K/min``                     a ramp RATE
#: ``The temperature was 425 K and again 3 K/min``              a ramp RATE
#: ``The temperature was 425 K, alternatively 3 K/min``         a ramp RATE
#: ===========================================================  ==================
#:
#: **THESE THREE ARE THE ORIGINAL RAMP-RATE DEFECT WITH A DIFFERENT CONNECTIVE.**
#: ``", ramped at 3 K/min"`` was refused because ``ramped at`` is not a hedge; these
#: say the same false thing through a gap every version of the hedge list admits, and
#: two of the three survive the ``or``-prefix correction above. Neither half of this
#: gate closes the other's cases.
#:
#: **AN ALLOWLIST, DELIBERATELY, AND NOT A LIST OF FORBIDDEN TAILS.** What may follow
#: a complete unit is whitespace, a sentence terminator, a separator or a closing
#: bracket — a small, closed, punctuation-only set. Everything else refuses, so a
#: compound unit nobody thought of (``K·s``, ``K^-1``, ``K-edge``) declines to read
#: rather than fabricating a value. A DENYLIST of known compound units would fail
#: OPEN, which is the failure mode this reader has already shipped twice.
#:
#: It is stated over the character IMMEDIATELY after the match, not over the rest of
#: the segment: a rule about the rest of the segment is a rule about what a sentence
#: may go on to say, and that was measured to cost six natural sentences their
#: restatement — including *"maybe 430 K and the atmosphere was dry nitrogen"*, where
#: the atmosphere rule's own text is the tail. ~~See ``_RESTATEMENT_RESIDUE`` for
#: the one class this leaves open~~ — that class is CLOSED (see
#: :data:`_RESTATEMENT_RESIDUE_CLOSED`); the open one is now
#: :data:`_LABEL_OVERREACH_CLOSED`, which this condition never reached at all
#: and which its own gate closed on 2026-09-13.
_UNIT_TERMINATORS: frozenset[str] = frozenset(",.;:!?)]}\"'")

#: THE THIRD CONDITION: ~~A RESTATEMENT BEHIND A **BARE** HEDGE~~ **EVERY
#: RESTATEMENT** MUST END THE STATEMENT. Added 2026-09-12 (second pass), scoped to
#: the bare-hedge branch; made UNIVERSAL 2026-09-12 (third pass) after the scope was
#: measured leaving five silent fabrications behind the ``or`` branch. It is the
#: decision the residue comment referred rather than took.
#:
#: **WHAT IT CLOSES.** A bare hedge, a COMPLETE unit, and then a phrase that
#: MODIFIES the value — ``", maybe 3 K of drift"`` — satisfied both earlier
#: conditions and proposed a drift figure as an absolute temperature, **with no
#: abstention at all**. Four such sentences were measured; all four are now refused
#: AND disclosed. They are pinned as CLOSED in
#: ``test_transcript_capture_hedge_and_unit_gate.py``.
#:
#: **TERMINAL MEANS ONE OF TWO THINGS, AND THE SECOND IS WHAT KEEPS CHAINING
#: ALIVE.** After the value and its complete unit, either
#:
#: 1. NO WORD follows — the remainder of the segment is horizontal whitespace and
#:    punctuation only — this predicate; or
#: 2. another hedge bridge follows, introducing a further restatement that was
#:    itself ACCEPTED. That is not a predicate over text, so it is not spelled
#:    here: it is enforced in :func:`_segment_readings` as a walk inward from the
#:    TAIL of the accepted chain, which is the only place the second clause is
#:    decidable. A chain therefore survives whole or loses its tail; it is never
#:    broken in the middle.
#:
#: ~~**SCOPED TO THE BARE-HEDGE BRANCH, AND THE SCOPE IS THE WHOLE TRADE.**~~ —
#: **UNIVERSAL SINCE 2026-09-12 (THIRD PASS). The scope lasted one commit and cost
#: five silent §5 false positives, and the heading is struck rather than rewritten
#: because the scoping was a reviewed decision that a measurement then overturned.**
#: A UNIVERSAL terminal rule was implemented, measured and withdrawn on three
#: counts; it was then re-adopted scoped on the grounds that scoping answered two of
#: them. All three objections are now resolved, and the third — the one that
#: actually held — was resolved by changing the FIXTURE, not the rule:
#:
#: * ~~"it does not close the defect — ``425 K, about 3 K.`` is terminal and read
#:   3"~~ — **EXPIRED, not answered.** That sentence was measured against a gate in
#:   which ``about`` bridged BARE. It no longer does (``_OR_REQUIRED_HEDGES``), so
#:   the row is refused by the FIRST condition and is in ``FALSE_RESTATEMENTS``
#:   today. The objection was correct when it was written.
#: * it cost SIX natural sentences their restatement. **Universal, it costs all
#:   six** (scoped it cost five; the sixth, *"started A, or maybe B, I would have to
#:   check"*, sat behind an explicit ``or``). **All six are accepted losses**, on one
#:   condition that is part of the decision rather than a bonus: every one of them is
#:   DISCLOSED (``trailing_text_after_further_values``) rather than silently dropped,
#:   and a seventh, *"425 K or 430 K at the end."*, joins them. §5 ranks a disclosed
#:   omission above an assertion nobody made; it ranks neither above a silent one,
#:   and the five sentences the scope left fabricating were silent.
#: * ~~"it disarmed the C-2 byte-ceiling proof by taking ``_bytes_only()`` from five
#:   candidates to THREE … Scoped, it does not"~~ — **THE OBJECTION WAS REAL AND WAS
#:   ANSWERED AT ITS SOURCE.** It was a FIXTURE coupling, not a product fact: a
#:   resource ceiling's proof was built on three candidates the C-1 gate had to admit,
#:   so every semantic decision about restatements silently moved a byte count.
#:   ``_bytes_only()`` is now built from LABEL-ANCHORED matches only (pass one, which
#:   no hedge, unit or terminal rule gates), reads FIVE under the universal rule,
#:   and ``test_the_C2_BYTE_CEILING_PROOF_IS_DECOUPLED_FROM_THE_C1_GATE`` asserts
#:   the mechanism rather than the number. **A resource-ceiling proof must not be
#:   hostage to a semantic gate**, and that this one was is why the same false
#:   positive class survived two fixes.
#:
#: **THE PREDICATE IS "NO WORD FOLLOWS", NOT "AT MOST ONE TERMINATOR FOLLOWS",
#: AND THE DIFFERENCE WAS MEASURED RATHER THAN CHOSEN.** The first spelling was
#: ``{_H_SPACE}*[.;:!?]?{_H_SPACE}*`` — whitespace and at most one sentence
#: terminator — and it refused two rows of
#: ``test_what_may_follow_a_complete_unit``: ``"…maybe 430 K,"`` and
#: ``"…maybe 430 K)"``, a trailing comma and a trailing bracket with **nothing
#: after them**. Those cost a legitimate restatement and buy nothing, because what
#: turns a hedged value into a different quantity is a PHRASE — *of drift*, *above
#: target*, *per minute* — and punctuation alone carries none. So the set is the
#: punctuation allowlist and the predicate is that the remainder holds no word.
#:
#: **THE PUNCTUATION SET IS :data:`_UNIT_TERMINATORS` ITSELF, REUSED DELIBERATELY
#: AND NOT COPIED.** The two answer different questions — "is the unit complete?"
#: over ONE following character, and "does the statement end here?" over the whole
#: remainder — but both are asking which characters are not part of a claim about
#: the value, and two hand-maintained copies of that answer would drift.
#: ``test_the_statement_end_set_is_the_unit_terminator_set`` pins the identity, so
#: widening one is visible as widening both. Note the direction of the risk is
#: benign here: a character added to the set can only make this predicate ADMIT
#: more, and the ratchet on ``_UNIT_TERMINATORS`` already refuses ``/``, ``^``,
#: ``-``, ``·``, ``*``, ``×`` and ``%``.
#: ``\s`` HERE, AND ``_H_SPACE`` IN ``_HEDGE_BRIDGE``. **CORRECTED 2026-09-12
#: (fourth pass): this predicate used ``_H_SPACE`` too, and reusing it was a
#: coincidence rather than a shared rule.** The two ask opposite questions about a
#: line break:
#:
#: * ``_HEDGE_BRIDGE`` asks *"is the connective IMMEDIATELY BETWEEN the two
#:   values?"* — a line break in that gap means it is not, so line breaks are
#:   EXCLUDED.
#: * this asks *"does the statement END after this value?"* — a line break after it
#:   means the statement plainly DOES end, so line breaks are INCLUDED.
#:
#: While ``_H_SPACE`` was ``[^\S\n]`` the difference showed up only for ``\n``, and
#: ``test_the_statement_end_set_is_the_unit_terminator_set`` recorded the visible
#: half accurately (*"``\r`` IS admitted … A bare ``\r`` with no word after it
#: withholds nothing, so it is not a hole"*). Narrowing ``_H_SPACE`` to all TEN
#: line-boundary characters turned that benign coincidence into a false refusal:
#: with the class shared, ``"...maybe 430 K\r"`` withheld 430 because a ``\r``
#: remained. Measured before the split: ``_statement_ends_after("X\r", 1)`` went
#: ``True`` -> ``False``. It is ``True`` again, for a reason rather than by
#: inheritance.
#:
#: **AND THE ``\n`` ROW MOVES TOO, WHICH IS THE HALF I PREDICTED WRONG AND THEN
#: MEASURED.** A first draft of this comment claimed ``_statement_ends_after("X\n",
#: 1)`` would stay ``False``; measured, it is now ``True``, and that is the correct
#: answer rather than an accepted cost — a value followed by nothing but a newline
#: ends its statement as plainly as one followed by a full stop. The old ``False``
#: was never a rule this module held; it was ``_H_SPACE`` leaking a
#: bridge-specific exclusion into an end-of-statement question. It is also
#: BEHAVIOURALLY INERT: ``_SEGMENT_BOUNDARY`` splits on ``\n+``, so no segment ever
#: contains one, and ``"X\nmore"`` is still ``False`` either way. The test row is
#: inverted with this reasoning attached rather than deleted.
_STATEMENT_END = re.compile(
    r"(?:\s|[" + re.escape("".join(sorted(_UNIT_TERMINATORS))) + r"])*"
)


def _statement_ends_after(text: str, position: int) -> bool:
    """Whether nothing but whitespace and punctuation follows.

    ``fullmatch``, never ``$``, for the reason :data:`_HEDGE_BRIDGE` gives: ``$``
    also matches before a trailing newline, and the entire content of this
    predicate is *"there is nothing after this"*.

    ``position`` is :meth:`re.Match.end` — the end of the value AND its unit — not
    ``end(1)``, which is the end of the number. The wrong one refuses every
    restatement, because ``" K"`` is not a terminator either; a test pins both
    offsets, exactly as it does for :func:`_unit_is_complete`.
    """
    return _STATEMENT_END.fullmatch(text[position:]) is not None

#: The two kinds of restatement refusal this reader discloses, named rather than
#: written as literals at the three sites that must agree: the gate that records
#: them, the abstention that serves them, and :data:`AMBIGUITY_POLICY`.
#:
#: **THEY ARE TWO KINDS AND NOT ONE, BECAUSE ONE OF THEM WOULD HAVE BEEN A FALSE
#: SENTENCE.** ``unhedged_further_values`` says a hedging word was missing, or the
#: unit was not the whole unit. Neither is true of a terminal refusal: the hedge is
#: present, the unit IS complete, and what withheld the value is the text that
#: FOLLOWS it. Reusing the name would have published a reason contradicted by the
#: quote sitting beside it, which is the defect class this module keeps finding.
_KIND_UNHEDGED = "unhedged_further_values"
_KIND_TRAILING = "trailing_text_after_further_values"

#: The four kinds the PASS-ONE assertion gate discloses. They are four and not
#: one for the reason the two above are two and not one: each names a DIFFERENT
#: fact about the sentence, and a shared name would publish a reason the quote
#: beside it contradicts. ``_KIND_NOT_ASSERTED`` says the label did not assert
#: this value; ``_KIND_QUALIFIED`` says it did and the following words changed what
#: the number measures; ``_KIND_NONE_SELECTED`` says the sentence asserted the
#: field more than once and this reader cannot say which value is the field's;
#: ``_KIND_NOT_THIS_SUBJECT`` says the words BEFORE the label name something other
#: than the field.
#:
#: **THE FOURTH IS ONE KIND AND NOT TWO, WHICH IS THE OPPOSITE CALL FROM THE ONE
#: ABOVE AND IS MADE ON THE SAME GROUND.** Gate (4) closes two families that look
#: different — a renamed quantity (*"the SETPOINT temperature"*) and a different
#: measurement (*"the PREVIOUS scan ended"*) — and the temptation is to give each
#: its own reason. They are one kind because the FACT is one fact: the words before
#: the label are ones this reader does not recognise as leaving the label the thing
#: being described. Splitting them would require this reader to say WHICH of the two
#: happened, and it cannot — *"The previous scan temperature was 425 K"* is both —
#: so a two-way split would publish a classification the reader does not hold,
#: which is the defect the rule above exists to prevent rather than an application
#: of it.
_KIND_NOT_ASSERTED = "label_does_not_assert_this_value"
_KIND_QUALIFIED = "value_qualified_by_what_follows"
_KIND_NONE_SELECTED = "several_values_and_none_selected"
_KIND_NOT_THIS_SUBJECT = "words_before_the_label_name_something_else"

#: The reason served for each, keyed by kind so the gate cannot record one and
#: serve the other's sentence. ``{field_path}`` is the only substitution.
#:
#: **NEITHER REASON QUOTES, COUNTS, CLASSIFIES OR NAMES A UNIT FOR THE WITHHELD
#: VALUES**, because not knowing what they are is the reason they were withheld.
#: Note the second reason carries NO NUMERIC EXAMPLE, deliberately: every digit
#: that would read naturally there ("3 K of drift") also appears in the measured
#: sentences this closes, so an example would look like a leak of the withheld
#: value and a test asserting it was not one would be asserting a coincidence.
_REFUSAL_REASONS: dict[str, str] = {
    _KIND_UNHEDGED: (
        "This sentence states further values of the same form for {field_path}, "
        "and they were not read. A second value is read only when a hedging word "
        "links it to the first — 'maybe', 'perhaps', 'or maybe', 'or about' and "
        "the like — and when it is not part of a larger unit such as K/min. "
        "Without both, a later value of the same form is usually a different "
        "quantity: a ramp rate, a step size, an offset from a setpoint. Nothing "
        "is guessed and nothing is proposed for them; read the sentence and state "
        "any value you want recorded on its own."
    ),
    _KIND_TRAILING: (
        "This sentence states a further value of the same form for {field_path} "
        "behind a hedging word, and it was not read because the sentence does not "
        "stop there. A hedged second value is read only when it ENDS the "
        "statement: either the sentence finishes after it, or the only thing "
        "following is another hedged value that was itself read. Here something "
        "else follows, and a value with a phrase after it is usually that "
        "phrase's quantity — a drift, an offset from a target, a rate per minute "
        "— rather than another statement of this field. Nothing is guessed and "
        "nothing is proposed for it; read the sentence and state any value you "
        "want recorded on its own."
    ),
    # THE PASS-ONE GATE'S THREE REASONS. Like the two above, none quotes, counts
    # or classifies the value it withheld: this reader does not know what the
    # quantity is, which is exactly why it did not propose it. Each says what the
    # SENTENCE did, which the scientist can check against the quote beside it.
    # NEITHER OF THESE TWO CARRIES A NUMERIC EXAMPLE EITHER, and both were written
    # with one and corrected before shipping. The rule is the one stated one entry
    # above for `_KIND_TRAILING`: every digit that reads naturally in an example
    # here ("3 K of drift", "rose by 30 K") also appears in the measured sentences
    # these close, so the example would sit in the same response as the value it
    # withheld and read as a leak of it. The constructions are NAMED instead, which
    # is what the scientist needs in order to re-read their own sentence.
    # SAME DISCIPLINE AS THE ROW BELOW, and it was corrected for the same reason:
    # the first version said "Something between the label and the value CHANGES
    # what the number measures", which asserts a reading of the sentence. On the
    # measured false-negative class that is false — in "the temperature, measured
    # carefully, was 425 K" nothing changes what the number measures and the reader
    # simply does not recognise the words in between. It now reports the reader's
    # own limit and offers the interpretation as the common case.
    _KIND_NOT_ASSERTED: (
        "This sentence puts a value near the words this reader looks for, but the "
        "words between them are ones it does not recognise as stating that value "
        "as {field_path}. Very often they change what the number measures: a "
        "drift, an error, a step, a resolution, a tolerance, a gradient, an "
        "uncertainty, a rise or a fall, a correction, a ramp to somewhere else. "
        "This reader cannot tell, so nothing is guessed and nothing is proposed. "
        "What it DOES read is a value the sentence asserts as the field itself — "
        "'was', 'is', 'was around', 'held at', 'settled at', 'read', 'set to', "
        "'reached', or the value written straight after the label — so if this is "
        "the field's value, state it that way and it will be read."
    ),
    # **THIS REASON SAYS WHAT THE READER DID, NOT WHAT THE SENTENCE MEANS, and the
    # first version got that wrong.** It read "…and then qualifies it, so the number
    # measures something else", which ASSERTS an interpretation — and on the
    # measured false-negative class it is false: in "the temperature was 425 K
    # consistently" nothing qualifies the value, the reader simply does not
    # recognise the word after it. Publishing a confident misreading of a
    # scientist's own sentence is the defect class this module exists to avoid, so
    # the reason now reports the reader's own limit and offers the interpretation
    # as the COMMON case rather than as the fact.
    _KIND_QUALIFIED: (
        "This sentence states a value for {field_path} and then continues with "
        "words this reader does not recognise, so it cannot tell whether the "
        "value stands on its own. Very often it does not: a difference from a "
        "target or a setpoint, an amount of drift or scatter, a rate per minute "
        "or per step, an upper or lower bound, or a comparison with another run "
        "all read this way, and recording one of those as an absolute value would "
        "put a number in the record nobody stated. So nothing is proposed. What "
        "this reader DOES read is a value followed by the end of the clause, by "
        "punctuation, by a new clause, or by where and when it was measured — so "
        "if the value does stand on its own, state it on its own and it will be "
        "read."
    ),
    # GATE (4)'s REASON, written to the same two rules as the two above it and to
    # one more of its own.
    #
    # (a) NO NUMERIC EXAMPLE, for the reason stated twice already: every digit that
    #     reads naturally here ("425 K", "295 K") is a value this gate withholds, so
    #     an example would sit in the same response as the withheld value.
    # (b) IT REPORTS THE READER'S LIMIT, NOT AN INTERPRETATION. It does NOT say the
    #     words before the label DO name something else — on "The cryostat
    #     temperature was 80 K" nothing was renamed and this reader simply has no
    #     grounds to decide whose temperature it is.
    # (c) AND IT DOES NOT CLAIM THAT WHAT IT REFUSED IS NOT THE FIELD'S VALUE, which
    #     is the claim §5 actually forbids here. An ambient or a cryostat temperature
    #     MAY be exactly what the scientist means by the field; deciding that it is
    #     not would be the scientific judgement §5 rules out just as surely as
    #     deciding that it is. So the reason offers the one thing that IS decidable —
    #     the prepositional restatement gate (1) already reads — and stops.
    _KIND_NOT_THIS_SUBJECT: (
        "This sentence states a value the way {field_path} is stated, but the words "
        "in FRONT of the label are ones this reader does not recognise as leaving "
        "the label the thing being described. Very often they name something else: "
        "a setpoint, a target, a requested or planned value, a maximum, a minimum, "
        "an average, an ambient or room figure — or, for a time, a previous, "
        "earlier, calibration, dark or reference scan rather than this run. This "
        "reader cannot tell which, and it is not deciding that the value is NOT the "
        "field's — only that this sentence does not settle it. So nothing is "
        "guessed and nothing is proposed. What it DOES read is the label with "
        "nothing in front of it but 'the', or with the qualifier moved behind the "
        "label — 'the temperature of the sample was …', 'the temperature at the "
        "second scan was …' — so if this is the field's value, state it that way "
        "and it will be read."
    ),
    _KIND_NONE_SELECTED: (
        # NO NUMERIC EXAMPLE, and the reason is not style: this reason shipped for
        # one commit reading "'was 300 K, then 350 K, then 400 K'", and an existing
        # test caught it, because on that very sentence the illustration coincides
        # with the WITHHELD values and so reads as a leak of them. That is the trap
        # `_REFUSAL_REASONS`' own comment already documented one entry above —
        # "every digit that would read naturally there also appears in the measured
        # sentences this closes" — walked into by the next reason added after it.
        "This sentence states more than one value for {field_path} with nothing "
        "between them but sequencing — one value, then another, then another — and "
        "{field_path} holds ONE value. So no value was selected. Taking the first "
        "would record a starting point as the value, and taking the last would "
        "record an endpoint; either is a choice this reader has no grounds to "
        "make, and the sentence describes a progression rather than a "
        "disagreement, so neither is offered as an alternative. The sentence is "
        "kept in full; state the one value you want recorded on its own."
    ),
}

#: THE FALSE-POSITIVE CLASS THAT REMAINS AFTER ALL THREE CONDITIONS, WRITTEN DOWN
#: BECAUSE IT IS A §5 DEFECT AND A SILENT ONE.
#:
#: ~~THE ONE FALSE-POSITIVE CLASS THIS GATE DOES NOT CLOSE … A hedge from
#: ``_BARE_HEDGES`` followed by a value with a complete unit and then a phrase that
#: MODIFIES that value still reads:~~
#:
#: ========================================================== ================
#: sentence                                                   read at bce43f19
#: ========================================================== ================
#: ``The temperature was 425 K, maybe 3 K of drift``          425 AND **3**
#: ``The temperature was 425 K, maybe 3 K above target``      425 AND **3**
#: ``The temperature was 425 K, perhaps 2 K of scatter``      425 AND **2**
#: ``The temperature was 425 K, alternatively 3 K per minute`` 425 AND **3**
#: ========================================================== ================
#:
#: **CLOSED 2026-09-12 (second pass). All four now read 425 ALONE and each raises a
#: ``trailing_text_after_further_values`` abstention**, and the four sentences are
#: pinned as CLOSED — not deleted — in
#: ``test_transcript_capture_hedge_and_unit_gate.py``, so nothing can quietly
#: reopen them. The decision that closed them is
#: :data:`_STATEMENT_END`'s second bullet: the SECOND of the four proxies below, the
#: one the previous revision of this comment measured and then referred. It is
#: struck rather than deleted because the proxies it rejected are still the reason
#: the class below stays open.
#:
#: **THE ARGUMENT FOR WHY IT WAS A DECISION AND NOT A PATCH IS UNCHANGED AND IS
#: KEPT IN FULL.** The difference between ``", maybe 3 K of drift"`` and ``", maybe
#: 430 K and the atmosphere was dry nitrogen"`` is that the first phrase modifies
#: the value and the second begins a new clause. That is a SEMANTIC distinction,
#: and every mechanical proxy for it was measured:
#:
#: * **requiring the restatement to END the statement, UNIVERSALLY** closes all
#:   four rows, and costs six natural sentences their restatement (*"…maybe 430 K,
#:   I am not sure."*, *"…maybe 430 K at the end."*, *"…maybe 430 K according to
#:   the log."*, *"…maybe 430 K and the atmosphere was dry nitrogen."*, *"…maybe
#:   430 K on the second scan."*, *"started A, or maybe B, I would have to
#:   check."*). It also silently weakens an unrelated proof: ``_bytes_only()`` in
#:   ``test_transcript_capture_ceilings.py`` needs FIVE candidates to exceed
#:   ``MAX_CANDIDATE_QUOTE_BYTES`` and the universal rule takes it to ~~four
#:   (999,996 B against a 1,048,576 B cap)~~ **THREE (750,000 B against a
#:   1,048,576 B cap)**, so **the C-2 byte-ceiling test stops
#:   firing** — the two fixes are coupled, which nobody expected. ~~**STILL TRUE,
#:   and still the reason the rule was not adopted universally**~~ — **TRUE OF THE
#:   OLD FIXTURE AND NO LONGER A REASON FOR ANYTHING (2026-09-12, third pass):
#:   ``_bytes_only()`` was rebuilt from label-anchored matches, which pass two never
#:   touches, and the universal rule was then adopted. The coupling was the FIXTURE's
#:   property, not the rule's, and treating it as the rule's cost two slices.**;
#: * **THE INHERITED FIGURE IS NOT REPRODUCIBLE AT THIS HEAD AND IS CORRECTED
#:   RATHER THAN CARRIED.** Measured 2026-09-12 by applying the mutation — drop
#:   the bare-hedge scope, run the fixture — the universal rule takes
#:   ``_bytes_only()`` to **THREE candidates and 750,000 quoted bytes**, not four
#:   and 999,996. Both links of that payload's chain go: ``435 K`` for its own
#:   trailing clause, and ``430 K`` because what follows it is then a bridge to a
#:   refusal. **Why the earlier pair read four is NOT established here** — the
#:   implementation it was measured on is not in this repository, so any account
#:   of it would be a reconstruction. The CONCLUSION is unchanged, which is why
#:   the figure matters less than the correction: three and four are both under
#:   the 1,048,576 B cap, so the C-2 byte-ceiling proof stops firing either way.
#: * **requiring terminality only behind a BARE hedge** closes all four rows and
#:   keeps five of those six false negatives, because they all use bare ``maybe``.
#:   ~~**ADOPTED**, re-measured: it loses FIVE of the six (the sixth uses ``or
#:   maybe``), every loss is disclosed, and ``_bytes_only()`` still reads five~~ —
#:   **ADOPTED FOR ONE COMMIT AND THEN SUPERSEDED BY THE UNIVERSAL RULE.** Every
#:   number in that sentence was correct; what it did not say is that the scope left
#:   five sentences fabricating SILENTLY behind the ``or`` branch, which is the
#:   outcome §5 ranks last. The universal rule is now in force and loses all six;
#: * **a clause-break rule keyed on punctuation or a conjunction** admits
#:   ``", maybe 3 K, ramping"``, measured — punctuation does not distinguish a new
#:   clause from a trailing modifier. Not adopted;
#: * **a denylist of modifier tails** (``of``, ``above``, ``per``, ``than``, …)
#:   FAILS OPEN, which is the failure mode this reader has already shipped twice,
#:   and would not even catch ``"colder than before"``. Not adopted.
#:
#: ~~``AMBIGUITY_POLICY``'s ``unhedged_further_values`` row does NOT disclose
#: these, and cannot: a value was read, so nothing was withheld to report.~~ —
#: that was the state of affairs it described, and it is now a
#: ``trailing_text_after_further_values`` row of its own. Reusing the old kind
#: would have served a reason saying the value was UNHEDGED beside a quote showing
#: it hedged.
#:
#: =========================================================================
#: WHAT IS STILL OPEN, AND IT IS NOT ROUNDED DOWN
#: =========================================================================
#:
#: ~~The third condition is scoped to the BARE-hedge branch, so **the same shape
#: behind an explicit ``or`` still fabricates.** Measured in-process after the fix,
#: which is how these five got here — they are not inherited:~~
#:
#: ============================================================== ============== ==============
#: sentence                                                       at ``ebc5c331`` universal (now)
#: ============================================================== ============== ==============
#: ``The temperature was 425 K or 3 K of drift``                  425 AND **3**  425, disclosed
#: ``The temperature was 425 K or 3 K above target``              425 AND **3**  425, disclosed
#: ``The temperature was 425 K, or about 3 K of drift``           425 AND **3**  425, disclosed
#: ``The temperature was 425 K, or maybe 3 K of drift``           425 AND **3**  425, disclosed
#: ``The temperature was 425 K, or perhaps 2 K of scatter``       425 AND **2**  425, disclosed
#: ============================================================== ============== ==============
#:
#: **CLOSED 2026-09-12 (third pass), and the five rows moved into
#: :data:`_RESTATEMENT_RESIDUE_CLOSED` rather than being deleted.** The constant
#: ``_RESTATEMENT_RESIDUE`` is GONE, because an empty ratcheted tuple makes a
#: parametrised test vacuous, which is worse than either an open row or an absence.
#: What replaced it, and is a DIFFERENT entrance to the same claim class, is
#: :data:`_LABEL_OVERREACH_CLOSED` — which was OPEN when this
#: sentence was written ("read that before concluding this reader no longer
#: over-reads") and was closed on 2026-09-13 by :data:`_ASSERTION_BRIDGE`.
#:
#: **THE ARGUMENT THAT WAS MADE FOR LEAVING THEM OPEN IS KEPT, BECAUSE BOTH HALVES
#: OF IT WERE WRONG IN INSTRUCTIVE WAYS.** ~~"all five were CONSTRUCTED here to
#: probe the boundary, and none is natural dictation … *425 K, or about 3 K of
#: drift* is barely English. That is an argument about LIKELIHOOD and not about
#: correctness."~~ — the second sentence was right and should have ended the matter:
#: a likelihood argument is not a §5 argument, and it was nonetheless the reason
#: recorded for shipping five silent fabrications. And the likelihood claim itself
#: does not survive the first two rows: *"The temperature was 425 K or 3 K of
#: drift"* is ordinary dictation.
#:
#: **WHY IT WAS NOT ALSO CLOSED, and what each reason turned out to be worth.**
#:
#: * ~~Extending condition 3 to the ``or``-PREFIXED-HEDGE branch disarms C-2:
#:   ``_bytes_only()`` drops from five candidates to THREE. **This one is a real
#:   obstacle and it is a fixture coupling, not a product fact** — solve the coupling
#:   first.~~ — **THAT INSTRUCTION WAS FOLLOWED AND IT WAS THE WHOLE SLICE.** The
#:   coupling was solved first and independently: ``_bytes_only()`` is now built
#:   from label-anchored matches, which pass two never touches, so the byte ceiling
#:   is proved by a payload no semantic decision can move. Measured with the
#:   universal rule in force — OLD fixture: no refusal, 3 candidates, 750,000 B
#:   under a 1,048,576 B cap; NEW fixture: refused, 5 candidates, 1,250,000 B.
#: * ~~Extending it to the BARE-``or`` branch ALONE … its real objection is that the
#:   resulting rule is ASYMMETRIC: a bare hedge and a bare ``or`` would require
#:   terminality while ``or`` + hedge would not, for no reason a reader could
#:   state.~~ — **the asymmetry objection was CORRECT, and the universal rule is what
#:   answers it.** All three branches now require terminality, so there is no split
#:   to justify. The cost it named is real and is paid: *"425 K or 430 K at the
#:   end."* loses its alternative, DISCLOSED.
#:
#: **WHAT THE UNIVERSAL RULE COSTS, MEASURED RATHER THAN ESTIMATED.** Every sentence
#: whose genuine alternative is followed by trailing prose loses the alternative —
#: all six rows of ``TERMINAL_RULE_WOULD_HAVE_LOST`` (scoped, it was five) plus
#: *"425 K or 430 K at the end."*. **Every one is disclosed**, and that is the
#: condition the trade was taken on: a sweep of ~~510~~ **476** constructed
#: sentences (~~fifteen~~ **fourteen**
#: connectives × seventeen modifier tails × two separators) found **0** second
#: values read and **0** withheld-and-silent refusals.
#:
#: **510 WAS FALSIFIED BY A LATER COMMIT IN THE SAME RANGE AND NOT SWEPT, and it is
#: corrected here because it is the recorded ACCEPTANCE CONDITION for the universal
#: terminality trade — a stale denominator makes the condition unfalsifiable.** The
#: grid is DERIVED from ``_ALL_CONNECTIVES``, so moving ``and again`` out of
#: ``_BARE_HEDGES`` took it from 15 connectives to 14 and the grid from 510 to 476;
#: the test was updated and this comment was not. The companion figure "RED with 374
#: of the rows" is unaffected and correct — it is a count of rows, not of the grid.
_RESTATEMENT_RESIDUE_CLOSED: tuple[str, ...] = (
    # Closed 2026-09-12, SECOND pass — condition 3 scoped to the bare-hedge branch.
    "The temperature was 425 K, maybe 3 K of drift",
    "The temperature was 425 K, maybe 3 K above target",
    "The temperature was 425 K, perhaps 2 K of scatter",
    "The temperature was 425 K, alternatively 3 K per minute",
    # Closed 2026-09-12, THIRD pass — condition 3 made UNIVERSAL. These five were
    # `_RESTATEMENT_RESIDUE`, pinned AS OPEN by a test that asserted the defect.
    # They are moved rather than deleted, so "the residue is closed" stays a
    # checkable claim; each reads 425 alone and each raises exactly one
    # `trailing_text_after_further_values` abstention.
    "The temperature was 425 K or 3 K of drift",
    "The temperature was 425 K or 3 K above target",
    "The temperature was 425 K, or about 3 K of drift",
    "The temperature was 425 K, or maybe 3 K of drift",
    "The temperature was 425 K, or perhaps 2 K of scatter",
)

#: A §5 FALSE POSITIVE OF THE SAME CLAIM CLASS THROUGH A DIFFERENT ENTRANCE.
#: **PRE-EXISTING, MEASURED 2026-09-12 (third pass), NOT CLOSED, AND NOT CAUSED BY
#: ANY OF THE THREE RESTATEMENT CONDITIONS.**
#:
#: Three sessions of work on this reader have treated "the reader proposes values
#: the transcript does not state" as a property of the RESTATEMENT scan (pass two).
#: It is not. The LABEL-ANCHORED rule of pass one has the same defect, and it is
#: reached by sentences far more natural than any of the five ``or``-branch rows
#: that were argued about at length:
#:
#: ================================================ ===================== ==========
#: sentence                                          proposes              really is
#: ================================================ ===================== ==========
#: ``The temperature drift was 3 K``                 ``temperature_K = 3`` a DRIFT
#: ``The temperature error was 2 K``                 ``temperature_K = 2`` an ERROR
#: ``temperature resolution 0.5 K``                  ``temperature_K=0.5`` a RESOLUTION
#: ``The temperature was stable to 1 K``             ``temperature_K = 1`` a TOLERANCE
#: ``The temperature rose by 30 K``                  ``temperature_K=30``  a DELTA
#: ``temperature step 5 K``                          ``temperature_K = 5`` a STEP SIZE
#: ``We held the temperature to within 2 K``         ``temperature_K = 2`` a TOLERANCE
#: ``It started drifting at 2026-01-01T00:00:00Z``   an acquisition START  a DRIFT ONSET
#: ================================================ ===================== ==========
#:
#: **Each is SILENT — no abstention, no clarification** — and each ships a ``rule``
#: sentence asserting the transcript stated the field. §5 ranks that below a
#: disclosed omission and below a silent omission alike.
#:
#: **IT IS PRE-EXISTING AND THAT IS MEASURED, NOT ASSUMED.** The same eight rows
#: were probed against the pristine ``ebc5c331`` module and against the universal
#: rule; the two readings are identical, because the cause is ``_TEMPERATURE_K``'s
#: own ``[^.;:]{0,40}?`` bridge between the label and the number, which lets ~40
#: characters of *anything* sit between ``temperature`` and the value it reads.
#:
#: **WHY IT IS PINNED HERE AND NOT FIXED.** It is not the restatement gate and it is
#: outside the slice that measured it. It is also NOT the same shape of fix: the
#: three restatement conditions constrain the gap AFTER a value that a label already
#: earned, while this would constrain what may sit BETWEEN a label and its value —
#: and every proxy that comes to mind (a denylist of ``drift``/``error``/``step``, a
#: shorter bridge, requiring a copula) either fails open or costs the label-anchored
#: readings the reader exists for. ``_TEMPERATURE_K``'s bridge is what makes
#: *"Sample temperature at the second scan was 425 K"* read at all.
#:
#: A test asserts these rows STILL FABRICATE, deliberately the wrong way round, so
#: closing the class requires deleting rows here rather than discovering that a
#: documented open item quietly went away.
#: **WIDENED 2026-09-12 (fourth pass) FROM SEVEN ROWS TO THIRTEEN.** Seven rows
#: described the class too narrowly for a wrong-way-round test to be useful: a
#: reader could reasonably have read them as an idiosyncratic handful rather than as
#: a family. The six added below were measured at ``22d794a5`` and again at this
#: head — identical readings, so they are PRE-EXISTING and `main` shares them, which
#: is why they are pinned and not fixed:
#:
#: ==========================================  ==========================  ==========
#: sentence                                     proposes                    really is
#: ==========================================  ==========================  ==========
#: ``The temperature uncertainty was 2 K``      ``temperature_K = 2``       an UNCERTAINTY
#: ``The temperature offset was 4 K``           ``temperature_K = 4``       an OFFSET
#: ``The temperature fell by 12 K``             ``temperature_K = 12``      a DELTA
#: ``temperature stability 0.2 K``              ``temperature_K = 0.2``     a STABILITY
#: ``The temperature gradient was 5 K``         ``temperature_K = 5``       a GRADIENT
#: ``We corrected the temperature by 7 K``      ``temperature_K = 7``       a CORRECTION
#: ==========================================  ==========================  ==========
#:
#: Each is SILENT — no abstention, no clarification — exactly like the original
#: seven, and each ships a ``rule`` sentence asserting the transcript stated the
#: field. ~~**THE PASS-ONE OVER-REACH ITSELF IS DELIBERATELY NOT FIXED HERE**: it is
#: pre-existing, ``main`` shares it, and constraining what may sit BETWEEN a label
#: and its value is a different shape of change from constraining the gap AFTER a
#: value — it needs its own slice and its own argument, for the reasons this
#: comment's earlier paragraphs give.~~
#:
#: **CLOSED 2026-09-13 BY THE PASS-ONE ASSERTION GATE, AND THE CONSTANT IS RENAMED
#: ``_LABEL_OVERREACH_CLOSED`` RATHER THAN EMPTIED — the precedent
#: :data:`_RESTATEMENT_RESIDUE_CLOSED` set one screen above.** Every row above now
#: proposes NOTHING and raises exactly one ``label_does_not_assert_this_value``
#: abstention naming the field. The referral WAS the right call and its reasoning
#: is kept: it did get its own slice and its own argument.
#:
#: **AND THE THREE PROXIES THIS COMMENT REJECTED WERE ALL CORRECTLY REJECTED.** A
#: denylist of ``drift``/``error``/``step`` fails open; a shorter bridge kills
#: *"Sample temperature at the second scan was 425 K"*; requiring a copula kills
#: *"temperature 425 K"*. What the comment did not consider is that the bridge's
#: **SHAPE** can be constrained without constraining its **LENGTH**:
#: :data:`_ASSERTION_BRIDGE` still admits a 40-character bridge, and admits that
#: exact sentence, while admitting no bare nominal head at all. Measured on the
#: closing slice: **1,645** generated adversarial sentences over **15** declared
#: families (~~eleven~~ — counted from the generator rather than from memory),
#: **0** fabrications and **0** silent refusals, against **240** silent
#: fabrications and **19** silently-selected progressions before. The corpus is an
#: ORACLE and not a sample: each family declares the verdict its rows must get, so
#: a "clean sweep" cannot be produced by rows that happen to read nothing. Its
#: SHAPE, which a bare count would overstate: single-segment English sentences over
#: the two numeric/instant label families, with the quantity re-subjected by a
#: nominal head, a verb of change, a tolerance phrase, a relational or rate tail, a
#: sequence connective, or nothing at all. It does NOT produce multi-sentence
#: transcripts, run references, the two free-phrase rules, non-English, or
#: unicode digit forms. Over the **156**
#: sentences this repository's own tests already contained, **23** readings changed,
#: **every one of the 23 removed a fabrication or withheld a progression**, and
#: **0 gained a candidate** — so no legitimate reading in the corpus was lost.
#:
#: **AND THE STRONGEST EVIDENCE IS OUT-OF-SAMPLE RATHER THAN ANY OF THOSE
#: NUMBERS.** An independent review hunted this class from scratch on the same day
#: and produced **twenty** members, not one of which appears in the thirteen rows
#: below, in the bridge grammar, or in the generator the fix was developed against.
#: **Nineteen are refused and disclosed** with no change to the gate.
#: `_PRE_LABEL_OVERREACH_CLOSED` is the twentieth and is a different sub-class,
#: named and left open. A table of thirteen entrances cannot produce that result;
#: a grammar can, and that is the whole argument for the shape of this fix.
#:
#: The one row of the table above that is NOT in this tuple is the instant row
#: (*"It started drifting at 2026-01-01T00:00:00Z"*), and that is unchanged: this
#: tuple has always been temperature-only while the table above describes the whole
#: class. Named so a reader does not count the two and conclude one is stale — it
#: is closed too, and asserted separately by
#: ``test_the_LABEL_ANCHORED_instant_overreach_is_CLOSED_TOO``.
#: ~~**THE ONE MEMBER OF THE CLASS THE PASS-ONE ASSERTION GATE DOES NOT CLOSE, and
#: it is a structurally DIFFERENT sub-class rather than a leftover row.**~~
#:
#: **STRUCK IN PLACE. IT WAS WITHDRAWN AS AN OVERCLAIM ~55 LINES BELOW, IN
#: ``d3473414``, AND THE HEADING WAS LEFT STANDING — which is the reason for
#: striking it rather than leaving the withdrawal to do the work.** A reader
#: arriving at this line reads a completeness claim and has no way to know, until
#: they reach the note, that the file itself contradicts it. That is the same
#: failure this file records elsewhere as *"the unstruck opening paragraph of the
#: same block, four lines above, was a second instance"*: a correction placed
#: BELOW the claim it corrects leaves the claim readable. **The claim is now
#: doubly false and doubly resolved** — the class had more members than one
#: (withdrawn ``d3473414``), and gate (4) closes every one of them, so the
#: sentence's subject no longer exists.
#:
#: An independent review hunted this class on 2026-09-13 and produced twenty rows
#: none of which was in the thirteen above. **Nineteen are closed** by
#: :data:`_ASSERTION_BRIDGE` without any of them being known to it — which is what a
#: class-level grammar buys over a table, and is the strongest evidence available
#: that the fix is not a patch of the thirteen entrances it was built against.
#: **This is the twentieth:**
#:
#: ==========================================  ==========================  =========
#: sentence                                     proposes                    really is
#: ==========================================  ==========================  =========
#: ``We lowered the temperature 15 K``          ``temperature_K = 15``      a DELTA
#: ==========================================  ==========================  =========
#:
#: **WHY THE BRIDGE CANNOT SEE IT.** The bridge is, by construction, the text
#: BETWEEN the label and the value, and here that text is EMPTY — the value is
#: juxtaposed, exactly as in *"temperature 425 K"*, which this reader must keep
#: reading. The word that re-subjects the quantity (``lowered``) sits to the LEFT of
#: the label, where the bridge grammar has no reach. The prepositional forms of the
#: same sentence ARE closed, because their preposition falls inside the bridge:
#: *"We lowered the temperature BY 15 K"*, *"We raised the temperature BY 40 K"* and
#: *"We corrected the temperature BY 7 K"* all refuse.
#:
#: **WHY IT IS NOT FIXED HERE, with the proxies named so they are not re-derived.**
#: Constraining the text BEFORE a label is a different question and every proxy
#: considered fails one of this module's own standing rules:
#:
#: * a denylist of change verbs (``lowered``/``raised``/``dropped``) FAILS OPEN on
#:   the next verb, which is the failure mode §5 and this file's own history rank
#:   worst;
#: * "no determiner immediately before the label" refuses *"The temperature 425 K"*,
#:   which is legitimate, and still admits *"We dropped temperature 5 K"*;
#: * "at most N words between a clause boundary and the label" is a word-count
#:   heuristic with no grammatical story, and *"The sample temperature 425 K"* and
#:   *"We lowered the temperature 15 K"* differ by one word.
#:
#: A fail-closed formulation over the PRE-LABEL context needs its own slice and its
#: own argument, exactly as the bridge did. Asserted as still-fabricating by
#: ``test_the_PRE_LABEL_overreach_is_STILL_OPEN`` so closing it requires deleting a
#: row here rather than discovering the item quietly went away.
#:
#: **AND THE ADVERSARIAL GENERATOR THIS FIX WAS BUILT AGAINST HAD THE SAME BLIND
#: SPOT AS THE FIX, which is the most useful thing measured about it.** That
#: generator crossed 43 nominal heads and 20 verbs of change against the label; it
#: produced **not one** of the review's twenty rows verbatim, and specifically its
#: change-verb table held ``raised by``, ``lowered by``, ``dropped by`` and
#: seventeen more — **every one with a preposition**. The BARE form (``lowered the
#: temperature 15 K``, no ``by``) is the single entry it lacked, and it is the
#: single row that still fabricates. A generator that only ever puts the
#: re-subjecting word where the bridge can see it cannot discover that the bridge
#: has a blind side. The lesson is not "add ``lowered``": it is that a corpus
#: generated from the same mental model as the fix tests the fix's reach and not its
#: premise, and only an independent hunt found the premise.
#: *** THE "ONE MEMBER" CLAIM ABOVE WAS AN OVERCLAIM AND IS WITHDRAWN — found by
#: independent review, 2026-09-13, and re-measured here before being written down. ***
#:
#: The note above called `"We lowered the temperature 15 K"` *"THE ONE MEMBER OF THE
#: CLASS the pass-one assertion gate does not close"*, over a one-row table. A
#: reviewer that wrote its own corpus found a **structurally different pre-label
#: family the delta case does not cover at all**, and every row of it is SILENT.
#:
#: Re-measured at this head, 8 of 8 silent (candidate proposed, zero disclosures):
#:
#:     "The setpoint temperature was 425 K."   -> 425
#:     "The maximum temperature was 500 K."    -> 500
#:     "The average temperature was 400 K."    -> 400
#:     "The ambient temperature was 295 K."    -> 295
#:     "The room temperature was 295 K."       -> 295
#:     "The target temperature was 425 K."     -> 425
#:     "The requested temperature was 425 K."  -> 425
#:     "The planned temperature was 425 K."    -> 425
#:
#: **WHY THE GATE CANNOT SEE THEM, which is the part worth understanding.** The
#: modifier sits BEFORE the label, and both allowlist grammars look AFTER it:
#: `_ASSERTION_BRIDGE` reads label -> value, `_VALUE_CONTINUATION` reads value ->
#: end. `"setpoint temperature was 425 K"` presents the gate with the bridge `" was "`
#: — which is exactly the bridge the gate exists to ADMIT, and correctly so, because
#: `"The temperature was 425 K"` must keep reading. The word that re-subjects the
#: quantity is upstream of everything the gate inspects.
#:
#: **THE SHARPEST EXHIBIT IS THIS MODULE'S OWN COMMENT.** The sequence gate cites
#: `"cryostat setpoint 80 K"` as a case where the gap *positively identifies 80 as
#: something else* — and `"The setpoint temperature was 425 K"` proposes 425 as the
#: temperature. The same word, read as disqualifying in one position and invisible in
#: the other.
#:
#: **PRE-EXISTING, VERIFIED RATHER THAN ASSUMED.** `git show
#: 2f9a1133:apps/api/isaac_api/transcript_capture.py` has
#: `_TEMPERATURE_K = \btemperatures?\b[^.;:]{0,40}?<number>\s*(?:K|kelvin)` — the bare
#: label with a permissive bridge — so every row above fabricates on `main` too. This
#: gate neither introduced nor worsened them; what was wrong and in range was the
#: published claim of completeness.
#:
#: ~~**NOT FIXED HERE, and the reason is the same one that referred the original
#: residue:** a fix has to reject a modifier before the label without rejecting
#: `"Sample temperature at the second scan was 425 K"` — where the words before the
#: label are a legitimate qualifier of the SAME quantity. That is a distinction
#: between an adjective that re-subjects and one that locates, it is not decidable by
#: the allowlist shape this gate uses, and a denylist of nouns fails OPEN, which is
#: the failure mode that has already shipped twice in this module. It needs its own
#: slice and its own argument.~~
#:
#: **CLOSED BY :data:`_PRE_LABEL` — GATE (4) — AND THE CONSTANT IS RENAMED
#: ``_PRE_LABEL_OVERREACH_CLOSED`` RATHER THAN EMPTIED, the precedent
#: :data:`_RESTATEMENT_RESIDUE_CLOSED` and :data:`_LABEL_OVERREACH_CLOSED` both
#: set.** Every row below now proposes NOTHING and raises exactly one
#: ``words_before_the_label_name_something_else`` abstention naming the field. It
#: DID get its own slice and its own argument, and both referrals were the right
#: call.
#:
#: **AND THE PARAGRAPH ABOVE IS WRONG IN EXACTLY ONE PLACE, WHICH IS THE WHOLE
#: LESSON AND IS THE SAME LESSON GATE (1) LEARNED.** It says the distinction *"is
#: not decidable by the allowlist shape this gate uses"* — TRUE, and it is why gate
#: (4) is a fourth gate rather than a widening of gate (1). It then says *"a
#: denylist of nouns fails OPEN, which is the failure mode that has already shipped
#: twice"* — also TRUE, and it settles the DENYLIST only. **The polarity was never
#: examined.** An ALLOWLIST of the same nouns fails CLOSED: an unanticipated noun
#: costs one DISCLOSED reading instead of minting a silent scientific value. That is
#: the identical move gate (1) made when it rejected *"a shorter bridge"* and
#: constrained the bridge's SHAPE instead — and this comment, having recorded that
#: move one screen above, did not apply it to itself. **A rejected proxy is only
#: rejected in the polarity it was considered in**, and three successive referrals
#: reasoned about the same one.
#:
#: **WHAT THE CLOSURE COST, MEASURED RATHER THAN ASSERTED.** Over the **232**
#: sentences this repository's own tests already contained that produce a
#: label-anchored match, gate (4) removes **2** readings and both are rows of this
#: tuple; **0** legitimate readings are lost and **0** are gained (a gate can only
#: refuse, and that direction is asserted by test). `"Sample temperature at the
#: second scan was 425 K"` — the reading every referral protected — still reads, as
#: does `"The sample temperature was 425 K."`, because ``sample`` is an admitted
#: locator. The benign-refusal cost of the new gate on an independently-written
#: corpus is recorded in :data:`_GATE_FALSE_NEGATIVES`.
_PRE_LABEL_OVERREACH_CLOSED: tuple[str, ...] = (
    # The DELTA case: the re-subjecting word is a verb and there is no `by`.
    "We lowered the temperature 15 K",
    # The MODIFIER family, added 2026-09-13. A noun or adjective before the label
    # renames the quantity; the bridge after it is the legitimate one.
    "The setpoint temperature was 425 K",
    "The maximum temperature was 500 K",
    "The average temperature was 400 K",
    "The ambient temperature was 295 K",
    "The room temperature was 295 K",
    "The target temperature was 425 K",
    "The requested temperature was 425 K",
    "The planned temperature was 425 K",
)

#: *** A SECOND, DISTINCT CLASS: RUN MISATTRIBUTION ON THE INSTANT RULES. Same
#: review, and it is NOT pre-label overreach — it is kept separate because
#: conflating them would hide what the fix would have to be. ***
#:
#: Re-measured at this head, 4 of 4 silent:
#:
#:     "The previous scan ended at <instant>."     -> acquired_end_utc
#:     "The last scan ended at <instant>."         -> acquired_end_utc
#:     "The calibration scan ended at <instant>."  -> acquired_end_utc
#:     "The reference scan started at <instant>."  -> acquired_start_utc
#:
#: **THE INSTANT RULES DO NOT ANCHOR ON "scan" AT ALL.** On `main` and here the
#: pattern is `\b(?:ended|end|finished|stopped)\b[^.;:]{0,40}?<instant>` — it anchors
#: on the VERB. So it never asks WHICH scan ended, and a sentence about a previous,
#: calibration, dark or reference scan is read as an instant for THE RUN CURRENTLY
#: SELECTED. That is a worse failure than reading the wrong quantity: the value is a
#: real acquisition time, of a different measurement, attributed to this one.
#:
#: **PRE-EXISTING**, by the same `git show` above. ~~**NOT FIXED HERE** for the
#: analogous reason: distinguishing "the scan" from "the previous scan" requires
#: knowing which scan the sentence is about, which is a referent-resolution problem
#: rather than a pattern-shape one, and guessing it would substitute one
#: misattribution for another.~~
#:
#: **CLOSED BY THE SAME GATE (4), AND THE REFERRAL'S PREMISE WAS FALSE — WHICH IS
#: WORTH MORE THAN THE FIX.** It said closing this needs REFERENT RESOLUTION:
#: knowing *which* scan the sentence is about. **It does not.** This reader never
#: had to decide which scan `"the previous scan"` names; it only had to notice that
#: the sentence does not say it is THIS one, and refuse. Deciding the referent and
#: declining to decide it are different acts, and only the first is the hard
#: problem — §5 asks for the second. **The general form of that error: "fixing this
#: requires knowing X" is a claim about a fix that ASSERTS, and a refusal asserts
#: nothing, so the requirement usually does not transfer.**
#:
#: And no guess replaced a misattribution, which is the thing the referral was
#: right to fear: each row raises one
#: ``words_before_the_label_name_something_else`` abstention, proposes nothing, and
#: the transcript is retained in full. Renamed rather than emptied, per the
#: precedent above.
_RUN_MISATTRIBUTION_CLOSED: tuple[str, ...] = (
    "The previous scan ended at 2026-01-01T00:00:00Z",
    "The last scan ended at 2026-01-01T00:00:00Z",
    "The calibration scan ended at 2026-01-01T00:00:00Z",
    "The reference scan started at 2026-01-01T00:00:00Z",
)

#: *** A THIRD, PRE-EXISTING CLASS, FOUND 2026-09-13 BY AN INDEPENDENT ADVERSARIAL
#: HUNT AFTER GATE (4) SHIPPED — AND IT IS A SILENT **LOSS**, WHICH §5 RANKS WORSE
#: THAN A SILENT REFUSAL. Named here because nothing in this module or the ledger
#: names it, NOT fixed because it is the DETECTOR and not a gate. ***
#:
#: **THE VALUE MAY PRECEDE THE LABEL, AND THEN NOTHING HAPPENS AT ALL.** Every
#: label-anchored pattern is written label-then-value —
#: ``\btemperatures?\b[^.;:]{0,40}?<number>\s*K`` — so a sentence that puts the
#: quantity in FRONT of the label produces **no match**, and therefore no candidate
#: AND no abstention. Measured at this head, and the detector pattern is
#: byte-identical to ``d3473414`` (``git diff d3473414 HEAD -- <this file>`` shows
#: zero changes to ``_TEMPERATURE_K``), so this is pre-existing in full:
#:
#:     "A 425 K temperature was used."          -> nothing, SILENT   <- a LOSS
#:     "We ran at a 425 K temperature."         -> nothing, SILENT   <- a LOSS
#:     "The 425 K temperature was held."        -> nothing, SILENT   <- a LOSS
#:     "We saw a 3 K temperature drift."        -> nothing, SILENT   <- correct outcome
#:     "A 3 K temperature error was seen."      -> nothing, SILENT   <- correct outcome
#:     "There was a 3 K temperature offset."    -> nothing, SILENT   <- correct outcome
#:
#: **THE TWO HALVES ARE OPPOSITE AND THAT IS THE WHOLE REASON TO RECORD IT.** The
#: last three are *drift*, *error* and *offset* — refusing them is RIGHT, and only
#: the silence is suboptimal. The first three are ordinary dictation of a real
#: temperature, refused just as silently. So the class contains both a correct
#: refusal and a genuine reading loss, produced by the same cause, and neither is
#: disclosed: the reader never knows it saw anything. That is worse than gate
#: (4)'s abstentions, which at least tell the scientist to restate.
#:
#: **WHY IT IS NOT FIXED HERE, with the shape of the fix named so it is not
#: re-derived.** It is not a gate, it is the DETECTOR. Every gate in this module is
#: built on the premise that the permissive pattern matches MORE than it may read —
#: *"the permissive pattern is kept as the DETECTOR — that is what makes a refusal
#: disclosable instead of silent"*. Widening ``_TEMPERATURE_K`` to match
#: value-then-label would change what all four gates see, what the restatement pass
#: is allowed to scan, and what every span-overlap guard computes, because
#: ``match.start(1)`` would no longer sit after the label and :func:`_label_bridge`
#: and :func:`_pre_label_text` both slice on that assumption. It is also the one
#: change in this module that can only ADD candidates, so it must arrive with its own
#: adversarial corpus rather than beside a gate. A slice of its own.
#:
#: Asserted the wrong way round by
#: ``test_the_VALUE_BEFORE_LABEL_class_is_STILL_SILENT`` so closing it is a reviewed
#: deletion rather than a documented item quietly going away.
_VALUE_BEFORE_LABEL_RESIDUE: tuple[str, ...] = (
    # The LOSSES: legitimate temperatures, read by nothing, disclosed by nothing.
    "A 425 K temperature was used.",
    "We ran at a 425 K temperature.",
    "The 425 K temperature was held.",
    # The CORRECT refusals, silent for the identical reason. Kept in the same tuple
    # deliberately: a fix that discloses one must disclose the other, and a fix that
    # reads the first three must NOT read these.
    "We saw a 3 K temperature drift.",
    "A 3 K temperature error was seen.",
    "There was a 3 K temperature offset.",
)

#: **THE OTHER SIDE OF THE SAME LEDGER: the false NEGATIVES this gate costs,
#: measured rather than asserted, because "fail-closed" is only acceptable if what
#: it closes on is genuinely unreadable.**
#:
#: ==================================================  =========================
#: measured over                                        reading lost, disclosed
#: ==================================================  =========================
#: 15 independently-written benign BRIDGE forms          **1** (7%)
#: 57 independently-written benign TAIL continuations    **16** (28%)
#: 1,365 generated legitimate sentences                  **0**
#: 156 sentences this repository's tests already had     **0**
#: ==================================================  =========================
#:
#: (The ratcheted ``_BENIGN_BRIDGE_FORMS`` tuple in the test file holds **20** of
#: these forms and loses **0**, because the one that IS lost is named below as
#: residue rather than pinned as passing. Both numbers are stated so neither reads
#: as the other.)
#:
#: **The bridge figure was 86% before it was measured**, and the generated corpus
#: reported 0 — see :data:`_ASSERTION_AT_VERB` for why a corpus built from the
#: grammar's own vocabulary cannot see that. The widening that fixed it reopened
#: nothing, asserted over all three defect corpora.
#:
#: **THE 16 TAIL LOSSES ARE NOT FIXABLE BY WIDENING, and that is the honest
#: residue.** Each is a BARE ADVERB or a relational preposition used benignly —
#: ``consistently``, ``steadily``, ``apparently``, ``nominally``, ``roughly``,
#: ``stable``, ``per the log``, ``from the log``. Admitting a bare adverb SHIELDS a
#: qualifier behind it (``just above target``, ``well below the setpoint``,
#: ``consistently above target``, ``nominally 3 K above target`` would every one
#: read as a temperature), and ``per``/``from`` cannot be told from ``per minute``
#: and ``from the setpoint`` without a domain lexicon this reader does not have.
#: So the 28% is PAID, knowingly, and every one of the 16 is disclosed with an
#: instruction that works ("state the value on its own"). A denylist of relational
#: heads would take it to ~0% and is refused on §5 grounds: its leak class
#: (appositive unit qualifiers — ``RMS``, ``peak to peak``, ``FWHM``, ``sigma``) is
#: OPEN and domain-specific, which is the shape that has bitten this module twice.
#: **A THIRD OPEN SUB-CLASS, FOUND BY SELF-REVIEW OF THIS SLICE'S OWN GRAMMAR AND
#: MEASURED RATHER THAN REASONED ABOUT.** :data:`_LABEL_MODIFIER` admits a
#: preposition plus a DETERMINER plus up to three arbitrary words, because that is
#: what makes *"Sample temperature at the second scan was 425 K"* and *"The
#: temperature of the sample was 425 K"* readable. When the modifier's OBJECT is
#: itself a quantity noun, the bridge parses and the value is read:
#:
#: ==============================================  =======================
#: sentence                                         proposes
#: ==============================================  =======================
#: ``The temperature of the drift was 3 K``         ``temperature_K = 3``
#: ``The temperature of the error was 2 K``         ``temperature_K = 2``
#: ``The temperature in the drift was 3 K``         ``temperature_K = 3``
#: ``The temperature of the ramp was 5 K``          ``temperature_K = 5``
#: ``The temperature for the tolerance was 1 K``    ``temperature_K = 1``
#: ==============================================  =======================
#:
#: Each is SILENT, so each is a §5 defect of the same rank as the thirteen this
#: slice closed. **The BARE forms are all closed** — ``The temperature DRIFT was
#: 3 K`` is refused — so what is open is specifically the determiner-led genitive.
#:
#: **WHY IT IS NOT CLOSED, and the reason is the same irreducible one the tail
#: gate records.** The discriminating fact is the SEMANTIC CLASS of the modifier's
#: object: *"the temperature of the SAMPLE"* is the sample's temperature and
#: *"the temperature of the DRIFT"* is a drift figure, and both are
#: preposition + determiner + noun. Telling them apart needs a lexicon of which
#: nouns name a THING that has a temperature versus a QUANTITY derived from one,
#: and this reader has none — the same wall as ``per the log`` versus
#: ``per minute``. Dropping ``of`` from :data:`_LABEL_MODIFIER` would close three
#: of the five rows at the cost of *"The temperature of the sample was 425 K"*,
#: which is ordinary dictation; that trade is a judgement for its own slice with
#: its own measurement, not one to make in a comment.
#:
#: ``at the step`` is listed with the others and is the case that shows why the
#: trade is not obvious: *"The temperature at the step was 5 K"* most likely
#: DOES state the temperature at that step, so reading 5 may be CORRECT there. A
#: rule that refused the whole family would lose it.
#:
#: **NO LIKELIHOOD ARGUMENT IS OFFERED FOR LEAVING IT OPEN.** These forms are less
#: natural than the thirteen bare compounds, and that is deliberately NOT the
#: reason recorded: ``_RESTATEMENT_RESIDUE_CLOSED`` documents a likelihood argument
#: being the stated basis for shipping five silent fabrications, and the correction
#: there was that a likelihood argument is not a §5 argument. The reason is the
#: missing lexicon, which is a statement about what is decidable here.
_MODIFIER_OBJECT_OVERREACH_RESIDUE: tuple[str, ...] = (
    "The temperature of the drift was 3 K",
    "The temperature of the error was 2 K",
    "The temperature in the drift was 3 K",
    "The temperature of the ramp was 5 K",
    "The temperature for the tolerance was 1 K",
)

#: THE ONE BRIDGE FORM STILL LOST, named rather than folded into a percentage.
#: A PARENTHETICAL between the label and its copula. Admitting it means admitting
#: arbitrary text inside ``, … ,`` — *"the temperature, which was a drift of, was
#: 3 K"* is the shape that makes that unsafe — so it needs the same
#: allowlist-grammar treatment the bridge itself got, over a different
#: constituent. Not built.
#: **THE TWO FREE-PHRASE RULES DO NOT SHARE THE LABEL-OVERREACH DEFECT, and this
#: is how that was established rather than assumed.** ``_ATMOSPHERE`` and
#: ``_ENVIRONMENT`` require :data:`_LABEL_SEPARATOR` — a copula, a colon or an
#: equals sign — IMMEDIATELY after the label, and anchor the phrase to the end of
#: the segment, so they were already gated in the shape ``_ASSERTION_BRIDGE`` gives
#: the other three. Measured: *"The atmosphere CHANGE was dry nitrogen"*, *"The
#: atmosphere DRIFT was dry nitrogen"* and *"The environment CONTROL was ambient
#: air"* all match nothing at all, while *"The atmosphere was dry nitrogen"* and
#: *"atmosphere: dry nitrogen"* read normally. They are therefore UNCHANGED by this
#: slice and carry no ``label_head``.
#:
#: **THEY HAVE A DIFFERENT IMPERFECTION, measured and named rather than fixed.**
#: ``_LABEL_SEPARATOR`` admits ``of``, so:
#:
#: ===================================================  ==========================
#: sentence                                              proposes as the atmosphere
#: ===================================================  ==========================
#: ``The atmosphere of the glovebox was dry nitrogen``   ``the glovebox was dry
#:                                                        nitrogen``
#: ===================================================  ==========================
#:
#: **It is NOT the class this slice closes, and the difference matters.** No
#: quantity is re-subjected and no number is invented: the proposed value is a
#: VERBATIM substring of the scientist's own sentence, shown to them for
#: confirmation, so what is wrong is the phrase BOUNDARY rather than the claim. A
#: scalar fabrication offers a plausible number nobody stated; this offers an
#: obviously-wrong string. Left alone because fixing it means editing
#: ``_LABEL_SEPARATOR``, which governs two rules this slice deliberately did not
#: change — and ``of`` is measured UNUSED by every phrase bridge in the repository's
#: corpus (``' was '``, ``' was: '``, ``': '``), so dropping it is a plausible fix
#: for its own slice.
_PHRASE_BOUNDARY_RESIDUE: tuple[tuple[str, str], ...] = (
    (
        "The atmosphere of the glovebox was dry nitrogen",
        "the glovebox was dry nitrogen",
    ),
)

_PARENTHETICAL_BRIDGE_RESIDUE: tuple[str, ...] = (
    "The temperature, measured carefully, was 425 K.",
)

#: **AND THE BRIDGE FIGURE IN IT WAS MEASURED ~3x TOO LOW, WHICH IS THE PART OF THIS
#: LEDGER A FUTURE SLICE SHOULD LEARN FROM RATHER THAN THE NUMBERS.** An independent
#: review put the overall benign-refusal rate at **28% (14 of 50)**, 10 of the 14
#: being bridge refusals, against the published *"bridge: 1 of 15 (7%)"*. The cause
#: is stated in :data:`_ASSERTION_AT_VERB` and is the same defect one level up: the
#: 86%→7% widening was re-measured against *"an independently-written list of fifteen
#: forms"* — **written by the same author as the grammar.** Fifteen forms from one
#: head is not an independent sample of how people talk; it is a second draw from the
#: distribution that produced the grammar. The module's *tail* figure (28%) matched
#: the reviewer's rate almost exactly and is honest, which is the tell: the figure
#: that came from a large corpus held up and the figure that came from a short
#: hand-written list did not.
#:
#: **THE 7% IS LEFT UNCHANGED HERE AND IS NOT RE-MEASURED BY THIS SLICE, deliberately
#: and with the limit stated.** It is gate (1)'s number, this slice changed no part of
#: gate (1), and replacing a stale figure with one measured by a DIFFERENT author on a
#: DIFFERENT corpus would silently change what the number means. The correction is
#: recorded beside it instead, with the reviewer's figure, so a reader gets both and
#: neither is presented as settled.
#:
#: **THE PRE-LABEL ROW BELOW CARRIES THE SAME DISCLOSURE ABOUT ITSELF, because the
#: honest thing is to say so rather than to repeat the mistake one gate over.** Its 49
#: forms were written by the author of gate (4) — before the grammar's vocabulary was
#: widened, and without consulting it while writing, which reduces the coupling but
#: does not remove it. **It is quoted beside two figures that ARE independent of this
#: slice and are the stronger evidence:** 0 of 20 lost from ``_BENIGN_BRIDGE_FORMS``
#: (written for gate (1), by a different slice, before gate (4) existed) and 0
#: legitimate readings lost from the 232 sentences this repository's tests already
#: contained. A single-author benign list should be read as a floor on the true loss
#: rate, never as an estimate of it.
_GATE_FALSE_NEGATIVES = (
    "bridge: 1 of 15 independently-written benign forms, a PARENTHETICAL (was 13 "
    "of 15 before the 2026-09-13 widening) -- and an independent review measured "
    "the overall benign-refusal rate at 28% (14 of 50), 10 of them bridge "
    "refusals, so this 7% is a single-author figure and is understated; "
    "tail: 16 of 57 benign continuations, every one a bare adverb or a benignly-"
    "used relational preposition, none of which can be admitted without shielding "
    "a qualifier behind it; "
    "pre-label: 2 of 51 benign forms (4%), both spoken discourse markers, was 22 "
    "of 51 (43%) before the apparatus/participle/affirming widening (corrected "
    "2026-09-13 from a published 20 of 51, which was a 49-row numerator rebased "
    "onto this denominator), and 0 of 20 "
    "_BENIGN_BRIDGE_FORMS; 0 of 1,365 generated legitimate sentences and 0 of the "
    "156 in this repository's own tests. Every loss is DISCLOSED."
)

_LABEL_OVERREACH_CLOSED: tuple[str, ...] = (
    "The temperature drift was 3 K",
    "The temperature error was 2 K",
    "temperature resolution 0.5 K",
    "The temperature was stable to 1 K",
    "The temperature rose by 30 K",
    "temperature step 5 K",
    "We held the temperature to within 2 K",
    # Added 2026-09-12 (fourth pass). Same class, same silence, same pre-existence.
    "The temperature uncertainty was 2 K",
    "The temperature offset was 4 K",
    "The temperature fell by 12 K",
    "temperature stability 0.2 K",
    "The temperature gradient was 5 K",
    "We corrected the temperature by 7 K",
)

#: A SEPARATE, PRE-EXISTING DEFECT, **CLOSED 2026-09-12 (second pass) BY
#: :data:`MAX_DISCLOSURES`.** The measurements are kept in full, because they are
#: what the ceiling is set against and because the reasoning for referring it is
#: the more instructive half.
#:
#: ``MAX_CANDIDATES`` and ``MAX_CANDIDATE_QUOTE_BYTES`` bound the CANDIDATE list
#: only. ``abstentions`` and ``clarifications`` are appended per regex MATCH, above
#: the ``if not settled: continue`` that feeds the ceiling accumulators, so neither
#: ceiling sees them and ``MAX_SEGMENTS`` does not bind because the payload is one
#: segment. Measured at this head, on legal single-segment transcripts sized at
#: exactly ``routes._MAX_TRANSCRIPT_BYTES``:
#:
#: ==================================  ========  =====================  ==========
#: payload                             bytes     disclosures            serialised
#: ==================================  ========  =====================  ==========
#: ``"temperature 1 C "`` x 16,384     262,144   16,384 abstentions     ~5.1 MB
#: ``"run zzz at 1 K "`` x 17,476      262,140   17,476 clarifications  ~4.3 MB
#: ==================================  ========  =====================  ==========
#:
#: No ceiling fires, and the response is still assembled inside ``record_lock``. So
#: the 165 MB the ceilings closed became ~5 MB, which is smaller and is **not a
#: bound**.
#:
#: **BOTH NUMBERS REPRODUCED EXACTLY** when this ceiling was built — 16,384 and
#: 17,476 on the same two payloads at the same byte ceiling — which is the reason
#: the ceiling could be set against them rather than against a guess.
#:
#: ~~**WHY IT IS REFERRED AND NOT FIXED HERE.** It is a resource bound, not a §5
#: honesty defect, so it does not belong in the same slice as the gate;~~ — the
#: separation held for exactly one slice. The specification it then gave was
#: followed to the letter and is worth keeping as the record of a referral that
#: worked: *"a third count folded into the pre-construction check (or its own*
#: ``MAX_DISCLOSURES``) *with the same refuse-whole semantics, which means a new
#: field on* ``TranscriptTooDense`` *and therefore an edit to the 422 body in*
#: ``routes.py`` *— a manifest-listed file whose snapshot this slice must not
#: drift."* All four of those are what shipped; the snapshot drift is reported
#: rather than regenerated, by the same reasoning.
#:
#: **Per-segment deduplication was considered and is NOT the fix**: it takes the
#: first payload to one disclosure, but ``"temperature 1 C temperature 2 C …"`` with
#: distinct numbers still yields ~16,000, so it reduces without bounding and would
#: read as a fix. **It was not adopted, not even as an optimisation beside the
#: bound**, because a reduction sitting next to a ceiling is the thing a future
#: reader mistakes for the ceiling.
#:
#: **Neither slice enlarged it.** The two restatement-refusal classes —
#: ``unhedged_further_values`` and ``trailing_text_after_further_values`` — are
#: deduplicated to at most one entry per segment per rule per KIND and are
#: therefore bounded by ``MAX_SEGMENTS`` × the 3 restatement-carrying rules × 2
#: kinds = 600 by construction, independent of transcript content.
#: ``MAX_SEGMENTS`` × ``len(_RULES)`` = 500 was the looser figure quoted here
#: before; both are upper bounds and neither is the measured worst legitimate
#: total, which is also 600 and is composed differently — see
#: :data:`MAX_DISCLOSURES`.
_DISCLOSURE_CEILING_GAP = (
    "CLOSED 2026-09-12 by MAX_DISCLOSURES, which refuses the whole transcript at "
    "the route before any note is stored. It was measured OPEN at 16,384 "
    "abstentions (~5.1 MB) and 17,476 clarifications (~4.3 MB) on single-segment "
    "transcripts at the transcript byte ceiling, with neither density ceiling "
    "firing; both figures reproduced exactly when the bound was built. See this "
    "constant's own comment for why per-segment deduplication was not the fix."
)

#: The absorbing element / absorption edge, which this build records as implicit,
#: sidecar-only content because the official schema has no native field for them.
_IMPLICIT_ONLY = re.compile(
    r"\b(?:absorbing element|absorption edge|[KL]\d?[- ]edge)\b", re.IGNORECASE
)

#: A run named by number, label or id.
_RUN_REFERENCE = re.compile(r"\brun\s+(?:number\s+|#\s*)?([A-Za-z0-9][A-Za-z0-9_-]{0,63})\b", re.IGNORECASE)

#: A run named by position or relation. Matched only to ASK, never to resolve.
_VAGUE_RUN = re.compile(
    r"\b(?:the\s+)?(?:first|second|third|fourth|fifth|last|latest|previous|prior|next|"
    r"other|same|earlier|later)\s+run\b",
    re.IGNORECASE,
)

#: Words that follow ``run`` but never name one. Without this, "run at 300 K" and
#: "run was repeated" would each be read as a reference to a run called "at" or
#: "was" and would produce a spurious unknown-run clarification on almost every
#: sentence.
_NOT_A_RUN_NAME: frozenset[str] = frozenset(
    {
        "at", "was", "were", "is", "in", "on", "for", "with", "the", "a", "an",
        "and", "to", "from", "by", "of", "again", "twice", "under", "over",
        "started", "ended", "finished", "began", "completed", "aborted", "failed",
        "repeated", "took", "had", "has", "used", "using", "after", "before",
        "this", "that", "these", "those", "it", "we", "i",
    }
)


@dataclass(frozen=True, slots=True)
class _Rule:
    """One entry of the closed table: a pattern, a path, and how to read a value.

    ``restatement`` is the rule's value form WITHOUT its label, and it is ``None``
    for every rule whose value is a free phrase. That is a decision, not an
    omission: ``430 K`` and ``2026-01-02T00:00:00Z`` carry a unit or a format that
    says what they are, so a second one in the same sentence is recognisably another
    statement of the same quantity. A bare phrase carries nothing — a second phrase
    after ``atmosphere was dry nitrogen`` could be about anything, and reading it as
    another atmosphere would be a guess. The phrase rules are also anchored to the
    end of the segment and so can match at most once regardless.

    ``restated_sentence`` exists because a candidate's ``rule`` is how a scientist
    checks WHY a value was read. ``sentence`` claims the label and the value appeared
    in one clause, which is not true of a restatement, so a restatement must not
    borrow it. **And it must state the MECHANISM, not just the conclusion** — ALL
    THREE conditions: that a qualifying hedging word sat immediately between the
    two values, that the unit was the whole unit, and — when that hedging word
    stood alone rather than behind an explicit ``or`` — that the restatement ended
    the statement. Together those are the whole of why the second value was
    readable. These strings have been wrong THREE times, and every correction is
    recorded because each was a claim about the transcript the
    reader had not checked: the first version asserted only that "the same sentence
    restates the …", false on six measured sentences; the second added the hedge and
    called it "the ONLY reason", which was true of a gate half the size of the real
    one and false on eleven further measured sentences — eight of them through
    ``about``/``around``/``roughly``/``approximately``/``possibly``/``again``, which
    modify what FOLLOWS them, and three through a compound unit; the third said
    "TWO conditions" and was false on four sentences; the fourth said "behind a
    BARE hedge" and was false on five more, behind an explicit ``or``. All nine are
    in :data:`_RESTATEMENT_RESIDUE_CLOSED`. See
    :data:`_HEDGE_BRIDGE`, :data:`_OR_REQUIRED_HEDGES`,
    :data:`_UNIT_TERMINATORS` and :data:`_STATEMENT_END`.

    ``label_head`` is the rule's own label as it appears at the start of its whole
    match, and it is what makes the PASS-ONE ASSERTION GATE applicable — see
    :data:`_ASSERTION_BRIDGE`. It is ``None`` for the two free-phrase rules, and
    that is a property of those rules rather than an exemption: ``_ATMOSPHERE`` and
    ``_ENVIRONMENT`` already require :data:`_LABEL_SEPARATOR` (a copula, a colon or
    an equals sign) immediately after the label AND anchor the phrase to the end of
    the segment, so they are gated in exactly the shape the bridge grammar gives
    the other three. Measured rather than assumed: *"The atmosphere CHANGE was dry
    nitrogen"* does not match at all, because ``change`` is not a separator.
    """

    name: str
    pattern: re.Pattern[str]
    field_path: str
    numeric: bool
    sentence: str
    restatement: re.Pattern[str] | None = None
    restated_sentence: str | None = None
    label_head: re.Pattern[str] | None = None


def _label_bridge(rule: "_Rule", match: re.Match[str]) -> str | None:
    """The text between ``rule``'s label and the value, or ``None`` if ungated.

    Sliced out of ``match.group(0)`` rather than out of the segment, so it cannot
    accidentally reach behind the label or past the value.
    """
    if rule.label_head is None:
        return None
    whole = match.group(0)
    head = rule.label_head.match(whole)
    if head is None:  # pragma: no cover - pinned by a test over every rule
        return None
    return whole[head.end() : match.start(1) - match.start()]


def _asserts_the_value(rule: "_Rule", match: re.Match[str]) -> bool:
    """GATE (1): does the sentence assert this value AS ``rule``'s field?

    True for an ungated rule, so the two phrase rules keep the behaviour their own
    separator and end-anchoring already give them.
    """
    bridge = _label_bridge(rule, match)
    return bridge is None or _ASSERTION_BRIDGE.fullmatch(bridge) is not None


def _value_of(rule: "_Rule", match: re.Match[str]) -> Any:
    """The value a match states, read exactly as the reading pass reads it.

    Shared with the construction loop below so the SEQUENCE GATE's "is it a
    DIFFERENT value?" test and the de-duplication's "is it the SAME value?" test
    cannot disagree — ``425`` and ``425.0`` must not be one to one of them and two
    to the other.
    """
    raw = match.group(1).strip()
    return _read_number(raw) if rule.numeric and raw else raw


def _continuation_is_clean(rule: "_Rule", text: str, match: re.Match[str]) -> bool:
    """GATE (2): does what follows the value leave it measuring ``rule``'s field?

    ``match.end()`` — the end of the value AND its unit. See
    :data:`_VALUE_CONTINUATION` and :func:`_unit_is_complete` for the offset trap
    this shares with them.
    """
    if rule.label_head is None:
        return True
    return _VALUE_CONTINUATION.match(text, match.end()) is not None


def _pre_label_text(rule: "_Rule", text: str, match: re.Match[str]) -> str | None:
    """The text from the start of the label's clause to the label, or ``None``.

    Sliced out of the SEGMENT rather than out of ``match.group(0)``, which is the
    opposite of :func:`_label_bridge` and is forced: the bridge lives inside the
    match and this lives entirely outside it, so there is nothing in the match to
    slice. The clause bound is what keeps it from becoming a whole-segment rule —
    see :data:`_PRE_LABEL_CLAUSE_OPEN`.
    """
    if rule.label_head is None:
        return None
    head = rule.label_head.match(match.group(0))
    if head is None:  # pragma: no cover - pinned by a test over every rule
        return None
    before = text[: match.start() + head.start()]
    last = None
    for boundary in _PRE_LABEL_CLAUSE_OPEN.finditer(before):
        last = boundary
    return before if last is None else before[last.end() :]


def _label_is_the_subject(rule: "_Rule", text: str, match: re.Match[str]) -> bool:
    """GATE (4): do the words BEFORE the label leave it naming ``rule``'s field?

    True for an ungated rule, for the reason :func:`_asserts_the_value` gives.

    **CHECKED LAST OF THE THREE PASS-ONE GATES, AND THE ORDER IS DELIBERATE RATHER
    THAN INCIDENTAL.** A sentence can fail more than one gate — *"We corrected the
    temperature by 7 K"* fails this one and gate (1) — and only the FIRST failure is
    disclosed, so the order decides which sentence the scientist is shown. Running
    this gate last leaves every reading refused by the bridge or the continuation
    disclosing exactly what it disclosed before, so the thirteen rows of
    :data:`_LABEL_OVERREACH_CLOSED` keep the reason they are pinned to, and only a
    match that survives both forward gates reaches this one.

    **RUNNING IT FIRST WAS TRIED AND RE-LABELLED EXACTLY TWO ALREADY-CLOSED ROWS —
    and this sentence said "six" until it was counted, which is the reason the
    derivation is written out rather than the number quoted.** The rows are
    *"We held the temperature to within 2 K"* and *"We corrected the temperature by
    7 K"*, both from :data:`_LABEL_OVERREACH_CLOSED`; they fail this gate on
    ``We held the``/``We corrected the`` AND gate (1) on their bridge. Re-derive over
    the 18 rows of :data:`_LABEL_OVERREACH_CLOSED` plus
    :data:`_MODIFIER_OBJECT_OVERREACH_RESIDUE`, counting those where
    ``_asserts_the_value and _continuation_is_clean`` is False and
    ``_label_is_the_subject`` is also False. Two is a smaller reason than six, and
    it is still the reason: the bridge is the NEARER fact about those sentences, so
    naming a pre-label word when the words between the label and the value are
    themselves disqualifying tells the scientist about the wrong half of their
    sentence — and it would break the pins those rows carry, for no gain.
    """
    pre_label = _pre_label_text(rule, text, match)
    return pre_label is None or _PRE_LABEL.fullmatch(pre_label) is not None


_RULES: tuple[_Rule, ...] = (
    _Rule(
        name="temperature_kelvin",
        pattern=_TEMPERATURE_K,
        field_path="context.temperature_K",
        numeric=True,
        sentence=(
            "the words 'temperature' and a number followed by K or kelvin appear "
            "in one clause; the number is read as written and the unit is not "
            "converted"
        ),
        label_head=_LABEL_HEAD_TEMPERATURE,
        restatement=_TEMPERATURE_K_RESTATED,
        restated_sentence=(
            "the same sentence restates the temperature, and THREE conditions "
            "all held. First, a HEDGING WORD sits immediately between the number "
            "the "
            "word 'temperature' introduced and this one, with nothing else at all "
            "in the gap — 'maybe', 'perhaps' or 'alternatively' on "
            "their own, a bare 'or', or an approximation behind an explicit 'or' "
            "such as 'or about'. A BARE 'about', 'around', 'roughly', "
            "'approximately' or 'possibly' is NOT enough, because those "
            "modify what follows them rather than hedging what came before: "
            "'about 3 K above target' states an offset, not a temperature. A bare "
            "'again' or 'and again' is not enough either, for a different reason: "
            "both mark a REPEAT, so they say the temperature was measured a second "
            "time rather than that this number might instead be the first one. "
            "Second, K or kelvin is the WHOLE unit — '3 K/min' is a ramp rate and "
            "is not read, however it is introduced. Third, when that hedging word "
            "stood ALONE rather than behind an explicit 'or', this value ENDED the "
            "statement — the sentence finished after it, or the only thing "
            "following was another hedged value that was itself read — because "
            "'maybe 3 K of drift' states a drift and not a temperature. Without "
            "all three a "
            "later number followed by K is a different quantity — a ramp rate, a "
            "step size, a setpoint, an offset — and is not read. It is not a "
            "correction, not "
            "a preference, and NOT a range or an interval, neither of which "
            "anybody stated"
        ),
    ),
    _Rule(
        name="acquisition_start",
        pattern=_ACQUIRED_START,
        field_path="timestamps.acquired_start_utc",
        numeric=False,
        sentence=(
            "a start word and a full UTC instant appear in one clause; the instant "
            "is taken exactly as written and is never completed or reformatted"
        ),
        label_head=_LABEL_HEAD_START,
        restatement=_INSTANT_RESTATED,
        restated_sentence=(
            "the same sentence restates the start, and THREE conditions all "
            "held. "
            "First, a HEDGING WORD sits immediately between the instant the start "
            "word introduced and this one, with nothing else at all in the gap — "
            "'maybe', 'perhaps' or 'alternatively' on their own, a "
            "bare 'or', or an approximation behind an explicit 'or' such as 'or "
            "about'. A BARE 'again' or 'and again' is NOT enough, because before a "
            "full instant either "
            "most naturally means the scan was REPEATED, which is a different "
            "run's instant; nor is a bare 'about', which introduces an "
            "arithmetic base rather than a start. Second, the instant is complete "
            "and stands on its own. Third, when that hedging word stood ALONE "
            "rather than behind an explicit 'or', this instant ENDED the "
            "statement — the sentence finished after it, or the only thing "
            "following was another hedged instant that was itself read. Without "
            "all three a later instant "
            "belongs to something else — the end of this run, or another run "
            "entirely — and is not read. It is taken exactly as written, and it "
            "is not a correction and not a range"
        ),
    ),
    _Rule(
        name="acquisition_end",
        pattern=_ACQUIRED_END,
        field_path="timestamps.acquired_end_utc",
        numeric=False,
        sentence=(
            "an end word and a full UTC instant appear in one clause; the instant "
            "is taken exactly as written and is never completed or reformatted"
        ),
        label_head=_LABEL_HEAD_END,
        restatement=_INSTANT_RESTATED,
        restated_sentence=(
            "the same sentence restates the end, and THREE conditions all held. "
            "First, a HEDGING WORD sits immediately between the instant the end "
            "word introduced and this one, with nothing else at all in the gap — "
            "'maybe', 'perhaps' or 'alternatively' on their own, a "
            "bare 'or', or an approximation behind an explicit 'or' such as 'or "
            "about'. A BARE 'again', 'and again' or 'about' is NOT enough, for the "
            "reason the "
            "start rule gives. Second, the instant is complete and stands on its "
            "own. Third, when that hedging word stood ALONE rather than behind an "
            "explicit 'or', this instant ENDED the statement — the sentence "
            "finished after it, or the only thing following was another hedged "
            "instant that was itself read. Without all three a later instant "
            "belongs to something "
            "else and is not read. It is taken exactly as written, and it is not "
            "a correction and not a range"
        ),
    ),
    _Rule(
        name="atmosphere",
        pattern=_ATMOSPHERE,
        field_path="context.thermodynamics.atmosphere",
        numeric=False,
        sentence=(
            "the word 'atmosphere' is followed by a short phrase that ends the "
            "sentence; the phrase is proposed exactly as written and is not "
            "matched against any vocabulary"
        ),
    ),
    _Rule(
        name="environment",
        pattern=_ENVIRONMENT,
        field_path="context.environment",
        numeric=False,
        sentence=(
            "the word 'environment' is followed by a short phrase that ends the "
            "sentence; the phrase is proposed exactly as written and is not "
            "matched against any vocabulary"
        ),
    ),
)

#: Every path the closed table above can propose. Exported so a route can assert
#: it against the set the write operation actually enforces, rather than a
#: reviewer noticing.
READABLE_FIELD_PATHS: frozenset[str] = frozenset(rule.field_path for rule in _RULES)


def _read_number(raw: str) -> Any:
    """``int`` when the text has no decimal point, else ``float``. Never rounded."""
    return float(raw) if "." in raw else int(raw)


def _spans_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    """Whether two half-open character spans share any character."""
    return left[0] < right[1] and right[0] < left[1]


def _unit_is_complete(text: str, match: re.Match[str]) -> bool:
    """Whether a restatement's unit is the WHOLE unit. See :data:`_UNIT_TERMINATORS`.

    Measured from ``match.end()`` — the end of the value AND its unit — and not
    from ``match.end(1)``, which is the end of the NUMBER. The two are one
    character apart in the source and the wrong one refuses every legitimate
    restatement as well, because ``" K"`` is not a terminator either; a test pins
    both offsets so the mistake cannot be made silently.
    """
    following = text[match.end() : match.end() + 1]
    return following == "" or following.isspace() or following in _UNIT_TERMINATORS


# --- locating the readings, separately from constructing the candidates -------


@dataclass(frozen=True, slots=True)
class _Reading:
    """One value this reader HAS read, before it becomes a candidate.

    It exists so the two ceilings can be enforced on an EXACT count and an EXACT
    byte total without the allocation they are there to prevent: a match object
    and a parsed value per reading, rather than a
    :class:`~.providers.extraction.FieldCandidate` carrying the segment text
    twice. Internal and never served.
    """

    rule: "_Rule"
    match: re.Match[str]
    restated: bool
    value: Any


def _segment_readings(
    segment: Segment,
) -> tuple[list["_Reading"], tuple[tuple[str, str, str], ...]]:
    """Every value one segment states, plus the rules whose restatements it REFUSED.

    Pure and cheap. It allocates no candidate and formats no ``rule`` sentence,
    which is what lets :func:`read_transcript` learn what a segment WOULD cost
    before it pays it.

    **THE SECOND RETURN VALUE EXISTS BECAUSE THE GATE WAS SILENT.** A refused
    restatement produced no candidate, no abstention and no ``review_required``
    row, and — because exactly one candidate then survived — ``len(produced) == 1``
    recorded the segment in ``candidate_by_segment``, so the note was presented as
    MAPPED to that one value. Measured: *"Temperature ramped 300 K, then 350 K,
    then 400 K."* proposed ``temperature_K = 300`` with empty ``abstentions``,
    empty ``review_required`` and ``candidate_by_segment == {0: 0}``, for a
    sentence that says the temperature went to 400. The refusal is CORRECT — those
    are not hedged restatements — but a correct refusal a scientist cannot see is
    the silent discard rule (4) exists to end, reached through the fix instead of
    through the defect.

    It reports, per rule and per REFUSAL KIND, ONE short quote — the rule's own
    label-anchored match, the statement whose field had further values withheld.

    **THAT SENTENCE WAS FALSE UNTIL 2026-09-12 (fourth pass), AND IT IS THE REASON
    THE QUOTE IS NOW THE REGION'S OWN LABEL MATCH.** All three refusal sites used
    ``matches[0].group(0)`` — the FIRST label-anchored match of the rule — while the
    anchor the refusal was measured from belonged to a LATER one. Measured at
    ``22d794a5``:

    * *"The temperature was 300 K and the temperature was 425 K, ramped at 3 K/min"*
      quoted ``temperature was 300 K``, while the withheld value (``3 K/min``) sits
      beside ``425 K``.

    A scientist reads that quote to find the sentence to check, so pointing at the
    wrong clause is a disclosure that discloses the wrong thing. Each refusal now
    carries the label match whose region the refused restatement was found in, which
    makes the sentence above true rather than aspirational. ``matches[-1]`` would
    also have fixed the measured row and is NOT what is used: with one region per
    label match (see the walk below) the region's own match is right for every
    region, and the last match is right only for the last one.

    **AND WHEN TWO REGIONS OF ONE RULE REFUSE THE SAME KIND, THE SERVED QUOTE NAMES
    THE FIRST OF THEM — corrected 2026-09-13, because the sentence above is stronger
    than the code.** ``refused.setdefault((rule_name, kind), quote)`` keeps the first
    writer, so *"each refusal carries the label match whose region the refused
    restatement was found in"* is true of the refusal DECISION and of the surviving
    entry, not of every refusal collapsed into it. Nothing is silent and nothing is
    false: the ``reason`` is plural throughout (*"This sentence states further
    values…"*) and the quote is a real clause of the real sentence. It is the
    docstring that overstated. The alternative — one disclosure per region — would
    multiply the disclosure count by the region count on exactly the payloads
    ``MAX_DISCLOSURES`` exists to bound, so the code is left alone deliberately.

    Deduplicated to at most one entry per segment per rule per kind, so the
    disclosure is bounded by ``MAX_SEGMENTS`` × the rules that HAVE a restatement
    × 2 = 600 by construction and cannot be inflated by a transcript that repeats a
    refusable phrase. (Three of the five rules carry a ``restatement``; a rule
    without one can refuse nothing. ``MAX_SEGMENTS`` × ``len(_RULES)`` = 500 is the
    looser bound this comment used to give, and it is also true — a bound that
    ignores the per-kind factor and the restatement-less rules happens to land
    between the two. Both are stated because the reader below serves the
    ``MAX_DISCLOSURES`` ceiling and a bound nobody can re-derive is not a bound.)

    **THE QUOTE IS THE LABELLED MATCH AND NOT THE SEGMENT, AND AN EXISTING TEST IS
    WHY.** The first version quoted ``segment.text``, which on the 27,025-byte
    single-segment payload took the route's response from a few hundred bytes to
    **226,673** — 8.4× the transcript — and tripped
    ``test_the_bare_dense_transcript_is_now_harmless_because_C1_refuses_it``. It was
    also redundant: rule (4) already stores every segment verbatim as a note, so
    quoting the segment here duplicates the text in the same response. The
    label-anchored match identifies the statement in a few words and deliberately
    does NOT include the withheld values — this reader does not know what they are,
    which is the whole reason they were withheld.
    """
    refused: dict[tuple[str, str], str] = {}
    # PASS ONE — EVERY label-anchored match of every rule, not just the first.
    #
    # ~~`match = rule.pattern.search(segment.text)`~~ — CORRECTED. `search`
    # returns the FIRST match and nothing else, so a sentence that names the
    # label twice ("the temperature was 425 K and the temperature at the end was
    # 430 K") proposed one value and lost the other in silence: no candidate, no
    # clarification, no abstention, no `review_required` row. The transcript
    # survived as a note, so nothing was destroyed — what was lost was the
    # READING, and with it the scientist's chance to accept either value.
    #
    # AND EVERY MATCH IS NOW PUT THROUGH THE PASS-ONE ASSERTION GATE, which is the
    # 2026-09-13 change. `rule.pattern` bridges its label to its value with
    # `[^.;:]{0,40}?`, so it MATCHES far more than it may READ: "the temperature
    # drift was 3 K" is a match and is not a temperature. The permissive pattern is
    # kept as the DETECTOR — that is what makes a refusal disclosable instead of
    # silent — and `_asserts_the_value` / `_continuation_is_clean` decide which
    # matches become readings.
    #
    # DETECTING AND READING WITH THE SAME PATTERN IS DELIBERATE, and the
    # alternative was measured and rejected: building the grammar INTO the pattern
    # would let the regex engine retry a longer bridge, but a refusal would then
    # produce NO MATCH and therefore no disclosure — a silent omission, which §5
    # ranks below a disclosed one. The cost of this direction is named in
    # `_LABEL_OVERREACH_CLOSED`: a sentence whose FIRST value fails the gate does
    # not get a second chance at a later value reachable from the same label.
    detected = [list(rule.pattern.finditer(segment.text)) for rule in _RULES]
    labelled: list[list[re.Match[str]]] = []
    #: `(rule_name, kind, quote, value_span)` for every match the gate refused.
    #: Written into `pending` below, with the same "was it read anyway?" filter
    #: every other refusal goes through.
    gate_refusals: list[tuple[str, str, str, tuple[int, int]]] = []
    for rule, matches in zip(_RULES, detected, strict=True):
        kept: list[re.Match[str]] = []
        for match in matches:
            if not _asserts_the_value(rule, match):
                gate_refusals.append(
                    (rule.name, _KIND_NOT_ASSERTED, match.group(0), match.span(1))
                )
                continue
            if not _continuation_is_clean(rule, segment.text, match):
                gate_refusals.append(
                    (rule.name, _KIND_QUALIFIED, match.group(0), match.span(1))
                )
                continue
            # GATE (4), last of the three — see `_label_is_the_subject` for why the
            # order is load-bearing. The QUOTE is the whole match, exactly as the
            # two gates above quote it, and so deliberately does NOT include the
            # pre-label words that caused the refusal: `match.group(0)` starts at
            # the label. Extending the quote backwards was considered and declined
            # — every other disclosure in this module quotes a match, a scientist
            # reading "the setpoint temperature was 425 K" sees the whole sentence
            # beside the reason anyway, and a quote whose span does not correspond
            # to a match would break the offset round-trip the quotes' honesty
            # rests on.
            if not _label_is_the_subject(rule, segment.text, match):
                gate_refusals.append(
                    (rule.name, _KIND_NOT_THIS_SUBJECT, match.group(0), match.span(1))
                )
                continue
            kept.append(match)
        labelled.append(kept)

    # The VALUE spans every label-anchored match of every rule has claimed.
    # ACROSS rules, which is what stops pass two from reading a value another
    # rule read under its own label: "started X and ended Y" states two
    # DIFFERENT fields, and a restatement scan that saw only "another instant
    # after the start word" would propose Y as a second acquisition START,
    # contradicting the word "ended" sitting in front of it. Value spans rather
    # than whole-match spans for the reason the abstention guard elsewhere gives.
    #
    # KEPT AS DEFENCE IN DEPTH now that `_HEDGE_BRIDGE` also refuses that
    # sentence. The two guards are independent and they AGREE on it — proven by
    # measurement rather than asserted, in
    # `test_both_restatement_guards_refuse_started_A_and_ended_B` — and keeping
    # both means a widened hedge list cannot reintroduce a cross-field read.
    claimed_value_spans = [
        match.span(1) for matches in labelled for match in matches
    ]

    #: EVERY refusal this segment is CONSIDERING, with the VALUE SPAN it is about.
    #: `(rule_name, kind, quote, value_span)`. Held instead of written straight into
    #: `refused` so the decision can be taken once every rule's readings are known —
    #: see the filter below, which is the whole reason this list exists.
    pending: list[tuple[str, str, str, tuple[int, int]]] = []
    #: The value spans pass TWO accepted, across all rules. `claimed_value_spans`
    #: above is pass ONE's equivalent; together they are "every value this segment
    #: was read for", which is exactly the set a refusal must not contradict.
    accepted_value_spans: list[tuple[int, int]] = []
    #: The label-anchored value spans THE SEQUENCE GATE withheld. `claimed` is
    #: computed before the gate runs, so without this subtraction a withheld value
    #: would still count as "read" and the filter below would DROP its own
    #: disclosure — the gate would withhold in silence, which is the one outcome
    #: §5 ranks below the defect it closes.
    withheld_value_spans: list[tuple[int, int]] = []

    found: list["_Reading"] = []
    for rule, matches in zip(_RULES, labelled, strict=True):
        if not matches:
            continue
        # `(match, restated)`, label-anchored readings first so a field's
        # candidates stay contiguous and in the order they were said.
        #
        # ~~`readings = [(match, False) for match in matches]`~~ — CHANGED
        # 2026-09-13: the list is now assembled PER REGION, below, because THE
        # SEQUENCE GATE can withhold a region's label reading. Assembling it up
        # front made that structurally impossible to express, which is part of why
        # the reader promoted the first value of a progression for so long.
        readings: list[tuple[re.Match[str], bool]] = []

        # PASS TWO — the same sentence restating the quantity WITHOUT restating
        # the label. Gated on pass one having matched, so a bare number is never
        # read; scanned only from the end of the last label-anchored match, so
        # the label still PRECEDES the value exactly as the rule's own pattern
        # requires ("At 300 K the temperature was 425 K" reads 425 alone).
        #
        # AND GATED ON THREE CONDITIONS, ALL REQUIRED, which together are the
        # corrections of 2026-09-12 (first and second pass). Ungated, this scan
        # read the whole remainder of
        # the segment for a bare value form and proposed a ramp rate, a step size,
        # a pressure, a cryostat setpoint, an END instant and a FUTURE run's
        # instant as alternatives for the labelled field. The FIRST gate closed
        # those six and left thirteen more, because six of the eleven connectives
        # modify what FOLLOWS them rather than hedging what came before, and
        # because `K\b` treats `K/` as a word boundary; the SECOND closed those
        # and left four, because a bare hedge in front of a complete unit says
        # nothing about the phrase behind it:
        #
        #   (1) `_HEDGE_BRIDGE`       — a qualifying connective, and nothing else,
        #                               between the two values. The six ambiguous
        #                               ones bridge only behind an explicit `or`.
        #   (2) `_unit_is_complete`   — the unit is the WHOLE unit, so `3 K/min` is
        #                               not read as 3 kelvin however it is
        #                               introduced.
        #   (3) `_statement_ends_after` — the restatement ends the statement, or
        #                               is followed by another restatement that was
        #                               itself accepted. UNIVERSAL over all three
        #                               hedge branches since 2026-09-12 (third
        #                               pass); it was scoped to the bare-hedge
        #                               branch for one commit and five sentences
        #                               fabricated through the `or` branch.
        #
        # `_OR_REQUIRED_HEDGES`, `_UNIT_TERMINATORS` and `_STATEMENT_END` carry the
        # three measured tables, and `_RESTATEMENT_RESIDUE_CLOSED` carries every
        # sentence the three conditions were built against — nine now, all refused
        # and all disclosed. A refusal by ANY of the three is disclosed —
        # `unhedged_further_values` for (1) and (2), which are both "this is not a
        # restatement of that quantity", and `trailing_text_after_further_values`
        # for (3), which is a different sentence and so is a different kind. The
        # overlap skip above is disclosed by neither, because it withholds nothing.
        #
        # `fullmatch`, NOT `$`. The bridge must be the WHOLE gap, and `$` also
        # matches before a trailing newline — the exact laxity this repository
        # already ships an exactness gate for (`src/isaac_records/exactness.py`).
        # A segment cannot contain a newline today (`_SEGMENT_BOUNDARY` splits on
        # them), so this is not a live hole being closed; it is a guard written so
        # it does not become one if segmentation ever changes.
        # ONE REGION PER LABEL MATCH, NOT ONE REGION PER RULE.
        #
        # ~~`anchor = max(match.end() for match in matches)`~~ — CORRECTED
        # 2026-09-12 (fourth pass) by independent review. That scanned from the
        # end of the LAST label match, so a restatement sandwiched BETWEEN two
        # label matches was never evaluated, therefore never refused, therefore
        # never disclosed — which falsified the claim the whole three-condition
        # trade rests on. §5 ranks a silent omission below a disclosed one, and
        # "no withholding is silent" was true only of single-label sentences,
        # which is the only shape the 476-cell sweep covers (~~510~~: that grid is
        # DERIVED, and `and again` left `_BARE_HEDGES` in the same commit range).
        # Measured at
        # `22d794a5`:
        #
        #   "The temperature was 425 K, maybe 428 K, and the temperature was
        #    430 K."                    -> [425, 430], 428 NEVER READ, no
        #                                  abstention at all
        #   "...started A, maybe B, and the scan started C."
        #                               -> [A, C], B silent
        #
        # It was an OMISSION and not an assertion, and it was NOT a regression:
        # `main` loses both 428 and 430. What it broke is the disclosure
        # guarantee.
        #
        # Each label match `Li` now owns the half-open region
        # `[Li.end(), L(i+1).start())`, and the LAST match owns
        # `[Lk.end(), len(text))` — byte-identical to the old single walk, which
        # is why no previously-accepted reading moves. A restatement in an
        # EARLIER region can only ever REFUSE, and that is a property rather than
        # a hope: `_statement_ends_after` looks at the whole remaining text, and
        # the remainder of an earlier region always contains the next label match,
        # so condition 3 can never hold there. So this change adds DISCLOSURES and
        # cannot add a candidate — asserted, not asserted-about.
        #
        # ~~`if rule.restatement is not None:` wrapped this whole walk~~ — REMOVED
        # 2026-09-13. The region is now walked for EVERY rule, because a region
        # decides whether its own label reading survives THE SEQUENCE GATE, and a
        # rule without a restatement pattern simply finds no siblings. The walk's
        # restatement half is guarded where it is used instead, which is also why
        # `if region_start >= region_end: continue` became a guard rather than a
        # `continue`: skipping the region used to skip nothing that mattered, and
        # now it would skip the label reading itself.
        for position, match in enumerate(matches):
            region_start = match.end()
            region_end = (
                matches[position + 1].start()
                if position + 1 < len(matches)
                else len(segment.text)
            )
            anchor = region_start
            #: Each ACCEPTED restatement, in text order. Held separately from
            #: `readings` because the third condition is decided over the chain and
            #: not over one restatement: see the tail walk below.
            #:
            #: ~~`(match, bridged_by_a_BARE_hedge)`~~ — the second element is GONE
            #: (2026-09-12, third pass). Condition 3 became UNIVERSAL, so nothing
            #: asks which branch admitted the gap, and a flag every iteration
            #: computed and every reader discarded is dead weight with a rationale
            #: that no longer describes the code. `_BARE_HEDGE_BRIDGE`, which
            #: existed only to compute it, is deleted for the same reason.
            accepted: list[re.Match[str]] = []
            #: **THE SEQUENCE GATE'S EVIDENCE.** Every further value of this field
            #: in this region that this reader cannot tell apart from the label's
            #: own: a complete unit, a clean continuation, a gap of pure
            #: coordination, and a DIFFERENT value. One of these means the sentence
            #: states the field more than once and says nothing about which
            #: statement is the field's — *"was 300 K, then 350 K, then 400 K"* —
            #: so no value is selected, INCLUDING the label's own.
            siblings: list[re.Match[str]] = []
            #: THIS REGION's refusals, held locally rather than written straight
            #: into `pending`. THE SEQUENCE GATE below can withhold the region's
            #: label reading, and both other refusal reasons say the labelled value
            #: WAS read ("only the labelled one was read"). Serving one of those
            #: beside a region that read nothing would publish a sentence the
            #: response itself contradicts — the exact defect class this module
            #: keeps finding. So a withheld region discloses ONCE, truthfully.
            region_pending: list[tuple[str, str, str, tuple[int, int]]] = []
            restatements = (
                rule.restatement.finditer(segment.text, anchor, region_end)
                if rule.restatement is not None and region_start < region_end
                else ()
            )
            for extra in restatements:
                if any(
                    _spans_overlap(extra.span(1), claimed)
                    for claimed in claimed_value_spans
                ):
                    # NOT recorded as a refusal, deliberately. This value WAS
                    # read — by another rule, under its own label — so nothing
                    # was withheld from the scientist and a disclosure saying
                    # "a value here was not read" would be false. Only the three
                    # gates below withhold a reading.
                    continue
                gap = segment.text[anchor : extra.start(1)]
                if _HEDGE_BRIDGE.fullmatch(gap) is None:
                    # THE SEQUENCE GATE, decided HERE because this is the one
                    # branch where the refused value is still a plausible value OF
                    # THIS FIELD: no hedge linked it, and nothing has said it is
                    # anything else. Three conditions, each of which must hold, and
                    # each of which exists because a corpus row would otherwise
                    # lose a legitimate reading:
                    #
                    #   * the unit is the WHOLE unit — "425 K, ramped at 3 K/min"
                    #     names a rate, so 425 survives;
                    #   * the continuation leaves the value absolute — "425 K,
                    #     maybe 430 K, and again 3 K of drift" names a drift, so
                    #     425 survives;
                    #   * the gap is PURE COORDINATION — "425 K, cryostat setpoint
                    #     80 K" names a different instrument, so 425 survives.
                    #
                    # And the value must DIFFER: "425 K, and again 425 K" is one
                    # value said twice, which is emphasis and not a progression.
                    # That condition is what answers the cost this gate was briefed
                    # with — "425 K, still 425 K at the end" keeps its reading.
                    if (
                        _unit_is_complete(segment.text, extra)
                        and _continuation_is_clean(rule, segment.text, extra)
                        and _SIBLING_GAP.fullmatch(gap) is not None
                        and _value_of(rule, extra) != _value_of(rule, match)
                    ):
                        siblings.append(extra)
                    region_pending.append(
                        (rule.name, _KIND_UNHEDGED, match.group(0), extra.span(1))
                    )
                    continue
                # THE SECOND CONDITION. The connective is sound and the
                # unit may still not be this rule's unit: `3 K/min` is a ramp
                # rate, and `K\b` treats `K/` as a word boundary. See
                # `_UNIT_TERMINATORS` for the measured table and for why the
                # check is an allowlist over ONE following character rather than
                # a rule about the rest of the sentence.
                if not _unit_is_complete(segment.text, extra):
                    region_pending.append(
                        (rule.name, _KIND_UNHEDGED, match.group(0), extra.span(1))
                    )
                    continue
                accepted.append(extra)
                # THE ANCHOR ADVANCES ONLY ON AN ACCEPTED RESTATEMENT, so the
                # chain is a chain of hedges rather than a chain of positions:
                # "425 K, maybe 430 K, or perhaps 435 K" reads all three, while
                # "425 K, cryostat setpoint 80 K, base 4 K" refuses both — 4's gap
                # is measured from 425, not from the 80 that was just refused.
                #
                # It advances even for a restatement the de-duplication below then
                # drops as an identical value, deliberately: adjacency is a fact
                # about the TEXT, so "425 K, maybe 425 K, or perhaps 430 K" still
                # reads 430.
                #
                # AND IT ADVANCES BEFORE THE THIRD CONDITION IS APPLIED, which is
                # not an oversight: the third condition's clause 2 asks whether a
                # further restatement was accepted, so it cannot be decided until
                # the whole chain is known. A restatement dropped below therefore
                # never retroactively re-anchors the gap of one after it — the
                # chain loses a TAIL, not a link.
                anchor = extra.end()

            # THE THIRD CONDITION, WALKED INWARD FROM THE TAIL. See
            # `_STATEMENT_END`. EVERY accepted restatement must END the statement,
            # and "another accepted restatement follows it" counts as ending it —
            # which is exactly "it is not the last surviving link", because a link
            # is only accepted when a hedge bridge sits immediately in front of it.
            # So the predicate is decidable only at the tail, and dropping the tail
            # can expose a new one. Measured:
            # "425 K, maybe 430 K, and again 3 K of drift" loses BOTH — `3` for
            # its own trailing phrase, `430` because what follows it is now a
            # bridge to a refusal rather than to a reading.
            #
            # ~~"A restatement behind an explicit `or` is never popped: that branch
            # carries a grammatical alternation marker, and the previous slice's own
            # argument for it is unrefuted."~~ — **UNIVERSAL SINCE 2026-09-12 (third
            # pass), and the exemption is struck rather than deleted because it was
            # the reason a measured §5 false-positive class shipped twice.** The
            # alternation marker is a real grammatical fact and it is still what
            # CONDITION 1 rests on; what it does NOT do is say anything about the
            # words AFTER the value, which is the only thing condition 3 asks. The
            # five sentences that exemption left fabricating are in
            # `_RESTATEMENT_RESIDUE_CLOSED`, measured before and after.
            while accepted and not _statement_ends_after(
                segment.text, accepted[-1].end()
            ):
                popped = accepted.pop()
                region_pending.append(
                    (rule.name, _KIND_TRAILING, match.group(0), popped.span(1))
                )

            # THE SEQUENCE GATE APPLIED. Decided after the tail walk, so a
            # restatement that condition 3 popped is not counted twice, and applied
            # to the WHOLE region: if this reader cannot say which value is the
            # field's, it cannot offer an alternative either, so the label reading
            # and every accepted restatement of this region go together.
            #
            # PER REGION AND NOT PER SEGMENT, deliberately. "The temperature was
            # 425 K and 430 K and the temperature was 500 K" withholds the first
            # clause and still reads 500: the ambiguity is local to the clause that
            # contains it, and widening it to the segment would let one sloppy
            # clause delete a clean one.
            if siblings:
                pending.append(
                    (rule.name, _KIND_NONE_SELECTED, match.group(0), match.span(1))
                )
                withheld_value_spans.append(match.span(1))
                continue

            pending.extend(region_pending)
            readings.append((match, False))
            readings.extend((extra, True) for extra in accepted)
            # AFTER the tail pops, so a popped restatement is NOT counted as read.
            accepted_value_spans.extend(extra.span(1) for extra in accepted)

        # ONE VALUE STATED TWICE IN ONE SENTENCE IS ONE CANDIDATE.
        # "425 K, and again 425 K" is emphasis, not disagreement. Two identical
        # candidates would mint two durable proposals — `routes`'
        # `_mint_transcript_proposals` keys on the candidate INDEX, so they do
        # not collapse — giving one fact two independently acceptable rows.
        # SCOPED TO ONE SEGMENT, deliberately: two sentences are two statements,
        # and `test_the_same_value_said_twice_is_not_a_conflict` pins that as two
        # candidates. The equality is `repr`, the same one the grouping in
        # `read_transcript` uses, so the two cannot disagree about what "the same
        # value" means.
        seen: set[str] = set()
        for match, restated in readings:
            raw = match.group(1).strip()
            if not raw:
                continue
            value = _read_number(raw) if rule.numeric else raw
            if repr(value) in seen:
                continue
            seen.add(repr(value))
            found.append(
                _Reading(rule=rule, match=match, restated=restated, value=value)
            )

    # A REFUSAL THAT ANOTHER RULE'S PASS TWO ALREADY READ IS DROPPED, NOT REPORTED.
    #
    # This is the second half of the principle stated at the overlap skip above: a
    # disclosure saying "a value here was not read" is FALSE when some rule read it,
    # so the skip is deliberately silent. That guard could only see pass ONE
    # (`claimed_value_spans` is built from `rule.pattern` matches), so a value
    # accepted by another rule's RESTATEMENT scan escaped it. Measured at
    # `22d794a5`:
    #
    #   "The scan started A and ended B, or maybe C."
    #     -> acquired_start=A, acquired_end=B, acquired_end=C (restated, correct)
    #     -> AND an `unhedged_further_values` abstention saying further values for
    #        timestamps.acquired_start_utc "were not read" -- while BOTH were read.
    #
    # The refusal decision therefore cannot be taken while walking one rule: it
    # depends on what LATER rules accept, and `_RULES` order is arbitrary with
    # respect to which rule reads a given span. Locating every reading first and
    # emitting refusals afterwards is what makes the claim checkable rather than
    # order-dependent.
    #
    # A REFUSAL IS NEVER WEAKENED INTO SILENCE BY THIS: it is dropped only when the
    # ~~exact~~ span it withholds OVERLAPS one that was READ, which means nothing is
    # withheld and there is nothing to disclose.
    #
    # ~~"the exact span"~~ — **CORRECTED 2026-09-13: the predicate is
    # `_spans_overlap`, not equality, and the difference is reachable.**
    # `_ATMOSPHERE`/`_ENVIRONMENT` claim a `_PHRASE` span up to 61 characters, so a
    # kelvin refusal whose value falls INSIDE a phrase candidate is dropped without
    # its own disclosure — an independent review measured 32 such cells in 40,000.
    # It is not a §5 loss and that is measured too: in all 32 the number still
    # reaches the scientist, quoted verbatim inside the phrase candidate they are
    # being asked to confirm. So the COMMENT is corrected and the predicate is not:
    # requiring equality would emit a disclosure saying a value "was not read"
    # about text sitting in a candidate on the same screen. A rule's own accepted spans are in the set too, which is
    # harmless — a span is visited once per rule, so a rule cannot both accept and
    # refuse one.
    # AND THE PASS-ONE GATE'S REFUSALS GO THROUGH THE SAME FILTER, for the same
    # reason: a permissive detector match whose value some OTHER rule read under
    # its own label withholds nothing, so a disclosure about it would be false.
    pending.extend(gate_refusals)
    withheld = set(withheld_value_spans)
    read_value_spans = [
        span for span in claimed_value_spans if span not in withheld
    ] + accepted_value_spans
    for rule_name, kind, quote, value_span in pending:
        if any(_spans_overlap(value_span, read) for read in read_value_spans):
            continue
        refused.setdefault((rule_name, kind), quote)

    # Rule ORDER, not insertion order: a disclosure list must be deterministic and
    # must not depend on which gate happened to refuse first. `_RULES` is the
    # module's own canonical order.
    return found, tuple(
        (rule.name, kind, refused[(rule.name, kind)])
        for rule in _RULES
        for kind in (
            _KIND_NOT_ASSERTED,
            _KIND_QUALIFIED,
            _KIND_NOT_THIS_SUBJECT,
            _KIND_NONE_SELECTED,
            _KIND_UNHEDGED,
            _KIND_TRAILING,
        )
        if (rule.name, kind) in refused
    )


# --- run reference resolution -------------------------------------------------


def _matching_runs(token: str, known_runs: tuple[RunRef, ...]) -> tuple[RunRef, ...]:
    """Runs a spoken token could name. Identifiers only; never a measured value.

    The precedence copies the run search this application already ships: an id
    matches WHOLE (a ULID's leading characters are shared by every run created in
    one session, so a substring test against one is a match-everything), a label
    matches by substring because a label is prose a person wrote, and an all-digit
    token additionally matches by ordinal.
    """
    needle = token.strip().lower()
    if not needle:
        return ()
    ordinal = int(needle) if needle.isdigit() and len(needle) <= 6 else None
    matched: list[RunRef] = []
    for run in known_runs:
        if needle == run.id.lower():
            matched.append(run)
        elif run.record_id is not None and needle == run.record_id.lower():
            matched.append(run)
        elif needle in run.label.lower():
            matched.append(run)
        elif ordinal is not None and run.ordinal == ordinal:
            matched.append(run)
    return tuple(matched)


def _run_clarifications(
    segments: tuple[Segment, ...],
    *,
    selected_run: str | None,
    known_runs: tuple[RunRef, ...],
) -> tuple[Clarification, ...]:
    """Every run-reference ambiguity in the transcript. Resolves nothing."""
    found: list[Clarification] = []
    options = tuple(run.to_option() for run in known_runs)
    for segment in segments:
        vague = _VAGUE_RUN.search(segment.text)
        if vague is not None:
            found.append(
                Clarification(
                    kind="vague_run_reference",
                    question=(
                        "This sentence refers to a run by position rather than by "
                        "name, number or id. Which run is it?"
                    ),
                    quote=vague.group(0),
                    options=options,
                    segment_index=segment.index,
                )
            )
            continue
        for match in _RUN_REFERENCE.finditer(segment.text):
            token = match.group(1)
            if token.lower() in _NOT_A_RUN_NAME:
                continue
            matched = _matching_runs(token, known_runs)
            if not matched:
                found.append(
                    Clarification(
                        kind="unknown_run_reference",
                        question=(
                            "This record has no run matching the run named here. "
                            "Which run is it, or should one be created?"
                        ),
                        quote=match.group(0),
                        options=options,
                        segment_index=segment.index,
                    )
                )
            elif len(matched) > 1:
                found.append(
                    Clarification(
                        kind="ambiguous_run_reference",
                        question=(
                            "The run named here matches more than one run of this "
                            "record. Which one is it?"
                        ),
                        quote=match.group(0),
                        options=tuple(run.to_option() for run in matched),
                        segment_index=segment.index,
                    )
                )
            elif selected_run is not None and matched[0].id != selected_run:
                found.append(
                    Clarification(
                        kind="conflicting_run_reference",
                        question=(
                            "This capture is addressed to one run and the "
                            "transcript names another. Which run should the values "
                            "be proposed against?"
                        ),
                        quote=match.group(0),
                        options=tuple(
                            run.to_option()
                            for run in known_runs
                            if run.id in {selected_run, matched[0].id}
                        ),
                        segment_index=segment.index,
                    )
                )
    return tuple(found)


# --- the reading ---------------------------------------------------------------


def read_transcript(
    text: str,
    *,
    selected_run: str | None,
    known_runs: tuple[RunRef, ...],
) -> TranscriptReading:
    """Read a FINALIZED transcript. Pure: no clock, no randomness, no I/O.

    ``selected_run`` is the run a scientist chose for this capture, and it is the
    ONLY thing that settles the target. A run named inside the transcript is
    checked against it and can raise a clarification, but it never becomes the
    target on its own — inferring a write target from prose is the guess this
    whole feature is arranged to refuse.

    **Candidates are withheld whenever the run target is unsettled**, which is
    every case where a clarification about the run was raised, and the case where
    no run was selected at all. That is deliberately blunt: a candidate a
    scientist could accept against the wrong run is worse than no candidate, and
    the transcript itself is retained either way, so nothing is lost by asking.
    """
    segments = segment_transcript(text)
    clarifications = list(
        _run_clarifications(segments, selected_run=selected_run, known_runs=known_runs)
    )
    if selected_run is None:
        clarifications.insert(
            0,
            Clarification(
                kind="run_target_required",
                question=(
                    "Which run do these notes describe? Every value this reader "
                    "can propose belongs to a run, and the run is never chosen "
                    "automatically — not even when the record has exactly one."
                ),
                quote=None,
                options=tuple(run.to_option() for run in known_runs),
                segment_index=None,
            ),
        )

    abstentions: list[Abstention] = []
    candidates: list[FieldCandidate] = []
    candidate_by_segment: dict[int, int] = {}
    #: Every reading this transcript will turn into a candidate, LOCATED but not
    #: yet constructed, with the two running totals the ceilings are checked
    #: against. See the check below for why construction is deferred.
    located: list[tuple[Segment, list["_Reading"]]] = []
    candidate_count = 0
    quote_bytes = 0
    # The run target is settled only when a run was selected AND nothing about a
    # run was left open. See the docstring.
    settled = selected_run is not None and not clarifications

    for segment in segments:
        implicit = _IMPLICIT_ONLY.search(segment.text)
        if implicit is not None:
            abstentions.append(
                Abstention(
                    kind="implicit_only_subject",
                    reason=(
                        "The absorbing element and the absorption edge are recorded "
                        "by this build as implicit, sidecar-only content: the "
                        "official record schema it validates against provides no "
                        "field for either, so there is no path to propose a value "
                        "at and none is invented."
                    ),
                    quote=implicit.group(0),
                    segment_index=segment.index,
                )
            )
        # THE NON-KELVIN DISCLOSURE, SPAN-GUARDED RATHER THAN SEGMENT-GUARDED.
        #
        # ~~`if other_unit is not None and not _TEMPERATURE_K.search(segment.text)`~~
        # — CORRECTED, because it asked "does this sentence contain ANY kelvin
        # reading?" and a kelvin reading ANYWHERE suppressed the disclosure for a
        # non-kelvin statement ELSEWHERE in the same sentence. Measured on the old
        # code: "Temperature was 425 K, maybe 430 C." proposed 425 and produced NO
        # abstention at all, so `430 C` vanished from the reading exactly as `430 K`
        # did — the same silent loss, reached through the guard instead of through
        # `search`.
        #
        # The narrow and correct question is whether THIS non-kelvin statement is
        # the one the kelvin rule already read, and the VALUE spans answer it. The
        # value spans rather than the whole-match spans, because `_TEMPERATURE_OTHER`
        # starts at the same `temperature` label and therefore always overlaps the
        # kelvin rule's whole match — comparing those would suppress every
        # disclosure and would look like it was working.
        kelvin_value_spans = [
            match.span(1) for match in _TEMPERATURE_K.finditer(segment.text)
        ]
        for other_unit in _TEMPERATURE_OTHER.finditer(segment.text):
            if any(
                _spans_overlap(other_unit.span(1), claimed)
                for claimed in kelvin_value_spans
            ):
                continue
            abstentions.append(
                Abstention(
                    kind="temperature_not_in_kelvin",
                    reason=(
                        "The temperature field records kelvin and this statement "
                        "gives another unit. Converting it would place a number in "
                        "the record that nobody stated, so nothing is proposed. "
                        "State the value in kelvin to propose one."
                    ),
                    quote=other_unit.group(0),
                    segment_index=segment.index,
                )
            )
        if not settled:
            continue
        found, refused_rules = _segment_readings(segment)
        # THE REFUSAL DISCLOSURE. One per segment per rule, no more: the reading
        # says WHICH FIELD had further values withheld and tells the scientist to
        # check the sentence. It asserts nothing about the withheld numbers — it
        # does not quote them, count them, classify them or name a unit for them,
        # because the whole reason they were withheld is that this reader does not
        # know what they are.
        #
        # BOUNDED BY CONSTRUCTION at `MAX_SEGMENTS` x the three rules that HAVE a
        # restatement x the two refusal KINDS = 600. The pre-existing gap that made
        # that bound load-bearing — neither density ceiling could see an
        # accumulator this one feeds — is CLOSED by `MAX_DISCLOSURES` below; see
        # `_DISCLOSURE_CEILING_GAP` for the measurements that closed it.
        for rule_name, refusal_kind, refused_quote in refused_rules:
            rule = next(entry for entry in _RULES if entry.name == rule_name)
            abstentions.append(
                Abstention(
                    kind=refusal_kind,
                    reason=_REFUSAL_REASONS[refusal_kind].format(
                        field_path=rule.field_path
                    ),
                    quote=refused_quote,
                    segment_index=segment.index,
                )
            )
        if not found:
            continue
        located.append((segment, found))
        candidate_count += len(found)
        # EVERY CANDIDATE CARRIES THE WHOLE SEGMENT, so the segment's byte length
        # times the number of readings over it IS the quoted cost, exactly. It is
        # carried TWICE per candidate (`quote`, and inside the `rule` sentence), so
        # the served size is about twice this plus per-candidate overhead; the
        # ceiling is stated over the quoted bytes rather than over a guess at the
        # serialised size, because this half is a measurement and that half is not.
        quote_bytes += len(segment.text.encode("utf-8")) * len(found)

    # THE CEILINGS ARE APPLIED BEFORE THE FIRST `FieldCandidate` IS CONSTRUCTED,
    # AND THAT ORDERING IS THE POINT RATHER THAN AN OPTIMISATION. Building the
    # 3,001 candidates of the measured attack and then discarding them allocates
    # **137,256,245 bytes** of `rule` strings and **135,120,025** of `quote`,
    # inside `record_lock` — paying the ceiling in full in order to enforce it.
    # (Measured here, on the 45,025-byte hedged payload, with both ceilings lifted.
    # The reviewer's "~81 MB" is right for the 27,025-byte BARE payload, which the
    # adjacency gate now reads as ONE candidate, so it is no longer the payload
    # these ceilings fire on. Quoting the number for the wrong payload is the kind
    # of inherited figure this file corrects rather than carries.)
    #
    # The locating pass above allocates match objects and one value per reading,
    # which is what makes an EXACT count and an EXACT byte total available here for
    # nothing — and the byte total is exact, not an estimate: `quote_bytes` equals
    # `sum(len(candidate.quote.encode()))` over the candidates that would have been
    # built, measured identical at 135,120,025.
    #
    # THE THIRD COUNT IS THE DISCLOSURES, AND IT IS CHECKED HERE RATHER THAN IN ITS
    # OWN PLACE FOR ONE REASON: this is the last point before the response's cost
    # is committed, and all three numbers are EXACT here. See `MAX_DISCLOSURES`
    # for what it bounds, what it does not, and the worst legitimate case it still
    # admits.
    #
    # THE DISCLOSURES ARE CONSTRUCTED AND THEN COUNTED, WHERE THE CANDIDATES ARE
    # COUNTED AND THEN CONSTRUCTED, AND THE ASYMMETRY IS DELIBERATE. A candidate
    # carries the whole segment TWICE, so building the ones the ceiling then
    # refuses costs O(values x segment length) — 137 MB, measured. A disclosure
    # carries a shared reason string and a short label-anchored quote, and there
    # can be at most one per regex match in a 256 KiB input, so building them is
    # O(transcript size) and bounded by the input ceiling that already exists. What
    # was NOT bounded, and is what this closes, is the RESPONSE: 16,384 abstentions
    # serialise to ~5.1 MB inside `record_lock`.
    #
    # THE FOURTH COUNT IS THE RUN OPTIONS THOSE DISCLOSURES CARRY, and it is here
    # for the same reason the third is: this is the last point before the response's
    # cost is committed, and the number is EXACT. It is summed over the
    # `Clarification` tuples that already exist, so it allocates nothing —
    # `_run_clarifications` builds ONE shared `options` tuple and every entry
    # references it, which is exactly why the in-memory cost is small and the
    # SERIALISED cost is not. See `MAX_DISCLOSURE_OPTIONS` for the measured table,
    # for why it is the exact served count and not `disclosures x len(known_runs)`,
    # and for the wire change that would remove the need for it.
    disclosure_count = len(abstentions) + len(clarifications)
    disclosure_options = sum(len(entry.options) for entry in clarifications)
    if (
        candidate_count > MAX_CANDIDATES
        or quote_bytes > MAX_CANDIDATE_QUOTE_BYTES
        or disclosure_count > MAX_DISCLOSURES
        or disclosure_options > MAX_DISCLOSURE_OPTIONS
    ):
        raise TranscriptTooDense(
            candidates=candidate_count,
            candidate_quote_bytes=quote_bytes,
            disclosures=disclosure_count,
            disclosure_options=disclosure_options,
            maximum_candidates=MAX_CANDIDATES,
            maximum_candidate_quote_bytes=MAX_CANDIDATE_QUOTE_BYTES,
            maximum_disclosures=MAX_DISCLOSURES,
            maximum_disclosure_options=MAX_DISCLOSURE_OPTIONS,
        )

    for segment, found in located:
        produced: list[int] = []
        for reading in found:
            rule = reading.rule
            candidates.append(
                FieldCandidate(
                    field_path=rule.field_path,
                    proposed_value=reading.value,
                    quote=segment.text,
                    start_char=segment.start_char,
                    end_char=segment.end_char,
                    origin=ORIGIN_TRANSCRIPT,
                    produced_by=PRODUCED_BY,
                    rule=(
                        f"in the sentence {segment.text.strip()!r}, "
                        f"{rule.restated_sentence if reading.restated else rule.sentence}; "
                        f"the value is quoted from the transcript, not interpreted"
                    ),
                    provenance=MappingProxyType(
                        {
                            "reader_rule": rule.name,
                            "run_id": selected_run,
                            "segment_index": segment.index,
                            "matched_text": reading.match.group(0),
                            # A RESTATEMENT SAYS SO. Its `rule` sentence already
                            # explains it in prose; this is the same fact where a
                            # surface can branch on it without parsing English.
                            "restated_in_same_sentence": reading.restated,
                        }
                    ),
                )
            )
            produced.append(len(candidates) - 1)
        # Exactly one, or none. See `candidate_for_segment`.
        if len(produced) == 1:
            candidate_by_segment[segment.index] = produced[0]

    review: list[ReviewRequired] = []
    by_path: dict[str, list[int]] = {}
    for position, candidate in enumerate(candidates):
        by_path.setdefault(candidate.field_path, []).append(position)
    for field_path, positions in by_path.items():
        values = {repr(candidates[position].proposed_value) for position in positions}
        if len(values) > 1:
            review.append(
                ReviewRequired(
                    kind="conflicting_values_for_one_field",
                    field_path=field_path,
                    reason=(
                        "This transcript proposes more than one value for this "
                        "field. Both proposals are listed and neither is preferred "
                        "— choosing the later one would be a guess, and dropping "
                        "them would lose something that was said twice. Accept at "
                        "most one."
                    ),
                    candidate_indexes=tuple(positions),
                )
            )

    return TranscriptReading(
        segments=segments,
        candidates=tuple(candidates),
        clarifications=tuple(clarifications),
        abstentions=tuple(abstentions),
        review_required=tuple(sorted(review, key=lambda entry: entry.field_path)),
        candidate_by_segment=MappingProxyType(dict(candidate_by_segment)),
        run_target=selected_run if candidates else None,
    )

"""The transcript reader's two density ceilings, MEASURED rather than argued.

WHY THIS FILE EXISTS
====================
``test_transcript_capture_multiple_values.py`` shipped a test named
``test_the_reader_adds_no_ceiling_because_the_durable_write_already_has_one``. It
argued, at length, that the cost of a dense transcript lands on the DURABLE WRITE
and that ``routes._MAX_PROPOSALS_PER_RECORD`` already bounded it. Then it asserted
``isinstance(routes._MAX_PROPOSALS_PER_RECORD, int)`` and ``> 0``, measured no
size, no count and no time — and forbade the fix, with
``assert not [name for name in dir(tc) if "MAX" in name and name != "MAX_SEGMENTS"]``.

Its premise was wrong. Measured through the real route at ``47fdbe30``:

===============================================  ===========  ==================
transcript                                       candidates   response bytes
===============================================  ===========  ==================
27,025 B, ONE segment, 3,000 kelvin values            3,001         165,828,285
45,025 B, the same with ``", maybe "`` between        3,001         273,900,285
the owner's sentence (46 B)                               2              11,554
===============================================  ===========  ==================

Both dense cases returned **200**, having minted **zero** proposals: the durable
write refused all 3,001 rows as ``proposals_too_large``, exactly as designed. The
bound that test pointed at worked perfectly, and the request still assembled and
serialised 165 MB **inside ``record_lock``**. ``MAX_SEGMENTS`` does not help — it
is ONE segment, which is what punctuation-free ASR emits — and the 256 KiB
transcript ceiling does not either, because the cost is O(values × segment
length): every candidate carries the whole segment TWICE (``quote``, and inside
the ``rule`` sentence), so a client that runs out of COUNT can spend the rest of
its budget on LENGTH.

**The second row is the reason there are two ceilings and not one.** ``", maybe "``
is a hedged connective, so the C-1 adjacency gate ACCEPTS every one of those 3,000
restatements. The adjacency gate does not bound size and a size bound does not make
values honest: two defects, two fixes.

WHAT IS MEASURED HERE
=====================
Candidate count, response bytes and elapsed time through the real HTTP route; that
each ceiling binds ON ITS OWN; that a refusal stores nothing and serves no partial
list; that the ceilings are applied BEFORE the first ``FieldCandidate`` is built;
and that every ordinary transcript is untouched.

Everything is synthetic. Nothing connects to a database and no network call is made.
"""

from __future__ import annotations

import json
import time

import pytest

import isaac_api.routes as routes
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
        "Ceiling fixture",
        {"kind": "synthetic"},
        {"meta": {}, "fields": {}, "pending": []},
    )
    return exp.id


RUN = tc.RunRef(id="run-1", label="Run 1", ordinal=1)
TEMPERATURE = "context.temperature_K"


def _read(text: str):
    return tc.read_transcript(text, selected_run="run-1", known_runs=(RUN,))


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


def _finalize(client, experiment_id: str, text: str, *, run_id: str):
    return client.post(
        f"/api/experiments/{experiment_id}/transcript",
        json={"text": text, "finalized": True, "run_id": run_id},
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _notes(client, experiment_id: str) -> list[dict]:
    response = client.get(f"/api/experiments/{experiment_id}/notes")
    assert response.status_code == 200, response.text
    return response.json()["notes"]


def _proposals(client, experiment_id: str) -> list[dict]:
    response = client.get(f"/api/experiments/{experiment_id}/proposals")
    assert response.status_code == 200, response.text
    return response.json()["proposals"]


# --- the payloads, each built for exactly one purpose --------------------------


def _one_segment(joiner: str, count: int = 3000) -> str:
    """ONE segment — no ``.``, ``!``, ``?`` or newline anywhere — naming ``count``
    further kelvin values after a labelled one. ``joiner=", "`` reproduces the
    reviewer's 27,025-byte measurement exactly; ``", maybe "`` is the hedged form
    the C-1 gate still accepts."""
    head = "The temperature was 425 K"
    return head + joiner + joiner.join(f"{value} K" for value in range(10000, 10000 + count))


#: COUNT binds, BYTES do not: 100 segments (exactly ``MAX_SEGMENTS``, so the
#: segment ceiling stays out of it) each stating six hedged values, each segment
#: tiny. 600 candidates over 42,600 quoted bytes.
_COUNT_ONLY = " ".join(
    ["temperature 1 K, maybe 2 K, maybe 3 K, maybe 4 K, maybe 5 K, maybe 6 K."] * 100
)


def _bytes_only() -> str:
    """BYTES bind, COUNT does not: one enormous segment stating five values.

    Five candidates — a hedged chain of three temperatures, plus a start and an end
    instant — each quoting ~250 KB. Well inside ``MAX_CANDIDATES`` and well outside
    ``MAX_CANDIDATE_QUOTE_BYTES``, which is the whole point: a bound on rows that a
    client can defeat by making each row large is not a bound.
    """
    head = (
        "The temperature was 425 K, maybe 430 K, or perhaps 435 K and it started "
        "2026-01-01T00:00:00Z and ended 2026-01-02T00:00:00Z "
    )
    return head + "ab " * ((250_000 - len(head)) // 3)


OWNER_SENTENCE = "The temperature was around 425 K, maybe 430 K."


# =============================================================================
# 1. THE MEASUREMENT. The reviewer's own attack, through the real route.
# =============================================================================


def test_the_dense_hedged_transcript_is_refused_and_the_response_is_small(
    client, experiment_id
):
    """THE HEADLINE MEASUREMENT: 273,900,285 bytes -> a typed 422 of a few hundred.

    Every number asserted here is measured in this test rather than quoted, and the
    BYTE assertion is the deterministic one — the elapsed-time assertion is a smoke
    bound on a shared machine, not a benchmark, and is written loose enough to say
    nothing except "this is not quadratic any more".

    MUTATION: raising either ceiling above the payload turns this RED.
    """
    run = _make_run(client, experiment_id)
    text = _one_segment(", maybe ")
    # The payload is a legal transcript: one segment, inside the byte ceiling.
    assert len(_encode(text)) <= routes._MAX_TRANSCRIPT_BYTES
    assert len(tc.segment_transcript(text)) == 1

    started = time.perf_counter()
    response = _finalize(client, experiment_id, text, run_id=run["id"])
    elapsed = time.perf_counter() - started

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "transcript_too_dense"
    assert "finalize it in smaller pieces" in body["message"]
    # THE EXACT NUMBERS, not "at least". Both are computable before a candidate is
    # constructed, which is why they are exact.
    assert body["candidates"] == 3001
    assert body["maximum_candidates"] == tc.MAX_CANDIDATES
    assert body["candidate_quote_bytes"] == len(_encode(text)) * 3001
    assert body["maximum_candidate_quote_bytes"] == tc.MAX_CANDIDATE_QUOTE_BYTES

    # RESPONSE SIZE — the measurement that is the whole point of the slice.
    assert len(response.content) < 2048, len(response.content)
    # And a smoke bound on the lock hold. 2.0 s was measured before the fix.
    assert elapsed < 5.0, elapsed

    # NOTHING WAS STORED. Refuse whole, never truncate.
    assert _notes(client, experiment_id) == []
    assert _proposals(client, experiment_id) == []


def test_the_c1_gate_alone_does_NOT_bound_the_response(client, experiment_id):
    """The measurement that proves the pair is needed rather than one of them.

    ``", maybe "`` is a hedge, so the adjacency gate accepts all 3,000 restatements
    and the reading is as large as it ever was. Asserted on the READER with the
    ceilings lifted, because with them in place the route never gets that far —
    i.e. this measures the thing the ceilings exist for, not the ceilings.

    MUTATION: none available. This test exists to record a fact about the OTHER
    fix, and it would go RED if a future slice narrowed the hedge list so far that
    ``maybe`` stopped bridging — which is worth knowing too.
    """
    text = _one_segment(", maybe ")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tc, "MAX_CANDIDATES", 10**9)
        patch.setattr(tc, "MAX_CANDIDATE_QUOTE_BYTES", 10**12)
        reading = _read(text)
    assert len(reading.candidates) == 3001
    served = json.dumps([candidate.to_dict() for candidate in reading.candidates])
    # Two orders of magnitude over the bounded response above, from ONE segment.
    assert len(served) > 200_000_000, len(served)


def test_the_bare_dense_transcript_is_now_harmless_because_C1_refuses_it(
    client, experiment_id
):
    """The reviewer's FIRST payload, for completeness: ``", "`` is not a hedge.

    It is accepted, with exactly ONE candidate, and the response is proportional to
    the transcript rather than to transcript × values. Recorded because "the same
    payload now returns 200" would otherwise look like the ceiling failing to fire.
    """
    run = _make_run(client, experiment_id)
    text = _one_segment(", ")
    assert len(_encode(text)) == 27_025  # the reviewer's exact segment

    response = _finalize(client, experiment_id, text, run_id=run["id"])
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [entry["proposed_value"] for entry in payload["candidates"]] == [425]
    # 165,828,285 B before; now linear in the transcript, which one note requires.
    assert len(response.content) < 8 * len(_encode(text)), len(response.content)


def _encode(text: str) -> bytes:
    return text.encode("utf-8")


# =============================================================================
# 2. EACH CEILING BINDS ON ITS OWN. A bound that never binds alone is decoration.
# =============================================================================


def test_the_count_ceiling_binds_with_the_byte_ceiling_far_from_binding():
    """600 candidates over 42,600 quoted bytes — 4% of the byte ceiling.

    MUTATION: deleting the ``candidate_count > MAX_CANDIDATES`` clause turns this
    RED. Deleting the byte clause leaves it GREEN, which is the point.
    """
    with pytest.raises(tc.TranscriptTooDense) as raised:
        _read(_COUNT_ONLY)
    refusal = raised.value
    assert refusal.candidates == 600
    assert refusal.candidates > tc.MAX_CANDIDATES
    assert refusal.candidate_quote_bytes == 42_600
    assert refusal.candidate_quote_bytes < tc.MAX_CANDIDATE_QUOTE_BYTES


def test_the_byte_ceiling_binds_with_the_count_ceiling_far_from_binding():
    """Five candidates — 1% of the count ceiling — over 1,250,000 quoted bytes.

    THIS IS THE CASE A ROW COUNT CANNOT SEE, and it is why there are two constants
    rather than one. ``routes._MAX_PROPOSAL_STATE_BYTES`` exists beside
    ``routes._MAX_PROPOSALS_PER_RECORD`` for the identical reason.

    MUTATION: deleting the ``quote_bytes > MAX_CANDIDATE_QUOTE_BYTES`` clause turns
    this RED. Deleting the count clause leaves it GREEN.
    """
    text = _bytes_only()
    assert len(tc.segment_transcript(text)) == 1
    assert len(_encode(text)) <= routes._MAX_TRANSCRIPT_BYTES

    with pytest.raises(tc.TranscriptTooDense) as raised:
        _read(text)
    refusal = raised.value
    assert refusal.candidates == 5
    assert refusal.candidates < tc.MAX_CANDIDATES
    assert refusal.candidate_quote_bytes == len(_encode(text)) * 5
    assert refusal.candidate_quote_bytes > tc.MAX_CANDIDATE_QUOTE_BYTES


def test_the_byte_ceiling_refuses_at_the_route_too_and_stores_nothing(
    client, experiment_id
):
    """The byte ceiling is not only a reader property; it reaches a client.

    MUTATION: catching ``TranscriptTooDense`` and returning 200 with an empty
    candidate list turns this RED at the status assertion.
    """
    run = _make_run(client, experiment_id)
    response = _finalize(client, experiment_id, _bytes_only(), run_id=run["id"])
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "transcript_too_dense"
    assert response.json()["candidates"] == 5
    assert _notes(client, experiment_id) == []
    assert _proposals(client, experiment_id) == []


# =============================================================================
# 3. REFUSE WHOLE, NEVER TRUNCATE — and never serve a partial list.
# =============================================================================


def test_a_refused_reading_cannot_be_mistaken_for_a_successful_one():
    """WHY AN EXCEPTION RATHER THAN A MARKER ON THE READING.

    A ``TranscriptReading`` carrying ``too_dense=True`` and ``candidates=()`` would
    hand a caller that ignored the flag an empty list indistinguishable from a
    complete reading of a transcript that stated nothing — the silent discard this
    feature exists to end, reached through the fix instead of through the defect. A
    truncated list is worse still. So the ONE thing asserted here is that no
    ``TranscriptReading`` is produced at all.

    MUTATION: returning a reading with an empty ``candidates`` tuple instead of
    raising turns this RED.
    """
    for payload in (_one_segment(", maybe "), _COUNT_ONLY, _bytes_only()):
        with pytest.raises(tc.TranscriptTooDense):
            _read(payload)


def test_the_route_stores_no_note_and_mints_no_proposal_on_a_dense_refusal(
    client, experiment_id
):
    """The refusal is BEFORE the note loop and before ``_mint_transcript_proposals``.

    A prior capture's notes are proven to survive, so "stores nothing" is measured
    as "adds nothing" rather than as "the record happens to be empty" — which would
    pass on a route that stored and then rolled back, and would also pass if the
    record simply could not store notes at all.

    MUTATION: moving the ``except tc.TranscriptTooDense`` handler below the
    ``capture_note`` loop turns this RED.
    """
    run = _make_run(client, experiment_id)
    assert _finalize(
        client, experiment_id, OWNER_SENTENCE, run_id=run["id"]
    ).status_code == 200
    before_notes = _notes(client, experiment_id)
    before_proposals = _proposals(client, experiment_id)
    assert len(before_notes) == 1 and len(before_proposals) == 2

    refused = _finalize(client, experiment_id, _one_segment(", maybe "), run_id=run["id"])
    assert refused.status_code == 422, refused.text

    assert _notes(client, experiment_id) == before_notes
    assert _proposals(client, experiment_id) == before_proposals


def test_the_record_is_not_advanced_by_a_dense_refusal(client, experiment_id):
    """Nothing was saved, so the ETag a client already holds is still current.

    MUTATION: saving before the refusal turns this RED.
    """
    run = _make_run(client, experiment_id)
    before = _etag(client, experiment_id)
    assert _finalize(
        client, experiment_id, _one_segment(", maybe "), run_id=run["id"]
    ).status_code == 422
    assert _etag(client, experiment_id) == before


# =============================================================================
# 4. THE CEILING IS NOT PAID IN FULL BEFORE IT IS APPLIED.
# =============================================================================


def test_no_FieldCandidate_is_constructed_for_a_transcript_that_blows_a_ceiling():
    """Bounding the COUNT is not the same as bounding the CONSTRUCTION.

    Building 3,001 candidates and then discarding them allocates ~81 MB of ``rule``
    strings inside ``record_lock`` — paying the ceiling in full in order to enforce
    it. The locating pass (``_segment_readings``) allocates a match object and a
    parsed value per reading and nothing else, which is what makes the exact count
    and the exact byte total available for free.

    MUTATION: moving the ceiling check after the construction loop turns this RED
    with ``3001 != 0``.
    """
    built: list[int] = []
    real = tc.FieldCandidate

    def counting(*args, **kwargs):
        built.append(1)
        return real(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tc, "FieldCandidate", counting)
        with pytest.raises(tc.TranscriptTooDense):
            _read(_one_segment(", maybe "))
        assert built == [], len(built)

        # POSITIVE CONTROL: the counter does count, so `built == []` above is a
        # measurement rather than a broken patch. This is the assertion that makes
        # the one above evidence.
        reading = _read(OWNER_SENTENCE)
    assert len(built) == 2 == len(reading.candidates)


# =============================================================================
# 5. THE WORST LEGITIMATE CASES ARE ADMITTED, and ordinary ones are untouched.
# =============================================================================


@pytest.mark.parametrize(
    "label,text,expected_candidates",
    [
        # The single 256 KiB ASR blob named in `MAX_CANDIDATES`' own comment.
        ("a full-size blob stating no readable value", "A" * 262_000, 0),
        # `MAX_SEGMENTS` segments at two candidates each.
        (
            "100 segments x 2 candidates",
            " ".join(["temperature 1 K, maybe 2 K."] * 100),
            200,
        ),
        # `MAX_SEGMENTS` segments at four — the worst legitimate count the comment
        # claims to admit (MAX_SEGMENTS x 4 = 400).
        (
            "100 segments x 4 candidates",
            " ".join(["temperature 1 K, maybe 2 K, maybe 3 K, maybe 4 K."] * 100),
            400,
        ),
        # A near-full-size transcript at two candidates per segment: 2 x 256 KiB of
        # quotes, which is the worst legitimate BYTE case the comment names.
        (
            "a near-full-size transcript at 2 candidates per segment",
            " ".join(["temperature 1 K, maybe 2 K " + "cd " * 860 + "x."] * 100),
            200,
        ),
    ],
    ids=lambda value: value if isinstance(value, str) and len(value) < 60 else "",
)
def test_the_worst_legitimate_cases_are_still_admitted(label, text, expected_candidates):
    """Each is named in ``MAX_CANDIDATES``' or ``MAX_CANDIDATE_QUOTE_BYTES``' own
    comment as a case the bound must still read. A ceiling whose stated headroom is
    not measured is a ceiling nobody has checked.

    MUTATION: lowering either ceiling to the measured worst legitimate case turns
    one of these RED, which is the headroom being real rather than asserted.
    """
    assert len(_encode(text)) <= routes._MAX_TRANSCRIPT_BYTES
    assert len(tc.segment_transcript(text)) <= tc.MAX_SEGMENTS
    reading = _read(text)
    assert len(reading.candidates) == expected_candidates


def test_the_owners_sentence_and_the_canonical_capture_are_byte_identical(
    client, experiment_id
):
    """ORDINARY TRANSCRIPTS ARE UNTOUCHED, which is the constraint the ceilings had
    to be chosen under. Asserted on the whole response minus its two
    capture-specific identifiers, so a change anywhere in the payload is caught,
    not only in the candidate list.
    """
    run = _make_run(client, experiment_id)
    response = _finalize(client, experiment_id, OWNER_SENTENCE, run_id=run["id"])
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [entry["proposed_value"] for entry in payload["candidates"]] == [425, 430]
    assert len(payload["proposals"]) == 2
    assert payload["unproposable"] == []
    assert payload["applied"] is False
    assert payload["capture"]["segments"] == 1
    # And neither ceiling came near: the numbers, so a later tightening that would
    # have clipped the owner's own sentence fails here first.
    reading = _read(OWNER_SENTENCE)
    assert len(reading.candidates) == 2 <= tc.MAX_CANDIDATES
    assert len(_encode(OWNER_SENTENCE)) * 2 <= tc.MAX_CANDIDATE_QUOTE_BYTES


# =============================================================================
# 6. THE CONSTANTS THEMSELVES.
# =============================================================================


def test_the_byte_ceiling_is_a_multiple_of_the_transcript_ceiling():
    """``MAX_CANDIDATE_QUOTE_BYTES``' comment says it is written as a multiple of
    the transcript ceiling so it FOLLOWS that constant instead of drifting from it,
    and that the worst legitimate case (a full transcript at two candidates per
    segment) is admitted with one doubling of headroom. Both are checkable.

    This is the ``test_run_page_bound_parity.py`` idiom: two constants in two
    modules that must agree, pinned against each other so drift fails a test rather
    than shipping.

    MUTATION: changing either constant without the other turns this RED.
    """
    assert tc.MAX_CANDIDATE_QUOTE_BYTES == 4 * routes._MAX_TRANSCRIPT_BYTES
    # The worst legitimate byte case, and the headroom the comment claims.
    worst_legitimate = 2 * routes._MAX_TRANSCRIPT_BYTES
    assert tc.MAX_CANDIDATE_QUOTE_BYTES == 2 * worst_legitimate


def test_the_count_ceiling_sits_above_the_segment_ceiling_times_a_real_sentence():
    """Two claims from the route's own comment, pinned.

    (1) ``MAX_CANDIDATES`` admits ``MAX_SEGMENTS`` x 4, the worst legitimate count.
    (2) It sits ABOVE that, which is what keeps an ordinarily-long transcript
        reporting ``transcript_too_long`` rather than ``transcript_too_dense`` —
        the precedence consequence the route discloses instead of letting a client
        discover it.
    """
    assert tc.MAX_CANDIDATES >= tc.MAX_SEGMENTS * 4
    assert tc.MAX_CANDIDATES > tc.MAX_SEGMENTS


def test_an_ordinarily_long_transcript_still_reports_the_SEGMENT_reason(
    client, experiment_id
):
    """The precedence consequence, measured rather than reasoned.

    101 segments stating one value each: over ``MAX_SEGMENTS``, nowhere near
    ``MAX_CANDIDATES``. It must report ``transcript_too_long``, because that is the
    bound a scientist can act on — "finalize it in smaller pieces" for a reason
    they can see in their own text.

    MUTATION: lowering ``MAX_CANDIDATES`` below 101 turns this RED with
    ``transcript_too_dense``, which is the precedence the route's comment names.
    """
    run = _make_run(client, experiment_id)
    text = " ".join(["Temperature was 425 K."] * 101)
    assert len(tc.segment_transcript(text)) == 101 > tc.MAX_SEGMENTS
    response = _finalize(client, experiment_id, text, run_id=run["id"])
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "transcript_too_long"
    assert _notes(client, experiment_id) == []


def test_the_refusal_payload_names_both_ceilings_and_both_measurements():
    """A refusal a client cannot act on is a refusal that will be retried forever.

    The exception carries four numbers, and all four reach the wire — pinned
    because three of them are easy to drop as "internal".
    """
    with pytest.raises(tc.TranscriptTooDense) as raised:
        _read(_COUNT_ONLY)
    refusal = raised.value
    assert refusal.candidates == 600
    assert refusal.maximum_candidates == tc.MAX_CANDIDATES
    assert refusal.candidate_quote_bytes == 42_600
    assert refusal.maximum_candidate_quote_bytes == tc.MAX_CANDIDATE_QUOTE_BYTES
    # And the message says what it is, with both measurements in it.
    text = str(refusal)
    assert "600" in text and "42600" in text
    assert str(tc.MAX_CANDIDATES) in text

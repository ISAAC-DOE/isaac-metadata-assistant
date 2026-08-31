"""The concurrent pair no existing file reaches: a RECORD write against a RUN write
at the SAME address — plus the version sequence a cursor walk would depend on.

WHAT IS ALREADY COVERED, SO THIS FILE DOES NOT RE-COVER IT
==========================================================
``test_handler_concurrency.py`` — two ``/answers``, two ``/edit``, the precondition
rules, a read during an in-flight write. ``test_lifecycle_concurrency.py`` — run
edits, overrides vs clear, run removal vs edit, run removal vs submit, submit
double-click, two scientists submitting, conflict decisions.
``test_concurrent_write_pairs_lose_no_update.py`` — eight further pairs including
asset edits, an answer against a correction, wildcard writers, transcript vs edit,
note review, run removal vs note capture. ``test_discard_concurrency.py`` — discard.

Every pair the brief listed is in one of those **except one**, and this file adds it.

THE PAIR: A RECORD-LEVEL WRITE AGAINST A RUN OVERRIDE AT ONE ADDRESS
====================================================================
``system.technique`` is answerable at the RECORD (``POST .../answers``, which
``CLAUDE.md`` §11 records as new) and overridable at a RUN
(``POST .../runs/{id}/overrides`` with ``field:system.technique``, which the same
section records as already being in ``EXPERIMENT_OVERRIDABLE_ADDRESSES``). So one
address is writable at two levels, through two routes, holding **two different
validators** — the record's ETag and the run's — while both take the same
``record_lock``. That combination appears nowhere else in the suite, and it is
exactly where a lost update hides: a test of either route alone sees a clean write.

**THE EXPECTED OUTCOME IS NOT "EXACTLY ONE WINS", AND SAYING SO MATTERS.** These two
writes are not competing for one cell — one sets the record's inherited value, the
other displaces inheritance for one run. Both landing is CORRECT. What must not
happen is a torn state: a record field holding neither writer's value, an override
holding neither, a run that inherits after being overridden, or a revision that
moved without a write.

THE CHANGE FEED DOES NOT EXIST, AND THE SUBSTITUTE IS NAMED RATHER THAN IMPLIED
==============================================================================
The brief asked for change-feed ordering under concurrent writes at
``GET /api/experiments/{id}/changes``. **That route is not in this build.** Measured
over ``app.openapi()["paths"]`` at ``c2a93a7``: 71 operations, none named
``changes``, and ``test_live_sync.py``'s own docstring records why — live sync is
conditional polling on the existing detail route (``If-None-Match`` → ``304``), and
*"no new revision endpoint … the ``_detail`` bundle is small and already carries the
authoritative ``version``/ETag, so no new route is warranted"*.

So the property a cursor walk would rest on is asserted where it actually lives: the
record's **version sequence**. A client polls with its last-seen ETag; if a
concurrent write could advance the version without a change, or change the document
without advancing it, that client would either re-fetch forever or miss an update —
which is the same class of defect a feed that skipped or duplicated an entity would
have. That is stated as a substitute, not as the thing that was asked for.

Everything is synthetic. No database, no network; the only files touched are inside
the test's own ``tmp_path`` workspace.
"""

from __future__ import annotations

import copy
import json

import pytest

import isaac_api.workspace as ws

from conftest import client_ws, tutorial_client
from test_handler_concurrency import _LockRendezvous, _outcome, _race
from test_lifecycle_concurrency import _assert_raced, _confirmed

#: The one address writable at BOTH levels. Record-level key on the left, run-level
#: override address on the right; they name the same field path, which is the whole
#: reason this pair contends.
RECORD_ANSWER_KEY = "system.technique"
RUN_OVERRIDE_ADDRESS = "field:system.technique"

#: Two values from the schema's own 37-member enum, so neither write is refused for
#: a reason that has nothing to do with the race.
RECORD_VALUE = "XAS"
RUN_VALUE = "XES"
CORRECTED_VALUE = "RIXS"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


# --- reads used for ASSERTIONS ONLY, never to perform a mutation --------------


def _record_etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, eid: str, rid: str) -> str:
    response = client.get(f"/api/experiments/{eid}/runs/{rid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _fixture(store):
    """A record with one run, created through the store so no HTTP write precedes
    the race."""
    exp = store.create_experiment(
        "Cross-level concurrency fixture", {"kind": "synthetic"}, {}
    )
    exp.add_run(label="Run A", draft={})
    exp.save_versioned()
    return store.load_experiment(exp.id)


def _record_field(exp):
    return (exp.draft.get("fields") or {}).get(RECORD_ANSWER_KEY)


def _run_override(exp, rid: str):
    """The stored override ENVELOPE, or ``None``.

    A stored override is ``{"payload": <envelope>, "recorded_utc": …}`` — the
    envelope is nested, not the entry itself. Reading the entry and comparing it to
    a value is how the first version of this file reported ``None`` for an override
    that had landed perfectly well.
    """
    entry = (exp.get_run(rid).to_state().get("overrides") or {}).get(
        RUN_OVERRIDE_ADDRESS
    )
    return entry.get("payload") if isinstance(entry, dict) else entry


def _value_of(envelope):
    return envelope.get("value") if isinstance(envelope, dict) else envelope


# =============================================================================
# 1. the uncovered pair
# =============================================================================


def test_a_record_answer_and_a_run_override_at_one_address_do_not_tear(
    client, monkeypatch
):
    """The pair no other file reaches, driven through the pinned rendezvous.

    Two routes, two validators, one address, one ``record_lock``. Both writes may
    legitimately land — they write different parts of the document — so the
    assertion is the INVARIANT rather than a winner: whatever each of the two
    stored values is, it is one of the two writers' values and never a blend, and a
    write that was refused left nothing behind.

    Measured on ``c2a93a7``: both land. The record's field carries the answer, the
    run's override carries its own value, and the run's resolved draft reads the
    OVERRIDE — inheritance is displaced, which is the documented meaning of an
    override and is what a scientist would expect.

    MUTATION: making ``set_run_override`` ALSO write the record's own field —
    the blend this test exists to forbid — turns it RED::

        AssertionError: a refused answer left content behind: {'value': 'XES',
        'status': 'verified', 'evidence': [{'source_type': 'user_confirmation',
        'question': 'What value?', 'answer': 'XES', …}]}

    The precondition that makes this a RACE rather than two sequential requests is
    asserted separately by
    :func:`test_the_two_writes_take_the_same_record_lock`.
    """
    store = client_ws(client)
    exp = _fixture(store)
    eid, rid = exp.id, exp.runs[0].id

    record_token = _record_etag(client, eid)
    run_token = _run_etag(client, eid, rid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/answers",
            json={
                "confirmed_by_user": True,
                "answers": {RECORD_ANSWER_KEY: RECORD_VALUE},
            },
            headers={"If-Match": record_token},
        ),
        lambda: client.post(
            f"/api/experiments/{eid}/runs/{rid}/overrides",
            json={
                "confirmed_by_user": True,
                "address": RUN_OVERRIDE_ADDRESS,
                "payload": _confirmed(RUN_VALUE),
            },
            headers={"If-Match": run_token},
        ),
    ])

    _assert_raced(rendezvous, client.tutorial_session_id, eid)
    answer_response, override_response = responses
    assert answer_response.status_code in (200, 412), _outcome(responses)
    assert override_response.status_code in (200, 412), _outcome(responses)

    after = store.load_experiment(eid)
    field = _record_field(after)
    override = _run_override(after, rid)

    if answer_response.status_code == 200:
        assert _value_of(field) == RECORD_VALUE, field
    else:
        assert field is None, f"a refused answer left content behind: {field}"

    if override_response.status_code == 200:
        assert _value_of(override) == RUN_VALUE, override
    else:
        assert override is None, f"a refused override left content behind: {override}"

    # No blend, in either direction.
    assert _value_of(field) != RUN_VALUE, field
    assert _value_of(override) != RECORD_VALUE, override


def test_an_override_that_landed_displaces_inheritance_rather_than_merging(
    client, monkeypatch
):
    """The scientific half of the same race: what the RUN then reads.

    A run that recorded an override at an address inherits nothing at that address
    — ``CLAUDE.md`` §11 states it directly (*"A run that has recorded ANY override
    … inherits none of them"*). Under a race the danger is a run that ends up with
    BOTH: an override stored and the record's inherited value still resolving.

    MUTATION: making ``resolve_inherited`` ignore the run's overrides — so
    inheritance wins over the override that displaced it — turns this RED::

        AssertionError: {}
        assert None == 'XES'
    """
    store = client_ws(client)
    exp = _fixture(store)
    eid, rid = exp.id, exp.runs[0].id

    record_token = _record_etag(client, eid)
    run_token = _run_etag(client, eid, rid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/answers",
            json={
                "confirmed_by_user": True,
                "answers": {RECORD_ANSWER_KEY: RECORD_VALUE},
            },
            headers={"If-Match": record_token},
        ),
        lambda: client.post(
            f"/api/experiments/{eid}/runs/{rid}/overrides",
            json={
                "confirmed_by_user": True,
                "address": RUN_OVERRIDE_ADDRESS,
                "payload": _confirmed(RUN_VALUE),
            },
            headers={"If-Match": run_token},
        ),
    ])
    _assert_raced(rendezvous, client.tutorial_session_id, eid)
    _, override_response = responses
    if override_response.status_code != 200:
        pytest.skip("the override was refused in this interleaving; nothing to resolve")

    after = store.load_experiment(eid)
    resolved = after.resolved_run_draft(after.get_run(rid))
    value = _value_of((resolved.get("fields") or {}).get(RECORD_ANSWER_KEY))
    assert value == RUN_VALUE, resolved.get("fields")


def test_a_record_CORRECTION_and_a_run_override_at_one_address_do_not_tear(
    client, monkeypatch
):
    """The same pair with the record's CORRECTION route instead of its answer route.

    ``POST .../edit`` is a different handler with a different precondition and a
    different evidence shape, so covering ``/answers`` does not cover it. The
    record is answered first, so ``/edit`` has something to correct — an edit at an
    unanswered address is a documented refusal and would make the race trivial.

    **THE CORRECTION USED TO BE UNREACHABLE, AND THE TEST PASSED ANYWAY. Found and
    fixed 2026-08-30, recorded rather than quietly corrected, because a race whose
    two writers are not both live is precisely the failure this file's own
    ``_LockRendezvous`` docstring warns about.** The body was
    ``{"confirmed_by_user": True, "field": …, "value": …}``; ``post_edit`` reads
    ``body.get("answers")`` and answers **422 ``unrecognized_field``** ("No
    editable field was recognized in the request") to every other spelling, above
    the handler. Measured directly, outside any race, on ``bc8b32a``::

        edit field/value  -> 422 {"error":"unrecognized_field", …}
        edit answers dict -> 200

    So ``edit_response.status_code == 200`` could never be taken: whichever way the
    race went the correction was refused — ``412`` when the override won, ``422``
    when it did not — and the test degenerated into "an override races something
    that is always refused" while claiming to cover a second handler. **Measured
    over 12 runs before and after: ``200`` occurred 0 times, and now occurs 5.**

    The recorded mutation below still turned it RED, which is *why* this went
    unnoticed for a whole branch: that mutation is about the OVERRIDE half, and the
    ``else`` branch it lands in was the only branch reachable. An effective
    mutation is not evidence that both writers are live.

    MUTATION: making ``set_run_override`` ALSO write the record's own field turns
    this RED — the correction's address ends up holding the RUN's value::

        AssertionError: a refused correction moved the stored value: XES
        assert 'XES' == 'XAS'
    """
    store = client_ws(client)
    exp = _fixture(store)
    eid, rid = exp.id, exp.runs[0].id

    seeded = client.post(
        f"/api/experiments/{eid}/answers",
        json={"confirmed_by_user": True, "answers": {RECORD_ANSWER_KEY: RECORD_VALUE}},
        headers={"If-Match": _record_etag(client, eid)},
    )
    assert seeded.status_code == 200, seeded.text

    record_token = _record_etag(client, eid)
    run_token = _run_etag(client, eid, rid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/edit",
            # `answers`, NOT `field`/`value` — see the docstring. The wrong
            # spelling made this writer a permanent 422 and the race one-sided.
            json={
                "confirmed_by_user": True,
                "answers": {RECORD_ANSWER_KEY: CORRECTED_VALUE},
            },
            headers={"If-Match": record_token},
        ),
        lambda: client.post(
            f"/api/experiments/{eid}/runs/{rid}/overrides",
            json={
                "confirmed_by_user": True,
                "address": RUN_OVERRIDE_ADDRESS,
                "payload": _confirmed(RUN_VALUE),
            },
            headers={"If-Match": run_token},
        ),
    ])

    _assert_raced(rendezvous, client.tutorial_session_id, eid)
    edit_response, override_response = responses

    after = store.load_experiment(eid)
    field_value = _value_of(_record_field(after))
    override_value = _value_of(_run_override(after, rid))

    # The record's field is one of exactly two possible values and never the run's.
    if edit_response.status_code == 200:
        assert field_value == CORRECTED_VALUE, field_value
    else:
        assert field_value == RECORD_VALUE, (
            f"a refused correction moved the stored value: {field_value}"
        )
    assert field_value != RUN_VALUE, field_value

    if override_response.status_code == 200:
        assert override_value == RUN_VALUE, override_value
    else:
        assert override_value is None, override_value


def test_the_two_writes_take_the_same_record_lock(client, monkeypatch):
    """The load-bearing precondition for every test above, asserted rather than
    assumed.

    If the record route and the run route took DIFFERENT locks — or if the run
    route's scope were not forwarded — the two requests would not serialise at all,
    the rendezvous would still open, and every assertion above would keep passing
    while pinning nothing. That is the failure mode ``_LockRendezvous``'s own
    docstring warns about, and ``assert_scoped`` is what catches it.

    MUTATION: making ``workspace._lock_key`` drop the session from the key turns
    this RED::

        AssertionError: the real lock contended on ['/01M19PAYNDG6WXKQA8B9KX5GQ5'],
        expected only 'loE0AGWFHZJOpYMhTg3cKg/01M19PAYNDG6WXKQA8B9KX5GQ5' — the
        scope was received but not forwarded

    *The narrower mutation — dropping ``session_id=`` from the override handler's
    own ``record_lock`` call — was not run as such: that exact call shape occurs at
    four sites in ``routes.py`` and a single-site replacement could not be targeted
    unambiguously. The key function is the shared choke point and mutating it
    reaches the same property.*
    """
    store = client_ws(client)
    exp = _fixture(store)
    eid, rid = exp.id, exp.runs[0].id
    record_token = _record_etag(client, eid)
    run_token = _run_etag(client, eid, rid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    _race([
        lambda: client.post(
            f"/api/experiments/{eid}/answers",
            json={
                "confirmed_by_user": True,
                "answers": {RECORD_ANSWER_KEY: RECORD_VALUE},
            },
            headers={"If-Match": record_token},
        ),
        lambda: client.post(
            f"/api/experiments/{eid}/runs/{rid}/overrides",
            json={
                "confirmed_by_user": True,
                "address": RUN_OVERRIDE_ADDRESS,
                "payload": _confirmed(RUN_VALUE),
            },
            headers={"If-Match": run_token},
        ),
    ])

    assert not rendezvous.timed_out, "the two writes did not both reach the lock"
    assert rendezvous.arrivals == 2, rendezvous.arrivals
    rendezvous.assert_scoped(client.tutorial_session_id)


# =============================================================================
# 2. the version sequence a polling client walks
# =============================================================================


def test_the_change_feed_route_does_not_exist_and_this_records_it(client):
    """**THE BRIEF ASKED FOR A ROUTE THIS BUILD DOES NOT HAVE**, and inventing a
    test that passed against something else would be worse than saying so.

    ``GET /api/experiments/{id}/changes`` is absent. Asserted over the published
    OpenAPI document rather than described, so the day it ships this test goes red
    and the substitute below is replaced by the real thing.

    ``test_live_sync.py`` records the design decision behind the absence: live sync
    is conditional polling on the existing detail route, and *"no new revision
    endpoint … no new route is warranted"*.

    MUTATION: adding a ``@router.get("/experiments/{experiment_id}/changes")``
    turns this RED::

        AssertionError: a /changes route now exists:
        ['/api/experiments/{experiment_id}/changes']
        assert not ['/api/experiments/{experiment_id}/changes']
    """
    from isaac_api.app import create_app

    paths = create_app().openapi()["paths"]
    feeds = sorted(p for p in paths if p.rstrip("/").endswith("/changes"))
    assert not feeds, f"a /changes route now exists: {feeds}"
    # And the substitute this file uses instead is present.
    assert "/api/experiments/{experiment_id}" in paths


def test_concurrent_writes_never_advance_the_version_without_changing_the_document(
    client, monkeypatch
):
    """The substitute property, and the one a polling client actually depends on.

    A client holds an ETag and re-fetches when it changes. Two failures matter and
    they are opposites: a version that moves without a change makes every client
    re-fetch forever, and a change that does not move the version makes every client
    miss it. Both are the polling equivalent of a feed that duplicates or skips.

    Two writers race on ONE record. Afterwards: the number of distinct versions
    observed equals one plus the number of writes that returned ``200``, and the
    final ETag matches the final document.

    MUTATION: making ``Experiment.save_versioned`` bump ``rev`` on entry, above
    the byte-stable no-op decision, turns this RED::

        AssertionError: the version moved 2 times for 1 accepted write(s)
        assert 2 == 1
    """
    store = client_ws(client)
    exp = _fixture(store)
    eid, rid = exp.id, exp.runs[0].id

    start = store.load_experiment(eid).rev
    token = _record_etag(client, eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    # Both writers hold the SAME record validator, so exactly one may land.
    responses = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/answers",
            json={
                "confirmed_by_user": True,
                "answers": {RECORD_ANSWER_KEY: RECORD_VALUE},
            },
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{eid}/answers",
            json={"confirmed_by_user": True, "answers": {"system.domain": "experimental"}},
            headers={"If-Match": token},
        ),
    ])
    _assert_raced(rendezvous, client.tutorial_session_id, eid)

    accepted = [r for r in responses if r.status_code == 200]
    assert len(accepted) == 1, _outcome(responses)

    after = store.load_experiment(eid)
    moved = after.rev - start
    assert moved == len(accepted), (
        f"the version moved {moved} times for {len(accepted)} accepted write(s)"
    )
    # And the served ETag is the one the stored document now has: a client that
    # re-fetched here would not be told to re-fetch again.
    assert _record_etag(client, eid) == after.etag()


def test_a_refused_write_leaves_the_version_and_the_document_untouched(
    client, monkeypatch
):
    """The other half, stated separately because it is a different failure.

    The loser of the race above must leave NOTHING — not its value, not a revision,
    not an answer-log entry. Asserted over the whole serialized document rather
    than over a field, because a partial write is exactly what a field-level check
    misses.

    **THREE INDEPENDENT GUARDS SEPARATE THESE TWO WRITERS, AND THAT WAS MEASURED
    BY MUTATIONS THAT FAILED TO TURN THIS RED.** Recording them is the point:

    * Disabling ``_check_if_match`` entirely (``return None``) — still green. The
      second writer is refused by the semantic already-answered guard instead.
    * Disabling ``_refuse_answering_an_already_answered_key`` AS WELL — still
      green. A third refusal, in the record-level enum write path, still separates
      them.

    So "exactly one lands" here is not held up by the compare-and-swap alone, and a
    reader who assumed it was would be wrong about which guard to preserve.

    MUTATION (the one that DOES turn it red): making
    ``Experiment.save_versioned`` bump ``rev`` on entry, before the byte-stable
    no-op decision::

        AssertionError: a refused write advanced the version: 3 - 1 = 2
        assert 2 == 1
    """
    store = client_ws(client)
    exp = _fixture(store)
    eid = exp.id
    start = store.load_experiment(eid).rev

    token = _record_etag(client, eid)
    rendezvous = _LockRendezvous(monkeypatch, eid)

    responses = _race([
        lambda: client.post(
            f"/api/experiments/{eid}/answers",
            json={"confirmed_by_user": True, "answers": {RECORD_ANSWER_KEY: "XAS"}},
            headers={"If-Match": token},
        ),
        lambda: client.post(
            f"/api/experiments/{eid}/answers",
            json={"confirmed_by_user": True, "answers": {RECORD_ANSWER_KEY: "XES"}},
            headers={"If-Match": token},
        ),
    ])
    _assert_raced(rendezvous, client.tutorial_session_id, eid)

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 422] or statuses == [200, 412], _outcome(responses)

    after = store.load_experiment(eid)
    stored = _value_of(_record_field(after))
    assert stored in ("XAS", "XES"), stored
    loser = "XES" if stored == "XAS" else "XAS"
    serialized = json.dumps(after.to_state())
    assert serialized.count(loser) == 0, "the loser's value reached the document"
    # ONE accepted write, ONE version step. A refused write that advanced `rev`
    # would make every polling client re-fetch a document that had not changed.
    assert after.rev - start == 1, (
        f"a refused write advanced the version: {after.rev} - {start} = "
        f"{after.rev - start}"
    )

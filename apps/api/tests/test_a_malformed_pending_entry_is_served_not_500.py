"""A stored blocker that is not a question is SERVED, said to be unreadable, and counted.

WHY THIS FILE EXISTS. ``test_a_malformed_pending_list_is_still_readable.py`` closed the
non-iterable ``pending`` CONTAINER and named, at its own bottom, exactly what it did not
close: ``serialize.pending_to_list`` calls ``entry.get("kind")``, so a well-formed list
holding a non-question ENTRY still failed the whole request. Measured over HTTP on
``1ad1f8f`` — ``TestClient(create_app(), raise_server_exceptions=False)``, so these are
the statuses a real client saw — with the value written into the persisted state:

===========================================  ==========  =========  =========
stored ``draft["pending"]``                  GET         GET        POST
                                             /pending    ?limit=5   /assistant/query
===========================================  ==========  =========  =========
``[7]``                                      **500**     **500**    **500**
``7``                                        **500**     **500**    **500**
``[{"kind": "qc", ...}, 7]``                 **500**     **500**    **500**
``["a string"]``                             **500**     **500**    **500**
``[None]``                                   **500**     **500**    **500**
===========================================  ==========  =========  =========

Every row is **200** after this change, at both levels (record draft and run draft) —
that is 10 measured cases, and the assistant column matters because it is a SECOND
route serialising the same list, which a fix scoped to the pending route would have left
broken.

``7`` and ``[7]`` reach the identical failure because ``workspace._blocker_entries``
turns the non-iterable into ``[7]``; the sibling file asserts the two behave IDENTICALLY
and that equality is preserved here rather than merely still passing.

THE DESIGN IS ``serialize.py``'S OWN, NOT A NEW ONE. That module already answers a
per-item degradation with ``unavailable`` + ``unavailable_reason`` on a served entry,
under a rule it states out loud: an entry whose stored content cannot be read is still
SERVED, carries whatever about it IS readable, and says so — nothing is invented for it,
and a bundle-level failure is a different question. An unreadable blocker is exactly
that shape one module over. The rejected alternatives are argued in
``serialize._unreadable_blocker``; the two that matter here are DROPPING it (which would
make the served list disagree with ``pending_count``, and would let a record whose only
blocker is unreadable read as finished) and a TYPED ERROR on the read (which hides the
record from an owner who did nothing wrong).

WHAT THIS FILE ALSO PINS, because it is where the HTTP symptom lives: the sibling
per-ITEM defect in ``draft_validator`` (``{"assets": [7]}``), whose unit-level fix lives
in ``tests/test_malformed_draft_containers_are_reported_not_raised.py`` and whose 500 was
never pinned at the route layer at all.

AND WHAT IS DELIBERATELY NOT FIXED, pinned at the bottom so the residue is visible
rather than implied: two WRITE-path refusals that are still HTTP 500. See
``test_a_malformed_block_evidence_container_REFUSES_the_write`` and
``test_the_ROUTE_LAYER_still_fails_a_write_on_a_non_iterable_pending`` for the
measurements and for why each was decided the way it was.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from isaac_api import serialize
from isaac_api import workspace as ws

#: The stored shapes under test. Each is TRUTHY or explicitly ``None`` — a falsy
#: ``pending`` container keeps its long-standing ``or []`` normalisation, which is the
#: sibling file's territory and is untouched.
MALFORMED_ENTRIES: tuple[object, ...] = (7, "a string", None, True, 1.5, ["nested"])

#: A well-formed blocker to sit beside the junk one, so per-item isolation is measured
#: rather than assumed. `qc` because it is answerable through the route with no worked
#: example (`test_qc_answerable.py`).
GOOD_QC = {
    "kind": "qc",
    "question": "What is the QC verdict for this measurement?",
    "blocker": "measurement.qc.status",
}


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    """A NORMAL-scope client — not the tutorial fixture. This is about a record the
    product itself creates; the worked-example scope refuses persistence."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _create(client: TestClient) -> str:
    resp = client.post("/api/experiments", json={"title": "malformed pending entry"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _add_run(client: TestClient, exp_id: str) -> str:
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    resp = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "Run 1"},
        headers={"If-Match": f'"{version}"'},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["run"]["id"]


def _persist(exp_id: str, value: object, *, on_run: bool = False, key: str = "pending") -> None:
    """Write the malformed value the way it can actually come to exist.

    NO SHIPPED WRITE PATH PRODUCES IT — the sibling file's ``_persist_malformed``
    docstring enumerates the producers (``complete.apply_answers`` assigns a list it
    built itself, ``routes._seed_for_new_run`` deep-copies template entries,
    ``blank_draft`` is literals). The reachable routes are an operator editing the
    persisted state — the workspace JSON, or the ``isaac_experiments.state`` JSONB — and
    any future importer or migration. Editing the store directly is an honest
    reproduction of that, not a shortcut around a route that would refuse it.
    """
    exp = ws.load_experiment(exp_id)
    assert exp is not None
    target = exp.runs[0].draft if on_run else exp.draft
    target[key] = value
    exp.save()


def _etag(client: TestClient, exp_id: str) -> str:
    return f'"{client.get(f"/api/experiments/{exp_id}").json()["version"]}"'


# --- the read is answered ------------------------------------------------------


@pytest.mark.parametrize("bad", MALFORMED_ENTRIES, ids=[repr(b) for b in MALFORMED_ENTRIES])
@pytest.mark.parametrize("on_run", [False, True], ids=["record-level", "run-level"])
def test_the_question_list_is_answered_for_every_malformed_entry_shape(
    client: TestClient, bad, on_run: bool
):
    """Each of these was **500** on ``1ad1f8f``, bounded and unbounded alike."""
    exp_id = _create(client)
    if on_run:
        _add_run(client, exp_id)
    _persist(exp_id, [GOOD_QC, bad], on_run=on_run)

    assert client.get(f"/api/experiments/{exp_id}/pending").status_code == 200
    assert client.get(f"/api/experiments/{exp_id}/pending?limit=5").status_code == 200
    # THE SECOND ROUTE THAT SERIALISES THE SAME LIST. A fix scoped to the pending route
    # would have left this one at 500 with nothing failing.
    assert (
        client.post(
            f"/api/experiments/{exp_id}/assistant/query",
            json={"question": "what is pending?"},
        ).status_code
        == 200
    )


def test_the_bare_and_the_wrapped_non_iterable_still_behave_IDENTICALLY(client: TestClient):
    """THE SIBLING FILE'S CLAIM, RE-MEASURED AFTER THE CONVERGENCE MOVED.

    ``test_the_non_iterable_case_now_behaves_EXACTLY_like_the_malformed_entry_case``
    asserts the equality and says so: "if the shared behaviour is later fixed — it will
    still pass, and it will still be pinning the thing this change actually did." This is
    that later fix, so the equality is asserted again HERE with the statuses written out,
    which is what stops "they agree" from quietly becoming "they agree, at 500".
    """
    statuses = {}
    for label, value in (("wrapped", [7]), ("bare", 7)):
        exp_id = _create(client)
        _persist(exp_id, value)
        statuses[label] = {
            "detail": client.get(f"/api/experiments/{exp_id}").status_code,
            "list": client.get("/api/experiments").status_code,
            "pending": client.get(f"/api/experiments/{exp_id}/pending").status_code,
        }
    assert statuses["bare"] == statuses["wrapped"], statuses
    assert statuses["bare"] == {"detail": 200, "list": 200, "pending": 200}, statuses


# --- what is served, exactly ---------------------------------------------------


def test_the_entry_is_served_and_names_the_shape_that_was_found(client: TestClient):
    exp_id = _create(client)
    _persist(exp_id, [7])

    body = client.get(f"/api/experiments/{exp_id}/pending").json()
    assert len(body["pending"]) == 1, body
    entry = body["pending"][0]
    assert entry["unavailable"] is True, entry
    assert "a number" in entry["unavailable_reason"], entry
    assert "not a question" in entry["unavailable_reason"], entry


def test_nothing_IS_INVENTED_FOR_IT(client: TestClient):
    """``CLAUDE.md`` §5, asserted key by key rather than described.

    A fabricated ``id`` or ``blocker_key`` would be the worst of these: ``id`` is the key
    an answer is submitted under and ``blocker_key`` is the identity a client stages
    input against, so a made-up one invites a write that can never land.
    """
    exp_id = _create(client)
    _persist(exp_id, ["a string"])

    entry = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"][0]
    for key in (
        "id",
        "kind",
        "question",
        "about",
        "demo_answer",
        "inferability",
        "run_id",
        "run_label",
        "blocker_key",
    ):
        assert entry[key] is None, (key, entry)
    # EVERY KEY IS PRESENT, none omitted: a consumer reading `entry["kind"]` must get
    # `None`, not a KeyError, so the served key set does not depend on readability.
    assert set(entry) == {
        "id",
        "kind",
        "question",
        "about",
        "demo_answer",
        "inferability",
        "run_id",
        "run_label",
        "blocker_key",
        "unavailable",
        "unavailable_reason",
    }, sorted(entry)


def test_the_stored_value_is_never_echoed_back(client: TestClient):
    """The reader is told WHAT SHAPE was found, never handed the content.

    ``serialize._JSON_KIND`` and ``draft_validator``'s container findings took this
    decision for the same reason: a stored string interpolated into a message is
    arbitrary content rendered as though it were the server's own words.
    """
    secret = "SENSITIVE-VALUE-THAT-MUST-NOT-BE-ECHOED"
    exp_id = _create(client)
    _persist(exp_id, [secret])

    text = client.get(f"/api/experiments/{exp_id}/pending").text
    assert secret not in text, text


def test_the_readable_questions_beside_it_are_still_served(client: TestClient):
    """PER-ITEM ISOLATION. One junk entry must not cost the reader the real questions —
    which is precisely what the 500 did."""
    exp_id = _create(client)
    _persist(exp_id, [GOOD_QC, 7, {**GOOD_QC, "kind": "series", "question": "Spectrum?"}])

    served = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert [e.get("kind") for e in served] == ["qc", None, "series"], served
    assert [e.get("unavailable") for e in served] == [None, True, None], served


def test_a_run_tag_survives_when_it_IS_readable(client: TestClient):
    """WHATEVER IS READABLE IS KEPT — the rule ``serialize.py`` already states for the
    evidence trail ("carries its own identity and whatever else about it IS readable").

    A mapping entry whose ``kind`` is unhashable cannot be read as a question, but its
    ``run_id`` can be, and that is the one fact that makes the document fixable: it names
    WHICH run holds the junk entry. Passing through a tag that is really there is not
    inventing one — and a NON-mapping entry, which has no readable anything, gets
    nothing.
    """
    exp_id = _create(client)
    run_id = _add_run(client, exp_id)
    _persist(
        exp_id,
        [{"kind": {}, "run_id": run_id, "run_label": "Run 1"}, 7],
        on_run=True,
    )

    served = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    unreadable = [e for e in served if e.get("unavailable")]
    assert len(unreadable) == 2, served
    assert unreadable[0]["run_id"] == run_id, unreadable[0]
    assert unreadable[0]["run_label"] == "Run 1", unreadable[0]
    assert unreadable[1]["run_id"] is None, unreadable[1]


def test_a_MAPPING_entry_that_raises_is_also_served(client: TestClient):
    """AN ``isinstance`` GUARD ALONE WOULD HAVE LEFT THREE SHAPES AT 500, and every test
    naming the defect would still have passed. Measured in-process on ``1ad1f8f``:

    * ``{"kind": {}}`` and ``{"kind": []}`` raise ``TypeError: unhashable type`` out of
      ``inferability._BLOCKER_REFUSALS.get(kind)`` — in EVERY scope;
    * ``{"kind": "asset", "uri": []}`` raises the same out of the example-answer lookup,
      in EXAMPLE SCOPE ONLY, which is why the scope is exercised here directly rather
      than only through a route.

    **THE FIRST TWO NOW TAKE AN EARLIER BRANCH, AND THE REASON THEY CARRY IS BETTER, SO
    THE ASSERTION IS NARROWED RATHER THAN DROPPED.** ``pending_to_list`` refuses an
    entry whose ``kind`` is not a string BEFORE reading it, because the answer key IS
    the kind and there is no key to submit an answer under — so ``{"kind": {}}`` is
    reported as naming its kind as an object rather than as an unexplained
    ``TypeError``. What this test exists to prove is UNCHANGED and still asserted: none
    of the three is a 500, all three are served ``unavailable``, and the third — the
    scope-dependent one — still proves the ``except`` branch is not dead, which is the
    whole reason ``_ITEM_SHAPE_ERRORS`` exists.
    """
    exp_id = _create(client)
    _persist(exp_id, [{"kind": {}}, {"kind": ["a", "list"]}])
    served = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert [e["unavailable"] for e in served] == [True, True], served
    assert all(
        "names its kind as an object" in e["unavailable_reason"]
        or "names its kind as a list" in e["unavailable_reason"]
        for e in served
    ), served
    # AND THE CONSEQUENCE, which is what the reason is FOR: no answer key is minted.
    assert all(e["id"] is None and e["blocker_key"] is None for e in served), served

    # THE SCOPE-DEPENDENT ONE. `example_scope` is what reaches the fixture lookup, so
    # this shape is readable outside the walkthrough scope and unreadable inside it —
    # honest in both, because the failure really is scope-dependent.
    entry = {"kind": "asset", "uri": ["not", "hashable"], "question": "sha256?"}
    demo = ws.load_demo_answers()
    outside = serialize.pending_to_list({"pending": [entry]}, demo, example_scope=False)
    inside = serialize.pending_to_list({"pending": [entry]}, demo, example_scope=True)
    assert outside["pending"][0].get("unavailable") is None, outside
    assert inside["pending"][0]["unavailable"] is True, inside


def test_a_programming_error_in_the_refusal_TABLE_is_not_reported_as_a_bad_document(
    monkeypatch,
):
    """``inferability.UnsupportedSuggestion`` is deliberately NOT caught.

    It is raised when the refusal table declares a state no blocker may have — a defect
    in this repository's own code. Reporting it to a scientist as "your stored question
    is malformed" would be a false statement about their record, which is the same
    reasoning ``_ITEM_SHAPE_ERRORS``' own note gives for staying narrow.
    """
    from isaac_api import inferability

    def boom(entry, *, example_available=False):
        raise inferability.UnsupportedSuggestion("the table is wrong")

    monkeypatch.setattr(serialize.inferability, "blocker_inferability", boom)
    with pytest.raises(inferability.UnsupportedSuggestion):
        serialize.pending_to_list({"pending": [GOOD_QC]}, {}, example_scope=False)


# --- it stays counted, and the record stays refused ---------------------------


def test_it_is_counted_and_the_record_is_not_reported_as_finished(client: TestClient):
    """THE REJECTED-ALTERNATIVE GUARD. Dropping the entry would pass every test above
    and would report a record nobody can finish as needing nothing."""
    exp_id = _create(client)
    _persist(exp_id, [7])

    detail = client.get(f"/api/experiments/{exp_id}").json()
    served = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert len(served) == 1, served
    assert detail["pending_count"] == len(served) == 1, (detail["pending_count"], served)
    assert detail["status"] == "needs_attention", detail

    exp = ws.load_experiment(exp_id)
    assert exp is not None
    assert exp.export_ready() is False
    assert exp.pending_count() == len(exp.pending())


def test_the_document_is_not_repaired_by_being_read(client: TestClient):
    """NO SILENT COERCION. Several reads later the stored value is byte-identical."""
    exp_id = _create(client)
    stored = [GOOD_QC, 7, "a string"]
    _persist(exp_id, copy.deepcopy(stored))

    for _ in range(3):
        assert client.get(f"/api/experiments/{exp_id}/pending").status_code == 200
        assert client.get(f"/api/experiments/{exp_id}").status_code == 200

    exp = ws.load_experiment(exp_id)
    assert exp is not None
    assert exp.draft["pending"] == stored, exp.draft["pending"]


# --- the write path: a junk entry no longer blocks every other answer ---------


def test_a_junk_entry_no_longer_makes_every_OTHER_question_unanswerable(client: TestClient):
    """Measured on ``1ad1f8f``: **500** from ``complete.apply_answers``
    (``AttributeError: 'int' object has no attribute 'get'``) when a valid ``qc`` answer
    was submitted against ``pending = [<good qc blocker>, 7]``. One junk entry made the
    whole record unanswerable.

    The junk entry is KEPT, verbatim and unanswered — the same answer the loop's own
    ``Unknown blocker kind`` branch already gives — so nothing is dropped, nothing is
    repaired, and the record stays refused.
    """
    exp_id = _create(client)
    _persist(exp_id, [GOOD_QC, 7])

    resp = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "valid", "evidence": "the spectrum is clean"}},
        },
        headers={"If-Match": _etag(client, exp_id)},
    )
    assert resp.status_code == 200, resp.text

    exp = ws.load_experiment(exp_id)
    assert exp is not None
    assert exp.draft["pending"] == [7], exp.draft["pending"]
    assert exp.draft["qc"]["status"] == "valid", exp.draft.get("qc")
    # STILL REFUSED, and that is the truthful outcome: a blocker nobody can read is a
    # blocker.
    assert exp.export_ready() is False


def test_the_edge_confirmation_survives_a_junk_implicit_item(client: TestClient):
    """``routes._edge_derivations_in`` gates this write with ``isinstance(entry, dict)
    and entry.get("about") == "edge"`` and its docstring calls that predicate
    "``complete.apply_answers``'s OWN" — while the two writers did not have the
    isinstance half. Measured on ``1ad1f8f`` with ``implicit = [7, <edge derivation>]``
    and ``{"edge": "L3"}``: ``POST /answers`` **500** and ``POST /edit`` **500**, one in
    each writer.
    """
    edge_entry = {
        "about": "edge",
        "value": None,
        "status": "needs_confirmation",
        "evidence": [
            {"source_type": "derivation", "rule": "absorbing element implies edge"}
        ],
    }
    for path, expected_value in (("answers", "L3"), ("edit", "L3")):
        exp_id = _create(client)
        _persist(exp_id, [7, copy.deepcopy(edge_entry)], key="implicit")
        resp = client.post(
            f"/api/experiments/{exp_id}/{path}",
            json={"confirmed_by_user": True, "answers": {"edge": expected_value}},
            headers={"If-Match": _etag(client, exp_id)},
        )
        assert resp.status_code == 200, (path, resp.text)
        exp = ws.load_experiment(exp_id)
        assert exp is not None
        implicit = exp.draft["implicit"]
        # The junk item is still there, untouched, and the edge landed on the entry that
        # carries the derivation.
        assert implicit[0] == 7, implicit
        assert implicit[1]["value"] == expected_value, implicit


# --- the sibling per-ITEM validator defect, at the route layer ----------------


@pytest.mark.parametrize(
    "name",
    ["assets", "descriptors_outputs", "implicit", "series", "links"],
)
def test_a_wrong_typed_ITEM_in_a_draft_container_does_not_500_the_read(
    client: TestClient, name: str
):
    """Measured on ``1ad1f8f``: **500** from ``GET /api/experiments/{id}``, because
    ``Experiment.draft_ok`` reaches ``validate_draft`` and the walk hit ``.get`` on the
    item. The unit-level fix and its rejected alternatives live in
    ``tests/test_malformed_draft_containers_are_reported_not_raised.py``; the HTTP
    symptom is pinned here because that is what a scientist reports, and because a
    route-layer change could otherwise re-open it with nothing failing.
    """
    exp_id = _create(client)
    _persist(exp_id, [7], key=name)

    assert client.get(f"/api/experiments/{exp_id}").status_code == 200
    assert client.get("/api/experiments").status_code == 200

    exp = ws.load_experiment(exp_id)
    assert exp is not None
    # AND THE RECORD IS STILL REFUSED, naming the item. Swallowing the wrong type would
    # return 200 with the export gate open on a document that could not be read.
    assert exp.draft_ok() is False
    from isaac_records.draft_validator import validate_draft

    assert any(where == f"{name}[0]" for where, _ in validate_draft(exp.draft).errors)


def test_the_run_override_PROBE_still_refuses_a_malformed_request_with_422(
    client: TestClient,
):
    """THE BOUNDARY THE ITEM GUARD MUST NOT CROSS, asserted through the route.

    ``routes._refuse_override_payload`` probes a client's override payload through
    ``validate_draft`` and catches ``_PROBE_STRUCTURAL_ERRORS`` to answer a typed 422 —
    the honest answer for a malformed REQUEST, which the caller can fix. Its measured
    cases are nested inside a top-level DICT container, and the only overridable
    addresses are ``field:<path>``, ``block:attribution`` and ``block:tags``, so no probe
    draft can name one of the five LIST containers the item guard covers. That is why
    the guard cannot make this branch dead — and it is checked rather than argued.
    """
    exp_id = _create(client)
    run_id = _add_run(client, exp_id)
    etag = client.get(f"/api/experiments/{exp_id}/runs/{run_id}").headers["ETag"]
    resp = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/overrides",
        json={
            "address": "block:attribution",
            "payload": {"contributors": ["not-a-dict"]},
            "confirmed_by_user": True,
        },
        headers={"If-Match": etag},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"] == "invalid_block_payload", resp.text


# --- THE RESIDUE: two write-path refusals that are still 500 -----------------


def test_a_malformed_block_evidence_container_REFUSES_the_write(client: TestClient):
    """FOUND, DECIDED, AND DELIBERATELY NOT "FIXED" — the decision is refusal.

    Measured over HTTP on ``1ad1f8f`` AND at this commit, with a valid ``qc`` answer
    submitted against a record whose stored ``block_evidence`` is not an object::

        block_evidence = 7                 POST /answers -> 500
        block_evidence = "operator text"   POST /answers -> 500
        block_evidence = []                POST /answers -> 500

    (``[]`` is falsy and still fails: ``draft.setdefault("block_evidence", {})`` returns
    the stored list because the KEY EXISTS, and a list has no ``setdefault``.)

    WHY THE WRITE IS NOT MADE TO SUCCEED, which is a different question from the read.
    Applying this answer means appending a ``user_confirmation`` to ``block_evidence``,
    and there is nowhere to append it. The three available outcomes are: store the
    verdict WITHOUT its confirmation, which writes a value with no evidence and is what
    ``CLAUDE.md`` §5 exists to forbid; REPLACE the stored container, which destroys
    whatever an operator wrote there; or REFUSE. Refusal is the only one that neither
    invents nor deletes, and a read has no equivalent third option — refusing a read
    takes the owner's record away, which is why the read degrades and the write does not.

    WHY THE REFUSAL IS STILL AN UNTYPED 500, stated rather than excused. A typed refusal
    is the better surface and it is a ROUTE-layer change: the truth core cannot produce
    an HTTP status, and raising a new exception type that nothing catches would leave the
    response byte-identical while adding public surface with no reader. That is a
    separate slice with its own review, and it is named in this slice's report rather
    than done quietly here.

    WHAT IS ALREADY SAFE, and is the half worth pinning: the write is refused
    ATOMICALLY. ``apply_answers`` deep-copies first and the route assigns only on
    success, so nothing is half-written — asserted below, because "it refuses" and "it
    refuses without damaging the document" are different claims.
    """
    for stored in (7, "operator text", []):
        exp_id = _create(client)
        _persist(exp_id, [GOOD_QC])
        _persist(exp_id, copy.deepcopy(stored), key="block_evidence")
        before = client.get(f"/api/experiments/{exp_id}").json()

        resp = client.post(
            f"/api/experiments/{exp_id}/answers",
            json={
                "confirmed_by_user": True,
                "answers": {"qc": {"status": "valid", "evidence": "clean"}},
            },
            headers={"If-Match": f'"{before["version"]}"'},
        )
        assert resp.status_code == 500, (stored, resp.status_code)

        after = client.get(f"/api/experiments/{exp_id}").json()
        assert after["version"] == before["version"], (stored, after["version"])
        assert after["rev"] == before["rev"], (stored, after["rev"])
        exp = ws.load_experiment(exp_id)
        assert exp is not None
        assert exp.draft["block_evidence"] == stored, exp.draft["block_evidence"]
        assert exp.draft["pending"] == [GOOD_QC], exp.draft["pending"]
        assert "qc" not in exp.draft or not exp.draft["qc"], exp.draft.get("qc")


def test_the_ROUTE_LAYER_still_fails_a_write_on_a_non_iterable_pending(client: TestClient):
    """FOUND AND OUT OF THIS SLICE'S SCOPE — recorded so it is not mistaken for covered.

    ``routes._answer_asset_uris`` reads ``draft.get("pending") or []`` and iterates it
    directly rather than through ``workspace._blocker_entries``, so a NON-ITERABLE
    ``pending`` — the shape the sibling slice fixed on every read path — still raises
    ``TypeError: 'int' object is not iterable`` on a WRITE. Measured over HTTP on
    ``1ad1f8f`` and at this commit: ``pending = 7`` plus any answer body ->
    ``POST /answers`` **500**, at ``routes.py`` in ``_answer_asset_uris``.

    It is a route-layer read of the raw stored document, and ``routes.py`` is outside
    this slice's declared scope; the fix is one call to the helper that already exists
    for exactly this. Pinned here so the gap is visible, with the same instruction the
    sibling gap carried: INVERT this test when it is closed, do not delete it.

    Note what is NOT broken: every READ of the same record is 200 (asserted below), so
    this is a write-path residue rather than a reopening of the read defect.
    """
    exp_id = _create(client)
    _persist(exp_id, 7)

    assert client.get(f"/api/experiments/{exp_id}/pending").status_code == 200
    assert client.get(f"/api/experiments/{exp_id}").status_code == 200

    resp = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "valid", "evidence": "clean"}},
        },
        headers={"If-Match": _etag(client, exp_id)},
    )
    assert resp.status_code == 500, resp.status_code


# --- READ vs. ANSWERABLE: the second class of entry, and what is preserved -----
#
# ADDED CLOSING AN INDEPENDENT REVIEW'S C1. A stored ``{"question": "q?"}`` — a mapping
# with prose and NO ``kind`` — was served ``{"id": "blocker", "kind": null, "question":
# "q?"}`` with no ``unavailable`` flag at all. Two things were wrong with that, and they
# pull in opposite directions, which is why the fix separates them:
#
#   * ``"blocker"`` IS NOT AN ANSWER KEY. Measured over HTTP at ``724ce58``:
#     ``POST /answers {"answers": {"blocker": "x"}, "confirmed_by_user": true}`` ->
#     **422 ``unrecognized_field``**. So the response advertised a key the write path
#     refuses, which is the fabricated identifier ``_unreadable_blocker`` exists to
#     avoid.
#   * THE PROSE WAS REAL. The server read it. The client's predicate (which requires a
#     string ``kind``) then classed the entry unanswerable and rendered "1 stored
#     question could not be read" — over a sentence the same response was carrying.


def test_a_kindless_entry_is_marked_unanswerable_and_KEEPS_its_prose(client: TestClient):
    exp_id = _create(client)
    _persist(exp_id, [{"question": "Which detector was used?"}])

    served = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert len(served) == 1, served
    entry = served[0]

    # NO FABRICATED ANSWER KEY. This is the half the write path measures.
    assert entry["id"] is None, entry
    assert entry["blocker_key"] is None, entry
    assert entry["kind"] is None, entry
    # THE DISCRIMINATOR IS THE FIELD, and it says WHY rather than claiming a failed read.
    assert entry["unavailable"] is True, entry
    assert "names no kind" in entry["unavailable_reason"], entry
    assert "could not be read" not in entry["unavailable_reason"], entry
    # AND THE PROSE SURVIVES. This is the assertion that fails if `_unreadable_blocker`
    # goes back to nulling `question`, and the reason the client can show the scientist
    # their own question instead of a generic label.
    assert entry["question"] == "Which detector was used?", entry


def test_the_fabricated_answer_key_really_is_refused_by_the_write_path(client: TestClient):
    """The measurement the change above rests on, asserted rather than quoted."""
    exp_id = _create(client)
    _persist(exp_id, [{"question": "Which detector was used?"}])
    resp = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"confirmed_by_user": True, "answers": {"blocker": "a value"}},
        headers={"If-Match": _etag(client, exp_id)},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"] == "unrecognized_field", resp.text


@pytest.mark.parametrize(
    "question", [{"a": 1}, ["a"], 7, True], ids=["object", "list", "number", "boolean"]
)
def test_a_non_string_question_on_an_ANSWERABLE_entry_is_never_served(client: TestClient, question):
    """I8, closed at the boundary that knows what it read.

    ``{"kind": "qc", "question": {"a": 1}}`` IS answerable — measured, ``POST /answers``
    with key ``qc`` answers **200** — so the client correctly treats it as a question
    and hands ``question`` to ``<h2>{blocker.question}</h2>``. React throws "Objects are
    not valid as a React child" and, with no ErrorBoundary anywhere in the application,
    the whole page blanks: strictly worse than the HTTP 500 this family of fixes
    replaced. A non-string is dropped rather than stringified — ``str({"a": 1})`` would
    put a Python repr on a scientist's screen as if it were their own prose.
    """
    exp_id = _create(client)
    _persist(exp_id, [{"kind": "qc", "question": question, "blocker": "measurement.qc.status"}])

    entry = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"][0]
    assert entry["kind"] == "qc", entry
    assert entry["id"] == "qc", entry  # still answerable — the kind is readable
    assert entry.get("unavailable") is None, entry
    assert entry["question"] is None, entry


@pytest.mark.parametrize("locator", [{"a": 1}, ["a"], 7], ids=["object", "list", "number"])
def test_a_non_string_locator_is_never_served_either(client: TestClient, locator):
    """``about`` reaches JSX by the same route as ``question``
    (``{item.about ?? item.kind}``), and ``_blocker_about`` passed the stored
    ``uri``/``blocker`` through verbatim."""
    exp_id = _create(client)
    _persist(exp_id, [{"kind": "qc", "question": "q?", "blocker": locator}])
    entry = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"][0]
    assert entry["about"] is None, entry


@pytest.mark.parametrize("tag", [{"a": 1}, 7], ids=["object", "number"])
def test_a_non_string_run_tag_is_never_served_either(client: TestClient, tag):
    """``_unreadable_blocker`` has always normalised these two; ``_readable_blocker`` did
    not, so the two served forms disagreed about what a run tag is — and ``blocker_key``
    was built by ``str()``-ing the value into a key the response reported as null."""
    exp_id = _create(client)
    _persist(exp_id, [{"kind": "qc", "question": "q?", "run_id": tag, "run_label": tag}])
    entry = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"][0]
    assert entry["run_id"] is None, entry
    assert entry["run_label"] is None, entry
    assert entry["blocker_key"] == "qc", entry


def test_item_shape_errors_is_exactly_these_five():
    """The caught set is pinned, because it is what stands between a malformed stored
    document and an HTTP 500 — and because an independent review found it wider than the
    two types anyone has reproduced, with nothing asserting its contents.

    Two things this pins, and they pull in opposite directions on purpose:

    * NOTHING NEW ARRIVES UNEXAMINED. A sixth type — above all ``Exception`` — turns
      every programming error in this module into "your stored question is malformed",
      which is a false statement about a scientist's record.
    * NOTHING IS QUIETLY NARROWED EITHER. ``ValueError``/``KeyError``/``IndexError`` are
      unmeasured on the pending path and ordinary on the evidence-trail walkers this
      tuple is shared with; dropping one is a measurement, not a tidy-up.
    """
    assert serialize._ITEM_SHAPE_ERRORS == (
        AttributeError,
        TypeError,
        ValueError,
        KeyError,
        IndexError,
    ), serialize._ITEM_SHAPE_ERRORS
    # THE TWO THAT MUST NEVER BE IN IT.
    assert Exception not in serialize._ITEM_SHAPE_ERRORS
    assert MemoryError not in serialize._ITEM_SHAPE_ERRORS
    # AND THE ONE THAT IS DELIBERATELY OUTSIDE IT — a defect in this repository's own
    # refusal table is not a defect in the reader's document.
    from isaac_api import inferability

    assert inferability.UnsupportedSuggestion not in serialize._ITEM_SHAPE_ERRORS
    assert not issubclass(inferability.UnsupportedSuggestion, serialize._ITEM_SHAPE_ERRORS)

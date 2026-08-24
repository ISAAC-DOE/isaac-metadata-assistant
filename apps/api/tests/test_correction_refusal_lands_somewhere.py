"""A refusal that redirects must redirect somewhere that accepts the request.

THREE DEFECTS, ALL MEASURED OVER HTTP BEFORE THIS FILE EXISTED
==============================================================

**1. The documented `422` body reached no published contract.**
``grep -n "_R_NOT_YET_ANSWERED" apps/api/isaac_api/routes.py`` returned exactly ONE
line — the definition — so the constant describing the ``not_yet_answered`` refusal was
merged into no route's ``responses={...}``. Both correction operations declared a
``422``: the record's enumerated three domain refusals and omitted this one, and the
run's carried only the framework's "Validation Error". A machine client could read the
whole published contract, receive ``error: not_yet_answered``, and find it described
nowhere.

**2. The run-level refusal named the operation that is GUARANTEED to refuse it.**
``answer_at`` was the hardcoded literal ``POST /api/experiments/{experiment_id}/answers``
— the RECORD's operation — on both call sites. Measured on a record with one run,
correcting that run's never-answered ``qc``::

    POST /runs/{run_id}/edit {"qc": {…}}  -> 422 not_yet_answered
                                            answer_at: POST …/answers        (record)
    POST /answers           {"qc": {…}}  -> 409 belongs_to_a_run
                                            answer_at: POST …/runs/{id}/answers

``_refuse_run_level_on_the_record`` exists precisely to refuse a run-owned key on a
record that has runs, so the first refusal sent a compliant client to the one operation
that could not help it, and the client had to follow a SECOND redirect to arrive where
the first refusal should have sent it. A misdirecting refusal is worse than a silent
one: it spends the caller's retry and reads as authoritative while doing it.

**3. `POST /runs/{run_id}/check` reported `blockers: []` for a LEGACY run.**
``blockers`` was built from ``pending_to_list(unit.draft, …)``, and ``unit.draft`` comes
from ``resolved_run_draft``, which deep-copies ``run.draft`` and layers only the
EXPERIMENT-LEVEL addresses over it. ``pending`` is unclassified, so it is neither
inherited nor synthesised — and a run created before ``_seed_for_new_run`` existed has
no ``pending`` key at all, which is the durable state ``ws.run_questions`` was made
public for. Measured on such a run::

    GET  /experiments/{id}/pending  -> series, qc, descriptor   (3)
    GET  /experiments/{id}          -> pending_count 3
    POST /runs/{run_id}/check       -> blockers []   ok: false   official.ok: false

An empty ``blockers`` beside ``ok: false`` is the shape a client reads as "it fails and
nothing is open to fix" — the same class of false report as ``GuidedCompletion``
rendering "All blockers resolved" on an empty list, which this repository has already
had to correct once on the record-level ``/answers`` response.

WHY THE EXISTING SUITES DID NOT CATCH ANY OF THEM
=================================================
Every run in the pre-existing run tests is created through ``POST /runs``, so it is
SEEDED and carries a ``pending`` key; the legacy shape is only reachable by writing the
run through the store, which two tests in ``test_run_level_answers.py`` do — for the two
WRITE paths, never for the check. And nothing asserted where ``answer_at`` pointed on
the run path: ``test_the_run_level_edit_refuses_it_too_and_asks_the_RUNS_questions``
asserted the status and the error name and stopped there, which is exactly how a body
that named the wrong level stayed green.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

SERIES = [
    {
        "series_id": "averaged_spectrum",
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [8970, 8980, 8990]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [0.02, 0.85, 1.45],
            }
        ],
    }
]
DESCRIPTOR = {
    "name": "inflection_point_energy",
    "kind": "absolute",
    "source": "manual",
    "value": 9001.2,
    "unit": "eV",
    "uncertainty": {"sigma": 0.01, "unit": "eV", "basis": "reported"},
}
QC = {"status": "valid", "evidence": "I0 stable across the scan."}

RECORD_ANSWERS_OPERATION = "POST /api/experiments/{experiment_id}/answers"
RUN_ANSWERS_OPERATION = "POST /api/experiments/{experiment_id}/runs/{run_id}/answers"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


# --------------------------------------------------------------------------- helpers


def _record_etag(client: TestClient, exp_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}").headers["ETag"]


def _run_etag(client: TestClient, exp_id: str, run_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}/runs/{run_id}").headers["ETag"]


def _new_record(client: TestClient, title: str = "Cu K-edge") -> str:
    created = client.post("/api/experiments", json={"title": title})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _add_run(client: TestClient, exp_id: str, label: str = "300 K") -> str:
    added = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": label},
        headers={"If-Match": _record_etag(client, exp_id)},
    )
    assert added.status_code == 201, added.text
    return added.json()["run"]["id"]


def _legacy_run(client: TestClient, exp_id: str, *, draft: dict, label: str = "Legacy run"):
    """A run written the way ``workspace.new_run`` wrote them before seeding existed.

    ``draft={}`` — no ``pending`` key — is not a hypothetical: ``Experiment.to_state()``
    serialises runs, so every run created before ``routes._seed_for_new_run`` shipped is
    still an empty-drafted run in the durable store. This is the store rather than a
    route on purpose; no route can produce this shape any more.
    """
    exp = ws.load_experiment(exp_id)
    run = exp.add_run(label=label, draft=draft)
    exp.save()
    assert ("pending" in ws.load_experiment(exp_id).get_run(run.id).draft) is ("pending" in draft)
    return run.id


def _run_check(client: TestClient, exp_id: str, run_id: str) -> dict:
    checked = client.post(f"/api/experiments/{exp_id}/runs/{run_id}/check")
    assert checked.status_code == 200, checked.text
    return checked.json()


def _questions_for_run(client: TestClient, exp_id: str, run_id: str) -> set[str]:
    """What ``GET /pending`` — the surface a scientist reads — says this run still owes."""
    listed = client.get(f"/api/experiments/{exp_id}/pending")
    assert listed.status_code == 200, listed.text
    return {q["id"] for q in listed.json()["pending"] if q.get("run_id") == run_id}


def _follow_answer_at(client: TestClient, refusal: dict, *, answers: dict, headers: dict):
    """Follow a refusal's own ``answer_at``, substituting ONLY ids the body carries.

    Deliberately generic and deliberately blind to which level raised the refusal: the
    URL is never written down here, and every ``{placeholder}`` is filled from a
    same-named string key of the SAME response body. So this helper cannot pass unless
    the refusal both names the right operation and carries every id that operation
    needs — which is the second half of the contract and the half that had no test.
    """
    method, template = refusal["answer_at"].split(" ", 1)
    path = template
    for key, value in refusal.items():
        if isinstance(value, str):
            path = path.replace("{" + key + "}", value)
    assert "{" not in path, (
        "the refusal named an operation whose ids it does not carry: "
        f"{refusal['answer_at']} -> {path}"
    )
    return client.request(
        method, path, json={"confirmed_by_user": True, "answers": answers}, headers=headers
    )


# ---------------------------------------------------------------------------
# TASK 1 — the refusal reaches the PUBLISHED contract, on both operations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/experiments/{experiment_id}/edit",
        "/api/experiments/{experiment_id}/runs/{run_id}/edit",
    ],
)
def test_both_correction_operations_document_the_not_yet_answered_refusal(client, path):
    """Asserted against the SERVED document, because that is what a client reads.

    The source constant existing is not the property under test — it existed, unused,
    for its whole life. What matters is that the description a caller can fetch names
    the error it will receive, and says what ``answer_at`` means.
    """
    served = client.get("/api/openapi").json()
    described = served["paths"][path]["post"]["responses"]["422"]["description"]
    assert "not_yet_answered" in described, path
    # The three siblings it shares the status with are still enumerated — the record
    # operation used to name them and the run operation named none of them.
    for sibling in ("confirmation_required", "unrecognized_field", "invalid_field_value"):
        assert sibling in described, (path, sibling)
    # And the `answer_at` contract, including the half a client must code for.
    assert "answer_at" in described, path
    assert "absent" in described, path


@pytest.mark.parametrize(
    "path",
    [
        "/api/experiments/{experiment_id}/edit",
        "/api/experiments/{experiment_id}/runs/{run_id}/edit",
    ],
)
def test_declaring_the_422_did_not_strip_the_framework_validation_schema(client, path):
    """THE TRAP THIS REPOSITORY ALREADY DOCUMENTS, pinned at the two routes that moved.

    FastAPI skips generating its own ``422`` the moment a route declares one, silently
    dropping the ``HTTPValidationError`` content ref. There is a global guard for every
    operation; this is the local one, because the run-level route gained an explicit
    ``422`` in the same change that wrote it and would have lost the ref by default.
    """
    served = client.get("/api/openapi").json()
    schema = served["paths"][path]["post"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]
    assert schema["$ref"] == "#/components/schemas/HTTPValidationError", path


# ---------------------------------------------------------------------------
# TASK 2 — the refusal names the operation for the level it was raised at
# ---------------------------------------------------------------------------


def test_a_run_level_refusal_names_the_RUN_answers_operation(client):
    """REGRESSION TEST for the misdirection. It used to name the record's operation."""
    exp_id = _new_record(client)
    run_id = _add_run(client, exp_id)

    refused = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": QC}},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "not_yet_answered"
    assert body["keys"] == ["qc"]
    assert body["answer_at"] == RUN_ANSWERS_OPERATION, body
    # THE CONCRETE IDS TRAVEL BESIDE THE TEMPLATE, which is the convention
    # `belongs_to_a_run` and every other operation pointer in this module follows.
    assert body["experiment_id"] == exp_id
    assert body["run_id"] == run_id
    assert "Nothing was written." in body["message"]
    # Nothing was written, and the question is exactly as open as it was.
    assert ws.load_experiment(exp_id).get_run(run_id).draft.get("qc") in (None, {})
    assert "qc" in _questions_for_run(client, exp_id, run_id)


def test_a_record_level_refusal_still_names_the_RECORD_answers_operation(client):
    """NEGATIVE CONTROL for over-correcting. The record path was never wrong.

    It is reachable only on a record with NO runs — see the test below — and that is
    exactly the record whose own ``/answers`` accepts the key.
    """
    exp_id = _new_record(client)

    refused = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": QC}},
        headers={"If-Match": _record_etag(client, exp_id)},
    )
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "not_yet_answered"
    assert body["answer_at"] == RECORD_ANSWERS_OPERATION, body
    assert body["experiment_id"] == exp_id
    # No `run_id`, because no run raised it.
    assert "run_id" not in body, body


@pytest.mark.parametrize("key,value", [("qc", QC), ("series", SERIES), ("descriptor", DESCRIPTOR)])
def test_the_record_path_cannot_emit_this_refusal_once_it_has_runs(client, key, value):
    """THE MEASUREMENT THAT MAKES THE RECORD-LEVEL `answer_at` TRUE, not merely unchanged.

    Every key ``not_yet_answered`` can name is also a key ``belongs_to_a_run`` refuses,
    and on the record path that refusal runs FIRST. So the ONE case in which a
    record-level ``answer_at`` would be a lie — a record that has runs, whose own
    ``/answers`` would answer ``409`` — is not reachable. This pins that ordering, so a
    future reordering fails here rather than silently re-introducing a false redirect.
    """
    exp_id = _new_record(client)
    _add_run(client, exp_id)

    refused = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={"confirmed_by_user": True, "answers": {key: value}},
        headers={"If-Match": _record_etag(client, exp_id)},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "belongs_to_a_run"
    assert refused.json()["answer_at"] == RUN_ANSWERS_OPERATION


def test_the_two_refusals_name_the_run_operation_with_the_same_string(client):
    """Two refusals, one destination. Two copies of a URL is how one goes stale.

    ``belongs_to_a_run`` (record -> run) and ``not_yet_answered`` (raised on a run) both
    have to send a caller to the run's answers operation. They now share one constant;
    this asserts it over HTTP rather than by reading the source, because a client
    comparing the two strings is comparing what was served.
    """
    exp_id = _new_record(client)
    run_id = _add_run(client, exp_id)

    from_the_record = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": QC}},
        headers={"If-Match": _record_etag(client, exp_id)},
    ).json()
    from_the_run = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": QC}},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    ).json()
    assert from_the_record["answer_at"] == from_the_run["answer_at"]


# ---------------------------------------------------------------------------
# TASK 4 — the end-to-end machine-client negative control
# ---------------------------------------------------------------------------


def test_a_machine_client_following_answer_at_reaches_a_route_that_ACCEPTS(client):
    """THE WHOLE DOCUMENTED PATH, walked the way a compliant MCP/HTTP client walks it.

    This is the test the misdirection survived the absence of. It never writes the
    follow-up URL down: it parses ``answer_at`` out of the refusal body and fills every
    placeholder from that same body, so it fails if the refusal names the wrong level,
    if it omits an id its own operation needs, or if the named operation refuses.

    The last assertion is the one that makes it a lifecycle test rather than a status
    test: a ``200`` from the answers operation would also have been reported by the
    original defect this application had — a stored value beside a question that never
    closed. So the question is checked to have actually LEFT the open set, on the
    surface a scientist reads and on the run's own check.
    """
    exp_id = _new_record(client)
    run_id = _add_run(client, exp_id)
    assert "qc" in _questions_for_run(client, exp_id, run_id)

    # 1. Attempt the correction of a question nobody has ever answered.
    refusal = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": QC}},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert refusal.status_code == 422, refusal.text
    body = refusal.json()
    assert body["error"] == "not_yet_answered"

    # 2-4. Follow `answer_at` PROGRAMMATICALLY and answer the question there.
    #      A 409 or a 422 here means the refusal sent the client somewhere that
    #      refuses, which is the defect; anything but 200 fails.
    answered = _follow_answer_at(
        client,
        body,
        answers={"qc": QC},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert answered.status_code == 200, (
        f"answer_at pointed at {body['answer_at']}, which refused: "
        f"{answered.status_code} {answered.text}"
    )

    # 5. The original correction now succeeds — the state the refusal said was missing
    #    is present, so the same request is no longer refused.
    corrected = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "compromised", "evidence": "Beam dropped, scan 3."}},
        },
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert corrected.status_code == 200, corrected.text
    stored = ws.load_experiment(exp_id).get_run(run_id).draft["qc"]
    assert stored["status"] == "compromised", stored
    assert stored["evidence"] == "Beam dropped, scan 3.", stored

    # 6. THE LIFECYCLE ACTUALLY MOVED. Not "a 200 was returned" — the question is gone
    #    from the list a scientist reads AND from the run's own check.
    assert "qc" not in _questions_for_run(client, exp_id, run_id)
    assert "qc" not in {b["kind"] for b in _run_check(client, exp_id, run_id)["blockers"]}


def test_the_control_fails_if_answer_at_names_an_operation_that_refuses(client):
    """THE NEGATIVE CONTROL'S OWN NEGATIVE CONTROL.

    ``_follow_answer_at`` is only evidence if it would actually notice a wrong
    destination. This substitutes the operation the refusal USED to name — the record's
    — into an otherwise identical body, and asserts the follow is refused. If this ever
    passes with a ``200``, the test above has stopped proving anything, because both
    destinations would then work and the assertion could not tell them apart.
    """
    exp_id = _new_record(client)
    run_id = _add_run(client, exp_id)
    refusal = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": QC}},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    ).json()

    as_it_used_to_be = {**refusal, "answer_at": RECORD_ANSWERS_OPERATION}
    followed = _follow_answer_at(
        client,
        as_it_used_to_be,
        answers={"qc": QC},
        headers={"If-Match": _record_etag(client, exp_id)},
    )
    assert followed.status_code == 409, followed.text
    assert followed.json()["error"] == "belongs_to_a_run"


# ---------------------------------------------------------------------------
# TASK 3 — `blockers` on the run check, across every question count
# ---------------------------------------------------------------------------


def test_a_legacy_runs_check_reports_the_questions_it_actually_owes(client):
    """REGRESSION TEST for the measured `blockers: []`.

    Before: ``blockers []`` beside ``ok: false``, while ``GET /pending`` listed three
    and ``pending_count`` said 3. After: the same three, from the same derivation.
    """
    exp_id = _new_record(client, "Legacy")
    run_id = _legacy_run(client, exp_id, draft={})

    shown = _questions_for_run(client, exp_id, run_id)
    assert shown == {"series", "qc", "descriptor"}, shown

    checked = _run_check(client, exp_id, run_id)
    assert {b["kind"] for b in checked["blockers"]} == shown, checked["blockers"]
    # THE PAIRING THAT MADE IT A FALSE REPORT rather than a missing one: a client
    # reading `ok: false` with an empty `blockers` is told it fails and nothing is
    # open to fix.
    assert checked["ok"] is False
    assert checked["blockers"], "an empty list beside ok: false is the defect itself"


def test_a_legacy_run_that_already_HOLDS_a_verdict_still_agrees_with_pending(client):
    """THE BOUNDARY CASE, pinned as CONSISTENCY rather than as a claim about the science.

    ``ws.run_questions`` derives a legacy run's list from the blank-draft template, so
    it lists ``qc`` even for a run whose draft already holds a verdict — a documented
    property of that derivation, and the reason
    :func:`routes._refuse_correcting_an_unanswered_key` requires a key to be BOTH open
    AND absent from the draft before refusing a correction.

    This test does NOT assert that listing ``qc`` there is right. It asserts that the
    check operation says whatever ``GET /pending`` and ``pending_count`` say, so the
    three surfaces cannot disagree about one run — which is the property that was
    broken. If that derivation is ever narrowed, this test moves with it in one place.
    """
    exp_id = _new_record(client, "Legacy with a verdict")
    run_id = _legacy_run(client, exp_id, draft={"qc": {"status": "valid", "evidence": "e"}})

    checked = _run_check(client, exp_id, run_id)
    assert {b["kind"] for b in checked["blockers"]} == _questions_for_run(client, exp_id, run_id)
    assert client.get(f"/api/experiments/{exp_id}").json()["pending_count"] == len(
        checked["blockers"]
    )


def test_a_run_with_zero_questions_reports_an_empty_list(client):
    """NEGATIVE CONTROL for over-reporting. An empty `blockers` must still be reachable.

    A run added to a record that has already answered everything ADOPTS those answers,
    so it owes nothing — and ``pending: []`` (the key present and empty) is how
    ``run_questions`` distinguishes "answered" from "never asked".
    """
    exp_id = _new_record(client)
    applied = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "answers": {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC},
            "confirmed_by_user": True,
        },
        headers={"If-Match": _record_etag(client, exp_id)},
    )
    assert applied.status_code == 200, applied.text
    run_id = _add_run(client, exp_id)

    checked = _run_check(client, exp_id, run_id)
    assert checked["blockers"] == []
    assert _questions_for_run(client, exp_id, run_id) == set()


def test_a_run_with_several_questions_reports_every_one_of_them(client):
    """A fresh seeded run owes all three, each addressable to the run that owns it."""
    exp_id = _new_record(client)
    run_id = _add_run(client, exp_id)

    blockers = _run_check(client, exp_id, run_id)["blockers"]
    assert {b["kind"] for b in blockers} == {"series", "qc", "descriptor"}
    for blocker in blockers:
        # `run_id` was `null` on this operation before the change, and `blocker_key` was
        # the bare kind — the COLLIDING key that `serialize.pending_to_list` introduced
        # `blocker_key` to replace, served by the one operation addressed to a single
        # run. Both now carry the run, as `GET /pending` already did.
        assert blocker["run_id"] == run_id, blocker
        assert blocker["blocker_key"] == f"{run_id}:{blocker['id']}", blocker
        # Every element carries a non-empty `message` — this operation's own contract.
        assert blocker["message"].strip()


def test_a_run_with_ONE_question_left_reports_exactly_that_one(client):
    """The counts in between, and the answered ones are gone rather than merely last."""
    exp_id = _new_record(client)
    run_id = _add_run(client, exp_id)

    for answers in ({"series": SERIES}, {"descriptor": DESCRIPTOR}):
        applied = client.post(
            f"/api/experiments/{exp_id}/runs/{run_id}/answers",
            json={"answers": answers, "confirmed_by_user": True},
            headers={"If-Match": _run_etag(client, exp_id, run_id)},
        )
        assert applied.status_code == 200, applied.text

    blockers = _run_check(client, exp_id, run_id)["blockers"]
    assert [b["kind"] for b in blockers] == ["qc"], blockers


def test_an_already_answered_question_is_absent_from_the_check(client):
    """The answered one leaves the list; the unanswered ones stay in it."""
    exp_id = _new_record(client)
    run_id = _add_run(client, exp_id)
    applied = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": {"qc": QC}, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert applied.status_code == 200, applied.text
    assert ws.load_experiment(exp_id).get_run(run_id).draft["qc"] == QC

    kinds = {b["kind"] for b in _run_check(client, exp_id, run_id)["blockers"]}
    assert "qc" not in kinds
    assert kinds == {"series", "descriptor"}, kinds


def test_one_runs_check_reports_ONLY_that_runs_questions(client):
    """SCOPE, unchanged by the fix and worth pinning because the source moved.

    The entries now come from ``Experiment.pending()``, which aggregates the record's
    own questions and EVERY run's. This operation documents "the run's open blocking
    questions", so the aggregate is filtered to this run — a sibling's questions must
    not appear here, and neither must the record's own non-run-level ones.
    """
    exp_id = _new_record(client)
    first = _add_run(client, exp_id, label="300 K")
    second = _add_run(client, exp_id, label="400 K")

    applied = client.post(
        f"/api/experiments/{exp_id}/runs/{first}/answers",
        json={"answers": {"qc": QC}, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(client, exp_id, first)},
    )
    assert applied.status_code == 200, applied.text

    first_blockers = _run_check(client, exp_id, first)["blockers"]
    second_blockers = _run_check(client, exp_id, second)["blockers"]
    assert {b["kind"] for b in first_blockers} == {"series", "descriptor"}
    assert {b["kind"] for b in second_blockers} == {"series", "qc", "descriptor"}
    assert {b["run_id"] for b in first_blockers} == {first}
    assert {b["run_id"] for b in second_blockers} == {second}

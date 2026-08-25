"""``POST /answers`` applied no size and no depth bound; ``POST /edit`` applied both.

THE DEFECT, measured by an independent security review on 2026-08-24, over HTTP, on a
record created through this application's own Create Experiment path.

``routes._correction_is_storable`` — the ``/edit`` screen — runs ``_is_storable_value``
with an 8 MiB cap, a depth-32 cap and a real JSON render. ``post_answers`` and
``_apply_to_run``'s answering branch called NEITHER. There is no global body-size
middleware in this application, so nothing else stood behind them. Two measurements:

    a 20 MiB `qc.evidence`  ->  POST /answers  200, PERSISTED (workspace file ~42 MB,
                                               ~2x amplification through
                                               `block_evidence` and `answer_log`)
                            ->  POST /edit     422 invalid_field_value

    a 700-deep `descriptor`  -> POST /answers  HTTP 500, `RecursionError` out of
                                               `isaac_records.complete`'s `copy.deepcopy`
                                               (depth 400 was accepted and STORED)
                            ->  POST /edit     422 invalid_field_value

Same value, same field, same record, two different answers — and the weaker of the two
is on the route a scientist and an MCP agent actually use to fill a record in.

THE ``qc`` HALF IS THIS BRANCH'S OWN DOING, which is why it is pinned rather than merely
noted: ``qc`` was not forwarded by ``_answers_to_apply_shape`` at all on ``main``, so
this branch ADDED the ingress and gave it the weaker screen of the two.

WHAT THE FIX IS, and what it deliberately is not. One route-level screen
(``routes._refuse_unstorable_answer``) on both answering paths, sharing
``routes._value_fits_the_store`` with the correction screen so the 8 MiB bound has one
definition. It applies size, depth and renderability ONLY. It does NOT apply the shape
predicates: a wrong-TYPED answer keeps taking the existing "not applied -> the blocker
stays open" path, which ``test_answers_wrong_type.py`` pins and which the record
``/edit`` route's own comment names as the reason it did not extend its screen here.
That negative control is in this file too, because a fix that quietly widened the screen
would pass everything above it and change a documented behaviour.

NO TRUTH-CORE CHANGE. ``src/isaac_records`` is untouched: the condition is an ingress
condition, and a depth guard inside ``apply_answers`` would change what every caller
gets, including the CLI and the exporter.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from isaac_api.app import create_app

from conftest import tutorial_client

#: The seeded worked-example record whose open blockers are STRUCTURED (`series` and
#: `descriptor`), which is what `test_answers_wrong_type.py` uses and what makes the
#: `RecursionError` reachable: the descriptor branch is the one that deep-copies.
PARTIAL = "01SYNTHXANESSEED0000000002"

#: The seeded worked-example record that still has OPEN ASSET questions, which
#: `PARTIAL` does not. Used only by the asset case: an asset value lives under
#: `asset_sha256` in the apply shape, so it is the one key class a screen could skip by
#: iterating top-level keys alone.
WITH_ASSETS = "01SYNTHXANESSEED0000000001"

#: Comfortably past `_MAX_CORRECTION_BYTES` (8 MiB) once rendered, and small enough that
#: building it costs nothing. The measured payload was 20 MiB; 12 MiB proves the same
#: boundary without making the suite allocate twice as much.
_TOO_BIG = "x" * (12 * 1024 * 1024)

#: Past `_MAX_VALUE_DEPTH` (32) by enough that the OLD behaviour was a `RecursionError`
#: rather than a quiet acceptance. 400 was measured stored; 700 was measured crashing.
_TOO_DEEP_LEVELS = 700


def _too_deep() -> dict:
    root: dict = {}
    node = root
    for _ in range(_TOO_DEEP_LEVELS):
        child: dict = {}
        node["a"] = child
        node = child
    return root


@pytest.fixture()
def client(monkeypatch, tmp_path) -> TestClient:
    # PER-TEST WORKSPACE, following `test_answers_wrong_type.py`: several of these
    # answer a blocker, and a shared workspace would make a later test read a record
    # whose pending set an earlier one changed.
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return tutorial_client(create_app())


@pytest.fixture()
def ordinary_client(monkeypatch, tmp_path) -> TestClient:
    """A client WITHOUT the worked-example session header.

    `POST /api/experiments` answers `409 ordinary_scope_required` inside a session — a
    session is discarded when it expires, so a record created in one would be lost — and
    the run-level cases below need a record they created, because the worked examples'
    runs are fixture-built.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws-ordinary"))
    return TestClient(create_app())


def _etag(client: TestClient, rid: str) -> str:
    response = client.get(f"/api/experiments/{rid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _answer(client: TestClient, rid: str, answers: dict):
    return client.post(
        f"/api/experiments/{rid}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": _etag(client, rid)},
    )


def _edit(client: TestClient, rid: str, answers: dict):
    return client.post(
        f"/api/experiments/{rid}/edit",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": _etag(client, rid)},
    )


def _pending_ids(client: TestClient, rid: str) -> set[str]:
    response = client.get(f"/api/experiments/{rid}/pending")
    assert response.status_code == 200, response.text
    return {entry["id"] for entry in response.json()["pending"]}


# ==========================================================================
# 1. the record-level answering path
# ==========================================================================

def test_an_oversized_answer_is_refused_rather_than_written(client):
    """BEFORE THE FIX: `200`, and ~42 MB on disk for a 20 MiB submission."""
    before = _pending_ids(client, PARTIAL)
    before_etag = _etag(client, PARTIAL)

    response = _answer(client, PARTIAL, {"descriptor": {"value": _TOO_BIG}})

    assert response.status_code == 422, response.status_code
    body = response.json()
    assert body["error"] == "invalid_field_value"
    assert body["key"] == "descriptor"
    assert body["keys"] == ["descriptor"]
    # NOTHING WAS WRITTEN, asserted at the two places a write would show: the record's
    # validator did not move, and the question the answer claimed to close is still open.
    assert _etag(client, PARTIAL) == before_etag
    assert _pending_ids(client, PARTIAL) == before


def test_an_over_deep_answer_is_a_typed_422_and_not_a_500(client):
    """BEFORE THE FIX: `RecursionError` out of `isaac_records.complete`'s `copy.deepcopy`,
    surfaced as a bare HTTP 500 from the truth core.

    CLAUDE.md §15 already records this exact shape — "a wrong-typed structured answer
    used to return HTTP 500 from the truth core" — as something a typed 422 should close.
    """
    before = _pending_ids(client, PARTIAL)
    response = _answer(client, PARTIAL, {"descriptor": _too_deep()})
    assert response.status_code == 422, response.status_code
    assert response.json()["error"] == "invalid_field_value"
    assert _pending_ids(client, PARTIAL) == before


def test_the_message_says_the_question_is_still_open_and_names_no_cause(client):
    """THE MESSAGE IS NOT `/edit`'s, and the difference is the honest half.

    `/edit`'s reads "The stored value is unchanged", which is true there and FALSE here:
    on the answering path the field may never have held a value at all. It names no
    cause, for the reason the `/edit` refusal's own comment gives at length — a
    cause-naming sentence was measured being served verbatim about a key it did not
    describe.
    """
    response = _answer(client, PARTIAL, {"series": [{"mu": _TOO_BIG}]})
    assert response.status_code == 422
    message = response.json()["message"]
    assert "the question is still open" in message
    assert "The stored value is unchanged" not in message
    for cause in ("bytes", "deep", "large", "8 MiB", "depth"):
        assert cause not in message, message


def test_an_unrenderable_answer_is_refused_too(client):
    """`NaN` renders as a bare JSON literal, which makes `experiment.json` invalid JSON
    and every later export raise `ValueError` FOREVER. The correction path has refused it
    since `_is_storable_value` gained condition 2; the answering path did not.

    Sent as raw content because `json.dumps` is what produces the invalid literal — a
    dict passed to `json=` would be rejected by the client, not by the server.
    """
    response = client.post(
        f"/api/experiments/{PARTIAL}/answers",
        content=json.dumps(
            {"answers": {"descriptor": {"value": float("nan")}}, "confirmed_by_user": True}
        ),
        headers={"If-Match": _etag(client, PARTIAL), "Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.status_code
    assert response.json()["error"] == "invalid_field_value"


# ==========================================================================
# 2. the two ingresses now agree
# ==========================================================================

@pytest.mark.parametrize(
    "value", ({"value": _TOO_BIG}, _too_deep()), ids=("oversized", "over-deep")
)
def test_answers_and_edit_refuse_the_same_value_with_the_same_code(client, value):
    """THE DEFECT WAS THE DISAGREEMENT, not either verdict on its own.

    `/edit` returned `422 invalid_field_value` for exactly these values while `/answers`
    returned `200` (or `500`). This asserts the codes now match. It does NOT assert the
    two routes are otherwise interchangeable: `/edit` on a record whose `descriptor`
    question is still OPEN refuses with `not_yet_answered`, which is a different and
    correct refusal about the QUESTION rather than about the value — so the comparison
    is made on the record path after the descriptor has been answered.
    """
    answered = _answer(client, PARTIAL, {"descriptor": {"value": 1.0, "uncertainty": 0.1}})
    assert answered.status_code == 200, answered.text

    from_answers = _answer(client, PARTIAL, {"descriptor": value})
    from_edit = _edit(client, PARTIAL, {"descriptor": value})
    assert from_answers.status_code == from_edit.status_code == 422
    assert from_answers.json()["error"] == from_edit.json()["error"] == "invalid_field_value"


# ==========================================================================
# 3. the run-level answering path — the other half of the same hole
# ==========================================================================

def _new_record_with_a_run(client: TestClient) -> tuple[str, str]:
    created = client.post("/api/experiments", json={"title": "size screen"})
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]
    run = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": "Run 1"},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert run.status_code == 201, run.text
    return experiment_id, run.json()["run"]["id"]


def _run_etag(client: TestClient, experiment_id: str, run_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


@pytest.mark.parametrize(
    "answers",
    (
        {"qc": {"status": "valid", "evidence": _TOO_BIG}},
        {"descriptor": _too_deep()},
    ),
    ids=("oversized-qc", "over-deep-descriptor"),
)
def test_the_run_answering_path_refuses_the_same_values(ordinary_client, answers):
    """THE RUN's `/answers` HAD NO VALUE-SIDE SCREEN AT ALL while the run's `/edit`,
    three lines away in the same function, has had one since the correction routes were
    hardened. One shared screen, or they drift — which is the whole argument for
    `_refuse_unstorable_answer` being a function.

    THE TWO CASES USE DIFFERENT KEYS ON PURPOSE, and the reason is a real narrowing of
    the finding. An over-deep `qc` never reaches this screen at all: `/answers` already
    passes `qc` through `is_qc_shaped` inside `_answers_to_apply_shape` (see that
    function's note on why `/answers` screens `qc` and `/edit` does not), and a nest of
    empty dicts has no `status`, so it is dropped before any write. `descriptor` has no
    such pre-screen on the answering path, which is exactly why the measured
    `RecursionError` came out of the descriptor branch's `copy.deepcopy`. An oversized
    `qc.evidence`, by contrast, IS well-shaped — which is the whole point of the finding.
    """
    experiment_id, run_id = _new_record_with_a_run(ordinary_client)
    response = ordinary_client.post(
        f"/api/experiments/{experiment_id}/runs/{run_id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(ordinary_client, experiment_id, run_id)},
    )
    assert response.status_code == 422, response.status_code
    assert response.json()["error"] == "invalid_field_value"


def test_an_oversized_asset_hash_is_refused_on_the_answering_path(client):
    """ASSET VALUES ARE SCREENED INDIVIDUALLY, not skipped because they live under a
    nested key. `asset_sha256` is a dict of uri -> value in the apply shape, so a screen
    that iterated only top-level keys would check the DICT and let every value inside it
    through — which is how the correction screen's own asset case was originally missed.
    """
    pending = client.get(f"/api/experiments/{WITH_ASSETS}/pending").json()["pending"]
    asset_uris = [entry["id"] for entry in pending if entry["kind"] == "asset"]
    # NOT A SKIP. An earlier draft skipped when the record had no asset question, which
    # would have made this test silently vacuous the day the fixture changed — and the
    # asset case is the one a top-level-keys-only screen would miss.
    assert asset_uris, [entry["kind"] for entry in pending]
    response = _answer(client, WITH_ASSETS, {asset_uris[0]: _TOO_BIG})
    assert response.status_code == 422, response.status_code
    assert response.json()["keys"] == [asset_uris[0]]


# ==========================================================================
# 4. the negative controls — what must NOT have changed
# ==========================================================================

def test_a_legitimate_structured_answer_still_applies(client):
    """THE CONTROL THAT MAKES THE REFUSAL MEAN SOMETHING. A screen that refused
    everything would satisfy every assertion above and break the product.
    """
    before = _pending_ids(client, PARTIAL)
    response = _answer(
        client,
        PARTIAL,
        {"series": [{"series_id": "s1", "mu": 0.1}, {"series_id": "s1", "mu": 0.2}]},
    )
    assert response.status_code == 200, response.text
    assert "series" not in _pending_ids(client, PARTIAL)
    assert before != _pending_ids(client, PARTIAL)


def test_a_LARGE_but_legal_series_is_still_accepted(client):
    """8 MiB IS NOT A SCIENTIFIC LIMIT AND MUST NOT BECOME ONE. A reduced spectrum is
    legitimately big — that is why the correction path uses `_MAX_CORRECTION_BYTES` and
    not the run path's 64 KiB, and why the answering path was given the SAME number
    rather than a stricter one of its own. ~20,000 points is a real spectrum's order of
    magnitude and is nowhere near the cap.
    """
    series = [{"series_id": "s1", "energy_eV": 7000.0 + i, "mu": 0.1} for i in range(20000)]
    response = _answer(client, PARTIAL, {"series": series})
    assert response.status_code == 200, response.status_code
    assert "series" not in _pending_ids(client, PARTIAL)


def test_a_wrong_TYPED_answer_still_takes_the_stays_pending_path(client):
    """THE SCREEN WAS NOT WIDENED TO SHAPE, AND THIS IS THE ASSERTION THAT SAYS SO.

    A wrong-typed answer is dropped by the core and its blocker is reported STILL OPEN in
    a `200` — the behaviour `test_answers_wrong_type.py` pins and that the record
    `/edit` route's own comment names as the reason it deliberately did not extend its
    screen to `/answers`. If a future change reaches for `_correction_is_storable` here
    instead of `_value_fits_the_store`, this goes red before that file does.
    """
    response = _answer(client, PARTIAL, {"series": "0" * 64})
    assert response.status_code == 200, response.text
    assert "series" in _pending_ids(client, PARTIAL)


def test_the_two_screens_share_one_definition_of_the_size_bound():
    """THE STRUCTURAL HALF: two screens for one condition is how they drift apart, and
    this hole is what drifting apart looks like. Asserted against the source rather than
    against behaviour, because behaviour cannot see a duplicated constant.
    """
    from isaac_api import routes

    assert routes._correction_is_storable("edge", "K") is True
    # The correction screen's size/depth/renderability half IS the answering screen.
    assert routes._value_fits_the_store(_TOO_BIG) is False
    assert routes._correction_is_storable("descriptor_label", _TOO_BIG) is False
    assert routes._value_fits_the_store(_too_deep()) is False


def test_the_published_contract_describes_the_new_refusal():
    """A REFUSAL THE ROUTE PERFORMS AND THE CONTRACT DOES NOT DESCRIBE IS THE GAP
    `_R_CORRECTION_REFUSED` WAS WRITTEN TO CLOSE ("the record's 422 enumerated three
    refusals while the route performed four"). Adding the behaviour without the sentence
    would repeat it on the other pair of routes.
    """
    app = create_app()
    schema = app.openapi()
    for path in (
        "/api/experiments/{experiment_id}/answers",
        "/api/experiments/{experiment_id}/runs/{run_id}/answers",
    ):
        description = schema["paths"][path]["post"]["responses"]["422"]["description"]
        assert "invalid_field_value" in description, path
        assert "the question is still open" in description, path

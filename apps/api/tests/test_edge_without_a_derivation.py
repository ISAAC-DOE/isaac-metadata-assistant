"""`edge` answered where there is nothing to write into: the last "identical" lie.

THE DEFECT, measured by an independent security review on 2026-08-24 against a record
created through this application's own ``POST /api/experiments`` path::

    POST /api/experiments/{id}/answers  {"edge": "L3"}
      -> 200
         invalidation.changed   false
         invalidation.reason    "No change — the submitted value was identical;
                                 nothing was invalidated."
         draft["implicit"]      still absent

Neither half of that reason is true — the value was not identical and was never stored.
It is the same "false twice over" defect this branch fixed for ``series``, ``qc``,
``descriptor`` and a pending asset hash, left live for the one key that has no blocker
and therefore fell outside every question-state refusal.

WHY IT HAPPENS: ``complete.apply_answers`` and ``complete.apply_corrections`` both write
``edge`` only INTO an existing ``implicit[]`` entry whose ``about`` is ``"edge"``.
``extract.draft_builder`` emits that entry; **no route creates one**, and a created record
has no ``implicit`` block at all. Nothing in the route stack noticed: ``edge`` is exempt
from ``_refuse_run_level_on_the_record`` (correctly — it does inherit), is in
``_has_correction_target``'s key set (so ``/edit`` proceeded), and is absent from
``_CORRECTABLE_KEY_KINDS`` (so ``_refuse_correcting_an_unanswered_key`` never saw it).

THE CHOICE MADE, and the alternative rejected. See
``routes._refuse_edge_with_nothing_to_confirm`` for the argument in full; in brief,
making the answer LAND would mean a route synthesising an ``implicit[]`` entry, which is
the extractor's block and asserts a derivation that a created record does not have
(CLAUDE.md §5), or changing ``src/isaac_records/complete.py``, which §13 protects. And
the official ISAAC schema has no edge field, so a refused answer costs the exported record
nothing.

THIS IS NOT THE UNCONDITIONAL REFUSAL THAT WAS TRIED AND WAS WORSE.
``routes._RUN_LEVEL_ANSWER_BLOCK``'s note records a version that refused ``edge`` on the
record outright, making it answerable by no route and pointing the caller at an operation
that would also refuse. This one fires only where there is demonstrably nothing to write
into, and names no alternative operation. The "it still works where it always worked"
half is pinned in ``test_run_level_answers.py`` and ``test_answering_a_closed_question.py``
— both of which had tests asserting the ``200``, and both of which were INVERTED rather
than deleted.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api.app import create_app

#: An `implicit[]` entry of the shape `draft_builder` emits: a derivation with no
#: confirmed value yet. This is what an `edge` answer confirms.
_EDGE_DERIVATION = {
    "about": "edge",
    "value": None,
    "evidence": [{"source_type": "derivation", "rule": "test"}],
}


@pytest.fixture()
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return TestClient(create_app())


def _etag(client: TestClient, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client: TestClient, experiment_id: str, run_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _record(client: TestClient, *, with_derivation: bool) -> str:
    created = client.post("/api/experiments", json={"title": "Edge"})
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]
    if with_derivation:
        # THE STORE, NOT A ROUTE — and that is exactly the point of the finding: no
        # route creates this entry, which is why a created record can never grow one.
        exp = ws.load_experiment(experiment_id)
        exp.draft.setdefault("implicit", []).append(dict(_EDGE_DERIVATION))
        exp.save()
    return experiment_id


def _add_run(client: TestClient, experiment_id: str) -> str:
    added = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": "300 K"},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert added.status_code == 201, added.text
    return added.json()["run"]["id"]


# ==========================================================================
# 1. the record's two write paths
# ==========================================================================

@pytest.mark.parametrize("operation", ("answers", "edit"))
def test_the_record_refuses_an_edge_it_has_nothing_to_confirm(client, operation):
    """BEFORE THE FIX both returned `200` with the "identical" reason, having written
    nothing. `/edit` reached it by a different route than `/answers` — `edge` is in
    `_has_correction_target`'s key set and absent from `_CORRECTABLE_KEY_KINDS` — which
    is why both are exercised rather than one standing in for the other.
    """
    experiment_id = _record(client, with_derivation=False)
    response = client.post(
        f"/api/experiments/{experiment_id}/{operation}",
        json={"answers": {"edge": "L3"}, "confirmed_by_user": True},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422, response.status_code
    body = response.json()
    assert body["error"] == "no_derivation_to_confirm"
    assert body["experiment_id"] == experiment_id
    assert body["key"] == "edge" and body["keys"] == ["edge"]
    assert not (ws.load_experiment(experiment_id).draft.get("implicit") or [])


def test_the_refusal_makes_no_claim_the_response_cannot_support(client):
    """THE MESSAGE IS THE WHOLE POINT OF THIS FINDING, so it is asserted rather than
    left to prose.

    It must not repeat the false "identical" claim, must not point at an operation that
    would also refuse (the mistake `_RUN_LEVEL_ANSWER_BLOCK` records), and must not imply
    the exported record has lost a value — the official schema has no edge field at all.
    """
    experiment_id = _record(client, with_derivation=False)
    response = client.post(
        f"/api/experiments/{experiment_id}/answers",
        json={"answers": {"edge": "L3"}, "confirmed_by_user": True},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    body = response.json()
    assert "identical" not in body["message"]
    assert "nothing was written" in body["message"]
    assert "no edge field" in body["message"]
    for pointer in ("answer_at", "edit_at", "operation"):
        assert pointer not in body, body


def test_a_record_that_HAS_a_derivation_is_completely_unaffected(client):
    """THE CONTROL. The refusal is conditional on there being nothing to write into; a
    record whose draft carries the derivation takes the answer exactly as before, and the
    value LANDS — asserted on the stored draft rather than on the status code, which is
    what the inverted tests were failing to do.
    """
    experiment_id = _record(client, with_derivation=True)
    response = client.post(
        f"/api/experiments/{experiment_id}/answers",
        json={"answers": {"edge": "L3"}, "confirmed_by_user": True},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 200, response.text
    stored = ws.load_experiment(experiment_id).draft.get("implicit") or []
    assert [e["value"] for e in stored if e.get("about") == "edge"] == ["L3"]


# ==========================================================================
# 2. the run's two write paths
# ==========================================================================

@pytest.mark.parametrize("operation", ("answers", "edit"))
def test_the_run_refuses_an_edge_it_has_nothing_to_confirm(client, operation):
    """THE SAME SCREEN, ASKED OF THE RUN's OWN DRAFT.

    `_apply_to_run` applies it BEFORE the correcting/answering branch, because both
    writers have the identical restriction — they write `edge` only into an entry that
    exists — so a run draft with no such entry produces a 200 about an impossible write
    either way. `run_id` travels in the body so the caller can tell which level refused.
    """
    experiment_id = _record(client, with_derivation=False)
    run_id = _add_run(client, experiment_id)
    response = client.post(
        f"/api/experiments/{experiment_id}/runs/{run_id}/{operation}",
        json={"answers": {"edge": "L3"}, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(client, experiment_id, run_id)},
    )
    assert response.status_code == 422, response.status_code
    body = response.json()
    assert body["error"] == "no_derivation_to_confirm"
    assert body["experiment_id"] == experiment_id
    assert body["run_id"] == run_id


# ==========================================================================
# 3. the published contract
# ==========================================================================

def test_all_four_write_operations_describe_the_refusal_they_perform():
    """THE GAP `_R_CORRECTION_REFUSED` WAS WRITTEN TO CLOSE, on four routes at once:
    "the record's 422 enumerated three refusals while the route performed four". A new
    refusal that reaches no generated OpenAPI document reaches no machine client that
    reads the contract before calling.
    """
    schema = create_app().openapi()
    for path in (
        "/api/experiments/{experiment_id}/answers",
        "/api/experiments/{experiment_id}/edit",
        "/api/experiments/{experiment_id}/runs/{run_id}/answers",
        "/api/experiments/{experiment_id}/runs/{run_id}/edit",
    ):
        description = schema["paths"][path]["post"]["responses"]["422"]["description"]
        assert "no_derivation_to_confirm" in description, path


def test_the_predicate_matches_the_truth_core_writers_it_stands_in_for():
    """THE STRUCTURAL HALF. This screen is only correct while it asks the SAME question
    `complete.apply_answers` and `complete.apply_corrections` ask. Both loop
    `draft["implicit"]` for `about == "edge"`; if either ever grew a create-if-absent
    branch, this refusal would start refusing writes that would now succeed.

    Asserted against the truth core's source, because nothing about its behaviour is
    observable from a draft that has no entry — which is precisely the case at issue.
    """
    import inspect

    from isaac_records import complete

    for writer in (complete.apply_answers, complete.apply_corrections):
        source = inspect.getsource(writer)
        assert 'imp.get("about") == "edge"' in source, writer.__name__
        assert 'draft.get("implicit")' in source, writer.__name__

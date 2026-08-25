"""A `200` THAT DISCARDED THE SCIENTIST'S VALUE AND GAVE A FALSE REASON FOR IT.

WHAT WAS MEASURED, over HTTP, on a record created through ``POST /api/experiments``. A
run's ``series`` was answered with ``series_id: "race-a"``; ``"race-b"`` was then sent to
the SAME operation::

    POST /api/experiments/{id}/runs/{run_id}/answers {"series": <race-b>}
      -> 200
         invalidation.changed        false
         invalidation.rev            unmoved
         invalidation.reason         "No change — the submitted value was identical;
                                      nothing was invalidated."
         stored series_id AFTER      race-a

The value was neither identical nor ever stored — the same two false claims, in the same
sentence, that ``_answers_to_apply_shape``'s docstring already records for the ASSET key
on the CORRECTION route and calls *"false twice over"*. It was live on the opposite route
in FIVE key/level combinations, every one of them measured before the fix:

    POST /runs/{run_id}/answers   series      -> 200, discarded, "identical"
    POST /runs/{run_id}/answers   qc          -> 200, discarded, "identical"
    POST /runs/{run_id}/answers   descriptor  -> 200, discarded, "identical"
    POST /answers  (no runs)      series      -> 200, discarded, "identical"
    POST /answers  (no runs)      <asset uri> -> 200, discarded, "identical"

WHY IT HAPPENS, structurally. ``complete.apply_answers`` iterates ``draft["pending"]`` and
writes only from inside a branch it entered from a pending entry, so a CLOSED question has
no entry, no branch, and no write — including for an asset, whose entry is removed when it
materialises. The route then reports ``changed=False``, and ``build_invalidation`` cannot
tell "the caller resubmitted the identical value" from "we dropped what the caller sent".

THE SEMANTICS CHOSEN, and why they are not invented. ``/answers`` answers OPEN questions;
``/edit`` corrects ALREADY-ANSWERED ones. ``_refuse_correcting_an_unanswered_key`` already
enforces one half of that division — ``/edit`` refuses a key that is still open, with
``422 not_yet_answered`` naming the answers operation. This is the mirror:
``422 already_answered`` naming the EDIT operation. No new concept, and the same
established rule that a refusal must land somewhere that accepts the request.

AND IT FIRES ONLY WHERE THE VALUES DIFFER. An identical resubmission is a real,
load-bearing behaviour — a client may retry a request it is unsure landed — pinned by
three tests elsewhere in this suite. A first draft of the refusal broke all three, which
is how the requirement was found rather than assumed. For an identical resubmission the
"identical" sentence is TRUE and nothing was lost; only a DIFFERING value is a discarded
one. Both directions are asserted here.

WHAT IS DELIBERATELY NOT CLOSED. An UNUSABLE value sent to a closed question is still
absorbed into the same ``200``. That is asserted below rather than left unsaid, as a
documented known limit: it belongs to the route's unusable-value doctrine
(``_correction_is_storable`` / ``invalid_field_value``), a different rule at a different
layer, and adopting it here would also change what an unusable answer to an OPEN question
does — where the returned ``pending`` list already tells the caller the answer did not
land.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import tutorial_client
from test_scientist_can_finish_a_record import DESCRIPTOR, QC, SERIES

#: Two series that differ only in their id, so a comparison cannot pass by accident on
#: some unrelated field.
SERIES_A = copy.deepcopy(SERIES)
SERIES_A[0]["series_id"] = "race-a"
SERIES_B = copy.deepcopy(SERIES)
SERIES_B[0]["series_id"] = "race-b"

_EDIT_RECORD = "POST /api/experiments/{experiment_id}/edit"
_EDIT_RUN = "POST /api/experiments/{experiment_id}/runs/{run_id}/edit"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


@pytest.fixture()
def tutorial(tmp_path, monkeypatch):
    """A worked-example client — the only scope with a seeded ASSET blocker."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _version(client, exp_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}").json()["version"]


def _answer(client, exp_id: str, answers: dict):
    return client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )


def _edit(client, exp_id: str, answers: dict):
    return client.post(
        f"/api/experiments/{exp_id}/edit",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )


def _answer_run(client, exp_id: str, answers: dict):
    run = ws.load_experiment(exp_id).runs[0]
    return client.post(
        f"/api/experiments/{exp_id}/runs/{run.id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{run.version_token()}"'},
    )


def _record_with_answers(client) -> str:
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    applied = _answer(client, exp_id, {"series": SERIES_A, "descriptor": DESCRIPTOR, "qc": QC})
    assert applied.status_code == 200, applied.text
    return exp_id


def _run_with_answers(client) -> tuple[str, str]:
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    added = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "300 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert added.status_code == 201, added.text
    applied = _answer_run(client, exp_id, {"series": SERIES_A, "descriptor": DESCRIPTOR, "qc": QC})
    assert applied.status_code == 200, applied.text
    return exp_id, ws.load_experiment(exp_id).runs[0].id


def _stored_series(exp_id: str, run_id: str | None = None):
    exp = ws.load_experiment(exp_id)
    draft = exp.get_run(run_id).draft if run_id else exp.draft
    return draft.get("series")


# --- the refusal, on the run route it was reported on -------------------------


def test_a_differing_series_on_a_run_is_refused_and_nothing_is_lost(client):
    """THE REGRESSION, exactly as measured."""
    exp_id, run_id = _run_with_answers(client)
    before = ws.load_experiment(exp_id).runs[0].version_token()

    refused = _answer_run(client, exp_id, {"series": SERIES_B})
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "already_answered"
    assert body["keys"] == ["series"]
    assert body["experiment_id"] == exp_id
    assert body["run_id"] == run_id
    assert body["answer_at"] == _EDIT_RUN

    # The two false claims are gone, not reworded: there is no `invalidation` at all.
    assert "invalidation" not in body
    assert "identical" not in body["message"]

    # Nothing written, nothing moved.
    assert _stored_series(exp_id, run_id)[0]["series_id"] == "race-a"
    assert ws.load_experiment(exp_id).runs[0].version_token() == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("series", SERIES_B),
        ("qc", {"status": "compromised", "evidence": "Beam dropped during scan 3."}),
        ("descriptor", {**DESCRIPTOR, "value": 9002.7}),
    ],
)
def test_every_run_level_key_measured_before_the_fix_is_refused(client, key, value):
    exp_id, run_id = _run_with_answers(client)
    refused = _answer_run(client, exp_id, {key: value})
    assert refused.status_code == 422, refused.text
    assert refused.json()["keys"] == [key], refused.json()


def test_the_record_route_with_no_runs_is_refused_and_points_at_the_records_edit(client):
    """The same defect at the record level, with the RECORD's edit operation named."""
    exp_id = _record_with_answers(client)
    refused = _answer(client, exp_id, {"series": SERIES_B})
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "already_answered"
    assert body["answer_at"] == _EDIT_RECORD
    assert "run_id" not in body
    assert _stored_series(exp_id)[0]["series_id"] == "race-a"


def test_a_stored_asset_re_answered_with_a_different_sha_is_refused(tutorial):
    """The FIFTH measured combination, and the one closest to the defect the
    correction route already fixed: `_answers_to_apply_shape`'s docstring records the
    identical `200`/"identical" pair for a pending asset uri on `/edit`."""
    exp_id = ws.SEED_NEW_DRAFT_ID
    uri = next(
        q["id"]
        for q in tutorial.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
        if q["kind"] == "asset"
    )
    assert _answer(tutorial, exp_id, {uri: "a" * 64}).status_code == 200

    refused = _answer(tutorial, exp_id, {uri: "b" * 64})
    assert refused.status_code == 422, refused.text
    assert refused.json()["keys"] == [uri], refused.json()
    stored = next(
        a for a in ws.load_experiment(exp_id, session_id=tutorial.tutorial_session_id).draft["assets"]
        if a["uri"] == uri
    )
    assert stored["sha256"] == "a" * 64


def test_the_refusal_names_every_offending_key_not_the_first(client):
    exp_id, _ = _run_with_answers(client)
    refused = _answer_run(
        client,
        exp_id,
        {"series": SERIES_B, "qc": {"status": "compromised", "evidence": "Beam dropped."}},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["keys"] == ["qc", "series"], refused.json()


# --- what must NOT be refused -------------------------------------------------


def test_resubmitting_the_identical_value_is_still_a_success(client):
    """THE IDEMPOTENT RETRY. A first draft of the refusal broke this.

    A client that is unsure a request landed may repeat it. Here the "the submitted
    value was identical" sentence is TRUE, so the `200` is honest and stays.
    """
    exp_id, run_id = _run_with_answers(client)
    before = ws.load_experiment(exp_id).runs[0].version_token()

    again = _answer_run(client, exp_id, {"series": SERIES_A, "descriptor": DESCRIPTOR, "qc": QC})
    assert again.status_code == 200, again.text
    assert again.json()["invalidation"]["changed"] is False
    assert "identical" in again.json()["invalidation"]["reason"]
    assert ws.load_experiment(exp_id).runs[0].version_token() == before
    assert _stored_series(exp_id, run_id)[0]["series_id"] == "race-a"


def test_resubmitting_the_identical_value_at_record_level_is_still_a_success(client):
    exp_id = _record_with_answers(client)
    again = _answer(client, exp_id, {"series": SERIES_A, "descriptor": DESCRIPTOR, "qc": QC})
    assert again.status_code == 200, again.text
    assert again.json()["invalidation"]["changed"] is False


def test_answering_an_open_question_is_untouched(client):
    """The ordinary, correct use of the route. The closed-state check comes first
    precisely so this cannot be caught by the probe."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    applied = _answer(client, exp_id, {"series": SERIES_B, "descriptor": DESCRIPTOR, "qc": QC})
    assert applied.status_code == 200, applied.text
    assert applied.json()["pending"] == []
    assert _stored_series(exp_id)[0]["series_id"] == "race-b"


def test_edge_is_still_answerable_on_a_record_that_has_runs(client):
    """`edge` IS EXCLUDED STRUCTURALLY, and the record operation's own response
    documentation promises it: it lives in the record's implicit derivations, which
    every non-diverging run inherits. It corresponds to no blocker, so "closed" is
    not a state it can be in — and a probe over the writer's key set (rather than
    over `_CORRECTABLE_KEY_KINDS`) would have refused it.

    **INVERTED, NOT DELETED, 2026-08-24.** This test asserted `200` on a record built by
    `POST /api/experiments`, which has no `implicit` block at all — so it was pinning the
    status code of a write that could not happen. `complete.apply_answers` writes `edge`
    only INTO an existing `implicit[]` entry, and the response carried the same
    "identical; nothing was invalidated" reason this whole file exists to remove, for the
    one key the file did not cover. The record is now given a real edge derivation, so
    the property the docstring claims — that `edge` survives the closed-question probe —
    is measured against a record where answering it does something.
    """
    exp_id, _ = _run_with_answers(client)
    exp = ws.load_experiment(exp_id)
    exp.draft.setdefault("implicit", []).append(
        {"about": "edge", "value": None, "evidence": [{"source_type": "derivation", "rule": "ci"}]}
    )
    exp.save()
    applied = _answer(client, exp_id, {"edge": "K"})
    assert applied.status_code == 200, applied.text
    stored = ws.load_experiment(exp_id).draft.get("implicit") or []
    assert [e["value"] for e in stored if e.get("about") == "edge"] == ["K"], stored


def test_edge_with_no_derivation_gets_the_SIXTH_false_identical_claim_removed(client):
    """THE KEY THIS FILE MISSED, and it is the same defect in the same sentence.

    The five combinations in the module docstring were fixed by `already_answered`, which
    is a statement about the QUESTION's state. `edge` has no question, so that refusal
    could never see it — and on a record with no `implicit` block the answer was dropped
    and reported as `changed: false`, reason *"the submitted value was identical; nothing
    was invalidated"*. Neither half was true.

    It is `422 no_derivation_to_confirm` rather than `already_answered` because nothing
    was ever answered: the record holds no edge derivation to confirm. See
    `routes._refuse_edge_with_nothing_to_confirm` for why refusing is the right choice
    against the no-guessing rule and against what the official record can carry.
    """
    exp_id, _ = _run_with_answers(client)
    refused = _answer(client, exp_id, {"edge": "K"})
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "no_derivation_to_confirm"
    assert "identical" not in body["message"]


def test_a_bare_descriptor_label_is_not_refused_and_names_no_edit_route(client):
    """It falls out of the probe on its own, and that is the desired answer.

    `apply_corrections` gates the whole descriptor block on `descriptor is not None`,
    so a label with no descriptor changes nothing. Both edit operations answer a bare
    label `422 unrecognized_field` (asserted here, at both levels), so a refusal that
    sent it to `/edit` would be the misdirection defect
    `_refuse_correcting_an_unanswered_key` was written to avoid.
    """
    exp_id = _record_with_answers(client)
    assert _answer(client, exp_id, {"descriptor_label": "relabel"}).status_code == 200
    refused = _edit(client, exp_id, {"descriptor_label": "relabel"})
    assert refused.status_code == 422
    assert refused.json()["error"] == "unrecognized_field"


def test_an_unrecognised_key_is_still_ignored_rather_than_refused(client):
    exp_id = _record_with_answers(client)
    assert _answer(client, exp_id, {"totally_made_up_field": "x"}).status_code == 200


def test_a_run_level_key_on_a_record_with_runs_still_gets_the_run_level_refusal(client):
    """ORDER MATTERS, and this pins it. `belongs_to_a_run` is the strictly more useful
    answer — it names the RUN's answers operation — so it must win over
    `already_answered`, whose "here" would be a level that no longer owns the value."""
    exp_id, run_id = _run_with_answers(client)
    refused = _answer(client, exp_id, {"series": SERIES_B})
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "belongs_to_a_run"
    assert refused.json()["runs"][0]["run_id"] == run_id


# --- the redirect actually works ----------------------------------------------


def test_the_operation_named_in_answer_at_accepts_the_very_value_that_was_refused(client):
    """THE PROPERTY A REFUSAL MUST HAVE. `_refuse_correcting_an_unanswered_key`'s
    docstring: "a refusal that misdirects is worse than one that says nothing: it
    spends the caller's retry and reads as authoritative while doing it."

    Here it is provable rather than plausible — a key is refused only if
    `apply_corrections` would write it, which satisfies every gate on the edit route.
    Asserted end to end at both levels rather than argued.
    """
    exp_id, run_id = _run_with_answers(client)
    refused = _answer_run(client, exp_id, {"series": SERIES_B})
    assert refused.status_code == 422
    assert refused.json()["answer_at"] == _EDIT_RUN

    run = ws.load_experiment(exp_id).runs[0]
    corrected = client.post(
        f"/api/experiments/{exp_id}/runs/{run.id}/edit",
        json={"answers": {"series": SERIES_B}, "confirmed_by_user": True},
        headers={"If-Match": f'"{run.version_token()}"'},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["invalidation"]["changed"] is True
    assert _stored_series(exp_id, run_id)[0]["series_id"] == "race-b"


def test_the_record_level_redirect_also_accepts_the_refused_value(client):
    exp_id = _record_with_answers(client)
    refused = _answer(client, exp_id, {"series": SERIES_B})
    assert refused.json()["answer_at"] == _EDIT_RECORD
    corrected = _edit(client, exp_id, {"series": SERIES_B})
    assert corrected.status_code == 200, corrected.text
    assert _stored_series(exp_id)[0]["series_id"] == "race-b"


# --- the two refusals are exact mirrors ---------------------------------------


def test_the_two_refusals_point_at_each_other(client):
    """`not_yet_answered` sends an OPEN key to `/answers`; `already_answered` sends a
    CLOSED key to `/edit`. Neither may exist without the other, and a client following
    either must not be bounced back."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]

    open_key = _edit(client, exp_id, {"series": SERIES_A})
    assert open_key.status_code == 422, open_key.text
    assert open_key.json()["error"] == "not_yet_answered"
    assert open_key.json()["answer_at"] == "POST /api/experiments/{experiment_id}/answers"

    assert _answer(client, exp_id, {"series": SERIES_A}).status_code == 200

    closed_key = _answer(client, exp_id, {"series": SERIES_B})
    assert closed_key.status_code == 422, closed_key.text
    assert closed_key.json()["error"] == "already_answered"
    assert closed_key.json()["answer_at"] == _EDIT_RECORD


def test_the_refusal_is_declared_in_the_published_contract(client):
    """`_R_NOT_YET_ANSWERED` was DEAD for its whole life — emitted by a route whose
    `responses={...}` never mentioned it, so no machine client that reads the contract
    before calling could know it existed. Both answers operations now declare this one,
    and the framework's `HTTPValidationError` ref survives the declaration."""
    spec = client.get("/api/openapi").json()
    for path in (
        "/api/experiments/{experiment_id}/answers",
        "/api/experiments/{experiment_id}/runs/{run_id}/answers",
    ):
        described = spec["paths"][path]["post"]["responses"]["422"]
        assert "already_answered" in described["description"], path
        assert (
            described["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/HTTPValidationError"
        ), path


# --- known limit, asserted rather than left unsaid ----------------------------


def test_an_unusable_value_on_a_closed_question_is_a_documented_known_limit(client):
    """NOT FIXED BY THIS SLICE, and pinned so it cannot be mistaken for fixed.

    `apply_corrections` declines a value it cannot store, so the probe sees no change
    and the request proceeds to the old `200`. This is the route's unusable-value
    doctrine (`_correction_is_storable` / `invalid_field_value`), a different rule at a
    different layer; adopting it here would also change what an unusable answer to an
    OPEN question does, where the returned `pending` list already tells the caller the
    answer did not land.

    If a later slice closes it, THIS TEST SHOULD GO RED and be inverted — which is this
    repository's established remedy for a test that pins a defect.
    """
    exp_id = _record_with_answers(client)
    absorbed = _answer(client, exp_id, {"qc": {"status": "not-an-enum-value"}})
    assert absorbed.status_code == 200, absorbed.text
    assert absorbed.json()["invalidation"]["changed"] is False
    assert ws.load_experiment(exp_id).draft["qc"]["status"] == "valid"

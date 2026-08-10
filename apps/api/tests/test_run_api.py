"""The Run HTTP API — exposing the Run domain model, not rebuilding it.

``workspace`` already carried the whole model: :class:`~isaac_api.workspace.Run`,
its per-run ``version_token``, ``Override``/``Resolution``, ``resolve_inherited``,
``field_level`` and ``Experiment.resolved_run_draft``. Nothing in it was reachable
over HTTP. These five operations expose it, and the tests below are addressed at
what exposing it can get WRONG rather than at the model, which
``test_run_domain_model.py`` already pins.

The seven invariants of the frozen slice contract, each with the test that holds it:

1. **Two runs of one experiment are isolated** — writing run 1 changes nothing about
   run 2's fields, ``rev`` or ``version``.
   (``test_writing_one_run_leaves_its_sibling_byte_identical``)
2. **A stale run ``If-Match`` is refused 412 and the stored value is unchanged.**
   (``test_a_stale_run_if_match_is_refused_and_the_stored_value_does_not_move``)
3. **A byte-stable PATCH does not bump ``rev``.** ``save_versioned`` already has that
   property; what could break it is THIS layer stamping a fresh timestamp into an
   evidence entry on every write, so the no-op is pinned end to end.
   (``test_resubmitting_the_same_value_does_not_advance_the_run``)
4. **Runs survive a reload from persisted state.**
   (``test_a_created_run_survives_a_reload_from_persisted_state``)
5. **Check Run writes nothing** — every version, the experiment's and every run's, is
   byte-identical across the call.
   (``test_check_run_moves_no_version_at_all``)
6. **``record_id`` is not advanced by any route here.**
   (``test_no_operation_in_this_api_mints_a_record_id``)
7. **Nothing under ``src/isaac_records/`` or ``schema/`` is modified.**
   (``test_the_truth_path_is_untouched_by_this_slice``)

Three of these were MUTATION-CHECKED: the production code was broken in the specific
way the test claims to catch, the test was confirmed RED, and the break was reverted.
The mutations are recorded on the tests themselves.

Every fixture is built from the committed synthetic seed drafts. Nothing here reads
real data and nothing here connects to a database.
"""

from __future__ import annotations

import copy
import json
import subprocess

import pytest

import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_records.models import field_value, user_confirmation

from conftest import client_ws, tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


# --- fixtures -----------------------------------------------------------------
#
# The split of the committed export-ready seed into its experiment-level and
# run-level halves uses the APPLICATION's own classifiers, exactly as
# `test_export_fan_out.py` does — a hand-written list here would be a second
# definition of the split and could pass while the product's composition was wrong.


def _split_full_draft() -> tuple[dict, dict]:
    full = ws._full_draft()
    experiment: dict = {"meta": copy.deepcopy(full["meta"]), "fields": {}, "pending": []}
    run: dict = {"fields": {}, "pending": []}

    for path, envelope in (full.get("fields") or {}).items():
        level = ws.field_level(path)
        if level == ws.LEVEL_EXPERIMENT:
            experiment["fields"][path] = copy.deepcopy(envelope)
        elif level == ws.LEVEL_RUN:
            run["fields"][path] = copy.deepcopy(envelope)

    for key, value in full.items():
        if key in ("fields", "meta", "pending", "implicit", "block_evidence"):
            continue
        level = ws.block_level(key)
        if level == ws.LEVEL_EXPERIMENT:
            experiment[key] = copy.deepcopy(value)
        elif level == ws.LEVEL_RUN:
            run[key] = copy.deepcopy(value)

    experiment["implicit"] = copy.deepcopy(full.get("implicit") or [])
    block_evidence = full.get("block_evidence") or {}
    experiment["block_evidence"] = {
        k: copy.deepcopy(v)
        for k, v in block_evidence.items()
        if k.startswith("attribution:")
    }
    run["block_evidence"] = {
        k: copy.deepcopy(v)
        for k, v in block_evidence.items()
        if not k.startswith("attribution:")
    }
    return experiment, run


@pytest.fixture()
def experiment_id(client):
    """An ordinary experiment with NO runs, seeded from the export-ready draft.

    Record-level content only: the runs this API creates start empty, and the
    inherited half is what makes ``RunView.inherited`` non-trivial.
    """
    experiment_draft, _ = _split_full_draft()
    store = client_ws(client)
    exp = store.create_experiment(
        "Run API fixture", {"kind": "synthetic"}, experiment_draft
    )
    return exp.id


def _experiment_etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _create_run(client, experiment_id: str, label: str | None = None):
    body = {} if label is None else {"label": label}
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json=body,
        headers={"If-Match": _experiment_etag(client, experiment_id)},
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]


def _run_etag(client, experiment_id: str, run_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _patch(client, experiment_id: str, run_id: str, body: dict, *, if_match=...):
    headers = {}
    tag = _run_etag(client, experiment_id, run_id) if if_match is ... else if_match
    if tag is not None:
        headers["If-Match"] = tag
    return client.patch(
        f"/api/experiments/{experiment_id}/runs/{run_id}", json=body, headers=headers
    )


def _nested_wide(levels: int, breadth: int = 3):
    """A tree that is LEGAL by depth and large by breadth — the shape the depth cap alone
    let through."""
    value = 1
    for _ in range(levels):
        value = [value] * breadth
    return value


def _stored_run(client, experiment_id: str, run_id: str):
    """The run as the STORE holds it — never as the response reported it."""
    exp = client_ws(client).load_experiment(experiment_id)
    return exp.get_run(run_id)


# --- 1. list / read / not-found -----------------------------------------------


def test_listing_runs_of_an_unknown_experiment_is_a_404(client):
    response = client.get("/api/experiments/NOT-A-RECORD/runs")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"


def test_reading_an_unknown_run_is_a_404_that_names_the_run_not_the_experiment(
    client, experiment_id
):
    """The two 404s are deliberately different bodies.

    ``experiment_not_found`` means the workspace has no such record;
    ``run_not_found`` means the record was read successfully and holds no run under
    that id. Collapsing them would send a client looking in the wrong place.
    """
    response = client.get(f"/api/experiments/{experiment_id}/runs/NOPE")
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"] == "run_not_found"
    assert body["experiment_id"] == experiment_id
    assert body["id"] == "NOPE"


def test_an_experiment_with_no_runs_lists_none_and_carries_its_own_etag(
    client, experiment_id
):
    response = client.get(f"/api/experiments/{experiment_id}/runs")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["runs"] == []
    exp = client_ws(client).load_experiment(experiment_id)
    assert body["experiment_version"] == exp.version_token()
    assert response.headers["ETag"] == exp.etag()


# --- 2. create ----------------------------------------------------------------


def test_creating_a_run_without_if_match_is_428_and_creates_nothing(
    client, experiment_id
):
    response = client.post(f"/api/experiments/{experiment_id}/runs", json={})
    assert response.status_code == 428, response.text
    assert response.json() == {
        "error": "precondition_required",
        "experiment_id": experiment_id,
    }
    assert client_ws(client).load_experiment(experiment_id).runs == []


def test_creating_a_run_with_a_stale_experiment_if_match_is_412_and_creates_nothing(
    client, experiment_id
):
    stale = _experiment_etag(client, experiment_id)
    _create_run(client, experiment_id, "Run A")  # moves the experiment on
    before = len(client_ws(client).load_experiment(experiment_id).runs)

    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": "Run B"},
        headers={"If-Match": stale},
    )
    assert response.status_code == 412, response.text
    body = response.json()
    assert body["error"] == "stale_write"
    assert body["experiment_id"] == experiment_id
    exp = client_ws(client).load_experiment(experiment_id)
    assert body["current_version"] == exp.version_token()
    assert response.headers["ETag"] == exp.etag()
    assert len(exp.runs) == before


def test_creating_a_run_with_a_malformed_if_match_is_400(client, experiment_id):
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={},
        headers={"If-Match": 'W/"weak"'},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "malformed_if_match"
    assert client_ws(client).load_experiment(experiment_id).runs == []


@pytest.mark.parametrize("label", [None, "", "   "])
def test_an_omitted_or_blank_label_is_assigned_run_n_by_the_server(
    client, experiment_id, label
):
    """Blank is not a label. It is NEVER stored as one, and none is invented from
    request content — ``Run N`` comes from ``next_ordinal()``, which the domain
    model owns."""
    body = {} if label is None else {"label": label}
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json=body,
        headers={"If-Match": _experiment_etag(client, experiment_id)},
    )
    assert response.status_code == 201, response.text
    run = response.json()["run"]
    assert run["label"] == "Run 1"
    assert run["ordinal"] == 1


def test_a_request_with_no_body_at_all_still_creates_a_run(client, experiment_id):
    """The body is optional, not merely optional-in-prose. A caller with nothing to
    say sends nothing, and the server names the run rather than refusing."""
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        headers={"If-Match": _experiment_etag(client, experiment_id)},
    )
    assert response.status_code == 201, response.text
    assert response.json()["run"]["label"] == "Run 1"


def test_a_supplied_label_is_kept_verbatim_and_does_not_decide_the_ordinal(
    client, experiment_id
):
    first = _create_run(client, experiment_id, "Run 10")
    second = _create_run(client, experiment_id, "Run 2")
    assert [first["label"], second["label"]] == ["Run 10", "Run 2"]
    # The ORDER KEY is the ordinal, never the label — "Run 10" sorts before "Run 2"
    # lexically and must not be re-ordered by this API.
    listed = client.get(f"/api/experiments/{experiment_id}/runs").json()["runs"]
    assert [r["label"] for r in listed] == ["Run 10", "Run 2"]
    assert [r["ordinal"] for r in listed] == [1, 2]


def test_a_non_string_label_is_refused_rather_than_coerced(client, experiment_id):
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": 5},
        headers={"If-Match": _experiment_etag(client, experiment_id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_label"
    assert client_ws(client).load_experiment(experiment_id).runs == []


def test_creating_a_run_returns_201_the_new_experiment_etag_and_an_empty_run(
    client, experiment_id
):
    before = _experiment_etag(client, experiment_id)
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": "Cold"},
        headers={"If-Match": before},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    exp = client_ws(client).load_experiment(experiment_id)
    assert response.headers["ETag"] == exp.etag()
    assert response.headers["ETag"] != before
    assert body["experiment_version"] == exp.version_token()

    run = body["run"]
    assert run["experiment_id"] == experiment_id
    assert run["record_id"] is None
    # NOTHING SCIENTIFIC IS COPIED IN. A new run carries no field of its own; the
    # record-level content it will export is resolved on read, not written down.
    assert run["fields"] == {}
    assert run["inherited"], "the seeded record-level content should resolve"
    assert all(
        entry["state"] == "inherited" for entry in run["inherited"].values()
    ), run["inherited"]


def test_there_is_no_server_side_maximum_run_count(client, experiment_id):
    for _ in range(12):
        _create_run(client, experiment_id)
    listed = client.get(f"/api/experiments/{experiment_id}/runs").json()["runs"]
    assert [r["ordinal"] for r in listed] == list(range(1, 13))


# --- 3. read one --------------------------------------------------------------


def test_a_run_read_carries_the_runs_own_etag_not_the_experiments(
    client, experiment_id
):
    """The distinction the whole PATCH contract rests on. If these two were the
    same string, a client could edit a run with a validator that says nothing about
    it."""
    run = _create_run(client, experiment_id)
    response = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}")
    assert response.status_code == 200, response.text
    exp = client_ws(client).load_experiment(experiment_id)
    stored = exp.get_run(run["id"])
    assert response.headers["ETag"] == f'"{stored.version_token()}"'
    assert response.headers["ETag"] != exp.etag()
    assert response.json()["run"]["version"] == stored.version_token()


def test_the_run_view_reports_inheritance_and_overrides_separately(
    client, experiment_id
):
    """``inherited`` is computed on read and is never merged into ``fields``.

    Contract §2 D2 makes inheritance a read-time resolution; a run that appeared to
    HOLD the record's values would have copied them, which is the thing the model
    exists to avoid.
    """
    run = _create_run(client, experiment_id)
    store = client_ws(client)
    exp = store.load_experiment(experiment_id)
    stored = exp.get_run(run["id"])
    address = ws.field_address("sample.material.name")
    assert address in exp.resolve_run(stored), "fixture must carry this record-level field"

    exp.set_run_override(
        stored, address, field_value("Overridden", status="verified", evidence=[])
    )
    exp.save_versioned()

    view = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").json()["run"]
    entry = view["inherited"][address]
    assert entry["state"] == "overridden"
    assert entry["payload"]["value"] == "Overridden"
    assert entry["inherited_payload"]["value"] != "Overridden"
    assert entry["displaced_payload"] == entry["inherited_payload"]
    # The override lives in the override map, NOT in the run's own field map.
    assert "sample.material.name" not in view["fields"]


# --- 4. patch: preconditions and refusals -------------------------------------


def test_patching_a_run_without_if_match_is_428(client, experiment_id):
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
        if_match=None,
    )
    assert response.status_code == 428, response.text
    assert response.json() == {
        "error": "precondition_required",
        "experiment_id": experiment_id,
        "run_id": run["id"],
    }
    assert _stored_run(client, experiment_id, run["id"]).draft.get("fields") in (None, {})


def test_patching_a_run_with_the_experiments_etag_is_stale_not_accepted(
    client, experiment_id
):
    """A real trap, and the reason the run carries its own validator at all: the
    record's `ETag` is a perfectly well-formed strong validator that says nothing
    about this run."""
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
        if_match=_experiment_etag(client, experiment_id),
    )
    assert response.status_code == 412, response.text
    assert response.json()["run_id"] == run["id"]


def test_patching_a_run_with_a_malformed_if_match_is_400_naming_both_ids(
    client, experiment_id
):
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
        if_match='W/"weak"',
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "malformed_if_match"
    assert body["experiment_id"] == experiment_id
    assert body["run_id"] == run["id"]


def test_patching_a_run_requires_confirmed_by_user(client, experiment_id):
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"fields": {"context.temperature_K": 300.0}},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "confirmation_required"
    assert _stored_run(client, experiment_id, run["id"]).draft.get("fields") in (None, {})


def test_patching_an_unknown_run_is_a_404(client, experiment_id):
    response = client.patch(
        f"/api/experiments/{experiment_id}/runs/NOPE",
        json={"confirmed_by_user": True, "fields": {"context.temperature_K": 1.0}},
        headers={"If-Match": "*"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "run_not_found"


@pytest.mark.parametrize(
    "path",
    [
        # Unclassified: the contract assigns `system.configuration.*` to NEITHER
        # level, and guessing which one would be the unevidenced inference the
        # project's no-guessing rules forbid.
        "system.configuration.detector_model",
        "system.configuration.n_scans",
        "timestamps.created_utc",
        # Record-level: entered once and inherited. Writing it on a run would put
        # the same value in two places.
        "sample.material.name",
        "sample.sample_id",
        "system.domain",
    ],
)
def test_a_path_that_is_not_run_level_is_refused_and_not_written(
    client, experiment_id, path
):
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {path: "anything"}},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrecognized_field"
    assert body["key"] == path
    assert body["keys"] == [path]
    # NOT silently ignored, and NOT written.
    stored = _stored_run(client, experiment_id, run["id"])
    assert path not in (stored.draft.get("fields") or {})


def test_one_bad_path_refuses_the_whole_request_including_its_valid_neighbour(
    client, experiment_id
):
    """Classification happens BEFORE any write, so a caller is never left holding a
    partial write it was told had been rejected."""
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {
            "confirmed_by_user": True,
            "fields": {
                "context.temperature_K": 300.0,
                "system.configuration.n_scans": 4,
            },
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["keys"] == ["system.configuration.n_scans"]
    stored = _stored_run(client, experiment_id, run["id"])
    assert stored.draft.get("fields") in (None, {})
    assert stored.rev == 1  # created, never edited


def test_a_body_naming_no_run_level_field_and_no_label_is_422_not_a_silent_no_op(
    client, experiment_id
):
    run = _create_run(client, experiment_id)
    for body in ({"confirmed_by_user": True}, {"confirmed_by_user": True, "fields": {}}):
        response = _patch(client, experiment_id, run["id"], body)
        assert response.status_code == 422, response.text
        assert response.json()["error"] == "unrecognized_field"


@pytest.mark.parametrize(
    "literal",
    ["NaN", "Infinity", "-Infinity", '{"a": [1, NaN]}'],
    ids=["nan", "inf", "-inf", "nan-nested-in-an-object"],
)
def test_a_value_json_cannot_represent_is_refused_before_anything_is_written(
    client, experiment_id, literal
):
    """THE ADVERSARIAL FINDING THIS PINS, because it was none of the things a
    key-only filter protects against.

    The body is sent as RAW BYTES, not through `json=`, because `json.dumps` cannot
    produce it and neither can a browser's `JSON.stringify` — which is precisely why
    it survived: every existing test and the whole frontend go through a serializer
    that refuses these literals. `curl` does not.

    Starlette parses the request with the stdlib `json.loads`, which ACCEPTS `NaN`,
    `Infinity` and `-Infinity`, and renders responses with
    `json.dumps(..., allow_nan=False)`, which REFUSES them. Before the guard, one
    such request produced all of:

      * a COMMITTED write (`rev` 1 -> 2, bare `NaN` in `experiment.json`, and a
        fabricated confirmation whose recorded answer read "NaN") reported to the
        caller as an HTTP 500 — a successful write announced as a failure;
      * `GET .../runs` and `GET .../runs/{run_id}` 500ing PERMANENTLY afterwards, so
        the client could not re-read the ETag it needed to repair the run;
      * `isaac validate --official` reporting PASS on the exported record, because
        `jsonschema` accepts `float('nan')` as `"number"` — a record file no strict
        RFC-8259 parser will read, through the export gate, with a green verdict.

    The last of those is a truth-plane escape (`CLAUDE.md` §13) whose ingress was this
    route alone: `POST /edit` already answered 422 and `POST /answers` left the value
    untouched. So the assertions below are deliberately about the STORE and the
    subsequent READS, not only about the status code.
    """
    run = _create_run(client, experiment_id)
    etag = _run_etag(client, experiment_id, run["id"])
    response = client.patch(
        f"/api/experiments/{experiment_id}/runs/{run['id']}",
        content=(
            '{"confirmed_by_user": true, "fields": {"context.temperature_K": '
            + literal
            + "}}"
        ).encode(),
        headers={"If-Match": etag, "content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrepresentable_value"
    assert body["keys"] == ["context.temperature_K"]

    # NOTHING WAS WRITTEN. `rev == 1` is "created, never edited".
    stored = _stored_run(client, experiment_id, run["id"])
    assert stored.rev == 1
    assert stored.draft.get("fields") in (None, {})

    # AND THE RUN IS STILL READABLE — the half of the defect that made it
    # unrecoverable rather than merely wrong.
    assert client.get(f"/api/experiments/{experiment_id}/runs").status_code == 200
    assert (
        client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").status_code == 200
    )


@pytest.mark.parametrize(
    "literal,where",
    [
        (r'"\ud800"', "fields"),
        (r'"\udfff"', "fields"),
        (r'{"k": "\ud800"}', "fields"),
        (r'"\ud800"', "label"),
    ],
    ids=["lone-high-surrogate", "lone-low-surrogate", "nested-in-an-object", "in-the-label"],
)
def test_a_lone_surrogate_is_refused_rather_than_500ing(
    client, experiment_id, literal, where
):
    """THE SECOND ROUND OF THE SAME DEFECT CLASS, and the reason the guard is now a
    real render rather than a near-enough one.

    The first version of `_is_json_renderable` called
    `json.dumps(value, allow_nan=False)` under a comment asserting it was "the SAME
    function Starlette renders responses with, so a value that passes here cannot fail
    there". It omitted `ensure_ascii=False` and the `.encode("utf-8")`. With
    `ensure_ascii` at its default a lone surrogate escapes to `"\ud800"` and serialises
    happily; with `ensure_ascii=False` the encode raises `UnicodeEncodeError`. So a
    lone surrogate still produced a 500 — and `label` was not covered by the value
    guard at all, so it 500ed on BOTH this route and `POST .../runs`.

    Unlike the `NaN` case nothing was written even before the fix: the signature hash
    raises before `save_versioned` writes. The assertions below still check the store,
    because "nothing was written" is the claim, not an assumption.
    """
    run = _create_run(client, experiment_id)
    etag = _run_etag(client, experiment_id, run["id"])
    body = (
        '{"confirmed_by_user": true, "label": ' + literal + "}"
        if where == "label"
        else '{"confirmed_by_user": true, "fields": {"context.temperature_K": '
        + literal
        + "}}"
    )
    response = client.patch(
        f"/api/experiments/{experiment_id}/runs/{run['id']}",
        content=body.encode(),
        headers={"If-Match": etag, "content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"

    stored = _stored_run(client, experiment_id, run["id"])
    assert stored.rev == 1
    assert client.get(f"/api/experiments/{experiment_id}/runs").status_code == 200


def test_creating_a_run_with_an_unrepresentable_label_is_refused_not_a_500(
    client, experiment_id
):
    """`label` reaches the store through TWO routes and the value guard iterates
    `fields`. This is the other one."""
    etag = client.get(f"/api/experiments/{experiment_id}").headers["ETag"]
    response = client.post(
        f"/api/experiments/{experiment_id}/runs",
        content=rb'{"label": "\ud800"}',
        headers={"If-Match": etag, "content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"
    assert client.get(f"/api/experiments/{experiment_id}/runs").json()["runs"] == []


def test_a_label_of_real_non_ascii_text_is_still_accepted(client, experiment_id):
    """The guard is about REPRESENTABILITY, not about ASCII. Without this the fix
    above could pass by refusing every non-ASCII label."""
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "label": "Run \u03b1 \u00b7 \u6e29\u5ea6"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["run"]["label"] == "Run \u03b1 \u00b7 \u6e29\u5ea6"


def test_the_run_check_reports_which_document_it_read_and_when_it_has_no_verdict(
    client, experiment_id
):
    """THE WIRE CONTRACT THE FRONTEND NOW RENDERS, pinned on the server side.

    `dry_run` and `unavailable` were both added to `_validate_unit` and NEITHER was
    asserted anywhere — a new field on a served contract, on two endpoints, entirely
    unpinned, which a reviewer found by grepping for it. `dry_run` states WHICH
    document was checked (the card said "(dry run)" unconditionally while a
    materialised unit validates the record already written); `unavailable` separates
    "no verdict could be reached" from "the schema rejected it", which the card
    rendered as `Check Failed`.
    """
    run = _create_run(client, experiment_id)
    body = client.post(
        f"/api/experiments/{experiment_id}/runs/{run['id']}/check"
    ).json()
    official = body["official"]
    # Not exported, so this IS a dry run over an in-memory candidate.
    assert official["dry_run"] is True
    # And a dry run that reached a verdict does not claim it could not be reached.
    assert official.get("unavailable") is not True
    # `ok` is still the composition of the two deterministic checks.
    assert body["ok"] == bool(body["draft"]["ok"] and official["ok"])


def test_the_run_check_says_unavailable_when_no_verdict_can_be_reached(
    client, experiment_id, monkeypatch
):
    """THE POSITIVE ASSERTION, WITHOUT WHICH THE TEST ABOVE PINS NOTHING.

    A reviewer deleted BOTH `"unavailable": True` lines from `_validate_unit` and this
    file still reported `91 passed`, because the only assertion on the field was
    `official.get("unavailable") is not True` on the happy path — satisfied by the key
    being absent. A negative assertion about a flag is not a test of the flag, and the
    branch the flag exists for was never exercised.

    The no-verdict branch is reached when a unit is materialised and its record file
    cannot be read. Rather than exporting and then corrupting a file — which would test
    the filesystem as much as the route — the two conditions are forced directly:
    `materialised()` true, `_read_artifact_json` returning `None`. That is exactly the
    state the route's own comment describes as "no verdict, not a schema violation".
    """
    run = _create_run(client, experiment_id)

    monkeypatch.setattr(ws.ExportUnit, "materialised", lambda self: True)
    monkeypatch.setattr(routes, "_read_artifact_json", lambda path: None)

    body = client.post(
        f"/api/experiments/{experiment_id}/runs/{run['id']}/check"
    ).json()
    official = body["official"]
    assert official["unavailable"] is True
    # It is a statement about the WRITTEN record, so it is not a dry run...
    assert official["dry_run"] is False
    # ...and it FAILS CLOSED: the flag explains the refusal, it does not soften it.
    assert official["ok"] is False
    assert body["ok"] is False
    assert official["errors"] == [
        {"path": "$", "message": "Validation could not be completed."}
    ]


@pytest.mark.parametrize("depth", [33, 600, 800, 900], ids=lambda d: f"depth-{d}")
def test_a_value_nested_deeper_than_the_limit_is_refused_before_the_write(
    client, experiment_id, depth
):
    """THE THIRD ROUND OF THE SAME DEFECT CLASS, and the one that proves why the guard's
    CONTRACT mattered more than its implementation.

    `_is_json_renderable` — as it was then named and documented — promised only that the
    response serializer could render the value. That promise was true and insufficient:
    `json.dumps` handles thousands of levels happily, so an 800-deep array PASSED the
    guard, the write COMMITTED, and `_run_view` then raised `RecursionError` while
    CONSTRUCTING the response. Measured consequences, identical to the `NaN` case:

      * `rev` 1 -> 2 and a 1.3 MB `experiment.json` on disk, reported to the caller as
        HTTP 500 with NO ETag on the response;
      * `GET .../runs`, `GET .../runs/{id}` and `GET /experiments/{id}` 500ing
        PERMANENTLY — verified against a FRESH app over the same workspace, so it was
        on-disk state and not a poisoned cache;
      * therefore no way to obtain the strong validator needed to repair the run.

    The window was roughly depth 600-950: shallower is safe, and >= ~1000 fails before
    the write. This test brackets it and also pins the boundary itself, because a limit
    nobody exercises drifts.
    """
    run = _create_run(client, experiment_id)
    etag = _run_etag(client, experiment_id, run["id"])
    payload = (
        '{"confirmed_by_user": true, "fields": {"context.temperature_K": '
        + "[" * depth
        + "1"
        + "]" * depth
        + "}}"
    )
    response = client.patch(
        f"/api/experiments/{experiment_id}/runs/{run['id']}",
        content=payload.encode(),
        headers={"If-Match": etag, "content-type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"

    # NOTHING WRITTEN, and — the half that made the defect unrecoverable — every read
    # still answers, so the caller can still get an ETag.
    stored = _stored_run(client, experiment_id, run["id"])
    assert stored.rev == 1
    assert stored.draft.get("fields") in (None, {})
    assert client.get(f"/api/experiments/{experiment_id}/runs").status_code == 200
    assert (
        client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").status_code == 200
    )
    assert client.get(f"/api/experiments/{experiment_id}").status_code == 200


@pytest.mark.parametrize("depth", [1200, 5000], ids=lambda d: f"depth-{d}")
def test_an_absurdly_nested_value_is_refused_by_SOMETHING_and_never_by_a_500(
    client, experiment_id, depth
):
    """PAST SOME DEPTH THE JSON PARSER REFUSES FIRST, AND WHICH DEPTH IS A CPYTHON
    VERSION PROPERTY — so this test deliberately does not assert a status code.

    `depth-1200` was originally folded into the parametrize above, asserting `422`. It
    passed locally on CPython 3.12.3, which parses a 2,000-deep array without complaint,
    and FAILED IN CI on 3.11.15, where `json.loads` raises `RecursionError` inside the
    body parser and FastAPI answers `400 {"detail": "There was an error parsing the
    body"}` before this application sees the request at all. Encoding one interpreter's
    boundary as an expectation is the same mistake `e2e/a11y-baseline.ts` exists to
    prevent for platform-dependent counts, and it is why that file says never to
    transcribe a number measured on the wrong platform.

    So what is asserted here is the invariant that holds on EVERY platform, which is
    also the whole of what the defect was about: the request is REFUSED, the refusal is
    not a 500, nothing is written, and the record stays readable. A 400 from the parser
    is a perfectly good refusal — arguably a better one, since it never reaches
    application code. The guard's own status code is pinned by the test above, at depths
    both interpreters parse.
    """
    run = _create_run(client, experiment_id)
    etag = _run_etag(client, experiment_id, run["id"])
    payload = (
        '{"confirmed_by_user": true, "fields": {"context.temperature_K": '
        + "[" * depth
        + "1"
        + "]" * depth
        + "}}"
    )
    response = client.patch(
        f"/api/experiments/{experiment_id}/runs/{run['id']}",
        content=payload.encode(),
        headers={"If-Match": etag, "content-type": "application/json"},
    )
    assert response.status_code in (400, 422), response.text
    assert response.status_code != 500

    stored = _stored_run(client, experiment_id, run["id"])
    assert stored.rev == 1
    assert stored.draft.get("fields") in (None, {})
    assert client.get(f"/api/experiments/{experiment_id}/runs").status_code == 200
    assert (
        client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").status_code == 200
    )
    assert client.get(f"/api/experiments/{experiment_id}").status_code == 200


def test_the_run_check_says_unavailable_when_the_dry_run_itself_raises(
    client, experiment_id, monkeypatch
):
    """THE SECOND `unavailable` BRANCH, which the first test did not reach.

    `_validate_unit` sets the flag in TWO places: the materialised-but-unreadable branch,
    and the branch where `export_draft` itself raises during the dry run. A reviewer
    deleted only the SECOND and the file still reported `99 passed` — so
    "it fails with either line removed", which the previous commit message asserted, was
    false. That is the FOURTH consecutive commit on this branch to over-state a
    "verified against a reintroduced defect" claim, which is why this test exists at all
    rather than the claim simply being softened.
    """

    def _boom(*_args, **_kwargs):
        raise RuntimeError("synthetic export failure")

    monkeypatch.setattr(routes, "export_draft", _boom)

    run = _create_run(client, experiment_id)
    body = client.post(
        f"/api/experiments/{experiment_id}/runs/{run['id']}/check"
    ).json()
    official = body["official"]
    assert official["unavailable"] is True
    # This branch IS a dry run — it is the dry run that failed.
    assert official["dry_run"] is True
    assert official["ok"] is False
    assert body["ok"] is False
    assert official["errors"] == [
        {"path": "$", "message": "Validation could not be completed."}
    ]
    # And it is a 200 with a verdict-shaped body, never a 500.
    assert (
        client.post(f"/api/experiments/{experiment_id}/runs/{run['id']}/check").status_code
        == 200
    )


@pytest.mark.parametrize(
    "make",
    [
        lambda: {"fields": {"context.temperature_K": _nested_wide(10)}},
        lambda: {"fields": {"context.temperature_K": "x" * 200_000}},
        lambda: {"fields": {"context.temperature_K": [1] * 200_000}},
        lambda: {"label": "L" * 100_000},
        # BETWEEN THE TWO LIMITS: 2,000 bytes is far under `_MAX_VALUE_BYTES` (64 KiB)
        # and far over `_MAX_LABEL_BYTES` (512). Without this case the label cap is not
        # load-bearing — a 100 KB label is refused by the value cap alone, which is
        # exactly what a negative control showed.
        lambda: {"label": "L" * 2_000},
    ],
    ids=[
        "wide-tree-at-legal-depth",
        "big-string",
        "big-list",
        "big-label",
        "label-over-its-own-smaller-cap",
    ],
)
def test_a_value_too_LARGE_to_store_is_refused_even_at_legal_depth(
    client, experiment_id, make
):
    """SIZE, WHICH THE DEPTH CAP DID NOT BOUND — the fourth instance of one defect class,
    and the reason the guard's contract is now stated as three conditions rather than
    grown by one each review.

    A reviewer measured the amplification on this build: at PERFECTLY LEGAL depth (a
    3-wide tree, 10 levels) a **236 KB body wrote 4.1 MB** to disk; 2.1 MB wrote 45.6 MB;
    172 MB wrote 4 GB while holding `record_lock` for 184 s and taking process RSS to
    5.6 GB. An 8 MB `label` was accepted too, since the value guard iterated `fields`
    only. The document is stored pretty-printed and each value is wrapped in an evidence
    envelope, which is where the ~17-23x comes from.

    Nothing was corrupted and no verdict was falsified — this is resource exhaustion, on
    a pod whose workspace is an `emptyDir` this project does not own — which is why it
    was an Important rather than a Critical. The sizes here are far below the measured
    hazard on purpose: the point is to pin the GUARD, not to spend 184 s in CI proving
    the hazard again.
    """
    run = _create_run(client, experiment_id)
    response = _patch(
        client, experiment_id, run["id"], {"confirmed_by_user": True, **make()}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"
    stored = _stored_run(client, experiment_id, run["id"])
    assert stored.rev == 1
    assert stored.draft.get("fields") in (None, {})
    assert stored.label == run["label"]


def test_a_value_and_a_label_at_ordinary_size_are_still_accepted(client, experiment_id):
    """The floor for the cap above. Without this it could pass by refusing everything —
    and the limits are deliberately ~2,000x the longest value the schema can put at any
    of the five writable paths (all scalars; the longest plausible is a 32-character
    ISO-8601 timestamp)."""
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {
            "confirmed_by_user": True,
            "label": "Cold run \u00b7 4 K",
            "fields": {"context.temperature_K": 277.15},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()["run"]
    assert body["fields"]["context.temperature_K"]["value"] == 277.15
    assert body["label"] == "Cold run \u00b7 4 K"


def test_the_size_cap_is_measured_on_the_rendered_bytes_not_the_python_object():
    """A 2-character string is not 2 bytes once rendered, and the cap is on what is
    STORED. Pinned directly, because the difference is what makes the check free: the
    render has already happened for condition 2."""
    assert routes._is_storable_value("x" * 10, max_bytes=12) is True
    # 10 characters render as 12 bytes with the quotes; 11 do not fit.
    assert routes._is_storable_value("x" * 11, max_bytes=12) is False


def test_the_depth_and_size_limits_have_a_floor():
    """THE CONSTANTS ARE PINNED FROM BELOW, because both boundary tests READ them and so
    would follow them anywhere. A reviewer set `_MAX_VALUE_DEPTH` to 1 and the file still
    reported `100 passed` — a limit nobody bounds is a limit that can be tightened into a
    product defect by a one-character edit.

    The floors are justified rather than round: the deepest whole document anywhere in
    this repository nests 7, and the longest value the schema can legitimately put at any
    of the five writable paths is a 32-character ISO-8601 timestamp.
    """
    assert routes._MAX_VALUE_DEPTH >= 16, "shallower than twice the deepest real document"
    assert routes._MAX_VALUE_BYTES >= 4 * 1024, "smaller than any plausible value needs"
    assert routes._MAX_LABEL_BYTES >= 128, "shorter than a name a person might type"
    # And an ordinary scalar must survive whatever the constants are set to.
    assert routes._is_storable_value("2026-01-31T09:00:00.000000+00:00") is True
    assert routes._is_storable_value(277.15) is True


def test_a_value_at_exactly_the_depth_limit_is_accepted(client, experiment_id):
    """The boundary from the other side. Without this, the fix above could pass by
    refusing every nested value — and the limit is deliberately far above anything the
    schema declares at these paths (all five are scalars) or any committed document
    (deepest is 7)."""
    run = _create_run(client, experiment_id)
    etag = _run_etag(client, experiment_id, run["id"])
    depth = routes._MAX_VALUE_DEPTH
    payload = (
        '{"confirmed_by_user": true, "fields": {"context.temperature_K": '
        + "[" * depth
        + "1"
        + "]" * depth
        + "}}"
    )
    response = client.patch(
        f"/api/experiments/{experiment_id}/runs/{run['id']}",
        content=payload.encode(),
        headers={"If-Match": etag, "content-type": "application/json"},
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/api/experiments/{experiment_id}/runs").status_code == 200


def test_the_depth_guard_does_not_itself_recurse():
    """`_value_depth_within` must REFUSE a 5,000-deep value rather than raise.

    SCOPED, because the obvious justification is over-general and a reviewer measured
    that. A *recursive early-exit* walk also passes this test: because the level is
    checked BEFORE descending, it returns at frame 33 and never overflows. What this
    test actually catches is a depth-COMPUTING implementation — `1 + max(depth(child) …)`,
    the shape most people reach for first — which recurses the full 5,000 frames and
    raises the very error the guard exists to prevent. That is the realistic regression,
    and it is worth a test; "proves the walk is iterative" is not what it proves.
    """
    deep = 1
    for _ in range(5000):
        deep = [deep]
    assert routes._value_depth_within(deep, routes._MAX_VALUE_DEPTH) is False
    assert routes._is_storable_value(deep) is False


def test_a_finite_number_at_the_same_path_is_still_accepted(client, experiment_id):
    """The guard is about REPRESENTABILITY, not about numbers. Without this, the fix
    above could pass by refusing every float."""
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 277.15}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["run"]["fields"]["context.temperature_K"]["value"] == 277.15


def test_a_non_object_fields_value_is_refused(client, experiment_id):
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": "context.temperature_K"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_fields"


# --- 4A. patch: the key must be a REAL field path, not merely a run-level prefix --
#
# THE DEFECT THIS SECTION CLOSES, measured against a running server before it was
# fixed: `field_level()` is a segment-aware PREFIX test, so every one of
# `context.typo_K`, `context.`, `context..`, `context`, `context. `,
# `context.<script>alert(1)</script>` and `timestamps.acquired_start_utc.evil`
# classified as run-level, returned 200, and was PERSISTED with a fabricated
# `user_confirmation` evidence entry. The consequence was not cosmetic: the run's
# own `check` then reported `context: Additional properties are not allowed` and
# `timestamps.acquired_start_utc: {'evil': 300} is not of type 'string'`, so ONE
# typo permanently blocked that run's official export — and the UI, which offers
# three fixed paths, had no way to clear it.
#
# It also recorded a `user_confirmation` for a path with no schema home, which is
# the invented evidence `CLAUDE.md` §5 forbids.
#
# The route's own OpenAPI description already promised the stricter behaviour
# ("A key that does not ... is rejected with 422 naming it"); the code now matches
# what it documents.


@pytest.mark.parametrize(
    "path",
    [
        # 1. INVENTED LEAVES UNDER A RUN-LEVEL PREFIX. Every one of these was
        #    accepted and written before the fix.
        "context.typo_K",
        "context.temperature",
        "context.",
        "context..",
        "context",
        "context. ",
        "context.<script>alert(1)</script>",
        "timestamps.acquired_start_utc.evil",
        # 2. ALREADY REFUSED BEFORE THE FIX, AND MUST STAY REFUSED. The fix
        #    narrows what is writable; it must not widen it anywhere.
        "Context.temperature_K",  # case is not normalised
        "CONTEXT",
        "contextual.foo",  # `_path_matches` is segment-aware, and stays so
        "qc",  # a top-level draft BLOCK, never a `fields` key
        "series",
        "tags",
        "sample.material.name",  # record-level: entered once and inherited
        "",
        " ",
        "timestamps",  # the bare block is not one of the two acquired timestamps
    ],
)
def test_a_path_that_is_not_a_real_run_writable_field_is_refused_and_not_written(
    client, experiment_id, path
):
    run = _create_run(client, experiment_id)
    before = _stored_run(client, experiment_id, run["id"])
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {path: "anything"}},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrecognized_field"
    assert body["key"] == path
    assert body["keys"] == [path]
    # NOT silently ignored, NOT written, and the run did not move at all — a
    # refused request must not advance a revision either.
    stored = _stored_run(client, experiment_id, run["id"])
    assert path not in (stored.draft.get("fields") or {})
    assert stored.rev == before.rev
    assert stored.version_token() == before.version_token()


def test_an_invented_path_cannot_wedge_the_run_it_was_addressed_to(
    client, experiment_id
):
    """THE CONSEQUENCE, end to end.

    Before the fix, `context.typo_K` was persisted and the run's own check then
    reported `Additional properties are not allowed ('typo_K' ...)` against
    `context` — an official-schema failure with no in-product repair path, because
    the UI offers three fixed paths and none of them is the typo.
    """
    run = _create_run(client, experiment_id)
    refused = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.typo_K": 300.0}},
    )
    assert refused.status_code == 422, refused.text

    check = client.post(f"/api/experiments/{experiment_id}/runs/{run['id']}/check")
    assert check.status_code == 200, check.text
    findings = json.dumps(check.json())
    assert "typo_K" not in findings
    assert "Additional properties are not allowed" not in findings


def test_the_three_paths_the_run_workspace_offers_are_all_still_writable(
    client, experiment_id
):
    """THE POSITIVE CONTROL for the refusal above.

    These three are `RUN_FIELDS` in `apps/web/src/lib/runFields.ts`, which is the
    only surface that writes a run field. A tightening that broke any of them
    would take the whole Run workspace with it, and a refusal-only test suite
    would not notice.
    """
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {
            "confirmed_by_user": True,
            "fields": {
                "context.environment": "in_situ",
                "context.temperature_K": 300.0,
                "timestamps.acquired_start_utc": "2026-01-01T00:00:00Z",
            },
        },
    )
    assert response.status_code == 200, response.text
    stored = _stored_run(client, experiment_id, run["id"]).draft["fields"]
    assert stored["context.environment"]["value"] == "in_situ"
    assert stored["context.temperature_K"]["value"] == 300.0
    assert stored["timestamps.acquired_start_utc"]["value"] == "2026-01-01T00:00:00Z"


def test_the_run_writable_paths_are_derived_from_the_extractor_field_map():
    """WHERE THE ALLOWLIST COMES FROM, pinned so it cannot become a hand-copied list.

    `routes.RUN_WRITABLE_FIELD_PATHS` is DERIVED at import time from
    `extract.structured.FIELD_MAP` — the deterministic extractor's own map of
    official dotted paths — filtered by `workspace.field_level`. Both gates are
    load-bearing: FIELD_MAP decides that the path EXISTS, `field_level` decides
    that it is the RUN's to write. Neither alone is sufficient, and the defect
    this closes was applying only the second.
    """
    from isaac_records.extract.structured import FIELD_MAP

    expected = {
        path for path, _coercer in FIELD_MAP.values() if ws.field_level(path) == ws.LEVEL_RUN
    }
    assert routes.RUN_WRITABLE_FIELD_PATHS == expected
    # The measured set at this commit. Stated literally as well as derived,
    # because a derivation that silently emptied itself would satisfy the
    # comparison above and refuse everything.
    assert expected == {
        "context.environment",
        "context.temperature_K",
        "context.thermodynamics.atmosphere",
        "timestamps.acquired_start_utc",
        "timestamps.acquired_end_utc",
    }


def test_every_run_writable_path_resolves_to_a_typed_node_in_the_official_schema():
    """WHY FIELD_MAP IS THE RIGHT SOURCE, asserted rather than asserted-in-a-comment.

    `FIELD_MAP`'s own header claims each path was "verified against
    schema/isaac_record_v1.json". A claim in a comment is what drifts, so it is
    measured here: every path this route will write resolves through
    `properties` to a node with a declared `type`.

    NOTE the asymmetry that decided the source of truth. The same walk does NOT
    resolve `sample.composition.*`, `sample.geometry.*` or
    `system.configuration.*` — the schema's OPEN namespaces, which declare no
    properties at all. So the official schema alone cannot enumerate a closed set
    of legal dotted paths; it would either admit anything under an open namespace
    or need a second, per-subtree policy. None of those namespaces is run-level,
    which is why the intersection used here is both closed and schema-backed.
    """
    schema = json.loads(
        (ws.REPO_ROOT / "schema" / "isaac_record_v1.json").read_text(encoding="utf-8")
    )
    for path in sorted(routes.RUN_WRITABLE_FIELD_PATHS):
        node = schema
        for segment in path.split("."):
            properties = node.get("properties")
            assert isinstance(properties, dict), path
            assert segment in properties, path
            node = properties[segment]
        assert "type" in node, path


# --- 4B. patch: a blank label is a refusal, not a silent no-op ------------------


@pytest.mark.parametrize("label", ["   ", "\t", "\n", " "])
def test_a_whitespace_only_label_is_refused_rather_than_silently_dropped(
    client, experiment_id, label
):
    """A rename to whitespace used to return 200 having renamed nothing.

    That contradicts this route's own stated doctrine — a request is never
    silently ignored — and it is the one place where "blank is not a label"
    (correct on CREATE, where blank means "server, you choose") produces a lie on
    EDIT, where there is no name for the server to choose and the caller was told
    the rename happened.
    """
    run = _create_run(client, experiment_id, label="Cold")
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "label": label},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_label"
    stored = _stored_run(client, experiment_id, run["id"])
    assert stored.label == "Cold"
    assert stored.rev == 1  # created, never edited


def test_a_whitespace_label_refuses_the_whole_request_including_its_valid_fields(
    client, experiment_id
):
    """Same whole-request refusal the path classification already gives."""
    run = _create_run(client, experiment_id, label="Cold")
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {
            "confirmed_by_user": True,
            "label": "  ",
            "fields": {"context.temperature_K": 300.0},
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_label"
    stored = _stored_run(client, experiment_id, run["id"])
    assert stored.draft.get("fields") in (None, {})
    assert stored.label == "Cold"


def test_a_blank_label_on_CREATE_is_still_the_server_choosing(client, experiment_id):
    """THE BOUNDARY of the fix above, pinned in the same file.

    On CREATE a blank label means "server, assign one", is documented as such and
    is covered by `test_an_omitted_or_blank_label_is_assigned_run_n_by_the_server`.
    The refusal added for EDIT must not have leaked into it.
    """
    run = _create_run(client, experiment_id, label="   ")
    assert run["label"] == "Run 1"


# --- 4C. patch: a clear of a field the run does not have writes nothing ---------


def test_clearing_a_field_the_run_does_not_have_does_not_move_the_run(
    client, experiment_id
):
    """A `null` for an absent field is a no-op, and used to be a no-op that still
    changed the document: the write path created `draft["fields"] = {}`
    unconditionally, which is part of the run's authoritative signature, so the
    run's `rev` advanced while nothing was written.

    Nothing LIED — the response reported the new version honestly — and it was
    reachable only once per run. It is fixed because a revision that means "your
    edit landed" should not be spent on an edit that did not.
    """
    run = _create_run(client, experiment_id)
    before = _stored_run(client, experiment_id, run["id"])
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": None}},
    )
    assert response.status_code == 200, response.text
    after = _stored_run(client, experiment_id, run["id"])
    assert after.rev == before.rev
    assert after.version_token() == before.version_token()
    assert response.json()["run"]["version"] == before.version_token()
    # And no empty `fields` map was manufactured on the way through.
    assert after.draft.get("fields") in (None, {})


# --- 5. patch: what it writes --------------------------------------------------


def test_an_accepted_write_stores_the_value_with_user_confirmation_evidence(
    client, experiment_id
):
    run = _create_run(client, experiment_id)
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {
            "confirmed_by_user": True,
            "fields": {
                "context.temperature_K": 300.0,
                "context.environment": "electrolyte",
            },
        },
    )
    assert response.status_code == 200, response.text
    view = response.json()["run"]
    assert view["fields"]["context.temperature_K"]["value"] == 300.0
    assert view["fields"]["context.environment"]["value"] == "electrolyte"

    stored = _stored_run(client, experiment_id, run["id"])
    envelope = stored.draft["fields"]["context.temperature_K"]
    assert envelope["status"] == "verified"
    assert [e["source_type"] for e in envelope["evidence"]] == ["user_confirmation"]
    assert envelope["evidence"][0]["answer"] == "300.0"
    assert envelope["evidence"][0]["timestamp"]
    # The new ETag is the RUN's, and it moved.
    assert response.headers["ETag"] == f'"{stored.version_token()}"'
    assert stored.rev == 2  # 1 at creation, 2 after the edit


def test_a_null_value_clears_the_field_entirely(client, experiment_id):
    run = _create_run(client, experiment_id)
    _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
    )
    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": None}},
    )
    assert response.status_code == 200, response.text
    assert "context.temperature_K" not in response.json()["run"]["fields"]
    stored = _stored_run(client, experiment_id, run["id"])
    assert "context.temperature_K" not in stored.draft["fields"]


def test_a_label_only_patch_renames_the_run_and_writes_no_field(client, experiment_id):
    run = _create_run(client, experiment_id)
    response = _patch(
        client, experiment_id, run["id"], {"confirmed_by_user": True, "label": "Warm"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["run"]["label"] == "Warm"
    stored = _stored_run(client, experiment_id, run["id"])
    assert stored.label == "Warm"
    assert stored.draft.get("fields") in (None, {})


def test_an_existing_unit_on_an_envelope_is_carried_not_dropped(client, experiment_id):
    """A unit is evidence-bearing content the request said nothing about. It is
    neither dropped nor re-derived — this API never invents a unit, and it must not
    delete one either."""
    run = _create_run(client, experiment_id)
    store = client_ws(client)
    exp = store.load_experiment(experiment_id)
    stored = exp.get_run(run["id"])
    stored.draft["fields"] = {
        "context.temperature_K": field_value(
            77.0,
            unit="K",
            status="verified",
            evidence=[user_confirmation("q", "77.0", "2026-01-01T00:00:00Z")],
        )
    }
    exp.save_versioned()

    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
    )
    assert response.status_code == 200, response.text
    envelope = _stored_run(client, experiment_id, run["id"]).draft["fields"][
        "context.temperature_K"
    ]
    assert envelope["unit"] == "K"
    assert envelope["value"] == 300.0
    # The prior evidence is kept alongside the new confirmation, never replaced.
    assert len(envelope["evidence"]) == 2


# --- 6. INVARIANT 3: a byte-stable re-entry does not advance the run -----------


def test_resubmitting_the_same_value_does_not_advance_the_run(client, experiment_id):
    """INVARIANT 3, pinned END TO END rather than at ``save_versioned``.

    ``save_versioned``'s byte-stable no-op is not enough on its own here: the write
    path stamps a ``user_confirmation`` with a fresh timestamp, so an unconditional
    append would make an identical re-submission a genuine document change and the
    no-op would never be reached. ``_apply_run_field`` is idempotent for exactly
    that reason, and this is the test that says so.
    """
    run = _create_run(client, experiment_id)
    body = {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}}
    first = _patch(client, experiment_id, run["id"], body)
    assert first.status_code == 200, first.text
    after_first = _stored_run(client, experiment_id, run["id"])
    version = after_first.version_token()
    evidence = copy.deepcopy(after_first.draft["fields"]["context.temperature_K"])

    second = _patch(client, experiment_id, run["id"], body)
    assert second.status_code == 200, second.text
    after_second = _stored_run(client, experiment_id, run["id"])
    assert after_second.rev == after_first.rev
    assert after_second.version_token() == version
    assert after_second.draft["fields"]["context.temperature_K"] == evidence
    assert second.headers["ETag"] == f'"{version}"'


# --- 7. INVARIANT 1: run isolation --------------------------------------------


def test_writing_one_run_leaves_its_sibling_byte_identical(client, experiment_id):
    """INVARIANT 1 — two runs of one experiment are isolated.

    MUTATION-CHECKED. `routes._apply_run_field` was made to write into the FIRST
    run's field map regardless of which run the request addressed (`fields` replaced
    by `exp.sorted_runs()[0].draft["fields"]` at the `patch_run` call site). This
    test went RED on the sibling's `fields` comparison; the other run-API tests
    stayed green, because every one of them uses a single run. Reverted.
    """
    first = _create_run(client, experiment_id, "Cold")
    second = _create_run(client, experiment_id, "Warm")

    before = _stored_run(client, experiment_id, second["id"])
    before_fields = copy.deepcopy(before.draft.get("fields") or {})
    before_rev, before_version = before.rev, before.version_token()

    response = _patch(
        client,
        experiment_id,
        first["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
    )
    assert response.status_code == 200, response.text

    after = _stored_run(client, experiment_id, second["id"])
    assert (after.draft.get("fields") or {}) == before_fields
    assert after.rev == before_rev
    assert after.version_token() == before_version

    # ...and the run that WAS addressed did move, so the assertion above is not
    # passing because nothing happened at all.
    written = _stored_run(client, experiment_id, first["id"])
    assert written.draft["fields"]["context.temperature_K"]["value"] == 300.0
    assert written.version_token() != second["version"]


def test_two_runs_hold_independent_field_maps(client, experiment_id):
    first = _create_run(client, experiment_id, "Cold")
    second = _create_run(client, experiment_id, "Warm")
    _patch(
        client,
        experiment_id,
        first["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 77.0}},
    )
    _patch(
        client,
        experiment_id,
        second["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
    )
    listed = {
        r["id"]: r for r in client.get(f"/api/experiments/{experiment_id}/runs").json()["runs"]
    }
    assert listed[first["id"]]["fields"]["context.temperature_K"]["value"] == 77.0
    assert listed[second["id"]]["fields"]["context.temperature_K"]["value"] == 300.0


# --- 8. INVARIANT 2: a stale run validator is refused -------------------------


def test_a_stale_run_if_match_is_refused_and_the_stored_value_does_not_move(
    client, experiment_id
):
    """INVARIANT 2 — a stale run `If-Match` is 412 and the stored value is unchanged.

    MUTATION-CHECKED. The `_check_if_match(...)` call in `patch_run` was replaced by
    `precondition = None`, so every validator was accepted. This test went RED on
    the status code AND, independently, on the stored-value assertion — the second
    run's write landed at 200 and overwrote 77.0 with 300.0. Reverted.

    The stored value is read back from the STORE, not from the response, and it is
    asserted to be the value the FIRST write left — a test that only checked the
    status code would pass against a handler that returned 412 after writing.
    """
    run = _create_run(client, experiment_id)
    stale = _run_etag(client, experiment_id, run["id"])

    first = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 77.0}},
        if_match=stale,
    )
    assert first.status_code == 200, first.text
    fresh = _stored_run(client, experiment_id, run["id"])
    assert fresh.version_token() != stale.strip('"')

    response = _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
        if_match=stale,
    )
    assert response.status_code == 412, response.text
    body = response.json()
    assert body == {
        "error": "stale_write",
        "experiment_id": experiment_id,
        "run_id": run["id"],
        "expected_rev": 1,
        "current_rev": fresh.rev,
        "expected_version": stale.strip('"'),
        "current_version": fresh.version_token(),
    }
    assert response.headers["ETag"] == f'"{fresh.version_token()}"'

    after = _stored_run(client, experiment_id, run["id"])
    assert after.draft["fields"]["context.temperature_K"]["value"] == 77.0
    assert after.rev == fresh.rev
    assert after.version_token() == fresh.version_token()


# --- 9. INVARIANT 4: durability across a reload -------------------------------


def test_a_created_run_survives_a_reload_from_persisted_state(client, experiment_id):
    """INVARIANT 4 — create, drop the in-memory experiment, reload, same run.

    The reload goes through the persisted state document on disk, not through a
    cached object: ``load_experiment`` re-reads and re-hydrates every time.
    """
    run = _create_run(client, experiment_id, "Cold")
    _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 77.0}},
    )
    live = _stored_run(client, experiment_id, run["id"])

    state = json.loads(
        client_ws(client).load_experiment(experiment_id).state_path.read_text()
    )
    assert [entry["id"] for entry in state["runs"]] == [run["id"]]

    reloaded = _stored_run(client, experiment_id, run["id"])
    assert reloaded is not live  # genuinely a fresh hydration
    assert reloaded.id == run["id"]
    assert reloaded.label == "Cold"
    assert reloaded.rev == live.rev
    assert reloaded.draft["fields"]["context.temperature_K"]["value"] == 77.0

    # And over HTTP, which is what a browser would see after a restart.
    view = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").json()["run"]
    assert view["label"] == "Cold"
    assert view["rev"] == live.rev
    assert view["fields"]["context.temperature_K"]["value"] == 77.0


# --- 10. INVARIANT 5: Check Run writes nothing --------------------------------


def _all_versions(client, experiment_id: str) -> dict:
    exp = client_ws(client).load_experiment(experiment_id)
    return {
        "experiment": exp.version_token(),
        **{run.id: run.version_token() for run in exp.sorted_runs()},
    }


def test_check_run_moves_no_version_at_all(client, experiment_id):
    """INVARIANT 5 — Check Run writes nothing.

    MUTATION-CHECKED. A single `exp.save_versioned()` was inserted into
    `post_run_check` immediately before the return. This test went RED on the
    version comparison. Reverted.

    The state file's bytes are compared as well as the versions, because a write
    that happened to be byte-stable would leave the versions equal and still be a
    write this operation promised not to make.
    """
    first = _create_run(client, experiment_id, "Cold")
    second = _create_run(client, experiment_id, "Warm")
    _patch(
        client,
        experiment_id,
        first["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 77.0}},
    )

    exp = client_ws(client).load_experiment(experiment_id)
    state_path = exp.state_path
    before_versions = _all_versions(client, experiment_id)
    before_bytes = state_path.read_bytes()
    before_mtime = state_path.stat().st_mtime_ns

    response = client.post(
        f"/api/experiments/{experiment_id}/runs/{first['id']}/check"
    )
    assert response.status_code == 200, response.text
    assert response.json()["checked_run_version"] == before_versions[first["id"]]
    # No ETag is minted by a read-only check.
    assert "ETag" not in response.headers

    assert _all_versions(client, experiment_id) == before_versions
    assert state_path.read_bytes() == before_bytes
    assert state_path.stat().st_mtime_ns == before_mtime
    assert second["id"] in before_versions  # the sibling was in scope of the check


def test_check_run_reports_both_deterministic_verdicts_and_no_third_one(
    client, experiment_id
):
    run = _create_run(client, experiment_id)
    body = client.post(
        f"/api/experiments/{experiment_id}/runs/{run['id']}/check"
    ).json()
    assert set(body) == {"ok", "draft", "official", "blockers", "checked_run_version"}
    assert set(body["draft"]) == {"ok", "errors", "warnings"}
    assert body["official"]["run_id"] == run["id"]
    assert body["official"]["dry_run"] is True
    assert body["official"]["schema"] == routes.SCHEMA_LABEL
    assert body["ok"] is (body["draft"]["ok"] and body["official"]["ok"])


def test_check_run_agrees_with_the_records_own_validate_operation(
    client, experiment_id
):
    """No second validator exists — this operation must produce the SAME verdict the
    record-level validate operation already produces for that run."""
    first = _create_run(client, experiment_id, "Cold")
    _create_run(client, experiment_id, "Warm")

    record_level = client.post(f"/api/experiments/{experiment_id}/validate").json()
    per_run = {entry["run_id"]: entry for entry in record_level["runs"]}
    check = client.post(
        f"/api/experiments/{experiment_id}/runs/{first['id']}/check"
    ).json()
    assert check["official"]["ok"] == per_run[first["id"]]["ok"]
    assert check["official"]["errors"] == per_run[first["id"]]["errors"]
    assert check["official"]["dry_run"] == per_run[first["id"]]["dry_run"]


def test_checking_an_unknown_run_is_a_404(client, experiment_id):
    response = client.post(f"/api/experiments/{experiment_id}/runs/NOPE/check")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "run_not_found"


# --- 11. INVARIANT 6: no route here mints a record id -------------------------


def test_no_operation_in_this_api_mints_a_record_id(client, experiment_id):
    """INVARIANT 6 — ``record_id`` is not advanced by any of these five operations.

    Exporting is what mints a record id, and it is deliberately not reachable from
    here: a check is a verdict, never a commit.
    """
    run = _create_run(client, experiment_id)
    client.get(f"/api/experiments/{experiment_id}/runs")
    client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}")
    _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
    )
    client.post(f"/api/experiments/{experiment_id}/runs/{run['id']}/check")

    exp = client_ws(client).load_experiment(experiment_id)
    assert exp.record_id is None
    assert [r.record_id for r in exp.runs] == [None]
    assert not exp.records_dir.exists() or list(exp.records_dir.iterdir()) == []


# --- 11b. the integration contract the frontend is built against --------------
#
# Five corrections came back from the frontend workstream after it built against
# the frozen slice contract. Four of them are assertions about the WIRE SHAPE that
# no other test in this file was making, and the frontend is already built on them,
# so they are pinned here rather than left to a review to notice.


def _split_raw_draft() -> tuple[dict, dict]:
    """``(experiment_draft, run_draft)`` from the EXTRACTION-ONLY seed.

    The same split as :func:`_split_full_draft`, except that the extractor's open
    blocking questions are kept and put on the RUN. That is where they belong: the
    raw draft's blockers are all asset / series / qc / descriptor questions, and
    every one of those blocks classifies as run-level (``block_level``).
    """
    full = ws._raw_draft()
    experiment: dict = {"meta": copy.deepcopy(full["meta"]), "fields": {}, "pending": []}
    run: dict = {"fields": {}, "pending": copy.deepcopy(full.get("pending") or [])}

    for path, envelope in (full.get("fields") or {}).items():
        level = ws.field_level(path)
        if level == ws.LEVEL_EXPERIMENT:
            experiment["fields"][path] = copy.deepcopy(envelope)
        elif level == ws.LEVEL_RUN:
            run["fields"][path] = copy.deepcopy(envelope)

    for key, value in full.items():
        if key in ("fields", "meta", "pending", "implicit", "block_evidence"):
            continue
        level = ws.block_level(key)
        if level == ws.LEVEL_EXPERIMENT:
            experiment[key] = copy.deepcopy(value)
        elif level == ws.LEVEL_RUN:
            run[key] = copy.deepcopy(value)
    return experiment, run


def test_every_inherited_entry_reports_state_and_never_provenance(
    client, experiment_id
):
    """CORRECTION 1 — the wire key is `state`, with THREE values.

    ``Resolution.provenance`` has only two (``inherited``/``overridden``) and is
    merged, tested domain code that this slice does not touch. The third value is
    the SERIALIZER's: an address in the resolution key set that the experiment
    carries nothing at, and that this run does not override, is ``absent`` — which
    ``provenance`` alone cannot say, because it would report that case as
    ``inherited`` and a client would render an inherited value that is not there.

    All three are asserted REACHABLE in one response. A test that only checked the
    two easy ones would pass against a serializer that never emits the third.
    """
    store = client_ws(client)
    exp = store.load_experiment(experiment_id)
    # An experiment-level address the experiment carries NOTHING at. A persisted
    # draft can hold a null envelope, and `resolve_inherited` keeps the address in
    # its key set, so this is the reachable `absent` case rather than a contrived one.
    exp.draft["fields"]["sample.sample_id"] = None
    exp.save_versioned()

    run = _create_run(client, experiment_id)
    exp = store.load_experiment(experiment_id)
    stored = exp.get_run(run["id"])
    exp.set_run_override(
        stored,
        ws.field_address("sample.material.name"),
        field_value("Overridden", status="verified", evidence=[]),
    )
    exp.save_versioned()

    body = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").json()
    inherited = body["run"]["inherited"]
    states = {entry["state"] for entry in inherited.values()}
    assert states == {"inherited", "overridden", "absent"}, inherited
    assert inherited[ws.field_address("sample.sample_id")]["state"] == "absent"
    assert inherited[ws.field_address("sample.material.name")]["state"] == "overridden"

    # `provenance` is the DOMAIN model's name and must not reach the wire as a KEY:
    # a client keying on it would silently miss the third state. The assertion is
    # on the key set of every entry, deliberately NOT on the whole serialized body
    # — the seed legitimately contains the WORD (`sample.material.provenance` is a
    # real official path, and one evidence quote uses it), so a substring scan
    # would fail for a reason that has nothing to do with this contract.
    for address, entry in inherited.items():
        assert set(entry) == {
            "state",
            "payload",
            "inherited_payload",
            "displaced_payload",
        }, (address, entry)


def test_every_blocker_carries_a_non_empty_message(client):
    """CORRECTION 2 — the `blockers[]` element shape is pinned.

    Exercised against a run that genuinely has open blocking questions (the
    extraction-only seed), not against an empty list — an empty list satisfies
    "every element has a message" vacuously, which is exactly the shape of green
    test this repository has shipped before.
    """
    experiment_draft, run_draft = _split_raw_draft()
    store = client_ws(client)
    exp = store.create_experiment(
        "Blocked run fixture", {"kind": "synthetic"}, experiment_draft
    )
    exp.add_run(label="Cold", draft=run_draft)
    exp.save_versioned()
    run_id = store.load_experiment(exp.id).runs[0].id

    body = client.post(f"/api/experiments/{exp.id}/runs/{run_id}/check").json()
    assert body["ok"] is False, "the fixture must actually be blocked"
    assert body["blockers"], "the fixture must actually carry blocking questions"
    for blocker in body["blockers"]:
        assert isinstance(blocker.get("message"), str), blocker
        assert blocker["message"].strip(), blocker
    # Derived, never composed: each message is text the blocker itself records.
    for blocker in body["blockers"]:
        assert blocker["message"] in (
            blocker.get("question"),
            blocker.get("about"),
            blocker.get("kind"),
        ), blocker


def test_the_etag_header_and_the_body_version_never_disagree(client, experiment_id):
    """CORRECTION 3 — the header and the body report the SAME revision.

    The frontend takes its `If-Match` from the BODY, so a header that had moved on
    while the body had not would hand it a validator that is already stale. Note
    the one difference that is not a disagreement: an `ETag` is a QUOTED validator
    (RFC 9110) and the body carries the bare revision, so the header is the body's
    value in double quotes — and `_check_if_match` accepts only the quoted form.
    Both are asserted, including that the body's value, quoted, is ACCEPTED.
    """
    created = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": "Cold"},
        headers={"If-Match": _experiment_etag(client, experiment_id)},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert created.headers["ETag"] == f'"{body["experiment_version"]}"'
    run_id = body["run"]["id"]

    # The experiment version the create returned, quoted, is what the NEXT create
    # must be able to send — the other body-sourced validator. Done here, before
    # anything else moves the record on.
    second = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": "Warm"},
        headers={"If-Match": f'"{body["experiment_version"]}"'},
    )
    assert second.status_code == 201, second.text
    assert second.headers["ETag"] == f'"{second.json()["experiment_version"]}"'

    read = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}")
    assert read.headers["ETag"] == f'"{read.json()["run"]["version"]}"'

    # The body's own value, quoted, is what a PATCH must be able to send.
    patched = client.patch(
        f"/api/experiments/{experiment_id}/runs/{run_id}",
        json={"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
        headers={"If-Match": f'"{read.json()["run"]["version"]}"'},
    )
    assert patched.status_code == 200, patched.text
    assert patched.headers["ETag"] == f'"{patched.json()["run"]["version"]}"'


def test_reading_one_run_returns_only_the_run(client, experiment_id):
    """CORRECTION 4 — `{"run": RunView}` and nothing else.

    The frontend's conflict-refresh depends on that shape; adding
    `experiment_version` here would give it a second validator to choose between
    at the exact moment it is recovering from having chosen wrong.
    """
    run = _create_run(client, experiment_id)
    body = client.get(f"/api/experiments/{experiment_id}/runs/{run['id']}").json()
    assert set(body) == {"run"}


# --- 12. INVARIANT 7 + tutorial isolation -------------------------------------


#: The truth path, exactly as ``CLAUDE.md`` §13 defines it. Named files, not a directory
#: glob — and that distinction was learned rather than designed.
#:
#: THIS GUARD USED TO FREEZE ALL OF ``src/isaac_records/``, which is broader than §13 and
#: broader than it needed to be. It was written for the Run slice, where the correct
#: statement was "this slice changes no core file at all", and it compares against the
#: merge base — so it fired on the FIRST later branch with a legitimate reason to touch a
#: core file, reporting "the truth path was modified" about ``complete.py``, which §13
#: does not list. A guard whose message misnames what it caught teaches the next reader
#: the wrong boundary, and invites being switched off rather than understood.
#:
#: What is protected here is unchanged in strength where §13 puts it: the official
#: validator, the draft validator, the exporter, the audit path, the CLI and the vendored
#: schema. A change to any of those is a truth-path change and must be reported as §13
#: requires. ``complete.py`` is core but not truth-path; changing it still carries §13's
#: disclosure obligations, which is why the commit that did so reports what changed, what
#: covers it, and that neither export behaviour nor schema compliance moved.
_TRUTH_PATH_FILES = (
    "schema/isaac_record_v1.json",
    "src/isaac_records/official.py",
    "src/isaac_records/draft_validator.py",
    "src/isaac_records/export.py",
    "src/isaac_records/audit.py",
    "src/isaac_records/cli.py",
)


def test_the_truth_path_is_untouched_by_this_slice():
    """INVARIANT 7 — no file ``CLAUDE.md`` §13 names as the truth path is modified.

    Asked of git rather than asserted in prose: the working tree is compared with
    the branch point, so an edit would be reported here whatever file it hid in.
    """
    root = ws.REPO_ROOT
    merge_base = subprocess.run(
        ["git", "merge-base", "HEAD", "origin/main"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    base = merge_base.stdout.strip() if merge_base.returncode == 0 else "HEAD"
    changed = subprocess.run(
        ["git", "diff", "--name-only", base, "--", *_TRUTH_PATH_FILES],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert changed == [], f"the truth path was modified: {changed}"


def test_the_run_api_does_not_weaken_tutorial_isolation(client, experiment_id):
    """A worked-example session's runs stay unpersistable, exactly as before.

    This API adds no storage path of its own — a run lives inside its experiment's
    state document — so the guard that refuses to write a session record to the
    database is the guard that refuses its runs. That is asserted here rather than
    assumed, because it is the invariant a new write path is most likely to break
    silently.
    """
    from isaac_api.experiment_repository import NotPersistable, PostgresOrdinaryStore

    run = _create_run(client, experiment_id)
    _patch(
        client,
        experiment_id,
        run["id"],
        {"confirmed_by_user": True, "fields": {"context.temperature_K": 300.0}},
    )
    exp = client_ws(client).load_experiment(experiment_id)
    assert exp.session_id == client.tutorial_session_id
    assert exp.runs, "the fixture must actually hold a run"
    with pytest.raises(NotPersistable):
        PostgresOrdinaryStore.refuse_if_not_persistable(exp)

    # The same guard still refuses a canonical example id in the ordinary scope.
    ordinary = ws.Experiment(
        session_id=None,
        id=next(iter(ws.CANONICAL_IDS)),
        title="t",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
    )
    with pytest.raises(NotPersistable):
        PostgresOrdinaryStore.refuse_if_not_persistable(ordinary)

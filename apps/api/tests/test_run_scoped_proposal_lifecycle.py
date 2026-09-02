"""THE RUN-SCOPED INGESTION PROPOSAL, END TO END, ON A RECORD WITH TWO RUNS.

WHAT WAS MISSING AND WHY THIS FILE EXISTS
=========================================
``test_ingestion_proposals.py`` is 3,000+ lines and it does exercise run-scoped
targets — but always against the ``experiment`` fixture, which has **exactly one
run** (``exp.add_run(label="Run A", ...)``, one call). A suite with one run cannot
distinguish "the value was written to the run this proposal names" from "the value
was written to the only run there is", and it cannot see a write that lands on a
neighbour. Every isolation claim this feature makes is therefore untested there,
not because anybody skipped it but because the fixture cannot express it.

The browser side stated the gap outright. ``apps/web/e2e/mutation/proposals.spec.ts``
says: *"an exported record refuses ``POST .../runs`` (409
``already_exported_without_runs``, measured), so no run-scoped proposal is exercised
here … Run-scoped acceptance, the ``target_run_removed`` refusal and the run's own
current-value read are NOT covered by this file."*

**THAT IS A PROPERTY OF THE TWO RECORDS THAT SPEC CHOSE, NOT OF THE PRODUCT.** The
product has a creation path — ``POST /api/experiments`` — and a record created
through it takes runs happily. ``test_the_product_s_own_creation_path_reaches_a_run_scoped_proposal``
below walks it over HTTP with nothing borrowed from a seed. The companion browser
suite is ``apps/web/e2e/trusted/proposals-run-scoped.spec.ts``.

THE TARGET IS DERIVED, NEVER GUESSED
====================================
``RUN_FIELD_TARGET`` and ``OVERRIDE_TARGET`` are computed at import from the
application's own ``PROPOSAL_TARGET_PATHS`` / ``_proposal_writer_for`` /
``_PROPOSAL_WRITER_SCOPE`` — the same three expressions the create route and the
review route dispatch on. A hand-copied literal would be a second definition of "a
run-scoped target", free to rot into a test that passes for the wrong reason, and
``test_the_derivation_is_not_vacuous_and_agrees_with_the_wire`` asserts the
derivation against what the list operation actually serves.

BOTH RUN-SCOPED WRITER CLASSES ARE COVERED, because they are different code paths
with different failure modes: ``run_field`` writes ``run.draft["fields"]`` directly,
``run_override`` goes through ``exp.set_run_override`` and can raise
``NotOverridable``.

THE ISOLATION CLAIM IS A WHOLE-BODY COMPARISON, NEVER PICKED KEYS
=================================================================
``_run_body`` captures the untargeted run's ENTIRE ``GET .../runs/{id}`` response
and the assertion is equality of the whole document. A test that compared three
fields could not see a fourth moving. ``test_the_isolation_comparison_is_not
_vacuous`` is the negative control: the same comparison is shown to go RED when the
other run really is written.

MUTATION-CHECKED
================
Tests whose docstring carries a ``MUTATION:`` line were verified by BREAKING the
production code in the way the test claims to catch, confirming the test went RED,
and reverting the break. A test with no ``MUTATION:`` line was not mutation-checked
and does not claim to have been.

ACCEPTANCE NEEDS A CONFIGURATION NO DEPLOYMENT HAS, AND THAT IS STATED NOT ASSUMED
=================================================================================
``accept`` answers ``409 human_actor_required`` in every default-configured
deployment (contract §5 **I4**; ``CLAUDE.md`` §15), because no trusted authentication
boundary exists in this build — that is Dean-owned infrastructure and no application
change can close it. The only legitimate way to reach the success leg is the fixture
verifier (``ISAAC_EDGE_TRUST_VERIFIER=test_fixture`` +
``ISAAC_FIXTURE_ACTOR_SUBJECT``), which ``test_deploy_config.py`` pins to no shipped
deploy artifact. The ``armed_client`` fixture selects it, and
``test_the_default_configuration_still_refuses_acceptance`` asserts the OTHER leg in
the same file so neither is quietly lost.

ORDINARY SCOPE, NOT A WORKED-EXAMPLE SESSION, AND THE REASON IS MEASURED
========================================================================
``identity.stamp_actor`` returns ``None`` unconditionally and FIRST inside a tutorial
session, so an acceptance there is recorded UNATTRIBUTED even under the fixture
verifier (``test_ingestion_proposals.py::test_I7_an_acceptance_inside_a_tutorial_
session_is_unattributed``). Attribution is one of the things this file proves, so the
records here are ordinary-scope records — which is also what they are in the product.

DATA BOUNDARY: none. Every value is synthetic and unmistakably so, written into a
``tmp_path`` workspace. No database connection is opened, no migration is applied, no
file outside ``tmp_path`` is written, and no production-derived content is read.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.identity as identity
import isaac_api.proposals as proposals
import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_records.export import transform
from isaac_records.models import user_confirmation

from test_export_fan_out import _split_full_draft

ACTOR = "synthetic.run.scoped.reviewer"

#: The captured sentence every proposal below cites. Deliberately vague about WHICH
#: run it describes, which is exactly the situation a proposal exists for: a person,
#: not an extractor, decides which run it belongs to.
NOTE_TEXT = (
    "the second configuration on the synthetic sheet was run differently from the "
    "first, and the pellet it used was not the one the sample sheet names"
)


# --- the target, derived from the application's own three expressions ----------


def _run_scoped_targets() -> dict[str, str]:
    """``{path: writer}`` for every proposal target this build treats as a RUN's.

    Built from the same three expressions the create route and the review route
    dispatch on, so this cannot report a target the routes would refuse.
    """
    out: dict[str, str] = {}
    for path in routes.PROPOSAL_TARGET_PATHS:
        writer = routes._proposal_writer_for(path)
        if writer is not None and routes._PROPOSAL_WRITER_SCOPE[writer] == "run":
            out[path] = writer
    return out


def _schema_node(path: str) -> dict | None:
    """The vendored official schema's node at a dotted path, or ``None``.

    A TEST-LOCAL reader of the document ``CLAUDE.md`` §1 makes the authority — not a
    second definition of any application behaviour. It exists so the values this file
    proposes come from the schema rather than from the author, which is the same rule
    ``test_ingestion_proposals.py`` follows for ``RECORD_VALUE``.
    """
    node: object = json.loads(
        (routes.schema_path(routes.REPO_ROOT)).read_text(encoding="utf-8")
    )
    for segment in path.split("."):
        if not isinstance(node, dict):
            return None
        node = (node.get("properties") or {}).get(segment)
        if node is None:
            return None
    return node if isinstance(node, dict) else None


_SEED_EXPERIMENT_DRAFT, _SEED_RUN_DRAFT = _split_full_draft()


def _seed_value(draft: dict, path: str):
    return ((draft.get("fields") or {}).get(path) or {}).get("value")


def _pick_run_field_target() -> str:
    """The lowest-sorting ``run_field`` target that can carry FOUR distinct values.

    Four, because this file needs three distinct values at once (run A's, run B's and
    the proposed one — otherwise a read of the wrong run is undetectable) plus one
    more for the edited-acceptance leg. The requirement is stated as a property and
    the path is then found, rather than a path being named and the property assumed:
    a schema refresh that closed or reopened an enum moves the choice automatically,
    and ``test_the_derivation_is_not_vacuous_and_agrees_with_the_wire`` fails loudly
    if nothing qualifies.
    """
    for path in sorted(
        p
        for p, w in _run_scoped_targets().items()
        if w == proposals.APPLIED_VIA_RUN_FIELD
    ):
        values = (_schema_node(path) or {}).get("enum")
        current = _seed_value(_SEED_RUN_DRAFT, path)
        if isinstance(values, list) and current in values and len(values) >= 4:
            return path
    raise AssertionError(
        "no run-scoped `run_field` proposal target is a schema enum of four or more "
        "members that the seed run draft already holds a value at"
    )


def _pick_override_target() -> str:
    """The lowest-sorting ``run_override`` target the RECORD holds a string at.

    A string with no enum, so a proposed value is a free correction rather than a
    choice from a closed set — deliberately the OTHER shape from the run-field target
    above, so the two legs of this file do not accidentally test one kind of value
    twice.
    """
    for path in sorted(
        p
        for p, w in _run_scoped_targets().items()
        if w == proposals.APPLIED_VIA_RUN_OVERRIDE
    ):
        node = _schema_node(path) or {}
        if node.get("type") == "string" and "enum" not in node:
            if isinstance(_seed_value(_SEED_EXPERIMENT_DRAFT, path), str):
                return path
    raise AssertionError(
        "no run-scoped `run_override` proposal target is an unconstrained schema "
        "string the seed experiment draft holds a value at"
    )


#: A run-scoped target written by ``PATCH .../runs/{id}``'s own writer.
RUN_FIELD_TARGET = _pick_run_field_target()
#: A run-scoped target written as a run's OVERRIDE of a record-level address.
OVERRIDE_TARGET = _pick_override_target()
#: The one record-scoped target, for the control that record scope still behaves.
RECORD_TARGET = sorted(
    p
    for p in routes.PROPOSAL_TARGET_PATHS
    if routes._PROPOSAL_WRITER_SCOPE.get(routes._proposal_writer_for(p)) == "record"
)[0]

#: THREE DISTINCT values at ``RUN_FIELD_TARGET`` plus one for the edit, every one a
#: member of the schema's own enum. Distinctness is what makes "the write landed on
#: the run it names" a different assertion from "the write landed somewhere".
RUN_A_CURRENT = _seed_value(_SEED_RUN_DRAFT, RUN_FIELD_TARGET)
_OTHER_ENUM_VALUES = [
    v for v in (_schema_node(RUN_FIELD_TARGET) or {})["enum"] if v != RUN_A_CURRENT
]
RUN_B_CURRENT, PROPOSED_RUN_VALUE, CORRECTED_RUN_VALUE = _OTHER_ENUM_VALUES[:3]

#: Two distinct values at ``OVERRIDE_TARGET`` — the record's, and the proposed one.
#: Synthetic and unmistakably so; the schema constrains this leaf to `type: string`
#: and nothing more, so no enum can supply it.
RECORD_OVERRIDE_CURRENT = _seed_value(_SEED_EXPERIMENT_DRAFT, OVERRIDE_TARGET)
PROPOSED_OVERRIDE_VALUE = f"{RECORD_OVERRIDE_CURRENT}-SYNTHETIC-RUN-B"


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    return ws


@pytest.fixture()
def armed(workspace, monkeypatch):
    """A deployment that CAN attribute: the fixture verifier, with a subject.

    No shipped deploy artifact sets these two variables (``test_deploy_config.py``
    pins that), so this is deliberately a configuration no deployment has. Without
    it the success leg of acceptance is unreachable and half this file's subject
    matter could not be measured at all.
    """
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


def _app_client() -> TestClient:
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def client(workspace):
    """ORDINARY scope, default configuration — the refusal leg."""
    return _app_client()


@pytest.fixture()
def armed_client(armed):
    """ORDINARY scope, fixture verifier — the only leg on which acceptance succeeds."""
    return _app_client()


@pytest.fixture()
def two_runs(workspace):
    """An exportable record with TWO runs and one note, in the ordinary scope.

    Both runs start from the SAME seed run draft, and run B is then moved to a
    different value at ``RUN_FIELD_TARGET``. That difference is load-bearing: with
    two identical runs, "the write landed on the run it names" and "the write landed
    on some run" are the same assertion.
    """
    experiment_draft, run_draft = _split_full_draft()
    exp = ws.create_experiment(
        "Run-scoped proposal lifecycle", {"kind": "synthetic"}, experiment_draft
    )
    exp.add_run(label="Run A", draft=copy.deepcopy(run_draft))
    run_b_draft = copy.deepcopy(run_draft)
    run_b_draft["fields"][RUN_FIELD_TARGET] = {
        "value": RUN_B_CURRENT,
        "status": "verified",
        "evidence": [
            user_confirmation(
                f"Value for {RUN_FIELD_TARGET} on this run?",
                RUN_B_CURRENT,
                "2026-09-01T00:00:00Z",
            )
        ],
        "unit": (run_draft["fields"].get(RUN_FIELD_TARGET) or {}).get("unit"),
    }
    if run_b_draft["fields"][RUN_FIELD_TARGET]["unit"] is None:
        del run_b_draft["fields"][RUN_FIELD_TARGET]["unit"]
    exp.add_run(label="Run B", draft=run_b_draft)
    exp.capture_note(text=NOTE_TEXT, source="typed_note")
    exp.save_versioned()
    return ws.load_experiment(exp.id)


# --- helpers ------------------------------------------------------------------


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, eid: str, run_id: str) -> str:
    """THE RUN's ETag. ``PATCH``/``overrides`` take it, not the record's."""
    response = client.get(f"/api/experiments/{eid}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_body(client, eid: str, run_id: str) -> dict:
    """The untargeted run's WHOLE served document, for a whole-body comparison."""
    response = client.get(f"/api/experiments/{eid}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _propose(client, exp, *, run_id, path, value, **body):
    body.setdefault("note_id", exp.notes[0].id)
    body.setdefault("target_field_path", path)
    body.setdefault("proposed_value", value)
    body.setdefault("rule", "the number the note gives for this run")
    if run_id is not None:
        body.setdefault("run_id", run_id)
    return client.post(
        f"/api/experiments/{exp.id}/proposals",
        json=body,
        headers={"If-Match": _etag(client, exp.id)},
    )


def _proposed(client, exp, **kwargs) -> dict:
    response = _propose(client, exp, **kwargs)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["deduplicated"] is False, "this setup must MINT, not reuse"
    return payload["proposal"]


def _review(client, eid: str, pid: str, *, if_match=..., **body):
    body.setdefault("confirmed_by_user", True)
    tag = _etag(client, eid) if if_match is ... else if_match
    headers = {} if tag is None else {"If-Match": tag}
    return client.post(
        f"/api/experiments/{eid}/proposals/{pid}/review", json=body, headers=headers
    )


def _runs(client, eid: str) -> list[dict]:
    response = client.get(f"/api/experiments/{eid}/runs")
    assert response.status_code == 200, response.text
    return response.json()["runs"]


def _authoritative_snapshot(exp) -> str:
    """Contract **I1**'s exact shape: every export unit's draft, every run resolved."""
    return json.dumps(
        {
            "export": [unit.draft for unit in exp.export_units()],
            "resolved": [exp.resolved_run_draft(run) for run in exp.sorted_runs()],
            "draft": exp.draft,
        },
        sort_keys=True,
        default=str,
    )


def _exported_bytes(exp) -> str:
    """Every official record this experiment would export, deterministically."""
    return json.dumps(
        [
            transform(
                unit.draft,
                record_id="01JQZZ2EXPORT000000000000" + str(index),
                now="2026-01-01T00:00:00Z",
            )
            for index, unit in enumerate(exp.export_units())
        ],
        sort_keys=True,
    )


def _changes(client, eid: str, **params) -> dict:
    response = client.get(f"/api/experiments/{eid}/changes", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _accept(client, exp, run_id, *, path=RUN_FIELD_TARGET, value=PROPOSED_RUN_VALUE):
    """Propose and accept one run-scoped value; returns ``(proposal, response)``."""
    proposal = _proposed(client, exp, run_id=run_id, path=path, value=value)
    response = _review(
        client,
        exp.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    return proposal, response


# --- the derivation itself ----------------------------------------------------


def test_the_derivation_is_not_vacuous_and_agrees_with_the_wire(client, two_runs):
    """The run-scoped set is real, non-empty, and is what the operation SERVES.

    The two targets this file uses are computed from ``_proposal_writer_for``; the
    list operation publishes ``record_scoped_target_field_paths``. If the two ever
    disagreed, every other test here would be aiming at a path the routes classify
    differently from the way this file believes they do — and would still pass, for
    the wrong reason.
    """
    listed = client.get(f"/api/experiments/{two_runs.id}/proposals")
    assert listed.status_code == 200, listed.text
    body = listed.json()

    served_all = set(body["target_field_paths"])
    served_record = set(body["record_scoped_target_field_paths"])
    served_run = served_all - served_record

    assert served_run == set(_run_scoped_targets()), (
        "the run-scoped set this file derives is not the complement of what the "
        "operation serves as record-scoped"
    )
    assert len(served_run) >= 2, "a two-writer proof needs at least two run targets"
    assert RUN_FIELD_TARGET in served_run
    assert OVERRIDE_TARGET in served_run
    assert RECORD_TARGET in served_record
    assert (
        routes._proposal_writer_for(RUN_FIELD_TARGET) == proposals.APPLIED_VIA_RUN_FIELD
    )
    assert (
        routes._proposal_writer_for(OVERRIDE_TARGET)
        == proposals.APPLIED_VIA_RUN_OVERRIDE
    )


def test_the_two_runs_hold_distinguishable_values_at_the_target(client, two_runs):
    """The fixture's premise, asserted rather than assumed.

    Every isolation claim below rests on the two runs differing at the target. If
    they ever became equal, those tests would pass while proving nothing, and the
    failure would surface as an unrelated assertion much later.
    """
    run_a, run_b = _runs(client, two_runs.id)
    assert run_a["label"] == "Run A" and run_b["label"] == "Run B"
    a = run_a["fields"][RUN_FIELD_TARGET]["value"]
    b = run_b["fields"][RUN_FIELD_TARGET]["value"]
    assert a == RUN_A_CURRENT
    assert b == RUN_B_CURRENT
    assert a != b != PROPOSED_RUN_VALUE != a, (
        "the two runs' current values and the proposed value must be three distinct "
        "values, or a read of the wrong run is undetectable"
    )


# --- 1. creation has no export side effect ------------------------------------


def test_1_creating_a_run_scoped_proposal_has_no_export_side_effect(
    client, two_runs, tmp_path
):
    """Contract **I1**/**I2**, at RUN scope on a record with two runs.

    MUTATION: added ``_apply_run_field(run.draft["fields"], target_field_path,
    proposed_value, ...)`` immediately after ``exp.add_proposal(proposal)`` in the
    create route; this test went RED.
    """
    before_snapshot = _authoritative_snapshot(two_runs)
    before_export = _exported_bytes(two_runs)
    run_a, run_b = _runs(client, two_runs.id)
    before_a, before_b = (
        _run_body(client, two_runs.id, run_a["id"]),
        _run_body(client, two_runs.id, run_b["id"]),
    )

    proposal = _proposed(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    assert proposal["run_id"] == run_a["id"]
    assert proposal["state"] == proposals.STATE_OPEN
    assert proposal["is_field_value"] is False
    assert proposal["applied"] is False

    stored = ws.load_experiment(two_runs.id)
    assert _authoritative_snapshot(stored) == before_snapshot
    assert _exported_bytes(stored) == before_export
    assert _run_body(client, two_runs.id, run_a["id"]) == before_a
    assert _run_body(client, two_runs.id, run_b["id"]) == before_b

    detail = client.get(f"/api/experiments/{two_runs.id}").json()
    assert detail["exported"] is False
    assert detail["record_id"] is None

    artifacts = client.get(f"/api/experiments/{two_runs.id}/artifacts").json()
    assert artifacts["record"] is None
    assert artifacts["sidecar"] is None
    assert artifacts["record_filename"] is None

    # NOT "no record inside the experiment directory" — the whole workspace, because
    # an export writes where the exporter says, not where this test guesses.
    written = sorted(p.name for p in tmp_path.rglob("*.json"))
    assert not any(name.endswith(".evidence.json") for name in written), written


def test_1_the_no_side_effect_comparison_is_not_vacuous(client, two_runs):
    """NEGATIVE CONTROL: the same comparison goes RED on a real write.

    Without this, a snapshot function that returned a constant would make the test
    above green forever.
    """
    before = _authoritative_snapshot(two_runs)
    run_a = _runs(client, two_runs.id)[0]
    response = client.patch(
        f"/api/experiments/{two_runs.id}/runs/{run_a['id']}",
        json={"confirmed_by_user": True, "fields": {RUN_FIELD_TARGET: CORRECTED_RUN_VALUE}},
        headers={"If-Match": _run_etag(client, two_runs.id, run_a["id"])},
    )
    assert response.status_code == 200, response.text
    assert _authoritative_snapshot(ws.load_experiment(two_runs.id)) != before


# --- 2. the proposal survives a new request and a reload ----------------------


def test_2_the_proposal_survives_a_new_request_and_a_store_reload(client, two_runs):
    """A second process's view of the same record carries the proposal verbatim.

    The durable PostgreSQL round trip is proven in
    ``apps/api/tests/test_proposal_durability.py`` (``@real_engine``, CI only). This
    is the filesystem half and the part any developer can run.
    """
    run_a = _runs(client, two_runs.id)[0]
    created = _proposed(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )

    fresh = _app_client()  # a new app instance: nothing in memory is shared
    listed = fresh.get(f"/api/experiments/{two_runs.id}/proposals")
    assert listed.status_code == 200, listed.text
    (reread,) = listed.json()["proposals"]

    # BYTE-EQUAL on every key the create response published, not on a chosen few.
    volatile = {"current_target_digest", "target_stale", "still_current"}
    for key, value in created.items():
        if key in volatile:
            continue
        assert reread[key] == value, f"{key} did not survive the round trip"

    stored = ws.load_experiment(two_runs.id)
    (from_store,) = stored.sorted_proposals()
    assert from_store.run_id == run_a["id"]
    assert from_store.target_field_path == RUN_FIELD_TARGET
    assert from_store.proposed_value == PROPOSED_RUN_VALUE


# --- 3. it is listed and readable with its run_id -----------------------------


def test_3_the_proposal_is_listed_and_readable_with_its_run_id(client, two_runs):
    run_a = _runs(client, two_runs.id)[0]
    created = _proposed(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    pid = created["proposal_id"]

    listed = client.get(f"/api/experiments/{two_runs.id}/proposals")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 1
    assert body["unreadable_entries"] == 0
    (row,) = body["proposals"]
    assert row["run_id"] == run_a["id"]

    detail = client.get(f"/api/experiments/{two_runs.id}/proposals/{pid}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["proposal"]["run_id"] == run_a["id"]


# --- 5. the panel's data source distinguishes the two runs --------------------


def test_5_the_run_read_the_review_surface_uses_reports_the_TARGETED_run(
    client, two_runs
):
    """The review surface's "what the record holds now" read, at the source.

    ``IngestionProposalsPanel``'s ``CurrentValue`` branches on ``proposal.run_id``:
    for a run-scoped proposal it calls ``GET .../runs/{run_id}`` and reads the run's
    resolved/own value; for a record-scoped one it reads the record's draft. This
    test measures the RESPONSE that branch depends on — that the two runs report
    different values at the target, and that neither equals the proposed one — so a
    panel reading the wrong run would be showing a value this assertion can name.

    The browser half is ``apps/web/e2e/trusted/proposals-run-scoped.spec.ts``.
    """
    run_a, run_b = _runs(client, two_runs.id)
    _proposed(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )

    a = _run_body(client, two_runs.id, run_a["id"])["run"]
    b = _run_body(client, two_runs.id, run_b["id"])["run"]
    assert a["fields"][RUN_FIELD_TARGET]["value"] == RUN_A_CURRENT
    assert b["fields"][RUN_FIELD_TARGET]["value"] == RUN_B_CURRENT
    assert a["fields"][RUN_FIELD_TARGET]["value"] != PROPOSED_RUN_VALUE

    # The override target resolves through `inherited`, which is the OTHER branch of
    # the same panel read, so both are measured rather than one standing in.
    address = ws.field_address(OVERRIDE_TARGET)
    assert address in a["inherited"], sorted(a["inherited"])
    assert a["inherited"][address]["state"] == "inherited"


# --- 6. there is no in-place edit; the edited acceptance is the edit primitive -


def test_6_no_operation_edits_a_stored_proposal_in_place(client, two_runs):
    """MEASURED, and reported rather than assumed: the proposal is immutable.

    The charter for this file asked for "the edit primitive the API offers before
    acceptance". There is none, and that is the contract's design (§3): a proposal
    records what was proposed, and a different view is a NEW proposal with its own
    id and its own audit trail. The two operations that exist on a stored proposal
    are the read and the review. ``PATCH`` and ``PUT`` are not routed.
    """
    run_a = _runs(client, two_runs.id)[0]
    created = _proposed(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    url = f"/api/experiments/{two_runs.id}/proposals/{created['proposal_id']}"
    for method in ("PATCH", "PUT", "DELETE"):
        response = client.request(
            method, url, json={"proposed_value": CORRECTED_RUN_VALUE}
        )
        assert response.status_code == 405, (
            f"{method} {url} answered {response.status_code}; an in-place edit of a "
            f"stored proposal must not exist"
        )
    stored = ws.load_experiment(two_runs.id).sorted_proposals()[0]
    assert stored.proposed_value == PROPOSED_RUN_VALUE


def test_6_an_edited_acceptance_writes_the_CORRECTED_value_to_one_run_only(
    armed_client, two_runs
):
    """The edit primitive that DOES exist, and its isolation.

    MUTATION: replaced ``accepted_value = body["value"]`` with ``accepted_value =
    proposal.proposed_value``; this test went RED.
    """
    run_a, run_b = _runs(armed_client, two_runs.id)
    before_b = _run_body(armed_client, two_runs.id, run_b["id"])

    created = _proposed(
        armed_client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        action="accept",
        accepted_from="edited",
        value=CORRECTED_RUN_VALUE,
    )
    assert response.status_code == 200, response.text
    reviewed = response.json()["proposal"]
    assert reviewed["accepted_from"] == "edited"
    assert reviewed["accepted_value"] == CORRECTED_RUN_VALUE
    assert reviewed["proposed_value"] == PROPOSED_RUN_VALUE, (
        "an edited acceptance must not rewrite what was PROPOSED — the two are "
        "different claims and the history has to keep both"
    )

    after_a = _run_body(armed_client, two_runs.id, run_a["id"])["run"]
    assert after_a["fields"][RUN_FIELD_TARGET]["value"] == CORRECTED_RUN_VALUE
    assert _run_body(armed_client, two_runs.id, run_b["id"]) == before_b


def test_6_superseding_writes_nothing_to_either_run(client, two_runs):
    """The pre-acceptance "change my mind" path needs no actor and writes nothing."""
    run_a, run_b = _runs(client, two_runs.id)
    before = _authoritative_snapshot(two_runs)
    created = _proposed(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    response = _review(
        client,
        two_runs.id,
        created["proposal_id"],
        action="supersede",
        reason="a better reading of the same note",
    )
    assert response.status_code == 200, response.text
    assert response.json()["proposal"]["state"] == proposals.STATE_SUPERSEDED
    assert _authoritative_snapshot(ws.load_experiment(two_runs.id)) == before


# --- 7 & 8. acceptance changes ONLY the targeted run --------------------------


@pytest.mark.parametrize(
    "path,value,expected_writer",
    [
        (RUN_FIELD_TARGET, PROPOSED_RUN_VALUE, proposals.APPLIED_VIA_RUN_FIELD),
        (OVERRIDE_TARGET, PROPOSED_OVERRIDE_VALUE, proposals.APPLIED_VIA_RUN_OVERRIDE),
    ],
    ids=["run_field", "run_override"],
)
def test_7_and_8_acceptance_writes_the_named_run_and_the_other_is_document_identical(
    armed_client, two_runs, path, value, expected_writer
):
    """BOTH run-scoped writer classes, on a record with two runs.

    The untargeted run's WHOLE served document is compared, not chosen keys — and
    it is DOCUMENT-IDENTICAL: every key of ``GET .../runs/{id}`` equal, including
    ``version``, ``rev`` and ``updated_utc``, because a run's version token is the
    RUN's ``<generation>.<rev>`` and not the record's. Nothing about the record's
    revision moving touches it.

    "DOCUMENT-IDENTICAL" AND NOT "BYTE-IDENTICAL", which an earlier revision of this
    docstring said. The comparison is ``==`` over the parsed JSON, so it is equality
    of every key and value and NOT of the response bytes: a key reordering or a
    whitespace change would pass it. That is the right comparison here — the claim
    is about the run's CONTENT — but the two are different claims and the stronger
    word was not the one being measured. (``_authoritative_snapshot`` elsewhere in
    this file IS a byte comparison, over ``json.dumps(..., sort_keys=True)``, and
    keeps that word.)

    MUTATION: inserted ``run = exp.sorted_runs()[0]`` at the top of
    ``_apply_accepted_proposal``'s run-field branch; the ``run_field`` case went RED.
    (The parametrisation deliberately targets the SECOND run, which is what makes
    "the first run" a wrong answer rather than an accidentally right one.)
    """
    run_a, run_b = _runs(armed_client, two_runs.id)
    target, other = run_b, run_a  # deliberately the SECOND run, not the first
    before_other = _run_body(armed_client, two_runs.id, other["id"])

    created = _proposed(
        armed_client, two_runs, run_id=target["id"], path=path, value=value
    )
    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text
    reviewed = response.json()["proposal"]
    assert reviewed["state"] == proposals.STATE_ACCEPTED
    assert reviewed["applied_via"] == expected_writer
    assert reviewed["applied_run_id"] == target["id"]
    assert reviewed["accepted_value"] == value

    after_other = _run_body(armed_client, two_runs.id, other["id"])
    assert after_other == before_other, (
        "the run this proposal did not name was modified; the differing keys are "
        + json.dumps(
            [
                k
                for k in set(after_other["run"]) | set(before_other["run"])
                if after_other["run"].get(k) != before_other["run"].get(k)
            ]
        )
    )

    after_target = _run_body(armed_client, two_runs.id, target["id"])["run"]
    if expected_writer == proposals.APPLIED_VIA_RUN_FIELD:
        assert after_target["fields"][path]["value"] == value
    else:
        entry = after_target["inherited"][ws.field_address(path)]
        assert entry["state"] == "overridden"
        assert entry["payload"]["value"] == value


def test_the_isolation_comparison_is_not_vacuous(armed_client, two_runs):
    """NEGATIVE CONTROL for the whole-body comparison above.

    Two accepts, one per run. The "other run is document-identical" comparison must
    go RED when the other run really has been written — otherwise a comparison that
    always passed would make every isolation claim in this file worthless.
    """
    run_a, run_b = _runs(armed_client, two_runs.id)
    before_b = _run_body(armed_client, two_runs.id, run_b["id"])

    _, first = _accept(armed_client, two_runs, run_a["id"])
    assert first.status_code == 200, first.text
    assert _run_body(armed_client, two_runs.id, run_b["id"]) == before_b

    _, second = _accept(armed_client, two_runs, run_b["id"], value=CORRECTED_RUN_VALUE)
    assert second.status_code == 200, second.text
    assert _run_body(armed_client, two_runs.id, run_b["id"]) != before_b


def test_the_default_configuration_still_refuses_acceptance(client, two_runs):
    """Contract **I4**, at run scope, in the SAME file as the success leg.

    Both are real behaviour, and a file that could only reach one of them would be
    asserting half the contract. This is what every shipped deployment does.
    """
    run_a = _runs(client, two_runs.id)[0]
    before = _authoritative_snapshot(two_runs)
    created = _proposed(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    response = _review(
        client,
        two_runs.id,
        created["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "human_actor_required"
    assert _authoritative_snapshot(ws.load_experiment(two_runs.id)) == before


def test_a_removed_target_run_refuses_acceptance_and_writes_nothing(
    armed_client, two_runs
):
    """``409 target_run_removed`` — reachable only where a record HAS two runs.

    On a one-run record, removing the run leaves nothing to compare against and the
    record itself changes shape; with two runs the survivor is right there and can
    be shown untouched. Removal does not renumber, so the id is never reissued and
    the proposal is never re-aimed.
    """
    run_a, run_b = _runs(armed_client, two_runs.id)
    created = _proposed(
        armed_client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    # `POST .../runs/{id}/remove`, not a `DELETE` — the operation is deliberately a
    # POST because removing a run rewrites the RECORD's document, and it takes the
    # RECORD's ETag for the same reason.
    removed = armed_client.post(
        f"/api/experiments/{two_runs.id}/runs/{run_a['id']}/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(armed_client, two_runs.id)},
    )
    assert removed.status_code == 200, removed.text

    before_b = _run_body(armed_client, two_runs.id, run_b["id"])
    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "target_run_removed"
    assert body["run_id"] == run_a["id"]
    assert _run_body(armed_client, two_runs.id, run_b["id"]) == before_b

    # It stays clearable: withdrawing needs no run and no actor.
    withdrawn = _review(
        armed_client, two_runs.id, created["proposal_id"], action="withdraw"
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["proposal"]["state"] == proposals.STATE_WITHDRAWN


# --- 9. preconditions ---------------------------------------------------------


def test_9_a_missing_if_match_is_428_when_an_actor_EXISTS(armed_client, two_runs):
    """The ordering the default deployment can never show.

    ``routes.post_proposal_review`` runs the attributability gate BEFORE
    ``_check_if_match``, so in every default deployment an ``accept`` with no
    ``If-Match`` answers ``409 human_actor_required`` and the ``428`` this
    operation documents is unreachable. Under the fixture verifier the actor exists,
    the gate passes, and the ``428`` is finally observable. Both halves of that
    published ordering are therefore measured somewhere, rather than one of them
    being taken on trust.
    """
    run_a = _runs(armed_client, two_runs.id)[0]
    created = _proposed(
        armed_client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    before = _authoritative_snapshot(two_runs)
    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        if_match=None,
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 428, response.text
    assert response.json()["error"] == "precondition_required"
    assert _authoritative_snapshot(ws.load_experiment(two_runs.id)) == before


def test_9_a_stale_if_match_is_412_and_carries_the_current_token(
    armed_client, two_runs
):
    run_a = _runs(armed_client, two_runs.id)[0]
    stale = _etag(armed_client, two_runs.id)
    created = _proposed(
        armed_client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )  # this create itself moves the record's version
    before = _authoritative_snapshot(ws.load_experiment(two_runs.id))

    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        if_match=stale,
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 412, response.text
    body = response.json()
    assert body["error"] == "stale_write"
    current = _etag(armed_client, two_runs.id).strip('"')
    assert current in json.dumps(body), (
        "a 412 must hand back the token to retry with; the body carried none: "
        + json.dumps(body)
    )
    assert _authoritative_snapshot(ws.load_experiment(two_runs.id)) == before


def test_9_a_moved_target_is_409_proposal_stale_and_the_other_run_is_untouched(
    armed_client, two_runs
):
    """The target digest, not the record revision — and only the NAMED run's target.

    MUTATION: replaced ``current != proposal.target_digest`` with
    ``proposal.base_rev != exp.rev``. This test still PASSED — which is the point:
    it cannot tell the two apart on its own. Its pair,
    ``test_9_an_unrelated_write_does_NOT_make_the_proposal_stale``, went RED, and
    the two together are what make the digest claim mean anything.
    """
    run_a, run_b = _runs(armed_client, two_runs.id)
    created = _proposed(
        armed_client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )

    moved = armed_client.patch(
        f"/api/experiments/{two_runs.id}/runs/{run_a['id']}",
        json={"confirmed_by_user": True, "fields": {RUN_FIELD_TARGET: CORRECTED_RUN_VALUE}},
        headers={"If-Match": _run_etag(armed_client, two_runs.id, run_a["id"])},
    )
    assert moved.status_code == 200, moved.text

    listed = armed_client.get(f"/api/experiments/{two_runs.id}/proposals").json()
    assert listed["proposals"][0]["target_stale"] is True

    before_b = _run_body(armed_client, two_runs.id, run_b["id"])
    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "proposal_stale"
    assert body["run_id"] == run_a["id"]
    assert body["target_field_path"] == RUN_FIELD_TARGET

    after_a = _run_body(armed_client, two_runs.id, run_a["id"])["run"]
    assert after_a["fields"][RUN_FIELD_TARGET]["value"] == CORRECTED_RUN_VALUE, (
        "the refusal must leave the NEWER value in place, not the proposed one"
    )
    assert _run_body(armed_client, two_runs.id, run_b["id"]) == before_b


def test_9_an_unrelated_write_does_NOT_make_the_proposal_stale(armed_client, two_runs):
    """The pair to the test above: staleness is the TARGET's, not the record's.

    Writing the OTHER run moves the record's revision and touches the proposal's
    target not at all, so the acceptance must still succeed. Without this, a
    precondition that refused everything would look correct.
    """
    run_a, run_b = _runs(armed_client, two_runs.id)
    created = _proposed(
        armed_client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    moved = armed_client.patch(
        f"/api/experiments/{two_runs.id}/runs/{run_b['id']}",
        json={"confirmed_by_user": True, "fields": {RUN_FIELD_TARGET: CORRECTED_RUN_VALUE}},
        headers={"If-Match": _run_etag(armed_client, two_runs.id, run_b["id"])},
    )
    assert moved.status_code == 200, moved.text

    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text
    after_a = _run_body(armed_client, two_runs.id, run_a["id"])["run"]
    assert after_a["fields"][RUN_FIELD_TARGET]["value"] == PROPOSED_RUN_VALUE


# --- 10. attribution ----------------------------------------------------------


def test_10_the_acceptance_history_carries_the_fixture_subject_and_trust_basis(
    armed_client, two_runs
):
    """Who accepted it, on what basis — and what the WRITTEN value does NOT carry.

    MUTATION: replaced ``actor_subject = identity_module.stamp_actor(identity,
    scope)`` with ``actor_subject = None``; this test went RED.
    """
    run_a = _runs(armed_client, two_runs.id)[0]
    _, response = _accept(armed_client, two_runs, run_a["id"])
    assert response.status_code == 200, response.text
    reviewed = response.json()["proposal"]

    (accept_act,) = [h for h in reviewed["history"] if h["action"] == "accept"]
    assert accept_act["actor_subject"] == ACTOR
    assert accept_act["actor_trust_basis"] == identity.TRUST_BASIS_TEST_FIXTURE
    assert accept_act["from_state"] == proposals.STATE_OPEN
    assert accept_act["to_state"] == proposals.STATE_ACCEPTED
    assert reviewed["accepted_by"]["subject"] == ACTOR
    assert reviewed["accepted_by"]["attributed"] is True

    # The PROPOSING act is still unattributed: nobody was named when it was made.
    (propose_act,) = [h for h in reviewed["history"] if h["action"] == "propose"]
    assert propose_act["actor_subject"] is None

    written = _run_body(armed_client, two_runs.id, run_a["id"])["run"]["fields"][
        RUN_FIELD_TARGET
    ]
    assert ACTOR not in json.dumps(written), (
        "the actor's name must not travel into the scientific value's envelope; "
        "attribution lives on the proposal's history: " + json.dumps(written)
    )


def test_10_the_written_run_field_records_a_user_confirmation(armed_client, two_runs):
    """Contract **I3**: the same envelope manual entry produces, not a second one."""
    run_a = _runs(armed_client, two_runs.id)[0]
    _, response = _accept(armed_client, two_runs, run_a["id"])
    assert response.status_code == 200, response.text

    envelope = _run_body(armed_client, two_runs.id, run_a["id"])["run"]["fields"][
        RUN_FIELD_TARGET
    ]
    assert envelope["value"] == PROPOSED_RUN_VALUE
    assert envelope["status"] == "verified"
    kinds = [e.get("source_type") for e in envelope["evidence"]]
    assert "user_confirmation" in kinds, envelope
    (confirmation,) = [
        e for e in envelope["evidence"] if e.get("source_type") == "user_confirmation"
    ]
    assert set(confirmation) == {"source_type", "question", "answer", "timestamp"}, (
        "the four-key `user_confirmation` shape `complete.py` mints, exactly: "
        + json.dumps(confirmation)
    )
    assert str(PROPOSED_RUN_VALUE) in str(confirmation["answer"])


def test_10_the_override_acceptance_records_what_it_displaced(armed_client, two_runs):
    """The other writer class's evidence, which is a different shape of claim."""
    run_a = _runs(armed_client, two_runs.id)[0]
    created = _proposed(
        armed_client,
        two_runs,
        run_id=run_a["id"],
        path=OVERRIDE_TARGET,
        value=PROPOSED_OVERRIDE_VALUE,
    )
    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text

    entry = _run_body(armed_client, two_runs.id, run_a["id"])["run"]["inherited"][
        ws.field_address(OVERRIDE_TARGET)
    ]
    assert entry["state"] == "overridden"
    assert entry["payload"]["value"] == PROPOSED_OVERRIDE_VALUE
    assert entry["inherited_payload"]["value"] != PROPOSED_OVERRIDE_VALUE, (
        "an override must record what it DISPLACED, or the record's own value is "
        "silently gone"
    )
    kinds = [e.get("source_type") for e in entry["payload"]["evidence"]]
    assert "user_confirmation" in kinds, entry["payload"]


# --- 11. the change feed ------------------------------------------------------


def test_11_the_feed_reports_the_proposal_and_the_targeted_run_above_the_cursor(
    armed_client, two_runs
):
    """A cursor taken before the accept; the entries after it; no duplicate, no loss.

    The untargeted run must NOT appear above that cursor — which is the change
    feed's own statement of the isolation the run bodies proved directly.

    MUTATION: made ``_apply_accepted_proposal``'s run-field branch loop over
    ``exp.sorted_runs()`` and write every one; this test went RED on the
    ``("run", run_b) not in kinds`` assertion.
    """
    run_a, run_b = _runs(armed_client, two_runs.id)
    created = _proposed(
        armed_client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )

    # Drain the feed to a cursor that sits AFTER the create and BEFORE the accept.
    page = _changes(armed_client, two_runs.id, limit=200)
    assert page["has_more"] is False, "the drain must reach the end, or the cursor lies"
    cursor = page["next_cursor"]

    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text

    after = _changes(armed_client, two_runs.id, cursor=cursor, limit=200)
    entries = after["changes"]
    kinds = {(e["kind"], e["entity_id"]): e for e in entries}
    assert len(kinds) == len(entries), "the feed returned a duplicate entry"

    proposal_entry = kinds[("proposal", created["proposal_id"])]
    assert proposal_entry["state"] == proposals.STATE_ACCEPTED
    run_entry = kinds[("run", run_a["id"])]
    assert ("run", run_b["id"]) not in kinds, (
        "the run this proposal did not name appeared in the post-accept window: "
        + json.dumps(entries)
    )

    floor = max(e["changed_at_rev"] for e in page["changes"]) if page["changes"] else 0
    assert proposal_entry["changed_at_rev"] > floor
    assert run_entry["changed_at_rev"] > floor
    assert proposal_entry["changed_at_rev"] == run_entry["changed_at_rev"], (
        "one write stamps every entity it changed with the same sequence position"
    )


def test_11_paging_one_entry_at_a_time_loses_and_duplicates_nothing(
    armed_client, two_runs
):
    """The page boundary, walked at ``limit=1``.

    ``changed_at_rev`` ties are broken by ``(kind, entity_id)``; without the
    tie-break a boundary could reorder between two requests, and the accept is
    exactly the case that produces a tie — the proposal and its run share a
    position.
    """
    run_a = _runs(armed_client, two_runs.id)[0]
    _, response = _accept(armed_client, two_runs, run_a["id"])
    assert response.status_code == 200, response.text

    whole = _changes(armed_client, two_runs.id, limit=200)
    assert whole["has_more"] is False

    walked: list[tuple] = []
    cursor = None
    for _ in range(len(whole["changes"]) + 5):
        page = _changes(
            armed_client,
            two_runs.id,
            limit=1,
            **({"cursor": cursor} if cursor else {}),
        )
        walked.extend((e["kind"], e["entity_id"], e["changed_at_rev"]) for e in page["changes"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break
    else:  # pragma: no cover - a bounded loop that must terminate
        pytest.fail("paging at limit=1 did not terminate")

    expected = [
        (e["kind"], e["entity_id"], e["changed_at_rev"]) for e in whole["changes"]
    ]
    assert walked == expected, (
        "one-at-a-time paging did not reproduce the single-page order exactly"
    )
    assert len(set(walked)) == len(walked), "paging duplicated an entry"


# --- 12. rejection ------------------------------------------------------------


def test_12_rejecting_leaves_both_runs_unchanged(client, two_runs):
    """It needs no actor — so it works in every deployment — and it writes nothing.

    MUTATION: widened the accept branch to ``action in (ACTION_ACCEPT,
    ACTION_REJECT)`` so a rejection fell through to ``_apply_accepted_proposal``;
    this test went RED.
    """
    run_a, run_b = _runs(client, two_runs.id)
    before_a = _run_body(client, two_runs.id, run_a["id"])
    before_b = _run_body(client, two_runs.id, run_b["id"])
    before_snapshot = _authoritative_snapshot(two_runs)

    created = _proposed(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
    )
    response = _review(
        client,
        two_runs.id,
        created["proposal_id"],
        action="reject",
        reason="the note is about the neighbouring campaign, not this run",
    )
    assert response.status_code == 200, response.text
    rejected = response.json()["proposal"]
    assert rejected["state"] == proposals.STATE_REJECTED
    assert rejected["applied"] is False
    assert rejected["applied_run_id"] is None

    assert _run_body(client, two_runs.id, run_a["id"]) == before_a
    assert _run_body(client, two_runs.id, run_b["id"]) == before_b
    assert _authoritative_snapshot(ws.load_experiment(two_runs.id)) == before_snapshot

    # Contract I6: the note behind it is untouched and still listed.
    notes = client.get(f"/api/experiments/{two_runs.id}/notes").json()
    assert any(n["id"] == created["note_id"] for n in notes["notes"])


# --- 13. idempotency ----------------------------------------------------------


def test_13_a_retried_create_with_the_same_client_request_key_returns_the_existing(
    client, two_runs
):
    """DEC-13, at run scope. The claim is exactly-once WITHIN A SCOPE, no more.

    The contract says: *"a key already present on this experiment returns the
    EXISTING proposal instead of minting a second"*. It does NOT claim cross-record
    uniqueness and no constraint enforces one, so this test asserts the scoped
    claim and then shows the same key on a DIFFERENT record minting its own.

    THE SECOND-RECORD LEG IS THE HALF THAT MAKES "WITHIN A SCOPE" A MEASUREMENT
    RATHER THAN A PARAPHRASE, and it was missing from an earlier revision of this
    test while this docstring already claimed it — found by independent review. A
    deduplication that ignored the experiment boundary would satisfy every
    assertion above it, because they all name one record.

    MUTATION: made the create route's deduplication search
    ``[q for other in ws.list_experiments(session_id=scope) for q in
    other.sorted_proposals()]`` instead of ``exp.sorted_proposals()``; the
    second-record leg went RED on exactly its own message, and every assertion above
    it still passed.
    """
    run_a, run_b = _runs(client, two_runs.id)
    key = "synthetic-retry-key-0001"

    first = _propose(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
        client_request_key=key,
    )
    assert first.status_code == 200, first.text
    minted = first.json()
    assert minted["deduplicated"] is False

    second = _propose(
        client,
        two_runs,
        run_id=run_a["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
        client_request_key=key,
    )
    assert second.status_code == 200, second.text
    retried = second.json()
    assert retried["deduplicated"] is True
    assert retried["proposal"]["proposal_id"] == minted["proposal"]["proposal_id"]

    # And a retry that names a DIFFERENT run under the same key still returns the
    # FIRST proposal — the key is the identity, not the body. Stated because the
    # opposite would be a silently mis-targeted proposal.
    third = _propose(
        client,
        two_runs,
        run_id=run_b["id"],
        path=RUN_FIELD_TARGET,
        value=PROPOSED_RUN_VALUE,
        client_request_key=key,
    )
    assert third.status_code == 200, third.text
    assert third.json()["deduplicated"] is True
    assert third.json()["proposal"]["run_id"] == run_a["id"]

    listed = client.get(f"/api/experiments/{two_runs.id}/proposals").json()
    assert listed["total"] == 1, "a retry minted a second proposal"

    # ---- THE SCOPE BOUNDARY ------------------------------------------------
    # A SECOND record, created through the product's own path, given the SAME key.
    # DEC-13 promises exactly-once "within a scope" and rests that on every write to
    # ONE experiment holding `record_lock` — so the key is deliberately not unique
    # across records and no constraint makes it so. This leg is what distinguishes
    # the promise the contract makes from the stronger one it does not.
    other = client.post("/api/experiments", json={"title": "A second record, same key"})
    assert other.status_code == 201, other.text
    other_id = other.json()["id"]
    other_run = client.post(
        f"/api/experiments/{other_id}/runs",
        json={"label": "Run A", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, other_id)},
    )
    assert other_run.status_code == 201, other_run.text
    other_note = client.post(
        f"/api/experiments/{other_id}/notes",
        json={"text": NOTE_TEXT, "source": "typed_note"},
        headers={"If-Match": _etag(client, other_id)},
    )
    assert other_note.status_code == 201, other_note.text

    elsewhere = client.post(
        f"/api/experiments/{other_id}/proposals",
        json={
            "note_id": other_note.json()["note"]["id"],
            "run_id": other_run.json()["run"]["id"],
            "target_field_path": RUN_FIELD_TARGET,
            "proposed_value": PROPOSED_RUN_VALUE,
            "rule": "the number the note gives for this run",
            "client_request_key": key,
        },
        headers={"If-Match": _etag(client, other_id)},
    )
    assert elsewhere.status_code == 200, elsewhere.text
    minted_elsewhere = elsewhere.json()
    assert minted_elsewhere["deduplicated"] is False, (
        "the same `client_request_key` deduplicated ACROSS records. DEC-13 promises "
        "exactly-once within a scope and rests it on the per-record lock; a global "
        "key would silently refuse a legitimate proposal on an unrelated record."
    )
    assert (
        minted_elsewhere["proposal"]["proposal_id"]
        != minted["proposal"]["proposal_id"]
    )
    assert minted_elsewhere["proposal"]["experiment_id"] == other_id

    # ...and neither record now sees the other's.
    assert client.get(f"/api/experiments/{other_id}/proposals").json()["total"] == 1
    assert (
        client.get(f"/api/experiments/{two_runs.id}/proposals").json()["total"] == 1
    )


# --- 14. record scope still behaves ------------------------------------------


def test_14_a_record_scoped_proposal_is_refused_a_run_and_still_works(
    armed_client, two_runs
):
    """The control: the one record-scoped target, on this same two-run record.

    A run-scoped feature that broke record scope would be caught here rather than
    by the other suite happening to run.
    """
    run_a, run_b = _runs(armed_client, two_runs.id)
    allowed = routes._record_enum_fields()[RECORD_TARGET]
    current = ((two_runs.draft.get("fields") or {}).get(RECORD_TARGET) or {}).get("value")
    value = next(v for v in allowed if v != current)

    refused = _propose(
        armed_client,
        two_runs,
        run_id=run_a["id"],
        path=RECORD_TARGET,
        value=value,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "target_is_record_scoped"

    before_a = _run_body(armed_client, two_runs.id, run_a["id"])
    before_b = _run_body(armed_client, two_runs.id, run_b["id"])
    created = _proposed(
        armed_client, two_runs, run_id=None, path=RECORD_TARGET, value=value
    )
    assert created["run_id"] is None

    response = _review(
        armed_client,
        two_runs.id,
        created["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text
    assert response.json()["proposal"]["applied_via"] == proposals.APPLIED_VIA_RECORD_ENUM
    assert response.json()["proposal"]["applied_run_id"] is None

    stored = ws.load_experiment(two_runs.id)
    assert stored.draft["fields"][RECORD_TARGET]["value"] == value
    # Neither RUN's own document moves: the record's field map is not a run's.
    assert _run_body(armed_client, two_runs.id, run_a["id"])["run"]["fields"] == (
        before_a["run"]["fields"]
    )
    assert _run_body(armed_client, two_runs.id, run_b["id"])["run"]["fields"] == (
        before_b["run"]["fields"]
    )


# --- validation and export read the accepted canonical run value -------------


def test_validation_and_the_export_dry_run_read_the_ACCEPTED_run_value(
    armed_client, two_runs
):
    """The point of the whole feature: the value becomes the record's, per run.

    Both runs are dry-run validated. Run A carries the accepted value, run B carries
    its own different one, and each run's official record — produced by the truth
    core's own ``transform`` — carries its own. A write that leaked across runs would
    show up here as two identical official records.
    """
    run_a, run_b = _runs(armed_client, two_runs.id)
    _, response = _accept(armed_client, two_runs, run_a["id"])
    assert response.status_code == 200, response.text

    # `POST .../validate` is the DRY RUN — it runs each unit through the export gate
    # and writes nothing. `POST .../export` would really export, which is a different
    # act and would make this test's subject the artifact rather than the value.
    dry = armed_client.post(f"/api/experiments/{two_runs.id}/validate", json={})
    assert dry.status_code == 200, dry.text
    report = dry.json()
    assert report["dry_run"] is True
    assert report["ok"] is True, json.dumps(report["errors"])
    assert report["official_validator_ran"] is True
    by_run = {r["run_id"]: r for r in report["runs"]}
    assert by_run[run_a["id"]]["ok"] is True
    assert by_run[run_b["id"]]["ok"] is True
    assert ws.load_experiment(two_runs.id).record_id is None, (
        "the dry run must not have exported anything"
    )

    stored = ws.load_experiment(two_runs.id)
    units = {unit.run.id: unit for unit in stored.export_units()}
    # The RUN's own id as `record_id`, which is what the exporter itself uses for a
    # fan-out unit — and the only 26-character upper-alphanumeric value in reach. A
    # hand-written stand-in fails the schema's `^[0-9A-Z]{26}$` and the failure reads
    # like a defect in the record rather than in the test.
    records = {
        run_id: transform(unit.draft, record_id=run_id, now="2026-01-01T00:00:00Z")
        for run_id, unit in units.items()
    }
    a_json, b_json = json.dumps(records[run_a["id"]]), json.dumps(records[run_b["id"]])
    assert str(PROPOSED_RUN_VALUE) in a_json
    assert str(RUN_B_CURRENT) in b_json
    assert str(PROPOSED_RUN_VALUE) not in b_json, (
        "the accepted value reached the run it was never proposed for"
    )

    # And the truth core agrees the run-A record is valid, through the app's own
    # standalone validator route rather than through a second implementation.
    # The operation takes the RECORD as the body, not a wrapper — a `{"record": ...}`
    # envelope validates as a record with one unexpected property and eight missing
    # ones, which reads like a product defect and is a wrong request.
    validated = armed_client.post("/api/validate/record", json=records[run_a["id"]])
    assert validated.status_code == 200, validated.text
    assert validated.json()["ok"] is True, json.dumps(validated.json())


# --- the product's own creation path ------------------------------------------


def test_the_product_s_own_creation_path_reaches_a_run_scoped_proposal(armed_client):
    """create → two runs → note → run-scoped proposal → accept, ALL over HTTP.

    Nothing here is borrowed from a seed or built through the store, which is the
    claim ``proposals.spec.ts`` could not make: it chose the two exported canonical
    records, and an exported record refuses ``POST .../runs`` with ``409
    already_exported_without_runs``. That is a property of THOSE RECORDS. A record
    created through the product's own Create Experiment path takes runs, and this
    walk is the proof.
    """
    created = armed_client.post(
        "/api/experiments", json={"title": "Two runs, one proposal"}
    )
    assert created.status_code == 201, created.text
    eid = created.json()["id"]

    run_ids = []
    for label in ("Run A", "Run B"):
        response = armed_client.post(
            f"/api/experiments/{eid}/runs",
            json={"label": label, "confirmed_by_user": True},
            headers={"If-Match": _etag(armed_client, eid)},
        )
        assert response.status_code == 201, response.text
        run_ids.append(response.json()["run"]["id"])
    assert len(set(run_ids)) == 2

    note = armed_client.post(
        f"/api/experiments/{eid}/notes",
        json={"text": NOTE_TEXT, "source": "typed_note"},
        headers={"If-Match": _etag(armed_client, eid)},
    )
    assert note.status_code == 201, note.text
    note_id = note.json()["note"]["id"]

    proposed = armed_client.post(
        f"/api/experiments/{eid}/proposals",
        json={
            "note_id": note_id,
            "run_id": run_ids[1],
            "target_field_path": RUN_FIELD_TARGET,
            "proposed_value": PROPOSED_RUN_VALUE,
            "rule": "the number the note gives for this run",
        },
        headers={"If-Match": _etag(armed_client, eid)},
    )
    assert proposed.status_code == 200, proposed.text
    pid = proposed.json()["proposal"]["proposal_id"]

    before_a = _run_body(armed_client, eid, run_ids[0])
    accepted = armed_client.post(
        f"/api/experiments/{eid}/proposals/{pid}/review",
        json={
            "confirmed_by_user": True,
            "action": "accept",
            "accepted_from": "candidate",
        },
        headers={"If-Match": _etag(armed_client, eid)},
    )
    assert accepted.status_code == 200, accepted.text
    reviewed = accepted.json()["proposal"]
    assert reviewed["applied_run_id"] == run_ids[1]
    assert reviewed["applied_via"] == proposals.APPLIED_VIA_RUN_FIELD

    assert (
        _run_body(armed_client, eid, run_ids[1])["run"]["fields"][RUN_FIELD_TARGET][
            "value"
        ]
        == PROPOSED_RUN_VALUE
    )
    assert _run_body(armed_client, eid, run_ids[0]) == before_a


def test_the_exported_seed_records_really_do_refuse_a_run(workspace):
    """The measurement the browser spec's claim rests on, kept honest.

    ``proposals.spec.ts`` says an exported record refuses ``POST .../runs``. That is
    true and it is why that file cannot cover run scope — but it is a fact about
    those records, not about the feature, and this asserts the distinction rather
    than leaving the two entangled.
    """
    from conftest import tutorial_client

    from isaac_api.app import create_app

    client = tutorial_client(create_app(), raise_server_exceptions=False)
    listed = client.get("/api/experiments").json()["experiments"]
    exported = [row for row in listed if row.get("record_id")]
    assert exported, "the worked-example session holds no exported record"
    eid = exported[0]["id"]
    response = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "Run C", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "already_exported_without_runs"

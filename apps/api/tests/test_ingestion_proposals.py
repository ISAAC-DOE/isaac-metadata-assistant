"""Persistent ingestion proposals — the model, its persistence, and four operations.

WHAT THIS FEATURE PROMISES, AND WHERE EACH PROMISE IS HELD HERE
===============================================================

``docs/ingestion-proposal-contract.md`` §5 states seven invariants. Each one is a
claim a test can falsify, and each is named below beside the test that falsifies it.

* **I1** — creating a proposal never mutates authoritative metadata.
  ``test_I1_creating_a_proposal_mutates_no_authoritative_metadata``
* **I2** — a proposal is inert to export.
  ``test_I2_a_populated_proposal_list_leaves_the_exported_record_byte_identical``
* **I3** — applying goes through the same service as manual entry.
  ``test_I3_accepting_calls_the_writer_that_owns_the_target`` (all three classes),
  plus the negative controls
  ``test_I3_the_module_contains_no_second_envelope_builder`` and
  ``test_I3_the_module_mints_no_evidence_and_imports_no_truth_core_writer``.
* **I4** — acceptance requires a trusted human identity, and no DEFAULT-configured
  deployment establishes one.
  ``test_I4_accept_is_refused_409_in_a_default_configured_deployment`` and
  ``test_I4_accept_succeeds_and_stamps_the_actor_under_the_fixture_verifier``.
* **I5** — a proposal can never present as a confirmed value.
  ``test_I5_a_proposal_cannot_be_constructed_as_a_verified_value`` and the three
  after it.
* **I6** — nothing captured is discarded.
  ``test_I6_rejecting_a_proposal_leaves_its_note_unchanged_and_still_listed``.
* **I7** — worked-example isolation, in all three of its parts.
  ``test_I7_a_tutorial_proposal_is_invisible_to_the_ordinary_scope``,
  ``test_I7_a_canonical_example_id_is_refused_in_any_scope``,
  ``test_I7_an_acceptance_inside_a_tutorial_session_is_unattributed``.

The thirteen decisions in contract §10 each have a test too; the ``DEC-n`` in a test
name says which.

MUTATION-CHECKED
================

Tests whose docstring carries a ``MUTATION:`` line were verified by BREAKING the
production code in the specific way the test claims to catch, confirming the test
went RED, and reverting the break. A test with no ``MUTATION:`` line was not
mutation-checked and does not claim to have been.

DATA BOUNDARY: none. Everything here is synthetic, written into a ``tmp_path``
workspace. No file outside it is read or written, nothing connects to a database, and
no production-derived content is touched.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.db_write as db_write
import isaac_api.identity as identity
import isaac_api.notes as notes
import isaac_api.proposals as proposals
import isaac_api.revision_history as rhist
import isaac_api.routes as routes
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws
from isaac_records.export import transform
from isaac_records.models import STATUSES, user_confirmation

from conftest import client_ws, tutorial_client
from submission_fake import FakeSubmissionConnection, fake_reader, fake_store
from test_export_fan_out import _split_full_draft

ACTOR = "ada.lovelace"

#: A run-level target and a record-level-override target, taken from the
#: APPLICATION's own derived set rather than written out here. A hand-copied literal
#: would be a second definition of "a real target" and could rot silently into a test
#: that passes for the wrong reason.
RUN_PATH = "context.temperature_K"
OVERRIDE_PATH = "sample.material.name"
#: The one record-scoped target: a closed enum the official schema declares.
RECORD_PATH = "system.technique"
#: A real member of that path's enum, taken from the vendored schema at import
#: rather than written out: a hand-copied literal would be a second copy of the
#: document CLAUDE.md §1 makes the authority, free to rot into a test that passes
#: for the wrong reason.
RECORD_VALUE = routes._record_enum_fields()[RECORD_PATH][0]

NOTE_TEXT = "the pellet was CuO2 and the cell sat at 300 K throughout"


def _module_source() -> str:
    return (
        Path(proposals.__file__).read_text(encoding="utf-8")
    )


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

    No shipped deploy artifact sets these two variables — ``test_deploy_config.py``
    pins that — so this is deliberately a configuration no deployment has. It exists
    because the refusal path and the success path are BOTH real behaviour and a suite
    that could only reach one of them would be asserting half the contract.
    """
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


@pytest.fixture()
def client(workspace):
    """An ORDINARY-scope client. Not a tutorial one — this feature's records are real."""
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def armed_client(armed):
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def experiment(workspace):
    """An experiment with one run, an exportable draft, and one note."""
    experiment_draft, run_draft = _split_full_draft()
    exp = ws.create_experiment(
        "Proposals fixture", {"kind": "synthetic"}, experiment_draft
    )
    exp.add_run(label="Run A", draft=copy.deepcopy(run_draft))
    exp.capture_note(text=NOTE_TEXT, source="typed_note")
    exp.save_versioned()
    return ws.load_experiment(exp.id)


# --- helpers ------------------------------------------------------------------


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _create(client, exp, *, path=OVERRIDE_PATH, value="Cu2O", **body):
    body.setdefault("note_id", exp.notes[0].id)
    body.setdefault("target_field_path", path)
    body.setdefault("proposed_value", value)
    body.setdefault("rule", "the token after `the pellet was` matched a material label")
    if path != RECORD_PATH and "run_id" not in body:
        body["run_id"] = exp.runs[0].id
    return client.post(
        f"/api/experiments/{exp.id}/proposals",
        json=body,
        headers={"If-Match": _etag(client, exp.id)},
    )


def _created(client, exp, **body) -> dict:
    response = _create(client, exp, **body)
    assert response.status_code == 200, response.text
    return response.json()["proposal"]


def _review(client, eid: str, pid: str, *, if_match=..., **body):
    body.setdefault("confirmed_by_user", True)
    tag = _etag(client, eid) if if_match is ... else if_match
    headers = {} if tag is None else {"If-Match": tag}
    return client.post(
        f"/api/experiments/{eid}/proposals/{pid}/review", json=body, headers=headers
    )


def _run_etag(client, eid: str, run_id: str) -> str:
    """THE RUN's ETag. `POST .../runs/{id}/overrides` takes it, not the record's.

    A test that sent the record's got `412 stale_write` reporting a rev the record
    did not have, which reads like a concurrency defect and is not one.
    """
    response = client.get(f"/api/experiments/{eid}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _override(client, eid: str, run_id: str, path: str, value):
    """Write a record-level address on one run, through the ordinary manual route.

    THE ENVELOPE CARRIES A `user_confirmation` ENTRY, and it has to: the override
    route runs the deterministic draft validator over the payload, and
    `{"status": "verified", "evidence": []}` is refused with *"verified field has no
    observed evidence or user confirmation"*. A test that sent the empty-evidence
    shape got a `422` that reads like a route defect and is the no-guessing rule
    working exactly as designed.
    """
    return client.post(
        f"/api/experiments/{eid}/runs/{run_id}/overrides",
        json={
            "confirmed_by_user": True,
            "address": ws.field_address(path),
            "payload": {
                "value": value,
                "status": "verified",
                "evidence": [
                    user_confirmation(
                        f"Value for {path} on this run?",
                        value,
                        "2026-08-29T00:00:00Z",
                    )
                ],
            },
        },
        headers={"If-Match": _run_etag(client, eid, run_id)},
    )


def _stored(eid: str):
    """The experiment as the STORE holds it — never as a response reported it."""
    return ws.load_experiment(eid)


def _exported_bytes(exp) -> str:
    """Every official record this experiment would export, as deterministic JSON.

    ``record_id`` and ``now`` are pinned so the comparison is about the CONTENT and
    not about two different minting moments — which is what makes a byte comparison
    meaningful rather than guaranteed to fail.
    """
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


def _authoritative_snapshot(exp) -> str:
    """The record's exported content plus every run's fully resolved draft.

    Contract **I1**'s exact shape: ``export_draft``'s subject for every unit, and
    ``resolved_run_draft`` for every run, captured byte-for-byte.
    """
    return json.dumps(
        {
            "export": [unit.draft for unit in exp.export_units()],
            "resolved": [exp.resolved_run_draft(run) for run in exp.sorted_runs()],
            "draft": exp.draft,
        },
        sort_keys=True,
        default=str,
    )


# --- I1: creating a proposal mutates nothing authoritative --------------------


def test_I1_creating_a_proposal_mutates_no_authoritative_metadata(client, experiment):
    """Contract **I1**, in the shape the contract specifies.

    Every export unit's draft AND every run's resolved draft, captured byte-for-byte
    before and after, plus the experiment's own draft. A proposal is a suggestion
    awaiting judgement; if creating one moved a single byte of scientific content,
    the whole feature would be a write path wearing a queue's name.

    MUTATION: made ``post_proposal`` call ``_apply_accepted_proposal`` before saving
    (i.e. applied the value at create time). This assertion went RED on the
    ``resolved`` and ``draft`` keys.
    """
    before = _authoritative_snapshot(experiment)

    proposal = _created(client, experiment)
    assert proposal["state"] == proposals.STATE_OPEN

    after = _authoritative_snapshot(_stored(experiment.id))
    assert after == before, (
        "creating a proposal changed authoritative scientific content. A proposal is "
        "a suggestion, not a write."
    )


def test_I1_creating_a_proposal_does_move_the_record_version(client, experiment):
    """DEC-10, which is the other half of I1 and must not be confused with it.

    A proposal act moves ``rev`` and the ``ETag`` and therefore DOES create a
    revision at the next submit, and that is INTENDED: the proposal is part of what
    the record holds, so a second client holding the pre-change validator must be
    refused rather than silently overwriting the act. The contract asserted the safe
    half and was silent on this one.
    """
    before = _stored(experiment.id).rev
    _created(client, experiment)
    assert _stored(experiment.id).rev == before + 1


# --- I2: a proposal is inert to export ----------------------------------------


def test_I2_a_populated_proposal_list_leaves_the_exported_record_byte_identical(
    client, experiment
):
    """Contract **I2**, made structural by the storage location rather than asserted.

    Proposals live at ``state["proposals"]``, beside ``notes`` and OUTSIDE ``draft``,
    and ``export.transform`` reads only the keys it names. So the exported official
    record cannot carry a proposal — but "cannot" is worth measuring, because the
    alternative location (``conflict_resolution.DRAFT_KEY``, inside the draft) is the
    one the sibling feature chose and would have made this false for a zero-run
    record.

    NOT MUTATION-CHECKED, AND THE ATTEMPT IS RECORDED RATHER THAN THE CLAIM. The
    mutation this test wants is a faithful RELOCATION of the state key into
    ``exp.draft``. Three scratch attempts could not achieve one: moving the read, the
    write and the signature entry together broke hydration first
    (``len(reloaded.proposals)`` went to 0), so the test went RED for a reason that
    was not the property. A mutation that breaks the fixture measures nothing, and an
    earlier revision of this docstring asserted the OPPOSITE outcome — this test
    green, the signature test red — from reasoning rather than from a run.

    What IS measured, and is decisive on its own, is the assertion below: the
    proposal payload is injected into a copy of every export unit's draft and
    ``transform`` is shown to produce the identical record. That is the property
    stated directly rather than through a mutant, and it holds for BOTH reasons at
    once — the key is not in the draft, and ``transform`` would ignore it if it were.
    """
    before = _exported_bytes(experiment)
    for index in range(3):
        _created(client, experiment, value=f"Cu{index}O")
    reloaded = _stored(experiment.id)
    assert len(reloaded.proposals) == 3
    assert _exported_bytes(reloaded) == before

    # THE DIRECT MEASUREMENT: even a draft that DID carry the key exports identically,
    # because `transform` reads only the keys it names. This is the half a storage
    # move could not take away, asserted rather than argued.
    contaminated = []
    for index, unit in enumerate(reloaded.export_units()):
        draft = copy.deepcopy(unit.draft)
        draft[proposals.STATE_KEY] = [p.to_state() for p in reloaded.proposals]
        contaminated.append(
            transform(
                draft,
                record_id="01JQZZ2EXPORT000000000000" + str(index),
                now="2026-01-01T00:00:00Z",
            )
        )
    assert json.dumps(contaminated, sort_keys=True) == before


def test_I2_a_proposal_is_absent_from_the_submission_content_signature(
    client, experiment
):
    """The half a byte-comparison of the exported record cannot see.

    ``submissions.content_signature`` digests each export unit's fully resolved
    draft. Storing proposals inside the draft would move that digest for a zero-run
    record — which is exactly the disclosure ``conflict_resolution`` has to make
    about ITS key. Storing them beside ``notes`` means there is no such disclosure to
    make, and this test is what keeps that true.
    """
    from isaac_api import submissions

    before = submissions.content_signature(experiment.id, experiment.export_units())
    _created(client, experiment)
    reloaded = _stored(experiment.id)
    assert (
        submissions.content_signature(reloaded.id, reloaded.export_units()) == before
    )


def test_I2_a_proposal_is_absent_from_every_runs_resolved_draft(client, experiment):
    _created(client, experiment)
    exp = _stored(experiment.id)
    for run in exp.sorted_runs():
        resolved = exp.resolved_run_draft(run)
        assert proposals.STATE_KEY not in resolved
        assert "proposals" not in json.dumps(resolved)


# --- I3: applying reuses the writers manual entry already goes through --------


@pytest.mark.parametrize(
    "path,value,writer_name,expected_via",
    [
        (RUN_PATH, 301.0, "_apply_run_field", proposals.APPLIED_VIA_RUN_FIELD),
        (
            OVERRIDE_PATH,
            "Cu2O",
            "set_run_override",
            proposals.APPLIED_VIA_RUN_OVERRIDE,
        ),
        (
            RECORD_PATH,
            RECORD_VALUE,
            "_apply_record_fields",
            proposals.APPLIED_VIA_RECORD_ENUM,
        ),
    ],
)
def test_I3_accepting_calls_the_writer_that_owns_the_target(
    armed_client, experiment, monkeypatch, path, value, writer_name, expected_via
):
    """Contract **I3**, per target class, by NAME.

    Each of the three writers is wrapped and the accept path is required to have
    called it. This is the only form of the claim that means anything: "we reuse the
    manual writer" is unfalsifiable if the test only checks the value landed, because
    a second envelope builder producing the same shape today would pass.

    ``set_run_override`` is patched on the CLASS, because the route reaches it as a
    bound method of the loaded experiment.

    MUTATION: replaced the ``_apply_run_field`` call in ``_apply_accepted_proposal``
    with a hand-built envelope of the identical shape. The value still landed and the
    record still exported; this test went RED on the run-field parameter, and the
    other two stayed green — which is the point of parameterising by class.
    """
    calls: list = []
    if writer_name == "set_run_override":
        original = ws.Experiment.set_run_override

        def spy(self, run, address, payload):
            calls.append((address, payload))
            return original(self, run, address, payload)

        monkeypatch.setattr(ws.Experiment, "set_run_override", spy)
    else:
        original = getattr(routes, writer_name)

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        monkeypatch.setattr(routes, writer_name, spy)

    proposal = _created(armed_client, experiment, path=path, value=value)
    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text
    assert calls, f"the accept path did not call {writer_name}"
    assert response.json()["proposal"]["applied_via"] == expected_via


def test_I3_the_module_contains_no_second_envelope_builder():
    """The negative control the contract names, spelled out HERE and not in the module.

    A second envelope builder is a second definition of "what a confirmed field looks
    like", free to drift from the one the exporter and the draft validator read. The
    two literals below are what building one looks like: the verified-envelope status
    pair, and a call to the truth core's confirmation-entry constructor.

    The strings live in this test rather than in ``proposals.py``'s own docstring,
    because a file that names the thing it must not contain cannot be checked for it.
    """
    source = _module_source()
    assert '"status": "verified"' not in source
    assert "'status': 'verified'" not in source
    assert "user_confirmation(" not in source


def test_I3_the_module_mints_no_evidence_and_imports_no_truth_core_writer():
    """The same claim from the IMPORTS, which the text scan above cannot reach.

    A module that imported ``isaac_records.models.user_confirmation`` and aliased it
    would pass the literal scan. So the import graph is walked instead — over the
    parsed AST, not over the text, because ``proposals.py``'s prose legitimately
    NAMES the truth core when it explains why it does not borrow that package's
    evidence vocabulary. A test that scanned the text would be measuring the
    docstring.

    The whole point is that applying a value is ``routes``' job, through the writers
    manual entry already uses.
    """
    import ast

    tree = ast.parse(_module_source())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(name.startswith("isaac_records") for name in imported), sorted(
        imported
    )
    assert not any("export" in name or "complete" in name for name in imported), sorted(
        imported
    )


# --- I4: acceptance requires a trusted human identity ------------------------


def test_I4_accept_is_refused_409_in_a_default_configured_deployment(
    client, experiment
):
    """Contract **I4** and §10.4, in the exact form the contract insists on.

    "In every DEFAULT-CONFIGURED deployment" — a claim about configuration, not about
    the build. ``FixtureEdgeVerifier`` reaches an actor from the process environment
    and no shipped deploy artifact sets its two variables, so this is the path that
    runs everywhere and the armed test below is the one that does not.

    MUTATION: removed the ``require_human_actor`` call from the accept branch. This
    went RED; the reject test below stayed green, which is the asymmetry DEC-9 wants.
    """
    proposal = _created(client, experiment)
    response = _review(
        client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "human_actor_required"

    stored = _stored(experiment.id).get_proposal(proposal["proposal_id"])
    assert stored.state == proposals.STATE_OPEN, "a refused accept recorded an act"
    assert stored.applied_via is None


def test_I4_accept_succeeds_and_stamps_the_actor_under_the_fixture_verifier(
    armed_client, experiment
):
    """DEC-2: the proposal ROW carries its own trust basis and so says what it is worth.

    That is the submission precedent, not the record-attribution one: an official
    record has no field to qualify an attribution, so a fixture name there would be
    permanent and indistinguishable. A proposal's history row is not that.
    """
    proposal = _created(armed_client, experiment)
    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text
    body = response.json()["proposal"]
    assert body["state"] == proposals.STATE_ACCEPTED
    assert body["accepted_by"]["subject"] == ACTOR
    assert body["accepted_by"]["trust_basis"] == identity.TRUST_BASIS_TEST_FIXTURE
    assert body["accepted_by"]["attributed"] is True


def test_I4_the_written_value_carries_no_actor_name(armed_client, experiment):
    """DEC-2's second half, asserted rather than assumed.

    The VALUE goes through the unchanged manual writers, which stamp no actor, so no
    fixture name can reach an official record however the proposal row is attributed.
    """
    proposal = _created(armed_client, experiment)
    assert (
        _review(
            armed_client,
            experiment.id,
            proposal["proposal_id"],
            action="accept",
            accepted_from="candidate",
        ).status_code
        == 200
    )
    exp = _stored(experiment.id)
    exported = _exported_bytes(exp)
    assert ACTOR not in exported
    assert ACTOR not in json.dumps(
        [exp.resolved_run_draft(run) for run in exp.sorted_runs()], default=str
    )


# --- DEC-9: reject / supersede / withdraw need no actor -----------------------


@pytest.mark.parametrize(
    "action,state",
    [
        ("reject", proposals.STATE_REJECTED),
        ("supersede", proposals.STATE_SUPERSEDED),
        ("withdraw", proposals.STATE_WITHDRAWN),
    ],
)
def test_DEC9_the_three_non_writing_acts_need_no_actor(
    client, experiment, action, state
):
    """DEC-9, and the asymmetry is the point.

    In a deployment that establishes nobody — which is every default one — gating
    these would leave the review queue permanently unclearable. That is the exact
    defect ``conflict_resolution`` was built to fix, and reintroducing it one feature
    over would be worse than not shipping the feature.

    The consequence is disclosed rather than hidden: the act is recorded
    ``unattributed``, which is what it is.
    """
    proposal = _created(client, experiment)
    response = _review(
        client, experiment.id, proposal["proposal_id"], action=action, reason="not this"
    )
    assert response.status_code == 200, response.text
    body = response.json()["proposal"]
    assert body["state"] == state
    assert body["accepted_by"] is None
    last = body["history"][-1]
    assert last["action"] == action
    assert last["actor_subject"] is None
    assert last["actor_trust_basis"] == "unattributed"
    assert last["reason"] == "not this"


def test_DEC9_a_reason_nobody_gave_is_not_invented(client, experiment):
    proposal = _created(client, experiment)
    response = _review(client, experiment.id, proposal["proposal_id"], action="reject")
    assert response.status_code == 200, response.text
    assert response.json()["proposal"]["history"][-1]["reason"] is None


# --- I5: a proposal can never present as a confirmed value --------------------


def _a_proposal(**overrides) -> proposals.IngestionProposal:
    kwargs = {
        "proposal_id": "PROP-1",
        "experiment_id": "EXP-1",
        "note_id": "NOTE-1",
        "target_field_path": OVERRIDE_PATH,
        "proposed_value": "Cu2O",
        "rule": "the label matched",
        "source": "typed_note",
        "proposed_utc": "2026-08-29T00:00:00Z",
        "base_rev": 4,
        "target_digest": proposals.target_digest({"envelope": None, "override": None}),
        "trust_basis": "unattributed",
    }
    kwargs.update(overrides)
    return proposals.new_proposal(**kwargs)


def test_I5_a_proposal_cannot_be_constructed_as_a_verified_value():
    """The four constants are PROPERTIES, so there is no field to set.

    Each route below is a different way a caller could attach the claim, and each has
    to fail for its own reason — a guard that only closed the first would leave the
    other three open. ``notes.py`` enumerates the same five and this is the same
    enforcement, which is why it is checked rather than inherited by assumption.

    MUTATION: turned ``verified`` into an ordinary field ``verified: bool = False``.
    The test went RED at the FIRST route — the constructor keyword — with ``Failed:
    DID NOT RAISE TypeError``. Stated that precisely rather than as "three of the
    four went red", which is what an earlier revision claimed: a test stops at its
    first failing assertion, so a single run measures ONE of the four routes and no
    more. The other three are asserted, not mutation-checked, and this docstring says
    so instead of implying otherwise.
    """
    proposal = _a_proposal()
    with pytest.raises(TypeError):
        proposals.IngestionProposal(  # type: ignore[call-arg]
            proposal_id="X",
            experiment_id="E",
            note_id="N",
            target_field_path=OVERRIDE_PATH,
            proposed_value="v",
            rule="r",
            source="typed_note",
            proposed_utc="t",
            base_rev=0,
            target_digest="d",
            trust_basis="unattributed",
            verified=True,
        )
    with pytest.raises(TypeError):
        dataclasses.replace(proposal, verified=True)  # type: ignore[call-arg]
    with pytest.raises((TypeError, dataclasses.FrozenInstanceError)):
        proposal.verified = True  # type: ignore[misc]
    with pytest.raises(AttributeError):
        object.__setattr__(proposal, "verified", True)
    with pytest.raises(AttributeError):
        object.__setattr__(proposal, "some_new_flag", True)


def test_I5_the_four_constants_cross_the_json_boundary():
    """A consumer reading JSON does not see the class invariant.

    ``FieldCandidate.to_dict`` set this rule and ``Note.to_state`` follows it: the
    guarantee has to survive the boundary rather than stop at it. ``applied`` travels
    with them because a JSON reader cannot tell from a state string that ``accepted``
    is terminal-and-applied.
    """
    state = _a_proposal().to_state()
    assert state["verified"] is False
    assert state["is_evidence"] is False
    assert state["is_field_value"] is False
    assert state["applied"] is False
    assert state["status"] == proposals.PROPOSAL_STATUS


def test_I5_the_proposal_status_is_not_a_draft_envelope_status():
    """Deliberately outside ``isaac_records.models.STATUSES``.

    A reader who keys on the string must see a token that appears nowhere in the
    draft vocabulary, rather than one that quietly reads as ``verified``.
    """
    assert proposals.PROPOSAL_STATUS not in STATUSES


def test_I5_an_accepted_proposal_still_reports_is_field_value_false(
    armed_client, experiment
):
    """The case the invariant is actually about.

    ``ConflictResolution`` already demonstrates that carrying a value does not
    violate this repository's rule — the rule is never PRESENTING as a confirmed
    field value. An accepted proposal holds the value that was written and must still
    report ``false``, or two places would answer "what is this field's value?".
    """
    proposal = _created(armed_client, experiment)
    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text
    body = response.json()["proposal"]
    assert body["accepted_value"] == "Cu2O"
    assert body["is_field_value"] is False
    assert body["verified"] is False
    assert body["is_evidence"] is False
    assert body["applied"] is True


# --- I6: nothing captured is discarded ----------------------------------------


def test_I6_rejecting_a_proposal_leaves_its_note_unchanged_and_still_listed(
    client, experiment
):
    """Contract **I6**, in the shape the contract specifies.

    The verbatim words live on the note; the proposal carries only ``note_id``. So no
    proposal outcome — rejection included — can destroy content, and this is what
    keeps that true rather than merely likely.

    MUTATION: made the reject branch call ``exp.replace_note`` with a dismissed note.
    The note-state assertion went RED.
    """
    note_before = _stored(experiment.id).notes[0].to_state()
    proposal = _created(client, experiment)

    assert (
        _review(
            client, experiment.id, proposal["proposal_id"], action="reject"
        ).status_code
        == 200
    )

    listed = client.get(f"/api/experiments/{experiment.id}/notes")
    assert listed.status_code == 200, listed.text
    ids = [note["id"] for note in listed.json()["notes"]]
    assert note_before["id"] in ids, "the note behind a rejected proposal vanished"
    assert _stored(experiment.id).notes[0].to_state() == note_before


def test_I6_there_is_no_operation_that_deletes_a_proposal(client, experiment):
    """There is no DELETE, and there will not be one.

    Checked against the served OpenAPI document rather than by reading the router, so
    a route added by any means is visible to it.
    """
    spec = client.get("/api/openapi").json()
    for path, methods in spec["paths"].items():
        if "proposal" not in path:
            continue
        assert "delete" not in methods, f"{path} publishes a DELETE"
    proposal = _created(client, experiment)
    for target in (
        f"/api/experiments/{experiment.id}/proposals",
        f"/api/experiments/{experiment.id}/proposals/{proposal['proposal_id']}",
    ):
        assert client.delete(target).status_code in (404, 405)


# --- I7: worked-example isolation ---------------------------------------------


def test_I7_a_tutorial_proposal_is_invisible_to_the_ordinary_scope(workspace):
    """Contract **I7**: a proposal never escapes a worked-example session.

    Every operation takes ``TutorialScopeDep`` and every write holds
    ``record_lock(..., session_id=scope)``, so a proposal is read and written ONLY
    within the scope that owns the record. The negative is what has to be asserted:
    it is not enough that the tutorial client can see its own proposal.

    MUTATION: dropped ``session_id=scope`` from ``list_proposals``' load. The
    ordinary-scope assertion went RED.
    """
    from isaac_api.app import create_app

    app = create_app()
    tclient = tutorial_client(app)
    ordinary = TestClient(app, raise_server_exceptions=False)

    store = client_ws(tclient)
    experiment_draft, run_draft = _split_full_draft()
    exp = store.create_experiment(
        "Tutorial proposal", {"kind": "synthetic"}, experiment_draft
    )
    exp.add_run(label="Run A", draft=copy.deepcopy(run_draft))
    exp.capture_note(text=NOTE_TEXT, source="typed_note")
    exp.save_versioned()
    exp = store.load_experiment(exp.id)

    created = _create(tclient, exp)
    assert created.status_code == 200, created.text
    pid = created.json()["proposal"]["proposal_id"]

    assert tclient.get(f"/api/experiments/{exp.id}/proposals").json()["total"] == 1

    # The ordinary scope cannot see the RECORD at all, which is the strongest form of
    # the isolation and is what the session boundary already guarantees for notes.
    assert ordinary.get(f"/api/experiments/{exp.id}/proposals").status_code == 404
    assert ordinary.get(f"/api/experiments/{exp.id}/proposals/{pid}").status_code == 404
    assert exp.id not in [
        row["id"] for row in ordinary.get("/api/experiments").json()["experiments"]
    ]


def test_I7_a_canonical_example_id_is_refused_in_any_scope(client):
    """The second half: a built-in worked example is not a normal record anywhere.

    ``PostgresOrdinaryStore.refuse_if_not_persistable`` raises on a canonical example
    id in ANY scope, and the ordinary workspace is never auto-seeded — so a canonical
    id simply does not resolve here. Asserted rather than assumed, because a proposal
    route that reached one would be writing into a discardable example.
    """
    for canonical in sorted(ws.CANONICAL_IDS):
        response = client.get(f"/api/experiments/{canonical}/proposals")
        assert response.status_code == 404, (canonical, response.text)
        assert response.json()["error"] == "experiment_not_found"


def test_I7_an_acceptance_inside_a_tutorial_session_is_unattributed(armed):
    """The third half, and the one a reader is least likely to expect.

    ``identity.stamp_actor`` returns ``None`` inside a worked-example session
    UNCONDITIONALLY AND FIRST — "a perfectly verified actor in a tutorial session
    still stamps nothing" — so an acceptance there is recorded ``unattributed`` EVEN
    under the fixture verifier, which this test arms to prove it.

    Real attribution inside a discardable session would be the one durable trace it
    left behind, attached to fabricated science.

    MUTATION: replaced ``stamp_actor(identity, scope)`` with
    ``identity.human.subject``. This went RED while
    ``test_I4_accept_succeeds_and_stamps_the_actor_under_the_fixture_verifier``
    stayed green — which is exactly the pair that makes the rule checkable.
    """
    from isaac_api.app import create_app

    tclient = tutorial_client(create_app())
    store = client_ws(tclient)
    experiment_draft, run_draft = _split_full_draft()
    exp = store.create_experiment(
        "Tutorial accept", {"kind": "synthetic"}, experiment_draft
    )
    exp.add_run(label="Run A", draft=copy.deepcopy(run_draft))
    exp.capture_note(text=NOTE_TEXT, source="typed_note")
    exp.save_versioned()
    exp = store.load_experiment(exp.id)

    proposal = _created(tclient, exp)
    response = _review(
        tclient,
        exp.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text
    body = response.json()["proposal"]
    assert body["state"] == proposals.STATE_ACCEPTED
    assert body["accepted_by"]["subject"] is None
    assert body["accepted_by"]["trust_basis"] == "unattributed"
    assert body["accepted_by"]["attributed"] is False
    assert ACTOR not in response.text


# --- DEC-1 and §10.3: the precondition, and the critical section --------------


def test_DEC1_a_stale_proposal_never_overwrites_a_newer_value(armed_client, experiment):
    """The hard safety rule, measured over HTTP.

    A proposal is a judgement about a target AS IT STOOD. If the target moves, the
    judgement no longer covers what is there, and accepting it would write over
    somebody else's newer value with an opinion formed about a different one.

    MUTATION: compared ``proposal.base_rev`` to ``exp.rev`` instead of comparing
    digests. The refusal still fired here — but
    ``test_DEC1_base_rev_is_not_the_precondition`` went RED, which is the pair that
    proves the digest is doing the work.
    """
    proposal = _created(armed_client, experiment, path=OVERRIDE_PATH, value="Cu2O")

    # Somebody else writes the target through the ordinary route.
    exp = _stored(experiment.id)
    override = _override(armed_client, experiment.id, exp.runs[0].id, OVERRIDE_PATH, "CuO")
    assert override.status_code in (200, 201), override.text

    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "proposal_stale"

    after = _stored(experiment.id)
    assert (
        after.runs[0].overrides[ws.field_address(OVERRIDE_PATH)].payload["value"] == "CuO"
    ), "a stale proposal overwrote a newer value"
    assert after.get_proposal(proposal["proposal_id"]).state == proposals.STATE_OPEN


def test_DEC1_base_rev_is_not_the_precondition(armed_client, experiment):
    """DEC-1, which supersedes §2's original answer, in the form that proves it.

    ``base_rev`` is the RECORD's rev and moves on ANY act. If it were the
    precondition, an unrelated act — capturing a note — would make every open
    proposal permanently un-acceptable. Here the record's rev moves twice and the
    accept still succeeds, because the TARGET did not move.
    """
    proposal = _created(armed_client, experiment)
    base_rev = proposal["base_rev"]

    for text in ("an unrelated remark", "and another"):
        captured = armed_client.post(
            f"/api/experiments/{experiment.id}/notes",
            json={"text": text, "source": "typed_note"},
            headers={"If-Match": _etag(armed_client, experiment.id)},
        )
        assert captured.status_code == 201, captured.text
    assert _stored(experiment.id).rev > base_rev

    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, (
        "an unrelated act made an open proposal un-acceptable, which is exactly the "
        "failure DEC-1 replaced base_rev to avoid. Body: " + response.text[:300]
    )
    assert response.json()["proposal"]["base_rev"] == base_rev


def test_DEC1_evidence_arriving_at_the_target_moves_the_digest(client, experiment):
    """The digest covers the value AND the evidence envelope, which is the contract.

    An acceptance is a judgement about a target as it stood, and a confirmation
    arriving IS a change to it — so the digest must move even when the value did not.
    """
    exp = _stored(experiment.id)
    run = exp.runs[0]
    before = proposals.target_digest(
        routes._proposal_target_state(exp, run, OVERRIDE_PATH)
    )
    exp.set_run_override(
        run,
        ws.field_address(OVERRIDE_PATH),
        {"value": "CuO", "status": "verified", "evidence": []},
    )
    after = proposals.target_digest(
        routes._proposal_target_state(exp, run, OVERRIDE_PATH)
    )
    assert after != before


def test_the_digest_is_re_read_inside_the_lock_and_before_the_write(
    armed_client, experiment, monkeypatch
):
    """§10.3, asserted as an ORDERING rather than as an outcome.

    "A digest read before the lock would let two accepts both pass." That is not
    something an outcome assertion can see: with the comparison correct but hoisted
    above ``record_lock``, a single-threaded test still refuses the second accept.

    So the ordering itself is observed. ``record_lock``, the digest function and the
    three writers are each wrapped to append to one trace, and the trace is required
    to read lock → digest → write. A digest computed before the lock, or a write
    committed before the comparison, changes this sequence and nothing else has to
    notice.

    MUTATION: hoisted the ``proposals.target_digest`` call above
    ``with ws.record_lock(...)`` in ``post_proposal_review``. The outcome assertions
    in the sibling tests all stayed green; this one went RED on the first element.
    """
    trace: list[str] = []

    original_lock = ws.record_lock

    def traced_lock(*args, **kwargs):
        trace.append("lock")
        return original_lock(*args, **kwargs)

    original_digest = proposals.target_digest

    def traced_digest(state):
        trace.append("digest")
        return original_digest(state)

    original_override = ws.Experiment.set_run_override

    def traced_write(self, run, address, payload):
        trace.append("write")
        return original_override(self, run, address, payload)

    proposal = _created(armed_client, experiment)

    monkeypatch.setattr(ws, "record_lock", traced_lock)
    monkeypatch.setattr(proposals, "target_digest", traced_digest)
    monkeypatch.setattr(routes.proposals, "target_digest", traced_digest)
    monkeypatch.setattr(ws.Experiment, "set_run_override", traced_write)

    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 200, response.text

    assert "write" in trace, trace
    assert trace.index("lock") < trace.index("digest") < trace.index("write"), (
        "the target digest must be re-read INSIDE the lock and BEFORE the write. "
        f"Observed order: {trace}"
    )


def test_two_accepts_of_the_same_target_do_not_both_land(armed_client, experiment):
    """The concurrency outcome the ordering above protects.

    Two proposals at one target, both open, both formed over the same digest. The
    first accept moves the target; the second is refused ``409 proposal_stale`` with
    nothing written, and is NOT auto-superseded — a person re-reads the value that is
    now there and decides.
    """
    first = _created(armed_client, experiment, value="Cu2O")
    second = _created(armed_client, experiment, value="CuO")
    assert first["target_digest"] == second["target_digest"]

    won = _review(
        armed_client,
        experiment.id,
        first["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert won.status_code == 200, won.text

    lost = _review(
        armed_client,
        experiment.id,
        second["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert lost.status_code == 409, lost.text
    assert lost.json()["error"] == "proposal_stale"

    exp = _stored(experiment.id)
    assert exp.runs[0].overrides[ws.field_address(OVERRIDE_PATH)].payload["value"] == "Cu2O"
    loser = exp.get_proposal(second["proposal_id"])
    assert loser.state == proposals.STATE_OPEN, "the loser was auto-superseded"


# --- a proposal can never mutate a Submitted revision -------------------------


@pytest.fixture()
def submission_db():
    return FakeSubmissionConnection()


@pytest.fixture()
def submitting_client(armed, submission_db, monkeypatch):
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(submission_db))
    monkeypatch.setattr(rhist, "reader", lambda env=None: fake_reader(submission_db))
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def test_accepting_a_proposal_never_mutates_a_submitted_revision(
    submitting_client, experiment, submission_db
):
    """A submitted revision is an immutable snapshot; an acceptance is a NEW Draft.

    The revision rows are append-only ``INSERT``s from ``submission_store``, and
    nothing on the proposal path reaches them. What an acceptance changes is the LIVE
    document, which a LATER submit records as a new revision through the ordinary
    revision semantics — so the history gains a version rather than losing one.

    Asserted from the recorded rows themselves rather than from the absence of an
    import, because the claim is about behaviour.
    """
    submitted = submitting_client.post(
        f"/api/experiments/{experiment.id}/submit",
        headers={"If-Match": _etag(submitting_client, experiment.id)},
    )
    assert submitted.status_code == 200, submitted.text
    snapshot = copy.deepcopy(submission_db.revisions)
    assert [row["revision_no"] for row in snapshot] == [1]

    proposal = _created(submitting_client, experiment)
    accepted = _review(
        submitting_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert accepted.status_code == 200, accepted.text

    assert submission_db.revisions == snapshot, (
        "accepting a proposal rewrote or appended to the submitted revision history. "
        "It must change the live draft only."
    )

    resubmitted = submitting_client.post(
        f"/api/experiments/{experiment.id}/submit",
        headers={"If-Match": _etag(submitting_client, experiment.id)},
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert [row["revision_no"] for row in submission_db.revisions] == [1, 2]
    assert submission_db.revisions[0] == snapshot[0]


# --- DEC-3: no stored quote ---------------------------------------------------


def test_DEC3_no_quote_is_stored_and_the_excerpt_is_derived(client, experiment):
    """DEC-3. The words live on the note; the proposal carries offsets.

    Storing them twice would put a copy of a scientist's verbatim text somewhere the
    transcript retention disclosure does not describe.

    MUTATION: added a ``quote`` field carrying ``note.text[start:end]``. The
    stored-state assertion went RED.
    """
    start = NOTE_TEXT.index("CuO2")
    proposal = _created(client, experiment, start_char=start, end_char=start + 4)
    assert proposal["excerpt"] == "CuO2"

    stored = _stored(experiment.id).get_proposal(proposal["proposal_id"]).to_state()
    assert "quote" not in stored
    assert "CuO2" not in json.dumps(
        {k: v for k, v in stored.items() if k not in ("proposed_value", "rule")}
    ), "the note's words were stored a second time on the proposal"


def test_DEC3_the_excerpt_follows_the_verbatim_capture_not_an_edit(client, experiment):
    """The offsets index ``note.text``, which is immutable, and never ``display_text``.

    ``notes.edit_note`` stores a corrected wording BESIDE the verbatim capture. A span
    into an editable string would silently start naming different words; a span into
    the capture cannot go stale.
    """
    start = NOTE_TEXT.index("CuO2")
    proposal = _created(client, experiment, start_char=start, end_char=start + 4)
    note_id = _stored(experiment.id).notes[0].id
    edited = client.post(
        f"/api/experiments/{experiment.id}/notes/{note_id}/review",
        json={"confirmed_by_user": True, "action": "edit", "text": "totally rewritten"},
        headers={"If-Match": _etag(client, experiment.id)},
    )
    assert edited.status_code == 200, edited.text

    reread = client.get(
        f"/api/experiments/{experiment.id}/proposals/{proposal['proposal_id']}"
    )
    assert reread.status_code == 200, reread.text
    assert reread.json()["proposal"]["excerpt"] == "CuO2"


def test_DEC3_a_span_outside_the_note_is_refused_not_clamped(client, experiment):
    response = _create(client, experiment, start_char=0, end_char=len(NOTE_TEXT) + 1)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_span"
    assert _stored(experiment.id).proposals == []


def test_DEC3_half_a_span_is_refused(client, experiment):
    response = _create(client, experiment, start_char=0)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_span"


# --- DEC-4: bounded payload ---------------------------------------------------


def test_DEC4_an_oversized_value_is_refused_with_value_too_large(client, experiment):
    """DEC-4. A REFUSAL, never a truncation.

    A truncated value misrepresents what was proposed and a truncated rule
    misrepresents why. The two refusals are kept distinct from
    ``unrepresentable_value`` because the remedies differ — shorten it, versus fix
    the encoding.
    """
    response = _create(client, experiment, value="x" * (routes._MAX_PROPOSAL_BYTES + 1))
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "value_too_large"
    assert body["max_bytes"] == routes._MAX_PROPOSAL_BYTES
    assert _stored(experiment.id).proposals == []


def test_DEC4_the_bound_covers_the_rule_as_well_as_the_value(client, experiment):
    response = _create(
        client, experiment, value="ok", rule="y" * (routes._MAX_PROPOSAL_BYTES + 1)
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "value_too_large"


def test_DEC4_an_unrepresentable_value_is_a_different_refusal(client, experiment):
    """A lone surrogate renders under ``ensure_ascii=True`` and raises under ``False``.

    Starlette renders with ``ensure_ascii=False`` and then ``.encode("utf-8")``, so
    this is the shape that produced a measured 500 on a neighbouring route. It is a
    typed refusal here, and NOT ``value_too_large``: the value is small.
    """
    # SENT AS RAW BYTES, because the test client's own encoder refuses a lone
    # surrogate before the request is made (`UnicodeEncodeError`). `json.dumps` with
    # its default `ensure_ascii=True` writes the six-character escape, which IS
    # encodable — and which the server's `json.loads` turns back into the surrogate.
    # That is exactly the path a browser client takes, and the one that produced a
    # measured 500 on a neighbouring route.
    body = json.dumps(
        {
            "note_id": experiment.notes[0].id,
            "target_field_path": OVERRIDE_PATH,
            "proposed_value": "\ud800",
            "rule": "a rule",
            "run_id": experiment.runs[0].id,
        }
    ).encode("ascii")
    response = client.post(
        f"/api/experiments/{experiment.id}/proposals",
        content=body,
        headers={
            "If-Match": _etag(client, experiment.id),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrepresentable_value"


def test_DEC4_the_per_record_count_is_bounded_at_create(client, experiment, monkeypatch):
    """DEC-5's other half: a record cannot hold unboundedly many proposals.

    The bound is low here so the test is a test rather than a load run; the constant
    it stands in for is ``_MAX_PROPOSALS_PER_RECORD``.
    """
    monkeypatch.setattr(routes, "_MAX_PROPOSALS_PER_RECORD", 2)
    for index in range(2):
        assert _create(client, experiment, value=f"Cu{index}O").status_code == 200
    refused = _create(client, experiment, value="one too many")
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "too_many_proposals"
    assert len(_stored(experiment.id).proposals) == 2


# --- DEC-5: bounded list ------------------------------------------------------


def test_DEC5_omitting_limit_returns_a_window_and_not_everything(client, experiment):
    """DEC-5, and it is a DELIBERATE departure from this API's other lists.

    ``GET .../runs`` and ``GET .../pending`` return everything by default and say in
    their own comments that the default must not quietly become a cap. That was right
    for lists a person creates one at a time. ``CLAUDE.md`` §11 records this
    repository paying 1,772,692 B for exactly the unpaginated shape, and a proposal's
    intended producer is automatic.

    MUTATION: made the default ``limit`` ``None`` and returned every proposal. This
    went RED; ``total`` stayed correct, which is why ``returned`` is asserted too.
    """
    monkeypatch_window = routes._PROPOSAL_WINDOW_DEFAULT
    for index in range(monkeypatch_window + 3):
        assert _create(client, experiment, value=f"Cu{index}O").status_code == 200

    response = client.get(f"/api/experiments/{experiment.id}/proposals")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == monkeypatch_window + 3
    assert body["returned"] == monkeypatch_window
    assert body["has_more"] is True
    assert body["next_cursor"] == body["proposals"][-1]["proposal_id"]


def test_DEC5_the_cursor_walks_the_whole_list_exactly_once(client, experiment):
    for index in range(7):
        assert _create(client, experiment, value=f"Cu{index}O").status_code == 200

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        query = f"?limit=3{'' if cursor is None else f'&after={cursor}'}"
        body = client.get(f"/api/experiments/{experiment.id}/proposals{query}").json()
        seen.extend(p["proposal_id"] for p in body["proposals"])
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]
    assert len(seen) == 7
    assert len(set(seen)) == 7
    assert seen == [p.proposal_id for p in _stored(experiment.id).sorted_proposals()]


def test_DEC5_the_window_is_server_capped(client, experiment):
    over = client.get(
        f"/api/experiments/{experiment.id}/proposals"
        f"?limit={routes._PROPOSAL_WINDOW_MAX + 1}"
    )
    assert over.status_code == 422, over.text


def test_DEC5_an_unknown_cursor_is_refused_rather_than_restarting(client, experiment):
    """Silently restarting a page walk returns the same window forever."""
    _created(client, experiment)
    response = client.get(
        f"/api/experiments/{experiment.id}/proposals?after=01JQZZNOTAPROPOSAL000000"
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_cursor"


# --- DEC-6: hydration returns the pair shape ----------------------------------


def _plant_unreadable(eid: str, entry) -> None:
    """Write a stored entry this build cannot read, the way an operator edit would."""
    path = ws.workspace_root() / eid / "experiment.json"
    state = json.loads(path.read_text())
    state.setdefault(proposals.STATE_KEY, []).append(entry)
    path.write_text(json.dumps(state))


@pytest.mark.parametrize(
    "entry",
    [
        7,
        "not a proposal",
        {"proposal_id": "P-BROKEN"},
        {"proposal_id": "P-BROKEN", "target_field_path": "", "rule": None},
    ],
)
def test_DEC6_an_unreadable_entry_is_preserved_counted_and_never_500s(
    client, experiment, entry
):
    """DEC-6 — the ``pending: 7`` finding, applied before it can happen again.

    A malformed value already PERSISTED cannot be refused to the reader, who did
    nothing wrong and whose record would simply vanish. So it is preserved VERBATIM,
    counted, surfaced as unreadable — never coerced, parsed, walked or dropped — and
    neither the list screen nor the detail route 500s over it.

    MUTATION: made ``_hydrate_proposals`` re-raise instead of collecting. **2 of the
    4 parameters went RED and 2 stayed GREEN**, which is the right outcome and is
    stated rather than rounded up: ``7`` and ``"not a proposal"`` are non-dicts and
    are filed as unreadable by the ``isinstance`` check BEFORE ``from_state`` is
    reached, so the raise never runs for them. The two dict entries are the ones the
    model refuses, and they are the ones this mutation reaches.
    """
    _created(client, experiment)
    _plant_unreadable(experiment.id, entry)

    listed = client.get(f"/api/experiments/{experiment.id}/proposals")
    assert listed.status_code == 200, listed.text
    assert listed.json()["unreadable_entries"] == 1
    assert listed.json()["total"] == 1

    # The record's own screens still read, which is the failure this shape exists for.
    assert client.get(f"/api/experiments/{experiment.id}").status_code == 200
    assert client.get("/api/experiments").status_code == 200


def test_DEC6_an_unreadable_entry_survives_a_save_verbatim(client, experiment):
    planted = {"proposal_id": "P-BROKEN", "mystery": {"nested": [1, 2, 3]}}
    _created(client, experiment)
    _plant_unreadable(experiment.id, planted)

    # A later write rewrites the whole document.
    _created(client, experiment, value="another")

    state = json.loads(
        (ws.workspace_root() / experiment.id / "experiment.json").read_text()
    )
    assert planted in state[proposals.STATE_KEY], (
        "a save rewrote the document without an entry this build could not read"
    )


def test_DEC6_a_duplicate_id_is_filed_as_unreadable_not_merged(client, experiment):
    created = _created(client, experiment)
    stored = _stored(experiment.id).get_proposal(created["proposal_id"]).to_state()
    _plant_unreadable(experiment.id, stored)

    body = client.get(f"/api/experiments/{experiment.id}/proposals").json()
    assert body["total"] == 1
    assert body["unreadable_entries"] == 1


def test_DEC6_hydration_returns_a_pair_and_never_raises():
    for raw in (None, 7, "x", {}, [7], [{"proposal_id": "x"}], [[]]):
        readable, unreadable = ws._hydrate_proposals(raw)
        assert isinstance(readable, list)
        assert isinstance(unreadable, list)


# --- DEC-7: excluded from the MCP-reachable detail payload --------------------


def test_DEC7_proposals_are_absent_from_the_mcp_reachable_detail_payload(
    client, experiment
):
    """DEC-7, asserted because ``mcp/client.py`` binds an OPERATION, not a shape.

    ``isaac_get_experiment`` reaches ``GET /api/experiments/{id}``. Adding a
    ``proposals`` key there would widen external-agent reads with no reviewed
    decision, and no allowlist check would notice — the allowlist governs which
    routes may be called, not what they return.

    MUTATION: added ``"proposals": [...]`` to the detail route's payload. This went
    RED; every other test in the file stayed green.
    """
    from isaac_api.mcp import policy

    reachable = {
        (operation.method, operation.path_template)
        for operation in policy.OPERATIONS.values()
    }
    assert ("GET", "/api/experiments/{experiment_id}") in reachable

    _created(client, experiment)
    body = client.get(f"/api/experiments/{experiment.id}").json()
    assert "proposals" not in body
    assert proposals.STATE_KEY not in json.dumps(body)
    # A SUBSTRING SCAN FOR "proposal" WOULD FAIL FOR THE WRONG REASON, and saying so
    # is part of the test: `system.configuration.proposal_id` is one of the official
    # schema's own field paths and appears in the fixture's draft. What must be absent
    # is the state KEY and every id this feature mints.
    for stored in _stored(experiment.id).proposals:
        assert stored.proposal_id not in json.dumps(body)

    listed = client.get("/api/experiments").json()
    assert proposals.STATE_KEY not in json.dumps(listed)


def test_DEC7_no_mcp_operation_or_tool_reaches_the_proposal_REVIEW_route():
    """~~``test_DEC7_no_mcp_operation_or_tool_reaches_a_proposal_route``~~ — **INVERTED
    ON 2026-09-01, NOT DELETED, BECAUSE IT WAS PINNING A CLAIM THE CONTRACT WITHDREW.**

    This asserted *"no `proposal` in any operation path, no `proposal` in any tool name,
    and exactly ten tools"*. ``docs/ingestion-proposal-contract.md`` §4's *"MCP: no new
    tool"* is struck in place there and amended IN §4 ITSELF, which adds four tools — a
    create at its own ``isaac:proposals.write`` scope, two reads, and the change feed —
    because *"the Claude voice-to-proposal workflow it authorizes is unbuildable if MCP
    cannot create a proposal"*.

    **THE HALF THAT SURVIVES IS THE HALF THAT MATTERS, AND IT IS WHAT THIS NOW PINS.**
    §4, unstruck: *"No accept, review, supersede, withdraw, finalize, export or
    Submit tool may exist at any scope, and `POST .../proposals/{id}/review` must never
    appear in an MCP `OPERATIONS` entry."* So the assertion moves from "no proposal
    route" to "no REVIEW route", and gains the ``accept``-token check that is the second,
    independent mechanism.

    A blanket ``"proposal" not in name`` would now be green only by deleting the
    feature, which is why the substring test is replaced by an enumeration of exactly
    which proposal operations are reachable. DEC-7's own subject — that no ``proposals``
    key is added to the MCP-reachable experiment DETAIL payload — is unchanged and is
    asserted by the test immediately above this one.
    """
    from isaac_api.mcp import policy

    reachable = {
        op.id for op in policy.OPERATIONS.values() if "proposal" in op.path_template
    }
    assert reachable == {"list_proposals", "get_proposal", "create_proposal"}

    # THE REVIEW ROUTE IS UNREACHABLE, BY PATH AND BY NAME.
    assert not any("/review" in op.path_template for op in policy.OPERATIONS.values())
    for banned in ("accept", "approve", "submit", "export", "finalis", "publish"):
        assert not any(
            banned in op.path_template.lower() for op in policy.OPERATIONS.values()
        ), banned
        assert not any(banned in name for name in policy.PERMITTED_TOOL_NAMES), banned
    for name in ("isaac_accept_proposal", "isaac_review_proposal_accept"):
        assert policy.forbidden_tool_reason(name) is not None, name

    # AND THE CREATE COSTS ITS OWN SCOPE, WHICH IS NOT THE DRAFT-WRITE ONE. A proposal
    # is not a draft write (§5 I1/I2), and giving the model-derived channel
    # `DRAFT_WRITE` would hand it the ability to change draft content directly.
    assert (
        policy.OPERATIONS["create_proposal"].scope is policy.Scope.PROPOSALS_WRITE
    )
    assert policy.Scope.PROPOSALS_WRITE not in {
        policy.OPERATIONS[op].scope
        for op in policy.OPERATIONS
        if op != "create_proposal"
    }
    assert len(policy.PERMITTED_TOOL_NAMES) == 14


# --- DEC-8: still_current is derived, never stored ----------------------------


def test_DEC8_still_current_is_derived_and_goes_false_when_the_target_is_corrected(
    armed_client, experiment
):
    """DEC-8. ``accepted`` is terminal, and the target can be corrected afterwards.

    Without this, an accepted proposal reads as a standing claim about the record's
    present content. It is re-digested on every read and never stored, so it cannot
    be persisted as ``true`` and then quietly stay that way.

    MUTATION: stored ``still_current: True`` on the proposal at accept time and
    served it from there. The post-correction assertion went RED.
    """
    proposal = _created(armed_client, experiment)
    accepted = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["proposal"]["still_current"] is True

    exp = _stored(experiment.id)
    corrected = _override(armed_client, experiment.id, exp.runs[0].id, OVERRIDE_PATH, "CuO")
    assert corrected.status_code in (200, 201), corrected.text

    reread = armed_client.get(
        f"/api/experiments/{experiment.id}/proposals/{proposal['proposal_id']}"
    ).json()["proposal"]
    assert reread["state"] == proposals.STATE_ACCEPTED
    assert reread["still_current"] is False
    assert "still_current" not in (
        _stored(experiment.id).get_proposal(proposal["proposal_id"]).to_state()
    )


def test_DEC8_still_current_is_null_rather_than_false_when_it_cannot_be_answered(
    armed_client, experiment
):
    """``null`` is not ``false``, and the difference is the honest one.

    "The target could not be read" and "the target changed" are different facts, and
    a ``false`` covering both would be the more comfortable of the two.
    """
    proposal = _created(armed_client, experiment)
    assert (
        _review(
            armed_client,
            experiment.id,
            proposal["proposal_id"],
            action="accept",
            accepted_from="candidate",
        ).status_code
        == 200
    )
    exp = _stored(experiment.id)
    removed = armed_client.post(
        f"/api/experiments/{experiment.id}/runs/{exp.runs[0].id}/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(armed_client, experiment.id)},
    )
    assert removed.status_code == 200, removed.text

    body = armed_client.get(
        f"/api/experiments/{experiment.id}/proposals/{proposal['proposal_id']}"
    ).json()["proposal"]
    assert body["still_current"] is None
    assert body["target_stale"] is None
    assert body["current_target_digest"] is None


# --- 409 target_run_removed ---------------------------------------------------


def test_a_proposal_whose_run_was_removed_is_refused_and_never_re_targeted(
    armed_client, experiment
):
    """§4's ``409 target_run_removed``, and the rule that makes it correct.

    ``remove_run`` does not renumber the survivors, so a removed run's id is never
    reissued and a proposal naming it goes PERMANENTLY dangling rather than silently
    shifting onto a neighbour. Re-aiming it would be inferring which run a scientist
    meant — the inference ``notes.Note`` refuses in its most damaging form.

    It is a different code from creation-time ``422 unknown_run``: that covers the run
    that never existed, and these are different failures.
    """
    exp = _stored(experiment.id)
    second = armed_client.post(
        f"/api/experiments/{experiment.id}/runs",
        json={"label": "Run B"},
        headers={"If-Match": _etag(armed_client, experiment.id)},
    )
    assert second.status_code == 201, second.text
    survivor = second.json()["run"]["id"]

    proposal = _created(armed_client, experiment)
    removed = armed_client.post(
        f"/api/experiments/{experiment.id}/runs/{exp.runs[0].id}/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(armed_client, experiment.id)},
    )
    assert removed.status_code == 200, removed.text

    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "target_run_removed"

    after = _stored(experiment.id)
    assert after.get_run(survivor).overrides == {}, "the proposal was re-aimed"
    assert after.get_proposal(proposal["proposal_id"]).state == proposals.STATE_OPEN

    # The proposal stays readable and a person may withdraw it.
    withdrawn = _review(
        armed_client, experiment.id, proposal["proposal_id"], action="withdraw"
    )
    assert withdrawn.status_code == 200, withdrawn.text


def test_an_unknown_run_at_create_is_a_different_refusal(client, experiment):
    response = _create(client, experiment, run_id="01JQZZNOTARUN0000000000000")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_run"


# --- DEC-11 and the declined keys ---------------------------------------------


@pytest.mark.parametrize(
    "key,value",
    [
        ("unit", "K"),
        ("quote", "CuO2"),
        ("uncertainty", 0.02),
        ("confidence", 0.86),
        ("probability", 0.9),
        ("score", 3),
        ("expires_utc", "2027-01-01T00:00:00Z"),
    ],
)
def test_DEC11_the_declined_keys_are_refused_by_name_with_the_reason(
    client, experiment, key, value
):
    """DEC-11 and its neighbours. Each was asked for and each was declined.

    A caller who sends one has read a version of the design that no longer holds, and
    a message naming the decision is worth more to them than ``unrecognized_field``.
    Nothing is written in any case.

    ``uncertainty`` is here for a reason worth stating: the reused confidence guard's
    key set is ``{confidence, probability, score}`` and does NOT include the word, so
    without this allowlist a bare ``uncertainty`` would arrive unremarked.
    """
    response = _create(client, experiment, **{key: value})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrecognized_field"
    assert body["key"] == key
    assert body["declined"] == [key]
    assert _stored(experiment.id).proposals == []


def test_the_model_has_no_unit_field_at_all():
    """DEC-11 from the shape rather than from the route.

    "Optional, never derived" still permits a unit the source never stated, with
    nothing requiring the ``rule`` sentence to cover it. Dropping the field is what
    makes that unconstructible.
    """
    fields = {f.name for f in dataclasses.fields(proposals.IngestionProposal)}
    assert "unit" not in fields
    assert "quote" not in fields
    assert "expires_utc" not in fields
    assert not (fields & {"confidence", "probability", "score", "uncertainty"})


def test_a_confidence_buried_in_a_nested_value_is_refused(client, experiment):
    """The reused guard, reaching where the body-key allowlist cannot.

    ``providers.guards.check_candidate_provenance`` is the function
    ``FieldCandidate.__post_init__`` already runs, so a stored proposal cannot carry
    something an unstored candidate is refused for.
    """
    response = _create(
        client, experiment, value={"reading": 3.2, "meta": {"confidence": 0.86}}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unsupported_proposal"
    assert _stored(experiment.id).proposals == []


# --- DEC-12: no table, no migration -------------------------------------------


def test_DEC12_no_table_was_added_to_the_write_policy():
    """DEC-12. ``db_write.OWNED_TABLES`` is UNCHANGED by this feature.

    §15 records FOUR occasions on which a table reached that list before any committed
    sentence named it. This is deliberately the first scope extension that adds none:
    the state document is already upserted whole, so a new key inside it needs no DDL.
    """
    assert not any("proposal" in table for table in db_write.OWNED_TABLES)
    assert db_write.OWNED_TABLES == frozenset(
        {
            "isaac_experiments",
            "isaac_schema_migrations",
            "isaac_runs",
            "isaac_experiment_revisions",
            "isaac_run_revisions",
            "isaac_revision_changes",
            "isaac_submissions",
            "isaac_submission_runs",
            "isaac_run_projection",
        }
    ), (
        "OWNED_TABLES moved. Persistent ingestion proposals add no table and no "
        "migration, deliberately: a feature needing one would not work until an "
        "operator applied it, and applying a hosted migration is a hard stop."
    )


def test_DEC12_no_migration_was_added():
    migrations = sorted(
        p.name
        for p in (Path(ws.__file__).parent / "migrations").glob("*.sql")
    )
    assert not any(name.startswith("0006") for name in migrations), migrations
    assert not any("proposal" in name for name in migrations), migrations


def test_DEC12_the_state_key_needs_no_migration_to_read_a_legacy_document(workspace):
    """A document written before proposals existed hydrates to an empty PAIR.

    And it hashes with ``"proposals": []``, so adding the key to the signature causes
    no spurious ``rev`` bump on legacy state — the property runs and notes both
    relied on.
    """
    exp = ws.create_experiment(
        "legacy", {"kind": "synthetic"}, {"meta": {}, "fields": {}, "pending": []}
    )
    legacy = {k: v for k, v in exp.to_state().items() if k != proposals.STATE_KEY}
    rehydrated = ws.Experiment.from_state(legacy)
    assert rehydrated.proposals == []
    assert rehydrated.unreadable_proposals == []
    assert ws._authoritative_signature(rehydrated) == ws._authoritative_signature(exp)


# --- DEC-13: the idempotency key ----------------------------------------------


def test_DEC13_a_repeated_create_with_one_key_mints_exactly_one_proposal(
    client, experiment
):
    """DEC-13, and the decline it reverses was answering a different question.

    Every write here is idempotent by CONTENT — true of applying, false of creating:
    two identical POSTs mint two ids, so a retrying client duplicates. Exactly-once
    within a scope, with no uniqueness constraint, because every write to one
    experiment holds ``record_lock``.

    MUTATION: dropped the ``find_by_client_request_key`` branch. The count assertion
    went RED.
    """
    first = _create(client, experiment, client_request_key="retry-1")
    assert first.status_code == 200, first.text
    assert first.json()["deduplicated"] is False

    second = _create(client, experiment, client_request_key="retry-1")
    assert second.status_code == 200, second.text
    assert second.json()["deduplicated"] is True
    assert (
        second.json()["proposal"]["proposal_id"]
        == first.json()["proposal"]["proposal_id"]
    )
    assert len(_stored(experiment.id).proposals) == 1


def test_DEC13_without_a_key_two_identical_creates_are_two_acts(client, experiment):
    """Stated rather than implied: the key is what makes creation exactly-once."""
    first = _created(client, experiment)
    second = _created(client, experiment)
    assert first["proposal_id"] != second["proposal_id"]
    assert len(_stored(experiment.id).proposals) == 2


def test_DEC13_a_dedupe_returns_the_first_id_not_a_later_one(client, experiment):
    """``find_by_client_request_key`` returns the EARLIEST match, deliberately.

    A retry's whole requirement is that it end up with one proposal and know which —
    the one its FIRST attempt established. This plants a second row with the same key
    the only way a route cannot (an operator edit) and pins the direction.
    """
    first = _created(client, experiment, client_request_key="retry-2")
    later = copy.deepcopy(
        _stored(experiment.id).get_proposal(first["proposal_id"]).to_state()
    )
    later["proposal_id"] = "01JQZZLATERPROPOSAL000001"
    later["proposed_utc"] = "2099-01-01T00:00:00Z"
    _plant_unreadable(experiment.id, later)

    again = _create(client, experiment, client_request_key="retry-2")
    assert again.status_code == 200, again.text
    assert again.json()["proposal"]["proposal_id"] == first["proposal_id"]


# --- §6: the seven paths no route accepts -------------------------------------


SEVEN = sorted(
    routes.NOTE_MAPPABLE_FIELD_PATHS - routes.PROPOSAL_TARGET_PATHS
)


def test_the_target_set_is_the_writable_set_and_is_derived():
    """§6. The permitted target set is DERIVED from the routes that write.

    18 of 25, and the split is re-derived here rather than transcribed, so a future
    widening of either input moves this test rather than leaving it asserting a
    number that used to be true.
    """
    assert routes.PROPOSAL_TARGET_PATHS is routes.NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT
    assert len(routes.PROPOSAL_TARGET_PATHS) == 18
    assert len(routes.NOTE_MAPPABLE_FIELD_PATHS) == 25
    assert SEVEN == sorted(
        [
            "system.configuration.detector_model",
            "system.configuration.monochromator_crystal",
            "system.configuration.n_scans",
            "system.configuration.proposal_id",
            "system.configuration.session_id",
            "system.configuration.spectrometer_geometry",
            "timestamps.created_utc",
        ]
    )


@pytest.mark.parametrize("path", SEVEN)
def test_a_target_no_route_can_write_is_refused_as_a_limit_of_this_build(
    client, experiment, path
):
    """§6: refused, naming the path, and NEVER as a statement about the schema.

    ``CLAUDE.md`` §1 makes the official schema not ours to speak for, and every one of
    these seven is a real field it defines. The note stays stored and stays mappable;
    what is missing is a route that writes a value there.
    """
    response = _create(client, experiment, path=path)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "no_write_path_for_field"
    assert body["key"] == path
    assert "LIMITATION OF THIS BUILD" in body["message"]
    assert "note IS stored" in body["message"]
    assert _stored(experiment.id).proposals == []


def test_a_path_outside_the_mappable_set_is_a_different_refusal(client, experiment):
    response = _create(client, experiment, path="sample.material.typo")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field"


def test_every_permitted_target_has_a_writer(client, experiment):
    """The import-time guard's claim, re-derived over the whole set.

    The guard raises ``RuntimeError`` while the module loads if a permitted target has
    no writer — so the application fails to START rather than accepting a proposal
    whose only possible outcome is a refusal at review. This asserts the same property
    the guard enforces, so the guard cannot be deleted without a test noticing.
    """
    assert routes._PROPOSAL_TARGETS_WITH_NO_WRITER == frozenset()
    for path in routes.PROPOSAL_TARGET_PATHS:
        writer = routes._proposal_writer_for(path)
        assert writer in proposals.APPLIED_VIA_VALUES, path
        assert routes._PROPOSAL_WRITER_SCOPE[writer] in ("run", "record")


def test_the_record_scoped_enum_path_routes_through_the_enum_writer_not_the_override(
    armed_client, experiment
):
    """§6's known pre-existing divergence, which this feature must not inherit.

    ``field:system.technique`` IS in ``EXPERIMENT_OVERRIDABLE_ADDRESSES`` and its run
    override returns 200 while accepting OFF-ENUM values. An accepted proposal at that
    path must route through ``_apply_record_fields``, which checks the enum.

    MUTATION: swapped the first two clauses of ``_proposal_writer_for`` so the
    override matched first. The off-enum refusal below went from 422 to 200.
    """
    assert (
        ws.field_address(RECORD_PATH) in routes.EXPERIMENT_OVERRIDABLE_ADDRESSES
    ), "the divergence this test guards against has gone away; re-derive the test"

    proposal = _created(armed_client, experiment, path=RECORD_PATH, value="not_a_technique")
    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "not_an_allowed_value"
    assert _stored(experiment.id).get_proposal(
        proposal["proposal_id"]
    ).state == proposals.STATE_OPEN


def test_a_record_scoped_target_refuses_a_run_id(client, experiment):
    response = _create(client, experiment, path=RECORD_PATH, run_id=experiment.runs[0].id)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "target_is_record_scoped"


def test_a_run_scoped_target_requires_a_run_id(client, experiment):
    body = {
        "note_id": experiment.notes[0].id,
        "target_field_path": RUN_PATH,
        "proposed_value": 301.0,
        "rule": "the number before K matched the temperature pattern",
    }
    response = client.post(
        f"/api/experiments/{experiment.id}/proposals",
        json=body,
        headers={"If-Match": _etag(client, experiment.id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "target_requires_a_run"


# --- the note citation, and the refusals that protect it ----------------------


def test_a_proposal_must_cite_a_note_this_record_holds(client, experiment):
    for note_id in (None, "", 7, "01JQZZNOTANOTE00000000000"):
        response = _create(client, experiment, note_id=note_id)
        assert response.status_code == 422, (note_id, response.text)
        assert response.json()["error"] == "unknown_note"


def test_a_rule_is_required_unconditionally(client, experiment):
    for rule in (None, "", "   ", 7):
        response = _create(client, experiment, rule=rule)
        assert response.status_code == 422, (rule, response.text)
        assert response.json()["error"] == "invalid_rule"


def test_a_proposal_with_no_value_is_refused(client, experiment):
    body = {
        "note_id": experiment.notes[0].id,
        "target_field_path": OVERRIDE_PATH,
        "rule": "a rule",
        "run_id": experiment.runs[0].id,
    }
    response = client.post(
        f"/api/experiments/{experiment.id}/proposals",
        json=body,
        headers={"If-Match": _etag(client, experiment.id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_proposed_value"


def test_a_null_value_is_refused_because_it_would_clear_the_field(client, experiment):
    """``_apply_run_field`` REMOVES the key for ``None``.

    Clearing a confirmed value is a different act with its own questions — what it
    means for a run that inherited it, and what the workflow should then say — and it
    is not something a proposal may smuggle in.
    """
    response = _create(client, experiment, value=None)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_proposed_value"


def test_the_source_is_read_off_the_note_and_not_off_the_body(client, experiment):
    """One fact, one home. A client-supplied source could disagree with the note's."""
    refused = _create(client, experiment, source="csv_column")
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "unrecognized_field"

    proposal = _created(client, experiment)
    assert proposal["source"] == _stored(experiment.id).notes[0].source


# --- the state machine --------------------------------------------------------


@pytest.mark.parametrize("first", ["reject", "supersede", "withdraw"])
@pytest.mark.parametrize("second", ["accept", "reject", "supersede", "withdraw"])
def test_a_review_act_reaches_an_open_proposal_or_it_reaches_none(
    armed_client, experiment, first, second
):
    """Every non-``open`` state is terminal, and that is a DECISION.

    A proposal that had been rejected and were then accepted would have a history
    saying both, and a reader would need an ordering rule to say which one stands.
    Re-proposing is expressible — a NEW proposal, with its own id and its own audit
    trail — and that keeps every recorded judgement readable exactly as it was made.
    """
    proposal = _created(armed_client, experiment)
    assert (
        _review(armed_client, experiment.id, proposal["proposal_id"], action=first).status_code
        == 200
    )
    body = {"action": second}
    if second == "accept":
        body["accepted_from"] = "candidate"
    response = _review(armed_client, experiment.id, proposal["proposal_id"], **body)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "proposal_not_open"


def test_the_history_is_append_only_and_records_who_and_what(armed_client, experiment):
    proposal = _created(armed_client, experiment)
    assert [h["action"] for h in proposal["history"]] == ["propose"]

    accepted = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
    ).json()["proposal"]
    assert [h["action"] for h in accepted["history"]] == ["propose", "accept"]
    assert accepted["history"][0] == proposal["history"][0], "the opening act was rewritten"
    assert accepted["history"][-1]["from_state"] == proposals.STATE_OPEN
    assert accepted["history"][-1]["to_state"] == proposals.STATE_ACCEPTED


def test_the_revision_helper_refuses_to_rewrite_what_was_proposed():
    """``IMMUTABLE_PROPOSAL_FIELDS`` is a DIFFERENT set from a note's, deliberately.

    A note's immutable set is capture-shaped; a proposal's is proposal-shaped. What
    must not move here is what was proposed — the value, the target, the rule, the
    note, and the digest the acceptance precondition compares against.
    """
    proposal = _a_proposal()
    for field in sorted(proposals.IMMUTABLE_PROPOSAL_FIELDS):
        with pytest.raises(proposals.ImmutableProposal):
            proposals.revise_proposal(proposal, **{field: "tampered"})


def test_the_history_may_only_be_extended():
    proposal = proposals.reject_proposal(_a_proposal(), at="2026-08-29T01:00:00Z")
    with pytest.raises(proposals.ImmutableProposal):
        proposals.revise_proposal(proposal, history=())
    with pytest.raises(proposals.ImmutableProposal):
        proposals.revise_proposal(
            proposal,
            history=(
                dataclasses.replace(proposal.history[0], at="2020-01-01T00:00:00Z"),
                proposal.history[1],
            ),
        )


def test_an_accepted_from_candidate_that_carries_a_different_value_is_refused(
    armed_client, experiment
):
    """"I accepted what was proposed" and "the proposal was wrong" are different claims."""
    proposal = _created(armed_client, experiment, value="Cu2O")
    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
        value="CuO",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "value_is_not_the_candidate"


def test_an_edited_acceptance_writes_the_corrected_value(armed_client, experiment):
    proposal = _created(armed_client, experiment, value="Cu2O")
    response = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="edited",
        value="CuO",
    )
    assert response.status_code == 200, response.text
    body = response.json()["proposal"]
    assert body["accepted_from"] == "edited"
    assert body["accepted_value"] == "CuO"
    assert body["proposed_value"] == "Cu2O", "the proposal was rewritten"

    exp = _stored(experiment.id)
    assert exp.runs[0].overrides[ws.field_address(OVERRIDE_PATH)].payload["value"] == "CuO"


def test_value_and_accepted_from_belong_to_accept_alone(client, experiment):
    proposal = _created(client, experiment)
    response = _review(
        client, experiment.id, proposal["proposal_id"], action="reject", value="CuO"
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field"


# --- the record's validator, and the ordering ---------------------------------


@pytest.mark.parametrize("op", ["create", "review"])
def test_the_record_validator_is_required_and_a_stale_one_writes_nothing(
    client, experiment, op
):
    proposal = _created(client, experiment) if op == "review" else None
    stale = _etag(client, experiment.id)
    # Move the record so the tag above goes stale.
    assert (
        client.post(
            f"/api/experiments/{experiment.id}/notes",
            json={"text": "moves the rev", "source": "typed_note"},
            headers={"If-Match": _etag(client, experiment.id)},
        ).status_code
        == 201
    )

    if op == "create":
        absent = _create(client, experiment)
        # `_create` supplies a fresh tag, so drive the absent/stale cases directly.
        assert absent.status_code == 200
        body = {
            "note_id": experiment.notes[0].id,
            "target_field_path": OVERRIDE_PATH,
            "proposed_value": "CuO",
            "rule": "a rule",
            "run_id": experiment.runs[0].id,
        }
        url = f"/api/experiments/{experiment.id}/proposals"
        assert client.post(url, json=body).status_code == 428
        assert client.post(url, json=body, headers={"If-Match": "junk"}).status_code == 400
        assert (
            client.post(url, json=body, headers={"If-Match": stale}).status_code == 412
        )
    else:
        pid = proposal["proposal_id"]
        assert _review(client, experiment.id, pid, action="reject", if_match=None).status_code == 428
        assert _review(client, experiment.id, pid, action="reject", if_match="junk").status_code == 400
        assert _review(client, experiment.id, pid, action="reject", if_match=stale).status_code == 412
        assert _stored(experiment.id).get_proposal(pid).state == proposals.STATE_OPEN


def test_a_malformed_body_is_refused_whatever_the_validator_says(client, experiment):
    """Every input is resolved BEFORE the precondition is checked.

    So a malformed request is a 422 whether or not the caller's ``If-Match`` happens
    to be current, and a refused request can never leave a partial act behind.
    """
    response = client.post(
        f"/api/experiments/{experiment.id}/proposals",
        json={"target_field_path": "nonsense", "verified": True},
        headers={"If-Match": "junk"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field"
    assert response.json()["key"] == "verified"


def test_a_confirmation_is_required_to_review(client, experiment):
    proposal = _created(client, experiment)
    response = client.post(
        f"/api/experiments/{experiment.id}/proposals/{proposal['proposal_id']}/review",
        json={"action": "reject"},
        headers={"If-Match": _etag(client, experiment.id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "confirmation_required"


@pytest.mark.parametrize("action", [{}, [], 7, None, "invented"])
def test_a_wrong_typed_action_is_a_typed_422_and_never_a_500(client, experiment, action):
    """The unhashable-operand defect the notes routes paid for twice.

    A membership test against a ``frozenset`` HASHES its operand, so ``{}`` and ``[]``
    produced measured 500s there. The ordering — ``isinstance`` first — is copied
    rather than re-derived.
    """
    proposal = _created(client, experiment)
    response = _review(client, experiment.id, proposal["proposal_id"], action=action)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_proposal_action"


def test_a_body_that_is_not_an_object_is_refused(client, experiment):
    response = client.post(
        f"/api/experiments/{experiment.id}/proposals",
        json=["not", "an", "object"],
        headers={"If-Match": _etag(client, experiment.id)},
    )
    assert response.status_code == 422, response.text


def test_a_404_for_an_unknown_proposal_is_distinct_from_an_unknown_record(
    client, experiment
):
    """Collapsing the two 404s sends a client looking in the wrong place."""
    missing = client.get(
        f"/api/experiments/{experiment.id}/proposals/01JQZZNOTAPROPOSAL000000"
    )
    assert missing.status_code == 404
    assert missing.json()["error"] == "proposal_not_found"

    no_record = client.get("/api/experiments/01JQZZNOSUCHRECORD000000/proposals")
    assert no_record.status_code == 404
    assert no_record.json()["error"] == "experiment_not_found"


def test_a_closed_proposal_is_still_listed_and_still_readable(client, experiment):
    """No delete anywhere: every outcome is a state, and a closed one stays visible."""
    proposal = _created(client, experiment)
    assert (
        _review(client, experiment.id, proposal["proposal_id"], action="reject").status_code
        == 200
    )
    listed = client.get(f"/api/experiments/{experiment.id}/proposals").json()
    assert [p["proposal_id"] for p in listed["proposals"]] == [proposal["proposal_id"]]
    assert listed["by_state"]["rejected"] == 1
    assert (
        client.get(
            f"/api/experiments/{experiment.id}/proposals/{proposal['proposal_id']}"
        ).status_code
        == 200
    )


# --- the served vocabularies --------------------------------------------------


def test_the_list_serves_the_sets_it_enforces(client, experiment):
    """The alternative is transcribing four closed sets into a client bundle.

    Where they would be free to drift from what these routes enforce — the defect
    ``_run_view``'s ``overridable`` flag and the notes list's
    ``value_writable_field_paths`` both exist to prevent.
    """
    body = client.get(f"/api/experiments/{experiment.id}/proposals").json()
    assert body["target_field_paths"] == sorted(routes.PROPOSAL_TARGET_PATHS)
    assert body["record_scoped_target_field_paths"] == [RECORD_PATH]
    assert body["states"] == list(proposals.PROPOSAL_STATES)
    assert body["review_actions"] == list(proposals.REVIEW_ACTIONS)
    assert body["accepted_from_values"] == list(proposals.ACCEPTED_FROM_VALUES)
    assert body["window_max"] == routes._PROPOSAL_WINDOW_MAX
    assert body["max_per_record"] == routes._MAX_PROPOSALS_PER_RECORD


def test_the_proposal_sources_are_the_notes_vocabulary_read_not_copied():
    """A proposal is not evidence, so its sources are not the evidence type system.

    Read from ``notes`` rather than restated, so a member added there cannot leave a
    stale set here.
    """
    assert proposals.PROPOSAL_SOURCES is notes.NOTE_SOURCES
    from isaac_records.models import SOURCE_TYPES

    assert not (proposals.PROPOSAL_SOURCES & set(SOURCE_TYPES))


def test_the_operation_descriptions_do_not_overstate_what_this_build_does(client):
    """Copy truthfulness, checked against the SERVED document.

    Three claims a reader acts on: acceptance is refused in a default-configured
    deployment, a proposal is not a confirmed value, and the seven-path refusal is a
    limit of this build rather than a statement about the schema.
    """
    spec = client.get("/api/openapi").json()
    review = spec["paths"][
        "/api/experiments/{experiment_id}/proposals/{proposal_id}/review"
    ]["post"]["description"]
    assert "409 human_actor_required" in review
    assert "default-configured" in review.lower()
    assert "no verifier in this build reads a request" in review

    create = spec["paths"]["/api/experiments/{experiment_id}/proposals"]["post"][
        "description"
    ]
    assert "WRITES NO SCIENTIFIC VALUE" in create
    assert "never asserts anything about the official" in create

    listing = spec["paths"]["/api/experiments/{experiment_id}/proposals"]["get"][
        "description"
    ]
    assert "A PROPOSAL IS NOT A CONFIRMED VALUE" in listing
    assert re.search(r"NOT a statement about the official ISAAC schema", listing)


# ==============================================================================
# THE CLOSURE SLICE, 2026-08-30
# ==============================================================================
#
# Everything below was added when this branch was completed. Two kinds of test, and
# the split matters:
#
#   * FIVE tests for guarantees this module STATES and NOTHING CHECKED. An auditor
#     broke each one in production code and the whole 123-test suite stayed green.
#     Each carries its own ``MUTATION:`` line with the break that was actually run.
#   * Tests for behaviour this slice CHANGED — the reachable 500 on the write path,
#     the precondition ordering on create, `reason` on accept, and the per-record
#     byte ceiling.


def _force(proposal, **changes):
    """Rewrite fields ``revise_proposal`` holds immutable, to build a stored document
    only a HAND EDIT (or a schema refresh) could produce.

    ``object.__setattr__`` reaches any frozen dataclass FIELD, here as everywhere —
    ``IMMUTABLE_PROPOSAL_FIELDS``'s own docstring says so and says what the guard is
    worth. That is exactly the property these tests need: the write path must be
    correct about a document it did not write, and no route can produce one.
    """
    for name, value in changes.items():
        object.__setattr__(proposal, name, value)
    return proposal


# --- the model's closed-state guard -------------------------------------------


@pytest.mark.parametrize(
    "act",
    [
        proposals.accept_proposal,
        proposals.reject_proposal,
        proposals.supersede_proposal,
        proposals.withdraw_proposal,
    ],
)
def test_the_model_refuses_every_review_act_on_a_closed_proposal(act):
    """``_refuse_a_closed_proposal`` is the model's own guard, and it had no test.

    The ROUTE's ``422 proposal_not_open`` is covered; this is the layer beneath it,
    which is the layer that has to hold for a caller that is not this route — the MCP
    surface, a later slice, or a test reaching the pure functions directly. All four
    acts are driven, because ``accept_proposal`` calls the guard on its own line while
    the other three reach it through ``_closed``: a break in either place leaves the
    other three passing.

    MUTATION: made ``_refuse_a_closed_proposal`` a no-op (``return`` as its whole
    body). Measured over THIS FILE — the scope that was actually run, not the whole
    backend suite: **4 failed, 161 passed**, and the four failures were these four
    parameters. Everything else in the file stayed green, including
    ``test_a_review_act_reaches_an_open_proposal_or_it_reaches_none``, because the
    route checks ``proposal.state != STATE_OPEN`` itself before ever calling the model.
    """
    opened = proposals.new_proposal(
        proposal_id="01JQZZ2CLOSED000000000000",
        experiment_id="01JQZZ2EXPERIMENT00000000",
        note_id="01JQZZ2NOTE00000000000000",
        target_field_path=RUN_PATH,
        proposed_value=300.0,
        rule="a rule",
        source="typed_note",
        proposed_utc="2026-08-30T00:00:00Z",
        base_rev=1,
        target_digest="d" * 64,
        trust_basis=proposals._unattributed(),
        run_id="01JQZZ2RUN000000000000000",
    )
    closed = proposals.withdraw_proposal(opened, at="2026-08-30T00:00:01Z")
    assert closed.state == proposals.STATE_WITHDRAWN

    extra = {}
    if act is proposals.accept_proposal:
        extra = {
            "accepted_value": 300.0,
            "accepted_from": proposals.ACCEPTED_FROM_CANDIDATE,
            "applied_via": proposals.APPLIED_VIA_RUN_FIELD,
            "applied_rev": 1,
            "applied_target_digest": "e" * 64,
            "actor_trust_basis": proposals._unattributed(),
        }
    with pytest.raises(proposals.UnsupportedProposal) as refusal:
        act(closed, at="2026-08-30T00:00:02Z", **extra)
    assert "already" in str(refusal.value)
    # And the closed proposal is untouched — the acts are pure, so a refusal cannot
    # have half-applied anything, and this says so rather than assuming it.
    assert closed.state == proposals.STATE_WITHDRAWN
    assert len(closed.history) == 2


# --- excerpt_of never quotes words nobody wrote --------------------------------


def test_an_out_of_range_span_yields_no_excerpt_and_never_a_clamped_one():
    """``excerpt_of``'s stated guarantee: *"a clamped excerpt is a quotation of words
    nobody wrote, which is worse than no quotation at all"*.

    The runtime behaviour was already correct and NOTHING ASSERTED IT. Both
    out-of-range shapes are driven — a span past the end of the text, and a span into
    a note this build could not find at all — because a clamp would answer a string
    for the first and the second is the ``None``-note path beside it.

    MUTATION: replaced the ``if proposal.end_char > len(note_text): return None``
    branch with ``note_text[proposal.start_char : proposal.end_char]`` — i.e. let
    Python's own slice clamping stand. Python does not raise on an out-of-range
    slice; it returns a SHORTER string. Measured over THIS FILE, which is the scope
    that was run: **1 failed, 164 passed**, and the one failure was this test.
    """
    text = "the pellet was CuO2"
    proposal = proposals.new_proposal(
        proposal_id="01JQZZ2EXCERPT0000000000",
        experiment_id="01JQZZ2EXPERIMENT00000000",
        note_id="01JQZZ2NOTE00000000000000",
        target_field_path=OVERRIDE_PATH,
        proposed_value="CuO2",
        rule="a rule",
        source="typed_note",
        proposed_utc="2026-08-30T00:00:00Z",
        base_rev=1,
        target_digest="d" * 64,
        trust_basis=proposals._unattributed(),
        run_id="01JQZZ2RUN000000000000000",
        start_char=15,
        end_char=19,
    )
    # In range: the words are derived, which is what makes the negative cases below
    # a statement about the guard rather than about a function that returns nothing.
    assert proposals.excerpt_of(proposal, text) == "CuO2"

    # PAST THE END. `text[15:400]` is `"CuO2"` in Python — a shorter string, not an
    # error — so a clamp here would answer a quotation the note does not support.
    past_the_end = _force(
        proposals.new_proposal(
            proposal_id="01JQZZ2EXCERPT0000000001",
            experiment_id="01JQZZ2EXPERIMENT00000000",
            note_id="01JQZZ2NOTE00000000000000",
            target_field_path=OVERRIDE_PATH,
            proposed_value="CuO2",
            rule="a rule",
            source="typed_note",
            proposed_utc="2026-08-30T00:00:00Z",
            base_rev=1,
            target_digest="d" * 64,
            trust_basis=proposals._unattributed(),
            run_id="01JQZZ2RUN000000000000000",
            start_char=15,
            end_char=400,
        )
    )
    assert text[15:400] == "CuO2", "the clamp this guard exists to refuse is real"
    assert proposals.excerpt_of(past_the_end, text) is None

    # A shorter note than the one the offsets were taken against — `notes.edit_note`
    # stores a corrected wording beside the immutable capture, and a client may pass
    # either.
    assert proposals.excerpt_of(proposal, "the pellet") is None
    # No note at all is `None` and not `""`: "the note is unavailable" and "the note
    # says nothing there" are different facts.
    assert proposals.excerpt_of(proposal, None) is None


# --- new_proposal deep-copies what was proposed --------------------------------


def test_the_proposed_value_is_deep_copied_and_a_later_edit_cannot_rewrite_it():
    """``new_proposal``'s stated reason for copying: *"a stored reference to a live
    envelope would let a later in-place edit rewrite what was proposed, and this
    record's whole value is that it says what was proposed at the time"*.

    NOTHING CHECKED IT. Every route test passes a literal built inline and then drops
    the reference, so a shared reference is invisible to all of them.

    MUTATION: removed ``copy.deepcopy`` from ``new_proposal`` (stored
    ``proposed_value`` directly). Measured over THIS FILE, which is the scope that was
    run: **1 failed, 164 passed**, and the one failure was this test, on the nested
    mutation.
    """
    live = {"value": "CuO2", "evidence": [{"kind": "user_confirmation"}]}
    proposal = proposals.new_proposal(
        proposal_id="01JQZZ2DEEPCOPY000000000",
        experiment_id="01JQZZ2EXPERIMENT00000000",
        note_id="01JQZZ2NOTE00000000000000",
        target_field_path=OVERRIDE_PATH,
        proposed_value=live,
        rule="a rule",
        source="typed_note",
        proposed_utc="2026-08-30T00:00:00Z",
        base_rev=1,
        target_digest="d" * 64,
        trust_basis=proposals._unattributed(),
        run_id="01JQZZ2RUN000000000000000",
    )
    # A NESTED mutation, not a top-level rebind: `live["value"] = ...` would also be
    # caught by a shallow copy, so it would not distinguish the two and the guarantee
    # the docstring makes is about depth.
    live["evidence"][0]["kind"] = "rewritten_after_the_fact"
    live["value"] = "something else"

    assert proposal.proposed_value == {
        "value": "CuO2",
        "evidence": [{"kind": "user_confirmation"}],
    }
    assert proposal.proposed_value is not live
    assert proposal.history[0].to_state_dict()["accepted_value"] is None

    # `accept_proposal` copies too, and for the same reason — the accepted value is
    # what the writer was handed, and an audit row that a caller can rewrite is not
    # an audit row.
    accepted_live = {"value": "Cu2O"}
    accepted = proposals.accept_proposal(
        proposal,
        at="2026-08-30T00:00:01Z",
        accepted_value=accepted_live,
        accepted_from=proposals.ACCEPTED_FROM_EDITED,
        applied_via=proposals.APPLIED_VIA_RUN_OVERRIDE,
        applied_rev=1,
        applied_target_digest="e" * 64,
        actor_trust_basis=proposals._unattributed(),
    )
    accepted_live["value"] = "rewritten"
    assert accepted.accepted_value == {"value": "Cu2O"}
    assert accepted.history[-1].accepted_value == {"value": "Cu2O"}


# --- an accepted proposal must say HOW it was applied ---------------------------


def test_an_accepted_proposal_cannot_be_constructed_without_saying_which_writer_ran():
    """``__post_init__``'s accepted-state requirement, which contract §5 **I3** rests
    on: *"``accepted`` is terminal-and-applied here, so a row that cannot say how the
    value was written would be claiming an application that may never have happened"*.

    NOTHING CHECKED IT. Every route path supplies ``applied_via`` from
    ``_apply_accepted_proposal``, so no test could reach the missing case.

    Each of the four accepted-state requirements is driven separately, because they
    are four different claims and a test that dropped all four at once could not say
    which one the model still enforces.

    MUTATION: deleted the ``if self.applied_via not in APPLIED_VIA_VALUES: raise``
    branch. Measured over THIS FILE, which is the scope that was run: **1 failed, 164
    passed** — this test, on its ``applied_via`` case, while its other four cases and
    everything else in the file stayed green. That is why the five requirements are
    driven in a loop rather than by one construction.
    """
    base = dict(
        proposal_id="01JQZZ2APPLIEDVIA0000000",
        experiment_id="01JQZZ2EXPERIMENT00000000",
        note_id="01JQZZ2NOTE00000000000000",
        target_field_path=RUN_PATH,
        proposed_value=300.0,
        rule="a rule",
        source="typed_note",
        proposed_utc="2026-08-30T00:00:00Z",
        base_rev=1,
        target_digest="d" * 64,
        trust_basis=proposals._unattributed(),
        state=proposals.STATE_ACCEPTED,
        accepted_value=300.0,
        accepted_from=proposals.ACCEPTED_FROM_CANDIDATE,
        applied_via=proposals.APPLIED_VIA_RUN_FIELD,
        applied_rev=1,
        applied_target_digest="e" * 64,
    )
    # The complete row constructs, or the four refusals below would prove nothing.
    assert proposals.IngestionProposal(**base).applied is True

    for omitted, expected in (
        ("accepted_value", "must record the value that was written"),
        ("accepted_from", "accepted_from must be one of"),
        ("applied_via", "must record WHICH writer applied it"),
        ("applied_rev", "the revision the write was applied on top of"),
        ("applied_target_digest", "what its target held after the"),
    ):
        with pytest.raises(proposals.UnsupportedProposal) as refusal:
            proposals.IngestionProposal(**{**base, omitted: None})
        assert expected in str(refusal.value), omitted

    # And a writer name this build does not have is refused as firmly as a missing
    # one: `applied_via` is a claim about WHICH function ran.
    with pytest.raises(proposals.UnsupportedProposal):
        proposals.IngestionProposal(**{**base, "applied_via": "some_other_writer"})


# --- an unaccepted proposal carries no trace of an application ------------------


@pytest.mark.parametrize(
    "state",
    [
        proposals.STATE_OPEN,
        proposals.STATE_REJECTED,
        proposals.STATE_SUPERSEDED,
        proposals.STATE_WITHDRAWN,
    ],
)
@pytest.mark.parametrize(
    "field,value",
    [
        ("accepted_value", 300.0),
        ("accepted_from", proposals.ACCEPTED_FROM_CANDIDATE),
        ("applied_via", proposals.APPLIED_VIA_RUN_FIELD),
        ("applied_run_id", "01JQZZ2RUN000000000000000"),
        ("applied_rev", 1),
        ("applied_target_digest", "e" * 64),
    ],
)
def test_an_unaccepted_proposal_carries_no_trace_of_an_application(state, field, value):
    """``__post_init__``'s stated honesty invariant: *"'Nobody accepted this' and
    'somebody accepted it and we filed it as open' are different facts, and a record
    that could hold both would make the state unreadable"*.

    SIX FIELDS × FOUR STATES, ALL TWENTY-FOUR, and none of them had a test. This is
    the guarantee that makes ``state`` readable at all, and it is enforced in one
    ``for`` loop — so a break there is a single edit that no route test can see,
    because no route constructs an unaccepted proposal carrying any of the six.

    MUTATION: deleted the ``else:`` branch containing that loop. Measured over THIS
    FILE, which is the scope that was run: **24 failed, 141 passed** — every one of
    the 24 parameters, and nothing else in the file.
    """
    base = dict(
        proposal_id="01JQZZ2NOTRACE0000000000",
        experiment_id="01JQZZ2EXPERIMENT00000000",
        note_id="01JQZZ2NOTE00000000000000",
        target_field_path=RUN_PATH,
        proposed_value=300.0,
        rule="a rule",
        source="typed_note",
        proposed_utc="2026-08-30T00:00:00Z",
        base_rev=1,
        target_digest="d" * 64,
        trust_basis=proposals._unattributed(),
        state=state,
    )
    # The row without the application trace constructs, so the refusal below is about
    # the ONE field and not about the state.
    assert proposals.IngestionProposal(**base).applied is False

    with pytest.raises(proposals.UnsupportedProposal) as refusal:
        proposals.IngestionProposal(**{**base, field: value})
    assert field in str(refusal.value)
    assert f"state {state!r}" in str(refusal.value)


# --- C3: the write path's reachable 500, now a typed 409 ------------------------


@pytest.mark.parametrize(
    "scenario,path,keeps_run",
    [
        # A run-scoped target stored with `run_id: null`. This is the shape that
        # MEASURED as `AttributeError: 'NoneType' object has no attribute 'draft'`
        # -> HTTP 500, from `run.draft.get("fields")` inside `_apply_accepted_proposal`.
        ("run_scoped_path_with_no_run", RUN_PATH, False),
        # The mirror image: the one record-scoped target, stored naming a run. The
        # record-level writer ignores the run entirely, so this would have written the
        # RECORD's own field for a proposal that says it is about one run.
        ("record_scoped_path_naming_a_run", RECORD_PATH, True),
        # A path no write route in this build owns at all — what a schema refresh, or
        # a change to any of the three sets `_proposal_writer_for` dispatches on,
        # leaves behind. `_PROPOSAL_WRITER_SCOPE[None]` is a `KeyError`, which is the
        # same 500 through a different door.
        ("path_with_no_writer_at_all", "system.configuration.gas_flow", False),
    ],
)
def test_a_stored_proposal_whose_scope_its_writer_cannot_serve_is_a_typed_409(
    armed_client, experiment, scenario, path, keeps_run
):
    """A **409**, never a 500, and nothing written.

    `_proposal_writer_for` is re-evaluated at REVIEW time over a `run_id` fixed at
    CREATE time, so the create route's scope check cannot bind this read. The read
    path already handles the class correctly — `_hydrate_proposals` files a pair-shape
    it cannot represent as unreadable rather than raising — and the write path now
    matches it.

    THE STORED DIGEST IS RESTAMPED TO WHAT THE FLIPPED TARGET ACTUALLY HOLDS. Without
    that the request meets `409 proposal_stale` first and this test would pass while
    never reaching the branch it names — the digest and the scope are two different
    preconditions and only one of them is under test here.

    MUTATION: reverted the scope guard at the top of `_apply_accepted_proposal`. All
    three parameters went RED, and the three failures were NOT the same failure — this
    is what was actually observed rather than what the three cases look like from the
    outside:

    * `run_scoped_path_with_no_run` answered **500 Internal Server Error**
      (`AttributeError: 'NoneType' object has no attribute 'draft'`). This is the
      reachable crash on the write path that the guard exists for.
    * `record_scoped_path_naming_a_run` answered **200**, with
      `applied_via: "record_enum_fields"` and `applied_run_id` set to the run — it
      wrote the RECORD's own field and then recorded, in the audit row, that it had
      applied it to a run. The worst of the three, because nothing reports it.
    * `path_with_no_writer_at_all` answered **422 `no_write_path_for_field`**, from
      `set_run_override` raising `NotOverridable` on an address that is not
      experiment-level. So this one was already refused — with the WRONG code and the
      wrong meaning: a `422` tells the caller to fix the body, and there is nothing in
      the body to fix. **An earlier version of this docstring claimed it answered
      `500 KeyError`; that was reasoned from `_PROPOSAL_WRITER_SCOPE[None]` and is
      corrected here, because it was never run.** The `KeyError` is what the NEW guard
      would raise if it indexed rather than used `.get`, which is why it uses `.get`.
    """
    # CREATED AT A PATH THIS BUILD ADMITS, then forced. The third scenario's path is
    # one of the seven the create route refuses outright with
    # `no_write_path_for_field` — which is the create-side guard working — so the only
    # way a proposal reaches review carrying it is a stored document this application
    # did not write, which is exactly the case under test.
    creation = _create(
        armed_client,
        experiment,
        path=RECORD_PATH if keeps_run else RUN_PATH,
        value=RECORD_VALUE if keeps_run else 301.0,
    )
    assert creation.status_code == 200, creation.text
    pid = creation.json()["proposal"]["proposal_id"]

    exp = _stored(experiment.id)
    stored = exp.get_proposal(pid)
    _force(
        stored,
        run_id=exp.runs[0].id if keeps_run else None,
        target_field_path=path,
    )
    # Restamp the precondition so the ONLY thing wrong with this document is the
    # scope. `_current_target_digest` is the route's own helper, so the value is the
    # one the route will compute rather than one this test composed.
    _force(stored, target_digest=routes._current_target_digest(exp, stored))
    exp.save_versioned()

    before = _authoritative_snapshot(_stored(experiment.id))
    response = _review(
        armed_client,
        experiment.id,
        pid,
        action="accept",
        accepted_from="candidate",
        value=RECORD_VALUE if keeps_run else 301.0,
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "target_scope_mismatch", body
    assert body["key"] == path
    assert "Nothing was written" in body["message"]

    after = _stored(experiment.id)
    assert _authoritative_snapshot(after) == before, (
        f"{scenario}: the refused acceptance moved scientific content"
    )
    assert after.get_proposal(pid).state == proposals.STATE_OPEN
    assert after.get_proposal(pid).applied_via is None


def test_the_scope_mismatch_refusal_does_not_gate_the_three_non_writing_acts(
    client, experiment
):
    """A dangling proposal must stay CLEARABLE, which is `target_run_removed`'s rule
    one step earlier and is the same rule here.

    `target_scope_mismatch` says there is nowhere to WRITE the value. Withdrawing
    writes nothing — it records that nobody wants the proposal — so gating it would
    leave a proposal no route could ever clear, in a build with no delete. The first
    version of the `target_run_removed` refusal gated all four acts and made §4's
    "a person may withdraw it" false; this is that lesson applied before the fact.
    """
    creation = _create(client, experiment, path=RUN_PATH, value=301.0)
    assert creation.status_code == 200, creation.text
    pid = creation.json()["proposal"]["proposal_id"]

    exp = _stored(experiment.id)
    _force(exp.get_proposal(pid), run_id=None)
    exp.save_versioned()

    response = _review(client, experiment.id, pid, action="withdraw")
    assert response.status_code == 200, response.text
    assert response.json()["proposal"]["state"] == proposals.STATE_WITHDRAWN


# --- I1: the precondition precedes both state checks ---------------------------


def test_the_precondition_precedes_the_deduplication_branch(client, experiment):
    """The published description says an omitted `If-Match` is `428`. It said so while
    the deduplication branch answered **200** without the header being looked at.

    Nothing was written by that 200 — it returned an existing row — so this was a
    false CLAIM rather than corruption: a success reported for a request that never
    presented the precondition the operation says it requires.

    MUTATION: moved `_check_if_match` back below both state checks — the shape this
    route shipped with. Measured over THIS FILE, which is the scope that was run:
    **2 failed, 163 passed**, and the two failures were this test and
    `test_the_precondition_precedes_the_per_record_ceiling` below. ONE mutation
    catches both because there is one ordering, which is why they are two tests over
    one seam rather than one test asserting two things.
    """
    first = _create(client, experiment, client_request_key="ordering-1")
    assert first.status_code == 200, first.text
    minted = first.json()["proposal"]["proposal_id"]

    body = {
        "note_id": experiment.notes[0].id,
        "target_field_path": OVERRIDE_PATH,
        "proposed_value": "Cu2O",
        "rule": "the token after `the pellet was` matched a material label",
        "run_id": experiment.runs[0].id,
        "client_request_key": "ordering-1",
    }

    absent = client.post(f"/api/experiments/{experiment.id}/proposals", json=body)
    assert absent.status_code == 428, absent.text

    stale = client.post(
        f"/api/experiments/{experiment.id}/proposals",
        json=body,
        headers={"If-Match": '"nope"'},
    )
    assert stale.status_code in (400, 412), stale.text

    # And with the current tag the branch still does its job — the exactly-once
    # guarantee is unchanged, which is the half a reordering could have broken.
    current = client.post(
        f"/api/experiments/{experiment.id}/proposals",
        json=body,
        headers={"If-Match": _etag(client, experiment.id)},
    )
    assert current.status_code == 200, current.text
    assert current.json()["deduplicated"] is True
    assert current.json()["proposal"]["proposal_id"] == minted
    assert len(_stored(experiment.id).proposals) == 1


def test_the_precondition_precedes_the_per_record_ceiling(
    client, experiment, monkeypatch
):
    """The same ordering, for the other state check.

    `too_many_proposals` answered `422` without the header being looked at, so a
    client with no `If-Match` at all learned about a ceiling instead of about the
    precondition it had omitted.

    MUTATION: the same single move as the test above — `_check_if_match` back below
    both state checks. Measured over THIS FILE: **2 failed, 163 passed**; this test
    failed with `422 too_many_proposals` where it requires `428`.
    """
    monkeypatch.setattr(routes, "_MAX_PROPOSALS_PER_RECORD", 1)
    assert _create(client, experiment, value="CuO").status_code == 200

    body = {
        "note_id": experiment.notes[0].id,
        "target_field_path": OVERRIDE_PATH,
        "proposed_value": "one too many",
        "rule": "a rule",
        "run_id": experiment.runs[0].id,
    }
    absent = client.post(f"/api/experiments/{experiment.id}/proposals", json=body)
    assert absent.status_code == 428, absent.text

    # With the tag, the ceiling is what refuses — so the reorder moved the ordering
    # and not the behaviour.
    capped = client.post(
        f"/api/experiments/{experiment.id}/proposals",
        json=body,
        headers={"If-Match": _etag(client, experiment.id)},
    )
    assert capped.status_code == 422, capped.text
    assert capped.json()["error"] == "too_many_proposals"


def test_the_create_declares_exactly_one_success_code_and_the_body_says_which(client):
    """Two outcomes, ONE success code, and the body distinguishes them.

    `POST .../proposals` is the only creating POST in this API that does not answer
    `201`, and the reason is that it may create nothing: an operation-level `201`
    would be an operation-wide claim that it creates. The repo-wide contract test
    refuses two success codes for exactly that ambiguity; this pins the resolution
    from the other side, so a later slice cannot restore the second code here without
    tripping both.
    """
    spec = client.get("/api/openapi").json()
    create = spec["paths"]["/api/experiments/{experiment_id}/proposals"]["post"]
    assert sorted(c for c in create["responses"] if c.startswith("2")) == ["200"]
    assert "deduplicated" in create["responses"]["200"]["description"]


# --- I3: `reason` is refused on accept, never dropped --------------------------


def test_a_reason_on_an_accept_is_refused_and_never_silently_discarded(
    armed_client, experiment
):
    """`reason` was in `_PROPOSAL_REVIEW_KEYS` and `accept_proposal` takes none, so an
    accept carrying one answered **200** and stored nothing.

    A sentence a scientist wrote disappearing into a success response is the defect
    the create route's own allowlist exists to prevent — *"refused rather than
    accepted and ignored"* — and this is that rule applied to the act it was missing
    from.

    MUTATION: neutralised the accept branch of the asymmetry check (`if False:` in
    place of `if "reason" in body:`). Measured over THIS FILE: **1 failed, 164
    passed** — this test, which met `200` with the scientist's sentence stored
    nowhere.
    """
    proposal = _created(armed_client, experiment)
    before = _stored(experiment.id).rev

    refused = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="accept",
        accepted_from="candidate",
        reason="because it looked right",
    )
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "unrecognized_field"
    assert body["key"] == "reason"
    assert "Nothing was written" in body["message"]

    after = _stored(experiment.id)
    assert after.rev == before
    assert after.get_proposal(proposal["proposal_id"]).state == proposals.STATE_OPEN

    # And the three acts that DO take one still do — the refusal is per-act, not a
    # removal of the field.
    kept = _review(
        armed_client,
        experiment.id,
        proposal["proposal_id"],
        action="reject",
        reason="the source sentence was about a different sample",
    )
    assert kept.status_code == 200, kept.text
    history = kept.json()["proposal"]["history"]
    assert history[-1]["reason"] == "the source sentence was about a different sample"


# --- I6: the per-record byte ceiling -------------------------------------------


def test_the_per_record_byte_ceiling_refuses_rather_than_trims(
    client, experiment, monkeypatch
):
    """`_MAX_PROPOSAL_BYTES` bounds ONE proposal and `_MAX_PROPOSALS_PER_RECORD`
    bounds the ROW COUNT, and their product was a **262 MB** experiment document that
    every individual refusal admitted.

    That matters because `load_experiment` parses the whole document on every read and
    `_authoritative_signature` sha256s the whole of it on every save. The bound is
    lowered here so this is a test rather than a load run.

    TWO MUTATIONS, BOTH RUN, because "there is no ceiling" and "the ceiling trims"
    are different defects and only one of them is caught by a status code. Measured
    over THIS FILE both times: **1 failed, 164 passed**, this test.

    MUTATION: neutralised the `len(projected) > _MAX_PROPOSAL_STATE_BYTES` branch.
    MUTATION: kept the branch and made it `exp.proposals.pop(0)` — trim the oldest to
    make room — instead of refusing. The second is the one worth having: a trimming
    build would answer `200` and still hold exactly one proposal, so a count assertion
    alone would pass; it is caught because the stored value is asserted to be the
    FIRST proposal's and not the second's.
    """
    assert routes._MAX_PROPOSAL_STATE_BYTES == routes._MAX_PROPOSAL_BYTES * 16, (
        "the ceiling is written as a multiple of the per-proposal bound so it follows "
        "`_MAX_NOTE_BYTES` rather than drifting from it"
    )

    assert _create(client, experiment, value="CuO").status_code == 200
    # MEASURED WITH THE ROUTE'S OWN RENDERER, not with a plain `json.dumps`. The
    # bound is over the compact separators `_render_exactly_as_a_response_would`
    # emits; a differently-spaced measurement here would make the ceiling this test
    # installs approximate, and "the refusal fired" would stop being a statement
    # about the boundary.
    stored_now = len(
        routes._render_exactly_as_a_response_would(
            [p.to_state() for p in _stored(experiment.id).proposals]
        )
    )
    # A ceiling that ADMITS the row already on file and refuses the next one, so the
    # refusal is about the addition rather than about the record being over already.
    monkeypatch.setattr(routes, "_MAX_PROPOSAL_STATE_BYTES", stored_now + 10)

    refused = _create(client, experiment, value="Cu2O")
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "proposals_too_large"
    assert body["max_bytes"] == stored_now + 10
    assert body["bytes"] > stored_now + 10
    assert "REFUSED rather than trimmed" in body["message"]

    after = _stored(experiment.id)
    assert len(after.proposals) == 1, "the refusal must not have removed anything"
    assert after.proposals[0].proposed_value == "CuO"


# --- DEC-10, as corrected 2026-08-30 -------------------------------------------


def test_a_non_accepting_proposal_act_moves_rev_but_records_no_revision(
    submitting_client, experiment, submission_db
):
    """Contract §10 **DEC-10**, whose original wording said a proposal act *"DOES
    create a revision at the next submit"*. **Measured false, and this is the
    measurement.**

    Both halves are asserted, because the corrected decision is that they come apart:
    `rev` and the `ETag` DO move — proposals are in the authoritative signature, so a
    stale second writer is refused — while the SUBMISSION does not, because
    `submissions.content_signature` is computed over the export units and no export
    unit contains a proposal. `state["proposals"]` sits outside `draft`, which is the
    property §7 chose the location for.

    The `accept` case is the exception and is covered by
    `test_accepting_a_proposal_never_mutates_a_submitted_revision` above, which shows
    revision 2 appearing — and there the revision comes from the VALUE WRITE, not from
    the proposal act.
    """
    submitted = submitting_client.post(
        f"/api/experiments/{experiment.id}/submit",
        headers={"If-Match": _etag(submitting_client, experiment.id)},
    )
    assert submitted.status_code == 200, submitted.text
    snapshot = copy.deepcopy(submission_db.revisions)
    assert [row["revision_no"] for row in snapshot] == [1]
    rev_before = _stored(experiment.id).rev

    proposal = _created(submitting_client, experiment)
    rejected = _review(
        submitting_client,
        experiment.id,
        proposal["proposal_id"],
        action="reject",
        reason="the sentence was about a different sample",
    )
    assert rejected.status_code == 200, rejected.text

    # HALF ONE — `rev` moved. Twice: once for the create, once for the reject.
    assert _stored(experiment.id).rev > rev_before

    # HALF TWO — the submission did not. The record's published content is unchanged,
    # so there is nothing to record and the route says so rather than filing an empty
    # revision.
    resubmitted = submitting_client.post(
        f"/api/experiments/{experiment.id}/submit",
        headers={"If-Match": _etag(submitting_client, experiment.id)},
    )
    assert resubmitted.status_code == 409, resubmitted.text
    assert resubmitted.json()["error"] == "already_submitted"
    assert submission_db.revisions == snapshot


def test_the_contract_no_longer_claims_a_proposal_act_creates_a_revision():
    """The corrected DEC-10 is pinned as TEXT, because a decision table is what a
    future slice reads before it builds.

    Both directions: the false clause must survive only as a struck correction, and
    the corrected claim must be present. A negative control alone would pass on a
    document that had simply deleted the row.
    """
    contract = (
        Path(routes.__file__).resolve().parents[3]
        / "docs"
        / "ingestion-proposal-contract.md"
    ).read_text(encoding="utf-8")
    assert "**DEC-10**" in contract
    assert "MEASURED FALSE 2026-08-30" in contract
    assert "~~**so a proposal act DOES create a revision at the next submit**~~" in contract
    assert "409 already_submitted" in contract
    # And the §7 enumeration now names the one place a proposal DOES travel durably.
    assert "isaac_experiment_revisions.state" in contract
    assert "submission_store.py:504" in contract

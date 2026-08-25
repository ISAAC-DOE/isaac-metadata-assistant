"""Adding a Run used to destroy the answers already given, and say nothing.

THE DEFECT, MEASURED OVER HTTP BEFORE THE FIX
=============================================
``series``, ``qc``, ``assets`` and ``descriptors_outputs`` are RUN-LEVEL blocks
(``workspace.RUN_LEVEL_BLOCKS``). ``Experiment.resolved_run_draft`` reads them off the
RUN, so the experiment's copies stop being part of any exported record the moment a run
exists. And ``workspace.new_run`` defaults a run's draft to ``{}``.

Put those two together and adding a run to a completed record did this::

    answer every question, no runs   -> pending 0 · status ready_to_export   (true)
    POST /runs                       -> pending 0 · status in_review
                                        workflow: complete_metadata COMPLETED
                                                  review_evidence  COMPLETED
    POST /export                     -> 200 {"ok": false}
                                        "'descriptors' is a required property"

Two failures at once, and the second is the worse one:

1. **The workflow lied.** It reported the metadata complete and the evidence reviewed,
   listed nothing to do, and could not export — for a reason no surface named.
2. **The scientist's input was silently discarded.** Everything they had entered was
   still in the document and no longer in any record.

A fresh run had the mirror-image problem: an empty draft carries no blockers, so a run
that needed a spectrum, a verdict and a descriptor reported **nothing pending**.

WHAT THIS FILE PINS
===================
The rule has two halves and the asymmetry between them is the no-guessing contract:

* the FIRST run ADOPTS the experiment's run-level content and its open questions,
  because a zero-run experiment IS its own record and adding the first run moves the
  exported identity onto that run;
* a LATER run does NOT, because copying one run's spectrum onto another asserts that
  two runs measured the same thing — a scientific claim nothing here evidences.

`test_assets.py::test_export_reach_none_is_measured_against_the_real_export_composition`
is the independent corroboration that half of this was known: it PINNED the asset half
of the data loss, called it "a pre-existing behaviour this slice does not change", and
is inverted in the same commit as this file.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from conftest import tutorial_client


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


def _complete_answers(app) -> dict:
    """Every answer for a record on this path, harvested from a seeded scenario."""
    seeded = tutorial_client(app)
    raw = [
        e for e in seeded.get("/api/experiments").json()["experiments"] if e["pending_count"] == 5
    ][0]
    pending = seeded.get(f"/api/experiments/{raw['id']}/pending").json()["pending"]
    answers = {b["id"]: b["demo_answer"]["value"] for b in pending if b["demo_answer"]}
    answers["qc"] = {"status": "valid", "evidence": "I0 stable across all scans."}
    return answers


def _version(client, exp_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}").json()["version"]


def _detail(client, exp_id: str) -> dict:
    return client.get(f"/api/experiments/{exp_id}").json()


def _add_run(client, exp_id: str, label: str) -> str:
    res = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": label},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert res.status_code == 201, res.text
    return res.json()["run"]["id"]


def _completed_record(app) -> tuple:
    client = TestClient(app)
    exp_id = client.post("/api/experiments", json={"title": "A finished record"}).json()["id"]
    applied = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": _complete_answers(app), "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["pending"] == []
    assert applied.json()["status"] == "ready_to_export"
    return client, exp_id


# ---------------------------------------------------------------------------
# The first run adopts what is already there
# ---------------------------------------------------------------------------


def test_adding_a_run_to_a_finished_record_does_not_undo_it(app):
    """THE REGRESSION TEST. Revert `_seed_for_new_run` and this fails at the export."""
    client, exp_id = _completed_record(app)
    _add_run(client, exp_id, "300 K")

    after = _detail(client, exp_id)
    assert after["pending_count"] == 0, after["pending_count"]
    assert after["status"] == "ready_to_export", after["status"]

    exported = client.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True, exported.json()


def test_the_workflow_never_claims_a_step_the_export_will_refuse(app):
    """NEGATIVE CONTROL for the lie, stated as a property rather than as a state.

    Before the fix this exact record reported `complete_metadata: completed` and
    `review_evidence: completed` while `POST /export` answered `ok: false`. The
    property is the CONJUNCTION — no combination of "metadata complete" and "nothing
    pending" may coexist with a refusing export.
    """
    client, exp_id = _completed_record(app)
    _add_run(client, exp_id, "300 K")

    detail = _detail(client, exp_id)
    steps = {s["id"]: s["state"] for s in detail["workflow"]["ordered_steps"]}
    claims_complete = (
        steps.get("complete_metadata") == "completed" and detail["pending_count"] == 0
    )
    exports = (
        client.post(
            f"/api/experiments/{exp_id}/export",
            headers={"If-Match": f'"{_version(client, exp_id)}"'},
        ).json()["ok"]
        is True
    )
    assert not claims_complete or exports, (
        f"the workflow claims completeness the export refuses: {steps}"
    )


def test_the_first_run_carries_the_evidenced_values_into_the_record_it_exports(app):
    """Adoption has to reach the RECORD, not merely the run document."""
    client, exp_id = _completed_record(app)
    _add_run(client, exp_id, "300 K")
    client.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )

    exp = ws.load_experiment(exp_id)
    record = json.loads(exp.export_units()[0].record_path().read_text(encoding="utf-8"))
    assert record["measurement"]["series"], "the spectrum did not reach the record"
    assert record["measurement"]["qc"]["status"] == "valid"
    assert record["descriptors"], "descriptors did not reach the record"


def test_an_unanswered_question_moves_to_the_first_run_rather_than_vanishing(app):
    """A question is content too. Dropping it is the same defect as dropping a value."""
    client = TestClient(app)
    exp_id = client.post("/api/experiments", json={"title": "Half done"}).json()["id"]
    before = {q["id"] for q in client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]}
    assert before == {"series", "qc", "descriptor"}, before

    run_id = _add_run(client, exp_id, "300 K")

    listed = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert {q["id"] for q in listed} == before, listed
    # ...and every one of them now belongs to the run that will export the record.
    assert all(q.get("run_id") == run_id for q in listed), listed


def test_the_experiments_own_run_level_questions_are_withheld_once_a_run_exists(app):
    """NEGATIVE CONTROL for double-asking.

    The experiment's copies are left in the DOCUMENT (withheld, not deleted) so that
    removing the run restores them. But they are no longer answerable into anything
    that ships, so listing them would be a dead end wearing the chrome of a real
    question.
    """
    client = TestClient(app)
    exp_id = client.post("/api/experiments", json={"title": "Half done"}).json()["id"]
    _add_run(client, exp_id, "300 K")

    listed = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert len(listed) == 3, listed  # three, not six
    assert ws.load_experiment(exp_id).draft["pending"], "the entries were DELETED, not withheld"


def test_removing_the_only_run_restores_the_records_own_questions(app):
    """The withholding is derived, so it reverses. Nothing was destroyed to achieve it."""
    client = TestClient(app)
    exp_id = client.post("/api/experiments", json={"title": "Half done"}).json()["id"]
    run_id = _add_run(client, exp_id, "300 K")

    removed = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert removed.status_code == 200, removed.text

    listed = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert {q["id"] for q in listed} == {"series", "qc", "descriptor"}, listed
    assert all(q.get("run_id") is None for q in listed), listed


# ---------------------------------------------------------------------------
# A later run does NOT adopt — the no-guessing half
# ---------------------------------------------------------------------------


def test_a_second_run_is_not_given_the_first_runs_science(app):
    """NEGATIVE CONTROL for the invention this rule exists to prevent.

    Copying the experiment's spectrum onto every run would assert that two runs
    measured the same thing. Nothing here evidences that, so the second run starts with
    the questions instead of with somebody else's answers.
    """
    client, exp_id = _completed_record(app)
    _add_run(client, exp_id, "300 K")
    second = _add_run(client, exp_id, "400 K")

    exp = ws.load_experiment(exp_id)
    run = exp.get_run(second)
    assert not run.draft.get("series"), "a second run was handed a spectrum it did not measure"
    assert not run.draft.get("qc"), "a second run was handed a QC verdict nobody made for it"
    assert not run.draft.get("descriptors_outputs")
    assert {e["kind"] for e in run.draft["pending"]} == {"series", "qc", "descriptor"}


def test_a_second_run_makes_the_record_incomplete_and_the_product_says_so(app):
    """The honest consequence of the rule above, asserted rather than assumed."""
    client, exp_id = _completed_record(app)
    _add_run(client, exp_id, "300 K")
    _add_run(client, exp_id, "400 K")

    detail = _detail(client, exp_id)
    assert detail["pending_count"] == 3, detail["pending_count"]
    assert detail["status"] != "ready_to_export", detail["status"]


def test_a_new_run_only_ever_receives_run_level_questions(app):
    """NEGATIVE CONTROL for asking a record-level question once per run.

    `blocker_is_run_level` fails closed, so an unrecognised kind stays on the record.
    """
    client, exp_id = _completed_record(app)
    _add_run(client, exp_id, "300 K")
    second = _add_run(client, exp_id, "400 K")

    run = ws.load_experiment(exp_id).get_run(second)
    for entry in run.draft["pending"]:
        assert ws.blocker_is_run_level(entry), entry


@pytest.mark.parametrize("entry", [None, "a string", 7, {}, {"kind": "invented"}])
def test_blocker_is_run_level_fails_closed(entry):
    """Nothing unrecognised is ever routed onto a run."""
    assert ws.blocker_is_run_level(entry) is False


def test_the_classification_is_derived_from_block_level_not_restated(app):
    """NEGATIVE CONTROL for two lists drifting apart.

    Every block `BLOCKER_KIND_BLOCK` names must be a real draft block, and the run/record
    split must be `block_level`'s answer rather than a copy of it.
    """
    for kind, block in ws.BLOCKER_KIND_BLOCK.items():
        assert block in ws.RUN_LEVEL_BLOCKS or block in ws.EXPERIMENT_LEVEL_BLOCKS, (kind, block)
        assert ws.blocker_is_run_level({"kind": kind}) == (
            ws.block_level(block) == ws.LEVEL_RUN
        ), kind


# ---------------------------------------------------------------------------
# The worked-example scenarios are untouched
# ---------------------------------------------------------------------------


def test_the_canonical_scenarios_still_report_what_they_always_did(app):
    """None of the five seeds has runs, so none of this reaches them."""
    seeded = tutorial_client(app)
    listing = seeded.get("/api/experiments").json()["experiments"]
    assert sorted(e["pending_count"] for e in listing) == [0, 0, 0, 2, 5]


# ---------------------------------------------------------------------------
# ADOPTION IS COMPLETE — the review found it was not
# ---------------------------------------------------------------------------


def test_adding_a_run_loses_no_run_level_field_from_the_exported_record(app):
    """REGRESSION TEST for the more dangerous half of the data loss.

    Adoption first copied only the four run-level BLOCKS. The block half failed LOUDLY
    at export (`'descriptors' is a required property`), which is how it was found. The
    FIELD half — `context.*` and both `timestamps.acquired_*` — returned `ok: true` and
    simply dropped evidenced values, which is strictly worse. An independent review
    measured five fields and twelve sidecar evidence keys gone from a record that still
    exported clean.

    It compares the record's OWN run-level fields against the record the RUN would
    export, which is a purer measurement than exporting twice: it needs no prior export
    (which the record would now refuse a run after), and it fails on the loss itself
    rather than on a downstream symptom.
    """
    from conftest import client_ws

    client = tutorial_client(app)
    store = client_ws(client)
    rid = ws.SEED_READY_ID

    before = {
        path: envelope
        for path, envelope in (store.load_experiment(rid).draft.get("fields") or {}).items()
        if ws.field_level(path) == ws.LEVEL_RUN
    }
    assert before, "the fixture no longer carries evidenced run-level fields"

    _add_run(client, rid, "300 K")
    exported = client.post(
        f"/api/experiments/{rid}/export",
        headers={"If-Match": f'"{_version(client, rid)}"'},
    )
    assert exported.json()["ok"] is True, exported.json()
    record = json.loads(
        store.load_experiment(rid).export_units()[0].record_path().read_text(encoding="utf-8")
    )

    for path, envelope in before.items():
        node = record
        for segment in path.split("."):
            assert isinstance(node, dict) and segment in node, (
                f"{path} was lost when the run was added"
            )
            node = node[segment]
        assert node == envelope["value"], (path, node, envelope["value"])


def test_the_six_unclassified_configuration_fields_are_deliberately_not_adopted(app):
    """The other side of the same rule, asserted so the omission is a decision.

    `system.configuration.*` is `unclassified` — neither experiment-level nor run-level —
    because whether two runs may differ in detector model is a scientific question this
    repository has no answer to (`docs/run-scope-decision-packet.md`, open for Angel).
    Copying them onto a run would answer it by accident.
    """
    client, exp_id = _completed_record(app)
    exp = ws.load_experiment(exp_id)
    exp.draft.setdefault("fields", {})["system.configuration.detector_model"] = {
        "value": "Vortex ME4",
        "status": "verified",
        "evidence": [{"source_type": "user_confirmation", "answer": "Vortex ME4"}],
    }
    exp.save()

    run_id = _add_run(client, exp_id, "300 K")
    run = ws.load_experiment(exp_id).get_run(run_id)
    assert "system.configuration.detector_model" not in (run.draft.get("fields") or {})
    assert ws.field_level("system.configuration.detector_model") == ws.LEVEL_UNCLASSIFIED


def test_a_run_created_before_seeding_existed_does_not_report_a_finished_record(app):
    """REGRESSION TEST for a state that lives in the DURABLE STORE, not just in theory.

    `new_run` defaulted a run's draft to `{}` before `_seed_for_new_run` existed, and
    `Experiment.to_state()` serialises runs — so every run created before that deploy is
    still an empty-drafted run in Postgres. The first version of the `pending()`
    withholding hid the record's own questions whenever ANY run existed, which put those
    records into exactly the state the seeding change was written to close:

        pending_count 0 · complete_metadata COMPLETED · export ok: false

    Withholding now requires a run to actually carry a question of that kind, so a
    question is never hidden from both.
    """
    client = TestClient(app)
    exp_id = client.post("/api/experiments", json={"title": "Legacy"}).json()["id"]
    exp = ws.load_experiment(exp_id)
    exp.add_run(label="Legacy run", draft={})  # exactly what pre-seeding runs look like
    exp.save()

    detail = _detail(client, exp_id)
    assert detail["pending_count"] == 3, detail["pending_count"]
    steps = {s["id"]: s["state"] for s in detail["workflow"]["ordered_steps"]}
    assert steps["complete_metadata"] != "completed", steps
    listed = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert {q["id"] for q in listed} == {"series", "qc", "descriptor"}, listed


def test_a_run_cannot_be_added_to_a_record_already_exported_without_runs(app):
    """REGRESSION TEST for a duplicate publication adoption made reachable.

    A zero-run record exports under its OWN id; the first run moves the exported
    identity onto the run. Before adoption the second export refused (the run had no
    descriptors), so this never arose. With adoption it succeeded, and an independent
    review measured the result: TWO official ISAAC records, different ids, identical
    science, no `links` relation, and nothing on any surface disclosing it.

    Pruning the earlier record would delete a published artifact — and the export
    keep-set protects `exp.id` unconditionally and deliberately. Emitting a link would
    invent a relation. Refusing states the real constraint: this application has no
    operation that withdraws a published record.
    """
    client, exp_id = _completed_record(app)
    exported = client.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert exported.json()["ok"] is True

    refused = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "300 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["error"] == "already_exported_without_runs"
    assert body["record_id"] == ws.load_experiment(exp_id).record_id
    assert "Nothing was written." in body["message"]
    assert ws.load_experiment(exp_id).runs == []


def test_a_run_can_still_be_added_before_the_record_is_exported(app):
    """NEGATIVE CONTROL for over-refusal. The refusal is about publication, not runs."""
    client, exp_id = _completed_record(app)
    added = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "300 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert added.status_code == 201, added.text


def test_the_six_unclassified_fields_are_absent_from_a_multi_run_record(app):
    """THE MEASURED COST of the open scope question, pinned so the packet cannot go stale.

    `docs/run-scope-decision-packet.md` asks whether the six `system.configuration.*`
    fields belong to a Run or to the Experiment, and has said since 2026-08-10 that
    nothing is blocked on the answer. That was cheap to defer for a reason that no
    longer holds: until 2026-08-19 no record with runs could be exported at all, so
    there were no multi-run records for the six to be missing from.

    Now there are. A record that carries all six, evidenced, publishes
    `system.configuration: null` the moment it has a run — because an unclassified field
    is inherited by neither level and `resolved_run_draft` reads run-level content off
    the RUN. That is not a bug to fix here; guessing a level would answer a scientific
    question by accident. It is a cost to state, and this is where it is stated so the
    packet's claim is checked rather than remembered.

    **If this test starts failing because the fields ARE present, the scope question has
    been answered somewhere** — find where, and make sure a scientist answered it.
    """
    from conftest import client_ws

    client = tutorial_client(app)
    store = client_ws(client)
    rid = ws.SEED_READY_ID

    carried = sorted(
        k for k in (store.load_experiment(rid).draft.get("fields") or {})
        if k.startswith("system.configuration.")
    )
    assert len(carried) == 6, carried
    assert all(ws.field_level(k) == ws.LEVEL_UNCLASSIFIED for k in carried), carried

    _add_run(client, rid, "300 K")
    exported = client.post(
        f"/api/experiments/{rid}/export",
        headers={"If-Match": f'"{_version(client, rid)}"'},
    )
    assert exported.json()["ok"] is True, exported.json()

    record = json.loads(
        store.load_experiment(rid).export_units()[0].record_path().read_text(encoding="utf-8")
    )
    assert record.get("system", {}).get("configuration") is None, (
        "the six unclassified fields reached a multi-run record — the scope question "
        "may have been answered by accident; see docs/run-scope-decision-packet.md"
    )

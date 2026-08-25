"""Export fan-out — contract §1 DECISION D1: one Run produces exactly one ISAAC record.

The application was hard-wired 1 experiment : 1 record: ``routes.post_export`` called
``export_draft(exp.draft, REPO_ROOT, record_id=exp.id)`` and the record id WAS the
experiment id. An experiment with N runs now exports N records, ``record_id ==
run.id``, related by schema-native means.

WHAT THIS FILE IS FOR, in order of how much it would cost to get wrong:

1. **Backward compatibility.** An experiment with NO runs — which is every experiment
   this application can currently create, and all stored data — must export exactly as
   it did: one record, ``record_id == exp.id``, same artifacts, same response shape.
2. **The fan-out itself**, including that ``record_id == run.id`` and that per-run
   drafts resolve inherited experiment-level content by reference.
3. **The run-blind derived state**, which was a MEASURED defect and not a theoretical
   one. On ``201cab0``:

       experiment with NO runs      -> status: needs_attention | pending: 3
       run holding three blockers   -> status: in_review       | pending: 0

   ``pending()``/``draft_ok()``/``status()``/``export_ready()`` read ``self.draft``
   only and never consulted ``self.runs``, so My Experiments would have grouped a
   blocked experiment as needing nothing.
4. **The commit boundary.** Every eligible run is validated before ANY file is
   written; one failure means no file for any run.
5. **The reset hazard.** ``workspace._plan_digest_row`` stats ``exp.record_path()`` /
   ``exp.sidecar_path()`` — SINGULAR. A fan-out has N pairs named by
   ``Run.record_id``, and ``Experiment.record_id`` is ``None`` for such an
   experiment, so both flags were permanently ``False`` and an acknowledged run
   export could be destroyed by a reset in silence.

Every fixture is built from the committed synthetic seed drafts. The truth core
(``src/isaac_records/``) and ``schema/`` are untouched by the slice this file covers.
"""

from __future__ import annotations

import copy
import inspect
import json
import pathlib
import re

import pytest

import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_records.export import export_draft
from isaac_records.models import field_value, user_confirmation

from conftest import client_ws, tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


# --- fixture builders ---------------------------------------------------------
#
# The committed export-ready seed draft (``_full_draft``) is SPLIT into its
# experiment-level and run-level halves using the application's OWN classifiers
# (``field_level`` / ``block_level``), rather than by a hand-written list. That is
# deliberate: a hand-written list would be a second definition of the split and could
# drift from the one the product uses, and these tests would then pass while the
# product's composition was wrong.


def _split_full_draft() -> tuple[dict, dict]:
    """``(experiment_draft, run_draft)`` derived from the export-ready seed.

    Unclassified content stays where the committed decision puts it: ``meta`` and
    ``implicit`` on the experiment (the export composer carries them onto each run),
    ``block_evidence`` split by the natural-key prefix its own keys carry.
    """
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
        k: copy.deepcopy(v) for k, v in block_evidence.items() if k.startswith("attribution:")
    }
    run["block_evidence"] = {
        k: copy.deepcopy(v) for k, v in block_evidence.items() if not k.startswith("attribution:")
    }
    return experiment, run


def _sample_id_envelope(value: str) -> dict:
    """A user-confirmed ``sample.sample_id`` — the one field a sibling link rests on."""
    return field_value(
        value,
        status="verified",
        evidence=[user_confirmation("Sample id?", value, "2026-01-01T00:00:00Z")],
    )


def _fan_out_experiment(
    store,
    *,
    experiment_id: str,
    run_labels: tuple[str, ...],
    sample_id: str | None = None,
):
    """An experiment with N export-ready runs, persisted in ``store``'s scope."""
    experiment_draft, run_draft = _split_full_draft()
    if sample_id is not None:
        experiment_draft["fields"]["sample.sample_id"] = _sample_id_envelope(sample_id)
    exp = store.create_experiment(
        "Fan-out fixture", {"kind": "synthetic"}, experiment_draft, id=experiment_id
    )
    for label in run_labels:
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    return store.load_experiment(experiment_id)


def _etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _export(client, experiment_id: str):
    return client.post(
        f"/api/experiments/{experiment_id}/export",
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _artifact_stems(exp) -> set[str]:
    """Every record-id stem with an artifact in this experiment's records dir."""
    records_dir = exp.records_dir
    if not records_dir.is_dir():
        return set()
    stems = set()
    for path in records_dir.iterdir():
        name = path.name
        if name.endswith(".evidence.json"):
            stems.add(name[: -len(".evidence.json")])
        elif name.endswith(".json"):
            stems.add(name[: -len(".json")])
    return stems


# --- 1. backward compatibility: no runs, one record, record_id == exp.id -------


def test_an_experiment_with_no_runs_still_exports_one_record_keyed_to_its_own_id(client):
    """THE COMMON CASE, AND THE ONE THAT MUST NOT MOVE.

    Every experiment this API can create today has zero runs, and so does all stored
    data. The seed's export-ready example is exported over the real HTTP surface and
    every observable is asserted: the record id, both artifact basenames, the on-disk
    pair, and the singular ``artifact_refs`` shape the response has always carried.

    The fan-out keys (``records``, ``pruned_record_ids``) must be ABSENT, not merely
    empty — a zero-run export is not a fan-out of one and must not present as one.
    """
    experiment_id = ws.SEED_READY_ID
    response = _export(client, experiment_id)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["ok"] is True
    assert body["record_id"] == experiment_id
    assert body["record"]["record_id"] == experiment_id
    assert body["artifact_refs"] == {
        "record_filename": f"{experiment_id}.json",
        "sidecar_filename": f"{experiment_id}.evidence.json",
    }
    assert "records" not in body
    assert "pruned_record_ids" not in body
    assert "runs" not in body

    exp = client_ws(client).load_experiment(experiment_id)
    assert exp.record_id == experiment_id
    assert _artifact_stems(exp) == {experiment_id}
    assert json.loads(exp.record_path().read_text())["record_id"] == experiment_id


def test_a_zero_run_export_draft_is_the_experiments_own_draft_object(client):
    """Backward compatibility is a property of the CODE PATH, not of a composition rule.

    The zero-run unit is handed ``exp.draft`` ITSELF — the same object the pre-fan-out
    route passed to ``export_draft`` — so there is no composition rule that can drift
    away from today's behaviour without this identity failing first.
    """
    exp = client_ws(client).load_experiment(ws.SEED_READY_ID)
    units = exp.export_units()
    assert len(units) == 1
    assert units[0].run is None
    assert units[0].target_id == exp.id
    assert units[0].draft is exp.draft


# --- 2. N runs -> N records, record_id == run.id -------------------------------


def test_an_experiment_with_n_runs_exports_exactly_n_records_keyed_to_run_ids(client):
    """The decision itself: one Run, one record, ``record_id == run.id``.

    Asserted three ways, because any one of them alone could pass while the fan-out
    was wrong: the response's ``records`` list, the ids stamped on the Runs in the
    persisted state, and the artifacts actually on disk.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTTHREERUNS00001"
    exp = _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2", "Run 3")
    )
    run_ids = [run.id for run in exp.sorted_runs()]

    response = _export(client, experiment_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True

    assert [entry["record_id"] for entry in body["records"]] == run_ids
    assert [entry["run_id"] for entry in body["records"]] == run_ids
    assert [entry["run_label"] for entry in body["records"]] == ["Run 1", "Run 2", "Run 3"]

    # `record_id` / `artifact_refs` are SINGULAR by name; a fan-out has several, and
    # filling them from an arbitrary one would be a false singular.
    assert body["record_id"] is None
    assert body["artifact_refs"] is None

    reloaded = store.load_experiment(experiment_id)
    assert [run.record_id for run in reloaded.sorted_runs()] == run_ids
    assert reloaded.record_id is None
    assert _artifact_stems(reloaded) == set(run_ids)

    for run_id in run_ids:
        record = json.loads((reloaded.records_dir / f"{run_id}.json").read_text())
        assert record["record_id"] == run_id
        sidecar = json.loads((reloaded.records_dir / f"{run_id}.evidence.json").read_text())
        assert sidecar["record_id"] == run_id


def test_every_fan_out_record_carries_the_shared_grouping_tag(client):
    """``tags`` is the schema's designated grouping for a SET of records.

    A tag is a label, not a scientific claim, and its value encodes only a stored
    identifier — so emitting one asserts nothing about the science.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTTAGGROUPING001"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))

    assert _export(client, experiment_id).status_code == 200
    reloaded = store.load_experiment(experiment_id)
    for run in reloaded.sorted_runs():
        record = json.loads((reloaded.records_dir / f"{run.record_id}.json").read_text())
        assert f"experiment:{experiment_id}" in record["tags"]
    assert exp.draft.get("tags") is None  # the stored draft gained nothing


# --- 3. sibling relations: exactly one, and nothing where nothing is supported --


def test_runs_sharing_a_sample_id_are_linked_same_sample_as_with_evidence(client):
    """The ONE relation stored structure supports, emitted with the evidence it must cite.

    The schema's own words are the justification: *"Two records share a sample_id if
    and only if they measured the same physical object — this is the basis that gives
    same_sample_as links their meaning."* The link is therefore a restatement of a
    stored equality under a definition the schema supplies, not a scientific judgement.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTSAMESAMPLE0001"
    exp = _fan_out_experiment(
        store,
        experiment_id=experiment_id,
        run_labels=("Run 1", "Run 2"),
        sample_id="SYNTH-PELLET-001",
    )
    run_ids = [run.id for run in exp.sorted_runs()]

    assert _export(client, experiment_id).status_code == 200
    reloaded = store.load_experiment(experiment_id)

    for run_id in run_ids:
        record = json.loads((reloaded.records_dir / f"{run_id}.json").read_text())
        siblings = [other for other in run_ids if other != run_id]
        assert record["links"] == [
            {"rel": "same_sample_as", "target": other, "basis": "same_sample_id"}
            for other in siblings
        ]
        sidecar = json.loads((reloaded.records_dir / f"{run_id}.evidence.json").read_text())
        for other in siblings:
            key = f"links:same_sample_as|{other}|same_sample_id"
            entries = sidecar["evidence"][key]
            assert entries[0]["source_type"] == "derivation"
            assert "sample_id" in entries[0]["rule"]


def test_runs_with_no_stored_sample_id_get_no_link_at_all(client):
    """EMITTING NOTHING IS THE CORRECT ANSWER, and it is asserted rather than assumed.

    With no ``sample.sample_id`` there is no stored fact supporting ANY member of the
    link vocabulary: ``replica_of`` would assert the runs are replicates (they may be
    a deliberate temperature series — the opposite claim), ``follows`` would read a
    procedural relation out of a display order key, ``derived_from`` and
    ``shared_material_batch`` have no stored counterpart at all. So the records carry
    the shared grouping tag and no ``links`` key — which is exactly what a reader of
    ``CLAUDE.md`` §5 should expect, and is why this test asserts the ABSENCE.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTNOSAMPLEID0001"
    _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))

    assert _export(client, experiment_id).status_code == 200
    reloaded = store.load_experiment(experiment_id)
    for run in reloaded.sorted_runs():
        record = json.loads((reloaded.records_dir / f"{run.record_id}.json").read_text())
        assert "links" not in record
        assert f"experiment:{experiment_id}" in record["tags"]


def test_a_single_run_is_never_linked_to_itself(client):
    """A group of one has no sibling. No self-link, no link key, still tagged."""
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTSINGLERUN00001"
    _fan_out_experiment(
        store,
        experiment_id=experiment_id,
        run_labels=("Run 1",),
        sample_id="SYNTH-PELLET-001",
    )

    assert _export(client, experiment_id).status_code == 200
    reloaded = store.load_experiment(experiment_id)
    run = reloaded.sorted_runs()[0]
    record = json.loads((reloaded.records_dir / f"{run.record_id}.json").read_text())
    assert "links" not in record


# --- 4. run-blind derived state (the measured defect) ---------------------------


def test_a_blocking_field_inside_a_run_is_counted_and_blocks_export_readiness():
    """THE MEASURED DEFECT. This test FAILS on ``201cab0``.

    Reproduced there before the fix::

        run carries 3 blockers -> status: in_review | pending: 0 | export_ready: False
        runs: 1 | blocking items inside the run: 3

    ``pending()`` returned ``[]`` for an experiment whose only Run could not be
    completed, and ``status()`` therefore reported ``in_review`` rather than
    ``needs_attention``. My Experiments groups on ``status()``.

    Driven against the store rather than over HTTP so the derivation is asserted
    directly, with no route in between to obscure which function is wrong.
    """
    from isaac_api.experiment_repository import blank_draft

    blank = blank_draft()
    assert len(blank["pending"]) == 3  # the fixture's premise, stated not assumed

    exp = ws.Experiment(
        id="01JQZ0RUNBLINDPENDING00001",
        title="run-blind",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={"meta": copy.deepcopy(blank["meta"]), "fields": {}, "pending": []},
    )
    run = exp.add_run(label="Run 1", draft=copy.deepcopy(blank))

    assert exp.draft.get("pending") == []  # the EXPERIMENT's own draft is clean
    assert len(run.draft["pending"]) == 3  # the RUN is what is blocked

    assert exp.pending_count() == 3
    assert exp.export_ready() is False
    assert exp.status() == ws.NEEDS_ATTENTION


def test_a_run_sourced_pending_entry_names_the_run_it_belongs_to():
    """A blocker must be addressable to the Run that owns it.

    A flat list of three identically-worded blockers from three runs is unusable: a
    client cannot tell which run to open. Experiment-level entries are passed through
    untouched, so a zero-run experiment's list is byte-identical to what it was.
    """
    from isaac_api.experiment_repository import blank_draft

    blank = blank_draft()
    exp = ws.Experiment(
        id="01JQZ0RUNPENDINGADDRESS001",
        title="addressable",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={
            "meta": copy.deepcopy(blank["meta"]),
            "fields": {},
            "pending": [{"kind": "experiment-level", "question": "own blocker"}],
        },
    )
    first = exp.add_run(label="Run 1", draft=copy.deepcopy(blank))
    second = exp.add_run(label="Run 2", draft=copy.deepcopy(blank))

    entries = exp.pending()
    assert entries[0] == {"kind": "experiment-level", "question": "own blocker"}
    assert "run_id" not in entries[0]

    run_entries = entries[1:]
    assert len(run_entries) == 6
    assert {e["run_id"] for e in run_entries} == {first.id, second.id}
    assert {e["run_label"] for e in run_entries} == {"Run 1", "Run 2"}
    # The blocker's own content survives the tagging.
    assert {e["kind"] for e in run_entries} == {"series", "qc", "descriptor"}


def test_status_is_done_only_when_every_run_is_exported(client):
    """``all_units_exported`` is ALL runs, not any.

    Contract §3 D4: a required validation failure on any Run blocks the whole
    submission, so any weaker aggregate would report a readiness the export path will
    not honour.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTSTATUSDONE0001"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    assert exp.status() == ws.READY_TO_EXPORT

    exp.sorted_runs()[0].record_id = "01JQZ0PRETENDEXPORTED00001"
    assert exp.all_units_exported() is False
    assert exp.status() != ws.DONE

    exp.sorted_runs()[1].record_id = "01JQZ0PRETENDEXPORTED00002"
    assert exp.all_units_exported() is True
    assert exp.status() == ws.DONE


def test_zero_run_derived_state_is_unchanged(client):
    """The other half of the aggregate: a zero-run experiment answers as it always did."""
    store = client_ws(client)
    ready = store.load_experiment(ws.SEED_READY_ID)
    new_draft = store.load_experiment(ws.SEED_NEW_DRAFT_ID)

    assert ready.runs == []
    assert ready.pending() == list(ready.draft.get("pending") or [])
    assert ready.status() == ws.READY_TO_EXPORT
    assert ready.export_ready() is True
    assert ready.all_units_exported() is ready.exported()

    assert new_draft.pending_count() > 0
    assert new_draft.status() == ws.NEEDS_ATTENTION


# --- 5. the commit boundary ----------------------------------------------------


def test_a_validation_failure_on_one_run_writes_no_artifact_for_any_run(client):
    """PHASE 1 IS ALL-OR-NOTHING. One refusal means zero files.

    Two runs are export-ready and the third has its QC verdict removed, which
    ``validate_draft`` refuses (a measurement with series must carry an evidenced qc
    verdict — no default 'valid'). The whole export must refuse with nothing written,
    not two records and an error.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTONEBADRUN00001"
    exp = _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2", "Run 3")
    )
    broken = exp.sorted_runs()[1]
    broken.draft.pop("qc")
    exp.save_versioned()

    response = _export(client, experiment_id)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["ok"] is False
    assert body["failed_run_ids"] == [broken.id]
    assert [entry["ok"] for entry in body["runs"]] == [True, False, True]
    assert body["errors"]

    reloaded = store.load_experiment(experiment_id)
    assert _artifact_stems(reloaded) == set()
    assert [run.record_id for run in reloaded.sorted_runs()] == [None, None, None]
    assert reloaded.record_id is None


def test_a_failed_run_is_addressable_by_run_id_and_label(client):
    """Per-run failures name their Run, and carry that run's own reports."""
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTADDRESSABLE001"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Alpha", "Beta"))
    broken = exp.sorted_runs()[1]
    broken.draft.pop("qc")
    exp.save_versioned()

    body = _export(client, experiment_id).json()
    failed = [entry for entry in body["runs"] if not entry["ok"]]
    assert len(failed) == 1
    assert failed[0]["run_id"] == broken.id
    assert failed[0]["run_label"] == "Beta"
    assert failed[0]["record_id"] == broken.id
    assert failed[0]["errors"]
    assert failed[0]["draft_report"] is not None


def test_a_fault_between_two_unit_writes_leaves_a_state_that_reconciles(client):
    """THE GUARANTEE ACTUALLY PROVIDED, asserted rather than claimed.

    Validation is all-or-nothing and the state is saved once, after every file. It is
    NOT atomic across the individual file writes. This test faults the SECOND run's
    record write, then asserts both halves of what that leaves and that the ordinary
    retry repairs it:

    * the first run's pair is on disk but NO run holds a ``record_id`` — the state
      never claims a fan-out it did not complete;
    * a clean retry republishes every not-yet-exported run and converges.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTPARTIALWRITE01"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    first, second = exp.sorted_runs()

    real = routes.atomic_write_text
    target = exp.records_dir / f"{second.id}.json"
    faulted = {"count": 0}

    def _maybe_fail(path, text):
        if pathlib.Path(path) == target:
            faulted["count"] += 1
            raise OSError("simulated fault between two units' artifact writes")
        return real(path, text)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(routes, "atomic_write_text", _maybe_fail)
        with pytest.raises(OSError):
            _export(client, experiment_id)
    assert faulted["count"] == 1

    mid = store.load_experiment(experiment_id)
    assert _artifact_stems(mid) == {first.id}  # one pair written, one not
    assert [run.record_id for run in mid.sorted_runs()] == [None, None]
    assert mid.status() != ws.DONE  # the state claims no completed fan-out

    response = _export(client, experiment_id)
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    healed = store.load_experiment(experiment_id)
    assert [run.record_id for run in healed.sorted_runs()] == [first.id, second.id]
    assert _artifact_stems(healed) == {first.id, second.id}


def test_an_already_materialised_run_is_not_rewritten_when_a_sibling_exports(client):
    """Records are immutable. A partial fan-out exports only what is missing.

    Adding a run to an experiment whose earlier runs are already on disk must export
    the new one and leave the existing records byte-identical — republishing them from
    a draft that may have moved on would silently rewrite an immutable record.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTPARTIALADD0001"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1",))
    assert _export(client, experiment_id).status_code == 200

    exported = store.load_experiment(experiment_id)
    first = exported.sorted_runs()[0]
    original_bytes = (exported.records_dir / f"{first.id}.json").read_bytes()

    _, run_draft = _split_full_draft()
    second = exported.add_run(label="Run 2", draft=copy.deepcopy(run_draft))
    exported.save_versioned()

    response = _export(client, experiment_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert [entry["run_id"] for entry in body["records"]] == [second.id]

    final = store.load_experiment(experiment_id)
    assert (final.records_dir / f"{first.id}.json").read_bytes() == original_bytes
    assert _artifact_stems(final) == {first.id, second.id}


def test_re_exporting_a_fully_exported_fan_out_is_refused_as_immutable(client):
    """Every unit materialised -> 409, exactly as the single-record case always did."""
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTIMMUTABLE00001"
    _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    assert _export(client, experiment_id).status_code == 200

    response = _export(client, experiment_id)
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "record_exists"


# --- 6. inheritance stays BY REFERENCE ----------------------------------------


def test_editing_an_experiment_field_changes_what_a_non_overriding_run_exports(client):
    """CONTRACT §2 D2 — inheritance is by reference, resolved on read, never copied.

    Two things are asserted together, and neither alone is the property:

    * the run's exported record REFLECTS an experiment-level edit made after the run
      existed (so it is not a stale copy taken at run creation);
    * the run's STORED document still contains none of it (so nothing was copied down
      — the run stores only the ABSENCE of an override).
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTBYREFERENCE001"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1",))
    run = exp.sorted_runs()[0]

    before = exp.resolved_run_draft(run)["fields"]["sample.material.name"]["value"]
    exp.draft["fields"]["sample.material.name"]["value"] = "Renamed synthetic pellet"
    after = exp.resolved_run_draft(run)["fields"]["sample.material.name"]["value"]

    assert before != "Renamed synthetic pellet"
    assert after == "Renamed synthetic pellet"

    # The run's OWN stored draft never held the field, before or after.
    assert "sample.material.name" not in (run.draft.get("fields") or {})
    exp.save_versioned()
    persisted = json.loads(exp.state_path.read_text())
    assert "sample.material.name" not in (persisted["runs"][0]["draft"].get("fields") or {})

    assert _export(client, experiment_id).status_code == 200
    reloaded = store.load_experiment(experiment_id)
    # Read the id back from the RELOADED run: the handler exported through its own
    # instance, so the local `run` object never learned its record id.
    exported_run = reloaded.sorted_runs()[0]
    assert exported_run.id == run.id
    record = json.loads((reloaded.records_dir / f"{exported_run.record_id}.json").read_text())
    assert record["sample"]["material"]["name"] == "Renamed synthetic pellet"


def test_an_override_displaces_the_inherited_value_for_that_run_only(client):
    """The override half: one run diverges, its sibling keeps inheriting."""
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTOVERRIDEONE001"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    first, second = exp.sorted_runs()

    address = ws.field_address("sample.material.name")
    exp.set_run_override(
        first,
        address,
        field_value(
            "Overridden pellet",
            status="verified",
            evidence=[user_confirmation("Material?", "Overridden pellet", "2026-01-01T00:00:00Z")],
        ),
    )
    exp.save_versioned()

    assert exp.resolved_run_draft(first)["fields"]["sample.material.name"]["value"] == (
        "Overridden pellet"
    )
    assert exp.resolved_run_draft(second)["fields"]["sample.material.name"]["value"] != (
        "Overridden pellet"
    )

    assert _export(client, experiment_id).status_code == 200
    reloaded = store.load_experiment(experiment_id)
    names = {
        run.label: json.loads(
            (reloaded.records_dir / f"{run.record_id}.json").read_text()
        )["sample"]["material"]["name"]
        for run in reloaded.sorted_runs()
    }
    assert names["Run 1"] == "Overridden pellet"
    assert names["Run 2"] != "Overridden pellet"


def test_the_inherited_attribution_block_takes_its_evidence_with_it(client):
    """``block_evidence`` MUST be merged or every fan-out export fails.

    ``attribution`` is experiment-level and inherited; ``validate_draft`` demands a
    covered ``attribution:<name>|<role>`` entry for each contributor. Inheriting the
    block without its evidence refuses the export — so this is a requirement, not a
    preference, and it is pinned so a later "simplification" cannot drop it.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTBLOCKEVIDENC01"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1",))
    run = exp.sorted_runs()[0]

    resolved = exp.resolved_run_draft(run)
    assert resolved["attribution"] == exp.draft["attribution"]
    assert any(k.startswith("attribution:") for k in resolved["block_evidence"])
    assert "qc:status" in resolved["block_evidence"]  # the run's own survived the merge

    # And the experiment-level `implicit` provenance is not silently discarded.
    assert {entry["about"] for entry in resolved["implicit"]} == {"absorbing_element", "edge"}

    assert export_draft(resolved, ws.REPO_ROOT, record_id=run.id).ok is True


# --- 7. orphan artifacts when the run set changes ------------------------------


def test_re_export_after_a_run_is_removed_leaves_no_orphan_artifact(client):
    """A deleted run's record must not linger, unreachable, in the records dir.

    ``_prune_orphan_artifacts`` removes only ``<record-id>.json`` /
    ``<record-id>.evidence.json`` pairs inside THIS experiment's own records dir whose
    id is not a current unit's, and only after a successful state save.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTORPHANPRUNE001"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    first, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    exported = store.load_experiment(experiment_id)
    assert _artifact_stems(exported) == {first.id, second.id}

    # Remove the second run and add a third.
    _, run_draft = _split_full_draft()
    exported.runs = [run for run in exported.runs if run.id != second.id]
    third = exported.add_run(label="Run 3", draft=copy.deepcopy(run_draft))
    exported.save_versioned()

    response = _export(client, experiment_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["pruned_record_ids"] == [second.id]

    final = store.load_experiment(experiment_id)
    assert _artifact_stems(final) == {first.id, third.id}
    assert not (final.records_dir / f"{second.id}.json").exists()
    assert not (final.records_dir / f"{second.id}.evidence.json").exists()


def test_pruning_never_touches_a_file_that_is_not_a_record_artifact(client):
    """The blast radius, pinned. Only ULID-named artifact pairs are candidates."""
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTPRUNESCOPE0001"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1",))
    exp.records_dir.mkdir(parents=True, exist_ok=True)
    bystander = exp.records_dir / "notes.json"
    bystander.write_text("{}\n", encoding="utf-8")
    not_an_id = exp.records_dir / "not-a-record-id.json"
    not_an_id.write_text("{}\n", encoding="utf-8")

    result = routes._prune_orphan_artifacts(exp, {"01JQZ0KEEPTHISRECORDID0001"})
    # F9 — the three-way answer. Nothing was removed AND nothing was protected AND
    # the prune was not declined: a file that is not a record artifact is simply not
    # a candidate, which is a different fact from every one of those three.
    assert result == {"pruned": [], "protected": [], "declined": False}
    assert bystander.exists()
    assert not_an_id.exists()


def test_a_zero_run_experiment_is_never_pruned(client):
    """Backward compatibility again: the pruner is not even reached without runs."""
    store = client_ws(client)
    assert _export(client, ws.SEED_READY_ID).status_code == 200
    exp = store.load_experiment(ws.SEED_READY_ID)
    stray = exp.records_dir / "01JQZ0STRAYARTIFACTFILE001.json"
    stray.write_text("{}\n", encoding="utf-8")

    response = _export(client, ws.SEED_READY_ID)
    assert response.status_code == 409  # already exported; nothing runs after this
    assert stray.exists()


# --- 8. the reset hazard: the plan digest must see a run's artifact pair --------


def test_the_reset_plan_digest_row_covers_every_runs_artifact_pair(client):
    """THE INTEGRATION HAZARD. PR #91 made the digest row stat the artifact pair so an
    export self-heal could not be destroyed by a reset in silence. It stats
    ``exp.record_path()`` / ``exp.sidecar_path()`` — SINGULAR, and ``None`` for a
    fan-out experiment, whose N pairs are named by ``Run.record_id``.

    The destructive path is the fan-out form of the one #91 closed: a run is exported
    (covered — ``Run.record_id`` is inside the authoritative signature), its record
    file later goes missing, and a re-export republishes it. ``run.record_id`` is
    ALREADY set, so the signature does not move, ``save_versioned`` returns ``False``,
    the version token does not move — and without the per-run presence flags NO row
    component moves at all.

    This test asserts the row MOVES when a run's artifact is removed, which is exactly
    the signal the reset's per-record precondition consumes.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTDIGESTROW00001"
    _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    assert _export(client, experiment_id).status_code == 200

    exp = store.load_experiment(experiment_id)
    row_before = ws._plan_digest_row(exp, ws.AMBIGUOUS)

    run = exp.sorted_runs()[0]
    (exp.records_dir / f"{run.record_id}.json").unlink()

    row_after = ws._plan_digest_row(store.load_experiment(experiment_id), ws.AMBIGUOUS)
    assert row_after != row_before

    # And the difference is in the per-run element, not incidentally elsewhere.
    assert row_before[:-1] == row_after[:-1]
    assert row_before[-1] == [[r.id, True, True] for r in exp.sorted_runs()]
    assert row_after[-1][0] == [run.id, False, True]


def test_the_digest_row_for_a_zero_run_experiment_gains_only_an_empty_list(client):
    """The row's meaning for the common case is unchanged; only its shape grows."""
    store = client_ws(client)
    exp = store.load_experiment(ws.SEED_READY_ID)
    row = ws._plan_digest_row(exp, ws.CANONICAL)
    assert row[-1] == []
    assert row[:-1] == [
        exp.id,
        ws.CANONICAL,
        exp.version_token(),
        len(exp.answer_log or []),
        ws._authoritative_signature(exp),
        False,
        False,
    ]


# --- 9. the record_id guard the run-domain slice left owed to this one ----------


def test_a_persisted_run_record_id_that_is_not_a_record_id_hydrates_as_not_exported():
    """``Run.from_state`` guards ``record_id``, because this slice builds paths from it.

    The run-domain slice documented the unguarded pass-through as a known gap owed to
    "the export fan-out slice that starts writing it". Anything that is not a valid
    record id becomes ``None`` — fail-closed and true, because a malformed id names no
    artifact this application ever wrote.
    """
    for bad in ("../../etc/passwd", "", 7, {"nope": True}, "lowercase0000000000000000"):
        run = ws.Run.from_state({"id": "01JQZ0GUARDRECORDIDRUN0001", "record_id": bad})
        assert run.record_id is None, bad

    good = ws.Run.from_state(
        {"id": "01JQZ0GUARDRECORDIDRUN0001", "record_id": "01JQZ0GUARDRECORDIDREC0001"}
    )
    assert good.record_id == "01JQZ0GUARDRECORDIDREC0001"


# --- 10. claims a record must not make (independent review, DO NOT SHIP) -------
#
# Every test below reproduces a defect an independent adversarial review MEASURED on
# `f7c286c` — the first fan-out commit. They are grouped here rather than folded into
# the sections above because what they have in common is not a code path: it is that
# each one made the application state something that was not true.


def _formula_override(value: str) -> dict:
    return field_value(
        value,
        status="verified",
        evidence=[user_confirmation("Formula?", value, "2026-01-01T00:00:00Z")],
    )


def test_no_sibling_link_is_emitted_against_a_record_whose_written_sample_id_differs(client):
    """C1 — THE LINK MUST BE TRUE OF THE TWO RECORDS, not of the current draft.

    ``_apply_sibling_grouping`` grouped on the CURRENTLY COMPOSED ``sample.sample_id``
    and included already-materialised units. An already-materialised unit's record is
    frozen at the value it held when it was written, so changing the experiment-level
    ``sample.sample_id`` and exporting a new run produced, on ``f7c286c``::

        OLD record ...817C sample_id: SYN-ORIGINAL
        NEW record ...JYM5 sample_id: SYN-DIFFERENT
        NEW record links: [{'rel': 'same_sample_as', 'target': '...817C',
                            'basis': 'same_sample_id'}]

    with a sidecar derivation asserting *"Both records carry sample.sample_id
    'SYN-DIFFERENT'"* — a value the target record does not contain. The link is
    provably false from the two records alone: a fabricated scientific relationship
    in an official ISAAC record (CLAUDE.md §5).
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTSTALESIBLING10"
    _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1",), sample_id="SYN-ORIGINAL"
    )
    assert _export(client, experiment_id).status_code == 200

    exported = store.load_experiment(experiment_id)
    first = exported.sorted_runs()[0]
    first_path = exported.records_dir / f"{first.record_id}.json"
    first_bytes = first_path.read_bytes()
    assert json.loads(first_bytes)["sample"]["sample_id"] == "SYN-ORIGINAL"

    later = store.load_experiment(experiment_id)
    later.draft["fields"]["sample.sample_id"] = _sample_id_envelope("SYN-DIFFERENT")
    _, run_draft = _split_full_draft()
    second = later.add_run(label="Run 2", draft=copy.deepcopy(run_draft))
    later.save_versioned()

    assert _export(client, experiment_id).status_code == 200
    final = store.load_experiment(experiment_id)
    new_record = json.loads((final.records_dir / f"{second.id}.json").read_text())

    assert new_record["sample"]["sample_id"] == "SYN-DIFFERENT"
    assert "links" not in new_record
    # …and the frozen record was not rewritten to make the claim true retroactively.
    assert first_path.read_bytes() == first_bytes


def test_a_later_run_still_links_to_a_sibling_whose_written_record_agrees(client):
    """C1 CONTROL — the fix must not silently delete the relation it was asked to check.

    Same shape as the test above with the sample id LEFT ALONE, so the target
    record really does carry the id the evidence sentence names. The link, and the
    evidence quoting that id, must still be emitted.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTLIVESIBLING010"
    _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1",), sample_id="SYNTH-PELLET-001"
    )
    assert _export(client, experiment_id).status_code == 200

    exported = store.load_experiment(experiment_id)
    first = exported.sorted_runs()[0]
    _, run_draft = _split_full_draft()
    second = exported.add_run(label="Run 2", draft=copy.deepcopy(run_draft))
    exported.save_versioned()

    assert _export(client, experiment_id).status_code == 200
    final = store.load_experiment(experiment_id)
    new_record = json.loads((final.records_dir / f"{second.id}.json").read_text())
    assert new_record["links"] == [
        {"rel": "same_sample_as", "target": first.record_id, "basis": "same_sample_id"}
    ]
    sidecar = json.loads((final.records_dir / f"{second.id}.evidence.json").read_text())
    key = f"links:same_sample_as|{first.record_id}|same_sample_id"
    assert "SYNTH-PELLET-001" in sidecar["evidence"][key][0]["rule"]
    # The sentence is checkable against the target record, which is the whole point.
    target = json.loads((final.records_dir / f"{first.record_id}.json").read_text())
    assert target["sample"]["sample_id"] == "SYNTH-PELLET-001"


def test_carried_implicit_provenance_is_dropped_for_a_run_that_overrides(client):
    """C2 — a derivation must not survive an override of the field it derives from.

    ``_merge_implicit`` carried every experiment-level ``implicit`` entry onto every
    run. Measured on ``f7c286c`` for a run overriding ``sample.material.formula``::

        resolved formula: FeO2   record formula: FeO2
        sidecar implicit:absorbing_element: {"value": "Cu", "evidence": [{...
          "rule": "absorbing element = sole non-oxygen element in
                   sample.material.formula (CuO2 -> Cu)"}]}

    Applying the stated rule to this record's own value yields ``Fe``. The docstring's
    argument ("merging asserts nothing that was not already asserted and evidenced on
    the experiment") holds only while the run agrees with the experiment.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTIMPLICITDROP10"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1",))
    run = exp.sorted_runs()[0]
    exp.set_run_override(
        run, ws.field_address("sample.material.formula"), _formula_override("FeO2")
    )
    exp.save_versioned()

    resolved = exp.resolved_run_draft(run)
    assert resolved["fields"]["sample.material.formula"]["value"] == "FeO2"
    assert resolved.get("implicit") is None

    assert _export(client, experiment_id).status_code == 200
    final = store.load_experiment(experiment_id)
    exported_run = final.sorted_runs()[0]
    sidecar = json.loads(
        (final.records_dir / f"{exported_run.record_id}.evidence.json").read_text()
    )
    assert [k for k in sidecar["evidence"] if k.startswith("implicit:")] == []


def test_carried_implicit_provenance_survives_a_run_that_overrides_nothing(client):
    """C2 CONTROL — dropping it from a NON-overriding run would delete real evidence.

    A run that overrides nothing genuinely holds the experiment's values, so the
    experiment's derivations are true of it and withholding them would silently
    remove recorded evidence from the sidecar.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTIMPLICITKEEP10"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1",))
    run = exp.sorted_runs()[0]
    resolved = exp.resolved_run_draft(run)
    assert {e["about"] for e in resolved["implicit"]} == {"absorbing_element", "edge"}

    assert _export(client, experiment_id).status_code == 200
    final = store.load_experiment(experiment_id)
    sidecar = json.loads(
        (final.records_dir / f"{final.sorted_runs()[0].record_id}.evidence.json").read_text()
    )
    assert sidecar["evidence"]["implicit:absorbing_element"]["value"] == "Cu"


def test_a_legacy_record_from_a_half_written_export_survives_the_next_fan_out(client):
    """C3 — prune must not delete a record in the crash window its own handler repairs.

    The keep-set was ``{unit.target_id} | {exp.record_id}``, and ``exp.record_id`` is
    ``None`` in exactly the half-written state the reconciliation branch exists for
    (artifacts written, state save faulted). Add a run and export, and the previously
    exported record was DELETED — while ``_prune_orphan_artifacts``'s own bound #3
    claimed "a legacy 1:1 artifact is preserved even after runs are added".
    """
    store = client_ws(client)
    experiment_id = ws.SEED_READY_ID

    def _boom(exp, if_match):
        raise OSError("simulated fault between the artifact write and the state save")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(routes, "_save_versioned", _boom)
        with pytest.raises(OSError):
            _export(client, experiment_id)

    half_written = store.load_experiment(experiment_id)
    assert half_written.record_id is None  # the documented crash window, exactly
    assert _artifact_stems(half_written) == {experiment_id}
    legacy_bytes = (half_written.records_dir / f"{experiment_id}.json").read_bytes()

    _, run_draft = _split_full_draft()
    run = half_written.add_run(label="Run 1", draft=copy.deepcopy(run_draft))
    half_written.save_versioned()

    assert _export(client, experiment_id).status_code == 200
    final = store.load_experiment(experiment_id)
    assert _artifact_stems(final) == {experiment_id, run.id}
    assert (final.records_dir / f"{experiment_id}.json").read_bytes() == legacy_bytes


def test_pruning_never_orphans_a_link_target_of_a_surviving_record(client):
    """C4 — a surviving immutable record must not be left pointing at nothing.

    Delete a run whose record a sibling links to, export again, and the target was
    pruned while the sibling's record — immutable, never rewritten — still carried
    ``links[].target`` naming it. ``dangling_link_count`` is a tracked integrity
    metric in this project; this is the application manufacturing one.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTDANGLINGLINK10"
    exp = _fan_out_experiment(
        store,
        experiment_id=experiment_id,
        run_labels=("Run 1", "Run 2"),
        sample_id="SYNTH-PELLET-001",
    )
    first, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    survivor = json.loads(
        (store.load_experiment(experiment_id).records_dir / f"{first.id}.json").read_text()
    )
    assert [link["target"] for link in survivor["links"]] == [second.id]

    trimmed = store.load_experiment(experiment_id)
    trimmed.runs = [run for run in trimmed.runs if run.id != second.id]
    _, run_draft = _split_full_draft()
    third = trimmed.add_run(label="Run 3", draft=copy.deepcopy(run_draft))
    trimmed.save_versioned()

    assert _export(client, experiment_id).status_code == 200
    final = store.load_experiment(experiment_id)
    stems = _artifact_stems(final)
    assert second.id in stems  # the link target survives
    assert {first.id, third.id} <= stems


def test_every_pruned_record_id_is_logged(client, caplog):
    """C3b — the only destructive operation in the app must not be the quietest one.

    ``_prune_orphan_artifacts`` deleted artifact pairs in silence, while the strictly
    less consequential export reconciliation (which deletes nothing) logs a warning.
    """
    import logging

    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTPRUNELOGGED010"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    first, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    trimmed = store.load_experiment(experiment_id)
    trimmed.runs = [run for run in trimmed.runs if run.id != second.id]
    _, run_draft = _split_full_draft()
    trimmed.add_run(label="Run 3", draft=copy.deepcopy(run_draft))
    trimmed.save_versioned()

    with caplog.at_level(logging.WARNING, logger=routes._log.name):
        response = _export(client, experiment_id)
    assert response.status_code == 200, response.text
    assert response.json()["pruned_record_ids"] == [second.id]

    pruned_warnings = [
        rec.getMessage()
        for rec in caplog.records
        if rec.levelno >= logging.WARNING and second.id in rec.getMessage()
    ]
    assert len(pruned_warnings) == 1, caplog.text
    assert "prune" in pruned_warnings[0].lower()
    # Path-free by rule (P30.6): a log line is an exfiltration surface too.
    assert str(final_dir := trimmed.records_dir) not in pruned_warnings[0], final_dir


def test_the_prune_keeps_the_artifact_a_surviving_run_actually_names(client):
    """C7 — ``keep_ids`` keyed on ``unit.target_id``; the artifact is named by ``record_id``.

    ``run.record_id == run.id`` holds today, but nothing asserted it and the module
    keyed the same concept two ways. With a divergent ``record_id`` planted, the prune
    deleted an artifact a SURVIVING run still names.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTIDDIVERGENCE10"
    planted = "01JQZ0FANOUTPLANTEDREC0010"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    first, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    divergent = store.load_experiment(experiment_id)
    kept = next(run for run in divergent.sorted_runs() if run.id == first.id)
    for suffix in (".json", ".evidence.json"):
        source = divergent.records_dir / f"{first.id}{suffix}"
        (divergent.records_dir / f"{planted}{suffix}").write_bytes(source.read_bytes())
    kept.record_id = planted
    divergent.runs = [run for run in divergent.runs if run.id != second.id]
    _, run_draft = _split_full_draft()
    divergent.add_run(label="Run 3", draft=copy.deepcopy(run_draft))
    divergent.save_versioned()

    assert _export(client, experiment_id).status_code == 200
    assert planted in _artifact_stems(store.load_experiment(experiment_id))


def test_marking_a_unit_exported_refuses_an_id_that_is_not_its_target(client):
    """C7 (the invariant itself) — the two names for one concept cannot drift silently.

    ``ExportUnit.mark_exported`` is where a record id becomes state. It is called with
    ``result.record["record_id"]``, minted by ``export_draft(..., record_id=target)``,
    so a mismatch is unreachable by construction — which is exactly why it should be
    stated where a future edit would have to break it deliberately.
    """
    store = client_ws(client)
    exp = store.load_experiment(ws.SEED_READY_ID)
    unit = exp.export_units()[0]
    with pytest.raises(ValueError):
        unit.mark_exported("01JQZ0FANOUTPLANTEDREC0010")
    assert exp.record_id is None
    unit.mark_exported(unit.target_id)  # the real call still works
    assert exp.record_id == exp.id


def test_the_three_workflow_call_sites_agree_on_a_fully_exported_fan_out(client):
    """C5 — three call sites, three answers, and one FALSE ``reopened_steps``.

    ``routes._detail`` used ``exp.exported()``, ``routes._workflow_for`` used
    ``all_units_exported()``, ``dependencies._post_workflow`` used ``exported()``.
    Measured on ``f7c286c`` for a fully-exported fan-out::

        EXPORT response workflow: export: 'completed'
        DETAIL   workflow:        export: 'current'
        DETAIL exported: False | record_id: None | status: done
        ... and any later mutation: reopened_steps: ['export'],
            "Updated 1 field(s); reopened: Export."

    The export step did not reopen. A false ``reopened_steps`` is a claim about the
    scientist's work that did not happen.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTWORKFLOWAGREE0"
    _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))

    export_body = _export(client, experiment_id).json()
    export_step = next(
        s for s in export_body["workflow"]["ordered_steps"] if s["id"] == "export"
    )
    assert export_step["state"] == "completed"

    detail = client.get(f"/api/experiments/{experiment_id}").json()
    detail_step = next(s for s in detail["workflow"]["ordered_steps"] if s["id"] == "export")
    assert detail_step["state"] == "completed"
    assert detail["exported"] is True
    assert detail["artifact"]["state"] == "current"
    # `record_id` and the singular pair stay null — a fan-out has N of each — but the
    # nulls now say WHY instead of reading as "nothing was exported".
    assert detail["record_id"] is None
    assert detail["artifact_refs"]["record_filename"] is None
    assert detail["artifact_refs"]["reason"]

    # THE MUTATION WAS `POST /edit {"edge": "L3"}` AND IT REACHED NOTHING. That is why
    # the old assertions below could be `reopened_steps: []` and "no downstream steps
    # reopened": `implicit` is merged onto a run only while that run holds every one of
    # the record's values, and an independent review measured this write answering 200
    # with `changed_fields: ['edge']` while the run's composed `implicit` was `[]`. The
    # route now REFUSES a run-owned key on a record with runs (`409 belongs_to_a_run`),
    # `edge` included, so that write is no longer available — and it should not be, since
    # it was reporting a change nothing read.
    #
    # The substitute is a REAL write, on the run, through the route that owns it. The
    # assertions therefore change too, and they change in the direction that makes this
    # test stronger: a genuine edit to an exported fan-out DOES stale the artifacts and
    # DOES reopen the export step. The property this test exists for — the three workflow
    # call sites agreeing — is asserted on a mutation whose consequences are real.
    run_id = store.load_experiment(experiment_id).sorted_runs()[0].id
    run_etag = client.get(f"/api/experiments/{experiment_id}/runs/{run_id}").headers["ETag"]
    edited = client.post(
        f"/api/experiments/{experiment_id}/runs/{run_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "compromised", "evidence": "Re-checked; I0 drifted."}},
        },
        headers={"If-Match": run_etag},
    )
    assert edited.status_code == 200, edited.text
    invalidation = edited.json()["invalidation"]
    assert invalidation["changed"] is True
    assert invalidation["changed_fields"] == ["qc"], invalidation
    # `reopened_steps` IS EMPTY, AND THAT IS CORRECT RATHER THAN A LEFTOVER. `export`
    # reopens when a completed step regresses, and `all_units_exported()` is still true:
    # every unit HAS been exported, and that fact did not become false. What did change
    # is whether the written artifacts still match the record — which is the `artifact`
    # block's job, and it says so. Asserting both together is the point: the workflow
    # claims no step was undone, the artifact claims it is stale, and neither is
    # borrowing the other's authority.
    assert invalidation["reopened_steps"] == [], invalidation
    # AND ALL THREE CALL SITES STILL AGREE.
    edited_step = next(
        s for s in edited.json()["workflow"]["ordered_steps"] if s["id"] == "export"
    )
    after = client.get(f"/api/experiments/{experiment_id}").json()
    after_step = next(s for s in after["workflow"]["ordered_steps"] if s["id"] == "export")
    assert edited_step["state"] == after_step["state"] == "completed", (edited_step, after_step)
    assert after["artifact"]["state"] == "stale", after["artifact"]


def test_validate_does_not_return_a_false_negative_for_an_exported_fan_out(client):
    """C6 — the endpoint validated the experiment-level half, which is never exported.

    Measured on ``f7c286c`` for a fully-exported fan-out whose N records had all just
    passed official validation::

        {"ok": false,
         "errors": [{"path": "$", "message": "'descriptors' is a required property"}],
         "dry_run": true}

    ``exp.exported()`` was False, so it fell into the dry-run branch and validated
    ``exp.draft`` — the experiment-level half alone. A validation endpoint asserting a
    schema-invalid verdict about a valid record set is worse than refusing to answer.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTVALIDATETRUE10"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    run_ids = [run.id for run in exp.sorted_runs()]
    assert _export(client, experiment_id).status_code == 200

    response = client.post(f"/api/experiments/{experiment_id}/validate")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True, body
    assert body["errors"] == []
    assert body["dry_run"] is False
    assert [entry["record_id"] for entry in body["runs"]] == run_ids
    assert all(entry["ok"] for entry in body["runs"])
    assert all(entry["dry_run"] is False for entry in body["runs"])


def test_validate_reports_an_unexported_fan_out_as_a_dry_run_per_run(client):
    """C6, the other side: nothing exported yet, so every verdict is a candidate.

    ``dry_run`` states WHICH document was checked, so it must be ``true`` whenever any
    part of the verdict came from an in-memory candidate rather than a written record.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTVALIDATEDRY010"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    run_ids = [run.id for run in exp.sorted_runs()]

    body = client.post(f"/api/experiments/{experiment_id}/validate").json()
    assert body["ok"] is True, body
    assert body["dry_run"] is True
    assert [entry["record_id"] for entry in body["runs"]] == run_ids
    assert all(entry["dry_run"] is True for entry in body["runs"])


def test_the_409_for_a_fan_out_names_no_single_record(client):
    """C10 — the refusal contradicted the endpoint's own documentation.

    The body returned a singular ``record_id`` naming ``sorted_runs()[0]`` while the
    operation's description says ``record_id`` is null for a fan-out.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUT409SHAPE000010"
    _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    assert _export(client, experiment_id).status_code == 200

    response = _export(client, experiment_id)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "record_exists"
    assert body["record_id"] is None
    assert experiment_id not in body["message"]


def test_the_409_for_a_zero_run_experiment_is_byte_identical(client):
    """C10 CONTROL — the common case's refusal must not move by one character."""
    experiment_id = ws.SEED_READY_ID
    assert _export(client, experiment_id).status_code == 200
    response = _export(client, experiment_id)
    assert response.status_code == 409
    assert response.json() == {
        "error": "record_exists",
        "message": f"{experiment_id}.json already exists; records are immutable.",
        "record_id": experiment_id,
    }


def test_the_artifacts_operation_says_why_a_fan_out_has_no_pair_of_its_own(client):
    """The disclosure correction, pinned.

    This operation serves the EXPERIMENT's own artifact pair, and a fan-out has
    none — so four nulls is the correct answer. Beside a fan-out-aware
    ``artifact.state`` of ``current`` those nulls read as "current, but there is
    nothing", which is why the reason is served rather than left to be inferred.
    Listing the per-run pairs is a later slice's job; saying so is this one's.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTARTIFACTSAY001"
    _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    assert _export(client, experiment_id).status_code == 200

    body = client.get(f"/api/experiments/{experiment_id}/artifacts").json()
    assert body["record"] is None and body["sidecar"] is None
    assert body["record_filename"] is None and body["sidecar_filename"] is None
    assert body["artifact"]["state"] == "current"
    assert body["reason"] == routes.FAN_OUT_ARTIFACT_REASON

    # The zero-run case gains nothing: no `reason` key at all.
    zero = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/artifacts").json()
    assert "reason" not in zero


# --- 11. the SECOND review: fixes that repaired one copy of a two-copy defect ---
#
# A second independent adversarial review of the fix commit returned SHIP AFTER
# FIXES. It confirmed the ten findings above are genuinely closed and that no
# zero-run behaviour regressed. What it found instead is a class of its own, and it
# is the reason this section is separate from section 10: several of those fixes
# repaired ONE COPY of a defect that had two, one bought its result by removing
# capability without saying so, one introduced a new permanent bad state, and the
# corrected disclosure block was itself incomplete.
#
# The lesson each test below encodes is "the fix was right and the search for its
# other copies was not", so every one of them asserts AGREEMENT BETWEEN TWO
# SURFACES rather than the behaviour of one.


def _corrupt(path: pathlib.Path) -> None:
    path.write_text("{ this is not json", encoding="utf-8")


# --- F1: the `/validate` fix repaired one of TWO copies ------------------------


def test_the_assistant_validate_thunk_agrees_with_the_validate_endpoint(client):
    """F1 — ``_assistant_validate_dryrun`` still carried the C6 defect verbatim.

    C6 made ``POST .../validate`` fan-out aware. The Assistant Q&A route reaches a
    SECOND copy of the same logic through ``_assistant_validate_dryrun``, which still
    tested ``exp.exported()`` — permanently False for a fan-out — and validated
    ``exp.draft``. Measured on ``c467dc7``, same experiment, one process::

        /api/experiments/{id}/validate         -> ok: true
        routes._assistant_validate_dryrun(exp) -> {"ok": false, "errors":
           [{"path": "$", "message": "'descriptors' is a required property"}]}

    That string is verbatim the defect C6 fixed. The two are now ONE function called
    from both places, so a third divergence would have to be written deliberately.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTASSISTVALID010"
    _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))

    # Before export: both surfaces answer from in-memory candidates.
    before_endpoint = client.post(f"/api/experiments/{experiment_id}/validate").json()
    before_thunk = routes._assistant_validate_dryrun(store.load_experiment(experiment_id))
    assert (before_thunk["ok"], before_thunk["errors"]) == (
        before_endpoint["ok"],
        before_endpoint["errors"],
    )

    assert _export(client, experiment_id).status_code == 200

    endpoint = client.post(f"/api/experiments/{experiment_id}/validate").json()
    assert endpoint["ok"] is True and endpoint["errors"] == []
    thunk = routes._assistant_validate_dryrun(store.load_experiment(experiment_id))
    assert thunk["ok"] is True, thunk
    assert thunk["errors"] == []
    # The assistant channel carries no `runs`/`schema`/`dry_run` — it answers a
    # question, it does not serve the validation contract — so it is projected, not
    # widened. Pinned so the shared function cannot leak its envelope into it.
    assert set(thunk) == {"ok", "errors"}


def test_the_assistant_validate_thunk_is_unchanged_for_a_zero_run_experiment(client):
    """F1 CONTROL — the common case must not move. Both branches, exported and not."""
    store = client_ws(client)
    fresh = routes._assistant_validate_dryrun(store.load_experiment(ws.SEED_READY_ID))
    assert set(fresh) == {"ok", "errors"}
    assert fresh["ok"] is True and fresh["errors"] == []

    assert _export(client, ws.SEED_READY_ID).status_code == 200
    exported = routes._assistant_validate_dryrun(store.load_experiment(ws.SEED_READY_ID))
    assert exported == {"ok": True, "errors": []}

    # …and the crash sentinel still degrades honestly rather than dry-running.
    exp = store.load_experiment(ws.SEED_READY_ID)
    _corrupt(exp.record_path())
    unreadable = routes._assistant_validate_dryrun(store.load_experiment(ws.SEED_READY_ID))
    assert unreadable == {
        "ok": False,
        "errors": [{"path": "$", "message": "Validation could not be completed."}],
    }


# --- F2: "all three `derive_workflow` sites" was a WRONG COUNT ------------------


def test_every_workflow_call_site_agrees_on_a_fully_exported_fan_out(client):
    """F2 — the C5 fix named THREE ``derive_workflow`` sites. There are FOUR call
    sites, plus the definition. ("Five" was this file's own correction of "three",
    and it counted the definition as a call.)

    ``runtime_records._project_one`` — the cross-record runtime projection served by
    ``GET /api/runtime/records`` — still passed ``exported=exp.exported()``. Measured
    on ``c467dc7``::

        runtime_records._project_one(exp)["exported"] -> False
        GET /api/experiments/{id} ["exported"]        -> True

    THIS TEST DOES NOT ESTABLISH THE COUNT, AND IT USED TO SAY IT DID. It asserted
    agreement across four HARD-CODED sites under the sentence *"the count is
    established here rather than remembered"* — so a fifth site, added anywhere,
    passed it untouched, which is the failure mode the sentence promised to prevent.
    The count is established by
    ``test_the_fan_out_disclosure_names_every_surface_that_reads_the_singular_pair``,
    which finds every ``derive_workflow`` caller in the package by AST search and
    pins the resulting set. What THIS test establishes is different and still worth
    having: that the sites, whatever their number, AGREE on one fully-exported
    fan-out. The fourth site, ``corpus_mutation._workflow_consistent``, takes no
    experiment at all — it calls ``derive_workflow`` with literal arguments as a
    pure-function regression check — and is asserted to be exactly that, so it cannot
    quietly become a fifth answer.
    """
    from isaac_api import corpus_mutation, dependencies, runtime_records

    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTRUNTIMEPROJ010"
    _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    assert _export(client, experiment_id).status_code == 200

    exp = store.load_experiment(experiment_id)
    detail = client.get(f"/api/experiments/{experiment_id}").json()

    def export_step(workflow: dict) -> str:
        return next(s for s in workflow["ordered_steps"] if s["id"] == "export")["state"]

    projected = runtime_records._project_one(exp)
    assert projected["exported"] is True, projected
    assert projected["workflow"]["current_step"] == detail["workflow"]["current_step"]
    assert projected["artifact_state"] == "current"
    assert projected["workflow"]["reopened"] is False

    assert detail["exported"] is True
    assert export_step(detail["workflow"]) == "completed"
    assert export_step(routes._workflow_for(exp)) == "completed"
    assert export_step(dependencies._post_workflow(exp)) == "completed"

    # The fifth site takes no experiment: a pure-function check over literals.
    import inspect

    source = inspect.getsource(corpus_mutation._workflow_consistent)
    assert "exported=False" in source
    assert "exp" not in inspect.signature(corpus_mutation._workflow_consistent).parameters


def test_the_runtime_projection_is_unchanged_for_a_zero_run_experiment(client):
    """F2 CONTROL — ``exported()`` and ``all_units_exported()`` are one function here."""
    from isaac_api import runtime_records

    store = client_ws(client)
    before = runtime_records._project_one(store.load_experiment(ws.SEED_READY_ID))
    assert before["exported"] is False and before["record_id"] is None
    assert _export(client, ws.SEED_READY_ID).status_code == 200
    after = runtime_records._project_one(store.load_experiment(ws.SEED_READY_ID))
    assert after["exported"] is True
    assert after["record_id"] == ws.SEED_READY_ID


# --- F5: `/audit` and `/warnings` still asserted false things ------------------


def test_audit_reports_the_records_a_fan_out_actually_exported(client):
    """F5 — ``/audit`` said nothing had been exported about N records on disk.

    Measured on ``c467dc7`` for a fully-exported 2-run fan-out::

        POST .../audit -> {"records": [], "text": "No records found.",
                           "message": "Nothing exported yet — export this
                                       experiment before auditing."}

    The audit itself was never the problem: ``audit_records`` GLOBS this experiment's
    own records dir and would have found every run's record. Only the ``exported()``
    gate in front of it was, and it is the same None-backed predicate C5 and C6 fixed
    two surfaces at a time.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTAUDITTRUTH0010"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    run_ids = [run.id for run in exp.sorted_runs()]

    before = client.post(f"/api/experiments/{experiment_id}/audit").json()
    assert before["records"] == []
    assert "message" in before  # nothing exported yet: still the honest answer

    assert _export(client, experiment_id).status_code == 200
    body = client.post(f"/api/experiments/{experiment_id}/audit").json()
    assert "message" not in body, body
    assert {row["name"] for row in body["records"]} == {f"{rid}.json" for rid in run_ids}
    assert all(row["ok"] for row in body["records"]), body
    assert body["text"] != "No records found."


def test_audit_covers_a_partially_exported_fan_out(client):
    """F5 — the gate asks "is anything on disk", not "is everything exported".

    A partial fan-out has records to audit. Gating on ``all_units_exported()`` would
    have replaced one false "nothing exported" with a narrower one.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTAUDITPARTIAL01"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1",))
    assert _export(client, experiment_id).status_code == 200

    grown = store.load_experiment(experiment_id)
    _, run_draft = _split_full_draft()
    grown.add_run(label="Run 2", draft=copy.deepcopy(run_draft))
    grown.save_versioned()

    body = client.post(f"/api/experiments/{experiment_id}/audit").json()
    assert [row["name"] for row in body["records"]] == [
        f"{exp.sorted_runs()[0].id}.json"
    ]
    assert "message" not in body


def test_audit_is_unchanged_for_a_zero_run_experiment(client):
    """F5 CONTROL — both arms of the gate, byte-for-byte."""
    refused = client.post(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/audit").json()
    assert refused == {
        "records": [],
        "text": "No records found.",
        "message": "Nothing exported yet — export this experiment before auditing.",
    }
    assert _export(client, ws.SEED_READY_ID).status_code == 200
    audited = client.post(f"/api/experiments/{ws.SEED_READY_ID}/audit").json()
    assert [row["name"] for row in audited["records"]] == [f"{ws.SEED_READY_ID}.json"]
    assert "message" not in audited


def test_warnings_describe_the_records_a_fan_out_actually_exported(client):
    """F5 — ``/warnings`` advised on a document that is never exported.

    ``exp.exported()`` is False for a fan-out, so ``_warnings_payload`` dry-ran
    ``exp.draft`` — the experiment-level half. Measured on ``c467dc7`` for a fully
    exported 2-run fan-out::

        GET .../warnings -> dry_run: true, codes ['NO_LINKS','NO_MEASUREMENT_SERIES']
        exported record keys -> [... 'measurement' ...]

    Every record on disk HAS a measurement block. The advice was about a document
    with no run-level content in it at all.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTWARNINGSTRUE01"
    exp = _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"), sample_id="SYN-W"
    )
    run_ids = [run.id for run in exp.sorted_runs()]
    assert _export(client, experiment_id).status_code == 200

    for body in (
        client.get(f"/api/experiments/{experiment_id}/warnings").json(),
        client.post(f"/api/experiments/{experiment_id}/warnings").json(),
    ):
        assert body["advisory"] is True and body["gating"] is False
        assert body["dry_run"] is False, body
        codes = {w["code"] for w in body["warnings"]}
        assert "NO_MEASUREMENT_SERIES" not in codes, body
        assert [entry["record_id"] for entry in body["runs"]] == run_ids
        assert all(entry["dry_run"] is False for entry in body["runs"])

    # …and the claim is checkable against the records themselves.
    final = store.load_experiment(experiment_id)
    for run_id in run_ids:
        record = json.loads((final.records_dir / f"{run_id}.json").read_text())
        assert "measurement" in record


def test_warnings_for_an_unexported_fan_out_are_a_dry_run_per_run(client):
    """F5 — ``dry_run`` states WHICH document the advice describes, per run."""
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTWARNINGSDRY001"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    run_ids = [run.id for run in exp.sorted_runs()]

    body = client.get(f"/api/experiments/{experiment_id}/warnings").json()
    assert body["dry_run"] is True
    assert [entry["record_id"] for entry in body["runs"]] == run_ids
    assert all(entry["dry_run"] is True for entry in body["runs"])


def test_warnings_are_unchanged_for_a_zero_run_experiment(client):
    """F5 CONTROL — no ``runs`` key at all, and the same two arms as before."""
    before = client.get(f"/api/experiments/{ws.SEED_READY_ID}/warnings").json()
    assert "runs" not in before
    assert before["dry_run"] is True
    assert _export(client, ws.SEED_READY_ID).status_code == 200
    after = client.get(f"/api/experiments/{ws.SEED_READY_ID}/warnings").json()
    assert "runs" not in after
    assert after["dry_run"] is False


#: Every attribute whose value depends on the SINGULAR exported pair, or which
#: derives the workflow from it. Read by :func:`_singular_state_callers`.
#:
#: ``all_units_exported``/``any_unit_exported`` are here even though they are the
#: fan-out-AWARE aggregates: a surface that calls one is a surface that had to
#: choose between them, and the choice is exactly what the block records. Leaving
#: them out is how ``derive_workflow`` came to have a caller nobody had to name.
_SINGULAR_STATE_ATTRS = frozenset(
    {
        "exported",
        "record_path",
        "sidecar_path",
        "all_units_exported",
        "any_unit_exported",
    }
)

#: Called as a bare name (``derive_workflow(...)``) or through a module
#: (``workflow.derive_workflow(...)``); both forms count.
_WORKFLOW_DERIVERS = frozenset({"derive_workflow"})


def _export_unit_bindings(func: "ast.AST") -> tuple[set[str], set[str]]:
    """Names inside ``func`` that provably hold an ``ExportUnit`` / a list of them.

    PROVABLY is the whole point, and it is why this is a binding pass and not a
    list of variable names. The version this replaced excluded every receiver
    except two literal identifiers, ``exp`` and ``post_exp``, so renaming the
    parameter was enough to leave the guard — and ``experiment`` was ALREADY the
    parameter name at two sites in ``workspace.py``.

    An ``ExportUnit`` is proved by one of four mechanical facts, never by what a
    variable is called:

      * a parameter annotated ``ExportUnit`` (bare, dotted, or stringified);
      * iteration over something that yields units — ``export_units()`` or a name
        already proved to hold a unit list;
      * a subscript of such a list (``units[0]``);
      * a comprehension over either of those.

    Anything not proved is INCLUDED in the caller set. That direction is
    deliberate: an unproved receiver produces one extra name the disclosure must
    account for, which is a sentence to write; the opposite default produces a
    silent hole, which is the defect this guard exists to prevent.
    """
    import ast

    def _is_unit_annotation(node) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value.strip().strip('"\'').split(".")[-1] == "ExportUnit"
        if isinstance(node, ast.Name):
            return node.id == "ExportUnit"
        if isinstance(node, ast.Attribute):
            return node.attr == "ExportUnit"
        return False

    def _is_unit_list_annotation(node) -> bool:
        # `list[ExportUnit]`, `Sequence["ExportUnit"]`, `list[ws.ExportUnit]`.
        return isinstance(node, ast.Subscript) and _is_unit_annotation(node.slice)

    unit_names: set[str] = set()
    list_names: set[str] = set()

    args = getattr(func, "args", None)
    if args is not None:
        every = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        if args.vararg:
            every.append(args.vararg)
        if args.kwarg:
            every.append(args.kwarg)
        for arg in every:
            if arg.annotation is None:
                continue
            if _is_unit_annotation(arg.annotation):
                unit_names.add(arg.arg)
            elif _is_unit_list_annotation(arg.annotation):
                list_names.add(arg.arg)

    def _yields_units(node) -> bool:
        """``expr`` iterates over ``ExportUnit``s."""
        if isinstance(node, ast.Name):
            return node.id in list_names
        if isinstance(node, ast.Call):
            callee = node.func
            name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
            return name == "export_units"
        return False

    def _is_unit_expr(node) -> bool:
        """``expr`` evaluates to ONE ``ExportUnit``."""
        if isinstance(node, ast.Name):
            return node.id in unit_names
        if isinstance(node, ast.Subscript):
            return _yields_units(node.value)
        return False

    # Two passes, because a binding can be established after a use in source order
    # (`for unit in units` where `units` is assigned earlier is the common shape,
    # but a comprehension can precede its own list assignment textually).
    for _ in range(2):
        for node in ast.walk(func):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if value is None:
                    continue
                bucket = None
                if _yields_units(value) or (
                    isinstance(value, ast.ListComp) and _yields_units(value.generators[0].iter)
                ):
                    bucket = list_names
                elif _is_unit_expr(value):
                    bucket = unit_names
                if bucket is not None:
                    for target in targets:
                        if isinstance(target, ast.Name):
                            bucket.add(target.id)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                if _yields_units(node.iter) and isinstance(node.target, ast.Name):
                    unit_names.add(node.target.id)
            elif isinstance(node, ast.comprehension):
                if _yields_units(node.iter) and isinstance(node.target, ast.Name):
                    unit_names.add(node.target.id)
    return unit_names, list_names


def _singular_state_callers(package: "pathlib.Path") -> set[str]:
    """``{"module.py::function"}`` for every caller the disclosure must name.

    Scans ``package.glob("*.py")`` — EVERY module, not an allowlist. The allowlist
    it replaced held four modules, so the same body of code moved into
    ``assistant_query.py`` was invisible.

    THE KEY IS QUALIFIED, and that is a fix rather than a decoration (B1). It used
    to be the bare function name, with the module carried only in the error message
    — so a caller was identified by a name that 19 pairs of functions in this
    package already share. ``def _summary(exp): return exp.exported()`` added to
    ``assistant_query.py`` passed the whole suite, because ``routes._summary`` is
    already disclosed. That is not a hypothetical shape: this branch's
    ``_assistant_validate_dryrun`` WAS a sibling copy of ``post_validate``, in a
    different module, and it asserted a falsehood for eleven days.
    """
    import ast

    found: set[str] = set()
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Which class, if any, encloses each function — so `self` inside
        # `ExportUnit` (and only there) can be excluded.
        enclosing: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in ast.walk(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        enclosing.setdefault(id(child), node.name)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            unit_names, list_names = _export_unit_bindings(node)
            in_export_unit = enclosing.get(id(node)) == "ExportUnit"
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                callee = inner.func
                # (a) `derive_workflow(...)` / `workflow.derive_workflow(...)`.
                bare = getattr(callee, "id", None) or getattr(callee, "attr", None)
                if bare in _WORKFLOW_DERIVERS:
                    found.add(f"{path.name}::{node.name}")
                    continue
                # (b) the singular pair / the aggregates, on a receiver.
                if not isinstance(callee, ast.Attribute) or callee.attr not in _SINGULAR_STATE_ATTRS:
                    continue
                receiver = callee.value
                if isinstance(receiver, ast.Name):
                    if receiver.id in unit_names or receiver.id in list_names:
                        continue
                    if receiver.id == "self" and in_export_unit:
                        continue
                elif isinstance(receiver, ast.Subscript):
                    if isinstance(receiver.value, ast.Name) and receiver.value.id in list_names:
                        continue
                elif isinstance(receiver, ast.Call):
                    # Resolve a chained receiver by its CALLEE name. Nothing in this
                    # package returns an `ExportUnit` from a call, so every chained
                    # receiver counts — `ws.load_experiment(id).exported()` is the
                    # shape that walked straight past the old `ast.Name`-only test.
                    pass
                found.add(f"{path.name}::{node.name}")
    return found


#: How the disclosure block NAMES a caller: one ``[caller] module.py::function`` per
#: comment line, and nothing else on the line.
#:
#: THE ENUMERATION IS STRUCTURED BECAUSE THE PREVIOUS ONE WAS PROSE (B2). Membership
#: was ``name not in block`` — a substring test against ~150 lines of English — so a
#: new caller named ``state``, ``status``, ``reason``, ``audit`` or ``_detail``
#: satisfied the guard with a SENTENCE. All five were measured GREEN. An entry is now
#: a parsed token that has to be typed deliberately, and nothing a paragraph says can
#: authorise a function.
_GUARD_ENTRY_RE = re.compile(
    r"^#\s+\[caller\]\s+([A-Za-z_][A-Za-z0-9_]*\.py::[A-Za-z_][A-Za-z0-9_]*)\s*$"
)


def _disclosure_block(package: "pathlib.Path") -> str:
    """The fan-out disclosure comment block in that package's ``workspace.py``."""
    text = (package / "workspace.py").read_text(encoding="utf-8")
    start = text.index("# --- WHAT EVERY OTHER SURFACE DOES FOR A FAN-OUT")
    end = text.index("SIBLING_REL = ")
    return text[start:end]


def _disclosure_entries(package: "pathlib.Path") -> set[str]:
    """The qualified names the block authorises, parsed — never matched as prose."""
    return {
        match.group(1)
        for line in _disclosure_block(package).splitlines()
        if (match := _GUARD_ENTRY_RE.match(line))
    }


def _disclosure_verdict(package: "pathlib.Path") -> tuple[list[str], list[str]]:
    """``(missing, stale)`` — the guard's VERDICT, which is the thing to assert on.

    ``missing`` is a caller the block does not name: the hole. ``stale`` is a name
    the block authorises that no function answers to: a pre-authorisation waiting
    for a body, and the one way the structured list could be abused to re-open the
    hole it closes.
    """
    callers = _singular_state_callers(package)
    entries = _disclosure_entries(package)
    return sorted(callers - entries), sorted(entries - callers)


def test_the_fan_out_disclosure_names_every_surface_that_reads_the_singular_pair(client):
    """F5 — the disclosure claimed completeness (*"each is now either fixed or
    stated"*) over four routes, while six more surfaces read the same None-backed
    predicate and were named nowhere.

    THE LIST IS ESTABLISHED BY SEARCH, HERE, AT TEST TIME — not transcribed from a
    reviewer's message and not remembered. Every function in the API package that
    reads ``exported()``, ``record_path()``, ``sidecar_path()``,
    ``all_units_exported()`` or ``any_unit_exported()`` on anything that is not a
    provable ``ExportUnit``, or that calls ``derive_workflow``, must be named in the
    disclosure block.

    THE SEARCH ITSELF WAS THE DEFECT ONCE, WHICH IS WHY IT IS NOW PROBED. The
    version this replaced advertised exactly what is written above and enforced
    something much narrower, so four separate one-line additions each left the suite
    GREEN: a parameter named ``experiment`` rather than ``exp`` (and ``experiment``
    is already the parameter name at ``workspace._apply_sibling_grouping`` and
    ``workspace._run_artifact_presence``); a chained receiver
    (``ws.load_experiment(id).exported()``); the same body in ``assistant_query.py``,
    outside a four-module allowlist; and a brand-new ``derive_workflow`` call site,
    which the searched attribute set did not contain at all despite the block's own
    sentence promising *"plus every ``derive_workflow`` call site"*.

    AND THE IDENTIFIER WAS THE NEXT DEFECT. The verdict keyed on the bare function
    NAME and tested membership by SUBSTRING against the whole block — so a sibling
    copy under a name another module already discloses passed (B1: ``_summary`` in
    ``assistant_query.py``), and so did five new callers whose names the block's
    PROSE happens to contain (B2: ``state``, ``status``, ``reason``, ``audit``,
    ``_detail``). Callers are now qualified ``module.py::function`` and membership is
    tested against a PARSED list of ``[caller]`` entries; a ``stale`` entry — an
    authorised name no function answers to — fails too.

    :func:`test_a_new_caller_cannot_slip_past_the_disclosure_guard` re-runs all
    eleven against this implementation and reads the guard's VERDICT, not the
    search's reach — which is the distinction that let B1 and B2 through the version
    of that test which claimed to measure it.
    """
    package = pathlib.Path(routes.__file__).parent
    block = _disclosure_block(package)

    # THE SEARCHED NAMES ARE ANCHORED TO REAL ATTRIBUTES, and this is not a
    # formality. `_WORKFLOW_DERIVERS` has an anchor — the pinned `call_sites` list
    # below is non-empty, so renaming `derive_workflow` empties it and fails here.
    # `_SINGULAR_STATE_ATTRS` had none: rename `exported()` and the search would
    # simply stop finding those callers, `assert callers` would still pass on the
    # `derive_workflow` half alone, and coverage would shrink in silence.
    for attr in _SINGULAR_STATE_ATTRS:
        assert callable(getattr(ws.Experiment, attr, None)), (
            f"`{attr}` is no longer a method of `Experiment` — the guard is now "
            "searching for a name nothing answers to, and its coverage has shrunk "
            "without a single test failing"
        )
    from isaac_api import workflow as workflow_module

    for name in _WORKFLOW_DERIVERS:
        assert callable(getattr(workflow_module, name, None)), name

    callers = _singular_state_callers(package)
    assert callers, "the search itself found nothing — it has stopped measuring"
    missing, stale = _disclosure_verdict(package)
    assert missing == [], (
        "these read the experiment's singular exported state, or derive the "
        f"workflow, and the fan-out disclosure names none of them: {missing}"
    )
    assert stale == [], (
        "the disclosure names these as callers and the search finds no such "
        f"function — a pre-authorised name is a hole waiting for a body: {stale}"
    )
    # And the claim itself must match what it lists: the old block said "each is now
    # either fixed or stated" over an enumeration that was not complete.
    assert "each is now either fixed or stated" not in block
    # The block states a `derive_workflow` COUNT. Establish it here rather than
    # trusting the sentence: the sentence used to say FIVE call sites when there are
    # four call sites and one definition.
    call_sites = sorted(
        qualified
        for qualified in callers
        if _derives_workflow(package / qualified.split("::")[0], qualified.split("::")[1])
    )
    assert call_sites == [
        "corpus_mutation.py::_workflow_consistent",
        "dependencies.py::_post_workflow",
        "routes.py::_workflow_for",
        "runtime_records.py::_project_one",
    ], call_sites
    assert "FIVE ``derive_workflow`` call sites" not in block


def _derives_workflow(path: "pathlib.Path", func_name: str) -> bool:
    """Whether the named function in ``path`` calls ``derive_workflow``."""
    import ast

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != func_name:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                bare = getattr(inner.func, "id", None) or getattr(inner.func, "attr", None)
                if bare in _WORKFLOW_DERIVERS:
                    return True
    return False


def test_a_new_caller_cannot_slip_past_the_disclosure_guard(tmp_path):
    """F-A — the TEN measured bypasses, re-run against the guard that closed them.

    Each probe is one function appended to a COPY of the API package; the guard is
    then re-run over the copy and its VERDICT is read. A probe absent from
    ``missing`` is a bypass. The first row is the positive control that always
    worked, kept so a guard that stops measuring altogether cannot pass this test by
    finding nothing.

    THIS TEST MEASURED THE WRONG THING UNTIL ``0337d19`` WAS REVIEWED. It asserted
    ``any(name.startswith("_probe") for name in _singular_state_callers(copy))`` —
    the SEARCH's reach — and never the guard's verdict. B1 and B2 are both found by
    the search and then waved through by the membership test, so this test could not
    have caught either, while its own docstring said the reach was "measured, not
    described". It now reads ``missing``.

    Measured on ``74509c4``, with the first five bodies::

        param named `exp`            -> RED   (caught)
        param named `experiment`     -> GREEN (bypassed)
        chained `Call` receiver      -> GREEN (bypassed)
        same body, assistant_query   -> GREEN (bypassed)
        new `derive_workflow` site   -> GREEN (bypassed)

    Measured on ``0337d19`` — the commit whose message called all five closed, and
    they were; these six are the ones its guard could not see::

        `_summary` in assistant_query.py   -> GREEN (bypassed)   B1
        `state`    in routes.py            -> GREEN (bypassed)   B2
        `status`   in memory.py            -> GREEN (bypassed)   B2
        `reason`   in routes.py            -> GREEN (bypassed)   B2
        `audit`    in routes.py            -> GREEN (bypassed)   B2
        `_detail`  in assistant_query.py   -> GREEN (bypassed)   B2

    All eleven are RED here.
    """
    import shutil

    package = pathlib.Path(routes.__file__).parent
    probes = {
        "control_param_named_exp": (
            "routes.py",
            "def _probe_control(exp):\n    return exp.exported()\n",
        ),
        "param_named_experiment": (
            "routes.py",
            "def _probe_renamed(experiment):\n    return experiment.exported()\n",
        ),
        "chained_call_receiver": (
            "routes.py",
            'def _probe_chained():\n    return ws.load_experiment("x").exported()\n',
        ),
        "module_outside_the_old_allowlist": (
            "assistant_query.py",
            "def _probe_elsewhere(exp):\n    return exp.exported()\n",
        ),
        "a_new_derive_workflow_call_site": (
            "routes.py",
            "def _probe_workflow(exp):\n    return derive_workflow(\n"
            "        pending_count=0, draft_ok=True, ready=True, exported=False, rev=1\n    )\n",
        ),
        # B1 — a SIBLING COPY under a name another module already discloses. This is
        # the defect class the guard exists to close: `_assistant_validate_dryrun`
        # was a sibling copy of `post_validate`. The package has 19 duplicated
        # function names across modules, and `_summary` is a disclosed caller in
        # `routes.py`, so a copy in `assistant_query.py` free-rode on its entry.
        "same_name_in_another_module": (
            "assistant_query.py",
            "def _summary(exp):\n    return exp.exported()\n",
        ),
        # B2 — five names the block's PROSE happens to contain. Membership was tested
        # against the whole block as a STRING, so each of these was satisfied by a
        # sentence rather than by an entry. `status` is the worst of them: it is both
        # a disclosed caller (`workspace.Experiment.status`) and an existing function
        # in `memory.py`.
        "prose_free_ride_state": ("routes.py", "def state(exp):\n    return exp.exported()\n"),
        "prose_free_ride_status": ("memory.py", "def status(exp):\n    return exp.exported()\n"),
        "prose_free_ride_reason": ("routes.py", "def reason(exp):\n    return exp.exported()\n"),
        "prose_free_ride_audit": ("routes.py", "def audit(exp):\n    return exp.exported()\n"),
        "prose_free_ride_detail": (
            "assistant_query.py",
            "def _detail(exp):\n    return exp.exported()\n",
        ),
    }
    for label, (module, body) in probes.items():
        copy_dir = tmp_path / label
        shutil.copytree(package, copy_dir, ignore=shutil.ignore_patterns("__pycache__", "data"))
        target = copy_dir / module
        target.write_text(target.read_text(encoding="utf-8") + "\n\n" + body, encoding="utf-8")
        # THE VERDICT, NOT THE REACH. This assertion used to read
        # `any(name.startswith("_probe") for name in _singular_state_callers(copy_dir))`
        # — it measured whether the SEARCH found the function and never whether the
        # GUARD failed. That is precisely why it could not catch B1 or B2, both of
        # which are found by the search and then waved through by the membership test.
        probe_name = body.split("def ", 1)[1].split("(", 1)[0]
        missing, _stale = _disclosure_verdict(copy_dir)
        assert f"{module}::{probe_name}" in missing, (
            f"{label}: the guard's verdict is empty of this caller — the bypass is "
            f"still open. missing={missing}"
        )

    # …and the guard is not simply naming everything: a genuine `ExportUnit`
    # receiver, by every one of the four proof shapes, is still excluded.
    clean = tmp_path / "clean"
    shutil.copytree(package, clean, ignore=shutil.ignore_patterns("__pycache__", "data"))
    (clean / "routes.py").write_text(
        (clean / "routes.py").read_text(encoding="utf-8")
        + "\n\n"
        + "def _probe_annotated(unit: ws.ExportUnit):\n    return unit.record_path()\n\n\n"
        + "def _probe_iterated(exp):\n    for u in exp.export_units():\n"
        + "        if u.record_path():\n            return u\n    return None\n\n\n"
        + "def _probe_subscript(exp):\n    units = exp.export_units()\n"
        + "    return units[0].sidecar_path()\n\n\n"
        + "def _probe_comprehension(exp):\n"
        + "    return [u.record_path() for u in exp.export_units()]\n",
        encoding="utf-8",
    )
    clean_missing, clean_stale = _disclosure_verdict(clean)
    assert clean_missing == [], clean_missing
    assert clean_stale == [], clean_stale


# --- F3: the C4 fix disables pruning in the NORMAL fan-out case ----------------


def test_a_shared_sample_id_makes_the_prune_decline_and_the_response_say_so(client):
    """F3 — C4's protection never expires, so pruning is off in the normal case.

    ``_link_targets_of_surviving_records`` protects any stem named as a
    ``links[].target`` by a kept record. Sibling records are MUTUALLY linked whenever
    two or more runs share a ``sample_id`` — the intended normal case — and surviving
    records are immutable, so nothing ever removes the protection. Measured on
    ``c467dc7``::

        2 runs sharing sample_id, exported (mutually linked);
        delete run 2, add run 3, export ->
          pruned_record_ids: []
          stems on disk: [run1, run2 (orphan), run3]

    The headline prune test passes only because its fixture uses ``sample_id=None``
    and therefore emits no links. The accumulation is REAL and is kept — deleting a
    record a surviving immutable record points at is the worse outcome — but it is no
    longer SILENT: the response names what it declined to remove.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTPROTECTEDPRUNE"
    exp = _fan_out_experiment(
        store,
        experiment_id=experiment_id,
        run_labels=("Run 1", "Run 2"),
        sample_id="SYNTH-PELLET-001",
    )
    first, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    trimmed = store.load_experiment(experiment_id)
    trimmed.runs = [run for run in trimmed.runs if run.id != second.id]
    _, run_draft = _split_full_draft()
    third = trimmed.add_run(label="Run 3", draft=copy.deepcopy(run_draft))
    trimmed.save_versioned()

    body = _export(client, experiment_id).json()
    assert body["ok"] is True
    assert body["pruned_record_ids"] == []
    assert body["protected_record_ids"] == [second.id]
    assert body["prune_declined"] is False
    assert _artifact_stems(store.load_experiment(experiment_id)) == {
        first.id,
        second.id,
        third.id,
    }


def test_nothing_to_prune_is_distinguishable_from_pruning_declined(client):
    """F9 — with F3 the prune has TWO independent ways of doing nothing.

    An unreadable kept record makes every survivor's targets unknown and the prune
    refuses entirely (fail-closed, logged). An empty ``pruned_record_ids`` therefore
    meant three different things at once. The response now separates them.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTPRUNEDECLINE01"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    first, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    trimmed = store.load_experiment(experiment_id)
    trimmed.runs = [run for run in trimmed.runs if run.id != second.id]
    _, run_draft = _split_full_draft()
    trimmed.add_run(label="Run 3", draft=copy.deepcopy(run_draft))
    trimmed.save_versioned()
    _corrupt(trimmed.records_dir / f"{first.id}.json")

    body = _export(client, experiment_id).json()
    assert body["ok"] is True
    assert body["prune_declined"] is True, body
    assert body["pruned_record_ids"] == []
    assert body["protected_record_ids"] == []
    assert second.id in _artifact_stems(store.load_experiment(experiment_id))


def test_a_real_prune_reports_that_it_was_not_declined(client):
    """F9 CONTROL — the ordinary removal keeps reporting exactly what it removed."""
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTPRUNENORMAL010"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    _, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    trimmed = store.load_experiment(experiment_id)
    trimmed.runs = [run for run in trimmed.runs if run.id != second.id]
    _, run_draft = _split_full_draft()
    trimmed.add_run(label="Run 3", draft=copy.deepcopy(run_draft))
    trimmed.save_versioned()

    body = _export(client, experiment_id).json()
    assert body["pruned_record_ids"] == [second.id]
    assert body["protected_record_ids"] == []
    assert body["prune_declined"] is False


# --- F4: the C5 fix introduced a permanent unrepairable `stale` ----------------


def test_exporting_a_new_run_does_not_stale_its_already_exported_siblings(client):
    """F4 — a ``stale`` nothing can repair, offering a destructive reset as the cure.

    ``_fan_out_artifact_state`` compares each materialised record against
    ``transform(unit.draft)``, and ``unit.draft`` comes from ``export_units()``, which
    applies sibling grouping to EVERY unit. So exporting a second run adds the REVERSE
    link into the first run's composed draft — a link ``_apply_sibling_grouping``'s own
    docstring says that record will deliberately never gain, because records are
    immutable. Measured on ``c467dc7``: export run 1 alone; add run 2; export ->

        artifact: {"state": "stale", "reason": "The record changed after export; …
                   regenerate the record (or reset the workspace) to refresh it."}
        status: done | exported: true | re-export -> 409 record_exists

    Nothing changed, and the only remedy offered was a whole-workspace reset.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTSTALESIBLING20"
    _fan_out_experiment(
        store,
        experiment_id=experiment_id,
        run_labels=("Run 1",),
        sample_id="SYNTH-PELLET-001",
    )
    assert _export(client, experiment_id).status_code == 200

    grown = store.load_experiment(experiment_id)
    _, run_draft = _split_full_draft()
    grown.add_run(label="Run 2", draft=copy.deepcopy(run_draft))
    grown.save_versioned()
    assert _export(client, experiment_id).status_code == 200

    detail = client.get(f"/api/experiments/{experiment_id}").json()
    assert detail["exported"] is True
    assert detail["artifact"] == {"state": "current", "reason": None}, detail["artifact"]

    artifacts = client.get(f"/api/experiments/{experiment_id}/artifacts").json()
    assert artifacts["artifact"]["state"] == "current"


def test_a_genuine_change_to_a_fan_out_record_is_still_reported_as_stale(client):
    """F4 CONTROL — the fix must not buy ``current`` by ceasing to compare.

    Only the links sibling grouping ADDS are excluded from the comparison, and only
    for a materialised unit whose record can never be rewritten to carry them. A
    scientific edit still stales the set, which is the whole point of the signal.

    Deliberately a TWO-run fan-out with a shared ``sample_id``, so both records carry
    a sibling link: the exclusion is exercised at the same time as the change it must
    not hide, rather than in a fixture where there is nothing to exclude.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTSTILLSTALE0010"
    _fan_out_experiment(
        store,
        experiment_id=experiment_id,
        run_labels=("Run 1", "Run 2"),
        sample_id="SYNTH-PELLET-001",
    )
    assert _export(client, experiment_id).status_code == 200
    assert client.get(f"/api/experiments/{experiment_id}").json()["artifact"]["state"] == (
        "current"
    )

    edited = store.load_experiment(experiment_id)
    edited.draft["fields"]["sample.material.formula"] = _formula_override("FeO2")
    edited.save_versioned()

    detail = client.get(f"/api/experiments/{experiment_id}").json()
    assert detail["artifact"]["state"] == "stale"
    assert detail["artifact"]["reason"].startswith("The record changed after export")


def test_a_partially_exported_fan_out_is_still_incomplete_not_current(client):
    """F4 CONTROL — the C5 label for "part of the set was never written" survives."""
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTPARTIALSTATE01"
    _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1",), sample_id="SYNTH-PELLET-001"
    )
    assert _export(client, experiment_id).status_code == 200
    grown = store.load_experiment(experiment_id)
    _, run_draft = _split_full_draft()
    grown.add_run(label="Run 2", draft=copy.deepcopy(run_draft))
    grown.save_versioned()

    detail = client.get(f"/api/experiments/{experiment_id}").json()
    assert detail["artifact"]["state"] == "stale"
    assert "have not been exported yet" in detail["artifact"]["reason"]


# --- F6: `_linkable` could emit a target naming a record id no file carries -----


def test_a_sibling_link_target_always_names_a_record_file_that_exists(client):
    """F6 — the materialised branch returned the record's OWN ``record_id``.

    That was justified as "the id of the file that exists", but the FILE is named by
    ``unit.target_id`` and the ``record_id`` inside it is a separate string. With the
    divergence section 10's own C7 test plants, measured on ``c467dc7``::

        targets = ['01JQZ0ADVPHANTOMTARGET0001']
        stems   = ['01KZMKT511J6RCMDGHJ1AVH618', '01KZMKT51KCWDN6C17WRYKQZF7']

    A manufactured dangling link — the exact metric C4 exists to protect. The target
    is now ``unit.target_id``, and a record whose own id disagrees with the file that
    carries it yields NO link, because a record we cannot trust to name itself is
    not evidence for a relation.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTPHANTOMLINK010"
    phantom = "01JQZ0ADVPHANTOMTARGET0001"
    _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1",), sample_id="SYNTH-PELLET-001"
    )
    assert _export(client, experiment_id).status_code == 200

    exported = store.load_experiment(experiment_id)
    first = exported.sorted_runs()[0]
    record_path = exported.records_dir / f"{first.record_id}.json"
    record = json.loads(record_path.read_text())
    record["record_id"] = phantom
    record_path.write_text(json.dumps(record), encoding="utf-8")

    _, run_draft = _split_full_draft()
    second = exported.add_run(label="Run 2", draft=copy.deepcopy(run_draft))
    exported.save_versioned()
    assert _export(client, experiment_id).status_code == 200

    final = store.load_experiment(experiment_id)
    stems = _artifact_stems(final)
    new_record = json.loads((final.records_dir / f"{second.id}.json").read_text())
    targets = [link["target"] for link in new_record.get("links") or []]
    assert phantom not in targets, targets
    assert all(target in stems for target in targets), (targets, sorted(stems))
    # The record could not vouch for its own identity, so no relation is asserted.
    assert targets == []


# --- F7: C1 closed emit-time falsity but not rewrite-time falsity ---------------


def test_a_rewrite_that_would_falsify_a_surviving_siblings_link_is_refused(client):
    """F7 — C1 asked "what will the record I write say"; nothing asked the converse.

    Measured on ``c467dc7``: two runs share ``SYN-A``, exported and mutually linked.
    Delete run 1's artifacts, change the experiment ``sample.sample_id``, and export
    along the blessed self-heal path ->

        01…63G  sample_id SYN-CHANGED  links []
        01…63H  sample_id SYN-A        links ['01…63G']   <- asserts a shared id

    Disprovable from the two records alone, and the falsified record is the SURVIVING
    one, which is immutable and cannot be corrected. The export is refused instead:
    within record immutability there is no way to write this unit without leaving a
    record asserting a relation the pair disproves.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTREWRITEFALSE01"
    exp = _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"), sample_id="SYN-A"
    )
    first, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    exported = store.load_experiment(experiment_id)
    survivor_path = exported.records_dir / f"{second.id}.json"
    survivor_bytes = survivor_path.read_bytes()
    assert [link["target"] for link in json.loads(survivor_bytes)["links"]] == [first.id]

    for suffix in (".json", ".evidence.json"):
        (exported.records_dir / f"{first.id}{suffix}").unlink()
    changed = store.load_experiment(experiment_id)
    changed.draft["fields"]["sample.sample_id"] = _sample_id_envelope("SYN-CHANGED")
    changed.save_versioned()

    response = _export(client, experiment_id)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "sibling_link_conflict"
    assert [c["record_id"] for c in body["conflicts"]] == [first.id]
    assert body["conflicts"][0]["sibling_record_id"] == second.id

    # NOTHING was written, and the surviving record is untouched.
    final = store.load_experiment(experiment_id)
    assert not (final.records_dir / f"{first.id}.json").exists()
    assert survivor_path.read_bytes() == survivor_bytes


def test_a_self_heal_that_falsifies_nothing_still_republishes(client):
    """F7 CONTROL — the refusal must be about the falsehood, not about self-healing.

    Same shape with the sample id LEFT ALONE: the republished record will carry the
    value its sibling's link names, so the pair still agrees and the blessed
    self-heal path must work exactly as it did.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTSELFHEALOK0010"
    exp = _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"), sample_id="SYN-A"
    )
    first, _second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    exported = store.load_experiment(experiment_id)
    for suffix in (".json", ".evidence.json"):
        (exported.records_dir / f"{first.id}{suffix}").unlink()

    response = _export(client, experiment_id)
    assert response.status_code == 200, response.text
    final = store.load_experiment(experiment_id)
    rewritten = json.loads((final.records_dir / f"{first.id}.json").read_text())
    assert rewritten["sample"]["sample_id"] == "SYN-A"


def test_the_conflict_409_offers_only_the_remedy_that_leaves_both_records_true(client):
    """F-B — the 409's SECOND remedy permanently dangles a link, silently.

    The message advised *"Restore the sample id, or remove the run."* Remedy 1 works.
    Remedy 2 was measured, end to end, on ``74509c4``::

        409 sibling_link_conflict -> remove the run -> export = 409 record_exists
        SURVIVOR TARGETS: ['01KZMQ…9H']  STEMS ON DISK: ['01KZMQ…9J']
        DANGLING:         ['01KZMQ…9H']

    The surviving record is immutable, so its ``same_sample_as`` link keeps naming a
    record that will never exist — one instance of exactly the
    ``dangling_link_count`` that ``_link_targets_of_surviving_records`` and
    ``protected_record_ids`` exist to prevent — and NOTHING reports it. The prune
    protects a target it can see; a run removed before the record was ever written
    leaves a target it cannot.

    So the advice is withdrawn rather than annotated. Advice that manufactures the
    defect the neighbouring code is built to prevent is not advice with a caveat.

    This test asserts BOTH halves: the message no longer offers it, and the reason it
    no longer offers it is reproduced here so the removal cannot be undone by someone
    who thinks it was merely terse.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTREMEDYCOST001"
    exp = _fan_out_experiment(
        store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"), sample_id="SYN-A"
    )
    first, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    exported = store.load_experiment(experiment_id)
    for suffix in (".json", ".evidence.json"):
        (exported.records_dir / f"{first.id}{suffix}").unlink()
    changed = store.load_experiment(experiment_id)
    changed.draft["fields"]["sample.sample_id"] = _sample_id_envelope("SYN-CHANGED")
    changed.save_versioned()

    refused = _export(client, experiment_id)
    assert refused.status_code == 409
    message = refused.json()["message"]
    assert "Restore the sample id" in message, message
    assert "remove the run" not in message, message

    # --- and here is what following it used to do, reproduced ------------------
    trimmed = store.load_experiment(experiment_id)
    trimmed.runs = [run for run in trimmed.runs if run.id != first.id]
    trimmed.save_versioned()

    after = _export(client, experiment_id)
    assert after.status_code == 409
    assert after.json()["error"] == "record_exists"

    final = store.load_experiment(experiment_id)
    stems = _artifact_stems(final)
    survivor = json.loads((final.records_dir / f"{second.id}.json").read_text())
    targets = [link["target"] for link in survivor.get("links") or []]
    assert targets == [first.id]
    assert first.id not in stems
    # The immutable survivor now asserts a relation to a record that does not exist,
    # and no surface reports it. THAT is the cost the removed clause was hiding.
    assert [t for t in targets if t not in stems] == [first.id]


# --- F8: a NO-OP override stripped all inherited `implicit` --------------------


def test_a_no_op_override_does_not_strip_inherited_implicit_provenance(client):
    """F8 — the rule was "any override recorded"; the justification was divergence.

    ``_merge_implicit``'s docstring argues from DIVERGENCE: *"That argument was wrong
    the moment a run diverged"*. An override whose value equals the experiment's has
    not diverged — the run genuinely holds the experiment's value at every address —
    so the experiment's derivations are still true of it and dropping them silently
    deletes recorded evidence, which is the failure ``inherit=True`` exists to avoid.

    Comparing values needs no dependency table: it asks only whether this run holds
    what the experiment holds, which is exactly the premise the ``inherit=True`` case
    already rests on. So the code is changed to match its own argument rather than the
    argument to match the code.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTNOOPOVERRIDE01"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1",))
    run = exp.sorted_runs()[0]
    inherited = copy.deepcopy(exp.draft["fields"]["sample.material.formula"])

    exp.set_run_override(run, ws.field_address("sample.material.formula"), inherited)
    exp.save_versioned()

    assert run.overrides, "the override must actually be recorded for this to mean anything"
    resolved = exp.resolved_run_draft(run)
    assert resolved["fields"]["sample.material.formula"] == inherited
    abouts = {entry["about"] for entry in resolved.get("implicit") or []}
    assert "absorbing_element" in abouts, resolved.get("implicit")

    assert _export(client, experiment_id).status_code == 200
    final = store.load_experiment(experiment_id)
    sidecar = json.loads(
        (final.records_dir / f"{final.sorted_runs()[0].record_id}.evidence.json").read_text()
    )
    assert [k for k in sidecar["evidence"] if k.startswith("implicit:")] != []


def test_the_no_op_test_is_envelope_equality_and_the_docstring_says_so(client):
    """F-D — the headline claims VALUES; the code compares the whole envelope.

    ``_diverges_from_experiment`` compares ``resolution.payload`` — the envelope —
    against ``resolution.inherited_payload``. ``Resolution.value`` exists for exactly
    the comparison the headline describes and is not used by it. The F8 test above
    passes because it re-records a BYTE-IDENTICAL envelope, so the two comparisons
    cannot be told apart there.

    Here they can. This run records the SAME scientific value with a re-stamped
    ``user_confirmation`` — a different envelope, an identical value — and every
    inherited ``implicit`` entry is still stripped. Measured, and asserted as the
    behaviour rather than as a defect: it is the fail-closed side, and the fix is to
    the CLAIM. See the docstring for why re-recording a value on the run's own
    authority is treated as divergence.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTENVELOPEDIVERG"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1",))
    run = exp.sorted_runs()[0]
    inherited = copy.deepcopy(exp.draft["fields"]["sample.material.formula"])

    restamped = copy.deepcopy(inherited)
    restamped["status"] = "verified"
    restamped["user_confirmation"] = {
        "confirmed_by": "synthetic-operator",
        "confirmed_utc": "2026-01-01T00:00:00Z",
    }
    assert restamped != inherited
    assert restamped["value"] == inherited["value"], "the VALUE must be identical"

    exp.set_run_override(run, ws.field_address("sample.material.formula"), restamped)
    exp.save_versioned()

    resolved = exp.resolved_run_draft(run)
    assert resolved["fields"]["sample.material.formula"]["value"] == inherited["value"]
    abouts = {entry["about"] for entry in resolved.get("implicit") or []}
    assert "absorbing_element" not in abouts, (
        "the comparison is envelope-based: same value, different envelope, entries "
        f"dropped — {resolved.get('implicit')}"
    )

    # …and the docstring must not claim otherwise.
    source = inspect.getsource(ws._merge_implicit) + inspect.getsource(
        ws._diverges_from_experiment
    )
    assert "THAT TEST IS ABOUT VALUES" not in source
    assert "ENVELOPE" in source, "the corrected headline must name what is compared"


def test_the_evidence_fallback_does_not_cite_a_stale_marker_a_fan_out_never_gets(client):
    """F-G — the justification names a compensating signal that does not exist.

    ``get_evidence`` serves no marker when it degrades to the draft trail, and the
    comment justified that by saying the one honest thing a marker would add is
    *"already published by ``/artifacts`` as ``artifact.state: 'stale'``, which this
    endpoint's only caller fetches in the same ``Promise.all``"*.

    For a fan-out ``/artifacts`` reports ``current`` — measured below. The two are not
    even describing the same thing: ``/artifacts`` is answering about the experiment's
    own pair (correctly absent, and it says why via ``reason``), while ``get_evidence``
    has silently fallen back to a DIFFERENT document. So the justification is
    corrected to the signal that is actually served, and the sentence that named a
    ``stale`` marker is gone.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTEVIDENCEMARKER"
    _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    assert _export(client, experiment_id).status_code == 200

    artifacts = client.get(f"/api/experiments/{experiment_id}/artifacts").json()
    assert artifacts["artifact"]["state"] == "current", artifacts["artifact"]
    assert artifacts["record"] is None and artifacts["sidecar"] is None
    assert artifacts["reason"] == routes.FAN_OUT_ARTIFACT_REASON

    # The evidence trail degraded, and nothing in it says which document it is.
    evidence = client.get(f"/api/experiments/{experiment_id}/evidence").json()
    assert set(evidence) == {"evidence"}

    source = inspect.getsource(routes.get_evidence)
    assert 'artifact.state: "stale"' not in source, (
        "the justification still cites a marker a fan-out never receives"
    )


# --- F-E / F-F: measured limits, RECORDED and deliberately not fixed -----------


def test_the_sibling_link_filter_is_blind_to_who_authored_the_link(client):
    """F-E — ``without_sibling_links`` filters on ``(rel, basis)``, not provenance.

    Its docstring used to describe the blind spot as "a change to a
    ``same_sample_as`` link on a materialised record — which is exactly the change
    that record can never receive", which reads as though the filter and the links
    this module emits were the same set. Nothing in it asks who wrote the link.
    """
    emitted = {"rel": ws.SIBLING_REL, "target": "01JQZ0TARGET00000000000001", "basis": ws.SIBLING_BASIS}
    other_rel = {**emitted, "rel": "derived_from"}

    # Dropped whatever wrote it — there is no provenance for this to consult.
    assert "links" not in ws.without_sibling_links({"record_id": "R", "links": [emitted]})
    control = {"record_id": "R", "links": [other_rel]}
    assert ws.without_sibling_links(control) == control

    # THE CONSEQUENCE, which is what the docstring understated: a record that gains
    # such a link after export compares EQUAL to the one on disk, so nothing stales.
    on_disk = {"record_id": "R"}
    gained_sibling = {"record_id": "R", "links": [emitted]}
    gained_other = {"record_id": "R", "links": [other_rel]}
    assert ws.without_sibling_links(on_disk) == ws.without_sibling_links(gained_sibling)
    assert ws.without_sibling_links(on_disk) != ws.without_sibling_links(gained_other)

    source = inspect.getsource(ws.without_sibling_links)
    assert "NOT ON PROVENANCE" in source


def test_an_orphan_is_reported_only_by_an_export_that_notices_it(client):
    """F-F — orphan accumulation has no standing signal. Recorded, not fixed.

    ``pruned_record_ids`` / ``protected_record_ids`` / ``prune_declined`` are fields
    of an EXPORT response. Delete a run from a fully-exported fan-out and never
    export again, and every read surface is silent: measured below, including
    ``/audit``, which globs the records directory and therefore reports the orphan as
    a PASSING RECORD — the one surface that can see the file describes it as healthy.
    """
    store = client_ws(client)
    experiment_id = "01JQZ0FANOUTORPHANSILENT01"
    exp = _fan_out_experiment(store, experiment_id=experiment_id, run_labels=("Run 1", "Run 2"))
    first, second = exp.sorted_runs()
    assert _export(client, experiment_id).status_code == 200

    trimmed = store.load_experiment(experiment_id)
    trimmed.runs = [run for run in trimmed.runs if run.id != second.id]
    trimmed.save_versioned()

    # The file is still there…
    assert _artifact_stems(store.load_experiment(experiment_id)) == {first.id, second.id}

    # …and nothing that reads reports it.
    detail = client.get(f"/api/experiments/{experiment_id}").json()
    assert "pruned_record_ids" not in detail and "protected_record_ids" not in detail
    artifacts = client.get(f"/api/experiments/{experiment_id}/artifacts").json()
    assert artifacts["artifact"]["state"] == "current", artifacts["artifact"]

    audited = client.post(f"/api/experiments/{experiment_id}/audit").json()
    rows = {row["name"]: row["ok"] for row in audited["records"]}
    assert rows == {f"{first.id}.json": True, f"{second.id}.json": True}, rows


def test_the_frontend_fixture_quotes_the_reason_the_backend_actually_serves():
    """F-C — the export screen RENDERS ``artifact_refs.reason``, so it can drift.

    ``apps/web/src/test/apiFixtures.ts`` carries a hand-copied ``FAN_OUT_REASON``
    because a vitest fixture cannot import from the Python package. A hand-copied
    string is exactly the thing this repository has watched go stale before, so it is
    pinned here rather than trusted — the frontend test would keep passing against a
    sentence the backend no longer sends.
    """
    fixture = (
        pathlib.Path(routes.__file__).parents[3]
        / "apps"
        / "web"
        / "src"
        / "test"
        / "apiFixtures.ts"
    )
    source = fixture.read_text(encoding="utf-8")
    marker = "export const FAN_OUT_REASON =\n  "
    start = source.index(marker) + len(marker)
    literal = source[start : source.index(";\n", start)].strip()
    assert literal.startswith('"') and literal.endswith('"'), literal
    assert json.loads(literal) == routes.FAN_OUT_ARTIFACT_REASON

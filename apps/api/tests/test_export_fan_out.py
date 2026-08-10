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
import json
import pathlib

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

    removed = routes._prune_orphan_artifacts(exp, {"01JQZ0KEEPTHISRECORDID0001"})
    assert removed == []
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

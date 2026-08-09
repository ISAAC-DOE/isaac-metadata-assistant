"""The Run domain model: shape, persistence, inheritance-by-reference, versioning.

Backend-only. Nothing here touches ``src/isaac_records/``, ``schema/``, export, a
route, a migration or a database — the model is exercised directly through
``workspace``.

The contract these tests pin is
``docs/superpowers/specs/2026-08-08-scientist-capture-data-contract.md``:

* §1 D1 — one Run produces exactly one ISAAC record, so a Run is a first-class
  object with its own draft, record identity and version;
* §2 D2 — inheritance is BY REFERENCE, NEVER BY COPY;
* §8 — ``from_state`` is legacy-tolerant, so adding runs needs no migration.
"""

from __future__ import annotations

import json

import pytest

from isaac_api import workspace as ws


@pytest.fixture()
def wsroot(tmp_path, monkeypatch):
    """A hermetic ordinary-scope workspace with no database configured."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.delenv("PGHOST", raising=False)
    return tmp_path


def _experiment(**kw) -> ws.Experiment:
    base = dict(
        id="01RUNDOMAINMODELTEST000001",
        title="Run model fixture",
        created_utc="2026-08-08T00:00:00Z",
        source={"description": "unit test", "files": []},
        draft={"fields": {}},
    )
    base.update(kw)
    return ws.Experiment(**base)


def _env(value, status: str = "verified") -> dict:
    """A draft field envelope in the shape ``blank_draft()``/the extractor produce."""
    return {"value": value, "status": status, "evidence": []}


# =============================================================================
# 1. legacy hydration — the proof that no migration is needed
# =============================================================================


def test_a_hand_written_legacy_document_still_hydrates_with_zero_runs():
    """A state document written BEFORE runs existed must hydrate unchanged.

    The dict below is written by hand rather than produced by ``to_state`` on
    purpose: a round-trip through the current writer could only ever prove the
    current writer agrees with itself. This is the pre-runs shape, and it also
    predates ``rev``/``updated_utc``/``generation``, so it exercises every
    legacy-tolerant default at once.
    """
    legacy = {
        "id": "01LEGACYNORUNSNOREVNOGEN00",
        "title": "Written by an older build",
        "created_utc": "2026-07-01T00:00:00Z",
        "source": {"description": "legacy", "files": []},
        "draft": {"fields": {"sample.material.name": _env("Copper(II) Oxide")}},
        "answer_log": [],
        "record_id": None,
    }
    assert "runs" not in legacy  # the point of the fixture

    exp = ws.Experiment.from_state(legacy)

    assert exp.runs == []
    assert exp.rev == 0
    assert exp.updated_utc == "2026-07-01T00:00:00Z"  # anchored to created_utc
    assert exp.generation == ws._legacy_generation(legacy["id"])
    # And it is immediately usable as a runs-carrying experiment.
    assert exp.next_ordinal() == 1
    assert exp.sorted_runs() == []


def test_adding_the_runs_key_does_not_bump_a_legacy_records_rev(wsroot):
    """The added signature key must not make every existing record look changed.

    ``_authoritative_signature`` now hashes ``runs``. Both sides of the comparison
    in ``save_versioned`` go through the same code, so a legacy document with no
    runs hashes with ``"runs": []`` on disk AND in memory. A re-save of unchanged
    legacy state must therefore still be a byte-stable no-op.
    """
    legacy = {
        "id": "01LEGACYNORUNSNOREVNOGEN00",
        "title": "Written by an older build",
        "created_utc": "2026-07-01T00:00:00Z",
        "source": {"description": "legacy", "files": []},
        "draft": {"fields": {}},
    }
    exp = ws.Experiment.from_state(legacy)
    exp.dir.mkdir(parents=True, exist_ok=True)
    # Write the LEGACY bytes to disk (not `to_state()` output), so the on-disk file
    # genuinely lacks the runs key.
    ws.atomic_write_text(exp.state_path, json.dumps(legacy, indent=2) + "\n")

    assert exp.save_versioned() is False
    assert exp.rev == 0
    assert json.loads(exp.state_path.read_text())["title"] == "Written by an older build"
    assert "runs" not in json.loads(exp.state_path.read_text())


# =============================================================================
# 2. shape and round-trip
# =============================================================================


def test_a_run_round_trips_through_state_with_every_field(wsroot):
    exp = _experiment()
    run = exp.add_run(label="Cold", draft={"fields": {"context.temperature_K": _env(77)}})
    run.record_id = "01EXPORTEDRECORDIDFORRUN01"
    exp.save()

    reloaded = ws.load_experiment(exp.id)
    assert reloaded is not None
    assert len(reloaded.runs) == 1
    got = reloaded.runs[0]

    assert got.id == run.id
    assert got.experiment_id == exp.id
    assert got.label == "Cold"
    assert got.ordinal == 1
    assert got.created_utc == run.created_utc
    assert got.draft == {"fields": {"context.temperature_K": _env(77)}}
    assert got.record_id == "01EXPORTEDRECORDIDFORRUN01"
    assert got.rev == run.rev
    assert got.updated_utc == run.updated_utc
    assert got.generation == run.generation
    assert got.version_token() == run.version_token()


def test_a_run_id_is_a_fresh_ulid_and_is_not_the_record_id():
    exp = _experiment()
    a = exp.add_run()
    b = exp.add_run()
    from isaac_records.ids import is_record_id

    assert is_record_id(a.id) and is_record_id(b.id)
    assert a.id != b.id
    # Minting a run asserts nothing about it having been exported.
    assert a.record_id is None and b.record_id is None


def test_the_experiment_state_document_carries_its_runs(wsroot):
    exp = _experiment()
    exp.add_run(label="A")
    exp.add_run(label="B")
    exp.save()

    state = json.loads(exp.state_path.read_text())
    assert [r["label"] for r in state["runs"]] == ["A", "B"]
    assert [r["ordinal"] for r in state["runs"]] == [1, 2]
    assert all(r["experiment_id"] == exp.id for r in state["runs"])


def test_a_run_carries_no_session_id(wsroot):
    """Scope is a property of the owning experiment, not of a run."""
    exp = _experiment(session_id=None)
    run = exp.add_run()
    assert "session_id" not in run.to_state()


# =============================================================================
# 3. ordering — explicit ordinal, never the label
# =============================================================================


def test_run_order_follows_the_ordinal_and_not_the_label():
    """The label must not determine order: 'Run 10' sorts before 'Run 2' lexically."""
    exp = _experiment()
    first = exp.add_run(label="Run 10")
    second = exp.add_run(label="Run 2")
    third = exp.add_run(label="aaa")

    assert [r.ordinal for r in (first, second, third)] == [1, 2, 3]
    assert [r.id for r in exp.sorted_runs()] == [first.id, second.id, third.id]

    # Renaming does not move a run.
    first.label = "zzzz last alphabetically"
    third.label = "AAA first alphabetically"
    assert [r.id for r in exp.sorted_runs()] == [first.id, second.id, third.id]


def test_sorted_runs_is_independent_of_list_position():
    exp = _experiment()
    a = exp.add_run()
    b = exp.add_run()
    exp.runs.reverse()
    assert [r.id for r in exp.sorted_runs()] == [a.id, b.id]


def test_ties_on_ordinal_still_produce_a_total_order():
    """A total order for ANY input, not only well-formed input — the authoritative
    signature depends on it being deterministic."""
    exp = _experiment()
    a = ws.new_run(exp.id, ordinal=1, created_utc="2026-08-08T00:00:00Z", id="01AAAA" + "A" * 20)
    b = ws.new_run(exp.id, ordinal=1, created_utc="2026-08-08T00:00:00Z", id="01BBBB" + "B" * 20)
    exp.runs = [b, a]
    assert [r.id for r in exp.sorted_runs()] == [a.id, b.id]


def test_next_ordinal_is_max_plus_one_not_length_plus_one():
    exp = _experiment()
    exp.add_run()
    second = exp.add_run()
    third = exp.add_run()
    exp.runs.remove(second)
    # len-based numbering would re-issue 3, which `third` already holds.
    assert exp.next_ordinal() == 4
    assert third.ordinal == 3


# =============================================================================
# 4. the experiment/run field split (contract §2)
# =============================================================================


@pytest.mark.parametrize(
    "path",
    [
        "sample.material.name",
        "sample.sample_form",
        "sample.composition.CuO2_mass_fraction",
        "system.domain",
        "system.technique",
        "system.facility.beamline",
        "system.instrument.model",
    ],
)
def test_contract_experiment_level_field_paths_classify_as_experiment_level(path):
    assert ws.field_level(path) == ws.LEVEL_EXPERIMENT


@pytest.mark.parametrize(
    "path",
    [
        "context.environment",
        "context.temperature_K",
        "context.electrochemistry.control_mode",
        "timestamps.acquired_start_utc",
        "timestamps.acquired_end_utc",
    ],
)
def test_contract_run_level_field_paths_classify_as_run_level(path):
    assert ws.field_level(path) == ws.LEVEL_RUN


@pytest.mark.parametrize(
    "path",
    [
        "system.configuration.detector_model",
        "system.configuration.n_scans",
        "timestamps.created_utc",
    ],
)
def test_paths_in_neither_contract_list_are_reported_unclassified_not_guessed(path):
    """These are emitted by the real extractor and are in NEITHER contract list.

    Assigning them a level would be an unevidenced scientific inference (may two
    runs of one experiment differ in detector model?), which ``CLAUDE.md`` §5
    forbids. Unclassified is the honest answer, and it is a tested answer rather
    than an accident.
    """
    assert ws.field_level(path) == ws.LEVEL_UNCLASSIFIED


def test_classification_is_segment_aware():
    assert ws.field_level("system.domain") == ws.LEVEL_EXPERIMENT
    assert ws.field_level("system.domainish") == ws.LEVEL_UNCLASSIFIED


# --- the draft has TWO namespaces, and 7 of the contract's 14 entries are blocks ---


@pytest.mark.parametrize("key", ["attribution", "tags"])
def test_contract_experiment_level_blocks_classify_as_experiment_level(key):
    assert ws.block_level(key) == ws.LEVEL_EXPERIMENT


@pytest.mark.parametrize("key", ["series", "qc", "assets", "descriptors_outputs"])
def test_contract_run_level_blocks_classify_as_run_level(key):
    assert ws.block_level(key) == ws.LEVEL_RUN


@pytest.mark.parametrize(
    "schema_path,block_key",
    [
        ("measurement.series", "series"),
        ("measurement.qc", "qc"),
        ("assets", "assets"),
        ("descriptors.outputs", "descriptors_outputs"),
        ("attribution.contributors", "attribution"),
        ("tags", "tags"),
    ],
)
def test_the_seven_schema_space_entries_are_blocks_and_never_field_keys(schema_path, block_key):
    """THE BUG THIS FILE ONCE ENCODED, pinned so it cannot come back.

    Contract §2 was written in official SCHEMA-PATH space and the first version of
    this module applied it to DRAFT FIELD KEYS. Six of the seven entries below (plus
    ``system.instrument``, which is a legitimate field path the extractor merely
    never emits) do not exist in the field map at all — a draft carries them as
    top-level blocks with different names. So the schema-space spelling classifies
    as unclassified in field space, and the block spelling is where the data is.
    """
    assert ws.field_level(schema_path) == ws.LEVEL_UNCLASSIFIED
    assert ws.block_level(block_key) != ws.LEVEL_UNCLASSIFIED


@pytest.mark.parametrize("key", ["meta", "pending", "implicit", "links", "block_evidence"])
def test_draft_only_and_undecided_blocks_are_unclassified(key):
    assert ws.block_level(key) == ws.LEVEL_UNCLASSIFIED


def test_block_classification_is_exact_not_a_prefix_test():
    assert ws.block_level("tags") == ws.LEVEL_EXPERIMENT
    assert ws.block_level("tags.extra") == ws.LEVEL_UNCLASSIFIED


def test_the_field_and_block_namespaces_are_addressed_explicitly():
    """``tags`` is both a top-level draft block and a legal official schema path, so
    a bare name would be ambiguous. The address prefix removes the ambiguity."""
    assert ws.field_address("tags") != ws.block_address("tags")
    assert ws.parse_address(ws.field_address("sample.material.name")) == (
        ws.ADDRESS_FIELD,
        "sample.material.name",
    )
    assert ws.parse_address(ws.block_address("tags")) == (ws.ADDRESS_BLOCK, "tags")
    assert ws.address_level(ws.block_address("tags")) == ws.LEVEL_EXPERIMENT
    assert ws.address_level(ws.field_address("tags")) == ws.LEVEL_UNCLASSIFIED


@pytest.mark.parametrize("bad", ["", "tags", "field:", ":tags", "nonsense:tags"])
def test_a_malformed_address_is_refused(bad):
    with pytest.raises(ValueError):
        ws.parse_address(bad)


def test_every_field_map_path_the_real_extractor_emits_is_classified_or_knowingly_not():
    """Run the DETERMINISTIC EXTRACTOR and classify what it actually produces.

    A hand-written parametrize list can only test the paths its author thought of.
    This asserts against the real committed fixtures, so a future FIELD_MAP entry
    that nobody classified shows up here rather than silently defaulting.
    """
    from isaac_records.extract.draft_builder import build_draft

    draft = build_draft(ws.CSV_PATH, ws.LISTING_PATH)
    levels = {p: ws.field_level(p) for p in draft["fields"]}
    unclassified = sorted(p for p, lvl in levels.items() if lvl == ws.LEVEL_UNCLASSIFIED)

    # Exactly the two families the docstring names, and nothing else.
    assert unclassified == [
        "system.configuration.detector_model",
        "system.configuration.monochromator_crystal",
        "system.configuration.n_scans",
        "system.configuration.proposal_id",
        "system.configuration.session_id",
        "system.configuration.spectrometer_geometry",
        "timestamps.created_utc",
    ]
    assert levels["context.temperature_K"] == ws.LEVEL_RUN
    assert levels["sample.material.name"] == ws.LEVEL_EXPERIMENT


def test_the_real_extractors_top_level_blocks_are_classified():
    """The draft blocks a real extraction produces, classified in block space."""
    from isaac_records.extract.draft_builder import build_draft

    draft = build_draft(ws.CSV_PATH, ws.LISTING_PATH)
    blocks = {k: ws.block_level(k) for k in draft if k != "fields"}

    assert blocks["attribution"] == ws.LEVEL_EXPERIMENT
    assert blocks["assets"] == ws.LEVEL_RUN
    assert blocks["qc"] == ws.LEVEL_RUN
    # Draft-only bookkeeping stays out of the inheritance model entirely.
    assert blocks["meta"] == ws.LEVEL_UNCLASSIFIED
    assert blocks["pending"] == ws.LEVEL_UNCLASSIFIED
    assert blocks["implicit"] == ws.LEVEL_UNCLASSIFIED


# =============================================================================
# 5. inheritance BY REFERENCE (contract §2 D2)
# =============================================================================


def test_an_experiment_level_field_is_inherited_without_being_copied(wsroot):
    exp = _experiment(draft={"fields": {"sample.material.name": _env("Copper(II) Oxide")}})
    run = exp.add_run()

    resolved = exp.resolve_run(run)
    assert resolved[ws.field_address("sample.material.name")].provenance == ws.PROVENANCE_INHERITED
    assert resolved[ws.field_address("sample.material.name")].value == "Copper(II) Oxide"

    # THE RUN STORES NOTHING. Not in its draft, not in its overrides, not on disk.
    assert run.draft == {}
    assert run.overrides == {}
    exp.save()
    assert "Copper(II) Oxide" not in json.dumps(json.loads(exp.state_path.read_text())["runs"])


def test_editing_the_experiment_value_flows_through_to_a_non_overriding_run():
    """The property that inheritance-by-copy would lose."""
    exp = _experiment(draft={"fields": {"sample.material.name": _env("Copper(II) Oxide")}})
    run = exp.add_run()
    assert exp.resolve_run(run)[ws.field_address("sample.material.name")].value == "Copper(II) Oxide"

    exp.draft["fields"]["sample.material.name"] = _env("Copper(I) Oxide")

    assert exp.resolve_run(run)[ws.field_address("sample.material.name")].value == "Copper(I) Oxide"


def test_an_override_records_the_inherited_value_it_displaced():
    exp = _experiment(draft={"fields": {"sample.sample_form": _env("pellet")}})
    run = exp.add_run()

    exp.set_run_override(run, ws.field_address("sample.sample_form"), _env("powder"))

    r = exp.resolve_run(run)[ws.field_address("sample.sample_form")]
    assert r.provenance == ws.PROVENANCE_OVERRIDDEN
    assert r.value == "powder"
    assert r.inherited_payload == _env("pellet")
    assert r.displaced_payload == _env("pellet")


def test_the_displaced_value_is_historical_and_the_inherited_value_is_live():
    """These two legitimately diverge, and the divergence is the point.

    ``displaced_payload`` is what the override displaced WHEN IT WAS RECORDED and
    is never refreshed; ``inherited_payload`` is what the experiment says now.
    """
    exp = _experiment(draft={"fields": {"sample.sample_form": _env("pellet")}})
    run = exp.add_run()
    exp.set_run_override(run, ws.field_address("sample.sample_form"), _env("powder"))

    exp.draft["fields"]["sample.sample_form"] = _env("thin film")

    r = exp.resolve_run(run)[ws.field_address("sample.sample_form")]
    assert r.displaced_payload == _env("pellet")  # history, unchanged
    assert r.inherited_payload == _env("thin film")  # live
    assert r.value == "powder"  # the override still wins


def test_an_override_of_a_path_the_experiment_does_not_carry_displaces_nothing():
    exp = _experiment(draft={"fields": {}})
    run = exp.add_run()
    exp.set_run_override(run, ws.field_address("sample.sample_form"), _env("powder"))

    r = exp.resolve_run(run)[ws.field_address("sample.sample_form")]
    assert r.inherited_payload is None
    assert r.displaced_payload is None
    # Absence is the encoding on disk, so "displaced nothing" stays distinguishable
    # from "displaced an explicit null".
    assert "displaced" not in run.overrides[ws.field_address("sample.sample_form")].to_state()


def test_clearing_an_override_restores_inheritance_by_reference():
    exp = _experiment(draft={"fields": {"sample.sample_form": _env("pellet")}})
    run = exp.add_run()
    exp.set_run_override(run, ws.field_address("sample.sample_form"), _env("powder"))

    assert exp.clear_run_override(run, ws.field_address("sample.sample_form")) is True
    assert exp.clear_run_override(run, ws.field_address("sample.sample_form")) is False

    r = exp.resolve_run(run)[ws.field_address("sample.sample_form")]
    assert r.provenance == ws.PROVENANCE_INHERITED
    assert r.value == "pellet"
    assert run.overrides == {}  # no copy left behind


def test_a_run_level_field_cannot_be_overridden():
    exp = _experiment()
    run = exp.add_run()
    with pytest.raises(ws.NotOverridable):
        exp.set_run_override(run, ws.field_address("context.temperature_K"), _env(77))
    with pytest.raises(ws.NotOverridable):
        exp.set_run_override(run, ws.field_address("system.configuration.n_scans"), _env(6))
    with pytest.raises(ws.NotOverridable):
        exp.set_run_override(run, ws.block_address("qc"), {"status": "valid"})
    assert run.overrides == {}


def test_resolution_only_reports_experiment_level_fields():
    exp = _experiment(
        draft={
            "fields": {
                "sample.material.name": _env("Copper(II) Oxide"),
                "context.temperature_K": _env(298),
                "system.configuration.n_scans": _env(6),
            }
        }
    )
    run = exp.add_run()
    assert set(exp.resolve_run(run)) == {ws.field_address("sample.material.name")}


def test_overrides_survive_a_round_trip(wsroot):
    exp = _experiment(draft={"fields": {"sample.sample_form": _env("pellet")}})
    run = exp.add_run()
    exp.set_run_override(run, ws.field_address("sample.sample_form"), _env("powder"))
    exp.save()

    reloaded = ws.load_experiment(exp.id)
    r = reloaded.resolve_run(reloaded.runs[0])[ws.field_address("sample.sample_form")]
    assert r.provenance == ws.PROVENANCE_OVERRIDDEN
    assert r.value == "powder"
    assert r.displaced_payload == _env("pellet")


# --- experiment-level BLOCKS inherit too (the gap the schema-space lists left) ---


def test_the_attribution_block_is_inherited_by_reference():
    """``attribution.contributors`` is contract §2 experiment-level, and a draft
    keeps it in a top-level block. Before the draft-space fix this inherited
    NOTHING — the resolution key set was empty for it."""
    contributors = {"contributors": [{"name": "Ada Lovelace", "role": "curated_record"}]}
    exp = _experiment(draft={"fields": {}, "attribution": contributors})
    run = exp.add_run()

    r = exp.resolve_run(run)[ws.block_address("attribution")]
    assert r.provenance == ws.PROVENANCE_INHERITED
    assert r.value == contributors
    assert run.overrides == {}  # nothing copied down

    exp.draft["attribution"] = {"contributors": [{"name": "Grace Hopper", "role": "curated_record"}]}
    assert exp.resolve_run(run)[ws.block_address("attribution")].value["contributors"][0][
        "name"
    ] == "Grace Hopper"


def test_the_tags_block_is_inherited_and_overridable():
    exp = _experiment(draft={"fields": {}, "tags": ["campaign-a"]})
    run = exp.add_run()
    assert exp.resolve_run(run)[ws.block_address("tags")].value == ["campaign-a"]

    exp.set_run_override(run, ws.block_address("tags"), ["campaign-a", "rerun"])

    r = exp.resolve_run(run)[ws.block_address("tags")]
    assert r.provenance == ws.PROVENANCE_OVERRIDDEN
    assert r.value == ["campaign-a", "rerun"]
    assert r.displaced_payload == ["campaign-a"]


def test_run_level_blocks_are_not_inherited():
    exp = _experiment(draft={"fields": {}, "qc": {"status": "valid"}, "series": [1, 2]})
    run = exp.add_run()
    assert set(exp.resolve_run(run)) == set()


def test_a_block_override_round_trips(wsroot):
    exp = _experiment(draft={"fields": {}, "tags": ["campaign-a"]})
    run = exp.add_run()
    exp.set_run_override(run, ws.block_address("tags"), ["rerun"])
    exp.save()

    reloaded = ws.load_experiment(exp.id)
    r = reloaded.resolve_run(reloaded.runs[0])[ws.block_address("tags")]
    assert r.value == ["rerun"]
    assert r.displaced_payload == ["campaign-a"]


def test_the_displaced_payload_is_deep_copied_at_capture():
    """The promise in ``Override``'s docstring — history is never refreshed — made
    true by construction rather than by how callers happen to write.

    An IN-PLACE edit of the experiment's own draft (rather than the wholesale
    replacement both current write paths use) must not rewrite the displaced record
    through a shared reference.
    """
    exp = _experiment(draft={"fields": {"sample.sample_form": _env("pellet")}})
    run = exp.add_run()
    exp.set_run_override(run, ws.field_address("sample.sample_form"), _env("powder"))

    exp.draft["fields"]["sample.sample_form"]["value"] = "MUTATED IN PLACE"

    r = exp.resolve_run(run)[ws.field_address("sample.sample_form")]
    assert r.displaced_payload["value"] == "pellet"  # history intact
    assert r.inherited_payload["value"] == "MUTATED IN PLACE"  # live view moved


# =============================================================================
# 6. versioning
# =============================================================================


def test_runs_are_inside_the_authoritative_signature():
    a = _experiment()
    b = _experiment()
    assert ws._authoritative_signature(a) == ws._authoritative_signature(b)
    b.add_run(id="01RUNIDFORSIGNATURETEST001", created_utc="2026-08-08T00:00:00Z")
    assert ws._authoritative_signature(a) != ws._authoritative_signature(b)


def test_the_signature_excludes_run_version_metadata():
    """Otherwise the bump this save is about to write would feed back into the
    decision about whether to write at all."""
    exp = _experiment()
    run = exp.add_run(id="01RUNIDFORSIGNATURETEST002", created_utc="2026-08-08T00:00:00Z")
    before = ws._authoritative_signature(exp)

    run.rev = 41
    run.updated_utc = "2030-01-01T00:00:00Z"
    run.generation = "deadbeefdeadbeef"

    assert ws._authoritative_signature(exp) == before


def test_the_signature_is_insensitive_to_in_memory_run_list_order():
    exp = _experiment()
    exp.add_run(id="01RUNIDFORSIGNATURETEST003", created_utc="2026-08-08T00:00:00Z")
    exp.add_run(id="01RUNIDFORSIGNATURETEST004", created_utc="2026-08-08T00:00:01Z")
    before = ws._authoritative_signature(exp)
    exp.runs.reverse()
    assert ws._authoritative_signature(exp) == before


def test_adding_a_run_bumps_the_experiment_rev(wsroot):
    exp = _experiment()
    assert exp.save_versioned() is True
    assert exp.rev == 1

    exp.add_run(label="Cold")
    assert exp.save_versioned() is True
    assert exp.rev == 2


def test_a_byte_stable_no_op_with_runs_never_bumps_anything(wsroot):
    exp = _experiment()
    run = exp.add_run()
    exp.save_versioned()
    exp_rev, run_rev, run_updated = exp.rev, run.rev, run.updated_utc

    assert exp.save_versioned() is False
    assert (exp.rev, run.rev, run.updated_utc) == (exp_rev, run_rev, run_updated)


def test_editing_one_run_bumps_that_run_only(wsroot):
    exp = _experiment()
    first = exp.add_run(label="Cold")
    second = exp.add_run(label="Hot")
    exp.save_versioned()
    assert (first.rev, second.rev) == (1, 1)

    first.draft = {"fields": {"context.temperature_K": _env(77)}}
    assert exp.save_versioned() is True

    assert first.rev == 2
    assert second.rev == 1  # untouched


def test_an_experiment_only_edit_does_not_disturb_a_run_version(wsroot):
    exp = _experiment()
    run = exp.add_run()
    exp.save_versioned()
    run_rev, run_updated = run.rev, run.updated_utc

    exp.title = "Renamed"
    assert exp.save_versioned() is True

    assert exp.rev == 2
    assert (run.rev, run.updated_utc) == (run_rev, run_updated)


def test_a_rejected_no_op_does_not_advance_a_run_version(wsroot):
    """The no-op decision is made BEFORE any run version is touched."""
    exp = _experiment()
    run = exp.add_run()
    exp.save_versioned()
    snapshot = (run.rev, run.updated_utc)

    for _ in range(3):
        assert exp.save_versioned() is False
    assert (run.rev, run.updated_utc) == snapshot


def test_an_override_bumps_the_run_and_is_idempotent(wsroot):
    exp = _experiment(draft={"fields": {"sample.sample_form": _env("pellet")}})
    run = exp.add_run()
    exp.save_versioned()
    base_rev = run.rev

    exp.set_run_override(run, ws.field_address("sample.sample_form"), _env("powder"))
    assert exp.save_versioned() is True
    assert run.rev == base_rev + 1
    recorded = run.overrides[ws.field_address("sample.sample_form")].recorded_utc

    # Re-applying an equal envelope must not restamp, so it must not churn a version.
    exp.set_run_override(run, ws.field_address("sample.sample_form"), _env("powder"))
    assert run.overrides[ws.field_address("sample.sample_form")].recorded_utc == recorded
    assert exp.save_versioned() is False
    assert run.rev == base_rev + 1


def test_a_stale_in_memory_run_cannot_regress_the_persisted_rev(wsroot):
    exp = _experiment()
    run = exp.add_run(id="01RUNIDFORREGRESSIONTEST01", created_utc="2026-08-08T00:00:00Z")
    exp.save_versioned()

    # Another writer advanced this run on disk.
    on_disk = json.loads(exp.state_path.read_text())
    on_disk["runs"][0]["rev"] = 9
    ws.atomic_write_text(exp.state_path, json.dumps(on_disk, indent=2) + "\n")

    run.label = "renamed, so the signature changes"
    assert exp.save_versioned() is True
    assert run.rev == 10


def test_deleting_a_run_bumps_the_experiment(wsroot):
    exp = _experiment()
    run = exp.add_run()
    exp.save_versioned()
    exp.runs.remove(run)
    assert exp.save_versioned() is True
    assert ws.load_experiment(exp.id).runs == []


# =============================================================================
# 6b. a malformed run entry must never take down a read
# =============================================================================


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    return TestClient(create_app())


def _write_runs(exp: ws.Experiment, runs: list) -> None:
    """Put a raw ``runs`` array on disk, bypassing ``to_state``."""
    state = json.loads(exp.state_path.read_text())
    state["runs"] = runs
    ws.atomic_write_text(exp.state_path, json.dumps(state, indent=2) + "\n")


@pytest.mark.parametrize(
    "malformed",
    [
        {"experiment_id": "x", "label": "no id"},  # the measured 500
        {"id": "01GOODRUNIDBUTNOEXPERIMENT", "label": "no experiment_id"},
        {"id": "01BADORDINALRUNIDAAAAAAAAA", "ordinal": "seven"},
        {"id": "01BADREVRUNIDAAAAAAAAAAAAA", "rev": []},
        "not even an object",
        None,
    ],
)
def test_one_malformed_run_entry_does_not_500_the_read_path(api, malformed):
    """Measured against the REAL HTTP surface, not just the dataclass.

    ``Run.from_state`` used to hard-subscript ``id``/``experiment_id`` while every
    other key used ``.get``. ``Experiment.from_state`` hydrates runs in an unguarded
    comprehension and ``list_experiments`` catches only ``FileNotFoundError``, so one
    bad entry returned 500 for the single record AND for the entire workspace list.
    """
    created = api.post("/api/experiments", json={"title": "Has a bad run"})
    assert created.status_code in (200, 201), created.text
    exp_id = created.json()["id"]

    exp = ws.load_experiment(exp_id)
    _write_runs(exp, [malformed])

    listing = api.get("/api/experiments")
    assert listing.status_code == 200, listing.text
    assert [e["id"] for e in listing.json()["experiments"]] == [exp_id]

    detail = api.get(f"/api/experiments/{exp_id}")
    assert detail.status_code == 200, detail.text


def test_a_good_run_beside_a_malformed_one_survives(api):
    created = api.post("/api/experiments", json={"title": "Mixed"})
    exp_id = created.json()["id"]
    exp = ws.load_experiment(exp_id)
    good = ws.new_run(exp_id, ordinal=1, label="Keep me", id="01SURVIVINGRUNIDAAAAAAAAAA")
    _write_runs(exp, [{"label": "drop me, no id"}, good.to_state()])

    assert api.get("/api/experiments").status_code == 200
    reloaded = ws.load_experiment(exp_id)
    assert [r.id for r in reloaded.runs] == ["01SURVIVINGRUNIDAAAAAAAAAA"]


def test_run_from_state_never_raises_on_garbage():
    for garbage in ({}, {"id": None}, {"ordinal": {}}, {"overrides": "nope"}):
        assert isinstance(ws.Run.from_state(garbage), ws.Run)


# =============================================================================
# 6c. run ids are unique, which is what makes the order total
# =============================================================================


def test_a_duplicate_run_id_is_dropped_on_hydration(wsroot):
    """Uniqueness is ENFORCED, not assumed — it is what makes ``sorted_runs`` total
    and keeps ``_persisted_run_state`` from collapsing two runs onto one key."""
    exp = _experiment()
    exp.save()
    dup = {"id": "01DUPLICATERUNIDAAAAAAAAAA", "experiment_id": exp.id, "ordinal": 1}
    _write_runs(exp, [dict(dup, label="first"), dict(dup, label="second")])

    reloaded = ws.load_experiment(exp.id)
    assert len(reloaded.runs) == 1
    assert reloaded.runs[0].label == "first"  # first occurrence wins


def test_add_run_refuses_a_duplicate_id():
    exp = _experiment()
    exp.add_run(id="01EXPLICITRUNIDAAAAAAAAAAA")
    with pytest.raises(ValueError):
        exp.add_run(id="01EXPLICITRUNIDAAAAAAAAAAA")


def test_unique_ids_make_the_signature_order_independent():
    """The property the old ``sorted_runs`` docstring claimed on the wrong grounds.

    Two runs sharing ordinal AND created_utc still sort deterministically, because
    the id breaks the tie and ids are unique.
    """
    exp = _experiment()
    exp.runs = [
        ws.new_run(exp.id, ordinal=1, created_utc="2026-08-08T00:00:00Z", id="01A" + "A" * 23),
        ws.new_run(exp.id, ordinal=1, created_utc="2026-08-08T00:00:00Z", id="01B" + "B" * 23),
    ]
    before = ws._authoritative_signature(exp)
    exp.runs.reverse()
    assert ws._authoritative_signature(exp) == before
    assert [r.id for r in exp.sorted_runs()] == ["01A" + "A" * 23, "01B" + "B" * 23]


# =============================================================================
# 7. no arbitrary run limit (brief §5)
# =============================================================================


def test_no_run_limit_is_imposed(wsroot):
    """A product-level maximum is forbidden and no defensive cap is added either —
    see the ``Experiment.runs`` field comment for why no number here would be
    honest. This asserts the absence of a cap; it is not a performance test."""
    exp = _experiment()
    for _ in range(250):
        exp.add_run()
    exp.save()

    reloaded = ws.load_experiment(exp.id)
    assert len(reloaded.runs) == 250
    assert [r.ordinal for r in reloaded.sorted_runs()] == list(range(1, 251))


# =============================================================================
# 8. tutorial isolation must not weaken
# =============================================================================


def test_a_worked_example_sessions_runs_are_never_persistable(wsroot):
    """The extended document changes nothing about the three isolation guards.

    A run is carried BY its experiment, and the experiment is the persistence
    unit — so a run of a worked-example session is unpersistable for exactly the
    reason its experiment is.
    """
    from isaac_api.experiment_repository import NotPersistable, PostgresOrdinaryStore

    exp = _experiment(session_id="s" * 22)
    exp.add_run(label="Cold")

    with pytest.raises(NotPersistable):
        PostgresOrdinaryStore.refuse_if_not_persistable(exp)


def test_a_canonical_example_id_with_runs_is_never_persistable(wsroot):
    from isaac_api.experiment_repository import NotPersistable, PostgresOrdinaryStore

    exp = _experiment(id=ws.SEED_DONE_ID, session_id=None)
    exp.add_run()

    with pytest.raises(NotPersistable):
        PostgresOrdinaryStore.refuse_if_not_persistable(exp)


def test_the_ordinary_store_seam_still_refuses_a_session_scope(wsroot):
    """``_ordinary_store`` returns None for any session, before anything else is
    consulted — unchanged, and re-pinned because runs now ride inside the document
    it would have written."""
    exp = _experiment(session_id="s" * 22)
    exp.add_run()
    assert ws._ordinary_store(exp.session_id) is None


def test_a_sessions_runs_stay_inside_the_session_directory(wsroot):
    exp = _experiment(session_id="s" * 22)
    exp.add_run(label="Cold")
    exp.save()

    assert exp.state_path.is_relative_to(ws.tutorial_namespace_root())
    # Not visible from the ordinary scope.
    assert ws.load_experiment(exp.id) is None
    assert ws.load_experiment(exp.id, exp.session_id) is not None
    assert len(ws.load_experiment(exp.id, exp.session_id).runs) == 1

"""Tests for the ``SanitizedSnapshotSource`` memory provider + the ``status()``
freshness seam + ``get_default_reader`` provider selection (P24.9-impl-2).

``SanitizedSnapshotSource`` is the hosted-image analogue of
``LocalGraphArtifactSource``: it reads a pre-generated, sanitized
``memory-snapshot.json`` (see ``scripts/build_memory_snapshot.py``) instead of the
live Graphify artifacts, and MUST return byte-identical shapes to the local reader
so the ``/api/memory/*`` routes need zero change. These tests pin:

* **Parity** against the golden fixture snapshot + its source fixture graph.
* **Honest degradation** (reused ``graph_absent`` / ``graph_unreadable`` reasons).
* The additive **``status()``** freshness seam on BOTH providers.
* **``get_default_reader()``** 5-step precedence + memoization.

The fixtures live at ``tests/fixtures/memory_snapshot/`` — the golden snapshot was
generated from ``tests/fixtures/memory_snapshot/graph/`` by impl-1, so parity holds
modulo the documented differences (``graph_mtime`` null-vs-float, ``on_disk``
uniformly false, and generator-side rationale truncation).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isaac_api import memory
from isaac_api.memory import LocalGraphArtifactSource, SanitizedSnapshotSource

# --- fixture locations --------------------------------------------------------

FORBIDDEN_VERDICT_KEYS = {"ok", "valid", "passed", "verdict", "schema", "errors"}
#: Mirrors the generator's MAX_RATIONALE_CHARS; the snapshot truncates rationales,
#: the live reader does not — the one documented file-detail parity difference.
MAX_RATIONALE_CHARS = 280


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    return here.parents[3]


_FIXTURE_ROOT = _repo_root() / "tests" / "fixtures" / "memory_snapshot"
_GOLDEN_SNAPSHOT = _FIXTURE_ROOT / "memory-snapshot.json"
_FIXTURE_GRAPH_DIR = _FIXTURE_ROOT / "graph"
_SNAPSHOT_COMMIT = "fakecommitp24900"
_SNAPSHOT_SHA256 = "86c25c586b3f9c104b087ba1be3db5486347cb81486b6c57a5085fc9a5dbc0d6"


# --- helpers ------------------------------------------------------------------


def _force_on_disk_false(obj):
    """Deep copy with every ``on_disk`` value forced ``False`` (the snapshot bakes
    it false; the live reader over a fixture whose files are absent also yields
    false, so this normalizes the documented difference either way)."""
    if isinstance(obj, dict):
        return {k: (False if k == "on_disk" else _force_on_disk_false(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_force_on_disk_false(v) for v in obj]
    return obj


def _drop_rationales(detail: dict) -> dict:
    """A file-detail copy (on_disk normalized) with ``rationales`` removed, so
    file() parity can be asserted independent of generator-side truncation."""
    d = _force_on_disk_false(detail)
    d.pop("rationales", None)
    return d


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


def _write_snapshot(path: Path, data) -> Path:
    text = data if isinstance(data, str) else json.dumps(data)
    path.write_text(text, encoding="utf-8")
    return path


def _golden_dict() -> dict:
    return json.loads(_GOLDEN_SNAPSHOT.read_text(encoding="utf-8"))


@pytest.fixture()
def snap():
    return SanitizedSnapshotSource(_GOLDEN_SNAPSHOT)


@pytest.fixture()
def local():
    return LocalGraphArtifactSource(_FIXTURE_GRAPH_DIR)


# --- 1. parity ----------------------------------------------------------------


def test_parity_overview(snap, local):
    so, lo = snap.overview(), local.overview()
    assert so["available"] is True
    assert lo["available"] is True
    # Documented difference #1: graph_mtime is null in the snapshot, a float live.
    assert so["graph_mtime"] is None
    assert isinstance(lo["graph_mtime"], float)
    so2, lo2 = dict(so), dict(lo)
    so2.pop("graph_mtime")
    lo2.pop("graph_mtime")
    assert so2 == lo2


def test_parity_concepts(snap, local):
    assert snap.concepts() == _force_on_disk_false(local.concepts())


def test_parity_concept_detail_each_id(snap, local):
    for summary in snap.concepts():
        cid = summary["id"]
        assert snap.concept(cid) == _force_on_disk_false(local.concept(cid))


def test_parity_files(snap, local):
    assert snap.files() == _force_on_disk_false(local.files())


def test_parity_file_detail_each_path_modulo_rationales(snap, local):
    for summary in snap.files():
        path = summary["path"]
        assert _drop_rationales(snap.file(path)) == _drop_rationales(local.file(path))


def test_file_detail_rationale_truncation_is_the_documented_difference(snap, local):
    # Documented difference #3: the generator truncates rationales at
    # MAX_RATIONALE_CHARS; the live reader returns the full label. The widget file
    # carries a deliberately >280-char rationale to exercise this.
    snap_rats = snap.file("src/fake_widget.py")["rationales"]
    local_rats = local.file("src/fake_widget.py")["rationales"]
    assert len(snap_rats) == len(local_rats) == 2
    assert snap_rats[0] == local_rats[0]  # short rationale identical
    long_snap, long_local = snap_rats[1], local_rats[1]
    assert len(long_local) > MAX_RATIONALE_CHARS  # live reader keeps full text
    assert len(long_snap) == MAX_RATIONALE_CHARS  # snapshot truncated
    assert long_snap.endswith("…")
    assert long_snap == long_local[: MAX_RATIONALE_CHARS - 1] + "…"


@pytest.mark.parametrize("path,expected", [
    ("src/fake_widget.py", "served"),
    ("docs/fake_notes.md", "served"),
    ("docs/nope.md", "not_indexed"),
    ("examples/README.md", "not_indexed"),  # governance-excluded, not in served
    ("../etc/passwd", "unsafe"),
    ("/etc/passwd", "unsafe"),
    ("~/x", "unsafe"),
    ("a\\b.md", "unsafe"),
    ("", "unsafe"),
])
def test_parity_classify_path(snap, local, path, expected):
    assert snap.classify_path(path) == expected
    assert local.classify_path(path) == expected


def test_parity_on_disk_uniformly_false_in_snapshot(snap):
    payloads = [snap.concepts(), snap.files()]
    payloads += [snap.concept(c["id"]) for c in snap.concepts()]
    payloads += [snap.file(f["path"]) for f in snap.files()]
    for on_disk in _walk_on_disk(payloads):
        assert on_disk is False


def _walk_on_disk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "on_disk":
                yield v
            yield from _walk_on_disk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_on_disk(v)


# --- 2. degradation (reused reason strings; never raises) ---------------------


def test_missing_snapshot_is_graph_absent(tmp_path):
    reader = SanitizedSnapshotSource(tmp_path / "nope.json")  # never created
    ov = reader.overview()
    assert ov["available"] is False
    assert ov["reason"] == "graph_absent"
    assert reader.concepts() == []
    assert reader.files() == []
    assert reader.concept("concept_fake_alpha") is None
    assert reader.file("src/fake_widget.py") is None


def test_truncated_json_is_graph_unreadable(tmp_path):
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", "{not valid json"))
    ov = reader.overview()
    assert ov["available"] is False
    assert ov["reason"] == "graph_unreadable"
    assert reader.concepts() == []
    assert reader.files() == []


def test_non_dict_snapshot_is_graph_unreadable(tmp_path):
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", [1, 2, 3]))
    assert reader.overview()["reason"] == "graph_unreadable"


def test_wrong_kind_is_graph_unreadable(tmp_path):
    data = _golden_dict()
    data["kind"] = "not-a-memory-snapshot"
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", data))
    assert reader.overview()["reason"] == "graph_unreadable"


def test_unsupported_schema_version_is_graph_unreadable(tmp_path):
    data = _golden_dict()
    data["snapshot_schema_version"] = 999  # != supported
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", data))
    assert reader.overview()["reason"] == "graph_unreadable"


def test_missing_required_top_level_key_is_graph_unreadable(tmp_path):
    data = _golden_dict()
    del data["served"]
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", data))
    assert reader.overview()["reason"] == "graph_unreadable"


def test_incomplete_projection_is_graph_unreadable(tmp_path):
    # A concept present in ``concepts`` but absent from ``concept_detail``.
    data = _golden_dict()
    data["concepts"].append({
        "id": "ghost_concept", "label": "Ghost", "community_id": None,
        "community_name": None, "source_file": None, "on_disk": False,
    })
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", data))
    assert reader.overview()["reason"] == "graph_unreadable"


def test_incomplete_file_projection_is_graph_unreadable(tmp_path):
    data = _golden_dict()
    data["files"].append({
        "path": "src/ghost.py", "file_type": "code", "community_id": None,
        "community_name": None, "node_count": 0, "on_disk": False,
    })
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", data))
    assert reader.overview()["reason"] == "graph_unreadable"


def test_unavailable_data_methods_never_raise(tmp_path):
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", "[garbage"))
    assert reader.concepts() == []
    assert reader.files() == []
    assert reader.concept("concept_fake_alpha") is None
    assert reader.file("src/fake_widget.py") is None
    assert reader.classify_path("src/fake_widget.py") == "not_indexed"
    assert reader.classify_path("../x") == "unsafe"


# --- 3. status() separated contract (P24.10) ----------------------------------
#
# App-HEAD equality freshness is GONE. status() carries two separated, provable
# freshness concepts (policy_consistency, indexed_sources) plus separated
# availability / integrity / provider / version metadata. status() takes no
# build_commit — the deployed/app commit is NEVER an input to any freshness value.

#: The exact key set BOTH providers' status() return (parity contract).
STATUS_KEYS = {
    "provider_kind", "available", "integrity",
    "policy_fingerprint", "policy_consistency",
    "served_manifest_fingerprint", "served_file_count",
    "indexed_sources", "freshness_scope", "freshness_basis",
    "source_graph_commit", "source_graph_sha256", "snapshot_schema_version",
}


def test_snapshot_status_key_set(snap):
    assert set(snap.status().keys()) == STATUS_KEYS


def test_local_status_key_set(local):
    assert set(local.status().keys()) == STATUS_KEYS


def test_provider_status_key_parity(snap, local):
    # Identical key set across both providers, available or not.
    assert set(snap.status().keys()) == set(local.status().keys())
    with_missing = SanitizedSnapshotSource(_FIXTURE_ROOT / "does-not-exist.json")
    assert set(with_missing.status().keys()) == STATUS_KEYS


def test_snapshot_status_takes_no_build_commit(snap):
    with pytest.raises(TypeError):
        snap.status(build_commit=_SNAPSHOT_COMMIT)  # app-HEAD removed from status()


def test_snapshot_with_memory_inputs_is_current(snap):
    st = snap.status()
    assert st["provider_kind"] == "sanitized-snapshot"
    assert st["available"] is True
    assert st["integrity"] == "verified"
    assert st["policy_consistency"] == "current"
    assert st["indexed_sources"] == "current"
    assert st["policy_fingerprint"] == memory.compute_memory_policy_fingerprint()
    embedded = _golden_dict()["memory_inputs"]
    assert st["served_manifest_fingerprint"] == embedded["served_manifest_fingerprint"]
    assert st["served_file_count"] == embedded["served_file_count"] == 3
    assert st["freshness_scope"] == "served_files_only"
    assert st["freshness_basis"] == "ci_content_manifest"
    assert st["source_graph_commit"] == _SNAPSHOT_COMMIT
    assert st["source_graph_sha256"] == _SNAPSHOT_SHA256
    assert st["snapshot_schema_version"] == 1


def test_snapshot_without_memory_inputs_degrades_to_unknown(tmp_path):
    # A pre-P24.10 snapshot (like the current committed one) has no memory_inputs:
    # still available + integrity=verified, but the two freshness concepts and the
    # fingerprints degrade honestly to unknown/None.
    data = _golden_dict()
    del data["memory_inputs"]
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", data))
    st = reader.status()
    assert st["available"] is True
    assert st["integrity"] == "verified"
    assert st["policy_consistency"] == "unknown"
    assert st["indexed_sources"] == "unknown"
    assert st["policy_fingerprint"] is None
    assert st["served_manifest_fingerprint"] is None
    assert st["served_file_count"] is None


def test_snapshot_malformed_manifest_indexed_unknown_never_stale(tmp_path):
    # Tamper the embedded aggregate so it no longer matches the recomputed
    # aggregate of served_content_manifest -> internal inconsistency -> unknown.
    # NEVER stale: the hosted runtime cannot recompute file digests (files not
    # shipped), so drift detection is CI's authority, not the reader's.
    data = _golden_dict()
    data["memory_inputs"]["served_manifest_fingerprint"] = "0" * 64
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", data))
    st = reader.status()
    assert st["available"] is True
    assert st["integrity"] == "verified"
    assert st["indexed_sources"] == "unknown"
    assert st["indexed_sources"] != "stale"


def test_snapshot_policy_fingerprint_mismatch_is_stale(tmp_path):
    # A recomputable policy fingerprint that differs from the embedded one is a
    # real, provable policy drift -> stale (policy is recomputable at runtime).
    data = _golden_dict()
    data["memory_inputs"]["policy_fingerprint"] = "f" * 64
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", data))
    st = reader.status()
    assert st["available"] is True
    assert st["integrity"] == "verified"
    assert st["policy_consistency"] == "stale"
    assert st["policy_fingerprint"] == "f" * 64


def test_snapshot_unsupported_version_integrity(tmp_path):
    data = _golden_dict()
    data["snapshot_schema_version"] = 999  # present but unsupported
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", data))
    st = reader.status()
    assert st["available"] is False
    assert st["integrity"] == "unsupported"
    assert st["policy_consistency"] == "unknown"
    assert st["indexed_sources"] == "unknown"


def test_snapshot_malformed_json_integrity_is_malformed(tmp_path):
    reader = SanitizedSnapshotSource(_write_snapshot(tmp_path / "s.json", "{not json"))
    st = reader.status()
    assert st["available"] is False
    assert st["integrity"] == "malformed"
    assert st["policy_consistency"] == "unknown"
    assert st["indexed_sources"] == "unknown"


def test_snapshot_status_unavailable(tmp_path):
    reader = SanitizedSnapshotSource(tmp_path / "missing.json")
    st = reader.status()
    assert st["provider_kind"] == "sanitized-snapshot"
    assert st["available"] is False
    assert st["integrity"] == "unknown"
    assert st["policy_consistency"] == "unknown"
    assert st["indexed_sources"] == "unknown"
    assert st["policy_fingerprint"] is None
    assert st["served_manifest_fingerprint"] is None
    assert st["served_file_count"] is None
    assert st["source_graph_commit"] is None
    assert st["source_graph_sha256"] is None
    assert st["snapshot_schema_version"] is None


def test_local_status_unknown_freshness(local):
    # A live graph carries NO embedded memory_inputs, so it has no fingerprint
    # reference to prove against -> both freshness concepts are honestly unknown,
    # both fingerprints None. source_graph_commit is the graph's built_at_commit.
    st = local.status()
    assert st["provider_kind"] == "local-graph"
    assert st["available"] is True
    assert st["integrity"] == "verified"
    assert st["policy_consistency"] == "unknown"
    assert st["indexed_sources"] == "unknown"
    assert st["policy_fingerprint"] is None
    assert st["served_manifest_fingerprint"] is None
    assert st["source_graph_commit"] == _SNAPSHOT_COMMIT  # graph built_at_commit
    assert st["source_graph_sha256"] is None
    assert st["snapshot_schema_version"] is None


def test_local_status_unavailable(tmp_path):
    reader = LocalGraphArtifactSource(tmp_path / "graphify-out")  # never created
    st = reader.status()
    assert st["provider_kind"] == "local-graph"
    assert st["available"] is False
    assert st["integrity"] == "unknown"
    assert st["policy_consistency"] == "unknown"
    assert st["indexed_sources"] == "unknown"


# --- 4. classify_path safety regardless of availability -----------------------


@pytest.mark.parametrize("bad", [
    "../etc/passwd", "foo/../../bar", "/abs/path", "~/x", "a\\b.md", "", "docs/../secret",
])
def test_classify_path_unsafe_even_when_snapshot_missing(tmp_path, bad):
    reader = SanitizedSnapshotSource(tmp_path / "missing.json")
    assert reader.classify_path(bad) == "unsafe"


def test_classify_path_served_path_is_not_indexed_when_missing(tmp_path):
    reader = SanitizedSnapshotSource(tmp_path / "missing.json")
    assert reader.classify_path("src/fake_widget.py") == "not_indexed"


# --- 5. get_default_reader() precedence + memoization -------------------------


@pytest.fixture()
def reset_memo(monkeypatch):
    monkeypatch.setattr(memory, "_default_reader", None)
    monkeypatch.setattr(memory, "_default_choice", None)


def _copy_golden(path: Path) -> Path:
    path.write_bytes(_GOLDEN_SNAPSHOT.read_bytes())
    return path


def test_seam_snapshot_env_wins(tmp_path, monkeypatch, reset_memo):
    snap_file = _copy_golden(tmp_path / "snap.json")
    monkeypatch.setattr(memory, "_PACKAGED_SNAPSHOT", tmp_path / "nonexistent-packaged.json")
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(snap_file))
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(_FIXTURE_GRAPH_DIR))  # must be ignored
    reader = memory.get_default_reader()
    assert isinstance(reader, SanitizedSnapshotSource)
    assert reader.snapshot_path == snap_file
    assert reader.overview()["built_at_commit"] == _SNAPSHOT_COMMIT


def test_seam_packaged_snapshot_used_when_no_env(tmp_path, monkeypatch, reset_memo):
    packaged = _copy_golden(tmp_path / "packaged.json")
    monkeypatch.delenv("ISAAC_MEMORY_SNAPSHOT", raising=False)
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(_FIXTURE_GRAPH_DIR))  # must be ignored
    monkeypatch.setattr(memory, "_PACKAGED_SNAPSHOT", packaged)
    reader = memory.get_default_reader()
    assert isinstance(reader, SanitizedSnapshotSource)
    assert reader.snapshot_path == packaged


def test_seam_memory_dir_when_no_snapshot(tmp_path, monkeypatch, reset_memo):
    monkeypatch.delenv("ISAAC_MEMORY_SNAPSHOT", raising=False)
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(_FIXTURE_GRAPH_DIR))
    monkeypatch.setattr(memory, "_PACKAGED_SNAPSHOT", tmp_path / "nope.json")
    reader = memory.get_default_reader()
    assert isinstance(reader, LocalGraphArtifactSource)
    assert reader.artifacts_dir == _FIXTURE_GRAPH_DIR


def test_seam_graphify_out_fallback(tmp_path, monkeypatch, reset_memo):
    monkeypatch.delenv("ISAAC_MEMORY_SNAPSHOT", raising=False)
    monkeypatch.delenv("ISAAC_MEMORY_DIR", raising=False)
    monkeypatch.setattr(memory, "_PACKAGED_SNAPSHOT", tmp_path / "nope.json")
    reader = memory.get_default_reader()
    assert isinstance(reader, LocalGraphArtifactSource)
    assert reader.artifacts_dir == memory._REPO_ROOT / "graphify-out"


def test_seam_memoized_and_rebuilt_on_choice_change(tmp_path, monkeypatch, reset_memo):
    snap_file = _copy_golden(tmp_path / "snap.json")
    monkeypatch.setattr(memory, "_PACKAGED_SNAPSHOT", tmp_path / "nope.json")
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(snap_file))
    r1 = memory.get_default_reader()
    r2 = memory.get_default_reader()
    assert r1 is r2  # same resolved choice -> memoized instance reused
    # Change the resolved choice -> rebuild a new instance.
    monkeypatch.delenv("ISAAC_MEMORY_SNAPSHOT", raising=False)
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(_FIXTURE_GRAPH_DIR))
    r3 = memory.get_default_reader()
    assert r3 is not r1
    assert isinstance(r3, LocalGraphArtifactSource)


# --- 6. cache behavior (mirrors the local reader) -----------------------------


def test_snapshot_parse_is_cached_and_reparses_on_mtime_change(tmp_path):
    import os

    snap_file = _copy_golden(tmp_path / "snap.json")
    reader = SanitizedSnapshotSource(snap_file)
    reader.overview()
    reader.concepts()
    reader.files()
    reader.file("src/fake_widget.py")
    assert reader.reload_count == 1  # parsed once despite many calls

    bumped = snap_file.stat().st_mtime + 10
    os.utime(snap_file, (bumped, bumped))
    reader.overview()
    assert reader.reload_count == 2  # re-parsed after mtime change


# --- 7. no-verdict / no-content / no-plane sweep ------------------------------


def test_no_verdict_or_content_or_plane_keys_anywhere(snap):
    payloads = [
        snap.overview(),
        snap.concepts(),
        snap.concept("concept_fake_alpha"),
        snap.files(),
        snap.file("src/fake_widget.py"),
        snap.status(),
    ]
    for payload in payloads:
        keys = set(_walk_keys(payload))
        assert "content" not in keys
        assert "lines" not in keys
        assert "plane" not in keys  # plane marking is added by routes, not the reader
        assert keys.isdisjoint(FORBIDDEN_VERDICT_KEYS)


# --- 8. interface: status is part of the seam ---------------------------------


def test_both_providers_expose_status(snap, local):
    assert callable(getattr(snap, "status"))
    assert callable(getattr(local, "status"))

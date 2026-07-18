"""Tests for the ``/api/memory/*`` HTTP endpoints and the additive
``/api/graph/status`` fields (P24.2).

These endpoints wrap the P24.1 read-only reader (``isaac_api.memory``) over
HTTP. Every test drives a real FastAPI ``TestClient`` against a synthetic,
unmistakably-fake ``graphify-out/`` artifact set pointed to via
``ISAAC_MEMORY_DIR`` — never the real repo graph — so results are deterministic
regardless of the real local graph's state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FORBIDDEN_KEYS = {"ok", "valid", "passed", "verdict", "schema", "errors"}
MEMORY_NOTE_FRAGMENT = "leads to verify"


def _repo_root() -> Path:
    """Walk up until the vendored official schema is found (mirrors memory.py)."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    return here.parents[3]


# --- synthetic-fixture builders (unmistakably fake; local to this test file) --


def _synthetic_graph() -> dict:
    """A tiny fake graph in networkx node-link shape (edges under ``links``)."""
    nodes = [
        {"id": "concept_alpha", "label": "Alpha concept", "file_type": "concept",
         "community": 7, "source_file": "docs/fake-note.md", "source_location": None},
        {"id": "concept_beta", "label": "Beta concept", "file_type": "concept",
         "community": 9, "source_file": "docs/fake-note.md", "source_location": None},
        {"id": "docs_fake_note", "label": "fake-note.md", "file_type": "document",
         "community": 7, "source_file": "docs/fake-note.md", "source_location": "L1"},
        {"id": "src_fake_mod", "label": "fake_mod.py", "file_type": "code",
         "community": 3, "source_file": "src/fake_mod.py", "source_location": "L1"},
        {"id": "src_other_mod", "label": "other_mod.py", "file_type": "code",
         "community": 5, "source_file": "src/other_mod.py", "source_location": "L1"},
    ]
    links = [
        {"source": "concept_alpha", "target": "src_fake_mod", "relation": "references",
         "weight": 5.0, "source_file": "docs/fake-note.md"},
        {"source": "concept_alpha", "target": "concept_beta", "relation": "relates_to",
         "weight": 3.0, "source_file": "docs/fake-note.md"},
        {"source": "src_fake_mod", "target": "src_other_mod", "relation": "imports",
         "weight": 4.0, "source_file": "src/fake_mod.py"},
    ]
    return {"nodes": nodes, "links": links, "built_at_commit": "fakecommit0000"}


def _synthetic_manifest() -> dict:
    keys = [
        "docs/fake-note.md",
        "src/fake_mod.py",
        "src/other_mod.py",
        # governance-excluded, present in the raw manifest, must 404 at the API:
        "examples/README.md",
    ]
    return {k: {"mtime": 1.0, "ast_hash": "fake", "semantic_hash": ""} for k in keys}


def _synthetic_labels() -> dict:
    return {"7": "Alpha community", "9": "Beta community",
            "3": "Mod community", "5": "Other community"}


def _write_artifacts(repo_root: Path, *, graph=..., manifest=..., labels=...) -> Path:
    """Write a fake ``graphify-out/`` under ``repo_root``; return the artifacts dir.

    ``...`` (Ellipsis, the default) uses the synthetic content above; ``None``
    skips writing that file; a ``dict`` is dumped as JSON; a ``str`` is written
    verbatim (for corrupt-JSON cases).
    """
    art = repo_root / "graphify-out"
    art.mkdir(parents=True, exist_ok=True)
    spec = {
        "graph.json": _synthetic_graph() if graph is ... else graph,
        "manifest.json": _synthetic_manifest() if manifest is ... else manifest,
        ".graphify_labels.json": _synthetic_labels() if labels is ... else labels,
    }
    for name, value in spec.items():
        if value is None:
            continue
        text = value if isinstance(value, str) else json.dumps(value)
        (art / name).write_text(text, encoding="utf-8")
    return art


def _client(tmp_path, monkeypatch, memory_dir=None) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    if memory_dir is not None:
        monkeypatch.setenv("ISAAC_MEMORY_DIR", str(memory_dir))
    from isaac_api.app import create_app

    return TestClient(create_app())


def _walk_keys(obj):
    """Yield every dict key appearing anywhere in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


def _assert_envelope(body: dict) -> None:
    assert body["plane"] == "memory"
    assert MEMORY_NOTE_FRAGMENT in body["note"]


# --- 1. success against fixture ------------------------------------------------


def test_memory_concepts_available(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/concepts").json()
    _assert_envelope(body)
    assert body["available"] is True
    assert "reason" not in body
    assert len(body["concepts"]) == 2
    alpha = next(c for c in body["concepts"] if c["id"] == "concept_alpha")
    assert alpha == {
        "id": "concept_alpha",
        "label": "Alpha concept",
        "community_id": "7",
        "community_name": "Alpha community",
        "source_file": "docs/fake-note.md",
        "on_disk": False,
    }


def test_memory_concept_detail_available(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/concepts/concept_alpha").json()
    _assert_envelope(body)
    assert body["available"] is True
    assert body["concept"]["id"] == "concept_alpha"
    assert "related" not in body["concept"]  # related is a sibling, not nested
    files = body["related"]["files"]
    concepts = body["related"]["concepts"]
    assert files == [{"path": "src/fake_mod.py", "relation": "references", "file_type": "code"}]
    assert concepts == [{"id": "concept_beta", "label": "Beta concept", "relation": "relates_to"}]
    assert len(files) <= 25
    assert len(concepts) <= 25


def test_memory_files_available(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/files").json()
    _assert_envelope(body)
    assert body["available"] is True
    paths = {f["path"] for f in body["files"]}
    assert paths == {"docs/fake-note.md", "src/fake_mod.py", "src/other_mod.py"}
    assert "examples/README.md" not in paths  # governance-excluded


def test_memory_file_detail_available(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/file", params={"path": "src/fake_mod.py"}).json()
    _assert_envelope(body)
    assert body["available"] is True
    file_ = body["file"]
    assert file_["path"] == "src/fake_mod.py"
    assert file_["file_type"] == "code"
    assert file_["local_reference"] == "src/fake_mod.py"
    assert "content" not in file_
    assert "lines" not in file_
    assert body["related"]["files"] == [
        {"path": "src/other_mod.py", "relation": "imports", "file_type": "code"}
    ]
    assert isinstance(body["rationales"], list)
    assert len(body["rationales"]) <= 10


def test_graph_status_additive_fields_present_when_available(tmp_path, monkeypatch):
    # No ISAAC_BUILD_COMMIT/RAILWAY_GIT_COMMIT_SHA set -> the reader's freshness
    # is deterministically "unknown" (the backend's own build commit is
    # unknown), while the graph itself IS available -> real counts present.
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "unknown"
    assert body["plane"] == "memory"
    assert body["built_at_commit"] == "fakecommit0000"
    assert body["node_count"] == 5
    assert body["edge_count"] == 3
    assert body["community_count"] == 4  # distinct communities {7,9,3,5}
    assert body["concept_count"] == 2
    assert body["file_count"] == 3  # served allowlist count (examples/ excluded)
    assert isinstance(body["graph_mtime"], float)
    assert body["provider_kind"] == "local-graph"
    assert body["snapshot_schema_version"] is None
    assert body["source_graph_sha256"] is None


def test_graph_status_local_provider_fresh_when_build_commit_matches(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "fakecommit0000")  # matches the synthetic graph
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "fresh"
    assert body["provider_kind"] == "local-graph"
    assert body["node_count"] == 5  # counts present alongside fresh


def test_graph_status_local_provider_stale_when_build_commit_differs(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "some-other-commit")
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "stale"
    assert body["provider_kind"] == "local-graph"
    assert body["node_count"] == 5  # counts present alongside stale


# --- 1b. P24.9: no emitted path may fail the served allowlist ------------------
#
# Concept anchors and related-file paths come from GRAPH NODES, not the manifest
# served allowlist, so an anchor/related path can point at a governance-excluded
# path (the live ``examples/README.md`` leak). Drive the real API and assert NO
# path-bearing field in any available response fails ``_is_served``; the
# examples-anchored concept specifically returns ``source_file: null`` while
# still being listed. RED before the reader hardening.

_PATH_KEYS = {"path", "source_file", "local_reference"}


def _walk_path_values(obj):
    """Yield ``(key, value)`` for every non-empty string under a path-bearing key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _PATH_KEYS and isinstance(v, str) and v:
                yield k, v
            yield from _walk_path_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_path_values(item)


def _anchor_graph() -> dict:
    """Graph with concepts anchored at examples-excluded / absolute / traversal
    paths, and a file whose related neighbors include a served path plus
    governance-excluded, absolute, and traversal paths — all of which must be
    withheld / dropped."""
    nodes = [
        {"id": "c_examples", "label": "Examples-anchored concept", "file_type": "concept",
         "community": 1, "source_file": "examples/README.md"},
        {"id": "c_absolute", "label": "Absolute-anchored concept", "file_type": "concept",
         "community": 1, "source_file": "/etc/passwd"},
        {"id": "c_traversal", "label": "Traversal-anchored concept", "file_type": "concept",
         "community": 1, "source_file": "../../secret"},
        {"id": "c_ok", "label": "Approved-anchor concept", "file_type": "concept",
         "community": 1, "source_file": "docs/fake-note.md"},
        {"id": "hub", "label": "hub.py", "file_type": "code", "community": 2,
         "source_file": "src/fake_mod.py", "source_location": "L1"},
        {"id": "served_neighbor", "label": "other_mod.py", "file_type": "code",
         "community": 2, "source_file": "src/other_mod.py", "source_location": "L1"},
        {"id": "excluded_neighbor", "label": "README.md", "file_type": "document",
         "community": 2, "source_file": "examples/README.md", "source_location": "L1"},
        {"id": "abs_neighbor", "label": "passwd", "file_type": "document",
         "community": 2, "source_file": "/etc/passwd", "source_location": "L1"},
        {"id": "traversal_neighbor", "label": "secret", "file_type": "document",
         "community": 2, "source_file": "../../secret", "source_location": "L1"},
    ]
    links = [
        {"source": "hub", "target": "served_neighbor", "relation": "imports",
         "weight": 5.0, "source_file": "src/fake_mod.py"},
        {"source": "hub", "target": "excluded_neighbor", "relation": "references",
         "weight": 9.0, "source_file": "src/fake_mod.py"},
        {"source": "hub", "target": "abs_neighbor", "relation": "references",
         "weight": 8.0, "source_file": "src/fake_mod.py"},
        {"source": "hub", "target": "traversal_neighbor", "relation": "references",
         "weight": 7.0, "source_file": "src/fake_mod.py"},
    ]
    return {"nodes": nodes, "links": links, "built_at_commit": "fakecommit0000"}


def _anchor_manifest() -> dict:
    keys = ["docs/fake-note.md", "src/fake_mod.py", "src/other_mod.py", "examples/README.md"]
    return {k: {"mtime": 1.0, "ast_hash": "fake", "semantic_hash": ""} for k in keys}


def _assert_no_unserved_path(body: dict) -> None:
    from isaac_api.memory import LocalGraphArtifactSource, _is_served

    for key, value in _walk_path_values(body):
        # Every emitted path must be BOTH governance-served AND path-safe — an
        # absolute/traversal path would now fail this sweep, not just an
        # examples/** path.
        assert _is_served(value), f"unserved path leaked via {key!r}: {value!r}"
        assert not LocalGraphArtifactSource._is_unsafe(value), \
            f"path-unsafe value leaked via {key!r}: {value!r}"


@pytest.mark.parametrize("cid", ["c_examples", "c_absolute", "c_traversal"])
def test_memory_concepts_withheld_anchor_nulled_but_listed(tmp_path, monkeypatch, cid):
    art = _write_artifacts(tmp_path, graph=_anchor_graph(), manifest=_anchor_manifest())
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/concepts").json()
    assert body["available"] is True
    concept = next(c for c in body["concepts"] if c["id"] == cid)
    assert concept["source_file"] is None  # excluded/absolute/traversal anchor withheld
    assert concept["on_disk"] is False
    _assert_no_unserved_path(body)


@pytest.mark.parametrize("cid", ["c_examples", "c_absolute", "c_traversal"])
def test_memory_concept_detail_withheld_anchor_nulled(tmp_path, monkeypatch, cid):
    art = _write_artifacts(tmp_path, graph=_anchor_graph(), manifest=_anchor_manifest())
    client = _client(tmp_path, monkeypatch, art)
    body = client.get(f"/api/memory/concepts/{cid}").json()
    assert body["available"] is True
    assert body["concept"]["source_file"] is None
    assert body["concept"]["on_disk"] is False
    _assert_no_unserved_path(body)


def test_memory_file_related_drops_excluded_and_unsafe_neighbors(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path, graph=_anchor_graph(), manifest=_anchor_manifest())
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/file", params={"path": "src/fake_mod.py"}).json()
    assert body["available"] is True
    related_paths = [f["path"] for f in body["related"]["files"]]
    assert "src/other_mod.py" in related_paths  # served neighbor retained
    assert "examples/README.md" not in related_paths  # governance-excluded dropped
    assert "/etc/passwd" not in related_paths  # absolute dropped
    assert "../../secret" not in related_paths  # traversal dropped
    _assert_no_unserved_path(body)


def test_no_unserved_path_across_all_memory_endpoints(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path, graph=_anchor_graph(), manifest=_anchor_manifest())
    client = _client(tmp_path, monkeypatch, art)
    bodies = [
        client.get("/api/memory/concepts").json(),
        client.get("/api/memory/concepts/c_examples").json(),
        client.get("/api/memory/concepts/c_absolute").json(),
        client.get("/api/memory/concepts/c_traversal").json(),
        client.get("/api/memory/concepts/c_ok").json(),
        client.get("/api/memory/files").json(),
        client.get("/api/memory/file", params={"path": "src/fake_mod.py"}).json(),
    ]
    for body in bodies:
        _assert_no_unserved_path(body)


# --- 2. missing graph (env -> empty tmp dir) -----------------------------------


def test_memory_endpoints_available_false_when_graph_absent(tmp_path, monkeypatch):
    empty_dir = tmp_path / "graphify-out"  # never created
    client = _client(tmp_path, monkeypatch, empty_dir)

    concepts = client.get("/api/memory/concepts").json()
    _assert_envelope(concepts)
    assert concepts == {
        "plane": "memory", "note": concepts["note"],
        "available": False, "reason": "graph_absent", "concepts": [],
    }

    concept = client.get("/api/memory/concepts/concept_alpha").json()
    assert concept["available"] is False
    assert concept["reason"] == "graph_absent"
    assert concept["concept"] is None
    assert concept["related"] == {"files": [], "concepts": []}

    files = client.get("/api/memory/files").json()
    assert files["available"] is False
    assert files["reason"] == "graph_absent"
    assert files["files"] == []

    file_ = client.get("/api/memory/file", params={"path": "src/fake_mod.py"}).json()
    assert file_["available"] is False
    assert file_["reason"] == "graph_absent"
    assert file_["file"] is None


def test_graph_status_additive_fields_absent_when_missing(tmp_path, monkeypatch):
    memory_dir = tmp_path / "graphify-out"  # never created
    client = _client(tmp_path, monkeypatch, memory_dir)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "missing"
    for key in ("built_at_commit", "node_count", "edge_count",
                "community_count", "file_count", "concept_count", "graph_mtime"):
        assert body[key] is None
    # provider_kind is provider IDENTITY, not a graph-content count — it stays
    # populated even when the graph itself is absent (mirrors reader.status()
    # returning provider_kind regardless of availability).
    assert body["provider_kind"] == "local-graph"
    assert body["snapshot_schema_version"] is None
    assert body["source_graph_sha256"] is None


def test_graph_status_single_source_when_env_overrides(tmp_path, monkeypatch):
    """ISAAC_MEMORY_DIR points at a populated graph: `status` and the additive
    counts must describe the SAME graph — never a self-contradictory body
    reading status:"missing" alongside populated counts (the documented future
    mounted-volume case). ISAAC_BUILD_COMMIT is set to the synthetic graph's own
    commit so freshness is deterministically "fresh", pinning the honest value
    rather than merely asserting "not missing"."""
    art = _write_artifacts(tmp_path / "volume")
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "fakecommit0000")
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/graph/status").json()
    # Counts describe the env-pointed graph...
    assert body["built_at_commit"] == "fakecommit0000"
    assert body["node_count"] == 5
    # ...and status must describe that same graph, so it cannot be "missing".
    assert body["status"] != "missing"
    assert body["status"] == "fresh"


# --- 2b. snapshot provider (packaged/explicit via ISAAC_MEMORY_SNAPSHOT) -------
#
# Reuses the golden fixture snapshot from test_snapshot_source.py (same repo
# path, same known commit/sha256) so these route-level tests pin the SAME
# provider-agnostic wiring against the second concrete MemoryReader, with no
# isinstance branch in routes.py.

_SNAPSHOT_FIXTURE = _repo_root() / "tests" / "fixtures" / "memory_snapshot" / "memory-snapshot.json"
_SNAPSHOT_COMMIT = "fakecommitp24900"
_SNAPSHOT_SHA256 = "86c25c586b3f9c104b087ba1be3db5486347cb81486b6c57a5085fc9a5dbc0d6"


def test_graph_status_snapshot_provider_fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(_SNAPSHOT_FIXTURE))
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", _SNAPSHOT_COMMIT)
    client = _client(tmp_path, monkeypatch)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "fresh"
    assert body["provider_kind"] == "sanitized-snapshot"
    assert body["snapshot_schema_version"] == 1
    assert body["source_graph_sha256"] == _SNAPSHOT_SHA256
    assert body["built_at_commit"] == _SNAPSHOT_COMMIT
    assert body["node_count"] is not None


def test_graph_status_snapshot_provider_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(_SNAPSHOT_FIXTURE))
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "deadbeefdeadbeef")  # differs from the snapshot
    client = _client(tmp_path, monkeypatch)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "stale"
    assert body["provider_kind"] == "sanitized-snapshot"
    assert body["node_count"] is not None  # counts present alongside stale


def test_graph_status_snapshot_provider_unknown_when_no_build_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(_SNAPSHOT_FIXTURE))
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    client = _client(tmp_path, monkeypatch)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "unknown"
    assert body["provider_kind"] == "sanitized-snapshot"
    assert body["node_count"] is not None  # available -> real counts, just unknown freshness


def test_graph_status_snapshot_missing_file_is_missing_with_null_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(tmp_path / "nope.json"))  # never created
    client = _client(tmp_path, monkeypatch)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "missing"
    for key in ("built_at_commit", "node_count", "edge_count",
                "community_count", "file_count", "concept_count", "graph_mtime"):
        assert body[key] is None
    assert body["provider_kind"] == "sanitized-snapshot"
    assert body["snapshot_schema_version"] is None
    assert body["source_graph_sha256"] is None


def test_graph_status_snapshot_unsupported_version_is_missing_with_null_counts(tmp_path, monkeypatch):
    data = json.loads(_SNAPSHOT_FIXTURE.read_text(encoding="utf-8"))
    data["snapshot_schema_version"] = 999  # unsupported -> graph_unreadable
    bad_snapshot = tmp_path / "bad-snapshot.json"
    bad_snapshot.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(bad_snapshot))
    client = _client(tmp_path, monkeypatch)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "missing"
    for key in ("built_at_commit", "node_count", "edge_count",
                "community_count", "file_count", "concept_count", "graph_mtime"):
        assert body[key] is None


def test_graph_status_note_never_carries_verdict_wording_across_states(tmp_path, monkeypatch):
    """Sweep fresh/stale/unknown/missing (both providers) and assert the `note`
    is always non-empty and free of PASS/FAIL/verdict wording — the memory
    plane never speaks in validator language, in any state."""
    notes = []

    # local: unknown (no build commit), fresh, stale.
    art = _write_artifacts(tmp_path / "local-graph")
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    notes.append(_client(tmp_path, monkeypatch, art).get("/api/graph/status").json()["note"])
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "fakecommit0000")
    notes.append(_client(tmp_path, monkeypatch, art).get("/api/graph/status").json()["note"])
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", "some-other-commit")
    notes.append(_client(tmp_path, monkeypatch, art).get("/api/graph/status").json()["note"])

    # local: missing (never-created dir).
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    notes.append(
        _client(tmp_path, monkeypatch, tmp_path / "never-created").get("/api/graph/status").json()["note"]
    )

    # snapshot: fresh.
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(_SNAPSHOT_FIXTURE))
    monkeypatch.setenv("ISAAC_BUILD_COMMIT", _SNAPSHOT_COMMIT)
    notes.append(_client(tmp_path, monkeypatch).get("/api/graph/status").json()["note"])

    for note in notes:
        assert note
        assert "PASS" not in note and "FAIL" not in note
        assert "verdict" not in note


# --- 3. malformed graph ---------------------------------------------------------


def test_memory_endpoints_available_false_when_graph_unreadable(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path, graph="{not valid json")
    client = _client(tmp_path, monkeypatch, art)

    for path in ("/api/memory/concepts", "/api/memory/files"):
        resp = client.get(path)
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["reason"] == "graph_unreadable"

    concept = client.get("/api/memory/concepts/concept_alpha")
    assert concept.status_code == 200
    assert concept.json()["available"] is False
    assert concept.json()["reason"] == "graph_unreadable"

    file_ = client.get("/api/memory/file", params={"path": "src/fake_mod.py"})
    assert file_.status_code == 200
    assert file_.json()["available"] is False
    assert file_.json()["reason"] == "graph_unreadable"


def test_graph_status_coherent_when_graph_exists_but_malformed(tmp_path, monkeypatch):
    """P24.9-impl-3: pin ``/api/graph/status`` when ``graph.json`` EXISTS but is
    malformed. The reader itself reports ``available: False`` (reason
    ``graph_unreadable``) for a type-corrupt/unparseable graph, so the wire
    ``status`` is ``"missing"`` — never a 500, and never a populated-count +
    parse-failure contradiction (every additive count is ``null``). This is the
    single-source invariant: status and counts always describe the SAME
    (in this case, unreadable) graph state.
    """
    art = _write_artifacts(tmp_path, graph="{not valid json")
    client = _client(tmp_path, monkeypatch, art)
    resp = client.get("/api/graph/status")
    assert resp.status_code == 200  # never 500
    body = resp.json()
    assert body["status"] == "missing"
    for key in ("node_count", "edge_count", "community_count", "file_count",
                "concept_count", "built_at_commit", "graph_mtime"):
        assert body[key] is None
    assert body["plane"] == "memory"
    assert "note" in body and body["note"]
    assert body["provider_kind"] == "local-graph"


# --- 4. auth ---------------------------------------------------------------------


@pytest.mark.parametrize("route", [
    "/api/memory/concepts",
    "/api/memory/concepts/concept_alpha",
    "/api/memory/files",
    "/api/memory/file?path=src/fake_mod.py",
])
def test_memory_endpoints_require_bearer_when_key_set(tmp_path, monkeypatch, route):
    art = _write_artifacts(tmp_path)
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    client = _client(tmp_path, monkeypatch, art)

    missing = client.get(route)
    assert missing.status_code == 401

    ok = client.get(route, headers={"Authorization": "Bearer demo-secret"})
    assert ok.status_code == 200


# --- 5. forbidden / unsafe path --------------------------------------------------


@pytest.mark.parametrize("bad_path", [
    "../schema/isaac_record_v1.json",
    "/etc/passwd",
])
def test_memory_file_unsafe_path_400(tmp_path, monkeypatch, bad_path):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    resp = client.get("/api/memory/file", params={"path": bad_path})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "unsafe_source_path"
    assert body["path"] == bad_path
    _assert_envelope(body)


def test_memory_file_clean_unknown_404(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    resp = client.get("/api/memory/file", params={"path": "docs/does-not-exist.md"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "source_not_indexed"
    _assert_envelope(body)


def test_memory_file_governance_excluded_404_even_though_in_raw_manifest(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    resp = client.get("/api/memory/file", params={"path": "examples/README.md"})
    assert resp.status_code == 404
    assert resp.json()["error"] == "source_not_indexed"


# --- 6. concept 404 ---------------------------------------------------------------


def test_memory_concept_unknown_404(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    resp = client.get("/api/memory/concepts/does_not_exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "concept_not_found"
    assert body["id"] == "does_not_exist"
    _assert_envelope(body)


# --- 7. no-verdict-language invariant ----------------------------------------------


def test_no_forbidden_verdict_keys_in_any_memory_response(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    empty_dir = tmp_path / "does-not-exist"

    bodies = [
        client.get("/api/memory/concepts").json(),
        client.get("/api/memory/concepts/concept_alpha").json(),
        client.get("/api/memory/concepts/nope").json(),
        client.get("/api/memory/files").json(),
        client.get("/api/memory/file", params={"path": "src/fake_mod.py"}).json(),
        client.get("/api/memory/file", params={"path": "../etc/passwd"}).json(),
        client.get("/api/memory/file", params={"path": "docs/nope.md"}).json(),
        client.get("/api/graph/status").json(),
    ]

    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(empty_dir))
    from isaac_api.app import create_app
    degraded_client = TestClient(create_app())
    bodies.append(degraded_client.get("/api/memory/concepts").json())
    bodies.append(degraded_client.get("/api/memory/concepts/concept_alpha").json())
    bodies.append(degraded_client.get("/api/memory/files").json())
    bodies.append(
        degraded_client.get("/api/memory/file", params={"path": "src/fake_mod.py"}).json()
    )
    # Degraded /api/graph/status (additive fields nulled) is swept too.
    bodies.append(degraded_client.get("/api/graph/status").json())

    for body in bodies:
        keys = set(_walk_keys(body))
        assert keys.isdisjoint(FORBIDDEN_KEYS), f"forbidden key found in {body!r}"


# --- 8. status back-compat -------------------------------------------------------


def test_graph_status_backward_compatible_shape_untouched(tmp_path, monkeypatch):
    """P24.9-impl-3: the pre-existing shape (status/plane/note) is preserved;
    `status` additionally accepts "unknown" now. build_commit is forced to
    None so this is deterministic regardless of the developer's local
    graphify-out/ state (see test_graph_status in test_api.py for the same
    pattern)."""
    monkeypatch.delenv("ISAAC_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    client = _client(tmp_path, monkeypatch)
    body = client.get("/api/graph/status").json()
    assert body["status"] in {"unknown", "missing"}
    assert body["plane"] == "memory"
    assert body["note"]

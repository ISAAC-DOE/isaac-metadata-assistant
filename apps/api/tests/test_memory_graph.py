"""Tests for the ``GET /api/memory/graph`` endpoint and its pure projection
function ``isaac_api.memory_graph.build_graph_projection`` (P36.2).

Mirrors ``test_memory_api.py``'s conventions: a real FastAPI ``TestClient``
driven against a synthetic, unmistakably-fake ``graphify-out/`` artifact set
via ``ISAAC_MEMORY_DIR`` (never the real repo graph) for most cases, plus one
integration check (test 14) against the real committed
``apps/api/isaac_api/data/memory-snapshot.json`` for the documented real
counts (201 files / 19 concepts / 508 edges).
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api import memory_graph

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
# A richer graph than test_memory_api.py's: 4 files with real, DISTINCT
# relation values (references / imports / calls / imports_from /
# shares_data_with all appear at least once across the fixture, spread over
# multiple links so we can assert the real strings are preserved verbatim and
# that a multi-edge between the SAME file pair accumulates into a sorted-
# unique ``relations`` list), plus 2 isolated concepts (concepts never
# contribute an edge — matches the real snapshot's ground truth).


def _synthetic_graph() -> dict:
    nodes = [
        {"id": "concept_alpha", "label": "Alpha concept", "file_type": "concept",
         "community": 7, "source_file": "docs/fake-note.md"},
        {"id": "concept_beta", "label": "Beta concept", "file_type": "concept",
         "community": 9, "source_file": "docs/fake-note.md"},
        {"id": "docs_fake_note", "label": "fake-note.md", "file_type": "document",
         "community": 7, "source_file": "docs/fake-note.md", "source_location": "L1"},
        {"id": "src_fake_mod", "label": "fake_mod.py", "file_type": "code",
         "community": 3, "source_file": "src/fake_mod.py", "source_location": "L1"},
        {"id": "src_fake_mod_2", "label": "fake_mod.py helper", "file_type": "code",
         "community": 3, "source_file": "src/fake_mod.py", "source_location": "L2"},
        {"id": "src_other_mod", "label": "other_mod.py", "file_type": "code",
         "community": 5, "source_file": "src/other_mod.py", "source_location": "L1"},
        {"id": "src_third_mod", "label": "third_mod.py", "file_type": "code",
         "community": 5, "source_file": "src/third_mod.py", "source_location": "L1"},
    ]
    links = [
        # concept <-> concept edge: the reader classifies a neighbor as a
        # "concept" relation purely by the NEIGHBOR's own file_type, so this
        # is aggregated into related.concepts (never related.files) from
        # either side — it must never surface as a graph-tab file-file edge
        # (edges come ONLY from a file's own related.files[]).
        {"source": "concept_alpha", "target": "concept_beta", "relation": "relates_to",
         "weight": 3.0, "source_file": "docs/fake-note.md"},
        # fake_mod.py <-> other_mod.py: TWO distinct multi-edges via two
        # different node-pairs of the SAME two files, with DIFFERENT
        # relations -> the projection must accumulate both into one sorted
        # ``relations`` list for the single (fake_mod, other_mod) pair.
        {"source": "src_fake_mod", "target": "src_other_mod", "relation": "imports",
         "weight": 4.0, "source_file": "src/fake_mod.py"},
        {"source": "src_fake_mod_2", "target": "src_other_mod", "relation": "calls",
         "weight": 4.0, "source_file": "src/fake_mod.py"},
        # other_mod.py <-> third_mod.py: a third, distinct relation value.
        {"source": "src_other_mod", "target": "src_third_mod", "relation": "imports_from",
         "weight": 2.0, "source_file": "src/other_mod.py"},
        # fake_mod.py <-> third_mod.py: the fifth relation value.
        {"source": "src_fake_mod", "target": "src_third_mod", "relation": "shares_data_with",
         "weight": 1.0, "source_file": "src/fake_mod.py"},
    ]
    return {"nodes": nodes, "links": links, "built_at_commit": "fakecommit0000"}


def _synthetic_manifest() -> dict:
    keys = [
        "docs/fake-note.md",
        "src/fake_mod.py",
        "src/other_mod.py",
        "src/third_mod.py",
        # governance-excluded, present in the raw manifest, must never surface:
        "examples/README.md",
    ]
    return {k: {"mtime": 1.0, "ast_hash": "fake", "semantic_hash": ""} for k in keys}


def _synthetic_labels() -> dict:
    return {"7": "Alpha community", "9": "Beta community",
            "3": "Mod community", "5": "Other community"}


def _write_artifacts(repo_root: Path, *, graph=..., manifest=..., labels=...) -> Path:
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


def _walk(obj):
    """Yield every (key, value) pair appearing anywhere in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def _walk_keys(obj):
    for k, _ in _walk(obj):
        yield k


def _walk_values(obj):
    for _, v in _walk(obj):
        yield v


# --- 1. projection shape --------------------------------------------------


def test_graph_projection_shape_available(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    resp = client.get("/api/memory/graph")
    assert resp.status_code == 200
    body = resp.json()

    assert body["plane"] == "memory"
    assert MEMORY_NOTE_FRAGMENT in body["note"]
    assert body["available"] is True
    assert body["truncated"] is False

    node_ids = {n["id"] for n in body["nodes"]}
    file_paths = {"docs/fake-note.md", "src/fake_mod.py", "src/other_mod.py", "src/third_mod.py"}
    concept_ids = {"concept_alpha", "concept_beta"}
    assert node_ids == file_paths | concept_ids
    assert "examples/README.md" not in node_ids  # governance-excluded

    kinds = {n["id"]: n["kind"] for n in body["nodes"]}
    for p in file_paths:
        assert kinds[p] == "file"
    for c in concept_ids:
        assert kinds[c] == "concept"

    # A file node carries the full shape.
    fake_mod = next(n for n in body["nodes"] if n["id"] == "src/fake_mod.py")
    assert fake_mod == {
        "id": "src/fake_mod.py",
        "kind": "file",
        "label": "src/fake_mod.py",
        "file_type": "code",
        "community_id": "3",
        "community_name": "Mod community",
        "node_count": 2,
        "on_disk": False,
    }
    alpha = next(n for n in body["nodes"] if n["id"] == "concept_alpha")
    assert alpha == {
        "id": "concept_alpha",
        "kind": "concept",
        "label": "Alpha concept",
        "community_id": "7",
        "community_name": "Alpha community",
        "on_disk": False,
        "source_file": "docs/fake-note.md",
    }

    # Edges: unique undirected pairs, real relation strings preserved, the
    # concept<->concept link never surfaces as a file-file edge.
    edge_pairs = {(e["source"], e["target"]) for e in body["edges"]}
    assert edge_pairs == {
        ("src/fake_mod.py", "src/other_mod.py"),
        ("src/other_mod.py", "src/third_mod.py"),
        ("src/fake_mod.py", "src/third_mod.py"),
    }
    fake_other = next(
        e for e in body["edges"]
        if {e["source"], e["target"]} == {"src/fake_mod.py", "src/other_mod.py"}
    )
    # Two distinct multi-edges (imports / calls) tie on weight between the
    # same file pair; the reader's own canonicalization picks one
    # deterministic winner ("calls" < "imports" lexicographically) — see
    # test_relations_accumulate_from_both_directions_when_they_differ below
    # for the projection's OWN accumulation logic, exercised directly against
    # a reader double that reports genuinely different relations per side.
    assert fake_other["relations"] == ["calls"]
    other_third = next(
        e for e in body["edges"]
        if {e["source"], e["target"]} == {"src/other_mod.py", "src/third_mod.py"}
    )
    assert other_third["relations"] == ["imports_from"]
    fake_third = next(
        e for e in body["edges"]
        if {e["source"], e["target"]} == {"src/fake_mod.py", "src/third_mod.py"}
    )
    assert fake_third["relations"] == ["shares_data_with"]
    # No edge is ever a concept<->file or concept<->concept pair.
    for e in body["edges"]:
        assert e["source"] in file_paths and e["target"] in file_paths

    # Communities: distinct among rendered FILE nodes only.
    comm_ids = {c["id"] for c in body["communities"]}
    assert comm_ids == {"3", "5", "7"}  # fake_mod+other's 3/5-adjacent + docs' 7
    comm3 = next(c for c in body["communities"] if c["id"] == "3")
    assert comm3 == {"id": "3", "name": "Mod community", "file_count": 1}

    meta = body["meta"]
    assert meta["counts"] == {
        "files": 4,
        "concepts": 2,
        "reference_edges": 3,
        "files_with_references": 3,  # fake_mod, other_mod, third_mod all referenced
        "isolated_files": 1,  # docs/fake-note.md has no file-file edge
        "communities_rendered": 3,
    }
    assert meta["underlying_graph"] == {
        "embedded": False,
        "node_count": 7,
        "edge_count": 5,
        "community_count": 4,
        "note": meta["underlying_graph"]["note"],
    }
    assert "not embedded" in meta["underlying_graph"]["note"]
    assert meta["provenance"]["built_at_commit"] == "fakecommit0000"
    assert meta["provenance"]["provider"] == "local-graph"
    assert meta["provenance"]["integrity"] == "verified"
    # A live graph has no snapshot schema/sha256 — honestly null, never invented.
    assert meta["provenance"]["source_graph_sha256"] is None
    assert meta["provenance"]["snapshot_schema_version"] is None


# --- 1b. relations-set accumulation (direct, provider-agnostic) -------------
# ``LocalGraphArtifactSource`` itself always canonicalizes a tied multi-edge
# between the same file pair down to ONE deterministic winning relation (see
# ``memory._prefer_related``), so it can never exercise the "two DIFFERENT
# relations for the same pair" branch of the projection's own accumulation
# logic. A minimal, directly-controlled MemoryReader double proves that
# branch works: when TWO sides of a pair report different relations (a
# legitimate shape a future provider could produce), the projection merges
# them into one sorted-unique list rather than dropping either.


class _FakeReader:
    """A minimal MemoryReader double — ``overview``/``concepts``/``concept``/
    ``files``/``file``/``classify_path``/``status``/``search`` — used ONLY to
    drive ``build_graph_projection`` directly against a controlled shape."""

    def __init__(self, files, concepts, file_details, status_body):
        self._files = files
        self._concepts = concepts
        self._file_details = file_details
        self._status = status_body

    def overview(self):
        return {
            "available": True,
            "built_at_commit": "fakehead",
            "node_count": 4,
            "edge_count": 1,
            "community_count": 1,
            "concept_count": len(self._concepts),
            "served_file_count": len(self._files),
            "manifest_file_count": len(self._files),
        }

    def concepts(self):
        return [dict(c) for c in self._concepts]

    def concept(self, concept_id):
        return None

    def files(self):
        return [dict(f) for f in self._files]

    def file(self, path):
        detail = self._file_details.get(path)
        return dict(detail) if detail is not None else None

    def classify_path(self, path):
        return "served" if path in self._file_details else "not_indexed"

    def status(self):
        return dict(self._status)

    def search(self, query, limit=10, offset=0):
        return {
            "available": True, "reason": None, "total": 0, "returned": 0,
            "limit": limit, "offset": offset, "results": [],
        }


def test_relations_accumulate_from_both_directions_when_they_differ():
    files = [
        {"path": "a.py", "file_type": "code", "community_id": "1",
         "community_name": "C1", "node_count": 1, "on_disk": False},
        {"path": "b.py", "file_type": "code", "community_id": "1",
         "community_name": "C1", "node_count": 1, "on_disk": False},
    ]
    file_details = {
        "a.py": {
            "path": "a.py", "file_type": "code", "community_id": "1",
            "community_name": "C1", "node_count": 1, "on_disk": False,
            "local_reference": "a.py", "rationales": [],
            "related": {
                "files": [{"path": "b.py", "relation": "imports", "file_type": "code"}],
                "concepts": [],
            },
        },
        "b.py": {
            "path": "b.py", "file_type": "code", "community_id": "1",
            "community_name": "C1", "node_count": 1, "on_disk": False,
            "local_reference": "b.py", "rationales": [],
            # b's OWN view reports a DIFFERENT relation for the SAME pair — a
            # shape the concrete local reader never produces today, but the
            # projection must still merge it honestly, not drop either value.
            "related": {
                "files": [{"path": "a.py", "relation": "calls", "file_type": "code"}],
                "concepts": [],
            },
        },
    }
    status_body = {
        "provider_kind": "fake", "available": True, "integrity": "verified",
        "source_graph_sha256": None, "snapshot_schema_version": None,
    }
    reader = _FakeReader(files, [], file_details, status_body)
    body = memory_graph.build_graph_projection(reader)

    assert len(body["edges"]) == 1
    edge = body["edges"][0]
    assert {edge["source"], edge["target"]} == {"a.py", "b.py"}
    assert edge["relations"] == ["calls", "imports"]


# --- 2. determinism ---------------------------------------------------------


def test_graph_projection_deterministic_across_calls(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    first = client.get("/api/memory/graph").json()
    second = client.get("/api/memory/graph").json()
    assert first == second


def test_build_graph_projection_deterministic_direct(tmp_path):
    from isaac_api.memory import LocalGraphArtifactSource

    art = _write_artifacts(tmp_path)
    reader = LocalGraphArtifactSource(art, repo_root=tmp_path)
    first = memory_graph.build_graph_projection(reader)
    second = memory_graph.build_graph_projection(reader)
    assert first == second


# --- 3. no forbidden verdict keys -------------------------------------------


def test_no_forbidden_keys_anywhere(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    bodies = [client.get("/api/memory/graph").json()]

    empty_dir = tmp_path / "does-not-exist"
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(empty_dir))
    from isaac_api.app import create_app

    degraded_client = TestClient(create_app())
    bodies.append(degraded_client.get("/api/memory/graph").json())

    for body in bodies:
        keys = set(_walk_keys(body))
        assert keys.isdisjoint(FORBIDDEN_KEYS), f"forbidden key found in {body!r}"


# --- 4. edge integrity -------------------------------------------------------


def test_every_edge_endpoint_is_a_known_node(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/graph").json()
    node_ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids
        assert e["source"] != e["target"]


# --- 5. no absolute/~/backslash/secret-shaped value -------------------------


def test_no_absolute_or_unsafe_or_secret_values(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/graph").json()
    for value in _walk_values(body):
        if not isinstance(value, str):
            continue
        assert not value.startswith("/"), value
        assert not value.startswith("~"), value
        assert "\\" not in value, value
        assert "secret" not in value.lower(), value
        assert "password" not in value.lower(), value
        assert "api_key" not in value.lower(), value


# --- 6. governance inheritance -----------------------------------------------


def test_governance_excluded_paths_never_appear(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/graph").json()
    for value in _walk_values(body):
        if isinstance(value, str):
            assert not value.startswith("examples/"), value
    node_ids = {n["id"] for n in body["nodes"]}
    assert "examples/README.md" not in node_ids


# --- 7. missing snapshot / graph -> available:false, HTTP 200 ---------------


def test_graph_absent_available_false_http_200(tmp_path, monkeypatch):
    empty_dir = tmp_path / "graphify-out"  # never created
    client = _client(tmp_path, monkeypatch, empty_dir)
    resp = client.get("/api/memory/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plane"] == "memory"
    assert body["available"] is False
    assert body["reason"] == "graph_absent"
    assert body["truncated"] is False
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["communities"] == []
    assert body["meta"]["counts"] == {
        "files": 0, "concepts": 0, "reference_edges": 0,
        "files_with_references": 0, "isolated_files": 0, "communities_rendered": 0,
    }
    assert body["meta"]["underlying_graph"]["node_count"] is None
    assert body["meta"]["underlying_graph"]["edge_count"] is None
    assert body["meta"]["underlying_graph"]["community_count"] is None
    assert body["meta"]["provenance"]["provider"] == "unavailable"


# --- 8. malformed graph -> graph_unreadable, HTTP 200 -----------------------


def test_graph_malformed_reason_graph_unreadable(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path, graph="{not valid json")
    client = _client(tmp_path, monkeypatch, art)
    resp = client.get("/api/memory/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["reason"] == "graph_unreadable"


# --- 9. unsupported snapshot schema version -> available:false --------------


def test_unsupported_snapshot_schema_version_available_false(tmp_path, monkeypatch):
    fixture = (
        _repo_root() / "tests" / "fixtures" / "memory_snapshot" / "memory-snapshot.json"
    )
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["snapshot_schema_version"] = 999
    bad_snapshot = tmp_path / "bad-snapshot.json"
    bad_snapshot.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(bad_snapshot))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    client = TestClient(create_app())
    resp = client.get("/api/memory/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["nodes"] == []


# --- 10. base path ------------------------------------------------------------


def test_route_lands_under_base_path(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(art))
    monkeypatch.setenv("ISAAC_BASE_PATH", "/krish")
    from isaac_api.app import create_app

    client = TestClient(create_app())
    resp = client.get("/krish/api/memory/graph")
    assert resp.status_code == 200
    assert resp.json()["available"] is True
    # The unprefixed path no longer exists.
    assert client.get("/api/memory/graph").status_code == 404


# --- 11. truth isolation ------------------------------------------------------


def test_memory_graph_module_imports_no_graphify_or_isaac_records():
    import ast

    src_path = _repo_root() / "apps" / "api" / "isaac_api" / "memory_graph.py"
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_roots.add(node.module.split(".")[0])
    assert "graphify" not in imported_roots
    assert "isaac_records" not in imported_roots


# --- 12. bounded (deterministic caps) -----------------------------------------


def _hub_and_spoke_graph(spoke_count: int) -> tuple[dict, dict]:
    """One hub file + ``spoke_count`` leaf files, each leaf connected ONLY to
    the hub (degree 1) so the reader's own per-file MAX_RELATED=25 cap never
    silently drops an edge from the LEAF's side (a degree-1 file's single
    neighbor is always within its own top-25). This lets a single synthetic
    fixture exceed BOTH memory_graph.MAX_NODES and memory_graph.MAX_EDGES at
    once, deterministically, without relying on tie-break behavior."""
    nodes = [{"id": "hub", "label": "hub.py", "file_type": "code", "community": 1,
              "source_file": "src/hub.py", "source_location": "L1"}]
    links = []
    manifest = {"src/hub.py": {"mtime": 1.0, "ast_hash": "fake", "semantic_hash": ""}}
    for i in range(spoke_count):
        path = f"src/leaf_{i:05d}.py"
        nid = f"leaf_{i:05d}"
        nodes.append({"id": nid, "label": f"leaf_{i:05d}.py", "file_type": "code",
                      "community": 1, "source_file": path, "source_location": "L1"})
        links.append({"source": "hub", "target": nid, "relation": "references",
                      "weight": float(i + 1), "source_file": path})
        manifest[path] = {"mtime": 1.0, "ast_hash": "fake", "semantic_hash": ""}
    graph = {"nodes": nodes, "links": links, "built_at_commit": "fakecommitbig"}
    return graph, manifest


def test_over_cap_synthetic_graph_is_truncated(tmp_path, monkeypatch):
    # 2100 spokes -> 2101 file nodes (> MAX_NODES=600) and 2100 edges
    # (> MAX_EDGES=2000), all surfaced via each degree-1 leaf's own view.
    graph, manifest = _hub_and_spoke_graph(2100)
    art = _write_artifacts(tmp_path, graph=graph, manifest=manifest, labels={})
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/graph").json()

    assert body["available"] is True
    assert body["truncated"] is True
    assert len(body["nodes"]) <= memory_graph.MAX_NODES
    assert len(body["edges"]) <= memory_graph.MAX_EDGES
    assert body["meta"]["counts"]["files"] <= memory_graph.MAX_NODES
    assert body["meta"]["counts"]["reference_edges"] <= memory_graph.MAX_EDGES
    # Edge integrity holds even under truncation.
    node_ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids


def test_under_cap_synthetic_graph_is_not_truncated(tmp_path, monkeypatch):
    graph, manifest = _hub_and_spoke_graph(5)
    art = _write_artifacts(tmp_path, graph=graph, manifest=manifest, labels={})
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/memory/graph").json()
    assert body["available"] is True
    assert body["truncated"] is False
    assert len(body["nodes"]) == 6
    assert len(body["edges"]) == 5


# --- 13. no mutation ----------------------------------------------------------


def test_get_mutates_no_file_or_mtime(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    graph_path = art / "graph.json"
    manifest_path = art / "manifest.json"
    before = {
        "graph_mtime": graph_path.stat().st_mtime,
        "manifest_mtime": manifest_path.stat().st_mtime,
        "graph_bytes": graph_path.read_bytes(),
        "manifest_bytes": manifest_path.read_bytes(),
    }
    client = _client(tmp_path, monkeypatch, art)
    for _ in range(3):
        resp = client.get("/api/memory/graph")
        assert resp.status_code == 200
    after = {
        "graph_mtime": graph_path.stat().st_mtime,
        "manifest_mtime": manifest_path.stat().st_mtime,
        "graph_bytes": graph_path.read_bytes(),
        "manifest_bytes": manifest_path.read_bytes(),
    }
    assert before == after


# --- 14. real committed snapshot ----------------------------------------------


def test_real_committed_snapshot_counts(tmp_path, monkeypatch):
    real_snapshot = _repo_root() / "apps" / "api" / "isaac_api" / "data" / "memory-snapshot.json"
    assert real_snapshot.is_file(), "committed snapshot must exist for this test"
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(real_snapshot))
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    client = TestClient(create_app())
    resp = client.get("/api/memory/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["meta"]["counts"]["files"] == 201
    assert body["meta"]["counts"]["concepts"] == 19
    assert body["meta"]["counts"]["reference_edges"] == 508
    assert body["meta"]["underlying_graph"]["node_count"] == 2988
    assert body["meta"]["underlying_graph"]["edge_count"] == 4465
    assert body["meta"]["underlying_graph"]["community_count"] == 257
    assert body["meta"]["underlying_graph"]["embedded"] is False
    assert body["meta"]["provenance"]["source_graph_sha256"] == (
        "0cfccb9f77893363ecfb467e129014d751bf16a76b2b37be990af9f263f4b432"
    )
    assert body["meta"]["provenance"]["snapshot_schema_version"] == 1
    assert body["meta"]["provenance"]["provider"] == "sanitized-snapshot"
    # Every real file node is uniformly not-on-disk (the snapshot bakes this).
    file_nodes = [n for n in body["nodes"] if n["kind"] == "file"]
    assert len(file_nodes) == 201
    assert all(n["on_disk"] is False for n in file_nodes)
    concept_nodes = [n for n in body["nodes"] if n["kind"] == "concept"]
    assert len(concept_nodes) == 19
    # The five real relation values appear (ground truth), never collapsed.
    all_relations = {r for e in body["edges"] for r in e["relations"]}
    assert all_relations == {
        "references", "imports", "calls", "imports_from", "shares_data_with",
    }
    assert body["truncated"] is False  # 220ish nodes / 508 edges, well under caps

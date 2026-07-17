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
    art = _write_artifacts(tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/graph/status").json()
    assert body["status"] in {"fresh", "stale", "missing"}
    assert body["plane"] == "memory"
    assert body["built_at_commit"] == "fakecommit0000"
    assert body["node_count"] == 5
    assert body["edge_count"] == 3
    assert body["community_count"] == 4  # distinct communities {7,9,3,5}
    assert body["concept_count"] == 2
    assert body["file_count"] == 3  # served allowlist count (examples/ excluded)
    assert isinstance(body["graph_mtime"], float)


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
    # Also point REPO_ROOT (the freshness check's source anchor) at the same
    # empty tmp tree so `status` itself is deterministically "missing" in this
    # test, matching the additive-fields-absent case exactly. Scoped to this
    # single test function; no other handler is exercised here.
    monkeypatch.setattr("isaac_api.routes.REPO_ROOT", tmp_path)
    client = _client(tmp_path, monkeypatch, memory_dir)
    body = client.get("/api/graph/status").json()
    assert body["status"] == "missing"
    for key in ("built_at_commit", "node_count", "edge_count",
                "community_count", "file_count", "concept_count", "graph_mtime"):
        assert body[key] is None


def test_graph_status_single_source_when_env_overrides(tmp_path, monkeypatch):
    """ISAAC_MEMORY_DIR points at a populated graph while the repo-local
    graphify-out is guaranteed absent (REPO_ROOT patched to an empty tmp tree,
    as in the missing-test above): `status` and the additive counts must
    describe the SAME graph — never a self-contradictory body reading
    status:"missing" alongside populated counts (the documented future
    mounted-volume case)."""
    art = _write_artifacts(tmp_path / "volume")
    empty_root = tmp_path / "empty-repo"
    empty_root.mkdir()
    monkeypatch.setattr("isaac_api.routes.REPO_ROOT", empty_root)
    client = _client(tmp_path, monkeypatch, art)
    body = client.get("/api/graph/status").json()
    # Counts describe the env-pointed graph...
    assert body["built_at_commit"] == "fakecommit0000"
    assert body["node_count"] == 5
    # ...and status must describe that same graph, so it cannot be "missing".
    assert body["status"] != "missing"
    # Pin the honest value: the env-pointed graph file exists, and no tracked
    # source under the (empty) root is newer than it -> "fresh".
    assert body["status"] == "fresh"


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
    """P24.6 Item 2 (coverage): pin ``/api/graph/status`` when ``graph.json``
    EXISTS but is malformed. The shape must be internally coherent and
    non-crashing: status is decided by mtime (the file is present) so it is
    ``fresh``/``stale`` — never ``missing`` and never a 500 — while every
    additive count is ``null`` (a malformed graph yields no honest counts, so
    there is no populated-count + parse-failure contradiction). The memory
    envelope stays intact.

    REPO_ROOT (the freshness check's tracked-source anchor) is patched to the
    empty tmp tree so ``status`` is deterministic and independent of the
    developer's working tree; the graph FILE stays anchored at the malformed
    ISAAC_MEMORY_DIR artifact.
    """
    art = _write_artifacts(tmp_path, graph="{not valid json")
    monkeypatch.setattr("isaac_api.routes.REPO_ROOT", tmp_path)
    client = _client(tmp_path, monkeypatch, art)
    resp = client.get("/api/graph/status")
    assert resp.status_code == 200  # never 500
    body = resp.json()
    assert body["status"] in {"fresh", "stale"}  # file exists -> mtime-based
    for key in ("node_count", "edge_count", "community_count", "file_count",
                "concept_count", "built_at_commit", "graph_mtime"):
        assert body[key] is None
    assert body["plane"] == "memory"
    assert "note" in body and body["note"]


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
    """Mirrors the existing (untouched) test_graph_status assertions exactly."""
    client = _client(tmp_path, monkeypatch)
    body = client.get("/api/graph/status").json()
    assert body["status"] in {"fresh", "stale", "missing"}
    assert body["plane"] == "memory"
    assert "never a validator" in body["note"]

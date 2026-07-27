"""Tests for ``GET /api/memory/graph/detail`` — the deep (symbol-level) Project
Memory graph layer — and the pure functions behind it
(``isaac_api.memory_graph.build_graph_detail`` and
``isaac_api.memory.GraphDetailSource``).

Conventions mirror ``test_memory_graph.py``: a real FastAPI ``TestClient``, an
unmistakably-fake synthetic artifact for every behavioural/negative case, plus
integration checks against the REAL committed pair
(``apps/api/isaac_api/data/memory-snapshot.json`` +
``apps/api/isaac_api/data/memory-graph-detail.json``) for the documented counts,
the honesty contract, and the data-safety gate.

Four things this file deliberately proves, because they are the properties that
make the surface publishable at all:

1. **Honesty.** The deep layer is a point-in-time index of ``built_at_commit``,
   which is generally NOT the current repository head. ``is_point_in_time`` /
   ``describes_current_head`` are asserted explicitly — they are the contract
   that stops a 2,612-node symbol map from reading as a map of today's code.
2. **No dangling edge.** Node capping is a sorted PREFIX, so out-of-range edges
   must be dropped BEFORE the edge cap is applied. Proven with a synthetic
   over-cap fixture that would produce dangling edges under the wrong ordering,
   not merely with the (uncapped) real artifact.
3. **Data safety.** Every node's ``source_file`` is inside the committed
   snapshot's served-content manifest; no absolute local path, URL, or
   credential-shaped string appears anywhere.
4. **Isolation.** No runtime Graphify service and no truth-core import: the deep
   layer serves from one committed file, and is available even when no Graphify
   artifact directory exists at all.
"""

from __future__ import annotations

import ast
import copy
import json
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api import memory, memory_graph

FORBIDDEN_KEYS = {"ok", "valid", "passed", "verdict", "schema", "errors"}
NOTE_FRAGMENT = "leads to verify"

#: The full relation vocabulary the committed artifact carries. Asserted as an
#: EXACT set: a value disappearing means the artifact lost real structure, and a
#: value appearing means something invented a relation the source graph never
#: recorded.
REAL_RELATIONS = {
    "contains", "calls", "imports", "imports_from", "references", "rationale_for",
    "method", "indirect_call", "re_exports", "uses", "inherits", "shares_data_with",
}

#: Documented real counts of the committed deep artifact.
REAL_NODES = 2612
REAL_EDGES = 4067
REAL_COMMUNITIES = 221


def _repo_root() -> Path:
    """Walk up until the vendored official schema is found (mirrors memory.py)."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    return here.parents[3]


REPO_ROOT = _repo_root()
REAL_SNAPSHOT = REPO_ROOT / "apps" / "api" / "isaac_api" / "data" / "memory-snapshot.json"
REAL_DETAIL = REPO_ROOT / "apps" / "api" / "isaac_api" / "data" / "memory-graph-detail.json"
FIXTURE_GRAPH_DIR = REPO_ROOT / "tests" / "fixtures" / "memory_snapshot" / "graph"
SOURCE_GRAPH_DIR = REPO_ROOT / "graphify-out"


@pytest.fixture(autouse=True)
def _reset_detail_memo(monkeypatch):
    """``isaac_api.memory`` memoizes the default detail source process-wide (it
    is rebuilt only when the resolved PATH changes). Reset it per test so no
    test can inherit another's cached source — the same hygiene
    ``conftest.py`` applies to ``_default_reader``."""
    monkeypatch.setattr(memory, "_default_detail_source", None)
    monkeypatch.setattr(memory, "_default_detail_path", None)


# --- synthetic artifact builders (unmistakably fake) --------------------------


def _valid_detail_artifact() -> dict:
    """A minimal but STRUCTURALLY VALID synthetic deep artifact.

    Every degraded-case test below mutates one field of this dict, and
    ``test_synthetic_artifact_is_a_positive_control`` proves the unmutated
    version really is served as ``available: true`` — so a degraded assertion
    can never pass vacuously because the helper itself was malformed.
    """
    nodes = [
        # id, label, file_type, source_file, source_location, community_id
        ["fake_doc_notes", "fake_notes.md", "document", "docs/fake_notes.md", "L1", "1"],
        ["fake_doc_notes_intro", "Intro", "document", "docs/fake_notes.md", "L4", "1"],
        ["fake_mod", "fake_widget.py", "code", "src/fake_widget.py", "L1", "2"],
        ["fake_mod_render", "render", "code", "src/fake_widget.py", "L12", "2"],
    ]
    edges = [
        [0, 1, "contains"],
        [2, 3, "contains"],
        [3, 0, "references"],
    ]
    return {
        "kind": "isaac-memory-graph-detail",
        "detail_schema_version": 1,
        "generator": "scripts/build_memory_snapshot.py",
        "built_at_commit": "fakedetailcommit0000",
        "source_graph_sha256": "f" * 64,
        "policy_fingerprint": "a" * 64,
        "structural_scope": "point_in_time_source_graph",
        "structural_basis": "graphify_index_at_built_at_commit",
        "served_file_count": 2,
        "served_path_set_fingerprint": memory.compute_served_path_set_fingerprint(
            ["docs/fake_notes.md", "src/fake_widget.py"]
        ),
        "encoding": {"nodes": "fake", "edges": "fake", "community_names": "fake"},
        "node_keys": ["id", "label", "file_type", "source_file", "source_location",
                      "community_id"],
        "edge_keys": ["source_index", "target_index", "relation"],
        "nodes": nodes,
        "edges": edges,
        "community_names": {"1": "Fake docs community", "2": "Fake code community"},
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "communities": 2,
            "file_types": {"code": 2, "document": 2},
            "relations": {"contains": 2, "references": 1},
        },
    }


def _write_detail(tmp_path: Path, artifact, name="fake-graph-detail.json") -> Path:
    path = tmp_path / name
    text = artifact if isinstance(artifact, str) else json.dumps(artifact)
    path.write_text(text, encoding="utf-8")
    return path


def _client(tmp_path, monkeypatch, *, detail_path=None, memory_dir=None,
            snapshot=None, base_path=None) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    if detail_path is not None:
        monkeypatch.setenv("ISAAC_MEMORY_GRAPH_DETAIL", str(detail_path))
    if memory_dir is not None:
        monkeypatch.setenv("ISAAC_MEMORY_DIR", str(memory_dir))
    if snapshot is not None:
        monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(snapshot))
    if base_path is not None:
        monkeypatch.setenv("ISAAC_BASE_PATH", base_path)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _real_client(tmp_path, monkeypatch) -> TestClient:
    """A client driving BOTH real committed artifacts (snapshot + deep layer)."""
    assert REAL_SNAPSHOT.is_file(), "committed snapshot must exist for this test"
    assert REAL_DETAIL.is_file(), "committed graph-detail artifact must exist"
    return _client(tmp_path, monkeypatch, detail_path=REAL_DETAIL, snapshot=REAL_SNAPSHOT)


def _walk(obj):
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


def _walk_strings(obj):
    """Every string anywhere in a nested structure, including bare list items
    (the deep layer's nodes/edges are positional ROWS, so a plain
    key/value walk would miss most of the payload)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_strings(item)
    elif isinstance(obj, str):
        yield obj


def _payload_strings(body: dict):
    """Only the graph PAYLOAD's strings — nodes, edges, community names. Used by
    the long-hex-digest scan, which must not fire on the provenance block, where
    a 40/64-char hex digest (``built_at_commit``, ``source_graph_sha256``,
    ``policy_fingerprint``, ``served_path_set_fingerprint``) is the legitimate,
    intended content."""
    for row in body["nodes"]:
        yield from _walk_strings(row)
    for row in body["edges"]:
        yield from _walk_strings(row)
    for cid, name in body["community_names"].items():
        yield cid
        if isinstance(name, str):
            yield name


# =============================================================================
# 1. route behaviour
# =============================================================================


def test_synthetic_artifact_is_a_positive_control(tmp_path, monkeypatch):
    """Guards every degraded test below: the UNMUTATED synthetic artifact is
    served as available, so a later ``available is False`` assertion proves the
    mutation caused the degradation."""
    path = _write_detail(tmp_path, _valid_detail_artifact())
    client = _client(tmp_path, monkeypatch, detail_path=path)
    body = client.get("/api/memory/graph/detail").json()
    assert body["available"] is True
    assert body["integrity"] == "verified"
    assert len(body["nodes"]) == 4
    assert len(body["edges"]) == 3


def test_detail_route_returns_200_and_a_well_formed_envelope(tmp_path, monkeypatch):
    client = _real_client(tmp_path, monkeypatch)
    resp = client.get("/api/memory/graph/detail")
    assert resp.status_code == 200
    body = resp.json()

    assert set(body) == {
        "plane", "note", "available", "reason", "integrity", "truncated",
        "node_keys", "edge_keys", "nodes", "edges", "community_names",
        "encoding", "meta",
    }
    assert body["plane"] == "memory"
    assert NOTE_FRAGMENT in body["note"]
    assert body["available"] is True
    assert body["reason"] is None
    assert body["integrity"] == "verified"
    assert body["truncated"] is False
    assert body["node_keys"] == ["id", "label", "file_type", "source_file",
                                 "source_location", "community_id"]
    assert body["edge_keys"] == ["source_index", "target_index", "relation"]
    assert set(body["encoding"]) == {"nodes", "edges", "community_names"}
    assert set(body["meta"]) == {"counts", "provenance"}

    # Every node row matches node_keys positionally, with real typed values.
    for row in body["nodes"]:
        assert isinstance(row, list) and len(row) == len(body["node_keys"])
        node_id, label, file_type, source_file, location, community_id = row
        assert isinstance(node_id, str) and node_id
        assert isinstance(source_file, str) and source_file
        for optional in (label, file_type, location, community_id):
            assert optional is None or isinstance(optional, str)
    for row in body["edges"]:
        assert isinstance(row, list) and len(row) == len(body["edge_keys"])
        source_index, target_index, relation = row
        assert isinstance(source_index, int) and not isinstance(source_index, bool)
        assert isinstance(target_index, int) and not isinstance(target_index, bool)
        assert isinstance(relation, str) and relation


@pytest.mark.parametrize(
    "mutate, expected_reason, expected_integrity",
    [
        pytest.param(None, "detail_absent", "unknown", id="absent"),
        pytest.param("wrong-kind", "detail_unreadable", "malformed", id="wrong_kind"),
        pytest.param("bad-version", "detail_unreadable", "unsupported",
                     id="wrong_schema_version"),
        pytest.param("missing-key", "detail_unreadable", "malformed",
                     id="missing_required_key"),
        pytest.param("malformed-json", "detail_unreadable", "malformed",
                     id="malformed_json"),
        pytest.param("null-provenance", "detail_unreadable", "malformed",
                     id="null_provenance"),
    ],
)
def test_unreadable_artifact_degrades_honestly(tmp_path, monkeypatch, mutate,
                                               expected_reason, expected_integrity):
    """Every failure mode yields the SAME honest envelope: HTTP 200,
    ``available: false``, zero nodes and zero edges (never a fabricated graph),
    and a provenance block collapsed to nulls rather than to plausible
    defaults."""
    if mutate is None:
        path = tmp_path / "never-created-graph-detail.json"
    elif mutate == "malformed-json":
        path = _write_detail(tmp_path, "{not valid json")
    else:
        artifact = _valid_detail_artifact()
        if mutate == "wrong-kind":
            artifact["kind"] = "something-else"
        elif mutate == "bad-version":
            artifact["detail_schema_version"] = 999
        elif mutate == "missing-key":
            del artifact["counts"]
        elif mutate == "null-provenance":
            artifact["built_at_commit"] = None
        path = _write_detail(tmp_path, artifact)

    client = _client(tmp_path, monkeypatch, detail_path=path)
    resp = client.get("/api/memory/graph/detail")
    assert resp.status_code == 200
    body = resp.json()

    assert body["plane"] == "memory"
    assert NOTE_FRAGMENT in body["note"]
    assert body["available"] is False
    assert body["reason"] == expected_reason
    assert body["integrity"] == expected_integrity
    assert body["truncated"] is False
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["node_keys"] == []
    assert body["edge_keys"] == []
    assert body["community_names"] == {}
    assert body["encoding"] == {}
    assert body["meta"]["counts"] == {
        "nodes": 0, "edges": 0, "communities": 0, "file_types": {}, "relations": {},
    }

    provenance = body["meta"]["provenance"]
    for nulled in ("built_at_commit", "source_graph_sha256", "detail_schema_version",
                   "generator", "policy_fingerprint", "structural_scope",
                   "structural_basis", "served_file_count",
                   "served_path_set_fingerprint"):
        assert provenance[nulled] is None, f"{nulled} was defaulted, not nulled"
    assert provenance["served_set_consistency"] == "unknown"
    # The honesty flags survive degradation — an empty graph is still not a map
    # of the current head.
    assert provenance["is_point_in_time"] is True
    assert provenance["describes_current_head"] is False


def test_base_graph_projection_is_unchanged_by_the_new_endpoint(tmp_path, monkeypatch):
    """The base 220-node projection's response must stay byte-compatible: the
    deep layer is a SEPARATE endpoint, never folded in. Asserted three ways —
    the exact top-level key set, the documented counts, and byte-for-byte
    equality of the base response before and after the deep endpoint is
    called."""
    client = _real_client(tmp_path, monkeypatch)
    before = client.get("/api/memory/graph")
    assert before.status_code == 200
    base = before.json()

    assert set(base) == {
        "plane", "note", "available", "truncated", "nodes", "edges",
        "communities", "meta",
    }
    assert base["meta"]["counts"] == {
        "files": 201,
        "concepts": 19,
        "reference_edges": 508,
        "files_with_references": base["meta"]["counts"]["files_with_references"],
        "isolated_files": base["meta"]["counts"]["isolated_files"],
        "communities_rendered": base["meta"]["counts"]["communities_rendered"],
    }
    assert len(base["nodes"]) == 220
    assert len(base["edges"]) == 508
    # None of the deep layer's own keys leaked into the base response.
    base_keys = set(_walk_keys(base))
    assert base_keys.isdisjoint({"node_keys", "edge_keys", "community_names",
                                 "encoding", "is_point_in_time",
                                 "describes_current_head"})

    assert client.get("/api/memory/graph/detail").status_code == 200
    after = client.get("/api/memory/graph")
    assert after.content == before.content


def test_new_route_is_published_in_openapi_with_its_metadata(tmp_path, monkeypatch):
    client = _real_client(tmp_path, monkeypatch)
    schema = client.get("/api/openapi").json()
    operation = schema["paths"]["/api/memory/graph/detail"]["get"]

    assert operation["tags"] == schema["paths"]["/api/memory/graph"]["get"]["tags"]
    assert operation["tags"] == ["Graph"]
    assert operation["summary"] == (
        "Get the Symbol-Level Project Memory Graph Structure"
    )
    description = operation["description"]
    # The four honesty claims the description is required to make.
    assert "point-in-time" in description
    assert "built_at_commit" in description
    assert "served files only" in description
    assert "leads to verify, never a verdict" in description
    assert "available: false" in description
    assert operation["responses"]["200"]["description"].strip() not in (
        "", "Successful Response",
    )
    assert sorted(operation["responses"]) == ["200", "401"]


def test_route_lands_under_the_configured_base_path(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, detail_path=REAL_DETAIL,
                     snapshot=REAL_SNAPSHOT, base_path="/krish")
    resp = client.get("/krish/api/memory/graph/detail")
    assert resp.status_code == 200
    assert resp.json()["available"] is True
    # The unprefixed path no longer exists.
    assert client.get("/api/memory/graph/detail").status_code == 404


def test_no_forbidden_verdict_key_anywhere(tmp_path, monkeypatch):
    """Project Memory computes no verdict: no key anywhere in either the
    available or the degraded envelope may be a verdict/truth key."""
    bodies = [_real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()]
    absent = _client(tmp_path, monkeypatch,
                     detail_path=tmp_path / "nope.json")
    bodies.append(absent.get("/api/memory/graph/detail").json())
    for body in bodies:
        keys = set(_walk_keys(body))
        assert keys.isdisjoint(FORBIDDEN_KEYS), f"forbidden key in {sorted(keys)}"


def test_route_is_deterministic_and_mutates_nothing(tmp_path, monkeypatch):
    before_bytes = REAL_DETAIL.read_bytes()
    before_mtime = REAL_DETAIL.stat().st_mtime
    client = _real_client(tmp_path, monkeypatch)
    first = client.get("/api/memory/graph/detail")
    second = client.get("/api/memory/graph/detail")
    assert first.content == second.content
    assert REAL_DETAIL.read_bytes() == before_bytes
    assert REAL_DETAIL.stat().st_mtime == before_mtime


# =============================================================================
# 2. data integrity and honesty
# =============================================================================


def test_real_artifact_counts_are_reported_exactly(tmp_path, monkeypatch):
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    assert len(body["nodes"]) == REAL_NODES
    assert len(body["edges"]) == REAL_EDGES
    assert len(body["community_names"]) == REAL_COMMUNITIES
    counts = body["meta"]["counts"]
    assert counts["nodes"] == REAL_NODES
    assert counts["edges"] == REAL_EDGES
    assert counts["communities"] == REAL_COMMUNITIES
    # The reported counts are the rendered counts, not an independent claim.
    assert counts["nodes"] == len(body["nodes"])
    assert counts["edges"] == len(body["edges"])
    assert counts["communities"] == len(body["community_names"])
    assert sum(counts["file_types"].values()) == REAL_NODES
    assert sum(counts["relations"].values()) == REAL_EDGES
    assert counts["file_types"] == {
        "code": 1697, "concept": 18, "document": 691, "rationale": 206,
    }


def test_no_dangling_edge_in_the_real_response(tmp_path, monkeypatch):
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    node_count = len(body["nodes"])
    for source_index, target_index, _relation in body["edges"]:
        assert 0 <= source_index < node_count
        assert 0 <= target_index < node_count


def test_every_community_id_on_a_node_has_a_name_entry(tmp_path, monkeypatch):
    """A node's ``community_id`` must resolve in ``community_names`` — otherwise
    a renderer would have to invent a cluster label."""
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    used = {row[5] for row in body["nodes"] if row[5] is not None}
    assert used
    assert used <= set(body["community_names"])


def test_relation_types_are_exactly_the_artifacts_own_set(tmp_path, monkeypatch):
    """Preserved verbatim and none invented: an EXACT set comparison, so a lost
    relation type fails just as loudly as a fabricated one."""
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    assert {row[2] for row in body["edges"]} == REAL_RELATIONS
    assert set(body["meta"]["counts"]["relations"]) == REAL_RELATIONS
    artifact = json.loads(REAL_DETAIL.read_text(encoding="utf-8"))
    assert {row[2] for row in artifact["edges"]} == REAL_RELATIONS


def test_provenance_states_the_point_in_time_honesty_contract(tmp_path, monkeypatch):
    """The two flags a consumer branches on without parsing prose. These are
    the contract that stops a symbol-level map from reading as current code."""
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    provenance = body["meta"]["provenance"]
    assert provenance["is_point_in_time"] is True
    assert provenance["describes_current_head"] is False
    assert provenance["structural_scope"] == "point_in_time_source_graph"
    assert provenance["structural_basis"] == "graphify_index_at_built_at_commit"
    # Content freshness and structural freshness are named as separate axes.
    assert provenance["served_content_scope"] == "served_files_only"
    assert provenance["served_content_basis"] == "ci_content_manifest"
    assert "separate axes" in provenance["note"]
    # ...and the response's own note repeats it in prose.
    assert "point-in-time" in body["note"]
    assert "not a map of the current repository HEAD" in body["note"]


def test_built_at_commit_is_reported_not_defaulted_or_hidden(tmp_path, monkeypatch):
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    provenance = body["meta"]["provenance"]
    artifact = json.loads(REAL_DETAIL.read_text(encoding="utf-8"))
    assert provenance["built_at_commit"] == artifact["built_at_commit"]
    assert re.fullmatch(r"[0-9a-f]{40}", provenance["built_at_commit"])
    assert provenance["source_graph_sha256"] == artifact["source_graph_sha256"]
    assert provenance["detail_schema_version"] == 1
    assert provenance["generator"] == "scripts/build_memory_snapshot.py"
    assert provenance["policy_fingerprint"] == artifact["policy_fingerprint"]


def test_served_set_consistency_is_current_for_the_committed_pair(tmp_path, monkeypatch):
    """The deep layer and the committed snapshot describe the same served PATH
    set, proven at runtime by recomputing the fingerprint from the reader's own
    file list — not asserted from prose."""
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    provenance = body["meta"]["provenance"]
    assert provenance["served_set_consistency"] == "current"
    assert provenance["snapshot_provider"] == "sanitized-snapshot"
    assert provenance["snapshot_built_at_commit"] == provenance["built_at_commit"]
    assert provenance["served_file_count"] == 201


def test_served_set_consistency_reports_stale_for_a_mismatched_reader(tmp_path,
                                                                     monkeypatch):
    """The check can actually fail: a reader describing a DIFFERENT served path
    set than the deep artifact must be reported ``stale``, never ``current``.
    Drives the real committed artifact against the small synthetic snapshot
    fixture."""
    fixture_snapshot = (
        REPO_ROOT / "tests" / "fixtures" / "memory_snapshot" / "memory-snapshot.json"
    )
    assert fixture_snapshot.is_file()
    client = _client(tmp_path, monkeypatch, detail_path=REAL_DETAIL,
                     snapshot=fixture_snapshot)
    body = client.get("/api/memory/graph/detail").json()
    assert body["available"] is True
    assert body["meta"]["provenance"]["served_set_consistency"] == "stale"


def test_served_set_consistency_is_unknown_without_a_readable_reader(tmp_path,
                                                                     monkeypatch):
    """No memory reader at all: the deep layer is still served (it needs only
    its own committed file), and the path-set comparison honestly reports
    ``unknown`` rather than claiming ``current``."""
    client = _client(tmp_path, monkeypatch, detail_path=REAL_DETAIL,
                     memory_dir=tmp_path / "no-such-graph-dir")
    body = client.get("/api/memory/graph/detail").json()
    assert body["available"] is True
    assert body["meta"]["provenance"]["served_set_consistency"] == "unknown"
    assert body["meta"]["provenance"]["snapshot_provider"] == "local-graph"


# --- the dangling-edge / cap-ordering invariant -------------------------------
#
# The real artifact is far under both caps, so it can never exercise capping.
# These tests drive ``build_graph_detail`` directly against synthetic OVER-CAP
# artifacts, using the REAL ``DETAIL_MAX_NODES`` / ``DETAIL_MAX_EDGES`` values
# (no monkeypatched caps), because the ORDER the two caps are applied in is the
# thing under test.


class _FakeDetailSource:
    """A ``memory.GraphDetailSource`` double returning a controlled artifact."""

    def __init__(self, data, *, available=True, reason=None, integrity="verified"):
        self._payload = {
            "available": available,
            "reason": reason,
            "integrity": integrity,
            "detail_schema_version": 1,
            "data": data,
        }

    def detail(self):
        return dict(self._payload)


class _FakeReader:
    """A minimal ``MemoryReader`` double: only ``status``/``files`` are used by
    the deep layer."""

    def __init__(self, paths=()):
        self._paths = list(paths)

    def status(self):
        return {"provider_kind": "fake", "available": True,
                "source_graph_commit": "fakehead"}

    def files(self):
        return [{"path": p} for p in self._paths]


def _synthetic_over_cap_artifact(node_count, edge_rows) -> dict:
    nodes = [
        [f"fake_node_{i:06d}", f"sym_{i}", "code", f"src/fake_{i % 7}.py", f"L{i}",
         str(i % 5)]
        for i in range(node_count)
    ]
    return {
        "node_keys": ["id", "label", "file_type", "source_file", "source_location",
                      "community_id"],
        "edge_keys": ["source_index", "target_index", "relation"],
        "nodes": nodes,
        "edges": edge_rows,
        "community_names": {str(c): f"Fake community {c}" for c in range(5)},
        "encoding": {"nodes": "fake", "edges": "fake", "community_names": "fake"},
        "built_at_commit": "fakeovercapcommit",
        "source_graph_sha256": "b" * 64,
        "policy_fingerprint": "c" * 64,
        "structural_scope": "point_in_time_source_graph",
        "structural_basis": "graphify_index_at_built_at_commit",
        "generator": "scripts/build_memory_snapshot.py",
        "served_file_count": 7,
        "served_path_set_fingerprint": "d" * 64,
        # A deliberately WRONG full-artifact count block: a truncated response
        # must report what it rendered, never these numbers.
        "counts": {"nodes": node_count, "edges": len(edge_rows), "communities": 5,
                   "file_types": {"code": node_count},
                   "relations": {"contains": len(edge_rows)}},
    }


def test_node_cap_drops_out_of_range_edges_before_the_edge_cap_applies():
    """The invariant that makes the prefix cap safe.

    The fixture is built so the WRONG ordering is detectable: the first 60,000
    edges (exactly ``DETAIL_MAX_EDGES``) all point at nodes BEYOND the node cap,
    and only the last five are in range. If the edge cap were applied first, the
    response would keep 60,000 edges every one of which dangles. Correct
    ordering drops the out-of-range edges first, leaving five valid edges and no
    edge truncation at all.
    """
    over = memory_graph.DETAIL_MAX_NODES + 50
    beyond = memory_graph.DETAIL_MAX_NODES  # first index that must not survive
    out_of_range = [
        [beyond + (i % 50), beyond + ((i + 1) % 50), "contains"]
        for i in range(memory_graph.DETAIL_MAX_EDGES)
    ]
    in_range = [[i, i + 1, "calls"] for i in range(5)]
    artifact = _synthetic_over_cap_artifact(over, out_of_range + in_range)

    body = memory_graph.build_graph_detail(_FakeDetailSource(artifact), _FakeReader())

    assert body["available"] is True
    assert body["truncated"] is True
    assert len(body["nodes"]) == memory_graph.DETAIL_MAX_NODES
    assert body["edges"] == in_range, (
        "out-of-range edges must be dropped BEFORE the edge cap is applied"
    )
    node_count = len(body["nodes"])
    for source_index, target_index, _relation in body["edges"]:
        assert 0 <= source_index < node_count
        assert 0 <= target_index < node_count
    # Surviving nodes are the deterministic sorted PREFIX of the artifact's own
    # order, so the 0-based edge indices stay meaningful.
    assert body["nodes"] == artifact["nodes"][:memory_graph.DETAIL_MAX_NODES]


def test_truncated_response_reports_rendered_counts_not_the_artifact_counts():
    over = memory_graph.DETAIL_MAX_NODES + 50
    edges = [[i, i + 1, "contains"] for i in range(10)]
    artifact = _synthetic_over_cap_artifact(over, edges)
    body = memory_graph.build_graph_detail(_FakeDetailSource(artifact), _FakeReader())

    counts = body["meta"]["counts"]
    assert body["truncated"] is True
    assert counts["nodes"] == memory_graph.DETAIL_MAX_NODES != over
    assert counts["edges"] == len(body["edges"])
    assert counts["file_types"] == {"code": memory_graph.DETAIL_MAX_NODES}
    assert counts["relations"] == {"contains": len(body["edges"])}
    # The artifact's own (larger) node count is NOT echoed.
    assert counts["nodes"] != artifact["counts"]["nodes"]


def test_edge_cap_is_applied_when_only_edges_exceed_their_cap():
    """The edge cap is not dead code: with nodes under their cap, an
    over-cap in-range edge list is truncated to exactly ``DETAIL_MAX_EDGES``
    and still carries no dangling endpoint."""
    edges = [[i % 10, (i + 1) % 10, "contains"]
             for i in range(memory_graph.DETAIL_MAX_EDGES + 5)]
    artifact = _synthetic_over_cap_artifact(10, edges)
    body = memory_graph.build_graph_detail(_FakeDetailSource(artifact), _FakeReader())

    assert body["truncated"] is True
    assert len(body["nodes"]) == 10
    assert len(body["edges"]) == memory_graph.DETAIL_MAX_EDGES
    for source_index, target_index, _relation in body["edges"]:
        assert 0 <= source_index < 10
        assert 0 <= target_index < 10


def test_under_cap_synthetic_artifact_is_not_truncated():
    edges = [[0, 1, "contains"], [1, 2, "calls"]]
    artifact = _synthetic_over_cap_artifact(3, edges)
    body = memory_graph.build_graph_detail(_FakeDetailSource(artifact), _FakeReader())
    assert body["truncated"] is False
    assert len(body["nodes"]) == 3
    assert body["edges"] == edges


def _counts_inflated_artifact() -> dict:
    """A structurally VALID artifact whose ``counts`` block claims a graph
    hundreds of thousands of times larger than the rows it carries."""
    artifact = _valid_detail_artifact()
    artifact["counts"] = {
        "nodes": 999999999,
        "edges": 888888888,
        "communities": 777777777,
        "file_types": {"fabricated": 999999999},
        "relations": {"fabricated": 888888888},
    }
    return artifact


def test_counts_cannot_overstate_an_untruncated_response():
    """The NON-truncated branch used to echo ``counts`` straight from the
    artifact, so an artifact claiming 999,999,999 nodes was served as
    ``available: true`` / ``integrity: "verified"`` / ``truncated: false`` with
    ``meta.counts.nodes == 999999999`` beside four actual node rows.

    Nothing in ``GraphDetailSource._derive`` cross-checks ``counts`` against
    ``len(nodes)``/``len(edges)`` — it validates rows and edge endpoints only —
    so the previous test that the real artifact's counts are exact passed purely
    because the committed artifact happens to be self-consistent. This asserts
    the property itself: the response cannot state a number its payload does not
    support.
    """
    artifact = _counts_inflated_artifact()
    body = memory_graph.build_graph_detail(_FakeDetailSource(artifact), _FakeReader())

    assert body["available"] is True
    assert body["truncated"] is False
    counts = body["meta"]["counts"]
    assert counts["nodes"] == len(body["nodes"]) == 4
    assert counts["edges"] == len(body["edges"]) == 3
    assert counts["nodes"] != artifact["counts"]["nodes"]
    assert counts["edges"] != artifact["counts"]["edges"]
    assert counts["communities"] != artifact["counts"]["communities"]
    # The fabricated histogram keys are not echoed either — the histograms are
    # recomputed from the rendered rows.
    assert "fabricated" not in counts["file_types"]
    assert "fabricated" not in counts["relations"]
    assert sum(counts["file_types"].values()) == len(body["nodes"])
    assert sum(counts["relations"].values()) == len(body["edges"])


def test_counts_cannot_overstate_end_to_end_through_the_route(tmp_path, monkeypatch):
    """The same property through the real seam: a counts-inflated artifact on
    disk, loaded by the real ``GraphDetailSource``, served by the real route.

    Also records WHERE the defence lives: ``_derive`` still ACCEPTS this artifact
    (``available: true``), because a self-inconsistent counts block is not a
    reason to withhold rows that are individually valid. Honesty is restored by
    recomputation in the response, and a counts/length mismatch in the COMMITTED
    artifact is caught separately at build time by the generator's
    ``_validate_detail_shape`` (see
    ``test_committed_artifact_passes_the_generators_own_gates``).
    """
    path = _write_detail(tmp_path, _counts_inflated_artifact())
    client = _client(tmp_path, monkeypatch, detail_path=path)
    body = client.get("/api/memory/graph/detail").json()

    assert body["available"] is True
    assert body["integrity"] == "verified"
    counts = body["meta"]["counts"]
    assert counts["nodes"] == len(body["nodes"]) == 4
    assert counts["edges"] == len(body["edges"]) == 3
    assert 999999999 not in counts.values()
    # And the generator would have REFUSED to write it in the first place.
    generator = _load_generator()
    issues = generator._validate_detail_shape(_counts_inflated_artifact())
    assert any("counts.nodes must equal len(nodes)" in issue for issue in issues), issues


def test_response_containers_do_not_alias_the_cached_artifact(tmp_path):
    """M5: the response's own lists/dicts are rebuilt, so a caller mutating them
    cannot corrupt the process-wide parsed-artifact cache.

    The ROWS are still shared by design (a per-request deep copy of ~6.7k rows
    would be pure waste); that residual is the documented read-only contract, and
    this test pins the part that IS enforced.
    """
    source = memory.GraphDetailSource(_write_detail(tmp_path, _valid_detail_artifact()))
    reader = _FakeReader()
    body = memory_graph.build_graph_detail(source, reader)
    cached = source.detail()["data"]

    assert body["nodes"] == cached["nodes"]
    assert body["nodes"] is not cached["nodes"]
    assert body["edges"] is not cached["edges"]
    assert body["community_names"] is not cached["community_names"]
    assert body["encoding"] is not cached["encoding"]

    # Hostile in-place container mutation of the response...
    body["nodes"].clear()
    body["edges"].append([0, 0, "fabricated"])
    body["community_names"]["999"] = "fabricated community"
    body["encoding"]["nodes"] = "fabricated"

    # ...leaves the cache, and therefore the next response, untouched.
    again = memory_graph.build_graph_detail(source, reader)
    assert len(again["nodes"]) == 4
    assert len(again["edges"]) == 3
    assert "999" not in again["community_names"]
    assert again["encoding"] == _valid_detail_artifact()["encoding"]
    assert again["meta"]["counts"]["nodes"] == 4


#: Payloads no correct generator emits. Each must be refused by the SOURCE (so
#: it can never reach the builder in production) and must not make the builder
#: raise if some other caller hands it over anyway.
_HOSTILE_PAYLOADS = [
    pytest.param(None, id="no_payload"),
    pytest.param({}, id="empty_payload"),
    pytest.param({"nodes": "not-a-list", "edges": []}, id="nodes_not_a_list"),
    pytest.param({"nodes": [], "edges": "not-a-list"}, id="edges_not_a_list"),
]


@pytest.mark.parametrize("hostile", _HOSTILE_PAYLOADS)
def test_build_graph_detail_degrades_on_a_hostile_payload(hostile):
    """A source reporting ``available: true`` with a structurally impossible
    payload degrades honestly instead of becoming a 500 or echoing the payload
    back as if it were a graph."""
    body = memory_graph.build_graph_detail(_FakeDetailSource(hostile), _FakeReader())
    assert body["available"] is False
    assert body["reason"] == "detail_unreadable"
    assert body["nodes"] == []
    assert body["edges"] == []


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param({"node_keys": ["id", "label"]}, id="short_node_keys"),
        pytest.param(
            {"node_keys": ["id", "source_file", "label", "file_type",
                           "source_location", "community_id"]},
            id="reordered_node_keys",
        ),
        pytest.param({"edge_keys": ["a", "b", "c"]}, id="renamed_edge_keys"),
        # Node-row mutations also blank ``edges`` so the refusal is provably
        # about the node row, not about an edge index left dangling by it.
        pytest.param({"nodes": [["only", "two"]], "edges": []}, id="short_node_row"),
        pytest.param({"nodes": [[1, None, None, "src/x.py", None, None]],
                      "edges": []}, id="non_string_node_id"),
        pytest.param({"nodes": [["n", None, None, None, None, None]],
                      "edges": []}, id="null_node_source_file"),
        pytest.param({"nodes": [["n", 7, None, "src/x.py", None, None]],
                      "edges": []}, id="non_string_node_label"),
        pytest.param({"edges": [[0, 99, "contains"]]}, id="out_of_range_edge"),
        pytest.param({"edges": [[0, 1]]}, id="short_edge_row"),
        pytest.param({"edges": [[0, 1, ""]]}, id="empty_relation"),
        pytest.param({"edges": [[True, 1, "contains"]]}, id="boolean_endpoint"),
    ],
)
def test_source_refuses_a_mis_shaped_artifact(tmp_path, mutate):
    """Rows are decoded POSITIONALLY, so the source must refuse an artifact whose
    declared column order or row shape differs — a mis-decoded graph that still
    looks plausible is worse than no graph. An out-of-range edge endpoint is
    refused here too, so a dangling edge can never enter from the file itself."""
    artifact = _valid_detail_artifact()
    artifact.update(mutate)
    source = memory.GraphDetailSource(_write_detail(tmp_path, artifact))
    result = source.detail()
    assert result["available"] is False
    assert result["reason"] == "detail_unreadable"
    assert result["integrity"] == "malformed"
    assert result["data"] is None


@pytest.mark.parametrize("bad_version", [True, False, 1.0, "1", None, [1]])
def test_source_refuses_a_non_int_detail_schema_version(tmp_path, bad_version):
    """``isinstance(True, int)`` is True and ``True != 1`` is False in Python, so
    a bare inequality check ACCEPTED ``detail_schema_version: true`` as version 1
    and echoed it into the response's provenance. The version field is the only
    thing standing between a future incompatible artifact and a silently
    mis-decoded graph, so it must be the int 1 and nothing else."""
    artifact = _valid_detail_artifact()
    artifact["detail_schema_version"] = bad_version
    source = memory.GraphDetailSource(_write_detail(tmp_path, artifact))
    result = source.detail()
    assert result["available"] is False
    assert result["reason"] == "detail_unreadable"
    assert result["data"] is None


def test_generator_also_refuses_a_boolean_detail_schema_version():
    """The generator carried the identical bool/int hole; both sides are fixed,
    so a ``true`` version can neither be written nor read."""
    generator = _load_generator()
    artifact = _valid_detail_artifact()
    artifact["detail_schema_version"] = True
    issues = generator._validate_detail_shape(artifact)
    assert any("detail_schema_version" in issue for issue in issues), issues


def test_source_refuses_an_unknown_top_level_key(tmp_path):
    """M2: the runtime used a SUBSET key check while the generator uses an EXACT
    one, so the runtime accepted artifacts the generator refuses to write. The
    ``detail_schema_version`` field — not silent tolerance — is the mechanism for
    adding a key, so the two are aligned on strictness."""
    artifact = _valid_detail_artifact()
    artifact["surprise_key"] = {"anything": True}
    source = memory.GraphDetailSource(_write_detail(tmp_path, artifact))
    result = source.detail()
    assert result["available"] is False
    assert result["reason"] == "detail_unreadable"
    assert result["integrity"] == "malformed"
    assert result["data"] is None
    # The generator refuses the same artifact, which is the strictness being matched.
    generator = _load_generator()
    assert any("unexpected top-level keys" in issue
               for issue in generator._validate_detail_shape(artifact))


# =============================================================================
# 3. data safety (the governance gate)
# =============================================================================


def _manifest_paths() -> set:
    snapshot = json.loads(REAL_SNAPSHOT.read_text(encoding="utf-8"))
    return {e["path"] for e in snapshot["memory_inputs"]["served_content_manifest"]}


def test_every_node_source_file_is_inside_the_served_content_manifest(tmp_path,
                                                                     monkeypatch):
    """The content-governance boundary. Not "mostly inside" — every single node.
    A node outside the manifest would ship a path the served-content gate
    withholds."""
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    manifest = _manifest_paths()
    assert len(manifest) == 200
    source_files = {row[3] for row in body["nodes"]}
    assert source_files, "no node carried a source_file — the check would be vacuous"
    outside = sorted(source_files - manifest)
    assert outside == [], f"nodes outside the served-content manifest: {outside}"
    assert len(source_files) == 179


def test_no_node_exposes_a_gitignored_path(tmp_path, monkeypatch):
    """Derived deterministically and OFFLINE — this test never shells out to
    ``git check-ignore``.

    The derivation: ``scripts/build_memory_snapshot.py`` builds the snapshot's
    served set as the intersection of the governance-filtered set with
    ``git ls-files`` (see its git-tracked filter), and the served-content
    manifest is computed from that set. A gitignored path is by definition not
    tracked, so it cannot be in the manifest. The test above proves every node's
    ``source_file`` is in the manifest; membership therefore entails
    not-gitignored. What is asserted here is the other half of the same
    boundary, which membership alone does not give us: every path also passes
    the runtime governance predicates the manifest was built with, so a future
    manifest built without the git filter could not sneak an excluded path
    through.
    """
    from isaac_api.memory import LocalGraphArtifactSource

    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    manifest = _manifest_paths()
    for row in body["nodes"]:
        source_file = row[3]
        assert source_file in manifest
        assert not LocalGraphArtifactSource._is_unsafe(source_file), source_file
        assert memory._is_served(source_file), source_file
        for excluded in memory.EXCLUDED_PREFIXES:
            assert not source_file.startswith(excluded), source_file


#: Machine / location / identity markers scanned across EVERY string in the
#: response — deliberately WIDER than a home-directory-plus-drive-letter check,
#: because node labels are docstring first-lines and heading text harvested from
#: served files: a future regeneration could legitimately pick up a ``~/.claude``
#: path, a mounted beamtime volume, an email address or an internal hostname from
#: a docstring, and the earlier narrow pattern would have passed all of them.
#: Kept as an INDEPENDENT spelling of the generator's ``_machine_secret_issues``
#: policy (never an import of it) so a regression in either is caught by the
#: other; ``test_the_machine_patterns_can_actually_match`` guards the guard.
_MACHINE_PATTERNS = {
    # home directories, in absolute and shorthand form
    "home_absolute": re.compile(r"/Users/|/home/|/root/"),
    "home_shorthand": re.compile(r"~/|~[A-Za-z0-9._-]+/"),
    # Windows machine paths and UNC network shares
    "windows_machine": re.compile(r"[A-Za-z]:\\|\\Users\\|\\home\\"),
    "unc_share": re.compile(r"\\\\[A-Za-z0-9._-]+\\"),
    # machine mount points and OS scratch roots
    "machine_mount": re.compile(
        r"/(?:Volumes|mnt|media|opt|srv)/|/var/folders/|/private/(?:tmp|var)/"
    ),
    "file_url": re.compile(r"file://"),
    # identities and network locations
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]{2,})+"),
    "internal_host": re.compile(
        r"(?i)[A-Za-z0-9-]+\.(?:slac|stanford|internal|corp|lan)(?![A-Za-z0-9-])"
    ),
    "mdns_host": re.compile(
        r"(?i)(?<![A-Za-z0-9._-])[A-Za-z0-9-]+\.local(?![A-Za-z0-9._-])"
    ),
}
_IPV4_RE = re.compile(r"(?<![0-9A-Za-z.-])(?:\d{1,3}\.){3}\d{1,3}(?![0-9A-Za-z.-])")
#: Disclosed exemption: loopback and the bind-any wildcard are documented,
#: non-identifying literals already published throughout the served docs
#: (``--host 127.0.0.1`` / ``--host 0.0.0.0``). Any other address still fails.
_IPV4_EXEMPT_RE = re.compile(r"\A(?:0\.0\.0\.0|127\.\d{1,3}\.\d{1,3}\.\d{1,3})\Z")
#: Disclosed exemption: the project's OWN deployment host, already published in
#: committed served documentation (``docs/deployment.md``). Removed from the value
#: before the hostname patterns run, so a different internal host in the same
#: string is still caught.
_PUBLIC_HOST_EXEMPTIONS = ("isaac.slac.stanford.edu",)


def _machine_marker_hits(value: str) -> list:
    """Every widened machine/location/identity marker in one string."""
    hits = []
    hostname_scope = value
    for host in _PUBLIC_HOST_EXEMPTIONS:
        hostname_scope = hostname_scope.replace(host, "")
    for name, pattern in _MACHINE_PATTERNS.items():
        target = hostname_scope if name in ("internal_host", "mdns_host") else value
        if pattern.search(target):
            hits.append(name)
    for match in _IPV4_RE.finditer(value):
        if not _IPV4_EXEMPT_RE.match(match.group(0)):
            hits.append(f"ip:{match.group(0)}")
    return hits


def test_no_absolute_local_path_anywhere_in_the_response(tmp_path, monkeypatch):
    """Two rules, matching the generator's own scan policy: machine / location /
    identity markers are rejected in EVERY string, while the strict path-shape
    rule (must not start with ``/`` or ``~``) applies only to the path-bearing
    field ``source_file``.

    Why the split rather than a blanket ``startswith("/")``: the artifact
    legitimately carries slash-command CONCEPT LABELS such as
    ``/isaac-complete — Validated Minimum Mode``. Those are command names, not
    paths, and the generator documents the same exemption. Note ``~`` is NOT
    exempted anywhere — no legitimate label names a home directory.
    """
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    repo_root_str = str(REPO_ROOT)
    checked = 0
    for value in _walk_strings(body):
        assert not _machine_marker_hits(value), (
            f"machine/location/identity marker in {value!r}: "
            f"{_machine_marker_hits(value)}"
        )
        assert repo_root_str not in value, f"generator machine path in {value!r}"
        checked += 1
    assert checked > 10000, f"only scanned {checked} strings — check the walker"

    for row in body["nodes"]:
        source_file = row[3]
        assert not source_file.startswith("/"), source_file
        assert not source_file.startswith("~"), source_file
        assert "\\" not in source_file, source_file
        assert ":" not in source_file, source_file
    # A slash-command label really is present, so the exemption above is a live
    # decision rather than a hypothetical one.
    labels = {row[1] for row in body["nodes"] if isinstance(row[1], str)}
    assert any(label.startswith("/isaac-") for label in labels)


#: Guard-the-guard corpus for the widened patterns. Left column must match the
#: named pattern; the legitimate-vocabulary list below must match nothing.
_MACHINE_MARKER_TARGETS = [
    ("home_absolute", "/Users/krishverma/secret.py"),
    ("home_absolute", "/home/dev/x"),
    ("home_absolute", "/root/x"),
    ("home_shorthand", "~/private/notes.xlsx"),
    ("home_shorthand", "~krish/secret.py"),
    ("windows_machine", r"C:\Users\dev\project"),
    ("unc_share", r"\\fileserver\slac\x"),
    ("machine_mount", "/Volumes/BEAMTIME/raw.h5"),
    ("machine_mount", "/var/folders/ab/cd/T/x"),
    ("machine_mount", "/private/tmp/x"),
    ("machine_mount", "/mnt/data/x"),
    ("machine_mount", "/media/usb/x"),
    ("machine_mount", "/opt/private/x"),
    ("machine_mount", "/srv/x/y"),
    ("file_url", "file:///etc/passwd"),
    ("email", "kverma@slac.stanford.edu"),
    ("internal_host", "s3df.slac.stanford.edu"),
    ("internal_host", "build01.internal"),
    ("internal_host", "host.corp"),
    ("internal_host", "box.lan"),
    ("mdns_host", "mymac.local"),
    ("ip", "10.1.2.3"),
    ("ip", "192.168.0.7"),
    ("ip", "172.16.5.9"),
    ("ip", "8.8.8.8"),
]

#: Strings that legitimately appear (or plausibly could appear) in a label, path
#: or docstring first-line and must NOT be flagged. Several are live false
#: positives that a naive pattern set produces against THIS repository's own
#: governance vocabulary.
_MACHINE_MARKER_NON_TARGETS = [
    "/isaac-complete — Validated Minimum Mode",
    "/isaac-export",
    "docs/deployment.md",
    "apps/web/src/lib/api.ts",
    "src/isaac_records/official.py",
    "src/optional/thing.py",          # contains "/opt" but not "/opt/"
    "127.0.0.1:8000",                 # documented loopback
    "--host 0.0.0.0",                 # documented bind-any
    ".claude/settings.local.json",    # dotted chain, not an mDNS host
    ".env.local",
    "file_detail.local_reference",
    "isaac.slac.stanford.edu",        # the project's own published host
    "@pytest.mark.parametrize",       # no local part, so not an email
    "ISAAC schema v1.05",
    "policy_version 1.0.0",
]


@pytest.mark.parametrize("expected,value", _MACHINE_MARKER_TARGETS,
                         ids=[f"{n}-{i}" for i, (n, _) in
                              enumerate(_MACHINE_MARKER_TARGETS)])
def test_the_machine_patterns_can_actually_match(expected, value):
    """Guard the guard: a scan that matches nothing proves nothing. Every
    widened category must fire on its target."""
    hits = _machine_marker_hits(value)
    assert any(h.split(":")[0] == expected for h in hits), (
        f"{expected} did not fire on {value!r} (hits: {hits})"
    )


@pytest.mark.parametrize("value", _MACHINE_MARKER_NON_TARGETS)
def test_the_machine_patterns_do_not_fire_on_legitimate_vocabulary(value):
    """The other half of the guard: a pattern set noisy enough to block a
    legitimate regeneration would get gutted, so the exemptions and the
    both-side guards are asserted explicitly."""
    assert _machine_marker_hits(value) == [], value


def test_the_generators_scanner_agrees_with_this_files_patterns():
    """The generator's ``_machine_secret_issues`` and this file's independent
    spelling must agree on every guard-the-guard case — otherwise one of the two
    was widened and the other silently was not."""
    generator = _load_generator()
    for expected, value in _MACHINE_MARKER_TARGETS:
        assert generator._machine_secret_issues(value, ""), (
            f"generator scanner missed {expected} target {value!r}"
        )
    for value in _MACHINE_MARKER_NON_TARGETS:
        assert generator._machine_secret_issues(value, "") == [], (
            f"generator scanner false-positives on {value!r}"
        )


#: Any URI scheme, not just http(s) — the assertion must cover what the docstring
#: concludes. One benign, documented exception: a docstring first-line in the
#: truth core mentions the ``ssrl-archive://`` sidecar convention, which is a
#: NON-RESOLVABLE identifier scheme (no host, no network client for it anywhere)
#: and therefore triggers no external request.
_URI_SCHEME_RE = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*://")
_BENIGN_SCHEMES = {"ssrl-archive"}


def test_no_external_url_anywhere_in_the_response(tmp_path, monkeypatch):
    """Proves the surface needs no external request to be rendered — the same
    ground on which the CDN-loading Graphify HTML was rejected.

    Asserted over ANY ``scheme://``, not only ``http(s)://``: a ``ws://``,
    ``ftp://`` or protocol-relative reference would fetch just as remotely. The
    one allowed scheme is the documented, non-resolvable ``ssrl-archive://``
    identifier.
    """
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    seen = set()
    for value in _walk_strings(body):
        for match in _URI_SCHEME_RE.finditer(value):
            scheme = match.group(0)[:-3]
            seen.add(scheme)
            assert scheme in _BENIGN_SCHEMES, f"external URI scheme in {value!r}"
    # The allowance is a live decision, not a hypothetical one.
    assert seen == {"ssrl-archive"}, seen


#: Credential-shaped patterns. ``long_hex_digest`` is applied only to the graph
#: PAYLOAD (see ``_payload_strings``): the provenance block's commit SHA and
#: sha256 fingerprints are legitimate long hex by design.
_SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "pem_private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "slack_token": re.compile(r"xox[baprs]-"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\."),
    "credential_assignment": re.compile(
        r"(?i)(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*\S"
    ),
}
_LONG_HEX_DIGEST = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{32,}(?![0-9A-Za-z])")


def test_no_secret_shaped_string_anywhere_in_the_response(tmp_path, monkeypatch):
    body = _real_client(tmp_path, monkeypatch).get("/api/memory/graph/detail").json()
    for value in _walk_strings(body):
        for name, pattern in _SECRET_PATTERNS.items():
            assert not pattern.search(value), f"{name}-shaped string: {value!r}"
    payload = list(_payload_strings(body))
    assert len(payload) > 10000
    for value in payload:
        assert not _LONG_HEX_DIGEST.search(value), f"digest-shaped payload: {value!r}"


def test_the_secret_patterns_can_actually_match():
    """Guards the guard: each pattern matches the thing it is meant to catch, so
    the scan above is not vacuous."""
    samples = {
        "aws_access_key": "AKIAIOSFODNN7EXAMPLE",
        "pem_private_key": "-----BEGIN RSA PRIVATE KEY-----",
        "github_token": "ghp_" + "a" * 24,
        "slack_token": "xoxb-fake",
        "jwt": "eyJhbGciOiJIUzI1NiJ9.fake",
        "credential_assignment": "api_key=fake",
    }
    for name, sample in samples.items():
        assert _SECRET_PATTERNS[name].search(sample), name
    assert _LONG_HEX_DIGEST.search("a" * 40)
    # ...and does not fire on legitimate payload vocabulary.
    for benign in ("apps/api/isaac_api/memory_graph.py", "build_graph_detail",
                   "Official schema v1.05", "L142"):
        for pattern in _SECRET_PATTERNS.values():
            assert not pattern.search(benign), benign
        assert not _LONG_HEX_DIGEST.search(benign), benign


# --- isolation: no Graphify service, no truth core ---------------------------
#
# Extends the existing convention (``test_memory_graph.py``'s
# ``test_memory_graph_module_imports_no_graphify_or_isaac_records`` and
# ``test_build_memory_snapshot.py``'s
# ``test_generator_does_not_import_truth_core_or_graphify``) to the whole
# runtime SERVING path of the deep layer, rather than writing a competing check.

_FORBIDDEN_ROOTS = {"graphify", "isaac_records"}


def _imported_roots(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("module_name", ["memory.py", "memory_graph.py"])
def test_serving_path_imports_neither_graphify_nor_the_truth_core(module_name):
    path = REPO_ROOT / "apps" / "api" / "isaac_api" / module_name
    assert path.is_file()
    assert _imported_roots(path).isdisjoint(_FORBIDDEN_ROOTS)


def test_deep_layer_needs_no_runtime_graphify_service(tmp_path, monkeypatch):
    """Served entirely from the one committed artifact: with the Graphify
    artifact directory pointed at a path that does not exist, the deep layer is
    still fully available with its real node and edge counts."""
    import sys

    client = _client(tmp_path, monkeypatch, detail_path=REAL_DETAIL,
                     memory_dir=tmp_path / "absent-graphify-out")
    body = client.get("/api/memory/graph/detail").json()
    assert body["available"] is True
    assert len(body["nodes"]) == REAL_NODES
    assert len(body["edges"]) == REAL_EDGES
    # Serving the request imported no Graphify package at all (same form as
    # ``tests/test_export.py``'s ``test_core_never_imports_graphify``).
    assert not any(
        name == "graphify" or name.startswith("graphify.") for name in sys.modules
    )
    # The ONLY file the deep layer needed is its own committed artifact.
    assert memory.get_default_detail_source().detail_path == REAL_DETAIL


# =============================================================================
# 4. determinism
# =============================================================================
#
# A full regeneration of the committed artifact requires ``graphify-out/``, which
# is gitignored and therefore ABSENT in CI. Rather than write a check that
# silently no-ops there, determinism is covered on three levels:
#
#   * unconditionally, by recomputing every fingerprint the committed artifact
#     records and comparing it to the runtime's own primitives
#     (``test_committed_artifact_fingerprints_match_recomputed_values``);
#   * unconditionally, by proving the generator's detail builder + serializer are
#     byte-deterministic over the COMMITTED synthetic fixture graph
#     (``test_detail_builder_is_byte_deterministic_over_the_fixture_graph``);
#   * conditionally, by byte-comparing the committed artifact against a real
#     regeneration when the source graph happens to be present locally
#     (``test_committed_artifact_matches_a_real_regeneration``, which SKIPS with
#     an explicit reason naming the missing input).


def _load_generator():
    """Load ``scripts/build_memory_snapshot.py`` — same importlib pattern
    ``test_build_memory_snapshot.py`` uses (``scripts/`` is not a package)."""
    import importlib.util

    script = REPO_ROOT / "scripts" / "build_memory_snapshot.py"
    spec = importlib.util.spec_from_file_location("build_memory_snapshot", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_artifact_fingerprints_match_recomputed_values():
    """Every provenance fingerprint the artifact records is recomputed here from
    the runtime's own primitives and the committed snapshot.

    What this actually detects, stated precisely (the earlier docstring claimed
    "a hand-edited or stale artifact cannot pass", which was FALSE — a review
    replayed 13 tamper mutations and 10 survived every CI assertion): a changed
    governance/exclusion policy, a served path SET that no longer matches the
    snapshot's, a served-file COUNT that disagrees, a detail artifact generated
    from different source-graph bytes or at a different indexed commit than the
    snapshot, a wrong ``kind``/version, and a ``counts`` block inconsistent with
    the three pinned totals.

    What it does NOT detect, and cannot without the source graph (which is
    gitignored and absent in CI): a semantically plausible edit to an individual
    row — a rewritten label, a node retargeted to a DIFFERENT SERVED file, a
    flipped or reversed edge, a renamed community. The gate below
    (``test_committed_artifact_passes_the_generators_own_gates``) closes the
    structural and data-safety half of that gap; the remaining semantic half is
    closed only by ``test_committed_artifact_matches_a_real_regeneration``, which
    runs only where ``graphify-out/graph.json`` exists.
    """
    artifact = json.loads(REAL_DETAIL.read_text(encoding="utf-8"))
    snapshot = json.loads(REAL_SNAPSHOT.read_text(encoding="utf-8"))

    assert artifact["policy_fingerprint"] == memory.compute_memory_policy_fingerprint()
    assert artifact["served_path_set_fingerprint"] == (
        memory.compute_served_path_set_fingerprint(snapshot["served"])
    )
    assert artifact["served_file_count"] == len(snapshot["served"]) == 201
    # Both artifacts were generated from the SAME source-graph bytes at the SAME
    # indexed commit — the two cannot silently drift apart.
    assert artifact["source_graph_sha256"] == snapshot["source_graph_sha256"]
    assert artifact["built_at_commit"] == snapshot["built_at_commit"]
    assert artifact["kind"] == memory.GRAPH_DETAIL_KIND
    assert artifact["detail_schema_version"] == (
        memory.SUPPORTED_GRAPH_DETAIL_SCHEMA_VERSION
    )
    # Internal consistency of the recorded counts.
    assert artifact["counts"]["nodes"] == len(artifact["nodes"]) == REAL_NODES
    assert artifact["counts"]["edges"] == len(artifact["edges"]) == REAL_EDGES
    assert artifact["counts"]["communities"] == len(artifact["community_names"])


def test_committed_artifact_passes_the_generators_own_gates():
    """The standing CI gate the deep artifact was missing.

    ``test_committed_snapshot.py`` has run the generator's own ``_validate_shape``
    and ``_scan_for_leaks`` against the REAL committed snapshot since P24; the
    deep artifact had no equivalent — its shape validator and leak scanner were
    exercised only against the synthetic fixture. So the artifact that actually
    ships was never put through the two functions written to police it.

    Three assertions, all against the real committed bytes:

    1. ``_validate_detail_shape`` — every structural rule the generator refuses
       to write, re-checked on what is committed: exact top-level key set, kind,
       int schema version, node/edge column order and row shape, duplicate ids,
       path-shaped ``source_location``, in-range edge endpoints, rationale label
       cap, and ``counts`` agreeing with ``len(nodes)``/``len(edges)``/
       ``len(community_names)``.
    2. ``_scan_detail_for_leaks`` — every node's ``source_file`` path-safe,
       governance-served and inside the snapshot's served set, plus the widened
       machine/identity/credential scan over every string in the artifact.
    3. Byte canonicality — the committed file is exactly what
       ``_serialize_detail`` produces for its own parsed content, so a hand-edit
       that changed formatting, key order or row layout fails here.
    """
    generator = _load_generator()
    real = json.loads(REAL_DETAIL.read_text(encoding="utf-8"))
    snapshot = json.loads(REAL_SNAPSHOT.read_text(encoding="utf-8"))

    assert generator._validate_detail_shape(real) == []
    assert generator._scan_detail_for_leaks(
        real, served=snapshot["served"], repo_root=REPO_ROOT
    ) == []
    assert generator._serialize_detail(real) == REAL_DETAIL.read_bytes()


#: Tamper mutations replayed against the committed artifact. ``True`` means the
#: CI gates above MUST detect the mutation; ``False`` records — honestly — a
#: mutation no CI assertion can catch without the (gitignored, CI-absent) source
#: graph, so the property is documented rather than claimed.
_TAMPERS = [
    ("counts_inflated", True),
    ("counts_edges_off_by_one", True),
    ("edge_endpoint_out_of_range", True),
    ("source_file_outside_served_set", True),
    ("duplicate_node_id", True),
    ("source_location_made_path_shaped", True),
    ("label_injects_home_shorthand_path", True),
    ("label_injects_unc_share", True),
    ("label_injects_machine_volume", True),
    ("label_injects_email_address", True),
    ("node_retargeted_to_another_served_file", False),
    ("edge_relation_flipped", False),
    ("edge_direction_reversed", False),
    ("community_renamed", False),
    ("label_rewritten_to_invented_prose", False),
    ("id_shaped_like_a_home_path", False),
]


def _apply_tamper(artifact: dict, name: str) -> dict:
    """Apply one named mutation in place and return the artifact."""
    if name == "counts_inflated":
        artifact["counts"]["nodes"] = 999999999
    elif name == "counts_edges_off_by_one":
        artifact["counts"]["edges"] += 1
    elif name == "edge_endpoint_out_of_range":
        artifact["edges"][0][1] = len(artifact["nodes"]) + 10
    elif name == "source_file_outside_served_set":
        artifact["nodes"][0][3] = "examples/private_beamtime.md"
    elif name == "duplicate_node_id":
        artifact["nodes"][1][0] = artifact["nodes"][0][0]
    elif name == "source_location_made_path_shaped":
        artifact["nodes"][0][4] = "../../etc/passwd"
    elif name == "label_injects_home_shorthand_path":
        artifact["nodes"][0][1] = "~/private/notes.xlsx"
    elif name == "label_injects_unc_share":
        artifact["nodes"][0][1] = r"\\fileserver\slac\x"
    elif name == "label_injects_machine_volume":
        artifact["nodes"][0][1] = "/Volumes/BEAMTIME/raw.h5"
    elif name == "label_injects_email_address":
        artifact["nodes"][0][1] = "kverma@slac.stanford.edu"
    elif name == "node_retargeted_to_another_served_file":
        other = next(row[3] for row in artifact["nodes"]
                     if row[3] != artifact["nodes"][0][3])
        artifact["nodes"][0][3] = other
    elif name == "edge_relation_flipped":
        artifact["edges"][0][2] = ("calls" if artifact["edges"][0][2] != "calls"
                                   else "imports")
    elif name == "edge_direction_reversed":
        edge = artifact["edges"][0]
        edge[0], edge[1] = edge[1], edge[0]
    elif name == "community_renamed":
        key = sorted(artifact["community_names"])[0]
        artifact["community_names"][key] = "Fabricated cluster name"
    elif name == "label_rewritten_to_invented_prose":
        artifact["nodes"][0][1] = "Handles the calibration sweep for the beamline"
    elif name == "id_shaped_like_a_home_path":
        artifact["nodes"][0][0] = "_Users_krishverma_secret_py"
    else:  # pragma: no cover - guards the table against a typo
        raise AssertionError(f"unknown tamper: {name}")
    return artifact


def _tamper_detected(artifact: dict, generator, served) -> bool:
    """Is this artifact rejected by a gate that is runnable in CI?

    Models the STRONGER attacker deliberately: someone who edits the artifact and
    re-serializes it with ``_serialize_detail``, so the byte-canonicality
    assertion in ``test_committed_artifact_passes_the_generators_own_gates``
    passes by construction and contributes nothing here. Including it would
    inflate every row of the table to "detected" while detecting only careless
    formatting. Canonicality is asserted on its own, against the committed bytes,
    in that test and in ``test_a_non_canonical_hand_edit_is_caught_by_bytes``.
    """
    if generator._validate_detail_shape(artifact):
        return True
    if generator._scan_detail_for_leaks(artifact, served=served, repo_root=REPO_ROOT):
        return True
    return False


def test_a_non_canonical_hand_edit_is_caught_by_bytes():
    """The canonicality half of the gate: an edit that does not reproduce
    ``_serialize_detail``'s exact output fails, even when its CONTENT would pass
    shape and leak validation."""
    generator = _load_generator()
    real = json.loads(REAL_DETAIL.read_text(encoding="utf-8"))
    # Same content, different (json.dumps default) formatting.
    non_canonical = json.dumps(real, sort_keys=True, indent=2).encode("utf-8")
    assert generator._validate_detail_shape(real) == []
    assert non_canonical != generator._serialize_detail(real)


@pytest.mark.parametrize("name,must_detect", _TAMPERS,
                         ids=[n for n, _ in _TAMPERS])
def test_tamper_detection_is_exactly_as_documented(name, must_detect):
    """Pins the tamper table both ways.

    ``must_detect=True`` rows are regressions if they ever stop being caught.
    ``must_detect=False`` rows assert the LIMIT honestly: they are semantically
    plausible single-row edits that no gate runnable in CI can distinguish from
    real data, because the source graph is gitignored and absent there. They are
    caught only by ``test_committed_artifact_matches_a_real_regeneration``, which
    is skipped without ``graphify-out/graph.json``. Recording them as ``False``
    keeps the file from implying a guarantee it does not provide.
    """
    generator = _load_generator()
    snapshot = json.loads(REAL_SNAPSHOT.read_text(encoding="utf-8"))
    baseline = json.loads(REAL_DETAIL.read_text(encoding="utf-8"))
    # Positive control: the untampered artifact passes every gate.
    assert not _tamper_detected(copy.deepcopy(baseline), generator, snapshot["served"])

    tampered = _apply_tamper(copy.deepcopy(baseline), name)
    detected = _tamper_detected(tampered, generator, snapshot["served"])
    assert detected is must_detect, (
        f"tamper {name!r}: detected={detected}, documented={must_detect}"
    )


def test_detail_builder_is_byte_deterministic_over_the_fixture_graph():
    """Two runs over the committed synthetic fixture graph must produce
    identical dicts AND identical serialized bytes. Runs everywhere, including
    CI: the fixture graph is committed."""
    generator = _load_generator()
    served = ["docs/fake_notes.md", "src/fake_helper.py", "src/fake_widget.py"]
    first = generator.build_graph_detail(FIXTURE_GRAPH_DIR, served=served)
    second = generator.build_graph_detail(FIXTURE_GRAPH_DIR, served=served)
    assert first == second
    assert generator._serialize_detail(first) == generator._serialize_detail(second)

    # ...and the fixture's governance-excluded / absolute-path nodes are DROPPED,
    # never emitted: the fixture graph deliberately carries a node anchored at
    # ``examples/README.md`` and one anchored at an absolute path.
    source_files = {row[3] for row in first["nodes"]}
    assert source_files <= set(served)
    assert not any(sf.startswith("examples/") or sf.startswith("/")
                   for sf in source_files)
    # Every edge index resolves, and the shape validation the generator applies
    # before writing passes.
    for source_index, target_index, _relation in first["edges"]:
        assert 0 <= source_index < len(first["nodes"])
        assert 0 <= target_index < len(first["nodes"])
    assert generator._validate_detail_shape(first) == []
    assert generator._scan_detail_for_leaks(
        first, served=served, repo_root=REPO_ROOT
    ) == []


@pytest.mark.skipif(
    not (SOURCE_GRAPH_DIR / "graph.json").is_file(),
    reason=(
        "graphify-out/graph.json is absent (it is gitignored, so it is never "
        "present in CI) — the committed artifact cannot be regenerated from its "
        "real source here; the unconditional fingerprint and builder-determinism "
        "tests above cover determinism in that environment"
    ),
)
def test_committed_artifact_matches_a_real_regeneration():
    """When the real source graph IS available locally, the committed artifact
    must be byte-identical to a fresh regeneration from it."""
    generator = _load_generator()
    snapshot = json.loads(REAL_SNAPSHOT.read_text(encoding="utf-8"))
    rebuilt = generator.build_graph_detail(
        SOURCE_GRAPH_DIR,
        served=snapshot["served"],
        source_graph_sha256=snapshot["source_graph_sha256"],
    )
    assert generator._serialize_detail(rebuilt) == REAL_DETAIL.read_bytes()


# =============================================================================
# 5. the source seam itself (GraphDetailSource)
# =============================================================================


def test_graph_detail_source_caches_by_mtime_and_never_raises(tmp_path):
    """One parse per artifact state: repeated reads reuse the cached state, and
    a rewritten file is re-read. Nothing raises out of ``detail()``."""
    path = _write_detail(tmp_path, _valid_detail_artifact())
    source = memory.GraphDetailSource(path)
    first = source.detail()
    assert first["available"] is True
    assert source.reload_count == 1
    for _ in range(3):
        assert source.detail()["available"] is True
    assert source.reload_count == 1

    broken = _valid_detail_artifact()
    broken["kind"] = "not-a-graph-detail"
    import os

    path.write_text(json.dumps(broken), encoding="utf-8")
    os.utime(path, (100.0, 100.0))  # distinct mtime, deterministically
    again = source.detail()
    assert again["available"] is False
    assert again["reason"] == "detail_unreadable"
    assert again["data"] is None
    assert source.reload_count == 2


def test_graph_detail_source_reports_absent_without_touching_disk(tmp_path):
    source = memory.GraphDetailSource(tmp_path / "definitely-not-here.json")
    result = source.detail()
    assert result == {"available": False, "reason": "detail_absent",
                      "integrity": "unknown", "detail_schema_version": None,
                      "data": None}


def test_default_detail_source_prefers_the_environment_override(tmp_path,
                                                               monkeypatch):
    """The documented resolution order: a non-empty override wins, otherwise the
    packaged artifact. Memoized, and rebuilt when the resolved path changes."""
    override = _write_detail(tmp_path, _valid_detail_artifact())
    monkeypatch.setenv(memory.ENV_MEMORY_GRAPH_DETAIL, str(override))
    source = memory.get_default_detail_source()
    assert source.detail_path == override
    assert memory.get_default_detail_source() is source  # memoized

    monkeypatch.delenv(memory.ENV_MEMORY_GRAPH_DETAIL, raising=False)
    packaged = memory.get_default_detail_source()
    assert packaged is not source
    assert packaged.detail_path == memory._PACKAGED_GRAPH_DETAIL


def test_default_detail_source_ignores_a_blank_override(tmp_path, monkeypatch):
    monkeypatch.setenv(memory.ENV_MEMORY_GRAPH_DETAIL, "   ")
    assert memory.get_default_detail_source().detail_path == (
        memory._PACKAGED_GRAPH_DETAIL
    )


# =============================================================================
# 6. the generator's --detail-out CLI path
# =============================================================================
#
# Driven over the committed synthetic fixture graph and its committed
# "served root" of real fixture bytes — the same inputs
# ``test_build_memory_snapshot.py`` uses for the snapshot CLI.

FIXTURE_SERVED_ROOT = (
    REPO_ROOT / "tests" / "fixtures" / "memory_snapshot" / "served_root"
)


def _cli_args(tmp_path, *, detail_out=None, check=False):
    args = [
        "--graph-dir", str(FIXTURE_GRAPH_DIR),
        "--out", str(tmp_path / "memory-snapshot.json"),
        "--repo-root", str(FIXTURE_SERVED_ROOT),
    ]
    if detail_out is not None:
        args += ["--detail-out", str(detail_out)]
    if check:
        args.append("--check")
    return args


def test_cli_detail_out_writes_an_artifact_the_runtime_source_accepts(tmp_path):
    """End-to-end generator-to-runtime contract: what the CLI writes is exactly
    what ``GraphDetailSource`` considers verified."""
    generator = _load_generator()
    detail_out = tmp_path / "memory-graph-detail.json"
    assert generator.main(_cli_args(tmp_path, detail_out=detail_out)) == 0
    assert detail_out.is_file()

    loaded = memory.GraphDetailSource(detail_out).detail()
    assert loaded["available"] is True
    assert loaded["integrity"] == "verified"
    assert loaded["detail_schema_version"] == 1
    assert loaded["data"]["kind"] == memory.GRAPH_DETAIL_KIND

    body = memory_graph.build_graph_detail(
        memory.GraphDetailSource(detail_out), _FakeReader()
    )
    assert body["available"] is True
    assert len(body["nodes"]) == loaded["data"]["counts"]["nodes"]
    assert len(body["edges"]) == loaded["data"]["counts"]["edges"]
    # No fixture node anchored outside the served set survives.
    assert {row[3] for row in body["nodes"]} <= {
        "docs/fake_notes.md", "src/fake_helper.py", "src/fake_widget.py",
    }


def test_cli_detail_out_round_trips_through_check(tmp_path):
    generator = _load_generator()
    detail_out = tmp_path / "memory-graph-detail.json"
    assert generator.main(_cli_args(tmp_path, detail_out=detail_out)) == 0
    assert generator.main(_cli_args(tmp_path, detail_out=detail_out, check=True)) == 0


def test_cli_check_detects_detail_drift(tmp_path):
    generator = _load_generator()
    detail_out = tmp_path / "memory-graph-detail.json"
    assert generator.main(_cli_args(tmp_path, detail_out=detail_out)) == 0
    payload = detail_out.read_bytes()
    drifted = payload.replace(b"fakecommitp24900", b"fakecommitDRIFTED")
    assert drifted != payload, "the fixture commit marker must be present"
    detail_out.write_bytes(drifted)
    assert generator.main(
        _cli_args(tmp_path, detail_out=detail_out, check=True)
    ) == generator.EXIT_CHECK_DRIFT


def test_cli_check_reports_an_absent_detail_target(tmp_path):
    generator = _load_generator()
    assert generator.main(_cli_args(tmp_path, detail_out=tmp_path / "nope.json")) == 0
    (tmp_path / "nope.json").unlink()
    assert generator.main(
        _cli_args(tmp_path, detail_out=tmp_path / "nope.json", check=True)
    ) == generator.EXIT_CHECK_DRIFT


def test_cli_check_never_writes_the_detail_artifact(tmp_path):
    generator = _load_generator()
    detail_out = tmp_path / "memory-graph-detail.json"
    generator.main(_cli_args(tmp_path, detail_out=detail_out, check=True))
    assert not detail_out.exists()


def test_cli_without_detail_out_writes_no_detail_artifact(tmp_path):
    """Opt-in: the deep layer is neither written nor checked unless asked for,
    so the snapshot pipeline's existing behaviour is unchanged."""
    generator = _load_generator()
    assert generator.main(_cli_args(tmp_path)) == 0
    assert (tmp_path / "memory-snapshot.json").is_file()
    assert list(p.name for p in tmp_path.iterdir()) == ["memory-snapshot.json"]


def test_cli_check_without_detail_out_says_the_detail_was_not_checked(tmp_path,
                                                                     capsys):
    """The reporting hole behind IMPORTANT-3: ``--check`` WITHOUT ``--detail-out``
    printed "ok: no drift" and exited 0 while a stale deep artifact sat on disk,
    telling the operator there was no drift when the run had not looked. The exit
    code and the default paths are deliberately unchanged — an opt-in flag that
    silently became mandatory would break existing callers — so the fix is that
    the run now SAYS it did not check."""
    generator = _load_generator()
    assert generator.main(_cli_args(tmp_path)) == 0
    capsys.readouterr()
    assert generator.main(_cli_args(tmp_path, check=True)) == 0
    err = capsys.readouterr().err
    assert "--detail-out not given" in err
    assert "NOT checked" in err
    assert "memory-graph-detail.json" in err


def test_cli_write_without_detail_out_says_the_detail_was_not_regenerated(tmp_path,
                                                                         capsys):
    """The other half: regenerating the snapshot with the documented command but
    without ``--detail-out`` rewrites the snapshot and leaves the deep artifact
    stale. Silence there is what would ship a stale artifact."""
    generator = _load_generator()
    assert generator.main(_cli_args(tmp_path)) == 0
    err = capsys.readouterr().err
    assert "--detail-out not given" in err
    assert "NOT regenerated" in err


def test_cli_check_reports_both_drifts_when_both_are_stale(tmp_path, capsys):
    """M3: the snapshot check used to ``return`` before the detail check, so an
    operator with two drifted artifacts was told about one. The exit code was
    already correct (6), so this is a reporting fix — both are now named."""
    generator = _load_generator()
    detail_out = tmp_path / "memory-graph-detail.json"
    snapshot_out = tmp_path / "memory-snapshot.json"
    assert generator.main(_cli_args(tmp_path, detail_out=detail_out)) == 0

    snapshot_out.write_bytes(snapshot_out.read_bytes() + b"\n")
    detail_out.write_bytes(detail_out.read_bytes() + b"\n")
    capsys.readouterr()

    assert generator.main(
        _cli_args(tmp_path, detail_out=detail_out, check=True)
    ) == generator.EXIT_CHECK_DRIFT
    err = capsys.readouterr().err
    assert "snapshot is stale/drifted" in err
    assert "graph detail is stale/drifted" in err


def test_cli_check_with_detail_out_fails_on_a_stale_detail_artifact(tmp_path, capsys):
    """The scenario the documented command block previously could not see: the
    snapshot is CURRENT and only the deep artifact is stale."""
    generator = _load_generator()
    detail_out = tmp_path / "memory-graph-detail.json"
    assert generator.main(_cli_args(tmp_path, detail_out=detail_out)) == 0
    detail_out.write_bytes(detail_out.read_bytes() + b"\n")
    capsys.readouterr()

    # Without --detail-out the same drift is invisible and the run exits 0...
    assert generator.main(_cli_args(tmp_path, check=True)) == 0
    # ...but the documented form now catches it.
    assert generator.main(
        _cli_args(tmp_path, detail_out=detail_out, check=True)
    ) == generator.EXIT_CHECK_DRIFT
    out_err = capsys.readouterr()
    assert "graph detail is stale/drifted" in out_err.err
    assert "matches regenerated snapshot (no drift)" in out_err.out


def test_valid_artifact_helper_is_not_accidentally_mutated_by_a_test():
    """The parametrized degraded tests mutate a fresh copy each time; this pins
    that the builder returns an independent dict."""
    first = _valid_detail_artifact()
    first["kind"] = "mutated"
    assert _valid_detail_artifact()["kind"] == "isaac-memory-graph-detail"
    assert copy.deepcopy(first) is not first

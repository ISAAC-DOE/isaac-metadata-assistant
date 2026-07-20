"""Durable CI gate over the COMMITTED sanitized Project Memory snapshot
(``apps/api/isaac_api/data/memory-snapshot.json``, P24.9-impl-4).

Unlike ``test_build_memory_snapshot.py`` (which drives the generator against a
small synthetic fixture graph under ``tests/fixtures/memory_snapshot/graph/``)
and ``test_snapshot_source.py`` (which drives the reader against a golden
*fixture* snapshot), this file loads the REAL artifact that ships in the
hosted image and asserts it stays clean — with no live ``graphify-out/``
needed, so it runs unconditionally in CI.

It reuses the generator's own validation/scan helpers (``_validate_shape`` /
``_scan_for_leaks``) rather than re-implementing shape/leak rules here — a
second, drifting copy of those rules would be worse than no test at all. The
script is loaded via ``importlib.util.spec_from_file_location``, the same
pattern ``test_build_memory_snapshot.py`` and ``tests/test_graphify_freshness.py``
use, since ``scripts/`` is not a package.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from isaac_api.memory import SUPPORTED_SNAPSHOT_SCHEMA_VERSION, SanitizedSnapshotSource

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "build_memory_snapshot.py"
SNAPSHOT_PATH = REPO_ROOT / "apps" / "api" / "isaac_api" / "data" / "memory-snapshot.json"


def _load_generator():
    spec = importlib.util.spec_from_file_location("build_memory_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


def _snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


# --- 1. shape + leak scan (reuses the generator's own helpers, never a copy) --


def test_committed_snapshot_file_exists():
    assert SNAPSHOT_PATH.is_file(), f"committed snapshot missing: {SNAPSHOT_PATH}"


def test_committed_snapshot_shape_is_valid():
    issues = gen._validate_shape(_snapshot())
    assert issues == [], f"shape issues in committed snapshot: {issues}"


def test_committed_snapshot_has_no_leaks():
    issues = gen._scan_for_leaks(_snapshot(), repo_root=REPO_ROOT)
    assert issues == [], f"leak/governance issues in committed snapshot: {issues}"


# --- 2. provenance -------------------------------------------------------------


def test_committed_snapshot_provenance():
    snapshot = _snapshot()
    assert snapshot["snapshot_schema_version"] == SUPPORTED_SNAPSHOT_SCHEMA_VERSION
    assert snapshot["kind"] == "isaac-memory-snapshot"

    built_at_commit = snapshot["built_at_commit"]
    assert isinstance(built_at_commit, str)
    assert len(built_at_commit) == 40
    assert all(c in "0123456789abcdef" for c in built_at_commit)

    source_sha = snapshot["source_graph_sha256"]
    assert isinstance(source_sha, str)
    assert len(source_sha) == 64
    assert all(c in "0123456789abcdef" for c in source_sha)

    assert snapshot["overview"]["graph_mtime"] is None


# --- 3. projection consistency --------------------------------------------------


def test_committed_snapshot_projection_consistency():
    snapshot = _snapshot()

    concept_detail = snapshot["concept_detail"]
    for c in snapshot["concepts"]:
        assert c["id"] in concept_detail, f"concept id missing from concept_detail: {c['id']!r}"

    file_detail = snapshot["file_detail"]
    for f in snapshot["files"]:
        assert f["path"] in file_detail, f"file path missing from file_detail: {f['path']!r}"

    assert snapshot["served"] == sorted(f["path"] for f in snapshot["files"])


# --- 4. reader sanity: SanitizedSnapshotSource accepts the real file -----------


def test_committed_snapshot_readable_by_sanitized_snapshot_source():
    snapshot = _snapshot()
    reader = SanitizedSnapshotSource(SNAPSHOT_PATH)

    overview = reader.overview()
    assert overview["available"] is True
    assert overview["built_at_commit"] == snapshot["built_at_commit"]
    assert overview["concept_count"] == len(snapshot["concepts"])
    assert overview["served_file_count"] == len(snapshot["files"])

    assert len(reader.concepts()) == len(snapshot["concepts"])
    assert len(reader.files()) == len(snapshot["files"])

    # P24.10: the REAL committed snapshot predates memory_inputs (it is
    # regenerated to embed them only in the release slice), so it degrades
    # honestly: available + integrity=verified, but both provable freshness
    # concepts are "unknown" (no embedded fingerprint reference to prove against).
    # The full content-drift gate is a later slice; this only pins the status shape.
    status = reader.status()
    assert status["provider_kind"] == "sanitized-snapshot"
    assert status["available"] is True
    assert status["integrity"] == "verified"
    assert status["policy_consistency"] == "unknown"
    assert status["indexed_sources"] == "unknown"
    assert status["policy_fingerprint"] is None
    assert status["served_manifest_fingerprint"] is None

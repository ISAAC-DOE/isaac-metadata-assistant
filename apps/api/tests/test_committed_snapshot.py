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

P24.10 Slice 6 adds a CI-ONLY *indexed-source content-drift* gate over the same
committed artifact. Indexed-source drift is never a runtime authority (runtime
stays Graphify-free); this gate lives only in the test/CI plane. It is
dual-branch / backward-compatible by approved contract:

* **Branch A — snapshot WITHOUT ``memory_inputs`` (current reality).** Asserts
  honest graceful degradation via ``SanitizedSnapshotSource.status()``:
  available + integrity="verified", both provable freshness concepts "unknown",
  both fingerprints ``None`` (no embedded fingerprint reference to prove against).
* **Branch B — snapshot WITH ``memory_inputs`` (activates automatically once the
  release slice regenerates the real snapshot; no code change here).** Recomputes
  the served-content manifest over EXACTLY the paths already embedded in the
  snapshot and asserts, entry-for-entry, that nothing drifted, plus the aggregate
  served-manifest fingerprint, the shipped policy fingerprint, the served-file
  count, and the freshness constants. Deterministic, offline, and Graphify-free:
  it reads only the snapshot dict and the included served files, never
  ``graphify-out/``.

SCOPE LIMITATION (release brief): the gate hashes ONLY the files already included
in the snapshot — it recomputes over the manifest's own path set, not the current
repo's served set. Newly-added indexable files are not detected without a Graphify
refresh (documented limitation).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from isaac_api import memory
from isaac_api.memory import SUPPORTED_SNAPSHOT_SCHEMA_VERSION, SanitizedSnapshotSource


def _repo_root() -> Path:
    """Robustly locate the repo root by the vendored official schema (mirrors
    ``isaac_api.memory._find_repo_root``); never a hardcoded absolute path."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    return here.parents[3]


REPO_ROOT = _repo_root()
SCRIPT = REPO_ROOT / "scripts" / "build_memory_snapshot.py"
SNAPSHOT_PATH = REPO_ROOT / "apps" / "api" / "isaac_api" / "data" / "memory-snapshot.json"

# Golden fixture snapshot — already post-P24.10, i.e. it embeds ``memory_inputs``
# — plus the real served files it was generated over. Used to exercise the strict
# Branch-B gate GREEN *now*, before the real committed snapshot is regenerated to
# embed ``memory_inputs`` (the later release slice).
_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "memory_snapshot"
_GOLDEN_SNAPSHOT = _FIXTURE_ROOT / "memory-snapshot.json"
_GOLDEN_SERVED_ROOT = _FIXTURE_ROOT / "served_root"


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
    # The P24.10 status-degradation assertions live in the dual-branch dispatch
    # test below (``test_committed_snapshot_indexed_source_gate_dispatches``) so
    # they are not duplicated here, and so they run only while degradation is the
    # reality (Branch A). Once the snapshot is regenerated with ``memory_inputs``,
    # dispatch flips to the strict Branch-B content-drift gate automatically.


# --- 4b. every served/manifest/files path must be GIT-TRACKED ------------------
#
# Regression guard (P24.10 content-drift fix): the committed snapshot must
# reference ONLY git-tracked files. An untracked/gitignored file (e.g. a
# locally-present ``ux-review/`` report that Graphify happened to index)
# neither ships in the Docker image built from the git checkout nor exists in
# a fresh CI checkout, so the Branch-B content-drift gate cannot read its bytes
# there (``ValueError: served path missing/unreadable``). This asserts the
# invariant on ANY machine regardless of local disk state — unlike the Branch-B
# gate, which caught it only in CI because the dev disk happened to carry the
# untracked files.


def _git_tracked_paths() -> set:
    """Repo-root-relative POSIX paths tracked by git (``git ls-files -z``).
    Deterministic and Graphify-free: reads only the git index, never
    ``graphify-out/``. ``-z`` yields NUL-terminated, unquoted literal paths."""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True, check=True,
    )
    return {p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p}


def test_committed_snapshot_paths_are_all_git_tracked():
    snapshot = _snapshot()
    tracked = _git_tracked_paths()

    served_paths = set(snapshot["served"])
    file_paths = {f["path"] for f in snapshot["files"]}
    manifest_paths = {
        entry["path"]
        for entry in snapshot.get("memory_inputs", {}).get("served_content_manifest", [])
    }
    referenced = served_paths | file_paths | manifest_paths

    untracked = sorted(referenced - tracked)
    assert untracked == [], (
        "committed snapshot references non-git-tracked paths (they cannot ship in "
        f"the Docker image nor be verified in a fresh CI checkout): {untracked}"
    )


# --- 5. indexed-source content-drift gate (P24.10 Slice 6, CI-ONLY) ------------
#
# Test scaffolding that builds a ``memory_inputs`` block from the REAL
# ``isaac_api.memory`` primitives (never a hand-rolled/hardcoded fingerprint), so
# Branch B is exercised end-to-end against a snapshot shaped exactly like the one
# the generator emits (its nine ``memory_inputs`` keys).


def _write(root: Path, rel: str, data: bytes) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def _build_memory_inputs(paths, repo_root) -> dict:
    """Assemble a valid nine-key ``memory_inputs`` block over ``paths`` (relative
    to ``repo_root``) using ONLY the shipped ``isaac_api.memory`` primitives —
    identical to ``scripts/build_memory_snapshot.py``'s block."""
    manifest = memory.compute_served_content_manifest(paths, repo_root)
    return {
        "policy_fingerprint": memory.compute_memory_policy_fingerprint(),
        "policy_version": memory.MEMORY_INPUTS_POLICY_VERSION,
        "projection_version": memory.PROJECTION_VERSION,
        "fingerprint_algo_version": memory.FINGERPRINT_ALGO_VERSION,
        "served_manifest_fingerprint": memory.compute_served_manifest_fingerprint(manifest),
        "served_content_manifest": manifest,
        "served_file_count": len(manifest),
        "freshness_scope": "served_files_only",
        "freshness_basis": "ci_content_manifest",
    }


def _assert_branch_a_degradation() -> None:
    """Branch A (snapshot WITHOUT ``memory_inputs``): honest graceful degradation
    via the reader's ``status()`` — available + verified, both freshness concepts
    ``"unknown"``, both fingerprints ``None`` (no reference to prove against)."""
    status = SanitizedSnapshotSource(SNAPSHOT_PATH).status()
    assert status["provider_kind"] == "sanitized-snapshot"
    assert status["available"] is True
    assert status["integrity"] == "verified"
    assert status["policy_consistency"] == "unknown"
    assert status["indexed_sources"] == "unknown"
    assert status["policy_fingerprint"] is None
    assert status["served_manifest_fingerprint"] is None


def _assert_indexed_source_content_gate(snapshot: dict, repo_root) -> None:
    """Branch B: strict indexed-source content-drift + policy gate (CI-ONLY).

    Deterministic, offline, Graphify-free. Recomputes the served-content manifest
    over EXACTLY the paths already embedded in
    ``snapshot["memory_inputs"]["served_content_manifest"]`` (the included-files
    set) using the shipped ``isaac_api.memory`` primitives — reading the CURRENT
    bytes of those exact files under ``repo_root`` — and asserts nothing drifted.
    It reads only the passed-in ``snapshot`` dict and those included served files;
    it never reads ``graphify-out/`` or imports graphify. Raises ``AssertionError``
    on any drift (including a modified, missing, or deleted included file).

    SCOPE LIMITATION (release brief): the gate hashes ONLY the files already
    included in the snapshot — it recomputes over the manifest's own path set, not
    the current repo's served set. Newly-added indexable files are not detected
    without a Graphify refresh (documented limitation)."""
    mi = snapshot["memory_inputs"]
    assert isinstance(mi, dict), "memory_inputs must be an object"

    embedded_manifest = mi["served_content_manifest"]
    assert isinstance(embedded_manifest, list) and embedded_manifest, (
        "memory_inputs.served_content_manifest must be a non-empty list"
    )
    # (1)+(2) The manifest's own path set IS the authoritative included-files set;
    # recompute over EXACTLY those paths from their CURRENT on-disk bytes. A
    # missing/deleted/unsafe/unserved included file raises ValueError inside the
    # primitive -> surfaced as drift (an AssertionError, so callers can assert it).
    included_paths = [e["path"] for e in embedded_manifest]
    try:
        recomputed = memory.compute_served_content_manifest(included_paths, repo_root)
    except ValueError as exc:
        raise AssertionError(
            f"indexed-source drift: an included file is missing/unreadable/unsafe: {exc}"
        ) from exc

    # (3) Entry-for-entry (path + sha256) equality: any modified included file
    # changes its sha256 and trips this.
    assert recomputed == embedded_manifest, (
        "indexed-source drift: recomputed served-content manifest != embedded "
        "manifest (an included file's bytes changed)"
    )
    # (4) Aggregate served-manifest fingerprint matches.
    assert (
        memory.compute_served_manifest_fingerprint(recomputed)
        == mi["served_manifest_fingerprint"]
    ), "indexed-source drift: recomputed served_manifest_fingerprint mismatch"
    # (5) Shipped policy constants still match the snapshot's build-time policy.
    assert (
        memory.compute_memory_policy_fingerprint() == mi["policy_fingerprint"]
    ), "policy drift: runtime memory policy fingerprint != embedded policy_fingerprint"
    # (6) served_file_count is internally consistent with the manifest.
    assert mi["served_file_count"] == len(embedded_manifest), (
        "memory_inputs.served_file_count != len(served_content_manifest)"
    )
    # (7) Freshness axes carry the expected constant values.
    assert mi["freshness_scope"] == "served_files_only"
    assert mi["freshness_basis"] == "ci_content_manifest"


# --- 6. dual-branch dispatch over the REAL committed snapshot -------------------


def test_committed_snapshot_indexed_source_gate_dispatches():
    """The gate dispatches on ``memory_inputs`` presence in the committed snapshot:
    Branch A (current reality) vs Branch B (post-regen). No code change is needed
    when the real snapshot is regenerated to embed ``memory_inputs`` — this test
    starts exercising the strict gate against the real artifact automatically."""
    snapshot = _snapshot()
    if "memory_inputs" in snapshot:
        # Branch B: strict content-drift + policy gate over the real repo files.
        _assert_indexed_source_content_gate(snapshot, REPO_ROOT)
    else:
        # Branch A: current reality (snapshot predates memory_inputs).
        _assert_branch_a_degradation()


# --- 7. Branch B strict gate exercised GREEN now (fixture + synthesized) --------


def test_indexed_source_gate_passes_for_golden_fixture_snapshot():
    """The golden fixture snapshot already embeds ``memory_inputs`` and ships the
    real served files it was built over, so the strict Branch-B gate is GREEN
    against a genuine ``memory_inputs``-bearing snapshot today."""
    snapshot = json.loads(_GOLDEN_SNAPSHOT.read_text(encoding="utf-8"))
    assert "memory_inputs" in snapshot, "golden fixture must be post-P24.10"
    _assert_indexed_source_content_gate(snapshot, _GOLDEN_SERVED_ROOT)


def test_indexed_source_gate_passes_for_synthesized_consistent_snapshot(tmp_path):
    """A snapshot synthesized from the real primitives over an on-disk served set
    passes the strict gate — proving the Branch-B logic is exercised and correct
    before the real snapshot is regenerated."""
    _write(tmp_path, "src/alpha.py", b"print('alpha')\n")
    _write(tmp_path, "docs/beta.md", b"# beta\n")
    mi = _build_memory_inputs(["src/alpha.py", "docs/beta.md"], tmp_path)
    _assert_indexed_source_content_gate({"memory_inputs": mi}, tmp_path)


# --- 8. Branch B catches real drift (negative tests: the gate is not a no-op) ---


def test_indexed_source_gate_fails_when_included_file_bytes_change(tmp_path):
    _write(tmp_path, "src/alpha.py", b"print('alpha')\n")
    _write(tmp_path, "docs/beta.md", b"# beta\n")
    snapshot = {"memory_inputs": _build_memory_inputs(
        ["src/alpha.py", "docs/beta.md"], tmp_path)}
    _assert_indexed_source_content_gate(snapshot, tmp_path)  # green before drift
    (tmp_path / "src" / "alpha.py").write_bytes(b"print('alpha-CHANGED')\n")
    with pytest.raises(AssertionError):
        _assert_indexed_source_content_gate(snapshot, tmp_path)


def test_indexed_source_gate_fails_when_included_file_deleted(tmp_path):
    _write(tmp_path, "src/alpha.py", b"print('alpha')\n")
    _write(tmp_path, "docs/beta.md", b"# beta\n")
    snapshot = {"memory_inputs": _build_memory_inputs(
        ["src/alpha.py", "docs/beta.md"], tmp_path)}
    (tmp_path / "docs" / "beta.md").unlink()
    with pytest.raises(AssertionError):
        _assert_indexed_source_content_gate(snapshot, tmp_path)


def test_indexed_source_gate_fails_when_policy_fingerprint_stale(tmp_path):
    _write(tmp_path, "src/alpha.py", b"print('alpha')\n")
    mi = _build_memory_inputs(["src/alpha.py"], tmp_path)
    mi["policy_fingerprint"] = "0" * 64  # simulate a shipped-policy change
    with pytest.raises(AssertionError):
        _assert_indexed_source_content_gate({"memory_inputs": mi}, tmp_path)


def test_indexed_source_gate_fails_when_served_file_count_inconsistent(tmp_path):
    _write(tmp_path, "src/alpha.py", b"print('alpha')\n")
    mi = _build_memory_inputs(["src/alpha.py"], tmp_path)
    mi["served_file_count"] = mi["served_file_count"] + 1
    with pytest.raises(AssertionError):
        _assert_indexed_source_content_gate({"memory_inputs": mi}, tmp_path)


def test_indexed_source_gate_fails_when_aggregate_fingerprint_stale(tmp_path):
    _write(tmp_path, "src/alpha.py", b"print('alpha')\n")
    mi = _build_memory_inputs(["src/alpha.py"], tmp_path)
    mi["served_manifest_fingerprint"] = "f" * 64
    with pytest.raises(AssertionError):
        _assert_indexed_source_content_gate({"memory_inputs": mi}, tmp_path)


# --- 9. documented scope limitation: newly-added files are NOT detected ---------


def test_indexed_source_gate_does_not_detect_newly_added_files(tmp_path):
    """Encodes the approved scope boundary: the gate recomputes ONLY over the
    manifest's own included-path set, so adding a brand-new indexable served file
    that is NOT in the manifest leaves the gate GREEN.

    Newly-added indexable files are not detected without a Graphify refresh
    (documented limitation)."""
    _write(tmp_path, "src/alpha.py", b"print('alpha')\n")
    mi = _build_memory_inputs(["src/alpha.py"], tmp_path)
    snapshot = {"memory_inputs": mi}
    # A new, served, indexable file appears in the repo but not in the manifest.
    _write(tmp_path, "src/gamma.py", b"print('gamma')\n")
    # Still green: the gate does not scan the current repo's served set.
    _assert_indexed_source_content_gate(snapshot, tmp_path)


# --- 10. the gate is Graphify-free (never imports graphify / reads graphify-out) -


_ALLOWED_IMPORT_ROOTS = {
    "__future__", "ast", "importlib", "json", "subprocess", "pathlib", "pytest",
    "isaac_api",
}


def test_indexed_source_gate_module_is_graphify_free():
    """The whole gate module imports no ``graphify`` (and only stdlib + pytest +
    the Graphify-free ``isaac_api`` reader): the gate reads only the snapshot dict
    and the included served files, never ``graphify-out/``."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
    assert "graphify" not in roots, f"gate must not import graphify (saw {roots})"
    assert roots <= _ALLOWED_IMPORT_ROOTS, (
        f"unexpected imports in gate module: {roots - _ALLOWED_IMPORT_ROOTS}"
    )

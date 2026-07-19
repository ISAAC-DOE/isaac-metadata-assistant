"""Tests for ``scripts/build_memory_snapshot.py`` — the deterministic sanitized
Project Memory snapshot generator (memory plane, P24.9-impl-1).

The generator reuses ``isaac_api.memory.LocalGraphArtifactSource`` (never
re-derives graph logic) and drives its six public methods over a small,
unmistakably-fake committed fixture graph under
``tests/fixtures/memory_snapshot/graph/``. It must never import
``isaac_records`` or ``graphify``, must be byte-deterministic, must force
``on_disk: false`` everywhere, must null ``graph_mtime`` (never an epoch/live
timestamp), must cap+truncate ``rationales`` strings, and must fail closed
(abort, write nothing) on any secret/governance-excluded/absolute-path leak.

The script is loaded via ``importlib.util.spec_from_file_location`` — the same
pattern ``tests/test_graphify_freshness.py`` uses for
``scripts/check_graphify_freshness.py`` — since ``scripts/`` is not a package.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from isaac_api import memory as isaac_memory

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "build_memory_snapshot.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "memory_snapshot"
FIXTURE_GRAPH_DIR = FIXTURE_DIR / "graph"
GOLDEN_SNAPSHOT = FIXTURE_DIR / "memory-snapshot.json"
#: Committed directory holding REAL bytes for the graph fixture's three served
#: paths (docs/fake_notes.md, src/fake_widget.py, src/fake_helper.py) — the
#: synthetic fixture graph references paths that do not exist under the real
#: repo root, so the served-content manifest (P24.10 Slice 2) needs its own
#: fixed, committed "repo root" to read bytes from.
FIXTURE_SERVED_ROOT = FIXTURE_DIR / "served_root"

FORBIDDEN_VERDICT_KEYS = {"ok", "valid", "passed", "verdict", "schema", "errors"}


def _load():
    spec = importlib.util.spec_from_file_location("build_memory_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load()


def _walk_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)
    elif isinstance(obj, str):
        yield obj


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def _walk_on_disk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "on_disk":
                yield v
            yield from _walk_on_disk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_on_disk(v)


@pytest.fixture()
def snapshot() -> dict:
    """The snapshot built directly from the committed fixture graph, reading
    served-content bytes from the committed ``served_root`` fixture (the
    synthetic graph's served paths do not exist under the real repo root)."""
    return gen.build_snapshot(FIXTURE_GRAPH_DIR, FIXTURE_SERVED_ROOT)


# --- 1. shape / schema validity -------------------------------------------


def test_top_level_keys_exact(snapshot):
    assert set(snapshot.keys()) == {
        "snapshot_schema_version", "kind", "generator",
        "built_at_commit", "source_graph_sha256",
        "overview", "concepts", "concept_detail",
        "files", "file_detail", "served",
        "memory_inputs",
    }


def test_shape_validation_passes(snapshot):
    assert gen._validate_shape(snapshot) == []


def test_kind_and_schema_version(snapshot):
    assert snapshot["kind"] == "isaac-memory-snapshot"
    assert snapshot["snapshot_schema_version"] == 1
    assert isinstance(snapshot["snapshot_schema_version"], int)


def test_generator_field_is_relative_script_path(snapshot):
    assert snapshot["generator"] == "scripts/build_memory_snapshot.py"


def test_built_at_commit_and_sha256(snapshot):
    assert snapshot["built_at_commit"] == "fakecommitp24900"
    raw = (FIXTURE_GRAPH_DIR / "graph.json").read_bytes()
    import hashlib
    assert snapshot["source_graph_sha256"] == hashlib.sha256(raw).hexdigest()


def test_overview_shape(snapshot):
    ov = snapshot["overview"]
    assert ov["built_at_commit"] == "fakecommitp24900"
    assert ov["node_count"] == 10
    assert ov["edge_count"] == 5
    assert ov["community_count"] == 3
    assert ov["concept_count"] == 3
    assert ov["served_file_count"] == 3
    assert ov["manifest_file_count"] == 4


def test_shape_invalid_when_top_level_key_missing(snapshot):
    broken = dict(snapshot)
    del broken["served"]
    issues = gen._validate_shape(broken)
    assert issues
    assert any("served" in i for i in issues)


def test_shape_invalid_when_overview_graph_mtime_not_null(snapshot):
    broken = copy.deepcopy(snapshot)
    broken["overview"]["graph_mtime"] = 123.0
    issues = gen._validate_shape(broken)
    assert issues
    assert any("graph_mtime" in i for i in issues)


# --- 2. graph_mtime is null, never epoch/positive --------------------------


def test_graph_mtime_is_null_never_epoch(snapshot):
    assert "graph_mtime" not in snapshot  # no top-level graph_mtime at all
    assert snapshot["overview"]["graph_mtime"] is None
    assert snapshot["overview"]["graph_mtime"] != 0.0


# --- 3. on_disk forced false everywhere ------------------------------------


def test_on_disk_false_everywhere_even_when_real_file_exists(tmp_path):
    """Create a REAL file on disk at the served path so the live reader would
    naturally report on_disk=True; the generator must still force False."""
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "fake_notes.md").write_text("# fake\n", encoding="utf-8")
    # The other two served paths (src/fake_widget.py, src/fake_helper.py) need
    # SOME real bytes too, so the served-content manifest can be built.
    shutil.copytree(FIXTURE_SERVED_ROOT / "src", tmp_path / "src")
    snap = gen.build_snapshot(FIXTURE_GRAPH_DIR, tmp_path)
    on_disk_values = list(_walk_on_disk(snap))
    assert on_disk_values, "expected at least one on_disk field"
    assert all(v is False for v in on_disk_values)


# --- 4. excluded-path absence -----------------------------------------------


def test_excluded_paths_never_appear(snapshot):
    haystack = list(_walk_strings(snapshot))
    assert not any(s.startswith("examples/") for s in haystack)
    assert not any(".superpowers/" in s for s in haystack)
    assert "examples/README.md" not in snapshot["served"]
    assert "examples/README.md" not in snapshot["file_detail"]
    assert all(f["path"] != "examples/README.md" for f in snapshot["files"])


def test_excluded_concept_anchor_is_null(snapshot):
    detail = snapshot["concept_detail"]["concept_fake_excluded"]
    assert detail["source_file"] is None
    summary = next(c for c in snapshot["concepts"] if c["id"] == "concept_fake_excluded")
    assert summary["source_file"] is None


def test_absolute_anchored_concept_is_null(snapshot):
    detail = snapshot["concept_detail"]["concept_fake_absolute"]
    assert detail["source_file"] is None


def test_excluded_related_file_dropped(snapshot):
    widget = snapshot["file_detail"]["src/fake_widget.py"]
    paths = [f["path"] for f in widget["related"]["files"]]
    assert "examples/README.md" not in paths
    assert "src/fake_helper.py" in paths  # the kept neighbor survives


def test_equal_weight_tie_related_relation_is_canonical(snapshot):
    """The fixture has two EQUAL-WEIGHT (6.0) edges from src/fake_widget.py to
    src/fake_helper.py — 'imports' and 'calls'. The retained relation must be
    the canonical (lexicographically smallest) 'calls', never the first-seen
    one, so the value is order/hash-seed independent."""
    widget = snapshot["file_detail"]["src/fake_widget.py"]
    helper = next(f for f in widget["related"]["files"] if f["path"] == "src/fake_helper.py")
    assert helper["relation"] == "calls"  # min(("calls",..), ("imports",..))


def test_cross_process_determinism_differing_hash_seeds(tmp_path):
    """Two subprocess runs of the generator under DIFFERENT PYTHONHASHSEED values
    must produce byte-identical snapshots (the equal-weight tie above would flip
    run-to-run under the old first-seen accumulator)."""
    import hashlib
    import os

    shas = []
    for seed in ("0", "1"):
        out = tmp_path / f"snap-{seed}.json"
        env = dict(os.environ, PYTHONHASHSEED=seed)
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--graph-dir", str(FIXTURE_GRAPH_DIR),
             "--out", str(out),
             "--repo-root", str(FIXTURE_SERVED_ROOT)],
            capture_output=True, text=True, timeout=60, env=env,
        )
        assert result.returncode == 0, result.stderr
        shas.append(hashlib.sha256(out.read_bytes()).hexdigest())
    assert shas[0] == shas[1], f"non-deterministic across hash seeds: {shas}"


# --- 5. absolute / traversal path absence -----------------------------------


def test_no_absolute_or_traversal_paths_anywhere(snapshot):
    for s in _walk_strings(snapshot):
        assert not s.startswith("/"), s
        assert not s.startswith("~"), s
        assert ".." not in s.split("/"), s


def test_scan_clean_on_good_snapshot(snapshot):
    assert gen._scan_for_leaks(snapshot, repo_root=REPO_ROOT) == []


# --- 6. secret / governance scan aborts -------------------------------------


def test_scan_catches_private_key_marker(snapshot):
    bad = copy.deepcopy(snapshot)
    bad["file_detail"]["src/fake_widget.py"]["rationales"][0] = (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n-----END RSA PRIVATE KEY-----"
    )
    issues = gen._scan_for_leaks(bad, repo_root=REPO_ROOT)
    assert issues


def test_scan_catches_aws_credential_pattern(snapshot):
    bad = copy.deepcopy(snapshot)
    bad["concept_detail"]["concept_fake_alpha"]["label"] = "leaked AKIAABCDEFGHIJKLMNOP token"
    issues = gen._scan_for_leaks(bad, repo_root=REPO_ROOT)
    assert issues


def test_scan_catches_absolute_path_value(snapshot):
    bad = copy.deepcopy(snapshot)
    bad["served"].append("/etc/passwd")
    issues = gen._scan_for_leaks(bad, repo_root=REPO_ROOT)
    assert issues


def test_scan_catches_home_directory_marker(snapshot):
    bad = copy.deepcopy(snapshot)
    bad["file_detail"]["src/fake_widget.py"]["rationales"][0] = (
        "see /Users/someone/secret-notes for details"
    )
    issues = gen._scan_for_leaks(bad, repo_root=REPO_ROOT)
    assert issues


def test_scan_catches_non_served_path_injected(snapshot):
    bad = copy.deepcopy(snapshot)
    bad["served"].append("examples/sneaky.md")
    issues = gen._scan_for_leaks(bad, repo_root=REPO_ROOT)
    assert issues


def test_scan_allows_slash_command_label_but_rejects_absolute_source_file(snapshot):
    """A slash-command CONCEPT LABEL that legitimately starts with '/'
    (e.g. '/isaac-export') is NOT a leak — path-shape rules apply only to
    path-bearing fields. But an absolute path in a path-bearing field
    (concept source_file '/etc/passwd') is still rejected."""
    ok = copy.deepcopy(snapshot)
    ok["concept_detail"]["concept_fake_alpha"]["label"] = "/isaac-export"
    ok["concepts"] = [
        (dict(c, label="/isaac-export") if c["id"] == "concept_fake_alpha" else c)
        for c in ok["concepts"]
    ]
    assert gen._scan_for_leaks(ok, repo_root=REPO_ROOT) == []

    bad = copy.deepcopy(snapshot)
    bad["concept_detail"]["concept_fake_alpha"]["source_file"] = "/etc/passwd"
    assert gen._scan_for_leaks(bad, repo_root=REPO_ROOT)


def test_real_slash_command_labels_pass_scan(snapshot):
    """Exact labels that reproduced the false positive against the real graph."""
    ok = copy.deepcopy(snapshot)
    for lbl in ("/isaac-export", "/isaac-draft — Fast Draft Mode",
                "/isaac-complete — Validated Minimum Mode", "/isaac-validate"):
        ok["file_detail"]["src/fake_widget.py"]["rationales"] = [lbl]
        assert gen._scan_for_leaks(ok, repo_root=REPO_ROOT) == [], lbl


def test_scan_catches_secret_straddling_truncation_via_extra_strings(snapshot):
    """A secret in the ORIGINAL (un-truncated) rationale must be caught even if
    the emitted (truncated) value only shows a harmless fragment. The scan
    receives the originals via extra_strings."""
    original = "x" * 275 + "AKIAABCDEFGHIJKLMNOP tail"  # AWS token past the 280 cut
    truncated = gen._truncate_rationale(original)
    clean = copy.deepcopy(snapshot)
    clean["file_detail"]["src/fake_widget.py"]["rationales"] = [truncated]
    # emitted/truncated value alone is clean...
    assert gen._scan_for_leaks(clean, repo_root=REPO_ROOT) == []
    # ...but scanning the original via extra_strings catches it.
    issues = gen._scan_for_leaks(clean, repo_root=REPO_ROOT, extra_strings=[original])
    assert issues


def test_cli_aborts_on_secret_straddling_truncation(tmp_path):
    """End-to-end: a graph whose rationale hides an AWS token past the 280 cut
    still aborts the CLI (non-zero, writes nothing)."""
    poisoned_dir = tmp_path / "graph"
    poisoned_dir.mkdir()
    graph = json.loads((FIXTURE_GRAPH_DIR / "graph.json").read_text(encoding="utf-8"))
    for node in graph["nodes"]:
        if node["id"] == "src_fake_widget_rationale_long":
            node["label"] = "y" * 300 + " AKIAABCDEFGHIJKLMNOP embedded-past-the-cut"
    (poisoned_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    for name in ("manifest.json", ".graphify_labels.json"):
        (poisoned_dir / name).write_text(
            (FIXTURE_GRAPH_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    # repo_root=tmp_path must carry real bytes for the manifest's served paths
    # so the CLI aborts on the SECRET SCAN, not on a missing-file error.
    shutil.copytree(FIXTURE_SERVED_ROOT, tmp_path, dirs_exist_ok=True)
    out_path = tmp_path / "memory-snapshot.json"
    rc = gen.main([
        "--graph-dir", str(poisoned_dir),
        "--out", str(out_path),
        "--repo-root", str(tmp_path),
    ])
    assert rc != 0
    assert not out_path.exists()


def test_scan_catches_windows_machine_marker_mid_string(snapshot):
    bad = copy.deepcopy(snapshot)
    bad["file_detail"]["src/fake_widget.py"]["rationales"][0] = (
        "referenced from C:\\Users\\dev\\project mid-string"
    )
    assert gen._scan_for_leaks(bad, repo_root=REPO_ROOT)


def test_scan_catches_forbidden_verdict_key(snapshot):
    bad = copy.deepcopy(snapshot)
    bad["verdict"] = "valid"
    issues = gen._scan_for_leaks(bad, repo_root=REPO_ROOT)
    assert issues


def test_scan_catches_on_disk_true(snapshot):
    bad = copy.deepcopy(snapshot)
    bad["files"][0]["on_disk"] = True
    issues = gen._scan_for_leaks(bad, repo_root=REPO_ROOT)
    assert issues


def test_cli_aborts_nonzero_and_writes_nothing_on_planted_secret(tmp_path):
    """End-to-end: a poisoned copy of the fixture graph (rationale containing an
    AWS-shaped credential token) must make the CLI abort non-zero and must
    never create the --out file."""
    poisoned_dir = tmp_path / "graph"
    poisoned_dir.mkdir()
    graph = json.loads((FIXTURE_GRAPH_DIR / "graph.json").read_text(encoding="utf-8"))
    for node in graph["nodes"]:
        if node["id"] == "src_fake_widget_rationale_short":
            node["label"] = "leaked token AKIAABCDEFGHIJKLMNOP in a comment"
    (poisoned_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (poisoned_dir / "manifest.json").write_text(
        (FIXTURE_GRAPH_DIR / "manifest.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (poisoned_dir / ".graphify_labels.json").write_text(
        (FIXTURE_GRAPH_DIR / ".graphify_labels.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # repo_root=tmp_path must carry real bytes for the manifest's served paths
    # so the CLI aborts on the SECRET SCAN, not on a missing-file error.
    shutil.copytree(FIXTURE_SERVED_ROOT, tmp_path, dirs_exist_ok=True)
    out_path = tmp_path / "memory-snapshot.json"
    rc = gen.main([
        "--graph-dir", str(poisoned_dir),
        "--out", str(out_path),
        "--repo-root", str(tmp_path),
    ])
    assert rc != 0
    assert not out_path.exists()


# --- 7. rationale truncation -------------------------------------------------


def test_max_rationale_chars_constant():
    assert gen.MAX_RATIONALE_CHARS == 280


def test_rationale_truncation_deterministic(snapshot):
    rationales = snapshot["file_detail"]["src/fake_widget.py"]["rationales"]
    short, long_ = rationales[0], rationales[1]
    assert short == "Short fake rationale about the widget module."  # unchanged
    assert len(long_) == gen.MAX_RATIONALE_CHARS
    assert long_.endswith("…")  # trailing ellipsis marks truncation
    raw = json.loads((FIXTURE_GRAPH_DIR / "graph.json").read_text(encoding="utf-8"))
    original = next(
        n["label"] for n in raw["nodes"] if n["id"] == "src_fake_widget_rationale_long"
    )
    assert long_ == original[: gen.MAX_RATIONALE_CHARS - 1] + "…"


def test_rationale_truncation_stable_across_runs():
    a = gen.build_snapshot(FIXTURE_GRAPH_DIR, FIXTURE_SERVED_ROOT)
    b = gen.build_snapshot(FIXTURE_GRAPH_DIR, FIXTURE_SERVED_ROOT)
    ra = a["file_detail"]["src/fake_widget.py"]["rationales"]
    rb = b["file_detail"]["src/fake_widget.py"]["rationales"]
    assert ra == rb


# --- 8. projection consistency ----------------------------------------------


def test_concepts_array_matches_concept_detail_projection(snapshot):
    for c in snapshot["concepts"]:
        detail = dict(snapshot["concept_detail"][c["id"]])
        detail.pop("related", None)
        assert c == detail


def test_files_array_matches_file_detail_projection(snapshot):
    for f in snapshot["files"]:
        detail = dict(snapshot["file_detail"][f["path"]])
        detail.pop("related", None)
        detail.pop("rationales", None)
        detail.pop("local_reference", None)
        assert f == detail


def test_served_matches_sorted_file_paths(snapshot):
    assert snapshot["served"] == sorted(f["path"] for f in snapshot["files"])
    assert snapshot["served"] == sorted(snapshot["served"])


def test_projection_consistency_check_raises_on_mismatch(snapshot):
    concepts_list = copy.deepcopy(snapshot["concepts"])
    concept_detail = copy.deepcopy(snapshot["concept_detail"])
    concepts_list[0]["label"] = "TAMPERED"
    with pytest.raises(gen.SnapshotError):
        gen._check_projection_consistency(
            concepts_list, concept_detail, snapshot["files"], snapshot["file_detail"]
        )


def test_projection_consistency_check_passes_on_good_data(snapshot):
    gen._check_projection_consistency(
        snapshot["concepts"], snapshot["concept_detail"],
        snapshot["files"], snapshot["file_detail"],
    )  # must not raise


# --- 9. no content/verdict keys anywhere ------------------------------------


def test_no_content_lines_or_verdict_keys(snapshot):
    keys = set(_walk_keys(snapshot))
    assert "content" not in keys
    assert "lines" not in keys
    assert keys.isdisjoint(FORBIDDEN_VERDICT_KEYS)


# --- 10. determinism ----------------------------------------------------------


def test_determinism_byte_identical_twice():
    a = gen.build_snapshot(FIXTURE_GRAPH_DIR, FIXTURE_SERVED_ROOT)
    b = gen.build_snapshot(FIXTURE_GRAPH_DIR, FIXTURE_SERVED_ROOT)
    assert gen._serialize(a) == gen._serialize(b)


def test_serialize_is_sorted_keys_with_trailing_newline(snapshot):
    payload = gen._serialize(snapshot)
    text = payload.decode("utf-8")
    assert text.endswith("\n")
    reparsed = json.loads(text)
    assert reparsed == snapshot


# --- 11. --check mode ---------------------------------------------------------


def test_check_passes_on_matching_golden_fixture():
    assert GOLDEN_SNAPSHOT.exists(), "golden fixture snapshot must be committed"
    rc = gen.main([
        "--graph-dir", str(FIXTURE_GRAPH_DIR),
        "--out", str(GOLDEN_SNAPSHOT),
        "--repo-root", str(FIXTURE_SERVED_ROOT),
        "--check",
    ])
    assert rc == 0


def test_check_fails_on_drifted_snapshot(tmp_path):
    drifted = tmp_path / "memory-snapshot.json"
    payload = GOLDEN_SNAPSHOT.read_bytes()
    mutated = payload.replace(b"fakecommitp24900", b"fakecommitDRIFTED")
    assert mutated != payload
    drifted.write_bytes(mutated)
    rc = gen.main([
        "--graph-dir", str(FIXTURE_GRAPH_DIR),
        "--out", str(drifted),
        "--repo-root", str(FIXTURE_SERVED_ROOT),
        "--check",
    ])
    assert rc != 0


def test_check_fails_on_malformed_target(tmp_path):
    malformed = tmp_path / "memory-snapshot.json"
    malformed.write_text("{not valid json", encoding="utf-8")
    rc = gen.main([
        "--graph-dir", str(FIXTURE_GRAPH_DIR),
        "--out", str(malformed),
        "--repo-root", str(FIXTURE_SERVED_ROOT),
        "--check",
    ])
    assert rc != 0


def test_check_never_writes(tmp_path):
    target = tmp_path / "memory-snapshot.json"
    gen.main([
        "--graph-dir", str(FIXTURE_GRAPH_DIR),
        "--out", str(target),
        "--repo-root", str(FIXTURE_SERVED_ROOT),
        "--check",
    ])
    assert not target.exists()


def test_write_is_atomic_no_tmp_left_behind(tmp_path):
    out_path = tmp_path / "memory-snapshot.json"
    rc = gen.main([
        "--graph-dir", str(FIXTURE_GRAPH_DIR),
        "--out", str(out_path),
        "--repo-root", str(FIXTURE_SERVED_ROOT),
    ])
    assert rc == 0
    assert out_path.exists()
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != out_path.name]
    assert leftovers == [], f"temp files left behind: {leftovers}"


def test_generate_then_check_round_trip(tmp_path):
    out_path = tmp_path / "memory-snapshot.json"
    rc1 = gen.main([
        "--graph-dir", str(FIXTURE_GRAPH_DIR),
        "--out", str(out_path),
        "--repo-root", str(FIXTURE_SERVED_ROOT),
    ])
    assert rc1 == 0
    assert out_path.exists()
    rc2 = gen.main([
        "--graph-dir", str(FIXTURE_GRAPH_DIR),
        "--out", str(out_path),
        "--repo-root", str(FIXTURE_SERVED_ROOT),
        "--check",
    ])
    assert rc2 == 0


# --- 12. CLI subprocess smoke -------------------------------------------------


def test_cli_subprocess_smoke(tmp_path):
    out_path = tmp_path / "memory-snapshot.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--graph-dir", str(FIXTURE_GRAPH_DIR),
         "--out", str(out_path),
         "--repo-root", str(FIXTURE_SERVED_ROOT)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["kind"] == "isaac-memory-snapshot"


# --- 13. isolation invariant ---------------------------------------------------


_FORBIDDEN_ROOTS = {"isaac_records", "graphify"}


def test_generator_does_not_import_truth_core_or_graphify():
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
    assert roots.isdisjoint(_FORBIDDEN_ROOTS), f"forbidden imports: {roots & _FORBIDDEN_ROOTS}"


def test_generator_imports_memory_module():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "from isaac_api import memory" in source or "isaac_api.memory" in source


# --- 14. memory_inputs fingerprint block (P24.10 Slice 2) ---------------------


_MEMORY_INPUTS_KEYS = {
    "policy_fingerprint", "policy_version", "projection_version",
    "fingerprint_algo_version", "served_manifest_fingerprint",
    "served_content_manifest", "served_file_count",
    "freshness_scope", "freshness_basis",
}


def test_max_rationale_chars_is_the_memory_module_constant():
    """Single source of truth (P24.10 Slice 2): the generator must not
    re-define its own ``280`` literal — it must reference
    ``isaac_api.memory.MAX_RATIONALE_CHARS`` so the runtime reader and the
    build-time generator can never drift apart."""
    assert gen.MAX_RATIONALE_CHARS == isaac_memory.MAX_RATIONALE_CHARS
    source = SCRIPT.read_text(encoding="utf-8")
    assert "280" not in source, "MAX_RATIONALE_CHARS must not be a re-declared literal"


def test_memory_inputs_present_with_exact_keys(snapshot):
    mi = snapshot["memory_inputs"]
    assert set(mi.keys()) == _MEMORY_INPUTS_KEYS


def test_memory_inputs_policy_fingerprint_matches_memory_module(snapshot):
    mi = snapshot["memory_inputs"]
    assert mi["policy_fingerprint"] == isaac_memory.compute_memory_policy_fingerprint()
    assert mi["policy_version"] == isaac_memory.MEMORY_INPUTS_POLICY_VERSION
    assert mi["projection_version"] == isaac_memory.PROJECTION_VERSION
    assert mi["fingerprint_algo_version"] == isaac_memory.FINGERPRINT_ALGO_VERSION


def test_memory_inputs_served_manifest_fingerprint_matches_memory_module(snapshot):
    mi = snapshot["memory_inputs"]
    expected = isaac_memory.compute_served_manifest_fingerprint(mi["served_content_manifest"])
    assert mi["served_manifest_fingerprint"] == expected


def test_memory_inputs_served_file_count_matches_manifest_length(snapshot):
    mi = snapshot["memory_inputs"]
    assert mi["served_file_count"] == len(mi["served_content_manifest"])


def test_memory_inputs_freshness_scope_and_basis(snapshot):
    mi = snapshot["memory_inputs"]
    assert mi["freshness_scope"] == "served_files_only"
    assert mi["freshness_basis"] == "ci_content_manifest"


def test_memory_inputs_manifest_covers_exactly_the_served_fixture_files(snapshot):
    """The manifest built from the fixture graph must cover exactly the three
    served fixture paths (examples/README.md is governance-excluded and never
    reaches ``served``), and each sha256 must match the real fixture bytes
    under FIXTURE_SERVED_ROOT."""
    manifest = snapshot["memory_inputs"]["served_content_manifest"]
    paths = [e["path"] for e in manifest]
    assert paths == sorted(snapshot["served"])
    assert paths == ["docs/fake_notes.md", "src/fake_helper.py", "src/fake_widget.py"]
    for entry in manifest:
        raw = (FIXTURE_SERVED_ROOT / entry["path"]).read_bytes()
        assert entry["sha256"] == hashlib.sha256(raw).hexdigest()


def test_memory_inputs_manifest_is_a_list_of_path_sha256_dicts(snapshot):
    manifest = snapshot["memory_inputs"]["served_content_manifest"]
    assert isinstance(manifest, list)
    for entry in manifest:
        assert set(entry.keys()) == {"path", "sha256"}
        assert isinstance(entry["path"], str)
        assert isinstance(entry["sha256"], str)
        assert len(entry["sha256"]) == 64


def test_memory_inputs_deterministic_across_two_builds():
    a = gen.build_snapshot(FIXTURE_GRAPH_DIR, FIXTURE_SERVED_ROOT)
    b = gen.build_snapshot(FIXTURE_GRAPH_DIR, FIXTURE_SERVED_ROOT)
    assert a["memory_inputs"] == b["memory_inputs"]
    assert gen._serialize(a) == gen._serialize(b)


# -- self-exclusion: the snapshot must never embed its own digest ------------


def test_manifest_paths_excludes_any_memory_snapshot_json_artifact():
    """Any served path that IS a ``*memory-snapshot.json`` artifact is dropped
    regardless of ``out_path`` — embedding the snapshot's own digest is
    circular by construction, not just when the names happen to collide."""
    served = ["docs/a.md", "data/memory-snapshot.json", "src/b.py"]
    kept = gen._manifest_paths(served, repo_root=FIXTURE_SERVED_ROOT, out_path=None)
    assert kept == ["docs/a.md", "src/b.py"]


def test_manifest_paths_excludes_out_path_relative_to_repo_root(tmp_path):
    """The CLI's own ``--out`` target, when it happens to fall inside
    ``repo_root`` at a served-looking relative path, must be excluded too —
    not just names ending in the literal ``memory-snapshot.json`` string."""
    served = ["docs/a.md", "reports/weekly.json", "src/b.py"]
    out_path = tmp_path / "reports" / "weekly.json"
    kept = gen._manifest_paths(served, repo_root=tmp_path, out_path=out_path)
    assert kept == ["docs/a.md", "src/b.py"]


def test_manifest_paths_out_path_outside_repo_root_excludes_nothing_extra(tmp_path):
    """When ``--out`` resolves OUTSIDE ``repo_root`` (the common case in these
    tests), there is nothing to exclude via the relative-path rule, and the
    function must not raise."""
    served = ["docs/a.md", "src/b.py"]
    out_path = tmp_path / "elsewhere" / "memory-snapshot-copy.txt"
    kept = gen._manifest_paths(served, repo_root=FIXTURE_SERVED_ROOT, out_path=out_path)
    assert kept == served


def test_build_snapshot_excludes_out_path_from_served_content_manifest():
    """End-to-end: passing ``out_path`` equal to one of the fixture's OWN
    served files must exclude that file from the served_content_manifest
    (self-exclusion), while leaving the top-level ``served``/``files`` lists
    (unrelated to memory_inputs) untouched."""
    coinciding_out = FIXTURE_SERVED_ROOT / "src" / "fake_widget.py"
    snap = gen.build_snapshot(FIXTURE_GRAPH_DIR, FIXTURE_SERVED_ROOT, out_path=coinciding_out)
    manifest_paths = [e["path"] for e in snap["memory_inputs"]["served_content_manifest"]]
    assert "src/fake_widget.py" not in manifest_paths
    assert manifest_paths == ["docs/fake_notes.md", "src/fake_helper.py"]
    # unaffected: the reader-derived served/files lists still list all three
    assert "src/fake_widget.py" in snap["served"]


# -- shape validation: memory_inputs is additive (backward compatible) -------


def test_shape_validation_passes_without_memory_inputs_key(snapshot):
    """A pre-P24.10 snapshot lacking ``memory_inputs`` entirely (e.g. the
    already-committed hosted snapshot, regenerated by a later release slice)
    must still validate cleanly — no schema version bump, purely additive."""
    legacy = dict(snapshot)
    del legacy["memory_inputs"]
    assert gen._validate_shape(legacy) == []


def test_shape_invalid_when_memory_inputs_is_not_an_object(snapshot):
    broken = copy.deepcopy(snapshot)
    broken["memory_inputs"] = "not-an-object"
    issues = gen._validate_shape(broken)
    assert issues
    assert any("memory_inputs" in i for i in issues)


def test_shape_invalid_when_memory_inputs_keys_mismatch(snapshot):
    broken = copy.deepcopy(snapshot)
    del broken["memory_inputs"]["served_file_count"]
    issues = gen._validate_shape(broken)
    assert issues
    assert any("memory_inputs" in i for i in issues)


# -- leak scan: manifest paths are covered by the path-shape rule ------------


def test_scan_catches_unsafe_path_injected_into_served_content_manifest(snapshot):
    bad = copy.deepcopy(snapshot)
    bad["memory_inputs"]["served_content_manifest"].append(
        {"path": "/etc/passwd", "sha256": "0" * 64}
    )
    issues = gen._scan_for_leaks(bad, repo_root=REPO_ROOT)
    assert issues


def test_scan_clean_on_good_snapshot_with_memory_inputs(snapshot):
    assert gen._scan_for_leaks(snapshot, repo_root=REPO_ROOT) == []

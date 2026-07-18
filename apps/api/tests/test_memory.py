"""Tests for the stdlib-only Project Memory reader (``isaac_api.memory``).

The reader is a read-only provenance view over the Graphify artifacts
(``graph.json`` / ``manifest.json`` / ``.graphify_labels.json``). It never
validates, never serves file content, and degrades honestly when artifacts are
absent or malformed. These tests run against tiny, unmistakably-fake synthetic
artifacts built in ``tmp_path`` (fake paths, fake commit ``fakecommit0000``),
plus one conditional smoke test against the real local graph when present.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from isaac_api import memory
from isaac_api.memory import LocalGraphArtifactSource

# --- synthetic-fixture builders (unmistakably fake) ---------------------------

FORBIDDEN_VERDICT_KEYS = {"ok", "valid", "passed", "verdict", "schema", "errors"}


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
        {"id": "src_fake_mod_func", "label": "do_thing()", "file_type": "code",
         "community": 3, "source_file": "src/fake_mod.py", "source_location": "L10"},
        {"id": "src_fake_mod_rationale_1", "label": "Fake rationale about the module.",
         "file_type": "rationale", "community": 3, "source_file": "src/fake_mod.py",
         "source_location": "L1"},
        {"id": "src_other_mod", "label": "other_mod.py", "file_type": "code",
         "community": 5, "source_file": "src/other_mod.py", "source_location": "L1"},
    ]
    links = [
        {"source": "concept_alpha", "target": "src_fake_mod", "relation": "references",
         "weight": 5.0, "source_file": "docs/fake-note.md"},
        {"source": "concept_alpha", "target": "src_other_mod", "relation": "mentions",
         "weight": 2.0, "source_file": "docs/fake-note.md"},
        {"source": "concept_alpha", "target": "concept_beta", "relation": "relates_to",
         "weight": 3.0, "source_file": "docs/fake-note.md"},
        {"source": "src_fake_mod", "target": "src_other_mod", "relation": "imports",
         "weight": 4.0, "source_file": "src/fake_mod.py"},
        {"source": "src_fake_mod", "target": "concept_alpha", "relation": "references",
         "weight": 1.0, "source_file": "src/fake_mod.py"},
        {"source": "src_fake_mod", "target": "src_fake_mod_func", "relation": "contains",
         "weight": 1.0, "source_file": "src/fake_mod.py"},
        {"source": "src_fake_mod_rationale_1", "target": "src_fake_mod",
         "relation": "rationale_for", "weight": 1.0, "source_file": "src/fake_mod.py"},
    ]
    return {"nodes": nodes, "links": links, "built_at_commit": "fakecommit0000"}


def _synthetic_manifest() -> dict:
    keys = [
        "docs/fake-note.md",
        "src/fake_mod.py",
        "src/other_mod.py",
        # governance-excluded (present in raw manifest, must not surface):
        "examples/README.md",
        ".superpowers/sdd/x.md",
        "apps/web/.vercel/project.json",
        ".claude/settings.local.json",
        "ux-review/shot.png",
        # kept (documented, non-secret):
        ".claude/skills/isaac-draft/SKILL.md",
    ]
    return {k: {"mtime": 1.0, "ast_hash": "fake", "semantic_hash": ""} for k in keys}


def _synthetic_labels() -> dict:
    return {"7": "Alpha community", "9": "Beta community",
            "3": "Mod community", "5": "Other community"}


def _write_artifacts(repo_root: Path, *, graph=..., manifest=..., labels=...) -> Path:
    """Write a fake ``graphify-out/`` under ``repo_root``; return the artifacts dir.

    Pass a value of ``...`` (Ellipsis) to use the default synthetic content, ``None``
    to skip writing that file entirely, a ``dict`` to dump as JSON, or a ``str`` to
    write verbatim (for corrupt-JSON cases).
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


@pytest.fixture()
def reader(tmp_path):
    """Reader over a full synthetic artifacts set; ``src/fake_mod.py`` + the note
    exist on disk, ``src/other_mod.py`` does not (drives ``on_disk`` true/false)."""
    art = _write_artifacts(tmp_path)
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "fake_mod.py").write_text("# fake\n", encoding="utf-8")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "fake-note.md").write_text("# fake note\n", encoding="utf-8")
    return LocalGraphArtifactSource(art)


def _walk_keys(obj):
    """Yield every dict key appearing anywhere in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


# --- 1. happy path ------------------------------------------------------------


def test_overview_counts(reader):
    ov = reader.overview()
    assert ov["available"] is True
    assert ov["built_at_commit"] == "fakecommit0000"
    assert ov["node_count"] == 7
    assert ov["edge_count"] == 7
    assert ov["community_count"] == 4  # distinct communities {7,9,3,5}
    assert ov["concept_count"] == 2
    assert ov["served_file_count"] == 4  # 9 manifest keys minus 5 excluded
    assert ov["manifest_file_count"] == 9
    assert isinstance(ov["graph_mtime"], float)


def test_concepts_list(reader):
    concepts = reader.concepts()
    assert len(concepts) == 2
    alpha = next(c for c in concepts if c["id"] == "concept_alpha")
    assert alpha["label"] == "Alpha concept"
    assert alpha["community_id"] == "7"
    assert alpha["community_name"] == "Alpha community"
    assert alpha["source_file"] == "docs/fake-note.md"
    assert alpha["on_disk"] is True  # docs/fake-note.md exists under the fake root


def test_concept_detail_related_ordered_and_typed(reader):
    detail = reader.concept("concept_alpha")
    assert detail["id"] == "concept_alpha"
    assert detail["source_file"] == "docs/fake-note.md"
    assert detail["community_id"] == "7"
    files = detail["related"]["files"]
    # ordered by edge weight desc: src_fake_mod (5.0) then src_other_mod (2.0)
    assert [f["path"] for f in files] == ["src/fake_mod.py", "src/other_mod.py"]
    assert files[0] == {"path": "src/fake_mod.py", "relation": "references",
                        "file_type": "code"}
    concepts = detail["related"]["concepts"]
    assert concepts == [{"id": "concept_beta", "label": "Beta concept",
                        "relation": "relates_to"}]


def test_concept_unknown_is_none(reader):
    assert reader.concept("concept_does_not_exist") is None


def test_files_list(reader):
    files = reader.files()
    paths = {f["path"] for f in files}
    assert paths == {
        "docs/fake-note.md",
        "src/fake_mod.py",
        "src/other_mod.py",
        ".claude/skills/isaac-draft/SKILL.md",
    }
    mod = next(f for f in files if f["path"] == "src/fake_mod.py")
    assert mod["file_type"] == "code"
    assert mod["community_id"] == "3"
    assert mod["community_name"] == "Mod community"
    assert mod["node_count"] == 3
    assert mod["on_disk"] is True
    other = next(f for f in files if f["path"] == "src/other_mod.py")
    assert other["on_disk"] is False  # never created on disk


def test_file_detail_related_rationales_reference(reader):
    detail = reader.file("src/fake_mod.py")
    assert detail["file_type"] == "code"
    assert detail["community_id"] == "3"
    assert detail["node_count"] == 3
    assert detail["on_disk"] is True
    assert detail["local_reference"] == "src/fake_mod.py"
    assert detail["related"]["files"] == [
        {"path": "src/other_mod.py", "relation": "imports", "file_type": "code"}
    ]
    assert detail["related"]["concepts"] == [
        {"id": "concept_alpha", "label": "Alpha concept", "relation": "references"}
    ]
    assert detail["rationales"] == ["Fake rationale about the module."]


def test_file_kept_skill_path(reader):
    detail = reader.file(".claude/skills/isaac-draft/SKILL.md")
    assert detail is not None
    assert detail["path"] == ".claude/skills/isaac-draft/SKILL.md"


# --- 2. allowlist governance --------------------------------------------------


def test_files_exclude_governance_prefixes(reader):
    paths = {f["path"] for f in reader.files()}
    assert not any(p.startswith("examples/") for p in paths)
    assert not any(p.startswith(".superpowers/") for p in paths)
    assert not any(p.startswith("apps/web/.vercel/") for p in paths)
    assert ".claude/settings.local.json" not in paths
    assert not any(p.endswith(".png") for p in paths)


@pytest.mark.parametrize("excluded", [
    "examples/README.md",
    ".superpowers/sdd/x.md",
    "apps/web/.vercel/project.json",
    ".claude/settings.local.json",
    "ux-review/shot.png",
])
def test_file_detail_excluded_paths_not_indexed(reader, excluded):
    assert reader.file(excluded) is None
    assert reader.classify_path(excluded) == "not_indexed"


# --- 2a. P24.8 Item 1: secret / local-settings defense-in-depth exclusions ----
#
# These patterns close NO currently-indexed leak — the only sensitive key ever
# seen in a real manifest is ``.claude/settings.local.json`` (already covered
# above); this is pure defense-in-depth against a future secret-shaped path
# landing in the manifest. Checks must be precise ext/basename/suffix matches,
# never overbroad substrings: harmless lookalikes (``environment.py``,
# ``token_utils.py``, ``credentials_form.tsx``, dotted doc names, bare
# ``local.json``) must still be served.

_SECRET_MANIFEST_KEYS = [
    ".env",
    ".env.local",
    ".env.production",
    "secrets/app.key",
    "certs/server.pem",
    "keys/client.p12",
    "keys/client.pfx",
    "keys/apns.p8",
    "keystores/app.jks",
    ".netrc",
    ".pypirc",
    "config/id_rsa",
    "config/id_ed25519",
    "aws/credentials",
    "gcp/credentials.json",
    "config/settings.local.json",
]

_HARMLESS_LOOKALIKE_KEYS = [
    "src/environment.py",
    "src/token_utils.py",
    "apps/web/credentials_form.tsx",
    "docs/my.notes.md",
    "apps/web/vite.config.ts",
    "data/metadata.json",
    "docs/local.json",
]


@pytest.fixture()
def governed_reader(tmp_path):
    """Reader whose manifest carries P24.8 secret-pattern + harmless-lookalike
    probe keys alongside one normal approved-source key. Independent of the
    ``reader`` fixture's fixed synthetic set so the new probes don't disturb
    the existing happy-path assertions."""
    keys = ["src/isaac_records/official.py", *_SECRET_MANIFEST_KEYS,
            *_HARMLESS_LOOKALIKE_KEYS]
    manifest = {k: {"mtime": 1.0, "ast_hash": "fake", "semantic_hash": ""} for k in keys}
    art = _write_artifacts(tmp_path, manifest=manifest)
    return LocalGraphArtifactSource(art)


@pytest.mark.parametrize("secret_key", _SECRET_MANIFEST_KEYS)
def test_files_exclude_sensitive_patterns(governed_reader, secret_key):
    paths = {f["path"] for f in governed_reader.files()}
    assert secret_key not in paths
    assert governed_reader.file(secret_key) is None
    assert governed_reader.classify_path(secret_key) == "not_indexed"


@pytest.mark.parametrize("harmless_key", _HARMLESS_LOOKALIKE_KEYS)
def test_harmless_dotted_filenames_still_served(governed_reader, harmless_key):
    paths = {f["path"] for f in governed_reader.files()}
    assert harmless_key in paths
    assert governed_reader.file(harmless_key) is not None
    assert governed_reader.classify_path(harmless_key) == "served"


@pytest.mark.parametrize("bad", ["../etc/passwd", "foo/../../bar", "/abs/path", "~/x"])
def test_traversal_still_blocked(governed_reader, bad):
    assert governed_reader.classify_path(bad) == "unsafe"


def test_approved_source_still_served(governed_reader):
    paths = {f["path"] for f in governed_reader.files()}
    assert "src/isaac_records/official.py" in paths
    assert governed_reader.classify_path("src/isaac_records/official.py") == "served"


# --- 2b. P24.9: concept-anchor + related path filtering -----------------------
#
# A concept's ``source_file`` and a related file's ``source_file`` come from
# GRAPH NODES, not the manifest served allowlist, so an anchor can point at a
# governance-excluded / secret path (e.g. the live ``examples/README.md`` leak).
# Every path-bearing value a reader method emits must pass ``_is_served``: an
# excluded concept anchor is nulled (concept STILL listed), and an excluded
# related file is dropped. RED before the reader hardening in ``_derive`` /
# ``concept`` / ``_related``.


def _anchor_graph() -> dict:
    """Fake graph exercising path filtering: concepts anchored to excluded /
    secret / approved / benign-dotted paths, and a file whose related neighbors
    include one served and one governance-excluded path."""
    nodes = [
        {"id": "c_excluded", "label": "Excluded anchor concept", "file_type": "concept",
         "community": 1, "source_file": "examples/README.md"},
        {"id": "c_secret", "label": "Secret anchor concept", "file_type": "concept",
         "community": 1, "source_file": "secrets/app.key"},
        {"id": "c_approved", "label": "Approved anchor concept", "file_type": "concept",
         "community": 1, "source_file": "README.md"},
        {"id": "c_benign", "label": "Benign dotted anchor concept", "file_type": "concept",
         "community": 1, "source_file": "docs/my..note.md"},
        # Path-unsafe anchors (defense-in-depth for a future snapshot/db/hosted
        # provider whose node source_file is absolute / traversal):
        {"id": "c_absolute", "label": "Absolute anchor concept", "file_type": "concept",
         "community": 1, "source_file": "/etc/passwd"},
        {"id": "c_traversal", "label": "Traversal anchor concept", "file_type": "concept",
         "community": 1, "source_file": "../../secret"},
        {"id": "hub", "label": "hub.py", "file_type": "code", "community": 2,
         "source_file": "src/hub.py", "source_location": "L1"},
        {"id": "served_neighbor", "label": "served.py", "file_type": "code",
         "community": 2, "source_file": "src/served.py", "source_location": "L1"},
        {"id": "excluded_neighbor", "label": "README.md", "file_type": "document",
         "community": 2, "source_file": "examples/README.md", "source_location": "L1"},
        {"id": "abs_neighbor", "label": "passwd", "file_type": "document",
         "community": 2, "source_file": "/etc/passwd", "source_location": "L1"},
        {"id": "traversal_neighbor", "label": "secret", "file_type": "document",
         "community": 2, "source_file": "../../secret", "source_location": "L1"},
    ]
    links = [
        {"source": "hub", "target": "served_neighbor", "relation": "imports",
         "weight": 5.0, "source_file": "src/hub.py"},
        # Higher weight than the served neighbor, so if it were NOT dropped it
        # would sort first — proving the drop happens before the cap/sort.
        {"source": "hub", "target": "excluded_neighbor", "relation": "references",
         "weight": 9.0, "source_file": "src/hub.py"},
        {"source": "hub", "target": "abs_neighbor", "relation": "references",
         "weight": 8.0, "source_file": "src/hub.py"},
        {"source": "hub", "target": "traversal_neighbor", "relation": "references",
         "weight": 7.0, "source_file": "src/hub.py"},
    ]
    return {"nodes": nodes, "links": links, "built_at_commit": "fakecommit0000"}


@pytest.fixture()
def anchor_reader(tmp_path):
    """Reader over ``_anchor_graph``. ``README.md`` exists on disk (drives the
    real ``on_disk`` check for a kept anchor); ``src/hub.py`` is served so its
    detail (and thus ``_related``) is reachable."""
    manifest = {k: {"mtime": 1.0, "ast_hash": "x", "semantic_hash": ""}
                for k in ("src/hub.py", "src/served.py", "README.md", "docs/my..note.md")}
    art = _write_artifacts(tmp_path, graph=_anchor_graph(), manifest=manifest, labels={})
    (tmp_path / "README.md").write_text("# fake readme\n", encoding="utf-8")
    return LocalGraphArtifactSource(art)


def test_concept_excluded_anchor_is_nulled_but_still_listed(anchor_reader):
    summaries = {c["id"]: c for c in anchor_reader.concepts()}
    assert "c_excluded" in summaries  # concept STILL surfaced
    assert summaries["c_excluded"]["source_file"] is None
    assert summaries["c_excluded"]["on_disk"] is False
    detail = anchor_reader.concept("c_excluded")
    assert detail is not None
    assert detail["source_file"] is None
    assert detail["on_disk"] is False


def test_concept_secret_anchor_is_nulled(anchor_reader):
    summary = next(c for c in anchor_reader.concepts() if c["id"] == "c_secret")
    assert summary["source_file"] is None
    assert summary["on_disk"] is False
    detail = anchor_reader.concept("c_secret")
    assert detail["source_file"] is None
    assert detail["on_disk"] is False


def test_concept_approved_anchor_kept_with_real_on_disk(anchor_reader):
    summary = next(c for c in anchor_reader.concepts() if c["id"] == "c_approved")
    assert summary["source_file"] == "README.md"
    assert summary["on_disk"] is True  # created on disk -> real existence check
    detail = anchor_reader.concept("c_approved")
    assert detail["source_file"] == "README.md"
    assert detail["on_disk"] is True


def test_concept_benign_dotted_anchor_kept(anchor_reader):
    # Dots, not traversal — served, so the anchor is retained (NOT nulled).
    summary = next(c for c in anchor_reader.concepts() if c["id"] == "c_benign")
    assert summary["source_file"] == "docs/my..note.md"
    detail = anchor_reader.concept("c_benign")
    assert detail["source_file"] == "docs/my..note.md"


@pytest.mark.parametrize("cid,src", [
    ("c_absolute", "/etc/passwd"),
    ("c_traversal", "../../secret"),
])
def test_concept_path_unsafe_anchor_is_nulled(anchor_reader, cid, src):
    # Defense-in-depth: an absolute/traversal anchor is path-unsafe, so it is
    # withheld even though _is_served alone would not have rejected it.
    summary = next(c for c in anchor_reader.concepts() if c["id"] == cid)
    assert summary["source_file"] is None
    assert summary["on_disk"] is False
    detail = anchor_reader.concept(cid)
    assert detail["source_file"] is None
    assert detail["on_disk"] is False


def test_related_files_drops_excluded_and_unsafe_keeps_served(anchor_reader):
    detail = anchor_reader.file("src/hub.py")
    related_paths = [f["path"] for f in detail["related"]["files"]]
    assert "src/served.py" in related_paths  # served neighbor retained
    assert "examples/README.md" not in related_paths  # governance-excluded dropped
    assert "/etc/passwd" not in related_paths  # absolute dropped
    assert "../../secret" not in related_paths  # traversal dropped
    # Every retained related path is BOTH served AND path-safe.
    assert all(_is_served_probe(p) and not _is_unsafe_probe(p) for p in related_paths)


def _is_served_probe(path: str) -> bool:
    """Mirror the reader's served predicate for the related-drop assertion."""
    from isaac_api.memory import _is_served

    return _is_served(path)


def _is_unsafe_probe(path: str) -> bool:
    """Mirror the reader's path-safety predicate for the related-drop assertion."""
    return LocalGraphArtifactSource._is_unsafe(path)


def test_anchor_reader_traversal_still_blocked(anchor_reader):
    assert anchor_reader.classify_path("../etc/passwd") == "unsafe"


def test_anchor_graph_malformed_degrades_not_raises(tmp_path):
    art = _write_artifacts(tmp_path, graph="{not valid json")
    reader = LocalGraphArtifactSource(art)
    ov = reader.overview()
    assert ov["available"] is False
    assert ov["reason"] == "graph_unreadable"
    assert reader.concepts() == []  # nothing raises


# --- 3. path guard ------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    "../schema/isaac_record_v1.json",
    "/etc/passwd",
    "a\\b.md",
    "~/x",
    "",
])
def test_classify_path_unsafe(reader, bad):
    assert reader.classify_path(bad) == "unsafe"


def test_classify_path_clean_unknown_is_not_indexed(reader):
    assert reader.classify_path("docs/nope.md") == "not_indexed"


def test_classify_path_served(reader):
    assert reader.classify_path("src/fake_mod.py") == "served"


# --- 3a. P24.6 Item 1: segment-based `..` guard (no substring over-match) ------
#
# A benign filename that merely CONTAINS two consecutive dots (e.g.
# ``docs/my..note.md``) is a safe relative path, not traversal — it must
# classify ``not_indexed`` (404), not ``unsafe`` (400). Real traversal (``..``
# as its own ``/``-delimited segment, leading/trailing/interior) must still be
# ``unsafe``. RED before the segment-based fix in ``_is_unsafe``.


@pytest.mark.parametrize("benign", [
    "docs/my..note.md",
    "data/v1..2/table.csv",
    "reports/2024..2025-summary.md",
])
def test_classify_path_benign_double_dot_is_not_indexed(reader, benign):
    # Pre-fix, the substring test ``".." in path`` wrongly flags these unsafe.
    assert reader.classify_path(benign) == "not_indexed"


@pytest.mark.parametrize("bad", [
    "../etc/passwd",
    "a/../b",
    "..",
    "docs/../secret",
    "x/..",
])
def test_classify_path_traversal_segment_is_unsafe(reader, bad):
    assert reader.classify_path(bad) == "unsafe"


# --- 3b. P24.6 Item 1: endpoint tier — benign `..` is 404, traversal is 400 ----
#
# Confirms the reader classification propagates to the HTTP tier: a benign
# ``..``-containing name returns 404 ``source_not_indexed`` (a safe relative path
# not in the served allowlist), while real traversal returns 400
# ``unsafe_source_path``. The graph is available here so the not_indexed branch
# (404) is reached rather than the graph-absent degraded (200) branch.


def _api_client(tmp_path, monkeypatch, memory_dir) -> TestClient:
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(memory_dir))
    from isaac_api.app import create_app

    return TestClient(create_app())


@pytest.mark.parametrize("benign", ["docs/my..note.md", "data/v1..2/table.csv"])
def test_memory_file_benign_double_dot_is_404_not_400(tmp_path, monkeypatch, benign):
    art = _write_artifacts(tmp_path)
    client = _api_client(tmp_path, monkeypatch, art)
    resp = client.get("/api/memory/file", params={"path": benign})
    assert resp.status_code == 404  # RED pre-fix: substring guard returned 400
    body = resp.json()
    assert body["error"] == "source_not_indexed"
    assert body["path"] == benign


@pytest.mark.parametrize("bad", ["../etc/passwd", "docs/../secret", "a/../b", "x/.."])
def test_memory_file_traversal_is_400(tmp_path, monkeypatch, bad):
    art = _write_artifacts(tmp_path)
    client = _api_client(tmp_path, monkeypatch, art)
    resp = client.get("/api/memory/file", params={"path": bad})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "unsafe_source_path"
    assert body["path"] == bad


# --- 4. absent artifacts ------------------------------------------------------


def test_absent_dir_degrades(tmp_path):
    reader = LocalGraphArtifactSource(tmp_path / "graphify-out")  # never created
    ov = reader.overview()
    assert ov["available"] is False
    assert ov["reason"] == "graph_absent"
    # list/detail degrade to empty/None; nothing raises.
    assert reader.concepts() == []
    assert reader.files() == []
    assert reader.concept("concept_alpha") is None
    assert reader.file("src/fake_mod.py") is None


def test_missing_graph_only_is_absent(tmp_path):
    art = _write_artifacts(tmp_path, graph=None)  # manifest + labels but no graph
    reader = LocalGraphArtifactSource(art)
    assert reader.overview()["reason"] == "graph_absent"


# --- 5. corrupt artifacts -----------------------------------------------------


def test_invalid_json_graph_is_unreadable(tmp_path):
    art = _write_artifacts(tmp_path, graph="{not valid json")
    reader = LocalGraphArtifactSource(art)
    ov = reader.overview()
    assert ov["available"] is False
    assert ov["reason"] == "graph_unreadable"
    assert reader.concepts() == []
    assert reader.files() == []


def test_wrong_shape_graph_is_unreadable(tmp_path):
    art = _write_artifacts(tmp_path, graph=[1, 2, 3])  # valid JSON, wrong shape
    reader = LocalGraphArtifactSource(art)
    assert reader.overview()["reason"] == "graph_unreadable"


def test_missing_nodes_key_is_unreadable(tmp_path):
    art = _write_artifacts(tmp_path, graph={"links": [], "built_at_commit": "x"})
    reader = LocalGraphArtifactSource(art)
    assert reader.overview()["reason"] == "graph_unreadable"


def test_type_corrupt_graph_is_unreadable(tmp_path):
    """JSON-valid graph whose VALUES have wrong types (string ``community``)
    degrades to graph_unreadable — never raises (a future db/hosted provider may
    carry different type conventions)."""
    graph = _synthetic_graph()
    for node in graph["nodes"]:
        node["community"] = str(node["community"])  # int expected -> str corrupt
    art = _write_artifacts(tmp_path, graph=graph)
    reader = LocalGraphArtifactSource(art)
    ov = reader.overview()
    assert ov["available"] is False
    assert ov["reason"] == "graph_unreadable"
    # list/detail calls degrade too; nothing raises.
    assert reader.concepts() == []
    assert reader.files() == []
    assert reader.concept("concept_alpha") is None
    assert reader.file("src/fake_mod.py") is None
    assert reader.classify_path("src/fake_mod.py") == "not_indexed"


def test_string_link_weight_normalizes_and_never_raises(tmp_path):
    """A JSON-valid graph with a non-numeric link weight (e.g. ``"weight": "9"``)
    stays available AND request-time reads return normally: the weight is
    normalized to 0.0 at build, so the corrupt edge sorts last among differing
    weights instead of raising in related-ordering arithmetic."""
    graph = _synthetic_graph()
    mentions = next(l for l in graph["links"] if l["relation"] == "mentions")
    mentions["weight"] = "9"  # truthy string: kept verbatim it would sort first
    art = _write_artifacts(tmp_path, graph=graph)
    reader = LocalGraphArtifactSource(art)

    assert reader.overview()["available"] is True
    detail = reader.concept("concept_alpha")  # must not raise
    files = detail["related"]["files"]
    # src_fake_mod keeps its real 5.0; the corrupt "9" degrades to 0.0 -> last.
    assert [f["path"] for f in files] == ["src/fake_mod.py", "src/other_mod.py"]
    assert reader.file("src/fake_mod.py") is not None  # must not raise either


@pytest.mark.parametrize("manifest", ["{broken manifest", None],
                         ids=["corrupt", "missing"])
def test_bad_manifest_alone_stays_available(tmp_path, manifest):
    """Corrupt/missing manifest with a healthy graph: the plane stays available
    (graph.json is the sole availability signal); the served allowlist degrades
    to empty, so files()/file() surface nothing."""
    art = _write_artifacts(tmp_path, manifest=manifest)
    reader = LocalGraphArtifactSource(art)
    ov = reader.overview()
    assert ov["available"] is True
    assert ov["served_file_count"] == 0
    assert ov["manifest_file_count"] == 0
    assert reader.files() == []
    assert reader.file("src/fake_mod.py") is None
    assert reader.classify_path("src/fake_mod.py") == "not_indexed"
    # concepts come from the graph, not the manifest — unaffected.
    assert {c["id"] for c in reader.concepts()} == {"concept_alpha", "concept_beta"}


def test_corrupt_labels_alone_stays_available(tmp_path):
    art = _write_artifacts(tmp_path, labels="{broken labels")
    reader = LocalGraphArtifactSource(art)
    ov = reader.overview()
    assert ov["available"] is True  # graph is fine
    alpha = next(c for c in reader.concepts() if c["id"] == "concept_alpha")
    assert alpha["community_id"] == "7"
    assert alpha["community_name"] is None  # labels unreadable -> honest null


def test_missing_labels_alone_stays_available(tmp_path):
    art = _write_artifacts(tmp_path, labels=None)
    reader = LocalGraphArtifactSource(art)
    assert reader.overview()["available"] is True
    alpha = next(c for c in reader.concepts() if c["id"] == "concept_alpha")
    assert alpha["community_name"] is None


# --- 6. cache behavior --------------------------------------------------------


def test_parse_is_cached_and_reparses_on_mtime_change(tmp_path):
    art = _write_artifacts(tmp_path)
    reader = LocalGraphArtifactSource(art)
    reader.overview()
    reader.concepts()
    reader.files()
    reader.file("src/fake_mod.py")
    assert reader.reload_count == 1  # parsed once despite many calls

    graph_path = art / "graph.json"
    bumped = graph_path.stat().st_mtime + 10
    os.utime(graph_path, (bumped, bumped))
    reader.overview()
    assert reader.reload_count == 2  # re-parsed after mtime change


# --- 7. no-content invariant --------------------------------------------------


def test_no_content_or_lines_keys_anywhere(reader):
    payloads = [
        reader.overview(),
        reader.concepts(),
        reader.concept("concept_alpha"),
        reader.files(),
        reader.file("src/fake_mod.py"),
    ]
    for payload in payloads:
        keys = set(_walk_keys(payload))
        assert "content" not in keys
        assert "lines" not in keys
        # memory never emits validation-verdict vocabulary either
        assert keys.isdisjoint(FORBIDDEN_VERDICT_KEYS)


def test_related_lists_capped_at_25(tmp_path):
    """A file linked to 30 others surfaces only the 25 highest-weight related files."""
    nodes = [{"id": "hub", "label": "hub.py", "file_type": "code", "community": 1,
              "source_file": "src/hub.py", "source_location": "L1"}]
    links = []
    for i in range(30):
        nodes.append({"id": f"n{i}", "label": f"m{i}.py", "file_type": "code",
                      "community": 2, "source_file": f"src/m{i}.py",
                      "source_location": "L1"})
        links.append({"source": "hub", "target": f"n{i}", "relation": "imports",
                      "weight": float(i), "source_file": "src/hub.py"})
    graph = {"nodes": nodes, "links": links, "built_at_commit": "fakecommit0000"}
    manifest = {"src/hub.py": {"mtime": 1.0, "ast_hash": "x", "semantic_hash": ""}}
    art = _write_artifacts(tmp_path, graph=graph, manifest=manifest, labels={})
    reader = LocalGraphArtifactSource(art)
    files = reader.file("src/hub.py")["related"]["files"]
    assert len(files) == 25
    weights_kept = [int(f["path"].removeprefix("src/m").removesuffix(".py"))
                    for f in files]
    assert weights_kept == list(range(29, 4, -1))  # top-25 weights, desc


# --- 8. default reader / env seam ---------------------------------------------


def test_default_reader_env_override(tmp_path, monkeypatch):
    art = _write_artifacts(tmp_path)
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(art))
    reader = memory.get_default_reader()
    ov = reader.overview()
    assert ov["available"] is True
    assert ov["built_at_commit"] == "fakecommit0000"


# --- 9. stdlib-only / isolation invariant -------------------------------------


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    return here.parents[3]


_STDLIB_ROOTS = {
    "json", "os", "sys", "time", "pathlib", "dataclasses", "typing",
    "functools", "collections", "__future__",
}


def test_memory_module_imports_only_stdlib():
    source = Path(memory.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import within isaac_api -> forbidden here
                roots.add(f".{node.module or ''}")
            elif node.module:
                roots.add(node.module.split(".")[0])
    assert roots <= _STDLIB_ROOTS, f"non-stdlib imports: {roots - _STDLIB_ROOTS}"
    # The forbidden modules must not appear among *actual* imports (docstring
    # mentions of them describing the isolation contract are fine).
    assert roots.isdisjoint({"isaac_records", "graphify", "fastapi", "isaac_api"})


# --- 10. real-graph smoke (conditional) ---------------------------------------


_REAL_GRAPH = _repo_root() / "graphify-out" / "graph.json"


@pytest.mark.skipif(not _REAL_GRAPH.exists(),
                    reason="no local graphify-out/graph.json (e.g. CI)")
def test_real_graph_smoke():
    reader = LocalGraphArtifactSource(_REAL_GRAPH.parent)
    ov = reader.overview()
    assert ov["available"] is True
    assert ov["concept_count"] == 19
    paths = {f["path"] for f in reader.files()}
    assert not any(p.startswith("examples/") for p in paths)
    assert not any(p.startswith(".superpowers/") for p in paths)
    assert not any(p.endswith(".png") for p in paths)

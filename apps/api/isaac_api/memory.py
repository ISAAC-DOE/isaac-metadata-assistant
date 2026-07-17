"""Read-only Project Memory reader over the Graphify artifacts (memory plane).

This module is the memory-plane analogue of ``sources.py``: a deterministic,
stdlib-only, read-only reader that surfaces *provenance* — never file content,
never a validation verdict — derived from the graph Graphify writes under the
gitignored ``graphify-out/`` tree. It answers status / concept / file-provenance
lookups for the ``/api/memory/*`` routes wired in a later slice (P24.2+).

Design contract (see docs/superpowers/specs/2026-07-16-phase-24-project-memory-design.md):

* **Truth isolation.** Imports only the standard library. It never imports
  ``isaac_records`` or ``graphify``, is never imported by the truth core, computes
  no verdict, and emits no key in ``{ok, valid, passed, verdict, schema, errors}``.
* **Metadata-only.** It serves provenance metadata plus a read-only repo-relative
  path *reference*. It never reads, opens, or serves file *content*: no ``content``
  / ``lines`` / bytes anywhere. The only filesystem access outside the artifacts
  directory is an existence-only ``on_disk`` check (``Path.exists``).
* **Served allowlist** (spec §4). The set of surfaced files is computed once per
  graph load from ``manifest.json`` keys, minus governance-sensitive prefixes
  (``examples/``, ``.superpowers/``, ``apps/web/.vercel/``), the exact file
  ``.claude/settings.local.json``, and binary extensions (``BINARY_EXTS``, incl.
  ``.png``). ``.claude/skills/**`` is kept. Traversal safety is closed-set
  membership in this allowlist; the path guard is defense-in-depth only.
* **Honest degradation.** No exception ever escapes for an artifact problem.
  Absent artifacts dir / missing ``graph.json`` -> ``available: False,
  reason: "graph_absent"``. Invalid JSON, a structurally-wrong graph, or a
  JSON-valid graph with type-corrupt values (any error during derivation) ->
  ``available: False, reason: "graph_unreadable"``. A missing/corrupt labels file
  alone never makes the plane unavailable — it only nulls ``community_name``.
  A missing/corrupt manifest alone never makes the plane unavailable either
  (``graph.json`` is the sole availability signal) — the served allowlist
  degrades to empty, so ``files()``/``file()`` surface nothing.

Provider seam
-------------
``LocalGraphArtifactSource`` is one concrete reader over a local artifacts
directory. Consumers should depend on its method surface (see the ``MemoryReader``
Protocol), not on how it loads data, so a future database source, mounted
graph-snapshot volume, hosted memory service, or login-gated institutional backend
can replace/supplement it without rewriting callers. ``get_default_reader()``
resolves the artifacts directory from the optional ``ISAAC_MEMORY_DIR`` environment
override (the future mounted-volume seam) and otherwise falls back to the repo's
``graphify-out/`` directory.

Rationale join
--------------
A file's ``rationales`` are the labels of graph nodes with ``file_type ==
"rationale"`` whose ``source_file`` equals that path (the same set the
``rationale_for`` edges point back into). Joining on ``source_file`` is robust to
collapsed/dangling edges and needs no edge traversal.

Cache
-----
The (~1.8 MB local) graph is parsed lazily on first use and cached in-process,
keyed by the mtimes of ``graph.json`` / ``manifest.json`` / ``.graphify_labels.json``.
It is re-parsed only when a key changes. Rebuild is GIL-safe: a fresh immutable
state object is built and then atomically swapped into a single attribute; no lock
is needed.
"""

from __future__ import annotations

import collections
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

# --- constants ----------------------------------------------------------------

GRAPH_FILE = "graph.json"
MANIFEST_FILE = "manifest.json"
LABELS_FILE = ".graphify_labels.json"

ENV_MEMORY_DIR = "ISAAC_MEMORY_DIR"

#: Governance-sensitive prefixes filtered out of the served allowlist (spec §4).
EXCLUDED_PREFIXES = ("examples/", ".superpowers/", "apps/web/.vercel/")
#: Exact repo-relative paths filtered out of the served allowlist.
EXCLUDED_EXACT = frozenset({".claude/settings.local.json"})
#: Binary extensions filtered out (no textual provenance value); ``.png`` required.
BINARY_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf"})

MAX_RELATED = 25
MAX_RATIONALES = 10

CONCEPT = "concept"
RATIONALE = "rationale"


# --- provider seam ------------------------------------------------------------


class MemoryReader(Protocol):
    """Stable read surface future memory sources (db / volume / hosted) mirror."""

    def overview(self) -> dict: ...
    def concepts(self) -> list: ...
    def concept(self, concept_id: str) -> Optional[dict]: ...
    def files(self) -> list: ...
    def file(self, path: str) -> Optional[dict]: ...
    def classify_path(self, path: str) -> str: ...


# --- parsed state -------------------------------------------------------------


@dataclass(frozen=True)
class _GraphState:
    """Immutable derived view of one graph load; swapped atomically into the cache."""

    key: tuple
    available: bool
    reason: Optional[str] = None
    built_at_commit: Optional[str] = None
    graph_mtime: float = 0.0
    node_count: int = 0
    edge_count: int = 0
    community_count: int = 0
    concept_count: int = 0
    served_file_count: int = 0
    manifest_file_count: int = 0
    labels: dict = field(default_factory=dict)  # community-id-string -> curated name
    concept_summaries: list = field(default_factory=list)
    concept_by_id: dict = field(default_factory=dict)
    file_summaries: dict = field(default_factory=dict)  # path -> summary dict
    served: frozenset = frozenset()
    nodes_by_id: dict = field(default_factory=dict)
    nodes_by_file: dict = field(default_factory=dict)  # path -> list[node]
    adjacency: dict = field(default_factory=dict)  # node_id -> list[(other,rel,weight)]
    rationales_by_file: dict = field(default_factory=dict)  # path -> list[str]


# --- helpers ------------------------------------------------------------------


def _find_repo_root() -> Path:
    """Walk up until the vendored official schema is found (mirrors workspace.py)."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "schema" / "isaac_record_v1.json").exists():
            return candidate
    return here.parents[3]


def _load_json(path: Path):
    """Return parsed JSON, or raise ``ValueError``/``OSError``. No content is kept."""
    return json.loads(path.read_text(encoding="utf-8"))


def _is_served(path: str) -> bool:
    if path.startswith(EXCLUDED_PREFIXES):
        return False
    if path in EXCLUDED_EXACT:
        return False
    if os.path.splitext(path)[1].lower() in BINARY_EXTS:
        return False
    return True


def _community_id(value) -> Optional[str]:
    return None if value is None else str(value)


def _file_type_for(nodes: list) -> Optional[str]:
    """The file's own kind: most-common ``file_type`` excluding attached
    rationale/concept nodes; falls back to any available kind."""
    own = [n.get("file_type") for n in nodes
           if n.get("file_type") not in (RATIONALE, CONCEPT) and n.get("file_type")]
    if own:
        return collections.Counter(own).most_common(1)[0][0]
    any_kind = [n.get("file_type") for n in nodes if n.get("file_type")]
    return any_kind[0] if any_kind else None


def _community_for(nodes: list):
    """Most-common community among a file's nodes; ties break to the smallest id."""
    comms = [n.get("community") for n in nodes if n.get("community") is not None]
    if not comms:
        return None
    counts = collections.Counter(comms)
    return max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]


# --- reader -------------------------------------------------------------------


class LocalGraphArtifactSource:
    """Concrete :class:`MemoryReader` over a local Graphify artifacts directory.

    ``artifacts_dir`` is where ``graph.json`` / ``manifest.json`` /
    ``.graphify_labels.json`` live (normally ``<repo>/graphify-out``). ``repo_root``
    anchors the existence-only ``on_disk`` checks and defaults to the artifacts
    directory's parent.
    """

    def __init__(self, artifacts_dir, repo_root=None):
        self.artifacts_dir = Path(artifacts_dir)
        self.repo_root = Path(repo_root) if repo_root is not None else self.artifacts_dir.parent
        self.graph_path = self.artifacts_dir / GRAPH_FILE
        self.manifest_path = self.artifacts_dir / MANIFEST_FILE
        self.labels_path = self.artifacts_dir / LABELS_FILE
        self.reload_count = 0
        self._state: Optional[_GraphState] = None

    # -- cache --

    def _mtime(self, path: Path) -> Optional[float]:
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def _current_key(self) -> tuple:
        return (
            self._mtime(self.graph_path),
            self._mtime(self.manifest_path),
            self._mtime(self.labels_path),
        )

    def _state_now(self) -> _GraphState:
        key = self._current_key()
        state = self._state
        if state is not None and state.key == key:
            return state
        new_state = self._build(key)
        self._state = new_state  # atomic swap; readers see one consistent object
        return new_state

    # -- build --

    def _build(self, key: tuple) -> _GraphState:
        self.reload_count += 1

        if not self.graph_path.is_file():
            return _GraphState(key=key, available=False, reason="graph_absent")
        try:
            graph = _load_json(self.graph_path)
        except (ValueError, OSError):
            return _GraphState(key=key, available=False, reason="graph_unreadable")
        if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
            return _GraphState(key=key, available=False, reason="graph_unreadable")

        # Never-raise guard over the whole derivation: a JSON-valid graph whose
        # VALUES have unexpected types (e.g. string ``community``, non-string
        # ``source_file``) must degrade to graph_unreadable, never propagate —
        # a future db/hosted provider may carry different type conventions. A
        # blanket wrapper is the deliberate choice here; no per-field coercion.
        try:
            return self._derive(key, graph)
        except Exception:
            return _GraphState(key=key, available=False, reason="graph_unreadable")

    def _derive(self, key: tuple, graph: dict) -> _GraphState:
        """Build the derived state from a shape-checked graph dict. May raise on
        type-corrupt values; ``_build`` catches everything and degrades."""
        nodes = [n for n in graph["nodes"] if isinstance(n, dict)]
        links = graph.get("links")
        if not isinstance(links, list):
            links = graph.get("edges")
        if not isinstance(links, list):
            links = []

        labels = self._load_labels()
        manifest_keys = self._load_manifest_keys()
        served = frozenset(p for p in manifest_keys if _is_served(p))

        nodes_by_id: dict = {}
        nodes_by_file: dict = collections.defaultdict(list)
        for node in nodes:
            nid = node.get("id")
            if nid is not None:
                nodes_by_id[nid] = node
            sf = node.get("source_file")
            if sf:
                nodes_by_file[sf].append(node)

        adjacency: dict = collections.defaultdict(list)
        for link in links:
            if not isinstance(link, dict):
                continue
            src, tgt = link.get("source"), link.get("target")
            if src is None or tgt is None:
                continue
            relation = link.get("relation")
            weight = link.get("weight") or 0.0
            adjacency[src].append((tgt, relation, weight))
            adjacency[tgt].append((src, relation, weight))

        rationales_by_file: dict = collections.defaultdict(list)
        for node in nodes:
            if node.get("file_type") == RATIONALE:
                sf = node.get("source_file")
                if sf and node.get("label"):
                    rationales_by_file[sf].append(node["label"])

        concept_summaries = []
        concept_by_id = {}
        for node in nodes:
            if node.get("file_type") != CONCEPT:
                continue
            summary = {
                "id": node.get("id"),
                "label": node.get("label"),
                "community_id": _community_id(node.get("community")),
                "community_name": self._community_name(node.get("community"), labels),
                "source_file": node.get("source_file"),
                "on_disk": self._on_disk(node.get("source_file")),
            }
            concept_summaries.append(summary)
            concept_by_id[node.get("id")] = node
        concept_summaries.sort(key=lambda c: (c["label"] or "", c["id"] or ""))

        file_summaries = {}
        for path in served:
            file_nodes = nodes_by_file.get(path, [])
            community = _community_for(file_nodes)
            file_summaries[path] = {
                "path": path,
                "file_type": _file_type_for(file_nodes),
                "community_id": _community_id(community),
                "community_name": self._community_name(community, labels),
                "node_count": len(file_nodes),
                "on_disk": self._on_disk(path),
            }

        communities = {n.get("community") for n in nodes if n.get("community") is not None}

        return _GraphState(
            key=key,
            available=True,
            built_at_commit=graph.get("built_at_commit"),
            graph_mtime=self._mtime(self.graph_path) or 0.0,
            node_count=len(nodes),
            edge_count=len(links),
            community_count=len(communities),
            concept_count=len(concept_summaries),
            served_file_count=len(served),
            manifest_file_count=len(manifest_keys),
            labels=labels,
            concept_summaries=concept_summaries,
            concept_by_id=concept_by_id,
            file_summaries=file_summaries,
            served=served,
            nodes_by_id=nodes_by_id,
            nodes_by_file=dict(nodes_by_file),
            adjacency=dict(adjacency),
            rationales_by_file=dict(rationales_by_file),
        )

    def _load_labels(self) -> dict:
        """Curated community names; corrupt/missing degrades to ``{}`` (null names)."""
        try:
            if self.labels_path.is_file():
                raw = _load_json(self.labels_path)
                if isinstance(raw, dict):
                    return {str(k): v for k, v in raw.items()}
        except (ValueError, OSError):
            pass
        return {}

    def _load_manifest_keys(self) -> list:
        """Indexed repo-relative paths; corrupt/missing degrades to ``[]``."""
        try:
            if self.manifest_path.is_file():
                raw = _load_json(self.manifest_path)
                if isinstance(raw, dict):
                    return list(raw.keys())
        except (ValueError, OSError):
            pass
        return []

    @staticmethod
    def _community_name(community, labels: dict) -> Optional[str]:
        if community is None:
            return None
        return labels.get(str(community))

    def _on_disk(self, rel_path) -> bool:
        """Existence-only check of ``rel_path`` resolved strictly under the repo root.

        Never opens or reads the file. Returns ``False`` for anything that would
        resolve outside the repo root (defense-in-depth; served paths are already a
        closed allowlist)."""
        if not rel_path:
            return False
        try:
            root = self.repo_root.resolve()
            target = (root / rel_path).resolve()
            target.relative_to(root)
        except (ValueError, OSError):
            return False
        return target.exists()

    # -- related --

    def _related(self, state: _GraphState, node_ids: set, self_path) -> dict:
        """Aggregate related files + concepts from edges touching ``node_ids``.

        Each related file/concept is kept at its highest edge weight, ordered by
        weight desc (ties by path/id), and capped at :data:`MAX_RELATED`. Edges to
        nodes in the same file (``self_path``) are skipped."""
        files_acc: dict = {}
        concepts_acc: dict = {}
        for nid in node_ids:
            for other_id, relation, weight in state.adjacency.get(nid, []):
                other = state.nodes_by_id.get(other_id)
                if other is None:
                    continue
                if other.get("file_type") == CONCEPT:
                    if other_id in node_ids:
                        continue
                    prev = concepts_acc.get(other_id)
                    if prev is None or weight > prev[0]:
                        concepts_acc[other_id] = (weight, relation, other.get("label"))
                else:
                    opath = other.get("source_file")
                    if not opath or opath == self_path:
                        continue
                    prev = files_acc.get(opath)
                    if prev is None or weight > prev[0]:
                        files_acc[opath] = (weight, relation, other.get("file_type"))
        files = sorted(files_acc.items(), key=lambda kv: (-kv[1][0], kv[0]))[:MAX_RELATED]
        concepts = sorted(
            concepts_acc.items(), key=lambda kv: (-kv[1][0], kv[0])
        )[:MAX_RELATED]
        return {
            "files": [
                {"path": p, "relation": rel, "file_type": ft}
                for p, (w, rel, ft) in files
            ],
            "concepts": [
                {"id": cid, "label": lb, "relation": rel}
                for cid, (w, rel, lb) in concepts
            ],
        }

    # -- public read surface --

    def overview(self) -> dict:
        state = self._state_now()
        if not state.available:
            return {"available": False, "reason": state.reason}
        return {
            "available": True,
            "built_at_commit": state.built_at_commit,
            "graph_mtime": state.graph_mtime,
            "node_count": state.node_count,
            "edge_count": state.edge_count,
            "community_count": state.community_count,
            "concept_count": state.concept_count,
            "served_file_count": state.served_file_count,
            "manifest_file_count": state.manifest_file_count,
        }

    def concepts(self) -> list:
        state = self._state_now()
        if not state.available:
            return []
        return [dict(c) for c in state.concept_summaries]

    def concept(self, concept_id: str) -> Optional[dict]:
        state = self._state_now()
        if not state.available:
            return None
        node = state.concept_by_id.get(concept_id)
        if node is None:
            return None
        detail = {
            "id": node.get("id"),
            "label": node.get("label"),
            "community_id": _community_id(node.get("community")),
            "community_name": self._community_name(node.get("community"), state.labels),
            "source_file": node.get("source_file"),
            "on_disk": self._on_disk(node.get("source_file")),
        }
        detail["related"] = self._related(state, {concept_id}, self_path=None)
        return detail

    def files(self) -> list:
        state = self._state_now()
        if not state.available:
            return []
        return [dict(state.file_summaries[p]) for p in sorted(state.file_summaries)]

    def file(self, path: str) -> Optional[dict]:
        state = self._state_now()
        if not state.available:
            return None
        summary = state.file_summaries.get(path)
        if summary is None:
            return None
        detail = dict(summary)
        detail["local_reference"] = path
        node_ids = {n.get("id") for n in state.nodes_by_file.get(path, [])
                    if n.get("id") is not None}
        detail["related"] = self._related(state, node_ids, self_path=path)
        detail["rationales"] = list(state.rationales_by_file.get(path, []))[:MAX_RATIONALES]
        return detail

    def classify_path(self, path: str) -> str:
        """``"unsafe"`` (400-worthy) / ``"served"`` / ``"not_indexed"`` (404-worthy).

        Unsafe = empty, absolute, backslash, ``..``, or ``~`` (defense-in-depth).
        Otherwise served iff it is an exact key in the closed served allowlist."""
        if self._is_unsafe(path):
            return "unsafe"
        state = self._state_now()
        if state.available and path in state.served:
            return "served"
        return "not_indexed"

    @staticmethod
    def _is_unsafe(path: str) -> bool:
        if not path:
            return True
        if path.startswith("/") or path.startswith("~"):
            return True
        if "\\" in path or ".." in path:
            return True
        return False


# --- module-level default accessor -------------------------------------------

_REPO_ROOT = _find_repo_root()
_default_reader: Optional[LocalGraphArtifactSource] = None
_default_dir: Optional[Path] = None


def _resolve_artifacts_dir() -> Path:
    override = os.environ.get(ENV_MEMORY_DIR, "").strip()
    if override:
        return Path(override)
    return _REPO_ROOT / "graphify-out"


def get_default_reader() -> LocalGraphArtifactSource:
    """The process-wide default reader.

    Resolves the artifacts directory from ``ISAAC_MEMORY_DIR`` (the mounted-volume
    seam) or the repo's ``graphify-out/``. The reader instance is reused so its
    mtime cache persists; it is rebuilt only if the resolved directory changes."""
    global _default_reader, _default_dir
    resolved = _resolve_artifacts_dir()
    if _default_reader is None or _default_dir != resolved:
        _default_reader = LocalGraphArtifactSource(resolved, repo_root=_REPO_ROOT)
        _default_dir = resolved
    return _default_reader

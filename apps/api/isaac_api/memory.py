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
  ``.claude/settings.local.json``, binary extensions (``BINARY_EXTS``, incl.
  ``.png``), and (P24.8 Item 1, defense-in-depth — closes no live leak today,
  since ``.claude/settings.local.json`` is the only sensitive key ever seen in a
  real manifest) secret-shaped extensions/basenames (``SECRET_EXTS`` /
  ``SECRET_BASENAMES``: keys, certs, keystores, ``id_rsa``-style, credential
  files) plus any ``.env``/``.env.*`` or ``*.local.json`` basename.
  ``.claude/skills/**`` is kept: its ``SKILL.md`` files are served as
  project-knowledge metadata only (path + graph metadata, never file contents);
  they were inspected and contain only generic skill definitions with
  repo-relative paths — no secrets, no machine-local/home paths. Local settings
  and the secret patterns above remain excluded regardless. Skills are
  memory/navigation material, never scientific evidence or validation (P24.8
  Item 3). Traversal safety is closed-set membership in this allowlist; the path
  guard is defense-in-depth only.
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
directory; ``SanitizedSnapshotSource`` is a second concrete reader over a
pre-generated sanitized ``memory-snapshot.json`` (the hosted-image seam).
Consumers should depend on the shared method surface (see the ``MemoryReader``
Protocol), not on how a reader loads data, so a future database source, mounted
graph-snapshot volume, hosted memory service, or login-gated institutional backend
can replace/supplement it without rewriting callers. ``get_default_reader()``
selects a provider by precedence: the ``ISAAC_MEMORY_SNAPSHOT`` file override, then
the packaged canonical snapshot if present, then the ``ISAAC_MEMORY_DIR`` live-graph
override (the mounted-volume seam), and finally the repo's ``graphify-out/``
directory. Both readers expose a ``status()`` method (P24.10) carrying the
provider kind, separated availability / integrity, and two provable, separated
freshness concepts (policy_consistency, indexed_sources) — the deployed/app-HEAD
commit is never an input to any freshness value.

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
import copy
import hashlib
import json
import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

# --- constants ----------------------------------------------------------------

GRAPH_FILE = "graph.json"
MANIFEST_FILE = "manifest.json"
LABELS_FILE = ".graphify_labels.json"

ENV_MEMORY_DIR = "ISAAC_MEMORY_DIR"
#: Absolute/relative path to a pre-generated sanitized ``memory-snapshot.json``
#: (the hosted-image seam). When set & non-empty it selects
#: :class:`SanitizedSnapshotSource` over the live-graph reader (see
#: :func:`get_default_reader`).
ENV_MEMORY_SNAPSHOT = "ISAAC_MEMORY_SNAPSHOT"

#: The ``kind`` sentinel a valid snapshot must carry (mirrors the generator's
#: ``scripts/build_memory_snapshot.py::SNAPSHOT_KIND``; kept independent so the
#: memory plane never imports the generator).
SNAPSHOT_KIND = "isaac-memory-snapshot"
#: The single ``snapshot_schema_version`` this reader understands. A snapshot
#: carrying any other version degrades to ``graph_unreadable`` (honest, never a
#: silent mis-read of a shape this code does not know).
SUPPORTED_SNAPSHOT_SCHEMA_VERSION = 1
#: Top-level keys every snapshot must carry (a missing one -> ``graph_unreadable``).
_SNAPSHOT_REQUIRED_KEYS = frozenset({
    "snapshot_schema_version", "kind", "generator",
    "built_at_commit", "source_graph_sha256",
    "overview", "concepts", "concept_detail", "files", "file_detail", "served",
})

#: --- deep (symbol-level) structural layer -----------------------------------
#: A SEPARATE, lazily-loaded sibling artifact of the snapshot (generated by
#: ``scripts/build_memory_snapshot.py --detail-out``). It is deliberately NOT
#: folded into ``memory-snapshot.json``: it is ~1.4x the snapshot's size, only
#: one endpoint needs it, and keeping the snapshot's shape (and therefore
#: ``SUPPORTED_SNAPSHOT_SCHEMA_VERSION``, a hashed input of
#: :func:`compute_memory_policy_fingerprint`) untouched keeps every already
#: committed snapshot's ``policy_consistency`` honestly ``"current"``.
GRAPH_DETAIL_FILE = "memory-graph-detail.json"
#: Absolute/relative path override to a pre-generated graph-detail artifact.
ENV_MEMORY_GRAPH_DETAIL = "ISAAC_MEMORY_GRAPH_DETAIL"
#: The ``kind`` sentinel a valid graph-detail artifact must carry.
GRAPH_DETAIL_KIND = "isaac-memory-graph-detail"
#: The single ``detail_schema_version`` this reader understands; any other
#: version degrades honestly rather than being mis-read.
SUPPORTED_GRAPH_DETAIL_SCHEMA_VERSION = 1
#: The positional row schemas this reader understands. Rows are decoded
#: POSITIONALLY by every consumer (``row[3]`` is the owning source file,
#: ``row[5]`` the community id), so an artifact declaring different keys must be
#: REFUSED rather than silently mis-decoded into a plausible-looking graph whose
#: columns mean something else.
SUPPORTED_GRAPH_DETAIL_NODE_KEYS = ("id", "label", "file_type", "source_file",
                                    "source_location", "community_id")
SUPPORTED_GRAPH_DETAIL_EDGE_KEYS = ("source_index", "target_index", "relation")
#: Top-level keys every graph-detail artifact must carry.
_GRAPH_DETAIL_REQUIRED_KEYS = frozenset({
    "kind", "detail_schema_version", "generator",
    "built_at_commit", "source_graph_sha256", "policy_fingerprint",
    "structural_scope", "structural_basis",
    "served_file_count", "served_path_set_fingerprint",
    "encoding", "node_keys", "edge_keys",
    "nodes", "edges", "community_names", "counts",
})

#: Governance-sensitive prefixes filtered out of the served allowlist (spec §4).
EXCLUDED_PREFIXES = ("examples/", ".superpowers/", "apps/web/.vercel/")
#: Exact repo-relative paths filtered out of the served allowlist.
EXCLUDED_EXACT = frozenset({".claude/settings.local.json"})
#: Binary extensions filtered out (no textual provenance value); ``.png`` required.
BINARY_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf"})
#: P24.8 defense-in-depth: secret-shaped extensions (keys/certs/keystores) filtered
#: out of the served allowlist; closes no live leak, guards future manifest entries.
SECRET_EXTS = frozenset({".key", ".pem", ".p12", ".pfx", ".pkcs12", ".p8", ".keystore", ".jks"})
#: P24.8 defense-in-depth: secret-shaped basenames (private keys / credential files).
SECRET_BASENAMES = frozenset({
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".netrc", ".pgpass", ".pypirc",
    ".htpasswd", "credentials", "credentials.json",
})

MAX_RELATED = 25
MAX_RATIONALES = 10

# --- P24.10 memory-input fingerprint version stamps (spec: phase 24 project
# memory freshness). These pin the exclusion policy, the reader projection shape,
# and the fingerprint algorithm independently, so a change to any one of them
# yields a different policy fingerprint (drift-detectable). Slice 1 defines the
# pure primitives only; generator/reader/route/frontend wiring is later slices.
MEMORY_INPUTS_POLICY_VERSION: int = 1
PROJECTION_VERSION: int = 1
FINGERPRINT_ALGO_VERSION: int = 1
#: Canonical home for the per-rationale character cap. The generator
#: (``scripts/build_memory_snapshot.py``) currently defines its own
#: ``MAX_RATIONALE_CHARS = 280``; a later slice makes it import this. Distinct
#: from ``MAX_RATIONALES`` (a per-file *count* cap). Participates in the policy
#: fingerprint so a changed cap is drift-detectable.
MAX_RATIONALE_CHARS: int = 280

CONCEPT = "concept"
RATIONALE = "rationale"

# --- P26.2 memory-search constants (see the shared ``_run_memory_search``) ----
#: Default page size, hard result cap, and post-normalization minimum query
#: length. Mirror the workspace search core's values so both planes behave the
#: same; kept independent so the memory plane never imports ``search.py``.
_MEM_DEFAULT_LIMIT = 10
_MEM_MAX_RESULTS = 50
_MEM_MIN_QUERY_LEN = 2
#: Reused honest reason string for a too-short query (same value the workspace
#: core emits) — never a verdict.
_MEM_QUERY_TOO_SHORT = "query_too_short"
#: Raw query is truncated to this before normalization (bounds the work).
_MEM_MAX_INPUT_LEN = 256
#: Snippet policy: values at/below this echo whole; longer text windows around
#: the first token hit.
_MEM_SNIPPET_WHOLE_MAX = 120
_MEM_SNIPPET_WINDOW = 80
#: Match-tier ranking (smaller sorts first): exact < prefix < token < substring.
_MEM_TIER_RANK = {"exact": 0, "prefix": 1, "token": 2, "substring": 3}


# --- provider seam ------------------------------------------------------------


class MemoryReader(Protocol):
    """Stable read surface future memory sources (db / volume / hosted) mirror."""

    def overview(self) -> dict: ...
    def concepts(self) -> list: ...
    def concept(self, concept_id: str) -> Optional[dict]: ...
    def files(self) -> list: ...
    def file(self, path: str) -> Optional[dict]: ...
    def classify_path(self, path: str) -> str: ...
    def status(self) -> dict: ...
    def search(self, query: str, limit: int = _MEM_DEFAULT_LIMIT, offset: int = 0) -> dict: ...


# --- parsed state -------------------------------------------------------------


@dataclass(frozen=True)
class _GraphState:
    """Immutable derived view of one graph load; swapped atomically into the cache."""

    key: tuple
    available: bool
    reason: Optional[str] = None
    #: Snapshot-integrity axis, SEPARATE from availability (P24.10). A live graph
    #: is ``"verified"`` when available, ``"malformed"`` when present-but-unreadable,
    #: ``"unknown"`` when absent. (Local graphs have no schema version, so never
    #: ``"unsupported"``.)
    integrity: str = "unknown"
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


@dataclass(frozen=True)
class _SnapshotState:
    """Immutable parsed view of one sanitized snapshot load; swapped atomically
    into the cache (mirrors :class:`_GraphState`)."""

    key: tuple
    available: bool
    reason: Optional[str] = None
    #: Snapshot-integrity axis, SEPARATE from availability (P24.10):
    #: ``"verified"`` (present + supported schema + valid shape), ``"unsupported"``
    #: (present but unsupported schema version), ``"malformed"`` (present but bad
    #: keys/types/unreadable), ``"unknown"`` (no artifact). A malformed snapshot is
    #: BOTH available=False AND integrity="malformed".
    integrity: str = "unknown"
    built_at_commit: Optional[str] = None
    source_graph_sha256: Optional[str] = None
    snapshot_schema_version: Optional[int] = None
    #: The snapshot's embedded top-level ``memory_inputs`` object (P24.10), or
    #: ``None`` when absent/malformed. Its presence + internal consistency drive
    #: the policy_consistency / indexed_sources freshness concepts; its absence
    #: degrades both to ``"unknown"`` without affecting availability/integrity.
    memory_inputs: Optional[dict] = None
    overview: dict = field(default_factory=dict)
    concepts: list = field(default_factory=list)
    concept_detail: dict = field(default_factory=dict)
    files: list = field(default_factory=list)
    file_detail: dict = field(default_factory=dict)
    served: frozenset = frozenset()


# --- helpers ------------------------------------------------------------------


def _memory_input_freshness(available: bool, memory_inputs) -> dict:
    """The shared, null-safe P24.10 freshness derivation for both providers'
    ``status()``, computed ONLY from a snapshot's embedded ``memory_inputs`` — the
    deployed/app-HEAD commit is NEVER an input to any value here.

    Returns the five ``memory_inputs``-derived status fields::

        policy_fingerprint, policy_consistency, served_manifest_fingerprint,
        served_file_count, indexed_sources

    * **policy_consistency** — ``"current"`` iff the runtime-recomputed
      :func:`compute_memory_policy_fingerprint` equals the embedded fingerprint;
      ``"stale"`` iff both present & differ; ``"unknown"`` when unavailable or the
      embedded fingerprint is absent/None. Policy is recomputable at runtime from
      shipped constants, so a real mismatch is a provable ``"stale"``.
    * **indexed_sources** — ``"current"`` iff ``memory_inputs`` is present AND
      internally consistent (the recomputed aggregate over its embedded
      ``served_content_manifest`` equals the embedded
      ``served_manifest_fingerprint``); otherwise ``"unknown"``. It is NEVER
      ``"stale"`` here: the hosted runtime does not ship the served files, so it
      cannot recompute their on-disk digests — actual content drift is CI's
      authority. Internal inconsistency degrades to ``"unknown"``, never a
      manufactured ``"stale"``.

    A live graph (no embedded ``memory_inputs``) passes ``memory_inputs=None`` and
    gets all-unknown / all-None: it carries no fingerprint reference to prove
    against.
    """
    mi = memory_inputs if isinstance(memory_inputs, dict) else None

    policy_fp = mi.get("policy_fingerprint") if mi else None
    policy_fp = policy_fp if isinstance(policy_fp, str) else None
    served_fp = mi.get("served_manifest_fingerprint") if mi else None
    served_fp = served_fp if isinstance(served_fp, str) else None
    served_count = mi.get("served_file_count") if mi else None
    if not (isinstance(served_count, int) and not isinstance(served_count, bool)):
        served_count = None

    if not available or policy_fp is None:
        policy_consistency = "unknown"
    else:
        policy_consistency = (
            "current" if compute_memory_policy_fingerprint() == policy_fp else "stale"
        )

    indexed_sources = "unknown"
    if available and mi is not None and served_fp is not None:
        manifest = mi.get("served_content_manifest")
        if isinstance(manifest, list):
            try:
                recomputed = compute_served_manifest_fingerprint(manifest)
            except Exception:
                recomputed = None
            if recomputed is not None and recomputed == served_fp:
                indexed_sources = "current"
            # else stays "unknown" — NEVER "stale" (runtime cannot recompute file
            # digests; drift detection is CI's authority).

    return {
        "policy_fingerprint": policy_fp,
        "policy_consistency": policy_consistency,
        "served_manifest_fingerprint": served_fp,
        "served_file_count": served_count,
        "indexed_sources": indexed_sources,
    }


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
    # ``base``/``ext`` are computed on the "/"-joined manifest key (never a native
    # OS path), so this is OS-independent regardless of host path semantics.
    base = path.rsplit("/", 1)[-1]
    ext = os.path.splitext(path)[1].lower()
    if ext in BINARY_EXTS or ext in SECRET_EXTS:
        return False
    # ``.env`` / ``.env.local`` / ``.env.production`` / ... — precise basename
    # match, not a substring check, so ``environment.py`` is unaffected.
    if base == ".env" or base.startswith(".env."):
        return False
    if base in SECRET_BASENAMES:
        return False
    # Local-only settings, generalizing the ``.claude/settings.local.json`` exact
    # match above; ``local.json`` (no leading dot-segment) is deliberately kept.
    if base.endswith(".local.json"):
        return False
    return True


def _served_source_file(sf) -> Optional[str]:
    """A concept's anchor path, but only when it is governance-served.

    Concept ``source_file`` values come from GRAPH NODES, not the manifest served
    allowlist, so an anchor can point at a governance-excluded / secret path (e.g.
    ``examples/README.md``) OR — for a future snapshot/db/hosted provider — an
    absolute / traversal path a served-only check would miss. Return ``sf``
    unchanged only when it is truthy, path-safe (mirrors ``classify_path``'s
    ``_is_unsafe`` contract), AND governance-served; otherwise ``None`` so the
    path is withheld while the concept itself is still surfaced. Single-sources
    the anchor policy for both the concept summary (``_derive``) and the concept
    detail (``concept``).
    """
    if sf and not LocalGraphArtifactSource._is_unsafe(sf) and _is_served(sf):
        return sf
    return None


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


def _prefer_related(cand: tuple, prev: tuple) -> bool:
    """Whether ``cand`` should replace the accumulated related entry ``prev``.

    Both are ``(weight, relation, extra)`` where ``extra`` is the file's
    ``file_type`` (related files) or the concept's ``label`` (related concepts).
    Higher weight always wins; on a weight tie the lexicographically smallest
    ``(relation or "", extra or "")`` wins. This makes the retained payload a
    CANONICAL choice rather than first-seen, so ``_related`` is independent of
    the order in which equal-weight multi-edges to the same target are visited
    (and thus independent of set-iteration / hash-seed order).
    """
    if cand[0] != prev[0]:
        return cand[0] > prev[0]
    return (cand[1] or "", cand[2] or "") < (prev[1] or "", prev[2] or "")


# --- P26.2 shared memory-search algorithm -------------------------------------
#
# One deterministic algorithm both providers delegate to. It reads ONLY the
# reader's own governance-filtered public methods (``overview`` / ``concepts`` /
# ``files`` / ``file`` / ``status``) — never a raw ``_GraphState`` /
# ``_SnapshotState`` collection — so every governance filter (served allowlist,
# secret/unsafe-path withholding, concept-anchor nulling) is inherited, and no
# excluded/secret/unsafe path can surface even when the query "matches" its name.
# Pure stdlib (``unicodedata`` + ``str``): no ``re``, no import of ``search.py``.
# It reimplements the workspace core's token-AND four-tier ranking locally.


def _mem_normalize(text: str) -> str:
    """Deterministic query/field normalization: NFC, casefold, collapse whitespace."""
    nfc = unicodedata.normalize("NFC", text)
    return " ".join(nfc.casefold().split())


def _mem_tier(field_cf: str, query_cf: str, tokens: tuple) -> Optional[str]:
    """Best matching tier of a normalized field against the normalized query.

    Token-AND at every tier: a match requires EVERY query token present. Returns
    ``None`` when the field does not match at all."""
    if not field_cf:
        return None
    if field_cf == query_cf:
        return "exact"
    if field_cf.startswith(query_cf):
        return "prefix"
    field_tokens = field_cf.split()
    if all(t in field_tokens for t in tokens):
        return "token"
    if all(t in field_cf for t in tokens):
        return "substring"
    return None


def _mem_snippet_and_offsets(text: str, tokens: tuple) -> tuple:
    """A deterministic snippet of ``text`` plus token offsets within it.

    Short values echo whole; long text windows (~80 chars) around the first token
    hit. Offsets index into the returned snippet (list of ``[start, end]``) so a
    client can highlight without any server-authored markup."""
    cf = text.casefold()
    first = None
    for t in tokens:
        i = cf.find(t)
        if i != -1 and (first is None or i < first):
            first = i
    if first is None:
        first = 0

    if len(text) <= _MEM_SNIPPET_WHOLE_MAX:
        snippet = text
    else:
        start = max(0, first - _MEM_SNIPPET_WINDOW // 2)
        snippet = text[start:start + _MEM_SNIPPET_WINDOW]

    scf = snippet.casefold()
    seen = set()
    for t in tokens:
        idx = scf.find(t)
        if idx != -1:
            seen.add((idx, idx + len(t)))
    ordered = sorted(seen)
    if not ordered:
        # Defensive: a matched candidate always has an in-snippet token, but never
        # emit an empty offsets list.
        ordered = [(0, min(len(snippet), 1))]
    return snippet, [[s, e] for s, e in ordered]


def _mem_best_aspect(aspects: list, query_cf: str, tokens: tuple):
    """Choose the single best-tier aspect of a candidate.

    ``aspects`` is a list of ``(text, field, reason, facet_priority)`` ordered by
    ascending facet priority, so a tier tie deterministically favors the
    lower-facet-priority field (like the workspace core's ``_best_aspect``).
    Returns ``(tier, text, field, reason, facet_priority)`` or ``None``."""
    best = None  # (tier_rank, order, tier, text, field, reason, facet)
    for order, (text, field, reason, facet) in enumerate(aspects):
        if not isinstance(text, str) or not text:
            continue
        tier = _mem_tier(_mem_normalize(text), query_cf, tokens)
        if tier is None:
            continue
        rank = _MEM_TIER_RANK[tier]
        if best is None or rank < best[0]:
            best = (rank, order, tier, text, field, reason, facet)
    if best is None:
        return None
    return best[2], best[3], best[4], best[5], best[6]


def _run_memory_search(reader, query: str, limit: int = _MEM_DEFAULT_LIMIT,
                       offset: int = 0) -> dict:
    """The shared, deterministic memory-plane search both providers delegate to.

    Reads only the reader's governance-filtered public surface; NEVER raises (an
    unavailable/degraded plane returns an honest empty envelope). Ranking is a
    fully deterministic ascending tuple ``(tier_rank, facet_priority,
    natural_key, match.field)``; results are truncated to
    :data:`_MEM_MAX_RESULTS` (that count is ``total``), then paginated."""
    clamped_limit = max(0, min(limit, _MEM_MAX_RESULTS))
    clamped_offset = max(0, offset)

    def _empty(available, reason):
        return {"available": available, "reason": reason, "total": 0,
                "returned": 0, "limit": clamped_limit, "offset": clamped_offset,
                "results": []}

    try:
        ov = reader.overview()
    except Exception:
        return _empty(False, "graph_unreadable")
    if not ov.get("available"):
        return _empty(False, ov.get("reason"))

    normalized = _mem_normalize((query or "")[:_MEM_MAX_INPUT_LEN])
    if len(normalized) < _MEM_MIN_QUERY_LEN:
        return _empty(True, _MEM_QUERY_TOO_SHORT)

    tokens = tuple(normalized.split())
    try:
        provider_kind = reader.status().get("provider_kind")
    except Exception:
        provider_kind = None
    source = f"memory:{provider_kind}"

    rows = []  # (sort_key, result)

    def _emit(kind, *, cid, path, label, community_name, tier, field, reason,
              text, facet, navigate_to):
        snippet, offsets = _mem_snippet_and_offsets(text, tokens)
        result = {
            "kind": kind, "id": cid, "path": path, "label": label,
            "community_name": community_name, "navigate_to": navigate_to,
            "plane": "memory", "source": source,
            "match": {"field": field, "snippet": snippet, "reason": reason,
                      "tier": tier, "offsets": offsets},
        }
        natural_key = (cid if cid is not None else path) or ""
        rows.append(((_MEM_TIER_RANK[tier], facet, natural_key, field), result))

    for c in reader.concepts():
        cid = c.get("id")
        community_name = c.get("community_name")
        aspects = [
            (c.get("label"), "concept.label", "matched concept label", 0),
            (cid, "concept.id", "matched concept identifier", 2),
            (community_name, "concept.community_name", "matched concept community", 3),
        ]
        best = _mem_best_aspect(aspects, normalized, tokens)
        if best is None:
            continue
        tier, text, field, reason, facet = best
        _emit("concept", cid=cid, path=None, label=c.get("label"),
              community_name=community_name, tier=tier, field=field, reason=reason,
              text=text, facet=facet, navigate_to=f"/memory?concept={cid}")

    for f in reader.files():
        path = f.get("path")
        community_name = f.get("community_name")
        aspects = [
            (path, "file.path", "matched file path", 1),
            (community_name, "file.community_name", "matched file community", 3),
            (f.get("file_type"), "file.file_type", "matched file type", 4),
        ]
        best = _mem_best_aspect(aspects, normalized, tokens)
        if best is not None:
            tier, text, field, reason, facet = best
            _emit("file", cid=None, path=path, label=path,
                  community_name=community_name, tier=tier, field=field,
                  reason=reason, text=text, facet=facet,
                  navigate_to=f"/memory?file={path}")

        try:
            detail = reader.file(path)
        except Exception:
            detail = None
        if detail is None:
            continue
        for rat in detail.get("rationales") or []:
            if not isinstance(rat, str) or not rat:
                continue
            tier = _mem_tier(_mem_normalize(rat), normalized, tokens)
            if tier is None:
                continue
            _emit("rationale", cid=None, path=path, label=path,
                  community_name=community_name, tier=tier, field="rationale",
                  reason="matched rationale text", text=rat, facet=5,
                  navigate_to=f"/memory?file={path}")

    rows.sort(key=lambda r: r[0])
    truncated = rows[:_MEM_MAX_RESULTS]
    total = len(truncated)
    page = [r for _, r in truncated[clamped_offset:clamped_offset + clamped_limit]]
    return {"available": True, "reason": None, "total": total,
            "returned": len(page), "limit": clamped_limit,
            "offset": clamped_offset, "results": page}


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
            return _GraphState(key=key, available=False, reason="graph_absent",
                               integrity="unknown")
        try:
            graph = _load_json(self.graph_path)
        except (ValueError, OSError):
            return _GraphState(key=key, available=False, reason="graph_unreadable",
                               integrity="malformed")
        if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
            return _GraphState(key=key, available=False, reason="graph_unreadable",
                               integrity="malformed")

        # Never-raise guard over the whole derivation: a JSON-valid graph whose
        # VALUES have unexpected types (e.g. string ``community``, non-string
        # ``source_file``) must degrade to graph_unreadable, never propagate —
        # a future db/hosted provider may carry different type conventions. A
        # blanket wrapper is the deliberate choice here; no per-field coercion.
        try:
            return self._derive(key, graph)
        except Exception:
            return _GraphState(key=key, available=False, reason="graph_unreadable",
                               integrity="malformed")

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
            # Normalize once at build so ALL downstream weight arithmetic
            # (dedup max, related ordering) operates on real numbers: any
            # non-numeric weight (str, None, list, ...) degrades to 0.0.
            # bool is deliberately excluded — JSON true/false is not a weight.
            w = link.get("weight")
            weight = w if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0
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
            sf = _served_source_file(node.get("source_file"))
            summary = {
                "id": node.get("id"),
                "label": node.get("label"),
                "community_id": _community_id(node.get("community")),
                "community_name": self._community_name(node.get("community"), labels),
                "source_file": sf,
                "on_disk": self._on_disk(sf),
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
            integrity="verified",
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
        nodes in the same file (``self_path``) are skipped.

        Order-independent / deterministic across processes and hash seeds: the
        node set is iterated in SORTED order, and for equal-weight multi-edges to
        the same target the retained ``(relation, file_type/label)`` payload is
        the canonical (lexicographically smallest) choice via
        :func:`_prefer_related`, never first-seen — so the result never depends
        on set-iteration order."""
        files_acc: dict = {}
        concepts_acc: dict = {}
        for nid in sorted(node_ids):
            for other_id, relation, weight in state.adjacency.get(nid, []):
                other = state.nodes_by_id.get(other_id)
                if other is None:
                    continue
                if other.get("file_type") == CONCEPT:
                    if other_id in node_ids:
                        continue
                    cand = (weight, relation, other.get("label"))
                    prev = concepts_acc.get(other_id)
                    if prev is None or _prefer_related(cand, prev):
                        concepts_acc[other_id] = cand
                else:
                    opath = other.get("source_file")
                    # Related file paths come from graph nodes, not the served
                    # allowlist, so drop any path-unsafe (absolute/traversal, for
                    # a future snapshot/db/hosted provider) or governance-excluded
                    # / secret path (e.g. examples/**) BEFORE the sort/cap — a
                    # related lead must never surface a path the file endpoints
                    # would 400/404.
                    if (not opath or opath == self_path
                            or self._is_unsafe(opath) or not _is_served(opath)):
                        continue
                    cand = (weight, relation, other.get("file_type"))
                    prev = files_acc.get(opath)
                    if prev is None or _prefer_related(cand, prev):
                        files_acc[opath] = cand
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
        sf = _served_source_file(node.get("source_file"))
        detail = {
            "id": node.get("id"),
            "label": node.get("label"),
            "community_id": _community_id(node.get("community")),
            "community_name": self._community_name(node.get("community"), state.labels),
            "source_file": sf,
            "on_disk": self._on_disk(sf),
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
        if "\\" in path:
            return True
        # Segment-based traversal check: reject ``..`` only when it is its own
        # ``/``-delimited segment (real traversal), not merely a substring of a
        # benign filename like ``docs/my..note.md``. Backslash-separated paths are
        # already rejected above, so a ``..\`` segment can never slip past the split.
        if ".." in path.split("/"):
            return True
        return False

    def status(self) -> dict:
        """Separated status/freshness descriptor for the seam (P24.10).

        A live graph carries NO embedded ``memory_inputs`` (only generated
        snapshots do), so it has no fingerprint reference to prove against:
        ``policy_consistency`` and ``indexed_sources`` are honestly ``"unknown"``
        and both fingerprints ``None``. (Live-graph-vs-repo drift is
        ``check_graphify_freshness.py``'s separate concern, out of scope here.)
        ``source_graph_commit`` is the graph's ``built_at_commit`` (version
        metadata, never a freshness input); a local reader has no snapshot
        schema/sha256, so those are ``None``. The key set matches
        :class:`SanitizedSnapshotSource.status` exactly (provider parity)."""
        state = self._state_now()
        fresh = _memory_input_freshness(state.available, None)
        return {
            "provider_kind": "local-graph",
            "available": state.available,
            "integrity": state.integrity,
            "policy_fingerprint": fresh["policy_fingerprint"],
            "policy_consistency": fresh["policy_consistency"],
            "served_manifest_fingerprint": fresh["served_manifest_fingerprint"],
            # Live served count is honest here (no manifest fingerprint to tie it
            # to); null when the graph is unavailable.
            "served_file_count": state.served_file_count if state.available else None,
            "indexed_sources": fresh["indexed_sources"],
            "freshness_scope": "served_files_only",
            "freshness_basis": "ci_content_manifest",
            "source_graph_commit": state.built_at_commit,
            "source_graph_sha256": None,
            "snapshot_schema_version": None,
        }

    def search(self, query: str, limit: int = _MEM_DEFAULT_LIMIT, offset: int = 0) -> dict:
        """Deterministic memory-plane search; delegates to the shared algorithm
        (P26.2). Governance filtering is inherited via this reader's public methods."""
        return _run_memory_search(self, query, limit, offset)


# --- sanitized snapshot reader ------------------------------------------------


class SanitizedSnapshotSource:
    """Concrete :class:`MemoryReader` over a pre-generated sanitized
    ``memory-snapshot.json`` (see ``scripts/build_memory_snapshot.py``).

    This is the hosted-image analogue of :class:`LocalGraphArtifactSource`: the
    snapshot already contains the reader's *returned* metadata (overview, concept
    and file summaries/details, the served allowlist) with no raw graph, no file
    contents, and no governance-excluded paths. This reader therefore only parses
    and serves that projection — it never re-derives graph logic — and returns
    shapes byte-identical to the local reader so the ``/api/memory/*`` routes need
    zero change. ``on_disk`` is whatever the snapshot baked (uniformly ``false``);
    ``graph_mtime`` is the snapshot's baked ``null``.

    Same mtime-cache pattern as the local reader: the snapshot is parsed lazily on
    first use and cached, keyed by its file mtime, re-parsed only on change, and
    swapped atomically into one attribute (GIL-safe; no lock). Any parse/derive
    problem degrades honestly to the SAME reason strings the local reader uses
    (``graph_absent`` / ``graph_unreadable``) — it never raises, never 500s.
    """

    def __init__(self, snapshot_path):
        self.snapshot_path = Path(snapshot_path)
        self.reload_count = 0
        self._state: Optional[_SnapshotState] = None

    # -- cache --

    def _mtime(self, path: Path) -> Optional[float]:
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def _current_key(self) -> tuple:
        return (self._mtime(self.snapshot_path),)

    def _state_now(self) -> _SnapshotState:
        key = self._current_key()
        state = self._state
        if state is not None and state.key == key:
            return state
        new_state = self._build(key)
        self._state = new_state  # atomic swap; readers see one consistent object
        return new_state

    # -- build --

    def _build(self, key: tuple) -> _SnapshotState:
        self.reload_count += 1

        if not self.snapshot_path.is_file():
            return _SnapshotState(key=key, available=False, reason="graph_absent",
                                  integrity="unknown")
        try:
            data = _load_json(self.snapshot_path)
        except (ValueError, OSError):
            return _SnapshotState(key=key, available=False, reason="graph_unreadable",
                                  integrity="malformed")
        if not isinstance(data, dict):
            return _SnapshotState(key=key, available=False, reason="graph_unreadable",
                                  integrity="malformed")

        # Integrity axis (P24.10), assessed BEFORE the blanket-degrade wrapper so a
        # present-but-unsupported schema version reports integrity="unsupported"
        # (distinct from the malformed shapes). A present int version that is not
        # the supported one is "unsupported"; a missing/non-int version falls
        # through to _derive, which raises -> "malformed".
        version = data.get("snapshot_schema_version")
        if isinstance(version, int) and not isinstance(version, bool) \
                and version != SUPPORTED_SNAPSHOT_SCHEMA_VERSION:
            return _SnapshotState(key=key, available=False, reason="graph_unreadable",
                                  integrity="unsupported", snapshot_schema_version=version)

        # Blanket never-raise guard over the whole derivation, exactly like
        # ``LocalGraphArtifactSource._build``: a missing key, wrong ``kind``,
        # wrong value type, or a structurally incomplete projection all degrade to
        # ``graph_unreadable`` / integrity="malformed" — never propagate.
        try:
            return self._derive(key, data)
        except Exception:
            return _SnapshotState(key=key, available=False, reason="graph_unreadable",
                                  integrity="malformed")

    def _derive(self, key: tuple, data: dict) -> _SnapshotState:
        """Validate and load a snapshot dict into immutable state. Raises on any
        shape/version/completeness problem; ``_build`` catches and degrades."""
        missing = _SNAPSHOT_REQUIRED_KEYS - set(data)
        if missing:
            raise ValueError(f"snapshot missing required keys: {sorted(missing)}")
        if data.get("kind") != SNAPSHOT_KIND:
            raise ValueError(f"snapshot kind mismatch: {data.get('kind')!r}")
        version = data.get("snapshot_schema_version")
        if version != SUPPORTED_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(f"unsupported snapshot_schema_version: {version!r}")

        overview = data["overview"]
        concepts = data["concepts"]
        concept_detail = data["concept_detail"]
        files = data["files"]
        file_detail = data["file_detail"]
        served = data["served"]
        if not isinstance(overview, dict):
            raise ValueError("overview must be an object")
        if not (isinstance(concepts, list) and isinstance(files, list)
                and isinstance(served, list)):
            raise ValueError("concepts/files/served must be lists")
        if not (isinstance(concept_detail, dict) and isinstance(file_detail, dict)):
            raise ValueError("concept_detail/file_detail must be objects")

        # Structural completeness: every summary must have a matching detail entry
        # (a projection with a dangling summary is corrupt, not partially valid).
        for c in concepts:
            if not isinstance(c, dict) or c.get("id") not in concept_detail:
                raise ValueError("concept in concepts[] missing from concept_detail")
        for f in files:
            if not isinstance(f, dict) or f.get("path") not in file_detail:
                raise ValueError("path in files[] missing from file_detail")

        # ``memory_inputs`` is an ADDITIVE, optional top-level object (P24.10): a
        # pre-P24.10 snapshot lacks it and stays fully verified. A present-but-not
        # a dict value degrades to None (freshness -> unknown), never unavailable.
        memory_inputs = data.get("memory_inputs")
        if not isinstance(memory_inputs, dict):
            memory_inputs = None

        return _SnapshotState(
            key=key,
            available=True,
            integrity="verified",
            built_at_commit=data.get("built_at_commit"),
            source_graph_sha256=data.get("source_graph_sha256"),
            snapshot_schema_version=version,
            memory_inputs=memory_inputs,
            overview=overview,
            concepts=concepts,
            concept_detail=concept_detail,
            files=files,
            file_detail=file_detail,
            served=frozenset(served),
        )

    # -- public read surface (shapes identical to LocalGraphArtifactSource) --

    def overview(self) -> dict:
        state = self._state_now()
        if not state.available:
            return {"available": False, "reason": state.reason}
        # The snapshot's overview already carries built_at_commit + counts +
        # graph_mtime:null, matching the local reader's key set exactly.
        return {"available": True, **state.overview}

    def concepts(self) -> list:
        state = self._state_now()
        if not state.available:
            return []
        return [copy.deepcopy(c) for c in state.concepts]

    def concept(self, concept_id: str) -> Optional[dict]:
        state = self._state_now()
        if not state.available:
            return None
        detail = state.concept_detail.get(concept_id)
        if detail is None:
            return None
        return copy.deepcopy(detail)  # fresh copy; never leak cached state

    def files(self) -> list:
        state = self._state_now()
        if not state.available:
            return []
        return [copy.deepcopy(f) for f in state.files]

    def file(self, path: str) -> Optional[dict]:
        state = self._state_now()
        if not state.available:
            return None
        detail = state.file_detail.get(path)
        if detail is None:
            return None
        return copy.deepcopy(detail)  # fresh copy; never leak cached state

    def classify_path(self, path: str) -> str:
        """``"unsafe"`` / ``"served"`` / ``"not_indexed"`` — the SAME contract as
        the local reader, using the identical traversal guard
        (``LocalGraphArtifactSource._is_unsafe``) so a path unsafe locally is
        unsafe here regardless of snapshot availability."""
        if LocalGraphArtifactSource._is_unsafe(path):
            return "unsafe"
        state = self._state_now()
        if state.available and path in state.served:
            return "served"
        return "not_indexed"

    def status(self) -> dict:
        """Separated status/freshness descriptor for the seam (P24.10).

        Carries the snapshot's own provenance (schema version, source graph commit
        + sha256, integrity) plus the two separated, provable freshness concepts
        derived ONLY from the embedded ``memory_inputs`` (never the deployed/app
        commit): ``policy_consistency`` (recomputed policy fingerprint vs embedded)
        and ``indexed_sources`` (embedded manifest internal consistency; never
        ``"stale"`` — the hosted runtime cannot recompute file digests). A snapshot
        without ``memory_inputs`` degrades both to ``"unknown"`` while staying
        available + integrity="verified". The key set matches
        :class:`LocalGraphArtifactSource.status` exactly (provider parity)."""
        state = self._state_now()
        fresh = _memory_input_freshness(state.available, state.memory_inputs)
        return {
            "provider_kind": "sanitized-snapshot",
            "available": state.available,
            "integrity": state.integrity,
            "policy_fingerprint": fresh["policy_fingerprint"],
            "policy_consistency": fresh["policy_consistency"],
            "served_manifest_fingerprint": fresh["served_manifest_fingerprint"],
            "served_file_count": fresh["served_file_count"],
            "indexed_sources": fresh["indexed_sources"],
            "freshness_scope": "served_files_only",
            "freshness_basis": "ci_content_manifest",
            "source_graph_commit": state.built_at_commit,
            "source_graph_sha256": state.source_graph_sha256,
            "snapshot_schema_version": state.snapshot_schema_version,
        }

    def search(self, query: str, limit: int = _MEM_DEFAULT_LIMIT, offset: int = 0) -> dict:
        """Deterministic memory-plane search; delegates to the shared algorithm
        (P26.2), byte-identical behavior to the local reader modulo the documented
        rationale truncation. Governance filtering is inherited via public methods."""
        return _run_memory_search(self, query, limit, offset)


# --- deep (symbol-level) graph detail source ----------------------------------


@dataclass(frozen=True)
class _GraphDetailState:
    """Immutable parsed view of one graph-detail artifact load; swapped
    atomically into the cache (mirrors :class:`_SnapshotState`)."""

    key: tuple
    available: bool
    reason: Optional[str] = None
    #: ``"verified"`` / ``"unsupported"`` / ``"malformed"`` / ``"unknown"`` —
    #: the same integrity vocabulary the snapshot reader uses.
    integrity: str = "unknown"
    detail_schema_version: Optional[int] = None
    data: Optional[dict] = None


class GraphDetailSource:
    """Read-only loader for the deep (symbol-level) structural layer.

    A deliberately narrow, SEPARATE seam from :class:`MemoryReader`: the deep
    layer is large, is needed by exactly one endpoint, and must be lazily
    fetched — never folded into ``/api/memory/graph``. This class parses and
    caches the committed artifact and validates only its structure; it derives
    no graph logic, invents no node/edge/relation, and reads no file contents.

    Honest degradation mirrors the other memory-plane readers: a missing
    artifact -> ``detail_absent``; unreadable / structurally wrong / unsupported
    schema version -> ``detail_unreadable``. Nothing ever raises out of
    :meth:`detail`, so the route can never 500.

    The returned ``data`` is the CACHED parsed artifact and is contractually
    read-only: callers must treat it as immutable (the route and
    ``memory_graph.build_graph_detail`` only slice and read it). It is not
    deep-copied per call on purpose — the payload is ~6.7k rows and copying it
    per request would be pure waste.

    That contract is partially ENFORCED rather than only documented:
    ``memory_graph._build_detail_available`` rebuilds the outer
    ``nodes``/``edges``/``community_names``/``encoding`` containers, so a caller
    mutating the response's own lists/dicts (``append``/``sort``/``clear``)
    cannot reach this cache. The individual ROWS remain shared, so an in-place
    row edit would still corrupt the cache; that residual is the read-only
    contract's remaining scope, and is why no consumer may write to a row.
    """

    def __init__(self, detail_path):
        self.detail_path = Path(detail_path)
        self.reload_count = 0
        self._state: Optional[_GraphDetailState] = None

    def _mtime(self, path: Path) -> Optional[float]:
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def _state_now(self) -> _GraphDetailState:
        key = (self._mtime(self.detail_path),)
        state = self._state
        if state is not None and state.key == key:
            return state
        new_state = self._build(key)
        self._state = new_state  # atomic swap; readers see one consistent object
        return new_state

    def _build(self, key: tuple) -> _GraphDetailState:
        self.reload_count += 1

        if not self.detail_path.is_file():
            return _GraphDetailState(key=key, available=False, reason="detail_absent",
                                     integrity="unknown")
        # KNOWN, CURRENTLY-SAFE PROPERTY (recorded, not machinery): there is no
        # BYTE-SIZE guard before this read. The path is env-overridable
        # (``ISAAC_MEMORY_GRAPH_DETAIL``), so an operator could point it at an
        # arbitrarily large file, which would be read fully into memory here.
        # Why this is accepted rather than capped: the ``is_file()`` guard above
        # already rejects non-regular files, so an endless character device such
        # as ``/dev/zero`` degrades to ``detail_absent`` without ever reaching this
        # read (verified), and the env override is an operator-controlled
        # deployment knob, never end-user input — a byte cap would add a tunable
        # without closing an untrusted-input path.
        try:
            data = _load_json(self.detail_path)
        except (ValueError, OSError):
            return _GraphDetailState(key=key, available=False,
                                     reason="detail_unreadable", integrity="malformed")
        if not isinstance(data, dict):
            return _GraphDetailState(key=key, available=False,
                                     reason="detail_unreadable", integrity="malformed")

        version = data.get("detail_schema_version")
        if isinstance(version, int) and not isinstance(version, bool) \
                and version != SUPPORTED_GRAPH_DETAIL_SCHEMA_VERSION:
            return _GraphDetailState(key=key, available=False,
                                     reason="detail_unreadable", integrity="unsupported",
                                     detail_schema_version=version)

        # Blanket never-raise guard, exactly like the other readers' ``_build``.
        try:
            return self._derive(key, data)
        except Exception:
            return _GraphDetailState(key=key, available=False,
                                     reason="detail_unreadable", integrity="malformed")

    def _derive(self, key: tuple, data: dict) -> _GraphDetailState:
        """Validate an artifact dict into immutable state. Raises on any
        shape/version problem; ``_build`` catches and degrades."""
        # EXACT key set, matching the generator's own ``_validate_detail_shape``
        # strictness. A subset check would let the runtime accept an artifact the
        # generator refuses to write; the version field is the intended mechanism
        # for adding a key, not silent tolerance of unknown ones.
        keys = set(data)
        missing = _GRAPH_DETAIL_REQUIRED_KEYS - keys
        if missing:
            raise ValueError(f"graph detail missing required keys: {sorted(missing)}")
        extra = keys - _GRAPH_DETAIL_REQUIRED_KEYS
        if extra:
            raise ValueError(f"graph detail has unexpected top-level keys: {sorted(extra)}")
        if data.get("kind") != GRAPH_DETAIL_KIND:
            raise ValueError(f"graph detail kind mismatch: {data.get('kind')!r}")
        # ``isinstance(True, int)`` is True and ``True != 1`` is False, so a bare
        # ``version != 1`` comparison would ACCEPT ``detail_schema_version: true``
        # as version 1 and echo it into provenance. Same bool/int guard already
        # applied to ``served_file_count`` and to edge endpoints below.
        version = data.get("detail_schema_version")
        if not (isinstance(version, int) and not isinstance(version, bool)
                and version == SUPPORTED_GRAPH_DETAIL_SCHEMA_VERSION):
            raise ValueError(f"unsupported detail_schema_version: {version!r}")
        for list_key in ("nodes", "edges", "node_keys", "edge_keys"):
            if not isinstance(data[list_key], list):
                raise ValueError(f"{list_key} must be a list")
        for dict_key in ("community_names", "counts", "encoding"):
            if not isinstance(data[dict_key], dict):
                raise ValueError(f"{dict_key} must be an object")
        # Provenance MUST be present and non-null: a deep layer whose
        # point-in-time provenance is unknown could be mistaken for a current
        # code map, which is precisely the dishonesty this seam must prevent.
        for prov_key in ("built_at_commit", "source_graph_sha256",
                         "structural_scope", "structural_basis",
                         "served_path_set_fingerprint", "policy_fingerprint"):
            value = data.get(prov_key)
            if not (isinstance(value, str) and value):
                raise ValueError(f"graph detail {prov_key} must be a non-empty string")
        if not isinstance(data.get("served_file_count"), int) \
                or isinstance(data.get("served_file_count"), bool):
            raise ValueError("graph detail served_file_count must be an int")

        # Positional decoding demands the declared column order match exactly.
        if tuple(data["node_keys"]) != SUPPORTED_GRAPH_DETAIL_NODE_KEYS:
            raise ValueError(f"unsupported node_keys: {data['node_keys']!r}")
        if tuple(data["edge_keys"]) != SUPPORTED_GRAPH_DETAIL_EDGE_KEYS:
            raise ValueError(f"unsupported edge_keys: {data['edge_keys']!r}")

        # Row shape, validated ONCE per load (then cached) rather than per
        # request. An edge endpoint out of range is rejected here, so the
        # response can never carry a dangling edge that came from the file
        # itself — the capping logic downstream only has to keep it that way.
        node_count = len(data["nodes"])
        for row in data["nodes"]:
            if not (isinstance(row, list)
                    and len(row) == len(SUPPORTED_GRAPH_DETAIL_NODE_KEYS)):
                raise ValueError("graph detail node row shape mismatch")
            if not (isinstance(row[0], str) and row[0]):
                raise ValueError("graph detail node id must be a non-empty string")
            # KNOWN, CURRENTLY-SAFE PROPERTY (recorded, not machinery): ``id`` has
            # no path-shape rule. The generator derives ids from the source graph's
            # own node ids, which are ``/``-free by construction (0 of the 2,612 ids
            # in the committed artifact contain ``/``), and ids are never resolved
            # against the filesystem by any consumer. ``source_file`` — the one
            # path-BEARING column — is the field the path-shape and served-set
            # rules are enforced on, here and in the generator's leak scan.
            if not (isinstance(row[3], str) and row[3]):
                raise ValueError("graph detail node source_file must be a non-empty string")
            for optional in (row[1], row[2], row[4], row[5]):
                if optional is not None and not isinstance(optional, str):
                    raise ValueError("graph detail node field must be a string or null")
        for row in data["edges"]:
            if not (isinstance(row, list)
                    and len(row) == len(SUPPORTED_GRAPH_DETAIL_EDGE_KEYS)):
                raise ValueError("graph detail edge row shape mismatch")
            for endpoint in (row[0], row[1]):
                if not (isinstance(endpoint, int) and not isinstance(endpoint, bool)
                        and 0 <= endpoint < node_count):
                    raise ValueError("graph detail edge endpoint must index into nodes")
            if not (isinstance(row[2], str) and row[2]):
                raise ValueError("graph detail edge relation must be a non-empty string")

        return _GraphDetailState(key=key, available=True, integrity="verified",
                                 detail_schema_version=version, data=data)

    def detail(self) -> dict:
        """``{available, reason, integrity, detail_schema_version, data}``.

        ``data`` is the parsed artifact when available, else ``None``. Never
        raises."""
        try:
            state = self._state_now()
        except Exception:  # pragma: no cover - defensive; _build never raises
            return {"available": False, "reason": "detail_unreadable",
                    "integrity": "malformed", "detail_schema_version": None,
                    "data": None}
        return {
            "available": state.available,
            "reason": state.reason,
            "integrity": state.integrity,
            "detail_schema_version": state.detail_schema_version,
            "data": state.data,
        }


# --- P24.10 memory-input fingerprint primitives -------------------------------
#
# Two provable freshness concepts, computed here as pure stdlib primitives (no
# wiring into generator/reader/route/frontend yet):
#   * a *policy fingerprint* over the exclusion/projection/algo policy, so a
#     changed governance policy is detectable; and
#   * a *served-content manifest* (repo-relative path + raw-bytes sha256) plus an
#     aggregate fingerprint over it, so a change to the actual served file bytes
#     is detectable.
# Both are deterministic and content-only; neither reads the graph or any
# governance-excluded path.


def _policy_fingerprint_payload() -> dict:
    """The canonical, sorted policy payload the policy fingerprint hashes.

    Every field materially participates in the fingerprint: the version stamps,
    plus the full exclusion policy (prefixes / exact paths / binary+secret
    extensions / secret basenames) and the rationale char cap. Sets are emitted
    as ``sorted`` lists so the payload is order-stable regardless of set-iteration
    / hash-seed order."""
    return {
        "schema_version": SUPPORTED_SNAPSHOT_SCHEMA_VERSION,
        "policy_version": MEMORY_INPUTS_POLICY_VERSION,
        "projection_version": PROJECTION_VERSION,
        "algo_version": FINGERPRINT_ALGO_VERSION,
        "excluded_prefixes": sorted(EXCLUDED_PREFIXES),
        "excluded_exact": sorted(EXCLUDED_EXACT),
        "binary_exts": sorted(BINARY_EXTS),
        "secret_exts": sorted(SECRET_EXTS),
        "secret_basenames": sorted(SECRET_BASENAMES),
        "max_rationale_chars": MAX_RATIONALE_CHARS,
    }


def compute_memory_policy_fingerprint() -> str:
    """A stable sha256 hex digest of the memory-input exclusion/version policy.

    Canonical serialization is ``json.dumps(payload, sort_keys=True,
    ensure_ascii=False, separators=(",", ":"))`` UTF-8 encoded, so the digest is
    deterministic and independent of dict-insertion / set-iteration order."""
    canonical = json.dumps(
        _policy_fingerprint_payload(),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def compute_served_content_manifest(served_paths, repo_root) -> list[dict]:
    """A deterministic ``[{"path", "sha256"}]`` manifest of served file bytes.

    ``repo_root`` is a :class:`~pathlib.Path`; ``served_paths`` is an iterable of
    repo-relative posix path strings. Every path must (a) be path-safe — not
    absolute, no ``..`` segment, no backslash / ``~`` (via
    :meth:`LocalGraphArtifactSource._is_unsafe`), (b) resolve strictly inside
    ``repo_root``, and (c) pass the served allowlist (:func:`_is_served`); any
    violation raises :class:`ValueError`. For each accepted path the raw bytes of
    ``repo_root / path`` are read and sha256-hexed; a missing/unreadable file
    raises :class:`ValueError`. Returns the entries sorted by ``path`` with posix
    separators — callers decide how to handle raised errors."""
    root = Path(repo_root).resolve()
    entries: list[dict] = []
    for path in served_paths:
        if not isinstance(path, str) or not path:
            raise ValueError(f"invalid served path: {path!r}")
        # Path-safety guard (absolute / ``..`` / backslash / ``~``), then the
        # governance served allowlist — both mirror the reader's contract so a
        # path unsafe or unserved for the reader is rejected here too.
        if LocalGraphArtifactSource._is_unsafe(path):
            raise ValueError(f"unsafe served path: {path!r}")
        if not _is_served(path):
            raise ValueError(f"path not in served allowlist: {path!r}")
        target = (root / path).resolve()
        try:
            target.relative_to(root)  # resolves outside repo_root -> reject
        except ValueError as exc:
            raise ValueError(f"served path escapes repo root: {path!r}") from exc
        try:
            raw = target.read_bytes()
        except OSError as exc:
            raise ValueError(f"served path missing/unreadable: {path!r}") from exc
        entries.append({"path": path.replace("\\", "/"), "sha256": hashlib.sha256(raw).hexdigest()})
    entries.sort(key=lambda e: e["path"])
    return entries


def compute_served_path_set_fingerprint(served_paths) -> str:
    """A stable sha256 over the served PATH SET only — never file contents.

    Deliberately content-free, and therefore a DIFFERENT concept from
    :func:`compute_served_manifest_fingerprint`: it proves that two artifacts
    describe the same set of served files, and stays stable while those files'
    contents are edited (content drift is the served-content manifest's job).
    Sorted join, so it is order-independent and deterministic."""
    return hashlib.sha256(
        "\n".join(sorted(served_paths)).encode("utf-8")
    ).hexdigest()


def compute_served_manifest_fingerprint(manifest) -> str:
    """An aggregate sha256 hex digest over a served-content manifest.

    ``manifest`` is any iterable of ``{"path", "sha256"}`` dicts (need not be
    pre-sorted — this function sorts by ``path`` itself). The digest is sha256 of
    ``"\\n".join(f"{path}\\0{sha256}")`` over the path-sorted pairs, so it is
    order-independent and changes iff any path or any sha256 changes."""
    pairs = sorted((e["path"], e["sha256"]) for e in manifest)
    joined = "\n".join(f"{path}\0{sha256}" for path, sha256 in pairs)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


# --- module-level default accessor -------------------------------------------

_REPO_ROOT = _find_repo_root()
#: The canonical snapshot shipped inside the hosted image, resolved
#: ``__file__``-relative so it is working-directory-independent (``isaac_api`` runs
#: via ``--app-dir apps/api``, not pip-installed). Present only once impl-4 commits
#: the real snapshot; absent in local dev, where the live-graph reader is used.
_PACKAGED_SNAPSHOT = Path(__file__).resolve().parent / "data" / "memory-snapshot.json"
#: The canonical deep-layer artifact shipped alongside the snapshot in the
#: hosted image (``Dockerfile``'s ``COPY apps/api/ apps/api/`` already ships
#: this directory). Resolved ``__file__``-relative, like the snapshot.
_PACKAGED_GRAPH_DETAIL = Path(__file__).resolve().parent / "data" / GRAPH_DETAIL_FILE

_default_reader: Optional[MemoryReader] = None
#: The ``(kind, path)`` choice the memoized reader was built for; rebuilt on change.
_default_choice: Optional[tuple] = None

_default_detail_source: Optional[GraphDetailSource] = None
_default_detail_path: Optional[Path] = None


def _resolve_reader_choice() -> tuple:
    """Resolve which memory provider to use, as a ``(kind, path)`` pair.

    Precedence (P24.9-impl-2 decision #2):
      1. ``ISAAC_MEMORY_SNAPSHOT`` set & non-empty -> the snapshot at that path.
      2. else the packaged canonical snapshot, if it exists.
      3. else ``ISAAC_MEMORY_DIR`` set & non-empty -> the live graph at that dir.
      4. else the repo's ``graphify-out/`` live graph.
    Honest-unavailable falls out naturally: if step 4's directory has no graph, the
    local reader reports ``graph_absent``."""
    snapshot = os.environ.get(ENV_MEMORY_SNAPSHOT, "").strip()
    if snapshot:
        return ("snapshot", Path(snapshot))
    if _PACKAGED_SNAPSHOT.is_file():
        return ("snapshot", _PACKAGED_SNAPSHOT)
    override = os.environ.get(ENV_MEMORY_DIR, "").strip()
    if override:
        return ("local", Path(override))
    return ("local", _REPO_ROOT / "graphify-out")


def get_default_reader() -> MemoryReader:
    """The process-wide default reader.

    Selects between :class:`SanitizedSnapshotSource` (hosted image / snapshot seam)
    and :class:`LocalGraphArtifactSource` (live ``graphify-out/``) via
    :func:`_resolve_reader_choice`. The reader instance is reused so its mtime cache
    persists; it is rebuilt only when the resolved ``(kind, path)`` choice changes."""
    global _default_reader, _default_choice
    choice = _resolve_reader_choice()
    if _default_reader is None or _default_choice != choice:
        kind, path = choice
        if kind == "snapshot":
            _default_reader = SanitizedSnapshotSource(path)
        else:
            _default_reader = LocalGraphArtifactSource(path, repo_root=_REPO_ROOT)
        _default_choice = choice
    return _default_reader


def _resolve_detail_path() -> Path:
    """Resolve the deep-layer artifact path: the ``ISAAC_MEMORY_GRAPH_DETAIL``
    override when set & non-empty, else the packaged canonical artifact. When
    neither exists the returned :class:`GraphDetailSource` honestly reports
    ``detail_absent`` — never a fabricated graph."""
    override = os.environ.get(ENV_MEMORY_GRAPH_DETAIL, "").strip()
    if override:
        return Path(override)
    return _PACKAGED_GRAPH_DETAIL


def get_default_detail_source() -> GraphDetailSource:
    """The process-wide default deep-layer source.

    Memoized so its mtime cache persists; rebuilt only when the resolved path
    changes (mirrors :func:`get_default_reader`)."""
    global _default_detail_source, _default_detail_path
    path = _resolve_detail_path()
    if _default_detail_source is None or _default_detail_path != path:
        _default_detail_source = GraphDetailSource(path)
        _default_detail_path = path
    return _default_detail_source

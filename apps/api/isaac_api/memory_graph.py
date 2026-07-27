"""Deterministic Project Memory "Graph" tab projection (memory plane, P36.2).

Pure, stdlib-only projection of a SERVED-FILE reference graph, built ONLY from
a ``MemoryReader``'s public surface (``overview`` / ``files`` / ``concepts`` /
``file`` / ``status`` — see ``isaac_api.memory.MemoryReader``). This module
imports NEITHER ``graphify`` nor ``isaac_records``: it is memory-plane
advisory material, never truth, and computes no verdict. No key anywhere in
its output is a member of ``{ok, valid, passed, verdict, schema, errors}``.

Ground truth (verified against the committed snapshot; do not "simplify" this
away): the committed snapshot embeds NO edge list. ``overview()``'s
``node_count`` / ``edge_count`` / ``community_count`` describe a LARGER
source graph that is not embedded (2988 / 4465 / 257 nodes/edges/communities
for the real committed snapshot). What IS embedded, per served file, is
``file_detail[path].related.files[]`` — a materialized list of
``{path, file_type, relation}`` neighbor entries whose ``relation`` carries
one of five real values (``references`` / ``imports`` / ``calls`` /
``imports_from`` / ``shares_data_with``). This module treats that per-file
related-files list as the ONLY edge source for a SMALLER, served-only
reference graph — never the un-embedded full source graph, and it never
synthesizes an edge from anywhere else (a concept's ``related`` is always
empty in the real data and never contributes an edge here).

Two caps (``MAX_NODES`` / ``MAX_EDGES``) bound the response so a client never
receives an unbounded graph in one shot, even against a future, much larger
snapshot; ``truncated`` reports whether either cap actually cut anything. Caps
are applied as a deterministic sorted-prefix (never a random sample), and
edges are re-validated against the surviving (post-cap) node set so the
response never carries a dangling edge.

Route wiring: ``GET /api/memory/graph`` in ``routes.py`` calls
``build_graph_projection(memory.get_default_reader())`` and returns the dict
verbatim (HTTP 200 always — this function never raises).

Deep (symbol-level) layer
-------------------------
``build_graph_detail`` is a SECOND, independent envelope over the committed
``memory-graph-detail.json`` artifact (see ``isaac_api.memory.GraphDetailSource``
and ``scripts/build_memory_snapshot.py --detail-out``), wired to its OWN route
``GET /api/memory/graph/detail`` so it is lazily fetched and never inflates the
base projection. The base projection's response shape above is UNCHANGED by it.
The deep layer is the symbol-level structure Graphify indexed at the artifact's
``built_at_commit`` — a point-in-time snapshot that is generally NOT the current
repository HEAD — and its provenance says so explicitly and machine-readably.

The only import here is the sibling memory-plane module ``isaac_api.memory``
(stdlib-only, Graphify-free, truth-free); this module still imports neither
``graphify`` nor ``isaac_records``.
"""

from __future__ import annotations

from . import memory

#: Deterministic sorted-prefix caps on the rendered response.
MAX_NODES = 600
MAX_EDGES = 2000

#: One shared, honest note for every response shape (available or degraded) —
#: mirrors the other memory-plane endpoints' single-note convention
#: (``routes.MEMORY_NOTE``), kept as an independent local constant so this
#: module stays import-free of ``routes``/``isaac_records``/``graphify``.
GRAPH_NOTE = (
    "Project memory returns leads to verify — never a validation verdict. "
    "This is a served-file reference graph, not the full (un-embedded) source graph."
)

#: The provenance/underlying-graph note repeated in every response's meta.
_UNDERLYING_GRAPH_NOTE = (
    "full source graph not embedded; this is the served-content reference projection"
)


def _safe_call(fn, default):
    """Call a zero-arg reader method; any exception degrades to ``default``.

    Both concrete ``MemoryReader`` implementations already guarantee their
    public methods never raise for an artifact problem, but this mirrors the
    blanket never-raise guards used elsewhere in the memory plane
    (``LocalGraphArtifactSource._build`` / ``SanitizedSnapshotSource._build``)
    so a reader with an unanticipated implementation can never turn this
    route into a 500.
    """
    try:
        return fn()
    except Exception:
        return default


def _provenance(overview: dict, status: dict) -> dict:
    """Provenance sourced from ONE reader's ``overview()`` + ``status()`` —
    never invented. ``provider`` collapses to ``"unavailable"`` when the plane
    is unavailable, mirroring ``/api/graph/status``'s convention so a degraded
    provider is never misread as a real provider identity."""
    return {
        "built_at_commit": overview.get("built_at_commit"),
        "source_graph_sha256": status.get("source_graph_sha256"),
        "snapshot_schema_version": status.get("snapshot_schema_version"),
        "provider": status.get("provider_kind") if status.get("available") else "unavailable",
        "integrity": status.get("integrity"),
    }


def _degraded(reason, overview: dict, status: dict) -> dict:
    """The honest ``available:false`` envelope — zero fabricated nodes/edges,
    HTTP 200 (the route never raises this as a 5xx)."""
    return {
        "plane": "memory",
        "note": GRAPH_NOTE,
        "available": False,
        "reason": reason,
        "truncated": False,
        "nodes": [],
        "edges": [],
        "communities": [],
        "meta": {
            "counts": {
                "files": 0,
                "concepts": 0,
                "reference_edges": 0,
                "files_with_references": 0,
                "isolated_files": 0,
                "communities_rendered": 0,
            },
            "underlying_graph": {
                "embedded": False,
                "node_count": None,
                "edge_count": None,
                "community_count": None,
                "note": _UNDERLYING_GRAPH_NOTE,
            },
            "provenance": _provenance(overview, status),
        },
    }


def _file_node(f: dict) -> dict:
    return {
        "id": f.get("path"),
        "kind": "file",
        "label": f.get("path"),
        "file_type": f.get("file_type"),
        "community_id": f.get("community_id"),
        "community_name": f.get("community_name"),
        "node_count": f.get("node_count"),
        "on_disk": f.get("on_disk"),
    }


def _concept_node(c: dict) -> dict:
    return {
        "id": c.get("id"),
        "kind": "concept",
        "label": c.get("label"),
        "community_id": c.get("community_id"),
        "community_name": c.get("community_name"),
        "on_disk": c.get("on_disk"),
        "source_file": c.get("source_file"),
    }


def _build_edges(reader, file_summaries: list, node_ids: set) -> list:
    """Undirected, deduplicated edges from EVERY file's own
    ``related.files[]`` only (never a concept's ``related`` — see module
    docstring). A pair is kept only when both ends are known node ids
    (defense-in-depth: the reader already governance-filters related paths,
    this simply never trusts a dangling/unknown id into an edge). Every real
    ``relation`` string seen for a pair (from either direction) is
    accumulated into a sorted-unique list — the real values are preserved
    verbatim, never collapsed to a single label."""
    edge_relations: dict = {}
    for f in file_summaries:
        path = f.get("path")
        if not path:
            continue
        detail = reader.file(path)
        if not isinstance(detail, dict):
            continue
        related = detail.get("related")
        rel_files = related.get("files") if isinstance(related, dict) else None
        for rel_file in rel_files or []:
            if not isinstance(rel_file, dict):
                continue
            other = rel_file.get("path")
            if not other or other == path:
                continue
            if path not in node_ids or other not in node_ids:
                continue
            pair = (path, other) if path < other else (other, path)
            relset = edge_relations.setdefault(pair, set())
            relation = rel_file.get("relation")
            if relation:
                relset.add(relation)

    edges = [
        {"source": a, "target": b, "relations": sorted(relset)}
        for (a, b), relset in edge_relations.items()
    ]
    edges.sort(key=lambda e: (e["source"], e["target"]))
    return edges


def _build_available(overview: dict, status: dict, reader) -> dict:
    file_summaries = reader.files() or []
    concept_summaries = reader.concepts() or []

    file_nodes = [_file_node(f) for f in file_summaries if f.get("path")]
    concept_nodes = [_concept_node(c) for c in concept_summaries if c.get("id")]
    all_nodes = sorted(file_nodes + concept_nodes, key=lambda n: n["id"])
    all_node_ids = {n["id"] for n in all_nodes}

    all_edges = _build_edges(reader, file_summaries, all_node_ids)

    # -- caps: deterministic sorted-prefix. Nodes are capped first; edges are
    # then re-validated against the SURVIVING (post-cap) node set — never a
    # dangling edge in the final response — before the edge cap is applied.
    nodes_truncated = len(all_nodes) > MAX_NODES
    rendered_nodes = all_nodes[:MAX_NODES]
    rendered_node_ids = {n["id"] for n in rendered_nodes}

    surviving_edges = [
        e for e in all_edges
        if e["source"] in rendered_node_ids and e["target"] in rendered_node_ids
    ]
    edges_truncated = len(surviving_edges) > MAX_EDGES
    rendered_edges = surviving_edges[:MAX_EDGES]

    truncated = nodes_truncated or edges_truncated

    # -- communities: distinct among rendered FILE nodes only (concepts carry
    # their own community_id/community_name on the node itself and never
    # contribute a community row here).
    rendered_file_nodes = [n for n in rendered_nodes if n["kind"] == "file"]
    rendered_concept_nodes = [n for n in rendered_nodes if n["kind"] == "concept"]
    community_acc: dict = {}
    for n in rendered_file_nodes:
        cid = n["community_id"]
        if cid is None:
            continue
        entry = community_acc.setdefault(
            cid, {"id": cid, "name": n["community_name"], "file_count": 0}
        )
        entry["file_count"] += 1
    communities = sorted(community_acc.values(), key=lambda c: c["id"])

    referenced_ids: set = set()
    for e in rendered_edges:
        referenced_ids.add(e["source"])
        referenced_ids.add(e["target"])
    files_with_references = sum(1 for n in rendered_file_nodes if n["id"] in referenced_ids)
    isolated_files = len(rendered_file_nodes) - files_with_references

    return {
        "plane": "memory",
        "note": GRAPH_NOTE,
        "available": True,
        "truncated": truncated,
        "nodes": rendered_nodes,
        "edges": rendered_edges,
        "communities": communities,
        "meta": {
            "counts": {
                "files": len(rendered_file_nodes),
                "concepts": len(rendered_concept_nodes),
                "reference_edges": len(rendered_edges),
                "files_with_references": files_with_references,
                "isolated_files": isolated_files,
                "communities_rendered": len(communities),
            },
            "underlying_graph": {
                "embedded": False,
                "node_count": overview.get("node_count"),
                "edge_count": overview.get("edge_count"),
                "community_count": overview.get("community_count"),
                "note": _UNDERLYING_GRAPH_NOTE,
            },
            "provenance": _provenance(overview, status),
        },
    }


# --- deep (symbol-level) detail layer -----------------------------------------
#
# Served by its OWN endpoint (``GET /api/memory/graph/detail``), lazily fetched,
# and NEVER folded into ``build_graph_projection``'s response — the base
# 220-node served-file projection above is untouched and stays byte-compatible
# in shape.

#: Deterministic sorted-prefix caps on the deep response. Node capping is a
#: PREFIX, so the surviving 0-based edge endpoint indices stay valid; edges
#: pointing past the cap are dropped before the edge cap is applied.
DETAIL_MAX_NODES = 20000
DETAIL_MAX_EDGES = 60000

DETAIL_NOTE = (
    "Project memory returns leads to verify — never a validation verdict. "
    "This is the symbol-level structure of the source graph as indexed at "
    "built_at_commit; it is a point-in-time snapshot, not a map of the current "
    "repository HEAD."
)

#: Machine-readable staleness contract, repeated in every response's provenance.
_DETAIL_PROVENANCE_NOTE = (
    "structure describes built_at_commit (point-in-time Graphify index), while "
    "the served-file content manifest is CI-current; the two are separate axes"
)


def _detail_provenance(data: dict, reader_status: dict, served_consistency: str) -> dict:
    """Provenance sourced ONLY from the artifact plus the reader's own
    ``status()`` — never invented, never defaulted to a flattering value."""
    return {
        "built_at_commit": data.get("built_at_commit"),
        "source_graph_sha256": data.get("source_graph_sha256"),
        "detail_schema_version": data.get("detail_schema_version"),
        "generator": data.get("generator"),
        "policy_fingerprint": data.get("policy_fingerprint"),
        # The two honesty flags a consumer can branch on without parsing prose.
        "is_point_in_time": True,
        "describes_current_head": False,
        "structural_scope": data.get("structural_scope"),
        "structural_basis": data.get("structural_basis"),
        # The served-file CONTENT manifest is a separate, CI-verified axis; the
        # deep layer only pins the served PATH SET.
        "served_content_scope": "served_files_only",
        "served_content_basis": "ci_content_manifest",
        # ``served_file_count`` counts the served PATH SET (every repo-relative
        # path the memory plane may describe). It is deliberately NOT the size of
        # the CI *content* manifest that the two ``served_content_*`` keys above
        # name: the manifest excludes one served path that is not content-hashed
        # (a committed fixture snapshot), so the manifest is one SMALLER than
        # this number. ``served_file_count_scope`` makes that explicit so a
        # consumer reading this block as a unit cannot infer an off-by-one story.
        "served_file_count": data.get("served_file_count"),
        "served_file_count_scope": "served_path_set",
        "served_path_set_fingerprint": data.get("served_path_set_fingerprint"),
        "served_set_consistency": served_consistency,
        "snapshot_provider": reader_status.get("provider_kind"),
        "snapshot_built_at_commit": reader_status.get("source_graph_commit"),
        "note": _DETAIL_PROVENANCE_NOTE,
    }


def _rendered_counts(nodes: list, edges: list) -> dict:
    """Counts recomputed from the rows this response ACTUALLY carries.

    The artifact's own ``counts`` block is never echoed — truncated or not. A
    response must describe what it contains: an artifact claiming
    ``{"nodes": 999999999}`` while shipping 2,612 rows would still be reported
    as 2,612 here. ``memory.GraphDetailSource._derive`` validates every row and
    every edge endpoint but does NOT cross-check ``counts`` against
    ``len(nodes)``/``len(edges)``, so echoing that block would let a hand-edited
    or stale artifact overstate the graph while still being served as
    ``integrity: "verified"``. Recomputation removes the possibility instead of
    relying on the artifact being self-consistent.

    Two independent layers cover the same defect from the other side: the
    generator's ``_validate_detail_shape`` refuses to WRITE a counts/length
    mismatch, and that validator is re-run against the REAL committed artifact
    in CI (``test_committed_artifact_passes_the_generators_own_gates``).

    ``communities`` is the number of DISTINCT community ids carried by the
    rendered nodes rather than ``len(community_names)``: the response ships the
    artifact's full name map verbatim, which for a truncated response can name
    clusters no rendered node belongs to.
    """
    rendered_communities = {row[5] for row in nodes if row[5] is not None}
    file_types: dict = {}
    for row in nodes:
        key = row[2] if row[2] is not None else "unknown"
        file_types[key] = file_types.get(key, 0) + 1
    relations: dict = {}
    for edge in edges:
        relations[edge[2]] = relations.get(edge[2], 0) + 1
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "communities": len(rendered_communities),
        "file_types": dict(sorted(file_types.items())),
        "relations": dict(sorted(relations.items())),
    }


def _detail_degraded(reason: str, integrity, reader_status: dict) -> dict:
    """The honest ``available:false`` envelope — zero fabricated nodes/edges,
    HTTP 200. Provenance collapses to nulls rather than plausible defaults."""
    return {
        "plane": "memory",
        "note": DETAIL_NOTE,
        "available": False,
        "reason": reason,
        "integrity": integrity,
        "truncated": False,
        "node_keys": [],
        "edge_keys": [],
        "nodes": [],
        "edges": [],
        "community_names": {},
        "encoding": {},
        "meta": {
            "counts": {"nodes": 0, "edges": 0, "communities": 0,
                       "file_types": {}, "relations": {}},
            "provenance": {
                "built_at_commit": None,
                "source_graph_sha256": None,
                "detail_schema_version": None,
                "generator": None,
                "policy_fingerprint": None,
                "is_point_in_time": True,
                "describes_current_head": False,
                "structural_scope": None,
                "structural_basis": None,
                "served_content_scope": "served_files_only",
                "served_content_basis": "ci_content_manifest",
                "served_file_count": None,
                "served_file_count_scope": "served_path_set",
                "served_path_set_fingerprint": None,
                "served_set_consistency": "unknown",
                "snapshot_provider": reader_status.get("provider_kind"),
                "snapshot_built_at_commit": reader_status.get("source_graph_commit"),
                "note": _DETAIL_PROVENANCE_NOTE,
            },
        },
    }


def _served_set_consistency(data: dict, reader) -> str:
    """``"current"`` / ``"stale"`` / ``"unknown"``: whether the deep layer and
    the memory reader describe the SAME served path set.

    Provable at runtime with no extra data: the reader's own ``files()`` is the
    served path set, so the artifact's embedded path-set fingerprint can be
    recomputed and compared. This is a PATH-SET check only — served-file
    *content* drift is CI's authority and is never inferred here."""
    embedded = data.get("served_path_set_fingerprint")
    if not isinstance(embedded, str) or not embedded:
        return "unknown"
    try:
        paths = [f.get("path") for f in (reader.files() or [])]
    except Exception:
        return "unknown"
    paths = [p for p in paths if isinstance(p, str) and p]
    if not paths:
        return "unknown"
    try:
        recomputed = memory.compute_served_path_set_fingerprint(paths)
    except Exception:
        return "unknown"
    return "current" if recomputed == embedded else "stale"


def build_graph_detail(detail_source, reader) -> dict:
    """The deep (symbol-level) layer's response envelope.

    Reads the committed artifact through ``detail_source`` (a
    ``memory.GraphDetailSource``) and passes its nodes/edges/relations through
    VERBATIM — no node, edge, hierarchy, label or relation value is derived,
    renamed or invented here. Direction is whatever the artifact recorded.

    The one thing that is NOT taken from the artifact is ``meta.counts``: it is
    always recomputed from the rows actually rendered, so the response cannot
    state a count its own payload does not support (see ``_rendered_counts``).

    Never raises: an absent/unreadable/unsupported artifact, an unavailable
    memory reader, or any unanticipated failure degrades to the same honest
    ``available:false`` envelope, so the route always answers HTTP 200."""
    try:
        reader_status = _safe_call(reader.status, {})
        if not isinstance(reader_status, dict):
            reader_status = {}
    except Exception:
        reader_status = {}

    try:
        loaded = detail_source.detail()
    except Exception:
        loaded = None
    if not isinstance(loaded, dict) or not loaded.get("available"):
        reason = (loaded.get("reason") if isinstance(loaded, dict) else None) \
            or "detail_unreadable"
        integrity = loaded.get("integrity") if isinstance(loaded, dict) else "unknown"
        return _detail_degraded(reason, integrity, reader_status)

    try:
        return _build_detail_available(loaded, reader, reader_status)
    except Exception:
        # The artifact loaded but the envelope could not be derived coherently —
        # degrade honestly rather than let an exception become a 500.
        return _detail_degraded("detail_unreadable",
                                loaded.get("integrity"), reader_status)


def _build_detail_available(loaded: dict, reader, reader_status: dict) -> dict:
    data = loaded.get("data")
    if not isinstance(data, dict):
        raise ValueError("graph detail payload missing")

    all_nodes = data.get("nodes")
    all_edges = data.get("edges")
    # Defense in depth: ``memory.GraphDetailSource`` already refuses an artifact
    # whose ``nodes``/``edges`` are not lists of well-shaped rows, so this cannot
    # trip for a source-loaded payload. It exists so a non-list payload from any
    # other caller degrades honestly instead of being echoed back as a "graph".
    if not isinstance(all_nodes, list) or not isinstance(all_edges, list):
        raise ValueError("graph detail nodes/edges must be lists")

    # Slicing/copying below is also the M5 cache-aliasing defence: the outer
    # ``nodes``/``edges``/``community_names``/``encoding`` containers handed to the
    # caller are NEVER the cached artifact's own containers, so a future in-place
    # ``body["nodes"].sort()`` / ``.clear()`` / ``.append()`` cannot corrupt the
    # process-wide cache. The ROWS themselves are still shared (a per-request deep
    # copy of ~6.7k rows would be pure waste); that residual aliasing stays a
    # documented read-only contract — see ``memory.GraphDetailSource`` — and is
    # asserted by ``test_response_containers_do_not_alias_the_cached_artifact``.
    nodes_truncated = len(all_nodes) > DETAIL_MAX_NODES
    nodes = all_nodes[:DETAIL_MAX_NODES] if nodes_truncated else list(all_nodes)
    if nodes_truncated:
        limit = len(nodes)
        surviving = [e for e in all_edges if e[0] < limit and e[1] < limit]
    else:
        surviving = list(all_edges)
    edges_truncated = len(surviving) > DETAIL_MAX_EDGES
    edges = surviving[:DETAIL_MAX_EDGES] if edges_truncated else surviving
    truncated = nodes_truncated or edges_truncated

    # ALWAYS recomputed from the rendered rows — the artifact's ``counts`` block
    # is never echoed in either branch. See ``_rendered_counts``.
    rendered_counts = _rendered_counts(nodes, edges)

    provenance = _detail_provenance(
        data, reader_status, _served_set_consistency(data, reader)
    )
    provenance["detail_schema_version"] = loaded.get("detail_schema_version")

    return {
        "plane": "memory",
        "note": DETAIL_NOTE,
        "available": True,
        "reason": None,
        "integrity": loaded.get("integrity"),
        "truncated": truncated,
        "node_keys": list(data.get("node_keys") or []),
        "edge_keys": list(data.get("edge_keys") or []),
        "nodes": nodes,
        "edges": edges,
        "community_names": dict(data.get("community_names") or {}),
        "encoding": dict(data.get("encoding") or {}),
        "meta": {
            "counts": rendered_counts,
            "provenance": provenance,
        },
    }


def build_graph_projection(reader) -> dict:
    """The Graph tab's deterministic, honest, capped served-file reference
    projection over ``reader`` (a ``MemoryReader``). Never raises: an absent
    artifact, an unreadable/malformed/unsupported artifact, or any
    unanticipated failure while deriving the projection all degrade to the
    same honest ``available:false`` envelope the other ``/api/memory/*``
    routes use — the caller always gets HTTP 200, never a 500."""
    overview = _safe_call(reader.overview, {})
    if not isinstance(overview, dict) or not overview.get("available"):
        reason = (overview.get("reason") if isinstance(overview, dict) else None) or "graph_unreadable"
        status = _safe_call(reader.status, {})
        if not isinstance(status, dict):
            status = {}
        return _degraded(reason, overview if isinstance(overview, dict) else {}, status)

    status = _safe_call(reader.status, {})
    if not isinstance(status, dict):
        status = {}
    try:
        return _build_available(overview, status, reader)
    except Exception:
        # The reader reported available:True but the projection could not be
        # derived coherently (an unanticipated reader implementation) —
        # degrade honestly rather than let an exception become a 500.
        return _degraded("graph_unreadable", overview, status)

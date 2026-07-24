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
"""

from __future__ import annotations

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

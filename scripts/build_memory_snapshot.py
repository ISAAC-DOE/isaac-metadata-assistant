#!/usr/bin/env python3
"""Deterministic sanitized Project Memory snapshot generator (memory plane).

Peer to ``scripts/check_graphify_freshness.py``. Reads live Graphify artifacts
(``graph.json`` / ``manifest.json`` / ``.graphify_labels.json``) via the
existing, Graphify-free reader ``apps/api/isaac_api/memory.py`` and serializes
its *returned* metadata into a single sanitized, deterministic JSON file
(``memory-snapshot.json``) suitable for shipping in the hosted image without
the raw graph, without file contents, and without governance-excluded paths.

See ``docs/superpowers/specs/2026-07-17-phase-24-9-hosted-project-memory-enablement.md``
§3/§6/§7/§8/§9 for the full design.

Design contract
----------------
* **Reuses, never re-derives.** Constructs
  ``isaac_api.memory.LocalGraphArtifactSource`` and drives its six public
  methods (``overview/concepts/concept/files/file/classify_path``). All
  sorting, related-edge weighting, and concept/related path filtering
  (P24.9-impl-0) come from the reader unchanged.
* **Truth-plane isolation.** Imports only the standard library plus
  ``isaac_api.memory`` (added to ``sys.path`` at runtime, never installed).
  Never imports ``isaac_records`` or ``graphify``.
* **Deterministic.** Same input graph bytes -> byte-identical output: no
  wall-clock, no machine-varying value. ``graph_mtime`` is baked to JSON
  ``null`` (a sanitized snapshot has no live file in the hosted deployment;
  a fake epoch/mtime would render a dishonest 1970-style age) — never a
  filesystem timestamp, never ``0.0``.
* **Fail-closed secret/governance scan.** Every path-bearing value must pass
  both ``memory._is_served`` and NOT
  ``LocalGraphArtifactSource._is_unsafe`` (belt-and-suspenders over the
  P24.9-impl-0 reader-level filtering). No absolute/home/Windows-drive path
  or private-key/credential-shaped token may appear in ANY string value. Any
  hit aborts with a non-zero exit and writes nothing.
* ``on_disk`` is forced ``false`` on every emitted summary/detail: the hosted
  image ships no source files, so a real existence check would be dishonest
  (and nondeterministic across machines).

CLI
---
::

    python scripts/build_memory_snapshot.py \\
        --graph-dir graphify-out \\
        --out memory-snapshot.json \\
        [--repo-root .] \\
        [--check]

``--check`` regenerates the snapshot in-memory from ``--graph-dir``, runs
shape validation and the secret scan, and compares the result byte-for-byte
to the existing ``--out`` file. It writes nothing and exits non-zero if the
committed file is stale, malformed, or absent.

Deep (symbol-level) graph detail layer
--------------------------------------
``--detail-out PATH`` additionally emits the **deep structural layer**: the
symbol-level node/edge graph Graphify indexed, restricted to nodes whose
``source_file`` is in the SAME served allowlist the snapshot ships. It is a
SEPARATE, opt-in artifact (``memory-graph-detail.json``) — never folded into
``memory-snapshot.json``, whose shape and ``snapshot_schema_version`` are
deliberately left untouched (see :data:`DETAIL_SCHEMA_VERSION` for why).

The deep layer is subject to the SAME fail-closed governance scan as the
snapshot: every node ``source_file`` must be path-safe (``_is_unsafe``),
governance-served (``memory._is_served``) AND a member of the snapshot's
served set; rationale labels are truncated at
:data:`MAX_RATIONALE_CHARS`; no value may carry a machine/home/absolute path
or a credential-shaped token. Any hit aborts and writes NOTHING — neither
artifact.

It is honest about staleness: the structural graph describes the commit
Graphify indexed (``built_at_commit``), which is generally NOT the current
repository HEAD, while the served-file *content* manifest embedded in the
snapshot is CI-current. The artifact carries
``structural_scope: "point_in_time_source_graph"`` and a
``served_path_set_fingerprint`` so a runtime can prove whether the deep layer
and the snapshot describe the same served path set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# --- sys.path wiring: reach apps/api/isaac_api without installing it ---------

_REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
_API_PATH = _REPO_ROOT_FOR_IMPORT / "apps" / "api"
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))

from isaac_api import memory  # noqa: E402
from isaac_api.memory import LocalGraphArtifactSource  # noqa: E402

# --- constants ----------------------------------------------------------------

SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_KIND = "isaac-memory-snapshot"

#: The deep (symbol-level) structural layer's OWN schema version and kind.
#:
#: WHY a separate version rather than bumping ``SNAPSHOT_SCHEMA_VERSION`` to 2:
#: ``memory-snapshot.json``'s shape does not change at all here (the deep layer
#: is a sibling artifact, lazily loaded by its own endpoint), so bumping its
#: version would be a false shape signal. It would also be actively harmful:
#: ``memory.SUPPORTED_SNAPSHOT_SCHEMA_VERSION`` is a hashed input of
#: ``memory.compute_memory_policy_fingerprint()``, so changing it silently
#: invalidates the ``policy_fingerprint`` embedded in every already-committed
#: snapshot and in ``tests/fixtures/memory_snapshot/memory-snapshot.json``,
#: flipping their honest ``policy_consistency: "current"`` to ``"stale"``.
#: Versioning the new artifact independently keeps both the snapshot contract
#: and the governance-policy fingerprint stable.
DETAIL_SCHEMA_VERSION = 1
DETAIL_KIND = "isaac-memory-graph-detail"

#: Positional row schemas for the deep layer's two bulk arrays. Declared IN the
#: artifact (``node_keys`` / ``edge_keys``) so the compact encoding stays
#: self-describing. Positional rows + node-index edge endpoints keep the
#: committed artifact roughly a third of the size of the equivalent
#: object-per-row form without losing any information.
DETAIL_NODE_KEYS = ("id", "label", "file_type", "source_file", "source_location",
                    "community_id")
DETAIL_EDGE_KEYS = ("source_index", "target_index", "relation")

#: Human/machine-readable description of the compact encoding, embedded in the
#: artifact so no consumer has to infer it.
DETAIL_ENCODING = {
    "nodes": (
        "Positional rows matching node_keys. Every source_file is repo-relative "
        "and a member of the snapshot's served allowlist."
    ),
    "edges": (
        "Positional rows matching edge_keys. source_index/target_index are "
        "0-based indices into nodes[]. Direction is preserved exactly as the "
        "source graph recorded it; relation is the source graph's own value, "
        "never normalized or invented."
    ),
    "community_names": "Mapping of community_id -> curated community name.",
}

#: Honest provenance stamps for the deep layer (mirrors the snapshot's
#: ``freshness_scope`` / ``freshness_basis`` convention).
DETAIL_STRUCTURAL_SCOPE = "point_in_time_source_graph"
DETAIL_STRUCTURAL_BASIS = "graphify_index_at_built_at_commit"
#: Deliberately hardcoded (never derived from __file__), so the emitted value
#: is always a stable repo-relative identifier, never an absolute local path.
GENERATOR_PATH = "scripts/build_memory_snapshot.py"

#: Per-rationale character cap (approval decision #10). Committing this text
#: is permanent in git history (Option A); keeping each string short bounds
#: both the review burden and the permanence footprint. Truncation is a hard
#: cut at ``MAX_RATIONALE_CHARS - 1`` characters plus a single trailing
#: ellipsis character, so the result is always exactly ``MAX_RATIONALE_CHARS``
#: long when truncated, and is a pure, deterministic function of the input
#: string (never split differently between runs).
#:
#: Single source of truth (P24.10 Slice 2): NOT re-declared as a literal here.
#: ``isaac_api.memory.MAX_RATIONALE_CHARS`` is also hashed into
#: ``compute_memory_policy_fingerprint()``'s payload, so a build-time-only
#: constant would let the runtime reader's policy fingerprint and this
#: generator's truncation silently drift apart.
MAX_RATIONALE_CHARS = memory.MAX_RATIONALE_CHARS

_REQUIRED_TOP_LEVEL_KEYS = frozenset({
    "snapshot_schema_version", "kind", "generator",
    "built_at_commit", "source_graph_sha256",
    "overview", "concepts", "concept_detail",
    "files", "file_detail", "served",
})
#: Present in every snapshot THIS generator emits, but optional for shape
#: validation (P24.10 Slice 2): additive, no ``SNAPSHOT_SCHEMA_VERSION`` bump,
#: so an already-committed pre-P24.10 snapshot (missing ``memory_inputs``
#: entirely) still validates cleanly via ``test_committed_snapshot.py`` until
#: a later release slice regenerates it.
_OPTIONAL_TOP_LEVEL_KEYS = frozenset({"memory_inputs"})
_TOP_LEVEL_KEYS = _REQUIRED_TOP_LEVEL_KEYS | _OPTIONAL_TOP_LEVEL_KEYS
_OVERVIEW_KEYS = frozenset({
    "built_at_commit", "graph_mtime", "node_count", "edge_count",
    "community_count", "concept_count", "served_file_count",
    "manifest_file_count",
})
_MEMORY_INPUTS_KEYS = frozenset({
    "policy_fingerprint", "policy_version", "projection_version",
    "fingerprint_algo_version", "served_manifest_fingerprint",
    "served_content_manifest", "served_file_count",
    "freshness_scope", "freshness_basis",
})

_FORBIDDEN_KEYS = frozenset(
    {"content", "lines", "ok", "valid", "passed", "verdict", "schema", "errors"}
)

# Machine-leak markers scanned across ALL string values (not just path fields).
# These are MACHINE / SECRET markers, NOT path-shape rules: bare ``startswith('/')``
# / ``~`` / anchored-drive path-shape checks are applied ONLY to path-bearing
# fields (via ``_is_unsafe`` + ``_is_served`` in ``_scan_for_leaks`` step 1), so a
# legitimate slash-command CONCEPT LABEL like ``/isaac-export`` is not flagged.
_WINDOWS_MACHINE_RE = re.compile(r"[A-Za-z]:\\|\\Users\\|\\home\\")  # unanchored, mid-string
#: UNC network share (``\\fileserver\share\...``) — a machine/network location,
#: not covered by the drive-letter/``\Users\`` patterns above.
_UNC_SHARE_RE = re.compile(r"\\\\[A-Za-z0-9._-]+\\")
#: Home shorthand ANYWHERE in a value: ``~/x`` and ``~someuser/x``. Note this is
#: a MACHINE-MARKER rule, not the path-shape rule: a bare leading ``/`` is still
#: allowed in non-path fields (see the slash-command exemption note above), but
#: ``~/`` never is — there is no legitimate label that names a home directory.
_HOME_SHORTHAND_RE = re.compile(r"~/|~[A-Za-z0-9._-]+/")
#: Machine mount points / OS scratch roots. ``/Volumes/`` (macOS external and
#: network volumes — e.g. a mounted beamtime disk), ``/var/folders/`` and
#: ``/private/tmp|var`` (macOS per-user temp), plus the common Linux mount and
#: vendor roots. All require the trailing slash, so ``src/optional/x`` (which
#: contains ``/opt``) is not a hit.
_MACHINE_MOUNT_RE = re.compile(
    r"/(?:Volumes|mnt|media|opt|srv)/|/var/folders/|/private/(?:tmp|var)/"
)
#: ``file://`` URLs — a local filesystem location wearing a URL. The runtime-side
#: response scan has always rejected these; the generator scan never did, which
#: the cross-check test caught.
_FILE_URL_RE = re.compile(r"(?i)file://")
#: Email addresses — personal/organisational identifiers that must never reach a
#: published label. Requires a local part, so a Python decorator such as
#: ``@pytest.mark.parametrize`` is not a hit.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]{2,})+")
#: Internal / organisational hostnames. Permissive on the left so a multi-label
#: host (``foo.bar.internal``) is caught too.
_INTERNAL_HOST_RE = re.compile(
    r"(?i)[A-Za-z0-9-]+\.(?:slac|stanford|internal|corp|lan)(?![A-Za-z0-9-])"
)
#: mDNS ``*.local`` hostnames, guarded on BOTH sides against ``[A-Za-z0-9._-]``
#: so the codebase's own governance vocabulary is not a false positive:
#: ``.claude/settings.local.json``, ``.env.local`` and
#: ``file_detail.local_reference`` are all dotted/underscored chains and do not
#: match, while a real ``mymac.local`` does.
_MDNS_HOST_RE = re.compile(r"(?i)(?<![A-Za-z0-9._-])[A-Za-z0-9-]+\.local(?![A-Za-z0-9._-])")
#: IPv4 dotted quads. See ``_IPV4_EXEMPT_RE`` for the two disclosed exemptions.
_IPV4_RE = re.compile(r"(?<![0-9A-Za-z.-])(?:\d{1,3}\.){3}\d{1,3}(?![0-9A-Za-z.-])")
#: DISCLOSED EXEMPTION 1 (IP): loopback and the bind-any wildcard. These are
#: documented, non-identifying literals that already appear throughout the served
#: docs and dev instructions (``--host 127.0.0.1``, ``--host 0.0.0.0``); flagging
#: them would block a legitimate regeneration without withholding anything. Any
#: other address — private (``10.x`` / ``192.168.x`` / ``172.16-31.x``) or public
#: — is still refused.
_IPV4_EXEMPT_RE = re.compile(r"\A(?:0\.0\.0\.0|127\.\d{1,3}\.\d{1,3}\.\d{1,3})\Z")
#: DISCLOSED EXEMPTION 2 (hostname): the project's OWN deployment host, which is
#: already published in committed served documentation (``docs/deployment.md``).
#: It is removed from the value before the hostname patterns run, so a genuinely
#: internal neighbour such as ``s3df.slac.stanford.edu`` still fires.
_PUBLIC_HOST_EXEMPTIONS = ("isaac.slac.stanford.edu",)
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----")
_CREDENTIAL_RE = re.compile(
    r"AKIA[0-9A-Z]{16}"       # AWS access key id
    r"|sk-[A-Za-z0-9]{16,}"   # generic secret-key-shaped token
    r"|ghp_[A-Za-z0-9]{20,}"  # GitHub personal access token
    r"|xox[bp]-[A-Za-z0-9-]+"  # Slack bot/user token
)
_HOME_MARKERS = ("/Users/", "/home/", "/root/")

# --- exit codes -----------------------------------------------------------

EXIT_OK = 0
EXIT_SOURCE_UNAVAILABLE = 3
EXIT_SHAPE_INVALID = 4
EXIT_SECURITY_SCAN_FAILED = 5
EXIT_CHECK_DRIFT = 6

_DETAIL_REQUIRED_KEYS = frozenset({
    "kind", "detail_schema_version", "generator",
    "built_at_commit", "source_graph_sha256", "policy_fingerprint",
    "structural_scope", "structural_basis",
    "served_file_count", "served_path_set_fingerprint",
    "encoding", "node_keys", "edge_keys",
    "nodes", "edges", "community_names", "counts",
})
_DETAIL_COUNTS_KEYS = frozenset({
    "nodes", "edges", "communities", "file_types", "relations",
})


class SnapshotError(RuntimeError):
    """Raised for any condition that must abort snapshot generation (a
    missing/unreadable source graph, or an internal consistency failure).
    Never write output when this is raised."""


# --- field projection (explicit allowlist of the reader's returned fields) --


def _sanitize_concept_detail(detail: dict) -> dict:
    related = detail.get("related") or {}
    return {
        "id": detail.get("id"),
        "label": detail.get("label"),
        "community_id": detail.get("community_id"),
        "community_name": detail.get("community_name"),
        "source_file": detail.get("source_file"),
        "on_disk": False,  # baked false unconditionally; see module docstring
        "related": {
            "files": [dict(f) for f in related.get("files", [])],
            "concepts": [dict(c) for c in related.get("concepts", [])],
        },
    }


def _sanitize_file_detail(detail: dict) -> dict:
    related = detail.get("related") or {}
    rationales = [_truncate_rationale(r) for r in detail.get("rationales", [])]
    return {
        "path": detail.get("path"),
        "file_type": detail.get("file_type"),
        "community_id": detail.get("community_id"),
        "community_name": detail.get("community_name"),
        "node_count": detail.get("node_count"),
        "on_disk": False,  # baked false unconditionally; see module docstring
        "local_reference": detail.get("local_reference"),
        "related": {
            "files": [dict(f) for f in related.get("files", [])],
            "concepts": [dict(c) for c in related.get("concepts", [])],
        },
        "rationales": rationales,
    }


def _truncate_rationale(text: Optional[str]) -> Optional[str]:
    """Deterministically cap a rationale string at ``MAX_RATIONALE_CHARS``.

    A hard cut at ``MAX_RATIONALE_CHARS - 1`` characters plus a single
    trailing ``"…"`` when (and only when) the original exceeds the cap;
    otherwise returned unchanged. Pure function of ``text`` and the constant,
    so it never truncates differently between runs."""
    if text is None:
        return text
    if len(text) <= MAX_RATIONALE_CHARS:
        return text
    return text[: MAX_RATIONALE_CHARS - 1] + "…"


def _project_concept(detail: dict) -> dict:
    """The ``concepts[]`` summary shape: the detail minus ``related``."""
    d = dict(detail)
    d.pop("related", None)
    return d


def _project_file(detail: dict) -> dict:
    """The ``files[]`` summary shape: the detail minus related/rationales/local_reference."""
    d = dict(detail)
    d.pop("related", None)
    d.pop("rationales", None)
    d.pop("local_reference", None)
    return d


def _check_projection_consistency(
    concepts_list: list, concept_detail_map: dict,
    files_list: list, file_detail_map: dict,
) -> None:
    """Self-check (§9.5): ``concepts``/``files`` arrays must equal the
    detail-map projections. Raises :class:`SnapshotError` on any mismatch —
    a defensive re-assertion independent of how the arrays were built."""
    if len(concepts_list) != len(concept_detail_map):
        raise SnapshotError(
            f"concepts/concept_detail count mismatch: "
            f"{len(concepts_list)} != {len(concept_detail_map)}"
        )
    for c in concepts_list:
        cid = c.get("id")
        if cid not in concept_detail_map:
            raise SnapshotError(f"concept id in concepts[] missing from concept_detail: {cid!r}")
        expected = _project_concept(concept_detail_map[cid])
        if c != expected:
            raise SnapshotError(f"concept projection mismatch for id={cid!r}")

    if len(files_list) != len(file_detail_map):
        raise SnapshotError(
            f"files/file_detail count mismatch: {len(files_list)} != {len(file_detail_map)}"
        )
    for f in files_list:
        path = f.get("path")
        if path not in file_detail_map:
            raise SnapshotError(f"path in files[] missing from file_detail: {path!r}")
        expected = _project_file(file_detail_map[path])
        if f != expected:
            raise SnapshotError(f"file projection mismatch for path={path!r}")


# --- served-content manifest (P24.10 Slice 2: memory_inputs) ----------------


def _manifest_paths(served: list, *, repo_root, out_path) -> list:
    """The served paths eligible for the ``memory_inputs`` served-content
    manifest: ``served`` minus two circular self-references.

    (a) The snapshot's OWN ``--out`` target, resolved relative to
    ``repo_root``, when the resolution succeeds (``out_path`` may legitimately
    live outside ``repo_root``, e.g. a tmp directory in tests — that is not an
    error, it just means nothing is excluded via this rule). Embedding the
    snapshot's own digest in itself is circular by construction.
    (b) Any served path that IS a ``*memory-snapshot.json`` artifact
    regardless of ``out_path`` — e.g. a stray prior snapshot the graph indexed
    from an earlier build — for the same reason.

    Order is preserved (callers pass an already-sorted ``served`` list)."""
    excluded_rel: Optional[str] = None
    if out_path is not None:
        try:
            out_rel = Path(out_path).resolve().relative_to(Path(repo_root).resolve())
        except ValueError:
            excluded_rel = None
        else:
            excluded_rel = out_rel.as_posix()
    return [
        p for p in served
        if p != excluded_rel and not p.endswith("memory-snapshot.json")
    ]


# --- git-tracked filter (the served set ships only tracked files) -----------


def _git_tracked_paths(repo_root) -> Optional[frozenset]:
    """Repo-root-relative POSIX paths tracked by git under ``repo_root``, or
    ``None`` when ``repo_root`` is not a git work tree.

    WHY this filter exists: the committed snapshot ships INSIDE a Docker image
    built from the git checkout, and its served-content drift is CI-verified
    against that same checkout (``test_committed_snapshot.py`` Branch B, which
    re-reads each served file's bytes). A file that is NOT git-tracked
    (untracked/gitignored) can neither ship in that image nor be read in a fresh
    CI checkout, so it must never enter ``served``/``files`` or the
    ``memory_inputs.served_content_manifest``, and its metadata must not leak
    into the served snapshot. A file that is present on the dev disk (and thus
    in the local Graphify index) but untracked — e.g. a gitignored
    ``ux-review/`` report — is exactly this hazard. The rule is the general
    invariant "git-tracked only", never a one-off path exclusion.

    Fail closed: if the ``git`` executable cannot be run at all (missing/broken
    binary), raise :class:`SnapshotError` rather than silently shipping
    untracked metadata. When ``repo_root`` is simply not a git work tree
    (``git`` returns non-zero — e.g. a throwaway tmp directory in a test), no
    Docker image is built from it and tracking is undefined, so return ``None``
    and let the caller skip the intersection. ``ls-files -z`` yields
    NUL-terminated, unquoted literal paths (repo-root-relative POSIX), matching
    how ``memory._is_served`` and the reader key served paths."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True,
        )
    except OSError as exc:  # git binary missing / not executable
        raise SnapshotError(
            f"cannot determine git-tracked files (git unavailable): {exc}"
        ) from exc
    if proc.returncode != 0:
        return None  # repo_root is not a git work tree; tracking is undefined here
    data = proc.stdout.decode("utf-8", "surrogateescape")
    return frozenset(p for p in data.split("\0") if p)


# --- generation -------------------------------------------------------------


def build_snapshot(
    graph_dir, repo_root, *, _rationale_originals=None, out_path=None
) -> dict:
    """Build the sanitized snapshot dict from a live/fixture Graphify artifacts
    directory. Drives ``LocalGraphArtifactSource``'s six public methods over
    the FULL concept-id set and FULL served-path set; never re-derives graph
    logic. Raises :class:`SnapshotError` if the source graph is absent/unreadable
    or a concept/file vanishes mid-generation (should never happen against a
    consistent snapshot of one reader instance).

    If ``_rationale_originals`` is a list, it is extended with every ORIGINAL
    (un-truncated) rationale string so the caller can secret-scan the full text,
    not just the emitted truncated value (a secret straddling the
    :data:`MAX_RATIONALE_CHARS` cut must still be caught).

    ``out_path``, when given, is the snapshot's own eventual ``--out`` target;
    it is used only to self-exclude the snapshot's own path (see
    :func:`_manifest_paths`) from the embedded ``memory_inputs`` served-content
    manifest (P24.10 Slice 2) — never read, never written here."""
    graph_dir = Path(graph_dir)
    repo_root = Path(repo_root)

    graph_path = graph_dir / memory.GRAPH_FILE
    if not graph_path.is_file():
        raise SnapshotError(f"source graph not found: {graph_path}")
    graph_bytes = graph_path.read_bytes()
    source_graph_sha256 = hashlib.sha256(graph_bytes).hexdigest()

    source = LocalGraphArtifactSource(graph_dir, repo_root=repo_root)
    overview = source.overview()
    if not overview.get("available"):
        raise SnapshotError(
            f"source graph unavailable: reason={overview.get('reason')!r}"
        )

    concept_detail_map: dict = {}
    for c in source.concepts():
        cid = c["id"]
        detail = source.concept(cid)
        if detail is None:
            raise SnapshotError(f"concept vanished during generation: {cid!r}")
        concept_detail_map[cid] = _sanitize_concept_detail(detail)

    # Restrict the served set to GIT-TRACKED files. Any untracked/gitignored
    # file the reader surfaced (present on the dev disk + Graphify index but not
    # in the checkout) is dropped here, so it never enters files/served or the
    # memory_inputs served-content manifest. See _git_tracked_paths for the full
    # rationale (ships in / verified against the git checkout only). ``None``
    # means repo_root is not a git work tree, so no intersection is applied.
    tracked_paths = _git_tracked_paths(repo_root)

    file_detail_map: dict = {}
    for f in source.files():
        path = f["path"]
        if tracked_paths is not None and path not in tracked_paths:
            continue
        detail = source.file(path)
        if detail is None:
            raise SnapshotError(f"file vanished during generation: {path!r}")
        if _rationale_originals is not None:
            _rationale_originals.extend(
                r for r in detail.get("rationales", []) if isinstance(r, str)
            )
        file_detail_map[path] = _sanitize_file_detail(detail)

    concepts_list = sorted(
        (_project_concept(d) for d in concept_detail_map.values()),
        key=lambda c: (c.get("label") or "", c.get("id") or ""),
    )
    files_list = sorted(
        (_project_file(d) for d in file_detail_map.values()),
        key=lambda f: f.get("path") or "",
    )
    served_list = sorted(f["path"] for f in files_list)

    _check_projection_consistency(concepts_list, concept_detail_map, files_list, file_detail_map)

    snapshot_overview = {
        "built_at_commit": overview.get("built_at_commit"),
        "graph_mtime": None,  # see module docstring: never a filesystem mtime
        "node_count": overview.get("node_count"),
        "edge_count": overview.get("edge_count"),
        "community_count": overview.get("community_count"),
        "concept_count": overview.get("concept_count"),
        # The reader's overview counts EVERY served file it indexed; this snapshot
        # serves only the git-tracked subset (see _git_tracked_paths), so report the
        # filtered served count to stay honest and internally consistent with
        # files/served. manifest_file_count is the raw Graphify-manifest key count
        # (a distinct concept, not the served subset) and is left as-is.
        "served_file_count": len(served_list),
        "manifest_file_count": overview.get("manifest_file_count"),
    }

    # --- P24.10 Slice 2: memory_inputs fingerprint block ---------------------
    # Reuses the pure primitives from isaac_api.memory unchanged (Slice 1);
    # this generator only WIRES them in. Self-excludes the snapshot's own
    # output path (and any stray *memory-snapshot.json) before reading bytes —
    # embedding the snapshot's own digest in itself would be circular.
    manifest_source_paths = _manifest_paths(served_list, repo_root=repo_root, out_path=out_path)
    try:
        served_content_manifest = memory.compute_served_content_manifest(
            manifest_source_paths, repo_root
        )
    except ValueError as exc:
        raise SnapshotError(f"failed to build served-content manifest: {exc}") from exc

    memory_inputs = {
        "policy_fingerprint": memory.compute_memory_policy_fingerprint(),
        "policy_version": memory.MEMORY_INPUTS_POLICY_VERSION,
        "projection_version": memory.PROJECTION_VERSION,
        "fingerprint_algo_version": memory.FINGERPRINT_ALGO_VERSION,
        "served_manifest_fingerprint": memory.compute_served_manifest_fingerprint(
            served_content_manifest
        ),
        "served_content_manifest": served_content_manifest,
        "served_file_count": len(served_content_manifest),
        "freshness_scope": "served_files_only",
        "freshness_basis": "ci_content_manifest",
    }

    return {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": SNAPSHOT_KIND,
        "generator": GENERATOR_PATH,
        "built_at_commit": overview.get("built_at_commit"),
        "source_graph_sha256": source_graph_sha256,
        "overview": snapshot_overview,
        "concepts": concepts_list,
        "concept_detail": concept_detail_map,
        "files": files_list,
        "file_detail": file_detail_map,
        "served": served_list,
        "memory_inputs": memory_inputs,
    }


# --- deep (symbol-level) structural layer -------------------------------------


def build_graph_detail(
    graph_dir, *, served, source_graph_sha256=None, _rationale_originals=None
) -> dict:
    """Build the deep (symbol-level) structural layer from the SAME source graph
    the snapshot was generated from, restricted to the snapshot's served set.

    ``served`` is the snapshot's ``served`` list (governance-filtered AND
    git-tracked). A node is retained ONLY when its ``source_file`` is a string
    that is path-safe, governance-served, and a member of ``served``; every
    other node — including every external/dependency node with no
    ``source_file`` — is dropped. An edge is retained only when BOTH endpoints
    survived that filter.

    Nothing is invented: node ``id`` / ``label`` / ``file_type`` /
    ``source_file`` / ``source_location`` / ``community`` and edge
    ``source`` / ``target`` / ``relation`` are the source graph's own values,
    passed through verbatim (``community`` is stringified to match the
    snapshot's ``community_id`` convention; a ``rationale`` node's label is
    truncated at :data:`MAX_RATIONALE_CHARS`, exactly like the snapshot's
    rationales). No hierarchy, no synthetic node, no synthetic edge, no
    relation renaming, and direction is preserved as recorded.

    Raises :class:`SnapshotError` if the source graph is absent/unreadable."""
    graph_dir = Path(graph_dir)
    graph_path = graph_dir / memory.GRAPH_FILE
    if not graph_path.is_file():
        raise SnapshotError(f"source graph not found: {graph_path}")
    graph_bytes = graph_path.read_bytes()
    if source_graph_sha256 is None:
        source_graph_sha256 = hashlib.sha256(graph_bytes).hexdigest()
    try:
        graph = json.loads(graph_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SnapshotError(f"source graph unreadable: {graph_path}: {exc}") from exc
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        raise SnapshotError(f"source graph structurally invalid: {graph_path}")

    served_set = frozenset(served)
    links = graph.get("links")
    if not isinstance(links, list):
        links = graph.get("edges")
    if not isinstance(links, list):
        links = []

    # -- nodes: explicit field allowlist. The source graph also carries
    # ``norm_label`` / ``_origin`` / ``source_url`` / ``captured_at`` /
    # ``author`` / ``contributor`` / ``rationale`` / ``type`` / ``ecosystem`` /
    # ``version`` on some nodes; NONE of them are emitted. Adding a field is a
    # deliberate act, never an accident of iteration.
    kept: dict = {}  # node id -> row tuple pieces
    for node in graph["nodes"]:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        sf = node.get("source_file")
        if not isinstance(nid, str) or not nid:
            continue
        if not isinstance(sf, str) or sf not in served_set:
            continue
        # Belt-and-suspenders over the served-set membership above: the same
        # two rules every other path-bearing field in this generator obeys.
        if LocalGraphArtifactSource._is_unsafe(sf) or not memory._is_served(sf):
            continue
        label = node.get("label")
        if not isinstance(label, str):
            label = None
        file_type = node.get("file_type")
        if not isinstance(file_type, str):
            file_type = None
        if file_type == memory.RATIONALE and label is not None:
            if _rationale_originals is not None:
                _rationale_originals.append(label)
            label = _truncate_rationale(label)
        loc = node.get("source_location")
        if not isinstance(loc, str):
            loc = None
        community_id = None
        if node.get("community") is not None:
            community_id = str(node["community"])
        if nid in kept:
            raise SnapshotError(f"duplicate node id in source graph: {nid!r}")
        kept[nid] = [nid, label, file_type, sf, loc, community_id]

    # Deterministic node order (and therefore deterministic edge indices):
    # by owning file, then by id. Independent of the source graph's own order.
    node_rows = sorted(kept.values(), key=lambda r: (r[3], r[0]))
    index_of = {row[0]: i for i, row in enumerate(node_rows)}

    edge_rows = []
    for link in links:
        if not isinstance(link, dict):
            continue
        src, tgt = link.get("source"), link.get("target")
        si, ti = index_of.get(src), index_of.get(tgt)
        if si is None or ti is None:
            continue
        relation = link.get("relation")
        if not isinstance(relation, str) or not relation:
            continue  # never invent a relation for an unlabeled edge
        edge_rows.append([si, ti, relation])
    edge_rows.sort(key=lambda e: (e[0], e[1], e[2]))

    labels = LocalGraphArtifactSource(graph_dir)._load_labels()
    used_communities = sorted({r[5] for r in node_rows if r[5] is not None})
    community_names = {}
    for cid in used_communities:
        name = labels.get(cid)
        community_names[cid] = name if isinstance(name, str) else None

    file_types: dict = {}
    for row in node_rows:
        key = row[2] if row[2] is not None else "unknown"
        file_types[key] = file_types.get(key, 0) + 1
    relations: dict = {}
    for edge in edge_rows:
        relations[edge[2]] = relations.get(edge[2], 0) + 1

    served_list = sorted(served_set)
    return {
        "kind": DETAIL_KIND,
        "detail_schema_version": DETAIL_SCHEMA_VERSION,
        "generator": GENERATOR_PATH,
        "built_at_commit": graph.get("built_at_commit"),
        "source_graph_sha256": source_graph_sha256,
        "policy_fingerprint": memory.compute_memory_policy_fingerprint(),
        # Honest staleness stamps: the STRUCTURE describes built_at_commit, which
        # is generally NOT the repository HEAD. Never present this as a current
        # code map.
        "structural_scope": DETAIL_STRUCTURAL_SCOPE,
        "structural_basis": DETAIL_STRUCTURAL_BASIS,
        # The served PATH SET size (``len(snapshot["served"])``), NOT the size of
        # the snapshot's CI content manifest. The two differ by one: the manifest
        # self-excludes any ``*memory-snapshot.json`` it would otherwise hash
        # (see ``_manifest_paths``), so ``memory_inputs.served_file_count`` is one
        # smaller than this. The runtime labels this explicitly when it publishes
        # the value (``memory_graph._detail_provenance``:
        # ``served_file_count_scope: "served_path_set"``).
        "served_file_count": len(served_list),
        # Single-sourced from the runtime reader module (never re-implemented
        # here) so the value the runtime recomputes and the value baked into the
        # artifact can never drift apart.
        "served_path_set_fingerprint": memory.compute_served_path_set_fingerprint(
            served_list
        ),
        "encoding": dict(DETAIL_ENCODING),
        "node_keys": list(DETAIL_NODE_KEYS),
        "edge_keys": list(DETAIL_EDGE_KEYS),
        "nodes": node_rows,
        "edges": edge_rows,
        "community_names": community_names,
        "counts": {
            "nodes": len(node_rows),
            "edges": len(edge_rows),
            "communities": len(community_names),
            "file_types": file_types,
            "relations": relations,
        },
    }


def _validate_detail_shape(detail: dict) -> list:
    """Return a list of human-readable shape problems; empty means valid."""
    issues = []
    if not isinstance(detail, dict):
        return ["graph detail is not a JSON object"]

    keys = set(detail.keys())
    if keys != _DETAIL_REQUIRED_KEYS:
        missing = sorted(_DETAIL_REQUIRED_KEYS - keys)
        extra = sorted(keys - _DETAIL_REQUIRED_KEYS)
        if missing:
            issues.append(f"missing top-level keys: {missing}")
        if extra:
            issues.append(f"unexpected top-level keys: {extra}")

    if detail.get("kind") != DETAIL_KIND:
        issues.append(f"kind must be {DETAIL_KIND!r}")
    # ``isinstance(True, int)`` is True and ``True != 1`` is False, so a bare
    # inequality would accept ``detail_schema_version: true`` as version 1.
    detail_version = detail.get("detail_schema_version")
    if not (isinstance(detail_version, int) and not isinstance(detail_version, bool)
            and detail_version == DETAIL_SCHEMA_VERSION):
        issues.append(f"detail_schema_version must be the int {DETAIL_SCHEMA_VERSION}")
    if detail.get("structural_scope") != DETAIL_STRUCTURAL_SCOPE:
        issues.append(f"structural_scope must be {DETAIL_STRUCTURAL_SCOPE!r}")
    if detail.get("structural_basis") != DETAIL_STRUCTURAL_BASIS:
        issues.append(f"structural_basis must be {DETAIL_STRUCTURAL_BASIS!r}")
    if list(detail.get("node_keys") or []) != list(DETAIL_NODE_KEYS):
        issues.append("node_keys must match DETAIL_NODE_KEYS")
    if list(detail.get("edge_keys") or []) != list(DETAIL_EDGE_KEYS):
        issues.append("edge_keys must match DETAIL_EDGE_KEYS")

    # Provenance must be PRESENT and non-null — a deep layer whose provenance is
    # unknown is worse than no deep layer (a consumer could mistake it for a
    # current code map).
    for prov_key in ("built_at_commit", "source_graph_sha256", "policy_fingerprint",
                     "served_path_set_fingerprint"):
        value = detail.get(prov_key)
        if not (isinstance(value, str) and value):
            issues.append(f"{prov_key} must be a non-empty string")
    sha = detail.get("source_graph_sha256")
    if isinstance(sha, str) and not re.fullmatch(r"[0-9a-f]{64}", sha):
        issues.append("source_graph_sha256 must be a 64-char hex sha256 digest")

    nodes = detail.get("nodes")
    edges = detail.get("edges")
    if not isinstance(nodes, list):
        issues.append("nodes must be a list")
        nodes = []
    if not isinstance(edges, list):
        issues.append("edges must be a list")
        edges = []

    seen_ids = set()
    for i, row in enumerate(nodes):
        if not (isinstance(row, list) and len(row) == len(DETAIL_NODE_KEYS)):
            issues.append(f"nodes[{i}] must be a {len(DETAIL_NODE_KEYS)}-element row")
            continue
        nid, label, file_type, sf, loc, cid = row
        if not (isinstance(nid, str) and nid):
            issues.append(f"nodes[{i}].id must be a non-empty string")
        elif nid in seen_ids:
            issues.append(f"nodes[{i}].id duplicated: {nid!r}")
        else:
            seen_ids.add(nid)
        if not (isinstance(sf, str) and sf):
            issues.append(f"nodes[{i}].source_file must be a non-empty string")
        for optional, name in ((label, "label"), (file_type, "file_type"),
                               (loc, "source_location"), (cid, "community_id")):
            if optional is not None and not isinstance(optional, str):
                issues.append(f"nodes[{i}].{name} must be a string or null")
        # ``source_location`` is a graph-internal line anchor (``L34``), never a
        # path: reject anything path-shaped outright.
        if isinstance(loc, str) and ("/" in loc or "\\" in loc):
            issues.append(f"nodes[{i}].source_location must not be path-shaped: {loc!r}")
        if isinstance(label, str) and len(label) > MAX_RATIONALE_CHARS \
                and file_type == memory.RATIONALE:
            issues.append(f"nodes[{i}].label exceeds MAX_RATIONALE_CHARS")

    node_count = len(nodes)
    for i, row in enumerate(edges):
        if not (isinstance(row, list) and len(row) == len(DETAIL_EDGE_KEYS)):
            issues.append(f"edges[{i}] must be a {len(DETAIL_EDGE_KEYS)}-element row")
            continue
        si, ti, relation = row
        for endpoint, name in ((si, "source_index"), (ti, "target_index")):
            if not (isinstance(endpoint, int) and not isinstance(endpoint, bool)
                    and 0 <= endpoint < node_count):
                issues.append(f"edges[{i}].{name} must index into nodes[]")
        if not (isinstance(relation, str) and relation):
            issues.append(f"edges[{i}].relation must be a non-empty string")

    community_names = detail.get("community_names")
    if not isinstance(community_names, dict):
        issues.append("community_names must be an object")
        community_names = {}
    else:
        for cid, name in community_names.items():
            if not isinstance(cid, str):
                issues.append(f"community_names key must be a string: {cid!r}")
            if name is not None and not isinstance(name, str):
                issues.append(f"community_names[{cid!r}] must be a string or null")

    counts = detail.get("counts")
    if not isinstance(counts, dict):
        issues.append("counts must be an object")
    else:
        if set(counts.keys()) != _DETAIL_COUNTS_KEYS:
            issues.append(f"counts keys mismatch: {sorted(counts.keys())}")
        if counts.get("nodes") != node_count:
            issues.append("counts.nodes must equal len(nodes)")
        if counts.get("edges") != len(edges):
            issues.append("counts.edges must equal len(edges)")
        if counts.get("communities") != len(community_names):
            issues.append("counts.communities must equal len(community_names)")
        for hist_key in ("file_types", "relations"):
            hist = counts.get(hist_key)
            if not isinstance(hist, dict) or not all(
                isinstance(v, int) and not isinstance(v, bool) for v in hist.values()
            ):
                issues.append(f"counts.{hist_key} must be an object of ints")

    served_count = detail.get("served_file_count")
    if not (isinstance(served_count, int) and not isinstance(served_count, bool)):
        issues.append("served_file_count must be an int")

    return issues


def _scan_detail_for_leaks(detail: dict, *, served, repo_root, extra_strings=()) -> list:
    """Fail-closed pre-write scan for the deep layer — the SAME policy the
    snapshot scan enforces, applied to every field the deep layer adds.

    (1) every node ``source_file`` must be path-safe, governance-served, AND a
    member of the snapshot's served set (a deep node whose owning file the
    snapshot does not serve must have been DROPPED, never emitted);
    (2) the machine-leak / credential value rules run over EVERY string in the
    artifact plus the un-truncated rationale originals;
    (3) no forbidden verdict/content key; (4) any ``on_disk`` value must be
    ``False`` (the deep layer emits none, so this asserts it stays that way)."""
    issues: list = []
    served_set = frozenset(served)

    nodes = detail.get("nodes")
    if not isinstance(nodes, list):
        nodes = []
    for i, row in enumerate(nodes):
        if not (isinstance(row, list) and len(row) == len(DETAIL_NODE_KEYS)):
            issues.append(f"nodes[{i}]: malformed row, cannot scan")
            continue
        sf = row[3]
        context = f"nodes[{i}].source_file"
        if not isinstance(sf, str):
            issues.append(f"{context}: non-string path value {sf!r}")
            continue
        if LocalGraphArtifactSource._is_unsafe(sf):
            issues.append(f"{context}: path-unsafe value {sf!r}")
            continue
        if not memory._is_served(sf):
            issues.append(f"{context}: non-served (governance-excluded) path {sf!r}")
            continue
        if sf not in served_set:
            issues.append(f"{context}: path outside the snapshot served set {sf!r}")

    repo_root_str = str(Path(repo_root).resolve())
    for s in _walk_strings(detail):
        issues.extend(_machine_secret_issues(s, repo_root_str))
    for s in extra_strings:
        if isinstance(s, str):
            issues.extend(_machine_secret_issues(s, repo_root_str))

    forbidden_hit = set(_walk_keys(detail)) & _FORBIDDEN_KEYS
    if forbidden_hit:
        issues.append(f"forbidden verdict/content key(s) present: {sorted(forbidden_hit)}")

    for on_disk in _walk_on_disk_values(detail):
        if on_disk is not False:
            issues.append(f"on_disk not forced false: {on_disk!r}")

    return issues


def _serialize_detail(detail: dict) -> bytes:
    """Stable serialization for the deep layer: sorted keys, one NODE/EDGE ROW
    PER LINE, trailing newline.

    Why not plain ``_serialize``: with ``indent=2`` every scalar of every
    positional row lands on its own line, which inflates the committed artifact
    by ~50% and makes a diff of one changed node span six lines. Emitting each
    row compactly on one line is both smaller AND more inspectable, while
    remaining a pure, deterministic function of ``detail`` (sorted keys at every
    level; no clock, no set iteration, no randomness)."""
    row_keys = ("nodes", "edges")
    keys = sorted(detail)
    chunks = ["{\n"]
    for position, key in enumerate(keys):
        tail = "," if position < len(keys) - 1 else ""
        key_json = json.dumps(key, ensure_ascii=False)
        if key in row_keys and isinstance(detail[key], list):
            rows = detail[key]
            if not rows:
                chunks.append(f"  {key_json}: []{tail}\n")
                continue
            chunks.append(f"  {key_json}: [\n")
            for i, row in enumerate(rows):
                row_tail = "," if i < len(rows) - 1 else ""
                chunks.append(
                    "    "
                    + json.dumps(row, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"))
                    + row_tail + "\n"
                )
            chunks.append(f"  ]{tail}\n")
        else:
            body = json.dumps(detail[key], ensure_ascii=False, sort_keys=True, indent=2)
            chunks.append(f"  {key_json}: {body.replace(chr(10), chr(10) + '  ')}{tail}\n")
    chunks.append("}\n")
    return "".join(chunks).encode("utf-8")


# --- shape validation ---------------------------------------------------------


def _validate_shape(snapshot: dict) -> list:
    """Return a list of human-readable shape problems; empty means valid."""
    issues = []
    if not isinstance(snapshot, dict):
        return ["snapshot is not a JSON object"]

    keys = set(snapshot.keys())
    missing = _REQUIRED_TOP_LEVEL_KEYS - keys
    extra = keys - _TOP_LEVEL_KEYS
    if missing:
        issues.append(f"missing top-level keys: {sorted(missing)}")
    if extra:
        issues.append(f"unexpected top-level keys: {sorted(extra)}")

    if not isinstance(snapshot.get("snapshot_schema_version"), int):
        issues.append("snapshot_schema_version must be an int")
    if snapshot.get("kind") != SNAPSHOT_KIND:
        issues.append(f"kind must be {SNAPSHOT_KIND!r}")
    if not isinstance(snapshot.get("generator"), str):
        issues.append("generator must be a string")

    bc = snapshot.get("built_at_commit")
    if bc is not None and not isinstance(bc, str):
        issues.append("built_at_commit must be a string or null")

    sha = snapshot.get("source_graph_sha256")
    if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
        issues.append("source_graph_sha256 must be a 64-char hex sha256 digest")

    overview = snapshot.get("overview")
    if not isinstance(overview, dict):
        issues.append("overview must be an object")
    else:
        okeys = set(overview.keys())
        if okeys != _OVERVIEW_KEYS:
            issues.append(f"overview keys mismatch: {sorted(okeys)}")
        if "graph_mtime" in overview and overview.get("graph_mtime") is not None:
            issues.append("overview.graph_mtime must be null")
        for count_key in ("node_count", "edge_count", "community_count",
                          "concept_count", "served_file_count", "manifest_file_count"):
            if count_key in overview and not isinstance(overview.get(count_key), int):
                issues.append(f"overview.{count_key} must be an int")

    for key, kind in (("concepts", list), ("files", list), ("served", list),
                       ("concept_detail", dict), ("file_detail", dict)):
        if not isinstance(snapshot.get(key), kind):
            issues.append(f"{key} must be a {kind.__name__}")

    # memory_inputs is OPTIONAL for shape validity (P24.10 Slice 2, additive —
    # see _OPTIONAL_TOP_LEVEL_KEYS), but when present must carry exactly the
    # expected sub-keys and value types.
    if "memory_inputs" in snapshot:
        mi = snapshot.get("memory_inputs")
        if not isinstance(mi, dict):
            issues.append("memory_inputs must be an object when present")
        else:
            mi_keys = set(mi.keys())
            if mi_keys != _MEMORY_INPUTS_KEYS:
                issues.append(f"memory_inputs keys mismatch: {sorted(mi_keys)}")
            for str_key in ("policy_fingerprint", "served_manifest_fingerprint",
                             "freshness_scope", "freshness_basis"):
                if str_key in mi and not isinstance(mi.get(str_key), str):
                    issues.append(f"memory_inputs.{str_key} must be a string")
            for int_key in ("policy_version", "projection_version",
                             "fingerprint_algo_version", "served_file_count"):
                if int_key in mi and not isinstance(mi.get(int_key), int):
                    issues.append(f"memory_inputs.{int_key} must be an int")
            manifest = mi.get("served_content_manifest")
            if not isinstance(manifest, list):
                issues.append("memory_inputs.served_content_manifest must be a list")
            elif "served_file_count" in mi and mi.get("served_file_count") != len(manifest):
                issues.append(
                    "memory_inputs.served_file_count must equal "
                    "len(served_content_manifest)"
                )

    return issues


# --- secret / governance scan (fail-closed, §8) -------------------------------


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


def _walk_on_disk_values(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "on_disk":
                yield v
            yield from _walk_on_disk_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_on_disk_values(v)


def _iter_path_fields(snapshot: dict):
    """Yield (context, path) for every path-bearing value. ``path`` may be
    ``None`` for a withheld (governance-excluded) concept anchor; callers
    must skip ``None`` — a null anchor is allowed, a non-null excluded one
    is not."""
    for p in snapshot.get("served", []) or []:
        yield ("served[]", p)
    for f in snapshot.get("files", []) or []:
        yield ("files[].path", f.get("path"))
    for path, detail in (snapshot.get("file_detail") or {}).items():
        yield ("file_detail key", path)
        yield ("file_detail.path", detail.get("path"))
        yield ("file_detail.local_reference", detail.get("local_reference"))
        for rf in (detail.get("related") or {}).get("files", []):
            yield ("file_detail.related.files[].path", rf.get("path"))
    for c in snapshot.get("concepts", []) or []:
        yield ("concepts[].source_file", c.get("source_file"))
    for cid, detail in (snapshot.get("concept_detail") or {}).items():
        yield (f"concept_detail[{cid!r}].source_file", detail.get("source_file"))
        for rf in (detail.get("related") or {}).get("files", []):
            yield (f"concept_detail[{cid!r}].related.files[].path", rf.get("path"))
    # P24.10 Slice 2: belt-and-suspenders over compute_served_content_manifest's
    # OWN _is_unsafe/_is_served enforcement at construction time — every
    # manifest entry's path goes through the same path-shape rule as every
    # other path-bearing field here.
    manifest = (snapshot.get("memory_inputs") or {}).get("served_content_manifest") or []
    for entry in manifest:
        if isinstance(entry, dict):
            yield ("memory_inputs.served_content_manifest[].path", entry.get("path"))


def _machine_secret_issues(s: str, repo_root_str: str) -> list:
    """Machine-leak / secret value checks applied to ANY string (NOT path-shape
    rules).

    A bare leading ``/`` and an anchored drive letter are deliberately NOT
    rejected here: a legitimate slash-command CONCEPT LABEL like
    ``/isaac-export`` is not a leak, and that exemption is a live decision (the
    real artifact carries five such labels). Path-SHAPE rejection — must not
    start with ``/`` or ``~``, no ``..`` segment, no backslash — happens only on
    the path-bearing fields (step 1 of each scanner). ``~`` IS rejected here,
    however: a home-directory shorthand is a machine marker in any field.

    Categories, all applied to every string of the artifact plus the
    un-truncated rationale originals: home markers (``/Users/``, ``/home/``,
    ``/root/``, ``~/``, ``~user/``), Windows/UNC machine paths, machine mount and
    OS-scratch roots (``/Volumes/``, ``/var/folders/``, ``/private/tmp|var``,
    ``/mnt|/media|/opt|/srv``), ``file://`` URLs, the generator's own repo root, email addresses,
    internal/organisational hostnames, mDNS ``*.local`` hostnames, non-loopback
    IPv4 addresses, private-key headers and credential-shaped tokens.

    Two exemptions are disclosed and narrow: loopback/``0.0.0.0`` addresses
    (``_IPV4_EXEMPT_RE``) and the project's own already-published deployment host
    (``_PUBLIC_HOST_EXEMPTIONS``)."""
    issues: list = []
    if any(marker in s for marker in _HOME_MARKERS):
        issues.append(f"home-directory marker found in value: {s!r}")
    if _HOME_SHORTHAND_RE.search(s):
        issues.append(f"home-shorthand ('~/') marker found in value: {s!r}")
    if _WINDOWS_MACHINE_RE.search(s):
        issues.append(f"windows machine path marker found in value: {s!r}")
    if _UNC_SHARE_RE.search(s):
        issues.append(f"UNC network share marker found in value: {s!r}")
    if _MACHINE_MOUNT_RE.search(s):
        issues.append(f"machine mount/scratch root found in value: {s!r}")
    if _FILE_URL_RE.search(s):
        issues.append(f"file:// URL found in value: {s!r}")
    if repo_root_str and repo_root_str in s:
        issues.append(f"generator machine repo-root string found in value: {s!r}")
    if _EMAIL_RE.search(s):
        issues.append(f"email address found in value: {s!r}")

    # Hostname rules run against a copy with the disclosed public-host exemption
    # removed, so the exemption cannot mask a DIFFERENT internal host in the same
    # string.
    hostname_scope = s
    for host in _PUBLIC_HOST_EXEMPTIONS:
        hostname_scope = hostname_scope.replace(host, "")
    if _INTERNAL_HOST_RE.search(hostname_scope):
        issues.append(f"internal hostname found in value: {s!r}")
    if _MDNS_HOST_RE.search(hostname_scope):
        issues.append(f"mDNS '.local' hostname found in value: {s!r}")

    for match in _IPV4_RE.finditer(s):
        if not _IPV4_EXEMPT_RE.match(match.group(0)):
            issues.append(f"IP address found in value: {match.group(0)!r} in {s!r}")

    if _PRIVATE_KEY_RE.search(s):
        issues.append("private-key marker found in a value")
    if _CREDENTIAL_RE.search(s):
        issues.append("credential-shaped token found in a value")
    return issues


def _scan_for_leaks(snapshot: dict, *, repo_root, extra_strings=()) -> list:
    """Fail-closed pre-write scan. Returns a list of human-readable issues;
    empty means clean. Scans PATHS and PROJECTED STRING METADATA only —
    never reads raw file contents.

    ``extra_strings`` are additional strings (e.g. the ORIGINAL, un-truncated
    rationale strings) run through the machine-leak / secret value checks so a
    secret straddling the :data:`MAX_RATIONALE_CHARS` cut cannot slip past by
    being split into a sub-pattern fragment in the emitted (truncated) value."""
    issues: list = []

    # (1) PATH-SHAPE rules — applied ONLY to path-bearing fields: every such
    # value must be NOT _is_unsafe (rejects leading '/', '..'-segment, '~',
    # backslash) AND _is_served. A null anchor (withheld excluded concept
    # anchor) is allowed and skipped.
    for context, path in _iter_path_fields(snapshot):
        if path is None:
            continue
        if not isinstance(path, str):
            issues.append(f"{context}: non-string path value {path!r}")
            continue
        if LocalGraphArtifactSource._is_unsafe(path):
            issues.append(f"{context}: path-unsafe value {path!r}")
            continue
        if not memory._is_served(path):
            issues.append(f"{context}: non-served (governance-excluded) path {path!r}")

    # (2) MACHINE-LEAK / SECRET rules — applied to ALL string values (paths,
    # labels, community_names, relations, rationales) PLUS the un-truncated
    # originals. NOT the path-shape rules above.
    repo_root_str = str(Path(repo_root).resolve())
    for s in _walk_strings(snapshot):
        issues.extend(_machine_secret_issues(s, repo_root_str))
    for s in extra_strings:
        if isinstance(s, str):
            issues.extend(_machine_secret_issues(s, repo_root_str))

    # (3) no content/lines key and none of the validation-verdict keys.
    keys = set(_walk_keys(snapshot))
    forbidden_hit = keys & _FORBIDDEN_KEYS
    if forbidden_hit:
        issues.append(f"forbidden verdict/content key(s) present: {sorted(forbidden_hit)}")

    # (4) on_disk uniformly false.
    for on_disk in _walk_on_disk_values(snapshot):
        if on_disk is not False:
            issues.append(f"on_disk not forced false: {on_disk!r}")

    return issues


# --- serialization (§7 determinism) -------------------------------------------


def _serialize(snapshot: dict) -> bytes:
    """Stable serialization: sorted keys, fixed indent, trailing newline.
    Byte-identical for byte-identical input across runs/machines."""
    text = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def _atomic_write(out_path: Path, payload: bytes) -> None:
    """Write ``payload`` to ``out_path`` atomically: a temp file in the same
    directory then ``os.replace`` — so a crash mid-write never leaves a
    truncated/partial snapshot at ``out_path``."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(out_path.parent), prefix=out_path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(tmp_name, out_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# --- CLI ------------------------------------------------------------------


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Generate the deterministic sanitized Project Memory snapshot."
    )
    parser.add_argument("--graph-dir", required=True, type=Path,
                        help="Directory containing graph.json/manifest.json/.graphify_labels.json")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output snapshot path (or --check target)")
    parser.add_argument("--repo-root", default=Path("."), type=Path,
                        help="Anchors _is_served/on_disk semantics (paths only); default '.'")
    parser.add_argument("--detail-out", default=None, type=Path,
                        help=("Also emit (or, with --check, verify) the deep "
                              "(symbol-level) structural layer at this path. Opt-in: "
                              "omitting it means the deep artifact is neither written "
                              "nor checked, and the run says so on stderr. The "
                              "documented value is "
                              "apps/api/isaac_api/data/memory-graph-detail.json — see "
                              "CLAUDE.md section 17."))
    parser.add_argument("--check", action="store_true",
                        help="Scan+validate only; write nothing; nonzero on any issue/drift")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()

    rationale_originals: list = []
    try:
        snapshot = build_snapshot(
            args.graph_dir, repo_root,
            _rationale_originals=rationale_originals, out_path=args.out,
        )
    except SnapshotError as exc:
        print(f"error: source graph unavailable: {exc}", file=sys.stderr)
        return EXIT_SOURCE_UNAVAILABLE

    shape_issues = _validate_shape(snapshot)
    if shape_issues:
        print("error: snapshot shape invalid:", file=sys.stderr)
        for issue in shape_issues:
            print(f"  - {issue}", file=sys.stderr)
        return EXIT_SHAPE_INVALID

    leak_issues = _scan_for_leaks(
        snapshot, repo_root=repo_root, extra_strings=rationale_originals
    )
    if leak_issues:
        print("error: secret/governance scan failed; writing nothing:", file=sys.stderr)
        for issue in leak_issues:
            print(f"  - {issue}", file=sys.stderr)
        return EXIT_SECURITY_SCAN_FAILED

    payload = _serialize(snapshot)

    # --- deep (symbol-level) structural layer, opt-in via --detail-out ---------
    # Built from the SAME graph bytes and restricted to the SAME served set the
    # snapshot just produced, so the two artifacts can never describe different
    # served path sets. Every failure mode below aborts BOTH writes (fail
    # closed): a half-written pair is worse than a stale pair.
    detail_payload = None
    if args.detail_out is not None:
        detail_originals: list = []
        try:
            detail = build_graph_detail(
                args.graph_dir,
                served=snapshot["served"],
                source_graph_sha256=snapshot["source_graph_sha256"],
                _rationale_originals=detail_originals,
            )
        except SnapshotError as exc:
            print(f"error: graph detail source unavailable: {exc}", file=sys.stderr)
            return EXIT_SOURCE_UNAVAILABLE

        detail_shape_issues = _validate_detail_shape(detail)
        if detail_shape_issues:
            print("error: graph detail shape invalid:", file=sys.stderr)
            for issue in detail_shape_issues:
                print(f"  - {issue}", file=sys.stderr)
            return EXIT_SHAPE_INVALID

        detail_leak_issues = _scan_detail_for_leaks(
            detail, served=snapshot["served"], repo_root=repo_root,
            extra_strings=detail_originals,
        )
        if detail_leak_issues:
            print(
                "error: graph detail secret/governance scan failed; writing nothing:",
                file=sys.stderr,
            )
            for issue in detail_leak_issues:
                print(f"  - {issue}", file=sys.stderr)
            return EXIT_SECURITY_SCAN_FAILED

        detail_payload = _serialize_detail(detail)

    # A run without --detail-out neither writes nor checks the deep artifact. That
    # is easy to do by accident (the documented command block omitted it for a
    # while), and silence there is dangerous in BOTH directions: a --check run
    # reports "no drift" while a stale deep artifact sits on disk, and a
    # regeneration run rewrites the snapshot and leaves the deep artifact stale.
    # So say so, on stderr, without changing the exit code or the default paths.
    if args.detail_out is None:
        verb = "checked" if args.check else "regenerated"
        print(
            f"note: --detail-out not given; the deep graph-detail artifact was NOT "
            f"{verb}. If it exists on disk it may be stale and this run says nothing "
            f"about it. Pass --detail-out "
            f"apps/api/isaac_api/data/memory-graph-detail.json to include it.",
            file=sys.stderr,
        )

    if args.check:
        # Both artifacts are reported, so an operator with two drifted files is
        # never told about only one of them. The exit code is unchanged.
        drift: list = []
        if not args.out.is_file():
            drift.append(f"--check target does not exist: {args.out}")
        elif args.out.read_bytes() != payload:
            drift.append(f"snapshot is stale/drifted relative to {args.out}")
        else:
            print(f"ok: {args.out} matches regenerated snapshot (no drift)")

        if detail_payload is not None:
            if not args.detail_out.is_file():
                drift.append(f"--check target does not exist: {args.detail_out}")
            elif args.detail_out.read_bytes() != detail_payload:
                drift.append(
                    f"graph detail is stale/drifted relative to {args.detail_out}"
                )
            else:
                print(f"ok: {args.detail_out} matches regenerated graph detail "
                      f"(no drift)")

        if drift:
            for issue in drift:
                print(f"error: {issue}", file=sys.stderr)
            return EXIT_CHECK_DRIFT
        return EXIT_OK

    _atomic_write(args.out, payload)
    print(f"wrote {args.out} ({len(payload)} bytes)")
    if detail_payload is not None:
        _atomic_write(args.detail_out, detail_payload)
        print(f"wrote {args.detail_out} ({len(detail_payload)} bytes)")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

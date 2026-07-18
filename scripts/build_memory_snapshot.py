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
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
MAX_RATIONALE_CHARS = 280

_TOP_LEVEL_KEYS = frozenset({
    "snapshot_schema_version", "kind", "generator",
    "built_at_commit", "source_graph_sha256",
    "overview", "concepts", "concept_detail",
    "files", "file_detail", "served",
})
_OVERVIEW_KEYS = frozenset({
    "built_at_commit", "graph_mtime", "node_count", "edge_count",
    "community_count", "concept_count", "served_file_count",
    "manifest_file_count",
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


# --- generation -------------------------------------------------------------


def build_snapshot(graph_dir, repo_root, *, _rationale_originals=None) -> dict:
    """Build the sanitized snapshot dict from a live/fixture Graphify artifacts
    directory. Drives ``LocalGraphArtifactSource``'s six public methods over
    the FULL concept-id set and FULL served-path set; never re-derives graph
    logic. Raises :class:`SnapshotError` if the source graph is absent/unreadable
    or a concept/file vanishes mid-generation (should never happen against a
    consistent snapshot of one reader instance).

    If ``_rationale_originals`` is a list, it is extended with every ORIGINAL
    (un-truncated) rationale string so the caller can secret-scan the full text,
    not just the emitted truncated value (a secret straddling the
    :data:`MAX_RATIONALE_CHARS` cut must still be caught)."""
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

    file_detail_map: dict = {}
    for f in source.files():
        path = f["path"]
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
        "served_file_count": overview.get("served_file_count"),
        "manifest_file_count": overview.get("manifest_file_count"),
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
    }


# --- shape validation ---------------------------------------------------------


def _validate_shape(snapshot: dict) -> list:
    """Return a list of human-readable shape problems; empty means valid."""
    issues = []
    if not isinstance(snapshot, dict):
        return ["snapshot is not a JSON object"]

    keys = set(snapshot.keys())
    missing = _TOP_LEVEL_KEYS - keys
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


def _machine_secret_issues(s: str, repo_root_str: str) -> list:
    """Machine-leak / secret value checks applied to ANY string (NOT path-shape
    rules). Bare ``startswith('/')`` / ``~`` / anchored-drive are deliberately
    NOT here — a legitimate slash-command label like ``/isaac-export`` is not a
    leak. Path-shape rejection happens only on path-bearing fields (step 1)."""
    issues: list = []
    if any(marker in s for marker in _HOME_MARKERS):
        issues.append(f"home-directory marker found in value: {s!r}")
    if _WINDOWS_MACHINE_RE.search(s):
        issues.append(f"windows machine path marker found in value: {s!r}")
    if repo_root_str and repo_root_str in s:
        issues.append(f"generator machine repo-root string found in value: {s!r}")
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
    parser.add_argument("--check", action="store_true",
                        help="Scan+validate only; write nothing; nonzero on any issue/drift")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()

    rationale_originals: list = []
    try:
        snapshot = build_snapshot(
            args.graph_dir, repo_root, _rationale_originals=rationale_originals
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

    if args.check:
        if not args.out.is_file():
            print(f"error: --check target does not exist: {args.out}", file=sys.stderr)
            return EXIT_CHECK_DRIFT
        existing = args.out.read_bytes()
        if existing != payload:
            print(f"error: snapshot is stale/drifted relative to {args.out}", file=sys.stderr)
            return EXIT_CHECK_DRIFT
        print(f"ok: {args.out} matches regenerated snapshot (no drift)")
        return EXIT_OK

    _atomic_write(args.out, payload)
    print(f"wrote {args.out} ({len(payload)} bytes)")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

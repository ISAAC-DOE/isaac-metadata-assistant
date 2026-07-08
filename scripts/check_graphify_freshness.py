#!/usr/bin/env python3
"""Deterministic Graphify freshness check (stdlib-only, no graphify required).

Prints exactly one word — fresh / stale / missing — and exits 0 / 1 / 2.
It compares the mtime of the derived graph (graphify-out/graph.json) against the
repo's *tracked source* material, mirroring the documented
`find ... -newer graphify-out/graph.json` staleness check in
docs/graphify-workflow.md §5 as a supported, testable tool.

MEMORY-PLANE convenience only: it never validates a record, never decides export,
never rewrites graphify-out/, never runs graphify, never reads file *contents*
(mtime only), never scans examples/ or other derived/volatile trees, and is not
imported by the deterministic truth path.

Usage:
    python scripts/check_graphify_freshness.py [REPO_ROOT]   # default: cwd
"""

from __future__ import annotations

import sys
from pathlib import Path

# Tracked source material whose changes should trigger a graph refresh
# (mirrors docs/graphify-workflow.md §5). Relative to the repo root.
TRACKED = (
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "pyproject.toml",
    "docs",
    "schema",
    "src",
    "scripts",
    "tests",
    ".claude/skills",
)

GRAPH = ("graphify-out", "graph.json")

# Directory names never scanned (derived / volatile / potentially sensitive).
# examples/ is excluded here AND is absent from TRACKED, so it is never walked.
IGNORED_DIRS = frozenset(
    {"graphify-out", ".venv", "__pycache__", ".pytest_cache", ".git", "examples"}
)

FRESH, STALE, MISSING = "fresh", "stale", "missing"
EXIT = {FRESH: 0, STALE: 1, MISSING: 2}


def _iter_source_files(root: Path):
    """Yield tracked source files under root, skipping ignored/derived dirs."""
    for name in TRACKED:
        target = root / name
        if target.is_file():
            yield target
        elif target.is_dir():
            for path in target.rglob("*"):
                if not path.is_file():
                    continue
                if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
                    continue
                yield path


def check(root: Path) -> str:
    """Return 'fresh', 'stale', or 'missing' for the graph under root.

    'missing' if graphify-out/graph.json is absent; 'stale' if any tracked source
    is strictly newer than the graph (matching `find -newer`); else 'fresh'.
    """
    graph = root.joinpath(*GRAPH)
    if not graph.is_file():
        return MISSING
    graph_mtime = graph.stat().st_mtime
    for path in _iter_source_files(root):
        try:
            if path.stat().st_mtime > graph_mtime:
                return STALE
        except OSError:
            continue
    return FRESH


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(argv[0]).resolve() if argv else Path.cwd()
    status = check(root)
    print(status)
    return EXIT[status]


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Refresh only the served-content manifest inside the committed memory snapshot.

``apps/api/isaac_api/data/memory-snapshot.json`` carries ``memory_inputs.served_content_manifest``:
one sha256 per served file, plus the aggregate ``served_manifest_fingerprint``.
``apps/api/tests/test_committed_snapshot.py`` fails when a listed file changes but its
hash does not, which is the usual cause of a red "tests and synthetic demo" job after
an ordinary web or docs edit.

``scripts/build_memory_snapshot.py`` regenerates the WHOLE snapshot, and it needs live
Graphify artifacts to do it. This script does the narrow job instead:

* it recomputes the hashes of the paths ALREADY listed, through the reader's own
  ``isaac_api.memory.compute_served_content_manifest``, so nothing is re-derived here;
* it rewrites only the changed ``sha256`` values and the fingerprint, leaving every other
  byte (formatting, order, every other field) as it was;
* it never adds or removes a path. A file that should start or stop being served needs
  a real snapshot rebuild.

Usage, from the repository root (or pass the root)::

    python scripts/refresh_served_manifest.py [REPO_ROOT]
    PYTHONPATH=src:apps/api python -m pytest apps/api/tests/test_committed_snapshot.py -q

Run it LAST, after every other edit in the change, because every listed file feeds the hash.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SNAPSHOT = Path("apps/api/isaac_api/data/memory-snapshot.json")


def refresh(root: Path) -> tuple[list[str], str, str]:
    sys.path[:0] = [str(root / "src"), str(root / "apps/api")]
    from isaac_api import memory  # noqa: E402 — the reader, added to the path above

    path = root / SNAPSHOT
    text = path.read_text(encoding="utf-8")
    inputs = json.loads(text)["memory_inputs"]
    old = inputs["served_content_manifest"]
    new = memory.compute_served_content_manifest([entry["path"] for entry in old], root)

    changed: list[str] = []
    for before, after in zip(old, new, strict=True):
        if before["path"] != after["path"]:
            raise SystemExit(f"manifest order changed at {before['path']!r}; rebuild the snapshot instead")
        if before["sha256"] != after["sha256"]:
            needle = f'"path": "{before["path"]}",\n        "sha256": "{before["sha256"]}"'
            if text.count(needle) != 1:
                raise SystemExit(f"cannot locate the manifest entry for {before['path']!r} exactly once")
            text = text.replace(needle, f'"path": "{after["path"]}",\n        "sha256": "{after["sha256"]}"')
            changed.append(before["path"])

    fingerprint_old = inputs["served_manifest_fingerprint"]
    fingerprint_new = memory.compute_served_manifest_fingerprint(new)
    if fingerprint_old != fingerprint_new:
        if text.count(fingerprint_old) != 1:
            raise SystemExit("cannot locate the served manifest fingerprint exactly once")
        text = text.replace(fingerprint_old, fingerprint_new)

    path.write_text(text, encoding="utf-8")
    return changed, fingerprint_old, fingerprint_new


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    changed, before, after = refresh(root)
    for name in changed:
        print("refreshed", name)
    print(f"{len(changed)} entries; fingerprint {before[:8]} -> {after[:8]}")


if __name__ == "__main__":
    main()

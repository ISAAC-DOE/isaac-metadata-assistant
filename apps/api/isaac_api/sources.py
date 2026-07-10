"""Governance-gated source preview.

Serves ONLY the two committed synthetic fixtures, by basename. No path traversal,
no arbitrary reads: this is the read side of the synthetic-only governance boundary
(the write side, ``POST /api/uploads``, is always 403). Anything outside the allowlist
is refused with a governance message.
"""

from __future__ import annotations

import re

from .workspace import CSV_PATH, LISTING_PATH

# basename -> (absolute path, media type). The complete, closed allowlist.
_ALLOWED = {
    CSV_PATH.name: (CSV_PATH, "text/csv"),
    LISTING_PATH.name: (LISTING_PATH, "text/plain"),
}

# Evidence locators like "line 16, ssrl-archive://…" carry a 1-based line number.
_LINE_RE = re.compile(r"\bline\s+(\d+)\b")


class SourceTraversal(Exception):
    """Raised when a source name is unsafe (contains '/' or '..' or is absolute)."""


class SourceNotAllowed(Exception):
    """Raised when a clean basename is not in the synthetic allowlist."""


def _guard_name(name: str) -> None:
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("~"):
        raise SourceTraversal(name)


def cited_lines_for(source_name: str, experiment) -> list[int]:
    """1-based line numbers of ``source_name`` referenced by the experiment's evidence.

    Derivable for the file listing (locators say ``line N``); the CSV cites fields, not
    lines, so it yields none — that is expected, not an error.
    """
    lines: set[int] = set()

    def scan(evidence_entries):
        for e in evidence_entries or []:
            if not isinstance(e, dict):
                continue
            if e.get("source_file") != source_name:
                continue
            m = _LINE_RE.search(str(e.get("locator") or ""))
            if m:
                lines.add(int(m.group(1)))

    draft = experiment.draft or {}
    for env in (draft.get("fields") or {}).values():
        if isinstance(env, dict):
            scan(env.get("evidence"))
    for imp in draft.get("implicit") or []:
        scan(imp.get("evidence"))
    for asset in draft.get("assets") or []:
        scan(asset.get("evidence"))
    for entry in draft.get("pending") or []:
        scan(entry.get("evidence"))

    return sorted(lines)


def read_source(source_name: str, experiment) -> dict:
    """Return the preview payload for an allowed synthetic fixture.

    Raises ``SourceTraversal`` (unsafe name) or ``SourceNotAllowed`` (not in allowlist).
    """
    _guard_name(source_name)
    if source_name not in _ALLOWED:
        raise SourceNotAllowed(source_name)
    path, media_type = _ALLOWED[source_name]
    text = path.read_text(encoding="utf-8")
    lines = [
        {"n": n, "text": line}
        for n, line in enumerate(text.splitlines(), start=1)
    ]
    return {
        "name": source_name,
        "media_type": media_type,
        "lines": lines,
        "cited_lines": cited_lines_for(source_name, experiment),
    }

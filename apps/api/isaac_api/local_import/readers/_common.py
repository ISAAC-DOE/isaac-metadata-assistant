"""Shared pieces of the generic readers: result types, the safe walk, hashing, line splitting.

Nothing here knows any file format. Every reader returns :class:`GenericRun` objects built from
these, so the bundle integrator consumes one shape whatever read the file.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...bl15.inventory import ArchiveLimits

SEVERITY_FLAG = "flag"
SEVERITY_NOTE = "note"

#: Most bytes read for one file, per reader (the BL15 walk's own per-entry ceiling is 8 MB).
MAX_SCAN_BYTES = 8_000_000
MAX_ROWS = 100_000
MAX_STATEMENT_CHARS = 2_000


@dataclass(frozen=True)
class Limits:
    """Walk ceilings, defaulting to the BL15 archive walk's own (not a second opinion)."""

    archive: ArchiveLimits = ArchiveLimits()
    max_scan_bytes: int = MAX_SCAN_BYTES
    max_companions_per_run: int = 50


@dataclass
class Anomaly:
    kind: str
    locator: str
    detail: str
    severity: str = SEVERITY_FLAG

    def to_dict(self) -> dict:
        return {"kind": self.kind, "locator": self.locator, "detail": self.detail, "severity": self.severity}


@dataclass
class HeaderLine:
    line: int
    key: str
    literal: str
    tokens: list[str] | None = None

    @property
    def locator(self) -> str:
        return f"line:{self.line}"


@dataclass
class GenericRun:
    """One run-like group of files and everything read from them. Pure data, no writes.

    ``run_key`` is ``<profile>:<relative directory>/<name>`` and cannot collide: two runs share
    a key only if they share a directory and a name, which is one run. ``scans`` holds one entry
    per file the reader parsed (``relative_path``, ``sha256``, ``size_bytes``, ``scan_index`` or
    ``None``, ``columns``, ``points`` and reader-specific literals). ``role_hints`` carries only
    what a file literally states (an application named in its own header, its extension); it is
    never a decision about what the file is.
    """

    run_key: str
    label: str
    profile: str
    directory: str
    scans: list[dict]
    companions: list[dict]
    statements: list[dict]
    anomalies: list[dict]
    header_differences: list[str]
    scan_indices: list[int]
    reader_id: str = ""
    role_hints: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReaderResult:
    """What one reader made of the files offered to it."""

    runs: list[GenericRun]
    #: Files the reader's naming rule selected but could not parse, each with why.
    unparsed: list[dict]
    #: ``(relative_path, role)`` for every file this reader consumed (a scan, a companion).
    consumed: list[tuple[str, str]]


@dataclass
class GenericCollection:
    runs: list[GenericRun]
    unparsed: list[dict]
    refused: list[dict]
    truncation: dict[str, int]
    files_seen: int


FileEntry = tuple[str, Path, int]  # (relative posix path, absolute path, size)


# --- analysis files -----------------------------------------------------------------------
#
# A scientist's ANALYSIS file (a Larch session, an Igor Pro experiment) is neither a run, nor a
# record group, nor a processed output. A reader of one returns an :class:`AnalysisFile`: a
# bounded list of statements the file makes, as VERBATIM literals with locators, plus the
# counts that say what was kept and what was not. The bundle holds them as ``extended_context[]``
# entries (``scope: "analysis_file"``, no ``run_id``, no ``processed_output_id``) and nothing
# else: no value is mapped onto an official field and no group or run is made from them.

#: Most extended-context entries ALL analysis files together may add to one bundle.
MAX_ANALYSIS_ENTRIES_TOTAL = 30_000
#: Characters kept of one stored literal unless a reader sets a tighter cap. A clipped literal
#: ENDS with :func:`clip_literal`'s marker, which names how many characters the source held.
MAX_ANALYSIS_LITERAL_CHARS = 500


@dataclass
class AnalysisFile:
    """What a reader of an analysis file found. Pure data; writes nothing.

    ``entries`` are ``{"concept", "literal", "locator"}`` dicts in file order. ``counts`` holds
    every total, kept count and cap (all integers or plain strings), so that a reader of the
    bundle can tell a complete reading from a bounded one. ``refused_reason`` is set, and
    ``entries`` is empty, when the file could not be read at all.
    """

    relative_path: str
    reader_id: str
    #: ``larch_session`` or ``igor_experiment`` (the file kind, from its own structure).
    kind: str
    entries: list[dict] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)
    refused_reason: str | None = None
    #: Things the reader could not parse and skipped (counted, never fatal).
    skipped_total: int = 0
    #: Statements it found and did not store because of a cap.
    suppressed_total: int = 0

    @property
    def partial(self) -> bool:
        return self.suppressed_total > 0


def clip_literal(text: str, limit: int = MAX_ANALYSIS_LITERAL_CHARS) -> tuple[str, bool]:
    """``(text or its first ``limit`` characters + a marker, whether it was clipped)``.

    The marker is part of the stored literal on purpose: a literal that was cut must say so
    where a reader looks at it, not only in a counter elsewhere.
    """
    if len(text) <= limit:
        return text, False
    return f"{text[:limit]} [clipped: first {limit} of {len(text)} characters]", True


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(root: Path, limits: ArchiveLimits, refused: list[dict], trunc: dict[str, int]) -> list[FileEntry]:
    """Regular files under ``root`` as ``(relative posix path, path, size)``. Symlinks are
    never followed and are listed as refused; depth, entry-count and path-length ceilings
    refuse and count rather than raise."""
    out: list[FileEntry] = []

    def visit(directory: Path, prefix: str, depth: int) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError:
            refused.append({"relative_path": prefix.rstrip("/") or ".", "reason": "unreadable_directory"})
            return
        for entry in entries:
            rel = f"{prefix}{entry.name}"
            try:
                if entry.is_symlink():
                    refused.append({"relative_path": rel, "reason": "symlink_not_followed"})
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth + 1 > limits.max_depth:
                        refused.append({"relative_path": rel, "reason": "too_deep"})
                        continue
                    visit(Path(entry.path), rel + "/", depth + 1)
                elif entry.is_file(follow_symlinks=False):
                    if len(rel) > limits.max_path_chars:
                        refused.append({"relative_path": rel[:80], "reason": "path_too_long"})
                        continue
                    if len(out) >= limits.max_entries:
                        trunc["files_not_considered"] = trunc.get("files_not_considered", 0) + 1
                        continue
                    out.append((rel, Path(entry.path), entry.stat(follow_symlinks=False).st_size))
            except OSError:
                refused.append({"relative_path": rel, "reason": "unreadable_entry"})

    visit(root, "", 0)
    return out


_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def split_lines(raw: bytes) -> list[str]:
    """Lines of a text file with ANY of CRLF, CR or LF as the break (old Mac exports use a bare
    CR). Decoded as latin-1 so every byte maps to a character and nothing can raise."""
    text = raw.decode("latin-1")
    lines = _LINE_BREAK.split(text)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def head_bytes(path: Path, n: int = 4096) -> bytes:
    try:
        with path.open("rb") as fh:
            return fh.read(n)
    except OSError:
        return b""


def clip(text: str, limit: int, trunc: dict[str, int], key: str) -> str:
    if len(text) <= limit:
        return text
    trunc[key] = trunc.get(key, 0) + len(text) - limit
    return text[:limit]


def statements_from(items: list[HeaderLine], rel: str, scan_index: int | None) -> list[dict]:
    return [
        {
            "key": i.key,
            "literal": i.literal,
            "tokens": i.tokens,
            "locator": i.locator,
            "source_relative_path": rel,
            "scan_index": scan_index,
        }
        for i in items
    ]

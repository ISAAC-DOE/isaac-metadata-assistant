"""Reader for headerless two-column numeric text files.

THE LAYOUT, FROM THE REAL FILES (literal structure only)
========================================================
Every non-blank line is two whitespace-separated numbers; there is no header, no comment and
no column name. The reader says so: every file carries the flag ``no_header``.

WHAT IS NOT DECIDED HERE
========================
Neither column is named or given a unit or a meaning. The first column is not called an energy
and the second is not called an intensity; ``columns`` holds the neutral labels ``column_1`` and
``column_2``, which are positions, not names. A line with more or fewer than two numbers, or a
cell that is not a number, is flagged.

SNIFFING IS STRICT ON PURPOSE. A file is claimed only if every complete line in its first
4 KiB has exactly two numeric tokens; any text line, a header, a third column or a lone word
rejects it. It is the LAST reader in the unified precedence so that no more specific format is
shadowed by it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ._common import (
    MAX_ROWS,
    MAX_SCAN_BYTES,
    SEVERITY_NOTE,
    Anomaly,
    FileEntry,
    GenericRun,
    Limits,
    ReaderResult,
    head_bytes,
    sha256_file,
    split_lines,
)

PROFILE_ID = "two_column_v1"
READER_ID = "two_column_reader_v1"
READER_VERSION = "1.0.0"

_SUFFIXES = (".txt",)


def _is_float(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


def sniff(path: str | Path) -> bool:
    p = Path(path)
    if p.suffix.lower() not in _SUFFIXES:
        return False
    head = head_bytes(p, 4096)
    if not head or b"\x00" in head:
        return False
    try:
        text = head.decode("ascii")
    except UnicodeDecodeError:
        return False
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(head) == 4096:
        lines = lines[:-1]  # the last line may be cut by the sample
    lines = [l for l in lines if l.strip()]
    if len(lines) < 2:
        return False
    for line in lines:
        tokens = line.split()
        if len(tokens) != 2 or not all(_is_float(t) for t in tokens):
            return False
    return True


@dataclass
class TwoColumnFile:
    rows: list[list[float | None]]
    anomalies: list[Anomaly] = field(default_factory=list)
    truncation: dict[str, int] = field(default_factory=dict)


def read(path: str | Path, *, max_bytes: int = MAX_SCAN_BYTES) -> TwoColumnFile:
    p = Path(path)
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"file is {size} bytes, over the {max_bytes}-byte bound")
    if not sniff(p):
        raise ValueError("not a headerless two-column numeric file")
    anomalies = [Anomaly("no_header", "line:1", "the file has no header, comment or column names; the columns are positions only", SEVERITY_NOTE)]
    trunc: dict[str, int] = {}
    rows: list[list[float | None]] = []
    for i, ln in enumerate(split_lines(p.read_bytes())):
        if not ln.strip():
            continue
        if len(rows) >= MAX_ROWS:
            trunc["rows_not_returned"] = trunc.get("rows_not_returned", 0) + 1
            continue
        tokens = ln.split()
        row: list[float | None] = []
        for col, token in enumerate(tokens):
            if _is_float(token):
                row.append(float(token))
            else:
                row.append(None)
                anomalies.append(Anomaly("non_numeric_cell", f"line:{i + 1}", f"column {col + 1} of this row is not a number; the cell is kept as null"))
        if len(tokens) != 2:
            anomalies.append(Anomaly("row_width_mismatch", f"line:{i + 1}", f"this row has {len(tokens)} cells and the file's first rows have 2"))
        rows.append(row)
    return TwoColumnFile(rows, anomalies, trunc)


def collect_from_files(files: list[FileEntry], limits: Limits = Limits(), claimed: set[str] | None = None) -> ReaderResult:
    """One run per file: nothing in a headerless file groups it with another."""
    claimed = claimed or set()
    runs: list[GenericRun] = []
    unparsed: list[dict] = []
    consumed: list[tuple[str, str]] = []
    for rel, path, size in sorted(files):
        if rel in claimed or not sniff(path):
            continue
        if size > min(limits.max_scan_bytes, limits.archive.max_entry_bytes):
            unparsed.append({"relative_path": rel, "reason_code": "file_too_large", "size_bytes": size})
            continue
        try:
            data = read(path, max_bytes=limits.max_scan_bytes)
        except (ValueError, OSError) as exc:
            unparsed.append({"relative_path": rel, "reason_code": "read_failed", "size_bytes": size, "detail": type(exc).__name__})
            continue
        consumed.append((rel, "scan"))
        directory, _, fname = rel.rpartition("/")
        stem = os.path.splitext(fname)[0]
        prefix = f"{directory}/" if directory else ""
        runs.append(
            GenericRun(
                run_key=f"{PROFILE_ID}:{prefix}{stem}",
                label=stem,
                profile=PROFILE_ID,
                directory=directory,
                scans=[
                    {
                        "relative_path": rel,
                        "sha256": sha256_file(path),
                        "size_bytes": size,
                        "scan_index": None,
                        "columns": ["column_1", "column_2"],
                        "points": len(data.rows),
                        "truncation": dict(data.truncation),
                    }
                ],
                companions=[],
                statements=[],
                anomalies=[{**a.to_dict(), "source_relative_path": rel, "scan_index": None} for a in data.anomalies],
                header_differences=[],
                scan_indices=[],
                reader_id=READER_ID,
                role_hints={"no_header": True, "extension": Path(rel).suffix.lower()},
            )
        )
    return ReaderResult(runs=runs, unparsed=unparsed, consumed=consumed)

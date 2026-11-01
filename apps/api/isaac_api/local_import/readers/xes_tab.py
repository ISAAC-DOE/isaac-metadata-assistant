"""Reader for tab-separated ``xes<N>`` text scans (a header of three ``xes`` names, then rows).

THE LAYOUT, FROM THE REAL FILES (literal structure only)
========================================================
The first line holds tab-separated names that are each ``xes`` and an integer
(``xes0<TAB>xes2<TAB>xes9``). Every later line holds the same number of tab-separated numbers.
The line break is a bare CR (an old Mac export) or CRLF or LF; all three are accepted.

WHAT IS NOT DECIDED HERE
========================
The names are kept verbatim (``header_names``) and are not given a meaning: this reader does not
say what ``xes0`` is, which column is an energy, what technique produced the file, or which
detector a number belongs to. The header line is a statement (``xes_header``), and the numeric
rows are parsed as floats. A row of the wrong width or a non-numeric cell is flagged.

GROUPING RULE (evidence in :func:`collect_from_files`)
======================================================
``<name>_<N>.txt`` files in one directory are repeat scans of ONE run ``<name>`` (N is the repeat
index). Evidence on the real corpus: 686 files in 129 folders at one depth; each folder holds an
extensionless file whose name equals ``<name>``, and 686 of 686 file names end ``_<digits>.txt``.
When that same-name file exists it is recorded as a related source (``same_name_file``), by the
shared name only; its content is read by whichever reader owns it, not here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ._common import (
    MAX_ROWS,
    MAX_SCAN_BYTES,
    SEVERITY_NOTE,
    Anomaly,
    FileEntry,
    GenericRun,
    HeaderLine,
    Limits,
    ReaderResult,
    head_bytes,
    sha256_file,
    split_lines,
    statements_from,
)
from dataclasses import dataclass, field

PROFILE_ID = "xes_tab_v1"
READER_ID = "xes_tab_reader_v1"
READER_VERSION = "1.0.0"

_NAME_TOKEN = re.compile(r"^xes\d+$")
_FILE_NAME = re.compile(r"^(?P<name>.+)_(?P<index>\d+)\.txt$", re.IGNORECASE)


def _header_names(first_line: str) -> list[str] | None:
    names = first_line.strip("\r\n").split("\t")
    if len(names) >= 2 and all(_NAME_TOKEN.match(n) for n in names):
        return names
    return None


def sniff(path: str | Path) -> bool:
    """True only when line 1 is two or more tab-separated ``xes<digits>`` names and no more."""
    head = head_bytes(Path(path), 1024)
    if not head or b"\x00" in head:
        return False
    first = re.split(rb"\r\n|\r|\n", head, maxsplit=1)[0]
    try:
        text = first.decode("ascii")
    except UnicodeDecodeError:
        return False
    return _header_names(text) is not None


@dataclass
class XesTabScan:
    header_names: list[str]
    header_line: HeaderLine
    rows: list[list[float | None]]
    anomalies: list[Anomaly] = field(default_factory=list)
    truncation: dict[str, int] = field(default_factory=dict)


def read(path: str | Path, *, max_bytes: int = MAX_SCAN_BYTES) -> XesTabScan:
    p = Path(path)
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"file is {size} bytes, over the {max_bytes}-byte bound")
    if not sniff(p):
        raise ValueError("not a tab-separated xes<N> scan")
    lines = split_lines(p.read_bytes())
    names = _header_names(lines[0])
    assert names is not None
    anomalies: list[Anomaly] = []
    trunc: dict[str, int] = {}
    rows: list[list[float | None]] = []
    for i in range(1, len(lines)):
        ln = lines[i]
        if not ln.strip():
            continue
        if len(rows) >= MAX_ROWS:
            trunc["rows_not_returned"] = trunc.get("rows_not_returned", 0) + 1
            continue
        tokens = ln.split("\t")
        row: list[float | None] = []
        for col, token in enumerate(tokens):
            try:
                row.append(float(token))
            except ValueError:
                row.append(None)
                anomalies.append(Anomaly("non_numeric_cell", f"line:{i + 1}", f"column {col + 1} of this row is not a number; the cell is kept as null"))
        if len(tokens) != len(names):
            anomalies.append(Anomaly("row_width_mismatch", f"line:{i + 1}", f"this row has {len(tokens)} cells and the header names {len(names)}"))
        rows.append(row)
    if not rows:
        anomalies.append(Anomaly("no_data", "line:2", "no data rows follow the header"))
    if len(set(names)) != len(names):
        anomalies.append(Anomaly("duplicate_column_names", "line:1", "two columns carry the same name", SEVERITY_NOTE))
    return XesTabScan(names, HeaderLine(1, "xes_header", "\t".join(names), list(names)), rows, anomalies, trunc)


def collect_from_files(files: list[FileEntry], limits: Limits = Limits(), claimed: set[str] | None = None) -> ReaderResult:
    claimed = claimed or set()
    by_rel = {rel: (path, size) for rel, path, size in files}
    groups: dict[tuple[str, str], list[tuple[int, str, Path, int]]] = {}
    unparsed: list[dict] = []
    consumed: list[tuple[str, str]] = []
    for rel, path, size in files:
        if rel in claimed:
            continue
        directory, _, fname = rel.rpartition("/")
        m = _FILE_NAME.match(fname)
        if not fname.lower().endswith(".txt") or not sniff(path):
            continue
        if size > min(limits.max_scan_bytes, limits.archive.max_entry_bytes):
            unparsed.append({"relative_path": rel, "reason_code": "file_too_large", "size_bytes": size})
            continue
        if m is None:
            # An xes header on a file that does not follow `<name>_<N>.txt`: a run of its own.
            groups.setdefault((directory, os.path.splitext(fname)[0]), []).append((0, rel, path, size))
        else:
            groups.setdefault((directory, m.group("name")), []).append((int(m.group("index")), rel, path, size))
    runs: list[GenericRun] = []
    for (directory, name), members in sorted(groups.items()):
        members.sort()
        prefix = f"{directory}/" if directory else ""
        scans: list[dict] = []
        statements: list[dict] = []
        anomalies: list[dict] = []
        headers: list[str] = []
        for index, rel, path, size in members:
            try:
                scan = read(path, max_bytes=limits.max_scan_bytes)
            except (ValueError, OSError) as exc:
                unparsed.append({"relative_path": rel, "reason_code": "read_failed", "size_bytes": size, "detail": type(exc).__name__})
                continue
            consumed.append((rel, "scan"))
            headers.append(scan.header_line.literal)
            scans.append(
                {
                    "relative_path": rel,
                    "sha256": sha256_file(path),
                    "size_bytes": size,
                    "scan_index": index,
                    "columns": list(scan.header_names),
                    "points": len(scan.rows),
                    "truncation": dict(scan.truncation),
                }
            )
            statements.extend(statements_from([scan.header_line], rel, index))
            for a in scan.anomalies:
                anomalies.append({**a.to_dict(), "source_relative_path": rel, "scan_index": index})
        if not scans:
            continue
        indices = [s["scan_index"] for s in scans]
        companions: list[dict] = []
        same = f"{prefix}{name}"
        if same in by_rel:  # a REFERENCE by shared name; it is not consumed, so whoever reads it still can
            path, size = by_rel[same]
            companions.append({"relative_path": same, "role": "same_name_file", "size_bytes": size, "sha256": sha256_file(path), "parsed": False})
        runs.append(
            GenericRun(
                run_key=f"{PROFILE_ID}:{prefix}{name}",
                label=name,
                profile=PROFILE_ID,
                directory=directory,
                scans=scans,
                companions=companions,
                statements=statements,
                anomalies=anomalies,
                header_differences=["xes_header"] if len(set(headers)) > 1 else [],
                scan_indices=indices,
                reader_id=READER_ID,
                role_hints={"technique": None, "note": "the header names are literal; no technique is assigned"},
            )
        )
    return ReaderResult(runs=runs, unparsed=unparsed, consumed=consumed)

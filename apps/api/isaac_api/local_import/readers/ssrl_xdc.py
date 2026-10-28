"""Reader for SSRL "EXAFS Data Collector 4.0" text scans (beamline 4-3 style folders).

WHAT THE FORMAT IS, AS FAR AS IT HAS BEEN VERIFIED (literal structure only)
===========================================================================
Line 1 is the signature ``SSRL   EXAFS Data Collector 4.0`` (three spaces). The header then
runs: line 2 a timestamp, line 3 ``PTS: N COLS: M``, line 4 a detector file name, line 5 a
region file name, line 6 a beamline/monochromator line, line 7 a timing line, line 8 a gain
line, any number of free-text lines, ``Weights:`` and one row, ``Offsets:`` and one row,
``Data:``, then ``M`` column-name lines, a blank line and ``N`` numeric rows. A ``_A.001``,
``_A.002`` ... series are repeat scans of one acquisition name; ``.rgn`` / ``.det`` / ``.exp``
files and a ``binary/`` folder of the original binary scans sit beside them.

WHAT THIS MODULE DOES NOT DO
============================
It decides NOTHING about what a header line means. Line 6 is kept as
``header_line_6_tokens`` and is not called an edge, a mono or a beamline; the timing and gain
lines likewise. The timestamp is parsed into a NAIVE datetime and ``timezone`` is the literal
``"not_stated"``: the file states no zone and none is assumed. A column is not given a unit
or a physical meaning; the only column the reader looks at by name is ``Requested Energy``
for one mechanical check (is the grid monotonic), and that is reported as a check, not a fact.
A non-numeric cell, a row with the wrong number of columns, a ``PTS`` or ``COLS`` that
disagrees with what was found, a non-monotonic energy grid and an unparseable timestamp are
FLAGGED (``anomalies``), never fixed and never raised.

THE BINARY VARIANT is a different signature (``SSRL - EXAFS Data Collector 4.0``, NUL bytes in
the header). :func:`sniff` rejects it; :func:`collect_generic` attaches those files to the run
of the same name as ``binary_original`` companions and parses nothing from them.

Everything is bounded (:class:`Limits`) and every bound that cuts something is counted.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ...bl15.inventory import ArchiveLimits
from ._common import (
    SEVERITY_FLAG,
    SEVERITY_NOTE,
    Anomaly,
    FileEntry,
    GenericCollection,
    GenericRun,
    HeaderLine,
    Limits,
    ReaderResult,
    sha256_file as _sha256,
    walk as _walk,
)

PROFILE_ID = "ssrl_xdc_v1"
READER_ID = "ssrl_xdc_reader_v1"
READER_VERSION = "1.0.0"

SIGNATURE = "SSRL   EXAFS Data Collector 4.0"
TIMEZONE_STATED = "not_stated"
ENERGY_COLUMN_NAME = "Requested Energy"

#: Most bytes read for one scan file, rows kept, and header lines scanned before ``Data:``.
MAX_SCAN_BYTES = 8_000_000
MAX_ROWS = 100_000
MAX_HEADER_LINES = 400
MAX_STATEMENT_CHARS = 2_000

# --- sniffing -------------------------------------------------------------------------------


def sniff(path: str | Path) -> bool:
    """True only when the first line is exactly the ASCII signature (trailing blanks and the
    line ending allowed). The binary variant, a single-space variant, a different version, a
    different case or leading text are all ``False``."""
    try:
        with Path(path).open("rb") as fh:
            first = fh.readline(256)
    except OSError:
        return False
    return _is_signature(first)


def _is_signature(first_line: bytes) -> bool:
    if b"\x00" in first_line:
        return False
    try:
        text = first_line.decode("ascii")
    except UnicodeDecodeError:
        return False
    return text.rstrip(" \t\r\n") == SIGNATURE


# --- the scan -------------------------------------------------------------------------------


@dataclass
class XdcScan:
    """One parsed scan file. Plain data; nothing here is interpreted."""

    version: str | None
    timestamp_literal: str | None
    timestamp_parsed: datetime | None  # naive; NEVER carries a zone
    timezone: str  # always "not_stated"
    points_declared: int | None
    cols_declared: int | None
    points_found: int
    cols_found: int
    detector_file: str | None
    region_file: str | None
    header_lines: list[HeaderLine]
    free_text_lines: list[HeaderLine]
    weights: list[float | None]
    offsets: list[float | None]
    column_names: list[str]
    rows: list[list[float | None]]
    energy_check: dict[str, Any]
    anomalies: list[Anomaly] = field(default_factory=list)
    truncation: dict[str, int] = field(default_factory=dict)


_PTS = re.compile(r"^\s*PTS:\s*(\d+)\s+COLS:\s*(\d+)\b")
_VERSION = re.compile(r"Data Collector (\d+\.\d+)\s*$")
_TIME_FORMAT = "%a %b %d %H:%M:%S %Y"


def _floats(text: str) -> list[float | None]:
    out: list[float | None] = []
    for token in text.split():
        try:
            out.append(float(token))
        except ValueError:
            out.append(None)
    return out


def read(path: str | Path, *, max_bytes: int = MAX_SCAN_BYTES) -> XdcScan:
    """Parse one scan file. Raises :class:`ValueError` only when the file is not an XDC scan
    (:func:`sniff` is false) or is over ``max_bytes``; every other irregularity is an anomaly."""
    p = Path(path)
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"file is {size} bytes, over the {max_bytes}-byte bound")
    raw = p.read_bytes()
    first_line = raw.split(b"\n", 1)[0]
    if not _is_signature(first_line):
        raise ValueError("not an SSRL EXAFS Data Collector 4.0 text scan")
    text = raw.decode("latin-1")  # every byte maps to a character; nothing is lost or raised
    lines = text.split("\n")
    lines = [ln.rstrip("\r") for ln in lines]
    anomalies: list[Anomaly] = []
    trunc: dict[str, int] = {}

    def lit(i: int) -> str | None:
        return lines[i].rstrip() if i < len(lines) else None

    version_match = _VERSION.search(lines[0].rstrip())
    header: list[HeaderLine] = [HeaderLine(1, "signature", lines[0].rstrip())]

    timestamp_literal = lit(1)
    parsed: datetime | None = None
    if timestamp_literal is not None:
        header.append(HeaderLine(2, "timestamp", timestamp_literal.strip()))
        try:
            parsed = datetime.strptime(timestamp_literal.strip(), _TIME_FORMAT)
        except ValueError:
            anomalies.append(Anomaly("timestamp_unparsed", "line:2", "the timestamp does not match 'Www Mmm dd hh:mm:ss yyyy'"))
        else:
            if parsed.strftime("%a") != timestamp_literal.strip()[:3]:
                anomalies.append(
                    Anomaly("timestamp_weekday_mismatch", "line:2", "the weekday named does not fall on the date named")
                )
    else:
        anomalies.append(Anomaly("header_incomplete", "line:2", "the file ends before the timestamp line"))

    points_declared = cols_declared = None
    pts_line = lit(2)
    if pts_line is not None:
        header.append(HeaderLine(3, "points_cols", pts_line.strip()))
        m = _PTS.match(pts_line)
        if m:
            points_declared, cols_declared = int(m.group(1)), int(m.group(2))
        else:
            anomalies.append(Anomaly("points_cols_unparsed", "line:3", "line 3 is not 'PTS: n COLS: m'"))
    else:
        anomalies.append(Anomaly("header_incomplete", "line:3", "the file ends before the PTS/COLS line"))

    detector_file = (lit(3) or "").strip() or None
    region_file = (lit(4) or "").strip() or None
    if lit(3) is not None:
        header.append(HeaderLine(4, "detector_file", lit(3).strip()))
    if lit(4) is not None:
        header.append(HeaderLine(5, "region_file", lit(4).strip()))
    for number, key, kind in ((6, "header_line_6_tokens", "tokens"), (7, "header_line_7_tokens", "tokens"), (8, "header_line_8_literal", "literal")):
        value = lit(number - 1)
        if value is None:
            anomalies.append(Anomaly("header_incomplete", f"line:{number}", "the file ends inside the fixed header lines"))
            continue
        header.append(HeaderLine(number, key, value.strip(), value.split() if kind == "tokens" else None))

    # Free text: every line from 9 up to the `Weights:` marker, kept verbatim.
    idx = 8
    free: list[HeaderLine] = []
    weights_at = None
    while idx < len(lines) and idx < MAX_HEADER_LINES:
        if lines[idx].strip() == "Weights:":
            weights_at = idx
            break
        if lines[idx].strip() == "Data:":
            break
        if lines[idx].strip():
            text_line = lines[idx].rstrip()
            if len(text_line) > MAX_STATEMENT_CHARS:
                trunc["free_text_chars_not_returned"] = trunc.get("free_text_chars_not_returned", 0) + len(text_line) - MAX_STATEMENT_CHARS
                text_line = text_line[:MAX_STATEMENT_CHARS]
            free.append(HeaderLine(idx + 1, "free_text", text_line.strip()))
        idx += 1
    weights: list[float | None] = []
    offsets: list[float | None] = []
    data_at = None
    if weights_at is None:
        anomalies.append(Anomaly("header_incomplete", f"line:{idx + 1}", "no 'Weights:' marker was found before the data"))
        if idx < len(lines) and lines[idx].strip() == "Data:":
            data_at = idx
    else:
        header.append(HeaderLine(weights_at + 1, "weights_marker", "Weights:"))
        wline = lit(weights_at + 1)
        weights = _floats(wline) if wline is not None else []
        if wline is not None:
            header.append(HeaderLine(weights_at + 2, "weights", wline.strip(), wline.split()))
        cursor = weights_at + 2
        if cursor < len(lines) and lines[cursor].strip() == "Offsets:":
            header.append(HeaderLine(cursor + 1, "offsets_marker", "Offsets:"))
            oline = lit(cursor + 1)
            offsets = _floats(oline) if oline is not None else []
            if oline is not None:
                header.append(HeaderLine(cursor + 2, "offsets", oline.strip(), oline.split()))
            cursor += 2
        else:
            anomalies.append(Anomaly("header_incomplete", f"line:{cursor + 1}", "no 'Offsets:' marker after the weights row"))
        if cursor < len(lines) and lines[cursor].strip() == "Data:":
            data_at = cursor
        else:
            anomalies.append(Anomaly("data_marker_missing", f"line:{cursor + 1}", "no 'Data:' marker after the offsets row"))

    columns: list[str] = []
    rows: list[list[float | None]] = []
    first_row_line = None
    if data_at is not None:
        header.append(HeaderLine(data_at + 1, "data_marker", "Data:"))
        i = data_at + 1
        limit = cols_declared if cols_declared is not None else None
        while i < len(lines) and lines[i].strip() != "":
            if limit is not None and len(columns) >= limit:
                break
            columns.append(lines[i].strip())
            i += 1
        if columns:
            header.append(HeaderLine(data_at + 2, "column_names", "\n".join(columns), list(columns)))
        # a single blank separator, then rows
        while i < len(lines) and lines[i].strip() == "":
            i += 1
        first_row_line = i + 1
        for j in range(i, len(lines)):
            ln = lines[j]
            if not ln.strip():
                continue
            if len(rows) >= MAX_ROWS:
                trunc["rows_not_returned"] = trunc.get("rows_not_returned", 0) + 1
                continue
            tokens = ln.split()
            row: list[float | None] = []
            for col, token in enumerate(tokens):
                try:
                    row.append(float(token))
                except ValueError:
                    row.append(None)
                    anomalies.append(
                        Anomaly("non_numeric_cell", f"line:{j + 1}", f"column {col + 1} of this row is not a number; the cell is kept as null")
                    )
            if columns and len(tokens) != len(columns):
                anomalies.append(
                    Anomaly("row_column_count_mismatch", f"line:{j + 1}", f"this row has {len(tokens)} cells and the header names {len(columns)} columns")
                )
            rows.append(row)
    else:
        anomalies.append(Anomaly("no_data", "line:1", "no data section could be located"))

    if points_declared is not None and points_declared != len(rows):
        anomalies.append(
            Anomaly("points_mismatch", f"line:3", f"the header declares {points_declared} points and {len(rows)} data rows were found")
        )
    if cols_declared is not None and columns and cols_declared != len(columns):
        anomalies.append(
            Anomaly("columns_mismatch", "line:3", f"the header declares {cols_declared} columns and {len(columns)} column names were found")
        )
    if len(columns) != len(set(columns)):
        anomalies.append(
            Anomaly("duplicate_column_names", f"line:{data_at + 2}" if data_at is not None else "line:1", "two or more columns carry the same name", SEVERITY_NOTE)
        )
    energy = _energy_check(columns, rows, first_row_line, anomalies)
    return XdcScan(
        version=version_match.group(1) if version_match else None,
        timestamp_literal=timestamp_literal.strip() if timestamp_literal is not None else None,
        timestamp_parsed=parsed,
        timezone=TIMEZONE_STATED,
        points_declared=points_declared,
        cols_declared=cols_declared,
        points_found=len(rows),
        cols_found=len(columns),
        detector_file=detector_file,
        region_file=region_file,
        header_lines=header,
        free_text_lines=free,
        weights=weights,
        offsets=offsets,
        column_names=columns,
        rows=rows,
        energy_check=energy,
        anomalies=anomalies,
        truncation=trunc,
    )



def _energy_check(columns: list[str], rows: list[list[float | None]], first_row_line: int | None, anomalies: list[Anomaly]) -> dict[str, Any]:
    """A mechanical check on the column literally named ``Requested Energy``: is the grid
    monotonic in one direction. Reported, never used to fix or reorder anything."""
    if ENERGY_COLUMN_NAME not in columns:
        return {"column": None, "checked": False, "reason": f"no column is named '{ENERGY_COLUMN_NAME}'"}
    index = columns.index(ENERGY_COLUMN_NAME)
    values = [(n, r[index]) for n, r in enumerate(rows) if index < len(r) and r[index] is not None]
    if len(values) < 2:
        return {"column": ENERGY_COLUMN_NAME, "checked": False, "reason": "fewer than two numeric values"}
    first, last = values[0][1], values[-1][1]
    direction = "increasing" if last > first else "decreasing" if last < first else "constant"
    breaks = 0
    first_break = None
    for (_, a), (n, b) in zip(values, values[1:]):
        wrong = (b < a) if direction == "increasing" else (b > a) if direction == "decreasing" else (b != a)
        if wrong:
            breaks += 1
            first_break = first_break if first_break is not None else n
    result: dict[str, Any] = {
        "column": ENERGY_COLUMN_NAME,
        "checked": True,
        "direction": direction if not breaks else "not_monotonic",
        "overall_direction": direction,
        "breaks": breaks,
    }
    if breaks:
        line = (first_row_line or 1) + (first_break or 0)
        result["first_break_row_index"] = first_break
        anomalies.append(
            Anomaly("energy_not_monotonic", f"line:{line}", f"{breaks} step(s) in '{ENERGY_COLUMN_NAME}' run against the {direction} direction of the scan")
        )
    return result


# --- collecting runs from a folder -----------------------------------------------------------

_SCAN_NAME = re.compile(r"^(?P<name>.+)_A\.(?P<index>\d{3,})$")
_BINARY_NAME = re.compile(r"^(?P<name>.+)\.(?P<index>\d{3,})$")
COMPANION_ROLES = {".rgn": "region", ".det": "detector", ".exp": "experiment"}


def collect_from_files(
    files: list[FileEntry], limits: Limits = Limits(), claimed: set[str] | None = None
) -> ReaderResult:
    """Runs from an already-walked file list, skipping any path in ``claimed``. Pure data."""
    claimed = claimed or set()
    by_rel = {rel: (path, size) for rel, path, size in files}
    unparsed: list[dict] = []
    consumed: list[tuple[str, str]] = []
    groups: dict[tuple[str, str], list[tuple[int, str, Path, int]]] = {}
    for rel, path, size in files:
        if rel in claimed:
            continue
        directory, _, fname = rel.rpartition("/")
        m = _SCAN_NAME.match(fname)
        if m is None:
            continue
        if not sniff(path):
            # A numbered `_A.NNN` file with another signature (the binary variant included) is
            # listed, not dropped; whether it is a different format is another reader's call.
            unparsed.append({"relative_path": rel, "reason_code": "signature_not_recognised", "size_bytes": size})
            continue
        if size > min(limits.max_scan_bytes, limits.archive.max_entry_bytes):
            unparsed.append({"relative_path": rel, "reason_code": "file_too_large", "size_bytes": size})
            continue
        groups.setdefault((directory, m.group("name")), []).append((int(m.group("index")), rel, path, size))

    runs: list[GenericRun] = []
    for (directory, name), members in sorted(groups.items()):
        members.sort()
        prefix = f"{directory}/" if directory else ""
        scans: list[dict] = []
        statements: list[dict] = []
        anomalies: list[dict] = []
        per_scan_header: list[dict[str, str]] = []
        for index, rel, path, size in members:
            try:
                scan = read(path, max_bytes=limits.max_scan_bytes)
            except (ValueError, OSError) as exc:
                unparsed.append({"relative_path": rel, "reason_code": "read_failed", "size_bytes": size, "detail": type(exc).__name__})
                continue
            digest = _sha256(path)
            consumed.append((rel, "scan"))
            scans.append(
                {
                    "relative_path": rel,
                    "sha256": digest,
                    "size_bytes": size,
                    "scan_index": index,
                    "columns": list(scan.column_names),
                    "points": scan.points_found,
                    "points_declared": scan.points_declared,
                    "timestamp_literal": scan.timestamp_literal,
                    "timestamp_naive": scan.timestamp_parsed.isoformat() if scan.timestamp_parsed else None,
                    "timezone": scan.timezone,
                    "energy_check": scan.energy_check,
                    "truncation": dict(scan.truncation),
                }
            )
            headers: dict[str, str] = {}
            for item in scan.header_lines + scan.free_text_lines:
                statements.append(
                    {
                        "key": item.key,
                        "literal": item.literal,
                        "tokens": item.tokens,
                        "locator": item.locator,
                        "source_relative_path": rel,
                        "scan_index": index,
                    }
                )
                if item.key not in ("timestamp", "free_text"):
                    headers[item.key] = item.literal
            per_scan_header.append(headers)
            for a in scan.anomalies:
                anomalies.append({**a.to_dict(), "source_relative_path": rel, "scan_index": index})
        if not scans:
            continue
        indices = [s["scan_index"] for s in scans]
        gaps = sorted(set(range(min(indices), max(indices) + 1)) - set(indices))
        if gaps:
            anomalies.append(
                {"kind": "scan_index_gap", "locator": "run", "detail": f"scan indices {gaps} are absent between {min(indices)} and {max(indices)}", "severity": SEVERITY_NOTE, "source_relative_path": None, "scan_index": None}
            )
        keys = set().union(*per_scan_header) if per_scan_header else set()
        differences = sorted(k for k in keys if len({h.get(k) for h in per_scan_header}) > 1)
        companions = _companions(prefix, name, by_rel, limits, claimed)
        for c in companions:
            consumed.append((c["relative_path"], c["role"]))
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
                header_differences=differences,
                scan_indices=indices,
                reader_id=READER_ID,
            )
        )
    return ReaderResult(runs=runs, unparsed=unparsed, consumed=consumed)


def collect_generic(root: str | Path, limits: Limits = Limits()) -> GenericCollection:
    """Walk ``root`` and return runs, plus every numbered file that was not parsed and why."""
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("the source root must be an existing folder that is not a symlink")
    refused: list[dict] = []
    trunc: dict[str, int] = {}
    files = _walk(base, limits.archive, refused, trunc)
    result = collect_from_files(files, limits)
    return GenericCollection(runs=result.runs, unparsed=result.unparsed, refused=refused, truncation=trunc, files_seen=len(files))


def _companions(prefix: str, name: str, by_rel: dict[str, tuple[Path, int]], limits: Limits, claimed: set[str]) -> list[dict]:
    """Context sources for one run: files in a same-named folder, a same-stem sibling with a
    companion extension, and the binary original of each scan in a sibling ``binary/`` folder.
    Metadata and a digest only; nothing is parsed."""
    found: list[tuple[str, str]] = []
    own_dir = f"{prefix}{name}/"
    for rel in by_rel:
        if rel in claimed:
            continue
        if rel.startswith(own_dir) and "/" not in rel[len(own_dir):]:
            ext = os.path.splitext(rel)[1].lower()
            found.append((rel, COMPANION_ROLES.get(ext, "other_context")))
        elif rel.startswith(prefix) and "/" not in rel[len(prefix):]:
            fname = rel[len(prefix):]
            stem, ext = os.path.splitext(fname)
            if stem == name and ext.lower() in COMPANION_ROLES:
                found.append((rel, COMPANION_ROLES[ext.lower()]))
        elif rel.startswith(f"{prefix}binary/") and "/" not in rel[len(prefix) + 7:]:
            m = _BINARY_NAME.match(rel[len(prefix) + 7:])
            if m and m.group("name") == name:
                found.append((rel, "binary_original"))
    out: list[dict] = []
    for rel, role in sorted(found)[: limits.max_companions_per_run]:
        path, size = by_rel[rel]
        out.append({"relative_path": rel, "role": role, "size_bytes": size, "sha256": _sha256(path), "parsed": False})
    return out


def collect_generic_runs(root: str | Path, limits: Limits = Limits()) -> list[GenericRun]:
    """The runs :func:`collect_generic` finds, without the unparsed/refused detail."""
    return collect_generic(root, limits).runs

"""Reader for PyMca/SPEC ``.mca`` text exports: a ``#F`` header and one array of counts.

THE LAYOUT, FROM THE REAL FILES (literal structure only)
========================================================
``#F <file path>``, ``#D <date>``, a blank line, ``#S <number> (<title>)``, ``#D <date>``,
``#@MCA %16C``, ``#@CHANN <channels> <first> <last> <reduction>``, ``#@CALIB <a> <b> <c>``, then
``@A <numbers>`` whose lines end in a backslash while the array continues. The array is read
across the continuation lines.

WHAT IS NOT DECIDED HERE
========================
The ``#F`` path, ``#S`` title and ``#D`` dates are kept verbatim as statements (the path is the
acquiring machine's, so it is source evidence and is not rewritten). ``#@CHANN`` and ``#@CALIB``
are parsed into numbers without a unit or a meaning. Nothing says what the spectrum is of.
The declared channel count is compared with the number of values found and any difference is
flagged. Only the FIRST block is read; a second ``#S`` or ``@A`` is flagged as not read.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ._common import (
    MAX_ROWS,
    MAX_SCAN_BYTES,
    MAX_STATEMENT_CHARS,
    SEVERITY_NOTE,
    Anomaly,
    FileEntry,
    GenericRun,
    HeaderLine,
    Limits,
    ReaderResult,
    clip,
    head_bytes,
    sha256_file,
    split_lines,
    statements_from,
)

PROFILE_ID = "mca_v1"
READER_ID = "mca_reader_v1"
READER_VERSION = "1.0.0"


def sniff(path: str | Path) -> bool:
    """True for a ``.mca`` file whose first line starts ``#F `` and which carries a
    ``#@MCA`` line and an ``@A`` line in its first 16 KiB. The extension is part of the test:
    SPEC acquisition files also begin ``#F`` and are another reader's."""
    p = Path(path)
    if p.suffix.lower() != ".mca":
        return False
    head = head_bytes(p, 16384)
    if not head.startswith(b"#F ") or b"\x00" in head:
        return False
    lines = re.split(rb"\r\n|\r|\n", head)
    return any(l.startswith(b"#@MCA") for l in lines) and any(l.startswith(b"@A") for l in lines)


@dataclass
class McaFile:
    header_lines: list[HeaderLine]
    channels_declared: int | None
    channel_range: list[float] | None  # the numbers on `#@CHANN`, after the channel count
    calibration: list[float | None]
    counts: list[float | None]
    anomalies: list[Anomaly] = field(default_factory=list)
    truncation: dict[str, int] = field(default_factory=dict)


def _numbers(text: str) -> list[float | None]:
    out: list[float | None] = []
    for token in text.split():
        try:
            out.append(float(token))
        except ValueError:
            out.append(None)
    return out


def read(path: str | Path, *, max_bytes: int = MAX_SCAN_BYTES) -> McaFile:
    p = Path(path)
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"file is {size} bytes, over the {max_bytes}-byte bound")
    if not sniff(p):
        raise ValueError("not a PyMca .mca export")
    lines = split_lines(p.read_bytes())
    anomalies: list[Anomaly] = []
    trunc: dict[str, int] = {}
    header: list[HeaderLine] = []
    channels: int | None = None
    chann_rest: list[float] | None = None
    calib: list[float | None] = []
    counts: list[float | None] = []
    blocks_s = 0
    in_array = False
    array_started = False
    extra_arrays = 0
    for i, raw in enumerate(lines):
        n = i + 1
        line = raw.rstrip()
        if in_array:
            if line.endswith("\\"):
                body = line[:-1]
            else:
                body, in_array = line, False
            if len(counts) < MAX_ROWS:
                counts.extend(_numbers(body))
            else:
                trunc["values_not_returned"] = trunc.get("values_not_returned", 0) + len(body.split())
            continue
        if line.startswith("@A"):
            if array_started:
                extra_arrays += 1
                continue
            array_started = True
            body = line[2:]
            if body.rstrip().endswith("\\"):
                body = body.rstrip()[:-1]
                in_array = True
            counts.extend(_numbers(body))
            continue
        if not line.startswith("#"):
            if line.strip():
                anomalies.append(Anomaly("unrecognised_line", f"line:{n}", "a line is neither a '#' header line nor part of the '@A' array", SEVERITY_NOTE))
            continue
        text = clip(line, MAX_STATEMENT_CHARS, trunc, "header_chars_not_returned")
        key_match = re.match(r"^#(@?[A-Za-z]+)\s*(.*)$", text)
        key = key_match.group(1) if key_match else "#"
        rest = key_match.group(2) if key_match else text[1:].strip()
        if key == "S":
            blocks_s += 1
            if blocks_s > 1:
                continue  # a second block is not read; flagged below
        if key == "@CHANN" and channels is None:
            nums = _numbers(rest)
            if nums and nums[0] is not None:
                channels = int(nums[0])
                chann_rest = [v for v in nums[1:] if v is not None]
        if key == "@CALIB" and not calib:
            calib = _numbers(rest)
        if not array_started:
            header.append(HeaderLine(n, {"F": "mca_file_path", "D": "date", "S": "scan_title", "@MCA": "mca_format", "@CHANN": "channels", "@CALIB": "calibration"}.get(key, f"header_{key}"), text[1:].strip() if key in ("S",) else rest, rest.split() if key in ("@CHANN", "@CALIB", "@MCA") else None))
    if extra_arrays or blocks_s > 1:
        anomalies.append(Anomaly("additional_block_not_read", "line:1", f"{max(extra_arrays, blocks_s - 1)} further '#S'/'@A' block(s) in the file were not read"))
    if not array_started:
        anomalies.append(Anomaly("no_counts_array", "line:1", "no '@A' array was found"))
    if channels is None:
        anomalies.append(Anomaly("channels_undeclared", "line:1", "no '#@CHANN' line with a channel count was found"))
    elif array_started and channels != len(counts):
        anomalies.append(Anomaly("channel_count_mismatch", "line:1", f"'#@CHANN' declares {channels} channels and {len(counts)} values were found"))
    if any(c is None for c in counts):
        anomalies.append(Anomaly("non_numeric_cell", "line:1", f"{sum(c is None for c in counts)} value(s) in the array are not numbers; kept as null"))
    return McaFile(header, channels, chann_rest, calib, counts, anomalies, trunc)


def collect_from_files(files: list[FileEntry], limits: Limits = Limits(), claimed: set[str] | None = None) -> ReaderResult:
    """One run per ``.mca`` file: the file is the unit, named by its file stem."""
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
            mca = read(path, max_bytes=limits.max_scan_bytes)
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
                        "columns": ["counts"],
                        "points": len(mca.counts),
                        "channels_declared": mca.channels_declared,
                        "channel_range": mca.channel_range,
                        "calibration": mca.calibration,
                        "truncation": dict(mca.truncation),
                    }
                ],
                companions=[],
                statements=statements_from(mca.header_lines, rel, None),
                anomalies=[{**a.to_dict(), "source_relative_path": rel, "scan_index": None} for a in mca.anomalies],
                header_differences=[],
                scan_indices=[],
                reader_id=READER_ID,
                role_hints={"extension": ".mca"},
            )
        )
    return ReaderResult(runs=runs, unparsed=unparsed, consumed=consumed)

"""Reader for SSRL "EXAFS Data Collector" 2.0 and 4.0 text scans (beamline 4-3 style folders).

WHAT THE FORMAT IS, AS FAR AS IT HAS BEEN VERIFIED (literal structure only)
===========================================================================
Line 1 is the signature ``SSRL   EXAFS Data Collector 4.0`` or ``SSRL   EXAFS Data Collector 2.0``
(three spaces; :data:`SIGNATURES`, a CLOSED set: no other version is accepted). The two versions
have the same text layout, which is all this reader reads, and each scan's stated version is kept
(``XdcScan.version``, the scan's ``version``). The header then
runs: line 2 a timestamp, line 3 ``PTS: N COLS: M``, line 4 a detector file name, line 5 a
region file name, line 6 a beamline/monochromator line, line 7 a timing line, line 8 the
``.exp`` COMMENTS1 (on the BL4-3 headers seen, the gain), any number of free-text lines (there,
COMMENTS2-4 on lines 9-11), ``Weights:`` and one row, ``Offsets:`` and one row,
``Data:``, then ``M`` column-name lines, a blank line and ``N`` numeric rows. A ``_A.001``,
``_A.002`` ... series are repeat scans of one acquisition name, and so is a bare ``.001``,
``.002`` ... series of TEXT scans (``NAME.NNN``, see :func:`collect_from_files`); ``.rgn`` / ``.det`` / ``.exp``
files and a ``binary/`` folder of the original binary scans sit beside them. Of the run's own
``<name>.exp`` only the ``DATA_FILE`` line (the name without its trailing ``_NNN``) is read; with no
``<name>.exp``, the same line of the ONLY ``.exp`` in the run's own folder (a template reused under
another name), kept only when it is the run's own name without its counter.

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

THE BINARY VARIANT is a different signature (``SSRL - EXAFS Data Collector 4.0`` or ``2.0``, NUL
bytes in the header). :func:`sniff` rejects it; :func:`collect_generic` attaches those files to the
run of the same name as ``binary_original`` companions and parses nothing from them.

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
#: 1.1.0: also reads the 2.0 text scans (same layout) and bare ``NAME.NNN`` text scans.
READER_VERSION = "1.1.0"

SIGNATURE = "SSRL   EXAFS Data Collector 4.0"
SIGNATURE_V2 = "SSRL   EXAFS Data Collector 2.0"
#: The accepted first lines, by the version each states. A CLOSED set: a version not listed here
#: (``4.1``, ``3.0`` ...) is not read, whatever its layout.
SIGNATURES: dict[str, str] = {"2.0": SIGNATURE_V2, "4.0": SIGNATURE}
ACCEPTED_VERSIONS = tuple(SIGNATURES)
TIMEZONE_STATED = "not_stated"
ENERGY_COLUMN_NAME = "Requested Energy"

#: Most bytes read for one scan file, rows kept, and header lines scanned before ``Data:``.
MAX_SCAN_BYTES = 8_000_000
MAX_ROWS = 100_000
MAX_HEADER_LINES = 400
MAX_STATEMENT_CHARS = 2_000

# --- sniffing -------------------------------------------------------------------------------


def sniff(path: str | Path) -> bool:
    """True only when the first line is exactly one of the ASCII :data:`SIGNATURES` (2.0 or 4.0;
    trailing blanks and the line ending allowed). The binary variant, a single-space variant, a
    version outside that set, a different case or leading text are all ``False``."""
    try:
        with Path(path).open("rb") as fh:
            first = fh.readline(256)
    except OSError:
        return False
    return _is_signature(first)


def _is_signature(first_line: bytes) -> bool:
    return _signature_version(first_line) is not None


def _signature_version(first_line: bytes) -> str | None:
    """The version (one of :data:`ACCEPTED_VERSIONS`) the first line states, or ``None`` when it is no signature."""
    if b"\x00" in first_line:
        return None
    try:
        text = first_line.decode("ascii")
    except UnicodeDecodeError:
        return None
    return next((v for v, sig in SIGNATURES.items() if text.rstrip(" \t\r\n") == sig), None)


def sniff_version(path: str | Path) -> str | None:
    """:func:`sniff`, saying WHICH version: ``"2.0"``, ``"4.0"`` or ``None``."""
    try:
        with Path(path).open("rb") as fh:
            first = fh.readline(256)
    except OSError:
        return None
    return _signature_version(first)


# --- the scan -------------------------------------------------------------------------------


@dataclass
class XdcScan:
    """One parsed scan file. Plain data; nothing here is interpreted."""

    version: str | None  # the version line 1 states: one of ACCEPTED_VERSIONS
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
        raise ValueError("not an SSRL EXAFS Data Collector 2.0 or 4.0 text scan")
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
#: A bare numbered name (``NAME.NNN``, no ``_A``): the binary originals' pattern too, so the TEXT
#: sniff decides. A file that passes it is a scan; one that does not is left exactly as before (a
#: ``binary_original`` companion when it sits in a ``binary/`` folder beside its run).
_BARE_SCAN_NAME = _BINARY_NAME
#: The name a bare series takes when the same folder also holds a ``NAME_A.NNN`` series of the
#: same NAME (compared without case): the ``_A`` series keeps ``NAME``, the bare one is
#: ``NAME.NNN``, the literal pattern of its files. Never merged; both carry :data:`COLLISION_KIND`.
BARE_COLLISION_SUFFIX = ".NNN"
COLLISION_KIND = "bare_and_a_series_share_a_name"
#: A 2.0 scan in an ``_A`` series that also has 4.0 scans: left OUT of the run (as reader 1.0.0 left it) and named.
V2_IN_V4_KIND = "v2_scan_in_v4_series_not_read"
COMPANION_ROLES = {".rgn": "region", ".det": "detector", ".exp": "experiment"}


def collect_from_files(
    files: list[FileEntry], limits: Limits = Limits(), claimed: set[str] | None = None
) -> ReaderResult:
    """Runs from an already-walked file list, skipping any path in ``claimed``. Pure data.

    TWO NAMINGS OF A SERIES. ``NAME_A.NNN`` text scans are one run named ``NAME`` (as always).
    A BARE ``NAME.NNN`` file is a scan only when it passes the text :func:`sniff`; it is then a
    scan of a run named ``NAME`` (``run_key`` ``ssrl_xdc_v1:<dir>/NAME``) with the same
    companions and ``.exp`` reading. A bare file that fails the sniff (a binary original) is not
    listed and stays what it was: a ``binary_original`` companion. A bare TEXT file where a run's
    companions are looked for (``<dir>/binary/NAME.NNN`` or ``<dir>/NAME/<file>`` beside a run
    ``NAME``) stays that run's companion, as before: it is never a run of its own.

    WHAT READER 1.0.0 FOUND KEEPS ITS PLACE. An ``_A`` series with at least one 4.0 scan was a run
    under reader 1.0.0 and is returned, in the same order, in :attr:`ReaderResult.runs`, read exactly
    as 1.0.0 read it: a 2.0 scan in it is NOT read (listed as not parsed, as 1.0.0 listed it, and named
    on the run as :data:`V2_IN_V4_KIND`, for the scientist). Every run
    1.0.0 did not find (a 2.0-only ``_A`` series, a bare series) is in :attr:`ReaderResult.late_runs`,
    which ``readers.collect_all_generic`` places after every reader's runs: such a run only ADDS run
    ids after the ones an import by the earlier build gave.

    THE COLLISION. When one folder holds both ``X.NNN`` and ``X_A.NNN`` text scans (X compared
    without case), they are NOT made one run: the ``_A`` series keeps the name ``X`` (and every
    companion named ``X``, compared without case as the collision is), the bare series is the run
    ``X.NNN`` (:data:`BARE_COLLISION_SUFFIX`; ``X.NNN-2``, ``-3`` ... when that name is taken) with no
    companion and no ``.exp`` reading of its own, and both runs carry a :data:`COLLISION_KIND`
    anomaly naming the other, so a scientist decides whether they are one acquisition. No two runs
    ever share a ``run_key``. A bare text scan is never also a companion of another run."""
    claimed = claimed or set()
    by_rel = {rel: (path, size) for rel, path, size in files}
    unparsed: list[dict] = []
    consumed: list[tuple[str, str]] = []
    groups: dict[tuple[str, str], list[tuple[int, str, Path, int]]] = {}
    early: set[tuple[str, str]] = set()  # _A series with a 4.0 scan: what reader 1.0.0 found
    bare_groups: dict[tuple[str, str], list[tuple[int, str, Path, int]]] = {}
    # An `_A` series with a 4.0 scan is the run reader 1.0.0 found, and it is found EXACTLY so: a 2.0 scan in it stays
    # out of it (listed as 1.0.0 listed it, and named on the run: V2_IN_V4_KIND). Only an `_A` series with no 4.0
    # scan at all is read from its 2.0 scans (a new, late run).
    versions = {rel: sniff_version(path) for rel, path, _s in files
                if rel not in claimed and _SCAN_NAME.match(rel.rpartition("/")[2])}
    has_v4 = {(rel.rpartition("/")[0], _SCAN_NAME.match(rel.rpartition("/")[2]).group("name"))
              for rel, v in versions.items() if v == "4.0"}
    v2_left_out: dict[tuple[str, str], list[str]] = {}
    for rel, path, size in files:
        if rel in claimed:
            continue
        directory, _, fname = rel.rpartition("/")
        m = _SCAN_NAME.match(fname)
        if m is None:
            bare = _BARE_SCAN_NAME.match(fname)
            if bare is None or not sniff(path):
                continue  # not a numbered name, or not a text scan (a binary original): as before
            if size > min(limits.max_scan_bytes, limits.archive.max_entry_bytes):
                unparsed.append({"relative_path": rel, "reason_code": "file_too_large", "size_bytes": size})
                continue
            bare_groups.setdefault((directory, bare.group("name")), []).append((int(bare.group("index")), rel, path, size))
            continue
        version = versions.get(rel)
        if version is None or (version == "2.0" and (directory, m.group("name")) in has_v4):
            # A numbered `_A.NNN` file with another signature (the binary variant included) is
            # listed, not dropped; whether it is a different format is another reader's call.
            unparsed.append({"relative_path": rel, "reason_code": "signature_not_recognised", "size_bytes": size})
            if version == "2.0":
                v2_left_out.setdefault((directory, m.group("name")), []).append(rel)
            continue
        if size > min(limits.max_scan_bytes, limits.archive.max_entry_bytes):
            unparsed.append({"relative_path": rel, "reason_code": "file_too_large", "size_bytes": size})
            continue
        groups.setdefault((directory, m.group("name")), []).append((int(m.group("index")), rel, path, size))
        if version == "4.0":
            early.add((directory, m.group("name")))

    # A bare text file where a run's companions are looked for stays that run's companion (as before).
    # Parents are decided folder by folder from the top, so a bare series that is itself a companion
    # is never a parent.
    parents: set[tuple[str, str]] = set(groups)
    accepted: dict[tuple[str, str], list[tuple[int, str, Path, int]]] = {}
    for (directory, name), members in sorted(bare_groups.items(), key=lambda kv: (kv[0][0].count("/") if kv[0][0] else -1, kv[0])):
        if _companion_place_of(directory, name, parents):
            continue
        accepted[(directory, name)] = members
        parents.add((directory, name))
    bare_scans = {rel for members in accepted.values() for _i, rel, _p, _s in members}

    a_names = {(d, n.casefold()): n for d, n in groups}
    taken = set(a_names) | {(d, n.casefold()) for d, n in accepted}
    collisions: dict[tuple[str, str], str] = {}  # _A group -> the bare run's name
    plan: list[tuple[str, str, str, list, str | None]] = []  # (directory, name, run name, members, collides with)
    for (directory, name), members in sorted(accepted.items()):
        other = a_names.get((directory, name.casefold()))
        run_name = name
        if other is not None:
            run_name, n = f"{name}{BARE_COLLISION_SUFFIX}", 1
            while (directory, run_name.casefold()) in taken:  # L3: never a second run with one run_key
                n += 1
                run_name = f"{name}{BARE_COLLISION_SUFFIX}-{n}"
            taken.add((directory, run_name.casefold()))
            collisions[(directory, other)] = run_name
        plan.append((directory, name, run_name, members, other))

    runs: list[GenericRun] = []
    late_runs: list[GenericRun] = []
    exp_taken: set[str] = set()
    a_order = sorted(groups.items(), key=lambda kv: (kv[0] not in early, kv[0]))  # 1.0.0's runs first, in its order
    for (directory, name), members in a_order:
        bare_name = collisions.get((directory, name))
        run = _build_run(directory, name, name, members, by_rel, limits, claimed, bare_scans, exp_taken,
                         unparsed, consumed, with_companions=True, fold=bare_name is not None)
        if run is None:
            continue
        if v2_left_out.get((directory, name)):
            files_out = v2_left_out[(directory, name)]
            run.anomalies.append({
                "kind": V2_IN_V4_KIND, "locator": "run", "severity": SEVERITY_FLAG, "source_relative_path": None,
                "scan_index": None,
                "detail": (f"{len(files_out)} scan file(s) of this series state EXAFS Data Collector 2.0 while the rest "
                           f"state 4.0 ({', '.join(files_out[:10])}{' ...' if len(files_out) > 10 else ''}); they were NOT "
                           "read into this run (as before), and are listed as not parsed. A scientist decides whether "
                           "they belong to it")})
        if bare_name is not None:
            run.anomalies.append(_collision_anomaly(
                f"the same folder also holds bare {name}.NNN text scans (compared without case); they are kept as the "
                f"separate run {bare_name}, not merged with this one. A scientist decides whether the two series are "
                "one acquisition"))
        # 1.0.0 found it only when one of the scans it READ is a 4.0 scan (the scans 1.0.0 would have read)
        (runs if any(sc["version"] == "4.0" for sc in run.scans) else late_runs).append(run)
    for directory, name, run_name, members, other in plan:
        run = _build_run(directory, name, run_name, members, by_rel, limits, claimed, bare_scans, exp_taken,
                         unparsed, consumed, with_companions=other is None)
        if run is None:
            continue
        if other is not None:
            run.anomalies.append(_collision_anomaly(
                f"the same folder also holds {other}_A.NNN text scans (the run {other}); these bare {name}.NNN scans are "
                f"kept as the separate run {run_name}, not merged with it, and the companion files named {other} stay "
                "with that run. A scientist decides whether the two series are one acquisition"))
        late_runs.append(run)
    return ReaderResult(runs=runs, unparsed=unparsed, consumed=consumed, late_runs=late_runs)


def _companion_place_of(directory: str, name: str, parents: set[tuple[str, str]]) -> bool:
    """Whether a bare series ``<directory>/<name>.NNN`` sits where a run's companions are looked for
    (:func:`_companions`): in ``<p>/binary/`` beside a run ``<p>/<name>``, or in ``<p>/<run>/``."""
    parent, _, last = directory.rpartition("/")
    if last == "binary" and (parent, name) in parents:
        return True
    return bool(directory) and (parent, last) in parents


def _collision_anomaly(detail: str) -> dict:
    return {"kind": COLLISION_KIND, "locator": "run", "detail": detail, "severity": SEVERITY_FLAG,
            "source_relative_path": None, "scan_index": None}


def _build_run(directory: str, name: str, run_name: str, members: list[tuple[int, str, Path, int]],
               by_rel: dict[str, tuple[Path, int]], limits: Limits, claimed: set[str], bare_scans: set[str],
               exp_taken: set[str], unparsed: list[dict], consumed: list[tuple[str, str]], *,
               with_companions: bool, fold: bool = False) -> GenericRun | None:
    """One run from one series of scan files (``name`` is the files' name, ``run_name`` the run's).
    ``with_companions`` False: no companion and no ``.exp`` reading (a bare series beside an ``_A`` one).
    ``fold``: companion names are compared without case (an ``_A`` series in a collision, found without case)."""
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
                "version": scan.version,
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
        return None
    indices = [s["scan_index"] for s in scans]
    gaps = sorted(set(range(min(indices), max(indices) + 1)) - set(indices))
    if gaps:
        anomalies.append(
            {"kind": "scan_index_gap", "locator": "run", "detail": f"scan indices {gaps} are absent between {min(indices)} and {max(indices)}", "severity": SEVERITY_NOTE, "source_relative_path": None, "scan_index": None}
        )
    keys = set().union(*per_scan_header) if per_scan_header else set()
    differences = sorted(k for k in keys if len({h.get(k) for h in per_scan_header}) > 1)
    companions = _companions(prefix, name, by_rel, limits, claimed, bare_scans, fold=fold) if with_companions else []
    for c in companions:
        consumed.append((c["relative_path"], c["role"]))
    own_exp = f"{prefix}{name}.exp"
    if fold:
        own_exp = next((c["relative_path"] for c in companions if c["relative_path"].casefold() == own_exp.casefold()), own_exp)
    data_file = _exp_data_file(own_exp, by_rel, companions) if with_companions else None
    if with_companions and data_file is None and own_exp not in by_rel:
        # r3a M1: a template `.exp` reused under another name (34 runs, each folder with its own copy of
        # `<template>_exp1.exp`): read when it is the ONLY `.exp` in the run's own folder, and kept only when its
        # DATA_FILE is the run's own name without its counter; the `.exp` file's own name is never a hint
        data_file = _folder_exp_data_file(prefix, name, by_rel, claimed, companions, limits, exp_taken)
        if data_file is not None and data_file["source_relative_path"] not in exp_taken:
            exp_taken.add(data_file["source_relative_path"])  # repeats in one folder share it: consumed once
            consumed.append((data_file["source_relative_path"], "experiment"))
    if data_file is not None:
        statements.append(data_file)
    return GenericRun(
        run_key=f"{PROFILE_ID}:{prefix}{run_name}",
        label=run_name,
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


def collect_generic(root: str | Path, limits: Limits = Limits()) -> GenericCollection:
    """Walk ``root`` and return runs, plus every numbered file that was not parsed and why."""
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("the source root must be an existing folder that is not a symlink")
    refused: list[dict] = []
    trunc: dict[str, int] = {}
    files = _walk(base, limits.archive, refused, trunc)
    result = collect_from_files(files, limits)
    return GenericCollection(runs=result.runs + result.late_runs, unparsed=result.unparsed, refused=refused,
                             truncation=trunc, files_seen=len(files))


def _companions(prefix: str, name: str, by_rel: dict[str, tuple[Path, int]], limits: Limits, claimed: set[str],
                scans: set[str] = frozenset(), *, fold: bool = False) -> list[dict]:
    """Context sources for one run: files in a same-named folder, a same-stem sibling with a
    companion extension, and the binary original of each scan in a sibling ``binary/`` folder.
    A bare ``NAME.NNN`` text scan of a run (``scans``) is never a companion. ``fold``: the run's
    name is compared without case (as a collision is found). Metadata and a digest only; nothing is parsed."""
    found: list[tuple[str, str]] = []
    key = (lambda t: t.casefold()) if fold else (lambda t: t)
    own_dir = key(f"{prefix}{name}/")
    for rel in by_rel:
        if rel in claimed or rel in scans:
            continue
        if key(rel).startswith(own_dir) and "/" not in rel[len(own_dir):]:
            ext = os.path.splitext(rel)[1].lower()
            found.append((rel, COMPANION_ROLES.get(ext, "other_context")))
        elif rel.startswith(prefix) and "/" not in rel[len(prefix):]:
            fname = rel[len(prefix):]
            stem, ext = os.path.splitext(fname)
            if key(stem) == key(name) and ext.lower() in COMPANION_ROLES:
                found.append((rel, COMPANION_ROLES[ext.lower()]))
        elif rel.startswith(f"{prefix}binary/") and "/" not in rel[len(prefix) + 7:]:
            m = _BINARY_NAME.match(rel[len(prefix) + 7:])
            if m and key(m.group("name")) == key(name):
                found.append((rel, "binary_original"))
    out: list[dict] = []
    for rel, role in sorted(found)[: limits.max_companions_per_run]:
        path, size = by_rel[rel]
        out.append({"relative_path": rel, "role": role, "size_bytes": size, "sha256": _sha256(path), "parsed": False})
    return out


#: Most bytes read from a run's own ``<name>.exp`` file (only its ``DATA_FILE`` line is taken).
MAX_EXP_BYTES = 64_000
#: ``DATA_FILE`` and its value: the acquisition's base name (the run name without its trailing ``_NNN``).
_EXP_DATA_FILE = re.compile(r"^\s*DATA_FILE(?:\s*[:=]\s*|\s+)(?P<value>\S(?:.*\S)?)\s*$")
#: c16-r L4: a terminal escape sequence, then any other control character, removed from the value
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _data_file_name(value: str) -> str:
    """The base name a ``DATA_FILE`` value writes: control characters removed (c16-r L4) and, for a path-like value
    (``C:\\xdc\\data\\01_SYNa.dat``, ``/data/01_SYNa.dat``), its last part without the extension."""
    text = _CONTROL_CHARS.sub("", _ANSI_ESCAPE.sub("", value)).strip()
    if "/" in text or "\\" in text:
        text = re.split(r"[/\\]", text)[-1]
        text = re.sub(r"\.[A-Za-z][A-Za-z0-9]{0,4}$", "", text)
    return text.strip()


def _exp_data_file(rel: str, by_rel: dict[str, tuple[Path, int]], companions: list[dict]) -> dict | None:
    """The ``DATA_FILE`` line of the run's own ``<name>.exp`` (a sibling with the run's name), as one statement
    (key ``exp_data_file``, the base name it writes, its line) — or ``None`` when there is no such file, it is too
    large, or no line names one. Nothing else in the file is read here (``EXPT_TYPE``, ``COMMENTS1-4`` are not); the
    companion is marked ``parsed`` only when the line was taken. A value of a known meaning, used ONLY to offer
    merge candidates by base name when it agrees with the run's own name (``grouping``): never a field value.
    c16-r L4: at most :data:`MAX_EXP_BYTES` + 1 bytes are read (more is too large, whatever the size said); lines end
    at CR, LF or CRLF; control characters are removed and a path-like value gives its base name."""
    companion = next((c for c in companions if c["relative_path"] == rel), None)
    if companion is None or rel not in by_rel or by_rel[rel][1] > MAX_EXP_BYTES:
        return None
    try:
        with by_rel[rel][0].open("rb") as fh:
            raw = fh.read(MAX_EXP_BYTES + 1)
    except OSError:
        return None
    if len(raw) > MAX_EXP_BYTES:
        return None
    for number, line in enumerate(re.split(r"\r\n|\r|\n", raw.decode("latin-1")), 1):
        m = _EXP_DATA_FILE.match(line)
        if m:
            value = _data_file_name(m.group("value")[:MAX_STATEMENT_CHARS])
            if not value:
                continue
            companion["parsed"] = True
            return {"key": "exp_data_file", "literal": value, "tokens": None, "locator": f"line:{number}",
                    "source_relative_path": rel, "scan_index": None}
    return None


def _folder_exp_data_file(prefix: str, name: str, by_rel: dict[str, tuple[Path, int]], claimed: set[str],
                          companions: list[dict], limits: Limits, taken: set[str]) -> dict | None:
    """r3a M1: the ``DATA_FILE`` of the ONE ``.exp`` in the run's own folder (the folder its scans are in, or a
    same-named folder beside them) when the run has no ``<name>.exp`` of its own — an experiment file reused as a
    template under another name. ``None`` when there are none or several there, or when its ``DATA_FILE`` is not
    the run's own name without its trailing counter (the folder's template then names another acquisition, and
    nothing is said about it). The ``.exp`` file's own name is never read as a hint. Read as
    :func:`_exp_data_file` reads, and the file becomes the ``experiment`` companion of the first run that takes it
    (``taken``: a folder's repeats share one)."""
    own_dir = f"{prefix}{name}/"
    found = sorted(rel for rel in by_rel
                   if os.path.splitext(rel)[1].lower() == ".exp"
                   and any(rel.startswith(d) and "/" not in rel[len(d):] for d in (prefix, own_dir)))
    if len(found) != 1 or found[0] in claimed:
        return None
    rel = found[0]
    companion = next((c for c in companions if c["relative_path"] == rel), None)
    probe = companion or {"relative_path": rel, "role": "experiment", "size_bytes": by_rel[rel][1], "parsed": False}
    got = _exp_data_file(rel, by_rel, [probe])
    if got is None or got["literal"].casefold() != re.sub(r"_\d+$", "", name).casefold():
        if companion is not None:
            companion["parsed"] = False
        return None
    if companion is None and rel not in taken and len(companions) < limits.max_companions_per_run:
        companions.append({**probe, "sha256": _sha256(by_rel[rel][0])})
    return got


def collect_generic_runs(root: str | Path, limits: Limits = Limits()) -> list[GenericRun]:
    """The runs :func:`collect_generic` finds, without the unparsed/refused detail."""
    return collect_generic(root, limits).runs

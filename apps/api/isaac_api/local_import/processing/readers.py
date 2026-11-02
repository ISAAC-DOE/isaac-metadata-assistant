"""Read the numeric columns of one scan file. Stdlib only; never raises on content.

Formats, chosen by CONTENT (never by extension):

* ``spec_columns`` — a SPEC-style block: column names from the LAST ``#L`` line before
  the data rows, exactly the convention ``bl15.signals.scan_channel_stats`` uses for the
  BL15-2 ``.dat``/``.txt`` exports (measured there: one scan block per file). A second
  ``#S`` block stops the read and is flagged. Asked for one scan (``scan=<#S number>``), a
  file of several ``#S`` blocks is read at that block only (a SPEC acquisition file whose run
  has no ``<stem>_dir`` exports; r5d H1); a file of one block is read whole, as before.
* ``ssrl_xdac`` — the SSRL "EXAFS Data Collector" text export (BL4-3, BL6-2, BL7-3): a
  free header, ``Data:``, one column name per line, a blank line, then rows.
* ``delimited_columns`` — a first non-numeric line of column names (tab or whitespace
  separated) followed by numeric rows (measured: a CR-line-ended three-column export).

Robustness rules, each producing a note rather than a silent change: CR-only and CRLF line
endings are normalised; a duplicate column name is kept with ``#2`` appended; a row whose
width differs from the header is skipped and counted; a non-numeric row is skipped and
counted.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

_L_LINE = re.compile(r"^#L[ \t]+(.*)$")
_S_LINE = re.compile(r"^#S\s")
_MAX_ROWS = 200_000
_MAX_BYTES = 64 * 1024 * 1024


@dataclass
class ScanTable:
    format_id: str | None
    labels: list[str] = field(default_factory=list)
    columns: dict[str, list[float]] = field(default_factory=dict)
    n_rows: int = 0
    notes: list[str] = field(default_factory=list)
    header_lines: list[str] = field(default_factory=list)
    error: str | None = None

    def has(self, name: str) -> bool:
        return name in self.columns


def _floats(parts: list[str]) -> list[float] | None:
    try:
        return [float(p) for p in parts]
    except ValueError:
        return None


def _dedupe(labels: list[str], notes: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for name in labels:
        if name in seen:
            seen[name] += 1
            new = f"{name}#{seen[name]}"
            notes.append(f"duplicate_column_label:{name}->{new}")
            out.append(new)
        else:
            seen[name] = 1
            out.append(name)
    return out


def _fill(table: ScanTable, labels: list[str], rows: list[list[float]], skipped_width: int, skipped_text: int) -> ScanTable:
    labels = _dedupe(labels, table.notes)
    table.labels = labels
    table.columns = {name: [r[i] for r in rows] for i, name in enumerate(labels)}
    table.n_rows = len(rows)
    if skipped_width:
        table.notes.append(f"rows_width_mismatch_skipped:{skipped_width}")
    if skipped_text:
        table.notes.append(f"rows_not_numeric_skipped:{skipped_text}")
    nonfinite = sum(1 for r in rows for v in r if not math.isfinite(v))
    if nonfinite:
        table.notes.append(f"nonfinite_values:{nonfinite}")
    return table


def _normalise_newlines(text: str, notes: list[str]) -> list[str]:
    if "\r" in text:
        if "\r\n" in text and "\r" not in text.replace("\r\n", ""):
            notes.append("crlf_line_endings")
        else:
            notes.append("cr_line_endings")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.split("\n")


def _spec_block(lines: list[str], scan: int, table: ScanTable) -> list[str] | None:
    """The lines of the ``#S <scan>`` block of a file of several ``#S`` blocks (``lines`` itself for a file of
    at most one); ``None`` with ``table.error`` set when no block, or more than one, has that number."""
    starts = [i for i, raw in enumerate(lines) if _S_LINE.match(raw.strip())]
    if len(starts) <= 1:
        return lines
    numbers = {i: lines[i].split()[1:2] for i in starts}
    hits = [i for i in starts if numbers[i] and numbers[i][0].isdigit() and int(numbers[i][0]) == scan]
    if len(hits) != 1:
        table.error = f"scan_number_repeated:{scan}" if hits else f"scan_not_in_file:{scan}"
        return None
    end = next((i for i in starts if i > hits[0]), len(lines))
    table.notes.append(f"scan_block_read:{scan}")
    return lines[hits[0]:end]


def _read_spec(lines: list[str], table: ScanTable, scan: int | None = None) -> ScanTable:
    if scan is not None:
        block = _spec_block(lines, scan, table)
        if block is None:
            return table
        lines = block
    labels: list[str] | None = None
    rows: list[list[float]] = []
    width = text = 0
    blocks = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if _S_LINE.match(line):
                blocks += 1
                if blocks > 1 and rows:
                    table.notes.append("multiple_scan_blocks_first_read")
                    break
            m = _L_LINE.match(line)
            if m:
                labels = m.group(1).split()
                rows = []
            elif len(table.header_lines) < 40:
                table.header_lines.append(line)
            continue
        if labels is None:
            continue
        vals = _floats(line.split())
        if vals is None:
            text += 1
            continue
        if len(vals) != len(labels):
            width += 1
            continue
        rows.append(vals)
        if len(rows) >= _MAX_ROWS:
            table.notes.append("row_limit_reached")
            break
    if labels is None:
        table.error = "no_column_labels"
        return table
    return _fill(table, labels, rows, width, text)


def _read_xdac(lines: list[str], table: ScanTable) -> ScanTable:
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "Data:")
    except StopIteration:
        table.error = "xdac_no_data_marker"
        return table
    table.header_lines = [ln.strip() for ln in lines[:start] if ln.strip()][:40]
    labels: list[str] = []
    i = start + 1
    while i < len(lines) and lines[i].strip():
        candidate = lines[i].strip()
        if _floats(candidate.split()) is not None:
            break
        labels.append(candidate)
        i += 1
    rows: list[list[float]] = []
    width = text = 0
    for raw in lines[i:]:
        line = raw.strip()
        if not line:
            continue
        vals = _floats(line.split())
        if vals is None:
            text += 1
            continue
        if len(vals) != len(labels):
            width += 1
            continue
        rows.append(vals)
        if len(rows) >= _MAX_ROWS:
            table.notes.append("row_limit_reached")
            break
    if not labels:
        table.error = "xdac_no_column_labels"
        return table
    return _fill(table, labels, rows, width, text)


def _read_delimited(lines: list[str], table: ScanTable) -> ScanTable:
    labels: list[str] | None = None
    rows: list[list[float]] = []
    width = text = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t") if "\t" in line else line.split()
        parts = [p.strip() for p in parts if p.strip()]
        vals = _floats(parts)
        if vals is None:
            if labels is None and not rows:
                labels = parts
            else:
                text += 1
            continue
        if labels is None:
            table.notes.append("no_header_columns_numbered")
            labels = [f"col{j + 1}" for j in range(len(vals))]
        if len(vals) != len(labels):
            width += 1
            continue
        rows.append(vals)
        if len(rows) >= _MAX_ROWS:
            table.notes.append("row_limit_reached")
            break
    if labels is None:
        table.error = "no_rows"
        return table
    return _fill(table, labels, rows, width, text)


def parse_text(text: str, scan: int | None = None) -> ScanTable:
    notes: list[str] = []
    if text.startswith("﻿"):
        text = text[1:]
        notes.append("bom_removed")
    lines = _normalise_newlines(text, notes)
    head = "\n".join(lines[:3])
    if "Data Collector" in head and head.lstrip().startswith("SSRL"):
        return _read_xdac(lines, ScanTable("ssrl_xdac", notes=notes))
    if any(_L_LINE.match(ln.strip()) for ln in lines[:400]):
        return _read_spec(lines, ScanTable("spec_columns", notes=notes), scan)
    return _read_delimited(lines, ScanTable("delimited_columns", notes=notes))


def table_from_columns(labels, columns, *, format_id: str, notes=None, header_lines=None) -> ScanTable:
    """Adapter for another reader's parsed scan (e.g. an XDC reader's ``XdcScan``):
    ``labels`` in order and ``columns`` {label: sequence of numbers}."""
    t = ScanTable(format_id, notes=list(notes or []), header_lines=list(header_lines or []))
    labels = list(labels)
    n = min((len(columns[c]) for c in labels), default=0)
    rows = [[float(columns[c][i]) for c in labels] for i in range(n)]
    return _fill(t, labels, rows, 0, 0)


def read_scan_file(path: Path, scan: int | None = None) -> ScanTable:
    try:
        size = path.stat().st_size
        if size > _MAX_BYTES:
            return ScanTable(None, error=f"file_too_large:{size}")
        data = path.read_bytes()
    except OSError as exc:
        return ScanTable(None, error=f"unreadable:{type(exc).__name__}")
    if b"\x00" in data[:4096]:
        # Measured: SSRL XDAC keeps a BINARY twin of every text export (``binary/x.001``).
        return ScanTable(None, error="binary_content")
    return parse_text(data.decode("utf-8", errors="replace"), scan)

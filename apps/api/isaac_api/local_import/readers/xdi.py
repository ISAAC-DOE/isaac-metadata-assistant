"""Reader for XDI/1.0 files, the way Athena and Demeter write their processed outputs.

These are the scientists' OWN processed outputs (``.nor``, ``.xmu``, ``.peak``, ``.nder``,
``.recon``, ``.pca`` ...). They are not raw data and ISAAC does not produce them; they are
read so a later step can compare ISAAC's own processing against them.

THE FORMAT, AS FAR AS THE REAL FILES SHOW (literal structure only)
==================================================================
Line 1 ``# XDI/1.0 <Application>/<version>`` (some files separate the words with tabs:
``#<tab>XDI/1.0<tab>Athena/0.9.26``). Then ``# Namespace.Key: value`` fields, among them
``# Column.N: name units``. A ``# ///`` line ends the fields and what follows up to the
``#-----`` separator is free-text comment. After the separator one ``#``-line names the
columns, and the numeric rows follow.

WHAT IS NOT DECIDED HERE
========================
``role_hints`` carries only what the file states about itself: the application named on line 1
(``processed_by``), the ``Demeter.output_filetype`` field if present, whether ``Athena.*``
fields are present, and the file's extension. Whether a spectrum is normalised, merged,
background-subtracted or anything else is NOT concluded from a column name or an extension.
Declared ``Column.N`` entries, the column-header line and the row width are compared and any
disagreement is flagged, not repaired.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._common import (
    MAX_ROWS,
    MAX_SCAN_BYTES,
    MAX_STATEMENT_CHARS,
    SEVERITY_FLAG,
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

PROFILE_ID = "xdi_v1"
READER_ID = "xdi_reader_v1"
READER_VERSION = "1.0.0"

_VERSION_LINE = re.compile(r"^#[ \t]+XDI/(?P<version>\d+\.\d+)(?:[ \t]+(?P<application>\S.*?))?[ \t]*$")
_FIELD = re.compile(r"^#[ \t]*(?P<ns>[A-Za-z][A-Za-z0-9_]*)\.(?P<key>[A-Za-z0-9_]+):[ \t]*(?P<value>.*?)[ \t]*$")
_SEPARATOR = re.compile(r"^#-{3,}")
_END_OF_FIELDS = re.compile(r"^#[ \t]*///[ \t]*$")
_COLUMN_KEY = re.compile(r"^\d+$")


def sniff(path: str | Path) -> bool:
    """True only for a first line of the form ``# XDI/<major>.<minor> [application]``."""
    head = head_bytes(Path(path), 512)
    if not head or b"\x00" in head:
        return False
    first = head.split(b"\n", 1)[0].split(b"\r", 1)[0]
    try:
        text = first.decode("ascii")
    except UnicodeDecodeError:
        return False
    return _VERSION_LINE.match(text) is not None


@dataclass
class XdiField:
    namespace: str
    key: str
    value: str
    line: int

    @property
    def locator(self) -> str:
        return f"line:{self.line}"


@dataclass
class XdiFile:
    version: str
    application_literal: str | None
    fields: list[XdiField]
    #: ``Column.N`` entries as declared: ``{N: "name units"}`` (literal).
    declared_columns: dict[int, str]
    comment_lines: list[HeaderLine]
    column_header: HeaderLine | None
    column_names: list[str]
    rows: list[list[float | None]]
    header_lines: list[HeaderLine]
    role_hints: dict[str, Any]
    anomalies: list[Anomaly] = field(default_factory=list)
    truncation: dict[str, int] = field(default_factory=dict)


def read(path: str | Path, *, max_bytes: int = MAX_SCAN_BYTES) -> XdiFile:
    """Parse one XDI file. Raises :class:`ValueError` only for a non-XDI file or one over the
    byte bound; every irregularity inside a real XDI file is an anomaly."""
    p = Path(path)
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"file is {size} bytes, over the {max_bytes}-byte bound")
    if not sniff(p):
        raise ValueError("not an XDI/1.0 file")
    lines = split_lines(p.read_bytes())
    anomalies: list[Anomaly] = []
    trunc: dict[str, int] = {}
    m = _VERSION_LINE.match(lines[0].rstrip())
    assert m is not None  # sniff() just matched it
    version, application = m.group("version"), m.group("application")
    header: list[HeaderLine] = [HeaderLine(1, "xdi_version", lines[0].strip())]

    fields: list[XdiField] = []
    declared: dict[int, str] = {}
    comments: list[HeaderLine] = []
    in_comment_block = False
    separator_at: int | None = None
    for i in range(1, len(lines)):
        line = lines[i]
        if _SEPARATOR.match(line):
            separator_at = i
            break
        if not line.startswith("#"):
            anomalies.append(Anomaly("no_separator", f"line:{i + 1}", "data began before a '#-----' separator line"))
            separator_at = None
            break
        if _END_OF_FIELDS.match(line):
            in_comment_block = True
            header.append(HeaderLine(i + 1, "end_of_fields_marker", line.strip()))
            continue
        if in_comment_block:
            text = clip(line[1:].strip(), MAX_STATEMENT_CHARS, trunc, "comment_chars_not_returned")
            if text:
                item = HeaderLine(i + 1, "comment", text)
                comments.append(item)
                header.append(item)
            continue
        fm = _FIELD.match(line)
        if fm is None:
            if line.strip("# \t"):
                anomalies.append(Anomaly("unrecognised_header_line", f"line:{i + 1}", "a header line is neither 'Namespace.key: value' nor a comment", SEVERITY_NOTE))
                header.append(HeaderLine(i + 1, "unrecognised_header_line", clip(line[1:].strip(), MAX_STATEMENT_CHARS, trunc, "header_chars_not_returned")))
            continue
        value = clip(fm.group("value"), MAX_STATEMENT_CHARS, trunc, "field_chars_not_returned")
        fld = XdiField(fm.group("ns"), fm.group("key"), value, i + 1)
        fields.append(fld)
        header.append(HeaderLine(i + 1, f"{fld.namespace}.{fld.key}", value))
        if fld.namespace == "Column" and _COLUMN_KEY.match(fld.key):
            number = int(fld.key)
            if number in declared:
                anomalies.append(Anomaly("duplicate_column_declaration", f"line:{i + 1}", f"Column.{number} is declared more than once"))
            declared[number] = value

    column_header: HeaderLine | None = None
    names: list[str] = []
    rows: list[list[float | None]] = []
    if separator_at is None:
        # data started without a separator (flagged above) or the file ended in the header
        data_start = next((i for i, ln in enumerate(lines) if i > 0 and ln.strip() and not ln.startswith("#")), None)
        if data_start is None:
            anomalies.append(Anomaly("no_data", "line:1", "no data rows were found"))
    else:
        data_start = separator_at + 1
        if data_start < len(lines) and lines[data_start].startswith("#"):
            raw = lines[data_start][1:].strip()
            names = raw.split()
            column_header = HeaderLine(data_start + 1, "column_names", raw, list(names))
            header.append(column_header)
            data_start += 1
        else:
            anomalies.append(Anomaly("no_column_header", f"line:{data_start + 1}", "no '#' column-header line follows the separator"))
    row_first_line = None
    if data_start is not None:
        for j in range(data_start, len(lines)):
            ln = lines[j]
            if not ln.strip():
                continue
            if ln.lstrip().startswith("#"):
                anomalies.append(Anomaly("comment_inside_data", f"line:{j + 1}", "a '#' line appears among the data rows; it is not read as data", SEVERITY_NOTE))
                continue
            if row_first_line is None:
                row_first_line = j + 1
            if len(rows) >= MAX_ROWS:
                trunc["rows_not_returned"] = trunc.get("rows_not_returned", 0) + 1
                continue
            row: list[float | None] = []
            for col, token in enumerate(ln.split()):
                try:
                    row.append(float(token))
                except ValueError:
                    row.append(None)
                    anomalies.append(Anomaly("non_numeric_cell", f"line:{j + 1}", f"column {col + 1} of this row is not a number; the cell is kept as null"))
            rows.append(row)
        if not rows:
            anomalies.append(Anomaly("no_data", f"line:{data_start + 1}", "no data rows were found"))
    widths = {len(r) for r in rows}
    if rows and len(widths) > 1:
        anomalies.append(Anomaly("row_width_varies", f"line:{row_first_line}", f"data rows have {sorted(widths)} cells"))
    width = max(widths) if widths else 0
    if names and rows and width != len(names):
        anomalies.append(Anomaly("column_count_mismatch", column_header.locator if column_header else "line:1", f"the column-header line names {len(names)} columns and the rows have {width}"))
    if declared and rows and max(declared) != width:
        anomalies.append(Anomaly("declared_columns_differ", "line:1", f"the highest Column.N declared is {max(declared)} and the rows have {width} columns"))
    if declared and sorted(declared) != list(range(1, max(declared) + 1)):
        anomalies.append(Anomaly("declared_column_numbers_not_contiguous", "line:1", "Column.N numbers declared are not 1..N without gaps", SEVERITY_NOTE))

    app_name, app_version = (None, None)
    if application:
        app_name, _, rest = application.partition("/")
        app_version = rest or None
    output_filetype = next((f.value for f in fields if f.namespace == "Demeter" and f.key == "output_filetype"), None)
    hints: dict[str, Any] = {
        "processed_by": app_name,
        "application_version": app_version,
        "demeter_output_filetype": output_filetype,
        "has_athena_fields": any(f.namespace == "Athena" for f in fields),
        "extension": p.suffix.lower() or None,
    }
    return XdiFile(
        version=version,
        application_literal=application,
        fields=fields,
        declared_columns=declared,
        comment_lines=comments,
        column_header=column_header,
        column_names=names,
        rows=rows,
        header_lines=header,
        role_hints=hints,
        anomalies=anomalies,
        truncation=trunc,
    )


# --- collecting -----------------------------------------------------------------------------


def collect_from_files(files: list[FileEntry], limits: Limits = Limits(), claimed: set[str] | None = None) -> ReaderResult:
    """Group XDI files by directory and name stem (``<stem>.nor``, ``<stem>.xmu`` ... are one
    group). Pure data; nothing is written."""
    claimed = claimed or set()
    groups: dict[tuple[str, str], list[tuple[str, Path, int]]] = {}
    unparsed: list[dict] = []
    for rel, path, size in files:
        if rel in claimed:
            continue
        if not sniff(path):
            continue
        if size > min(limits.max_scan_bytes, limits.archive.max_entry_bytes):
            unparsed.append({"relative_path": rel, "reason_code": "file_too_large", "size_bytes": size})
            continue
        directory, _, fname = rel.rpartition("/")
        stem = os.path.splitext(fname)[0]
        groups.setdefault((directory, stem), []).append((rel, path, size))
    runs: list[GenericRun] = []
    consumed: list[tuple[str, str]] = []
    for (directory, stem), members in sorted(groups.items()):
        prefix = f"{directory}/" if directory else ""
        scans: list[dict] = []
        statements: list[dict] = []
        anomalies: list[dict] = []
        hints_by_file: dict[str, dict] = {}
        for rel, path, size in sorted(members):
            try:
                xdi = read(path, max_bytes=limits.max_scan_bytes)
            except (ValueError, OSError) as exc:
                unparsed.append({"relative_path": rel, "reason_code": "read_failed", "size_bytes": size, "detail": type(exc).__name__})
                continue
            consumed.append((rel, "processed_output"))
            scans.append(
                {
                    "relative_path": rel,
                    "sha256": sha256_file(path),
                    "size_bytes": size,
                    "scan_index": None,
                    "extension": path.suffix.lower(),
                    "columns": list(xdi.column_names),
                    "points": len(xdi.rows),
                    "xdi_version": xdi.version,
                    "declared_columns": {str(k): v for k, v in sorted(xdi.declared_columns.items())},
                    "role_hints": xdi.role_hints,
                    "truncation": dict(xdi.truncation),
                }
            )
            hints_by_file[rel] = xdi.role_hints
            statements.extend(statements_from(xdi.header_lines, rel, None))
            for a in xdi.anomalies:
                anomalies.append({**a.to_dict(), "source_relative_path": rel, "scan_index": None})
        if not scans:
            continue
        runs.append(
            GenericRun(
                run_key=f"{PROFILE_ID}:{prefix}{stem}",
                label=stem,
                profile=PROFILE_ID,
                directory=directory,
                scans=scans,
                companions=[],
                statements=statements,
                anomalies=anomalies,
                header_differences=[],
                scan_indices=[],
                reader_id=READER_ID,
                role_hints={
                    "processed_by": sorted({h["processed_by"] for h in hints_by_file.values() if h["processed_by"]}),
                    "extensions": sorted({h["extension"] for h in hints_by_file.values() if h["extension"]}),
                    "kind": "processed_output_of_the_scientist",
                },
            )
        )
    return ReaderResult(runs=runs, unparsed=unparsed, consumed=consumed)


def collect_processed_outputs(root: str | Path, limits: Limits = Limits()) -> list[GenericRun]:
    """Every XDI file under ``root``, with relative path and sha256, grouped by name stem.

    These are the scientists' own processed outputs, offered to whatever compares ISAAC's
    processing against them. ``.prj`` project files are not XDI and are not touched here."""
    from ._common import walk

    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("the source root must be an existing folder that is not a symlink")
    files = walk(base, limits.archive, [], {})
    return collect_from_files(files, limits).runs

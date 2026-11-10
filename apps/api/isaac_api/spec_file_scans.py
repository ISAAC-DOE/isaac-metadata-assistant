"""The scans kept inside a SPEC file itself: ONE splitter, shared by the import rule and the HERFD selector.

The engine takes a SPEC run's scans from its `<stem>_dir/` folder of one-scan exports. Some runs have no
such folder, or an empty one: their scans exist only as `#S` blocks of the SPEC file. Such a run's scans are
then those blocks: each energy scan (`gscan`, the command `bl15.spec.gscan_grid` reads as an energy grid)
with at least one data row and a `#S` number used once in the file. Every other block is named and left out.

Two consumers split a file with the functions here, so they cannot disagree about which blocks are scans:

* the local import's rule :data:`SPEC_FILE_SCANS_RULE_ID` (``local_import.bundle.build_bundle``), which lists
  the blocks as the run's scans (``{relative_path: <the SPEC file>, scan_index: <its #S number>}``);
* the HERFD channel selector's inputs (``historical_import``), which reads one ``bl15.signals.scan_channel_stats``
  per listed block when the run has no `_dir` exports to read.

Pure text in, plain values out. Nothing here reads a file.
"""

from __future__ import annotations

import re
from typing import Container

#: The rule that lists a SPEC file's own `#S` blocks as its run's scans.
SPEC_FILE_SCANS_RULE_ID = "spec_file_energy_scans_v1"
#: A `#S` command that is an energy scan (its first word).
SPEC_ENERGY_SCAN_COMMANDS = frozenset({"gscan"})
_SPEC_S_LINE = re.compile(r"^#S[ \t]+(\S+)[ \t]*(.*)$")
#: A `#S` number: ASCII digits only (``str.isdigit`` accepts ``²``, which ``int`` refuses).
_ASCII_NUMBER = re.compile(r"[0-9]+")

#: Source types whose SPEC file's own scans are listed when no `_dir` export exists: a run-candidate SPEC
#: acquisition, and a standard or reference measurement (a reference pellet). An alignment file is NOT one: its
#: scans are positioning scans, and it stays at its `_dir` count.
_SPEC_ACQUISITION = "spec_acquisition"
_STANDARD_OR_REFERENCE = "standard_or_reference"


def lists_in_file_scans(source_type: str | None, run_candidate: bool) -> bool:
    """Whether a unit of this source type may have its SPEC file's own `#S` energy scans listed as its scans."""
    return (bool(run_candidate) and source_type == _SPEC_ACQUISITION) or source_type == _STANDARD_OR_REFERENCE


def _split(text: str) -> tuple[list[str], list[dict]]:
    """``(lines, blocks)``: each block ``{literal, command, rows, start, end}`` (line indices, ``end`` exclusive)."""
    lines = text.lstrip("﻿").splitlines()
    blocks: list[dict] = []
    for i, line in enumerate(lines):
        m = _SPEC_S_LINE.match(line)
        if m:
            if blocks:
                blocks[-1]["end"] = i
            blocks.append({"literal": m.group(1), "command": m.group(2).strip(), "rows": 0, "start": i, "end": len(lines)})
        elif blocks and line.strip() and not line.startswith("#"):
            blocks[-1]["rows"] += 1
    return lines, blocks


def _judge(blocks: list[dict]) -> tuple[list[tuple[int, dict]], list[dict]]:
    """``(kept [(number, block)], left out [{scan, command, why}])``, in file order."""
    numbers = [int(b["literal"]) if _ASCII_NUMBER.fullmatch(b["literal"]) else None for b in blocks]
    seen: dict[int, int] = {}
    for n in numbers:
        if n is not None:
            seen[n] = seen.get(n, 0) + 1
    kept: list[tuple[int, dict]] = []
    left_out: list[dict] = []
    for b, n in zip(blocks, numbers):
        word = b["command"].split()[0] if b["command"] else ""
        if n is None:
            why = "its #S number is not a number"
        elif seen[n] > 1:
            why = "its #S number appears more than once in the file, so it names no single scan"
        elif word not in SPEC_ENERGY_SCAN_COMMANDS:
            why = f"not an energy scan ({word or 'no command'})"
        elif not b["rows"]:
            why = "no data rows"
        else:
            kept.append((n, b))
            continue
        left_out.append({"scan": b["literal"], "command": word or None, "why": why})
    return kept, left_out


def spec_file_scans(text: str) -> tuple[list[int], list[dict]]:
    """``(scan numbers, left out)`` of one SPEC file's own ``#S`` blocks (:data:`SPEC_FILE_SCANS_RULE_ID`).

    A scan is an energy scan (:data:`SPEC_ENERGY_SCAN_COMMANDS`) with at least one data row whose ``#S``
    number appears once. Each other block is in ``left out`` as ``{scan, command, why}``."""
    kept, left_out = _judge(_split(text)[1])
    return [n for n, _ in kept], left_out


def spec_file_scan_blocks(text: str) -> list[tuple[int, str]]:
    """``[(#S number, that block's text)]`` for exactly the scans :func:`spec_file_scans` lists, in file order.

    A block runs from its ``#S`` line up to the next ``#S`` line (or the end of the file), the same span
    ``local_import.processing.readers`` reads for one ``scan_index``."""
    lines, blocks = _split(text)
    kept, _ = _judge(blocks)
    return [(n, "\n".join(lines[b["start"]:b["end"]]) + "\n") for n, b in kept]


def exported_copy_of(stem: str, stems: Container[str]) -> str | None:
    """The run ``stem`` names an exported copy of (``SYN_A.dat`` beside a run ``SYN_A``: grouping's
    ``exported_file_read_as_acquisition`` rule), else ``None``. Such a copy lists no in-file scans of its own."""
    from .local_import.grouping import _EXPORT_EXT  # local: grouping imports bundle

    m = _EXPORT_EXT.match(str(stem or ""))
    return m.group("base") if m and m.group("base") in stems and m.group("base") != stem else None

"""Reader for Igor Pro packed experiments (``.pxp``): the text and the wave names it holds.

A ``.pxp`` is a scientist's ANALYSIS file. It is never a run, never a record group and never a
processed output. This reader walks the file's RECORDS and returns bounded, verbatim statements
as evidence (:class:`~._common.AnalysisFile`); the bundle holds them as ``extended_context[]``
entries and does nothing else with them. Pure Python, standard library only (no ``igor2``), and
NOTHING IN IT EVER EXECUTES what it reads: procedure text is read as text. A wave's DATA is not
read at all, only its name and its note.

THE FORMAT (Igor Pro Technical Note PTN003 "Igor File Formats", checked against a real file)
============================================================================================
A packed experiment is a sequence of records, each ``<header><data>``. The header is 8 bytes,
``uint16 recordType, int16 version, int32 numDataBytes`` in the file's byte order (little-endian
from Windows and Intel Macs, big-endian from old PowerPC Macs; this reader tries both on the
first header and refuses the file if neither is plausible). The high bit of ``recordType`` is a
flag and is masked off. Types this reader uses:

=====  ====================================================================================
type   handled as
=====  ====================================================================================
2      history: the experiment's command history (text)
4      recreation macros (text)
5      procedure window text
8      a packed FILE (a notebook or procedure file kept inside the experiment). Only the
       layout observed in a real file is read: ``int32`` data-fork length at byte 22, the
       file's text starting at byte 154, a 4-character type code at byte 4 and a name at byte
       32. Anything that does not match that layout, or whose text is not text, is SKIPPED
       and counted (``packed_file_unrecognised``), never guessed
3      a wave. The wave format version is the first ``int16`` of the record DATA (the
       record header's own version field is 0 in the real file). Versions 5 (name at byte 92,
       note at ``64 + wfmSize + formulaSize``) is read; versions 2 and 3 are read for the
       name and the note by the same documented offsets; others are skipped and counted
9 / 10 data folder start / end: their names give each wave its folder path
=====  ====================================================================================

Every other record type is counted by type in the summary and skipped.

WHAT IS STORED (``concept``, verbatim ``literal``, ``locator``)
===============================================================
* ``igor.history_line``  one non-empty history line, clipped at 500 characters, ``history line N``
* ``igor.recreation_macros`` / ``igor.procedure_text`` / ``igor.packed_file_text``: one entry per
  text record, clipped at 8,000 characters, ``record N (procedure)`` etc.
* ``igor.packed_file_name`` / ``igor.packed_file_type`` the stated name and 4-character type code
* ``igor.data_folder``   a data folder's name, ``record N (data folder start)``
* ``igor.wave``          a wave's name, ``record N (wave, data folder root:...)``
* ``igor.wave_note``     a wave's note text, clipped at 1,000 characters, ``record N (wave note)``
* ``igor.reader_summary`` the reader's own counts, caps and skips, as JSON

TEXT ENCODING: UTF-8 when the bytes are valid UTF-8; otherwise the experiment's own platform
decides, read from the recreation macros' header line (``Platform=Windows`` -> cp1252, anything
else -> mac_roman, which Igor Pro before version 7 wrote on a Mac). Which was used is stated in
the summary. Lines break on CR, LF or CRLF.

BOUNDS (stated in every file's summary entry)
=============================================
at most 100,000 records walked; a record whose length is negative or runs past the end of the
file ends the walk (counted as ``malformed_length``, what was read before it is kept); at most
1 MiB read of any one text record and 16 MiB of text in all; at most 5,000 history lines,
5,000 waves, 1,000 wave notes and 5,000 data folders stored; a file over 256 MiB, or one whose
first header is not plausible, is refused with the reason.
"""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any

from ._common import MAX_ANALYSIS_ENTRIES_TOTAL, AnalysisFile, Limits, clip_literal

READER_ID = "igor_pxp_v1"
READER_VERSION = "1.0.0"
KIND = "igor_experiment"
EXTENSION = ".pxp"

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_RECORDS = 100_000
MAX_TEXT_RECORD_BYTES = 1 << 20
MAX_TEXT_TOTAL_BYTES = 16 << 20
MAX_HISTORY_LINES = 5_000
MAX_WAVES = 5_000
MAX_WAVE_NOTES = 1_000
MAX_FOLDERS = 5_000
MAX_HISTORY_LINE_CHARS = 500
MAX_TEXT_RECORD_CHARS = 8_000
MAX_NOTE_CHARS = 1_000
MAX_NAME_CHARS = 255
#: Deepest data-folder nesting tracked. Igor itself nests a handful; a crafted file can nest
#: 10^5 and make every wave's folder path a megabyte, so the stack is capped and the overflow counted.
MAX_FOLDER_DEPTH = 64
#: Characters of a folder path kept in a locator (the path is clipped, with a marker).
MAX_FOLDER_PATH_CHARS = 200

REC_HISTORY = 2
REC_WAVE = 3
REC_RECREATION = 4
REC_PROCEDURE = 5
REC_PACKED_FILE = 8
REC_FOLDER_START = 9
REC_FOLDER_END = 10
_TEXT_KIND = {REC_RECREATION: "recreation_macros", REC_PROCEDURE: "procedure_text"}
_TEXT_LABEL = {REC_RECREATION: "recreation macros", REC_PROCEDURE: "procedure", REC_PACKED_FILE: "packed file"}

_PACKED_FILE_TEXT_START = 154
_PACKED_FILE_FORK_LENGTH_AT = 22
_PACKED_FILE_NAME_AT = 32
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def sniff(relative_path: str) -> bool:
    return relative_path.lower().endswith(EXTENSION)


def _printable_ratio(data: bytes) -> float:
    if not data:
        return 1.0
    good = sum(1 for c in data if 32 <= c < 127 or c in (9, 10, 13) or c >= 128)
    return good / len(data)


def _cstring(data: bytes) -> str:
    raw = data.split(b"\x00", 1)[0][:MAX_NAME_CHARS]
    return raw.decode("latin-1")


def _plausible_name(name: str) -> bool:
    return bool(name) and all(32 <= ord(c) < 127 or ord(c) >= 160 for c in name)


def _detect_byte_order(head: bytes, size: int) -> str | None:
    for order in ("<", ">"):
        record_type, _version, length = struct.unpack(order + "Hhi", head)
        if (record_type & 0x7FFF) <= 0x7F and 0 <= length <= size - 8:
            return order
    return None


def _wave_fields(data: bytes, order: str) -> tuple[str | None, bytes | None, bool]:
    """``(name, note, recognised)`` for one wave record's data. Never raises."""
    if len(data) < 2:
        return None, None, False
    version = struct.unpack_from(order + "h", data, 0)[0]
    try:
        if version == 5 and len(data) >= 124:
            wfm, formula, note_size = struct.unpack_from(order + "iii", data, 4)
            name = _cstring(data[92:124])
            start = 64 + wfm + formula
            note = None
            if note_size > 0 and wfm >= 0 and formula >= 0 and start + note_size <= len(data):
                chunk = data[start : start + note_size]
                if _printable_ratio(chunk) >= 0.9:
                    note = chunk
            return (name if _plausible_name(name) else None), note, True
        if version == 3 and len(data) >= 46:
            wfm, note_size, formula = struct.unpack_from(order + "iii", data, 2)
            name = _cstring(data[26:46])
            start = 20 + wfm + formula
            note = None
            if note_size > 0 and wfm >= 0 and formula >= 0 and start + note_size <= len(data):
                chunk = data[start : start + note_size]
                if _printable_ratio(chunk) >= 0.9:
                    note = chunk
            return (name if _plausible_name(name) else None), note, True
        if version == 2 and len(data) >= 42:
            wfm, note_size = struct.unpack_from(order + "ii", data, 2)
            name = _cstring(data[22:42])
            start = 16 + wfm
            note = None
            if note_size > 0 and wfm >= 0 and start + note_size <= len(data):
                chunk = data[start : start + note_size]
                if _printable_ratio(chunk) >= 0.9:
                    note = chunk
            return (name if _plausible_name(name) else None), note, True
    except struct.error:
        return None, None, False
    return None, None, False


def _packed_file(data: bytes, order: str) -> tuple[str | None, str | None, bytes | None]:
    """``(name, type code, text bytes)`` for a packed-file record laid out as observed."""
    if len(data) <= _PACKED_FILE_TEXT_START:
        return None, None, None
    fork = struct.unpack_from(order + "i", data, _PACKED_FILE_FORK_LENGTH_AT)[0]
    if not (0 < fork <= len(data) - _PACKED_FILE_TEXT_START):
        return None, None, None
    text = data[_PACKED_FILE_TEXT_START : _PACKED_FILE_TEXT_START + fork]
    if _printable_ratio(text) < 0.9 or b"\x00" in text:
        return None, None, None
    name = _cstring(data[_PACKED_FILE_NAME_AT : _PACKED_FILE_NAME_AT + 32])
    code = data[4:8].decode("latin-1")
    return (name if _plausible_name(name) else None), (code if _plausible_name(code) else None), text


def read(
    path: Path,
    relative_path: str,
    limits: Limits = Limits(),
    entry_budget: int = MAX_ANALYSIS_ENTRIES_TOTAL,
) -> AnalysisFile:
    """Read one ``.pxp`` into an :class:`AnalysisFile`. Never raises for a bad file."""
    result = AnalysisFile(relative_path=relative_path, reader_id=READER_ID, kind=KIND)
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            result.refused_reason = f"the file is {size} bytes; the reader's ceiling is {MAX_FILE_BYTES}"
            return result
        fh = path.open("rb")
    except OSError as exc:
        result.refused_reason = f"the file could not be read ({type(exc).__name__})"
        return result

    type_counts: dict[int, int] = {}
    skipped_types: dict[int, int] = {}
    wave_unrecognised = packed_unrecognised = malformed_length = 0
    records = 0
    folder_stack: list[str] = []
    folder_overflow_total = 0
    folder_overflow = 0  # folder starts past MAX_FOLDER_DEPTH, paired off by later ends
    folder_path = "root"  # the clipped path of the current folder, kept up to date on push/pop

    def refresh_path() -> str:
        text = "root:" + ":".join(folder_stack) if folder_stack else "root"
        clipped, _ = clip_literal(text, MAX_FOLDER_PATH_CHARS)
        return clipped

    folders: list[dict] = []
    waves: list[dict] = []
    notes: list[dict] = []
    texts: list[tuple[int, int, bytes]] = []  # (record number, type, bytes)
    packed: list[tuple[int, str | None, str | None, bytes]] = []
    text_bytes_read = 0
    text_truncated = 0
    dropped = {"waves": 0, "wave_notes": 0, "folders": 0, "history_lines": 0}
    stopped_by: str | None = None
    try:
        with fh:
            head = fh.read(8)
            if len(head) < 8:
                result.refused_reason = "the file is shorter than one record header"
                return result
            order = _detect_byte_order(head, size)
            if order is None:
                result.refused_reason = (
                    "the first record header is not valid in either byte order, so this is "
                    "not an Igor packed experiment this reader can open"
                )
                return result
            fh.seek(0)
            offset = 0
            while offset + 8 <= size:
                if records >= MAX_RECORDS:
                    stopped_by = "max_records"
                    break
                fh.seek(offset)
                header = fh.read(8)
                if len(header) < 8:
                    break
                raw_type, _version, length = struct.unpack(order + "Hhi", header)
                if length < 0 or offset + 8 + length > size:
                    malformed_length += 1
                    stopped_by = "malformed_length"
                    break
                records += 1
                rtype = raw_type & 0x7FFF
                type_counts[rtype] = type_counts.get(rtype, 0) + 1
                number = records
                if rtype in (REC_HISTORY, REC_RECREATION, REC_PROCEDURE, REC_PACKED_FILE):
                    want = min(length, MAX_TEXT_RECORD_BYTES + (_PACKED_FILE_TEXT_START if rtype == REC_PACKED_FILE else 0))
                    room = MAX_TEXT_TOTAL_BYTES - text_bytes_read
                    if room <= 0:
                        skipped_types[rtype] = skipped_types.get(rtype, 0) + 1
                    else:
                        want = min(want, room)
                        body = fh.read(want)
                        text_bytes_read += len(body)
                        text_truncated += int(want < length)
                        if rtype == REC_PACKED_FILE:
                            name, code, text = _packed_file(body, order)
                            if text is None:
                                packed_unrecognised += 1
                            else:
                                packed.append((number, name, code, text))
                        else:
                            texts.append((number, rtype, body))
                elif rtype == REC_WAVE:
                    body = fh.read(min(length, 1 << 22))
                    name, note, recognised = _wave_fields(body, order)
                    if not recognised or name is None:
                        wave_unrecognised += 1
                    else:
                        if len(waves) < MAX_WAVES:
                            waves.append({"number": number, "name": name, "folder": folder_path})
                        else:
                            dropped["waves"] += 1
                        if note:
                            if len(notes) < MAX_WAVE_NOTES:
                                notes.append({"number": number, "note": note})
                            else:
                                dropped["wave_notes"] += 1
                elif rtype == REC_FOLDER_START:
                    body = fh.read(min(length, 256))
                    name = _cstring(body)
                    shown = name if _plausible_name(name) else "?"
                    if shown == "?":
                        skipped_types[rtype] = skipped_types.get(rtype, 0) + 1
                    if len(folder_stack) >= MAX_FOLDER_DEPTH:
                        folder_overflow += 1
                        folder_overflow_total += 1
                    else:
                        folder_stack.append(shown)
                        folder_path = refresh_path()
                    if shown != "?":
                        if len(folders) < MAX_FOLDERS:
                            folders.append({"number": number, "name": name})
                        else:
                            dropped["folders"] += 1
                elif rtype == REC_FOLDER_END:
                    if folder_overflow:
                        folder_overflow -= 1
                    elif folder_stack:
                        folder_stack.pop()
                        folder_path = refresh_path()
                else:
                    skipped_types[rtype] = skipped_types.get(rtype, 0) + 1
                offset += 8 + length
    except (OSError, struct.error) as exc:
        stopped_by = f"io_error:{type(exc).__name__}"

    if records == 0:
        result.refused_reason = "no record could be read from this file"
        return result

    # ---- text decoding: UTF-8 if valid, else the platform the macros state --------------------
    platform_windows = any(
        rtype == REC_RECREATION and b"Platform=Windows" in body[:400] for _n, rtype, body in texts
    )

    def decode(data: bytes) -> tuple[str, str]:
        try:
            return data.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            codec = "cp1252" if platform_windows else "mac_roman"
            return data.decode(codec, errors="replace"), codec

    entries: list[dict] = []
    encodings: dict[str, int] = {}
    history_seen = 0
    history_total_lines = 0
    history_kept = 0
    text_records_clipped = 0
    for number, rtype, body in texts:
        text, enc = decode(body)
        encodings[enc] = encodings.get(enc, 0) + 1
        if rtype == REC_HISTORY:
            history_seen += 1
            suffix = "" if history_seen == 1 else f" (record {number})"
            for k, line in enumerate(_LINE_BREAK.split(text), 1):
                if not line.strip():
                    continue
                history_total_lines += 1
                if history_kept >= MAX_HISTORY_LINES:
                    dropped["history_lines"] += 1
                    continue
                history_kept += 1
                literal, _ = clip_literal(line, MAX_HISTORY_LINE_CHARS)
                entries.append({"concept": "igor.history_line", "literal": literal, "locator": f"history line {k}{suffix}"})
        else:
            literal, clipped = clip_literal(text, MAX_TEXT_RECORD_CHARS)
            text_records_clipped += int(clipped)
            entries.append(
                {
                    "concept": f"igor.{_TEXT_KIND[rtype]}",
                    "literal": literal,
                    "locator": f"record {number} ({_TEXT_LABEL[rtype]})",
                }
            )
    for number, name, code, body in packed:
        text, enc = decode(body)
        encodings[enc] = encodings.get(enc, 0) + 1
        label = f"record {number} ({_TEXT_LABEL[REC_PACKED_FILE]})"
        if name:
            entries.append({"concept": "igor.packed_file_name", "literal": name, "locator": label})
        if code:
            entries.append({"concept": "igor.packed_file_type", "literal": code, "locator": label})
        literal, clipped = clip_literal(text, MAX_TEXT_RECORD_CHARS)
        text_records_clipped += int(clipped)
        entries.append({"concept": "igor.packed_file_text", "literal": literal, "locator": label})
    for folder in folders:
        entries.append({"concept": "igor.data_folder", "literal": folder["name"], "locator": f"record {folder['number']} (data folder start)"})
    for wave in waves:
        entries.append(
            {
                "concept": "igor.wave",
                "literal": wave["name"],
                "locator": f"record {wave['number']} (wave, data folder {wave['folder']})",
            }
        )
    for note in notes:
        text, enc = decode(note["note"])
        literal, _ = clip_literal(text, MAX_NOTE_CHARS)
        entries.append({"concept": "igor.wave_note", "literal": literal, "locator": f"record {note['number']} (wave note)"})

    room = max(entry_budget - 1, 0)
    budget_dropped = max(len(entries) - room, 0)
    kept = entries[:room]
    counts: dict[str, Any] = {
        "byte_order": "little-endian" if order == "<" else "big-endian",
        "records_walked": records,
        "record_types": {str(k): v for k, v in sorted(type_counts.items())},
        "record_types_skipped": {str(k): v for k, v in sorted(skipped_types.items())},
        "stopped_by": stopped_by,
        "malformed_length": malformed_length,
        "text_encodings": encodings,
        "history_lines_total": history_total_lines,
        "history_lines_kept": history_kept,
        "text_records": len(texts) - history_seen + len(packed),
        "text_records_clipped": text_records_clipped,
        "text_records_read_short": text_truncated,
        "packed_file_unrecognised": packed_unrecognised,
        "waves_kept": len(waves),
        "wave_records_unrecognised": wave_unrecognised,
        "wave_notes_kept": len(notes),
        "data_folders_kept": len(folders),
        "folder_starts_past_depth_cap": folder_overflow_total,
        "caps": {
            "records": MAX_RECORDS,
            "text_record_bytes": MAX_TEXT_RECORD_BYTES,
            "history_lines": MAX_HISTORY_LINES,
            "history_line_chars": MAX_HISTORY_LINE_CHARS,
            "text_record_chars": MAX_TEXT_RECORD_CHARS,
            "waves": MAX_WAVES,
            "folder_depth": MAX_FOLDER_DEPTH,
            "folder_path_chars": MAX_FOLDER_PATH_CHARS,
            "wave_notes": MAX_WAVE_NOTES,
            "wave_note_chars": MAX_NOTE_CHARS,
            "entries_for_this_file": entry_budget,
        },
        "dropped_for_a_cap": {**dropped, "file_budget": budget_dropped},
    }
    result.counts = counts
    result.skipped_total = (
        sum(skipped_types.values()) + wave_unrecognised + packed_unrecognised + malformed_length
    )
    result.suppressed_total = sum(dropped.values()) + budget_dropped + text_truncated
    summary = {
        "concept": "igor.reader_summary",
        "literal": json.dumps({"reader": READER_ID, **counts}, sort_keys=True, ensure_ascii=False),
        "locator": "file",
    }
    result.entries = [summary, *kept]
    return result

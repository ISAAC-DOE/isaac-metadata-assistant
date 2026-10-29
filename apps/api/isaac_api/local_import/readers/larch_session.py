"""Reader for Larch session files (``.larix``): what an analysis session STATES.

A ``.larix`` is a scientist's ANALYSIS file. It is never a run, never a record group and never
a processed output: nothing here becomes one. The reader returns bounded, verbatim statements
as evidence (:class:`~._common.AnalysisFile`); the bundle holds them as ``extended_context[]``
entries and does nothing else with them. NOTHING IN THIS MODULE EVER EXECUTES OR EVALUATES
what it reads: the session's command history is Larch (Python-like) source and is read as TEXT,
split into statements by bracket and quote balance, never by ``eval``, ``exec``, ``ast`` or
``import``. Standard library only.

THE FORMAT, FROM THE REAL FILES (literal structure only)
========================================================
Measured on two real sessions (a Larch 2025.2.0 save, ~10 MB of text in ~3 MB of gzip):

* the file is **gzip-compressed UTF-8 text** (magic ``1f 8b``). A file that is plain text and
  starts with ``##LARIX:`` is accepted as well; anything else is refused;
* line 1 is ``##LARIX: <version>  Larch Session File``; line 2 ``##Date Saved: <timestamp>``;
* ``##<CONFIG>`` ... ``##</CONFIG>`` holds ``##<Key>: <value>`` lines (machine, Python and Larch
  versions, and a few absolute paths of the saving user's profile);
* ``##<Session Commands>`` ... ``##</Session Commands>`` is the command history, one Larch
  statement per logical line, continuation lines indented (a call may span several lines);
* ``##<Symbols: count=N>`` ... ``##</Symbols>`` holds the session's variables as pairs of lines:
  ``<:name:>`` then one JSON object. A ``Group`` object states, as plain JSON scalars, its
  ``groupname``, ``filename``, ``atsym``, ``edge``, ``e0``, ``energy_shift`` and the keyword
  arguments of the calls that made it (``callargs``: ``pre_edge``, ``mback_norm`` ...). The
  array-valued members (``energy``, ``mu``, ``norm`` ...) are NOT read: they are data, not
  statements about the analysis.

WHAT IS STORED (every entry: ``concept``, verbatim ``literal``, ``locator``)
============================================================================
=============================== ====================================================== ==========================
concept                         literal                                                locator
=============================== ====================================================== ==========================
``larch.header.*``              the ``##LARIX`` and ``##Date Saved`` values            ``line N``
``larch.config.*``              version and platform values (see WITHHELD below)       ``line N``
``larch.xasgroup.filename`` /   one pair per ``_xasgroups`` entry: the data file name   ``symbol _xasgroups
``larch.xasgroup.groupname``    and the group name Larch gave it                       entry K``
``larch.group.<attr>``          a Group's stated scalar (``e0``, ``edge``, ``atsym`` ..) ``symbol <name>``
``larch.group.callargs.<fn>.<kw>`` a keyword argument a group's own record states      ``symbol <name>
                                                                                       callargs.<fn>``
``larch.data_file``             the path string of a ``read_*`` call, as written       ``command N``
``larch.param.<fn>.<kw>``       a keyword value of a processing call (``pre_edge``,    ``command N``
                                ``autobk``, ``xftf`` ...), written as in the call
``larch.param.set.<attr>``      the right-hand side of ``<group>.e0 = ..`` /           ``command N``
                                ``.energy_shift = ..``
``larch.command``               one history statement, clipped at 500 characters       ``command N (lines A-B)``
``larch.reader_summary``        the reader's own counts and caps, as JSON              ``file``
=============================== ====================================================== ==========================

``command N`` is the 1-based position of a statement among ALL history statements, so a number
means the same thing whether or not that statement's entry was stored. Display-only calls
(``plot*``, ``newplot``) are counted by name in the summary and NOT stored as entries: on the
measured files they were more than half of the history and state no parameter of the analysis.
Parameter entries repeat across hundreds of calls, so they are THINNED on ``(concept, literal)``:
the first locator is kept and the repeats are counted in the summary. The statement that carried
each call is still stored as a ``larch.command`` entry.

BOUNDS (stated in every file's ``larch.reader_summary`` entry)
==============================================================
decompressed text <= 64 MiB and <= 200 times the compressed size (a gzip bomb is refused, with
the number); at most 200,000 history statements scanned; entries per category are capped
(commands 6,000, data files 2,000, parameters 3,000, symbol-derived 6,000); a stored literal is
clipped at 500 characters with a marker that names the original length; the whole file adds at
most ``entry_budget`` entries. A cap that drops something says how many in the summary.

WITHHELD, AND SAID SO
=====================
The machine's name and MAC id and the saving user's profile paths (``home_dir``, ``history_file``
..) are not stored: they identify a person's machine, not an analysis. The summary says that
they were withheld and how many config lines were not kept. Paths a COMMAND states (the data
files it read) are kept as written, because they are the evidence of what was analysed.
"""

from __future__ import annotations

import json
import re
import zlib
from pathlib import Path
from typing import Any

from ._common import MAX_ANALYSIS_ENTRIES_TOTAL, AnalysisFile, Limits, clip_literal

READER_ID = "larch_session_v1"
READER_VERSION = "1.0.0"
KIND = "larch_session"
EXTENSION = ".larix"

MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_STATEMENTS_SCANNED = 200_000
MAX_COMMAND_ENTRIES = 6_000
MAX_DATA_FILE_ENTRIES = 2_000
MAX_PARAMETER_ENTRIES = 3_000
MAX_SYMBOL_ENTRIES = 6_000
MAX_SYMBOL_JSON_CHARS = 4_000_000
MAX_COMMAND_CHARS = 500
MAX_SCALAR_CHARS = 300
MAX_NAME_PART_CHARS = 64  # a function / keyword / section name placed in a concept or summary
MAX_SUMMARY_NAMES = 40  # distinct section names / display-call names listed in the summary


def _part(text: str) -> str:
    """A name from the file, bounded before it is placed in a concept id or the summary."""
    return text if len(text) <= MAX_NAME_PART_CHARS else text[:MAX_NAME_PART_CHARS] + "~"

#: ``##Key: value`` config lines whose VALUE is kept (the rest are counted, not kept).
_CONFIG_KEPT = {
    "Machine Platform": "machine_platform",
    "Machine Version": "machine_version",
    "Machine Processor": "machine_processor",
    "Machine Architecture": "machine_architecture",
    "Python Version": "python_version",
    "Python Implementation": "python_implementation",
    "Larch Release Version": "release_version",
    "Larch Release Date": "release_date",
    "Larch larch_version": "larch_version",
}
#: Config keys withheld on purpose: they identify a machine or a user's profile directory.
_CONFIG_WITHHELD = frozenset(
    {
        "Machine Name",
        "Machine MACID",
        "Larch history_file",
        "Larch home_dir",
        "Larch init_files",
        "Larch user_larchdir",
    }
)

#: Calls whose keyword arguments are processing parameters (matched by exact name).
PARAMETER_FUNCTIONS = frozenset(
    {
        "pre_edge",
        "find_e0",
        "autobk",
        "xftf",
        "xftr",
        "xftf_fast",
        "mback",
        "mback_norm",
        "feffit",
        "feffit_dataset",
        "feffit_transform",
        "lincombo_fit",
        "merge_groups",
    }
)
#: ``read_*`` calls whose first string argument names a data file.
DATA_READERS = frozenset(
    {
        "read_ascii",
        "read_xdi",
        "read_athena",
        "read_gsexdi",
        "read_xafsdata",
        "read_specfile",
        "read_hdf5",
        "read_xas_data",
        "read_csv",
    }
)
_SET_PARAMETERS = ("e0", "energy_shift")
#: Scalar members of a Group symbol that are stored.
_GROUP_ATTRS = (
    "groupname",
    "filename",
    "path",
    "atsym",
    "edge",
    "e0",
    "energy_shift",
    "energy_units",
    "datatype",
    "xasmode",
    "energy_ref",
    "copied_from",
)

_CALL = re.compile(r"^(?:[A-Za-z_][\w.]*\s*=\s*)?(?P<fn>[A-Za-z_][\w.]*)\s*\(")
_KWARG = re.compile(r"^(?P<k>[A-Za-z_]\w*)\s*=(?!=)\s*(?P<v>.*)$", re.DOTALL)
_STRING_ARG = re.compile(r"""^(?P<q>['"])(?P<s>.*)(?P=q)$""", re.DOTALL)
_SET_ATTR = re.compile(
    r"^[A-Za-z_][\w.]*\.(?P<attr>e0|energy_shift)\s*=(?!=)\s*(?P<v>[^\n=][^\n]*)$"
)


# --- the file's bytes -> text ------------------------------------------------------------


def _inflate(data: bytes) -> tuple[str | None, str | None, str]:
    """``(text, refusal, container)`` — gzip bounded in output size AND ratio, or plain text."""
    if data[:2] == b"\x1f\x8b":
        ceiling = min(MAX_DECOMPRESSED_BYTES, max(len(data) * MAX_COMPRESSION_RATIO, 1 << 20))
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = bytearray()
        try:
            view = memoryview(data)
            for start in range(0, len(data), 1 << 16):
                chunk = view[start : start + (1 << 16)]
                while chunk:
                    room = ceiling - len(out) + 1
                    out += decoder.decompress(chunk, room)
                    if len(out) > ceiling:
                        return (
                            None,
                            "the gzip stream expands past "
                            f"{ceiling} bytes (ceiling: {MAX_DECOMPRESSED_BYTES} bytes and "
                            f"{MAX_COMPRESSION_RATIO} times the {len(data)} compressed); "
                            "it was not read",
                            "gzip",
                        )
                    chunk = decoder.unconsumed_tail
                    if decoder.eof:
                        break
                if decoder.eof:
                    break
        except zlib.error as exc:
            return None, f"the gzip stream is damaged ({exc.__class__.__name__})", "gzip"
        if not decoder.eof:
            return None, "the gzip stream ends early (truncated file)", "gzip"
        return bytes(out).decode("utf-8", errors="replace"), None, "gzip"
    if data.startswith(b"##LARIX:"):
        if len(data) > MAX_DECOMPRESSED_BYTES:
            return None, f"the text is past {MAX_DECOMPRESSED_BYTES} bytes", "text"
        return data.decode("utf-8", errors="replace"), None, "text"
    return (
        None,
        "this is neither a gzip file nor text starting with the `##LARIX:` header, so it is "
        "not a Larch session file this reader can open",
        "unknown",
    )


# --- history text -> statements ------------------------------------------------------------


def split_statements(body: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """``[(first line, last line, text)]`` from ``(line number, line)`` pairs of the history.

    A new statement starts at a non-blank, non-comment, non-indented line while no bracket and
    no string is open. Indented lines and lines inside brackets continue the current statement.
    Quote handling is single-line (``'`` / ``"``, backslash escapes) plus triple quotes. Text is
    only ever scanned character by character; it is never compiled.
    """
    out: list[tuple[int, int, str]] = []
    cur: list[str] = []
    start = last = 0
    depth = 0
    quote: str | None = None  # "'", '"', "'''", '"""'
    continued = False
    for number, line in body:
        fresh = depth == 0 and quote is None and not continued
        stripped = line.strip()
        if fresh:
            if not stripped or stripped.startswith("#"):
                continue
            if cur and not line[:1].isspace():
                out.append((start, last, "\n".join(cur)))
                cur = []
            if not cur:
                start = number
        elif not cur:
            start = number
        cur.append(line)
        last = number
        # scan the line for bracket / quote state
        i, n = 0, len(line)
        continued = False
        while i < n:
            c = line[i]
            if quote is not None:
                if c == "\\":
                    i += 2
                    continue
                if line.startswith(quote, i):
                    i += len(quote)
                    quote = None
                    continue
                i += 1
                continue
            if c == "#":
                break
            if c in "'\"":
                quote = c * 3 if line.startswith(c * 3, i) else c
                i += len(quote)
                continue
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth = max(depth - 1, 0)
            i += 1
        if quote in ("'", '"'):
            quote = None  # a single-quoted string cannot span lines; recover at the break
        if depth == 0 and quote is None and line.rstrip().endswith("\\"):
            continued = True
    if cur:
        out.append((start, last, "\n".join(cur)))
    return out


def _matching_paren(text: str, open_at: int) -> int | None:
    depth = 0
    quote: str | None = None
    i, n = open_at, len(text)
    while i < n:
        c = text[i]
        if quote is not None:
            if c == "\\":
                i += 2
                continue
            if text.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if c in "'\"":
            quote = c * 3 if text.startswith(c * 3, i) else c
            i += len(quote)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if quote is not None:
            if c == "\\":
                i += 2
                continue
            if text.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if c in "'\"":
            quote = c * 3 if text.startswith(c * 3, i) else c
            i += len(quote)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    tail = text[start:]
    if tail.strip():
        parts.append(tail)
    return parts


def parse_call(statement: str) -> tuple[str, list[str], list[tuple[str, str]]] | None:
    """``(function name, positional args, [(keyword, value text)])`` for a call statement.

    The statement may assign the call to a name. ``None`` when it does not start with a call.
    """
    match = _CALL.match(statement.lstrip())
    if match is None:
        return None
    text = statement.lstrip()
    open_at = match.end() - 1
    close = _matching_paren(text, open_at)
    if close is None:
        return None
    positional: list[str] = []
    keywords: list[tuple[str, str]] = []
    for arg in _split_top_level(text[open_at + 1 : close]):
        kw = _KWARG.match(arg.strip())
        if kw:
            keywords.append((kw.group("k"), re.sub(r"\s+", " ", kw.group("v").strip())))
        elif arg.strip():
            positional.append(arg.strip())
    return match.group("fn"), positional, keywords


def _scalar_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return json.dumps(value)
    return None


# --- the reader ------------------------------------------------------------------------------


def sniff(relative_path: str) -> bool:
    """The reader claims a file by its extension; the CONTENT decides whether it can be read."""
    return relative_path.lower().endswith(EXTENSION)


def read(
    path: Path,
    relative_path: str,
    limits: Limits = Limits(),
    entry_budget: int = MAX_ANALYSIS_ENTRIES_TOTAL,
) -> AnalysisFile:
    """Read one ``.larix`` into an :class:`AnalysisFile`. Never raises for a bad file."""
    result = AnalysisFile(relative_path=relative_path, reader_id=READER_ID, kind=KIND)
    try:
        size = path.stat().st_size
        if size > limits.max_scan_bytes:
            result.refused_reason = (
                f"the file is {size} bytes; the reader's ceiling is {limits.max_scan_bytes}"
            )
            return result
        with path.open("rb") as fh:
            data = fh.read(limits.max_scan_bytes + 1)
    except OSError as exc:
        result.refused_reason = f"the file could not be read ({type(exc).__name__})"
        return result
    text, refusal, container = _inflate(data)
    if text is None:
        result.refused_reason = refusal
        return result
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n")]
    if not lines or not lines[0].startswith("##LARIX:"):
        result.refused_reason = (
            "the first line is not a `##LARIX:` header, so this is not a Larch session file"
        )
        return result

    header: list[dict] = []
    config: list[dict] = []
    commands_body: list[tuple[int, str]] = []
    symbol_pairs: list[tuple[int, str, str]] = []
    config_withheld = config_not_kept = 0
    sections_seen: list[str] = []
    sections_not_listed = 0
    section: str | None = None
    pending: tuple[int, str] | None = None
    unpaired_symbol_lines = 0

    for index, line in enumerate(lines, 1):
        if line.startswith("##<") and not line.startswith("##</"):
            section = line[3:].split(">", 1)[0].split(":", 1)[0].strip()
            if len(sections_seen) < MAX_SUMMARY_NAMES:
                sections_seen.append(_part(section))
            else:
                sections_not_listed += 1
            pending = None
            continue
        if line.startswith("##</"):
            section = None
            pending = None
            continue
        if section is None:
            if line.startswith("##LARIX:"):
                header.append({"concept": "larch.header.larix", "literal": clip_literal(line[8:].strip(), MAX_SCALAR_CHARS)[0], "locator": f"line {index}"})
            elif line.startswith("##Date Saved:"):
                header.append({"concept": "larch.header.date_saved", "literal": clip_literal(line[13:].strip(), MAX_SCALAR_CHARS)[0], "locator": f"line {index}"})
            continue
        if section == "CONFIG":
            if line.startswith("##") and ":" in line:
                key, _, value = line[2:].partition(":")
                key = key.strip()
                if key in _CONFIG_WITHHELD:
                    config_withheld += 1
                elif key in _CONFIG_KEPT:
                    config.append({"concept": f"larch.config.{_CONFIG_KEPT[key]}", "literal": clip_literal(value.strip(), MAX_SCALAR_CHARS)[0], "locator": f"line {index}"})
                else:
                    config_not_kept += 1
        elif section == "Session Commands":
            commands_body.append((index, line))
        elif section == "Symbols":
            marker = re.match(r"^<:(.*):>$", line)
            if marker:
                pending = (index, marker.group(1))
            elif pending is not None:
                symbol_pairs.append((pending[0], pending[1], line))
                pending = None
            elif line.strip():
                unpaired_symbol_lines += 1

    statements = split_statements(commands_body)
    scanned = statements[:MAX_STATEMENTS_SCANNED]
    not_scanned = len(statements) - len(scanned)

    # ---- the history, statement by statement ------------------------------------------------
    commands: list[dict] = []
    data_files: list[dict] = []
    params: list[dict] = []
    display_counts: dict[str, int] = {}
    seen_data: set[str] = set()
    seen_params: set[tuple[str, str]] = set()
    commands_clipped = data_file_repeats = param_repeats = 0
    commands_total_stored_candidates = 0
    dropped = {"commands": 0, "data_files": 0, "parameters": 0, "symbols": 0}
    parameter_values_total = 0

    for number, (first, last, text) in enumerate(scanned, 1):
        call = parse_call(text)
        fn = call[0] if call else None
        base_fn = fn.rsplit(".", 1)[-1] if fn else None
        locator = f"command {number}"
        if base_fn is not None and base_fn.lower().startswith(("plot", "newplot")):
            key = _part(base_fn)
            if key not in display_counts and len(display_counts) >= MAX_SUMMARY_NAMES:
                key = "(other display calls)"
            display_counts[key] = display_counts.get(key, 0) + 1
            continue
        commands_total_stored_candidates += 1
        if len(commands) < MAX_COMMAND_ENTRIES:
            literal, clipped = clip_literal(text, MAX_COMMAND_CHARS)
            commands_clipped += int(clipped)
            commands.append({"concept": "larch.command", "literal": literal, "locator": f"{locator} (lines {first}-{last})"})
        else:
            dropped["commands"] += 1
        if call is None:
            set_match = _SET_ATTR.match(text.strip())
            if set_match:
                value = re.sub(r"\s+", " ", set_match.group("v").strip())
                parameter_values_total += 1
                key = (f"larch.param.set.{set_match.group('attr')}", value)
                if key in seen_params:
                    param_repeats += 1
                elif len(params) < MAX_PARAMETER_ENTRIES:
                    seen_params.add(key)
                    literal, _ = clip_literal(value, MAX_SCALAR_CHARS)
                    params.append({"concept": key[0], "literal": literal, "locator": locator})
                else:
                    dropped["parameters"] += 1
            continue
        _, positional, keywords = call
        if base_fn in DATA_READERS and positional:
            string = _STRING_ARG.match(positional[0])
            if string:
                value = string.group("s")
                if value in seen_data:
                    data_file_repeats += 1
                elif len(data_files) < MAX_DATA_FILE_ENTRIES:
                    seen_data.add(value)
                    literal, _ = clip_literal(value, MAX_SCALAR_CHARS)
                    data_files.append({"concept": "larch.data_file", "literal": literal, "locator": locator})
                else:
                    dropped["data_files"] += 1
        if base_fn in PARAMETER_FUNCTIONS:
            for keyword, value in keywords:
                parameter_values_total += 1
                key = (f"larch.param.{_part(base_fn)}.{_part(keyword)}", value)
                if key in seen_params:
                    param_repeats += 1
                elif len(params) < MAX_PARAMETER_ENTRIES:
                    seen_params.add(key)
                    literal, _ = clip_literal(value, MAX_SCALAR_CHARS)
                    params.append({"concept": key[0], "literal": literal, "locator": locator})
                else:
                    dropped["parameters"] += 1

    # ---- the symbols: groups and the file -> group map --------------------------------------
    symbols: list[dict] = []
    symbols_total = group_symbols = skipped = 0
    for index, name, raw in symbol_pairs:
        symbols_total += 1
        if len(raw) > MAX_SYMBOL_JSON_CHARS:
            skipped += 1
            continue
        try:
            obj = json.loads(raw)
        except (ValueError, RecursionError):
            skipped += 1
            continue
        if not isinstance(obj, dict):
            skipped += 1
            continue
        shown, _ = clip_literal(name, 120)
        if obj.get("__class__") == "Group":
            group_symbols += 1
            for attr in _GROUP_ATTRS:
                text_value = _scalar_text(obj.get(attr)) if attr in obj else None
                if text_value is None:
                    continue
                if len(symbols) >= MAX_SYMBOL_ENTRIES:
                    dropped["symbols"] += 1
                    continue
                literal, _ = clip_literal(text_value, MAX_SCALAR_CHARS)
                symbols.append({"concept": f"larch.group.{attr}", "literal": literal, "locator": f"symbol {shown}"})
            callargs = obj.get("callargs")
            if isinstance(callargs, dict):
                for fn_name, kwargs in callargs.items():
                    if fn_name == "__class__" or not isinstance(kwargs, dict):
                        continue
                    for keyword, value in kwargs.items():
                        text_value = _scalar_text(value) if keyword != "__class__" else None
                        if text_value is None:
                            continue
                        if len(symbols) >= MAX_SYMBOL_ENTRIES:
                            dropped["symbols"] += 1
                            continue
                        literal, _ = clip_literal(text_value, MAX_SCALAR_CHARS)
                        symbols.append(
                            {
                                "concept": f"larch.group.callargs.{_part(fn_name)}.{_part(keyword)}",
                                "literal": literal,
                                "locator": f"symbol {shown} callargs.{_part(fn_name)}",
                            }
                        )
        elif name == "_xasgroups":
            for k, (filename, groupname) in enumerate(
                ((a, b) for a, b in obj.items() if a != "__class__"), 1
            ):
                for concept, value in (("larch.xasgroup.filename", filename), ("larch.xasgroup.groupname", groupname)):
                    text_value = _scalar_text(value)
                    if text_value is None:
                        continue
                    if len(symbols) >= MAX_SYMBOL_ENTRIES:
                        dropped["symbols"] += 1
                        continue
                    literal, _ = clip_literal(text_value, MAX_SCALAR_CHARS)
                    symbols.append({"concept": concept, "literal": literal, "locator": f"symbol _xasgroups entry {k}"})

    # ---- assemble, with the total budget ----------------------------------------------------------
    ordered = header + config + symbols + data_files + params + commands
    summary_slot = 1
    room = max(entry_budget - summary_slot, 0)
    budget_dropped = max(len(ordered) - room, 0)
    kept = ordered[:room]
    result.suppressed_total = sum(dropped.values()) + not_scanned + budget_dropped
    result.skipped_total = skipped + unpaired_symbol_lines
    counts: dict[str, Any] = {
        "container": container,
        "text_bytes": len(text.encode("utf-8", errors="replace")),
        "sections": sections_seen,
        "sections_not_listed": sections_not_listed,
        "history_statements": len(statements),
        "history_statements_not_scanned": not_scanned,
        "commands_stored_of": commands_total_stored_candidates,
        "commands_kept": len(commands),
        "command_chars_cap": MAX_COMMAND_CHARS,
        "commands_clipped": commands_clipped,
        "display_commands_not_stored": dict(sorted(display_counts.items())),
        "data_files_kept": len(data_files),
        "data_file_repeats_thinned": data_file_repeats,
        "parameter_values_seen": parameter_values_total,
        "parameters_kept": len(params),
        "parameter_repeats_thinned": param_repeats,
        "symbols_total": symbols_total,
        "group_symbols": group_symbols,
        "symbol_entries_kept": len(symbols),
        "symbols_skipped_unparseable": skipped,
        "config_lines_withheld": config_withheld,
        "config_lines_not_kept": config_not_kept,
        "withheld": "machine name, machine id and the saving user's profile paths",
        "caps": {
            "commands": MAX_COMMAND_ENTRIES,
            "data_files": MAX_DATA_FILE_ENTRIES,
            "parameters": MAX_PARAMETER_ENTRIES,
            "symbol_entries": MAX_SYMBOL_ENTRIES,
            "literal_chars": MAX_SCALAR_CHARS,
            "entries_for_this_file": entry_budget,
        },
        "dropped_for_a_cap": {**dropped, "not_scanned": not_scanned, "file_budget": budget_dropped},
    }
    result.counts = counts
    summary = {
        "concept": "larch.reader_summary",
        "literal": json.dumps({"reader": READER_ID, **counts}, sort_keys=True, ensure_ascii=False),
        "locator": "file",
    }
    result.entries = [summary, *kept]
    return result

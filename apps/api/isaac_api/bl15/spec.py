"""The root SPEC acquisition reader — the ``#O``/``#P`` pairing one.

Format, measured (characterization §3.1): a file-level header ``#F`` ``#E``
``#D`` ``#C``, then ``#O0``..``#O21`` carrying 172 whitespace-column motor
**names**, then one block per scan — ``#S`` ``#D`` ``#T`` ``#G*`` ``#Q``
``#P0``..``#P21`` (**positions, in the same order as the names**) ``#N`` ``#L``
— then the data rows.

**THE PAIRING IS THE WHOLE JOB, AND NOTHING IN A ``#P`` LINE NAMES ITS MOTOR.**
The names live in ``#O<i>``, the values in ``#P<i>``, and they are zipped by
index and then by column position. **No index is hard-coded anywhere in this
module.** Verified by measurement over all 94 acquisition files in the supplied
archive: the pairing puts ``energy``, ``emiss``, ``filter``, ``Sx``, ``Sy``,
``Sz`` and ``Sr`` on exactly the values the corresponding ``.dat`` export states
by NAME for the same scan (``#P0 dummy0=<v> energy=<v> emiss=<v>
filter=<v> Sx=<v> ...``) — an independent check that could not agree by
accident.

**A MISPAIRED ``#P`` LINE IS REFUSED, NOT GUESSED.** If a ``#P<i>`` line's field
count does not match its ``#O<i>`` line's, every mapping on that line is
suspect: a missing field silently shifts every later motor's value onto its
neighbour's name. The line is reported under ``skipped`` naming BOTH counts and
contributes no evidence. Zero real files in the supplied archive mispair; the
path exists because a mispaired reading is worse than none, and it is exercised
by a fixture built to mispair.

**``#E`` AND ``#D`` ARE TWO STATEMENTS AND ARE NOT RECONCILED.** ``#E`` is a Unix
epoch, converted to ISO-8601 UTC by a named rule. ``#D`` is a local-time string
with no zone, read verbatim and given no ``timestamp_utc`` at all, because
assigning it one would require inventing a timezone. If they disagree, BOTH are
read and the disagreement is a later slice's to surface.

**``#C`` IS NEVER AN ISAAC IDENTITY.** ``#C spec  User = <beamline account>`` states what
the SPEC session thought its user was. the value is a shared beamline account, not a
person and not an Authentik principal, and ``CLAUDE.md`` §15 is explicit that
``attribution.uploaded_by`` may only be stamped from a trusted authentication
boundary this build does not have. It is read as
:data:`~isaac_api.bl15.evidence.CONCEPT_SPEC_USER_STRING` — raw evidence — and
no reader in this package maps it to an actor.

**THE ``#F`` DECLARATION IS THE CONFLICT-DETECTION ANCHOR, AND THIS READER
DETECTS NOTHING.** Four measured files disagree with their own external names —
``29``/``30``/``31``/``32_03_JK2_base_after1500Cycling_...`` all declare
``..._beforeCycling_...`` internally. This reader reports what the file says, at
``#F``, and stops. Comparing it with the external name is :mod:`bl15.relate`'s
job, and choosing between them is nobody's job in this repository: it is a
question for the scientist.

**AND A ``#F`` IS NOT ALWAYS A BARE STEM.** Measured over all 188 files carrying
one: **186 bare stems and 2 absolute filesystem paths**. The literal is reported
whole, path and all — a value a scientist cannot find in the file is worse than a
long one — with the basename beside it as the normalised reading and as
``measurement_stem``. See :data:`RULE_F_CARRIES_A_PATH`; a fixture carries the
path form so the 186-vs-2 split has regression cover.

**THE DATA ROWS ARE NOT READ INTO EVIDENCE.** 500 KB of numbers is not 500 KB of
statements. Row counts are reported per scan under ``skipped`` with reason
:data:`SKIP_DATA_ROWS`, which is an INFORMATIONAL skip: the rows were seen,
counted, and deliberately not turned into statements.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ._emit import EvidenceBuilder, oversize_reason, refusal
from .evidence import (
    CONCEPT_ACQUISITION_EPOCH,
    CONCEPT_ACQUISITION_TIMESTAMP,
    CONCEPT_COUNTING_TIME,
    CONCEPT_DETECTOR_COLUMN,
    CONCEPT_EMISSION_ENERGY,
    CONCEPT_ENERGY_GRID,
    CONCEPT_FILTER,
    CONCEPT_MOTOR_POSITION,
    CONCEPT_SAMPLE_POSITION,
    CONCEPT_SCAN_COMMAND,
    CONCEPT_SPEC_FILE_DECLARATION,
    CONCEPT_SPEC_USER_STRING,
    DETERMINISM_NORMALIZED,
    DETERMINISM_READ,
    MAX_DATA_ROWS,
    MAX_SOURCE_BYTES,
    SCOPE_MEASUREMENT,
    SCOPE_SCAN,
    SOURCE_TYPE_SPEC_ACQUISITION,
    ReaderResult,
)
from .inventory import SourceRecord

PARSER_ID = "bl15_spec_acquisition_v1"

#: A UTF-8 byte-order mark, written as an ESCAPE and never as a literal byte in
#: any source file of this package. ``CLAUDE.md`` §11 records at length what an
#: invisible byte in a tracked file costs — a ``grep``/``rg`` sweep that returns
#: zero hits and exits 0, indistinguishable from a skipped file. The measured
#: beamtime-notes file in the supplied archive begins with one.
BOM = "\ufeff"

#: An informational skip: the rows were counted and deliberately not read.
SKIP_DATA_ROWS = "data_rows_counted_not_read"
#: A ``#P`` line whose field count disagrees with its ``#O`` line.
SKIP_MISPAIRED_POSITIONS = "mispaired_motor_positions"
#: A ``#P`` line with no ``#O`` line at the same index.
SKIP_UNPAIRED_POSITIONS = "motor_positions_without_names"
#: ``#N``. See :data:`RULE_N_IS_COLUMN_COUNT`.
SKIP_N_IS_COLUMN_COUNT = "header_N_is_the_column_count"
#: A header this reader does not read (``#G*``, ``#Q``, ``#@*`` …).
SKIP_UNREAD_HEADER = "header_not_read_by_this_reader"


RULE_EPOCH_TO_UTC = (
    "bl15.spec.epoch_to_utc_iso.v1: `#E` states a Unix epoch in seconds; it is "
    "converted to an ISO-8601 instant in UTC. This is an exact, "
    "timezone-unambiguous conversion of the number the file states — it is NOT "
    "reconciled against `#D`, which is a local-time string with no zone, and "
    "the two are reported as separate statements even when they disagree."
)
RULE_COUNTING_TIME_SECONDS = (
    "bl15.spec.counting_time_seconds.v1: `#T <value>  (sec)` states the "
    "counting time per point, with the unit written in the line itself. The "
    "value is reported as a number in seconds only because the line's own `(sec)` "
    "says so; a `#T` line declaring any other unit is read verbatim with no "
    "normalised value."
)
RULE_GSCAN_GRID = (
    "bl15.spec.gscan_grid_literal.v1: for a `gscan <motor> <grid...> <ctime>` "
    "command the energy grid is the fields between the motor name and the FINAL "
    "field. Warranted by the acquisition method's own call, which this archive "
    "contains: `Ir_XAS.mac` builds the command as "
    "`gscan energy %s %f` with `%s` the grid literal `XAS_MAIN_GRID` and `%f` "
    "the counting time. Applied ONLY to `gscan`; `ascan`, `a2scan` and "
    "`loopscan` (all present in `alignment`) carry no grid and get none."
)
RULE_O_P_PAIRING = (
    "bl15.spec.motor_name_position_pairing.v1: motor names come from `#O<i>` and "
    "positions from `#P<i>`, zipped by index and then by whitespace column. No "
    "index is hard-coded. A line pair whose field counts disagree is REFUSED "
    "whole and reported with both counts, because one missing field shifts "
    "every later value onto the wrong motor's name. The position is "
    "additionally read as a number where the field parses as one; a field that "
    "does not parse keeps its literal and gets no normalised value, because the "
    "NAME is still established by the pairing even when the value is not a "
    "number."
)
RULE_F_CARRIES_A_PATH = (
    "bl15.spec.file_declaration_carries_a_path.v1: this `#F` declaration is an "
    "ABSOLUTE FILESYSTEM PATH rather than a bare measurement stem, and the "
    "literal is reported WHOLE, path included — a value a scientist cannot find "
    "in the file is worse than a long one. The basename is reported beside it as "
    "the normalised reading, and as `measurement_stem`, because that is the part "
    "a relationship pass can compare. MEASURED over all 188 files carrying a "
    "`#F`: 186 bare stems, 2 absolute paths, and ZERO whose basename still "
    "differs once the path is stripped — so stripping the path has never yet "
    "changed a comparison, and reporting the fact that it was there is the "
    "point. COMPARING it with the external filename is `bl15.relate`'s job, not "
    "this reader's."
)
RULE_N_IS_COLUMN_COUNT = (
    "bl15.spec.N_is_the_column_count.v1: `#N` is NOT read as a point count. "
    "MEASURED over the supplied archive: in 920 of 920 scan blocks `#N` equals "
    "the number of column names on the following `#L` line exactly (39/39, "
    "40/40, 24/24), while the scans carry 444 to 7,320 data rows. So `#N` is "
    "the COLUMN count, which `bl15.evidence` has no concept for, and reporting "
    "it as `point_count` would publish a false statement. It is reported under "
    "`skipped` with this measurement instead. Each column name IS read, from "
    "`#L`, as a `detector_column`."
)

NORMALIZATION_RULES: frozenset[str] = frozenset(
    {
        RULE_EPOCH_TO_UTC,
        RULE_COUNTING_TIME_SECONDS,
        RULE_GSCAN_GRID,
        RULE_O_P_PAIRING,
        RULE_F_CARRIES_A_PATH,
    }
)

#: Motor names whose position is a statement about something more specific than
#: "a motor is here". Measured from the archive's own ``.dat`` exports, which
#: name the same motors explicitly. Everything not listed is
#: :data:`~isaac_api.bl15.evidence.CONCEPT_MOTOR_POSITION` — deliberately, because
#: this package does not know what 165 other beamline motors mean and must not
#: pretend to.
MOTOR_CONCEPTS: dict[str, str] = {
    "emiss": CONCEPT_EMISSION_ENERGY,
    "filter": CONCEPT_FILTER,
    "Sx": CONCEPT_SAMPLE_POSITION,
    "Sy": CONCEPT_SAMPLE_POSITION,
    "Sz": CONCEPT_SAMPLE_POSITION,
    "Sr": CONCEPT_SAMPLE_POSITION,
}

_HEADER_LINE = re.compile(r"^#([A-Za-z@]+)(\d*)[ \t]*(.*)$")
_COUNTING_TIME = re.compile(r"^(\S+)\s*\(sec\)\s*$")
_SCAN_HEADER = re.compile(r"^(\S+)\s+(.*)$")


def _to_float(text: str) -> float | int | None:
    try:
        value = float(text)
    except ValueError:
        return None
    if value.is_integer() and "." not in text and "e" not in text.casefold():
        return int(value)
    return value


def read_spec_acquisition(
    record: SourceRecord, text: str, *, id_prefix: str = ""
) -> ReaderResult:
    """Read one root SPEC acquisition file. Never raises.

    ``text`` is supplied by the caller; this reader opens nothing.
    """
    measured = max(record.size_bytes, len(text.encode("utf-8", "replace")))
    if measured > MAX_SOURCE_BYTES:
        return refusal(
            source_path=record.archive_path,
            parser_id=PARSER_ID,
            reason=oversize_reason(measured, MAX_SOURCE_BYTES),
        )

    # A UTF-8 BOM is written as an escape, never as a literal byte in this
    # source file: `CLAUDE.md` §11 records what an invisible byte in a tracked
    # file costs (a `grep` sweep that returns zero hits and exits 0).
    body = text.lstrip(BOM)
    lines = body.splitlines()
    if not any(line.startswith("#F") for line in lines):
        return refusal(
            source_path=record.archive_path,
            parser_id=PARSER_ID,
            reason=(
                "not_a_spec_acquisition: no `#F` filename declaration appears "
                "anywhere in this file. A root SPEC acquisition always declares "
                "its own name; a per-scan `.dat` export never does, and a macro "
                "has no `#` headers at all"
            ),
        )

    builder = EvidenceBuilder(
        source_path=record.archive_path,
        source_type=SOURCE_TYPE_SPEC_ACQUISITION,
        parser_id=PARSER_ID,
        id_prefix=id_prefix,
    )

    declared_stem: str | None = None
    motor_names: dict[int, list[str]] = {}
    scan_label: str | None = None
    row_count = 0
    row_first_line: int | None = None
    row_cap_hit = False
    # Two skip classes are AGGREGATED rather than emitted per occurrence, and the
    # reason is measured: `alignment` carries 233 scan blocks, each with its own
    # `#N` and five `#G*`/`#Q` lines, so per-line entries would bury the
    # mispairing and row-count reports that actually carry information under
    # ~1,400 identical ones. Each aggregate states its own count and first line.
    unread_headers: dict[str, list[int]] = {}
    n_headers: list[int] = []
    n_values: list[str] = []

    def flush_rows() -> None:
        nonlocal row_count, row_first_line, row_cap_hit
        if row_count:
            builder.skip(
                reason=SKIP_DATA_ROWS,
                locator=(
                    f"{scan_label or 'file'} data block, "
                    f"lines {row_first_line}..{(row_first_line or 0) + row_count - 1}"
                ),
                detail=(
                    f"{row_count} data rows were counted and deliberately not "
                    f"read into evidence"
                    + (
                        f"; the reader stopped walking rows at the ceiling of "
                        f"{MAX_DATA_ROWS}, so the count is a LOWER BOUND"
                        if row_cap_hit
                        else ""
                    )
                ),
                row_count=row_count,
                complete=not row_cap_hit,
            )
        row_count = 0
        row_first_line = None
        row_cap_hit = False

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        if not line.startswith("#"):
            if row_first_line is None:
                row_first_line = number
            if row_count >= MAX_DATA_ROWS:
                row_cap_hit = True
                continue
            row_count += 1
            continue

        match = _HEADER_LINE.match(line)
        if not match:
            builder.skip(
                reason=SKIP_UNREAD_HEADER,
                locator=f"line {number}",
                detail="a `#` line this reader could not parse as a header",
            )
            continue
        key, suffix, payload = match.group(1), match.group(2), match.group(3)
        payload = payload.rstrip()

        if key == "F" and not suffix:
            flush_rows()
            literal = payload.strip()
            # Two real shapes, measured: 186 bare stems and 2 absolute paths.
            # The literal is NEVER shortened; a path carries the basename beside
            # it as the normalised reading. See RULE_F_CARRIES_A_PATH.
            carries_path = "/" in literal or "\\" in literal
            declared_stem = (
                literal.replace("\\", "/").rsplit("/", 1)[-1]
                if carries_path
                else literal
            ) or None
            builder.add(
                locator=f"line {number} header #F",
                raw_literal=literal,
                concept=CONCEPT_SPEC_FILE_DECLARATION,
                determinism=(
                    DETERMINISM_NORMALIZED if carries_path else DETERMINISM_READ
                ),
                normalized_value=declared_stem if carries_path else None,
                normalization_rule=(
                    RULE_F_CARRIES_A_PATH if carries_path else None
                ),
                scope=SCOPE_MEASUREMENT,
                measurement_stem=declared_stem,
            )
            continue

        if key == "E" and not suffix:
            iso = None
            epoch = _to_float(payload.strip())
            if epoch is not None:
                iso = datetime.fromtimestamp(
                    float(epoch), tz=timezone.utc
                ).isoformat()
            builder.add(
                locator=f"line {number} header #E",
                raw_literal=payload.strip(),
                concept=CONCEPT_ACQUISITION_EPOCH,
                determinism=(
                    DETERMINISM_NORMALIZED if iso else DETERMINISM_READ
                ),
                normalized_value=iso,
                normalization_rule=RULE_EPOCH_TO_UTC if iso else None,
                timestamp_utc=iso,
                scope=SCOPE_MEASUREMENT,
                measurement_stem=declared_stem,
            )
            continue

        if key == "D" and not suffix:
            # `#D` appears once at file level and once per scan; the scope
            # follows where we are, which is what `scan_label` tracks.
            builder.add(
                locator=(
                    f"line {number} header #D"
                    + (f" ({scan_label})" if scan_label else "")
                ),
                raw_literal=payload.strip(),
                concept=CONCEPT_ACQUISITION_TIMESTAMP,
                scope=SCOPE_SCAN if scan_label else SCOPE_MEASUREMENT,
                measurement_stem=declared_stem,
            )
            continue

        if key == "C" and not suffix:
            builder.add(
                locator=f"line {number} header #C",
                raw_literal=payload.strip(),
                concept=CONCEPT_SPEC_USER_STRING,
                scope=SCOPE_MEASUREMENT,
                measurement_stem=declared_stem,
            )
            continue

        if key == "O" and suffix.isdigit():
            motor_names[int(suffix)] = payload.split()
            continue

        if key == "S" and not suffix:
            flush_rows()
            scan_match = _SCAN_HEADER.match(payload)
            scan_number = scan_match.group(1) if scan_match else payload.strip()
            command = scan_match.group(2).strip() if scan_match else ""
            scan_label = f"scan {scan_number}"
            # THE SCAN THIS FILE IS NOW INSIDE, stamped on every scan-scope statement
            # that follows (`EvidenceBuilder.scan`). A numeric `#S` label is written
            # without leading zeros so it matches a scan export's `_001` index.
            builder.scan = str(int(scan_number)) if scan_number.isdigit() else scan_number
            if command:
                builder.add(
                    locator=f"line {number} header #S ({scan_label})",
                    raw_literal=command,
                    concept=CONCEPT_SCAN_COMMAND,
                    scope=SCOPE_SCAN,
                    measurement_stem=declared_stem,
                )
                grid = gscan_grid(command)
                if grid is not None:
                    builder.add(
                        locator=(
                            f"line {number} header #S ({scan_label}) "
                            f"gscan grid literal"
                        ),
                        raw_literal=grid,
                        concept=CONCEPT_ENERGY_GRID,
                        scope=SCOPE_SCAN,
                        measurement_stem=declared_stem,
                    )
            continue

        if key == "T" and not suffix:
            seconds = None
            time_match = _COUNTING_TIME.match(payload.strip())
            if time_match:
                seconds = _to_float(time_match.group(1))
            builder.add(
                locator=f"line {number} header #T ({scan_label or 'file'})",
                raw_literal=payload.strip(),
                concept=CONCEPT_COUNTING_TIME,
                determinism=(
                    DETERMINISM_NORMALIZED
                    if seconds is not None
                    else DETERMINISM_READ
                ),
                normalized_value=seconds,
                unit="s" if seconds is not None else None,
                normalization_rule=(
                    RULE_COUNTING_TIME_SECONDS if seconds is not None else None
                ),
                scope=SCOPE_SCAN if scan_label else SCOPE_MEASUREMENT,
                measurement_stem=declared_stem,
            )
            continue

        if key == "P" and suffix.isdigit():
            _read_positions(
                builder,
                index=int(suffix),
                payload=payload,
                motor_names=motor_names,
                line_number=number,
                scan_label=scan_label,
                declared_stem=declared_stem,
            )
            continue

        if key == "N" and not suffix:
            n_headers.append(number)
            n_values.append(payload.strip())
            continue

        if key == "L" and not suffix:
            for position, column in enumerate(payload.split()):
                builder.add(
                    locator=(
                        f"line {number} header #L column {position} "
                        f"({scan_label or 'file'})"
                    ),
                    raw_literal=column,
                    concept=CONCEPT_DETECTOR_COLUMN,
                    scope=SCOPE_SCAN if scan_label else SCOPE_MEASUREMENT,
                    measurement_stem=declared_stem,
                    item=f"column {position}",
                )
            continue

        unread_headers.setdefault(f"#{key}{suffix}", []).append(number)

    flush_rows()

    if n_headers:
        builder.skip(
            reason=SKIP_N_IS_COLUMN_COUNT,
            locator=f"line {n_headers[0]} header #N (and {len(n_headers) - 1} more)",
            detail=RULE_N_IS_COLUMN_COUNT,
            occurrence_count=len(n_headers),
            raw_literals=sorted(set(n_values)),
        )
    for header, numbers in sorted(unread_headers.items()):
        builder.skip(
            reason=SKIP_UNREAD_HEADER,
            locator=f"line {numbers[0]} header {header}",
            detail=(
                f"`{header}` appears {len(numbers)} time(s) and carries no "
                f"concept in `bl15.evidence`; it is reported rather than read"
            ),
            header=header,
            occurrence_count=len(numbers),
        )
    return builder.result()


def gscan_grid(command: str) -> str | None:
    """The grid literal inside a ``gscan`` command, verbatim, or ``None``.

    See :data:`RULE_GSCAN_GRID` for why the final field is the counting time and
    why this is applied to ``gscan`` alone.
    """
    fields = command.split()
    if len(fields) < 4 or fields[0] != "gscan":
        return None
    grid_fields = fields[2:-1]
    if not grid_fields:
        return None
    return " ".join(grid_fields)


def _read_positions(
    builder: EvidenceBuilder,
    *,
    index: int,
    payload: str,
    motor_names: dict[int, list[str]],
    line_number: int,
    scan_label: str | None,
    declared_stem: str | None,
) -> None:
    values = payload.split()
    names = motor_names.get(index)
    if names is None:
        builder.skip(
            reason=SKIP_UNPAIRED_POSITIONS,
            locator=f"line {line_number} header #P{index}",
            detail=(
                f"`#P{index}` carries {len(values)} positions but no `#O{index}` "
                f"line declared any motor names for that index, so nothing on "
                f"this line can be named. No mapping is guessed"
            ),
            position_count=len(values),
        )
        return
    if len(names) != len(values):
        builder.skip(
            reason=SKIP_MISPAIRED_POSITIONS,
            locator=f"line {line_number} header #P{index}",
            detail=(
                f"`#O{index}` declares {len(names)} motor names and `#P{index}` "
                f"carries {len(values)} positions. The whole line is refused: "
                f"one missing field would shift every later position onto the "
                f"wrong motor's name, and a mispaired mapping is worse than no "
                f"mapping"
            ),
            name_count=len(names),
            position_count=len(values),
        )
        return
    for column, (name, value) in enumerate(zip(names, values)):
        builder.add(
            locator=(
                f"line {line_number} header #P{index} column {column} "
                f"(motor `{name}` from #O{index})"
                + (f" ({scan_label})" if scan_label else "")
            ),
            raw_literal=value,
            concept=MOTOR_CONCEPTS.get(name, CONCEPT_MOTOR_POSITION),
            determinism=DETERMINISM_NORMALIZED,
            normalized_value=_to_float(value),
            normalization_rule=RULE_O_P_PAIRING,
            scope=SCOPE_SCAN if scan_label else SCOPE_MEASUREMENT,
            measurement_stem=declared_stem,
            item=name,
        )

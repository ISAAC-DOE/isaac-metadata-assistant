"""The per-scan ``.dat`` export reader.

**A GENUINELY DIFFERENT FORMAT FROM THE ROOT ACQUISITION, AND DELIBERATELY NOT
SHARING ITS PAIRING CODE.** Measured (characterization §3.2): a ``.dat`` carries
the same ``#S`` ``#D`` ``#T`` ``#N`` ``#L`` header, but its positions are
**already keyed** —

.. code-block:: text

    #P0 dummy0=<v> energy=<v> emiss=<v> filter=<v> Sx=<v> Sy=<v> ...

— there is **no ``#O`` block** and **no ``#F``**. So the fragile part of
:mod:`bl15.spec` (zip 22 name lines against 22 position lines and refuse a
mispair) has no counterpart here at all: a mispairing is not *detected*, it is
*impossible*, because every value names its own motor on its own line. Sharing
the ``#O`` code would mean carrying a refusal path that can never fire and, worse,
inviting a future change to make one format's assumption true of the other.
Verified over all **908** ``.dat`` files in the supplied archive: **0** carry an
``#F``, **0** carry an ``#O``, **908** have keyed ``#P`` lines, and each holds
exactly **one** ``#S`` block.

**THE STEM AND THE SCAN INDEX COME FROM THE BASENAME, BY A NAMED RULE.** A
``.dat`` never declares which measurement it belongs to, and the only statement
about that is its own filename: ``<stem>_001.dat``. Measured: **908 of 908**
basenames match ``<stem>_<digits>.dat``, and all 908 use a three-digit index. The
derivation is reported as a normalisation with
:data:`RULE_BASENAME_STEM_AND_INDEX` — never as something the file's content said.

**A ``.dat`` IS A SCAN, NOT A MEASUREMENT.** 908 files are the scan children of
~92 measurements (0 to 233 per directory). ``scan_export`` is deliberately absent
from :data:`~isaac_api.bl15.evidence.RUN_CANDIDATE_SOURCE_TYPES`; promoting each
to a Run would invent 816 measurements nobody performed. Statements are scoped
:data:`~isaac_api.bl15.evidence.SCOPE_SCAN`.

**THE DATA ROWS ARE NOT READ.** Counted and reported under ``skipped``, same as
the acquisition reader.
"""

from __future__ import annotations

import re

from ._emit import EvidenceBuilder, oversize_reason, refusal
from .evidence import (
    CONCEPT_ACQUISITION_TARGET,
    CONCEPT_ACQUISITION_TIMESTAMP,
    CONCEPT_COUNTING_TIME,
    CONCEPT_DETECTOR_COLUMN,
    CONCEPT_ENERGY_GRID,
    CONCEPT_MOTOR_POSITION,
    CONCEPT_SCAN_COMMAND,
    DETERMINISM_NORMALIZED,
    DETERMINISM_READ,
    MAX_DATA_ROWS,
    MAX_SOURCE_BYTES,
    SCOPE_SCAN,
    SOURCE_TYPE_SCAN_EXPORT,
    ReaderResult,
)
from .inventory import SourceRecord
from .spec import (
    BOM,
    MOTOR_CONCEPTS,
    RULE_COUNTING_TIME_SECONDS,
    RULE_GSCAN_GRID,
    SKIP_DATA_ROWS,
    SKIP_UNREAD_HEADER,
    gscan_grid,
)

PARSER_ID = "bl15_scan_export_v1"

#: A ``#P`` field that is not ``name=value``.
SKIP_UNKEYED_POSITION = "position_field_not_keyed"
#: The basename does not carry a ``_<digits>`` scan index.
SKIP_NO_SCAN_INDEX = "basename_states_no_scan_index"
#: ``#N``. Same measurement as :mod:`bl15.spec` — it is a column count.
SKIP_N_IS_COLUMN_COUNT = "header_N_is_the_column_count"


RULE_BASENAME_STEM_AND_INDEX = (
    "bl15.scans.basename_stem_and_index.v1: a scan export's basename is "
    "`<measurement stem>_<zero-padded scan index>.dat`, so the stem and the "
    "scan index are read from the NAME — nothing inside the file states either. "
    "Measured: 908 of 908 `.dat` basenames in the supplied archive match this "
    "shape, all with a three-digit index. The padding is dropped and the index "
    "reported as an integer; the stem is reported verbatim. A basename that does "
    "NOT match gets no stem and no index, and the reader says so under "
    "`skipped` rather than splitting on the last `_` and hoping."
)
RULE_KEYED_POSITION = (
    "bl15.scans.keyed_motor_position.v1: a `.dat`'s `#P<i>` line carries "
    "`motor=value` fields, so each position names its own motor and no pairing "
    "against an `#O` block is needed OR possible. The value is additionally read "
    "as a number where it parses as one. A field with no `=` is reported under "
    "`skipped` with its position on the line, never split on whitespace and "
    "guessed."
)
RULE_N_IS_COLUMN_COUNT = (
    "bl15.scans.N_is_the_column_count.v1: as in the root acquisition, `#N` "
    "equals the `#L` column count and is NOT a point count — measured 920 of "
    "920 scan blocks across the archive. `bl15.evidence` has no column-count "
    "concept, so it is reported under `skipped` with the measurement rather "
    "than published as `point_count`."
)

NORMALIZATION_RULES: frozenset[str] = frozenset(
    {
        RULE_BASENAME_STEM_AND_INDEX,
        RULE_KEYED_POSITION,
        RULE_COUNTING_TIME_SECONDS,
        RULE_GSCAN_GRID,
    }
)

_HEADER_LINE = re.compile(r"^#([A-Za-z@]+)(\d*)[ \t]*(.*)$")
_COUNTING_TIME = re.compile(r"^(\S+)\s*\(sec\)\s*$")
_SCAN_HEADER = re.compile(r"^(\S+)\s+(.*)$")
_BASENAME = re.compile(r"^(?P<stem>.+)_(?P<index>\d+)\.(?:dat|DAT)$")


def _to_float(text: str) -> float | int | None:
    try:
        value = float(text)
    except ValueError:
        return None
    if value.is_integer() and "." not in text and "e" not in text.casefold():
        return int(value)
    return value


def stem_and_index(basename: str) -> tuple[str | None, int | None]:
    """``('03_01_ZZ1_acid', 1)`` for ``03_01_ZZ1_acid_001.dat``.

    ``(None, None)`` when the basename does not match. See
    :data:`RULE_BASENAME_STEM_AND_INDEX` for why nothing is guessed.
    """
    match = _BASENAME.match(basename)
    if not match:
        return None, None
    return match.group("stem"), int(match.group("index"))


def own_scan_number(lines: list[str]) -> str | None:
    """The SPEC scan number a per-scan export states on its own ``#S`` line.

    ``None`` unless exactly one ``#S`` line carries a number. Written without leading
    zeros, as the acquisition file's ``#S`` numbers are compared.
    """
    numbers = set()
    for line in lines:
        if line.startswith("#S") and not line[2:3].isalnum():
            match = _SCAN_HEADER.match(line[2:].strip())
            if match:
                numbers.add(match.group(1))
    if len(numbers) != 1:
        return None
    (number,) = numbers
    return str(int(number)) if number.isdigit() else None


def read_scan_export(
    record: SourceRecord, text: str, *, id_prefix: str = ""
) -> ReaderResult:
    """Read one ``.dat`` per-scan export. Never raises."""
    measured = max(record.size_bytes, len(text.encode("utf-8", "replace")))
    if measured > MAX_SOURCE_BYTES:
        return refusal(
            source_path=record.archive_path,
            parser_id=PARSER_ID,
            reason=oversize_reason(measured, MAX_SOURCE_BYTES),
        )

    lines = text.lstrip(BOM).splitlines()
    if any(line.startswith("#F") for line in lines):
        return refusal(
            source_path=record.archive_path,
            parser_id=PARSER_ID,
            reason=(
                "not_a_scan_export: this file declares its own name with `#F`, "
                "which makes it a ROOT SPEC ACQUISITION and not a per-scan "
                "export. Read it with `bl15.spec` instead — its positions are "
                "paired against an `#O` block, which this reader does not do"
            ),
        )
    if not any(line.startswith("#S") for line in lines):
        return refusal(
            source_path=record.archive_path,
            parser_id=PARSER_ID,
            reason=(
                "not_a_scan_export: no `#S` scan header appears anywhere in "
                "this file, so nothing in it states which scan it is"
            ),
        )

    builder = EvidenceBuilder(
        source_path=record.archive_path,
        source_type=SOURCE_TYPE_SCAN_EXPORT,
        parser_id=PARSER_ID,
        id_prefix=id_prefix,
    )

    stem, index = stem_and_index(record.basename)
    # EVERY statement in a scan export is about ONE scan — the one the file ITSELF
    # names on its own `#S` line, which is the acquisition file's SPEC scan number.
    # Stamped once here (`EvidenceBuilder.scan`, `bl15.mapping.RULE_CARDINALITY` v2).
    #
    # NOT THE BASENAME INDEX, and that is a correction (2026-09-23): v1 took `_001` to
    # be `#S 1`, which nothing establishes — a SPEC file reopened and appended can hold
    # `#S 6` for the scan exported as `_001`. A file stating more than one `#S`, or none
    # that is a number, names no single scan, so its statements stay unestablished and
    # are compared with every reading of the measurement.
    builder.scan = own_scan_number(lines)
    if stem is None:
        builder.skip(
            reason=SKIP_NO_SCAN_INDEX,
            locator=f"basename `{record.basename}`",
            detail=(
                "the basename does not match `<stem>_<digits>.dat`, so neither "
                "the measurement stem nor the scan index could be read from it. "
                "Nothing is inferred; the scan's own headers are still read"
            ),
        )
    else:
        builder.add(
            locator=f"basename `{record.basename}` (stem + scan index {index})",
            raw_literal=record.basename,
            # `acquisition_target` and NOT `scan_count`. The basename states
            # WHICH measurement this scan belongs to and WHICH scan it is; it
            # states nothing about HOW MANY scans there are, and `scan_count`
            # means the latter (it is what a macro's `IrL3_xas ... nbrScan ...`
            # argument states). `bl15.evidence` has no `scan_index` concept, so
            # the index travels in `normalized_value` and in the locator rather
            # than under a concept that would misname it.
            concept=CONCEPT_ACQUISITION_TARGET,
            determinism=DETERMINISM_NORMALIZED,
            normalized_value={"measurement_stem": stem, "scan_index": index},
            normalization_rule=RULE_BASENAME_STEM_AND_INDEX,
            scope=SCOPE_SCAN,
            measurement_stem=stem,
        )

    row_count = 0
    row_first_line: int | None = None
    row_cap_hit = False
    unread_headers: dict[str, list[int]] = {}
    n_headers: list[int] = []
    n_values: list[str] = []

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
            unread_headers.setdefault("unparsed", []).append(number)
            continue
        key, suffix, payload = match.group(1), match.group(2), match.group(3)
        payload = payload.rstrip()

        if key == "S" and not suffix:
            scan_match = _SCAN_HEADER.match(payload)
            command = scan_match.group(2).strip() if scan_match else ""
            if command:
                builder.add(
                    locator=f"line {number} header #S",
                    raw_literal=command,
                    concept=CONCEPT_SCAN_COMMAND,
                    scope=SCOPE_SCAN,
                    measurement_stem=stem,
                )
                grid = gscan_grid(command)
                if grid is not None:
                    builder.add(
                        locator=f"line {number} header #S gscan grid literal",
                        raw_literal=grid,
                        concept=CONCEPT_ENERGY_GRID,
                        scope=SCOPE_SCAN,
                        measurement_stem=stem,
                    )
            continue

        if key == "D" and not suffix:
            builder.add(
                locator=f"line {number} header #D",
                raw_literal=payload.strip(),
                concept=CONCEPT_ACQUISITION_TIMESTAMP,
                scope=SCOPE_SCAN,
                measurement_stem=stem,
            )
            continue

        if key == "T" and not suffix:
            seconds = None
            time_match = _COUNTING_TIME.match(payload.strip())
            if time_match:
                seconds = _to_float(time_match.group(1))
            builder.add(
                locator=f"line {number} header #T",
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
                scope=SCOPE_SCAN,
                measurement_stem=stem,
            )
            continue

        if key == "P" and suffix.isdigit():
            for position, field in enumerate(payload.split()):
                if "=" not in field:
                    builder.skip(
                        reason=SKIP_UNKEYED_POSITION,
                        locator=(
                            f"line {number} header #P{suffix} field {position}"
                        ),
                        raw_literal=field,
                        detail=(
                            "a `.dat` position field carries `motor=value`; "
                            "this one has no `=`, so no motor names it and "
                            "nothing is guessed from its position on the line"
                        ),
                    )
                    continue
                name, _, value = field.partition("=")
                builder.add(
                    locator=(
                        f"line {number} header #P{suffix} key `{name}` "
                        f"(field {position})"
                    ),
                    raw_literal=value,
                    concept=MOTOR_CONCEPTS.get(name, CONCEPT_MOTOR_POSITION),
                    determinism=DETERMINISM_NORMALIZED,
                    normalized_value=_to_float(value),
                    normalization_rule=RULE_KEYED_POSITION,
                    scope=SCOPE_SCAN,
                    measurement_stem=stem,
                    item=name,
                )
            continue

        if key == "N" and not suffix:
            n_headers.append(number)
            n_values.append(payload.strip())
            continue

        if key == "L" and not suffix:
            for position, column in enumerate(payload.split()):
                builder.add(
                    locator=f"line {number} header #L column {position}",
                    raw_literal=column,
                    concept=CONCEPT_DETECTOR_COLUMN,
                    scope=SCOPE_SCAN,
                    measurement_stem=stem,
                    item=f"column {position}",
                )
            continue

        unread_headers.setdefault(f"#{key}{suffix}", []).append(number)

    if row_count:
        builder.skip(
            reason=SKIP_DATA_ROWS,
            locator=(
                f"data block, lines {row_first_line}.."
                f"{(row_first_line or 0) + row_count - 1}"
            ),
            detail=(
                f"{row_count} data rows were counted and deliberately not read "
                f"into evidence"
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
    if n_headers:
        builder.skip(
            reason=SKIP_N_IS_COLUMN_COUNT,
            locator=f"line {n_headers[0]} header #N",
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

    # `emiss`, `filter` and `Sx`/`Sy`/`Sz`/`Sr` are named through the SAME
    # `MOTOR_CONCEPTS` table `bl15.spec` pairs its `#O` names against — imported,
    # not copied. That sharing is what lets a `.dat`'s keyed positions be used to
    # verify the acquisition reader's index-and-column pairing, which is the one
    # independent check available for it. Asserted in
    # `test_bl15_readers.py`, not at runtime: a reader must never raise.
    return builder.result()

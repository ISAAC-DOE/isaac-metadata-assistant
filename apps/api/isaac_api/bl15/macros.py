"""SPEC ``.mac`` acquisition scripts, **read as text. Nothing is ever executed.**

**NOTHING IN THIS MODULE EVALUATES, IMPORTS, COMPILES OR INTERPRETS ANYTHING.** A
macro is a program written for a beamline control system, and it arrives from
outside this repository. It is split into lines, matched against a fixed set of
anchored patterns, and reported. There is no ``eval``, no ``exec``, no subprocess,
no dynamic import and no dispatch table keyed on file content anywhere in this
file, and `test_bl15_readers.py` asserts that by reading this module's own source.

**``newfile`` DECLARATIONS ARE THE MEASUREMENT BOUNDARIES.** Measured over the
supplied archive: **156** ``newfile`` declarations across **60** macro files (59
``.mac`` plus the extensionless ``run29``), **95** distinct targets, **29** macros
declaring more than one, a maximum of **8** (``run15.mac``), and **4** declaring
**none at all** — ``Ir_XAS.mac``, ``trigger.mac``, ``motors_cpy_pre77.mac`` and
``motors_cpy_pre112.mac``.

**ZERO BLOCKS IS A RESULT, NOT A FAILURE.** Four real macros declare no target,
and each is a legitimate file: two define procedures, two restore motor
positions. A reader that treated zero as an error would refuse four sources that
have nothing wrong with them; a reconstruction that mapped one macro to one Run
would have produced 60 Runs for 95 declared measurements and turned four
non-measurements into measurements. ``macro`` is deliberately absent from
:data:`~isaac_api.bl15.evidence.RUN_CANDIDATE_SOURCE_TYPES`.

**COMMANDS ARE GROUPED INTO THE BLOCK THEY FOLLOW.** Everything between one
``newfile`` and the next belongs to that declaration, and its locator says so
(``line 42 in newfile block 2``). Commands *before* the first ``newfile`` belong
to no block — ``run15.mac`` opens with ``qdo Ir_XAS.mac`` and an absolute
``mv Sx ... Sy ... Sz ...`` before declaring anything — so they are reported at
:data:`~isaac_api.bl15.evidence.SCOPE_BEAMTIME` with ``measurement_stem`` left
``None``. Attributing them to the first block would assert a scope the file does
not state.

**THE ``IrL3_xas`` SIGNATURE IS READ FROM THE ARCHIVE'S OWN HELP TEXT.**
``Ir_XAS.mac`` prints it: ``IrL3_xas  cntSec  nbrScan  emission  nbrFilter``. So
``IrL3_xas 0.5 2 <emission> <filter>`` states 0.5 s per point, 2 scans, an
emission energy and a filter number — four separate statements at one locator,
each with a named rule citing that help text. **The signature is not guessed
and not inferred from
argument magnitudes**; if the archive did not document it, this reader would
report the command line verbatim and nothing else.

**A ``def`` BLOCK MAKES THE FILE A METHOD DEFINITION**, and the energy grid inside
it is read as a literal: ``XAS_MAIN_GRID = "<start> <stop> <step> ..."``.
``Ir_XAS.mac`` contains **two** such assignments (``IrL3_xas`` and
``IrL3_short_xas`` declare different grids), so both are reported, each at its own
line. Nothing decides which one a given acquisition used — that would require
knowing which procedure was called, which the macro does not state.
"""

from __future__ import annotations

import re

from ._emit import EvidenceBuilder, oversize_reason, refusal
from .evidence import (
    CONCEPT_ACQUISITION_METHOD,
    CONCEPT_ACQUISITION_TARGET,
    CONCEPT_COUNTING_TIME,
    CONCEPT_EMISSION_ENERGY,
    CONCEPT_ENERGY_GRID,
    CONCEPT_FILTER,
    CONCEPT_MOTOR_POSITION,
    CONCEPT_SAMPLE_POSITION,
    CONCEPT_SCAN_COUNT,
    CONCEPT_TRIGGER,
    DETERMINISM_NORMALIZED,
    MAX_SOURCE_BYTES,
    SCOPE_BEAMTIME,
    SCOPE_MEASUREMENT,
    SOURCE_TYPE_ACQUISITION_METHOD_MACRO,
    SOURCE_TYPE_MACRO,
    ReaderResult,
)
from .inventory import SourceRecord
from .spec import BOM

PARSER_ID = "bl15_macro_v1"

#: A line no pattern in this reader claimed.
SKIP_UNREAD_COMMAND = "macro_line_not_read"
#: A recognised command whose arguments do not match its documented signature.
SKIP_ARGUMENT_COUNT = "command_argument_count_unexpected"
#: A ``mv``/``mvr``/``umv`` with an odd number of arguments.
SKIP_UNPAIRED_MOTOR_ARGUMENTS = "motor_move_arguments_unpaired"


RULE_NEWFILE_TARGET = (
    "bl15.macros.newfile_target.v1: `newfile <target>` declares the measurement "
    "file the commands that follow will write into, so the target is the "
    "measurement stem this block INTENDS. It is an intention and not an "
    "observation: measured over the archive, 9 declared targets have no "
    "acquisition file and 9 acquisitions have no declared target, and the "
    "`29`-`32` and `44`-`46` families are the same measurements under different "
    "names. The declaration is read; nothing is reconciled here."
)
RULE_QDO_INCLUDE = (
    "bl15.macros.qdo_include.v1: `qdo <file>` includes another macro, so the "
    "named file is read as the acquisition method this macro relies on. The "
    "include is NOT followed — this reader is handed one file's text and opens "
    "nothing."
)
RULE_MOTOR_MOVE = (
    "bl15.macros.motor_move.v1: `mv`/`umv` state ABSOLUTE motor destinations and "
    "`mvr` a RELATIVE offset, as `<motor> <value>` pairs. Each pair is one "
    "statement, and the absolute/relative distinction is preserved in "
    "`normalized_value` rather than collapsed — adding a `mvr` offset to a "
    "preceding `mv` would compute a position the file never states. An odd "
    "argument count is reported under `skipped`, never paired up by guesswork."
)
RULE_IRL3_XAS_SIGNATURE = (
    "bl15.macros.irl3_xas_signature.v1: `IrL3_xas cntSec nbrScan emission "
    "nbrFilter`, read from the acquisition method's OWN help text in "
    "`Ir_XAS.mac` (`printf(\"    IrL3_xas  cntSec  nbrScan  emission  "
    "nbrFilter\\n\\n\")`). Four statements at one locator: counting time in "
    "seconds, scan count, emission energy in eV, and filter number. The unit "
    "for emission comes from the same file, which prints `Moving emission "
    "energy to %f eV`. A call with a different argument count is reported under "
    "`skipped` and yields no statement — the signature is documented, not "
    "inferred from magnitudes."
)
RULE_XAS_GRID_LITERAL = (
    "bl15.macros.xas_grid_literal.v1: `XAS_MAIN_GRID = \"<grid>\"` inside a "
    "`def` block states the energy grid that block's `gscan` will use. The "
    "quoted literal is reported verbatim. `Ir_XAS.mac` declares TWO, for "
    "`IrL3_xas` and `IrL3_short_xas`; both are reported and neither is chosen, "
    "because the macro does not state which procedure any acquisition called."
)
RULE_DEF_METHOD = (
    "bl15.macros.def_method.v1: `def <name> '{` declares a procedure, so the "
    "name is read as an acquisition method this file DEFINES. A file that "
    "defines rather than acquires is not a measurement, which is why "
    "`Ir_XAS.mac` and `trigger.mac` declare no `newfile` at all."
)

NORMALIZATION_RULES: frozenset[str] = frozenset(
    {
        RULE_NEWFILE_TARGET,
        RULE_QDO_INCLUDE,
        RULE_MOTOR_MOVE,
        RULE_IRL3_XAS_SIGNATURE,
        RULE_XAS_GRID_LITERAL,
        RULE_DEF_METHOD,
    }
)

#: Most ``newfile`` blocks one macro may declare. Measured maximum is 8.
MAX_NEWFILE_BLOCKS = 512

# Every pattern is ANCHORED at the start of a (stripped) line and matches a
# literal command word. There is no pattern built from file content.
_NEWFILE = re.compile(r"^newfile[ \t]+(\S+)[ \t]*(.*)$")
_QDO = re.compile(r"^qdo[ \t]+(\S+)")
_MOVE = re.compile(r"^(mvr|umv|mv)[ \t]+(.+)$")
_TRIGGER = re.compile(r"^trigger[ \t]*$")

#: Acquisition commands whose ARGUMENT SIGNATURE this archive documents, and
#: therefore the only ones whose arguments may be read as named statements.
#: Extending this set requires a source that states the new command's signature
#: — reading four roles off an unknown command's four arguments would be a guess
#: dressed as a normalisation, and a plausible one, which is worse.
DOCUMENTED_XAS_COMMANDS: tuple[str, ...] = ("IrL3_xas", "IrL3_short_xas")

_IRL3 = re.compile(
    r"^(" + "|".join(DOCUMENTED_XAS_COMMANDS) + r")[ \t]+(.+)$"
)
_DEF = re.compile(r"^def[ \t]+(\S+)")
_GRID = re.compile(r"""^XAS_MAIN_GRID[ \t]*=[ \t]*"([^"]*)"[ \t]*$""")
_COMMENT = re.compile(r"^#")

#: Motors whose destination is a statement about the SAMPLE's position rather
#: than about a generic axis. Same four the ``.dat`` exports name.
_SAMPLE_MOTORS = frozenset({"Sx", "Sy", "Sz", "Sr"})


def _to_float(text: str) -> float | int | None:
    try:
        value = float(text)
    except ValueError:
        return None
    if value.is_integer() and "." not in text and "e" not in text.casefold():
        return int(value)
    return value


def read_macro(
    record: SourceRecord, text: str, *, id_prefix: str = ""
) -> ReaderResult:
    """Read one ``.mac`` (or extensionless) macro as text. Never raises."""
    measured = max(record.size_bytes, len(text.encode("utf-8", "replace")))
    if measured > MAX_SOURCE_BYTES:
        return refusal(
            source_path=record.archive_path,
            parser_id=PARSER_ID,
            reason=oversize_reason(measured, MAX_SOURCE_BYTES),
        )

    lines = text.lstrip(BOM).splitlines()
    if any(line.startswith("#F") or line.startswith("#S ") for line in lines):
        return refusal(
            source_path=record.archive_path,
            parser_id=PARSER_ID,
            reason=(
                "not_a_macro: this file carries SPEC DATA headers (`#F`/`#S`), "
                "so it is an acquisition or a scan export, not a script. Read "
                "it with `bl15.spec` or `bl15.scans`"
            ),
        )

    defines = [line for line in lines if _DEF.match(line.strip())]
    source_type = (
        SOURCE_TYPE_ACQUISITION_METHOD_MACRO if defines else SOURCE_TYPE_MACRO
    )

    builder = EvidenceBuilder(
        source_path=record.archive_path,
        source_type=source_type,
        parser_id=PARSER_ID,
        id_prefix=id_prefix,
    )

    #: ``None`` until the first ``newfile``; commands before it belong to no
    #: block and are scoped to the beamtime rather than to a measurement.
    block_index: int | None = None
    block_stem: str | None = None
    unread: dict[int, str] = {}
    blocks: list[str] = []

    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or _COMMENT.match(line):
            continue

        def place() -> tuple[str, str, str | None]:
            """Locator suffix, scope and stem for a command in the current block."""
            if block_index is None:
                return (
                    " (before any newfile declaration)",
                    SCOPE_BEAMTIME,
                    None,
                )
            return (
                f" in newfile block {block_index}",
                SCOPE_MEASUREMENT,
                block_stem,
            )

        match = _NEWFILE.match(line)
        if match:
            if len(blocks) >= MAX_NEWFILE_BLOCKS:
                builder.skip(
                    reason="too_many_newfile_blocks",
                    locator=f"line {number}",
                    detail=(
                        f"this macro declares more than {MAX_NEWFILE_BLOCKS} "
                        f"`newfile` targets; later declarations were not read"
                    ),
                    ceiling=MAX_NEWFILE_BLOCKS,
                )
                break
            block_index = len(blocks)
            block_stem = match.group(1)
            blocks.append(block_stem)
            builder.add(
                locator=f"line {number} newfile block {block_index}",
                raw_literal=match.group(1),
                concept=CONCEPT_ACQUISITION_TARGET,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=block_stem,
                normalization_rule=RULE_NEWFILE_TARGET,
                scope=SCOPE_MEASUREMENT,
                measurement_stem=block_stem,
            )
            trailing = match.group(2).strip()
            if trailing:
                builder.skip(
                    reason=SKIP_ARGUMENT_COUNT,
                    locator=f"line {number} newfile block {block_index}",
                    raw_literal=trailing,
                    detail=(
                        "`newfile` carried extra arguments after its target; "
                        "they were not read"
                    ),
                )
            continue

        match = _DEF.match(line)
        if match:
            builder.add(
                locator=f"line {number} `def`",
                raw_literal=match.group(1),
                concept=CONCEPT_ACQUISITION_METHOD,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=match.group(1),
                normalization_rule=RULE_DEF_METHOD,
                scope=SCOPE_BEAMTIME,
            )
            continue

        match = _GRID.match(line)
        if match:
            builder.add(
                locator=f"line {number} `XAS_MAIN_GRID`",
                raw_literal=match.group(1),
                concept=CONCEPT_ENERGY_GRID,
                scope=SCOPE_BEAMTIME,
            )
            continue

        match = _QDO.match(line)
        if match:
            suffix, scope, stem = place()
            builder.add(
                locator=f"line {number} `qdo`{suffix}",
                raw_literal=match.group(1),
                concept=CONCEPT_ACQUISITION_METHOD,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=match.group(1),
                normalization_rule=RULE_QDO_INCLUDE,
                scope=scope,
                measurement_stem=stem,
            )
            continue

        match = _IRL3.match(line)
        if match:
            _read_irl3(
                builder,
                command=match.group(1),
                arguments=match.group(2).split(),
                line_number=number,
                place=place,
            )
            continue

        match = _MOVE.match(line)
        if match:
            _read_move(
                builder,
                verb=match.group(1),
                arguments=match.group(2).split(),
                line_number=number,
                place=place,
            )
            continue

        if _TRIGGER.match(line):
            suffix, scope, stem = place()
            builder.add(
                locator=f"line {number} `trigger`{suffix}",
                raw_literal=line,
                concept=CONCEPT_TRIGGER,
                scope=scope,
                measurement_stem=stem,
            )
            continue

        unread[number] = line

    if unread:
        first = min(unread)
        builder.skip(
            reason=SKIP_UNREAD_COMMAND,
            locator=f"line {first}",
            detail=(
                f"{len(unread)} line(s) matched no command this reader reads. "
                f"They are counted rather than interpreted; a macro is a "
                f"program and this reader claims only the commands it names"
            ),
            line_count=len(unread),
            first_line=unread[first],
            lines=sorted(unread),
        )

    result = builder.result()
    return result


def newfile_targets(text: str) -> tuple[str, ...]:
    """Every ``newfile`` target in declaration order. **May be empty.**

    Exposed separately from :func:`read_macro` because a relationship pass wants
    the target list without the command detail, and because four real macros
    legitimately answer ``()``.
    """
    return tuple(
        match.group(1)
        for match in (
            _NEWFILE.match(line.strip()) for line in text.lstrip(BOM).splitlines()
        )
        if match
    )


def _read_irl3(
    builder: EvidenceBuilder,
    *,
    command: str,
    arguments: list[str],
    line_number: int,
    place,
) -> None:
    suffix, scope, stem = place()
    locator = f"line {line_number} `{command}`{suffix}"
    if len(arguments) != 4:
        builder.skip(
            reason=SKIP_ARGUMENT_COUNT,
            locator=locator,
            raw_literal=" ".join(arguments),
            detail=(
                f"`{command}` is documented in `Ir_XAS.mac` as taking four "
                f"arguments (cntSec nbrScan emission nbrFilter); this call "
                f"carries {len(arguments)}. No statement is read from it — "
                f"assigning the arguments by magnitude would be a guess"
            ),
            argument_count=len(arguments),
            expected_argument_count=4,
        )
        return
    cnt_sec, nbr_scan, emission, nbr_filter = arguments
    for literal, concept, value, unit in (
        (cnt_sec, CONCEPT_COUNTING_TIME, _to_float(cnt_sec), "s"),
        (nbr_scan, CONCEPT_SCAN_COUNT, _to_float(nbr_scan), None),
        (emission, CONCEPT_EMISSION_ENERGY, _to_float(emission), "eV"),
        (nbr_filter, CONCEPT_FILTER, _to_float(nbr_filter), None),
    ):
        builder.add(
            locator=f"{locator} argument `{literal}`",
            raw_literal=literal,
            concept=concept,
            determinism=DETERMINISM_NORMALIZED,
            normalized_value=value,
            unit=unit if value is not None else None,
            normalization_rule=RULE_IRL3_XAS_SIGNATURE,
            scope=scope,
            measurement_stem=stem,
        )


def _read_move(
    builder: EvidenceBuilder,
    *,
    verb: str,
    arguments: list[str],
    line_number: int,
    place,
) -> None:
    suffix, scope, stem = place()
    locator = f"line {line_number} `{verb}`{suffix}"
    if len(arguments) % 2 != 0:
        builder.skip(
            reason=SKIP_UNPAIRED_MOTOR_ARGUMENTS,
            locator=locator,
            raw_literal=" ".join(arguments),
            detail=(
                f"`{verb}` takes `<motor> <value>` pairs and this call carries "
                f"{len(arguments)} arguments, an odd number. Nothing is paired "
                f"up: one missing value would shift every later value onto the "
                f"wrong motor"
            ),
            argument_count=len(arguments),
        )
        return
    relative = verb == "mvr"
    for position in range(0, len(arguments), 2):
        motor = arguments[position]
        literal = arguments[position + 1]
        value = _to_float(literal)
        builder.add(
            locator=f"{locator} motor `{motor}`",
            raw_literal=literal,
            # `Sx`/`Sy`/`Sz`/`Sr` are the sample stage — the same four the `.dat`
            # exports name — so their destinations are sample-position
            # statements. Every other motor is a generic `motor_position`,
            # deliberately: `motors_cpy_pre77.mac` moves `c1p`, `c1y`, `c2p` …,
            # which are spectrometer crystals and not the sample, and calling
            # those a sample position would be a false statement about where
            # the sample was.
            concept=(
                CONCEPT_SAMPLE_POSITION
                if motor in _SAMPLE_MOTORS
                else CONCEPT_MOTOR_POSITION
            ),
            determinism=DETERMINISM_NORMALIZED,
            normalized_value={
                "motor": motor,
                "value": value,
                "relative": relative,
            },
            normalization_rule=RULE_MOTOR_MOVE,
            scope=scope,
            measurement_stem=stem,
        )

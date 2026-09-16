"""What KIND of source an archive entry is — **content first, name second.**

**THE CORPUS SETTLES THIS, AND IT SETTLES IT AGAINST THE NAME.** Measured on the
supplied archive (``docs/evidence/bl15-2-corpus-characterization-2026-09-16.md``
§2.1):

* ``run29`` has **no extension** and is a **macro** — its first non-blank line is
  ``qdo Ir_XAS.mac``.
* ``alignment`` has **no extension** and is a **SPEC acquisition** — its first
  line is ``#F alignment``, and it carries 233 scans.
* ``IrO2_5wpc_pellet_transmission`` has no extension and is a SPEC acquisition of
  a reference pellet.
* ``run29.mac`` and ``run29.mac.mac`` are two DIFFERENT files (4,059 and 4,013
  bytes) whose names suggest one.

A classifier keying on the extension is wrong about all four. So
:func:`classify` reads the beginning of the file when the caller supplies it,
and falls back to the path only when it does not — and it **says which it did**,
in :attr:`Classification.confidence`, so a surface can tell a content decision
from a name guess.

**EVERY CLASSIFICATION IS OVERRIDABLE, ALWAYS.** :attr:`Classification.overridable`
is a constant ``True``. A scientist looking at their own archive knows things no
heuristic can: that an extensionless file is a macro they wrote, that a
``_transmission`` file is a standard rather than a sample. Refusing them the
correction would make this module an authority it is not
(``CLAUDE.md`` §1: the deterministic truth path is the only authority, and this
is not it).

**RUN CANDIDACY IS NOT CLASSIFICATION, and the two are deliberately separate.**
:data:`~isaac_api.bl15.evidence.RUN_CANDIDATE_SOURCE_TYPES` holds
``spec_acquisition`` and nothing else. ``macro`` is **never** a run candidate:
one ``.mac`` in this corpus declares up to EIGHT measurements (``run15.mac``) and
four declare none, so one macro is neither one run nor zero. ``scan_export`` is
never a run candidate either: 908 ``.dat`` files are the scan children of ~92
measurements, and promoting each to a Run would invent 816 measurements nobody
performed. Deciding candidacy is :mod:`bl15.reconstruct`'s job; this module only
says what a file IS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .evidence import (
    SOURCE_TYPE_ACQUISITION_METHOD_MACRO,
    SOURCE_TYPE_ALIGNMENT,
    SOURCE_TYPE_BEAMTIME_NOTES,
    SOURCE_TYPE_DETECTOR_PRODUCT,
    SOURCE_TYPE_MACRO,
    SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO,
    SOURCE_TYPE_PROCESSED_SPECTRUM,
    SOURCE_TYPE_SHARED_README,
    SOURCE_TYPE_SPEC_ACQUISITION,
    SOURCE_TYPE_STANDARD_OR_REFERENCE,
    SOURCE_TYPE_SCAN_EXPORT,
    SOURCE_TYPE_UNKNOWN,
    SOURCE_TYPES,
)
from .inventory import SourceRecord

CLASSIFIER_ID = "bl15_content_led_classifier_v1"

#: The classification was decided by reading the file's own bytes.
CONFIDENCE_CONTENT = "content"
#: No content was supplied, so the decision rests on the path alone. **A
#: path-confidence classification is a lead, not a fact** — the four measured
#: counterexamples above are all path-confidence mistakes.
CONFIDENCE_PATH = "path"
#: Neither content nor path decided it.
CONFIDENCE_UNKNOWN = "unknown"

CONFIDENCES: frozenset[str] = frozenset(
    {CONFIDENCE_CONTENT, CONFIDENCE_PATH, CONFIDENCE_UNKNOWN}
)


@dataclass(frozen=True)
class Classification:
    """What one entry is, why, and how firmly.

    :attr:`reason` is written FOR A SCIENTIST and names the evidence it used —
    *"the first header line is `#F`"*, not *"matched rule 7"*. It reaches a
    review surface verbatim, and a reason that does not name its evidence is
    indistinguishable from an assertion.
    """

    source_type: str
    reason: str
    confidence: str
    #: Always ``True``. Declared as a field rather than a constant so it appears
    #: in the wire shape a surface renders: a classification a scientist cannot
    #: see is correctable is one they will not correct.
    overridable: bool = True
    classifier_id: str = CLASSIFIER_ID

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"unknown source_type: {self.source_type!r}")
        if self.confidence not in CONFIDENCES:
            raise ValueError(f"unknown confidence: {self.confidence!r}")

    def to_state(self) -> dict:
        return {
            "source_type": self.source_type,
            "reason": self.reason,
            "confidence": self.confidence,
            "overridable": self.overridable,
            "classifier_id": self.classifier_id,
        }


# --- content probes ----------------------------------------------------------

_HEADER = re.compile(r"^#([A-Z])(\d*)\b")
_KEYED_POSITION = re.compile(r"^#P\d+\s+\S+=")
_TWO_COLUMN_NUMERIC = re.compile(
    r"^\s*[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
    r"\s+[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?\s*$"
)
_MACRO_COMMAND = re.compile(
    r"^\s*(qdo|newfile|umv|mvr|mv|trigger|ascan|a2scan|loopscan|gscan|"
    r"IrL3_xas|IrL3_short_xas|plotselect|sleep)\b"
)
_ALIGNMENT_STEM = re.compile(r"(?:^|[_\-])align", re.IGNORECASE)
_STANDARD_STEM = re.compile(
    r"(?:pellet|transmission|oldPellet|standard)", re.IGNORECASE
)
_NOTES_STEM = re.compile(r"(?:herfd|notes|beam\s*\d|bl\s*15)", re.IGNORECASE)


def _significant_lines(head_text: str, limit: int = 400) -> list[str]:
    """Non-blank lines of the head, in order, bounded."""
    out = []
    for line in head_text.splitlines():
        if line.strip():
            out.append(line)
            if len(out) >= limit:
                break
    return out


def _has_def_block(lines: list[str]) -> bool:
    return any(re.match(r"^\s*def\s+\S+", line) for line in lines)


# --- the classifier ---------------------------------------------------------


def classify(
    record: SourceRecord, *, head_text: str | None
) -> Classification:
    """Decide what ``record`` is. Never raises.

    ``head_text`` is the beginning of the file, decoded by the CALLER (the walk
    owns decoding; see :class:`~isaac_api.bl15.inventory.ArchiveLimits.head_bytes`).
    Pass ``None`` when no content is available — the result is then capped at
    :data:`CONFIDENCE_PATH` and the reason says so.
    """
    basename = record.basename
    extension = (record.extension or "").casefold()
    stem = basename[: -(len(extension) + 1)] if extension else basename

    if head_text is None:
        return _classify_by_path(record, stem, extension)

    lines = _significant_lines(head_text)
    if not lines:
        return Classification(
            source_type=SOURCE_TYPE_UNKNOWN,
            reason=(
                "the file's opening bytes contain no non-blank line, so nothing "
                "in its content identifies it"
            ),
            confidence=CONFIDENCE_CONTENT,
        )

    # `.mca` IS TESTED BEFORE THE `#F` TEST, AND THE ORDER IS THE POINT.
    #
    # **Do not "fix" this back to content-first.** Both `.mca` detector products
    # in the measured archive BEGIN WITH `#F` — they are SPEC-format dumps — so a
    # classifier that reaches the `#F` branch first calls them SPEC acquisitions,
    # which was measured to produce two spurious measurement units and two false
    # name conflicts in the relationship layer.
    #
    # This does NOT weaken the content-led rule, and the distinction is worth
    # stating precisely: `run29` and `alignment` need CONTENT because their names
    # carry nothing at all (one has no extension and is a macro; the other has no
    # extension and is an acquisition). `.mca` is the opposite case — the
    # extension is the MORE SPECIFIC fact, and the content it shares with an
    # acquisition is the less specific one. Content-led means "prefer the more
    # specific evidence", not "never look at the name".
    if extension == "mca":
        return Classification(
            source_type=SOURCE_TYPE_DETECTOR_PRODUCT,
            reason=(
                "a detector product (`.mca`, a multichannel-analyser dump). Its "
                "content is NOT read by this package — and note that both such "
                "files in the measured archive open with a SPEC `#F` header, so "
                "the extension is what tells them apart from an acquisition"
            ),
            confidence=CONFIDENCE_CONTENT,
        )

    first = lines[0]
    header_keys = [
        m.group(0) for m in (_HEADER.match(line) for line in lines) if m
    ]
    has_F = any(line.startswith("#F") for line in lines)
    has_S = any(line.startswith("#S") for line in lines)
    keyed_positions = any(_KEYED_POSITION.match(line) for line in lines)

    # 1. A SPEC acquisition declares its own filename with `#F`. That is the
    #    single most reliable marker in this corpus and the one that rescues
    #    `alignment`.
    if has_F:
        if _ALIGNMENT_STEM.search(stem):
            return Classification(
                source_type=SOURCE_TYPE_ALIGNMENT,
                reason=(
                    "a SPEC acquisition (it declares its own filename with an "
                    f"`#F` header) whose name says it is an alignment scan: "
                    f"`{stem}`"
                ),
                confidence=CONFIDENCE_CONTENT,
            )
        if _STANDARD_STEM.search(stem):
            return Classification(
                source_type=SOURCE_TYPE_STANDARD_OR_REFERENCE,
                reason=(
                    "a SPEC acquisition (it declares its own filename with an "
                    "`#F` header) whose name says it is a pellet / "
                    f"transmission reference rather than a sample: `{stem}`"
                ),
                confidence=CONFIDENCE_CONTENT,
            )
        return Classification(
            source_type=SOURCE_TYPE_SPEC_ACQUISITION,
            reason=(
                "a SPEC acquisition: its first header block declares the file's "
                "own name with `#F`, which no other format in this archive does"
            ),
            confidence=CONFIDENCE_CONTENT,
        )

    # 2. A scan export has the same `#S`/`#D`/`#T`/`#N`/`#L` header WITHOUT an
    #    `#F`, and its `#P` lines are `name=value` keyed rather than paired
    #    against an `#O` block.
    if has_S or keyed_positions:
        if keyed_positions:
            detail = (
                "its `#P0` line is `name=value` keyed (`energy=...`), which is "
                "the per-scan export form and not the acquisition file's "
                "separated `#O`/`#P` blocks"
            )
        else:
            detail = (
                "it carries an `#S` scan header but declares no `#F` filename, "
                "which is the per-scan export form"
            )
        return Classification(
            source_type=SOURCE_TYPE_SCAN_EXPORT,
            reason=f"a single-scan export: {detail}",
            confidence=CONFIDENCE_CONTENT,
        )

    # 3. Macros. A `def` block makes the file a method definition rather than a
    #    run of measurements — `Ir_XAS.mac` defines `IrL3_xas` and acquires
    #    nothing, and `trigger.mac` defines `trigger`.
    macro_commands = [line for line in lines if _MACRO_COMMAND.match(line)]
    has_newfile = any(re.match(r"^\s*newfile\b", line) for line in lines)
    if _has_def_block(lines):
        return Classification(
            source_type=SOURCE_TYPE_ACQUISITION_METHOD_MACRO,
            reason=(
                "an acquisition-method macro: it opens a `def` block, so it "
                "DEFINES a procedure rather than acquiring anything. It is "
                "never a measurement"
            ),
            confidence=CONFIDENCE_CONTENT,
        )
    if macro_commands and not has_newfile:
        moves = [
            line for line in lines if re.match(r"^\s*(umv|mvr|mv)\b", line)
        ]
        if len(moves) == len(macro_commands):
            return Classification(
                source_type=SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO,
                reason=(
                    f"a motor snapshot: every one of its {len(moves)} commands "
                    "is a motor move and it declares no `newfile`, so it "
                    "restores positions rather than acquiring data"
                ),
                confidence=CONFIDENCE_CONTENT,
            )
    if macro_commands:
        return Classification(
            source_type=SOURCE_TYPE_MACRO,
            reason=(
                "a macro: its first non-blank line is a SPEC command "
                f"(`{first.strip().split()[0]}`)"
                + (
                    f" and it declares measurement targets with `newfile`"
                    if has_newfile
                    else " and it declares no `newfile` target"
                )
                + ". A macro is script evidence and is never itself a "
                "measurement"
            ),
            confidence=CONFIDENCE_CONTENT,
        )

    # 4. A processed two-column spectrum. Checked AFTER the header formats so an
    #    acquisition's data rows can never reach it.
    numeric = [line for line in lines if _TWO_COLUMN_NUMERIC.match(line)]
    if numeric and len(numeric) == len(lines) and not header_keys:
        return Classification(
            source_type=SOURCE_TYPE_PROCESSED_SPECTRUM,
            reason=(
                f"a processed spectrum: all {len(lines)} of its opening lines "
                "are two whitespace-separated numbers and it carries no header "
                "at all. It is a CANDIDATE processed artifact — nothing here "
                "makes it an official ISAAC reduced spectrum"
            ),
            confidence=CONFIDENCE_CONTENT,
        )

    # 5. Text sources: the one shared readme, and the beamtime notes.
    if extension == "txt":
        if basename.casefold() == "readme.txt" and record.depth == 0:
            return Classification(
                source_type=SOURCE_TYPE_SHARED_README,
                reason=(
                    "the archive's single root `readme.txt`: shared "
                    "beamtime-scope context, not a per-measurement source"
                ),
                confidence=CONFIDENCE_CONTENT,
            )
        if _NOTES_STEM.search(stem):
            return Classification(
                source_type=SOURCE_TYPE_BEAMTIME_NOTES,
                reason=(
                    "the beamtime notes: a `.txt` at the archive root whose "
                    f"name names the beamtime (`{stem}`). Its `.docx` and "
                    "`.pdf` siblings are the SAME witness in other "
                    "representations, not additional ones"
                ),
                confidence=CONFIDENCE_CONTENT,
            )

    # `.mca` is handled at the TOP of this function, before the `#F` test. See
    # the comment there for why the ordering is deliberate.
    return Classification(
        source_type=SOURCE_TYPE_UNKNOWN,
        reason=(
            "no content marker this classifier knows appears in the file's "
            f"opening lines (first line: `{first.strip()[:80]}`)"
        ),
        confidence=CONFIDENCE_CONTENT,
    )


def _classify_by_path(
    record: SourceRecord, stem: str, extension: str
) -> Classification:
    """The no-content fallback. Capped at :data:`CONFIDENCE_PATH`."""
    caveat = (
        " No content was supplied, so this rests on the name alone — and in "
        "this archive the name is wrong about `run29` (a macro) and `alignment` "
        "(an acquisition)."
    )
    if extension == "dat":
        return Classification(
            source_type=SOURCE_TYPE_SCAN_EXPORT,
            reason=f"a `.dat` per-scan export, by extension.{caveat}",
            confidence=CONFIDENCE_PATH,
        )
    if extension == "mac":
        return Classification(
            source_type=SOURCE_TYPE_MACRO,
            reason=f"a `.mac` macro, by extension.{caveat}",
            confidence=CONFIDENCE_PATH,
        )
    if extension == "mca":
        return Classification(
            source_type=SOURCE_TYPE_DETECTOR_PRODUCT,
            reason=f"a `.mca` detector product, by extension.{caveat}",
            confidence=CONFIDENCE_PATH,
        )
    if extension == "txt" and record.basename.casefold() == "readme.txt":
        return Classification(
            source_type=SOURCE_TYPE_SHARED_README,
            reason=f"named `readme.txt`.{caveat}",
            confidence=CONFIDENCE_PATH,
        )
    return Classification(
        source_type=SOURCE_TYPE_UNKNOWN,
        reason=(
            "no content was supplied and the name carries no marker this "
            f"classifier recognises (`{record.basename}`)"
        ),
        confidence=CONFIDENCE_UNKNOWN,
    )

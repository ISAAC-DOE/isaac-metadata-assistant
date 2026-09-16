"""``readme.txt`` and the beamtime notes — the two human-written text sources.

Two readers, deliberately in one module: both read prose a person typed, both
depend on heading vocabulary measured from ONE document, and both produce
statements whose *scope is wider than a measurement*. Keeping them together makes
that shared property visible; splitting them would suggest the ``readme`` is a
format when it is one file.

**``.txt`` ONLY. A DOCX/PDF/TXT TRIO IS ONE SOURCE FAMILY, NOT THREE WITNESSES.**
The archive holds ``250411 BL 15 IrOx NP HERFD acid base`` as ``.docx``, ``.pdf``
and ``.txt`` — the same document, saved three ways (characterization §3.6).
**This slice implements no DOCX and no PDF extraction**, and that is a scope
decision rather than an oversight: the ``.txt`` is a flattening of the ``.docx``
tables and carries the same content in a form that needs no dependency. When
DOCX/PDF extraction is built, the three must be recognised as **one** witness —
counting them as three would triple the apparent corroboration for every claim
in the document.

**THE RECOGNISER TABLES ARE MEASURED FROM ONE DOCUMENT AND ARE NAMED AS SUCH.**
:data:`PREPARATION_HEADINGS`, :data:`PURPOSE_HEADINGS`, :data:`TABLE_COLUMNS` and
:data:`QUALITY_MARKERS` are this scientist's headings, not a schema and not a
beamline convention. A second beamtime's notes will need their own tables. Unlike
:mod:`bl15.filenames`, this module consults no
:class:`~isaac_api.bl15.profiles.NamingProfile` — a profile describes a FILENAME
convention, and extending it to prose headings would conflate two different
things. Named residue, stated rather than implied.

**THE BROAD CLAIM IS READ AND NOT APPLIED — this is the one rule that matters
most here.** The real document opens a sentence with *"In ALL experiments we
used ..."*, names one medium, and places it DIRECTLY ABOVE a sample section
naming the opposite one — in a document whose own preparation section states a
third thing again (the sentence and both media are quoted in
``docs/evidence/bl15-2-corpus-characterization-2026-09-16.md`` §3.7; they are
not restated here). It is read as an
:data:`~isaac_api.bl15.evidence.CONCEPT_ELECTROLYTE_OR_MEDIUM` statement at
:data:`~isaac_api.bl15.evidence.SCOPE_BEAMTIME`, and **this reader applies it to
nothing**: no sample, no measurement, no default. A broad human statement is
candidate shared context; sample-specific contrary evidence is a conflict; and
resolving a conflict is a scientist's act, not a reader's.

**A FILE-NUMBER ROW STATES A NUMBER, NOT A STEM.** The tables map
``Step``/``File Number``/``E-chem Procedure``/``Notes``, and the File Number cell
holds a bare integer — ``11``, ``12``, ``23``. That is the same legacy number a
filename's leading token carries, but the notes never write a stem, so
:attr:`SourceEvidence.measurement_stem` is deliberately left ``None`` on every
:data:`~isaac_api.bl15.evidence.CONCEPT_NOTE_FILE_NUMBER_ROW`. Joining a number to
a stem is :mod:`bl15.relate`'s job — and the archive contains a duplicate legacy
number (``32`` appears on two distinct acquisitions), so the join is not even a
function.

**ENCODING.** The real notes file begins with a UTF-8 BOM and uses CRLF line
endings throughout (measured: 1,936 of them). The BOM is stripped, and
``splitlines`` handles CRLF; neither is treated as content. ``readme.txt`` has
neither, which is why both are exercised in the fixtures.

**UNPARSED PROSE IS REPORTED IN BLOCKS, WITH ITS FIRST LINE.** The notes file is
~2,000 lines of mostly narrative. One ``skipped`` entry per contiguous
unrecognised block, carrying the line range, the line count and the block's first
line verbatim — not one entry per line, which would bury the parsed rows under
two thousand identical ones, and not a bare count, which would leave a scientist
unable to see WHAT was passed over.
"""

from __future__ import annotations

import re

from ._emit import EvidenceBuilder, oversize_reason, refusal
from .evidence import (
    CONCEPT_BEAMSIZE,
    CONCEPT_BEAMTIME_DATES,
    CONCEPT_BEAMTIME_PURPOSE,
    CONCEPT_ECHEM_PROCEDURE,
    CONCEPT_ELECTROLYTE_OR_MEDIUM,
    CONCEPT_ELEMENT,
    CONCEPT_FILTER,
    CONCEPT_FLOW_RATE,
    CONCEPT_GAS_CONDITION,
    CONCEPT_MONOCHROMATOR_CALIBRATION,
    CONCEPT_NOTE_FILE_NUMBER_ROW,
    CONCEPT_PH,
    CONCEPT_POTENTIAL_REFERENCE,
    CONCEPT_QUALITY_NOTE,
    CONCEPT_SAMPLE_NAME,
    CONCEPT_SAMPLE_PREPARATION,
    CONCEPT_SPECTROMETER_CONFIG,
    CONCEPT_STEP_NUMBER,
    DETERMINISM_NORMALIZED,
    MAX_SOURCE_BYTES,
    SCOPE_BEAMTIME,
    SCOPE_MEASUREMENT,
    SCOPE_SAMPLE_GROUP,
    SOURCE_TYPE_BEAMTIME_NOTES,
    SOURCE_TYPE_SHARED_README,
    ReaderResult,
)
from .inventory import SourceRecord
from .spec import BOM

README_PARSER_ID = "bl15_shared_readme_v1"
NOTES_PARSER_ID = "bl15_beamtime_notes_v1"

#: A contiguous run of lines no recogniser claimed.
SKIP_UNRECOGNIZED_PROSE = "unrecognized_prose_block"
#: A table row whose cells did not read as ``Step`` + ``File Number``.
SKIP_UNREADABLE_TABLE_ROW = "table_row_not_readable"


# --- measured heading vocabulary --------------------------------------------
#
# Every literal below appears in the ONE supplied beamtime notes document. None
# is a standard, and none may be treated as one.

#: Section headings under which the document describes how a sample was made.
PREPARATION_HEADINGS: tuple[str, ...] = (
    "what to have ready",
    "to make the ink:",
    "to make the ink",
    "procedure for preparing electrode",
    "preparing working electrode",
    "assembling cell and running electrochemical cleaning",
    "at the beamline",
)
#: Headings after which the next non-blank line states why the beamtime ran.
PURPOSE_HEADINGS: tuple[str, ...] = ("main scopes", "main scope")
#: The four column headers of a file-number table, in the order the DOCX
#: flattening emits them.
TABLE_COLUMNS: tuple[str, ...] = (
    "step",
    "file number",
    "e-chem procedure",
    "notes",
)
#: Parenthetical qualifiers in a sample heading that state a quality judgement.
QUALITY_MARKERS: tuple[str, ...] = ("bad", "good", "noisy", "failed", "discard")
#: ``readme.txt``'s own section labels.
README_SECTIONS: tuple[tuple[str, str], ...] = (
    ("beamsize", CONCEPT_BEAMSIZE),
    ("spectrometer", CONCEPT_SPECTROMETER_CONFIG),
    ("monochromator", CONCEPT_MONOCHROMATOR_CALIBRATION),
)


RULE_README_SECTION = (
    "bl15.notes.readme_section.v1: `readme.txt` is written as `<Label>:` "
    "followed by indented continuation lines, so a section's statement is its "
    "label line PLUS every indented line under it, joined with newlines and "
    "reported verbatim. The label decides the concept (Beamsize -> beamsize, "
    "Spectrometer -> spectrometer_configuration, Monochromator -> "
    "monochromator_calibration). Nothing inside the section is parsed into "
    "numbers: a beamsize line mixes a slit size, a motor "
    "identifier and two bend settings, and splitting it would invent structure "
    "the file does not have."
)
RULE_README_ELEMENT = (
    "bl15.notes.readme_element.v1: a `readme.txt` line holding ONE token of one "
    "or two letters, outside any labelled section, states the element under "
    "study. Measured: the supplied `readme.txt` carries exactly one such line. "
    "Read AS ITSELF — no atomic number, no edge, no absorption line is "
    "derived from it, and the edge in particular is a separate concept the "
    "readme does not state."
)
RULE_BEAMTIME_DATES = (
    "bl15.notes.beamtime_dates.v1: a line beginning `Beam` and containing a "
    "four-digit year states the beamtime's dates. Reported verbatim — the range "
    "is NOT parsed into two ISO instants, because the line names a month, a day "
    "range and a year and NO timezone, and the shift line beside it names two "
    "clock times and no date — so any instant would be invented."
)
RULE_BEAMTIME_PURPOSE = (
    "bl15.notes.beamtime_purpose.v1: the first non-blank line after a `Main "
    "Scopes` heading states the beamtime's purpose. Reported verbatim as a "
    "beamtime-scope statement; it is never read as a sample property."
)
RULE_BROAD_CLAIM = (
    "bl15.notes.broad_shared_claim.v1: a sentence opening `In ALL experiments` "
    "states something the author believes of the whole beamtime, so it is read "
    "at beamtime scope and APPLIED TO NOTHING. In the supplied document this "
    "exact sentence names one medium and sits directly above a sample section "
    "naming the opposite one, in a document whose preparation section states a "
    "third. It is candidate shared context; the contradiction is a conflict "
    "for a scientist, and no reader may resolve it by preferring either."
)
RULE_SAMPLE_HEADING = (
    "bl15.notes.sample_heading.v1: `Sample <n> <name> in <medium>` opens a "
    "sample section, stating a sample name and a medium at sample-group scope. "
    "A trailing parenthetical matching a measured quality marker (`(bad)`) is "
    "read as a separate quality note. The name and the medium are read as "
    "themselves; `in base` is not expanded to a concentration even though the "
    "same document states one elsewhere."
)
RULE_TABLE_ROW = (
    "bl15.notes.file_number_row.v1: inside a `Step / File Number / E-chem "
    "Procedure / Notes` table, a cell holding a bare integer followed by "
    "another cell holding a bare integer is a (step, file number) pair. The "
    "file number is reported as `note_file_number_row` with "
    "`measurement_stem` left NULL: the notes state a legacy NUMBER and never a "
    "stem, and the archive contains a duplicate legacy number (`32` on two "
    "distinct acquisitions), so joining number to stem is neither this "
    "reader's job nor a function."
)
RULE_ECHEM_PROCEDURE = (
    "bl15.notes.echem_procedure.v1: a table cell containing the document's own "
    "phrase `Sets the working potential to` states the electrochemical step "
    "performed. Reported verbatim at sample-group scope with the table row in "
    "its locator, so the row binding survives without this reader claiming a "
    "measurement it cannot name. The potential inside the sentence is NOT "
    "extracted as a potential magnitude: the sentence also states its reference "
    "basis (`vs reference`), and splitting the two would separate a magnitude "
    "from the only basis statement the corpus has for it."
)
RULE_REFERENCE_BASIS = (
    "bl15.notes.potential_reference_basis.v1: `RHE`, `Ag/AgCl`, `SCE` or the "
    "phrase `vs reference` states what a potential is measured against. THIS IS "
    "THE ONLY PLACE IN THE CORPUS THAT STATES A BASIS — `bl15.filenames` "
    "deliberately never emits this concept, because `850mV` in a filename says "
    "nothing about it. Read verbatim; `vs reference` is NOT resolved to a "
    "specific electrode, because the document does not say which one."
)
RULE_PH_VALUE = (
    "bl15.notes.ph_value.v1: `pH = <number>` or `pH <number>` states a pH at "
    "sample-group scope."
)
RULE_GAS_CONDITION = (
    "bl15.notes.gas_condition.v1: `<gas> sat` / `<gas> saturated` states the "
    "atmosphere the cell was held under (measured: `Ar sat`)."
)
RULE_FLOW_RATE = (
    "bl15.notes.flow_rate.v1: `<number> <ml|mL|uL> / min` states a flow rate; "
    "the unit is taken from the line itself and normalised only in case "
    "(`ml/min` -> `mL/min`)."
)
RULE_FILTER_SETTING = (
    "bl15.notes.filter_setting.v1: `Filter = <n>` states the filter number at "
    "sample-group scope. It is the same concept a filename's `filter<n>` token "
    "states, at a wider scope — which is exactly the kind of pair a later "
    "conflict check needs both halves of."
)
RULE_PREPARATION_SECTION = (
    "bl15.notes.preparation_section.v1: a line matching a measured preparation "
    "heading declares that the document describes sample preparation from that "
    "point. The HEADING is reported, with the line range of the block beneath "
    "it in the locator; the prose itself is NOT parsed into quantities. "
    "A line of the form `Weigh <mass> of <material>` is a recipe step, not a "
    "metadata field, and "
    "turning it into one would invent a schema the document does not have."
)

NORMALIZATION_RULES: frozenset[str] = frozenset(
    {
        RULE_README_SECTION,
        RULE_README_ELEMENT,
        RULE_BEAMTIME_DATES,
        RULE_BEAMTIME_PURPOSE,
        RULE_BROAD_CLAIM,
        RULE_SAMPLE_HEADING,
        RULE_TABLE_ROW,
        RULE_ECHEM_PROCEDURE,
        RULE_REFERENCE_BASIS,
        RULE_PH_VALUE,
        RULE_GAS_CONDITION,
        RULE_FLOW_RATE,
        RULE_FILTER_SETTING,
        RULE_PREPARATION_SECTION,
    }
)

#: A ``readme.txt`` section label. The label may carry ANYTHING before its
#: colon except another colon — measured, because the first version of this
#: pattern allowed only letters and spaces and therefore silently failed to
#: match the archive's own ``Beamsize @<energy>eV:`` label, sending the whole
#: section to ``skipped``. The defect was invisible in review and obvious the
#: moment the reader ran over the real file.
_README_LABEL = re.compile(r"^([A-Za-z][^:]*?)\s*:\s*(.*)$")
_ELEMENT = re.compile(r"^[A-Z][a-z]?$")
_BEAM_DATES = re.compile(r"^Beam\b.*\d{4}", re.IGNORECASE)
_BROAD_CLAIM = re.compile(r"^In ALL experiments\b", re.IGNORECASE)
_SAMPLE_HEADING = re.compile(
    r"^Sample\s+(\d+)\s*(?:([^\s(]+)\s*)?(?:in\s+([A-Za-z0-9]+)\s*)?"
    r"(?:\(([^)]*)\)\s*)?$"
)
_BARE_INTEGER = re.compile(r"^\d+$")
#: A cell of a DOCX table flattened to text. Measured: every table cell line in
#: the supplied notes begins with a tab, INCLUDING an empty one, which flattens
#: to a lone tab and is therefore a CELL rather than a blank line. Telling those
#: two apart is what keeps a table's columns aligned.
_TABLE_CELL = re.compile(r"^\t")
_ECHEM = re.compile(r"Sets the working potential to", re.IGNORECASE)
_REFERENCE = re.compile(r"\b(RHE|Ag/AgCl|SCE)\b|\bvs\.?\s+reference\b", re.IGNORECASE)
_PH = re.compile(r"\bpH\s*=?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_GAS = re.compile(r"^(Ar|N2|O2|air|He)\s+sat(?:urated)?\b", re.IGNORECASE)
_FLOW = re.compile(
    r"(\d+(?:\.\d+)?)\s*(ml|mL|µL|uL|ul)\s*/\s*min", re.IGNORECASE
)
_FILTER_SETTING = re.compile(r"^Filter\s*=\s*(\d+)\s*$", re.IGNORECASE)
_COMMENT = re.compile(r"^\s*#")


def _to_number(text: str) -> float | int:
    value = float(text)
    return int(value) if value.is_integer() and "." not in text else value


def _oversize(record: SourceRecord, text: str, parser_id: str):
    measured = max(record.size_bytes, len(text.encode("utf-8", "replace")))
    if measured > MAX_SOURCE_BYTES:
        return refusal(
            source_path=record.archive_path,
            parser_id=parser_id,
            reason=oversize_reason(measured, MAX_SOURCE_BYTES),
        )
    return None


# --- readme.txt --------------------------------------------------------------


def read_shared_readme(
    record: SourceRecord, text: str, *, id_prefix: str = ""
) -> ReaderResult:
    """Read the archive's single root ``readme.txt``. Never raises.

    **Every statement is :data:`SCOPE_BEAMTIME`.** The readme states the element,
    the beamsize, the spectrometer configuration and the monochromator
    calibration for the WHOLE beamtime, and treating any of them as a
    per-measurement value would be a lie about where it came from. Measured: the
    archive has exactly ONE readme, at the root, with no nested ones — so nested
    scope inheritance is deliberately not designed here, against no examples.
    """
    oversized = _oversize(record, text, README_PARSER_ID)
    if oversized is not None:
        return oversized

    lines = text.lstrip(BOM).splitlines()
    builder = EvidenceBuilder(
        source_path=record.archive_path,
        source_type=SOURCE_TYPE_SHARED_README,
        parser_id=README_PARSER_ID,
        id_prefix=id_prefix,
    )

    unread: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        raw = lines[index]
        line = raw.strip()
        if not line:
            index += 1
            continue
        if _COMMENT.match(raw):
            # The real readme opens with `# 2025-04_Sokaras`. It is a comment and
            # this reader assigns it NO concept: it looks like a date and a name,
            # and reading either out of it would be a guess about which.
            unread.append((index + 1, line))
            index += 1
            continue

        label_match = _README_LABEL.match(line)
        if label_match:
            label = label_match.group(1).strip().casefold()
            concept = next(
                (
                    mapped
                    for prefix, mapped in README_SECTIONS
                    if label.startswith(prefix)
                ),
                None,
            )
            if concept is not None:
                body = [raw]
                end = index + 1
                while end < len(lines) and (
                    lines[end].startswith((" ", "\t"))
                    or (lines[end].strip() and not _README_LABEL.match(lines[end].strip()))
                ):
                    if lines[end].strip():
                        body.append(lines[end])
                    end += 1
                builder.add(
                    locator=f"lines {index + 1}..{end} (`{line.split(':')[0]}`)",
                    raw_literal="\n".join(body),
                    concept=concept,
                    determinism=DETERMINISM_NORMALIZED,
                    normalized_value=None,
                    normalization_rule=RULE_README_SECTION,
                    scope=SCOPE_BEAMTIME,
                )
                index = end
                continue
            unread.append((index + 1, line))
            index += 1
            continue

        if _ELEMENT.match(line):
            builder.add(
                locator=f"line {index + 1}",
                raw_literal=line,
                concept=CONCEPT_ELEMENT,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=line,
                normalization_rule=RULE_README_ELEMENT,
                scope=SCOPE_BEAMTIME,
            )
            index += 1
            continue

        unread.append((index + 1, line))
        index += 1

    _report_unread(builder, unread)
    return builder.result()


# --- the beamtime notes ------------------------------------------------------


def read_beamtime_notes(
    record: SourceRecord, text: str, *, id_prefix: str = ""
) -> ReaderResult:
    """Read the flattened beamtime-notes ``.txt``. Never raises.

    **``.txt`` only.** The ``.docx`` and ``.pdf`` siblings are the same document
    and the same witness; see this module's own docstring.
    """
    oversized = _oversize(record, text, NOTES_PARSER_ID)
    if oversized is not None:
        return oversized

    lines = text.lstrip(BOM).splitlines()
    builder = EvidenceBuilder(
        source_path=record.archive_path,
        source_type=SOURCE_TYPE_BEAMTIME_NOTES,
        parser_id=NOTES_PARSER_ID,
        id_prefix=id_prefix,
    )

    unread: list[tuple[int, str]] = []
    #: Which sample section we are inside, for a locator. It is NEVER put in
    #: `measurement_stem`: a sample section is a sample group, not a measurement.
    sample_label: str | None = None
    #: How many file-number tables have opened, and where we are in the current
    #: one. `None` when no table is open.
    table_index = -1
    in_table = False
    row_index = 0
    awaiting_purpose = False

    index = -1
    while index + 1 < len(lines):
        index += 1
        number = index + 1
        raw = lines[index]
        line = raw.strip()
        if not line:
            continue

        where = f"line {number}" + (
            f" (in `{sample_label}`)" if sample_label else ""
        )

        if awaiting_purpose:
            awaiting_purpose = False
            builder.add(
                locator=where,
                raw_literal=line,
                concept=CONCEPT_BEAMTIME_PURPOSE,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=None,
                normalization_rule=RULE_BEAMTIME_PURPOSE,
                scope=SCOPE_BEAMTIME,
            )
            continue

        folded = line.casefold().rstrip(" \t")

        if folded in PURPOSE_HEADINGS:
            awaiting_purpose = True
            continue

        if _BEAM_DATES.match(line):
            builder.add(
                locator=where,
                raw_literal=line,
                concept=CONCEPT_BEAMTIME_DATES,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=None,
                normalization_rule=RULE_BEAMTIME_DATES,
                scope=SCOPE_BEAMTIME,
            )
            continue

        if _BROAD_CLAIM.match(line):
            builder.add(
                locator=where,
                raw_literal=line,
                concept=CONCEPT_ELECTROLYTE_OR_MEDIUM,
                determinism=DETERMINISM_NORMALIZED,
                # Deliberately NO normalised value. The sentence states a
                # medium in prose and this reader does not extract one: a
                # concentration lifted out of a claim the document itself
                # contradicts would look like a resolved fact.
                normalized_value=None,
                normalization_rule=RULE_BROAD_CLAIM,
                scope=SCOPE_BEAMTIME,
            )
            continue

        sample_match = _SAMPLE_HEADING.match(line)
        if sample_match:
            in_table = False
            pending_step = None
            sample_label = line
            name, medium, parenthetical = (
                sample_match.group(2),
                sample_match.group(3),
                sample_match.group(4),
            )
            if name:
                builder.add(
                    locator=f"line {number} sample heading",
                    raw_literal=name,
                    concept=CONCEPT_SAMPLE_NAME,
                    determinism=DETERMINISM_NORMALIZED,
                    normalized_value=name,
                    normalization_rule=RULE_SAMPLE_HEADING,
                    scope=SCOPE_SAMPLE_GROUP,
                )
            if medium:
                builder.add(
                    locator=f"line {number} sample heading",
                    raw_literal=medium,
                    concept=CONCEPT_ELECTROLYTE_OR_MEDIUM,
                    determinism=DETERMINISM_NORMALIZED,
                    normalized_value=medium.casefold(),
                    normalization_rule=RULE_SAMPLE_HEADING,
                    scope=SCOPE_SAMPLE_GROUP,
                )
            if parenthetical and parenthetical.strip().casefold() in QUALITY_MARKERS:
                builder.add(
                    locator=f"line {number} sample heading qualifier",
                    raw_literal=parenthetical.strip(),
                    concept=CONCEPT_QUALITY_NOTE,
                    determinism=DETERMINISM_NORMALIZED,
                    normalized_value=parenthetical.strip().casefold(),
                    normalization_rule=RULE_SAMPLE_HEADING,
                    scope=SCOPE_SAMPLE_GROUP,
                )
            elif parenthetical:
                unread.append((number, line))
            continue

        if folded in PREPARATION_HEADINGS:
            builder.add(
                locator=where,
                raw_literal=line,
                concept=CONCEPT_SAMPLE_PREPARATION,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=None,
                normalization_rule=RULE_PREPARATION_SECTION,
                scope=SCOPE_BEAMTIME,
            )
            continue

        # --- the file-number table ---------------------------------------
        if folded == TABLE_COLUMNS[0]:
            # `Step` alone opens a table. Whether it is a FILE-NUMBER table is
            # decided by the next header cell, not by this one: the document
            # contains `Step`-headed tables with no File Number column at all
            # (measured, lines 97 and 161), and their rows must not be read as
            # file numbers.
            in_table = False
            table_index += 1
            continue
        if folded == TABLE_COLUMNS[1]:
            in_table = True
            row_index = 0
            continue
        if folded in TABLE_COLUMNS[2:]:
            continue

        if in_table and _TABLE_CELL.match(raw) and _BARE_INTEGER.match(line):
            # THIS IS THE `Step` CELL. The `File Number` cell is the cell
            # IMMEDIATELY AFTER it — adjacency, not "the next bare integer you
            # find". The first version of this reader paired any two bare
            # integers and produced 51 file numbers from the real document,
            # including `2, 4, 6, 8, 10` for Sample 1, whose File Number column
            # is EMPTY THROUGHOUT: it had paired step 1 with step 2 and reported
            # the second step as a file number. An empty cell flattens to a
            # lone tab, which a blank-line skip silently swallowed, and the
            # column alignment was destroyed from there on.
            row_index += 1
            builder.add(
                locator=(
                    f"line {number} table {table_index} row {row_index} "
                    f"column `Step`"
                ),
                raw_literal=line,
                concept=CONCEPT_STEP_NUMBER,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=int(line),
                normalization_rule=RULE_TABLE_ROW,
                scope=SCOPE_SAMPLE_GROUP,
            )
            next_raw = lines[index + 1] if index + 1 < len(lines) else ""
            next_line = next_raw.strip()
            if not _TABLE_CELL.match(next_raw):
                builder.skip(
                    reason=SKIP_UNREADABLE_TABLE_ROW,
                    locator=(
                        f"line {number} table {table_index} row {row_index} "
                        f"column `File Number`"
                    ),
                    detail=(
                        "the cell after this row's `Step` is not a table cell "
                        "at all, so the row's `File Number` column could not "
                        "be located. The step is read; no file number is "
                        "invented"
                    ),
                )
                continue
            index += 1
            if not _BARE_INTEGER.match(next_line):
                builder.skip(
                    reason=SKIP_UNREADABLE_TABLE_ROW,
                    locator=(
                        f"line {index + 1} table {table_index} row {row_index} "
                        f"column `File Number`"
                    ),
                    raw_literal=next_line,
                    detail=(
                        "this row's `File Number` cell is empty or is not a "
                        "bare integer. The step is read and NO file number is "
                        "reported — Sample 1 of the real document has an empty "
                        "File Number column throughout, and filling it from a "
                        "neighbouring cell is exactly the defect this "
                        "adjacency rule exists to prevent"
                    ),
                )
                continue
            builder.add(
                locator=(
                    f"line {index + 1} table {table_index} row {row_index} "
                    f"column `File Number`"
                ),
                raw_literal=next_line,
                concept=CONCEPT_NOTE_FILE_NUMBER_ROW,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=int(next_line),
                normalization_rule=RULE_TABLE_ROW,
                scope=SCOPE_MEASUREMENT,
                # NULL on purpose. See RULE_TABLE_ROW.
                measurement_stem=None,
            )
            continue

        claimed = False

        if _ECHEM.search(line):
            builder.add(
                locator=(
                    f"{where} table {table_index} row {row_index} "
                    f"column `E-chem Procedure`"
                    if in_table
                    else where
                ),
                raw_literal=line,
                concept=CONCEPT_ECHEM_PROCEDURE,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=None,
                normalization_rule=RULE_ECHEM_PROCEDURE,
                scope=SCOPE_SAMPLE_GROUP,
            )
            claimed = True

        reference = _REFERENCE.search(line)
        if reference:
            builder.add(
                locator=f"{where} reference basis",
                raw_literal=reference.group(0),
                concept=CONCEPT_POTENTIAL_REFERENCE,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=reference.group(0).strip(),
                normalization_rule=RULE_REFERENCE_BASIS,
                scope=SCOPE_SAMPLE_GROUP,
            )
            claimed = True

        ph = _PH.search(line)
        if ph:
            builder.add(
                locator=f"{where} pH",
                raw_literal=ph.group(0),
                concept=CONCEPT_PH,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=_to_number(ph.group(1)),
                normalization_rule=RULE_PH_VALUE,
                scope=SCOPE_SAMPLE_GROUP,
            )
            claimed = True

        gas = _GAS.match(line)
        if gas:
            builder.add(
                locator=f"{where} gas condition",
                raw_literal=line,
                concept=CONCEPT_GAS_CONDITION,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=gas.group(1).casefold(),
                normalization_rule=RULE_GAS_CONDITION,
                scope=SCOPE_SAMPLE_GROUP,
            )
            claimed = True

        flow = _FLOW.search(line)
        if flow:
            unit = flow.group(2)
            builder.add(
                locator=f"{where} flow rate",
                raw_literal=flow.group(0),
                concept=CONCEPT_FLOW_RATE,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=_to_number(flow.group(1)),
                unit="mL/min" if unit.casefold() in ("ml",) else "uL/min",
                normalization_rule=RULE_FLOW_RATE,
                scope=SCOPE_SAMPLE_GROUP,
            )
            claimed = True

        filter_setting = _FILTER_SETTING.match(line)
        if filter_setting:
            builder.add(
                locator=f"{where} filter setting",
                raw_literal=line,
                concept=CONCEPT_FILTER,
                determinism=DETERMINISM_NORMALIZED,
                normalized_value=int(filter_setting.group(1)),
                normalization_rule=RULE_FILTER_SETTING,
                scope=SCOPE_SAMPLE_GROUP,
            )
            claimed = True

        if not claimed:
            unread.append((number, line))

    _report_unread(builder, unread)
    return builder.result()


def _report_unread(
    builder: EvidenceBuilder, unread: list[tuple[int, str]]
) -> None:
    """One ``skipped`` entry per CONTIGUOUS run of unrecognised lines.

    Contiguous in LINE NUMBER, so a 40-line narrative paragraph is one entry
    naming its range, its length and its first line — not forty entries, and not
    a bare total a scientist could not act on.
    """
    if not unread:
        return
    unread = sorted(unread)
    start = 0
    for position in range(1, len(unread) + 1):
        breaks = position == len(unread) or unread[position][0] != (
            unread[position - 1][0] + 1
        )
        if not breaks:
            continue
        first_line, first_text = unread[start]
        last_line = unread[position - 1][0]
        builder.skip(
            reason=SKIP_UNRECOGNIZED_PROSE,
            locator=(
                f"line {first_line}"
                if first_line == last_line
                else f"lines {first_line}..{last_line}"
            ),
            detail=(
                f"{position - start} line(s) matched no recogniser this reader "
                f"knows and were passed over rather than interpreted"
            ),
            line_count=position - start,
            first_line_text=first_text,
        )
        start = position

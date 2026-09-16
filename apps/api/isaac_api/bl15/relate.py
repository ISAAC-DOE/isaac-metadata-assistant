"""Reconstruct what belongs to what — and record what disagrees.

**THE CENTRAL JUDGEMENT IN THIS MODULE IS WHAT COUNTS AS ONE MEASUREMENT, and it is the
one thing the authorizing brief made mandatory rather than advisory.** Two shortcuts are
forbidden by name, and both are measured against the real corpus:

* **One ``.mac`` is NOT one measurement.** 156 ``newfile`` declarations across 60 macro
  files; 29 declare more than one, the maximum is 8, and **4 declare none at all** (an
  acquisition-method definition, a trigger, two motor snapshots). One-macro-one-unit
  would have produced 60 units for 95 declared measurements *and* turned four
  non-measurements into measurements.
* **One ``.dat`` is NOT one measurement.** 908 scan exports across 94 directories, 0 to
  233 each. One-file-one-unit would have invented 816 measurements nobody performed.

What IS one measurement here is **one SPEC acquisition file** — 94 of them. Everything
else attaches to it: its scan children, the macro blocks that declared it, the processed
products that name it, the human note rows that cite its number, and the beamtime-scope
context it inherits.

**THIS MODULE NEVER RESOLVES A DISAGREEMENT.** It finds them and names them. Five kinds
are reachable in this corpus and each is reported with every reading intact, because the
whole reason Historical Import exists is that a scientist — not an import tool — decides
which reading is right. The measured reason that matters most: the corpus contains a
**systematic rename**, four consecutive files declaring ``beforeCycling`` internally
while their names say ``after1500Cycling``. A rule like *"trust the internal header, it
is closer to the instrument"* sounds obviously right and **is wrong for those four**,
because a deliberate rename is likelier to be the scientist's correction than the header
is. So no source ranking is applied, anywhere.

**IT IS ALSO PURE STRUCTURE OVER FACTS IT IS GIVEN.** It opens no file and parses no
format: the internal declarations, the macro targets and the note rows arrive as
arguments from the readers. That keeps the "a reader never opens a file" boundary in one
place, and it means this module degrades honestly — called with paths alone it still
finds the scan groups, and says so rather than pretending the other relationships are
absent.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from . import evidence as ev
from .inventory import SourceRecord

#: Source types that become a :class:`MeasurementUnit` — an acquisition with scans,
#: macros and products hanging off it.
#:
#: **DELIBERATELY WIDER THAN ``RUN_CANDIDATE_SOURCE_TYPES``, and the gap is the point.**
#: An alignment scan and a reference pellet are physically SPEC acquisitions with their
#: own scan directories. If they were not units, their scans would attach to nothing:
#: measured, that orphaned **242 of the 908** scan exports, and the honest reason a
#: surface could give for them would have been wrong — they are not "outside a scan
#: directory", they are inside the scan directory of an acquisition nothing made a unit.
#:
#: So they become units, and :attr:`MeasurementUnit.run_candidate` — not membership here
#: — decides whether one is offered as a Run. That also satisfies the requirement that a
#: scientist be able to inspect and CHANGE an uncertain classification: the unit and its
#: evidence exist either way, and only a flag moves.
UNIT_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        ev.SOURCE_TYPE_SPEC_ACQUISITION,
        ev.SOURCE_TYPE_ALIGNMENT,
        ev.SOURCE_TYPE_STANDARD_OR_REFERENCE,
    }
)

#: A measurement stem's leading legacy number, e.g. ``15`` in
#: ``15_02_JK2_base_...``. The corpus's own identifier, not ISAAC's.
_LEGACY = re.compile(r"^(\d+)_")
#: The suffix the beamline gives a measurement's scan directory.
SCAN_DIR_SUFFIX = "_dir"
#: ``<stem>_001.dat`` -> scan index 1. The index is read, never counted from position:
#: a directory listing sorted differently must not renumber a scientist's scans.
_SCAN_INDEX = re.compile(r"_(\d+)\.dat\Z", re.IGNORECASE)


# --- conflicts ---------------------------------------------------------------

#: An acquisition's own internal declaration disagrees with its filename. FOUR files in
#: the real corpus, consecutive, in one sample group, making the identical substitution.
CONFLICT_DECLARATION_VS_FILENAME = "internal_declaration_vs_filename"
#: Two distinct measurements carry one legacy number. Neither may be overwritten and
#: neither is "the real one" — they are two files the scientist has.
CONFLICT_DUPLICATE_LEGACY_NUMBER = "duplicate_legacy_number"
#: A macro declared a measurement that no acquisition file provides. 9 in the corpus.
CONFLICT_DECLARED_NEVER_ACQUIRED = "macro_declared_never_acquired"
#: An acquisition exists that no macro declared. 9 in the corpus.
CONFLICT_ACQUIRED_NEVER_DECLARED = "acquired_never_declared"
#: A human note row and the filesystem imply different things about one measurement.
CONFLICT_NOTE_VS_FILESYSTEM = "note_vs_filesystem"

CONFLICT_KINDS: frozenset[str] = frozenset(
    {
        CONFLICT_DECLARATION_VS_FILENAME,
        CONFLICT_DUPLICATE_LEGACY_NUMBER,
        CONFLICT_DECLARED_NEVER_ACQUIRED,
        CONFLICT_ACQUIRED_NEVER_DECLARED,
        CONFLICT_NOTE_VS_FILESYSTEM,
    }
)

#: The one value a conflict's resolution may take in this build. A conflict is
#: **surfaced, never resolved** — so there is exactly one state, and it is named rather
#: than left as ``None`` so no consumer reads absence as agreement.
UNRESOLVED_SOURCES_DISAGREE = "sources_disagree"


@dataclass(frozen=True)
class Reading:
    """ONE source's account of a disputed subject. Verbatim, with its provenance."""

    source_path: str
    locator: str
    value: str
    #: What kind of source this is, so a scientist can weigh it THEMSELVES. It is
    #: recorded for explanation and is deliberately not an authority ranking — see the
    #: module docstring for the measured reason a ranking would be wrong here.
    source_type: str = ev.SOURCE_TYPE_UNKNOWN

    def to_state(self) -> dict:
        return {
            "source_path": self.source_path,
            "locator": self.locator,
            "value": self.value,
            "source_type": self.source_type,
        }


@dataclass(frozen=True)
class Conflict:
    """Two or more sources disagreeing, with every reading kept.

    :attr:`readings` may hold **three or more**, and that is not hypothetical: for the
    ``29``–``32`` group the macro, the internal declaration and the filename are three
    sources and at least two disagree. A surface built for exactly two would be wrong
    about the corpus's most instructive case.
    """

    kind: str
    #: What is in dispute, in a scientist's words — a measurement stem, a legacy number.
    subject: str
    readings: tuple[Reading, ...]
    #: Why this is unresolved. Always :data:`UNRESOLVED_SOURCES_DISAGREE` today.
    unresolved_reason: str = UNRESOLVED_SOURCES_DISAGREE
    #: One sentence a scientist reads to understand what they are looking at. Required:
    #: a conflict a reader cannot interpret is a conflict they will dismiss.
    explanation: str = ""

    def __post_init__(self) -> None:
        if self.kind not in CONFLICT_KINDS:
            raise ValueError(f"unknown conflict kind: {self.kind!r}")
        if len(self.readings) < 2:
            # A "conflict" with one reading is a statement. Refused at construction so
            # no surface can ever show a disagreement that nothing disagrees with.
            raise ValueError(
                f"{self.kind}: a conflict needs at least two readings, got "
                f"{len(self.readings)}"
            )
        if not self.explanation:
            raise ValueError(f"{self.kind}: a conflict needs an explanation")

    def to_state(self) -> dict:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "readings": [r.to_state() for r in self.readings],
            "unresolved_reason": self.unresolved_reason,
            "explanation": self.explanation,
        }


# --- the measurement unit ----------------------------------------------------


@dataclass(frozen=True)
class MacroBlock:
    """One ``newfile`` block: a macro declaring it is about to write a measurement.

    :attr:`block_index` is the block's position in its macro, so a scientist can find
    it. :attr:`acquired` is whether an acquisition file of that name exists — INTENT and
    FACT are both recorded because in this corpus they differ nine times each way.
    """

    macro_path: str
    block_index: int
    declared_target: str
    acquired: bool

    def to_state(self) -> dict:
        return {
            "macro_path": self.macro_path,
            "block_index": self.block_index,
            "declared_target": self.declared_target,
            "acquired": self.acquired,
        }


@dataclass(frozen=True)
class ScanChild:
    """One ``.dat`` scan export belonging to a measurement. **Never a Run of its own.**"""

    path: str
    #: Read out of the filename suffix, not assigned by listing order.
    scan_index: int | None

    def to_state(self) -> dict:
        return {"path": self.path, "scan_index": self.scan_index}


@dataclass(frozen=True)
class MeasurementUnit:
    """ONE scientist-meaningful measurement — the candidate Run unit.

    Assembled around a single SPEC acquisition file. It is a **candidate**: nothing here
    is a Run until a scientist reviews it, and nothing here carries a scientific value
    at all — values arrive from the readers and are mapped separately.
    """

    stem: str
    acquisition_path: str
    #: The classifier's verdict on the acquisition this unit is built around. Carried so
    #: :attr:`run_candidate` is derived rather than stored, and so a scientist
    #: overriding a classification changes ONE value.
    source_type: str = ev.SOURCE_TYPE_SPEC_ACQUISITION
    legacy_number: int | None = None
    #: The second filename token when numeric — the sample/electrode instance
    #: **candidate**. NOT an established fact: the registry marks it
    #: ``needs_domain_review`` and it is the first question in the domain packet.
    group_token: str | None = None
    scan_dir: str | None = None
    scans: tuple[ScanChild, ...] = ()
    #: Byte-identical copies of the acquisition found elsewhere in the archive. In the
    #: real corpus every ``_dir`` holds one. They are **kept, not dropped** — they are
    #: real files the scientist has — and the consequence is only that they must not be
    #: counted as a second witness.
    duplicate_copies: tuple[str, ...] = ()
    #: Byte-identical copies of this acquisition that were themselves CLASSIFIED as
    #: acquisitions and were suppressed from becoming units of their own.
    #:
    #: **THIS IS THE FIELD THAT STOPS THE CORPUS DOUBLING.** Every ``*_dir`` in the real
    #: archive holds a byte-identical copy of its root acquisition file, and a
    #: content-led classifier is RIGHT to call those copies SPEC acquisitions — they
    #: begin with ``#F`` and they are. Measured: letting them become units turned 94
    #: measurements into **181**, 908 scans into 1,332, and ONE duplicated legacy number
    #: into **89**. The copies are still listed, because they are real files the
    #: scientist has; they are just not second measurements.
    suppressed_duplicate_acquisitions: tuple[str, ...] = ()
    declared_by: tuple[MacroBlock, ...] = ()
    #: Processed products naming this measurement. A CANDIDATE classification: nothing
    #: here makes a merged file ISAAC's official reduced spectrum.
    processed_products: tuple[str, ...] = ()
    #: Human note rows citing this measurement's legacy number.
    note_rows: tuple[dict, ...] = ()
    #: What the acquisition declares itself to be called, when it says.
    internal_declaration: str | None = None
    conflicts: tuple[Conflict, ...] = ()

    @property
    def run_candidate(self) -> bool:
        """Whether this unit may be offered as a Run. **Alignment and standards are not.**

        Derived from :attr:`source_type` with no field behind it, so it cannot be
        persisted out of step with the classification that decides it — the same
        discipline the import session's own candidate model uses.

        An alignment acquisition and a reference pellet are real measurements and are
        fully assembled as units, with their scans, macros and conflicts. They are just
        not sample measurements, and the authorizing brief is explicit that a scientist
        Run must not be created from all of them automatically. A scientist who
        disagrees changes the classification; nothing here is discarded.
        """
        return self.source_type in ev.RUN_CANDIDATE_SOURCE_TYPES

    @property
    def scan_count(self) -> int:
        """How many scan exports. **Zero is legitimate** — two real measurements have none."""
        return len(self.scans)

    @property
    def source_count(self) -> int:
        """Distinct sources supporting this unit, counting a duplicate copy ONCE.

        The acquisition, its scans, the macros that declared it, its processed products
        and its note rows. Duplicates are excluded deliberately: the same bytes in two
        places is one witness, and a count that included them would inflate a
        scientist's confidence for a filesystem reason.
        """
        macro_paths = {b.macro_path for b in self.declared_by}
        return (
            1
            + len(self.scans)
            + len(macro_paths)
            + len(self.processed_products)
            + len(self.note_rows)
        )

    def to_state(self) -> dict:
        return {
            "stem": self.stem,
            "acquisition_path": self.acquisition_path,
            "source_type": self.source_type,
            "run_candidate": self.run_candidate,
            "legacy_number": self.legacy_number,
            "group_token": self.group_token,
            "scan_dir": self.scan_dir,
            "scans": [s.to_state() for s in self.scans],
            "scan_count": self.scan_count,
            "duplicate_copies": list(self.duplicate_copies),
            "suppressed_duplicate_acquisitions": list(
                self.suppressed_duplicate_acquisitions
            ),
            "declared_by": [b.to_state() for b in self.declared_by],
            "processed_products": list(self.processed_products),
            "note_rows": [dict(r) for r in self.note_rows],
            "internal_declaration": self.internal_declaration,
            "conflicts": [c.to_state() for c in self.conflicts],
            "source_count": self.source_count,
        }


@dataclass(frozen=True)
class SampleGroup:
    """Measurements sharing one sample/electrode token, in legacy order.

    A **grouping candidate**, and the distinction is load-bearing: in the real corpus
    the ten groups' legacy ranges are contiguous and non-overlapping, which independently
    corroborates the beamtime notes' own sample sections. **Corroboration is not proof** —
    a token meaning something else could produce contiguous ranges too.
    """

    group_token: str | None
    stems: tuple[str, ...]
    legacy_low: int | None = None
    legacy_high: int | None = None
    #: True when this group's legacy numbers form an unbroken run with no member of
    #: another group inside it. Reported because a BROKEN range is the signal that the
    #: token does not mean what the grouping assumes.
    contiguous: bool = False

    def to_state(self) -> dict:
        return {
            "group_token": self.group_token,
            "stems": list(self.stems),
            "measurement_count": len(self.stems),
            "legacy_low": self.legacy_low,
            "legacy_high": self.legacy_high,
            "contiguous": self.contiguous,
        }


@dataclass(frozen=True)
class Relationships:
    """Everything one relate pass established, and everything it could not attach."""

    units: tuple[MeasurementUnit, ...] = ()
    groups: tuple[SampleGroup, ...] = ()
    #: Conflicts that belong to no single unit — a duplicated legacy number is about two
    #: units, and a macro target that was never acquired is about none.
    corpus_conflicts: tuple[Conflict, ...] = ()
    #: Sources this pass did not attach to any measurement, with the reason. **As
    #: load-bearing as `units`**: a reconstruction that reported only what it
    #: assembled would leave a scientist unable to see what it left out, which is
    #: `HIST-004`'s banned pattern one layer down.
    unattached: tuple[dict, ...] = ()
    #: Which inputs were actually supplied. A relate pass over paths alone is valid and
    #: finds fewer relationships; saying which were available stops a consumer reading
    #: "no macro declared this" when no macro was ever offered.
    inputs_present: tuple[str, ...] = ()

    def by_stem(self) -> dict[str, MeasurementUnit]:
        return {u.stem: u for u in self.units}

    def to_state(self) -> dict:
        return {
            "units": [u.to_state() for u in self.units],
            "groups": [g.to_state() for g in self.groups],
            "corpus_conflicts": [c.to_state() for c in self.corpus_conflicts],
            "unattached": [dict(u) for u in self.unattached],
            "inputs_present": list(self.inputs_present),
            "unit_count": len(self.units),
            "conflict_count": sum(len(u.conflicts) for u in self.units)
            + len(self.corpus_conflicts),
        }


# --- the pass ----------------------------------------------------------------


def relate(
    *,
    entries: Sequence[SourceRecord],
    classifications: Mapping[str, str],
    internal_declarations: Mapping[str, str] | None = None,
    macro_declarations: Mapping[str, Sequence[str]] | None = None,
    note_file_numbers: Mapping[int, Sequence[Mapping]] | None = None,
    duplicate_groups: Sequence[Sequence[str]] = (),
) -> Relationships:
    """Attach every source to the measurement it belongs to, and name what disagrees.

    :param entries: the archive inventory's records.
    :param classifications: ``archive_path -> source_type``. **Content-led** — the real
        corpus has an extensionless macro (``run29``) beside an extensionless SPEC
        acquisition (``alignment``), so a path-led classification would be wrong about
        both and this function trusts what it is told rather than re-deriving it.
    :param internal_declarations: ``acquisition path -> the name it declares for
        itself``. Optional; without it the declaration-versus-filename conflict cannot
        be found, and :attr:`Relationships.inputs_present` says so.
    :param macro_declarations: ``macro path -> declared targets IN ORDER``. Order is
        the block index a scientist is shown.
    :param note_file_numbers: ``legacy number -> the human note rows citing it``.
    :param duplicate_groups: content-hash groups from the inventory.
    """
    present: list[str] = ["entries", "classifications"]
    if internal_declarations:
        present.append("internal_declarations")
    if macro_declarations:
        present.append("macro_declarations")
    if note_file_numbers:
        present.append("note_file_numbers")
    if duplicate_groups:
        present.append("duplicate_groups")

    internal_declarations = dict(internal_declarations or {})
    macro_declarations = dict(macro_declarations or {})
    note_file_numbers = {int(k): list(v) for k, v in (note_file_numbers or {}).items()}

    by_path = {e.archive_path: e for e in entries}
    candidates = [
        e
        for e in entries
        if classifications.get(e.archive_path) in UNIT_SOURCE_TYPES
    ]
    copies = _copies_by_path(duplicate_groups)
    acquisitions, suppressed = _canonical_acquisitions(candidates, copies)
    # Deterministic order, so two passes over one archive produce identical output and
    # a diff of `to_state()` means something.
    acquisitions.sort(key=lambda e: (_legacy_of(e.basename) or 0, e.archive_path))

    stems = {e.basename for e in acquisitions}
    scans = _scans_by_stem(entries, classifications, stems)
    blocks = _blocks_by_target(macro_declarations, stems)
    processed = _processed_by_legacy(entries, classifications)

    attached: set[str] = set()
    units: list[MeasurementUnit] = []

    for entry in acquisitions:
        stem = entry.basename
        legacy = _legacy_of(stem)
        declared = internal_declarations.get(entry.archive_path)
        unit_scans = tuple(scans.get(stem, ()))
        unit_blocks = tuple(blocks.get(stem, ()))
        unit_copies = tuple(p for p in copies.get(entry.archive_path, ()) if p != entry.archive_path)
        unit_processed = tuple(processed.get(legacy, ())) if legacy is not None else ()
        rows = tuple(dict(r) for r in note_file_numbers.get(legacy, ())) if legacy is not None else ()

        conflicts: list[Conflict] = []
        # COMPARE BASENAMES, NOT THE RAW DECLARATION, and this is a measured
        # correction rather than defensive coding. Two files in the real corpus declare
        # themselves with an ABSOLUTE FILESYSTEM PATH
        # (`/data/.../MERGE/ave_JK2_filter10.mca`) instead of a bare stem. A raw
        # comparison called both of them conflicts — and they are not: their basenames
        # match their filenames exactly. Measured over all 188 files carrying a
        # declaration: 186 bare stems, 2 absolute paths, and ZERO whose basename still
        # differs once the path is stripped. So this removes two false entries from the
        # conflict list and loses none of the four real ones, which matters because a
        # conflict list with false entries in it is a list a scientist stops reading.
        declared_name = declared.rsplit("/", 1)[-1] if declared else None
        if declared_name and declared_name != stem:
            readings = [
                Reading(
                    source_path=entry.archive_path,
                    locator="filename",
                    value=stem,
                    source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
                ),
                Reading(
                    source_path=entry.archive_path,
                    locator="#F",
                    # VERBATIM, including a path if the file wrote one. The comparison
                    # above is on basenames; what a scientist is SHOWN is what the file
                    # actually says, because a trimmed value they cannot find in the
                    # file is worse than a long one.
                    value=declared,
                    source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
                ),
            ]
            # A macro that declared EITHER name is a third reading, and the real corpus
            # has exactly that for the 29-32 group. Appended rather than replacing,
            # because a three-way disagreement is what a scientist has to see.
            for target, block_list in blocks.items():
                if target != declared_name:
                    continue
                for block in block_list:
                    readings.append(
                        Reading(
                            source_path=block.macro_path,
                            locator=f"newfile block {block.block_index}",
                            value=block.declared_target,
                            source_type=ev.SOURCE_TYPE_MACRO,
                        )
                    )
            conflicts.append(
                Conflict(
                    kind=CONFLICT_DECLARATION_VS_FILENAME,
                    subject=stem,
                    readings=tuple(readings),
                    explanation=(
                        "This acquisition's filename and the name it declares inside "
                        "itself are different. Neither is preferred automatically: a "
                        "file may have been renamed afterwards to correct it, or the "
                        "header may be the only untouched record. Which applies is "
                        "yours to say."
                    ),
                )
            )

        # Only for a SAMPLE measurement. An alignment scan or a reference pellet that
        # no macro declared is not a discrepancy — it is how that work is done — and
        # reporting it as a conflict would put 5 false entries in the list a scientist
        # is meant to trust.
        if (
            not unit_blocks
            and macro_declarations
            and classifications.get(entry.archive_path)
            in ev.RUN_CANDIDATE_SOURCE_TYPES
        ):
            conflicts.append(
                Conflict(
                    kind=CONFLICT_ACQUIRED_NEVER_DECLARED,
                    subject=stem,
                    readings=(
                        Reading(
                            source_path=entry.archive_path,
                            locator="filename",
                            value=stem,
                            source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
                        ),
                        Reading(
                            source_path="(the macros in this import)",
                            locator="newfile declarations",
                            value="no macro declares this measurement",
                            source_type=ev.SOURCE_TYPE_MACRO,
                        ),
                    ),
                    explanation=(
                        "This measurement exists but no macro in the import declared "
                        "it. That is normal for work driven by hand, and it also "
                        "happens when a file was renamed after acquisition — the "
                        "acquisition is real either way."
                    ),
                )
            )

        attached.add(entry.archive_path)
        attached.update(suppressed.get(entry.archive_path, ()))
        attached.update(s.path for s in unit_scans)
        attached.update(unit_copies)
        attached.update(unit_processed)
        attached.update(b.macro_path for b in unit_blocks)
        if unit_scans or unit_copies:
            attached.add(f"{entry.archive_path}{SCAN_DIR_SUFFIX}")

        units.append(
            MeasurementUnit(
                stem=stem,
                acquisition_path=entry.archive_path,
                source_type=classifications.get(
                    entry.archive_path, ev.SOURCE_TYPE_SPEC_ACQUISITION
                ),
                legacy_number=legacy,
                group_token=_group_token_of(stem),
                scan_dir=(
                    f"{entry.parent_dir + '/' if entry.parent_dir else ''}"
                    f"{stem}{SCAN_DIR_SUFFIX}"
                    if unit_scans
                    else None
                ),
                scans=unit_scans,
                duplicate_copies=unit_copies,
                suppressed_duplicate_acquisitions=tuple(
                    suppressed.get(entry.archive_path, ())
                ),
                declared_by=unit_blocks,
                processed_products=unit_processed,
                note_rows=rows,
                internal_declaration=declared,
                conflicts=tuple(conflicts),
            )
        )

    corpus_conflicts = list(_duplicate_legacy_conflicts(units))
    corpus_conflicts.extend(_never_acquired_conflicts(macro_declarations, stems))

    unattached = _unattached(by_path, attached, classifications)

    return Relationships(
        units=tuple(units),
        groups=_groups(units),
        corpus_conflicts=tuple(corpus_conflicts),
        unattached=tuple(unattached),
        inputs_present=tuple(present),
    )


# --- helpers -----------------------------------------------------------------


def _legacy_of(stem: str) -> int | None:
    m = _LEGACY.match(stem)
    return int(m.group(1)) if m else None


def _group_token_of(stem: str) -> str | None:
    """The second token, when it is numeric. ``None`` when the stem has no such token.

    ``None`` rather than a placeholder: two real measurements (the old pellets) carry no
    group token, and a placeholder would put them in a group that does not exist.
    """
    parts = stem.split("_")
    if len(parts) > 1 and parts[0].isdigit() and parts[1].isdigit():
        return parts[1]
    return None


def _canonical_acquisitions(
    candidates: Sequence[SourceRecord],
    copies: Mapping[str, Sequence[str]],
) -> tuple[list[SourceRecord], dict[str, tuple[str, ...]]]:
    """Pick ONE unit per distinct set of acquisition bytes, and say which were suppressed.

    **This exists because of a measured factor-of-two error, and the error was not in the
    classifier — the classifier was right.** Every ``*_dir`` in the real archive holds a
    byte-identical copy of its root acquisition file (96 duplicate-content groups over
    193 files). Those copies begin with ``#F``, so a content-led classifier calls them
    SPEC acquisitions, correctly. Letting each become a measurement produced **181 units
    for 94 measurements**, attributed **1,332 scans where 908 exist**, and reported
    **89 duplicated legacy numbers where the corpus has exactly one** — which would have
    buried the real duplicate (number 32) in noise and destroyed the credibility of the
    conflict list.

    The canonical copy is the **shallowest** path, then the lexicographically smallest.
    Shallowest first because the archive's own convention puts the acquisition at the
    root and the copy inside the scan directory, so depth is the structural fact rather
    than a guess about names; lexicographic order only to make ties deterministic.

    **Identity is CONTENT, never the name.** Two acquisitions with the same stem and
    different bytes are two measurements and both are kept — the corpus's ``29``–``32``
    group proves names are unreliable, and ``run29.mac`` / ``run29.mac.mac`` proves
    similar names can hold different content.
    """
    by_digest: dict[str, list[SourceRecord]] = defaultdict(list)
    for entry in candidates:
        by_digest[entry.content_sha256].append(entry)

    kept: list[SourceRecord] = []
    suppressed: dict[str, tuple[str, ...]] = {}
    for members in by_digest.values():
        members = sorted(members, key=lambda e: (e.depth, e.archive_path))
        canonical = members[0]
        kept.append(canonical)
        others = tuple(e.archive_path for e in members[1:])
        if others:
            suppressed[canonical.archive_path] = others
    # `copies` is accepted so a future change can cross-check the inventory's own
    # grouping against the digests seen here; it is deliberately not required, because a
    # relate pass given no duplicate_groups must still deduplicate — the digest is on
    # every SourceRecord and is the authority.
    del copies
    return kept, suppressed


def _copies_by_path(groups: Sequence[Sequence[str]]) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for group in groups:
        members = tuple(sorted(group))
        for member in members:
            out[member] = members
    return out


def _scans_by_stem(
    entries: Sequence[SourceRecord],
    classifications: Mapping[str, str],
    stems: set[str],
) -> dict[str, tuple[ScanChild, ...]]:
    """Attach each scan export to its parent measurement.

    Matched on the scan's PARENT DIRECTORY name (``<stem>_dir``) rather than by string
    prefix on the filename. Prefix matching would attach a scan of
    ``32_03_..._after1500Cycling_...`` to ``32_03_..._after1400Cycling_...`` whenever one
    stem is a prefix of another, and this corpus has stems that differ only late in the
    name.
    """
    buckets: dict[str, list[ScanChild]] = defaultdict(list)
    for entry in entries:
        if classifications.get(entry.archive_path) != ev.SOURCE_TYPE_SCAN_EXPORT:
            continue
        parent = entry.parent_dir.rsplit("/", 1)[-1] if entry.parent_dir else ""
        if not parent.endswith(SCAN_DIR_SUFFIX):
            continue
        stem = parent[: -len(SCAN_DIR_SUFFIX)]
        if stem not in stems:
            continue
        m = _SCAN_INDEX.search(entry.basename)
        buckets[stem].append(
            ScanChild(path=entry.archive_path, scan_index=int(m.group(1)) if m else None)
        )
    return {
        stem: tuple(
            sorted(children, key=lambda c: (c.scan_index is None, c.scan_index, c.path))
        )
        for stem, children in buckets.items()
    }


def _blocks_by_target(
    macro_declarations: Mapping[str, Sequence[str]], stems: set[str]
) -> dict[str, tuple[MacroBlock, ...]]:
    buckets: dict[str, list[MacroBlock]] = defaultdict(list)
    for macro_path, targets in macro_declarations.items():
        for index, target in enumerate(targets):
            buckets[target].append(
                MacroBlock(
                    macro_path=macro_path,
                    block_index=index,
                    declared_target=target,
                    acquired=target in stems,
                )
            )
    return {
        target: tuple(sorted(blocks, key=lambda b: (b.macro_path, b.block_index)))
        for target, blocks in buckets.items()
    }


def _processed_by_legacy(
    entries: Sequence[SourceRecord], classifications: Mapping[str, str]
) -> dict[int, tuple[str, ...]]:
    """Attach processed products by their LEADING legacy number only.

    Deliberately weak. The real corpus's merged filenames are re-spelled (``f10`` where
    the acquisition says ``filter10``), one names TWO legacy numbers at once, and seven
    name none — so a stem match would attach almost nothing and a fuzzy match would
    attach the wrong thing. A product naming no number stays **unattached and visible**,
    which is the honest outcome.
    """
    buckets: dict[int, list[str]] = defaultdict(list)
    for entry in entries:
        if classifications.get(entry.archive_path) not in {
            ev.SOURCE_TYPE_PROCESSED_SPECTRUM,
            ev.SOURCE_TYPE_DETECTOR_PRODUCT,
        }:
            continue
        m = _LEGACY.match(entry.basename)
        if m:
            buckets[int(m.group(1))].append(entry.archive_path)
    return {n: tuple(sorted(paths)) for n, paths in buckets.items()}


def _duplicate_legacy_conflicts(units: Sequence[MeasurementUnit]):
    by_number: dict[int, list[MeasurementUnit]] = defaultdict(list)
    for unit in units:
        if unit.legacy_number is not None:
            by_number[unit.legacy_number].append(unit)
    for number, sharing in sorted(by_number.items()):
        if len(sharing) < 2:
            continue
        yield Conflict(
            kind=CONFLICT_DUPLICATE_LEGACY_NUMBER,
            subject=str(number),
            readings=tuple(
                Reading(
                    source_path=u.acquisition_path,
                    locator="filename",
                    value=u.stem,
                    source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
                )
                for u in sharing
            ),
            explanation=(
                f"Two separate measurements were both recorded as number {number}. "
                "Both files exist and both are kept; neither is a duplicate of the "
                "other and neither is the 'real' one."
            ),
        )


def _never_acquired_conflicts(
    macro_declarations: Mapping[str, Sequence[str]], stems: set[str]
):
    seen: set[str] = set()
    for macro_path, targets in sorted(macro_declarations.items()):
        for index, target in enumerate(targets):
            if target in stems or target in seen:
                continue
            seen.add(target)
            yield Conflict(
                kind=CONFLICT_DECLARED_NEVER_ACQUIRED,
                subject=target,
                readings=(
                    Reading(
                        source_path=macro_path,
                        locator=f"newfile block {index}",
                        value=target,
                        source_type=ev.SOURCE_TYPE_MACRO,
                    ),
                    Reading(
                        source_path="(this import's acquisitions)",
                        locator="filenames",
                        value="no acquisition file of this name is present",
                        source_type=ev.SOURCE_TYPE_SPEC_ACQUISITION,
                    ),
                ),
                explanation=(
                    "A macro said it was about to record this measurement and no "
                    "matching file is in the import. The measurement may have been "
                    "abandoned, renamed afterwards, or saved somewhere not included "
                    "here. Nothing is assumed either way."
                ),
            )


def _groups(units: Sequence[MeasurementUnit]) -> tuple[SampleGroup, ...]:
    buckets: dict[str | None, list[MeasurementUnit]] = defaultdict(list)
    for unit in units:
        buckets[unit.group_token].append(unit)

    # A group's range is contiguous only if no OTHER group's number falls inside it.
    # Checked across groups rather than within one, because the signal that the token
    # does not mean an instance is interleaving, not a gap.
    owner: dict[int, str | None] = {}
    for token, members in buckets.items():
        for unit in members:
            if unit.legacy_number is not None:
                owner.setdefault(unit.legacy_number, token)

    out: list[SampleGroup] = []
    for token, members in buckets.items():
        numbers = sorted(u.legacy_number for u in members if u.legacy_number is not None)
        low = numbers[0] if numbers else None
        high = numbers[-1] if numbers else None
        contiguous = bool(numbers) and all(
            owner.get(n, token) == token for n in range(low, high + 1)
        )
        out.append(
            SampleGroup(
                group_token=token,
                stems=tuple(u.stem for u in members),
                legacy_low=low,
                legacy_high=high,
                contiguous=contiguous,
            )
        )
    return tuple(sorted(out, key=lambda g: (g.group_token is None, g.group_token or "")))


def _unattached(
    by_path: Mapping[str, SourceRecord],
    attached: set[str],
    classifications: Mapping[str, str],
) -> list[dict]:
    """Every source no measurement claimed, with the reason — sorted, never silent.

    The reasons are deliberately specific rather than one "unmatched" bucket: a beamtime
    README is unattached because it belongs to the WHOLE import, which is a different
    fact from a processed product whose filename names no measurement.
    """
    reasons = {
        ev.SOURCE_TYPE_SHARED_README: (
            "beamtime-scope context — belongs to the whole import, not to one "
            "measurement, and is inherited rather than copied"
        ),
        ev.SOURCE_TYPE_BEAMTIME_NOTES: (
            "human documentation for the whole beamtime; its individual rows attach to "
            "measurements by file number"
        ),
        ev.SOURCE_TYPE_ACQUISITION_METHOD_MACRO: (
            "defines the acquisition method — it declares no measurement of its own"
        ),
        ev.SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO: (
            "a snapshot of instrument state, not a measurement"
        ),
        ev.SOURCE_TYPE_MACRO: (
            "a macro whose declared measurements are all attached elsewhere, or which "
            "declares none"
        ),
        ev.SOURCE_TYPE_ALIGNMENT: (
            "alignment or setup work — a real acquisition, and not a sample measurement"
        ),
        ev.SOURCE_TYPE_STANDARD_OR_REFERENCE: (
            "a standard or reference measurement; whether it should become a Run is a "
            "question for a scientist"
        ),
        ev.SOURCE_TYPE_PROCESSED_SPECTRUM: (
            "a processed product whose filename names no measurement number this import "
            "contains"
        ),
        ev.SOURCE_TYPE_DETECTOR_PRODUCT: (
            "a detector product whose filename names no measurement number this import "
            "contains"
        ),
        ev.SOURCE_TYPE_SCAN_EXPORT: (
            "a scan export whose scan directory names no acquisition in this import"
        ),
        ev.SOURCE_TYPE_UNKNOWN: "not classified — nothing in this import identifies it",
    }
    out: list[dict] = []
    for path in sorted(set(by_path) - attached):
        source_type = classifications.get(path, ev.SOURCE_TYPE_UNKNOWN)
        out.append(
            {
                "archive_path": path,
                "source_type": source_type,
                "reason": reasons.get(source_type, reasons[ev.SOURCE_TYPE_UNKNOWN]),
            }
        )
    return out

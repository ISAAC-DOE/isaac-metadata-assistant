"""What ONE entry in a historical archive is, and the ceilings a walk obeys.

**Declared here rather than in :mod:`bl15.archive` so the two halves can be built
independently**: the walkers that produce these records (a folder walk, a ZIP walk)
and the readers and classifiers that consume them share this file and nothing else.

Nothing in this module opens a file, walks a tree, or decodes bytes. It is the shape
and the bounds. :mod:`bl15.archive` implements the walk; every reader in this package
takes a :class:`SourceRecord` plus text the CALLER obtained, which is the same
"a parser never opens a file itself" boundary ``historical_import.SourceParser``
already draws one layer up — kept in one place instead of in every reader.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArchiveLimits:
    """Resource ceilings for one inventory walk.

    Defaults are set against the **measured** real BL15-2 archive (1,192 files, 88 MB
    uncompressed, largest single file ~500 KB — see
    ``docs/evidence/bl15-2-corpus-characterization-2026-09-16.md``) with headroom, so
    they are bounds a real corpus clears rather than numbers chosen to be round.

    A walk that meets a ceiling **refuses the entry and keeps going**, recording the
    refusal; it does not abort the inventory. A corpus with one pathological member is
    still worth inventorying, and a scientist who can see *"this file was skipped and
    why"* is better served than one handed an error page.
    """

    #: Most entries one archive may contribute. 1,192 measured; 4x headroom.
    max_entries: int = 5_000
    #: Largest single entry that will be inventoried and offered for reading.
    max_entry_bytes: int = 8_000_000
    #: Total expanded size across the whole walk.
    max_total_bytes: int = 600_000_000
    #: Most bytes a ZIP member may expand to per compressed byte. A zip bomb's
    #: signature; 1,000:1 is far above anything text achieves in practice.
    max_compression_ratio: int = 1_000
    #: Deepest path nesting. The real corpus is 2 levels; this bounds a crafted one.
    max_depth: int = 12
    #: Longest archive-relative path.
    max_path_chars: int = 1_024
    #: Bytes decoded when a classifier needs to look at the beginning of a file.
    #: Enough for a full SPEC header block (22 ``#O`` lines plus preamble) and far
    #: short of a whole scan file.
    head_bytes: int = 8_192


#: Why an entry was refused. A closed set so a surface can group them; each carries
#: the measured number and the ceiling in its detail string, never just a label.
REFUSAL_PATH_TRAVERSAL = "path_traversal"
REFUSAL_ABSOLUTE_PATH = "absolute_path"
REFUSAL_SYMLINK = "symlink"
REFUSAL_TOO_LARGE = "entry_too_large"
REFUSAL_TOTAL_TOO_LARGE = "archive_too_large"
REFUSAL_TOO_MANY_ENTRIES = "too_many_entries"
REFUSAL_COMPRESSION_RATIO = "compression_ratio"
REFUSAL_TOO_DEEP = "path_too_deep"
REFUSAL_PATH_TOO_LONG = "path_too_long"
REFUSAL_UNREADABLE = "unreadable"
REFUSAL_UNDECODABLE = "undecodable"

REFUSAL_REASONS: frozenset[str] = frozenset(
    {
        REFUSAL_PATH_TRAVERSAL,
        REFUSAL_ABSOLUTE_PATH,
        REFUSAL_SYMLINK,
        REFUSAL_TOO_LARGE,
        REFUSAL_TOTAL_TOO_LARGE,
        REFUSAL_TOO_MANY_ENTRIES,
        REFUSAL_COMPRESSION_RATIO,
        REFUSAL_TOO_DEEP,
        REFUSAL_PATH_TOO_LONG,
        REFUSAL_UNREADABLE,
        REFUSAL_UNDECODABLE,
    }
)


@dataclass(frozen=True)
class SourceRecord:
    """ONE file found in an archive, before anything has read it.

    :attr:`archive_path` is **archive-relative, forward-slashed, and normalised** —
    it is the scientist's handle on the source and it appears verbatim in every
    piece of evidence read from it. It is never absolute: an absolute path leaks the
    reader's filesystem into an audit trail, and on a ZIP it is a traversal attempt.

    :attr:`extension` is lowercase and carries **no leading dot**; it is ``""`` for
    an extensionless file. It is recorded because it is a fact about the name, and it
    is deliberately **not** how anything is classified — the real corpus has an
    extensionless macro (``run29``) sitting beside an extensionless SPEC acquisition
    (``alignment``), so a classifier keying on the extension would be wrong about
    both (see :mod:`bl15.classify`).
    """

    archive_path: str
    basename: str
    extension: str
    size_bytes: int
    #: SHA-256 of the raw bytes. **The only identity used for deduplication.** In the
    #: real corpus every ``*_dir`` also holds a byte-identical copy of its root
    #: acquisition file — 96 duplicate groups over 193 files — so a name-similarity
    #: heuristic would both miss these and wrongly fuse ``run29.mac`` with
    #: ``run29.mac.mac``, which have different content.
    content_sha256: str
    #: Archive-relative directory, ``""`` at the archive root.
    parent_dir: str
    #: Depth below the archive root; 0 for a root-level file.
    depth: int


@dataclass(frozen=True)
class ArchiveInventory:
    """Everything one safe walk found, everything it refused, and the totals.

    **:attr:`refused` is as load-bearing as :attr:`entries`.** An inventory that
    listed only what it accepted would be ``HIST-004``'s banned
    "Upload -> Spinner -> Mysterious JSON" in miniature: a scientist could not tell a
    corpus with 1,192 files from a corpus with 1,200 of which 8 were quietly dropped.
    """

    #: What the scientist called this import. Never a filesystem path.
    root_label: str
    entries: tuple[SourceRecord, ...] = ()
    #: ``{"archive_path": str, "reason": str (one of REFUSAL_REASONS),
    #: "detail": str}`` — detail states the measured value and the ceiling.
    refused: tuple[dict, ...] = ()
    total_bytes: int = 0
    #: Set when the walk stopped early (entry or byte ceiling). Distinct from a
    #: per-entry refusal: it means the inventory itself is INCOMPLETE, and a
    #: reconstruction over an incomplete inventory must say so rather than report a
    #: candidate count as if it were the whole corpus.
    truncated_reason: str | None = None
    #: Groups of two or more :attr:`SourceRecord.archive_path` sharing one
    #: ``content_sha256``, each group sorted. Membership in a group is NOT a reason
    #: to drop a member: both copies are real files the scientist has, and the
    #: consequence is only that they must not be counted as two witnesses.
    duplicate_groups: tuple[tuple[str, ...], ...] = ()

    def by_path(self) -> dict[str, SourceRecord]:
        return {e.archive_path: e for e in self.entries}

    def to_state(self) -> dict:
        return {
            "root_label": self.root_label,
            "entry_count": len(self.entries),
            "total_bytes": self.total_bytes,
            "refused": [dict(r) for r in self.refused],
            "truncated_reason": self.truncated_reason,
            "duplicate_group_count": len(self.duplicate_groups),
        }

"""Deterministic readers for facility file formats the BL15 engine does not handle.

Each module is stdlib-only and reads the LITERAL structure of a file; none interprets a value.
They return plain data (:class:`~._common.GenericRun`) and write nothing, so a caller (the
bundle builder) decides what to do with it.

:func:`collect_all_generic` runs every reader's ``sniff`` over the files nothing has claimed
yet, in a fixed precedence order, so each file is claimed at most once and every claim is
recorded. The precedence is most specific first, and the headerless two-column reader last:

1. ``ssrl_xdc``    exact first-line signature, plus its ``.rgn/.det/.exp`` companions
2. ``xdi``         ``# XDI/<v>`` first line
3. ``mca``         ``.mca`` with ``#F``, ``#@MCA`` and ``@A``
4. ``xes_tab``     ``.txt`` whose first line is tab-separated ``xes<N>`` names
5. ``two_column``  ``.txt`` of nothing but two numbers per line

Files an ISAAC deterministic reader already read are passed as ``skip`` and are never claimed.

TWO ADDITIONS (2026-10-28)
==========================
* **A ZIP found in the folder is walked one level deep** through the SAME guarded ZIP walk the
  engine uses (``bl15.archive.walk_nested_zip``: traversal, symlink, size, ratio, count and
  total-byte bounds). Its accepted members are staged, read-only, in a private temporary
  directory that is deleted before this function returns, and are offered to the readers as
  files named ``<zip path>!/<member path>``, exactly as if they were loose files. The generic
  readers read from disk Paths, which is why a member is staged rather than streamed.
* **Analysis files** (``.larix``, ``.pxp``) are read by :data:`ANALYSIS_READERS` after the run
  readers, into :attr:`UnifiedCollection.analysis_files`. They are evidence only: never a run,
  never a record group, never a processed output.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Iterable

from ...bl15 import archive as _archive
from . import igor_pxp, larch_session, mca, ssrl_xdc, two_column, xdi, xes_tab
from ._common import MAX_ANALYSIS_ENTRIES_TOTAL, AnalysisFile, FileEntry, GenericRun, Limits, walk

#: ``(name, module)`` in precedence order. The order is part of the contract.
READERS = (
    ("ssrl_xdc", ssrl_xdc),
    ("xdi", xdi),
    ("mca", mca),
    ("xes_tab", xes_tab),
    ("two_column", two_column),
)

#: ``(name, module)``: readers of a scientist's ANALYSIS files. Each module has ``sniff(rel)``
#: and ``read(path, rel, limits, entry_budget) -> AnalysisFile``. Run after :data:`READERS`;
#: they claim by extension, and the file's content decides whether it can be read.
ANALYSIS_READERS = (
    ("larch_session", larch_session),
    ("igor_pxp", igor_pxp),
)

__all__ = [
    "ANALYSIS_READERS",
    "READERS",
    "UnifiedCollection",
    "collect_all_generic",
    "igor_pxp",
    "larch_session",
    "mca",
    "ssrl_xdc",
    "two_column",
    "xdi",
    "xes_tab",
]


@dataclass
class UnifiedCollection:
    runs: list[GenericRun]
    #: One entry per file a reader consumed: ``{relative_path, reader, role}``. A path appears once.
    claims: list[dict]
    #: Files no reader claimed and no deterministic reader had read, in walk order.
    unclaimed: list[str]
    #: Files a reader's naming rule selected but it could not parse, with the reader that tried.
    unparsed: list[dict]
    refused: list[dict]
    truncation: dict[str, int]
    files_seen: int
    skipped: int
    precedence: list[str] = field(default_factory=lambda: [name for name, _ in READERS])
    #: A second claim on an already-claimed file (never expected); reported, not applied.
    duplicate_claims: list[dict] = field(default_factory=list)
    #: One per ``.larix`` / ``.pxp`` an analysis reader opened, read or refused. Evidence only.
    analysis_files: list[AnalysisFile] = field(default_factory=list)
    #: ZIPs found in the folder: ``{relative_path, walked, members, refused, detail}``.
    nested_zips: list[dict] = field(default_factory=list)
    #: Nested members the engine walk accepted but that could not be handed to the generic
    #: readers: ``{relative_path, reason}``. They are reported, never silently dropped.
    staging_failures: list[dict] = field(default_factory=list)


_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9_-]{1,15}$")


def _staged_name(index: int, member: str) -> str:
    """A collision-free file name for one staged member, KEEPING its suffix.

    The readers decide by ``Path.suffix`` (``.mca``, ``.nor`` ...), so the suffix survives; the
    rest of the name is the member's number, so two members that differ only by case or by
    Unicode normalisation (one file on a case-insensitive volume), a member called ``x`` beside
    ``x/y``, or a name segment longer than the file system allows can never collide or fail.
    The REPORTED relative path is the member's real one and is not derived from this name.
    """
    suffix = PurePosixPath(member).suffix
    return f"m{index:06d}{suffix if _SAFE_SUFFIX.match(suffix) else ''}"


def _expand_nested_zips(
    files: list[FileEntry],
    staging: Path,
    limits: Limits,
    nested: list[dict],
    refused: list[dict],
    failures: list[dict],
) -> list[FileEntry]:
    """``files`` plus every accepted member of every ``.zip`` among them, staged under ``staging``.

    Reuses ``archive.walk_nested_zip`` (all the guards) and ``archive.iter_zip_member_bytes``
    (the bounded member read). The budget is the ENGINE's: the folder's own accepted bytes and
    entries count first, then each ZIP spends what is left, so both sides accept the same
    members. A member that cannot be staged (a file-system error) or whose staged bytes do not
    hash to what the walk recorded is NOT offered to any reader and is reported in ``failures``
    with the reason; the import continues.
    """
    out: list[FileEntry] = []
    arch = limits.archive
    folder_bytes = sum(size for _r, _p, size in files if size <= arch.max_entry_bytes)
    taken = {rel for rel, _p, _s in files}
    staged_total = 0
    staged_count = 0
    index = 0
    member_index = 0
    root = staging.resolve()
    for rel, path, size in files:
        out.append((rel, path, size))
        if not rel.lower().endswith(".zip"):
            continue
        budget = replace(
            arch,
            max_entries=max(arch.max_entries - len(files) - staged_count, 0),
            max_total_bytes=max(arch.max_total_bytes - folder_bytes - staged_total, 0),
        )
        result = _archive.walk_nested_zip(
            path, container=rel, container_depth=rel.count("/"), limits=budget, taken=taken
        )
        info = result.container
        nested.append(
            {
                "relative_path": rel,
                "walked": info.walked,
                "members": len(result.entries),
                "refused": len(result.refused),
                "detail": info.detail,
            }
        )
        for row in result.refused:
            refused.append({"relative_path": row.get("archive_path"), "reason": row.get("reason")})
        if not info.walked:
            continue
        prefix = f"{rel}{_archive.NESTED_SEPARATOR}"
        expected = {e.archive_path[len(prefix) :]: e for e in result.entries}
        index += 1
        for member, data in _archive.iter_zip_member_bytes(path, list(expected), budget):
            nested_rel = f"{prefix}{member}"
            if data is None:
                failures.append({"relative_path": nested_rel, "reason": "the member could not be read again for the generic readers"})
                continue
            member_index += 1
            dest = root / f"z{index:04d}" / _staged_name(member_index, member)
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                staged_bytes = dest.read_bytes()
            except OSError as exc:
                failures.append(
                    {"relative_path": nested_rel, "reason": f"the member could not be staged ({type(exc).__name__})"}
                )
                continue
            if hashlib.sha256(staged_bytes).hexdigest() != expected[member].content_sha256:
                try:
                    dest.unlink()
                except OSError:
                    pass
                failures.append(
                    {"relative_path": nested_rel, "reason": "the staged bytes do not match the digest the walk recorded; the member was not read"}
                )
                continue
            out.append((nested_rel, dest, len(data)))
            staged_total += len(data)
            staged_count += 1
    return out


def collect_all_generic(root: str | Path, limits: Limits = Limits(), skip: Iterable[str] = ()) -> UnifiedCollection:
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("the source root must be an existing folder that is not a symlink")
    refused: list[dict] = []
    trunc: dict[str, int] = {}
    files = walk(base, limits.archive, refused, trunc)
    staging_dir = tempfile.TemporaryDirectory(prefix="isaac-nested-zip-")
    try:
        return _collect(base, files, limits, skip, refused, trunc, staging_dir)
    finally:
        staging_dir.cleanup()


def _collect(base, files, limits, skip, refused, trunc, staging_dir) -> UnifiedCollection:
    nested_zips: list[dict] = []
    staging_failures: list[dict] = []
    files = _expand_nested_zips(files, Path(staging_dir.name), limits, nested_zips, refused, staging_failures)
    skip_set = set(skip)
    claimed: set[str] = set(skip_set)
    runs: list[GenericRun] = []
    claims: list[dict] = []
    unparsed: list[dict] = []
    duplicates: list[dict] = []
    for name, module in READERS:
        result = module.collect_from_files(files, limits, set(claimed))
        for rel, role in result.consumed:
            if rel in claimed:
                duplicates.append({"relative_path": rel, "reader": name, "role": role})
                continue
            claimed.add(rel)
            claims.append({"relative_path": rel, "reader": name, "role": role})
        runs.extend(result.runs)
        unparsed.extend({**u, "reader": name} for u in result.unparsed)
    analysis: list[AnalysisFile] = []
    budget = MAX_ANALYSIS_ENTRIES_TOTAL
    for _name, module in ANALYSIS_READERS:
        for rel, path, _size in files:
            if rel in claimed or not module.sniff(rel):
                continue
            result = module.read(path, rel, limits, entry_budget=max(budget, 1))
            analysis.append(result)
            if result.refused_reason is None:
                budget -= len(result.entries)
                claimed.add(rel)
                claims.append({"relative_path": rel, "reader": result.reader_id, "role": "analysis_file"})
    unclaimed = [rel for rel, _, _ in files if rel not in claimed]
    return UnifiedCollection(
        runs=runs,
        claims=claims,
        unclaimed=unclaimed,
        unparsed=unparsed,
        refused=refused,
        truncation=trunc,
        files_seen=len(files),
        skipped=len(skip_set & {rel for rel, _, _ in files}),
        duplicate_claims=duplicates,
        analysis_files=analysis,
        nested_zips=nested_zips,
        staging_failures=staging_failures,
    )

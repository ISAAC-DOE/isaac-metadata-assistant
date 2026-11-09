"""Deterministic readers for facility file formats the BL15 engine does not handle.

Each module is stdlib-only and reads the LITERAL structure of a file; none interprets a value.
They return plain data (:class:`~._common.GenericRun`) and write nothing, so a caller (the
bundle builder) decides what to do with it.

:func:`collect_all_generic` runs every reader's ``sniff`` over the files nothing has claimed
yet, in a fixed precedence order, so each file is claimed at most once and every claim is
recorded. The precedence is most specific first, and the headerless two-column reader last:

1. ``ssrl_xdc``    exact first-line signature (2.0 or 4.0), plus its ``.rgn/.det/.exp`` companions
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

A ZIP GIVEN AS THE ROOT (2026-11-09)
====================================
:func:`collect_all_generic_zip` runs the same readers over a top-level ZIP's members, so a ZIP of a
folder gives the readers what the folder gives them. Its members are the ENGINE's own walk of a
ZIP root (``bl15.archive.inventory_zip`` with ``refuse_duplicates=True``, exactly the call
``historical_import`` makes): the same guards and refusals, the same relative paths (the member
path with a "compress this folder" wrapper stripped by ``common_root_prefix``, no ``<zip>!/``
prefix), ``__MACOSX/`` and ``.DS_Store`` left out as the engine leaves them out. Accepted members
are staged and digest-checked exactly as a nested ZIP's are, and offered in the order the folder
walk would list the same files. As for the engine, a ZIP among the members is NOT opened.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import zipfile
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
    "collect_all_generic_zip",
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
    #: The ``run_key`` of each run a reader returned as LATE (:attr:`~._common.ReaderResult.late_runs`), placed
    #: after every reader's runs: the import numbers their candidates after every other run's too.
    late_run_keys: list[str] = field(default_factory=list)
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


def _stage_member(dest: Path, data: bytes, digest: str, rel: str, failures: list[dict]) -> bool:
    """Write one walked member to ``dest`` and check its bytes against the walk's ``digest``.

    ``True`` when the staged file may be offered to the readers. Otherwise the reason is appended
    to ``failures`` under ``rel`` (the member's reported path) and nothing is left at ``dest``.
    """
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        staged_bytes = dest.read_bytes()
    except OSError as exc:
        failures.append({"relative_path": rel, "reason": f"the member could not be staged ({type(exc).__name__})"})
        return False
    if hashlib.sha256(staged_bytes).hexdigest() != digest:
        try:
            dest.unlink()
        except OSError:
            pass
        failures.append(
            {"relative_path": rel, "reason": "the staged bytes do not match the digest the walk recorded; the member was not read"}
        )
        return False
    return True


def _folder_walk_order(rel: str) -> list[str]:
    """The sort key that lists archive paths in the order :func:`~._common.walk` lists the same
    files in a folder: depth-first, each directory's entries by name, so ``b/x`` comes before
    ``b.txt`` (``"b" < "b.txt"``) where a plain string sort would put it after (``"." < "/"``)."""
    return rel.split("/")


def _zip_root_members(
    zip_path: Path,
    staging: Path,
    limits: Limits,
    refused: list[dict],
    trunc: dict[str, int],
    failures: list[dict],
) -> list[FileEntry]:
    """Every member of the top-level ZIP the ENGINE accepts, staged under ``staging``.

    The walk IS the engine's: ``archive.inventory_zip(..., refuse_duplicates=True)``, the call
    ``historical_import._inventory_and_containers_of`` makes for a ZIP root, so the guards
    (traversal, absolute, symlink, size, declared and measured ratio, entry-count, total-byte,
    depth, path length, duplicate paths), the ``__MACOSX/`` / ``.DS_Store`` exclusion and the
    wrapper-folder strip all match it, and each staged member is reported under the very path the
    engine gives it. The bytes come through ``archive.iter_zip_member_bytes`` (the bounded member
    read); the member name it is asked for re-derives the stripped wrapper exactly as the engine's
    own ``_locate_zip_member`` does. Nothing is offered to a reader before its staged bytes hash
    to the walk's digest.
    """
    inventory = _archive.inventory_zip(
        zip_path, root_label=zip_path.name, limits=limits.archive, refuse_duplicates=True
    )
    for row in inventory.refused:
        refused.append({"relative_path": row.get("archive_path"), "reason": row.get("reason")})
    if inventory.truncated_reason:
        trunc[f"zip_walk_{inventory.truncated_reason}"] = 1
    if not inventory.entries:
        return []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:  # NAMES ONLY: nothing is read here
            prefix = _archive.common_root_prefix(
                i.filename for i in zf.infolist() if not i.is_dir() and not _archive.is_os_metadata(i.filename)
            )
    except (zipfile.BadZipFile, OSError, EOFError):
        prefix = None  # the engine walk opened it a moment ago; a failure here fails each member below
    by_member = {(f"{prefix}/{e.archive_path}" if prefix else e.archive_path): e for e in inventory.entries}
    root = staging.resolve()
    out: list[FileEntry] = []
    member_index = 0
    for member, data in _archive.iter_zip_member_bytes(zip_path, list(by_member), limits.archive):
        entry = by_member[member]
        if data is None:
            failures.append(
                {"relative_path": entry.archive_path, "reason": "the member could not be read again for the generic readers"}
            )
            continue
        member_index += 1
        dest = root / "z0001" / _staged_name(member_index, member)
        if _stage_member(dest, data, entry.content_sha256, entry.archive_path, failures):
            out.append((entry.archive_path, dest, len(data)))
    out.sort(key=lambda f: _folder_walk_order(f[0]))
    return out


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
            if not _stage_member(dest, data, expected[member].content_sha256, nested_rel, failures):
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


def collect_all_generic_zip(
    zip_path: str | Path, limits: Limits = Limits(), skip: Iterable[str] = ()
) -> UnifiedCollection:
    """:func:`collect_all_generic` for a ZIP given AS THE ROOT of an import.

    The readers see the members the engine's walk of that ZIP accepts, under the engine's own
    relative paths (so ``skip``, the bundle's source rows and every claim are one set of strings),
    staged in a private temporary directory that is removed before this returns. A ZIP among the
    members is not opened, as the engine does not open it for a ZIP root: it is offered to the
    readers like any other member (none claims it) and stays an ordinary unread file.
    """
    path = Path(zip_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("the source ZIP must be an existing file that is not a symlink")
    refused: list[dict] = []
    trunc: dict[str, int] = {}
    staging_failures: list[dict] = []
    staging_dir = tempfile.TemporaryDirectory(prefix="isaac-zip-root-")
    try:
        files = _zip_root_members(path, Path(staging_dir.name), limits, refused, trunc, staging_failures)
        return _collect(
            path, files, limits, skip, refused, trunc, staging_dir,
            expand_nested=False, staging_failures=staging_failures,
        )
    finally:
        staging_dir.cleanup()


def _collect(
    base, files, limits, skip, refused, trunc, staging_dir, *, expand_nested: bool = True,
    staging_failures: list[dict] | None = None,
) -> UnifiedCollection:
    nested_zips: list[dict] = []
    staging_failures = list(staging_failures or ())
    if expand_nested:
        files = _expand_nested_zips(files, Path(staging_dir.name), limits, nested_zips, refused, staging_failures)
    skip_set = set(skip)
    claimed: set[str] = set(skip_set)
    runs: list[GenericRun] = []
    claims: list[dict] = []
    unparsed: list[dict] = []
    duplicates: list[dict] = []
    late_runs: list[GenericRun] = []
    for name, module in READERS:
        result = module.collect_from_files(files, limits, set(claimed))
        for rel, role in result.consumed:
            if rel in claimed:
                duplicates.append({"relative_path": rel, "reader": name, "role": role})
                continue
            claimed.add(rel)
            claims.append({"relative_path": rel, "reader": name, "role": role})
        runs.extend(result.runs)
        late_runs.extend(getattr(result, "late_runs", None) or ())
        unparsed.extend({**u, "reader": name} for u in result.unparsed)
    # runs a reader marks LATE (the SSRL XDC reader's runs its 1.0.0 did not find: 2.0-only and bare
    # ``NAME.NNN`` series) come after every reader's runs: they only ADD run ids after the earlier ones
    runs.extend(late_runs)
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
        late_run_keys=[r.run_key for r in late_runs],
    )

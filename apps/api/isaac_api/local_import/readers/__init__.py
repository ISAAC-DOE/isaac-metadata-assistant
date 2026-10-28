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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import mca, ssrl_xdc, two_column, xdi, xes_tab
from ._common import GenericRun, Limits, walk

#: ``(name, module)`` in precedence order. The order is part of the contract.
READERS = (
    ("ssrl_xdc", ssrl_xdc),
    ("xdi", xdi),
    ("mca", mca),
    ("xes_tab", xes_tab),
    ("two_column", two_column),
)

__all__ = ["READERS", "UnifiedCollection", "collect_all_generic", "mca", "ssrl_xdc", "two_column", "xdi", "xes_tab"]


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


def collect_all_generic(root: str | Path, limits: Limits = Limits(), skip: Iterable[str] = ()) -> UnifiedCollection:
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("the source root must be an existing folder that is not a symlink")
    refused: list[dict] = []
    trunc: dict[str, int] = {}
    files = walk(base, limits.archive, refused, trunc)
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
    )

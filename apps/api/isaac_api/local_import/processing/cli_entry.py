"""Thin entry points for ``isaac bundle group`` and ``isaac process`` (wired by the bundle CLI).

Writer note: ``local_import.bundle`` has no API (yet) to write ``record_groups`` or
``processing_results`` INTO ``bundle.json``, so these write side files beside it:

* ``<bundle_dir>/record_groups.json`` — ``record_groups[]`` (bundle-v1.1 shape; each group
  may carry ``merge_candidate_ids``), ``merge_candidates[]`` (groups a scientist can merge
  with one decision), ``engine_reading_issues``, ``key_classes`` and
  ``unread_acquisition_groups[]`` (acquisitions with no bundle run; not record groups);
* ``<bundle_dir>/processing/processing_results.json`` — ``processing_results[]`` and
  ``unread_acquisition_results[]``.

``bundle.json`` is never modified here. When ``bundle.json`` itself carries
``record_groups`` (merged in later, possibly scientist-edited), those are processed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .. import grouping as G

GROUPS_FILE = "record_groups.json"
GROUPS_FORMAT = "isaac.record-groups"
GROUPS_FORMAT_VERSION = "0.1.0"


def build_groups_payload(bundle: Mapping) -> dict:
    proposal = G.propose(bundle)
    groups = proposal["record_groups"]
    unread = G.propose_unread_acquisition_groups(bundle)
    return {
        "format": GROUPS_FORMAT,
        "format_version": GROUPS_FORMAT_VERSION,
        "rule_id": G.GROUPING_RULE_ID,
        "bundle_id": bundle.get("bundle_id"),
        "experiment_key": G.experiment_key_of(bundle),
        "notice": "Proposed groups (status: proposed). A scientist confirms, splits or merges them; nothing here is official.",
        "summary": G.summarize_groups(groups),
        "unread_summary": G.summarize_groups(unread),
        "merge_candidate_summary": {
            "merge_candidates": len(proposal["merge_candidates"]),
            "groups_in_a_candidate": len({g for mc in proposal["merge_candidates"] for g in mc["group_ids"]}),
            "runs_with_engine_reading_issues": len(proposal["engine_reading_issues"]["per_run"]),
        },
        "record_groups": groups,
        "merge_candidates": proposal["merge_candidates"],
        "engine_reading_issues": proposal["engine_reading_issues"],
        "key_classes": proposal["key_classes"],
        "unread_acquisition_groups": unread,
        "unread_merge_candidates": G.propose_unread_merge_candidates(unread),
    }


def run_group(bundle_dir: Path | str, *, write: bool = True, bundle: Mapping | None = None) -> dict:
    """Propose record groups for the bundle in ``bundle_dir``; write ``record_groups.json``."""
    from ..bundle import load_bundle

    bundle_dir = Path(bundle_dir)
    bundle = bundle if bundle is not None else load_bundle(bundle_dir)
    payload = build_groups_payload(bundle)
    if write:
        path = bundle_dir / GROUPS_FILE
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    return payload


def run_process(
    bundle_dir: Path | str,
    *,
    source_root: Path | str | None = None,
    params: Mapping[str, Any] | None = None,
    params_file: Path | str | None = None,
    group_ids: Sequence[str] | None = None,
    athena: bool = True,
    regroup: bool = False,
    bundle: Mapping | None = None,
    calibration_approvals: Mapping[str, Mapping] | None = None,
) -> dict:
    """Run protocol ``isaac.xas.v0`` over the bundle's groups (grouping first when absent).

    ``source_root``: the folder the bundle was imported from (the bundle stores only
    relative paths unless imported with ``--record-local-root``). ``params`` /
    ``params_file`` (JSON ``{section: {key: value}}``) override protocol defaults — a params
    file is never a scientist decision. ``calibration_approvals`` (``{group_id: {element, edge,
    decided_by, decision_id}}``, from the scientist's processing-approval decisions) is the
    only input that applies a calibration shift. Each run writes to
    ``processing/<group_id>/<run_id>/``; earlier runs are never overwritten.
    """
    from .run import process_bundle

    bundle_dir = Path(bundle_dir)
    if regroup or not (bundle_dir / GROUPS_FILE).is_file():
        run_group(bundle_dir, bundle=bundle)
    overrides: dict = {}
    if params_file:
        overrides = json.loads(Path(params_file).read_text(encoding="utf-8"))
    for section, values in (params or {}).items():
        overrides.setdefault(section, {}).update(values)
    return process_bundle(
        bundle_dir,
        source_root=Path(source_root) if source_root else None,
        params=overrides or None,
        group_ids=group_ids,
        athena=athena,
        bundle=bundle,
        calibration_approvals=calibration_approvals,
    )

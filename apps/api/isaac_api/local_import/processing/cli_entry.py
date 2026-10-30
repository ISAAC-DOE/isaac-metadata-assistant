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


def _header_reader(root: Path | None):
    """``relative_path -> header lines | None`` over the source folder (stdlib reader)."""
    from pathlib import PurePosixPath

    from .readers import read_scan_file

    def read(rel: str):
        if root is None or not rel:
            return None
        p = PurePosixPath(rel)
        if p.is_absolute() or ".." in p.parts:
            return None
        full = root.joinpath(*p.parts)
        if full.is_symlink() or not full.is_file():
            return None
        t = read_scan_file(full)
        return None if t.error else t.header_lines

    return read


def build_groups_payload(bundle: Mapping, *, source_root: Path | None = None, context: Mapping | None = None) -> dict:
    proposal = G.propose(bundle, context=context)
    groups = proposal["record_groups"]
    unread = G.propose_unread_acquisition_groups(bundle)
    cpos = (proposal.get("counter_positions_decision") or {}).get("positions") or ()
    unread_candidates = G.propose_unread_merge_candidates(unread, counter_positions=cpos)
    root = Path(source_root) if source_root else None
    if root is None and (bundle.get("source_root") or {}).get("local_root_hint"):
        root = Path(bundle["source_root"]["local_root_hint"])
    n_unread_before = len(unread)
    unread, unread_candidates = G.promote_unread_by_headers(unread, unread_candidates, _header_reader(root))
    # ONE experiment-scope counter question across bundle runs AND unread acquisitions.
    pos_count: dict[int, int] = {}
    for q in proposal["experiment_questions"]:
        for p, n in (q.get("candidates_resolved_by_position") or {}).items():
            pos_count[int(p)] = pos_count.get(int(p), 0) + int(n)
    for mc in unread_candidates:
        if not mc.get("names_agree_on_non_counter_tokens", True):
            for p in G._differing_number_positions(mc["reasons"][0]["stems"], counter_positions=cpos):
                pos_count[p] = pos_count.get(p, 0) + 1
    q = G.counter_question(pos_count, proposal["counter_positions_decision"])
    experiment_questions = [x for x in proposal["experiment_questions"] if x.get("kind") != "naming_counter_positions"] + ([q] if q else [])
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
        "experiment_questions": experiment_questions,
        "violations_prevented": len(proposal["violations_prevented"]),
        "merges_prevented_by_name_tokens": proposal["merges_prevented_by_name_tokens"],
        "counter_positions_decision": proposal["counter_positions_decision"],
        "unread_acquisition_groups": unread,
        "unread_merge_candidates": unread_candidates,
        "unread_header_promotion": {
            "source_root_available": root is not None,
            "acquisitions": n_unread_before,
            "groups_after": len(unread),
            "multi_acquisition_groups": sum(1 for g in unread if len(g.get("acquisition_keys") or ()) > 1),
        },
        "condition_violations": proposal["condition_violations"],
    }


def run_group(bundle_dir: Path | str, *, write: bool = True, bundle: Mapping | None = None, source_root: Path | str | None = None) -> dict:
    """Propose record groups for the bundle in ``bundle_dir``; write ``record_groups.json``.

    ``source_root`` (else the bundle's ``local_root_hint``) lets acquisitions with no bundle
    run be grouped on their literal header statements; without it they stay merge candidates."""
    from ..bundle import load_bundle

    bundle_dir = Path(bundle_dir)
    bundle = bundle if bundle is not None else load_bundle(bundle_dir)
    payload = build_groups_payload(bundle, source_root=Path(source_root) if source_root else None)
    if write:
        path = bundle_dir / GROUPS_FILE
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    return payload


#: The key ``run_process`` adds to ``summary`` on a ``--group`` run: how many undecided results of
#: OTHER groups it carried forward unchanged (so the bundle writer keeps them; see run_process).
OTHER_GROUPS_KEPT = "results_of_other_groups_kept"


def _refuse(message: str):
    from ..mutations import MutationRefused

    return MutationRefused(message, code=2)


def _scan_paths(bundle: Mapping, bundle_dir: Path, group_ids: Sequence[str] | None) -> list[tuple[str, str | None]]:
    """``(relative_path, source_id)`` of every scan the groups to be processed list — the files
    processing must READ. Record groups come from where processing takes them (``bundle.json``,
    else ``record_groups.json``); with neither, every run's scans. Unread acquisitions too."""
    from .run import group_scans

    runs_by_key = {r.get("run_key"): r for r in bundle.get("runs") or ()}
    groups: list = list(bundle.get("record_groups") or ())
    if not groups:
        side = bundle_dir / GROUPS_FILE
        try:
            groups = list(json.loads(side.read_text(encoding="utf-8")).get("record_groups") or ()) if side.is_file() else []
        except (OSError, ValueError):
            groups = []
    if not groups:
        groups = [{"group_id": None, "member_run_keys": list(runs_by_key)}]
    groups = groups + G.propose_unread_acquisition_groups(bundle)
    wanted = set(group_ids or ())
    out: list[tuple[str, str | None]] = []
    for g in groups:
        if wanted and g.get("group_id") not in wanted:
            continue
        scans, _stems, _sel = group_scans(g, runs_by_key)
        out.extend((s.get("relative_path") or "", s.get("source_id")) for s in scans if s.get("relative_path"))
    return out


def reachable_source_root(bundle: Mapping, bundle_dir: Path, source_root: Path | str | None,
                          group_ids: Sequence[str] | None = None) -> Path | None:
    """The folder processing reads the raw scans from, or a refusal (``MutationRefused``, code 2).

    ``--source`` when given, else the bundle's ``source_root.local_root_hint`` (recorded only by
    ``isaac import --record-local-root``). Refused, BEFORE anything is written, when neither is
    given, when the folder does not exist, or when NOT ONE scan file the groups list is found
    there with the bytes the bundle recorded (``content_sha256``) — the wrong folder, or a moved
    one. Processing then would only store a ``fail``/``no_readable_scan`` verdict per group,
    which says nothing about the data. Some files missing is not refused: each missing scan is
    reported on its own result. ``None`` when the groups list no scan at all (nothing to read)."""
    from .run import _resolve_source, sha256_file

    paths = _scan_paths(bundle, bundle_dir, group_ids)
    sr = bundle.get("source_root") or {}
    hint = sr.get("local_root_hint")
    zipped = sr.get("kind") == "zip"
    what = "the beamtime folder you imported" + (" (unzipped: processing reads a folder, not a ZIP)" if zipped else "")
    if source_root:
        root, named = Path(source_root).expanduser(), f"--source {source_root}"
    elif hint:
        root, named = Path(hint), "the folder this bundle recorded at import (local_root_hint)"
    else:
        if not paths:
            return None
        raise _refuse(
            "Nothing was processed and nothing was written: this bundle does not record where its source is "
            f"(that is the default), so the raw scan files cannot be read. Pass --source <{what}>."
        )
    if not root.is_dir():
        raise _refuse(f"Nothing was processed and nothing was written: {named} is not an existing folder on this "
                      f"computer. Pass --source <{what}>.")
    if not paths:
        return root
    sources = {s.get("source_id"): s for s in bundle.get("sources") or () if s.get("source_id")}
    missing = changed = 0
    for rel, sid in paths:
        full = _resolve_source(root, rel)
        if full is None or not full.is_file():
            missing += 1
            continue
        expected = (sources.get(sid) or {}).get("content_sha256")
        try:
            if not expected or sha256_file(full) == expected:
                return root
        except OSError:
            missing += 1
            continue
        changed += 1
    detail = f"{missing} not found" + (f", {changed} with different bytes than were imported" if changed else "")
    raise _refuse(
        f"Nothing was processed and nothing was written: none of the {len(paths)} scan file(s) these groups list "
        f"could be read from {named} ({detail}). Pass --source <{what}>."
    )


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
    from ..bundle import PROCESSING_STATE_DECISIONS, PROCESSING_UNDECIDED_STATES, load_bundle, processing_id
    from .run import process_bundle

    bundle_dir = Path(bundle_dir)
    bundle = bundle if bundle is not None else load_bundle(bundle_dir)
    # REFUSE BEFORE ANYTHING IS WRITTEN (record_groups.json, processing/) when the raw scans cannot be read.
    root = reachable_source_root(bundle, bundle_dir, source_root, group_ids)
    if regroup or not (bundle_dir / GROUPS_FILE).is_file():
        run_group(bundle_dir, bundle=bundle, source_root=root)
    overrides: dict = {}
    if params_file:
        overrides = json.loads(Path(params_file).read_text(encoding="utf-8"))
    for section, values in (params or {}).items():
        overrides.setdefault(section, {}).update(values)
    payload = process_bundle(
        bundle_dir,
        source_root=root,
        params=overrides or None,
        group_ids=group_ids,
        athena=athena,
        bundle=bundle,
        calibration_approvals=calibration_approvals,
    )
    if group_ids and payload.get("status") == "processed":
        # `--group` REPLACES ONLY THAT GROUP'S RESULTS. The bundle writer (mutations.process) keeps the
        # decided results and the superseded groups' and replaces every other stored result with this
        # run's, so the undecided results of the groups NOT named are carried forward here, unchanged.
        wanted = set(group_ids)
        decided = {d["target"]["id"] for d in bundle.get("scientist_decisions") or ()
                   if (d.get("target") or {}).get("kind") == "processing_result" and d.get("decision") in PROCESSING_STATE_DECISIONS}
        known = {g.get("group_id") for g in bundle.get("record_groups") or ()}
        others = [dict(r) for r in bundle.get("processing_results") or ()
                  if r.get("group_id") not in wanted and r.get("group_id") in known
                  and processing_id(r) not in decided and r.get("state") in PROCESSING_UNDECIDED_STATES]
        payload["processing_results"] = others + list(payload.get("processing_results") or ())
        if isinstance(payload.get("summary"), dict):
            payload["summary"][OTHER_GROUPS_KEPT] = len(others)
    return payload

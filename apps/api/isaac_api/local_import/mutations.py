"""Mutations of an ISAAC Local Import Bundle (slice LOCAL-2). No hand-edited JSON.

Every write here goes through :func:`save_bundle`, which (1) re-derives every state
with :func:`bundle.apply_derivations` and rebuilds ``questions[]``, (2) re-validates
the whole bundle against v1 and REFUSES to write an invalid one, (3) holds an
exclusive lock on the bundle directory, and (4) replaces ``bundle.json`` atomically
(temp file + ``os.replace``), then regenerates the derived section files.

THE BLIND PROTOCOL. ``exposures[]`` records every time a CLI command PRINTED a
target's parser value (``bundle show``, ``bundle list candidates``, ``bundle reveal``).
``annotate --blind`` is honoured only when no exposure exists for that target;
otherwise the interpretation is stored with ``blind: false`` and the reason. The CLI
cannot see a person or an agent reading ``bundle.json`` or ``reading.full.json``
directly — a blind claim is only as good as that discipline, and the contract says so.

IDENTITY. ``decided_by.identity`` is always ``local_unverified``: this build
authenticates nobody. An ORCID iD is stored as ``orcid_claimed`` — a credit value the
local user typed — and is never used to decide anything.
"""

from __future__ import annotations

import fcntl
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import bundle as B

ORCID_RE = re.compile(r"\A[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]\Z")
MAX_EXCERPT_CHARS = 4_000
MAX_EXCERPTS = 5
EXCERPT_CONTEXT_LINES = 3

#: Crosscheck categories -> how a candidate is recognised (target path prefix or key).
CROSSCHECK_CATEGORIES: Sequence[tuple[str, tuple[str, ...], tuple[str, ...]]] = (
    ("sample_identity", ("sample.material.name", "sample.sample_id"), ("sample_name",)),
    ("potential_or_reference_basis", ("context.electrochemistry.potential", "context.electrochemistry.reference"), ("potential_magnitude", "potential_scale")),
    ("reaction", ("context.electrochemistry.reaction",), ()),
    ("environment", ("context.environment",), ()),
    ("cell_type", ("context.electrochemistry.cell_type",), ()),
    ("acquisition_time", ("timestamps.acquired_start_utc",), ()),
)


class MutationRefused(ValueError):
    """A mutation that was refused; nothing was written. ``code`` is the exit code."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- load / lock / save -------------------------------------------------------------------


@contextmanager
def locked(bundle_dir: Path):
    """An exclusive advisory lock on ``<dir>/.bundle.lock`` for one read-modify-write."""
    bundle_dir = Path(bundle_dir)
    lock = bundle_dir / ".bundle.lock"
    with open(lock, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load(bundle_dir: Path) -> dict:
    path = B.bundle_path(Path(bundle_dir))
    if not path.is_file():
        raise MutationRefused(f"No bundle.json at {bundle_dir}.", code=6)
    try:
        return B.load_bundle(path)
    except B.BundleInvalid as exc:
        raise MutationRefused(f"Unreadable bundle: {exc}", code=1) from exc


def save_bundle(bundle_dir: Path, bundle: dict) -> None:
    """Re-derive, re-validate, then atomically replace. Refuses an invalid result."""
    from . import cli

    bundle["format_version"] = B.FORMAT_VERSION
    for key in ("record_groups", "processing_results", "exposures"):
        bundle.setdefault(key, [])
    B.refresh_questions(bundle)
    B.apply_derivations(bundle)
    errors = B.validate_bundle(bundle)
    if errors:
        raise MutationRefused(
            "The change would leave the bundle invalid, so nothing was written:\n  - "
            + "\n  - ".join(errors[:20]),
            code=5,
        )
    bundle_dir = Path(bundle_dir)
    cli._atomic_write(bundle_dir / B.BUNDLE_FILE, B.encode(bundle))
    for name, data in cli.section_payloads(bundle).items():
        cli._atomic_write(bundle_dir / name, data)


def mutate(bundle_dir: Path, change) -> Any:
    """Lock, load, apply ``change(bundle)``, save. Returns what ``change`` returned."""
    with locked(Path(bundle_dir)):
        bundle = load(bundle_dir)
        result = change(bundle)
        save_bundle(bundle_dir, bundle)
        return result


# --- target lookup ---------------------------------------------------------------------------


def resolve_target(bundle: Mapping, target_id: str) -> tuple[str, dict]:
    """``(kind, object)`` for an id, by the bundle's own id spaces. ``experiment`` names
    the whole beamtime (e.g. for ``set_counter_positions``)."""
    if target_id == "experiment":
        return "experiment", {"id": "experiment"}
    sections = (
        ("candidate", "candidates", "candidate_id"),
        ("missing_value", "missing_values", "value_id"),
        ("conflict", "conflicts", "conflict_id"),
        ("source", "sources", "source_id"),
        ("run", "runs", "run_id"),
        ("record_group", "record_groups", "group_id"),
    )
    for kind, section, key in sections:
        for obj in bundle.get(section) or ():
            if obj.get(key) == target_id:
                return kind, obj
    for result in bundle.get("processing_results") or ():
        if B.processing_id(result) == target_id:
            return "processing_result", result
    raise MutationRefused(f"No target with id {target_id!r} in this bundle.", code=6)


def _candidate_of_conflict(bundle: Mapping, conflict: Mapping) -> str | None:
    return conflict.get("candidate_id")


def record_exposure(bundle: dict, kind: str, target_id: str, command: str) -> None:
    """Record that ``command`` printed this target's parser value. First one per
    (target, command) is kept — the question a blind check asks is WHETHER and WHEN."""
    exposures = bundle.setdefault("exposures", [])
    for e in exposures:
        if e["target"] == {"kind": kind, "id": target_id} and e["command"] == command:
            return
    exposures.append(
        {
            "exposure_id": f"x-{len(exposures) + 1:06d}",
            "target": {"kind": kind, "id": target_id},
            "command": command,
            "at_utc": now_utc(),
        }
    )


def exposures_for(bundle: Mapping, kind: str, target_id: str) -> list[dict]:
    return [e for e in bundle.get("exposures") or () if e["target"] == {"kind": kind, "id": target_id}]


def expose_and_load(bundle_dir: Path, targets: Iterable[tuple[str, str]], command: str) -> dict:
    """Record exposures FIRST (durably), then hand back the bundle for printing. If the
    exposure cannot be written, nothing is printed — the caller gets the refusal."""
    targets = list(targets)

    def change(bundle):
        for kind, tid in targets:
            record_exposure(bundle, kind, tid, command)
            if kind == "conflict":
                _, conflict = resolve_target(bundle, tid)
                cid = conflict.get("candidate_id")
                if cid:
                    record_exposure(bundle, "candidate", cid, command)
        return bundle

    return mutate(bundle_dir, change)


# --- annotate (AI interpretation) -----------------------------------------------------------


def parse_value(raw: str | None, as_json: bool) -> Any:
    if raw is None:
        return None
    if not as_json:
        return raw
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise MutationRefused(f"--value is not valid JSON: {exc}") from exc


def annotate(
    bundle_dir: Path,
    *,
    target_id: str,
    value: Any,
    excerpt_locator: str | None,
    source_id: str | None,
    model_id: str,
    blind: bool,
    rationale: str,
) -> dict:
    """Store ONE AI interpretation. It can lift a value to ``needs_review`` and never
    higher (``bundle.derive_value_state``); it never settles a conflict."""

    def change(bundle):
        kind, obj = resolve_target(bundle, target_id)
        if kind not in ("candidate", "missing_value", "record_group", "source", "run", "processing_result"):
            raise MutationRefused(f"An AI interpretation cannot target a {kind}.")
        if source_id is not None and source_id not in {s["source_id"] for s in bundle["sources"]}:
            raise MutationRefused(f"Unknown source {source_id!r}.", code=6)
        prior = exposures_for(bundle, kind, target_id)
        if blind and not prior:
            is_blind, basis = True, "No CLI command had printed this target's parser value before this reading."
        elif blind:
            first = prior[0]
            is_blind, basis = False, (
                f"--blind was requested, but `{first['command']}` printed this target's parser "
                f"value at {first['at_utc']}, so the reading is not blind."
            )
        else:
            is_blind, basis = False, "Not requested as blind."
        interps = bundle.setdefault("ai_interpretations", [])
        entry = {
            "interpretation_id": f"ai-{len(interps) + 1:04d}",
            "target": {"kind": kind, "id": target_id},
            "proposed_value": value,
            "rationale": rationale or "",
            "source_refs": [{"source_id": source_id, "locator": excerpt_locator}] if (source_id or excerpt_locator) else [],
            "method": "ai_interpretation",
            "model": {"model_id": model_id},
            "created_utc": now_utc(),
            "max_state": "needs_review",
            "blind": is_blind,
            "blind_basis": basis,
            "excerpt_locator": excerpt_locator,
        }
        interps.append(entry)
        if kind == "candidate":
            if len(obj["evidence"]) >= B.MAX_EVIDENCE_PER_CANDIDATE:
                obj["evidence_truncated"] = True
            else:
                path = None
                if source_id:
                    path = next(s["relative_path"] for s in bundle["sources"] if s["source_id"] == source_id)
                obj["evidence"].append(
                    {
                        "evidence_id": f"{obj['candidate_id']}.ai{len(interps):04d}",
                        "source_id": source_id,
                        "relative_path": path,
                        "locator": excerpt_locator or "(no locator given)",
                        "statement_key": obj["statement_key"],
                        "literal_value": value,
                        "method": "ai_interpretation",
                        "method_id": model_id,
                        "relation": "context",
                        "reading_index": None,
                        "normalization": [],
                    }
                )
            obj["evidence_total"] = max(obj["evidence_total"] + 1, len(obj["evidence"]))
            obj["evidence_truncated"] = obj["evidence_total"] > len(obj["evidence"])
        return entry

    return mutate(bundle_dir, change)


# --- decide (scientist decision) ------------------------------------------------------------


def _has_source_evidence(candidate: Mapping) -> bool:
    return any(e["method"] in ("deterministic_parser", "stored_rule") for e in candidate["evidence"])


def _check_decision(bundle: Mapping, kind: str, obj: Mapping, decision: str, value: Any, *, bulk: bool) -> None:
    allowed = B.DECISIONS_BY_KIND.get(kind)
    if allowed is None:
        raise MutationRefused(f"A {kind} cannot be decided.")
    if decision not in allowed:
        raise MutationRefused(f"`{decision}` is not a decision for a {kind}; allowed: {', '.join(sorted(allowed))}.")
    if decision == "correct" and value is None:
        raise MutationRefused("`correct` needs --value.")
    if kind == "candidate" and decision == "confirm":
        if value is None and obj["value"] is None:
            raise MutationRefused(
                f"{obj['candidate_id']} carries no value to confirm. Use `correct --value ...` "
                "to give one."
            )
        if bulk and not _has_source_evidence(obj):
            raise MutationRefused(f"{obj['candidate_id']} has no source evidence; a bulk confirmation needs it.")
    if kind in ("missing_value", "conflict") and decision in ("confirm", "correct") and value is None:
        raise MutationRefused(f"Deciding a {kind} needs --value: there is no single extracted value to confirm.")


def decide(
    bundle_dir: Path,
    *,
    target_ids: Sequence[str],
    decision: str,
    value: Any,
    by: str,
    orcid: str | None,
    note: str | None = None,
    split_into: Sequence[Sequence[str]] | None = None,
    merge_with: Sequence[str] | None = None,
    qc_status: str | None = None,
    qc_note: str | None = None,
    element: str | None = None,
    edge: str | None = None,
    positions: Sequence[int] | None = None,
) -> dict:
    """Record a scientist decision for each target (ALL-OR-NOTHING), idempotently.

    Replaying the same decision for a target whose latest decision is already identical
    records nothing new. Each target is its own entry even in a bulk call, sharing a
    ``batch_id``.
    """
    problem = B.decider_name_problem(by)
    if problem:
        raise MutationRefused(f"--by is required: the name of the person deciding (this one {problem.replace('has ', 'has ', 1)}).")
    if orcid is not None and not ORCID_RE.fullmatch(orcid):
        raise MutationRefused("--orcid must look like 0000-0000-0000-0000 (last character may be X).")
    if not target_ids:
        raise MutationRefused("No target given.")
    if qc_status is not None:
        allowed = qc_status_vocabulary()
        if qc_status not in allowed:
            raise MutationRefused(f"--qc-status must be one of {', '.join(allowed)} (measurement.qc.status).")
        if decision != "approve":
            raise MutationRefused("--qc-status goes with --decision approve on a processing result.")
    if decision == "approve_calibration":
        if not (element and re.fullmatch(r"[A-Z][a-z]?", element)) or not (edge and re.fullmatch(r"K|L[1-3]|M[1-5]", edge)):
            raise MutationRefused("approve_calibration needs --element (e.g. Ir) and --edge (K, L1-L3, M1-M5).")
    elif element or edge:
        raise MutationRefused("--element/--edge go with --decision approve_calibration on a record group.")
    if decision == "set_counter_positions":
        if (
            not positions
            or len(positions) > 8
            or any(not isinstance(n, int) or isinstance(n, bool) or n < 1 for n in positions)
        ):
            raise MutationRefused("--positions must be 1 to 8 positive whole numbers, e.g. --positions 2 or --positions 2,3.")
        positions = list(positions)
    elif positions:
        raise MutationRefused("--positions goes with --target experiment --decision set_counter_positions.")
    bulk = len(target_ids) > 1

    def change(bundle):
        latest = B._decisions_by_target(bundle.get("scientist_decisions") or ())
        planned: list[tuple[str, dict]] = []
        for tid in target_ids:
            kind, obj = resolve_target(bundle, tid)
            _check_decision(bundle, kind, obj, decision, value, bulk=bulk)
            if qc_status is not None and kind != "processing_result":
                raise MutationRefused("--qc-status applies to a processing result only.")
            if kind == "processing_result" and decision == "approve" and qc_status is None:
                # I4: the QC status is never guessed from the protocol's verdict.
                raise MutationRefused(
                    "Approving a processing result needs --qc-status (one of "
                    + ", ".join(qc_status_vocabulary()) + "): the QC status is a person's statement."
                )
            planned.append((kind, obj))
        decided_by = {
            "name": by.strip(),
            "basis": "self_reported_local_user",
            "identity": "local_unverified",
            "orcid_claimed": (
                {"value": orcid, "basis": "claimed_for_credit_not_authentication"} if orcid else None
            ),
        }
        decisions = bundle.setdefault("scientist_decisions", [])
        batch_id = f"batch-{len(decisions) + 1:04d}" if bulk else None
        recorded, unchanged = [], []
        for tid, (kind, obj) in zip(target_ids, planned):
            prior = latest.get((kind, tid))
            signature = (decision, json.dumps(value, sort_keys=True), decided_by["name"], orcid,
                         json.dumps(split_into or []), json.dumps(merge_with or []), qc_status, qc_note, element, edge,
                         json.dumps(positions or []))
            if prior is not None and (
                prior.get("decision"),
                json.dumps(prior.get("value"), sort_keys=True),
                (prior.get("decided_by") or {}).get("name"),
                ((prior.get("decided_by") or {}).get("orcid_claimed") or {}).get("value"),
                json.dumps(prior.get("split_into") or []),
                json.dumps(prior.get("merge_with") or []),
                prior.get("qc_status"),
                prior.get("qc_note"),
                prior.get("element"),
                prior.get("edge"),
                json.dumps(prior.get("positions") or []),
            ) == signature:
                unchanged.append(tid)
                continue
            entry = {
                "decision_id": f"d-{len(decisions) + 1:05d}",
                "target": {"kind": kind, "id": tid},
                "decision": decision,
                "value": value,
                "chosen_reading_index": None,
                "decided_by": decided_by,
                "decided_utc": now_utc(),
                "method": "scientist_answer",
                "note": note,
                "batch_id": batch_id,
            }
            if split_into:
                entry["split_into"] = [list(g) for g in split_into]
            if merge_with:
                entry["merge_with"] = list(merge_with)
            if decision == "approve_calibration":
                entry["element"], entry["edge"] = element, edge
            if decision == "set_counter_positions":
                entry["positions"] = positions
            if kind == "processing_result" and decision == "approve":
                # AN APPROVAL BINDS TO EXACTLY THIS RESULT'S FILES (and their hashes).
                entry["approved_files"] = [
                    {"role": f.get("role"), "relative_path": f.get("relative_path"), "sha256": f.get("sha256")}
                    for f in (obj.get("outputs") or {}).get("files") or ()
                ]
            if qc_status is not None:
                # THE PERSON STATES THE QC STATUS; what they were shown is kept beside it.
                qc = obj.get("qc") or {}
                entry["qc_status"] = qc_status
                entry["qc_note"] = qc_note
                entry["qc_evidence"] = {"verdict": qc.get("verdict"), "metrics": qc.get("metrics") or {}}
            decisions.append(entry)
            recorded.append(tid)
        return {"recorded": recorded, "unchanged": unchanged, "batch_id": batch_id}

    return mutate(bundle_dir, change)


# --- crosscheck plan / excerpt / reveal ---------------------------------------------------------


def _locators(candidate: Mapping) -> list[dict]:
    return [
        {"source_id": e["source_id"], "relative_path": e["relative_path"], "locator": e["locator"]}
        for e in candidate["evidence"]
        if e["method"] != "ai_interpretation"
    ][:B.MAX_EVIDENCE_PER_CANDIDATE]


def crosscheck_plan(bundle: Mapping) -> dict:
    """High-value targets to cross-check, with ids and source locators — NO values.
    Also the coverage so far: checked (has an AI reading), blind-checked, unchecked."""
    required = B.required_record_paths()
    interps = bundle.get("ai_interpretations") or ()
    checked: dict[tuple[str, str], list[dict]] = {}
    for i in interps:
        checked.setdefault((i["target"]["kind"], i["target"]["id"]), []).append(i)
    items: list[dict] = []

    def add(kind, tid, category, run_id, locators):
        key = (kind, tid)
        readings = checked.get(key, [])
        items.append(
            {
                "target": {"kind": kind, "id": tid},
                "category": category,
                "run_id": run_id,
                "locators": locators,
                "checked": bool(readings),
                "blind_checks": sum(1 for r in readings if r.get("blind")),
                "parser_value_exposed": bool(exposures_for(bundle, kind, tid)),
            }
        )

    sources = {s["source_id"]: s for s in bundle["sources"]}
    for run in bundle["runs"]:
        locs = [{"source_id": run["acquisition_source_id"], "relative_path": sources.get(run["acquisition_source_id"], {}).get("relative_path"), "locator": "the acquisition file"}]
        locs += [{"source_id": s["source_id"], "relative_path": s["relative_path"], "locator": f"scan {s['scan_index']}"} for s in run["scans"]]
        locs += [{"source_id": d["macro_source_id"], "relative_path": d["macro_path"], "locator": f"newfile block {d['block_index']}"} for d in run["declared_by"]]
        add("run", run["run_id"], "run_association", run["run_id"], locs)
        if run["signal_selection"]:
            add("run", run["run_id"], "herfd_signal_choice", run["run_id"],
                [{"source_id": s["source_id"], "relative_path": s["relative_path"], "locator": f"scan {s['scan_index']} channel columns"} for s in run["scans"]])
    for c in bundle["candidates"]:
        path = c["target_field_path"] or ""
        category = None
        for name, prefixes, keys in CROSSCHECK_CATEGORIES:
            if any(path == p or path.startswith(p) for p in prefixes) or c["statement_key"] in keys:
                category = name
                break
        if category is None and path and B._required_for(path, required):
            category = "required_by_record"
        if category:
            add("candidate", c["candidate_id"], category, c["run_id"], _locators(c))
    for m in bundle["missing_values"]:
        if B._required_for(m["target_field_path"], required):
            add("missing_value", m["value_id"], "required_by_record", m["run_id"], [])
    total = len(items)
    checked_n = sum(1 for i in items if i["checked"])
    blind_n = sum(1 for i in items if i["blind_checks"])
    return {
        "total": total,
        "coverage": {
            "checked": checked_n,
            "blind_checked": blind_n,
            "unchecked": total - checked_n,
            "statement": (
                "Spot checks only. A checked target has at least one AI reading recorded; "
                "nothing here claims the bundle is verified, and unchecked targets were not "
                "examined at all."
            ),
        },
        "items": items,
    }


def _source_root(bundle: Mapping, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    hint = bundle["source_root"].get("local_root_hint")
    if hint:
        return Path(hint)
    raise MutationRefused(
        "This bundle does not record where its source is (that is the default). Pass "
        "--source <the folder or ZIP you imported>."
    )


_LINE_RE = re.compile(r"\bline (\d+)\b")


def excerpt(bundle: Mapping, target_id: str, *, source: str | None) -> dict:
    """Raw source text at a target's locators — never a parser value. Bounded. The file
    is re-read through the same guarded walk, and refused if its bytes changed."""
    from .. import historical_import as hist
    from ..bl15 import archive

    kind, obj = resolve_target(bundle, target_id)
    if kind == "candidate":
        locs = _locators(obj)
    elif kind == "source":
        locs = [{"source_id": obj["source_id"], "relative_path": obj["relative_path"], "locator": "line 1"}]
    elif kind == "run":
        locs = [{"source_id": obj["acquisition_source_id"], "relative_path": None, "locator": "line 1"}]
    else:
        raise MutationRefused(f"A {kind} has no source locators to excerpt.")
    root = _source_root(bundle, source)
    inventory = hist._inventory_of(root, root_label=root.name)
    current = {e.archive_path: e for e in inventory.entries}
    sources = {s["source_id"]: s for s in bundle["sources"]}
    out = []
    for loc in locs[:MAX_EXCERPTS]:
        src = sources.get(loc["source_id"]) if loc["source_id"] else None
        if src is None:
            continue
        path = src["relative_path"]
        entry = current.get(path)
        if entry is None:
            out.append({"source_id": src["source_id"], "relative_path": path, "refused": "the file is no longer in the source"})
            continue
        if src["content_sha256"] and entry.content_sha256 != src["content_sha256"]:
            out.append({"source_id": src["source_id"], "relative_path": path, "refused": "the file's bytes changed since the import"})
            continue
        text, refusal = archive.read_source_text(inventory, path, source_root=root)
        if text is None:
            out.append({"source_id": src["source_id"], "relative_path": path, "refused": str(refusal)})
            continue
        lines = text.splitlines()
        match = _LINE_RE.search(loc["locator"] or "")
        if match:
            n = int(match.group(1))
            lo, hi = max(1, n - EXCERPT_CONTEXT_LINES), min(len(lines), n + EXCERPT_CONTEXT_LINES)
        else:
            lo, hi = 1, min(len(lines), 2 * EXCERPT_CONTEXT_LINES + 1)
        body = "\n".join(f"{i:>5}: {lines[i - 1]}" for i in range(lo, hi + 1))
        truncated = len(body) > MAX_EXCERPT_CHARS
        out.append(
            {
                "source_id": src["source_id"],
                "relative_path": path,
                "locator": loc["locator"],
                "lines": [lo, hi],
                "text": body[:MAX_EXCERPT_CHARS],
                "truncated": truncated,
            }
        )
    return {
        "target": {"kind": kind, "id": target_id},
        "excerpts": out,
        "omitted": max(0, len(locs) - MAX_EXCERPTS),
        "statement": "Raw source text only; no parser value is shown. Reading this does not record an exposure.",
    }


def _same(a: Any, b: Any) -> bool:
    def norm(v):
        return v.strip().casefold() if isinstance(v, str) else v
    return norm(a) == norm(b)


def reveal(bundle_dir: Path, target_id: str) -> dict:
    """The parser value plus a comparison with every AI reading. RECORDS AN EXPOSURE."""
    with locked(Path(bundle_dir)):
        bundle = load(bundle_dir)
        kind, obj = resolve_target(bundle, target_id)
        record_exposure(bundle, kind, target_id, "bundle reveal")
        save_bundle(bundle_dir, bundle)
    readings = [i for i in bundle.get("ai_interpretations") or () if i["target"] == {"kind": kind, "id": target_id}]
    if kind == "candidate":
        parser = {"value": obj["value"], "observed_literals": obj["observed_literals"], "value_state": obj["value_state"]}
        base = obj["value"]
    elif kind == "run":
        parser = {"signal_selection": obj["signal_selection"], "label": obj["label"]}
        base = (obj["signal_selection"] or {}).get("primary_channel")
    else:
        parser = {"value": None, "note": f"a {kind} has no parser value"}
        base = None
    return {
        "target": {"kind": kind, "id": target_id},
        "parser": parser,
        "ai_readings": [
            {
                "interpretation_id": r["interpretation_id"],
                "proposed_value": r["proposed_value"],
                "blind": r.get("blind", False),
                "agrees_with_parser": (_same(r["proposed_value"], base) if base is not None else None),
            }
            for r in readings
        ],
        "exposure_recorded": True,
    }


# --- LOCAL-P wiring: grouping and processing, persisted through save_bundle ----------------------


def group(bundle_dir: Path, *, regroup: bool = False) -> dict:
    """Propose record groups (``local_import.grouping``, via LOCAL-P's entry point) and
    store them in ``record_groups[]``. A group a scientist already decided is KEPT on
    ``--regroup``; only undecided proposals are replaced."""
    try:
        from .processing import cli_entry
    except ImportError as exc:  # pragma: no cover - the package ships with the checkout
        raise MutationRefused(f"grouping is not installed: {exc}", code=2) from exc

    def change(bundle):
        decided = {d["target"]["id"] for d in bundle.get("scientist_decisions") or () if d["target"]["kind"] == "record_group"}
        existing = list(bundle.get("record_groups") or ())
        if existing and not regroup:
            raise MutationRefused("This bundle already has record groups; pass --regroup to replace the undecided ones.")
        payload = cli_entry.build_groups_payload(bundle)
        keep = [g for g in existing if g["group_id"] in decided]
        kept_ids = {g["group_id"] for g in keep}
        fresh = [dict(g) for g in payload["record_groups"] if g["group_id"] not in kept_ids]
        for g in fresh:
            g["status"] = "proposed"  # only a decision moves it
            g.setdefault("condition_violations", [])  # carried; a proposed group must have none
        bundle["record_groups"] = keep + fresh
        bundle["grouping_questions"] = [
            dict(q) for q in (payload.get("experiment_questions") or payload.get("questions") or ())
            if isinstance(q, Mapping)
        ]
        ids = {g["group_id"] for g in bundle["record_groups"]}
        bundle["merge_candidates"] = [
            dict(mc) for mc in payload.get("merge_candidates") or () if set(mc.get("group_ids") or ()) <= ids
        ]
        return {
            "record_groups": len(bundle["record_groups"]),
            "kept_decided": len(keep),
            "proposed": len(fresh),
            "merge_candidates": len(bundle["merge_candidates"]),
            "rule_id": payload.get("rule_id"),
            "statement": "Proposed groups only. A scientist confirms, splits, merges or rejects each one.",
            "read_them_with": [
                "isaac bundle list <bundle_dir> groups",
                "isaac bundle show <bundle_dir> group <group_id>",
                "isaac bundle list <bundle_dir> merge-candidates",
            ],
        }

    result = mutate(bundle_dir, change)
    # record_groups.json is kept as a MIRROR of bundle.json's record_groups (so LOCAL-P's
    # processing reads exactly the persisted groups and never re-proposes its own).
    from .cli import _atomic_write, _json_bytes

    saved = load(bundle_dir)
    _atomic_write(
        Path(bundle_dir) / cli_entry.GROUPS_FILE,
        _json_bytes({
            "format": cli_entry.GROUPS_FORMAT,
            "format_version": cli_entry.GROUPS_FORMAT_VERSION,
            "notice": "A mirror of bundle.json's record_groups, rewritten by every `isaac bundle group`. bundle.json is the authority.",
            "bundle_id": saved.get("bundle_id"),
            "record_groups": saved.get("record_groups") or [],
            "merge_candidates": saved.get("merge_candidates") or [],
        }),
    )
    return result


def process(
    bundle_dir: Path,
    *,
    source: str | None = None,
    group_ids: Sequence[str] | None = None,
    athena: bool = True,
    params_file: str | None = None,
) -> dict:
    """Run the processing protocol (LOCAL-P's ``processing.cli_entry.run_process``) and
    store its ``processing_results[]``. A result a scientist already decided is KEPT;
    nothing here approves anything — every new result is undecided."""
    try:
        from .processing import cli_entry
    except ImportError as exc:
        raise MutationRefused(f"processing not installed: {exc}", code=2) from exc
    bundle_dir = Path(bundle_dir)
    current = load(bundle_dir)
    if not current.get("record_groups"):
        raise MutationRefused("No record groups yet: run `isaac bundle group` first.", code=2)
    payload = cli_entry.run_process(
        bundle_dir,
        source_root=source,
        group_ids=group_ids,
        athena=athena,
        params_file=params_file,
        bundle=current,
        calibration_approvals=calibration_approvals(current),
    )
    if payload.get("status") == "processing_unavailable":
        missing = ", ".join(payload.get("missing") or []) or "its dependencies"
        raise MutationRefused(f"processing not installed: missing {missing}.", code=2)
    produced = [dict(r) for r in payload.get("processing_results") or ()]

    def change(bundle):
        known = {g["group_id"] for g in bundle.get("record_groups") or ()}
        decided = {d["target"]["id"] for d in bundle.get("scientist_decisions") or () if d["target"]["kind"] == "processing_result"}
        keep = [r for r in bundle.get("processing_results") or () if B.processing_id(r) in decided]
        kept = {B.processing_id(r) for r in keep}
        fresh = []
        for r in produced:
            if r.get("group_id") not in known or B.processing_id(r) in kept:
                continue
            if r.get("state") not in B.PROCESSING_UNDECIDED_STATES:
                r["state"] = B.STATE_NEEDS_REVIEW
            fresh.append(r)
        bundle["processing_results"] = keep + fresh
        return {
            "processing_results": len(bundle["processing_results"]),
            "kept_decided": len(keep),
            "new": len(fresh),
            "summary": payload.get("summary"),
            "statement": "Draft, unreviewed processing. Nothing goes into a record until a scientist approves it.",
        }

    return mutate(bundle_dir, change)


def qc_status_vocabulary() -> list[str]:
    """``measurement.qc.status`` values from the PINNED upstream vocabulary when the
    validator is installed, else from the vendored schema's enum."""
    from . import portal as P

    where = P.locate()
    if where.get("available"):
        try:
            vocab = json.loads((Path(where["dir"]) / "data" / "vocabulary.json").read_text(encoding="utf-8"))
            values = vocab["Measurement"]["measurement.qc.status"]["values"]
            if isinstance(values, list) and values:
                return [str(v) for v in values]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    node = B._schema_node("measurement.qc.status") or {}
    return [str(v) for v in node.get("enum") or ()]


def calibration_approvals(bundle: Mapping) -> dict:
    """``{group_id: {element, edge, decided_by, decision_id}}`` from the LATEST
    ``approve_calibration`` decision per group — the only thing that lets processing apply
    a calibration shift. A decision always has a named decider (``--by`` is required)."""
    out: dict = {}
    for d in bundle.get("scientist_decisions") or ():
        if d.get("decision") == "approve_calibration" and d["target"]["kind"] == "record_group":
            out[d["target"]["id"]] = {
                "element": d["element"],
                "edge": d["edge"],
                "decided_by": (d.get("decided_by") or {}).get("name"),
                "decision_id": d["decision_id"],
            }
    return out


def counter_positions(bundle: Mapping) -> list[int] | None:
    """The scientist's LATEST ``set_counter_positions`` answer (every earlier one is kept in
    ``scientist_decisions``; the last supersedes), or ``None``. For the grouping step."""
    latest = None
    for d in bundle.get("scientist_decisions") or ():
        if (
            d.get("decision") == "set_counter_positions"
            and d["target"] == {"kind": "experiment", "id": "experiment"}
            and B.decider_name_problem((d.get("decided_by") or {}).get("name")) is None
        ):
            latest = list(d.get("positions") or [])
    return latest

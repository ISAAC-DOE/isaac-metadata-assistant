"""P30.1 — a thin, read-only cross-record runtime projection (safe facts only).

A DERIVED read model over the SAME ``workspace.list_experiments()`` snapshot P26
search uses — NO index, NO cache, NO database, NO service, NO persisted state.
The projection is recomputed per request, so it is current-by-construction and
survives reset / deletion / restart with zero extra machinery.

Governance (the whole risk of a derived read model): it emits ONLY a strict
allow-set of safe *confirmed* facts plus freshness metadata. It NEVER surfaces
draft field values, evidence bodies, unconfirmed proposals, inferred values as
facts, rejected values, chat / answer_log, sidecar content, secrets, or internal
filesystem paths. ``navigate_to`` is a CLIENT route (``/record/<id>``), never a
filesystem path. Per-field evidence *classifications* stay private — only the
5-class histogram counts leave this module.

Pure, non-mutating, Graphify-free. It reuses the existing read-only derivations
(``derive_workflow``, ``evidence_classify.classify_fields`` counts,
``dependencies.artifact_state``) and the ``workspace.Experiment`` accessors; it
imports and touches NOTHING in the frozen truth path.
"""

from __future__ import annotations

from typing import Iterable

from . import evidence_classify
from .dependencies import artifact_state
from .workflow import derive_workflow

#: The six evidence-support classes, in display precedence. The single source
#: for the ``evidence_counts`` histogram key set (counts only — never per-field).
#:
#: ``unreadable`` is its own bucket, not folded into ``unknown``: ``unknown``
#: asserts that nothing defensible is recorded, and an entry whose stored evidence
#: could not be read supports no such assertion. Folding them would have made the
#: workspace histogram state a finding about the science that nobody measured.
EVIDENCE_CLASSES: tuple[str, ...] = (
    "supported",
    "inferred_candidate",
    "insufficient_evidence",
    "conflicting_evidence",
    "unknown",
    "unreadable",
)

#: The ONLY keys a projected record may carry — a strict, safe allow-set.
ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "experiment_id",
        "title",
        "status",
        "pending_count",
        "exported",
        "record_id",
        "workflow",
        "evidence_counts",
        "artifact_state",
        "record_rev",
        "updated_utc",
        "navigate_to",
    }
)

#: The typed filter values the consumer uses (no speculative extras).
_WORKFLOW_STATES: frozenset[str] = frozenset({"blocked", "reopened", "current"})
_ARTIFACT_STATES: frozenset[str] = frozenset({"none", "current", "stale"})


def _evidence_counts(draft: dict) -> dict[str, int]:
    """The 5-class histogram of ``classify_fields`` — counts only.

    Per-field classifications, values, evidence bodies, and source locators are
    deliberately discarded; only the integer tallies survive.
    """
    counts = {c: 0 for c in EVIDENCE_CLASSES}
    for field_result in evidence_classify.classify_fields(draft):
        cls = field_result["classification"]
        if cls in counts:  # defensive; classify_fields only emits known classes
            counts[cls] += 1
    return counts


def _project_one(exp) -> dict:
    """Project a single experiment to the safe allow-set.

    Each expensive derivation (``status``, ``draft_ok``, ``export_ready``,
    ``classify_fields``) is computed exactly ONCE — no value is recomputed within
    this record's projection.
    """
    pending = exp.pending_count()
    # REVIEW ITEM F2 — `all_units_exported()`, not `exported()`. The C5 fix named
    # "all three `derive_workflow` sites" and there are FIVE; this projection was one
    # of the two it missed, so `GET /api/runtime/records` disagreed with the detail
    # endpoint about the same experiment in the same process:
    #
    #     runtime_records._project_one(exp)["exported"] -> False
    #     GET /api/experiments/{id} ["exported"]        -> True
    #
    # For an experiment with no runs the two are the same function of the same field.
    # `record_id` below stays `exp.record_id` — null for a fan-out — for exactly the
    # reason `routes._summary` gives: `exported` and `record_id` answer two different
    # questions, and a fan-out genuinely has no single record id.
    exported = exp.all_units_exported()
    status = exp.status()
    draft_ok = exp.draft_ok()
    ready = exp.export_ready()

    workflow = derive_workflow(
        pending_count=pending,
        draft_ok=draft_ok,
        ready=ready,
        exported=exported,
        rev=exp.rev,
    )
    steps = workflow["ordered_steps"]

    return {
        "experiment_id": exp.id,
        "title": exp.title,
        "status": status,
        "pending_count": pending,
        "exported": exported,
        "record_id": exp.record_id,
        # ONLY current_step + two booleans — no labels, reasons, or values.
        "workflow": {
            "current_step": workflow["current_step"],
            "blocked": any(s["blocked"] for s in steps),
            "reopened": any(s["reopened"] for s in steps),
        },
        "evidence_counts": _evidence_counts(exp.draft),
        # The freshness string only (none|current|stale) — never the reason body.
        "artifact_state": artifact_state(exp)["state"],
        # Freshness metadata for stale-view detection (same signal as the ETag).
        "record_rev": exp.rev,
        "updated_utc": exp.updated_utc,
        # A CLIENT route, never a filesystem path.
        "navigate_to": f"/record/{exp.id}",
    }


def filter_records(
    records: list[dict],
    *,
    status: str | None = None,
    workflow_state: str | None = None,
    artifact: str | None = None,
    has_conflict: bool = False,
) -> list[dict]:
    """Apply the consumer's typed filters to already-projected records.

    All filters are conjunctive (AND). An unrecognized ``workflow_state`` /
    ``artifact`` value matches NOTHING (returns an empty set) rather than being
    silently ignored, so a bad filter never leaks the full set.
    """
    out = records
    if status is not None:
        out = [r for r in out if r["status"] == status]
    if workflow_state is not None:
        if workflow_state == "blocked":
            out = [r for r in out if r["workflow"]["blocked"]]
        elif workflow_state == "reopened":
            out = [r for r in out if r["workflow"]["reopened"]]
        elif workflow_state == "current":
            out = [r for r in out if r["workflow"]["current_step"] is not None]
        else:
            out = []  # unrecognized state matches nothing
    if artifact is not None:
        out = [r for r in out if r["artifact_state"] == artifact]
    if has_conflict:
        out = [r for r in out if r["evidence_counts"]["conflicting_evidence"] >= 1]
    return out


def project_records(experiments: Iterable, *, filters: dict | None = None) -> list[dict]:
    """Project a scan of experiments to the safe read model, filtered + ordered.

    ``experiments`` is the SAME snapshot ``workspace.list_experiments()`` returns.
    Ordering is deterministic and stable: by ``created_utc`` then ``id``. Pure and
    non-mutating — a fresh projection each call, no cache.
    """
    ordered = sorted(experiments, key=lambda e: (e.created_utc, e.id))
    records = [_project_one(e) for e in ordered]
    if filters:
        records = filter_records(records, **filters)
    return records

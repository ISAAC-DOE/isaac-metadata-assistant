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

    ~~That sentence was TRUE OF THE FOUR NAMED CALLS AND FALSE OF WHAT THEY COST~~,
    and it is corrected in place rather than rewritten because it is the reason nobody
    looked. Each of ``status``, ``draft_ok`` and ``export_ready`` is indeed *called*
    once — and each of them independently COMPOSED the export-unit list and re-resolved
    every run's draft underneath. Measured on a fully answered three-run fan-out, with
    ``export_units`` and ``resolved_run_draft`` counted directly::

        before   export_units 4   resolved_run_draft 12   export_draft 6   (2x runs)
        after    export_units 1   resolved_run_draft  3   export_draft 3   (1x runs)

    TWO THINGS ABOUT ARRIVING AT THOSE NUMBERS ARE WORTH KEEPING, because both are the
    shape of error this file is about.

    The first attempt reached ``export_units`` 4 -> **2**, not 4 -> 1: threading the
    three derivations left ``artifact_state`` composing a second list, and only a stack
    trace found it. *"I threaded the seams"* is exactly the kind of claim that reads as
    complete and measures as half.

    And ``export_draft`` was **missing from the first version of this table**, measured
    as 0 by a probe that patched ``isaac_records.export.export_draft`` while
    ``workspace`` had imported the name directly — so the patch was on an object nobody
    called. It is the LARGER of the two terms (the dry run, 2x the run count, which PR
    #177 measured at roughly half a detail request), and a counter aimed at the wrong
    object reported its absence as a zero rather than as a failure to observe.

    ``routes._detail`` closed exactly this in PR #176 (``_shared_units``) and PR #177
    (``_shared_dry_run``); this projection is the site those slices did not reach, and
    PR #179's residue list named it. The seams are the same two, used the same way:
    THREADED, NOT MEMOISED — nothing is stored on the ``Experiment``, because this
    module is called in a loop over records that a caller may have mutated, and a cache
    on the instance can be served stale. ``None`` still means "derive your own".

    ``dry_run_verdict`` answers ``None`` while ``pending_count() > 0``, which is exactly
    the union of ``status``'s and ``export_ready``'s short-circuits — so on a record
    that still owes questions the dry run is entered ZERO times here, as it was before,
    and this does not make the common case slower to speed up the rare one.
    """
    pending = exp.pending_count()
    # ONE COMPOSITION AND ONE DRY RUN FOR THE WHOLE PROJECTION — see the docstring for
    # the measurement, and `routes._shared_units` / `routes._shared_dry_run` for why
    # these are arguments rather than caches.
    units = exp.export_units()
    dry_run_ok = exp.dry_run_verdict(units=units)
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
    # `all_units_exported` is deliberately NOT given `units`: it reads `run.record_id`
    # directly and never builds a unit list, which its own docstring says and which the
    # before-measurement confirms — it is not one of the four compositions.
    exported = exp.all_units_exported()
    status = exp.status(units=units, dry_run_ok=dry_run_ok)
    draft_ok = exp.draft_ok(units=units)
    # `units=` HERE IS CURRENTLY UNREACHABLE, and it is kept deliberately rather than
    # trimmed. `export_ready` reads `units` only on the branch where `dry_run_ok is
    # None`, and that branch is guarded by `pending_count() > 0`, which returns `False`
    # before it looks — so with the verdict threaded above, no call from this site can
    # reach it. A mutation removing the argument therefore PASSES the whole suite, and
    # that is recorded here instead of being reported as a clean sweep: an inert
    # mutation surviving is information about the code, not a hole in the tests.
    # It stays because `routes._workflow_for` passes both for the same pair, and an
    # argument that is correct-but-unread costs nothing while a missing one becomes a
    # silent 2x the moment the gate changes.
    ready = exp.export_ready(units=units, dry_run_ok=dry_run_ok)

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
        # THE SECOND COMPOSITION, AND IT WAS THE ONE THE FIRST FIX MISSED. Threading
        # `units` into the three derivations above took the count 4 -> 2, not 4 -> 1,
        # and a trace named this call as the remainder (`_fan_out_artifact_state` <-
        # `artifact_state` <- `_project_one`). The parameter already existed; this site
        # simply never passed it. Recorded because "I threaded the seams" is exactly
        # the kind of claim that reads as complete and measures as half.
        "artifact_state": artifact_state(exp, units=units)["state"],
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

"""P28.1 — the fixed canonical workflow, DERIVED from current record truth.

This module is pure and side-effect free. It is NOT part of the deterministic
truth core (it authorizes nothing, validates nothing, exports nothing) and it is
Graphify-free. The workflow is ONE permanent ordered sequence whose per-step
state is computed on read from the current signals only — never persisted, never
reordered, never recomputed on the client.

Canonical order (fixed, app-native ids):
    load_record → complete_metadata → review_evidence
                → review_export_readiness → export
"""

from __future__ import annotations

#: The single canonical order. Never reordered, never persisted.
CANONICAL_ORDER: tuple[str, ...] = (
    "load_record",
    "complete_metadata",
    "review_evidence",
    "review_export_readiness",
    "export",
)

#: Title Case, canonical labels keyed by step id.
CANONICAL_LABELS: dict[str, str] = {
    "load_record": "Load Record",
    "complete_metadata": "Complete Metadata",
    "review_evidence": "Review Evidence",
    "review_export_readiness": "Review Export Readiness",
    "export": "Export",
}

_REOPENED_REASON = (
    "An upstream change reopened this step; it no longer reflects the current record."
)


def derive_workflow(
    *,
    pending_count: int,
    draft_ok: bool,
    ready: bool,
    exported: bool,
    rev: int,
) -> dict:
    """Derive the fixed canonical workflow from current record signals.

    A step is *satisfied* when its criterion holds:

        load_record             = True (a loaded record always exists)
        complete_metadata       = pending_count == 0
        review_evidence         = pending_count == 0 and draft_ok
        review_export_readiness = ready
        export                  = exported

    ``current_step`` is the first unsatisfied step (``None`` if all satisfied).
    An unsatisfied step is ``reopened`` when some LATER step is satisfied (the
    record progressed past it, then upstream data regressed — derivable without
    persisting any history), ``current`` when it is the first unsatisfied step,
    and ``blocked`` otherwise (an earlier prerequisite is unmet).
    """
    satisfied = {
        "load_record": True,
        "complete_metadata": pending_count == 0,
        "review_evidence": pending_count == 0 and draft_ok,
        "review_export_readiness": ready,
        "export": exported,
    }

    # First unsatisfied step in canonical order (None if all satisfied).
    current_step: str | None = next(
        (sid for sid in CANONICAL_ORDER if not satisfied[sid]), None
    )
    current_label = CANONICAL_LABELS[current_step] if current_step is not None else None

    ordered_steps: list[dict] = []
    for index, sid in enumerate(CANONICAL_ORDER):
        if satisfied[sid]:
            ordered_steps.append(
                {
                    "id": sid,
                    "label": CANONICAL_LABELS[sid],
                    "state": "completed",
                    "current": False,
                    "reopened": False,
                    "blocked": False,
                    "reason": None,
                }
            )
            continue

        is_current = sid == current_step
        # A later step being satisfied means the record once progressed past
        # this step — it was completed and has now regressed (reopened).
        is_reopened = any(satisfied[later] for later in CANONICAL_ORDER[index + 1 :])
        is_blocked = not is_current and not is_reopened

        if is_current:
            state = "current"
            reason = None
        elif is_reopened:
            state = "reopened"
            reason = _REOPENED_REASON
        else:
            state = "blocked"
            reason = f"Complete '{current_label}' first."

        ordered_steps.append(
            {
                "id": sid,
                "label": CANONICAL_LABELS[sid],
                "state": state,
                "current": is_current,
                "reopened": is_reopened,
                "blocked": is_blocked,
                "reason": reason,
            }
        )

    return {
        "ordered_steps": ordered_steps,
        "current_step": current_step,
        "record_rev": rev,
    }

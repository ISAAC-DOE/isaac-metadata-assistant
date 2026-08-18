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


# ==============================================================================
# THE SUBMISSION LIFECYCLE — a SECOND derivation, deliberately beside the first
# ==============================================================================
#
# WHY IT IS NOT A SIXTH STEP OF `CANONICAL_ORDER`. The five steps above are one
# ordered sequence through a single record's preparation, and every one of them is
# a function of the record's own current signals. Submission is not: it is a
# DECLARATION BY A PERSON, it lives in a different store, and — the part that
# actually forces the split — it can be UNKNOWABLE. A deployment whose migrations
# have not been applied cannot say whether a record was submitted, and there is no
# honest value for a step state in that case. `blocked` would be false, `current`
# would be false, and `completed` would be a lie. So the lifecycle is its own
# object with its own explicit "known" bit, and `derive_workflow` above is
# UNCHANGED — same signature, same five steps, same states, same callers.
#
# THE ONE RULE THIS FUNCTION EXISTS TO ENFORCE: **`submitted` IS NEVER DERIVED
# FROM `exported`.** Export is a mechanical transform any caller can perform at any
# time; submission is a person saying "this is finished, and I am the one saying
# so". Treating an exported record as submitted would attribute a declaration
# nobody made. The enforcement here is structural rather than a comment: this
# function HAS NO `exported` PARAMETER, so no future edit inside it can reach for
# one, and `test_revision_history` asserts the signature.

#: The four lifecycle states, in the order a record passes through them.
LIFECYCLE_ORDER: tuple[str, ...] = (
    "draft",
    "needs_review",
    "ready_to_submit",
    "submitted",
)

#: Title Case, canonical labels keyed by lifecycle state.
LIFECYCLE_LABELS: dict[str, str] = {
    "draft": "Draft",
    "needs_review": "Needs Review",
    "ready_to_submit": "Ready to Submit",
    "submitted": "Submitted",
}


def derive_lifecycle(
    *,
    pending_count: int,
    failing_unit_count: int,
    submitted_known: bool,
    submitted_for_current_content: bool | None,
    submission_unknown_reason: str | None = None,
) -> dict:
    """Derive the submission lifecycle state. PURE — no I/O, no environment.

    THE FOUR STATES, AND WHAT EACH ONE IS DERIVED FROM:

    ``submitted``
        A durable submitted revision exists **for the content signature of the record
        as it is now**. Not "has ever been submitted": a record submitted and then
        edited is no longer submitted *as it stands*, and saying otherwise would tell
        a scientist their current draft is on record when it is not. Requires
        ``submitted_known`` — see below.

    ``ready_to_submit``
        Every scientific hard blocker is resolved: no unanswered question
        (``pending_count == 0``) and no export unit whose dry run refuses
        (``failing_unit_count == 0``). Both numbers come from
        ``submissions.blocker_report``, which is the ONE definition of what blocks a
        submission; this function re-derives nothing and adds no fifth reason.

    ``needs_review``
        Every question has been answered and the record still does not pass
        (``pending_count == 0`` and ``failing_unit_count > 0``). This is the state
        where there is nothing left to *fill in* and something left to *look at*.

    ``draft``
        Anything else — which today means unanswered questions remain.

    **WHAT `needs_review` DELIBERATELY IS NOT.** It is not "this record has
    conflicting evidence". ``submissions.conflict_summary`` records conflicting
    evidence and is documented as disclosed-never-gated. Conflicts are reported
    beside the lifecycle, not inside it.

    **THE REASON FOR THAT CHANGED, AND THE CONCLUSION DID NOT.** This paragraph used
    to justify non-gating by saying a conflict is something **no surface in this
    build can clear** — so labelling the record "Needs Review" would put it in a
    state it could not leave. That was true when written and is no longer: the
    conflict-resolution operations (``GET``/``POST .../conflicts``) let a scientist
    record which competing answer they stand behind, so the trap argument no longer
    applies.

    The conclusion stands on a different and better footing: **gating is a product
    decision no committed sentence in this repository authorises**, and
    ``conflict_summary`` says so in its own ``gating`` field rather than leaving it
    to be inferred. Note also that resolution does not make a conflict disappear —
    a ``deferred`` decision is a recorded outcome that deliberately does NOT clear
    it, and a resolution whose competing set has since moved reads ``stale``, which
    counts as unresolved. So even with the surface in place, "has a conflict" would
    be a poor lifecycle input.

    Recorded rather than quietly rewritten, because the invalidating change was
    made in this repository and a reader who finds the old argument elsewhere
    should be able to see why it was retired.

    **INFRASTRUCTURE NEVER DOWNGRADES SCIENTIFIC READINESS.** Whether this deployment
    could actually record a submission — whether it has a database, whether it can
    establish an attributable actor — is not an input to this function and must not
    become one. A record that is scientifically ready reads ``ready_to_submit`` on a
    deployment that can submit nothing at all; the reason it cannot is a separate,
    separately-named fact that the caller attaches
    (``routes._submission_deployment_block``). Merging the two would tell a scientist
    their science is unfinished because an operator has not applied a migration.

    ``submitted_known`` IS THE OTHER HALF OF THE SAME PRINCIPLE. When the history
    cannot be read, ``submitted_for_current_content`` is ``None``, the state falls
    back to the scientific derivation, and ``submission.known`` is ``False`` with a
    reason. **It never falls back to "not submitted"**, because "we could not look"
    and "we looked and found nothing" are different, and only one of them is
    something this application observed.
    """
    blocked = pending_count > 0 or failing_unit_count > 0
    reasons: list[dict] = []

    if submitted_known and submitted_for_current_content:
        state = "submitted"
        reasons.append(
            {
                "code": "submitted_for_current_content",
                "message": (
                    "A submission is on record for exactly this content."
                ),
            }
        )
    elif not blocked:
        state = "ready_to_submit"
        reasons.append(
            {
                "code": "no_scientific_blockers",
                "message": (
                    "Every question is answered and every unit passes the export "
                    "gate."
                ),
            }
        )
    elif pending_count == 0:
        state = "needs_review"
        reasons.append(
            {
                "code": "units_fail_the_export_gate",
                "message": (
                    f"Every question is answered and {failing_unit_count} unit"
                    f"{'' if failing_unit_count == 1 else 's'} still do not pass "
                    "the export gate."
                ),
            }
        )
    else:
        state = "draft"
        reasons.append(
            {
                "code": "questions_unanswered",
                "message": (
                    f"{pending_count} question{'' if pending_count == 1 else 's'} "
                    "the system refused to guess are still unanswered."
                ),
            }
        )

    if not submitted_known:
        # DISCLOSED ON EVERY STATE, not only on the ones a reader might doubt. A
        # record reading `ready_to_submit` on a deployment that cannot see its own
        # history might already be submitted; saying so is the whole point.
        reasons.append(
            {
                "code": "submission_state_unknown",
                "message": (
                    "This deployment could not read the submission history, so "
                    "whether this content has already been submitted is unknown "
                    "rather than no."
                ),
            }
        )

    return {
        "state": state,
        "label": LIFECYCLE_LABELS[state],
        "reasons": reasons,
        "scientific_readiness": {
            "blocked": blocked,
            "pending_count": pending_count,
            "failing_unit_count": failing_unit_count,
        },
        "submission": {
            "known": submitted_known,
            "submitted_for_current_content": (
                bool(submitted_for_current_content) if submitted_known else None
            ),
            "unknown_reason": None if submitted_known else submission_unknown_reason,
        },
    }

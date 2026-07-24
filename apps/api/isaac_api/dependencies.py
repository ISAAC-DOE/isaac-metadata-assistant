"""P28.2 — dependency-aware downstream invalidation + exported-artifact freshness.

Pure, read-only, Graphify-free. This module computes two DERIVED signals — never
persisted, never a second workflow store:

  * ``artifact_state`` — is the exported official record still a faithful
    projection of the CURRENT draft? An exported artifact is *stale* iff
    ``transform(current_draft)`` differs from the on-disk exported record
    (normalising the export timestamp). ``title``/``source`` are NOT part of the
    official record, so a presentation-only change never stales; a scientific
    field change does. This is the truthful freshness signal.
  * ``build_invalidation`` — the reopen DELTA a mutation caused, reported at the
    post-mutation revision. A byte-stable no-op invalidates nothing.

The truth core is imported READ-ONLY (``transform``), exactly as
``workspace.status()`` already calls ``export_draft`` — no writes here.
"""

from __future__ import annotations

import json

from isaac_records.export import transform

from .workflow import CANONICAL_LABELS, derive_workflow

_STALE_REASON = (
    "The record changed after export; the exported artifact no longer reflects "
    "the current record. Records are immutable — regenerate the record (or reset "
    "the demo) to refresh it."
)
_MISSING_REASON = "The exported artifact is missing or unreadable."


def _canonical(obj: dict) -> str:
    """Deterministic canonical JSON for content equality (stable key order)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def artifact_state(exp) -> dict:
    """Derived freshness of an experiment's exported official record.

    Returns ``{"state": "none"|"current"|"stale", "reason": str|None}``:

      * not exported                 -> ``none``
      * exported and content matches  -> ``current``
      * exported but content differs  -> ``stale`` (record changed after export)
      * exported but artifact missing/unreadable/not JSON -> ``stale`` (defensive)

    Never throws — a detail GET must not 500 on a corrupt/absent artifact.
    """
    if not exp.exported():
        return {"state": "none", "reason": None}

    record_path = exp.record_path()
    try:
        ondisk = json.loads(record_path.read_text(encoding="utf-8"))
        now0 = ondisk["timestamps"]["created_utc"]
    except Exception:
        # Missing/unreadable/not-JSON, or no created_utc — treat as stale, never throw.
        return {"state": "stale", "reason": _MISSING_REASON}

    try:
        current = transform(exp.draft, record_id=exp.id, now=now0)
    except Exception:  # pragma: no cover - defensive; transform is read-only + total
        return {"state": "stale", "reason": _MISSING_REASON}

    if _canonical(current) == _canonical(ondisk):
        return {"state": "current", "reason": None}
    return {"state": "stale", "reason": _STALE_REASON}


def reopened_steps(pre_steps: list[dict], post_steps: list[dict]) -> list[str]:
    """Step ids that were ``completed`` before the mutation but are NOT after.

    Both arguments are ``ordered_steps`` lists (see ``derive_workflow``). A step
    reopens when an upstream change regressed it past its satisfied criterion.
    """
    post_completed = {
        s["id"] for s in post_steps if s.get("state") == "completed"
    }
    return [
        s["id"]
        for s in pre_steps
        if s.get("state") == "completed" and s["id"] not in post_completed
    ]


def _post_workflow(post_exp) -> dict:
    """Derive the post-mutation workflow from the SAME signals ``_detail`` uses."""
    return derive_workflow(
        pending_count=post_exp.pending_count(),
        draft_ok=post_exp.draft_ok(),
        ready=post_exp.export_ready(),
        exported=post_exp.exported(),
        rev=post_exp.rev,
    )


def _labels(step_ids: list[str]) -> str:
    return ", ".join(CANONICAL_LABELS.get(sid, sid) for sid in step_ids)


def build_invalidation(
    *,
    changed: bool,
    changed_fields: list[str],
    pre_steps: list[dict],
    post_exp,
) -> dict:
    """The downstream-invalidation summary for a mutation, at the post-mutation rev.

    Returns ``{changed, rev, changed_fields, reopened_steps, artifact, reason}``.
    Deterministic and honest: a no-op reports ``changed=False`` with empty
    ``changed_fields``/``reopened_steps``; a real change reports which downstream
    steps (if any) reopened and whether the exported artifact is now stale.
    """
    post_workflow = _post_workflow(post_exp)
    reopened = reopened_steps(pre_steps, post_workflow["ordered_steps"])
    artifact = artifact_state(post_exp)

    if not changed:
        reason = "No change — the submitted value was identical; nothing was invalidated."
    elif reopened:
        reason = f"Updated {len(changed_fields)} field(s); reopened: {_labels(reopened)}."
    else:
        reason = f"Updated {len(changed_fields)} field(s); no downstream steps reopened."

    return {
        "changed": changed,
        "rev": post_exp.rev,
        "changed_fields": list(changed_fields),
        "reopened_steps": reopened,
        "artifact": artifact,
        "reason": reason,
    }

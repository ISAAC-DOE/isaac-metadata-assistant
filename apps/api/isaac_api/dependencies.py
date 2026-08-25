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
from .record_attribution import without_server_stamp
from .workspace import without_sibling_links

_STALE_REASON = (
    "The record changed after export; the exported artifact no longer reflects "
    "the current record. Records are immutable — regenerate the record (or reset "
    "the workspace) to refresh it."
)
#: PUBLIC (P4): the single definition of the missing/unreadable-artifact reason.
#: ``routes.get_artifacts`` reports the same absence with the same vocabulary, so
#: this string must have exactly ONE definition — a second copy in the route would
#: be a copy unit free to drift out of step with the state it describes.
MISSING_REASON = "The exported artifact is missing or unreadable."


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

    **FAN-OUT (review item C5).** An experiment with runs exports one record per run
    and ``Experiment.record_id`` stays ``None``, so the ``exp.exported()`` test above
    reported ``none`` — "nothing was exported" — for an experiment whose N records
    were all on disk and current. The same three labels are kept, because they mean
    the same things about a SET of artifacts as about one, and because inventing a
    fourth would change a shape every existing reader understands:

      * no run exported yet                                   -> ``none``
      * every run exported and every record matches           -> ``current``
      * anything else (a run still unexported, a record that
        no longer matches, a record that cannot be read)      -> ``stale``

    The middle case is the one worth stating: a PARTIALLY exported fan-out is
    ``stale``, not ``current`` and not ``none``, because the artifact set on disk is
    not a faithful projection of the current record. That warns rather than
    reassures, which is the right direction for a signal about whether exported
    output can be trusted.
    """
    if getattr(exp, "runs", None):
        return _fan_out_artifact_state(exp)

    if not exp.exported():
        return {"state": "none", "reason": None}

    record_path = exp.record_path()
    try:
        ondisk = json.loads(record_path.read_text(encoding="utf-8"))
        now0 = ondisk["timestamps"]["created_utc"]
    except Exception:
        # Missing/unreadable/not-JSON, or no created_utc — treat as stale, never throw.
        return {"state": "stale", "reason": MISSING_REASON}

    try:
        current = transform(exp.draft, record_id=exp.id, now=now0)
    except Exception:  # pragma: no cover - defensive; transform is read-only + total
        return {"state": "stale", "reason": MISSING_REASON}

    # `record_attribution.without_server_stamp` on BOTH sides, for the same reason
    # `without_sibling_links` is applied on both sides in the fan-out branch below:
    # `attribution.uploaded_by` is SERVER-stamped at write time and `transform`
    # cannot emit it (that is the truth core's invariant), so without this every
    # stamped artifact would report `stale` on every read, forever, and the only
    # remedy the reason offers is a destructive workspace reset. What is deliberately
    # lost is that a change to the stamp ALONE does not stale an artifact — correct,
    # because the stamp is not draft content and "the record changed after export" is
    # not what a differing stamp means.
    if _canonical(without_server_stamp(current)) == _canonical(
        without_server_stamp(ondisk)
    ):
        return {"state": "current", "reason": None}
    return {"state": "stale", "reason": _STALE_REASON}


#: A fan-out whose runs are not all exported yet. Deliberately NOT the "record
#: changed after export" reason: nothing changed, part of the set was never written.
_INCOMPLETE_REASON = (
    "Some of this record's runs have not been exported yet, so the exported "
    "artifacts do not cover the whole record."
)


def _fan_out_artifact_state(exp) -> dict:
    """:func:`artifact_state` for an experiment with runs. Same labels, N artifacts.

    Compares each run's WRITTEN record against what exporting that run now would
    produce, using ``export_units()`` so the comparison sees exactly the composed
    draft the export path would use — including the shared grouping tag and any
    sibling links, which are properties of the SET and are invisible to a per-run
    composition.

    **THE GROUPING-ADDED SIBLING LINKS ARE EXCLUDED FROM THE COMPARISON (review item
    F4), and that is a correction of this function rather than a concession.** The
    drafts come from ``export_units()``, which applies sibling grouping to every unit
    including materialised ones — so exporting a second run adds the REVERSE link into
    an already-written record's composed draft, a link that record will deliberately
    never gain because records are immutable. Every materialised sibling therefore
    reported ``stale`` with the reason "The record changed after export … regenerate
    the record (or reset the workspace) to refresh it", while nothing had changed,
    re-export answered 409, and the only offered remedy was a destructive reset.

    ``workspace.without_sibling_links`` is applied to BOTH sides, so every other link
    still compares faithfully; see that function for what this can and cannot detect.
    """
    try:
        units = exp.export_units()
    except Exception:  # pragma: no cover - defensive; composition is read-only
        return {"state": "stale", "reason": MISSING_REASON}

    if not any(unit.current_record_id() is not None for unit in units):
        return {"state": "none", "reason": None}
    if not all(unit.current_record_id() is not None for unit in units):
        return {"state": "stale", "reason": _INCOMPLETE_REASON}

    for unit in units:
        record_path = unit.record_path()
        if record_path is None:
            return {"state": "stale", "reason": MISSING_REASON}
        try:
            ondisk = json.loads(record_path.read_text(encoding="utf-8"))
            now0 = ondisk["timestamps"]["created_utc"]
            current = transform(unit.draft, record_id=unit.target_id, now=now0)
        except Exception:
            return {"state": "stale", "reason": MISSING_REASON}
        current = without_server_stamp(without_sibling_links(current))
        ondisk = without_server_stamp(without_sibling_links(ondisk))
        if _canonical(current) != _canonical(ondisk):
            return {"state": "stale", "reason": _STALE_REASON}
    return {"state": "current", "reason": None}


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
    """Derive the post-mutation workflow from the SAME signals ``_detail`` uses.

    ``exported`` is ``all_units_exported()`` (review item C5). It used to be
    ``exported()`` while ``routes._workflow_for`` — which supplies the ``pre_steps``
    this is compared against — used ``all_units_exported()``, so on a fully-exported
    fan-out every mutation reported ``reopened_steps: ['export']`` and the sentence
    *"Updated 1 field(s); reopened: Export."*. The export step had not reopened. A
    false ``reopened_steps`` is a claim about work the scientist did not have undone.

    For an experiment with no runs the two are the same function of the same field.
    """
    return derive_workflow(
        pending_count=post_exp.pending_count(),
        draft_ok=post_exp.draft_ok(),
        ready=post_exp.export_ready(),
        exported=post_exp.all_units_exported(),
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

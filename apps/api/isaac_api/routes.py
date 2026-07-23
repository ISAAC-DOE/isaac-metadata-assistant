"""HTTP endpoints for the local UI prototype (all JSON, prefixed ``/api``).

Every verdict is produced by an ``isaac_records`` core function — this module only
routes, serializes (via ``serialize``), and enforces the synthetic-only governance
boundary. It adds no validation logic and never mutates the truth path.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Body, Header, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from isaac_records.audit import audit_records, render_audit
from isaac_records.complete import apply_answers, apply_corrections
from isaac_records.draft_validator import validate_draft
from isaac_records.export import export_draft
from isaac_records.extract.draft_builder import build_draft
from isaac_records.official import EXPECTED_VERSION, validate_official
from isaac_records.portal_warnings import portal_warnings

from . import __version__
from . import dependencies
from . import evidence_classify
from . import memory
from . import runtime_mode
from . import runtime_records
from . import search
from . import serialize
from . import sources
from . import version_contract as vc
from . import workspace as ws
from .workflow import derive_workflow
from .workspace import REPO_ROOT, Experiment, atomic_write_text

router = APIRouter(prefix="/api")

SCHEMA_LABEL = f"ISAAC v{EXPECTED_VERSION}"

_UPLOAD_BLOCKED = {
    "blocked": True,
    "reason": (
        "Real or private data upload is approval-gated and not enabled in this "
        "synthetic prototype."
    ),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _not_found(experiment_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "experiment_not_found", "id": experiment_id},
    )


# --- If-Match precondition (P27.5-strict optimistic-concurrency contract) -----
#
# RFC 9110 strong comparison for unsafe methods: only strong quoted validators are
# accepted; weak (``W/"..."``) and malformed values are rejected 400. A mismatch is
# 412 stale_write (with the current ETag echoed so the client refreshes in one
# hop). A MISSING If-Match is now rejected 428 precondition_required — the
# one-release compatibility grace is retired (``vc.precondition_required()`` is
# True). No filesystem path, secret, or raw record content ever appears in a token
# or error body.

#: A strong ETag validator: a double-quoted opaque token, no ``W/`` prefix.
_STRONG_TAG_RE = re.compile(r'^"[^"\\]+"$')


def _expected_rev_from_token(token: str | None) -> int | None:
    """The integer after the LAST ``.`` of a client token, else ``None``."""
    if not token or "." not in token:
        return None
    try:
        return int(token.rsplit(".", 1)[-1])
    except (TypeError, ValueError):
        return None


def _precondition_required(exp) -> JSONResponse:
    return JSONResponse(
        status_code=428,
        content={"error": "precondition_required", "experiment_id": exp.id},
    )


def _malformed_if_match(exp) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": "malformed_if_match",
            "experiment_id": exp.id,
            "message": "If-Match must be one or more strong quoted validators.",
        },
    )


def _stale_write(exp, expected_token: str | None) -> JSONResponse:
    resp = JSONResponse(
        status_code=412,
        content={
            "error": "stale_write",
            "experiment_id": exp.id,
            "expected_rev": _expected_rev_from_token(expected_token),
            "current_rev": exp.rev,
            "expected_version": expected_token,
            "current_version": exp.version_token(),
        },
    )
    # Echo the CURRENT strong validator so the client can refresh in one hop.
    resp.headers["ETag"] = exp.etag()
    return resp


def _check_if_match(if_match: str | None, exp) -> JSONResponse | None:
    """Classify an ``If-Match`` header against the loaded experiment.

    Returns an error ``JSONResponse`` to short-circuit, or ``None`` to proceed:
      * absent      -> 428 precondition_required (grace retired; always enforced).
      * ``*``       -> None (matches iff the resource exists — and we loaded it).
      * strong match-> None (proceed).
      * weak/malformed/empty-list -> 400 (whole header malformed).
      * all valid strong validators but none match -> 412 stale_write.
    """
    if if_match is None:
        if vc.precondition_required():
            return _precondition_required(exp)
        return None
    raw = if_match.strip()
    if raw == "*":
        return None  # matches iff the resource exists — and we loaded it
    # RFC 9110 #-list: recipients ignore empty list elements, so a trailing comma
    # or an empty element is tolerated. A header that reduces to NO tags (e.g. just
    # "," or whitespace) is malformed.
    tags = [t for t in (part.strip() for part in raw.split(",")) if t]
    if not tags:
        return _malformed_if_match(exp)
    for tag in tags:
        if tag.startswith("W/") or not _STRONG_TAG_RE.match(tag):
            return _malformed_if_match(exp)
    if any(tag == exp.etag() for tag in tags):
        return None
    # All valid strong validators, none matched -> stale. Report the client's first.
    first_token = tags[0][1:-1] if tags else None
    return _stale_write(exp, first_token)


def _if_none_match_hit(if_none_match: str | None, exp) -> bool:
    """True if the client's If-None-Match indicates the record is UNCHANGED (→304).

    RFC 9110 uses weak comparison for If-None-Match; our validators are strong and
    the client echoes them verbatim, so normalise a leading ``W/`` then string-match.
    ``*`` matches iff the resource exists (it does here). Absent/empty/no-match → not
    a hit (fall through to the full 200 bundle).
    """
    if not if_none_match:
        return False
    raw = if_none_match.strip()
    if raw == "*":
        return True
    current = exp.etag()
    for part in raw.split(","):
        tag = part.strip()
        if tag.startswith("W/"):
            tag = tag[2:]
        if tag == current:
            return True
    return False


# --- summary / detail serialization -------------------------------------------


def _summary(exp: Experiment) -> dict:
    return {
        "id": exp.id,
        "title": exp.title,
        "status": exp.status(),
        "created_utc": exp.created_utc,
        "pending_count": exp.pending_count(),
        "evidenced_field_count": exp.evidenced_field_count(),
        "exported": exp.exported(),
        "record_id": exp.record_id,
    }


def _detail(exp: Experiment) -> dict:
    detail = _summary(exp)
    record_path = exp.record_path()
    sidecar_path = exp.sidecar_path()
    detail.update(
        {
            "draft_ok": exp.draft_ok(),
            # P30.6 — SAFE basename only, never the absolute server/mount path
            # (CLAUDE.md path-boundary rules). The client labels + names the
            # download from the filename; JSON content comes from /artifacts.
            "artifact_refs": {
                "record_filename": record_path.name if exp.exported() and record_path else None,
                "sidecar_filename": sidecar_path.name if exp.exported() and sidecar_path else None,
            },
            "source_files": (exp.source or {}).get("files") or [],
            "workflow": derive_workflow(
                pending_count=exp.pending_count(),
                draft_ok=exp.draft_ok(),
                ready=exp.export_ready(),
                exported=exp.exported(),
                rev=exp.rev,
            ),
            # Derived exported-artifact freshness (P28.2): none | current | stale.
            "artifact": dependencies.artifact_state(exp),
        }
    )
    return detail


def _workflow_for(exp: Experiment) -> dict:
    """Derive the workflow from an experiment's current signals (same call as
    ``_detail``). Used to capture the pre-mutation step states and to surface the
    post-mutation workflow on a mutation response."""
    return derive_workflow(
        pending_count=exp.pending_count(),
        draft_ok=exp.draft_ok(),
        ready=exp.export_ready(),
        exported=exp.exported(),
        rev=exp.rev,
    )


# --- 1. health ----------------------------------------------------------------


def _build_commit() -> str | None:
    """Deploy identity, read live (not cached) so it reflects the running env.

    ``ISAAC_BUILD_COMMIT`` takes precedence when set; else Railway's
    auto-injected ``RAILWAY_GIT_COMMIT_SHA``; else ``None`` — never guessed.
    """
    return (
        os.environ.get("ISAAC_BUILD_COMMIT", "").strip()
        or os.environ.get("RAILWAY_GIT_COMMIT_SHA", "").strip()
        or None
    )


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": runtime_mode.runtime_mode(),
        "core": "isaac_records",
        "version": __version__,
        "commit": _build_commit(),
    }


# --- 2. demo run --------------------------------------------------------------


@router.post("/demo/run")
def demo_run(body: dict = Body(default=None)) -> dict:
    mode = (body or {}).get("mode", "draft_only")
    if mode not in ("draft_only", "full"):
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_mode", "allowed": ["draft_only", "full"]},
        )

    steps: list[dict] = []

    # Idempotent: ensure the canonical five-scenario seed exists first, then run
    # the requested pipeline against a FIXED canonical id, overwriting it in place
    # (upsert) rather than appending a new random experiment. Re-running never
    # increases the record count and preserves canonical identities.
    ws.ensure_seeded()
    target_id = ws.SEED_DONE_ID if mode == "full" else ws.SEED_NEW_DRAFT_ID
    created_utc, title = ws.SEED_META[target_id]

    # [1] build_draft — deterministic extraction from the synthetic fixtures.
    draft = build_draft(ws.CSV_PATH, ws.LISTING_PATH)
    steps.append(
        {
            "name": "build_draft",
            "detail": (
                f"{len(draft.get('fields') or {})} evidenced fields, "
                f"{len(draft.get('pending') or [])} pending blocker(s)"
            ),
            "ok": True,
        }
    )

    # [2] validate_draft — no-guessing checks (pass even with pending open).
    draft_report = validate_draft(draft)
    steps.append(
        {
            "name": "validate_draft",
            "detail": f"draft ok: {str(draft_report.ok).lower()}",
            "ok": draft_report.ok,
        }
    )

    # The persistence of the fixed canonical target id is serialised under the same
    # per-record lock the /answers and /export mutations use, so a concurrent
    # mutation on this id can never lose an update. ensure_seeded/build_draft/
    # validate_draft above stay outside the lock (ensure_seeded only creates MISSING
    # ids; neither racily mutates the target's persisted authoritative state).
    with ws.record_lock(target_id):
        exp = ws.create_experiment(
            title=title,
            source={
                "description": "Synthetic XANES campaign (CuO, Cu K-edge) — committed demo fixtures",
                "files": list(ws.SOURCE_FILES),
            },
            draft=draft,
            id=target_id,
            created_utc=created_utc,
        )

        if mode == "full":
            # [3] apply_answers — the committed SIMULATED human answers, verbatim, so the
            #     completion path matches run_synthetic_demo.py exactly.
            answers = ws.load_demo_answers()
            completed = apply_answers(draft, answers)
            exp.draft = completed
            exp.answer_log.append(
                {"kind": "demo_fixture", "label": "Demo answers (synthetic)", "at": _now_iso()}
            )
            steps.append(
                {
                    "name": "apply_answers",
                    "detail": (
                        f"{len(completed.get('pending') or [])} pending remaining, "
                        f"{len(completed.get('assets') or [])} assets resolved"
                    ),
                    "ok": True,
                }
            )

            # [4] export_draft — schema-gated transform, then write into the workspace.
            result = export_draft(completed, REPO_ROOT, record_id=exp.id)
            if result.ok:
                _write_record(exp, result)
            exp.save()
            steps.append(
                {
                    "name": "export_draft",
                    "detail": (
                        f"official schema valid: "
                        f"{result.official_report.ok if result.official_report else False}"
                    ),
                    "ok": result.ok,
                }
            )
        else:
            exp.save()

    return {"experiment_id": exp.id, "steps": steps, "status": exp.status()}


# --- 2b. guarded synthetic-demo reset (P26.0b) --------------------------------
#
# Restores the workspace to EXACTLY the five canonical P26.0a scenarios. It never
# accepts caller-supplied ids or paths (unknown fields are rejected by the typed
# request model), removes ONLY managed synthetic-demo records, and refuses on any
# ambiguous record. There is deliberately NO general per-experiment delete route.

_RESET_CONFIRMATION = "RESET SYNTHETIC DEMO"


class DemoResetRequest(BaseModel):
    """Typed reset request. ``extra="forbid"`` rejects any caller-supplied ids or
    paths (e.g. ``ids``/``experiment_id``/``path``) with a 422 — they can never
    influence what is removed."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["preview", "execute"]
    confirmation: str | None = None


class DemoResetResponse(BaseModel):
    """Typed, path-free reset result (no filesystem paths ever leak out)."""

    status: Literal["ok", "refused"]
    mode: Literal["preview", "execute"]
    previous_count: int
    canonical_count: int
    legacy_count: int
    ambiguous_count: int
    removed_count: int
    final_count: int
    canonical_ids: list[str]
    removable: list[dict]
    state_counts: dict


def _reset_response(data: dict, *, mode: str, status: str, http: int) -> JSONResponse:
    payload = {k: v for k, v in data.items() if k != "refused"}
    resp = DemoResetResponse(status=status, mode=mode, **payload)
    return JSONResponse(status_code=http, content=resp.model_dump())


@router.post("/demo/reset")
def demo_reset(req: DemoResetRequest):
    # demo_reset is a single-user, confirmation-gated synthetic-demo admin reset: a
    # whole-workspace rmtree-of-managed-legacy + reseed spanning MULTIPLE ids. It is
    # intentionally NOT coordinated with the per-record mutation locks (which guard a
    # single id's compare-and-swap); a multi-id admin reset has no meaningful single
    # lock to take, and it is not part of the concurrent-writer contract.
    mode = req.mode

    # Governance gate: refuse outside synthetic-only mode (classification is
    # read-only, so it is safe to report counts alongside the refusal).
    if not ws.is_synthetic_only():
        data = ws.reset_to_canonical_seed(dry_run=True)
        return _reset_response(data, mode=mode, status="refused", http=403)

    # Preview NEVER mutates: classify only.
    if mode == "preview":
        data = ws.reset_to_canonical_seed(dry_run=True)
        status = "refused" if data["refused"] else "ok"
        return _reset_response(data, mode=mode, status=status, http=200)

    # Execute requires the exact confirmation phrase; otherwise no mutation.
    if req.confirmation != _RESET_CONFIRMATION:
        data = ws.reset_to_canonical_seed(dry_run=True)
        return _reset_response(data, mode=mode, status="refused", http=409)

    # Confirmed execute: the reset itself refuses (no mutation) if any ambiguous
    # record is present; otherwise it removes managed legacy + reseeds.
    data = ws.reset_to_canonical_seed(dry_run=False)
    if data["refused"]:
        return _reset_response(data, mode=mode, status="refused", http=409)
    return _reset_response(data, mode=mode, status="ok", http=200)


# --- 3. list ------------------------------------------------------------------


@router.get("/experiments")
def list_experiments() -> dict:
    return {"experiments": [_summary(e) for e in ws.list_experiments()]}


# --- 4. detail ----------------------------------------------------------------


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: str,
    response: Response,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    # Conditional GET (P27.6 live-sync polling): if the client's If-None-Match
    # matches the current strong validator, the record is unchanged -> 304 with the
    # ETag and NO body (a cheap change signal; polling is only a signal, the fetched
    # snapshot remains authoritative).
    if _if_none_match_hit(if_none_match, exp):
        return Response(status_code=304, headers={"ETag": exp.etag()})
    detail = _detail(exp)
    detail.update(vc.version_fields(exp))
    response.headers["ETag"] = exp.etag()
    return detail


# --- 5. draft (grouped) -------------------------------------------------------


@router.get("/experiments/{experiment_id}/draft")
def get_draft(experiment_id: str, response: Response):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    response.headers["ETag"] = exp.etag()
    return serialize.draft_to_groups(exp.draft)


# --- 6. pending ---------------------------------------------------------------


@router.get("/experiments/{experiment_id}/pending")
def get_pending(experiment_id: str, response: Response):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    response.headers["ETag"] = exp.etag()
    return serialize.pending_to_list(exp.draft, ws.load_demo_answers())


# --- 7. answers ---------------------------------------------------------------


def _answers_to_apply_shape(answers_by_id: dict, draft: dict, timestamp: str) -> dict:
    """Translate UI answers (keyed by blocker id/about) into ``apply_answers`` input.

    Only values literally present are forwarded; blank/missing answers are dropped, so the
    core never invents. Asset blockers key on their URI; ``series``/``descriptor``/``edge``
    key on their kind name.
    """
    pending = draft.get("pending") or []
    # An asset key is recognized if it names a still-pending asset blocker (the
    # /answers fill path) OR an asset already present in the draft (the /edit
    # correction path, where 0 pending means no blocker carries the uri). The union
    # leaves /answers behaviour unchanged — a pending asset is never yet in
    # draft["assets"], so its uri is still recognized exactly as before.
    asset_uris = {e.get("uri") for e in pending if e.get("kind") == "asset"}
    asset_uris |= {a.get("uri") for a in (draft.get("assets") or []) if isinstance(a, dict)}
    out: dict = {"timestamp": timestamp, "asset_sha256": {}}
    for key, value in (answers_by_id or {}).items():
        if value in (None, ""):
            continue
        if key in asset_uris:
            out["asset_sha256"][key] = value
        elif key in ("series", "descriptor", "descriptor_label", "edge"):
            out[key] = value
        # Unknown keys are ignored — never invented into the draft.
    return out


@router.post("/experiments/{experiment_id}/answers")
def post_answers(
    experiment_id: str,
    response: Response,
    body: dict = Body(...),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    # Cheap existence pre-check OUTSIDE the lock so a bogus/non-existent id never
    # creates a permanent entry in the never-evicting per-record lock map (bounds
    # it to ids that actually resolve to a record).
    if ws.load_experiment(experiment_id) is None:
        return _not_found(experiment_id)
    # The per-record lock serialises the entire load->precondition->mutate->save
    # compare-and-swap; the experiment is loaded FRESH inside the lock so two
    # writers holding the same token cannot both succeed.
    with ws.record_lock(experiment_id):
        exp = ws.load_experiment(experiment_id)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        if body.get("confirmed_by_user") is not True:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "confirmation_required",
                    "message": "confirmed_by_user must be true to apply answers.",
                },
            )
        err = _check_if_match(if_match, exp)
        if err is not None:
            return err
        # Capture the PRE-mutation workflow so the invalidation can report the
        # reopen DELTA (which completed steps regressed) after applying answers.
        pre_steps = _workflow_for(exp)["ordered_steps"]
        # The answer keys we are about to forward (non-blank, recognised). On a
        # real change these are the fields written; on a no-op nothing is written.
        submitted_fields = [
            k for k, v in (body.get("answers") or {}).items() if v not in (None, "")
        ]
        timestamp = _now_iso()
        apply_shape = _answers_to_apply_shape(body.get("answers") or {}, exp.draft, timestamp)
        exp.draft = apply_answers(exp.draft, apply_shape)
        # answer_log is EXCLUDED from the rev signature: log the submission only when it
        # actually changes the authoritative draft, so an identical re-entry is neither
        # logged nor rewritten (byte-stable) and never bumps rev. save_versioned decides
        # by comparing the on-disk authoritative signature.
        exp.answer_log.append({"applied": apply_shape, "at": timestamp})
        changed = exp.save_versioned()
        if not changed:
            exp.answer_log.pop()  # no-op re-entry: discard the speculative log append
        # Derived downstream invalidation (P28.2) at the post-mutation revision. A
        # byte-stable no-op reports changed=False with empty deltas and no rev bump.
        changed_fields = submitted_fields if changed else []
        invalidation = dependencies.build_invalidation(
            changed=changed,
            changed_fields=changed_fields,
            pre_steps=pre_steps,
            post_exp=exp,
        )
        result = serialize.pending_to_list(exp.draft, ws.load_demo_answers())
        result["status"] = exp.status()
        result.update(vc.version_fields(exp))
        result["workflow"] = _workflow_for(exp)
        result["invalidation"] = invalidation
        response.headers["ETag"] = exp.etag()
        return result


# --- 7b. edit (correct an already-answered field) -----------------------------


def _has_correction_target(apply_shape: dict) -> bool:
    """True iff ``apply_shape`` names at least one recognized correction field.

    An asset sha256 (keyed by a known uri), a series/descriptor/edge value. A bare
    ``descriptor_label`` (or only ``timestamp``/``asset_sha256:{}``) is NOT an
    actionable correction — an edit body that reduces to nothing recognized is
    rejected (422) rather than silently no-op'd, so an unknown field is never
    quietly swallowed.
    """
    return bool(apply_shape.get("asset_sha256")) or any(
        k in apply_shape for k in ("series", "descriptor", "edge")
    )


@router.post("/experiments/{experiment_id}/edit")
def post_edit(
    experiment_id: str,
    response: Response,
    body: dict = Body(...),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    # Mirrors post_answers EXACTLY: existence pre-check OUTSIDE the lock so a bogus
    # id never pins a permanent entry in the never-evicting per-record lock map.
    if ws.load_experiment(experiment_id) is None:
        return _not_found(experiment_id)
    # The per-record lock serialises load->precondition->mutate->save; the record is
    # loaded FRESH inside the lock so two writers holding the same token cannot both
    # succeed (compare-and-swap).
    with ws.record_lock(experiment_id):
        exp = ws.load_experiment(experiment_id)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window
        if body.get("confirmed_by_user") is not True:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "confirmation_required",
                    "message": "confirmed_by_user must be true to correct a field.",
                },
            )
        err = _check_if_match(if_match, exp)
        if err is not None:
            return err
        # Capture the PRE-mutation workflow so the invalidation reports the reopen
        # DELTA (which completed steps, if any, regressed) after the correction.
        pre_steps = _workflow_for(exp)["ordered_steps"]
        submitted_fields = [
            k for k, v in (body.get("answers") or {}).items() if v not in (None, "")
        ]
        timestamp = _now_iso()
        apply_shape = _answers_to_apply_shape(body.get("answers") or {}, exp.draft, timestamp)
        if not _has_correction_target(apply_shape):
            # No recognized field to correct — never invent one.
            return JSONResponse(
                status_code=422,
                content={
                    "error": "unrecognized_field",
                    "message": "No editable field was recognized in the request.",
                },
            )
        # OVERWRITE the current value(s) for the recognized keys, recording a fresh
        # user_confirmation. apply_corrections never touches pending and never
        # invents a value (a malformed sha256 / off-enum qc leaves the value as-is).
        exp.draft = apply_corrections(exp.draft, apply_shape)
        exp.answer_log.append({"edited": apply_shape, "at": timestamp})
        changed = exp.save_versioned()
        if not changed:
            exp.answer_log.pop()  # byte-stable no-op: discard the speculative log append
        changed_fields = submitted_fields if changed else []
        invalidation = dependencies.build_invalidation(
            changed=changed,
            changed_fields=changed_fields,
            pre_steps=pre_steps,
            post_exp=exp,
        )
        result = serialize.pending_to_list(exp.draft, ws.load_demo_answers())
        result["status"] = exp.status()
        result.update(vc.version_fields(exp))
        result["workflow"] = _workflow_for(exp)
        result["invalidation"] = invalidation
        response.headers["ETag"] = exp.etag()
        return result


# --- 8. export ----------------------------------------------------------------


def _write_record(exp: Experiment, result) -> None:
    """Write record + sidecar into the experiment records dir and mark it exported."""
    exp.records_dir.mkdir(parents=True, exist_ok=True)
    exp.record_id = result.record["record_id"]
    record_path = exp.records_dir / f"{exp.record_id}.json"
    sidecar_path = exp.records_dir / f"{exp.record_id}.evidence.json"
    atomic_write_text(record_path, json.dumps(result.record, indent=2) + "\n")
    atomic_write_text(sidecar_path, json.dumps(result.sidecar, indent=2) + "\n")


@router.post("/experiments/{experiment_id}/export")
def post_export(
    experiment_id: str,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    # Cheap existence pre-check OUTSIDE the lock so a bogus/non-existent id never
    # creates a permanent entry in the never-evicting per-record lock map.
    if ws.load_experiment(experiment_id) is None:
        return _not_found(experiment_id)
    # The per-record lock serialises load->precondition->mutate->save; load FRESH
    # inside the lock. The precondition (400/412) is evaluated BEFORE the export
    # immutability 409 so a stale client refreshes before making a state decision.
    with ws.record_lock(experiment_id):
        exp = ws.load_experiment(experiment_id)
        if exp is None:
            return _not_found(experiment_id)  # deleted in the pre-check→lock race window

        err = _check_if_match(if_match, exp)
        if err is not None:
            return err

        # Capture the PRE-export workflow for the reopen DELTA (export normally
        # completes the final step, so no step reopens — but we report honestly).
        pre_steps = _workflow_for(exp)["ordered_steps"]

        # Immutability guard (mirrors cli.cmd_export): never overwrite an existing record.
        record_path = exp.records_dir / f"{exp.id}.json"
        if record_path.exists():
            return JSONResponse(
                status_code=409,
                content={
                    "error": "record_exists",
                    "message": f"{record_path.name} already exists; records are immutable.",
                    "record_id": exp.id,
                },
            )

        result = export_draft(exp.draft, REPO_ROOT, record_id=exp.id)
        payload = serialize.export_result_to_dict(result)
        if not result.ok:
            # Nothing written. Surface the failing reports and a flat errors list.
            # No mutation happened, so report an honest changed=False invalidation
            # (never fabricate a mutation that did not occur).
            errors = []
            if payload["official_report"]:
                errors = payload["official_report"]["errors"]
            elif not result.draft_report.ok:
                errors = payload["draft_report"]["errors"]
            payload["errors"] = errors
            payload["workflow"] = _workflow_for(exp)
            payload["invalidation"] = dependencies.build_invalidation(
                changed=False, changed_fields=[], pre_steps=pre_steps, post_exp=exp
            )
            return JSONResponse(status_code=200, content=payload)

        _write_record(exp, result)
        # export changes the authoritative state (record_id: None -> id), so this bumps
        # rev and stamps updated_utc, persisting the state atomically.
        exp.save_versioned()
        payload["record_id"] = exp.record_id
        # P30.6 — SAFE basename only (see _detail); never the absolute path.
        payload["artifact_refs"] = {
            "record_filename": exp.record_path().name,
            "sidecar_filename": exp.sidecar_path().name,
        }
        payload.update(vc.version_fields(exp))
        # export completes the final workflow step and makes the artifact current.
        payload["workflow"] = _workflow_for(exp)
        payload["invalidation"] = dependencies.build_invalidation(
            changed=True,
            changed_fields=["record_id"],
            pre_steps=pre_steps,
            post_exp=exp,
        )
        response.headers["ETag"] = exp.etag()
        return payload


# --- 9. validate --------------------------------------------------------------


@router.post("/experiments/{experiment_id}/validate")
def post_validate(experiment_id: str):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)

    if exp.exported():
        record = json.loads(exp.record_path().read_text(encoding="utf-8"))
        report = validate_official(record, REPO_ROOT)
        return {
            "ok": report.ok,
            "errors": [{"path": e.path, "message": e.message} for e in report.errors],
            "schema": SCHEMA_LABEL,
            "dry_run": False,
        }

    # Dry-run: export_draft in memory (writes nothing). Robust to malformed drafts.
    try:
        result = export_draft(exp.draft, REPO_ROOT)
        if result.official_report is not None:
            errors = [
                {"path": e.path, "message": e.message}
                for e in result.official_report.errors
            ]
        elif not result.draft_report.ok:
            errors = [
                {"path": w, "message": m} for w, m in result.draft_report.errors
            ]
        else:
            errors = []
        ok = result.ok
    except Exception as exc:  # pragma: no cover - defensive; return errors, not 500
        ok, errors = False, [{"path": "$", "message": f"validation error: {exc}"}]

    return {"ok": ok, "errors": errors, "schema": SCHEMA_LABEL, "dry_run": True}


# --- 10. audit ----------------------------------------------------------------


@router.post("/experiments/{experiment_id}/audit")
def post_audit(experiment_id: str):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    if not exp.exported():
        return {
            "records": [],
            "text": "No records found.",
            "message": "Nothing exported yet — export this experiment before auditing.",
        }
    results = audit_records(exp.records_dir, REPO_ROOT)
    return serialize.audit_to_dict(results, render_audit(results))


# --- 11. warnings (advisory, non-gating) --------------------------------------


def _warnings_payload(exp: Experiment) -> dict:
    if exp.exported():
        record = json.loads(exp.record_path().read_text(encoding="utf-8"))
        dry_run = False
    else:
        # Advisory check on the dry-run record (populated even when official fails).
        result = export_draft(exp.draft, REPO_ROOT)
        record = result.record or {}
        dry_run = True
    payload = serialize.warnings_to_dict(portal_warnings(record))
    payload["dry_run"] = dry_run
    return payload


@router.get("/experiments/{experiment_id}/warnings")
def get_warnings(experiment_id: str):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    return _warnings_payload(exp)


@router.post("/experiments/{experiment_id}/warnings")
def post_warnings(experiment_id: str):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    return _warnings_payload(exp)


# --- 12. evidence -------------------------------------------------------------


@router.get("/experiments/{experiment_id}/evidence")
def get_evidence(experiment_id: str):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    if exp.exported():
        record = json.loads(exp.record_path().read_text(encoding="utf-8"))
        sidecar = json.loads(exp.sidecar_path().read_text(encoding="utf-8"))
        entries = serialize.evidence_trail_from_sidecar(sidecar, record)
    else:
        entries = serialize.evidence_trail_from_draft(exp.draft)
    return {"evidence": entries}


# --- 12b. evidence classification (P28.5, evidence-support axis, read-only) ----

#: The five evidence-support classes, in the display precedence used everywhere.
#: The single source for the ``counts`` histogram key set.
_EVIDENCE_CLASSES = (
    "supported",
    "inferred_candidate",
    "insufficient_evidence",
    "conflicting_evidence",
    "unknown",
)


@router.get("/experiments/{experiment_id}/evidence-classification")
def get_evidence_classification(experiment_id: str, response: Response):
    """Typed evidence-support classification for the CURRENT record (P28.4 view).

    Read-only; carries ONLY the evidence-support axis — ``field_results`` (from the
    frozen ``evidence_classify.classify_fields``) plus a same-axis ``counts``
    histogram — bound to the authoritative ``record_rev`` so a client can detect a
    stale view. It deliberately carries NO validity/completion/advisory verdict
    (no ``valid``/``ok``/``exportable``/``complete``/``blocking``/``warnings``);
    those stay in their own endpoints. No lock is taken (pure read).
    """
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    field_results = evidence_classify.classify_fields(exp.draft)
    counts = {c: 0 for c in _EVIDENCE_CLASSES}
    for fr in field_results:
        counts[fr["classification"]] += 1
    response.headers["ETag"] = exp.etag()
    return {"record_rev": exp.rev, "field_results": field_results, "counts": counts}


# --- 13. source preview -------------------------------------------------------


@router.get("/experiments/{experiment_id}/source-preview")
def get_source_preview(experiment_id: str, source: str = ""):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    try:
        return sources.read_source(source, exp)
    except sources.SourceTraversal:
        return JSONResponse(
            status_code=400,
            content={
                "error": "unsafe_source_name",
                "message": "Path traversal rejected — pass a bare fixture basename.",
            },
        )
    except sources.SourceNotAllowed:
        return JSONResponse(
            status_code=404,
            content={
                "error": "source_not_allowed",
                "message": (
                    "Only the two committed synthetic fixtures may be previewed in this "
                    "synthetic prototype."
                ),
                "allowed": list(ws.SOURCE_FILES),
            },
        )


# --- 13b. artifacts (exported record + sidecar content, read-only) ------------


@router.get("/experiments/{experiment_id}/artifacts")
def get_artifacts(experiment_id: str):
    """Return the written record + sidecar JSON for an exported experiment.

    Read-only: it reads ONLY the two files ``export`` wrote inside the workspace,
    resolved from the record id (never a query-controlled path). A non-exported
    experiment returns null payloads (200, not an error); an unknown id is 404.
    """
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    if not exp.exported():
        return {
            "record": None,
            "sidecar": None,
            "record_filename": None,
            "sidecar_filename": None,
        }
    record_path = exp.record_path()
    sidecar_path = exp.sidecar_path()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    return {
        "record": record,
        "sidecar": sidecar,
        # P30.6 — SAFE basename only, never the absolute server/mount path.
        "record_filename": record_path.name,
        "sidecar_filename": sidecar_path.name,
    }


# --- 14. graph status (memory plane) ------------------------------------------


#: Additive /graph/status count fields sourced from the memory reader's overview.
#: Single-source guarantee: the separated status fields and these counts describe
#: the SAME graph — the handler resolves ONE reader and reads both its
#: ``status()`` and its ``overview()`` off that one instance. Present with real
#: values when the reader is available; explicit ``null`` (not omitted, for shape
#: stability) otherwise. (``source_graph_commit`` carries the built_at_commit as a
#: top-level version-metadata field, so it is not repeated here.)
_STATUS_ADDITIVE_FIELDS = (
    "node_count", "edge_count", "community_count",
    "file_count", "concept_count", "graph_mtime",
)

#: Memory-plane notes (P24.10). Leads/provenance framing only — never
#: PASS/FAIL/valid/invalid/verdict wording, and never phrased around a single
#: conflated freshness status (there isn't one anymore). Keyed by availability.
_GRAPH_STATUS_NOTES = {
    "available": (
        "Project Memory provides leads and provenance, never a correctness "
        "ruling — confirm every lead against the cited files."
    ),
    "unavailable": (
        "Project Memory is unavailable, so no leads can be served. It provides "
        "leads and provenance, never a correctness ruling — confirm against the "
        "cited files."
    ),
}


@router.get("/graph/status")
def graph_status() -> dict:
    """Provider-agnostic, separated memory-plane status (P24.10).

    Resolves ONE reader and reads BOTH its ``status()`` (provider identity +
    separated availability / integrity / provable freshness) and its
    ``overview()`` (counts) off that same instance — never
    ``isinstance``-branches on which provider it is.

    App-HEAD equality is REMOVED from all freshness: the deployed commit is
    surfaced ONLY as ``deployed_app_commit`` version metadata, never an input to
    ``memory_policy`` or ``indexed_sources``. The two freshness concepts are kept
    separate and provable; the reader returns ``"unknown"`` rather than
    manufacturing ``"current"`` when it cannot prove a status.
    """
    reader = memory.get_default_reader()
    st = reader.status()
    overview = reader.overview()

    available = st["available"]
    availability = "available" if available else "unavailable"
    note = _GRAPH_STATUS_NOTES["available" if available else "unavailable"]

    body = {
        "plane": "memory",
        "availability": availability,
        "integrity": st["integrity"],
        "provider": st["provider_kind"] if available else "unavailable",
        "memory_policy": st["policy_consistency"],
        "indexed_sources": st["indexed_sources"],
        "policy_fingerprint": st["policy_fingerprint"],
        "served_manifest_fingerprint": st["served_manifest_fingerprint"],
        "served_file_count": st["served_file_count"],
        "freshness_scope": st["freshness_scope"],
        "freshness_basis": st["freshness_basis"],
        "source_graph_commit": st["source_graph_commit"],
        "snapshot_schema_version": st["snapshot_schema_version"],
        # VERSION METADATA ONLY — never a freshness input.
        "deployed_app_commit": _build_commit(),
        "note": note,
    }
    if overview["available"]:
        body.update(
            node_count=overview["node_count"],
            edge_count=overview["edge_count"],
            community_count=overview["community_count"],
            file_count=overview["served_file_count"],
            concept_count=overview["concept_count"],
            graph_mtime=overview["graph_mtime"],
        )
    else:
        body.update({key: None for key in _STATUS_ADDITIVE_FIELDS})
    return body


# --- 15. uploads (always blocked) ---------------------------------------------


@router.post("/uploads")
def uploads():
    # Governance seam: no multipart is declared or parsed; no file is read or stored.
    # The refusal is tied to the authoritative runtime-mode source; uploads stay
    # blocked in synthetic-only mode (real-data ingestion is Phase 31, not here).
    payload = dict(_UPLOAD_BLOCKED)
    payload["synthetic_only"] = ws.is_synthetic_only()
    return JSONResponse(status_code=403, content=payload)


# --- 16. memory (project memory plane over HTTP) -------------------------------
#
# Thin HTTP wrapper around the read-only ``isaac_api.memory`` reader (P24.1).
# Handlers call ONLY the reader (plus FastAPI plumbing) — no isaac_records
# imports, no verdict computation. The reader never raises for artifact
# problems, so these handlers never need a try/except to avoid a 500.

MEMORY_NOTE = "Project memory returns leads to verify — never a validation verdict."


def _memory_error(status_code: int, error: str, **extra) -> JSONResponse:
    content = {"error": error, "plane": "memory", "note": MEMORY_NOTE}
    content.update(extra)
    return JSONResponse(status_code=status_code, content=content)


@router.get("/memory/concepts")
def get_memory_concepts() -> dict:
    reader = memory.get_default_reader()
    overview = reader.overview()
    if not overview["available"]:
        return {
            "plane": "memory",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": overview["reason"],
            "concepts": [],
        }
    return {
        "plane": "memory",
        "note": MEMORY_NOTE,
        "available": True,
        "concepts": reader.concepts(),
    }


@router.get("/memory/concepts/{concept_id}")
def get_memory_concept(concept_id: str):
    reader = memory.get_default_reader()
    overview = reader.overview()
    if not overview["available"]:
        return {
            "plane": "memory",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": overview["reason"],
            "concept": None,
            "related": {"files": [], "concepts": []},
        }
    # Availability wins over 404 — we cannot know the id set without a graph,
    # so an unknown id is only ever reported once we know the graph is readable.
    detail = reader.concept(concept_id)
    if detail is None:
        return _memory_error(404, "concept_not_found", id=concept_id)
    related = detail.pop("related")
    return {
        "plane": "memory",
        "note": MEMORY_NOTE,
        "available": True,
        "concept": detail,
        "related": related,
    }


@router.get("/memory/files")
def get_memory_files() -> dict:
    reader = memory.get_default_reader()
    overview = reader.overview()
    if not overview["available"]:
        return {
            "plane": "memory",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": overview["reason"],
            "files": [],
        }
    return {
        "plane": "memory",
        "note": MEMORY_NOTE,
        "available": True,
        "files": reader.files(),
    }


@router.get("/memory/file")
def get_memory_file(path: str = ""):
    reader = memory.get_default_reader()
    # Unsafe path is a deterministic, availability-independent guard: it wins
    # even when the graph is absent (spec §3.5).
    classification = reader.classify_path(path)
    if classification == "unsafe":
        return _memory_error(400, "unsafe_source_path", path=path)

    overview = reader.overview()
    if not overview["available"]:
        return {
            "plane": "memory",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": overview["reason"],
            "file": None,
            "related": {"files": [], "concepts": []},
            "rationales": [],
        }
    if classification == "not_indexed":
        return _memory_error(404, "source_not_indexed", path=path)

    detail = reader.file(path)
    related = detail.pop("related")
    rationales = detail.pop("rationales")
    return {
        "plane": "memory",
        "note": MEMORY_NOTE,
        "available": True,
        "file": detail,
        "related": related,
        "rationales": rationales,
    }


# --- 17. search (composed truth + memory planes, grouped, no verdict) ----------
#
# Composes the two existing search cores into ONE grouped, plane-labeled envelope.
# It computes NO verdict and carries NO verdict keys. Each plane is a separate,
# self-labeled group so a client always knows which plane a lead came from and can
# never confuse a memory lead for a truth-plane ruling.
#
# Degradation is ALWAYS in-body (available:false + reason), never a 5xx: both cores
# are designed never to raise, and the composition is additionally wrapped so any
# unexpected failure still yields a shaped 200 with the affected group degraded.
#
# ``scope`` selects which planes are actually searched:
#   * ``all``       -> both planes searched and populated.
#   * ``workspace`` -> workspace searched; memory group PRESENT with its real
#                      availability reported but no rows (memory not searched).
#   * ``memory``    -> symmetric: memory searched; workspace group present, no rows.
# ``normalized_query`` is always computed (workspace_search is cheap over the tens of
# in-memory snapshots) even when the workspace group's rows are blanked out.

_SEARCH_SCOPES = ("all", "workspace", "memory")


def _blank_group_rows(group: dict) -> dict:
    """Report a group's availability/reason but with no rows (out-of-scope plane)."""
    group["results"] = []
    group["total"] = 0
    group["returned"] = 0
    return group


@router.get("/search")
def search_records(
    q: str = "", scope: str = "all", limit: int = 10, offset: int = 0
) -> dict:
    if scope not in _SEARCH_SCOPES:
        scope = "all"

    # --- workspace group (truth plane) ---
    # Always run the workspace core: it is cheap over the in-memory snapshot and it
    # is the source of the envelope's ``normalized_query``. Only its rows are blanked
    # when the workspace plane is out of scope.
    normalized_query = search.normalize((q or "")[:256])
    query_too_short = False
    try:
        exps = ws.list_experiments()  # hardened, read-race-safe snapshot
        wres = search.workspace_search(q, exps, limit=limit, offset=offset)
        normalized_query = wres.normalized_query
        query_too_short = wres.reason == search.QUERY_TOO_SHORT
        workspace_group = {
            "plane": search.PLANE,
            "provider": search.PROVIDER,
            "available": True,
            "reason": wres.reason,
            "total": wres.total,
            "returned": wres.returned,
            "limit": wres.limit,
            "offset": wres.offset,
            "results": [dataclasses.asdict(r) for r in wres.results],
        }
    except Exception:  # pragma: no cover - defensive; degrade in-body, never 500
        workspace_group = {
            "plane": search.PLANE,
            "provider": search.PROVIDER,
            "available": False,
            "reason": None,
            "total": 0,
            "returned": 0,
            "limit": max(0, limit),
            "offset": max(0, offset),
            "results": [],
        }
    if scope == "memory":
        _blank_group_rows(workspace_group)

    # --- memory group (memory plane) ---
    try:
        reader = memory.get_default_reader()
        mres = reader.search(q, limit=limit, offset=offset)
        try:
            provider_kind = reader.status().get("provider_kind")
        except Exception:  # pragma: no cover - defensive; identity only
            provider_kind = None
        memory_group = {
            "plane": "memory",
            # Coalesce a missing kind to "unavailable" so the label is never the
            # literal "memory:None" (only reachable if status() unexpectedly raises).
            "provider": f"memory:{provider_kind or 'unavailable'}",
            "note": MEMORY_NOTE,
            "available": mres["available"],
            "reason": mres["reason"],
            "total": mres["total"],
            "returned": mres["returned"],
            "limit": mres["limit"],
            "offset": mres["offset"],
            "results": mres["results"],
        }
    except Exception:  # pragma: no cover - defensive; degrade in-body, never 500
        memory_group = {
            "plane": "memory",
            "provider": "memory:unavailable",
            "note": MEMORY_NOTE,
            "available": False,
            "reason": "graph_unreadable",
            "total": 0,
            "returned": 0,
            "limit": max(0, limit),
            "offset": max(0, offset),
            "results": [],
        }
    # A too-short query is a QUERY-level condition, orthogonal to plane
    # availability: the workspace core reports it directly, but the memory core
    # checks availability first and so would surface ``graph_absent`` for a short
    # query against an absent graph. Normalize both planes to the same query-level
    # ``query_too_short`` reason (with no rows) so the envelope is symmetric — the
    # plane's own ``available`` flag still reports its true state.
    if query_too_short:
        memory_group["reason"] = search.QUERY_TOO_SHORT
        _blank_group_rows(memory_group)

    if scope == "workspace":
        _blank_group_rows(memory_group)

    return {
        "query": q,
        "normalized_query": normalized_query,
        "scope": scope,
        "workspace": workspace_group,
        "memory": memory_group,
    }


# --- 18. runtime records (thin read-only cross-record projection, P30.1) -------
#
# A DERIVED read model over the SAME ``list_experiments()`` snapshot search uses —
# no index, no cache, no lock, current-by-construction. It emits ONLY the safe
# confirmed-facts allow-set (see ``runtime_records``) plus freshness metadata, and
# accepts a few typed filters the cross-record triage consumer uses. Auth is
# enforced by the app-wide middleware exactly like the other reads (401 when the
# key is set). It never mutates and never touches the truth path.


@router.get("/runtime/records")
def runtime_record_projection(
    status: str | None = None,
    workflow_state: str | None = None,
    artifact: str | None = None,
    has_conflict: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    filters = {
        "status": status,
        "workflow_state": workflow_state,
        "artifact": artifact,
        "has_conflict": has_conflict,
    }
    # Fresh scan each call → project → filter. ``total`` is the filtered count
    # BEFORE pagination so a client can page without losing the denominator.
    records = runtime_records.project_records(ws.list_experiments(), filters=filters)
    total = len(records)
    start = max(0, offset)
    records = records[start:]
    if limit is not None:
        records = records[: max(0, limit)]
    return {"records": records, "total": total}

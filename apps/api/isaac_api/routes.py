"""HTTP endpoints for the local UI prototype (all JSON, prefixed ``/api``).

Every verdict is produced by an ``isaac_records`` core function — this module only
routes, serializes (via ``serialize``), and enforces the synthetic-only governance
boundary. It adds no validation logic and never mutates the truth path.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from isaac_records.audit import audit_records, render_audit
from isaac_records.complete import apply_answers
from isaac_records.draft_validator import validate_draft
from isaac_records.export import export_draft
from isaac_records.extract.draft_builder import build_draft
from isaac_records.official import EXPECTED_VERSION, validate_official
from isaac_records.portal_warnings import portal_warnings

from . import __version__
from . import serialize
from . import sources
from . import workspace as ws
from .workspace import REPO_ROOT, Experiment

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
            "artifact_refs": {
                "record_path": str(record_path) if exp.exported() else None,
                "sidecar_path": str(sidecar_path) if exp.exported() else None,
            },
            "source_files": (exp.source or {}).get("files") or [],
        }
    )
    return detail


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
        "mode": "synthetic-only",
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

    exp = ws.create_experiment(
        title="Synthetic XANES — CuO (Cu K-edge) Demo (demo/run)",
        source={
            "description": "Synthetic XANES campaign (CuO, Cu K-edge) — committed demo fixtures",
            "files": list(ws.SOURCE_FILES),
        },
        draft=draft,
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


# --- 3. list ------------------------------------------------------------------


@router.get("/experiments")
def list_experiments() -> dict:
    return {"experiments": [_summary(e) for e in ws.list_experiments()]}


# --- 4. detail ----------------------------------------------------------------


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    return _detail(exp)


# --- 5. draft (grouped) -------------------------------------------------------


@router.get("/experiments/{experiment_id}/draft")
def get_draft(experiment_id: str):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    return serialize.draft_to_groups(exp.draft)


# --- 6. pending ---------------------------------------------------------------


@router.get("/experiments/{experiment_id}/pending")
def get_pending(experiment_id: str):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    return serialize.pending_to_list(exp.draft, ws.load_demo_answers())


# --- 7. answers ---------------------------------------------------------------


def _answers_to_apply_shape(answers_by_id: dict, draft: dict, timestamp: str) -> dict:
    """Translate UI answers (keyed by blocker id/about) into ``apply_answers`` input.

    Only values literally present are forwarded; blank/missing answers are dropped, so the
    core never invents. Asset blockers key on their URI; ``series``/``descriptor``/``edge``
    key on their kind name.
    """
    pending = draft.get("pending") or []
    asset_uris = {e.get("uri") for e in pending if e.get("kind") == "asset"}
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
def post_answers(experiment_id: str, body: dict = Body(...)):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)
    if body.get("confirmed_by_user") is not True:
        return JSONResponse(
            status_code=422,
            content={
                "error": "confirmation_required",
                "message": "confirmed_by_user must be true to apply answers.",
            },
        )
    timestamp = _now_iso()
    apply_shape = _answers_to_apply_shape(body.get("answers") or {}, exp.draft, timestamp)
    exp.draft = apply_answers(exp.draft, apply_shape)
    exp.answer_log.append({"applied": apply_shape, "at": timestamp})
    exp.save()
    result = serialize.pending_to_list(exp.draft, ws.load_demo_answers())
    result["status"] = exp.status()
    return result


# --- 8. export ----------------------------------------------------------------


def _write_record(exp: Experiment, result) -> None:
    """Write record + sidecar into the experiment records dir and mark it exported."""
    exp.records_dir.mkdir(parents=True, exist_ok=True)
    exp.record_id = result.record["record_id"]
    record_path = exp.records_dir / f"{exp.record_id}.json"
    sidecar_path = exp.records_dir / f"{exp.record_id}.evidence.json"
    record_path.write_text(json.dumps(result.record, indent=2) + "\n", encoding="utf-8")
    sidecar_path.write_text(json.dumps(result.sidecar, indent=2) + "\n", encoding="utf-8")


@router.post("/experiments/{experiment_id}/export")
def post_export(experiment_id: str):
    exp = ws.load_experiment(experiment_id)
    if exp is None:
        return _not_found(experiment_id)

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
        errors = []
        if payload["official_report"]:
            errors = payload["official_report"]["errors"]
        elif not result.draft_report.ok:
            errors = payload["draft_report"]["errors"]
        payload["errors"] = errors
        return JSONResponse(status_code=200, content=payload)

    _write_record(exp, result)
    exp.save()
    payload["record_id"] = exp.record_id
    payload["artifact_refs"] = {
        "record_path": str(exp.record_path()),
        "sidecar_path": str(exp.sidecar_path()),
    }
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
            "record_path": None,
            "sidecar_path": None,
        }
    record_path = exp.record_path()
    sidecar_path = exp.sidecar_path()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    return {
        "record": record,
        "sidecar": sidecar,
        "record_path": str(record_path),
        "sidecar_path": str(sidecar_path),
    }


# --- 14. graph status (memory plane) ------------------------------------------


def _graph_freshness() -> str:
    """Call scripts/check_graphify_freshness.check() by file path (scripts/ is not a
    package). Any failure degrades to 'missing' — the memory plane is optional."""
    import importlib.util

    script = REPO_ROOT / "scripts" / "check_graphify_freshness.py"
    spec = importlib.util.spec_from_file_location("check_graphify_freshness", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check(REPO_ROOT)


@router.get("/graph/status")
def graph_status() -> dict:
    note = "Graphify is a memory/query layer — never a validator."
    try:
        status = _graph_freshness()
    except Exception:
        status = "missing"
    return {"status": status, "plane": "memory", "note": note}


# --- 15. uploads (always blocked) ---------------------------------------------


@router.post("/uploads")
def uploads():
    # Governance seam: no multipart is declared or parsed; no file is read or stored.
    return JSONResponse(status_code=403, content=_UPLOAD_BLOCKED)

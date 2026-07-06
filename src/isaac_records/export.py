"""Transform a draft into an official ISAAC record + an evidence sidecar.

The record conforms to the official schema (no envelope, no evidence keys — the
schema is `additionalProperties: false`). The sidecar preserves the auditability
the record cannot carry: it maps official JSON-paths (and asset/descriptor/implicit
keys) to the evidence collected during drafting.

Export is validation-gated: it refuses unless the draft passes no-guessing checks
AND the produced record passes the official schema.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .draft_validator import DraftReport, validate_draft
from .ids import is_record_id, new_record_id
from .official import OfficialReport, validate_official

ISAAC_VERSION = "1.05"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_path(obj: dict, dotted: str, value) -> None:
    """Set a nested object path (dotted, no array indices), creating dicts."""
    parts = dotted.split(".")
    node = obj
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def get_path(obj, dotted: str):
    node = obj
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def strip_evidence(node):
    """Deep-copy a structured block with every 'evidence' key removed, so it
    conforms to the official schema (which forbids unknown keys)."""
    if isinstance(node, dict):
        return {k: strip_evidence(v) for k, v in node.items() if k != "evidence"}
    if isinstance(node, list):
        return [strip_evidence(v) for v in node]
    return node


def transform(draft: dict, *, record_id: str | None = None, now: str | None = None) -> dict:
    """Build the official-shape record from a draft (no validation here)."""
    now = now or _now_iso()
    meta = draft.get("meta") or {}
    record: dict = {
        "isaac_record_version": ISAAC_VERSION,
        "record_id": record_id or new_record_id(),
    }
    for key in ("record_type", "record_domain", "source_type"):
        if meta.get(key) is not None:
            record[key] = meta[key]

    # Scalar fields: drop the envelope, keep the value. Skip honestly-missing fields.
    for path, env in (draft.get("fields") or {}).items():
        if not isinstance(env, dict):
            continue
        if env.get("status") == "missing" or env.get("value") is None:
            continue
        set_path(record, path, env["value"])

    # Timestamps: created_utc is required by the schema — default to now.
    record.setdefault("timestamps", {})
    record["timestamps"].setdefault("created_utc", now)

    # Structured blocks copied verbatim, evidence keys stripped.
    if draft.get("series"):
        record.setdefault("measurement", {})["series"] = strip_evidence(draft["series"])
        if draft.get("qc"):
            record["measurement"]["qc"] = strip_evidence(draft["qc"])
        elif "qc" not in record["measurement"]:
            record["measurement"]["qc"] = {"status": "valid"}
    if draft.get("assets"):
        record["assets"] = [strip_evidence(a) for a in draft["assets"]]
    if draft.get("descriptors_outputs"):
        record["descriptors"] = {"outputs": strip_evidence(draft["descriptors_outputs"])}
    if draft.get("links") is not None:
        record["links"] = strip_evidence(draft["links"])
    if draft.get("attribution"):
        record["attribution"] = strip_evidence(draft["attribution"])
    if draft.get("tags"):
        record["tags"] = list(draft["tags"])

    return record


def build_sidecar(draft: dict, record: dict) -> dict:
    """Evidence map keyed by official JSON-path / asset / descriptor / implicit."""
    ev: dict = {}
    for path, env in (draft.get("fields") or {}).items():
        if isinstance(env, dict) and env.get("evidence") and env.get("value") is not None:
            ev[path] = env["evidence"]
    for asset in draft.get("assets") or []:
        if asset.get("evidence"):
            ev[f"assets:{asset.get('asset_id', asset.get('uri', '?'))}"] = asset["evidence"]
    for out in draft.get("descriptors_outputs") or []:
        for d in out.get("descriptors") or []:
            if d.get("evidence"):
                ev[f"descriptors:{d.get('name', '?')}"] = d["evidence"]
    for imp in draft.get("implicit") or []:
        ev[f"implicit:{imp.get('about', '?')}"] = {
            "value": imp.get("value"),
            "evidence": imp.get("evidence", []),
        }
    return {
        "record_id": record["record_id"],
        "schema_version": ISAAC_VERSION,
        "generated_utc": _now_iso(),
        "evidence": ev,
    }


@dataclass
class ExportResult:
    ok: bool
    record: dict | None
    sidecar: dict | None
    draft_report: DraftReport
    official_report: OfficialReport | None


def export_draft(
    draft: dict,
    root: Path,
    *,
    record_id: str | None = None,
    now: str | None = None,
) -> ExportResult:
    draft_report = validate_draft(draft)
    if record_id is not None and not is_record_id(record_id):
        draft_report.err("record_id", f"{record_id!r} is not a valid ULID (^[0-9A-Z]{{26}}$)")
    if not draft_report.ok:
        return ExportResult(False, None, None, draft_report, None)

    record = transform(draft, record_id=record_id, now=now)
    official_report = validate_official(record, root)
    if not official_report.ok:
        return ExportResult(False, record, None, draft_report, official_report)

    sidecar = build_sidecar(draft, record)
    return ExportResult(True, record, sidecar, draft_report, official_report)

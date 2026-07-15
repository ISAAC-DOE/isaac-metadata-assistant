"""Read-only JSON serializers for core dataclasses and draft structures.

The core (``draft_validator``, ``official``, ``portal_warnings``, ``export``, ``audit``)
exposes ``.render()`` and typed fields but no ``.to_dict()`` — by design (see
docs/ui-handoff/technical-architecture.md §11). This module owns ALL serialization so
no method is added to a core dataclass. It never re-implements a verdict: it only reshapes
what the core returned.

Serialization rules honored here (technical-architecture.md §3 / §9):
  - ``DraftReport.errors`` is ``[(where, msg)]``  -> ``{where, message}``.
  - ``OfficialReport.errors`` is ``[OfficialError(path, message)]`` -> ``{path, message}``.
  - ``PortalWarningReport`` exposes only ``.warnings`` + ``.advisory`` — the warning payload
    carries ``advisory:true, gating:false`` and NO ok/valid/passed field.
"""

from __future__ import annotations

from isaac_records.draft_validator import OBSERVED_SOURCE_TYPES, DraftReport
from isaac_records.export import ExportResult, get_path
from isaac_records.official import OfficialReport
from isaac_records.portal_warnings import PortalWarningReport

# --- report serializers -------------------------------------------------------


def draft_report_to_dict(report: DraftReport) -> dict:
    return {
        "ok": report.ok,
        "errors": [{"where": w, "message": m} for w, m in report.errors],
        "warnings": [{"where": w, "message": m} for w, m in report.warnings],
    }


def official_report_to_dict(report: OfficialReport) -> dict:
    return {
        "ok": report.ok,
        "errors": [{"path": e.path, "message": e.message} for e in report.errors],
    }


def warnings_to_dict(report: PortalWarningReport) -> dict:
    """Advisory, non-gating channel. Deliberately NO ok/valid/passed field."""
    return {
        "advisory": True,
        "gating": False,
        "warnings": [
            {"code": w.code, "where": w.where, "message": w.message}
            for w in report.warnings
        ],
    }


def export_result_to_dict(result: ExportResult) -> dict:
    """Serialize an ExportResult (reports always; record/sidecar when produced)."""
    out: dict = {
        "ok": result.ok,
        "draft_report": draft_report_to_dict(result.draft_report),
        "official_report": (
            official_report_to_dict(result.official_report)
            if result.official_report is not None
            else None
        ),
    }
    if result.record is not None:
        out["record"] = result.record
    if result.sidecar is not None:
        out["sidecar"] = result.sidecar
    return out


def audit_to_dict(results, text: str) -> dict:
    """``audit_records`` returns [(name, OfficialReport, (covered, expected, uncovered, dangling))].

    Coverage is completeness reporting, never a verdict: ``evidence_present`` /
    ``evidence_expected`` are the honest record-derived denominator, and the
    ``uncovered`` / ``dangling`` key lists are passed through faithfully.
    """
    records = []
    for name, report, (covered, expected, uncovered, dangling) in results:
        records.append(
            {
                "name": name,
                "ok": report.ok,
                "schema_errors": [
                    {"path": e.path, "message": e.message} for e in report.errors
                ],
                "evidence_present": covered,
                "evidence_expected": expected,
                "uncovered": list(uncovered),
                "dangling": list(dangling),
            }
        )
    return {"records": records, "text": text}


# --- draft field grouping -----------------------------------------------------

# Draft ``fields`` keys are official dotted JSON-paths (verified against
# docs/samples/…evidence.json). We group by the top-level path segment into stable,
# human-titled sections. Order is fixed; any unmapped prefix lands in "Other".
_GROUP_TITLES: dict[str, str] = {
    "system": "System & Instrument",
    "timestamps": "Timestamps",
    "sample": "Sample",
    "context": "Environment & Context",
    "measurement": "Measurement",
    "assets": "Assets & Files",
    "descriptors": "Descriptors",
    "attribution": "Attribution",
}
_GROUP_ORDER = list(_GROUP_TITLES.keys())
_OTHER = "Other"


def _label(path: str) -> str:
    """Humanize the last path segment (e.g. ``sample.material.formula`` -> ``Formula``)."""
    last = path.split(".")[-1]
    return last.replace("_", " ").strip().title()


def _source_types(evidence) -> list[str]:
    seen: list[str] = []
    for e in evidence or []:
        st = e.get("source_type") if isinstance(e, dict) else None
        if st and st not in seen:
            seen.append(st)
    return seen


def _draft_field(path: str, env: dict) -> dict:
    evidence = env.get("evidence") or []
    return {
        "path": path,
        "label": _label(path),
        "value": env.get("value"),
        "status": env.get("status"),
        "evidence_count": len(evidence),
        "source_types": _source_types(evidence),
    }


def draft_to_groups(draft: dict) -> dict:
    """Group draft scalar fields into stable UI sections for the Review Record screen."""
    fields = draft.get("fields") or {}
    buckets: dict[str, list[dict]] = {}
    for path, env in fields.items():
        if not isinstance(env, dict):
            continue
        top = path.split(".")[0]
        title = _GROUP_TITLES.get(top, _OTHER)
        buckets.setdefault(title, []).append(_draft_field(path, env))

    ordered_titles = [
        _GROUP_TITLES[k] for k in _GROUP_ORDER if _GROUP_TITLES[k] in buckets
    ]
    if _OTHER in buckets:
        ordered_titles.append(_OTHER)

    groups = [{"title": t, "fields": buckets[t]} for t in ordered_titles]
    return {"groups": groups}


# --- pending blockers ---------------------------------------------------------

_DEMO_LABEL = "Demo answer (synthetic)"


def _demo_answer_for(entry: dict, demo_answers: dict):
    """Return the labeled demo suggestion for a blocker, or None. Never auto-applied."""
    kind = entry.get("kind")
    if kind == "asset":
        value = (demo_answers.get("asset_sha256") or {}).get(entry.get("uri"))
    elif kind == "series":
        value = demo_answers.get("series")
    elif kind == "descriptor":
        value = demo_answers.get("descriptor")
    else:
        value = None
    if value is None:
        return None
    return {"value": value, "label": _DEMO_LABEL}


def blocker_id(entry: dict) -> str:
    """Stable id used as the answer key. Asset blockers key on their URI."""
    kind = entry.get("kind")
    if kind == "asset":
        return entry.get("uri") or "asset"
    return kind or "blocker"


def _blocker_about(entry: dict):
    return entry.get("uri") or entry.get("blocker")


def pending_to_list(draft: dict, demo_answers: dict) -> dict:
    pending = []
    for entry in draft.get("pending") or []:
        pending.append(
            {
                "id": blocker_id(entry),
                "kind": entry.get("kind"),
                "question": entry.get("question"),
                "about": _blocker_about(entry),
                "demo_answer": _demo_answer_for(entry, demo_answers),
            }
        )
    return {"pending": pending}


# --- evidence trail -----------------------------------------------------------


def _status_from_evidence(evidence) -> str:
    """Derive a display status from evidence types (mirrors draft_validator semantics).

    An observed source (incl. user_confirmation) => verified; derivation-only => inferred.
    """
    types = {e.get("source_type") for e in (evidence or []) if isinstance(e, dict)}
    if types & set(OBSERVED_SOURCE_TYPES):
        return "verified"
    if "derivation" in types:
        return "inferred"
    return "verified"


def evidence_trail_from_draft(draft: dict) -> list[dict]:
    """Evidence trail for a not-yet-exported experiment: read the draft envelopes."""
    entries: list[dict] = []
    for path, env in (draft.get("fields") or {}).items():
        if not isinstance(env, dict):
            continue
        entries.append(
            {
                "path": path,
                "value": env.get("value"),
                "status": env.get("status"),
                "evidence": env.get("evidence") or [],
            }
        )
    for imp in draft.get("implicit") or []:
        entries.append(
            {
                "path": f"implicit:{imp.get('about', '?')}",
                "value": imp.get("value"),
                "status": _status_from_evidence(imp.get("evidence")),
                "evidence": imp.get("evidence") or [],
            }
        )
    for asset in draft.get("assets") or []:
        aid = asset.get("asset_id", asset.get("uri", "?"))
        entries.append(
            {
                "path": f"assets:{aid}",
                "value": asset.get("sha256"),
                "status": _status_from_evidence(asset.get("evidence")),
                "evidence": asset.get("evidence") or [],
            }
        )
    return entries


def evidence_trail_from_sidecar(sidecar: dict, record: dict) -> list[dict]:
    """Evidence trail for an exported experiment: read the real sidecar faithfully.

    Sidecar keys are official dotted paths, or ``assets:``/``descriptors:``/``implicit:``
    namespaced keys. ``implicit:`` values are ``{value, evidence}``; the rest are evidence
    lists. Values are resolved from the record so sha256s are visible post-export.
    """
    assets_by_id = {
        a.get("asset_id"): a for a in (record.get("assets") or []) if isinstance(a, dict)
    }
    entries: list[dict] = []
    for key, payload in (sidecar.get("evidence") or {}).items():
        if key.startswith("implicit:"):
            value = payload.get("value") if isinstance(payload, dict) else None
            evidence = payload.get("evidence") if isinstance(payload, dict) else payload
        else:
            evidence = payload
            if ":" in key:
                namespace, _, name = key.partition(":")
                if namespace == "assets":
                    value = (assets_by_id.get(name) or {}).get("sha256")
                else:
                    value = None
            else:
                value, _found = get_path(record, key)
        entries.append(
            {
                "path": key,
                "value": value,
                "status": _status_from_evidence(evidence),
                "evidence": evidence or [],
            }
        )
    return entries

"""Audit: validate every record in records/ against the official schema, and
report evidence-sidecar coverage.

Exact by construction (a loop over the deterministic validator), so completeness
questions get exact answers.
"""

from __future__ import annotations

import json
from pathlib import Path

from .export import get_path
from .official import OfficialError, OfficialReport, validate_official


def _sidecar_coverage(record: dict, sidecar_path: Path) -> tuple[int, int, list[str]]:
    """Return (resolved, total_pathlike, dangling) for a record's sidecar.

    Only dotted keys (no ':' prefix) are literal JSON-paths into the record;
    asset:/descriptors:/implicit: keys are namespaced and not checked here.
    """
    if not sidecar_path.exists():
        return (0, 0, [])
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    dangling: list[str] = []
    total = 0
    resolved = 0
    for key in (sidecar.get("evidence") or {}):
        if ":" in key:
            continue
        total += 1
        _, found = get_path(record, key)
        if found:
            resolved += 1
        else:
            dangling.append(key)
    return (resolved, total, dangling)


def audit_records(records_dir: Path, root: Path) -> list[tuple[str, OfficialReport, tuple]]:
    results = []
    for path in sorted(Path(records_dir).glob("*.json")):
        if path.name.endswith(".evidence.json"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report = OfficialReport([OfficialError(path.name, f"invalid JSON: {exc}")])
            results.append((path.name, report, (0, 0, [])))
            continue
        report = validate_official(record, root)
        sidecar = path.with_name(path.stem + ".evidence.json")
        coverage = _sidecar_coverage(record, sidecar)
        results.append((path.name, report, coverage))
    return results


def render_audit(results) -> str:
    if not results:
        return "No records found."
    lines = []
    failing = 0
    for name, report, (resolved, total, dangling) in results:
        verdict = "PASS" if report.ok else "FAIL"
        if not report.ok:
            failing += 1
        cov = f"evidence {resolved}/{total}" if total else "no sidecar"
        lines.append(f"{verdict}  {name}  ({len(report.errors)} schema errors, {cov})")
        for e in report.errors:
            lines.append(f"        {e.path} — {e.message}")
        for d in dangling:
            lines.append(f"        ⚠ sidecar path does not resolve: {d}")
    lines.append("")
    lines.append(f"{len(results)} records audited, {failing} failing official validation")
    return "\n".join(lines)

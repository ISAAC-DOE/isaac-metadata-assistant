"""Audit: run finalization-level validation over every record in records/.

This is deliberately a loop over the validator, not an agent: completeness
questions ("which records are missing raw-data URIs?") get exact answers.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .validator import ValidationReport, validate_record


def audit_records(
    records_dir: Path,
    schema: dict,
    vocabularies: dict[str, list[str]],
) -> list[tuple[str, ValidationReport]]:
    results: list[tuple[str, ValidationReport]] = []
    for path in sorted(Path(records_dir).glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report = ValidationReport()
            report.add("error", "PARSE", path.name, f"invalid JSON: {exc}")
            results.append((path.name, report))
            continue
        results.append((path.name, validate_record(record, schema, vocabularies, finalize=True)))
    return results


def render_audit(results: list[tuple[str, ValidationReport]]) -> str:
    if not results:
        return "No records found."
    lines = []
    code_counts: Counter[str] = Counter()
    for name, report in results:
        verdict = "PASS" if report.ok else "FAIL"
        lines.append(f"{verdict}  {name}  ({len(report.errors)} errors, {len(report.warnings)} warnings)")
        for issue in report.errors:
            lines.append(f"       {issue.code:<26} {issue.path} — {issue.message}")
            code_counts[issue.code] += 1
    failed = sum(1 for _, r in results if not r.ok)
    lines.append("")
    lines.append(f"{len(results)} records audited, {failed} failing")
    if code_counts:
        lines.append("Error counts: " + ", ".join(f"{c}×{code}" for code, c in code_counts.most_common()))
    return "\n".join(lines)

"""Audit: validate every record in records/ against the official schema, and
report evidence-sidecar coverage.

Exact by construction (a loop over the deterministic validator), so completeness
questions get exact answers.

Coverage is an HONEST expected-vs-covered model: the denominator is enumerated
from RECORD content — every scalar leaf reachable by dict-only traversal, plus one
block target per series / qc / link / asset / descriptor / contributor — not from
the sidecar's own keys. A record whose spectrum, qc verdict, or contributors carry
no evidence therefore cannot audit at full coverage, and evidence claiming objects
the record does not have surfaces as dangling. Coverage is completeness reporting,
never a pass/fail verdict; official validation is separate.
"""

from __future__ import annotations

import json
from pathlib import Path

from .export import get_path
from .official import OfficialError, OfficialReport, validate_official

# Top-level identity/classification leaves are record-keeping, not evidenced claims.
_EXCLUDE_TOP = {
    "isaac_record_version",
    "record_id",
    "record_type",
    "record_domain",
    "source_type",
}
# Dotted subtrees/leaves that never contribute scalar targets. ``timestamps.created_utc``
# is system-stamped; ``tags`` are user-authored labels; ``measurement.qc`` is covered by
# the ``qc:status`` block target; ``attribution`` contributors are per-person block targets.
_EXCLUDE_PATHS = {
    "timestamps.created_utc",
    "tags",
    "measurement.qc",
    "attribution",
}


def _scalar_targets(record: dict) -> list[str]:
    """Leaf values reachable by DICT-ONLY traversal (never descend into lists),
    keyed by dotted path, minus the identity/system/label exclusions above."""
    out: list[str] = []

    def walk(node: dict, prefix: str) -> None:
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if prefix == "" and key in _EXCLUDE_TOP:
                continue
            if path in _EXCLUDE_PATHS:
                continue
            if isinstance(value, dict):
                walk(value, path)
            elif isinstance(value, list):
                continue  # lists are block territory, never scalar targets
            else:
                out.append(path)

    walk(record, "")
    return out


def _block_targets(record: dict) -> list[str]:
    """One natural-key block target per series / qc / link / asset / descriptor /
    contributor, constructed to match the producer's sidecar keying exactly (no
    escaping of ``|`` — a collision is an upstream duplicate-refusal, not our concern)."""
    out: list[str] = []
    measurement = record.get("measurement") or {}
    for series in measurement.get("series") or []:
        out.append(f"series:{series.get('series_id') or '?'}")
    if measurement.get("qc") is not None:
        out.append("qc:status")
    for link in record.get("links") or []:
        out.append(f"links:{link.get('rel')}|{link.get('target')}|{link.get('basis')}")
    for asset in record.get("assets") or []:
        out.append(f"assets:{asset.get('asset_id', asset.get('uri', '?'))}")
    for output in (record.get("descriptors") or {}).get("outputs") or []:
        for descriptor in output.get("descriptors") or []:
            out.append(f"descriptors:{descriptor.get('name', '?')}")
    for contributor in (record.get("attribution") or {}).get("contributors") or []:
        out.append(f"attribution:{contributor.get('name')}|{contributor.get('role')}")
    return out


def _sidecar_coverage(
    record: dict, sidecar_path: Path
) -> tuple[int, int, list[str], list[str]]:
    """Return (covered, expected, uncovered, dangling) for a record's sidecar.

    - expected: targets enumerated from the record (scalars + blocks).
    - covered: expected targets whose key is present in the sidecar evidence map.
    - uncovered: expected − covered, sorted for stable output.
    - dangling: (a) dotted sidecar keys that do not resolve into the record, plus
      (b) namespaced sidecar keys (excluding informational ``implicit:*``) that are
      not in the expected set — evidence claiming objects the record does not have.

    A missing sidecar file yields ``(0, expected, sorted(expected), [])`` — an honest
    0/N, not 0/0.
    """
    expected = _scalar_targets(record) + _block_targets(record)
    expected_set = set(expected)

    if not sidecar_path.exists():
        return (0, len(expected), sorted(expected), [])

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    evidence = sidecar.get("evidence") or {}
    present = set(evidence.keys())

    covered = sum(1 for key in expected if key in present)
    uncovered = sorted(key for key in expected if key not in present)

    dangling: list[str] = []
    for key in evidence:
        if ":" in key:  # namespaced (block / asset / descriptor / implicit)
            if key.startswith("implicit:"):
                continue  # informational: never expected, covered, or dangling
            if key not in expected_set:
                dangling.append(key)
        else:  # dotted record path
            _, found = get_path(record, key)
            if not found:
                dangling.append(key)

    return (covered, len(expected), uncovered, sorted(dangling))


def audit_records(records_dir: Path, root: Path) -> list[tuple[str, OfficialReport, tuple]]:
    results = []
    for path in sorted(Path(records_dir).glob("*.json")):
        if path.name.endswith(".evidence.json"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report = OfficialReport([OfficialError(path.name, f"invalid JSON: {exc}")])
            results.append((path.name, report, (0, 0, [], [])))
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
    for name, report, (covered, expected, uncovered, dangling) in results:
        verdict = "PASS" if report.ok else "FAIL"
        if not report.ok:
            failing += 1
        cov = f"evidence {covered}/{expected}" if expected else "no sidecar"
        lines.append(f"{verdict}  {name}  ({len(report.errors)} schema errors, {cov})")
        for e in report.errors:
            lines.append(f"        {e.path} — {e.message}")
        if uncovered:
            lines.append(f"        uncovered: {', '.join(uncovered)}")
        for d in dangling:
            lines.append(f"        ⚠ sidecar path does not resolve: {d}")
    lines.append("")
    lines.append(f"{len(results)} records audited, {failing} failing official validation")
    return "\n".join(lines)

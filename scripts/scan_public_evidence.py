#!/usr/bin/env python3
"""Structural allowlist + leak scan for a PUBLIC aggregate evidence artifact.

Runs against the EXACT file that will be committed, not against an in-memory
payload. That distinction is the whole point: a field can be dropped from the
served response and still reach the repository through a hand-written summary.

The allowlist is CLOSED. A key that is not enumerated is a failure, not a
warning -- the same fail-closed shape ``verification._project`` uses on the
success path. "It appeared in the endpoint payload" is explicitly NOT a reason
to publish; the approval that authorises this artifact enumerates the fields,
and this script is that enumeration made executable.

Exit codes: 0 clean, 1 violation. Prints every violation, not just the first.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# The closed allowlist. One entry per field the publication approval names.
# --------------------------------------------------------------------------
ALLOWED_KEYS: frozenset[str] = frozenset({
    "corpus_type", "record_count",
    "official_passing", "official_failing",
    "shadow_passing", "shadow_failing",
    "operators_defined",
    "trials_attempted", "trials_applicable", "trials_skipped_not_applicable",
    "expected_outcome_matches", "unexpected_outcomes", "observation_only_trials",
    "oracle_failures",
    "source_mutation_failures",
    "failures_by_error_code", "failures_by_schema_path",
    "cells", "suppressed_categories", "suppressed_total", "floor",
    "transaction_read_only", "dml_statements", "ddl_statements",
    "source_records_modified", "private_values_exposed",
    "official_validator_unchanged", "export_gating_unchanged",
    "parameterized_queries_only",
    "schema_version",
    "approximate_duration_seconds",
    "deterministic_rerun",
    "runs_compared", "deterministic_fields_identical", "volatile_fields_differed",
    "methodology", "limitations",
    # oracle sub-keys
    "restoration_failures", "repeatability_failures", "ordering_instability_failures",
    "no_guessing_failures", "workflow_consistency_failures", "engine_disagreements",
})

# Fields deliberately EXCLUDED even though they appear in the endpoint payload.
# Named so a future reader sees the omission was a decision, not an oversight.
DELIBERATELY_EXCLUDED = (
    "schema_fingerprint",   # hash of the vendored schema; not on the approved list
    "generated_at",         # exact timestamp; volatile and unnecessary
    "duration_ms",          # exact ms; published only as an approximate figure
    "cache_age_seconds",    # internal operational detail
    "verification_mode",    # internal mode token; corpus_type says it in prose
    "report_format_version",  # internal contract version
)

# --------------------------------------------------------------------------
# Content patterns that must never appear anywhere in the artifact.
# --------------------------------------------------------------------------
FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ULID / record identifier", r"\b[0-9A-HJKMNP-TV-Z]{26}\b"),
    ("sha256-shaped digest", r"\b[0-9a-f]{64}\b"),
    ("shorter hex digest", r"\b[0-9a-f]{32}\b"),
    ("RFC3339 timestamp", r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"),
    ("hostname / service topology", r"\b[a-z0-9-]+\.(?:svc|cluster|local|internal)\b"),
    ("libpq connection variable", r"\bPG(?:HOST|USER|PASSWORD|PORT|DATABASE|SSLMODE|PASSFILE|SSLKEY|SSLCERT)\b"),
    ("database name", r"\bmetadata_assistant\b"),
    ("connection URI", r"\b(?:postgres|postgresql)://"),
    ("IP address", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    ("bearer/credential token", r"\b(?:Bearer|password|secret|token)\s*[:=]"),
)


def _walk(value, path: str, out: list[tuple[str, object]]) -> None:
    if isinstance(value, dict):
        for key, sub in value.items():
            out.append((f"{path}.{key}", key))
            _walk(sub, f"{path}.{key}", out)
    elif isinstance(value, list):
        for index, sub in enumerate(value):
            _walk(sub, f"{path}[{index}]", out)


def scan_json(path: Path) -> list[str]:
    """Every key must be on the closed allowlist."""
    violations: list[str] = []
    payload = json.loads(path.read_text(encoding="utf-8"))
    keys: list[tuple[str, object]] = []
    _walk(payload, "", keys)
    for where, key in keys:
        if key not in ALLOWED_KEYS:
            violations.append(f"{path.name}: key not on the closed allowlist: {key!r} at {where}")
    return violations


def scan_text(path: Path) -> list[str]:
    """No forbidden content pattern may appear, in any file type."""
    violations: list[str] = []
    text = path.read_text(encoding="utf-8")
    for label, pattern in FORBIDDEN_PATTERNS:
        for match in re.finditer(pattern, text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(
                f"{path.name}:{line}: forbidden content ({label}): {match.group(0)[:40]!r}"
            )
    return violations


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: scan_public_evidence.py <file> [<file> ...]", file=sys.stderr)
        return 2

    violations: list[str] = []
    for raw in argv[1:]:
        path = Path(raw)
        if not path.is_file():
            print(f"FAIL: not a file: {path}", file=sys.stderr)
            return 2
        violations.extend(scan_text(path))
        if path.suffix == ".json":
            violations.extend(scan_json(path))

    print(f"scanned {len(argv) - 1} file(s)")
    print(f"closed allowlist: {len(ALLOWED_KEYS)} permitted keys")
    print(f"forbidden patterns: {len(FORBIDDEN_PATTERNS)}")
    print("deliberately excluded despite appearing in the endpoint payload: "
          + ", ".join(DELIBERATELY_EXCLUDED))

    if violations:
        print(f"\nFAIL — {len(violations)} violation(s):")
        for line in violations:
            print(f"  {line}")
        return 1

    print("\nOK — no allowlist violation, no forbidden content.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

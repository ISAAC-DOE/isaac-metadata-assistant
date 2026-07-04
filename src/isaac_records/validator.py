"""Deterministic validation for ISAAC records.

Rules enforced (all come from schema/isaac_record.schema.json, including its
x-field-rules block, so the schema stays the single source of truth):

- structure: JSON Schema Draft 2020-12
- evidence: a verified field needs observed evidence or user confirmation;
  an inferred field needs a derivation rule
- vocabulary: values on vocabulary-controlled fields must be allowed terms
- units: unit-bearing fields must carry a parseable unit of the right dimension
- raw data: linked by URI, never copied into the record
- finalization (--finalize / export / audit): every required field must be
  verified or inferred — never needs_confirmation, missing, or rejected
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Iterator

from jsonschema import Draft202012Validator
from pint import UnitRegistry

ERROR = "error"
WARNING = "warning"

FINAL_STATUSES = ("verified", "inferred")
OBSERVED_SOURCE_TYPES = (
    "document",
    "spreadsheet",
    "screenshot",
    "web_form",
    "file_listing",
    "user_confirmation",
)

_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://\S+$")
_ENVELOPE_KEYS = {"value", "status", "evidence"}
_UREG = UnitRegistry()


@dataclass
class Issue:
    level: str
    code: str
    path: str
    message: str

    def render(self) -> str:
        mark = "✗" if self.level == ERROR else "⚠"
        return f"{mark} {self.level:<7} {self.code:<26} {self.path} — {self.message}"


@dataclass
class ValidationReport:
    issues: list[Issue] = dc_field(default_factory=list)

    def add(self, level: str, code: str, path: str, message: str) -> None:
        self.issues.append(Issue(level, code, path, message))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = [i.render() for i in self.issues]
        verdict = "PASS" if self.ok else "FAIL"
        lines.append(f"{verdict} ({len(self.errors)} errors, {len(self.warnings)} warnings)")
        return "\n".join(lines)


def load_schema(root: Path) -> dict:
    schema_path = Path(root) / "schema" / "isaac_record.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def load_vocabularies(root: Path) -> dict[str, list[str]]:
    vocab_dir = Path(root) / "vocabulary"
    vocabularies: dict[str, list[str]] = {}
    if vocab_dir.is_dir():
        for path in sorted(vocab_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            vocabularies[data["field"]] = list(data["terms"])
    return vocabularies


def get_envelope(record: dict, dotted: str) -> dict | None:
    """Resolve a dotted path like 'technique.xas.edge' to its field envelope."""
    node = record
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


def iter_envelopes(node, prefix: str = "") -> Iterator[tuple[str, dict]]:
    """Yield (dotted_path, envelope) for every field envelope in the record."""
    if isinstance(node, dict):
        if _ENVELOPE_KEYS.issubset(node.keys()):
            yield prefix, node
            return
        for key, child in node.items():
            yield from iter_envelopes(child, f"{prefix}.{key}" if prefix else key)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            yield from iter_envelopes(child, f"{prefix}[{i}]")


def required_paths(schema: dict, record: dict | None = None, technique: str | None = None) -> list[str]:
    """Base required fields plus technique-conditional ones.

    The technique is taken from the record's technique.name value unless
    given explicitly. Matching is case-insensitive against the schema keys.
    """
    rules = schema.get("x-field-rules", {})
    paths = list(rules.get("required", []))
    if technique is None and record is not None:
        env = get_envelope(record, "technique.name")
        if env and isinstance(env.get("value"), str):
            technique = env["value"]
    if technique:
        for key, extras in rules.get("technique_requirements", {}).items():
            if key.lower() == technique.lower():
                paths.extend(p for p in extras if p not in paths)
    return paths


def validate_record(
    record: dict,
    schema: dict,
    vocabularies: dict[str, list[str]],
    *,
    finalize: bool = False,
) -> ValidationReport:
    report = ValidationReport()

    for err in sorted(
        Draft202012Validator(schema).iter_errors(record),
        key=lambda e: list(map(str, e.absolute_path)),
    ):
        path = ".".join(str(p) for p in err.absolute_path) or "$"
        report.add(ERROR, "SCHEMA", path, err.message)

    for path, env in iter_envelopes(record):
        status = env.get("status")
        value = env.get("value")
        entries = [e for e in (env.get("evidence") or []) if isinstance(e, dict)]

        if status == "missing" and value is not None:
            report.add(ERROR, "STATUS_VALUE_MISMATCH", path, "status is 'missing' but a value is present")
        if status in FINAL_STATUSES and value is None:
            report.add(ERROR, "STATUS_VALUE_MISMATCH", path, f"status is '{status}' but value is null")

        if status == "verified" and value is not None:
            if not any(e.get("source_type") in OBSERVED_SOURCE_TYPES for e in entries):
                report.add(
                    ERROR,
                    "EVIDENCE_MISSING",
                    path,
                    "verified field has no observed evidence or user confirmation",
                )
        if status == "inferred" and value is not None:
            if not any(e.get("source_type") == "derivation" and e.get("rule") for e in entries):
                report.add(
                    ERROR,
                    "EVIDENCE_MISSING",
                    path,
                    "inferred field has no derivation evidence with a stated rule",
                )
            elif not any(e.get("source_type") in OBSERVED_SOURCE_TYPES for e in entries):
                report.add(
                    WARNING,
                    "INFERRED_NO_SOURCE",
                    path,
                    "inferred field cites a rule but no observed evidence supporting it",
                )

    rules = schema.get("x-field-rules", {})

    for path, vocab_name in rules.get("vocabulary", {}).items():
        env = get_envelope(record, path)
        if env is None or env.get("value") is None:
            continue
        terms = vocabularies.get(vocab_name)
        if terms is None:
            report.add(WARNING, "VOCAB_FILE_MISSING", path, f"no vocabulary file for '{vocab_name}'")
        elif env["value"] not in terms:
            report.add(
                ERROR,
                "VOCAB_UNSUPPORTED",
                path,
                f"'{env['value']}' is not in the {vocab_name} vocabulary (allowed: {', '.join(terms)})",
            )

    for path, reference_unit in rules.get("units", {}).items():
        env = get_envelope(record, path)
        if env is None or env.get("value") is None:
            continue
        unit = env.get("unit")
        if not unit:
            report.add(ERROR, "UNIT_MISSING", path, f"value present but no unit (expected a {reference_unit}-compatible unit)")
            continue
        try:
            parsed = _UREG.Unit(unit)
        except Exception:
            report.add(ERROR, "UNIT_UNPARSEABLE", path, f"unit '{unit}' is not a recognized unit")
            continue
        if parsed.dimensionality != _UREG.Unit(reference_unit).dimensionality:
            report.add(
                ERROR,
                "UNIT_WRONG_DIMENSION",
                path,
                f"unit '{unit}' has the wrong dimension (expected compatible with {reference_unit})",
            )

    uris_env = get_envelope(record, "raw_data.uris")
    if uris_env is not None and uris_env.get("value") is not None:
        value = uris_env["value"]
        if not isinstance(value, list):
            report.add(ERROR, "RAW_DATA_NOT_URI", "raw_data.uris", "must be a list of URI strings")
        else:
            for i, item in enumerate(value):
                if not isinstance(item, str) or not _URI_RE.match(item):
                    report.add(
                        ERROR,
                        "RAW_DATA_NOT_URI",
                        f"raw_data.uris[{i}]",
                        "raw data must be linked by URI (scheme://...), never copied into the record",
                    )

    required = required_paths(schema, record)
    for path in required:
        env = get_envelope(record, path)
        if env is None and not finalize:
            report.add(WARNING, "REQUIRED_FIELD_ABSENT", path, "required field has no envelope yet")

    if finalize:
        for path in required:
            env = get_envelope(record, path)
            if env is None:
                report.add(ERROR, "FINALIZATION_INCOMPLETE", path, "required field is absent from the record")
                continue
            status = env.get("status")
            if status not in FINAL_STATUSES:
                report.add(
                    ERROR,
                    "FINALIZATION_INCOMPLETE",
                    path,
                    f"required field has status '{status}' — must be verified or inferred to finalize",
                )
            elif path == "raw_data.uris" and not env.get("value"):
                report.add(ERROR, "FINALIZATION_INCOMPLETE", path, "at least one raw-data URI is required to finalize")

    return report

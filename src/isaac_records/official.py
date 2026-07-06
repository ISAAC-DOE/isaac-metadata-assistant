"""Validation against the vendored official ISAAC schema.

The official schema (`schema/isaac_record_v1.json`, pinned v1.05) is the authority.
Because it is `additionalProperties: false` throughout, with inline enums and
if/then conditionals, plain JSON Schema validation already covers every hard
(HTTP-400) rule the official portal enforces — unknown blocks, bad vocabulary,
anti-pattern descriptor names, and the conditional required fields
(evidence⇒descriptors, performance+galvanostatic⇒current_setpoint, ...).

The soft-warning tier (NO_LINKS, MISSING_PH, ...) lives in the official
`portal/validation.py` and is intentionally not reimplemented here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

EXPECTED_VERSION = "1.05"


def schema_path(root: Path) -> Path:
    return Path(root) / "schema" / "isaac_record_v1.json"


@lru_cache(maxsize=8)
def _validator_for(path_str: str, mtime: float) -> Draft202012Validator:
    schema = json.loads(Path(path_str).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def load_official_validator(root: Path) -> Draft202012Validator:
    path = schema_path(root)
    return _validator_for(str(path), path.stat().st_mtime)


@dataclass
class OfficialError:
    path: str
    message: str

    def render(self) -> str:
        return f"✗ {self.path} — {self.message}"


@dataclass
class OfficialReport:
    errors: list[OfficialError]

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        if self.ok:
            return "PASS — valid against official ISAAC schema v" + EXPECTED_VERSION
        lines = [e.render() for e in self.errors]
        lines.append(f"FAIL ({len(self.errors)} schema errors)")
        return "\n".join(lines)


def validate_official(record: dict, root: Path) -> OfficialReport:
    validator = load_official_validator(root)
    errors = [
        OfficialError(
            path=".".join(str(p) for p in err.absolute_path) or "$",
            message=err.message,
        )
        for err in sorted(
            validator.iter_errors(record),
            key=lambda e: list(map(str, e.absolute_path)),
        )
    ]
    return OfficialReport(errors)

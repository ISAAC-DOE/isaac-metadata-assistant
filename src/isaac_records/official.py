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
def _checked_schema_text(path_str: str, mtime_ns: int, size: int) -> str:
    """Cache the expensive part: reading and PROVING the schema document valid.

    Only the immutable schema *text* is cached, never a validator or a parsed
    dict. ``check_schema`` is the costly step (~43 ms here); re-parsing the text
    and constructing a validator costs ~0.15 ms, so it is done per call. Note
    that is ~25x the old warm path (0.006 ms), and ``validate_official`` is ~35%
    slower as a result — cheap in absolute terms, but it is a real multiplier on
    a function called in loops, not free.

    The cache key is the path plus ``st_mtime_ns`` and ``st_size``. State the
    limit honestly rather than the guarantee: this catches a size change or a
    later clock tick, and it is strictly stronger than the float ``st_mtime`` it
    replaced — but it is a heuristic, NOT content identity. A replacement written
    in the same nanosecond tick AND of exactly the same byte length is still
    served from the stale entry. Closing that would mean hashing the file on
    every call, which is the cost this cache exists to avoid.
    """
    text = Path(path_str).read_text(encoding="utf-8")
    Draft202012Validator.check_schema(json.loads(text))
    return text


def load_official_validator(root: Path) -> Draft202012Validator:
    """Build a PRIVATE validator over the authoritative schema.

    Every call returns a fresh validator holding a freshly parsed schema dict.
    A caller may still mutate the object it was handed — Python cannot prevent
    that — but such a mutation is confined to that object and can never reach
    another caller or a later validation.
    """
    path = schema_path(root)
    stat = path.stat()
    return Draft202012Validator(
        json.loads(_checked_schema_text(str(path), stat.st_mtime_ns, stat.st_size))
    )


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

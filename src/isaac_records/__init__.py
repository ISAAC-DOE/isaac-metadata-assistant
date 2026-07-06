"""Deterministic core for ISAAC metadata records.

Two layers, both LLM-free:
  - draft authoring   — `models` + `draft_validator`: the no-guessing envelope format
  - export + validate — `export` (draft → official record + sidecar) and `official`
                        (validation against the vendored official schema, v1.05)

The official ISAAC schema is the source of truth; this package never redefines it.
"""

__version__ = "0.2.0"

from .draft_validator import DraftReport, validate_draft
from .export import ExportResult, build_sidecar, export_draft, transform
from .ids import is_record_id, new_record_id
from .models import derivation, evidence, field_value, user_confirmation
from .official import OfficialReport, validate_official

__all__ = [
    "DraftReport",
    "ExportResult",
    "OfficialReport",
    "build_sidecar",
    "derivation",
    "evidence",
    "export_draft",
    "field_value",
    "is_record_id",
    "new_record_id",
    "transform",
    "user_confirmation",
    "validate_draft",
    "validate_official",
]

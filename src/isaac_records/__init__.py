"""Deterministic core for ISAAC metadata records.

Validation, audit, and export are plain code with zero LLM involvement:
the trust rules of the project (no evidence → no finalized field) are
enforced here, not by prompts.
"""

__version__ = "0.1.0"

from .models import derivation, evidence, field_value, user_confirmation
from .validator import (
    ValidationReport,
    load_schema,
    load_vocabularies,
    validate_record,
)

__all__ = [
    "ValidationReport",
    "derivation",
    "evidence",
    "field_value",
    "load_schema",
    "load_vocabularies",
    "user_confirmation",
    "validate_record",
]

"""Phase-2 interface seam for XANES / characterization extraction (LOGIC-FREE).

This module defines *only* the typed contract that `/isaac-draft` extractors will
implement in Phase 3. It contains no parsing/extraction logic: every operation
raises `NotImplementedError`. The design these stubs seam is `docs/extraction.md`.

Isolation guarantees (mirroring the truth-path / advisory-review isolation):
  - it is NOT imported by `src/isaac_records/__init__.py`, so importing the
    deterministic core never pulls extraction in;
  - it does NOT import `graphify` (or anything else beyond the stdlib);
  - it does NOT touch export/validation/truth-path behavior.

An `ExtractedField` mirrors the draft envelope (`models.field_value`):
`{path, value, unit?, status, evidence[]}`, keyed by an official dotted
JSON-path. `status` uses the same vocabulary the draft layer accepts
(`verified | inferred | needs_confirmation | missing | rejected`); `evidence`
entries use the same `source_type` set the draft validator accepts
(`document | spreadsheet | screenshot | web_form | file_listing |
user_confirmation | derivation`). See `models.py` / `draft_validator.py`.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ArtifactKind(Enum):
    """The accepted intake artifact types (see docs/intake.md §2)."""

    XLSX = "xlsx"
    CSV = "csv"
    JSON = "json"
    FILE_LISTING = "file_listing"
    SCREENSHOT = "screenshot"
    PDF = "pdf"
    NOTES = "notes"


@dataclass(frozen=True)
class ExtractedField:
    """One extracted candidate, shaped like a draft field envelope.

    Attributes:
        path: official dotted JSON-path (e.g. ``system.facility.beamline``).
        value: the extracted value (``None`` for a ``missing`` field).
        status: one of ``verified | inferred | needs_confirmation | missing | rejected``.
        unit: optional unit string when the value is dimensional.
        evidence: tuple of evidence entries captured at extraction time
            (``models.evidence`` shape); empty only for a non-final field.
    """

    path: str
    value: Any
    status: str
    unit: str | None = None
    evidence: tuple = field(default_factory=tuple)


class Extractor(abc.ABC):
    """Abstract extractor for a single :class:`ArtifactKind`.

    Phase-3 subclasses implement :meth:`extract`. This base intentionally holds
    no logic — it is the interface seam only.
    """

    #: the artifact kind this extractor handles.
    kind: ArtifactKind

    @abc.abstractmethod
    def extract(self, path) -> list[ExtractedField]:
        """Extract candidate fields from the artifact at ``path``.

        Phase-2 stub: no logic here. Implemented in Phase 3, where a
        deterministic parser (xlsx/csv/json/file_listing) or an LLM-assisted
        reader (screenshot/pdf/notes) captures evidence at read time.
        """
        raise NotImplementedError("Extractor.extract lands in Phase 3 (docs/extraction.md)")


# Phase-3 deterministic parsers. Imported AFTER the seam types above so the
# sub-modules can `from . import ExtractedField` without a circular import. These
# import no LLM/network code and (via a lazy local import of openpyxl) do not force
# openpyxl at import time. Still NOT imported by `isaac_records/__init__.py`.
from .file_listing import AssetCandidate, archive_root, parse_file_listing
from .structured import FIELD_MAP, parse_contributors, parse_rows, parse_structured

__all__ = [
    "ArtifactKind",
    "ExtractedField",
    "Extractor",
    "AssetCandidate",
    "FIELD_MAP",
    "archive_root",
    "parse_contributors",
    "parse_file_listing",
    "parse_rows",
    "parse_structured",
]

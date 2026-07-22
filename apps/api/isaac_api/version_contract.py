"""Canonical version/optimistic-concurrency contract shared across the API.

Single source for the version envelope surfaced to clients, the non-noisy
missing-If-Match deprecation signal, and the ONE grace toggle. During the
P27.3/P27.4 one-release compatibility grace a missing If-Match is accepted and
flagged; the later strict slice (after the deployed frontend is verified sending
If-Match) flips `precondition_required()` to True so a missing precondition
becomes 428 — a single-point change, not a scattered edit.
"""
from __future__ import annotations
from pydantic import BaseModel

#: Non-noisy response header signalling a version-less (deprecated) mutation.
DEPRECATION_HEADER = "X-ISAAC-Deprecation"
DEPRECATION_VALUE = "if-match-required-next-release"

#: One-release compatibility grace. While False, a missing If-Match on a
#: mutation is accepted (and flagged with the deprecation header). The strict
#: slice flips this to True so missing -> 428. THIS IS THE SINGLE TOGGLE POINT.
_PRECONDITION_REQUIRED = False


def precondition_required() -> bool:
    """Whether a mutation MUST carry If-Match (strict) vs the one-release grace."""
    return _PRECONDITION_REQUIRED


class VersionEnvelope(BaseModel):
    """The typed version metadata surfaced on record reads + successful mutations."""
    rev: int
    updated_utc: str
    version: str


def version_fields(exp) -> dict:
    """The single producer of the {rev, updated_utc, version} envelope dict."""
    return {"rev": exp.rev, "updated_utc": exp.updated_utc, "version": exp.version_token()}

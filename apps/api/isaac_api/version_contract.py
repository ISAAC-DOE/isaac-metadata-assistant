"""Canonical version/optimistic-concurrency contract shared across the API.

Single source for the version envelope surfaced to clients and the ONE
precondition toggle. The P27.3/P27.4 one-release compatibility grace (missing
If-Match accepted + flagged) has been RETIRED: the deployed frontend is
hosted-verified to send `If-Match` on every mutation, so `precondition_required()`
now returns True — a mutation MUST carry a matching (or `*`) If-Match or it is
rejected 428. This stays a single-point contract, not a scattered edit.
"""
from __future__ import annotations
from pydantic import BaseModel

#: Preconditions are now MANDATORY (the one-release grace is retired). A missing
#: If-Match on a version-gated mutation is rejected 428. THIS IS THE SINGLE
#: TOGGLE POINT for the enforced state.
_PRECONDITION_REQUIRED = True


def precondition_required() -> bool:
    """Whether a mutation MUST carry If-Match. Now always True (grace retired)."""
    return _PRECONDITION_REQUIRED


class VersionEnvelope(BaseModel):
    """The typed version metadata surfaced on record reads + successful mutations."""
    rev: int
    updated_utc: str
    version: str


def version_fields(exp) -> dict:
    """The single producer of the {rev, updated_utc, version} envelope dict."""
    return {"rev": exp.rev, "updated_utc": exp.updated_utc, "version": exp.version_token()}

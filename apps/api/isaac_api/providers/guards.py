"""The no-guessing guards these seams must obey, REUSED rather than rewritten.

THE ONE THING THIS MODULE EXISTS TO PREVENT
===========================================
A second copy of the confidence-is-not-evidence rule. ``inferability.py`` already
decides that ``model_confidence``, ``heuristic_confidence``, ``statistical_prior``
and any ``confidence`` / ``probability`` / ``score`` key **anywhere in a tree** are
not evidence about a record. That rule was got wrong once already — its first
version scanned only the top level and therefore passed the exact nested shape
this repository's own corpus writes (``inferability._confidence_keys_in``'s
docstring records it). A second implementation here would be a second chance to
get it wrong, and worse, the two could diverge silently.

So this module **imports the existing rule and calls it**. It defines no key list
of its own. If ``inferability._CONFIDENCE_KEYS`` is widened, these seams tighten
with it; if it is emptied, these seams stop refusing — which is exactly the
coupling ``test_providers.py`` asserts, by emptying it and watching the refusal
disappear. A reimplementation would survive that test; reuse cannot.

WHY THE IMPORTED NAMES INCLUDE A PRIVATE ONE
============================================
``_confidence_keys_in`` is the recursive scanner. Re-walking the tree here with
the public ``_CONFIDENCE_KEYS`` constant would be a reimplementation of the part
that was historically wrong (the *recursion*, not the key list). Importing the
scanner is the narrower dependency, and ``inferability`` is a sibling module in
this same package, not a foreign API.

``inferability._check_evidence`` — the fuller guard — is deliberately NOT used,
and the reason is a design decision, not an oversight. It requires every entry to
carry a ``source_type`` drawn from ``RECORD_EVIDENCE_SOURCE_TYPES``. A capture
candidate carries none, because **no ISAAC source type describes a transcript**:
``src/isaac_records/models.py``'s ``SOURCE_TYPES`` is closed at seven, and adding
an eighth is a truth-core change under ``CLAUDE.md`` §13 that this slice does not
make. A candidate is therefore *pre-evidence*: it quotes what a human said and
waits for that human to confirm it, at which point the existing
``user_confirmation`` path — not this one — writes the evidence.

WHAT IS AND IS NOT IMPORTED FROM THE TRUTH PLANE
================================================
Nothing under ``providers/`` imports ``isaac_records`` directly; a source scan in
``test_providers.py`` enforces that. Stated honestly rather than absolutely:
``inferability`` itself imports two read-only CONSTANTS from the truth plane
(``draft_validator.OBSERVED_SOURCE_TYPES``) and one pure derivation helper, so a
transitive import exists. What does not exist, at any depth, is a call from these
seams into ``official.py``, ``export.py``, ``draft_validator``'s validators, or
``audit.py`` — nothing here can make a record valid, exportable, or written.
"""

from __future__ import annotations

from typing import Any

# The existing rule. Imported, never restated. See the module docstring for why a
# private name is among them.
from ..inferability import (  # noqa: F401  (NON_EVIDENCE_SOURCE_TYPES is re-exported)
    NON_EVIDENCE_SOURCE_TYPES,
    UnsupportedSuggestion,
    _confidence_keys_in,
)

__all__ = [
    "NON_EVIDENCE_SOURCE_TYPES",
    "UnsupportedSuggestion",
    "refuse_confidence_as_evidence",
    "refuse_non_evidence_source_type",
    "check_candidate_provenance",
]


def refuse_confidence_as_evidence(where: str, node: Any) -> None:
    """Raise if any confidence-like key appears anywhere in ``node``'s tree.

    Delegates the whole decision — the key set AND the recursion — to
    ``inferability._confidence_keys_in``. This function contributes the message,
    nothing else.
    """
    stray = _confidence_keys_in(node)
    if stray:
        raise UnsupportedSuggestion(
            f"{where}: carries {stray} — a confidence number is a claim about a "
            "predictor, not about this record. A model that is sure is still a "
            "model; only evidence or a person's confirmation makes a value real."
        )


def refuse_non_evidence_source_type(where: str, node: Any, _depth: int = 0) -> None:
    """Raise if any ``source_type`` in ``node``'s tree is a non-evidence type.

    The list is ``inferability.NON_EVIDENCE_SOURCE_TYPES``, unmodified. A capture
    candidate that labelled itself ``model_confidence`` or ``statistical_prior``
    would be asserting that a model's opinion is a source; it is not.

    Depth is bounded exactly as the imported scanner bounds itself; candidate
    provenance is a small hand-built mapping.
    """
    if _depth > 12:
        return
    if isinstance(node, dict):
        value = node.get("source_type")
        if isinstance(value, str) and value in NON_EVIDENCE_SOURCE_TYPES:
            raise UnsupportedSuggestion(
                f"{where}: source_type {value!r} is not record-specific evidence — "
                "it describes a model, a population, another record, or the schema, "
                "never this record"
            )
        for child in node.values():
            refuse_non_evidence_source_type(where, child, _depth + 1)
    elif isinstance(node, (list, tuple)):
        for item in node:
            refuse_non_evidence_source_type(where, item, _depth + 1)


def check_candidate_provenance(where: str, provenance: Any) -> None:
    """Both refusals, in the order a reader expects them. Raises or returns None."""
    refuse_confidence_as_evidence(where, provenance)
    refuse_non_evidence_source_type(where, provenance)

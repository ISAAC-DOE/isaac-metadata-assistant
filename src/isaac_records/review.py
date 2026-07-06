"""Stage 4: advisory AI scientific-consistency review (PLACEHOLDER INTERFACE).

This module defines the *seam* for a future Scientific Review Agent / Consistency
Review Agent. It is intentionally inert: the default `NoOpReviewer` returns no
findings, makes no LLM or Graphify call, and does not touch the record. Nothing in
the export/validation path imports this module, so it cannot change whether a record
is produced or considered valid.

Where it sits in the stack (see docs/proposal-v2.md §"Validation stack"):

    1. Draft no-guessing validation      (draft_validator.py)      — gates authoring
    2. Official ISAAC schema validation   (official.py)             — gates export
    3. Official portal/validation.py tier (upstream, when wired)    — soft warnings
    4. AI scientific consistency review   (this module)             — ADVISORY ONLY
    5. Human review of flagged issues                               — the decider

Hard guarantees this layer must always keep:
  - advisory only — it never marks a record officially valid or invalid;
  - it never replaces the schema validator or the official portal validator;
  - it never silently modifies records or overrides validation;
  - it runs only AFTER stages 1-3 have already decided validity.

A real implementation would subclass `Reviewer` and MAY consult Graphify for
similar-record comparison (passed in as `graph_context`) — but Graphify remains a
memory/context source here, never a source of truth.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum


class ReviewCategory(str, Enum):
    """What an advisory finding is about."""

    SCIENTIFIC_PLAUSIBILITY = "scientific_plausibility"
    RECORD_CONTEXT_CONSISTENCY = "record_context_consistency"
    DESCRIPTOR_TECHNIQUE_MISMATCH = "descriptor_technique_mismatch"
    MISSING_IMPORTANT_CONTEXT = "missing_important_context"
    POSSIBLE_OVERCLAIMING = "possible_overclaiming"
    SIMILAR_RECORD_COMPARISON = "similar_record_comparison"
    SUGGESTED_REVIEW_QUESTION = "suggested_review_question"


@dataclass(frozen=True)
class ReviewFinding:
    """One advisory observation. Never a pass/fail verdict."""

    category: ReviewCategory
    message: str
    where: str | None = None  # official JSON-path / block the finding concerns
    suggested_question: str | None = None  # a question to route to a human
    related_record_ids: tuple[str, ...] = ()  # from Graphify similar-record lookup, if any


@dataclass(frozen=True)
class ReviewReport:
    """Advisory result. Deliberately has NO .ok / .valid / .passed — this layer
    does not decide validity. `advisory` is always True and is a self-check."""

    findings: tuple[ReviewFinding, ...] = ()
    advisory: bool = True

    def render(self) -> str:
        if not self.findings:
            return "Advisory review: no findings. (Advisory only — does not affect validity.)"
        lines = ["Advisory review (does NOT affect official validity):"]
        for f in self.findings:
            loc = f" @ {f.where}" if f.where else ""
            lines.append(f"  • [{f.category.value}]{loc} {f.message}")
            if f.suggested_question:
                lines.append(f"      ↳ ask a human: {f.suggested_question}")
        return "\n".join(lines)


class Reviewer(abc.ABC):
    """Interface for a future advisory reviewer.

    Implementations MUST NOT mutate `record` and MUST return a `ReviewReport`
    (never a boolean verdict). `graph_context` is optional Graphify-derived context
    (e.g. similar records) — advisory input only, never authoritative.
    """

    @abc.abstractmethod
    def review(
        self,
        record: dict,
        *,
        sidecar: dict | None = None,
        graph_context: dict | None = None,
    ) -> ReviewReport:  # pragma: no cover - interface
        ...


class NoOpReviewer(Reviewer):
    """The default placeholder: reviews nothing, changes nothing."""

    def review(
        self,
        record: dict,
        *,
        sidecar: dict | None = None,
        graph_context: dict | None = None,
    ) -> ReviewReport:
        return ReviewReport(findings=())

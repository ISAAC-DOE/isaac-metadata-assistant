"""Seam 3 — a question plus grounded context becomes an answer.

THE NO-GUESSING RULE APPLIES TO THE ANSWER ITSELF
=================================================
``docs/ai-integration-decision-packet.md`` §6.4 is explicit that the no-guessing
rule binds the assistant's own answers, not only the fields it might propose. So
this seam is built around one structural commitment: **an answer must cite the
context items it used, and an answer with no citations cannot be constructed.**
:class:`AssistantAnswer` raises when ``grounded_in`` is empty. A question the
supplied context does not cover produces a :class:`ProviderRefusal`, never a
short paragraph composed from general knowledge.

That mirrors what the shipped deterministic assistant already does — an
unmatched question resolves to ``unsupported`` and the refusal *names what is
supported* (``assistant_query.py``) — rather than inventing a second, softer
policy for the model-backed path.

AN ANSWER IS NOT A VERDICT
==========================
:attr:`AssistantAnswer.authoritative` is a read-only ``False``. Nothing this seam
returns decides validity, exportability, or scientific correctness. The
established stack is unchanged: ``draft_validator`` then ``official`` then the
portal warning tier then advisory review then a human (``CLAUDE.md`` §3). This
seam is not even in that list; it answers questions about state a caller already
has, and the caller assembled the context.

WHAT THE CALLER SENDS IS THE CALLER'S DECISION, AND IT IS NOT MADE HERE
=======================================================================
:class:`ContextItem` exists so that "what did we send to the provider?" has an
answer that is a list, not a shrug. This module never fetches context: it cannot
read a record, a workspace, or a database. Whatever a future caller decides may
leave SLAC (decisions **D6**/**D8**, both DEFERRED) is passed in explicitly and
is visible in the request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Protocol, Union, runtime_checkable

from .base import (
    IMPLEMENTATION_DETERMINISTIC_FAKE,
    IMPLEMENTATION_UNCONFIGURED,
    SEAM_ASSISTANT,
)
from .refusal import (
    REASON_INPUT_NOT_SUPPLIED,
    REASON_OUTSIDE_GROUNDED_CONTEXT,
    ProviderRefusal,
    unconfigured_refusal,
)

__all__ = [
    "ContextItem",
    "AssistantRequest",
    "AssistantAnswer",
    "AssistantOutcome",
    "AssistantProvider",
    "UnconfiguredAssistantProvider",
    "DeterministicAssistantFake",
]


@dataclass(frozen=True)
class ContextItem:
    """One piece of grounding the caller chose to supply.

    ``key`` is how an answer cites it; ``text`` is what a provider would see;
    ``origin`` says where the caller got it, in the caller's own words.
    """

    key: str
    text: str
    origin: str

    def __post_init__(self) -> None:
        if not self.key or not self.text or not self.origin:
            raise ValueError(
                "a context item must have a key, text, and a stated origin — "
                "unattributed context is how an answer loses its grounding"
            )

    def to_dict(self) -> dict:
        return {"key": self.key, "text": self.text, "origin": self.origin}


@dataclass(frozen=True)
class AssistantRequest:
    """A question, and the ONLY material an answer may be built from."""

    question: str
    grounded_context: tuple[ContextItem, ...] = ()

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "grounded_context": [c.to_dict() for c in self.grounded_context],
        }


@dataclass(frozen=True)
class AssistantAnswer:
    """An answer, with the context keys it was built from. Never a verdict."""

    text: str
    #: The ``ContextItem.key`` values this answer used. **Never empty** — an
    #: uncited answer is refused at construction.
    grounded_in: tuple[str, ...]
    produced_by: str

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("an answer must say something")
        if not self.grounded_in:
            raise ValueError(
                "an answer must cite the context it used; an answer grounded in "
                "nothing is a guess, and this seam refuses instead"
            )

    @property
    def refused(self) -> bool:
        return False

    @property
    def authoritative(self) -> bool:
        """Always ``False``. This seam decides nothing about any record."""
        return False

    def to_dict(self) -> dict:
        return {
            "refused": False,
            "authoritative": False,
            "text": self.text,
            "grounded_in": list(self.grounded_in),
            "produced_by": self.produced_by,
        }


AssistantOutcome = Union[AssistantAnswer, ProviderRefusal]


@runtime_checkable
class AssistantProvider(Protocol):
    """Question + grounded context in, cited answer out — or a typed refusal."""

    SEAM: ClassVar[str]
    IMPLEMENTATION: ClassVar[str]
    PRODUCTION_CONFIGURED: ClassVar[bool]

    def status_reason(self) -> str: ...

    def answer(self, request: AssistantRequest) -> AssistantOutcome: ...


class UnconfiguredAssistantProvider:
    """The production default. Answers nothing and says so.

    Note what this does NOT do: it does not fall back to the shipped
    deterministic Q&A. That path exists, is reached through its own route, and
    already answers within its bounded catalog. Silently substituting it here
    would make "the model answered" and "the catalog answered" indistinguishable
    to the caller, which is the disclosure defect this project has shipped before.
    """

    SEAM: ClassVar[str] = SEAM_ASSISTANT
    IMPLEMENTATION: ClassVar[str] = IMPLEMENTATION_UNCONFIGURED
    PRODUCTION_CONFIGURED: ClassVar[bool] = False

    MISSING: ClassVar[tuple[str, ...]] = (
        "an approved model provider (decision D3)",
        "an institutional credential for it (decision D4)",
        "billing (decision D5)",
        "approved egress, retention terms and a data policy (decisions D6, D7, D8)",
    )

    def status_reason(self) -> str:
        return (
            "No language model is configured. Nothing typed here is sent to a "
            "model provider, because there is no model provider."
        )

    def answer(self, request: AssistantRequest) -> AssistantOutcome:
        return unconfigured_refusal(
            SEAM_ASSISTANT, missing=self.MISSING, what="answer with a language model"
        )


#: Word-ish tokens. Lower-cased, punctuation dropped. Used for containment only —
#: there is no scoring, no ranking, and therefore no confidence to leak.
_WORD = re.compile(r"[a-z0-9]+")

#: Tokens too common to constitute grounding. Without this, "the" in a question
#: would match every context item and the fake would appear to answer anything.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "any", "are", "as", "at", "be", "by", "did", "do",
        "does", "for", "from", "has", "have", "how", "in", "is", "it", "its",
        "of", "on", "or", "that", "the", "there", "this", "to", "was", "were",
        "what", "when", "where", "which", "who", "why", "with",
    }
)


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS)


class DeterministicAssistantFake:
    """A test double. Pure function of its input: no clock, no randomness, no I/O.

    The rule, in full: *a context item is used iff it shares at least one
    non-stopword token with the question.* Used items are quoted in the order the
    caller supplied them, and the answer is a fixed template. If no item shares a
    token, the double **refuses** — it has nothing to answer from, and answering
    anyway is exactly the behaviour this seam exists to make impossible.

    Deliberately unimpressive. A fake that appeared to reason would tempt someone
    to demonstrate it, and a demonstration of a fake is a fake demonstration.
    """

    SEAM: ClassVar[str] = SEAM_ASSISTANT
    IMPLEMENTATION: ClassVar[str] = IMPLEMENTATION_DETERMINISTIC_FAKE
    PRODUCTION_CONFIGURED: ClassVar[bool] = False

    def status_reason(self) -> str:
        return (
            "A deterministic test double is selected for the assistant seam. It "
            "quotes back the supplied context and refuses anything outside it."
        )

    def answer(self, request: AssistantRequest) -> AssistantOutcome:
        if not request.question or not request.question.strip():
            return ProviderRefusal(
                seam=SEAM_ASSISTANT,
                reason=REASON_INPUT_NOT_SUPPLIED,
                missing=("question",),
                message="No question was asked, so nothing is answered.",
            )
        asked = set(_tokens(request.question))
        used = [
            item for item in request.grounded_context if asked & set(_tokens(item.text + " " + item.key))
        ]
        if not used:
            return ProviderRefusal(
                seam=SEAM_ASSISTANT,
                reason=REASON_OUTSIDE_GROUNDED_CONTEXT,
                missing=("grounded context covering the question",),
                message=(
                    "The supplied context does not cover this question, so it is "
                    "not answered. The deterministic test double answers only "
                    "from context it was given: "
                    + (
                        ", ".join(item.key for item in request.grounded_context)
                        or "none was supplied"
                    )
                    + "."
                ),
            )
        body = " ".join(f"{item.key}: {item.text}" for item in used)
        return AssistantAnswer(
            text=(
                f"From the supplied context — {body} — and from nothing else. "
                "This is quoted context, not a judgement about the record."
            ),
            grounded_in=tuple(item.key for item in used),
            produced_by=IMPLEMENTATION_DETERMINISTIC_FAKE,
        )

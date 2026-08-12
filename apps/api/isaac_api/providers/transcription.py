"""Seam 1 — audio or a manually-typed transcript becomes transcript text.

WHAT A TRANSCRIPT IS, AND IS NOT
================================
A transcript is **text a human said**. It is not a measurement, not evidence, and
not a value. Nothing in this module produces an ISAAC field, and nothing it
produces may be treated as observed. The capture-extraction seam is the only
consumer, and all IT produces is candidates a scientist must confirm.

WHY THERE ARE NO TIMESTAMPS
===========================
:class:`TranscriptSegment` carries **character offsets into the transcript**, not
seconds into an audio stream. Two reasons, and the second is the load-bearing one:

1. Character offsets are computable from the text alone, so they are true of a
   typed transcript as well as a spoken one.
2. A time in seconds is a claim about the audio. When the input is a typed
   transcript there is no audio, and a fake that emitted plausible seconds would
   be inventing a measurement — the precise failure ``CLAUDE.md`` §5 forbids. A
   real provider that returns genuine timings can add a field for them; this seam
   does not pre-invent one to be filled with guesses.

AUDIO IS NEVER PERSISTED, AND THIS MODULE CANNOT PERSIST IT
===========================================================
Per DECISION D6 (``docs/superpowers/specs/2026-08-08-scientist-capture-data-contract.md``)
the honest v1 is transcript-only: audio never leaves the browser except to a
configured, approved provider, and there is nowhere on the server to keep it
anyway (``POST /api/uploads`` is an unconditional 403 and ``python-multipart`` is
not a dependency). Accordingly :class:`TranscriptionRequest` carries an
``audio_ref`` — an opaque handle a *future* provider would resolve — and never
bytes. This module opens no file, writes no file, and performs no network I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Protocol, Union, runtime_checkable

from .base import (
    IMPLEMENTATION_DETERMINISTIC_FAKE,
    IMPLEMENTATION_UNCONFIGURED,
    SEAM_TRANSCRIPTION,
)
from .refusal import (
    REASON_INPUT_NOT_SUPPLIED,
    ProviderRefusal,
    unconfigured_refusal,
)

__all__ = [
    "TranscriptionRequest",
    "TranscriptSegment",
    "TranscriptionResult",
    "TranscriptionOutcome",
    "TranscriptionProvider",
    "UnconfiguredTranscriptionProvider",
    "DeterministicTranscriptionFake",
]


@dataclass(frozen=True)
class TranscriptionRequest:
    """One transcription ask.

    Exactly one of ``audio_ref`` / ``manual_transcript`` is the real input;
    supplying neither is a refusal, not an empty result.
    """

    #: An opaque handle to audio held elsewhere (in the browser, today). NEVER
    #: bytes, and never a server path — nothing here reads a file.
    audio_ref: str | None = None
    #: Text a human typed instead of speaking. The only input a fake can honour.
    manual_transcript: str | None = None
    #: BCP-47 language tag the caller asserts. Advisory; nothing here detects one,
    #: because language detection is inference and this seam does not infer.
    language: str | None = None

    def to_dict(self) -> dict:
        return {
            "audio_ref": self.audio_ref,
            "manual_transcript": self.manual_transcript,
            "language": self.language,
        }


@dataclass(frozen=True)
class TranscriptSegment:
    """One contiguous span of the transcript, located by character offset."""

    index: int
    text: str
    start_char: int
    end_char: int

    def __post_init__(self) -> None:
        if self.start_char < 0 or self.end_char < self.start_char:
            raise ValueError("segment offsets must be a non-negative, ordered span")

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "text": self.text,
            "start_char": self.start_char,
            "end_char": self.end_char,
        }


@dataclass(frozen=True)
class TranscriptionResult:
    """A transcript, with its segmentation and its origin stated.

    ``verbatim`` records whether the text is exactly what the caller supplied
    (a typed transcript) or a provider's rendering of speech. A consumer that
    treats the two identically is free to; one that wants to know can ask.
    """

    text: str
    segments: tuple[TranscriptSegment, ...]
    #: Which implementation produced this. Reported, never inferred.
    produced_by: str
    #: ``True`` when the text is byte-identical to caller-supplied input.
    verbatim: bool
    language: str | None = None

    @property
    def refused(self) -> bool:
        """Always ``False``. The discriminator against :class:`ProviderRefusal`."""
        return False

    def to_dict(self) -> dict:
        return {
            "refused": False,
            "text": self.text,
            "segments": [s.to_dict() for s in self.segments],
            "produced_by": self.produced_by,
            "verbatim": self.verbatim,
            "language": self.language,
        }


#: What a call returns. A union, so a caller that ignores the refusal branch
#: fails type-checking rather than rendering an empty transcript as a real one.
TranscriptionOutcome = Union[TranscriptionResult, ProviderRefusal]


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Audio or typed text in, transcript out — or a typed refusal."""

    SEAM: ClassVar[str]
    IMPLEMENTATION: ClassVar[str]
    PRODUCTION_CONFIGURED: ClassVar[bool]

    def status_reason(self) -> str: ...

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionOutcome: ...


class UnconfiguredTranscriptionProvider:
    """The production default. Transcribes nothing and says so.

    It is not a stub awaiting completion: it is the correct implementation for a
    deployment with no approved transcription provider (decision **D9**, DEFERRED).
    """

    SEAM: ClassVar[str] = SEAM_TRANSCRIPTION
    IMPLEMENTATION: ClassVar[str] = IMPLEMENTATION_UNCONFIGURED
    PRODUCTION_CONFIGURED: ClassVar[bool] = False

    #: Named in every refusal. Each is an institutional decision, not a task.
    MISSING: ClassVar[tuple[str, ...]] = (
        "an approved transcription provider (decision D9)",
        "an institutional credential for it (decision D4)",
        "approved egress for speech leaving SLAC (decisions D6, D8)",
    )

    def status_reason(self) -> str:
        return (
            "No transcription provider is configured. Speech is not transcribed "
            "and no audio leaves the browser."
        )

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionOutcome:
        return unconfigured_refusal(
            SEAM_TRANSCRIPTION, missing=self.MISSING, what="transcribe speech"
        )


#: Sentence-ish boundary: terminal punctuation followed by whitespace. Fixed and
#: simple on purpose — a cleverer splitter would be a language model in disguise.
_SEGMENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class DeterministicTranscriptionFake:
    """A test double. Pure function of its input: no clock, no randomness, no I/O.

    Determinism is structural, not merely observed. This class holds no state, the
    only module-level object it touches is a compiled regex, and the output
    contains nothing that is not derived from ``request``. Two instances given the
    same request produce byte-identical ``to_dict()`` output.

    **It refuses audio.** Given an ``audio_ref`` and no ``manual_transcript`` it
    returns a refusal, because a fake cannot know what was said and words invented
    to fill the gap would be indistinguishable from a transcript. A test double
    whose failure mode is fabrication is worse than no test double.
    """

    SEAM: ClassVar[str] = SEAM_TRANSCRIPTION
    IMPLEMENTATION: ClassVar[str] = IMPLEMENTATION_DETERMINISTIC_FAKE
    PRODUCTION_CONFIGURED: ClassVar[bool] = False

    def status_reason(self) -> str:
        return (
            "A deterministic test double is selected for the transcription seam. "
            "It contacts nothing and only re-segments text the caller supplied."
        )

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionOutcome:
        text = request.manual_transcript
        if text is None or not text.strip():
            return ProviderRefusal(
                seam=SEAM_TRANSCRIPTION,
                reason=REASON_INPUT_NOT_SUPPLIED,
                missing=("manual_transcript",),
                message=(
                    "The deterministic test double transcribes nothing: it has no "
                    "model and no audio. It segments a transcript the caller "
                    "supplies, and refuses rather than inventing words for audio "
                    "it cannot hear."
                ),
            )
        return TranscriptionResult(
            text=text,
            segments=_segment(text),
            produced_by=IMPLEMENTATION_DETERMINISTIC_FAKE,
            verbatim=True,
            language=request.language,
        )


def _segment(text: str) -> tuple[TranscriptSegment, ...]:
    """Split on terminal punctuation, keeping true character offsets.

    Offsets are computed by scanning forward through the ORIGINAL string, so an
    offset always indexes back into ``text`` exactly. A segmenter whose offsets do
    not round-trip is a source of false quotes, and a quote is what a candidate
    stakes its provenance on.
    """
    pieces = [p for p in _SEGMENT_BOUNDARY.split(text) if p.strip()]
    segments: list[TranscriptSegment] = []
    cursor = 0
    for index, piece in enumerate(pieces):
        start = text.index(piece, cursor)
        end = start + len(piece)
        cursor = end
        segments.append(
            TranscriptSegment(index=index, text=piece, start_char=start, end_char=end)
        )
    return tuple(segments)

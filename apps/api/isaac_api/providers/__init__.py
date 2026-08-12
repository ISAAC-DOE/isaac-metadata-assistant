"""The three AI provider seams — implemented, tested, and wired to nothing.

READ THIS BEFORE ASSUMING ANYTHING ABOUT WHAT THIS PACKAGE DOES
===============================================================
It performs **no network I/O, no filesystem I/O, and no model call**, and it has
no dependency that could: no SDK, no HTTP client, nothing outside the standard
library and one sibling module. That is not a temporary state pending a
credential — it is the deliverable. Production is truthfully **unconfigured**.

The two facts behind that, both true, and collapsing them in either direction
misrepresents somebody (``docs/ai-integration-decision-packet.md``, header block):

* the infrastructure owner **deferred** AI integration — D1–D9 are unanswered;
* the project owner **elected to continue implementing** it against deterministic
  fakes.

Those are compatible because *implementation complete* and *production provider
configured* are different things. This package is the first. Building it creates
no connection, incurs no charge, sends nothing anywhere, and pre-empts none of
the deferred decisions.

THE THREE SEAMS, AND WHY THEY ARE THREE
=======================================
====================== =============================================== =========
Seam                   In → out                                        Decisions
====================== =============================================== =========
``transcription``      audio handle / typed text → transcript + spans  D9, D4, D6
``capture_extraction`` transcript / note text → **candidate** patches   D3, D4, D6
``assistant``          question + grounded context → a cited answer     D3–D8
====================== =============================================== =========

They are separate because approving one approves none of the others
(``…decision-packet.md`` §1.2): a transcription vendor is not a model provider,
and a model provider is not a transcription vendor. One seam can be wired without
silently authorising the rest.

THE INVARIANTS, IN ONE PLACE
============================
1. **The production default for every seam is unconfigured**, and it refuses
   **honestly** — a typed :class:`~.refusal.ProviderRefusal` naming what is
   missing. Not an exception (an unconfigured provider is the normal state, and
   exceptions get swallowed into blank screens); not a silent empty result (an
   empty transcript is a legitimate output of a *working* provider).
2. **Every extraction output is a candidate.** :class:`~.extraction.FieldCandidate`
   has no field for status, verification, evidence or acceptance; those are
   read-only constant properties on a frozen, slotted dataclass. Constructing one
   that presents as verified is a ``TypeError`` or an ``AttributeError``, not a
   code-review finding.
3. **Model confidence is not evidence.** The refusal is
   ``inferability._confidence_keys_in`` and ``inferability.NON_EVIDENCE_SOURCE_TYPES``,
   *imported and called* — see :mod:`.guards` for why reuse rather than a second
   copy, and ``test_providers.py`` for the test that fails if this package ever
   grows its own.
4. **No provider output enters the truth path.** Nothing here imports
   ``official.py``, ``export.py``, ``draft_validator.py``, ``audit.py`` or
   ``cli.py``; a source scan enforces it. A candidate becomes a value only
   through the existing ``POST /experiments/{id}/answers`` contract, with
   ``confirmed_by_user: true`` and a matching ``If-Match``.
5. **A transcript is text a human said, not a measurement.** Extraction proposes;
   a scientist disposes.

WHAT IS NOT HERE, DELIBERATELY
==============================
No route, no frontend, no dependency, no schema change, no migration. Nothing
serves :func:`~.config.capabilities` yet — it exists as the honest input a future
Settings surface would read, so that surface never has to compute "are we
connected?" for itself.

**Wiring status of the boot check, stated rather than implied:**
:func:`~.config.validate_provider_config_or_raise` is written for the top of
``create_app()`` and is **NOT called there in this slice**, which is new-files
only. Until it is called, a misconfigured container still boots (fail-closed, into
``unconfigured``) — the function refuses, the application does not yet consult it.
The one-line change and its consequence are in the slice report.
"""

from __future__ import annotations

from .assistant import (
    AssistantAnswer,
    AssistantOutcome,
    AssistantProvider,
    AssistantRequest,
    ContextItem,
    DeterministicAssistantFake,
    UnconfiguredAssistantProvider,
)
from .base import (
    IMPLEMENTATION_DETERMINISTIC_FAKE,
    IMPLEMENTATION_UNCONFIGURED,
    SEAM_ASSISTANT,
    SEAM_CAPTURE_EXTRACTION,
    SEAM_TRANSCRIPTION,
    SEAMS,
    ProviderImplementation,
)
from .config import (
    ASSISTANT_PROVIDER_ENV,
    CAPTURE_EXTRACTION_PROVIDER_ENV,
    PROVIDER_ENV_VARS,
    RECOGNISED_IMPLEMENTATIONS,
    TRANSCRIPTION_PROVIDER_ENV,
    capabilities,
    resolve_assistant_provider,
    resolve_capture_extraction_provider,
    resolve_transcription_provider,
    validate_provider_config_or_raise,
)
from .extraction import (
    CANDIDATE_STATUS,
    CaptureExtractionProvider,
    DeterministicCaptureExtractionFake,
    ExtractionOutcome,
    ExtractionRequest,
    ExtractionResult,
    FieldCandidate,
    ORIGIN_TRANSCRIPT,
    ORIGIN_TYPED_NOTE,
    UnconfiguredCaptureExtractionProvider,
)
from .guards import UnsupportedSuggestion
from .refusal import (
    DECISION_PACKET,
    REASON_INPUT_NOT_SUPPLIED,
    REASON_NO_PROVIDER_CONFIGURED,
    REASON_OUTSIDE_GROUNDED_CONTEXT,
    REFUSAL_REASONS,
    ProviderRefusal,
)
from .transcription import (
    DeterministicTranscriptionFake,
    TranscriptionOutcome,
    TranscriptionProvider,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegment,
    UnconfiguredTranscriptionProvider,
)

__all__ = [
    # seams + shared vocabulary
    "SEAMS",
    "SEAM_TRANSCRIPTION",
    "SEAM_CAPTURE_EXTRACTION",
    "SEAM_ASSISTANT",
    "IMPLEMENTATION_UNCONFIGURED",
    "IMPLEMENTATION_DETERMINISTIC_FAKE",
    "ProviderImplementation",
    # refusal
    "DECISION_PACKET",
    "ProviderRefusal",
    "REFUSAL_REASONS",
    "REASON_NO_PROVIDER_CONFIGURED",
    "REASON_INPUT_NOT_SUPPLIED",
    "REASON_OUTSIDE_GROUNDED_CONTEXT",
    "UnsupportedSuggestion",
    # transcription
    "TranscriptionRequest",
    "TranscriptSegment",
    "TranscriptionResult",
    "TranscriptionOutcome",
    "TranscriptionProvider",
    "UnconfiguredTranscriptionProvider",
    "DeterministicTranscriptionFake",
    # extraction
    "CANDIDATE_STATUS",
    "ORIGIN_TRANSCRIPT",
    "ORIGIN_TYPED_NOTE",
    "ExtractionRequest",
    "FieldCandidate",
    "ExtractionResult",
    "ExtractionOutcome",
    "CaptureExtractionProvider",
    "UnconfiguredCaptureExtractionProvider",
    "DeterministicCaptureExtractionFake",
    # assistant
    "ContextItem",
    "AssistantRequest",
    "AssistantAnswer",
    "AssistantOutcome",
    "AssistantProvider",
    "UnconfiguredAssistantProvider",
    "DeterministicAssistantFake",
    # config / status
    "PROVIDER_ENV_VARS",
    "RECOGNISED_IMPLEMENTATIONS",
    "TRANSCRIPTION_PROVIDER_ENV",
    "CAPTURE_EXTRACTION_PROVIDER_ENV",
    "ASSISTANT_PROVIDER_ENV",
    "resolve_transcription_provider",
    "resolve_capture_extraction_provider",
    "resolve_assistant_provider",
    "validate_provider_config_or_raise",
    "capabilities",
]

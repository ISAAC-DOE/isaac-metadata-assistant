"""Which implementation each seam gets, and the honest report of that.

MIRRORS ``runtime_mode.py`` DELIBERATELY, INCLUDING ITS ASYMMETRY
=================================================================
``runtime_mode`` splits one question into two functions, and the split is the
design:

* **Resolution never raises.** ``runtime_mode()`` always yields a usable, safe
  value; unset, empty, whitespace and garbage all fail closed. So does
  :func:`resolve_transcription_provider` and its two siblings — an accident can
  never grant a provider.
* **Detection of a misconfiguration is a separate job**, done once at boot by
  :func:`validate_provider_config_or_raise`, so a container configured for
  something this build cannot honour fails to construct rather than booting into
  a surprising state.

The asymmetry is copied too. ``runtime_mode`` *recognises* ``real`` as a valid
value and still refuses to boot in it, because the guardrails do not exist. Here,
``deterministic-fake`` is recognised — :func:`resolve_*` will return the fake, and
the test suite uses that mapping — but :func:`validate_provider_config_or_raise`
**refuses to boot with it**. DECISION D6 says the fake "exists for tests only and
is never reachable in production"; making that true means the application cannot
be started with one. Tests construct fakes directly, or via ``resolve_*``, which
is not a boot.

WHAT ``capabilities()`` MAY AND MAY NOT SAY
===========================================
It reports, per seam: the resolved implementation's name, ``configured``, and a
reason. ``configured`` is read off
:attr:`~.base.ProviderImplementation.PRODUCTION_CONFIGURED`, which **no class in
this package sets to True** — so the report cannot claim a provider exists. That
is a structural guarantee, tested two ways in ``test_providers.py`` (a runtime
walk of every class, and an AST scan of every source file).

``configured`` means *a production provider is wired and may be called*. The
deterministic fake reports ``False`` and is named in ``implementation``. Calling
a fake "configured" would put a word in front of a reader that they would
reasonably take to mean "a model is running" — and the fake answers none of the
decisions in ``docs/ai-integration-decision-packet.md`` §5, all of which are
DEFERRED. Disclosed, not hidden; and not promoted.

This function opens no connection, reads no credential, and performs no probe. It
is a projection of this build's own constants and three environment variables.
"""

from __future__ import annotations

import os

from .assistant import (
    AssistantProvider,
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
)
from .extraction import (
    CaptureExtractionProvider,
    DeterministicCaptureExtractionFake,
    UnconfiguredCaptureExtractionProvider,
)
from .transcription import (
    DeterministicTranscriptionFake,
    TranscriptionProvider,
    UnconfiguredTranscriptionProvider,
)

__all__ = [
    "PROVIDER_ENV_VARS",
    "RECOGNISED_IMPLEMENTATIONS",
    "TRANSCRIPTION_PROVIDER_ENV",
    "CAPTURE_EXTRACTION_PROVIDER_ENV",
    "ASSISTANT_PROVIDER_ENV",
    "capabilities",
    "resolve_assistant_provider",
    "resolve_capture_extraction_provider",
    "resolve_transcription_provider",
    "validate_provider_config_or_raise",
]

TRANSCRIPTION_PROVIDER_ENV = "ISAAC_TRANSCRIPTION_PROVIDER"
CAPTURE_EXTRACTION_PROVIDER_ENV = "ISAAC_CAPTURE_EXTRACTION_PROVIDER"
ASSISTANT_PROVIDER_ENV = "ISAAC_ASSISTANT_PROVIDER"

#: Seam -> the env var that selects its implementation. Fixed order.
PROVIDER_ENV_VARS: dict[str, str] = {
    SEAM_TRANSCRIPTION: TRANSCRIPTION_PROVIDER_ENV,
    SEAM_CAPTURE_EXTRACTION: CAPTURE_EXTRACTION_PROVIDER_ENV,
    SEAM_ASSISTANT: ASSISTANT_PROVIDER_ENV,
}

#: Every value this build understands. A value outside this set is a
#: configuration error at boot and resolves to ``unconfigured`` at runtime — the
#: two behaviours are different on purpose, exactly as in ``runtime_mode``.
RECOGNISED_IMPLEMENTATIONS: frozenset[str] = frozenset(
    {IMPLEMENTATION_UNCONFIGURED, IMPLEMENTATION_DETERMINISTIC_FAKE}
)

#: Seam -> {implementation name: class}. The unconfigured entry is the default
#: for every seam, and is what an unrecognised value falls back to.
_REGISTRY: dict[str, dict[str, type]] = {
    SEAM_TRANSCRIPTION: {
        IMPLEMENTATION_UNCONFIGURED: UnconfiguredTranscriptionProvider,
        IMPLEMENTATION_DETERMINISTIC_FAKE: DeterministicTranscriptionFake,
    },
    SEAM_CAPTURE_EXTRACTION: {
        IMPLEMENTATION_UNCONFIGURED: UnconfiguredCaptureExtractionProvider,
        IMPLEMENTATION_DETERMINISTIC_FAKE: DeterministicCaptureExtractionFake,
    },
    SEAM_ASSISTANT: {
        IMPLEMENTATION_UNCONFIGURED: UnconfiguredAssistantProvider,
        IMPLEMENTATION_DETERMINISTIC_FAKE: DeterministicAssistantFake,
    },
}


def _raw(seam: str) -> str | None:
    """The raw env value for a seam, or ``None`` when the var is unset."""
    return os.environ.get(PROVIDER_ENV_VARS[seam])


def _selected(seam: str) -> str:
    """Resolve a seam's implementation NAME, fail-closed. Never raises.

    Unset, empty, whitespace-only, and every unrecognised value all resolve to
    :data:`~.base.IMPLEMENTATION_UNCONFIGURED`. There is no case in which a typo
    turns a provider on.
    """
    raw = _raw(seam)
    if raw is None:
        return IMPLEMENTATION_UNCONFIGURED
    value = raw.strip()
    if value in RECOGNISED_IMPLEMENTATIONS:
        return value
    return IMPLEMENTATION_UNCONFIGURED


def _resolve(seam: str):
    return _REGISTRY[seam][_selected(seam)]()


def resolve_transcription_provider() -> TranscriptionProvider:
    """The transcription implementation for this environment. Fail-closed."""
    return _resolve(SEAM_TRANSCRIPTION)


def resolve_capture_extraction_provider() -> CaptureExtractionProvider:
    """The extraction implementation for this environment. Fail-closed."""
    return _resolve(SEAM_CAPTURE_EXTRACTION)


def resolve_assistant_provider() -> AssistantProvider:
    """The assistant implementation for this environment. Fail-closed."""
    return _resolve(SEAM_ASSISTANT)


def validate_provider_config_or_raise() -> None:
    """Raise ``RuntimeError`` for a misconfigured provider seam; else return.

    Intended for the top of ``create_app()``, beside
    ``runtime_mode.validate_runtime_mode_or_raise()``.

    Passes when every provider env var is unset or exactly ``unconfigured``.
    Raises when one is set to:

      * ``deterministic-fake`` — recognised, and refused: the fake is a test
        double and must not be reachable through a booted application
        (DECISION D6), or
      * any other value, including empty or whitespace-only — a configuration
        error. Refusing it is the point: silently falling back to
        ``unconfigured`` would leave an operator believing a provider they named
        is in use.

    Seams are checked in :data:`~.base.SEAMS` order so the message a
    misconfigured container prints is deterministic.
    """
    for seam in SEAMS:
        env_var = PROVIDER_ENV_VARS[seam]
        raw = _raw(seam)
        if raw is None:
            continue
        value = raw.strip()
        if value == IMPLEMENTATION_UNCONFIGURED:
            continue
        if value == IMPLEMENTATION_DETERMINISTIC_FAKE:
            raise RuntimeError(
                f"{env_var}='{IMPLEMENTATION_DETERMINISTIC_FAKE}' is refused: the "
                "deterministic provider is a test double and is not reachable "
                "through a running application. The test suite constructs it "
                f"directly. Unset {env_var} or set it to "
                f"'{IMPLEMENTATION_UNCONFIGURED}'."
            )
        raise RuntimeError(
            f"{env_var}={raw!r} is invalid. Expected "
            f"'{IMPLEMENTATION_UNCONFIGURED}' (unset defaults to it). No AI "
            "provider is implemented in this build; the outstanding decisions "
            "are recorded in docs/ai-integration-decision-packet.md §5."
        )


def capabilities() -> dict:
    """Per-seam status: implementation, ``configured``, and a reason.

    The honest input to a future Settings surface. Serializable, side-effect
    free, and safe to serve: every string is a constant from this package, and no
    environment VALUE is echoed back (only whether it resolved).
    """
    seams = []
    for seam in SEAMS:
        provider = _resolve(seam)
        # Read off the instance, never inferred from the class name or from the
        # env value. Nothing in this package sets this True.
        configured = bool(getattr(provider, "PRODUCTION_CONFIGURED", False))
        seams.append(
            {
                "seam": seam,
                "implementation": provider.IMPLEMENTATION,
                "configured": configured,
                "is_test_double": provider.IMPLEMENTATION
                == IMPLEMENTATION_DETERMINISTIC_FAKE,
                "reason": provider.status_reason(),
                "selected_by": PROVIDER_ENV_VARS[seam],
            }
        )
    return {
        "any_provider_configured": any(s["configured"] for s in seams),
        "decision_reference": "docs/ai-integration-decision-packet.md",
        "seams": seams,
    }

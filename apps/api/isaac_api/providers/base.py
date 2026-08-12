"""Shared vocabulary for the three provider seams.

The three seams — transcription, capture extraction, and the assistant — are
deliberately SEPARATE (``docs/ai-integration-decision-packet.md`` §1.2: approving
a transcription provider does not approve a model provider, and the reverse is
also true). This module holds only what all three must agree on, so that keeping
them separate stays cheap:

* the seam names, as constants, so a refusal and a capability report cannot
  disagree about what a seam is called;
* the ``PRODUCTION_CONFIGURED`` class flag that :func:`~.config.capabilities`
  reads — and the reason it is a class flag rather than a computed guess;
* the declaration that every seam's ``__call__`` returns *either* its own result
  type *or* a :class:`~.refusal.ProviderRefusal`, never ``None``.

THE ``PRODUCTION_CONFIGURED`` FLAG IS THE WHOLE HONESTY MECHANISM
=================================================================
``capabilities()`` does not infer "configured" from an env var, from a class
name, or from whether a call happens to succeed. It reads
:attr:`ProviderImplementation.PRODUCTION_CONFIGURED` off the resolved instance.
**No class in this package sets it ``True``**, and ``test_providers.py`` proves
that two ways: by walking every class in the package at runtime, and by parsing
every source file in it for the assignment. So the capability report cannot say
"configured" — not because the logic is careful, but because there is nothing for
it to be careful about. Wiring a real provider means writing a class that sets the
flag, which is a visible, reviewable act.

The deterministic fakes set it ``False`` as well, and that is not a fudge. A fake
contacts nothing, costs nothing, and answers no question in §5's decision list.
Reporting it as "configured" would put a true-looking word in front of a person
who would reasonably read it as "a model is running". The capability report names
the implementation separately, so the fake is disclosed rather than hidden.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

__all__ = [
    "SEAM_ASSISTANT",
    "SEAM_CAPTURE_EXTRACTION",
    "SEAM_TRANSCRIPTION",
    "SEAMS",
    "IMPLEMENTATION_UNCONFIGURED",
    "IMPLEMENTATION_DETERMINISTIC_FAKE",
    "ProviderImplementation",
]

SEAM_TRANSCRIPTION = "transcription"
SEAM_CAPTURE_EXTRACTION = "capture_extraction"
SEAM_ASSISTANT = "assistant"

#: Fixed order, used by :func:`~.config.capabilities` so its output is stable.
SEAMS: tuple[str, ...] = (SEAM_TRANSCRIPTION, SEAM_CAPTURE_EXTRACTION, SEAM_ASSISTANT)

#: The production default for every seam.
IMPLEMENTATION_UNCONFIGURED = "unconfigured"

#: The test double. Never reachable through a booted application — see
#: :func:`~.config.validate_provider_config_or_raise`, which refuses to boot when
#: an environment selects it, exactly as ``runtime_mode`` refuses ``real``.
IMPLEMENTATION_DETERMINISTIC_FAKE = "deterministic-fake"


@runtime_checkable
class ProviderImplementation(Protocol):
    """What every seam implementation declares about itself.

    ``Protocol`` rather than a base class on purpose: a future production
    provider may well be a thin adapter over a vendor SDK object and should not
    have to inherit anything from this package to be usable. What it must do is
    answer these three questions.
    """

    #: Which seam this implements. One of :data:`SEAMS`.
    SEAM: ClassVar[str]
    #: The implementation's own name, reported by ``capabilities()``.
    IMPLEMENTATION: ClassVar[str]
    #: ``True`` only for an implementation wired to a real, approved provider.
    #: Nothing in this package sets it ``True``; see the module docstring.
    PRODUCTION_CONFIGURED: ClassVar[bool]

    def status_reason(self) -> str:
        """One sentence for ``capabilities()``. Present indicative, no timeline."""
        ...

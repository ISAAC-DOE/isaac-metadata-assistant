"""The one refusal shape every provider seam returns when it cannot act.

WHY A VALUE AND NOT AN EXCEPTION
================================
An unconfigured provider is not an error condition. It is the **normal, correct,
expected** state of this build: the institutional endpoint, the credential and the
network path do not exist (``docs/ai-integration-decision-packet.md`` §5, D3–D9,
all DEFERRED). A state that is normal must not be signalled by an exception,
because exceptions get caught-and-logged and turn into a blank screen — and a
blank screen is indistinguishable from "the model had nothing to say".

Nor may it be a silent empty result. An empty transcript, an empty candidate list
and an empty answer are all *legitimate outputs* of a working provider. If refusal
shared a shape with success, every caller would have to guess which one it got —
and this repository has already shipped the consequence of that class of mistake
(``CLAUDE.md`` §11, the three false disclosure claims).

So refusal is a **typed value**, distinguishable by its own class, carrying the
name of what is missing. It is safe to render verbatim: every field is composed
from this module's own constants and the seam's name. No caller input, no
environment value, and no credential can reach a :class:`ProviderRefusal`.

WHAT A REFUSAL MAY NEVER DO
===========================
It may never imply that a provider exists, is reachable, is being retried, is
"temporarily" unavailable, or is warming up. ``docs/ai-integration-decision-packet.md``
§6.1 forbids a fake ``Connected`` state, and §9's closing line — *"build nothing
that implies any of it exists"* — is unaffected by the owner's decision to
continue implementing. The wording here is therefore in the present indicative
and names the decision that is outstanding, not a timeline.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DECISION_PACKET",
    "REFUSAL_REASONS",
    "REASON_NO_PROVIDER_CONFIGURED",
    "REASON_INPUT_NOT_SUPPLIED",
    "REASON_OUTSIDE_GROUNDED_CONTEXT",
    "ProviderRefusal",
    "unconfigured_refusal",
]

#: The committed document that records WHY each seam is unconfigured, and who
#: owns the decision. Quoted into every unconfigured refusal so a reader can find
#: the answer rather than being told to wait.
DECISION_PACKET = "docs/ai-integration-decision-packet.md"

#: No production provider is wired for this seam. The default state of this build.
REASON_NO_PROVIDER_CONFIGURED = "no_provider_configured"

#: The caller did not supply the input the seam needs, and the seam will not
#: invent it. (A transcription seam handed no audio and no transcript has nothing
#: to transcribe; producing words would be fabrication, not a fallback.)
REASON_INPUT_NOT_SUPPLIED = "input_not_supplied"

#: The question cannot be answered from the grounded context the caller supplied,
#: and the seam will not answer from anywhere else. Mirrors the deterministic
#: assistant's existing ``unsupported`` branch: refuse, naming what IS available.
REASON_OUTSIDE_GROUNDED_CONTEXT = "outside_grounded_context"

#: Frozen. A reason outside this set is a bug, and :class:`ProviderRefusal`
#: raises on one rather than rendering an unreviewed string to a human.
REFUSAL_REASONS: frozenset[str] = frozenset(
    {
        REASON_NO_PROVIDER_CONFIGURED,
        REASON_INPUT_NOT_SUPPLIED,
        REASON_OUTSIDE_GROUNDED_CONTEXT,
    }
)

#: Words a refusal message may never contain. Each one, in this position, would
#: assert something about a provider that does not exist: that it is there but
#: busy, that waiting will help, or that a connection was attempted. Checked at
#: construction, because a refusal string is a claim under test
#: (``CLAUDE.md`` §11, the ``upload-claim-parity`` lesson).
_FORBIDDEN_MESSAGE_SUBSTRINGS: tuple[str, ...] = (
    "temporarily",
    "try again",
    "retry",
    "reconnect",
    "connecting",
    "connected",
    "timed out",
    "timeout",
    "rate limit",
    "quota",
    "coming soon",
    "not yet available",
)


@dataclass(frozen=True)
class ProviderRefusal:
    """A seam declining to act, with the missing item named.

    ``refused`` is a constant ``True`` property rather than a field, so no caller
    can construct a refusal that claims not to be one, and no ``dict``-shaped copy
    of a success result can impersonate one by setting a flag.
    """

    #: ``"transcription"`` | ``"capture_extraction"`` | ``"assistant"``.
    seam: str
    #: One of :data:`REFUSAL_REASONS`.
    reason: str
    #: The concrete missing items, named. Never empty for a refusal — "something
    #: is missing" without saying what is the shape of an unhelpful error.
    missing: tuple[str, ...]
    #: A sentence safe to show a human. Present indicative; never a timeline.
    message: str
    #: Where the outstanding decision is recorded, for a reader who wants the why.
    decision_reference: str = DECISION_PACKET

    def __post_init__(self) -> None:
        if self.reason not in REFUSAL_REASONS:
            raise ValueError(
                f"unknown refusal reason {self.reason!r}; allowed: "
                f"{sorted(REFUSAL_REASONS)}"
            )
        if not self.missing:
            raise ValueError(
                f"{self.seam}: a refusal must name what is missing; an unnamed "
                "refusal is indistinguishable from a failure"
            )
        if not self.message:
            raise ValueError(f"{self.seam}: a refusal must explain itself")
        lowered = self.message.lower()
        for banned in _FORBIDDEN_MESSAGE_SUBSTRINGS:
            if banned in lowered:
                raise ValueError(
                    f"{self.seam}: refusal message contains {banned!r}, which "
                    "implies a provider exists and is momentarily unavailable. "
                    "No provider exists."
                )

    @property
    def refused(self) -> bool:
        """Always ``True``. The discriminator every caller branches on."""
        return True

    def to_dict(self) -> dict:
        return {
            "refused": True,
            "seam": self.seam,
            "reason": self.reason,
            "missing": list(self.missing),
            "message": self.message,
            "decision_reference": self.decision_reference,
        }


def unconfigured_refusal(seam: str, *, missing: tuple[str, ...], what: str) -> ProviderRefusal:
    """The standard refusal for a seam with no production provider wired.

    ``what`` names the capability in the user's terms ("transcribe audio", not
    "call the ASR endpoint"). The rest of the sentence is fixed here so the three
    seams cannot drift into three different levels of candour.
    """
    return ProviderRefusal(
        seam=seam,
        reason=REASON_NO_PROVIDER_CONFIGURED,
        missing=missing,
        message=(
            f"This build cannot {what}: no provider is configured for the "
            f"{seam} seam. Missing: {', '.join(missing)}. These are institutional "
            f"decisions recorded in {DECISION_PACKET}; the capability is built and "
            "tested, and it is not wired to anything."
        ),
    )

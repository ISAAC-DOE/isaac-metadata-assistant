"""Where the ISAAC Assistant artifact companion lives, if an operator has said so.

DISABLED BY DEFAULT, AND NOT A SWITCH SOMEBODY CAN FLIP IN CODE
==============================================================
There is no committed artifact URL in this repository and there must never be one.
A published artifact's URL identifies a specific account's specific artifact; in a
Team organisation it is also the thing that decides who can reach it. Committing
one would put an access-bearing identifier in a git history that outlives the
artifact, and would make an operator's visibility decision into a merge.

So the value arrives from the environment, the default resolves to
:class:`UnconfiguredArtifactLink`, and that object serves nothing. This mirrors
``mcp/deployment.py``'s ``UnconfiguredDeployment``, deliberately: the same problem
gets the same shape, and a reader who knows one knows this one.

DEEP LINK ONLY — EMBEDDING IS REFUSED HERE, NOT MERELY UNIMPLEMENTED
====================================================================
:func:`embed_markup` exists and always raises. That is the point of it.

The vendor documentation verified 2026-08-31 documents the ``Get embed code`` /
``Allowed domains`` flow under **"Embed artifacts"**, which follows **"Publish
artifacts"** and **"Who can access published artifacts"** — the *public* branch.
The **"Share artifacts within your organization"** branch documents no embedding at
all. Since ISAAC's requirement is an organization-private artifact, embedding it in
``isaac.slac.stanford.edu`` is **not documented as supported**, and the only
documented way to get an embeddable artifact is to publish it publicly.

**And publishing is not available for the artifact in question** — corrected
2026-09-01, because the earlier wording here framed it as a decision nobody had
taken, which reads as though someone could take it: *"Artifacts created on Team or
Enterprise accounts can only be shared within your organization—they cannot be
published publicly"*, and *"Publishing is available on Free, Pro, and Max plans."*
Publishing this companion from a **personal** account instead would forfeit the
organization-private property that was the requirement, and *that* is the visibility
decision nobody has made and an agent may not make. Either way the raise below is
correct; it now rests on availability first and authorization second.

A future author reaching for an ``<iframe>`` will find a raise and this paragraph
rather than a blank space that looks like an oversight. Evidence and the full
argument: ``docs/isaac-assistant-artifact-feasibility.md`` §4.

WHAT IS VALIDATED, AND WHY EACH CHECK IS THERE
==============================================
The URL is operator-supplied configuration, so it is checked the way configuration
is checked — fail closed, and never repeat the offending value back in an error,
because an operator who pastes the wrong string into the wrong variable should not
have it copied into a log.

THE THING THAT IS VALIDATED IS THE THING THAT IS STORED
=======================================================
Two defects found by independent review on 2026-08-31, recorded here because the
shape of each is more useful than the fix.

**The port was read outside the guard.** ``urlsplit`` does not validate a port
while parsing; it defers that to attribute access, so ``urlsplit(...).port`` raises
``ValueError`` for ``https://claude.ai:abc/x`` and ``https://claude.ai:99999/x``.
Reading it outside the ``try`` broke *both* of this module's stated contracts at
once: a caller catching :class:`ArtifactLinkRefusal` got an uncaught ``ValueError``
instead, and that ``ValueError``'s message **quotes the offending value** — the one
thing every refusal here is written to avoid. The guard now covers the attribute
access, which is where the parse actually happens.

**And validation ran on the parsed form while the raw form was stored.**
``urlsplit`` silently strips ASCII TAB, CR and LF before parsing, so
``"https://claude.ai/x\\r\\nLocation: https://evil.example"`` validated as host
``claude.ai`` and was then stored *with the CRLF intact*. Any consumer that does
not re-parse — an ``href``, a ``Location:`` header, a ``fetch`` — could resolve the
stored string differently from the string that was checked. That is the classic
URL-validation bypass, and it defeats the threat model above exactly.

**Both remedies are applied, and neither alone was enough.** A raw control
character is refused by name, *before* parsing, so the operator is told what is
wrong rather than having it quietly removed — refusal is the right posture for
configuration. And the accepted value is stored **re-serialised from the parsed
parts** rather than as pasted, so the string ISAAC serves is by construction the
string that was checked, whatever a future parser might decide to strip. Refusal
alone would leave the divergence class open to anything ``urlsplit`` learns to
ignore next; normalisation alone would silently rewrite an operator's value.
Normalisation also lowercases the host, which the permitted-host check already did
and the store previously did not.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "ARTIFACT_URL_ENV",
    "ArtifactLinkRefusal",
    "CONTROL_CHARACTERS",
    "ConfiguredArtifactLink",
    "UnconfiguredArtifactLink",
    "embed_markup",
    "resolve_artifact_link",
]

#: The one environment variable an operator sets. Named for what it is, so that a
#: grep for the feature finds the switch.
ARTIFACT_URL_ENV = "ISAAC_ASSISTANT_ARTIFACT_URL"

#: Hosts a companion artifact URL may name. A closed set rather than "any https
#: URL", because the failure mode of a typo'd host is that ISAAC sends its
#: scientists somewhere an attacker chose.
PERMITTED_ARTIFACT_HOSTS = frozenset({"claude.ai", "www.claude.ai"})

#: C0 controls and DEL. ``urlsplit`` strips TAB, CR and LF before parsing, so a
#: value carrying one would be *validated* in a form it is not *stored* in. These
#: are refused before parsing rather than stripped, because a configuration value
#: containing one is an operator mistake worth surfacing.
CONTROL_CHARACTERS = frozenset(chr(code) for code in range(0x20)) | {"\x7f"}


class ArtifactLinkRefusal(Exception):
    """A configured value was refused. Carries a reason, never the value."""


@dataclass(frozen=True)
class UnconfiguredArtifactLink:
    """The default. Serves no URL, and says what is missing rather than failing.

    It is not "disabled" in the sense of a feature a user could turn on. No
    configuration of this object produces a URL; an operator sets the environment
    variable and gets a :class:`ConfiguredArtifactLink` instead.
    """

    reason: str = "no artifact URL is configured"

    @property
    def is_configured(self) -> bool:
        return False

    @property
    def url(self) -> None:
        return None


@dataclass(frozen=True)
class ConfiguredArtifactLink:
    """An operator-supplied artifact URL that passed every check.

    ``url`` is the **normalised** form — re-serialised from the parsed parts, with
    the host lowercased — not the string as pasted. See the module docstring: what
    is validated and what is stored must be the same string.
    """

    url: str

    @property
    def is_configured(self) -> bool:
        return True


def _refuse(reason: str) -> ArtifactLinkRefusal:
    return ArtifactLinkRefusal(
        f"{ARTIFACT_URL_ENV} was refused: {reason}. The value is deliberately not "
        "repeated here."
    )


def resolve_artifact_link(
    env: "os._Environ[str] | dict[str, str] | None" = None,
) -> UnconfiguredArtifactLink | ConfiguredArtifactLink:
    """Resolve the companion artifact link from the environment.

    Returns :class:`UnconfiguredArtifactLink` when the variable is unset or empty —
    the default and the honest one. Raises :class:`ArtifactLinkRefusal` when a value
    is present but unusable, because a *present but wrong* value is an operator
    mistake that should be loud, while an *absent* one is the normal state.
    """
    environ = os.environ if env is None else env
    raw = (environ.get(ARTIFACT_URL_ENV) or "").strip()
    if not raw:
        return UnconfiguredArtifactLink()

    if any(character in CONTROL_CHARACTERS for character in raw):
        # Checked BEFORE parsing, on purpose. ``urlsplit`` would remove TAB, CR and
        # LF and hand back something that passes every check below while the value
        # the operator actually pasted still carries them.
        raise _refuse("it contains a control character")

    try:
        parts = urlsplit(raw)
    except ValueError as exc:  # pragma: no cover - urlsplit itself rarely raises
        raise _refuse("it is not a parseable URL") from exc

    if parts.scheme != "https":
        raise _refuse("the scheme is not https")
    if parts.username or parts.password:
        raise _refuse("it carries embedded credentials")

    try:
        port = parts.port
    except ValueError as exc:
        # ``urlsplit`` defers port validation to attribute access, and the
        # ``ValueError`` it raises QUOTES the offending value. Catching it here is
        # what keeps both contracts: a present-but-wrong value raises
        # ``ArtifactLinkRefusal``, and no refusal repeats what was pasted.
        raise _refuse("its port is not a number in the range 0-65535") from exc
    if port is not None:
        raise _refuse("it names an explicit port")

    host = (parts.hostname or "").lower()
    if host not in PERMITTED_ARTIFACT_HOSTS:
        raise _refuse("the host is not a permitted artifact host")
    if not parts.path or parts.path == "/":
        raise _refuse("it names no artifact path")
    if parts.query or parts.fragment:
        # A query or fragment on a deep link is where an Experiment ID would be
        # smuggled. No vendor documentation supports an artifact receiving one, so
        # accepting the shape would invite a caller to rely on behaviour nobody has
        # verified.
        raise _refuse("it carries a query string or fragment")

    # Re-serialised from the parts that were checked, never the string as pasted.
    # Query and fragment are empty by the refusal above; the host is the lowercased
    # one the allowlist matched, so what is stored cannot differ from what passed.
    return ConfiguredArtifactLink(url=urlunsplit(("https", host, parts.path, "", "")))


def embed_markup(*_args: object, **_kwargs: object) -> str:
    """Always raises. Embedding a private org-shared artifact is not supported.

    See this module's docstring and
    ``docs/isaac-assistant-artifact-feasibility.md`` §4. If Anthropic later
    documents embedding for organization-shared (non-public) artifacts, this
    function is where that capability lands — and it lands with the vendor sentence
    that authorises it quoted in its docstring.
    """
    raise ArtifactLinkRefusal(
        "embedding is refused: the vendor documentation verified 2026-08-31 "
        "documents the embed flow only for PUBLICLY published artifacts, and this "
        "companion is organization-private. ISAAC deep-links to it instead."
    )

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
documented way to get an embeddable artifact is to publish it publicly — which for
this companion is a visibility decision nobody has made and an agent may not make.

A future author reaching for an ``<iframe>`` will find a raise and this paragraph
rather than a blank space that looks like an oversight. Evidence and the full
argument: ``docs/isaac-assistant-artifact-feasibility.md`` §4.

WHAT IS VALIDATED, AND WHY EACH CHECK IS THERE
==============================================
The URL is operator-supplied configuration, so it is checked the way configuration
is checked — fail closed, and never repeat the offending value back in an error,
because an operator who pastes the wrong string into the wrong variable should not
have it copied into a log.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

__all__ = [
    "ARTIFACT_URL_ENV",
    "ArtifactLinkRefusal",
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
    """An operator-supplied artifact URL that passed every check."""

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

    try:
        parts = urlsplit(raw)
    except ValueError as exc:  # pragma: no cover - urlsplit is very permissive
        raise _refuse("it is not a parseable URL") from exc

    if parts.scheme != "https":
        raise _refuse("the scheme is not https")
    if parts.username or parts.password:
        raise _refuse("it carries embedded credentials")
    if parts.port is not None:
        raise _refuse("it names an explicit port")
    if (parts.hostname or "").lower() not in PERMITTED_ARTIFACT_HOSTS:
        raise _refuse("the host is not a permitted artifact host")
    if not parts.path or parts.path == "/":
        raise _refuse("it names no artifact path")
    if parts.query or parts.fragment:
        # A query or fragment on a deep link is where an Experiment ID would be
        # smuggled. No vendor documentation supports an artifact receiving one, so
        # accepting the shape would invite a caller to rely on behaviour nobody has
        # verified.
        raise _refuse("it carries a query string or fragment")

    return ConfiguredArtifactLink(url=raw)


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

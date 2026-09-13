"""Relative deep links an agent can hand a scientist. **MCP-006.**

THE GAP THIS CLOSES
===================
An agent that captures a note or records a proposal has to be able to say *where to
look*. Before this module there was nothing it could say: no ``?proposal=`` parameter
existed, so the best an agent could do was name an id and leave the scientist to find
the screen. A suggestion nobody can navigate to is a suggestion nobody reviews.

EVERY LINK IS RELATIVE, AND THAT IS THE LOAD-BEARING PROPERTY
=============================================================
The web router's ``basename`` is ``''`` locally and ``/krish`` in the deployed build,
and it is the ONE place that prefix is known. ``lib/routes.ts``' own doc-comments say
the same thing from the other side: the parameter value is the deep-linkable part
precisely *"so every link stays relative to the router `basename` … and no surface
ever writes a base path of its own"*.

**So this module writes no scheme, no host, no port, and no base path.** It emits a
path beginning with a single ``/`` and nothing before it. That is not timidity about
URLs — it is the only honest option available here:

* this process cannot know the public origin. It sits behind an Authentik edge and an
  ingress it cannot observe, and ``X-Isaac-Edge`` is **permanently disqualified** from
  witnessing edge traversal, so any host this module synthesised would be a guess.
* a guess that is wrong is worse than a relative path, because it looks clickable.
  A scientist handed ``http://localhost:8000/record/...`` by an agent has been sent
  somewhere that does not exist for them.

The cost is stated rather than hidden: **an agent cannot hand a scientist a bare
clickable URL from these values alone.** It can say "open ISAAC and go to
``/record/X?view=capture&proposal=Y``", which is navigable from inside the app the
scientist is already signed in to. Closing that gap needs a configured public base
URL, which is a deployment fact nobody has supplied — it is named residue, not an
oversight.

THE CONVENTION IS REUSED, NOT INVENTED
======================================
``?tab=`` (Settings, Governance, Statistics), ``?view=`` (record, evidence), ``?run=``
and ``?compare=`` are all one mechanism read with ``useSearchParams`` and written by
copying the existing ``URLSearchParams``. ``?proposal=`` is the next use of it, not a
new one. The literals here are the frontend's own — ``RECORD_VIEW_PARAM``/``'view'``,
``RECORD_RUN_PARAM``/``'run'``, ``RECORD_PROPOSAL_PARAM``/``'proposal'``, and the
``capture`` workspace id — and they are transcribed deliberately, because the
alternative is for Python to import TypeScript. :func:`link_literals` exists so a test
can hold the two copies against each other rather than trusting this paragraph.

NOTHING IS VALIDATED, AND NOTHING IS INVENTED
=============================================
An id is percent-encoded and placed in the query; it is never checked for existence,
because these functions are pure string builders with no workspace access, and a
"validated" link would make callers believe an existence check happened. A caller that
has just been handed an id by a route is holding an id the route accepted. An absent
id yields **no link at all** rather than a link with an empty parameter — a
``?proposal=`` with nothing after it would navigate to a screen claiming to focus
something and focus nothing.
"""

from __future__ import annotations

from typing import Mapping
from urllib.parse import quote

__all__ = [
    "AMBIGUITY_PARAM",
    "CAPTURE_VIEW",
    "PROPOSAL_PARAM",
    "RUN_PARAM",
    "VIEW_PARAM",
    "ambiguity_link",
    "capture_link",
    "experiment_link",
    "link_literals",
    "proposal_link",
    "run_link",
]

#: The frontend's `RECORD_VIEW_PARAM`. Transcribed; see :func:`link_literals`.
VIEW_PARAM = "view"
#: The frontend's `RECORD_RUN_PARAM`.
RUN_PARAM = "run"
#: The frontend's `RECORD_PROPOSAL_PARAM`, added for MCP-006.
PROPOSAL_PARAM = "proposal"
#: The record workspace that renders capture, notes and proposals — a member of the
#: frontend's `RECORD_VIEW_IDS`.
CAPTURE_VIEW = "capture"

#: The AMBIGUITY item parameter. **IT IS `PROPOSAL_PARAM`, ON PURPOSE, AND THAT IS A
#: FINDING RATHER THAN A SHORTCUT.**
#:
#: MCP-006 asks for a link to an "ambiguity item". Measured before writing one: this
#: build has **no separate ambiguity entity and no route that serves one**. What it
#: has is a proposal whose value the reader must disambiguate, reviewed on the same
#: screen, addressed by the same id. Minting a second parameter for it would publish a
#: navigational distinction the application does not make — a link that looked like it
#: opened a different surface and opened the same one.
#:
#: So :func:`ambiguity_link` is an ALIAS with its own name and its own docstring, kept
#: separate so that if an ambiguity ever becomes its own entity the change is one
#: function rather than a search for every caller who assumed it was a proposal.
AMBIGUITY_PARAM = PROPOSAL_PARAM


def _usable(value: object) -> bool:
    """A non-blank string — the only thing that may reach a URL from here."""
    return isinstance(value, str) and bool(value.strip())


def _record_path(experiment_id: str, **params: str | None) -> str | None:
    """``/record/<id>`` with the supplied query parameters, or ``None``.

    ``None`` when the experiment id is missing or blank, because every link here is a
    link to a record and there is no record to link to. Parameters whose value is
    ``None`` or blank are OMITTED rather than emitted empty — see the module
    docstring's last paragraph.

    **OMITTING A PARAMETER IS NOT THE SAME AS THE LINK STILL BEING CORRECT, AND THAT
    DISTINCTION IS ENFORCED BY THE CALLERS RATHER THAN HERE.** This helper is happy to
    build ``/record/X`` from ``run=None`` — which is right for
    :func:`experiment_link` and WRONG for :func:`run_link`, where it would produce a
    link labelled "run" that addresses the record instead. That defect was written and
    caught before it shipped: the entity-specific builders below each refuse a missing
    id of their own, so a caller can never be handed a broader link than it asked for
    under a narrower name. A link that silently widens its own scope is worse than no
    link, because the label is what the agent repeats to the scientist.

    Order is the insertion order of the caller's keyword arguments, which is stable in
    Python and is what makes these strings comparable byte-for-byte in a test.
    """
    if not _usable(experiment_id):
        return None
    path = f"/record/{quote(experiment_id, safe='')}"
    pairs = [
        f"{key}={quote(value, safe='')}"
        for key, value in params.items()
        if _usable(value)
    ]
    return f"{path}?{'&'.join(pairs)}" if pairs else path


def experiment_link(experiment_id: str) -> str | None:
    """The record's own screen. Lands on the `fields` workspace, as a bare URL does.

    No ``?view=`` is emitted deliberately: ``/record/<id>`` bare already resolves to
    ``fields``, so adding it would make this link differ from the one a bookmark or an
    existing test holds while going to the same place.
    """
    return _record_path(experiment_id)


def capture_link(experiment_id: str) -> str | None:
    """The record's `capture` workspace — where notes and proposals are reviewed.

    THE ADDRESS FOR A NOTE, and there is deliberately no per-note parameter. A note is
    reviewed in the same panel group as a proposal, on the same screen, and no
    ``?note=`` exists; minting one would publish a navigational distinction the
    application does not make and would send a scientist to a screen claiming to focus
    something it cannot focus. The workspace is the most specific honest address.
    """
    return _record_path(experiment_id, **{VIEW_PARAM: CAPTURE_VIEW})


def run_link(experiment_id: str, run_id: str) -> str | None:
    """One run, opened in the record's `runs` workspace.

    ``?view=runs`` is NOT emitted and ``?run=`` alone is, because the frontend already
    resolves a bare ``?run=`` to the runs workspace — that predates MCP-006 and is the
    pattern ``?proposal=`` was modelled on. Emitting both would be a second way to say
    one thing.

    ``None`` FOR A MISSING RUN ID, and this refusal is the reason ``_record_path``'s
    own omission rule is not enough: without it a blank ``run_id`` would yield
    ``/record/<id>`` under the name "run".
    """
    if not _usable(run_id):
        return None
    return _record_path(experiment_id, **{RUN_PARAM: run_id})


def proposal_link(experiment_id: str, proposal_id: str) -> str | None:
    """One proposal, opened in the record's `capture` workspace. **MCP-006.**

    ``?view=capture`` IS EMITTED HERE, unlike in :func:`run_link`, and the asymmetry is
    deliberate rather than an inconsistency. The frontend resolves a bare
    ``?proposal=`` to `capture` too, so the view is redundant in the common case — but
    a URL carrying BOTH ``?run=`` and ``?proposal=`` with no ``?view=`` resolves to
    `runs`, because the older address wins so that no link that worked before moves.
    Emitting the view means this link cannot be ambiguous even if a caller later
    appends a run, and it costs one parameter.

    ``None`` FOR A MISSING PROPOSAL ID, for :func:`run_link`'s reason — a blank id
    would otherwise yield the plain capture workspace under the name "proposal",
    telling a scientist a specific suggestion was addressed when none was.
    """
    if not _usable(proposal_id):
        return None
    return _record_path(
        experiment_id, **{VIEW_PARAM: CAPTURE_VIEW, PROPOSAL_PARAM: proposal_id}
    )


def ambiguity_link(experiment_id: str, item_id: str) -> str | None:
    """An item whose value the scientist has to disambiguate.

    **THE SAME LINK AS :func:`proposal_link`, BECAUSE THIS BUILD HAS NO SEPARATE
    AMBIGUITY ENTITY** — see :data:`AMBIGUITY_PARAM`. It is a distinct function so the
    caller's intent is recorded at the call site and so a future ambiguity entity is
    one edit rather than an audit.
    """
    return proposal_link(experiment_id, item_id)


def link_literals() -> Mapping[str, str]:
    """The frontend literals this module transcribes, for a parity test to check.

    Published as DATA rather than described in prose, because the module docstring's
    claim that these match ``apps/web/src/lib/routes.ts`` is exactly the kind of claim
    this repository has been caught asserting without measuring. A test reads the
    TypeScript and compares.
    """
    return {
        "RECORD_VIEW_PARAM": VIEW_PARAM,
        "RECORD_RUN_PARAM": RUN_PARAM,
        "RECORD_PROPOSAL_PARAM": PROPOSAL_PARAM,
        "capture_view_id": CAPTURE_VIEW,
    }

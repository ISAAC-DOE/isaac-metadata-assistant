"""No surface may attribute a finding to the official ISAAC schema that it did not make.

THE DEFECT THIS CLOSES, measured over HTTP by an independent review
===================================================================
On a run whose descriptor ``name`` carries a trailing newline::

    POST /api/experiments/{id}/runs/{run_id}/check
      draft    {"ok": true,  "errors": []}
      official {"ok": false, "dry_run": true, "schema": "ISAAC v1.05"}
               errors[0] = ISAAC's OWN anchored-pattern exactness message

The vendored official ISAAC schema never examined that record: ``export_draft``
returns before ``validate_official`` when the exactness gate refuses, and folds the
exactness findings into ``draft_report`` on the way out.

``CLAUDE.md`` §1 makes the vendored schema upstream-owned and §12 states the rule
outright: *"the gate is ISAAC's, not upstream's ... no surface may report an
exactness refusal as an official-schema error."*

WHY THIS FILE WAS REWRITTEN, AND IT IS THE WHOLE POINT OF THE SLICE
===================================================================
The first version of this file said:

    "**There is nothing on the payload to branch on.** ... The durable fix is a
    discriminator on the wire (``official_validator_ran`` ...); it is deliberately
    not in this slice ... **So this file guards the only thing that WAS fixed: the
    descriptions no longer claim what the payload cannot support.** It asserts
    nothing about the payload itself, which is the honest scope."

That scope was honest and it was not enough. Two things went wrong that a
description-only guard could not see:

1. **THE DISCRIMINATOR NOW EXISTS**, so the guard can and must assert something
   about the payload. ``official_validator_ran`` is published by both operations;
   ``test_run_api``/``test_official_validator_ran_discriminator`` exhibits both
   branches over HTTP.

2. **THE GUARDED SURFACE SET WAS A HAND-KEPT LIST, AND THAT IS HOW THE SIXTH
   SURFACE GETS MISSED.** The previous slice corrected three React renderers and
   left the claim standing in a fourth screen, in a fifth module, and in both
   machine-readable contracts — while a test named
   ``test_the_surfaces_under_guard_still_exist`` passed, because it only checked
   that the surfaces IT KNEW ABOUT existed. A list cannot notice an omission from
   itself.

   So the set is now **DERIVED FROM THE CODE**: every served operation whose
   endpoint function reaches one of the verdict builders, and every MCP tool whose
   declared ``operation_ids`` resolve to such an operation. Add a route that
   returns an official verdict, or a tool over one, and it is guarded the moment it
   exists — not the moment somebody remembers to list it.

Nothing here opens a network connection, reads real data, or touches a database.
"""

from __future__ import annotations

import inspect

import pytest

from isaac_api.mcp.policy import OPERATIONS
from isaac_api.mcp.tools import TOOLS

#: The wire field that answers "did the official validator produce these findings?".
#: Every guarded description must name it, because a disclosure that does not tell the
#: caller HOW to tell the two cases apart leaves them exactly where they were.
DISCRIMINATOR = "official_validator_ran"

#: The disclosure each affected surface must carry. Written once and required
#: verbatim, so the surfaces cannot drift into different stories about one fact.
DISCLOSURE = "the vendored official ISAAC schema's verdict WHERE THE OFFICIAL VALIDATOR RAN"

#: The names, in ``isaac_api.routes``, that BUILD an official-schema verdict. A route
#: that calls one of these publishes findings whose producer is ambiguous on the wire
#: unless it publishes the discriminator, so calling one is what puts a route under
#: this guard.
#:
#: ``validate_official`` is included as well as the two local builders, so a route
#: that reaches the truth-core validator directly — the way ``post_validate``'s
#: already-exported branch does — cannot escape by not going through a helper.
VERDICT_BUILDERS = ("_validate_unit", "_fan_out_official_verdict", "validate_official")

#: Operations DELIBERATELY EXEMPT, keyed exactly as the derivation names them, each
#: with the reason it is not a false negative. An entry here is a CLAIM, re-checked by
#: ``test_every_exemption_names_a_real_operation_and_a_reason``: the operation must
#: still be derived (so a stale exemption cannot silently widen the guard) and the
#: reason must actually say something.
#:
#: Keyed by ``"METHOD /path"`` rather than by MCP operation id on purpose — the MCP
#: allowlist does not contain every route, so an id-keyed exemption for an
#: unallowlisted operation resolves to nothing and silently fails to exempt.
EXEMPT: dict[str, str] = {
    "POST /api/validate/record": (
        "The derivation finds this route because it calls `validate_official` "
        "directly, and it is exempt because it is the surface that already SEPARATES "
        "the two gates — `schema_ok` beside `ok`, and `exactness_errors` as its own "
        "list, which is a stronger publication of the distinction than a boolean. It "
        "is also the operation every other guarded description points AT, so "
        "requiring it to carry the pointer to itself would be circular. Note what "
        "this exemption does NOT excuse: CLAUDE.md §12 records that the Validator "
        "screen over this route once rendered `FAIL - Invalid against official ISAAC "
        "schema v1.05 - 0 errors` above `schema_ok: true`, and "
        "`apps/web/src/__tests__/validator-exactness.test.tsx` is what guards that."
    ),
}


@pytest.fixture(scope="module")
def spec() -> dict:
    from isaac_api.app import create_app

    return create_app().openapi()


def _operation_ids_by_route() -> dict[str, tuple[str, str]]:
    """Every allowlisted operation id -> ``(method, path)`` as OpenAPI spells it."""
    return {
        op.id: (op.method.lower(), op.path_template) for op in OPERATIONS.values()
    }


def derive_guarded_routes(spec: dict) -> dict[str, str]:
    """Every SERVED operation whose endpoint reaches a verdict builder.

    Derived by reading the endpoint's own source, which is the closest mechanical
    stand-in available for "this operation publishes an official verdict". A call
    graph would be stronger; a hand-kept list is what this replaces, and the failure
    mode of a list is silence, which is worse than the failure mode here (a route
    that mentions a builder in a comment and is guarded unnecessarily — visible, and
    fixed by naming it in ``EXEMPT`` with a reason).
    """
    import isaac_api.routes as routes

    found: dict[str, str] = {}
    for route in routes.router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:  # pragma: no cover - every APIRoute has one
            continue
        try:
            source = inspect.getsource(endpoint)
        except (OSError, TypeError):  # pragma: no cover - defensive
            continue
        if not any(name in source for name in VERDICT_BUILDERS):
            continue
        for method in sorted(m.lower() for m in (route.methods or ())):
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            path = route.path
            if path in spec["paths"] and method in spec["paths"][path]:
                found[f"{method.upper()} {path}"] = path
    return found


def derive_guarded_tools(spec: dict, exclude: set[str] | None = None) -> dict[str, str]:
    """Every MCP tool whose declared operations resolve to a guarded route.

    THIS IS THE DERIVATION THAT WOULD HAVE CAUGHT THE MISS. ``isaac_check_run`` was
    left stating the withdrawn claim while three renderers were corrected, because
    nothing connected the tool to the route it wraps. ``Tool.operation_ids`` ->
    ``OPERATIONS[...].path_template`` is exactly that connection, and it is already
    validated at import time by ``_validate_tool``.
    """
    routes_by_name = derive_guarded_routes(spec)
    guarded_paths = {
        path
        for name, path in routes_by_name.items()
        if not (exclude and name in exclude)
    }
    by_id = _operation_ids_by_route()
    out: dict[str, str] = {}
    for name, tool in TOOLS.items():
        for operation_id in tool.operation_ids:
            entry = by_id.get(operation_id)
            if entry is not None and entry[1] in guarded_paths:
                out[name] = operation_id
                break
    return out


def _served(spec: dict, method: str, path: str) -> str:
    operation = (spec["paths"].get(path) or {}).get(method)
    assert operation is not None, f"{method.upper()} {path} is not served"
    return " ".join((operation.get("description") or "").split())


def _all_descriptions(spec: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, path in derive_guarded_routes(spec).items():
        if name in EXEMPT:
            continue
        method = name.split(" ", 1)[0].lower()
        out[name] = _served(spec, method, path)
    for tool_name in derive_guarded_tools(spec, exclude=set(EXEMPT)):
        out[f"mcp:{tool_name}"] = " ".join(TOOLS[tool_name].description.split())
    return out


# --------------------------------------------------------------------------- #
# the derivation itself, guarded before anything is derived from it
# --------------------------------------------------------------------------- #


def test_the_derivation_finds_the_surfaces_we_already_know_about(spec):
    """A DERIVATION CAN GO SILENT AS EASILY AS A LIST CAN GO STALE.

    ``inspect.getsource`` on a decorated endpoint, a rename of a builder, a router
    restructure — any of these could make ``derive_guarded_routes`` return ``{}``,
    and every assertion below would then pass over an empty set. So the three
    surfaces this defect was measured on are asserted to be IN the derived set. They
    are a floor, not the set: the set is whatever the code says, and that is the
    point.
    """
    derived = _all_descriptions(spec)
    for expected in (
        "POST /api/experiments/{experiment_id}/validate",
        "POST /api/experiments/{experiment_id}/runs/{run_id}/check",
        "mcp:isaac_check_run",
    ):
        assert expected in derived, (
            f"the derivation lost {expected!r}. Every assertion in this file is "
            f"computed over the derived set, so a silent derivation is a silent "
            f"guard. Derived: {sorted(derived)}"
        )
    for name, text in derived.items():
        assert text, f"{name} serves an empty description"


def test_every_exemption_names_a_real_operation_and_a_reason(spec):
    """An exemption for an operation that is no longer derived is a dead permission.

    It is also worse than dead: a route renamed or restructured out of the derived set
    leaves its exemption behind, and the next route to land on that key inherits a
    permission nobody granted it.
    """
    derived = derive_guarded_routes(spec)
    for name, reason in EXEMPT.items():
        assert name in derived, (
            f"{name!r} is exempted from the official-attribution guard and is not in "
            f"the derived set. Delete the exemption. Derived: {sorted(derived)}"
        )
        assert len(reason.split()) >= 20, (
            f"the exemption for {name!r} does not explain itself. An exemption is a "
            "claim that the surface is safe for a different reason; state it."
        )


# --------------------------------------------------------------------------- #
# the disclosure, and the discriminator that makes it actionable
# --------------------------------------------------------------------------- #


def test_every_surface_scopes_the_official_attribution(spec):
    wanted = " ".join(DISCLOSURE.split())
    for name, text in sorted(_all_descriptions(spec).items()):
        assert wanted in text, (
            f"{name} reports an official verdict without saying that the official "
            "validator may not have run. A dry run refused by the no-guessing check "
            "or by ISAAC's anchored-pattern exactness gate returns THOSE findings "
            f"under the same `errors` key. Required verbatim: {wanted!r}"
        )


def test_every_surface_NAMES_THE_FIELD_A_CALLER_BRANCHES_ON(spec):
    """A disclaimer without a discriminator leaves the caller where they started.

    This is the assertion the first version of this file could not make, and its
    absence is why five surfaces each invented their own ordering rule. A
    description that says "the official validator may not have run" and does not
    say how to tell is an invitation to guess.
    """
    for name, text in sorted(_all_descriptions(spec).items()):
        assert DISCRIMINATOR in text, (
            f"{name} discloses that the official validator may not have run without "
            f"naming `{DISCRIMINATOR}`, the field that says which. Every consumer "
            "that had to reconstruct this from `dry_run` plus an ordering rule got "
            "it wrong at least once — CLAUDE.md §12."
        )


def test_no_surface_says_the_wire_carries_no_discriminator(spec):
    """The withdrawn META-claim, which outlived the defect it described.

    Three files asserted "there is nothing on the payload to branch on" as a
    standing fact. It was true and is not. A future reader who believes it will
    reimplement the ordering rule, so the sentence itself is now guarded.
    """
    for name, text in sorted(_all_descriptions(spec).items()):
        for phrase in (
            "no discriminator",
            "nothing to branch on",
            "cannot tell the two apart",
        ):
            assert phrase not in text.lower(), (
                f"{name} still says the payload carries {phrase!r}. It carries "
                f"`{DISCRIMINATOR}`."
            )


#: The phrasings that were withdrawn, each of which attributes a finding to the
#: official schema unconditionally. A positive check alone would pass on a
#: description that carried the disclosure AND the old claim.
WITHDRAWN: tuple[str, ...] = (
    "Checks this record against the vendored official ISAAC schema and returns",
    "the official-schema verdict",
    "the official ISAAC schema verdict, and the run's open blocking",
)


@pytest.mark.parametrize("phrase", WITHDRAWN, ids=[p[:34] for p in WITHDRAWN])
def test_no_surface_carries_a_withdrawn_attribution(spec, phrase: str):
    wanted = " ".join(phrase.split())
    for name, text in sorted(_all_descriptions(spec).items()):
        assert wanted not in text, (
            f"{name} states a withdrawn attribution: {wanted!r}. It says the official "
            "ISAAC schema produced findings the official ISAAC schema may never have "
            "seen — CLAUDE.md §12."
        )


def test_the_route_descriptions_name_where_the_two_gates_ARE_separated(spec):
    """The disclosure must point somewhere, not merely disclaim.

    `POST /api/validate/record` already separates `schema_ok` from
    `exactness_errors`, and it is the answer for an HTTP caller who needs the
    findings split rather than merely attributed. Naming it is the difference
    between a warning and a route.

    **THE MCP TOOLS ARE DELIBERATELY EXEMPT.** No tool exposes that operation, so
    naming an HTTP path there would tell an agent about a call it cannot make. An
    agent's honest remedy is the one its own description now gives: read
    `official_validator_ran: false` as "the export gate refused", not as "the
    official schema rejected it".
    """
    for name, text in sorted(_all_descriptions(spec).items()):
        if name.startswith("mcp:"):
            continue
        assert "/api/validate/record" in text, (
            f"{name} discloses that the official validator may not have run and does "
            "not name the operation that reports the two gates separately"
        )

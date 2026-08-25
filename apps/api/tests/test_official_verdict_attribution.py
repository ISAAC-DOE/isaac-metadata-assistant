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
exactness findings into ``draft_report`` on the way out. Three DESCRIPTIONS said
otherwise, in the words a client author and a language model read before calling:

* ``POST /api/experiments/{id}/validate`` — *"Checks this record against the
  vendored official ISAAC schema and returns `ok`…"*
* ``POST /api/experiments/{id}/runs/{run_id}/check`` — *"returns the no-guessing
  draft verdict, the official-schema verdict, and…"*
* the MCP tool ``isaac_check_run`` — *"the official ISAAC schema verdict"*

``CLAUDE.md`` §1 makes the vendored schema upstream-owned and §12 states the rule
outright: *"the gate is ISAAC's, not upstream's ... no surface may report an
exactness refusal as an official-schema error."* §12 also records that a surface
shipped this exact conflation once already (``VerdictCard``), and
``routes._export_step_detail`` closed it a third time on the pipeline wire.

WHY FOUR SURFACES GOT IT WRONG AT ONCE
======================================
**There is nothing on the payload to branch on.** ``schema`` is stamped
unconditionally, and ``dry_run`` does not discriminate — a dry-run PASS does require
``validate_official``, a dry-run FAILURE may never have reached it. The durable fix
is a discriminator on the wire (``official_validator_ran``, or a separate findings
list as ``POST /api/validate/record`` already has); it is deliberately not in this
slice, and ``routes._validate_unit`` records why. **So this file guards the only
thing that WAS fixed: the descriptions no longer claim what the payload cannot
support.** It asserts nothing about the payload itself, which is the honest scope.

Nothing here opens a network connection, reads real data, or touches a database.
"""

from __future__ import annotations

import pytest

from isaac_api.mcp.tools import TOOLS

#: The disclosure each affected surface must carry. Written once and required
#: verbatim, so the three cannot drift into three different stories about one fact.
DISCLOSURE = "the vendored official ISAAC schema's verdict WHERE THE OFFICIAL VALIDATOR RAN"

#: The route operations that report an official verdict built by
#: ``routes._validate_unit`` — the function whose three branches produce three kinds
#: of finding under one ``errors`` key.
ROUTE_OPERATIONS: tuple[tuple[str, str], ...] = (
    ("post", "/api/experiments/{experiment_id}/validate"),
    ("post", "/api/experiments/{experiment_id}/runs/{run_id}/check"),
)

#: MCP tools whose description reports the same block.
MCP_TOOLS: tuple[str, ...] = ("isaac_check_run",)

#: The phrasings that were withdrawn, each of which attributes a finding to the
#: official schema unconditionally. A positive check alone would pass on a
#: description that carried the disclosure AND the old claim.
WITHDRAWN: tuple[str, ...] = (
    "Checks this record against the vendored official ISAAC schema and returns",
    "the official-schema verdict",
    "the official ISAAC schema verdict, and the run's open blocking",
)


@pytest.fixture(scope="module")
def spec() -> dict:
    from isaac_api.app import create_app

    return create_app().openapi()


def _served(spec: dict, method: str, path: str) -> str:
    operation = (spec["paths"].get(path) or {}).get(method)
    assert operation is not None, f"{method.upper()} {path} is not served"
    return " ".join((operation.get("description") or "").split())


def _all_descriptions(spec: dict) -> dict[str, str]:
    out = {
        f"{method.upper()} {path}": _served(spec, method, path)
        for method, path in ROUTE_OPERATIONS
    }
    for name in MCP_TOOLS:
        tool = TOOLS.get(name)
        assert tool is not None, f"no MCP tool named {name!r}"
        out[f"mcp:{name}"] = " ".join(tool.description.split())
    return out


def test_the_surfaces_under_guard_still_exist(spec):
    """A guard on the guard: a renamed route would make everything below vacuous."""
    described = _all_descriptions(spec)
    assert len(described) == len(ROUTE_OPERATIONS) + len(MCP_TOOLS)
    for name, text in described.items():
        assert text, f"{name} serves an empty description"


def test_every_surface_scopes_the_official_attribution(spec):
    wanted = " ".join(DISCLOSURE.split())
    for name, text in sorted(_all_descriptions(spec).items()):
        assert wanted in text, (
            f"{name} reports an official verdict without saying that the official "
            "validator may not have run. A dry run refused by the no-guessing check "
            "or by ISAAC's anchored-pattern exactness gate returns THOSE findings "
            f"under the same `errors` key. Required verbatim: {wanted!r}"
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
    distinction. Naming it is the difference between a warning and a route.

    **THE MCP TOOL IS DELIBERATELY EXEMPT.** No tool exposes that operation — the
    registry holds ten and `isaac_check_run` is the only validation one — so naming
    an HTTP path there would tell an agent about a call it cannot make. An agent's
    honest remedy is the one its own description gives: read `official.ok` as "the
    export gate refused", not as "the official schema rejected it".
    """
    for method, path in ROUTE_OPERATIONS:
        text = _served(spec, method, path)
        assert "/api/validate/record" in text, (
            f"{method.upper()} {path} discloses that the official validator may not "
            "have run and does not name the operation that reports the two gates "
            "separately"
        )

"""The MCP tool descriptions and the REST descriptions of the SAME operation must agree.

WHAT THIS EXISTS TO PREVENT, measured over HTTP by an independent review
=======================================================================
``isaac_create_run``'s tool description said::

    "The new run starts EMPTY: no record-level value is copied into it and no
     scientific value is invented."

while the REST description of the operation it calls (``POST
/api/experiments/{experiment_id}/runs``) said, in capitals::

    "THE FIRST RUN ADOPTS THE RECORD'S PER-RUN CONTENT; A LATER RUN DOES NOT."

``workspace.py`` agreed with the second. The behaviour agrees with the second:
answer ``qc`` on a record with no runs, add the first run, and that run's draft
carries ``{"status": "valid", "evidence": "I0 stable"}``.

So one feature told a **person** the truth (``mcpConnectContent.ts`` had already
been corrected) and told a **language model** the reverse — in the text a model
reads *before* it acts. An agent believing "starts EMPTY" would re-answer values
that are already present, or decline to add a first run in order to protect
content that adding it would have carried across.

**No test compared the two surfaces at all.** That is why it survived: the MCP
suite checks scopes, schemas and boundaries; the OpenAPI suite checks the served
document; nothing read both descriptions in one process. This file does.

WHY A TABLE OF SHARED SENTENCES RATHER THAN A GENERAL EQUALITY
==============================================================
The two descriptions are deliberately NOT identical — the REST one addresses a
client author and names status codes, the MCP one addresses an agent and names
``if_match``. Requiring equality would force one register onto both audiences and
would be abandoned the first time it was inconvenient.

Nor can "these two do not contradict each other" be decided mechanically. So the
control is narrower and checkable: for a claim that BOTH surfaces must make, the
sentence is written once in the route and **quoted verbatim** by the tool, and this
file asserts it is present in both. A rewording on either side turns this red.

Paired with a NEGATIVE control naming the withdrawn sentence, because a parity
assertion alone would pass on a description that carried the true sentence and the
false one together — which is a real hazard here, given that both surfaces were
edited and only one was fixed.

Nothing here opens a network connection, reads real data, or touches a database.
"""

from __future__ import annotations

import pytest

from isaac_api.mcp import policy
from isaac_api.mcp.tools import TOOLS

#: ``{tool name: (operation id, sentence that must appear in BOTH descriptions)}``.
#:
#: One entry per claim, not per tool: a tool may share more than one sentence with
#: its route, and naming them individually makes a failure say WHICH claim drifted.
SHARED_CLAIMS: tuple[tuple[str, str, str], ...] = (
    (
        "isaac_create_run",
        "create_run",
        "THE FIRST RUN ADOPTS THE RECORD'S PER-RUN CONTENT; A LATER RUN DOES "
        "NOT.",
    ),
    (
        # THE HIGHEST-STAKES CLAIM THE PROPOSAL SURFACE MAKES, and the one a
        # paraphrase would quietly weaken. `isaac_propose_field_value` is the channel
        # for model-derived output, and it is safe only because a proposal is not a
        # value: `proposals.py` cannot represent a confirmed one, and the proposal is
        # stored outside `draft`, so no export and no submission signature reads it.
        # A tool description that softened this to "does not immediately write" would
        # be describing a different feature to the one reader who acts on it alone.
        "isaac_propose_field_value",
        "create_proposal",
        "IT WRITES NO SCIENTIFIC VALUE AND MINTS NO EVIDENCE.",
    ),
)

#: Sentences that must appear in NO tool description, with the reason they were
#: withdrawn. A parity check alone cannot catch a description that states the true
#: claim and the false one in adjacent sentences.
WITHDRAWN: tuple[tuple[str, str], ...] = (
    (
        "starts EMPTY: no record-level value is copied into it",
        "the first run adopts the record's per-run content — measured: answer `qc`, "
        "add the first run, and the run's draft carries the verdict",
    ),
)


@pytest.fixture(scope="module")
def spec() -> dict:
    from isaac_api.app import create_app

    return create_app().openapi()


def _tool(name: str):
    tool = TOOLS.get(name)
    assert tool is not None, f"no MCP tool named {name!r}"
    return tool


def _route_description(spec: dict, operation_id: str) -> str:
    """The SERVED description of the route an MCP operation id names.

    Read from the generated document rather than from the ``routes.py`` source
    string, for the reason ``test_submit_refusal_partition.py`` gives: the constant
    is what we wrote and the document is what a client reads.
    """
    operation = policy.OPERATIONS[operation_id]
    served = (spec["paths"].get(operation.path_template) or {}).get(
        operation.method.lower()
    )
    assert served is not None, (
        f"the MCP policy names {operation.method} {operation.path_template} for "
        f"operation {operation_id!r}, and the served document has no such operation"
    )
    return served.get("description") or ""


def test_the_lookup_finds_something_at_all():
    """A guard on the guard: an empty table would make every assertion below vacuous."""
    assert SHARED_CLAIMS, "the shared-claim table is empty"
    for tool_name, operation_id, sentence in SHARED_CLAIMS:
        assert _tool(tool_name) is not None
        assert operation_id in policy.OPERATIONS, operation_id
        assert sentence.strip(), (tool_name, operation_id)


@pytest.mark.parametrize(
    ("tool_name", "operation_id", "sentence"),
    SHARED_CLAIMS,
    ids=[f"{t}:{o}" for t, o, _ in SHARED_CLAIMS],
)
def test_a_shared_claim_is_made_by_both_surfaces(
    spec, tool_name: str, operation_id: str, sentence: str
):
    route_text = " ".join(_route_description(spec, operation_id).split())
    tool_text = " ".join(_tool(tool_name).description.split())
    wanted = " ".join(sentence.split())
    assert wanted in route_text, (
        f"the ROUTE description for {operation_id} no longer carries the shared "
        f"claim {wanted!r}. If the claim changed, change it on BOTH surfaces and "
        "here; if it was deleted, delete this row and say why."
    )
    assert wanted in tool_text, (
        f"the MCP tool {tool_name!r} no longer carries the shared claim {wanted!r}, "
        "so the machine-facing half of this feature can disagree with the "
        "human-facing half again — which is exactly what it did."
    )


@pytest.mark.parametrize(
    ("phrase", "why"), WITHDRAWN, ids=[p[:32] for p, _ in WITHDRAWN]
)
def test_no_tool_description_carries_a_withdrawn_claim(phrase: str, why: str):
    for name, tool in TOOLS.items():
        assert phrase not in " ".join(tool.description.split()), (
            f"MCP tool {name!r} states a withdrawn claim: {phrase!r} — {why}"
        )

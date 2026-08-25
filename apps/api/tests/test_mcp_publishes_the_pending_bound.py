"""THE MCP TOOL DESCRIPTION IS A SEPARATE PUBLISHED CONTRACT, AND IT HAS TO SAY THE
SAME THING THE HTTP CONTRACT SAYS.

WHY THIS FILE EXISTS
====================
When the four mutation operations started returning a WINDOWED ``pending`` list, five
HTTP operation descriptions were updated to say so — and the MCP tools were not.
``mcp.tools._ok`` forwards ``result.body`` verbatim as ``data``, so
``isaac_answer_questions`` began returning a bounded list to external agents while its
published description still read as though ``data.pending`` were the record's whole
set. An agent that computed "how much is left" from ``len(data.pending)`` would have
been given a number that stops at ``PENDING_WINDOW``.

The repository's own standard for the bound, from
``apps/web/src/__tests__/settings-api.test.tsx``:

    a bounded response that did not say so in the published contract would be exactly
    the silent truncation the bound exists to prevent.

That standard was applied to OpenAPI and not here, which is the gap this file closes —
and closes STRUCTURALLY rather than by adding two more descriptions to a list somebody
has to remember. **WHICH tools must carry the statement is DERIVED**, from the routes
that actually call ``routes._mutation_pending_response``, so a fifth bounded operation
added later fails this file on the day it is registered rather than on the day an agent
misreads it.

WHY THE DERIVATION IS AN AST WALK RATHER THAN A PROSE MARKER
============================================================
Searching the operation descriptions for a sentence would test prose against prose:
the failure being guarded is precisely that a description did not get updated, so a
description cannot be the evidence. The call graph is the code. ``_apply_to_run`` is
why the walk must be TRANSITIVE — two of the four routes reach the bundle through it
and neither names it directly.
"""

from __future__ import annotations

import ast
import inspect

import pytest
from fastapi.routing import APIRoute

from isaac_api import routes as api_routes
from isaac_api import serialize
from isaac_api.mcp.policy import OPERATIONS
from isaac_api.mcp.tools import TOOLS

#: The function whose return value IS the bounded bundle. Everything downstream of a
#: call to it, however many hops away, serves a windowed ``pending``.
_BUNDLE = "_mutation_pending_response"

#: A substring of the published statement, chosen to be the part that carries the
#: MEANING rather than the formatting: a tool may reword around it, but a tool that
#: does not say the list is a window is the defect.
_MARKER = "IS A WINDOW, NOT THE RECORD'S WHOLE SET"


def _callers_of(name: str) -> set[str]:
    """Every function in ``routes`` that reaches ``name``, directly or through others."""
    tree = ast.parse(inspect.getsource(api_routes))
    calls: dict[str, set[str]] = {}

    class Walk(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_FunctionDef(self, node):  # noqa: N802 - ast API
            self.stack.append(node.name)
            calls.setdefault(node.name, set())
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):  # noqa: N802 - ast API
            if self.stack and isinstance(node.func, ast.Name):
                calls[self.stack[-1]].add(node.func.id)
            self.generic_visit(node)

    Walk().visit(tree)
    reached = {name}
    changed = True
    while changed:
        changed = False
        for function, called in calls.items():
            if function not in reached and called & reached:
                reached.add(function)
                changed = True
    return reached


def _bounded_operation_ids() -> set[str]:
    """The MCP operation ids whose HTTP route returns a bounded ``pending``."""
    reached = _callers_of(_BUNDLE)
    endpoints = {
        (method, route.path)
        for route in api_routes.router.routes
        if isinstance(route, APIRoute) and route.endpoint.__name__ in reached
        for method in route.methods - {"HEAD", "OPTIONS"}
    }
    return {
        operation_id
        for operation_id, operation in OPERATIONS.items()
        if (operation.method, operation.path_template) in endpoints
    }


def test_the_derivation_finds_the_four_bounded_operations():
    """A GUARD ON THE GUARD, and it is not ceremony.

    Every assertion below is over a DERIVED set, so a walk that silently found nothing
    — a renamed helper, a route registered somewhere this does not look — would make
    the whole file pass while checking nothing. Pinning the membership means the
    derivation breaking is a failure rather than a vacuous pass. It is a set equality
    rather than a length so that a fifth bounded operation is a NAMED failure.
    """
    assert _bounded_operation_ids() == {
        "answer_record_question",
        "answer_run_question",
        "correct_record_field",
        "correct_run_field",
    }


def test_every_tool_reaching_a_bounded_operation_publishes_the_bound():
    """THE FINDING. Two tools reach one of the four, and both must say so.

    ``isaac_answer_questions`` reaches all four. ``isaac_update_draft`` reaches
    ``correct_record_field`` on its record-level branch only — which is why its
    statement is scoped to that branch rather than asserted of both.
    """
    bounded = _bounded_operation_ids()
    reaching = [tool for tool in TOOLS.values() if set(tool.operation_ids) & bounded]
    assert {tool.name for tool in reaching} == {
        "isaac_answer_questions",
        "isaac_update_draft",
    }, sorted(tool.name for tool in reaching)

    for tool in reaching:
        assert _MARKER in tool.description, tool.name
        # `pending_page` is the block a caller has to be told to read INSTEAD of
        # `len(data.pending)`; naming the window without naming the block would leave
        # the agent knowing it has a page and not how to find the total.
        assert "pending_page" in tool.description, tool.name


def test_the_published_window_is_the_server_s_own_number():
    """INTERPOLATED, NOT RETYPED — the same rule ``routes._BOUNDED_PENDING_PARAGRAPH``
    follows. A hand-typed 50 in a published description is a copy free to drift, and
    the copy that drifts is the one the external agent is reading."""
    for name in ("isaac_answer_questions", "isaac_update_draft"):
        assert str(serialize.PENDING_WINDOW) in TOOLS[name].description, name


@pytest.mark.parametrize(
    "name", ["isaac_list_questions", "isaac_get_experiment", "isaac_create_run"]
)
def test_a_tool_that_returns_a_complete_list_does_not_claim_a_bound(name):
    """THE NEGATIVE CONTROL, and it is the half that keeps the fix honest.

    ``isaac_list_questions`` reaches ``GET /pending``, which answers COMPLETELY by
    default — bounding there is opt-in and this tool sends no parameters. A tool that
    told an agent its complete list was a window would be the mirror-image lie, and it
    would also make the statement above meaningless by making it universal.
    """
    assert _MARKER not in TOOLS[name].description

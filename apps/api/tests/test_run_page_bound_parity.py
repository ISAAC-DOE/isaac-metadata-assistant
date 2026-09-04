"""`RUN_PAGE_MAX` and the browser's `RUN_LIST_LIMIT_MAX` must not drift apart.

WHY THIS FILE EXISTS, IN THE WORDS OF THE THING IT GUARDS
=========================================================

``apps/web/src/lib/runPaging.ts`` mirrors the server's ``RUN_PAGE_MAX`` as a
client-side literal, and its own docstring names the gap rather than papering over
it: *"If the server's bound ever changes, this one has to change with it — NO TEST IN
THIS TREE PINS THAT AGREEMENT TODAY, and that is a named gap rather than an oversight
papered over: closing it needs either a committed test reading ``RUN_PAGE_MAX`` out of
the OpenAPI document this build already serves, or a Python-side test asserting the
two literals match, and neither exists yet."*

``docs/session-closure-2026-09-02b.md`` records the same gap as residue. This is the
first of the two remedies that docstring names, plus the second as its floor.

WHY IT IS NOT THE *PREFERRED* REMEDY, STATED RATHER THAN LEFT TO BE NOTICED
===========================================================================

The better fix is to SERVE the bound in the run-listing response and have the browser
read it, so no copy exists to drift. That was measured as reachable and is deliberately
NOT done here, for a reason that is about this slice rather than about the design: the
only consumer of the value is ``RunsSection.tsx``, and consuming a served bound means
changing that component's over-the-cap decision — work this slice is scoped out of.
A served field with no reader would be the shape this repository has already deleted
once (``api.getProposal``, "dead code kept alive by a counter is worse than a smaller
counter"). So the copy stays and the DRIFT is what is closed.

WHAT THIS DOES AND DOES NOT PROVE
=================================

It proves the three expressions of one bound agree TODAY: the Python constant, the
``maximum`` FastAPI derives from it for the query parameter, and the TypeScript
literal. It does not prove the browser USES the bound correctly — that is
``runs-section-live-refresh.test.tsx``'s job — and it does not stop a future slice
retyping the number somewhere this file does not look.

IT PARSES TYPESCRIPT WITH A REGEX, and that is a known cost carried deliberately, the
way ``test_contract_description_parity.py`` carries it for
``REAL_CONTRACT_DESCRIPTIONS``: Python can see BOTH sides and the frontend suite can
see only one, so this is the side the check has to live on. The failure mode that
matters is a check that silently matches nothing, so the parse is asserted separately
and loudly before anything is compared.

DATA BOUNDARY: none. This file reads two committed source files and one generated
OpenAPI document. No workspace, no network, no database.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import isaac_api.routes as routes

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_PAGING_TS = REPO_ROOT / "apps" / "web" / "src" / "lib" / "runPaging.ts"

#: `export const RUN_LIST_LIMIT_MAX = 200;` — anchored on the DECLARATION rather than
#: on the bare name, for the reason `test_contract_description_parity.py` records: the
#: name also appears in that module's prose, and a search that matched a mention would
#: read a number out of a comment.
_LITERAL_RE = re.compile(r"^export const RUN_LIST_LIMIT_MAX\s*=\s*(\d+);", re.MULTILINE)

RUNS_PATH = "/api/experiments/{experiment_id}/runs"


@pytest.fixture(scope="module")
def spec() -> dict:
    from isaac_api.app import create_app

    return create_app().openapi()


def _typescript_literal() -> int:
    assert RUN_PAGING_TS.is_file(), f"missing {RUN_PAGING_TS}"
    source = RUN_PAGING_TS.read_text()
    matches = _LITERAL_RE.findall(source)
    # LOUD RATHER THAN VACUOUS. A shape change — a computed value, a re-export, a
    # rename — must fail here with a sentence naming what happened, not make every
    # assertion below pass over an empty match set.
    assert len(matches) == 1, (
        "expected exactly one `export const RUN_LIST_LIMIT_MAX = <number>;` "
        f"declaration in {RUN_PAGING_TS}, found {len(matches)}. If the browser now "
        "reads this bound from the server instead of declaring it, delete this test "
        "and say so — do not relax the pattern."
    )
    return int(matches[0])


def test_the_typescript_literal_is_parseable():
    """Guards the regex, so the parity check below cannot become vacuous."""
    assert _typescript_literal() > 0


def test_the_served_parameter_maximum_is_the_python_constant(spec):
    """FastAPI's `le=RUN_PAGE_MAX` reaches the wire as the same number.

    This half needs no TypeScript at all, and it is the half that would catch a
    refactor that moved the bound off the route signature — at which point the
    browser's copy would be right about a constant nothing enforced.
    """
    parameters = spec["paths"][RUNS_PATH]["get"]["parameters"]
    limits = [p for p in parameters if p["name"] == "limit"]
    assert len(limits) == 1, "the run listing declares exactly one `limit` parameter"
    schema = limits[0]["schema"]
    # `int | None` renders as an `anyOf`, so the bound sits on the integer branch.
    branches = schema.get("anyOf", [schema])
    maxima = [b["maximum"] for b in branches if "maximum" in b]
    assert maxima == [routes.RUN_PAGE_MAX]


def test_the_browser_literal_matches_the_server_bound():
    """The one assertion the residue asked for: the two copies are the same number.

    MUTATION: changing either `RUN_PAGE_MAX` or `RUN_LIST_LIMIT_MAX` alone turns this
    RED with both values named, which is the whole point — the failure has to say
    which side moved.
    """
    literal = _typescript_literal()
    assert literal == routes.RUN_PAGE_MAX, (
        f"apps/web/src/lib/runPaging.ts declares RUN_LIST_LIMIT_MAX = {literal} while "
        f"routes.RUN_PAGE_MAX is {routes.RUN_PAGE_MAX}. They are one bound with two "
        "expressions: the browser decides, without a round trip, whether it can "
        "re-read everything on screen in ONE bounded request, and a client that "
        "believes a larger bound than the server enforces will ask for a page the "
        "server clamps — reading fewer runs than it thinks it read."
    )


def test_the_parameter_description_states_the_same_bound(spec):
    """And the prose a caller reads is interpolated, not retyped.

    `_RUN_LIMIT_DESC` is an f-string over `RUN_PAGE_MAX` — this asserts that property
    through the SERVED document rather than by reading the f-string, so a future
    slice that hardcodes the number into the description is caught here.
    """
    parameters = spec["paths"][RUNS_PATH]["get"]["parameters"]
    description = next(p for p in parameters if p["name"] == "limit")["description"]
    assert f"1–{routes.RUN_PAGE_MAX}." in description

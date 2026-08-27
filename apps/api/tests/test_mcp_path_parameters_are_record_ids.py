"""``mcp.client._PATH_PARAM`` — the dot was never an id character.

THE DEFECT, REPRODUCED OVER THE REAL CLIENT AGAINST THE REAL APP
================================================================
``_PATH_PARAM`` was ``^[A-Za-z0-9._~-]{1,128}$``. Its comment called the class
"deliberately narrow" and explained the three extra characters as headroom "so a
legitimate id shape change does not require a security review". One of the three
was ``.`` — and ``.`` and ``..`` are not id characters, they are PATH SEGMENTS.
Measured before the fix:

* ``isaac_get_run(run_id="..")`` returned ``isError: false`` and handed the agent
  the **record** detail. ``httpx`` resolved ``/api/experiments/{id}/runs/..`` to
  ``/api/experiments/{id}``, so a request for a run silently answered with a
  record.
* ``isaac_get_run(run_id=".")`` reached ``GET .../runs`` — the run LIST.
* ``isaac_update_draft(run_id="..")`` reached ``PATCH /api/experiments/{id}``,
  **a route that is not in** ``policy.OPERATIONS`` **at all.** It was inert only
  because that route's own body model happened to answer ``422`` for the payload
  the tool sends — an accident of two unrelated schemas, not a boundary.

WHY EVERY EXISTING REJECTION CASE MISSED IT
===========================================
Two suites already test hostile path parameters, and between them they try
``../../etc/passwd``, ``abc/../../x``, ``%2e%2e%2f``, ``../export``,
``..%2fexport``, ``x/../../export``, ``a b``, ``a\\nb`` and ``""``. **Every one of
them fails on the ``/``, the ``%``, the space, the newline or the emptiness — not
one of them fails on the dot.** So a bare ``..`` walked straight through a suite
that read as though it were testing exactly this. §3 below re-runs those same
strings and additionally asserts, per string, that each is refused for a reason
that survives removing the slash — which is the assertion the old suites could not
make about themselves.

THE FIX, AND THE ONE THING IT MUST NOT BE READ AS
=================================================
The pattern is now the id SHAPE: ``\\A[0-9A-Z]{26}\\Z``. It is not a guess —
``policy.OPERATIONS`` declares exactly two placeholders, ``experiment_id`` and
``run_id`` (§1 asserts that, so a third one added later cannot inherit this
predicate silently), and both name ids minted by ``isaac_records.ids``.

It is RESTATED rather than imported, because
``test_mcp_boundaries.test_nothing_in_the_mcp_package_imports_the_truth_path``
forbids this package from importing ``isaac_records`` at all (``CLAUDE.md`` §13):
the MCP layer reaches ISAAC only through ISAAC's own HTTP routes. §2 is what makes
the copy safe — it asserts the copy and ``isaac_records.ids.RECORD_ID_RE`` accept
and reject the same strings, so drift between them fails here rather than at a
boundary.

It does NOT tighten the HTTP routes. ``routes.ExperimentId`` keeps its
128-character bound and still answers ``404`` for a well-formed id the workspace
does not hold; an id-FORMAT check on a public route is a product change, and
``_EXPERIMENT_ID_MAX_LENGTH``'s own note says so. The MCP boundary is allowed to be
strictly narrower than the API it calls — that is what a boundary is for.
"""

from __future__ import annotations

import asyncio
import copy
import re

import pytest

import isaac_api.workspace as ws
from isaac_api.mcp.client import ApiRefusal, AsgiApiClient, _PATH_PARAM
from isaac_api.mcp.policy import OPERATIONS

EXPERIMENT_ID = "01MCPPATHPARAM0000000000AB"


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    return ws


@pytest.fixture()
def client(workspace):
    from isaac_api.app import create_app

    exp = ws.create_experiment(
        "MCP path-parameter fixture",
        {"kind": "synthetic"},
        copy.deepcopy(ws._full_draft()),
        id=EXPERIMENT_ID,
    )
    exp.save_versioned()
    return AsgiApiClient(create_app())


def _call(client, operation_id: str, **path_params):
    return asyncio.run(client.call(operation_id, path_params=path_params))


# =============================================================================
# 1. The two reproductions, as tests
# =============================================================================


def test_a_DOTDOT_run_id_no_longer_hands_back_the_RECORD(client):
    """The first reproduction. ``..`` climbed from a run to its record."""
    with pytest.raises(ApiRefusal) as raised:
        _call(client, "get_run", experiment_id=EXPERIMENT_ID, run_id="..")

    assert raised.value.code == "invalid_path_parameter"
    assert raised.value.data["parameter"] == "run_id"


def test_a_DOTDOT_run_id_no_longer_reaches_an_UNALLOWLISTED_ROUTE(client):
    """The second, and the more serious of the two.

    ``update_run_draft`` with ``run_id=".."`` resolved to
    ``PATCH /api/experiments/{id}`` — the rename route, which is **not** in
    ``OPERATIONS``. The allowlist is the whole point of this layer: an operation
    reaching a route the policy never granted is the boundary failing, whatever the
    route then does with the body.
    """
    with pytest.raises(ApiRefusal) as raised:
        asyncio.run(
            client.call(
                "update_run_draft",
                path_params={"experiment_id": EXPERIMENT_ID, "run_id": ".."},
                json_body={"confirmed_by_user": True, "values": {}},
                if_match='"x.0"',
            )
        )

    assert raised.value.code == "invalid_path_parameter"


def test_a_SINGLE_DOT_run_id_no_longer_reaches_the_run_LIST(client):
    """Not in the original report, and found while reproducing it.

    ``.`` resolved ``/runs/.`` to ``/runs`` and returned the LIST — a different
    route, a different response shape, and ``isError: false``. A fix aimed only at
    ``..`` would have left it.
    """
    with pytest.raises(ApiRefusal) as raised:
        _call(client, "get_run", experiment_id=EXPERIMENT_ID, run_id=".")

    assert raised.value.code == "invalid_path_parameter"


def test_a_DOTTED_experiment_id_is_refused_too(client):
    """Both placeholders, not just the run one."""
    with pytest.raises(ApiRefusal) as raised:
        _call(client, "get_experiment", experiment_id="..")

    assert raised.value.code == "invalid_path_parameter"
    assert raised.value.data["parameter"] == "experiment_id"


def test_a_REAL_ID_still_works_so_the_pattern_is_not_a_blanket_refusal(client):
    """The negative control. A pattern matching nothing would pass everything above."""
    result = _call(client, "get_experiment", experiment_id=EXPERIMENT_ID)

    assert result.status == 200
    assert result.body["id"] == EXPERIMENT_ID


def test_an_UNKNOWN_but_WELL_FORMED_id_still_reaches_the_API(client):
    """The boundary refuses SHAPES, and leaves EXISTENCE to the API.

    This is the property that keeps the refusal honest: a 26-character id this
    workspace does not hold must still produce the API's own ``404``, not a
    client-side refusal that would make "no such record" indistinguishable from
    "malformed request".
    """
    result = _call(client, "get_experiment", experiment_id="01NOSUCHRECORD000000000000")

    assert result.status == 404


# =============================================================================
# 2. The copy is pinned to the original it may not import
# =============================================================================


def test_the_pattern_agrees_with_the_truth_cores_RECORD_ID_RE(client):
    """The whole justification for restating the regex instead of importing it.

    ``mcp`` may not import ``isaac_records`` (``CLAUDE.md`` §13, held mechanically
    by ``test_nothing_in_the_mcp_package_imports_the_truth_path``), so the pattern
    is a deliberate duplicate. A deliberate duplicate is only safe while something
    fails when it drifts, and this is that something. The test file is allowed the
    import that the package is not.
    """
    from isaac_records.ids import RECORD_ID_RE

    assert _PATH_PARAM.pattern == RECORD_ID_RE.pattern

    candidates = [
        "01ARZ3NDEKTSV4RRFFQ69G5FAV",  # a real ULID shape
        "0" * 26,
        "A" * 26,
        "A" * 25,
        "A" * 27,
        "a" * 26,  # lowercase: refused by both
        "01ARZ3NDEKTSV4RRFFQ69G5FA.",
        "..",
        ".",
        "",
        "A" * 26 + "\n",  # the `$`-vs-`\Z` case `isaac_records.ids` exists for
        "\n" + "A" * 26,
    ]
    for value in candidates:
        assert bool(_PATH_PARAM.match(value)) == bool(RECORD_ID_RE.match(value)), value


def test_the_pattern_is_anchored_with_Z_not_dollar(client):
    """``^…$`` would admit a trailing newline, at the path-segment boundary.

    ``isaac_records.ids`` documents this at length as the reason its own predicate
    is ``\\A…\\Z``. Asserted here as BEHAVIOUR rather than as a string comparison,
    so it survives the pattern being rewritten.
    """
    assert _PATH_PARAM.match("A" * 26) is not None
    assert _PATH_PARAM.match("A" * 26 + "\n") is None


def test_every_MCP_PLACEHOLDER_names_an_id_this_pattern_describes(client):
    """The pattern's justification is a measurement, so it is re-measured.

    ``_PATH_PARAM`` is a record-id shape because every placeholder the client can
    render names a record id. That is true today over ``OPERATIONS``; a third
    placeholder — a label, a slug, a date — must not silently inherit a predicate
    that was derived for ids.
    """
    placeholders = set()
    for operation in OPERATIONS.values():
        placeholders |= set(re.findall(r"\{([a-z_]+)\}", operation.path_template))

    assert placeholders == {"experiment_id", "run_id"}, (
        "a new MCP path placeholder appeared. `_PATH_PARAM` applies the RECORD ID "
        f"shape to every one of them; confirm that is right for: {placeholders}"
    )


# =============================================================================
# 3. The old cases still pass — and now for a reason that survives the slash
# =============================================================================


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "abc/../../x",
        "%2e%2e%2f",
        "a b",
        "a\nb",
        "",
        "../export",
        "..%2fexport",
        "x/../../export",
    ],
)
def test_the_previously_tested_hostile_values_are_still_refused(client, hostile):
    """Regression cover for the two existing suites, restated over this client."""
    with pytest.raises(ApiRefusal) as raised:
        _call(client, "get_experiment", experiment_id=hostile)

    assert raised.value.code == "invalid_path_parameter"


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "abc/../../x", "../export", "x/../../export"],
)
def test_those_values_were_refused_ONLY_for_their_SLASHES_before(client, hostile):
    """The measurement that explains why nine hostile strings missed the dot.

    Strip the slashes and re-apply the OLD character class: every one of these
    still matches it. So each was refused for a character that is obviously not an
    id character, and none of them ever exercised the dot at all — which is how a
    suite can look like it covers path traversal and not cover ``..``.

    This is a statement about the old pattern, kept as a test so the reasoning is
    checkable rather than asserted in a comment.
    """
    old_pattern = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
    without_slashes = hostile.replace("/", "")

    assert old_pattern.match(without_slashes), (
        f"{hostile!r} would have been refused by the old class even without its "
        "slashes, so it did test something beyond the slash"
    )
    # And the new pattern refuses it on the SHAPE, slashes or not.
    assert _PATH_PARAM.match(without_slashes) is None

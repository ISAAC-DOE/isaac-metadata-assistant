"""``If-Match: *`` on ``POST .../discard``, and the guard that used to run too late.

TWO DEFECTS, BOTH ON THE ONE IRREVERSIBLE OPERATION IN THIS API
===============================================================
This file covers the two findings that are specific to ``discard`` and that no
existing suite could reach, because both were measured rather than reasoned about.

**1. ``If-Match: *`` satisfied the precondition and destroyed an unread edit.**
Measured over HTTP, on ``main``, with one client and one record::

    same client, stale real ETag  ->  412 stale_write
    same client, If-Match: *      ->  200 {"discarded_title": "IMPORTANT NEW WORK"}

The ``discarded_title`` in that ``200`` is the title a CONCURRENT writer had just
committed. The discard did not merely destroy work it had not read — it reported
the destroyed title back without ever having compared a version.

That is not a hardening preference, it is a copy/behaviour mismatch. The
operation's own published description ends *"There is no undo. That is why the
confirmation and the precondition are both required."* ``*`` makes the second of
those two vacuous while the sentence goes on claiming it. And ``*`` is precisely
the idiom for *"I hold no validator"* — the one state in which an irreversible
removal must not proceed.

**THE FIX IS SCOPED TO THIS ONE CALL SITE, AND THAT IS THE POINT.**
``_check_if_match`` returns early on ``*`` by design (RFC 9110: it matches iff the
resource exists), and ``test_mcp_if_match_wildcard.py`` pins that acceptance as a
contract, with an explicit instruction that it must not be "made consistent" by
tightening. That pin stands and is not weakened here. Run removal and asset
removal must keep accepting ``*``: both are recoverable by re-adding, and both
already refuse a published artifact with a ``409``. Sweeping all three would be
exactly the silent contract change that test exists to prevent — so §2 below
asserts, positively, that the other two still accept it.

**2. The path-safety guard ran AFTER the durable delete it was guarding.**
``_remove_experiment_dir`` proved the target was a direct child of the scope root
— but it is the LAST step of ``discard_experiment``, and the step before it is a
durable delete that has already committed. Measured, with a scope root reached
through a symlink: the durable delete committed, the guard raised, the caller got
an untyped ``500``, the record was still readable and still listed, and every
retry did the same thing. The condition is a property of the filesystem, not of
the moment, so the ``discard_experiment`` docstring's promise that "re-issuing the
discard converges" was true of a transient store failure and false of this one.

This is the same shape as the reset defect this repository already has a written
record of (``main`` before ``#183``/``#187``): a destructive path that answered
with a recoverable-sounding refusal AFTER it had already destroyed something and
could never succeed on retry. **Fail-closed describes the DECISION, not its
TIMING, and on a destructive path the timing is the whole thing.**

WHAT THIS FILE DELIBERATELY DOES NOT ASSERT
===========================================
It does not assert that the guard's refusal became a typed 4xx. It did not, and
that is deliberate rather than unfinished: the condition is not reachable over
HTTP without a symlink into the scope root, nobody's request caused it, and
``routes``' own ``_PROBE_STRUCTURAL_ERRORS`` note argues the case directly — a
genuine server-side anomaly converted into a client-blaming ``4xx`` is a defect
that stops being investigated. What had to change is that it can no longer
destroy anything first, and §3 asserts exactly that and no more.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

import isaac_api.workspace as ws

EXPERIMENT_ID = "01DISCARDWILDCARD000000001"
OTHER_ID = "01DISCARDWILDCARD000000002"


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A private ORDINARY-scope workspace with no database configured.

    Ordinary scope for the reason the two sibling discard suites give: it is the
    scope a scientist's own record lives in and the only one a successful discard
    is reachable from at all.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    return ws


def _client():
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _make(experiment_id: str = EXPERIMENT_ID, *, runs: tuple[str, ...] = ()):
    """An export-ready ordinary-scope experiment. Composes no scientific value."""
    exp = ws.create_experiment(
        "Wildcard discard fixture",
        {"kind": "synthetic"},
        copy.deepcopy(ws._full_draft()),
        id=experiment_id,
    )
    run_draft = copy.deepcopy(exp.draft)
    for label in runs:
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    return ws.load_experiment(experiment_id)


def _etag(client, experiment_id: str = EXPERIMENT_ID) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _discard(client, experiment_id: str = EXPERIMENT_ID, *, if_match: str):
    return client.post(
        f"/api/experiments/{experiment_id}/discard",
        json={"confirmed_by_user": True},
        headers={"If-Match": if_match},
    )


# =============================================================================
# 1. The wildcard is refused, and the record survives
# =============================================================================


def test_a_WILDCARD_precondition_is_refused_and_NOTHING_is_removed(workspace):
    """The headline case: ``*`` no longer authorises an irreversible removal."""
    _make()
    client = _client()

    response = _discard(client, if_match="*")

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "wildcard_precondition_refused", body
    assert body["experiment_id"] == EXPERIMENT_ID, body

    # The record is untouched by every measure the discard suite uses.
    assert ws.load_experiment(EXPERIMENT_ID) is not None
    listed = [row["id"] for row in client.get("/api/experiments").json()["experiments"]]
    assert EXPERIMENT_ID in listed
    assert (ws.scope_root(None) / EXPERIMENT_ID).exists()


def test_the_refusal_names_NO_VERSION_because_a_wildcard_carries_none(workspace):
    """The reason this is a ``400`` and not a ``412``, asserted rather than argued.

    A ``412`` body carries ``expected_rev`` / ``expected_version`` — the two fields
    a client reads to recover. ``*`` carries no version at all
    (``_first_client_token`` returns ``None`` for it, by design), so a ``412`` here
    would echo nulls into exactly those fields and assert a staleness that does not
    exist. A ``412`` would also promise that a re-read and a retry converge, and
    re-reading changes nothing whatsoever about ``*``.
    """
    _make()
    client = _client()

    body = _discard(client, if_match="*").json()

    for absent in ("expected_rev", "expected_version", "current_rev"):
        assert absent not in body, (
            f"the wildcard refusal published {absent!r}, which would describe a "
            "version comparison that never happened"
        )


def test_the_wildcard_refusal_is_NOT_the_malformed_one(workspace):
    """``If-Match: *`` is well-formed under RFC 9110, and is not called malformed.

    Two conditions, two typed ``error`` values inside one already-published status.
    Collapsing them would tell a client with a CORRECT header that their header is
    malformed, and send them hunting a syntax bug that is not there — while the
    actual remedy is different in kind: a malformed header is respelt, a wildcard
    is REPLACED by a validator the client must first go and read.
    """
    _make()
    client = _client()

    wildcard = _discard(client, if_match="*")
    malformed = _discard(client, if_match="not-a-validator")

    assert wildcard.status_code == malformed.status_code == 400
    assert wildcard.json()["error"] == "wildcard_precondition_refused"
    assert malformed.json()["error"] == "malformed_if_match"
    assert wildcard.json()["error"] != malformed.json()["error"]


def test_an_OMITTED_header_is_still_428_and_not_the_wildcard_refusal(workspace):
    """The wildcard branch must not swallow the absent-header case.

    ``_is_wildcard_if_match(None)`` is ``False`` on purpose: an absent header is a
    different condition with a different status and a different remedy.
    """
    _make()
    client = _client()

    response = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/discard",
        json={"confirmed_by_user": True},
    )

    assert response.status_code == 428, response.text
    assert response.json()["error"] == "precondition_required"
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_a_REAL_ETAG_still_discards_so_the_refusal_is_not_a_blanket_block(workspace):
    """The negative control. A fix that refused every discard would pass §1 alone."""
    _make()
    client = _client()

    response = _discard(client, if_match=_etag(client))

    assert response.status_code == 200, response.text
    assert response.json()["discarded_experiment_id"] == EXPERIMENT_ID
    assert ws.load_experiment(EXPERIMENT_ID) is None


@pytest.mark.parametrize("spelling", ["*", " * ", "\t*\n"])
def test_the_wildcard_is_recognised_THROUGH_WHITESPACE(workspace, spelling):
    """The predicate normalises exactly as ``_check_if_match`` does.

    This is the assertion that makes the shared predicate worth having. The two
    call sites must agree about what a wildcard IS, and the direction a private
    second copy would drift in is the bad one: a spelling this stopped recognising
    is a wildcard the destructive path would wave through, because the refusal is
    an early return and ``_check_if_match`` would go on returning ``None`` for it.
    """
    _make()
    client = _client()

    response = _discard(client, if_match=spelling)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "wildcard_precondition_refused"
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_the_wildcard_refusal_is_reached_BEFORE_any_domain_check_writes(workspace):
    """A canonical example refused for BEING canonical, not for the wildcard.

    The ordering matters and is asserted rather than assumed: the domain refusals
    are cheapest-first and all write nothing, and the precondition is checked after
    them. So a canonical id must still answer ``409 canonical_example_record`` even
    with ``*``, and NOT the new ``400`` — otherwise the wildcard check would have
    been hoisted above the domain refusals and changed which reason a caller is
    told.
    """
    client = _client()
    session = client.post("/api/tutorial/sessions").json()["session_id"]

    response = client.post(
        f"/api/experiments/{ws.SEED_READY_ID}/discard",
        json={"confirmed_by_user": True},
        headers={"If-Match": "*", "X-Isaac-Tutorial-Session": session},
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "canonical_example_record"


# =============================================================================
# 2. THE OTHER TWO REMOVALS STILL ACCEPT `*` — the contract that must not move
# =============================================================================


def test_RUN_REMOVAL_still_accepts_a_wildcard(workspace):
    """Positive control for the boundary of the change.

    ``test_mcp_if_match_wildcard.py`` pins ``*`` as accepted and instructs that it
    must not be tightened "for consistency". Run removal is recoverable by
    re-adding and already refuses a published artifact with a ``409``, so the
    reasoning that singles out discard does not reach it. Asserted POSITIVELY here
    so that a future sweep which tightened all three would fail this file rather
    than quietly widening the refusal.
    """
    exp = _make(runs=("run-a",))
    run_id = exp.sorted_runs()[0].id
    client = _client()

    response = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/runs/{run_id}/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": "*"},
    )

    assert response.status_code == 200, response.text
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_a_RECORD_LEVEL_WRITE_still_accepts_a_wildcard(workspace):
    """The same control on a non-removal write: ``*`` is untouched there too."""
    _make()
    client = _client()

    response = client.patch(
        f"/api/experiments/{EXPERIMENT_ID}",
        json={"title": "Renamed by a client holding no validator"},
        headers={"If-Match": "*"},
    )

    assert response.status_code == 200, response.text
    assert ws.load_experiment(EXPERIMENT_ID).title == (
        "Renamed by a client holding no validator"
    )


def test_exactly_ONE_operation_refuses_the_wildcard(workspace):
    """Stated as a count over the published contract, not as three examples.

    The claim the description makes is *"this is the only operation in this API
    that refuses it"*. A claim of that shape has to be checked as a claim, because
    the failure mode is a SECOND operation quietly acquiring the refusal — which no
    per-operation test would notice.
    """
    from isaac_api.app import create_app

    spec = create_app().openapi()
    refusing = sorted(
        f"{method.upper()} {path}"
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
        if isinstance(operation, dict)
        and "wildcard_precondition_refused" in json.dumps(operation)
    )

    assert refusing == ["POST /api/experiments/{experiment_id}/discard"], refusing


# =============================================================================
# 3. The path-safety guard runs BEFORE the destruction it guards
# =============================================================================


def _reroute_through_a_symlink(experiment_id: str, tmp_path: Path) -> None:
    """Make the record's directory a symlink, so it resolves outside the root.

    This is the only way to reach the guard at all: nothing this application does
    can produce such a directory, which is why the defect was not HTTP-reachable
    and why it is reproduced here rather than left as prose.
    """
    root = ws.scope_root(None)
    elsewhere = tmp_path / "outside-the-scope-root"
    elsewhere.mkdir(exist_ok=True)
    shutil.move(str(root / experiment_id), str(elsewhere / experiment_id))
    (root / experiment_id).symlink_to(elsewhere / experiment_id)


def test_the_guard_refuses_BEFORE_the_durable_delete_commits(workspace, tmp_path, monkeypatch):
    """The ordering defect, asserted as an ordering and not as an outcome.

    A spy store records whether the durable delete was reached. Before the fix it
    WAS: the rows went, the guard then raised, and the record stayed readable with
    no way to converge. Asserting only "the record is still here" would pass on the
    broken code too, because the broken code also left the record readable — it
    just left it readable with its durable rows already destroyed.
    """
    _make()
    _reroute_through_a_symlink(EXPERIMENT_ID, tmp_path)

    reached = []

    class _SpyStore:
        def discard(self, exp):
            reached.append(exp.id)
            return 3

    monkeypatch.setattr(ws, "_ordinary_store", lambda session_id: _SpyStore())

    with pytest.raises(ValueError):
        ws.discard_experiment(ws.load_experiment(EXPERIMENT_ID))

    assert reached == [], (
        "the durable delete committed before the path-safety guard refused — the "
        "rows are gone, the record is still readable, and no retry can converge"
    )
    assert ws.load_experiment(EXPERIMENT_ID) is not None


def test_the_guard_message_carries_NO_ABSOLUTE_PATH(workspace, tmp_path):
    """A raised message is a log line, and a log line is an exfiltration surface.

    The message used to interpolate the fully RESOLVED target, so it published an
    absolute server path — through an untyped ``500``, at that. ``CLAUDE.md``
    forbids it and ``workspace``'s own logging note says why. The name is taken
    from the REQUESTED directory rather than the resolved one, so a symlink cannot
    report the name of whatever it points at either.
    """
    _make()
    _reroute_through_a_symlink(EXPERIMENT_ID, tmp_path)

    with pytest.raises(ValueError) as raised:
        ws.discard_experiment(ws.load_experiment(EXPERIMENT_ID))

    message = str(raised.value)
    assert "/" not in message, message
    assert str(tmp_path) not in message, message
    assert "outside-the-scope-root" not in message, message
    # It still names the record, which is what makes the refusal actionable.
    assert EXPERIMENT_ID in message, message


def test_an_ORDINARY_discard_still_removes_the_directory(workspace):
    """Negative control: the guard is still permissive about a normal record.

    A "fix" that refused every directory would satisfy both assertions above.
    """
    _make()

    outcome = ws.discard_experiment(ws.load_experiment(EXPERIMENT_ID))

    assert outcome["durable_rows_removed"] == 0
    assert not (ws.scope_root(None) / EXPERIMENT_ID).exists()
    assert ws.load_experiment(EXPERIMENT_ID) is None


def test_the_guard_is_still_enforced_at_the_REMOVAL_ITSELF(workspace, tmp_path):
    """The check is deliberately performed twice, and the second one is load-bearing.

    ``_remove_experiment_dir`` is also reached by the worked-example RESET, which
    never passes through ``discard_experiment``. Moving the guard forward INSTEAD OF
    duplicating it would have relocated the hole rather than closed it, so the
    inner check is asserted directly rather than trusted.
    """
    _make(OTHER_ID)
    _reroute_through_a_symlink(OTHER_ID, tmp_path)

    with pytest.raises(ValueError):
        ws._remove_experiment_dir(
            ws.load_experiment(OTHER_ID).dir, session_id=None
        )

    assert ws.load_experiment(OTHER_ID) is not None

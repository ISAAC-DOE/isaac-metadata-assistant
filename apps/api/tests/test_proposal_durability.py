"""PROPOSAL DURABILITY THROUGH THE DURABLE POSTGRESQL REPOSITORY.

THE GAP THIS FILE CLOSES, MEASURED RATHER THAN ASSERTED
=======================================================
Persistent ingestion proposals live at ``state["proposals"]`` inside the experiment
state document (``proposals.STATE_KEY``), and that document is upserted whole into
``isaac_experiments.state``. So durability through PostgreSQL is very likely BY
CONSTRUCTION — and until this file, "very likely" was the whole of the evidence.
Measured at ``7ff8194``, in the main checkout::

    grep -ac proposal apps/api/tests/test_experiment_repository.py   -> 0  (exit 1)
    rg    -c  proposal apps/api/tests/test_experiment_repository.py  ->     (exit 1)
    python3 byte-count of b'proposal' in that file                   -> 0

and the durable-restart family in ``test_run_rows_become_authoritative.py``
(``_survives_a_restart``, lines 1314-1592) has no proposal member — its single
``proposal`` occurrence is a loose docstring word in the TRANSCRIPT case, and the
transcript path stores Unmapped Notes, not ``IngestionProposal``s.

FILESYSTEM durability was already proven: ``test_ingestion_proposals.py`` reads
``experiment.json`` off disk and asserts a planted entry survives a save. What was
unproven is the round trip through the DURABLE repository — the one the product's
own "create a proposal, restart the application, the proposal is still there"
workflow depends on, and the one whose failure mode is silent.

``CLAUDE.md`` §11 records the reason an inference is not enough here: the
``changed_at_rev`` defect was missed by a local implementer AND by an independent
reviewer, and was caught only by CI against a real PostgreSQL, because the
engine-gated suites skip everywhere else.

WHAT IS PROVEN, AND WHERE
=========================
The file has two halves, and they prove different things.

* **The LOCAL half** (no engine, runs everywhere) builds the scenario against the
  FILESYSTEM repository and exercises the comparison this file's durability claims
  rest on. It is where the NEGATIVE CONTROLS live: six separate ways a proposal can
  be silently lost, each one asserted to make :func:`assert_the_same_document` go
  RED. A comparison that could only go green would be a gap wearing the costume of
  a proof — ``test_run_row_parity``'s phrase, and its rule.
* **The REAL-ENGINE half** (``@real_engine``) runs the same scenario against a real
  PostgreSQL and asserts the round trip: the durable row matches the working copy
  after EVERY proposal act, a pod restart reproduces the whole document, an entry
  this build cannot read survives verbatim and is still counted, and — the control
  that makes the other three worth reading — the assertion goes RED when the stored
  ``proposals`` key is dropped OUT OF BAND, and green again once it is restored.

THE COMPARISON IS OVER THE WHOLE SERIALISED STATE, NEVER OVER PICKED KEYS. A test
that checks three fields cannot see a fourth being dropped, and the fields most at
risk here (``accepted_value``, ``applied_via``, ``applied_rev``,
``applied_target_digest``, ``client_request_key``, ``start_char``/``end_char``, and
the whole ``history`` tuple) are exactly the ones nobody would think to pick.
``proposal_change_revs`` is compared too, and it is a separate TOP-LEVEL key rather
than a field of a proposal — see ``workspace.Experiment.proposal_change_revs`` —
so a reader that copied ``proposals`` alone would drop the change feed's sequence
coordinate for every proposal and nothing else would notice.

THE ENGINE GATE
===============
``test_run_row_parity``'s gate is REUSED RATHER THAN COPIED, exactly as
``test_discard_an_unsubmitted_experiment.py`` reuses it and for the reason that file
states: it is a consent variable checked first and unconditionally
(``ISAAC_RUN_REAL_ENGINE_PARITY``), plus a loopback-only ``PGHOST`` check, plus a
``PGHOSTADDR`` refusal, plus the ``PGDATABASE`` gate, plus a probe that the tables
exist. A second, weaker gate written here would be exactly the drift those layers
exist to prevent.

**A SKIP IS NOT A PASS, AND THE GUARD FOR THAT IS THE CI STEP, NOT A TEST IN HERE.**
Stated precisely, because the near-miss is easy to write and reads as true:
``test_run_row_parity``'s
``test_the_real_engine_is_present_when_the_environment_demands_it`` fails on an
unreachable engine whenever ``ISAAC_REQUIRE_REAL_ENGINE_PARITY`` is set — but it
runs only where that FILE is collected, and CI runs each real-engine suite as its
own one-file-by-path step, so it does NOT protect this one. What protects this one
is its own step in ``.github/workflows/ci.yml`` (*"Prove ingestion proposals survive
the durable round trip"*), which reads the skip count back off the run and fails the
build if it is non-zero, and asserts an exact scenario count so a DELETED test is
not silent either. A duplicate in-file guard would add a second number describing
one suite — the mistake the parity step's own comments warn about at length.

DATA BOUNDARY: none. Every value is synthetic and unmistakably so. The local half
writes into a ``tmp_path`` workspace and opens no connection at all. The real-engine
half writes into CI's throwaway ``postgres:18`` service container and into a
``tmp_path`` workspace. NO HOSTED OR SLAC DATABASE IS CONTACTED BY ANYTHING IN THIS
FILE, and no migration is applied anywhere.

**THE PRODUCTION-DERIVED ``records`` TABLE IS NAMED ONCE, AND THIS SENTENCE USED TO
SAY IT WAS NOT.** An earlier revision of this paragraph read *"the production-derived
``records`` table is neither read nor named"*, and an independent review measured that
false against the file it describes: ``test_the_test_statements_pass_the_write_statement_policy``
passes the string ``"SELECT record_id FROM records"`` to ``WriteStatementPolicy.check``
and requires it to be REFUSED. That is the NEGATIVE CONTROL which stops a permissive
policy object making the three positive assertions above it vacuous, and it is the
ONLY SQL string in this file that names the table. **No statement naming ``records``
is ever executed against any engine here** — ``check`` is a pure tokenizer that opens
nothing — and nothing in this file reads a row of it.

*(Measured, not asserted, because the first attempt at this correction over-claimed
in turn: ``grep -an '\brecords\b'`` over this file returns twelve lines, and most
are the ENGLISH VERB — "``CLAUDE.md`` §11 records the reason", "``subject`` records
who proposed". The table is referred to in exactly three places: this paragraph, that
test's own docstring, and the one SQL string. "The only occurrence of the name" would
have been false; "the only SQL string naming it" is what the file supports.)*

The correction is kept in place rather than quietly swapped, because ``CLAUDE.md``
§11 catalogues exactly this shape: a governance sentence published without being
checked against the file it describes, in the paragraph §12's "Data boundary" field
is read from.
"""

from __future__ import annotations

import copy
import json
import shutil

import pytest
from fastapi.testclient import TestClient

import isaac_api.experiment_repository as repo
import isaac_api.identity as identity
import isaac_api.proposals as proposals
import isaac_api.routes as routes
import isaac_api.workspace as ws

from test_run_row_parity import (
    _as_document,
    _execute,
    _query,
    real_engine,
)

# =============================================================================
# 1. the scenario — one builder, used by BOTH halves
# =============================================================================
#
# ONE BUILDER, DELIBERATELY. The local half can run it on a developer machine and
# the real-engine half runs the identical sequence against PostgreSQL, so "the
# scenario is well formed" and "the scenario survives the database" are separate
# claims established by separate runs over the same acts. If the two diverged, the
# local half would stop being evidence about the thing CI measures.

#: Who the fixture verifier vouches for. Synthetic; no deployment mints this.
ACTOR = "ada.lovelace"

NOTE_TEXT = (
    "SYNTHETIC FIXTURE — the pellet was CuO2 and the cell sat at 300 K throughout"
)

#: The one record-scoped target: a closed enum the official schema declares.
RECORD_PATH = "system.technique"
#: A record-level address written on a run through the override writer.
RUN_OVERRIDE_PATH = "sample.material.name"
#: A run-level draft field.
RUN_FIELD_PATH = "context.temperature_K"

#: A real member of ``system.technique``'s enum, read from the VENDORED SCHEMA at
#: import rather than written out. A hand-copied literal would be a second copy of
#: the document ``CLAUDE.md`` §1 makes the authority, free to rot into a test that
#: passes for the wrong reason — ``test_ingestion_proposals.py``'s rule.
RECORD_VALUE = routes._record_enum_fields()[RECORD_PATH][0]

#: AN ENTRY THIS BUILD CANNOT READ. ``IngestionProposal.from_state`` refuses it (no
#: ``experiment_id``, no ``note_id``, no target, no rule), so ``_hydrate_proposals``
#: files it under ``unreadable_proposals`` and ``to_state`` writes it back out
#: untouched. Contract DEC-6: preserved VERBATIM, counted, surfaced as unreadable,
#: and never coerced, parsed, walked or dropped.
#:
#: It is the entry MOST LIKELY to be lost by a serialisation round trip, because it
#: is the one thing in the document that no model on either side can represent — and
#: it is the same shape as the ``pending: 7`` finding ``CLAUDE.md`` §11 records.
PLANTED_UNREADABLE = {
    "proposal_id": "P-FROM-A-BUILD-THIS-ONE-CANNOT-READ",
    "mystery": {"nested": [1, 2, 3]},
}


def _arm_the_fixture_verifier(monkeypatch) -> None:
    """A deployment that CAN attribute, so ACCEPT is reachable.

    ``accept`` answers ``409 human_actor_required`` in every default-configured
    deployment, because no trusted authentication boundary exists in this build
    (``CLAUDE.md`` §15). That is a CONFIGURATION fact, not a defect — and it would
    make the ``accepted`` shape, with its ``accepted_value``, ``accepted_from``,
    ``applied_via``, ``applied_run_id``, ``applied_rev`` and
    ``applied_target_digest``, unreachable from this suite. Six stored fields that
    are only ever non-``None`` on an accepted proposal are exactly the six a round
    trip could drop unobserved, so the fixture verifier is armed here for the same
    reason ``test_ingestion_proposals.py``'s ``armed`` fixture exists: the refusal
    path and the success path are both real behaviour.

    No shipped deploy artifact sets these two variables — ``test_deploy_config.py``
    pins that — so this is deliberately a configuration no deployment has.
    """
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)


def _client() -> TestClient:
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _etag(client: TestClient, rid: str) -> str:
    response = client.get(f"/api/experiments/{rid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _create_proposal(client, rid, *, path, value, **extra) -> str:
    body = {
        "note_id": extra.pop("note_id"),
        "target_field_path": path,
        "proposed_value": value,
        "rule": "SYNTHETIC FIXTURE — the token after `the pellet was` matched a "
        "material label",
    }
    body.update(extra)
    response = client.post(
        f"/api/experiments/{rid}/proposals",
        json=body,
        headers={"If-Match": _etag(client, rid)},
    )
    assert response.status_code == 200, response.text
    return response.json()["proposal"]["proposal_id"]


def _review(client, rid, pid, **body):
    body.setdefault("confirmed_by_user", True)
    response = client.post(
        f"/api/experiments/{rid}/proposals/{pid}/review",
        json=body,
        headers={"If-Match": _etag(client, rid)},
    )
    assert response.status_code == 200, response.text
    return response.json()["proposal"]


def _plant_unreadable(rid: str, entry: object) -> None:
    """Append a raw entry to the WORKSPACE FILE, out of band.

    This is not an act and no ``after_each`` checkpoint follows it: it simulates a
    document written by a build that understood something this one does not, which
    is the only way an unreadable entry can come to exist. The DURABLE row does not
    carry it until the next real save rewrites the whole document — which is
    precisely the property the next act then measures.
    """
    path = ws.workspace_root() / rid / "experiment.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault(proposals.STATE_KEY, []).append(entry)
    path.write_text(json.dumps(state), encoding="utf-8")


def build_the_scenario(client: TestClient, after_each=None) -> str:
    """One record carrying every proposal shape this build can store.

    Returns the experiment id. ``after_each(rid, label)`` — when given — is called
    after each act that WRITES, INCLUDING the create (the durable row exists from
    that moment), and never after the out-of-band plant, which by construction
    leaves the durable row one save behind.

    THE SHAPES, and why each is here rather than for coverage's sake:

    * an ACCEPTED record-scoped proposal — the only shape carrying the six
      ``accepted_*``/``applied_*`` fields, and a two-transition history;
    * a REJECTED run-scoped proposal with a reason — a second two-transition
      history, through a different act, on a proposal that names a run;
    * a WITHDRAWN run-scoped proposal — a third act, and the one whose save is what
      carries the planted entry into the database;
    * an OPEN proposal carrying ``start_char``, ``end_char`` and
      ``client_request_key`` — the three optional fields nothing else here sets;
    * one UNREADABLE raw entry.
    """

    created = client.post("/api/experiments", json={"title": "Proposal durability"})
    assert created.status_code == 201, created.text
    rid = created.json()["id"]

    def checkpoint(label: str) -> None:
        if after_each is not None:
            after_each(rid, label)

    checkpoint("create the experiment")

    run = client.post(
        f"/api/experiments/{rid}/runs",
        json={"label": "R1"},
        headers={"If-Match": _etag(client, rid)},
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["run"]["id"]
    checkpoint("add a run")

    note = client.post(
        f"/api/experiments/{rid}/notes",
        json={"text": NOTE_TEXT, "source": "typed_note"},
        headers={"If-Match": _etag(client, rid)},
    )
    assert note.status_code == 201, note.text
    note_id = note.json()["note"]["id"]
    checkpoint("capture the note behind every proposal")

    to_accept = _create_proposal(
        client, rid, path=RECORD_PATH, value=RECORD_VALUE, note_id=note_id
    )
    checkpoint("propose the record-scoped value")
    to_reject = _create_proposal(
        client,
        rid,
        path=RUN_OVERRIDE_PATH,
        value="Cu2O",
        note_id=note_id,
        run_id=run_id,
    )
    checkpoint("propose the run-scoped override")
    to_withdraw = _create_proposal(
        client,
        rid,
        path=RUN_FIELD_PATH,
        value=300.0,
        note_id=note_id,
        run_id=run_id,
    )
    checkpoint("propose the run-scoped field")
    _create_proposal(
        client,
        rid,
        path=RUN_OVERRIDE_PATH,
        value="CuO",
        note_id=note_id,
        run_id=run_id,
        start_char=4,
        end_char=10,
        client_request_key="synthetic-durability-key-1",
    )
    checkpoint("propose the one that stays open")

    _review(client, rid, to_accept, action="accept", accepted_from="candidate")
    checkpoint("accept")
    _review(
        client,
        rid,
        to_reject,
        action="reject",
        reason="SYNTHETIC FIXTURE — the label was the crucible, not the pellet",
    )
    checkpoint("reject")

    # OUT OF BAND, AND DELIBERATELY BETWEEN TWO ACTS. No checkpoint follows it.
    _plant_unreadable(rid, PLANTED_UNREADABLE)

    _review(
        client,
        rid,
        to_withdraw,
        action="withdraw",
        reason="SYNTHETIC FIXTURE — the reading was the setpoint, not the sample",
    )
    checkpoint("withdraw, and carry the unreadable entry into the durable row")

    return rid


# =============================================================================
# 2. the comparison, and what it must be able to say NO to
# =============================================================================

_ABSENT = object()


def assert_the_same_document(actual: object, expected: dict, what: str) -> None:
    """WHOLE-DOCUMENT equality, with a message that names the keys that differ.

    NOT A PICKED-KEY COMPARISON, and that is the entire design. Every durability
    claim in this file goes through this one function, so a field added to
    ``IngestionProposal.to_state`` tomorrow is covered on the day it is added
    without anybody remembering to extend a list — and a field DROPPED by a future
    serialisation change fails here rather than passing three hand-picked
    assertions.

    The diff in the message is deliberately over TOP-LEVEL keys plus the two
    proposal-bearing ones rendered in full: a bare ``assert a == b`` over a whole
    experiment document produces an unreadable wall, and an unreadable failure is
    one a future session is tempted to re-run rather than read.
    """
    if not isinstance(actual, dict):
        raise AssertionError(
            f"{what}: expected a state document and got {type(actual).__name__}"
        )
    if actual == expected:
        return
    differing = sorted(
        key
        for key in set(actual) | set(expected)
        if actual.get(key, _ABSENT) != expected.get(key, _ABSENT)
    )

    def rendered(document: dict, key: str) -> str:
        return json.dumps(document.get(key, None), sort_keys=True, default=str)

    raise AssertionError(
        f"{what}: the stored document is not the one this record holds.\n"
        f"  top-level keys that differ: {differing}\n"
        f"  actual   proposals            = {rendered(actual, proposals.STATE_KEY)}\n"
        f"  expected proposals            = {rendered(expected, proposals.STATE_KEY)}\n"
        f"  actual   proposal_change_revs = {rendered(actual, 'proposal_change_revs')}\n"
        f"  expected proposal_change_revs = {rendered(expected, 'proposal_change_revs')}"
    )


def assert_the_scenario_is_not_vacuous(document: dict) -> None:
    """AN EMPTY ROUND TRIP SURVIVES TRIVIALLY, so the premise is asserted, not assumed.

    ``[] == []`` is true of a database that stored nothing, of a reader that dropped
    everything, and of a builder that silently failed. Every claim in this file is
    worthless without this, which is why it runs inside each of them rather than
    once in a fixture the others could stop calling.
    """
    stored = document.get(proposals.STATE_KEY)
    assert isinstance(stored, list), stored
    readable = [entry for entry in stored if entry != PLANTED_UNREADABLE]
    assert len(readable) == 4, f"expected four readable proposals, got {len(readable)}"
    assert PLANTED_UNREADABLE in stored, "the unreadable entry never reached the document"
    assert {entry["state"] for entry in readable} == {
        proposals.STATE_ACCEPTED,
        proposals.STATE_REJECTED,
        proposals.STATE_WITHDRAWN,
        proposals.STATE_OPEN,
    }, sorted(entry["state"] for entry in readable)
    # THE HISTORIES ARE THE AUDIT CLAIM. A truncated one is a silent audit failure —
    # the proposal is still there, still in the right state, and the act that put it
    # there is gone.
    multi = [entry for entry in readable if len(entry["history"]) > 1]
    assert len(multi) == 3, [len(entry["history"]) for entry in readable]
    # ...and the ACCEPTED shape really carries the six fields only it can carry.
    accepted = next(
        entry for entry in readable if entry["state"] == proposals.STATE_ACCEPTED
    )
    assert accepted["accepted_value"] == RECORD_VALUE, accepted
    assert accepted["accepted_from"] == proposals.ACCEPTED_FROM_CANDIDATE, accepted
    assert accepted["applied_via"] == proposals.APPLIED_VIA_RECORD_ENUM, accepted
    assert isinstance(accepted["applied_rev"], int), accepted
    assert isinstance(accepted["applied_target_digest"], str), accepted
    # THE ACTOR IS ON THE TRANSITION, NOT ON THE PROPOSAL, and the distinction is the
    # feature's rather than this test's: ``IngestionProposal.subject`` records who
    # PROPOSED — ``unattributed``, i.e. ``None``, in every deployment, because
    # creating a proposal requires no actor — while the accept's actor is recorded on
    # the ``accept`` transition. A durability test that asserted the wrong one would
    # be pinning a field that is ``None`` on both sides of the round trip and would
    # prove nothing about the attribution actually being carried.
    assert accepted["subject"] is None, accepted
    accept_transition = accepted["history"][-1]
    assert accept_transition["action"] == proposals.ACTION_ACCEPT, accept_transition
    assert accept_transition["actor_subject"] == ACTOR, accept_transition
    assert accept_transition["actor_trust_basis"] == identity.FIXTURE_VERIFIER, (
        accept_transition
    )
    # ...and the OPEN one carries the three optional fields nothing else sets.
    still_open = next(
        entry for entry in readable if entry["state"] == proposals.STATE_OPEN
    )
    assert (still_open["start_char"], still_open["end_char"]) == (4, 10), still_open
    assert still_open["client_request_key"] == "synthetic-durability-key-1", still_open
    # THE SEQUENCE COORDINATE IS A SEPARATE TOP-LEVEL KEY. A reader that copied
    # `proposals` alone would drop it for every proposal and nothing else would say so.
    positions = document.get("proposal_change_revs")
    assert isinstance(positions, dict) and len(positions) == 4, positions


def assert_the_list_route_agrees(client: TestClient, rid: str) -> None:
    """WHAT A SCIENTIST WOULD SEE, as well as what the document holds.

    A document can be perfect while the surface over it is not, and the reverse.
    ``total`` counts the READABLE proposals only — measured, not assumed: the
    unreadable entry is reported separately under ``unreadable_entries`` and is
    deliberately never rendered, because this server cannot say what a refused entry
    contains without inventing it (contract DEC-6).

    THE RECORD'S OWN SCREENS ARE CHECKED IN THE SAME BREATH. ``CLAUDE.md`` §11
    records that one malformed persisted value once made ``GET /api/experiments``
    answer **500** and took My Experiments down for every record; an unreadable
    proposal is the same shape, so "it survived" is only half the claim and "the
    list still answers" is the other half.

    Verified against the FILESYSTEM repository by the local half of this file, and
    re-asserted against PostgreSQL AFTER A RESTART by the real-engine half — which
    is what makes the numbers here measurements rather than guesses.
    """
    listed = client.get(f"/api/experiments/{rid}/proposals")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 4, body
    assert body["unreadable_entries"] == 1, body
    assert body["by_state"] == {
        proposals.STATE_OPEN: 1,
        proposals.STATE_ACCEPTED: 1,
        proposals.STATE_REJECTED: 1,
        proposals.STATE_SUPERSEDED: 0,
        proposals.STATE_WITHDRAWN: 1,
    }, body["by_state"]
    assert client.get(f"/api/experiments/{rid}").status_code == 200
    assert client.get("/api/experiments").status_code == 200


def _the_note_id(client: TestClient, rid: str) -> str:
    listed = client.get(f"/api/experiments/{rid}/notes")
    assert listed.status_code == 200, listed.text
    return listed.json()["notes"][0]["id"]


def assert_a_later_act_still_lands(client: TestClient, rid: str, before: dict) -> dict:
    """THE RECORD IS STILL WRITABLE, and the four already there are untouched.

    A restored working copy that can be READ but not written on is a different and
    quieter failure than one that lost content, and it is the one a read-only
    assertion cannot see.

    THE READABLE AND UNREADABLE HALVES ARE COMPARED SEPARATELY, and that is the
    document's own arrangement rather than a convenience:
    ``workspace._proposal_state_payload`` writes the canonically ordered readable
    proposals FIRST and appends the unreadable raw entries after them, so a fifth
    proposal lands in the MIDDLE of the stored array, not at its end. A naive
    "everything but the last element is unchanged" comparison would fail here for
    the wrong reason — and would have, before this was measured.
    """
    key = proposals.STATE_KEY
    readable_before = [e for e in before[key] if e != PLANTED_UNREADABLE]
    _create_proposal(
        client, rid, path=RECORD_PATH, value=RECORD_VALUE, note_id=_the_note_id(client, rid)
    )
    after = ws.load_experiment(rid).to_state()
    readable_after = [e for e in after[key] if e != PLANTED_UNREADABLE]

    assert len(readable_after) == len(readable_before) + 1, (
        "the later act did not append exactly one proposal"
    )
    assert readable_after[: len(readable_before)] == readable_before, (
        "a later act rewrote or reordered the proposals that were already there"
    )
    assert after[key][-1] == PLANTED_UNREADABLE, (
        "the unreadable entry moved or was rewritten by a later save"
    )
    return after


# --- the six ways a proposal can be silently lost -----------------------------
#
# Each mutilation is a REAL failure mode rather than an arbitrary edit, and each is
# asserted below to make `assert_the_same_document` go RED. They exist because this
# repository has repeatedly shipped guards that passed while being wrong: a
# comparison is only evidence if something is known to fail it.


def _drop_the_proposals_key(document: dict) -> dict:
    """A writer that never serialised the key at all."""
    out = copy.deepcopy(document)
    out.pop(proposals.STATE_KEY)
    return out


def _empty_the_proposals_list(document: dict) -> dict:
    """A reader that treated "cannot read this" as "there is nothing here"."""
    out = copy.deepcopy(document)
    out[proposals.STATE_KEY] = []
    return out


def _drop_the_unreadable_entry(document: dict) -> dict:
    """DEC-6's failure: the one entry the model cannot represent is discarded."""
    out = copy.deepcopy(document)
    out[proposals.STATE_KEY] = [
        entry for entry in out[proposals.STATE_KEY] if entry != PLANTED_UNREADABLE
    ]
    return out


def _truncate_a_history(document: dict) -> dict:
    """The audit trail loses its most recent act while the state keeps it."""
    out = copy.deepcopy(document)
    for entry in out[proposals.STATE_KEY]:
        if isinstance(entry, dict) and len(entry.get("history") or []) > 1:
            entry["history"] = entry["history"][:-1]
            return out
    raise AssertionError("no multi-transition history to truncate — fixture is wrong")


def _blank_an_accepted_field(document: dict) -> dict:
    """One of the six fields only an accepted proposal carries goes missing."""
    out = copy.deepcopy(document)
    for entry in out[proposals.STATE_KEY]:
        if isinstance(entry, dict) and entry.get("state") == proposals.STATE_ACCEPTED:
            entry["applied_target_digest"] = None
            return out
    raise AssertionError("no accepted proposal to blank — fixture is wrong")


def _drop_the_change_revs(document: dict) -> dict:
    """The change feed's sequence coordinate, which is NOT inside ``proposals``."""
    out = copy.deepcopy(document)
    out.pop("proposal_change_revs")
    return out


#: ``(label, mutilate, the top-level keys the comparison must report)``.
#:
#: THE THIRD ELEMENT IS WHY THESE ARE CONTROLS AND NOT MERELY DIFFERENT ASSERTIONS.
#: Five of the six damage ``proposals`` and the sixth damages
#: ``proposal_change_revs`` — a SEPARATE top-level key — so requiring the exact key
#: list catches a mutilation that accidentally disturbed something else and would
#: otherwise have produced a red for the wrong reason.
MUTILATIONS = [
    ("the whole proposals key is dropped", _drop_the_proposals_key, ["proposals"]),
    ("the proposals list comes back empty", _empty_the_proposals_list, ["proposals"]),
    ("the unreadable entry is discarded", _drop_the_unreadable_entry, ["proposals"]),
    ("one history entry is truncated", _truncate_a_history, ["proposals"]),
    (
        "an accepted proposal's applied digest is blanked",
        _blank_an_accepted_field,
        ["proposals"],
    ),
    (
        "proposal_change_revs is dropped",
        _drop_the_change_revs,
        ["proposal_change_revs"],
    ),
]


# =============================================================================
# 3. reading the durable row — the TEST's own statements, never the application's
# =============================================================================
#
# These are TEST statements, defined here for `test_run_row_parity`'s stated reason:
# `db_write`'s primary guarantee is that every statement the WRITE PATH issues is a
# module-level constant in the application, so a test-only read must not be added to
# `experiment_repository`. They still go through `policy.check(...)`, so they are
# bound by the same owned-table and forbidden-verb rules as everything else.

Q_TEST_STORED_STATE = "SELECT state FROM isaac_experiments WHERE experiment_id = %s"

#: THE OUT-OF-BAND MUTATION the round trip's own control uses: the stored document
#: loses its ``proposals`` key while every other key stays exactly as it was. It is
#: a legal, policy-passing statement against an owned table, issued by the TEST.
#:
#: ``::text`` IS EXPLICIT ON PURPOSE. ``jsonb`` has three ``-`` operators (``text``,
#: ``text[]``, ``integer``) and an untyped literal leaves the choice to PostgreSQL's
#: operator resolution. It resolves correctly today; naming the type removes a
#: question that would otherwise be answered for the first time in CI, on a machine
#: with no engine to reproduce it.
Q_TEST_DROP_THE_STORED_PROPOSALS_KEY = (
    "UPDATE isaac_experiments SET state = state - 'proposals'::text"
    " WHERE experiment_id = %s"
)

#: The restore. The WHOLE document is written back, not a patch, so the control
#: cannot leave the row in a third state that is neither broken nor original.
Q_TEST_RESTORE_THE_STORED_DOCUMENT = (
    "UPDATE isaac_experiments SET state = %s::jsonb WHERE experiment_id = %s"
)


def _document_in_the_database(rid: str) -> dict:
    rows = _query(Q_TEST_STORED_STATE, (rid,))
    assert rows, f"no durable row exists for {rid}: nothing was persisted at all"
    return _as_document(rows[0][0])


def _document_in_the_workspace(rid: str) -> dict:
    path = ws.workspace_root() / rid / "experiment.json"
    assert path.exists(), f"no working copy exists for {rid}"
    return json.loads(path.read_text(encoding="utf-8"))


def _hydrate_after_the_restart(rid: str) -> None:
    """One hydration pass, ASSERTED TO HAVE PUT THIS RECORD BACK ON DISK.

    ── WHY THE ASSERTION IS ON THE FILE AND NOT ON A ``None`` CHECK LATER ──────────
    ``test_run_row_parity.py:1249-1258``, inside
    ``test_parity_survives_a_pod_restart_and_hydration_leaves_the_rows_untouched``,
    records this as a MEASURED correction rather
    than a style: ``ws.load_experiment`` **hydrates on a miss by design** (a record
    created before a pod restart has a durable row and no directory, so a deep link
    to it must not 404). So ``assert load_experiment(rid) is not None`` after a
    restart passes whether or not ``hydrate()`` did anything at all — the load would
    have restored it either way — and a test asserting only that would be describing
    ``load_experiment``'s fallback while claiming to describe hydration. The parity
    suite guards this with ``restored >= 1`` on the count. An earlier revision of this
    file dropped that guard while its docstrings went on saying "hydrates it back",
    which is the claim-versus-proof gap an independent review caught.

    THE FILE IS A STRICTLY STRONGER GUARD THAN THE COUNT, AND THAT IS WHY IT IS THE
    ONE THAT ALWAYS RUNS. ``restored >= 1`` says the pass wrote SOME directory; in a
    shared throwaway database populated by earlier CI steps that could be anybody's.
    ``experiment.json`` existing at THIS id, checked BEFORE anything calls
    ``load_experiment``, says the pass wrote THIS one. Both are asserted where both
    are available.

    ``HydrationSkippedRows`` is raised AFTER the loop, so every restorable row —
    including this test's — has already been written by the time it is raised. It
    means some OTHER row in the shared throwaway database does not describe the
    record it is filed under, which later steps of CI's ``postgres-migration`` job
    plant deliberately. That is not this test's subject. The COUNT is unavailable on
    that path, which is precisely why the file check is the primary evidence and the
    count is an extra rather than the only one.
    """
    path = ws.workspace_root() / rid / "experiment.json"
    assert not path.exists(), (
        "the premise of a restart is that the working copy is GONE; this pass would "
        "have had nothing to prove"
    )
    try:
        restored = repo.repository().hydrate()
    except repo.HydrationSkippedRows:
        restored = None
    if restored is not None:
        assert restored >= 1, restored
    assert path.exists(), (
        "hydration did not restore this record's working copy. Asserted HERE, before "
        "any load: `ws.load_experiment` hydrates on a miss, so a later `is not None` "
        "would hide this exact failure."
    )


# =============================================================================
# 4. THE LOCAL HALF — no engine, and it is where the controls live
# =============================================================================


@pytest.fixture()
def filesystem_workspace(tmp_path, monkeypatch):
    """A private workspace with NO database: the filesystem repository, as locally."""
    root = tmp_path / "ws"
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(root))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    _arm_the_fixture_verifier(monkeypatch)
    return root


def test_the_scenario_is_not_vacuous_and_the_comparison_PASSES_on_it(
    filesystem_workspace,
):
    """THE PREMISE, ASSERTED BEFORE ANYTHING RESTS ON IT.

    Two claims that the six controls below are worthless without: the builder really
    produced four proposals in four different states with three multi-transition
    histories and one unreadable entry, and :func:`assert_the_same_document` really
    returns quietly on a document that matches. A control suite whose comparison
    always raised would report six passes and prove nothing.

    IT ALSO EXERCISES EVERY SHARED ASSERTION THE REAL-ENGINE HALF USES, and that is
    deliberate rather than incidental. There is no PostgreSQL and no container
    runtime on a developer machine in this project, so CI is the FIRST execution of
    the six ``@real_engine`` cases; running their helpers here against the
    filesystem repository is what turns their numbers — ``total == 4``,
    ``unreadable_entries == 1``, the ``by_state`` distribution, the append position
    of a later proposal — into things that were measured rather than reasoned.
    """
    client = _client()
    assert repo.repository().backend == repo.BACKEND_FILESYSTEM, (
        "this half is written for the filesystem repository"
    )
    rid = build_the_scenario(client)

    document = ws.load_experiment(rid).to_state()
    assert_the_scenario_is_not_vacuous(document)
    # The working copy on disk IS the serialised state — the property every
    # durable comparison below leans on, measured rather than assumed.
    assert_the_same_document(
        _document_in_the_workspace(rid), document, "the working copy"
    )
    assert_the_same_document(copy.deepcopy(document), document, "an untouched copy")
    assert_the_list_route_agrees(client, rid)
    assert_a_later_act_still_lands(client, rid, document)


def test_the_checkpoint_plumbing_really_fires_after_every_act(filesystem_workspace):
    """THE REAL-ENGINE PER-ACT CASE'S STRUCTURE, REHEARSED WHERE IT CAN BE RUN.

    ``test_REAL_ENGINE_the_durable_row_matches_the_working_copy_after_every_act``
    passes a callback into the builder and asserts it fired ten times. If the
    builder ever stopped calling it, that test would pass having asserted nothing —
    which is the failure mode this file's docstring says this repository keeps
    shipping — and CI would be the only place anybody found out.

    So the same plumbing runs here against the filesystem repository: ten
    checkpoints, and at each one the working copy on disk exists and IS the
    serialised state. That last part is what the durable case then compares the
    database against, so a checkpoint firing before the file was written would be a
    real defect in the durable case rather than a flake.
    """
    client = _client()
    observed: list[str] = []

    def after_each(rid: str, label: str) -> None:
        observed.append(label)
        assert_the_same_document(
            _document_in_the_workspace(rid),
            ws.load_experiment(rid).to_state(),
            f"the working copy after: {label}",
        )

    build_the_scenario(client, after_each=after_each)
    assert len(observed) == 10, observed
    assert observed[0] == "create the experiment", observed
    assert observed[-1].startswith("withdraw"), observed


def test_the_restart_helper_FAILS_when_hydration_does_not_restore_this_record(
    filesystem_workspace, monkeypatch
):
    """THE CONTROL FOR :func:`_hydrate_after_the_restart`, and it runs WITHOUT an engine.

    That helper carries the only assertion standing between the three real-engine
    restart cases and a hydration that restored nothing — and an independent review
    caught an earlier revision of this file having dropped it, because
    ``ws.load_experiment`` HYDRATES ON A MISS, so a later ``is not None`` passes
    either way. A guard added in response to that finding and then never observed
    firing would be the same class of defect one level up.

    BOTH ARMS ARE MUTATED, because the helper makes two different claims:

    * **the COUNT arm.** The filesystem repository's ``hydrate()`` returns ``0`` by
      construction — there is no store to restore from — so simply running the helper
      here drives ``restored >= 1`` red. No monkeypatching is needed for this one,
      which is what makes it a real mutation rather than a staged one.
    * **the FILE arm, which is the stronger claim and the one a count cannot make.**
      A repository whose ``hydrate()`` reports restoring five records while writing
      nothing for THIS id passes ``restored >= 1`` and must still be refused. In a
      database shared with earlier CI steps that is not hypothetical: another step's
      rows are exactly what would make a non-zero count true about somebody else.

    AND THE HELPER IS THEN SHOWN TO PASS when hydration really does write the file,
    so the two raises above are attributable to the mutations and not to a helper
    that raises unconditionally.
    """
    client = _client()
    rid = build_the_scenario(client)
    path = ws.workspace_root() / rid / "experiment.json"

    # THE PREMISE GUARD FIRST: a "restart" that did not lose the working copy proves
    # nothing, and the helper says so before it hydrates anything.
    with pytest.raises(AssertionError, match="working copy is GONE"):
        _hydrate_after_the_restart(rid)

    saved = path.read_text(encoding="utf-8")
    path.unlink()

    # ARM 1 — the count. The filesystem repository restores nothing, and says so.
    with pytest.raises(AssertionError):
        _hydrate_after_the_restart(rid)
    assert not path.exists(), "nothing should have been restored here"

    # ARM 2 — a hydration that reports success and writes nothing for this record.
    class _RestoredSomebodyElse:
        backend = repo.BACKEND_POSTGRES

        def hydrate(self) -> int:
            return 5

    monkeypatch.setattr(repo, "repository", lambda *a, **k: _RestoredSomebodyElse())
    with pytest.raises(AssertionError, match="did not restore this record"):
        _hydrate_after_the_restart(rid)

    # AND THE HELPER PASSES when the file really comes back. Written by a stand-in
    # rather than by a real store, because there is no engine here — what is being
    # controlled is the helper's verdict, not the store's behaviour.
    class _RestoredThisOne:
        backend = repo.BACKEND_POSTGRES

        def hydrate(self) -> int:
            path.write_text(saved, encoding="utf-8")
            return 1

    monkeypatch.setattr(repo, "repository", lambda *a, **k: _RestoredThisOne())
    _hydrate_after_the_restart(rid)
    assert ws.load_experiment(rid) is not None


def test_the_test_statements_pass_the_write_statement_policy():
    """THE THREE SQL STATEMENTS ARE LEGAL BEFORE ANY ENGINE IS ASKED.

    ``WriteStatementPolicy`` is pure and needs no connection, so a statement this
    file would have discovered was REFUSED only in CI can be refused here instead.
    That matters more than usual: there is no PostgreSQL on a developer machine in
    this project, so a policy refusal in one of the real-engine cases would surface
    as a red build with no local reproduction.

    THE NEGATIVE CONTROL IS THE SECOND HALF. A policy object that accepted
    everything would pass the loop above and prove nothing, so a statement naming
    the production-derived ``records`` table — the one table this application must
    never reference — is required to be REFUSED.
    """
    import isaac_api.db_write as dbw

    policy = dbw.WriteStatementPolicy()
    for sql in (
        Q_TEST_STORED_STATE,
        Q_TEST_DROP_THE_STORED_PROPOSALS_KEY,
        Q_TEST_RESTORE_THE_STORED_DOCUMENT,
    ):
        assert policy.check(sql) == sql.strip(), sql

    with pytest.raises(dbw.WriteRefused):
        policy.check("SELECT record_id FROM records")


@pytest.mark.parametrize(
    "label,mutilate,expected_keys", MUTILATIONS, ids=[m[0] for m in MUTILATIONS]
)
def test_the_comparison_FAILS_on_each_way_a_proposal_can_be_silently_lost(
    filesystem_workspace, label, mutilate, expected_keys
):
    """SIX NEGATIVE CONTROLS, each a real silent-loss mode rather than an arbitrary edit.

    Each asserts BEHAVIOUR — the comparison raises — and not the presence of a
    string. ``CLAUDE.md`` §11 records two guards in this repository that passed
    while being wrong because they pinned a literal rather than an outcome; this is
    the shape that does not.

    The mutilation is applied to a COPY and the original is asserted still good
    afterwards, so no control leaves a mutation standing for the next one.
    """
    client = _client()
    rid = build_the_scenario(client)
    document = ws.load_experiment(rid).to_state()
    assert_the_scenario_is_not_vacuous(document)

    broken = mutilate(document)
    assert broken != document, f"{label}: the mutilation changed nothing"
    with pytest.raises(AssertionError) as raised:
        assert_the_same_document(broken, document, "a deliberately damaged document")
    # THE COMPARISON NAMED EXACTLY WHAT WAS DAMAGED. Asserting only that it raised
    # would pass on a comparison that raises unconditionally, and asserting a bare
    # substring would pass on a message that prints the word regardless — both are
    # shapes this repository has shipped. The key list is COMPUTED by the function
    # under test and is empty on a document that matches.
    assert f"keys that differ: {expected_keys}" in str(raised.value), str(raised.value)

    # AND THE MUTATION IS NOT LEFT APPLIED. The comparison is green again on the
    # untouched document, which is what makes the raise above attributable to the
    # mutilation rather than to anything this test did on the way there.
    assert_the_same_document(
        ws.load_experiment(rid).to_state(), document, "the record after the control"
    )


# =============================================================================
# 5. THE REAL ENGINE — opt-in, loopback-only, and it WRITES
# =============================================================================
#
# EVERYTHING ABOVE RUNS WITHOUT A DATABASE. These four do not: they are the only
# assertions in this repository that a proposal survives PostgreSQL, and they are
# the reason the file exists. They SKIP everywhere else, including the ordinary CI
# backend job, and a skip is a visible non-result.
#
# SIX, COUNTING §6. Two further `@real_engine` cases were added at the end of this
# file on 2026-09-02, for the run-scoped acceptance this section's scenario cannot
# express (`applied_run_id` is `None` in every document above). "These four" is left
# as it is because it is TRUE OF THE FOUR THAT FOLLOW IT; the total is six, and
# `.github/workflows/ci.yml`'s `expected_scenarios` is 20 rather than 14 for the
# same reason.


@pytest.fixture()
def durable_workspace(tmp_path, monkeypatch):
    """A private workspace with the REAL database left configured.

    ``PGHOST`` and friends are deliberately NOT cleared — these tests exist to talk
    to the engine. ``test_run_row_parity``'s fixture, for its reason.
    """
    root = tmp_path / "ws"
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(root))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    _arm_the_fixture_verifier(monkeypatch)
    return root


def _assert_the_backend_is_durable() -> None:
    """Without this, a misconfigured environment would run every assertion below
    against the FILESYSTEM repository, read an empty table, and pass — green, and
    meaningless. ``test_run_row_parity._new_experiment``'s guard, for its reason."""
    backend = repo.repository().backend
    assert backend == repo.BACKEND_POSTGRES, backend


@real_engine
def test_REAL_ENGINE_the_durable_row_matches_the_working_copy_after_every_act(
    durable_workspace,
):
    """EVERY PROPOSAL ACT IS PERSISTED IN THE WRITE THAT PERFORMS IT.

    Asserted after each act rather than once at the end, because "the final state
    reached the database" and "each act reached the database" are different claims:
    a route that persisted nothing until the last write would satisfy the first and
    would lose everything to a pod roll in between, which is the only failure this
    feature can actually suffer in production.

    The comparison is WHOLE-DOCUMENT, so it also proves that no act persisted the
    proposals while dropping something else, or the reverse.
    """
    _assert_the_backend_is_durable()
    client = _client()
    observed: list[str] = []

    def after_each(rid: str, label: str) -> None:
        observed.append(label)
        assert_the_same_document(
            _document_in_the_database(rid),
            _document_in_the_workspace(rid),
            f"the durable row after: {label}",
        )

    rid = build_the_scenario(client, after_each=after_each)

    # THE CHECKPOINTS REALLY RAN. A callback that was never invoked — because the
    # builder stopped calling it, or because an early return skipped it — would make
    # this test pass having asserted nothing, which is the exact failure the file's
    # docstring says this repository keeps shipping.
    assert len(observed) == 10, observed

    stored = _document_in_the_database(rid)
    assert_the_scenario_is_not_vacuous(stored)
    assert_the_same_document(
        stored, ws.load_experiment(rid).to_state(), "the finished durable row"
    )


@real_engine
def test_REAL_ENGINE_every_proposal_and_its_history_survives_a_pod_restart(
    durable_workspace,
):
    """THE PRODUCT WORKFLOW: create a proposal, restart the application, it is there.

    THE WORKSPACE IS AN ``emptyDir`` CACHE, NOT THE RECORD. A pod roll empties it and
    the durable row is all that is left, so this deletes the workspace outright and
    hydrates it back — ``test_run_row_parity``'s pod-restart idiom, and the shape
    ``test_run_rows_become_authoritative``'s ``_survives_a_restart`` family uses for
    every other kind of content a record carries. Proposals had no member of that
    family, which is the gap this file's docstring measures.

    The comparison is over the WHOLE serialised state, before and after, both taken
    through ``Experiment.to_state()`` so that the run ordering Stage 2b may legally
    permute is normalised by the same function on both sides and cannot manufacture
    a difference that is not about proposals.
    """
    _assert_the_backend_is_durable()
    client = _client()
    rid = build_the_scenario(client)

    before = ws.load_experiment(rid).to_state()
    assert_the_scenario_is_not_vacuous(before)
    assert_the_same_document(
        _document_in_the_database(rid), before, "the durable row before the restart"
    )

    # THE POD RESTARTS: the emptyDir workspace is gone. That the working copy really
    # went, and that hydration really put it back, are both asserted inside
    # `_hydrate_after_the_restart` — see its docstring for why the second one cannot
    # be left to a later `load_experiment`.
    shutil.rmtree(ws.workspace_root())

    _hydrate_after_the_restart(rid)
    restored = ws.load_experiment(rid)
    assert restored is not None, "the record did not come back from the database"

    after = restored.to_state()
    assert_the_scenario_is_not_vacuous(after)
    assert_the_same_document(after, before, "the record after a pod restart")

    # AND THE RECORD IS STILL WRITABLE AFTERWARDS, so the restored working copy is a
    # usable basis for the next act rather than merely a readable one — the property
    # `test_run_row_parity`'s restart case asserts for runs, asserted here for
    # proposals. A fifth proposal lands, and the four that were there are untouched.
    reopened = assert_a_later_act_still_lands(client, rid, after)
    assert_the_same_document(
        _document_in_the_database(rid), reopened, "the durable row after the next act"
    )


@real_engine
def test_REAL_ENGINE_an_unreadable_entry_survives_the_restart_and_is_still_counted(
    durable_workspace,
):
    """CONTRACT DEC-6, THROUGH POSTGRESQL — the case a round trip is most likely to eat.

    An entry this build cannot read has no model on either side of the wire, so it
    survives only if the document is carried whole. It must come back BYTE-FOR-BYTE,
    the list route must still COUNT it rather than render it, and — the half that
    makes this the ``pending: 7`` finding's shape rather than merely its cousin — the
    record's own screens must still answer ``200`` over it.
    """
    _assert_the_backend_is_durable()
    client = _client()
    rid = build_the_scenario(client)
    before = ws.load_experiment(rid).to_state()
    assert PLANTED_UNREADABLE in before[proposals.STATE_KEY], (
        "the premise is that the unreadable entry reached the document"
    )

    shutil.rmtree(ws.workspace_root())
    _hydrate_after_the_restart(rid)

    restored = ws.load_experiment(rid)
    assert restored is not None
    assert restored.unreadable_proposals == [PLANTED_UNREADABLE], (
        "the entry this build cannot read did not survive the durable round trip"
    )
    assert PLANTED_UNREADABLE in restored.to_state()[proposals.STATE_KEY], (
        "the entry was hydrated but would not be written back out"
    )
    assert_the_list_route_agrees(client, rid)


@real_engine
def test_REAL_ENGINE_the_round_trip_assertion_FAILS_on_a_dropped_key_and_recovers(
    durable_workspace,
):
    """THE CONTROL FOR THE THREE ABOVE, AND IT MUTATES THE REAL ROW.

    The three real-engine cases immediately above can only report green or red, and a
    suite that
    has never been observed going red over a genuine defect is not evidence that it
    would. So the stored ``proposals`` key is DROPPED out of band — by the test,
    through a legal policy-passing statement, which is exactly the situation a
    silent serialisation regression would produce — and the round-trip assertion is
    required to go RED.

    THEN IT IS RESTORED, AND THE ASSERTION IS REQUIRED TO GO GREEN AGAIN. A control
    that left the row damaged would poison every later test sharing the database,
    and "it failed once" without "it passes once the cause is removed" does not
    establish that the failure was caused by the mutation.

    The literal ``'proposals'`` in the statement is pinned to the constant below, so
    the control cannot rot into an update of a key nothing uses.
    """
    _assert_the_backend_is_durable()
    assert proposals.STATE_KEY == "proposals", (
        "Q_TEST_DROP_THE_STORED_PROPOSALS_KEY names this key as a SQL literal"
    )
    client = _client()
    rid = build_the_scenario(client)

    expected = ws.load_experiment(rid).to_state()
    assert_the_scenario_is_not_vacuous(expected)
    original = _document_in_the_database(rid)
    assert_the_same_document(original, expected, "the durable row before the control")

    assert _execute(Q_TEST_DROP_THE_STORED_PROPOSALS_KEY, (rid,)) == 1
    damaged = _document_in_the_database(rid)
    # THE DAMAGE IS EXACTLY ONE KEY, measured independently of the comparison under
    # test. Without this the statement could have emptied the row, rewritten the
    # whole document, or done nothing at all, and the raise below would read the
    # same in every case.
    assert set(expected) - set(damaged) == {proposals.STATE_KEY}, sorted(damaged)
    assert set(damaged) - set(expected) == set(), sorted(damaged)

    with pytest.raises(AssertionError) as raised:
        assert_the_same_document(damaged, expected, "the damaged durable row")
    # THE MESSAGE NAMES THE KEY IT COMPUTED, not a literal this test supplied: the
    # rendered diff prints `proposals` unconditionally, so asserting the bare word
    # would pass on a comparison that had noticed nothing. This asserts the computed
    # differing-key LIST, which is empty on a document that matches.
    assert f"keys that differ: ['{proposals.STATE_KEY}']" in str(raised.value), str(
        raised.value
    )

    # AND A RESTART OVER THE DAMAGED ROW LOSES THE PROPOSALS, which is the outcome
    # the whole file exists to make impossible to reach silently. Asserted here so
    # the control measures the CONSEQUENCE and not only the comparison.
    shutil.rmtree(ws.workspace_root())
    _hydrate_after_the_restart(rid)
    lost = ws.load_experiment(rid)
    assert lost is not None
    assert lost.proposals == [] and lost.unreadable_proposals == [], (
        "the drop was supposed to make the proposals unrecoverable; if they came "
        "back, this control is not measuring what it claims to"
    )

    # RESTORE, and the assertion recovers.
    assert (
        _execute(
            Q_TEST_RESTORE_THE_STORED_DOCUMENT,
            (json.dumps(original, sort_keys=True), rid),
        )
        == 1
    )
    assert_the_same_document(
        _document_in_the_database(rid), expected, "the durable row after the restore"
    )
    shutil.rmtree(ws.workspace_root())
    _hydrate_after_the_restart(rid)
    recovered = ws.load_experiment(rid)
    assert recovered is not None
    assert_the_same_document(
        recovered.to_state(), expected, "the record restored from the repaired row"
    )


# =============================================================================
# 6. THE RUN-SCOPED ACCEPTANCE — added 2026-09-02, and the gap it closes is one
#    the file above could not see
# =============================================================================
#
# WHAT WAS MEASURED. Before this section, ``grep -an applied_run_id`` over this file
# returned exactly ONE line: a docstring listing the six ``accepted_*``/``applied_*``
# fields. No assertion touched it — and no assertion COULD, because
# :func:`build_the_scenario` accepts exactly one proposal and that one is
# RECORD-scoped, so ``applied_run_id`` is ``None`` in every document this file has
# ever compared. A serialisation change that dropped it, or that wrote it back as
# ``null``, would have passed all fourteen scenarios.
#
# ``None == None`` is the durability equivalent of ``[] == []``, which is the
# vacuousness this file's own §2 exists to refuse. So the field is given a value
# that is not ``None``, on a record with TWO runs so that the value is a CHOICE
# rather than the only id available, and the whole-document comparison then has
# something to lose.
#
# TWO RUNS, NOT ONE, AND THE SECOND ONE IS THE POINT. With one run, a reader that
# invented ``applied_run_id`` from ``exp.runs[0].id`` would be indistinguishable
# from one that carried it. The accepted proposals below name run TWO and run ONE
# respectively, so a document that lost the field and reconstructed it has to be
# wrong about at least one of them.
#
# The full lifecycle over two runs — isolation, attribution, the change feed, the
# refusals — is ``apps/api/tests/test_run_scoped_proposal_lifecycle.py``; this
# section proves only the DURABILITY of what that file establishes.

def _schema_enum(path: str) -> tuple:
    """The vendored official schema's ``enum`` at a dotted path, or ``()``.

    A TEST-LOCAL reader of the document ``CLAUDE.md`` §1 makes the authority — not a
    second definition of any application behaviour. It exists so
    :data:`SECOND_RUN_FIELD_VALUE` below comes from the schema rather than from the
    author, which is the rule :data:`RECORD_VALUE` follows one section up.
    """
    node: object = json.loads(
        routes.schema_path(routes.REPO_ROOT).read_text(encoding="utf-8")
    )
    for segment in path.split("."):
        if not isinstance(node, dict):
            return ()
        node = (node.get("properties") or {}).get(segment)
        if node is None:
            return ()
    values = node.get("enum") if isinstance(node, dict) else None
    return tuple(values) if isinstance(values, list) else ()


def _second_run_field() -> tuple[str, object]:
    """A SECOND run-level draft field and one legal value for it, both DERIVED.

    Two gates, both read at import from sources the application owns:
    :data:`routes.RUN_WRITABLE_FIELD_PATHS` — exactly what ``PATCH .../runs/{id}``
    accepts, and the same set ``_proposal_writer_for`` dispatches ``run_field`` on —
    and the vendored schema closing the path with a string ``enum``, which is what
    makes a legal value available without this file inventing one.

    ``sorted`` and ``[0]`` rather than "whatever the set yields first":
    ``frozenset`` iteration order is not stable across processes, and a scenario
    that picked a different path on different runs would make a failure
    irreproducible.

    THIS WAS TWO LITERALS UNDER A COMMENT CLAIMING THEY WERE DERIVED, which an
    independent review measured. The comment is now true rather than removed,
    because the claim was the right one to make: a hand-copied path or enum member
    is a second copy of a document the server already publishes, free to rot into a
    scenario that passes for the wrong reason.
    """
    for path in sorted(routes.RUN_WRITABLE_FIELD_PATHS):
        if path == RUN_FIELD_PATH:
            continue
        values = _schema_enum(path)
        if values and all(isinstance(value, str) for value in values):
            return path, values[0]
    raise AssertionError(
        "no run-writable field other than RUN_FIELD_PATH is closed by a string enum "
        "in the vendored schema, so this scenario has no second target"
    )


#: A second run-level draft field, so the two accepted proposals below differ in
#: their target as well as in their run — and one value the official schema declares
#: legal for it. DERIVED; see :func:`_second_run_field`.
SECOND_RUN_FIELD_PATH, SECOND_RUN_FIELD_VALUE = _second_run_field()


def build_the_two_run_scenario(client: TestClient, after_each=None) -> tuple[str, str, str]:
    """One record, TWO runs, and an accepted run-scoped proposal on EACH.

    Returns ``(experiment_id, first_run_id, second_run_id)``. ``after_each(rid,
    label)`` is called after every act that writes, exactly as
    :func:`build_the_scenario`'s is.

    Deliberately NOT a variant of :func:`build_the_scenario`. That builder's shape is
    load-bearing for eleven existing assertions — ``total == 4``, three
    multi-transition histories, one unreadable entry, a four-key
    ``proposal_change_revs`` — and widening it to carry a second run would have meant
    editing every one of those numbers to prove something none of them is about.
    """

    created = client.post(
        "/api/experiments", json={"title": "Run-scoped proposal durability"}
    )
    assert created.status_code == 201, created.text
    rid = created.json()["id"]

    def checkpoint(label: str) -> None:
        if after_each is not None:
            after_each(rid, label)

    checkpoint("create the experiment")

    run_ids: list[str] = []
    for label in ("R1", "R2"):
        response = client.post(
            f"/api/experiments/{rid}/runs",
            json={"label": label},
            headers={"If-Match": _etag(client, rid)},
        )
        assert response.status_code == 201, response.text
        run_ids.append(response.json()["run"]["id"])
        checkpoint(f"add run {label}")
    first, second = run_ids
    assert first != second

    note = client.post(
        f"/api/experiments/{rid}/notes",
        json={"text": NOTE_TEXT, "source": "typed_note"},
        headers={"If-Match": _etag(client, rid)},
    )
    assert note.status_code == 201, note.text
    note_id = note.json()["note"]["id"]
    checkpoint("capture the note behind both proposals")

    # The SECOND run first, so a document that reconstructed `applied_run_id` from
    # "the first run" would be wrong about this one.
    on_second = _create_proposal(
        client,
        rid,
        path=RUN_FIELD_PATH,
        value=300.0,
        note_id=note_id,
        run_id=second,
    )
    checkpoint("propose a run-level field on the second run")
    on_first = _create_proposal(
        client,
        rid,
        path=SECOND_RUN_FIELD_PATH,
        value=SECOND_RUN_FIELD_VALUE,
        note_id=note_id,
        run_id=first,
    )
    checkpoint("propose a different run-level field on the first run")

    _review(client, rid, on_second, action="accept", accepted_from="candidate")
    checkpoint("accept the one that names the second run")
    _review(client, rid, on_first, action="accept", accepted_from="candidate")
    checkpoint("accept the one that names the first run")

    return rid, first, second


def assert_the_two_run_scenario_is_not_vacuous(
    document: dict, first: str, second: str
) -> None:
    """``applied_run_id`` is REALLY set, REALLY differs, and names REAL runs.

    Three separate claims, because two of them are the ones a broken round trip
    would satisfy: a document that lost the field satisfies none, one that wrote
    ``null`` satisfies none, and one that reconstructed the field from a single run
    satisfies the first two and fails the third.
    """
    stored = document.get(proposals.STATE_KEY)
    assert isinstance(stored, list) and len(stored) == 2, stored
    assert all(entry["state"] == proposals.STATE_ACCEPTED for entry in stored), stored

    # `.get`, and the presence check FIRST as an assertion — a bare subscript raises
    # `KeyError`, which the drop control below would not recognise as a refusal.
    assert all("applied_run_id" in entry for entry in stored), (
        "a stored acceptance carries no `applied_run_id` key at all: " + json.dumps(stored)
    )
    applied = {entry["target_field_path"]: entry.get("applied_run_id") for entry in stored}
    assert applied == {RUN_FIELD_PATH: second, SECOND_RUN_FIELD_PATH: first}, applied
    assert all(value is not None for value in applied.values()), applied
    assert len(set(applied.values())) == 2, (
        "both acceptances landed on the same run; `applied_run_id` cannot then "
        "distinguish a carried value from a reconstructed one"
    )
    for entry in stored:
        assert entry["run_id"] == entry["applied_run_id"], entry
        assert entry["applied_via"] == proposals.APPLIED_VIA_RUN_FIELD, entry
        assert isinstance(entry["applied_rev"], int), entry
        assert entry["history"][-1]["actor_subject"] == ACTOR, entry

    positions = document.get("proposal_change_revs")
    assert isinstance(positions, dict) and len(positions) == 2, positions


def assert_each_run_holds_only_its_own_accepted_value(
    client: TestClient, rid: str, first: str, second: str
) -> None:
    """The scientific consequence, read back over HTTP after the round trip.

    A durable document that is byte-perfect while the runs it describes hold the
    wrong values would be a passing durability suite over a broken record, so the
    served runs are checked too.
    """
    def fields(run_id: str) -> dict:
        response = client.get(f"/api/experiments/{rid}/runs/{run_id}")
        assert response.status_code == 200, response.text
        return response.json()["run"]["fields"]

    on_first, on_second = fields(first), fields(second)
    assert on_second[RUN_FIELD_PATH]["value"] == 300.0, on_second
    assert on_first[SECOND_RUN_FIELD_PATH]["value"] == SECOND_RUN_FIELD_VALUE, on_first
    assert RUN_FIELD_PATH not in on_first, (
        "the value accepted for the second run reached the first: " + json.dumps(on_first)
    )
    assert SECOND_RUN_FIELD_PATH not in on_second, (
        "the value accepted for the first run reached the second: "
        + json.dumps(on_second)
    )


def test_the_two_run_scenario_sets_applied_run_id_where_the_original_cannot(
    filesystem_workspace,
):
    """THE PREMISE, AND THE GAP, MEASURED IN THE SAME TEST.

    The second half is the part worth keeping: it re-runs the ORIGINAL builder and
    asserts that every ``applied_run_id`` it produces is ``None``. That is not a
    criticism of that builder — it accepts a record-scoped proposal, which correctly
    has no run — it is the reason this section had to exist, stated as an assertion
    so that a future change making the original cover the field would make this
    sentence fail rather than quietly become false.
    """
    client = _client()
    assert repo.repository().backend == repo.BACKEND_FILESYSTEM

    # THE CHECKPOINT PLUMBING, REHEARSED WHERE IT CAN BE RUN — the same reason
    # `test_the_checkpoint_plumbing_really_fires_after_every_act` exists for the
    # original builder. `test_REAL_ENGINE_a_run_scoped_acceptance_survives_the_round
    # _trip_with_its_run` asserts `len(observed) == 8`; if this builder ever stopped
    # calling the callback, that test would pass having asserted nothing and CI would
    # be the only place anybody found out.
    observed: list[str] = []

    def after_each(rid_: str, label: str) -> None:
        observed.append(label)
        assert_the_same_document(
            _document_in_the_workspace(rid_),
            ws.load_experiment(rid_).to_state(),
            f"the working copy after: {label}",
        )

    rid, first, second = build_the_two_run_scenario(client, after_each=after_each)
    assert len(observed) == 8, observed
    document = ws.load_experiment(rid).to_state()
    assert_the_two_run_scenario_is_not_vacuous(document, first, second)
    assert_the_same_document(
        _document_in_the_workspace(rid), document, "the working copy"
    )
    assert_each_run_holds_only_its_own_accepted_value(client, rid, first, second)

    original = ws.load_experiment(build_the_scenario(_client())).to_state()
    applied = [
        entry.get("applied_run_id")
        for entry in original[proposals.STATE_KEY]
        if isinstance(entry, dict) and entry.get("state") == proposals.STATE_ACCEPTED
    ]
    assert applied == [None], (
        "the original scenario now sets `applied_run_id`; this section's premise — "
        f"that it could not — is stale: {applied}"
    )


@pytest.mark.parametrize(
    "damage",
    ["drop_applied_run_id", "null_applied_run_id", "swap_applied_run_id"],
)
def test_the_comparison_FAILS_on_each_way_a_run_scoped_acceptance_can_be_LOST(
    filesystem_workspace, damage
):
    """THE CONTROLS. Three ways ``applied_run_id`` can go wrong, all caught.

    The third is the one a picked-key comparison would miss and a single-run fixture
    could not even express: the field is present, non-null, and names the WRONG run.
    """
    client = _client()
    rid, first, second = build_the_two_run_scenario(client)
    expected = ws.load_experiment(rid).to_state()
    assert_the_two_run_scenario_is_not_vacuous(expected, first, second)

    damaged = copy.deepcopy(expected)
    entries = damaged[proposals.STATE_KEY]
    if damage == "drop_applied_run_id":
        for entry in entries:
            entry.pop("applied_run_id")
    elif damage == "null_applied_run_id":
        for entry in entries:
            entry["applied_run_id"] = None
    else:
        for entry in entries:
            entry["applied_run_id"] = first if entry["applied_run_id"] == second else second

    assert damaged != expected, f"the {damage} control changed nothing"
    with pytest.raises(AssertionError):
        assert_the_same_document(damaged, expected, f"the {damage} document")
    # ...and the vacuousness check refuses it too, so a future comparison that got
    # laxer would still not make this section green by accident.
    with pytest.raises(AssertionError):
        assert_the_two_run_scenario_is_not_vacuous(damaged, first, second)


@real_engine
def test_REAL_ENGINE_a_run_scoped_acceptance_survives_the_round_trip_with_its_run(
    durable_workspace,
):
    """``applied_run_id`` reaches PostgreSQL and comes back naming the same run.

    Asserted after EVERY act, for the reason the per-act case above gives: "the
    final state reached the database" and "each act reached the database" are
    different claims, and only the second survives a pod roll mid-sequence.
    """
    _assert_the_backend_is_durable()
    client = _client()
    observed: list[str] = []

    def after_each(rid: str, label: str) -> None:
        observed.append(label)
        assert_the_same_document(
            _document_in_the_database(rid),
            _document_in_the_workspace(rid),
            f"the durable row after: {label}",
        )

    rid, first, second = build_the_two_run_scenario(client, after_each=after_each)
    assert len(observed) == 8, observed

    stored = _document_in_the_database(rid)
    assert_the_two_run_scenario_is_not_vacuous(stored, first, second)
    assert_the_same_document(
        stored, ws.load_experiment(rid).to_state(), "the durable row at the end"
    )
    assert_each_run_holds_only_its_own_accepted_value(client, rid, first, second)


@real_engine
def test_REAL_ENGINE_the_run_scoped_acceptances_survive_a_pod_restart(
    durable_workspace,
):
    """The working copy is destroyed, hydration restores it, and both runs are right.

    The restart is what a durable repository is FOR, and it is the only path on
    which the stored ``applied_run_id`` is actually read back by the application
    rather than merely written and re-read by this test.
    """
    _assert_the_backend_is_durable()
    client = _client()
    rid, first, second = build_the_two_run_scenario(client)
    expected = ws.load_experiment(rid).to_state()
    assert_the_two_run_scenario_is_not_vacuous(expected, first, second)

    shutil.rmtree(ws.workspace_root() / rid)
    _hydrate_after_the_restart(rid)

    restored = ws.load_experiment(rid)
    assert restored is not None
    assert_the_same_document(restored.to_state(), expected, "the record after a restart")
    assert_the_two_run_scenario_is_not_vacuous(restored.to_state(), first, second)
    assert_each_run_holds_only_its_own_accepted_value(client, rid, first, second)

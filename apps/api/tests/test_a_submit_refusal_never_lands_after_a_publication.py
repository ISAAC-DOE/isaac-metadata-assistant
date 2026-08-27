"""THREE SUBMIT REFUSALS THAT NOTHING IN THIS REPOSITORY PINNED, FOUND BY MUTATION.

WHY THIS FILE EXISTS, AND HOW ITS THREE GAPS WERE ESTABLISHED
=============================================================
``test_submit_declares_the_record_a_person_built.py`` and ``test_submission.py``
were mutation-tested in an isolated copy of this repository before this file was
written. Nineteen faults were injected into ``routes.py`` and
``submission_store.py`` and the two suites were re-run against each. Sixteen were
killed. Three survived, and one of the three had a REAL, OBSERVABLE consequence
that no test in the repository could see:

    Removing the route's ``by_key`` preflight branch — ``if by_key is not None:``
    in ``post_submit`` — changed nothing that any existing test asserts. Both
    before and after, a reused ``Idempotency-Key`` over moved content answers
    ``409 idempotency_key_conflict`` and no history row appears, because
    ``record_submission`` re-reads the key inside its own transaction and raises
    :class:`~isaac_api.submission_store.IdempotencyKeyConflict`, which the route
    catches and reports identically.

    What DID change is what is on disk. Measured on a record whose second run was
    still UNMATERIALISED at the moment of the request:

    ==========================  =============================  ==================
    ``by_key`` preflight        ``published_record_count``      artifacts on disk
    ==========================  =============================  ==================
    present (shipped)           0                              unchanged
    removed (the mutant)        1                              2 files appeared
    ==========================  =============================  ==================

    So the shipped preflight is the ONLY thing standing between a rejected
    idempotency key and an official ISAAC record being published for it. The
    brief for this pass put it exactly right: *a refusal that lands after
    something was written is the finding.* On this path the refusal lands first,
    and until now nothing proved it.

THE OTHER TWO SURVIVORS ARE DEFENCE IN DEPTH, NOT DEFECTS, and they are the
reason the second half of this file exists. Disabling ``record_submission``'s
own in-transaction re-reads was invisible, because the ROUTE's preflight
short-circuits first. That is correct layering — but it means those two branches
had **no test anywhere in this repository**: ``SubmissionAlreadyExists`` and
``IdempotencyKeyConflict`` are never raised in any test file, only ever observed
as an HTTP error string. They are re-read inside the writing transaction
deliberately (*"the preflight ran in an earlier transaction so its answer can be
stale by now"*), which is precisely the case an HTTP test cannot construct. They
are driven directly here.

WHAT THIS FILE DELIBERATELY DOES NOT CLAIM. It does not claim that a submit
refusal can never land after a publication — one can, by design, and
``test_submission.py`` pins that arm: a concurrent writer who takes the key
between the preflight and the insert produces a refusal that DISCLOSES what it
published (``test_a_lost_race_to_the_same_key_over_other_content_is_a_key_conflict``
asserts a non-empty ``records``). The claim here is narrower and is the one that
was unpinned: **the preflight arm refuses before publishing, and says so.**

THE RECORD IS BUILT THROUGH ``POST /api/experiments`` AND THE ANSWER ROUTES, with
every value written out below. No fixture sheet, no seed, no ``_full_draft()`` —
see :func:`test_nothing_in_this_file_borrows_a_fixture_value`.

Nothing here opens a network connection, reads real data, or touches a database.
No production code is modified by anything in this file.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import pathlib

import pytest
from fastapi.testclient import TestClient

import isaac_api.identity as identity
import isaac_api.revision_history as rhist
import isaac_api.submission_store as sstore
import isaac_api.submissions as submissions
import isaac_api.workspace as ws

from submission_fake import FakeSubmissionConnection, fake_reader, fake_store

ACTOR = "grace.hopper"

#: Written out as a person supplies them. Nothing is harvested from a fixture.
DESCRIPTOR = {
    "name": "white_line_intensity",
    "kind": "absolute",
    "source": "manual",
    "value": 1.42,
    "unit": "mu_normalized",
    "uncertainty": {"sigma": 0.02, "unit": "mu_normalized", "basis": "reported"},
}
SERIES = [
    {
        "series_id": "averaged_spectrum",
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [8975, 8985, 8995]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [0.03, 0.91, 1.42],
            }
        ],
    }
]
QC = {"status": "valid", "evidence": "Reference foil scanned before and after; no drift."}

#: The five history tables, named so an assertion message can say which one moved.
HISTORY_TABLES = ("revisions", "run_revisions", "changes", "submissions", "submission_runs")


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def db():
    return FakeSubmissionConnection()


@pytest.fixture()
def client(tmp_path, monkeypatch, db):
    """A deployment that can attribute a person, with nothing seeded in it."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    monkeypatch.setattr(rhist, "reader", lambda env=None: fake_reader(db))
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


# --- the walk, written out ----------------------------------------------------


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, eid: str, run_id: str) -> str:
    response = client.get(f"/api/experiments/{eid}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _answers() -> dict:
    return {
        "series": copy.deepcopy(SERIES),
        "descriptor": copy.deepcopy(DESCRIPTOR),
        "qc": copy.deepcopy(QC),
    }


def _answer_every_open_run_question(client, eid: str) -> None:
    for question in client.get(f"/api/experiments/{eid}/pending").json()["pending"]:
        run_id = question.get("run_id")
        assert run_id is not None, question
        answered = client.post(
            f"/api/experiments/{eid}/runs/{run_id}/answers",
            json={"answers": _answers(), "confirmed_by_user": True},
            headers={"If-Match": _run_etag(client, eid, run_id)},
        )
        assert answered.status_code == 200, answered.text
    assert client.get(f"/api/experiments/{eid}/pending").json()["pending"] == []


def _built(client, title: str, *, runs: tuple[str, ...]) -> str:
    """Create a record and answer every question, with values typed out above."""
    created = client.post("/api/experiments", json={"title": title})
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    filled = client.post(
        f"/api/experiments/{eid}/answers",
        json={"answers": _answers(), "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert filled.status_code == 200, filled.text
    for label in runs:
        added = client.post(
            f"/api/experiments/{eid}/runs",
            json={"label": label, "confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        )
        assert added.status_code == 201, added.text
    _answer_every_open_run_question(client, eid)
    return eid


def _artifacts(eid: str) -> dict[str, str]:
    """``filename -> sha256`` for every file in this record's records directory."""
    exp = ws.load_experiment(eid)
    if exp is None or not exp.records_dir.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(exp.records_dir.iterdir())
        if path.is_file()
    }


def _rows(db) -> dict[str, int]:
    return {name: len(getattr(db, name)) for name in HISTORY_TABLES}


def _unmaterialised_unit_ids(eid: str) -> list[str]:
    exp = ws.load_experiment(eid)
    return [unit.target_id for unit in exp.export_units() if not unit.materialised()]


# ==========================================================================
# 1. THE GAP MUTATION FOUND: THE PREFLIGHT REFUSES *BEFORE* IT PUBLISHES
# ==========================================================================


def test_a_reused_key_over_new_content_refuses_before_it_publishes_anything(client, db):
    """**THE PROPERTY THE ``by_key`` PREFLIGHT EXISTS FOR, AND THE ONE NOBODY PINNED.**

    A scientist submits a one-run record under ``Idempotency-Key: K``. They then add
    a second run and answer it — so the record now holds a unit that has NEVER been
    materialised — and their client retries under the SAME key, which is the exact
    mistake an idempotency key is meant to catch.

    Every assertion below is made from AUTHORITATIVE STATE re-read after the call:
    the records directory is re-hashed, and all five history tables are re-counted.
    None of it is inferred from the status code.

    THE PREMISE IS ASSERTED, NOT ASSUMED. If the second unit were already
    materialised there would be nothing left to publish and this test would pass
    against a route that published freely — which is exactly how the existing
    ``test_a_second_submission_before_materialisation_still_says_nothing_was_published``
    ends up unable to see this: its record was fully materialised by the preceding
    successful submit. So ``_unmaterialised_unit_ids`` is checked to be non-empty
    immediately before the request, and non-empty again immediately after.
    """
    eid = _built(client, "Cu K-edge XANES, two temperatures", runs=("300 K",))
    first = client.post(
        f"/api/experiments/{eid}/submit",
        headers={"If-Match": _etag(client, eid), "Idempotency-Key": "client-token-0001"},
    )
    assert first.status_code == 200, first.text

    added = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "400 K", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert added.status_code == 201, added.text
    _answer_every_open_run_question(client, eid)

    # THE PREMISE. Without this the test cannot distinguish "refused before
    # publishing" from "had nothing to publish".
    pending_publication = _unmaterialised_unit_ids(eid)
    assert len(pending_publication) == 1, pending_publication

    artifacts_before = _artifacts(eid)
    rows_before = _rows(db)
    exp = ws.load_experiment(eid)
    signature_now = submissions.content_signature(exp.id, exp.export_units())
    assert signature_now != first.json()["content_signature"], (
        "the second run must have moved the content signature, or this is not a "
        "key REUSE over new content and the branch under test is never reached"
    )

    refused = client.post(
        f"/api/experiments/{eid}/submit",
        headers={"If-Match": _etag(client, eid), "Idempotency-Key": "client-token-0001"},
    )

    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["error"] == "idempotency_key_conflict"
    # THE FINDING THIS TEST EXISTS FOR: nothing was published, and the body says so.
    assert body["published_record_count"] == 0, body
    assert body["records"] == [], body
    assert "Nothing was written" in body["message"], body["message"]
    assert _artifacts(eid) == artifacts_before, (
        "an idempotency-key conflict published an official ISAAC record. The "
        "refusal is correct and the publication is not: the preflight exists so "
        "that a rejected key never leaves an artifact behind."
    )
    assert _rows(db) == rows_before
    assert _unmaterialised_unit_ids(eid) == pending_publication, (
        "the unit that was awaiting publication must still be awaiting it"
    )


def test_an_already_submitted_refusal_cannot_reach_this_shape_at_all(client, db):
    """WHY THE TEST ABOVE HAS NO ``already_submitted`` TWIN — established, not assumed.

    ``already_submitted`` is decided by an EQUAL content signature. A unit that has
    never been materialised is a unit the signature was not computed over, so the
    signature necessarily differs and that branch is unreachable in this shape. It
    would be easy to write the twin, see it pass, and record coverage for a case
    that cannot occur; this asserts the unreachability instead.
    """
    eid = _built(client, "unreachable twin", runs=("300 K",))
    submitted = client.post(
        f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
    )
    assert submitted.status_code == 200, submitted.text
    signature = submitted.json()["content_signature"]

    assert _unmaterialised_unit_ids(eid) == [], "a successful submit materialises every unit"
    added = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "400 K", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert added.status_code == 201, added.text
    _answer_every_open_run_question(client, eid)

    exp = ws.load_experiment(eid)
    assert len(_unmaterialised_unit_ids(eid)) == 1
    assert submissions.content_signature(exp.id, exp.export_units()) != signature, (
        "adding an unmaterialised unit must move the signature; if it ever stops "
        "doing so, `already_submitted` becomes reachable with something still to "
        "publish and the test above needs a twin"
    )
    # And the keyless retry over that new content is accepted, not `already_submitted`.
    again = client.post(
        f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
    )
    assert again.status_code == 200, again.text
    assert again.json()["revision_no"] == 2


# ==========================================================================
# 2. THE TWO IN-TRANSACTION RE-READS, WHICH NO TEST ANYWHERE HAD DRIVEN
# ==========================================================================
#
# `record_submission` re-reads both refusals inside the writing transaction and
# says why: *"the preflight ran in an earlier transaction so its answer can be
# stale by now, and re-reading them inside the writing transaction is what makes
# 'already submitted' a decision about the same instant as the write."* An HTTP
# request cannot reach either branch, because the route's own preflight answers
# first — which is what made them invisible to every existing test, and is why the
# store is driven directly here.


def _store_ready(client, db, title: str) -> tuple[object, str]:
    """A record submitted once over HTTP, plus its live ``Experiment``.

    Submitting over HTTP first is deliberate: it materialises every unit exactly as
    the route does, so the direct calls below exercise the real refusal rather than
    the ``ValueError`` an unmaterialised unit would raise before a connection opens.
    """
    eid = _built(client, title, runs=("300 K",))
    submitted = client.post(
        f"/api/experiments/{eid}/submit",
        headers={"If-Match": _etag(client, eid), "Idempotency-Key": "first-key"},
    )
    assert submitted.status_code == 200, submitted.text
    return ws.load_experiment(eid), submitted.json()["content_signature"]


def test_the_store_re_reads_the_signature_inside_its_own_transaction(client, db):
    """``SubmissionAlreadyExists`` — raised, and leaving the database exactly as it was.

    The name appears in no other test file in this repository; it has only ever
    been observed as the string ``"already_submitted"`` in an HTTP body.
    """
    exp, signature = _store_ready(client, db, "store signature re-read")
    rows_before = _rows(db)
    commits_before = db.commits

    with pytest.raises(sstore.SubmissionAlreadyExists) as raised:
        fake_store(db).record_submission(
            exp=exp,
            units=exp.export_units(),
            content_signature=signature,
            conflict_summary={},
            subject=ACTOR,
            trust_basis=identity.FIXTURE_VERIFIER,
            idempotency_key=None,
        )

    assert raised.value.existing["content_signature"] == signature
    assert _rows(db) == rows_before, "a refused re-read wrote a row"
    assert db.commits == commits_before, "a refused re-read committed"
    assert db.rollbacks >= 1, "the transaction must have been rolled back"


def test_the_store_re_reads_the_idempotency_key_inside_its_own_transaction(client, db):
    """``IdempotencyKeyConflict`` — the same, for the other refusal.

    The signature passed here is deliberately one this record has never had, so the
    ``by_signature`` branch above cannot fire and the KEY branch is what raises.
    """
    exp, signature = _store_ready(client, db, "store key re-read")
    rows_before = _rows(db)
    commits_before = db.commits
    other_content = "f" * 64
    assert other_content != signature

    with pytest.raises(sstore.IdempotencyKeyConflict) as raised:
        fake_store(db).record_submission(
            exp=exp,
            units=exp.export_units(),
            content_signature=other_content,
            conflict_summary={},
            subject=ACTOR,
            trust_basis=identity.FIXTURE_VERIFIER,
            idempotency_key="first-key",
        )

    assert raised.value.existing["idempotency_key"] == "first-key"
    assert raised.value.existing["content_signature"] == signature, (
        "the conflict must report the submission that already holds the key"
    )
    assert _rows(db) == rows_before
    assert db.commits == commits_before
    assert db.rollbacks >= 1


@pytest.mark.parametrize(
    "key",
    [
        # The discriminating case, and the ONE that catches a swap. This key is
        # ALREADY on the recorded submission, so a store that asked the key
        # question first would answer `idempotency_key_conflict` — telling a
        # scientist they reused a token when what actually happened is that this
        # exact content is already on record.
        "first-key",
        # A key that collides with nothing. Both orders answer the same thing
        # here, which is precisely why this arm alone cannot pin the ordering;
        # it is kept as the control that shows the parametrisation is not
        # measuring the key at all.
        "a-completely-different-key",
        None,
    ],
)
def test_the_signature_refusal_is_reached_before_the_key_refusal(client, db, key):
    """THE ORDER OF THE TWO RE-READS, PINNED. Signature first, key second.

    MEASURED BY MUTATION: a version of this test that only ever passed a
    non-colliding key SURVIVED a fault that swapped the two re-reads, because with
    no key collision both orders answer identically. The ``"first-key"`` arm is
    what kills it.
    """
    exp, signature = _store_ready(client, db, f"refusal ordering {key}")
    rows_before = _rows(db)

    with pytest.raises(sstore.SubmissionAlreadyExists):
        fake_store(db).record_submission(
            exp=exp,
            units=exp.export_units(),
            content_signature=signature,
            conflict_summary={},
            subject=ACTOR,
            trust_basis=identity.FIXTURE_VERIFIER,
            idempotency_key=key,
        )
    assert _rows(db) == rows_before


# ==========================================================================
# 3. NEGATIVE CONTROL FOR THIS FILE'S OWN PREMISE
# ==========================================================================


def test_nothing_in_this_file_borrows_a_fixture_value():
    """The premise, guarded — the same shape and reason as the guards in
    ``test_scientist_can_finish_a_record.py`` and
    ``test_submit_declares_the_record_a_person_built.py``.

    Every record here starts where a scientist starts. An edit that reached for
    ``ws._full_draft()``, ``_split_full_draft()`` or a canonical seed id would
    restore the blind spot this file exists inside, and the file would keep
    passing while measuring something else.
    """
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    tree.body = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.FunctionDef)
            and node.name == "test_nothing_in_this_file_borrows_a_fixture_value"
        )
    ]
    borrowed = {
        "_full_draft",
        "_review_draft",
        "_split_full_draft",
        "load_demo_answers",
        "demo_answers",
        "tutorial_client",
        "tutorial_ws",
        "create_experiment",
    }
    seed_prefixes = ("01" + "SYNTH", "01" + "JQZ0")
    used: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in borrowed:
            used.append(node.id)
        if isinstance(node, ast.Attribute) and node.attr in borrowed:
            used.append(node.attr)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith(seed_prefixes):
                used.append(node.value)
    assert used == [], f"this file borrowed fixture machinery: {sorted(set(used))}"

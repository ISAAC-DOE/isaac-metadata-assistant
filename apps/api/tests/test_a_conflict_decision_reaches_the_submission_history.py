"""A conflict decision taken AFTER a submission must be recordable — in both shapes.

THE DEFECT THIS FILE EXISTS FOR, as it was measured over HTTP against the real routes.
One act — ``POST .../conflicts/resolve`` at one record-level address, ``200`` in both
cases — used to have two outcomes decided only by whether the record had runs:

    zero-run record : submit#2 -> 200, revision 2 recorded, conflict_summary
                      {resolutions_supplied: true, resolved_field_count: 1,
                       unresolved_field_count: 0}
    record with runs: submit#2 -> 409 already_submitted, one revision on record
                      forever, its conflict_summary still reading
                      {resolutions_supplied: false, unresolved_field_count: 1}

``submissions.content_signature`` digested each EXPORT UNIT's fully resolved draft. A
zero-run record's one unit draft IS ``exp.draft``, which is where
``conflict_resolution.write_resolution`` stores decisions, so a decision moved the
digest. A record with runs composes its units from run drafts, and
``workspace.Experiment.resolved_run_draft`` deliberately does not copy the
record-level decisions key into one — ``routes.post_submit`` reads them off
``exp.draft`` separately for exactly that reason. So the decision moved no unit draft,
the digest did not move, and ``isaac_submissions.conflict_summary`` — the ONE place a
submission discloses that a human settled a conflicting field — could never be written
again for that record. **A record with runs is the shape this product normally
produces.**

WHAT THE DEFECT WAS NOT, because the fix must not be described as repairing damage
that never happened: nothing was mutated. Revision 1's snapshot was intact, the
exported records on disk were untouched, and the decision itself was stored in the
workspace document and readable at ``GET .../conflicts``. It was a RECORDING gap in
the submission history, plus a ``409`` asserting the record was unchanged when the
persisted document had moved.

The first test is written as the INVARIANT — *the same act must be recordable whatever
shape the record has* — and is parameterised over both shapes, so the two cannot drift
apart again without one parameter failing.

THE OTHER THREE TESTS PIN THE BOUNDARY OF THE FIX, and they matter as much as it does.
The digest was widened to cover the record's conflict decisions BECAUSE a submission
row discloses them in ``conflict_summary``; it was NOT widened to cover the document.
So a captured note still does not make a resubmission a new submission, and the
refusal that says so must stop claiming the record is unchanged.
"""
from __future__ import annotations

import copy

import pytest

import isaac_api.conflict_resolution as cr
import isaac_api.identity as identity
import isaac_api.revision_history as rhist
import isaac_api.submission_store as sstore
import isaac_api.submissions as submissions
import isaac_api.workspace as ws
from fastapi.testclient import TestClient
from isaac_records.models import user_confirmation

from submission_fake import FakeSubmissionConnection, fake_reader, fake_store
from test_export_fan_out import _split_full_draft

ACTOR = "ada.lovelace"
ADDRESS = "sample.material.name"
ZERO_RUN_ID = "01JQZZ2SERVN00000000000001"
FAN_OUT_ID = "01JQZZ2SERVN00000000000002"


@pytest.fixture()
def armed(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return ws


@pytest.fixture()
def db():
    return FakeSubmissionConnection()


@pytest.fixture()
def wired(monkeypatch, db):
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    monkeypatch.setattr(rhist, "reader", lambda env=None: fake_reader(db))
    return db


@pytest.fixture()
def client(armed, wired):
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _etag(client, eid):
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _competing(*answers):
    """A draft envelope whose evidence asserts two different values — a conflict."""
    return {
        "value": answers[0],
        "status": "verified",
        "evidence": [
            user_confirmation("What material?", answer, "2026-01-01T00:00:00Z")
            for answer in answers
        ],
    }


def _make(eid, *, runs, conflicting=True):
    experiment_draft, run_draft = _split_full_draft()
    if not runs:
        experiment_draft = copy.deepcopy(ws._full_draft())
    if conflicting:
        experiment_draft["fields"][ADDRESS] = _competing("CuO", "Cu2O")
    exp = ws.create_experiment(
        "Conflict decision fixture", {"kind": "synthetic"}, experiment_draft, id=eid
    )
    for label in runs:
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    return ws.load_experiment(eid)


def _submit(client, eid):
    return client.post(
        f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
    )


def _resolve(client, eid):
    return client.post(
        f"/api/experiments/{eid}/conflicts/resolve",
        json={
            "confirmed_by_user": True,
            "address": ADDRESS,
            "outcome": "resolved",
            "chosen_value": "CuO",
            "chosen_from": "candidate",
        },
        headers={"If-Match": _etag(client, eid)},
    )


@pytest.mark.parametrize("eid,runs", [(ZERO_RUN_ID, ()), (FAN_OUT_ID, ("Run A",))])
def test_a_decision_taken_after_a_submission_reaches_the_history(client, db, eid, runs):
    _make(eid, runs=runs)

    first = _submit(client, eid)
    assert first.status_code == 200, first.text
    assert first.json()["conflict_summary"]["unresolved_field_count"] == 1, (
        "the fixture must actually carry an unresolved conflict, or this proves nothing"
    )
    revision_1_state = copy.deepcopy(db.revisions[0]["state"])

    resolved = _resolve(client, eid)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolution"]["outcome"] == "resolved"

    second = _submit(client, eid)

    # NOT MUTATED — asserted first, because it is the half that always held and this
    # file must not read as though the decision had corrupted anything.
    assert db.revisions[0]["state"] == revision_1_state, (
        "revision 1's immutable snapshot was rewritten"
    )

    assert second.status_code == 200, (
        "a human decision that settles a conflicting field is disclosed ONLY by a "
        "submission's conflict_summary, so a decision the resubmission cannot record "
        "is a decision no revision on file will ever show. Body: " + second.text[:300]
    )
    summary = second.json()["conflict_summary"]
    assert summary["resolutions_supplied"] is True
    assert summary["resolved_field_count"] == 1
    assert summary["unresolved_field_count"] == 0
    assert [row["revision_no"] for row in db.revisions] == [1, 2]

    # NOTHING WAS REPUBLISHED. The units were already materialised by submit#1, and
    # exported records are immutable — the second submission records a declaration
    # over the same artifacts and writes no file.
    assert second.json()["records"] == []
    assert second.json()["published_record_count"] == 0


def test_a_decision_moves_the_signature_for_a_record_with_runs(armed):
    """The domain-level half, at the function the route trusts.

    Deliberately NOT over HTTP: this is the exact comparison whose shape-dependence
    was the defect, and pinning it here means a future change to the signature's
    payload fails on the rule rather than on a route's behaviour three layers up.
    """
    exp = _make(FAN_OUT_ID, runs=("Run A", "Run B"))
    before = submissions.content_signature(exp.id, exp.export_units())

    # The competing set comes from the evidence, through the same function the route
    # uses — a hand-written pair would not be canonicalised the way the conflict rule
    # canonicalises, and `new_resolution` refuses a `candidate` choice that is not in
    # the set it was actually asserted over.
    competing = cr.competing_from_evidence(exp.draft["fields"][ADDRESS]["evidence"])
    assert len(competing) == 2, competing
    cr.write_resolution(
        exp.draft,
        cr.new_resolution(
            resolution_id="01JQZZ2RESOLUTION00000001",
            address=ADDRESS,
            outcome=cr.OUTCOME_RESOLVED,
            competing_values=competing,
            recorded_utc="2026-01-02T00:00:00Z",
            trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
            chosen_value="CuO",
            chosen_from=cr.CHOSEN_FROM_CANDIDATE,
        ),
    )
    exp.save_versioned()
    reloaded = ws.load_experiment(exp.id)

    # The decision is NOT in any unit's composed draft — `resolved_run_draft` withholds
    # it on purpose, and this asserts that rather than assuming it, because the whole
    # fix rests on the signature covering something the unit drafts do not.
    units = reloaded.export_units()
    assert all(cr.DRAFT_KEY not in unit.draft for unit in units)
    assert submissions.conflict_decisions(units), "the decision must be readable here"

    assert submissions.content_signature(reloaded.id, units) != before


@pytest.mark.parametrize("runs", [(), ("Run A",)])
def test_a_captured_note_is_still_not_a_new_submission(client, db, runs):
    """THE BOUNDARY, and it is deliberate rather than an oversight.

    A submission DISCLOSES the records it published and the conflict state it
    reported. A note is neither: it reaches no official record and no column of the
    submission mentions it, so a second row over the same science would make no claim
    the first did not. The revision SNAPSHOT beside the row does archive the note —
    that is what the snapshot is for — and it is deliberately not what decides
    identity, because a digest that moved with the whole document would license a new
    submission for every keystroke. The refusal is correct; what was wrong was the
    sentence it used to carry.
    """
    eid = "01JQZZ2SERVN00000000000003"
    _make(eid, runs=runs, conflicting=False)

    first = _submit(client, eid)
    assert first.status_code == 200, first.text

    note = client.post(
        f"/api/experiments/{eid}/notes",
        json={"text": "the beamline tripped during scan 3", "source": "typed_note"},
        headers={"If-Match": _etag(client, eid)},
    )
    assert note.status_code == 201, note.text

    second = _submit(client, eid)
    assert second.status_code == 409, second.text
    assert second.json()["error"] == "already_submitted"
    assert len(db.revisions) == 1


def test_the_refusal_does_not_claim_the_whole_document_is_unchanged(client, db):
    """The other half of the defect, and arguably the sharper one.

    ``already_submitted`` used to read *"already been submitted with exactly this
    content"* — an assertion about the whole record, on a comparison that excludes the
    title, the notes and the captured transcript. A scientist who had just changed one
    of those was told by the refusal that they had changed nothing.
    """
    eid = "01JQZZ2SERVN00000000000004"
    _make(eid, runs=("Run A",), conflicting=False)
    assert _submit(client, eid).status_code == 200

    note = client.post(
        f"/api/experiments/{eid}/notes",
        json={"text": "a note, so the document really has moved", "source": "typed_note"},
        headers={"If-Match": _etag(client, eid)},
    )
    assert note.status_code == 201, note.text

    refused = _submit(client, eid)
    assert refused.status_code == 409, refused.text
    message = refused.json()["message"]

    assert "exactly this content" not in message, message
    # It names the comparison's scope...
    assert "published" in message and "conflict decisions" in message, message
    # ...and what is outside it, which is what the scientist in this test just did.
    for excluded in ("title", "notes", "transcript"):
        assert excluded in message, (excluded, message)

def test_repeating_the_same_decision_does_not_manufacture_a_second_submission(client, db):
    """THE IDEMPOTENCY HALF OF THE WIDENING, and the question a reviewer should ask.

    If a decision moves the digest, does clicking the same decision twice record two
    submissions? No — and the reason is in ``conflict_resolution`` rather than here:
    ``revise_resolution`` returns the EXISTING object for a re-decision that changes
    nothing, ``write_resolution`` upserts in place preserving every row's position, and
    ``save_versioned`` writes nothing when the authoritative state is byte-identical.
    So the document does not move, the digest does not move, and the resubmission is
    refused exactly as a duplicate should be.

    This is the property that makes the widened digest still usable as an idempotency
    key. Without it, widening the coverage would have traded a recording gap for a
    stream of identical submissions.
    """
    eid = "01JQZZ2SERVN00000000000005"
    _make(eid, runs=("Run A",))

    assert _submit(client, eid).status_code == 200
    assert _resolve(client, eid).status_code == 200
    second = _submit(client, eid)
    assert second.status_code == 200, second.text
    assert len(db.revisions) == 2

    etag_before = _etag(client, eid)
    again = _resolve(client, eid)
    assert again.status_code == 200, again.text
    assert _etag(client, eid) == etag_before, (
        "an identical re-decision rewrote the document, which would advance the "
        "revision and license a submission for an act that changed nothing"
    )

    third = _submit(client, eid)
    assert third.status_code == 409, third.text
    assert third.json()["error"] == "already_submitted"
    assert len(db.revisions) == 2, [row["revision_no"] for row in db.revisions]

"""What ``content_signature`` covers of a conflict decision, and what follows from it.

THIS FILE PINS CURRENT BEHAVIOUR. It passed the moment it was written and it passes
now: nothing in the application changed for it. Said plainly because a test that reads
like a regression guard when it is really a *decision record* invites a future session
to "restore" what it thinks used to be true. The defect this closes was in PROSE —
``submissions.content_signature`` stated a rule narrower than the digest it describes —
and the fix is a corrected docstring plus these assertions, so that the two
consequences of the real rule are CHOSEN rather than merely reachable.

THE RULE, as the implementation actually has it: the digest covers
``submissions.conflict_decisions``, which returns the record's stored decisions
**verbatim** — ``rationale``, ``recorded_utc`` and the whole ``history`` tuple
included. That is strictly broader than ``conflict_summary``, which discloses
addresses, counts and four fixed state words and nothing else. Two consequences,
both measured over HTTP below:

  1. a **rationale-only** revision moves the digest, so it admits a further
     submission whose ``conflict_summary`` is byte-identical to the previous one's;
  2. **revise-then-revert** does not return the digest to its earlier value — it
     produces a THIRD distinct one — because ``conflict_resolution.revise_resolution``
     appends an ``ACTION_REVISE`` transition, so ``to_state()`` can never re-enter a
     value it has already had.

BOTH FAIL OPEN: an extra submission row, no data lost, no artifact rewritten. The
narrower alternative — digesting only what ``conflict_summary`` discloses — fails
CLOSED, which is why it was rejected; the argument is in
``submissions.content_signature`` and is not repeated here.

THE HARNESS IS DELIBERATELY BORROWED, not rebuilt.
``test_a_conflict_decision_reaches_the_submission_history`` established the fake
connection, the fixture record shapes and the ETag plumbing for exactly this
machinery in exactly this PR; a second harness over the same routes could drift from
it and would then be testing itself.
"""

from __future__ import annotations

import isaac_api.conflict_resolution as cr
import isaac_api.workspace as ws

# Only NON-test names: importing a `test_*` function would collect it twice.
from test_a_conflict_decision_reaches_the_submission_history import (  # noqa: F401
    ADDRESS,
    _etag,
    _make,
    _submit,
    armed,  # fixture
    client,  # fixture
    db,  # fixture
    wired,  # fixture
)

FAN_OUT_ID = "01JQZZ2VERBATIM0000000001"
REVERT_ID = "01JQZZ2VERBATIM0000000002"

FIRST_RATIONALE = "the 300 eV scan is the one we trust"
CORRECTED_RATIONALE = "corrected: it was the 400 eV scan we trust"


def _resolve(client, eid, *, rationale):
    """The same decision every time, differing ONLY in its rationale.

    ``outcome``, ``chosen_value`` and ``chosen_from`` are held constant on purpose:
    ``revise_resolution``'s idempotency check compares all four, so varying only the
    rationale isolates the component under test. Holding all four constant is what
    ``test_repeating_the_same_decision_does_not_manufacture_a_second_submission``
    already pins as a no-op, and this file is the other side of that boundary.
    """
    return client.post(
        f"/api/experiments/{eid}/conflicts/resolve",
        json={
            "confirmed_by_user": True,
            "address": ADDRESS,
            "outcome": "resolved",
            "chosen_value": "CuO",
            "chosen_from": "candidate",
            "rationale": rationale,
        },
        headers={"If-Match": _etag(client, eid)},
    )


def _stored_decision(eid):
    """The one stored decision, as ``conflict_decisions`` hands it to the digest."""
    exp = ws.load_experiment(eid)
    stored = exp.draft[cr.DRAFT_KEY]
    assert len(stored) == 1, stored
    return stored[0]


def test_a_rationale_only_revision_moves_the_digest_and_admits_a_submission(client, db):
    """CONSEQUENCE 1, and the one a reader is most likely to call a bug.

    A corrected rationale changes no exported byte and changes nothing
    ``conflict_summary`` reports — the two disclosures below are asserted EQUAL — and
    it still licenses another submission, because the digest covers the decision
    verbatim. That is the safe direction: the alternative is a scientist who fixes the
    reason they gave being told the record is unchanged, with no durable record that
    they corrected anything.
    """
    _make(FAN_OUT_ID, runs=("Run A",))

    assert _submit(client, FAN_OUT_ID).status_code == 200
    assert _resolve(client, FAN_OUT_ID, rationale=FIRST_RATIONALE).status_code == 200
    second = _submit(client, FAN_OUT_ID)
    assert second.status_code == 200, second.text

    # The rationale is really the only thing that moves.
    before = _stored_decision(FAN_OUT_ID)
    revised = _resolve(client, FAN_OUT_ID, rationale=CORRECTED_RATIONALE)
    assert revised.status_code == 200, revised.text
    after = _stored_decision(FAN_OUT_ID)
    assert after["rationale"] == CORRECTED_RATIONALE
    assert before["rationale"] == FIRST_RATIONALE
    assert {
        key: value
        for key, value in after.items()
        if key not in ("rationale", "history")
    } == {
        key: value
        for key, value in before.items()
        if key not in ("rationale", "history")
    }, "something other than the rationale moved, so this proves less than it claims"

    third = _submit(client, FAN_OUT_ID)
    assert third.status_code == 200, (
        "a corrected rationale is a real change of mind about a conflict, and the "
        "digest covers the stored decision verbatim, so the resubmission is accepted "
        "rather than refused as a duplicate. Body: " + third.text[:300]
    )
    assert [row["revision_no"] for row in db.revisions] == [1, 2, 3]

    # WHAT THE THIRD SUBMISSION DISCLOSES IS IDENTICAL TO THE SECOND'S — which is
    # exactly why the "it covers what a submission discloses" wording was false. The
    # digest moved on something no disclosure column mentions.
    assert second.json()["conflict_summary"] == third.json()["conflict_summary"]
    signatures = [row["content_signature"] for row in db.submissions]
    assert len(signatures) == len(set(signatures)) == 3, signatures


def test_revise_then_revert_does_not_return_the_digest_to_its_earlier_value(client, db):
    """CONSEQUENCE 2: reverting a rationale yields a THIRD digest, not the first again.

    THE MECHANISM, named so this reads as chosen rather than accidental:
    ``revise_resolution`` APPENDS an ``ACTION_REVISE`` transition on every act that
    changes anything, and ``ConflictResolution.to_state`` serialises the whole
    ``history`` tuple. So the state a revert produces differs from the state before the
    first revision by one more history entry, and the digest differs with it. A
    monotonically growing audit trail cannot be un-grown, and this is the arithmetic
    consequence of that.

    Fails OPEN: one extra submission row for the round trip. Making it fail closed
    would mean either digesting a decision without its history — losing the record
    that anything was reconsidered — or comparing decisions semantically inside a
    digest, which is a second definition of "the same decision".
    """
    _make(REVERT_ID, runs=("Run A",))

    assert _submit(client, REVERT_ID).status_code == 200
    assert _resolve(client, REVERT_ID, rationale=FIRST_RATIONALE).status_code == 200
    submission_a = _submit(client, REVERT_ID)
    assert submission_a.status_code == 200, submission_a.text

    assert _resolve(client, REVERT_ID, rationale=CORRECTED_RATIONALE).status_code == 200
    submission_b = _submit(client, REVERT_ID)
    assert submission_b.status_code == 200, submission_b.text

    # ...and back to exactly the rationale of submission A.
    assert _resolve(client, REVERT_ID, rationale=FIRST_RATIONALE).status_code == 200
    reverted = _stored_decision(REVERT_ID)
    assert reverted["rationale"] == FIRST_RATIONALE

    submission_c = _submit(client, REVERT_ID)
    assert submission_c.status_code == 200, (
        "the revert changed the stored document, so it is not a duplicate. Body: "
        + submission_c.text[:300]
    )
    assert [row["revision_no"] for row in db.revisions] == [1, 2, 3, 4]

    # THE ASSERTION THIS FILE EXISTS FOR: C is a THIRD value, not A again.
    a, b, c = (row["content_signature"] for row in db.submissions[1:])
    assert a != c, (
        "the digest returned to an earlier value after a revert, which would mean the "
        "appended ACTION_REVISE history stopped reaching the digest"
    )
    assert len({a, b, c}) == 3, (a, b, c)

    # The named reason, asserted rather than described: record, revise, revise.
    actions = [entry["action"] for entry in reverted["history"]]
    assert actions == [cr.ACTION_RECORD, cr.ACTION_REVISE, cr.ACTION_REVISE], actions

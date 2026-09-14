"""The claim `RETENTION_STATES_NOT_IMPLEMENTED` rests on, pinned.

*** THIS TEXT IS SERVED TO CLIENTS AND WAS PINNED BY NOTHING. *** That is the
condition in which `AMBIGUITY_POLICY` drifted earlier the same day: the code
changed, the served sentence did not, and only a deliberate re-read caught it.

The two retention states are refused for ONE reason — that nothing in this build
removes a note from a record that survives. If a future slice adds a note
deletion, the refusal becomes false and the states become offerable. Either
outcome is fine; discovering it by reading is not.

WHAT THIS DOES NOT ASSERT, and the wording of the claim was corrected to match:
discarding an experiment DOES destroy its notes, because notes live inside the
record document. That is the record going, not the transcript being retired from
a record that remains — which is what the two refused states would need.
"""

from __future__ import annotations

import pytest

from isaac_api import transcript_capture as tc
from isaac_api.app import create_app


@pytest.fixture(scope="module")
def schema() -> dict:
    return create_app().openapi()


def test_no_published_route_deletes_a_note(schema: dict) -> None:
    offenders = [
        f"DELETE {path}"
        for path, ops in schema["paths"].items()
        if "delete" in ops and "note" in path.lower()
    ]
    assert offenders == [], (
        "a DELETE addressed to a note now exists, so the reason "
        "`RETENTION_STATES_NOT_IMPLEMENTED` gives clients is false: "
        f"{offenders}. Either retire that refusal and offer the retention state, "
        "or narrow the claim — do not leave the served text asserting it."
    )


def test_the_notes_routes_are_the_ones_this_claim_assumes(schema: dict) -> None:
    """A VACUITY GUARD for the test above.

    `no DELETE among the note paths` also passes if there are no note paths at
    all — e.g. if a rename made the filter match nothing. This pins the shape the
    claim actually rests on.
    """
    notes = {
        path: sorted(ops)
        for path, ops in schema["paths"].items()
        if "note" in path.lower()
    }
    assert notes == {
        "/api/experiments/{experiment_id}/notes": ["get", "post"],
        "/api/experiments/{experiment_id}/notes/{note_id}": ["get"],
        "/api/experiments/{experiment_id}/notes/{note_id}/review": ["post"],
    }, (
        "the note routes changed shape. Re-read "
        "`RETENTION_STATES_NOT_IMPLEMENTED` against them before updating this: "
        f"{notes}"
    )


def test_the_served_reason_still_says_what_this_file_verifies() -> None:
    """The claim and its proof must not drift apart.

    Asserted over the SUBSTANCE ('removes a note from a record that survives'),
    not over the whole paragraph, so ordinary copy editing does not fail this —
    only a change to the thing being claimed.
    """
    reasons = {row["state"]: row["reason"] for row in tc.RETENTION_STATES_NOT_IMPLEMENTED}
    assert set(reasons) == {"retain_during_draft", "remove_after_extraction"}
    joined = " ".join(reasons.values())
    assert "removes a note from a record that survives" in joined, (
        "the served reason no longer states the property this file verifies. If the "
        "reason changed, change what is verified here too: "
        f"{joined}"
    )
    # And it must NOT have gone back to the unqualified absolute, which discard
    # falsifies: discarding an experiment destroys its notes along with it.
    assert "no operation that removes a note" not in joined, (
        "the unqualified claim is back. Discarding an experiment DOES remove its "
        "notes, because they live in the record document."
    )

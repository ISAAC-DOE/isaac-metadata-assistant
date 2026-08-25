"""``SIGNATURE_SCOPE`` is a SERVED disclosure, and nothing pinned its value.

THE GAP THIS FILE CLOSES, measured rather than argued. ``submissions.SIGNATURE_SCOPE``
is served as ``signature_scope`` by ``GET /api/experiments/{id}/revisions``
(``routes.py``), and it is itself a component of the digest it labels. Reverting that
one line to its previous value ``"export_unit_ids_and_drafts"`` — while
``content_signature`` went on covering the record's conflict decisions — left the FULL
suite green: ``5209 passed, 32 skipped``, identical to clean. Its only other
occurrences in the repository were two FRONTEND FIXTURES, which are inputs rather than
assertions, and no screen renders the value. So a served string could drift out of
agreement with the digest it describes, and the response would describe a scope one
term narrower than the thing it labels — which is exactly the defect the constant's own
comment says the value was moved to avoid.

WHAT THE GUARD IS, AND WHAT IT IS NOT. It is not a spelling test for one string: the
expected terms are checked against the payload ``content_signature`` ACTUALLY digests,
observed at runtime, so **adding a future component to that payload without renaming
the scope goes RED**. It is not a claim that the label is well-written prose, and it
deliberately does not police word order or the connective words.

HOW THE PAYLOAD IS OBSERVED. ``content_signature`` hands its payload to
:func:`isaac_api.submissions.canonical_json` exactly once, so intercepting that call
captures the real object — no copy of the dict literal is kept here, which is the point.
An AST or a hand-written duplicate of the payload would need updating in the same act
that added a component, and would therefore never fail.
"""

from __future__ import annotations

import pytest

import isaac_api.submissions as submissions

# Only NON-test names: importing a `test_*` function would collect it twice.
from test_a_conflict_decision_reaches_the_submission_history import (  # noqa: F401
    _etag,
    _make,
    armed,  # fixture
    client,  # fixture
    db,  # fixture
    wired,  # fixture
)

EID = "01JQZZ2SCOPELABEL00000001"

#: The two payload keys that are NOT components of the covered content, and so are
#: not things the label has to name.
#:
#: ``experiment_id`` is the SUBJECT of the digest — every value covered belongs to that
#: one record — not a kind of content covered. ``scope`` is this very label: requiring
#: the label to name itself is circular, and it is in the payload for a different
#: reason (so that widening the coverage necessarily changes every digest value).
NOT_COMPONENTS = ("experiment_id", "scope")

#: ``payload key -> the terms any of which count as naming it``. Explicit and readable
#: on purpose: a reader must be able to see WHY each key is considered named.
#:
#: * ``units`` — the label's ``export_unit_ids`` contains ``unit``; the plural and the
#:   singular are both accepted because "unit ids" and "units" name the same thing.
#: * ``conflict_decisions`` — named by exactly that phrase, or by its two words.
EXPECTED_TERMS: dict[str, tuple[str, ...]] = {
    "units": ("units", "unit"),
    "conflict_decisions": ("conflict_decisions", "conflict", "decisions"),
}


def scope_names(key: str, scope: str) -> bool:
    """Does ``scope`` name the payload component ``key``? The one predicate here.

    RAISES for a key it has no mapping for, and that is the guard's teeth rather than
    an oversight: a component added to the digest that nobody has decided how to name
    must fail, not silently pass.
    """
    if key not in EXPECTED_TERMS:
        raise AssertionError(
            f"`content_signature` digests a component {key!r} that "
            f"EXPECTED_TERMS says nothing about. A new component means the served "
            f"scope label may now be narrower than the digest it describes: decide "
            f"what SIGNATURE_SCOPE should call it, rename the constant, and add the "
            f"term here."
        )
    return any(term in scope for term in EXPECTED_TERMS[key])


@pytest.fixture()
def payload(armed, monkeypatch):
    """The exact object ``content_signature`` digests, intercepted at the one call."""
    captured: list = []
    original = submissions.canonical_json

    def spy(value):
        captured.append(value)
        return original(value)

    monkeypatch.setattr(submissions, "canonical_json", spy)
    exp = _make(EID, runs=("Run A",))
    digest = submissions.content_signature(exp.id, exp.export_units())
    assert len(digest) == 64, digest
    assert len(captured) == 1, (
        "the interception assumes canonical_json is called once per signature; it "
        f"was called {len(captured)} times, so this fixture is capturing the wrong "
        "object"
    )
    assert isinstance(captured[0], dict), captured[0]
    return captured[0]


def test_the_served_scope_label_names_every_component_of_the_digest(payload):
    """The guard: every covered component appears in the string the API serves."""
    components = [key for key in payload if key not in NOT_COMPONENTS]
    assert components, payload  # the interception found a payload with content

    unnamed = [key for key in components if not scope_names(key, submissions.SIGNATURE_SCOPE)]
    assert not unnamed, (
        f"SIGNATURE_SCOPE is {submissions.SIGNATURE_SCOPE!r}, which does not name "
        f"{unnamed!r}. It is SERVED as `signature_scope`, so a reader would be told "
        f"the digest covers less than it does."
    )

    # The two non-components are asserted PRESENT, so the exemption above stays honest:
    # if either ever left the payload, this file would be exempting a key that no
    # longer exists and the exemption would need re-deciding rather than inheriting.
    for key in NOT_COMPONENTS:
        assert key in payload, (key, sorted(payload))


def test_the_guard_rejects_the_scope_label_this_constant_used_to_carry(payload):
    """NEGATIVE CONTROL — proof the predicate above can fail at all.

    ``"export_unit_ids_and_drafts"`` is the literal value the constant held before the
    digest was widened, and it is the exact string whose restoration left the whole
    suite green. It must be REJECTED by the same predicate the assertion above passes
    with, or that assertion is proving nothing.
    """
    stale = "export_unit_ids_and_drafts"
    assert stale != submissions.SIGNATURE_SCOPE, (
        "the constant has been reverted to its pre-widening value in the source"
    )

    assert scope_names("units", stale), "the stale label did name the unit component"
    assert not scope_names("conflict_decisions", stale), (
        "the negative control does not fire, so the guard proves nothing"
    )

    components = [key for key in payload if key not in NOT_COMPONENTS]
    assert [key for key in components if not scope_names(key, stale)] == [
        "conflict_decisions"
    ]


def test_an_unmapped_component_fails_rather_than_passing_quietly():
    """The other half of the teeth: an unnamed FUTURE component must go RED.

    Simulated with a key no mapping covers, because the real event this guards
    against — somebody adding a fourth component to ``content_signature``'s payload —
    cannot be staged without editing the module under test.
    """
    with pytest.raises(AssertionError, match="EXPECTED_TERMS says nothing about"):
        scope_names("qc_verdicts", submissions.SIGNATURE_SCOPE)


def test_the_served_field_is_the_constant_itself(client, db):
    """The label reaches the wire, and it reaches it unchanged.

    Pinned because the constant and the response field are two lines in two modules,
    and a route that assembled the string itself would leave the constant looking
    authoritative while disclosing something else.
    """
    _make("01JQZZ2SCOPELABEL00000002", runs=("Run A",))
    response = client.get("/api/experiments/01JQZZ2SCOPELABEL00000002/revisions")
    assert response.status_code == 200, response.text
    assert response.json()["signature_scope"] == submissions.SIGNATURE_SCOPE

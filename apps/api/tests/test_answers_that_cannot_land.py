"""An answer the record cannot store is refused BY NAME, not absorbed into a false 200.

THE DEFECT THIS FILE PINS
=========================
Found by an independent end-to-end verification of the MCP surface, and measured at both
levels and on both surfaces (MCP and plain HTTP)::

    POST .../answers {"qc": "valid"}        <- the bare string the question's text suggests
      -> 200, error None, changed False, changed_fields []
         invalidation.reason: "No change — the submitted value was identical; nothing
                               was invalidated."
         pending before ['descriptor','qc','series'] / after ['descriptor','qc','series']

The same outcome for ``{"qc": {"verdict": …}}``, an off-enum ``{"qc": {"status": "ok"}}``,
``series`` as ``[[energy, mu], …]``, ``series`` as ``[]``, ``descriptor`` as a bare
string, and — separately — for an UNRECOGNISED key such as the plausible typo
``sample.material.nmae``.

WHY IT WAS A CLOSED LOOP RATHER THAN MERELY A BAD MESSAGE. Followed mechanically by a
compliant client:

1. ``changed: false`` + *"the submitted value was identical"* — the only supported
   reading is "already stored".
2. ``isaac_answer_questions``' description said a DIFFERING value on an already-answered
   question is refused ``422 already_answered``. No refusal came, reinforcing (1).
3. That description's remedy for an already-confirmed value is ``correcting: true``.
4. ``correcting: true`` -> ``422 not_yet_answered``, whose ``answer_at`` is the answers
   operation from step 1.

No message anywhere in the cycle said the value's SHAPE was rejected.

WHY THE EXISTING SUITE MISSED IT, which is the part worth keeping. Two tests asserted
the ``200`` and the still-open question and never read ``invalidation.reason``, so they
passed while the response contradicted itself — one of them
(``test_qc_answerable::test_an_off_enum_verdict_is_never_stored_and_the_question_stays_open``)
even had the docstring *"the response itself tells the caller nothing happened"*, which
is the property the response did not have. Those tests are INVERTED in place rather than
deleted, per this repository's established remedy; this file is the positive coverage
they never had.

WHAT IS DELIBERATELY NOT CHANGED, pinned here so a later slice does not "tidy" it:

* a BLANK value is still dropped at any key — a blank answer is not an answer;
* an IDENTICAL resubmission is still a ``200`` with an unmoved revision, and still says
  so, because a client must be able to retry a call it is unsure landed;
* a MALFORMED asset sha256 is still a ``200`` leaving the blocker open (a shipped UI
  affordance and a browser spec depend on it) — but its reason no longer claims the
  value was identical;
* ``/edit`` still tolerates a ride-along unrecognised key.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import tutorial_client
from isaac_api.dependencies import NO_OP_IDENTICAL_REASON

FALSE_CAUSE = "the submitted value was identical"
MADE_UP_KEY = "sample.material.nmae"  # a plausible typo for sample.material.name

#: Every recognised value the truth core's own shape predicates decline, one per row.
#: They are the six shapes the verification measured, not a generated sweep, so each
#: row is a shape a real client actually sent.
UNSTORABLE = [
    pytest.param("qc", "valid", id="qc=bare-verdict-string"),
    pytest.param("qc", {"verdict": "valid"}, id="qc=wrong-key"),
    pytest.param("qc", {"status": "ok"}, id="qc=off-enum-status"),
    pytest.param("qc", {"status": "valid", "evidence": {"note": "x"}}, id="qc=dict-note"),
    pytest.param("series", [[7112.0, 0.1], [7113.0, 0.2]], id="series=list-of-pairs"),
    pytest.param("series", [], id="series=empty"),
    pytest.param("series", "not-a-list", id="series=string"),
    pytest.param("descriptor", "e0 = 7112 eV", id="descriptor=string"),
    pytest.param("descriptor", {}, id="descriptor=empty"),
]


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def client(app) -> TestClient:
    return TestClient(app)


def _created(client) -> str:
    """A record built through the product's OWN Create Experiment path.

    Deliberately NOT a seed. Every completion and export test in the suite starts from
    a draft ``build_draft`` filled from a fixture sheet, which is precisely why this
    whole class of defect survived 4,700 backend tests.
    """
    created = client.post("/api/experiments", json={"title": "A record a scientist made"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _answer(client, eid: str, answers: dict):
    return client.post(
        f"/api/experiments/{eid}/answers",
        json={"confirmed_by_user": True, "answers": answers},
        headers={"If-Match": _etag(client, eid)},
    )


def _pending_ids(client, eid: str) -> list[str]:
    return [q["id"] for q in client.get(f"/api/experiments/{eid}/pending").json()["pending"]]


def _rev(client, eid: str) -> int:
    return client.get(f"/api/experiments/{eid}").json()["rev"]


def _run_fixture(client) -> tuple[str, str]:
    """A record with ONE run whose science questions are still open, over HTTP only.

    The first run of a record ADOPTS the record's run-level content, so a run added to a
    record nobody has answered yet inherits nothing and raises its own `series`, `qc`
    and `descriptor` questions — which is exactly the state a client is in when it
    answers a run for the first time.
    """
    eid = _created(client)
    created = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "300 K"},
        headers={"If-Match": _etag(client, eid)},
    )
    assert created.status_code == 201, created.text
    return eid, created.json()["run"]["id"]


def _run_etag(client, eid: str, rid: str) -> str:
    response = client.get(f"/api/experiments/{eid}/runs/{rid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


# ---------------------------------------------------------------------------
# A recognised key whose value the core declines
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key,value", UNSTORABLE)
def test_a_value_the_record_cannot_store_is_refused_by_name(client, key, value):
    """422, naming the key, saying the value is not a shape the record can store."""
    eid = _created(client)
    before_rev, before_pending = _rev(client, eid), _pending_ids(client, eid)
    assert key in before_pending, f"fixture no longer raises a {key} question"

    response = _answer(client, eid, {key: value})

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_field_value", body
    assert body["key"] == key, body
    assert body["keys"] == [key], body
    assert "not a shape the record can store" in body["message"], body["message"]
    # AND THE MESSAGE MAKES NEITHER OF THE TWO CLAIMS THE OLD 200 MADE.
    assert FALSE_CAUSE not in body["message"], body["message"]
    assert "identical" not in body["message"], body["message"]
    # Nothing was written and the question is exactly where the caller left it.
    assert _rev(client, eid) == before_rev
    assert _pending_ids(client, eid) == before_pending


@pytest.mark.parametrize("key,value", UNSTORABLE)
def test_the_refusal_is_the_same_at_the_run_level(client, key, value):
    """The run route is the one a fan-out record's client actually calls."""
    eid, rid = _run_fixture(client)
    before = _rev(client, eid)

    response = client.post(
        f"/api/experiments/{eid}/runs/{rid}/answers",
        json={"confirmed_by_user": True, "answers": {key: value}},
        headers={"If-Match": _run_etag(client, eid, rid)},
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_field_value", body
    assert body["keys"] == [key], body
    assert _rev(client, eid) == before, "nothing may have been written"


def test_the_refusal_names_every_offending_key_not_the_first(client):
    """This module's standing convention for a refusal a client has to act on."""
    eid = _created(client)

    response = _answer(client, eid, {"qc": "valid", "series": [], "descriptor": "x"})

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_field_value"
    assert sorted(body["keys"]) == ["descriptor", "qc", "series"], body


def test_one_unstorable_key_refuses_the_whole_body_so_nothing_lands_by_halves(client):
    """A partially-applied write is a state no response could describe honestly."""
    eid = _created(client)
    good_series = [{"series_id": "s1", "energy_eV": [7112.0], "mu": [0.5]}]
    before_pending = _pending_ids(client, eid)

    response = _answer(client, eid, {"series": good_series, "qc": "valid"})

    assert response.status_code == 422, response.text
    assert response.json()["keys"] == ["qc"], response.json()
    assert _pending_ids(client, eid) == before_pending, (
        "the well-formed series must NOT have landed: the refusal happens before the "
        "write, so the caller can resend the whole body once the bad key is fixed"
    )


def test_the_closed_loop_is_broken_at_its_first_step(client):
    """The four-step cycle from this file's docstring, walked as a client would.

    The loop existed because step 1 was a `200`. It is now a `422` naming the key, so
    steps 2-4 are never reached — and the test asserts the OLD step 4 as a negative
    control, so a regression that restores the `200` fails here rather than silently
    re-opening the cycle.
    """
    eid = _created(client)

    step_1 = _answer(client, eid, {"qc": "valid"})
    assert step_1.status_code == 422, step_1.text
    assert step_1.json()["error"] == "invalid_field_value"

    # The remedy the OLD response steered a client towards, which was the dead end.
    step_4 = client.post(
        f"/api/experiments/{eid}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": {"status": "valid"}}},
        headers={"If-Match": _etag(client, eid)},
    )
    assert step_4.status_code == 422, step_4.text
    assert step_4.json()["error"] == "not_yet_answered", step_4.json()
    # The dead end is still a dead end; what changed is that nothing sends you into it.


# ---------------------------------------------------------------------------
# An unrecognised key
# ---------------------------------------------------------------------------


def test_an_unrecognised_key_is_refused_rather_than_dropped_in_silence(client):
    """The record never held this key, so nothing about it can be 'identical'."""
    eid = _created(client)
    before_rev, before_pending = _rev(client, eid), _pending_ids(client, eid)

    response = _answer(client, eid, {MADE_UP_KEY: "PROBE-VALUE"})

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrecognized_field", body
    assert body["keys"] == [MADE_UP_KEY], body
    assert body["experiment_id"] == eid, body
    assert FALSE_CAUSE not in body["message"], body["message"]
    # The caller's VALUE is not echoed back — it has no business in an error body.
    assert "PROBE-VALUE" not in response.text, response.text
    assert _rev(client, eid) == before_rev
    assert _pending_ids(client, eid) == before_pending


def test_the_run_level_route_refuses_an_unrecognised_key_too(client):
    """Same defect, the level a fan-out record uses."""
    eid, rid = _run_fixture(client)
    before = _rev(client, eid)

    response = client.post(
        f"/api/experiments/{eid}/runs/{rid}/answers",
        json={"confirmed_by_user": True, "answers": {MADE_UP_KEY: "PROBE-VALUE"}},
        headers={"If-Match": _run_etag(client, eid, rid)},
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unrecognized_field", body
    assert body["run_id"] == rid, body
    assert _rev(client, eid) == before


def test_a_ride_along_unrecognised_key_is_dropped_but_no_longer_LIED_ABOUT(client):
    """THE NARROW RULE'S OTHER HALF, and the case that decided the rule's boundary.

    Refusing EVERY unrecognised key was implemented first and rejected — it misdirects a
    run-owned asset hash sent to the record, it split the two ingresses' rules, and it
    broke 22 tests in five files whose subject is not this defect. The argument is in
    `routes._refuse_a_body_that_names_nothing_answerable`.

    So a ride-along key is still dropped, exactly as on the correction operations. What
    changed is that the response no longer says the submitted value was identical, which
    a reader would have applied to the key that vanished.
    """
    eid = _created(client)
    verdict = {"status": "valid", "evidence": "I0 stable."}
    landed = _answer(client, eid, {"qc": verdict, MADE_UP_KEY: "x"})

    assert landed.status_code == 200, landed.text
    assert landed.json()["invalidation"]["changed_fields"] == ["qc"], landed.json()
    assert "qc" not in _pending_ids(client, eid), "the recognised half must have landed"

    # The SAME body again: the qc verdict is now identical, and one key is still dropped.
    again = _answer(client, eid, {"qc": verdict, MADE_UP_KEY: "x"})
    assert again.status_code == 200, again.text
    invalidation = again.json()["invalidation"]
    assert invalidation["changed"] is False, invalidation
    assert FALSE_CAUSE not in invalidation["reason"], (
        "a no-op over a body that dropped a key may not claim the submitted value was "
        f"identical: {invalidation['reason']!r}"
    )


def test_a_bare_descriptor_label_claims_no_comparison_either(client):
    """The inert key. `apply_answers` builds the whole descriptor block or none of it.

    A label with no descriptor is recognised, storable and written NOWHERE, so it is the
    one recognised key for which `changed=False` proves nothing about a stored value.
    """
    eid = _created(client)

    response = _answer(client, eid, {"descriptor_label": "relabel"})

    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]
    assert invalidation["changed"] is False, invalidation
    assert FALSE_CAUSE not in invalidation["reason"], invalidation["reason"]


def test_a_blank_value_under_an_unrecognised_key_is_still_dropped(client):
    """NEGATIVE CONTROL. A blank answer is not an answer, and never was one.

    The screen never sends one, and a body of blanks has always been a byte-stable
    no-op. Refusing it would break that for no gain — and the no-op's reason must not
    claim a comparison either, which the second half asserts.
    """
    eid = _created(client)
    before_rev = _rev(client, eid)

    response = _answer(client, eid, {MADE_UP_KEY: "", "series": None})

    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]
    assert invalidation["changed"] is False, invalidation
    assert _rev(client, eid) == before_rev
    assert FALSE_CAUSE not in invalidation["reason"], invalidation["reason"]


def test_the_correction_route_still_tolerates_a_ride_along_key(client):
    """NEGATIVE CONTROL for the scope of this slice.

    `/edit`'s tolerance is pinned by an argued test of its own and its report about
    ride-alongs is already honest. Widening the refusal to it is a separate decision;
    this asserts that this slice did not take it silently.
    """
    eid = _created(client)
    assert _answer(client, eid, {"qc": {"status": "valid", "evidence": "note"}}).status_code == 200

    response = client.post(
        f"/api/experiments/{eid}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "failed", "evidence": "note"}, MADE_UP_KEY: "x"},
        },
        headers={"If-Match": _etag(client, eid)},
    )

    assert response.status_code == 200, response.text
    assert response.json()["invalidation"]["changed_fields"] == ["qc"], response.json()


# ---------------------------------------------------------------------------
# The no-op reason no longer claims a comparison that did not happen
# ---------------------------------------------------------------------------


def test_an_identical_resubmission_is_a_200_that_still_says_so(client):
    """THE PROPERTY THREE EXISTING TESTS PIN, asserted here on the reason as well.

    A previous attempt at a related refusal broke all three. A client must be able to
    retry a call it is unsure landed — and for a genuinely identical resubmission the
    identical-value sentence is simply TRUE, so it is still served.
    """
    eid = _created(client)
    verdict = {"qc": {"status": "valid", "evidence": "I0 stable across all scans."}}
    assert _answer(client, eid, verdict).status_code == 200
    settled = _rev(client, eid)

    again = _answer(client, eid, verdict)

    assert again.status_code == 200, again.text
    invalidation = again.json()["invalidation"]
    assert invalidation["changed"] is False, invalidation
    assert invalidation["reason"] == NO_OP_IDENTICAL_REASON, invalidation["reason"]
    assert _rev(client, eid) == settled, "a retry must not advance the revision"


def test_a_malformed_asset_sha_is_a_200_whose_reason_claims_no_comparison(client):
    """THE ONE DECLINED VALUE THAT IS DELIBERATELY STILL A 200 — and it stops lying.

    `GuidedCompletion` renders "That answer was not applied … nothing was invented in
    its place" for exactly this case, and a browser mutation spec asserts the status is
    `200` so the client cannot lean on an error. Refusing it is a frontend change as
    much as a backend one. What is fixed here is the sentence beside it: the record has
    never held this URI's hash, so nothing about it can be identical.
    """
    seeded = tutorial_client(client.app)
    listed = seeded.get("/api/experiments").json()["experiments"]
    target = next(e["id"] for e in listed if e["pending_count"] >= 1)
    pending = seeded.get(f"/api/experiments/{target}/pending").json()["pending"]
    uri = next((q["id"] for q in pending if q["kind"] == "asset"), None)
    if uri is None:
        pytest.skip("no seeded record raises an asset blocker")

    etag = seeded.get(f"/api/experiments/{target}").headers["ETag"]
    response = seeded.post(
        f"/api/experiments/{target}/answers",
        json={"confirmed_by_user": True, "answers": {uri: "Z" * 64}},
        headers={"If-Match": etag},
    )

    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]
    assert invalidation["changed"] is False, invalidation
    assert FALSE_CAUSE not in invalidation["reason"], invalidation["reason"]
    assert uri in [q["id"] for q in response.json()["pending"]], "the blocker must stay open"


def test_an_empty_answers_body_claims_no_comparison_either(client):
    """Nothing was submitted, so "the submitted value" names nothing to compare."""
    eid = _created(client)

    response = _answer(client, eid, {})

    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]
    assert invalidation["changed"] is False, invalidation
    assert FALSE_CAUSE not in invalidation["reason"], invalidation["reason"]


# ---------------------------------------------------------------------------
# The published contract says what the route does
# ---------------------------------------------------------------------------


def test_both_answers_operations_declare_the_two_refusals_they_perform(client):
    """A behaviour added without the sentence repeats the gap this module keeps closing.

    `_R_CORRECTION_REFUSED`'s own note records an operation whose "422 enumerated three
    refusals while the route performed four". A contract CHANGE — refusing a key that
    was documented as ignored — has to be declared, not merely implemented.
    """
    document = client.get("/api/openapi").json()
    for path in (
        "/api/experiments/{experiment_id}/answers",
        "/api/experiments/{experiment_id}/runs/{run_id}/answers",
    ):
        description = document["paths"][path]["post"]["responses"]["422"]["description"]
        assert "unrecognized_field" in description, path
        assert "invalid_field_value" in description, path
        # The withdrawn sentence survives ONLY as a struck-through correction. Deleting
        # it would hide that the contract used to say the opposite.
        assert "~~A wrong-TYPED value is NOT this refusal" in description, path
        assert "WITHDRAWN" in description, path

    prose = document["paths"]["/api/experiments/{experiment_id}/answers"]["post"]["description"]
    assert "unrecognized_field" in prose, prose
    assert "invalid_field_value" in prose, prose


def test_the_mcp_tool_no_longer_states_the_two_false_sentences(client):
    """The two sentences the verification measured false, and their replacements.

    Both were consequences of the route's behaviour rather than independent mistakes,
    so fixing the route without fixing them would have left the tool description as
    the surviving false claim.
    """
    from isaac_api.mcp.tools import TOOLS

    description = TOOLS["isaac_answer_questions"].description

    # The false sentence is kept ONLY inside a strike, which is this repository's
    # remedy: a reader must be able to see that it was said and is withdrawn.
    assert "is ignored rather than guessed" in description
    assert "~~an UNRECOGNISED key naming no open question" in description
    assert "measurably false" in description
    # ...and the truth that replaces it.
    assert "EITHER ACTED ON OR REFUSED BY NAME" in description
    assert "unrecognized_field" in description
    assert "invalid_field_value" in description
    # The retry-is-safe sentence keeps its guarantee AND gains the reason it used to
    # be dangerous on its own.
    assert "a retry of a call you are unsure landed is safe" in description
    assert "we threw your value away" in description

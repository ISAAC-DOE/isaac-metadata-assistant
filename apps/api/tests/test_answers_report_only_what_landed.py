"""`changed_fields` must name what was WRITTEN, not what was submitted.

THE DEFECT THIS CLOSES, measured over HTTP by an independent review
===================================================================
On a LEGACY run — one created before ``_seed_for_new_run`` existed, so its draft
carries no ``pending`` key — a wrong-typed answer was reported as an update::

    POST /api/experiments/{id}/runs/{run_id}/answers  {"series": "not-a-list"}
      -> 200
         invalidation.changed        true
         invalidation.changed_fields ["series"]
         invalidation.reason         "Updated 1 field(s); no downstream steps
                                      reopened."
         stored series AFTER         None
         `series` STILL an open question

The identical request against a SEEDED run reported ``changed: false``, correctly.

The two halves of the answer came from different places and only one of them was
about the write. ``changed`` is ``save_versioned()``'s verdict — true here because
``routes._apply_to_run`` MATERIALISES a legacy run's derived questions into the
document before writing, which is a real change to the document. ``changed_fields``
was derived from the SUBMITTED shape and never consulted the result.

**THIS IS THE MIRROR OF THE ``already_answered`` DEFECT THIS BRANCH FIXED, POLARITY
REVERSED**, on exactly the runs the branch's legacy handling was written for: that one
said *"the submitted value was identical"* about a value that had changed; this one
said *"Updated 1 field(s)"* about a value that was never stored.

WHAT MUST NOT REGRESS WHILE FIXING IT
=====================================
Materialising a legacy run's template IS a change, the revision SHOULD move, and
``changed`` must stay ``true`` — reverting that would re-open the 200 that destroyed a
run's questions (``test_run_level_answers.py``). Only the NAMING is narrowed. Both
halves are asserted here, in the same test, so a future "simplification" that turns
``changed`` off to make ``changed_fields`` empty fails.

Nothing here opens a network connection, reads real data, or touches a database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

SERIES = [
    {
        "series_id": "averaged_spectrum",
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [8970, 8980, 8990]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [0.02, 0.85, 1.45],
            }
        ],
    }
]
DESCRIPTOR = {
    "name": "inflection_point_energy",
    "kind": "absolute",
    "source": "manual",
    "value": 9001.2,
    "unit": "eV",
    "uncertainty": {"sigma": 0.01, "unit": "eV", "basis": "reported"},
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _version(client, exp_id):
    return client.get(f"/api/experiments/{exp_id}").json()["version"]


def _run_etag(client, exp_id, run_id):
    return client.get(f"/api/experiments/{exp_id}/runs/{run_id}").headers["ETag"]


def _legacy_run(client, draft=None):
    """A run with NO `pending` key — exactly what pre-seeding runs are on disk."""
    exp_id = client.post("/api/experiments", json={"title": "Legacy"}).json()["id"]
    exp = ws.load_experiment(exp_id)
    run = exp.add_run(label="Legacy run", draft=dict(draft or {}))
    exp.save()
    assert "pending" not in ws.load_experiment(exp_id).get_run(run.id).draft
    return exp_id, run.id


def _seeded_run(client):
    exp_id = client.post("/api/experiments", json={"title": "Seeded"}).json()["id"]
    run_id = (
        client.post(
            f"/api/experiments/{exp_id}/runs",
            json={"label": "300 K"},
            headers={"If-Match": f'"{_version(client, exp_id)}"'},
        )
        .json()["run"]["id"]
    )
    return exp_id, run_id


# ---------------------------------------------------------------------------
# the run path — where it was measured
# ---------------------------------------------------------------------------


def test_a_declined_answer_on_a_legacy_run_names_no_updated_field(client):
    """THE REGRESSION TEST. 200, the revision moves, and NOTHING is named.

    THE VEHICLE CHANGED ON 2026-08-25 AND THE SUBJECT DID NOT. This sent
    ``{"series": "not-a-list"}``, which is now ``422 invalid_field_value`` — asserted at
    the bottom of this test, so the coverage moved rather than vanished. The property
    under test was never about the wrong TYPE; it is that a key the core RECEIVED and
    did not write must not be named as updated on a document that moved for another
    reason. ``descriptor_label`` is the honest remaining vehicle for exactly that: both
    core writers build the whole descriptor block and gate it on
    ``descriptor is not None``, so a bare label is received, stored NOWHERE, and
    deliberately outside the shape screen (see ``_SHAPE_SCREENED_ANSWER_KEYS``).
    """
    exp_id, run_id = _legacy_run(client)
    response = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": {"descriptor_label": "relabel"}, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]

    # THE FIX: no field is named, and the count in the sentence follows the list.
    assert invalidation["changed_fields"] == [], invalidation
    assert "Updated 0 field(s)" in invalidation["reason"], invalidation

    # THE HALF THAT MUST NOT REGRESS: the document really did change (the derived
    # questions were materialised), so `changed` stays true.
    assert invalidation["changed"] is True, invalidation

    # And the write really was declined: nothing stored, questions still open.
    stored = ws.load_experiment(exp_id).get_run(run_id).draft
    assert stored.get("descriptors_outputs") in (None, []), stored
    assert "descriptor" in {e["kind"] for e in stored["pending"]}, stored["pending"]

    # WHERE THE OLD VEHICLE WENT. A wrong-TYPED value is now refused by name before any
    # write, so it can no longer reach the reporting code this test guards at all.
    refused = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": {"series": "not-a-list"}, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "invalid_field_value", refused.json()


def test_the_same_request_on_a_seeded_run_is_unchanged(client):
    """The control the defect report itself used: the seeded path was already right.

    Same re-vehicling as the test above, for the same reason.
    """
    exp_id, run_id = _seeded_run(client)
    response = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": {"descriptor_label": "relabel"}, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]
    assert invalidation["changed"] is False, invalidation
    assert invalidation["changed_fields"] == [], invalidation
    # AND THE NO-OP CLAIMS NOTHING. A bare label is written nowhere, so `changed=False`
    # proves nothing about a stored value and the reason must not say it does.
    assert "identical" not in invalidation["reason"], invalidation


def test_a_good_answer_on_a_legacy_run_is_still_named(client):
    """NEGATIVE CONTROL. Narrowing the claim must not silence a real write.

    Reporting nothing would be the same class of false statement in the other
    direction, and is the cheapest way to make the test above pass for the wrong
    reason.
    """
    exp_id, run_id = _legacy_run(client)
    response = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={
            "answers": {"qc": {"status": "valid", "evidence": "I0 stable."}},
            "confirmed_by_user": True,
        },
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]
    assert invalidation["changed_fields"] == ["qc"], invalidation
    assert "Updated 1 field(s)" in invalidation["reason"], invalidation
    stored = ws.load_experiment(exp_id).get_run(run_id).draft
    assert stored["qc"] == {"status": "valid", "evidence": "I0 stable."}


def test_a_legacy_run_answered_with_the_value_it_already_holds_still_counts(client):
    """THE CASE A VALUE COMPARISON ALONE WOULD GET WRONG.

    `_apply_to_run` materialises a legacy run's derived questions from the BLANK-draft
    template, so it lists `qc` even for a run that already HOLDS a verdict — a state
    `draft_builder` never produces and `complete.apply_answers` records as reachable
    over HTTP. Answering it with the value already stored moves no value, and closes a
    question that was genuinely open. The blocker-resolution half of
    `_fields_the_write_landed` is what catches it.
    """
    verdict = {"status": "valid", "evidence": "I0 stable."}
    exp_id, run_id = _legacy_run(client, draft={"qc": dict(verdict)})
    shown = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert "qc" in {q["id"] for q in shown}, shown

    response = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": {"qc": dict(verdict)}, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]
    assert invalidation["changed_fields"] == ["qc"], invalidation
    stored = ws.load_experiment(exp_id).get_run(run_id).draft
    assert "qc" not in {e["kind"] for e in stored["pending"]}, stored["pending"]


# ---------------------------------------------------------------------------
# the record path — the same helper, the same defect shape
# ---------------------------------------------------------------------------


def test_a_mixed_request_on_a_record_names_only_the_field_that_landed(client):
    """The record path had the same hole, reachable by combining two answers.

    One good value makes `changed` true; a wrong-typed one beside it was named as
    updated on the strength of the first one's write. Measured on the same code path
    as the run defect, one level up.
    """
    exp_id = client.post("/api/experiments", json={"title": "Mixed"}).json()["id"]
    # ~~`{"series": SERIES, "descriptor": "not-a-mapping"}`~~ — the wrong-typed half is
    # now `422 invalid_field_value` and the whole body is refused, which is asserted at
    # the end of this test. `descriptor_label` is the remaining key the core receives and
    # writes nowhere, so it exercises the same reporting rule.
    response = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "answers": {"series": SERIES, "descriptor_label": "relabel"},
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]
    assert invalidation["changed"] is True, invalidation
    assert invalidation["changed_fields"] == ["series"], invalidation
    assert "Updated 1 field(s)" in invalidation["reason"], invalidation
    stored = ws.load_experiment(exp_id).draft
    assert stored.get("descriptors_outputs") in (None, []), stored.get(
        "descriptors_outputs"
    )

    # WHERE THE OLD VEHICLE WENT: one unstorable key refuses the WHOLE body, so a
    # partially-applied write is not a state any response has to describe.
    other = client.post("/api/experiments", json={"title": "Mixed 2"}).json()["id"]
    refused = client.post(
        f"/api/experiments/{other}/answers",
        json={
            "answers": {"series": SERIES, "descriptor": "not-a-mapping"},
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{_version(client, other)}"'},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["keys"] == ["descriptor"], refused.json()
    assert ws.load_experiment(other).draft.get("series") is None, "nothing may land"


def test_a_record_correction_that_lands_is_still_named(client):
    """NEGATIVE CONTROL for the `/edit` call site, which shares the helper."""
    exp_id = client.post("/api/experiments", json={"title": "Correct me"}).json()["id"]
    client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "answers": {"qc": {"status": "valid", "evidence": "I0 stable."}},
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    response = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={
            "answers": {"qc": {"status": "compromised", "evidence": "Beam dropped."}},
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert response.status_code == 200, response.text
    invalidation = response.json()["invalidation"]
    assert invalidation["changed_fields"] == ["qc"], invalidation


# ---------------------------------------------------------------------------
# the guard on the table
# ---------------------------------------------------------------------------


def test_every_shaped_answer_key_has_a_value_slot():
    """A key added to `_answers_to_apply_shape` without a slot must fail HERE.

    `_fields_the_write_landed` falls back to the older, weaker claim for a key it
    cannot locate — under-reporting an update is its own false statement, so silently
    dropping the field would be worse. That fallback is only safe while it is
    unreachable, and this is what keeps it unreachable.

    The key set is read off `_answers_to_apply_shape`'s own source rather than
    restated, so adding a branch there without a slot here turns this red.
    """
    import ast
    import inspect

    import isaac_api.routes as routes

    source = inspect.getsource(routes._answers_to_apply_shape)
    tree = ast.parse(source.lstrip())
    # Every string literal the function compares a key against or assigns into `out`,
    # excluding the two structural keys.
    literals: set[str] = set()
    for node in ast.walk(tree):
        # Anchored on the loop variable `key`, not on any comparison: the function
        # also tests `value in (None, "")`, and a comparator-blind sweep collected
        # the empty string as though it were an answer key.
        if (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == "key"
        ):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(
                    comparator.value, str
                ):
                    literals.add(comparator.value)
                elif isinstance(comparator, ast.Tuple):
                    for element in comparator.elts:
                        if isinstance(element, ast.Constant) and isinstance(
                            element.value, str
                        ):
                            literals.add(element.value)
    assert literals, (
        "no shaped-answer key literals were found in `_answers_to_apply_shape`; the "
        "extraction above no longer matches its shape, which would make this guard "
        "vacuous. Fix the extraction rather than deleting the test."
    )
    missing = sorted(literals - set(routes._ANSWER_KEY_VALUE_SLOT))
    assert not missing, (
        f"`_answers_to_apply_shape` forwards {missing} and `_ANSWER_KEY_VALUE_SLOT` "
        "does not say where their values land, so `_fields_the_write_landed` would "
        "fall back to naming them without checking. Add the slot."
    )

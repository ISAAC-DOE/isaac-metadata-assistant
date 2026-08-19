"""A scientist can now finish a record they created. Before this slice, they could not.

THE DEFECT THIS FILE PINS
=========================
`POST /api/experiments` creates a record. Its draft raises three blocking questions —
`series`, `descriptor`, `qc` — and `POST /answers` could answer exactly two of them.
`_answers_to_apply_shape` forwarded `series`, `descriptor`, `descriptor_label`, `edge`
and asset hashes, and **never `qc`**. So the record could be completed as far as the
product allowed and still refuse to export, with:

    draft_report.errors[0].message ==
      "measurement has series but qc verdict has no evidence; confirm or supply
       provenance (no default 'valid')"

and no route anywhere that could supply the verdict. Measured on `main` before the fix:
`pending` came back `['qc']` after applying every answer the API accepts, `status`
stayed `needs_attention`, and `POST /export` answered `200 {"ok": false}` forever.

**Why no existing test caught it.** All five canonical scenarios are built by
`build_draft` from a fixture sheet that already carries a `qc` verdict, so every
completion/export test in the suite starts past the one question the API cannot answer.
The gap was only reachable through the path a real scientist takes, and nothing took it.

That is why the first test here drives the WHOLE path over HTTP rather than asserting
on `_answers_to_apply_shape` directly: a unit test of the mapper would have been
satisfied by the mapper, and the mapper was not what was wrong — the product was.

WHAT IS DELIBERATELY NOT CLAIMED
================================
This slice does not classify anything, does not change what a QC verdict MEANS, and
does not decide when one is required. `complete.py` already owned the enum, already
refused to invent a default, and already wrote the evidence entry; all of that is
unchanged and none of it moved into the route. The route learned to pass a value along.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from conftest import tutorial_client, tutorial_ws


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


def _harvested_answers(app) -> dict:
    """Every answer the seeded scenario offers — everything EXCEPT a QC verdict.

    Harvested rather than hardcoded so this file cannot drift from the fixtures, and
    deliberately NOT extended with a `qc` entry: the point of the first test is that
    this set is everything the product could previously supply.
    """
    seeded = tutorial_client(app)
    raw = [
        e for e in seeded.get("/api/experiments").json()["experiments"] if e["pending_count"] == 5
    ][0]
    pending = seeded.get(f"/api/experiments/{raw['id']}/pending").json()["pending"]
    harvested = {b["id"]: b["demo_answer"]["value"] for b in pending if b["demo_answer"]}
    assert "qc" not in harvested, "the seed now ships a qc demo answer; re-read this file"
    return harvested


def _new_record(client) -> str:
    created = client.post("/api/experiments", json={"title": "A record a scientist made"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _version(client, exp_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}").json()["version"]


def _answer(client, exp_id: str, answers: dict):
    return client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )


def _export(client, exp_id: str):
    return client.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )


# ---------------------------------------------------------------------------
# The path a scientist actually takes
# ---------------------------------------------------------------------------


def test_a_record_created_through_the_product_can_now_be_completed_and_exported(app):
    """THE REGRESSION TEST FOR THE WHOLE DEFECT. Create -> answer -> export, over HTTP.

    Remove `"qc"` from `_answers_to_apply_shape`'s forwarded key tuple and this fails
    at the `pending == []` assertion — which is exactly where the product failed.
    """
    answers = _harvested_answers(app)
    client = TestClient(app)
    exp_id = _new_record(client)

    partial = _answer(client, exp_id, answers)
    assert partial.status_code == 200, partial.text
    assert [q["id"] for q in partial.json()["pending"]] == ["qc"], (
        "the pre-fix state: everything answerable is answered, and qc remains"
    )

    finished = _answer(
        client,
        exp_id,
        {
            "qc": {
                "status": "valid",
                "evidence": "I0 stable across all scans; no glitches in the merged spectrum.",
            }
        },
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["pending"] == [], finished.json()["pending"]
    assert finished.json()["status"] == "ready_to_export", finished.json()["status"]

    exported = _export(client, exp_id)
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True, exported.json()


def test_the_verdict_and_its_evidence_are_what_reach_the_official_record(app):
    """The value has to arrive in the RECORD, not merely leave `pending`.

    A blocker that clears without the verdict landing would be the worse defect: the
    product would say the question was answered while the record said nothing.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))
    _answer(
        client,
        exp_id,
        {"qc": {"status": "compromised", "evidence": "Beam dropped during scan 3."}},
    )
    assert _export(client, exp_id).json()["ok"] is True

    exp = ws.load_experiment(exp_id)
    record = json.loads(exp.export_units()[0].record_path().read_text(encoding="utf-8"))
    assert record["measurement"]["qc"]["status"] == "compromised"
    assert record["measurement"]["qc"]["evidence"] == "Beam dropped during scan 3."


def test_the_answer_is_recorded_as_a_user_confirmation_in_the_evidence_trail(app):
    """A verdict is a scientific judgement, so the trail must say a person made it."""
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))
    _answer(client, exp_id, {"qc": {"status": "failed", "evidence": "Sample degraded."}})

    trail = ws.load_experiment(exp_id).draft["block_evidence"]["qc:status"]
    assert trail, "answering qc left no evidence entry"
    assert any("failed" in json.dumps(entry) for entry in trail)


# ---------------------------------------------------------------------------
# NEGATIVE CONTROLS — the no-guessing rules the route must not have weakened
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verdict",
    ["VALID", "ok", "good", "", "probably valid", "Valid", None, 7, [], {"status": "valid"}],
)
def test_an_off_enum_verdict_is_never_stored_and_the_question_stays_open(app, verdict):
    """NEGATIVE CONTROL: the route must not have widened the enum by forwarding the key.

    `complete._QC_STATUSES` is the only definition of an acceptable verdict, and the
    route reaches it through `is_qc_shaped` rather than restating it. Anything outside
    it leaves the blocker OPEN — the response itself tells the caller nothing happened.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))

    res = _answer(client, exp_id, {"qc": {"status": verdict}})
    assert res.status_code == 200, res.text
    assert [q["id"] for q in res.json()["pending"]] == ["qc"], res.json()["pending"]
    assert (ws.load_experiment(exp_id).draft.get("qc") or {}).get("status") is None


def test_no_verdict_is_ever_invented_by_omission(app):
    """NEGATIVE CONTROL for the rule the blocker's own text states: no default 'valid'.

    An empty qc answer, and a qc answer that is not a mapping at all, must both leave
    the record with NO verdict — never a helpful assumed one.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))

    for empty in ({}, "", None, "valid"):
        _answer(client, exp_id, {"qc": empty})
        assert (ws.load_experiment(exp_id).draft.get("qc") or {}).get("status") is None, empty

    assert _export(client, exp_id).json()["ok"] is False


def test_a_verdict_with_a_non_string_evidence_note_is_refused_not_stored(app):
    """`measurement.qc.evidence` is a schema string; a dict there would validate late.

    Refusing at the route is what stops a 200 about a record official validation will
    then reject — the failure landing one step further from the person who caused it.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))

    res = _answer(client, exp_id, {"qc": {"status": "valid", "evidence": {"note": "x"}}})
    assert res.status_code == 200, res.text
    assert [q["id"] for q in res.json()["pending"]] == ["qc"]
    assert (ws.load_experiment(exp_id).draft.get("qc") or {}).get("status") is None


def test_the_route_does_not_carry_its_own_copy_of_the_verdict_enum(app):
    """NEGATIVE CONTROL for the two definitions drifting apart.

    If the route ever spells the four verdicts itself, a fifth added to the schema is
    accepted here and declined by the core — a 200 that changed nothing, which is the
    exact defect `is_sha256_shaped` was added to close for a different key.
    """
    import isaac_api.routes as routes

    source = pathlib.Path(routes.__file__).read_text(encoding="utf-8")
    # ONLY `compromised` is scanned, and the other three are named here rather than
    # looped over so the omission is a stated choice: `valid`, `failed` and `pending` are
    # ordinary English words that appear throughout this file in prose and in unrelated
    # identifiers (`pending`, `pending_count`, `draft_ok`), so their presence proves
    # nothing. `compromised` appears nowhere else, which makes it the one reliable
    # tripwire for the enum having been copied.
    assert '"compromised"' not in source, (
        "routes.py spells a verdict itself instead of deferring to is_qc_shaped"
    )
    from isaac_records.complete import is_qc_shaped

    assert "is_qc_shaped" in source, "the route stopped using the shared predicate"
    assert is_qc_shaped({"status": "compromised"}) is True


# ---------------------------------------------------------------------------
# The correction path — a wrong verdict must be fixable
# ---------------------------------------------------------------------------


def test_a_recorded_verdict_can_be_corrected_afterwards(app):
    """Answering `qc` removes it from `pending`, so `/answers` cannot revise it.

    Without the `/edit` half, a scientist who mis-clicked would own a wrong scientific
    judgement permanently — which is a worse product than one that cannot record a
    verdict at all, and is why this slice enabled both paths rather than one.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))
    _answer(client, exp_id, {"qc": {"status": "valid", "evidence": "First reading."}})
    assert ws.load_experiment(exp_id).draft["qc"]["status"] == "valid"

    corrected = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {
                "qc": {"status": "compromised", "evidence": "Re-checked: I0 drifted."}
            },
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["invalidation"]["changed_fields"] == ["qc"]

    draft = ws.load_experiment(exp_id).draft
    assert draft["qc"]["status"] == "compromised"
    assert draft["qc"]["evidence"] == "Re-checked: I0 drifted."
    # BOTH readings survive. A correction is a new judgement, not the erasure of the
    # old one — the trail is what lets a reviewer see that the verdict changed.
    assert len(draft["block_evidence"]["qc:status"]) == 2


def test_an_edit_naming_only_an_unusable_verdict_is_refused_rather_than_absorbed(app):
    """`/edit` has no pending blocker to leave open, so silence there is genuinely silent.

    The route's own comment says a body naming a recognised field with an unusable value
    gets a typed refusal rather than a 200. `qc` must obey that rule like every other key.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))
    _answer(client, exp_id, {"qc": {"status": "valid", "evidence": "First reading."}})

    res = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": {"status": "excellent"}}},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert res.status_code == 422, res.text
    # THE ERROR CODE MATTERS, and asserting only `422` made this test pass with the fix
    # REVERTED — pre-fix the same body was refused by `_has_correction_target` as
    # `unrecognized_field`, for the opposite reason (the route did not know `qc` at all).
    # `invalid_field_value` is the claim the docstring actually makes: the field IS
    # recognised, and this particular value cannot be stored.
    body = res.json()
    assert body["error"] == "invalid_field_value", body
    assert body.get("fields") == ["qc"] or "qc" in json.dumps(body), body
    assert ws.load_experiment(exp_id).draft["qc"]["status"] == "valid"


def test_re_sending_an_identical_verdict_changes_nothing_and_does_not_advance_rev(app):
    """The documented no-op. Unchanged-because-equal is not unchanged-because-unusable."""
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))
    _answer(client, exp_id, {"qc": {"status": "valid", "evidence": "First reading."}})
    before = ws.load_experiment(exp_id).rev

    client.post(
        f"/api/experiments/{exp_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "valid", "evidence": "First reading."}},
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert ws.load_experiment(exp_id).rev == before
    assert len(ws.load_experiment(exp_id).draft["block_evidence"]["qc:status"]) == 1


# ---------------------------------------------------------------------------
# The worked-example scenarios must be untouched by this
# ---------------------------------------------------------------------------


def test_the_canonical_scenarios_still_carry_the_verdicts_they_shipped_with(app):
    """This slice added a route, not a fixture change. The five seeds must be identical.

    AN EARLIER VERSION OF THIS TEST WAS VACUOUS and an independent review measured why:
    it asserted only that `"qc"` did not appear in `draft["pending"]`, and three of the
    five seeds have an EMPTY pending list — so it would have passed unchanged if every
    seed's verdict had been deleted. It now reads the verdict itself.
    """
    seeded = tutorial_client(app)
    listing = seeded.get("/api/experiments").json()["experiments"]
    assert len(listing) == 5, listing
    for exp in listing:
        draft = tutorial_ws().load_experiment(exp["id"]).draft
        assert draft["qc"]["status"] == "valid", (exp["id"], draft.get("qc"))
        assert "qc" not in json.dumps(draft.get("pending") or [])


# ---------------------------------------------------------------------------
# THE VERDICT AND ITS REASONING ARE ONE VALUE — findings C1 and I3
# ---------------------------------------------------------------------------


def test_flipping_the_verdict_does_not_leave_the_old_reasoning_attached(app):
    """CRITICAL REGRESSION TEST. An independent review measured this end to end.

    Correcting `compromised` -> `valid` with no new note used to KEEP the old one, so an
    exported official record read::

        {"status": "valid", "evidence": "Beam dropped during scan 3; spectrum unusable."}

    Official validation passed. The advisory tier was silent, because
    `QC_NONVALID_WITHOUT_EVIDENCE` does not fire for `valid`. And `block_evidence` gained
    a confirmation naming "valid", so the trail looked correct while the record's own
    provenance contradicted its verdict. That is `CLAUDE.md` §5 inverted: the evidence is
    present, and it is false.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))
    _answer(
        client,
        exp_id,
        {"qc": {"status": "compromised", "evidence": "Beam dropped during scan 3."}},
    )

    corrected = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": {"status": "valid"}}},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert corrected.status_code == 200, corrected.text

    stored = ws.load_experiment(exp_id).draft["qc"]
    assert stored["status"] == "valid"
    assert "evidence" not in stored, (
        f"the note that justified the OLD verdict is still attached: {stored}"
    )

    assert _export(client, exp_id).json()["ok"] is True
    record = json.loads(
        ws.load_experiment(exp_id).export_units()[0].record_path().read_text(encoding="utf-8")
    )
    assert "Beam dropped" not in json.dumps(record["measurement"]["qc"]), record["measurement"]["qc"]


def test_correcting_only_the_reasoning_is_applied_and_reported_truthfully(app):
    """REGRESSION TEST for I3: "the submitted value was identical" about a changed value.

    `apply_corrections` compared only `status`, so an evidence-only correction was
    declined — and `build_invalidation` then asserted the submitted value was identical
    when it was not. A scientist had no way to correct the reasoning behind a verdict,
    and the product told them they already had.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))
    _answer(client, exp_id, {"qc": {"status": "valid", "evidence": "first note"}})

    corrected = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "valid", "evidence": "I re-checked I0 and it drifted."}},
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert corrected.status_code == 200, corrected.text
    invalidation = corrected.json()["invalidation"]
    assert invalidation["changed"] is True, invalidation
    assert invalidation["changed_fields"] == ["qc"], invalidation
    assert "identical" not in invalidation["reason"], invalidation["reason"]

    assert ws.load_experiment(exp_id).draft["qc"]["evidence"] == "I re-checked I0 and it drifted."


def test_a_genuinely_identical_resubmission_is_still_a_no_op(app):
    """NEGATIVE CONTROL for the fix above going too far.

    Widening the comparison to the whole `{status, evidence}` pair must not turn a real
    no-op into a write — that would append a second confirmation to the evidence trail
    for a value nobody changed.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))
    _answer(client, exp_id, {"qc": {"status": "valid", "evidence": "first note"}})
    before = ws.load_experiment(exp_id).rev

    again = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "valid", "evidence": "first note"}},
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert again.status_code == 200, again.text
    assert again.json()["invalidation"]["changed"] is False
    assert ws.load_experiment(exp_id).rev == before
    assert len(ws.load_experiment(exp_id).draft["block_evidence"]["qc:status"]) == 1


def test_a_note_less_verdict_is_accepted_and_exports_which_is_why_the_UI_is_stricter(app):
    """The TRUE backend rule, pinned — because a comment claimed the opposite.

    The frontend requires a note for every verdict. An earlier comment justified that by
    saying the draft validator refuses a note-less verdict. It does not:
    `apply_answers` writes the `block_evidence["qc:status"]` confirmation
    unconditionally, so `_claim_covered` is satisfied and the record exports clean.

    Requiring a note in the UI is therefore a PRODUCT decision stricter than any backend
    rule. This test exists so that the honest version of the comment has something
    checkable behind it.
    """
    client = TestClient(app)
    exp_id = _new_record(client)
    _answer(client, exp_id, _harvested_answers(app))
    finished = _answer(client, exp_id, {"qc": {"status": "valid"}})

    assert finished.json()["pending"] == []
    assert finished.json()["status"] == "ready_to_export"
    assert _export(client, exp_id).json()["ok"] is True
    assert "evidence" not in ws.load_experiment(exp_id).draft["qc"]

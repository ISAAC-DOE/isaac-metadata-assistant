"""A run's science can be answered and corrected — and answering it on the record cannot.

THE DEFECT THIS CLOSES, measured over HTTP by an independent review
==================================================================
``series``, ``qc``, ``assets`` and ``descriptors_outputs`` are RUN-LEVEL blocks, so
``Experiment.resolved_run_draft`` reads them off the RUN. Once a run existed, an answer
written into ``exp.draft`` reached no exported record — and every surface said it had::

    qc = compromised + "Beam dropped during scan 3; spectrum unusable."
    POST /runs                                   -> 201
    POST /edit {"qc": {"status": "valid", …}}    -> 200 · changed_fields ["qc"]
                                                    status ready_to_export
                                                    artifact {"state": "current"}
    POST /export                                 -> ok: true
    ON DISK measurement.qc = {"status": "compromised",
                              "evidence": "Beam dropped during scan 3; spectrum unusable."}

Three things made that Critical rather than merely wrong:

1. the published record asserted a verdict its own sidecar then contradicted (the
   sidecar's ``block_evidence`` IS merged onto the run, so the "Correct the QC status?
   → valid" confirmation travelled while the verdict did not);
2. the application affirmatively said the artifact was ``current``; and
3. it was introduced by the run-adoption slice — before adoption the export simply
   refused, which is a loud failure rather than a quiet false claim.

THE FIX HAS TWO HALVES AND NEEDS BOTH
=====================================
Refusing on the record without providing a run-level route would leave a multi-run
record unfinishable, which is a different defect rather than a fix. So:

* ``POST /api/experiments/{id}/answers`` and ``/edit`` refuse a run-owned key with
  ``409 belongs_to_a_run``, naming the runs and the route that can take it; and
* ``POST /api/experiments/{id}/runs/{run_id}/answers`` and ``/edit`` write the run.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

DESCRIPTOR = {
    "name": "inflection_point_energy",
    "kind": "absolute",
    "source": "manual",
    "value": 9001.2,
    "unit": "eV",
    "uncertainty": {"sigma": 0.01, "unit": "eV", "basis": "reported"},
}
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


def _finished_record_with_a_run(client, qc):
    """A completed record plus one run — the run has ADOPTED everything."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "answers": {"series": SERIES, "descriptor": DESCRIPTOR, "qc": qc},
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    run_id = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "300 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    ).json()["run"]["id"]
    return exp_id, run_id


def _on_disk(exp_id):
    exp = ws.load_experiment(exp_id)
    return json.loads(exp.export_units()[0].record_path().read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The record refuses what belongs to a run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answers",
    [
        {"qc": {"status": "valid", "evidence": "Re-reduced."}},
        {"series": SERIES},
        {"descriptor": DESCRIPTOR},
    ],
)
def test_the_record_refuses_a_run_owned_answer_once_it_has_runs(client, answers):
    """REGRESSION TEST. The 200 that published nothing is now a 409 that writes nothing."""
    exp_id, run_id = _finished_record_with_a_run(
        client, {"status": "compromised", "evidence": "Beam dropped during scan 3."}
    )
    before = json.dumps(ws.load_experiment(exp_id).to_state(), sort_keys=True)

    refused = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={"confirmed_by_user": True, "answers": answers},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["error"] == "belongs_to_a_run"
    assert body["keys"] == sorted(answers), body
    assert body["runs"][0]["run_id"] == run_id
    assert "runs/{run_id}/answers" in body["answer_at"]
    assert "Nothing was written." in body["message"]

    assert json.dumps(ws.load_experiment(exp_id).to_state(), sort_keys=True) == before


def test_a_record_with_no_runs_still_takes_every_answer(client):
    """NEGATIVE CONTROL for over-refusal. The refusal is about runs, not about keys."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    applied = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "answers": {
                "series": SERIES,
                "descriptor": DESCRIPTOR,
                "qc": {"status": "valid", "evidence": "Stable."},
            },
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["pending"] == []


def test_an_edge_answer_IS_refused_because_it_does_not_reliably_reach_the_run(client):
    """THIS TEST IS INVERTED, and the version it replaces was vacuous as well as wrong.

    It read *"The exception, and it is a real one rather than an oversight. `edge` lives
    in `implicit`, which `resolved_run_draft` MERGES from the record onto every run."*
    The merge is CONDITIONAL —
    `_merge_implicit(..., inherit=not _diverges_from_experiment(resolutions))` — and a run
    that diverges at any experiment-level address, including one that re-records a
    byte-identical value, receives no inherited entry at all. An independent review
    measured `POST /edit {"edge": "L3"}` answering **200** with
    `changed_fields: ['edge']` while the run's composed `implicit` was `[]` and the
    exported sidecar carried none.

    It was also vacuous: its fixture was a created record whose `implicit` is `[]`, so
    `{"edge": "K"}` wrote nothing and the only assertion was `status_code == 200` — which
    a route that had silently done nothing would also satisfy.
    """
    exp_id, _ = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    refused = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"edge": "K"}, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "belongs_to_a_run"
    assert refused.json()["keys"] == ["edge"], refused.json()


def test_a_record_with_no_runs_still_takes_an_edge_answer(client):
    """NEGATIVE CONTROL for the refusal above: it is about runs, not about `edge`.

    A zero-run record IS its own record, so its `implicit` is the one the export reads
    and answering the edge there reaches it. Refusing unconditionally would remove a
    working capability.
    """
    exp_id = client.post("/api/experiments", json={"title": "No runs"}).json()["id"]
    answered = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"edge": "K"}, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert answered.status_code == 200, answered.text


# ---------------------------------------------------------------------------
# The run takes it, and it reaches the record
# ---------------------------------------------------------------------------


def test_correcting_a_verdict_on_the_run_reaches_the_exported_record(client):
    """THE END-TO-END PROOF. This is the exact sequence the review measured failing."""
    exp_id, run_id = _finished_record_with_a_run(
        client,
        {"status": "compromised", "evidence": "Beam dropped during scan 3; spectrum unusable."},
    )

    corrected = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "valid", "evidence": "Re-reduced; I0 stable."}},
        },
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["invalidation"]["changed_fields"] == ["qc"]

    client.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert _on_disk(exp_id)["measurement"]["qc"] == {
        "status": "valid",
        "evidence": "Re-reduced; I0 stable.",
    }


def test_a_second_run_can_be_answered_and_the_record_then_exports(client):
    """The other half: a multi-run record was previously unfinishable by any route."""
    exp_id, _ = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    second = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "400 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    ).json()["run"]["id"]

    listed = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert {q["id"] for q in listed} == {"series", "qc", "descriptor"}
    assert all(q["run_id"] == second for q in listed), listed

    answered = client.post(
        f"/api/experiments/{exp_id}/runs/{second}/answers",
        json={
            "answers": {
                "series": SERIES,
                "descriptor": DESCRIPTOR,
                "qc": {"status": "valid", "evidence": "Second run, I0 stable."},
            },
            "confirmed_by_user": True,
        },
        headers={"If-Match": _run_etag(client, exp_id, second)},
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["pending"] == [], answered.json()["pending"]

    exported = client.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert exported.json()["ok"] is True, exported.json()
    # One Run, one ISAAC record — two runs, two records.
    assert len(ws.load_experiment(exp_id).export_units()) == 2


def test_one_run_s_answer_does_not_touch_another_run(client):
    """NEGATIVE CONTROL for the whole point of per-run writes."""
    exp_id, first = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    second = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "400 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    ).json()["run"]["id"]

    client.post(
        f"/api/experiments/{exp_id}/runs/{second}/answers",
        json={
            "answers": {"qc": {"status": "failed", "evidence": "Sample degraded."}},
            "confirmed_by_user": True,
        },
        headers={"If-Match": _run_etag(client, exp_id, second)},
    )

    exp = ws.load_experiment(exp_id)
    assert exp.get_run(first).draft["qc"]["status"] == "valid"
    assert exp.get_run(second).draft["qc"]["status"] == "failed"


# ---------------------------------------------------------------------------
# The preconditions
# ---------------------------------------------------------------------------


def test_the_run_route_requires_the_RUN_s_etag_not_the_records(client):
    """A record token here would let a caller write a run it never read."""
    exp_id, run_id = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    wrong = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": {"qc": {"status": "failed", "evidence": "x"}}, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert wrong.status_code == 412, wrong.text
    assert ws.load_experiment(exp_id).get_run(run_id).draft["qc"]["status"] == "valid"


def test_a_missing_precondition_is_428_and_writes_nothing(client):
    exp_id, run_id = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    r = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": {"qc": {"status": "failed", "evidence": "x"}}, "confirmed_by_user": True},
    )
    assert r.status_code == 428, r.text
    assert ws.load_experiment(exp_id).get_run(run_id).draft["qc"]["status"] == "valid"


def test_an_unconfirmed_run_answer_is_refused(client):
    exp_id, run_id = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    r = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": {"qc": {"status": "failed", "evidence": "x"}}},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "confirmation_required"


def test_an_unusable_correction_on_a_run_is_the_same_typed_refusal_as_on_the_record(client):
    exp_id, run_id = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    r = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": {"status": "excellent"}}},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "invalid_field_value"
    assert r.json()["keys"] == ["qc"]
    assert ws.load_experiment(exp_id).get_run(run_id).draft["qc"]["status"] == "valid"


def test_an_unknown_run_is_a_404_rather_than_a_silent_no_op(client):
    exp_id, _ = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    r = client.post(
        f"/api/experiments/{exp_id}/runs/01NOTAREALRUNID0000000000/answers",
        json={"answers": {"qc": {"status": "failed", "evidence": "x"}}, "confirmed_by_user": True},
        headers={"If-Match": '"whatever.1"'},
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# THE MUTATIONS THAT SURVIVED THE WHOLE SUITE
# ---------------------------------------------------------------------------
#
# An independent review mutation-tested every shipped change and found four that no
# test noticed. Each is closed below, and each names the mutation it fails on — a
# regression test whose failure mode is unstated is one nobody can trust.


def test_the_refusal_is_enforced_on_ANSWERS_and_not_only_on_EDIT(client):
    """MUTATION M1: deleting the refusal from `POST /answers` failed nothing.

    The whole suite passed with the guard removed from `/answers` while it stayed on
    `/edit`, and the C1 defect returned verbatim — measured `200`,
    `changed_fields: ['series','descriptor','qc']`, the record's draft holding the
    verdict, and the run's composed draft carrying `qc: null`.

    `/answers` is the path a scientist reaches first, so this is the half that matters.
    """
    exp_id, run_id = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    before = json.dumps(ws.load_experiment(exp_id).to_state(), sort_keys=True)

    refused = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={
            "answers": {
                "series": SERIES,
                "descriptor": DESCRIPTOR,
                "qc": {"status": "failed", "evidence": "Should not land."},
            },
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "belongs_to_a_run"
    assert refused.json()["keys"] == ["descriptor", "qc", "series"], refused.json()
    # NOTHING WROTE — the whole document, not just the run.
    assert json.dumps(ws.load_experiment(exp_id).to_state(), sort_keys=True) == before
    assert ws.load_experiment(exp_id).get_run(run_id).draft["qc"]["status"] == "valid"


def test_every_producer_of_a_pending_list_agrees_on_a_record_with_runs(client):
    """MUTATION M5: reverting the record routes to draft-only pending failed nothing.

    That is the fix whose own commit message named the consequence — the screen renders
    "All blockers resolved" on an empty list, so a record whose detail said three
    questions remained told the scientist they were finished. It shipped with no
    coverage.

    **AND IT IS NOW UNREACHABLE THROUGH THOSE TWO ROUTES, which is worth stating rather
    than papering over with a test that proves something else.** Every key `/answers` and
    `/edit` accept — `series`, `qc`, `descriptor`, `descriptor_label`, an asset hash,
    `edge` — is run-owned, so on a record WITH runs both routes refuse everything with
    `409 belongs_to_a_run`, and on a record WITHOUT runs `exp.pending()` and
    `exp.draft["pending"]` are the same list. The `entries=` argument on those two is
    therefore correct and currently inert: it stops being inert the moment a
    record-level answer key exists again.

    What IS reachable, and is what this pins, is that the THREE producers of a pending
    list agree: the detail response's count, `GET /pending`, and a run write's response.
    Disagreement between any two of them is the defect, whichever one is wrong.
    """
    exp_id = client.post("/api/experiments", json={"title": "Three producers"}).json()["id"]
    run_id = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "300 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    ).json()["run"]["id"]

    detail_count = client.get(f"/api/experiments/{exp_id}").json()["pending_count"]
    listed = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    written = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": {"qc": {"status": "valid", "evidence": "I0 stable."}}, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert written.status_code == 200, written.text

    after_detail = client.get(f"/api/experiments/{exp_id}").json()["pending_count"]
    after_listed = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]

    assert detail_count == len(listed) == 3, (detail_count, len(listed))
    assert after_detail == len(after_listed) == len(written.json()["pending"]) == 2, (
        after_detail,
        len(after_listed),
        len(written.json()["pending"]),
    )
    # Every remaining question still belongs to the run, and says so.
    assert all(q["run_id"] == run_id for q in after_listed), after_listed


def test_a_run_write_reports_the_runs_new_version(client):
    """MUTATION M4: dropping `run_version` from the response failed nothing.

    A client that has just written a run needs its next `If-Match` without a second
    read; without this it would send the record's token and get a 412 it could not
    explain.
    """
    exp_id, run_id = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    before = _run_etag(client, exp_id, run_id)
    written = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "failed", "evidence": "Sample degraded."}},
        },
        headers={"If-Match": before},
    )
    assert written.status_code == 200, written.text
    assert "run_version" in written.json(), written.json().keys()
    assert f'"{written.json()["run_version"]}"' == _run_etag(client, exp_id, run_id)
    assert f'"{written.json()["run_version"]}"' != before


def test_descriptor_label_alone_is_refused_on_a_record_with_runs(client):
    """MUTATION M6: dropping `descriptor_label` from the run-owned key map failed nothing.

    It writes into `descriptors_outputs`, which is a run-level block, so on a record
    with runs it reaches nothing — exactly like `descriptor` itself.
    """
    exp_id, _ = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    refused = client.post(
        f"/api/experiments/{exp_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"descriptor": DESCRIPTOR, "descriptor_label": "relabelled"},
        },
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["keys"] == ["descriptor", "descriptor_label"], refused.json()


def test_a_run_answer_is_recorded_in_the_answer_log(client):
    """The reset disclosure counts `answer_log`, and the run path was not appending.

    `workspace._at_risk_summary` reports `confirmed_answers` from it, before a
    DESTRUCTIVE reset. Measured by an independent review: two confirmed run answers
    reported `confirmed_answers: 0`, so the disclosure under-counted a scientist's own
    work on the one screen where that matters most.
    """
    exp_id, run_id = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    before = len(ws.load_experiment(exp_id).answer_log)

    client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "failed", "evidence": "Sample degraded."}},
        },
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    log = ws.load_experiment(exp_id).answer_log
    assert len(log) == before + 1, log
    assert log[-1]["run_id"] == run_id, log[-1]
    assert "edited" in log[-1], log[-1]


def test_a_no_op_run_write_does_not_grow_the_answer_log(client):
    """NEGATIVE CONTROL for the append: the record path pops a speculative entry on a
    byte-stable no-op, and the run path must too — otherwise the reset disclosure
    over-counts, which is the same defect in the other direction."""
    exp_id, run_id = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
    before = len(ws.load_experiment(exp_id).answer_log)
    client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "valid", "evidence": "ok"}},
        },
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    # Unchanged, not empty: `_finished_record_with_a_run` answers on the RECORD before
    # the run exists, so the log already holds that entry. Asserting emptiness would
    # have measured the fixture rather than the no-op.
    assert len(ws.load_experiment(exp_id).answer_log) == before, (
        ws.load_experiment(exp_id).answer_log
    )


def test_answering_a_run_leaves_no_question_the_record_cannot_answer(client):
    """CRITICAL REGRESSION TEST. The measured sequence, assertion by assertion.

    An independent review measured this on the exact flow this feature exists to enable.
    The withholding rule had been made conditional on some run still CARRYING the kind,
    which un-withheld the record's copy the instant the run answered it::

        create -> POST /runs -> answer series+qc+descriptor ON THE RUN   (all 200)
        GET /experiments/{id}   -> pending_count 3 · export BLOCKED
        POST /export            -> 200 {"ok": true}    <- contradicts the workflow
        GET /pending            -> three entries, run_id null
        POST /answers | /edit   -> 409 belongs_to_a_run ("send them to the run")
        POST /runs/{id}/answers -> 200, changed nothing, the entries stay

    Three questions shown in both places and accepted in neither, and a record claiming
    export was blocked while export succeeded. The only escape was removing the run and
    re-answering on the record — discarding the run's science.
    """
    exp_id = client.post("/api/experiments", json={"title": "Answer on the run"}).json()["id"]
    run_id = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "300 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    ).json()["run"]["id"]

    answered = client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={
            "answers": {
                "series": SERIES,
                "descriptor": DESCRIPTOR,
                "qc": {"status": "valid", "evidence": "I0 stable."},
            },
            "confirmed_by_user": True,
        },
        headers={"If-Match": _run_etag(client, exp_id, run_id)},
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["pending"] == [], answered.json()["pending"]

    detail = client.get(f"/api/experiments/{exp_id}").json()
    assert detail["pending_count"] == 0, detail["pending_count"]
    assert client.get(f"/api/experiments/{exp_id}/pending").json()["pending"] == []

    steps = {s["id"]: s["state"] for s in detail["workflow"]["ordered_steps"]}
    exported = client.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert exported.json()["ok"] is True, exported.json()
    # THE CONJUNCTION IS THE PROPERTY: no combination of "nothing pending" and a blocked
    # export step may coexist with an export that succeeds.
    assert steps["export"] != "blocked", steps
    assert steps["complete_metadata"] == "completed", steps

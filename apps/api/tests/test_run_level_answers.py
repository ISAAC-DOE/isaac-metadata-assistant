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


def test_an_edge_answer_is_NOT_refused_because_it_does_reach_the_run(client):
    """The exception, and it is a real one rather than an oversight.

    `edge` lives in `implicit`, which `resolved_run_draft` MERGES from the record onto
    every run — so an edge answered on the record does reach the run's exported
    document. Refusing it would send a scientist to a route that cannot take it.
    """
    exp_id, _ = _finished_record_with_a_run(client, {"status": "valid", "evidence": "ok"})
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

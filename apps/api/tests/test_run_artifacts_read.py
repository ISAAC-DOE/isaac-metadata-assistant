"""A record with runs can have its exported files READ, and each run says if it changed.

THE DEFECTS, measured by an independent QA audit in a real browser on 2026-10-11 at
``1879baef``:

* **A-02** — a record with runs exports one official record + evidence sidecar PER RUN,
  and no read operation listed them. ``GET .../artifacts`` answered four nulls and a
  reason ending *"no read operation lists them yet"*, so the export screen offered no
  View or Download and, after a reload, not even the filenames. Every record Historical
  Import creates has runs.
* **A-06** — after an edit the screen said the artifact was out of date and told the
  scientist to "regenerate the record (or reset the workspace)". Neither exists for a
  scientist's record: an exported unit is never rewritten.

Every value is written out here; nothing is borrowed from a seed.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from isaac_api import dependencies
from isaac_api import routes

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
QC = {"status": "valid", "evidence": "I0 stable across all scans."}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _version(client, exp_id: str, run_id: str | None = None) -> str:
    if run_id is None:
        return client.get(f"/api/experiments/{exp_id}").json()["version"]
    return client.get(f"/api/experiments/{exp_id}/runs/{run_id}").json()["run"]["version"]


def _add_run(client, exp_id: str, label: str) -> str:
    added = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": label},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert added.status_code in (200, 201), added.text
    return added.json()["run"]["id"]


def _run_write(client, exp_id: str, run_id: str, op: str, answers: dict):
    return client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/{op}",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id, run_id)}"'},
    )


def _exported_fan_out(client, labels=("Run A", "Run B")) -> tuple[str, list[str]]:
    exp_id = client.post("/api/experiments", json={"title": "Fan-out"}).json()["id"]
    run_ids = [_add_run(client, exp_id, label) for label in labels]
    for run_id in run_ids:
        answered = _run_write(
            client, exp_id, run_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC}
        )
        assert answered.status_code == 200, answered.text
    exported = client.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True, exported.json()
    return exp_id, run_ids


def test_every_exported_run_is_listed_with_its_written_files(client):
    exp_id, run_ids = _exported_fan_out(client)
    body = client.get(f"/api/experiments/{exp_id}/run-artifacts").json()
    assert body["runs_total"] == 2 and body["total"] == 2 and body["returned"] == 2
    assert [row["run_id"] for row in body["artifacts"]] == run_ids
    assert [row["run_label"] for row in body["artifacts"]] == ["Run A", "Run B"]
    for row, run_id in zip(body["artifacts"], run_ids):
        assert row["record_id"] == run_id
        # Bare basenames, never a server path.
        assert row["record_filename"] == f"{run_id}.json"
        assert row["sidecar_filename"] == f"{run_id}.evidence.json"
        assert "/" not in row["record_filename"] and "/" not in row["sidecar_filename"]
        assert row["artifact"] == {"state": "current", "reason": None}
    # THE BYTES ON DISK, not a re-derivation.
    from isaac_api import workspace as ws

    exp = ws.load_experiment(exp_id)
    for row in body["artifacts"]:
        on_disk = json.loads((exp.records_dir / row["record_filename"]).read_text())
        assert row["record"] == on_disk
        sidecar = json.loads((exp.records_dir / row["sidecar_filename"]).read_text())
        assert row["sidecar"] == sidecar


def test_the_list_survives_a_reload_where_the_export_response_did_not(client):
    """The only other place these files were named was the export RESPONSE."""
    exp_id, _ = _exported_fan_out(client)
    artifacts = client.get(f"/api/experiments/{exp_id}/artifacts").json()
    assert artifacts["record"] is None  # still singular, still null for a fan-out
    assert artifacts["reason"] == routes.FAN_OUT_ARTIFACT_REASON
    assert "listed per run" in artifacts["reason"]
    assert "no read operation lists them yet" not in artifacts["reason"]
    # It is rendered to scientists verbatim, so it names no route.
    assert "/api/" not in artifacts["reason"]
    assert client.get(f"/api/experiments/{exp_id}/run-artifacts").json()["total"] == 2


def test_paging_is_bounded_and_reports_the_true_total(client):
    exp_id, run_ids = _exported_fan_out(client, labels=("R1", "R2", "R3"))
    page = client.get(f"/api/experiments/{exp_id}/run-artifacts?limit=2").json()
    assert page["total"] == 3 and page["returned"] == 2 and page["limit"] == 2
    rest = client.get(f"/api/experiments/{exp_id}/run-artifacts?limit=2&offset=2").json()
    assert [r["run_id"] for r in page["artifacts"] + rest["artifacts"]] == run_ids
    past = client.get(f"/api/experiments/{exp_id}/run-artifacts?offset=99").json()
    assert past["artifacts"] == [] and past["total"] == 3
    # REVIEW (e): the ceiling is NOT the run list's 200 — each row carries two whole
    # documents, one holding a spectrum that may be 8 MiB.
    assert routes.RUN_ARTIFACT_PAGE_MAX == 25 < routes.RUN_PAGE_MAX
    assert client.get(
        f"/api/experiments/{exp_id}/run-artifacts?limit={routes.RUN_ARTIFACT_PAGE_MAX}"
    ).status_code == 200
    assert client.get(
        f"/api/experiments/{exp_id}/run-artifacts?limit={routes.RUN_ARTIFACT_PAGE_MAX + 1}"
    ).status_code == 422
    # The default window, stated rather than "every run".
    assert client.get(f"/api/experiments/{exp_id}/run-artifacts").json()["limit"] == (
        routes.RUN_ARTIFACT_WINDOW
    )


def test_an_unexported_run_is_not_listed(client):
    exp_id, run_ids = _exported_fan_out(client)
    later = _add_run(client, exp_id, "Run C")
    body = client.get(f"/api/experiments/{exp_id}/run-artifacts").json()
    assert body["runs_total"] == 3
    assert body["total"] == 2
    assert later not in [r["run_id"] for r in body["artifacts"]]


def test_a_run_edited_after_export_is_named_stale_with_the_true_reason(client):
    """A-06: the row that changed says so, and the reason names no remedy."""
    exp_id, (run_a, run_b) = _exported_fan_out(client)
    new_series = copy.deepcopy(SERIES)
    new_series[0]["channels"][0]["values"] = [0.03, 0.86, 1.44]
    edited = _run_write(client, exp_id, run_a, "edit", {"series": new_series})
    assert edited.status_code == 200, edited.text
    body = client.get(f"/api/experiments/{exp_id}/run-artifacts").json()
    states = {r["run_id"]: r["artifact"] for r in body["artifacts"]}
    assert states[run_b] == {"state": "current", "reason": None}
    assert states[run_a]["state"] == "stale"
    assert states[run_a]["reason"] == dependencies.STALE_REASON
    # The file served is the one that was WRITTEN — unchanged by the edit.
    row_a = next(r for r in body["artifacts"] if r["run_id"] == run_a)
    assert row_a["record"]["measurement"]["series"][0]["channels"][0]["values"] == [
        0.02,
        0.85,
        1.45,
    ]


def test_the_stale_reason_offers_no_control_that_does_not_exist():
    reason = dependencies.STALE_REASON.lower()
    assert "regenerate" not in reason
    assert "reset" not in reason
    assert "fixed" in reason and "does not include" in reason


def test_a_record_without_runs_is_pointed_at_its_own_pair(client):
    exp_id = client.post("/api/experiments", json={"title": "No runs"}).json()["id"]
    body = client.get(f"/api/experiments/{exp_id}/run-artifacts").json()
    assert body["artifacts"] == [] and body["total"] == 0 and body["runs_total"] == 0
    assert "/artifacts" in body["reason"]


def test_an_unknown_record_is_404(client):
    """REVIEW (d): asserted on the BODY, because a bare 404 also passes where the route
    does not exist at all."""
    response = client.get("/api/experiments/01ZZZZZZZZZZZZZZZZZZZZZZZZ/run-artifacts")
    assert response.status_code == 404
    assert response.json()["error"] == "experiment_not_found"


def test_a_missing_file_is_a_null_payload_and_stale_never_an_error(client):
    from isaac_api import workspace as ws

    exp_id, (run_a, _) = _exported_fan_out(client)
    exp = ws.load_experiment(exp_id)
    (exp.records_dir / f"{run_a}.evidence.json").unlink()
    body = client.get(f"/api/experiments/{exp_id}/run-artifacts")
    assert body.status_code == 200
    row = next(r for r in body.json()["artifacts"] if r["run_id"] == run_a)
    assert row["sidecar"] is None
    assert row["record"] is not None
    assert row["artifact"] == {"state": "stale", "reason": dependencies.MISSING_REASON}

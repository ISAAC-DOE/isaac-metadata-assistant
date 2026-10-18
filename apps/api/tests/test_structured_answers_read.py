"""A confirmed structured answer can be SEEN after the visit that answered it (A-01/A-04).

THE DEFECT, measured by an independent QA audit in a real browser on 2026-10-11 at
``1879baef``. A reduced spectrum, QC verdict or descriptor was visible — and correctable
— only during the visit in which it was answered. After a reload Guided Completion said
"No open questions", Export Readiness said "Back to Complete →", and no screen showed
the confirmed value at all: no read operation served it. The correction operations
worked; nothing could reach them.

This file pins the read: every value comes back verbatim, its state is the state the
correction operation will act on, and nothing is filled in.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

SERIES = [
    {
        "series_id": "averaged_spectrum",
        "independent_variables": [{"name": "incident_energy", "unit": "eV", "values": [1, 2]}],
        "channels": [
            {"name": "absorption", "unit": "mu_normalized", "role": "primary_signal", "values": [0.1, 0.2]}
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


def _version(client, exp_id, run_id=None):
    if run_id is None:
        return client.get(f"/api/experiments/{exp_id}").json()["version"]
    return client.get(f"/api/experiments/{exp_id}/runs/{run_id}").json()["run"]["version"]


def _write(client, exp_id, op, answers, run_id=None, version=None):
    base = f"/api/experiments/{exp_id}" + (f"/runs/{run_id}" if run_id else "")
    token = version if version is not None else _version(client, exp_id, run_id)
    return client.post(
        f"{base}/{op}",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{token}"'},
    )


def _read(client, exp_id, query=""):
    response = client.get(f"/api/experiments/{exp_id}/structured-answers{query}")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_fresh_record_reports_three_open_questions_and_no_values(client):
    exp_id = client.post("/api/experiments", json={"title": "Fresh"}).json()["id"]
    body = _read(client, exp_id)
    assert body["level"] == "record" and body["total"] == 1
    (unit,) = body["units"]
    assert unit["run_id"] is None
    assert unit["edit_at"] == "POST /api/experiments/{experiment_id}/edit"
    for key in ("series", "qc", "descriptor"):
        assert unit["answers"][key] == {"state": "open", "value": None, "editable": False}


def test_confirmed_values_come_back_verbatim_after_the_answering_visit(client):
    exp_id = client.post("/api/experiments", json={"title": "Answered"}).json()["id"]
    assert _write(
        client, exp_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC}
    ).status_code == 200
    (unit,) = _read(client, exp_id)["units"]
    answers = unit["answers"]
    assert answers["series"] == {
        "state": "confirmed",
        "value": SERIES,
        "editable": True,
        "confirmation": "confirmed",
    }
    assert answers["qc"] == {
        "state": "confirmed",
        "value": QC,
        "editable": True,
        "confirmation": "confirmed",
    }
    desc = answers["descriptor"]
    assert desc["state"] == "confirmed" and desc["editable"] is True and desc["count"] == 1
    # The core's own confirmation is not part of the value a person supplied.
    assert desc["value"] == DESCRIPTOR
    assert "evidence" not in desc["value"]


def test_the_version_it_serves_is_the_one_the_correction_operation_takes(client):
    """`editable` is a promise the correction route keeps — pinned by keeping it."""
    exp_id = client.post("/api/experiments", json={"title": "Correctable"}).json()["id"]
    _write(client, exp_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    (unit,) = _read(client, exp_id)["units"]
    corrected = copy.deepcopy(SERIES)
    corrected[0]["channels"][0]["values"] = [0.3, 0.4]
    edited = _write(client, exp_id, "edit", {"series": corrected}, version=unit["version"])
    assert edited.status_code == 200, edited.text
    (after,) = _read(client, exp_id)["units"]
    assert after["answers"]["series"]["value"] == corrected
    assert after["version"] != unit["version"]


def test_a_record_with_runs_reports_each_run_and_pages_over_them(client):
    exp_id = client.post("/api/experiments", json={"title": "Runs"}).json()["id"]
    run_ids = []
    for label in ("Run A", "Run B", "Run C"):
        added = client.post(
            f"/api/experiments/{exp_id}/runs",
            json={"label": label},
            headers={"If-Match": f'"{_version(client, exp_id)}"'},
        )
        run_ids.append(added.json()["run"]["id"])
    _write(client, exp_id, "answers", {"qc": QC}, run_id=run_ids[1])
    body = _read(client, exp_id, "?limit=2")
    assert body["level"] == "run" and body["total"] == 3 and body["returned"] == 2
    assert [u["run_id"] for u in body["units"]] == run_ids[:2]
    assert body["units"][0]["edit_at"] == "POST /api/experiments/{experiment_id}/runs/{run_id}/edit"
    assert body["units"][1]["answers"]["qc"]["state"] == "confirmed"
    assert body["units"][0]["answers"]["qc"]["state"] == "open"
    only = _read(client, exp_id, f"?run_id={run_ids[1]}")
    assert [u["run_id"] for u in only["units"]] == [run_ids[1]] and only["total"] == 1
    assert only["units"][0]["version"] == _version(client, exp_id, run_ids[1])


def test_an_unknown_run_is_refused_not_answered_empty(client):
    exp_id = client.post("/api/experiments", json={"title": "No such run"}).json()["id"]
    response = client.get(f"/api/experiments/{exp_id}/structured-answers?run_id=nope")
    assert response.status_code == 404
    assert response.json()["error"] == "run_not_found"


def test_several_descriptors_are_shown_but_not_offered_for_correction(client):
    """The correction route rebuilds the block with ONE descriptor, so offering it here
    would delete the rest."""
    from isaac_api import workspace as ws

    exp_id = client.post("/api/experiments", json={"title": "Two descriptors"}).json()["id"]
    _write(client, exp_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    exp = ws.load_experiment(exp_id)
    second = dict(DESCRIPTOR, name="white_line_energy")
    exp.draft["descriptors_outputs"][0]["descriptors"].append(second)
    exp.save()
    desc = _read(client, exp_id)["units"][0]["answers"]["descriptor"]
    assert desc["state"] == "confirmed" and desc["count"] == 2
    assert desc["editable"] is False
    assert "delete the others" in desc["reason"]


# --- REVIEW I-2: a descriptor the form cannot carry back is NOT offered for editing ---


def _store_descriptor(exp_id, descriptor):
    from isaac_api import workspace as ws

    exp = ws.load_experiment(exp_id)
    exp.draft["descriptors_outputs"][0]["descriptors"] = [descriptor]
    exp.save()


def test_a_descriptor_with_fields_the_form_does_not_show_is_read_only_with_a_reason(client):
    """Demonstrated by review: Save turned `{at, definition, uncertainty.bounds/notes,
    value: "42"}` into `{…, value: 42}` — re-typing a value nobody changed and dropping
    four fields nobody touched. The schema admits all of them, and the API takes them."""
    exp_id = client.post("/api/experiments", json={"title": "Rich descriptor"}).json()["id"]
    _write(client, exp_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    rich = {
        "name": "inflection_point_energy",
        "kind": "absolute",
        "source": "manual",
        "value": "42",
        "definition": "first-derivative maximum",
        "at": {"temperature_K": 300},
        "uncertainty": {"sigma": None, "bounds": [41, 43], "notes": "from the fit"},
    }
    _store_descriptor(exp_id, rich)
    desc = _read(client, exp_id)["units"][0]["answers"]["descriptor"]
    assert desc["state"] == "confirmed" and desc["editable"] is False
    assert "`at`" in desc["reason"] and "`definition`" in desc["reason"]
    assert desc["value"] == rich  # shown whole, untouched


@pytest.mark.parametrize(
    "change, editable",
    [
        ({"value": "42"}, False),  # text the form's `typedValue` would turn into 42
        ({"value": "0x1A"}, False),  # JavaScript reads this as 26
        ({"value": " octahedral"}, False),  # the form trims it
        ({"value": "octahedral", "kind": "categorical"}, True),
        ({"value": 2**60}, False),  # beyond what a browser carries exactly
        ({"uncertainty": {"sigma": 0.01, "notes": "x"}}, False),
        ({"kind": "guess"}, False),  # not an option the form's select offers
        ({}, True),  # the ordinary descriptor the form itself writes
    ],
)
def test_editable_only_when_the_form_writes_the_descriptor_back_unchanged(client, change, editable):
    exp_id = client.post("/api/experiments", json={"title": "Round trip"}).json()["id"]
    _write(client, exp_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    _store_descriptor(exp_id, {**DESCRIPTOR, **change})
    desc = _read(client, exp_id)["units"][0]["answers"]["descriptor"]
    assert desc["editable"] is editable, desc
    assert ("reason" in desc) is (not editable)


def test_a_qc_note_the_verdict_control_would_trim_is_read_only(client):
    from isaac_api import workspace as ws

    exp_id = client.post("/api/experiments", json={"title": "QC note"}).json()["id"]
    _write(client, exp_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    exp = ws.load_experiment(exp_id)
    exp.draft["qc"]["evidence"] = "  padded note  "
    exp.save()
    qc = _read(client, exp_id)["units"][0]["answers"]["qc"]
    assert qc["editable"] is False and "note" in qc["reason"]


# --- REVIEW I-3: an exported unit says so, before anything is edited -------------


def test_a_unit_reports_whether_its_official_record_has_been_written(client):
    exp_id = client.post("/api/experiments", json={"title": "Exported"}).json()["id"]
    _write(client, exp_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    assert _read(client, exp_id)["units"][0]["exported"] is False
    exported = client.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert exported.json()["ok"] is True, exported.json()
    assert _read(client, exp_id)["units"][0]["exported"] is True


def test_the_page_ceiling_is_small_because_a_unit_carries_a_whole_spectrum(client):
    from isaac_api import routes

    exp_id = client.post("/api/experiments", json={"title": "Ceiling"}).json()["id"]
    assert routes.STRUCTURED_ANSWER_PAGE_MAX == 25
    assert client.get(f"/api/experiments/{exp_id}/structured-answers?limit=25").status_code == 200
    assert client.get(f"/api/experiments/{exp_id}/structured-answers?limit=26").status_code == 422


# --- RE-REVIEW: a MISSING field is something to fill in, never a reason to lock ------


SEED_4 = "01SYNTHXANESSEED0000000004"
SEED_1 = "01SYNTHXANESSEED0000000001"


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    """The worked-example session, where the canonical seeds live."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws-seeded"))
    from conftest import tutorial_client
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def test_seed_4s_descriptor_missing_its_uncertainty_is_editable_and_fixable(seeded):
    """The re-review's finding: the record that NEEDS this correction was the one locked.
    Seed 4's descriptor lacks `uncertainty`, export refuses it for exactly that, and the
    first version of the rule called it read-only because "the form would write one" —
    the A-01/A-04 dead loop again, for the records it exists for."""
    before = seeded.post(f"/api/experiments/{SEED_4}/validate").json()
    assert "'uncertainty' is a required property" in [e["message"] for e in before["errors"]]
    (unit,) = seeded.get(f"/api/experiments/{SEED_4}/structured-answers").json()["units"]
    desc = unit["answers"]["descriptor"]
    assert desc["editable"] is True and "reason" not in desc
    corrected = {**desc["value"], "uncertainty": {"sigma": 0.3, "unit": "eV"}}
    edited = seeded.post(
        f"/api/experiments/{SEED_4}/edit",
        json={"answers": {"descriptor": corrected, "descriptor_label": desc["label"]}, "confirmed_by_user": True},
        headers={"If-Match": f'"{unit["version"]}"'},
    )
    assert edited.status_code == 200, edited.text
    after = seeded.post(f"/api/experiments/{SEED_4}/validate").json()
    assert after["ok"] is True, after["errors"]


@pytest.mark.parametrize(
    "stored",
    [
        {"value": 8981.2, "unit": "eV", "uncertainty": {"sigma": 0.3}},  # no name/kind/source
        {"name": "inflection_point_energy", "kind": "absolute", "source": "manual", "value": 1.0},
        {"name": "inflection_point_energy", "kind": "absolute", "source": "manual", "value": 1.0, "uncertainty": {}},
    ],
)
def test_an_ABSENT_field_leaves_the_descriptor_editable(client, stored):
    exp_id = client.post("/api/experiments", json={"title": "Absent fields"}).json()["id"]
    _write(client, exp_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    _store_descriptor(exp_id, stored)
    desc = _read(client, exp_id)["units"][0]["answers"]["descriptor"]
    assert desc["editable"] is True, desc


# --- RE-REVIEW (minor): a stored value is labelled by what its evidence IS ----------


def test_a_value_read_from_a_source_is_not_called_confirmed(seeded):
    """Seeds 1 and 4 carry a QC verdict whose evidence is an EXTRACTION (a spreadsheet
    row), not a person's confirmation. Nothing may say "Confirmed by You" about it."""
    for seed in (SEED_1, SEED_4):
        (unit,) = seeded.get(f"/api/experiments/{seed}/structured-answers").json()["units"]
        assert unit["answers"]["qc"]["confirmation"] == "from_evidence", seed


def test_a_value_a_person_confirmed_is_called_confirmed(client):
    exp_id = client.post("/api/experiments", json={"title": "Confirmed"}).json()["id"]
    _write(client, exp_id, "answers", {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    answers = _read(client, exp_id)["units"][0]["answers"]
    assert {k: answers[k]["confirmation"] for k in answers} == {
        "series": "confirmed",
        "qc": "confirmed",
        "descriptor": "confirmed",
    }

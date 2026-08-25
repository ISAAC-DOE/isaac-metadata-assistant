"""THE END-TO-END CLAIM: a scientist can create a record and finish it. Nothing borrowed.

WHY THIS FILE EXISTS SEPARATELY FROM EVERY OTHER EXPORT TEST
============================================================
Every completion and export test in this repository starts from one of the five
canonical scenarios, whose drafts are built by ``build_draft`` from a fixture sheet.
Those drafts arrive carrying a QC verdict, a reduced spectrum and a descriptor — the
exact three values a real scientist has to supply — so the whole suite began past the
part of the product that did not work, and stayed green for months while a record
created through ``POST /api/experiments`` could not be completed at all.

So this file borrows NOTHING. Every value is written out here as a person would type it,
and the path is the public HTTP API from an empty workspace to a validated official
record. It is deliberately verbose for that reason: a helper that fetched a demo answer
would reintroduce exactly the blind spot it exists to close.

THE THREE DEFECTS IT WOULD HAVE CAUGHT, each measured on `main` before its fix:

  1. ``qc`` was not forwarded by ``_answers_to_apply_shape``, so the verdict could not be
     supplied by any request and ``pending`` stayed ``['qc']`` forever.
  2. Adding a Run gave it an empty draft, so the record reported ``pending 0`` and
     ``complete_metadata: completed`` while the export refused for a reason no surface
     named — and everything already answered stopped being part of any record.
  3. ``descriptors_outputs`` was stamped ``label: "completion_demo"`` and
     ``generated_by: {"agent": "isaac-complete-demo"}`` — a demo agent claiming
     authorship of a scientist's descriptor, in an exported official record.

WHAT THIS FILE DOES NOT CLAIM
=============================
It does not claim the product is complete. It claims exactly one thing: the path from
"create" to "a valid official ISAAC record on disk" is walkable through the public API
with values a person supplies. Submission needs a database and is refused honestly
without one; that is asserted here too, rather than left out because it is inconvenient.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

#: A descriptor exactly as the entry form emits it — `name` from the vocabulary the UI
#: suggests, `kind`/`source` from the schema's enums, a numeric value, and an
#: uncertainty. Written out rather than harvested; see the module docstring.
DESCRIPTOR = {
    "name": "inflection_point_energy",
    "kind": "absolute",
    "source": "manual",
    "value": 9001.2,
    "unit": "eV",
    "uncertainty": {"sigma": 0.01, "unit": "eV", "basis": "reported"},
}

#: A three-point spectrum. Small on purpose: this asserts that a series a person pasted
#: is stored and exported, not that the reduction pipeline works.
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

QC = {"status": "valid", "evidence": "I0 stable across all scans; no glitches."}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A plain client on an empty workspace — NO worked-example session."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


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


def _record_on_disk(exp_id: str) -> dict:
    exp = ws.load_experiment(exp_id)
    return json.loads(exp.export_units()[0].record_path().read_text(encoding="utf-8"))


def test_create_answer_export_with_values_a_person_supplied(client):
    """THE WALK. Create an empty record, answer its three questions, export it."""
    created = client.post("/api/experiments", json={"title": "Cu K-edge XANES, 300 K"})
    assert created.status_code == 201, created.text
    exp_id = created.json()["id"]

    opened = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert {q["id"] for q in opened} == {"series", "qc", "descriptor"}, opened

    filled = _answer(client, exp_id, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    assert filled.status_code == 200, filled.text
    assert filled.json()["pending"] == [], filled.json()["pending"]
    assert filled.json()["status"] == "ready_to_export", filled.json()["status"]

    exported = _export(client, exp_id)
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True, exported.json()


def test_the_exported_record_validates_against_the_official_schema(client):
    """Not "the app said ok" — the bytes on disk, against the vendored schema."""
    import pathlib

    from isaac_records.official import validate_official

    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    _answer(client, exp_id, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    assert _export(client, exp_id).json()["ok"] is True

    report = validate_official(_record_on_disk(exp_id), pathlib.Path.cwd())
    ok = report.ok if hasattr(report, "ok") else report["ok"]
    assert ok, report


def test_the_values_the_person_supplied_are_the_values_in_the_record(client):
    """A blocker clearing is not the same as a value arriving."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    _answer(client, exp_id, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    _export(client, exp_id)

    record = _record_on_disk(exp_id)
    assert record["measurement"]["series"][0]["series_id"] == "averaged_spectrum"
    assert record["measurement"]["qc"] == QC
    stored = record["descriptors"]["outputs"][0]["descriptors"][0]
    assert {k: stored[k] for k in DESCRIPTOR} == DESCRIPTOR


def test_the_record_does_not_claim_a_demo_agent_generated_the_descriptor(client):
    """REGRESSION TEST. The record used to assert authorship nobody had.

    Measured before the fix, on a record a person filled in by hand::

        "label": "completion_demo",
        "generated_by": {"agent": "isaac-complete-demo", "version": "0.1"}

    The schema says `generated_by` is "Tool/pipeline/person that generated these
    descriptors", so that is a false provenance claim in an exported official record.
    """
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    _answer(client, exp_id, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    _export(client, exp_id)

    output = _record_on_disk(exp_id)["descriptors"]["outputs"][0]
    assert "demo" not in json.dumps(output).lower(), output
    assert output["generated_by"]["agent"] == "isaac-metadata-assistant"
    assert "person" in output["generated_by"]["notes"]
    # `author` and `version` are OMITTED rather than invented — this application cannot
    # name the person (no trusted authentication boundary) and has no version to vouch
    # for. An absent key is the honest form of an unknown.
    assert "author" not in output["generated_by"], output["generated_by"]
    assert "version" not in output["generated_by"], output["generated_by"]


def test_the_same_walk_works_with_a_run(client):
    """The multi-Run architecture, end to end, from a record a person created."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    _answer(client, exp_id, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})

    added = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "300 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert added.status_code == 201, added.text

    detail = client.get(f"/api/experiments/{exp_id}").json()
    assert detail["pending_count"] == 0, detail["pending_count"]
    assert _export(client, exp_id).json()["ok"] is True

    # One Run, one ISAAC record — and the record id is the RUN's.
    exp = ws.load_experiment(exp_id)
    units = exp.export_units()
    assert len(units) == 1
    assert units[0].current_record_id() == exp.runs[0].id
    assert _record_on_disk(exp_id)["measurement"]["qc"] == QC


def test_a_second_run_reopens_the_record_and_says_which_run_needs_what(client):
    """The honest consequence: a second run has its own science and its own questions."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    _answer(client, exp_id, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    for label in ("300 K", "400 K"):
        client.post(
            f"/api/experiments/{exp_id}/runs",
            json={"label": label},
            headers={"If-Match": f'"{_version(client, exp_id)}"'},
        )

    listed = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert {q["id"] for q in listed} == {"series", "qc", "descriptor"}, listed
    # Every remaining question is addressed to the run that owns it, so a client can
    # take the scientist to the right place rather than to the record in general.
    second = ws.load_experiment(exp_id).runs[1]
    assert all(q["run_id"] == second.id for q in listed), listed
    assert all(q["run_label"] == "400 K" for q in listed), listed


def test_submitting_is_refused_honestly_and_says_which_gate_stopped_it(client):
    """Stated rather than omitted. TWO external dependencies, refused in order.

    This is the boundary between what this environment can prove and what it cannot, and
    the honest thing is to assert the refusals rather than to leave Submit out of the
    walk because it is inconvenient.

    THE FIRST GATE is identity (E1). A submission is a declaration by a named person, and
    a deployment with no trusted authentication boundary cannot establish who is calling
    — so it refuses rather than recording an unattributed declaration. That is the
    default on every deployment shipped today, including the hosted one.

    THE SECOND GATE is durable storage. It is only reachable once the first passes, so
    the test arms a verifier to see it. Migrations `0003`/`0004` create the tables it
    needs and only the infrastructure operator may apply them.

    Both messages name their own cause. Neither says "submitted".
    """
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    _answer(client, exp_id, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    _export(client, exp_id)

    unattributed = client.post(
        f"/api/experiments/{exp_id}/submit",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert unattributed.status_code == 409, unattributed.text
    body = unattributed.json()
    assert body["error"] == "human_actor_required"
    assert body["reason"] == "no_verifier_configured"
    assert "Nothing was written." in body["message"]


def test_the_storage_gate_is_reached_and_also_refuses_honestly(client, monkeypatch):
    """The second gate, reached by arming the identity one. Still not a false success."""
    from isaac_api import identity as identity_module

    monkeypatch.setenv(identity_module.EDGE_TRUST_VERIFIER_ENV, identity_module.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity_module.FIXTURE_ACTOR_SUBJECT_ENV, "sfaraday")

    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    _answer(client, exp_id, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC})
    _export(client, exp_id)

    submitted = client.post(
        f"/api/experiments/{exp_id}/submit",
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert submitted.status_code == 503, submitted.text
    body = submitted.json()
    assert body["reason"] == "no_durable_storage"
    assert "would be lost" in body["message"]


def test_nothing_in_this_file_borrows_a_fixture_value():
    """NEGATIVE CONTROL for this file's own premise.

    Its whole value is that it starts where a scientist starts. A future edit that
    reached for `load_demo_answers()` or a canonical seed id would quietly restore the
    blind spot that let three defects live in a suite of thousands of passing tests.
    """
    import ast
    import pathlib

    # PARSED, not grepped. The first version scanned the raw text and tripped on its own
    # docstring, which is the guard failing to distinguish talking about a thing from
    # doing it — the same mistake in miniature that this file exists to prevent.
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    # THIS FUNCTION IS EXCLUDED FROM ITS OWN SCAN. It has to name the things it forbids
    # in order to look for them, and a guard that fails on its own vocabulary is a guard
    # nobody can keep. Excluding exactly one node — by name, so a rename cannot silently
    # widen the hole — is narrower than stripping strings or comments everywhere.
    tree.body = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.FunctionDef)
            and node.name == "test_nothing_in_this_file_borrows_a_fixture_value"
        )
    ]
    borrowed = {"load_demo_answers", "tutorial_client", "tutorial_ws", "demo_answers"}
    seed_prefixes = ("01" + "SYNTH", "01" + "JQZ0")
    used: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in borrowed:
            used.append(node.id)
        if isinstance(node, ast.Attribute) and node.attr in borrowed:
            used.append(node.attr)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # A canonical seed id, used as a value rather than named as a symbol.
            if node.value.startswith(seed_prefixes):
                used.append(node.value)
    assert used == [], f"this file borrowed fixture machinery: {sorted(set(used))}"

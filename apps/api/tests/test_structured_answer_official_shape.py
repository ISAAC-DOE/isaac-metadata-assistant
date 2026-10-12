"""A structured answer is checked against the OFFICIAL schema's rule for its path (A-03).

THE DEFECT, measured by an independent QA audit in a real browser on 2026-10-11, at
``1879baef``: the series entry control said *"The shape is checked here and again on
the server"*, and ``[{"series_id": "x"}]`` was ACCEPTED by ``POST /answers`` — the
question closed and the record could then never export. The failure surfaced only at
export, as the validator's raw text.

Every value in this file is written out, as a person would type it, and nothing is
borrowed from a seed — for the reason ``test_scientist_can_finish_a_record.py`` gives.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from isaac_api import official_shape

GOOD_SERIES = [
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

GOOD_DESCRIPTOR = {
    "name": "inflection_point_energy",
    "kind": "absolute",
    "source": "manual",
    "value": 9001.2,
    "unit": "eV",
    "uncertainty": {"sigma": 0.01, "unit": "eV", "basis": "reported"},
}

QC = {"status": "valid", "evidence": "I0 stable across all scans."}

#: The audit's own value, verbatim.
AUDIT_SERIES = [{"series_id": "x"}]


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


def _post(client, exp_id: str, op: str, answers: dict, run_id: str | None = None):
    base = f"/api/experiments/{exp_id}" + (f"/runs/{run_id}" if run_id else "")
    return client.post(
        f"{base}/{op}",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id, run_id)}"'},
    )


def _created(client) -> str:
    created = client.post("/api/experiments", json={"title": "Shape check"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _with_run(client) -> tuple[str, str]:
    exp_id = _created(client)
    added = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "Run A"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert added.status_code in (200, 201), added.text
    return exp_id, added.json()["run"]["id"]


# --- the module ---------------------------------------------------------------


def test_the_audit_value_is_refused_by_the_schemas_own_rule():
    findings, more = official_shape.shape_findings("series", AUDIT_SERIES)
    assert more is False
    messages = {f["message"] for f in findings}
    # Verbatim jsonschema messages, at record paths the export gate would print.
    assert "'independent_variables' is a required property" in messages
    assert "'channels' is a required property" in messages
    assert {f["path"] for f in findings} == {"measurement.series.0"}
    assert all(f["key"] == "series" for f in findings)


def test_a_value_that_fits_produces_no_finding():
    assert official_shape.shape_findings("series", GOOD_SERIES) == ([], False)
    assert official_shape.shape_findings("descriptor", GOOD_DESCRIPTOR) == ([], False)


def test_a_nested_part_is_named_by_its_record_path():
    bad = copy.deepcopy(GOOD_SERIES)
    bad[0]["channels"][0]["role"] = "signal"
    findings, _ = official_shape.shape_findings("series", bad)
    assert [f["path"] for f in findings] == ["measurement.series.0.channels.0.role"]
    assert findings[0]["message"].startswith("'signal' is not one of")


def test_a_descriptor_missing_its_uncertainty_is_refused_at_its_record_path():
    bad = {k: v for k, v in GOOD_DESCRIPTOR.items() if k != "uncertainty"}
    findings, _ = official_shape.shape_findings("descriptor", bad)
    assert findings == [
        {
            "key": "descriptor",
            "path": "descriptors.outputs.0.descriptors.0",
            "message": "'uncertainty' is a required property",
        }
    ]


def test_the_rule_is_read_from_the_vendored_schema_not_a_copy(monkeypatch):
    """Negative control: point the rule at a node that does not exist and every check
    fails CLOSED with the stated reason — it never silently admits."""
    monkeypatch.setitem(
        official_shape.SHAPE_RULES, "series", (("properties", "nope"), "measurement.series")
    )
    findings, _ = official_shape.shape_findings("series", GOOD_SERIES)
    assert findings == [
        {
            "key": "series",
            "path": "measurement.series",
            "message": official_shape.SCHEMA_UNREADABLE_MESSAGE,
        }
    ]


# --- the four write paths -----------------------------------------------------


def test_answers_refuses_the_audit_value_and_the_question_stays_open(client):
    exp_id = _created(client)
    before = client.get(f"/api/experiments/{exp_id}").json()["rev"]
    refused = _post(client, exp_id, "answers", {"series": AUDIT_SERIES})
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "official_shape_mismatch"
    assert body["keys"] == ["series"]
    assert len(body["schema_errors"]) == 2
    assert body["schema_errors_more"] is False
    # No exact total is reported: counting every error was the unbounded work (C-1).
    assert "schema_errors_total" not in body
    assert {e["message"] for e in body["schema_errors"]} == {
        "'independent_variables' is a required property",
        "'channels' is a required property",
    }
    assert "not a verdict on the whole record" in body["message"]
    # Nothing was written: the question is still open and the revision did not move.
    pending = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert "series" in {q["id"] for q in pending}
    assert client.get(f"/api/experiments/{exp_id}").json()["rev"] == before


def test_answers_still_accepts_a_value_that_fits(client):
    exp_id = _created(client)
    ok = _post(
        client, exp_id, "answers", {"series": GOOD_SERIES, "descriptor": GOOD_DESCRIPTOR, "qc": QC}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["pending"] == []


def test_edit_refuses_an_invalid_correction_and_keeps_the_stored_value(client):
    exp_id = _created(client)
    assert _post(
        client, exp_id, "answers", {"series": GOOD_SERIES, "descriptor": GOOD_DESCRIPTOR, "qc": QC}
    ).status_code == 200
    bad = copy.deepcopy(GOOD_DESCRIPTOR)
    bad["kind"] = "guess"
    refused = _post(client, exp_id, "edit", {"descriptor": bad})
    assert refused.status_code == 422, refused.text
    body = refused.json()
    assert body["error"] == "official_shape_mismatch"
    assert body["schema_errors"][0]["path"] == "descriptors.outputs.0.descriptors.0.kind"
    assert "The stored value is unchanged." in body["message"]
    draft = client.get(f"/api/experiments/{exp_id}/structured-answers").json()
    stored = draft["units"][0]["answers"]["descriptor"]["value"]
    assert stored["kind"] == "absolute"


def test_the_run_level_paths_refuse_it_too(client):
    exp_id, run_id = _with_run(client)
    refused = _post(client, exp_id, "answers", {"series": AUDIT_SERIES}, run_id=run_id)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "official_shape_mismatch"
    assert refused.json()["run_id"] == run_id
    assert _post(client, exp_id, "answers", {"series": GOOD_SERIES}, run_id=run_id).status_code == 200
    refused_edit = _post(client, exp_id, "edit", {"series": AUDIT_SERIES}, run_id=run_id)
    assert refused_edit.status_code == 422, refused_edit.text
    assert refused_edit.json()["error"] == "official_shape_mismatch"


def test_a_wrong_typed_value_keeps_its_existing_refusal(client):
    """The coarse storability refusal still answers first — this never describes a
    value twice."""
    exp_id = _created(client)
    refused = _post(client, exp_id, "answers", {"series": "nope"})
    assert refused.status_code == 422
    assert refused.json()["error"] == "invalid_field_value"


def test_findings_are_bounded_and_say_that_there_are_more(client):
    exp_id = _created(client)
    many = [{"series_id": f"s{i}"} for i in range(40)]
    refused = _post(client, exp_id, "answers", {"series": many})
    body = refused.json()
    assert len(body["schema_errors"]) == official_shape.FINDINGS_LIMIT == 25
    assert body["schema_errors_more"] is True


# --- C-1: the check is LAZY, bounded in time and memory, and outside the lock ------


def test_the_validator_is_consumed_lazily_never_exhausted(monkeypatch):
    """REVIEW C-1. The first version collected and sorted EVERY error and capped only
    the response; 300,000 items ran for over 45 s at more than 1.37 GB. The bound must be
    on the WALK: at most one error past the reported limit may ever be pulled."""
    real = official_shape._sub_validator
    pulled = {"n": 0}

    class Counting:
        def __init__(self, inner):
            self.inner = inner

        def iter_errors(self, value):
            for err in self.inner.iter_errors(value):
                pulled["n"] += 1
                yield err

    monkeypatch.setattr(official_shape, "_sub_validator", lambda key: Counting(real(key)))
    findings, more = official_shape.shape_findings("series", [{}] * 10_000)
    assert len(findings) == official_shape.FINDINGS_LIMIT and more is True
    assert pulled["n"] == official_shape.FINDINGS_LIMIT + 1


def test_a_very_large_invalid_series_is_refused_quickly(client):
    """The measured attack, at HTTP: `[{}] * N` costs work proportional to where the
    first errors are, not to N. 100,000 items took ~5 s and ~1 GB on the eager version."""
    import time

    exp_id = _created(client)
    version = _version(client, exp_id)
    started = time.perf_counter()
    refused = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"series": [{}] * 100_000}, "confirmed_by_user": True},
        headers={"If-Match": f'"{version}"'},
    )
    elapsed = time.perf_counter() - started
    assert refused.status_code == 422, refused.text[:300]
    assert refused.json()["error"] == "official_shape_mismatch"
    assert elapsed < 2.0, f"refusal took {elapsed:.2f} s"


def test_the_check_runs_before_the_record_lock_is_taken(client, monkeypatch):
    """It depends only on the submitted value, so it must not hold the lock every other
    writer of the record waits on."""
    import isaac_api.routes as routes
    import isaac_api.workspace as ws

    held = {"now": False}
    seen: list[bool] = []
    real_lock = ws.record_lock
    real_findings = official_shape.findings_for_answers

    import contextlib

    @contextlib.contextmanager
    def tracking_lock(*args, **kwargs):
        with real_lock(*args, **kwargs):
            held["now"] = True
            try:
                yield
            finally:
                held["now"] = False

    def tracking_findings(*args, **kwargs):
        seen.append(held["now"])
        return real_findings(*args, **kwargs)

    monkeypatch.setattr(ws, "record_lock", tracking_lock)
    monkeypatch.setattr(official_shape, "findings_for_answers", tracking_findings)
    exp_id = _created(client)
    assert _post(client, exp_id, "answers", {"series": AUDIT_SERIES}).status_code == 422
    assert seen and not any(seen), seen
    assert routes.official_shape is official_shape


# --- MINOR (a): an `evidence` key is judged the way EXPORT judges it --------------


def test_a_descriptor_carrying_evidence_is_checked_as_export_will_see_it(client):
    """`complete.py` overwrites a descriptor's `evidence` and export strips evidence at
    every depth, so a value carrying one exports cleanly; it must not be refused here."""
    exp_id = _created(client)
    with_evidence = dict(GOOD_DESCRIPTOR, evidence=[{"source_type": "user_confirmation"}])
    series = copy.deepcopy(GOOD_SERIES)
    series[0]["channels"][0]["evidence"] = [{"source_type": "spreadsheet"}]
    ok = _post(
        client, exp_id, "answers", {"series": series, "descriptor": with_evidence, "qc": QC}
    )
    assert ok.status_code == 200, ok.text


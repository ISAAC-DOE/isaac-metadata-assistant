"""A CREATED record renders its metadata fields, and every row says where it is written.

THE DEFECT THIS FILE EXISTS TO CLOSE, measured over HTTP before the change::

    POST /api/experiments                      -> 201, pending_count 3
    GET  /api/experiments/{id}/draft           -> 200 {"groups": []}   <- ZERO rows
    GET  /api/experiments/{id}/pending         -> series, qc, descriptor  (never a field)

``serialize.draft_to_groups`` iterated ``draft["fields"]``, which a created record's
draft leaves empty, and ``FieldGroup`` is the only field-rendering component the frontend
has. The same call on a fixture-seeded record returned **26 rows in 4 groups**. So a
scientist who created a record could not see — and had no way to discover — that a record
holds a sample, a facility or a technique at all.

WHY THE EXISTING SUITE COULD NOT SEE IT, which is the same blind spot
``test_scientist_can_finish_a_record.py`` was written for: every canonical scenario is
built by ``build_draft`` from a fixture sheet that already carries all 26 values, so every
draft test in the suite began past the part that did not work. **Every test here creates
its record through the product's own route**, and one negative control below parses this
file to prove it.

THE OTHER HALF IS AS IMPORTANT AS THE SKELETON. ``CLAUDE.md`` §11 records a shipped defect
in which *"a panel told the scientist to enter a value on 25 fields, and 7 accept none"*.
Rendering 26 rows is only an improvement if each one is honest about whether a value can
be entered and where, so the writability facts are asserted here **against the routes
themselves** — every claim is checked by sending the write and reading the status, rather
than by re-stating the constant that produced it.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from isaac_api import routes as r
from isaac_api import workspace as ws


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A plain client on an empty workspace — NO worked-example session."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _created(client) -> str:
    created = client.post("/api/experiments", json={"title": "Cu K-edge XANES, 300 K"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _rows(client, exp_id: str) -> dict[str, dict]:
    body = client.get(f"/api/experiments/{exp_id}/draft").json()
    return {f["path"]: f for g in body["groups"] for f in g["fields"]}


def _version(client, exp_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}").json()["version"]


def _run_version(client, exp_id: str, run_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}/runs/{run_id}").json()["run"]["version"]


# --- the skeleton itself ------------------------------------------------------


def test_a_created_record_renders_its_fields_instead_of_nothing(client):
    """THE WALK. Create a record through the product's own route; read its draft."""
    exp_id = _created(client)
    body = client.get(f"/api/experiments/{exp_id}/draft").json()

    titles = [g["title"] for g in body["groups"]]
    counts = {g["title"]: len(g["fields"]) for g in body["groups"]}
    total = sum(counts.values())

    # The measured after-state, written out rather than derived from the constant, so
    # this reads as the observation it is. Before: 0 groups, 0 rows.
    assert titles == ["System & Instrument", "Timestamps", "Sample", "Environment & Context"]
    assert counts == {
        "System & Instrument": 13,
        "Timestamps": 3,
        "Sample": 7,
        "Environment & Context": 3,
    }
    assert total == 26


def test_the_skeleton_is_exactly_what_a_seeded_record_already_carries(client, tmp_path, monkeypatch):
    """A created record's rows and a seeded record's rows are the SAME 26 paths.

    This is the property that makes the change safe rather than merely additive: the
    skeleton adds nothing to a record that already holds every path, so every committed
    fixture record's response keeps the rows, the groups and the order it had.
    """
    from isaac_api.app import create_app

    created_paths = set(_rows(client, _created(client)))

    seeded = TestClient(create_app())
    opened = seeded.post("/api/tutorial/sessions")
    seeded.headers["X-Isaac-Tutorial-Session"] = opened.json()["session_id"]
    seed_id = opened.json()["record_ids"][0]
    seeded_rows = _rows(seeded, seed_id)

    assert created_paths == set(seeded_rows)
    assert len(created_paths) == 26
    # And every one of the seeded record's is a value it HOLDS, so none of its rows is a
    # skeleton row. Without this the equality above would also pass if the seeded record
    # had quietly started rendering skeletons of its own.
    assert all(row["present"] is True for row in seeded_rows.values())


def test_a_skeleton_row_claims_nothing_the_record_does_not_hold(client):
    exp_id = _created(client)
    for path, row in _rows(client, exp_id).items():
        assert row["present"] is False, path
        assert row["value"] is None, path
        assert row["status"] == "missing", path
        assert row["evidence_count"] == 0, path
        assert row["source_types"] == [], path


def test_reading_the_draft_writes_nothing(client):
    """A skeleton row exists in the RESPONSE only. Nothing is stored, nothing moves."""
    exp_id = _created(client)
    before = client.get(f"/api/experiments/{exp_id}").json()

    client.get(f"/api/experiments/{exp_id}/draft")
    client.get(f"/api/experiments/{exp_id}/draft")

    after = client.get(f"/api/experiments/{exp_id}").json()
    assert after["version"] == before["version"]
    assert after["rev"] == before["rev"]
    assert after["status"] == before["status"]
    assert after["pending_count"] == before["pending_count"]
    # And the stored document itself still holds no field.
    assert (ws.load_experiment(exp_id).draft.get("fields") or {}) == {}


def test_the_skeleton_does_not_become_a_blocking_question(client):
    """26 unfilled rows are not 26 new things a scientist owes.

    The record's blocking questions are its series, QC verdict and descriptors; a field
    row is not one, and a screen that turned the skeleton into 26 blockers would be
    reporting work nobody asked for.
    """
    exp_id = _created(client)
    pending = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert {p["id"] for p in pending} == {"series", "qc", "descriptor"}


# --- the capture facts, checked against the routes rather than the constants --


def _write_probes(client, exp_id: str, run_id: str, path: str, value):
    """Every write route this application has, at one path. Returns {name: status}."""
    envelope = {
        "value": value,
        "status": "verified",
        "evidence": [
            {
                "source_type": "user_confirmation",
                "locator": "typed by the scientist",
                "quote": "probe",
                "confidence": "high",
            }
        ],
    }
    answers = {"answers": {path: value}, "confirmed_by_user": True}
    return {
        "record_answers": client.post(
            f"/api/experiments/{exp_id}/answers",
            json=answers,
            headers={"If-Match": f'"{_version(client, exp_id)}"'},
        ).status_code,
        "record_edit": client.post(
            f"/api/experiments/{exp_id}/edit",
            json=answers,
            headers={"If-Match": f'"{_version(client, exp_id)}"'},
        ).status_code,
        "run_patch": client.patch(
            f"/api/experiments/{exp_id}/runs/{run_id}",
            json={"confirmed_by_user": True, "fields": {path: value}},
            headers={"If-Match": f'"{_run_version(client, exp_id, run_id)}"'},
        ).status_code,
        "run_answers": client.post(
            f"/api/experiments/{exp_id}/runs/{run_id}/answers",
            json=answers,
            headers={"If-Match": f'"{_run_version(client, exp_id, run_id)}"'},
        ).status_code,
        "run_edit": client.post(
            f"/api/experiments/{exp_id}/runs/{run_id}/edit",
            json=answers,
            headers={"If-Match": f'"{_run_version(client, exp_id, run_id)}"'},
        ).status_code,
        "run_override": client.post(
            f"/api/experiments/{exp_id}/runs/{run_id}/overrides",
            json={
                "confirmed_by_user": True,
                "address": ws.field_address(path),
                "payload": envelope,
            },
            headers={"If-Match": f'"{_run_version(client, exp_id, run_id)}"'},
        ).status_code,
    }


#: A value each path will actually accept, so a refusal measures the ROUTE and not the
#: value. Anything absent takes a plain string, which is what the untyped paths hold.
_PROBE_VALUES = {
    "system.domain": "experimental",
    "system.technique": "XAS",
    "context.environment": "ambient",
    "context.temperature_K": 300,
    "system.configuration.n_scans": 3,
    "sample.composition.CuO2_mass_fraction": 0.5,
    "sample.composition.sucrose_mass_fraction": 0.5,
    "sample.geometry.pellet_diameter_mm": 5,
    "timestamps.acquired_start_utc": "2026-01-01T00:00:00Z",
    "timestamps.acquired_end_utc": "2026-01-01T01:00:00Z",
    "timestamps.created_utc": "2026-01-01T00:00:00Z",
}


@pytest.mark.parametrize("path", sorted(r.CAPTURE_SURFACE_PATHS))
def test_each_served_capture_fact_is_what_the_routes_actually_do(client, path):
    """The three booleans on every row, checked by SENDING the write.

    This is the assertion that keeps the served answer honest. Re-stating
    ``RUN_WRITABLE_FIELD_PATHS`` here would prove only that one constant equals itself;
    what a scientist needs is that a row saying "you can enter this" belongs to a route
    that accepts it, and that a row offering nothing belongs to routes that all refuse.

    A FRESH RECORD PER PATH, because the probes mutate: an earlier path's accepted write
    changes what a later one's route says (an answered field is then ``already_answered``).
    """
    exp_id = _created(client)
    added = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "probe run"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert added.status_code == 201, added.text
    run_id = added.json()["run"]["id"]

    capture = _rows(client, exp_id)[path]["capture"]
    observed = _write_probes(client, exp_id, run_id, path, _PROBE_VALUES.get(path, "probe-value"))

    assert capture["record_writable"] is (observed["record_answers"] == 200), (path, observed)
    assert capture["run_field_writable"] is (observed["run_patch"] == 200), (path, observed)
    assert capture["run_overridable"] is (observed["run_override"] == 200), (path, observed)

    if not any(
        (capture["record_writable"], capture["run_field_writable"], capture["run_overridable"])
    ):
        # THE ROW THAT OFFERS NOTHING MUST BE REFUSED BY EVERYTHING. This is the half
        # that stops the surface pointing a scientist at a locked door.
        assert set(observed.values()) == {422}, (path, observed)


def test_the_four_buckets_are_the_measured_ones(client):
    """The whole table at once, so a path silently changing bucket is visible.

    Stated as counts AND as the paths themselves: a count alone would survive two paths
    swapping buckets.
    """
    rows = _rows(client, _created(client))
    record = {p for p, row in rows.items() if row["capture"]["record_writable"]}
    run_field = {p for p, row in rows.items() if row["capture"]["run_field_writable"]}
    overridable = {p for p, row in rows.items() if row["capture"]["run_overridable"]}
    nowhere = {
        p
        for p, row in rows.items()
        if not any(
            (
                row["capture"]["record_writable"],
                row["capture"]["run_field_writable"],
                row["capture"]["run_overridable"],
            )
        )
    }

    assert record == {"system.domain", "system.technique"}
    assert run_field == {
        "context.environment",
        "context.temperature_K",
        "context.thermodynamics.atmosphere",
        "timestamps.acquired_start_utc",
        "timestamps.acquired_end_utc",
    }
    assert len(overridable) == 13
    assert nowhere == {
        "timestamps.created_utc",
        *(p for p in rows if p.startswith("system.configuration.")),
    }
    assert len(nowhere) == 7


def test_the_seven_unwritable_rows_do_not_all_get_the_same_reason(client):
    """``workspace.field_level`` warns against exactly this conflation.

    All seven are ``unclassified``, but for two different reasons, and that docstring says
    so in as many words: ``timestamps.created_utc`` *"is the one member of this list that
    does NOT need a scientific answer — stated here because grouping it with the six made
    it look as though it did"*. ``open_namespace`` is what lets a surface say the six's
    scope is an open scientific question without saying it of the export stamp.
    """
    rows = _rows(client, _created(client))
    assert rows["timestamps.created_utc"]["capture"]["level"] == "unclassified"
    assert rows["timestamps.created_utc"]["capture"]["open_namespace"] is None
    for path, row in rows.items():
        if path.startswith("system.configuration."):
            assert row["capture"]["level"] == "unclassified", path
            assert row["capture"]["open_namespace"] == "system.configuration", path


def test_choices_are_the_vendored_schema_s_own_enum(client):
    """Read from the schema, never transcribed — so a refresh moves the control."""
    import json

    from isaac_records.official import schema_path

    schema = json.loads(
        schema_path(pathlib.Path(__file__).resolve().parents[3]).read_text(encoding="utf-8")
    )
    system = schema["properties"]["system"]["properties"]

    rows = _rows(client, _created(client))
    assert rows["system.domain"]["capture"]["choices"] == system["domain"]["enum"]
    assert rows["system.technique"]["capture"]["choices"] == system["technique"]["enum"]
    # Served ONLY where a record-level route can take one: a list beside a path no
    # record-level operation accepts would be a set of options with nowhere to send them.
    for path, row in rows.items():
        if not row["capture"]["record_writable"]:
            assert row["capture"]["choices"] is None, path


def test_answering_an_enum_field_turns_its_row_from_skeleton_into_a_value(client):
    """End to end: the control's own write, read back through the same response."""
    exp_id = _created(client)
    assert _rows(client, exp_id)["system.domain"]["present"] is False

    applied = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"system.domain": "experimental"}, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert applied.status_code == 200, applied.text

    row = _rows(client, exp_id)["system.domain"]
    assert row["present"] is True
    assert row["value"] == "experimental"
    assert row["status"] == "verified"
    assert row["source_types"] == ["user_confirmation"]
    # The row keeps its capture facts, so the screen can offer the correction path.
    assert row["capture"]["record_writable"] is True
    # And the row count is unchanged: a filled path replaces its own skeleton rather
    # than joining it.
    assert len(_rows(client, exp_id)) == 26


def test_a_malformed_persisted_field_does_not_gain_an_invented_clean_row(client):
    """A wrong-typed stored envelope is skipped, and no skeleton is substituted for it.

    ``draft_to_groups`` has always skipped a non-dict envelope. Manufacturing a tidy
    `missing` row in its place would hide a malformed document behind a row that reads
    as normal — the opposite of CLAUDE.md §11's rule that a persisted malformed value is
    read rather than dressed up.
    """
    exp_id = _created(client)
    exp = ws.load_experiment(exp_id)
    exp.draft.setdefault("fields", {})["sample.material.name"] = "not-an-envelope"
    exp.save()

    rows = _rows(client, exp_id)
    assert "sample.material.name" not in rows
    assert len(rows) == 25


def test_this_file_creates_its_records_and_never_borrows_a_seed(client):
    """NEGATIVE CONTROL, and the reason this file exists at all.

    ``test_scientist_can_finish_a_record.py`` carries the same guard for the same reason:
    the defect above survived 5,000+ tests because every one of them started from a
    fixture that already held the values. A later edit reaching for a canonical id would
    silently restore that blind spot, and every assertion here would keep passing.
    """
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    # SPLIT LITERALS, so this control does not match its own needles — which is exactly
    # how its first version failed, twice. It scans CODE FORMS (a call, an id) rather
    # than bare names, because the prose above legitimately NAMES the seed helper while
    # explaining why nothing here uses it, and a control that forbade the word would
    # forbid the explanation.
    for needle in ("SEED_READY" + "_ID", "01SYNTHXANES" + "SEED", "build_" + "draft("):
        assert needle not in source, needle
    assert ("import build_" + "draft") not in source
    # EXACTLY ONE worked-example session is opened in this file, and it is a DELIBERATE
    # comparison against the seeded response. Counted rather than forbidden, so a second
    # one — a test quietly reaching for a ready-made record — names itself. The needle is
    # split for the same reason as the ones above: this line would otherwise be one of
    # the occurrences it counts.
    assert source.count("tutorial/" + "sessions") == 1

"""AFTER EVERY WRITE, ASK THE HISTORY SURFACE WHAT HAPPENED — AND CHECK ITS ANSWER.

THE GAP THIS CLOSES, MEASURED RATHER THAN ASSUMED
=================================================
``test_a_submitted_records_artifacts_are_never_rewritten.py`` drives 19 write
routes at a submitted record and, after each one, re-reads the artifacts and two
of the five history tables. It never reads ``GET .../revisions``,
``.../revisions/{n}`` or ``.../revisions/{n}/diff`` at any point. So nothing in
this repository pins what the history SURFACES *say* about the asset, transcript,
note, override, rename or conflict writes that sweep performs.
``test_revision_history.py`` reads all three surfaces, but only ever after a
single field edit written directly onto ``exp.draft``.

The consequence is specific: the diff's ``content_signature_matches`` is the
field a scientist relies on to know whether what they just did needs
re-submitting, and it had been exercised against exactly ONE kind of write.

THE ORACLE IS NOT AN ECHO, AND THAT IS THE DESIGN DECISION IN THIS FILE
======================================================================
``GET .../revisions/{n}/diff`` computes ``content_signature_matches`` as
``revision["content_signature"] == submissions.content_signature(exp.id,
exp.export_units())``. A test that recomputed the same expression would be
comparing the route against itself and would pass against any consistent lie.

So the oracle is a DIFFERENT ROUTE: ``POST .../submit``. Submit's
``already_submitted`` branch is decided by the same equality, reached through an
entirely separate code path (the store's preflight over the recorded rows). The
property asserted for every write below is therefore a CROSS-SURFACE one, and it
is the one a scientist actually experiences:

    the diff says the signature still matches  <=>  submitting again is refused
    the diff says it does not                  <=>  submitting again is accepted

A surface that reported "nothing moved" about a record the submit path considers
new — or the reverse — would be telling a scientist their work is already on
record when it is not. Nothing could catch that from one side alone.

WHAT IS *NOT* CLAIMED. That every write SHOULD move the signature. Several
deliberately do not, and the table below asserts only that the surface agrees
with the submit path about which did. Which writes belong in which group is
measured by the run, not declared here — except for the two non-vacuity floors,
which exist so a change that froze every write into one group could not pass.

THE RECORD IS BUILT THROUGH ``POST /api/experiments`` AND THE ANSWER ROUTES, with
values written out below; see :func:`test_nothing_in_this_file_borrows_a_fixture_value`.

Nothing here opens a network connection, reads real data, or touches a database.
No production code is modified by anything in this file.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

import isaac_api.identity as identity
import isaac_api.revision_history as rhist
import isaac_api.submission_store as sstore
import isaac_api.workspace as ws
from isaac_records.models import user_confirmation

from submission_fake import FakeSubmissionConnection, fake_reader, fake_store

ACTOR = "grace.hopper"

DESCRIPTOR = {
    "name": "white_line_intensity",
    "kind": "absolute",
    "source": "manual",
    "value": 1.42,
    "unit": "mu_normalized",
    "uncertainty": {"sigma": 0.02, "unit": "mu_normalized", "basis": "reported"},
}
SERIES = [
    {
        "series_id": "averaged_spectrum",
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [8975, 8985, 8995]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [0.03, 0.91, 1.42],
            }
        ],
    }
]
QC = {"status": "valid", "evidence": "Reference foil scanned before and after; no drift."}

#: The run-level address written twice, with different values, when a case needs a
#: real conflict for ``POST /conflicts/resolve`` to decide. ``timestamps.*`` rather
#: than ``context.*`` because the official schema declares
#: ``context.required == ["environment", "temperature_K"]``, so writing one
#: ``context`` field alone makes the record un-submittable — and the fixture
#: unbuildable.
CONFLICT_ADDRESS = "timestamps.acquired_start_utc"
CONFLICT_VALUES = ("2026-01-01T00:00:00Z", "2026-02-02T00:00:00Z")

#: The scope the diff declares for its ``changes`` list. Named so the honesty
#: assertion below can quote it rather than repeat a literal in five places.
CHANGES_SCOPE = "draft_field_values_only"

HISTORY_TABLES = ("revisions", "run_revisions", "changes", "submissions", "submission_runs")


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def db():
    return FakeSubmissionConnection()


@pytest.fixture()
def client(tmp_path, monkeypatch, db):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    monkeypatch.setattr(rhist, "reader", lambda env=None: fake_reader(db))
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


# --- the walk, written out ----------------------------------------------------


def _etag(client, eid: str) -> str:
    response = client.get(f"/api/experiments/{eid}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _run_etag(client, eid: str, run_id: str) -> str:
    response = client.get(f"/api/experiments/{eid}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _answers() -> dict:
    return {
        "series": copy.deepcopy(SERIES),
        "descriptor": copy.deepcopy(DESCRIPTOR),
        "qc": copy.deepcopy(QC),
    }


def _built(client, title: str) -> tuple[str, str]:
    """A one-run record, answered through the public routes. Returns ``(id, run_id)``."""
    created = client.post("/api/experiments", json={"title": title})
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    filled = client.post(
        f"/api/experiments/{eid}/answers",
        json={"answers": _answers(), "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert filled.status_code == 200, filled.text
    added = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "300 K", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert added.status_code == 201, added.text
    for question in client.get(f"/api/experiments/{eid}/pending").json()["pending"]:
        run_id = question["run_id"]
        answered = client.post(
            f"/api/experiments/{eid}/runs/{run_id}/answers",
            json={"answers": _answers(), "confirmed_by_user": True},
            headers={"If-Match": _run_etag(client, eid, run_id)},
        )
        assert answered.status_code == 200, answered.text
    assert client.get(f"/api/experiments/{eid}/pending").json()["pending"] == []
    return eid, ws.load_experiment(eid).sorted_runs()[0].id


def _submit(client, eid: str):
    return client.post(f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)})


def _artifacts(eid: str) -> dict[str, str]:
    exp = ws.load_experiment(eid)
    if exp is None or not exp.records_dir.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(exp.records_dir.iterdir())
        if path.is_file()
    }


def _capture_note(client, eid: str) -> str:
    captured = client.post(
        f"/api/experiments/{eid}/transcript",
        json={"text": "the sample was copper oxide", "finalized": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert captured.status_code == 200, captured.text
    notes = client.get(f"/api/experiments/{eid}/notes").json()["notes"]
    assert notes, "the transcript capture produced no note"
    return notes[0]["id"]


def _write_conflicting(client, eid: str, run_id: str, value: str) -> None:
    written = client.patch(
        f"/api/experiments/{eid}/runs/{run_id}",
        json={"confirmed_by_user": True, "fields": {CONFLICT_ADDRESS: value}},
        headers={"If-Match": _run_etag(client, eid, run_id)},
    )
    assert written.status_code == 200, written.text


# --- the write table ----------------------------------------------------------
#
# Each entry is ``(name, before_submit, after_submit, write)``. Every write is aimed
# at a record of its OWN so no case can mask another — the existing sweep runs all of
# its attempts against one record, which is right for an immutability sweep and wrong
# for a per-write representation check.
#
# THE ``after_submit`` SLOT EXISTS FOR EXACTLY ONE CASE AND THE REASON IS A MEASURED
# ONE. ``POST /runs/{run}/overrides`` at ``field:sample.material.name`` leaves the
# record UN-EXPORTABLE — the official schema's ``sample`` object requires siblings the
# override does not supply — so an override applied BEFORE the fixture submit would
# make the fixture unbuildable. ``overrides/clear`` therefore has to add its override
# after the submission and clear it as the write under test.


def _cases():
    def rename(client, eid, run_id):
        return client.patch(
            f"/api/experiments/{eid}",
            json={"title": "Cu K-edge XANES (renamed after submission)"},
            headers={"If-Match": _etag(client, eid)},
        )

    def asset_unassociated(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/assets",
            json={
                "confirmed_by_user": True,
                "asset_id": "loose_asset",
                "content_role": "reduction_product",
                "uri": "synthetic://example/loose/CuO.xdi",
                "sha256": "a" * 64,
            },
            headers={"If-Match": _etag(client, eid)},
        )

    def asset_associated(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/assets",
            json={
                "confirmed_by_user": True,
                "asset_id": "run_asset",
                "content_role": "reduction_product",
                "uri": "synthetic://example/run/CuO.xdi",
                "sha256": "b" * 64,
                "run_ids": [run_id],
            },
            headers={"If-Match": _etag(client, eid)},
        )

    def asset_patch(client, eid, run_id):
        return client.patch(
            f"/api/experiments/{eid}/assets/run_asset",
            json={"confirmed_by_user": True, "sha256": "c" * 64},
            headers={"If-Match": _etag(client, eid)},
        )

    def asset_remove(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/assets/run_asset/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        )

    def add_run_asset(client, eid, run_id):
        assert asset_associated(client, eid, run_id).status_code == 201

    def transcript(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/transcript",
            json={"text": "the sample was copper oxide", "finalized": True},
            headers={"If-Match": _etag(client, eid)},
        )

    def note_map(client, eid, run_id):
        note_id = _capture_note(client, eid)
        return client.post(
            f"/api/experiments/{eid}/notes/{note_id}/review",
            json={
                "confirmed_by_user": True,
                "action": "map",
                "field_path": "sample.material.name",
            },
            headers={"If-Match": _etag(client, eid)},
        )

    def note_keep(client, eid, run_id):
        note_id = _capture_note(client, eid)
        return client.post(
            f"/api/experiments/{eid}/notes/{note_id}/review",
            json={"confirmed_by_user": True, "action": "keep"},
            headers={"If-Match": _etag(client, eid)},
        )

    def note_dismiss(client, eid, run_id):
        note_id = _capture_note(client, eid)
        return client.post(
            f"/api/experiments/{eid}/notes/{note_id}/review",
            json={"confirmed_by_user": True, "action": "dismiss"},
            headers={"If-Match": _etag(client, eid)},
        )

    def override(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/runs/{run_id}/overrides",
            json={
                "confirmed_by_user": True,
                "address": "field:sample.material.name",
                "payload": {
                    "value": "CuO",
                    "status": "verified",
                    "evidence": [
                        user_confirmation("What material?", "CuO", "2026-01-01T00:00:00Z")
                    ],
                },
            },
            headers={"If-Match": _run_etag(client, eid, run_id)},
        )

    def override_clear(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/runs/{run_id}/overrides/clear",
            json={"confirmed_by_user": True, "address": "field:sample.material.name"},
            headers={"If-Match": _run_etag(client, eid, run_id)},
        )

    def add_override(client, eid, run_id):
        assert override(client, eid, run_id).status_code < 300

    def run_field(client, eid, run_id):
        return client.patch(
            f"/api/experiments/{eid}/runs/{run_id}",
            json={
                "confirmed_by_user": True,
                "fields": {"timestamps.acquired_end_utc": "2026-03-03T00:00:00Z"},
            },
            headers={"If-Match": _run_etag(client, eid, run_id)},
        )

    def run_edit_qc(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/runs/{run_id}/edit",
            json={
                "confirmed_by_user": True,
                "answers": {"qc": {"status": "compromised", "note": "reconsidered"}},
            },
            headers={"If-Match": _run_etag(client, eid, run_id)},
        )

    def run_answers_qc(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/runs/{run_id}/answers",
            json={"confirmed_by_user": True, "answers": {"qc": copy.deepcopy(QC)}},
            headers={"If-Match": _run_etag(client, eid, run_id)},
        )

    def add_run(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/runs",
            json={"label": "400 K", "confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        )

    def make_conflict(client, eid, run_id):
        _write_conflicting(client, eid, run_id, CONFLICT_VALUES[0])
        _write_conflicting(client, eid, run_id, CONFLICT_VALUES[1])

    def resolve_conflict(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/conflicts/resolve",
            json={
                "confirmed_by_user": True,
                "run_id": run_id,
                "address": CONFLICT_ADDRESS,
                "outcome": "resolved",
                "chosen_value": CONFLICT_VALUES[1],
                "chosen_from": "candidate",
            },
            headers={"If-Match": _etag(client, eid)},
        )

    def csv_preview(client, eid, run_id):
        return client.post(
            f"/api/experiments/{eid}/ingestion/csv/preview",
            content=b"field,value\nsample.material.name,PREVIEW-ONLY\n",
            headers={"Content-Type": "text/csv", "If-Match": _etag(client, eid)},
        )

    def validate(client, eid, run_id):
        return client.post(f"/api/experiments/{eid}/validate")

    def audit(client, eid, run_id):
        return client.post(f"/api/experiments/{eid}/audit")

    def warnings(client, eid, run_id):
        return client.post(f"/api/experiments/{eid}/warnings")

    def check(client, eid, run_id):
        return client.post(f"/api/experiments/{eid}/runs/{run_id}/check")

    return [
        ("PATCH /experiments/{id} (rename)", None, None, rename),
        ("POST /assets (associated with no run)", None, None, asset_unassociated),
        ("POST /assets (associated with the run)", None, None, asset_associated),
        ("PATCH /assets/{id}", add_run_asset, None, asset_patch),
        ("POST /assets/{id}/remove", add_run_asset, None, asset_remove),
        ("POST /transcript", None, None, transcript),
        ("POST /notes/{id}/review action=map", None, None, note_map),
        ("POST /notes/{id}/review action=keep", None, None, note_keep),
        ("POST /notes/{id}/review action=dismiss", None, None, note_dismiss),
        ("POST /runs/{run}/overrides", None, None, override),
        ("POST /runs/{run}/overrides/clear", None, add_override, override_clear),
        ("PATCH /runs/{run}", None, None, run_field),
        ("POST /runs/{run}/edit", None, None, run_edit_qc),
        ("POST /runs/{run}/answers", None, None, run_answers_qc),
        ("POST /runs (add)", None, None, add_run),
        ("POST /conflicts/resolve", make_conflict, None, resolve_conflict),
        ("POST /ingestion/csv/preview", None, None, csv_preview),
        ("POST /validate", None, None, validate),
        ("POST /audit", None, None, audit),
        ("POST /warnings", None, None, warnings),
        ("POST /runs/{run}/check", None, None, check),
    ]


# ==========================================================================
# 1. THE CROSS-SURFACE PROPERTY
# ==========================================================================


def test_the_diff_predicts_the_submit_outcome_for_every_write_path(client, db):
    """**THE HEADLINE PROPERTY.** For 21 writes: what the diff says about the
    signature is what the submit path decides about the record.

    Every case gets a FRESH record, submitted once, so no write can mask another
    and the diff is always read against revision 1. After the write:

      * the write is asserted ACCEPTED, so a payload that silently stopped
        reaching its handler is loud rather than passing as "did not move
        anything" — the failure mode that would hollow this test out;
      * the published artifacts are re-hashed and must be unchanged, because none
        of these routes republishes an immutable record;
      * the diff is read, and then the submit path is asked independently.

    ``changes_scope`` is asserted on every case because ``changes == []`` is only
    honest beside a signature that says whether anything moved — the narrowing has
    to be visible on the same body, not implied by silence.
    """
    moved: list[str] = []
    unmoved: list[str] = []
    for name, before, after, write in _cases():
        eid, run_id = _built(client, name)
        if before is not None:
            before(client, eid, run_id)
        first = _submit(client, eid)
        assert first.status_code == 200, f"{name}: fixture submit failed: {first.text[:300]}"
        if after is not None:
            after(client, eid, run_id)
        artifacts = _artifacts(eid)

        response = write(client, eid, run_id)
        assert response is not None and response.status_code < 300, (
            f"{name} did not reach its write path — it answered "
            f"{None if response is None else response.status_code}: "
            f"{'' if response is None else response.text[:300]}. A case that stops "
            f"being accepted must be re-declared, not left to read as 'moved nothing'."
        )
        assert _artifacts(eid) == artifacts, (
            f"{name} changed a published artifact of a submitted record"
        )

        diff = client.get(f"/api/experiments/{eid}/revisions/1/diff")
        assert diff.status_code == 200, (name, diff.text[:300])
        body = diff.json()
        assert body["comparable"] is True, (name, body)
        assert body["changes_scope"] == CHANGES_SCOPE, (name, body["changes_scope"])
        says_unchanged = body["content_signature_matches"]

        # THE INDEPENDENT SIDE. A different route, a different code path, the same
        # question. THREE outcomes are reachable and each says something different:
        #
        #   200                        -> the submit path considers this new content
        #   409 already_submitted      -> it considers the content unchanged
        #   409 submission_blocked     -> the record is no longer exportable
        #
        # The third is not a shrug. It was MEASURED on `POST /runs/{run}/overrides`,
        # whose write leaves the record un-exportable, and it still constrains the
        # diff: a record that submitted cleanly a moment ago and is now blocked has
        # necessarily changed, because the blockers are computed over the same unit
        # drafts the signature is computed over. So it must NOT read as unchanged.
        again = _submit(client, eid)
        assert again.status_code in (200, 409), (name, again.status_code, again.text[:300])
        error = again.json().get("error") if again.status_code == 409 else None
        assert error in (None, "already_submitted", "submission_blocked"), (name, again.json())
        submit_says_unchanged = error == "already_submitted"
        if error == "submission_blocked":
            assert says_unchanged is False, (
                f"{name}: the record can no longer be exported, so its unit drafts "
                f"moved — yet the diff reports content_signature_matches=True"
            )

        assert says_unchanged == submit_says_unchanged, (
            f"{name}: the diff says content_signature_matches={says_unchanged!r} "
            f"while POST /submit answered {again.status_code} ({error!r}). One of "
            f"the two surfaces is telling a scientist the wrong thing about whether "
            f"their work is on record."
        )
        (unmoved if says_unchanged else moved).append(name)

    # NON-VACUITY FLOORS. Without these, a change that froze every write into one
    # group would satisfy the equality above trivially.
    assert len(moved) >= 4, f"too few writes moved the signature; the walk is degenerate: {moved}"
    assert len(unmoved) >= 4, f"too few writes left it alone: {unmoved}"
    assert len(moved) + len(unmoved) == 21, (moved, unmoved)
    # The four body-less POSTs are documented read-only, so they belong in `unmoved`
    # by construction rather than by measurement — asserted so a route that quietly
    # acquired a write is caught here as well as by the read-only test elsewhere.
    for read_only in ("POST /validate", "POST /audit", "POST /warnings", "POST /runs/{run}/check"):
        assert read_only in unmoved, (read_only, moved)


# ==========================================================================
# 2. WHAT THE SURFACE SAYS ABOUT AN ASSET, AND WHY THE ANSWER DIFFERS BY ONE FIELD
# ==========================================================================


def test_an_asset_reaches_the_history_only_when_it_is_associated_with_a_run(client, db):
    """MEASURED, AND WORTH A TEST BECAUSE THE TWO CALLS DIFFER BY ONE KEY.

    ``POST /assets`` answers ``201`` either way. On a record WITH runs, an asset
    created without ``run_ids`` is associated with no unit, so it reaches no
    export unit's draft, moves no signature, and the history honestly reports that
    nothing changed — a resubmission is refused ``already_submitted``. The same
    call carrying ``run_ids`` moves the signature and the resubmission is accepted.

    Both are correct: association is the API's own model and the response carries
    ``associated_run_ids`` so a caller can see which happened. It is pinned because
    a reader who assumed "an asset always changes the record" would file the first
    case as a defect, and because a change that silently associated every asset
    with every run would move science into records nobody attached it to.

    The ZERO-RUN control is the half that makes the sentence precise: with no runs
    there is nothing to associate to, the record is its own unit, and the asset
    moves the signature without any ``run_ids`` at all.
    """
    eid, run_id = _built(client, "asset association")
    assert _submit(client, eid).status_code == 200

    loose = client.post(
        f"/api/experiments/{eid}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "loose_asset",
            "content_role": "reduction_product",
            "uri": "synthetic://example/loose/CuO.xdi",
            "sha256": "a" * 64,
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert loose.status_code == 201, loose.text
    assert loose.json()["asset"]["asset_id"] == "loose_asset"
    diff = client.get(f"/api/experiments/{eid}/revisions/1/diff").json()
    assert diff["content_signature_matches"] is True, diff
    assert diff["changes"] == [], diff["changes"]
    refused = _submit(client, eid)
    assert refused.status_code == 409 and refused.json()["error"] == "already_submitted"
    assert "loose_asset" not in json.dumps(
        [unit.draft.get("assets") for unit in ws.load_experiment(eid).export_units()]
    ), "an asset associated with no run must not reach a run's composed draft"

    attached = client.post(
        f"/api/experiments/{eid}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "run_asset",
            "content_role": "reduction_product",
            "uri": "synthetic://example/run/CuO.xdi",
            "sha256": "b" * 64,
            "run_ids": [run_id],
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert attached.status_code == 201, attached.text
    moved = client.get(f"/api/experiments/{eid}/revisions/1/diff").json()
    assert moved["content_signature_matches"] is False, (
        "an asset attached to a run is part of that unit's science and must move "
        "the signature"
    )
    assert moved["changes"] == [], (
        "an asset is a block, not a draft FIELD value, so it produces no change "
        "row — which is honest only because `content_signature_matches` is False "
        "beside it"
    )
    accepted = _submit(client, eid)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["revision_no"] == 2

    # THE ZERO-RUN CONTROL, on its own record.
    created = client.post("/api/experiments", json={"title": "zero-run asset"})
    assert created.status_code == 201, created.text
    solo = created.json()["id"]
    filled = client.post(
        f"/api/experiments/{solo}/answers",
        json={"answers": _answers(), "confirmed_by_user": True},
        headers={"If-Match": _etag(client, solo)},
    )
    assert filled.status_code == 200, filled.text
    assert _submit(client, solo).status_code == 200
    solo_asset = client.post(
        f"/api/experiments/{solo}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "solo_asset",
            "content_role": "reduction_product",
            "uri": "synthetic://example/solo/CuO.xdi",
            "sha256": "d" * 64,
        },
        headers={"If-Match": _etag(client, solo)},
    )
    assert solo_asset.status_code == 201, solo_asset.text
    solo_diff = client.get(f"/api/experiments/{solo}/revisions/1/diff").json()
    assert solo_diff["content_signature_matches"] is False, solo_diff
    assert _submit(client, solo).status_code == 200


# ==========================================================================
# 3. THE DIFF NAMES NOBODY IT CANNOT VOUCH FOR
# ==========================================================================


def test_the_diff_surface_invents_no_actor_and_upgrades_no_basis(client, db):
    """``test_revision_history.py`` checks this on the LISTING. The DIFF carries an
    actor too, through ``_revision_summary``, and nothing checked it.

    ``attribution.uploaded_by`` requires ``trust_basis ==
    verified_edge_assertion`` and no verifier in this build mints one, so the
    strongest thing any surface may say about this row is ``test_fixture``. Both
    directions are driven: an attributed row must not be upgraded, and a row with
    no subject must read as nobody rather than as a placeholder.
    """
    eid, run_id = _built(client, "diff actor")
    assert _submit(client, eid).status_code == 200

    diff = client.get(f"/api/experiments/{eid}/revisions/1/diff")
    assert diff.status_code == 200, diff.text
    revision = diff.json()["revision"]
    assert revision["actor"] == {
        "subject": ACTOR,
        "trust_basis": "test_fixture",
        "attributed": True,
    }, revision["actor"]
    assert revision["submission"]["actor"]["trust_basis"] == "test_fixture"
    assert "verified_edge_assertion" not in json.dumps(diff.json()), diff.text[:400]

    # THE OTHER DIRECTION. A row the database would accept with no subject at all —
    # planted, because the submit route refuses to record one in this deployment.
    db.revisions.append(
        {
            "revision_id": "01ADVERSARIALDIFFUNATTRIB01",
            "experiment_id": eid,
            "revision_no": 2,
            "experiment_rev": ws.load_experiment(eid).rev,
            "generation": ws.load_experiment(eid).generation,
            "state": db.revisions[0]["state"],
            "content_signature": "0" * 64,
            "reason": sstore.REASON_SUBMISSION,
            "subject": None,
            "trust_basis": "unattributed",
            "created_utc": "2026-01-01T00:00:00+00:00",
        }
    )
    unattributed = client.get(f"/api/experiments/{eid}/revisions/2/diff")
    assert unattributed.status_code == 200, unattributed.text
    actor = unattributed.json()["revision"]["actor"]
    assert actor == {"subject": None, "trust_basis": "unattributed", "attributed": False}, actor
    rendered = json.dumps(unattributed.json()).lower()
    for invented in ("system", "unknown user", "anonymous", "isaac user", "n/a"):
        assert invented not in rendered, (invented, rendered[:400])


# ==========================================================================
# 4. NEGATIVE CONTROL FOR THIS FILE'S OWN PREMISE
# ==========================================================================


def test_nothing_in_this_file_borrows_a_fixture_value():
    """Same guard, same reason, as in the two sibling adversarial files."""
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    tree.body = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.FunctionDef)
            and node.name == "test_nothing_in_this_file_borrows_a_fixture_value"
        )
    ]
    borrowed = {
        "_full_draft",
        "_review_draft",
        "_split_full_draft",
        "load_demo_answers",
        "demo_answers",
        "tutorial_client",
        "tutorial_ws",
        "create_experiment",
    }
    seed_prefixes = ("01" + "SYNTH", "01" + "JQZ0")
    used: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in borrowed:
            used.append(node.id)
        if isinstance(node, ast.Attribute) and node.attr in borrowed:
            used.append(node.attr)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith(seed_prefixes):
                used.append(node.value)
    assert used == [], f"this file borrowed fixture machinery: {sorted(set(used))}"

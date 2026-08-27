"""AN ADVERSARIAL PASS OVER ``POST /api/experiments/{id}/submit`` — on a record NOBODY SEEDED.

WHY THIS FILE EXISTS BESIDE ``test_submission.py``
==================================================
``test_submission.py`` is the submit lifecycle's own suite and it is thorough. Every
record in it is built by ``ws.create_experiment(..., ws._full_draft())`` or by
``_split_full_draft()`` — the fixture sheet. That sheet already carries ``series``,
``qc``, ``descriptor``, ``sample.material.name``, ``sample.sample_form`` and the rest,
so every submission test in this repository *begins past the part a scientist has to
do*. That is the exact blind spot ``test_scientist_can_finish_a_record.py`` was written
to close for the EXPORT path, and it had never been closed for SUBMIT.

So this file borrows nothing. Every record is created through ``POST /api/experiments``
and completed through the answer routes with values written out here as a person would
type them. :func:`test_nothing_in_this_file_borrows_a_fixture_value` is the negative
control for that premise, in the same shape and for the same reason as the one in
``test_scientist_can_finish_a_record.py``.

WHAT IT MEASURED THAT THE SEEDED SUITE COULD NOT
================================================
Two things, both consequences of starting from an EMPTY record rather than a full one:

* **The refusal a person actually meets first.** A freshly created, unanswered record's
  ``submission_blocked`` body carries ``errors: [{"path": "$", "message": "'descriptors'
  is a required property"}]`` — an OFFICIAL-SCHEMA verdict, from a validator that DID
  run. A seeded record never produces that body because it is never in that state.
* **The second refusal a person meets, and it comes from a DIFFERENT gate wearing the
  same clothes.** A descriptor name with a trailing newline is refused by ISAAC's own
  anchored-pattern exactness gate, which returns BEFORE ``validate_official`` is called
  (``official_report is None``). The submit refusal renders both under one flat
  ``failing_units[].errors`` key with no discriminator. See
  :func:`test_a_draft_only_finding_and_an_official_verdict_are_not_labelled` — that test
  pins the CURRENT behaviour and says plainly what it is, rather than asserting a fix
  that has not been made.

HOW THE HAPPY PATH IS REACHABLE, and it is the seam ``test_submission.py`` established:
``ISAAC_EDGE_TRUST_VERIFIER=test_fixture`` for an attributable actor, and
``submission_store.store`` / ``revision_history.reader`` pointed at ONE in-process
connection double (``submission_fake.py``) so the write path's real transaction
machinery runs and the read path reads the rows the write path wrote. ``PGHOST`` stays
unset; experiments themselves use the filesystem repository. Nothing here opens a
network connection, reads real data, or touches a database.

NOTHING IN THIS FILE MODIFIES PRODUCTION CODE. Two tests monkeypatch a route-module
symbol to INJECT A FAULT (a raising ``_write_record``); that is a fault injection in the
test process and is reverted by ``monkeypatch``.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import pathlib
import threading

import pytest
from fastapi.testclient import TestClient

import isaac_api.identity as identity
import isaac_api.revision_history as rhist
import isaac_api.routes as routes
import isaac_api.submission_store as sstore
import isaac_api.submissions as submissions
import isaac_api.workspace as ws

from submission_fake import FakeSubmissionConnection, fake_reader, fake_store

ACTOR = "ada.lovelace"

#: A descriptor exactly as a person supplies it. Written out; see the module docstring.
DESCRIPTOR = {
    "name": "inflection_point_energy",
    "kind": "absolute",
    "source": "manual",
    "value": 9001.2,
    "unit": "eV",
    "uncertainty": {"sigma": 0.01, "unit": "eV", "basis": "reported"},
}

#: A three-point spectrum. Small on purpose.
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

#: The two run-level field paths a person can write on a record they created that leave
#: the record STILL SUBMITTABLE. MEASURED over all five members of
#: ``routes.RUN_WRITABLE_FIELD_PATHS``, not chosen: the three ``context.*`` paths each
#: require a sibling the same request must supply (``context`` declares
#: ``required: ["environment", "temperature_K"]``), so writing one alone makes the
#: record un-exportable until the other arrives. ``timestamps.*`` has no such coupling.
#: :func:`test_which_run_level_writes_leave_a_record_submittable` re-derives this rather
#: than trusting the comment.
_SAFE_RUN_FIELD = "timestamps.acquired_start_utc"
_SAFE_RUN_VALUE = "2026-01-01T00:00:00Z"


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def armed(tmp_path, monkeypatch):
    """A deployment that can attribute a person and has nothing seeded in it."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return ws


@pytest.fixture()
def db():
    return FakeSubmissionConnection()


@pytest.fixture()
def client(armed, db, monkeypatch):
    """One connection double behind BOTH the write path and the read path."""
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


def _create(client, title: str) -> str:
    created = client.post("/api/experiments", json={"title": title})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _answer(client, eid: str, answers: dict, run_id: str | None = None):
    if run_id is None:
        return client.post(
            f"/api/experiments/{eid}/answers",
            json={"answers": answers, "confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        )
    return client.post(
        f"/api/experiments/{eid}/runs/{run_id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": _run_etag(client, eid, run_id)},
    )


def _built(client, title: str, *, runs: tuple[str, ...] = (), descriptor=None) -> str:
    """Create a record and answer every question it has, with values typed out here.

    A record with runs is answered at BOTH levels: the record's own three answers land
    first and the FIRST run adopts them; every later run has its own three questions and
    they are answered through that run's own route. Nothing is harvested.
    """
    eid = _create(client, title)
    filled = _answer(
        client,
        eid,
        {
            "series": copy.deepcopy(SERIES),
            "descriptor": copy.deepcopy(descriptor if descriptor is not None else DESCRIPTOR),
            "qc": copy.deepcopy(QC),
        },
    )
    assert filled.status_code == 200, filled.text
    for label in runs:
        added = client.post(
            f"/api/experiments/{eid}/runs",
            json={"label": label, "confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        )
        assert added.status_code == 201, added.text
    for question in client.get(f"/api/experiments/{eid}/pending").json()["pending"]:
        run_id = question.get("run_id")
        assert run_id is not None, question
        answered = _answer(
            client,
            eid,
            {
                "series": copy.deepcopy(SERIES),
                "descriptor": copy.deepcopy(DESCRIPTOR),
                "qc": copy.deepcopy(QC),
            },
            run_id=run_id,
        )
        assert answered.status_code == 200, answered.text
    assert client.get(f"/api/experiments/{eid}/pending").json()["pending"] == []
    return eid


def _submit(client, eid: str, *, if_match: str | None = None, key: str | None = None):
    headers = {"If-Match": if_match if if_match is not None else _etag(client, eid)}
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(f"/api/experiments/{eid}/submit", headers=headers)


def _artifacts(eid: str) -> dict[str, str]:
    """``filename -> sha256`` for every file in this record's records directory."""
    exp = ws.load_experiment(eid)
    if exp is None or not exp.records_dir.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(exp.records_dir.iterdir())
        if path.is_file()
    }


def _row_counts(db) -> tuple[int, ...]:
    return (
        len(db.revisions),
        len(db.run_revisions),
        len(db.changes),
        len(db.submissions),
        len(db.submission_runs),
    )


# ==========================================================================
# 1. THE EXACT CURRENT REVISION IS WHAT GETS SUBMITTED
# ==========================================================================


def test_the_revision_captures_the_record_as_it_is_after_publication(client, db):
    """Not a stale composition and not a racing re-read — the row is checked, not the code.

    THE ORDER IS THE POINT AND IT IS EASY TO GET BACKWARDS. Materialisation writes the
    official records and then SAVES the state, which advances ``rev``. If the revision
    snapshot were composed before that save it would record a record that says it was
    never exported, while naming the records it exported — so the assertion here is
    against the record's rev AFTER the call, read back from disk, not against the rev
    the handler started from.
    """
    eid = _built(client, "Cu K-edge XANES, 300 K")
    before = ws.load_experiment(eid).rev

    submitted = _submit(client, eid)
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()

    after = ws.load_experiment(eid)
    row = [r for r in db.revisions if r["experiment_id"] == eid]
    assert len(row) == 1, row
    assert row[0]["experiment_rev"] == after.rev, (
        "the revision must name the record's rev as it is once the submission is "
        f"recorded; it named {row[0]['experiment_rev']} and the record is at {after.rev}"
    )
    assert after.rev > before, "materialisation must have advanced the record's rev"
    assert row[0]["generation"] == after.generation
    assert row[0]["reason"] == sstore.REASON_SUBMISSION
    assert body["revision_no"] == 1


def test_the_stored_signature_is_the_one_a_fresh_read_recomputes(client, db):
    """The digest is checked against a re-derivation from disk, not against itself.

    A submission whose recorded ``content_signature`` did not match what the record now
    holds would make ``lifecycle.state: submitted`` a lie on the very next read, and the
    response echoing its own input could never catch it.
    """
    eid = _built(client, "signature", runs=("300 K", "400 K"))
    submitted = _submit(client, eid)
    assert submitted.status_code == 200, submitted.text

    reread = ws.load_experiment(eid)
    recomputed = submissions.content_signature(reread.id, reread.export_units())
    assert submitted.json()["content_signature"] == recomputed
    assert db.revisions[-1]["content_signature"] == recomputed
    assert db.submissions[-1]["content_signature"] == recomputed


def test_the_stored_snapshot_is_the_document_the_record_holds(client, db):
    """The revision's ``state`` is the record's own state, not a summary of it.

    Asserted against three values a PERSON supplied — if the snapshot were composed from
    anything but the live document, at least one of them would be missing.
    """
    eid = _built(client, "snapshot")
    assert _submit(client, eid).status_code == 200
    stored = json.loads(db.revisions[-1]["state"])
    rendered = json.dumps(stored)
    assert "averaged_spectrum" in rendered
    assert "inflection_point_energy" in rendered
    assert "I0 stable across all scans" in rendered
    assert stored["id"] == eid
    assert stored["rev"] == ws.load_experiment(eid).rev


# ==========================================================================
# 2. ONE RUN -> ONE OFFICIAL ISAAC RECORD, AS ONE COHERENT SUBMISSION
# ==========================================================================


def test_two_runs_publish_two_records_under_one_submission(client, db):
    """The whole-experiment claim: N runs, N records, ONE submission row, N unit rows."""
    eid = _built(client, "fan out", runs=("300 K", "400 K"))
    run_ids = [run.id for run in ws.load_experiment(eid).sorted_runs()]

    submitted = _submit(client, eid)
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()

    assert body["published_record_count"] == 2
    assert body["unit_count"] == 2
    assert {entry["record_id"] for entry in body["records"]} == set(run_ids), body["records"]
    assert {entry["run_id"] for entry in body["records"]} == set(run_ids)
    # ONE submission, N unit rows — the coherent-whole property.
    assert len(db.submissions) == 1
    assert len(db.revisions) == 1
    assert len(db.run_revisions) == 2
    assert {row["record_id"] for row in db.submission_runs} == set(run_ids)
    assert {row["submission_id"] for row in db.submission_runs} == {
        db.submissions[0]["submission_id"]
    }
    # And on disk: one record + one sidecar per run, and nothing else.
    assert set(_artifacts(eid)) == {
        f"{run_id}{suffix}" for run_id in run_ids for suffix in (".json", ".evidence.json")
    }


def test_each_published_record_carries_that_runs_own_science(client, db):
    """``record_id == run_id`` is not enough — the BYTES must be that run's.

    Both runs here are answered with the same spectrum, so the discriminating value is
    the QC note, which is made distinct per run.
    """
    eid = _create(client, "per-run science")
    assert _answer(
        client, eid, {"series": SERIES, "descriptor": DESCRIPTOR, "qc": dict(QC, evidence="run one")}
    ).status_code == 200
    for label in ("300 K", "400 K"):
        assert client.post(
            f"/api/experiments/{eid}/runs",
            json={"label": label, "confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        ).status_code == 201
    second = ws.load_experiment(eid).sorted_runs()[1].id
    assert _answer(
        client,
        eid,
        {"series": SERIES, "descriptor": DESCRIPTOR, "qc": dict(QC, evidence="run two")},
        run_id=second,
    ).status_code == 200

    assert _submit(client, eid).status_code == 200
    exp = ws.load_experiment(eid)
    notes = {}
    for unit in exp.export_units():
        record = json.loads(unit.record_path().read_text(encoding="utf-8"))
        assert record["record_id"] == unit.current_record_id()
        notes[unit.run_id] = record["measurement"]["qc"]["evidence"]
    assert sorted(notes.values()) == ["run one", "run two"], notes


# ==========================================================================
# 3. THE BLOCKERS — AND THE ONE THING THE WIRE CANNOT SAY
# ==========================================================================


def test_an_unanswered_record_refuses_and_publishes_nothing(client, db):
    """The first refusal a person meets. Nothing on disk, nothing in any table."""
    eid = _create(client, "unanswered")
    refused = _submit(client, eid)
    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["error"] == "submission_blocked"
    assert body["pending_count"] == 3
    assert {q["kind"] for q in body["pending"]} == {"series", "qc", "descriptor"}
    assert body["published_record_count"] == 0 and body["records"] == []
    assert "Nothing was written" in body["message"]
    assert _artifacts(eid) == {}
    assert _row_counts(db) == (0, 0, 0, 0, 0)


def test_a_draft_only_finding_and_an_official_verdict_are_not_labelled(client, db):
    """**FINDING, PINNED AS MEASURED — the submit refusal cannot say which gate spoke.**

    ``official_validator_ran`` exists on this repository's wire *"precisely because the
    wire could not say whether the validator had run"* (``CLAUDE.md``, PR #185). It is
    published by ``POST .../validate`` and derivable from ``POST .../export`` (which
    carries ``official_report``, ``null`` exactly when the validator did not run). It is
    **absent from the submit refusal**, which flattens both gates into one
    ``failing_units[].errors`` list.

    Both arms are driven here on records a person built:

    * **The official validator RAN.** An unanswered record — the most common failing
      payload in the product — yields ``'descriptors' is a required property``, which is
      the vendored schema speaking.
    * **The official validator did NOT run.** A descriptor name carrying a trailing
      newline is refused by ISAAC's own anchored-pattern exactness gate
      (``src/isaac_records/exactness.py``), which returns before ``validate_official``
      is called; ``export_result_to_dict`` reports ``official_report: null``.

    WHAT IS ASSERTED, AND WHAT IS DELIBERATELY NOT. The absence of the discriminator is
    asserted, because that is what was measured. The ONE incidental difference — draft
    findings serialise under ``where`` and official errors under ``path`` — is asserted
    as an OBSERVATION so a future reader can see it exists, with the caveat that it is a
    by-product of two serialisers having different key names and is documented nowhere
    as a contract. This test does NOT assert that ``official_validator_ran`` ought to be
    added; that is a product decision, and no production code was changed here.

    §1's rule is not broken by either body: neither claims the official schema refused
    anything. The gap is that neither claims it did, and a client cannot tell.
    """
    unanswered = _create(client, "official arm")
    official_refusal = _submit(client, unanswered).json()

    name_with_newline = dict(DESCRIPTOR, name=DESCRIPTOR["name"] + "\n")
    exact = _built(client, "exactness arm", descriptor=name_with_newline)
    draft_refusal = _submit(client, exact).json()

    assert official_refusal["error"] == draft_refusal["error"] == "submission_blocked"
    official_errors = official_refusal["failing_units"][0]["errors"]
    draft_errors = draft_refusal["failing_units"][0]["errors"]

    # The two arms really are the two arms.
    assert official_errors[0]["message"] == "'descriptors' is a required property"
    assert "trailing newline" in draft_errors[0]["message"]

    # THE FINDING: no marker anywhere in either body says which gate produced them.
    for body in (official_refusal, draft_refusal):
        assert "official_validator_ran" not in body, body
        for unit in body["failing_units"]:
            assert set(unit) == {"unit_id", "run_id", "run_label", "errors"}, unit
            assert "official_validator_ran" not in unit
            assert "official_report" not in unit
            assert "draft_report" not in unit

    # THE CONTROL: the export route on the SAME exactness record does distinguish them,
    # so the information exists and is simply not carried onto this path.
    exported = client.post(
        f"/api/experiments/{exact}/export", headers={"If-Match": _etag(client, exact)}
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["official_report"] is None, (
        "the exactness gate must return before validate_official, or this test is "
        "measuring something else"
    )

    # THE INCIDENTAL DIFFERENCE, recorded as an observation. Not a contract.
    assert set(official_errors[0]) == {"path", "message"}
    assert set(draft_errors[0]) == {"where", "message"}


def test_neither_blocked_body_claims_the_official_schema_refused_the_record(client):
    """§1's rule, checked on both arms: no surface reports an ISAAC gate as a schema error."""
    exact = _built(
        client, "no misattribution", descriptor=dict(DESCRIPTOR, name=DESCRIPTOR["name"] + "\n")
    )
    body = _submit(client, exact).json()
    rendered = json.dumps(body)
    assert "official ISAAC schema" not in rendered, rendered[:400]
    assert "Invalid against" not in rendered
    assert "ISAAC gate" in rendered or "ISAAC will not strip" in rendered


def test_there_is_still_no_force_parameter_on_a_record_a_person_built(client, db):
    """No override, no ``?force=``, no body that turns the refusal into a submission."""
    eid = _create(client, "no override")
    for attempt in (
        lambda: client.post(
            f"/api/experiments/{eid}/submit?force=true", headers={"If-Match": _etag(client, eid)}
        ),
        lambda: client.post(
            f"/api/experiments/{eid}/submit",
            json={"force": True, "confirmed_by_user": True, "submit_anyway": True},
            headers={"If-Match": _etag(client, eid)},
        ),
    ):
        response = attempt()
        assert response.status_code == 409, response.text
        assert response.json()["error"] == "submission_blocked"
    assert _row_counts(db) == (0, 0, 0, 0, 0)
    assert _artifacts(eid) == {}


# ==========================================================================
# 4. CONFLICTS, NOTES, ASSETS
# ==========================================================================


def test_an_unresolved_conflict_is_disclosed_and_does_NOT_refuse(client, db):
    """**THE BRIEF FOR THIS PASS SAID "unresolved conflicts refuse". THEY DO NOT.**

    That is the documented and implemented behaviour, with a written reason: correcting
    an answer APPENDS a second confirmation rather than replacing the first, so a record
    would be refused forever for the act of fixing a typo. Pinned here on a record a
    person built, because a future change in the direction the brief assumed would be a
    real regression and this file should be the thing that catches it.

    The conflict is manufactured the way the product manufactures one — by answering the
    same question twice with different values.
    """
    eid = _built(client, "conflicting evidence")
    corrected = client.post(
        f"/api/experiments/{eid}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "compromised", "note": "second look"}},
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert corrected.status_code == 200, corrected.text

    submitted = _submit(client, eid)
    assert submitted.status_code == 200, submitted.text
    summary = submitted.json()["conflict_summary"]
    assert summary["gating"] == "disclosed_not_gated", summary
    assert len(db.submissions) == 1
    # The disclosure carries addresses and counts, never a scientific value.
    rendered = json.dumps(summary)
    assert "compromised" not in rendered and "second look" not in rendered, rendered


def test_an_unmapped_note_is_carried_in_the_snapshot_and_changes_no_record(client, db):
    """Unmapped Notes behave exactly as ``notes.py`` specifies: **a path, never a value.**

    ``NOTE_MAPPED`` is documented *"A scientist named the official field path this note
    belongs to. NOT a value."* So a mapped transcript line must (a) be preserved in the
    immutable revision snapshot, (b) appear nowhere in the published official record, and
    (c) not move the content signature — which is why resubmitting after mapping one is
    ``already_submitted`` rather than a second declaration.

    THIS ALSO CORRECTS A PHRASE IN THE BRIEF: it asked that "accepted transcript changes
    are carried" into the submission. A transcript-origin note is carried into the
    SNAPSHOT and is deliberately never carried into the RECORD; there is no route by
    which a note becomes a field value.
    """
    eid = _built(client, "notes")
    captured = client.post(
        f"/api/experiments/{eid}/transcript",
        json={"text": "the sample was copper oxide", "finalized": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert captured.status_code == 200, captured.text
    note_id = client.get(f"/api/experiments/{eid}/notes").json()["notes"][0]["id"]
    mapped = client.post(
        f"/api/experiments/{eid}/notes/{note_id}/review",
        json={
            "confirmed_by_user": True,
            "action": "map",
            "field_path": "sample.material.name",
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["note"]["state"] == "mapped"
    assert mapped.json()["note"]["is_field_value"] is False

    assert _submit(client, eid).status_code == 200
    record = json.loads(
        ws.load_experiment(eid).export_units()[0].record_path().read_text(encoding="utf-8")
    )
    assert record.get("sample") is None, (
        "a mapped note names a path and is not a value; it must never reach the record"
    )
    assert "copper oxide" in db.revisions[-1]["state"], (
        "the note IS part of the immutable snapshot, which is where it belongs"
    )

    # And mapping another one afterwards is not a second declaration.
    again = client.post(
        f"/api/experiments/{eid}/transcript",
        json={"text": "actually cuprous oxide", "finalized": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert again.status_code == 200, again.text
    repeat = _submit(client, eid)
    assert repeat.status_code == 409, repeat.text
    assert repeat.json()["error"] == "already_submitted"
    assert len(db.submissions) == 1


def test_an_asset_a_person_recorded_reaches_the_published_record(client, db):
    """Assets ARE carried — into the record, the snapshot and the signature."""
    eid = _built(client, "assets")
    created = client.post(
        f"/api/experiments/{eid}/assets",
        json={
            "confirmed_by_user": True,
            "asset_id": "reduction_output",
            "content_role": "reduction_product",
            "uri": "synthetic://example/probe/CuO.xdi",
            "sha256": "a" * 64,
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert created.status_code == 201, created.text

    assert _submit(client, eid).status_code == 200
    record = json.loads(
        ws.load_experiment(eid).export_units()[0].record_path().read_text(encoding="utf-8")
    )
    assert [a["asset_id"] for a in record["assets"]] == ["reduction_output"]
    assert record["assets"][0]["sha256"] == "a" * 64
    assert "reduction_output" in db.revisions[-1]["state"]


# ==========================================================================
# 5. PRECONDITIONS — AND THE WILDCARD
# ==========================================================================


def test_a_stale_if_match_refuses_and_writes_absolutely_nothing(client, db):
    """412, no artifact, no row. The precondition is checked inside the lock."""
    eid = _built(client, "stale")
    stale = _etag(client, eid)
    renamed = client.patch(
        f"/api/experiments/{eid}", json={"title": "renamed"}, headers={"If-Match": stale}
    )
    assert renamed.status_code == 200, renamed.text

    refused = _submit(client, eid, if_match=stale)
    assert refused.status_code == 412, refused.text
    assert refused.json()["error"] == "stale_write"
    assert _artifacts(eid) == {}, "a refused precondition must not publish an official record"
    assert _row_counts(db) == (0, 0, 0, 0, 0)


def test_if_match_star_declares_over_content_the_caller_never_read(client, db):
    """**THE WILDCARD, MEASURED — and this is the judgement call this pass was asked for.**

    ``routes._check_if_match`` accepts ``*`` deliberately and RFC 9110 says it matches
    iff the resource exists. ``test_mcp_if_match_wildcard.py`` refuses it at the MCP
    layer and pins that the HTTP acceptance did not change, so the acceptance is a
    committed decision, not an oversight.

    WHAT IT COSTS ON THIS PARTICULAR OPERATION, driven end to end: a caller reads the
    record, somebody else lands a science change, and the wildcard submit succeeds over
    the NEW content. The recorded ``content_signature`` is the new one. Submitting is
    "a declaration by a named person that the work is finished", so ``*`` attaches that
    person's name to content they did not see.

    IT IS NOT A LOST UPDATE, and that distinction is why this is pinned rather than
    reported as a defect: nothing is overwritten, the history is append-only, the record
    is published exactly as it stands, and the response returns the signature actually
    submitted so a careful client can compare. The exposure is misattribution, not data
    loss. My judgement is in the module report; this test exists so the behaviour cannot
    change silently in either direction.
    """
    eid = _built(client, "wildcard")
    before = ws.load_experiment(eid)
    signature_the_caller_read = submissions.content_signature(before.id, before.export_units())

    intervening = client.post(
        f"/api/experiments/{eid}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"qc": {"status": "compromised", "note": "somebody else looked"}},
        },
        headers={"If-Match": _etag(client, eid)},
    )
    assert intervening.status_code == 200, intervening.text
    after = ws.load_experiment(eid)
    signature_now = submissions.content_signature(after.id, after.export_units())
    assert signature_now != signature_the_caller_read

    submitted = _submit(client, eid, if_match="*")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["content_signature"] == signature_now
    assert submitted.json()["content_signature"] != signature_the_caller_read
    assert submitted.json()["subject"] == ACTOR
    record = json.loads(
        ws.load_experiment(eid).export_units()[0].record_path().read_text(encoding="utf-8")
    )
    assert record["measurement"]["qc"]["status"] == "compromised"


def test_the_wildcard_still_cannot_submit_a_record_that_does_not_exist(client, db):
    """The narrow control: ``*`` means "iff the resource exists", and it does not invent one."""
    missing = client.post(
        "/api/experiments/01NOSUCHRECORDEXISTS000001/submit", headers={"If-Match": "*"}
    )
    assert missing.status_code == 404, missing.text
    assert _row_counts(db) == (0, 0, 0, 0, 0)


# ==========================================================================
# 6. DOUBLE-CLICK, EXACT RETRY, SIMULTANEOUS SUBMIT
# ==========================================================================


def test_a_double_click_records_one_submission_and_echoes_the_first(client, db):
    """The second call is a refusal that hands back the receipt, not a second row."""
    eid = _built(client, "double click")
    first = _submit(client, eid)
    assert first.status_code == 200, first.text
    counts = _row_counts(db)

    second = _submit(client, eid)
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"] == "already_submitted"
    assert body["submission"]["submission_id"] == first.json()["submission_id"]
    assert _row_counts(db) == counts, "an already_submitted refusal wrote a row"
    assert body["published_record_count"] == 0


def test_an_exact_retry_under_the_same_key_replays_rather_than_re_declaring(client, db):
    """What an ``Idempotency-Key`` is FOR: a lost response, retried, returns the original."""
    eid = _built(client, "retry")
    first = _submit(client, eid, key="a-client-token-0001")
    assert first.status_code == 200, first.text
    counts = _row_counts(db)

    retry = _submit(client, eid, key="a-client-token-0001")
    assert retry.status_code == 200, retry.text
    assert retry.json()["replayed"] is True
    assert retry.json()["submission_id"] == first.json()["submission_id"]
    assert retry.json()["revision_id"] == first.json()["revision_id"]
    assert _row_counts(db) == counts


def test_the_same_key_over_different_content_is_refused_not_replayed(client, db):
    """A reused key over moved science must never replay somebody else's receipt."""
    eid = _built(client, "key reuse")
    assert _submit(client, eid, key="reused-key").status_code == 200
    counts = _row_counts(db)
    moved = client.post(
        f"/api/experiments/{eid}/edit",
        json={"confirmed_by_user": True, "answers": {"qc": {"status": "failed", "note": "no"}}},
        headers={"If-Match": _etag(client, eid)},
    )
    assert moved.status_code == 200, moved.text

    refused = _submit(client, eid, key="reused-key")
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "idempotency_key_conflict"
    assert _row_counts(db) == counts


def test_four_simultaneous_submits_record_exactly_one(client, db):
    """REAL THREADS through the real route, all holding the SAME validator.

    The outcome is not the one a reader expects, and it is the more informative one:
    the winner's materialisation advances the record's ``rev``, so the three losers'
    validator is stale by the time they take the lock and they are refused ``412``
    rather than ``already_submitted``. Either answer is correct and neither records a
    second declaration; what this pins is that the count is exactly one, whichever
    refusal the losers get.
    """
    eid = _built(client, "threads")
    shared = _etag(client, eid)
    results: list = []
    lock = threading.Lock()

    def go():
        response = client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": shared}
        )
        with lock:
            results.append((response.status_code, (response.json() or {}).get("error")))

    threads = [threading.Thread(target=go) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 4
    accepted = [r for r in results if r[0] == 200]
    assert len(accepted) == 1, results
    for status, error in results:
        if status == 200:
            continue
        assert (status, error) in {(412, "stale_write"), (409, "already_submitted")}, results
    assert len(db.submissions) == 1, db.submissions
    assert len(db.revisions) == 1


def test_a_second_submission_needs_a_second_revision_number(client, db):
    """``revision_id`` is UNIQUE and ``revision_no`` increments — one submission per revision."""
    eid = _built(client, "two revisions", runs=("300 K",))
    run_id = ws.load_experiment(eid).sorted_runs()[0].id
    assert _submit(client, eid).status_code == 200

    moved = client.patch(
        f"/api/experiments/{eid}/runs/{run_id}",
        json={"confirmed_by_user": True, "fields": {_SAFE_RUN_FIELD: _SAFE_RUN_VALUE}},
        headers={"If-Match": _run_etag(client, eid, run_id)},
    )
    assert moved.status_code == 200, moved.text
    second = _submit(client, eid)
    assert second.status_code == 200, second.text
    assert second.json()["revision_no"] == 2
    assert [r["revision_no"] for r in db.revisions] == [1, 2]
    assert len({r["revision_id"] for r in db.revisions}) == 2
    assert len({s["revision_id"] for s in db.submissions}) == 2, (
        "two submissions must not share one revision row"
    )
    # And a change row was recorded for the address that moved.
    assert [c["address"] for c in db.changes] == [_SAFE_RUN_FIELD], db.changes
    assert db.changes[0]["change_kind"] == submissions.CHANGE_ADDED


def test_which_run_level_writes_leave_a_record_submittable(client):
    """RE-DERIVES the comment on :data:`_SAFE_RUN_FIELD` rather than trusting it.

    All five run-writable paths are driven on their own record. The three ``context.*``
    ones each leave the record un-submittable *when written alone*, because the official
    schema declares ``context.required == ["environment", "temperature_K"]``, so the
    first write of either creates a ``context`` object missing its sibling. THAT IS NOT
    A DEFECT AND IS NOT REPORTED AS ONE — a single request supplying both is accepted,
    which this test also drives. It is recorded because it is the trap that makes
    ``_SAFE_RUN_FIELD`` a ``timestamps`` path, and because a reader who picked
    ``context.temperature_K`` for a submit test would spend an hour on it.
    """
    outcomes: dict[str, int] = {}
    for path, value in (
        ("timestamps.acquired_start_utc", "2026-01-01T00:00:00Z"),
        ("timestamps.acquired_end_utc", "2026-01-01T01:00:00Z"),
        ("context.environment", "ex_situ"),
        ("context.temperature_K", 301),
        ("context.thermodynamics.atmosphere", "air"),
    ):
        eid = _built(client, f"writable {path}", runs=("R",))
        run_id = ws.load_experiment(eid).sorted_runs()[0].id
        assert _submit(client, eid).status_code == 200
        written = client.patch(
            f"/api/experiments/{eid}/runs/{run_id}",
            json={"confirmed_by_user": True, "fields": {path: value}},
            headers={"If-Match": _run_etag(client, eid, run_id)},
        )
        assert written.status_code == 200, written.text
        outcomes[path] = _submit(client, eid).status_code

    assert set(routes.RUN_WRITABLE_FIELD_PATHS) == set(outcomes), (
        "a run-writable path was added or removed; drive it here too"
    )
    assert {p for p, s in outcomes.items() if s == 200} == {
        "timestamps.acquired_start_utc",
        "timestamps.acquired_end_utc",
    }, outcomes
    assert {p for p, s in outcomes.items() if s == 409} == {
        "context.environment",
        "context.temperature_K",
        "context.thermodynamics.atmosphere",
    }, outcomes

    # The control: both required siblings in ONE request, and it submits.
    eid = _built(client, "both context fields", runs=("R",))
    run_id = ws.load_experiment(eid).sorted_runs()[0].id
    assert _submit(client, eid).status_code == 200
    paired = client.patch(
        f"/api/experiments/{eid}/runs/{run_id}",
        json={
            "confirmed_by_user": True,
            "fields": {"context.environment": "ex_situ", "context.temperature_K": 301},
        },
        headers={"If-Match": _run_etag(client, eid, run_id)},
    )
    assert paired.status_code == 200, paired.text
    assert _submit(client, eid).status_code == 200


# ==========================================================================
# 7. PARTIAL MATERIALISATION
# ==========================================================================


def test_a_fault_partway_through_publication_records_no_submission(client, db, monkeypatch):
    """THE HALF-WRITTEN SHAPE, DRIVEN RATHER THAN DESCRIBED.

    ``_write_record`` is made to raise on the SECOND unit — a fault injection in the
    test process, reverted by ``monkeypatch``; no production code is modified. What is
    then measured, from disk and from the tables rather than from the status code:

    * unit one's record AND its evidence sidecar are on disk;
    * unit two's are not;
    * the state save never happened, so NEITHER run carries a ``record_id`` — this is
      exactly the orphan-pair shape ``_run_published_stem`` and ``_save_versioned``
      document, and it is why the discard guard asks about DISK and not only state;
    * **no submission row and no revision row exist**, because the durable write comes
      after materialisation. That ordering is the whole recoverability argument.
    """
    eid = _built(client, "partial", runs=("A", "B"))
    real_write = routes._write_record
    calls = {"n": 0}

    def failing_write(exp, result, unit, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("injected: the second unit's artifact could not be written")
        return real_write(exp, result, unit, **kwargs)

    monkeypatch.setattr(routes, "_write_record", failing_write)
    faulted = client.post(
        f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
    )
    assert faulted.status_code == 500, faulted.text
    assert calls["n"] == 2

    exp = ws.load_experiment(eid)
    assert exp is not None, "the record must survive a failed publication"
    on_disk = sorted(_artifacts(eid))
    assert len(on_disk) == 2, on_disk
    stem = on_disk[0].split(".")[0]
    assert on_disk == [f"{stem}.evidence.json", f"{stem}.json"], on_disk
    assert [run.record_id for run in exp.sorted_runs()] == [None, None], (
        "the state save comes after every artifact write, so a fault leaves an orphan "
        "pair with no persisted record_id — the shape the discard guard exists for"
    )
    assert _row_counts(db) == (0, 0, 0, 0, 0), (
        "a submission must never be recorded for records that were not all published"
    )


def test_the_retry_after_that_fault_converges_on_exactly_one_submission(client, db, monkeypatch):
    """The other half of the recoverability claim, measured rather than asserted."""
    eid = _built(client, "partial then retry", runs=("A", "B"))
    real_write = routes._write_record
    calls = {"n": 0}

    def failing_write(exp, result, unit, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("injected")
        return real_write(exp, result, unit, **kwargs)

    monkeypatch.setattr(routes, "_write_record", failing_write)
    assert (
        client.post(
            f"/api/experiments/{eid}/submit", headers={"If-Match": _etag(client, eid)}
        ).status_code
        == 500
    )
    monkeypatch.setattr(routes, "_write_record", real_write)

    retried = _submit(client, eid)
    assert retried.status_code == 200, retried.text
    run_ids = {run.id for run in ws.load_experiment(eid).sorted_runs()}
    assert set(_artifacts(eid)) == {
        f"{run_id}{suffix}" for run_id in run_ids for suffix in (".json", ".evidence.json")
    }
    assert _row_counts(db) == (1, 2, 0, 1, 2), (
        "one revision, two run revisions, one submission, two unit rows — exactly one "
        f"coherent declaration, not two halves: {_row_counts(db)}"
    )
    assert retried.json()["published_record_count"] == 2


# ==========================================================================
# 8. NOTHING DESTROYS A SUBMISSION
# ==========================================================================


def test_discard_refuses_a_submitted_record_and_removes_nothing(client, db):
    """Attacked directly, on both record shapes, with the tables re-read afterwards."""
    for title, runs, expected in (
        ("discard zero-run", (), "experiment_exported"),
        ("discard fan-out", ("300 K",), "runs_exported"),
    ):
        eid = _built(client, title, runs=runs)
        assert _submit(client, eid).status_code == 200
        artifacts = _artifacts(eid)
        counts = _row_counts(db)

        refused = client.post(
            f"/api/experiments/{eid}/discard",
            json={"confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"] == expected, refused.json()
        assert "Nothing was removed" in refused.json()["message"]
        assert ws.load_experiment(eid) is not None
        assert _artifacts(eid) == artifacts
        assert _row_counts(db) == counts


def test_discard_is_refused_by_HISTORY_ALONE_when_nothing_is_on_disk(client, db):
    """THE BACKSTOP ISOLATED. The artifact checks run first, so they normally fire first.

    This puts a revision row against a record that has published nothing, which removes
    every earlier refusal from the path and leaves ``_submission_history_refusal`` as the
    only thing standing between a scientist and a destroyed submission. It answers
    ``409 submitted``, names the counts, and removes nothing.
    """
    eid = _create(client, "history only")
    db.revisions.append(
        {
            "revision_id": "01ADVERSARIALHISTORYROW0001",
            "experiment_id": eid,
            "revision_no": 1,
            "experiment_rev": 1,
            "generation": "planted",
            "state": "{}",
            "content_signature": "0" * 64,
            "reason": sstore.REASON_SUBMISSION,
            "subject": None,
            "trust_basis": submissions.TRUST_BASIS_UNATTRIBUTED,
            "created_utc": "2026-01-01T00:00:00+00:00",
        }
    )
    assert _artifacts(eid) == {}, "the earlier refusals must not be reachable here"

    refused = client.post(
        f"/api/experiments/{eid}/discard",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "submitted"
    assert refused.json()["revision_count"] == 1
    assert ws.load_experiment(eid) is not None
    assert len(db.revisions) == 1


def test_removing_a_run_that_a_submission_named_is_refused(client, db):
    """A submitted unit is always an EXPORTED unit, so its run can never be removed.

    That is a structural consequence rather than a coincidence, and it is what makes a
    ``removed`` unit unreachable in the submission history: a unit only reaches a
    revision if it materialised, and ``post_run_remove`` refuses a materialised run.
    """
    eid = _built(client, "run removal", runs=("300 K", "400 K"))
    assert _submit(client, eid).status_code == 200
    artifacts = _artifacts(eid)
    counts = _row_counts(db)

    for run in ws.load_experiment(eid).sorted_runs():
        refused = client.post(
            f"/api/experiments/{eid}/runs/{run.id}/remove",
            json={"confirmed_by_user": True},
            headers={"If-Match": _etag(client, eid)},
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"] == "run_exported", refused.json()
    assert _artifacts(eid) == artifacts
    assert _row_counts(db) == counts
    assert len(ws.load_experiment(eid).runs) == 2


def test_a_run_added_after_a_submission_can_still_be_removed(client, db):
    """THE CONTROL for the test above. The refusal is about EXPORTED, not about SUBMITTED.

    Without this, ``run_exported`` on every run would be indistinguishable from a blanket
    freeze, and a change that froze the whole record would pass the test above.
    """
    eid = _built(client, "later run", runs=("300 K",))
    assert _submit(client, eid).status_code == 200
    added = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "500 K", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert added.status_code == 201, added.text
    new_run = added.json()["run"]["id"]
    counts = _row_counts(db)
    artifacts = _artifacts(eid)

    removed = client.post(
        f"/api/experiments/{eid}/runs/{new_run}/remove",
        json={"confirmed_by_user": True},
        headers={"If-Match": _etag(client, eid)},
    )
    assert removed.status_code == 200, removed.text
    assert _row_counts(db) == counts
    assert _artifacts(eid) == artifacts


def test_a_change_after_a_submission_is_a_NEW_revision_and_rewrites_nothing(client, db):
    """The immutability claim at the level a scientist experiences it."""
    eid = _built(client, "new revision", runs=("300 K",))
    run_id = ws.load_experiment(eid).sorted_runs()[0].id
    first = _submit(client, eid)
    assert first.status_code == 200, first.text
    artifacts = _artifacts(eid)
    first_revision = copy.deepcopy(db.revisions[0])
    first_submission = copy.deepcopy(db.submissions[0])

    moved = client.patch(
        f"/api/experiments/{eid}/runs/{run_id}",
        json={"confirmed_by_user": True, "fields": {_SAFE_RUN_FIELD: _SAFE_RUN_VALUE}},
        headers={"If-Match": _run_etag(client, eid, run_id)},
    )
    assert moved.status_code == 200, moved.text
    second = _submit(client, eid)
    assert second.status_code == 200, second.text

    assert db.revisions[0] == first_revision, "the first revision row was rewritten"
    assert db.submissions[0] == first_submission, "the first submission row was rewritten"
    assert second.json()["revision_no"] == 2
    assert second.json()["published_record_count"] == 0, (
        "the official record is immutable and is not republished"
    )
    assert _artifacts(eid) == artifacts, "the published artifacts were rewritten"
    assert second.json()["published_artifact_state"]["state"] == "stale", (
        "the response must DISCLOSE that what was submitted is not what is on disk"
    )


# ==========================================================================
# 9. THE GATE PARITY THAT MAKES THE DISCARD BACKSTOP SOUND
# ==========================================================================


def test_a_deployment_that_can_RECORD_a_submission_can_always_READ_one():
    """WHY ``_submission_history_refusal`` MAY RETURN ``None`` FOR A MISSING READER.

    It reasons that *"a deployment that cannot record a submission is exactly a
    deployment that cannot hold one"* — and a discard proceeds on that basis. That is
    only safe if the two gates are literally the same predicate, which is asserted here
    from source rather than taken from the comment. If a later change gave the store a
    weaker gate than the reader, discard would start destroying records whose history it
    simply could not see.

    Opens no connection: both functions are inspected, not called against a server.
    """
    import inspect

    import isaac_api.experiment_repository as repo

    store_src = inspect.getsource(sstore.store)
    reader_src = inspect.getsource(rhist.reader)
    assert "repo._postgres_available(env)" in store_src, store_src
    assert "repo._postgres_available(env)" in reader_src, reader_src
    assert callable(repo._postgres_available)
    # And in the shipped default (no PGHOST), both are None together.
    empty: dict[str, str] = {}
    assert sstore.store(empty) is None
    assert rhist.reader(empty) is None


# ==========================================================================
# 10. NEGATIVE CONTROL FOR THIS FILE'S OWN PREMISE
# ==========================================================================


def test_nothing_in_this_file_borrows_a_fixture_value():
    """The premise, guarded. Same shape and same reason as the one in
    ``test_scientist_can_finish_a_record.py``.

    This file's whole value is that its records start where a scientist starts. An edit
    that reached for ``ws._full_draft()``, ``_split_full_draft()``, ``load_demo_answers``
    or a canonical seed id would restore exactly the blind spot it exists to close, and
    the file would keep passing while measuring something else.
    """
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

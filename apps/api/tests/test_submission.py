"""``POST /api/experiments/{id}/submit`` — the scientist's submission lifecycle.

THE ONE CLAIM THIS WHOLE FILE EXISTS TO PROTECT: **submitting is a declaration by a
person, and it is never derived from anything else.** Exporting a record does not
submit it, an unattributable caller cannot submit, and a worked-example session is
never submitted. Everything else here is the machinery that keeps those three true
without leaving a half-written state behind.

HOW THE HAPPY PATH IS REACHABLE AT ALL, since the default build refuses every
submission. Two seams, and both are the ones the application actually uses:

  * ``ISAAC_EDGE_TRUST_VERIFIER=test_fixture`` plus ``ISAAC_FIXTURE_ACTOR_SUBJECT``
    selects ``identity.FixtureEdgeVerifier`` through the existing, boot-validated
    selection mechanism. It reads its subject from the PROCESS ENVIRONMENT and never
    from a request — a header-reading verifier would rebuild the forgeable-header
    hazard Q4 is answered against — and it mints ``trust_basis="test_fixture"``, so
    every row it causes is permanently labelled as fixture-attributed.
  * ``submission_store.store`` is monkeypatched to a store bound to the in-process
    connection double in ``submission_fake.py``. The real transaction machinery runs;
    only the server is fake. ``PGHOST`` stays UNSET, so experiments themselves keep
    using the filesystem repository exactly as they do in every other test here.

Every fixture is built from the committed synthetic seed drafts. Nothing here reads
real data and nothing here connects to a database.
"""

from __future__ import annotations

import copy
import json

import pytest

import isaac_api.db_write as dbw
import isaac_api.experiment_repository as repo
import isaac_api.identity as identity
import isaac_api.routes as routes
import isaac_api.submission_store as sstore
import isaac_api.submissions as submissions
import isaac_api.workspace as ws
from isaac_records.models import field_value, user_confirmation

from conftest import tutorial_client
from submission_fake import (
    FAKE_SUBMITTED_UTC,
    FakeSubmissionConnection,
    fake_env,
    fake_store,
)

ACTOR = "ada.lovelace"
EXPERIMENT_ID = "01SUBMITROUTEFIXTURE000001"

#: The two halves of the publication disclosure every refusal now carries, quoted
#: here so each assertion can check BOTH directions. A test that only asserted the
#: presence of one of them would pass against an unconditional message, which is the
#: exact defect (C1) these strings exist to pin.
PUBLISHED_NOTHING = "Nothing was written, and no official record was published."
PUBLISHED_SOMETHING = "ALREADY published"


def _assert_published_nothing(body: dict) -> None:
    """The refusal claims nothing reached the disk — and had better be right."""
    assert body["published_record_count"] == 0, body
    assert body["records"] == [], body
    assert PUBLISHED_NOTHING in body["message"], body["message"]
    assert PUBLISHED_SOMETHING not in body["message"], body["message"]


def _assert_published(body: dict, record_ids: set[str]) -> None:
    """The refusal names exactly the records THIS request put on disk."""
    assert body["published_record_count"] == len(record_ids), body
    assert {entry["record_id"] for entry in body["records"]} == record_ids, body
    assert PUBLISHED_SOMETHING in body["message"], body["message"]
    assert PUBLISHED_NOTHING not in body["message"], body["message"]
    for record_id in record_ids:
        assert record_id in body["message"], body["message"]


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    return ws


@pytest.fixture()
def armed(workspace, monkeypatch):
    """A deployment that CAN attribute: the fixture verifier, with a subject."""
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.setenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, ACTOR)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_GROUPS_ENV, raising=False)
    return workspace


@pytest.fixture()
def db():
    return FakeSubmissionConnection()


@pytest.fixture()
def wired(monkeypatch, db):
    """Point the route's store factory at the connection double."""
    store = fake_store(db)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    return store


def _client():
    from isaac_api.app import create_app

    from fastapi.testclient import TestClient

    return TestClient(create_app(), raise_server_exceptions=False)


def _make(experiment_id: str = EXPERIMENT_ID, *, runs: tuple[str, ...] = (), draft=None):
    """An export-ready ordinary-scope experiment, optionally with runs."""
    exp = ws.create_experiment(
        "Submission fixture",
        {"kind": "synthetic"},
        copy.deepcopy(draft) if draft is not None else ws._full_draft(),
        id=experiment_id,
    )
    for label in runs:
        exp.add_run(label=label, draft={})
    exp.save_versioned()
    return ws.load_experiment(experiment_id)


def _etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _submit(client, experiment_id: str, *, if_match=..., key: str | None = None):
    headers = {}
    tag = _etag(client, experiment_id) if if_match is ... else if_match
    if tag is not None:
        headers["If-Match"] = tag
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(f"/api/experiments/{experiment_id}/submit", headers=headers)


def _export(client, experiment_id: str):
    return client.post(
        f"/api/experiments/{experiment_id}/export",
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _artifacts(exp) -> set[str]:
    records_dir = exp.records_dir
    if not records_dir.is_dir():
        return set()
    return {p.name for p in records_dir.iterdir()}


# =============================================================================
# 1. PRODUCTION IS FAIL-CLOSED, AND FAILS AS A 409 RATHER THAN A 500
# =============================================================================


def test_the_default_build_refuses_every_submission_with_a_typed_409(workspace, wired, db):
    """No verifier is configured anywhere in this build, so nobody can be attributed.

    409 AND NOT 500 IS THE POINT. ``identity.HumanActorRequired`` is raised from a
    FastAPI dependency, and its own docstring warned that until the handler is
    registered in ``create_app`` "raising this from a live route would surface as a
    500". This route is the first consumer; ``create_app`` registers the handler in
    the same change. Without that line this test sees a bare 500 with a traceback in
    the server log.
    """
    _make()
    client = _client()
    response = _submit(client, EXPERIMENT_ID)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "human_actor_required"
    assert body["operation"] == "submit"
    assert body["reason"] == "no_verifier_configured"
    assert "Nothing was written" in body["message"]
    # NOTHING WAS WRITTEN, in either place. No submission row...
    assert db.is_empty()
    # ...and no official record either: the refusal precedes materialisation.
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == set()


def test_the_refusal_names_no_host_path_credential_or_driver_message(workspace, wired):
    _make()
    text = _submit(_client(), EXPERIMENT_ID).text
    for leak in ("PGHOST", "PGPASSWORD", "db.invalid", "/private/tmp", "Traceback"):
        assert leak not in text, leak


def test_five_planted_edge_headers_do_not_make_a_submission_possible(workspace, wired, db):
    """A forged identity header is worth exactly nothing on this route.

    The infrastructure owner's Q4 answer is that the Service is a plain ClusterIP
    with no NetworkPolicy, so any in-cluster pod can send these. The route consumes
    ``require_human_actor``, which reaches an actor only through a verifier, and no
    shipped verifier reads a request at all.
    """
    _make()
    client = _client()
    headers = {name: "attacker" for name in identity.EDGE_INJECTED_HEADERS}
    headers.update({name: "attacker" for name in identity.PERMANENTLY_UNTRUSTED_HEADERS})
    headers["If-Match"] = _etag(client, EXPERIMENT_ID)
    response = client.post(f"/api/experiments/{EXPERIMENT_ID}/submit", headers=headers)
    assert response.status_code == 409
    assert response.json()["reason"] == "no_verifier_configured"
    assert db.is_empty()
    assert "attacker" not in response.text


def test_a_configured_verifier_with_no_subject_refuses_with_the_other_reason(
    workspace, monkeypatch, wired, db
):
    """A verifier RAN and found no boundary — which is not the same as none looking.

    ``Unconfigured`` would be false here: a verifier was selected. The fixture
    verifier returns ``NotTraversed``, which resolves to
    ``unverified_edge_traversal``, and the two reasons carry different messages
    because they suggest different next steps.
    """
    monkeypatch.setenv(identity.EDGE_TRUST_VERIFIER_ENV, identity.FIXTURE_VERIFIER)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    _make()
    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 409
    assert response.json()["reason"] == "unverified_edge_traversal"
    assert db.is_empty()


# =============================================================================
# 2. THE ORDER OF REFUSALS, each writing nothing
# =============================================================================


def test_an_unknown_id_is_404(armed, wired, db):
    response = _submit(_client(), "01NOSUCHEXPERIMENT00000000", if_match='"x.0"')
    assert response.status_code == 404
    assert response.json()["error"] == "experiment_not_found"
    assert db.is_empty()


def test_a_worked_example_session_record_is_never_submitted(armed, wired, db):
    """409, and all three enforcements of the rule are named in the codebase.

    This route refuses a scoped request outright; ``identity.stamp_actor`` returns
    ``None`` for any non-``None`` scope; and
    ``PostgresOrdinaryStore.refuse_if_not_persistable`` raises on a session record.
    A worked-example session is temporary and synthetic, so a durable declaration
    over one would outlive the thing it declares, attached to fabricated science.
    """
    from isaac_api.app import create_app

    client = tutorial_client(create_app(), raise_server_exceptions=False)
    response = _submit(client, ws.SEED_READY_ID)
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "tutorial_scope_forbidden"
    assert db.is_empty()
    assert _artifacts(ws.load_experiment(ws.SEED_READY_ID, session_id=client.tutorial_session_id)) == set()


def test_a_missing_if_match_is_428_and_a_malformed_one_is_400(armed, wired, db):
    _make()
    client = _client()
    absent = _submit(client, EXPERIMENT_ID, if_match=None)
    assert absent.status_code == 428
    assert absent.json()["error"] == "precondition_required"
    for bad in ('W/"weak"', "unquoted", ","):
        malformed = _submit(client, EXPERIMENT_ID, if_match=bad)
        assert malformed.status_code == 400, bad
        assert malformed.json()["error"] == "malformed_if_match"
    assert db.is_empty()
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == set()


def test_a_stale_if_match_is_412_and_echoes_the_current_etag(armed, wired, db):
    _make()
    client = _client()
    response = _submit(client, EXPERIMENT_ID, if_match='"stale.0"')
    assert response.status_code == 412
    assert response.json()["error"] == "stale_write"
    assert response.headers["ETag"] == _etag(client, EXPERIMENT_ID)
    assert db.is_empty()


@pytest.mark.parametrize("key", ["", "   ", "k" * (sstore.IDEMPOTENCY_KEY_MAX + 1)])
def test_a_malformed_idempotency_key_is_400_and_writes_nothing(armed, wired, db, key):
    """400 rather than 422, matching ``malformed_if_match``: both are HEADERS.

    The bound exists because the column has no length limit of its own, and the
    emptiness check because ``''`` is a key every keyless retry could collide with —
    which the database CHECK also refuses.
    """
    _make()
    response = _submit(_client(), EXPERIMENT_ID, key=key)
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "malformed_idempotency_key"
    assert db.is_empty()


def test_no_durable_storage_is_a_503_that_publishes_nothing(armed, monkeypatch, tmp_path):
    monkeypatch.setattr(sstore, "store", lambda env=None: None)
    _make()
    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "submission_unavailable"
    assert body["reason"] == sstore.BLOCKER_NO_DURABLE_STORAGE
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == set()


def test_absent_submission_tables_are_a_503_that_publishes_nothing(armed, monkeypatch):
    """THE DEPLOYMENT-ORDER CASE, and the reason the check runs before materialising.

    The image rolls out on merge and an operator applies migrations by hand
    afterwards, so a build routinely runs against a database its own migration has
    not reached. If the tables were checked AFTER materialisation, that window would
    publish official records for a submission that could not be recorded.

    THIS IS THE **NEGATIVE CONTROL** FOR C1's DISCLOSURE, and it is only a control
    because its sibling
    ``test_tables_that_vanish_after_the_preflight_disclose_what_was_published``
    exercises the same refusal on the other side of materialisation. Together they
    fail an unconditional message in whichever direction it is written.
    """
    db = FakeSubmissionConnection(tables=False)
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    _make()
    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["reason"] == "tables_absent"
    _assert_published_nothing(body)
    assert db.is_empty()
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == set(), (
        "an official record was published for a submission that could not be recorded"
    )


def test_tables_that_vanish_after_the_preflight_disclose_what_was_published(
    armed, monkeypatch
):
    """C1(A). THE REFUSAL ARRIVES AFTER TWO OFFICIAL RECORDS ARE ON DISK.

    The preflight answers "tables present" and the route materialises; by the time
    ``record_submission`` re-probes inside its own transaction they are gone (the
    operator rolled the migration back, or the request raced the apply). The
    transaction really did issue only ``SELECT``s and roll back — ``db.is_empty()``
    proves it — but an artifact pair IS on disk and ``record_id`` HAS moved, and the
    message used to end "Nothing was written, and no official record was published."

    WHY THAT MATTERED ENOUGH TO BE A CRITICAL. Exported records are immutable and no
    route republishes one. A scientist told nothing was published edits the record
    and retries; the retry publishes nothing, and the artifacts hold the pre-edit
    science permanently under ids the eventual submission names.
    """
    db = FakeSubmissionConnection()
    store = fake_store(db)
    real_preflight = store.preflight

    def vanishing(*args, **kwargs):
        answer = real_preflight(*args, **kwargs)
        db.tables.clear()
        return answer

    monkeypatch.setattr(store, "preflight", vanishing)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    _make()

    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["reason"] == "tables_absent"
    _assert_published(body, {EXPERIMENT_ID})
    # The TRUE half is not weakened: no submission row exists.
    assert db.is_empty(), "the refused transaction left a row behind"
    # ...and the false half is now false no longer — the records really are there,
    # and the record's own state really did move.
    exp = ws.load_experiment(EXPERIMENT_ID)
    assert _artifacts(exp) == {f"{EXPERIMENT_ID}.json", f"{EXPERIMENT_ID}.evidence.json"}
    assert exp.record_id == EXPERIMENT_ID


def test_unanswered_blockers_refuse_with_a_per_unit_report_and_publish_nothing(
    armed, wired, db
):
    """The gate is EXACTLY the export gate: pending == 0 AND every dry run passes."""
    _make(draft=ws._blank_draft() if hasattr(ws, "_blank_draft") else ws._review_draft())
    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "submission_blocked"
    assert body["pending_count"] >= 1 or body["failing_units"]
    assert db.is_empty()
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == set()


def test_there_is_no_force_parameter_and_no_submit_anyway(armed, wired, db):
    """Contract §3 D4: a validation failure on any run blocks the whole submission.

    Asserted as an ABSENCE, over the generated contract, because a future slice
    adding an override would otherwise be invisible to every other test here.
    """
    from isaac_api.app import create_app

    operation = create_app().openapi()["paths"][
        "/api/experiments/{experiment_id}/submit"
    ]["post"]
    names = {p["name"].lower() for p in operation.get("parameters", [])}
    assert not any(
        token in name for name in names for token in ("force", "anyway", "override", "skip")
    ), names
    assert "requestBody" not in operation, "submit takes no body, so none can carry a force flag"


def test_a_sibling_link_conflict_refuses_the_submission_too(armed, wired, db, monkeypatch):
    """The shared refusal, reached from the submit route rather than from export."""
    _make()
    monkeypatch.setattr(
        ws,
        "sibling_link_conflicts",
        lambda units: [{"record_id": "01AAAAAAAAAAAAAAAAAAAAAAAA", "detail": "x"}],
    )
    # `sibling_link_conflicts` is consulted only for an experiment WITH runs, so the
    # fixture needs one; a zero-run experiment has no siblings by construction.
    exp = ws.load_experiment(EXPERIMENT_ID)
    exp.add_run(label="only run", draft=copy.deepcopy(exp.draft))
    exp.save_versioned()
    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "sibling_link_conflict"
    assert db.is_empty()


# =============================================================================
# 3. THE HAPPY PATH
# =============================================================================


def test_a_submission_publishes_the_records_and_records_who_submitted_them(armed, wired, db):
    _make()
    client = _client()
    response = _submit(client, EXPERIMENT_ID)
    assert response.status_code == 200, response.text
    body = response.json()

    # The declaration.
    assert body["experiment_id"] == EXPERIMENT_ID
    assert body["subject"] == ACTOR
    assert body["trust_basis"] == identity.TRUST_BASIS_TEST_FIXTURE
    assert body["replayed"] is False
    assert body["unit_count"] == 1
    # THE SERVER ASSIGNED THE TIME. The double stamps a fixed value; an application
    # substituting its own clock fails here.
    assert body["submitted_utc"] == FAKE_SUBMITTED_UTC

    # The records it published.
    assert body["published_record_count"] == 1
    assert body["records"][0]["record_id"] == EXPERIMENT_ID
    exp = ws.load_experiment(EXPERIMENT_ID)
    assert _artifacts(exp) == {f"{EXPERIMENT_ID}.json", f"{EXPERIMENT_ID}.evidence.json"}

    # The rows.
    assert len(db.submissions) == 1
    stored = db.submissions[0]
    assert stored["subject"] == ACTOR
    assert stored["trust_basis"] == identity.TRUST_BASIS_TEST_FIXTURE
    assert stored["content_signature"] == body["content_signature"]
    assert len(db.revisions) == 1
    assert db.submission_runs[0]["record_id"] == EXPERIMENT_ID
    assert db.submission_runs[0]["run_id"] is None


def test_a_fan_out_submission_records_one_row_per_run(armed, wired, db):
    """One Run, one official record, one ``isaac_submission_runs`` row — contract §1 D1."""
    exp = _make()
    run_draft = copy.deepcopy(exp.draft)
    exp = ws.load_experiment(EXPERIMENT_ID)
    for label in ("run A", "run B"):
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()

    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unit_count"] == 2
    run_ids = {r.id for r in ws.load_experiment(EXPERIMENT_ID).runs}
    assert {row["unit_id"] for row in db.submission_runs} == run_ids
    assert {row["run_id"] for row in db.submission_runs} == run_ids
    # `record_id = unit_id`, which is the CHECK the schema also carries.
    assert all(row["record_id"] == row["unit_id"] for row in db.submission_runs)
    # One run-revision row per run, frozen in the snapshot.
    assert {r["run_id"] for r in db.run_revisions} == run_ids


def test_the_recorded_subject_is_labelled_test_fixture_and_never_a_verified_edge(
    armed, wired, db
):
    """A fixture-attributed row says so about itself, permanently.

    That label is the whole mitigation for a test/dev verifier existing at all: if
    it is ever enabled somewhere it should not be, the rows it caused are
    identifiable without anyone remembering how the deployment was configured.
    """
    _make()
    assert _submit(_client(), EXPERIMENT_ID).status_code == 200
    for row in db.revisions + db.submissions:
        assert row["trust_basis"] == identity.TRUST_BASIS_TEST_FIXTURE
        assert row["trust_basis"] != identity.TRUST_BASIS_VERIFIED_EDGE_ASSERTION
    # And no shipped verifier can mint the stronger basis at all.
    for factory in identity._VERIFIERS.values():
        verdict = factory().verify(object())
        assertion = getattr(verdict, "assertion", None)
        if assertion is not None:
            assert assertion.trust_basis == identity.TRUST_BASIS_TEST_FIXTURE


def test_submitting_a_fully_exported_record_publishes_nothing_and_still_records_it(
    armed, wired, db
):
    """THE CASE THAT MAKES SUBMIT UNABLE TO CALL THE EXPORT ROUTE.

    ``post_export`` answers ``409 record_exists`` when every unit is already
    materialised, which is the normal state of a fully-exported record. Routing
    submit through it would make the most-ready records the ones that cannot be
    submitted. Materialised units are skipped: never revalidated, never rewritten.
    """
    _make()
    client = _client()
    assert _export(client, EXPERIMENT_ID).status_code == 200
    before = {
        name: (ws.load_experiment(EXPERIMENT_ID).records_dir / name).read_bytes()
        for name in _artifacts(ws.load_experiment(EXPERIMENT_ID))
    }
    # Export a second time and the route refuses — the state submit must survive.
    assert _export(client, EXPERIMENT_ID).status_code == 409

    response = _submit(client, EXPERIMENT_ID)
    assert response.status_code == 200, response.text
    assert response.json()["published_record_count"] == 0
    assert response.json()["records"] == []
    assert len(db.submissions) == 1
    after = {
        name: (ws.load_experiment(EXPERIMENT_ID).records_dir / name).read_bytes()
        for name in _artifacts(ws.load_experiment(EXPERIMENT_ID))
    }
    assert after == before, "an already-exported record was rewritten by a submission"


def test_a_submission_discloses_whether_the_published_records_are_current(armed, wired, db):
    """A DEFECT FOUND WHILE WRITING THE REAL-ENGINE PROOF, not a hypothetical.

    Exported records are immutable, so an already-materialised unit is skipped and
    never rewritten. Export a record, edit its draft, submit — and the submission
    names record ids whose artifacts hold something else. The response must not let
    a reader infer that what was submitted is what was published.

    IT IS DISCLOSED AND NOT REFUSED, deliberately: the hard-blocker gate is exactly
    the export gate (contract §3 D4), and there is no operation that republishes an
    immutable record, so refusing would leave a scientist with no way forward.
    """
    _make()
    client = _client()
    assert _export(client, EXPERIMENT_ID).status_code == 200
    clean = _submit(client, EXPERIMENT_ID)
    assert clean.status_code == 200, clean.text
    assert clean.json()["published_artifact_state"]["state"] == "current"

    exp = ws.load_experiment(EXPERIMENT_ID)
    address = next(iter(exp.draft["fields"]))
    exp.draft["fields"][address]["value"] = "edited after the record was published"
    exp.save_versioned()

    edited = _submit(client, EXPERIMENT_ID)
    assert edited.status_code == 200, edited.text
    state = edited.json()["published_artifact_state"]
    assert state["state"] == "stale", state
    assert state["reason"], "a stale disclosure with no reason explains nothing"
    # It published nothing — the record is immutable — and the count says so rather
    # than implying the edit reached the artifact.
    assert edited.json()["published_record_count"] == 0


def test_the_disclosure_is_present_on_a_replay_too(armed, wired, db):
    """One shape, so a client never branches on whether a key exists."""
    _make()
    client = _client()
    assert _submit(client, EXPERIMENT_ID, key="k").status_code == 200
    replay = _submit(client, EXPERIMENT_ID, key="k")
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["published_artifact_state"]["state"] == "current"


# =============================================================================
# 4. EXPORT DOES NOT SUBMIT
# =============================================================================


def test_exporting_records_no_submission_of_any_kind(armed, wired, db):
    """The claim this whole file exists to protect, asserted at its narrowest.

    An export can be run by any caller at any time and needs no attributable actor.
    If it recorded a submission, it would attribute a declaration nobody made.
    """
    _make()
    client = _client()
    assert _export(client, EXPERIMENT_ID).status_code == 200
    assert db.is_empty(), "exporting wrote a submission row"
    assert db.statements == [], "exporting opened the submission write path at all"


def test_the_export_route_declares_no_dependency_on_the_submission_seam():
    """A TEXTUAL guard over ``post_export``'s own body, and nothing wider than that.

    **THIS DOCSTRING USED TO CLAIM IT "asserts on the whole call graph", AND IT DOES
    NOT.** It reads exactly one function's source with ``inspect.getsource`` and
    greps for three names, which is the weaker check the sentence above it was
    dismissing — a helper called from ``post_export`` could still reach the seam and
    this would pass.

    THE BEHAVIOURAL CLAIM IS COVERED, just not here: ``db.statements == []`` in
    ``test_exporting_records_no_submission_of_any_kind`` proves the export route
    opened no statement against the submission connection at all, through whatever
    call graph it took. This test is the cheap tripwire that makes a future edit to
    ``post_export`` itself visible in review; that one is the proof.
    """
    import inspect

    source = inspect.getsource(routes.post_export)
    for forbidden in ("submission_store", "submissions.content_signature", "record_submission"):
        assert forbidden not in source, forbidden


# =============================================================================
# 5. IDEMPOTENCE AND CONCURRENCY
# =============================================================================


def test_submitting_the_same_content_twice_is_refused_and_echoes_the_first(armed, wired, db):
    _make()
    client = _client()
    first = _submit(client, EXPERIMENT_ID)
    assert first.status_code == 200, first.text
    second = _submit(client, EXPERIMENT_ID)
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"] == "already_submitted"
    assert body["submission"]["submission_id"] == first.json()["submission_id"]
    assert len(db.submissions) == 1, "a duplicate submission row was written"


def test_an_exact_retry_under_the_same_key_replays_the_original_200(armed, wired, db):
    _make()
    client = _client()
    first = _submit(client, EXPERIMENT_ID, key="retry-1")
    assert first.status_code == 200, first.text
    replay = _submit(client, EXPERIMENT_ID, key="retry-1")
    assert replay.status_code == 200, replay.text
    body = replay.json()
    # THE ORIGINAL ROW, READ BACK — the original id, the original timestamp.
    assert body["submission_id"] == first.json()["submission_id"]
    assert body["submitted_utc"] == first.json()["submitted_utc"]
    # ...and it is FLAGGED, because a client that cannot tell a first success from a
    # replay cannot tell whether its own retry logic works, and a UI saying
    # "submitted just now" over an older submission asserts a time that never was.
    assert body["replayed"] is True
    assert first.json()["replayed"] is False
    # A replay publishes nothing, and says so rather than claiming the original's work.
    assert body["published_record_count"] == 0 and body["records"] == []
    assert len(db.submissions) == 1


def test_the_same_key_over_different_content_is_refused_rather_than_replayed(
    armed, wired, db
):
    """A reused key is a client bug, and silently replaying it would hide one."""
    _make()
    client = _client()
    assert _submit(client, EXPERIMENT_ID, key="k").status_code == 200
    exp = ws.load_experiment(EXPERIMENT_ID)
    address = next(iter(exp.draft["fields"]))
    exp.draft["fields"][address]["value"] = "changed after the first submission"
    exp.save_versioned()
    response = _submit(client, EXPERIMENT_ID, key="k")
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "idempotency_key_conflict"
    assert len(db.submissions) == 1


def test_a_losing_concurrent_submit_is_answered_from_the_winners_row(armed, monkeypatch):
    """THE THIRD POST-RACE OUTCOME: no readable winner, so the GENERIC conflict.

    The loser rolled back, so the winner is read in a FRESH transaction — reading it
    inside the loser's would return the loser's own uncommitted view.

    THIS TEST COVERS ONE OF THE THREE OUTCOMES, AND SAYS SO. Its docstring used to
    promise "409 echoing the winner, or a replay if it carried the winner's key" and
    asserted neither (review item I5). Those two are now exercised by
    ``test_a_lost_race_with_a_readable_winner_echoes_it`` and
    ``test_a_lost_race_under_the_winners_key_replays_the_winners_row``; what happens
    HERE is the case where the winner is gone or unreadable, in which reporting a
    specific outcome would be inventing one.

    IT ALSO ASSERTS WHAT THE REQUEST PUBLISHED (C1(B)). The refusal arrives after
    materialisation, so an official record IS on disk; the message used to say
    "Nothing was written by this request."
    """
    db = FakeSubmissionConnection()
    store = fake_store(db)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    _make()
    client = _client()
    assert _submit(client, EXPERIMENT_ID).status_code == 200
    winner_id = db.submissions[0]["submission_id"]

    # Now simulate the race: the preflight sees nothing (a second experiment id, so
    # the natural key is free) but the insert loses.
    second = "01SUBMITROUTEFIXTURE000002"
    _make(second)
    db.refuse_submission_insert = True
    response = _submit(client, second)
    assert response.status_code == 409, response.text
    body = response.json()
    # The winner for THAT signature does not exist (the fake refused every insert),
    # so the honest answer is the generic conflict rather than an invented receipt.
    assert body["error"] == "submission_conflict"
    assert len(db.submissions) == 1 and db.submissions[0]["submission_id"] == winner_id
    assert len(db.revisions) == 1, "the loser's revision row survived"
    # C1(B) — the loser DID publish an official record before it was refused.
    _assert_published(body, {second})
    assert _artifacts(ws.load_experiment(second)) == {
        f"{second}.json",
        f"{second}.evidence.json",
    }


def _lose_the_race_to(db, *, experiment_id: str, content_signature: str, **row):
    """Arm the one-shot hook so a concurrent writer commits just before our insert.

    This is the ONLY window that yields ``SubmissionRaceLost`` rather than
    ``SubmissionAlreadyExists``: ``record_submission`` re-reads the signature and the
    key inside its own transaction, so a row that exists before that read is found by
    it instead.
    """
    db.before_submission_insert = lambda conn: conn.commit_from_another_writer(
        conn.winner_row(
            experiment_id=experiment_id, content_signature=content_signature, **row
        )
    )


def _signature_of(experiment_id: str) -> str:
    exp = ws.load_experiment(experiment_id)
    return submissions.content_signature(exp.id, exp.export_units())


def test_a_lost_race_with_a_readable_winner_echoes_it(armed, monkeypatch):
    """I5 + C1(C). The winner's row is echoed, and what we published is disclosed.

    The loser is answered exactly as it would have been had it arrived one moment
    later — a ``409 already_submitted`` carrying the winner's receipt — and it must
    NOT claim that nothing was published, because it materialised the record before
    the write.
    """
    db = FakeSubmissionConnection()
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    _make()
    _lose_the_race_to(db, experiment_id=EXPERIMENT_ID, content_signature=_signature_of(EXPERIMENT_ID))

    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "already_submitted"
    assert body["submission"]["submission_id"] == "01WINNERSUBMISSION00000001"
    assert body["submission"]["subject"] == "other.scientist"
    _assert_published(body, {EXPERIMENT_ID})
    # The winner's row survived the loser's rollback; the loser's did not land.
    assert [row["submission_id"] for row in db.submissions] == ["01WINNERSUBMISSION00000001"]
    assert db.revisions == [], "the loser's revision row was not rolled back"
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == {
        f"{EXPERIMENT_ID}.json",
        f"{EXPERIMENT_ID}.evidence.json",
    }


def test_a_lost_race_under_the_winners_key_replays_the_winners_row(armed, monkeypatch):
    """I5 + the replay branch's own disclosure.

    A client retrying with the key the winner used cannot tell a lost response from a
    duplicate request, so it gets the original ``200`` — but ``records`` on a replay
    means *what this request published*, and after a lost race that is not empty.
    The helper's docstring used to assert it always was.
    """
    db = FakeSubmissionConnection()
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    _make()
    _lose_the_race_to(
        db,
        experiment_id=EXPERIMENT_ID,
        content_signature=_signature_of(EXPERIMENT_ID),
        idempotency_key="shared-key",
    )

    response = _submit(_client(), EXPERIMENT_ID, key="shared-key")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["replayed"] is True
    assert body["submission_id"] == "01WINNERSUBMISSION00000001"
    assert body["submitted_utc"] == FAKE_SUBMITTED_UTC
    # THE HALF THAT USED TO BE HARDCODED TO ZERO.
    assert body["published_record_count"] == 1, body
    assert body["records"][0]["record_id"] == EXPERIMENT_ID, body
    assert len(db.submissions) == 1


def test_a_lost_race_to_the_same_key_over_other_content_is_a_key_conflict(
    armed, monkeypatch
):
    """I5 + C1(D). The winner holds our key but different content.

    ``by_signature`` finds nothing and ``by_key`` finds the winner, so the honest
    answer is "your key is reused, choose a new one" rather than a replay of a
    submission over content this caller never sent — and it too must disclose the
    record it published on the way here.
    """
    db = FakeSubmissionConnection()
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(db))
    _make()
    _lose_the_race_to(
        db,
        experiment_id=EXPERIMENT_ID,
        content_signature="f" * 64,  # NOT this request's content
        idempotency_key="shared-key",
    )

    response = _submit(_client(), EXPERIMENT_ID, key="shared-key")
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "idempotency_key_conflict"
    assert body["submission"]["submission_id"] == "01WINNERSUBMISSION00000001"
    _assert_published(body, {EXPERIMENT_ID})


def test_a_second_submission_before_materialisation_still_says_nothing_was_published(
    armed, wired, db
):
    """THE NEGATIVE CONTROL for the three tests above.

    The same two refusals, reached from the PREFLIGHT — before a single artifact is
    written — must keep the sentence they always had. Without this, a disclosure that
    unconditionally claimed a publication would pass everything above.
    """
    _make()
    client = _client()
    assert _submit(client, EXPERIMENT_ID, key="first").status_code == 200
    before = _artifacts(ws.load_experiment(EXPERIMENT_ID))

    duplicate = _submit(client, EXPERIMENT_ID)
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"] == "already_submitted"
    _assert_published_nothing(duplicate.json())

    exp = ws.load_experiment(EXPERIMENT_ID)
    address = next(iter(exp.draft["fields"]))
    exp.draft["fields"][address]["value"] = "changed after the first submission"
    exp.save_versioned()
    reused = _submit(client, EXPERIMENT_ID, key="first")
    assert reused.status_code == 409, reused.text
    assert reused.json()["error"] == "idempotency_key_conflict"
    _assert_published_nothing(reused.json())

    # And nothing was republished on either path — the records are immutable.
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == before


# =============================================================================
# 5b. A CONFIGURED DATABASE THAT DOES NOT WORK IS A TYPED 503, NEVER A 500
# =============================================================================


def test_the_submission_store_and_the_experiment_repository_gate_identically(workspace):
    """I1, at its root. Two surfaces disagreeing about one deployment is the defect.

    ``submission_store.store`` used to gate on ``PGHOST`` alone while
    ``experiment_repository.ordinary_store`` additionally applied
    ``db_write.pgdatabase_gate``. A deployment with ``PGHOST`` set and ``PGDATABASE``
    pointing elsewhere therefore built a submission store, opened a transaction, and
    had ``WriteRefused`` raised at it from inside ``write_transaction`` — an exception
    no handler renders, so the route answered **500**.
    """
    cases = [
        ({}, True),
        ({"PGHOST": ""}, True),
        (fake_env(), False),
        (fake_env(PGDATABASE="somewhere_else"), True),
        (fake_env(PGDATABASE=""), True),
    ]
    for env, expect_none in cases:
        assert (sstore.store(env) is None) is expect_none, env
        assert (sstore.store(env) is None) == (repo.ordinary_store(env) is None), env


def test_a_misconfigured_pgdatabase_is_a_typed_503_and_never_a_500(armed, monkeypatch):
    """I1, through the route, with the health block asserted beside it."""
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", "somewhere_else")
    _make()
    client = _client()

    health = client.get("/api/health").json()["submission"]
    assert health["configuration_permits"] is False
    assert sstore.BLOCKER_NO_DURABLE_STORAGE in health["blockers"]

    response = _submit(client, EXPERIMENT_ID)
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "submission_unavailable"
    assert body["reason"] == sstore.BLOCKER_NO_DURABLE_STORAGE
    _assert_published_nothing(body)
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == set()
    for leak in ("PGHOST", "PGPASSWORD", "db.invalid", "somewhere_else", "Traceback"):
        assert leak not in response.text, leak


def test_a_database_that_refuses_the_connection_is_a_typed_503(armed, monkeypatch):
    """The half a configuration gate CANNOT catch: configured, named right, silent."""

    def refuse(env):
        raise dbw.WriteRefused("could not connect (OperationalError)")

    store = sstore.PostgresSubmissionStore(fake_env(), connect=refuse)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    _make()
    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "submission_unavailable"
    assert body["reason"] == "database_unavailable"
    # The refusal precedes materialisation, so this is also a negative control.
    _assert_published_nothing(body)
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == set()
    for leak in ("PGHOST", "PGPASSWORD", "db.invalid", "OperationalError", "Traceback"):
        assert leak not in response.text, leak


def test_a_database_that_stops_answering_mid_request_discloses_what_was_published(
    armed, monkeypatch
):
    """The same refusal on the far side of materialisation — so it must disclose.

    The preflight connects and answers; the write cannot. Two official records are on
    disk by then, and a 503 saying "nothing was published" would be the C1 defect
    wearing a different reason code.
    """
    db = FakeSubmissionConnection()
    calls = {"n": 0}

    def flaky(env):
        calls["n"] += 1
        if calls["n"] > 1:
            raise dbw.WriteRefused("could not connect (OperationalError)")
        return db

    store = sstore.PostgresSubmissionStore(fake_env(), connect=flaky)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    _make()

    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["reason"] == "database_unavailable"
    _assert_published(body, {EXPERIMENT_ID})
    assert db.is_empty()
    assert _artifacts(ws.load_experiment(EXPERIMENT_ID)) == {
        f"{EXPERIMENT_ID}.json",
        f"{EXPERIMENT_ID}.evidence.json",
    }


# =============================================================================
# 6. CONFLICTING EVIDENCE — recorded, disclosed, NEVER gating
# =============================================================================


def test_conflicting_evidence_is_recorded_and_disclosed_and_does_not_block(armed, wired, db):
    """A state ordinary editing produces and no surface can clear.

    ``_apply_run_field`` APPENDS a ``user_confirmation`` entry every time and never
    replaces one, and no route removes an evidence entry — so answering a question,
    noticing a typo and answering it again manufactures a conflict permanently.
    Gating on it would refuse the record forever for the act of fixing a mistake.
    """
    draft = ws._full_draft()
    address = "sample.sample_id"
    draft.setdefault("fields", {})[address] = field_value(
        "SYN-SECOND-ANSWER",
        status="verified",
        evidence=[
            user_confirmation("Sample id?", "SYN-FIRST-ANSWER", "2026-01-01T00:00:00Z"),
            user_confirmation("Sample id?", "SYN-SECOND-ANSWER", "2026-01-02T00:00:00Z"),
        ],
    )
    _make(draft=draft)

    units = ws.load_experiment(EXPERIMENT_ID).export_units()
    summary = submissions.conflict_summary(units)
    assert summary["conflicting_field_count"] >= 1, summary
    assert address in summary["affected_units"][0]["addresses"]

    response = _submit(_client(), EXPERIMENT_ID)
    assert response.status_code == 200, response.text
    disclosed = response.json()["conflict_summary"]
    assert disclosed["conflicting_field_count"] == summary["conflicting_field_count"]
    assert disclosed["gating"] == "disclosed_not_gated"
    # And it is on the ROW, not only in the response — a later reader must be able
    # to see that the submission was made over conflicting evidence.
    assert json.loads(db.submissions[0]["conflict_summary"])["conflicting_field_count"] >= 1


def test_the_conflict_summary_carries_addresses_and_never_values(armed, wired, db):
    """Scientific values live in the snapshot; a disclosure column carries navigation."""
    draft = ws._full_draft()
    draft.setdefault("fields", {})["sample.sample_id"] = field_value(
        "SYN-SECOND-ANSWER",
        status="verified",
        evidence=[
            user_confirmation("Sample id?", "SYN-FIRST-ANSWER", "2026-01-01T00:00:00Z"),
            user_confirmation("Sample id?", "SYN-SECOND-ANSWER", "2026-01-02T00:00:00Z"),
        ],
    )
    _make(draft=draft)
    assert _submit(_client(), EXPERIMENT_ID).status_code == 200
    stored = db.submissions[0]["conflict_summary"]
    assert "SYN-FIRST-ANSWER" not in stored and "SYN-SECOND-ANSWER" not in stored
    assert "sample.sample_id" in stored


# =============================================================================
# 7. THE CONTENT SIGNATURE
# =============================================================================


def test_the_signature_is_stable_across_materialisation(workspace):
    """THE PROPERTY THE WHOLE RECOVERY STORY RESTS ON.

    The route materialises artifacts, saves state, and THEN records the submission.
    A fault in that window leaves records on disk and no submission; the retry must
    compute the SAME signature or it would write a second submission for one act.
    Materialisation sets ``record_id`` and bumps ``rev`` and ``updated_utc``, so the
    signature has to exclude all three — and this is where that is checked.
    """
    exp = _make()
    before = submissions.content_signature(exp.id, exp.export_units())
    for unit in exp.export_units():
        unit.mark_exported(unit.target_id)
    exp.save_versioned()
    reloaded = ws.load_experiment(EXPERIMENT_ID)
    assert reloaded.rev > exp.rev or reloaded.record_id is not None
    assert submissions.content_signature(reloaded.id, reloaded.export_units()) == before


def test_the_signature_moves_when_a_field_value_moves(workspace):
    exp = _make()
    before = submissions.content_signature(exp.id, exp.export_units())
    address = next(iter(exp.draft["fields"]))
    exp.draft["fields"][address]["value"] = "something else"
    exp.save_versioned()
    reloaded = ws.load_experiment(EXPERIMENT_ID)
    assert submissions.content_signature(reloaded.id, reloaded.export_units()) != before


def test_the_signature_does_not_move_when_only_the_title_moves(workspace):
    """A DOCUMENTED EXCLUSION, asserted so it cannot be lost by accident.

    A record's title is workspace metadata and reaches no official record, so
    renaming and re-submitting publishes nothing new and is not a second submission.
    That is the honest answer, and it is the one exclusion a reader might expect to
    go the other way — which is why it is pinned rather than left in prose.
    """
    exp = _make()
    before = submissions.content_signature(exp.id, exp.export_units())
    exp.title = "renamed entirely"
    exp.save_versioned()
    reloaded = ws.load_experiment(EXPERIMENT_ID)
    assert submissions.content_signature(reloaded.id, reloaded.export_units()) == before


def test_the_signature_does_not_move_when_two_runs_are_reordered(workspace):
    """``sorted_runs`` orders on ``(ordinal, created_utc, id)``; records do not.

    Reordering two runs changes that sequence without changing a single official
    record, so a signature that moved on a reorder would refuse a re-submission of
    byte-identical content.
    """
    exp = _make()
    run_draft = copy.deepcopy(exp.draft)
    exp = ws.load_experiment(EXPERIMENT_ID)
    exp.add_run(label="A", draft=copy.deepcopy(run_draft))
    exp.add_run(label="B", draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    exp = ws.load_experiment(EXPERIMENT_ID)
    before = submissions.content_signature(exp.id, exp.export_units())
    first, second = exp.sorted_runs()
    first.ordinal, second.ordinal = second.ordinal, first.ordinal
    exp.save_versioned()
    reloaded = ws.load_experiment(EXPERIMENT_ID)
    assert [r.label for r in reloaded.sorted_runs()] == ["B", "A"]
    assert submissions.content_signature(reloaded.id, reloaded.export_units()) == before


# =============================================================================
# 8. MCP, AND THE CAPABILITY DISCLOSURE
# =============================================================================


def test_no_mcp_tool_can_reach_the_new_submit_path(armed):
    """Structurally impossible, and the new path is checked against the same policy.

    ``mcp/policy.py`` refuses ``submit`` as a TOKEN at import time, in both the tool
    name and the path template, so this is not a list that has to be maintained —
    but the new route is a new path, and asserting it is refused by the shipped
    policy is what makes that claim about THIS path rather than about the idea of
    one.
    """
    from isaac_api.mcp import policy

    # The tool name is refused by token, whatever else it is called.
    assert policy.forbidden_tool_reason("submit_experiment")
    assert policy.forbidden_tool_reason("isaac_finalise_record")
    # No allowlisted operation reaches it, and no operation targeting it can be
    # declared at all: `_validated` runs at IMPORT and raises on the path token, so
    # adding one is not a change that ships broken — it is a change that cannot be
    # imported.
    assert all("submit" not in op.path_template for op in policy.OPERATIONS.values())
    smuggled = policy.Operation(
        id="isaac_finish",
        method="POST",
        path_template="/api/experiments/{experiment_id}/submit",
        scope=policy.Scope.DRAFT_WRITE,
        summary="",
        mutates=True,
        requires_if_match=True,
    )
    with pytest.raises(RuntimeError) as excinfo:
        policy._validated((smuggled,))
    assert "forbidden path token" in str(excinfo.value)


def test_the_health_block_reports_both_blockers_and_never_claims_availability(
    workspace, monkeypatch
):
    body = _client().get("/api/health").json()["submission"]
    assert body["configuration_permits"] is False
    assert set(body["blockers"]) == {
        sstore.BLOCKER_NO_DURABLE_STORAGE,
        sstore.BLOCKER_NO_ATTRIBUTABLE_ACTOR,
    }
    assert body["actor_trust_basis"] is None
    assert body["verifier_id"] == "unconfigured"
    assert body["basis"] == "configuration_only"


def test_an_armed_deployment_discloses_the_fixture_basis_on_health(armed, monkeypatch):
    """An operator must be able to see this from the banner, not from the manifest.

    A deployment attributing on a test-fixture basis is attributing on something that
    is NOT proof anyone authenticated, and hiding that behind a green
    ``configuration_permits`` would be the kind of comfortable falsehood this
    project's health surfaces have been corrected for before.
    """
    monkeypatch.setenv("PGHOST", "db.invalid")
    monkeypatch.setenv("PGDATABASE", "metadata_assistant")
    body = _client().get("/api/health").json()["submission"]
    assert body["actor_trust_basis"] == identity.TRUST_BASIS_TEST_FIXTURE
    assert body["verifier_id"] == identity.FIXTURE_VERIFIER
    assert sstore.BLOCKER_NO_ATTRIBUTABLE_ACTOR not in body["blockers"]

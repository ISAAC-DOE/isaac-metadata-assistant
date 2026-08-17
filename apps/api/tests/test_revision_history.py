"""The revision-history READ surface, and the derived submission lifecycle.

THE ONE CLAIM THIS FILE EXISTS TO PROTECT, and it is the first section below:
**"this record has no submitted revisions" and "this server could not find out"
are different answers, and this API never gives the first when the second is
true.** Migrations ``0003_revisions`` and ``0004_submissions`` are applied by an
operator, separately from the image rollout, and on the hosted deployment they
have not been applied at all — so a running build meeting a database without the
history tables is the NORMAL case, not an edge case. An empty ``revisions: []``
there would be a lie with a plausible shape.

The second claim, and the reason Part B exists at all: **`submitted` is never
derived from `exported`.** Export is a mechanical transform any caller can perform;
submission is a declaration by a person. ``workflow.derive_lifecycle`` has no
``exported`` parameter, which is asserted here rather than described.

HOW THE HAPPY PATH IS REACHABLE, since the default build refuses every submission:
exactly the two seams ``test_submission.py`` uses — ``ISAAC_EDGE_TRUST_VERIFIER=
test_fixture`` with a subject, and ``submission_store.store`` monkeypatched to the
in-process connection double in ``submission_fake.py``. The real transaction
machinery runs; only the server is fake. The READ path is bound to the SAME
double, so a listing that disagreed with what the write path actually wrote would
fail here. ``PGHOST`` stays unset, so experiments themselves keep using the
filesystem repository.

Nothing here reads real data and nothing here opens a database connection.
"""

from __future__ import annotations

import ast
import copy
import inspect
import json
from pathlib import Path

import pytest

import isaac_api.db_write as dbw
import isaac_api.identity as identity
import isaac_api.revision_history as rhist
import isaac_api.submission_store as sstore
import isaac_api.submissions as submissions
import isaac_api.workflow as workflow
import isaac_api.workspace as ws
from isaac_records.models import field_value, user_confirmation

from conftest import tutorial_client
# The export-ready seed draft SPLIT into its experiment-level and run-level halves
# using the application's OWN classifiers. Imported rather than re-derived: a second
# copy of that split would be a second definition that could drift from the one the
# product uses, and these tests would then pass while the composition was wrong.
from test_export_fan_out import _split_full_draft
from submission_fake import (
    FAKE_CREATED_UTC,
    FakeSubmissionConnection,
    fake_reader,
    fake_store,
)

ACTOR = "ada.lovelace"
EXPERIMENT_ID = "01HISTORYFIXTURE0000000001"

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
    """Point BOTH the write store and the read reader at the same double."""
    store = fake_store(db)
    reader = fake_reader(db)
    monkeypatch.setattr(sstore, "store", lambda env=None: store)
    monkeypatch.setattr(rhist, "reader", lambda env=None: reader)
    return store


@pytest.fixture()
def no_tables(monkeypatch):
    """A deployment WITH a database whose history tables have not been created.

    This is the hosted deployment's actual state today, which is why it is a named
    fixture rather than an inline detail of one test.
    """
    conn = FakeSubmissionConnection(tables=False)
    monkeypatch.setattr(rhist, "reader", lambda env=None: fake_reader(conn))
    monkeypatch.setattr(sstore, "store", lambda env=None: fake_store(conn))
    return conn


def _client():
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _make(experiment_id: str = EXPERIMENT_ID, *, draft=None):
    """An export-ready, run-free experiment — the shape every record here has."""
    exp = ws.create_experiment(
        "Revision history fixture",
        {"kind": "synthetic"},
        copy.deepcopy(draft) if draft is not None else ws._full_draft(),
        id=experiment_id,
    )
    exp.save_versioned()
    return ws.load_experiment(experiment_id)


def _make_fan_out(*, labels: tuple[str, ...], experiment_id: str = EXPERIMENT_ID):
    """An experiment whose runs each export their own official record.

    A run created with an EMPTY draft is not submittable — it inherits the record's
    fields but not its blocks, so its composed draft has no `descriptors` and the
    official schema refuses it. That is correct behaviour and is why the halves are
    split with the product's own classifiers rather than by hand.
    """
    experiment_draft, run_draft = _split_full_draft()
    exp = ws.create_experiment(
        "Revision history fan-out fixture",
        {"kind": "synthetic"},
        experiment_draft,
        id=experiment_id,
    )
    for label in labels:
        exp.add_run(label=label, draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    return ws.load_experiment(experiment_id)


#: The one field these tests edit to make a record's content differ. A record-level
#: string with user-confirmation evidence, so the edited record stays export-ready —
#: an edit that broke the export gate would change the lifecycle state as a side
#: effect and make the test mean something else.
_EDITED_ADDRESS = "sample.material.name"


def _edit(value: str, experiment_id: str = EXPERIMENT_ID):
    exp = ws.load_experiment(experiment_id)
    before = (exp.draft["fields"].get(_EDITED_ADDRESS) or {}).get("value")
    exp.draft["fields"][_EDITED_ADDRESS] = field_value(
        value,
        status="verified",
        evidence=[user_confirmation("Material name?", value, "2026-01-01T00:00:00Z")],
    )
    exp.save_versioned()
    return before


def _etag(client, experiment_id: str = EXPERIMENT_ID) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _submit(client, experiment_id: str = EXPERIMENT_ID):
    return client.post(
        f"/api/experiments/{experiment_id}/submit",
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _revisions(client, experiment_id: str = EXPERIMENT_ID):
    return client.get(f"/api/experiments/{experiment_id}/revisions")


def _revision(client, revision_no: int, experiment_id: str = EXPERIMENT_ID):
    return client.get(f"/api/experiments/{experiment_id}/revisions/{revision_no}")


def _diff(client, revision_no: int, experiment_id: str = EXPERIMENT_ID):
    return client.get(f"/api/experiments/{experiment_id}/revisions/{revision_no}/diff")


# =============================================================================
# 1. THE READ MODULE'S OWN INVENTORY — every statement is a SELECT
# =============================================================================


def _read_module_statements() -> dict[str, str]:
    """Every module-level ``Q_*`` in ``revision_history``, parsed from SOURCE.

    Source rather than attributes, for the reason
    ``test_submission_store._module_statements`` gives: a constant assembled at run
    time is exactly how someone would slip past a scan over module attributes.
    """
    path = Path(rhist.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or not target.id.startswith("Q_"):
                continue
            resolved = getattr(rhist, target.id, None)
            assert isinstance(resolved, str), target.id
            out[target.id] = resolved
    return out


def test_every_statement_in_the_read_module_is_a_select():
    """The property the module docstring claims, asserted rather than described.

    It is a STRONGER property than the append-only guarantee
    ``test_submission_store`` enforces globally (which forbids only ``UPDATE`` and
    ``DELETE`` naming a history table), and it is only cheap to state because this
    module has no other kind of statement in it. An ``INSERT`` added here would
    fail this test even though the global scan would let it through.
    """
    statements = _read_module_statements()
    assert statements, "the scan found no statements at all"
    for name, sql in statements.items():
        lowered = " ".join(sql.lower().split())
        assert lowered.startswith("select "), f"{name} is not a SELECT: {sql[:80]}"
        for verb in ("insert ", "update ", "delete ", "create ", "drop "):
            assert verb not in lowered, f"{name} contains {verb!r}"


def test_every_read_statement_passes_the_owned_tables_policy():
    """The other direction: an over-broad refusal filter would break the feature.

    It is not a formality. ``db_write.WriteStatementPolicy`` treats ``on`` as a
    table introducer, so a JOIN written the obvious way — ``JOIN isaac_submissions s
    ON s.revision_id = …`` — is REFUSED because the alias reads as a table this
    application does not own. That refusal is why this module issues no joins, and
    this test is what would catch a future one.
    """
    for name, sql in _read_module_statements().items():
        assert dbw.WriteStatementPolicy().check(sql) == sql.strip(), name


def test_a_join_written_the_obvious_way_really_is_refused():
    """Guards the paragraph above: the constraint it cites is real, not folklore."""
    with pytest.raises(dbw.WriteRefused):
        dbw.WriteStatementPolicy().check(
            "SELECT r.revision_id FROM isaac_experiment_revisions r"
            " JOIN isaac_submissions s ON s.revision_id = r.revision_id"
        )


# =============================================================================
# 2. THE REFUSAL THAT MATTERS — "cannot know" is never rendered as "nothing"
# =============================================================================


@pytest.mark.parametrize("path", ["", "/1", "/1/diff"])
def test_tables_absent_is_a_typed_refusal_and_never_an_empty_list(
    armed, no_tables, path
):
    """THE SINGLE MOST IMPORTANT TEST IN THIS SLICE.

    ``0003``/``0004`` are not applied to the hosted database, so this is the state
    that deployment is in RIGHT NOW. The three properties asserted are, in order:
    the answer is a refusal and not a listing; the rows key is ABSENT rather than
    empty, so there is nothing an unwary client could read as "no revisions"; and
    the message says out loud that this is not a statement about the record.
    """
    _make()
    client = _client()
    response = client.get(f"/api/experiments/{EXPERIMENT_ID}/revisions{path}")
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "revision_history_unavailable"
    assert body["availability"]["state"] == "unavailable"
    assert body["availability"]["reason"] == "tables_absent"
    # NOT `[]`. Absent.
    assert "revisions" not in body, body
    assert "total" not in body, body
    assert "changes" not in body, body
    assert "not a statement that this record has never been submitted" in (
        body["availability"]["message"]
    )


@pytest.mark.parametrize("path", ["", "/1", "/1/diff"])
def test_no_database_configured_is_a_typed_refusal_and_never_an_empty_list(
    armed, monkeypatch, path
):
    """A deployment with no application database at all. Same rule, different cause."""
    monkeypatch.setattr(rhist, "reader", lambda env=None: None)
    _make()
    response = _client().get(f"/api/experiments/{EXPERIMENT_ID}/revisions{path}")
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["availability"]["reason"] == "no_durable_storage"
    assert "revisions" not in body, body
    assert "which is not the same as this record never having been submitted" in (
        body["availability"]["message"]
    )


@pytest.mark.parametrize("path", ["", "/1", "/1/diff"])
def test_a_database_that_does_not_answer_is_a_typed_refusal_not_a_500(
    armed, monkeypatch, path
):
    """A configured database that refuses the connection.

    503 AND NOT 500. ``db_write.WriteRefused`` has no handler registered anywhere in
    ``create_app``, so an uncaught one is a bare 500 with a traceback in the server
    log — which is what the submit route was corrected for (review item I1) and what
    a READ operation must never do at all.
    """

    class Refusing:
        def history(self, *a, **k):
            raise dbw.WriteRefused("could not connect (OperationalError)")

        def revision(self, *a, **k):
            raise dbw.WriteRefused("could not connect (OperationalError)")

    monkeypatch.setattr(rhist, "reader", lambda env=None: Refusing())
    _make()
    response = _client().get(f"/api/experiments/{EXPERIMENT_ID}/revisions{path}")
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["availability"]["reason"] == "database_unavailable"
    assert "revisions" not in body, body


def test_a_missing_psycopg2_is_also_a_refusal_rather_than_a_500(armed, monkeypatch):
    """``MissingDependency`` is caught here even though ``post_submit`` does not.

    The divergence is deliberate and is argued at ``routes._HISTORY_READ_FAILURES``:
    a read operation in this application must never 500.
    """

    class Broken:
        def history(self, *a, **k):
            raise dbw.MissingDependency("psycopg2 is not importable")

    monkeypatch.setattr(rhist, "reader", lambda env=None: Broken())
    _make()
    response = _revisions(_client())
    assert response.status_code == 503, response.text
    assert response.json()["availability"]["reason"] == "database_unavailable"


def test_the_refusal_names_no_host_path_credential_or_driver_message(armed, no_tables):
    _make()
    text = _revisions(_client()).text
    for leak in ("PGHOST", "PGPASSWORD", "db.invalid", "/private/tmp", "Traceback"):
        assert leak not in text, leak


def test_an_available_history_with_no_revisions_IS_an_empty_list_and_says_so(
    armed, wired
):
    """The other direction — without which the guard above would be vacuous.

    A record that really has never been submitted, on a deployment that really can
    read its own history, gets ``revisions: []`` and an availability message saying
    that an empty list here means what it looks like it means.
    """
    _make()
    response = _revisions(_client())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["availability"]["state"] == "available"
    assert body["availability"]["reason"] is None
    assert body["revisions"] == []
    assert body["total"] == 0
    assert "An empty list" in body["availability"]["message"]


def test_a_worked_example_record_is_not_applicable_rather_than_unavailable(workspace):
    """A FACT, not an inability, and it must never be reported as either the other.

    A worked-example session is refused by ``post_submit`` outright, so such a record
    cannot have a submission history. No database is consulted to establish that,
    which is why the state is ``not_applicable`` and the answer is ``200``.
    """
    from isaac_api.app import create_app

    client = tutorial_client(create_app(), raise_server_exceptions=False)
    response = _revisions(client, ws.SEED_READY_ID)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["availability"]["state"] == "not_applicable"
    assert body["availability"]["reason"] == "worked_example_session"
    assert "revisions" not in body, body
    assert body["lifecycle"]["submission"]["known"] is True
    assert body["lifecycle"]["submission"]["submitted_for_current_content"] is False


def test_an_unknown_record_is_404_before_any_history_question(armed, wired):
    response = _revisions(_client(), "01NOSUCHEXPERIMENT00000000")
    assert response.status_code == 404
    assert response.json()["error"] == "experiment_not_found"


# =============================================================================
# 3. THE HAPPY PATHS — list, fetch, diff
# =============================================================================


def _submitted_once(client):
    """One submitted revision over the standard export-ready fixture."""
    _make()
    response = _submit(client)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_submitted_revision_is_listed_with_its_submission_and_actor(armed, wired, db):
    client = _client()
    recorded = _submitted_once(client)
    body = _revisions(client).json()

    assert body["availability"]["state"] == "available"
    assert body["total"] == 1
    assert body["returned"] == 1
    row = body["revisions"][0]
    assert row["revision_no"] == 1
    assert row["revision_id"] == recorded["revision_id"]
    assert row["reason"] == sstore.REASON_SUBMISSION
    assert row["created_utc"] == FAKE_CREATED_UTC
    assert row["content_signature"] == recorded["content_signature"]
    assert row["actor"] == {
        "subject": ACTOR,
        "trust_basis": identity.TRUST_BASIS_TEST_FIXTURE,
        "attributed": True,
    }
    assert row["submission"]["submission_id"] == recorded["submission_id"]
    assert row["submission"]["unit_count"] == recorded["unit_count"]
    assert row["submission"]["idempotency_key_used"] is False
    # And the listing agrees with what the WRITE path actually put in the double.
    assert len(db.revisions) == 1 and len(db.submissions) == 1


def test_the_listing_is_newest_first_and_states_how_many_exist(armed, wired):
    client = _client()
    _submitted_once(client)
    # A second submission needs different content: the signature is the natural
    # idempotency key, so re-submitting identical content is refused by design.
    _edit("Second material")
    assert _submit(client).status_code == 200

    body = _revisions(client).json()
    assert [r["revision_no"] for r in body["revisions"]] == [2, 1]
    assert body["total"] == 2
    assert body["current_submission"]["submission_id"] == (
        body["revisions"][0]["submission"]["submission_id"]
    )


def test_one_revision_reads_back_with_its_runs_changes_and_submission(armed, wired):
    client = _client()
    _make_fan_out(labels=("Run A", "Run B"))
    assert _submit(client).status_code == 200, _submit(client).text

    response = _revision(client, 1)
    assert response.status_code == 200, response.text
    revision = response.json()["revision"]
    assert revision["revision_no"] == 1
    assert [r["label"] for r in revision["run_revisions"]] == ["Run A", "Run B"]
    assert all(r["created_utc"] == FAKE_CREATED_UTC for r in revision["run_revisions"])
    # A FIRST revision has NO predecessor, so it records no changes at all — which
    # is not the same as having changed nothing. `changes_scope` says what the rows
    # would have covered.
    assert revision["changes"] == []
    assert revision["changes_scope"] == "draft_field_values_only"
    assert {r["unit_id"] for r in revision["submission_runs"]} == {
        run.id for run in ws.load_experiment(EXPERIMENT_ID).sorted_runs()
    }


def test_a_second_revision_records_the_addresses_that_changed(armed, wired):
    client = _client()
    _submitted_once(client)
    _edit("Second material")
    assert _submit(client).status_code == 200

    revision = _revision(client, 2).json()["revision"]
    changed = {(c["address"], c["change_kind"]) for c in revision["changes"]}
    assert (_EDITED_ADDRESS, "modified") in changed
    assert revision["change_counts"].get("modified") == 1


def test_a_revision_whose_submission_row_is_gone_is_paired_with_NOTHING(
    armed, wired, db
):
    """`submission: null` must mean "there is no submission row", exactly.

    THE FIRST VERSION OF THE LISTING COULD NOT PROMISE THAT. It read every
    submission for the experiment under the same ``LIMIT`` as the revisions, ordered
    by ``submitted_utc``, and paired the two lists in Python — so a revision inside
    the revision window whose submission fell outside the submission window would
    have been reported with no submission, and the UI's sentence "no submission row
    is recorded against this snapshot" would have been false about a submission that
    exists. The listing now reads each revision's submission by its own unique key,
    so the pairing is exact; this asserts the property that fix buys, on the one
    state that can produce a genuine ``None``.
    """
    client = _client()
    _submitted_once(client)
    assert _revisions(client).json()["revisions"][0]["submission"] is not None
    # A psql session could remove the submission and leave the snapshot. Nothing in
    # this application can, which is why the double is what produces the state.
    db.submissions.clear()
    row = _revisions(client).json()["revisions"][0]
    assert row["submission"] is None
    # The revision itself is still listed and still counted — dropping it would make
    # the listing disagree with `total` for a reason no reader could see.
    assert row["revision_no"] == 1
    assert _revisions(client).json()["total"] == 1


def test_the_detail_body_never_carries_the_stored_record_snapshot(armed, wired, db):
    """The revision holds a whole experiment document. It never leaves the process.

    Asserted three ways, because one way is easy to satisfy by accident: the
    revision object carries no ``state`` and no ``draft`` key at any depth; the
    stored document's own serialised text does not appear in the response; and the
    reader DID fetch it (otherwise the test would pass against a route that could
    not have leaked it because it never had it).

    ``availability.state`` is a different thing wearing the same word, which is why
    the scan is scoped to the revision object rather than run over the whole body.
    """
    client = _client()
    _submitted_once(client)
    body = _revision(client, 1).json()

    def _forbidden_keys(node):
        if isinstance(node, dict):
            assert "state" not in node, node.keys()
            assert "draft" not in node, node.keys()
            for value in node.values():
                _forbidden_keys(value)
        elif isinstance(node, list):
            for value in node:
                _forbidden_keys(value)

    _forbidden_keys(body["revision"])
    stored = json.loads(db.revisions[0]["state"])
    assert stored.get("draft"), "the fixture must actually have a stored draft"
    assert json.dumps(stored["draft"]) not in json.dumps(body)
    # The reader really did read the column — so the absence above is the route
    # withholding it, not the query never having asked for it.
    assert rhist.Q_REVISION_BY_NO in {sql for sql, _p in db.statements}


def test_a_revision_number_this_record_does_not_have_is_404_not_503(armed, wired):
    """Three different answers, never merged: no record / no revision / cannot look."""
    client = _client()
    _submitted_once(client)
    response = _revision(client, 7)
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"] == "revision_not_found"
    assert body["revision_no"] == 7


def test_revision_zero_is_refused_by_the_path_contract(armed, wired):
    _make()
    assert _client().get(f"/api/experiments/{EXPERIMENT_ID}/revisions/0").status_code == 422


def test_the_diff_reports_the_field_that_changed_with_both_values(armed, wired):
    client = _client()
    _submitted_once(client)
    before = _edit("Edited material")

    response = _diff(client, 1)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["comparable"] is True
    assert body["content_signature_matches"] is False
    changed = {c["address"]: c for c in body["changes"]}
    assert changed[_EDITED_ADDRESS]["change_kind"] == "modified"
    assert changed[_EDITED_ADDRESS]["previous_value"] == before
    assert changed[_EDITED_ADDRESS]["current_value"] == "Edited material"
    assert body["change_counts"]["modified"] >= 1
    assert body["units"]["comparable"] is True
    assert body["units"]["added"] == [] and body["units"]["removed"] == []


def test_an_unedited_record_diffs_to_nothing_and_the_signatures_match(armed, wired):
    client = _client()
    _submitted_once(client)
    body = _diff(client, 1).json()
    assert body["changes"] == []
    assert body["content_signature_matches"] is True


def test_adding_a_run_shows_as_a_unit_addition_and_not_only_as_field_rows(armed, wired):
    """The same event at two altitudes, and the surface gets both.

    ``address_changes`` contributes one ``added`` row per field the new run holds,
    which is true and is not the sentence a reader wants first.
    """
    client = _client()
    _make_fan_out(labels=("Run A",))
    assert _submit(client).status_code == 200
    _, run_draft = _split_full_draft()
    exp = ws.load_experiment(EXPERIMENT_ID)
    exp.add_run(label="Run B", draft=copy.deepcopy(run_draft))
    exp.save_versioned()
    added = ws.load_experiment(EXPERIMENT_ID).sorted_runs()[-1].id

    body = _diff(client, 1).json()
    assert body["units"]["added"] == [added]
    assert body["units"]["removed"] == []
    assert body["current_run_labels"][added] == "Run B"


def test_a_snapshot_that_cannot_be_rehydrated_degrades_rather_than_failing(
    armed, wired, db
):
    """``comparable: false`` and NO ``changes`` key — never an empty list.

    An empty list would assert a comparison this server did not make. The stored
    document is corrupted directly in the double, which is the only way to reach a
    historical row this build cannot read.
    """
    client = _client()
    _submitted_once(client)
    db.revisions[0]["state"] = json.dumps({"not": "an experiment"})

    body = _diff(client, 1).json()
    assert body["comparable"] is False
    assert "changes" not in body, body
    assert "could not be read back" in body["comparable_note"]
    assert body["units"]["comparable"] is False


# =============================================================================
# 4. THE DERIVED LIFECYCLE
# =============================================================================


def _lifecycle(client, experiment_id: str = EXPERIMENT_ID) -> dict:
    response = _revisions(client, experiment_id)
    return response.json()["lifecycle"]


def test_derive_lifecycle_has_no_exported_parameter(armed):
    """STRUCTURAL, not a comment. `submitted` cannot be derived from `exported`.

    A future edit inside ``derive_lifecycle`` cannot reach for an ``exported``
    signal, because the function is never handed one. The same check covers
    ``artifact``, ``record_id`` and anything else that describes publication rather
    than declaration.
    """
    names = set(inspect.signature(workflow.derive_lifecycle).parameters)
    assert names == {
        "pending_count",
        "failing_unit_count",
        "submitted_known",
        "submitted_for_current_content",
        "submission_unknown_reason",
    }, names


def test_an_unanswered_record_reads_draft(armed, wired):
    """A record with an unanswered blocker. `draft` is the "still filling this in" state."""
    draft = copy.deepcopy(ws._full_draft())
    draft.setdefault("pending", []).append(
        {"key": "sample.sample_id", "question": "Which sample was this?"}
    )
    _make(draft=draft)
    assert ws.load_experiment(EXPERIMENT_ID).pending_count() > 0
    lifecycle = _lifecycle(_client())
    assert lifecycle["state"] == "draft"
    assert lifecycle["label"] == "Draft"
    assert lifecycle["scientific_readiness"]["pending_count"] > 0


def test_an_answered_record_that_still_fails_the_gate_reads_needs_review(armed, wired):
    """``ws._review_draft`` — every question answered, the official schema refuses.

    This is the state where there is nothing left to fill in and something left to
    look at, and it is derived entirely from ``blocker_report``'s own two numbers.
    """
    _make(draft=ws._review_draft())
    lifecycle = _lifecycle(_client())
    assert lifecycle["state"] == "needs_review"
    assert lifecycle["scientific_readiness"]["pending_count"] == 0
    assert lifecycle["scientific_readiness"]["failing_unit_count"] >= 1
    assert lifecycle["scientific_readiness"]["failing_units"], lifecycle


def test_a_ready_unsubmitted_record_reads_ready_to_submit(armed, wired):
    _make()
    lifecycle = _lifecycle(_client())
    assert lifecycle["state"] == "ready_to_submit"
    assert lifecycle["scientific_readiness"]["blocked"] is False
    assert lifecycle["submission"]["known"] is True
    assert lifecycle["submission"]["submitted_for_current_content"] is False


def test_a_submitted_record_reads_submitted_for_exactly_that_content(armed, wired):
    client = _client()
    _submitted_once(client)
    assert _lifecycle(client)["state"] == "submitted"

    # EDIT IT, and it stops being submitted AS IT STANDS. "Has ever been submitted"
    # would be a different and much less useful claim, and would tell a scientist
    # their current draft is on record when it is not.
    _edit("Edited material")
    after = _lifecycle(client)
    assert after["state"] == "ready_to_submit"
    assert after["submission"]["submitted_for_current_content"] is False


def test_an_exported_but_unsubmitted_record_is_NOT_submitted(armed, wired, db):
    """Exporting is not a declaration by anyone, and must never read as one."""
    client = _client()
    _make()
    exported = client.post(
        f"/api/experiments/{EXPERIMENT_ID}/export",
        headers={"If-Match": _etag(client)},
    )
    assert exported.status_code == 200, exported.text
    assert ws.load_experiment(EXPERIMENT_ID).all_units_exported() is True

    lifecycle = _lifecycle(client)
    assert lifecycle["state"] != "submitted", lifecycle
    assert lifecycle["state"] == "ready_to_submit"
    assert lifecycle["submission"]["submitted_for_current_content"] is False
    # And nothing reached the history tables.
    assert db.is_empty()


def test_a_ready_record_with_no_trusted_actor_still_reads_ready_to_submit(
    workspace, wired
):
    """THE CASE THE BRIEFING NAMES, and the one this design exists for.

    No verifier is configured — which is EVERY deployment shipped today — so
    ``POST .../submit`` would refuse with ``409 human_actor_required``. The record's
    science is finished all the same, and infrastructure must never be allowed to
    describe it as unfinished. The reason it cannot be submitted is reported under
    its own name, beside the state rather than inside it.
    """
    _make()
    lifecycle = _lifecycle(_client())
    assert lifecycle["state"] == "ready_to_submit"
    blocked = lifecycle["submission_blocked_by_deployment"]
    assert blocked["blocked"] is True
    assert sstore.BLOCKER_NO_ATTRIBUTABLE_ACTOR in blocked["blockers"]
    assert blocked["actor_trust_basis"] is None
    assert blocked["basis"] == "configuration_only"
    assert "says nothing about whether this record is ready" in blocked["message"]
    # The refusal it predicts is the refusal the submit route actually gives.
    refused = _submit(_client())
    assert refused.status_code == 409
    assert refused.json()["error"] == "human_actor_required"


def test_an_unreadable_history_leaves_the_state_scientific_and_says_it_is_unknown(
    armed, no_tables
):
    """It never falls back to "not submitted", because that was not observed."""
    _make()
    body = _revisions(_client()).json()
    lifecycle = body["lifecycle"]
    assert lifecycle["state"] == "ready_to_submit"
    assert lifecycle["submission"]["known"] is False
    assert lifecycle["submission"]["submitted_for_current_content"] is None
    assert lifecycle["submission"]["unknown_reason"] == "tables_absent"
    assert any(r["code"] == "submission_state_unknown" for r in lifecycle["reasons"])


def test_deployment_blockers_never_change_the_lifecycle_state(armed, wired, monkeypatch):
    """The two are computed from disjoint inputs, asserted directly on the pure fn.

    ``derive_lifecycle`` is handed no deployment signal at all, so the property is
    that the same scientific inputs produce the same state whatever the deployment
    can do. Asserted here over the derivation rather than over one route response,
    because it is a property of the derivation.
    """
    for known, submitted in ((True, False), (False, None)):
        ready = workflow.derive_lifecycle(
            pending_count=0,
            failing_unit_count=0,
            submitted_known=known,
            submitted_for_current_content=submitted,
        )
        assert ready["state"] == "ready_to_submit"
    assert workflow.LIFECYCLE_ORDER == (
        "draft",
        "needs_review",
        "ready_to_submit",
        "submitted",
    )


# =============================================================================
# 5. ACTOR HONESTY — a row nobody vouched for is rendered as exactly that
# =============================================================================


def test_an_unattributed_revision_names_nobody_and_invents_no_placeholder(
    workspace, wired, db, monkeypatch
):
    """The row a deployment with no verifier would write, read back honestly.

    It is written through the STORE rather than the route, deliberately: the route
    refuses an unattributable caller (409), which is correct, and is exactly why
    such a row cannot be produced over HTTP in this build. The row shape is the one
    the database admits — ``CHECK ((trust_basis = 'unattributed') = (subject IS
    NULL))`` — and the fake enforces that CHECK too, so a row with a name and this
    basis could not be created here even deliberately.
    """
    exp = _make()
    units = exp.export_units()
    for unit in units:
        unit.mark_exported(unit.target_id)
    store = fake_store(db)
    store.record_submission(
        exp=exp,
        units=units,
        content_signature=submissions.content_signature(exp.id, units),
        conflict_summary={},
        subject=None,
        trust_basis=submissions.TRUST_BASIS_UNATTRIBUTED,
        idempotency_key=None,
    )

    body = _revisions(_client()).json()
    row = body["revisions"][0]
    assert row["actor"] == {
        "subject": None,
        "trust_basis": "unattributed",
        "attributed": False,
    }
    # NO PLACEHOLDER ANYWHERE. Not "system", not "unknown", not the deployment name.
    text = json.dumps(body).lower()
    for invented in ("system", "unknown user", "anonymous", "n/a", "isaac user"):
        assert invented not in text, invented


def test_a_fixture_attributed_row_says_what_its_attribution_is_worth(armed, wired):
    """``test_fixture`` is a real shipped basis and is not proof anyone authenticated.

    The surface is handed the basis rather than a flattened "attributed", for the
    same reason ``submission_store.capability`` publishes ``actor_trust_basis`` on
    ``/api/health``.
    """
    client = _client()
    _submitted_once(client)
    row = _revisions(client).json()["revisions"][0]
    assert row["actor"]["trust_basis"] == identity.TRUST_BASIS_TEST_FIXTURE
    assert row["actor"]["trust_basis"] != identity.TRUST_BASIS_VERIFIED_EDGE_ASSERTION


# =============================================================================
# 6. THE EXISTING WORKFLOW IS UNCHANGED
# =============================================================================


def test_derive_workflow_keeps_its_five_step_contract_and_its_signature():
    """Additive means additive. ``derive_workflow`` was not touched."""
    assert workflow.CANONICAL_ORDER == (
        "load_record",
        "complete_metadata",
        "review_evidence",
        "review_export_readiness",
        "export",
    )
    assert set(inspect.signature(workflow.derive_workflow).parameters) == {
        "pending_count",
        "draft_ok",
        "ready",
        "exported",
        "rev",
    }
    derived = workflow.derive_workflow(
        pending_count=0, draft_ok=True, ready=True, exported=False, rev=3
    )
    assert set(derived) == {"ordered_steps", "current_step", "record_rev"}
    assert [s["id"] for s in derived["ordered_steps"]] == list(workflow.CANONICAL_ORDER)
    assert derived["current_step"] == "export"
    assert derived["record_rev"] == 3


def test_the_record_detail_payload_gained_no_lifecycle_key(armed, wired):
    """The lifecycle is served by the history operation, not bolted onto every read.

    A lifecycle on ``GET /experiments/{id}`` would make every detail read open a
    database connection, and would give two surfaces two chances to disagree. It is
    deliberately in ONE place.
    """
    client = _client()
    _make()
    detail = client.get(f"/api/experiments/{EXPERIMENT_ID}").json()
    assert "lifecycle" not in detail, detail.keys()
    assert set(detail["workflow"]) == {"ordered_steps", "current_step", "record_rev"}


# =============================================================================
# 7. THE PURE COMPARISON FUNCTIONS — no drift from the stored change rows
# =============================================================================


def _envelope(value):
    return {"value": value, "status": "verified", "evidence": []}


_DRAFT_MATRIX = [
    None,
    {},
    {"fields": None},
    {"fields": {}},
    {"fields": {"a": _envelope(1)}},
    {"fields": {"a": _envelope("1")}},
    {"fields": {"a": _envelope(None), "b": _envelope(0)}},
    {"fields": {"a": _envelope(False), "b": _envelope([1, 2])}},
    {"fields": {"a": _envelope({"k": "v"}), "": _envelope("skipped")}},
    {"fields": {"a": "not an envelope", "b": _envelope("kept")}},
]


@pytest.mark.parametrize("draft", _DRAFT_MATRIX)
def test_present_field_values_is_field_values_carrying_the_raw_value(draft):
    """One presence rule, restated in one place and pinned here.

    If the two ever diverge this fails, rather than a diff quietly disagreeing with
    the change rows stored beside it.
    """
    raw = submissions.present_field_values(draft)
    canonical = {
        key: submissions.canonical_json(value) for key, value in raw.items()
    }
    assert canonical == submissions.field_values(draft)


def _unit_maps():
    a = _DRAFT_MATRIX[4]
    b = _DRAFT_MATRIX[5]
    c = _DRAFT_MATRIX[7]
    return [
        (None, {}),
        (None, {"U1": a}),
        ({}, {}),
        ({"U1": a}, {"U1": a}),
        ({"U1": a}, {"U1": b}),
        ({"U1": a}, {"U1": c}),
        ({"U1": a}, {}),
        ({}, {"U1": a}),
        ({"U1": a, "U2": c}, {"U2": c, "U3": b}),
    ]


@pytest.mark.parametrize("previous,current", _unit_maps())
def test_address_value_changes_projects_exactly_onto_address_changes(previous, current):
    """The value-carrying diff and the stored change rows describe the same set.

    They are written out separately — the write path is left untouched — so the
    equality is bought with this test rather than with a refactor of a durable
    write path.
    """
    rich = submissions.address_value_changes(previous, current)
    projection = [(c["unit_id"], c["address"], c["change_kind"]) for c in rich]
    assert projection == submissions.address_changes(previous, current)


def test_a_missing_baseline_yields_no_changes_rather_than_everything_added():
    assert submissions.address_value_changes(None, {"U1": _DRAFT_MATRIX[4]}) == []
    membership = submissions.unit_membership_changes(None, {"U1": {}})
    assert membership == {
        "comparable": False,
        "added": [],
        "removed": [],
        "unchanged": [],
    }


def test_unit_membership_changes_reports_both_directions():
    assert submissions.unit_membership_changes({"A": {}, "B": {}}, {"B": {}, "C": {}}) == {
        "comparable": True,
        "added": ["C"],
        "removed": ["A"],
        "unchanged": ["B"],
    }


# =============================================================================
# 8. THE READER ITSELF — no connection is ever opened without PGHOST
# =============================================================================


def test_the_reader_is_none_without_a_configured_database(monkeypatch):
    monkeypatch.delenv("PGHOST", raising=False)
    assert rhist.reader({}) is None


def test_the_reader_gate_is_the_same_function_the_write_path_uses():
    """Equivalence with the write path, asserted rather than assumed.

    A deployment that cannot record a submission is exactly a deployment that
    cannot read one back, and two copies of the condition could drift.
    """
    source = Path(rhist.__file__).read_text(encoding="utf-8")
    assert "repo._postgres_available(env)" in source
    store_source = Path(sstore.__file__).read_text(encoding="utf-8")
    assert "repo._postgres_available(env)" in store_source


def test_the_history_read_issues_only_the_statements_it_declares(armed, wired, db):
    """Every statement that reached the double is one this application declares.

    Together with the SELECT-only inventory above, this is what makes "the history
    read writes nothing" a checked property rather than a claim.
    """
    client = _client()
    _submitted_once(client)
    db.statements.clear()
    assert _revisions(client).status_code == 200
    declared = set(_read_module_statements().values()) | {
        sstore.Q_TABLE_PRESENT,
        sstore.Q_SUBMISSION_BY_SIGNATURE,
        dbw.Q_SET_STATEMENT_TIMEOUT,
        dbw.Q_SET_LOCK_TIMEOUT,
        dbw.Q_CURRENT_DATABASE,
    }
    issued = {sql for sql, _params in db.statements}
    assert issued <= declared, issued - declared
    assert db.commits >= 1 and db.rollbacks == 0
    # And nothing was written.
    assert len(db.revisions) == 1 and len(db.submissions) == 1


# =============================================================================
# REGRESSION FROM INDEPENDENT REVIEW — the "a read must never 500" invariant was
# only true of the two exceptions the CONNECTION layer raises.
# =============================================================================


class _DriverError(Exception):
    """Stands in for psycopg2's `OperationalError` / `QueryCanceled` / `UndefinedColumn`.

    A distinct class, not `WriteRefused`: the point of the test below is that the
    catch used to be keyed on `db_write`'s own two exception types, and NOTHING
    wraps an error raised by `cursor.execute`. `write_transaction` catches
    `BaseException`, rolls back, and re-raises unchanged.
    """


@pytest.mark.parametrize("path", ["", "/1", "/1/diff"])
def test_a_DRIVER_error_mid_query_is_a_refusal_and_not_a_500(armed, monkeypatch, path):
    """The gap the three existing failure tests could not see.

    They raise `WriteRefused`/`MissingDependency` from a stub — the two types
    raised at exactly four CONNECTION sites. Every other reachable failure came
    from `cursor.execute` and escaped as an undeclared 500: the server dropping
    the connection mid-transaction, a pooler rejecting `SET LOCAL`, an
    administrator cancelling the query, a `lock_timeout` firing, or a drifted
    `0003` where `to_regclass` resolves the relation but a column is missing —
    which `_tables_present` is relation-level and cannot detect.

    500 is not in this operation's declared contract, the frontend's envelope
    reader rejects it, and the raw driver message — which echoes the host, the
    user and the connection string — reached the log.

    MUTATION: narrow `_HISTORY_READ_FAILURES` back to
    `(WriteRefused, MissingDependency)` and every parameterization goes RED.
    """

    class ExplodingMidQuery:
        def history(self, *a, **k):
            raise _DriverError("server closed the connection unexpectedly\nhost=db.invalid")

        def revision(self, *a, **k):
            raise _DriverError("server closed the connection unexpectedly\nhost=db.invalid")

        def diff(self, *a, **k):
            raise _DriverError("server closed the connection unexpectedly\nhost=db.invalid")

    monkeypatch.setattr(rhist, "reader", lambda env=None: ExplodingMidQuery())
    _make()
    response = _client().get(f"/api/experiments/{EXPERIMENT_ID}/revisions{path}")

    assert response.status_code == 503, response.text
    body = response.json()
    assert body["availability"]["reason"] == "database_unavailable"
    # Never an empty list: "could not read" is not "there are none".
    assert "revisions" not in body, body
    # And the driver's message — which carries the host — must not be echoed.
    assert "db.invalid" not in response.text
    assert "Traceback" not in response.text


def test_the_unreachable_lead_names_no_cause_it_cannot_know(armed, monkeypatch):
    """The copy must not blame the network for a failure that was not the network.

    It used to say the database "did not accept the connection", which was true
    of the two connection exceptions and false of everything the widened catch
    now covers. Naming the wrong cause is worse than naming none: it sends an
    operator to the network when the answer is in the code.
    """

    class ExplodingMidQuery:
        def history(self, *a, **k):
            raise _DriverError("canceling statement due to statement timeout")

    monkeypatch.setattr(rhist, "reader", lambda env=None: ExplodingMidQuery())
    _make()
    message = _revisions(_client()).json()["availability"]["message"]

    assert "did not accept the connection" not in message
    # What it must still say, in substance.
    assert "not a statement that this record has never been submitted" in message


def test_a_refusal_still_carries_the_records_ETag(armed, no_tables):
    """The version is knowable on a refusal path, so withholding it was an accident.

    `list_revisions` sets `response.headers["ETag"]` on the injected `Response`,
    but that only reaches a body FastAPI serialises itself. Every refusal path
    returns a `JSONResponse` directly, and FastAPI does not merge the injected
    headers into one — so the ETag was dropped on exactly the paths this
    deployment always takes. `tables_absent` is its current state, so it was
    never emitted at all.

    The experiment loaded fine; it is the HISTORY that could not be read.

    MUTATION: drop the `etag=` keyword at the call sites and this goes RED.
    """
    _make()
    response = _revisions(_client())
    assert response.status_code == 503, response.text
    assert response.headers.get("ETag"), "a refusal must still say which version it refused for"


def test_the_single_revision_routes_do_not_describe_a_list_they_do_not_return():
    """`HISTORY_READ_NOTE`'s second sentence is about a list.

    It was served on all three operations, including the two that return ONE
    revision and a diff — "an empty list here means this record has no submitted
    revisions", in a body with no list in it. Not user-visible today, because the
    UI reads `availability.message` only on the non-available branches; a false
    sentence in the contract's own response body all the same.
    """
    from isaac_api.routes import HISTORY_READ_NOTE, HISTORY_READ_NOTE_SINGLE

    assert "empty list" in HISTORY_READ_NOTE
    assert "empty list" not in HISTORY_READ_NOTE_SINGLE

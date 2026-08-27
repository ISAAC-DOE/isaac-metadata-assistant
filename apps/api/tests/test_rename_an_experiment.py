"""A scientist can correct what they named an experiment.

WHY THIS FILE EXISTS
====================

Until ``PATCH /api/experiments/{experiment_id}`` shipped, ``title`` was written
exactly ONCE — by ``POST /api/experiments`` — and no operation could change it.
``0001_experiments`` is applied to the hosted database, so every mistakenly created
experiment was permanent, with its typo. Nothing in the repository named that
absence, and nothing tested it, because there was no route to test.

Every test here therefore FAILS on ``origin/main``, and the first one fails for the
reason that matters: on ``origin/main`` the method is not routed at all and the
server answers ``405``. That is asserted explicitly rather than left implied, so a
reader can see what this file is a regression guard against.

WHAT IT DELIBERATELY DOES NOT COVER
===================================

**Discard.** A scientist still cannot remove an experiment they created. That is not
an omission this file papers over: ``CLAUDE.md`` §15's 2026-08-07 write lift
enumerates, per table, what writing each one covers, and every one of those
enumerations is an INSERT or an UPSERT — the five submission-lifecycle tables for
"writing them through ``submission_store.py``'s append-only ``INSERT``s",
``isaac_run_projection`` for "the ONE statement ``Q_UPSERT_RUN_PROJECTION``". No
committed sentence permits a ``DELETE`` against any of them, so the slice that would
have shipped one could not establish its authorization basis and stopped.

**The free-text note.** ``POST /api/experiments`` accepts a ``description`` and
stores it at ``source.description`` — which ``workspace.classify_experiment`` also
reads as the provenance marker that decides whether a record belongs to the managed
demo dataset. The rename refuses that key outright rather than putting a text box
over a deletion classifier, and :func:`test_the_note_is_not_editable_here` pins the
refusal AND that the stored note is untouched by it.

EVERYTHING IS SYNTHETIC. No file outside the test's own ``tmp_path`` workspace is
read or written, and no database connection is opened (``PGHOST`` is deleted by
every fixture).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import tutorial_client

# The interleaving seam and the thread runner are IMPORTED rather than re-declared,
# for the reason `test_lifecycle_concurrency` gives: a second copy of
# `_LockRendezvous` would be a second definition of "these two requests overlapped",
# free to drift from the one `test_handler_concurrency` maintains.
from test_handler_concurrency import (  # noqa: E402
    _LockRendezvous,
    _outcome,
    _race,
)
from test_lifecycle_concurrency import _assert_raced  # noqa: E402

TYPO = "Cu K-edge, first attemt"
FIXED = "Cu K-edge, first attempt"
#: A title neither writer may be able to claim silently. Distinct enough that
#: `assert LOSER not in json.dumps(state)` is a real statement.
LOSER = "zzz-loser-title-4711"


# =============================================================================
# fixtures
# =============================================================================


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """The real app over a throwaway workspace, in ORDINARY scope.

    No worked-example header, so ``scope`` is ``None`` — which is the only scope
    this operation acts in. ``raise_server_exceptions=False`` matches every other
    HTTP-level file here: a handler that raised surfaces as a 500 response whose
    code an assertion states, rather than as an exception that names the wrong
    problem.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def example(tmp_path, monkeypatch):
    """A client inside a worked-example session, for the tutorial-isolation tests."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


# =============================================================================
# helpers — reads used for ASSERTIONS ONLY, never to perform a mutation
# =============================================================================


def _create(client, title: str = TYPO, **body) -> tuple[str, str]:
    response = client.post("/api/experiments", json={"title": title, **body})
    assert response.status_code == 201, response.text
    return response.json()["id"], response.headers["ETag"]


def _rename(client, experiment_id: str, etag: str | None, **body):
    headers = {} if etag is None else {"If-Match": etag}
    return client.patch(f"/api/experiments/{experiment_id}", json=body, headers=headers)


def _persisted(experiment_id: str):
    """The stored document, read from the workspace — never the response body."""
    exp = ws.load_experiment(experiment_id)
    assert exp is not None, f"{experiment_id} is gone"
    return exp


def _snapshot(exp) -> dict:
    """Everything about a record that a RENAME must not move."""
    return {
        "id": exp.id,
        "created_utc": exp.created_utc,
        "generation": exp.generation,
        "source": exp.source,
        "draft": exp.draft,
        "answer_log": exp.answer_log,
        "record_id": exp.record_id,
        "runs": [r.to_state() for r in exp.sorted_runs()],
        "notes": [n.to_state() for n in exp.notes],
    }


# =============================================================================
# 1. the route exists at all — the whole point of the slice
# =============================================================================


def test_the_method_is_routed(client):
    """On ``origin/main`` this is a ``405``: no ``PATCH`` was published on the path.

    Asserted as its own test, before any behaviour, so the regression this file
    guards is legible without reading the rest of it.
    """
    experiment_id, etag = _create(client)
    response = _rename(client, experiment_id, etag, title=FIXED)
    assert response.status_code != 405, (
        "PATCH is not routed on /api/experiments/{id} — a scientist cannot rename"
    )
    assert response.status_code == 200, response.text


def test_the_operation_is_published_with_a_written_summary(client):
    from isaac_api.app import create_app

    spec = create_app().openapi()
    operation = spec["paths"]["/api/experiments/{experiment_id}"]["patch"]
    assert operation["summary"] == "Rename an Experiment"
    # The three response codes a client has to branch on are declared, not just
    # returned. A caller writes its retry loop from the spec.
    for code in ("400", "412", "428", "409", "422"):
        assert code in operation["responses"], (
            f"{code} is returned but not declared: {sorted(operation['responses'])}"
        )


# =============================================================================
# 2. the happy path, and the version contract underneath it
# =============================================================================


def test_a_typo_can_be_corrected(client):
    experiment_id, etag = _create(client)
    response = _rename(client, experiment_id, etag, title=FIXED)

    assert response.status_code == 200, response.text
    assert response.json()["title"] == FIXED
    assert _persisted(experiment_id).title == FIXED


def test_the_title_is_stripped_not_stored_padded(client):
    experiment_id, etag = _create(client)
    assert _rename(client, experiment_id, etag, title=f"  {FIXED}  ").status_code == 200
    assert _persisted(experiment_id).title == FIXED


def test_a_rename_advances_the_revision_and_moves_the_etag(client):
    """``title`` is inside ``_authoritative_signature``, so it MUST move the token.

    This is the assertion the unverified snapshot branch failed: it called
    ``exp.save()`` rather than ``_save_versioned``, which rewrote the document and
    left ``rev`` — and therefore the ``ETag`` — exactly where it was. A second client
    holding the pre-rename validator would then have passed its own precondition and
    silently overwritten the rename, which is the precise loss the precondition
    exists to prevent.
    """
    experiment_id, etag = _create(client)
    before = _persisted(experiment_id)

    response = _rename(client, experiment_id, etag, title=FIXED)

    assert response.status_code == 200, response.text
    after = _persisted(experiment_id)
    assert after.rev == before.rev + 1
    assert after.generation == before.generation, "a rename is not a re-creation"
    assert response.headers["ETag"] == after.etag()
    assert response.headers["ETag"] != etag
    assert response.json()["version"] == after.version_token()


def test_resending_the_same_title_writes_nothing_and_leaves_the_etag_alone(client):
    experiment_id, etag = _create(client)
    renamed = _rename(client, experiment_id, etag, title=FIXED)
    assert renamed.status_code == 200, renamed.text
    settled = renamed.headers["ETag"]
    before = _persisted(experiment_id)

    again = _rename(client, experiment_id, settled, title=FIXED)

    assert again.status_code == 200, again.text
    assert again.headers["ETag"] == settled, "a no-op re-entry churned the validator"
    after = _persisted(experiment_id)
    assert after.rev == before.rev
    assert after.updated_utc == before.updated_utc


def test_if_match_star_is_accepted(client):
    experiment_id, _ = _create(client)
    response = _rename(client, experiment_id, "*", title=FIXED)
    assert response.status_code == 200, response.text
    assert _persisted(experiment_id).title == FIXED


def test_a_rename_moves_nothing_else_about_the_record(client):
    experiment_id, etag = _create(client)
    before = _snapshot(_persisted(experiment_id))

    assert _rename(client, experiment_id, etag, title=FIXED).status_code == 200

    assert _snapshot(_persisted(experiment_id)) == before


# =============================================================================
# 3. the If-Match contract — 428 / 400 / 412, and NOTHING written by any of them
# =============================================================================


def test_absent_if_match_is_428_and_writes_nothing(client):
    experiment_id, _ = _create(client)

    response = _rename(client, experiment_id, None, title=FIXED)

    assert response.status_code == 428, response.text
    assert response.json()["error"] == "precondition_required"
    assert _persisted(experiment_id).title == TYPO


@pytest.mark.parametrize(
    "header",
    [
        pytest.param('W/"x.0"', id="weak-validator"),
        pytest.param(",", id="reduces-to-no-tags"),
        pytest.param("not-quoted", id="unquoted"),
        pytest.param("", id="empty"),
    ],
)
def test_a_malformed_if_match_is_400_and_writes_nothing(client, header):
    experiment_id, _ = _create(client)

    response = _rename(client, experiment_id, header, title=FIXED)

    assert response.status_code == 400, response.text
    assert response.json()["error"] == "malformed_if_match"
    assert _persisted(experiment_id).title == TYPO


def test_a_stale_if_match_is_412_writes_nothing_and_echoes_the_current_etag(client):
    experiment_id, stale = _create(client)
    assert _rename(client, experiment_id, stale, title=FIXED).status_code == 200
    current = _persisted(experiment_id).etag()

    response = _rename(client, experiment_id, stale, title=LOSER)

    assert response.status_code == 412, response.text
    body = response.json()
    assert body["error"] == "stale_write"
    assert response.headers["ETag"] == current
    exp = _persisted(experiment_id)
    assert exp.title == FIXED
    assert LOSER not in json.dumps(exp.to_state())


def test_the_loser_can_refresh_and_retry_in_one_hop(client):
    """The 412 has to be actionable, not merely correct.

    Re-read → re-apply → retry must converge, which is the whole reason the refusal
    echoes the current validator.
    """
    experiment_id, stale = _create(client)
    assert _rename(client, experiment_id, stale, title=FIXED).status_code == 200

    refused = _rename(client, experiment_id, stale, title="Cu K-edge, run 1")
    assert refused.status_code == 412

    retried = _rename(
        client, experiment_id, refused.headers["ETag"], title="Cu K-edge, run 1"
    )
    assert retried.status_code == 200, retried.text
    assert _persisted(experiment_id).title == "Cu K-edge, run 1"


# =============================================================================
# 4. what the body may say
# =============================================================================


@pytest.mark.parametrize(
    "title",
    [pytest.param("", id="empty"), pytest.param("   ", id="whitespace-only")],
)
def test_a_blank_title_is_refused_and_writes_nothing(client, title):
    """A record always has a name. ``min_length=1`` accepts a string of spaces."""
    experiment_id, etag = _create(client)

    response = _rename(client, experiment_id, etag, title=title)

    assert response.status_code == 422, response.text
    assert _persisted(experiment_id).title == TYPO


def test_a_body_naming_no_title_is_refused(client):
    experiment_id, etag = _create(client)
    response = client.patch(
        f"/api/experiments/{experiment_id}", json={}, headers={"If-Match": etag}
    )
    assert response.status_code == 422, response.text
    assert _persisted(experiment_id).title == TYPO


def test_the_note_is_not_editable_here(client):
    """``description`` is refused, and the stored note is untouched by the refusal.

    This is the slice's one deliberate asymmetry with the create form, and it is a
    boundary rather than an oversight: ``source.description`` is what
    ``ws.classify_experiment`` reads as proof that this application generated a
    record from its own committed fixtures, and ``managed_legacy`` is the one bucket
    ``ws.remove_experiment`` will delete. A rename does not write a deletion
    classifier.
    """
    note = "Second attempt after the beam trip."
    experiment_id, etag = _create(client, description=note)
    assert _persisted(experiment_id).source["description"] == note

    response = _rename(client, experiment_id, etag, title=FIXED, description="anything")

    assert response.status_code == 422, response.text
    exp = _persisted(experiment_id)
    assert exp.title == TYPO, "a refused body renamed the record anyway"
    assert exp.source["description"] == note


@pytest.mark.parametrize("key", ["id", "rev", "draft", "record_id", "runs"])
def test_any_other_field_is_refused_outright(client, key):
    experiment_id, etag = _create(client)

    response = _rename(client, experiment_id, etag, title=FIXED, **{key: "x"})

    assert response.status_code == 422, response.text
    assert _persisted(experiment_id).title == TYPO


def test_a_title_longer_than_create_accepts_is_refused(client):
    """The cap MATCHES create's exactly. A stricter rename would leave a title this
    application accepted impossible to correct, which is what this route exists to
    fix."""
    experiment_id, etag = _create(client)
    assert _rename(client, experiment_id, etag, title="a" * 200).status_code == 200
    settled = _persisted(experiment_id).etag()
    assert _rename(client, experiment_id, settled, title="a" * 201).status_code == 422


def test_an_unknown_id_is_404(client):
    response = _rename(client, "01NOSUCHEXPERIMENT00000000", "*", title=FIXED)
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"


# =============================================================================
# 5. tutorial isolation — §15's invariant, which this route must not become a
#    fourth way into
# =============================================================================


def test_a_worked_example_cannot_be_renamed(example):
    listed = example.get("/api/experiments").json()["experiments"]
    assert listed, "the worked-example session seeded nothing"
    experiment_id = listed[0]["id"]
    detail = example.get(f"/api/experiments/{experiment_id}")
    before = detail.json()["title"]

    response = example.patch(
        f"/api/experiments/{experiment_id}",
        json={"title": "renamed example"},
        headers={"If-Match": detail.headers["ETag"]},
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "ordinary_scope_required"
    after = example.get(f"/api/experiments/{experiment_id}").json()["title"]
    assert after == before


def test_the_scope_refusal_precedes_the_precondition(example):
    """A tutorial client is refused BEFORE it is told to send an ``If-Match``.

    The other ordering would answer ``428`` — an instruction to fetch and resend a
    validator for a write this operation was never going to accept.
    """
    experiment_id = example.get("/api/experiments").json()["experiments"][0]["id"]

    response = example.patch(
        f"/api/experiments/{experiment_id}", json={"title": "renamed example"}
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "ordinary_scope_required"


def test_the_route_reaches_no_removal_or_seeding_path(client, monkeypatch):
    """Named rather than reasoned about: a rename calls neither.

    ``ws.remove_experiment`` has exactly one caller — the guarded demo reset — and
    this slice does not become a second. The seeding path is watched for the same
    reason: a rename must not materialise a canonical example into the ordinary
    workspace.
    """
    calls: list[str] = []
    for name in ("remove_experiment", "seed_if_empty"):
        if hasattr(ws, name):
            real = getattr(ws, name)
            monkeypatch.setattr(
                ws,
                name,
                lambda *a, _n=name, _r=real, **k: (calls.append(_n), _r(*a, **k))[1],
            )

    experiment_id, etag = _create(client)
    assert _rename(client, experiment_id, etag, title=FIXED).status_code == 200

    assert calls == []


# =============================================================================
# 6. a rename never asks anyone to re-export
# =============================================================================


def test_renaming_an_exported_record_leaves_its_artifact_current(client):
    """The route's own description makes this claim, so it is measured, not asserted.

    ``dependencies.artifact_state`` compares record CONTENT rather than ``rev``, and
    ``title`` reaches no exported record — so bumping the revision for a rename must
    not flip a `current` artifact to `stale`. If it did, correcting a typo would
    demand a re-export of a record whose scientific content did not change.
    """
    experiment_id, etag = _create(client)
    # The committed export-ready draft, taken from the application's own fixture
    # rather than hand-written, so this cannot pass against a draft the product
    # would not itself produce.
    exp = _persisted(experiment_id)
    exp.draft = ws._full_draft()
    exp.save()

    ready = client.get(f"/api/experiments/{experiment_id}")
    assert ready.json()["pending_count"] == 0, ready.text
    exported = client.post(
        f"/api/experiments/{experiment_id}/export",
        json={},
        headers={"If-Match": ready.headers["ETag"]},
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True, exported.text

    detail = client.get(f"/api/experiments/{experiment_id}")
    assert detail.json()["artifact"]["state"] == "current", detail.text

    renamed = _rename(client, experiment_id, detail.headers["ETag"], title=FIXED)

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["artifact"]["state"] == "current", renamed.text
    assert renamed.json()["title"] == FIXED


# =============================================================================
# 7. two concurrent clients — the CAS gate under a real race
# =============================================================================


def test_two_concurrent_renames_on_one_token_leave_exactly_one_winner(
    client, monkeypatch
):
    """Both writers hold the SAME validator and overlap at the record lock.

    The rendezvous guarantees the property every assertion rests on: whatever each
    request loaded before it reached the lock, it loaded before either could hold
    the lock. A handler that checked its precondition OUTSIDE the lock would fail
    here on every run rather than one in a thousand.

    WHICH writer wins is the scheduler's to decide and is not pinned. What is pinned
    holds in both orderings: exactly one 200, exactly one 412, ONE revision bump, and
    the loser's title nowhere in the stored document.
    """
    experiment_id, shared = _create(client)
    before = _persisted(experiment_id)

    rendezvous = _LockRendezvous(monkeypatch, experiment_id)
    responses = _race(
        [
            lambda: _rename(client, experiment_id, shared, title=FIXED),
            lambda: _rename(client, experiment_id, shared, title=LOSER),
        ]
    )
    _assert_raced(rendezvous, None, experiment_id)

    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 412], _outcome(responses)

    winner = next(r for r in responses if r.status_code == 200)
    loser = next(r for r in responses if r.status_code == 412)
    assert loser.json()["error"] == "stale_write"

    exp = _persisted(experiment_id)
    assert exp.rev == before.rev + 1, "two writes landed, or none did"
    assert exp.title == winner.json()["title"]
    assert exp.etag() == winner.headers["ETag"]
    # The refused writer's value is nowhere in the document — not in the title, not
    # in the source, not in the answer log.
    refused_title = LOSER if exp.title == FIXED else FIXED
    if refused_title == LOSER:
        assert LOSER not in json.dumps(exp.to_state())
    # And the loser's echoed validator is the winner's, so its retry converges.
    assert loser.headers["ETag"] == exp.etag()


def test_a_concurrent_rename_and_run_add_do_not_lose_each_other(client, monkeypatch):
    """A rename racing a STRUCTURAL write, both holding the same record validator.

    They touch disjoint parts of one document, which is exactly when a lost update is
    easiest to ship: nothing about the two payloads collides, so only the shared
    validator stands between them. Adding a run is chosen as the partner because it
    is the other record-ETag-gated mutation a brand-new experiment can accept, and
    because it moves a DIFFERENT key of the same signature. Exactly one is refused.
    """
    experiment_id, shared = _create(client)

    rendezvous = _LockRendezvous(monkeypatch, experiment_id)
    responses = _race(
        [
            lambda: _rename(client, experiment_id, shared, title=FIXED),
            lambda: client.post(
                f"/api/experiments/{experiment_id}/runs",
                json={"label": LOSER},
                headers={"If-Match": shared},
            ),
        ]
    )
    _assert_raced(rendezvous, None, experiment_id)

    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 412] or codes == [200, 412], _outcome(responses)

    exp = _persisted(experiment_id)
    assert exp.rev == 1, "both writes landed on one validator, or neither did"
    if responses[0].status_code == 200:
        assert exp.title == FIXED
        assert exp.runs == []
        assert LOSER not in json.dumps(exp.to_state())
    else:
        assert exp.title == TYPO
        assert [r.label for r in exp.runs] == [LOSER]

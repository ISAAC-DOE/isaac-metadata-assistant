"""An ordinary record survives the ENTIRE worked-example lifecycle, untouched.

WHY A SEPARATE FILE FROM ``test_tutorial_scope.py``. That file establishes the
structure: the examples live in ``<workspace>/_tutorial/<session id>/``, ordinary
enumeration excludes that namespace, and an unknown session 404s. This file asks the
question a reader actually cares about — *if I have work in My Experiments, can any
part of the walkthrough touch it?* — and answers it by BUILDING ordinary records in
every state this build can produce, running the whole lifecycle over them, and
comparing them byte for byte afterwards.

WHAT "UNTOUCHED" MEANS HERE, stated so it cannot quietly shrink. For every ordinary
record the following are captured before and compared after: its id, its persisted
state file's exact bytes (which carries the title, source, draft, answer log,
``record_id``, ``rev``, ``updated_utc`` and generation), the full API detail bundle,
the pending-question list, the evidence trail, the workflow, the exported-artifact
state, and the bytes of any exported record and evidence-sidecar file on disk.

THE LIFECYCLE RUN OVER THEM IS THE REAL ONE, not a subset: open a session, read it,
run the worked example inside it, preview AND execute the guarded reset inside it, then
discard the session. Every one of those is a WRITE in the session's scope, and two of
them (``/demo/run``, ``/demo/reset``) are the operations that used to write into the
ordinary workspace.

``create_experiment`` is used to build the ordinary records. It has no production
caller — this build cannot create a record, which is exactly why the ordinary workspace
is empty in practice — so it is a test-only constructor, and using it is the only way to
test the property at all. That is a deliberate choice, not a shortcut around a route.

Everything is synthetic: the committed reference fixtures, through the unchanged truth
core. No real data, no network, no database.
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api.routes import TUTORIAL_SESSION_HEADER

from conftest import tutorial_client


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def plain(app) -> TestClient:
    """A client with NO session header: the ordinary workspace."""
    return TestClient(app)


# --- building ordinary records in every state this build can reach -------------


def _raw_draft() -> dict:
    """A real extracted draft from the committed reference files (5 blockers open)."""
    return ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH)


def _full_draft() -> dict:
    """The same draft with every committed answer applied (0 blockers)."""
    import copy

    return ws.apply_answers(_raw_draft(), copy.deepcopy(ws.load_demo_answers()))


def _make_ordinary(title: str, draft: dict, *, managed_legacy: bool = False) -> str:
    """One ordinary record, and return its id.

    ``managed_legacy`` gives it the provenance marker the reset classifier reads, with
    a NON-canonical id — the shape the reset would remove *if it were in the reset's
    scope*. It is deliberately included: a record that the destructive path would
    otherwise be willing to delete is the strongest case for "the ordinary workspace is
    not in that path's scope at all".
    """
    source = (
        {"description": ws.MANAGED_SOURCE_DESCRIPTION, "files": list(ws.SOURCE_FILES)}
        if managed_legacy
        else {"description": "hand-authored, for a preservation test", "files": []}
    )
    return ws.create_experiment(title=title, source=source, draft=draft).id


def _artifact_bytes(exp_id: str) -> dict[str, str]:
    """Every file under this record's directory, path -> text. Empty when it has none."""
    root = ws.scope_root(None) / exp_id
    if not root.is_dir():
        return {}
    return {
        str(p.relative_to(root)): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _snapshot(plain: TestClient, exp_id: str) -> dict:
    """Everything about one ordinary record that must not move."""
    detail = plain.get(f"/api/experiments/{exp_id}")
    assert detail.status_code == 200, detail.text
    files = _artifact_bytes(exp_id)
    # A guard against a VACUOUS comparison: an empty snapshot would compare equal to
    # another empty snapshot, so a record that had been deleted outright would pass
    # every `before == after` assertion in this file.
    assert "experiment.json" in files, (
        f"{exp_id} has no persisted state file, so a snapshot comparison over it would "
        f"prove nothing. Files found: {sorted(files)}"
    )
    return {
        "id": exp_id,
        "files": files,
        "detail": detail.json(),
        "etag": detail.headers.get("etag"),
        "pending": plain.get(f"/api/experiments/{exp_id}/pending").json(),
        "evidence": plain.get(f"/api/experiments/{exp_id}/evidence").json(),
        "artifacts": plain.get(f"/api/experiments/{exp_id}/artifacts").json(),
        "draft": plain.get(f"/api/experiments/{exp_id}/draft").json(),
    }


def _confirm_one_answer(plain: TestClient, exp_id: str) -> tuple[str, object]:
    """Confirm ONE real blocking answer on an ordinary record, over HTTP.

    Returns the `(field, value)` that was confirmed, so a caller that wants to EDIT it
    afterwards names the field the record actually has an answer for.
    """
    detail = plain.get(f"/api/experiments/{exp_id}").json()
    pending = plain.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    assert pending, "expected the raw draft to have open blockers"
    answers = ws.load_demo_answers()
    target = next((p for p in pending if p["id"] in answers), None)
    assert target is not None, "no committed answer matches an open blocker"
    field, value = target["id"], answers[target["id"]]
    response = plain.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {field: value}, "confirmed_by_user": True},
        headers={"If-Match": f'"{detail["version"]}"'},
    )
    assert response.status_code == 200, response.text
    return field, value


def _export(plain: TestClient, exp_id: str) -> None:
    """Export an ordinary record, over HTTP, so it really has written artifacts."""
    detail = plain.get(f"/api/experiments/{exp_id}").json()
    response = plain.post(
        f"/api/experiments/{exp_id}/export",
        headers={"If-Match": f'"{detail["version"]}"'},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True, response.text


def _build_ordinary_population(plain: TestClient) -> list[str]:
    """One ordinary record of EVERY kind the spec asks to be preserved.

    Returned in a fixed order so a failure names a specific kind rather than an index.

    THE SIXTH ENTRY IS A NAME COLLISION, and it is here because independent review
    found the first five could not detect one. Every one of them is titled
    ``"Ordinary · …"``, so none collides with anything the worked example creates —
    and a cleanup that identified the examples by TITLE instead of by SCOPE would have
    left all five untouched and passed this whole file. Production is correct today
    (disposal is a scope-rooted ``rmtree`` behind a direct-child guard, and the reset
    classifier reads provenance inside its own scope), so this closes a
    FIXTURE-COVERAGE hole rather than a live defect — but the hole is exactly the one
    a plausible future "tidy up the example records" change would fall into.
    """
    fresh = _make_ordinary("Ordinary · untouched draft", _raw_draft())
    confirmed = _make_ordinary("Ordinary · a confirmed answer", _raw_draft())
    _confirm_one_answer(plain, confirmed)
    edited = _make_ordinary("Ordinary · an edited field", _raw_draft())
    field, value = _confirm_one_answer(plain, edited)
    _edit_one_field(plain, edited, field, value)
    exported = _make_ordinary("Ordinary · exported record", _full_draft())
    _export(plain, exported)
    legacy = _make_ordinary(
        "Ordinary · managed-legacy provenance", _raw_draft(), managed_legacy=True
    )
    # Titled EXACTLY the base the five built-in examples are named from — the backend
    # builds theirs as f"{_SEED_TITLE_BASE} · <suffix>", so this is the strongest
    # collision available: a title-prefix rule, an exact-match rule and a
    # "startswith" rule would all claim it. It is an ORDINARY record with a
    # non-canonical id, in the ordinary scope, and it must survive untouched.
    seed_titled = _make_ordinary(ws._SEED_TITLE_BASE, _raw_draft())
    return [fresh, confirmed, edited, exported, legacy, seed_titled]


def _edit_one_field(plain: TestClient, exp_id: str, field: str, value: object) -> None:
    """Overwrite an ALREADY-CONFIRMED value, over HTTP, recording a fresh confirmation.

    The edit route recognises only fields that have already been answered — which is the
    whole point of the affordance — so the caller passes the field it just confirmed.
    """
    detail = plain.get(f"/api/experiments/{exp_id}").json()
    response = plain.post(
        f"/api/experiments/{exp_id}/edit",
        json={"answers": {field: value}, "confirmed_by_user": True},
        headers={"If-Match": f'"{detail["version"]}"'},
    )
    assert response.status_code == 200, response.text


def _run_whole_tutorial_lifecycle(app) -> str:
    """Open a session, work inside it, reset inside it, discard it. Returns its id."""
    session = tutorial_client(app)
    sid = session.tutorial_session_id

    # Read it: the five examples are there.
    ids = [e["id"] for e in session.get("/api/experiments").json()["experiments"]]
    assert set(ids) == set(ws.CANONICAL_IDS)

    # Run the worked example inside the session (a write, in the session's scope).
    run = session.post("/api/demo/run", json={"mode": "draft_only"})
    assert run.status_code in (200, 409), run.text

    # Preview AND execute the guarded reset inside the session — the destructive path.
    preview = session.post("/api/demo/reset", json={"mode": "preview"})
    assert preview.status_code == 200, preview.text
    digest = preview.json()["plan_digest"]
    execute = session.post(
        "/api/demo/reset",
        json={
            "mode": "execute",
            "confirmation": "RESET EXAMPLE WORKSPACE",
            "plan_digest": digest,
        },
    )
    assert execute.status_code == 200, execute.text
    assert execute.json()["status"] == "ok", execute.text

    # Discard it.
    discarded = session.delete(f"/api/tutorial/sessions/{sid}")
    assert discarded.status_code == 204, discarded.text
    assert not ws.tutorial_session_exists(sid)
    return sid


# =============================================================================
# T16 · ordinary-record preservation across the whole lifecycle
# =============================================================================


def test_zero_ordinary_records_stay_zero_across_the_whole_lifecycle(app, plain):
    assert plain.get("/api/experiments").json() == {"experiments": []}
    _run_whole_tutorial_lifecycle(app)
    # Nothing appeared, and no directory was left where a record would be enumerated.
    assert plain.get("/api/experiments").json() == {"experiments": []}
    assert plain.get("/api/runtime/records").json() == {"records": [], "total": 0}
    assert ws.list_experiments(None) == []


def test_one_ordinary_record_is_byte_identical_across_the_whole_lifecycle(app, plain):
    exp_id = _make_ordinary("Ordinary · the only record", _raw_draft())
    before = _snapshot(plain, exp_id)

    _run_whole_tutorial_lifecycle(app)

    assert _snapshot(plain, exp_id) == before


@pytest.mark.parametrize("kind", [0, 1, 2, 3, 4, 5])
def test_every_kind_of_ordinary_record_is_byte_identical_across_the_lifecycle(
    app, plain, kind
):
    """Fresh / confirmed / edited / exported / managed-legacy / seed-titled.

    Parametrized rather than looped so a regression names the KIND that broke instead
    of failing once on whichever came first.

    ``kind == 5`` is the name collision — see ``_build_ordinary_population``. Without
    it "every kind" was a promise the fixtures did not keep: a cleanup that matched on
    TITLE rather than on scope would have passed all five other cases.
    """
    population = _build_ordinary_population(plain)
    exp_id = population[kind]
    before = _snapshot(plain, exp_id)
    # Sanity: the record really is in the state this case claims, so a preservation
    # assertion cannot pass over a record that was never in that state.
    detail = before["detail"]
    if kind == 0:
        assert detail["pending_count"] > 0 and not detail["exported"]
    if kind in (1, 2):
        assert detail["rev"] > 0 and detail["pending_count"] < 5
    if kind == 3:
        assert detail["exported"] is True and detail["record_id"]
        assert before["artifacts"]["record"] is not None
        assert before["artifacts"]["sidecar"] is not None
        assert any(p.endswith(".evidence.json") for p in before["files"])
    if kind == 4:
        assert ws.load_experiment(exp_id).source["description"] == (
            ws.MANAGED_SOURCE_DESCRIPTION
        )
    if kind == 5:
        # The collision really is one: same title as the examples' base, and NOT one
        # of the canonical ids. A test that asserted only the title would still pass
        # over a record that had quietly become canonical.
        assert detail["title"] == ws._SEED_TITLE_BASE
        assert exp_id not in ws.CANONICAL_IDS

    _run_whole_tutorial_lifecycle(app)

    assert _snapshot(plain, exp_id) == before


def test_multiple_ordinary_records_are_all_preserved_together(app, plain):
    population = _build_ordinary_population(plain)
    before = {exp_id: _snapshot(plain, exp_id) for exp_id in population}
    listed_before = plain.get("/api/experiments").json()

    _run_whole_tutorial_lifecycle(app)

    assert {exp_id: _snapshot(plain, exp_id) for exp_id in population} == before
    # The LIST is unchanged too — same ids, same order, same derived fields, and no
    # example record joined it.
    assert plain.get("/api/experiments").json() == listed_before
    assert set(population).isdisjoint(ws.CANONICAL_IDS)
    for row in listed_before["experiments"]:
        assert row["id"] not in ws.CANONICAL_IDS
        assert row["scenario"] is None


def test_a_managed_legacy_ordinary_record_is_not_removable_by_a_session_reset(app, plain):
    """The destructive path's own classifier never sees the ordinary workspace.

    A managed-legacy record is exactly what ``/demo/reset`` removes — inside its own
    scope. This asserts the scope boundary at the point it matters most: the record
    that the reset WOULD delete is still there afterwards, and the reset's own report
    never named it.
    """
    legacy = _make_ordinary(
        "Ordinary · managed-legacy provenance", _raw_draft(), managed_legacy=True
    )
    before = _snapshot(plain, legacy)

    session = tutorial_client(app)
    preview = session.post("/api/demo/reset", json={"mode": "preview"}).json()
    # The classification the operator would have read never mentions the ordinary record.
    assert legacy not in [r["id"] for r in preview["removable"]]
    assert preview["previous_count"] == len(ws.CANONICAL_IDS)
    execute = session.post(
        "/api/demo/reset",
        json={
            "mode": "execute",
            "confirmation": "RESET EXAMPLE WORKSPACE",
            "plan_digest": preview["plan_digest"],
        },
    )
    assert execute.status_code == 200, execute.text

    assert _snapshot(plain, legacy) == before


# =============================================================================
# T8 / T10 / T11 · ordinary aggregates and Project Memory exclude the examples
# =============================================================================


def test_ordinary_counts_and_statistics_exclude_the_examples(app, plain):
    """With a session OPEN and one ordinary record present, ordinary counts see one.

    `test_tutorial_scope.py` proves the ordinary aggregates survive an EMPTY workspace.
    This is the case that would catch a leak: if a scope boundary were a filter someone
    forgot, the ordinary totals would be 6 rather than 1.
    """
    exp_id = _make_ordinary("Ordinary · the only record", _raw_draft())
    session = tutorial_client(app)
    assert len(session.get("/api/experiments").json()["experiments"]) == len(
        ws.CANONICAL_IDS
    )

    ordinary_list = plain.get("/api/experiments").json()["experiments"]
    assert [row["id"] for row in ordinary_list] == [exp_id]

    # The Statistics page's one read.
    runtime = plain.get("/api/runtime/records").json()
    assert runtime["total"] == 1
    assert [r["experiment_id"] for r in runtime["records"]] == [exp_id]
    # ...and every filtered projection agrees.
    for params in (
        {"status": ws.NEEDS_ATTENTION},
        {"status": ws.DONE},
        {"has_conflict": True},
        {"workflow_state": "blocked"},
    ):
        body = plain.get("/api/runtime/records", params=params).json()
        assert all(r["experiment_id"] == exp_id for r in body["records"]), params
        assert body["total"] == len(body["records"]), params


def test_ordinary_search_excludes_the_examples(app, plain):
    exp_id = _make_ordinary("Ordinary · a searchable ordinary title", _raw_draft())
    tutorial_client(app)  # a session is open, holding five example records

    body = plain.get("/api/search", params={"q": "ordinary"}).json()
    hits = body["workspace"]["results"]
    assert [h["experiment_id"] for h in hits] == [exp_id]

    # The examples' own title base finds NOTHING in the ordinary scope, even though a
    # session holding five records with that exact title is open right now.
    example_hits = plain.get("/api/search", params={"q": "XANES Example"}).json()
    assert example_hits["workspace"]["results"] == []
    assert example_hits["workspace"]["total"] == 0
    for canonical in ws.CANONICAL_IDS:
        assert canonical not in json.dumps(example_hits)


def test_project_memory_never_names_an_example_record_in_either_scope(app, plain):
    """T11, answered precisely rather than assumed.

    Project Memory indexes the REPOSITORY (source, docs, schema, fixtures) from a
    committed snapshot; it does not index workspace records at all, so "excludes the
    examples" is true by construction rather than by a filter. That is worth pinning
    rather than asserting in prose: if a future slice ever fed workspace records into
    the memory plane, this fails.
    """
    session = tutorial_client(app)
    for client in (plain, session):
        for path in (
            "/api/memory/files",
            "/api/memory/concepts",
            "/api/memory/graph",
            "/api/graph/status",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
            payload = json.dumps(response.json())
            for canonical in ws.CANONICAL_IDS:
                assert canonical not in payload, f"{path} named {canonical}"
            assert ws._SEED_TITLE_BASE not in payload, path


# =============================================================================
# T18 · a scoped request cannot reach an ordinary record
# =============================================================================


def test_a_tutorial_scoped_request_cannot_reach_an_ordinary_record(app, plain):
    """The boundary in the OTHER direction, which nothing pinned before.

    `test_a_canonical_id_is_404_in_the_ordinary_workspace` covers ordinary -> example.
    This covers example -> ordinary: inside a session, an ordinary record's id must be
    a 404, on every read AND every write. Without it, a session could read — or worse,
    mutate — the reader's own records simply by knowing an id.
    """
    exp_id = _make_ordinary("Ordinary · not reachable from a session", _raw_draft())
    before = _snapshot(plain, exp_id)
    session = tutorial_client(app)

    reads = [
        f"/api/experiments/{exp_id}",
        f"/api/experiments/{exp_id}/draft",
        f"/api/experiments/{exp_id}/pending",
        f"/api/experiments/{exp_id}/evidence",
        f"/api/experiments/{exp_id}/evidence-classification",
        f"/api/experiments/{exp_id}/artifacts",
    ]
    for path in reads:
        assert session.get(path).status_code == 404, path

    version = f'"{before["detail"]["version"]}"'
    writes = [
        (
            f"/api/experiments/{exp_id}/answers",
            {"answers": {"series": "x"}, "confirmed_by_user": True},
        ),
        (
            f"/api/experiments/{exp_id}/edit",
            {"field": "series", "value": "x", "confirmed_by_user": True},
        ),
        (f"/api/experiments/{exp_id}/export", None),
    ]
    for path, body in writes:
        response = session.post(path, json=body, headers={"If-Match": version})
        assert response.status_code == 404, f"{path} -> {response.status_code}"

    # ...and the record is untouched by every one of those attempts.
    assert _snapshot(plain, exp_id) == before


def test_a_second_session_cannot_reach_the_first_sessions_record(app):
    """The same boundary between two sessions, over HTTP, on a WRITE.

    `test_two_sessions_are_independently_mutable_and_mutually_invisible` establishes
    independence at the store level. This adds the HTTP write path, because a route
    that resolved the scope for reads but not for a mutation would pass that one.
    """
    first = tutorial_client(app)
    second = tutorial_client(app)
    target = ws.SEED_NEW_DRAFT_ID

    detail = second.get(f"/api/experiments/{target}")
    assert detail.status_code == 200
    version = f'"{detail.json()["version"]}"'

    # Both sessions hold a record with this id, so the interesting question is whether
    # writing in one moves the other's copy.
    before = json.loads(
        (ws.scope_root(first.tutorial_session_id) / target / "experiment.json").read_text(
            encoding="utf-8"
        )
    )
    answers = ws.load_demo_answers()
    field = next(iter(answers))
    response = second.post(
        f"/api/experiments/{target}/answers",
        json={"answers": {field: answers[field]}, "confirmed_by_user": True},
        headers={"If-Match": version},
    )
    assert response.status_code == 200, response.text
    after = json.loads(
        (ws.scope_root(first.tutorial_session_id) / target / "experiment.json").read_text(
            encoding="utf-8"
        )
    )
    assert after == before


# =============================================================================
# T20 · creating a session cannot race the staleness sweep
# =============================================================================


def test_creating_a_session_cannot_be_swept_by_a_concurrent_sweep(app):
    """A FRESH session must survive a sweep running at the same moment.

    `create_tutorial_session` sweeps first and then creates, so the dangerous
    interleaving is a sweep that starts while another request is mid-create: if the
    sweep read a directory whose marker had not been written yet, the "age nobody can
    read is stale" rule (which is correct, and fail-closed) would delete a session that
    was seconds old, and the reader would be 404'd out of a walkthrough they had just
    started.
    """
    client = TestClient(app)
    created: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def create() -> None:
        try:
            for _ in range(3):
                response = client.post("/api/tutorial/sessions")
                assert response.status_code == 201, response.text
                with lock:
                    created.append(response.json()["session_id"])
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            with lock:
                errors.append(exc)

    def sweep() -> None:
        try:
            for _ in range(20):
                ws.sweep_stale_tutorial_sessions()
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=create) for _ in range(3)]
    threads += [threading.Thread(target=sweep) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == [], errors
    assert len(created) == 9
    assert len(set(created)) == 9, "two sessions were minted with the same id"
    for session_id in created:
        assert ws.tutorial_session_exists(session_id), (
            f"session {session_id} was swept while it was fresh"
        )
        assert {e.id for e in ws.list_experiments(session_id)} == set(ws.CANONICAL_IDS)


def test_a_sweep_during_a_lifecycle_leaves_the_ordinary_workspace_alone(app, plain):
    exp_id = _make_ordinary("Ordinary · present during a sweep", _raw_draft())
    before = _snapshot(plain, exp_id)
    stale = tutorial_client(app).tutorial_session_id
    marker = ws.scope_root(stale) / ws.TUTORIAL_MARKER
    marker.unlink()  # an unreadable age is treated as stale, by design
    assert ws.sweep_stale_tutorial_sessions() == 1
    assert not ws.tutorial_session_exists(stale)
    assert _snapshot(plain, exp_id) == before


# =============================================================================
# the scope header itself
# =============================================================================


def test_an_ordinary_request_carries_no_scope_and_a_scoped_one_is_explicit(app, plain):
    """The header is the ONLY thing that selects a scope — there is no implicit default.

    Stated as a test because it is what makes every assertion above meaningful: if the
    server could infer a scope from anything else (a cookie, a most-recent session, a
    directory scan), "no header" would stop meaning "the ordinary workspace".
    """
    exp_id = _make_ordinary("Ordinary · header-selected scope", _raw_draft())
    session_id, _ = ws.create_tutorial_session()

    assert [e["id"] for e in plain.get("/api/experiments").json()["experiments"]] == [
        exp_id
    ]
    scoped = plain.get(
        "/api/experiments", headers={TUTORIAL_SESSION_HEADER: session_id}
    ).json()
    assert {e["id"] for e in scoped["experiments"]} == set(ws.CANONICAL_IDS)
    # An empty / whitespace header is not a scope selector either, and must not be
    # mistaken for one.
    for blank in ("", "   "):
        response = plain.get(
            "/api/experiments", headers={TUTORIAL_SESSION_HEADER: blank}
        )
        assert response.status_code in (200, 422), blank
        if response.status_code == 200:
            assert [e["id"] for e in response.json()["experiments"]] == [exp_id], blank

"""A persisted ``record_id`` must never become a path, and never a 500.

WHAT THIS FILE PINS, in order of how much it would hurt to lose:

1. **A persisted ``record_id`` cannot address a file outside ``records_dir``.**
   ``Experiment.record_path`` built ``<records_dir>/<record_id>.json`` from a
   TRUTHINESS check, so ``"../planted_secret"`` produced a path one level up and
   ``GET /api/experiments/{id}/artifacts`` answered **200 carrying that file's
   contents**. ``"../../../far_away_secret"`` reached outside the whole workspace.
2. **A falsy non-``None`` ``record_id`` is not a 500.** ``exported()`` asks
   ``record_id is not None`` while ``record_path()`` asked truthiness, so ``{}``,
   ``[]``, ``0``, ``""`` and ``False`` each said "exported" and then handed the
   route ``None`` to call ``.read_text()`` on — **500** on both
   ``/evidence`` and ``/artifacts``.
3. **The degradation is truthful.** A record whose stored ``record_id`` is not a
   record id reads ``exported: false`` and offers no artifact filename. It is not
   repaired, and the stored document is not rewritten by reading it.

MEASURED OVER HTTP ON ``cde8d7c`` before the fix; every status code asserted below
was observed in both directions (see the module's own test names).

**REACHABILITY, STATED PLAINLY RATHER THAN OVERSTATED.** No route lets a client set
``record_id`` — export mints it with ``new_record_id()`` — so reaching the traversal
needs a persisted document written from outside this application (an operator edit,
an out-of-band ``INSERT``, a future importer). **This is defence in depth, not a live
breach.** The tests below therefore write the state file directly, which is the only
way in, and say so rather than implying a client could do it.

TWO INDEPENDENT GATES ARE PINNED SEPARATELY, on purpose. ``from_state`` refuses the
value on the READ path; ``record_path``/``sidecar_path`` refuse it again at the point
a string becomes a path, which is what covers ``record_id`` being assigned directly
(the export route does exactly that). A test that only drove HTTP would pass with
either gate alone, so the second is exercised against the object.

Every fixture is synthetic and hand-built. Nothing here reads real data.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api.app import create_app

#: The five values that are FALSY but not ``None``. Each was a measured 500.
FALSY_NON_NONE = [{}, [], 0, "", False]

#: Values that are truthy strings and would have become a path component.
TRAVERSALS = ["../planted_secret", "../../../far_away_secret"]

PLANTED = "PLANTED-SECRET-CONTENT-THAT-MUST-NOT-BE-SERVED"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _create(client) -> str:
    r = client.post("/api/experiments", json={"title": "Containment probe"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _state_path(exp_id: str):
    return ws.workspace_root() / exp_id / "experiment.json"


def _poke_record_id(exp_id: str, value) -> None:
    """Write ``record_id`` straight into the persisted document.

    THE ONLY WAY IN, and that is the point rather than a shortcut: no route accepts
    this value from a client. Writing the file is what an operator edit or an
    out-of-band write looks like from this application's side.
    """
    path = _state_path(exp_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    state["record_id"] = value
    path.write_text(json.dumps(state), encoding="utf-8")


@pytest.mark.parametrize("value", FALSY_NON_NONE)
def test_a_falsy_record_id_is_read_not_crashed(client, value):
    """Was **500** on both routes for all five values; is **200**.

    The asymmetry that caused it is worth keeping in the test name's reach:
    ``exported()`` used ``is not None`` and ``record_path()`` used truthiness, so
    these five fell exactly between the two.
    """
    exp_id = _create(client)
    _poke_record_id(exp_id, value)

    assert client.get(f"/api/experiments/{exp_id}/evidence").status_code == 200
    assert client.get(f"/api/experiments/{exp_id}/artifacts").status_code == 200
    # The whole list must not be affected either.
    assert client.get("/api/experiments").status_code == 200


@pytest.mark.parametrize("value", FALSY_NON_NONE)
def test_a_falsy_record_id_reads_as_not_exported(client, value):
    """The degradation is TRUTHFUL: a value that is not a record id is not an export.

    This is the half a crash-only fix would miss. Answering 200 while still claiming
    ``exported: true`` would be a record asserting it has an artifact that cannot be
    named, which is the honesty defect rather than the crash.
    """
    exp_id = _create(client)
    _poke_record_id(exp_id, value)

    detail = client.get(f"/api/experiments/{exp_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["exported"] is False
    refs = body.get("artifact_refs") or {}
    assert refs.get("record_filename") is None
    assert refs.get("sidecar_filename") is None


@pytest.mark.parametrize("value", TRAVERSALS)
def test_a_traversing_record_id_serves_no_file_from_outside_records_dir(
    client, tmp_path, value
):
    """Was **200 with the planted file's contents**; serves nothing.

    The planted file is written at the path the OLD code would have resolved to, so
    this test is only meaningful while that file exists — it asserts the bytes are
    reachable on disk and still absent from every response.
    """
    exp_id = _create(client)
    records_dir = ws.workspace_root() / exp_id / "records"
    records_dir.mkdir(parents=True, exist_ok=True)

    target = (records_dir / f"{value}.json").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"secret": PLANTED}), encoding="utf-8")
    # The bytes really are on disk and really are outside `records_dir` — otherwise
    # this test could pass by planting nothing.
    assert target.is_file()
    assert not target.is_relative_to(records_dir.resolve())

    _poke_record_id(exp_id, value)

    for path in ("", "/evidence", "/artifacts", "/export-readiness"):
        response = client.get(f"/api/experiments/{exp_id}{path}")
        assert response.status_code in (200, 404), (path, response.status_code)
        assert PLANTED not in response.text, f"{path} served content from {target}"
        # The traversal must not survive as a FILENAME either: `record_filename`
        # reaches the browser, and `../planted_secret.json` there would be both a
        # path leak and a download the client could be induced to name.
        assert "planted_secret" not in response.text
        assert "far_away_secret" not in response.text


@pytest.mark.parametrize("value", TRAVERSALS + FALSY_NON_NONE)
def test_the_path_methods_refuse_the_value_even_when_assigned_directly(
    client, tmp_path, value
):
    """THE SECOND GATE, exercised where HTTP cannot reach it.

    ``record_id`` is a plain mutable attribute and the export route assigns it
    directly (``exp.record_id = result.record["record_id"]``), so a parse-time guard
    alone would leave that assignment unguarded. Driving the object is the only way
    to tell the two gates apart: over HTTP either one alone would make the tests
    above pass.
    """
    exp_id = _create(client)
    exp = ws.load_experiment(exp_id)
    assert exp is not None

    exp.record_id = value  # bypasses `from_state` entirely, as the export route does

    assert exp.record_path() is None
    assert exp.sidecar_path() is None


def test_a_real_record_id_still_resolves_to_its_artifact_pair(client):
    """THE NEGATIVE CONTROL. A guard that refused everything would pass every test above.

    Exports a record for real and asserts both halves of the pair are named and sit
    inside ``records_dir`` — so the gate is proven to admit what it must.
    """
    exp_id = _create(client)
    exp = ws.load_experiment(exp_id)
    assert exp is not None

    exp.record_id = ws.new_record_id()

    record_path = exp.record_path()
    sidecar_path = exp.sidecar_path()
    assert record_path is not None and sidecar_path is not None
    records_dir = exp.records_dir.resolve()
    assert record_path.resolve().parent == records_dir
    assert sidecar_path.resolve().parent == records_dir
    assert record_path.name == f"{exp.record_id}.json"
    assert sidecar_path.name == f"{exp.record_id}.evidence.json"


def test_reading_a_degraded_document_does_not_rewrite_it(client):
    """NOTHING IS REPAIRED. The stored bytes are unchanged by being read.

    The fallback is a READ-TIME normalisation, not a migration. A read that silently
    rewrote the document would make the degradation unobservable to whoever has to
    fix it, and would do it without the record's version moving.
    """
    exp_id = _create(client)
    _poke_record_id(exp_id, "../planted_secret")
    before = _state_path(exp_id).read_bytes()

    assert client.get(f"/api/experiments/{exp_id}").status_code == 200
    assert client.get(f"/api/experiments/{exp_id}/artifacts").status_code == 200
    assert client.get("/api/experiments").status_code == 200

    assert _state_path(exp_id).read_bytes() == before

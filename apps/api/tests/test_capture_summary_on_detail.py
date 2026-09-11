"""``GET /api/experiments/{id}`` carries the record's capture counts — and costs
nothing extra to do it.

WHY THIS FILE EXISTS
====================

The record sidebar promotes capture to a destination of its own and states how much
is behind it ("3 notes · 2 to review"). Until ``capture_summary`` existed, the only
way a client could learn those numbers was to issue ``GET .../notes`` and
``GET .../proposals`` — **two extra requests per record load, on three of the four
record workspaces**, on a screen whose panels are deliberately lazy so a reader who
never opens capture pays nothing. ``GET .../notes`` has no ``limit``, so that read is
unbounded, and the client had been shrinking it with ``?state=dismissed`` purely to
throw the rows away. Measured over HTTP on 2026-09-11, on a record holding 10 notes
and 3 open proposals: the pair as issued cost **4,281 B** and the same pair
unfiltered **11,073 B** — to render two integers the server already held in memory.
The block that replaced them is **79 B** on a response the screen already fetches.

WHAT IS PINNED HERE, AND WHY EACH ONE IS A SEPARATE CLAIM
=========================================================

1. **PARITY.** Every number in ``capture_summary`` equals the number the list route
   that owns it reports as its own total — over records with dismissed notes, mixed
   proposal states, unreadable entries of both kinds, and none of any of it. Two
   surfaces now state these counts and they must not be able to disagree. The
   production code shares ONE expression per number (``routes._notes_total``,
   ``_proposal_state_counts``, ``_unreadable_note_count``,
   ``_unreadable_proposal_count``); this proves the sharing at the wire rather than
   by reading the file.

2. **THEY ARE TOTALS, NOT ARRAY LENGTHS.** ``CLAUDE.md`` §11 records four separate
   surfaces that shipped a count taken from a fetched array. The detail payload has
   no array to take one from, which removes the hazard on this route but not the
   defect's ancestor: ``proposals_open`` must be the count of OPEN proposals over the
   whole record, not the record's proposal total and not what a window returned.
   Fixtures below hold rejected, withdrawn and superseded proposals alongside open
   ones precisely so that the record's total and its open count differ. (``accepted``
   is deliberately absent: acceptance answers ``409 human_actor_required`` in a
   default-configured deployment — ``CLAUDE.md`` §15 — and no application change can
   close that.)

3. **NO EXTRA WORK.** ``CLAUDE.md`` §11's 2026-08-25 entry records that this exact
   route once composed every run five times and dry-ran every unit twice. A block
   added to it must be arithmetic over lists already in memory, and that is asserted
   two ways: directly, with ``routes._capture_summary`` run under spies on every
   composition, dry run and filesystem read; and over HTTP, by comparing the detail
   route's call counters against a run in which the block is stubbed out entirely.

WHAT IS NOT CLAIMED
===================

Nothing here times anything — a wall-clock assertion in the normal suite is flaky
under CPU contention and this repository has been bitten by exactly that. The
request-count measurement is in the slice report, taken in a real browser.

Everything is synthetic. No file outside the tmp workspace is read or written, and
nothing connects to a database.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import isaac_api.notes as notes_module
import isaac_api.proposals as proposals_module
import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_api import experiment_repository as repo

from conftest import client_ws, tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def ordinary_client(tmp_path, monkeypatch):
    """A NON-tutorial client. Needed only by the rename test — see its docstring."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws-ordinary"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    from fastapi.testclient import TestClient

    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def experiment_id(client):
    store = client_ws(client)
    exp = store.create_experiment(
        "Capture summary fixture",
        {"kind": "synthetic"},
        {"meta": {}, "fields": {}, "pending": []},
    )
    return exp.id


# --- helpers ------------------------------------------------------------------


def _etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _capture_note(client, experiment_id: str, text: str) -> dict:
    response = client.post(
        f"/api/experiments/{experiment_id}/notes",
        json={"text": text, "source": "typed_note"},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 201, response.text
    return response.json()["note"]


def _dismiss(client, experiment_id: str, note_id: str) -> None:
    response = client.post(
        f"/api/experiments/{experiment_id}/notes/{note_id}/review",
        json={"action": "dismiss", "confirmed_by_user": True},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 200, response.text


def _state_path(client, experiment_id: str) -> Path:
    return ws.scope_root(client.tutorial_session_id) / experiment_id / "experiment.json"


def _plant(client, experiment_id: str, key: str, entry) -> None:
    """Write a stored entry this build cannot read, the way a later build would.

    Planted rather than created through a route, because by definition no route in
    this build can produce one.
    """
    path = _state_path(client, experiment_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault(key, []).append(copy.deepcopy(entry))
    path.write_text(json.dumps(state), encoding="utf-8")


def _record_scoped_path(client, experiment_id: str) -> str:
    """A target path the SERVER says is record-scoped — read, never transcribed.

    The route serves the set for exactly this reason (``_proposals_payload``: the
    alternative is transcribing a derived path set into a client, where it is free to
    drift from what the routes enforce). A run-scoped path would need a run, which
    these fixtures deliberately do not have.
    """
    paths = _proposals_list(client, experiment_id)["record_scoped_target_field_paths"]
    assert paths, "the build must offer at least one record-scoped target path"
    return paths[0]


def _open_proposal(client, experiment_id: str, *, note_id: str, value: str) -> str:
    """One OPEN proposal, minted through the production route."""
    response = client.post(
        f"/api/experiments/{experiment_id}/proposals",
        json={
            "note_id": note_id,
            "target_field_path": _record_scoped_path(client, experiment_id),
            "proposed_value": value,
            "rule": "a test fixture proposed it",
        },
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 200, response.text
    return response.json()["proposal"]["proposal_id"]


def _review(client, experiment_id: str, proposal_id: str, action: str) -> None:
    response = client.post(
        f"/api/experiments/{experiment_id}/proposals/{proposal_id}/review",
        json={"action": action, "confirmed_by_user": True},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 200, response.text


def _proposals_in_states(client, experiment_id: str, *, note_id: str) -> None:
    """Two open, one rejected, one withdrawn and one superseded — all through the
    production routes, none planted.

    **NO STATE IS WRITTEN INTO THE DOCUMENT, and the first version of this fixture
    did exactly that and was wrong in an instructive way.** Setting ``state`` to
    ``"accepted"`` on a stored entry produced an entry ``IngestionProposal`` refuses
    to hydrate — an accepted proposal carries decision fields an open one does not —
    so the record gained an ``unreadable_entries`` of 1 and the fixture was measuring
    a defect it had itself created. Reaching each state the way the product reaches
    it removes the whole class of error.

    ``accepted`` IS ABSENT, and that is a configuration fact rather than a gap:
    acceptance answers ``409 human_actor_required`` in a default-configured
    deployment (``CLAUDE.md`` §15) because no trusted authentication boundary exists
    in this build. ``superseded`` covers the "terminal state that is not open" axis
    this file needs, and ``test_ingestion_proposals.py`` owns acceptance.
    """
    path = _record_scoped_path(client, experiment_id)

    def propose(value: str) -> str:
        response = client.post(
            f"/api/experiments/{experiment_id}/proposals",
            json={
                "note_id": note_id,
                "target_field_path": path,
                "proposed_value": value,
                "rule": "a test fixture proposed it",
            },
            headers={"If-Match": _etag(client, experiment_id)},
        )
        assert response.status_code == 200, response.text
        return response.json()["proposal"]["proposal_id"]

    _review(client, experiment_id, propose("to-be-rejected"), "reject")
    _review(client, experiment_id, propose("to-be-withdrawn"), "withdraw")
    # A second live proposal at the SAME target supersedes the first, which is how
    # the product reaches that state and needs no review call at all.
    superseded = propose("first-at-this-path")
    _review(client, experiment_id, superseded, "supersede")
    propose("open-one")
    propose("open-two")


def _detail(client, experiment_id: str) -> dict:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _notes_list(client, experiment_id: str, **params) -> dict:
    response = client.get(f"/api/experiments/{experiment_id}/notes", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _proposals_list(client, experiment_id: str, **params) -> dict:
    response = client.get(f"/api/experiments/{experiment_id}/proposals", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _assert_parity(client, experiment_id: str) -> dict:
    """The whole contract, in one call: the detail block equals the list routes.

    Read through the HTTP surface on both sides, because that is where a client sees
    them and where a divergence would actually be shipped.
    """
    summary = _detail(client, experiment_id)["capture_summary"]
    listed_notes = _notes_list(client, experiment_id)
    listed_proposals = _proposals_list(client, experiment_id)

    assert summary == {
        "notes_total": listed_notes["total"],
        "proposals_open": listed_proposals["by_state"]["open"],
        "unreadable_entries": (
            listed_notes["unreadable_entries"] + listed_proposals["unreadable_entries"]
        ),
    }, (summary, listed_notes, listed_proposals)
    return summary


# --- 1. parity with the two list routes ---------------------------------------


def test_an_untouched_record_reports_three_zeroes_rather_than_omitting_the_block(
    client, experiment_id
):
    """ZERO IS A CLAIM AND IS MADE EXPLICITLY.

    A client that had to distinguish "this record holds nothing" from "the server did
    not say" by the presence of a key would get it wrong, and the one surface reading
    this block renders NOTHING for the second case and a real sentence for the first.
    So the block is always present and always three integers.
    """
    summary = _assert_parity(client, experiment_id)
    assert summary == {
        "notes_total": 0,
        "proposals_open": 0,
        "unreadable_entries": 0,
    }


def test_notes_total_counts_every_note_the_record_holds_including_dismissed(
    client, experiment_id
):
    """``total``'s own definition, which is the route's and not a choice made here.

    ``GET .../notes`` states *"DISMISSED NOTES ARE INCLUDED … it is not a deletion,
    and this API has no operation that deletes a note"*. A record whose notes were
    every one dismissed still HOLDS them, and the summary says so.

    MUTATION (run 2026-09-11): changed ``routes._notes_total`` to count only notes
    whose state is not ``dismissed``. **3 RED** — this test, the window-invariance
    test, and the one-expression source guard (because the mutant's body is no longer
    a bare ``len(exp.notes)``). Reverted; 13 pass.
    """
    first = _capture_note(client, experiment_id, "the beamline tripped")
    _capture_note(client, experiment_id, "scan 3 was repeated")
    _capture_note(client, experiment_id, "sample looked discoloured")
    _dismiss(client, experiment_id, first["id"])

    summary = _assert_parity(client, experiment_id)
    assert summary["notes_total"] == 3
    # ...and the record really is in the state this test claims, rather than the
    # dismissal having silently failed and the number being right by accident.
    assert _notes_list(client, experiment_id)["by_state"]["dismissed"] == 1


def test_proposals_open_counts_open_ones_and_not_the_records_proposal_total(
    client, experiment_id
):
    """THE DEFECT'S ANCESTOR, pinned on a fixture where the numbers differ.

    Five proposals, two open. A summary reporting the record's proposal TOTAL says
    five; one reporting a fetched window's length says whatever the window held. Both
    are wrong and both are mistakes this repository has shipped.

    MUTATIONS (both run 2026-09-11): ``proposals_open`` set to ``len(exp.proposals)``
    — **3 RED** (this test, the window-invariance test, and the constant guard).
    Then set to ``sum(_proposal_state_counts(exp).values())``, which is the same
    number by a different route — **3 RED, identically**. Both reverted; 13 pass.
    """
    note = _capture_note(client, experiment_id, "the pellet was Cu2O")
    _proposals_in_states(client, experiment_id, note_id=note["id"])

    summary = _assert_parity(client, experiment_id)
    assert summary["proposals_open"] == 2
    listed = _proposals_list(client, experiment_id)
    assert listed["total"] == 5, "the fixture must make total and open differ"
    assert listed["by_state"] == {
        "open": 2,
        "accepted": 0,
        "rejected": 1,
        "superseded": 1,
        "withdrawn": 1,
    }


def test_unreadable_entries_sums_BOTH_kinds_rather_than_one_of_them(
    client, experiment_id
):
    """Two stored entries this build cannot present — one of each kind.

    A summary that counted only one kind would let "1 note" read as the whole of what
    was captured when it is not, which is the silent discard both list routes' own
    disclosures exist to end.

    MUTATIONS (both run 2026-09-11): ``unreadable_entries`` set to
    ``_unreadable_note_count(exp)`` alone — **1 RED**, this test. Set to
    ``_unreadable_proposal_count(exp)`` alone — **3 RED**, this test plus both
    no-extra-work tests, whose fixture holds an unreadable note and no unreadable
    proposal. Both reverted; 13 pass.
    """
    note = _capture_note(client, experiment_id, "a readable one")
    _plant(
        client,
        experiment_id,
        "notes",
        {
            "id": "FROM-A-LATER-BUILD",
            "text": "content this build cannot interpret",
            "source": "a_source_this_build_does_not_know",
            "captured_utc": "2026-09-01T00:00:00Z",
        },
    )
    _plant(client, experiment_id, proposals_module.STATE_KEY, {"proposal_id": "P-BROKEN"})
    _open_proposal(client, experiment_id, note_id=note["id"], value="Cu2O")

    summary = _assert_parity(client, experiment_id)
    assert summary == {
        "notes_total": 1,
        "proposals_open": 1,
        "unreadable_entries": 2,
    }
    # Each list route still discloses its OWN kind separately, which is where a
    # reader finds out WHICH. The summary sums; it does not replace them.
    assert _notes_list(client, experiment_id)["unreadable_entries"] == 1
    assert _proposals_list(client, experiment_id)["unreadable_entries"] == 1


def test_the_summary_is_unmoved_by_a_filter_or_a_window_the_client_asked_for(
    client, experiment_id
):
    """A LIST REQUEST'S PARAMETERS CANNOT MOVE THE RECORD'S OWN NUMBERS.

    This is the property the old client was exploiting when it read
    ``?state=dismissed`` purely to shrink a payload: the route applies ``state`` to
    the ROWS it selects and computes its totals over the whole record. The summary
    inherits that by construction — it is on a route that takes neither parameter —
    and the assertion is that the two agree under every window the client could have
    asked for.
    """
    note = _capture_note(client, experiment_id, "first")
    second = _capture_note(client, experiment_id, "second")
    _dismiss(client, experiment_id, second["id"])
    _proposals_in_states(client, experiment_id, note_id=note["id"])

    summary = _detail(client, experiment_id)["capture_summary"]
    assert summary == {"notes_total": 2, "proposals_open": 2, "unreadable_entries": 0}

    for params in ({}, {"state": "dismissed"}, {"state": "unreviewed"}):
        assert _notes_list(client, experiment_id, **params)["total"] == 2, params
    for params in ({}, {"limit": 1}, {"state": "open"}, {"order": "newest_first"}):
        listed = _proposals_list(client, experiment_id, **params)
        assert listed["by_state"]["open"] == 2, params
        assert listed["total"] == 5, params


def test_the_summary_tracks_a_write_rather_than_being_stamped_once(
    client, experiment_id
):
    """It is derived per read, so a note captured now is counted now.

    Not a caching test for its own sake: ``_capture_summary`` is deliberately
    threaded-not-memoised for the reason ``_shared_units`` sets out — this module
    mutates an ``Experiment`` and re-reads its derived state in the same request, so
    anything stored on the instance can be served stale.
    """
    assert _detail(client, experiment_id)["capture_summary"]["notes_total"] == 0
    _capture_note(client, experiment_id, "one")
    assert _detail(client, experiment_id)["capture_summary"]["notes_total"] == 1
    _capture_note(client, experiment_id, "two")
    assert _assert_parity(client, experiment_id)["notes_total"] == 2


def test_the_capture_block_appears_on_every_response_built_from_the_detail_bundle(
    ordinary_client,
):
    """``_detail`` is also the RENAME response's body, and a client refreshing its
    screen from a mutation response must not lose a field the GET carries. One
    composition, one shape.

    AN ORDINARY-SCOPE CLIENT, because ``PATCH /api/experiments/{id}`` answers ``409
    ordinary_scope_required`` inside a worked-example session by design — the five
    built-in examples are fixed teaching material and a reset would revert the
    change. Every other test here runs in the tutorial scope, which is the scope
    those fixtures are cheapest in; this one cannot.
    """
    client = ordinary_client
    exp = ws.create_experiment(
        "Rename fixture", {"kind": "synthetic"}, {"meta": {}, "fields": {}, "pending": []}
    )
    _capture_note(client, exp.id, "one")

    before = _detail(client, exp.id)["capture_summary"]
    renamed = client.patch(
        f"/api/experiments/{exp.id}",
        json={"title": "Renamed"},
        headers={"If-Match": _etag(client, exp.id)},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "Renamed", "the fixture must actually have renamed"
    assert renamed.json()["capture_summary"] == before == {
        "notes_total": 1,
        "proposals_open": 0,
        "unreadable_entries": 0,
    }


# --- 2. it costs no extra work ------------------------------------------------


class _WorkCounter:
    def __init__(self) -> None:
        self.resolved_run_draft = 0
        self.export_units = 0
        self.export_draft = 0
        self.validate_draft = 0
        self.load_experiment = 0
        self.file_reads = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "resolved_run_draft": self.resolved_run_draft,
            "export_units": self.export_units,
            "export_draft": self.export_draft,
            "validate_draft": self.validate_draft,
            "load_experiment": self.load_experiment,
            "file_reads": self.file_reads,
        }

    def __repr__(self) -> str:  # pragma: no cover - assertion message only
        return repr(self.as_dict())


@pytest.fixture()
def work(monkeypatch) -> _WorkCounter:
    """Count the expensive things, over the real HTTP surface.

    The first four are the ones ``test_detail_route_composes_each_run_once.py``'s
    profile named. ``load_experiment`` and ``Path.read_text`` are added here because
    the specific hazard THIS block could introduce is not a recomposition — it is an
    I/O read to fetch notes or proposals that the route would otherwise not perform.
    A counter that omitted them would read as coverage of the claim it does not make.
    """
    counter = _WorkCounter()
    real_compose = ws.Experiment.resolved_run_draft
    real_units = ws.Experiment.export_units
    real_export_draft = ws.export_draft
    real_validate = ws.validate_draft
    real_load = ws.load_experiment
    real_read_text = Path.read_text

    def spy_compose(self, run):
        counter.resolved_run_draft += 1
        return real_compose(self, run)

    def spy_units(self, *args, **kwargs):
        counter.export_units += 1
        return real_units(self, *args, **kwargs)

    def spy_export_draft(*args, **kwargs):
        counter.export_draft += 1
        return real_export_draft(*args, **kwargs)

    def spy_validate(*args, **kwargs):
        counter.validate_draft += 1
        return real_validate(*args, **kwargs)

    def spy_load(*args, **kwargs):
        counter.load_experiment += 1
        return real_load(*args, **kwargs)

    def spy_read_text(self, *args, **kwargs):
        counter.file_reads += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(ws.Experiment, "resolved_run_draft", spy_compose)
    monkeypatch.setattr(ws.Experiment, "export_units", spy_units)
    monkeypatch.setattr(ws, "export_draft", spy_export_draft)
    monkeypatch.setattr(ws, "validate_draft", spy_validate)
    monkeypatch.setattr(ws, "load_experiment", spy_load)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    return counter


def _populate(client, experiment_id: str) -> None:
    note = _capture_note(client, experiment_id, "the beamline tripped")
    _capture_note(client, experiment_id, "scan 3 was repeated")
    _open_proposal(client, experiment_id, note_id=note["id"], value="one")
    _open_proposal(client, experiment_id, note_id=note["id"], value="two")
    _plant(client, experiment_id, "notes", {"id": "ALIEN", "shape": "unknown"})


def test_the_capture_summary_itself_performs_no_composition_and_no_read(
    client, experiment_id, work
):
    """THE DIRECT PROOF, at the function rather than through the route.

    ``notes``, ``unreadable_notes``, ``proposals`` and ``unreadable_proposals`` are
    ordinary list fields on ``Experiment``, filled once by ``workspace._hydrate_notes``
    / ``_hydrate_proposals`` when the document was loaded. So the block must be pure
    arithmetic over lists already in memory. Asserted, not assumed: every counter is
    zero across the call, INCLUDING the filesystem one.

    MUTATIONS (both run 2026-09-11): added ``ws.load_experiment(exp.id)`` to
    ``routes._capture_summary`` — **2 RED**, this test and the A/B below. Added
    ``exp.export_units()`` instead — **3 RED**, those two plus the n-times-read
    guard. Both reverted; 13 pass.
    """
    _populate(client, experiment_id)
    exp = client_ws(client).load_experiment(experiment_id)
    assert exp is not None
    # The fixture must be non-trivial, or "zero work" is true of nothing.
    assert len(exp.notes) == 2 and len(exp.proposals) == 2 and len(exp.unreadable_notes) == 1

    for field in vars(work):
        setattr(work, field, 0)
    summary = routes._capture_summary(exp)

    assert work.as_dict() == {
        "resolved_run_draft": 0,
        "export_units": 0,
        "export_draft": 0,
        "validate_draft": 0,
        "load_experiment": 0,
        "file_reads": 0,
    }, work
    assert summary == {"notes_total": 2, "proposals_open": 2, "unreadable_entries": 1}


def test_the_detail_route_does_exactly_the_same_work_with_the_block_as_without_it(
    client, experiment_id, work, monkeypatch
):
    """THE SAME PROOF OVER HTTP, A/B against the block stubbed out entirely.

    Stronger than a fixed expected number, because it does not have to be updated
    when an unrelated slice changes what the route legitimately does: whatever the
    route costs, it must cost the SAME with this block and without it.

    ``_capture_summary`` is the one seam, exactly as ``_shared_units`` and
    ``_shared_dry_run`` are theirs, which is what makes this reproducible by patching
    a single function.

    MUTATION (run 2026-09-11): made ``routes._capture_summary`` read one file
    (``Path(__file__).read_text()`` — harmless, so the ONLY thing that moves is the
    counter). **2 RED**, this test and the direct one above; ``file_reads`` differed
    by exactly one. Reverted; 13 pass.
    """
    _populate(client, experiment_id)

    for field in vars(work):
        setattr(work, field, 0)
    with_block = _detail(client, experiment_id)
    cost_with = work.as_dict()

    monkeypatch.setattr(routes, "_capture_summary", lambda exp: {})
    for field in vars(work):
        setattr(work, field, 0)
    without_block = _detail(client, experiment_id)
    cost_without = work.as_dict()

    assert cost_with == cost_without, (cost_with, cost_without)
    # The A/B must actually have differed in the one way it is supposed to, or the
    # equality above is a comparison of two identical runs.
    assert without_block["capture_summary"] == {}
    assert with_block["capture_summary"] == {
        "notes_total": 2,
        "proposals_open": 2,
        "unreadable_entries": 1,
    }
    # ...and the rest of the response is byte-identical, so nothing else moved.
    assert {k: v for k, v in with_block.items() if k != "capture_summary"} == {
        k: v for k, v in without_block.items() if k != "capture_summary"
    }


def test_adding_the_block_did_not_reintroduce_an_n_times_read(client, work):
    """The equality ``test_detail_route_composes_each_run_once.py`` owns, re-asserted
    on a record that also holds capture material.

    That file's fixtures hold no notes and no proposals, so its counters could not
    have seen a capture-shaped regression. One composition per run and one unit list
    per response, with two notes, two proposals and an unreadable entry present.
    """
    store = client_ws(client)
    exp = store.create_experiment(
        "Capture summary with runs", {"kind": "synthetic"}, repo.blank_draft()
    )
    for index in range(3):
        exp.add_run(label=f"Run {index + 1}", draft=repo.blank_draft())
    exp.save_versioned()
    _populate(client, exp.id)

    for field in vars(work):
        setattr(work, field, 0)
    body = _detail(client, exp.id)

    assert body["pending_count"] > 0, "workload must still owe questions"
    assert work.resolved_run_draft == 3, work
    assert work.export_units == 1, work
    assert work.export_draft == 0, work
    assert body["capture_summary"]["notes_total"] == 2

    # AND THE PAYLOAD STAYS FLAT, which is the other half of what
    # `docs/evidence/scale-envelope-2026-08-27.md` §(b) measured about this route:
    # "1.5 KiB at every count … nothing in the response can grow". Three integers
    # cannot, whatever the record holds — asserted rather than assumed, because a
    # block that had served the ROWS would have broken that property silently.
    assert set(body["capture_summary"]) == {
        "notes_total",
        "proposals_open",
        "unreadable_entries",
    }
    assert all(isinstance(v, int) for v in body["capture_summary"].values())


# --- 3. the one-expression guarantee, structurally ----------------------------


def test_each_capture_count_has_exactly_one_expression_in_the_route_module():
    """TWO SURFACES, ONE EXPRESSION EACH — asserted over the source.

    ``CLAUDE.md`` §11 records four separate surfaces that shipped a number they had
    not derived from what they claimed to describe. The structural defence is that
    neither the list route nor the detail route computes its own: both call the same
    helper. A future edit that inlines ``len(exp.notes)`` back into one of them
    reintroduces the drift silently, and this is what fails when it does.

    It asserts over the MODULE SOURCE rather than over behaviour because the parity
    tests above already cover behaviour AT ONE MOMENT; this covers the reason they
    will keep agreeing.

    MUTATIONS (both run 2026-09-11): put ``len(exp.notes)`` back inline as
    ``_notes_payload``'s ``total`` — **1 RED, only this test**, which is exactly the
    point: the numbers still AGREE at that moment, so no parity test could see it.
    Put the ``by_state`` loop back inline in ``_proposals_payload`` — **1 RED, only
    this test**. Both reverted; 13 pass.
    """
    source = Path(routes.__file__).read_text(encoding="utf-8")

    for attribute, helper in (
        ("exp.notes", "_notes_total"),
        ("exp.unreadable_notes", "_unreadable_note_count"),
        ("exp.unreadable_proposals", "_unreadable_proposal_count"),
    ):
        occurrences = source.count(f"len({attribute})")
        assert occurrences == 1, (
            f"len({attribute}) appears {occurrences} times; it belongs only inside "
            f"routes.{helper}, which both the list payload and capture_summary call"
        )

    # The proposal state loop is the one derivation with a body, and it must exist
    # exactly once too — the `_proposals_payload` copy is now a call.
    assert source.count("for proposal in exp.proposals:") == 1, source.count(
        "for proposal in exp.proposals:"
    )


def test_the_open_state_is_the_proposals_modules_own_constant():
    """Never the literal ``"open"`` transcribed into the route.

    ``proposals.STATE_OPEN`` is the same constant the review routes gate on, so the
    count and the rule cannot drift apart.
    """
    assert proposals_module.STATE_OPEN in proposals_module.PROPOSAL_STATES
    source = Path(routes.__file__).read_text(encoding="utf-8")
    assert "proposals.STATE_OPEN" in source
    assert '"proposals_open": _proposal_state_counts(exp).get(proposals.STATE_OPEN' in source


def test_the_notes_vocabulary_is_unchanged_by_this_block():
    """A negative control on scope: this slice added a read, not a note state."""
    assert set(notes_module.NOTE_STATES) == {"unreviewed", "mapped", "kept", "dismissed"}

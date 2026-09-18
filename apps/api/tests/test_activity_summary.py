"""THE CROSS-EXPERIMENT ACTIVITY SUMMARY — `ACT-004`, against `DEC-44`.

Every assertion here is BEHAVIOURAL where it can be: a real request through the real
application to a real workspace whose activity was produced by real write paths, then
a read of what the summary says about it. ``CLAUDE.md`` §11 records a slice whose
central claim was pinned by string presence and which passed 25 tests beside a
fabricating seam, so the few structural assertions below (the no-headcount guard, the
no-event-content guard) are the ones where a behaviour cannot express the claim, and
each says why.

DATA BOUNDARY: **none.** Every value is synthetic and unmistakably so, in a
``tmp_path`` workspace. No database connection is opened, no migration is applied, no
external host is contacted, and nothing production-derived is read.

AUTHORIZATION BASIS: ``CLAUDE.md`` §15's application-side scope extension of
2026-08-29 ("the associated tests"), plus ``DEC-44`` — *"Statistics may SUMMARIZE this
history; Statistics must never be its source of truth"* — and ``DEC-50``, which
releases ``ACT-001``…``ACT-004`` for implementation with the actor reading
``unattributed``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api import activity, activity_summary, identity

SUMMARY = "/api/activity/summary"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A plain client on an empty workspace — NO worked-example session."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.delenv(identity.EDGE_TRUST_VERIFIER_ENV, raising=False)
    monkeypatch.delenv(identity.FIXTURE_ACTOR_SUBJECT_ENV, raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _create(client, title="Cu K-edge XANES, 300 K") -> str:
    created = client.post("/api/experiments", json={"title": title})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _etag(client, exp_id: str) -> dict:
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    return {"If-Match": f'"{version}"'}


def _rename(client, exp_id: str, title: str) -> None:
    """One real write path that records one real activity event."""
    response = client.patch(
        f"/api/experiments/{exp_id}", json={"title": title}, headers=_etag(client, exp_id)
    )
    assert response.status_code == 200, response.text


def _summary(client, **params) -> dict:
    response = client.get(SUMMARY, params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


def _state_path(exp_id: str):
    return ws.scope_root(None) / exp_id / "experiment.json"


def _rewrite_activity(exp_id: str, entries: list) -> None:
    """Put raw activity entries into a stored document.

    USED ONLY for the two cases a write path CANNOT produce — a stored entry the
    model refuses, and a readable entry whose timestamp will not parse. Everything
    else in this file goes through the real routes, because a fixture that writes the
    state it then asserts about proves nothing about the application.
    """
    path = _state_path(exp_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    state["activity"] = entries
    path.write_text(json.dumps(state), encoding="utf-8")


def _event(seq: int, recorded_utc: str, exp_id: str) -> dict:
    """One well-formed stored event, in the shape `ActivityEvent.to_state()` writes."""
    return {
        "id": f"synthetic-event-{seq}",
        "experiment_id": exp_id,
        "seq": seq,
        "recorded_utc": recorded_utc,
        "actor": activity.ACTOR_UNATTRIBUTED,
        "actor_trust_basis": activity.TRUST_BASIS_UNATTRIBUTED,
        "channel": activity.CHANNEL_WEB,
        "action": activity.ACTION_EXPERIMENT_RENAMED,
        "object_type": activity.OBJECT_EXPERIMENT,
        "object_id": exp_id,
        "run_id": None,
        "field_path": None,
        "before": {"present": True, "value": "before"},
        "after": {"present": True, "value": "after"},
        "source_ref": None,
        "is_field_value": False,
        "is_evidence": False,
    }


def _stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ==========================================================================
# the empty workspace, and the shape that never changes
# ==========================================================================


def test_an_empty_workspace_summarizes_honestly_rather_than_erroring(client):
    """Zeros, a stated window, a stated scope, and the served vocabularies."""
    body = _summary(client)
    assert body["totals"] == {
        "events_in_window": 0,
        "events_all_time": 0,
        "events_with_unreadable_timestamp": 0,
        "unreadable_entries": 0,
    }
    assert body["scope"]["experiments_in_scope"] == 0
    assert body["scope"]["experiments_summarized"] == 0
    assert body["scope"]["truncated"] is False
    assert body["scope"]["hydration_complete"] is True
    assert body["changed_records"] == {
        "rows": [],
        "total": 0,
        "returned": 0,
        "limit": activity_summary.RECORD_ROWS,
    }
    assert body["window"]["days"] == activity_summary.DEFAULT_WINDOW_DAYS
    # THE VOCABULARIES ARE SERVED, NEVER TRANSCRIBED — `activity_page`'s rule, so a
    # client's own labels cannot drift from the set the routes enforce.
    assert body["actions"] == sorted(activity.ACTIVITY_ACTIONS)
    assert body["channels"] == sorted(activity.ACTIVITY_CHANNELS)
    assert body["object_types"] == sorted(activity.ACTIVITY_OBJECT_TYPES)
    # A COMPLETE MAP, not a sparse one: the response shape does not change with the
    # data, so no client has to branch on a key's presence to read a count.
    assert set(body["by_action"]) == set(activity.ACTIVITY_ACTIONS)
    assert set(body["by_channel"]) == set(activity.ACTIVITY_CHANNELS)
    assert set(body["by_object_type"]) == set(activity.ACTIVITY_OBJECT_TYPES)
    assert set(body["by_action"].values()) == {0}
    # A WHOLE LIST MAKES NO DISCLOSURE — `_hydration_disclosure`'s established shape.
    assert "incomplete" not in body


def test_a_record_with_no_activity_contributes_no_row_and_no_count(client):
    """A created record records nothing — `activity.py` names that deliberately."""
    _create(client)
    body = _summary(client)
    assert body["scope"]["experiments_in_scope"] == 1
    assert body["totals"]["events_all_time"] == 0
    assert body["changed_records"]["total"] == 0


# ==========================================================================
# real acts, counted
# ==========================================================================


def test_real_write_paths_are_counted_and_the_record_is_reachable(client):
    """The acts come from real routes, and the row carries the drill-down id."""
    first = _create(client, "First record")
    second = _create(client, "Second record")
    _rename(client, first, "First record, renamed")
    _rename(client, first, "First record, renamed again")
    _rename(client, second, "Second record, renamed")

    body = _summary(client)
    assert body["totals"]["events_in_window"] == 3
    assert body["totals"]["events_all_time"] == 3
    assert body["by_action"][activity.ACTION_EXPERIMENT_RENAMED] == 3
    assert body["by_channel"][activity.CHANNEL_WEB] == 3
    assert body["by_object_type"][activity.OBJECT_EXPERIMENT] == 3
    assert body["changed_records"]["total"] == 2
    rows = body["changed_records"]["rows"]
    # BUSIEST FIRST, deterministically — the ordering is the server's so every
    # consumer renders one order.
    assert [row["experiment_id"] for row in rows] == [first, second]
    assert [row["events_in_window"] for row in rows] == [2, 1]
    # EVERY ROW IS ADDRESSABLE. A count that advertises content a reader cannot reach
    # is the dead end `d308b827` was written for.
    for row in rows:
        reachable = client.get(f"/api/experiments/{row['experiment_id']}/activity")
        assert reachable.status_code == 200
        assert reachable.json()["total"] >= row["events_in_window"]


def test_the_ranked_slices_are_ordered_and_their_counts_are_the_true_ones(client):
    exp = _create(client)
    _rename(client, exp, "renamed once")
    body = _summary(client)
    assert body["ranked_actions"] == [
        {"name": activity.ACTION_EXPERIMENT_RENAMED, "count": 1}
    ]
    assert body["actions_with_events"] == 1
    assert body["ranked_channels"] == [{"name": activity.CHANNEL_WEB, "count": 1}]
    assert body["channels_with_events"] == 1


def test_the_summary_writes_nothing(client):
    """READ-ONLY, and asserted over the record's own version rather than asserted in
    prose. `DEC-50`: append-only, no `UPDATE`, ever — so a summary that bumped a
    revision would be writing to the thing it claims only to describe."""
    exp = _create(client)
    _rename(client, exp, "renamed")
    before = client.get(f"/api/experiments/{exp}").json()["version"]
    _summary(client)
    _summary(client, window_days=90)
    after = client.get(f"/api/experiments/{exp}").json()["version"]
    assert after == before


# ==========================================================================
# the window
# ==========================================================================


def test_an_event_outside_the_window_is_in_the_all_time_total_and_not_the_window_one(
    client,
):
    """The two totals are different facts, and an old act is not made to vanish."""
    exp = _create(client)
    now = datetime.now(timezone.utc)
    _rewrite_activity(
        exp,
        [
            _event(1, _stamp(now - timedelta(days=40)), exp),
            _event(2, _stamp(now - timedelta(days=2)), exp),
        ],
    )
    body = _summary(client)
    assert body["totals"]["events_all_time"] == 2
    assert body["totals"]["events_in_window"] == 1
    assert body["changed_records"]["rows"][0]["events_in_window"] == 1

    # A WIDER WINDOW REACHES IT — proving the first figure was a property of the
    # window and not of a dropped event.
    wider = _summary(client, window_days=90)
    assert wider["totals"]["events_in_window"] == 2
    assert wider["window"]["days"] == 90


def test_the_window_bounds_are_served_so_a_label_cannot_disagree_with_its_figure(
    client,
):
    body = _summary(client, window_days=3)
    since = datetime.strptime(body["window"]["since_utc"], "%Y-%m-%dT%H:%M:%SZ")
    computed = datetime.strptime(body["window"]["computed_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
    assert computed - since == timedelta(days=3)
    assert body["window"]["days"] == 3


def test_an_out_of_range_window_is_refused_at_the_boundary(client):
    """A bounded parameter, refused with the admissible range rather than clamped —
    the route DECLARES the bound, so a caller learns the ceiling instead of guessing
    it. (`activity_history` clamps its `limit` instead, and the difference is
    deliberate: a clamped page is still an honest page, whereas a clamped window would
    silently answer a different question from the one asked.)"""
    assert client.get(SUMMARY, params={"window_days": 0}).status_code == 422
    assert (
        client.get(
            SUMMARY, params={"window_days": activity_summary.WINDOW_DAYS_MAX + 1}
        ).status_code
        == 422
    )
    assert (
        client.get(
            SUMMARY, params={"window_days": activity_summary.WINDOW_DAYS_MAX}
        ).status_code
        == 200
    )


def test_the_window_has_no_upper_bound_so_a_future_event_is_never_a_silent_bucket(
    client,
):
    """A future-dated stored event is COUNTED, not hidden.

    Clamping the top of the window at `now` would put it in neither bucket while the
    response reported nothing about it — a number the server holds and does not serve,
    which is the defect class this module's docstring names.
    """
    exp = _create(client)
    now = datetime.now(timezone.utc)
    _rewrite_activity(exp, [_event(1, _stamp(now + timedelta(days=5)), exp)])
    body = _summary(client)
    assert body["totals"]["events_in_window"] == 1
    assert body["totals"]["events_with_unreadable_timestamp"] == 0


# ==========================================================================
# malformed persisted data is READ, never refused
# ==========================================================================


def test_a_stored_entry_the_model_cannot_read_is_counted_rather_than_crashing(client):
    """`CLAUDE.md` §11's read-path rule. A malformed PERSISTED value must not make a
    reader's screen vanish — a read-path 500 has twice taken a whole list screen down
    in this repository."""
    exp = _create(client)
    now = datetime.now(timezone.utc)
    _rewrite_activity(
        exp,
        [
            _event(1, _stamp(now), exp),
            {"id": "broken", "seq": "not-an-integer"},
            7,
        ],
    )
    body = _summary(client)
    assert body["totals"]["unreadable_entries"] == 2
    assert body["totals"]["events_all_time"] == 1
    assert body["totals"]["events_in_window"] == 1


def test_an_unparseable_timestamp_is_its_own_count_and_is_in_neither_window_bucket(
    client,
):
    """A third answer, reported as one.

    Placing such an event inside the window or outside it would be a guess, and the
    guess would make one of the two window figures wrong by an amount nothing on the
    wire discloses.
    """
    exp = _create(client)
    now = datetime.now(timezone.utc)
    broken = _event(2, "whenever", exp)
    _rewrite_activity(exp, [_event(1, _stamp(now), exp), broken])
    body = _summary(client)
    assert body["totals"]["events_all_time"] == 2
    assert body["totals"]["events_in_window"] == 1
    assert body["totals"]["events_with_unreadable_timestamp"] == 1
    # It is NOT an unreadable ENTRY — the model read it fine; only its clock is
    # unreadable. Two different facts, two different counts.
    assert body["totals"]["unreadable_entries"] == 0


def test_a_naive_timestamp_is_unreadable_rather_than_assumed_to_be_utc(client):
    """Assuming a zone would be inventing one — `CLAUDE.md` §5."""
    exp = _create(client)
    _rewrite_activity(exp, [_event(1, "2099-01-01T00:00:00", exp)])
    body = _summary(client)
    assert body["totals"]["events_with_unreadable_timestamp"] == 1
    assert body["totals"]["events_in_window"] == 0


# ==========================================================================
# the bound, and the counts that must never come from a list
# ==========================================================================


def test_the_changed_record_count_is_not_the_length_of_the_row_list(client):
    """`CLAUDE.md` §11's measured defect: a count taken from a bounded list."""
    ids = [_create(client, f"Record {n}") for n in range(activity_summary.RECORD_ROWS + 3)]
    for exp in ids:
        _rename(client, exp, "renamed")
    body = _summary(client)
    assert body["changed_records"]["total"] == len(ids)
    assert body["changed_records"]["returned"] == activity_summary.RECORD_ROWS
    assert len(body["changed_records"]["rows"]) == activity_summary.RECORD_ROWS
    assert body["changed_records"]["total"] > body["changed_records"]["returned"]
    # AND THE EVENT TOTAL COVERS EVERY RECORD, not only the listed ones.
    assert body["totals"]["events_in_window"] == len(ids)


def test_a_truncated_scope_says_so_and_its_totals_describe_only_what_it_read():
    """The bound, exercised through the pure function because building 501 records
    over HTTP would be a slow test of the same arithmetic.

    `summarize` is where the bound lives; the route only passes rows to it.
    """

    class _Row:
        def __init__(self, key: str, events: list) -> None:
            self.id = key
            self.title = key
            self.activity = events
            self.unreadable_activity = []

    now = datetime.now(timezone.utc)

    def _one(key: str) -> list:
        return [
            activity.ActivityEvent(
                id=f"{key}-1",
                experiment_id=key,
                seq=1,
                recorded_utc=_stamp(now),
                actor=activity.ACTOR_UNATTRIBUTED,
                actor_trust_basis=activity.TRUST_BASIS_UNATTRIBUTED,
                channel=activity.CHANNEL_WEB,
                action=activity.ACTION_EXPERIMENT_RENAMED,
                object_type=activity.OBJECT_EXPERIMENT,
                object_id=key,
            )
        ]

    rows = [_Row(f"r{n:04d}", _one(f"r{n:04d}")) for n in range(12)]
    body = activity_summary.summarize(
        rows, now=now, hydration_complete=True, experiment_limit=10
    )
    assert body["scope"]["experiments_in_scope"] == 12
    assert body["scope"]["experiments_summarized"] == 10
    assert body["scope"]["truncated"] is True
    assert body["scope"]["selection"] == activity_summary.SELECTION_MOST_RECENTLY_CREATED
    # EVERY TOTAL IS A TOTAL OVER WHAT IT READ — 10, not 12. The response says so;
    # this asserts that it MEANS it.
    assert body["totals"]["events_all_time"] == 10
    assert body["totals"]["events_in_window"] == 10
    # THE TAIL, because the input is ordered by `created_utc` ascending. Pinned so a
    # future change to the selection cannot quietly become "the oldest ten".
    assert {row["experiment_id"] for row in body["changed_records"]["rows"]} <= {
        f"r{n:04d}" for n in range(2, 12)
    }
    assert "r0000" not in {row["experiment_id"] for row in body["changed_records"]["rows"]}


def test_hydration_completeness_is_passed_in_and_has_no_default():
    """A completeness claim this module cannot discover must not be publishable by
    omission — so the keyword is required and a caller has to state it."""
    with pytest.raises(TypeError):
        activity_summary.summarize([], now=datetime.now(timezone.utc))  # type: ignore[call-arg]


# ==========================================================================
# attribution — the figure this slice refuses to produce
# ==========================================================================


def test_attribution_reports_events_and_names_and_never_a_number_of_people(client):
    """`ACT-005` is blocked on `EXT-01`, so a headcount would be structurally `0` —
    and `0` there is a claim about the PEOPLE where the true statement is about the
    DEPLOYMENT.

    This is one of the file's few structural assertions, and it is structural because
    the claim is about a key that must NOT exist: no behaviour can demonstrate the
    absence of a figure.
    """
    exp = _create(client)
    _rename(client, exp, "renamed")
    body = _summary(client)
    attribution = body["attribution"]
    assert attribution["unattributed_events"] == 1
    assert attribution["attributed_events"] == 0
    assert attribution["attributed_actors"] == []
    assert attribution["actor_basis"] == activity.ACTOR_UNATTRIBUTED
    serialized = json.dumps(body)
    for forbidden in ("collaborator", "distinct_actors", "actor_count", "people"):
        assert forbidden not in serialized


# ==========================================================================
# a summary is not the source of truth, structurally
# ==========================================================================


def test_the_summary_carries_no_event_content_so_it_cannot_stand_in_for_the_history(
    client,
):
    """`DEC-44`: Statistics may summarize the history and must never be its source of
    truth. Asserted over the payload because the claim is about what is ABSENT — no
    event id, no `before`/`after` pair — which no behaviour can show.

    **THE FIRST VERSION OF THIS TEST ASSERTED THE WRONG STRING AND FAILED, correctly,
    and the correction is the more useful half.** It renamed the record to a
    distinctive phrase and then asserted that phrase absent — but the phrase was the
    record's CURRENT TITLE, which this summary legitimately carries (so does
    ``GET /api/experiments``) and which is how a reader recognises the row they are
    being sent to. The claim that matters is narrower and is what is asserted now: a
    PRIOR value, which lives only in an event's ``before``, never reaches the summary.
    So the record is renamed and the RETIRED title is the string under test.
    """
    exp = _create(client, "the title this record started with")
    _rename(client, exp, "the title a reader sees now")
    detail = client.get(f"/api/experiments/{exp}/activity").json()
    event = detail["events"][0]
    assert event["before"] == {
        "present": True,
        "value": "the title this record started with",
    }

    body = _summary(client)
    serialized = json.dumps(body)
    assert event["id"] not in serialized
    # THE PRIOR VALUE IS NOWHERE. Only the event holds it.
    assert "the title this record started with" not in serialized
    assert '"before"' not in serialized
    assert '"after"' not in serialized
    # The CURRENT title IS present, and that is correct rather than a leak: it is the
    # row's own name, and the row exists to be followed.
    assert body["changed_records"]["rows"][0]["title"] == "the title a reader sees now"
    # What it DOES carry, beside that name, is the address of the history holding the
    # values it does not.
    assert body["changed_records"]["rows"][0]["experiment_id"] == exp


def test_the_newest_event_matches_the_canonical_order_the_history_serves(client):
    """`_latest` uses `max` on `(seq, id)` rather than `sorted_events(...)[-1]` for
    one pass instead of a sort. They are the same event BY CONSTRUCTION — this pins
    it, so a future change to the canonical key cannot make the summary disagree with
    the per-record history about which act was last."""
    exp = _create(client)
    for n in range(3):
        _rename(client, exp, f"renamed {n}")
    detail = client.get(
        f"/api/experiments/{exp}/activity", params={"newest_first": "true"}
    ).json()
    newest = detail["events"][0]
    row = _summary(client)["changed_records"]["rows"][0]
    assert row["last_seq"] == newest["seq"]
    assert row["last_action"] == newest["action"]
    assert row["last_event_utc"] == newest["recorded_utc"]


def test_the_module_exposes_no_mutator():
    """There is no `record`, `append`, `revise`, `replace` or `delete` here — the same
    inventory claim `activity.py` and `activity_history.py` each make about
    themselves, restated for the third reader of the same append-only history."""
    exported = set(activity_summary.__all__)
    # THE VERB BAN APPLIES TO THE CALLABLES, not to every exported name. The first
    # version applied it to all of them and failed on `RECORD_ROWS` — a CONSTANT whose
    # name contains "record" and which mutates nothing. A ban that fires on a bound's
    # name is a ban that gets loosened rather than obeyed, so it is scoped instead.
    callables = {name for name in exported if callable(getattr(activity_summary, name))}
    assert callables == {"instant", "summarize"}
    for verb in ("record", "append", "revise", "replace", "delete", "write", "save"):
        assert not any(verb in name.lower() for name in callables), verb
    assert exported == {
        "DEFAULT_WINDOW_DAYS",
        "EXPERIMENT_LIMIT",
        "RECORD_ROWS",
        "SELECTION_MOST_RECENTLY_CREATED",
        "WINDOW_DAYS_MAX",
        "instant",
        "summarize",
    }

"""THE SEQUENCE COORDINATE the change feed's order is built on, and its edges.

WHY THIS FILE EXISTS SEPARATELY FROM ``test_change_feed.py``
============================================================
That file tests the FEED: what a page contains, what a cursor refuses, what the
published contract says. This one tests the thing underneath it — the durable
per-record sequence position (``Run.changed_at_rev``,
``Experiment.proposal_change_revs``, and ``Experiment.rev`` for the record itself)
that ``change_feed.ChangeEntry.key`` leads with. Those are ``workspace.py``'s to
maintain, and every property below is a property of the STORAGE that the feed's
correctness rests on rather than a property of the feed.

THE DEFECT THIS SEQUENCE REPLACED, in one sentence, because every test here is
shaped by it: the key used to lead with ``updated_utc``, which
``workspace._now_iso`` formats to WHOLE SECONDS, so a change landing inside the
second a cursor already named moved an entity's version without moving its key and
was **silently never reported by that cursor**. The regression test for that lives
in ``test_change_feed.py`` next to the feed it is about
(``test_a_same_second_write_behind_the_cursor_IS_REPORTED``, which is the old
``..._is_a_measured_gap`` inverted rather than deleted). What lives HERE is
everything the fix newly depends on:

  1. backward compatibility — there is NO migration and none is authorized, so a
     document persisted without the new fields has to hydrate to a defined value
  2. the coordinate stays OUT of the authoritative signature, so a content-identical
     re-entry is still a no-op (the reason is NOT the feedback loop ``workspace.py``
     first claimed — that was measured false; see section 2's tests)
  3. a position must never move BACKWARDS, including under concurrent writers
  4. paging over the sequence loses nothing and duplicates nothing

Everything here is synthetic: records created through ``POST /api/experiments`` or
constructed in process. No real data, no network, no database.
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from isaac_api import change_feed as cf
from isaac_api import routes
from isaac_api import workspace as ws


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def client(app) -> TestClient:
    return TestClient(app)


def _record(client: TestClient, *, runs: int = 0, title: str = "sequence") -> str:
    exp_id = client.post("/api/experiments", json={"title": title}).json()["id"]
    if runs:
        exp = ws.load_experiment(exp_id)
        for i in range(runs):
            exp.add_run(label=f"Run {i + 1}", draft=routes._seed_for_new_run(exp))
        exp.save_versioned()
    return exp_id


def _touch_run(exp_id: str, run_id: str, value: str) -> None:
    """One real versioned write that changes exactly one run."""
    exp = ws.load_experiment(exp_id)
    run = next(r for r in exp.runs if r.id == run_id)
    run.draft.setdefault("fields", {})["context.beamline"] = {
        "value": value,
        "status": "verified",
    }
    assert exp.save_versioned() is True


def _make_proposal(exp, *, pid: str, value: str = "XANES", base_rev: int | None = None):
    """One synthetic proposal appended to ``exp.proposals``. NOT saved.

    Imported inside the helper for ``test_change_feed.py``'s reason: the feed module
    must import nothing from ``proposals``, and a module-level import in a test file
    about the feed reads as though it did.
    """
    from isaac_api import proposals as proposals_module

    proposal = proposals_module.new_proposal(
        proposal_id=pid,
        experiment_id=exp.id,
        note_id="01SYNTHETICNOTENOTENOTENO",
        target_field_path="field:system.technique",
        proposed_value=value,
        rule="synthetic fixture rule — this file asserts ordering, not science",
        source=sorted(proposals_module.PROPOSAL_SOURCES)[0],
        proposed_utc="2026-01-01T00:00:00Z",
        # ``base_rev`` IS OVERRIDABLE, and it has to be. It is part of the proposal's
        # stored state and therefore of its signature, so a test that rebuilds a
        # proposal to be BYTE-IDENTICAL to an earlier one must be able to hold it
        # fixed — otherwise the rebuild differs in a field the test is not about and
        # the untouched branch it is aiming at is never reached.
        base_rev=exp.rev if base_rev is None else base_rev,
        target_digest="0000000000000000",
        trust_basis=proposals_module._unattributed(),
    )
    exp.proposals.append(proposal)
    return proposal


def _walk(client: TestClient, exp_id: str, *, limit: int) -> list[dict]:
    """Every entry the feed hands out, paged from the start, one page at a time.

    Returns entries in the order they were RETURNED, so a caller can assert on
    duplicates and on loss separately — a set would hide the first.
    """
    seen: list[dict] = []
    cursor: str | None = None
    for _ in range(1000):  # a bound, so a non-terminating feed fails rather than hangs
        params = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        res = client.get(f"/api/experiments/{exp_id}/changes", params=params)
        assert res.status_code == 200, res.text
        page = res.json()
        seen.extend(page["changes"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            return seen
    raise AssertionError("the feed did not terminate")


# =============================================================================
# 1. BACKWARD COMPATIBILITY — there is no migration, and none is authorized
# =============================================================================


def test_a_state_document_written_before_the_sequence_existed_hydrates(client):
    """THE NO-MIGRATION REQUIREMENT, measured on a document that genuinely lacks both.

    ``CLAUDE.md`` §15 permits no new table and this slice adds no migration, so the
    ONLY thing standing between a pre-existing state file and a 500 is the hydration
    default. The keys are stripped from the persisted document rather than simulated
    by constructing an object without them, because ``from_state`` is the function
    that has to tolerate their absence and a bare construction never calls it.

    A DEFAULT OF ``0`` IS ASSERTED, NOT MERELY "no exception". ``0`` means "no
    versioned save has ever recorded this entity changing", which is precisely true of
    a document written before the coordinate existed. The alternative that would also
    avoid an exception — defaulting to the record's CURRENT ``rev`` — would assert
    that every entity changed at a revision it may never have been touched at, and the
    feed would then report a change that did not happen.
    """
    exp_id = _record(client, runs=3, title="legacy")
    exp = ws.load_experiment(exp_id)
    _make_proposal(exp, pid="01SYNTHETICPROPOSALPROPOS")
    exp.save_versioned()

    raw = json.loads(exp.state_path.read_text(encoding="utf-8"))
    # The precondition: this build DOES write both, so stripping them is a real
    # downgrade and not a no-op that would make the test vacuous.
    assert "proposal_change_revs" in raw
    assert all("changed_at_rev" in r for r in raw["runs"])
    raw.pop("proposal_change_revs")
    for run in raw["runs"]:
        run.pop("changed_at_rev")
    exp.state_path.write_text(json.dumps(raw), encoding="utf-8")

    legacy = ws.load_experiment(exp_id)
    assert legacy is not None
    assert [r.changed_at_rev for r in legacy.runs] == [0, 0, 0]
    assert legacy.proposal_change_revs == {}

    # And every entity is still SERVED — a coordinate of 0 sorts first, it does not
    # disappear. `ZERO_KEY` is (-1, "", ""), strictly below it.
    page = client.get(f"/api/experiments/{exp_id}/changes").json()
    assert page["returned"] == 5  # the record, three runs, one proposal
    assert {c["changed_at_rev"] for c in page["changes"] if c["kind"] != "experiment"} == {0}


def test_a_legacy_document_resumes_a_cursor_correctly_once_it_moves(client):
    """The legacy default is safe under PAGING, which is the case that could lose data.

    Every entity at 0 means the whole record sits at one sequence position and the
    `(kind, entity_id)` tie-break is doing all of the ordering — the exact condition
    the old timestamp key lost changes in. The sequence still saves it, because the
    first real change moves the changed entity to a position strictly above every
    legacy one.
    """
    exp_id = _record(client, runs=4, title="legacy paging")
    exp = ws.load_experiment(exp_id)
    raw = json.loads(exp.state_path.read_text(encoding="utf-8"))
    for run in raw["runs"]:
        run.pop("changed_at_rev")
    raw["rev"] = 0
    exp.state_path.write_text(json.dumps(raw), encoding="utf-8")

    page = client.get(f"/api/experiments/{exp_id}/changes", params={"limit": 2}).json()
    assert page["has_more"] is True
    assert {c["changed_at_rev"] for c in page["changes"]} == {0}
    cursor = page["next_cursor"]
    already = {c["entity_id"] for c in page["changes"]}

    # A run page one ALREADY handed out changes. Under the legacy-zero key it would
    # sit behind the cursor forever.
    target = next(c["entity_id"] for c in page["changes"] if c["kind"] == "run")
    _touch_run(exp_id, target, "BL-SYNTH")

    resumed = client.get(
        f"/api/experiments/{exp_id}/changes", params={"cursor": cursor}
    ).json()
    reported = [c["entity_id"] for c in resumed["changes"]]
    assert target in reported
    assert len(reported) == len(set(reported))
    # ...and the entity from page one that did NOT change is not re-reported.
    untouched = already - {target, exp_id}
    assert not (untouched & set(reported))


def test_the_state_round_trip_is_byte_stable_with_and_without_the_new_fields(client):
    """``to_state`` -> ``from_state`` -> ``to_state`` is byte-identical, both ways.

    TWO ROUND TRIPS, not one, because they answer different questions. The first is
    over a document this build wrote: nothing is lost or reordered by a load-and-save,
    which is what makes a save that changes nothing write nothing. The second is over
    a document written BEFORE the fields existed: it gains them at their defaults and
    is then stable, so the upgrade is a one-time widening rather than a value that
    churns on every save.

    ``sort_keys`` IS NOT USED. The comparison is over ``json.dumps`` of the dict in
    ITERATION order, so a key that moved position — which a reader diffing two state
    files would see — fails here too.
    """
    exp_id = _record(client, runs=2, title="round trip")
    exp = ws.load_experiment(exp_id)
    _make_proposal(exp, pid="01SYNTHETICPROPOSALPROPOS")
    exp.save_versioned()

    original = ws.load_experiment(exp_id).to_state()
    again = ws.Experiment.from_state(original).to_state()
    assert json.dumps(again) == json.dumps(original)

    # The new keys are actually IN there, so the equality above is not two copies of
    # a document that never carried them.
    assert original["proposal_change_revs"] == {"01SYNTHETICPROPOSALPROPOS": exp.rev}
    assert all("changed_at_rev" in r for r in original["runs"])

    # ...and the legacy shape converges after exactly one round trip.
    #
    # THE MAP COMES BACK EMPTY, NOT ``{pid: 0}``, and the asymmetry with ``runs`` is
    # deliberate rather than an oversight. A run CARRIES its coordinate, so a run whose
    # key was stripped hydrates with the field at its default and the field is written
    # back. A proposal does NOT carry one — the coordinate lives in a map beside the
    # proposals — so an absent map is an absent ENTRY, and an absent entry already
    # means 0 by ``_proposal_entries``' ``positions.get(pid, 0)``. Materialising
    # ``{pid: 0}`` would write a coordinate no save produced in order to say the same
    # thing the absence already says.
    legacy = json.loads(json.dumps(original))
    legacy.pop("proposal_change_revs")
    for run in legacy["runs"]:
        run.pop("changed_at_rev")
    upgraded = ws.Experiment.from_state(legacy).to_state()
    assert upgraded["proposal_change_revs"] == {}
    assert [r["changed_at_rev"] for r in upgraded["runs"]] == [0, 0]
    assert json.dumps(ws.Experiment.from_state(upgraded).to_state()) == json.dumps(upgraded)

    # AND THE ABSENCE READS AS 0 AT THE FEED, which is the claim the paragraph above
    # rests on — asserted rather than argued, because "an absent entry already means 0"
    # is exactly the kind of sentence that stops being true without anyone noticing.
    exp.state_path.write_text(json.dumps(upgraded), encoding="utf-8")
    page = client.get(f"/api/experiments/{exp_id}/changes").json()
    proposal_entry = next(c for c in page["changes"] if c["kind"] == "proposal")
    assert proposal_entry["changed_at_rev"] == 0


@pytest.mark.parametrize(
    "persisted,expected,why",
    [
        pytest.param(None, {}, "an absent key is the legacy case", id="absent"),
        pytest.param("nope", {}, "a non-object is not a map", id="not-a-dict"),
        pytest.param([1, 2], {}, "a list is not a map", id="list"),
        pytest.param({"p": 3}, {"p": 3}, "the ordinary case", id="ok"),
        pytest.param({"p": "3"}, {}, "a string is not coerced to 3", id="string"),
        pytest.param({"p": 3.0}, {}, "a float is not a sequence position", id="float"),
        pytest.param({"p": True}, {}, "isinstance(True, int) is True in Python", id="bool"),
        pytest.param({"p": -1}, {}, "a negative would sit below the start of the order", id="negative"),
        pytest.param({"p": None}, {}, "null is not a position", id="null"),
        pytest.param({"": 3}, {}, "an empty id names nothing", id="empty-key"),
        pytest.param({3: 3}, {}, "a non-string key is not a proposal id", id="non-string-key"),
        pytest.param({"a": 1, "b": "x"}, {"a": 1}, "one bad entry drops itself, not the map", id="partial"),
    ],
)
def test_a_wrong_typed_persisted_position_is_DROPPED_never_coerced(persisted, expected, why):
    """``_hydrate_change_revs`` on the READ path: never raises, never invents.

    DROPPING IS THE POINT, and it is not the same as tolerating. A dropped entry lands
    in exactly the bucket a MISSING entry was already in — 0, "no versioned save has
    recorded this proposal changing" — where the existing policy applies unchanged and
    the entity is still served. Coercing instead would put an entity at a position in
    the feed's order that no save ever produced, and a client would then be told a
    change happened at a revision that does not exist.

    IT NEVER RAISES because this is the read path. ``CLAUDE.md`` §11 records the two
    500s a persisted wrong-typed value already caused here — one malformed run draft
    took the whole My Experiments screen down — and the rule that came out of it: a
    malformed value in a REQUEST can be refused, because the caller sent it; a
    malformed value already PERSISTED cannot be refused to the reader, who did nothing
    wrong and whose record would simply vanish.
    """
    assert ws._hydrate_change_revs(persisted) == expected, why


def test_a_negative_persisted_run_position_is_clamped_and_still_served(client):
    """A run at ``-5`` on disk must not sit BELOW the start of the order.

    ``change_feed.ZERO_KEY`` is ``(-1, "", "")`` and every read starts strictly after
    it, so an entity whose position hydrated as ``-5`` would be returned by no request
    at all — not by a cursor, and not by the cursorless resync that the published
    ``GAP_GUARANTEE`` offers as the remedy for everything. It would be invisible, which
    is worse than being reported late.
    """
    exp_id = _record(client, runs=2, title="negative run position")
    exp = ws.load_experiment(exp_id)
    raw = json.loads(exp.state_path.read_text(encoding="utf-8"))
    raw["runs"][0]["changed_at_rev"] = -5
    exp.state_path.write_text(json.dumps(raw), encoding="utf-8")

    reloaded = ws.load_experiment(exp_id)
    assert reloaded.runs[0].changed_at_rev == 0, "clamped by Run.__post_init__"

    page = client.get(f"/api/experiments/{exp_id}/changes").json()
    assert raw["runs"][0]["id"] in {c["entity_id"] for c in page["changes"]}
    assert min(c["changed_at_rev"] for c in page["changes"]) >= 0


def test_a_negative_persisted_RECORD_rev_still_appears_in_its_own_feed(client):
    """THE HOLE THE FIRST VERSION OF THIS SLICE LEFT, and it is the record's own entry.

    ``Run.changed_at_rev`` is clamped in ``__post_init__`` and a proposal's position is
    dropped by ``_hydrate_change_revs`` if it is negative — but the EXPERIMENT's
    coordinate is ``exp.rev`` itself, hydrated by ``_as_int``, which never raises and
    never validates. A persisted ``"rev": -5`` therefore reached ``ChangeEntry.key``
    unclamped and put the record's own entry at ``(-5, ...)``, strictly BELOW
    ``ZERO_KEY``, where no read returns it. The entry ``_experiment_entries``
    documents as "exactly one, always present" was absent, and the module's own
    ``ZERO_KEY`` comment asserted this could not happen.

    Two changes close it and both are asserted here: ``change_feed._position`` floors
    what is READ, and ``save_versioned``'s ``max(self.rev, disk_rev, 0) + 1`` floors
    what is WRITTEN — the second matters because without it the next save would reach
    ``-4`` and stamp every entity it changed at a negative position.
    """
    exp_id = _record(client, runs=1, title="negative rev")
    exp = ws.load_experiment(exp_id)
    raw = json.loads(exp.state_path.read_text(encoding="utf-8"))
    raw["rev"] = -5
    exp.state_path.write_text(json.dumps(raw), encoding="utf-8")

    page = client.get(f"/api/experiments/{exp_id}/changes").json()
    record_entry = next(c for c in page["changes"] if c["kind"] == "experiment")
    assert record_entry["entity_id"] == exp_id
    assert record_entry["changed_at_rev"] == 0
    # `rev` is published VERBATIM — the floor is on the ORDER, not on the entity's own
    # version number, which every other route also serves.
    assert record_entry["rev"] == -5

    # ...and the next write lands strictly above, rather than at -4.
    run_id = next(c["entity_id"] for c in page["changes"] if c["kind"] == "run")
    _touch_run(exp_id, run_id, "BL-SYNTH")
    after = client.get(f"/api/experiments/{exp_id}/changes").json()
    assert min(c["changed_at_rev"] for c in after["changes"]) >= 0
    assert next(c for c in after["changes"] if c["kind"] == "experiment")["rev"] == 1


@pytest.mark.parametrize(
    "raw,expected,why",
    [
        pytest.param(7, 7, "the ordinary case", id="int"),
        pytest.param(0, 0, "0 is a real position, not a missing value", id="zero"),
        pytest.param(-5, 0, "THE LIVE BRANCH: the lower floor", id="negative"),
        pytest.param("7", 0, "a string is not a position", id="string"),
        pytest.param(3.9, 0, "a float is not a position", id="float"),
        pytest.param(True, 0, "isinstance(True, int) is True in Python", id="bool"),
        pytest.param(False, 0, "…and so is False", id="bool-false"),
        pytest.param(None, 0, "null is not a position", id="null"),
        pytest.param([3], 0, "a list is not a position", id="list"),
    ],
)
def test_position_refuses_a_non_integer_and_a_bool(raw, expected, why):
    """``change_feed._position`` DIRECTLY, because nothing tested it at all.

    ``grep _position apps/api/tests/`` matched only docstring mentions before this,
    which is how the function's own docstring came to name two examples that were the
    opposite of what happens — nothing was exercising the branch the claim was about.

    WHAT THIS PROVES AND WHAT IT DELIBERATELY DOES NOT. It proves the function
    behaves as documented for every input class, including the ``bool`` exclusion that
    ``isinstance(True, int)`` makes necessary. It does NOT prove that a persisted
    document can reach those branches — it cannot, and the test immediately below
    measures why. The guard is reachable from a directly-constructed ``ChangeEntry``
    and from a future collector reading something ``workspace`` does not hydrate,
    which is the only claim made for it.
    """
    assert cf._position(raw) == expected, why


@pytest.mark.parametrize(
    "persisted,served,why",
    [
        pytest.param("7", 7, '`int("7") == 7`', id="string"),
        pytest.param(True, 1, "`int(True) == 1`", id="bool"),
        pytest.param(3.9, 3, "`int(3.9) == 3`, truncating", id="float"),
    ],
)
def test_a_wrong_typed_persisted_POSITION_is_COERCED_by_hydration_not_refused(
    client, persisted, served, why
):
    """THE MEASUREMENT ``_position``'s DOCSTRING GOT BACKWARDS, recorded so it stays.

    ``_position`` used to claim that a ``changed_at_rev`` of ``True`` "would
    otherwise read as the position 1" and that "nothing is coerced". Both named
    examples are exactly what a persisted document produces, because hydration runs
    FIRST: ``Run.from_state`` and ``Experiment.from_state`` read these two coordinates
    through ``workspace._as_int``, which coerces, so the value ``_position`` receives
    is already an ``int`` and its type branch never fires.

    THIS TEST RECORDS THE BEHAVIOUR; IT DOES NOT ENDORSE IT. Two candidate fixes were
    weighed and the docstring was corrected rather than the hydration tightened.
    ``CLAUDE.md`` §11 is emphatic that a malformed PERSISTED value must be READ, and
    the coercion IS a form of reading it — nothing 500s, nothing vanishes. Tightening
    it at the hydration boundary is not free either: ``rev`` is also the record's
    served ``version`` token and the basis of every ``If-Match``, so dropping a
    coerced ``"7"`` to ``0`` would move a record's version BACKWARDS and could let a
    stale token match. That trades a wrong docstring for a concurrency hazard.

    BOTH COORDINATES ARE MEASURED, because the docstring named both. The run's
    position and the record's own ``rev`` go through the same coercion.
    """
    exp_id = _record(client, runs=1, title="coerced position")
    exp = ws.load_experiment(exp_id)
    raw = json.loads(exp.state_path.read_text(encoding="utf-8"))
    run_id = raw["runs"][0]["id"]
    raw["runs"][0]["changed_at_rev"] = persisted
    raw["rev"] = persisted
    exp.state_path.write_text(json.dumps(raw), encoding="utf-8")

    page = client.get(f"/api/experiments/{exp_id}/changes").json()
    run_entry = next(c for c in page["changes"] if c["entity_id"] == run_id)
    record_entry = next(c for c in page["changes"] if c["kind"] == "experiment")
    assert run_entry["changed_at_rev"] == served, why
    assert record_entry["changed_at_rev"] == served, why


def test_an_ABSURD_persisted_position_over_reports_rather_than_omitting(client):
    """THE UPPER BOUND IS NOT CLAMPED, and the consequence is bounded the safe way.

    The mirror of ``test_a_negative_persisted_RECORD_rev_still_appears_in_its_own_feed``,
    and the reason ``_position`` calls itself "the one clamp" about the LOWER bound
    only. A persisted ``10 ** 30`` is served verbatim as a position: no cursor a
    client can hold will ever advance past it, so that entity is reported on every
    poll for as long as it holds that value.

    IT IS DISCLOSED RATHER THAN CLAMPED BECAUSE THE FAILURE DIRECTION IS THE
    RECOVERABLE ONE. Over-reporting an entity is what a state feed already does when
    something changes twice; silently omitting one is the defect this whole slice
    exists to close. An upper clamp would have to invent a ceiling, and a ceiling set
    wrong WOULD omit. Both halves are asserted: the entity keeps being reported, and
    the cursorless resync still returns the whole record.
    """
    exp_id = _record(client, runs=2, title="absurd position")
    exp = ws.load_experiment(exp_id)
    raw = json.loads(exp.state_path.read_text(encoding="utf-8"))
    loud_run = raw["runs"][0]["id"]
    quiet_run = raw["runs"][1]["id"]
    raw["runs"][0]["changed_at_rev"] = 10**30
    exp.state_path.write_text(json.dumps(raw), encoding="utf-8")

    first = client.get(f"/api/experiments/{exp_id}/changes").json()
    assert first["changes"][-1]["entity_id"] == loud_run  # last in the order
    assert first["changes"][-1]["changed_at_rev"] == 10**30

    # A cursor at the end of that page is now ABOVE every ordinary position, so the
    # loud entity is re-reported and the quiet ones are not. That is the cost.
    held = client.get(
        f"/api/experiments/{exp_id}/changes", params={"cursor": first["next_cursor"]}
    ).json()
    assert held["changes"] == []
    # …and it is capped: the resync remedy the contract publishes still works, and
    # still names both runs at their current positions.
    resync = client.get(f"/api/experiments/{exp_id}/changes").json()
    assert {loud_run, quiet_run} <= {c["entity_id"] for c in resync["changes"]}


def test_a_persisted_Infinity_rev_is_READ_as_0_rather_than_500(client):
    """``_as_int`` PROMISED "never raises" AND RAISED, on a value JSON really carries.

    ``int(float("inf"))`` raises ``OverflowError``, which is neither ``TypeError`` nor
    ``ValueError``, so it escaped ``_as_int``'s except clause — and ``json.loads``
    accepts the bare token ``Infinity`` by default, so this is a document a foreign
    writer can produce rather than a construction only a test can reach. The measured
    result was an HTTP 500 on three read paths, under a docstring saying it could not
    happen.

    PRE-EXISTING, NOT INTRODUCED HERE — ``_as_int`` is byte-identical on ``bebf4e2``
    for this clause — but this slice adds a call site and prose asserting the promise,
    so the promise is made true rather than the prose weakened. ``0`` is the bucket
    every other unreadable value already lands in, which is ``CLAUDE.md`` §11's rule:
    the reader did nothing wrong and their record must not vanish.

    THE WHOLE-WORKSPACE LIST IS ASSERTED TOO, because that is the path a malformed
    document has taken down before: one bad record used to 500 My Experiments for
    every record.
    """
    exp_id = _record(client, runs=1, title="infinite rev")
    exp = ws.load_experiment(exp_id)
    text = exp.state_path.read_text(encoding="utf-8")
    raw = json.loads(text)
    raw["rev"] = 1
    # Written as the literal token, because that is what a foreign writer would emit
    # and what `json.dumps(float("inf"))` itself produces.
    exp.state_path.write_text(
        json.dumps(raw).replace('"rev": 1', '"rev": Infinity'), encoding="utf-8"
    )
    assert "Infinity" in exp.state_path.read_text(encoding="utf-8")

    assert ws._as_int(float("inf")) == 0
    assert ws._as_int(float("-inf")) == 0
    assert ws.load_experiment(exp_id).rev == 0

    page = client.get(f"/api/experiments/{exp_id}/changes")
    assert page.status_code == 200, page.text
    assert next(c for c in page.json()["changes"] if c["kind"] == "experiment")["rev"] == 0
    assert client.get(f"/api/experiments/{exp_id}").status_code == 200
    assert client.get("/api/experiments").status_code == 200


# =============================================================================
# 2. THE COORDINATE STAYS OUT OF THE AUTHORITATIVE SIGNATURE
# =============================================================================


def test_saving_an_unchanged_record_twice_writes_nothing(client):
    """THE BYTE-STABLE NO-OP still holds with the sequence coordinates in the document.

    Adding a key to a persisted document is a chance to make every save write, and this
    is the cheapest check that it did not: load, save, and measure the FILE. A record
    that rewrote itself on every poll would move every entity's position on every poll,
    and the feed would report the whole record as changed forever.

    MEASURED AS BYTES ON DISK, not as a return value alone. ``save_versioned`` -> False
    is the decision; the file being byte-identical is the consequence, and a build that
    returned False while rewriting the document would pass the weaker assertion.

    THIS TEST DOES **NOT** PROVE THE ABSENCE OF A FEEDBACK LOOP, and an earlier
    docstring in ``workspace.py`` cited it as though it did. It cannot: with
    ``changed_at_rev`` deliberately ADDED to ``_run_signature_payload``, this test
    still passes — measured — because both sides of the signature comparison read the
    same on-disk number. The real property that exclusion buys is the next test's.
    """
    exp_id = _record(client, runs=3, title="no feedback")
    exp = ws.load_experiment(exp_id)
    _make_proposal(exp, pid="01SYNTHETICPROPOSALPROPOS")
    assert exp.save_versioned() is True

    before = exp.state_path.read_bytes()
    assert ws.load_experiment(exp_id).save_versioned() is False
    assert exp.state_path.read_bytes() == before
    assert ws.load_experiment(exp_id).save_versioned() is False
    assert exp.state_path.read_bytes() == before


def test_a_stale_object_whose_CONTENT_matches_disk_writes_nothing(client):
    """WHY THE COORDINATE IS EXCLUDED FROM THE SIGNATURE — the real reason, measured.

    ``workspace.py`` justified the exclusion with a feedback loop: "every save of an
    untouched record would bump every run forever". That was measured FALSE (see
    ``_run_signature_payload``, where the claim is struck rather than replaced). This is
    the property that IS true and that the exclusion actually buys.

    THE SETUP IS THE ONE CASE WHERE THE TWO SIDES DISAGREE. A writer loads a record;
    another writer changes a run and then changes it back byte-for-byte; the first
    writer's copy now matches disk in CONTENT and is two saves behind in POSITION. With
    the position out of the signature, its re-entry is correctly a no-op. With the
    position IN the signature, the signatures differ in that number alone, the no-op
    becomes a WRITE, and this stale writer's older document overwrites the other's.

    MUTATION: add ``"changed_at_rev": run.changed_at_rev`` to
    ``_run_signature_payload``, and the final assertions go red — ``save_versioned``
    returns True and the file changes.
    """
    exp_id = _record(client, runs=2, title="stale no-op")
    stale = ws.load_experiment(exp_id)
    target_id = stale.runs[0].id
    original_draft = json.loads(json.dumps(stale.runs[0].draft))
    stale_position = stale.runs[0].changed_at_rev

    _touch_run(exp_id, target_id, "BL-B")

    back = ws.load_experiment(exp_id)
    run = next(r for r in back.runs if r.id == target_id)
    run.draft = json.loads(json.dumps(original_draft))
    assert back.save_versioned() is True
    disk_position = next(
        r.changed_at_rev for r in ws.load_experiment(exp_id).runs if r.id == target_id
    )
    assert disk_position > stale_position, "precondition: the positions disagree"

    # The stale object's CONTENT is identical to disk; only the position differs.
    on_disk = ws.load_experiment(exp_id)
    assert ws._run_signature(on_disk.runs[0]) == ws._run_signature(stale.runs[0])
    assert on_disk.title == stale.title

    before = stale.state_path.read_bytes()
    assert stale.save_versioned() is False, (
        "a content-identical re-entry wrote, and would have overwritten the other "
        "writer's document"
    )
    assert stale.state_path.read_bytes() == before


def test_a_refused_write_rolls_back_the_sequence_coordinates(client, monkeypatch):
    """A refused save must not leave an entity at a position that exists nowhere.

    BOTH HALVES, because they fail differently. The record's own ``rev`` rolls back to
    the persisted value while a run or a proposal, if its coordinate were left
    advanced, would sit AHEAD of the record — so a client whose cursor is at the
    record's real position would be handed an entry claiming a revision that was never
    written. And the next successful save reaches that same number, finds the
    coordinate already there, and reports nothing new: a version nobody can reach and
    a change nobody is told about, from one un-rolled-back integer.
    """
    exp_id = _record(client, runs=2, title="rollback")
    exp = ws.load_experiment(exp_id)
    _make_proposal(exp, pid="01SYNTHETICPROPOSALPROPOS")
    assert exp.save_versioned() is True

    persisted = ws.load_experiment(exp_id)
    before_rev = persisted.rev
    before_runs = {r.id: r.changed_at_rev for r in persisted.runs}
    before_proposals = dict(persisted.proposal_change_revs)

    doomed = ws.load_experiment(exp_id)
    doomed.runs[0].label = "Renamed"
    _make_proposal(doomed, pid="01SYNTHETICPROPOSALTWOTWO", value="EXAFS")

    def _explode(self):
        raise RuntimeError("the durable write refused")

    # SAVED AND RESTORED BY HAND rather than with ``monkeypatch.undo()``. The ``app``
    # fixture sets ``ISAAC_UI_WORKSPACE`` through the SAME ``monkeypatch`` instance, so
    # ``undo()`` unsets the workspace and every later ``load_experiment`` answers
    # ``None`` — which reads as "the refused write destroyed the record".
    real_save = ws.Experiment.save
    ws.Experiment.save = _explode
    try:
        with pytest.raises(RuntimeError):
            doomed.save_versioned()
    finally:
        ws.Experiment.save = real_save

    assert doomed.rev == before_rev
    assert {r.id: r.changed_at_rev for r in doomed.runs} == before_runs
    # The proposal that already existed is back at its recorded position; the one this
    # failed write introduced has no position claiming a revision nothing wrote.
    assert doomed.proposal_change_revs == before_proposals

    # AND THE DISK NEVER MOVED, which is the half a rollback of in-memory state alone
    # would pass while having written a document.
    reread = ws.load_experiment(exp_id)
    assert reread.rev == before_rev
    assert {r.id: r.changed_at_rev for r in reread.runs} == before_runs
    assert reread.proposal_change_revs == before_proposals


# =============================================================================
# 3. A POSITION NEVER MOVES BACKWARDS
# =============================================================================


def test_a_stale_writer_cannot_regress_a_position_it_did_not_change(client):
    """THE ABA CASE, deterministic — and the reason the untouched branch clamps.

    ``_bump_changed_runs`` SKIPS a run whose signature matches disk, so that run keeps
    whatever its in-memory copy holds. Hold an experiment object across two other
    writes that change a run and then change it BACK, and the stale copy's content
    matches disk again while its POSITION is two saves behind. Writing that position
    back would move the run backwards in the feed's order, into a range every cursor
    has already passed — and a change that lands below a cursor is a change that cursor
    will never report.

    THE REVERT HAS TO BE EXACT, AND THE FIRST VERSION OF THIS TEST'S WAS NOT. It added
    a field with ``draft.setdefault("fields", {})`` and removed it with ``pop``, which
    leaves an empty ``fields`` dict where the seed had no such key at all — so the
    run's signature never returned to its original value, the stale writer's copy did
    NOT match disk, the run was stamped rather than skipped, and the test passed
    without ever entering the branch it exists for. It is recorded rather than quietly
    fixed because a negative control that never reaches its own code path is worse than
    no control: it reads as coverage. The revert is now a deep copy of the captured
    original, and the precondition is ASSERTED at the signature.

    THE STALE WRITE ALSO CHANGES THE TITLE, deliberately. An exact revert of the only
    change makes the record's whole authoritative signature equal what is on disk, and
    ``save_versioned`` correctly writes NOTHING — so without a second, unrelated change
    the stale save is a no-op and the skip branch is never reached either.

    MUTATION: replace ``max(run.changed_at_rev, prior[2])`` in ``_bump_changed_runs``
    with the bare ``continue``, and the final assertion goes red.
    """
    exp_id = _record(client, runs=2, title="ABA")
    stale = ws.load_experiment(exp_id)
    target_id = stale.runs[0].id
    stale_position = stale.runs[0].changed_at_rev
    original_signature = ws._run_signature(stale.runs[0])
    original_draft = json.loads(json.dumps(stale.runs[0].draft))

    # A -> B on the target run, by a writer that is NOT the stale object.
    _touch_run(exp_id, target_id, "BL-B")
    moved_position = next(
        r.changed_at_rev for r in ws.load_experiment(exp_id).runs if r.id == target_id
    )
    assert moved_position > stale_position

    # B -> A, exactly, plus an unrelated change so the record still has something to
    # write.
    back = ws.load_experiment(exp_id)
    run = next(r for r in back.runs if r.id == target_id)
    run.draft = json.loads(json.dumps(original_draft))
    back.title = "ABA, renamed by the reverting writer"
    assert back.save_versioned() is True
    restored = next(r for r in ws.load_experiment(exp_id).runs if r.id == target_id)
    restored_position = restored.changed_at_rev
    assert restored_position > moved_position
    # THE PRECONDITION, measured: the run's content is byte-for-byte what the stale
    # object holds, so the stale save WILL take the skip branch.
    assert ws._run_signature(restored) == original_signature

    # The stale object now agrees with disk about the run's CONTENT and disagrees
    # about its POSITION. It saves something unrelated.
    stale.title = "ABA, renamed by a stale writer"
    assert stale.save_versioned() is True

    final = next(r for r in ws.load_experiment(exp_id).runs if r.id == target_id)
    assert ws._run_signature(final) == original_signature, "the run really was skipped"
    assert final.changed_at_rev >= restored_position, (
        "a stale writer moved a run BACKWARDS in the feed's order"
    )


def test_a_stale_writer_cannot_regress_a_PROPOSAL_position(client):
    """The same defect one entity kind over, and it needs its own test.

    ``_bump_changed_proposals``' untouched branch reads ``self.proposal_change_revs``,
    which is a map on the stale OBJECT rather than a field on the entity, so the run
    test above cannot reach it. The clamp is the same shape and so is the failure: a
    proposal written backwards sits below cursors that have already passed it.

    A PROPOSAL HAS NO IN-PLACE MUTATOR — every act in ``proposals.py`` returns a NEW
    frozen object — so the A -> B -> A here is done by rebuilding the identical
    proposal, which is what a revert of an accidental edit would produce.

    MUTATION: replace ``max(self.proposal_change_revs.get(pid, 0), prior[1])`` with
    ``self.proposal_change_revs.get(pid, 0)``, and the final assertion goes red.
    """
    pid = "01SYNTHETICPROPOSALPROPOS"
    exp_id = _record(client, runs=1, title="proposal ABA")
    seed = ws.load_experiment(exp_id)
    _make_proposal(seed, pid=pid, value="XANES")
    assert seed.save_versioned() is True

    stale = ws.load_experiment(exp_id)
    stale_position = stale.proposal_change_revs[pid]
    original_signature = ws._proposal_signature(stale.proposals[0])
    anchor_rev = stale.proposals[0].base_rev

    # A -> B: the proposal is replaced by one that differs.
    edited = ws.load_experiment(exp_id)
    edited.proposals = []
    _make_proposal(edited, pid=pid, value="EXAFS", base_rev=anchor_rev)
    assert edited.save_versioned() is True
    moved_position = ws.load_experiment(exp_id).proposal_change_revs[pid]
    assert moved_position > stale_position

    # B -> A: rebuilt BYTE-IDENTICALLY — ``base_rev`` pinned to the original, or the
    # rebuild would differ in a field this test is not about and would be stamped
    # rather than skipped, which is how the first version of this test passed without
    # entering the branch it exists for.
    back = ws.load_experiment(exp_id)
    back.proposals = []
    _make_proposal(back, pid=pid, value="XANES", base_rev=anchor_rev)
    back.title = "proposal ABA, reverted"
    assert back.save_versioned() is True
    restored_position = ws.load_experiment(exp_id).proposal_change_revs[pid]
    assert restored_position > moved_position
    # THE PRECONDITION, measured at the signature: the stale object's proposal is
    # byte-for-byte what is on disk, so its save WILL take the untouched branch.
    assert (
        ws._proposal_signature(ws.load_experiment(exp_id).proposals[0])
        == original_signature
    )

    stale.title = "proposal ABA, renamed by a stale writer"
    assert stale.save_versioned() is True

    final = ws.load_experiment(exp_id)
    assert final.proposals[0].proposed_value == "XANES", "the proposal really was skipped"
    assert final.proposal_change_revs[pid] >= restored_position, (
        "a stale writer moved a proposal BACKWARDS in the feed's order"
    )


def test_concurrent_writers_never_move_an_entity_backwards(client):
    """SIMULATED CONCURRENT WRITERS: many threads, one record, one invariant.

    WHAT IS ASSERTED IS A MONOTONICITY PROPERTY, NOT A COUNT. How many of N concurrent
    writes land is a function of the compare-and-swap and of scheduling, and asserting
    a number would be asserting timing — which ``CLAUDE.md`` §7 records this repository
    being bitten by. What must hold regardless of interleaving is that no entity's
    position is ever LOWER than one previously observed, and that the record's own
    entry is never below any entity of the record.

    The positions are SAMPLED THROUGHOUT, not only at the end: a final-state check
    would pass on a run that dipped and recovered, and a dip is exactly the window in
    which a polling client loses a change.
    """
    exp_id = _record(client, runs=6, title="concurrent")
    run_ids = [r.id for r in ws.load_experiment(exp_id).runs]

    high_water: dict[str, int] = {}
    violations: list[str] = []
    lock = threading.Lock()

    def _sample() -> None:
        # THE READ IS INSIDE THE LOCK, AND THAT IS A CORRECTNESS FIX TO THE TEST
        # RATHER THAN TIDINESS. With the read outside it, two samplers could observe
        # revisions 5 and 7 and then RECORD them in the opposite order, and the
        # high-water check would report a regression the store never performed — a
        # flaky FALSE POSITIVE on a test whose whole job is to be believed when it
        # says a position went backwards. Reading under the same lock that records
        # makes the observation sequence a total order, so a sample recorded later
        # was also read later, and writes being monotone then makes the check sound.
        with lock:
            exp = ws.load_experiment(exp_id)
            positions = {r.id: r.changed_at_rev for r in exp.runs}
            positions[exp.id] = exp.rev
            for entity, position in positions.items():
                if position < high_water.get(entity, 0):
                    violations.append(
                        f"{entity}: {high_water[entity]} -> {position}"
                    )
                high_water[entity] = max(high_water.get(entity, 0), position)
            if positions[exp.id] < max(positions.values()):
                violations.append("an entity sat above the record's own rev")

    def _writer(rid: str, n: int) -> None:
        for i in range(n):
            try:
                with ws.record_lock(exp_id):
                    _touch_run(exp_id, rid, f"BL-{rid[-4:]}-{i}")
            except Exception as exc:  # pragma: no cover - reported, never swallowed
                with lock:
                    violations.append(f"write raised: {exc!r}")
            _sample()

    threads = [threading.Thread(target=_writer, args=(rid, 4)) for rid in run_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not violations, violations
    # NOT VACUOUS: the writes really happened, so the sampler had something to see.
    final = ws.load_experiment(exp_id)
    assert final.rev >= len(run_ids) * 4
    assert all(r.changed_at_rev > 0 for r in final.runs)


def test_concurrent_writers_lose_no_change_from_a_cursor(client):
    """The same interleaving, judged from a CLIENT's cursor rather than from the store.

    A poller holds a cursor while writers run, then resumes ONCE. Every entity whose
    position advanced past that cursor must appear in the walk, exactly once. This is
    the property ``SEQUENCE_PROOF`` claims and the one the timestamp key did not have:
    under the old key two writes inside one second could leave a changed entity behind
    a cursor and it would never be reported at all.
    """
    exp_id = _record(client, runs=5, title="concurrent cursor")
    run_ids = [r.id for r in ws.load_experiment(exp_id).runs]

    page = client.get(f"/api/experiments/{exp_id}/changes").json()
    cursor = page["next_cursor"]
    baseline = {c["entity_id"]: c["changed_at_rev"] for c in page["changes"]}

    errors: list[str] = []

    def _writer(rid: str) -> None:
        for i in range(3):
            try:
                with ws.record_lock(exp_id):
                    _touch_run(exp_id, rid, f"BL-{i}")
            except Exception as exc:  # pragma: no cover
                errors.append(repr(exc))

    threads = [threading.Thread(target=_writer, args=(rid,)) for rid in run_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors

    resumed = _walk(client, exp_id, limit=2)
    reported = [c["entity_id"] for c in resumed]
    assert len(reported) == len(set(reported)), "an entity was reported twice"

    # Everything that moved past the cursor is in the resumed walk. Computed from the
    # STORE's current positions rather than from what the feed said, so the feed is
    # being checked against the storage and not against itself.
    final = ws.load_experiment(exp_id)
    moved = {r.id for r in final.runs if r.changed_at_rev > baseline[r.id]}
    moved.add(exp_id)  # every write moves the record's own entry
    assert moved <= set(reported), sorted(moved - set(reported))


# =============================================================================
# 4. PAGING OVER THE SEQUENCE
# =============================================================================


def test_paging_one_entry_at_a_time_over_interleaved_kinds_loses_nothing(client):
    """PROPOSAL, RUN AND RECORD EVENTS INTERLEAVED, walked one entry per page.

    ``limit=1`` is the harshest paging there is: every entry is its own page boundary,
    so any ordering instability shows up immediately as a duplicate or a loss. The
    three kinds are written in an interleaved sequence so no kind occupies a
    contiguous block of positions — a feed that happened to be correct only when one
    kind's entities were adjacent would pass a gentler arrangement.
    """
    from isaac_api import proposals as proposals_module

    exp_id = _record(client, runs=3, title="interleaved")
    run_ids = [r.id for r in ws.load_experiment(exp_id).runs]

    # run, proposal, run, proposal-transition, run, record — six writes, three kinds.
    _touch_run(exp_id, run_ids[0], "BL-1")

    exp = ws.load_experiment(exp_id)
    _make_proposal(exp, pid="01SYNTHETICPROPOSALAAAAAA")
    assert exp.save_versioned() is True

    _touch_run(exp_id, run_ids[1], "BL-2")

    exp = ws.load_experiment(exp_id)
    exp.proposals[0] = proposals_module.reject_proposal(
        exp.proposals[0], at="2026-01-02T00:00:00Z", reason="synthetic"
    )
    _make_proposal(exp, pid="01SYNTHETICPROPOSALBBBBBB", value="EXAFS")
    assert exp.save_versioned() is True

    _touch_run(exp_id, run_ids[2], "BL-3")

    exp = ws.load_experiment(exp_id)
    exp.title = "interleaved, renamed"
    assert exp.save_versioned() is True

    walked = _walk(client, exp_id, limit=1)
    ids = [c["entity_id"] for c in walked]
    assert len(ids) == len(set(ids)), "an entity was returned twice"

    everything = client.get(f"/api/experiments/{exp_id}/changes").json()
    assert set(ids) == {c["entity_id"] for c in everything["changes"]}
    assert len(ids) == 6  # the record, three runs, two proposals
    assert {c["kind"] for c in walked} == {"experiment", "run", "proposal"}

    # The walk is in the SAME order the unpaged read gives — paging is a window on one
    # order, not an order of its own.
    assert [c["entity_id"] for c in everything["changes"]] == ids
    # ...and that order is the published one.
    keys = [(c["changed_at_rev"], c["kind"], c["entity_id"]) for c in walked]
    assert keys == sorted(keys)


def test_entities_sharing_one_position_are_a_total_order_with_no_loss(client):
    """EQUAL POSITIONS ACROSS DIFFERENT ENTITIES — the tie-break's own case.

    One ``save_versioned`` stamps every entity it changed with the SAME position, so a
    record built in one write has every entity at one number and ``(kind, entity_id)``
    is doing ALL of the ordering. That is not a corner case; it is the ordinary state
    of a freshly created record, and it is the condition under which a merely-stable
    sort would let a page boundary reorder between two requests.

    The precondition is MEASURED rather than assumed: if the positions were ever
    distinct, this test would be passing on a sequence that happened to be unique
    rather than on the tie-break.
    """
    exp_id = _record(client, title="one write")
    exp = ws.load_experiment(exp_id)
    # ONE ``save_versioned`` for all eleven entities, which is what makes their
    # positions equal. Two saves would give the runs one position and the proposals
    # another, and the tie-break would then be ordering within groups rather than
    # across the whole record.
    for i in range(9):
        exp.add_run(label=f"Run {i + 1}", draft=routes._seed_for_new_run(exp))
    _make_proposal(exp, pid="01SYNTHETICPROPOSALAAAAAA")
    _make_proposal(exp, pid="01SYNTHETICPROPOSALBBBBBB", value="EXAFS")
    assert exp.save_versioned() is True

    everything = client.get(f"/api/experiments/{exp_id}/changes").json()["changes"]
    assert len(everything) == 12  # the record, nine runs, two proposals
    assert len({c["changed_at_rev"] for c in everything}) == 1, "precondition"

    for limit in (1, 2, 5, 7, 11, 12, 13):
        walked = _walk(client, exp_id, limit=limit)
        ids = [c["entity_id"] for c in walked]
        assert len(ids) == len(set(ids)), (limit, "duplicate")
        assert ids == [c["entity_id"] for c in everything], (limit, "order or loss")


def test_a_page_boundary_exactly_at_the_max_page_size(client):
    """THE OFF-BY-ONE, at the SERVER's ceiling rather than at a number a test chose.

    Three records, at ``CHANGE_FEED_LIMIT_MAX`` entities minus one, exactly, and plus
    one. ``has_more`` and ``remaining`` are asserted on each, because the two are
    published separately and a client that trusts one over the other must not be able
    to tell them apart. The exact-fit case is the one an off-by-one gets wrong in the
    quiet direction: ``has_more: true`` on a full page whose successor is empty costs a
    client one wasted request, while ``has_more: false`` on a page that left one entity
    behind loses it silently.

    The limit is asked for as a number ABOVE the ceiling in each case, so the CLAMP is
    what produces the page size — which is the path a real client hits and the one a
    hard-coded 200 would not exercise.
    """
    cap = cf.CHANGE_FEED_LIMIT_MAX

    for entities, expect_more, expect_remaining in (
        (cap - 1, False, 0),
        (cap, False, 0),
        (cap + 1, True, 1),
    ):
        exp_id = _record(client, runs=entities - 1, title=f"boundary {entities}")
        page = client.get(
            f"/api/experiments/{exp_id}/changes", params={"limit": cap + 500}
        ).json()
        assert page["limit"] == cap, "the clamp is reported"
        assert page["returned"] == min(entities, cap), entities
        assert page["has_more"] is expect_more, entities
        assert page["remaining"] == expect_remaining, entities

        # And the walk from the start still yields exactly the record's entities, once
        # each — the boundary is a window edge, not a place entries fall through.
        walked = _walk(client, exp_id, limit=cap + 500)
        ids = [c["entity_id"] for c in walked]
        assert len(ids) == entities == len(set(ids)), entities


def test_a_cursor_resumes_after_the_state_is_ROUND_TRIPPED_between_pages(client):
    """RESTART BETWEEN PAGES: read half, put the document through the store, resume.

    A cursor names stored coordinates and nothing process-local, so a page and its
    successor may be served by different application objects over a document that has
    been re-read from disk in between. The round trip here is a real one —
    ``to_state`` -> ``from_state`` -> ``save`` -> reload — because a test that only
    reloaded would not prove the coordinates SURVIVE serialisation, which is the half
    a missing ``to_state`` key would break.

    A SECOND APPLICATION serves the resumed page, so nothing in-process carries over.
    """
    exp_id = _record(client, runs=7, title="round trip paging")
    exp = ws.load_experiment(exp_id)
    _make_proposal(exp, pid="01SYNTHETICPROPOSALAAAAAA")
    assert exp.save_versioned() is True
    _touch_run(exp_id, exp.runs[0].id, "BL-SYNTH")

    page = client.get(f"/api/experiments/{exp_id}/changes", params={"limit": 4}).json()
    assert page["has_more"] is True
    cursor = page["next_cursor"]
    seen = {c["entity_id"] for c in page["changes"]}

    # THE ROUND TRIP: serialise, rehydrate, write back, re-read.
    original = ws.load_experiment(exp_id)
    rehydrated = ws.Experiment.from_state(json.loads(json.dumps(original.to_state())))
    rehydrated.save()
    assert ws.load_experiment(exp_id).to_state() == original.to_state()

    from isaac_api.app import create_app

    second = TestClient(create_app())
    resumed = second.get(
        f"/api/experiments/{exp_id}/changes", params={"cursor": cursor}
    ).json()
    assert resumed["has_more"] is False
    resumed_ids = [c["entity_id"] for c in resumed["changes"]]
    assert len(resumed_ids) == len(set(resumed_ids))
    assert not (seen & set(resumed_ids)), "an entity was handed out twice"
    assert seen | set(resumed_ids) == {
        c["entity_id"]
        for c in second.get(f"/api/experiments/{exp_id}/changes").json()["changes"]
    }


def test_a_cursor_held_across_a_round_trip_still_reports_a_LATER_change(client):
    """The round trip must not swallow a change made after the cursor was issued.

    The test above proves nothing is duplicated or lost across a rehydrate. This one
    proves the coordinates still MOVE afterwards: a save through a rehydrated object
    stamps positions that the held cursor is still strictly below, so the change is
    reported. A ``to_state``/``from_state`` pair that silently reset a coordinate would
    pass the first test — everything would simply be at 0 — and fail this one.
    """
    exp_id = _record(client, runs=4, title="round trip then change")
    page = client.get(f"/api/experiments/{exp_id}/changes").json()
    cursor = page["next_cursor"]
    target = next(c["entity_id"] for c in page["changes"] if c["kind"] == "run")

    original = ws.load_experiment(exp_id)
    ws.Experiment.from_state(json.loads(json.dumps(original.to_state()))).save()

    _touch_run(exp_id, target, "BL-AFTER")

    resumed = client.get(
        f"/api/experiments/{exp_id}/changes", params={"cursor": cursor}
    ).json()
    reported = [c["entity_id"] for c in resumed["changes"]]
    assert target in reported, reported
    assert exp_id in reported
    assert len(reported) == len(set(reported))

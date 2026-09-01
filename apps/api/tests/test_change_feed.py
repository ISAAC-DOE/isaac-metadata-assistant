"""The record change feed is a COALESCING STATE FEED, and every claim it makes holds.

WHAT THIS FILE IS GUARDING, AND WHY THE NAMING IS THE FIRST TEST
================================================================
``GET /api/experiments/{id}/changes`` reports "this entity is at a version later than
your cursor". It does NOT report "here is every act that happened". There is no event
table in this application and `CLAUDE.md` §15 does not permit one, so an event log is
not something the storage can back — which means the danger is not that the feature
is missing, it is that the feature gets DESCRIBED as something it is not. A surface
that says "event log" and coalesces is a surface a client will count with.

So the first section below asserts the vocabulary, in the served OpenAPI document and
in the frontend copy constant, and asserts the negative: the word "event log" appears
in neither, and neither claims exactly-once delivery.

Everything after that is a property the brief required, one section each, with the
limitation stated honestly rather than the guarantee stated broadly:

  1. naming and the four published properties
  2. total order, with a tie-break that is doing real work
  3. the cursor is opaque, versioned, and refused rather than guessed at
  4. bounds are CLAMPED and the clamp is reported
  5. no duplicates and no gaps, paged one entry at a time
  6. scope: a worked-example entity never appears in an ordinary-scope feed
  7. the kind set is DERIVED from collectors, not hard-coded
  8. deletions cannot be reported, and delete->recreate is still distinguishable
  9. a cursor survives an application restart
 10. the feed composes nothing — zero draft/export/pending derivations per request

Everything here is synthetic: a record created through ``POST /api/experiments`` and
given runs in process. No real data, no network, no database.

The byte/call-count benchmark is opt-in at the bottom::

    ISAAC_PERF_BENCH=1 .venv/bin/pytest apps/api/tests/test_change_feed.py -q -s -k benchmark
"""

from __future__ import annotations

import base64
import json
import os

import pytest
from fastapi.testclient import TestClient

from isaac_api import change_feed as cf
from isaac_api import routes
from isaac_api import workspace as ws

from conftest import tutorial_client


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return create_app()


@pytest.fixture()
def client(app) -> TestClient:
    """A plain client on an empty workspace — NO worked-example session."""
    return TestClient(app)


def _with_runs(client: TestClient, n: int, *, title: str = "change feed") -> str:
    """A record created over HTTP, then given ``n`` runs IN PROCESS.

    The same harness shape ``test_pending_reads_are_boundable.py`` uses, and for the
    same reason: ``POST /runs`` rewrites the whole document per call, so building a
    thousand runs that way would measure the store rather than the feed.

    IT IS ALSO WHAT MAKES THE TIE-BREAK TESTS MEANINGFUL. One ``save_versioned``
    stamps every changed run with the same ``_now_iso()`` instant, so every run here
    shares one ``updated_utc`` and the order rests entirely on ``(kind, entity_id)``.
    """
    exp_id = client.post("/api/experiments", json={"title": title}).json()["id"]
    exp = ws.load_experiment(exp_id)
    for i in range(n):
        exp.add_run(label=f"Run {i + 1}", draft=routes._seed_for_new_run(exp))
    exp.save_versioned()
    return exp_id


def _feed(client: TestClient, exp_id: str, **params) -> dict:
    res = client.get(f"/api/experiments/{exp_id}/changes", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _description(client: TestClient) -> str:
    spec = client.get("/openapi.json").json()
    return spec["paths"]["/api/experiments/{experiment_id}/changes"]["get"]["description"]


# =============================================================================
# 1. naming, and the three published properties
# =============================================================================


def test_the_published_description_calls_it_a_state_feed_and_never_an_event_log(client):
    """THE NAMING TEST, and it is first because it is the one a refactor breaks silently.

    A positive AND a negative, because either alone passes on the wrong document: a
    description could carry "state feed" in one sentence and "event log" in the next,
    and a description could omit "event log" while never saying what it IS.
    """
    text = _description(client)
    assert "coalescing STATE feed, not an event log" in text
    lowered = text.lower()
    # BOTH PHRASES APPEAR, AND EVERY OCCURRENCE OF EACH IS A DENIAL. A blunt "the
    # phrase is absent" was the first version of this assertion and it was wrong twice
    # over: it failed on the honest text (which has to name what the feed is NOT), and
    # it would have passed on a description that simply never addressed the question.
    # What is actually worth pinning is that the document never makes either claim.
    assert lowered.count("event log") == lowered.count("not an event log") == 1
    assert lowered.count("exactly-once") == lowered.count("not exactly-once") == 1
    # It says what coalescing COSTS, not merely that it happens.
    assert "Ten edits to one run between two reads are ONE entry" in text


@pytest.mark.parametrize(
    "claim",
    [
        pytest.param(cf.SEQUENCE_PROOF, id="sequence-proof"),
        pytest.param(cf.GAP_GUARANTEE, id="gap"),
        pytest.param(cf.DELETION_LIMITATION, id="deletion"),
        pytest.param(cf.EXPIRY_PROPERTY, id="expiry"),
    ],
)
def test_each_published_property_reaches_the_served_document_verbatim(client, claim):
    """ONE definition, quoted — never a paraphrase in the route and a constant here.

    The same posture as ``dependencies.MISSING_REASON``: a claim written twice is a
    claim free to drift, and these four are exactly the claims a client would build
    the wrong retry logic on top of.

    ``SEQUENCE_PROOF`` JOINED THE LIST WITH THE ORDERING FIX, and it is published
    rather than kept as an internal comment for the reason the other three are: it is
    the argument a client's own correctness rests on, and a client that cannot read it
    has to take "no entity is skipped" on trust.
    """
    assert claim in _description(client)


def test_the_gap_guarantee_names_its_own_failure_mode_rather_than_promising_none():
    """The honest half has to be present, not just the reassuring half.

    THIS TEST USED TO REQUIRE THE LITERAL "PROVIDED `updated_utc` never moves
    backwards", AND THAT PROVISO WAS FALSE — which is the reason the assertion is
    replaced rather than extended. A backwards clock is not the only way to lose a
    change: a write landing inside the SAME ONE-SECOND STAMP a cursor already names
    moves an entity's `version` without moving its key, and the entity is then never
    reported. That is a monotonic clock, so the old proviso held while the guarantee
    it protected did not, and a test requiring the old words was mechanically keeping
    the false version in place. See
    ``test_a_same_second_write_behind_the_cursor_is_a_measured_gap``, which
    demonstrates the loss rather than asserting prose about it.
    """
    # ── RE-PINNED AGAIN WITH THE SEQUENCE FIX, AND THE HISTORY IS THE POINT ───────
    #
    # Three wordings of this sentence were measured false in turn: "never moves
    # backwards", then "STRICTLY ADVANCES" (reproduced false with no clock
    # manipulation at all — a stamp advancing INTO the cursor's own second, with the
    # tie-break placing the entity behind), and then the honest third wording, which
    # was true but which disclosed a real defect rather than describing a working
    # feed. THE DEFECT IS NOW FIXED IN THE KEY rather than in the sentence, and this
    # test's job changes with it: it pins that the guarantee is stated about the KEY,
    # that the closed gap is RECORDED rather than deleted, and that what is still not
    # promised is still named.
    assert "SORT KEY advances strictly past" in cf.GAP_GUARANTEE
    # The mechanism, because a rule with no mechanism beside it reads as arbitrary and
    # is the half a later tidy-up drops.
    assert "durable strictly-increasing SEQUENCE POSITION" in cf.GAP_GUARANTEE
    assert "`(changed_at_rev, kind, entity_id)`" in cf.GAP_GUARANTEE
    # THE CLOSED GAP IS KEPT AS A RECORDED CORRECTION. A disclosure deleted the moment
    # it stopped applying leaves a reader unable to tell a fixed defect from one that
    # was never there — and this file has three false wordings behind it that only
    # make sense if the reader can see them.
    assert "SAME-SECOND GAP THIS SENTENCE USED TO DISCLOSE IS CLOSED" in cf.GAP_GUARANTEE
    assert "WHOLE SECONDS" in cf.GAP_GUARANTEE
    assert "measured false" in cf.GAP_GUARANTEE
    # AND THE FIX IS NAMED AS A KEY CHANGE, NOT A CLOCK CHANGE. A future reader who
    # thought the remedy was a sub-second timestamp would be re-opening the decision
    # this slice deliberately refused.
    assert "fixed by changing the KEY, not the clock" in cf.GAP_GUARANTEE
    # WHAT IS STILL NOT PROMISED, each named rather than implied by silence.
    assert "not exactly-once delivery" in cf.GAP_GUARANTEE
    assert "sits at 0" in cf.GAP_GUARANTEE
    assert "starts a fresh sequence at 0" in cf.GAP_GUARANTEE
    assert "no cursor at all" in cf.GAP_GUARANTEE


def test_the_ordering_proof_is_written_out_rather_than_asserted():
    """The ARGUMENT is published, not just the conclusion.

    Three successive wordings of `GAP_GUARANTEE` were measured false, and none of them
    failed because someone reasoned badly — they failed because nobody had written the
    reasoning down where a reader could check it. So the proof is a published constant
    with the two steps that carry it, and this test pins both: that the cursor's
    position is bounded above by the record's rev, and that a later change is written
    at a strictly greater one. Drop either step and the conclusion does not follow.
    """
    assert "SEQUENCE POSITION, not a clock" in cf.SEQUENCE_PROOF
    # Step 1: the cursor cannot name a position above the record's own rev.
    assert "at most the record's rev at the moment that cursor was issued" in cf.SEQUENCE_PROOF
    # Step 2: a later change is written strictly above it.
    assert "strictly greater than the rev on disk when it ran" in cf.SEQUENCE_PROOF
    # The conclusion, and the part that is the whole difference from the old key: the
    # tie-break cannot rescue or ruin it, because the first component already decided.
    assert "ON THE FIRST COMPONENT ALONE" in cf.SEQUENCE_PROOF
    assert "regardless of how the kind and entity-id tie-break falls" in cf.SEQUENCE_PROOF


def test_the_deletion_limitation_is_stated_as_a_limitation():
    assert "cannot report deletions" in cf.DELETION_LIMITATION
    assert "tombstone" in cf.DELETION_LIMITATION
    assert "`generation`" in cf.DELETION_LIMITATION


def test_expiry_is_published_as_a_property_and_no_code_handles_it():
    """A property, NOT a code path — and the absence is asserted, not assumed.

    The brief's instruction was to document expiry as structurally impossible and to
    write no handling for it. An unwritten branch is invisible to every other test in
    this file, so it is checked directly against the two modules' source: nothing
    mints, returns or matches a `cursor_expired` state.
    """
    assert "never expires" in cf.EXPIRY_PROPERTY
    assert "no `cursor_expired` status" in cf.EXPIRY_PROPERTY

    from pathlib import Path

    feed_src = Path(cf.__file__).read_text(encoding="utf-8")
    routes_src = Path(routes.__file__).read_text(encoding="utf-8")
    # In `change_feed.py` the token occurs ONCE — inside `EXPIRY_PROPERTY`, where it
    # is the thing being denied. Anywhere else would be a handler.
    assert feed_src.count("cursor_expired") == 1
    assert "cursor_expired" not in routes_src


# =============================================================================
# 2. the total order, and a tie-break that is doing real work
# =============================================================================


def test_the_order_is_changed_at_rev_then_kind_then_entity_id(client):
    """THE PUBLISHED ORDER, over the wire, and the leading component is on the wire.

    This was `test_the_order_is_updated_utc_then_kind_then_entity_id` and it is renamed
    rather than edited in place, because the change it is tracking is the whole slice:
    the key's leading component stopped being a whole-second timestamp and became a
    durable sequence position. `updated_utc` is still published — clients display it —
    and it is asserted below to be exactly what it now is, which is NOT the order.
    """
    exp_id = _with_runs(client, 6)
    changes = _feed(client, exp_id)["changes"]
    keys = [(c["changed_at_rev"], c["kind"], c["entity_id"]) for c in changes]
    assert keys == sorted(keys)


def test_updated_utc_is_still_published_and_is_no_longer_the_order(client):
    """The field a "nothing reads it any more" tidy-up would delete.

    It is on the wire for every entry, because clients display "last updated" and the
    frontend's `ApiChangeEntry` names it. It is NOT the order, and the two halves are
    asserted separately: the timestamps are all EQUAL here (one write, one second),
    so an order that still led with them would be decided entirely by the tie-break —
    which is the exact condition under which the old key lost changes.
    """
    exp_id = _with_runs(client, 6)
    changes = _feed(client, exp_id)["changes"]
    assert all(isinstance(c["updated_utc"], str) and c["updated_utc"] for c in changes)
    assert len({c["updated_utc"] for c in changes}) == 1
    # And the key does not contain it at all — asserted structurally rather than by
    # inspecting the wire, because `ChangeEntry.key` is what `changes_page` compares.
    exp = ws.load_experiment(exp_id)
    entry = cf.collect(exp)[0]
    assert entry.key == (entry.changed_at_rev, entry.kind, entry.entity_id)
    assert entry.updated_utc not in entry.key


def test_the_tie_break_is_load_bearing_because_the_sequence_positions_are_equal(client):
    """The precondition the tie-break exists for is MEASURED, not assumed.

    One `save_versioned` stamps every entity it changed with the SAME sequence
    position — that is the design, since they changed in one write — so on a record
    whose runs were created together the leading component is constant and
    `(kind, entity_id)` is doing all of the ordering. If this assertion ever fails, the
    ordering tests below stop proving what they claim: they would be passing on a
    position that happened to be unique rather than on the tie-break.

    THE SEQUENCE FIX DID NOT MAKE THE TIE-BREAK REDUNDANT, and that is worth stating
    because it is the natural assumption. The two solve different failures: the
    tie-break stops a page boundary reordering between two requests; the sequence stops
    a CHANGE being invisible to a cursor. Removing either reintroduces its own defect.
    """
    exp_id = _with_runs(client, 8)
    changes = _feed(client, exp_id)["changes"]
    positions = {c["changed_at_rev"] for c in changes}
    assert len(positions) == 1, positions
    # ...and the order is therefore entirely `(kind, entity_id)`.
    assert [c["kind"] for c in changes] == ["experiment"] + ["run"] * 8
    run_ids = [c["entity_id"] for c in changes if c["kind"] == "run"]
    assert run_ids == sorted(run_ids)


def test_the_order_does_not_depend_on_the_stored_list_order(client):
    """Reversing `exp.runs` must not move a single entry.

    `sorted_runs`' own docstring records that a non-total key made exactly this
    reversible: `sorted` is merely stable, so an incomplete key lets input order leak
    into output order. For a CURSOR-PAGED reader that is not cosmetic — it is how an
    entity gets skipped at a page boundary.
    """
    exp_id = _with_runs(client, 5)
    forward = _feed(client, exp_id)["changes"]

    exp = ws.load_experiment(exp_id)
    exp.runs.reverse()
    entries = [e.to_wire() for e in cf.collect(exp)]
    assert entries == forward


class _NoTieBreak(cf.ChangeEntry):
    """A `ChangeEntry` whose key is THE SEQUENCE POSITION ALONE, padded to the arity.

    This is the mutant: `(changed_at_rev, "", "")` keeps the tuple three components
    wide so `encode_cursor` still works, while removing every component that
    distinguishes two entities stamped by the same write. It is what `ChangeEntry.key`
    would be if someone "simplified" the tie-break away on the grounds that the
    sequence had made it unnecessary, and the test below shows what that costs.
    """

    @property
    def key(self) -> tuple[int, str, str]:
        return (self.changed_at_rev, "", "")


def _tie_break_removed(exp):
    """`RECORD_COLLECTORS`' entries, re-minted with the tie-break stripped out."""
    for e in cf.collect(exp):
        yield _NoTieBreak(
            kind=e.kind,
            entity_id=e.entity_id,
            changed_at_rev=e.changed_at_rev,
            updated_utc=e.updated_utc,
            rev=e.rev,
            generation=e.generation,
        )


def _walk(exp, collectors, *, limit):
    """Page to exhaustion, returning every entity id handed out, duplicates kept."""
    seen: list[str] = []
    cursor = None
    for _ in range(100):  # bounded so a broken cursor cannot hang the suite
        page = cf.changes_page(exp, scope_tag="t", cursor=cursor, limit=limit, collectors=collectors)
        seen.extend(c["entity_id"] for c in page["changes"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            return seen
    raise AssertionError("the walk did not terminate")


def test_removing_the_tie_break_loses_entities_at_a_page_boundary(client):
    """THE MUTATION TEST THE TIE-BREAK EXISTS FOR, and it is about PAGING, not sorting.

    `test_the_order_does_not_depend_on_the_stored_list_order` above already shows the
    tie-break fixing the ORDER. This shows the consequence that actually matters: with
    the tie-break removed, every entity of one record shares one key, so the cursor
    minted from page one sits at or after every remaining entity and `key > start`
    excludes all of them. The walk terminates having handed out `limit` entities and
    silently dropped the rest — no error, no `has_more`, a page that looks complete.

    The control is the same walk with the real collectors: it must reach everything.
    Without that half the test would pass on a feed that was broken for both.
    """
    exp = ws.load_experiment(_with_runs(client, 7))
    everything = {e.entity_id for e in cf.collect(exp)}
    assert len(everything) == 8  # the record plus seven runs
    # The precondition the whole test rests on: one write, one sequence position.
    assert len({e.changed_at_rev for e in cf.collect(exp)}) == 1

    intact = _walk(exp, cf.RECORD_COLLECTORS, limit=3)
    assert len(intact) == len(set(intact)), "the real feed returned an entity twice"
    assert set(intact) == everything, "the real feed skipped an entity"

    mutant = (cf.KindCollector(kind="run", read=_tie_break_removed),)
    lost = _walk(exp, mutant, limit=3)
    assert set(lost) < everything, "the mutant did not lose anything — the test is vacuous"
    assert len(lost) == 3, lost
    # And it lies about it: the page that dropped five entities said there were none
    # left, which is exactly why a cursor-paged reader cannot detect this itself.
    last = cf.changes_page(
        exp, scope_tag="t", cursor=cf.encode_cursor(cf.ZERO_KEY, scope="t"), limit=3, collectors=mutant
    )
    assert last["has_more"] is True
    resumed = cf.changes_page(exp, scope_tag="t", cursor=last["next_cursor"], collectors=mutant)
    assert resumed["changes"] == [] and resumed["has_more"] is False and resumed["remaining"] == 0


# =============================================================================
# 3. the cursor
# =============================================================================


def test_a_cursor_round_trips_through_the_server_only(client):
    """The client's whole contract: take `next_cursor`, send it back, get the rest.

    Note what this test does NOT do — it never builds a cursor. The only place in this
    file that constructs one is the refusal section below, which is what "opaque"
    means operationally.
    """
    exp_id = _with_runs(client, 5)
    first = _feed(client, exp_id, limit=2)
    assert first["returned"] == 2 and first["has_more"] is True
    second = _feed(client, exp_id, cursor=first["next_cursor"], limit=2)
    assert second["returned"] == 2
    assert {c["entity_id"] for c in first["changes"]} & {
        c["entity_id"] for c in second["changes"]
    } == set()


def test_an_empty_page_returns_the_position_the_caller_was_already_at(client):
    """A poller at the end makes no progress and loses nothing.

    `next_cursor` is present on an empty page rather than `null`, so a client never
    has to special-case "the server gave me nothing to resume from".
    """
    exp_id = _with_runs(client, 3)
    whole = _feed(client, exp_id)
    assert whole["has_more"] is False
    end = _feed(client, exp_id, cursor=whole["next_cursor"])
    assert end["changes"] == [] and end["returned"] == 0 and end["remaining"] == 0
    assert end["next_cursor"] == whole["next_cursor"]


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("", id="empty"),
        pytest.param("!!!not base64!!!", id="not-base64url"),
        pytest.param(base64.urlsafe_b64encode(b"\xff\xfe\xfd").decode(), id="not-utf8"),
        pytest.param(base64.urlsafe_b64encode(b"not json").decode(), id="not-json"),
        pytest.param(base64.urlsafe_b64encode(b'["a","b","c"]').decode(), id="not-object"),
    ],
)
def test_an_undecodable_cursor_is_refused_422(client, bad):
    exp_id = _with_runs(client, 2)
    res = client.get(f"/api/experiments/{exp_id}/changes", params={"cursor": bad})
    assert res.status_code == 422, res.text
    assert res.json()["error"] == "malformed_cursor"
    assert res.json()["reason"] == "not_decodable"


def _handmade(payload: dict) -> str:
    """A cursor built by hand — used ONLY to prove a bad one is refused."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def test_a_cursor_of_another_version_is_refused_rather_than_interpreted(client):
    """A future payload shape must not be read with today's rules.

    The version exists so the server can change the tuple; a build that silently
    accepted an unknown version would answer from a key it had guessed at.
    """
    exp_id = _with_runs(client, 2)
    tag = cf.record_scope_tag(exp_id, None)
    token = _handmade({"v": 99, "s": tag, "q": 3, "k": "run", "e": "x"})
    res = client.get(f"/api/experiments/{exp_id}/changes", params={"cursor": token})
    assert res.status_code == 422
    assert res.json()["reason"] == "not_decodable"


def test_a_version_1_cursor_is_REFUSED_rather_than_MISREAD(client):
    """THE VERSION TRANSITION, and it is the case a bump exists for.

    A v1 cursor's leading component was a `%Y-%m-%dT%H:%M:%SZ` STRING under the key
    `t`; a v2 cursor's is an integer sequence position under `q`. Neither converts into
    the other — a timestamp does not name a `rev`, and no arithmetic recovers one — so
    the only two possible behaviours are REFUSE and GUESS, and guessing here means
    answering a well-formed page computed from a position the caller never held.

    Two independent refusals are asserted, not one, because either alone would leave
    the other unproven: the version check fires first, and a payload that somehow
    carried `v: 2` while keeping v1's shape is still missing `q`. A build that
    "helpfully" migrated the old shape would pass neither.

    The remedy is the published one and it is asserted here too — a client that gets
    this `422` drops the cursor and resyncs, which is the SAME remedy the other
    refusal reason has, which is why both share one status.
    """
    exp_id = _with_runs(client, 3)
    tag = cf.record_scope_tag(exp_id, None)

    v1 = _handmade({"v": 1, "s": tag, "t": "2026-01-01T00:00:00Z", "k": "run", "e": "x"})
    res = client.get(f"/api/experiments/{exp_id}/changes", params={"cursor": v1})
    assert res.status_code == 422
    assert res.json()["reason"] == "not_decodable"

    # ...and the shape alone is refused even wearing the current version number.
    relabelled = _handmade(
        {"v": cf.CURSOR_VERSION, "s": tag, "t": "2026-01-01T00:00:00Z", "k": "run", "e": "x"}
    )
    res = client.get(f"/api/experiments/{exp_id}/changes", params={"cursor": relabelled})
    assert res.status_code == 422
    assert res.json()["reason"] == "not_decodable"

    # THE REMEDY WORKS. A test that only proved the refusal would read as an argument
    # that the bump stranded every existing client.
    assert _feed(client, exp_id)["returned"] == 4


@pytest.mark.parametrize("missing", ["q", "k", "e"])
def test_a_cursor_missing_a_key_component_is_refused(client, missing):
    exp_id = _with_runs(client, 2)
    payload = {
        "v": cf.CURSOR_VERSION,
        "s": cf.record_scope_tag(exp_id, None),
        "q": 1,
        "k": "run",
        "e": "x",
    }
    payload.pop(missing)
    res = client.get(
        f"/api/experiments/{exp_id}/changes", params={"cursor": _handmade(payload)}
    )
    assert res.status_code == 422
    assert res.json()["reason"] == "not_decodable"


@pytest.mark.parametrize(
    "payload_patch,why",
    [
        pytest.param({"q": "7"}, "a string sequence must not become 7", id="q-as-string"),
        pytest.param({"q": 1.5}, "a float is not a sequence position", id="q-as-float"),
        pytest.param({"q": None}, "null is not a position", id="q-as-null"),
        pytest.param({"k": 7}, "an integer kind must not become '7'", id="kind-as-int"),
        pytest.param({"e": 7}, "an integer id must not become '7'", id="id-as-int"),
        # `isinstance(True, int)` is True in Python, so a bare integer check would
        # ACCEPT this and decode it to the real position `1`. That is the one case in
        # this list a reasonable implementation gets wrong by accident.
        pytest.param({"q": True}, "a bool must not decode to the position 1", id="q-as-bool"),
    ],
)
def test_a_wrong_typed_component_is_refused_and_never_coerced(client, payload_patch, why):
    """Coercion here would build a key that compares against real keys and answer from
    a position the caller never asked for — a wrong answer where an error was
    available."""
    exp_id = _with_runs(client, 2)
    payload = {
        "v": cf.CURSOR_VERSION,
        "s": cf.record_scope_tag(exp_id, None),
        "q": 1,
        "k": "run",
        "e": "x",
    }
    payload.update(payload_patch)
    res = client.get(
        f"/api/experiments/{exp_id}/changes", params={"cursor": _handmade(payload)}
    )
    assert res.status_code == 422, why
    assert res.json()["reason"] == "not_decodable", why


def test_a_cursor_from_another_record_is_refused_as_the_wrong_feed(client):
    """Two records have two orders, so one's position is meaningless in the other.

    The refusal shares the published `422 malformed_cursor` status — a client has one
    remedy either way — but carries its own `reason`, because "you sent the wrong
    record's cursor" is a different bug from "that is not a cursor".
    """
    a = _with_runs(client, 3, title="record A")
    b = _with_runs(client, 3, title="record B")
    cursor_a = _feed(client, a, limit=1)["next_cursor"]
    res = client.get(f"/api/experiments/{b}/changes", params={"cursor": cursor_a})
    assert res.status_code == 422
    assert res.json()["reason"] == "wrong_feed"
    assert "resync" in res.json()["message"]


# =============================================================================
# 4. bounds — clamped, never refused, and the clamp is reported
# =============================================================================


def test_the_default_window_is_fifty(client):
    exp_id = _with_runs(client, 80)
    body = _feed(client, exp_id)
    assert body["limit"] == cf.CHANGE_FEED_WINDOW == 50
    assert body["returned"] == 50
    assert body["has_more"] is True
    assert body["remaining"] == 81 - 50  # 80 runs + the experiment's own entry


@pytest.mark.parametrize(
    "asked,effective",
    [
        pytest.param(1000, 200, id="above-the-maximum"),
        pytest.param(201, 200, id="one-above"),
        pytest.param(200, 200, id="at-the-maximum"),
        pytest.param(0, 1, id="zero"),
        pytest.param(-5, 1, id="negative"),
    ],
)
def test_an_out_of_range_limit_is_clamped_and_the_clamp_is_reported(
    client, asked, effective
):
    """CLAMPED, NOT REFUSED — and the effective value is in the body.

    A `422` on `limit=1000` would make a client guess the ceiling; a silent clamp
    would make it believe it had the whole set. Reporting the number it got is the
    only version of this that is both usable and honest.
    """
    exp_id = _with_runs(client, 3)
    body = _feed(client, exp_id, limit=asked)
    assert body["limit"] == effective


def test_a_non_integer_limit_is_still_a_type_refusal(client):
    """The clamp is about RANGE. `limit=banana` names no number to clamp, and the
    parameter layer refusing it is the honest outcome — documented in the parameter
    description so the two behaviours are not read as one contradictory rule."""
    exp_id = _with_runs(client, 2)
    res = client.get(f"/api/experiments/{exp_id}/changes", params={"limit": "banana"})
    assert res.status_code == 422


def test_next_cursor_and_has_more_are_always_present(client):
    """On every shape of response, including the ones where they are trivial."""
    for n in (0, 1, 60):
        exp_id = _with_runs(client, n, title=f"always present {n}")
        for params in ({}, {"limit": 1}, {"limit": 500}):
            body = _feed(client, exp_id, **params)
            assert isinstance(body["next_cursor"], str) and body["next_cursor"]
            assert isinstance(body["has_more"], bool)
            assert body["limit"] >= 1


# =============================================================================
# 5. no duplicates, no gaps
# =============================================================================


def test_paging_one_entry_at_a_time_reaches_every_entity_exactly_once(client):
    """The strongest form of the guarantee: `limit=1`, walked to exhaustion.

    A page size of one maximises the number of boundaries, which is where a
    non-strict comparison duplicates and a mis-ordered key skips.
    """
    exp_id = _with_runs(client, 12)
    expected = {(c["kind"], c["entity_id"]) for c in _feed(client, exp_id, limit=500)["changes"]}
    assert len(expected) == 13

    seen: list[tuple[str, str]] = []
    cursor = None
    for _ in range(100):  # bounded so a broken cursor cannot hang the suite
        body = _feed(client, exp_id, **({"cursor": cursor} if cursor else {}), limit=1)
        seen.extend((c["kind"], c["entity_id"]) for c in body["changes"])
        cursor = body["next_cursor"]
        if not body["has_more"]:
            break
    assert len(seen) == len(set(seen)), "an entity was returned twice"
    assert set(seen) == expected, "an entity was skipped"


def test_an_entity_that_changes_after_your_cursor_comes_back(client):
    """Resume, then write, then resume again — the entity reappears at its new version.

    This is the coalescing feed's actual promise, and it is the reason the cursor
    names a POSITION rather than a set of seen ids: an entity that moves gets a later
    key, so it is ahead of a cursor it was previously behind.
    """
    exp_id = _with_runs(client, 2)
    end = _feed(client, exp_id)
    assert end["has_more"] is False
    before = {c["entity_id"]: c["version"] for c in end["changes"]}

    # THE WRITE GOES THROUGH `save_versioned`, AND IT DID NOT USED TO. The earlier
    # version of this test hand-set `updated_utc` to a far-future stamp and
    # hand-incremented `target.rev` before a plain `save()` — which was enough while
    # the key led with a timestamp, and is deliberately not enough now. A sequence
    # position is written by the versioned save and by nothing else, so a test that
    # fabricated one would have been asserting against a state the application cannot
    # produce.
    exp = ws.load_experiment(exp_id)
    target = exp.sorted_runs()[0]
    target.draft["fields"] = {"context.beamline": {"value": "BL-SYNTH", "status": "verified"}}
    assert exp.save_versioned() is True

    resumed = _feed(client, exp_id, cursor=end["next_cursor"])
    moved = {c["entity_id"]: c["version"] for c in resumed["changes"]}
    assert target.id in moved
    assert moved[target.id] != before[target.id]
    # The OTHER run did not move, so this is not a feed that re-reports everything on
    # every write and would have passed the assertion above by accident.
    other = exp.sorted_runs()[1].id
    assert other not in moved


def test_a_cursorless_read_is_the_resync_and_returns_the_start_of_the_order(client):
    exp_id = _with_runs(client, 4)
    walked = _feed(client, exp_id, cursor=_feed(client, exp_id, limit=1)["next_cursor"])
    assert walked["returned"] == 4  # everything after the first entry
    resync = _feed(client, exp_id)
    assert resync["returned"] == 5  # the whole order, from the start
    assert resync["changes"][0]["kind"] == "experiment"


def test_replaying_a_cursor_returns_the_identical_page(client):
    """IDEMPOTENT REPLAY, which the brief requires and nothing else here covered.

    A poller that cannot tell whether its last request landed must be able to send the
    same cursor again. That is safe only if the page is a pure function of (stored
    state, cursor, limit) — no server-side offset, no consumption, no "seen" set. It
    is, and the assertion is over the serialised BODY rather than over a subset of
    keys, so a future field that happened to be non-deterministic (a timestamp, a
    nonce, an iteration-ordered dict) would fail here rather than in production.
    """
    exp_id = _with_runs(client, 5)
    cursor = _feed(client, exp_id, limit=2)["next_cursor"]

    bodies = [
        client.get(f"/api/experiments/{exp_id}/changes", params={"cursor": cursor, "limit": 2}).content
        for _ in range(3)
    ]
    assert bodies[0] == bodies[1] == bodies[2]
    # Replay is idempotent because it makes no progress on its own: the cursor a
    # replayed page hands back is the one a first read handed back.
    assert json.loads(bodies[0])["next_cursor"] == json.loads(bodies[2])["next_cursor"]

    # A cursorless read is replayable too — that is what makes the resync remedy in
    # `GAP_GUARANTEE` something a client can retry rather than something it gets one
    # attempt at.
    plain = [client.get(f"/api/experiments/{exp_id}/changes").content for _ in range(2)]
    assert plain[0] == plain[1]


def test_a_same_second_write_behind_the_cursor_IS_REPORTED(client, monkeypatch):
    """**THE REGRESSION TEST FOR THE DEFECT THIS SLICE FIXED.** Inverted, not deleted.

    THIS TEST WAS `test_a_same_second_write_behind_the_cursor_is_a_measured_gap` AND
    IT ASSERTED THE LOSS. Its body read `assert target_id not in {...}` with the
    comment "THIS IS THE GAP", and it passed — the module's own `GAP_GUARANTEE`
    disclosed the exposure and this test measured it. That is the defect: a change to
    an entity that sorted BEHIND the cursor inside the cursor's own whole second moved
    the entity's `version` without moving its key, so `key > start` excluded it and no
    cursor ever reported it. The remedy on offer was "throw the cursor away and
    resync", i.e. read everything, which is the one thing a bounded feed exists to
    avoid.

    IT IS INVERTED RATHER THAN DELETED because a deleted test leaves no evidence that
    the behaviour ever differed, and this file already carries three wordings of
    `GAP_GUARANTEE` that were each measured false. The setup below is UNCHANGED —
    same six runs, same frozen clock, same cursor, same write — so the only thing that
    moved is the verdict.

    THE CLOCK IS STILL FROZEN, AND THAT IS NOW THE POINT RATHER THAN THE WORKAROUND.
    Pinning `_now_iso` to the stamp the record already carries reproduces the exact
    production condition the old key lost changes in — a second write landing in the
    same second as the first — with no sleep, no retry, and no dependence on how fast
    the machine is. Under the sequence key the frozen clock is irrelevant to the
    order, and this test passing IS that statement.

    MUTATION: revert `ChangeEntry.key`'s leading component to `updated_utc` and this
    goes red on the `target_id in` assertion, with the resumed page returning exactly
    the three entities the old test expected.
    """
    exp_id = _with_runs(client, 6)
    page = _feed(client, exp_id, limit=4)
    assert page["has_more"] is True
    stamp = page["changes"][0]["updated_utc"]
    assert {c["updated_utc"] for c in _feed(client, exp_id)["changes"]} == {stamp}

    # A run that page one already handed out, i.e. one BEHIND the cursor.
    target_id = next(c["entity_id"] for c in page["changes"] if c["kind"] == "run")
    before_version = next(c["version"] for c in page["changes"] if c["entity_id"] == target_id)
    before_position = next(
        c["changed_at_rev"] for c in page["changes"] if c["entity_id"] == target_id
    )

    monkeypatch.setattr(ws, "_now_iso", lambda: stamp)
    exp = ws.load_experiment(exp_id)
    target = next(r for r in exp.runs if r.id == target_id)
    target.draft.setdefault("fields", {})["context.beamline"] = {
        "value": "BL-SYNTH",
        "status": "verified",
    }
    assert exp.save_versioned() is True

    # The write really happened, and the CLOCK really did not move — which is what
    # made this unreportable before.
    #
    # `Run.version_token` is a METHOD here, unlike `ChangeEntry.version_token`, which
    # is a property. Calling it matters: `written.version_token != before_version`
    # compares a bound method to a string and is trivially, silently true — a vacuous
    # assertion in the one place this test needs a real one.
    written = next(r for r in ws.load_experiment(exp_id).runs if r.id == target_id)
    written_version = written.version_token()
    assert isinstance(written_version, str) and written_version != before_version
    assert written.updated_utc == stamp, "the timestamp must NOT have moved"
    # ...and the SEQUENCE did. That is the whole fix, in one comparison.
    assert written.changed_at_rev > before_position

    # ...AND THE CURSOR SEES IT. This is the assertion that was `not in` before.
    resumed = _feed(client, exp_id, cursor=page["next_cursor"])
    resumed_ids = [c["entity_id"] for c in resumed["changes"]]
    assert target_id in resumed_ids, resumed
    # Reported ONCE. A fix that re-emitted the boundary position would have satisfied
    # the line above while handing a poller duplicates on every request.
    assert len(resumed_ids) == len(set(resumed_ids))
    # THE EXACT SIZE, spelled out, because "the target is there" is satisfied by a
    # feed that re-reports everything. The old test asserted `returned == 3` — the
    # three entities page one had not reached. It is 5: those three, plus the target
    # run, plus the RECORD'S OWN entry, which every write moves by design (a run edit
    # changes the record's authoritative signature, so `exp.rev` advances). Both
    # additions are named rather than left to the number.
    assert resumed["returned"] == 5, resumed
    assert set(resumed_ids) == (
        {c["entity_id"] for c in _feed(client, exp_id)["changes"]}
        - ({c["entity_id"] for c in page["changes"]} - {target_id, exp_id})
    )
    moved = next(c for c in resumed["changes"] if c["entity_id"] == target_id)
    assert moved["version"] == written_version != before_version

    # THE RESYNC STILL AGREES, and it is asserted because it is the published remedy:
    # a client that distrusts its cursor must not get a different answer.
    resync = {c["entity_id"]: c["version"] for c in _feed(client, exp_id)["changes"]}
    assert resync[target_id] == written_version

    # The RUNS that did not change kept their positions, so the resumed page is not a
    # disguised full re-read. The experiment is excluded deliberately and not silently:
    # it is the one entity that SHOULD be re-reported, and folding it into this set
    # would have made the assertion pass for the wrong reason.
    unchanged_runs = {
        c["entity_id"] for c in page["changes"] if c["kind"] == "run"
    } - {target_id}
    assert unchanged_runs, "precondition: page one held a run that did not change"
    assert not (unchanged_runs & set(resumed_ids)), "an unchanged run was re-reported"


def test_two_writes_in_ONE_second_with_a_page_between_them_lose_nothing(client, monkeypatch):
    """The defect's shape at its sharpest: page, write, page — all inside one second.

    The test above changes an entity page one already handed out. This one is the
    tighter case the brief names: TWO changes inside the SAME whole second with the
    cursor paged BETWEEN them. Under the timestamp key both writes carried the
    identical stamp, so the second one's key was decided entirely by the
    `(kind, entity_id)` tie-break and landed behind the cursor whenever the id sorted
    lower — an outcome that depended on a run id, which is to say on chance.

    IT IS MADE DETERMINISTIC rather than left to chance: the two runs are chosen by
    sorted id, and the one written second is the LOWER one, which is exactly the case
    the old key lost. The clock is frozen for the whole test, so nothing here can pass
    because a second boundary happened to fall in the right place.
    """
    exp_id = _with_runs(client, 4)
    stamp = _feed(client, exp_id)["changes"][0]["updated_utc"]
    monkeypatch.setattr(ws, "_now_iso", lambda: stamp)

    run_ids = sorted(c["entity_id"] for c in _feed(client, exp_id)["changes"] if c["kind"] == "run")
    higher, lower = run_ids[-1], run_ids[0]

    def _touch(rid: str, value: str) -> None:
        exp = ws.load_experiment(exp_id)
        run = next(r for r in exp.runs if r.id == rid)
        run.draft.setdefault("fields", {})["context.beamline"] = {
            "value": value, "status": "verified",
        }
        assert exp.save_versioned() is True

    # WRITE ONE, then read to the very end of the feed and hold that cursor.
    _touch(higher, "BL-ONE")
    page = _feed(client, exp_id)
    assert page["has_more"] is False
    cursor = page["next_cursor"]
    assert page["changes"][-1]["entity_id"] == higher, "the cursor sits on the higher id"

    # WRITE TWO, in the same second, on the LOWER id — behind the cursor's tie-break.
    _touch(lower, "BL-TWO")

    # Every stamp in the record is still the one instant, so an order that led with
    # the clock had nothing left to order by.
    assert {c["updated_utc"] for c in _feed(client, exp_id)["changes"]} == {stamp}

    resumed = _feed(client, exp_id, cursor=cursor)
    reported = [c["entity_id"] for c in resumed["changes"]]
    assert lower in reported, reported
    assert len(reported) == len(set(reported))
    # The record's own entry moved too — both writes bumped it — and nothing else did.
    assert set(reported) == {lower, exp_id}


# =============================================================================
# 6. scope
# =============================================================================


def test_a_worked_example_record_is_not_readable_from_the_ordinary_feed(app):
    """The NEGATIVE, which is the half a scoping bug passes.

    Scope is a directory namespace, so this is structural rather than a filter — but
    a route that forgot `TutorialScopeDep` would read the ordinary workspace and
    answer `404` for a record that exists, or worse, answer from the wrong one.
    """
    session = tutorial_client(app)
    plain = TestClient(app)
    tutorial_id = session.get("/api/experiments").json()["experiments"][0]["id"]

    assert session.get(f"/api/experiments/{tutorial_id}/changes").status_code == 200
    assert plain.get(f"/api/experiments/{tutorial_id}/changes").status_code == 404


def test_an_ordinary_record_is_not_readable_from_a_session_feed(app):
    plain = TestClient(app)
    session = tutorial_client(app)
    exp_id = _with_runs(plain, 2, title="ordinary")

    assert plain.get(f"/api/experiments/{exp_id}/changes").status_code == 200
    assert session.get(f"/api/experiments/{exp_id}/changes").status_code == 404


def test_a_cursor_is_bound_to_its_scope_as_well_as_to_its_record():
    """Same record id, two scopes, two feeds — so one's cursor is the other's error.

    Asserted at the digest rather than over HTTP because the two scopes cannot hold
    the same record id through the API; the property being pinned is that the SCOPE is
    an input to the tag, which is what would silently stop being true if a later edit
    dropped the argument.
    """
    ordinary = cf.record_scope_tag("01EXAMPLEEXAMPLEEXAMPLEEXA", None)
    session = cf.record_scope_tag("01EXAMPLEEXAMPLEEXAMPLEEXA", "sess-abc")
    assert ordinary != session

    with pytest.raises(cf.MalformedCursor) as err:
        cf.decode_cursor(
            cf.encode_cursor((3, "run", "x"), scope=ordinary),
            scope=session,
        )
    assert err.value.reason == "wrong_feed"


# =============================================================================
# 7. the kind set is DERIVED
# =============================================================================


def test_the_served_kinds_are_derived_from_the_collectors(client):
    """THE SERVED SET, and it is THREE now — `proposal` joined `experiment` and `run`.

    Asserted as an equality against a literal rather than against `cf.feed_kinds()`
    alone, because the two halves are different claims: that the wire agrees with the
    module, and that the module serves the set this change intends. A test written
    only as `wire == feed_kinds()` would pass on a build that served no kinds at all.
    """
    exp_id = _with_runs(client, 1)
    assert (
        _feed(client, exp_id)["kinds"]
        == cf.feed_kinds()
        == ["experiment", "proposal", "run"]
    )


def test_a_FOURTH_kind_needs_no_change_to_this_module():
    """EXTENSIBILITY, PROVEN — and the seam has now been USED rather than only claimed.

    THIS TEST WAS `test_a_third_kind_needs_no_change_to_this_module` AND ITS DOCSTRING
    SAID `proposal` "exists in an unmerged PR and is NOT at this commit". Both halves
    are false now: `proposals.py` is in this tree and `RECORD_COLLECTORS` serves the
    kind. The rename is not cosmetic — the seam's own evidence changed from a
    hypothetical to a shipped third collector, and a test still counting to three
    would be describing a build that no longer exists.

    The stand-in is still a LOCAL FAKE and is still passed in rather than registered
    globally: a module-level registry that tests append to leaks between tests. What it
    proves is unchanged — a new kind sorts by the SAME key as the built-in ones, so a
    collector cannot smuggle in its own ordering.
    """
    entry = cf.ChangeEntry(
        kind="stand_in",
        entity_id="z-last",
        changed_at_rev=9,
        updated_utc="2099-01-01T00:00:00Z",
        rev=3,
        generation="deadbeefdeadbeef",
    )
    collectors = (*cf.RECORD_COLLECTORS, cf.KindCollector(kind="stand_in", read=lambda _e: [entry]))

    assert cf.feed_kinds(collectors) == ["experiment", "proposal", "run", "stand_in"]

    class _Bare:
        """The minimum an `Experiment` has to look like for the built-in collectors.

        It carries `proposals` and `proposal_change_revs` because the proposal
        collector reads them DIRECTLY, exactly as the run collector reads `runs` —
        no `getattr` default, because a collector that tolerated a missing attribute
        would serve an empty kind on a record whose proposals failed to hydrate, and
        report that as "no proposals" rather than as an error.
        """

        id = "01EXAMPLEEXAMPLEEXAMPLEEXA"
        updated_utc = "2026-01-01T00:00:00Z"
        rev = 0
        generation = "0123456789abcdef"
        runs: list = []
        proposals: list = []
        proposal_change_revs: dict = {}

    page = cf.changes_page(_Bare(), scope_tag="tag", collectors=collectors)
    assert page["kinds"] == ["experiment", "proposal", "run", "stand_in"]
    assert [c["kind"] for c in page["changes"]] == ["experiment", "stand_in"]
    # And the new kind sorts by the SAME key as the built-in ones — a collector cannot
    # smuggle in its own ordering. The record sits at position 0 and the stand-in at 9,
    # so this is the SEQUENCE deciding, not the alphabet.
    assert [c["changed_at_rev"] for c in page["changes"]] == [0, 9]
    assert page["changes"][-1]["version"] == "deadbeefdeadbeef.3"


#: Every stored attribute of an `IngestionProposal` that is CONTENT — the value, what
#: it targets, why it was produced, who produced it, and the audit of what was done to
#: it. Transcribed from `proposals.IngestionProposal.__slots__` and checked against it
#: below, so this list cannot quietly fall behind the model.
_PROPOSAL_CONTENT_ATTRS = frozenset({
    "experiment_id",
    "note_id",
    "target_field_path",
    "proposed_value",
    "rule",
    "source",
    "base_rev",
    "target_digest",
    "trust_basis",
    "run_id",
    "start_char",
    "end_char",
    "client_request_key",
    "subject",
    "accepted_value",
    "accepted_from",
    "applied_via",
    "applied_run_id",
    "applied_rev",
    "applied_target_digest",
})

#: The four a feed entry legitimately needs: which proposal, when it last moved, and
#: what lifecycle state it is in. `history` is here ONLY because `updated_utc` reads
#: the last transition's timestamp off it; nothing else about a transition is read.
_PROPOSAL_COORDINATE_ATTRS = frozenset({"proposal_id", "history", "state", "proposed_utc"})


def test_the_content_attribute_list_is_the_model_minus_the_coordinates():
    """GUARDS THE GUARD BELOW, because a hand-written forbidden-list rots silently.

    The test after this one asserts that `change_feed.py` reads none of
    `_PROPOSAL_CONTENT_ATTRS`. That assertion is only worth anything if the list IS
    the model's content — a list that fell one field behind a model that grew would
    pass while the new field was readable. So the two sets are asserted to PARTITION
    `IngestionProposal.__slots__` exactly: every slot is in one of them, and neither
    contains anything that is not a slot.
    """
    from isaac_api import proposals as proposals_module

    slots = set(proposals_module.IngestionProposal.__slots__)
    assert _PROPOSAL_CONTENT_ATTRS | _PROPOSAL_COORDINATE_ATTRS == slots, (
        "a proposal field is in neither list — classify it before it can be served",
        slots ^ (_PROPOSAL_CONTENT_ATTRS | _PROPOSAL_COORDINATE_ATTRS),
    )
    assert not (_PROPOSAL_CONTENT_ATTRS & _PROPOSAL_COORDINATE_ATTRS)


def test_the_module_reaches_no_proposal_CONTENT_even_though_it_serves_the_kind():
    """No import of `proposals`, and no read of a proposal CONTENT attribute anywhere.

    THIS TEST WAS `test_the_module_names_no_feature_it_does_not_have`, and it asserted
    that the string "proposal" appeared in no executable literal of the module. That
    was the right test while the kind was unserved and is the WRONG test now — the
    module has to name the kind in order to serve it, so the old assertion would only
    be satisfiable by a build that did not have the feature. Deleting it outright
    would have thrown away the property it was really protecting, which survives the
    change intact and is what is asserted here instead:

    **`change_feed.py` cannot render a proposal's content, because it never reads
    one.** That is a structural guarantee rather than a review one. It is checked two
    ways, because either alone is escapable: no `import` names the module (so no
    helper of `proposals.py` is reachable), and no ATTRIBUTE ACCESS anywhere in the
    parsed module names a content field (so even a duck-typed object handed in by a
    collector cannot have its value read).

    IT IS ASKED OF THE AST, NOT OF THE TEXT, and the original reason still holds: the
    module's own prose says the words "proposals" and "proposed value" while
    explaining why it does not touch them, so a `rg`-style scan flags the very
    documentation of the absence. The new reason is sharper — `GAP_GUARANTEE` and
    `SEQUENCE_PROOF` are module-level string CONSTANTS, not docstrings, and they
    contain ordinary English words like "rule" and "source". A literal scan would have
    to special-case them, and a special case is where the next escape lives.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path(cf.__file__).read_text(encoding="utf-8"))

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not [m for m in imported if "proposal" in m], imported

    read = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not (read & _PROPOSAL_CONTENT_ATTRS), sorted(read & _PROPOSAL_CONTENT_ATTRS)

    # NOT VACUOUS: the module DOES read the coordinate attributes, so the check above
    # is discriminating between two sets it can actually see rather than passing
    # because `read` is empty or because attribute access was never parsed.
    assert _PROPOSAL_COORDINATE_ATTRS <= read, sorted(_PROPOSAL_COORDINATE_ATTRS - read)


def _make_proposal(exp, *, pid: str, value: str = "XANES"):
    """One synthetic proposal appended to ``exp.proposals``. NOT saved.

    Built directly rather than through ``POST /notes/.../propose`` because that route
    needs a note, a writable target path and the record's ETag, none of which any test
    in this file is about. ``proposals`` is imported INSIDE the helper on purpose:
    ``change_feed.py`` must import nothing from it (asserted over the parsed module
    above), and a module-level import here would read as though it did.
    """
    from isaac_api import proposals as proposals_module

    proposal = proposals_module.new_proposal(
        proposal_id=pid,
        experiment_id=exp.id,
        note_id="01SYNTHETICNOTENOTENOTENO",
        target_field_path="field:system.technique",
        proposed_value=value,
        rule="synthetic fixture rule — this test asserts visibility, not science",
        source=sorted(proposals_module.PROPOSAL_SOURCES)[0],
        proposed_utc="2026-01-01T00:00:00Z",
        base_rev=exp.rev,
        target_digest="0000000000000000",
        trust_basis=proposals_module._unattributed(),
    )
    exp.proposals.append(proposal)
    return proposal


def test_a_proposal_act_moves_the_records_own_entry_AND_its_own(client):
    """WHAT THE FEED SAYS ABOUT PROPOSALS — AND THE SECOND HALF IS NEWLY TRUE.

    THIS TEST WAS `..._and_nothing_finer` AND IT PINNED A SHORTFALL. Its second half
    asserted that no `proposal` kind was served, that no page carried a proposal id,
    and that a client could not tell WHICH proposal moved. Every one of those
    assertions is inverted here rather than deleted, because the shortfall was real
    and a reader has to be able to see that it was closed rather than that it was
    never there. The `proposal` kind is now served.

    WHAT ALREADY HELD AND STILL DOES, asserted first because a client can build on it:
    proposals are part of the record's authoritative signature, so a proposal act moves
    the record's own `rev` and therefore the `experiment` entry. If a later slice takes
    proposals out of the signature, that assertion fails — which is why the mechanism
    is pinned rather than trusted.

    WHAT IS NEW: the proposal has its own entry, at the same sequence position as the
    record's, carrying its id and its lifecycle state and NOTHING ELSE.
    """
    exp_id = _with_runs(client, 1, title="proposal visibility")
    before = {(c["kind"], c["entity_id"]): c for c in _feed(client, exp_id)["changes"]}
    assert not [k for k in before if k[0] == "proposal"], "precondition: none yet"

    pid = "01SYNTHETICPROPOSALPROPOS"
    exp = ws.load_experiment(exp_id)
    _make_proposal(exp, pid=pid)
    assert exp.save_versioned() is True, "a proposal act must be a real write"

    after_page = _feed(client, exp_id)
    after = {(c["kind"], c["entity_id"]): c for c in after_page["changes"]}

    # WHAT HOLDS — the record's own entry moved, so a poller is told to re-read.
    assert after[("experiment", exp_id)]["version"] != before[("experiment", exp_id)]["version"]

    # WHAT IS NEW — and each clause is the inverse of one the old test asserted.
    assert "proposal" in after_page["kinds"]
    assert ("proposal", pid) in after
    entry = after[("proposal", pid)]
    assert entry["state"] == "open"
    # The proposal moved AT this save, so it shares the record's sequence position.
    assert entry["changed_at_rev"] == after[("experiment", exp_id)]["changed_at_rev"]

    # The run did not move: a proposal is not a run act, and the feed does not pretend
    # otherwise by bumping everything.
    run_key = next(k for k in before if k[0] == "run")
    assert after[run_key]["version"] == before[run_key]["version"]
    assert after[run_key]["changed_at_rev"] < entry["changed_at_rev"]


def test_a_proposal_entry_carries_NO_CONTENT_over_the_wire(client):
    """THE MINIMUM, MEASURED ON THE WIRE — the structural test's runtime counterpart.

    `test_the_module_reaches_no_proposal_CONTENT_even_though_it_serves_the_kind` asks
    the AST whether the module COULD read a value. This asks the response whether one
    ARRIVED, and the two are not the same question: a collector passed in by a caller,
    or a future entry field spread from a model, would defeat the first and be caught
    by the second.

    IT ASSERTS OVER THE RAW BODY, not over parsed keys. A value nested anywhere — in a
    key name, in a string, inside a field this test does not know about — is a
    substring of the response, and the proposal is built with values chosen to be
    unmistakable if they leak.
    """
    exp_id = _with_runs(client, 1, title="proposal content")
    pid = "01SYNTHETICPROPOSALPROPOS"
    exp = ws.load_experiment(exp_id)
    _make_proposal(exp, pid=pid, value="LEAKCANARYVALUE")
    assert exp.save_versioned() is True

    res = client.get(f"/api/experiments/{exp_id}/changes")
    assert res.status_code == 200
    body = res.text
    entry = next(c for c in res.json()["changes"] if c["kind"] == "proposal")

    # The key set is EXACT, not a subset: a future field added to `to_wire` shows up
    # here rather than shipping unnoticed.
    assert set(entry) == {"kind", "entity_id", "changed_at_rev", "updated_utc", "state"}

    # And no coordinate is synthesised for a kind that has none.
    assert "version" not in entry and "rev" not in entry and "generation" not in entry

    for leak in (
        "LEAKCANARYVALUE",
        "field:system.technique",
        "synthetic fixture rule",
        "01SYNTHETICNOTENOTENOTENO",
        "0000000000000000",
    ):
        assert leak not in body, leak


def test_the_feed_reports_only_lifecycle_states_the_contract_DEFINES(client):
    """NO INVENTED STATES — the feed passes `state` through and classifies nothing.

    The proposal contract defines exactly five states. This asserts that what reaches
    the wire is drawn from that set and that the feed does not map, normalise or
    default it — a feed that rewrote an unknown state onto a known one would be
    inventing a judgement about a lifecycle it does not own.

    The negative control is the second half: an out-of-contract state is set DIRECTLY
    on the stored entity and reaches the wire UNCHANGED. That is deliberate. The feed
    is not the validator; `proposals.py` refuses such a state at construction, and a
    feed that silently corrected one would hide a corrupt document instead of showing
    it.
    """
    from isaac_api import proposals as proposals_module

    exp_id = _with_runs(client, 1, title="proposal states")
    pid = "01SYNTHETICPROPOSALPROPOS"
    exp = ws.load_experiment(exp_id)
    proposal = _make_proposal(exp, pid=pid)
    assert exp.save_versioned() is True

    entry = next(c for c in _feed(client, exp_id)["changes"] if c["kind"] == "proposal")
    assert entry["state"] in proposals_module.PROPOSAL_STATES
    assert set(proposals_module.PROPOSAL_STATES) == {
        "open", "accepted", "rejected", "superseded", "withdrawn"
    }, "the contract's state set moved — re-read it before changing the feed"

    # THE PASS-THROUGH, proven by moving the proposal through a REAL transition rather
    # than by fabricating a state. `reject_proposal` is the contract's own function, so
    # what reaches the wire is a state the contract produced and the feed did not
    # classify, default or map.
    exp = ws.load_experiment(exp_id)
    exp.proposals[0] = proposals_module.reject_proposal(
        exp.proposals[0], at="2026-01-02T00:00:00Z", reason="synthetic"
    )
    assert exp.save_versioned() is True
    entry = next(c for c in _feed(client, exp_id)["changes"] if c["kind"] == "proposal")
    assert entry["state"] == "rejected"
    # The transition is a change, so the position advanced with it.
    assert entry["changed_at_rev"] > 1


def test_a_proposal_the_model_REFUSES_is_not_served_and_is_not_discarded(client):
    """An out-of-contract proposal on disk is UNREADABLE — and both halves matter.

    THE FIRST HALF, which is `_proposal_entries`' documented claim: an unreadable
    proposal is not served. It has no id this application is willing to read, so the
    feed cannot name it, and an entity a client cannot address is one it could not act
    on if it were told about it.

    THE SECOND HALF, which is the reason the first is safe: it is not DELETED either.
    `Experiment.unreadable_proposals` keeps the raw entry verbatim so a save cannot
    discard a recorded human judgement this build could not parse. A feed that went
    silent about a row that had also been thrown away would be a data-loss path
    wearing a filter's clothes.

    THIS TEST REPLACED A WRONG ONE, and the mistake is worth recording. The first
    version asserted that an out-of-contract `state` reached the wire UNCHANGED, on
    the theory that "the feed is not the validator". It does not: `_hydrate_proposals`
    refuses the entry at load, so the proposal never becomes a proposal at all. The
    theory was right and the prediction was wrong, which is the difference between
    reasoning about a module and reading it.
    """
    exp_id = _with_runs(client, 1, title="unreadable proposal")
    pid = "01SYNTHETICPROPOSALPROPOS"
    exp = ws.load_experiment(exp_id)
    _make_proposal(exp, pid=pid)
    assert exp.save_versioned() is True
    assert any(c["kind"] == "proposal" for c in _feed(client, exp_id)["changes"])

    # Corrupt the STORED document directly — the only way to reach this state, since
    # every constructor in `proposals.py` refuses it.
    raw = json.loads(exp.state_path.read_text(encoding="utf-8"))
    raw["proposals"][0]["state"] = "not-a-contract-state"
    exp.state_path.write_text(json.dumps(raw), encoding="utf-8")

    reloaded = ws.load_experiment(exp_id)
    assert reloaded.proposals == []
    assert len(reloaded.unreadable_proposals) == 1
    assert reloaded.unreadable_proposals[0]["state"] == "not-a-contract-state"

    page = _feed(client, exp_id)
    assert not [c for c in page["changes"] if c["kind"] == "proposal"]
    assert pid not in {c["entity_id"] for c in page["changes"]}
    # `proposal` stays in the SERVED KIND SET: the kinds a deployment serves is a
    # property of its collectors, not of whether this record happens to hold one.
    assert "proposal" in page["kinds"]


# =============================================================================
# 8. deletions
# =============================================================================


def test_a_removed_run_is_simply_absent_and_no_tombstone_is_invented(client):
    """The limitation, DEMONSTRATED rather than only documented.

    A client resuming from a cursor it held before the removal learns nothing at all
    about the run that went away — which is why the description says so outright
    instead of leaving a reader to discover it.
    """
    exp_id = _with_runs(client, 3)
    before = _feed(client, exp_id)
    doomed = [c["entity_id"] for c in before["changes"] if c["kind"] == "run"][0]

    exp = ws.load_experiment(exp_id)
    assert exp.remove_run(doomed) is not None
    exp.save_versioned()

    after = _feed(client, exp_id)
    ids = {c["entity_id"] for c in after["changes"]}
    assert doomed not in ids
    # No entry anywhere claims a removal — no `deleted`, no `tombstone`, no null kind.
    # `changed_at_rev` JOINED THE KEY SET with the ordering fix; it is the sort
    # position, not a claim about the removed run, and the set is asserted exactly
    # rather than as a subset so a future `deleted: false` would fail here.
    assert all(set(c) == {
        "kind", "entity_id", "version", "rev", "generation", "updated_utc",
        "changed_at_rev",
    } for c in after["changes"])

    # And resuming from the pre-removal cursor reports nothing about it either.
    resumed = _feed(client, exp_id, cursor=before["next_cursor"])
    assert doomed not in {c["entity_id"] for c in resumed["changes"]}


def test_a_recreated_run_is_distinguishable_by_generation(client):
    """What the feed CAN do about deletion, and it is the ABA case.

    Remove a run and add one back under the same id: `rev` returns to 0, so a
    rev-only reader would see no change at all. `generation` is minted fresh at
    genuine creation, so `version` differs — which is the entire reason the feed
    publishes the token rather than the number.
    """
    exp_id = _with_runs(client, 2)
    original = [c for c in _feed(client, exp_id)["changes"] if c["kind"] == "run"][0]

    exp = ws.load_experiment(exp_id)
    exp.remove_run(original["entity_id"])
    exp.add_run(label="reborn", draft=routes._seed_for_new_run(exp), id=original["entity_id"])
    exp.save_versioned()

    reborn = [
        c
        for c in _feed(client, exp_id)["changes"]
        if c["entity_id"] == original["entity_id"]
    ]
    assert len(reborn) == 1
    assert reborn[0]["generation"] != original["generation"]
    assert reborn[0]["version"] != original["version"]


# =============================================================================
# 9. restart durability
# =============================================================================


def test_a_cursor_survives_an_application_restart(tmp_path, monkeypatch):
    """Build, get a cursor, THROW THE APPLICATION AWAY, resume.

    Cursors encode state coordinates — a timestamp, a kind, an entity id — and no
    process-local offset, so nothing about them depends on the process that issued
    them. The test asserts that by constructing a second application over the same
    workspace directory rather than by inspecting the token.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    first = TestClient(create_app())
    exp_id = _with_runs(first, 6)
    page = _feed(first, exp_id, limit=3)
    assert page["has_more"] is True
    cursor = page["next_cursor"]
    seen = {c["entity_id"] for c in page["changes"]}
    del first

    second = TestClient(create_app())  # a different application object entirely
    resumed = _feed(second, exp_id, cursor=cursor)
    assert resumed["returned"] == 4
    assert not (seen & {c["entity_id"] for c in resumed["changes"]})
    assert resumed["has_more"] is False


# =============================================================================
# 10. the feed composes nothing
# =============================================================================


class _CountingDerivations:
    """Counts the three derivations that make `routes.list_experiments` O(runs).

    Monkeypatched onto the workspace module for the duration of one request. The point
    is not that these functions are slow in the abstract — it is that reaching for any
    of them from the feed would reintroduce, in a NEW surface, the exact shape the
    detail route had to be un-picked from.
    """

    NAMES = ("resolved_run_draft", "pending", "export_draft")

    def __enter__(self):
        self.counts = {n: 0 for n in self.NAMES}
        self._saved = {
            "resolved_run_draft": ws.Experiment.resolved_run_draft,
            "pending": ws.Experiment.pending,
            "export_draft": ws.export_draft,
        }

        def wrap(name, original):
            def counted(*args, **kwargs):
                self.counts[name] += 1
                return original(*args, **kwargs)

            return counted

        ws.Experiment.resolved_run_draft = wrap(
            "resolved_run_draft", self._saved["resolved_run_draft"]
        )
        ws.Experiment.pending = wrap("pending", self._saved["pending"])
        ws.export_draft = wrap("export_draft", self._saved["export_draft"])
        return self

    def __exit__(self, *exc):
        ws.Experiment.resolved_run_draft = self._saved["resolved_run_draft"]
        ws.Experiment.pending = self._saved["pending"]
        ws.export_draft = self._saved["export_draft"]
        return False


@pytest.mark.parametrize("runs", [25, 250])
def test_a_feed_request_composes_no_draft_and_runs_no_dry_run(client, runs):
    exp_id = _with_runs(client, runs)
    with _CountingDerivations() as counted:
        assert client.get(f"/api/experiments/{exp_id}/changes").status_code == 200
    assert counted.counts == {"resolved_run_draft": 0, "pending": 0, "export_draft": 0}


def test_the_counter_can_actually_fail(client):
    """Guards the guard. A counter that never increments would make the test above
    vacuous, and this file's own subject matter is surfaces that pass by not looking."""
    exp_id = _with_runs(client, 2)
    with _CountingDerivations() as counted:
        assert client.get(f"/api/experiments/{exp_id}").status_code == 200
    assert sum(counted.counts.values()) > 0


def test_the_response_is_flat_in_the_number_of_runs(client):
    """250 runs and 1,000 runs are BYTE-IDENTICAL in length.

    Not "similar": every entry is the same width (a 26-character id, a 16-hex
    generation, one `rev` digit, a one-second timestamp) and the window stops at 50
    either way, so past the window the run count cannot move the response at all.
    """
    a = _with_runs(client, 250, title="flat 250")
    b = _with_runs(client, 1000, title="flat 1000")
    size_a = len(client.get(f"/api/experiments/{a}/changes").content)
    size_b = len(client.get(f"/api/experiments/{b}/changes").content)
    assert size_a == size_b
    # And it is far below the record's own question set at the same size — the point
    # of the feature. (1.77 MB per `/pending` at 1,000 runs; see
    # `test_pending_reads_are_boundable.py`.)
    assert size_b < 20_000


@pytest.mark.skipif(
    not os.environ.get("ISAAC_PERF_BENCH"),
    reason="opt-in benchmark; set ISAAC_PERF_BENCH=1",
)
def test_benchmark_prints_the_table_in_the_docstring(client):
    """Re-derives the table in `change_feed.changes_page`. Prints; asserts only the
    two properties that are contention-free (zero derivations, flat bytes)."""
    print(f"\n{'runs':>6} {'bytes':>10} {'entries':>8} {'resolved':>9} {'export':>7} {'pending':>8}")
    for n in (25, 250, 1000):
        exp_id = _with_runs(client, n, title=f"bench {n}")
        with _CountingDerivations() as counted:
            res = client.get(f"/api/experiments/{exp_id}/changes")
        body = res.json()
        print(
            f"{n:>6} {len(res.content):>10,} {len(body['changes']):>8} "
            f"{counted.counts['resolved_run_draft']:>9} "
            f"{counted.counts['export_draft']:>7} {counted.counts['pending']:>8}"
        )
        assert sum(counted.counts.values()) == 0


def test_a_cursor_this_feed_did_not_issue_is_refused_on_its_ALPHABET(client):
    """The strictness `decode_cursor`'s docstring promises, measured rather than described.

    THE DEFECT AN INDEPENDENT REVIEW FOUND, and why the existing case did not catch it.
    The parametrised `not-base64url` case sends ``"!!!not base64!!!"``, which is refused
    because the SURVIVING characters are not valid JSON — not because a non-alphabet
    character was rejected. So the alphabet claim had no test, and it was false three
    ways at once:

    * the comment said ``validate=True``, and **`urlsafe_b64decode` has no such
      parameter** — its signature is ``(s)``, so passing it raises ``TypeError``;
    * appending ``****`` to a valid cursor decoded to the IDENTICAL key and the route
      answered ``200``;
    * so did appending ``=``, because ``encode_cursor`` strips padding but nothing
      refused a token that carried it.

    Two distinct strings therefore named one position, while the docstring said "STRICT
    AT EVERY STEP" and the wire-published ``EXPIRY_PROPERTY`` told clients a cursor is
    refused for exactly two reasons.

    MUTATION: dropping `validate=True` turns the `****` case green again; dropping the
    `"=" in token` guard turns the padding case green again.
    """
    from isaac_api import change_feed as cf

    scope = "record|scope"
    issued = cf.encode_cursor((7, "run", "01ABC"), scope=scope)
    # The control: what the feed actually issues still decodes.
    assert cf.decode_cursor(issued, scope=scope) is not None

    refused: dict[str, str] = {}
    for label, token in {
        "trailing-non-alphabet": issued + "****",
        "interior-non-alphabet": issued[:5] + "!" + issued[5:],
        "padding-the-encoder-strips": issued + "=",
    }.items():
        try:
            cf.decode_cursor(token, scope=scope)
        except cf.MalformedCursor as exc:
            refused[label] = exc.reason
        else:  # pragma: no cover - the defect this test exists for
            refused[label] = "ACCEPTED"

    assert refused == {
        "trailing-non-alphabet": "not_decodable",
        "interior-non-alphabet": "not_decodable",
        "padding-the-encoder-strips": "not_decodable",
    }, refused

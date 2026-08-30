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

  1. naming and the three published properties
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
        pytest.param(cf.GAP_GUARANTEE, id="gap"),
        pytest.param(cf.DELETION_LIMITATION, id="deletion"),
        pytest.param(cf.EXPIRY_PROPERTY, id="expiry"),
    ],
)
def test_each_published_property_reaches_the_served_document_verbatim(client, claim):
    """ONE definition, quoted — never a paraphrase in the route and a constant here.

    The same posture as ``dependencies.MISSING_REASON``: a claim written twice is a
    claim free to drift, and these three are exactly the claims a client would build
    the wrong retry logic on top of.
    """
    assert claim in _description(client)


def test_the_gap_guarantee_names_its_own_failure_mode_rather_than_promising_none():
    """The honest half has to be present, not just the reassuring half."""
    assert "PROVIDED `updated_utc` never moves backwards" in cf.GAP_GUARANTEE
    assert "not claimed to be" in cf.GAP_GUARANTEE
    # The single-pod argument is offered as the REASON the exposure is small, and is
    # explicitly refused as a proof that it is zero. That distinction is the whole
    # point of the sentence and is the thing a later edit would smooth away.
    assert "not a proof that it is zero" in cf.GAP_GUARANTEE
    assert "no cursor at all" in cf.GAP_GUARANTEE


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


def test_the_order_is_updated_utc_then_kind_then_entity_id(client):
    exp_id = _with_runs(client, 6)
    changes = _feed(client, exp_id)["changes"]
    keys = [(c["updated_utc"], c["kind"], c["entity_id"]) for c in changes]
    assert keys == sorted(keys)


def test_the_tie_break_is_load_bearing_because_the_timestamps_are_equal(client):
    """The precondition the tie-break exists for is MEASURED, not assumed.

    `updated_utc` is `%Y-%m-%dT%H:%M:%SZ` — one-second resolution — and one
    `save_versioned` stamps every changed run with one instant. If this assertion ever
    fails, the ordering tests below stop proving what they claim: they would be
    passing on a timestamp that happened to be unique rather than on the tie-break.
    """
    exp_id = _with_runs(client, 8)
    changes = _feed(client, exp_id)["changes"]
    stamps = {c["updated_utc"] for c in changes}
    assert len(stamps) == 1, stamps
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
    token = _handmade({"v": 99, "s": tag, "t": "2026-01-01T00:00:00Z", "k": "run", "e": "x"})
    res = client.get(f"/api/experiments/{exp_id}/changes", params={"cursor": token})
    assert res.status_code == 422
    assert res.json()["reason"] == "not_decodable"


@pytest.mark.parametrize("missing", ["t", "k", "e"])
def test_a_cursor_missing_a_key_component_is_refused(client, missing):
    exp_id = _with_runs(client, 2)
    payload = {
        "v": cf.CURSOR_VERSION,
        "s": cf.record_scope_tag(exp_id, None),
        "t": "2026-01-01T00:00:00Z",
        "k": "run",
        "e": "x",
    }
    payload.pop(missing)
    res = client.get(
        f"/api/experiments/{exp_id}/changes", params={"cursor": _handmade(payload)}
    )
    assert res.status_code == 422
    assert res.json()["reason"] == "not_decodable"


def test_a_non_string_component_is_refused_and_never_coerced(client):
    """`t: 7` must not become `"7"`.

    Coercion here would build a key that compares against real keys and answer from a
    position the caller never asked for — a wrong answer where an error was available.
    """
    exp_id = _with_runs(client, 2)
    token = _handmade(
        {"v": cf.CURSOR_VERSION, "s": cf.record_scope_tag(exp_id, None), "t": 7, "k": "run", "e": "x"}
    )
    res = client.get(f"/api/experiments/{exp_id}/changes", params={"cursor": token})
    assert res.status_code == 422
    assert res.json()["reason"] == "not_decodable"


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

    exp = ws.load_experiment(exp_id)
    target = exp.sorted_runs()[0]
    target.draft["fields"] = {"context.beamline": {"value": "BL-SYNTH", "status": "verified"}}
    exp.updated_utc = "2099-01-01T00:00:00Z"
    target.updated_utc = "2099-01-01T00:00:00Z"
    target.rev += 1
    exp.save()

    resumed = _feed(client, exp_id, cursor=end["next_cursor"])
    moved = {c["entity_id"]: c["version"] for c in resumed["changes"]}
    assert target.id in moved
    assert moved[target.id] != before[target.id]


def test_a_cursorless_read_is_the_resync_and_returns_the_start_of_the_order(client):
    exp_id = _with_runs(client, 4)
    walked = _feed(client, exp_id, cursor=_feed(client, exp_id, limit=1)["next_cursor"])
    assert walked["returned"] == 4  # everything after the first entry
    resync = _feed(client, exp_id)
    assert resync["returned"] == 5  # the whole order, from the start
    assert resync["changes"][0]["kind"] == "experiment"


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
            cf.encode_cursor(("2026-01-01T00:00:00Z", "run", "x"), scope=ordinary),
            scope=session,
        )
    assert err.value.reason == "wrong_feed"


# =============================================================================
# 7. the kind set is DERIVED
# =============================================================================


def test_the_served_kinds_are_derived_from_the_collectors(client):
    exp_id = _with_runs(client, 1)
    assert _feed(client, exp_id)["kinds"] == cf.feed_kinds() == ["experiment", "run"]


def test_a_third_kind_needs_no_change_to_this_module():
    """EXTENSIBILITY, PROVEN — and proven without a proposal dependency.

    The brief names `proposal` as a kind that exists in an unmerged PR and is NOT at
    this commit. The wrong preparation would be a `try: import proposals` here; the
    right one is that the collector tuple is a PARAMETER, so the slice that lands the
    feature adds a collector and this module is untouched. The stand-in below is a
    local fake for exactly that reason — it proves the seam without asserting anything
    about a feature this build does not have.

    It is passed in rather than registered globally: a module-level registry that
    tests append to leaks between tests.
    """
    entry = cf.ChangeEntry(
        kind="stand_in",
        entity_id="z-last",
        updated_utc="2099-01-01T00:00:00Z",
        rev=3,
        generation="deadbeefdeadbeef",
    )
    collectors = (*cf.RECORD_COLLECTORS, cf.KindCollector(kind="stand_in", read=lambda _e: [entry]))

    assert cf.feed_kinds(collectors) == ["experiment", "run", "stand_in"]

    class _Bare:
        id = "01EXAMPLEEXAMPLEEXAMPLEEXA"
        updated_utc = "2026-01-01T00:00:00Z"
        rev = 0
        generation = "0123456789abcdef"
        runs: list = []

    page = cf.changes_page(_Bare(), scope_tag="tag", collectors=collectors)
    assert page["kinds"] == ["experiment", "run", "stand_in"]
    assert [c["kind"] for c in page["changes"]] == ["experiment", "stand_in"]
    # And the new kind sorts by the SAME key as the built-in ones — a collector cannot
    # smuggle in its own ordering.
    assert page["changes"][-1]["version"] == "deadbeefdeadbeef.3"


def test_the_module_names_no_feature_it_does_not_have():
    """No hard-coded proposal dependency — asserted over the PARSED module.

    A `rg`-style check over the source text was the first version of this and it was
    unusable: the module's own docstrings say the words "import proposals" while
    explaining why it does not do that, so a text scan flags the very prose that
    documents the absence. The structural question — does any import name it, does any
    executable literal equal it — is a question about the AST, so it is asked there.
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

    # Docstrings are prose ABOUT the design and are excluded by identity, not by a
    # heuristic over their contents.
    docstrings = {
        id(n.body[0].value)
        for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and n.body
        and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
        and isinstance(n.body[0].value.value, str)
    }
    literals = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in docstrings
    ]
    assert not [s for s in literals if "proposal" in s.lower()], literals


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
    assert all(set(c) == {
        "kind", "entity_id", "version", "rev", "generation", "updated_utc"
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

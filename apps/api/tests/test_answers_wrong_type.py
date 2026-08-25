"""A wrong-typed answer must never return 500.

FOUND BY the R3 browser mutation suite, not by any unit test — which is the argument
for that suite existing. A fixture sent a sha256 STRING for record 2's first pending
blocker, assuming it was an asset hash. It is a `series` blocker, and the request came
back:

    AttributeError: 'str' object has no attribute 'get'
      src/isaac_records/complete.py:106  in apply_answers
      apps/api/isaac_api/routes.py:1135  in post_answers
    -> HTTP 500

`draft["series"]` was set to the string, then iterated — so `s` was a single character
and `s.get("series_id")` raised. `descriptor` had the same shape of hole one branch
down (`desc["evidence"] = [...]` raises TypeError on a str). `qc` did NOT: it already
type-guarded with `isinstance(qc_answer, dict)`, which is the convention the fix
follows.

WHAT THE FIX CHOSE, and what it deliberately did not. A wrong-typed answer now takes
the module's existing "not applied -> stays pending" path, the same one an off-enum qc
verdict takes. It does NOT return a typed 422 naming the offending field. A 422 would
be better API hygiene and is a reasonable follow-up, but it needs the route to
distinguish "dropped because wrong type" from "dropped because unrecognised", which is
a wider change than removing a crash. The crash is the defect; the 422 is an
improvement. This test pins the crash being gone, and pins that nothing was written.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from isaac_api.app import create_app

from conftest import tutorial_client, tutorial_ws

PARTIAL = "01SYNTHXANESSEED0000000002"


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    # PER-TEST WORKSPACE, following the convention in test_reset.py. Without it these
    # tests share one workspace: the "correctly-typed series answer applies" test
    # answers a blocker, and every later test then reads a record whose pending set has
    # changed. That showed up while running a negative control — tests that should have
    # been unaffected failed, which reads like a broken fix rather than a dirty fixture.
    monkeypatch.setenv('ISAAC_UI_WORKSPACE', str(tmp_path / 'ws'))
    return tutorial_client(create_app())


def _version(client: TestClient, rid: str) -> str:
    r = client.get(f"/api/experiments/{rid}")
    assert r.status_code == 200, r.text
    return r.json()["version"]


def _pending_kinds(client: TestClient, rid: str) -> dict[str, str]:
    r = client.get(f"/api/experiments/{rid}/pending")
    assert r.status_code == 200, r.text
    return {p["id"]: p["kind"] for p in r.json()["pending"]}


def _post(client: TestClient, rid: str, answers: dict):
    return client.post(
        f"/api/experiments/{rid}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, rid)}"'},
    )


def test_the_fixture_assumption_that_started_this_is_recorded(client):
    """Record 2's open blockers are STRUCTURED, not string-valued. The browser fixture
    assumed an asset hash and sent a sha256; that is how the 500 was found."""
    kinds = _pending_kinds(client, PARTIAL)
    assert set(kinds.values()) == {"series", "descriptor"}, kinds


@pytest.mark.parametrize(
    "answers",
    [
        pytest.param({"series": "d4c0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b999"}, id="series=str"),
        pytest.param({"series": 42}, id="series=int"),
        pytest.param({"series": {"series_id": "s"}}, id="series=dict-not-list"),
        pytest.param({"series": ["not-a-dict"]}, id="series=list-of-str"),
        pytest.param({"descriptor": "a-string"}, id="descriptor=str"),
        pytest.param({"descriptor": [1, 2, 3]}, id="descriptor=list"),
        pytest.param({"qc": "valid"}, id="qc=str (already guarded, kept as a regression)"),
    ],
)
def test_a_wrong_typed_answer_never_returns_500(client, answers):
    res = _post(client, PARTIAL, answers)
    assert res.status_code != 500, (
        f"a wrong-typed answer crashed the server: {answers!r} -> {res.status_code}. "
        "Malformed input must be refused or ignored, never raise out of the truth core."
    )
    assert res.status_code < 500, res.text


@pytest.mark.parametrize(
    "answers",
    [
        {"series": "d4c0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b999"},
        {"descriptor": "a-string"},
    ],
)
def test_a_wrong_typed_answer_writes_nothing_and_leaves_the_field_pending(client, answers):
    before_rev = client.get(f"/api/experiments/{PARTIAL}").json()["rev"]
    before_pending = _pending_kinds(client, PARTIAL)

    res = _post(client, PARTIAL, answers)
    assert res.status_code < 500, res.text

    after = client.get(f"/api/experiments/{PARTIAL}").json()
    assert after["rev"] == before_rev, (
        "a wrong-typed answer must not count as a write — rev moved, so something was "
        "persisted from input the code could not interpret"
    )
    assert _pending_kinds(client, PARTIAL) == before_pending, (
        "the blocker must stay pending: refusing to interpret a value is not the same "
        "as answering it"
    )


def test_no_traceback_or_server_path_reaches_the_client(client):
    """The 500 did not leak (the body was a bare 'Internal Server Error'), and that
    must remain true for whatever status the guard now produces."""
    res = _post(
        client,
        PARTIAL,
        {"series": "d4c0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b999"},
    )
    body = res.text
    for marker in ("Traceback", "complete.py", "routes.py", "/Users/", "/private/tmp", "site-packages"):
        assert marker not in body, f"{marker!r} leaked into the client response: {body[:400]}"


def test_a_correctly_typed_series_answer_still_applies(client):
    """The guard must not reject VALID structured input — otherwise it would convert a
    crash into a silent refusal of legitimate answers, which is worse."""
    kinds = _pending_kinds(client, PARTIAL)
    assert "series" in kinds.values()

    demo = client.get(f"/api/experiments/{PARTIAL}/pending").json()["pending"]
    series_entry = next(p for p in demo if p["kind"] == "series")
    value = (series_entry.get("demo_answer") or {}).get("value")
    assert value is not None, "the series blocker must offer a structured example value"

    before_rev = client.get(f"/api/experiments/{PARTIAL}").json()["rev"]
    res = _post(client, PARTIAL, {"series": value})
    assert res.status_code == 200, res.text
    after = client.get(f"/api/experiments/{PARTIAL}").json()
    assert after["rev"] > before_rev, "a correctly-typed series answer must be applied"


# ---------------------------------------------------------------------------
# POST /edit — the half of this file that did not exist
# ---------------------------------------------------------------------------
#
# THIS FILE HARDENED `POST /answers` AND STOPPED THERE, and the gap was invisible for the
# same reason gaps usually are: nothing named it. `grep -c /edit` over this file returned
# 0 until now, and `apply_answers` in `complete.py` grew type guards while
# `apply_corrections` — the `/edit` path — did not.
#
# MEASURED on the unguarded code, with a valid correction accepted first so the negatives
# mean something:
#
#   series = 5 / "nope" / [1, 2] / a 1 MB string  ->  HTTP 500 from the truth core
#   series = {}                                   ->  HTTP 200, and the already-confirmed
#                                                     series REPLACED BY `{}` — a dict
#                                                     where the schema requires a list
#
# The second is the worse of the two: the first writes nothing and reports failure, while
# the second reports success and destroys a value a scientist had confirmed. Both are
# closed — the core refuses to apply an unusable shape, and the route turns that refusal
# into a typed 422 rather than a silent 200, which its own description requires.


def _valid_series() -> list[dict]:
    return [{"energy_eV": 8979.0, "mu": 0.1, "series_id": "s1"}]


def _valid_descriptor() -> dict:
    return {"value": 8981.2, "unit": "eV", "uncertainty": {"sigma": 0.3}}


def _answer_the_open_questions(client: TestClient) -> None:
    """Confirm `series` and `descriptor` through `/answers`, which is the route for it.

    THESE TESTS USED TO ESTABLISH THE CONFIRMED VALUE THROUGH `/edit`, and that was
    exercising a defect rather than setting up a fixture. `PARTIAL` has both questions
    OPEN, and `/edit` admitted them — storing the value and leaving the question open,
    a `200` about a write that resolved nothing. `/edit` now refuses that with
    `422 not_yet_answered`, so the setup has to use the route that actually answers a
    question. The assertions below are unchanged and are about the same property; only
    the way the "already confirmed" state is reached has moved to the honest path.
    """
    etag = client.get(f"/api/experiments/{PARTIAL}").headers["ETag"]
    res = client.post(
        f"/api/experiments/{PARTIAL}/answers",
        json={
            "confirmed_by_user": True,
            "answers": {"series": _valid_series(), "descriptor": _valid_descriptor()},
        },
        headers={"If-Match": etag},
    )
    assert res.status_code == 200, res.text


def _draft(client: TestClient) -> dict:
    """The draft as the STORE holds it, never as a response summarised it — the claim
    under test is about what was written, not about what was reported."""
    import isaac_api.workspace as ws

    # `tutorial_client` pins the session id on the client for exactly this use.
    exp = ws.load_experiment(PARTIAL, session_id=client.tutorial_session_id)
    assert exp is not None
    return exp.draft


def test_a_valid_structured_correction_is_accepted(client):
    """THE POSITIVE CONTROL, and it is load-bearing rather than ceremonial: an earlier
    investigation of this defect sent the wrong body shape, got 422 for everything
    including the valid case, and concluded the route was already safe. A negative result
    means nothing without this."""
    _answer_the_open_questions(client)
    etag = client.get(f"/api/experiments/{PARTIAL}").headers["ETag"]
    res = client.post(
        f"/api/experiments/{PARTIAL}/edit",
        json={"confirmed_by_user": True, "answers": {"series": _valid_series()}},
        headers={"If-Match": etag},
    )
    assert res.status_code == 200, res.text


@pytest.mark.parametrize(
    "key,value",
    [
        ("series", 5),
        ("series", "nope"),
        ("series", [1, 2]),
        ("series", {}),
        ("series", [{}, 3]),
        ("series", "x" * 100_000),
        # THE TWO CRITICALS, which the first version of this parametrize did not contain —
        # a negative control re-admitting `[]` left every test passing.
        ("series", []),
        ("series", [{"series_id": {"a": 1}, "mu": 0.1}]),
        ("descriptor", {}),
        ("descriptor", 5),
        ("descriptor", "nope"),
        ("descriptor", [1]),
    ],
    ids=[
        "series-int",
        "series-str",
        "series-list-of-ints",
        "series-dict",
        "series-list-with-a-non-dict",
        "series-long-str",
        "series-EMPTY-destroys-a-confirmed-spectrum",
        "series-unhashable-series_id-wedges-the-record",
        "descriptor-EMPTY-destroys-a-confirmed-descriptor",
        "descriptor-int",
        "descriptor-str",
        "descriptor-list",
    ],
)
def test_a_wrong_typed_correction_is_refused_and_destroys_nothing(client, key, value):
    _answer_the_open_questions(client)
    before = _draft(client)

    etag = client.get(f"/api/experiments/{PARTIAL}").headers["ETag"]
    res = client.post(
        f"/api/experiments/{PARTIAL}/edit",
        json={"confirmed_by_user": True, "answers": {key: value}},
        headers={"If-Match": etag},
    )

    # A typed refusal, NOT a 500 and NOT a silent 200.
    assert res.status_code == 422, res.text
    assert res.json()["error"] == "invalid_field_value"
    assert res.json()["keys"] == [key]

    # And the confirmed value the correction would have replaced is byte-identical.
    assert _draft(client).get("series") == before.get("series")
    assert _draft(client).get("series") == _valid_series()
    # The record is still readable — no wedge.
    assert client.get(f"/api/experiments/{PARTIAL}").status_code == 200


# ---------------------------------------------------------------------------
# The core guard, tested AT THE CORE
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS AS A SEPARATE TEST, established by a negative control rather than
# assumed: with the core guard removed, every route-level test above still PASSED, because
# the route now refuses a wrong-typed correction before `apply_corrections` ever sees it.
# So the two layers need two tests, or the inner one is decoration.
#
# It is defence in depth on purpose. `apply_corrections` lives in `src/isaac_records/`, is
# importable by the CLI and by any future caller, and the failure it prevents is not a
# crash but the destruction of an already-confirmed scientific value: `series = {}` used to
# replace a valid series with `{}`, return no error at all, and leave a dict where the
# official schema requires a list.


@pytest.mark.parametrize(
    "value",
    [5, "nope", [1, 2], {}, [{}, 3], [], [{"series_id": {"a": 1}, "mu": 0.1}]],
    ids=[
        "int",
        "str",
        "list-of-ints",
        "dict",
        "list-with-a-non-dict",
        "EMPTY-list",
        "unhashable-series_id",
    ],
)
def test_apply_corrections_refuses_a_wrong_typed_series_without_touching_the_draft(value):
    from isaac_records.complete import apply_corrections

    draft = {"series": [{"energy_eV": 8979.0, "mu": 0.1, "series_id": "s1"}]}
    before = copy.deepcopy(draft)

    out = apply_corrections(draft, {"series": value, "timestamp": "2026-01-01T00:00:00Z"})

    # Neither applied nor raised. The confirmed series is byte-identical.
    assert out["series"] == before["series"]
    assert isinstance(out["series"], list)


@pytest.mark.parametrize(
    "value", [5, "nope", [1], {}], ids=["int", "str", "list", "empty-dict"]
)
def test_apply_corrections_refuses_a_wrong_typed_descriptor(value):
    """ASSERTS ON `descriptors_outputs`, WHICH IS WHERE THE VALUE ACTUALLY GOES.

    The first version of this test asserted `out["descriptor"] == {...}` — a key
    `apply_corrections` NEVER writes. A reviewer replaced the guard with
    `descriptor = {"CORRUPTED_BY_MUTANT": True}`, so a wrong-typed descriptor was absorbed
    and written, and all 31 tests still passed. It proved only "did not raise"; the word
    "refuses" in its name was untested. `{}` is included because it is the case that
    destroyed a confirmed descriptor AND appended an evidence entry reading
    `"answer": "None"` — a recorded human confirmation of a value that does not exist.
    """
    from isaac_records.complete import apply_corrections

    kept = {"name": "d", "value": 1.0, "evidence": [{"source_type": "spreadsheet"}]}
    out = apply_corrections(
        {"descriptors_outputs": [dict(kept)]},
        {"descriptor": value, "timestamp": "2026-01-01T00:00:00Z"},
    )
    # Not applied: the confirmed descriptor is byte-identical, and no confirmation was
    # fabricated for a value that was never supplied.
    assert out["descriptors_outputs"] == [kept]
    assert all(
        e.get("source_type") != "user_confirmation"
        for d in out["descriptors_outputs"]
        for e in (d.get("evidence") or [])
    )


def test_apply_corrections_still_applies_a_WELL_typed_series():
    """The floor. Without it the guards above could pass by refusing everything."""
    from isaac_records.complete import apply_corrections

    fresh = [{"energy_eV": 9000.0, "mu": 0.2, "series_id": "s2"}]
    out = apply_corrections(
        {"series": [{"energy_eV": 1.0, "mu": 0.0, "series_id": "s1"}]},
        {"series": fresh, "timestamp": "2026-01-01T00:00:00Z"},
    )
    assert out["series"] == fresh
    assert "series:s2" in out["block_evidence"]



def test_an_empty_series_correction_cannot_reach_an_exported_record(client):
    """THE HARM, END TO END — and the reason `[]` is refused rather than merely guarded.

    Measured on the unguarded code, on the exportable seed: `POST /edit {"series": []}`
    returned 200 and replaced a confirmed 7-point spectrum with `[]`; `POST /validate` then
    reported `ok: true` with zero errors, and `POST /export` wrote an official ISAAC record
    whose `measurement.series` was `[]`. The schema permits it — `measurement.series` is an
    array with no `minItems` — so nothing downstream could have caught it. A record that
    passes validation while describing no measurement is worse than one that fails.
    """
    exportable = "01SYNTHXANESSEED0000000003"
    before = client.post(f"/api/experiments/{exportable}/validate").json()
    assert before["ok"] is True, "this test needs a record that starts exportable"

    etag = client.get(f"/api/experiments/{exportable}").headers["ETag"]
    res = client.post(
        f"/api/experiments/{exportable}/edit",
        json={"confirmed_by_user": True, "answers": {"series": []}},
        headers={"If-Match": etag},
    )
    assert res.status_code == 422, res.text
    assert res.json()["error"] == "invalid_field_value"

    # Still exportable, and still describing the measurement it described before.
    after = client.post(f"/api/experiments/{exportable}/validate").json()
    assert after["ok"] is True
    etag = client.get(f"/api/experiments/{exportable}").headers["ETag"]
    exported = client.post(
        f"/api/experiments/{exportable}/export", json={}, headers={"If-Match": etag}
    )
    assert exported.status_code == 200, exported.text
    artifacts = client.get(f"/api/experiments/{exportable}/artifacts").json()
    series = ((artifacts.get("record") or {}).get("measurement") or {}).get("series")
    assert isinstance(series, list) and len(series) > 0, (
        "an exported official record must not describe an empty measurement series"
    )


# --- the asset-sha256 hole the type guard did not cover -----------------------


def _asset_uri(client: TestClient, rid: str) -> str:
    """The uri of a still-PENDING asset blocker — the `/answers` fill path's key."""
    pending = client.get(f"/api/experiments/{rid}/pending").json()["pending"]
    uris = [e["id"] for e in pending if e["kind"] == "asset"]
    assert uris, "this test needs a record with a pending asset blocker"
    return uris[0]


def _stored_asset_uri(client: TestClient, rid: str) -> str:
    """The uri of an asset ALREADY IN THE DRAFT — the `/edit` correction path's key.

    A SEPARATE HELPER FROM `_asset_uri`, and the distinction is the whole of the second
    defect found on this route. `/edit` can only overwrite a value that exists, so a
    pending uri and a stored uri are not interchangeable there: a pending one names no
    editable field. Using the pending helper for a `/edit` test measures the
    `unrecognized_field` refusal while appearing to measure the value refusal.
    """
    assets = tutorial_ws().load_experiment(rid).draft.get("assets") or []
    uris = [a["uri"] for a in assets if a.get("uri")]
    assert uris, "this test needs a record with an asset already stored in the draft"
    return uris[0]


@pytest.mark.parametrize(
    "sha,why",
    [
        ("Z" * 64, "64 characters, not hex"),
        ("abc", "far too short"),
        ("5" * 63, "63 hex characters"),
        ("5" * 65, "65 hex characters"),
        ("3" * 64 + " ", "one trailing SPACE"),
        ("3" * 64 + "\n", "one trailing NEWLINE — 65 chars, and `$` used to match it"),
        ("A" * 64, "uppercase hex, which the stored form is not"),
    ],
)
def test_a_malformed_asset_sha_is_refused_rather_than_answered_200(client, sha, why):
    """A CORRECTION THAT CANNOT BE STORED MUST NOT BE REPORTED AS SAVED.

    The `/edit` guard originally asked only `isinstance(value, str)` of an asset sha, so
    every value below passed it, was then declined by `apply_corrections` for being
    malformed, and the route answered **200 with `rev` unmoved and nothing written**.
    Measured before the fix on the first six.

    That is the outcome this route's own comment calls forbidden — "a body that names
    [a recognised field] and gives it an unusable value" gets a typed refusal — closed
    for `series` and `descriptor`, where malformation is a question of TYPE, and left
    open here, where it is a question of FORMAT.

    A scientist correcting a hash with a typo was told it was saved. Nothing was
    destroyed and nothing was invented, which is why no other test caught it.

    THE SEVENTH CASE IS NOT LIKE THE OTHER SIX, and it is why the label on the space
    case now says SPACE. A trailing space was refused all along; a trailing NEWLINE was
    not, because `_SHA256_RE` was `$`-anchored and Python's `$` also matches before a
    final newline. So the parametrize named the category "trailing whitespace" while
    covering only the half of it that already worked. Measured on the `$` pattern:
    `POST /edit` returned 200, stored `'999…9\\n'`, `POST /validate` reported `ok: true`,
    and `POST /export` produced an official record with `official_report.ok: true`.

    ADDRESSED AT A STORED ASSET, not a pending one. A pending uri is not an editable
    field on this route at all (see the two tests below), so aiming this test at one
    would measure the `unrecognized_field` refusal while appearing to measure this one —
    and would keep passing if the value guard were deleted.
    """
    rid = "01SYNTHXANESSEED0000000003"
    uri = _stored_asset_uri(client, rid)
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    before = client.get(f"/api/experiments/{rid}").json()["rev"]
    stored_before = copy.deepcopy(tutorial_ws().load_experiment(rid).draft["assets"])

    res = client.post(
        f"/api/experiments/{rid}/edit",
        json={"confirmed_by_user": True, "answers": {uri: sha}},
        headers={"If-Match": etag},
    )

    assert res.status_code == 422, f"{why}: {res.status_code} {res.text}"
    assert res.json()["error"] == "invalid_field_value"
    assert res.json()["key"] == uri
    assert client.get(f"/api/experiments/{rid}").json()["rev"] == before
    # …and the hash that WAS there is byte-identical, not merely un-advanced.
    assert tutorial_ws().load_experiment(rid).draft["assets"] == stored_before


def test_the_refusal_message_names_no_field_class_but_the_offending_one(client):
    """THE 422's PROSE MUST NOT NAME A CAUSE THE RESPONSE HAS NOT ESTABLISHED.

    Measured on the shipped message, for a body whose only offending key was an ASSET
    URI: "These corrections are not the shape the record can store, so nothing was
    written: `series` must be a list of objects and `descriptor` must be an object."
    Two field classes named, neither of them the one that was refused — and the same
    text came back for `descriptor_label`.

    The refusal was widened to new key classes without the sentence being touched, so its
    honesty depended on the ONE client that reads the `error` code and writes its own
    copy. Every other consumer — curl, the generated OpenAPI, the Assistant — was handed
    the false text. `key`/`keys` already say which field was refused; the prose says only
    what is true of all of them.
    """
    rid = "01SYNTHXANESSEED0000000003"
    uri = _stored_asset_uri(client, rid)
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]

    res = client.post(
        f"/api/experiments/{rid}/edit",
        json={"confirmed_by_user": True, "answers": {uri: "not-a-hash"}},
        headers={"If-Match": etag},
    )

    assert res.status_code == 422, res.text
    body = res.json()
    assert body["error"] == "invalid_field_value"
    assert body["key"] == uri and body["keys"] == [uri]
    message = body["message"]
    # The offending key is an asset uri. The message may not name a DIFFERENT key class.
    assert "series" not in message, message
    assert "descriptor" not in message, message
    # It must still say the two things that are true and that a reader needs.
    assert "nothing was written" in message.lower()
    assert "unchanged" in message.lower()


def test_a_still_pending_asset_uri_is_not_an_editable_field_on_the_edit_path(client):
    """A WELL-FORMED HASH FOR A PENDING ASSET WAS ANSWERED 200 WITH NOTHING STORED.

    The same defect class as the malformed-hash one above, on the same route and the same
    key, and reachable with a value that is beyond reproach. Measured before this fix:

        POST /edit {"<a still-pending asset uri>": "9" * 64}
        -> 200 · rev 0 -> 0 · stored sha256 None
        -> invalidation.reason "No change — the submitted value was identical;
                                nothing was invalidated."

    The value was not identical. It was never stored. `apply_corrections` iterates
    `draft["assets"]`, and a pending asset is by construction not in it — `apply_answers`
    is what creates the asset entry from the blocker — so the correction path could never
    have written it.

    `unrecognized_field`, deliberately, and NOT `invalid_field_value`: the value was
    fine. The dedicated client notice for `invalid_field_value` says "this field still
    holds the value it held before", which would be a third false claim about a field
    that holds no value yet. The generic notice claims less, and less is what is known.
    """
    rid = "01SYNTHXANESSEED0000000001"
    uri = _asset_uri(client, rid)
    assert uri not in [
        a["uri"] for a in (tutorial_ws().load_experiment(rid).draft.get("assets") or [])
    ], "this test needs a uri that is pending and NOT already stored"
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    rev_before = client.get(f"/api/experiments/{rid}").json()["rev"]

    res = client.post(
        f"/api/experiments/{rid}/edit",
        json={"confirmed_by_user": True, "answers": {uri: "9" * 64}},
        headers={"If-Match": etag},
    )

    assert res.status_code == 422, res.text
    assert res.json()["error"] == "unrecognized_field"
    # Nothing written, nothing invented, and no 200 asserting a cause.
    assert client.get(f"/api/experiments/{rid}").json()["rev"] == rev_before
    after = tutorial_ws().load_experiment(rid).draft
    assert (after.get("assets") or []) == []
    assert "9" * 64 not in json.dumps(after)


def test_the_same_pending_uri_is_still_accepted_by_the_answers_path(client):
    """THE OTHER DIRECTION, so the refusal above cannot have been a blanket narrowing.

    `POST /answers` is SUPPOSED to accept a still-pending asset uri — that is the fill
    path, and it is the only path that can materialise the asset at all. The `edit_only`
    narrowing must not touch it. Same record, same uri, same hash as the test above.
    """
    rid = "01SYNTHXANESSEED0000000001"
    uri = _asset_uri(client, rid)
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]

    res = client.post(
        f"/api/experiments/{rid}/answers",
        json={"confirmed_by_user": True, "answers": {uri: "9" * 64}},
        headers={"If-Match": etag},
    )

    assert res.status_code == 200, res.text
    after = tutorial_ws().load_experiment(rid).draft
    stored = {a["uri"]: a["sha256"] for a in (after.get("assets") or [])}
    assert stored.get(uri) == "9" * 64, "the answers path must still fill a pending asset"
    assert uri not in _pending_kinds(client, rid), "the blocker must be resolved, not left open"
    assert res.json()["invalidation"]["changed_fields"] == [uri]


def test_changed_fields_names_only_what_the_apply_shape_carried(client):
    """A KEY THE ROUTE DROPPED WAS REPORTED BACK AS AN UPDATED FIELD.

    `changed_fields` was `submitted_fields` — every non-blank REQUEST-BODY key — so a
    ride-along key was not merely ignored, it was ASSERTED. Measured before the fix:

        POST /edit {"<a stored asset uri>": "9" * 64,
                    "totally_made_up_field": "invented"}
        -> 200 · changed_fields ["<uri>", "totally_made_up_field"]
        -> reason "Updated 2 field(s); no downstream steps reopened."

    and `totally_made_up_field` appears nowhere in the stored draft.

    **`qc` USED TO BE THE SECOND EXAMPLE HERE, and it no longer is — because the
    defect it illustrated was fixed at the SOURCE rather than at the report.** The old
    text read: *"`qc` behaved the same way and is worse, because it is a real field
    name: `apply_corrections` handles it, `_answers_to_apply_shape` does not forward
    it, so it was reported as updated while `draft["qc"]["status"]` never moved."*
    That was true. The route now forwards `qc`, so it is reported as updated AND the
    value moves. This test therefore asserts the STRONGER thing: `qc` appears in
    `changed_fields` only alongside proof that the stored verdict really changed.
    Deleting the `qc` case instead would have removed the only coverage of the field
    that motivated the fix.


    This is the counter-argument to this whole slice being over-strict. The slice's
    premise is that answering 200 to a request that changed nothing is silent; a
    ride-along key is worse than silent, because the response makes a claim.
    """
    rid = "01SYNTHXANESSEED0000000003"
    uri = _stored_asset_uri(client, rid)
    qc_before = (tutorial_ws().load_experiment(rid).draft.get("qc") or {}).get("status")
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]

    res = client.post(
        f"/api/experiments/{rid}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {
                uri: "9" * 64,
                "totally_made_up_field": "invented",
                "qc": {"status": "failed"},
            },
        },
        headers={"If-Match": etag},
    )

    assert res.status_code == 200, res.text
    inv = res.json()["invalidation"]
    assert inv["changed"] is True
    assert inv["changed_fields"] == [uri, "qc"], inv["changed_fields"]
    assert "Updated 2 field(s)" in inv["reason"], inv["reason"]

    after = tutorial_ws().load_experiment(rid).draft
    assert "totally_made_up_field" not in json.dumps(after)
    assert "invented" not in json.dumps(after)
    # The ride-along key is still asserted about nowhere. `qc` is reported ONLY
    # because the stored verdict really moved — the claim and the write are checked
    # together, so a regression that reports it without storing it fails here.
    assert (after.get("qc") or {}).get("status") == "failed"
    assert qc_before != "failed", "fixture no longer exercises a CHANGE of verdict"


def test_a_wellformed_asset_sha_still_applies_and_re_sending_it_is_a_no_op(client):
    """THE OTHER HALF, so the refusal above cannot be satisfied by refusing everything.

    A well-formed hash is applied and advances `rev`. Re-sending the SAME hash answers
    200 with `rev` unmoved — and that 200 is CORRECT, not the defect above: the value
    was storable, and the byte-stable no-op is documented behaviour. The distinction the
    fix draws is between "unchanged because equal" and "unchanged because unusable".
    """
    rid = "01SYNTHXANESSEED0000000001"
    uri = _asset_uri(client, rid)

    # Fill it through the answers path first, so `/edit` is genuinely a correction.
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    filled = client.post(
        f"/api/experiments/{rid}/answers",
        json={"confirmed_by_user": True, "answers": {uri: "3" * 64}},
        headers={"If-Match": etag},
    )
    assert filled.status_code == 200, filled.text
    after_fill = client.get(f"/api/experiments/{rid}").json()["rev"]

    # A different well-formed hash applies.
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    corrected = client.post(
        f"/api/experiments/{rid}/edit",
        json={"confirmed_by_user": True, "answers": {uri: "7" * 64}},
        headers={"If-Match": etag},
    )
    assert corrected.status_code == 200, corrected.text
    advanced = client.get(f"/api/experiments/{rid}").json()["rev"]
    assert advanced > after_fill, "a real correction must advance the revision"

    # The same hash again is a no-op, and stays a 200.
    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    again = client.post(
        f"/api/experiments/{rid}/edit",
        json={"confirmed_by_user": True, "answers": {uri: "7" * 64}},
        headers={"If-Match": etag},
    )
    assert again.status_code == 200, again.text
    assert client.get(f"/api/experiments/{rid}").json()["rev"] == advanced


def test_the_answers_path_is_deliberately_unchanged_by_the_sha_guard(client):
    """`POST /answers` still leaves the blocker OPEN for a malformed sha.

    It does not borrow `/edit`'s typed refusal, and that asymmetry is the design: there
    the response already tells the caller the question was not answered, so nothing is
    silent. Pinned here because the fix above touches the shared predicate.
    """
    rid = "01SYNTHXANESSEED0000000001"
    uri = _asset_uri(client, rid)
    before = _pending_kinds(client, rid)

    etag = client.get(f"/api/experiments/{rid}").headers["ETag"]
    res = client.post(
        f"/api/experiments/{rid}/answers",
        json={"confirmed_by_user": True, "answers": {uri: "Z" * 64}},
        headers={"If-Match": etag},
    )

    assert res.status_code == 200, res.text
    assert uri in _pending_kinds(client, rid), "a malformed sha must leave the blocker open"
    assert _pending_kinds(client, rid) == before


# ---------------------------------------------------------------------------
# Correcting a question nobody has answered
# ---------------------------------------------------------------------------
#
# THE DEFECT, MEASURED OVER MCP BY AN INDEPENDENT REVIEW BEFORE THIS EXISTED.
# `/edit` admitted `series`, `descriptor` and `qc` unconditionally, while
# `apply_corrections` deliberately never touches `pending`. So:
#
#     POST /edit {"series": [...]}   ->  200, changed_fields: ["series"]
#     GET  /pending                  ->  "series" STILL OPEN
#
# The value was written with a fresh `user_confirmation` and the question the
# scientist was looking at did not move — a 200 about a write that resolved nothing.
# Worse, the MCP tool description GUARANTEED it could not happen ("correcting a field
# nothing has answered is refused"), so a model was told the call had been declined
# while it had in fact half-succeeded.
#
# These tests were also the reason the setup above had to change: every wrong-type
# case reached its "already confirmed" state THROUGH THIS DEFECT.


def test_correcting_a_question_nobody_has_answered_is_refused(client):
    open_kinds = {
        e["kind"] for e in client.get(f"/api/experiments/{PARTIAL}/pending").json()["pending"]
    }
    assert {"series", "descriptor"} <= open_kinds, open_kinds

    etag = client.get(f"/api/experiments/{PARTIAL}").headers["ETag"]
    res = client.post(
        f"/api/experiments/{PARTIAL}/edit",
        json={"confirmed_by_user": True, "answers": {"series": _valid_series()}},
        headers={"If-Match": etag},
    )
    assert res.status_code == 422, res.text
    body = res.json()
    # A TYPED REFUSAL NAMING THE STATE, not `unrecognized_field`. The field IS
    # recognised; only its state is wrong, and telling a scientist otherwise sends
    # them looking for a misspelling that is not there.
    assert body["error"] == "not_yet_answered"
    assert body["keys"] == ["series"]
    assert "answers" in body["answer_at"]

    # NOTHING WAS WRITTEN, and the question is exactly as open as it was.
    assert _draft(client).get("series") in (None, [], {})
    after = {
        e["kind"] for e in client.get(f"/api/experiments/{PARTIAL}/pending").json()["pending"]
    }
    assert after == open_kinds


def test_the_refusal_names_EVERY_offending_key_not_the_first(client):
    etag = client.get(f"/api/experiments/{PARTIAL}").headers["ETag"]
    res = client.post(
        f"/api/experiments/{PARTIAL}/edit",
        json={
            "confirmed_by_user": True,
            "answers": {"series": _valid_series(), "descriptor": _valid_descriptor()},
        },
        headers={"If-Match": etag},
    )
    assert res.status_code == 422, res.text
    assert res.json()["keys"] == ["descriptor", "series"]


def test_the_SAME_correction_is_accepted_once_the_question_is_answered(client):
    """THE NEGATIVE CONTROL, and it is the load-bearing half.

    A refusal that also refuses the legitimate case is not a fix. Byte-identical body,
    byte-identical route — the only thing that changed is that the question has been
    answered.
    """
    _answer_the_open_questions(client)
    etag = client.get(f"/api/experiments/{PARTIAL}").headers["ETag"]
    res = client.post(
        f"/api/experiments/{PARTIAL}/edit",
        json={"confirmed_by_user": True, "answers": {"series": _valid_series()}},
        headers={"If-Match": etag},
    )
    assert res.status_code == 200, res.text


def test_edge_is_not_refused_because_it_is_never_an_open_QUESTION(client):
    """`edge` corresponds to no blocker, so "unanswered" is not a state it can be in.

    Named explicitly because a rule written over "keys that appear in `pending`" would
    have swept it in by accident, and `edge` is answerable on the record BY DESIGN —
    it lives in the implicit derivations every non-diverging run inherits.
    """
    etag = client.get(f"/api/experiments/{PARTIAL}").headers["ETag"]
    res = client.post(
        f"/api/experiments/{PARTIAL}/edit",
        json={"confirmed_by_user": True, "answers": {"edge": "K"}},
        headers={"If-Match": etag},
    )
    assert res.status_code == 200, res.text

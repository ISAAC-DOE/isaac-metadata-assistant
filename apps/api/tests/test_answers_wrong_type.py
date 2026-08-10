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

import pytest
from fastapi.testclient import TestClient

from isaac_api.app import create_app

from conftest import tutorial_client

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
    etag = client.get(f"/api/experiments/{PARTIAL}").headers["ETag"]
    ok = client.post(
        f"/api/experiments/{PARTIAL}/edit",
        json={"confirmed_by_user": True, "answers": {"series": _valid_series()}},
        headers={"If-Match": etag},
    )
    assert ok.status_code == 200, ok.text
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

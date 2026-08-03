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

import pytest
from fastapi.testclient import TestClient

from isaac_api.app import create_app

PARTIAL = "01SYNTHXANESSEED0000000002"


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    # PER-TEST WORKSPACE, following the convention in test_reset.py. Without it these
    # tests share one workspace: the "correctly-typed series answer applies" test
    # answers a blocker, and every later test then reads a record whose pending set has
    # changed. That showed up while running a negative control — tests that should have
    # been unaffected failed, which reads like a broken fix rather than a dirty fixture.
    monkeypatch.setenv('ISAAC_UI_WORKSPACE', str(tmp_path / 'ws'))
    return TestClient(create_app())


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

"""P27.5-strict — mandatory If-Match preconditions (grace retired).

TEST-FIRST acceptance contract (authored BEFORE the strict flip; RED until
`version_contract.precondition_required()` returns True and the handlers reject a
missing If-Match with 428). The deployed frontend has been hosted-verified to send
`If-Match` on every mutation, so the one-release compatibility grace is now retired:

  * matching If-Match  -> 200 (proceeds)
  * stale If-Match     -> 412 Precondition Failed (unchanged, no mutation)
  * MISSING If-Match   -> 428 Precondition Required (NEW — was 200 under the grace)
  * malformed / weak   -> 400 (unchanged)
  * existing export 409 immutability preserved for a CURRENT client
  * NO deprecation header anywhere (the grace signal is gone)
  * a missing/stale precondition performs NO mutation

Applies to the two version-protected scientific-record mutations
(`POST /answers`, `POST /export`). Reset/demo/validate/audit are NOT version-gated.
All fixtures synthetic; truth core untouched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

from conftest import tutorial_client, tutorial_ws


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _real_answers_payload():
    answers = ws.load_demo_answers()
    return {
        "confirmed_by_user": True,
        "answers": {"series": answers.get("series"), "descriptor": answers.get("descriptor")},
    }


def _version(client, exp_id):
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    return r.json()["version"]


def _im(client, exp_id):
    return {"If-Match": f'"{_version(client, exp_id)}"'}


# --- the grace is retired: the single toggle is now ON ------------------------


def test_precondition_is_now_required():
    from isaac_api import version_contract as vc

    assert vc.precondition_required() is True


# --- MISSING If-Match -> 428 (the core strict behavior) -----------------------


def test_missing_if_match_on_answers_returns_428(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload()
    )
    assert r.status_code == 428, r.text
    body = r.json()
    assert body["error"] == "precondition_required"
    assert body["experiment_id"] == ws.SEED_NEW_DRAFT_ID


def test_missing_if_match_on_export_returns_428(client):
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export")
    assert r.status_code == 428, r.text
    assert r.json()["error"] == "precondition_required"


def test_missing_if_match_performs_no_mutation(client):
    before = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload()
    )
    assert r.status_code == 428
    after = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    assert after["version"] == before["version"], "a 428 must not have mutated the record"


def test_missing_export_precondition_writes_no_record(client):
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export")
    assert r.status_code == 428
    assert tutorial_ws().load_experiment(ws.SEED_READY_ID).exported() is False


# --- matching still succeeds; stale/malformed unchanged -----------------------


def test_matching_if_match_still_succeeds(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers=_im(client, ws.SEED_NEW_DRAFT_ID),
    )
    assert r.status_code == 200, r.text


def test_stale_if_match_still_412(client):
    im = _im(client, ws.SEED_NEW_DRAFT_ID)
    client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload(), headers=im
    )
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers", json=_real_answers_payload(), headers=im
    )
    assert r.status_code == 412, r.text
    assert r.json()["error"] == "stale_write"


def test_malformed_if_match_still_400(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": "garbage"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "malformed_if_match"


def test_wildcard_if_match_still_matches_existing(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": "*"},
    )
    assert r.status_code == 200, r.text


def test_the_contract_DISCLOSES_that_the_wildcard_skips_the_revision_comparison(client):
    """THE TWO STATEMENTS MUST AGREE, and for a long time they did not.

    The test above pins that `If-Match: *` is ACCEPTED — deliberately, because RFC
    9110 defines it as "if the resource exists" and this application implements that
    (`_check_if_match` returns `None` for `*` without comparing anything). Meanwhile
    the published `428` description read:

        "Every write requires the record's current `ETag`, so a blind overwrite is
         not possible."

    Two independent audits rated that HIGH, and they were right: `*` IS a blind
    overwrite. A caller that has never read the record — or the RUN — can send three
    bytes and overwrite it, and the machine-readable contract said that could not
    happen. An agent reading it would not defend against a client that sends `*`.

    THE BEHAVIOUR IS NOT CHANGED HERE. It is tested above and it is what the RFC
    says; reversing a tested decision is not this test's business. What is fixed is
    that the contract now says so. This pins the agreement in both directions, so
    neither side can drift back alone.
    """
    described = client.get("/api/openapi").json()["paths"][
        "/api/experiments/{experiment_id}/answers"
    ]["post"]["responses"]["428"]["description"]
    flat = " ".join(described.split())
    # It names the exception, names what `*` means, and says the write SUCCEEDS.
    assert "`If-Match: *` is accepted" in flat
    assert "if the resource exists" in flat
    assert "has never read" in flat
    # NEGATIVE CONTROL: the retired sentence must not return. It is the exact
    # sentence a well-meaning copy edit would restore.
    assert "a blind overwrite is not possible" not in flat.replace(
        '"a blind overwrite is not possible"', ""
    )


def test_the_wildcard_writes_a_RUN_the_caller_never_read(client):
    """The half that is more surprising than the record-level one, measured.

    `_apply_to_run`'s own docstring says a per-run validator exists so that "a
    client holding the RECORD's token cannot use it here, which is deliberate: it
    would let a caller write a run it never read." `*` lets exactly that — it is
    neither the record's token nor the run's, and it is accepted.

    Asserted so the disclosure above is grounded in a measurement rather than in
    reading `_check_if_match`, and so that a future change to the run path cannot
    quietly diverge from the record path here.
    """
    # A SEED RECORD, because this fixture is a worked-example client and
    # `POST /api/experiments` is refused in that scope. The wildcard question is
    # about the precondition, not about how the record came to exist.
    eid = ws.SEED_NEW_DRAFT_ID
    run = client.post(
        f"/api/experiments/{eid}/runs",
        json={"label": "R1"},
        # NEVER READ THE RECORD. No GET precedes this, and no ETag is held.
        headers={"If-Match": "*"},
    )
    assert run.status_code in {200, 201}, run.text
    rid = run.json()["run"]["id"]
    written = client.patch(
        f"/api/experiments/{eid}/runs/{rid}",
        json={"confirmed_by_user": True, "fields": {"context.temperature_K": 301.0}},
        headers={"If-Match": "*"},
    )
    assert written.status_code == 200, written.text
    reread = client.get(f"/api/experiments/{eid}/runs/{rid}").json()["run"]
    assert reread["fields"]["context.temperature_K"]["value"] == 301.0


# --- 428 must precede the 422 confirmation gate? NO: shape(422) precedes -------
# (documented ordering: request-shape validation precedes precondition). A missing
# body confirmation is still 422 regardless of If-Match. We assert the mandate order.


def test_unconfirmed_answers_still_422_even_without_if_match(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json={"confirmed_by_user": False, "answers": {}},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "confirmation_required"


# --- current client still hits the 409 immutability guard ---------------------


def test_current_client_still_409_on_already_exported(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_DONE_ID}/export", headers=_im(client, ws.SEED_DONE_ID)
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "record_exists"


def test_missing_if_match_on_exported_record_is_428_not_409(client):
    """Ordering guard: precondition precedes the export-domain conflict. A MISSING
    If-Match on an ALREADY-exported record must return 428 (refresh first), NOT the
    409 immutability response — a version-less client must refresh before it can
    make any current-state decision."""
    r = client.post(f"/api/experiments/{ws.SEED_DONE_ID}/export")  # no If-Match
    assert r.status_code == 428, r.text
    assert r.json()["error"] == "precondition_required"


# --- no deprecation header survives the grace removal -------------------------


def test_no_deprecation_header_on_successful_mutation(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers=_im(client, ws.SEED_NEW_DRAFT_ID),
    )
    assert r.status_code == 200
    assert not r.headers.get("X-ISAAC-Deprecation"), "grace signal must be gone in strict mode"


# --- the strong-validator pattern is exact by construction --------------------


def test_the_strong_validator_pattern_carries_its_exactness_in_the_pattern():
    """`_STRONG_TAG_RE` was `^"[^"\\]+"$` applied with `.match()`, and Python's `$`
    also matches immediately before a trailing newline — so `'"abc"\n'` was accepted
    as a well-formed strong validator.

    STATED HONESTLY: that was NOT reachable over HTTP. An ASGI server will not deliver
    a header value containing LF, and both call sites feed this `part.strip()`, which
    removes the newline before the pattern sees it — so this test is a unit test of the
    constant, not an end-to-end regression, and there is no HTTP case to add. The
    pattern is anchored anyway so that a third caller reading a validator from anywhere
    other than a header cannot reopen the hole; that is the same decision
    `draft_validator._SHA256_RE` and `format_shadow._RFC3339_SHAPE` took.

    The `.match`/`.fullmatch` agreement is the property being pinned. Note the ONE
    thing this does NOT change and never claimed to: `[^"\\]` still admits an embedded
    newline INSIDE the quotes, so `'"a\nb"'` matches before and after. That is a
    separate question about the character class, deliberately left alone.
    """
    from isaac_api.routes import _STRONG_TAG_RE

    # Anchors, not the `^` of the negated class `[^"\\]` — hence startswith/endswith
    # rather than a substring test, which the class's own `^` would have defeated.
    assert _STRONG_TAG_RE.pattern.startswith("\\A")
    assert _STRONG_TAG_RE.pattern.endswith("\\Z")
    assert "$" not in _STRONG_TAG_RE.pattern

    assert _STRONG_TAG_RE.match('"abc"'), "a legitimate strong validator must still pass"
    assert _STRONG_TAG_RE.match('"1.7"'), "the real token shape must still pass"

    for label, bad in (
        ("trailing LF — the regression", '"abc"\n'),
        ("trailing CR", '"abc"\r'),
        ("trailing space", '"abc" '),
        ("trailing junk", '"abc"x'),
        ("leading LF", '\n"abc"'),
        ("leading space", ' "abc"'),
        ("weak validator", 'W/"abc"'),
        ("unquoted", "abc"),
        ("empty token", '""'),
    ):
        assert _STRONG_TAG_RE.match(bad) is None, f"{label} accepted: {bad!r}"

    for candidate in ('"abc"', '"abc"\n', '\n"abc"', "abc", '""', ""):
        assert (_STRONG_TAG_RE.match(candidate) is not None) == (
            _STRONG_TAG_RE.fullmatch(candidate) is not None
        ), repr(candidate)

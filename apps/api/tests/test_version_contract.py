"""P27.3 — Backend version contract: ETag / If-Match / 412 stale-write, ABA-safe.

TEST-FIRST acceptance contract (authored BEFORE implementation; RED until the
generation-nonce token, the ETag/If-Match HTTP contract, the per-record mutation
lock, and the CORS ``expose_headers=["ETag"]`` land).

This slice builds ON the P27.2 rev model (``test_versioning.py``) — it does NOT
duplicate it. P27.2 proved the *persistence* layer (``rev``/``updated_utc``,
atomic writes, byte-stable no-op). P27.3 adds the *HTTP concurrency contract*.

Contract pinned here
--------------------
Token (ABA-safe): every experiment carries a durable opaque ``generation`` nonce
(minted at genuine (re)instantiation, PRESERVED across saves / loads / no-op
re-entries) plus the monotonic ``rev``. The public concurrency token is
``version_token() == f"{generation}.{rev}"``; the HTTP ETag is that value as a
strong quoted validator: ``ETag: "<generation>.<rev>"``. ``generation`` is random
(``secrets.token_hex``), so a record that is deleted-and-recreated (or replaced)
gets a NEW generation and every pre-lifecycle token stops matching — defeating the
rev-0→rev-0 ABA. ``_authoritative_signature`` still EXCLUDES generation/rev (they
are version metadata), so a byte-stable no-op never churns the token.

Response bodies of mutation-capable reads (detail/draft/pending) and successful
mutations expose ``rev`` (int), ``updated_utc`` (str), ``version`` (str = the
unquoted token) AND set the strong ``ETag`` header. The frontend echoes the
authoritative token; it never reconstructs one.

If-Match on the two scientific-record mutations (``/answers``, ``/export``):
  * absent           -> ACCEPTED in P27.3 (one-release compatibility grace) with a
                        non-noisy server deprecation header; becomes 428 in the
                        later strict slice.
  * ``*``            -> matches iff the record exists (it does) -> proceed.
  * strong match     -> proceed.
  * strong mismatch  -> 412 stale_write (typed body; current ETag echoed).
  * weak ``W/"..."`` -> 400 (weak validators are NOT supported for mutations —
                        documented restriction; strong comparison per RFC 9110).
  * malformed        -> 400 (distinct from missing).
  * multi-tag list   -> proceed iff ANY listed strong tag matches, else 412.

Conflict ordering: auth -> shape -> 404 -> precondition(400/412) -> scientific ->
export-domain 409 -> mutate. A stale client gets 412 BEFORE the export 409, so it
refreshes before making a current-state decision.

Race safety: ``ws.record_lock(id)`` serializes the load->compare->mutate->save
critical section (single-process uvicorn threadpool is the deployed model), so two
writers holding the same token cannot both succeed — exactly one wins, the loser
is stale, and ``rev`` advances exactly once.

All fixtures are synthetic. The truth core is never bypassed. No secret, no
filesystem path, and no raw record content ever appears in a token or error body.
"""

from __future__ import annotations

import concurrent.futures
import copy
import json
import re
import threading

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws

# strong ETag: a double-quoted opaque token, no W/ prefix.
_STRONG_ETAG_RE = re.compile(r'^"[^"\\]+"$')
# the token payload we mint: <generation>.<rev>, generation = lowercase hex.
_TOKEN_RE = re.compile(r"^[0-9a-f]+\.\d+$")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


@pytest.fixture()
def tmp_ws(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return ws


def _fresh_draft():
    return ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH)


def _real_answers_payload():
    """A payload that genuinely changes the raw NEW-DRAFT seed's authoritative draft."""
    answers = ws.load_demo_answers()
    return {
        "confirmed_by_user": True,
        "answers": {"series": answers.get("series"), "descriptor": answers.get("descriptor")},
    }


def _detail(client, exp_id):
    r = client.get(f"/api/experiments/{exp_id}")
    assert r.status_code == 200, r.text
    return r


def _token_of(client, exp_id):
    return _detail(client, exp_id).json()["version"]


def _quote(token: str) -> str:
    return f'"{token}"'


# =============================================================================
# 1. Version exposure — body fields + strong ETag header
# =============================================================================


def test_detail_body_carries_rev_updated_utc_and_version(client):
    body = _detail(client, ws.SEED_NEW_DRAFT_ID).json()
    assert isinstance(body["rev"], int)
    assert isinstance(body["updated_utc"], str) and body["updated_utc"]
    assert _TOKEN_RE.match(body["version"]), body["version"]


def test_detail_sets_strong_etag_header_matching_version(client):
    r = _detail(client, ws.SEED_NEW_DRAFT_ID)
    etag = r.headers.get("ETag")
    assert etag is not None, "record detail must carry an ETag"
    assert _STRONG_ETAG_RE.match(etag), f"ETag must be a strong quoted validator, got {etag!r}"
    assert not etag.startswith("W/"), "ETag must be strong, not weak"
    # header and body agree on the authoritative token
    assert etag == _quote(r.json()["version"])


@pytest.mark.parametrize("suffix", ["", "/draft", "/pending"])
def test_mutation_capable_reads_all_expose_etag(client, suffix):
    r = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}{suffix}")
    assert r.status_code == 200, r.text
    assert r.headers.get("ETag"), f"GET {suffix or '(detail)'} must expose an ETag"


def test_same_version_returns_same_etag(client):
    a = _detail(client, ws.SEED_READY_ID).headers["ETag"]
    b = _detail(client, ws.SEED_READY_ID).headers["ETag"]
    assert a == b


def test_accepted_mutation_changes_etag(client):
    before = _detail(client, ws.SEED_NEW_DRAFT_ID).headers["ETag"]
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": before},
    )
    assert r.status_code == 200, r.text
    after = _detail(client, ws.SEED_NEW_DRAFT_ID).headers["ETag"]
    assert after != before, "an accepted authoritative mutation must change the ETag"


def test_token_contains_no_secret_path_or_content(client):
    body = _detail(client, ws.SEED_READY_ID).json()
    token = body["version"]
    lowered = token.lower()
    for forbidden in ("/", "\\", "tmp", "workspace", "key", "cuo", "xanes", "sha256"):
        assert forbidden not in lowered, f"token leaked {forbidden!r}: {token!r}"


# =============================================================================
# 2. ABA / lifecycle — generation defeats rev-0 reuse
# =============================================================================


def test_recreation_changes_the_token_even_at_rev_zero(tmp_ws):
    """A deleted-and-recreated canonical record at rev 0 must NOT reuse its token."""
    tmp_ws.ensure_seeded()
    before = tmp_ws.load_experiment(tmp_ws.SEED_NEW_DRAFT_ID)
    assert before.rev == 0
    token_before = before.version_token()

    # simulate a lifecycle wipe of that one record, then reseed it
    import shutil

    shutil.rmtree(before.dir)
    tmp_ws.ensure_seeded()  # recreates the missing canonical id at rev 0

    after = tmp_ws.load_experiment(tmp_ws.SEED_NEW_DRAFT_ID)
    assert after.rev == 0, "recreated canonical is rev 0 (same integer as before)"
    assert after.version_token() != token_before, (
        "ABA: a rev-0 token from before recreation must not equal the rev-0 token after"
    )


def test_pre_reset_token_cannot_mutate_recreated_record(client):
    """End-to-end ABA guard through HTTP: a token captured before a lifecycle
    recreation is rejected 412 afterward, even though both are rev 0."""
    stale_token = _token_of(client, ws.SEED_NEW_DRAFT_ID)

    # wipe + let the next request reseed the missing canonical id at rev 0
    import shutil

    shutil.rmtree(ws.workspace_root() / ws.SEED_NEW_DRAFT_ID)

    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(stale_token)},
    )
    assert r.status_code == 412, r.text
    assert r.json()["error"] == "stale_write"


def test_noop_demo_run_does_not_churn_the_token(client):
    """Repeated idempotent demo runs (no authoritative change) must not churn the
    version token — the generation is preserved across an in-place upsert."""
    client.post("/api/demo/run", json={"mode": "full"})
    token1 = _token_of(client, ws.SEED_DONE_ID)
    client.post("/api/demo/run", json={"mode": "full"})
    token2 = _token_of(client, ws.SEED_DONE_ID)
    assert token1 == token2, "a no-op demo re-run must not churn the token"


def test_reset_preserves_untouched_canonical_token(client):
    """Reset leaves present canonical records untouched; their token stays valid
    because nothing about them changed (documented reset semantics)."""
    before = _token_of(client, ws.SEED_READY_ID)
    r = client.post("/api/demo/reset", json={"mode": "execute", "confirmation": "RESET SYNTHETIC DEMO"})
    assert r.status_code == 200, r.text
    after = _token_of(client, ws.SEED_READY_ID)
    assert before == after


# =============================================================================
# 3. Compatibility grace (P27.3) — missing If-Match accepted, signalled
# =============================================================================


def test_missing_if_match_is_accepted_during_grace(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
    )
    assert r.status_code == 200, "P27.3 temporarily accepts a version-less mutation"


def test_missing_if_match_carries_deprecation_signal(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
    )
    assert r.status_code == 200
    signal = r.headers.get("X-ISAAC-Deprecation", "")
    assert "if-match" in signal.lower(), (
        "a version-less mutation must carry a non-noisy deprecation signal header"
    )


def test_if_match_present_does_not_carry_deprecation_signal(client):
    token = _token_of(client, ws.SEED_NEW_DRAFT_ID)
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(token)},
    )
    assert r.status_code == 200
    assert not r.headers.get("X-ISAAC-Deprecation"), (
        "a properly-versioned mutation must NOT be flagged deprecated"
    )


# =============================================================================
# 4. If-Match parsing / comparison
# =============================================================================


def test_matching_if_match_succeeds(client):
    token = _token_of(client, ws.SEED_NEW_DRAFT_ID)
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(token)},
    )
    assert r.status_code == 200, r.text


def test_stale_if_match_returns_412_typed_body(client):
    token = _token_of(client, ws.SEED_NEW_DRAFT_ID)
    # first mutation advances the token
    ok = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(token)},
    )
    assert ok.status_code == 200
    # a second request replaying the ORIGINAL (now stale) token must be rejected
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(token)},
    )
    assert r.status_code == 412, r.text
    body = r.json()
    assert body["error"] == "stale_write"
    assert body["experiment_id"] == ws.SEED_NEW_DRAFT_ID
    assert "current_rev" in body and "expected_rev" in body
    assert "current_version" in body
    # the 412 echoes the CURRENT ETag so the client can refresh in one hop
    assert r.headers.get("ETag") == _quote(_token_of(client, ws.SEED_NEW_DRAFT_ID))


def test_wildcard_if_match_matches_existing_record(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": "*"},
    )
    assert r.status_code == 200, r.text


def test_weak_validator_is_rejected_400(client):
    token = _token_of(client, ws.SEED_NEW_DRAFT_ID)
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": f'W/{_quote(token)}'},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "malformed_if_match"


def test_malformed_if_match_is_400_not_412_or_428(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": "not-a-quoted-tag"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "malformed_if_match"


def test_multi_tag_if_match_succeeds_when_one_matches(client):
    token = _token_of(client, ws.SEED_NEW_DRAFT_ID)
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": f'"stale-aaa.0", {_quote(token)}'},
    )
    assert r.status_code == 200, r.text


def test_multi_tag_if_match_412_when_none_match(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": '"stale-aaa.0", "stale-bbb.1"'},
    )
    assert r.status_code == 412, r.text


# =============================================================================
# 5. Mutation safety — no mutation on stale; bump exactly once on match
# =============================================================================


def test_stale_answers_performs_no_mutation(client):
    token = _token_of(client, ws.SEED_NEW_DRAFT_ID)
    # advance once
    client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(token)},
    )
    detail_after_first = _detail(client, ws.SEED_NEW_DRAFT_ID).json()
    # replay the stale token -> 412 and NO further state change
    client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(token)},
    )
    detail_after_stale = _detail(client, ws.SEED_NEW_DRAFT_ID).json()
    assert detail_after_stale["rev"] == detail_after_first["rev"]
    assert detail_after_stale["version"] == detail_after_first["version"]


def test_matching_answers_bumps_rev_exactly_once(client):
    body0 = _detail(client, ws.SEED_NEW_DRAFT_ID).json()
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(body0["version"])},
    )
    assert r.status_code == 200
    body1 = _detail(client, ws.SEED_NEW_DRAFT_ID).json()
    assert body1["rev"] == body0["rev"] + 1


def test_stale_export_performs_no_export(client):
    """A stale If-Match on export must 412 AND leave the record un-exported."""
    # READY seed is exportable and NOT yet exported.
    token = _token_of(client, ws.SEED_READY_ID)
    # An out-of-band authoritative bump makes the client's token stale WITHOUT
    # exporting anything.
    exp = ws.load_experiment(ws.SEED_READY_ID)
    exp.title = exp.title + " (bumped out of band)"
    assert exp.save_versioned() is True
    assert exp.exported() is False
    # The stale export attempt must be rejected and must NOT export the record.
    r = client.post(
        f"/api/experiments/{ws.SEED_READY_ID}/export",
        headers={"If-Match": _quote(token)},
    )
    assert r.status_code == 412, r.text
    assert r.json()["error"] == "stale_write"
    assert ws.load_experiment(ws.SEED_READY_ID).exported() is False, (
        "a stale export must not have written a record"
    )


def test_stale_client_gets_412_before_export_409(client):
    """Ordering: a stale client hitting an already-exported record gets 412
    (refresh first), NOT the export-domain 409."""
    r = client.post(
        f"/api/experiments/{ws.SEED_DONE_ID}/export",
        headers={"If-Match": '"definitely-stale.0"'},
    )
    assert r.status_code == 412, "stale precondition must be evaluated before the 409"


def test_current_client_still_gets_409_on_already_exported(client):
    """A CURRENT client re-exporting an already-exported record still gets the
    existing immutability 409 — the version contract does not mask it."""
    token = _token_of(client, ws.SEED_DONE_ID)
    r = client.post(
        f"/api/experiments/{ws.SEED_DONE_ID}/export", headers={"If-Match": _quote(token)}
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "record_exists"


# =============================================================================
# 6. Concurrency — per-record lock + compare-and-swap (drive the write path
#    directly under threads; TestClient serialises HTTP so it cannot race)
# =============================================================================


def test_record_lock_serializes_compare_and_swap(tmp_ws):
    tmp_ws.ensure_seeded()
    exp_id = tmp_ws.SEED_NEW_DRAFT_ID
    token = tmp_ws.load_experiment(exp_id).version_token()

    start = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def writer(tag: str):
        start.wait()
        with tmp_ws.record_lock(exp_id):
            exp = tmp_ws.load_experiment(exp_id)
            if exp.version_token() != token:
                with lock:
                    outcomes.append("stale")
                return
            exp.title = exp.title + f"·{tag}"  # authoritative change
            exp.save_versioned()
            with lock:
                outcomes.append("ok")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(writer, ["A", "B"]))

    assert sorted(outcomes) == ["ok", "stale"], outcomes
    # rev advanced EXACTLY once past the starting rev
    final = tmp_ws.load_experiment(exp_id)
    assert final.rev == 1
    # the file is valid JSON (no partial/corrupt state)
    json.loads(final.state_path.read_text(encoding="utf-8"))


def test_two_writers_same_token_only_one_persists(tmp_ws):
    tmp_ws.ensure_seeded()
    exp_id = tmp_ws.SEED_PARTIAL_ID
    token = tmp_ws.load_experiment(exp_id).version_token()
    barrier = threading.Barrier(2)

    def mutate(new_title):
        barrier.wait()
        try:
            with tmp_ws.record_lock(exp_id):
                exp = tmp_ws.load_experiment(exp_id)
                if exp.version_token() != token:
                    return False
                exp.title = new_title
                return exp.save_versioned()
        except Exception:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(mutate, ["title-A", "title-B"]))

    assert results.count(True) == 1, results
    assert tmp_ws.load_experiment(exp_id).rev == 1


# =============================================================================
# 7. CORS — If-Match allowed, ETag exposed, no wildcard regression, preflight ok
# =============================================================================


def _cors_client(tmp_path, monkeypatch, origin="https://isaac-demo-web.vercel.app"):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_CORS_ORIGINS", origin)
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app()), origin


def test_cors_exposes_etag_header(tmp_path, monkeypatch):
    client, origin = _cors_client(tmp_path, monkeypatch)
    r = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}", headers={"Origin": origin})
    exposed = r.headers.get("access-control-expose-headers", "")
    assert "etag" in exposed.lower(), (
        f"ETag must be in Access-Control-Expose-Headers for cross-origin reads, got {exposed!r}"
    )


def test_cors_preflight_allows_if_match(tmp_path, monkeypatch):
    client, origin = _cors_client(tmp_path, monkeypatch)
    r = client.options(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "if-match,content-type",
        },
    )
    assert r.status_code in (200, 204), r.text
    allowed = r.headers.get("access-control-allow-headers", "").lower()
    # allow_headers=["*"] echoes requested headers; If-Match must be permitted
    assert "if-match" in allowed or allowed == "*"


def test_cors_denies_unapproved_origin(tmp_path, monkeypatch):
    client, _ = _cors_client(tmp_path, monkeypatch)
    r = client.get(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}",
        headers={"Origin": "https://evil.example.com"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


# =============================================================================
# 8. Endpoint-level guarantees (review hardening: T1/T2/T3, M3)
# =============================================================================


def test_answers_endpoint_reads_fresh_state_under_lock(client):
    """The mutation endpoint must load the record FRESH inside the lock and reject
    a token that an OUT-OF-BAND writer (not the HTTP layer) has since invalidated —
    proving the handler never trusts a stale client token against cached state."""
    token = _token_of(client, ws.SEED_NEW_DRAFT_ID)
    # advance the on-disk state directly, bypassing the HTTP endpoint entirely
    exp = ws.load_experiment(ws.SEED_NEW_DRAFT_ID)
    exp.title = exp.title + " (edited out of band)"
    assert exp.save_versioned() is True
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(token)},
    )
    assert r.status_code == 412, r.text
    assert r.json()["current_version"] == ws.load_experiment(ws.SEED_NEW_DRAFT_ID).version_token()


def test_no_deprecation_header_on_stale_412(client):
    token = _token_of(client, ws.SEED_NEW_DRAFT_ID)
    client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(token)},
    )
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": _quote(token)},
    )
    assert r.status_code == 412
    assert not r.headers.get("X-ISAAC-Deprecation"), "a stale 412 must not be flagged deprecated"


def test_no_deprecation_header_on_malformed_400(client):
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": "not-a-quoted-tag"},
    )
    assert r.status_code == 400
    assert not r.headers.get("X-ISAAC-Deprecation")


def test_export_grace_emits_deprecation_header(client):
    """The export path, like answers, must flag a version-less mutation during the
    P27.3 compatibility grace."""
    r = client.post(f"/api/experiments/{ws.SEED_READY_ID}/export")  # no If-Match
    assert r.status_code == 200, r.text
    assert "if-match" in r.headers.get("X-ISAAC-Deprecation", "").lower()


def test_if_match_tolerates_trailing_comma(client):
    """RFC 9110 #-list rule: recipients ignore empty list elements. A trailing
    comma must not be misread as a malformed header (M3)."""
    token = _token_of(client, ws.SEED_NEW_DRAFT_ID)
    r = client.post(
        f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/answers",
        json=_real_answers_payload(),
        headers={"If-Match": f"{_quote(token)},"},
    )
    assert r.status_code == 200, r.text

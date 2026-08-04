"""P26.1 — Workspace search core (pure, deterministic, no route, no LLM).

Behavior-level tests over the REAL canonical five-scenario seed. Every assertion is
derived from the public workspace surface (``ws.list_experiments()`` + the derived
``Experiment`` state), never a hand-authored fixture, so the contract stays honest
about actual product state.

The core under test is a PURE function:

    search.workspace_search(query, experiments, *, limit, offset) -> WorkspaceSearchResults

It reads ONLY already-exposed workspace content (experiment title/id, exported
record id, draft field path/label/value/status, pending field names/questions, draft
evidence source labels/locators/quotes, source-file references). It computes NO
verdict, imports NO truth-core validator, and performs NO filesystem traversal of its
own — it consumes the hardened ``list_experiments()`` snapshot, so a directory removed
by a concurrent reset can never make search raise (P26.0b read-race contract, §10).

Governance: results never surface absolute/filesystem/Railway paths, ``examples/**``,
secrets, or verdict keys/language.
"""

from __future__ import annotations

import dataclasses
import re
import shutil

import pytest

import isaac_api.search as search
import isaac_api.workspace as ws

from conftest import open_tutorial_scope, tutorial_client


# --- fixtures -----------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """An isolated worked-example session holding exactly the canonical five scenarios.

    Re-pointed from the normal workspace (which is no longer auto-seeded) to a
    worked-example session. The five records, their content, and every assertion
    below are unchanged; only the directory they live in is.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return open_tutorial_scope()


@pytest.fixture()
def experiments(workspace):
    exps = workspace.list_experiments()
    assert len(exps) == 5  # sanity: the P26.0a canonical seed
    return exps


# --- helpers ------------------------------------------------------------------


def run(query, experiments, **kw):
    return search.workspace_search(query, experiments, **kw)


def ids(results):
    return [r.experiment_id for r in results.results]


def id_set(results):
    return {r.experiment_id for r in results.results}


def kinds(results):
    return {r.kind for r in results.results}


def by_scenario(experiments):
    """Map the five canonical ids to their Experiment objects."""
    return {e.id: e for e in experiments}


def blob(results):
    """Fully serialize a result set for governance scans."""
    return repr(dataclasses.asdict(results))


# =============================================================================
# Normalization
# =============================================================================


def test_case_insensitive_title_match(experiments):
    lower = id_set(run("new draft", experiments))
    upper = id_set(run("NEW DRAFT", experiments))
    assert lower == upper
    assert ws.SEED_NEW_DRAFT_ID in lower


def test_unicode_nfc_normalization(experiments):
    # café decomposed (e + combining acute) vs precomposed é must normalize equal.
    decomposed = run("café", experiments)
    composed = run("café", experiments)
    assert decomposed.normalized_query == composed.normalized_query == "café"


def test_whitespace_collapsed(experiments):
    padded = run("  new    draft  ", experiments)
    assert padded.normalized_query == "new draft"
    assert id_set(padded) == id_set(run("new draft", experiments))


def test_single_char_query_is_too_short(experiments):
    r = run("n", experiments)
    assert r.reason == search.QUERY_TOO_SHORT
    assert r.total == 0
    assert r.results == () or list(r.results) == []


def test_empty_query_is_too_short(experiments):
    r = run("", experiments)
    assert r.reason == search.QUERY_TOO_SHORT
    assert r.total == 0


def test_whitespace_only_query_is_too_short(experiments):
    r = run("   ", experiments)
    assert r.reason == search.QUERY_TOO_SHORT
    assert r.total == 0


def test_two_char_query_is_allowed(experiments):
    r = run("cu", experiments)  # boundary: MIN_QUERY_LEN == 2
    assert r.reason is None
    assert r.total > 0


# =============================================================================
# Matching (one meaningful hit per kind)
# =============================================================================


def test_title_match(experiments):
    r = run("partially", experiments)
    assert ws.SEED_PARTIAL_ID in id_set(r)
    hit = next(x for x in r.results if x.experiment_id == ws.SEED_PARTIAL_ID)
    assert hit.kind == "experiment"


def test_experiment_id_match(experiments):
    r = run(ws.SEED_READY_ID, experiments)
    assert ws.SEED_READY_ID in id_set(r)
    assert any(
        x.kind == "experiment" and x.match.field == "id"
        for x in r.results
        if x.experiment_id == ws.SEED_READY_ID
    )


def test_record_id_match_only_for_exported(experiments):
    exp5 = by_scenario(experiments)[ws.SEED_DONE_ID]
    assert exp5.record_id  # the exported scenario has a record id
    r = run(exp5.record_id, experiments)
    record_hits = [x for x in r.results if x.kind == "record_id"]
    assert record_hits, "exported record id must produce a record_id result"
    assert all(x.experiment_id == ws.SEED_DONE_ID for x in record_hits)


def test_draft_field_value_match(experiments):
    # SSRL is a confirmed draft field value (system.facility.facility_name).
    r = run("ssrl", experiments)
    field_hits = [x for x in r.results if x.kind == "draft_field"]
    assert field_hits
    hit = field_hits[0]
    assert hit.match.field.startswith("draft.")
    assert "ssrl" in hit.match.snippet.lower()


def test_pending_field_match(experiments):
    # sha256 appears in pending blocker questions (New Draft has 5 pending).
    r = run("sha256", experiments)
    pending_hits = [
        x
        for x in r.results
        if x.kind == "draft_field" and "pending" in x.match.reason.lower()
    ]
    assert pending_hits
    assert any(x.experiment_id == ws.SEED_NEW_DRAFT_ID for x in pending_hits)


def test_evidence_match(experiments):
    # A committed synthetic source file basename appears in evidence entries.
    r = run("mock_campaign", experiments)
    assert any(x.kind == "evidence" for x in r.results)


def test_artifact_match_for_exported(experiments):
    r = run("exported record", experiments)
    artifact_hits = [x for x in r.results if x.kind == "artifact"]
    assert artifact_hits, "the exported scenario must surface an artifact lead"
    assert all(x.experiment_id == ws.SEED_DONE_ID for x in artifact_hits)


def test_source_ref_match(experiments):
    r = run("raw_scan_listing", experiments)
    assert any(x.kind == "source_ref" for x in r.results)


def test_no_match_returns_empty_but_valid(experiments):
    r = run("zzqqxxnope", experiments)
    assert r.reason is None
    assert r.total == 0
    assert list(r.results) == []


# =============================================================================
# Ranking (deterministic)
# =============================================================================


def test_exact_match_ranks_first(experiments):
    exp5 = by_scenario(experiments)[ws.SEED_DONE_ID]
    r = run(exp5.title, experiments)  # the full title == exact match on scenario 5
    assert r.results, "exact full-title query must return the matching experiment"
    assert r.results[0].experiment_id == ws.SEED_DONE_ID
    assert r.results[0].match.tier == "exact"


def test_tier_order_is_monotonic(experiments):
    # Across the whole result set, tiers never improve as you go down the list.
    order = {"exact": 0, "prefix": 1, "token": 2, "substring": 3}
    r = run("cu", experiments)
    tiers = [order[x.match.tier] for x in r.results]
    assert tiers == sorted(tiers)


def test_prefix_tie_broken_by_created_then_id(experiments):
    # Every canonical title starts with the shared base -> prefix tier on all five,
    # so the title results order by created_utc (example 1..5), then id.
    # The query must be a genuine PREFIX of that shared base, or this exercises the
    # substring tier instead of the prefix tier it is named for.
    r = run("xanes example", experiments, limit=search.MAX_RESULTS)
    title_ids = [
        x.experiment_id for x in r.results if x.kind == "experiment" and x.match.field == "title"
    ]
    expected = [
        ws.SEED_NEW_DRAFT_ID,
        ws.SEED_PARTIAL_ID,
        ws.SEED_READY_ID,
        ws.SEED_REVIEW_ID,
        ws.SEED_DONE_ID,
    ]
    assert title_ids == expected


def test_deterministic_repeated_query(experiments):
    a = run("cu k-edge", experiments, limit=search.MAX_RESULTS)
    b = run("cu k-edge", experiments, limit=search.MAX_RESULTS)
    key = lambda res: [(x.kind, x.experiment_id, x.match.field, x.match.tier) for x in res.results]
    assert key(a) == key(b)


def test_every_result_explains_why_it_matched(experiments):
    r = run("cu", experiments, limit=search.MAX_RESULTS)
    assert r.results
    for x in r.results:
        assert x.match.reason and x.match.reason.strip()
        assert x.match.tier in {"exact", "prefix", "token", "substring"}


# =============================================================================
# Pagination and caps
# =============================================================================


def test_default_limit_is_ten(experiments):
    r = run("cu", experiments)  # broad query -> many hits
    assert r.limit == search.DEFAULT_LIMIT == 10
    assert r.returned == min(r.total, 10)
    assert r.returned == len(r.results)


def test_explicit_limit(experiments):
    r = run("cu", experiments, limit=2)
    assert r.returned == min(r.total, 2)
    assert len(r.results) <= 2


def test_offset_pages_do_not_overlap(experiments):
    full = run("cu", experiments, limit=search.MAX_RESULTS)
    page1 = run("cu", experiments, limit=3, offset=0)
    page2 = run("cu", experiments, limit=3, offset=3)
    key = lambda res: [(x.kind, x.experiment_id, x.match.field) for x in res.results]
    assert set(key(page1)).isdisjoint(set(key(page2)))
    assert key(page1) + key(page2) == key(full)[:6]


def test_total_counts_all_matches(experiments):
    r = run("cu", experiments, limit=search.MAX_RESULTS)
    assert r.total == len(r.results)
    assert r.total <= search.MAX_RESULTS


def test_result_cap_50(experiments):
    # Clone one seeded experiment into >50 distinct experiments; the cap holds.
    base = experiments[0]
    many = []
    for i in range(60):
        clone = dataclasses.replace(base, id=f"{ws.SEED_NEW_DRAFT_ID[:-2]}{i:02d}")
        many.append(clone)
    r = run("synthetic", many, limit=search.MAX_RESULTS)
    assert r.total <= 50
    assert r.returned <= 50


def test_limit_clamped_above_cap(experiments):
    r = run("cu", experiments, limit=1000)
    assert r.returned <= search.MAX_RESULTS


def test_negative_offset_treated_as_zero(experiments):
    a = run("cu", experiments, offset=-5)
    b = run("cu", experiments, offset=0)
    assert ids(a) == ids(b)


def test_zero_limit_returns_no_rows_but_reports_total(experiments):
    r = run("cu", experiments, limit=0)
    assert r.returned == 0
    assert list(r.results) == []
    assert r.total > 0


# =============================================================================
# Five-scenario coverage
# =============================================================================


def test_each_scenario_distinguishable_by_title(experiments):
    # Scenario-specific title tokens isolate exactly one scenario each.
    assert id_set(run("new draft", experiments)) == {ws.SEED_NEW_DRAFT_ID}
    assert id_set(run("partially", experiments)) == {ws.SEED_PARTIAL_ID}
    assert id_set(run("ready", experiments)) == {ws.SEED_READY_ID}
    assert id_set(run("review", experiments)) == {ws.SEED_REVIEW_ID}
    assert id_set(run("exported", experiments)) == {ws.SEED_DONE_ID}


def test_shared_token_returns_multiple_scenarios(experiments):
    assert id_set(run("xanes", experiments, limit=search.MAX_RESULTS)) == {
        ws.SEED_NEW_DRAFT_ID,
        ws.SEED_PARTIAL_ID,
        ws.SEED_READY_ID,
        ws.SEED_REVIEW_ID,
        ws.SEED_DONE_ID,
    }


def test_result_status_matches_derived_status(experiments):
    scen = by_scenario(experiments)
    r = run("xanes example", experiments, limit=search.MAX_RESULTS)
    # Non-vacuity: a query that matches nothing would let the loop below pass
    # without checking a single status. (Before P1 renamed the seed titles this
    # query read "synthetic xanes"; the rename would otherwise have silently
    # emptied it.)
    assert r.results
    for x in r.results:
        assert x.status == scen[x.experiment_id].status()
    # spot-check the four derived states are all represented across the seed
    statuses = {scen[i].status() for i in scen}
    assert statuses == {ws.NEEDS_ATTENTION, ws.READY_TO_EXPORT, ws.IN_REVIEW, ws.DONE}


def test_navigation_targets_are_valid(experiments):
    valid_ids = {e.id for e in experiments}
    r = run("cu", experiments, limit=search.MAX_RESULTS)
    assert r.results
    for x in r.results:
        assert x.navigate_to.startswith(f"/record/{x.experiment_id}")
        assert x.experiment_id in valid_ids
        suffix = x.navigate_to[len(f"/record/{x.experiment_id}"):]
        assert suffix in ("", "/complete", "/evidence", "/export")


def test_plane_and_source_labels(experiments):
    r = run("cu", experiments, limit=search.MAX_RESULTS)
    assert r.results
    for x in r.results:
        assert x.plane == "truth"
        assert x.source == "workspace-store"
    assert search.PLANE == "truth"
    assert search.PROVIDER == "workspace-store"


# =============================================================================
# Governance / no-verdict / no-leak
# =============================================================================

_FORBIDDEN_KEYS = {"ok", "valid", "passed", "verdict", "schema", "schema_valid", "audit_passed", "errors"}


def test_no_verdict_keys_in_result_shape(experiments):
    r = run("cu", experiments, limit=search.MAX_RESULTS)
    d = dataclasses.asdict(r)

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k not in _FORBIDDEN_KEYS, f"forbidden verdict key: {k}"
                walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v)

    walk(d)


def test_no_verdict_language_in_server_text(experiments):
    r = run("cu", experiments, limit=search.MAX_RESULTS)
    verdict = re.compile(r"\b(pass|passed|fail|failed|valid|invalid)\b", re.IGNORECASE)
    for x in r.results:
        # server-authored text (never echoed data) must carry no verdict wording
        assert not verdict.search(x.match.reason)
        assert not verdict.search(x.match.tier)


def test_no_filesystem_paths_leak(experiments, workspace):
    r = run("cu", experiments, limit=search.MAX_RESULTS)
    text = blob(r)
    assert str(workspace) not in text
    assert "/tmp/" not in text
    assert "examples/" not in text
    assert ".evidence.json" not in text
    assert "/records/" not in text


def test_no_absolute_path_attributes(experiments):
    r = run("cu", experiments, limit=search.MAX_RESULTS)
    for x in r.results:
        # navigate_to is the ONLY leading-slash value permitted (a client route).
        for attr in (x.label, x.match.snippet, x.match.field, x.title):
            assert not attr.startswith("/"), f"unexpected leading-slash value: {attr!r}"


# =============================================================================
# Read-concurrency safety (P26.0b contract, §10) + pure-core boundary
# =============================================================================


def test_search_is_pure_over_snapshot_after_dirs_removed(experiments, workspace):
    """Search consumes the already-loaded snapshot; removing the backing dirs
    afterwards cannot make it raise or change its answer — it never re-reads disk."""
    before = ids(run("cu", experiments, limit=search.MAX_RESULTS))
    for child in workspace.workspace_root().iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    after = ids(run("cu", experiments, limit=search.MAX_RESULTS))
    assert before == after


def test_core_does_no_filesystem_traversal():
    """The core must not introduce its own directory walk (read-race contract):
    it operates on the injected experiments only."""
    src = (
        __import__("pathlib").Path(search.__file__).read_text(encoding="utf-8")
    )
    for banned in ("iterdir(", "listdir(", ".glob(", ".rglob(", "os.walk", "scandir("):
        assert banned not in src, f"search core must not traverse the filesystem: {banned}"


def test_core_imports_no_truth_core_validator():
    """search.py computes no verdict and imports no truth-core validation."""
    src = __import__("pathlib").Path(search.__file__).read_text(encoding="utf-8")
    for banned in (
        "validate_draft",
        "validate_official",
        "export_draft",
        "audit_records",
        "portal_warnings",
    ):
        assert banned not in src, f"search core must not import truth-core: {banned}"


# =============================================================================
# P26.3 — GET /api/search route (grouped, plane-labeled, no-verdict envelope)
# =============================================================================

from pathlib import Path as _Path

from fastapi.testclient import TestClient


def _repo_root() -> _Path:
    here = _Path(__file__).resolve()
    for cand in (here, *here.parents):
        if (cand / "schema" / "isaac_record_v1.json").exists():
            return cand
    return here.parents[3]


_GOLDEN_SNAPSHOT = _repo_root() / "tests" / "fixtures" / "memory_snapshot" / "memory-snapshot.json"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Seeded workspace; memory plane DETERMINISTICALLY degraded (graph_absent).

    Point ISAAC_MEMORY_SNAPSHOT at a guaranteed-nonexistent path so the reader
    resolves to a degraded snapshot source regardless of whether a real
    ``graphify-out/`` exists in the dev checkout — the memory-plane availability of
    these route tests must not depend on the developer's local graph (CI has none).
    A test that wants an available memory plane builds its own client (see
    ``test_route_memory_available_via_snapshot``)."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_MEMORY_DIR", raising=False)
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(tmp_path / "no-such-snapshot.json"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _walk_dict_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_dict_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_dict_keys(v)


def test_route_envelope_shape(client):
    r = client.get("/api/search", params={"q": "xanes"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"query", "normalized_query", "scope", "workspace", "memory"}
    assert body["scope"] == "all"
    ws_group = body["workspace"]
    assert ws_group["plane"] == "truth"
    assert ws_group["provider"] == "workspace-store"
    assert ws_group["available"] is True
    assert ws_group["total"] > 0
    assert {"total", "returned", "limit", "offset", "results"} <= set(ws_group)
    mem = body["memory"]
    assert mem["plane"] == "memory"
    assert mem["provider"].startswith("memory:")
    assert "note" in mem and mem["note"]
    assert isinstance(mem["available"], bool)


def test_route_workspace_returns_seeded_hits(client):
    body = client.get("/api/search", params={"q": "xanes"}).json()
    results = body["workspace"]["results"]
    assert results
    for row in results:
        assert row["kind"] in (
            "experiment", "record_id", "draft_field", "evidence", "artifact", "source_ref"
        )
        assert row["plane"] == "truth"
        assert row["navigate_to"].startswith("/record/")


def test_route_scope_workspace_omits_memory_results(client):
    body = client.get("/api/search", params={"q": "xanes", "scope": "workspace"}).json()
    assert body["scope"] == "workspace"
    assert body["workspace"]["results"]
    # memory group still present + availability reported, but no rows
    assert body["memory"]["results"] == []


def test_route_scope_memory_omits_workspace_results(client):
    body = client.get("/api/search", params={"q": "xanes", "scope": "memory"}).json()
    assert body["scope"] == "memory"
    assert body["workspace"]["results"] == []


def test_route_query_too_short(client):
    body = client.get("/api/search", params={"q": "a"}).json()
    assert body["workspace"]["reason"] == "query_too_short"
    assert body["workspace"]["total"] == 0
    assert body["memory"]["reason"] == "query_too_short"


def test_route_memory_unavailable_but_workspace_ok_is_200(client):
    # No memory graph configured -> memory plane degrades honestly, workspace still works,
    # and the response is a clean 200 (never a 5xx from a degraded provider).
    r = client.get("/api/search", params={"q": "xanes"})
    assert r.status_code == 200
    body = r.json()
    assert body["memory"]["available"] is False
    assert body["memory"]["reason"] in ("graph_absent", "graph_unreadable")
    assert body["workspace"]["available"] is True
    assert body["workspace"]["results"]


def test_route_memory_available_via_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_MEMORY_SNAPSHOT", str(_GOLDEN_SNAPSHOT))
    from isaac_api.app import create_app

    c = tutorial_client(create_app())
    body = c.get("/api/search", params={"q": "fake"}).json()
    assert body["memory"]["available"] is True
    assert body["memory"]["results"]
    for row in body["memory"]["results"]:
        assert row["plane"] == "memory"
        assert row["kind"] in ("concept", "file", "rationale")


def test_route_default_limit_and_pagination(client):
    body = client.get("/api/search", params={"q": "cu"}).json()
    assert body["workspace"]["limit"] == 10
    p1 = client.get("/api/search", params={"q": "cu", "limit": 2, "offset": 0}).json()
    assert len(p1["workspace"]["results"]) <= 2
    assert p1["workspace"]["limit"] == 2


def test_route_no_verdict_keys(client):
    body = client.get("/api/search", params={"q": "xanes"}).json()
    forbidden = {"ok", "valid", "passed", "verdict", "schema", "schema_valid", "audit_passed", "errors"}
    for k in _walk_dict_keys(body):
        assert k not in forbidden, f"verdict key in envelope: {k}"


def test_route_is_auth_gated(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    from isaac_api.app import create_app

    # Deliberately NOT the worked-example client: this test is about the auth gate,
    # and opening a session over HTTP would itself need the key. The gate applies
    # identically in either scope.
    c = TestClient(create_app())
    assert c.get("/api/search", params={"q": "xanes"}).status_code == 401
    ok = c.get("/api/search", params={"q": "xanes"}, headers={"Authorization": "Bearer demo-secret"})
    assert ok.status_code == 200


def test_route_group_returned_matches_len(client):
    body = client.get("/api/search", params={"q": "xanes"}).json()
    for grp in (body["workspace"], body["memory"]):
        assert grp["returned"] == len(grp["results"])


def test_route_limit_offset_forwarded(client):
    body = client.get("/api/search", params={"q": "cu", "limit": 2, "offset": 1}).json()
    assert body["workspace"]["limit"] == 2
    assert body["workspace"]["offset"] == 1
    assert len(body["workspace"]["results"]) <= 2


@pytest.mark.parametrize(
    "params",
    [
        {"q": "cu", "limit": -5},
        {"q": "cu", "limit": 0},
        {"q": "cu", "offset": -9},
        {"q": "cu", "limit": 100000},
        {"q": "cu", "scope": "../bad"},
        {"q": "café🔬"},
    ],
)
def test_route_adversarial_params_never_5xx(client, params):
    r = client.get("/api/search", params=params)
    assert r.status_code == 200
    body = r.json()
    assert body["workspace"]["returned"] == len(body["workspace"]["results"])


# =============================================================================
# Adversarial governance — dirty draft/evidence content must never leak
# (plan §15 risk 2: "a path never appears in results even if it 'matches'")
# =============================================================================


def _adversarial_experiment():
    """A synthetic experiment whose draft carries path-like/secret-shaped content.

    Uses the REAL ``Experiment`` dataclass. A pending entry forces
    status=needs_attention so ``status()`` never invokes the exporter. Values here
    are deliberately dirty — absolute paths, an ``examples/`` fixture path, a
    workspace-internal sidecar path — to prove none of them reach an emitted field.
    """
    return ws.Experiment(
        id="01ADVERSARIAL00000000000001",
        title="Adversarial governance probe",
        created_utc="2026-01-01T00:00:00Z",
        source={"description": "probe", "files": ["examples/leak_fixture.csv"]},
        draft={
            "fields": {
                "sample.material.formula": {
                    "value": "/tmp/secret/absolute_value.dat",
                    "status": "verified",
                    "evidence": [
                        {
                            "source_type": "file",
                            "source_file": "examples/private_scan.csv",
                            "locator": "examples/private_scan.csv:12",
                            "quote": "/var/secret/leaked_quote",
                        }
                    ],
                }
            },
            "pending": [{"kind": "series", "question": "confirm the series"}],
        },
    )


@pytest.mark.parametrize("query", ["secret", "private_scan", "examples", "leak", "absolute_value"])
def test_dirty_paths_never_leak_into_results(query):
    exp = _adversarial_experiment()
    r = run(query, [exp], limit=search.MAX_RESULTS)
    text = blob(r)
    for danger in ("/tmp/", "/var/", "examples/", ".evidence.json", "/records/", "absolute_value.dat"):
        assert danger not in text, f"query {query!r} leaked {danger!r}"
    for x in r.results:
        for attr in (x.label, x.match.snippet, x.match.field, x.title):
            assert not attr.startswith("/")
            assert "examples/" not in attr


def test_safe_aspects_still_match_on_dirty_experiment():
    # The sanitizer is surgical: a path-like VALUE is dropped, but the safe field
    # label ("Formula") still matches — search does not over-redact.
    exp = _adversarial_experiment()
    r = run("formula", [exp], limit=search.MAX_RESULTS)
    assert any(x.kind == "draft_field" and x.match.snippet == "Formula" for x in r.results)


def test_synthetic_archive_uri_is_not_treated_as_a_path(experiments):
    # ssrl-archive:// URIs are already-served legitimate leads (shown in /pending
    # and /evidence); they must NOT be redacted as filesystem paths.
    #
    # TAKES THE `experiments` FIXTURE, and the reason is a real defect rather than
    # tidiness. This test used to take NO fixture and call a module-level
    # `experiments_fixture()` helper that opened a worked-example session directly.
    # Nothing had set `ISAAC_UI_WORKSPACE`, and the package's one autouse fixture
    # only neutralises the packaged memory snapshot — so the session was created in
    # whatever the AMBIENT default workspace is, which on a developer machine is
    # `/tmp/isaac-ui-workspace`. It was never disposed, so every run of this file left
    # one more `_tutorial/<session id>/` directory behind, each holding five
    # materialised example records: 50 of them had accumulated when this was found.
    # The `experiments` fixture points the workspace at this test's own `tmp_path` and
    # seeds exactly the same five records, so the assertion is unchanged and the write
    # lands where pytest can clean it up.
    r = run("xanes_reduction_v2", experiments, limit=search.MAX_RESULTS)
    assert r.total > 0


# =============================================================================
# Additional contract pins surfaced by independent review
# =============================================================================


def test_negative_multi_token_returns_empty(experiments):
    # token-AND: one matching + one non-matching token => no results.
    r = run("ssrl zzznope", experiments)
    assert r.reason is None
    assert r.total == 0


def test_long_value_snippet_is_windowed():
    long_value = "x" * 200 + "NEEDLE" + "y" * 200  # >120 chars, needle in the middle
    exp = ws.Experiment(
        id="01LONGVALUE0000000000000001",
        title="Long value probe",
        created_utc="2026-01-02T00:00:00Z",
        source={"description": "probe", "files": []},
        draft={
            "fields": {
                "sample.note": {"value": long_value, "status": "verified", "evidence": []}
            },
            "pending": [{"kind": "series", "question": "q"}],
        },
    )
    r = run("needle", [exp], limit=search.MAX_RESULTS)
    field_hits = [x for x in r.results if x.kind == "draft_field"]
    assert field_hits
    snip = field_hits[0].match.snippet
    assert "needle" in snip.lower()
    assert len(snip) < len(long_value)  # windowed, not echoed whole


def test_offsets_bracket_the_matched_token(experiments):
    r = run("ssrl", experiments, limit=search.MAX_RESULTS)
    hit = next(x for x in r.results if x.kind == "draft_field")
    assert hit.match.offsets
    for start, end in hit.match.offsets:
        assert hit.match.snippet[start:end].lower() == "ssrl"


def test_max_input_length_truncation(experiments):
    r = run("z" * 300, experiments)
    assert len(r.normalized_query) <= 256


def test_same_value_distinct_fields_both_surface(experiments):
    # facility_name and site both hold "SSRL" — distinct fields (distinct labels)
    # must BOTH surface; dedup only collapses byte-identical leads.
    r = run("ssrl", experiments, limit=search.MAX_RESULTS)
    exp1_fields = [
        x
        for x in r.results
        if x.kind == "draft_field" and x.experiment_id == ws.SEED_NEW_DRAFT_ID
    ]
    labels = {x.label for x in exp1_fields}
    assert {"Facility Name", "Site"} <= labels

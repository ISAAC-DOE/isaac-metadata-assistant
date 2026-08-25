"""``GET /api/experiments/{id}`` must compose each run's draft ONCE — pinned structurally.

WHY THIS FILE EXISTS. The record-detail route was measured
(`docs/evidence/scale-envelope-2026-08-25.md` §3) at **flat payload, linear time**:
~1.5 KB at any run count, 3.0 ms at 25 runs and 83.2 ms at 1,000. ``cProfile`` over ten
requests on a 1,000-run record put ``copy.deepcopy`` at ~49% cumulative, driven by
``Experiment.resolved_run_draft`` at **3,000 calls per request** — exactly 3x the run
count, because ``export_units()`` composes every run's draft and the route reached it
three times:

    1x  routes._detail  <- _workflow_for            <- workspace.draft_ok
    1x  routes._detail  (detail["draft_ok"])        <- workspace.draft_ok
    1x  routes._detail  <- dependencies.artifact_state <- _fan_out_artifact_state

``json.decoder.raw_decode`` was **1** call per request, so document parsing was never
the bottleneck. And on a record with **no open questions** the count is FIVE, not three:
``_summary``'s ``status()`` and ``_workflow_for``'s ``export_ready()`` each reach
``_all_units_pass_dry_run`` once ``pending_count() == 0``, which they short-circuit past
while anything is still pending.

**THE REMEDY IS THREADING, NOT CACHING, AND THAT IS THE WHOLE DESIGN.** A per-instance
memo (``functools.cached_property``, an instance dict, a ``rev``-keyed cache) would be
unsafe here for a reason this repository has already written down: routes MUTATE an
``Experiment`` and then re-read its derived state in the same request (answer -> recompute
status/workflow), so a memo would serve a stale composition after a write and no test in
the suite would necessarily see it. So ``routes._shared_units`` composes the unit list
once per detail response and every consumer takes it as an OPTIONAL argument whose
default is "compose your own". Nothing is stored, nothing is invalidated, and the
un-threaded path is still the code that runs everywhere else.

**WHAT IS GUARDED HERE IS NOT THE TIMING.** A wall-clock assertion in the normal suite is
flaky under CPU contention and this repository has been bitten by exactly that
(``CLAUDE.md`` §7). The guards are:

1. **A call-count guard** — ``resolved_run_draft`` is entered exactly once per run and
   ``export_units`` exactly once per detail response, on a pending record and on a fully
   answered one. Equality rather than a ceiling, so a future regression back to 3x or 5x
   is a named failure.
2. **A structural anti-scaling guard** — compositions-per-run is IDENTICAL for a small and
   a large record.
3. **BYTE EQUALITY OF THE WHOLE RESPONSE, threaded against un-threaded**, over every
   shape the derivations branch on. ``routes._shared_units`` is the one seam, so
   monkeypatching it to ``None`` reproduces the pre-change code path exactly and the two
   response bodies must be identical byte for byte — not merely equal as parsed JSON.
4. **A no-mutation guard** on the shared list: sharing one composed unit list between
   ``draft_ok``, ``status``, ``export_ready`` and ``artifact_state`` is sound only because
   ``validate_draft``, ``export_draft`` and ``transform`` read their draft and never write
   it. That is asserted rather than assumed.

The out-of-suite before/after wall-clock is in the evidence document; nothing here times
anything.
"""

from __future__ import annotations

import copy
import json

import pytest

import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_api import dependencies
from isaac_api import experiment_repository as repo
from isaac_records.models import field_value, user_confirmation

from conftest import client_ws, tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


# --- workload builders --------------------------------------------------------
#
# Ids are FIXED rather than minted, because two of the assertions below compare two
# HTTP responses byte for byte and a time-ordered ULID would differ between them.


def _rid(prefix: str, i: int) -> str:
    """A 26-character id from ``[A-Z0-9]`` — what ``is_record_id`` requires."""
    stem = f"{prefix}{i:03d}"
    assert len(stem) <= 26, stem
    return stem + "0" * (26 - len(stem))


def _seeded_run_draft() -> dict:
    """What ``routes._seed_for_new_run`` leaves on a run: the ``pending`` KEY PRESENT."""
    return {"pending": [copy.deepcopy(e) for e in repo.blank_draft()["pending"]]}


def _legacy_run_draft() -> dict:
    """A LEGACY run — no ``pending`` key at all.

    The durable state ``new_run`` produced before ``_seed_for_new_run`` shipped, so every
    run created before that deploy still looks like this.
    """
    return {}


def _build(store, exp_id: str, title: str, own_draft: dict, run_drafts: list[dict]):
    exp = store.create_experiment(title, {"kind": "synthetic"}, own_draft, id=exp_id)
    for i, draft in enumerate(run_drafts):
        exp.add_run(label=f"Run {i + 1}", draft=draft, id=_rid(exp_id[:20], i))
    exp.save_versioned()
    return exp_id


def _split_full_draft() -> tuple[dict, dict]:
    """``(experiment_draft, run_draft)`` from the export-ready seed.

    The same split ``test_export_fan_out`` uses, and for the same reason: the levels come
    from the application's OWN classifiers, so this fixture cannot drift away from the
    composition the product performs.
    """
    full = ws._full_draft()
    experiment: dict = {"meta": copy.deepcopy(full["meta"]), "fields": {}, "pending": []}
    run: dict = {"fields": {}, "pending": []}
    for path, envelope in (full.get("fields") or {}).items():
        level = ws.field_level(path)
        if level == ws.LEVEL_EXPERIMENT:
            experiment["fields"][path] = copy.deepcopy(envelope)
        elif level == ws.LEVEL_RUN:
            run["fields"][path] = copy.deepcopy(envelope)
    for key, value in full.items():
        if key in ("fields", "meta", "pending", "implicit", "block_evidence"):
            continue
        level = ws.block_level(key)
        if level == ws.LEVEL_EXPERIMENT:
            experiment[key] = copy.deepcopy(value)
        elif level == ws.LEVEL_RUN:
            run[key] = copy.deepcopy(value)
    experiment["implicit"] = copy.deepcopy(full.get("implicit") or [])
    block_evidence = full.get("block_evidence") or {}
    experiment["block_evidence"] = {
        k: copy.deepcopy(v) for k, v in block_evidence.items() if k.startswith("attribution:")
    }
    run["block_evidence"] = {
        k: copy.deepcopy(v) for k, v in block_evidence.items() if not k.startswith("attribution:")
    }
    return experiment, run


def _fan_out(store, exp_id: str, labels: tuple[str, ...], *, sample_id: str | None = None):
    """An experiment with N EXPORT-READY runs — ``pending_count() == 0``, so the
    derivations that short-circuit on open questions are actually entered."""
    experiment_draft, run_draft = _split_full_draft()
    if sample_id is not None:
        experiment_draft["fields"]["sample.sample_id"] = field_value(
            sample_id,
            status="verified",
            evidence=[user_confirmation("Sample id?", sample_id, "2026-01-01T00:00:00Z")],
        )
    exp = store.create_experiment(
        "Fan-out fixture", {"kind": "synthetic"}, experiment_draft, id=exp_id
    )
    for i, label in enumerate(labels):
        exp.add_run(label=label, draft=copy.deepcopy(run_draft), id=_rid(exp_id[:20], i))
    exp.save_versioned()
    return store.load_experiment(exp_id)


def _export(client, exp_id: str):
    tag = client.get(f"/api/experiments/{exp_id}").headers["ETag"]
    response = client.post(
        f"/api/experiments/{exp_id}/export", headers={"If-Match": tag}
    )
    assert response.status_code == 200, response.text
    assert response.json().get("ok") is True, response.text
    return response


# --- the call counter ---------------------------------------------------------


class _Counter:
    def __init__(self) -> None:
        self.resolved_run_draft = 0
        self.export_units = 0

    def __repr__(self) -> str:  # pragma: no cover - assertion message only
        return (
            f"resolved_run_draft={self.resolved_run_draft} "
            f"export_units={self.export_units}"
        )


@pytest.fixture()
def counted(monkeypatch) -> _Counter:
    """Count entries into the two methods the profile named, over the real HTTP surface.

    Patched on the CLASS, so the count is what the route actually did rather than what a
    re-implementation of the route would have done.
    """
    counter = _Counter()
    real_compose = ws.Experiment.resolved_run_draft
    real_units = ws.Experiment.export_units

    def spy_compose(self, run):
        counter.resolved_run_draft += 1
        return real_compose(self, run)

    def spy_units(self, *args, **kwargs):
        counter.export_units += 1
        return real_units(self, *args, **kwargs)

    monkeypatch.setattr(ws.Experiment, "resolved_run_draft", spy_compose)
    monkeypatch.setattr(ws.Experiment, "export_units", spy_units)
    return counter


# --- 1. the call-count guard --------------------------------------------------


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("n", [1, 3, 7])
def test_a_detail_read_composes_each_runs_draft_exactly_once(client, counted, legacy, n):
    """THE DEFECT, stated as an equality.

    Before threading this was ``3 * n`` compositions and 3 unit lists, on the workload the
    scale envelope measured (open questions, so the dry-run branches are not entered).
    """
    store = client_ws(client)
    exp_id = _build(
        store,
        _rid("01DETAILONCE", n + (100 if legacy else 0)),
        "detail-once",
        repo.blank_draft(),
        [(_legacy_run_draft() if legacy else _seeded_run_draft()) for _ in range(n)],
    )
    counted.resolved_run_draft = counted.export_units = 0

    response = client.get(f"/api/experiments/{exp_id}")
    assert response.status_code == 200, response.text
    assert response.json()["pending_count"] > 0, "workload must still owe questions"

    assert counted.resolved_run_draft == n, counted
    assert counted.export_units == 1, counted


def test_a_detail_read_of_a_fully_answered_record_also_composes_once(client, counted):
    """THE OTHER HALF, and it is the worse case rather than the better one.

    With ``pending_count() == 0`` the two derivations that short-circuit past
    ``_all_units_pass_dry_run`` stop short-circuiting, so ``_summary``'s ``status()`` and
    ``_workflow_for``'s ``export_ready()`` each reach ``export_units()`` too — FIVE unit
    lists per response, and ``5 * n`` compositions. It must still be one and ``n``.
    """
    store = client_ws(client)
    exp = _fan_out(store, "01DETAILONCEANSWERED000000", ("Run A", "Run B", "Run C"))
    counted.resolved_run_draft = counted.export_units = 0

    body = client.get(f"/api/experiments/{exp.id}").json()
    assert body["pending_count"] == 0, body["pending_count"]

    assert counted.resolved_run_draft == 3, counted
    assert counted.export_units == 1, counted


def test_a_detail_read_of_an_exported_fan_out_also_composes_once(client, counted):
    """And once every run is exported, where ``artifact_state`` additionally reads each
    written record off disk through the SAME unit list."""
    store = client_ws(client)
    exp = _fan_out(
        store, "01DETAILONCEEXPORTED000000", ("Run A", "Run B"), sample_id="SAMPLE-1"
    )
    _export(client, exp.id)
    counted.resolved_run_draft = counted.export_units = 0

    body = client.get(f"/api/experiments/{exp.id}").json()
    assert body["artifact"]["state"] == "current", body["artifact"]

    assert counted.resolved_run_draft == 2, counted
    assert counted.export_units == 1, counted


# --- 2. the structural anti-scaling guard -------------------------------------


SMALL, LARGE = 4, 64


def test_the_composition_work_per_run_does_not_grow_with_the_run_count(client, counted):
    """Not "is it fast" but "is the work per run CONSTANT".

    A ratio rather than a total, because the response is inherently one composition per
    run; what must not move is the MULTIPLE. Equality, so a regression to any factor
    above one is a named failure rather than a slow test.
    """
    store = client_ws(client)
    small = _build(
        store, "01DETAILSCALESMALL00000000", "small", repo.blank_draft(),
        [_seeded_run_draft() for _ in range(SMALL)],
    )
    large = _build(
        store, "01DETAILSCALELARGE00000000", "large", repo.blank_draft(),
        [_seeded_run_draft() for _ in range(LARGE)],
    )
    client.get(f"/api/experiments/{small}")  # warm any one-time lazy import

    counted.resolved_run_draft = counted.export_units = 0
    client.get(f"/api/experiments/{small}")
    small_calls, small_units = counted.resolved_run_draft, counted.export_units

    counted.resolved_run_draft = counted.export_units = 0
    client.get(f"/api/experiments/{large}")
    large_calls, large_units = counted.resolved_run_draft, counted.export_units

    assert small_calls / SMALL == large_calls / LARGE == 1, (
        f"{SMALL} runs -> {small_calls} compositions, {LARGE} runs -> {large_calls}"
    )
    assert small_units == large_units == 1, (small_units, large_units)


# --- 3. byte equality, threaded against un-threaded ---------------------------


def _all_shapes(client) -> dict[str, str]:
    """Every shape the four unit-dependent derivations branch on, keyed by name.

    Returned as ``{name: experiment_id}``. The five canonical seeds are read through the
    worked-example session this client is bound to; everything else is built here.
    """
    store = client_ws(client)
    shapes: dict[str, str] = {
        f"seed:{rid}": rid for rid in sorted(client.tutorial_record_ids)
    }

    shapes["zero_run"] = _build(
        store, "01SHAPEZERORUN000000000000", "zero run", repo.blank_draft(), []
    )
    shapes["legacy_run"] = _build(
        store, "01SHAPELEGACY00000000000000"[:26], "legacy", repo.blank_draft(),
        [_legacy_run_draft()],
    )
    shapes["multi_run"] = _build(
        store, "01SHAPEMULTIRUN00000000000", "multi", repo.blank_draft(),
        [_seeded_run_draft() for _ in range(3)],
    )
    shapes["mixed_runs"] = _build(
        store, "01SHAPEMIXEDRUNS0000000000", "mixed", repo.blank_draft(),
        [_legacy_run_draft(), _seeded_run_draft(), {"pending": []}],
    )

    # A MALFORMED PERSISTED `pending` ENTRY. `pending()` passes a non-dict through
    # as-is rather than repairing it, so the derivations must survive one.
    malformed = repo.blank_draft()
    malformed["pending"] = [*malformed["pending"], "a malformed persisted entry", None, 7]
    shapes["malformed_pending_zero_run"] = _build(
        store, "01SHAPEMALFORMED000000000A", "malformed", copy.deepcopy(malformed), []
    )
    shapes["malformed_pending_with_runs"] = _build(
        store, "01SHAPEMALFORMED000000000B", "malformed runs", copy.deepcopy(malformed),
        [_legacy_run_draft(), _legacy_run_draft()],
    )

    # DRAFTS THAT FAIL THE NO-GUESSING CHECKS, so `draft_ok` is discriminating rather
    # than True in every row.
    bad = repo.blank_draft()
    bad["meta"] = {}
    shapes["draft_not_ok_zero_run"] = _build(
        store, "01SHAPEBADDRAFT000000000A0", "bad draft", copy.deepcopy(bad), []
    )
    bad_run = _seeded_run_draft()
    bad_run["fields"] = {
        "sample.sample_id": {"value": "unevidenced", "status": "verified", "evidence": []}
    }
    shapes["draft_not_ok_with_runs"] = _build(
        store, "01SHAPEBADDRAFT000000000B0", "bad draft runs", copy.deepcopy(bad),
        [copy.deepcopy(bad_run), copy.deepcopy(bad_run)],
    )

    # A FULLY EXPORTED FAN-OUT, and a PARTIAL one (export two runs, then add a third).
    full = _fan_out(store, "01SHAPEFANOUTFULL000000000", ("Run A", "Run B"), sample_id="S1")
    _export(client, full.id)
    shapes["fan_out_fully_exported"] = full.id

    partial = _fan_out(store, "01SHAPEFANOUTPART000000000", ("Run A", "Run B"), sample_id="S1")
    _export(client, partial.id)
    reloaded = store.load_experiment(partial.id)
    _, run_draft = _split_full_draft()
    reloaded.add_run(label="Run C", draft=run_draft, id="01SHAPEFANOUTPARTRUNC00000")
    reloaded.save_versioned()
    shapes["fan_out_partially_exported"] = partial.id

    # A ZERO-RUN record exported and then EDITED — the non-fan-out `stale` branch.
    experiment_draft, run_draft = _split_full_draft()
    merged = copy.deepcopy(experiment_draft)
    for key, value in run_draft.items():
        if key == "fields":
            merged["fields"].update(copy.deepcopy(value))
        elif key == "block_evidence":
            merged.setdefault("block_evidence", {}).update(copy.deepcopy(value))
        elif key != "pending":
            merged[key] = copy.deepcopy(value)
    store.create_experiment(
        "solo exported", {"kind": "synthetic"}, copy.deepcopy(merged),
        id="01SHAPESOLOEXPORTED0000000",
    )
    _export(client, "01SHAPESOLOEXPORTED0000000")
    shapes["zero_run_fully_exported"] = "01SHAPESOLOEXPORTED0000000"

    store.create_experiment(
        "solo stale", {"kind": "synthetic"}, copy.deepcopy(merged),
        id="01SHAPESOLOSTALE0000000000",
    )
    _export(client, "01SHAPESOLOSTALE0000000000")
    stale = store.load_experiment("01SHAPESOLOSTALE0000000000")
    stale.draft["tags"] = [*(stale.draft.get("tags") or []), "shape-stale-marker"]
    stale.save_versioned()
    shapes["zero_run_stale"] = "01SHAPESOLOSTALE0000000000"

    return shapes


def test_the_shape_set_covers_every_branch_the_derivations_take(client):
    """A GUARD ON THE GUARD. The byte-equality test below is only as good as its inputs,
    and a fixture that silently produced fifteen ``needs_attention`` rows would pass it
    while exercising one branch. So the SET of observed ``status`` / ``draft_ok`` /
    ``artifact.state`` values is pinned, and a shape builder that stops producing one is
    a named failure rather than a quiet loss of coverage."""
    shapes = _all_shapes(client)
    assert len(shapes) == 17, sorted(shapes)

    seen = {"status": set(), "draft_ok": set(), "artifact": set()}
    for exp_id in shapes.values():
        body = client.get(f"/api/experiments/{exp_id}").json()
        seen["status"].add(body["status"])
        seen["draft_ok"].add(body["draft_ok"])
        seen["artifact"].add(body["artifact"]["state"])

    assert seen["status"] == {"needs_attention", "in_review", "ready_to_export", "done"}
    assert seen["draft_ok"] == {True, False}
    assert seen["artifact"] == {"none", "current", "stale"}


def test_threading_the_unit_list_does_not_move_one_byte_of_any_response(
    client, monkeypatch
):
    """THE SEMANTIC PROOF, and it is byte equality of the WHOLE response rather than a
    field-by-field comparison of the four keys that happen to depend on the unit list.

    ``routes._shared_units`` is the single seam. Patched to return ``None`` every consumer
    falls back to composing its own units — which is, line for line, the code that ran
    before this change — so the two bodies must be identical byte for byte. A read does
    not bump ``rev`` or ``updated_utc``, so no normalisation is needed and none is done:
    the comparison is on ``response.content``.
    """
    shapes = _all_shapes(client)
    threaded = {
        name: client.get(f"/api/experiments/{exp_id}").content
        for name, exp_id in shapes.items()
    }

    monkeypatch.setattr(routes, "_shared_units", lambda exp: None)
    unthreaded = {
        name: client.get(f"/api/experiments/{exp_id}").content
        for name, exp_id in shapes.items()
    }

    differing = [name for name in shapes if threaded[name] != unthreaded[name]]
    assert not differing, differing
    # …and not vacuously: every body must be a real detail response.
    for name, body in threaded.items():
        parsed = json.loads(body)
        assert {"status", "draft_ok", "workflow", "artifact"} <= set(parsed), name


# --- 4. the property that makes sharing sound ---------------------------------


def test_the_consumers_do_not_write_into_the_composed_drafts(client):
    """WHY ONE LIST CAN BE SHARED AT ALL, asserted rather than assumed.

    ``draft_ok`` runs ``validate_draft``, the dry run runs ``export_draft``, and
    ``artifact_state`` runs ``transform`` — all three over the SAME composed dicts once
    the list is threaded. If any of them wrote into its input, the second consumer would
    see a draft the first had altered and the sharing would be a behaviour change rather
    than a saving. They do not, and this is where that stops being a reading of the truth
    core and becomes a test.
    """
    store = client_ws(client)
    exp = _fan_out(store, "01SHARINGISSOUND0000000000", ("Run A", "Run B"), sample_id="S1")
    _export(client, exp.id)
    exp = store.load_experiment(exp.id)

    units = exp.export_units()
    before = json.dumps([u.draft for u in units], sort_keys=True, default=str)

    assert exp.draft_ok(units=units) is True
    assert exp.export_ready(units=units) is True
    assert exp.status(units=units) == "done"
    assert dependencies.artifact_state(exp, units=units)["state"] == "current"

    after = json.dumps([u.draft for u in units], sort_keys=True, default=str)
    assert after == before, "a consumer wrote into the composed draft it was handed"


def test_the_threaded_and_unthreaded_derivations_agree_on_every_shape(client):
    """The same equality as the byte test, one level down — so a failure localises to a
    derivation instead of to "some byte of some response"."""
    shapes = _all_shapes(client)
    store = client_ws(client)
    for name, exp_id in shapes.items():
        exp = store.load_experiment(exp_id)
        units = exp.export_units()
        assert exp.draft_ok(units=units) == exp.draft_ok(), name
        assert exp.status(units=units) == exp.status(), name
        assert exp.export_ready(units=units) == exp.export_ready(), name
        assert dependencies.artifact_state(exp, units=units) == dependencies.artifact_state(
            exp
        ), name
        assert routes._workflow_for(exp, units=units) == routes._workflow_for(exp), name
        assert routes._summary(exp, units=units) == routes._summary(exp), name


def test_a_zero_run_experiment_ignores_a_unit_list_for_draft_ok(client):
    """THE ONE BRANCH THAT MUST NOT LEARN ABOUT UNITS. ``draft_ok`` on a zero-run
    experiment is ``validate_draft(self.draft).ok`` and stays that, whatever it is
    handed — the zero-run path is the common case and its correctness argument is that
    it is the SAME CALL the pre-fan-out code made.
    """
    store = client_ws(client)
    exp_id = _build(
        store, "01ZERORUNIGNORESUNITS00000", "zero", repo.blank_draft(), []
    )
    exp = store.load_experiment(exp_id)
    assert not exp.runs
    # A list that is not this experiment's at all: the zero-run branch returns before
    # looking, so it cannot change the answer.
    assert exp.draft_ok(units=[]) == exp.draft_ok()

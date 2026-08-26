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
   shape the derivations branch on. ~~``routes._shared_units`` is the one seam, so
   monkeypatching it to ``None`` reproduces the pre-change code path exactly~~ — **there
   are TWO seams and this file asserted one; corrected in place, see
   ``_disable_threading``.** ``_detail`` also derives ``draft_ok`` once and hands it to
   ``_workflow_for``, and both must be disabled to reproduce the pre-change path. The two
   response bodies must then be identical byte for byte — not merely equal as parsed JSON.
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


def _run_id(exp_id: str, i: int) -> str:
    """A run id that is UNIQUE TO ITS EXPERIMENT, and deterministic.

    It used to be ``_rid(exp_id[:20], i)``, which keeps only the first twenty characters
    of the experiment id — so ``…MALFORMED000000000A`` and ``…MALFORMED000000000B``, which
    differ only in their last character, minted THE SAME run ids. Harmless while every
    shape lives in its own experiment document, and a trap for the first assertion that
    looks a run up by id across shapes. The TAIL is what distinguishes these fixtures, so
    the tail is what is kept: ``exp_id[3:]`` is 23 characters and the ordinal is 3 more.
    """
    stem = exp_id[3:] + f"{i:03d}"
    assert len(stem) == 26, stem
    return stem


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
        exp.add_run(label=f"Run {i + 1}", draft=draft, id=_run_id(exp_id, i))
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
        exp.add_run(label=label, draft=copy.deepcopy(run_draft), id=_run_id(exp_id, i))
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
        self.export_draft = 0

    def __repr__(self) -> str:  # pragma: no cover - assertion message only
        return (
            f"resolved_run_draft={self.resolved_run_draft} "
            f"export_units={self.export_units} "
            f"export_draft={self.export_draft}"
        )


@pytest.fixture()
def counted(monkeypatch) -> _Counter:
    """Count entries into the three functions the profile named, over the real HTTP
    surface.

    Patched on the CLASS (and, for ``export_draft``, on the ``workspace`` module that
    imported it), so the count is what the route actually did rather than what a
    re-implementation of the route would have done.

    **``export_draft`` WAS NOT COUNTED HERE, AND ITS ABSENCE HID THE LARGER HALF OF THE
    COST.** The two counters above were enough to prove the composition is shared, and
    this file said so; but on a fully answered record ``status()`` and ``export_ready()``
    each dry-ran EVERY unit, so ``export_draft`` ran 2x the run count and no assertion in
    this file looked at it. An independent review measured it at 200 runs — 400 calls,
    roughly half the request — while every test here passed. A counter that omits the
    dominant term reads as coverage of it.
    """
    counter = _Counter()
    real_compose = ws.Experiment.resolved_run_draft
    real_units = ws.Experiment.export_units
    real_export_draft = ws.export_draft

    def spy_compose(self, run):
        counter.resolved_run_draft += 1
        return real_compose(self, run)

    def spy_units(self, *args, **kwargs):
        counter.export_units += 1
        return real_units(self, *args, **kwargs)

    def spy_export_draft(*args, **kwargs):
        counter.export_draft += 1
        return real_export_draft(*args, **kwargs)

    monkeypatch.setattr(ws.Experiment, "resolved_run_draft", spy_compose)
    monkeypatch.setattr(ws.Experiment, "export_units", spy_units)
    monkeypatch.setattr(ws, "export_draft", spy_export_draft)
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
    # THE TRAP GUARD, and it is the reason ``_shared_dry_run`` gates on
    # ``pending_count()`` rather than computing up front. On THIS workload the dry run
    # is entered ZERO times — ``status()`` answers ``needs_attention`` and
    # ``export_ready()`` returns ``False`` before reaching it — and a "compute it once
    # for the whole response" that ignored that would turn 0 into ``n``, making the
    # COMMON case slower in order to speed up the rare one. Zero, asserted.
    assert counted.export_draft == 0, counted


def test_a_detail_read_of_a_fully_answered_record_also_composes_once(client, counted):
    """THE OTHER HALF, and it is the worse case rather than the better one.

    With ``pending_count() == 0`` the two derivations that short-circuit past
    ``_all_units_pass_dry_run`` stop short-circuiting, so ``_summary``'s ``status()`` and
    ``_workflow_for``'s ``export_ready()`` each reach ``export_units()`` too — FIVE unit
    lists per response, and ``5 * n`` compositions. It must still be one and ``n``.

    **AND ``export_draft`` MUST BE ``n``, NOT ``2 * n``.** Sharing the composed unit list
    removed the repeated COMPOSITION and left the repeated DRY RUN: ``status()`` and
    ``export_ready()`` each ran ``export_draft`` over every unit, measured at 200 runs as
    400 calls per request and roughly half the request's time. ``_shared_dry_run``
    derives the verdict once and hands it to both.
    """
    store = client_ws(client)
    exp = _fan_out(store, "01DETAILONCEANSWERED000000", ("Run A", "Run B", "Run C"))
    counted.resolved_run_draft = counted.export_units = counted.export_draft = 0

    body = client.get(f"/api/experiments/{exp.id}").json()
    assert body["pending_count"] == 0, body["pending_count"]

    assert counted.resolved_run_draft == 3, counted
    assert counted.export_units == 1, counted
    assert counted.export_draft == 3, counted


def test_a_detail_read_of_an_exported_fan_out_also_composes_once(client, counted):
    """And once every run is exported, where ``artifact_state`` additionally reads each
    written record off disk through the SAME unit list.

    ``export_draft`` is ``n`` here BEFORE the dry-run sharing as well as after, and that
    is recorded rather than glossed: ``status()`` short-circuits to ``DONE`` on a fully
    exported record, so only ``export_ready()`` ever reached the dry run on this shape.
    The equality is asserted anyway — a change that made the DONE branch dry-run again
    would be a regression this file would otherwise not see.
    """
    store = client_ws(client)
    exp = _fan_out(
        store, "01DETAILONCEEXPORTED000000", ("Run A", "Run B"), sample_id="SAMPLE-1"
    )
    _export(client, exp.id)
    counted.resolved_run_draft = counted.export_units = counted.export_draft = 0

    body = client.get(f"/api/experiments/{exp.id}").json()
    assert body["artifact"]["state"] == "current", body["artifact"]

    assert counted.resolved_run_draft == 2, counted
    assert counted.export_units == 1, counted
    assert counted.export_draft == 2, counted


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


DRY_SMALL, DRY_LARGE = 3, 24


def test_the_dry_run_work_per_run_does_not_grow_with_the_run_count(client, counted):
    """The same ratio guard for the DRY RUN, on the workload that actually reaches it.

    The test above is taken on records that still owe questions, where ``export_draft``
    is zero — so it could not have caught the 2x it is written to catch. This one uses
    fully answered records, where both consumers reach the dry run, and pins
    ``export_draft`` per run at exactly one. ``LARGE`` is smaller here than above because
    each run's dry run is a real ``export_draft``, not a composition.
    """
    store = client_ws(client)
    small = _fan_out(
        store,
        "01DRYSCALESMALL00000000000",
        tuple(f"Run {i}" for i in range(DRY_SMALL)),
    )
    large = _fan_out(
        store,
        "01DRYSCALELARGE00000000000",
        tuple(f"Run {i}" for i in range(DRY_LARGE)),
    )
    assert client.get(f"/api/experiments/{small.id}").json()["pending_count"] == 0
    assert client.get(f"/api/experiments/{large.id}").json()["pending_count"] == 0

    counted.export_draft = 0
    client.get(f"/api/experiments/{small.id}")
    small_dry = counted.export_draft

    counted.export_draft = 0
    client.get(f"/api/experiments/{large.id}")
    large_dry = counted.export_draft

    assert small_dry / DRY_SMALL == large_dry / DRY_LARGE == 1, (
        f"{DRY_SMALL} runs -> {small_dry} dry runs, {DRY_LARGE} runs -> {large_dry}"
    )


# --- 3. byte equality, threaded against un-threaded ---------------------------


#: How many DISTINCT experiments the shape set holds. Asserted inside ``_all_shapes``
#: AND by each of its three consumers, because those two guards fail differently: the
#: first catches a builder that stopped producing a shape (or produced an alias of one
#: it already had), the second catches a consumer handed a set that is not the one
#: ``_all_shapes`` promises — including an empty one, which every "for name in shapes"
#: loop below would otherwise iterate zero times and pass.
_SHAPE_COUNT = 21


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

    # DEGRADED ARTIFACTS — the ``MISSING_REASON`` branches, which nothing above enters.
    # `artifact_state` has four separate "the file is not readable as the record it
    # should be" exits (two on the single-record path, two on the fan-out path) and the
    # shape set reached NONE of them: every exported fixture above has a well-formed
    # artifact on disk. An independent review measured the gap and built these four; they
    # are adopted here because a branch the byte-equality test never enters is a branch
    # the threading is not proved over.
    for name, exp_id, damage in (
        ("zero_run_artifact_deleted", "01SHAPESOLODELETED00000000", "delete"),
        ("zero_run_artifact_unparseable", "01SHAPESOLOGARBAGE00000000", "garbage"),
    ):
        store.create_experiment(
            f"solo {damage}", {"kind": "synthetic"}, copy.deepcopy(merged), id=exp_id
        )
        _export(client, exp_id)
        path = store.load_experiment(exp_id).record_path()
        assert path is not None and path.exists(), exp_id
        if damage == "delete":
            path.unlink()
        else:
            path.write_text("{not json at all", encoding="utf-8")
        shapes[name] = exp_id

    for name, exp_id, damage in (
        ("fan_out_artifact_deleted", "01SHAPEFANOUTDELETED000000", "delete"),
        ("fan_out_artifact_unparseable", "01SHAPEFANOUTGARBAGE000000", "garbage"),
    ):
        damaged = _fan_out(store, exp_id, ("Run A", "Run B"), sample_id="S1")
        _export(client, damaged.id)
        units = store.load_experiment(exp_id).export_units()
        path = units[0].record_path()
        assert path is not None and path.exists(), exp_id
        if damage == "delete":
            path.unlink()
        else:
            path.write_text("{not json at all", encoding="utf-8")
        shapes[name] = exp_id

    # THE GUARD LIVES HERE, NOT IN ONE TEST, and that is the point of moving it. It used
    # to be ``assert len(shapes) == 17`` in the coverage test alone, which counts KEYS:
    # aliasing three builders to the same experiment id left the count at 17 while three
    # shapes vanished, and the byte-equality test — which iterates this same dict — would
    # not have noticed either. Counting the DISTINCT ids as well closes both, and doing it
    # inside the builder means every consumer of the shape set gets the guard.
    assert len(set(shapes.values())) == len(shapes) == _SHAPE_COUNT, sorted(shapes)
    return shapes


def test_the_shape_set_covers_every_branch_the_derivations_take(client):
    """A GUARD ON THE GUARD. The byte-equality test below is only as good as its inputs,
    and a fixture that silently produced fifteen ``needs_attention`` rows would pass it
    while exercising one branch. So the SET of observed ``status`` / ``draft_ok`` /
    ``artifact.state`` values is pinned, and a shape builder that stops producing one is
    a named failure rather than a quiet loss of coverage."""
    shapes = _all_shapes(client)
    assert len(shapes) == _SHAPE_COUNT, sorted(shapes)
    # The count and the distinctness are asserted INSIDE ``_all_shapes`` — see the note
    # there for why counting keys in this test alone was not a guard at all.
    seen = {"status": set(), "draft_ok": set(), "artifact": set(), "reason": set()}
    for exp_id in shapes.values():
        body = client.get(f"/api/experiments/{exp_id}").json()
        seen["status"].add(body["status"])
        seen["draft_ok"].add(body["draft_ok"])
        seen["artifact"].add(body["artifact"]["state"])
        seen["reason"].add(body["artifact"]["reason"])

    assert seen["status"] == {"needs_attention", "in_review", "ready_to_export", "done"}
    assert seen["draft_ok"] == {True, False}
    assert seen["artifact"] == {"none", "current", "stale"}
    # THE REASON, NOT ONLY THE LABEL. Three different situations all report ``stale``,
    # and the four degraded-artifact shapes exist precisely to reach the one the set
    # never reached before — so pinning the label alone would let them be deleted
    # without a failure.
    assert seen["reason"] == {
        None,
        dependencies._STALE_REASON,
        dependencies._INCOMPLETE_REASON,
        dependencies.MISSING_REASON,
    }, seen["reason"]


def _disable_threading(monkeypatch) -> None:
    """Restore the PRE-CHANGE call pattern in :func:`routes._detail`, all THREE seams.

    **THERE ARE NOW THREE, AND THE COUNT HAS BEEN WRONG ONCE ALREADY** — the paragraph
    below records it saying "one" when there were two. The third is
    ``routes._shared_dry_run``: ``_detail`` derives the dry-run verdict once and passes
    it as ``dry_run_ok`` to both ``_summary``'s ``status()`` and ``_workflow_for``'s
    ``export_ready()``. Patching the other two does not revert that, so the ``kwargs``
    filter below drops ``dry_run_ok`` as well — and both are dropped by REMOVING the
    keyword rather than by passing ``None``, because ``None`` is what the parameter
    already defaults to and dropping it is what the fourteen unshared call sites do.

    **THERE ARE TWO SEAMS, AND THIS FILE USED TO CLAIM THERE WAS ONE.** The docstring
    below said *"``routes._shared_units`` is the single seam"*; it is not.
    ``_detail`` also derives ``draft_ok`` ONCE and passes it as
    ``_workflow_for(…, draft_ok=draft_ok)``, and patching ``_shared_units`` does not
    revert that. Measured under the old single patch, ``_workflow_for`` was still
    receiving ``draft_ok`` as a keyword on every call — so ``_workflow_for``'s
    ``draft_ok is None`` branch was NEVER exercised through ``_detail``, and the arm
    the test called "the code that ran before" was a third configuration that has
    never shipped (3-run record: main 9/3/6 for
    ``resolved_run_draft``/``export_units``/``validate_draft``, that arm 6/2/3,
    threaded 3/1/3).

    **THE CONSEQUENCE WAS REPRODUCED, NOT INFERRED.** Mutating ``routes.py``'s
    ``draft_ok=draft_ok`` to ``draft_ok=(not draft_ok)`` left this whole file at
    **14 passed**. It is a false claim in the proof file rather than an unguarded
    product defect — the wider suite does catch that mutation — and the evidence
    document's own A/B harness had it right, disabling BOTH seams.

    Dropping the boolean rather than dropping the whole keyword is deliberate: it is
    what ``_workflow_for``'s ``units=None, draft_ok=None`` default means, and it is
    what the other fourteen call sites of `_workflow_for` actually do (fifteen in
    `routes.py`, counted; the commit message said "twelve").
    """
    real_workflow_for = routes._workflow_for
    monkeypatch.setattr(routes, "_shared_units", lambda exp: None)
    monkeypatch.setattr(routes, "_shared_dry_run", lambda exp, **kwargs: None)
    monkeypatch.setattr(
        routes, "_workflow_for", lambda exp, **kwargs: real_workflow_for(exp)
    )


def test_threading_the_unit_list_does_not_move_one_byte_of_any_response(
    client, monkeypatch
):
    """THE SEMANTIC PROOF, and it is byte equality of the WHOLE response rather than a
    field-by-field comparison of the four keys that happen to depend on the unit list.

    ~~``routes._shared_units`` is the single seam.~~ **FALSE, and corrected in place
    rather than deleted, because a proof file that misnames its own seam is the exact
    thing worth remembering.** There are TWO — see :func:`_disable_threading`. With both
    disabled every consumer falls back to composing its own units and deriving its own
    ``draft_ok``, which is line for line the code that ran before this change, so the two
    bodies must be identical byte for byte. A read does not bump ``rev`` or
    ``updated_utc``, so no normalisation is needed and none is done: the comparison is on
    ``response.content``.
    """
    shapes = _all_shapes(client)
    assert len(shapes) == _SHAPE_COUNT, sorted(shapes)
    threaded = {
        name: client.get(f"/api/experiments/{exp_id}").content
        for name, exp_id in shapes.items()
    }

    _disable_threading(monkeypatch)
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
    assert len(shapes) == _SHAPE_COUNT, sorted(shapes)
    store = client_ws(client)
    for name, exp_id in shapes.items():
        exp = store.load_experiment(exp_id)
        units = exp.export_units()
        dry_run_ok = exp.dry_run_verdict(units=units)
        assert exp.draft_ok(units=units) == exp.draft_ok(), name
        assert exp.status(units=units) == exp.status(), name
        assert exp.export_ready(units=units) == exp.export_ready(), name
        # THE THIRD SEAM, at the level it lives on. ``_detail`` does not call
        # ``status()``/``export_ready()`` with ``units`` alone; it passes the dry-run
        # verdict it already derived. That configuration is what ships, so that
        # configuration is what is compared against the un-threaded derivation.
        assert exp.status(units=units, dry_run_ok=dry_run_ok) == exp.status(), name
        assert (
            exp.export_ready(units=units, dry_run_ok=dry_run_ok) == exp.export_ready()
        ), name
        assert dependencies.artifact_state(exp, units=units) == dependencies.artifact_state(
            exp
        ), name
        assert routes._workflow_for(exp, units=units) == routes._workflow_for(exp), name
        # THE SECOND SEAM, at the level it lives on. ``_detail`` does not call
        # ``_workflow_for(exp, units=units)``; it calls it with the boolean it already
        # derived. That configuration is what ships, so that configuration is what is
        # compared against the un-threaded derivation.
        assert routes._workflow_for(
            exp,
            units=units,
            draft_ok=exp.draft_ok(units=units),
            dry_run_ok=dry_run_ok,
        ) == routes._workflow_for(exp), name
        assert routes._summary(exp, units=units) == routes._summary(exp), name
        assert routes._summary(
            exp, units=units, dry_run_ok=dry_run_ok
        ) == routes._summary(exp), name


def test_the_dry_run_verdict_is_none_exactly_when_neither_consumer_would_reach_it(
    client,
):
    """THE GATE, stated as an equivalence rather than as a direction.

    ``dry_run_verdict`` must answer ``None`` on every shape where the dry run is entered
    zero times today, and a real boolean on every shape where it is entered at all — the
    first half stops the sharing from making the common (pending) case slower, the second
    half stops it from silently disabling the sharing. Both are checked over the whole
    shape set, and the ``None`` half is checked by COUNTING the dry runs the un-threaded
    derivations actually perform rather than by re-stating the gate's own condition,
    which would pass by construction.
    """
    shapes = _all_shapes(client)
    assert len(shapes) == _SHAPE_COUNT, sorted(shapes)
    store = client_ws(client)
    seen_none = seen_bool = 0
    for name, exp_id in shapes.items():
        exp = store.load_experiment(exp_id)
        units = exp.export_units()
        verdict = exp.dry_run_verdict(units=units)

        calls = 0
        real_export_draft = ws.export_draft
        with pytest.MonkeyPatch.context() as patch:
            def spy(*args, _real=real_export_draft, **kwargs):
                nonlocal calls
                calls += 1
                return _real(*args, **kwargs)

            patch.setattr(ws, "export_draft", spy)
            exp.status()
            exp.export_ready()

        if verdict is None:
            seen_none += 1
            assert calls == 0, f"{name}: verdict withheld but {calls} dry run(s) happen"
        else:
            seen_bool += 1
            assert calls > 0, f"{name}: verdict derived but no dry run happens"
            assert verdict == exp._all_units_pass_dry_run(units=units), name
    # …and not vacuously: the shape set must contain both kinds.
    assert seen_none and seen_bool, (seen_none, seen_bool)


def test_a_threaded_false_verdict_is_honoured_rather_than_re_derived(client):
    """``dry_run_ok=False`` MUST NOT BE READ AS "not supplied".

    ``False`` and ``None`` are both falsy, and an implementation written as ``dry_run_ok
    or self._all_units_pass_dry_run(...)`` would silently re-derive on every negative
    verdict — restoring the 2x on exactly the records whose dry run FAILS, and doing it
    invisibly, because re-deriving produces the same answer. So the two consumers are
    handed a ``False`` that disagrees with the truth and must return the ``False``.
    """
    store = client_ws(client)
    exp = store.load_experiment(_fan_out(store, "01DRYRUNFALSEHONOURED00000", ("A", "B")).id)
    units = exp.export_units()
    assert exp.dry_run_verdict(units=units) is True, "fixture must pass the dry run"

    assert exp.status(units=units, dry_run_ok=False) == "in_review"
    assert exp.status(units=units, dry_run_ok=True) == "ready_to_export"
    assert exp.export_ready(units=units, dry_run_ok=False) is False
    assert exp.export_ready(units=units, dry_run_ok=True) is True


def test_a_zero_run_experiment_ignores_a_unit_list_for_draft_ok(client):
    """THE ONE BRANCH THAT MUST NOT LEARN ABOUT UNITS. ``draft_ok`` on a zero-run
    experiment is ``validate_draft(self.draft).ok`` and stays that, whatever it is
    handed — the zero-run path is the common case and its correctness argument is that
    it is the SAME CALL the pre-fan-out code made.

    **THE FIXTURE IS A DRAFT THAT FAILS VALIDATION, AND THAT IS THE WHOLE TEST.** It was
    ``repo.blank_draft()``, on which ``validate_draft(draft).ok`` is ``True`` and
    ``all([])`` is also ``True`` — so both sides of the equality were the constant
    ``True``, the two branches were indistinguishable, and the exact violation this test
    names (moving the ``units`` check ABOVE the zero-run early return) left the file at
    **14 passed**. On a failing draft the two branches answer differently: the early
    return says ``False``, and an implementation that consulted ``units=[]`` first would
    say ``all([]) is True``. So ``draft_ok() is False`` is asserted FIRST, because the
    equality is only decisive once the constant is ruled out.
    """
    store = client_ws(client)
    bad = repo.blank_draft()
    bad["meta"] = {}
    exp_id = _build(store, "01ZERORUNIGNORESUNITS00000", "zero", bad, [])
    exp = store.load_experiment(exp_id)
    assert not exp.runs
    assert exp.draft_ok() is False, "the fixture must not be a draft that passes"
    # A list that is not this experiment's at all: the zero-run branch returns before
    # looking, so it cannot change the answer — and `all([])` would answer `True`.
    assert exp.draft_ok(units=[]) is False
    assert exp.draft_ok(units=[]) == exp.draft_ok()


def test_the_mutation_paths_shared_unit_list_does_not_move_an_invalidation(client):
    """THE SECOND THREADING SITE, AND IT IS ON THE MUTATION PATH.

    ``dependencies.build_invalidation`` composes ``post_exp.export_units()`` once and
    threads it to BOTH ``_post_workflow`` and ``artifact_state`` — the same sharing as
    ``routes._detail``'s, on the path that answers every export, answer and remove. It
    had no equivalence guard anywhere: this file never mentioned ``build_invalidation``,
    and the differential that covered it was an out-of-suite harness. So the same
    equality is asserted here, over the same shape set, at the level of the whole
    returned envelope rather than of the two derivations inside it.

    The un-threaded arm drops the keyword rather than passing ``units=None`` explicitly,
    because ``units=None`` IS the un-threaded default and dropping it is what every
    caller that does not share did before this change.
    """
    shapes = _all_shapes(client)
    assert len(shapes) == _SHAPE_COUNT, sorted(shapes)
    store = client_ws(client)
    real_post_workflow = dependencies._post_workflow
    real_artifact_state = dependencies.artifact_state

    for name, exp_id in shapes.items():
        exp = store.load_experiment(exp_id)
        pre_steps = routes._workflow_for(exp)["ordered_steps"]
        kwargs = dict(
            changed=True,
            changed_fields=["sample.sample_id"],
            pre_steps=pre_steps,
            post_exp=exp,
        )
        threaded = dependencies.build_invalidation(**kwargs)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                dependencies, "_post_workflow", lambda e, **kw: real_post_workflow(e)
            )
            patch.setattr(
                dependencies, "artifact_state", lambda e, **kw: real_artifact_state(e)
            )
            unthreaded = dependencies.build_invalidation(**kwargs)

        assert threaded == unthreaded, name
        # …and not vacuously: the envelope must be a real invalidation summary.
        assert {"changed", "rev", "reopened_steps", "artifact", "reason"} <= set(
            threaded
        ), name

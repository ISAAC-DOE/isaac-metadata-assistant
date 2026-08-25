"""``pending_count()`` must answer without building the list — pinned structurally.

WHY THIS FILE EXISTS. ``Experiment.pending_count`` was literally
``len(self.pending())``, and ``Experiment.pending`` builds one dict per open question
per run — plus, for a run whose draft predates ``routes._seed_for_new_run`` and so
carries no ``pending`` key, a ``copy.deepcopy`` of every entry of a freshly rebuilt
``blank_draft()``. The record-detail route reads FOUR integers out of that derivation
per request (``_summary``, ``_workflow_for``, ``status()``, ``export_ready()``), so one
``GET /api/experiments/{id}`` on a 1000-run record entered ``run_questions`` 4000 times
(``cProfile`` ``ncalls``) and constructed ~12 000 dictionaries, all discarded. The
response is **1464 bytes at any run count** — flat payload, linear time, which is the
signature of work being done and thrown away.

Measured in-process before and after, best-of, 1000 runs::

    pending_count()   seeded  0.717 ms -> 0.098 ms      legacy  8.183 ms -> 0.094 ms
    GET detail (route)                                  legacy  86.1 ms  -> 53.3 ms

**WHAT IS GUARDED HERE IS NOT THE TIMING.** A wall-clock assertion in the normal suite
is flaky under CPU contention, and this repository has already been bitten by exactly
that (``CLAUDE.md`` §7's benchmark note: run 1 launched 16 agents concurrently and its
wall-clock numbers are excluded from every verdict for that reason). So the normal-suite
guards are:

1. **The binding equality** ``pending_count() == len(pending())``, over every workload
   shape — zero-run, seeded, legacy, mixed, answered, partly answered, and a malformed
   non-dict entry, which ``pending()`` deliberately passes through as-is and which must
   therefore be COUNTED as one.
2. **A structural anti-scaling assertion**: the number of ``copy.deepcopy`` calls and
   ``blank_draft()`` builds made by ``pending_count()`` is IDENTICAL for a small and a
   large record. Equality rather than "small", so a future implementation that
   legitimately copies a constant amount still passes while any per-run materialisation
   fails.

The wall-clock benchmark is opt-in and lives at the bottom, behind
``ISAAC_PERF_BENCH=1``::

    ISAAC_PERF_BENCH=1 .venv/bin/pytest \\
      apps/api/tests/test_pending_count_is_not_materialised.py -q -s -k benchmark
"""

from __future__ import annotations

import copy
import json
import os
import time

import pytest

from isaac_api import experiment_repository as repo
from isaac_api import workspace as ws

# --- workload builders --------------------------------------------------------


def _experiment(draft: dict | None = None) -> ws.Experiment:
    """A bare in-memory experiment. NOT persisted: every property under test is a
    property of the derivation, so the store is not part of the subject."""
    return ws.Experiment(
        id="01PENDINGCOUNTGUARD00000000",
        title="pending-count guard",
        created_utc="2026-08-24T00:00:00Z",
        source={},
        draft=repo.blank_draft() if draft is None else draft,
    )


def _seeded_draft() -> dict:
    """What ``routes._seed_for_new_run`` leaves on a run: the ``pending`` KEY PRESENT."""
    return {"pending": [copy.deepcopy(e) for e in repo.blank_draft()["pending"]]}


def _legacy_draft() -> dict:
    """A LEGACY run: no ``pending`` key at all.

    This is the durable state ``ws.run_questions`` was made public for — ``new_run``
    defaulted a run's draft to ``{}`` until ``_seed_for_new_run`` shipped, so every run
    created before that deploy is still an empty-drafted run in PostgreSQL. Built the
    way the existing legacy-run tests build it (``_legacy_run(..., draft={})``).
    """
    return {}


def _with_runs(n: int, *, legacy: bool, draft: dict | None = None) -> ws.Experiment:
    exp = _experiment(draft)
    for i in range(n):
        exp.add_run(
            label=f"Run {i + 1}",
            draft=_legacy_draft() if legacy else _seeded_draft(),
            id=f"01RUNPENDINGCOUNTGUARD{i:04d}",
        )
    return exp


# --- 1. the binding equality --------------------------------------------------


def _assert_parity(exp: ws.Experiment, note: str) -> int:
    """``pending_count() == len(pending())``, and neither is accidentally zero-vs-zero
    in a way that would let both derivations be broken and still agree."""
    listed = exp.pending()
    counted = exp.pending_count()
    assert counted == len(listed), f"{note}: count {counted} != len(list) {len(listed)}"
    return counted


@pytest.mark.parametrize("n", [0, 1, 2, 7])
@pytest.mark.parametrize("legacy", [False, True])
def test_the_count_equals_the_length_of_the_list(n: int, legacy: bool):
    """THE INVARIANT, across run counts and across both run shapes.

    Non-trivial in both directions: with runs the record's own run-level questions are
    WITHHELD (``pending``'s long comment — the condition is ``self.runs``, not "some run
    still carries this kind", and the second version was a measured defect), so the
    count is not ``own + 3n``; and a legacy run's questions come from the template
    rather than from its draft, so it is not ``own`` either.
    """
    exp = _with_runs(n, legacy=legacy)
    counted = _assert_parity(exp, f"n={n} legacy={legacy}")
    # A record with no runs is its own record and keeps all three of its own
    # questions; the moment a run exists they are withheld and each run owes three.
    assert counted == (3 if n == 0 else 3 * n), counted


def test_the_count_equals_the_length_for_a_mixed_record():
    """Seeded and legacy runs on ONE record — the shape a deploy actually produces."""
    exp = _experiment()
    for i in range(4):
        exp.add_run(
            label=f"Run {i + 1}",
            draft=_legacy_draft() if i % 2 else _seeded_draft(),
            id=f"01RUNMIXEDPENDINGCOUNT{i:04d}",
        )
    assert _assert_parity(exp, "mixed") == 12


def test_the_count_equals_the_length_for_answered_and_partly_answered_runs():
    """``pending: []`` (key present, empty) is how ``run_questions`` distinguishes
    ANSWERED from NEVER ASKED, and a partly-answered run is the ordinary mid-flow
    state. Both must count as what they list."""
    exp = _experiment()
    exp.add_run(label="answered", draft={"pending": []}, id="01RUNANSWERED000000000000")
    partly = _seeded_draft()
    partly["pending"] = [e for e in partly["pending"] if e.get("kind") != "qc"]
    exp.add_run(label="partly", draft=partly, id="01RUNPARTLY0000000000000")
    exp.add_run(label="legacy", draft=_legacy_draft(), id="01RUNLEGACYMIX0000000000")
    assert _assert_parity(exp, "answered/partly/legacy") == 0 + 2 + 3


def test_the_count_equals_the_length_for_malformed_entries():
    """A NON-DICT ENTRY IS COUNTED AS ONE, because ``pending()`` passes it through
    as-is rather than wrapping or dropping it — "this is a derived view, not a place to
    start repairing documents". A count that silently skipped it would disagree with
    every surface that renders the list."""
    own = repo.blank_draft()
    own["pending"] = [*own["pending"], "a malformed persisted entry", None, 7]
    assert _assert_parity(_experiment(own), "malformed, no runs") == 6

    exp = _with_runs(2, legacy=True, draft=own)
    # The three run-level entries of the record's own list are withheld; the three
    # malformed ones are not run-level (``blocker_is_run_level`` is fail-closed on a
    # non-dict) so they survive, plus three questions per legacy run.
    assert _assert_parity(exp, "malformed, with runs") == 3 + 6


def test_a_non_list_pending_document_counts_the_same_way_the_list_does():
    """EXACT-EQUIVALENCE ON A BROKEN DOCUMENT, which is the input least able to
    survive two disagreeing derivations. ``pending()`` does ``list(...)`` on whatever
    is stored, so a dict yields its KEYS; the count must agree rather than
    special-case."""
    own = repo.blank_draft()
    own["pending"] = {"one": {}, "two": {}}
    assert _assert_parity(_experiment(own), "dict pending, no runs") == 2
    assert _assert_parity(_with_runs(1, legacy=True, draft=own), "dict pending, runs") == 5


def test_run_question_count_mirrors_run_questions_branch_for_branch():
    """The per-run half of the invariant, asserted on its own so a failure localises."""
    for label, draft in (
        ("legacy", _legacy_draft()),
        ("seeded", _seeded_draft()),
        ("answered", {"pending": []}),
        ("non-dict draft", None),
        ("dict pending", {"pending": {"a": 1, "b": 2}}),
    ):
        run = ws.new_run("01EXP", ordinal=1, draft=draft)
        if label == "non-dict draft":
            object.__setattr__(run, "draft", "not a dict")
        assert ws.run_question_count(run) == len(ws.run_questions(run)), label


# --- 2. the structural anti-scaling guard -------------------------------------


class _Counter:
    def __init__(self) -> None:
        self.deepcopy = 0
        self.blank_draft = 0
        self.run_questions = 0


@pytest.fixture()
def counted(monkeypatch) -> _Counter:
    """Count the three things a per-run materialisation cannot avoid doing.

    Patched in ``workspace``'s own namespace (and on ``experiment_repository``, which
    ``run_questions`` imports lazily) so this measures what the module under test
    actually calls, not what some other module does.
    """
    c = _Counter()
    real_deepcopy = copy.deepcopy
    real_blank = repo.blank_draft
    real_questions = ws.run_questions

    def spy_deepcopy(*a, **k):
        c.deepcopy += 1
        return real_deepcopy(*a, **k)

    def spy_blank(*a, **k):
        c.blank_draft += 1
        return real_blank(*a, **k)

    def spy_questions(*a, **k):
        c.run_questions += 1
        return real_questions(*a, **k)

    monkeypatch.setattr(ws.copy, "deepcopy", spy_deepcopy)
    monkeypatch.setattr(repo, "blank_draft", spy_blank)
    monkeypatch.setattr(ws, "run_questions", spy_questions)
    return c


SMALL, LARGE = 8, 512


@pytest.mark.parametrize("legacy", [False, True])
def test_pending_count_does_not_scale_its_work_with_the_run_count(counted, legacy):
    """THE GUARD. Not "is it fast" but "is the work per run zero".

    ``pending_count()`` is run over a small and a large record and the three counters
    must be IDENTICAL. Equality rather than a ceiling, deliberately: an implementation
    that copies a constant amount once still passes, while any implementation whose
    cost is per-run fails — including the original ``len(self.pending())``, which for
    ``LARGE`` legacy runs made 512 ``blank_draft()`` builds and 1536 deep copies.

    BOTH RECORDS ARE BUILT BEFORE ANY COUNTING STARTS, and that is not tidiness —
    ``_seeded_draft()`` calls ``blank_draft()`` and ``new_run`` deep-copies the draft it
    is handed, so construction alone is legitimately per-run and would have swamped the
    signal. The template cache is warmed for the same reason: its one-time build must
    not be mistaken for per-run work in whichever parametrisation runs first.
    """
    ws._run_level_template()  # warm; the cache is a per-process derivation
    small_exp = _with_runs(SMALL, legacy=legacy)
    large_exp = _with_runs(LARGE, legacy=legacy)
    small_exp.pending_count()  # warm any one-time lazy import on the read path
    counted.deepcopy = counted.blank_draft = counted.run_questions = 0

    small_exp.pending_count()
    small = (counted.deepcopy, counted.blank_draft, counted.run_questions)
    counted.deepcopy = counted.blank_draft = counted.run_questions = 0

    large_exp.pending_count()
    large = (counted.deepcopy, counted.blank_draft, counted.run_questions)

    assert small == large, (
        f"pending_count()'s work scales with the run count: {SMALL} runs -> "
        f"{small} (deepcopy, blank_draft, run_questions), {LARGE} runs -> {large}"
    )
    # And the strongest available statement of the same property: it does not enter
    # the list builder at all.
    assert large == (0, 0, 0), large


def test_run_questions_does_not_rebuild_the_blank_draft_per_call(counted):
    """HYPOTHESIS (2)'s other half. ``pending()`` still returns N x 3 entries — that
    is its contract and it is inherently linear — but the TEMPLATE it derives a legacy
    run's questions from is a constant, and it was being rebuilt once per run.

    So this guards the template derivation, not the output size: ``blank_draft()`` is
    built at most once no matter how many legacy runs are listed.
    """
    ws._run_level_template()
    exp = _with_runs(LARGE, legacy=True)  # BUILT FIRST — see the guard above
    counted.blank_draft = 0
    assert len(exp.pending()) == 3 * LARGE
    assert counted.blank_draft == 0, (
        f"blank_draft() was rebuilt {counted.blank_draft} times while listing "
        f"{LARGE} legacy runs' questions"
    )


# --- 3. the safety property the deepcopy was there for ------------------------


def test_a_legacy_runs_questions_are_owned_outright_by_their_caller():
    """THE REASON THE COPY EXISTS, pinned so the fast path cannot quietly drop it.

    ``routes._apply_to_run`` MATERIALISES ``ws.run_questions(run)`` into the run's
    draft and writes it, and ``complete.apply_answers`` then mutates that list — so a
    caller receiving the module-level template's own objects would corrupt the template
    for every later run and every later request. ``json.loads`` of a pre-serialised
    payload gives the same guarantee ``copy.deepcopy`` gave; this asserts the guarantee
    rather than the mechanism.
    """
    a_run = ws.new_run("01EXP", ordinal=1, draft=_legacy_draft())
    b_run = ws.new_run("01EXP", ordinal=2, draft=_legacy_draft())
    a, b = ws.run_questions(a_run), ws.run_questions(b_run)
    assert a == b and a is not b

    descriptor = next(e for e in a if e["kind"] == "descriptor")
    other = next(e for e in b if e["kind"] == "descriptor")
    assert descriptor is not other
    assert descriptor["evidence"] is not other["evidence"], "NESTED containers are shared"

    # Mutate one caller's copy the way a writer does, at both levels.
    descriptor["evidence"].append({"source_type": "user_confirmation"})
    descriptor["question"] = "rewritten"
    a.clear()

    assert ws.run_questions(b_run) == b, "one caller's mutation reached another's"
    fresh = ws.run_questions(ws.new_run("01EXP", ordinal=3, draft=_legacy_draft()))
    assert fresh == b, "one caller's mutation reached the shared template"


def test_the_cached_template_equals_a_freshly_derived_one():
    """The precondition the JSON fast path rests on, checked as a TEST as well as at
    build time: the round-trip must be lossless for this data. A tuple would come back
    a list and a non-string key a string, so if ``blank_draft()`` ever stops being JSON
    literals this fails here rather than silently changing a persisted document."""
    entries, payload = ws._run_level_template()
    fresh = [e for e in repo.blank_draft()["pending"] if ws.blocker_is_run_level(e)]
    assert entries == fresh
    assert payload is not None, "the fast path was disabled; the round-trip is lossy"
    assert json.loads(payload) == fresh
    assert {e["kind"] for e in fresh} == {"series", "qc", "descriptor"}, fresh


# --- 4. the opt-in benchmark --------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("ISAAC_PERF_BENCH") != "1",
    reason="wall-clock benchmark; opt in with ISAAC_PERF_BENCH=1 (see module docstring)",
)
@pytest.mark.parametrize("legacy", [False, True])
def test_benchmark_pending_count(legacy, capsys):
    """PRINTS a table; ASSERTS NOTHING ABOUT TIME.

    Deliberately not a threshold. A wall-clock assertion in CI is flaky under CPU
    contention and this repository has already had measurements contaminated that way
    (``CLAUDE.md`` §7). The only assertion is the invariant, which is true regardless
    of how loaded the machine is.
    """
    rows = []
    for n in (25, 100, 250, 500, 1000):
        exp = _with_runs(n, legacy=legacy)
        best_count = best_list = float("inf")
        for _ in range(5):
            t0 = time.perf_counter()
            counted = exp.pending_count()
            best_count = min(best_count, time.perf_counter() - t0)
            t0 = time.perf_counter()
            listed = len(exp.pending())
            best_list = min(best_list, time.perf_counter() - t0)
        assert counted == listed
        rows.append((n, best_count * 1e3, best_list * 1e3))
    with capsys.disabled():
        kind = "legacy" if legacy else "seeded"
        print(f"\n{kind}: {'runs':>6} {'pending_count ms':>18} {'pending ms':>12}")
        for n, c, lst in rows:
            print(f"{kind}: {n:>6} {c:>18.3f} {lst:>12.3f}")

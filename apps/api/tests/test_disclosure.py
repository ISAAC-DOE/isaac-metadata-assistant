"""Tests for minimum-cell-size suppression.

This module is privacy-critical, so the tests are written to fail loudly rather
than to confirm a happy path.

The attack under test is **differencing against a public universe**, not "a cell
of 1 is small". The keys of these histograms are schema paths, rule families and
JSON pointers — all derivable from ``schema/isaac_record_v1.json``, which is
vendored, public and published upstream. So an observer never needs us to name
the withheld key: they enumerate the schema, diff it against the published
cells, and the missing key is the withheld one. If exactly ONE key is withheld,
``suppressed_total`` is that key's exact count, and the floor bought nothing.

The absorption loop is therefore the load-bearing behaviour in the module, and
most of this file is about it — including the worked example the authorizing
prompt specified, the proof that "never exactly one" cannot be reached from any
input with two or more keys, and the honest pin on the one degenerate input
where it *can* be reached.

Nothing here reads a record, a schema, a database or a network. The count maps
are literals and generated integers.
"""

from __future__ import annotations

import itertools
import random

import pytest

from isaac_api.disclosure import (
    MIN_CELL_SIZE,
    SuppressedHistogram,
    suppress_small_cells,
)


# =============================================================================
# The contract's basic shape
# =============================================================================


def test_the_default_floor_is_a_documented_placeholder_not_a_ruling():
    """The value 5 is the conventional statistical-disclosure default. The
    matrix (§4.3.1) requires *a* floor and does not fix its value; the value is
    question (c) of Q19 in ``docs/dean-authorization-packet.md``, UNANSWERED.
    Pinned so a change is a decision, not a drift."""
    assert MIN_CELL_SIZE == 5


def test_empty_input_publishes_nothing_and_withholds_nothing():
    """An empty histogram is not an error and not a suppression."""
    result = suppress_small_cells({})
    assert result == SuppressedHistogram(
        cells=(), suppressed_categories=0, suppressed_total=0, floor=MIN_CELL_SIZE
    )


def test_the_floor_actually_applied_is_echoed_back():
    """A reader must never have to assume the default was in force."""
    assert suppress_small_cells({}, floor=9).floor == 9
    assert suppress_small_cells({"a": 100}).floor == MIN_CELL_SIZE


def test_every_cell_at_or_above_the_floor_is_published_and_nothing_is_withheld():
    """The no-op case. ``suppressed_categories == 0`` must mean exactly that:
    nothing was withheld. It must never be a rounding of "we withheld something
    but would rather not say"."""
    result = suppress_small_cells({"a": 10, "b": 6, "c": 5})
    assert result.cells == (("a", 10), ("b", 6), ("c", 5))
    assert result.suppressed_categories == 0
    assert result.suppressed_total == 0


def test_the_floor_is_inclusive():
    """``count >= floor`` publishes. A cell exactly at the floor is safe by
    definition of the floor; excluding it would be a silently different (and
    undocumented) rule."""
    at_floor = suppress_small_cells({"a": 5, "b": 5, "c": 5}, floor=5)
    assert at_floor.suppressed_categories == 0
    assert [count for _, count in at_floor.cells] == [5, 5, 5]

    below = suppress_small_cells({"a": 5, "b": 5, "c": 5}, floor=6)
    assert below.cells == ()
    assert below.suppressed_categories == 3


def test_a_single_large_cell_is_published_and_is_not_the_dangerous_case():
    """One key with a huge count is ABOVE the floor, so there is nothing to
    suppress and nothing to absorb. ``suppressed_categories == 0`` here is
    correct and is NOT the one-withheld-category case — the dangerous shape is a
    single key BELOW the floor, pinned separately below."""
    result = suppress_small_cells({"only": 10_000})
    assert result.cells == (("only", 10_000),)
    assert result.suppressed_categories == 0
    assert result.suppressed_total == 0


def test_cells_are_sorted_by_descending_count_then_by_key():
    """A total order that never depends on input iteration order, so the same
    counts always render the same way regardless of how the map was built."""
    counts = {"zebra": 7, "alpha": 7, "middle": 9, "omega": 7}
    result = suppress_small_cells(counts)
    assert result.cells == (("middle", 9), ("alpha", 7), ("omega", 7), ("zebra", 7))

    # Same content, different insertion order → identical output.
    reordered = {"omega": 7, "middle": 9, "zebra": 7, "alpha": 7}
    assert suppress_small_cells(reordered) == result


def test_the_published_and_withheld_counts_always_reconcile_to_the_input():
    """Nothing is invented and nothing evaporates: published + withheld == total,
    and published categories + withheld categories == the number of keys."""
    counts = {"a": 20, "b": 11, "c": 4, "d": 2, "e": 9}
    result = suppress_small_cells(counts)
    assert sum(c for _, c in result.cells) + result.suppressed_total == sum(counts.values())
    assert len(result.cells) + result.suppressed_categories == len(counts)


# =============================================================================
# THE ABSORPTION LOOP — the differencing defence
# =============================================================================


def test_the_worked_example_from_the_specification():
    """``{a: 10, b: 9, c: 1}`` — the case the whole loop exists for.

    Trace, step by step:

    1. Initial pass at floor 5: ``a=10`` and ``b=9`` publish; ``c=1`` is
       withheld. ``suppressed_categories == 1``.
    2. That is the leak. The key universe is public, so an observer diffs it
       against the published cells, finds ``c`` missing, and reads
       ``suppressed_total == 1`` as ``c``'s exact count.
    3. Absorption: the smallest published cell by ``(count, key)`` ascending is
       ``b=9``. It moves into the withheld bucket.
    4. ``suppressed_categories == 2``; the loop stops.

    Result: ``cells == (("a", 10),)``, two categories withheld, total 10. The
    observer now knows only that ``b + c == 10`` with ``c < 5``.
    """
    result = suppress_small_cells({"a": 10, "b": 9, "c": 1})
    assert result.cells == (("a", 10),)
    assert result.suppressed_categories == 2
    assert result.suppressed_total == 10
    assert result.floor == 5


def test_absorption_takes_the_smallest_published_cell_not_an_arbitrary_one():
    """Absorbing the smallest cell loses the least information. Absorbing the
    largest would be safe too, and much more destructive."""
    result = suppress_small_cells({"big": 100, "mid": 20, "small": 6, "tiny": 1})
    assert result.cells == (("big", 100), ("mid", 20))
    assert result.suppressed_categories == 2
    assert result.suppressed_total == 7  # small(6) + tiny(1)


def test_absorption_ties_break_on_the_key_ascending():
    """Two published cells with equal counts must resolve deterministically, or
    the same input would publish different histograms on different runs."""
    counts = {"beta": 8, "alpha": 8, "gamma": 20, "tiny": 2}
    result = suppress_small_cells(counts)
    assert result.cells == (("gamma", 20), ("beta", 8))
    assert result.suppressed_categories == 2
    assert result.suppressed_total == 10  # alpha(8) + tiny(2)

    # Deterministic across insertion orders and across repeated calls.
    for permutation in itertools.permutations(counts.items()):
        assert suppress_small_cells(dict(permutation)) == result


def test_absorption_consuming_every_cell_publishes_nothing_and_is_not_an_error():
    """``{a: 10, c: 1}`` — the fail-closed outcome.

    ``c`` is withheld alone, so ``a`` is absorbed, which leaves no published
    cells. Publishing nothing is the CORRECT answer, not a failure: the
    alternative is publishing a cell from which the withheld one is recoverable.
    No exception, no sentinel, no partial result.
    """
    result = suppress_small_cells({"a": 10, "c": 1})
    assert result.cells == ()
    assert result.suppressed_categories == 2
    assert result.suppressed_total == 11


def test_absorption_is_not_triggered_when_two_categories_are_already_withheld():
    """The loop must not over-absorb. Two withheld categories already defeat
    the single-key differencing attack, so a third is gratuitous data loss."""
    result = suppress_small_cells({"a": 30, "b": 20, "c": 2, "d": 1})
    assert result.cells == (("a", 30), ("b", 20))
    assert result.suppressed_categories == 2
    assert result.suppressed_total == 3


def test_absorption_can_need_only_one_pass_but_the_condition_is_re_evaluated():
    """The loop is a ``while``, not an ``if``. One absorption always lifts the
    count from 1 to 2, so a second pass never fires — but the condition is
    re-evaluated rather than assumed, so a future change to the absorption rule
    (for example absorbing into a floor rather than one cell at a time) cannot
    leave a single withheld category behind unnoticed."""
    result = suppress_small_cells({"a": 50, "b": 40, "c": 30, "d": 1})
    assert result.suppressed_categories == 2
    assert result.cells == (("a", 50), ("b", 40))


def test_a_zero_count_cell_is_withheld_and_the_weakness_that_creates_is_pinned():
    """A KNOWN WEAKNESS, recorded rather than hidden.

    A key present in the input with a count of ``0`` is below any legal floor,
    so it is withheld and it counts toward ``suppressed_categories``. That can
    satisfy the ``>= 2`` condition without adding real uncertainty: an observer
    who reasons that a zero cell contributes nothing to ``suppressed_total`` is
    back to nearly one withheld key.

    The module docstring says so and tells callers not to construct count maps
    with explicit zero cells — build them from observations only. This test
    exists so that instruction has a failing consequence if the behaviour is
    ever changed without changing the documentation.
    """
    result = suppress_small_cells({"a": 10, "b": 9, "zero": 0})
    assert result.suppressed_categories == 2
    assert result.suppressed_total == 9, (
        "the zero cell contributes nothing to the total, which is precisely why "
        "it adds little real uncertainty"
    )
    # The absorption still ran (`b` was taken), because at the initial pass only
    # `zero` was withheld.
    assert result.cells == (("a", 10),)


# =============================================================================
# THE INVARIANT: suppressed_categories is never exactly 1
# =============================================================================


def _random_count_map(rng: random.Random) -> dict[str, int]:
    size = rng.randint(0, 12)
    return {
        f"key_{index:02d}": rng.choice([0, 1, 1, 2, 3, 4, 4, 5, 5, 6, 9, 17, 40, 1000])
        for index in range(size)
    }


@pytest.mark.parametrize("seed", range(60))
def test_property_suppressed_categories_is_never_exactly_one(seed):
    """THE INVARIANT, over generated count maps.

    ``suppressed_categories == 1`` is the leak: one withheld key against a
    publicly enumerable universe is identified by elimination, and its exact
    count is then ``suppressed_total``.

    The invariant holds ABSOLUTELY for every input with two or more keys. There
    is exactly one reachable exception — a map with a SINGLE key whose count is
    below the floor — and it is carved out here explicitly, asserted to be
    accompanied by an empty ``cells`` tuple, and pinned in its own test below.
    A carve-out that silently widened would fail here, because the condition is
    stated as an implication over ``len(counts)``, not as a skip.
    """
    rng = random.Random(seed)
    for floor in (1, 2, 5, 7):
        counts = _random_count_map(rng)
        result = suppress_small_cells(counts, floor=floor)

        if len(counts) >= 2:
            assert result.suppressed_categories != 1, (
                f"the differencing defence failed: exactly one category was "
                f"withheld from a {len(counts)}-key map at floor {floor}. "
                f"counts={counts}"
            )
        else:
            assert result.suppressed_categories != 1 or result.cells == (), (
                "the single-key exception must always publish zero cells; a "
                "published cell alongside one withheld category is the attack"
            )

        # Conservation holds regardless.
        assert (
            sum(c for _, c in result.cells) + result.suppressed_total
            == sum(counts.values())
        )


@pytest.mark.parametrize("floor", [1, 2, 5, 7, 100])
def test_the_invariant_holds_over_an_exhaustive_small_sweep(floor):
    """Exhaustive rather than random, over every count vector in ``0..6`` for
    two and three keys. Small enough to enumerate, large enough to cross every
    floor boundary."""
    for size in (2, 3):
        for vector in itertools.product(range(7), repeat=size):
            counts = {f"k{i}": v for i, v in enumerate(vector)}
            result = suppress_small_cells(counts, floor=floor)
            assert result.suppressed_categories != 1, (counts, floor, result)


def test_the_one_degenerate_case_the_module_cannot_fix_is_pinned_here():
    """THE HONEST HOLE, with its proof of uniqueness.

    A map with a single sub-floor key has no published cell to absorb, so the
    loop cannot run and ``suppressed_categories`` stays at 1. The observer, who
    knows the universe, learns that key's exact count from ``suppressed_total``.

    The module does NOT paper over this. Reporting ``0`` withheld would be a
    false claim; zeroing ``suppressed_total`` would be a differently false
    claim. The honest numbers are returned and **the caller must not publish a
    histogram whose universe is a single key** — no floor can anonymise a
    one-cell aggregate, because the aggregate *is* the cell.

    Uniqueness, re-derived rather than asserted: with ``n >= 2`` keys,
    ``suppressed_categories == 1`` implies ``n - 1 >= 1`` published cells remain,
    so the loop condition holds and it absorbs again. Termination at 1 therefore
    forces ``n == 1``. The exhaustive sweep above measures the ``n in (2, 3)``
    half of that.
    """
    result = suppress_small_cells({"lonely": 3})
    assert result.cells == ()
    assert result.suppressed_categories == 1
    assert result.suppressed_total == 3, (
        "the count is reported truthfully. If this ever returns 0, the module "
        "started lying to look safe — read the module docstring before changing it."
    )


# =============================================================================
# Input validation — and the rule that a refusal must not leak either
# =============================================================================


def test_a_floor_below_one_is_refused():
    """A floor of 0 suppresses nothing (counts are non-negative), so it would
    present the ABSENCE of suppression as suppression — the silent-half-fix
    shape this project refuses on principle."""
    for bad in (0, -1, -5):
        with pytest.raises(ValueError):
            suppress_small_cells({"a": 1}, floor=bad)


def test_a_non_integer_floor_is_refused():
    for bad in (5.0, "5", None, True):
        with pytest.raises(TypeError):
            suppress_small_cells({"a": 1}, floor=bad)


def test_negative_counts_are_refused():
    """A negative count is not a histogram cell. Silently clamping it would make
    ``suppressed_total`` and the conservation property meaningless."""
    with pytest.raises(ValueError):
        suppress_small_cells({"a": 10, "b": -1})


def test_non_string_keys_and_non_integer_counts_are_refused():
    with pytest.raises(TypeError):
        suppress_small_cells({1: 10})
    with pytest.raises(TypeError):
        suppress_small_cells({"a": 1.5})
    with pytest.raises(TypeError):
        suppress_small_cells({"a": "10"})


def test_a_boolean_count_is_refused_because_true_would_silently_be_one():
    """``bool`` is an ``int`` subclass. ``{"a": True}`` counting as ``{"a": 1}``
    is a footgun, not a feature."""
    with pytest.raises(TypeError):
        suppress_small_cells({"a": True})


def test_a_refusal_message_never_echoes_the_key_or_the_value():
    """THE ERROR PATH IS A LEAK PATH, and this module is downstream of record
    content: its keys can be JSON pointers or map keys drawn from a record.

    This is the same failure ``corpus_mutation.FAILURE_STATUSES`` exists to
    prevent — an earlier version of ``build_failure_report`` echoed its argument,
    and the natural caller would have passed ``str(exc)``. So the exceptions
    raised here name the CONSTRAINT and never the offending datum.
    """
    canary_key = "SECRET-CANARY-KEY"
    canary_value = -987654321

    with pytest.raises(ValueError) as negative:
        suppress_small_cells({canary_key: canary_value})
    assert canary_key not in str(negative.value)
    assert str(canary_value) not in str(negative.value)

    with pytest.raises(TypeError) as wrong_type:
        suppress_small_cells({canary_key: canary_key})
    assert canary_key not in str(wrong_type.value)


def test_the_input_mapping_is_not_modified():
    """A caller's histogram must survive the call unchanged — this function is
    a projection, not a filter applied in place."""
    counts = {"a": 10, "b": 9, "c": 1}
    snapshot = dict(counts)
    suppress_small_cells(counts)
    assert counts == snapshot


def test_the_result_is_frozen_and_hashable():
    """``SuppressedHistogram`` is a frozen dataclass of tuples, so a caller
    cannot mutate a published histogram after the suppression decision was
    made."""
    result = suppress_small_cells({"a": 10, "b": 9, "c": 1})
    with pytest.raises(Exception):
        result.cells = ()  # type: ignore[misc]
    assert hash(result) == hash(suppress_small_cells({"a": 10, "b": 9, "c": 1}))

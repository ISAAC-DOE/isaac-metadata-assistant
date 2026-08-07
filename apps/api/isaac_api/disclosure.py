"""Minimum-cell-size suppression for aggregate histograms.

WHY THIS EXISTS
===============
``docs/superpowers/plans/2026-08-02-corpus-validation-authorization.md`` §3
records the finding, and it is blunt: *"There is no minimum-cell-size
suppression anywhere in the aggregation path"* — re-derivable with
``rg -n 'MIN_CELL|suppress' apps/api/isaac_api/db_recon.py
apps/api/isaac_api/routes.py``, which returned nothing. The baseline matrix
§4.3.1 requires one, because over a ~30-row corpus a cell of 1 *is* a
single-record fact wearing aggregate clothing. This module is that primitive.

It is a pure function over a count map. It reads no schema, opens no
connection, and knows nothing about records — it is deliberately ignorant of
what its keys mean, so it cannot be talked into a special case.

THE ATTACK IT DEFEATS, WHICH IS NOT THE OBVIOUS ONE
===================================================
The obvious threat is "a cell of 1 identifies one record", and a floor handles
that. The subtle threat is **differencing against a public universe**, and a
plain floor does NOT handle it:

    The key set is *knowable*. These histograms are keyed by schema paths, rule
    families, and JSON pointers — all derivable from
    ``schema/isaac_record_v1.json``, which is vendored, public, and published
    upstream. So an observer does not need us to name the withheld key. They
    enumerate the schema, diff it against the published ``cells``, and the
    missing key is the withheld one. If exactly ONE key is withheld,
    ``suppressed_total`` is then *that key's exact count*.

Suppression that hides the key while publishing the count is worthless when the
key set is knowable by elimination. So :func:`suppress_small_cells` runs an
**absorption loop**: while exactly one category is withheld and any published
cell remains, the smallest published cell is absorbed into the withheld bucket.
Ties break on the key, ascending, so the outcome is deterministic and does not
depend on dict ordering. It repeats — absorbing one cell can leave the count at
two and stop, or the newly absorbed cell can itself be the only sub-floor member
of nothing; the loop condition is re-evaluated each pass.

Absorption is **lossy on purpose**. Publishing less than the floor permits is
always safe; publishing a recoverable single cell is not. If absorption consumes
every cell, the result publishes nothing. That is the correct fail-closed
outcome, not an error, and it is not signalled by an exception.

THE ONE CASE THIS CANNOT FIX, STATED RATHER THAN HIDDEN
=======================================================
``suppressed_categories == 1`` is reachable for exactly one shape of input: a
map with a **single** key whose count is below the floor. There is then no
published cell to absorb, the loop cannot run, and the result is
``cells=()`` with ``suppressed_categories=1`` and the true
``suppressed_total``. An observer who knows the universe learns that key's exact
count.

The proof that this is the ONLY reachable case is short and is re-derived by
``test_disclosure.py``: with *n* ≥ 2 keys, ``suppressed_categories == 1`` implies
``n - 1 ≥ 1`` published cells remain, so the loop condition holds and it absorbs
again. Termination at 1 therefore forces ``n == 1``.

This module does not paper over it. It does not report ``0`` withheld (a false
claim), and it does not zero ``suppressed_total`` (a differently false claim).
**The caller is responsible for not publishing a histogram whose universe is a
single key** — no floor can make a one-cell aggregate anonymous, because the
aggregate *is* the cell. :func:`suppress_small_cells` returns the honest numbers
and the caller withholds the whole block.

WHAT IS NOT DEFENDED
====================
* **Repeated queries over changing data.** This is a stateless per-call
  primitive. It has no query budget and no memory of what it published last
  time; a caller that serves the same histogram as the corpus evolves can be
  differenced across time. Baseline matrix §4.3.3's absolute prohibition on
  caller-parameterized aggregation exists partly for this reason.
* **Cross-tabulation.** Matrix §4.3.2: adding a dimension to a breakdown is not
  a free extension of it. A 2-D table can satisfy the floor in every cell and
  still identify a record through its margins. This function sees one dimension
  and cannot know it is a slice of a bigger table.
* **A zero-count key padding the withheld bucket.** A key present in the input
  with a count of 0 is below the floor, so it is withheld and it counts toward
  ``suppressed_categories`` — which can satisfy the ``>= 2`` condition without
  adding real uncertainty (the observer can reason that a zero cell contributes
  nothing to ``suppressed_total``). Two withheld keys, one known to be 0, is
  close to one withheld key. Do not construct count maps with explicit zero
  cells; build them from observations only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

__all__ = [
    "MIN_CELL_SIZE",
    "SuppressedHistogram",
    "suppress_small_cells",
]

#: The default floor. Matrix §4.3.1 requires a minimum cell size over the ~30-row
#: corpus but does not fix its value — that is question (c) of Q19 in
#: ``docs/dean-authorization-packet.md``, which is UNANSWERED. 5 is the
#: conventional statistical-disclosure default and is used here as a documented
#: placeholder, NOT as a ruling. If Dean answers with a different number, change
#: this constant; do not add a second one.
MIN_CELL_SIZE = 5


@dataclass(frozen=True)
class SuppressedHistogram:
    """A histogram safe to publish, plus an honest account of what was withheld.

    ``cells``
        ``(key, count)`` pairs that survived, sorted by ``(-count, key)`` — a
        total order that never depends on input iteration order.
    ``suppressed_categories``
        HOW MANY distinct keys were withheld. Never WHICH: naming them would
        undo the suppression, and the count is what a reader needs to know that
        the published cells are not the whole picture.
    ``suppressed_total``
        The sum of the withheld counts. Meaningful only alongside
        ``suppressed_categories >= 2`` — see the module docstring's account of
        the single-category case.
    ``floor``
        The floor actually applied, echoed so a reader never has to assume it
        was the default.
    """

    cells: tuple[tuple[str, int], ...]
    suppressed_categories: int
    suppressed_total: int
    floor: int


def _validated(counts: Mapping[str, int]) -> dict[str, int]:
    """Reject anything that is not a ``str -> non-negative int`` map.

    The refusal messages deliberately name NO key and NO value. Keys in these
    histograms can be JSON pointers or map keys drawn from record content, so an
    exception that echoed one would be a leak on the error path — the exact
    failure ``corpus_mutation.build_failure_report`` was rewritten to prevent
    (``FAILURE_STATUSES``: an earlier version echoed its argument, and the
    natural caller would have passed ``str(exc)``).

    ``bool`` is rejected even though it is an ``int`` subclass: ``True`` silently
    counting as 1 is a footgun, not a feature.
    """
    out: dict[str, int] = {}
    for key, value in counts.items():
        if not isinstance(key, str):
            raise TypeError("histogram keys must be str (offending key not echoed)")
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("histogram counts must be int (offending value not echoed)")
        if value < 0:
            raise ValueError("histogram counts must be non-negative (value not echoed)")
        out[key] = value
    return out


def suppress_small_cells(
    counts: Mapping[str, int], *, floor: int = MIN_CELL_SIZE
) -> SuppressedHistogram:
    """Suppress sub-floor cells, then defeat single-category differencing.

    Algorithm, in the order it runs:

    1. **Initial pass.** Every cell with ``count < floor`` is withheld; the rest
       are published.
    2. **Absorption loop.** While exactly one category is withheld AND at least
       one published cell remains, move the smallest published cell — ordered by
       ``(count, key)`` ascending, so ties are broken deterministically — into
       the withheld bucket. Re-check.
    3. Publish what is left, sorted by ``(-count, key)``.

    Outcomes worth naming, because each is a decision and not a fallout:

    * empty input → nothing published, nothing withheld, all zeros;
    * every cell at or above the floor → nothing withheld,
      ``suppressed_categories == 0``;
    * one key with a large count → it is above the floor and there is nothing to
      suppress, so it is published with ``suppressed_categories == 0``. This is
      NOT the dangerous single-category case; the dangerous one is a single key
      *below* the floor, which the module docstring treats at length;
    * absorption consuming every cell → zero published cells, fail-closed, no
      exception.

    ``floor`` must be at least 1. A floor of 0 (or less) would suppress nothing,
    because counts are non-negative — it would look like suppression and be
    none, which is the silent-half-fix shape this project refuses on principle.
    """
    if not isinstance(floor, int) or isinstance(floor, bool):
        raise TypeError("floor must be an int")
    if floor < 1:
        raise ValueError(
            "floor must be at least 1; a floor of 0 suppresses nothing and would "
            "present the absence of suppression as suppression"
        )

    validated = _validated(counts)

    published: dict[str, int] = {}
    suppressed: dict[str, int] = {}
    for key, value in validated.items():
        (published if value >= floor else suppressed)[key] = value

    # The differencing defence. Documented at length in the module docstring:
    # one withheld key against a publicly enumerable universe means the withheld
    # key is identified by elimination and its count is read off `suppressed_total`.
    while len(suppressed) == 1 and published:
        victim = min(published, key=lambda k: (published[k], k))
        suppressed[victim] = published.pop(victim)

    cells = tuple(
        (key, published[key])
        for key in sorted(published, key=lambda k: (-published[k], k))
    )
    return SuppressedHistogram(
        cells=cells,
        suppressed_categories=len(suppressed),
        suppressed_total=sum(suppressed.values()),
        floor=floor,
    )

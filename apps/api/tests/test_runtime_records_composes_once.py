"""``runtime_records._project_one`` composed the unit list four times and said "ONCE".

WHY THIS FILE EXISTS. The projection's own docstring read *"Each expensive derivation
(``status``, ``draft_ok``, ``export_ready``, ``classify_fields``) is computed exactly
ONCE — no value is recomputed within this record's projection."* Each of those is indeed
*called* once. Each of them independently COMPOSED the export-unit list and re-resolved
every run's draft underneath, and the sentence is the reason nobody looked. Measured on a
fully answered three-run fan-out::

    before   export_units 4   resolved_run_draft 12   export_draft 6   (2x the runs)
    after    export_units 1   resolved_run_draft  3   export_draft 3   (1x the runs)

``routes._detail`` closed exactly this in PR #176 (``_shared_units``) and PR #177
(``_shared_dry_run``). This projection is the site those slices did not reach, and PR
#179's residue list named it.

THE FIRST ATTEMPT REACHED 4 -> 2, NOT 4 -> 1, and this file pins the number rather than
the intent for that reason: threading the three derivations left ``artifact_state``
composing a second list, and only a stack trace found it. A test asserting "fewer than
before" would have passed over the half-fix. See
``test_the_projection_composes_the_unit_list_exactly_once``.

WHAT THIS FILE DELIBERATELY DOES NOT DO: assert a wall-clock figure. The counts are
contention-free by construction; a millisecond number measured on a loaded laptop is not,
and ``docs/evidence/scale-envelope-2026-08-25.md`` records what happens when the two are
reported with equal confidence.
"""

from __future__ import annotations

import json

from isaac_api import runtime_records

from conftest import client_ws  # noqa: F401  (fixture)
from test_detail_route_composes_each_run_once import (  # noqa: F401  (fixtures)
    _fan_out,
    client,
    counted,
)


def _answered_fan_out(client, counted):
    """A fully answered three-run fan-out, with the counters zeroed after setup."""
    store = client_ws(client)
    exp = _fan_out(store, "01RUNTIMEONCEANSWERED00000", ("Run A", "Run B", "Run C"))
    counted.resolved_run_draft = counted.export_units = counted.export_draft = 0
    return exp


def test_the_projection_composes_the_unit_list_exactly_once(client, counted):
    """ONE composition, and one resolved draft per run — not four and twelve.

    The exact numbers are asserted, not an inequality, because the half-fix that reached
    ``export_units == 2`` would satisfy any "fewer than before" assertion while leaving
    ``artifact_state`` composing its own list.
    """
    exp = _answered_fan_out(client, counted)
    assert exp.pending_count() == 0, exp.pending_count()

    runtime_records._project_one(exp)

    assert counted.export_units == 1, counted
    assert counted.resolved_run_draft == 3, counted
    # AND THE DRY RUN, WHICH IS THE LARGER TERM AND WHICH THE FIRST VERSION OF THIS FILE
    # DID NOT ASSERT. `status()` and `export_ready()` each dry-ran every unit, so
    # `export_draft` was 2x the run count; PR #177 measured that at roughly half a
    # detail request. Without this line, a seam that drops `dry_run_ok` on the way to
    # either consumer passes every other assertion here — verified: two such mutations
    # survived the four tests that preceded it.
    assert counted.export_draft == 3, counted


def test_a_pending_record_still_never_enters_the_dry_run(client, counted):
    """THE GATE, and it is the half that could have made the common case slower.

    ``dry_run_verdict`` answers ``None`` while ``pending_count() > 0``, which is exactly
    the union of ``status``'s and ``export_ready``'s short-circuits. A naive "derive it
    once up front" would have turned ZERO dry runs into N on every record that still owes
    questions — the common case — to speed up the rare one. ``export_draft`` must stay at
    0 here.
    """
    # Built through the STORE, not over HTTP: this file's `client` fixture is
    # tutorial-scoped, and `POST /api/experiments` correctly answers 409
    # `ordinary_scope_required` there. The record only has to still owe questions.
    store = client_ws(client)
    exp = store.create_experiment(
        "still pending", {"kind": "synthetic"}, {}, id="01RUNTIMEONCEPENDING000000"
    )
    for i, label in enumerate(("Run A", "Run B")):
        exp.add_run(label=label, id=f"01RUNTIMEPENDINGRUN{i:07d}")
    exp.save_versioned()
    exp = store.load_experiment("01RUNTIMEONCEPENDING000000")

    assert exp.pending_count() > 0, exp.pending_count()
    counted.resolved_run_draft = counted.export_units = counted.export_draft = 0

    runtime_records._project_one(exp)

    assert counted.export_draft == 0, counted


def test_the_projection_is_byte_identical_to_the_unthreaded_derivation(client, counted):
    """THE SAFETY PROOF. Sharing is only sound if the answer does not move.

    Compared as serialised JSON rather than field by field, so a key that appeared or
    disappeared would fail too — the same standard
    ``test_detail_route_composes_each_run_once.py`` holds the detail route to.
    """
    exp = _answered_fan_out(client, counted)

    threaded = runtime_records._project_one(exp)

    # The un-threaded derivation, written out rather than reached by patching, so this
    # cannot agree with the code by construction.
    from isaac_api.dependencies import artifact_state
    from isaac_api.workflow import derive_workflow

    pending = exp.pending_count()
    exported = exp.all_units_exported()
    workflow = derive_workflow(
        pending_count=pending,
        draft_ok=exp.draft_ok(),
        ready=exp.export_ready(),
        exported=exported,
        rev=exp.rev,
    )
    assert threaded["status"] == exp.status(), threaded["status"]
    assert threaded["pending_count"] == pending
    assert threaded["exported"] == exported
    assert threaded["artifact_state"] == artifact_state(exp)["state"]
    assert threaded["workflow"]["current_step"] == workflow["current_step"]

    assert json.dumps(threaded, sort_keys=True) == json.dumps(
        runtime_records._project_one(exp), sort_keys=True
    )


def test_nothing_is_stored_on_the_experiment(client, counted):
    """THREADED, NOT MEMOISED — and this is why.

    ``runtime_records`` is called in a loop over records a caller may have mutated, so a
    cache on the instance can be served stale. A second projection of the same object
    must do the same work, not less.
    """
    exp = _answered_fan_out(client, counted)

    runtime_records._project_one(exp)
    first = counted.export_units
    runtime_records._project_one(exp)

    assert counted.export_units == first * 2, counted
    assert not any(
        "unit" in name and not name.startswith("__") for name in vars(exp)
    ), sorted(vars(exp))


def test_a_false_verdict_reaches_the_projection_rather_than_being_re_derived(client, counted):
    """``dry_run_ok=False`` MUST NOT BE READ AS "not supplied", and THIS TEST EXISTS
    BECAUSE THE MUTATION THAT BREAKS IT SURVIVED THE FIRST FOUR.

    ``False`` and ``None`` are both falsy, so ``dry_run_ok or None`` — or the equivalent
    ``dry_run_ok or exp._all_units_pass_dry_run(...)`` inside a consumer — silently
    re-derives on every NEGATIVE verdict. That restores the doubling on exactly the
    records whose dry run fails, and does it invisibly, because re-deriving produces the
    same answer. Counting calls cannot see it; only a verdict that DISAGREES with the
    truth can.

    So the projection is handed a ``False`` that the record itself would contradict, and
    the projected ``status`` must be the one the ``False`` implies. The sibling assertion
    for ``routes._detail`` is
    ``test_detail_route_composes_each_run_once.py::test_a_threaded_false_verdict_is_honoured_rather_than_re_derived``;
    this file needed its own because the projection is a separate call path with its own
    seams, and the four tests above all passed with the defect present.
    """
    exp = _answered_fan_out(client, counted)
    units = exp.export_units()
    assert exp.dry_run_verdict(units=units) is True, "fixture must pass the dry run"

    # The two consumers, driven directly with a verdict that disagrees with the record.
    assert exp.status(units=units, dry_run_ok=False) == "in_review"
    assert exp.status(units=units, dry_run_ok=True) == "ready_to_export"
    assert exp.export_ready(units=units, dry_run_ok=False) is False
    assert exp.export_ready(units=units, dry_run_ok=True) is True

    # And through the projection itself, so a seam that drops the argument on the way is
    # caught too rather than only a consumer that mishandles it.
    projected = runtime_records._project_one(exp)
    assert projected["status"] == "ready_to_export", projected["status"]


def _answered_but_refused(client, counted):
    """A record with NOTHING pending whose dry run nonetheless FAILS.

    A malformed ``sha256`` on a run asset is a draft-validator refusal, not a blocking
    question, so ``pending_count()`` stays 0 and both consumers still REACH the dry run —
    which is the only state in which a mishandled ``False`` is observable at all.

    The experiment-level version of this does not work and the difference is worth
    recording: an asset appended to ``exp.draft`` left ``dry_run_verdict`` at ``True``,
    because for a fan-out the units are composed from RUN drafts. The fixture has to
    break what the units are actually built from.
    """
    store = client_ws(client)
    exp = _fan_out(store, "01RUNTIMEONCEREFUSED000000", ("Run A", "Run B"))
    for run in exp.runs:
        run.draft.setdefault("assets", []).append(
            {
                "asset_id": "a1",
                "sha256": "not-a-digest",
                "evidence": [{"kind": "user_confirmation", "answer": "x"}],
            }
        )
    exp.save_versioned()
    exp = store.load_experiment("01RUNTIMEONCEREFUSED000000")
    counted.resolved_run_draft = counted.export_units = counted.export_draft = 0
    return exp


def test_a_negative_verdict_is_threaded_rather_than_re_derived(client, counted):
    """``dry_run_ok=False`` MUST NOT BE READ AS "not supplied" — AND THE TWO MUTATIONS
    THAT BREAK THIS SURVIVED EVERY OTHER TEST IN THIS FILE.

    ``False`` and ``None`` are both falsy, so ``dry_run_ok or None`` in the projection —
    or ``dry_run_ok or self._all_units_pass_dry_run(...)`` inside a consumer — silently
    re-derives on every NEGATIVE verdict. That restores the doubling on exactly the
    records whose dry run fails, and does it invisibly, because re-deriving produces the
    same answer.

    **Both mutations are INERT on a passing record**, which is why the fully answered
    test above cannot see them: with ``dry_run_ok is True``, ``True or None`` is ``True``
    and an ``export_ready`` handed a true verdict returns before it ever looks at
    ``units``. Only a record that reaches the dry run AND fails it distinguishes
    threading from re-deriving. Verified: with this fixture, ``dry_run_ok or None``
    takes ``export_draft`` from 1 to 2 — one
    short-circuited dry run per consumer that re-derives.

    The status assertion is the second half — the projection must REPORT the refusal
    (``in_review``), not merely compute it cheaply.
    """
    exp = _answered_but_refused(client, counted)
    assert exp.pending_count() == 0, exp.pending_count()
    assert exp.dry_run_verdict(units=exp.export_units()) is False, "fixture must FAIL"
    counted.resolved_run_draft = counted.export_units = counted.export_draft = 0

    projected = runtime_records._project_one(exp)

    assert counted.export_units == 1, counted
    # ONE, NOT TWO, and the difference is `all()` being lazy: `_all_units_pass_dry_run`
    # stops at the first unit that fails, so a two-run refusal costs one `export_draft`
    # and not one per unit. This assertion was written as 2 and measured as 1 — recorded
    # rather than quietly corrected, because an expected number that happens to be
    # larger than the truth would still have caught the mutation and would still have
    # been wrong.
    assert counted.export_draft == 1, counted
    assert projected["status"] == "in_review", projected["status"]
    # The projection deliberately serves only `current_step` plus two booleans — no
    # `export_ready` key exists, and asserting one was my error, not a missing field.
    # `current_step` is what carries the refusal to a reader.
    assert projected["workflow"]["current_step"] != "export", projected["workflow"]

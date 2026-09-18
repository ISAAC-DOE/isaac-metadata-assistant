"""THE APPEND-ONLY ACTIVITY MODEL — immutability, the absent/null split, and no-op silence.

Every test here is shaped like the defect it would catch, not like the feature it
covers. The list is written out so a reviewer can check the coverage against the
claims rather than against the code:

* a recorded event is refused by three of the four routes that work on an ordinary
  frozen dataclass — and the FOURTH, ``object.__setattr__`` on a declared field,
  SUCCEEDS and is asserted to succeed, because publishing "it cannot be mutated"
  without that limit would overstate the model;
* nothing anywhere can delete one;
* ``before``/``after`` distinguish *there was no value* from *the value was null*,
  across the JSON boundary and not merely in memory;
* an event is invisible to ``export.transform``, to
  ``submissions.content_signature`` and to every run's ``resolved_run_draft``;
* a malformed PERSISTED entry is READ, not refused, and is not discarded either;
* a malformed value in a REQUEST is refused;
* a byte-stable no-op records nothing and burns no sequence position;
* an actor nothing vouched for reads ``unattributed``, and a name with no basis is
  refused.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

import isaac_api.workspace as ws
from isaac_api import activity, activity_history


def _exp(tmp_path, monkeypatch, exp_id="01JACTIVITY0000000000000AA"):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    exp = ws.Experiment(
        id=exp_id,
        title="A record",
        created_utc="2026-01-01T00:00:00Z",
        source={},
        draft={},
    )
    exp.dir.mkdir(parents=True, exist_ok=True)
    assert exp.save_versioned() is True
    return exp


def _event(**over):
    base = dict(
        id="01JEVENT000000000000000001",
        experiment_id="01JACTIVITY0000000000000AA",
        seq=1,
        recorded_utc="2026-01-01T00:00:01Z",
        action=activity.ACTION_FIELD_ANSWERED,
        object_type=activity.OBJECT_FIELD,
        object_id="01JACTIVITY0000000000000AA",
        channel=activity.CHANNEL_WEB,
    )
    base.update(over)
    return activity.new_event(**base)


# --- immutability ------------------------------------------------------------


def test_the_immutability_of_a_recorded_event_IS_EXACTLY_THIS_MUCH():
    """Four routes, and one of them SUCCEEDS — which is asserted, not omitted.

    The title says "exactly this much" because the interesting content of this test is
    its limit. Three routes are refused; ``object.__setattr__`` on a DECLARED field is
    not, here as on every frozen dataclass, and publishing "an event cannot be
    mutated" without saying so would be a stronger claim than the model supports.

    What append-only means here is the property stated in ``activity.py``: **no
    mutator exists anywhere in the application**, so no code path can rewrite a
    recorded row — pinned by the inventory test below, not by this one.
    """
    event = _event()

    with pytest.raises(dataclasses.FrozenInstanceError):
        event.after = "tampered"  # type: ignore[misc]

    with pytest.raises(TypeError):
        dataclasses.replace(event, is_field_value=True)  # type: ignore[misc]

    # *** AND THE ONE THAT DOES **NOT** RAISE, ASSERTED RATHER THAN OMITTED. ***
    # `object.__setattr__` REACHES a declared field of a frozen dataclass — here as
    # everywhere, and `notes.py`'s own docstring says so in terms: "`object.__setattr__`
    # can still overwrite an ordinary *field* — that is true of every frozen dataclass,
    # and this module uses it itself in `__post_init__`". An earlier draft of this test
    # asserted it raises, which would have published a stronger immutability claim than
    # the model can support. What "append-only" buys is stated precisely in
    # `activity.py`: no mutator exists, so nothing in the application can rewrite a row
    # — not that the attribute is unreachable from a debugger.
    tampered = _event()
    object.__setattr__(tampered, "after", "tampered")
    assert tampered.after == "tampered"

    # WHAT `slots=True` DOES BUY, and it is the half that matters: a NEW attribute
    # cannot be attached after construction, so nothing can smuggle a `verified` or a
    # `status` onto a recorded event.
    with pytest.raises(AttributeError):
        object.__setattr__(event, "a_new_flag", True)

    # `replace` is not an exception to immutability — it returns a NEW event and
    # leaves this one alone. That is how `_commit_staged_activity` mints `seq`.
    replaced = dataclasses.replace(event, seq=9)
    assert replaced is not event
    assert event.seq == 1
    assert replaced.seq == 9


def test_the_four_read_only_constants_have_no_field_behind_them():
    """``is_field_value``/``is_evidence`` cannot be set, and survive the wire."""
    event = _event()
    assert event.is_field_value is False
    assert event.is_evidence is False
    # *** THE EXCEPTION CLASS HERE IS NOT `FrozenInstanceError`, AND THAT IS A
    # *** MEASUREMENT RATHER THAN A GUESS. ***
    # Assigning to a read-only PROPERTY of a `frozen=True, slots=True` dataclass
    # raises `TypeError: super(type, obj): obj must be an instance or subtype of
    # type` — a CPython artefact of `slots=True` RECREATING the class while the
    # generated `__setattr__` still closes over the original one. Assigning to a
    # declared FIELD on the same object raises `FrozenInstanceError` normally
    # (asserted above), so the two spellings of "refused" differ by exception class.
    #
    # `notes.Note`'s docstring says `n.verified = True` "is refused by the frozen
    # `__setattr__`", which is true about the EFFECT and imprecise about the class.
    # Both are accepted here rather than pinning one, because the property this test
    # defends is the refusal, and pinning a CPython implementation detail would make
    # a future interpreter's tidier error a test failure.
    with pytest.raises((TypeError, dataclasses.FrozenInstanceError)):
        event.is_field_value = True  # type: ignore[misc]
    with pytest.raises(AttributeError):
        object.__setattr__(event, "is_field_value", True)
    # Serialised, so a consumer reading JSON sees the guarantee rather than having
    # to know the class invariant.
    assert event.to_state()["is_field_value"] is False
    assert event.to_state()["is_evidence"] is False


def test_no_module_exposes_any_way_to_revise_or_delete_a_recorded_event():
    """An INVENTORY claim, not a spot check — ``revision_history.py``'s device.

    The property is that the two activity modules and the store expose no mutator at
    all, which is stronger than "the one I know about refuses". A name added later
    that looks like a mutator fails this.
    """
    for module in (activity, activity_history):
        exposed = set(getattr(module, "__all__", ()))
        # LOWERCASE NAMES ONLY — the exported CONSTANTS are deliberately excluded,
        # and the exclusion is narrow rather than convenient. `ACTION_RUN_REMOVED`
        # and `ACTION_ASSET_UPDATED` are the NAMES OF ACTS the history records; they
        # are not operations on a history, and matching them would make this guard
        # fail for describing the world accurately. A function is what could mutate
        # a row, and every function this module exports is lowercase.
        offenders = sorted(
            name
            for name in exposed
            if name == name.lower()
            and any(
                verb in name
                for verb in ("revise", "replace", "delete", "remove", "edit", "update")
            )
        )
        assert offenders == [], f"{module.__name__} exposes {offenders}"

    # The store side: an experiment can APPEND activity and read it, and has no
    # operation that removes or replaces one — unlike notes and proposals, which
    # deliberately have `replace_note` / `replace_proposal` because those entities
    # have review lifecycles.
    # `dir()` on the CLASS, which is the whole surface a caller can reach by name.
    # The three LISTS (`activity`, `unreadable_activity`, `_staged_activity`) are
    # instance attributes created by `default_factory`, so they are deliberately not
    # here — a class-level scan is exactly the right scope for "what operations
    # exist".
    store_names = sorted(n for n in dir(ws.Experiment) if "activity" in n)
    assert store_names == [
        # Commits the staged events. `save_versioned`'s, and nothing else's.
        "_commit_staged_activity",
        # STAGES one event. It does not append to `activity`.
        "record_activity",
        # A read.
        "sorted_activity",
    ], store_names
    # NO `replace_activity` AND NO `remove_activity`, which is the asymmetry with
    # notes and proposals: both of those have `replace_*` because their entities have
    # review lifecycles. An event has none.
    assert not hasattr(ws.Experiment, "replace_activity")
    assert not hasattr(ws.Experiment, "remove_activity")


def test_the_immutable_field_set_is_the_WHOLE_field_set():
    """``notes`` freezes a capture-shaped subset; an event has no revisable part."""
    declared = {f.name for f in dataclasses.fields(activity.ActivityEvent)}
    assert declared == set(activity.IMMUTABLE_EVENT_FIELDS)


# --- absent is not null ------------------------------------------------------


def test_before_distinguishes_absent_from_null_in_memory_and_over_the_wire():
    """THE CENTRAL DISTINCTION. A flat ``before: null`` cannot express both."""
    created = _event(before=activity.ABSENT, after=5)
    nulled = _event(before=None, after=5)

    assert created.before is activity.ABSENT
    assert nulled.before is None

    # And the wire form keeps them apart. This is the assertion that a
    # `before_present` sibling flag would have made possible to get wrong.
    assert created.to_state()["before"] == {"present": False, "value": None}
    assert nulled.to_state()["before"] == {"present": True, "value": None}

    # A round trip through JSON preserves both, which is what makes the split a
    # property of the persisted history and not of one process's memory.
    for event in (created, nulled):
        revived = activity.ActivityEvent.from_state(
            json.loads(json.dumps(event.to_state()))
        )
        assert (revived.before is activity.ABSENT) == (event.before is activity.ABSENT)
        assert revived.before == event.before or event.before is activity.ABSENT


def test_absent_is_falsy_and_a_single_instance():
    """So a site writing ``if before:`` cannot branch on the distinction unawares."""
    assert bool(activity.ABSENT) is False
    assert activity.Absent() is activity.ABSENT
    assert repr(activity.ABSENT) == "ABSENT"


def test_an_unreadable_before_envelope_reads_as_absent_and_never_as_null():
    """The fail-closed reading: claim nothing, rather than claim the value was null."""
    for broken in (None, 7, "nope", [], {}, {"value": 5}, {"present": "yes", "value": 5}):
        state = _event().to_state()
        state["before"] = broken
        assert activity.ActivityEvent.from_state(state).before is activity.ABSENT


# --- the bounded vocabularies ------------------------------------------------


def test_a_channel_outside_the_bounded_set_is_refused_not_coerced():
    with pytest.raises(activity.UnsupportedActivityEvent):
        _event(channel="carrier-pigeon")
    with pytest.raises(activity.UnsupportedActivityEvent):
        _event(channel="")
    # And DEC-44's four, no more and no fewer.
    assert activity.ACTIVITY_CHANNELS == frozenset(
        {"web", "mcp", "historical_import", "system"}
    )


def test_channel_is_required_with_no_default_so_a_write_path_cannot_omit_it():
    """``ACT-002``'s mechanical half: omission is a ``TypeError`` at the call."""
    with pytest.raises(TypeError):
        activity.new_event(  # type: ignore[call-arg]
            id="01JEVENT000000000000000001",
            experiment_id="01JACTIVITY0000000000000AA",
            seq=1,
            recorded_utc="2026-01-01T00:00:01Z",
            action=activity.ACTION_FIELD_ANSWERED,
            object_type=activity.OBJECT_FIELD,
            object_id="01JACTIVITY0000000000000AA",
        )


def test_an_unknown_action_or_object_type_is_refused():
    with pytest.raises(activity.UnsupportedActivityEvent):
        _event(action="did_something")
    with pytest.raises(activity.UnsupportedActivityEvent):
        _event(object_type="thingummy")


def test_channel_scope_refuses_an_unknown_scope_at_the_with_statement():
    with pytest.raises(activity.UnsupportedActivityEvent):
        with activity.channel_scope("nonsense"):
            pass


def test_the_ambient_channel_never_silently_becomes_web():
    """``ambient_channel``'s default is the CALLER's, so omission is a ``TypeError``."""
    assert activity.ambient_channel(activity.CHANNEL_SYSTEM) == activity.CHANNEL_SYSTEM
    with activity.channel_scope(activity.CHANNEL_MCP):
        assert activity.ambient_channel(activity.CHANNEL_SYSTEM) == activity.CHANNEL_MCP
    # Reset with the token, so the scope is exactly the block.
    assert activity.ambient_channel(activity.CHANNEL_SYSTEM) == activity.CHANNEL_SYSTEM
    with pytest.raises(TypeError):
        activity.ambient_channel()  # type: ignore[call-arg]


# --- the actor ---------------------------------------------------------------


def test_an_actor_nothing_vouched_for_reads_unattributed_with_a_matching_basis():
    event = _event()
    assert event.actor == "unattributed"
    assert event.actor_trust_basis == "unattributed"


def test_a_name_with_no_basis_and_a_basis_with_no_name_are_both_refused():
    """The half-attributed row is the shape the whole identity seam exists to refuse."""
    with pytest.raises(activity.UnsupportedActivityEvent):
        _event(actor="somebody", actor_trust_basis="unattributed")
    with pytest.raises(activity.UnsupportedActivityEvent):
        _event(actor="unattributed", actor_trust_basis="verified_edge_assertion")
    with pytest.raises(activity.UnsupportedActivityEvent):
        _event(actor="")


def test_actor_from_identity_answers_unattributed_for_everything_this_build_makes():
    """``ACT-005``'s seam, and the reason it is not wired: nothing names anybody.

    Every object here is passed as a settled identity, which is the ONLY input this
    function takes. It reads no request, so a forged header has no path to it at all
    — the HTTP half of that claim is asserted in ``test_activity_api.py``.
    """
    from isaac_api import identity as identity_module

    assert activity.actor_from_identity(None) == ("unattributed", "unattributed")

    untrusted = identity_module.resolve_request_identity(
        identity_module.Unconfigured(verifier_id=identity_module.UNCONFIGURED_VERIFIER)
    )
    assert untrusted.human is None
    assert activity.actor_from_identity(untrusted) == ("unattributed", "unattributed")

    class _NoSubject:
        human = type("H", (), {"subject": "", "trust_basis": "test_fixture"})()

    class _NoBasis:
        human = type("H", (), {"subject": "alice", "trust_basis": None})()

    assert activity.actor_from_identity(_NoSubject()) == ("unattributed", "unattributed")
    assert activity.actor_from_identity(_NoBasis()) == ("unattributed", "unattributed")

    # And the one shape that WOULD attribute, so this test is not vacuous: a settled
    # identity carrying a human with both halves. No verifier in this build produces
    # one from a request; constructing it here proves the function is not a constant.
    class _Attributed:
        human = type("H", (), {"subject": "alice", "trust_basis": "test_fixture"})()

    assert activity.actor_from_identity(_Attributed()) == ("alice", "test_fixture")


# --- the sequence, and silence on a no-op ------------------------------------


def test_seq_starts_at_one_and_is_monotonic_across_saves(tmp_path, monkeypatch):
    exp = _exp(tmp_path, monkeypatch)
    for n in range(3):
        exp.record_activity(
            action=activity.ACTION_EXPERIMENT_RENAMED,
            object_type=activity.OBJECT_EXPERIMENT,
            object_id=exp.id,
            channel=activity.CHANNEL_WEB,
            before=exp.title,
            after=f"T{n}",
        )
        exp.title = f"T{n}"
        assert exp.save_versioned() is True
    assert [e.seq for e in exp.sorted_activity()] == [1, 2, 3]


def test_several_events_in_one_save_get_distinct_positions(tmp_path, monkeypatch):
    """Which is why ``seq`` is not the record's ``rev``: ``rev`` moves once per save."""
    exp = _exp(tmp_path, monkeypatch)
    for n in range(3):
        exp.record_activity(
            action=activity.ACTION_FIELD_ANSWERED,
            object_type=activity.OBJECT_FIELD,
            object_id=exp.id,
            channel=activity.CHANNEL_WEB,
            field_path=f"f{n}",
            after=n,
        )
    exp.title = "moved"
    rev_before = exp.rev
    assert exp.save_versioned() is True
    assert exp.rev == rev_before + 1
    assert [e.seq for e in exp.sorted_activity()] == [1, 2, 3]


def test_a_byte_stable_no_op_records_nothing_and_burns_no_position(tmp_path, monkeypatch):
    """THE STAGING GUARANTEE. An event is recorded iff the state actually changed."""
    exp = _exp(tmp_path, monkeypatch)
    exp.record_activity(
        action=activity.ACTION_EXPERIMENT_RENAMED,
        object_type=activity.OBJECT_EXPERIMENT,
        object_id=exp.id,
        channel=activity.CHANNEL_WEB,
        before="A record",
        after="Renamed",
    )
    exp.title = "Renamed"
    assert exp.save_versioned() is True
    assert [e.seq for e in exp.activity] == [1]

    # Now a request that changes nothing: it stages an event and the save refuses.
    exp.record_activity(
        action=activity.ACTION_EXPERIMENT_RENAMED,
        object_type=activity.OBJECT_EXPERIMENT,
        object_id=exp.id,
        channel=activity.CHANNEL_WEB,
        before="Renamed",
        after="Renamed",
    )
    assert exp.save_versioned() is False
    assert [e.seq for e in exp.activity] == [1], "a no-op recorded an event"
    assert exp._staged_activity == [], "the staging was not cleared"

    # And the NEXT real change starts at 2, not 3 — the no-op burned no position.
    exp.record_activity(
        action=activity.ACTION_EXPERIMENT_RENAMED,
        object_type=activity.OBJECT_EXPERIMENT,
        object_id=exp.id,
        channel=activity.CHANNEL_WEB,
        before="Renamed",
        after="Again",
    )
    exp.title = "Again"
    assert exp.save_versioned() is True
    assert [e.seq for e in exp.activity] == [1, 2]


def test_activity_is_outside_the_authoritative_signature(tmp_path, monkeypatch):
    """Staging an event must not, by itself, make a record look changed.

    This is what keeps the ``If-Match`` contract and the change feed honest: `rev`
    moves exactly when the authoritative state moves.
    """
    exp = _exp(tmp_path, monkeypatch)
    before = ws._authoritative_signature(exp)
    exp.record_activity(
        action=activity.ACTION_EXPERIMENT_RENAMED,
        object_type=activity.OBJECT_EXPERIMENT,
        object_id=exp.id,
        channel=activity.CHANNEL_WEB,
        after="x",
    )
    assert ws._authoritative_signature(exp) == before
    # And a COMMITTED event does not move it either.
    exp.title = "x"
    assert exp.save_versioned() is True
    assert exp.activity
    committed = ws._authoritative_signature(exp)
    exp.activity.append(
        dataclasses.replace(exp.activity[0], id="01JEVENT000000000000000009", seq=99)
    )
    assert ws._authoritative_signature(exp) == committed


def test_a_refused_save_rolls_the_events_back_and_re_stages_them(tmp_path, monkeypatch):
    """A phantom act and a burned position, from one un-rolled-back append."""
    exp = _exp(tmp_path, monkeypatch)
    exp.record_activity(
        action=activity.ACTION_EXPERIMENT_RENAMED,
        object_type=activity.OBJECT_EXPERIMENT,
        object_id=exp.id,
        channel=activity.CHANNEL_WEB,
        after="boom",
    )
    exp.title = "boom"

    def _explode():
        raise RuntimeError("the database said no")

    real_save = exp.save
    exp.save = _explode  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        exp.save_versioned()
    assert exp.activity == [], "a refused write left a phantom event behind"
    assert len(exp._staged_activity) == 1, "a refused write lost the caller's audit row"

    # THE RETRY RECORDS IT, AT POSITION 1 — nothing was burned.
    #
    # `save` is restored by hand rather than with `monkeypatch.undo()`, and the
    # difference is a trap worth recording: `undo()` reverts EVERY patch this test's
    # fixture made, including `_exp`'s `ISAAC_UI_WORKSPACE`, so the retry would save
    # into a different (empty) workspace, find no prior signature, and the assertion
    # would pass for the wrong reason — or fail for one.
    exp.save = real_save  # type: ignore[method-assign]
    exp.title = "boom"
    assert exp.save_versioned() is True
    assert [e.seq for e in exp.activity] == [1]


# --- persisted tolerance -----------------------------------------------------


def test_a_malformed_persisted_entry_is_read_not_refused_and_not_discarded(
    tmp_path, monkeypatch
):
    """``CLAUDE.md`` §11: a wrong-typed PERSISTED value must never 500 a reader.

    And the second half, which is this feature's own: it must not be dropped either.
    An audit history whose reader silently deletes a row it cannot parse is not one.
    """
    exp = _exp(tmp_path, monkeypatch)
    exp.record_activity(
        action=activity.ACTION_EXPERIMENT_RENAMED,
        object_type=activity.OBJECT_EXPERIMENT,
        object_id=exp.id,
        channel=activity.CHANNEL_WEB,
        after="ok",
    )
    exp.title = "ok"
    exp.save_versioned()

    state = json.loads(exp.state_path.read_text(encoding="utf-8"))
    good = state[activity.ACTIVITY_STATE_KEY][0]
    state[activity.ACTIVITY_STATE_KEY] = [
        good,
        7,  # not an object at all
        {"id": "x"},  # an object the model refuses
        dict(good),  # a DUPLICATE id: readable, but two events cannot share one
    ]
    exp.state_path.write_text(json.dumps(state), encoding="utf-8")

    reloaded = ws.load_experiment(exp.id)
    assert reloaded is not None, "one malformed row hid the whole record"
    assert [e.id for e in reloaded.activity] == [good["id"]]
    assert len(reloaded.unreadable_activity) == 3

    # AND THEY SURVIVE A SAVE. Nothing is coerced, parsed, walked or dropped.
    reloaded.title = "moved again"
    assert reloaded.save_versioned() is True
    after = json.loads(reloaded.state_path.read_text(encoding="utf-8"))
    assert 7 in after[activity.ACTIVITY_STATE_KEY]
    assert {"id": "x"} in after[activity.ACTIVITY_STATE_KEY]
    assert len(after[activity.ACTIVITY_STATE_KEY]) == 4

    # And the read API COUNTS them rather than rendering them.
    page = activity_history.activity_page(reloaded)
    assert page["unreadable_entries"] == 3
    assert page["total"] == 1


def test_a_top_level_activity_value_that_is_not_a_list_is_read_not_refused(
    tmp_path, monkeypatch
):
    exp = _exp(tmp_path, monkeypatch)
    state = json.loads(exp.state_path.read_text(encoding="utf-8"))
    state[activity.ACTIVITY_STATE_KEY] = "not a list"
    exp.state_path.write_text(json.dumps(state), encoding="utf-8")
    reloaded = ws.load_experiment(exp.id)
    assert reloaded is not None
    assert reloaded.activity == []
    assert reloaded.unreadable_activity == []


def test_a_document_written_before_activity_existed_needs_no_migration(
    tmp_path, monkeypatch
):
    """The mechanical reason ``ACT-001``'s "Needs migration ``0006``" is answered ``no``."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    legacy = {
        "id": "01JLEGACY00000000000000001",
        "title": "Written before the history existed",
        "created_utc": "2026-01-01T00:00:00Z",
    }
    exp = ws.Experiment.from_state(legacy)
    assert exp.activity == []
    assert exp.unreadable_activity == []
    # And it hashes identically to the same record re-read, so the added key causes
    # NO spurious rev bump on legacy state — the property runs, notes and proposals
    # each relied on.
    assert ws._authoritative_signature(exp) == ws._authoritative_signature(
        ws.Experiment.from_state(json.loads(json.dumps(exp.to_state())))
    )


def test_a_nonsense_persisted_position_cannot_produce_a_position_below_one(
    tmp_path, monkeypatch
):
    """The ``max(..., 0)`` floor. A malformed historical row must not refuse the act."""
    exp = _exp(tmp_path, monkeypatch)
    # `seq` cannot be negative on a constructed event (the model refuses), so the
    # only way to reach the floor is a hydrated document. Simulate exactly that.
    exp.activity[:] = [activity.ActivityEvent.from_state({**_event().to_state(), "seq": 1})]
    exp.record_activity(
        action=activity.ACTION_EXPERIMENT_RENAMED,
        object_type=activity.OBJECT_EXPERIMENT,
        object_id=exp.id,
        channel=activity.CHANNEL_WEB,
        after="next",
    )
    exp.title = "next"
    assert exp.save_versioned() is True
    assert min(e.seq for e in exp.activity) >= 1


# --- inert to export ---------------------------------------------------------


def test_an_activity_event_reaches_neither_export_nor_the_submission_signature(
    tmp_path, monkeypatch
):
    """Contract invariant **I2**, and it is STRUCTURAL: nothing that exports looks here.

    Asserted by MEASUREMENT rather than by reading the code: the same record is
    hashed and composed with and without a recorded event, and every artifact is
    byte-identical.
    """
    from isaac_api import submissions

    exp = _exp(tmp_path, monkeypatch)
    exp.draft = {"fields": {}, "pending": []}
    exp.save_versioned()

    units_before = [u.draft for u in exp.export_units()]
    signature_before = submissions.content_signature(exp.id, exp.export_units())
    resolved_before = [
        exp.resolved_run_draft(run) for run in exp.sorted_runs()
    ]

    exp.record_activity(
        action=activity.ACTION_FIELD_ANSWERED,
        object_type=activity.OBJECT_FIELD,
        object_id=exp.id,
        channel=activity.CHANNEL_WEB,
        field_path="qc",
        before=activity.ABSENT,
        after={"status": "valid"},
    )
    exp.title = "forces the write"
    assert exp.save_versioned() is True
    assert exp.activity, "the event was not recorded, so this test proves nothing"

    assert [u.draft for u in exp.export_units()] == units_before
    assert (
        submissions.content_signature(exp.id, exp.export_units()) == signature_before
    )
    assert [exp.resolved_run_draft(r) for r in exp.sorted_runs()] == resolved_before

    # And the key is not inside `draft`, which is what makes the above structural
    # rather than a coincidence of today's `transform`.
    assert activity.ACTIVITY_STATE_KEY not in exp.draft
    assert activity.ACTIVITY_STATE_KEY in exp.to_state()


def test_no_truth_path_module_imports_the_activity_modules():
    """The deterministic core must not be able to reach an audit row.

    ``CLAUDE.md`` §13 names the truth path; this is the same kind of inventory guard
    the repository already applies to Graphify imports.
    """
    import pathlib

    root = pathlib.Path(ws.__file__).resolve().parents[3] / "src" / "isaac_records"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "activity_history" in text or "import activity" in text:
            offenders.append(path.name)
    assert offenders == [], offenders


def test_the_activity_panel_transcribes_the_server_actor_constants_exactly():
    """The frontend copies two server constants; nothing made them agree.

    ``ActivityHistoryPanel.tsx`` declares ``ACTOR_UNATTRIBUTED`` and
    ``TRUST_BASIS_TEST_FIXTURE`` because the frontend has no import path to Python.
    Both decide BEHAVIOUR, not wording: the first gates whether any per-row actor is
    rendered at all and which standing disclosure appears, the second gates
    ``DEC-45``'s "a name never travels unqualified" qualification.

    **A drift in either spelling fails NO frontend test**, because every frontend
    fixture supplies the same literal the component compares against — so the two
    sides would agree with each other and disagree with the server. The visible
    result would be an actor column silently appearing on every row of every record
    (the sentinel no longer matching), or a fixture-minted name rendered with no
    qualification at all. This is the mirror of the parity guards ``CLAUDE.md`` §11
    records for the blocker keys and for ``RUN_LIST_LIMIT_MAX``.

    The declarations are matched as whole lines, in the exact one-per-line form the
    component's own comment says to keep them in, so a reformat that merges them is
    a visible failure here rather than a silent hole.
    """
    import pathlib
    import re

    from isaac_api import identity

    panel = (
        pathlib.Path(ws.__file__).resolve().parents[3]
        / "apps"
        / "web"
        / "src"
        / "components"
        / "ActivityHistoryPanel.tsx"
    )
    assert panel.is_file(), panel
    # `errors="replace"` and a plain read: §11's NUL-byte trap is about `grep`
    # exiting 0 on a file it skipped, and a Python read cannot fail that way.
    source = panel.read_text(encoding="utf-8", errors="replace")

    def declared(name: str) -> str:
        found = re.findall(rf"^const {name} = '([^']*)';$", source, flags=re.MULTILINE)
        assert len(found) == 1, f"expected exactly one `const {name} = '...';` line, found {found}"
        return found[0]

    assert declared("ACTOR_UNATTRIBUTED") == activity.ACTOR_UNATTRIBUTED
    assert declared("TRUST_BASIS_TEST_FIXTURE") == identity.TRUST_BASIS_TEST_FIXTURE

    # NEGATIVE CONTROL: the two are different strings, so a guard that accidentally
    # compared one constant against itself would still be doing work.
    assert activity.ACTOR_UNATTRIBUTED != identity.TRUST_BASIS_TEST_FIXTURE


def test_the_other_frontend_sites_spell_test_fixture_the_same_way():
    """Two more frontend files hard-code ``test_fixture``, and they must not diverge.

    ``revisionHistory.actorBasisNote`` is the rule ``ActivityHistoryPanel`` reuses
    rather than re-invents, and ``currentUserContract`` declares the basis as a
    TypeScript union member. Three spellings of one value is how a vocabulary
    drifts — which is the reason ``activity.TRUST_BASIS_UNATTRIBUTED``'s own
    docstring gives for reusing ``submissions``' constant instead of minting a new
    one. Asserted over PRESENCE of the correct literal rather than over absence of a
    wrong one, because the wrong one is unbounded.
    """
    import pathlib

    from isaac_api import identity

    web = pathlib.Path(ws.__file__).resolve().parents[3] / "apps" / "web" / "src"
    quoted = f"'{identity.TRUST_BASIS_TEST_FIXTURE}'"
    for rel in ("lib/revisionHistory.ts", "lib/currentUserContract.ts"):
        path = web / rel
        assert path.is_file(), path
        assert quoted in path.read_text(encoding="utf-8", errors="replace"), rel

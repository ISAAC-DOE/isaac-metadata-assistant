"""Unmapped Notes — the domain model, its persistence, and the four HTTP operations.

WHAT THIS FEATURE PROMISES, AND WHERE EACH PROMISE IS HELD HERE
===============================================================

The feature is four sentences, and every one of them is a claim a test can falsify:

1. **Nothing captured is ever silently discarded.** Dismissal is a recorded,
   retrievable state; a stored entry this build cannot read is preserved verbatim
   rather than dropped; there is no delete operation anywhere.
   (``test_a_dismissed_note_is_still_listed_and_still_readable``,
   ``test_an_unreadable_stored_entry_survives_a_save_verbatim``,
   ``test_the_api_exposes_no_way_to_delete_a_note``)
2. **No guessed schema target.** ``candidate_field_path`` is absent unless
   something deterministic produced it AND stated the rule; ``run_id`` is never
   inferred from the only run that happens to exist; an invented path is refused
   rather than stored. (``test_a_note_nothing_proposed_a_home_for_has_no_candidate_path``,
   ``test_the_only_run_is_not_inferred_as_a_notes_run``,
   ``test_a_candidate_path_and_its_rule_travel_together``)
3. **A note is not evidence and not a value, structurally.**
   (``test_a_note_cannot_be_constructed_as_a_verified_value`` and the four tests
   after it)
4. **"Keep as Note" is a first-class outcome.** It is a state a scientist reaches
   deliberately, indistinguishable in kind from ``mapped``.
   (``test_keeping_a_note_is_a_recorded_outcome_not_an_unfinished_review``)

MUTATION-CHECKED
================

Every test in the "negative controls" list of the slice contract was verified by
BREAKING the production code in the specific way the test claims to catch,
confirming the test went RED, and reverting the break. The mutation is recorded in
the docstring of each such test under ``MUTATION:``. A test whose docstring has no
``MUTATION:`` line was not mutation-checked and does not claim to have been.

Everything here is synthetic. No file outside the tmp workspace is read or written,
and nothing connects to a database.
"""

from __future__ import annotations

import copy
import dataclasses
import json

import pytest

import isaac_api.notes as notes
import isaac_api.routes as routes
import isaac_api.workspace as ws
from isaac_records.models import STATUSES

from conftest import client_ws, tutorial_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def experiment_id(client):
    """An ordinary experiment with no runs and an empty draft.

    Notes are about content that has NO schema home, so a fixture that is already
    full of mapped fields would obscure rather than help.
    """
    store = client_ws(client)
    exp = store.create_experiment(
        "Notes fixture", {"kind": "synthetic"}, {"meta": {}, "fields": {}, "pending": []}
    )
    return exp.id


#: A real official field path, taken from the application's own map rather than
#: written out here — a hand-copied literal would be a second definition of "real
#: path" and could rot silently into a test that passes for the wrong reason.
MAPPABLE = sorted(routes.NOTE_MAPPABLE_FIELD_PATHS)[0]


# --- helpers ------------------------------------------------------------------


def _etag(client, experiment_id: str) -> str:
    response = client.get(f"/api/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    return response.headers["ETag"]


def _capture(client, experiment_id: str, **body):
    body.setdefault("text", "the beamline tripped, scan 3 was repeated")
    body.setdefault("source", "typed_note")
    return client.post(
        f"/api/experiments/{experiment_id}/notes",
        json=body,
        headers={"If-Match": _etag(client, experiment_id)},
    )


def _captured(client, experiment_id: str, **body) -> dict:
    response = _capture(client, experiment_id, **body)
    assert response.status_code == 201, response.text
    return response.json()["note"]


def _review(client, experiment_id: str, note_id: str, *, if_match=..., **body):
    body.setdefault("confirmed_by_user", True)
    tag = _etag(client, experiment_id) if if_match is ... else if_match
    headers = {} if tag is None else {"If-Match": tag}
    return client.post(
        f"/api/experiments/{experiment_id}/notes/{note_id}/review",
        json=body,
        headers=headers,
    )


def _stored(client, experiment_id: str):
    """The experiment as the STORE holds it — never as a response reported it."""
    return client_ws(client).load_experiment(experiment_id)


def _a_note(**overrides) -> notes.Note:
    kwargs = {
        "id": "NOTE-1",
        "experiment_id": "EXP-1",
        "text": "  verbatim, with edge whitespace  ",
        "source": "typed_note",
        "captured_utc": "2026-08-12T00:00:00Z",
    }
    kwargs.update(overrides)
    return notes.new_note(**kwargs)


# --- 1. a note is not a value, and cannot be made into one --------------------


def test_a_note_cannot_be_constructed_as_a_verified_value():
    """The four constants are PROPERTIES, so there is no field to set.

    This is the structural half of "a note is not evidence and not a value". Each
    route below is a different way a caller could try to attach the claim, and each
    has to fail for its own reason — a guard that only closed the first would leave
    the other three open.

    MUTATION: turned ``verified`` from a read-only property into an ordinary field
    ``verified: bool = False`` on ``Note``. Three of these four assertions went RED
    immediately (construction, ``replace`` and ``object.__setattr__`` all began to
    succeed). Reverted.
    """
    note = _a_note()

    # 1. There is no such constructor argument.
    with pytest.raises(TypeError):
        notes.Note(
            id="X",
            experiment_id="E",
            text="t",
            source="typed_note",
            captured_utc="2026-08-12T00:00:00Z",
            verified=True,  # type: ignore[call-arg]
        )

    # 2. `dataclasses.replace` cannot introduce it either.
    with pytest.raises(TypeError):
        dataclasses.replace(note, verified=True)  # type: ignore[call-arg]

    # 3. Plain assignment is refused by `frozen=True`. CPython raises TypeError
    #    rather than FrozenInstanceError when `slots=True` is also set; the test
    #    accepts either rather than pinning an implementation detail.
    with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
        note.verified = True  # type: ignore[misc]

    # 4. `object.__setattr__` is the escape hatch that DOES work on an ordinary
    #    frozen dataclass field. It cannot reach a property with no setter.
    with pytest.raises(AttributeError):
        object.__setattr__(note, "verified", True)

    # 5. `slots=True` leaves no instance __dict__ to smuggle a new flag into.
    with pytest.raises(AttributeError):
        object.__setattr__(note, "confirmed_by_user", True)

    assert note.verified is False
    assert note.is_evidence is False
    assert note.is_field_value is False


def test_the_four_constants_survive_serialisation():
    """A JSON reader cannot see a class invariant, so the wire repeats it.

    MUTATION: dropped ``verified``/``is_evidence``/``is_field_value`` from
    ``Note.to_state``. RED here and in the HTTP test below. Reverted.
    """
    payload = _a_note().to_state()
    assert payload["status"] == notes.NOTE_STATUS
    assert payload["verified"] is False
    assert payload["is_evidence"] is False
    assert payload["is_field_value"] is False


def test_a_notes_status_is_not_a_draft_envelope_status():
    """``unmapped_note`` must appear nowhere in the draft vocabulary.

    A reader that keys on the string sees a token it does not recognise rather than
    one that quietly reads as ``verified``. This is the assertion that would catch
    somebody "tidying" ``NOTE_STATUS`` into an existing member.

    MUTATION: set ``NOTE_STATUS = "verified"``. RED. Reverted.
    """
    assert notes.NOTE_STATUS not in STATUSES
    assert notes.NOTE_STATUS not in {s.lower() for s in STATUSES}


def test_a_note_carries_no_isaac_evidence_source_type():
    """The note vocabulary is this feature's own and does not borrow the evidence one.

    Borrowing a member would widen what those words mean in the truth core, which
    is a §13 change this feature does not make.
    """
    from isaac_records.models import SOURCE_TYPES

    assert not (notes.NOTE_SOURCES & set(SOURCE_TYPES))


def test_a_request_cannot_ask_a_note_to_be_a_value(client, experiment_id):
    """A body key claiming verification is REFUSED, not accepted and ignored.

    The difference matters: an ignored key returns ``201`` with ``verified: false``
    in a body the caller is not reading, and the caller goes on believing it stored
    a confirmed value. A ``422`` naming the key cannot be misread.

    MUTATION: made ``_unknown_note_keys`` return ``None`` unconditionally. RED —
    the request became a ``201``. Reverted.
    """
    for claim in ({"verified": True}, {"status": "verified"}, {"is_evidence": True}):
        response = _capture(client, experiment_id, **claim)
        assert response.status_code == 422, (claim, response.text)
        body = response.json()
        assert body["error"] == "unrecognized_field"
        assert body["key"] == next(iter(claim))
    assert _stored(client, experiment_id).notes == []


def test_every_note_the_api_returns_states_that_it_is_not_a_value(client, experiment_id):
    note = _captured(client, experiment_id)
    assert note["verified"] is False
    assert note["is_evidence"] is False
    assert note["is_field_value"] is False
    assert note["status"] == "unmapped_note"

    listed = client.get(f"/api/experiments/{experiment_id}/notes").json()["notes"]
    assert [n["verified"] for n in listed] == [False]
    assert [n["is_field_value"] for n in listed] == [False]


# --- 2. no guessed schema target ----------------------------------------------


def test_a_note_nothing_proposed_a_home_for_has_no_candidate_path(client, experiment_id):
    """``None``, not a plausible-looking path.

    The failure this guards against is the tempting one: a note whose text contains
    the word "formula" acquiring ``sample.material.formula`` because something
    matched a substring. Nothing here proposes anything, so the field must be
    ``null`` end to end — in the response, and on disk.

    MUTATION: defaulted ``candidate_field_path`` in ``Experiment.capture_note`` to
    ``MAPPABLE`` when the caller passed ``None``. RED. Reverted.
    """
    note = _captured(
        client,
        experiment_id,
        text="the sample formula looked wrong on the second scan",
    )
    assert note["candidate_field_path"] is None
    assert note["candidate_rule"] is None
    assert note["mapped_field_path"] is None

    stored = _stored(client, experiment_id).notes[0]
    assert stored.candidate_field_path is None
    assert stored.candidate_rule is None


def test_a_candidate_path_and_its_rule_travel_together():
    """Either half without the other is refused, in BOTH directions.

    A path with no rule is an unexplained proposal — a guess wearing a field name.
    A rule with no path describes a derivation that produced nothing.

    MUTATION: deleted the ``candidate_rule is None`` branch from
    ``Note.__post_init__``. RED. Reverted.
    """
    with pytest.raises(notes.UnsupportedNote):
        _a_note(candidate_field_path=MAPPABLE)
    with pytest.raises(notes.UnsupportedNote):
        _a_note(candidate_rule="matched the column heading exactly")

    both = _a_note(
        candidate_field_path=MAPPABLE, candidate_rule="the CSV heading matched exactly"
    )
    assert both.candidate_field_path == MAPPABLE
    assert both.candidate_rule == "the CSV heading matched exactly"


def test_an_invented_candidate_path_is_refused_rather_than_stored(client, experiment_id):
    """Membership, not shape. ``sample.material.typo`` has a plausible shape.

    A stored path that does not exist is a guess that looks like a fact, and a
    plausible shape is exactly what gets believed.
    """
    response = _capture(
        client,
        experiment_id,
        candidate_field_path=MAPPABLE.rsplit(".", 1)[0] + ".not_a_real_field",
        candidate_rule="an ingest proposed it",
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field"
    assert _stored(client, experiment_id).notes == []


def test_a_note_cannot_be_mapped_to_a_field_that_does_not_exist(client, experiment_id):
    note = _captured(client, experiment_id)
    response = _review(
        client, experiment_id, note["id"], action="map", field_path="sample.made.up"
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unrecognized_field"
    assert _stored(client, experiment_id).notes[0].mapped_field_path is None


def test_the_only_run_is_not_inferred_as_a_notes_run(client, experiment_id):
    """An omitted ``run_id`` stays omitted even when exactly one run exists.

    "The only run" is an inference about the science, not a stored rule, and this is
    the single most tempting place in the feature to make one: the answer would be
    right most of the time, which is what makes it dangerous.

    MUTATION: in ``Experiment.capture_note``, defaulted ``run_id`` to
    ``self.runs[0].id`` when ``run_id is None and len(self.runs) == 1``. RED.
    Reverted.
    """
    created = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": "the only run"},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert created.status_code == 201, created.text
    only_run_id = created.json()["run"]["id"]

    note = _captured(client, experiment_id, text="a remark about the record as a whole")
    assert note["run_id"] is None
    assert _stored(client, experiment_id).notes[0].run_id is None

    # ...and a note that DOES name the run keeps it, so the assertion above is
    # about inference rather than about the field being ignored.
    attached = _captured(client, experiment_id, text="about this run", run_id=only_run_id)
    assert attached["run_id"] == only_run_id


def test_a_note_cannot_name_a_run_this_record_does_not_have(client, experiment_id):
    response = _capture(client, experiment_id, run_id="NOT-A-RUN")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "unknown_run"
    assert _stored(client, experiment_id).notes == []


def test_a_blank_optional_is_refused_not_folded_into_absent():
    """``""`` and ``None`` mean different things and are not collapsed.

    ``None`` means nobody supplied this. ``""`` means a caller supplied something
    empty and expects it to have been stored. Folding the second into the first is a
    small silent discard.
    """
    with pytest.raises(notes.UnsupportedNote):
        _a_note(run_id="")
    with pytest.raises(notes.UnsupportedNote):
        _a_note(candidate_field_path="", candidate_rule="r")


# --- 3. no silent discard -----------------------------------------------------


def test_a_dismissed_note_is_still_listed_and_still_readable(client, experiment_id):
    """Dismissal is a STATE. The note stays retrievable by every read path.

    This is the negative control for the whole feature: if dismissal ever became a
    delete, this is what would catch it.

    MUTATION: made ``post_note_review``'s dismiss branch call a
    ``exp.notes.remove(note)`` instead of ``exp.replace_note(dismiss_note(...))``.
    RED on all four assertions below. Reverted.
    """
    note = _captured(client, experiment_id, text="an aside nobody could place")
    response = _review(client, experiment_id, note["id"], action="dismiss")
    assert response.status_code == 200, response.text
    assert response.json()["note"]["state"] == "dismissed"

    # 1. The unfiltered list still contains it, and `total` still counts it.
    listed = client.get(f"/api/experiments/{experiment_id}/notes").json()
    assert listed["total"] == 1
    assert listed["returned"] == 1
    assert [n["id"] for n in listed["notes"]] == [note["id"]]
    assert listed["by_state"] == {"unreviewed": 0, "mapped": 0, "kept": 0, "dismissed": 1}

    # 2. It is addressable directly, with a 200 and not a 404.
    read = client.get(f"/api/experiments/{experiment_id}/notes/{note['id']}")
    assert read.status_code == 200, read.text
    assert read.json()["note"]["state"] == "dismissed"

    # 3. Its verbatim text is unchanged by having been dismissed.
    assert read.json()["note"]["text"] == "an aside nobody could place"

    # 4. It survives a reload from persisted state.
    reloaded = _stored(client, experiment_id).notes
    assert len(reloaded) == 1
    assert reloaded[0].dismissed is True
    assert reloaded[0].text == "an aside nobody could place"


def test_a_dismissed_note_is_only_hidden_when_a_client_asks_for_a_subset(
    client, experiment_id
):
    """Filtering is the caller's, and a filtered list still states the true total.

    A client that narrows to ``unreviewed`` gets an empty page whose ``total`` is
    still 1, so it can never render "no notes" while the record holds one.
    """
    note = _captured(client, experiment_id)
    _review(client, experiment_id, note["id"], action="dismiss")

    narrowed = client.get(
        f"/api/experiments/{experiment_id}/notes", params={"state": "unreviewed"}
    ).json()
    assert narrowed["notes"] == []
    assert narrowed["returned"] == 0
    assert narrowed["total"] == 1
    assert narrowed["by_state"]["dismissed"] == 1


def test_the_api_exposes_no_way_to_delete_a_note(client):
    """There is no DELETE, and no action named one.

    Asked of the generated OpenAPI document rather than asserted in prose, so a
    route added later is caught wherever it was declared.

    MUTATION: added a ``@router.delete("/experiments/{experiment_id}/notes/{note_id}")``
    stub. RED. Reverted (the stub was never implemented).
    """
    spec = client.get("/api/openapi").json()
    note_paths = {p: m for p, m in spec["paths"].items() if "/notes" in p}
    assert note_paths, "the note operations vanished from the spec"
    for path, methods in note_paths.items():
        assert "delete" not in methods, f"{path} gained a DELETE"
        assert "put" not in methods, f"{path} gained a PUT"

    assert "delete" not in notes.NOTE_ACTIONS
    assert "remove" not in notes.NOTE_ACTIONS


def test_an_unreadable_stored_entry_survives_a_save_verbatim(client, experiment_id):
    """A note this build cannot read is PRESERVED, counted, and written back out.

    This is where "no silent discard" is hardest and where the run model's policy
    is deliberately not followed: ``_hydrate_runs`` DROPS an entry it cannot make a
    run of. Doing that here would mean this feature's own read path quietly
    deleting captured content.

    The entry is planted directly in the stored document, because that is exactly
    how it would arrive in reality — written by a build that knew a shape this one
    does not.

    MUTATION: changed ``_hydrate_notes`` to ``continue`` instead of appending to
    ``unreadable`` (i.e. made it behave like ``_hydrate_runs``). RED on the
    survival and the disclosure assertions. Reverted.
    """
    _captured(client, experiment_id, text="a readable one")
    store = client_ws(client)
    exp = store.load_experiment(experiment_id)

    alien = {
        "id": "FROM-A-LATER-BUILD",
        "text": "content this build cannot interpret",
        "source": "a_source_this_build_does_not_know",
        "captured_utc": "2026-09-01T00:00:00Z",
        "confidence_model": {"kind": "something new"},
    }
    state = exp.to_state()
    state["notes"].append(copy.deepcopy(alien))
    path = ws.scope_root(client.tutorial_session_id) / experiment_id / "experiment.json"
    path.write_text(json.dumps(state), encoding="utf-8")

    # 1. Reading does not raise, does not drop it, and does not invent a note.
    reread = store.load_experiment(experiment_id)
    assert len(reread.notes) == 1
    assert reread.unreadable_notes == [alien]

    # 2. It is DISCLOSED rather than silently absent. Reporting zero here while the
    #    document holds one is the exact silent discard this feature exists to end.
    listed = client.get(f"/api/experiments/{experiment_id}/notes").json()
    assert listed["unreadable_entries"] == 1
    assert listed["total"] == 1  # it is not rendered as a note, because it cannot be

    # 3. A subsequent WRITE preserves it byte-for-byte rather than rewriting the
    #    document without it. This is the assertion that matters: a read that keeps
    #    it and a save that drops it is still a silent discard.
    _captured(client, experiment_id, text="a second readable one")
    after = json.loads(path.read_text(encoding="utf-8"))
    assert alien in after["notes"]
    assert len(client_ws(client).load_experiment(experiment_id).notes) == 2


def test_editing_never_replaces_the_verbatim_capture(client, experiment_id):
    """The original text, every superseded wording, and the current one all survive.

    MUTATION: made ``edit_note`` pass ``text=revised`` to ``revise_note`` (i.e.
    overwrite the capture). RED — ``revise_note`` raised ``ImmutableCapture``, and
    with that guard also removed the ``text`` assertion below went RED. Reverted.
    """
    note = _captured(client, experiment_id, text="orginal typo'd wording")
    first = _review(client, experiment_id, note["id"], action="edit", text="second wording")
    assert first.status_code == 200, first.text
    second = _review(client, experiment_id, note["id"], action="edit", text="third wording")
    assert second.status_code == 200, second.text

    final = second.json()["note"]
    assert final["text"] == "orginal typo'd wording"  # never touched
    assert final["revised_text"] == "third wording"
    assert final["display_text"] == "third wording"

    superseded = [
        entry["superseded_text"]
        for entry in final["history"]
        if entry["action"] == "edit"
    ]
    assert superseded == ["orginal typo'd wording", "second wording"]


def test_the_capture_fields_cannot_be_revised_by_any_action():
    """``revise_note`` is the one door, and it is closed on the capture.

    A review action added later cannot rewrite what was captured by accident — only
    by deliberately bypassing the sole revision helper this module exposes.
    """
    note = _a_note()
    for field in sorted(notes.IMMUTABLE_NOTE_FIELDS):
        with pytest.raises(notes.ImmutableCapture):
            notes.revise_note(note, **{field: "rewritten"})


def test_a_notes_history_may_only_be_extended():
    """An audit trail that can be rewritten is not an audit trail.

    MUTATION: deleted the history-prefix check from ``revise_note``. RED on both
    assertions. Reverted.
    """
    note = notes.dismiss_note(_a_note(), at="2026-08-12T01:00:00Z")
    assert len(note.history) == 2

    with pytest.raises(notes.ImmutableCapture):  # shortened
        notes.revise_note(note, history=note.history[:1])
    with pytest.raises(notes.ImmutableCapture):  # earlier entry rewritten
        notes.revise_note(
            note,
            history=(
                dataclasses.replace(note.history[0], at="2020-01-01T00:00:00Z"),
                note.history[1],
            ),
        )


def test_text_too_large_is_refused_rather_than_truncated(client, experiment_id):
    """"Never truncated" is kept by REFUSING, not by silently keeping a prefix.

    A truncated note is a note that lies about what was written, which is worse
    than no note at all.
    """
    response = _capture(client, experiment_id, text="x" * (routes._MAX_NOTE_BYTES + 1))
    assert response.status_code == 422, response.status_code
    assert response.json()["error"] == "unrepresentable_value"
    assert _stored(client, experiment_id).notes == []


def test_the_verbatim_text_is_stored_exactly_as_sent(client, experiment_id):
    """Not trimmed, not normalised, not case-folded. Whitespace included."""
    raw = "  Scan 3 \t re-run — beam DROPPED.\n\n  See logbook p.14  "
    note = _captured(client, experiment_id, text=raw)
    assert note["text"] == raw
    assert _stored(client, experiment_id).notes[0].text == raw
    read = client.get(f"/api/experiments/{experiment_id}/notes/{note['id']}").json()
    assert read["note"]["text"] == raw


# --- 4. "keep as note" is a first-class outcome -------------------------------


def test_keeping_a_note_is_a_recorded_outcome_not_an_unfinished_review(
    client, experiment_id
):
    """``kept`` is a decision, reached and recorded exactly as ``mapped`` is.

    The assertion that carries the meaning is the last one: a kept note is NOT
    counted among the unreviewed. If it were, "keep" would be a no-op dressed as an
    action and the queue would never empty.
    """
    note = _captured(client, experiment_id, text="prose about why we came back on Tuesday")
    response = _review(client, experiment_id, note["id"], action="keep")
    assert response.status_code == 200, response.text

    kept = response.json()["note"]
    assert kept["state"] == "kept"
    assert kept["mapped_field_path"] is None  # it belongs to no field, and says so
    assert [e["action"] for e in kept["history"]] == ["capture", "keep"]
    assert kept["history"][-1]["from_state"] == "unreviewed"
    assert kept["history"][-1]["to_state"] == "kept"

    listed = client.get(f"/api/experiments/{experiment_id}/notes").json()
    assert listed["by_state"] == {"unreviewed": 0, "mapped": 0, "kept": 1, "dismissed": 0}


def test_mapping_records_a_target_and_writes_no_value(client, experiment_id):
    """A mapped note says WHERE content belongs. It does not say what the value is.

    Deriving a value from prose means deciding what the value IS, which is precisely
    the guess this project refuses. So the draft must be byte-identical across a
    map, and the note must carry no value of any kind.

    MUTATION: made the map branch also write ``exp.draft["fields"][field_path]`` as
    a ``field_value`` envelope. RED on the draft-unchanged assertion. Reverted.
    """
    before = copy.deepcopy(_stored(client, experiment_id).draft)
    note = _captured(client, experiment_id, text="this belongs with the material")
    response = _review(client, experiment_id, note["id"], action="map", field_path=MAPPABLE)
    assert response.status_code == 200, response.text

    mapped = response.json()["note"]
    assert mapped["state"] == "mapped"
    assert mapped["mapped_field_path"] == MAPPABLE
    assert mapped["is_field_value"] is False
    assert mapped["verified"] is False
    assert mapped["history"][-1]["field_path"] == MAPPABLE

    assert _stored(client, experiment_id).draft == before


def test_a_machine_candidate_and_a_scientists_mapping_are_different_fields(
    client, experiment_id
):
    """Collapsing them would make a suggestion indistinguishable from a decision."""
    note = _captured(
        client,
        experiment_id,
        candidate_field_path=MAPPABLE,
        candidate_rule="the CSV heading matched this path exactly",
    )
    assert note["candidate_field_path"] == MAPPABLE
    assert note["mapped_field_path"] is None
    assert note["state"] == "unreviewed"  # a proposal is not a decision

    other = sorted(routes.NOTE_MAPPABLE_FIELD_PATHS)[1]
    mapped = _review(
        client, experiment_id, note["id"], action="map", field_path=other
    ).json()["note"]
    assert mapped["candidate_field_path"] == MAPPABLE  # the proposal is still recorded
    assert mapped["mapped_field_path"] == other  # the decision overrode it


def test_a_dismissal_reason_is_stored_when_given_and_absent_when_not(
    client, experiment_id
):
    """No justification is ever composed on a scientist's behalf.

    A fabricated reason in an audit trail is worse than a missing one.
    """
    with_reason = _captured(client, experiment_id, text="one")
    body = _review(
        client, experiment_id, with_reason["id"], action="dismiss", reason="duplicate of scan 2"
    ).json()["note"]
    assert body["history"][-1]["reason"] == "duplicate of scan 2"

    without = _captured(client, experiment_id, text="two")
    body = _review(client, experiment_id, without["id"], action="dismiss").json()["note"]
    assert body["history"][-1]["reason"] is None


# --- 5. persistence: round trip, versioning, isolation ------------------------


def test_notes_round_trip_through_to_state_and_from_state(client, experiment_id):
    """Every field survives the persistence boundary, including the history.

    Asserted as an equality of the SERIALISED forms rather than field by field, so a
    field added later is covered without editing this test.

    MUTATION: dropped ``"notes"`` from ``Experiment.to_state``. RED. Reverted.
    MUTATION: dropped the ``history`` key from ``Note.to_state``. RED. Reverted.
    """
    first = _captured(
        client,
        experiment_id,
        text="  whitespace and — unicode …  ",
        candidate_field_path=MAPPABLE,
        candidate_rule="the ingest matched this heading",
    )
    second = _captured(client, experiment_id, text="second")
    _review(client, experiment_id, second["id"], action="edit", text="second, corrected")
    _review(client, experiment_id, second["id"], action="dismiss", reason="superseded")

    exp = _stored(client, experiment_id)
    before = [n.to_state() for n in exp.sorted_notes()]

    revived = ws.Experiment.from_state(
        exp.to_state(), session_id=client.tutorial_session_id
    )
    after = [n.to_state() for n in revived.sorted_notes()]

    assert after == before
    assert len(after) == 2
    assert after[0]["text"] == "  whitespace and — unicode …  "
    assert after[0]["candidate_rule"] == "the ingest matched this heading"
    assert [e["action"] for e in after[1]["history"]] == ["capture", "edit", "dismiss"]
    assert after[1]["history"][-1]["reason"] == "superseded"
    assert after[1]["revised_text"] == "second, corrected"


def test_capturing_a_note_moves_the_experiment_version(client, experiment_id):
    """A note is authoritative state, so capturing one is a real change to the record.

    MUTATION: removed the ``"notes"`` key from ``_authoritative_signature``'s
    payload. RED here and in the dismissal test below. Reverted.
    """
    before = _etag(client, experiment_id)
    before_version = client.get(f"/api/experiments/{experiment_id}").json()["version"]

    _captured(client, experiment_id)

    after = _etag(client, experiment_id)
    after_version = client.get(f"/api/experiments/{experiment_id}").json()["version"]
    assert after != before
    assert after_version != before_version


def test_dismissing_a_note_moves_the_experiment_version(client, experiment_id):
    """The one place "dismissal is an audited act" has to be true.

    A dismissal that does not move the version is one a concurrent write can erase
    without either writer noticing.

    MUTATION: as above. RED. Reverted.
    """
    note = _captured(client, experiment_id)
    before = _etag(client, experiment_id)

    response = _review(client, experiment_id, note["id"], action="dismiss")
    assert response.status_code == 200, response.text

    assert _etag(client, experiment_id) != before
    assert response.json()["experiment_version"] != before.strip('"').rsplit(".", 1)[0]


@pytest.mark.parametrize(
    "action,extra",
    [
        ("map", {"field_path": MAPPABLE}),
        ("keep", {}),
        ("dismiss", {}),
        ("dismiss", {"reason": "duplicate"}),
    ],
)
def test_repeating_an_act_that_changes_nothing_moves_no_version(
    client, experiment_id, action, extra
):
    """Idempotence, end to end. A double-click adds no audit row and no revision.

    This is the property that makes hashing the whole history safe: if a re-entry
    appended, every re-click would bump the record's revision and invalidate every
    other client's ETag for nothing.
    """
    note = _captured(client, experiment_id)
    first = _review(client, experiment_id, note["id"], action=action, **extra)
    assert first.status_code == 200, first.text
    settled = _etag(client, experiment_id)
    history_length = len(first.json()["note"]["history"])

    again = _review(client, experiment_id, note["id"], action=action, **extra)
    assert again.status_code == 200, again.text
    assert len(again.json()["note"]["history"]) == history_length
    assert _etag(client, experiment_id) == settled


def test_an_experiment_written_before_notes_existed_does_not_bump_its_version(
    client, experiment_id
):
    """The added state key must not cause a spurious revision on legacy state.

    A stored document with no ``notes`` key hydrates to an empty list and hashes
    exactly as an experiment whose notes are empty, so simply reading and re-saving
    a pre-feature record changes nothing.
    """
    path = ws.scope_root(client.tutorial_session_id) / experiment_id / "experiment.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state.pop("notes", None)
    path.write_text(json.dumps(state), encoding="utf-8")

    legacy = client_ws(client).load_experiment(experiment_id)
    assert legacy.notes == []
    assert legacy.unreadable_notes == []

    before = _etag(client, experiment_id)
    changed = legacy.save_versioned()
    assert changed is False
    assert _etag(client, experiment_id) == before


def test_notes_captured_in_a_worked_example_session_stay_inside_it(client, experiment_id):
    """Tutorial isolation. A note is experiment state, so it inherits the scope.

    BOTH HALVES ARE ASSERTED, and the first version of this test is the reason that
    sentence is here. It checked only that an UNSCOPED read is a 404 — which a route
    that ignores the session header entirely also satisfies, because then nobody can
    read the notes and the negative assertion passes for the wrong reason. The
    mutation below survived it. The scoped reads are what make the 404s mean
    "isolated" rather than "broken".

    MUTATION: made ``list_notes`` resolve with ``session_id=None``. First version:
    STILL GREEN — the defect this test exists to catch went undetected. With the
    scoped reads added: RED. Reverted.
    """
    note = _captured(client, experiment_id, text="captured inside the worked example")

    from isaac_api.app import create_app
    from fastapi.testclient import TestClient

    # 1. INSIDE the session, both reads work and return the note.
    listed = client.get(f"/api/experiments/{experiment_id}/notes")
    assert listed.status_code == 200, listed.text
    assert [n["id"] for n in listed.json()["notes"]] == [note["id"]]
    read = client.get(f"/api/experiments/{experiment_id}/notes/{note['id']}")
    assert read.status_code == 200, read.text
    assert read.json()["note"]["text"] == "captured inside the worked example"

    # 2. OUTSIDE it, the same ids are not reachable at all.
    unscoped = TestClient(create_app())

    assert unscoped.get(f"/api/experiments/{experiment_id}/notes").status_code == 404
    assert (
        unscoped.get(f"/api/experiments/{experiment_id}/notes/{note['id']}").status_code
        == 404
    )
    assert unscoped.get("/api/experiments").json()["experiments"] == []

    # A second session cannot see the first session's notes either.
    other = tutorial_client(create_app())
    assert other.get(f"/api/experiments/{experiment_id}/notes").status_code == 404


def test_a_note_never_reaches_an_exported_record(client):
    """The structural boundary: export reads ``draft``, and notes are not in it.

    Asserted against the artifacts on disk — the official record AND the evidence
    sidecar — rather than against the code path, so a future change that started
    threading notes into either would be caught wherever it was made.
    """
    experiments = client.get("/api/experiments").json()["experiments"]
    raw = [e for e in experiments if e["pending_count"] == 5]
    assert len(raw) == 1
    exp_id = raw[0]["id"]

    marker = "NOTE-MARKER-must-not-reach-an-official-record"
    _captured(client, exp_id, text=marker)

    pending = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]
    answers = {
        b["id"]: b["demo_answer"]["value"] for b in pending if b["demo_answer"] is not None
    }
    applied = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": _etag(client, exp_id)},
    )
    assert applied.status_code == 200, applied.text

    exported = client.post(
        f"/api/experiments/{exp_id}/export", headers={"If-Match": _etag(client, exp_id)}
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True

    records_dir = ws.scope_root(client.tutorial_session_id) / exp_id / "records"
    written = sorted(records_dir.glob("*.json"))
    assert written, "the export wrote no artifacts, so this test proves nothing"
    for artifact in written:
        text = artifact.read_text(encoding="utf-8")
        assert marker not in text, f"the note's text reached {artifact.name}"
        assert "unmapped_note" not in text, f"a note's status reached {artifact.name}"

    # ...and the note is still on the experiment, unchanged by the export.
    assert _stored(client, exp_id).notes[0].text == marker


# --- 6. concurrency: one validator, the record's ------------------------------


def test_capturing_without_an_if_match_is_a_428_and_writes_nothing(client, experiment_id):
    response = client.post(f"/api/experiments/{experiment_id}/notes", json={
        "text": "t", "source": "typed_note"
    })
    assert response.status_code == 428, response.text
    assert _stored(client, experiment_id).notes == []


def test_a_stale_if_match_is_a_412_and_the_note_is_not_captured(client, experiment_id):
    stale = _etag(client, experiment_id)
    _captured(client, experiment_id, text="the write that moved the version")

    response = client.post(
        f"/api/experiments/{experiment_id}/notes",
        json={"text": "should not land", "source": "typed_note"},
        headers={"If-Match": stale},
    )
    assert response.status_code == 412, response.text

    stored = _stored(client, experiment_id).notes
    assert [n.text for n in stored] == ["the write that moved the version"]


def test_a_stale_if_match_refuses_a_review_and_the_state_does_not_move(
    client, experiment_id
):
    note = _captured(client, experiment_id)
    stale = _etag(client, experiment_id)
    _captured(client, experiment_id, text="a second note moves the record on")

    response = _review(
        client, experiment_id, note["id"], action="dismiss", if_match=stale
    )
    assert response.status_code == 412, response.text
    assert _stored(client, experiment_id).get_note(note["id"]).state == "unreviewed"


def test_reviewing_without_confirmation_is_refused(client, experiment_id):
    note = _captured(client, experiment_id)
    response = client.post(
        f"/api/experiments/{experiment_id}/notes/{note['id']}/review",
        json={"action": "dismiss"},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "confirmation_required"
    assert _stored(client, experiment_id).get_note(note["id"]).state == "unreviewed"


def test_the_etag_a_note_read_returns_is_the_records(client, experiment_id):
    """Notes have no validator of their own, and a client must not invent one."""
    note = _captured(client, experiment_id)
    record_tag = _etag(client, experiment_id)
    for url in (
        f"/api/experiments/{experiment_id}/notes",
        f"/api/experiments/{experiment_id}/notes/{note['id']}",
    ):
        assert client.get(url).headers["ETag"] == record_tag


# --- 7. malformed payloads are typed 422s, never 500s -------------------------


@pytest.mark.parametrize(
    "body,expected_error",
    [
        ({"source": "typed_note"}, "invalid_note_text"),
        ({"text": "", "source": "typed_note"}, "invalid_note_text"),
        ({"text": "   ", "source": "typed_note"}, "invalid_note_text"),
        ({"text": 5, "source": "typed_note"}, "invalid_note_text"),
        ({"text": ["a"], "source": "typed_note"}, "invalid_note_text"),
        ({"text": {"a": 1}, "source": "typed_note"}, "invalid_note_text"),
        ({"text": None, "source": "typed_note"}, "invalid_note_text"),
        ({"text": "t"}, "unknown_note_source"),
        ({"text": "t", "source": "invented"}, "unknown_note_source"),
        ({"text": "t", "source": 7}, "unknown_note_source"),
        ({"text": "t", "source": None}, "unknown_note_source"),
        ({"text": "t", "source": "typed_note", "run_id": 7}, "unknown_run"),
        ({"text": "t", "source": "typed_note", "run_id": ""}, "unknown_run"),
        (
            {"text": "t", "source": "typed_note", "candidate_field_path": 7},
            "unrecognized_field",
        ),
        (
            {"text": "t", "source": "typed_note", "candidate_rule": "r"},
            "unsupported_note",
        ),
        (
            {
                "text": "t",
                "source": "typed_note",
                "candidate_field_path": MAPPABLE,
                "candidate_rule": 7,
            },
            "unsupported_note",
        ),
        ({"text": "t", "source": "typed_note", "note": "extra"}, "unrecognized_field"),
        ({"text": "t", "source": "typed_note", "evidence": []}, "unrecognized_field"),
    ],
)
def test_a_malformed_capture_is_a_typed_422_and_never_a_500(
    client, experiment_id, body, expected_error
):
    """Every wrong shape a client can send resolves to a NAMED refusal.

    A 500 here would be the wedged-record failure mode this repository has paid for
    twice: an unhandled exception inside ``record_lock``, a traceback on the wire,
    and no statement about whether anything was written.

    MUTATION: removed the ``except notes.UnsupportedNote`` handler around
    ``exp.capture_note``. RED on the two ``unsupported_note`` rows, which became
    uncaught ``UnsupportedNote`` exceptions. Reverted.
    """
    response = client.post(
        f"/api/experiments/{experiment_id}/notes",
        json=body,
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422, (body, response.status_code, response.text[:400])
    assert response.json()["error"] == expected_error, response.text
    assert _stored(client, experiment_id).notes == []


@pytest.mark.parametrize(
    "body,expected_error",
    [
        ({}, "unknown_note_action"),
        ({"action": "delete"}, "unknown_note_action"),
        ({"action": "capture"}, "unknown_note_action"),
        ({"action": 7}, "unknown_note_action"),
        ({"action": None}, "unknown_note_action"),
        ({"action": "map"}, "unrecognized_field"),
        ({"action": "map", "field_path": 7}, "unrecognized_field"),
        ({"action": "map", "field_path": ""}, "unrecognized_field"),
        ({"action": "edit"}, "invalid_note_text"),
        ({"action": "edit", "text": ""}, "invalid_note_text"),
        ({"action": "edit", "text": 7}, "invalid_note_text"),
        ({"action": "dismiss", "reason": 7}, "invalid_note_text"),
        ({"action": "dismiss", "reason": ""}, "invalid_note_text"),
        ({"action": "keep", "verified": True}, "unrecognized_field"),
        ({"action": "keep", "state": "mapped"}, "unrecognized_field"),
    ],
)
def test_a_malformed_review_is_a_typed_422_and_never_a_500(
    client, experiment_id, body, expected_error
):
    note = _captured(client, experiment_id)
    response = client.post(
        f"/api/experiments/{experiment_id}/notes/{note['id']}/review",
        json={"confirmed_by_user": True, **body},
        headers={"If-Match": _etag(client, experiment_id)},
    )
    assert response.status_code == 422, (body, response.status_code, response.text[:400])
    assert response.json()["error"] == expected_error, response.text
    # Nothing partial was left behind.
    stored = _stored(client, experiment_id).get_note(note["id"])
    assert stored.state == "unreviewed"
    assert stored.revised_text is None
    assert stored.mapped_field_path is None
    assert [e.action for e in stored.history] == ["capture"]


def test_an_unknown_note_is_a_404_that_names_the_note_not_the_experiment(
    client, experiment_id
):
    response = client.get(f"/api/experiments/{experiment_id}/notes/NOPE")
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"] == "note_not_found"
    assert body["experiment_id"] == experiment_id
    assert body["id"] == "NOPE"


def test_notes_of_an_unknown_experiment_are_a_404(client):
    assert client.get("/api/experiments/NOT-A-RECORD/notes").status_code == 404
    response = client.post(
        "/api/experiments/NOT-A-RECORD/notes",
        json={"text": "t", "source": "typed_note"},
        headers={"If-Match": '"whatever.0"'},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "experiment_not_found"


# --- 8. the list contract -----------------------------------------------------


def test_the_list_reports_the_server_s_own_mappable_paths_and_sources(
    client, experiment_id
):
    """The control a client offers and the request the server accepts are ONE expression.

    Transcribing either into the frontend bundle would let them drift, and the
    drift would show up as a control that offers a path the server refuses.
    """
    body = client.get(f"/api/experiments/{experiment_id}/notes").json()
    assert body["mappable_field_paths"] == sorted(routes.NOTE_MAPPABLE_FIELD_PATHS)
    assert body["sources"] == sorted(notes.NOTE_SOURCES)
    assert MAPPABLE in body["mappable_field_paths"]


def test_notes_are_listed_oldest_capture_first_and_the_order_is_total(
    client, experiment_id
):
    """Canonical order, and dismissing does not move a note under the reader's cursor."""
    ids = [_captured(client, experiment_id, text=f"note {n}")["id"] for n in range(5)]
    listed = client.get(f"/api/experiments/{experiment_id}/notes").json()["notes"]
    assert [n["id"] for n in listed] == ids

    _review(client, experiment_id, ids[1], action="dismiss")
    after = client.get(f"/api/experiments/{experiment_id}/notes").json()["notes"]
    assert [n["id"] for n in after] == ids


def test_an_empty_record_reports_zero_rather_than_omitting_the_counts(
    client, experiment_id
):
    """An honest empty state needs the numbers to exist, not to be absent."""
    body = client.get(f"/api/experiments/{experiment_id}/notes").json()
    assert body["notes"] == []
    assert body["total"] == 0
    assert body["returned"] == 0
    assert body["unreadable_entries"] == 0
    assert body["by_state"] == {"unreviewed": 0, "mapped": 0, "kept": 0, "dismissed": 0}

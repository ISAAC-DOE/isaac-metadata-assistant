"""THE ASSISTANT NAMED THREE OUTSTANDING FIELDS ON A FINISHED RECORD.

WHAT WAS MEASURED, over HTTP, on a record created through this application's own
``POST /api/experiments`` path with one run whose every run-level question was answered
ON THE RUN::

    exp.pending()                       -> 0        export_ready() -> True
    GET /pending                        -> 0
    GET /experiments/{id}               -> pending_count 0
    pending_to_list(exp.draft, ...)     -> 3   ['series', 'qc', 'descriptor']

    "Is this record ready to export?"
       -> "... On this record, 3 fields still need you."
    "What fields are still pending?"
       -> "3 fields still need you: reduced_spectrum, qc_status,
           required_for_evidence_record."
    POST /api/experiments/{id}/answers {"series": ...}   -> 409 belongs_to_a_run

Every one of the three was already answered on the run AND unanswerable at the record
level by design — ``Experiment.pending()`` WITHHOLDS a record's run-level questions once
a run exists precisely because ``_refuse_run_level_on_the_record`` refuses them. So the
assistant sent a scientist to answer questions that no route accepts, about a record that
was finished.

THE CAUSE was the one remaining run-blind ``serialize.pending_to_list`` call site in
``routes.py``: the ``AssistantContext`` construction passed no ``entries=``, so it read
``exp.draft["pending"]`` directly. Every other call site — ``GET /pending``, both
``/answers`` responses, the run check, the run ``/answers`` response — had already been
corrected, and the comment on the first of them names the defect in the same words.

THE ASSISTANT ALSO CONTRADICTED ITSELF IN ONE SESSION, which is what makes this a
truthfulness defect rather than a stale number. The ``record`` intent reads
``_summary(exp)["pending_count"]``, i.e. ``exp.pending_count()``, which was already
run-aware. So "summarize this record" said 0 pending while "what still needs me?" said 3.

WHY THE EXISTING SUITE DID NOT CATCH IT. Every assistant test drives one of the five
canonical seeds, and a seed has no runs — for a zero-run experiment ``Experiment.pending()``
returns ``draft["pending"]`` unchanged, so the defective and the correct call are
byte-identical there. The blind spot is the same one
``test_scientist_can_finish_a_record.py`` exists for, one surface over. This file
therefore borrows no seed and no demo answer: it creates a record and writes out the
values a person would type.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

import isaac_api.assistant_query as aq
import isaac_api.workspace as ws

#: Written out rather than harvested, for the reason in the docstring. Deliberately the
#: same shapes ``test_scientist_can_finish_a_record`` uses, imported rather than copied
#: so the two files cannot drift about what a valid answer looks like.
from test_scientist_can_finish_a_record import DESCRIPTOR, QC, SERIES


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A plain client on an empty workspace — NO worked-example session, no seeds."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _version(client, exp_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}").json()["version"]


def _ask(client, exp_id: str, question: str) -> str:
    r = client.post(f"/api/experiments/{exp_id}/assistant/query", json={"question": question})
    assert r.status_code == 200, r.text
    return r.json()["answer"]


def _finished_record_with_one_run(client) -> str:
    """create -> add a run -> answer every run-level question ON THE RUN."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge XANES"}).json()["id"]
    added = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "300 K"},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert added.status_code == 201, added.text
    run = ws.load_experiment(exp_id).runs[0]
    answered = client.post(
        f"/api/experiments/{exp_id}/runs/{run.id}/answers",
        json={
            "answers": {"series": SERIES, "descriptor": DESCRIPTOR, "qc": QC},
            "confirmed_by_user": True,
        },
        headers={"If-Match": f'"{run.version_token()}"'},
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["pending"] == [], answered.json()["pending"]
    return exp_id


def test_the_record_really_is_finished_and_its_draft_really_does_still_list_three(client):
    """THE PRECONDITION OF THE WHOLE FILE, asserted rather than assumed.

    If these two stopped disagreeing the tests below would pass for the wrong reason —
    they would be measuring a record with nothing withheld. The gap between
    ``exp.pending()`` and ``exp.draft["pending"]`` IS the trap, so it is pinned.
    """
    exp_id = _finished_record_with_one_run(client)
    exp = ws.load_experiment(exp_id)

    assert exp.pending() == []
    assert exp.export_ready() is True
    assert client.get(f"/api/experiments/{exp_id}/pending").json()["pending"] == []
    assert client.get(f"/api/experiments/{exp_id}").json()["pending_count"] == 0

    # The withheld copies are still IN the document — `pending()` is a derived view.
    withheld = {e.get("kind") for e in exp.draft["pending"]}
    assert withheld == {"series", "qc", "descriptor"}, exp.draft["pending"]

    # …and they are unanswerable where the assistant was pointing.
    refused = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"series": SERIES}, "confirmed_by_user": True},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"] == "belongs_to_a_run"


def test_the_assistant_does_not_name_pending_fields_on_a_finished_record(client):
    """THE REGRESSION. It used to answer with three names, every one a dead end."""
    exp_id = _finished_record_with_one_run(client)

    answer = _ask(client, exp_id, "what fields are still pending?")
    assert answer == "No pending fields are listed for this record.", answer
    for name in ("reduced_spectrum", "qc_status", "required_for_evidence_record"):
        assert name not in answer, answer


def test_the_readiness_answer_counts_what_is_actually_open(client):
    """It used to read "On this record, 3 fields still need you" on a ready record."""
    exp_id = _finished_record_with_one_run(client)

    answer = _ask(client, exp_id, "is this record ready to export?")
    assert "On this record, 0 fields still need you." in answer, answer
    assert "3 fields" not in answer, answer


def test_the_assistant_does_not_contradict_itself_within_one_session(client):
    """Two intents, one record, one count. They disagreed 0 vs 3.

    The `record` intent reads `_summary(exp)["pending_count"]`, which was already
    run-aware; the other two read the assistant's own `pending` context, which was not.
    """
    exp_id = _finished_record_with_one_run(client)

    summary = _ask(client, exp_id, "summarize this record")
    assert "0 pending fields" in summary, summary
    assert "0 fields still need you" in _ask(client, exp_id, "is this ready to export?")
    assert _ask(client, exp_id, "what still needs me?") == (
        "No pending fields are listed for this record."
    )


def test_a_run_owned_question_is_named_with_the_run_that_owns_it(client):
    """COHERENCE FOR A MULTI-RUN RECORD, which the count fix alone does not give.

    Passing `entries=exp.pending()` makes the assistant see the RUNS' questions, and
    three runs each needing a spectrum produce three entries whose `about` is
    byte-identical. Composed without the run, that reads as three different fields of
    the record — when it is one field of three different runs, each answerable only at
    the run's own answers operation.
    """
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    for label in ("300 K", "400 K"):
        client.post(
            f"/api/experiments/{exp_id}/runs",
            json={"label": label},
            headers={"If-Match": f'"{_version(client, exp_id)}"'},
        )
    assert client.get(f"/api/experiments/{exp_id}").json()["pending_count"] == 6

    answer = _ask(client, exp_id, "what still needs me?")
    assert answer.startswith("6 fields still need you:"), answer
    assert "reduced_spectrum (on run 300 K)" in answer, answer
    # No bare, unqualified repetition of the same label.
    assert "you: reduced_spectrum," not in answer, answer


def test_a_run_created_without_a_label_still_gets_a_name_not_a_null(client):
    """Over HTTP the route names the run itself ("Run 1"), so this asserts what
    actually ships rather than the defensive branch below it."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    client.post(
        f"/api/experiments/{exp_id}/runs",
        json={},
        headers={"If-Match": f'"{_version(client, exp_id)}"'},
    )
    answer = _ask(client, exp_id, "what still needs me?")
    assert "(on run Run 1)" in answer, answer
    assert "None" not in answer and "null" not in answer, answer


def test_a_missing_run_label_reads_as_unlabelled_rather_than_interpolated():
    """THE DEFENSIVE BRANCH, and it is labelled as defensive rather than implied live.

    ``POST /runs`` mints "Run N" when no label is given, so no shipped producer reaches
    this. It exists because ``Experiment.pending()`` copies ``run.label`` verbatim and
    the run contract types it ``string | null`` — the same reason ``RunFindings.labelFor``
    has a fallback, and the defect ``fan-out-null-render`` exists for.
    """
    for absent in ({}, {"run_label": None}, {"run_label": "   "}):
        labels = aq._pending_labels([{"about": "reduced_spectrum", "run_id": "01RUN", **absent}])
        assert labels == ["reduced_spectrum (on an unlabelled run)"], (absent, labels)


@pytest.mark.parametrize("label", ["/Users/me/secret", "valid against v1.05"])
def test_an_unsafe_or_verdict_bearing_run_label_is_withheld_not_propagated(label):
    """THE RUN LABEL IS THE FIRST USER-SUPPLIED STRING TO ENTER A COMPOSED ANSWER.

    It is scrubbed per-fragment rather than left to the whole-answer guard in
    ``assistant_query.answer``, which replaces the ENTIRE text on a hit — so a run named
    ``/Users/me`` or ``valid`` would otherwise have blanked the pending list itself,
    letting the naming of a run decide whether the assistant answers at all.

    Asserted at the composer rather than over HTTP because ``_join_capped`` caps the
    rendered list at three entries, so an unsafe label on a fourth run never reaches the
    text and the guard would go untested.
    """
    labels = aq._pending_labels(
        [{"about": "reduced_spectrum", "run_id": "01RUN", "run_label": label}]
    )
    assert labels == ["reduced_spectrum (on a run whose label is withheld)"], labels
    assert label not in labels[0]


def test_a_record_level_question_is_not_attributed_to_any_run(client):
    """The other direction: an untagged entry gets no clause invented for it."""
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    answer = _ask(client, exp_id, "what still needs me?")
    assert "(on " not in answer, answer
    assert "3 fields still need you: reduced_spectrum," in answer, answer


def test_a_zero_run_record_is_unmoved_by_the_fix(client):
    """The guarantee that keeps every seeded scenario's answer byte-identical.

    ``Experiment.pending()`` returns ``draft["pending"]`` unchanged when there are no
    runs, so passing ``entries=`` cannot change a zero-run answer. Measured here rather
    than argued: the same record, both derivations, same composed labels.
    """
    exp_id = client.post("/api/experiments", json={"title": "Cu K-edge"}).json()["id"]
    exp = ws.load_experiment(exp_id)
    assert exp.pending() == exp.draft["pending"]

    import isaac_api.serialize as serialize

    run_blind = serialize.pending_to_list(exp.draft, ws.load_demo_answers())
    run_aware = serialize.pending_to_list(
        exp.draft, ws.load_demo_answers(), entries=exp.pending()
    )
    assert run_blind == run_aware
    assert aq._pending_labels(run_blind["pending"]) == aq._pending_labels(
        run_aware["pending"]
    )


def test_the_assistant_still_mutates_nothing(client):
    """Read-only, re-asserted on the path this file changed."""
    exp_id = _finished_record_with_one_run(client)
    before = client.get(f"/api/experiments/{exp_id}").json()
    stored = copy.deepcopy(ws.load_experiment(exp_id).draft)

    for q in ("what still needs me?", "is this ready to export?", "summarize this record"):
        _ask(client, exp_id, q)

    after = client.get(f"/api/experiments/{exp_id}").json()
    assert after["rev"] == before["rev"]
    assert after["version"] == before["version"]
    assert ws.load_experiment(exp_id).draft == stored

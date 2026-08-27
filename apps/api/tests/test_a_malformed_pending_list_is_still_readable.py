"""A persisted ``pending`` that is not a list must not take the reader's record away.

WHY THIS FILE EXISTS. Both derivations of the open-question list read the stored value
with ``list(...)``, so a document holding a NON-ITERABLE ``pending`` raised
``TypeError: 'int' object is not iterable`` on a GET. Measured over HTTP on
``721238a``, with ``draft["pending"] = 7`` written into the persisted state:

===============================================  ====================
request                                          before
===============================================  ====================
``GET /api/experiments/{id}``  (run-level)       **500**
``GET /api/experiments``       (run-level)       **500**
``GET /api/experiments/{id}``  (record-level)    **500**
===============================================  ====================

The middle row is the one that decides the severity: ONE malformed run draft took down
**My Experiments for the whole workspace**, not just its own record.

THE DESIGN, AND WHY IT IS NOT A TYPED ERROR. ``CLAUDE.md`` §11 records the sibling
family — "a wrong-typed structured answer used to return HTTP 500 from the truth core.
A typed 422 is a deliberate follow-up" — and this programme built that typed refusal for
the ANSWER path. This is the same shape on the READ path, and the difference is
decisive: a malformed value arriving in a REQUEST can be refused, because the caller
sent it and a 422 names what to fix; a malformed value already PERSISTED cannot be
refused to the reader, who did nothing wrong and whose record would simply disappear.

So the read degrades, and it degrades ONTO THE POSTURE THIS MODULE ALREADY HAS rather
than inventing a new one. ``Experiment.pending`` passes a non-dict ENTRY through as-is
— "this is a derived view, not a place to start repairing documents" — and
``pending_count`` counts it as one. A non-iterable ``pending`` is exactly one value this
module cannot read, so it becomes exactly one entry, the value itself, unrepaired. The
record therefore stays blocked, which is the truthful answer: a document whose blocker
list cannot be read must not be certified export-ready.

THREE THINGS THAT WERE REJECTED, each because it would tell the reader something false:

* **``[]`` — "nothing is pending."** It is the smallest patch and it is a lie: it moves
  the record to ``status: in_review``, files it in My Experiments as needing nothing,
  and unblocks the export gate on a document nobody could read.
* **A typed error on the read.** See above; it hides the record from its owner.
* **Coercion — parsing, wrapping, or repairing the stored value.** That turns a broken
  document into a plausible one, which ``CLAUDE.md`` §5 exists to prevent.

~~WHAT THIS DELIBERATELY DOES NOT FIX, pinned at the bottom so it is visible rather than
implied: ``serialize.pending_to_list`` calls ``entry.get("kind")`` and so still 500s on
a non-dict entry. That is a PRE-EXISTING defect of the malformed-ENTRY case
(``pending: [7]``), not of this one, and the last test asserts the two now behave
IDENTICALLY — which is the whole claim this change makes.~~

**THE RESIDUE NAMED ABOVE IS CLOSED, and the paragraph is struck rather than deleted so
a reader can see that this file's claim was scoped rather than wrong.** The malformed
ENTRY now serves as one entry marked ``unavailable`` with a reason naming the shape
(``serialize._unreadable_blocker``), so ``GET /pending`` answers **200** where every row
of the table above was **500**. The equality test at the bottom is UNCHANGED and still
passing — which is exactly what it said would happen: "if the shared behaviour is later
fixed — it will still pass, and it will still be pinning the thing this change actually
did." The new behaviour, its rejected alternatives and the two write-path refusals that
are still 500 are pinned in
``apps/api/tests/test_a_malformed_pending_entry_is_served_not_500.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from isaac_api import experiment_repository as repo
from isaac_api import workspace as ws

#: The stored value under test. Non-iterable, and TRUTHY — a falsy one (``0``, ``""``,
#: ``None``) has always been normalised to the empty list by the ``or []`` this code has
#: carried since it was written, and that tolerance is untouched here.
MALFORMED = 7


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    """A NORMAL-scope client. Not the tutorial fixture: this is about a record the
    product itself creates, and the worked-example scope refuses persistence."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _create(client: TestClient) -> str:
    resp = client.post("/api/experiments", json={"title": "malformed pending"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _add_run(client: TestClient, exp_id: str) -> None:
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    resp = client.post(
        f"/api/experiments/{exp_id}/runs",
        json={"label": "Run 1"},
        headers={"If-Match": f'"{version}"'},
    )
    assert resp.status_code == 201, resp.text


def _persist_malformed(exp_id: str, *, on_run: bool) -> None:
    """Write the malformed value the way it can actually come to exist.

    NO SHIPPED WRITE PATH PRODUCES THIS. ``complete.apply_answers`` assigns
    ``draft["pending"] = remaining_pending``, a list it built itself;
    ``routes._seed_for_new_run`` deep-copies template entries; ``blank_draft`` is
    literals. The reachable producers are an operator editing the persisted state — the
    workspace JSON, or the ``isaac_experiments.state`` JSONB in the app-owned database —
    and any future importer or migration. This test therefore edits the store directly,
    which is an honest reproduction of the only way the state arises rather than a
    convenience shortcut around a route that would refuse it.
    """
    exp = ws.load_experiment(exp_id)
    assert exp is not None
    target = exp.runs[0].draft if on_run else exp.draft
    target["pending"] = MALFORMED
    exp.save()


# --- the read survives --------------------------------------------------------


@pytest.mark.parametrize("on_run", [False, True], ids=["record-level", "run-level"])
def test_the_record_and_the_whole_list_are_still_readable(client: TestClient, on_run: bool):
    exp_id = _create(client)
    if on_run:
        _add_run(client, exp_id)
    _persist_malformed(exp_id, on_run=on_run)

    detail = client.get(f"/api/experiments/{exp_id}")
    assert detail.status_code == 200, detail.text
    listing = client.get("/api/experiments")
    assert listing.status_code == 200, listing.text
    assert any(e["id"] == exp_id for e in listing.json()["experiments"])


@pytest.mark.parametrize("on_run", [False, True], ids=["record-level", "run-level"])
def test_the_reader_is_not_told_the_record_needs_nothing(client: TestClient, on_run: bool):
    """THE REJECTED-ALTERNATIVE GUARD. Degrading to ``[]`` would pass every test above
    and would report a document nobody could read as needing no attention."""
    exp_id = _create(client)
    if on_run:
        _add_run(client, exp_id)
    _persist_malformed(exp_id, on_run=on_run)

    body = client.get(f"/api/experiments/{exp_id}").json()
    assert body["pending_count"] >= 1, body
    assert body["status"] == "needs_attention", body

    # The gate itself, not only what the response says about it. `export_ready` is not
    # a key on this payload — it is a derivation the route reads — so it is asserted
    # where it lives, and a future response-shape change cannot quietly drop the check.
    exp = ws.load_experiment(exp_id)
    assert exp is not None
    assert exp.export_ready() is False


@pytest.mark.parametrize("on_run", [False, True], ids=["record-level", "run-level"])
def test_the_document_is_not_repaired_by_being_read(client: TestClient, on_run: bool):
    """NO SILENT COERCION. Several reads later the stored value is byte-identical."""
    exp_id = _create(client)
    if on_run:
        _add_run(client, exp_id)
    _persist_malformed(exp_id, on_run=on_run)

    for _ in range(3):
        assert client.get(f"/api/experiments/{exp_id}").status_code == 200
        assert client.get("/api/experiments").status_code == 200

    exp = ws.load_experiment(exp_id)
    stored = (exp.runs[0].draft if on_run else exp.draft)["pending"]
    assert stored == MALFORMED and isinstance(stored, int), stored


# --- what the derivations actually answer -------------------------------------


def test_a_non_iterable_becomes_exactly_one_entry_and_it_is_the_stored_value():
    """ONE entry, and NOTHING IS INVENTED: the entry IS the value, not a synthesised
    question standing in for it. A wrapper would be this module deciding what the
    document meant."""
    run = ws.new_run("01EXP", ordinal=1, draft={"pending": MALFORMED})
    assert ws.run_questions(run) == [MALFORMED]
    assert ws.run_question_count(run) == 1


def test_the_binding_invariant_holds_on_the_broken_document():
    """``pending_count() == len(pending())`` — the invariant
    ``test_pending_count_is_not_materialised.py`` exists to protect — on the input least
    able to survive two derivations disagreeing."""
    for on_run in (False, True):
        draft = repo.blank_draft()
        exp = ws.Experiment(
            id="01MALFORMEDPENDINGGUARD0000",
            title="malformed",
            created_utc="2026-08-25T00:00:00Z",
            source={},
            draft=draft,
        )
        if on_run:
            exp.add_run(label="Run 1", draft={"pending": MALFORMED}, id="01RUNMALFORMED000000000000")
        else:
            draft["pending"] = MALFORMED
        assert exp.pending_count() == len(exp.pending()), on_run
        assert exp.pending_count() >= 1, on_run


def test_the_ITERABLE_malformed_cases_are_untouched():
    """REGRESSION GUARD on behaviour this repository already decided and PINNED.

    ``test_a_non_list_pending_document_counts_the_same_way_the_list_does`` asserts a
    stored dict yields its KEYS. That is not a fabrication — the keys become non-dict
    entries, which every surface already treats as unreadable — and it is not this
    change's to revisit. Only the NON-iterable case, which had no behaviour at all
    because it raised, is given one.
    """
    run = ws.new_run("01EXP", ordinal=1, draft={"pending": {"a": 1, "b": 2}})
    assert ws.run_questions(run) == ["a", "b"]
    assert ws.run_question_count(run) == 2

    run = ws.new_run("01EXP", ordinal=2, draft={"pending": "abc"})
    assert ws.run_questions(run) == ["a", "b", "c"]
    assert ws.run_question_count(run) == 3

    for falsy in (0, "", None, [], {}):
        run = ws.new_run("01EXP", ordinal=3, draft={"pending": falsy})
        assert ws.run_questions(run) == [], falsy
        assert ws.run_question_count(run) == 0, falsy


def test_the_list_returned_is_a_copy_so_a_caller_cannot_reach_the_stored_document():
    """``run_questions`` has always returned ``list(...)``, and ``routes._apply_to_run``
    materialises what it returns into a run's draft before writing. A degradation that
    handed back a view of stored state would be a new aliasing bug wearing a fix."""
    run = ws.new_run("01EXP", ordinal=1, draft={"pending": MALFORMED})
    got = ws.run_questions(run)
    got.append("mutated by the caller")
    assert run.draft["pending"] == MALFORMED
    assert ws.run_questions(run) == [MALFORMED]

    # THE ORDINARY STORED-LIST BRANCH TOO. Asserting only the non-iterable branch was
    # NOT enough and this is not a hypothetical: `[raw]` is a fresh list by
    # construction, so that half of the test passes under an implementation that hands
    # a stored list straight back. Mutation-tested — replacing `list(raw)` with `raw`
    # left the first half green and is caught only here.
    run = ws.new_run("01EXP", ordinal=2, draft={"pending": [{"kind": "series"}]})
    got = ws.run_questions(run)
    got.append("mutated by the caller")
    assert run.draft["pending"] == [{"kind": "series"}]
    assert ws.run_questions(run) == [{"kind": "series"}]


# --- the residue, named rather than implied -----------------------------------


def test_the_non_iterable_case_now_behaves_EXACTLY_like_the_malformed_entry_case(
    client: TestClient,
):
    """THE CLAIM THIS CHANGE MAKES, asserted as an equality rather than as a status code.

    ~~``GET /pending`` renders entries through ``serialize.pending_to_list``, which calls
    ``entry.get("kind")`` and so fails on ANY non-dict entry. That is a pre-existing
    defect of the malformed-ENTRY case and is deliberately NOT fixed here — fixing it
    means deciding what a client is shown for an unreadable blocker, which is a response
    contract, not a read guard.~~ **That decision has since been made** — the response
    contract is ``unavailable`` + ``unavailable_reason`` on a served entry
    (``serialize._unreadable_blocker``) — so both cases are now **200** here. The
    paragraph is struck rather than rewritten because it is the reason this test was
    written as an EQUALITY, and the next paragraph is what makes that survive the fix.

    What this change is entitled to claim is CONVERGENCE: ``pending: 7`` is no longer a
    separate, worse failure than ``pending: [7]``. Asserting the two are equal keeps the
    test honest if the shared behaviour is later fixed — it will still pass, and it will
    still be pinning the thing this change actually did.
    """
    statuses = {}
    for label, value in (("wrapped", [MALFORMED]), ("bare", MALFORMED)):
        exp_id = _create(client)
        exp = ws.load_experiment(exp_id)
        exp.draft["pending"] = value
        exp.save()
        statuses[label] = {
            "detail": client.get(f"/api/experiments/{exp_id}").status_code,
            "list": client.get("/api/experiments").status_code,
            "pending": client.get(f"/api/experiments/{exp_id}/pending").status_code,
        }
    assert statuses["bare"] == statuses["wrapped"], statuses
    # And the two that this change IS responsible for are green in both.
    assert statuses["bare"]["detail"] == 200 and statuses["bare"]["list"] == 200, statuses


# --- the sibling defect, at the same layer -----------------------------------
#
# The `assets` half of this change was closed in `src/isaac_records/draft_validator.py`
# and covered only by unit-level `validate_draft` tests. That leaves the HTTP symptom
# — the one actually measured, and the one a scientist would report — pinned nowhere,
# so a route-layer change could re-open the 500 with nothing failing. It is pinned
# here, beside the `pending` case it is a sibling of, because both are the same
# question: a persisted document the reader did not write must not take their record
# away.


def _persist_wrong_typed_container(exp_id: str, name: str, value: object) -> None:
    """Same honest reproduction as :func:`_persist_malformed` — see its docstring.

    A wrong-typed top-level container has no shipped producer either: block overrides
    are type-gated by the vendored schema and run-level blocks are refused outright.
    An operator edit of the persisted state, or a future importer, is the reachable
    route to it.
    """
    exp = ws.load_experiment(exp_id)
    assert exp is not None
    exp.draft[name] = value
    exp.save()


@pytest.mark.parametrize(
    "name, value",
    [
        ("assets", "not a list"),
        ("descriptors_outputs", "not a list"),
        ("attribution", "not an object"),
        ("meta", 7),
    ],
    ids=["assets", "descriptors_outputs", "attribution", "meta"],
)
def test_a_wrong_typed_container_does_not_500_the_read(client: TestClient, name, value):
    """Measured on ``721238a``: each of these returned **500** from ``GET
    /api/experiments/{id}``, because ``Experiment.draft_ok`` reaches ``validate_draft``
    and the walk hit ``.get`` on the wrong type. The listing survived (it does not
    validate), which is the one way this family is less severe than the ``pending`` one.
    """
    exp_id = _create(client)
    _persist_wrong_typed_container(exp_id, name, value)

    detail = client.get(f"/api/experiments/{exp_id}")
    assert detail.status_code == 200, detail.text
    assert client.get("/api/experiments").status_code == 200


def test_the_reader_is_not_told_a_malformed_container_is_export_ready(client: TestClient):
    """THE REJECTED-ALTERNATIVE GUARD, again. Swallowing the wrong type without filing a
    finding would return 200 and leave the export gate open on an unreadable document.
    The record must stay refused, and the refusal must name the container."""
    exp_id = _create(client)
    _persist_wrong_typed_container(exp_id, "assets", "not a list")

    exp = ws.load_experiment(exp_id)
    assert exp is not None
    assert exp.draft_ok() is False
    assert exp.export_ready() is False

    # AND THE REFUSAL NAMES THE CONTAINER. `draft_ok` is a boolean, so asserting on it
    # alone would also pass if the draft were refused for some unrelated reason; the
    # report is read directly from the module that produces it. (An earlier revision of
    # this test guarded that assertion behind `hasattr(exp, "draft_report")` — a method
    # that does not exist — so the assertion never ran at all. Kept as a note because a
    # never-executed assertion reads exactly like a passing one.)
    from isaac_records.draft_validator import validate_draft

    report = validate_draft(exp.draft)
    assert [where for where, _ in report.errors] == ["assets"], report.errors

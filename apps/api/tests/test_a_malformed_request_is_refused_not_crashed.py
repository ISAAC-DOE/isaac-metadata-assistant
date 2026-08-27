"""A malformed value in a REQUEST gets a typed 4xx. Three families, one rule.

THE GOVERNING RULE, from PR #177, and it is what separates this file from
``test_one_malformed_document_does_not_take_down_the_list.py``: *a malformed value in a
REQUEST can be refused, because the caller sent it and a typed 422 names what to fix; a
malformed value already PERSISTED cannot be refused to the reader, who did nothing wrong
and whose record would simply vanish.* Everything here arrives in a request, so
everything here is a refusal.

THE THREE FAMILIES, each measured over HTTP on ``cde8d7c``:

**F3 — ``answers`` that is not an object.** All four write operations read it as
``(body.get("answers") or {}).items()``, and ``or {}`` is not a type guard: it catches
``None`` and every wrong type is truthy. **24 measured 500s** — four operations by six
values (``"str"``, ``5``, ``1.5``, ``True``, ``[1]``, ``[{"a": 1}]``).

**F4 — an unhashable value against a ``frozenset``.** ``source not in NOTE_SOURCES``
and ``action not in NOTE_ACTIONS`` HASH their operand, so a ``dict`` or ``list`` raised
``TypeError: unhashable type`` — **two lines above a correct typed refusal that already
existed and already anticipated a non-string**. The fix lets the wrong type REACH that
refusal rather than writing a second one, which is why the assertions below pin the
existing error codes rather than new ones.

**F5 — an ``experiment_id`` at or above 256 bytes.** The untrusted segment becomes a
filesystem path COMPONENT and ``Path.exists()`` raises ``OSError: File name too long``
instead of answering ``False``. Measured: 255 → 404, **256 → 500**, 4096 → 500.

**WHY A NAIVE FUZZ SWEEP FINDS NONE OF THIS**, recorded because the audit that found it
nearly shipped a clean bill of health from a 728-request sweep that returned zero 500s.
Every write operation refuses a body without ``confirmed_by_user: true`` BEFORE it
reads ``answers``; the two RUN operations additionally check ``If-Match`` first, and a
run's ``If-Match`` is **the RUN's token, not the record's**. A corpus that satisfies
neither precondition returns a tidy sweep of 422s and 412s and never reaches the line
that raises. The helpers below exist to actually get there, and
``test_the_preconditions_really_do_gate_the_crash_line`` pins that they do.

Every fixture is synthetic and hand-built. Nothing here reads real data.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from isaac_api import notes
from isaac_api.app import create_app
from isaac_api.routes import _EXPERIMENT_ID_MAX_LENGTH

#: Wrong types that are TRUTHY. Each of these was a measured 500 on all four
#: `answers` operations.
TRUTHY_WRONG = ["str", 5, 1.5, True, [1], [{"a": 1}]]

#: Wrong types that are FALSY. These never crashed — `or {}` read them as the empty
#: map — and their change of status is a deliberate BEHAVIOUR CHANGE, pinned
#: separately below so it can never be mistaken for part of the crash fix.
FALSY_WRONG = [0, "", False, []]

#: Unhashable values. `in` against a `frozenset` hashes its operand.
UNHASHABLE = [{}, [], {"a": 1}, [1]]

#: Hashable non-members. THE CONTROL that makes F4 a defect rather than a design:
#: these always returned the intended typed 422.
HASHABLE_NON_MEMBERS = ["invented", 5, None, True]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def experiment(client) -> str:
    r = client.post("/api/experiments", json={"title": "Refusal probe"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _experiment_etag(client, exp_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}").headers["ETag"]


@pytest.fixture()
def run(client, experiment):
    """A run, plus a way to get ITS etag — which is not the record's.

    Adding a run needs the RECORD's token; editing one needs the RUN's. Getting that
    backwards is how a probe gets 412 forever and concludes the route is safe.
    """
    r = client.post(
        f"/api/experiments/{experiment}/runs",
        json={"label": "Run 1"},
        headers={"If-Match": _experiment_etag(client, experiment)},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["run"]["id"]


def _run_etag(client, exp_id: str, run_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}/runs/{run_id}").headers["ETag"]


def _post_answers(client, exp_id, run_id, *, operation: str, value):
    """POST one of the four operations with a CURRENT precondition token."""
    if operation.startswith("run"):
        url = f"/api/experiments/{exp_id}/runs/{run_id}/{operation.split('/')[1]}"
        etag = _run_etag(client, exp_id, run_id)
    else:
        url = f"/api/experiments/{exp_id}/{operation.split('/')[1]}"
        etag = _experiment_etag(client, exp_id)
    return client.post(
        url,
        json={"confirmed_by_user": True, "answers": value},
        headers={"If-Match": etag},
    )


OPERATIONS = ["exp/answers", "exp/edit", "run/answers", "run/edit"]


# --- F3 -----------------------------------------------------------------------


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("value", TRUTHY_WRONG)
def test_answers_that_is_not_an_object_is_refused(client, experiment, run, operation, value):
    """Was **500** for all 24 combinations; is **422 invalid_body**."""
    response = _post_answers(client, experiment, run, operation=operation, value=value)
    assert response.status_code == 422, (operation, value, response.status_code)
    body = response.json()
    assert body["error"] == "invalid_body"
    assert body["experiment_id"] == experiment
    if operation.startswith("run"):
        assert body["run_id"] == run
    else:
        assert "run_id" not in body


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("value", TRUTHY_WRONG)
def test_a_refused_body_is_never_echoed_back(client, experiment, run, operation, value):
    """The refusal names neither the value nor its type.

    Echoing client-supplied content of unknown size and nesting back into an error
    body is how a refusal becomes a reflection surface — the same reason
    ``_refuse_unstorable_answer`` names ``key``/``keys`` and never a value.
    """
    response = _post_answers(client, experiment, run, operation=operation, value=value)
    assert response.status_code == 422
    text = response.text
    for marker in ("str", "1.5", "{'a': 1}", '"a": 1'):
        if marker == "str":
            # `str` appears in no legitimate part of this body.
            assert "'str'" not in text and '"str"' not in text
        else:
            assert marker not in text


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("value", FALSY_WRONG)
def test_a_falsy_wrong_typed_answers_is_also_refused(client, experiment, run, operation, value):
    """A DELIBERATE BEHAVIOUR CHANGE, pinned apart from the crash fix.

    These four never crashed. On ``/answers`` ``or {}`` read them as the empty map and
    each answered **200** — a silent no-op shaped like success. On ``/edit`` they
    already answered 422, with ``no_correction_target``. Both now answer ``422
    invalid_body``: the same refusal, more accurately blamed. A client that sent
    ``"answers": ""`` did not send an empty map.
    """
    response = _post_answers(client, experiment, run, operation=operation, value=value)
    assert response.status_code == 422, (operation, value)
    assert response.json()["error"] == "invalid_body"


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("value", [None, {}])
def test_absent_or_empty_answers_keeps_its_existing_status(client, experiment, run, operation, value):
    """THE NEGATIVE CONTROL. A guard that refused everything would pass every test above.

    ``None`` and ``{}`` are not refused by this guard — it refuses a body that names
    something UNREADABLE, not one that names nothing at all. Their statuses differ
    between the two operations (``/answers`` accepts, ``/edit`` has nothing to
    correct), so what is asserted is that neither is ``invalid_body`` and neither is
    a 500.
    """
    response = _post_answers(client, experiment, run, operation=operation, value=value)
    assert response.status_code != 500
    if response.status_code == 422:
        assert response.json().get("error") != "invalid_body"


def test_a_well_formed_answers_map_still_reaches_the_writer(client, experiment):
    """The strongest negative control available: an unrecognised KEY still gets the
    route's own ``422``, not this guard's — proving the body was read, not rejected."""
    response = _post_answers(
        client, experiment, None, operation="exp/answers", value={"no_such_key": "v"}
    )
    assert response.status_code == 422
    assert response.json().get("error") != "invalid_body"


def test_the_preconditions_really_do_gate_the_crash_line(client, experiment, run):
    """PINS THE TRAP that cost the audit a false negative.

    Without ``confirmed_by_user`` the confirmation gate answers FIRST, so a body
    carrying an unreadable ``answers`` never reaches the line that used to raise —
    which is exactly why a 728-request fuzz sweep came back with zero 500s.

    And a RUN operation checks ``If-Match`` against **the RUN's token, not the
    record's**, so a probe holding the record's token gets 412 forever and concludes
    the route is safe. That half is asserted with a WELL-FORMED body, deliberately:
    this guard now runs BEFORE the precondition (see
    ``test_an_unreadable_body_is_refused_even_with_a_stale_token``), so sending an
    unreadable body here would prove nothing about the precondition.
    """
    unconfirmed = client.post(
        f"/api/experiments/{experiment}/answers",
        json={"answers": "str"},
        headers={"If-Match": _experiment_etag(client, experiment)},
    )
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["error"] == "confirmation_required"

    wrong_token = client.post(
        f"/api/experiments/{experiment}/runs/{run}/answers",
        json={"confirmed_by_user": True, "answers": {}},
        headers={"If-Match": _experiment_etag(client, experiment)},
    )
    assert wrong_token.status_code == 412


def test_an_unreadable_body_is_refused_even_with_a_stale_token(client, experiment, run):
    """THE ORDERING IS DELIBERATE: the body guard runs BEFORE the precondition.

    A body this operation cannot read is a 422 whether or not the caller's ``If-Match``
    is current. Telling such a client its token is stale would send it to re-read and
    retry — and the retry it builds is unreadable too, so the loop cannot terminate.
    The confirmation gate stays AHEAD of both, which the test above pins.
    """
    stale = '"gen-that-never-existed.0"'

    record_level = client.post(
        f"/api/experiments/{experiment}/answers",
        json={"confirmed_by_user": True, "answers": "str"},
        headers={"If-Match": stale},
    )
    assert record_level.status_code == 422
    assert record_level.json()["error"] == "invalid_body"

    run_level = client.post(
        f"/api/experiments/{experiment}/runs/{run}/answers",
        json={"confirmed_by_user": True, "answers": "str"},
        headers={"If-Match": stale},
    )
    assert run_level.status_code == 422
    assert run_level.json()["error"] == "invalid_body"


# --- F4 -----------------------------------------------------------------------


@pytest.mark.parametrize("value", UNHASHABLE)
def test_an_unhashable_note_source_reaches_the_refusal_that_already_existed(
    client, experiment, value
):
    """Was **500** (``TypeError: unhashable type``); is the route's OWN ``422``.

    The error code is asserted to be the pre-existing one, because the fix was to let
    the wrong type reach the refusal already sitting two lines below — not to add a
    second refusal with a new vocabulary.
    """
    response = client.post(
        f"/api/experiments/{experiment}/notes",
        json={"text": "hello", "source": value},
        headers={"If-Match": _experiment_etag(client, experiment)},
    )
    assert response.status_code == 422, (value, response.status_code)
    body = response.json()
    assert body["error"] == "unknown_note_source"
    assert body["source"] is None  # never the unhashable value itself
    assert sorted(notes.NOTE_SOURCES) == sorted(body["allowed"])


@pytest.mark.parametrize("value", HASHABLE_NON_MEMBERS)
def test_a_hashable_non_member_source_is_unchanged(client, experiment, value):
    """THE CONTROL. These always returned 422; they must still return the SAME 422."""
    response = client.post(
        f"/api/experiments/{experiment}/notes",
        json={"text": "hello", "source": value},
        headers={"If-Match": _experiment_etag(client, experiment)},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_note_source"


@pytest.fixture()
def note(client, experiment) -> str:
    r = client.post(
        f"/api/experiments/{experiment}/notes",
        json={"text": "a typed note", "source": "typed_note"},
        headers={"If-Match": _experiment_etag(client, experiment)},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["note"]["id"]


@pytest.mark.parametrize("value", UNHASHABLE)
def test_an_unhashable_note_action_reaches_the_refusal_that_already_existed(
    client, experiment, note, value
):
    """Was **500**; is the route's own ``422 unknown_note_action``.

    The note has to be created for real first: a bad note id answers 404 BEFORE the
    action is read, which is another precondition that hides this crash.
    """
    response = client.post(
        f"/api/experiments/{experiment}/notes/{note}/review",
        json={"action": value, "confirmed_by_user": True},
        headers={"If-Match": _experiment_etag(client, experiment)},
    )
    assert response.status_code == 422, (value, response.status_code)
    body = response.json()
    assert body["error"] == "unknown_note_action"
    assert body["action"] is None


@pytest.mark.parametrize("value", HASHABLE_NON_MEMBERS + ["capture"])
def test_a_hashable_non_member_action_is_unchanged(client, experiment, note, value):
    """THE CONTROL, including ``capture`` — a real member of ``NOTE_ACTIONS`` that this
    route deliberately excludes, so the set DIFFERENCE is still being applied."""
    response = client.post(
        f"/api/experiments/{experiment}/notes/{note}/review",
        json={"action": value, "confirmed_by_user": True},
        headers={"If-Match": _experiment_etag(client, experiment)},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_note_action"


def test_a_real_note_action_still_applies(client, experiment, note):
    """THE POSITIVE CONTROL: the guard admits what it must."""
    response = client.post(
        f"/api/experiments/{experiment}/notes/{note}/review",
        json={"action": "keep", "confirmed_by_user": True},
        headers={"If-Match": _experiment_etag(client, experiment)},
    )
    assert response.status_code == 200, response.text


# --- F5 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["", "/evidence", "/artifacts", "/runs", "/notes"],
)
@pytest.mark.parametrize("length", [_EXPERIMENT_ID_MAX_LENGTH + 1, 255, 256, 300, 4096])
def test_an_over_long_experiment_id_is_refused_not_crashed(client, path, length):
    """Was **500** at 256 and above (``OSError: File name too long``); is **422**.

    Asserted across several operations because the bound is on the shared
    ``ExperimentId`` type, so it must cover every route taking the parameter — the
    whole reason the guard is at the boundary and not inside ``load_experiment``.
    """
    response = client.get(f"/api/experiments/{'a' * length}{path}")
    assert response.status_code == 422, (path, length, response.status_code)


@pytest.mark.parametrize("length", [1, 26, _EXPERIMENT_ID_MAX_LENGTH])
def test_an_id_within_the_bound_still_gets_an_honest_404(client, length):
    """THE NEGATIVE CONTROL, and the reason the bound is 128 rather than 26.

    A ``404`` is the only thing entitled to say "no such record". A tighter bound
    would turn a length check into an id-FORMAT check and answer 422 for an id that
    is simply absent — including the 26-character ULID this product actually mints.
    """
    response = client.get(f"/api/experiments/{'a' * length}")
    assert response.status_code == 404, (length, response.status_code)


def test_the_bound_is_the_one_the_mcp_boundary_already_publishes():
    """128 is ADOPTED, not invented.

    ``mcp/tools._EXPERIMENT_ID`` declares ``maxLength: 128`` for this exact
    identifier, and its own note records that "ADDING VALIDATION TO THE HTTP ROUTE IS
    A PRODUCT CHANGE AND IS NOT MADE HERE". This is that change. Read from the module
    rather than transcribed, so the two cannot drift apart.
    """
    from isaac_api.mcp.tools import _EXPERIMENT_ID

    assert _EXPERIMENT_ID["maxLength"] == _EXPERIMENT_ID_MAX_LENGTH


def test_a_write_route_also_refuses_an_over_long_id(client):
    """The bound covers writes too, and refuses BEFORE the confirmation gate.

    A 422 from path validation, not from ``confirmation_required`` — the segment
    never names a record, so there is nothing to confirm against.
    """
    response = client.post(
        f"/api/experiments/{'a' * 300}/answers",
        json={"confirmed_by_user": True, "answers": {}},
    )
    assert response.status_code == 422

"""One malformed experiment document must cost that record, not the whole workspace.

THE DEFECT, MEASURED OVER HTTP ON ``cde8d7c``. ``Experiment.from_state`` read ``id``,
``title`` and ``created_utc`` as HARD SUBSCRIPTS and coerced ``rev`` with a bare
``int()``. ``list_experiments_with_hydration`` catches only ``FileNotFoundError``, so
one unreadable document made **``GET /api/experiments`` return 500** — hiding EVERY
record — while each healthy record's own detail route still answered 200. A silent
whole-list outage that no single-record probe would see.

WHY THE FIX IS A DEGRADATION AND NOT A REFUSAL. From PR #177, and it is the rule the
whole family turns on: *a malformed value in a REQUEST can be refused, because the
caller sent it and a typed 422 names what to fix; a malformed value already PERSISTED
cannot be refused to the reader, who did nothing wrong and whose record would simply
vanish.* So these documents are READ, never repaired, and the record stays BLOCKED.

WHAT THIS FILE PINS THAT A CRASH-ONLY TEST WOULD MISS, and each is a separate test:

* the healthy record is still IN the list (a fix that dropped the bad row silently
  would pass a status-code-only assertion, and would delete a scientist's record from
  their own list screen);
* the degraded record stays BLOCKED — never ``ready_to_export``, never ``done``, and
  its export refuses;
* nothing is invented — no synthetic blocker is written, and the stored document is
  byte-identical after being read;
* an unusable stored ``id`` falls back to the DIRECTORY the document was read from,
  because ``Experiment.dir`` is ``scope_root / self.id`` and an ``id`` of ``""`` would
  alias the SCOPE ROOT, so a later save would write ``<scope_root>/experiment.json``;
* the STRICT reader is still strict — ``Experiment.from_state`` still raises, because
  six fail-closed consumers depend on that raise (the reset preflight above all).

The last one is the point of the whole design. Making ``from_state`` total, as
``Run.from_state`` was made, would have silently weakened all six at once.

Every fixture is synthetic and hand-built. Nothing here reads real data.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api.app import create_app

_DELETE = object()

#: (label, key, value) — every one of these was a measured 500 on the LIST route, the
#: DETAIL route, or both. `created_utc: 5` needs a second record to reproduce, because
#: its raise is in `out.sort(...)` comparing `int` with `str`.
MALFORMED = [
    ("id absent", "id", _DELETE),
    ("title absent", "title", _DELETE),
    ("created_utc absent", "created_utc", _DELETE),
    ("rev is not numeric", "rev", "x"),
    ("draft is not an object", "draft", "nope"),
    ("source is not an object", "source", "nope"),
    ("created_utc is not a string", "created_utc", 5),
    ("answer_log is not a list", "answer_log", "nope"),
]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _create(client, title: str) -> str:
    r = client.post("/api/experiments", json={"title": title})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _state_path(exp_id: str):
    return ws.workspace_root() / exp_id / "experiment.json"


def _poke(exp_id: str, key: str, value) -> None:
    path = _state_path(exp_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    if value is _DELETE:
        state.pop(key, None)
    else:
        state[key] = value
    path.write_text(json.dumps(state), encoding="utf-8")


@pytest.fixture()
def two_records(client):
    """A healthy record and one to break. TWO, deliberately.

    `created_utc: 5` raises in the list's `sort`, which needs something to compare
    against — a single-record workspace reports that row clean.
    """
    healthy = _create(client, "Healthy record")
    broken = _create(client, "Record to break")
    return healthy, broken


@pytest.mark.parametrize("label,key,value", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_the_list_survives_one_malformed_document(client, two_records, label, key, value):
    """Was **500** for six of these eight; is **200**, with the healthy record present."""
    healthy, broken = two_records
    _poke(broken, key, value)

    listing = client.get("/api/experiments")
    assert listing.status_code == 200, f"{label}: {listing.status_code}"

    # NOT JUST A 200. A fix that dropped the unreadable row would also return 200 and
    # would silently delete a record from its owner's list.
    ids = {e["id"] for e in listing.json()["experiments"]}
    assert healthy in ids, f"{label}: the healthy record vanished from the list"
    assert broken in ids, f"{label}: the degraded record vanished from the list"


@pytest.mark.parametrize("label,key,value", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_the_degraded_records_own_detail_route_survives(client, two_records, label, key, value):
    """Was **500** for six of these eight on the record's OWN route."""
    _healthy, broken = two_records
    _poke(broken, key, value)

    assert client.get(f"/api/experiments/{broken}").status_code == 200, label
    assert client.get(f"/api/experiments/{broken}/evidence").status_code == 200, label


@pytest.mark.parametrize("label,key,value", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_a_malformed_document_stays_blocked(client, two_records, label, key, value):
    """DEGRADE TRUTHFULLY: readable, and never certified exportable.

    A document this reader had to normalise must not reach `ready_to_export` or
    `done`, and its export must refuse. 200-and-fine would be the honesty defect that
    replaces the crash.
    """
    _healthy, broken = two_records
    _poke(broken, key, value)

    detail = client.get(f"/api/experiments/{broken}")
    assert detail.status_code == 200, label
    body = detail.json()
    assert body["status"] not in ("ready_to_export", "done"), (label, body["status"])
    assert body["exported"] is False, label

    etag = detail.headers["ETag"]
    export = client.post(
        f"/api/experiments/{broken}/export", headers={"If-Match": etag}
    )
    # Either a refusal to act, or a 200 that says `ok: false`. What it must never be
    # is a written artifact.
    assert export.status_code != 500, label
    if export.status_code == 200:
        assert export.json().get("ok") is False, label


#: Wrong-typed values that did NOT crash — they are here because normalising them is
#: a type-contract fix rather than a crash fix, and the two must not be conflated.
WRONG_TYPED_BUT_HARMLESS = [
    ("title is a number", "title", 5),
    ("title is an object", "title", {"a": 1}),
    ("created_utc is an object", "created_utc", {"a": 1}),
    ("rev is a list", "rev", []),
]


@pytest.mark.parametrize(
    "label,key,value",
    MALFORMED + WRONG_TYPED_BUT_HARMLESS,
    ids=[m[0] for m in MALFORMED + WRONG_TYPED_BUT_HARMLESS],
)
def test_a_normalised_key_still_has_its_declared_type(client, two_records, label, key, value):
    """THE HALF A CRASH-ONLY TEST MISSES, and it was found by mutation.

    Reverting ``_as_str`` on ``title`` to a raw ``state.get`` broke NO test in the
    first version of this file: an absent title became ``None`` and a numeric one
    stayed ``5``, neither of which raises. So the whole list kept answering 200 while
    the response carried a ``title`` that is not a string, which every client reads as
    one. Not crashing is not the same as being readable.

    ``""`` RATHER THAN ``str(value)`` is the no-guessing rule, not tidiness:
    ``str()`` cannot fail, so a coercing fallback would manufacture the title
    ``"{'a': 1}"`` out of an object and the timestamp ``"5"`` out of an integer. A
    wrong-typed key on disk is not evidence for any particular string, so it falls
    back to what a MISSING key already got.
    """
    _healthy, broken = two_records
    _poke(broken, key, value)

    body = client.get(f"/api/experiments/{broken}").json()
    assert isinstance(body["title"], str), (label, body["title"])
    assert isinstance(body["id"], str) and body["id"], label

    exp = ws.load_experiment(broken)
    assert exp is not None
    assert isinstance(exp.title, str), (label, exp.title)
    assert isinstance(exp.created_utc, str), (label, exp.created_utc)
    assert isinstance(exp.rev, int), (label, exp.rev)
    assert isinstance(exp.source, dict) and isinstance(exp.draft, dict), label
    assert isinstance(exp.answer_log, list), label
    # Nothing was manufactured out of the wrong-typed value.
    if key == "title" and not isinstance(value, str):
        assert exp.title == ""


def test_a_document_that_is_not_an_object_at_all_is_read(client, two_records):
    """A whole document that is a JSON LIST — was **500** on both routes.

    Not in the table above because it is not a key at all: it is the case where
    every `.get` below would raise `AttributeError`.
    """
    healthy, broken = two_records
    _state_path(broken).write_text("[1, 2, 3]", encoding="utf-8")

    listing = client.get("/api/experiments")
    assert listing.status_code == 200
    assert healthy in {e["id"] for e in listing.json()["experiments"]}
    assert client.get(f"/api/experiments/{broken}").status_code == 200


@pytest.mark.parametrize("label,key,value", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_reading_a_malformed_document_does_not_rewrite_it(client, two_records, label, key, value):
    """NOTHING IS REPAIRED, and the stored bytes prove it.

    The normalisation is read-time. A read that rewrote the file would erase the
    evidence of the degradation, without the record's version moving.
    """
    _healthy, broken = two_records
    _poke(broken, key, value)
    before = _state_path(broken).read_bytes()

    client.get("/api/experiments")
    client.get(f"/api/experiments/{broken}")
    client.get(f"/api/experiments/{broken}/evidence")

    assert _state_path(broken).read_bytes() == before, label


def test_an_unusable_id_falls_back_to_the_address_not_to_blank(client, two_records):
    """An ``id`` of ``""`` would alias the SCOPE ROOT — so the address wins.

    ``Experiment.dir`` is ``scope_root / self.id``. If an unusable stored ``id``
    became ``""``, ``dir`` would BE the scope root and a later save would write
    ``<scope_root>/experiment.json`` — a real file outside every experiment
    directory that no enumeration would ever read again. The fallback is the
    directory the document was read from, which is the same rule
    ``stored_experiments`` and ``_heal_from_conflict`` already apply in reverse.
    """
    _healthy, broken = two_records
    _poke(broken, "id", _DELETE)

    exp = ws.load_experiment(broken)
    assert exp is not None
    assert exp.id == broken
    assert exp.dir == ws.workspace_root() / broken
    assert exp.dir != ws.workspace_root()

    detail = client.get(f"/api/experiments/{broken}")
    assert detail.status_code == 200
    assert detail.json()["id"] == broken


@pytest.mark.parametrize("label,key,value", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_the_strict_reader_is_still_strict(two_records, label, key, value):
    """``Experiment.from_state`` MUST GO ON RAISING. This is the design, not an omission.

    Six consumers depend on the raise as a fail-closed or fail-soft gate — above all
    ``_current_plan_row``, the reset PREFLIGHT, which answers ``_UNREADABLE_ROW`` for a
    document that will not hydrate so a destructive reset REFUSES. Making
    ``from_state`` total (the obvious fix, and the one ``Run.from_state`` took) would
    have weakened all six silently and invisibly.

    Only the raising cases are asserted here: three of the eight rows above are
    tolerated by ``from_state`` already and are covered by the list/detail tests.
    """
    _healthy, broken = two_records
    _poke(broken, key, value)
    state = json.loads(_state_path(broken).read_text(encoding="utf-8"))

    strict_raises = key in ("id", "title", "created_utc") and value is _DELETE
    strict_raises = strict_raises or (key == "rev" and value == "x")
    if not strict_raises:
        pytest.skip(f"{label} is tolerated by the strict reader; covered by the route tests")

    with pytest.raises((KeyError, TypeError, ValueError)):
        ws.Experiment.from_state(state, session_id=None)


def test_the_reset_preflight_still_refuses_a_malformed_document(client, two_records):
    """THE FAIL-CLOSED GATE THE TOLERANCE MUST NOT HAVE WEAKENED.

    ``_load_all_experiments`` now degrades, and this proves that did NOT reach the
    reset's own preflight: ``_current_plan_row`` re-reads through the STRICT reader and
    still answers ``_UNREADABLE_ROW``, which compares unequal to every real row.
    """
    _healthy, broken = two_records
    _poke(broken, "id", _DELETE)

    row = ws._current_plan_row(broken, session_id=None)
    assert row is ws._UNREADABLE_ROW


def test_the_classification_pass_and_the_reset_check_now_disagree_on_purpose(
    client, two_records
):
    """THE ASYMMETRY IS THE DESIGN, and it is pinned so nobody "fixes" it into agreement.

    ``_load_all_experiments`` normalises (a reader must not be shown a 500);
    ``_current_plan_row`` stays STRICT (a destructive reset must not proceed on a
    document it cannot prove is unchanged). So a malformed record classifies into a
    bucket and appears in the plan, and the execute-time re-read then answers
    ``_UNREADABLE_ROW`` — unequal to the planned row, so the reset REFUSES it.

    This is strictly better than the previous behaviour, in which the malformed
    document made the classification pass itself RAISE, so no reset could even be
    planned. Both halves are asserted, because asserting only the second would pass
    if the first had gone back to raising.
    """
    _healthy, broken = two_records
    _poke(broken, "id", _DELETE)

    # 1. The classification pass READS it — no raise, and the record is present.
    loaded = ws._load_all_experiments(session_id=None)
    assert broken in {e.id for e in loaded}

    # 2. The reset's own re-read REFUSES it, and the two therefore disagree.
    planned = ws._plan_digest_row(
        next(e for e in loaded if e.id == broken),
        ws.classify_experiment(next(e for e in loaded if e.id == broken)),
    )
    assert ws._current_plan_row(broken, session_id=None) != planned

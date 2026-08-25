"""The open-question list can be BOUNDED, and a bounded list says that it is one.

WHY THIS FILE EXISTS
====================
``GET /experiments/{id}/pending`` served every open blocking question of the whole
record, and so did all four MUTATION responses — ``POST /answers``, ``POST /edit``,
``POST /runs/{run_id}/answers`` and ``POST /runs/{run_id}/edit``. A record's question
count is ``3 x runs``, so both grew without bound. Measured in-process over HTTP on
``c153ec9`` (the commit this branch is based on), against a record created through
``POST /api/experiments`` with N runs each carrying the three seeded run-level
questions::

     runs   GET /pending B   entries   POST /runs/{id}/answers B   entries
       25           44,236        75                     44,840        74
      100          176,989       300                    177,592       299
      250          442,939       750                    443,542       749
      500          886,189     1,500                    886,792     1,499
     1000        1,772,692     3,000                  1,773,294     2,999

~~627 bytes per entry, flat, and 71% of those bytes are ``inferability`` +
``question``~~ — **both figures were overstated and are corrected in place**: the
marginal cost is **591.0 bytes per entry** (``(1,772,692 - 176,989) / 2,700``, and
every other adjacent pair of rows above gives the same number), and ``inferability`` +
``question`` are **63.5%** of the served bytes, 68.1% counting their keys. Still three
fixed question templates repeated once per run, which is the fact those percentages
were carrying. ``serialize.py``'s note above ``PENDING_WINDOW`` holds the command that
re-derives them, and the harness they depend on — the runs above were created with no
explicit label, and passing one of a different length moves every figure in the table.

**THE MUTATION COLUMN IS THE WORSE HALF**, because it is the WRITE path a scientist
hits repeatedly: answering ONE question on ONE run downloaded the whole record's
question set, every time, to report one answer.

WHAT IS GUARDED HERE, AND WHAT DELIBERATELY IS NOT
==================================================
Not the timing. A wall-clock assertion in the normal suite is flaky under CPU
contention and this repository has been bitten by exactly that (``CLAUDE.md`` §7).
Every assertion below is over **response BYTES and ENTRY COUNTS**, which are
deterministic for a given workload, plus the four contract properties the bound has
to preserve:

1. **The unbounded default is unchanged.** ``GET /pending`` with no parameters
   returns the same single ``pending`` key it always did, complete, with no page
   block. Bounding is something a client ASKS for; it is never imposed on a consumer
   that does not know to page.
2. **Nothing is silently truncated.** Every bounded response carries ``pending_page``
   with ``total``, ``returned``, ``withheld`` and ``complete``.
3. **Nothing becomes undiscoverable.** Paging reaches every question exactly once,
   and a run filter refuses an unknown run rather than answering "nothing left".
4. **The counters still speak for the record.** ``pending_count``, ``status`` and
   ``export_ready`` are derived from the full list before any bounding, so
   ``pending_count() == len(pending())`` — the invariant
   ``test_pending_count_is_not_materialised.py`` pins — is untouched.

Plus the one property that makes the mutation window SAFE rather than merely small:
**it is anchored on the unit that was written**, so the question a caller just
answered is always in the response even on a 1,000-run record. Without that,
``GuidedCompletion.answerWasApplied`` — which decides "did my answer land?" by asking
whether its question is still in the returned list — would read an answer the truth
core REFUSED as applied.

The wall-clock-free byte benchmark is opt-in at the bottom::

    ISAAC_PERF_BENCH=1 .venv/bin/pytest \\
      apps/api/tests/test_pending_reads_are_boundable.py -q -s -k benchmark
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from isaac_api import routes, serialize
from isaac_api import workspace as ws

#: A three-point spectrum written out here rather than harvested from a fixture, for
#: the same reason ``test_scientist_can_finish_a_record.py`` writes its own: a helper
#: that fetched a demo answer would reintroduce the blind spot that file exists to
#: close. Small on purpose — this asserts routing and bounding, not reduction.
SERIES = [
    {
        "series_id": "averaged_spectrum",
        "independent_variables": [
            {"name": "incident_energy", "unit": "eV", "values": [8970, 8980, 8990]}
        ],
        "channels": [
            {
                "name": "absorption",
                "unit": "mu_normalized",
                "role": "primary_signal",
                "values": [0.02, 0.85, 1.45],
            }
        ],
    }
]

QC = {"status": "valid", "evidence": "I0 stable across all scans; no glitches."}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A plain client on an empty workspace — NO worked-example session."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return TestClient(create_app())


def _with_runs(client: TestClient, n: int, *, title: str = "bounded pending") -> tuple[str, list[str]]:
    """A record created over HTTP, then given ``n`` runs IN PROCESS.

    THE RUNS ARE NOT ADDED OVER HTTP, and that is a measurement decision rather than a
    shortcut. ``POST /runs`` rewrites the whole experiment document per call, so
    building 1,000 runs that way is quadratic in the STORE and would make this file
    take minutes while measuring something other than the response. ``add_run`` with
    ``routes._seed_for_new_run`` is exactly what that route persists, so the resulting
    document is the one the route would have written.
    """
    exp_id = client.post("/api/experiments", json={"title": title}).json()["id"]
    exp = ws.load_experiment(exp_id)
    for i in range(n):
        exp.add_run(label=f"Run {i + 1}", draft=routes._seed_for_new_run(exp))
    exp.save_versioned()
    return exp_id, [r.id for r in ws.load_experiment(exp_id).sorted_runs()]


def _run_version(client: TestClient, exp_id: str, run_id: str) -> str:
    return client.get(f"/api/experiments/{exp_id}/runs/{run_id}").json()["run"]["version"]


def _open_for_run(client: TestClient, exp_id: str, run_id: str) -> int:
    """How many questions THAT RUN still owes, read from the server rather than assumed.

    It exists because two assertions below used to be written ``<= PENDING_WINDOW + 4``,
    and **4 is a number the code does not bound.** ``pending_mutation_window`` returns
    the head PLUS every still-open question of the written unit, uncapped — so the
    honest right-hand side is the head plus THIS, measured, and an independent review
    was right that the magic constant was asserting a guarantee that does not exist.
    """
    page = client.get(f"/api/experiments/{exp_id}/pending?run_id={run_id}")
    return page.json()["pending_page"]["total"]


def _answer_run(client: TestClient, exp_id: str, run_id: str, answers: dict):
    return client.post(
        f"/api/experiments/{exp_id}/runs/{run_id}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers={"If-Match": f'"{_run_version(client, exp_id, run_id)}"'},
    )


# --- 1. the unbounded default is UNCHANGED ------------------------------------


@pytest.mark.parametrize("n", [0, 1, 5, 40])
def test_an_unbounded_read_returns_one_key_and_the_whole_set(client, n):
    """THE DEFAULT IS COMPLETE AND ITS SHAPE IS UNMOVED.

    Exactly one top-level key, and no `pending_page`. A page block that appeared
    unconditionally would be harmless to a client that reads it and a new thing to
    misread for every client that does not — and the whole reason bounding is opt-in
    on this route is that a consumer which never learned to page must be handed
    nothing new at all.
    """
    exp_id, _ = _with_runs(client, n)
    body = client.get(f"/api/experiments/{exp_id}/pending").json()
    assert set(body) == {"pending"}, sorted(body)

    detail = client.get(f"/api/experiments/{exp_id}").json()
    assert len(body["pending"]) == detail["pending_count"]
    # Not merely "the route agrees with itself": a zero-run record owes its own three
    # questions and an N-run record owes three per run, the record's own being
    # withheld once a run exists (`Experiment.pending`'s long comment).
    assert len(body["pending"]) == (3 if n == 0 else 3 * n)


def test_the_unbounded_body_is_byte_identical_to_the_serializer(client):
    """No re-shaping crept in on the default path. The bytes a client receives are the
    bytes `serialize.pending_to_list` produces over the full derivation."""
    exp_id, _ = _with_runs(client, 4)
    exp = ws.load_experiment(exp_id)
    expected = serialize.pending_to_list(
        exp.draft,
        ws.load_demo_answers(),
        example_scope=False,
        entries=exp.pending(),
    )
    assert client.get(f"/api/experiments/{exp_id}/pending").json() == expected


# --- 2. a bounded read says what it withheld ----------------------------------


def test_a_limit_returns_a_page_that_states_what_it_withheld(client):
    exp_id, _ = _with_runs(client, 40)  # 120 questions
    body = client.get(f"/api/experiments/{exp_id}/pending?limit=10").json()

    assert len(body["pending"]) == 10
    assert body["pending_page"] == {
        "total": 120,
        "returned": 10,
        "offset": 0,
        "limit": 10,
        "withheld": 110,
        "complete": False,
        "run_id": None,
        "record_total": 120,
    }


def test_a_page_that_holds_everything_says_complete(client):
    """`complete` is the signal a client keys "nothing left" off, so it must be true
    exactly when the list IS the set — including when a limit was sent and simply was
    not reached. A bound that reports itself as a truncation it did not perform would
    make every small record look partial."""
    exp_id, _ = _with_runs(client, 2)  # 6 questions
    page = client.get(f"/api/experiments/{exp_id}/pending?limit=50").json()["pending_page"]
    assert page["complete"] is True
    assert (page["total"], page["returned"], page["withheld"]) == (6, 6, 0)


def test_paging_reaches_every_question_exactly_once(client):
    """CONSTRAINT 3, ASSERTED RATHER THAN ASSUMED: no blocker may become
    undiscoverable. Walking the pages must reconstruct the unbounded list EXACTLY —
    same entries, same order, no gap and no repeat."""
    exp_id, _ = _with_runs(client, 17)  # 51 questions: not a multiple of the page
    whole = client.get(f"/api/experiments/{exp_id}/pending").json()["pending"]

    walked: list[dict] = []
    offset = 0
    while True:
        body = client.get(
            f"/api/experiments/{exp_id}/pending?offset={offset}&limit=7"
        ).json()
        walked.extend(body["pending"])
        offset += body["pending_page"]["returned"]
        if body["pending_page"]["withheld"] == 0:
            break
    assert walked == whole
    assert len(walked) == 51


def test_an_offset_past_the_end_is_an_empty_page_not_a_refusal(client):
    """What a "load more" sends after a concurrent write shortened the list. The same
    decision `_RUN_OFFSET_DESC` records for the run list: clamp, and let `total` tell
    the client it ran off the end."""
    exp_id, _ = _with_runs(client, 2)
    body = client.get(f"/api/experiments/{exp_id}/pending?offset=999").json()
    assert body["pending"] == []
    assert body["pending_page"]["total"] == 6
    assert body["pending_page"]["withheld"] == 0
    # `complete` is FALSE here even though nothing is withheld, because `offset != 0`:
    # this page is not the set, it is the empty tail of it, and a client that read
    # `complete: true` off it would conclude the record has no open questions.
    assert body["pending_page"]["complete"] is False


def test_a_limit_over_the_ceiling_is_refused(client):
    exp_id, _ = _with_runs(client, 1)
    over = routes.PENDING_PAGE_MAX + 1
    assert client.get(f"/api/experiments/{exp_id}/pending?limit={over}").status_code == 422
    assert client.get(f"/api/experiments/{exp_id}/pending?limit=0").status_code == 422
    assert client.get(f"/api/experiments/{exp_id}/pending?offset=-1").status_code == 422
    # And OMITTING the limit is still unbounded — the ceiling bounds one response, it
    # is not a cap on how many questions a record may have.
    exp_id, _ = _with_runs(client, routes.PENDING_PAGE_MAX // 2)
    body = client.get(f"/api/experiments/{exp_id}/pending").json()
    assert len(body["pending"]) > routes.PENDING_PAGE_MAX


# --- 3. the run filter --------------------------------------------------------


def test_a_run_filter_returns_that_runs_questions_and_still_reports_the_record(client):
    exp_id, run_ids = _with_runs(client, 6)
    target = run_ids[4]
    body = client.get(f"/api/experiments/{exp_id}/pending?run_id={target}").json()

    assert {q["run_id"] for q in body["pending"]} == {target}
    assert {q["kind"] for q in body["pending"]} == {"series", "qc", "descriptor"}
    page = body["pending_page"]
    assert (page["total"], page["returned"], page["withheld"]) == (3, 3, 0)
    assert page["run_id"] == target
    # THE HALF THAT KEEPS A FILTERED READ HONEST. `total` is the run's; a screen that
    # rendered it as "3 still to confirm" would understate an 18-question record by
    # fifteen. `record_total` is the record's, in the same response.
    assert page["record_total"] == 18


def test_an_unknown_run_is_refused_not_answered_with_an_empty_list(client):
    """A filter that silently matches nothing is a surface answering less than it
    claims: `total: 0` reads as "this run has no open questions", which is a
    statement about a run that does not exist."""
    exp_id, _ = _with_runs(client, 2)
    res = client.get(f"/api/experiments/{exp_id}/pending?run_id=01NOSUCHRUN00000000000000")
    assert res.status_code == 404
    assert res.json()["error"] == "run_not_found"


def test_the_filter_composes_with_paging(client):
    exp_id, run_ids = _with_runs(client, 3)
    target = run_ids[1]
    body = client.get(
        f"/api/experiments/{exp_id}/pending?run_id={target}&offset=1&limit=1"
    ).json()
    assert len(body["pending"]) == 1
    assert body["pending"][0]["run_id"] == target
    assert body["pending_page"]["total"] == 3
    assert body["pending_page"]["withheld"] == 1
    assert body["pending_page"]["record_total"] == 9


# --- 4. the mutation responses are bounded, and say so ------------------------


def test_a_record_level_answer_carries_a_page_block_even_when_complete(client):
    """`pending_page` is UNCONDITIONAL on a mutation, unlike on a read. This response
    is bounded whether the caller asked or not, so a client must never have to infer
    completeness from an absent key."""
    exp_id, _ = _with_runs(client, 0)
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    res = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"qc": QC}, "confirmed_by_user": True},
        headers={"If-Match": f'"{version}"'},
    )
    assert res.status_code == 200, res.text
    page = res.json()["pending_page"]
    assert page["complete"] is True
    assert (page["total"], page["returned"], page["withheld"]) == (2, 2, 0)


def test_a_run_answer_on_a_large_record_returns_a_window_not_the_record(client):
    """THE MEASURED DEFECT, closed. 1,000 runs is 3,000 open questions; before this
    the response carried all of them."""
    exp_id, run_ids = _with_runs(client, 1000)
    res = _answer_run(client, exp_id, run_ids[500], {"qc": QC})
    assert res.status_code == 200, res.text
    body = res.json()

    page = body["pending_page"]
    assert page["total"] == 2999, page  # the record's real count, undiminished
    assert page["complete"] is False
    assert page["withheld"] == page["total"] - page["returned"]
    # The window is the head plus this run's own still-open questions — the head plus
    # what THIS unit still owes, read from the server. ~~`<= PENDING_WINDOW + 4`~~: the
    # 4 was a magic margin the code does not bound (see `_open_for_run`), so it is
    # replaced by the measured quantity it was standing in for.
    assert page["returned"] <= serialize.PENDING_WINDOW + _open_for_run(
        client, exp_id, run_ids[500]
    ), page
    assert len(body["pending"]) == page["returned"]

    # AND THE COUNTERS STILL SPEAK FOR THE RECORD, not for the page. This is the half
    # a bound is most likely to break, and it is the invariant
    # `test_pending_count_is_not_materialised.py` pins from the other side.
    assert client.get(f"/api/experiments/{exp_id}").json()["pending_count"] == 2999
    assert body["status"] == "needs_attention"
    # `complete_metadata` is `pending_count == 0` (`workflow.derive_workflow`), so a
    # workflow computed off the WINDOW would have said this record's metadata was
    # complete the moment the window emptied.
    assert body["workflow"]["current_step"] == "complete_metadata", body["workflow"]


def test_the_window_is_anchored_on_the_run_that_was_written(client):
    """THE PROPERTY THAT MAKES THE WINDOW SAFE RATHER THAN MERELY SMALL.

    Run 900's questions are nowhere near the head of a 1,000-run record's list. A
    plain head-of-list window would not contain them, and `GuidedCompletion` decides
    "was my answer applied?" by asking whether its question is still in this list — so
    a refusal would have read as a success. Answering ONE of this run's three
    questions must leave its other two visibly open IN THIS RESPONSE.
    """
    exp_id, run_ids = _with_runs(client, 1000)
    target = run_ids[900]
    body = _answer_run(client, exp_id, target, {"qc": QC}).json()

    mine = [q for q in body["pending"] if q.get("run_id") == target]
    assert {q["kind"] for q in mine} == {"series", "descriptor"}, mine
    # The answered one is gone from the window because it is gone from the record —
    # not because the window did not reach it.
    assert all(q["kind"] != "qc" for q in mine), mine


def test_a_refused_answer_far_from_the_head_is_reported_as_still_open(client):
    """THE DEFECT THE ANCHOR EXISTS TO PREVENT, exercised end to end.

    ~~`apply_answers` leaves a wrong-typed `series` unapplied and puts the blocker
    straight back — over HTTP that is a 200 with `changed: false`.~~ **THE VEHICLE
    CHANGED ON 2026-08-25; THE ANCHOR IS UNCHANGED AND SO IS WHAT IT PROTECTS.** A
    wrong-typed `series` is now `422 invalid_field_value` before any write — asserted
    below — so that particular request no longer produces a `200` for a client to
    misread at all. The property is preserved MORE strongly by the refusal, because
    `GuidedCompletion` takes its error path and claims nothing.

    What still reaches the reporting code is a bare `descriptor_label`: the core receives
    it, both writers gate the descriptor block on `descriptor is not None`, so it is
    stored nowhere and every one of the run's questions is still open. That is the
    remaining `200`-that-wrote-nothing on a run, and it is the one this window must still
    carry from index ~2,700 of the record's list.
    """
    exp_id, run_ids = _with_runs(client, 1000)
    target = run_ids[900]

    # The refusal, first: the old vehicle cannot reach the window because it cannot
    # reach the write. A 422 carries no `pending` list, and needs none.
    refused = _answer_run(client, exp_id, target, {"series": ["not an object"]})
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "invalid_field_value", refused.json()
    assert "pending" not in refused.json(), refused.json()

    res = _answer_run(client, exp_id, target, {"descriptor_label": "relabel"})
    assert res.status_code == 200, res.text  # a 200 that wrote NOTHING

    body = res.json()
    # NOTHING LANDED, and `changed_fields` is the statement to read rather than
    # `changed`. `_fields_the_write_landed` removes a key the core received and
    # DECLINED, so an empty list beside `changed: true` is this route's honest report
    # of a write whose only effect was on the document's derived shape — the case its
    # own comment records as "`Updated 0 field(s)` ... literally true".
    assert body["invalidation"]["changed_fields"] == [], body["invalidation"]
    # THE ASSERTION THIS FILE EXISTS FOR. The entry is at index ~2,700 of the record's
    # list, far past any head-of-list window, and it is HERE — so the client's
    # membership test reads "still open" and the screen claims nothing.
    mine = {q["kind"] for q in body["pending"] if q.get("run_id") == target}
    assert mine == {"series", "qc", "descriptor"}, mine
    assert body["pending_page"]["complete"] is False

    # The positive control for the anchor: a write the core ACCEPTS on the same run
    # still returns that run's remaining questions from deep in the list.
    body = _answer_run(client, exp_id, target, {"series": SERIES}).json()
    assert {q["kind"] for q in body["pending"] if q.get("run_id") == target} == {
        "qc",
        "descriptor",
    }


def test_a_record_level_write_anchors_on_the_records_own_questions(client):
    """The same rule with `unit_run_id=None`. A zero-run record's own questions sort
    first, so the anchor selects nothing the head did not already hold — it is
    expressed as one rule anyway, so a future change to `Experiment.pending()`'s order
    cannot quietly break the guarantee on one of the two paths."""
    exp_id, _ = _with_runs(client, 0)
    version = client.get(f"/api/experiments/{exp_id}").json()["version"]
    body = client.post(
        f"/api/experiments/{exp_id}/answers",
        json={"answers": {"series": SERIES}, "confirmed_by_user": True},
        headers={"If-Match": f'"{version}"'},
    ).json()
    assert {q["kind"] for q in body["pending"]} == {"qc", "descriptor"}
    assert body["pending_page"]["complete"] is True


# --- 5. the anti-scaling guard (bytes, never wall-clock) ----------------------


#: What one `POST /runs/{id}/answers` response may weigh, at ANY run count.
#:
#: NOT A TIMING ASSERTION. Response bytes are deterministic for a given workload, so
#: this is as reproducible under CPU contention as an equality is — which is the whole
#: reason the guard is expressed in bytes rather than in milliseconds (see the module
#: docstring, and `CLAUDE.md` §7 for the contaminated benchmark that taught this
#: repository the difference).
#:
#: 60 KB is set against the measurement rather than guessed: a window of
#: `PENDING_WINDOW` entries at the measured ~591 bytes each (this said ~~627~~ and is
#: corrected with the table in the module docstring) is ~30 KB, plus the
#: workflow/invalidation/version envelope. It is a CEILING with real headroom, not a
#: target — the point is that the number does not move with the RUN COUNT, and the
#: equality-shaped assertion below is what actually establishes that.
#:
#: **IT IS NOT A CEILING ON EVERY MUTATION RESPONSE, AND SAYING SO IS PART OF THE
#: GUARD.** The window is ANCHORED and the anchored set is uncapped, so a response is
#: flat in the run count and LINEAR IN ONE UNIT'S OPEN-QUESTION COUNT: a unit owing 82
#: still-open questions returns 132 entries and ~87 KB, past this number.
#: `test_the_anchored_set_is_not_capped` measures exactly that and is the disclosure
#: this constant would otherwise be read as denying. Every record reachable through a
#: shipped capture path today owes at most five questions per unit, which is why the
#: sweeps below stay far under it.
MUTATION_RESPONSE_CEILING = 60_000


def test_the_mutation_response_does_not_grow_with_the_run_count(client):
    """THE GUARD. Not "is it small" but "is the growth zero".

    Before this change the same measurement read 44,840 bytes at 25 runs and 1,773,294
    at 1,000 — a 39x spread. The assertion is on the SPREAD as well as the ceiling,
    because a ceiling alone would pass an implementation that still grew linearly and
    merely started smaller.
    """
    sizes = (25, 250, 1000)
    measured: dict[int, int] = {}
    for n in sizes:
        exp_id, run_ids = _with_runs(client, n, title=f"scale {n}")
        res = _answer_run(client, exp_id, run_ids[-1], {"qc": QC})
        assert res.status_code == 200, res.text
        measured[n] = len(res.content)
        # See `_open_for_run`: the head plus what the written unit still owes, not the
        # head plus 4.
        assert res.json()["pending_page"]["returned"] <= serialize.PENDING_WINDOW + (
            _open_for_run(client, exp_id, run_ids[-1])
        )

    assert max(measured.values()) < MUTATION_RESPONSE_CEILING, measured
    # The bytes that DO move are the digits of a few integers and the run labels in
    # the window, so a 40x workload may not add even 10% to the response.
    assert measured[1000] < measured[25] * 1.1, measured


def test_a_bounded_read_does_not_grow_with_the_run_count(client):
    """The same property on the read path, for a client that asks for a page."""
    measured: dict[int, int] = {}
    for n in (25, 250, 1000):
        exp_id, _ = _with_runs(client, n, title=f"read scale {n}")
        res = client.get(f"/api/experiments/{exp_id}/pending?limit={serialize.PENDING_WINDOW}")
        measured[n] = len(res.content)
        assert res.json()["pending_page"]["returned"] == serialize.PENDING_WINDOW
    assert max(measured.values()) < MUTATION_RESPONSE_CEILING, measured
    assert measured[1000] < measured[25] * 1.1, measured


#: 80 extra `asset` sha256 questions, injected on one run so that ONE UNIT owes more
#: than `PENDING_WINDOW`. Written out here rather than produced through a capture path
#: because **no shipped capture path can produce them**: an `asset` question comes from
#: an ingested file listing, `POST /api/uploads` refuses every upload, and
#: `POST /ingestion/csv/preview` has no route that APPLIES a preview. That is why the
#: residue this test pins is LATENT rather than live — and why it is pinned anyway, so
#: that a future capture surface finds a measurement instead of a surprise.
def _extra_asset_questions(n: int) -> list[dict]:
    return [
        {
            "kind": "asset",
            "content_role": "raw_data_pointer",
            "uri": f"synthetic://fixture/scan_{i:03d}.h5",
            "media_type": "application/x-hdf5",
            "blocker": "sha256",
            "question": f"What is the sha256 of synthetic://fixture/scan_{i:03d}.h5?",
            "evidence": [],
        }
        for i in range(n)
    ]


def test_the_anchored_set_is_not_capped(client):
    """THE RESPONSE IS FLAT IN THE RUN COUNT AND LINEAR IN ONE UNIT'S QUESTION COUNT.

    Two clauses, and this file used to publish only the first. ``PENDING_WINDOW``'s
    comment said a unit owes "at most five" while ``pending_mutation_window``'s
    docstring said "three or four"; an independent review noticed the contradiction and
    then measured what neither number bounded — ``pending_mutation_window`` puts EVERY
    entry the written unit owns into the window, uncapped.

    WHY IT IS NOT CAPPED, argued where it is implemented and restated here because a
    test is where the next reader looks: a cap would have to drop some of the written
    unit's still-open questions, and the function is given ``unit_run_id`` and nothing
    finer — so it could drop the very entry ``GuidedCompletion.answerWasApplied`` looks
    for, and an entry missing from the list reads as ANSWERED. A "Confirmed by You" chip
    over a value the record does not hold is strictly worse than the bytes a cap saves.

    WHAT IS ASSERTED, and what deliberately is not. The ENTRY COUNT is a property of
    the construction and is asserted exactly. The BYTE size is not: it moves with the
    length of the injected URIs (measured 87,082 B with the fixture above; an
    independent review measured 83,672 with its own), so asserting it would pin the
    fixture rather than the behaviour. What IS asserted about the bytes is the property
    that matters — the response says out loud that it exceeded the policy.
    """
    exp_id, run_ids = _with_runs(client, 60, title="uncapped anchor")
    exp = ws.load_experiment(exp_id)
    last = exp.sorted_runs()[-1]
    last.draft["pending"] = list(last.draft.get("pending") or []) + _extra_asset_questions(80)
    exp.save_versioned()
    target = run_ids[-1]

    # 60 runs x 3, plus 80 = 260, less the `qc` this write answers.
    res = _answer_run(client, exp_id, target, {"qc": QC})
    assert res.status_code == 200, res.text
    body = res.json()
    page = body["pending_page"]

    owed = _open_for_run(client, exp_id, target)
    assert owed == 82, owed  # 80 assets + series + descriptor; qc is answered
    # The head (50) plus this unit's 82 — the last run's entries sort at the TAIL, so
    # nothing overlaps and the two simply add.
    assert page["returned"] == serialize.PENDING_WINDOW + owed == 132, page
    assert len(body["pending"]) == 132

    # THE GUARANTEE THE ANCHOR MAKES, checked entry by entry rather than by count:
    # every one of that unit's still-open questions came back.
    returned_keys = {
        item["blocker_key"] for item in body["pending"] if item.get("run_id") == target
    }
    owned = client.get(f"/api/experiments/{exp_id}/pending?run_id={target}").json()["pending"]
    assert returned_keys == {item["blocker_key"] for item in owned}

    # AND IT IS NOT SILENT. `returned` reports what came back and `limit` reports the
    # policy applied, so a response carrying 132 entries under a limit of 50 SAYS SO.
    # This is the opposite of truncation and is disclosed just as plainly.
    assert page["limit"] == serialize.PENDING_WINDOW
    assert page["returned"] > page["limit"]
    assert page["total"] == 259
    assert page["withheld"] == 259 - 132
    assert page["complete"] is False
    # The residue, stated as a measurement rather than a worry: this response is past
    # the ceiling the run-count sweeps assert, and the ceiling's own comment now says
    # so. It is bounded by ONE unit's question count, never by the record's.
    assert len(res.content) > MUTATION_RESPONSE_CEILING, len(res.content)


def test_withheld_counts_what_is_ahead_not_what_an_offset_skipped(client):
    """``withheld`` IS ``total - offset - returned``, and the docstring used to promise
    something else.

    It said "how many questions this response is NOT showing", which an offset makes
    false: the questions an offset skipped are not shown and are not counted. The number
    is the right one for "is there more to fetch?", which is what a pager asks, and the
    fix was to the SENTENCE — an offset is something the caller chose, so a client that
    skipped two questions knows it skipped them. Pinned here so the corrected reading is
    the one a future edit has to keep.
    """
    exp_id, run_ids = _with_runs(client, 1)  # one run, three questions
    page = client.get(
        f"/api/experiments/{exp_id}/pending?run_id={run_ids[0]}&offset=2&limit=5"
    ).json()["pending_page"]
    assert (page["total"], page["offset"], page["returned"]) == (3, 2, 1)
    assert page["withheld"] == 0  # nothing AHEAD; two were skipped behind
    assert page["complete"] is False  # `offset != 0`, so this is not the set


def test_complete_is_relative_to_the_filter_and_record_total_says_so(client):
    """``complete: true`` under a ``run_id`` filter means "this RUN has nothing
    further", never "this RECORD has nothing further".

    The page block's docstring asserted that a client reading only ``complete`` cannot
    mistake a page for the set, unqualified — and under a filter it can. ``record_total``
    is the mitigation, is served on every page, and is what makes the two
    distinguishable; this pins that it actually differs when it matters.
    """
    exp_id, run_ids = _with_runs(client, 3)  # 9 questions, 3 per run
    page = client.get(f"/api/experiments/{exp_id}/pending?run_id={run_ids[0]}").json()[
        "pending_page"
    ]
    assert page["complete"] is True and page["total"] == 3
    assert page["record_total"] == 9  # the record is emphatically NOT complete
    assert client.get(f"/api/experiments/{exp_id}").json()["pending_count"] == 9


def test_an_empty_run_id_is_refused_rather_than_read_as_absent(client):
    """``?run_id=`` IS A RUN FILTER NAMING A RUN THE RECORD DOES NOT HOLD.

    Treating it as absent was the alternative and it is the more dangerous one: a
    client that interpolated nothing into ``?run_id=${runId}`` would be handed the WHOLE
    record and would read it as that run's questions — a superset presented as a subset,
    which is the silent-wrong-answer class this route already refuses an unknown run to
    avoid. So the behaviour stands and ``_PENDING_RUN_ID_DESC`` now documents it, which
    is what an independent review asked for: the 404 names ``""`` as the id, and a
    reader has to be able to find out why.
    """
    exp_id, _ = _with_runs(client, 1)
    res = client.get(f"/api/experiments/{exp_id}/pending?run_id=")
    assert res.status_code == 404, res.text
    assert res.json()["error"] == "run_not_found"
    assert res.json()["id"] == ""
    assert "?run_id=" in routes._PENDING_RUN_ID_DESC


def test_the_unbounded_read_is_still_deliberately_linear(client):
    """A NEGATIVE CONTROL, and it is here so nobody "fixes" it.

    The default answers COMPLETELY, so it MUST grow with the record — that is the
    constraint, not a leak in it. If this ever stops growing, the default has started
    truncating silently and the two guards above would still pass.
    """
    small_id, _ = _with_runs(client, 10, title="linear 10")
    large_id, _ = _with_runs(client, 100, title="linear 100")
    small = len(client.get(f"/api/experiments/{small_id}/pending").content)
    large = len(client.get(f"/api/experiments/{large_id}/pending").content)
    assert large > small * 5, (small, large)


# --- 6. the opt-in byte benchmark ---------------------------------------------


@pytest.mark.skipif(
    os.environ.get("ISAAC_PERF_BENCH") != "1",
    reason="scale envelope; opt in with ISAAC_PERF_BENCH=1 (see module docstring)",
)
def test_benchmark_pending_scale_envelope(client, capsys):
    """PRINTS the envelope; ASSERTS NOTHING ABOUT TIME.

    Deliberately not a threshold and deliberately not a stopwatch — see the module
    docstring. The only assertions are the invariants, which hold however loaded the
    machine is.
    """
    rows = []
    for n in (25, 100, 250, 500, 1000):
        exp_id, run_ids = _with_runs(client, n, title=f"bench {n}")
        unbounded = client.get(f"/api/experiments/{exp_id}/pending")
        bounded = client.get(
            f"/api/experiments/{exp_id}/pending?limit={serialize.PENDING_WINDOW}"
        )
        mutated = _answer_run(client, exp_id, run_ids[-1], {"qc": QC})
        assert mutated.status_code == 200, mutated.text
        rows.append(
            (
                n,
                len(unbounded.content),
                len(unbounded.json()["pending"]),
                len(bounded.content),
                len(mutated.content),
                mutated.json()["pending_page"]["returned"],
                mutated.json()["pending_page"]["total"],
            )
        )
    with capsys.disabled():
        print(
            f"\n{'runs':>6} {'GET (default) B':>17} {'entries':>8} "
            f"{'GET ?limit=50 B':>17} {'POST answers B':>16} {'ents':>6} {'total':>7}"
        )
        for row in rows:
            print(
                f"{row[0]:>6} {row[1]:>17,} {row[2]:>8,} {row[3]:>17,} "
                f"{row[4]:>16,} {row[5]:>6,} {row[6]:>7,}"
            )
        print(
            "\nBEFORE, measured on c153ec9 (same harness, same workload):\n"
            "    25    44,236       75          -        44,840     74\n"
            "  1000 1,772,692    3,000          -     1,773,294  2,999"
        )

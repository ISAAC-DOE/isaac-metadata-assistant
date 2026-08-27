"""The destructive reset must refuse a scope it cannot read BEFORE it destroys any of it.

REPRODUCED OVER HTTP FIRST, on `c2cced5`, with `raise_server_exceptions=False`. The
defect is a consequence of the tolerant-read slice in this same PR: `_load_all_experiments`
was made tolerant (through `_hydrate_experiment`) while `_current_plan_row` — the reset's
per-record precondition — was deliberately left strict. Nothing checked for that
disagreement before the mutation loop, so with ONE canonical seed's `experiment.json`
missing its `title` (one of the eight cases this PR's own F2 fixes):

===========================  ==============================  ================================
step                         `main` (`b458e71`)              `c2cced5`, before this file
===========================  ==============================  ================================
`POST /api/demo/reset`       **500** `KeyError: 'title'`     **200**, `final_count: 5`,
  preview                    — nothing destroyed             `refusal_reason: null`
execute #0                   500, nothing destroyed          **412 plan_digest_stale**,
                                                             `removed_count: 1` — the
                                                             managed-legacy record was
                                                             DESTROYED, the malformed
                                                             canonical was NOT repaired
execute #1, #2 (fresh        500                             **412 forever**,
digest each time)                                            `removed_count: 0`
===========================  ==============================  ================================

Second reproduction, also observed: three managed-legacy records with the LAST one in
listing order malformed. Execute removed **2 of 3** and then refused permanently.

Three distinct problems, and this file pins all three:

* **the tutorial workspace became permanently un-resettable.** The canonical loop
  `break`s on the malformed id, so the very record the reset exists to restore is the one
  it can never restore, and every retry aborts at the same place;
* **`plan_digest_stale` was a false and unactionable reason.** Its documented meaning is
  "re-preview and retry" (`_current_plan_row`'s own docstring: *"a spurious refusal
  (recoverable in one further request)"*). Here the retry could never succeed;
* **`final_count` was a projection the execute could not produce.** `CLAUDE.md` §11
  records that `final_count` is *measured, not asserted*.

The fix is `workspace._malformed_experiment_ids`: a workspace-wide preflight, taken
inside `_reset_lock` and BEFORE the mutation loop, refusing with the new typed reason
`malformed_records_present` (409) and naming the ids in `malformed_ids`. §5 below is the
negative control that proves the preflight — and not something else — is what does it, by
putting the refusal back inside the loop and observing the original defect return.

**THE PREDICATE IS READER DISAGREEMENT, NOT "the strict reader raised", and §6 is where
that is pinned.** The first version of this fix asked only whether `_current_plan_row`
answered `_UNREADABLE_ROW`, which is the mechanism the reviewer's `title`-absent case
uses. Measured over all eight of F2's documents, **seven break the reset and only four of
those raise**: `draft`, `source` and `answer_log` holding a wrong-typed value hydrate
STRICTLY WITHOUT ERROR, to different content than the tolerant reader produces, so the
rows differ and the loop aborts identically. The raise-shaped predicate left three of the
seven destroying records and looked complete, because the four loudest cases passed. The
eighth (`created_utc` holding an int) is correctly NOT reported — it is in no element of
the plan row, both readers agree, and the reset runs cleanly over it.

**These tests assert on what is still ON DISK, not only on the status code.** A reset that
answers 409 while having removed a record is the whole defect, and a status-code-only test
would pass through it.

Everything here is synthetic: the committed reference fixtures and the committed simulated
answers, inside `tmp_path`. The truth core is never bypassed and nothing is written outside
the test's workspace.
"""

from __future__ import annotations

import json

import pytest

import isaac_api.workspace as ws

from conftest import tutorial_client, tutorial_ws

CONFIRM = "RESET EXAMPLE WORKSPACE"

_DELETE = object()

#: F2's own eight malformed documents, copied from
#: `test_one_malformed_document_does_not_take_down_the_list.py` on purpose rather than
#: imported: that file's list is the definition of "a malformed document is real enough to
#: fix", and this file's whole premise is that the SAME documents must be treated as real
#: on the destructive path. If the two lists ever diverge, the divergence is the finding.
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
    from isaac_api.app import create_app

    # `raise_server_exceptions=False` so an unhandled 500 is OBSERVED as a 500 rather
    # than re-raised into the test — the reproduction above depends on that.
    return tutorial_client(create_app(), raise_server_exceptions=False)


# --- helpers ------------------------------------------------------------------


def _state_path(experiment_id: str):
    return tutorial_ws().workspace_root() / experiment_id / "experiment.json"


def _poke(experiment_id: str, key: str, value) -> None:
    """Degrade ONE persisted document in place, exactly as F2's suite does."""
    path = _state_path(experiment_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    if value is _DELETE:
        state.pop(key, None)
    else:
        state[key] = value
    path.write_text(json.dumps(state), encoding="utf-8")


def _break(experiment_id: str) -> None:
    """The reviewer's exact case: a canonical seed whose `title` is gone."""
    _poke(experiment_id, "title", _DELETE)


def _dirs_on_disk() -> set[str]:
    """Ids present ON DISK — the assertion that a status-code-only test cannot make."""
    return {p.name for p in tutorial_ws().workspace_root().iterdir() if p.is_dir()}


def _preview(client):
    return client.post("/api/demo/reset", json={"mode": "preview"})


def _execute(client, *, token, confirmation=CONFIRM):
    body: dict = {"mode": "execute"}
    if confirmation is not None:
        body["confirmation"] = confirmation
    if token is not None:
        body["plan_digest"] = token
    return client.post("/api/demo/reset", json=body)


def _execute_fresh(client):
    """Preview, then execute with THAT preview's digest — the honest client's loop.

    Used so a refusal can never be blamed on a stale precondition: this client always
    presents the digest the server has just issued.
    """
    return _execute(client, token=_preview(client).json()["plan_digest"])


def _make_managed_legacy(title: str = "Older example record (example run)"):
    """A pre-canonical managed record: random id + the committed provenance marker."""
    return tutorial_ws().create_experiment(
        title=title,
        source={
            "description": ws.MANAGED_SOURCE_DESCRIPTION,
            "files": list(ws.SOURCE_FILES),
        },
        draft=ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH),
    )


def _make_unrelated(title: str = "Some other experiment"):
    """A record with NO managed marker — classifies ambiguous, never removed."""
    return tutorial_ws().create_experiment(
        title=title,
        source={"description": "hand-authored / unknown provenance", "files": []},
        draft=ws.build_draft(ws.CSV_PATH, ws.LISTING_PATH),
    )


# --- 1. the reproduction --------------------------------------------------------


def test_the_preview_refuses_instead_of_projecting_a_reset_it_cannot_perform(client):
    """OBSERVED BEFORE: `200`, `refusal_reason: null`, `final_count: 5`."""
    tutorial_ws().ensure_tutorial_seeded()
    _make_managed_legacy()
    _break(ws.SEED_READY_ID)

    body = _preview(client).json()

    assert body["status"] == "refused"
    assert body["refusal_reason"] == "malformed_records_present"
    # CLAUDE.md §11: `final_count` is MEASURED, not asserted. A preview that cannot be
    # carried out must not project the count a successful one would leave behind.
    assert body["final_count"] == body["previous_count"] == 6


def test_the_execute_destroys_nothing_and_gives_a_reason_that_is_true(client):
    """OBSERVED BEFORE: `412 plan_digest_stale`, `removed_count: 1`, the record gone."""
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    _break(ws.SEED_READY_ID)
    before = _dirs_on_disk()

    r = _execute_fresh(client)

    assert r.status_code == 409, r.text
    body = r.json()
    assert body["refusal_reason"] == "malformed_records_present"
    assert body["removed_count"] == 0
    # THE ASSERTION THAT MATTERS. The defect answered a refusal with the record already
    # deleted; a status code alone cannot tell the two apart.
    assert _dirs_on_disk() == before
    assert legacy.id in _dirs_on_disk()


def test_the_reason_is_never_the_one_whose_remedy_cannot_work(client):
    """`plan_digest_stale` means "re-preview and retry". The retry could never succeed."""
    tutorial_ws().ensure_tutorial_seeded()
    _make_managed_legacy()
    _break(ws.SEED_READY_ID)

    r = _execute_fresh(client)

    assert r.json()["refusal_reason"] != "plan_digest_stale"
    assert r.status_code != 412


def test_the_refusal_is_stable_and_destroys_nothing_on_any_retry(client):
    """OBSERVED BEFORE: `412` forever, having destroyed the legacy set on the first try."""
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    _break(ws.SEED_READY_ID)
    before = _dirs_on_disk()

    for attempt in range(3):
        r = _execute_fresh(client)
        assert r.status_code == 409, (attempt, r.text)
        assert r.json()["refusal_reason"] == "malformed_records_present", attempt
        assert r.json()["removed_count"] == 0, attempt
        assert _dirs_on_disk() == before, f"attempt {attempt} destroyed something"
    assert legacy.id in _dirs_on_disk()


def test_the_second_reproduction_three_legacy_records_with_the_last_one_malformed(client):
    """OBSERVED BEFORE: execute removed **2 of 3** and then refused permanently."""
    tutorial_ws().ensure_tutorial_seeded()
    created = {_make_managed_legacy(f"legacy {n}").id for n in "ABC"}
    # The order the reset walks is the order `_load_all_experiments` presents, so the
    # LAST of the three is the one the loop reaches after removing the other two.
    order = [e.id for e in tutorial_ws()._load_all_experiments() if e.id in created]
    assert len(order) == 3
    _break(order[-1])

    r = _execute_fresh(client)

    assert r.status_code == 409, r.text
    assert r.json()["removed_count"] == 0
    assert created <= _dirs_on_disk(), "all three managed-legacy records must survive"


def test_a_malformed_canonical_seed_is_not_repaired_by_a_refusal(client):
    """Stated because it is the honest limit of this fix, not an oversight.

    The reset cannot restore a canonical seed while refusing to run, so the malformed
    document is still malformed afterwards. What changed is that the operator is now TOLD
    which record it is, instead of watching a retry loop destroy a little more each time.
    Repairing an unreadable document is a different decision and is not taken here.
    """
    tutorial_ws().ensure_tutorial_seeded()
    _break(ws.SEED_READY_ID)

    _execute_fresh(client)

    state = json.loads(_state_path(ws.SEED_READY_ID).read_text(encoding="utf-8"))
    assert "title" not in state


# --- 2. what the refusal is allowed to say --------------------------------------


def test_the_refusal_names_the_malformed_record_and_discloses_nothing_more(client):
    """Actionable, and bounded by what this surface already shows.

    Ids are already on this response (`canonical_ids`, `removable[].id`), so naming one
    here is not a new class of disclosure. A TITLE would be, and would additionally be
    dishonest: for an unreadable document it comes from the read path's fallbacks rather
    than from the document.
    """
    tutorial_ws().ensure_tutorial_seeded()
    _break(ws.SEED_READY_ID)

    body = _preview(client).json()

    assert body["malformed_ids"] == [ws.SEED_READY_ID]
    blob = json.dumps(body)
    assert str(tutorial_ws().workspace_root()) not in blob
    assert "experiment.json" not in blob


def test_malformed_ids_is_empty_when_every_document_reads(client):
    """The field must be safe to branch on, which means it is present and empty on
    every other outcome rather than absent."""
    tutorial_ws().ensure_tutorial_seeded()
    _make_managed_legacy()

    assert _preview(client).json()["malformed_ids"] == []
    assert _execute_fresh(client).json()["malformed_ids"] == []


def test_every_reported_id_is_sorted_and_deduplicated(client):
    tutorial_ws().ensure_tutorial_seeded()
    _break(ws.SEED_PARTIAL_ID)
    _break(ws.SEED_READY_ID)

    ids = _preview(client).json()["malformed_ids"]

    assert ids == sorted({ws.SEED_PARTIAL_ID, ws.SEED_READY_ID})


# --- 3. the §11 reset invariants are unchanged ----------------------------------


def test_an_omitted_plan_digest_is_still_428_and_still_mutates_nothing(client):
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    _break(ws.SEED_READY_ID)
    before = _dirs_on_disk()

    r = _execute(client, token=None)

    assert r.status_code == 428, r.text
    assert r.json()["refusal_reason"] == "plan_digest_required"
    assert _dirs_on_disk() == before
    assert legacy.id in _dirs_on_disk()


def test_a_stale_plan_digest_still_outranks_the_malformed_refusal(client):
    """Unchanged precedence, and it is deliberate.

    A client holding a stale plan is told to look again rather than handed a
    classification verdict about a session it has never seen — the same reason the
    ambiguity verdict sits behind the precondition. Its re-preview then names the
    unreadable record, which is the "recoverable in one further request" the reason
    means.
    """
    tutorial_ws().ensure_tutorial_seeded()
    stale = _preview(client).json()["plan_digest"]
    _make_managed_legacy()  # the session moves after the operator's preview
    _break(ws.SEED_READY_ID)

    r = _execute(client, token=stale)

    assert r.status_code == 412, r.text
    assert r.json()["refusal_reason"] == "plan_digest_stale"
    # ...and the one further request tells the truth.
    assert _preview(client).json()["refusal_reason"] == "malformed_records_present"


def test_a_wrong_confirmation_phrase_is_still_checked_first(client):
    tutorial_ws().ensure_tutorial_seeded()
    _break(ws.SEED_READY_ID)
    token = _preview(client).json()["plan_digest"]

    r = _execute(client, token=token, confirmation="RESET")

    assert r.status_code == 409, r.text
    assert r.json()["refusal_reason"] == "confirmation_required"


def test_malformed_outranks_ambiguous_because_it_claims_less(client):
    """A verdict about a document's CONTENT must not be given for a document that
    would not parse: `_hydrate_experiment` falls a non-dict `source` back to `{}`, so the
    ambiguity verdict for a degraded document is derived from normalised content."""
    tutorial_ws().ensure_tutorial_seeded()
    unrelated = _make_unrelated()
    _poke(unrelated.id, "source", "nope")

    body = _preview(client).json()

    assert body["refusal_reason"] == "malformed_records_present"
    assert body["malformed_ids"] == [unrelated.id]


def test_ambiguous_still_refuses_with_409_when_every_document_reads(client):
    """The pre-existing refusal is untouched — this slice adds a tier, it replaces none."""
    tutorial_ws().ensure_tutorial_seeded()
    unrelated = _make_unrelated()
    legacy = _make_managed_legacy()

    r = _execute_fresh(client)

    assert r.status_code == 409, r.text
    assert r.json()["refusal_reason"] == "ambiguous_records_present"
    assert {unrelated.id, legacy.id} <= _dirs_on_disk()


# --- 4. the healthy path is not made timid --------------------------------------


def test_a_readable_session_still_resets_completely(client):
    """A fail-closed gate that also closes on the healthy case is not a fix."""
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()

    r = _execute_fresh(client)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["refusal_reason"] is None
    assert body["removed_count"] == 1
    assert body["final_count"] == len(ws.CANONICAL_IDS) == 5
    assert legacy.id not in _dirs_on_disk()
    assert _dirs_on_disk() == set(ws.CANONICAL_IDS)


def test_the_preflight_examines_each_document_exactly_once_per_call(client, monkeypatch):
    """The preflight costs one extra read and one extra strict hydration per record.

    Pinned so a later slice cannot quietly turn it into a pass per record PER MUTATED
    ID, which on a scope of N records would be N^2 strict reads on the destructive path.
    """
    tutorial_ws().ensure_tutorial_seeded()
    calls: list[list] = []
    real = ws._strict_plan_row

    def counting(state, session_id):
        row = real(state, session_id)
        calls.append(row)
        return row

    monkeypatch.setattr(ws, "_strict_plan_row", counting)
    _preview(client)

    assert len(calls) == len(ws.CANONICAL_IDS) == 5
    assert sorted(row[0] for row in calls) == sorted(ws.CANONICAL_IDS)


# --- 5. the mutations -----------------------------------------------------------
#
# Each one removes exactly one guard and asserts the ORIGINAL defect returns. A test that
# passes with the guard removed is testing nothing.


def test_MUTATION_putting_the_refusal_back_inside_the_loop_destroys_records(
    client, monkeypatch
):
    """THE NEGATIVE CONTROL FOR THIS WHOLE FILE, and the exact defect.

    Neutralising `_malformed_experiment_ids` leaves the per-record check in the mutation
    loop as the only gate — which is precisely the shape the reviewer reproduced. The
    original behaviour must come back: a managed-legacy record DESTROYED, then `412`
    `plan_digest_stale`, then `412` forever. If this test ever stops observing that, the
    fix above has stopped being what makes §1 pass.
    """
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    _break(ws.SEED_READY_ID)
    monkeypatch.setattr(ws, "_malformed_experiment_ids", lambda ids, session_id: [])

    first = _execute_fresh(client)

    assert first.status_code == 412, first.text
    assert first.json()["refusal_reason"] == "plan_digest_stale"
    assert first.json()["removed_count"] == 1
    assert legacy.id not in _dirs_on_disk(), "the defect is that this record is destroyed"

    for attempt in range(2):
        again = _execute_fresh(client)
        assert again.status_code == 412, attempt
        assert again.json()["removed_count"] == 0, attempt
    assert ws.SEED_READY_ID in _dirs_on_disk()
    assert "title" not in json.loads(_state_path(ws.SEED_READY_ID).read_text())


def test_MUTATION_the_preview_projection_returns_when_the_preflight_is_removed(
    client, monkeypatch
):
    """The second half of the same defect: `final_count: 5` on a reset that cannot run."""
    tutorial_ws().ensure_tutorial_seeded()
    _make_managed_legacy()
    _break(ws.SEED_READY_ID)
    monkeypatch.setattr(ws, "_malformed_experiment_ids", lambda ids, session_id: [])

    body = _preview(client).json()

    assert body["refusal_reason"] is None
    assert body["final_count"] == 5 != body["previous_count"]


def test_MUTATION_forwarding_the_reason_is_what_stops_the_route_mislabelling_it(client):
    """The route used to hardcode `ambiguous_records_present` for every non-stale
    refusal. With the hardcode in place this body would read `ambiguous_records_present`
    over a session with zero ambiguous records — a false reason on the destructive path,
    produced by a route that never read the answer it was given.
    """
    tutorial_ws().ensure_tutorial_seeded()
    _break(ws.SEED_READY_ID)

    body = _execute_fresh(client).json()

    assert body["ambiguous_count"] == 0
    assert body["refusal_reason"] == "malformed_records_present"


def test_the_per_record_check_still_backstops_a_document_that_breaks_in_the_window(
    client, monkeypatch
):
    """The preflight does NOT replace the check inside the loop, and this pins it.

    A document that becomes unreadable AFTER the preflight really has changed in the
    window, so `plan_digest_stale` is the TRUE reason for it — and the operator's next
    preview names the record, which is the one-further-request recovery that reason
    promises. Simulated by breaking the document from inside the preflight itself, which
    is the only way to land a change in a window the test cannot otherwise reach.
    """
    tutorial_ws().ensure_tutorial_seeded()
    _make_managed_legacy()
    real = ws._malformed_experiment_ids

    def break_it_in_the_window(ids, session_id):
        _break(ws.SEED_READY_ID)
        return []

    monkeypatch.setattr(ws, "_malformed_experiment_ids", break_it_in_the_window)
    r = _execute_fresh(client)

    assert r.status_code == 412, r.text
    assert r.json()["refusal_reason"] == "plan_digest_stale"

    # Restored by SETATTR, not by `monkeypatch.undo()`: this is the same `monkeypatch`
    # the `client` fixture used to point `ISAAC_UI_WORKSPACE` at `tmp_path`, and
    # `undo()` would roll that back too — the preview below would then read a different
    # workspace and the assertion would pass or fail for the wrong reason.
    monkeypatch.setattr(ws, "_malformed_experiment_ids", real)
    assert _preview(client).json()["refusal_reason"] == "malformed_records_present"


# --- 6. every one of F2's own eight documents -----------------------------------

#: The three that hydrate STRICTLY WITHOUT ERROR and still break the reset, because the
#: two readers read them to different content. They are the reason the preflight asks
#: "do the readers agree?" rather than "did the strict reader raise?" — a predicate
#: written around the raise covers four of the seven breaking documents and looks
#: complete, because the four loudest cases pass.
#:
#: Measured, per case, strict row vs. tolerant row:
#:   `draft: "nope"`      — differing `_authoritative_signature`
#:   `source: "nope"`     — differing `_authoritative_signature`
#:   `answer_log: "nope"` — `len(exp.answer_log or [])` is 4 strictly (over the string)
#:                          and 0 tolerantly
SILENTLY_DIVERGENT = [
    ("draft is not an object", "draft", "nope"),
    ("source is not an object", "source", "nope"),
    ("answer_log is not a list", "answer_log", "nope"),
]

#: The one of the eight that does NOT break the reset, and is correctly NOT reported.
#: `created_utc` is in no element of the plan row, so both readers build the same row
#: and the reset runs cleanly over it. The preflight reports documents that BREAK THE
#: RESET, not documents that are ill-formed — pinned so a later slice does not "fix"
#: this into a refusal and call it an improvement.
AGREED = ("created_utc is not a string", "created_utc", 5)


@pytest.mark.parametrize(
    "label,key,value", SILENTLY_DIVERGENT, ids=[m[0] for m in SILENTLY_DIVERGENT]
)
def test_a_document_that_hydrates_strictly_and_still_diverges_is_reported(
    client, label, key, value
):
    """THE CASE THE FIRST VERSION OF THIS FIX MISSED, and it missed three of seven.

    The strict reader raises on none of these. Each is nevertheless fatal to the reset
    in exactly the same way as a raise: the row differs, so the mutation loop aborts on
    it, so the reset destroys what it reached and then refuses forever.
    """
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    _poke(ws.SEED_READY_ID, key, value)

    # The strict reader is untroubled by this document — so a preflight built around
    # `_UNREADABLE_ROW` would have seen nothing wrong with it.
    state = json.loads(_state_path(ws.SEED_READY_ID).read_text(encoding="utf-8"))
    assert ws._strict_plan_row(state, client.tutorial_session_id) != ws._UNREADABLE_ROW, label

    body = _preview(client).json()
    assert body["refusal_reason"] == "malformed_records_present", label
    assert body["malformed_ids"] == [ws.SEED_READY_ID], label

    r = _execute_fresh(client)
    assert r.status_code == 409, (label, r.text)
    assert r.json()["removed_count"] == 0, label
    assert legacy.id in _dirs_on_disk(), label


def test_a_malformed_field_the_plan_row_does_not_see_is_deliberately_not_reported(client):
    """The negative half of the predicate, and it is a claim about honesty.

    `created_utc` holding an int is malformed by F2's list and is NOT reported here,
    because both readers build the same row from it and the reset completes correctly.
    Reporting it would refuse a reset that works, over a field the decision does not
    depend on.
    """
    _label, key, value = AGREED
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    _poke(ws.SEED_READY_ID, key, value)

    assert _preview(client).json()["malformed_ids"] == []
    r = _execute_fresh(client)
    assert r.status_code == 200, r.text
    assert r.json()["removed_count"] == 1
    assert legacy.id not in _dirs_on_disk()



@pytest.mark.parametrize("label,key,value", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_no_malformed_document_can_make_the_reset_destroy_and_then_refuse(
    client, label, key, value
):
    """The invariant, over all eight, whether or not a given case is unhydratable.

    Deliberately NOT "every case refuses": not all eight defeat the strict reader, and
    asserting that they do would be asserting something unmeasured. What must hold for
    every one of them is the property the defect broke — **the reset either proceeds
    cleanly or refuses having destroyed nothing.** The combination the defect produced —
    a refusal with `removed_count > 0` — must be unreachable.
    """
    tutorial_ws().ensure_tutorial_seeded()
    legacy = _make_managed_legacy()
    _poke(ws.SEED_READY_ID, key, value)
    before = _dirs_on_disk()

    r = _execute_fresh(client)
    body = r.json()

    if r.status_code == 200:
        assert body["refusal_reason"] is None, label
        assert legacy.id not in _dirs_on_disk(), label
        return
    assert body["removed_count"] == 0, f"{label}: refused AFTER destroying something"
    assert _dirs_on_disk() == before, f"{label}: refused AFTER destroying something"
    assert body["refusal_reason"] != "plan_digest_stale", (
        f"{label}: a reason whose documented remedy is 'retry', for a state where "
        f"retry can never succeed"
    )
    assert body["final_count"] == body["previous_count"], label

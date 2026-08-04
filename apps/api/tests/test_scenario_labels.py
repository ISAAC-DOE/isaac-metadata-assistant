"""Derived scenario labels for the five canonical synthetic seeds.

The five canonical seeds share ONE scientific title (the lifecycle suffix the
backend appends is stripped for display), so the API additionally serves a
DERIVED scenario label naming which seeded fixture a row is. This module pins
that contract:

* the five id -> label mappings are exactly what the seed builders produce;
* the label is DERIVED at serialization time and never stored on disk;
* a non-canonical (user-created) id has NO scenario;
* the label names the seeded fixture AT MATERIALISATION TIME, in the past tense,
  and is deliberately never refreshed — so advancing a record through the real
  supported flow changes its derived status without FALSIFYING the label.
  Invariance of the value alone would NOT establish that: an invariant
  present-tense state description over a mutating record is guaranteed to go
  false, which is exactly what an earlier wording did ("Scenario 2 · Partially
  Confirmed" survived unchanged while the record became fully confirmed,
  exported and done). Both properties are pinned separately below;
* the label reaches NO draft, official record, evidence sidecar, or export.

Everything is exercised through the public workspace + HTTP surface against the
two committed synthetic fixtures and the committed demo answers. Nothing under
``examples/`` is read and the truth core is never bypassed or modified.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_records.complete import apply_answers
from isaac_records.export import export_draft

from conftest import open_tutorial_scope, tutorial_client, tutorial_ws

#: The pinned contract. Each label states HOW ITS FIXTURE WAS MATERIALISED, and is
#: traced here to the seed builder that does the materialising:
#:   1 ``_raw_draft``     — ``build_draft`` only, no answers applied at all
#:                          -> "extraction only"
#:   2 ``_partial_draft`` — only the committed answers MINUS ``series`` and
#:                          ``descriptor`` applied
#:                          -> "some answers confirmed"
#:   3 ``_full_draft``    — every committed answer applied
#:                          -> "all answers confirmed"
#:   4 ``_review_draft``  — full answers MINUS the descriptor's ``uncertainty``
#:                          sub-key (``answers["descriptor"].pop("uncertainty")``),
#:                          which the official schema lists as a REQUIRED descriptor
#:                          property (schema/isaac_record_v1.json)
#:                          -> "descriptor uncertainty omitted"
#:   5 ``_full_draft`` + ``exported=True``, so ``_materialise_seed`` runs the REAL
#:                          ``export_draft`` while building the fixture
#:                          -> "export run"
#:
#: Every clause is past tense and about SETUP, never about the record's current
#: state, so no later user action can make it false. Seed 5 deliberately avoids the
#: bare word "Exported" so the badge does not verbatim-duplicate the lifecycle chip
#: rendered on the same row.
#: P1 renamed the user-visible prefix ``Scenario N`` -> ``Example N`` and the
#: materialisation-scope marker ``seeded:`` -> ``at setup:``. Both were development
#: jargon; NEITHER was decorative, so both were replaced rather than dropped — the
#: numbering still distinguishes five examples from five duplicates, and the scope
#: marker is still the only thing keeping each clause past-tense. Every assertion
#: below is unchanged in strictness, WITH ONE EXCEPTION, named here because the
#: blanket claim was false as first written: ``test_no_draft_contains_the_label``
#: was NARROWED. It previously asserted the bare word ``Scenario`` appears nowhere
#: in any draft; it now asserts only the ``Example N ·`` shape, because ``Example``
#: on its own is ordinary English that legitimate draft prose may contain while
#: ``Scenario`` was not. The narrowing is defensible and is argued at its own site;
#: it is a real loss of strictness and must not be described as a string move.
EXPECTED_LABELS = {
    ws.SEED_NEW_DRAFT_ID: "Example 1 · at setup: extraction only",
    ws.SEED_PARTIAL_ID: "Example 2 · at setup: some answers confirmed",
    ws.SEED_READY_ID: "Example 3 · at setup: all answers confirmed",
    ws.SEED_REVIEW_ID: "Example 4 · at setup: descriptor uncertainty omitted",
    ws.SEED_DONE_ID: "Example 5 · at setup: export run",
}

ALL_LABEL_STRINGS = tuple(EXPECTED_LABELS.values())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app

    return tutorial_client(create_app())


@pytest.fixture()
def seeded_ws(tmp_path, monkeypatch):
    """The store bound to an isolated worked-example session (no HTTP).

    Re-pointed from the normal workspace, which is no longer auto-seeded. The five
    canonical records and every assertion about them are unchanged; only the
    directory they live in is.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    return open_tutorial_scope()


def _experiments(client) -> list[dict]:
    return client.get("/api/experiments").json()["experiments"]


# --- 1. the five id -> label mappings -----------------------------------------


@pytest.mark.parametrize(("seed_id", "label"), sorted(EXPECTED_LABELS.items()))
def test_scenario_label_for_each_canonical_id(seed_id, label):
    assert ws.scenario_label(seed_id) == label


def test_every_canonical_id_has_a_label_and_nothing_else_does():
    assert set(ws.SEED_SCENARIOS) == set(ws.CANONICAL_IDS)


def test_labels_are_distinct():
    assert len(set(EXPECTED_LABELS.values())) == 5


def test_list_endpoint_serves_the_label_for_all_five_rows(client):
    rows = _experiments(client)
    assert len(rows) == 5
    assert {r["id"]: r["scenario"] for r in rows} == EXPECTED_LABELS


def test_detail_endpoint_serves_the_same_label(client):
    for seed_id, label in EXPECTED_LABELS.items():
        body = client.get(f"/api/experiments/{seed_id}").json()
        assert body["scenario"] == label


def test_label_is_derived_from_the_same_seed_spec_that_builds_the_title():
    """One source of truth: the label mapping is built from ``_seed_specs()``, the
    same rows that author the titles. Nothing parses a title to recover a label."""
    specs = {s.id: s for s in ws._seed_specs()}
    assert {i: s.scenario for i, s in specs.items()} == EXPECTED_LABELS
    # ...and the label is NOT a substring-derivable transform of the title: the
    # titles carry lifecycle suffixes, never the scenario wording.
    for seed_id, label in EXPECTED_LABELS.items():
        assert label not in specs[seed_id].title


# --- 2. derived, never stored --------------------------------------------------


def test_experiment_state_has_no_scenario_key(seeded_ws):
    for exp in seeded_ws.list_experiments():
        assert "scenario" not in exp.to_state()
        assert not hasattr(exp, "scenario")


def test_on_disk_state_file_never_contains_the_label(seeded_ws):
    for exp in seeded_ws.list_experiments():
        raw = exp.state_path.read_text(encoding="utf-8")
        assert "scenario" not in raw
        for label in ALL_LABEL_STRINGS:
            assert label not in raw


def test_save_load_round_trip_adds_no_new_key(seeded_ws):
    """A full save -> reload -> save round-trip must not introduce a stored
    scenario: the on-disk key set is byte-identical before and after."""
    for exp in seeded_ws.list_experiments():
        before = json.loads(exp.state_path.read_text(encoding="utf-8"))
        reloaded = seeded_ws.load_experiment(exp.id)
        assert reloaded is not None
        reloaded.save()
        after = json.loads(exp.state_path.read_text(encoding="utf-8"))
        assert set(after) == set(before)
        assert "scenario" not in after
        assert after == before
        # The label is still available — because it is derived from the id.
        assert seeded_ws.scenario_label(reloaded.id) == EXPECTED_LABELS[reloaded.id]


def test_label_survives_a_fresh_workspace_without_any_stored_state(tmp_path, monkeypatch):
    """Derivation, not persistence: a brand-new workspace (no state files yet)
    already resolves every label."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "pristine"))
    assert {i: ws.scenario_label(i) for i in ws.CANONICAL_IDS} == EXPECTED_LABELS


# --- 3. non-canonical records have NO scenario --------------------------------


@pytest.mark.parametrize(
    "other_id",
    [
        "01SYNTHTESTEXP000000000000",
        "01SYNTHLEGACYDEMORUN000001",
        ws.SEED_NEW_DRAFT_ID[:-1] + "9",  # near-miss on the canonical prefix
        "",
    ],
)
def test_non_canonical_id_has_no_scenario(other_id):
    assert ws.scenario_label(other_id) is None


def test_non_canonical_record_is_served_with_scenario_null(tmp_path, monkeypatch):
    """A non-canonical (user/ad-hoc) record's summary carries ``scenario: null`` —
    never a label, never a placeholder string. The UI renders nothing for it."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    from isaac_api.app import create_app
    from isaac_records.extract.draft_builder import build_draft

    client = tutorial_client(create_app())
    exp = tutorial_ws().create_experiment(
        "Ad hoc synthetic record",
        {"description": ws.MANAGED_SOURCE_DESCRIPTION, "files": list(ws.SOURCE_FILES)},
        build_draft(ws.CSV_PATH, ws.LISTING_PATH),
    )
    assert exp.id not in ws.CANONICAL_IDS

    row = next(r for r in _experiments(client) if r["id"] == exp.id)
    assert row["scenario"] is None
    detail = client.get(f"/api/experiments/{exp.id}").json()
    assert detail["scenario"] is None
    # ...and the canonical rows in the SAME response still carry theirs.
    labelled = {r["id"]: r["scenario"] for r in _experiments(client) if r["scenario"] is not None}
    assert labelled == EXPECTED_LABELS


# --- 4. the label describes SETUP, so advancing the record cannot falsify it ----
#
# Two DIFFERENT properties, pinned separately, because the first does NOT imply the
# second:
#   (a) the label's VALUE is invariant under mutation
#       -> test_label_is_unchanged_when_the_record_advances
#   (b) the label's WORDING is scoped to materialisation, so the invariant value
#       stays a TRUE statement after the record has advanced
#       -> test_advanced_seed_label_is_not_falsified_by_the_new_state
# An invariant PRESENT-TENSE state description satisfies (a) and violates (b), and
# that is precisely the defect this file previously asserted was impossible.


def test_label_is_unchanged_when_the_record_advances(seeded_ws):
    """Confirming the outstanding answers on the partial seed changes its pending
    count and derived status, but NOT its scenario label.

    This pins INVARIANCE OF THE VALUE only. Invariance alone does NOT make the
    badge safe beside the live status chip — an unchanging *present-tense* state
    description would be guaranteed to end up false. Non-contradiction is a
    property of the WORDING and is pinned separately, by
    ``test_advanced_seed_label_is_not_falsified_by_the_new_state``.
    """
    exp = seeded_ws.load_experiment(seeded_ws.SEED_PARTIAL_ID)
    assert exp is not None
    before_pending = exp.pending_count()
    assert before_pending > 0
    label_before = seeded_ws.scenario_label(exp.id)

    exp.draft = apply_answers(exp.draft, copy.deepcopy(seeded_ws.load_demo_answers()))
    exp.save_versioned()

    after = seeded_ws.load_experiment(exp.id)
    assert after is not None
    assert after.pending_count() < before_pending
    assert seeded_ws.scenario_label(after.id) == label_before
    assert label_before == EXPECTED_LABELS[seeded_ws.SEED_PARTIAL_ID]


#: The materialisation-scope marker every label must carry after ``Example N · ``.
#: Without an explicit scope the clause reads as a description of the record as it
#: is NOW, and an unchanging description of a mutating record goes false.
SCOPE_MARKER = "at setup: "

#: The numbering prefix every label must carry. ``Example `` since P1.
LABEL_PREFIX = "Example "


def _if_match(client, exp_id: str) -> dict:
    return {"If-Match": client.get(f"/api/experiments/{exp_id}").headers["ETag"]}


def _descriptor(draft: dict) -> dict:
    """The single descriptor the completion answers write, or ``{}`` if there is none."""
    blocks = draft.get("descriptors_outputs") or []
    if not blocks:
        return {}
    return (blocks[0].get("descriptors") or [{}])[0]


def test_advanced_seed_label_is_not_falsified_by_the_new_state(client):
    """Advance seeds through the REAL supported flow, then prove the label still holds.

    No bypass: seed 2 is completed with the committed demo answers via
    ``POST /answers``; seed 4 has its descriptor (WITH uncertainty) supplied via
    ``POST /edit``; both are then exported via ``POST /export``. Each ends at
    ``pending_count == 0``, ``exported: true``, ``status: done`` — so the state the
    fixture was seeded in is genuinely gone.

    For each seed the test then shows, on the record itself, that the *materialisation
    claim the label makes* is FALSE of the live record and TRUE of the freshly
    materialised fixture: seed 4's live descriptor now HAS an uncertainty, and seed 2's
    live draft now has every answer applied. Read as a present-tense description of the
    record, the label would therefore be a lie on screen. It is not one, because the
    ``at setup:`` scope confines it to setup — which is the property asserted here, and
    the property the earlier wording ("Partially Confirmed", "Missing Required Field")
    did not have.
    """
    pristine = {s.id: s for s in ws._seed_specs()}

    # -- seed 2: answer the two remaining blockers through /answers, then export ---
    pid = ws.SEED_PARTIAL_ID
    before = client.get(f"/api/experiments/{pid}").json()
    assert before["pending_count"] == 2 and before["exported"] is False
    label = before["scenario"]
    assert label == EXPECTED_LABELS[pid]

    answers = {
        b["id"]: b["demo_answer"]["value"]
        for b in client.get(f"/api/experiments/{pid}/pending").json()["pending"]
        if b["demo_answer"] is not None
    }
    assert set(answers) == {"series", "descriptor"}, answers
    r = client.post(
        f"/api/experiments/{pid}/answers",
        json={"answers": answers, "confirmed_by_user": True},
        headers=_if_match(client, pid),
    )
    assert r.status_code == 200, r.text
    r = client.post(f"/api/experiments/{pid}/export", headers=_if_match(client, pid))
    assert r.status_code == 200 and r.json()["ok"] is True, r.text

    after = client.get(f"/api/experiments/{pid}").json()
    assert (after["pending_count"], after["exported"], after["status"]) == (0, True, "done")
    # (a) the value did not move...
    assert after["scenario"] == label
    # (b) ...and it is still TRUE, because it is scoped to setup. Read as a claim
    # about the record NOW it would be false: only PART of the answers were applied
    # at setup, but the live draft now carries all of them.
    assert label.split(" · ", 1)[1].startswith(SCOPE_MARKER), (
        f"{label!r} states no scope, so it reads as a description of the record as "
        "it is now — which this advance has just falsified"
    )
    assert len(pristine[pid].draft_fn()["pending"]) == 2, "setup left blockers open"
    assert len(tutorial_ws().load_experiment(pid).draft["pending"]) == 0, "live record has none"

    # -- seed 4: supply the omitted descriptor uncertainty via /edit, then export --
    rid = ws.SEED_REVIEW_ID
    before = client.get(f"/api/experiments/{rid}").json()
    assert (before["pending_count"], before["status"]) == (0, "in_review")
    label = before["scenario"]
    assert label == EXPECTED_LABELS[rid]
    # The seeded fixture really does omit the uncertainty — the label's claim.
    assert "uncertainty" not in _descriptor(pristine[rid].draft_fn())

    full_descriptor = copy.deepcopy(ws.load_demo_answers()["descriptor"])
    assert "uncertainty" in full_descriptor
    r = client.post(
        f"/api/experiments/{rid}/edit",
        json={"answers": {"descriptor": full_descriptor}, "confirmed_by_user": True},
        headers=_if_match(client, rid),
    )
    assert r.status_code == 200, r.text
    r = client.post(f"/api/experiments/{rid}/export", headers=_if_match(client, rid))
    assert r.status_code == 200 and r.json()["ok"] is True, r.text

    after = client.get(f"/api/experiments/{rid}").json()
    assert (after["pending_count"], after["exported"], after["status"]) == (0, True, "done")
    # The record now passes official validation and has an exported record — the
    # descriptor uncertainty is present.
    assert "uncertainty" in _descriptor(tutorial_ws().load_experiment(rid).draft)
    verdict = client.post(f"/api/experiments/{rid}/validate")
    assert verdict.status_code == 200 and verdict.json()["ok"] is True, verdict.text
    # (a) invariant value, (b) still true — because of the setup scope.
    assert after["scenario"] == label
    assert label.split(" · ", 1)[1].startswith(SCOPE_MARKER), (
        f"{label!r} states no scope, so on this row it now asserts a missing "
        "descriptor uncertainty that the record demonstrably has"
    )


def test_every_label_is_explicitly_scoped_to_materialisation():
    """All five labels — not only the ones the flow above advances — carry the scope
    marker, so none of them can be read as a live-state description."""
    for seed_id, label in EXPECTED_LABELS.items():
        prefix, _, clause = label.partition(" · ")
        assert prefix.startswith(LABEL_PREFIX), label  # the deliberate N prefix stays
        assert clause.startswith(SCOPE_MARKER), f"{seed_id}: {label!r} states no scope"
        assert clause[len(SCOPE_MARKER):].strip(), f"{seed_id}: empty scoped clause"


def test_label_carries_no_count_or_status_vocabulary():
    """The wording is deliberately free of counts and of the derived status
    vocabulary, so it can neither restate nor contradict the status chip / queue
    group. ``Exported``, ``Done`` and ``Draft`` are included because all three are
    DISPLAY strings actually rendered on a row (``LABELS.chipExported``,
    ``LABELS.chipDraft`` and the Done group), so a label reusing any of them would
    verbatim-duplicate a live chip beside it. ``Draft`` was the omission the
    pre-Dean release review caught: the lifecycle chip on EVERY non-exported row
    reads ``Draft``, which makes it the single most collision-prone word of the set,
    and it was the one word the guard did not check. The frontend twin
    (``experiment-scenario-badge.test.tsx``) checks the same list."""
    status_words = (
        ws.NEEDS_ATTENTION,
        ws.IN_REVIEW,
        ws.READY_TO_EXPORT,
        ws.DONE,
        "Needs Attention",
        "In Review",
        "Ready to Export",
        "Exported",
        "Done",
        "Draft",
    )
    for label in ALL_LABEL_STRINGS:
        assert not any(ch.isdigit() for ch in label.split("·", 1)[1])
        for word in status_words:
            assert word.lower() not in label.lower()


# --- 5. the label reaches NO draft / record / sidecar / export -----------------


def test_no_draft_contains_the_label(seeded_ws):
    for exp in seeded_ws.list_experiments():
        blob = json.dumps(exp.draft, ensure_ascii=False)
        for label in ALL_LABEL_STRINGS:
            assert label not in blob
        # The bare numbering prefix must not leak either — checked as the exact
        # "<prefix>N ·" shape a label would carry, because "Example " on its own is
        # an ordinary English word that legitimate draft prose could contain.
        for n in range(1, 6):
            assert f"{LABEL_PREFIX}{n} ·" not in blob


def test_exported_record_and_sidecar_files_do_not_contain_the_label(seeded_ws):
    done = [e for e in seeded_ws.list_experiments() if e.exported()]
    assert len(done) == 1
    exp = done[0]
    for path in (exp.record_path(), exp.sidecar_path()):
        assert path is not None and path.exists()
        raw = path.read_text(encoding="utf-8")
        for label in ALL_LABEL_STRINGS:
            assert label not in raw
        assert "scenario" not in raw.lower()


def test_real_export_of_every_seed_omits_the_label(seeded_ws):
    """Run the REAL ``export_draft`` for each seed; neither the official record
    nor the evidence sidecar may contain the label (or the word 'scenario')."""
    for exp in seeded_ws.list_experiments():
        result = export_draft(copy.deepcopy(exp.draft), seeded_ws.REPO_ROOT)
        for payload in (result.record, result.sidecar):
            if payload is None:
                continue
            blob = json.dumps(payload, ensure_ascii=False)
            for label in ALL_LABEL_STRINGS:
                assert label not in blob
            assert "scenario" not in blob.lower()


def test_artifacts_endpoint_does_not_leak_the_label(client):
    """The artifact payload a user downloads is the official record + sidecar; the
    presentation label must be absent from both."""
    resp = client.get(f"/api/experiments/{ws.SEED_DONE_ID}/artifacts")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["record"] is not None and body["sidecar"] is not None
    blob = json.dumps(body, ensure_ascii=False)
    for label in ALL_LABEL_STRINGS:
        assert label not in blob
    assert "scenario" not in blob.lower()


# --- 6. idempotence: the five canonical records + labels are stable -----------


def test_demo_run_keeps_exactly_five_canonical_records_and_labels(client):
    assert {r["id"] for r in _experiments(client)} == set(ws.CANONICAL_IDS)
    for _ in range(3):
        for mode in ("draft_only", "full"):
            resp = client.post("/api/demo/run", json={"mode": mode})
            assert resp.status_code == 200
            rows = _experiments(client)
            assert len(rows) == 5
            assert {r["id"] for r in rows} == set(ws.CANONICAL_IDS)
            assert {r["id"]: r["scenario"] for r in rows} == EXPECTED_LABELS


def test_reset_restores_the_five_labels(client):
    # R1: an execute carries the plan digest from its own preview (428 without it).
    digest = client.post("/api/demo/reset", json={"mode": "preview"}).json()["plan_digest"]
    resp = client.post(
        "/api/demo/reset",
        json={
            "mode": "execute",
            "confirmation": "RESET EXAMPLE WORKSPACE",
            "plan_digest": digest,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    rows = _experiments(client)
    assert len(rows) == 5
    assert {r["id"]: r["scenario"] for r in rows} == EXPECTED_LABELS


def test_canonical_id_set_is_unchanged():
    """No new ids, and the five fixed ids keep their exact values."""
    assert ws.CANONICAL_IDS == frozenset(EXPECTED_LABELS)
    assert sorted(ws.CANONICAL_IDS) == [
        "01SYNTHXANESSEED0000000001",
        "01SYNTHXANESSEED0000000002",
        "01SYNTHXANESSEED0000000003",
        "01SYNTHXANESSEED0000000004",
        "01SYNTHXANESSEED0000000005",
    ]

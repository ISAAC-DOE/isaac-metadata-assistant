"""Unified provenance — TWO INDEPENDENT DIMENSIONS, derived and never stored.

WHAT THIS FILE IS FOR, in order of how much it would hurt to lose:

1. **Origin must never imply support.** Three negative controls prove that
   ``file``, ``assistant`` and ``derived`` can each carry ``needs_review``, and a
   signature assertion proves there is no parameter through which an origin could
   reach the review-state decision at all. This is the defect the whole module
   exists to prevent: a provenance chip that says "from a spreadsheet" and is read
   as "checked".
2. **The two mapping tables are EXHAUSTIVE over the vocabularies they map**, and
   are checked against those vocabularies rather than against a copy — so adding
   an eighth evidence type to the truth core fails here.
3. **The unreachable arms are pinned as unreachable, precisely.** ``assistant``
   has no producer anywhere; ``voice`` has no producer in the application but IS
   reachable over the notes API, and the test says which is which rather than
   repeating a convenient summary.
4. **The module is not truth-path.** Its imports from ``isaac_records`` are
   asserted against a one-name allowlist, read out of the source with the ``ast``
   module, so a later edit cannot quietly import the validator or the exporter.

Nothing here writes a record, and nothing reads real data: every fixture below is
either a hand-built dict or one of the committed worked-example records.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api import notes as notes_module
from isaac_api import provenance
from isaac_records.models import SOURCE_TYPES

from conftest import tutorial_client

MODULE_PATH = Path(provenance.__file__)

#: Read from the module rather than transcribed, so the frozen shape and what the
#: route actually serves cannot drift apart in opposite directions.
ENTRY_KEYS = set(provenance.ENTRY_KEYS)


def test_the_entry_shape_is_the_eight_documented_keys():
    """Pins the constant itself, so reading it above is not circular.

    `unavailable` was added after independent review found that a PARTIALLY
    unreadable payload reported `supported`. The wire shape had no slot to carry
    the disclosure, so no client could have reached a different verdict either.
    """
    assert ENTRY_KEYS == {
        "address",
        "origins",
        "primary_origin",
        "review_state",
        "evidence_count",
        "inherited",
        "note_refs",
        "unavailable",
    }


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _ev(source_type: str, **kw) -> dict:
    return {"source_type": source_type, **kw}


def _draft(**fields) -> dict:
    return {"fields": fields}


# =============================================================================
# 1 — the vocabularies are closed, and the two tables cover them exhaustively
# =============================================================================


def test_the_two_dimensions_are_the_declared_closed_vocabularies():
    assert provenance.ORIGINS == (
        "manual",
        "file",
        "voice",
        "inherited",
        "assistant",
        "derived",
        "evidence",
        "unknown",
    )
    assert provenance.REVIEW_STATES == (
        "supported",
        "needs_review",
        "conflict",
        "unmapped",
    )
    # No member of one dimension is a member of the other. If they ever overlapped,
    # a single string could not be read unambiguously as one axis or the other.
    assert not set(provenance.ORIGINS) & set(provenance.REVIEW_STATES)


def test_every_truth_core_source_type_is_mapped_and_nothing_else_is():
    """Checked against ``models.SOURCE_TYPES`` itself, not a transcription."""
    assert set(provenance.SOURCE_TYPE_ORIGIN) == set(SOURCE_TYPES)
    assert set(provenance.SOURCE_TYPE_ORIGIN.values()) <= set(provenance.ORIGINS)


def test_every_note_source_is_mapped_and_nothing_else_is():
    assert set(provenance.NOTE_SOURCE_ORIGIN) == set(notes_module.NOTE_SOURCES)
    assert set(provenance.NOTE_SOURCE_ORIGIN.values()) <= set(provenance.ORIGINS)


@pytest.mark.parametrize(
    "source_type,origin",
    [
        ("user_confirmation", "manual"),
        ("document", "file"),
        ("spreadsheet", "file"),
        ("screenshot", "file"),
        ("file_listing", "file"),
        # The one judgement call. `web_form` is an ingested capture of a form the
        # scientist filled in elsewhere — `docs/extraction.md` produces it from the
        # vision row beside `screenshot`, and the committed draft fixture cites it
        # with a `source_file` and a locator. `user_confirmation` is the only
        # evidence type this application mints for a person's own act.
        ("web_form", "file"),
        ("derivation", "derived"),
    ],
)
def test_the_evidence_type_mapping_table(source_type, origin):
    assert provenance.origins_from_evidence([_ev(source_type)]) == [origin]


@pytest.mark.parametrize(
    "source,origin",
    [
        ("typed_note", "manual"),
        ("transcript", "voice"),
        ("csv_column", "file"),
        ("file_listing_line", "file"),
        ("extraction_residue", "file"),
    ],
)
def test_the_note_source_mapping_table(source, origin):
    assert provenance.note_origins(source) == [origin]


def test_the_web_form_judgement_is_pinned_against_the_committed_fixture():
    """The reason `web_form` maps to `file` is checkable, so it is checked.

    If the committed draft fixture ever stops citing a `source_file` for its
    `web_form` evidence, the justification in the mapping table has lost its
    evidence and this fails rather than going quiet.
    """
    import json

    repo_root = Path(__file__).resolve().parents[3]
    fixture = json.loads(
        (repo_root / "tests" / "fixtures" / "cuo_xanes_draft.json").read_text()
    )
    web_form_entries = [
        entry
        for env in fixture["fields"].values()
        for entry in (env.get("evidence") or [])
        if entry.get("source_type") == "web_form"
    ]
    assert web_form_entries, "the fixture no longer carries web_form evidence"
    for entry in web_form_entries:
        assert entry.get("source_file"), entry
        assert entry.get("locator"), entry


# =============================================================================
# 2 — origins are a SET, and the primary is chosen by precedence, never position
# =============================================================================


def test_multiple_evidence_entries_yield_multiple_origins():
    origins = provenance.origins_from_evidence(
        [_ev("spreadsheet"), _ev("user_confirmation"), _ev("derivation", rule="r")]
    )
    assert origins == ["derived", "file", "manual"]


def test_the_primary_origin_is_precedence_and_not_array_position():
    """The same set in both orders must give the same primary."""
    forward = [_ev("user_confirmation"), _ev("spreadsheet")]
    reverse = [_ev("spreadsheet"), _ev("user_confirmation")]
    a = provenance.origins_from_evidence(forward)
    b = provenance.origins_from_evidence(reverse)
    assert a == b
    assert provenance.primary_origin(a) == provenance.primary_origin(b) == "file"
    # And it is not simply "the first declared member" either: `manual` is declared
    # first in ORIGINS and still loses.
    assert provenance.ORIGINS[0] == "manual"


def test_the_precedence_order_is_total_over_the_vocabulary():
    assert set(provenance.ORIGIN_PRECEDENCE) == set(provenance.ORIGINS)
    assert len(provenance.ORIGIN_PRECEDENCE) == len(provenance.ORIGINS)
    assert provenance.ORIGIN_PRECEDENCE[0] == "inherited"
    assert provenance.ORIGIN_PRECEDENCE[-1] == "unknown"
    # Every pair resolves the same way whichever order it is presented in.
    for i, high in enumerate(provenance.ORIGIN_PRECEDENCE):
        for low in provenance.ORIGIN_PRECEDENCE[i + 1 :]:
            assert provenance.primary_origin([high, low]) == high
            assert provenance.primary_origin([low, high]) == high


def test_an_undeterminable_origin_is_unknown_and_never_a_plausible_default():
    assert provenance.origins_from_evidence([]) == []
    assert provenance.origins_from_evidence(None) == []
    assert provenance.primary_origin([]) == "unknown"
    assert provenance.primary_origin(None) == "unknown"
    # An origin outside the vocabulary is ignored rather than echoed back.
    assert provenance.primary_origin(["not_an_origin"]) == "unknown"
    assert provenance.note_origins("not_a_note_source") == []


def test_an_unnameable_channel_is_evidence_and_deliberately_not_unknown():
    """A citation exists; only its channel cannot be named. Two different facts."""
    assert provenance.origins_from_evidence([_ev("some_future_kind")]) == ["evidence"]
    assert provenance.origins_from_evidence([{"locator": "row 3"}]) == ["evidence"]
    # ...whereas nothing recorded at all really is unknown.
    entries = provenance.describe_experiment(_draft(**{"a.b": {"value": 1, "status": "verified"}}))[
        "entries"
    ]
    assert entries[0]["origins"] == ["unknown"]
    assert entries[0]["primary_origin"] == "unknown"


def test_unreadable_stored_evidence_contributes_no_invented_origin():
    entries = provenance.describe_experiment(_draft(**{"a.b": 7}))["entries"]
    assert [e["address"] for e in entries] == ["a.b"]
    assert entries[0]["origins"] == ["unknown"]
    assert entries[0]["evidence_count"] == 0
    # ...and it is the conservative review state, never `supported`.
    assert entries[0]["review_state"] == "needs_review"


# =============================================================================
# 3 — THE CONSTRAINT: origin must never imply support
# =============================================================================


def test_review_state_takes_no_origin_parameter():
    """The enforcement is structural: there is no parameter to pass one through.

    `unavailable` joined the signature when a partially unreadable payload was
    found reporting `supported`. It is a fact about whether the STORED PAYLOAD
    could be read, not about where the value came from, so the invariant this
    test guards is untouched — and the second assertion, which is the one that
    actually forbids origin, is deliberately kept rather than folded into the
    first. The exact-set assertion catches an argument being added; the substring
    assertion catches the specific argument that would break the model.
    """
    params = set(inspect.signature(provenance.review_state).parameters)
    assert params == {
        "status",
        "evidence_count",
        "classification",
        "note_state",
        "unavailable",
    }
    assert not {p for p in params if "origin" in p}


@pytest.mark.parametrize(
    "origin,evidence",
    [
        # NEGATIVE CONTROL 1 — `file`. Read out of a spreadsheet, and nobody has
        # confirmed it.
        ("file", [_ev("spreadsheet", source_file="sheet.csv", locator="B2")]),
        # NEGATIVE CONTROL 2 — `derived`. A documented rule proposed it; a rule is
        # a mechanism, not an acceptance.
        ("derived", [_ev("derivation", rule="edge follows from the absorbing element")]),
    ],
)
def test_a_file_or_derived_origin_can_carry_needs_review(origin, evidence):
    entries = provenance.describe_experiment(
        _draft(**{"a.b": {"value": "V", "status": "needs_confirmation", "evidence": evidence}})
    )["entries"]
    assert entries[0]["primary_origin"] == origin
    assert entries[0]["review_state"] == "needs_review"


def test_the_assistant_origin_can_carry_needs_review():
    """NEGATIVE CONTROL 3 — `assistant`, exercised at the only level it exists.

    Nothing in this build can produce an assistant-origin entry (see the
    unreachability test below), so the control is applied to the derivation
    itself: with the origin held at `assistant` and the review dimension given a
    status nothing establishes, the answer is `needs_review`. If a producer is
    ever added, the composed entry inherits this behaviour because the two
    derivations are separate functions.
    """
    assert provenance.primary_origin(["assistant"]) == "assistant"
    assert (
        provenance.review_state(status="needs_confirmation", evidence_count=1)
        == "needs_review"
    )
    assert provenance.review_state(status="inferred", evidence_count=3) == "needs_review"


def test_no_origin_alone_ever_produces_supported():
    """The exhaustive form of the three controls: every origin, no support."""
    for origin in provenance.ORIGINS:
        assert provenance.primary_origin([origin]) == origin
        # `review_state` cannot even see it, so the answer is the same every time.
        assert provenance.review_state(status="missing", evidence_count=0) == "needs_review"


def test_supported_requires_both_halves_and_a_verified_status_alone_is_not_enough():
    assert provenance.review_state(status="verified", evidence_count=1) == "supported"
    # A `verified` status with no citation is exactly the unsupported claim the
    # no-guessing rule exists to surface — it is NOT supported here.
    assert provenance.review_state(status="verified", evidence_count=0) == "needs_review"
    # And evidence without an established status is not support either.
    assert provenance.review_state(status="inferred", evidence_count=2) == "needs_review"
    assert (
        provenance.review_state(status="needs_confirmation", evidence_count=2)
        == "needs_review"
    )


def test_an_unrecognised_status_falls_to_the_conservative_state():
    for status in (None, "unavailable", "rejected", "missing", "wat"):
        assert provenance.review_state(status=status, evidence_count=5) == "needs_review"


# =============================================================================
# 4 — review state: conflict and unmapped come from the existing signals
# =============================================================================


def test_conflict_is_delegated_to_the_existing_classifier():
    """Two incompatible confirmed answers. The rule lives in the classifier."""
    from isaac_api import evidence_classify

    draft = _draft(
        **{
            "a.b": {
                "value": "one",
                "status": "verified",
                "evidence": [
                    _ev("user_confirmation", answer="one"),
                    _ev("user_confirmation", answer="two"),
                ],
            }
        }
    )
    # The classifier is what says `conflicting_evidence`...
    assert evidence_classify.classify_fields(draft)[0]["classification"] == (
        "conflicting_evidence"
    )
    # ...and this module reports `conflict` for exactly that, over a field whose
    # own status is `verified` — so conflict outranks support.
    entry = provenance.describe_experiment(draft)["entries"][0]
    assert entry["review_state"] == "conflict"
    assert entry["primary_origin"] == "manual"


def test_conflict_outranks_every_other_review_answer():
    assert (
        provenance.review_state(
            status="verified", evidence_count=2, classification="conflicting_evidence"
        )
        == "conflict"
    )
    assert (
        provenance.review_state(
            status="verified",
            evidence_count=2,
            classification="conflicting_evidence",
            note_state=notes_module.NOTE_UNREVIEWED,
        )
        == "conflict"
    )


def test_only_the_conflict_class_is_consumed_from_the_classifier():
    """The other five evidence-support classes are a DIFFERENT axis and are
    deliberately ignored — folding six into four would make one a lossy rename."""
    for other in (
        "supported",
        "inferred_candidate",
        "insufficient_evidence",
        "unknown",
        "unreadable",
    ):
        assert (
            provenance.review_state(status="verified", evidence_count=1, classification=other)
            == "supported"
        )


def test_an_unreviewed_note_is_unmapped_and_carries_no_evidence():
    note = notes_module.new_note(
        id="n1",
        experiment_id="x",
        text="the second scan was repeated",
        source="typed_note",
        captured_utc="2026-01-01T00:00:00Z",
    )
    result = provenance.describe_experiment({}, [note])
    assert [e["address"] for e in result["entries"]] == ["note:n1"]
    entry = result["entries"][0]
    assert entry["review_state"] == "unmapped"
    assert entry["primary_origin"] == "manual"
    assert entry["evidence_count"] == 0
    assert entry["note_refs"] == ["n1"]
    assert entry["inherited"] is False


def test_a_reviewed_note_is_not_listed_and_the_omission_is_counted():
    note = notes_module.new_note(
        id="n1",
        experiment_id="x",
        text="prose about the experiment",
        source="typed_note",
        captured_utc="2026-01-01T00:00:00Z",
    )
    kept = notes_module.keep_note(note, at="2026-01-02T00:00:00Z")
    result = provenance.describe_experiment({}, [kept])
    assert result["entries"] == []
    assert result["notes_summary"] == {"total": 1, "listed_as_unmapped": 0}


def test_a_mapped_note_becomes_a_reference_on_the_field_it_was_mapped_to():
    note = notes_module.new_note(
        id="n1",
        experiment_id="x",
        text="this belongs to the formula",
        source="typed_note",
        captured_utc="2026-01-01T00:00:00Z",
    )
    mapped = notes_module.map_note(
        note, field_path="sample.material.formula", at="2026-01-02T00:00:00Z"
    )
    result = provenance.describe_experiment(
        _draft(
            **{
                "sample.material.formula": {
                    "value": "CuO",
                    "status": "verified",
                    "evidence": [_ev("spreadsheet")],
                },
                "sample.material.name": {"value": "x", "status": "verified", "evidence": []},
            }
        ),
        [mapped],
    )
    by_address = {e["address"]: e for e in result["entries"]}
    assert by_address["sample.material.formula"]["note_refs"] == ["n1"]
    assert by_address["sample.material.name"]["note_refs"] == []
    # A mapped note is not itself an entry — it is not unmapped any more, and none
    # of the other three review states is true of it.
    assert "note:n1" not in by_address


def test_a_machine_candidate_path_is_not_treated_as_a_mapping():
    """A suggestion is not a decision — `notes` keeps the two apart, so do we."""
    note = notes_module.new_note(
        id="n1",
        experiment_id="x",
        text="Cu K edge",
        source="typed_note",
        captured_utc="2026-01-01T00:00:00Z",
        candidate_field_path="sample.material.formula",
        candidate_rule="the heading matched the formula column",
    )
    result = provenance.describe_experiment(
        _draft(
            **{
                "sample.material.formula": {
                    "value": "CuO",
                    "status": "verified",
                    "evidence": [_ev("spreadsheet")],
                }
            }
        ),
        [note],
    )
    by_address = {e["address"]: e for e in result["entries"]}
    assert by_address["sample.material.formula"]["note_refs"] == []
    # The note is still listed in its own right, because nobody has reviewed it.
    assert by_address["note:n1"]["review_state"] == "unmapped"


# =============================================================================
# 5 — the unreachable arms, stated precisely rather than conveniently
# =============================================================================


def test_nothing_in_this_build_can_produce_an_assistant_origin():
    """`assistant` is unreachable, and this is the mechanical proof.

    There is no `assistant` member in either closed vocabulary a mapping reads,
    so no evidence entry and no note can be read into it. The only remaining way
    in would be a hand-written mapping, which the two exhaustiveness tests above
    forbid.
    """
    assert "assistant" not in SOURCE_TYPES
    assert "assistant" not in notes_module.NOTE_SOURCES
    assert "assistant" not in provenance.SOURCE_TYPE_ORIGIN.values()
    assert "assistant" not in provenance.NOTE_SOURCE_ORIGIN.values()
    assert provenance.ORIGIN_ASSISTANT in provenance.ORIGINS


def test_the_assistant_origin_never_appears_over_the_committed_example_records(client):
    """The claim above, re-checked end to end over every worked example."""
    listing = client.get("/api/experiments").json()
    ids = [row["id"] for row in listing["experiments"]]
    assert ids, "no worked-example records to check"
    for experiment_id in ids:
        body = client.get(f"/api/experiments/{experiment_id}/provenance").json()
        for entry in body["entries"]:
            assert "assistant" not in entry["origins"], entry
            assert "voice" not in entry["origins"], entry


def test_the_voice_arm_has_no_producer_but_is_not_unreachable_over_the_api(client):
    """PRECISION, because the two easy summaries are both wrong.

    Nothing in this build TRANSCRIBES anything — there is no recorder, no
    transcription provider, and the notes panel hard-codes `typed_note`. But
    `POST .../notes` validates `source` against the whole note vocabulary, so a
    direct API caller CAN store a transcript note today, and this module reports
    `voice` for it. "No producer exists" is true of the application; "the arm is
    unreachable" is false at the API boundary, and a test that asserted the
    stronger claim would be asserting something the route disproves.
    """
    assert "transcript" in notes_module.NOTE_SOURCES

    experiment_id = client.get("/api/experiments").json()["experiments"][0]["id"]
    version = client.get(f"/api/experiments/{experiment_id}").json()["version"]
    created = client.post(
        f"/api/experiments/{experiment_id}/notes",
        headers={"If-Match": f'"{version}"'},
        json={"text": "spoken aside about the second scan", "source": "transcript"},
    )
    assert created.status_code == 201, created.text

    body = client.get(f"/api/experiments/{experiment_id}/provenance").json()
    voice = [e for e in body["entries"] if "voice" in e["origins"]]
    assert len(voice) == 1
    assert voice[0]["primary_origin"] == "voice"
    assert voice[0]["review_state"] == "unmapped"


# =============================================================================
# 6 — runs: inheritance is an origin, and it is not support either
# =============================================================================


def _record_with_a_run(client):
    experiment_id = client.get("/api/experiments").json()["experiments"][0]["id"]
    version = client.get(f"/api/experiments/{experiment_id}").json()["version"]
    created = client.post(
        f"/api/experiments/{experiment_id}/runs",
        headers={"If-Match": f'"{version}"'},
        json={"label": "Run A"},
    )
    assert created.status_code == 201, created.text
    return experiment_id, created.json()["run"]["id"]


def test_a_run_reports_inherited_addresses_with_the_inherited_origin(client):
    experiment_id, run_id = _record_with_a_run(client)
    body = client.get(f"/api/experiments/{experiment_id}/provenance?run={run_id}").json()
    assert body["run_id"] == run_id

    inherited = [e for e in body["entries"] if e["inherited"]]
    assert inherited, "the run inherits nothing, so nothing is being tested"
    for entry in inherited:
        assert "inherited" in entry["origins"]
        # The inherited value's OWN origin travels with it — inheritance says whose
        # value it is, not how it was produced — and `inherited` leads.
        assert entry["primary_origin"] == "inherited"
        assert set(entry["origins"]) <= set(provenance.ORIGINS)


def test_the_record_level_view_never_claims_anything_is_inherited(client):
    experiment_id, _run_id = _record_with_a_run(client)
    body = client.get(f"/api/experiments/{experiment_id}/provenance").json()
    assert body["run_id"] is None
    assert all(e["inherited"] is False for e in body["entries"])
    assert all("inherited" not in e["origins"] for e in body["entries"])


def test_inheritance_does_not_make_a_value_supported():
    """An inherited envelope that nothing establishes stays `needs_review`."""

    class _Res:
        provenance = ws.PROVENANCE_INHERITED
        payload = {"value": "V", "status": "needs_confirmation", "evidence": []}

    result = provenance.describe_run({}, {"field:sample.material.name": _Res()})
    entry = result["entries"][0]
    assert entry["address"] == "sample.material.name"
    assert entry["origins"] == ["inherited"]
    assert entry["primary_origin"] == "inherited"
    assert entry["review_state"] == "needs_review"
    assert entry["inherited"] is True


def test_an_overridden_address_is_the_runs_own_value_and_not_inherited():
    class _Res:
        provenance = ws.PROVENANCE_OVERRIDDEN
        payload = {
            "value": "V",
            "status": "verified",
            "evidence": [{"source_type": "user_confirmation", "answer": "V"}],
        }

    result = provenance.describe_run({}, {"field:sample.material.name": _Res()})
    entry = result["entries"][0]
    assert entry["inherited"] is False
    assert entry["origins"] == ["manual"]
    assert entry["review_state"] == "supported"


def test_block_addresses_are_not_described_and_the_omission_is_named():
    """A block carries no envelope, so neither dimension can be derived for it."""

    class _Res:
        provenance = ws.PROVENANCE_INHERITED
        payload = ["tag-a", "tag-b"]

    result = provenance.describe_run({}, {"block:tags": _Res()})
    assert result["entries"] == []
    assert result["blocks_not_described"] == ["block:tags"]


# =============================================================================
# 7 — the route
# =============================================================================


def test_the_route_returns_typed_entries_for_a_record(client):
    experiment_id = client.get("/api/experiments").json()["experiments"][0]["id"]
    r = client.get(f"/api/experiments/{experiment_id}/provenance")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "experiment_id",
        "run_id",
        "record_rev",
        "entries",
        "notes_summary",
        "blocks_not_described",
    }
    assert body["experiment_id"] == experiment_id
    assert isinstance(body["record_rev"], int)
    assert body["entries"], "the worked example has no described addresses"
    for entry in body["entries"]:
        assert set(entry) == ENTRY_KEYS, entry
        assert entry["origins"], "origins is never empty — `unknown` is a real answer"
        assert set(entry["origins"]) <= set(provenance.ORIGINS)
        assert entry["primary_origin"] in entry["origins"]
        assert entry["review_state"] in provenance.REVIEW_STATES
        assert isinstance(entry["inherited"], bool)
        assert isinstance(entry["note_refs"], list)


def test_the_route_carries_no_validity_or_export_verdict(client):
    experiment_id = client.get("/api/experiments").json()["experiments"][0]["id"]
    body = client.get(f"/api/experiments/{experiment_id}/provenance").json()
    forbidden = {"valid", "ok", "exportable", "complete", "blocking", "warnings", "errors"}
    assert not (forbidden & set(body))
    for entry in body["entries"]:
        assert not (forbidden & set(entry))


def test_the_route_sets_the_records_etag_and_mutates_nothing(client):
    experiment_id = client.get("/api/experiments").json()["experiments"][0]["id"]
    before = client.get(f"/api/experiments/{experiment_id}").json()["version"]
    r = client.get(f"/api/experiments/{experiment_id}/provenance")
    assert r.headers["ETag"] == f'"{before}"'
    client.get(f"/api/experiments/{experiment_id}/provenance?run=nope")
    after = client.get(f"/api/experiments/{experiment_id}").json()["version"]
    assert after == before


def test_the_route_is_deterministic(client):
    experiment_id = client.get("/api/experiments").json()["experiments"][0]["id"]
    first = client.get(f"/api/experiments/{experiment_id}/provenance").json()
    second = client.get(f"/api/experiments/{experiment_id}/provenance").json()
    assert first == second


def test_an_unknown_experiment_is_a_typed_404(client):
    r = client.get("/api/experiments/no-such-record/provenance")
    assert r.status_code == 404
    assert r.json() == {"error": "experiment_not_found", "id": "no-such-record"}


def test_an_unknown_run_is_a_typed_404_and_never_the_record_answer(client):
    experiment_id = client.get("/api/experiments").json()["experiments"][0]["id"]
    r = client.get(f"/api/experiments/{experiment_id}/provenance?run=no-such-run")
    assert r.status_code == 404
    assert r.json() == {
        "error": "run_not_found",
        "experiment_id": experiment_id,
        "id": "no-such-run",
    }


def test_the_worked_example_scope_is_honoured(tmp_path, monkeypatch):
    """Without the session header the record is not in the ordinary workspace."""
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    app = create_app()
    scoped = tutorial_client(app)
    experiment_id = scoped.get("/api/experiments").json()["experiments"][0]["id"]
    assert scoped.get(f"/api/experiments/{experiment_id}/provenance").status_code == 200

    unscoped = TestClient(app)
    r = unscoped.get(f"/api/experiments/{experiment_id}/provenance")
    assert r.status_code == 404
    assert r.json()["error"] == "experiment_not_found"


def test_an_unknown_worked_example_session_is_refused_not_answered(client):
    experiment_id = client.get("/api/experiments").json()["experiments"][0]["id"]
    from isaac_api.routes import TUTORIAL_SESSION_HEADER

    unknown = "Zz" + "0" * 20
    assert ws.is_tutorial_session_id(unknown)
    r = TestClient(client.app).get(
        f"/api/experiments/{experiment_id}/provenance",
        headers={TUTORIAL_SESSION_HEADER: unknown},
    )
    assert r.status_code == 404
    assert r.json()["error"] == "tutorial_session_not_found"


# =============================================================================
# 8 — this module is not truth-path, and its imports are pinned
# =============================================================================

#: The ONLY thing this module may take from the truth core: a vocabulary tuple.
#: Everything else — validation, export, the audit, the CLI, the schema — is a
#: decision the truth core makes and this view must never re-make.
_ALLOWED_CORE_IMPORTS = {("isaac_records.models", "SOURCE_TYPES")}


def _core_imports() -> set[tuple[str, str]]:
    tree = ast.parse(MODULE_PATH.read_text())
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("isaac_records"):
            for alias in node.names:
                found.add((node.module, alias.name))
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("isaac_records"):
                    found.add((alias.name, "*"))
    return found


def test_the_module_takes_only_a_vocabulary_from_the_truth_core():
    assert _core_imports() == _ALLOWED_CORE_IMPORTS


def test_the_import_scan_can_actually_fail():
    """Guards the guard: the scan really does see an isaac_records import."""
    assert _core_imports(), "the scan found nothing, so it proves nothing"


def test_no_truth_path_module_is_imported_by_name():
    source = MODULE_PATH.read_text()
    tree = ast.parse(source)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    for forbidden in (
        "isaac_records.official",
        "isaac_records.draft_validator",
        "isaac_records.export",
        "isaac_records.audit",
        "isaac_records.cli",
        "isaac_records.exactness",
    ):
        assert forbidden not in imported, forbidden


def test_the_module_is_graphify_free():
    """No graph/memory-plane import or call. The word itself appears in the
    module's own prose saying so, which is why this checks the IMPORTS."""
    tree = ast.parse(MODULE_PATH.read_text())
    names = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not [n for n in names if "graph" in n.lower()], names
    assert "graphify" not in {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_nothing_here_writes_anything():
    """A read-only view: no persistence verb appears in the module at all."""
    source = MODULE_PATH.read_text()
    for verb in ("save(", "write_text(", "atomic_write", "record_lock(", "open("):
        assert verb not in source, verb


def test_the_derivations_do_not_mutate_their_input():
    draft = _draft(
        **{
            "a.b": {
                "value": "V",
                "status": "verified",
                "evidence": [_ev("spreadsheet", source_file="s.csv")],
            }
        }
    )
    import copy

    before = copy.deepcopy(draft)
    provenance.describe_experiment(draft)
    assert draft == before


# =============================================================================
# REGRESSIONS FROM INDEPENDENT REVIEW — two CRITICALs, each with the exact shape
# that made it invisible to the suite that shipped it.
# =============================================================================


def test_a_partially_unreadable_payload_is_never_supported():
    """CRITICAL. `verified` + one readable citation + one unreadable one.

    `serialize._trail_entry` passes a draft field's stored `status` through
    verbatim and sets `unavailable` when only PART of the payload could be read.
    Its docstring says the pass-through "is defensible only BECAUSE
    `unavailable`/`unavailable_reason` travel with it. Nothing here may present
    that status as fully justified support."

    `provenance` did not read `unavailable`, and `ENTRY_KEYS` had no slot to
    carry it — so the entry reported `supported`, and the panel painted a green
    Supported chip beneath a row it had already marked unavailable. Of the three
    surfaces reading this data, provenance was the only one that lost the
    disclosure.

    MUTATION: delete the `if unavailable:` arm in `review_state` and this goes RED.
    """
    draft = {
        "fields": {
            "sample.material.formula": {
                "value": "CuO",
                "status": "verified",
                # One readable entry and one that is not an evidence object.
                "evidence": [_ev("spreadsheet", source_file="x.xlsx", locator="B2"), 7],
            }
        }
    }
    described = provenance.describe_experiment(draft)
    entry = next(e for e in described["entries"] if e["address"] == "sample.material.formula")

    assert entry["unavailable"] is True, "the disclosure must reach the wire"
    assert entry["review_state"] == provenance.REVIEW_NEEDS_REVIEW, (
        "a payload this build could only partly read must never read as supported"
    )
    # And the control: the SAME field with every entry readable IS supported, so
    # the assertion above is not passing for an unrelated reason.
    draft["fields"]["sample.material.formula"]["evidence"] = [
        _ev("spreadsheet", source_file="x.xlsx", locator="B2")
    ]
    clean = provenance.describe_experiment(draft)
    clean_entry = next(
        e for e in clean["entries"] if e["address"] == "sample.material.formula"
    )
    assert clean_entry["unavailable"] is False
    assert clean_entry["review_state"] == provenance.REVIEW_SUPPORTED


def test_the_record_path_names_its_own_undescribed_blocks():
    """CRITICAL. `blocks_not_described` was ALWAYS `[]` on the record path.

    It was populated only from `resolutions`, and `describe_experiment` passes
    `{}` — so the default call every client makes first reported that nothing had
    been omitted, while `attribution`, `qc`, `series` and the rest were as
    undescribed as they are for a run. Asking for the same record's RUN would
    name `block:attribution`; the record-level answer was the less honest of the
    two, in the one field whose entire purpose is to prevent that.

    MUTATION: seed `blocks_not_described` as `[]` again and this goes RED.
    """
    draft = {
        "fields": {"sample.material.formula": {"value": "CuO", "status": "verified", "evidence": []}},
        "attribution": {"uploaded_by": None},
        "qc": {"status": "pass"},
        "series": [],
        "block_evidence": {},
    }
    described = provenance.describe_experiment(draft)

    assert described["blocks_not_described"] == [
        ws.block_address("attribution"),
        ws.block_address("block_evidence"),
        ws.block_address("qc"),
        ws.block_address("series"),
    ]
    # `fields` is DESCRIBED, so it must not appear; naming it would overstate the
    # gap as badly as the empty list understated it.
    assert ws.block_address("fields") not in described["blocks_not_described"]


def test_the_described_keys_match_what_the_trail_reader_actually_walks():
    """`_DESCRIBED_DRAFT_KEYS` mirrors `serialize.evidence_trail_from_draft`.

    If that reader learns to walk a fourth key, this module would start naming it
    as undescribed — reporting a gap that is not there. Pinned against the
    reader's own source so the two cannot drift silently.
    """
    from isaac_api import serialize

    source = inspect.getsource(serialize.evidence_trail_from_draft)
    for key in provenance._DESCRIBED_DRAFT_KEYS:
        assert f'"{key}"' in source, f"{key} is claimed as described but the reader never names it"
    # And the guard-the-guard: the set is not empty, so the loop above is not vacuous.
    assert provenance._DESCRIBED_DRAFT_KEYS == {"fields", "implicit", "assets"}


def test_a_run_scoped_note_is_not_attributed_to_the_record(tmp_path, monkeypatch):
    """IMPORTANT. The record view used to claim every note, including run ones.

    The RUN branch narrows notes to `n.run_id == run` and explains why: attaching
    a record-level note to whichever run is on screen "would be exactly the
    invention `notes` refuses". The RECORD branch passed `exp.sorted_notes()` —
    every note — and `_note_refs_by_path` keys purely on `mapped_field_path` and
    never looks at `run_id`.

    So a note captured against a run, mapped to a field path the record also
    carries, appeared in the RECORD's `note_refs` with no run marker and was
    counted in `notes_summary` as an unmapped entry of the record. The same
    invention, in the opposite direction.

    MUTATION: pass `exp.sorted_notes()` on the record branch again and the first
    assertion goes RED.

    Uses a PLAIN client, not the module's `client` fixture: that one is a
    worked-example session, and creating an experiment inside a session is a 409
    by design.
    """
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    client = TestClient(create_app())

    created = client.post("/api/experiments", json={"title": "note scoping"})
    assert created.status_code in (200, 201), created.text
    experiment_id = created.json()["id"]

    runs = client.post(
        f"/api/experiments/{experiment_id}/runs",
        json={"label": "300 K", "confirmed_by_user": True},
        headers={"If-Match": client.get(f"/api/experiments/{experiment_id}").headers["ETag"]},
    )
    assert runs.status_code in (200, 201), runs.text
    run_id = runs.json()["run"]["id"]

    # One note captured against the RUN.
    noted = client.post(
        f"/api/experiments/{experiment_id}/notes",
        json={"text": "Ran hotter than planned.", "source": "typed_note", "run_id": run_id},
        headers={"If-Match": client.get(f"/api/experiments/{experiment_id}").headers["ETag"]},
    )
    assert noted.status_code in (200, 201), noted.text

    record_view = client.get(f"/api/experiments/{experiment_id}/provenance")
    assert record_view.status_code == 200, record_view.text
    assert record_view.json()["notes_summary"] == {"total": 0, "listed_as_unmapped": 0}, (
        "a note captured against a run is not a note about the record"
    )

    # …and the run view DOES carry it, so the assertion above is not passing
    # because the note simply vanished.
    run_view = client.get(f"/api/experiments/{experiment_id}/provenance?run={run_id}")
    assert run_view.status_code == 200, run_view.text
    assert run_view.json()["notes_summary"]["listed_as_unmapped"] == 1

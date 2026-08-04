"""P34.1 — the READ-ONLY deterministic assistant-query resolver + endpoint.

Two layers are covered:

* ``classify()`` — a PURE, context-free classifier over a finite intent catalog.
  Aliases map to intents, genuine ties are ``ambiguous``, open-world questions are
  ``unsupported``, and the same input is byte-identical across runs.
* ``POST /experiments/{id}/assistant/query`` — assembles read-only grounding and
  returns a verdict-guarded, leak-safe, deterministic answer. The record is NEVER
  mutated (rev/version unchanged is the proof), no answer states a PASS/FAIL or
  valid/invalid conclusion, and no absolute path / secret / bearer / long hex ever
  appears in an answer or source label.

All fixtures are synthetic; the truth/export path is untouched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api import assistant_query as aq

from conftest import bind_tutorial_session, tutorial_client

# --- classify() unit tests (pure; no workspace) -------------------------------

# question -> expected intent (one representative alias per family, plus more).
INTENT_CASES = [
    # pending_fields
    ("What still needs me?", aq.PENDING_FIELDS),
    ("what needs attention", aq.PENDING_FIELDS),
    ("what's missing", aq.PENDING_FIELDS),
    ("show me the pending fields", aq.PENDING_FIELDS),
    ("what should I review next", aq.PENDING_FIELDS),
    # export_blockers (precedence over readiness on a blocker/negation cue)
    ("why can't I export?", aq.EXPORT_BLOCKERS),
    ("what's blocking export", aq.EXPORT_BLOCKERS),
    ("what's left before export", aq.EXPORT_BLOCKERS),
    # export_readiness
    ("is this ready to export?", aq.EXPORT_READINESS),
    ("export readiness", aq.EXPORT_READINESS),
    ("am I done", aq.EXPORT_READINESS),
    # workflow_step
    ("what is the current step", aq.WORKFLOW_STEP),
    ("explain the workflow", aq.WORKFLOW_STEP),
    ("where am I", aq.WORKFLOW_STEP),
    # field_provenance
    ("where did the formula come from", aq.FIELD_PROVENANCE),
    ("trace the edge to its source", aq.FIELD_PROVENANCE),
    ("provenance of the formula", aq.FIELD_PROVENANCE),
    # evidence_summary
    ("summarize the evidence for the formula", aq.EVIDENCE_SUMMARY),
    ("what's the evidence for the edge", aq.EVIDENCE_SUMMARY),
    ("why multiple evidence entries", aq.EVIDENCE_SUMMARY),
    # record_summary
    ("summarize this record", aq.RECORD_SUMMARY),
    ("what is this record", aq.RECORD_SUMMARY),
    ("record status overview", aq.RECORD_SUMMARY),
    # memory_lead
    ("what does project memory know about copper", aq.MEMORY_LEAD),
    ("docs about xanes", aq.MEMORY_LEAD),
    ("where is the edge concept defined", aq.MEMORY_LEAD),
]


@pytest.mark.parametrize("question,expected", INTENT_CASES)
def test_classify_maps_aliases_to_intents(question, expected):
    assert aq.classify(question).intent == expected


OPEN_WORLD = [
    "what is the oxidation state of iron",
    "what's the weather",
    "who won the game last night",
    "translate this to french",
]


@pytest.mark.parametrize("question", OPEN_WORLD)
def test_open_world_questions_are_unsupported_never_guessed(question):
    c = aq.classify(question)
    assert c.intent == aq.UNSUPPORTED
    assert c.confidence == "none"


def test_empty_question_is_unsupported():
    assert aq.classify("   ").intent == aq.UNSUPPORTED


def test_ambiguous_tie_between_distinct_intents():
    # "current step" (workflow_step) + "what's missing" (pending_fields) tie 1:1.
    c = aq.classify("what's the current step and what's missing")
    assert c.intent == aq.AMBIGUOUS
    assert set(c.alternatives) == {aq.WORKFLOW_STEP, aq.PENDING_FIELDS}


def test_export_blocker_cue_outranks_readiness():
    # A blocker/negation-cued export question is export_blockers, not readiness.
    assert aq.classify("what's left before I can export").intent == aq.EXPORT_BLOCKERS


def test_field_extraction_present_and_absent():
    with_field = aq.classify("where did the formula come from")
    assert with_field.extracted.get("field") == "formula"
    assert with_field.confidence == "high"
    # No identifiable field -> intent still provenance, but low confidence, no guess.
    no_field = aq.classify("where did it come from")
    assert no_field.intent == aq.FIELD_PROVENANCE
    assert "field" not in no_field.extracted
    assert no_field.confidence == "low"


def test_memory_topic_extraction():
    c = aq.classify("what does project memory know about copper oxide")
    assert c.intent == aq.MEMORY_LEAD
    assert c.extracted.get("topic") == "copper oxide"


def test_classify_is_deterministic():
    for q in ["What still needs me?", "why can't I export", "summarize this record",
              "what is the oxidation state of iron", "where did the formula come from"]:
        first = aq.classify(q)
        second = aq.classify(q)
        assert first == second  # frozen dataclass equality


# --- endpoint tests -----------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    return tutorial_client(create_app())


def _query(client, exp_id, question, **body):
    return client.post(f"/api/experiments/{exp_id}/assistant/query",
                       json={"question": question, **body})


def _no_leak(text: str) -> None:
    assert "/Users/" not in text
    assert "\\Users\\" not in text
    assert "Bearer " not in text
    # No 32+ char hex token.
    import re
    assert not re.search(r"\b[0-9a-f]{32,}\b", text, re.I), text


def test_pending_fields_answered_with_grounding(client):
    r = _query(client, ws.SEED_NEW_DRAFT_ID, "what still needs me?")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "answered"
    assert body["grounding"] == ["workflow"]
    assert isinstance(body["record_rev"], int)
    assert body["version"] and "." in body["version"]
    assert aq.has_verdict_language(body["answer"]) is False
    _no_leak(body["answer"])


def test_export_blockers_answered_from_schema(client):
    r = _query(client, ws.SEED_NEW_DRAFT_ID, "why can't I export?")
    body = r.json()
    assert body["result"] == "answered"
    assert body["grounding"] == ["schema"]
    assert aq.has_verdict_language(body["answer"]) is False


def test_workflow_and_record_summary_answered(client):
    for q in ("what is the current step", "summarize this record"):
        body = _query(client, ws.SEED_READY_ID, q).json()
        assert body["result"] == "answered"
        assert aq.has_verdict_language(body["answer"]) is False
        _no_leak(body["answer"])


def test_field_provenance_answered_for_a_real_field(client):
    # Pick a real evidenced field from the ready record's evidence trail.
    trail = client.get(f"/api/experiments/{ws.SEED_READY_ID}/evidence").json()["evidence"]
    entry = next(e for e in trail if e.get("evidence"))
    token = entry["path"].split(".")[-1].split(":")[-1].replace("_", " ")
    body = _query(client, ws.SEED_READY_ID, f"where did the {token} come from").json()
    assert body["result"] == "answered"
    assert body["grounding"] == ["files"]
    _no_leak(body["answer"])


def test_field_provenance_without_a_field_is_honest(client):
    body = _query(client, ws.SEED_READY_ID, "where did it come from").json()
    assert body["result"] == "insufficient_context"
    # Honest: it asks which field / lists traceable fields, never guesses one.
    assert "which field" in body["answer"].lower() or "traceable" in body["answer"].lower()
    _no_leak(body["answer"])


def test_unsupported_open_world_question(client):
    body = _query(client, ws.SEED_READY_ID, "what is the oxidation state of iron").json()
    assert body["result"] == "unsupported"
    # Names the supported families and suggests a supported question.
    assert "pending" in body["answer"] and "still" in body["answer"].lower()


def test_ambiguous_question_result(client):
    body = _query(client, ws.SEED_READY_ID,
                  "what's the current step and what's missing").json()
    assert body["result"] == "ambiguous"
    _no_leak(body["answer"])


def test_empty_question_is_400(client):
    r = _query(client, ws.SEED_READY_ID, "   ")
    assert r.status_code == 400
    assert r.json()["error"] == "empty_question"


def test_oversized_question_is_400(client):
    r = _query(client, ws.SEED_READY_ID, "x" * 501)
    assert r.status_code == 400
    assert r.json()["error"] == "question_too_long"


def test_missing_record_is_404(client):
    r = _query(client, "01MISSINGRECORD00000000000", "what still needs me?")
    assert r.status_code == 404
    assert r.json()["error"] == "experiment_not_found"


def test_stale_flag_when_grounded_rev_differs(client):
    fresh = _query(client, ws.SEED_READY_ID, "summarize this record").json()
    assert fresh["stale"] is False  # no grounded_rev supplied
    stale = _query(client, ws.SEED_READY_ID, "summarize this record",
                   grounded_rev="0.999").json()
    assert stale["stale"] is True


def test_history_is_ignored_and_bounded(client):
    # A large history payload is accepted (presentation-only) and never errors.
    r = _query(client, ws.SEED_READY_ID, "what still needs me?",
               history=[{"role": "user", "text": f"msg {i}"} for i in range(50)])
    assert r.status_code == 200
    assert r.json()["result"] == "answered"


# --- safety: read-only, determinism, no verdict, no leak ----------------------


def test_query_never_mutates_the_record(client):
    before = client.get(f"/api/experiments/{ws.SEED_READY_ID}").json()
    for q in ("what still needs me?", "why can't I export?", "summarize this record",
              "where did the formula come from", "what is the current step"):
        _query(client, ws.SEED_READY_ID, q)
    after = client.get(f"/api/experiments/{ws.SEED_READY_ID}").json()
    # rev + version unchanged is the proof no answers/edit/export side effect ran.
    assert after["rev"] == before["rev"]
    assert after["version"] == before["version"]


def test_endpoint_is_deterministic(client):
    first = _query(client, ws.SEED_READY_ID, "what still needs me?").json()
    second = _query(client, ws.SEED_READY_ID, "what still needs me?").json()
    assert first == second


def test_same_normalized_question_is_repeatable(client):
    # Surrounding punctuation/whitespace/casing normalize to the same answer.
    a = _query(client, ws.SEED_READY_ID, "What still needs me?").json()
    b = _query(client, ws.SEED_READY_ID, "  what   STILL needs me  ").json()
    assert a["answer"] == b["answer"]
    assert a["result"] == b["result"]


def test_no_verdict_language_in_any_answer(client):
    questions = [q for q, _ in INTENT_CASES] + OPEN_WORLD + [
        "what's the current step and what's missing",  # ambiguous
    ]
    for q in questions:
        body = _query(client, ws.SEED_READY_ID, q).json()
        assert aq.has_verdict_language(body["answer"]) is False, (q, body["answer"])
        _no_leak(body["answer"])
        for src in body["sources"]:
            _no_leak(src["label"])
            nav = src["navigate_to"]
            assert nav is None or nav.startswith(("/record", "/memory")), nav


# --- memory_lead against a synthetic available graph --------------------------


def _write_synthetic_graph(repo_root: Path) -> Path:
    art = repo_root / "graphify-out"
    art.mkdir(parents=True, exist_ok=True)
    graph = {
        "nodes": [
            {"id": "concept_copper", "label": "Copper oxide", "file_type": "concept",
             "community": 7, "source_file": "docs/fake-note.md"},
            {"id": "docs_fake", "label": "fake-note.md", "file_type": "document",
             "community": 7, "source_file": "docs/fake-note.md"},
        ],
        "links": [],
        "built_at_commit": "fakecommit0000",
    }
    manifest = {"docs/fake-note.md": {"mtime": 1.0, "ast_hash": "fake", "semantic_hash": ""}}
    labels = {"7": "Copper community"}
    (art / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (art / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (art / ".graphify_labels.json").write_text(json.dumps(labels), encoding="utf-8")
    return art


def test_memory_lead_returns_cited_leads_with_advisory_framing(tmp_path, monkeypatch):
    art = _write_synthetic_graph(tmp_path)
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(art))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    c = tutorial_client(create_app())
    body = _query(c, ws.SEED_READY_ID, "what does project memory know about copper").json()
    assert body["result"] == "answered"
    assert body["grounding"] == ["graph"]
    # Advisory framing, never a verdict; distinguishes memory leads from record truth.
    assert "leads to verify" in body["answer"]
    assert "Memory suggests" in body["answer"]
    assert aq.has_verdict_language(body["answer"]) is False
    assert body["sources"], "cited leads expected"
    for src in body["sources"]:
        _no_leak(src["label"])
        nav = src["navigate_to"]
        assert nav is None or nav.startswith(("/record", "/memory"))


# --- D1: a cited source LABEL is verdict-guarded, not only path/secret-scrubbed --
#
# A project-memory lead whose LABEL contains reserved verdict language (e.g. a doc
# titled "Records valid against v1.05") must be dropped from `sources` — otherwise
# the citation chip would surface the phrase and bypass the guard that neutralizes
# the answer body. `_scrub_sources` now drops such a label on BOTH endpoints.


def _verdict_search(_topic):
    # A synthetic memory reader whose leads carry reserved verdict language in their
    # labels (one PASS/FAIL token, one "valid against"), plus one safe label.
    return {
        "available": True,
        "results": [
            {"label": "Records valid against v1.05", "navigate_to": "/memory/doc1"},
            {"label": "QC gate marked PASS", "navigate_to": "/memory/doc2"},
            {"label": "Copper oxide note", "navigate_to": "/memory/doc3"},
        ],
    }


def _memory_context() -> aq.AssistantContext:
    return aq.AssistantContext(
        record_summary={}, pending={"pending": []}, evidence_trail=[],
        workflow={}, record_rev=1, version_token="p34.1", navigate_base="/record/x",
        search=_verdict_search,
    )


def test_verdict_language_source_label_is_dropped_record_scope():
    classified = aq.classify("what does project memory know about copper")
    body = aq.answer(classified, _memory_context(), grounded_rev=None)
    labels = [s["label"] for s in body["sources"]]
    assert "Records valid against v1.05" not in labels
    assert "QC gate marked PASS" not in labels
    assert "Copper oxide note" in labels  # the safe lead survives
    for label in labels:
        assert aq.has_verdict_language(label) is False, label


def test_verdict_language_source_label_is_dropped_memory_scope():
    classified = aq.classify("what does project memory know about copper")
    body = aq.answer_memory_scope(classified, _verdict_search)
    labels = [s["label"] for s in body["sources"]]
    assert "Records valid against v1.05" not in labels
    assert "QC gate marked PASS" not in labels
    assert "Copper oxide note" in labels
    for label in labels:
        assert aq.has_verdict_language(label) is False, label


# --- auth ---------------------------------------------------------------------


def test_requires_auth_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    from isaac_api.app import create_app

    # The session is opened in-process rather than over HTTP: this deployment
    # requires the key, and pinning it as a client default would destroy the 401
    # this test asserts. Same scope either way.
    c = bind_tutorial_session(TestClient(create_app()))
    r = c.post(f"/api/experiments/{ws.SEED_READY_ID}/assistant/query",
               json={"question": "what still needs me?"})
    assert r.status_code == 401


# --- P34.4: record-agnostic memory-scope endpoint -----------------------------
#
# The Project Memory surface has NO record, so it uses POST /api/assistant/memory/query
# (no experiment path param). A project-memory question is answered from the memory
# reader (cited leads + advisory framing, never a verdict); ANY other question is an
# honest refusal directing the user to open a record — never a fabricated record
# answer. It loads/creates NO record: record_rev/version are null and stale is False.


def _mem_query(client, question, **body):
    return client.post("/api/assistant/memory/query", json={"question": question, **body})


def test_memory_scope_answers_memory_question_with_cited_leads(tmp_path, monkeypatch):
    art = _write_synthetic_graph(tmp_path)
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_MEMORY_DIR", str(art))
    monkeypatch.delenv("ISAAC_UI_API_KEY", raising=False)
    from isaac_api.app import create_app

    c = tutorial_client(create_app())
    r = _mem_query(c, "what does project memory know about copper")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "answered"
    assert body["grounding"] == ["graph"]
    # Advisory "leads to verify" framing, never a verdict.
    assert "leads to verify" in body["answer"]
    assert "Memory suggests" in body["answer"]
    assert aq.has_verdict_language(body["answer"]) is False
    assert body["sources"], "cited leads expected"
    for src in body["sources"]:
        _no_leak(src["label"])
        nav = src["navigate_to"]
        assert nav is None or nav.startswith(("/record", "/memory"))
    # No record on this surface.
    assert body["record_rev"] is None
    assert body["version"] is None
    assert body["stale"] is False


def test_memory_scope_refuses_record_question_and_directs_to_a_record(client):
    # A record-style question ("what still needs me") is NOT answered as a record
    # here — it is an honest refusal pointing the user at a record.
    body = _mem_query(client, "what still needs me?").json()
    assert body["result"] == "unsupported"
    assert "Project Memory view" in body["answer"]
    assert "Open a record" in body["answer"]
    assert body["grounding"] == []
    assert body["sources"] == []
    assert body["record_rev"] is None
    assert body["version"] is None
    assert body["stale"] is False
    assert aq.has_verdict_language(body["answer"]) is False
    _no_leak(body["answer"])


@pytest.mark.parametrize("q", [
    "why can't I export?",           # export_blockers (record intent)
    "summarize this record",          # record_summary (record intent)
    "where did the formula come from",  # field_provenance (record intent)
    "what is the oxidation state of iron",  # unsupported open-world
    "what's the current step and what's missing",  # ambiguous
])
def test_memory_scope_refuses_every_non_memory_intent(client, q):
    body = _mem_query(client, q).json()
    assert body["result"] == "unsupported"
    assert "Open a record" in body["answer"]
    assert aq.has_verdict_language(body["answer"]) is False
    _no_leak(body["answer"])


def test_memory_scope_empty_question_is_400(client):
    r = _mem_query(client, "   ")
    assert r.status_code == 400
    assert r.json()["error"] == "empty_question"


def test_memory_scope_oversized_question_is_400(client):
    r = _mem_query(client, "x" * 501)
    assert r.status_code == 400
    assert r.json()["error"] == "question_too_long"


def test_memory_scope_history_is_accepted_and_bounded(client):
    r = _mem_query(client, "docs about xanes",
                   history=[{"role": "user", "text": f"m {i}"} for i in range(50)])
    assert r.status_code == 200


def test_memory_scope_is_deterministic(client):
    first = _mem_query(client, "what still needs me?").json()
    second = _mem_query(client, "what still needs me?").json()
    assert first == second


def test_memory_scope_creates_no_experiment(client):
    # The memory endpoint never loads/creates a record: the workspace record count
    # is unchanged after a batch of memory-scope queries.
    before = client.get("/api/experiments").json()["experiments"]
    for q in ("docs about xanes", "what still needs me?", "why can't I export?"):
        _mem_query(client, q)
    after = client.get("/api/experiments").json()["experiments"]
    assert [e["id"] for e in after] == [e["id"] for e in before]


def test_memory_scope_no_leak_in_any_answer_or_label(client):
    questions = [q for q, _ in INTENT_CASES] + OPEN_WORLD
    for q in questions:
        body = _mem_query(client, q).json()
        assert aq.has_verdict_language(body["answer"]) is False, (q, body["answer"])
        _no_leak(body["answer"])
        for src in body["sources"]:
            _no_leak(src["label"])
            nav = src["navigate_to"]
            assert nav is None or nav.startswith(("/record", "/memory")), nav


def test_memory_scope_requires_auth_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ISAAC_UI_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("ISAAC_UI_API_KEY", "demo-secret")
    from isaac_api.app import create_app

    # The session is opened in-process rather than over HTTP: this deployment
    # requires the key, and pinning it as a client default would destroy the 401
    # this test asserts. Same scope either way.
    c = bind_tutorial_session(TestClient(create_app()))
    r = c.post("/api/assistant/memory/query", json={"question": "docs about xanes"})
    assert r.status_code == 401


# --- P36V.1 Unit B: the humanized blocker copy + the real validate affordance ---
#
# Two hosted-QA defects are pinned here.
#
# (1) The Assistant said: "1 path is listed as blocking export: $." The literal `$`
#     comes from the TRUTH CORE (`src/isaac_records/official.py:71` falls back to it
#     for a root-level violation, where `err.absolute_path` is empty). `official.py`
#     is NOT edited; the humanization is display-only, and the exact locator is
#     preserved in `technical_paths` for the Technical Details disclosure.
#
# (2) The validate affordance was a CITED-SOURCE chip `{"label": "Open Validate",
#     "navigate_to": base}` where `base` is `/record/<id>` — the record already on
#     screen. Clicking it navigated to the current page, so nothing visibly
#     happened. It is now a typed `action` targeting the standalone Validator, and
#     the response no longer cites an action as if it were a source.


def _action_of(client, exp_id, question) -> dict:
    return _query(client, exp_id, question).json()


def test_root_level_blocker_is_never_reported_as_the_raw_dollar_locator(client):
    """The exact reported hosted defect. The seed new draft's validate dry-run
    yields a single ROOT-level error whose locator is the literal `$`."""
    body = _action_of(client, ws.SEED_NEW_DRAFT_ID, "why can't I export?")
    assert body["result"] == "answered"
    # the primary, user-facing answer names the RECORD, never the raw locator
    assert "$" not in body["answer"]
    assert body["answer"].startswith("1 record-level validation issue may be blocking export.")
    assert "1 path is listed as blocking export" not in body["answer"]
    # …and the exact locator survives, for the Technical Details disclosure only
    assert body["technical_paths"] == ["$"]


def test_export_blockers_carries_the_open_validator_action_not_a_self_navigating_chip(client):
    body = _action_of(client, ws.SEED_NEW_DRAFT_ID, "what's blocking export?")
    # the typed action mirrors the frontend's frozen OPEN_VALIDATOR_ACTION exactly
    assert body["action"] == {
        "kind": "open-validator",
        "label": "Open Validator",
        "to": "/governance?tab=validator",
    }
    # the misnamed, self-navigating cited-source chip is gone
    assert body["sources"] == []
    labels = [s["label"] for s in body["sources"]]
    assert "Open Validate" not in labels
    # the action target is a BASE-PATH-FREE in-app client route: the deployed
    # `/krish` prefix is applied by the router's basename, never written here
    assert body["action"]["to"].startswith("/governance")
    assert not body["action"]["to"].startswith("/krish")
    assert "://" not in body["action"]["to"]
    # it never points at the record already on screen
    assert not body["action"]["to"].startswith("/record")


def test_export_readiness_carries_the_same_action(client):
    body = _action_of(client, ws.SEED_READY_ID, "is this ready to export?")
    assert body["action"]["kind"] == "open-validator"
    assert body["action"]["to"] == "/governance?tab=validator"
    assert body["sources"] == []


def test_the_visible_control_name_is_open_validator_everywhere(client):
    """Label consistency: the control is "Open Validator". The prose used to name
    "Open Validate", a control that existed nowhere in the app under that name."""
    assert "Open Validate to" not in aq._ROUTE_TO_VALIDATE
    assert "Open Validator" in aq._ROUTE_TO_VALIDATE
    for exp_id, q in (
        (ws.SEED_NEW_DRAFT_ID, "what's blocking export?"),
        (ws.SEED_READY_ID, "why can't I export?"),
        (ws.SEED_READY_ID, "is this ready to export?"),
    ):
        answer = _action_of(client, exp_id, q)["answer"]
        assert "Open Validator" in answer
        # the retired name must not reappear in either casing
        assert not re.search(r"open Validate\b", answer, re.I), answer


def test_no_other_intent_offers_an_action(client):
    """Nothing new was surfaced: only the two export intents carry the action."""
    for q in ("what still needs me?", "what is the current step",
              "summarize this record", "where did the formula come from",
              "what's the evidence for the formula", "docs about xanes",
              "what is the oxidation state of iron",
              "what's the current step and what's missing"):
        body = _action_of(client, ws.SEED_READY_ID, q)
        assert body["action"] is None, (q, body["action"])
        assert body["technical_paths"] == [], (q, body["technical_paths"])


def test_memory_scope_response_has_the_same_shape_and_offers_no_action(client):
    body = _mem_query(client, "docs about xanes").json()
    assert body["action"] is None
    assert body["technical_paths"] == []


def test_every_answer_carries_both_new_keys(client):
    """A stable response shape: the keys are always present, never conditionally
    absent, so a client never has to distinguish absent from empty."""
    for q in [q for q, _ in INTENT_CASES] + OPEN_WORLD:
        body = _action_of(client, ws.SEED_READY_ID, q)
        assert "action" in body and "technical_paths" in body, q
        assert isinstance(body["technical_paths"], list), q


def test_the_action_passes_the_same_guards_as_a_cited_source(client):
    """The action goes through the SAME client-route allowlist, path/secret scrub
    and verdict guard every cited source passes."""
    body = _action_of(client, ws.SEED_NEW_DRAFT_ID, "why can't I export?")
    action = body["action"]
    _no_leak(action["label"])
    _no_leak(action["to"])
    assert aq.has_verdict_language(action["label"]) is False
    assert action["to"].startswith(aq._CLIENT_ROUTE_PREFIXES)
    # a hostile / unknown descriptor is refused outright, never passed through
    assert aq._safe_action(None) is None
    assert aq._safe_action({"kind": "open-validator", "label": "x"}) is None
    assert aq._safe_action(
        {"kind": "open-validator", "label": "x", "to": "/Users/me/secret"}
    ) is None
    assert aq._safe_action(
        {"kind": "open-validator", "label": "x", "to": "https://evil.example"}
    ) is None
    assert aq._safe_action(
        {"kind": "open-validator", "label": "Records valid against v1.05",
         "to": "/governance?tab=validator"}
    ) is None
    assert aq._safe_action({"kind": "", "label": "x", "to": "/governance"}) is None


def test_technical_paths_pass_the_path_secret_scrub(client):
    """A locator is rendered verbatim in the disclosure, so it passes the same
    scrub. One that trips it is never rewritten into something it is not — it is
    replaced by the explicit withheld MARKER (P36V.1 review M5: a silent drop
    desynchronized the stated count from the shown locators)."""
    assert aq._safe_technical_paths(["$", "assets.0.sha256"]) == ["$", "assets.0.sha256"]
    assert aq._safe_technical_paths(["/Users/me/x.json"]) == [aq.WITHHELD_TECHNICAL]
    assert aq._safe_technical_paths(["Bearer abc"]) == [aq.WITHHELD_TECHNICAL]
    # the unsafe content itself never survives, in either case
    for shown in (aq._safe_technical_paths(["/Users/me/x.json"])
                  + aq._safe_technical_paths(["Bearer abc"])):
        _no_leak(shown)
    assert aq._safe_technical_paths([None, "", 7, "$"]) == ["$"]
    assert aq._safe_technical_paths("not a list") == []


def test_new_copy_passes_the_verdict_guard_and_the_leak_scrub(client):
    for exp_id in (ws.SEED_NEW_DRAFT_ID, ws.SEED_READY_ID):
        for q in ("why can't I export?", "is this ready to export?"):
            body = _action_of(client, exp_id, q)
            assert aq.has_verdict_language(body["answer"]) is False, body["answer"]
            assert aq._is_unsafe_string(body["answer"]) is False, body["answer"]
            _no_leak(body["answer"])
            for p in body["technical_paths"]:
                _no_leak(p)


def test_readiness_clause_is_grammatical(client):
    """The clause used to read "This record has 5 fields still need you"."""
    for exp_id in (ws.SEED_NEW_DRAFT_ID, ws.SEED_READY_ID):
        answer = _action_of(client, exp_id, "is this ready to export?")["answer"]
        assert "has 0 field" not in answer
        assert re.search(r"On this record, \d+ fields? still needs? you\.", answer), answer


def test_blocker_answers_stay_deterministic_and_read_only(client):
    before = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    first = _action_of(client, ws.SEED_NEW_DRAFT_ID, "why can't I export?")
    second = _action_of(client, ws.SEED_NEW_DRAFT_ID, "why can't I export?")
    assert first == second
    after = client.get(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}").json()
    # rev + version unchanged: humanizing a locator and offering a navigation
    # target mutated nothing and ran no validation that changed anything.
    assert after["rev"] == before["rev"]
    assert after["version"] == before["version"]


def _ctx(**over) -> aq.AssistantContext:
    """A minimal, workspace-free context for unit-level `answer()` tests."""
    kwargs = dict(
        record_summary={}, pending={"pending": []}, evidence_trail=[], workflow={},
        record_rev=1, version_token="1.0", navigate_base="/record/x",
    )
    kwargs.update(over)
    return aq.AssistantContext(**kwargs)


def test_a_branch_that_raises_returns_no_partial_extras(monkeypatch):
    """If a branch populates `extras` and then raises, the fallback answer must not
    carry a half-built action / locator list.

    P36V.1 review M3 — this test used to patch `blocking_summary`, which is called
    BEFORE either extra is assigned, so `extras` was still empty when the exception
    unwound and the `extras = {}` reset it claims to exercise was a no-op. It now
    patches `_open_validator_action`, the LAST assignment in the branch: by the time
    it raises, `extras["technical_paths"]` really is populated."""
    ctx = _ctx(validate=lambda: {"ok": False, "errors": [{"path": "$"}]})

    seen: dict = {}
    real_technical = aq.technical_paths

    def spy(paths):
        out = real_technical(paths)
        seen["technical"] = out
        return out

    def boom():
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(aq, "technical_paths", spy)
    monkeypatch.setattr(aq, "_open_validator_action", boom)
    body = aq.answer(aq.classify("why can't I export?"), ctx, None)

    # proof the partially-populated path was really exercised this time
    assert seen["technical"] == ["$"]
    assert body["result"] == "insufficient_context"
    assert body["action"] is None
    assert body["technical_paths"] == []
    assert "$" not in body["answer"]


# --- P36V.1 review IMPORTANT-1: the validation-CRASH sentinel ------------------
#
# `routes.py::_assistant_validate_dryrun` returns
# `[{"path": "$", "message": "Validation could not be completed."}]` when the
# deterministic dry-run RAISED. Read through the locator formatter alone that is
# indistinguishable from a root-level violation, so the humanized answer told the
# reader "1 record-level validation issue may be blocking export" — a confident
# claim about an issue the validator never located. `routes.py` is NOT changed here;
# the interpretation is.

_SENTINEL = [{"path": "$", "message": "Validation could not be completed."}]


def test_a_validation_crash_is_never_described_as_a_validation_issue():
    body = aq.answer(aq.classify("why can't I export?"),
                     _ctx(validate=lambda: {"ok": False, "errors": list(_SENTINEL)}), None)
    assert body["result"] == "insufficient_context"
    assert body["answer"].startswith(
        "The deterministic schema check could not be completed for this record"
    )
    # no count, no location, no locator disclosure — none was reported
    assert "validation issue" not in body["answer"]
    assert "record-level" not in body["answer"]
    assert "may be blocking export" not in body["answer"]
    assert "$" not in body["answer"]
    assert body["technical_paths"] == []
    # the reader can still REACH the deterministic check
    assert body["action"]["kind"] == "open-validator"
    assert aq.has_verdict_language(body["answer"]) is False
    assert aq._is_unsafe_string(body["answer"]) is False


def test_a_genuine_root_level_issue_is_still_reported_as_one():
    """The fix is discrimination, not a blanket mute."""
    real = [{"path": "$", "message": "'sample' is a required property"}]
    body = aq.answer(aq.classify("why can't I export?"),
                     _ctx(validate=lambda: {"ok": False, "errors": real}), None)
    assert body["result"] == "answered"
    assert body["answer"].startswith("1 record-level validation issue may be blocking export.")
    assert body["technical_paths"] == ["$"]


def test_the_sentinel_alongside_a_real_finding_is_reported_as_findings():
    mixed = _SENTINEL + [{"path": "assets", "message": "'assets' is a required property"}]
    body = aq.answer(aq.classify("why can't I export?"),
                     _ctx(validate=lambda: {"ok": False, "errors": mixed}), None)
    assert body["result"] == "answered"
    assert body["answer"].startswith(
        "2 validation issues may be blocking export: the record itself, assets."
    )
    assert body["technical_paths"] == ["$", "assets"]


def test_no_errors_is_still_the_honest_empty_answer_not_the_crash_answer():
    body = aq.answer(aq.classify("why can't I export?"),
                     _ctx(validate=lambda: {"ok": True, "errors": []}), None)
    assert body["answer"].startswith(
        "No blocking validation issues are listed in the current validation response."
    )
    assert body["result"] == "answered"


def test_a_crashing_validator_reaches_the_honest_answer_END_TO_END(client, monkeypatch):
    """The whole chain, through the real route: `export_draft` raises → `routes.py`
    emits its sentinel → the resolver describes a crash, not a finding."""
    from isaac_api import routes

    def boom(*_a, **_k):
        raise RuntimeError("synthetic export failure")

    monkeypatch.setattr(routes, "export_draft", boom)
    body = _action_of(client, ws.SEED_NEW_DRAFT_ID, "why can't I export?")
    assert body["result"] == "insufficient_context"
    assert "could not be completed" in body["answer"]
    assert "validation issue" not in body["answer"]
    assert "$" not in body["answer"]
    assert body["technical_paths"] == []
    # and the plain /validate endpoint really did emit the sentinel (the frontend
    # composer's input) — proof the shape being interpreted is the shape produced
    v = client.post(f"/api/experiments/{ws.SEED_NEW_DRAFT_ID}/validate").json()
    assert v["errors"] == [{"path": "$", "message": "Validation could not be completed."}]


# --- P36V.1 review M4: a NEUTRALIZED answer ships no extras --------------------


def test_a_verdict_guarded_answer_ships_no_action_and_no_locators():
    """When the verdict guard replaces the text, the answer names no locations — so
    it must not still carry a locator disclosure or a navigation control (M4)."""
    trips = [{"path": "PASS.x", "message": "m"}, {"path": "assets", "message": "m"}]
    body = aq.answer(aq.classify("why can't I export?"),
                     _ctx(validate=lambda: {"ok": False, "errors": trips}), None)
    assert body["answer"] == aq._NEUTRAL_ROUTED
    assert body["action"] is None
    assert body["technical_paths"] == []


def test_a_leak_guarded_answer_ships_no_action_and_no_locators():
    trips = [{"path": "/Users/me/secret.json", "message": "m"}]
    body = aq.answer(aq.classify("why can't I export?"),
                     _ctx(validate=lambda: {"ok": False, "errors": trips}), None)
    assert body["answer"] == aq._NEUTRAL_ROUTED
    assert body["action"] is None
    assert body["technical_paths"] == []
    _no_leak(body["answer"])


# --- P36V.1 review M5: the stated count and the disclosure agree ---------------


def test_an_unsafe_locator_is_disclosed_as_withheld_not_silently_dropped():
    """The prose count comes from the unfiltered error list, so dropping an unsafe
    4th locator produced "5 validation issues" beside 4 rows, with the missing one
    named nowhere. The count stays truthful and the drop is now disclosed."""
    errors = [
        {"path": "assets", "message": "m"},
        {"path": "sample.id", "message": "m"},
        {"path": "measurement.series", "message": "m"},
        {"path": "/Users/me/secret.json", "message": "m"},
        {"path": "system.technique", "message": "m"},
    ]
    body = aq.answer(aq.classify("why can't I export?"),
                     _ctx(validate=lambda: {"ok": False, "errors": errors}), None)
    # the unsafe locator is past the ≤3 label cap, so the answer text stays safe …
    assert body["answer"].startswith("5 validation issues may be blocking export:")
    _no_leak(body["answer"])
    # … and the disclosure has FIVE rows: the count and the list agree
    assert len(body["technical_paths"]) == 5
    assert body["technical_paths"][3] == aq.WITHHELD_TECHNICAL
    assert body["technical_paths"] == [
        "assets", "sample.id", "measurement.series", aq.WITHHELD_TECHNICAL,
        "system.technique",
    ]
    for p in body["technical_paths"]:
        _no_leak(p)


def test_safe_technical_paths_marks_rather_than_hides_an_unsafe_locator():
    assert aq._safe_technical_paths(["$", "assets.0.sha256"]) == ["$", "assets.0.sha256"]
    assert aq._safe_technical_paths(["/Users/me/x.json"]) == [aq.WITHHELD_TECHNICAL]
    assert aq._safe_technical_paths(["Bearer abc"]) == [aq.WITHHELD_TECHNICAL]
    assert aq._safe_technical_paths(["a" * 40]) == [aq.WITHHELD_TECHNICAL]  # long hex
    # the marker itself is not a locator, and leaks nothing
    _no_leak(aq.WITHHELD_TECHNICAL)
    assert "/" not in aq.WITHHELD_TECHNICAL
    # entries that carry NO locator at all are still omitted (they cannot occur from
    # `technical_paths`, which yields a non-empty string per error)
    assert aq._safe_technical_paths([None, "", 7, "$"]) == ["$"]
    assert aq._safe_technical_paths("not a list") == []


# --- P36V.1 review IMPORTANT-3: cited sources open the surface they name -------


def test_cited_sources_never_point_at_the_record_page_already_on_screen(client):
    """"Complete Metadata" and "Evidence & Sources" targeted `base` — the record page
    the question was asked from — so from the Record Workbench the chip was inert."""
    base = f"/record/{ws.SEED_READY_ID}"
    cases = {
        "what still needs me?": ("Complete Metadata", f"{base}/complete"),
        "where did the formula come from": ("Evidence & Sources", f"{base}/evidence"),
        "what's the evidence for the formula": ("Evidence & Sources", f"{base}/evidence"),
    }
    for question, (label, expected) in cases.items():
        body = _action_of(client, ws.SEED_READY_ID, question)
        assert body["sources"], (question, body)
        src = body["sources"][0]
        assert src["label"] == label, question
        assert src["navigate_to"] == expected, question
        # it survived the SAME allowlist a cited source must pass …
        assert aq._safe_navigate_to(expected) == expected
        # … it is base-path-FREE and in-app
        assert not expected.startswith("/krish")
        assert "://" not in expected
        assert expected != base, "the whole point: not the page already on screen"


def test_the_two_record_root_citations_are_deliberate_and_still_allowlisted(client):
    """The IMPORTANT-3 audit's deliberate leaves: "Workflow" (no `/workflow` client
    route exists — `RecordWorkbench` IS the workflow surface) and "Record" (the
    record root IS the record surface the label names)."""
    base = f"/record/{ws.SEED_READY_ID}"
    for question, label in (("what is the current step", "Workflow"),
                            ("summarize this record", "Record")):
        body = _action_of(client, ws.SEED_READY_ID, question)
        src = body["sources"][0]
        assert src["label"] == label, question
        assert src["navigate_to"] == base, question
        assert aq._safe_navigate_to(base) == base


def test_every_cited_navigate_to_is_an_allowlisted_client_route(client):
    """No new target escaped the allowlist, for ANY catalog question."""
    for q, _intent in INTENT_CASES:
        body = _action_of(client, ws.SEED_READY_ID, q)
        for src in body["sources"]:
            nav = src["navigate_to"]
            if nav is None:
                continue
            assert nav.startswith(aq._CLIENT_ROUTE_PREFIXES), (q, nav)
            assert aq._safe_navigate_to(nav) == nav, (q, nav)
            _no_leak(nav)
    assert aq.has_verdict_language(body["answer"]) is False

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
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import isaac_api.workspace as ws
from isaac_api import assistant_query as aq

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

    return TestClient(create_app())


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

    c = TestClient(create_app())
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

    c = TestClient(create_app())
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

    c = TestClient(create_app())
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

    c = TestClient(create_app())
    r = c.post("/api/assistant/memory/query", json={"question": "docs about xanes"})
    assert r.status_code == 401

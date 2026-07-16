# Phases 23–26 Arc — Approved Scope Decisions

Date: 2026-07-16
Status: Approved by user with revised scope decisions
Base commit at approval: 17b5fff

This document records the approved arc order, scope decisions, and back-burner
list for the Phases 23–26 product arc. Detailed per-phase plans live in
sibling documents; design specs live in `docs/superpowers/specs/`.

## Arc order (approved)

1. Phase 23 — Tiny Cleanup
2. Phase 24 — Project Memory
3. Phase 25 — Grounded Assistant
4. Phase 26 — Real Search

Implementation authorization is gated: Phase 23 first, then a P24.0 design
mini-spec only, then a user review gate before any Project Memory
implementation. P24.0, P25.0, and P26.0 each stop for user review before
implementation begins.

Contingency: if Graphify regeneration or Project Memory design stalls, P25
may move before P24 — but only after reporting the real blocker to the user
first.

## Governing principle

**This must actually work.** No demo-looking UI that pretends a capability
exists. Every visible feature must be backed by real data, real API
behavior, real tests, and honest degraded states.

## Model / subagent rule

- Fable 5: orchestrator, planner, reviewer, verifier, task decomposer only.
  Never directly implements production code or edits implementation files.
- Opus 4.8: product/architecture decisions, Project Memory design, Graphify
  boundary review, source/file explorer architecture, assistant/search
  architecture, final review, design/governance-sensitive judgment.
- Sonnet 5: cleanup implementation, docs micro-fixes, frontend
  copy/CSS/tests, API health additive field, mechanical grep audits,
  low-risk implementation.
- Graphify: discovery/project-memory navigation only. After Graphify
  returns leads, inspect actual files before making claims. Not a source of
  truth.

## Key scope decisions

1. `/api/health` gains additive commit/build identity in Phase 23:
   `ISAAC_BUILD_COMMIT` first, `RAILWAY_GIT_COMMIT_SHA` fallback, `null`
   locally. No auth or deployment-architecture changes.
2. Docs truth micro-fixes in Phase 23 fix current misleading docs only —
   historical design snapshots are not rewritten unless actively misleading
   current readers.
3. Graphify regeneration approved before Phase 24 planning (graph is stale,
   pre-Phase-22). No real/private data indexed; `graphify-out/` never staged.
4. Hosted-demo behavior for Project Memory: honest missing/unavailable
   states if the graph is not present there. No graph snapshot shipped into
   Docker/Railway in this arc without explicit later approval.
5. Project Memory v1 is **project-knowledge memory** (concepts, docs,
   architecture, source files, plan/spec files, provenance, relationships,
   Graphify-indexed artifacts, readable source/file references). It must NOT
   claim related records, record/experiment similarity, scientific
   conclusions, or validation authority.
6. No full graph explorer in this arc. Instead: a scientist/operator-facing
   memory interface — status, concept lookup, source/file provenance,
   related files/docs/concepts, explanation of memory-result provenance,
   clear degraded states. Graph visualization stays local/dev-only or
   back-burner.
7. A safe, read-only source/file explorer is wanted — backed only by
   approved/indexed project knowledge sources. Never an arbitrary
   filesystem browser; never exposes secrets, private data, `examples/`, or
   graphify-out internals; degrades honestly; labeled as project
   knowledge/memory, not validation, and never implies source files are
   scientific evidence unless they actually are.
8. Phase 25: remove the disabled freeform assistant input; replace with
   honest "Guided prompts only" framing. No freeform chat, no LLM-based
   assistant behavior, no assistant-generated scientific values.
9. Phase 26: implement both workspace/truth-plane search (experiments,
   draft fields, evidence sources, artifact/source references) and
   memory/project-knowledge search (concepts, docs/source files, memory
   hits, source-explorer references). Both real, tested, scoped,
   explainable. No fake, decorative, or authority-implying search.
10. P26 rewrite of the P22 "no fake search" honesty tests is approved in
    principle, but only when real search exists, as a clearly reviewed
    dedicated slice with rationale comments — never buried in a feature
    diff. New invariant: fake search must not exist; real search may exist
    only if backed by API behavior, keyboard behavior, result rendering,
    and tests.
11. Approved phase plans are persisted to `docs/superpowers/plans/` as part
    of the appropriate planning/docs slice.

## Back burner (explicitly deferred)

- related records / record similarity / experiment similarity
- full graph explorer / raw network visualization
- graph-in-Docker deployment change
- record indexing into memory
- real/private data memory
- LLM/freeform assistant
- real-data upload
- second domain (performance/electrochemistry etc.)
- portal parity
- MCP
- dark theme
- multi-user auth
- rate limiting

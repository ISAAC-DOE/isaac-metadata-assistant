---
name: isaac-query
description: Answer questions about ISAAC records, schema, vocabulary, history, or related experiments using explicit source routing (official schema, audit CLI, git log, knowledge graph). Use when the user runs /isaac-query or asks questions about the project's records or requirements.
---

# /isaac-query

Route every question to the source that actually owns the answer. The knowledge graph never
answers what a deterministic source can.

## Routing table

| Question class | Source (in order) | Example |
|---|---|---|
| Required fields / structure / allowed values | `schema/isaac_record_v1.json` (blocks, enums, conditional `allOf`) | "What's required for a performance electrochemistry record?" |
| Descriptor class names | `vocabulary/descriptor_class.json` (+ Controlled-Vocabulary wiki) | "What do I call a Tafel-slope descriptor?" |
| How is X encoded in practice | the vendored golden records in `tests/fixtures/official/` | "How is an XAS spectrum stored?" → `ex_situ_xanes_cuo2_record.json` |
| Completeness / which records fail | `.venv/bin/isaac audit` | "Which records fail official validation or lack a sidecar?" |
| A specific record's contents / its evidence | read `records/<id>.json` and `records/<id>.evidence.json` | "Where did record X's beamline come from?" |
| Schema / vocabulary change history | `git log -p -- schema/ vocabulary/` | "What changed since we vendored v1.05?" |
| Similarity / relationships / cross-experiment memory | `graphify query "<q>"` — only if `graphify-out/graph.json` exists | "Which records are related to CuO?" |

## Rules

- The **official schema is the authority.** If the graph or a golden example seems to
  contradict it, the schema wins — say so.
- The graph is **optional and derived.** If `graphify-out/graph.json` is absent, answer the
  deterministic classes normally and offer to build it (`/graphify .`) for similarity questions.
  Graph answers are lossy LLM extractions — present as leads, quote `source_location`.
- Name the source you used in your reply, so the user always knows where a fact came from.

---
name: isaac-query
description: Answer questions about ISAAC records, schema, vocabulary, history, or related experiments using explicit source routing (schema file, audit CLI, git log, knowledge graph). Use when the user runs /isaac-query or asks questions about the project's records or requirements.
---

# /isaac-query

Different question classes have different sources of truth. Route explicitly —
**the knowledge graph never answers a question a deterministic source can.**

## Routing table

| Question class | Source (in order) | Example |
|---|---|---|
| Required fields, record structure | `.venv/bin/isaac required-fields [--technique T]`, then `schema/isaac_record.schema.json` | "What fields are required for an operando XAS record?" |
| Allowed vocabulary terms | `vocabulary/<field>.json` | "What sample environments are allowed?" |
| Completeness / which records fail | `.venv/bin/isaac audit` | "Which records are missing raw-data URIs?" |
| Contents of a specific record | read `records/<id>.json` directly | "What temperature was record X collected at?" |
| Schema / vocabulary change history | `git log -p -- schema/ vocabulary/` | "What changed in the schema recently?" |
| Similarity, relationships, cross-experiment memory | `graphify query "<question>"` — only if `graphify-out/graph.json` exists | "Which campaigns are related to CuO?" |

## Graph rules

- The graph is **optional and derived**. If `graphify-out/graph.json` does not
  exist, answer the deterministic classes normally and, for similarity questions,
  say the graph is not built yet and offer to run `/graphify .`.
- Graph answers are lossy LLM extractions: present them as leads
  ("the graph connects X to Y via Z"), never as validated facts, and quote the
  `source_location` when the query output provides one.
- If a graph answer contradicts the schema, a record file, or the validator,
  the deterministic source wins — say so explicitly.

Answer with the source you used named in the reply, so the user always knows
where a fact came from.

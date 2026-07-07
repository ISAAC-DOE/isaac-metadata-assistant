---
name: isaac-query
description: Answer questions about ISAAC records, schema, vocabulary, history, or related experiments using explicit source routing (official schema, audit CLI, git log, knowledge graph). Use when the user runs /isaac-query or asks questions about the project's records or requirements.
---

# /isaac-query

Route every question to the source that **actually owns the answer**. Split questions into two
classes first, then route:

- **Truth questions** (valid? required? complete? exportable? what value?) → a deterministic source.
  **Graphify may never answer these.**
- **Memory / navigation questions** (where is this? how are these connected? what's related? what
  changed?) → Graphify is useful, but cite and spot-check the file it points at.

The reviewer-facing walkthrough of this split is [`docs/query-demo.md`](../../../docs/query-demo.md).

## Routing table

| Question class | Kind | Source (in order) | Example |
|---|---|---|---|
| Is this record valid? / can this draft export? | truth | `.venv/bin/isaac validate <r> --official` · `isaac export` (**not Graphify**) | "Is record X valid?" |
| Required fields / structure / allowed values | truth | `schema/isaac_record_v1.json` (blocks, enums, conditional `allOf`) | "What's required for a performance electrochemistry record?" |
| Descriptor class names | truth | `vocabulary/descriptor_class.json` (+ Controlled-Vocabulary wiki) | "What do I call a Tafel-slope descriptor?" |
| Completeness / which records fail / dangling evidence | truth | `.venv/bin/isaac audit` (**not Graphify**) | "Which records fail official validation or lack a sidecar?" |
| A specific record's field provenance / evidence | truth | read `records/<id>.json` and `records/<id>.evidence.json` (the sidecar owns evidence; Graphify may *locate* it but the sidecar is authoritative) | "Where did record X's beamline come from?" |
| How is X encoded in practice | source | the vendored golden records in `tests/fixtures/official/` | "How is an XAS spectrum stored?" → `ex_situ_xanes_cuo2_record.json` |
| Schema / vocabulary change history | source | `git log -p -- schema/ vocabulary/` | "What changed since we vendored v1.05?" |
| Architecture / "how is this wired?" / project memory | memory | `graphify explain "<node>"` · `graphify path "<A>" "<B>"` — then cite the doc/source | "How is `export.py` wired?" |
| Related docs / related records / "where is this explained?" | memory | `graphify query "<q>"` — then read the cited file | "Which docs explain the sidecar?" |
| Similarity / relationships / cross-experiment memory | memory | `graphify query "<q>"` — only if `graphify-out/graph.json` exists | "Which records are related to CuO?" |
| Roadmap / mentor decisions / "what's next?" | memory | [`docs/mentor-decisions.md`](../../../docs/mentor-decisions.md), roadmap docs — **the latest human/mentor decision overrides stale graph memory** | "What decisions are open?" |

## Rules

- **Truth beats memory, always.** If the graph or a golden example seems to contradict the official
  schema, a validated record, or the audit, the deterministic source wins — say so explicitly.
- **Graphify cannot decide validity, exportability, required fields, vocabulary, completeness, or any
  missing scientific value.** A missing value stays `pending` and is answered by a human, never by
  the graph, never guessed.
- **The graph is optional and derived.** If `graphify-out/graph.json` is absent, answer the truth
  classes normally and offer to build it (`graphify update .`) for memory/navigation questions.
- **Graph output is leads, not answers.** `graphify query` returns related nodes with
  `src=<file> loc=L<line>` — quote the source location and confirm the claim in that file.
  `graphify explain` / `graphify path` need an **exact node label** (a file/function/entity), not a
  free-text concept; if none matches, fall back to `query` or read the doc directly.
- **Name the source you used** in every reply, so the user always knows where a fact came from.

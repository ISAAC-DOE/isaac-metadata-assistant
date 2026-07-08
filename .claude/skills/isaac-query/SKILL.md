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

The reviewer-facing walkthrough of this split is [`docs/query-demo.md`](../../../docs/query-demo.md);
worked routing patterns are in [`docs/query-cookbook.md`](../../../docs/query-cookbook.md), the
Graphify how-to + freshness policy in [`docs/graphify-workflow.md`](../../../docs/graphify-workflow.md),
and the concept→file map in [`docs/project-memory-map.md`](../../../docs/project-memory-map.md).
The one-screen safety checklist is [`docs/query-safety-checklist.md`](../../../docs/query-safety-checklist.md).

## Routing table

| Question class | Kind | Source (in order) | Example |
|---|---|---|---|
| Is this record valid? / can this draft export? | truth | `.venv/bin/isaac validate <r> --official` · `isaac export` (**not Graphify**) | "Is record X valid?" |
| Required fields / structure / allowed values | truth | `schema/isaac_record_v1.json` (blocks, enums, conditional `allOf`) | "What's required for a performance electrochemistry record?" |
| Descriptor class names | truth | `vocabulary/descriptor_class.json` (+ Controlled-Vocabulary wiki) | "What do I call a Tafel-slope descriptor?" |
| Completeness / which records fail / dangling evidence | truth | `.venv/bin/isaac audit` (**not Graphify**) | "Which records fail official validation or lack a sidecar?" |
| "What does this warning mean?" / advisory soft-warnings | advisory | read [`portal-warnings.md`](../../../docs/portal-warnings.md) + `src/isaac_records/portal_warnings.py`; Graphify only to *navigate* to them. **A warning is advisory / non-gating — never an invalidity verdict.** | "What does `NO_LINKS` mean?" |
| A specific record's field provenance / evidence | truth | read `records/<id>.json` and `records/<id>.evidence.json` (the sidecar owns evidence; Graphify may *locate* it but the sidecar is authoritative) | "Where did record X's beamline come from?" |
| How is X encoded in practice | source | the vendored golden records in `tests/fixtures/official/` | "How is an XAS spectrum stored?" → `ex_situ_xanes_cuo2_record.json` |
| Schema / vocabulary change history | source | `git log -p -- schema/ vocabulary/` | "What changed since we vendored v1.05?" |
| Architecture / "how is this wired?" / "which files implement X?" / project memory | memory | Graphify **first** (`graphify explain "<node>"` · `graphify path "<A>" "<B>"` · `graphify query "<q>"`), **then open and confirm the cited file** — how-to in [`graphify-workflow.md`](../../../docs/graphify-workflow.md) | "Which files implement export?" |
| Related docs / related records / "where is X explained?" | memory | `graphify query "<q>"` for leads, **then read the cited file**; concept→file anchor: [`project-memory-map.md`](../../../docs/project-memory-map.md) | "Which docs explain the sidecar?" |
| Similarity / relationships / cross-experiment memory | memory | `graphify query "<q>"` — only if `graphify-out/graph.json` exists | "Which records are related to CuO?" |
| Roadmap / mentor decisions / "what's next?" | memory | [`docs/mentor-decisions.md`](../../../docs/mentor-decisions.md), roadmap docs — **the latest human/mentor decision overrides stale graph memory** | "What decisions are open?" |
| "Can we use real data?" / real-vs-synthetic policy | policy | [`data-governance.md`](../../../docs/data-governance.md) (+ [`intake.md`](../../../docs/intake.md)) — a **policy** question: do **not** guess, do **not** ask the graph. Real / sanitized data needs explicit **written** approval. | "Can we index a real beamline export?" |

## Fallback order (check availability first)

1. **Truth / policy question?** (valid · required · complete · warning · vocabulary · real-data) →
   go straight to the deterministic source in the table above. **Skip Graphify.**
2. **Memory / navigation question?** → check the graph is usable: `graphify-out/graph.json` exists
   and `graphify` runs.
   - **Usable** → query for leads, then **open and confirm the cited file** before answering.
   - **Missing or erroring** → fall back to direct repo search (grep/read, anchored by
     [`project-memory-map.md`](../../../docs/project-memory-map.md)) and say the memory layer was
     unavailable. **Never invent graph output**; offer to build it (`graphify update .`).
3. **Name the source you actually used** (graph + file, file only, or CLI).

## Rules

- **Truth beats memory, always.** If the graph or a golden example seems to contradict the official
  schema, a validated record, or the audit, the deterministic source wins — say so explicitly.
- **Graphify is never truth.** It cannot decide validity, exportability, required fields, vocabulary,
  or completeness, cannot fill a missing scientific value, and **never overrides a `validate` /
  `audit` result**. A missing value stays `pending` and is answered by a human, never by the graph,
  never guessed.
- **The graph is optional and derived.** If `graphify-out/graph.json` is absent, answer the truth
  classes normally and offer to build it (`graphify update .`) for memory/navigation questions.
- **Graph freshness — treat the graph as a point-in-time snapshot.** Before leaning on it, check
  staleness with the dependency-free `find` check in
  [`graphify-workflow.md` §5](../../../docs/graphify-workflow.md); if it may be stale, say so and
  verify the claim against the actual files. Refresh (`graphify update .`) **only** when a *tracked
  source* actually changed (`README.md` · `CLAUDE.md` · `AGENTS.md` · `pyproject.toml` · `docs/` ·
  `schema/` · `src/` · `scripts/` · `tests/` · `.claude/skills/`) **and** the answer depends on it —
  **never** because of `/tmp` output, `.venv`, caches, or `graphify-out/` itself (none are tracked
  source). Do **not** auto-refresh on every question.
- **Never index real / private data without explicit approval.** Graphify runs on the repo's own
  source, docs, and synthetic fixtures only; anything real (e.g. real artifacts under `examples/`)
  needs approval first — `graphify-out/` is derived and inherits the sensitivity of whatever it
  indexed. See [`data-governance.md`](../../../docs/data-governance.md).
- **Graph output is leads, not answers.** `graphify query` returns related nodes with
  `src=<file> loc=L<line>` — quote the source location and confirm the claim in that file.
  `graphify explain` / `graphify path` need an **exact node label** (a file/function/entity), not a
  free-text concept; if none matches, fall back to `query` or read the doc directly.
- **Name the source you used** in every reply, so the user always knows where a fact came from.

# Graphify query / memory demo (for reviewers)

**Audience:** mentors and reviewers (Angel, Dean) — not just developers.
**Purpose:** show what the Graphify *memory / query* layer adds to the ISAAC Metadata Assistant,
and — just as importantly — what it is **not allowed to decide**.

> **One-sentence version.** The deterministic Python pipeline and the official ISAAC schema decide
> what is *true* (valid, exportable, complete). Graphify is a **memory/navigation layer** on top:
> it helps a person find *where* something lives, *how* pieces connect, and *what* to read next.
> It never validates a record, never fills a missing scientific value, and never authorizes export.

This document is a **demo script**: representative questions, the exact command to run, what you get
back, and how to confirm the answer against the deterministic source. Graphify is optional — the
whole record-building pipeline runs correctly with it entirely absent.

---

## 1. The two planes (why this separation matters)

The system deliberately separates **what is true** from **what we remember**.

| | Truth plane | Memory / query plane |
|---|---|---|
| **Owns** | validity, exportability, required fields, vocabulary, audit result | context, navigation, "where is this?", "how are these connected?" |
| **Made of** | `schema/isaac_record_v1.json`, `official.py`, `draft_validator.py`, `export.py`, `audit.py`, `cli.py`, tests | Graphify (`graphify-out/graph.json`), the docs, the evidence sidecars |
| **Deterministic?** | Yes — same input, same answer, no LLM | No — a lossy LLM-extracted graph snapshot |
| **Required to run?** | Yes | No — optional add-on |
| **Can it authorize export?** | Yes (only this plane can) | **Never** |

A test (`test_core_never_imports_graphify`) structurally enforces that the truth plane never imports
Graphify. If a graph answer ever conflicts with the schema, a validated record, or the audit, **the
deterministic source wins** — and the assistant should say so.

For the pipeline itself, see [`docs/architecture.md`](architecture.md). For the end-to-end proof,
see [`docs/demo.md`](demo.md).

---

## 2. What Graphify is here

Graphify is a knowledge graph built from this repository's own files — source modules, the schema,
the docs, the synthetic fixtures, and the sample record. Each node carries a **source location**
(`src=<file> loc=L<line>`), so every lead points back at a real file you can open and verify.

Build/refresh is a single command; the output lives in `graphify-out/` and is **gitignored**
(never committed):

```bash
graphify update .        # refresh the graph after code/doc changes
```

If `graphify-out/graph.json` is absent, the memory plane is simply unavailable — answer the
deterministic questions normally and offer to build it.

---

## 3. What Graphify is allowed to answer — and what it must not decide

**Graphify is useful for (memory / navigation):**

- architecture navigation — "how is `export.py` wired?"
- project memory — related docs, related records, related fixtures
- "where is this explained / where does this live?"
- "what is connected to this sample / field / module?"
- documentation and cross-experiment leads
- "what changed / how did we get here?" as *context* (git log remains the precise history)

**Graphify must NOT decide (truth):**

- ❌ whether a record is valid → `isaac validate --official`
- ❌ whether a draft can be exported → `isaac export` (gated by both validators)
- ❌ which fields are required / what vocabulary is allowed → the official schema
- ❌ whether records are complete / sidecars resolve → `isaac audit`
- ❌ the value of any missing scientific field (sha256, spectrum, descriptor, edge) → **stays
  `pending`, answered by a human, never guessed**
- ❌ what the current roadmap / mentor decision is → the docs + the latest human decision override
  stale graph memory

Graphify provides context. The deterministic pipeline and official schema provide truth.

---

## 4. When to use a deterministic source instead

For anything that decides truth, skip the graph and run the real check:

| Question | Correct source (not Graphify) |
|---|---|
| "Is this record valid?" | `.venv/bin/isaac validate <record> --official` |
| "What's required for this record type?" | `schema/isaac_record_v1.json` (blocks, enums, conditional `allOf`) |
| "Which records are incomplete / have dangling evidence?" | `.venv/bin/isaac audit` |
| "Where did this record's field come from?" | `records/<id>.evidence.json` (the sidecar) |
| "What exactly changed in the schema?" | `git log -p -- schema/` |
| "Can this draft export?" | `.venv/bin/isaac export <draft>` (refuses unless both validators pass) |

---

## 5. The three Graphify commands (real, tested behavior)

All output below is from the graph in this repo. Graphify returns **leads with source locations**,
not a synthesized prose answer — you then open the cited file to confirm.

### `graphify query "<natural-language question>"`

Traverses the graph from semantically-matched start nodes and returns related nodes + edges, each
with a source location. Best for "what is connected to this / where does this live?"

```text
$ graphify query "Where is the evidence sidecar explained?"
Traversal: BFS depth=2 | Start: ['evidence', 'evidence', 'evidence()'] | 45 nodes found
NODE export.py          [src=src/isaac_records/export.py loc=L1  ...]
NODE validate_official()[src=src/isaac_records/official.py loc=L67 ...]
NODE validate_draft()   [src=src/isaac_records/draft_validator.py loc=L88 ...]
...
```

Note what this is and isn't: it surfaced the **implementation** that builds the sidecar
(`export.py`) — good navigation leads — but the *prose explanation* lives in
[`docs/architecture.md` → "Why the sidecar exists"](architecture.md) and the README "Two layers"
section. Use the leads to jump to the right neighborhood, then read the doc/source to get the actual
answer.

### `graphify explain "<node label>"`

A node card: source location, type, community, degree, and every connection. Best for "how is this
file/function wired into the rest of the system?"

```text
$ graphify explain "export.py"
Node: export.py   Source: src/isaac_records/export.py L1   Type: code   Degree: 22
  <-- cli.py [imports_from]        --> validate_official() [imports]
  <-- audit.py [imports_from]      --> official.py [imports_from]
  --> transform() [contains]       --> draft_validator.py [imports_from]
  --> export_draft() [contains]    --> validate_draft() [imports]
  ...
```

That single card shows the truth-plane wiring at a glance: `cli.py` and `audit.py` call into
`export.py`, and `export.py` gates on `validate_official` + `validate_draft`.

> ⚠️ `explain` needs an **actual node label** (a file, function, or extracted entity), not a
> free-text concept. `graphify explain "no-guessing policy"` returns *"No node matching …"*. For
> concept questions, use `query`, or read the doc directly (no-guessing lives in
> [`CLAUDE.md` §5](../CLAUDE.md) and the README "Core principle").

### `graphify path "<node A>" "<node B>"`

Shortest path between two node labels. Best for "how are these two things connected?"

```text
$ graphify path "export.py" "official.py"
Shortest path (1 hops):
  export.py --imports_from [EXTRACTED]--> official.py
```

---

## 6. Worked reviewer questions

A representative set. Each row: the question, whether it's a *memory* or *truth* question, and the
route that actually owns the answer.

| Reviewer question | Kind | Route |
|---|---|---|
| What does the synthetic demo prove? | memory | `graphify query` for leads → confirm in [`docs/demo.md`](demo.md) |
| Where is the evidence sidecar explained? | memory | `graphify query "evidence sidecar"` → [`docs/architecture.md`](architecture.md) "Why the sidecar exists" + README "Two layers" |
| Difference between a draft and an official record? | memory | README "Two layers"; [`docs/architecture.md`](architecture.md). Official *shape* is owned by `schema/isaac_record_v1.json` |
| Why leave `sha256` pending instead of guessing? | memory | [`CLAUDE.md` §5](../CLAUDE.md) no-guessing; [`docs/architecture.md`](architecture.md) "what needs a human"; enforced in `draft_validator.py` |
| Which docs explain the no-guessing policy? | memory | `CLAUDE.md` §5, README "Core principle", [`docs/architecture.md`](architecture.md) |
| How does a draft become an official record? | memory | [`docs/architecture.md`](architecture.md) pipeline; the actual transform is `isaac export` |
| What decisions are still open for mentors? | memory | [`docs/mentor-decisions.md`](mentor-decisions.md) (D1–D8) — **the doc + latest human decision are authoritative, not stale graph memory** |
| What are the current limitations? | memory | [`docs/architecture.md`](architecture.md) "Not built yet"; §7 below |
| Where is portal validation discussed? | memory | [`docs/portal-warnings.md`](portal-warnings.md) (the non-gating advisory seam), README "Validation stack" (stage 3) — hard gate stays `isaac validate --official` |
| Truth plane vs memory/query plane? | memory | README "Two planes"; [`docs/architecture.md`](architecture.md); §1 above |
| Which files explain the one-command demo? | memory | README "Quickstart"; [`docs/demo.md`](demo.md); `scripts/run_synthetic_demo.py` |
| What is deterministic vs. future/optional? | memory | [`docs/architecture.md`](architecture.md) "deterministic vs. a human" + "Not built yet" |
| **Is this record valid?** | **truth** | **`isaac validate --official` — NOT Graphify** |
| **Can this draft export?** | **truth** | **`isaac export` — NOT Graphify** |
| **Which records fail / lack a sidecar?** | **truth** | **`isaac audit` — NOT Graphify** |

The bottom three rows are the guardrail: a validity/export/completeness question is answered by
running the deterministic check, never by the graph.

---

## 7. How to spot-check any Graphify claim

The graph is a **lossy LLM extraction**, refreshed on demand, not a live source of truth. Treat every
graph answer as a lead:

1. **Read the `src=<file> loc=L<line>`** on the node — it points at a real file and line.
2. **Open that file** and confirm the claim is actually there.
3. **If it's a truth question** (valid? required? complete? exportable?), ignore the graph and run
   the deterministic command (§4).
4. **If the graph and a deterministic source disagree**, the deterministic source wins — and the
   graph may be stale; consider `graphify update .`.

Known caveats: `query` traversals can start from imperfectly-matched nodes and surface adjacent-but-
not-exact results; `explain`/`path` need exact node labels; the committed sample and fixtures are
**synthetic**, so graph nodes about "CuO2 / BL15-2 / SSRL" describe fake demo data, not real
experiments.

---

## 8. How this supports the ISAAC assistant story

- The prototype **already** produces official, schema-valid ISAAC records through a deterministic,
  no-guessing pipeline (proven end-to-end in [`docs/demo.md`](demo.md)).
- Graphify makes that system **navigable and explainable**: a reviewer or a future teammate can ask
  where a concept lives, how modules connect, and what to read next — without touching the truth path.
- Because validation, export, and audit stay deterministic and Graphify-free, adding a memory layer
  **does not cost any trust**. The graph can be wrong or absent and the records are still valid.
- This is the shape we want to pitch: **deterministic truth + assistant memory**, cleanly separated.

---

## 9. Current limitations (honest)

- **Leads, not answers.** `query` returns related nodes with source locations, not a finished prose
  answer. You still open the cited doc/source.
- **`explain`/`path` need exact node labels.** Free-text concepts may return "No node matching".
- **Lossy + point-in-time.** The graph is an LLM extraction from a past snapshot; refresh with
  `graphify update .` after significant changes. Do not commit `graphify-out/`.
- **Synthetic only.** Every record/fixture in the graph is synthetic demo data.
- **No graceful-degradation test suite yet.** `/isaac-query` routes to the graph when present and
  degrades to deterministic sources when absent, but a dedicated automated test tier for that
  fallback is deferred (future query-layer work).
- **Not truth, by design.** Graphify is intentionally excluded from validation/export/audit. This is
  a feature, not a gap.

---

*Reproduce the deterministic proof this doc sits on top of:* [`docs/demo.md`](demo.md).
*See the plane boundary in code:* `test_core_never_imports_graphify`.
*Which source owns which question:* [`query-cookbook.md`](query-cookbook.md).
*Build / query / refresh the graph (and the freshness policy):* [`graphify-workflow.md`](graphify-workflow.md).

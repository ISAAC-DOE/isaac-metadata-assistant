# Graphify Efficacy Benchmark — Methodology and Pre-Registration

**Status:** pre-registered. **Written before any benchmark arm executed and before any
result was observed.** Repository HEAD at pre-registration: `9df2ef7` (main).

This document exists so the verdict cannot be fitted to the data. The decision rules in
§5 were fixed in advance; if a later revision changes them, that revision must say so
explicitly and give the reason, rather than editing them silently.

---

## 1. The question

Not "does Graphify work?" but:

> Does Graphify materially improve repository navigation, understanding, relationship
> discovery, and task completion compared with ordinary repository tools — and on which
> kinds of tasks?

The unit of analysis is the **task category**, not an overall score. A single aggregate
number would hide the thing most worth knowing: that a tool can be strong on one class
of question and actively misleading on another.

## 2. Corpus

The ISAAC repository itself, at `9df2ef7`. It is a reasonable benchmark corpus because
it contains a Python truth core, a FastAPI backend, a React/TypeScript frontend, a large
`docs/` tree with historical decision records, extensive tests, JSON schemas, and a long
commit history — enough real complexity for relationship-discovery questions to be
non-trivial.

Everything in this repository is public. No task touches private data, the deployed
application, the database, or the network.

## 3. Index state — measured, not assumed

The graph found on disk at the start of this work was **stale by 420 commits and 529
changed files** (built at `caab1d0`, 2026-07-18; benchmark begins at `9df2ef7`,
2026-08-07). Benchmarking against that artifact would have measured *stale Graphify*, not
Graphify, and would have understated the tool.

The index was therefore rebuilt at exactly `9df2ef7` before either arm ran.

| Measurement | Value | How obtained |
|---|---|---|
| Reindex wall-clock | **10.04 s** | `/usr/bin/time -p graphify update .` |
| External model invocations for reindex | **0** | tool reported "no LLM needed"; no API key set |
| Nodes before → after | 2,988 → **10,618** | `graph.json` |
| Edges before → after | 4,465 → **18,849** | `graph.json` |
| Communities | 585 | tool output |
| Median query latency | **~0.6 s** (0.57–0.69 s over 4 queries) | wall-clock around `graphify query` |
| `graph.html` visualisation | **not generated** | tool refused: 10,618 nodes exceeds its 5,000-node viz limit |

The schema of the rebuilt graph is identical to the stale one (same node keys, same
relation vocabulary) and every relation type grew, so the rebuild is an enlargement, not
a regression. This was checked rather than assumed, because the tool's log line
("backed up curated graph") could be misread as destructive.

**The staleness itself is a finding**, and it belongs to the observational record (§7),
not to the controlled comparison: in the real life of this project the graph was allowed
to drift 420 commits behind HEAD. The controlled arms use a fresh index, which is the
*most favourable* condition for Graphify. Any weakness the benchmark finds under a fresh
index cannot be explained away as staleness.

## 4. Design

### 4.1 Task set

Eight tasks, frozen by an independent designer agent **before** either arm ran. The
designer was forbidden from using Graphify, forbidden from reading `graphify-out/`, and
did not know the decision rules below.

Category coverage is deliberately not uniform in Graphify's favour:

| Category | What it probes |
|---|---|
| A | Cross-document conceptual discovery |
| B | Architecture / data-flow tracing |
| C | Change-impact discovery |
| D | Feature ownership / navigation |
| E | Security / trust relationship discovery (public-safe only) |
| F | Exact-string / stale-state lookup — **negative control**, grep expected to win |
| G | Truth-path / runtime verification — real code and tests are the only authority |

At least one task is an **intentionally misleading semantic probe**: nearby concepts
exist in the repository but only one exact implementation is correct. It measures
false-lead behaviour, which an accuracy-only metric would miss.

The frozen task set is `docs/evidence/graphify-task-set.json`.

### 4.2 Gold answers

Built by a separate independent evaluator, without Graphify, using direct file
inspection, `rg`, `git`, and test execution. For each task the gold record holds required
files, relevant symbols, required relationships, the expected conclusion, and known false
leads. **Gold answers are never shown to benchmark agents.**

> **Post-run correction to what this section implies.** Gold records were built and used,
> but **were never committed to this package** — see §5.2a. Nothing here should be read as
> a promise that a third party can inspect them.

Grading is on *evidence*, not prose similarity: did the agent reach the right conclusion,
and did it cite the files that actually establish it?

### 4.3 Arms

Fresh isolated agents, no shared conversational memory, neither arm able to see the
other's output.

- **Arm A (baseline):** filesystem navigation, `find`, `rg`, `grep`, `git`, direct file
  reads, tests/CLI. Graphify forbidden.
- **Arm B (Graphify-assisted):** Graphify available for discovery and navigation, plus
  all ordinary tools afterwards. Agents must still open real files before asserting
  anything — the standing project rule that Graphify returns leads and files remain the
  source of truth is preserved inside the experiment.

Identical task prompts, identical completion criteria, comparable agent configuration.

### 4.4 Repetition and order

2 independent runs per task per arm = 32 runs at minimum. A third run is added only for
tasks whose two runs disagree enough to leave a category verdict unstable. Runs are not
multiplied by default.

Task order is varied between runs so that order and learning effects do not systematically
favour one arm.

## 5. PRE-REGISTERED DECISION RULES

*Fixed before results. Not to be retuned afterwards.*

### 5.1 Gate

**Graphify must not reduce correctness to qualify as helpful.** Correctness dominates
every efficiency gain: a faster route to a wrong or unsupported answer is a worse tool,
not a better one. If Arm B's correctness is materially below Arm A's in a category, that
category cannot be classified better than `GRAPHIFY_HARMFUL` regardless of speed.

### 5.2 Metrics

> **Annotated after the benchmark ran — declarations unchanged, collection status added.**
> The status column below was appended once the runs were complete. **No metric was added,
> removed, or reworded**, and no decision rule in §5.1/§5.3/§5.4 was touched. The column
> exists because seven of the metrics declared here were never collected, and a
> pre-registration that silently reports only the favourable subset defeats its own purpose.
> The full accounting — why each was dropped, and whether its absence could have changed a
> category verdict — is in the results document under **"Declared but not measured"**.

**Quality** (graded against gold, blind to arm where practical):

| Declared metric | Collected? |
|---|---|
| conclusion correctness | **yes** — per-run, but recorded on only 17 of 32 runs; see the results doc |
| required-file recall | **no** |
| evidence completeness | **no** |
| count of false-positive leads pursued | **partly** — boolean lead flags and a `dead_ends` count, never a count graded against gold |
| unsupported claims | **no** |
| missed relationships | **no** |

**Efficiency:**

| Declared metric | Collected? |
|---|---|
| elapsed wall-clock | **yes** (`duration_ms`) — but excluded from every verdict as CPU-contended |
| tool calls | **yes** — this is the effort measure every verdict is computed from |
| files opened | **yes** — reported as a headline count; not a verdict input |
| irrelevant files opened | **no** |
| Graphify query count | **yes** |
| downstream verification calls | **no** |
| tokens where measurable | **yes** |

**Operational overhead** — measured and reported *separately*, never netted silently
against per-task gains: index build/refresh time (**collected**), query latency
(**collected**), storage (**not collected** — node and edge counts are reported in its
place; bytes on disk were never measured), staleness risk (**collected**), maintenance
burden (**reported qualitatively**). Both figures are reported: per-task interactive
efficiency, and total cost including indexing.

### 5.2a Gold answers were used for grading but never committed

Recorded here, at the point of declaration, so a reader of §4.2 is not misled: the gold
records described in §4.2 were built and were used to grade every run, but **they are not
part of this evidence package**. `graphify-task-set.json` holds the prompts, not the
answers. Correctness grading is therefore **not independently auditable**. See the results
document's threats-to-validity section for exactly which correctness claims a reader can
still check against committed artifacts, and which they cannot.

### 5.3 Category classification

Per category:

- **`GRAPHIFY_STRONGLY_HELPFUL`** — correctness equal or better, AND a substantial and
  consistent improvement in median time or tool effort (≥30% on the effort measure, in the
  same direction in every run of the category).
- **`GRAPHIFY_HELPFUL`** — correctness equal or better, AND a material median improvement
  in time or tool effort (≥15%), without a countervailing rise in false leads.
- **`GRAPHIFY_NEUTRAL`** — correctness equal and effort within ±15%, or gains and losses
  that cancel.
- **`GRAPHIFY_HARMFUL`** — correctness declines, OR false leads materially increase, OR
  effort increases without a compensating quality gain.
- **`INSUFFICIENT_EVIDENCE`** — runs within the category disagree and a third run does not
  resolve them, or the task proved defective.

### 5.4 Rules that protect the negative controls

- Graphify receives **no credit** on a task that a deterministic tool answers correctly and
  faster. Category F exists to be lost.
- On the misleading semantic probe, pursuing a plausible-but-wrong lead is scored as a
  false positive **even if the agent eventually recovers**. Recovery cost is real cost.
- An arm that reaches the right conclusion **without** citing the files that establish it
  is scored as not-correct. Confident unsupported answers are a failure mode, not a near-miss.

### 5.5 Honesty commitments

- If the benchmark shows Graphify is not meaningfully useful, the report says so, and the
  project's guidance is narrowed to match. The feature is not protected from its own result.
- Indexing and maintenance overhead is never hidden inside a per-task average.
- Any task discovered to be defective mid-benchmark is reported as defective and excluded
  explicitly, never silently dropped or quietly replaced.
- Controlled-benchmark evidence and observational repository evidence (§7) are reported
  separately and never mixed.

## 6. Threats to validity

- **n is small.** 8 tasks × 2 runs × 2 arms detects large, consistent effects; it does not
  resolve subtle ones. Category verdicts resting on a single divergent run are reported as
  `INSUFFICIENT_EVIDENCE` rather than as a finding.
- **Single corpus, single repository.** Conclusions are about this repository's shape —
  Python + TypeScript, doc-heavy, history-heavy. They do not automatically transfer.
- **Agent variance** is a real confound; repetition is the only control applied.
- **The fresh index favours Graphify** relative to how the tool was actually kept in this
  project. Stated plainly so the result is read in the right direction.
- **The grader knows which arm produced which transcript** in cases where the transcript
  mentions a tool by name. Grading is anchored on file-level evidence to blunt this.

## 7. Observational evidence is kept separate

A parallel review of how Graphify has actually been integrated, maintained, enforced and
used in this repository's history is reported in the results document under its own
heading. It is **observational, not experimental**: it can show what the project believed
and did, but it cannot establish efficacy. Where the repository's design intent and the
benchmark's measured outcome disagree, that disagreement is reported explicitly.

---

## Change log

| Date | Change |
|---|---|
| 2026-08-07 | Pre-registered. No arm had run; no result observed. |
| 2026-08-08 | **Disclosure only — no decision rule changed.** §5.2 annotated with per-metric collection status (seven declared metrics were never collected); §4.2 corrected to state that gold records exist but were not committed; §5.2a added. The declared metric list, §5.1, §5.3 and §5.4 are byte-unchanged, and no verdict was recomputed. |

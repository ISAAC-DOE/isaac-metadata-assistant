# Graphify Efficacy Benchmark — Results

**Methodology and pre-registered decision rules:**
[`graphify-benchmark-methodology.md`](graphify-benchmark-methodology.md) — written and committed
**before** any arm ran and before any result was observed.
**Frozen task set:** [`graphify-task-set.json`](graphify-task-set.json).
**Raw per-run metrics:** [`graphify-run-results.json`](graphify-run-results.json).

Repository under test: ISAAC at `9df2ef7`, in an isolated worktree pinned to that commit so
concurrent work on `main` could not perturb it. Graph index rebuilt at exactly that commit.

---

## 1. Headline

Across 8 tasks × 2 arms × 2 runs — **32 usable runs, 16 per arm** (plus 1 excluded harness failure):

| Metric | Arm A (baseline) | Arm B (Graphify) | Δ (B vs A) |
|---|---|---|---|
| Tool calls, median | 26.5 | 28.0 | **+5.7%** |
| Files opened, median | 9.5 | 8.0 | −15.8% |
| Tokens, median | 94,614 | 95,093 | **+0.5%** |
| Dead ends, median | 1.5 | 1.0 | −33.3% |
| Tokens, total | 1,568,835 | 1,634,044 | **+4.2%** |

Graphify-assisted agents spent **slightly more** effort overall and opened somewhat fewer files.
Token cost is level to within 0.5%. Nothing here is a material efficiency gain.

**The qualitative result is stronger than the numeric one.** Across **16 Arm B runs, the agents'
own self-assessment `graphify_helped` was never once "yes"** — 13 × "partly", 3 × "no". In every
run where Arm B reached the answer, its own notes credit `rg`/`grep`, not the graph.

Correctness after both runs: **7 ties and 1 consistent Arm B advantage** (task T3).

**One correction, because an earlier draft of this document overstated it.** That draft said
"Graphify never reduced correctness". That is contradicted by data shipped in this same
package: on T5 run 1, Arm B named the wrong "unprotectable shape" and is recorded as
`possible_wrong_answer` in `graphify-run-results.json`, with the run-2 entry stating verbatim
that "run1 ArmB got this WRONG". Arm A was correct on that item in **both** runs.

The accurate statement is narrower: **Arm B produced one wrong answer that Arm A did not, and
Arm A produced one wrong answer that Arm B did not** (T3's missed `export.py:23`, missed in
both Arm A runs). Arm B's T5 miss did not repeat in run 2 and is best read as within-arm
variance — the same reading applied to Arm A's T6 run-1 errors, which also did not repeat.
Under the §5.1 gate Graphify still passes, because no category shows a *sustained* correctness
decline. It was not demonstrated to raise correctness either.

---

## 2. Category verdicts

Applied mechanically from the pre-registered §5.3 rules. Effort is measured in **tool calls**;
wall-clock is excluded as contended (see §5).

| Cat | Task | Correctness | Tool calls A → B (median) | Verdict |
|---|---|---|---|---|
| A — cross-document discovery | T1 | tie (both correct ×2) | 27.0 → 27.5 (+1.9%) | `GRAPHIFY_NEUTRAL` |
| B — architecture tracing | T2 | tie (both correct ×2) | 32.5 → 27.5 (−15.4%) | `INSUFFICIENT_EVIDENCE` |
| C — change impact | T3 | **Arm B better, 2/2 vs 0/2** | 48.0 → 40.0 (−16.7%) | `GRAPHIFY_HELPFUL` *(see caveat)* |
| D — feature ownership | T4 | tie (both correct ×2) | 23.5 → 24.0 (+2.1%) | `GRAPHIFY_NEUTRAL` |
| E — security/trust | T5 | tie after both runs | 25.0 → 34.0 (+36%) | `INSUFFICIENT_EVIDENCE` |
| F — exact-string (**negative control**) | T6 | tie after both runs | 40.5 → 51.0 (**+26%**) | **`GRAPHIFY_HARMFUL`** |
| G — truth-path/runtime | T7 | tie (both correct ×2) | 21.0 → 27.5 (+31%) | `INSUFFICIENT_EVIDENCE` |
| D — misleading probe | T8 | tie (both correct ×2) | 21.5 → 18.0 (−16.3%) | `GRAPHIFY_NEUTRAL` |

### The negative control was lost, as designed — and the loss is clean

Category F (T6, exhaustive environment-variable inventory) is the one category where the
distributions **do not overlap**, in either direction:

| | Arm A runs | Arm B runs |
|---|---|---|
| Tool calls | 39, 42 | **48, 54** |
| Tokens | 105,516 · 103,478 | **122,741 · 126,738** |

Every Arm B run cost more than every Arm A run — +26% tool calls, +19% tokens — for **equal
correctness**. That satisfies the pre-registered `GRAPHIFY_HARMFUL` condition ("effort increases
without a compensating quality gain") and, unlike the three categories below, it does not rest on a
single divergent run.

This is the result the negative control existed to produce. It is also the only category where
an Arm B agent lowered its own confidence to *medium*. The mechanism is in §3: the graph
answered a completeness question with a **documentation table that omits ~12 of the required
variables**.

*(An earlier draft claimed this was "the only category where both Arm B agents rated Graphify
'no'". That is wrong and the raw data in this package contradicts it: T6's ratings were
"partly" then "no". The three "no" ratings across the whole benchmark fall in **three
different** tasks — T4, T5, T6 — one each. No category has two. The error made the
negative-control finding look stronger than it is; the finding stands on the non-overlapping
effort figures above, which do not depend on it.)*

Three categories land on `INSUFFICIENT_EVIDENCE` because their effort difference rests on a
**single divergent run** — exactly the condition §6 of the pre-registration says must be reported
as insufficient rather than banked as a finding. In each case the two runs of the same arm differ
more than the two arms differ (e.g. T5 Arm B: 44 then 24; T7 Arm B: 37 then 18). **Agent-to-agent
variance in this benchmark is larger than the tool effect.** That is itself the most robust
quantitative result here.

### The one `GRAPHIFY_HELPFUL`, and why it should not be over-read

Category C (T3, schema-version blast radius) is the only category meeting the pre-registered
`HELPFUL` bar: Arm B was consistently more correct (found `export.py:23`'s second, independent
`ISAAC_VERSION` constant in **both** runs; Arm A missed it in **both**, once asserting the
opposite) *and* used 16.7% fewer tool calls, with no rise in dead ends.

**But the mechanism is not Graphify, by Arm B's own account in both runs:**

- run 1: *"graphify … never surfaced `official.py`, `export.py`, or `db_recon`'s `schema_authority`
  — the highest-value load-bearing files were found via targeted grep for the version literal."*
- run 2: *"it didn't reveal the `export.py`/`official.py` constant duplication … those came from
  targeted rg greps."* This run additionally logged Graphify as a **dead end** on exactly that
  question: *"returned mostly AST containment edges … with no cross-file import edges to
  `official.py` or `export.py`, so it couldn't answer the 'which modules import vs repeat'
  question by itself."*

The label is reported because the pre-registered rule produces it and retuning thresholds after
seeing data is forbidden. The honest reading is that **no causal path from Graphify to the win
exists in either transcript**, and at n=2 per arm this is not a result to build policy on.

---

## 3. Graphify's failure mode is reproducible, not incidental

The same query returns the same wrong node across independent runs. This is a property of the
index and its matcher, not agent noise.

| Query token | Node actually returned | Observed |
|---|---|---|
| `"preview"` (CSV reconcile) | `apps/web/src/components/ResetDemoDialog.tsx` | T2 run 1 **and** run 2 |
| `"version"` | `apps/web/package.json`'s `version` field | T4 run 1 |
| `"private"` | `apps/web/package.json`'s `"private": true` | pre-benchmark probe |
| `"If-Match"` | `X-Isaac-Tutorial-Session` cluster, not the precondition code | T4 run 1 **and** run 2 |

**Mechanism 1 — flat label space.** BFS start-node selection matches short, generic node *labels*.
Because the graph indexes JSON keys, package manifests, doc headings and AST identifiers in one
label space, a common English word resolves to whichever node happens to carry it — often a
`package.json` field or an unrelated UI component.

**Mechanism 2 — backend Python is systematically under-surfaced.** Across the benchmark, Arm B
agents reported that Graphify did **not** surface `export.py`, `official.py`, `serialize.py`,
`inferability.py`, `verification.py`, `disclosure.py`, `csv_ingest.py`, `routes.py`, `auth.py`,
`db_recon.schema_authority`, or `run_verification` — *even when those files were the answer*.
One transcript states it plainly: **"Python backend nodes were largely absent from the BFS result."**

**What Graphify did reliably surface:** documentation and TypeScript/frontend nodes —
`docs/project-memory-map.md`, `docs/deployment.md`, `docs/evidence/suggestion-safety-methodology.md`,
`CsvReconcilePanel.tsx`, `GuidedPrompt.tsx`, the schema-browser cluster. That is a genuine and
consistent capability.

**On the negative control it was a liability.** T6 asked for an exhaustive environment-variable
inventory. Graphify surfaced `docs/deployment.md`'s env-var table — which **omits at least a dozen
of the required variables**. The agent caught the incompleteness; an agent that trusted the lead
would have failed the task. A documentation-shaped answer to a completeness question is worse than
no answer.

---

## 4. Operational cost — measured, and never netted against per-task gains

| Item | Measurement | How |
|---|---|---|
| Full reindex at HEAD | **10.04 s** | `/usr/bin/time -p graphify update .` |
| External model calls for reindex | **0** | tool reports "no LLM needed"; no API key configured |
| Lifetime external-model cost of this graph | **1 invocation, ever** (2026-07-06, 89,405 input tokens) | `graphify-out/cost.json`, identical across all 6 dated copies |
| Query latency | **~0.6 s** (0.57–0.69 s over 4 queries) | wall-clock around `graphify query` |
| Graph size at HEAD | 10,618 nodes / 18,849 edges / 585 communities | tool output |
| **HTML visualisation** | **no longer generates** | tool refuses: 10,618 nodes exceeds its own 5,000-node limit |
| **Observed staleness in real use** | **420 commits / 529 changed files** | index found at `caab1d0` (2026-07-18) vs HEAD `9df2ef7` (2026-08-07) |

Indexing is cheap. **Maintenance discipline is the real cost, and in this project's actual history
it was not paid**: the graph was 420 commits stale when this work began. Regeneration requires a
user-local `graphify` binary that CI cannot obtain, so nothing automated can close that gap.

The benchmark deliberately gave Graphify the *most favourable* condition — a fresh index built at
the exact commit under test. The results above are therefore an **upper bound** on its value in
this repository, not a typical-day estimate.

---

## 5. Threats to validity

- **Wall-clock is contaminated and was excluded from every verdict.** Run 1 launched 16 agents
  concurrently; an Arm B agent independently detected the contention (found a competing process in
  `ps aux`) and honestly reported the elevated time it measured rather than "correcting" it. Run 2 used
  8-agent waves and times dropped sharply (T1 Arm B: 186 s → 89 s) — confirming the effect. Tool
  calls, files opened, tokens and dead ends are unaffected by CPU contention and carry the verdicts.
- **Agent variance exceeds the tool effect** (§2). This is the dominant limitation. Two runs per
  arm detect only large, consistent differences.
- **n = 8 tasks, one repository.** Conclusions are about this codebase's shape — Python + TypeScript,
  doc-heavy, history-heavy — and do not automatically transfer.
- **This repository is unusually self-documenting**, which compresses any measurable gap: several
  answers are stated in prose inside the very files an agent must find (T8's lure is corrected by
  `inferability.py`'s own docstring; T5's rationale sits in `disclosure.py`'s docstring). Both arms
  converge once the right file is open, so most tasks became location races, not reasoning races.
  The benchmark designer flagged this risk in advance, before results existed.
- **One harness failure, excluded not hidden.** The orchestrator initially wrote the task file to
  the main repo rather than the pinned worktree. One Arm A run hit it, correctly refused to invent
  an answer, and was relaunched. Its metrics are excluded and marked in the raw results.
- **Grading is not fully blind**: transcripts that mention a tool by name reveal their arm. Grading
  was anchored on file-level evidence against gold to blunt this.

---

## 6. Observational evidence — reported separately, and it does not establish efficacy

A parallel review of how Graphify has actually been used in this repository's history (kept apart
from the controlled results above, per §7 of the methodology):

**Well-supported by mechanical evidence:**
- The truth/memory boundary is **genuinely enforced, not merely documented**: three separate tests
  assert via `sys.modules` that the truth core never imports `graphify`
  (`tests/test_export.py:170`, `tests/test_e2e.py:112-116`, `tests/test_extract_interface.py:30-38`),
  and they run in CI.
- The external model was invoked **exactly once, ever**; every later update reused cached labels.
- The point-in-time, disclosed, non-blocking freshness policy is deliberate and documented.

**Claimed but not demonstrated:**
- **No commit, plan document, or report in this repository's history cites a Graphify query as the
  means by which something was discovered.** 52 Graphify-related commits (measured: `git log --all -i --grep=graphify`) are maintenance and
  infrastructure. `docs/query-demo.md` and `docs/query-cookbook.md` contain worked transcripts, but
  they read as illustrative documentation, not "we ran this and learned something we didn't know."
- The long-standing "dangling/collapsed semantic edges from AST/semantic ID mismatch" caveat in
  `CLAUDE.md` §7 has **no measured instance** anywhere in the repo; the sources for it are
  mutually-citing prose. (A *different*, real staleness defect **was** measured — a renamed symbol
  `_validator_for` → `_checked_schema_text` persisting in the deep graph artifact — but it is a
  staleness bug, not the AST-collapse the caveat names. The two should not be conflated.)
- Graph freshness is **not gated in CI**. `scripts/check_graphify_freshness.py` is exercised only
  by its own unit test; no standalone CI step runs it.

**A naming hazard worth recording:** `dangling_link_count` in `db_recon`/`authorization.py` and
`CLAUDE.md` §15 concerns **Postgres record-to-record links**, an unrelated subsystem. It is easily
misread as the Graphify dangling-edge caveat. They are different things.

**Note on the shipped product:** the deployed app never reads a live graph. `graphify-out/` is
gitignored and excluded from the Docker COPY allowlist, so the hosted Project Memory screen always
serves the committed 220-node snapshot. Nothing in this benchmark bears on that feature's
correctness — only on Graphify as a *developer navigation tool*.

---

## 7. By-product findings (real repository defects surfaced by the benchmark)

These are outputs of the work, independent of the Graphify question:

1. **Two independent schema-version constants with no test pinning them equal.**
   `official.EXPECTED_VERSION` and `export.ISAAC_VERSION` are separate literals; `export.py` does
   not import from `official.py`, yet `ISAAC_VERSION` is what stamps `isaac_record_version` on
   every record (`export.py:134`) and `schema_version` on every sidecar (`export.py:252`). Verified
   directly. A desync would be caught only indirectly, by every export failing the official gate.
   **Recommend a one-line regression test.**
2. **The `_histogram` single-key disclosure gap** (independently rediscovered by a benchmark agent
   that knew nothing about it) — found, reproduced synthetically, and fixed in the same session.
3. **Public-reference determinism confirmed three independent times** — orchestrator, Arm A, Arm B
   — with byte-identical values for every field except `generated_at`/`duration_ms`/
   `cache_age_seconds`. Incidental: `repeat=2` and `repeat=3` produce identical reported scalars.

---

## 8. Recommended routing policy (evidence-backed)

Derived from §2–§4. The standing hard rule is unchanged and reinforced by every run:
**Graphify returns leads; the actual files remain the source of truth.**

### Use Graphify first for
Nothing. **No task category in this benchmark showed a correctness or efficiency gain that
survives its own error bars.** Recommending it as a first step would not be supported by the
measurements.

### Use Graphify optionally for
- **Orienting in unfamiliar documentation** — locating which `docs/` file discusses a concept.
  This is the one capability it demonstrated consistently (it reliably surfaced
  `project-memory-map.md`, `deployment.md`, `suggestion-safety-methodology.md`).
- **Frontend/TypeScript neighbourhood discovery** — it surfaced React components and TS types
  more readily than backend Python.

In both cases treat the output as a pointer to a *document*, and verify in source before asserting.

### Do not use Graphify for
- **Exhaustive or exact-string inventories** (env vars, every call site, every occurrence).
  Measured `GRAPHIFY_HARMFUL`: +26% effort, +19% tokens, no accuracy gain, and it answers
  completeness questions with incomplete documentation. **`rg` is strictly better.**
- **Locating backend Python implementation.** It systematically failed to surface `export.py`,
  `official.py`, `serialize.py`, `verification.py`, `disclosure.py`, `csv_ingest.py`, `routes.py`,
  `auth.py` — even when those were the answer.
- **Import/dependency questions** ("which modules import X vs re-declare it"). Logged explicitly as
  a dead end: the graph returned AST containment edges with no cross-file import edges.
- **Runtime or truth-path verification.** Only running the code answers it; the graph pointed at
  neighbouring test modules instead of the entry point in both runs.
- **Disambiguating similarly-named concepts.** Short generic tokens (`preview`, `version`,
  `private`) reliably resolve to `package.json` fields or unrelated components.

### Practical note on cost
Reindexing is cheap (**10 s, no model call**). If Graphify is kept, run `graphify update .` before
relying on it — the index in this repository was **420 commits stale** when this benchmark began,
and nothing in CI can refresh it. A stale graph is worse than no graph, because its answers look
authoritative.

### Honest bottom line
This benchmark does not support the current `CLAUDE.md` §7 instruction to *"use Graphify before
answering architecture/codebase questions."* That instruction presumes a benefit the measurements
do not show. The narrower role the evidence supports is: **an optional documentation-orientation
aid, never a first step, never for exhaustive or backend-code questions.**

Nothing here bears on the *shipped* Project Memory feature, which serves a committed snapshot and
never reads a live graph.

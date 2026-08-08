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

> **Three disclosure limits a reader should carry into every number below.** (1) Seven metrics
> declared in the pre-registration were never collected — enumerated, with their effect on each
> verdict, in **§5**. (2) The gold answer sets were used to grade correctness but **were never
> committed**, so correctness grading is **not independently auditable**; §6 says so in full and
> marks, claim by claim, which correctness statements a reader can check for themselves and which
> they cannot. (3) **One category verdict (T8) sits outside the band its own label requires** — a
> deviation from mechanical application of the pre-registered rules, recorded in **§2** and left
> uncorrected on purpose. None of the three changes a measured figure, and the conclusions stand on
> what was measured — but none should be discovered late.

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

Applied mechanically from the pre-registered §5.3 rules — **with one exception, disclosed
immediately below the table: T8's label does not meet its own stated condition.** Effort is measured
in **tool calls**; wall-clock is excluded as contended (see §6).

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

### Recorded deviation: T8's label sits outside its own band

Found while auditing this document against the pre-registration, and recorded here rather than
quietly corrected.

**T8 is labelled `GRAPHIFY_NEUTRAL`, but it does not meet the stated condition for that label.**
`GRAPHIFY_NEUTRAL` under §5.3 requires "correctness equal and effort **within ±15%**". T8's measured
effort change is **−16.3%**, outside the band, and Arm B was faster in **both** runs, not just at the
median:

| T8 | run 1 | run 2 | median |
|---|---|---|---|
| Arm A tool calls | 23 | 20 | 21.5 |
| Arm B tool calls | **21** | **15** | **18.0** (−16.3%) |

Correctness is a tie (T8 is the one task where all four runs carry a correctness annotation).
**Applied literally, §5.3 yields `GRAPHIFY_HELPFUL`** — "correctness equal or better, AND a material
median improvement in time or tool effort (≥15%), without a countervailing rise in false leads."
It does not reach `GRAPHIFY_STRONGLY_HELPFUL`, which needs ≥30%.

**The justification that would make `NEUTRAL` correct exists, and it is the final clause of the
`HELPFUL` rule** — *"without a countervailing rise in false leads."* Dead ends did rise on Arm B:

| T8 dead ends | run 1 | run 2 | total | median |
|---|---|---|---|---|
| Arm A | 1 | 1 | **2** | 1.0 |
| Arm B | 3 | 1 | **4** | 2.0 |

A doubling of both the total and the median is a defensible reading of "countervailing rise", which
would disqualify `HELPFUL` and leave `NEUTRAL` as the nearest label.

**But that reasoning was never stated at the time, and it is being recorded now rather than presented
as the original rationale.** Two things weaken it, and both belong in the record:

- **`dead_ends` is a proxy, not the declared metric.** §5.2's quality metric is "count of
  false-positive leads pursued", graded against gold's false-lead list — one of the metrics never
  collected (§5). Neither T8 Arm B run carries any false-lead flag (`graphify_false_lead`,
  `reproducible_false_lead`, `graphify_incomplete_doc_lead`, `graphify_steered_to_gold_false_lead`),
  unlike T2, T4, T5 and T6. So no *Graphify-attributed* false lead was recorded on T8 at all.
- **The same clause was stated explicitly one category earlier.** The `GRAPHIFY_HELPFUL` finding for
  T3 is justified in §2 as holding "with no rise in dead ends" — and that checks out (T3 dead ends:
  Arm A 2+2=4, Arm B 3+1=4; medians 2.0 and 2.0). The clause was therefore in active use. Its
  silence on T8 is an omission, not a convention of the document.

**The deviation is conservative in direction — and a conservative deviation is still a deviation.**
Mislabelling T8 understates Graphify: it withholds a `HELPFUL` the rules would have granted, so no
finding in this document is inflated by it, and §9's routing policy is if anything stricter than the
data requires. That is not a defence. The pre-registration's entire claim to credibility is that the
rules were fixed in advance and applied **mechanically**; a verdict silently sitting outside its own
band undercuts that claim regardless of which way it errs, and a reader who checks the arithmetic
should find the discrepancy already disclosed rather than discover it unaided.

**The label is left as it stands.** Re-deciding a verdict after seeing the data is precisely what
§5.3's "not to be retuned afterwards" forbids, and re-labelling now — with full knowledge of the
result — would be a worse breach than the original omission. The honest remedy for an unstated
deviation is to state it, not to re-run the decision.

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

## 5. Declared but not measured

The methodology was **pre-registered**, and §5.2 of it declared a metric list before any arm ran.
**Seven of those declared measurements were never collected, and one only partly.** Declaring a
measurement and then reporting only the subset that was taken — without saying so — is precisely
the selective-reporting failure that pre-registration exists to prevent. This section is the
accounting. Nothing below is retro-fitted: no value is estimated, reconstructed, or measured after
the fact and presented as if it had been collected during the runs.

**The conclusions in §1–§4 and §9 stand on what was measured.** No verdict in §2 was computed from
any uncollected metric: §5.3 of the pre-registration keys on correctness, tool-call effort, and
false leads, all three of which were recorded. What the gaps remove is (a) a reader's ability to see
*how* the correctness judgement was reached, and (b) any chance of detecting a Graphify benefit that
the three reported measures are blind to. Both are stated per metric below.

| Declared in §5.2 | Collected? | Why not | Could its absence change a category verdict? |
|---|---|---|---|
| conclusion correctness | **yes** (17/32 runs annotated) | — | it *is* the gate; see §6 for what a reader can audit |
| **required-file recall** | **no** | The harness wrote one conclusion-level outcome per run into `graphify-run-results.json` and nothing else. Re-deriving it now would need the gold evidence sets, which were not committed (§6) | **Yes — Category C.** See (a) below |
| **evidence completeness** | **no** | same as above | **Yes — Category C.** See (a) below |
| count of false-positive leads pursued | **partly** | Recorded as boolean flags (`graphify_false_lead`, `reproducible_false_lead`, `graphify_incomplete_doc_lead`, `graphify_steered_to_gold_false_lead`) plus an integer `dead_ends`, never as a count graded against gold's `common_false_leads` list | No — the flags and `dead_ends` are what the §5.3 false-lead limb was applied to, and both are committed |
| **unsupported claims** | **no** | same as required-file recall | Not directly; §5.3 has no unsupported-claims limb. Indirectly via §5.4, which folds them into correctness |
| **missed relationships** | **no** | same as required-file recall | Not directly; same indirect route as above |
| elapsed wall-clock | **yes** (`duration_ms`) | — | excluded from every verdict as CPU-contended (§6), which is disclosed, not silent |
| tool calls | **yes** | — | this is the effort measure every verdict uses |
| files opened | **yes** | — | headline only; not a §5.3 input |
| **irrelevant files opened** | **no** | Requires a per-run trace of *which* files were opened, classified against gold's required-file list. The harness captured only the integer `files_opened`; no file-open trace exists | Not mechanically — but it is the gap most likely to have favoured Graphify. See (b) below |
| Graphify query count | **yes** | — | no |
| **downstream verification calls** | **no** | Requires per-tool-call classification (was this call confirming a graph lead, or primary discovery?). The harness captured only the integer `tool_uses`, with no per-call log or timestamps | No — not a §5.3 input. See (c) below |
| tokens | **yes** | — | no |
| index build / refresh time | **yes** (10.04 s) | — | no |
| query latency | **yes** (~0.6 s) | — | no |
| **storage** | **no** | Simply never measured. §4 reports node and edge counts (10,618 / 18,849) in its place; bytes on disk were never taken, and are deliberately **not** measured now — a figure taken today would come from a differently-built index at a different HEAD | **No, by construction.** See (d) below |
| staleness risk | **yes** (420 commits) | — | no |
| maintenance burden | **qualitatively** | — | no |

### (a) Required-file recall and evidence completeness — the one place a verdict is genuinely at risk

§5.4 of the pre-registration scores an arm that reaches the right conclusion **without citing the
files that establish it** as *not correct*. Recall and evidence completeness are therefore
constituents of the correctness judgement, and correctness gates every verdict under §5.1. Neither
was recorded per run.

**Category C (T3) is the exposure.** Its `GRAPHIFY_HELPFUL` label requires "correctness equal or
better". If Arm B's required-file recall had been graded and found materially worse, that premise
fails and C drops to `GRAPHIFY_NEUTRAL` or below.

**This is not a hypothetical.** The committed raw data already records a recall deficit on the Arm B
side: T3 Arm B run 1 carries a `missed_vs_armA` field listing 34 fixtures (including
`qa/validator-upload-package`'s 17 and `tests/fixtures/truthpath`'s 5) and the hand-maintained
`rule_family_coverage.json` ledger — all found by Arm A and missed by Arm B. Arm A run 2 in turn
missed `export.py:23` and asserted the opposite. **Both arms had recall gaps, in opposite
directions, and the metric that would have netted them was not collected.**

The label is left as the pre-registered rule produced it, because retuning after seeing data is
forbidden and because the rule was applied to the correctness evidence that *was* recorded. But §2
already warns C should not be over-read on mechanism grounds, and this is a second, independent
reason: **had the declared recall metric been collected, C is the verdict most likely to have moved,
and the committed hints point toward neutral rather than more helpful.**

**Category F (T6) is the other place §5.3 mentions a quality gain — and its verdict survives.**
`GRAPHIFY_HARMFUL` has three independent limbs, and F satisfies two. A graded quality gain for Arm B
would have been the "compensating quality gain" that defeats the *effort* limb. But the *false-lead*
limb stands on its own: Arm B run 1 is flagged `graphify_incomplete_doc_lead` and no Arm A T6 run
carries any false-lead flag. And the direction of the unmeasured quality effect is not open here —
Graphify's actual T6 contribution was a documentation table omitting at least a dozen required
variables, a quality *liability*, not a gain. **F is robust to this gap.**

The three `INSUFFICIENT_EVIDENCE` categories are also robust: that label is triggered by two runs of
the same arm disagreeing, and the disagreement is in the committed integers.

### (b) Irrelevant files opened — the gap most likely to have favoured Graphify

Named explicitly rather than buried, because honest disclosure has to cut both ways. Arm B opened
**fewer files overall** (median 8.0 vs 9.5, −15.8%). That is consistent with — though it does not
demonstrate — Graphify steering agents away from irrelevant files, which is exactly what the
declared "irrelevant files opened" metric would have tested. It was not collected.

Because §5.3's effort measure is **tool calls**, a favourable result here could not mechanically
change any category label. It would, however, bear on §9's *"Use Graphify first for: Nothing"*, which
rests on no measured gain surviving its error bars. **A reader should treat that recommendation as
resting on the measures that were taken — not as the outcome of a search that ruled this one out.**

### (c) Downstream verification calls

Declared to capture whether a Graphify lead forces extra confirmation work. Uncollected, and
uncollected in *both* directions: it could have supported §9's conclusion (leads costing extra
verification) or undercut it (leads confirmed cheaply). It is not a §5.3 input, so no category label
depends on it.

### (d) Storage

Cannot change any category verdict **by construction**: §5.2 requires operational overhead to be
reported separately and never netted against per-task gains, and category verdicts are per-task.
It bears only on §4 and on the overall keep-or-retire question — where §4's conclusion ("indexing is
cheap; maintenance discipline is the real cost, and it was not paid") does not depend on bytes on
disk.

---

## 6. Threats to validity

### The gold answers were never committed — correctness grading is not independently auditable

This is the most serious limitation in the package, and it is placed first for that reason.

Methodology §4.2 specifies that for each task a gold record holds the required files, relevant
symbols, required relationships, the expected conclusion, and known false leads, built by a separate
evaluator working without Graphify. **Those gold records were built, and they were used to grade
every run. They were never committed.** `graphify-task-set.json` contains only `id`, `category`,
`prompt`, `expected_difficulty` and `is_misleading_semantic_probe` — the questions, not the answers.

They cannot be recovered after the fact, and this package **will not reconstruct them**: a gold set
written now, by someone who has seen the results, is not a gold set. The gap is recorded rather than
filled.

What follows:

- **Correctness is the metric that gates every category verdict** (§5.1: correctness dominates every
  efficiency gain, and a category where Arm B is materially less correct cannot rank above
  `GRAPHIFY_HARMFUL` regardless of speed). It is also the one metric a reader cannot re-derive from
  what is committed.
- Every correctness claim in this document therefore weakens to **"as graded — unverifiable by a
  reader"**, except where the table below marks it otherwise.
- **Only 17 of the 32 runs carry any correctness annotation at all** (`graded`, `probe_correct`,
  `unique_correct_find`, or `possible_wrong_answer`), and they are not evenly spread: **13 of 16
  run-2 records are annotated, but only 4 of 16 run-1 records.** Where a "both correct ×2" claim
  rests on an unannotated run, a reader has nothing at all to check it against.
- **Two annotations quote gold directly** and are unverifiable for the same reason: T5 Arm B run 2's
  `graphify_steered_to_gold_false_lead` flag with its note that "gold lists db_recon as the #1
  common_false_lead for T5", and the T3 `graded` strings describing `export.py:23` as the "gold #1
  item". The *ranking* in both cases is an appeal to an uncommitted document.
- Grading was also **not fully blind** (transcripts naming a tool reveal their arm); it was anchored
  on file-level evidence against gold to blunt this. With gold uncommitted, a reader cannot check
  that anchoring either.

#### Which claims a reader can check, and which they cannot

| Claim | Reader-checkable? | Basis |
|---|---|---|
| Headline medians and totals (§1); per-category tool-call medians and deltas (§2) | **Yes, fully** | Recomputable from `graphify-run-results.json` alone |
| Category F non-overlapping distributions — 39, 42 vs 48, 54 tool calls; 105,516 · 103,478 vs 122,741 · 126,738 tokens (§2) | **Yes, fully** | Same file. The `GRAPHIFY_HARMFUL` effort evidence needs no gold |
| `graphify_helped` never once "yes" — 13 partly, 3 no, falling in three *different* tasks T4/T5/T6 (§1, §2) | **Yes, fully** | Same file |
| Reproducible false-lead table (§3) | **Yes, as recorded** — not reproducible | The flags and notes are committed, so a reader can verify *that the runs recorded it*. They cannot re-run the queries: `graphify-out/` is gitignored, so the index is not in the package |
| **T3 — "Arm B better, 2/2 vs 0/2"** | **Partly** | Arm B's **2/2: yes** (run 1 `unique_correct_find` names `export.py:23`; run 2 `graded` reads "FOUND export.py:23"). Arm A's **0/2: run 2 only** (`graded`: "MISSED export.py:23 … Asserted the OPPOSITE"). **Arm A run 1 carries no correctness annotation**, so half of "0/2" rests on uncommitted gold |
| **T3 — the underlying finding itself** | **Yes, fully, in source** | Verified directly against the committed tree while writing this section: `official.py:23` holds `EXPECTED_VERSION = "1.05"`; `export.py:23` holds a second, independent `ISAAC_VERSION = "1.05"`; `export.py` imports only `OfficialReport, validate_official` from `.official`, **not** the constant; and it stamps `ISAAC_VERSION` at `export.py:134` and `export.py:252`. This is the strongest claim in the package and it needs no gold at all |
| **T5 — "tie after both runs"** | **Partly** | That Arm B run 1 diverged **is** checkable (`possible_wrong_answer`, verbatim; run 2's `graded` says "run1 ArmB got this WRONG"). Arm A run 2's `graded` is checkable as an annotation. **Arm A run 1 is unannotated.** *Which* shape is right was referred to gold — the `possible_wrong_answer` text literally says "GOLD MUST ADJUDICATE" — but the substance is independently supportable: `apps/api/isaac_api/disclosure.py`'s module docstring names the single-key map as the one case it cannot fix, under the heading "THE ONE CASE THIS CANNOT FIX, STATED RATHER THAN HIDDEN" |
| **T6 — "tie after both runs"** | **Partly** | Arm A run 2 and Arm B run 2 are `graded` CORRECT. **Arm A run 1 and Arm B run 1 carry no correctness annotation** — that Arm A run 1 had two errors is an inference from run 2's grader prose ("fixed BOTH run1 ArmA errors"), not a graded record of run 1 |
| **T6 — "the documentation table omits ~12 required variables"** | **Yes** | `docs/deployment.md` is committed and the omitted names are listed in the raw note. Spot-checked while writing this section: `PGSSLMODE`, `PGCONNECT_TIMEOUT`, `ISAAC_RUN_SLAC_DB_RECON`, `ISAAC_DB_RECON_ALLOW_RAW_IDS` and `ISAAC_RUNTIME_MODE` each appear **zero** times in `docs/deployment.md` while appearing elsewhere in the repository |
| **T8 — "tie (both correct ×2)"** | **Yes, fully** | The only task where all four runs carry a correctness annotation: `probe_correct` on both run 1s, `graded` on both run 2s |
| **T1 — "tie (both correct ×2)"** | **No** | **None of T1's four runs carries any correctness annotation.** This claim rests entirely on uncommitted gold |
| **T2, T4, T7 — "tie (both correct ×2)"** | **Partly** | T2: one of four runs annotated (Arm A run 2). T4 and T7: two of four (both run 2s). The run-1 halves rest on uncommitted gold. T7 has an independent route — Arm B run 1's note reports re-running `run_verification` and reproducing the orchestrator's figures exactly, which a reader can repeat |
| §4 operational figures (reindex 10.04 s, latency ~0.6 s, 420-commit staleness) | **Partly** | Single measurements with the commands named, not re-derivable from the package: they need the user-local `graphify` binary and a rebuild, and `graphify-out/` is gitignored |
| §7 observational claims (three `sys.modules` truth-core tests, one lifetime model invocation, 52 Graphify commits) | **Yes** | Given as `file:line` citations and a named `git log` command, all against committed artifacts |

**Read together with §5:** the categories whose correctness claim is weakest for a reader (T1, T2)
are `GRAPHIFY_NEUTRAL` and `INSUFFICIENT_EVIDENCE` — verdicts that assert no benefit. The two
categories carrying an actual directional finding, C and F, are the two with the most committed
correctness evidence, and F's is entirely effort-based and needs no gold.

### Other threats

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
  was anchored on file-level evidence against gold to blunt this — and because gold was not
  committed, a reader cannot check that anchoring either (see above).

---

## 7. Observational evidence — reported separately, and it does not establish efficacy

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

## 8. By-product findings (real repository defects surfaced by the benchmark)

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

## 9. Recommended routing policy (evidence-backed)

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

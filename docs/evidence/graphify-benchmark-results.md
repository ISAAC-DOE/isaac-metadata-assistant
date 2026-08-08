# Graphify Efficacy Benchmark — Results

**Methodology and pre-registered decision rules:**
[`graphify-benchmark-methodology.md`](graphify-benchmark-methodology.md) — **written** before any
arm ran and before any result was observed.
**Frozen task set:** [`graphify-task-set.json`](graphify-task-set.json).
**Raw per-run metrics:** [`graphify-run-results.json`](graphify-run-results.json).

> **The pre-registration ordering is asserted by the author, not witnessed by git.** An earlier
> revision of the line above read "written **and committed** before any arm ran". The word
> *committed* implied an independent, mechanical check that does not exist, and it is withdrawn.
> All four artifacts of this package — methodology, results, `graphify-run-results.json` and
> `graphify-task-set.json` — first appear together in **one commit, `35c4cbb`** (2026-08-07
> 18:56 −0700; verified with `git show --stat 35c4cbb`, which lists all four). The methodology has
> never existed in a commit that did not also contain the results, so git cannot corroborate that
> it was written first. The methodology's own header claims only that it was *written* before any
> arm executed; that is the claim this package makes, and it rests on the author's word.
>
> **What a reader *can* check mechanically — and it holds: no decision rule or category label was
> changed after results existed.** `git diff 35c4cbb..HEAD -- docs/evidence/graphify-benchmark-methodology.md`
> shows the only edits since that commit are §4.2's post-run correction, §5.2's collection-status
> column, the new §5.2a, and a change-log row — all disclosure, none of them a rule. **§5.1 (the
> correctness gate) and §5.3–§5.4 (category classification and negative-control protections) are
> byte-identical between `35c4cbb` and HEAD**, confirmed by extracting each section from both
> revisions and comparing digests (§5.1 `sha256 36d79d50…` in both; §5.3–§5.4 `sha256 99b163fa…`
> in both). The rules every verdict below was computed from are the rules as first committed.

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

> **Footnote on the percentages in this table.** Two of these rows are medians of small integers
> over 16 observations per arm, and a percentage on such a median is a comparability aid, not a
> measure of effect size. Dead ends move **1.5 → 1.0**, which is a difference of half a dead end
> per run and prints as −33.3%; files opened move **9.5 → 8.0** and print as −15.8%. Read the raw
> medians first and the percentages second. All figures are recomputed from
> `graphify-run-results.json` (32 records, 16 per arm).

Graphify-assisted agents spent **slightly more** effort overall and opened somewhat fewer files.
**Both token figures, because the two point in different directions:** the *median* run cost
+0.5% (94,614 → 95,093) while the *total* across all 16 runs per arm cost **+4.2%**
(1,568,835 → 1,634,044) — the totals diverge more than the medians because Arm B's expensive runs
were more expensive than Arm A's. Quoting only "level to within 0.5%", as an earlier revision of
this line did, selects the friendlier of two numbers printed in the same table. Nothing here is a
material efficiency gain in either direction.

**The qualitative result is stronger than the numeric one.** Across **16 Arm B runs, the agents'
own self-assessment `graphify_helped` was never once "yes"** — 13 × "partly", 3 × "no". In every
run where Arm B reached the answer, its own notes credit `rg`/`grep`, not the graph.

Correctness after both runs: **7 ties and 1 consistent Arm B advantage** (task T3).

> **Three disclosure limits a reader should carry into every number below.** (1) Seven metrics
> declared in the pre-registration were never collected — enumerated, with their effect on each
> verdict, in **§5**. (2) The gold answer sets were used to grade correctness but **were never
> committed**, so correctness grading is **not independently auditable**; §6 says so in full and
> marks, claim by claim, which correctness statements a reader can check for themselves and which
> they cannot. (3) **The §5.3 rules were not applied purely mechanically in five of the eight
> tasks** — not because any label is wrong, but because in each case a rule limb was left
> unadjudicated or a rationale unstated. All five are enumerated in **§2, "Recorded deviations from
> mechanical application"**, with the direction each one cuts. **No label is changed**, because
> re-deciding a verdict after seeing the data is what §5.3's "not to be retuned afterwards"
> forbids. None of the three limits changes a measured figure, and the conclusions stand on what
> was measured — but none should be discovered late.

**One correction, because an earlier draft of this document overstated it.** That draft said
"Graphify never reduced correctness". That is contradicted by data shipped in this same
package: on T5 run 1, Arm B named the wrong "unprotectable shape" and is recorded as
`possible_wrong_answer` in `graphify-run-results.json`, with the run-2 entry stating verbatim
that "run1 ArmB got this WRONG". Arm A was correct on that item in **both** runs.

The accurate statement is narrower: **Arm B produced one wrong answer that Arm A did not, and
Arm A produced one wrong answer that Arm B did not** (T3's missed `export.py:23`, missed in
both Arm A runs). Arm B's T5 miss did not repeat in run 2 and is best read as within-arm
variance — the same reading applied to Arm A's T6 run-1 errors, which also did not repeat.
It was not demonstrated to raise correctness either.

**And the sentence that used to close this paragraph was itself a deviation, so it is retracted
rather than quietly deleted.** It read: *"Under the §5.1 gate Graphify still passes, because no
category shows a **sustained** correctness decline."* **The word "sustained" appears nowhere in
the pre-registration.** §5.1 (`methodology.md:134-137`) says correctness "**materially below**",
with no durability qualifier and no requirement that a decline repeat across runs. Substituting a
stricter test than the one that was pre-registered, at the exact point where T5's Arm B run-1 wrong
answer would otherwise have to be adjudicated, is a post-hoc softening of the gate. It is recorded
as such in §2 under T5. The T5 label is left unchanged for the reason given there.

---

## 2. Category verdicts

Computed from the pre-registered §5.3 rules. **The application was not purely mechanical in five of
the eight rows below**, and every departure is enumerated after the table under "Recorded deviations
from mechanical application". Effort is measured in **tool calls**; wall-clock is excluded as
contended (see §6).

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

### Recorded deviations from mechanical application

Found while auditing this document against the pre-registration, and recorded here rather than
quietly corrected. **Five of the eight tasks in the table above are affected** (four distinct
categories — T4 and T8 both sit in category D). **No label is changed by this section** —
re-deciding a verdict with full knowledge of the result is exactly what §5.3's "not to be retuned
afterwards" forbids, and would be a worse breach than the omissions being disclosed. The
honest remedy for an unstated deviation is to state it, not to re-run the decision.

**Direction is given for each, because a disclosure that hides which way it cuts is not a
disclosure.** Three of the five (T5, T4, T7) leave Graphify better off than a strict reading would
have; two (T8, T2) leave it worse off. The net is not the point. The point is that the
pre-registration's entire claim to credibility is that the rules were fixed in advance and applied
**mechanically**, and a reader who checks the arithmetic should find each departure already
disclosed rather than discover it unaided.

#### T8 (Cat D, misleading probe) — the label is correct; the *rationale* was never stated

**An earlier revision of this document asserted that T8's `GRAPHIFY_NEUTRAL` label "sits outside its
own band". That assertion was wrong, and it was wrong because it truncated the rule it quoted.** It
said `GRAPHIFY_NEUTRAL` "requires 'correctness equal and effort **within ±15%**'". The pre-registered
rule (`methodology.md:197-198`) is **disjunctive**:

> **`GRAPHIFY_NEUTRAL`** — correctness equal and effort within ±15%, **or gains and losses that
> cancel.**

Stopping the quotation before "or", and adding the word "requires", converted a two-limb disjunction
into a single condition and manufactured a deviation that does not exist. **The recorded verdict
`GRAPHIFY_NEUTRAL` is correct under the rules as written.** What was actually missing is the
rationale, which is supplied here.

The measured figures, recomputed from `graphify-run-results.json`:

| T8 | run 1 | run 2 | median |
|---|---|---|---|
| Arm A tool calls | 23 | 20 | 21.5 |
| Arm B tool calls | **21** | **15** | **18.0** (−16.3%) |
| Arm A dead ends | 1 | 1 | 1.0 (total 2) |
| Arm B dead ends | **3** | 1 | **2.0** (total 4) |

Correctness is a tie — T8 is the one task where all four runs carry a correctness annotation.

**Why `GRAPHIFY_HELPFUL` is disqualified, by two independent routes.**

1. **The `HELPFUL` rule's own final clause.** `GRAPHIFY_HELPFUL` (`methodology.md:195-196`) requires
   "correctness equal or better, AND a material median improvement in time or tool effort (≥15%),
   **without a countervailing rise in false leads**." Arm B's effort improvement clears the bar at
   −16.3%, but dead ends rose from a median of 1.0 to 2.0 and a total of 2 to 4 — a doubling of
   both. That is a countervailing rise, and the clause is conjunctive, so `HELPFUL` fails on its own
   terms.
2. **§5.4's amplifier, which was pre-registered for exactly this task.** T8 is the **only** task
   flagged `"is_misleading_semantic_probe": true` in `graphify-task-set.json` (verified: the other
   seven are `false`). §5.4 (`methodology.md:208-209`) pre-registers that "on the misleading
   semantic probe, pursuing a plausible-but-wrong lead is scored as a false positive **even if the
   agent eventually recovers**. Recovery cost is real cost." T8 is therefore the one task where the
   false-lead limb is *strengthened* rather than weighed, and Arm B's three run-1 dead ends against
   Arm A's one are counted in full regardless of Arm B reaching the right answer.

**Why `GRAPHIFY_NEUTRAL` is reached: limb 2, "gains and losses that cancel."** A −16.3% effort gain
set against a doubling of false leads on the task specifically designed to detect false leads is the
paradigm case of gains and losses cancelling. `NEUTRAL` is not a fallback here; it is the limb that
fits.

**One caveat on the evidence for that reasoning, and it is a real one:**

- **`dead_ends` is a proxy, not the declared metric.** §5.2's quality metric is "count of
  false-positive leads pursued", graded against gold's false-lead list — one of the metrics never
  collected (§5). Neither T8 Arm B run carries any false-lead flag (`graphify_false_lead`,
  `reproducible_false_lead`, `graphify_incomplete_doc_lead`, `graphify_steered_to_gold_false_lead`),
  unlike T2, T4, T5 and T6. So no *Graphify-attributed* false lead was recorded on T8 at all, and
  the "countervailing rise" above rests on the proxy integer, not on the declared measure.
- **The clause was in active use elsewhere in this document**, which is why its silence on T8 was an
  omission rather than a convention: the `GRAPHIFY_HELPFUL` finding for T3 is justified below as
  holding "with no rise in dead ends", and that checks out (T3 dead ends: Arm A 2+2=4, Arm B 3+1=4;
  medians 2.0 and 2.0).

**Direction:** against Graphify. `NEUTRAL` is the less favourable of the two candidate labels, so no
finding in this document is inflated by it and §9's routing policy is, if anything, stricter than
this category requires.

#### T5 (Cat E) — the §5.1 gate was softened by a word that is not in the pre-registration

**The recorded label is `INSUFFICIENT_EVIDENCE`. The §5.1 correctness gate was live and was
answered with a test that was not pre-registered.**

Measured: Arm A tool calls 25, 25 (median 25.0); Arm B 44, 24 (median 34.0) — **+36.0%**. Arm B run 1
carries `possible_wrong_answer` (it named the wrong "unprotectable shape"); Arm B run 2's `graded`
field states verbatim that "run1 ArmB got this WRONG". Arm B run 2 additionally carries
`graphify_steered_to_gold_false_lead`. Arm A run 2 is `graded` "CORRECT — named the SINGLE-KEY
shape"; **Arm A run 1 carries no correctness field at all**, only a note describing that it
independently rediscovered the disclosure gap, so its correctness — like most run-1 records — rests
on uncommitted gold (§6). Taking the annotations at face value, the raw data shows **Arm B 1/2
correct against Arm A 2/2**, at **+36% effort**, with a Graphify-attributed steer toward gold's own
#1 false lead.

§5.1 (`methodology.md:134-137`) says: "If Arm B's correctness is **materially below** Arm A's in a
category, that category cannot be classified better than `GRAPHIFY_HARMFUL` regardless of speed."
The defence offered in §1 was that "no category shows a **sustained** correctness decline".
**"Sustained" appears nowhere in the pre-registration.** §5.1 contains no durability qualifier and
does not require a decline to repeat across runs. Reading one in is a post-hoc narrowing of the gate,
applied at the single point in the benchmark where the gate would otherwise bind. That sentence has
been retracted in §1.

The substantive argument for treating the run-1 miss as within-arm variance is not worthless — Arm A
also produced a non-repeating error on T6, and the same reading was applied there. But it is an
argument made after seeing which way it needed to come out, and §5.1 was not written to admit it.

**Direction:** in Graphify's favour. A strict §5.1 application would force this category to no better
than `GRAPHIFY_HARMFUL`; `INSUFFICIENT_EVIDENCE` is more favourable than that.

#### T4 (Cat D) — the `HARMFUL` false-lead limb was live and was never adjudicated

**The recorded label is `GRAPHIFY_NEUTRAL`** on the strength of effort being within band: Arm A tool
calls 27, 20 (median 23.5); Arm B 27, 21 (median 24.0) — **+2.1%**, comfortably inside ±15%, with
correctness tied.

But `GRAPHIFY_HARMFUL` (`methodology.md:199-200`) is a three-limb disjunction — "correctness
declines, **OR false leads materially increase**, OR effort increases without a compensating quality
gain" — and **limb 2 was never addressed on T4.** Both Arm B runs carry `graphify_false_lead`, run 2
additionally carries `reproducible_false_lead`, and **neither Arm A run carries any false-lead
flag**. §3 of this very document headlines that failure as one of its two named mechanisms: the
`"If-Match"` query returned the `X-Isaac-Tutorial-Session` cluster instead of the precondition code
on **both** runs, and the `"version"` query collided with `apps/web/package.json`'s version field.
Arm B run 2 is also one of only three runs in the entire benchmark rated `graphify_helped: "no"`.

The countervailing evidence, stated so the omission is not overcorrected: the proxy integer moves
the other way. T4 dead ends are Arm A 3, 0 (median 1.5, total 3) and Arm B 2, 1 (median 1.5, total 3)
— **identical medians and identical totals**. So "false leads materially increase" is arguable on the
committed boolean flags and not supported by the committed counts, and the declared metric that
would have settled it (a false-positive count graded against gold) was never collected (§5).

That is precisely why it needed adjudicating rather than passing unmentioned. The limb was live, the
evidence pointed both ways, and the document reached `NEUTRAL` without saying so.

**Direction:** in Graphify's favour. Leaving limb 2 unadjudicated is what allows `NEUTRAL` to stand
uncontested.

#### T2 and T7 — `INSUFFICIENT_EVIDENCE` was applied without the third run its §5.3 definition names

`INSUFFICIENT_EVIDENCE` under §5.3 (`methodology.md:201-202`) reads: "runs within the category
disagree **and a third run does not resolve them**, or the task proved defective." §4.4
(`methodology.md:121`) commits that "a third run **is added** only for tasks whose two runs disagree
enough to leave a category verdict unstable."

**No third run was ever executed.** `graphify-run-results.json` holds exactly 32 records — verified:
every one of the 16 (task, arm) pairs has exactly 2 runs, and no record carries a `run` value above
2. Neither task proved defective. So the label's stated precondition was not met for **T2** (Arm A
39, 26 → median 32.5; Arm B 29, 26 → median 27.5, **−15.4%**, which would clear `HELPFUL`'s ≥15%
bar) or for **T7** (Arm A 25, 17 → median 21.0; Arm B 37, 18 → median 27.5, **+31.0%**, which would
engage `HARMFUL`'s effort limb). The same gap applies to **T5**, whose separate and more serious
issue is recorded above.

**There is an alternative route in the pre-registration, and it does apply — but it is a different
rule and was never cited.** §6 of the methodology (`methodology.md:226-227`) states: "Category
verdicts resting on a **single divergent run** are reported as `INSUFFICIENT_EVIDENCE` rather than as
a finding." Each of these three categories does rest on a single divergent run — T2 on Arm A run 1
(39 vs 26), T7 on Arm B run 1 (37 vs 18), T5 on Arm B run 1 (44 vs 24) — so §6 supports the label
independently of §5.3's third-run clause. **The labels therefore stand, but on §6's authority, not
on the §5.3 definition this document implied it was applying.** The distinction matters: §6 justifies
declining to bank a finding; it does not justify claiming the runs were tested for stability and
found unstable. They were not tested.

**Direction:** mixed, and stated rather than averaged. Withholding a verdict on **T7** (+31% effort
against Graphify, which would otherwise engage `HARMFUL`'s third limb) runs **in Graphify's favour**.
Withholding one on **T2** (−15.4%, which clears `HELPFUL`'s ≥15% bar) runs **against** it — though
`HELPFUL` would still have had to survive its false-lead clause, and both T2 Arm B runs carry
`graphify_false_lead` with `reproducible_false_lead` on run 2.

### The negative control was lost, as designed — and the loss is clean

Category F (T6, exhaustive environment-variable inventory) is the one category where the
distributions **do not overlap**, in either direction:

| | Arm A runs | Arm B runs |
|---|---|---|
| Tool calls | 39, 42 | **48, 54** |
| Tokens | 105,516 · 103,478 | **122,741 · 126,738** |

Every Arm B run cost more than every Arm A run — +25.9% tool calls, +19.4% tokens — for **equal
correctness**. That satisfies the pre-registered `GRAPHIFY_HARMFUL` condition ("effort increases
without a compensating quality gain") and, unlike the three categories below, it does not rest on a
single divergent run.

> **How strong "clean" is, stated precisely, because the word invites over-reading.** Complete
> 2-versus-2 separation is the **strongest signal this design can produce** — with two observations
> per arm there is no arrangement more extreme than every Arm B run exceeding every Arm A run. It is
> also not, on its own, a significant result: under the null hypothesis of exchangeable runs there
> are C(4,2) = 6 ways to split four values into two labelled arms, exactly one of which is this
> complete separation, so the exact one-sided permutation probability is **1/6 ≈ 0.17**. That is the
> floor imposed by n = 2, not a property of the effect. **The `GRAPHIFY_HARMFUL` verdict rests on
> the pre-registered §5.3 rule being satisfied, not on statistical significance**, and no
> significance is claimed for it.

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
as insufficient rather than banked as a finding. (**§6, not §5.3.** §5.3's own definition of that
label names a third run that was never executed; the deviations section above records this for T2,
T5 and T7.) In each case the two runs of the same arm differ
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
| count of false-positive leads pursued | **partly** | Recorded as boolean flags (`graphify_false_lead`, `reproducible_false_lead`, `graphify_incomplete_doc_lead`, `graphify_steered_to_gold_false_lead`) plus an integer `dead_ends`, never as a count graded against gold's `common_false_leads` list | No — the flags and `dead_ends` are what the §5.3 false-lead limb was applied to where it was applied at all, and both are committed. But see §2's deviations section: on **T4** the `GRAPHIFY_HARMFUL` false-lead limb was never adjudicated, and the flags and the counts point in opposite directions there |
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
reason: **had the declared recall metric been collected, C is the verdict whose premise is least
well supported, and the committed hints point toward neutral rather than more helpful.**

**Category F (T6) is the other place §5.3 mentions a quality gain — and its verdict survives.**
`GRAPHIFY_HARMFUL` has three independent limbs, and F satisfies two. A graded quality gain for Arm B
would have been the "compensating quality gain" that defeats the *effort* limb. But the *false-lead*
limb stands on its own: Arm B run 1 is flagged `graphify_incomplete_doc_lead` and no Arm A T6 run
carries any false-lead flag. And the direction of the unmeasured quality effect is not open here —
Graphify's actual T6 contribution was a documentation table omitting at least a dozen required
variables, a quality *liability*, not a gain. **F is robust to this gap.**

The three `INSUFFICIENT_EVIDENCE` categories are also robust to *this* gap: the label rests on two
runs of the same arm disagreeing, and the disagreement is in the committed integers. (Their separate
issue — that §5.3's definition of the label names a third run that was never executed, so they stand
on §6's route instead — is recorded in §2's deviations section.)

### (b) Irrelevant files opened — the gap most likely to have favoured Graphify

Named explicitly rather than buried, because honest disclosure has to cut both ways. Arm B opened
**fewer files overall** (median 8.0 vs 9.5, −15.8%). That is consistent with — though it does not
demonstrate — Graphify steering agents away from irrelevant files, which is exactly what the
declared "irrelevant files opened" metric would have tested. It was not collected.

Because §5.3's effort measure is **tool calls**, a favourable result here could not mechanically
change any category label. It would, however, bear on §9's *"Use Graphify first for: Nothing"*, which
rests on no measured gain being distinguishable from run-to-run variance (no interval or
significance test was computed — see §9). **A reader should treat that recommendation as resting on
the measures that were taken — not as the outcome of a search that ruled this one out.**

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

- **Wall-clock is contaminated and was excluded from every verdict — and the excluded figure ran
  *against* Graphify.** Stating the direction matters, because an exclusion whose direction is
  withheld can be read as selection either way. **The number that was dropped: median duration
  Arm A 154,864.5 ms (154.9 s) vs Arm B 218,391.0 ms (218.4 s) — `+41.0%` against Graphify**
  (recomputed as the median of `duration_ms` over all 16 runs per arm in
  `graphify-run-results.json`; the totals move the same way but far less, 3,578,412 ms vs
  3,835,469 ms, `+7.2%`, which is itself a symptom of the contamination). **That is the largest
  anti-Graphify number anywhere in this package, and it is the one figure this document refuses to
  use.** It is dropped because it is contaminated, not because it is inconvenient: run 1 launched 16
  agents concurrently; an Arm B agent independently detected the contention (found a competing
  process in `ps aux`) and honestly reported the elevated time it measured rather than "correcting"
  it. Run 2 used 8-agent waves and times dropped sharply (T1 Arm B: 186 s → 89 s) — confirming that
  the metric is tracking scheduler load, not tool efficacy. Arm assignment was not balanced against
  wave occupancy, so the arms are not exchangeable on this metric at all. Tool calls, files opened,
  tokens and dead ends are unaffected by CPU contention and carry the verdicts. **The rule applied
  is symmetric: a contaminated metric is excluded whichever arm it would have favoured, and
  suppressing the largest unfavourable number would have been the same methodological error as
  banking it.**
- **Agent variance exceeds the tool effect** (§2). This is the dominant limitation. Two runs per
  arm detect only large, consistent differences.
- **n = 8 tasks, one repository.** Conclusions are about this codebase's shape — Python + TypeScript,
  doc-heavy, history-heavy — and do not automatically transfer.
- **This repository is unusually self-documenting**, which compresses any measurable gap: several
  answers are stated in prose inside the very files an agent must find (T8's lure is corrected by
  `inferability.py`'s own docstring; T5's rationale sits in `disclosure.py`'s docstring). Both arms
  converge once the right file is open, so most tasks became location races, not reasoning races.
  The benchmark designer flagged this risk in advance, before results existed.
- **One harness failure was excluded, another instance of the same defect was kept, and the
  exclusion is not auditable.** Three separate corrections belong here, because an earlier revision
  of this bullet was wrong on all three.
  - *What happened:* the orchestrator initially wrote the task file to the main repo rather than the
    pinned worktree. One Arm A run on T5 hit it, correctly refused to invent an answer, and was
    relaunched.
  - *The excluded run's metrics are **not** "marked in the raw results".* They are **absent**.
    `graphify-run-results.json` holds 32 records, every one carrying `"status": "ok"` (verified: the
    set of distinct `status` values is exactly `{"ok"}`), and every one of the 16 (task, arm) pairs
    has exactly 2 runs. There is no excluded-run record to inspect and no field distinguishing one.
    What *is* marked is the **replacement**: T5 Arm A run 1's note begins "RELAUNCHED run." A reader
    can see that a relaunch happened; they cannot see what was discarded, so they cannot check that
    the exclusion was applied to a genuinely defective run rather than an unfavourable one.
  - *The same defect occurred in Arm B and that run was kept.* **T1 Arm B run 1** records it
    explicitly — "Read task file from main repo path (untracked files do not propagate to
    worktrees) - same commit, investigation done in wt-bench" — and it was retained with
    `tool_uses: 36`, the highest of T1's four runs and the outlier that sets Arm B's T1 median.
    **This is a differential exclusion: the same harness defect was excluded in one arm and kept in
    the other.**
  - *Direction: it runs **against** Graphify, which is why it was not caught.* T1's recorded verdict
    is `GRAPHIFY_NEUTRAL` at 27.0 → 27.5 median tool calls (+1.9%). Excluding T1 Arm B run 1 on the
    same grounds as the T5 Arm A run leaves Arm B's single remaining run at 19 tool calls against
    Arm A's median of 27.0 — **−29.6%**, which clears `GRAPHIFY_HELPFUL`'s ≥15% bar and sits just
    under `GRAPHIFY_STRONGLY_HELPFUL`'s ≥30%. **No such recomputation is performed and T1's label is
    not changed**: a one-run arm is not a median, re-deciding a verdict after seeing the data is
    forbidden by §5.3, and the correct remedy would have been a relaunch at the time, which is no
    longer possible. The figure is given so a reader can see the size of what the inconsistency
    concealed.
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
Nothing. **No task category in this benchmark showed a correctness or efficiency gain
distinguishable from the run-to-run variance visible in the raw data.** No confidence interval,
standard error, or significance test was computed anywhere in this package; at **two observations
per arm per task** none would be meaningful, and none is claimed. The phrase "error bars" appeared
in earlier revisions of this document and was unearned — there were no error bars. What the
recommendation actually rests on is the pre-registered §5.3 rules applied to the committed medians,
plus the repeatedly observed fact that **within-arm spread exceeds between-arm spread** (§2: T5 Arm
B 44 then 24; T7 Arm B 37 then 18). Recommending Graphify as a first step would not be supported by
those measurements.

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
This benchmark does not support the `CLAUDE.md` §7 instruction — **the one this benchmark caused
to be withdrawn** — to *"use Graphify before answering architecture/codebase questions."* That
instruction presumed a benefit the measurements do not show, and §7 now records it as WITHDRAWN
rather than current. The narrower role the evidence supports is: **an optional documentation-orientation
aid, never a first step, never for exhaustive or backend-code questions.**

Nothing here bears on the *shipped* Project Memory feature, which serves a committed snapshot and
never reads a live graph.

# Measured scale envelope — 2026-08-25

**Measured at `main` = `b7008b8`**, in-process against the FastAPI `TestClient`, so every
figure is SERVER work with no browser and no network in it. That is deliberate: the browser
half was measured and bounded separately (`docs/run-scale-measurements.md`), and the server
half is the one a payload table could not show — flat bytes, linear time.

**How to re-measure — CORRECTED after independent review.** ~~"What IS committed is the
opt-in harness for the count derivation"~~ implied that was the only one. **It is not: there
is a second committed harness that reproduces most of these columns** —
`apps/api/tests/test_pending_reads_are_boundable.py::test_benchmark_pending_scale_envelope`,
behind the same `ISAAC_PERF_BENCH=1` opt-in. That is the runnable reproduction and should be
preferred over the scratchpad scripts:

```
ISAAC_PERF_BENCH=1 .venv/bin/pytest -q -s -k benchmark \
  apps/api/tests/test_pending_reads_are_boundable.py \
  apps/api/tests/test_pending_count_is_not_materialised.py
```

Neither asserts anything about wall-clock — a timing assertion in the normal suite is flaky
under CPU contention, and this repository has been bitten by that.

**THE RUN LABEL MOVES EVERY BYTE FIGURE, AND THE TWO TABLES BELOW USED DIFFERENT ONES.** The
pending payload embeds `run_label`, so its width is in every count. §1 was taken with
`Run {:04d}`; §2 with `Run {}`. A reviewer measured that no single workload reproduces both
tables, which is correct and is a defect in how this document was written rather than in the
measurements. Each table now states its scheme. The committed harness uses `Run {}`, so it
reproduces §2's columns byte-for-byte and gives slightly smaller figures than §1 (44,236
against 44,413 at 25 runs) — that difference is the label, not a discrepancy.

**Machine and contention.** Taken on a quiet macOS machine with no subagents running. An
earlier run of the same harness under contention (two review agents plus a test suite)
produced byte counts identical to these and wall-clock within noise — the byte figures are
contention-free by construction, the millisecond figures are indicative only. **Linux CI is
not a source for any number here**; nothing in CI runs this harness.

---

## 1. The default, unbounded reads

*Run labels `Run {:04d}`.*

| runs | detail bytes | detail min/med ms | `GET /pending` bytes | min/med ms | entries | `GET /runs` bytes | min/med ms |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 25 | 1,475 | 3.2 / 3.3 | 44,413 | 2.9 / 3.0 | 75 | 10,718 | 2.1 / 2.1 |
| 100 | 1,479 | 8.7 / 8.8 | 177,613 | 7.4 / 7.8 | 300 | 42,598 | 4.6 / 4.7 |
| 250 | 1,479 | 19.2 / 20.6 | 444,013 | 16.7 / 18.3 | 750 | 106,498 | 9.2 / 9.6 |
| 500 | 1,480 | 37.0 / 40.3 | 888,013 | 31.7 / 32.3 | 1,500 | 212,998 | 16.1 / 16.7 |
| 1000 | 1,483 | 76.0 / 81.4 | 1,776,013 | 66.7 / 68.7 | 3,000 | 426,003 | 32.3 / 35.6 |

**`GET /pending` is linear and unbounded BY DESIGN, and that is not an oversight.** A client
asking "what is unresolved?" gets the complete truth; bounding is something a client ASKS
for. A negative-control test asserts this default still GROWS with run count, precisely so
that nobody later "fixes" it into silent truncation.

## 2. The bounded reads, and the write path

*Run labels `Run {}`. This harness also ANSWERS `qc` on the newest run at each level, so the pending set shrinks by one run per level — which is why its answer-response delta differs from a harness that answers nothing.*

| runs | detail bytes | detail med ms | `?limit=50` bytes | `?run_id=` bytes | `POST …/answers` bytes |
|---:|---:|---:|---:|---:|---:|
| 25 | 1,475 | 3.0 | 29,584 | 1,932 | 31,962 |
| 100 | 1,479 | 9.6 | 29,587 | 1,936 | 31,971 |
| 250 | 1,479 | 19.6 | 29,587 | 1,936 | 31,971 |
| 500 | 1,480 | 40.8 | 29,590 | 1,937 | 31,974 |
| 1000 | 1,483 | 83.2 | 29,590 | 1,940 | 31,980 |

**Across a 40× workload:** `?limit=50` moves **+6 bytes** and `?run_id=` **+8** — both
independently reproduced byte-for-byte by a reviewer. ~~the answer response **+18**~~ —
**that one is harness-dependent and was published without its harness.** An independent
measurement of the same route with no run answered gives **31,958 → 31,968 = +10**, and the
figure moves with the label scheme (`Run {}` +10, `Run {:04d}` +6, `{:03d}` +8). What is
robust across every variant is that it is a DIGIT-COUNT delta on a ~32 KB response, against
**1,773,294 B** before the bounding work. Quote the range, not one number. The write path — the one a scientist hits
repeatedly — was **1,773,294 B** before this programme's bounding work and is now flat at
~32 KB.

## 3. What is still linear, named rather than implied

> **STATUS CHANGED 2026-08-25 — the multiple is gone, the linearity is not.** The
> diagnosis below stands unaltered and is what the fix was built from; §3A records what
> was done, what it measured, and what is left, and **§3B closes the one residual §3A
> named as "not attempted"** (the repeated dry run, which was the larger half on a fully
> answered record). Read §3 for the defect, §3A and §3B for its current state.

**The record-detail route's TIME is still linear: 3.0 ms at 25 runs, 83.2 ms at 1,000**, while
its payload is flat at ~1.5 KB. So the cost is invisible in bytes and visible only in latency,
which is how it went unnoticed before.

It was profiled rather than guessed at, and **the profile's CAUSAL ATTRIBUTION was wrong —
corrected here after an independent review traced the frames.** The counts were exact:
`resolved_run_draft` at **3,000 calls per request** (exactly 3× runs), `export_units` 3, and
`json.decoder.raw_decode` **1** — so document parsing is genuinely **not** the bottleneck
(0.6–1.7% depending on how it is totalled). `copy.deepcopy` is ~49% cumulative / ~19%
`tottime`; the original "53% of total time" mixed a `tottime` figure with a total.

~~"the detail route reaches it three times (`status()`, `export_ready()`, and the derived
workflow)"~~ — **FALSE, and it matters because it mis-scoped the remedy.** `status()` reaches
`_all_units_pass_dry_run` only when `pending_count() == 0`, and `export_ready()` returns
`False` before it — so on a record owing 3× runs questions, which is exactly the workload
these tables measure, **neither reaches `export_units` at all.** Frame-level tracing gives the
real three:

```
1x  routes.py _detail  <- _workflow_for  <- workspace.draft_ok
1x  routes.py _detail                    <- workspace.draft_ok
1x  routes.py _detail  <- dependencies.artifact_state <- _fan_out_artifact_state
```

i.e. **`draft_ok()` twice plus `artifact_state` once** — corroborated by the profile, where
`export_draft`/`transform` have ZERO calls while `validate_draft` has 2,000. On a fully
answered record the count is **five, not three**.

**The earlier `pending_count` fix removed the other 8× of this** (it was materialising ~12,000
dictionaries per request to produce four integers; 8.18 ms → 0.09 ms on a 1,000-run legacy
record). What remains is the composed-draft work. ~~"Threading the two derived facts through
the response builder is the shape that works"~~ — **that remedy was scoped to
`status()`/`export_ready()`, which the corrected trace shows contribute NOTHING on this
workload.** A slice following the original paragraph would have optimised code that never
runs. The real callers are `draft_ok()` and `artifact_state`, and memoising `export_units()`
per instance is still unsafe for the reason originally given — routes mutate an `Experiment`
and re-read its state in the same request. ~~**Not done, and not begun**, and now at least
pointed at the right functions.~~ — **DONE 2026-08-25; see §3A.** The sentence is struck
rather than deleted because it was true when written and because the thing that made it
actionable — being pointed at the right functions — is what §3A was built on.

## 3A. What the threading slice did, and what is still linear afterwards

**THE REMEDY WAS THREADING, NOT MEMOISATION, AND THE DISTINCTION IS THE WHOLE DESIGN.** §3
is right that a per-instance memo is unsafe: routes mutate an `Experiment` and re-read its
derived state in the same request (answer → recompute status/workflow), so a
`cached_property` or an instance dict would serve a stale composition after a write. So
`draft_ok`, `_all_units_pass_dry_run`, `status` and `export_ready` each gained an
**optional** already-composed `units` argument, `dependencies.artifact_state` gained the
same, and `routes._detail` composes the list **once** through the one named seam
`routes._shared_units` and hands it to every consumer. Nothing is stored, nothing is
invalidated, and every other call site — `_workflow_for` is reached by every mutation
response, ~~a dozen sites~~ **fourteen others, fifteen in `routes.py` all told; counted
with `grep -n '_workflow_for(' apps/api/isaac_api/routes.py`, and "a dozen" was wrong by
three** — is byte-for-byte the code it was, because `units=None` still means "compose your
own".

**A SECOND, SMALLER SHARING, FOUND BY RE-PROFILING RATHER THAN BY READING.** Sharing the
unit list stopped the re-*composition* but `draft_ok` was still being *derived* twice from
it — once for the workflow's steps and once for the response's own key — i.e.
`validate_draft` over every unit, twice: **2,000 calls per request at 1,000 runs, exactly
2× runs**, which is also the figure §3 quotes from the original profile without remarking on
it. `_detail` now derives it once and passes the boolean. This is why the table below has a
`validate_draft` column that §3 does not.

### Call counts per request — measured, not argued

Counted by wrapping the two methods over the real HTTP surface, and asserted in the normal
suite by `apps/api/tests/test_detail_route_composes_each_run_once.py`:

| runs | `resolved_run_draft` | `export_units` | `validate_draft` |
|---:|---:|---:|---:|
| 25 | 75 → **25** | 3 → **1** | 50 → **25** |
| 100 | 300 → **100** | 3 → **1** | 200 → **100** |
| 250 | 750 → **250** | 3 → **1** | 500 → **250** |
| 500 | 1,500 → **500** | 3 → **1** | 1,000 → **500** |
| 1000 | **3,000 → 1,000** | 3 → **1** | 2,000 → **1,000** |

**There is no `export_draft` column here because on this workload it is zero, and that
matters — see the fully-answered record below, where it is not.** Re-measured on both arms
at **25 runs (0 → 0, alongside 75 → 25 / 3 → 1 / 50 → 25)** and **100 runs (0 → 0,
alongside 300 → 100 / 3 → 1 / 200 → 100)**, which also reproduces this table's first two
rows exactly. It is zero by construction while `pending_count() > 0`: `status()`
short-circuits before `_all_units_pass_dry_run` and `export_ready()` returns `False`
before it, so the dry run is never entered. 250, 500 and 1,000 were not re-measured for
this column.

The 3× confirms §3's corrected trace exactly. Two further counts §3 does not give, because
they are worse and are the ones a scientist reaches at the END of the work: on a **fully
answered, unexported** record it was **5×** (`status()` and `export_ready()` stop
short-circuiting the moment `pending_count()` hits 0), and on a **fully exported fan-out**
**4×**. Both are now 1×, and both are pinned by their own tests.

#### The fully-answered record, measured separately — because the table above hides its residual

**`export_draft` IS ZERO ON THE WORKLOAD ABOVE BECAUSE OF WHAT THAT WORKLOAD IS, NOT
BECAUSE OF ANYTHING THIS CHANGE DID.** Those rows are taken on a record with open
questions, where the dry run is never reached. An independent review measured the fully-answered
record — the one both this section and the commit message single out as *"the worst case
and the one a scientist reaches at the END of the work"* — and found a residual this
document had no row for. **Re-measured here at 200 fully-answered runs, over the real HTTP
surface, both arms in one process** (the "before" arm is the current code with both seams
disabled, exactly as in the A/B below):

| | `resolved_run_draft` | `export_units` | `validate_draft` | **`export_draft`** |
|---|---:|---:|---:|---:|
| before (both seams disabled) | 1,000 (5×) | 5 | 400 (2×) | **400 (2×)** |
| after the unit-list threading | **200 (1×)** | **1** | **200 (1×)** | **400 (2×)** |
| **after the dry-run sharing (§3B)** | **200 (1×)** | **1** | **200 (1×)** | **200 (1×)** |

**THE THIRD ROW IS NEW AND IS WHAT §3B RECORDS.** The `400 (2×)` the paragraphs below
call unmovable-by-composition-sharing has been moved, by sharing the DRY RUN rather than
the composition. Everything those paragraphs say about why the *composition* threading
could not touch it remains exactly true and is left standing; what has changed is that a
different seam now does.

The 5× → 1× composition claim is exactly right, and `validate_draft` halves. **What does
not move is `export_draft`: it stays at 2× the run count**, because `status()` and
`export_ready()` each call `_all_units_pass_dry_run`, and threading the unit list removes
the *composition* they shared, not the *dry run* they each perform. Sharing the composed
list was never going to touch that.

**So the speed-up on THIS workload is materially smaller than the 2.4–2.5× headline below,
and the two figures must not be quoted as if they were the same measurement.** The
reviewer, on a quiet machine, measured **1,293 ms → 1,010 ms, ≈1.28×** at 200 runs, with
`export_draft` accounting for roughly half the request against roughly 3% for the
composition the threading removed. **A re-measurement here reproduced the CALL COUNTS
exactly and the wall-clock NOT at all**: 5,285 ms → 3,344 ms best-of-seven, a ratio of
1.58×, taken while another agent was working in the same repository — the un-threaded
arm's median was 11,927 ms against its own minimum of 5,285 ms, which is contention on the
face of it. **Neither ratio is quoted as precise, and the disagreement is reported rather
than resolved**: the counts are contention-free by construction and are what this row
should be read for. It also qualifies the A/B section's *"the speed-up column is the robust
figure"* — robust across repeats of the SAME workload, not transferable to a different one.

**Nothing here is false in the rows above; the omission is what misleads.** A reader who
maps "5× composition removed" onto the 2.4–2.5× headline will expect the fully-answered
record to be the biggest win, and it is the smallest one measured.

*Everything in this sub-section remains a true account of THE THREADING SLICE and is left
standing as written. It is no longer a true account of the CURRENT code: §3B shares the dry
run as well, taking the same 200-run workload to `export_draft` 200 (1×) and a further
1.74×. Do not quote the `400 (2×)` row as the shipped state.*

~~**The next candidate, named and NOT attempted:** `status()` and `export_ready()` could
share one dry run the way they now share one composition. That is a larger change than
this slice … it is not authorised here, and no measurement in this repository establishes
what it would be worth beyond the 2× above.~~ — **DONE 2026-08-25; see §3B.** Struck
rather than deleted because it was true when written and because it is the paragraph the
next slice was built from. Its estimate of the difficulty was right — the two DO have
different short-circuits, and reconciling them is the whole design — and its statement
that nothing established the value was also right, which is why §3B measures it rather
than asserting it.

### Wall-clock — the ratio is the finding; the absolutes carry a caveat

A/B **interleaved in one process on one machine**, arms alternating so drift hits both
equally. The "before" arm is the current code with the two seams disabled
(`_shared_units → None`, `_workflow_for` dropping the boolean it is handed), which
reproduces the old call pattern exactly; its numbers agree with §1's independently measured
before-figures within a few percent, which is the cross-check that makes the reconstruction
usable.

| runs | §1 published (min) | A/B before (min) | **A/B after (min)** | speed-up |
|---:|---:|---:|---:|---:|
| 25 | 3.2 | 3.5 | **2.6** | 1.37× |
| 100 | 8.7 | 8.9 | **4.3** | 2.06× |
| 250 | 19.2 | 20.3 | **8.9** | 2.29× |
| 500 | 37.0 | 39.3 | **16.7** | 2.36× |
| 1000 | 76.0 | 78.2 | **31.4** | 2.49× |

**THE ABSOLUTE MILLISECONDS ARE INDICATIVE ONLY AND THIS IS NOT A FORMALITY — IT WAS
OBSERVED.** Two further runs of the identical harness, taken minutes later while another
agent was working in the same repository, put the *before* arm at 107–109 ms at 1,000 runs
against this table's 78 — a 38% inflation of the arm that was supposed to be the fixed
reference. The **ratios in those same runs were 1.45–1.50 / 2.02–2.09 / 2.33–2.39 /
2.38–2.40 / 2.40–2.44**, i.e. indistinguishable from this table. So the speed-up column is
the robust figure and the millisecond columns are not, exactly as `CLAUDE.md` §7's
contention note requires; the row above is quoted from the quietest run and only because
its before arm reproduces §1. **Nothing in CI runs this harness and no Linux figure exists.**

### STILL LINEAR, and this is a partial win reported as one

**`GET /api/experiments/{id}` is still linear in time.** 2.6 ms at 25 runs, 31.4 ms at
1,000; the marginal cost from 100 → 1,000 runs is ~30 µs per run. The multiple was removed;
the slope was not. Where the remaining 31.4 ms goes on a 1,000-run record, measured
best-of-ten per component:

| component | ms | share |
|---|---:|---:|
| `export_units()` — composing 1,000 run drafts **once** | 21.7 | 68% |
| `load_experiment()` — read the document, build 1,000 `Run` objects | 4.6 | 14% |
| `draft_ok(units=…)` — `validate_draft` over 1,000 composed drafts | 1.7 | 5% |
| `artifact_state(units=…)`, `pending_count()` | 0.15 | <1% |
| remainder (ASGI, routing, response serialisation) | ~3.7 | 12% |

**The dominant term is now the one composition the response genuinely needs, and it is not
reducible without changing the storage model.** `draft_ok` is *defined* as "every unit's
composed draft passes the no-guessing checks", and a run's draft is composed on read
precisely so that inheritance stays by reference — edit an experiment-level field and every
run reflects it with no fan-out write (`workspace.resolved_run_draft`, contract §2 D2).
Avoiding the composition would mean either storing composed drafts (giving up that
invariant) or decomposing validation into an experiment half plus a per-run half (a
different, unproven definition of `draft_ok`). **Neither is attempted here and neither is
justified by any measurement in this repository.** `load_experiment` and `pending()` are
linear by contract for the same reason.

**What was NOT changed, named rather than implied:** `GET /pending`'s unbounded default is
still deliberately linear (§1) and a negative-control test keeps it that way; nothing in
`src/isaac_records/**` was touched; and no response moved by one byte — ~~17~~ **21**
record shapes (the five canonical seeds, zero-run, legacy-run, multi-run, mixed, malformed
`pending`, `draft_ok` false, partially and fully exported fan-outs, exported and stale
zero-run, and — added after review — four **degraded artifacts**, a deleted and an
unparseable record file on both the single-record and the fan-out path, which are the only
shapes that reach `dependencies.MISSING_REASON`) were captured before the change and after
it and are **byte-identical**.

~~"with the same equality re-asserted in the suite by patching `_shared_units` to
`None`"~~ **— THAT WAS NOT ENOUGH, and it is struck rather than edited because the
committed test asserted it as a completeness claim.** There are **two** seams: `_detail`
also derives `draft_ok` once and hands it to `_workflow_for`, and patching
`_shared_units` alone does not revert that. Measured: mutating `draft_ok=draft_ok` to
`draft_ok=(not draft_ok)` left `test_detail_route_composes_each_run_once.py` at **14
passed**. The A/B harness in this document had it right — it disabled both — and the
suite now does too, plus a threaded-vs-un-threaded guard on
`dependencies.build_invalidation`, the second threading site, which is on the MUTATION
path and had no committed guard at all.

Also corrected: the detail response is flat as **+2 bytes**, not the +8 first published.
`detail bytes = 1458 + len(title)` fits exactly across four independent titles, so most of
the apparent growth was the harness's own lengthening titles presented as a run-count
effect.

## 3B. Sharing the dry run — the residual §3A named, measured and closed

**WHAT WAS SHARED, AND IT IS NOT WHAT §3A SHARED.** §3A threaded the composed
`export_units()` list; the dry run each consumer then performed over it was untouched, so
`export_draft` stayed at 2× the run count. This slice threads the *verdict*:
`Experiment.dry_run_verdict(units=…)` derives it once, and `status()` / `export_ready()`
take it as an optional `dry_run_ok` whose `None` default is, line for line, the code that
ran before the parameter existed. `routes._shared_dry_run` is the seam; nothing is stored,
for the reason §3A gives at length.

**THE GATE IS THE DESIGN, AND IT IS WHERE A NAIVE VERSION GOES WRONG.** Both consumers
short-circuit past the dry run while `pending_count() > 0` — `status()` answers
`needs_attention`, `export_ready()` returns `False` — so on a record that still owes
questions the dry run is entered **zero** times. A "compute it once up front" would have
turned 0 into N and made the COMMON case slower to speed up the rare one. So
`dry_run_verdict` returns `None` while anything is pending, which is exactly the union of
the two short-circuits: `status()` has an extra `all_units_exported()` short-circuit, but
`export_ready()` does not, so there is no reachable state where a verdict is composed that
nobody asked for.

### Call counts per request — measured over HTTP, arms interleaved in one process

200 runs, fully answered and unexported. The "before" arms are the current code with the
named seams disabled, the same reconstruction §3A's A/B uses.

| arm | `resolved_run_draft` | `export_units` | `validate_draft` | **`export_draft`** | min ms |
|---|---:|---:|---:|---:|---:|
| `main` @ `721238a` (both seams off) | 1,000 (5×) | 5 | 400 (2×) | **400 (2×)** | 5,310.7 |
| this seam off only | 200 (1×) | 1 | 200 (1×) | **400 (2×)** | 3,321.0 |
| **after** | **200 (1×)** | **1** | **200 (1×)** | **200 (1×)** | **1,913.7** |

* this seam alone: **1.74×** (min), 1.71× (median of seven)
* cumulative against `main`: **2.75×** (min), 2.74× (median)

**And the case that must NOT get worse — 500 runs, still pending, 41 interleaved reps:**

| | `export_draft` | min ms | med ms |
|---|---:|---:|---:|
| before | **0** | 17.1 | 19.0 |
| after | **0** | 17.3 | 18.6 |

**0 → 0 is the load-bearing figure**, and it is asserted in the normal suite rather than
only measured here (`test_detail_route_composes_each_run_once.py`). The cost that IS paid
on every read, including every pending one, is **one extra `pending_count()`** — measured
directly at 0.0195 ms (200 runs) and 0.0474 ms (500 runs) over 2,000 repetitions, i.e.
~0.26% of an ~18 ms request, which is inside the run-to-run spread above and is why the
ratios come out at 0.99× / 1.02× rather than cleanly at 1.

**THE MILLISECONDS ARE CONTAMINATED AND THE COUNTS ARE NOT.** Every figure above was taken
with the machine's load average between 5 and 7.5 on 10 cores, with another agent working
in the same repository. That is the same contamination §3A reports; its `main`-arm
reconstruction here (5,310.7 ms) reproduces §3A's own contended re-measurement (5,285 ms)
rather than its quiet-machine table (which has no 200-run row), so the arms are internally
consistent and the *ratios* are what this section should be read for. No Linux/CI figure
exists; nothing in CI runs this harness.

### The semantic proof, unchanged in kind

The full detail response is **byte-identical across all 21 shapes** with the seams on and
off — `response.content`, not parsed JSON. The suite's `_disable_threading` now reverts
**three** seams, not two; it had to be extended, and the extension was verified by mutation
(`dry_run_ok=dry_run_ok` → `dry_run_ok=(dry_run_ok is False)` in `routes._detail`, which
the byte-equality test then fails). That is the same class of defect §3A records for the
second seam, caught this time before shipping rather than after.

### What is STILL linear, and what was deliberately not done

`GET /api/experiments/{id}` remains linear in time; §3A's component breakdown is unchanged
in kind — the dominant term is the one composition the response genuinely needs.
~~Nothing in `src/isaac_records/**` was touched.~~ **Struck 2026-08-25, and it was false of
the commit that carried it.** The sentence is true of THIS SECTION — no performance seam
reaches the truth core, `export.py` and `official.py` are unchanged, and no export verdict
moves for a well-formed draft. But the commit that landed §3B also landed a wrong-typed
top-level container guard in `src/isaac_records/draft_validator.py`, disclosed under §13 in
`apps/api/tests/test_run_api.py::_DISCLOSED_TRUTH_PATH_CHANGES`. An unqualified "nothing was
touched" in the one line of this artifact that speaks to truth-path exposure is exactly the
claim a reader would rely on and not re-check, so it is corrected in place rather than
scoped quietly. `_all_units_pass_dry_run` keeps its `units=None`
fallback and every caller outside `routes._detail` — including
`dependencies.build_invalidation`, which needs the verdict exactly once — is byte-for-byte
the code it was. `GET /pending`'s unbounded default is untouched.

## 4. The tested ceiling, stated as a ceiling

**1,000 runs on one experiment** is the highest workload measured. Nothing here supports a
claim beyond it, and no claim of unlimited scale is made. `/pending`'s default response at
that size is 1.78 MB, which is why the bounded reads exist.

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
> was done, what it measured, and what is left. Read §3 for the defect and §3A for its
> current state.

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
response, a dozen sites — is byte-for-byte the code it was, because `units=None` still
means "compose your own".

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

The 3× confirms §3's corrected trace exactly. Two further counts §3 does not give, because
they are worse and are the ones a scientist reaches at the END of the work: on a **fully
answered, unexported** record it was **5×** (`status()` and `export_ready()` stop
short-circuiting the moment `pending_count()` hits 0), and on a **fully exported fan-out**
**4×**. Both are now 1×, and both are pinned by their own tests.

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
`src/isaac_records/**` was touched; and no response moved by one byte — 17 record shapes
(the five canonical seeds, zero-run, legacy-run, multi-run, mixed, malformed `pending`,
`draft_ok` false, partially and fully exported fan-outs, exported and stale zero-run) were
captured before the change and after it and are **byte-identical**, with the same equality
re-asserted in the suite by patching `_shared_units` to `None`.

Also corrected: the detail response is flat as **+2 bytes**, not the +8 first published.
`detail bytes = 1458 + len(title)` fits exactly across four independent titles, so most of
the apparent growth was the harness's own lengthening titles presented as a run-count
effect.

## 4. The tested ceiling, stated as a ceiling

**1,000 runs on one experiment** is the highest workload measured. Nothing here supports a
claim beyond it, and no claim of unlimited scale is made. `/pending`'s default response at
that size is 1.78 MB, which is why the bounded reads exist.

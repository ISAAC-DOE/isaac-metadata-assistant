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
and re-read its state in the same request. **Not done, and not begun**, and now at least
pointed at the right functions.

Also corrected: the detail response is flat as **+2 bytes**, not the +8 first published.
`detail bytes = 1458 + len(title)` fits exactly across four independent titles, so most of
the apparent growth was the harness's own lengthening titles presented as a run-count
effect.

## 4. The tested ceiling, stated as a ceiling

**1,000 runs on one experiment** is the highest workload measured. Nothing here supports a
claim beyond it, and no claim of unlimited scale is made. `/pending`'s default response at
that size is 1.78 MB, which is why the bounded reads exist.

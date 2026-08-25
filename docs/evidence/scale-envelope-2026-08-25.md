# Measured scale envelope — 2026-08-25

**Measured at `main` = `b7008b8`**, in-process against the FastAPI `TestClient`, so every
figure is SERVER work with no browser and no network in it. That is deliberate: the browser
half was measured and bounded separately (`docs/run-scale-measurements.md`), and the server
half is the one a payload table could not show — flat bytes, linear time.

**How to re-measure.** The harnesses are `scale_bench.py` and `final_bench.py`, written to a
scratchpad rather than committed, because they create 1,000 runs over HTTP and take ~15
minutes. What IS committed is the opt-in in-process harness for the count derivation
(`ISAAC_PERF_BENCH=1 .venv/bin/pytest -q -s -k benchmark
apps/api/tests/test_pending_count_is_not_materialised.py`), which asserts nothing about
wall-clock — a timing assertion in the normal suite is flaky under CPU contention, and this
repository has been bitten by that.

**Machine and contention.** Taken on a quiet macOS machine with no subagents running. An
earlier run of the same harness under contention (two review agents plus a test suite)
produced byte counts identical to these and wall-clock within noise — the byte figures are
contention-free by construction, the millisecond figures are indicative only. **Linux CI is
not a source for any number here**; nothing in CI runs this harness.

---

## 1. The default, unbounded reads

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

| runs | detail bytes | detail med ms | `?limit=50` bytes | `?run_id=` bytes | `POST …/answers` bytes |
|---:|---:|---:|---:|---:|---:|
| 25 | 1,475 | 3.0 | 29,584 | 1,932 | 31,962 |
| 100 | 1,479 | 9.6 | 29,587 | 1,936 | 31,971 |
| 250 | 1,479 | 19.6 | 29,587 | 1,936 | 31,971 |
| 500 | 1,480 | 40.8 | 29,590 | 1,937 | 31,974 |
| 1000 | 1,483 | 83.2 | 29,590 | 1,940 | 31,980 |

**Across a 40× workload:** `?limit=50` moves **+6 bytes**, `?run_id=` **+8**, and the answer
response **+18**. Those are digit counts. The write path — the one a scientist hits
repeatedly — was **1,773,294 B** before this programme's bounding work and is now flat at
~32 KB.

## 3. What is still linear, named rather than implied

**The record-detail route's TIME is still linear: 3.0 ms at 25 runs, 83.2 ms at 1,000**, while
its payload is flat at ~1.5 KB. So the cost is invisible in bytes and visible only in latency,
which is how it went unnoticed before.

It was profiled rather than guessed at. `cProfile` over ten requests on a 1,000-run record:
`copy.deepcopy` is **53%** of total time, driven by `workspace.Experiment.resolved_run_draft`
at **3,000 calls per request** — `export_units()` composes every run's draft, and the detail
route reaches it three times (`status()`, `export_ready()`, and the derived workflow).
Document parsing is **not** the bottleneck: `json.decoder.raw_decode` is 0.054 s of 3.244 s,
one call per request.

**The earlier `pending_count` fix removed the other 8× of this** (it was materialising ~12,000
dictionaries per request to produce four integers; 8.18 ms → 0.09 ms on a 1,000-run legacy
record). What remains is the composed-draft work, and the obvious fix — memoising
`export_units()` per request — is **not** safe as a per-instance cache, because routes mutate
an `Experiment` and then re-read its status in the same request. Threading the two derived
facts through the response builder is the shape that works. **Not done, and not begun.**

## 4. The tested ceiling, stated as a ceiling

**1,000 runs on one experiment** is the highest workload measured. Nothing here supports a
claim beyond it, and no claim of unlimited scale is made. `/pending`'s default response at
that size is 1.78 MB, which is why the bounded reads exist.

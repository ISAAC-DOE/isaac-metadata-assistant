# Measured scale envelope — 2026-08-27

**Branch `feat/discard-evidence-graph-compare-runs-a11y`, measured over real HTTP with a real
Chromium**, at run counts **25 · 100 · 250 · 500 · 1000**. This is the first measurement of
this branch's data model: the Evidence Graph's five sub-fetches, Compare Runs' four network
reads per comparison, and the Discard control had never been measured at scale.

**Tested ceiling: 1,000 runs, ACTUALLY REACHED.** Nothing here is extrapolated to 1,000 —
every 1,000-run figure is one this sweep produced. Nothing beyond 1,000 was measured and
nothing here supports a claim beyond it.

**Read `docs/run-scale-measurements.md` first for what it corrects.** §7 below states which of
its conclusions this sweep confirms, which it supersedes, and which it inherits unchanged.

---

## 0. How these were taken, and what is and is not trustworthy in them

```bash
# the main sweep — every server route and every browser surface, five counts
cd apps/web && rm -rf /tmp/isaac-bench-0827-ws && \
E2E_MUT_WEB_PORT=5173 E2E_MUT_API_PORT=8000 \
E2E_MUT_WORKSPACE=/tmp/isaac-bench-0827-ws \
E2E_MUT_SESSION_FILE=/tmp/isaac-bench-0827-session.json \
E2E_UVICORN=/Users/krishverma/Documents/ISAAC/.venv/bin/uvicorn \
E2E_BENCH_COUNTS=25,100,250,500,1000 \
npx playwright test --config=playwright.bench.config.ts scale-2026-08-27

# the DOM attribution, per screen, by class
E2E_BENCH_COUNTS=1000 npx playwright test --config=playwright.bench.config.ts dom-attribution

# Export Readiness + the record screen's request tally
E2E_BENCH_COUNTS=25,1000 npx playwright test --config=playwright.bench.config.ts exportreadiness-scale

# the server-side call-count attribution (in-process, no browser)
.venv/bin/python /tmp/count_rev.py 500     # not committed; see §4 for what it does
```

Three new committed harnesses, all `.bench.ts` and therefore collected by **neither** Playwright
config by default, exactly as `run-scale.bench.ts` is:

| file | what it answers |
|---|---|
| `apps/web/e2e/mutation/scale-2026-08-27.bench.ts` | every server route these screens issue, plus the browser cost of the record screen, the Evidence Graph and Compare Runs |
| `apps/web/e2e/mutation/dom-attribution.bench.ts` | **which elements** the DOM is, per screen, by class |
| `apps/web/e2e/mutation/exportreadiness-scale.bench.ts` | the Export Readiness screen, and each screen's request tally with bounded/unbounded `/pending` kept apart |

`dom-attribution.bench.ts` exists because `docs/run-scale-measurements.md` §1 attributed the
record screen's 16,134 nodes with a per-class probe **that was never committed** — which is why
that document carries an arithmetic correction where a re-measurement should be. It is committed
now.

### Machine and contention — stated rather than assumed

Before the main sweep: `ps aux | grep -E "uvicorn|vite|pytest|playwright|vitest"` returned
**nothing**, and ports 5173, 5174, 8000, 8100 and 5274 were all free. `uptime` read
`load averages: 2.28 5.15 9.24` — a *decaying* profile, i.e. the machine had been busy and was
not busy then. I did not continuously monitor load during the sweep, so I cannot claim it stayed
quiet; I can claim no test process of mine or anyone else's was running when it started.

**Every count in this document is contention-proof by construction** — bytes, DOM node counts,
request counts, call counts. **Every millisecond is not**, and is secondary evidence. Each ms
figure is a **median of three**. Where a count answers the question, the count is what is quoted.

*(For contrast: during the verification `pytest` run afterwards the same machine read
`load averages: 56.00 36.03 19.19`. No measurement in this document was taken then.)*

**Ports.** The bench config inherits the mutation config, whose defaults are **5274/8100**, not
5173/8000. This sweep overrode them to 5173/8000 with a private workspace and session file, so it
could not collide with another agent running the mutation suite. The backend was confirmed to be
this checkout before anything was measured: **71 operations** and
`/api/experiments/{experiment_id}/discard` **present**.

---

## 1. The server routes

Median of three, over HTTP, `ms / KiB / n` where `n` is that route's own cardinality.

| route | 25 | 100 | 250 | 500 | 1000 |
|---|---|---|---|---|---|
| `GET /runs` (unpaged) | 14 / 187.9 / 25 | 53 / 748.1 / 100 | 137 / 1868.7 / 250 | 268 / 3736.4 / 500 | **551 / 7471.7 / 1000** |
| `GET /runs?limit=50` | 15 / 187.9 / 25 | 28 / **374.6** / 50 | 28 / **374.6** / 50 | 42 / **374.6** / 50 | 34 / **374.6** / 50 |
| `GET /experiments/{id}` (detail) | 7 / 1.5 / 77 | 21 / 1.5 / 302 | 50 / 1.5 / 752 | 100 / 1.5 / 1502 | **205 / 1.6 / 3002** |
| `GET /pending` (unbounded) | 6 / 75.6 / 77 | 14 / 293.5 / 302 | 33 / 729.7 / 752 | 68 / 1456.8 / 1502 | **148 / 2910.9 / 3002** |
| `GET /pending?limit=50` | 4 / **49.6** / 50 | 4 / **49.6** / 50 | 6 / **49.6** / 50 | 8 / **49.6** / 50 | 15 / **49.6** / 50 |
| **graph sub-fetch** `GET /conflicts` | 2 / 0.4 / 0 | 2 / 0.4 / 0 | 3 / 0.4 / 0 | 4 / 0.4 / 0 | 8 / 0.4 / 0 |
| **graph sub-fetch** `GET /notes` | 2 / 1.6 / 0 | 2 / 1.6 / 0 | 3 / 1.6 / 0 | 5 / 1.6 / 0 | 8 / 1.6 / 0 |
| **graph sub-fetch** `GET /provenance` | 3 / 6.1 / 28 | 2 / 6.1 / 28 | 4 / 6.1 / 28 | 7 / 6.1 / 28 | 8 / 6.1 / 28 |
| **graph sub-fetch** `GET /assets` | 2 / 1.9 / 0 | 3 / 6.8 / 0 | 4 / 16.7 / 0 | 7 / 33.3 / 0 | 11 / **66.5** / 0 |
| **graph sub-fetch** `GET /revisions` | 25 / 5.5 / 25 | 91 / 18.2 / 100 | 227 / 43.7 / 250 | 468 / 86.2 / 500 | **942 / 171.1 / 1000** |
| **compare** `GET /conflicts?run=` | 2 / 0.5 / 0 | 2 / 0.5 / 0 | 3 / 0.5 / 0 | 5 / 0.5 / 0 | 26 / 0.5 / 0 |
| **compare** `GET /pending?run_id=&limit=5` | 2 / 6.0 / 5 | 3 / 6.0 / 5 | 3 / 6.0 / 5 | 6 / 6.0 / 5 | 26 / 6.0 / 5 |

Reading notes that are easy to get wrong:

- **`GET /runs?limit=50` reads 187.9 KiB at 25 runs** because 25 < 50: the page *is* the whole
  list. It is flat at 374.6 KiB from 100 onward, which is the real result.
- **`n` for the detail route is `pending_count`**, not a payload length. The detail response
  carries **no runs at all** — see §3.
- **`n` for `/revisions` is `failing_unit_count`.** That route answers no `revisions` array on a
  draft record; it answers `lifecycle` + `availability`, and the only thing inside that grows is
  `lifecycle.scientific_readiness.failing_units`.
- **`/conflicts`, `/notes` and `/assets` report `n=0`** because the synthetic record carries no
  conflicts, notes or assets. Their *time* still grows, and `/assets`' *bytes* grow — see §3.

---

## 2. The browser

| | 25 | 100 | 250 | 500 | 1000 |
|---|---|---|---|---|---|
| **record screen** load ms | 709 | 1 162 | 1 668 | 3 214 | **6 251** |
| **record screen** DOM nodes | 808 | 1 186 | 1 186 | 1 186 | **1 186** |
| **record screen** API requests | 27 | — | — | — | **27** |
| long tasks | 0 | 0 | 0 | 0 | **0** |
| search (server round trip) ms | 810 | 815 | 814 | 809 | **816** |
| Focus Run ms | 51 | 44 | 49 | 44 | **36** |
| expand first card ms | 58 | 44 | 40 | 57 | **44** |
| expand last card ms | 48 | 38 | 36 | 41 | **38** |
| **Discard controls rendered** | 1 | 1 | 1 | 1 | **1** |
| **Evidence Graph** ms | 533 | 668 | 1 113 | 1 108 | **1 633** |
| **Evidence Graph** DOM | 755 | 1 243 | 1 243 | 1 243 | **1 243** |
| **Evidence Graph** API requests | 27 | 27 | 27 | 27 | **27** |
| **Evidence Graph** long tasks | 0 | 0 | 0 | 0 | **0** |
| **Compare Runs** (both on page) ms | 541 | 1 116 | 1 643 | 3 686 | **7 663** |
| **Compare Runs** (both on page) requests | 31 | 31 | 31 | 31 | **31** |
| **Compare Runs** (both on page) DOM | 1 114 | 1 492 | 1 492 | 1 492 | **1 492** |
| **Compare Runs** (deep-linked) ms | 526 | 1 132 | 2 178 | 3 182 | **5 659** |
| **Compare Runs** (deep-linked) requests | 31 | 32 | 32 | 32 | **32** |

The Evidence Graph's own disclosure line is flat from 100 runs onward —
`"54 of 120 nodes drawn · 53 of 182 relationships"` at 100, 250, 500 **and** 1000, against
`"29 of 70 nodes drawn · 28 of 107 relationships"` at 25.

### The record screen's requests, attributed — and one figure that would have been a false finding

The record screen issues a **constant 27** API requests at 25 runs and at 1,000. Per route,
with bounded and unbounded `/pending` deliberately kept apart (they are the same path and are
2 910.9 KiB vs 49.6 KiB apart at 1,000 runs):

| screen | unbounded `/pending` | windowed `/pending?limit=` | total requests |
|---|---:|---:|---:|
| record | **2** | 1 | 27 |
| Export Readiness | **2** | 2 | 21 |

> **THE `×2` IS REACT STRICTMODE, NOT DUPLICATE PRODUCTION TRAFFIC.** `src/main.tsx:25` wraps
> the app in `<StrictMode>`, which double-invokes effects in development, and the Vite dev
> server these benchmarks drive is a development build. Essentially *every* route in the tally
> reads ×2, which is the signature. **The production figure is half of each: one unbounded
> `/pending` per screen load, not two.** Reported this way because "the record screen fetches
> 5.8 MiB of blockers twice" would have been a striking finding and a false one.

**So at 1,000 runs the record screen downloads ~2.9 MiB of unbounded `/pending` per load** (this
dev measurement: ~5.8 MiB), which is the dominant term in `load ms` and is the design described
in §3(c) rather than a defect.

**Three things this branch added are bounded, and it is worth saying so explicitly because the
question was open:**

- **The Evidence Graph's five sub-fetches do not multiply.** 27 API requests at 25 runs and 27 at
  1,000; DOM flat at 1,243; long tasks 0 at every count. `evidenceGraph.ts` bounds every axis it
  draws (`MAX_EVIDENCE_GRAPH_NODES`, `MAX_VISIBLE_EVIDENCE_NODES`, `MAX_GRAPH_CONFLICTS`,
  `MAX_GRAPH_NOTES`, `MAX_GRAPH_ASSET_REFS`) and discloses each in words.
- **Compare Runs costs a constant number of reads.** 31 with both runs on the loaded page; **32**
  when one is deep-linked and must be fetched — exactly the one extra `getRun` its header
  describes, and it does not become two or N. DOM flat at 1,492.
- **Discard renders once per record, not once per run.** 1 control at 25 runs and 1 at 1,000.

---

## 3. What still scales, named precisely

**(a) `GET /revisions` is the single most expensive route in the application at scale — 942 ms
at 1,000 runs**, 4.6× the detail route and roughly 70× each of the other four graph sub-fetches.
It is linear in both time (~0.94 ms/run) and bytes (~175 B/run). **This branch put it on the
Evidence Graph's load path**, where it was previously reached only from Export Readiness. §4
attributes the cost.

**(b) The detail route's payload is FLAT and its latency is LINEAR** — 1.5 KiB at every count,
7 ms → 205 ms. Measured: `GET /api/experiments/{id}` carries `id`, `title`, `scenario`,
`status`, `pending_count`, `evidenced_field_count`, `exported`, `record_id`, `draft_ok`,
`artifact_refs`, `source_files`, `workflow`, `artifact`, `rev`, `updated_utc`, `version` — **no
`state`, no `runs`, no drafts**. So nothing in the response can grow; what grows is the
*derivation* of `pending_count`, `draft_ok`, `workflow` and `artifact`, each of which composes
every run.

**(c) `GET /pending` unbounded is linear and unbounded BY DESIGN** — 2 910.9 KiB / 3 002 entries
at 1,000 runs. This is correct and must not be "fixed": a caller asking what is unresolved gets
the complete truth. The bounded form is what a caller opts into, and it is flat.

**(d) `GET /assets` grows in bytes despite carrying zero assets** — 1.9 → 66.5 KiB, ~66 B/run.
Traced to `_assets_payload`, which embeds `[{id, label, ordinal} for run in exp.sorted_runs()]`
with a stated reason: *"`runs` is included because associating an asset needs the record's runs
and a client should not have to make a second read to draw the control."* That is the whole
option list of a control, so it is linear **and correct**; at 66 B/run it is ~5% of what the run
list itself costs. **Named, not filed as a defect.**

**(e) `load ms` and both Compare Runs timings still grow.** The record screen issues a constant
**27** requests at 25 and at 1,000 runs, so the growth is per-request cost, not request count —
principally the unbounded `/pending` it fetches for Review Record plus the linear detail route.

---

## 4. The two prior server-side issues: which hold, and which do not

### The unbounded `/pending` payload — **FIXED, AND THE FIX HOLDS.**

`GET /pending?limit=50` is **flat at 49.6 KiB and exactly 50 entries at every count from 25 to
1,000**, against 75.6 KiB → 2 910.9 KiB unbounded. `serialize.PENDING_WINDOW = 50` is present and
the anchored window is documented at `serialize.py:695-844`.

**And the two unbounded call sites are still correct and were not touched.** `api.getPending`
(no parameters) is called by `getReviewBundle` (`api.ts:2136`) and `getExportReadiness`
(`api.ts:2154`) — Review Record and Export Readiness — where a windowed read would UNDERSTATE
outstanding work from a page. Confirmed by reading, not assumed.

### Linear detail-route latency — **THE MULTIPLE IS GONE; THE LINEARITY IS NOT.**

Both threading seams are present (`routes._shared_units` at `routes.py:1233`,
`routes._shared_dry_run` at `:1282`) and **measurably working**. Call counts per request at 500
runs, taken by wrapping the methods over the real surface:

| route | ms | `export_units` | `resolved_run_draft` | `export_draft` | `pending` |
|---|---:|---:|---:|---:|---:|
| `GET /revisions` | 452 | 1 | 500 (**1×**) | **500 (1×)** | 1 |
| `GET /experiments/{id}` | 109 | 1 | 500 (**1×**) | **0** | 0 |
| `GET /pending` | 64 | 0 | 0 | 0 | 1 |

`resolved_run_draft` is **1× the run count, not 3× or 5×** — which is precisely what
`scale-envelope-2026-08-25.md` §3A claims and this reproduces independently over HTTP. So the
threading holds. What remains is that the work is still O(runs); the fix removed the *multiple*,
which is what it set out to do.

### Why `/revisions` costs 4× the detail route — the new finding

`list_revisions` calls `_lifecycle_payload` → `submissions.blocker_report`, which does
`pending = list(exp.pending())` **and** an `export_draft` dry run **per unit**. The detail route
reaches `export_draft` **zero** times on the same record, because `status()` and `export_ready()`
both short-circuit while `pending_count() > 0`. `blocker_report` has no such short-circuit.

**And `derive_lifecycle` cannot use the result on this workload**: with `pending_count > 0` the
state is `draft` regardless of `failing_unit_count` (`ready_to_submit` and `needs_review` both
require `pending_count == 0`). So at 1,000 runs the route performs 1,000 dry runs whose outcome
cannot change the state it returns.

**I did not act on that**, and the reason is not caution about the code: `failing_unit_count` and
`failing_units` are **published fields**, so skipping the dry run would turn a reported number
into an absent one. That is a change to what the submission-lifecycle API asserts, and §15's
"`blocker_report` is the ONE definition of what blocks a submission" makes it an owner decision,
not a benchmark's. **It is recorded in §6 as the largest single latency item still on the table.**

---

## 5. THE DEFECT THIS SWEEP FOUND: Export Readiness held 22,267 DOM nodes

**Measured, then attributed, then fixed, then re-measured.**

`docs/run-scale-measurements.md` §1 records the record screen's unbounded "Fields Need Your
Confirmation" banner — 16,134 nodes at 1,000 runs — and the bound that reduced it to ~1,175. **The
same defect existed one screen away, larger, and the §1 fix never reached it.**

At 1,000 runs, by class:

| screen | total | top classes |
|---|---:|---|
| record | 1 186 | `run-card`×50 and siblings — bounded |
| **export-readiness** | **22 267** | **`run-finding`×1000** + twelve sibling classes ×1000 each, `mono`×4002, `lucide-triangle-alert`×1001 |
| guided-completion | 498 | `upcoming-row`×49 — bounded |
| evidence-graph | 1 243 | `evgraph-row`×54 — bounded |

`ExportReadiness.tsx:821` renders `<RunFindings runs={validate.runs} />`, and `RunFindings` did
`runs.map(...)` with no bound — one `<li className="run-finding">` per run at ~21 nodes each.

> **A trap worth recording, because the first probe fell into it.** Gated only on the Export
> heading, the probe read **152 nodes** with `skeleton×5` — it measured the *loading* state and
> reported a flat, healthy number. That is the most misleading possible result, because it looks
> like an answer. The committed probe waits for `.skeleton` to detach.
>
> **A second, smaller figure exists for the same screen and is reported rather than reconciled
> away: 21,253**, from `exportreadiness-scale.bench.ts`, which waits on the revision panel
> attaching instead of on skeletons detaching. Both are pre-fix and both are of the same defect;
> they differ because they stop at slightly different settle points. **The before/after pair in
> the table below is taken from ONE harness with ONE wait condition** (`dom-attribution`,
> 22,267 → 2,318), because a before and an after measured by different probes would not be a
> comparison.

### The fix, and why it is not "the first 50"

`RUN_FINDINGS_WINDOW = 50` (the number this product already means by a page of runs —
`PENDING_WINDOW`, `RUNS_PAGE_SIZE`), **ordered by state: `fail`, then `unavailable`, then
`pass`**, with the withheld entries named **by state** underneath.

Bounding this list by POSITION would have been a silent truncation of blockers wearing a
disclosure. The §1 banner's entries are homogeneous — every one an open question, so the first ten
are a fair sample. **These are not interchangeable**: the list exists to say *which* runs did not
pass, so a record whose failures sit after 50 passing runs would have shown a scientist fifty
green rows and hidden every failure behind "and 950 more".

Four properties the change preserves, each pinned by test
(`apps/web/src/__tests__/run-findings-bounded.test.tsx`):

1. **At or below 50, nothing changes at all** — same entries, same server order. The reorder
   engages only when the bound does.
2. **The tally is computed over the full array**, not the drawn subset: `107 runs: 100 passed · 7
   did not pass.`
3. **The withheld sentence names states**, never a bare count: *"Showing 50 of 125 runs, the ones
   needing attention first. 75 passed are not listed."*
4. **`adviceFor` stays POSITIONAL across the reorder.** It indexes `warningRuns` by position
   because both lists come from `exp.export_units()` in the same order; the original index travels
   with each entry, so the sort cannot hand run 60's advisory to whichever run is drawn third.

**Negative control, EXECUTED.** The ordering was replaced with `const ordered = entries;` (bound
by position), the file was run, and **3 of 6 failed** — verbatim
`expected [ 'Pass 0', 'Pass 1', 'Pass 2' ] to deeply equal [ 'Fail 901', 'Fail 902', 'Fail 903' ]`.
The source was restored and `cmp`-compared byte-for-byte.

### Post-fix re-measurement

| Export Readiness at 1,000 runs | before | after |
|---|---:|---:|
| **DOM nodes** | **22 267** | **2 318** (−89.6%) |
| `run-finding` elements | 1 000 | **50** |
| `mono` elements | 4 002 | **202** |
| API requests | 21 | 21 (unchanged) |

All 50 drawn rows carry `run-finding-state-fail`, confirming the failures-first ordering under a
real 1,000-run workload rather than only in a fixture.

**Corroborated by the second harness, and with the below-the-bound control measured rather than
assumed** (`exportreadiness-scale.bench.ts`, whose wait condition differs — so it is quoted as
its own before/after pair, never mixed with the one above):

| Export Readiness DOM | before | after |
|---|---:|---:|
| at **25** runs (bound must NOT engage) | 778 | **778 — unchanged** |
| at **1,000** runs | 21 253 | **1 304** (−93.9%) |

The 25-run row is the one that matters for the "invisible until it is needed" claim: below the
window the screen is byte-for-byte the screen it was.

**Files changed:** `apps/web/src/components/RunFindings.tsx`,
`apps/web/src/components/run-findings.css`, and the new
`apps/web/src/__tests__/run-findings-bounded.test.tsx`. **No backend file, no baseline file, no
truth-path file, and no snapshot was touched.**

### Verification

| check | result |
|---|---|
| `cd apps/web && npx tsc -b` | clean |
| `cd apps/web && npx vitest run` | **179 files / 4,713 passed** (from 178 / 4,707 — this slice adds one file of six tests) |
| `.venv/bin/pytest -q` | **1 failed, 6 081 passed, 39 skipped** — the one failure is `test_committed_snapshot.py::test_committed_snapshot_indexed_source_gate_dispatches`, and it is **not this slice's**: its assertion names `apps/api/tests/test_api.py`, a Stage 2b file (see below) |
| snapshot drift (`build_memory_snapshot.py --check`, read-only) | **drift reported, and NOT from this slice** — see below |

**On the snapshot.** `--check` reports the committed snapshot as drifted. Attributed rather than
assumed: none of this slice's five files appears in `snapshot["served"]` (201 paths) **or** in
`served_content_manifest` (200 entries). The two modified files that *are* in the manifest are
`apps/api/tests/test_api.py` and `apps/api/tests/test_deploy_config.py`, which belong to the
concurrent Stage 2b work in the same tree. **This slice cannot drift the snapshot, and did not
regenerate it.**

**One defect in this slice's own diff, found by review and fixed:** the new
`RUN_FINDINGS_WINDOW` constant was first inserted *between* `STATE_CLAUSE`'s docblock and
`STATE_CLAUSE` itself, orphaning a comment that exists to stop a specific false claim
("did not pass", not "failed the official ISAAC schema"). It is now placed above that docblock.
`npx tsc -b` also caught two type errors in the new test that `vitest` passed straight through —
`vitest` does not typecheck, so a green test run is not evidence the types are right.

---

## 6. What is NOT claimed, and what was NOT measured

**Tested ceiling: 1,000 runs, reached.** Nothing beyond it was measured.

**These are local numbers from one machine, one Chromium, one synthetic record, with the backend
on loopback.** What transfers is shape and ratio, not milliseconds. **No hosted figure of any kind
exists** — `/krish` sits behind an Authentik edge this environment cannot authenticate to.

Not measured, and named rather than left implicit:

- **Memory.** Deliberately, for the reason `run-scale.bench.ts` gives: `performance.memory` is a
  coarse Chromium-only whole-process estimate that cannot be compared across runs.
- **The `/revisions` dry-run short-circuit** (§4). The largest single latency item still on the
  table, ~740 ms of the 942 ms at 1,000 runs. Not attempted because it changes what a published
  field reports; it needs an owner decision, not a benchmark's.
- **Export Readiness post-fix WALL-CLOCK.** The post-fix run was taken at
  `load averages: 32.37` (the verification `pytest` was draining), so its 5 720 ms is
  contaminated and is not quoted anywhere as a result. Its DOM and request counts, which are
  contention-proof, are. The 25-run post-fix DOM **was** measured (778, unchanged).
- **`failing_units` rendered by `RevisionHistoryPanel`** was measured as **0 `<li>` at 1,000
  runs** — because a worked-example session answers `availability.state: not_applicable` and that
  panel takes a different branch. So its `.map` is **unbounded in source and unexercised in this
  scope**. Do not read the 0 as "bounded"; it is "not reached here". A durable non-tutorial record
  was not measured, and could not be in this harness.
- **Concurrency.** One browser, one worker, one record. No parallel-client behaviour.
- **Any count between the five measured**, and any count above 1,000.
- **Wall-clock as a comparison against `scale-envelope-2026-08-25.md`.** That document measured
  in-process via `TestClient`; this one measures over HTTP. Byte and call counts are comparable;
  milliseconds are not, and no ratio between the two documents is claimed. (The in-process
  cross-check in §4 was run here specifically so the call counts *are* comparable, and they agree.)

---

## 7. What this supersedes in `docs/run-scale-measurements.md`

- **§4(a) named bounding `/pending` as "the next slice"** — *"Bounding it is a contract change —
  the route has no `limit`"*. **That slice has since shipped and this sweep confirms it works**:
  `?limit=50` is flat at 49.6 KiB / 50 entries from 25 to 1,000 runs. The unbounded default is
  unchanged and still correct.
- **§4(b)'s shape holds and its number has moved.** The detail route's payload is still flat and
  its latency still linear, but at **205 ms at 1,000 runs**, not 634 ms — the `_shared_units` /
  `_shared_dry_run` threading landed in between. The *conclusion* ("there is no payload to justify
  it") is unchanged and is still the right way to read it.
- **§3's record-screen table still reproduces.** DOM 1 175 → **1 186** here (this branch adds the
  Discard control and other chrome), long tasks 0, search/focus/expand all flat. Nothing regressed.
- **§5's headline — "the cost is in the DATA, not in the rendering" — is now HALF TRUE, and this
  is the correction that matters.** It was true of the record screen and it was measured there. It
  is **false of Export Readiness**, where rendering was 22,267 nodes for a 1,000-run record —
  *larger than the 16,134* §1 calls "THE DEFECT". §5's own warning applies to itself: *a conclusion
  about where cost lives expires when the thing it was measured on changes shape*, and "the DOM is
  bounded" was never checked on any screen but one. The virtualization conclusion still stands:
  post-fix, no screen measured here exceeds 2,318 nodes, and 2,318 is nothing to virtualize.

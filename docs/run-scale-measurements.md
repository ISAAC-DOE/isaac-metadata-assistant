# High-run-count: the measured envelope, and what it rules out

> # RE-MEASURED AGAIN ON 2026-08-27 — SEE [`docs/evidence/scale-envelope-2026-08-27.md`](evidence/scale-envelope-2026-08-27.md)
>
> That sweep measured this branch's new surfaces (the Evidence Graph's five sub-fetches,
> Compare Runs' four reads, the Discard control) at **25 · 100 · 250 · 500 · 1000**, over real
> HTTP with a real Chromium. **Three of its results bear directly on this document**, and are
> recorded here rather than only there because a reader who stops at this file would otherwise
> carry away two claims that no longer hold:
>
> 1. **§4(a)'s "next slice" SHIPPED.** ~~"Bounding it is a contract change — the route has no
>    `limit` — and is named here as the next slice"~~ — `GET /pending?limit=50` now exists and is
>    **flat at 49.6 KiB / 50 entries from 25 to 1,000 runs**, against 2,910.9 KiB unbounded. The
>    unbounded default is deliberately unchanged and is still correct for Review Record and
>    Export Readiness.
>
> 2. **§4(b)'s shape holds; its NUMBER has moved.** The detail route's payload is still flat and
>    its latency still linear, but at **205 ms at 1,000 runs, not 634 ms** — the
>    `routes._shared_units` / `_shared_dry_run` threading landed in between. Do not quote 634 ms
>    as current.
>
> 3. **§5's headline is now HALF TRUE, and this is the correction that matters.** ~~"the cost is
>    in the DATA, not in the rendering"~~ was measured on the RECORD screen and is true there —
>    DOM 1,186 at 1,000 runs, re-confirmed. It is **FALSE of Export Readiness**, which held
>    **22,267 DOM nodes** at 1,000 runs (`run-finding`×1000 plus twelve sibling classes ×1000
>    each) — *larger than the 16,134* §1 above calls "THE DEFECT". The §1 bound was applied to
>    the record screen's banner and never reached the sibling screen with the same shape.
>    Now bounded to **2,318**.
>
> **§5's own lesson applies to §5**: *a conclusion about where cost lives expires when the thing
> it was measured on changes shape* — and "the DOM is bounded" had never been checked on any
> screen but one. The virtualization conclusion is unaffected: post-fix, no screen measured
> exceeds 2,318 nodes.
>
> Everything else in this document reproduced. The 2026-08-27 sweep also commits the per-class
> DOM probe whose absence §1 records ("it is NOT independently re-measurable"), as
> `apps/web/e2e/mutation/dom-attribution.bench.ts`.


> # RE-MEASURED IN FULL ON 2026-08-20 — AND IT FOUND A DEFECT THAT MADE THIS DOCUMENT'S HEADLINE CONCLUSION FALSE
>
> **Everything below the horizontal rule is the OLD measurement.** It is kept because it is what the
> new numbers are measured against, and because two of its conclusions were right and one has been
> overturned. Read this block first; the body of the document is history.
>
> The browser-side half of this document had been un-re-measured through the paging slice, the run
> browser, the field-adoption change and everything since, and said so. This is the re-measurement,
> with the four things §23 asked for and the old harness did not have: a **paged** read, **search**
> latency, **Focus Run** latency, and a corrected long-task observer.
>
> ## 1. THE DEFECT: the record screen's DOM cost was not the run cards. It was the pending banner.
>
> At 1000 runs the record screen held **16,134 DOM nodes**. The Run browser's cards were **50** of
> them — it pages at `RUNS_PAGE_SIZE`. A DOM probe attributed the rest:
>
> | class | count |
> |---|---:|
> | `needsyou-item` / `needsyou-num` / `needsyou-q` / `needsyou-about` / `mono` | **3,002 each** |
> | `run-card` | 50 |
> | everything else together | ~~under 700~~ **~1,074** |
>
> *(`under 700` CORRECTED 2026-08-24 by an independent truthfulness review. It contradicted this table's own arithmetic: 16,134 − (3,002 × 5 = 15,010) − 50 = **1,074**. The document's post-fix figure corroborates it — 16,134 − (2,992 × 5) = 1,174, against the 1,175 reported — implying a non-banner baseline of ~1,125. The five-nodes-per-item markup is confirmed at `RecordWorkbench.tsx:552-577`. It is NOT independently re-measurable: the per-class DOM probe was never committed — `run-scale.bench.ts:243` records only `getElementsByTagName('*').length` — so this correction is arithmetic over the table's own published numbers, not a fresh measurement, and is labelled as such.)*
>
> `RecordWorkbench`'s "Fields Need Your Confirmation" banner rendered **every** blocking question:
> 1000 runs × 3 run-level questions + 2 record-level = 3,002 list items at five nodes each. ~15,000
> of the 16,134.
>
> **So this document's headline — "The DOM is not the problem, and this is the finding that redirects
> the work" — was TRUE WHEN IT WAS MEASURED AND IS NOW FALSE.** Not because the measurement was
> wrong: at the time the run count WAS the card count, so this list was as short as the card list. It
> went false when runs began paging and this banner did not. That is worth stating precisely, because
> the wrong lesson to draw is "the old measurement was sloppy". The right one is that a conclusion
> about where cost lives expires when the thing it was measured on changes shape.
>
> **A second defect in the same place, and it is a correctness one.** The list was keyed on `p.id`.
> A run-owned question's `id` is its KIND — `series`, `qc`, `descriptor` — so a record with N runs
> produced N identical `<li key="series">`. Duplicate React keys, on the first screen a scientist
> opens. Now keyed on `blocker_key`.
>
> ## 2. The fix is one bound, and this is what it bought
>
> The banner now lists the first **10** and states the remainder in words — *"Showing the first 10 of
> 3002. 2992 more are waiting"* — with the full count still in the title, because a truncated list
> that read as complete would be worse than a slow one.
>
> | at 1000 runs | before | after |
> |---|---:|---:|
> | DOM nodes | 16,134 | **1,175** |
> | expand first card | 127 ms | **44 ms** |
> | expand last card | 124 ms | **39 ms** |
> | Focus Run | 287 ms | **46 ms** |
> | paged read (`limit=50`) | 234 ms | **36 ms** |
> | long tasks | 3 | **0** |
> | load (navigation → usable) | 10,009 ms | 6,681 ms |
>
> **DOM is now FLAT above the first page** — 1,172 at 50 runs, 1,175 at 1000. So is expand, so is
> Focus Run, so is search, and long tasks are 0 at every count including 1000. Five columns that
> degraded no longer do.
>
> ## 3. The full table, after the fix
>
> Local machine, Chromium, backend on loopback, `workers: 1`, `retries: 0`. **These are not a promise
> about any deployment**; what transfers is the shape and the ratios.
>
> | runs | unpaged ms | unpaged KiB | paged ms | paged KiB | inh/run | load ms | cards | DOM nodes | expand 1st | expand last | search ms | focus ms | long tasks |
> |---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
> | 25 | 16 | 188 | 18 | 188 | 15 | 773 | 25 | 797 | 65 | 35 | 808 | 49 | 0 |
> | 50 | 28 | 375 | 28 | 375 | 15 | 805 | 50 | 1 172 | 41 | 39 | 808 | 41 | 0 |
> | 100 | 53 | 748 | 29 | 375 | 15 | 1 126 | 50 | 1 175 | 38 | 40 | 811 | 46 | 0 |
> | 250 | 130 | 1 869 | 31 | 375 | 15 | 2 151 | 50 | 1 175 | 41 | 38 | 814 | 45 | 0 |
> | 500 | 274 | 3 736 | 32 | 375 | 15 | 3 648 | 50 | 1 175 | 42 | 39 | 811 | 40 | 0 |
> | 1000 | 570 | 7 472 | 36 | 375 | 15 | 6 681 | 50 | 1 175 | 44 | 39 | 808 | 46 | 0 |
>
> Reproduce: `E2E_BENCH_COUNTS=25,50,100,250,500,1000 npm run bench:runs`. The paged column, the two
> interaction columns and the ceiling row all have a committed reproduction path now; the old
> document said its paging figures did not.
>
> **`cards` is capped at 50 by the product, not by the harness**, and the harness's final assertion
> was WRONG about that: it asserted `cards == COUNTS[last]`, which was right while the Runs section
> rendered the unpaged list and false since the Run browser landed. The 1000-run row would have
> failed it after a 30-minute run, and the failure would have read as a performance problem. It now
> asserts the capped count **and** that the runs really exist, because a capped count alone would
> pass for a harness that created none.
>
> **`search ms` is ~810 at every count and is NOT a scale finding.** 300 ms of it is
> `RUN_SEARCH_DEBOUNCE_MS` and the rest is a round trip — the Run browser matches on the SERVER, so
> nothing here is filtered in the browser. It is flat, which is the useful fact. *An earlier pass of
> this benchmark read 369/419 ms at 500/1000 and ~810 below that; those two figures came from the
> pre-fix runs where the page was busy, and the post-fix column is uniform. The inversion is not
> explained here and is not needed for any conclusion.*
>
> ## 4. TWO SERVER-SIDE COSTS THAT STILL SCALE, AND ONE OF THEM IS THE MORE INTERESTING RESULT
>
> `load ms` still grows — 805 ms at 50 runs to 6,681 ms at 1000 — while the list the page fetches is
> flat at 375 KiB. So the remaining cost is not the run list. Measured directly, in process
> (`TestClient`, no network):
>
> | runs | `GET /pending` | entries | `GET /experiments/{id}` | detail KiB |
> |---:|---:|---:|---:|---:|
> | 25 | 75.7 KiB / 4.7 ms | 77 | 15.3 ms | 1.5 |
> | 100 | 293.9 KiB / 14.2 ms | 302 | 66.7 ms | 1.6 |
> | 250 | 730.7 KiB / 34.3 ms | 752 | 151.5 ms | 1.6 |
> | 1000 | **2 914.8 KiB / 133.7 ms** | **3 002** | **634.2 ms** | **1.6** |
>
> **(a) `/pending` is unbounded — 2.9 MiB at 1000 runs.** The banner's RENDER is bounded now; its
> FETCH is not. This is the payload behind `load ms`. Bounding it is a contract change — the route
> has no `limit` — and is named here as the next slice rather than half-done at the end of a long
> one.
>
> **(b) The detail route's payload is FLAT at 1.6 KiB and its latency grows LINEARLY to 634 ms.**
> This is the more interesting number in the whole benchmark, because there is no payload to justify
> it: the response does not contain the per-run work it does. It derives every blocking question in
> order to report `pending_count`, then returns the count. At 1000 runs that is 3,002 derivations for
> one integer. Nothing about this is fixed by paging anything.
>
> ## 5. What is NOT claimed
>
> **Tested ceiling: 1000 runs**, and that is now re-established rather than inherited — the previous
> ceiling rested on a browser run that predated a 76% payload growth, and this document said to treat
> it as unverified. Nothing beyond 1000 was measured and nothing here supports a claim beyond it.
>
> **The envelope is not "fine".** At 1000 runs a scientist waits ~6.7 s for the record screen. That
> is better than the ~10 s before the fix and it is not good, and the two costs in §4 are where the
> remaining seconds are. **Do not read "DOM is flat" as "scale is solved".**
>
> **The old conclusion that survives**: the cost is in the DATA, not in the rendering — now true for a
> second, sharper reason than when it was written. Virtualization is still ruled out: 1,175 nodes is
> nothing to virtualize.
>
> ---
>
> ## RE-MEASURED AGAIN, LATER ON 2026-08-19 — THE ×1.76 "GROWTH" LOOKS LIKE TWO DIFFERENT RUN SHAPES
>
> **Read this before the block below it.** That block reports the per-run payload growing from
> ≈7.47 KiB to 13.12 KiB and attributes it to features landing since 2026-08-12. Measured three
> ways today, the ×1.76 is better explained by the PROBE changing than by the payload growing —
> and if that is right, the older figure was never superseded, it was measuring a different thing.
>
> | How the runs were created | KiB/run | What each run carries |
> |---|---:|---|
> | `add_run(draft=deepcopy(full_draft))` — the reproduction command below | **13.12** | its OWN copy of a 26-entry field map |
> | `POST /api/experiments/{id}/runs` on the SAME full-field record | **7.48** | no own fields; the 26 arrive as `inherited` |
> | `POST .../runs` on a record CREATED IN THE APP | **0.41** | no own fields, and almost nothing to inherit |
>
> Linear in every case (7.52 at 25 runs, 7.48 at 100; 0.42 at 25, 0.41 at 100 and 250).
>
> **Why the middle row matters.** `_run_view` serialises the run's own `fields` and its `inherited`
> resolution — not its `series`, `qc` or `descriptors_outputs`. So a run that owns a field map pays
> for it twice (once as its own copy, once resolved) and a run that inherits pays once. A
> deep-copied draft is the first shape; every run the API creates is the second.
>
> **7.48 is within 0.01 KiB of the 7.47 this document reported for the older measurement.** That
> coincidence, plus the mechanism above, is why the growth claim is doubted here. It is **not
> proof**: the older probe is not recorded in this document, so what it did cannot be checked, and
> the honest statement is that the two figures are consistent with measuring inherited-only and
> own-fields runs respectively rather than with a 1.76× increase over time. Whoever wrote the block
> below may have had a reason this reader cannot see.
>
> **What is NOT in doubt, and is the useful part.** Every figure is linear in run count, and the
> cost is in the DATA rather than the rendering — which is the conclusion the body of this document
> reaches and which none of this disturbs. The planning number depends on which shape you expect:
>
> * **0.41 KiB/run** is what the product produces TODAY for a record created in it, because the
>   campaign-sheet fields (technique, facility, sample, contributors) still have **no capture
>   surface**. At 1000 runs that is ≈400 KiB unpaged.
> * **7.5 KiB/run** is what the same product will produce the moment those fields CAN be captured,
>   because they become inherited content on every run. ≈7.3 MiB unpaged at 1000 runs.
> * **13.1 KiB/run** is the worst case, reachable only if a run acquires its own copy of the field
>   map. No API path does that today.
>
> So the envelope is conditional on a capability that does not exist yet, and a ×18 jump is waiting
> behind it. That is worth knowing before anyone treats 0.41 as the answer.
>
> Read latency, same runs, same process (`TestClient`, so no network): 15 ms unpaged at 25 runs,
> 52 ms at 100 for the 7.5 KiB/run shape; 3/5/10 ms at 25/100/250 for the 0.41 shape. Exporting 25
> runs — 25 official records and 25 sidecars — took 0.3 s. **These are process-local timings and
> are not a browser measurement**; the DOM, long-task and initial-load figures the body of this
> document discusses are still not re-measured.
>
> Reproduce the middle and bottom rows:
>
> ```bash
> PYTHONPATH=apps/api:src .venv/bin/python - <<'EOF'
> import os, tempfile, copy, time
> os.environ['ISAAC_UI_WORKSPACE'] = tempfile.mkdtemp()
> from isaac_api.app import create_app
> import isaac_api.workspace as ws
> from fastapi.testclient import TestClient
> c = TestClient(create_app(), raise_server_exceptions=False)
> EID = '01SCALEAPIPATH000000000001'
> exp = ws.create_experiment('full-field record', {'kind': 'synthetic'},
>                            copy.deepcopy(ws._full_draft()), id=EID)
> exp.save_versioned()
> def v(): return c.get(f'/api/experiments/{EID}').json()['version']
> for target in (25, 100):
>     while len(ws.load_experiment(EID).sorted_runs()) < target:
>         c.post(f'/api/experiments/{EID}/runs',
>                json={'label': f'run {len(ws.load_experiment(EID).sorted_runs())+1}'},
>                headers={'If-Match': f'"{v()}"'})
>     b = len(c.get(f'/api/experiments/{EID}/runs').content)
>     print(f'{target:>4} runs  {b/1024:8.1f} KiB  {b/target/1024:6.2f} KiB/run')
> EOF
> ```
>
> For the 0.41 row, create the record with `POST /api/experiments` instead and answer it through
> `POST /answers` — the difference is entirely in how many fields the record carries.

> ## RE-MEASURED 2026-08-19 — THE HEADLINE PER-RUN FIGURE IS 1.76× WHAT THIS DOCUMENT SAYS
>
> Everything below was measured on or before **2026-08-12**. Since then the run payload has grown:
> asset references, unified provenance, unmapped notes, revision history, transcript capture, run
> removal and conflict resolution all landed. The programme plan warned about exactly this — *"do not
> reuse old Run-scale numbers as final proof"* — so the per-run payload was re-measured.
>
> | | This document | **Re-measured 2026-08-19** | Change |
> |---|---|---|---|
> | Unpaged payload per run | ≈7.47 KiB | **13.12 KiB** | **×1.76** |
> | `limit=50` response | 374 KiB *(asserted, no reproduction path)* | **656 KiB** | ×1.75 |
> | Implied unpaged at 1000 runs | 7.47 MiB | **≈12.8 MiB** | ×1.76 |
>
> **The per-run cost is exactly linear**, which is what makes the extrapolation safe to state: 328.1
> KiB at 25 runs, 1312.2 KiB at 100, 3280.7 KiB at 250 — 13.12 KiB/run at all three, to two decimal
> places. So the *shape* of the finding below is unchanged and its conclusion still holds: the cost is
> in the DATA, not the rendering, and bounding the data is the answer. Only the constants moved.
>
> **Reproduce it — and note this path is more reproducible than the paging figures below**, which this
> document already admits are asserted rather than harness output. This needs no browser and no
> Playwright config:
>
> ```bash
> PYTHONPATH=apps/api:src .venv/bin/python - <<'EOF'
> import os, tempfile, copy
> os.environ['ISAAC_UI_WORKSPACE'] = tempfile.mkdtemp()
> from isaac_api.app import create_app
> import isaac_api.workspace as ws
> from fastapi.testclient import TestClient
> c = TestClient(create_app(), raise_server_exceptions=False)
> EID = '01SCALEPROBE00000000000001'
> exp = ws.create_experiment('scale probe', {'kind': 'synthetic'},
>                            copy.deepcopy(ws._full_draft()), id=EID)
> draft = copy.deepcopy(exp.draft)
> for n in (25, 100, 250):
>     while len(exp.sorted_runs()) < n:
>         exp.add_run(label=f'run {len(exp.sorted_runs())+1}', draft=copy.deepcopy(draft))
>     exp.save_versioned()
>     b = len(c.get(f'/api/experiments/{EID}/runs').content)
>     print(f'{n:>4} runs  {b/1024:8.1f} KiB  {b/n/1024:6.2f} KiB/run')
> print('limit=50:', len(c.get(f'/api/experiments/{EID}/runs',
>                              params={'limit': 50}).content) / 1024, 'KiB')
> EOF
> ```
>
> **WHAT THIS RE-MEASUREMENT DOES NOT COVER, stated so the table is not over-read.** It measures the
> API payload only — the thing this document identifies as where the cost lives. It does **not**
> re-measure DOM node counts, initial browser load, long tasks, search/filter responsiveness or
> Focus Run, all of which are below and all of which are now equally stale. Those need the browser
> benchmark (`npm run bench:runs`, with `E2E_BENCH_COUNTS` for the 1000 row), which was not re-run.
> **Do not quote the browser-side figures below as current.**
>
> **THE TESTED CEILING IS THEREFORE NOT RE-ESTABLISHED.** This document's ceiling claim rests on a
> 1000-run browser run that has not been repeated since the payload grew by 76%. Treat the ceiling as
> **unverified at the current data model** rather than as measured.


**Status: measurement complete; it changed the plan.** Virtualization/windowing is the reflexive
answer to "the run list is long". **These measurements rule it out** — rendering is not where the
cost is — and point at bounding the *data* instead.

*An earlier revision attributed the virtualization proposal to "the roadmap's scale item". No such
document is in this repository: `git grep -a -i "virtuali"` finds, outside this file, one unrelated
a11y comment, and nothing matches `*roadmap*`. The proposal came from the working brief this phase
was authorised from, which is not committed here. Corrected so the framing does not cite a source a
reader cannot open — the measurements below stand on their own either way.*

**Reproduce:** `npm run bench:runs` (see `apps/web/e2e/mutation/run-scale.bench.ts`). It is a
`*.bench.ts`, collected by **neither** Playwright config by default, and nothing in CI runs it.
Two limits on that word *reproduce*, both real:

- the default `COUNTS` stops at **500**. The 1000-run row every headline figure cites — 7.47 MiB,
  12 326 nodes, 10.3 s, the tested ceiling — needs `E2E_BENCH_COUNTS=25,50,100,250,500,1000`;
- the benchmark reads the **unpaged** endpoint only. It never sends `limit` or `offset`, so the
  paging figures quoted in the commit that introduced them (at 1000 runs: unpaged 543 ms / 7474 KiB
  → `limit=50` 30 ms / 374 KiB → `limit=200` 103 ms / 1495 KiB) have **no committed reproduction
  path**. They are internally consistent with this table at ≈7.47 KiB/run, and an independent review
  measured the same 7.47 KiB/run over 201 runs — but they are asserted, not reproducible, and are
  labelled as such rather than presented as harness output.

---

## 1. What was measured

One record (`SEED.fresh`, the XANES example), which carries real record-level content — **15
inherited addresses per run**. That number matters more than any other input here, and using a bare
experiment instead of a seeded one is the single easiest way to get a falsely reassuring result: a
freshly created experiment resolves **1** inherited address, so its payload is ~15× smaller and its
API time ~10× lower. An earlier probe did exactly that and produced "the backend is not the
bottleneck", which the table below shows is false.

Local machine, Chromium, backend on loopback, `workers: 1`, `retries: 0`. **These are not a
promise about any deployment.** What transfers is the *shape* and the *ratios*, not the milliseconds.

| runs | API ms | payload | inh/run | load ms | cards | DOM nodes | expand 1st | expand last | long tasks |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 25 | 15 | 187 KiB | 15 | 627 | 25 | 626 | 66 | 37 | 0 |
| 50 | 28 | 373 KiB | 15 | 628 | 50 | 926 | 43 | 40 | 0 |
| 100 | 59 | 747 KiB | 15 | 1 102 | 100 | 1 526 | 45 | 44 | 0 |
| 250 | 139 | 1.87 MiB | 15 | 2 199 | 250 | 3 326 | 67 | 69 | 0 |
| 500 | 274 | 3.74 MiB | 15 | 4 016 | 500 | 6 326 | 90 | 99 | 5 |
| 1000 | 560 | 7.47 MiB | 15 | 10 288 | 1000 | 12 326 | 183 | 169 | 14 |

`load ms` is navigation → *every* card present **and** `Add Run` enabled. Deliberately not
first-paint: first-paint is flat by construction and says nothing about the tail.

---

## 2. What the numbers say

**The DOM is not the problem, and this is the finding that redirects the work.** A collapsed card
costs **exactly 12 DOM nodes** (626 nodes at 25 runs → 12 326 at 1000). *An earlier revision said
"the slope is 11.9/card". That number is not produced by these data under any fit: every consecutive
pair gives exactly 12.0, and so does the endpoint slope (12 326 − 626)/975. Corrected rather than
quietly deleted, because a figure that no arithmetic on the published table reproduces is the kind of
claim this document exists to make checkable.* 12 326 nodes
is an unremarkable page. `RunCard` mounts its heavy children inside `{expanded && …}`, so a collapsed
card really is just a header — the existing design already got the expensive half right.

**Expand latency does not degrade at the tail.** The last card behaves like the first at every count
(37/66 at 25 runs; 169/183 at 1000). Whatever slows down at 1000 runs, it is not "this card is far
down the list". Interaction with one run is not gated on the others.

**The cost is the payload.** API time and bytes are both cleanly linear in run count
(≈0.56 ms and ≈7.6 KiB per run). At 1000 runs the client receives **7.47 MiB** of JSON.

*An earlier revision added "and `load ms` tracks them at roughly 2.5×, which is transfer + parse +
render". That is withdrawn: the measured load/API ratios in this very table are 41.8, 22.4, 18.7,
15.8, 14.7 and 18.4, none of them near 2.5. What the table does support is weaker and worth stating
plainly — `load ms` grows monotonically with payload, and grows FASTER than linearly at the top end
(500 → 1000 runs doubles the runs and multiplies load by 2.56×). The relationship is superlinear at
the tail, which is the opposite of what "tracks at 2.5×" implies.*

**Where it comes from is the part worth naming.** `inherited` is computed per run, and for runs that
override nothing — the normal case — **every run carries a byte-identical copy of the same 15
record-level payloads**. At 1000 runs the response contains ~15 000 resolutions of which ~15 are
distinct. The payload is dominated by repetition, not by run content.

**Long tasks appear at 500** — and the *magnitudes* in this table's `long tasks` column are not
trustworthy, so only that directional statement survives.

*The harness registered its `PerformanceObserver` with `addInitScript` INSIDE the per-count loop.
`addInitScript` accumulates rather than replaces, so the k-th row navigated with k observers all
incrementing one counter, and the column reported roughly k × the true count. Reproduced standalone:
after four registrations a single long task read as 4. The 500-run row is iteration 5, so its "5"
is about 1. The harness is fixed (the observer is now installed once, outside the loop), but **the
column in this table was captured before the fix and has NOT been re-measured** — re-running the
benchmark is the only thing that will correct it. The 0 at 250 and below is still meaningful (k × 0
is 0), so "the first long tasks appear at 500" holds; "multiply by 1000" does not. Note also that
the observer counts long tasks from the two expand/collapse interactions as well as from load, so
even a corrected column is a per-visit total and not purely parse/render.*

### The envelope, stated as a scientist would feel it

| runs | load | verdict |
|---:|---|---|
| ≤ 100 | ≈1.1 s | comfortable |
| 250 | ≈2.2 s | noticeable, usable |
| 500 | ≈4.0 s | bad; first long tasks |
| 1000 | ≈10.3 s | unusable |

**Tested ceiling: 1000 runs.** It renders correctly and stays interactive once loaded — it is the
*wait* that fails, not the list. Nothing here supports a claim beyond 1000, and nothing was measured
beyond it.

---

## 3. What this rules in and out

**Ruled OUT — windowing/virtualization.** It reduces DOM nodes, and DOM nodes are already cheap
(~12/card, flat expand latency). It would add real complexity — scroll restoration, focus management
across recycled rows, screen-reader semantics for a list whose items are not all present — to fix a
cost that is not being paid. It would not remove a single byte from the 7.47 MiB.

**Ruled IN — bounding the data.** Fetching a bounded page of runs cuts payload, parse, render and
long tasks together, because they are all downstream of the same bytes. This is the "simplest
appropriate strategy" the roadmap asks for.

**Also ruled in, and larger — stop repeating `inherited`.** Sending record-level resolutions once per
*experiment* plus per-run overrides would attack the redundancy directly rather than paginating
around it. It is an API contract change affecting the override panel, so it is recorded here as the
structural follow-up rather than folded into the first slice.

**Not a fix on its own — search/filter/Focus Run.** They are genuine scientist needs at high run
counts, and they help only if the filtering happens where the data is bounded. A client-side filter
over an already-downloaded 7.47 MiB has already paid the whole cost.

---

## 4. Honest limits of this measurement

- **One machine, loopback backend.** Real deployments add network transfer to a payload whose growth
  is the finding — so the hosted picture is *worse* than this table, not better.
- **No memory number.** `performance.memory` is Chromium-only, coarsely quantised, and reports the
  whole renderer; it would look authoritative and compare across nothing. Long-task counts are
  reported instead.
- **All runs are empty.** They carry no field values of their own, so per-run content contributes
  almost nothing to the payload here. A workspace of *filled* runs would be larger — this table is a
  floor.
- **Timings include the harness.** `load ms` is measured from Playwright, including its own
  navigation overhead. Differences between rows are meaningful; absolute values are not a browser
  performance profile.

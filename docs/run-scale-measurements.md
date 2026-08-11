# High-run-count: the measured envelope, and what it rules out

**Status: measurement complete; it changed the plan.** The roadmap's scale item names
"virtualization" among its candidate fixes. **These measurements rule virtualization out** —
rendering is not where the cost is — and point at bounding the *data* instead. Recorded here so the
choice is traceable to numbers rather than to the word appearing in a roadmap.

**Reproduce:** `npm run bench:runs` (see `apps/web/e2e/mutation/run-scale.bench.ts`). It is a
`*.bench.ts`, collected by **neither** Playwright config by default, and nothing in CI runs it.

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
costs **~12 DOM nodes** (626 nodes at 25 runs → 12 326 at 1000; the slope is 11.9/card). 12 326 nodes
is an unremarkable page. `RunCard` mounts its heavy children inside `{expanded && …}`, so a collapsed
card really is just a header — the existing design already got the expensive half right.

**Expand latency does not degrade at the tail.** The last card behaves like the first at every count
(37/66 at 25 runs; 169/183 at 1000). Whatever slows down at 1000 runs, it is not "this card is far
down the list". Interaction with one run is not gated on the others.

**The cost is the payload.** API time and bytes are both cleanly linear in run count
(≈0.56 ms and ≈7.6 KiB per run), and `load ms` tracks them at roughly 2.5×, which is transfer +
parse + render. At 1000 runs the client receives **7.47 MiB** of JSON.

**Where it comes from is the part worth naming.** `inherited` is computed per run, and for runs that
override nothing — the normal case — **every run carries a byte-identical copy of the same 15
record-level payloads**. At 1000 runs the response contains ~15 000 resolutions of which ~15 are
distinct. The payload is dominated by repetition, not by run content.

**Long tasks appear at 500 and multiply by 1000** (0 → 5 → 14), consistent with parse/render of a
multi-megabyte response rather than with per-card work.

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

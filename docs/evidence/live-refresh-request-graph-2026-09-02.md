# The record screen's live-refresh request graph — measured, 2026-09-02

**What this document is.** The before/after request graph of the Record Workbench when
something changes elsewhere, and the argument for the three changes made to it. Every
number here was produced by a command that is quoted beside it. Numbers that could not
be produced are named as such rather than estimated.

**Branch** `feat/bounded-live-refresh-data-path`, based on `origin/main` `504c2ee`.

---

## 1. What was there, and why no test could see it

The record screen runs **two** pollers, both at an 8 s cadence with ±20 % jitter:

| Poller | Asks | On a change |
|---|---|---|
| `useRecordSync` | conditional `GET /api/experiments/{id}` with the held ETag | 200 → `onChange(fresh)` → `bundle.reloadSilent()` |
| `useChangeFeed` | `GET /api/experiments/{id}/changes?cursor=…` | entries → `summariseChanges` → `needsCanonicalRefetch` → `bundle.reloadSilent()` |

Neither knew about the other. `bundle.reloadSilent()` re-runs `api.getRecordBundle`,
which is **nine** requests, one of which is the **unbounded** `GET /pending` — the
record's entire open-question list, 3,000 entries / 1.77 MB at 1,000 runs (the column in
`useRecordSession.AGENT_CONTEXT_PENDING_WINDOW`). The screen renders **ten** of them.

Worse than "twice": while a refetch is outstanding the screen has not yet adopted the new
version, so `useRecordSync` keeps answering 200 on **every** subsequent tick and each one
started another full bundle. The measured figure below is four, not two.

None of this was visible to any existing test, because every existing test asserts what
is **on screen**, and four identical refetches render exactly what one renders. The
defect was only ever observable as a **count**.

---

## 2. Method

### 2.1 Request counts — vitest, exact

A probe mounted the real `RecordWorkbench` through `AppRoutes` against the repository's
own `stubFetchRoutes` fixture harness, with fake timers, `Math.random` pinned to 0.5 (so
jitter is exactly 1×) and `document.visibilityState` forced visible, and tallied every
recorded URL. Scenarios were driven by the two routes the pollers read:
`GET {id}` (with real `If-None-Match` semantics and a `hold` switch that answers 304
while the body has already moved — the state the two pollers are in when the feed wins
the race) and `GET {id}/changes` (one-shot, modelling cursor advancement).

**Before** and **after** are the SAME probe on the SAME tree, with the slice's two
behavioural changes reverted for the "before" run by replacing

```ts
const reloadFromSignal = () => {
  if (refetchInFlightRef.current) return;   //  ← the coalescing gate
  refetchInFlightRef.current = true;
  liveRefreshRef.current = true;            //  ← the bounded live read
  bundle.reloadSilent();
};
```

with `const reloadFromSignal = () => { bundle.reloadSilent(); };`, which is exactly what
the two call sites did at `504c2ee`. Same fixtures, same timers, same machine.

```bash
cd apps/web && npx vitest run src/__tests__/zz-probe-request-graph.test.tsx
```

*(The probe file was temporary and is not committed; the committed guard that pins the
same properties is `apps/web/src/__tests__/live-refresh-request-graph.test.tsx`.)*

### 2.2 Bytes and DOM — Playwright, real browser and real backend

`apps/web/e2e/mutation/live-refresh-request-graph.bench.ts`, run against a real FastAPI
backend in an isolated worked-example session. Response body bytes come from
Playwright's own `request.sizes().responseBodySize`, not from a body the bench reads.

```bash
cd apps/web && E2E_UVICORN=…/.venv/bin/uvicorn E2E_BENCH_RUNS=15 \
  npm run bench:runs -- live-refresh-request-graph
```

### 2.3 What could NOT be measured, and why

- **Browser update latency (event → DOM change).** Not separable from the poll cadence,
  which is 8 s with ±20 % jitter and dominates it by two orders of magnitude. A figure
  here would be a measurement of the timer, presented as a measurement of the code.
- **Long tasks.** `PerformanceObserver('longtask')` reports nothing for the durations
  involved in this harness's headless Chromium. Nothing is estimated in its place.
- **Server latency as a verdict.** Printed by the bench for reading only. `CLAUDE.md` §7
  records a wall-clock figure being excluded from every verdict because concurrent
  agents contaminated it; the same discipline applies, and this machine was running
  other work.
- **Anything hosted.** `/krish` sits behind an Authentik edge this environment cannot
  authenticate to. No hosted figure of any kind is claimed.

---

## 3. Request counts — before and after

`/pending` **unbounded** means the request carried no query string at all.

### A · First paint — unchanged, deliberately

Identical before and after: **16 requests**, of which the record bundle is nine
(`GET {id}`, `/draft`, `/pending`, `POST /validate`, `POST /audit`, `/warnings`,
`/evidence`, `/artifacts`, `GET /api/graph/status`) and the rest belong to the Runs,
Notes, Proposals and Assets panels, `/evidence-classification` + `/pending?limit=50`
(the assistant context) and `/api/health`.

The bundle's `/pending` is still **unbounded** on first paint. That is a decision, not
an oversight: the complete list is what the assistant's grounding chip is exact over on
a freshly-loaded record, and a bound that reached the initial load would narrow it
silently. Pinned by the first test in the committed guard.

### B · One run edited by another client — record poller wins the race

| | requests | bundles | unbounded `GET /pending` |
|---|---:|---:|---:|
| before | **44** | **4** | **4** |
| after | **17** | **1** | **0** |

Before, per-route: `GET {id}` ×7, `/draft` ×4, `/pending` ×4, `POST /validate` ×4,
`POST /audit` ×4, `/warnings` ×4, `/evidence` ×4, `/artifacts` ×4, `/api/graph/status` ×4,
`/changes` ×3, `/pending?limit=50` ×1, `/evidence-classification` ×1.

After: `GET {id}` ×4, `/changes` ×3, one each of `/draft`, `/pending?limit=10`,
`POST /validate`, `POST /audit`, `/warnings`, `/evidence`, `/artifacts`,
`/api/graph/status`, `/pending?limit=50`, `/evidence-classification`.

**−61 % requests, −75 % bundles, and the unbounded question read is gone.**

### C · One run edited by another client — feed wins the race

| | requests | bundles | unbounded `GET /pending` |
|---|---:|---:|---:|
| before | **21** | **1** | **1** |
| after | **21** | **1** | **0** |

The count is unchanged and that is honest: in this ordering the record poller is
answering 304 while the feed reports, so only one signal ever reaches the screen and
there was nothing to coalesce. The gain here is entirely in the **shape** of the one
refetch — `?limit=10` instead of the whole list — which is a byte gain, not a count gain.

### D · Ten run entries in ONE feed page

| | requests | bundles |
|---|---:|---:|
| before | **17** | **1** |
| after | **17** | **1** |

Already one, in both. Reported because it was worth checking rather than assuming, and
pinned by a test so that a future slice moving the refetch inside an entry loop turns
one save's ten runs into ten bundles and fails instead of shipping.

### E · Ten proposal entries, record ETag held

| | requests | bundles | proposals re-read |
|---|---:|---:|---:|
| before | **7** | **0** | **1** |
| after | **7** | **0** | **1** |

Unchanged, and correct already: `needsCanonicalRefetch` returns false for a
proposal-only summary, so the record bundle is not refetched and the panel that owns
that content re-reads instead.

### F · One proposal act, with the record's own rev moving too — **the residue**

| | requests | bundles | unbounded `GET /pending` |
|---|---:|---:|---:|
| before | **45** | **4** | **4** |
| after | **18** | **1** | **0** |

**This is the honest caveat the charter asked for, and it is not closed.** A proposal act
DOES move the record's own rev in this build, so the version poller sees a genuine change
and the screen refetches its bundle — nine requests for content none of which the
proposal act altered. Scenario E is the feed path deciding correctly; F is the version
poller deciding, and it decides without knowing what moved.

**Why it was not "fixed".** The obvious fix is to adopt the fresh `detail` alone (the
conditional GET already returns it) and skip the other eight requests when the feed has
said, for that revision, that only proposals moved. It was designed, and **declined**,
because the correlation is unsound in a way that fails silently:

- The feed is ordered `(changed_at_rev, kind, entity_id)` and **a page boundary may fall
  anywhere in it**. One page can legitimately carry `[proposal@R]` while the next carries
  `[experiment@R]` — `'experiment' < 'proposal'` decides the tie, and both orderings are
  legal (`RecordChangeSummary.proposalRev` documents exactly this hazard for a different
  consumer). A screen that concluded "R was proposal-only" from the first page and then
  adopted a detail without its eight siblings would show **stale fields, stale evidence
  and a stale verdict** for a real content change, until the next unrelated save.
- The gain is one-sided anyway: it can only help in the FEED-FIRST ordering, which
  `recordChanges.ChangeFloors` measures as the rarer one.

A silent-staleness defect traded for a saving on the rarer ordering is a bad trade, and
the class of defect this repository keeps catching. **The sound fix is a server-side
discriminator** — the change feed saying whether a page is complete for a revision, or
the record's response saying which parts moved — and that is a backend change with its
own argument to make. It is named here rather than implied.

---

## 4. Bytes and DOM — real browser, real backend

**Workload:** the canonical `SEED.ready` record built up to **15 runs / 42 open
questions** in an isolated worked-example session; one run then edited by a SECOND
client over HTTP while the page sat untouched; a 25 s watch window, and a 25 s QUIET
control window of the same length (a count during an event window means nothing without
the count during an equally long quiet one — two pollers tick through both).

**Before** and **after** are the same bench, on the same tree, with the same revert
described in §2.1.

| | requests | response bytes | `GET /pending` (unbounded) | `GET /pending?limit=10` |
|---|---:|---:|---:|---:|
| **before** | 15 | **128,718** | 1 x **41,944 B** | — |
| **after** | 15 | **97,217** | **0** | 1 x **10,443 B** |

**-31,501 bytes, -24.5 %, on one live event at 42 open questions — from one route.**
The saving is `41,944 - 10,443 = 31,501`, which is the whole of the difference; every
other route is byte-identical between the two runs.

**The REQUEST count is unchanged in this run, and that is reported rather than smoothed
over.** In the browser the two pollers' real arrival times happened not to overlap, so
only one signal reached the screen and there was nothing to coalesce — the same shape as
§3's scenario C. The coalescing gain is the §3 scenario B figure (44 -> 17 requests, 4 -> 1
bundles), which is produced under a deterministic worst-case ordering that a wall-clock
browser run cannot be made to reproduce on demand. Two different questions, two different
harnesses; neither number is presented as the other.

**Quiet control:** 3 requests / 699 B in 25 s, identical before and after — the feed's
own cadence, and nothing else. **DOM nodes after first paint: 757**, identical before and
after; this slice changes no rendered structure.

**A cost this slice did NOT remove, named because it is now the largest item in the
window.** `useRecordSession`'s AgentContext effect is keyed on `version`, so every
adopted revision re-reads `GET /pending?limit=50` — **42,069 B** here, and at 42 open
questions that window IS the whole list. It is already bounded (at 50, deliberately, and
`AGENT_CONTEXT_PENDING_WINDOW` carries the argument for that number), so it is not an
unbounded read; but on a record with fewer than 50 questions the bound does not bind, and
after this slice it is the single biggest response in a live event. Narrowing it is a
change to the assistant's grounding contract and is not this slice's to make.

**The bench asserts the invariant, and the assertion FIRED on the before run** — which is
what makes it a measurement with a control rather than a printout:

```
Error: a live event must never issue the unbounded GET /pending
  - Array []
  + Array [ "GET /experiments/{id}/pending" ]
```

**Harness caveat, stated because the first-paint numbers look doubled and are.** The dev
server renders under React `StrictMode`, which mounts every effect twice, so the browser
first-paint counts (`29 requests`) are ~2x the distinct reads a production build issues.
It applies equally to both runs and to every route, and the exact per-read counts are the
vitest ones in §3. The bytes are what this harness is for.

---

## 5. What changed

1. **`api.getRecordBundle(id, { pendingLimit? })`.** Omitted, byte-identical to before
   (nine requests, unbounded `/pending`). Supplied, the pending member becomes
   `GET /pending?limit=N` and the new `RecordBundle.pendingTotal` comes from the server's
   `pending_page.total`. `api.getPending` — the complete reader — is **unchanged** and is
   still what `getExportReadiness` calls; `CLAUDE.md` §11 is explicit that Review Record
   and Export Readiness must not page, and that is not a residue to clean up.

2. **`RecordBundle.pendingTotal`.** Every count on the screen (banner title, overflow
   sentence, status-bar phase) and the assistant's `pending_summary` chip now read it.
   The window bounds what is **fetched**, never what is **claimed** — a record with 3,002
   questions still says 3,002 and still says how many it is not showing.

3. **The coalescing gate** in `RecordWorkbench`: at most one bundle refetch outstanding.
   Keyed on **in-flightness**, not on a revision — see §6.

4. **A third floor, for the run list** (`ChangeFloors.run`, `RecordChangeSummary.runRev`,
   `RecordSession.runActivity`). `RunsSection` fetches the run list itself, so a record
   refetch adopts none of it; measured against the record floor, a `run` entry was
   filtered whenever the record poller won and — a floor never coming back down — was
   dropped for good. This is the same defect `ChangeFloors` was created for, in the one
   kind the first split left behind. `activity` and the announced sentence are computed
   with `run: recordRev` and are therefore **byte-identical** to before.

---

## 6. A wrong turn, recorded because it is the obvious one

The coalescing gate was first written to compare **revisions**: "have I already asked for
a refetch at or past rev R?" An existing fixture caught it on the first run.

The optimistic-concurrency token has the form `"<generation>.<rev>"`, so **a rev is not
monotonic across generations**. `apiFixtures.liveDetailRoute` moves `"1.0"` → `"2.0"` —
a real change — and both derive rev **0**. A rev-keyed gate silently refused every
refetch across a generation boundary: a live update dropped for good, which is the exact
class of defect this slice exists to remove.

In-flightness needs no arithmetic and no ordering assumption. A refetch reads the record
as it is **when it runs**, so any signal arriving while one is outstanding is about a
change that refetch will already carry, and a signal arriving after it settles is either
genuinely newer or is filtered by `summariseChanges` against the freshly adopted
revision.

The gate **re-opens on every settlement**, including a failed one. Without that, one
failed background refetch would close it permanently: the poller would keep answering
200, every signal would be dropped as redundant, and the screen would sit on pre-change
data for as long as it stayed open. There is a negative control for exactly that.

---

## 7. Raw output

### 7.1 vitest probe

Commands and the tallies they printed are in §3; the probe is reproducible from the
description in §2.1 and the committed guard exercises the same paths.

### 7.2 Playwright bench

```
$ E2E_UVICORN=.../.venv/bin/uvicorn E2E_BENCH_RUNS=15 E2E_BENCH_WATCH_MS=25000 \
    npm run bench:runs -- live-refresh-request-graph

=========== BEFORE (reloadFromSignal reverted; head of the log was trimmed by
            the capturing shell, so first paint is quoted from the AFTER run,
            where it is identical: 29 req / 443,920 B / 757 DOM nodes) ========
#### B · one run edited by another client, watched 25000 ms — 15 requests, 128718 response bytes
    1      42069 B  GET /experiments/{id}/pending?limit=50
    1      41944 B  GET /experiments/{id}/pending
    1       9362 B  GET /experiments/{id}/evidence
    1       8978 B  GET /experiments/{id}/draft
    1       7515 B  GET /experiments/{id}/evidence-classification
    1       7105 B  GET /experiments/{id}/warnings
    1       3660 B  POST /experiments/{id}/validate
    2       3196 B  GET /experiments/{id}
    1       3178 B  GET /experiments/{id}/changes
    1        804 B  GET /graph/status
    2        466 B  GET /experiments/{id}/changes?cursor=eyJlIjoiMDFNMUhSWE1IV1ZXQjQ2UjJHREFSTVJaNlEiLCJrIjoicnVuIiwicSI6MTYsInMiOiI0ODE1Y2M5ZWQ0OWM3NDk0IiwidiI6Mn0
    1        323 B  GET /experiments/{id}/artifacts
    1        118 B  POST /experiments/{id}/audit

#### C · CONTROL: 25000 ms with nothing happening — 3 requests, 699 response bytes
    3        699 B  GET /experiments/{id}/changes?cursor=eyJlIjoiMDFNMUhSWE1IV1ZXQjQ2UjJHREFSTVJaNlEiLCJrIjoicnVuIiwicSI6MTYsInMiOiI0ODE1Y2M5ZWQ0OWM3NDk0IiwidiI6Mn0

SUMMARY  paint=29req/443920B  event=15req/128718B  quiet=3req/699B  dom=757  runs=15  questions=42

=========== AFTER (this branch) ==============================================
record 01SYNTHXANESSEED0000000003: 15 runs, 42 open questions

#### A · first paint — 29 requests, 443920 response bytes
    2     232194 B  GET /experiments/{id}/runs?limit=50&offset=0
    2      83888 B  GET /experiments/{id}/pending
    1      42069 B  GET /experiments/{id}/pending?limit=50
    2      18724 B  GET /experiments/{id}/evidence
    2      17956 B  GET /experiments/{id}/draft
    2      14180 B  GET /experiments/{id}/warnings
    2       7654 B  GET /experiments/{id}/assets
    1       7515 B  GET /experiments/{id}/evidence-classification
    2       7290 B  POST /experiments/{id}/validate
    2       4048 B  GET /experiments/{id}/notes
    2       3196 B  GET /experiments/{id}
    2       2102 B  GET /experiments/{id}/proposals
    2       1608 B  GET /graph/status
    2        646 B  GET /experiments/{id}/artifacts
    1        614 B  GET /health
    2        236 B  POST /experiments/{id}/audit
  DOM nodes after first paint: 757

#### B · one run edited by another client, watched 25000 ms — 15 requests, 97217 response bytes
    1      42069 B  GET /experiments/{id}/pending?limit=50
    1      10443 B  GET /experiments/{id}/pending?limit=10
    1       9362 B  GET /experiments/{id}/evidence
    1       8978 B  GET /experiments/{id}/draft
    1       7515 B  GET /experiments/{id}/evidence-classification
    1       7105 B  GET /experiments/{id}/warnings
    1       3660 B  POST /experiments/{id}/validate
    2       3196 B  GET /experiments/{id}
    1       3178 B  GET /experiments/{id}/changes
    1        804 B  GET /graph/status
    2        466 B  GET /experiments/{id}/changes?cursor=eyJlIjoiMDFNMUhSVkhDU0pZQTIzNUJTTjdINE40WkciLCJrIjoicnVuIiwicSI6MTYsInMiOiJiMTY5OGVkYmZiMTY5ZTYwIiwidiI6Mn0
    1        323 B  GET /experiments/{id}/artifacts
    1        118 B  POST /experiments/{id}/audit

#### C · CONTROL: 25000 ms with nothing happening — 3 requests, 699 response bytes
    3        699 B  GET /experiments/{id}/changes?cursor=eyJlIjoiMDFNMUhSVkhDU0pZQTIzNUJTTjdINE40WkciLCJrIjoicnVuIiwicSI6MTYsInMiOiJiMTY5OGVkYmZiMTY5ZTYwIiwidiI6Mn0

SUMMARY  paint=29req/443920B  event=15req/97217B  quiet=3req/699B  dom=757  runs=15  questions=42
```


---

## 8. Mutation controls

Every new guard was checked by reverting the behaviour it pins and confirming it fails.

| Mutation | Command | Result |
|---|---|---|
| `reloadFromSignal` → `bundle.reloadSilent()` (gate and bound both removed) | `npx vitest run src/__tests__/live-refresh-request-graph.test.tsx` | **3 failed** — "RECORD POLLER FIRST", "FEED POLLER FIRST", "a second signal arriving while a refetch is outstanding" |
| `pendingTotal` → `pending.length` | same | **1 failed** — "after a WINDOWED refresh the banner still states the record's real count" |
| run floor → record floor (`run: recordRev`) | `npx vitest run src/__tests__/change-feed-mount.test.tsx` | **2 failed** — "a RUN reaches the run list…", "delivers a run signal ONCE…" |
| run floor never advances | same | **1 failed** — "delivers a run signal ONCE…" |

One test — "TEN run entries in ONE feed page cost ONE bundle" — passes under all of the
above, and that is stated in the test itself rather than left to be found: it pins a
property of the page → summary → refetch mapping, which the gate does not create.

### 8.1 Two claims that were UNPINNED, found by independent review (added 2026-09-02)

The review of PR #224 measured two of this slice's own claims as **reachable by no
assertion anywhere** — reverting either passed all 5,087 tests. Both were comments, and a
comment no test can fail is a claim free to drift. They are pinned now, and the finding is
recorded rather than quietly fixed, because "I added a guard" and "the guard can fail" are
different statements and this slice made the first one twice.

| Claim | Was | Now pinned by | Mutation | Result |
|---|---|---|---|---|
| the assistant's `pending_summary` chip counts `pendingTotal`, not the array handed to it | unpinned | `…/live-refresh-request-graph.test.tsx` · "the assistant's pending_summary chip counts pendingTotal…" | `state.bundle.pendingTotal ?? pending.length` → `pending.length` | **1 failed** |
| …and its `?? pending.length` fallback is a real branch | unpinned | same test, CONTROL 2 | `… ?? pending.length` → `state.bundle.pendingTotal` | **1 failed** |
| `liveRefreshRef` is SINGLE-SHOT — the bound reaches the poll-driven refetch and nothing else | unpinned | same file · "SINGLE-SHOT: pressing Refresh after a windowed refresh issues the UNBOUNDED read" | delete `liveRefreshRef.current = false` | **1 failed** |

The second row matters more than it looks: without it, *deleting* the fallback would have
passed, and every fixture in the repository that casts to `RecordBundle` (there are
several, and they carry no `pendingTotal`) would have started composing
`"undefined fields still need you"`.

The `liveRefreshRef` test presses the **Refresh button the screen actually renders** rather
than calling `reload` directly, because the claim is about what a person gets. It asserts an
ORDERING (the unbounded read came after the windowed one) and not "the last `/pending` call
is the bare one" — the last one is `?limit=50`, `useRecordSession`'s AgentContext prefix
re-firing because `reload` blanks to `loading` and drops `detail`. That first attempt failed
for exactly that reason and the corrected form is in the test's own comment.

### 8.2 `onAgentRefresh` bypasses the gate on purpose (M4, recorded not tested)

`RecordWorkbench.onAgentRefresh` calls `bundle.reloadSilent()` directly rather than through
`reloadFromSignal`, so it is neither gated nor windowed. Deliberate on both counts: it runs
after the reader **confirmed** a staged proposal, so it must not be dropped as redundant
because a poller happened to have a refetch outstanding — a scientist who confirms a value
and sees the old one is the defect `CLAUDE.md` §11 records four surfaces committing — and
its list is not windowed for the same reason first paint is not. Its cost is one bundle per
confirmed proposal, bounded by how fast a person can press a button. Recorded as a comment
in the guard file so a future slice routing it through the gate knows what it has to argue
away.

---

## 9. `CLAUDE.md` §11 corrected in place (2026-09-02)

§11 said `api.getPending` "**still exists and is still correct twice**, for Review Record
and Export Readiness … Do not 'fix' those two." This slice pages one of those two, on one
of its paths, and recorded nothing — so the instruction would have sent a future session to
undo it.

The sentence is **struck and annotated rather than rewritten**, this repository's
convention. The correction states: `api.getPending` itself is unchanged; **Export Readiness
is untouched**; Review Record's **initial load is unchanged and still unbounded**; its
**live refresh** uses `?limit=10` through the new opt-in `pendingLimit`; and **no count
understates**, because `pendingTotal` carries `pending_page.total` and every count on the
screen and in the assistant chip reads that — with the test that fails if one is taken from
the fetched array named inline.

`CLAUDE.md` is in the served-content manifest (§17's own table lists it among the six root
files), so the snapshot was regenerated in the same change.

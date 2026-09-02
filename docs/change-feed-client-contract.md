# The change-feed client's drain budget — measured request behaviour

**Scope.** `apps/web/src/lib/useChangeFeed.ts` only: how many `GET
/api/experiments/{id}/changes` requests the browser client issues, when, and what it
reports about whether it is caught up. The server contract is
`apps/api/isaac_api/change_feed.py` and is **unchanged by this document and by the
change it records** — no route, no response shape and no backend file was touched.

**Every number here was produced by a run.** Each row names the test that asserts it.
The "before" column was measured on the pre-change hook using the *same* harness
(`feedServer` in `apps/web/src/__tests__/change-feed.test.ts`), so the two columns
differ in the code under test and in nothing else. Re-derive rather than quoting:

```bash
cd apps/web && npx vitest run src/__tests__/change-feed.test.ts
```

Conditions for every figure below, because none of them is meaningful without:
`limit = 50` (the server's default window), `Math.random` pinned to `0.5` so the ±20%
cadence jitter is exactly 1.0, the tab visible throughout, `t = 0` at mount, and
`vi.useFakeTimers()` — so these are **scheduler** timings, not wall-clock, and they
carry no claim about network or server latency. This repository does not measure
latency anywhere and this document does not start.

---

## 1. What was wrong

The client had one drain tier: after a page reporting `has_more`, fetch the next after
`CHANGE_FEED_DRAIN_DELAY_MS` (250 ms), for at most
`CHANGE_FEED_MAX_CONSECUTIVE_DRAINS` (20) consecutive pages. Past that it fell back to
the ordinary 8 s cadence, and — correctly, and deliberately — did **not** refill the
budget, because refilling it had already been measured as sustaining ~1.6 req/s
forever against a server answering `has_more: true`.

The consequence was a **cliff at a boundary nobody can see**:

| backlog | pages | caught up at | measured by |
|---|---:|---:|---|
| 1,050 entries | 21 | mount **+13,000 ms** | the burst exactly exhausts the budget |
| 1,100 entries | 22 | mount **+21,000 ms** | one more entry costs **8,000 ms** |

and a long backlog crawled: 5,000 entries (100 pages) caught up at mount **+645,000 ms**
— 10 minutes 45 seconds — while `CHANGE_FEED_CADENCE_CLAIM` tells a scientist an
update "appears shortly after it is made".

Two further defects were found while reproducing that, neither of them about rate:

* **A `422 malformed_cursor` was unrecoverable.** The server's published remedy is
  "drop the cursor and resync". The hook did not: it counted a failure, backed off, and
  resent the same refused cursor on every later poll, forever.
* **The cursor advanced before the entries were handed over.** A consumer that threw
  left the position already past a page nobody had processed, and the next request
  resumed *after* it. The page was gone, and the poll had looked successful.

## 2. What the client does now

One function decides the whole drain rate — `changeFeedBacklogDelayMs(drainsSoFar)`,
exported so this document and the tests pin the function the hook runs rather than a
transcription of it:

| consecutive backlog pages so far | delay before the next |
|---|---|
| `0 … 19` | 250 ms (`CHANGE_FEED_DRAIN_DELAY_MS`) — the **burst**, unchanged |
| `20` | 500 ms |
| `21` | 1,000 ms |
| `22` | 2,000 ms |
| `23` | 4,000 ms |
| `24` and beyond | 8,000 ms (`POLL_INTERVAL_MS`) — the ceiling, forever |

Pinned by `changeFeedBacklogDelayMs — the two-tier ladder, as a pure function` (three
tests, including the ceiling asserted at `Number.MAX_SAFE_INTEGER`).

The budget is still spent **per backlog**, cleared only when the server says
`has_more: false` or when a poll fails. The escalation is one-way: a continuation delay
only ever grows. That is what keeps the refill defect from returning.

## 3. Boundary cases, measured

`pages` is how many requests it took to reach `has_more: false`.

| case | entries | pages | before | after | test |
|---|---:|---:|---:|---:|---|
| empty feed | 0 | 1 | +8,000 ms | +8,000 ms | `EMPTY FEED: one request per cadence…` |
| one page | 10 | 1 | +8,000 ms | +8,000 ms | `ONE PAGE: 10 of a 50 window…` |
| **exactly the page limit** | 50 | 1 | +8,000 ms | +8,000 ms | `EXACTLY THE PAGE LIMIT: a FULL page with has_more:false does not drain` |
| one past the page limit | 51 | 2 | +8,250 ms | +8,250 ms | `ONE PAST THE PAGE LIMIT…` |
| **exactly the drain budget** | 1,050 | 21 | +13,000 ms | +13,000 ms | `EXACTLY THE BUDGET (21 pages)…` |
| **one page past the budget** | 1,100 | 22 | +21,000 ms | **+13,500 ms** | `ONE PAGE PAST THE BUDGET (22 pages)…` |
| four past the budget | 1,250 | 25 | +45,000 ms | **+20,500 ms** | (both columns measured on the harness; the ladder tests pin the delays that produce it) |
| long backlog | 5,000 | 100 | +645,000 ms | **+620,500 ms** | `A LONG BACKLOG (100 pages)…` |

The 50-entry row is the anti-inference case: a client that guessed continuation from
`changes.length === limit` would fast-follow a full page that is in fact the last one.
Continuation is read from the server's `has_more`, never inferred. The mutant that
swaps the condition for `page.changes.length >= page.limit` fails **6** tests.

**No entry is skipped at the ceiling.** The 22-page and 100-page tests both assert the
delivered `entity_id`s equal `E-0 … E-(n-1)` exactly, in order — across the
burst/continuation boundary and across the whole 100-page run.

## 4. The hard rate bound

Under a server answering `has_more: true` with a moving cursor **forever** (modelled by
`feedServer({ grow })`, which appends entries after every page is cut), the delays after
the first request are 250 × 20, then 500, 1000, 2000, 4000, then `POLL_INTERVAL_MS`
forever. So in any window of `T` ms the client issues **at most `26 + T / 8000`
requests**, and the steady state *is* the ordinary cadence:

| window | before | after | bound |
|---:|---:|---:|---:|
| 60,000 ms | 26 | 29 | 33 |
| 120,000 ms | 34 | 37 | 41 |
| 600,000 ms | 94 | 97 | 101 |

Pinned by `SUSTAINED has_more never exceeds the documented rate bound`, which checks all
three horizons, asserts the count is **not** vacuously small, and asserts that every gap
in the last stretch is exactly `POLL_INTERVAL_MS` — i.e. the escalation really does decay
to the cadence rather than merely staying under a bound. The sustained cost of this
change is therefore bounded by **four extra requests during the transition and none
thereafter**, and measured at **+3 at every one of the three horizons** (26→29, 34→37,
94→97); the asymptotic rate is identical to before.

## 5. What the hook now reports

`useChangeFeed` returns `catchingUp: boolean` and `remaining: number | null` alongside
`degraded`, `cursor` and `checkNow`. Both come from the server's own `has_more` and
`remaining` on the last successful page.

* `catchingUp` is `true` whenever the deployment says entities remain — **including**
  while the stuck-cursor guard is refusing to fast-follow, which is exactly the state in
  which a surface must not render "up to date".
* `catchingUp` is **not** cleared by a failed poll. A failure says nothing about whether
  the backlog cleared, and clearing it would let a surface claim to be current on the
  strength of an error.
* `remaining` is `null` for "this client does not know" — before any successful page,
  when the server sent no finite number, and after a refused cursor is dropped. It is
  never defaulted to `0`, which would publish a caught-up claim the deployment never made.

**No UI copy is wired to either field by this change**, deliberately: the consumers are
owned elsewhere. The fields exist so a surface *can* say "still catching up" truthfully.

## 6. Failure and cancellation, mid-drain

| condition | behaviour | test |
|---|---|---|
| `422` on a request that **carried** a cursor | cursor dropped, `remaining` → `null`, retried at the ordinary cadence (**no** backoff escalation — the refusal has just been fixed), failure still counted toward `degraded` | `RESYNCS FROM THE FEED FLOOR after a 422…` |
| `422` on a request carrying **no** cursor | ordinary backoff ladder; degrades after `DEGRADED_THRESHOLD` | `a 422 on a request that carried NO cursor…` |
| `404` | cursor **kept** — a missing record is not a bad cursor, and replaying the feed would re-deliver every entry | `a 404 does NOT drop the cursor…` |
| transport failure mid-drain | budget forfeited, backoff to 2×, resumes from the cursor the last good page issued, no entry lost | `a retryable failure MID-DRAIN…` |
| consumer throws | cursor **not** advanced; the same page is re-requested | `a THROWING consumer does not advance the cursor…` |
| unmount with a request in flight | that request aborted, no state update | `UNMOUNTING MID-DRAIN…` |
| unmount between polls | pending timer cleared | `UNMOUNTING BETWEEN POLLS leaves no pending timer` |
| tab hidden mid-drain | backlog paused, **no timer left armed**, resumes from the same cursor on becoming visible | `HIDING THE TAB MID-DRAIN…`, `a poll that SETTLES AFTER the tab is hidden arms no timer` |

Only a request that **carried** a cursor may drop one. That is what stops the resync
from looping: a `422` a resync cannot fix — a malformed `limit`, say, which FastAPI also
answers `422` and which this client cannot tell apart, because `httpErrorWithReason`
attaches the server's `error` string on `404` responses only — falls through to the
ordinary ladder. At most every other request can take the recovery branch.

## 7. How the tests were shown to be real

Thirteen mutants were applied to `useChangeFeed.ts` one at a time and the suite re-run.
**All thirteen are now caught**; three survived on first pass and each survival was a
genuine gap that was then closed:

| mutant | tests failed |
|---|---:|
| continuation delay = ordinary cadence (the old cliff) | 4 |
| continuation stays at the full drain rate (no ceiling) | 5 |
| cursor adopted before `onChanges` (the old order) | 1 |
| `422` recovery removed | 1 |
| drop the cursor on **any** error | 2 |
| `catchingUp` hardcoded `false` | 4 |
| `remaining` defaults to `0` instead of `null` | 1 |
| continuation inferred from `changes.length >= limit` | 6 |
| budget refilled at the ceiling | 2 |
| `catchingUp`/`remaining` not reset on a new record | 1 |
| unmount does not abort the in-flight request | 1 |
| unmount leaves the timer running | 1 *(survived until a dedicated test was added — the existing one unmounted with a request in flight, when no timer is pending anyway, so its `getTimerCount() === 0` was **vacuously true**)* |
| visibility gate removed from `schedule` | 1 *(survived until a test was added for the one path that reaches it: a request already in flight when the tab is hidden, whose `.finally` would otherwise arm a timer on a paused poller — hiding between polls is handled by the listener's `clearTimer`, and a timer firing while hidden is handled by `runPoll`'s own guard, so neither existing test could see the gate at all)* |

## 8. What this deliberately does not do

* **It does not refill the burst budget at the ceiling.** That was measured once as
  ~1.6 req/s sustained forever, ~13× the ordinary cadence.
* **It does not jitter the continuation delay.** Jitter desynchronises two *tabs* at the
  cadence; these are continuations of one read. At the ceiling that means an unjittered
  8,000 ms against the cadence's 8,000 ± 20%, i.e. at most 1.6 s of difference in when
  one tab's catch-up request lands.
* **It does not push, stream or subscribe.** No SSE, no WebSocket — that would be a
  second synchronisation scheme beside `useRecordSync`.
* **It changes no server file, no route and no response shape.**
* **It wires no UI copy** to `catchingUp` or `remaining`.
* **It makes no latency claim.** Every figure above is fake-timer scheduling.

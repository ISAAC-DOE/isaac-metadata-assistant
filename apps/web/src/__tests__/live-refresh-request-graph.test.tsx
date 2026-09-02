/*
 * WHAT ONE LIVE EVENT COSTS THE RECORD SCREEN — counted, per route, at the wire.
 *
 * ── WHY A TEST AND NOT A REVIEW ─────────────────────────────────────────────────
 *
 * The record screen runs TWO pollers (`useRecordSync` on the record's ETag,
 * `useChangeFeed` on the coalescing state feed) and each of them, independently, used
 * to call `bundle.reloadSilent()` — nine requests, one of which was the UNBOUNDED
 * `GET /pending`. Neither knew about the other, so one change made by a colleague cost
 * TWO complete bundles and downloaded the record's entire open-question list twice.
 * On a 1,000-run record that list is 3,000 entries / 1.77 MB.
 *
 * None of that was visible to any existing test, because every existing test asserts
 * what is ON SCREEN. Two identical refetches render exactly what one renders. The
 * defect was only ever observable as a COUNT, so this file counts.
 *
 * ── WHAT IT PINS ────────────────────────────────────────────────────────────────
 *
 *   1. FIRST PAINT IS UNCHANGED — the same nine experiment-scoped bundle requests, and
 *      the pending read still carries NO query string. A bound that reached the
 *      initial load would silently narrow the assistant's grounding on mount.
 *   2. NO LIVE EVENT CAUSES AN UNBOUNDED `GET /pending`. This is the slice's central
 *      invariant, and it is asserted over the RECORDED URLS rather than over a spy, so
 *      it cannot be satisfied by a mock that never issued the request.
 *   3. ONE bundle refetch per record movement, whichever poller wins.
 *   4. A BURST of N entries in one feed page costs ONE refetch, and a proposal-only
 *      burst costs NONE.
 *   5. Signals arriving while a refetch is outstanding cost at most ONE follow-up.
 *   6. NEGATIVE CONTROLS for 3 and 5 — a later, genuinely separate change still
 *      refetches, and a failed refetch re-opens the gate. Without these, a gate that
 *      simply refused everything after the first event would pass 3, 4 and 5.
 *
 * ── WHAT IT DOES NOT MEASURE, STATED RATHER THAN IMPLIED ────────────────────────
 *
 * BYTES AND LATENCY. jsdom's `fetch` is a stub returning fixture objects; there is no
 * wire, no serialisation and no server. Request COUNTS and their URLs are exact here;
 * transferred bytes and server timings are a browser measurement and belong in
 * `apps/web/e2e/mutation/*.bench.ts`. Nothing in this file prints a byte figure, and
 * `docs/evidence/live-refresh-request-graph-2026-09-02.md` says which figures came
 * from where.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { NEEDSYOU_VISIBLE, LIVE_PENDING_WINDOW } from '../screens/RecordWorkbench';
import {
  bundleRoutes,
  experimentDetail,
  pendingResponse,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { RouteResult } from '../test/apiFixtures';
import type { ApiChangeEntry, ApiChangeFeedPage } from '../lib/types';
import { POLL_INTERVAL_MS } from '../lib/useRecordSync';

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

/** The rev this view holds on first paint, derived exactly as the hook derives it. */
const KNOWN_REV = Number(String(experimentDetail.version).split('.').pop());

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

async function settle(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

/**
 * A `GET {id}` route with real ETag semantics AND a switch.
 *
 * `apiFixtures.liveDetailRoute` almost does this, but it always answers the bumped
 * version once bumped — which makes the FEED-FIRST ordering unreachable, because the
 * record poller would already have reported the change. `held` keeps the conditional
 * GET answering 304 while the plain bundle GET still serves the current body, which is
 * exactly the state the two pollers are in when the feed wins the race.
 */
function detailRoute(): {
  route: (init?: RequestInit) => RouteResult;
  bump: (toRev: number) => void;
  hold: (held: boolean) => void;
} {
  let rev = KNOWN_REV;
  let held = false;
  /*
   * THE VERSION MOVES WITHIN ONE GENERATION, AND `apiFixtures.liveDetailRoute` DOES
   * NOT — which is why this is written here rather than reused.
   *
   * That helper moves `"1.0"` -> `"2.0"`. Both derive rev **0**, because the token is
   * `"<generation>.<rev>"` and a new generation restarts the rev. That is a faithful
   * model of a re-materialisation and a USELESS one for this file: the change feed's
   * `changed_at_rev` is compared against the derived rev, so under that fixture an
   * adopted refetch never raises the floor and every later poll re-reports the same
   * entries forever. The counts would then measure the fixture rather than the code.
   * (It is also the fixture that caught a revision-keyed version of the coalescing
   * gate being wrong across exactly that boundary — see the negative control below.)
   */
  const bodyFor = () => ({
    ...experimentDetail,
    id: ID,
    version: `1.${rev}`,
    rev,
  });
  return {
    bump: (toRev: number) => {
      rev = toRev;
    },
    hold: (v: boolean) => {
      held = v;
    },
    route: (init?: RequestInit): RouteResult => {
      const inm = (init?.headers as Record<string, string> | undefined)?.['If-None-Match'];
      if (inm) {
        // A held poller is told "unchanged" whatever the body now says. It models the
        // window between a save landing and this client's next conditional GET seeing
        // it, which is where the feed can legitimately arrive first.
        if (held || inm === `"1.${rev}"`) return { status: 304, etag: inm };
        return { status: 200, body: bodyFor(), etag: `"1.${rev}"` };
      }
      return { status: 200, body: bodyFor(), etag: `"1.${rev}"` };
    },
  };
}

function feedPage(changes: ApiChangeEntry[], over: Partial<ApiChangeFeedPage> = {}) {
  return {
    changes,
    next_cursor: `CURSOR-${changes.length}-${changes[0]?.changed_at_rev ?? 0}`,
    has_more: false,
    limit: 50,
    returned: changes.length,
    remaining: 0,
    kinds: ['experiment', 'proposal', 'run'],
    ...over,
  } as ApiChangeFeedPage;
}

const runEntry = (n: number, rev: number): ApiChangeEntry => ({
  kind: 'run',
  entity_id: `01RUN${String(n).padStart(21, '0')}`,
  changed_at_rev: rev,
  updated_utc: '2026-09-02T10:00:00Z',
});

const proposalEntry = (n: number, rev: number): ApiChangeEntry => ({
  kind: 'proposal',
  entity_id: `01PROPOSAL${String(n).padStart(16, '0')}`,
  changed_at_rev: rev,
  state: 'open',
  updated_utc: '2026-09-02T10:00:00Z',
});

const experimentEntry = (rev: number): ApiChangeEntry => ({
  kind: 'experiment',
  entity_id: ID,
  changed_at_rev: rev,
  updated_utc: '2026-09-02T10:00:00Z',
});

/** How many times a route was requested, matched on the path before any query. */
function countPath(calls: string[], key: string): number {
  return calls.filter((c) => c.replace(/\?.*$/, '') === key).length;
}

/** Every recorded `GET …/pending` that sent NO query string — the unbounded read. */
function unboundedPendingReads(calls: string[]): string[] {
  return calls.filter((c) => c === `GET ${BASE}/pending`);
}

/**
 * The bundle's OWN member reads, per fetch. `GET …/draft` is the witness used
 * throughout: it is issued exactly once per `getRecordBundle` and by nothing else on
 * this screen, so its count IS the bundle count. `GET {id}` cannot be the witness —
 * the record poller issues it too — and that difference is the whole reason the
 * duplicate refetch was invisible.
 */
const bundleCount = (calls: string[]) => countPath(calls, `GET ${BASE}/draft`);

describe('the record screen live-refresh request graph', () => {
  let detail: ReturnType<typeof detailRoute>;
  let feed: { changes: ApiChangeEntry[] };
  let calls: string[];

  function mount(extra: Record<string, unknown> = {}) {
    detail = detailRoute();
    feed = { changes: [] };
    calls = stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}`]: detail.route,
      /*
       * ONE-SHOT, WHICH IS WHAT A CURSOR ACTUALLY DOES. The real feed advances the
       * caller's cursor past what it returned, so a second poll gets an empty page.
       * A stub that re-served the same batch on every tick would model a server that
       * never advances, and every count in this file would be a count of replays.
       */
      [`GET ${BASE}/changes`]: () => {
        const changes = feed.changes;
        feed.changes = [];
        return { body: feedPage(changes) };
      },
      ...extra,
    } as never);
    return renderAt(`/record/${ID}`);
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5); // pin poll jitter to exactly 1×
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  // --- 1. first paint is untouched ------------------------------------------

  it('first paint issues the same nine bundle reads, and its pending read is UNBOUNDED', async () => {
    mount();
    await settle();

    /*
     * THE NINE, ENUMERATED RATHER THAN COUNTED. A bare total would pass if one member
     * were swapped for another; naming them is what makes "the first paint is
     * unchanged" a checkable claim instead of an arithmetic coincidence. `GET {id}`
     * is excluded from the enumeration and asserted separately: the record poller
     * shares that path, so its count is not a property of the bundle alone.
     */
    for (const key of [
      `GET ${BASE}/draft`,
      `POST ${BASE}/validate`,
      `POST ${BASE}/audit`,
      `GET ${BASE}/warnings`,
      `GET ${BASE}/evidence`,
      `GET ${BASE}/artifacts`,
      'GET /api/graph/status',
    ]) {
      expect(countPath(calls, key), key).toBe(1);
    }
    expect(countPath(calls, `GET ${BASE}`)).toBe(1);

    /*
     * `/pending` IS READ TWICE ON FIRST PAINT AND ALWAYS WAS, by two different owners,
     * and enumerating it as "one of the nine" would have been wrong about the screen
     * rather than about the bundle. The bundle's member is the UNBOUNDED one; the
     * second is `useRecordSession`'s AgentContext prefix, which has been bounded at
     * `AGENT_CONTEXT_PENDING_WINDOW` (50) since well before this slice. Both are
     * asserted, because a slice that dropped either would change what the screen knows.
     */
    expect(countPath(calls, `GET ${BASE}/pending`)).toBe(2);
    expect(unboundedPendingReads(calls), 'the bundle member, unbounded').toHaveLength(1);
    expect(
      calls.filter((c) => c === `GET ${BASE}/pending?limit=50`),
      "the assistant context's own prefix, unchanged by this slice",
    ).toHaveLength(1);
  });

  it('the live window is at least what the banner renders, so a refresh cannot shrink the list', () => {
    /*
     * A CONSTANT-RELATIONSHIP GUARD, not a value guard. If `LIVE_PENDING_WINDOW` fell
     * below `NEEDSYOU_VISIBLE`, a background refresh would silently render fewer rows
     * than the initial load did — a list shrinking with no act by the reader, and
     * nothing on screen to say why.
     */
    expect(LIVE_PENDING_WINDOW).toBeGreaterThanOrEqual(NEEDSYOU_VISIBLE);
  });

  // --- 2. one event, either ordering, one bundle ----------------------------

  it('RECORD POLLER FIRST: one movement costs ONE bundle, and its pending read is bounded', async () => {
    mount();
    await settle();
    const before = bundleCount(calls);
    const beforeUnbounded = unboundedPendingReads(calls).length;

    // A colleague saves: the record's ETag moves AND the feed reports the run and the
    // record's own entry, which is what one save actually produces (contract DEC-10).
    detail.bump(KNOWN_REV + 1);
    feed.changes = [experimentEntry(KNOWN_REV + 1), runEntry(1, KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 3);

    expect(bundleCount(calls) - before, 'exactly one bundle refetch').toBe(1);
    // THE CENTRAL INVARIANT. Not "fewer" — none.
    expect(unboundedPendingReads(calls).length - beforeUnbounded).toBe(0);
    expect(
      calls.filter((c) => c === `GET ${BASE}/pending?limit=${LIVE_PENDING_WINDOW}`),
    ).toHaveLength(1);
  });

  it('FEED POLLER FIRST: the same one bundle, and the record poller does not add a second', async () => {
    mount();
    await settle();
    const before = bundleCount(calls);

    // The save has happened, but this client's conditional GET has not seen it yet.
    detail.hold(true);
    detail.bump(KNOWN_REV + 1);
    feed.changes = [experimentEntry(KNOWN_REV + 1), runEntry(1, KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 2);
    expect(bundleCount(calls) - before, 'the feed alone refetched once').toBe(1);

    // Now the record poller catches up. The refetch has already adopted the new
    // version, so its conditional GET is answered 304 and nothing further happens.
    detail.hold(false);
    await settle(POLL_INTERVAL_MS * 3);
    expect(bundleCount(calls) - before, 'and the record poller added nothing').toBe(1);
    expect(unboundedPendingReads(calls)).toHaveLength(1); // the first paint's, and only it
  });

  // --- 3. bursts -------------------------------------------------------------

  /*
   * THIS ONE IS ABOUT THE PAGE, NOT THE GATE, AND SAYING SO IS PART OF IT. Ten entries
   * arrive in one page, produce one summary and cost one refetch — and they would even
   * with the coalescing gate removed, because the mapping page → summary → refetch is
   * 1:1 by construction. It is pinned anyway: a future slice that iterated entries, or
   * moved the refetch inside the loop, would turn one save's ten runs into ten bundles,
   * and nothing else here would notice.
   */
  it('TEN run entries in ONE feed page cost ONE bundle, not ten', async () => {
    mount();
    await settle();
    const before = bundleCount(calls);

    detail.hold(true);
    detail.bump(KNOWN_REV + 1);
    feed.changes = Array.from({ length: 10 }, (_, i) => runEntry(i, KNOWN_REV + 1));
    await settle(POLL_INTERVAL_MS * 3);

    expect(bundleCount(calls) - before).toBe(1);
  });

  it('TEN proposal entries cost NO bundle at all — the record read is not stale for them', async () => {
    mount();
    await settle();
    const before = bundleCount(calls);
    const proposalsBefore = countPath(calls, `GET ${BASE}/proposals`);

    // The record's ETag is deliberately held: a proposal act DOES move the record's
    // rev in this build, and this isolates what the FEED path decides from what the
    // version poller would do about the same act. The version poller's cost on a
    // proposal act is a MEASURED, UNCLOSED residue — see the evidence document.
    detail.hold(true);
    feed.changes = Array.from({ length: 10 }, (_, i) => proposalEntry(i, KNOWN_REV + 1));
    await settle(POLL_INTERVAL_MS * 3);

    expect(bundleCount(calls) - before, 'no bundle for content this screen does not render').toBe(
      0,
    );
    // …and the surface that DOES own that content re-read instead. Without this the
    // assertion above would also pass on a build where the proposal signal went nowhere.
    expect(countPath(calls, `GET ${BASE}/proposals`)).toBeGreaterThan(proposalsBefore);
  });

  // --- 3b. the window bounds what is FETCHED, never what is CLAIMED -----------

  it('after a WINDOWED refresh the banner still states the record\'s real count', async () => {
    /*
     * THE HONESTY HALF OF THE BOUND, AND THE ONE THAT WOULD HAVE BEEN INVISIBLE.
     *
     * Bounding the live read is only safe because every COUNT on the screen comes from
     * the server's `pending_page.total` rather than from the length of what arrived. A
     * build that counted the fetched array would render "10 Fields Need Your
     * Confirmation" over a record holding thirty, and drop the overflow sentence
     * entirely — a truncated list reading as complete, which is exactly what
     * `NEEDSYOU_VISIBLE`'s own note says must never happen. Nothing would look broken.
     *
     * The pending route here TRUNCATES on a bounded read, which `apiFixtures`
     * deliberately does not: its `pendingRoutes` always serves the whole list, so a
     * windowed read there is indistinguishable from an unbounded one and this defect
     * could not be reached at all.
     */
    const ALL = Array.from({ length: 30 }, (_, i) => ({
      ...(pendingResponse.pending[0] as Record<string, unknown>),
      id: `synthetic-blocker-${i}`,
      blocker_key: `synthetic-blocker-${i}`,
      about: `synthetic_field_${i}`,
      question: `Confirm synthetic field ${i}?`,
    }));
    const truncating = (_init?: RequestInit, path?: string) => {
      const limit = Number(/[?&]limit=(\d+)/.exec(path ?? '')?.[1] ?? NaN);
      if (!Number.isFinite(limit)) return { body: { pending: ALL } };
      const page = ALL.slice(0, limit);
      return {
        body: {
          pending: page,
          pending_page: {
            total: ALL.length,
            returned: page.length,
            offset: 0,
            limit,
            withheld: ALL.length - page.length,
            complete: false,
            run_id: null,
            record_total: ALL.length,
          },
        },
      };
    };

    const { getByText } = mount({ [`GET ${BASE}/pending`]: truncating });
    await settle();
    getByText('30 Fields Need Your Confirmation');
    getByText(/Showing the first 10 of 30\./);

    detail.bump(KNOWN_REV + 1);
    feed.changes = [experimentEntry(KNOWN_REV + 1), runEntry(1, KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 3);

    // The refresh fetched TEN…
    expect(
      calls.filter((c) => c === `GET ${BASE}/pending?limit=${LIVE_PENDING_WINDOW}`),
    ).toHaveLength(1);
    // …and the screen still says THIRTY, and still says how many it is not showing.
    getByText('30 Fields Need Your Confirmation');
    getByText(/Showing the first 10 of 30\./);
    getByText(/20 more are waiting/);
  });

  // --- 4. in-flight coalescing, and the controls that make it mean something --

  it('a second signal arriving while a refetch is outstanding does not add a second bundle', async () => {
    /*
     * The bundle's `draft` read is held open, so the refetch is genuinely in flight
     * while the next poll tick fires. Without the gate this is where the second
     * nine-request bundle came from.
     */
    let release!: () => void;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    let holdNext = false;
    const routes = bundleRoutes(ID);
    const draftBody = (routes[`GET ${BASE}/draft`] as { body: unknown }).body;

    mount({
      [`GET ${BASE}/draft`]: async () => {
        if (holdNext) await gate;
        return { body: draftBody };
      },
    });
    await settle();
    const before = bundleCount(calls);

    /*
     * THE ETAG IS DELIBERATELY **NOT** HELD HERE. That is what makes a second signal
     * actually arrive: `useRecordSync` polls with the version this view still holds, so
     * for as long as the refetch has not landed EVERY tick answers 200 and reports the
     * same change again. Measured with the gate removed, this scenario issued FOUR
     * complete bundles and four unbounded `GET /pending` for one save — see the
     * evidence document's scenario B. An earlier version of this test held the ETag,
     * which silenced the very signal it was meant to be counting: it passed with the
     * gate reverted, and so proved nothing.
     */
    holdNext = true;
    detail.bump(KNOWN_REV + 1);
    feed.changes = [experimentEntry(KNOWN_REV + 1), runEntry(1, KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS); // the first signal → refetch starts and hangs
    expect(bundleCount(calls) - before).toBe(1);

    // Two further poll ticks while it hangs. The record poller reports the same
    // unadopted change on each of them.
    await settle(POLL_INTERVAL_MS * 2);
    expect(bundleCount(calls) - before, 'no second bundle while one is outstanding').toBe(1);

    holdNext = false;
    await act(async () => {
      release();
      await Promise.resolve();
    });
    await settle();
  });

  it('NEGATIVE CONTROL: a LATER, separate change still refetches — the gate is not a mute', async () => {
    /*
     * Everything above is satisfied by a gate that simply refuses every signal after
     * the first. This is the assertion that says it does not, and it is the reason the
     * gate is keyed on a read being OUTSTANDING rather than on a revision: a
     * revision-keyed gate got this wrong across a generation boundary
     * (`"1.0"` → `"2.0"` derive the same rev) and dropped the update for good.
     */
    mount();
    await settle();
    const before = bundleCount(calls);

    detail.hold(true);
    feed.changes = [experimentEntry(KNOWN_REV + 1), runEntry(1, KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 2);
    expect(bundleCount(calls) - before).toBe(1);

    // A genuinely later save, reported by a later page.
    feed.changes = [experimentEntry(KNOWN_REV + 2), runEntry(2, KNOWN_REV + 2)];
    await settle(POLL_INTERVAL_MS * 2);
    expect(bundleCount(calls) - before, 'the second change is not swallowed').toBe(2);
  });

  it('NEGATIVE CONTROL: a FAILED refetch re-opens the gate, so the next poll retries', async () => {
    /*
     * The failure mode this exists to make impossible: one failed background refetch
     * closing the gate permanently, so the poller keeps answering 200, every signal is
     * dropped as redundant, and the screen shows pre-change data indefinitely with no
     * recourse but the human pressing Refresh.
     */
    let failing = false;
    const routes = bundleRoutes(ID);
    const draftBody = (routes[`GET ${BASE}/draft`] as { body: unknown }).body;
    mount({
      [`GET ${BASE}/draft`]: () => (failing ? { status: 503, body: {} } : { body: draftBody }),
    });
    await settle();
    const before = bundleCount(calls);

    // The save lands; this client's conditional GET is held, so the FEED reports it
    // first — and the refetch it triggers fails.
    failing = true;
    detail.hold(true);
    detail.bump(KNOWN_REV + 1);
    feed.changes = [experimentEntry(KNOWN_REV + 1), runEntry(1, KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 2);
    expect(bundleCount(calls) - before, 'the first attempt happened and failed').toBe(1);

    /*
     * NOW THE ORDINARY RECOVERY PATH, not a contrived second signal: the backend comes
     * back and the record poller — which has been answering 304 while held — sees the
     * version it never adopted. Under a gate that did not re-open, this poll and every
     * one after it would be dropped as "already asked for", and the screen would sit on
     * pre-change data for as long as it stayed open.
     */
    failing = false;
    detail.hold(false);
    await settle(POLL_INTERVAL_MS * 2);
    expect(bundleCount(calls) - before, 'and the next poll tried again').toBeGreaterThan(1);
  });
});

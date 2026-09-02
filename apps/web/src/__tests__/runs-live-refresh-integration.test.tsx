/*
 * THE RUNS LIVE REFRESH, THROUGH THE REAL SCREEN — producer to consumer, counted at
 * the wire.
 *
 * ── WHY THIS FILE EXISTS AND `runs-section-live-refresh.test.tsx` DOES NOT COVER IT ─
 *
 * That file renders `RunsSection` under a hand-written `Harness` that hands it an
 * `activity` object and a `recordVersion` string directly. It is the right test for
 * "given this summary, does the section re-read?" and it is structurally incapable of
 * answering the question this slice actually turned on: **is anything connected to
 * those two props at all?**
 *
 * On the tree immediately before this slice the answer was no. PR #224 shipped the
 * producer (`useRecordSession.runActivity`, `RecordChangeSummary.runRev`) and PR #222
 * shipped the consumer (`RunsSection`'s two props), each with a green suite, and
 * `RecordWorkbench.tsx` rendered `<RunsSection experimentId={id} />` — both props
 * absent, both defaulting to `null`, every effect in the consumer returning on its
 * first line. A colleague's run edit moved no pixel. Neither branch's tests could see
 * it, because neither branch's tests mount the screen that wires them.
 *
 * So this file mounts the REAL `AppRoutes` at `/record/:id`, stubs `fetch` and nothing
 * else, and counts `GET …/runs` at the recorded URL. The wiring is the subject.
 *
 * ── WHAT IT PINS ────────────────────────────────────────────────────────────────
 *
 *   1. A colleague's RUN EDIT costs exactly ONE bounded runs re-read. Bounded is
 *      asserted on the `limit` in the recorded query string, not on a spy argument:
 *      a re-read that dropped the bound would fetch a 1,000-run list to show a
 *      one-field change.
 *   2. A colleague's RUN REMOVAL — which the change feed STRUCTURALLY CANNOT REPORT,
 *      because removing a run moves only the record's own entry — still makes the run
 *      disappear, via `recordVersion` rather than via `activity`.
 *   3. A PROPOSAL-ONLY feed page costs NO runs re-read on the feed's own account, and
 *      the disclosed cost afterwards is exactly one, once the record poller adopts the
 *      version the proposal act bumped.
 *   4. The RECORD POLLER WINNING THE RACE totals the same one re-read as the feed
 *      winning it — the two paths coalesce rather than each fetching.
 *   5. Unmounting mid-refresh leaves no timer and no `act` warning.
 *
 * ── THE MUTATION CONTROLS, RUN AND REVERTED — AND ONE OF THEM IS INERT ──────────
 *
 * Recorded here because an assertion never observed going red is not evidence that it
 * would, and because the FIRST version of this file was worthless in exactly the way a
 * control exists to expose. Each mutation was applied to the source named, this file
 * re-run, and the change reverted. Raw output:
 * `docs/evidence/two-actor-workflow-proof-2026-09-02.md`.
 *
 *   A. delete `activity={runActivity}` from `RecordWorkbench.tsx`
 *      -> **7 passed. AN EQUIVALENT MUTATION, and the reason is measured rather than
 *      guessed.** `recordChanges.needsCanonicalRefetch` returns `true` whenever
 *      `summary.runIds.length > 0`, so ANY run signal also triggers a bundle refetch;
 *      the refetch moves `detail.version`; and `recordVersion` then fires the
 *      completeness path. On THIS screen the completeness path therefore SUBSUMES the
 *      fast path for every scenario this harness can build. The request ORDER is
 *      identical too — measured by printing the recorded calls with and without the
 *      prop, and the runs re-read lands at the same position in both.
 *      The prop is kept, because it is PR #224/#222's designed contract and it is the
 *      only path that does not wait on a nine-request bundle refetch; but this file
 *      must not be read as evidence that it does anything here. **Do not "strengthen"
 *      a test until control A goes red without first changing what the screen does.**
 *   B. delete `recordVersion={detail.version}` -> **2 FAILED**: the removal test
 *      (`expected 2 to be 1` — the removed run stays on screen) and the proposal-only
 *      test (`expected +0 to be 1`). So `recordVersion` is load-bearing, and it is the
 *      prop that carries the two cases the feed structurally cannot report.
 *   C. delete the in-flight coalesce branch from `RunsSection.triggerBoundedSilentReload`
 *      -> **7 passed.** Also inert here: under fake timers the two paths do not
 *      actually overlap, so nothing lands while a request is outstanding. The
 *      `toBe(1)` assertions are still real — control D shows they can fail — but they
 *      are not measuring the coalesce.
 *   D. delete BOTH props, which is EXACTLY the tree immediately before this slice
 *      -> **4 of 7 FAILED** (edit, removal, proposal-only, record-poller-first), each
 *      with the re-read count at 0 or the run still on screen. That is the control
 *      that matters: the wiring as a whole is load-bearing, and this file would have
 *      caught the disconnected screen that two green branches shipped.
 *
 * ── WHAT IT DOES NOT MEASURE, STATED RATHER THAN IMPLIED ────────────────────────
 *
 * BYTES AND LATENCY. jsdom's `fetch` is a stub; there is no wire and no server.
 * Request counts and their query strings are exact; transferred bytes are a browser
 * measurement and belong in the e2e suites.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import {
  bundleRoutes,
  experimentDetail,
  runFixture,
  runsPage,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { RouteResult } from '../test/apiFixtures';
import type { ApiChangeEntry, ApiChangeFeedPage } from '../lib/types';
import { POLL_INTERVAL_MS } from '../lib/useRecordSync';
import { CHANGE_FEED_CLIENT_LIMIT } from '../lib/useRecordSession';

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

/** The rev this view holds on first paint, derived exactly as the hook derives it. */
const KNOWN_REV = Number(String(experimentDetail.version).split('.').pop());

const RUN_ONE = '01SYNTHTESTRUN0000000000A1';
const RUN_TWO = '01SYNTHTESTRUN0000000000A2';

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
 * A `GET {id}` route with real ETag semantics AND a switch, lifted from
 * `live-refresh-request-graph.test.tsx` for the reason that file states: the shared
 * `apiFixtures.liveDetailRoute` always answers the bumped version once bumped, which
 * makes the FEED-FIRST ordering unreachable. `held` keeps the conditional GET
 * answering 304 while the plain bundle GET serves the current body — exactly the state
 * the two pollers are in when the feed wins the race.
 */
function detailRoute(): {
  route: (init?: RequestInit) => RouteResult;
  bump: (toRev: number) => void;
  hold: (held: boolean) => void;
  version: () => string;
} {
  let rev = KNOWN_REV;
  let held = false;
  const token = () => `1.${rev}`;
  const bodyFor = () => ({ ...experimentDetail, id: ID, version: token(), rev });
  return {
    version: token,
    bump: (toRev: number) => {
      rev = toRev;
    },
    hold: (v: boolean) => {
      held = v;
    },
    route: (init?: RequestInit): RouteResult => {
      const inm = (init?.headers as Record<string, string> | undefined)?.['If-None-Match'];
      if (inm) {
        if (held || inm === `"${token()}"`) return { status: 304, etag: inm };
        return { status: 200, body: bodyFor(), etag: `"${token()}"` };
      }
      return { status: 200, body: bodyFor(), etag: `"${token()}"` };
    },
  };
}

function feedPage(changes: ApiChangeEntry[], over: Partial<ApiChangeFeedPage> = {}) {
  return {
    changes,
    next_cursor: `CURSOR-${changes.length}-${changes[0]?.changed_at_rev ?? 0}`,
    has_more: false,
    limit: CHANGE_FEED_CLIENT_LIMIT,
    returned: changes.length,
    remaining: 0,
    kinds: ['experiment', 'proposal', 'run'],
    ...over,
  } as ApiChangeFeedPage;
}

const runEntry = (runId: string, rev: number): ApiChangeEntry => ({
  kind: 'run',
  entity_id: runId,
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

/**
 * `.run-card` count.
 *
 * READ SYNCHRONOUSLY AFTER `settle()`, NEVER THROUGH `waitFor`, and the reason is
 * measured rather than stylistic: this file runs on FAKE timers, and
 * testing-library's `waitFor` polls on an interval it expects something else to
 * advance. Under `vi.useFakeTimers()` nothing does, so the first version of this
 * file hung all six mounting tests at `Test timed out in 5000ms` — naming neither
 * the query nor the DOM, exactly the failure mode `CLAUDE.md` records from the
 * 2026-08-25 flake. `settle()` advances the fake clock and flushes React inside
 * `act`, so by the time it returns there is nothing left to wait for.
 */
function runCards(view: { container: HTMLElement }): number {
  return view.container.querySelectorAll('.run-card').length;
}

/** Every recorded `GET …/runs`, query string included. */
function runsReads(calls: string[]): string[] {
  return calls.filter((c) => c.replace(/\?.*$/, '') === `GET ${BASE}/runs`);
}

/** The `limit` each recorded runs read carried, in order. `null` = no `limit` sent. */
function runsReadLimits(calls: string[]): (string | null)[] {
  return runsReads(calls).map((c) => {
    const q = c.includes('?') ? c.slice(c.indexOf('?') + 1) : '';
    return new URLSearchParams(q).get('limit');
  });
}

describe('the runs live refresh, wired through the real Record Workbench', () => {
  let detail: ReturnType<typeof detailRoute>;
  let feed: { changes: ApiChangeEntry[] };
  let calls: string[];
  /** The run set the server currently holds. Mutated by a test to model a colleague. */
  let serverRuns: ReturnType<typeof runFixture>[];

  function mount() {
    detail = detailRoute();
    feed = { changes: [] };
    serverRuns = [
      runFixture({ id: RUN_ONE, label: 'Run 1', ordinal: 1 }),
      runFixture({ id: RUN_TWO, label: 'Run 2', ordinal: 2 }),
    ];
    calls = stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}`]: detail.route,
      /*
       * THE RUNS LIST, ANSWERING WITH THE RECORD'S CURRENT VERSION — which is what the
       * real route does, and it is load-bearing rather than incidental. `RunsSection`
       * holds the `experiment_version` its last read returned and compares the
       * `recordVersion` prop against it; a fixture that froze `experiment_version` at
       * `1.0` would make the completeness path fire forever and every count below
       * would be a count of the fixture.
       */
      [`GET ${BASE}/runs`]: () => ({
        body: { ...runsPage([...serverRuns]), experiment_version: detail.version() },
      }),
      // ONE-SHOT, which is what a cursor actually does: the real feed advances past
      // what it returned, so a second poll gets an empty page.
      [`GET ${BASE}/changes`]: () => {
        const changes = feed.changes;
        feed.changes = [];
        return { body: feedPage(changes) };
      },
    } as never);
    return renderAt(`/record/${ID}`);
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5); // pin poll jitter to exactly 1x
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

  // --- 0. the premise -------------------------------------------------------

  it('first paint reads the runs ONCE, and both runs are on screen', async () => {
    const view = mount();
    await settle();
    expect(runCards(view)).toBe(2);
    expect(runsReads(calls), 'the runs list is read once on first paint').toHaveLength(1);
    view.unmount();
  });

  // --- 1. a colleague's RUN EDIT -> exactly one bounded re-read -------------

  it("a colleague's run EDIT costs exactly ONE bounded runs re-read", async () => {
    const view = mount();
    await settle();
    expect(runCards(view)).toBe(2);
    const before = runsReads(calls).length;

    /*
     * THE RECORD POLLER IS HELD — the feed-wins-the-race ordering, which is the window
     * between a colleague's write landing and this client's next conditional GET
     * seeing it.
     *
     * IT DOES NOT ISOLATE `activity`, AND AN EARLIER REVISION OF THIS COMMENT CLAIMED
     * IT DID. That claim is struck rather than reworded because it was measured false
     * and the measurement is the useful part: even held, deleting
     * `activity={runActivity}` leaves this test GREEN. `hold` only silences the
     * CONDITIONAL GET, and `needsCanonicalRefetch` makes any run signal trigger a
     * bundle refetch whose plain `GET {id}` is not held at all — so `detail.version`
     * moves either way and the completeness path re-reads either way. See control A in
     * this file's header for the full result. What this test does establish is that ONE
     * event costs ONE bounded read on the feed-first ordering, which control D shows is
     * not free.
     */
    detail.hold(true);
    /*
     * WHAT ONE COLLEAGUE'S RUN EDIT ACTUALLY PRODUCES, per the feed contract: the
     * record's own entry AND the run's, both at the new rev. Modelling only the run
     * entry would be modelling something the server does not emit.
     */
    serverRuns = [
      runFixture({ id: RUN_ONE, label: 'Run 1 (edited by a colleague)', ordinal: 1 }),
      runFixture({ id: RUN_TWO, label: 'Run 2', ordinal: 2 }),
    ];
    detail.bump(KNOWN_REV + 1);
    feed.changes = [experimentEntry(KNOWN_REV + 1), runEntry(RUN_ONE, KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 3);

    const added = runsReads(calls).length - before;
    expect(added, 'exactly one runs re-read for one run edit').toBe(1);

    /*
     * BOUNDED, ASSERTED ON THE WIRE. `RunsSection` re-reads only what is on screen —
     * `pendingSignalLimitRef` is the received count, which is 2 here. A re-read that
     * dropped the bound would fetch a 1,000-run list to show a one-field change, and a
     * spy on `api.listRuns` would not distinguish the two.
     */
    expect(runsReadLimits(calls).slice(before)).toEqual(['2']);

    // ...and the edit is on screen, so the re-read was adopted rather than merely made.
    expect(view.container.textContent).toContain('Run 1 (edited by a colleague)');
    view.unmount();
  });

  // --- 2. a colleague's RUN REMOVAL -> the completeness path ----------------

  it("a colleague's run REMOVAL disappears from the section, on ONE re-read, with NO run entry in the feed", async () => {
    const view = mount();
    await settle();
    expect(runCards(view)).toBe(2);
    const before = runsReads(calls).length;

    /*
     * A REMOVAL IS INVISIBLE TO THE FAST PATH, BY CONSTRUCTION. The feed is a
     * coalescing STATE projection over entities that EXIST, so a removed run has no
     * entry to report — only the record's own entry moves. The feed page below
     * therefore carries the `experiment` entry and NOTHING ELSE, which is what makes
     * this test a test of `recordVersion` and not of `activity`.
     */
    serverRuns = [runFixture({ id: RUN_ONE, label: 'Run 1', ordinal: 1 })];
    detail.bump(KNOWN_REV + 1);
    feed.changes = [experimentEntry(KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 3);

    expect(runCards(view)).toBe(1);
    expect(view.container.textContent).not.toContain('Run 2');

    const added = runsReads(calls).length - before;
    expect(added, 'exactly one runs re-read for one removal').toBe(1);
    expect(runsReadLimits(calls).slice(before)).toEqual(['2']);
    view.unmount();
  });

  // --- 3. a PROPOSAL-ONLY page -> no runs read on the feed's account --------

  it('a PROPOSAL-ONLY feed page costs NO runs re-read on the feed’s own account, and exactly one on the record poller’s', async () => {
    const view = mount();
    await settle();
    expect(runCards(view)).toBe(2);
    const before = runsReads(calls).length;

    /*
     * THE FEED WINS THE RACE AND CARRIES ONLY A PROPOSAL. `hold(true)` keeps the record
     * poller's conditional GET answering 304 while the bumped body is already being
     * served to a plain GET — the window between a colleague's write landing and this
     * client's next conditional GET seeing it, which is where the feed can legitimately
     * arrive first. Without the hold this leg is unreachable and the assertion below
     * would be measuring the ordinary ordering twice.
     */
    detail.hold(true);
    detail.bump(KNOWN_REV + 1);
    feed.changes = [proposalEntry(1, KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 2);

    expect(
      runsReads(calls).length - before,
      'a proposal is not run news: the runs list is not re-read for it',
    ).toBe(0);

    /*
     * THE DISCLOSED COST. The proposal act bumped the RECORD's revision, so once the
     * record poller stops being held it adopts a new `detail.version` and the
     * completeness path re-reads — one bounded read, for a change that was not a run's.
     * That is the price of a path that can see a removal, and it is stated rather than
     * hidden: `recordVersion` moving is the only signal a removal ever produces, so a
     * completeness path that ignored a record-only bump would ignore removals too.
     */
    detail.hold(false);
    await settle(POLL_INTERVAL_MS * 3);
    expect(
      runsReads(calls).length - before,
      'exactly one, once the record poller adopts the bumped version',
    ).toBe(1);
    expect(runsReadLimits(calls).slice(before)).toEqual(['2']);
    view.unmount();
  });

  // --- 4. the record poller winning -> the same one -------------------------

  it('the RECORD POLLER winning the race totals the same ONE re-read', async () => {
    const view = mount();
    await settle();
    expect(runCards(view)).toBe(2);
    const before = runsReads(calls).length;

    /*
     * BUNDLE FIRST, FEED SECOND. The record poller's conditional GET is NOT held, so it
     * sees the new version on its next tick and the bundle refetch lands before the
     * feed page arrives — the ordinary ordering. Both paths then have something to say
     * about the same event, and the point of this test is that they do not each fetch.
     */
    serverRuns = [
      runFixture({ id: RUN_ONE, label: 'Run 1 (edited)', ordinal: 1 }),
      runFixture({ id: RUN_TWO, label: 'Run 2', ordinal: 2 }),
    ];
    detail.bump(KNOWN_REV + 1);
    await settle(POLL_INTERVAL_MS * 2);
    feed.changes = [experimentEntry(KNOWN_REV + 1), runEntry(RUN_ONE, KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 3);

    expect(
      runsReads(calls).length - before,
      'whichever poller wins, the runs list is re-read once for one event',
    ).toBe(1);
    expect(view.container.textContent).toContain('Run 1 (edited)');
    view.unmount();
  });

  // --- 5. unmount mid-refresh ----------------------------------------------

  it('unmounting mid-refresh leaves no timer and no act warning', async () => {
    const warn = vi.spyOn(console, 'error').mockImplementation(() => {});
    const view = mount();
    await settle();
    expect(runCards(view)).toBe(2);

    detail.bump(KNOWN_REV + 1);
    feed.changes = [experimentEntry(KNOWN_REV + 1), runEntry(RUN_ONE, KNOWN_REV + 1)];
    // Advance ONE tick so the signal has been delivered and a re-read is outstanding,
    // then tear the tree down underneath it.
    await settle(POLL_INTERVAL_MS);
    view.unmount();
    await settle(POLL_INTERVAL_MS * 3);

    expect(vi.getTimerCount(), 'every interval and timeout is cleared on unmount').toBe(0);
    const acts = warn.mock.calls
      .map((c) => String(c[0] ?? ''))
      .filter((m) => m.includes('not wrapped in act'));
    expect(acts, 'a state update landed after unmount').toEqual([]);
  });

  // --- 6. the change-feed page size (Part 2) -------------------------------

  it('the change-feed request carries limit=200, the server’s own maximum', async () => {
    const view = mount();
    /*
     * TWO SETTLES, AND THE FIRST ONE IS LOAD-BEARING. `useChangeFeed` polls only while
     * `enabled` — which `useRecordSession` gates on the record having LOADED — so a
     * single `settle(POLL_INTERVAL_MS * 2)` advances the clock past the first tick
     * before the bundle has resolved and the feed is never polled at all. Measured: the
     * first version of this test asserted `limit=200` over ZERO requests and reported
     * `expected 0 to be greater than 0`, which is the assertion doing its job — a
     * vacuous `for` over an empty list would have PASSED.
     */
    await settle();
    await settle(POLL_INTERVAL_MS * 2);

    const feedReads = calls.filter((c) => c.replace(/\?.*$/, '') === `GET ${BASE}/changes`);
    expect(feedReads.length, 'the feed was polled at all').toBeGreaterThan(0);

    /*
     * EVERY feed read, not just the first. A limit passed only on the cursorless mount
     * read — or only on the continuations — would halve the benefit and would pass an
     * assertion written about one of them.
     */
    for (const read of feedReads) {
      const q = read.includes('?') ? read.slice(read.indexOf('?') + 1) : '';
      expect(new URLSearchParams(q).get('limit'), read).toBe(String(CHANGE_FEED_CLIENT_LIMIT));
    }
    expect(CHANGE_FEED_CLIENT_LIMIT, "change_feed.CHANGE_FEED_LIMIT_MAX").toBe(200);
    view.unmount();
  });
});

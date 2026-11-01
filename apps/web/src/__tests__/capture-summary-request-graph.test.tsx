/*
 * THE SIDEBAR'S CAPTURE COUNTS COST NO REQUEST ON ANY WORKSPACE, AND STAY TRUE LIVE.
 *
 * ── WHAT `record-capture-destination.test.tsx` ALREADY OWNS, AND WHAT IT DID NOT ─
 *
 * That file pins that the counts are the RECORD PAYLOAD'S (`capture_summary`) and
 * that `?view=fields` reads neither list to get them. Two things were left to a
 * comment rather than a test after `lib/useCaptureSummary.ts` was deleted
 * (2026-09-11):
 *
 *   1. "No extra request" on EVERY workspace, not one. The deleted hook ran on
 *      every workspace but the one whose panels read the lists themselves, so a
 *      regression reintroduced behind a workspace gate would pass a single-view
 *      check. Each workspace is enumerated below; the proposals workspace is the
 *      control — its PANELS read the lists (three reads, enumerated with their
 *      owners), and the sidebar adds nothing on top.
 *   2. LIVE TRUTHFULNESS. The deleted hook re-read the two lists whenever the
 *      change feed's `note`/`proposal` positions moved. The bundle-borne count
 *      moves only when the BUNDLE refetches, and `needsCanonicalRefetch`
 *      deliberately refetches nothing for a proposal-only feed summary
 *      (`live-refresh-request-graph.test.tsx` pins that). So the claim "the bundle
 *      refetch already covers it" decomposes into three paths, each pinned here:
 *        · a `note` entry is an `otherKinds` entry, so the FEED refetches;
 *        · a proposal act moves the record's own ETag (the server hashes proposals
 *          into the revision signature — `test_capture_summary_on_detail.py` pins
 *          that half), so the RECORD POLLER refetches;
 *        · a proposal-only feed page with the record poller not yet caught up
 *          refetches NOTHING and the count waits — for exactly one record-poller
 *          interval, after which it is right. That wait is stated, not hidden.
 *
 * ── MUTATION-CHECKED 2026-10-29 ─────────────────────────────────────────────
 *
 * Each break applied to production code, this file re-run, then reverted:
 *   A. Restored the pre-2026-09-11 `useCaptureSummary` (`GET .../notes?state=
 *      dismissed` + `GET .../proposals?limit=1`, gated off on `proposals`) and
 *      wired it back into `RecordWorkbench` — 8 RED: all five non-proposals
 *      workspace tests (2 extra list reads each) and all three live tests (the
 *      badge then states the lists' disagreeing numbers); the proposals control
 *      stays green, as it must.
 *   B. `captureSummary` frozen at the first-paint value (a `useRef` snapshot
 *      instead of `detail.capture_summary`) — 3 RED, the three live tests.
 *   C. `needsCanonicalRefetch` with `otherKinds` dropped — 1 RED, the `note` live
 *      test (the record-poller paths still carry the other two, correctly).
 *
 * ── WHAT IT DOES NOT MEASURE ────────────────────────────────────────────────
 *
 * Bytes and latency (jsdom `fetch` is a stub). Request COUNTS and URLs are exact.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, act, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import {
  bundleRoutes,
  experimentDetail,
  noteFixture,
  notesPage,
  proposalsEmpty,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { RouteResult } from '../test/apiFixtures';
import type { ApiCaptureSummary, ApiChangeEntry, ApiChangeFeedPage } from '../lib/types';
import { POLL_INTERVAL_MS } from '../lib/useRecordSync';

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;
const KNOWN_REV = Number(String(experimentDetail.version).split('.').pop());

async function settle(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

/** Path-only match: a list read is a list read whatever its query string. */
function countPath(calls: string[], key: string): number {
  return calls.filter((c) => c.replace(/\?.*$/, '') === key).length;
}
const listReads = (calls: string[]) =>
  countPath(calls, `GET ${BASE}/notes`) + countPath(calls, `GET ${BASE}/proposals`);
/** `GET …/draft` is issued once per bundle and by nothing else — the bundle witness. */
const bundleCount = (calls: string[]) => countPath(calls, `GET ${BASE}/draft`);

/**
 * A detail route with ETag semantics, a hold switch (so the feed can win the race),
 * and a MUTABLE `capture_summary` — the server's count moving is the whole event.
 */
function detailRoute(initial: ApiCaptureSummary) {
  let rev = KNOWN_REV;
  let held = false;
  let summary = initial;
  const bodyFor = () => ({
    ...experimentDetail,
    id: ID,
    version: `1.${rev}`,
    rev,
    capture_summary: summary,
  });
  return {
    write: (toRev: number, next: ApiCaptureSummary) => {
      rev = toRev;
      summary = next;
    },
    hold: (v: boolean) => {
      held = v;
    },
    route: (init?: RequestInit): RouteResult => {
      const inm = (init?.headers as Record<string, string> | undefined)?.['If-None-Match'];
      if (inm && (held || inm === `"1.${rev}"`)) return { status: 304, etag: inm };
      return { status: 200, body: bodyFor(), etag: `"1.${rev}"` };
    },
  };
}

function feedPage(changes: ApiChangeEntry[]): ApiChangeFeedPage {
  return {
    changes,
    next_cursor: `CURSOR-${changes.length}-${changes[0]?.changed_at_rev ?? 0}`,
    has_more: false,
    limit: 50,
    returned: changes.length,
    remaining: 0,
    kinds: ['experiment', 'note', 'proposal', 'run'],
  } as ApiChangeFeedPage;
}

const entry = (kind: string, entityId: string, rev: number): ApiChangeEntry =>
  ({
    kind,
    entity_id: entityId,
    changed_at_rev: rev,
    updated_utc: '2026-10-29T10:00:00Z',
    ...(kind === 'proposal' ? { state: 'open' } : {}),
  }) as ApiChangeEntry;

/** The Proposals badge as a screen reader reaches it — the link's own description. */
function badge(): string | null {
  const group = screen.getByRole('navigation', { name: 'Data Capture' });
  const link = within(group).getByRole('link', { name: 'Proposals' });
  const id = link.getAttribute('aria-describedby');
  return id === null ? null : (document.getElementById(id)?.textContent ?? null);
}

describe('the capture summary — request graph and live truth', () => {
  let detail: ReturnType<typeof detailRoute>;
  let feed: { changes: ApiChangeEntry[] };
  let calls: string[];

  function mount(view: string, initial: ApiCaptureSummary) {
    detail = detailRoute(initial);
    feed = { changes: [] };
    calls = stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}`]: detail.route,
      // Both list routes are SERVED, with numbers that disagree with the payload,
      // so a surface that went back to reading them is caught by the count AND by
      // what it would render.
      [`GET ${BASE}/notes`]: { body: notesPage([noteFixture()], { total: 9 }) },
      [`GET ${BASE}/proposals`]: {
        body: { ...proposalsEmpty, total: 11, by_state: { ...proposalsEmpty.by_state, open: 7 } },
      },
      [`GET ${BASE}/changes`]: () => {
        const changes = feed.changes;
        feed.changes = [];
        return { body: feedPage(changes) };
      },
    } as never);
    return render(
      <MemoryRouter
        initialEntries={[`/record/${ID}?view=${view}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
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

  // --- 1. no list read for the count, on any workspace ------------------------

  const TWO_OPEN = { notes_total: 3, proposals_open: 2, unreadable_entries: 0 };

  for (const view of ['fields', 'runs', 'graph', 'capture', 'activity']) {
    it(`?view=${view}: first paint AND three poll cycles read neither list, and the badge is the payload's`, async () => {
      mount(view, TWO_OPEN);
      await settle();
      await settle(POLL_INTERVAL_MS * 3);
      expect(badge()).toBe('2 awaiting review');
      expect(
        calls.filter((c) => /\/(notes|proposals)(\?|$)/.test(c)),
        'no notes/proposals list read on a workspace without those panels',
      ).toEqual([]);
    });
  }

  it('CONTROL — ?view=proposals: only the PANELS read the lists, and the sidebar adds none', async () => {
    mount('proposals', TWO_OPEN);
    await settle();
    /*
     * ENUMERATED, WITH OWNERS, rather than counted. All three are panel-owned and
     * none is the count: `IngestionProposalsPanel` reads its window
     * (`GET …/proposals`), `UnmappedNotesPanel` reads its list (`GET …/notes`) and,
     * separately, the proposal CAPABILITIES it needs to offer "Propose"
     * (`GET …/proposals?limit=1` — `target_field_paths`, not `by_state`). The
     * deleted hook's pair was `notes?state=dismissed` + `proposals?limit=1`; the
     * first is the one that must never reappear.
     */
    expect(calls.filter((c) => /\/(notes|proposals)(\?|$)/.test(c)).sort()).toEqual(
      [
        `GET ${BASE}/notes`,
        `GET ${BASE}/proposals`,
        `GET ${BASE}/proposals?limit=1`,
      ].sort(),
    );
    // Withheld here by design: the panels beside it state their own counts.
    expect(badge()).toBeNull();
  });

  // --- 2. a live change updates the count -------------------------------------

  it('a NOTE feed entry (feed wins the race) refetches the bundle, and the count follows', async () => {
    mount('capture', { notes_total: 1, proposals_open: 1, unreadable_entries: 0 });
    await settle();
    expect(badge()).toBe('1 awaiting review');
    const bundles = bundleCount(calls);

    detail.hold(true); // the record poller has not seen the write yet
    detail.write(KNOWN_REV + 1, { notes_total: 2, proposals_open: 3, unreadable_entries: 0 });
    feed.changes = [entry('note', '01NOTE0000000000000000000A', KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 2);

    expect(bundleCount(calls) - bundles, 'the feed alone refetched once').toBe(1);
    expect(badge()).toBe('3 awaiting review');
    expect(listReads(calls)).toBe(0);
  });

  it('a PROPOSAL act seen by the RECORD POLLER first refetches the bundle, and the count follows', async () => {
    mount('fields', { notes_total: 1, proposals_open: 1, unreadable_entries: 0 });
    await settle();
    const bundles = bundleCount(calls);

    detail.write(KNOWN_REV + 1, { notes_total: 1, proposals_open: 2, unreadable_entries: 0 });
    feed.changes = [
      entry('experiment', ID, KNOWN_REV + 1),
      entry('proposal', '01PROPOSAL0000000000000001', KNOWN_REV + 1),
    ];
    await settle(POLL_INTERVAL_MS * 3);

    expect(bundleCount(calls) - bundles, 'exactly one bundle').toBe(1);
    expect(badge()).toBe('2 awaiting review');
    expect(listReads(calls)).toBe(0);
  });

  it('a PROPOSAL-ONLY feed page refetches nothing; the count waits for the record poller, then is right', async () => {
    mount('fields', { notes_total: 1, proposals_open: 1, unreadable_entries: 0 });
    await settle();
    const bundles = bundleCount(calls);

    detail.hold(true);
    detail.write(KNOWN_REV + 1, { notes_total: 1, proposals_open: 0, unreadable_entries: 0 });
    feed.changes = [entry('proposal', '01PROPOSAL0000000000000001', KNOWN_REV + 1)];
    await settle(POLL_INTERVAL_MS * 2);
    // Stated, not hidden: `needsCanonicalRefetch` is false for a proposal-only
    // summary, so for this window the bundle-borne count is the pre-write one.
    expect(bundleCount(calls) - bundles).toBe(0);
    expect(badge()).toBe('1 awaiting review');

    // The proposal act moved the record's ETag; once the record poller sees it,
    // ONE bundle refetch carries the new count. Nothing else is needed.
    detail.hold(false);
    await settle(POLL_INTERVAL_MS * 2);
    expect(bundleCount(calls) - bundles).toBe(1);
    expect(badge()).toBeNull(); // zero open: no badge, never a "0"
    expect(listReads(calls)).toBe(0);
  });
});

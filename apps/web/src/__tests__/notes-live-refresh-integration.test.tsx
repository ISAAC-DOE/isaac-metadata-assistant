/*
 * THE NOTES LIVE REFRESH, THROUGH THE REAL SCREEN — producer to consumer, counted at
 * the wire.
 *
 * ── WHY THIS FILE EXISTS AND `unmapped-notes.test.tsx` DOES NOT COVER IT ────────
 *
 * That file renders `UnmappedNotesPanel` directly and hands it an `activity` object
 * as a prop. It is the right test for "given this summary, does the panel re-read?"
 * and it is structurally incapable of answering the question F-1 actually turned on:
 * **is anything connected to that prop at all?**
 *
 * Modelled directly on `runs-live-refresh-integration.test.tsx`'s own header, because
 * this is the same shape of defect it exists to catch: a producer
 * (`useRecordSession.notesActivity`) and a consumer (`UnmappedNotesPanel`'s `activity`
 * prop) can each ship with a fully green unit suite while `RecordWorkbench` renders
 * `<UnmappedNotesPanel experimentId={id} />` with nothing threaded — a colleague's
 * note moves no pixel, and neither branch's tests could see it, because neither
 * branch's tests mount the screen that wires them.
 *
 * UNLIKE `RunsSection`, THIS PANEL HAS NO `recordVersion` FALLBACK PROP, so there is
 * no second path that could subsume this one — see control A in the runs file's own
 * header for what that subsumption looks like and why it matters that nothing here
 * plays the same role. If this fix is disconnected, nothing else on this screen
 * re-reads the notes list on its behalf.
 *
 * So this file mounts the REAL `AppRoutes` at `/record/:id?view=capture` — the
 * workspace that mounts `UnmappedNotesPanel` — stubs `fetch` and nothing else, and
 * counts `GET …/notes` at the recorded URL.
 *
 * ── WHAT IT PINS ────────────────────────────────────────────────────────────────
 *
 *   1. First paint reads the notes ONCE, with the seeded note on screen.
 *   2. A colleague's note arriving (the record's `experiment` entry moving, since
 *      there is no `note` change-feed kind — see `useRecordSession.notesActivity`)
 *      costs exactly ONE notes re-read and the new note appears, on the FEED-FIRST
 *      ordering (the record poller's conditional GET held at 304 while the plain
 *      GET already serves the bumped body).
 *   3. The SAME event on the RECORD-POLLER-FIRST ordering (the ordinary one) also
 *      costs exactly one re-read and the note appears — reviewer-verified ordering.
 *
 * ── THE MUTATION CONTROL, RUN AND REVERTED ──────────────────────────────────────
 *
 * `activity={notesActivity}` was deleted from `RecordWorkbench.tsx:1117` (leaving
 * `<UnmappedNotesPanel experimentId={id} />`) and this file re-run:
 * **test 2 and test 3 both FAILED** (`expected +0 to be 1` — no second `GET
 * …/notes` — and the seeded second note never appears on screen). Test 1 stayed
 * green, which is expected: first paint does not depend on this prop at all. The
 * change was then reverted and this file re-run green. That is the disconnection
 * this file exists to catch, reproduced and confirmed caught.
 *
 * ── WHAT IT DOES NOT MEASURE, STATED RATHER THAN IMPLIED ────────────────────────
 *
 * BYTES AND LATENCY. jsdom's `fetch` is a stub; there is no wire and no server.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import {
  bundleRoutes,
  experimentDetail,
  noteFixture,
  notesPage,
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
 * A `GET {id}` route with real ETag semantics AND a `held` switch — lifted from
 * `runs-live-refresh-integration.test.tsx` for the reason that file states: a fixture
 * that always answers the bumped version once bumped makes the FEED-FIRST ordering
 * unreachable. `held` keeps the conditional GET answering 304 while the plain GET
 * already serves the bumped body — exactly the state the two pollers are in when the
 * feed wins the race.
 */
function detailRoute(): {
  route: (init?: RequestInit) => RouteResult;
  bump: (toRev: number) => void;
  hold: (held: boolean) => void;
} {
  let rev = KNOWN_REV;
  let held = false;
  const token = () => `1.${rev}`;
  const bodyFor = () => ({ ...experimentDetail, id: ID, version: token(), rev });
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

/** There is no `note` kind — see `useRecordSession.notesActivity`. A note write
 *  rides on the record's own entry, which is what this models. */
const experimentEntry = (rev: number): ApiChangeEntry => ({
  kind: 'experiment',
  entity_id: ID,
  changed_at_rev: rev,
  updated_utc: '2026-09-03T10:00:00Z',
});

/** Every recorded `GET …/notes`. */
function notesReads(calls: string[]): string[] {
  return calls.filter((c) => c.replace(/\?.*$/, '') === `GET ${BASE}/notes`);
}

function noteCards(view: { container: HTMLElement }): number {
  return view.container.querySelectorAll('.note-card').length;
}

describe('the notes live refresh, wired through the real Record Workbench', () => {
  let detail: ReturnType<typeof detailRoute>;
  let feed: { changes: ApiChangeEntry[] };
  let calls: string[];
  /** The note set the server currently holds. Mutated by a test to model a
   *  colleague's Finalize minting a note this reader never touched. */
  let serverNotes: ReturnType<typeof noteFixture>[];

  function mount() {
    detail = detailRoute();
    feed = { changes: [] };
    serverNotes = [noteFixture({
      id: 'note-1',
      text: 'first note, seeded on the record',
      display_text: 'first note, seeded on the record',
    })];
    calls = stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}`]: detail.route,
      [`GET ${BASE}/notes`]: () => ({ body: notesPage([...serverNotes]) }),
      // ONE-SHOT, which is what a cursor actually does: the real feed advances
      // past what it returned, so a second poll gets an empty page.
      [`GET ${BASE}/changes`]: () => {
        const changes = feed.changes;
        feed.changes = [];
        return { body: feedPage(changes) };
      },
    } as never);
    // `?view=capture` — the record screen's four workspaces are `?view=` deep
    // links on one route, and `UnmappedNotesPanel` lives on `capture`. A bare
    // `/record/<id>` opens Record Fields, where it is not mounted at all, so
    // every count below would be a count of zero.
    return renderAt(`/record/${ID}?view=capture`);
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

  it('first paint reads the notes ONCE, with the seeded note on screen', async () => {
    const view = mount();
    await settle();
    expect(noteCards(view)).toBe(1);
    expect(notesReads(calls), 'the notes list is read once on first paint').toHaveLength(1);
    view.unmount();
  });

  it(
    "a colleague's Finalize mints a note elsewhere on this screen -> exactly ONE " +
      'notes re-read, and it appears — FEED WINS THE RACE',
    async () => {
      const view = mount();
      await settle();
      expect(noteCards(view)).toBe(1);
      const before = notesReads(calls).length;

      // The record poller's conditional GET is held at 304 while the plain GET
      // already serves the bumped body — the window in which the feed can
      // legitimately arrive first.
      detail.hold(true);
      serverNotes = [
        ...serverNotes,
        noteFixture({
          id: 'note-2',
          text: 'second note, minted elsewhere on this screen',
          display_text: 'second note, minted elsewhere on this screen',
        }),
      ];
      detail.bump(KNOWN_REV + 1);
      feed.changes = [experimentEntry(KNOWN_REV + 1)];
      await settle(POLL_INTERVAL_MS * 3);

      const added = notesReads(calls).length - before;
      expect(added, 'exactly one notes re-read for one record-moving event').toBe(1);
      expect(noteCards(view)).toBe(2);
      expect(view.container.textContent).toContain('second note, minted elsewhere on this screen');
      view.unmount();
    },
  );

  it(
    'the SAME event on the RECORD-POLLER-FIRST ordering (the ordinary one) — still ' +
      'exactly one re-read',
    async () => {
      const view = mount();
      await settle();
      expect(noteCards(view)).toBe(1);
      const before = notesReads(calls).length;

      // BUNDLE FIRST, FEED SECOND. The record poller's conditional GET is NOT
      // held, so it sees the new version on its next tick before the feed page
      // arrives — the ordinary ordering, and the one the reviewer verified.
      serverNotes = [
        ...serverNotes,
        noteFixture({
          id: 'note-2',
          text: 'second note, minted elsewhere on this screen',
          display_text: 'second note, minted elsewhere on this screen',
        }),
      ];
      detail.bump(KNOWN_REV + 1);
      await settle(POLL_INTERVAL_MS * 2);
      feed.changes = [experimentEntry(KNOWN_REV + 1)];
      await settle(POLL_INTERVAL_MS * 3);

      const added = notesReads(calls).length - before;
      expect(added, 'whichever poller wins, one notes re-read for one event').toBe(1);
      expect(noteCards(view)).toBe(2);
      expect(view.container.textContent).toContain('second note, minted elsewhere on this screen');
      view.unmount();
    },
  );
});

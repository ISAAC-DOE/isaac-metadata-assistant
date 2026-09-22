/*
 * THE PROMOTED CAPTURE DESTINATION — the record sidebar's `Data Capture` group.
 *
 * ── WHAT IT IS, AND WHY IT IS NOT A SIXTH WORKFLOW STEP ────────────────────
 *
 * The project owner's observation was that the workflow spine describes the
 * record-COMPLETION lifecycle, and that the scientist's actual first act —
 * writing down what just happened at the instrument — had no place in it and
 * was reaching the reader as the third row of a secondary list. So `capture` is
 * promoted: its own group, above `Workspaces`, carrying the record's live note
 * and open-proposal counts.
 *
 * IT IS STILL NOT A STEP, and that is the property most of this file exists to
 * pin. `apps/api/isaac_api/workflow.py:128-149` keeps submission out of
 * `CANONICAL_ORDER` because a step state needs a criterion the record's own
 * signals can DECIDE. Capture has no such criterion: "the scientist has
 * finished capturing" is not derivable from any count this build holds, and a
 * criterion invented in the client (`notes >= 1`, say) would leave every record
 * that legitimately needs no notes permanently unsatisfied — a spine nagging
 * falsely, which is the no-guessing rule (CLAUDE.md §5) broken in the UI.
 *
 * ── AND WHY THE COUNTS ARE THE SERVER'S TOTALS ─────────────────────────────
 *
 * They arrive on the record's OWN detail payload (`capture_summary`), which this
 * screen already fetches. That is a 2026-09-11 change and it deleted
 * `lib/useCaptureSummary.ts`: the numbers used to be assembled here from
 * `GET .../notes?state=dismissed` and `GET .../proposals?limit=1` — two extra
 * requests per record load on three of the four workspaces, the notes one
 * unbounded, the filter present only to shrink a payload whose rows were thrown
 * away. The tests that pinned "the server's TOTAL, not the fetched array's
 * length" are kept and re-pointed: the list routes now serve numbers that
 * DISAGREE with the bundle's, so a surface that went back to reading them fails
 * here rather than passing against a fixture where the two happen to agree.
 * CLAUDE.md §11 records four separate surfaces that shipped exactly that defect.
 *
 * ── WHAT THIS FILE DOES NOT OWN ────────────────────────────────────────────
 *
 * `record-workspaces.test.tsx` owns the four destinations as a set, the push /
 * Back contract, the query-string copying and the `aria-current="page"`
 * anti-goals over every link in the landmark. This file owns only what
 * promoting one of them added.
 *
 * ── MUTATION-CHECKED, 2026-09-11 ───────────────────────────────────────────
 *
 * Each break was applied to the production code, this file plus
 * `record-workspaces.test.tsx` and `notes-live-refresh-integration.test.tsx`
 * re-run, and then reverted (33 pass):
 *
 *   1. Dropped the capture-workspace gate in `RecordWorkbench`
 *      (`detail.capture_summary ?? null`, unconditionally) — 1 RED, the gate test.
 *   2. Treated an ABSENT `capture_summary` as three zeroes rather than as unknown
 *      — 1 RED, "says NOTHING AT ALL … never 0". That is the assertion that keeps
 *      "the record holds nothing" and "this client does not know" apart.
 *   3. Gave `captureSummaryLine` a verdict clause
 *      (`'all reviewed — nothing outstanding'` when nothing is open) — 3 RED,
 *      including the 27-case enumeration, which is the guard a keyword blacklist
 *      once failed to be (see the note above the table).
 *   4. Hardcoded the note count to `1` instead of reading the server's — 4 RED,
 *      including "states the RECORD PAYLOAD'S counts".
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import {
  bundleRoutes,
  captureDetail,
  detailWithoutCaptureSummary,
  noteFixture,
  notesPage,
  proposalsEmpty,
  runFixture,
  runsPage,
  stubFetchRoutes,
} from '../test/apiFixtures';
import { captureSummaryLine } from '../components/RecordWorkspaceNav';

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

/** A proposals listing with the server's own `by_state`, and a WINDOW of rows. */
function proposalsWindow(over: Record<string, unknown>) {
  return { ...proposalsEmpty, ...over };
}

function renderAt(path: string, extra: Record<string, unknown> = {}) {
  stubFetchRoutes({
    ...bundleRoutes(ID),
    [`GET ${BASE}/runs`]: { body: runsPage([runFixture({ id: 'RUNAAA', label: 'Run 1' })]) },
    ...extra,
  } as never);
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

const nav = () => screen.getByRole('navigation', { name: 'Record workspaces' });
const captureNav = () => screen.getByRole('navigation', { name: 'Data Capture' });
const captureLink = () => within(captureNav()).getByRole('link', { name: 'Capture' });
const proposalsLink = () => within(captureNav()).getByRole('link', { name: 'Proposals' });
/** The rail is rendered only once the record has loaded. */
const loaded = () => screen.findByRole('link', { name: 'Activity' });

/** The Proposals badge as a screen reader reaches it — the link's own
 *  description, never text that happens to sit nearby. */
function proposalsDescription(): string | null {
  const id = proposalsLink().getAttribute('aria-describedby');
  if (id === null) return null;
  return document.getElementById(id)?.textContent ?? null;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/*
 * ── REWRITTEN 2026-09-22 (owner QA N3), INVERTED RATHER THAN DROPPED ────────
 *
 * The promoted `Experiment Data` CARD, with its note/proposal counts as the link's
 * description, is gone. The group is three ordinary destination rows — Capture
 * (Capture Home), Proposals (the one focused review surface) and Runs — and the
 * counts moved to where they are USED:
 *
 *   · the open-proposal count is a badge on the Proposals row (the thing it counts
 *     is behind that row), described to a screen reader as "<n> awaiting review";
 *   · the whole summary line — notes, open proposals, unreadable entries — is on
 *     Capture Home, pinned by `capture-intake.test.tsx` and below.
 *
 * Every property the old file pinned survives in its new place: the group is a
 * named landmark above the spine and the workspaces; a count is the SERVER'S
 * total from the record payload and no list is read for it; an unknown total
 * renders NOTHING rather than "0"; the count is withheld on the one destination
 * whose panels state their own; and neither row carries completion state.
 */
describe('the Data Capture group', () => {
  it('is its own NAMED landmark, above the workspaces list AND above the workflow spine', async () => {
    renderAt(`/record/${ID}`);
    await loaded();
    const group = captureNav();
    expect(
      within(group)
        .getAllByRole('link')
        .map((l) => l.getAttribute('aria-label') ?? l.textContent),
    ).toEqual(['Capture', 'Proposals', 'Runs']);
    const spine = screen.getByRole('navigation', { name: 'Workflow pipeline' });
    expect(group.compareDocumentPosition(spine) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(group.compareDocumentPosition(nav()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('Capture routes to Capture Home, copying the address and dropping a task or proposal focus', async () => {
    renderAt(`/record/${ID}?view=capture&method=write&run=RUNAAA&proposal=P1`);
    await loaded();
    const query = new URLSearchParams((captureLink().getAttribute('href') ?? '').split('?')[1]);
    expect(query.get('view')).toBe('capture');
    expect(query.get('run')).toBe('RUNAAA');
    // `method` would reopen the task; `view=capture&proposal=` would open Proposals.
    expect(query.has('method')).toBe(false);
    expect(query.has('proposal')).toBe(false);
  });

  it('marks Capture with aria-current="page" on Capture Home AND on its focused views', async () => {
    renderAt(`/record/${ID}?view=capture&method=voice`);
    await waitFor(() => expect(captureLink()).toHaveAttribute('aria-current', 'page'));
    expect(proposalsLink()).not.toHaveAttribute('aria-current');
  });

  it('the Proposals badge states the RECORD PAYLOAD’S open count, and reads no list to get it', async () => {
    const calls = stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}`]: { body: { ...captureDetail({ notes_total: 3, proposals_open: 2 }), id: ID } },
      [`GET ${BASE}/runs`]: { body: runsPage([runFixture({ id: 'RUNAAA', label: 'Run 1' })]) },
      // The list routes DISAGREE with the payload, so a badge that went back to
      // reading them fails here rather than passing on agreeing fixtures.
      [`GET ${BASE}/notes`]: { body: notesPage([noteFixture()], { total: 9 }) },
      [`GET ${BASE}/proposals`]: {
        body: proposalsWindow({
          proposals: [],
          total: 11,
          returned: 0,
          by_state: { open: 7, accepted: 4, rejected: 0, superseded: 0, withdrawn: 0 },
        }),
      },
    } as never);
    render(
      <MemoryRouter
        initialEntries={[`/record/${ID}?view=fields`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    await loaded();
    await waitFor(() => expect(proposalsDescription()).toBe('2 awaiting review'));
    const listReads = calls.filter((c) => {
      const path = c.replace(/\?.*$/, '');
      return path === `GET ${BASE}/notes` || path === `GET ${BASE}/proposals`;
    });
    expect(listReads).toEqual([]);
  });

  it('shows NO badge when nothing is open — never a "0"', async () => {
    // `bundleRoutes` serves a detail whose `capture_summary` is three zeroes.
    renderAt(`/record/${ID}?view=fields`);
    await loaded();
    expect(proposalsLink().getAttribute('aria-describedby')).toBeNull();
    expect(proposalsLink().textContent).toBe('Proposals');
  });

  it('says NOTHING AT ALL while the counts are unknown — never "0"', async () => {
    renderAt(`/record/${ID}?view=fields`, {
      [`GET ${BASE}`]: { body: detailWithoutCaptureSummary(ID) },
    });
    await loaded();
    expect(proposalsLink().getAttribute('aria-describedby')).toBeNull();
    expect(proposalsLink().textContent).toBe('Proposals');
  });

  it('withholds the badge on the Proposals view, whose panels state their own counts', async () => {
    const calls = stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}`]: { body: { ...captureDetail({ notes_total: 3, proposals_open: 2 }), id: ID } },
      [`GET ${BASE}/runs`]: { body: runsPage([runFixture({ id: 'RUNAAA', label: 'Run 1' })]) },
      [`GET ${BASE}/notes`]: { body: notesPage([noteFixture()], { total: 3 }) },
    } as never);
    render(
      <MemoryRouter
        initialEntries={[`/record/${ID}?view=proposals`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    await loaded();
    await waitFor(() => expect(proposalsLink()).toHaveAttribute('aria-current', 'page'));
    // The PANELS read their lists, exactly once each.
    await waitFor(() =>
      expect(calls.filter((c) => c.replace(/\?.*$/, '') === `GET ${BASE}/notes`)).toHaveLength(1),
    );
    expect(proposalsLink().getAttribute('aria-describedby')).toBeNull();
    expect(proposalsLink().textContent).toBe('Proposals');
  });

  it('Capture Home discloses stored entries neither list could read, rather than understating the record', async () => {
    renderAt(`/record/${ID}?view=capture`, {
      // The SERVER sums the two kinds (`routes._capture_summary`); the client
      // renders the sum. Nothing here adds two numbers together.
      [`GET ${BASE}`]: {
        body: { ...captureDetail({ notes_total: 1, unreadable_entries: 2 }), id: ID },
      },
    });
    await loaded();
    await waitFor(() =>
      expect(document.querySelector('.capture-home-summary')?.textContent ?? '').toContain(
        '1 note · 2 unreadable entries',
      ),
    );
  });

  it.each([
    ['inactive', 'fields'],
    ['ACTIVE', 'capture'],
    ['ACTIVE', 'proposals'],
  ])('carries NO completion state while %s (%s) — no tick, no lock, no reason, no step', async (
    _name,
    view,
  ) => {
    renderAt(`/record/${ID}?view=${view}`, {
      [`GET ${BASE}`]: { body: { ...captureDetail({ notes_total: 3, proposals_open: 1 }), id: ID } },
    });
    await loaded();
    for (const link of within(captureNav()).getAllByRole('link')) {
      expect(link.getAttribute('aria-current')).not.toBe('step');
      expect(link.getAttribute('aria-disabled')).toBeNull();
      expect(link.className).not.toMatch(/completed|blocked|reopened|current\b/);
      // No state glyph — a tick or a lock would claim a verdict in a picture.
      expect(link.querySelector('svg')).toBeNull();
      expect(link.querySelector('.spine-disc')).toBeNull();
      expect(link.textContent).not.toMatch(/first\./);
      expect(link.tagName).toBe('A');
      expect(link.getAttribute('href')).toBeTruthy();
    }
  });

  it('does not enter the workflow spine, which still derives exactly its five steps', async () => {
    renderAt(`/record/${ID}?view=capture`);
    const spine = await screen.findByRole('navigation', { name: 'Workflow pipeline' });
    await loaded();
    const labels = Array.from(spine.querySelectorAll('.spine-label')).map(
      (el) => (el.textContent ?? '').trim(),
    );
    expect(labels).toHaveLength(5);
    expect(labels.some((l) => /Capture|Proposal/.test(l))).toBe(false);
    expect(spine.contains(captureLink())).toBe(false);
    expect(spine.contains(proposalsLink())).toBe(false);
  });

  it('keeps the Proposals link’s accessible NAME the destination, with the count as its DESCRIPTION', async () => {
    renderAt(`/record/${ID}?view=fields`, {
      [`GET ${BASE}`]: { body: { ...captureDetail({ proposals_open: 4 }), id: ID } },
    });
    await loaded();
    await waitFor(() => expect(proposalsDescription()).toBe('4 awaiting review'));
    expect(proposalsLink().getAttribute('aria-label')).toBe('Proposals');
    expect(screen.queryByRole('link', { name: /awaiting review/ })).toBeNull();
  });
});

/*
 * THE WHOLE OUTPUT SPACE, ENUMERATED — not a keyword blacklist.
 *
 * ── WHY THIS REPLACED A REGEX GUARD, AND THE MEASUREMENT THAT KILLED IT ────
 *
 * This block used to end with an `it` titled "never produces a verdict",
 * asserting `not.toMatch(/ready|complete|blocked|required|finish|first/i)`
 * over three hand-picked summaries. An independent review injected a REAL
 * verdict into `captureSummaryLine`:
 *
 *     else if (summary.notesTotal > 0) parts.push('all reviewed — nothing outstanding');
 *
 * ...and that test STAYED GREEN. Four other tests in this file caught it — the
 * exact-string assertions — and the one NAMED as the guarantee caught nothing.
 * Replacing `captureNavEmpty` with 'All caught up' was the same story. A
 * blacklist only ever forbids the words its author already thought of, and its
 * NAME is what the next author reads before adding a clause.
 *
 * `captureSummaryLine` is a pure function of three integers — the server's own
 * three, taken from the record payload unadapted — and every branch in it turns
 * on `> 0` and `=== 1`. So 0 / 1 / 2 on each of the three axes
 * visits every branch and every combination of branches: 27 cases, each with
 * its string written out. Any added clause, any reworded clause, any verdict,
 * any reordering and any pluralisation slip changes at least one of the 27 and
 * names the case it changed in the failure.
 *
 * The table is deliberately written out rather than snapshotted to a file: a
 * `toMatchSnapshot` would let a future author accept a verdict by re-recording
 * it, which is the same escape in a new shape.
 */
const EVERY_LINE: Record<string, string> = {
  // notes,open,unreadable
  '0,0,0': 'No notes or proposals',
  '0,0,1': '1 unreadable entry',
  '0,0,2': '2 unreadable entries',
  '0,1,0': '1 to review',
  '0,1,1': '1 to review · 1 unreadable entry',
  '0,1,2': '1 to review · 2 unreadable entries',
  '0,2,0': '2 to review',
  '0,2,1': '2 to review · 1 unreadable entry',
  '0,2,2': '2 to review · 2 unreadable entries',
  '1,0,0': '1 note',
  '1,0,1': '1 note · 1 unreadable entry',
  '1,0,2': '1 note · 2 unreadable entries',
  '1,1,0': '1 note · 1 to review',
  '1,1,1': '1 note · 1 to review · 1 unreadable entry',
  '1,1,2': '1 note · 1 to review · 2 unreadable entries',
  '1,2,0': '1 note · 2 to review',
  '1,2,1': '1 note · 2 to review · 1 unreadable entry',
  '1,2,2': '1 note · 2 to review · 2 unreadable entries',
  '2,0,0': '2 notes',
  '2,0,1': '2 notes · 1 unreadable entry',
  '2,0,2': '2 notes · 2 unreadable entries',
  '2,1,0': '2 notes · 1 to review',
  '2,1,1': '2 notes · 1 to review · 1 unreadable entry',
  '2,1,2': '2 notes · 1 to review · 2 unreadable entries',
  '2,2,0': '2 notes · 2 to review',
  '2,2,1': '2 notes · 2 to review · 1 unreadable entry',
  '2,2,2': '2 notes · 2 to review · 2 unreadable entries',
};

describe('captureSummaryLine', () => {
  it('renders nothing at all for an UNKNOWN summary — a different claim from an empty record', () => {
    expect(captureSummaryLine(null)).toBeNull();
    // ...and the empty-record sentence is a real string, so the two can never
    // be confused by a caller branching on falsiness.
    expect(
      captureSummaryLine({ notes_total: 0, proposals_open: 0, unreadable_entries: 0 }),
    ).toBeTruthy();
  });

  it('produces exactly these 27 strings over 0/1/2 on all three counts — nothing else', () => {
    const produced: Record<string, string> = {};
    for (const notes_total of [0, 1, 2]) {
      for (const proposals_open of [0, 1, 2]) {
        for (const unreadable_entries of [0, 1, 2]) {
          const line = captureSummaryLine({ notes_total, proposals_open, unreadable_entries });
          expect(line, `${notes_total},${proposals_open},${unreadable_entries} produced no line`)
            .not.toBeNull();
          produced[`${notes_total},${proposals_open},${unreadable_entries}`] = line as string;
        }
      }
    }
    // Whole-object equality, so an ADDED clause is caught as surely as a
    // changed one and the diff names every case that moved.
    expect(produced).toEqual(EVERY_LINE);
    expect(Object.keys(produced)).toHaveLength(27);
  });

  it('scales past the enumerated range without changing shape', () => {
    /* The table above fixes the GRAMMAR at the only three values where it can
       branch. This is the one property it cannot see: that nothing special
       happens further up, e.g. a cap, a "99+", or a different separator. */
    expect(
      captureSummaryLine({ notes_total: 1204, proposals_open: 37, unreadable_entries: 0 }),
    ).toBe('1204 notes · 37 to review');
  });
});

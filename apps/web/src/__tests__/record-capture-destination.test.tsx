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
const captureLink = () => screen.getByRole('link', { name: 'Capture & Proposals' });

/** The summary line as a screen reader would reach it — through the link's own
 *  description, never by hunting for text that happens to sit nearby. */
function describedText(): string | null {
  const id = captureLink().getAttribute('aria-describedby');
  if (id === null) return null;
  return document.getElementById(id)?.textContent ?? null;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the promoted capture destination', () => {
  it('is its own group, ABOVE the workspaces list, and still inside the one nav landmark', async () => {
    renderAt(`/record/${ID}`);
    await screen.findByRole('link', { name: 'Record Fields' });

    const captureEyebrow = within(nav()).getByText('Data Capture');
    const workspacesEyebrow = within(nav()).getByText('Workspaces');
    /* ABOVE, asserted as document order rather than by reading the JSX: the
       whole point of the change is where a reader's eye lands first. */
    expect(
      captureEyebrow.compareDocumentPosition(workspacesEyebrow) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(nav().contains(captureLink())).toBe(true);

    /* AND IT APPEARS EXACTLY ONCE. Promoting it is a rendering split, not a
       second list: a build that forgot to filter `capture` out of the list
       below would show the destination twice with two different shapes. */
    expect(screen.getAllByRole('link', { name: 'Capture & Proposals' })).toHaveLength(1);
    expect(
      within(nav()).getAllByRole('link').map((l) => l.getAttribute('aria-label') ?? l.textContent),
    ).toEqual(['Capture & Proposals', 'Record Fields', 'Runs', 'Graph']);
  });

  it('routes to ?view=capture, the destination that already exists', async () => {
    renderAt(`/record/${ID}?run=RUNAAA`);
    await screen.findByRole('link', { name: 'Record Fields' });

    const href = captureLink().getAttribute('href') ?? '';
    const query = new URLSearchParams(href.split('?')[1] ?? '');
    expect(query.get('view')).toBe('capture');
    // ...and the rest of the address is COPIED, not rebuilt — the same contract
    // the three rows below it keep.
    expect(query.get('run')).toBe('RUNAAA');
  });

  it('marks itself with aria-current="page" when it is the open workspace', async () => {
    renderAt(`/record/${ID}?view=capture`);
    await waitFor(() => expect(captureLink()).toHaveAttribute('aria-current', 'page'));
  });

  it('states the RECORD PAYLOAD’S counts, and reads no list to get them', async () => {
    const calls = stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}`]: { body: { ...captureDetail({ notes_total: 3, proposals_open: 2 }), id: ID } },
      [`GET ${BASE}/runs`]: { body: runsPage([runFixture({ id: 'RUNAAA', label: 'Run 1' })]) },
      /*
       * THE LIST ROUTES ARE STUBBED TO DISAGREE, DELIBERATELY. If this row ever
       * goes back to reading a list — a `.length`, or even the list's own honest
       * `total` — it renders "9 notes · 7 to review" and fails here. A fixture
       * where the two agree could not tell the two implementations apart, which
       * is the whole reason these bodies are wrong on purpose.
       */
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

    await screen.findByRole('link', { name: 'Record Fields' });
    await waitFor(() => expect(describedText()).toBe('3 notes · 2 to review'));

    /*
     * AND NOT ONE REQUEST WAS SPENT ON IT. This is the point of the change and
     * it is asserted rather than described: on a NON-capture workspace the
     * capture panels are not mounted, so neither list is read at all. The old
     * hook made exactly two requests here on every record load.
     */
    const listReads = calls.filter((c) => {
      const path = c.replace(/\?.*$/, '');
      return path === `GET ${BASE}/notes` || path === `GET ${BASE}/proposals`;
    });
    expect(listReads).toEqual([]);
  });

  it('says “No notes or proposals” only when every total is zero', async () => {
    // `bundleRoutes` serves a detail whose `capture_summary` is three zeroes.
    renderAt(`/record/${ID}?view=fields`);
    await screen.findByRole('link', { name: 'Record Fields' });
    await waitFor(() => expect(describedText()).toBe('No notes or proposals'));
  });

  it('states nothing while the CAPTURE workspace is the open one, and still reads no list for it', async () => {
    /*
     * THE RULE: the summary describes a destination the reader is not in.
     *
     * ── THE GATE HAD TWO REASONS AND NOW HAS ONE, WHICH IS WHY THIS TEST WAS
     *    REWRITTEN RATHER THAN DELETED ────────────────────────────────────────
     *
     * The COST reason is gone. The counts arrive on the bundle, so switching the
     * line off saves no request and switching it on spends none — and this test
     * asserts that directly below, because a gate justified by a saving that no
     * longer exists is a gate a future reader will remove for the wrong reason.
     *
     * The CONSISTENCY reason holds and is now the whole argument. On this one
     * workspace `UnmappedNotesPanel` and `IngestionProposalsPanel` are on screen
     * reading their own lists, and they update the instant a person dismisses a
     * note or rejects a proposal. The bundle's copy moves only when the bundle
     * refetches — a change-feed poll away. So a sidebar line here would restate,
     * less precisely and for a few seconds wrongly, a number the panel beside it
     * has already corrected. Absence is not a loss: the panels state their own.
     */
    const calls = stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}`]: { body: { ...captureDetail({ notes_total: 3 }), id: ID } },
      [`GET ${BASE}/runs`]: { body: runsPage([runFixture({ id: 'RUNAAA', label: 'Run 1' })]) },
      [`GET ${BASE}/notes`]: { body: notesPage([noteFixture()], { total: 3 }) },
    } as never);
    render(
      <MemoryRouter
        initialEntries={[`/record/${ID}?view=capture`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    await screen.findByRole('link', { name: 'Record Fields' });
    await waitFor(() => expect(captureLink()).toHaveAttribute('aria-current', 'page'));

    // The capture PANEL reads the notes, exactly once. The sidebar reads nothing
    // — not here, and (see the test above) not on any other workspace either.
    await waitFor(() =>
      expect(calls.filter((c) => c.replace(/\?.*$/, '') === `GET ${BASE}/notes`)).toHaveLength(1),
    );
    expect(captureLink().getAttribute('aria-describedby')).toBeNull();
    expect(captureLink().textContent).toBe('Capture & Proposals');

    /*
     * AND THE NUMBER WAS AVAILABLE THE WHOLE TIME. The bundle carried
     * `notes_total: 3`, so this is a rendering decision and not a missing read —
     * which is precisely what makes it a decision a future session may revisit
     * without any server work.
     */
    expect(describedText()).toBeNull();
  });

  it('says NOTHING AT ALL while the counts are unknown — never “0”', async () => {
    /*
     * THE DISTINCTION THIS PINS. "No notes or proposals" is a claim about the
     * record; absence is a claim about this client's knowledge. A read that
     * failed must produce the second, and a surface that printed a zero — or
     * kept the previous record's numbers — would be asserting the first.
     */
    renderAt(`/record/${ID}?view=fields`, {
      /*
       * THE "UNKNOWN" CASE MOVED WITH THE DATA. It used to be a failed
       * `GET .../notes`; the counts no longer come from there, and a failed
       * detail read takes the whole screen to its backend-down state rather than
       * to a record with an unknown count. What remains reachable, and is what
       * this now serves, is an API build that does not send the block at all.
       */
      [`GET ${BASE}`]: { body: detailWithoutCaptureSummary(ID) },
    });
    await screen.findByRole('link', { name: 'Record Fields' });

    // Give the failed read time to land and any summary to appear.
    await waitFor(() => expect(screen.queryByText('No notes or proposals')).toBeNull());
    expect(captureLink().getAttribute('aria-describedby')).toBeNull();
    expect(captureLink().textContent).toBe('Capture & Proposals');
  });

  it('discloses stored entries neither list could read, rather than understating the record', async () => {
    renderAt(`/record/${ID}?view=fields`, {
      // The SERVER sums the two kinds (`routes._capture_summary`); the client
      // renders the sum. Nothing here adds two numbers together.
      [`GET ${BASE}`]: {
        body: { ...captureDetail({ notes_total: 1, unreadable_entries: 2 }), id: ID },
      },
    });
    await screen.findByRole('link', { name: 'Record Fields' });
    await waitFor(() => expect(describedText()).toBe('1 note · 2 unreadable entries'));
  });

  /*
   * BOTH STATES, AND THE SECOND ONE IS NOT PADDING.
   *
   * The first version of this test ran only on `?view=fields`, where the row is
   * NOT the open workspace — so `aria-current` is absent whatever the code
   * says. Mutating the component to render `aria-current="step"` left it GREEN:
   * the assertion was true by construction, which is the defect this repository
   * has caught itself shipping repeatedly. `step` can only appear on the ACTIVE
   * row, so the active render is the one that can see it.
   */
  it.each([
    ['inactive', 'fields'],
    ['ACTIVE', 'capture'],
  ])('carries NO completion state while %s — no tick, no lock, no reason, no step', async (
    _name,
    view,
  ) => {
    renderAt(`/record/${ID}?view=${view}`, {
      [`GET ${BASE}`]: { body: { ...captureDetail({ notes_total: 3 }), id: ID } },
    });
    await screen.findByRole('link', { name: 'Record Fields' });
    await waitFor(() =>
      expect(captureLink().getAttribute('aria-current')).toBe(
        view === 'capture' ? 'page' : null,
      ),
    );

    const link = captureLink();
    /*
     * THE ANTI-GOALS, ONE BY ONE. Each is something the spine one region up
     * legitimately does, and none of them may ever appear here: this row is
     * always reachable, in any record state, and the record's own signals
     * cannot decide when capture is "done".
     */
    expect(link.getAttribute('aria-current')).not.toBe('step');
    expect(link.getAttribute('aria-disabled')).toBeNull();
    expect(link.className).not.toMatch(/completed|blocked|reopened|current\b/);
    // No state glyph — a tick or a lock would claim a verdict in a picture.
    expect(link.querySelector('svg')).toBeNull();
    expect(link.querySelector('.spine-disc')).toBeNull();
    // No gating sentence. The spine renders "Complete 'X' first." on a blocked
    // step; this destination is never blocked, so it never earns one.
    expect(link.textContent).not.toMatch(/first\./);
    // ...and the row is still a real link, so it is reachable by keyboard and
    // by the browser's own affordances rather than being an inert card.
    expect(link.tagName).toBe('A');
    expect(link.getAttribute('href')).toBeTruthy();
  });

  it('does not enter the workflow spine, which still derives exactly its five steps', async () => {
    renderAt(`/record/${ID}?view=capture`);
    const spine = await screen.findByRole('navigation', { name: 'Workflow pipeline' });
    const labels = within(spine)
      .getAllByRole('listitem')
      .map((li) => (li.textContent ?? '').trim());
    expect(labels).toHaveLength(5);
    expect(labels.some((l) => /Capture/.test(l))).toBe(false);
    // The capture destination lives in the OTHER landmark, not this one.
    expect(spine.contains(captureLink())).toBe(false);
  });

  it('keeps the link’s accessible NAME the destination, with the counts as its DESCRIPTION', async () => {
    renderAt(`/record/${ID}?view=fields`, {
      [`GET ${BASE}`]: { body: { ...captureDetail({ notes_total: 4 }), id: ID } },
    });
    await screen.findByRole('link', { name: 'Record Fields' });
    await waitFor(() => expect(describedText()).toBe('4 notes'));

    /*
     * WHY THIS IS PINNED. Left to its content the link's name would be
     * "Capture & Proposals 4 notes" — a name that changes whenever a colleague
     * captures a note. A reader navigating by link name would find the
     * destination renamed under them, and every `getByRole('link', { name })`
     * in this suite would be querying a moving target.
     */
    expect(captureLink().getAttribute('aria-label')).toBe('Capture & Proposals');
    expect(screen.queryByRole('link', { name: /4 notes/ })).toBeNull();
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

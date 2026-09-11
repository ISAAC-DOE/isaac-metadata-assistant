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
 * Both fixtures below deliberately serve a LIST SHORTER THAN THE TOTAL, because
 * a count read off `notes.length` or `proposals.length` would pass against a
 * fixture where the two agree. CLAUDE.md §11 records four separate surfaces
 * that shipped exactly that defect; the proposals read is bounded to one row, so
 * on this screen the two would disagree by an order of magnitude.
 *
 * ── WHAT THIS FILE DOES NOT OWN ────────────────────────────────────────────
 *
 * `record-workspaces.test.tsx` owns the four destinations as a set, the push /
 * Back contract, the query-string copying and the `aria-current="page"`
 * anti-goals over every link in the landmark. This file owns only what
 * promoting one of them added.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import {
  bundleRoutes,
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

  it('states the SERVER’S totals, not the length of what was fetched', async () => {
    renderAt(`/record/${ID}?view=fields`, {
      // One note in the page; the record holds THREE. A `.length` count reads 1.
      [`GET ${BASE}/notes`]: {
        body: notesPage([noteFixture()], {
          total: 3,
          by_state: { unreviewed: 2, mapped: 1, kept: 0, dismissed: 0 },
        }),
      },
      // NO rows in the window at all; the record holds five proposals, two of
      // them open. A `.length` count reads 0 and the row would say nothing.
      [`GET ${BASE}/proposals`]: {
        body: proposalsWindow({
          proposals: [],
          total: 5,
          returned: 0,
          by_state: { open: 2, accepted: 3, rejected: 0, superseded: 0, withdrawn: 0 },
        }),
      },
    });

    await screen.findByRole('link', { name: 'Record Fields' });
    await waitFor(() => expect(describedText()).toBe('3 notes · 2 to review'));
  });

  it('says “No notes or proposals” only when every total is zero', async () => {
    // `bundleRoutes` serves an empty notes list and an empty proposals list.
    renderAt(`/record/${ID}?view=fields`);
    await screen.findByRole('link', { name: 'Record Fields' });
    await waitFor(() => expect(describedText()).toBe('No notes or proposals'));
  });

  it('states nothing, and reads nothing, while the CAPTURE workspace is the open one', async () => {
    /*
     * THE RULE: the summary describes a destination the reader is not in. On
     * `?view=capture` the three panels are on screen stating their own counts
     * from their own reads, so a sidebar line would be a SECOND copy of a
     * number already visible — free to disagree with it for a poll interval —
     * bought with a second `GET .../notes` and a second `GET .../proposals` on
     * the busiest surface of the record. `notes-live-refresh-integration.test.tsx`
     * counts those reads at the wire and is what this gate keeps honest.
     */
    const calls = stubFetchRoutes({
      ...bundleRoutes(ID),
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

    // The capture PANEL reads the notes; the sidebar does not read them again.
    await waitFor(() =>
      expect(calls.filter((c) => c.replace(/\?.*$/, '') === `GET ${BASE}/notes`)).toHaveLength(1),
    );
    expect(captureLink().getAttribute('aria-describedby')).toBeNull();
    expect(captureLink().textContent).toBe('Capture & Proposals');
  });

  it('says NOTHING AT ALL while the counts are unknown — never “0”', async () => {
    /*
     * THE DISTINCTION THIS PINS. "No notes or proposals" is a claim about the
     * record; absence is a claim about this client's knowledge. A read that
     * failed must produce the second, and a surface that printed a zero — or
     * kept the previous record's numbers — would be asserting the first.
     */
    renderAt(`/record/${ID}?view=fields`, {
      [`GET ${BASE}/notes`]: { status: 503, body: { detail: 'down' } },
    });
    await screen.findByRole('link', { name: 'Record Fields' });

    // Give the failed read time to land and any summary to appear.
    await waitFor(() => expect(screen.queryByText('No notes or proposals')).toBeNull());
    expect(captureLink().getAttribute('aria-describedby')).toBeNull();
    expect(captureLink().textContent).toBe('Capture & Proposals');
  });

  it('discloses stored entries neither list could read, rather than understating the record', async () => {
    renderAt(`/record/${ID}?view=fields`, {
      [`GET ${BASE}/notes`]: {
        body: notesPage([noteFixture()], { total: 1, unreadable_entries: 1 }),
      },
      [`GET ${BASE}/proposals`]: {
        body: proposalsWindow({ unreadable_entries: 1 }),
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
      [`GET ${BASE}/notes`]: { body: notesPage([noteFixture()], { total: 3 }) },
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
      [`GET ${BASE}/notes`]: { body: notesPage([], { total: 4 }) },
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
 * `captureSummaryLine` is a pure function of three integers, and every branch
 * in it turns on `> 0` and `=== 1`. So 0 / 1 / 2 on each of the three axes
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
      captureSummaryLine({ notesTotal: 0, proposalsOpen: 0, unreadableEntries: 0 }),
    ).toBeTruthy();
  });

  it('produces exactly these 27 strings over 0/1/2 on all three counts — nothing else', () => {
    const produced: Record<string, string> = {};
    for (const notesTotal of [0, 1, 2]) {
      for (const proposalsOpen of [0, 1, 2]) {
        for (const unreadableEntries of [0, 1, 2]) {
          const line = captureSummaryLine({ notesTotal, proposalsOpen, unreadableEntries });
          expect(line, `${notesTotal},${proposalsOpen},${unreadableEntries} produced no line`)
            .not.toBeNull();
          produced[`${notesTotal},${proposalsOpen},${unreadableEntries}`] = line as string;
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
      captureSummaryLine({ notesTotal: 1204, proposalsOpen: 37, unreadableEntries: 0 }),
    ).toBe('1204 notes · 37 to review');
  });
});

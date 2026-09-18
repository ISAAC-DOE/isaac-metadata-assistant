import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import {
  activitySummaryFixture,
  statisticsRoutes,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';

/**
 * WORKSPACE ACTIVITY on the Statistics Overview tab — `ACT-004`, against `DEC-44`.
 *
 * `DEC-44` permits a summary of the append-only activity history in the same
 * sentence that forbids one from replacing it, so this file asserts BOTH
 * directions: that the counts reach the reader, and that the section cannot be
 * mistaken for the history — every record it names is a link into that record's
 * own Activity view, and no act is reconstructable from what it renders.
 *
 * THREE CHOICES ABOUT HOW THIS FILE ASSERTS, inherited from `statistics-page.test.tsx`
 * because a second idiom on one screen is how two suites come to disagree:
 *
 *  1. Every element is resolved by role or by its own visible label. The section
 *     is a `region` named by its heading, so a lookup is scoped without depending
 *     on section order.
 *  2. Expected figures are TRANSCRIBED LITERALS derived by hand from
 *     `activitySummaryFixture`, never recomputed from it. Recomputing would make
 *     each assertion agree with the fixture even if both were wrong.
 *  3. Where the claim is about something ABSENT — no headcount, no event content —
 *     the assertion is over the rendered text, because no behaviour can
 *     demonstrate the absence of a figure.
 */

afterEach(cleanup);

/* ---- what the fixture implies, derived by hand ------------------------- */

const EVENTS_IN_WINDOW = '9';
const RECORDS_CHANGED = '2';
const EVENTS_ALL_TIME = '12';
const FIRST_ROW_ID = '01SYNTHTESTEXP000000000000';
const FIRST_ROW_TITLE = 'Synthetic Record — Second Needs Attention';
const SECOND_ROW_ID = '01SYNTHTESTDONE00000000000';

const SECTION = 'Workspace Activity';

function renderStatistics(routes: Record<string, RouteEntry>) {
  const calls = stubFetchRoutes(routes);
  const view = render(
    <MemoryRouter
      initialEntries={[ROUTES.statistics]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
  return { ...view, calls };
}

/** The Statistics page with ONE override applied to the activity summary body. */
function renderWithSummary(over: Record<string, unknown>) {
  return renderStatistics(
    statisticsRoutes({ activity: { body: { ...activitySummaryFixture, ...over } } }),
  );
}

async function settled(): Promise<void> {
  await waitFor(() =>
    expect(document.querySelectorAll('.fetch-state[role="status"]')).toHaveLength(0),
  );
}

const section = (): HTMLElement => screen.getByRole('region', { name: SECTION });

function figureValue(label: string): string {
  const row = within(section()).getByText(label).closest('.stats-figure');
  expect(row, `no figure row labelled "${label}"`).not.toBeNull();
  return row!.querySelector('dd')?.textContent?.trim() ?? '';
}

describe('Workspace Activity summarizes the history and never replaces it', () => {
  it('renders the three headline figures from the server, each at its own label', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    expect(figureValue('Changes in the Last 7 Days')).toBe(EVENTS_IN_WINDOW);
    expect(figureValue('Records Changed')).toBe(RECORDS_CHANGED);
    expect(figureValue('Recorded Acts, All Time')).toBe(EVENTS_ALL_TIME);
  });

  it('labels the window from the PAYLOAD, so the figure and its label cannot disagree', async () => {
    /*
     * `ACT-004`'s sixth rule. A literal `7` anywhere in the component would be a
     * second source of the window, free to drift from the one the count was
     * computed over. The server owns the window; this proves the label follows it.
     */
    renderWithSummary({
      window: {
        days: 30,
        since_utc: '2099-06-08T00:00:00Z',
        computed_at_utc: '2099-07-08T00:00:00Z',
      },
    });
    await settled();
    expect(within(section()).getByText('Changes in the Last 30 Days')).toBeTruthy();
    expect(within(section()).queryByText('Changes in the Last 7 Days')).toBeNull();
  });

  it('takes Records Changed from the server total, NEVER from the rows it received', async () => {
    /*
     * `CLAUDE.md` §11's most-repeated measured defect: a count taken from a
     * bounded list understates the truth the moment the list is shorter than the
     * whole. Here the server says NINE records changed and sends TWO rows.
     */
    renderWithSummary({
      changed_records: { ...activitySummaryFixture.changed_records, total: 9, returned: 2 },
    });
    await settled();
    expect(figureValue('Records Changed')).toBe('9');
    // And the list says what it is showing, rather than letting 2 read as 9.
    expect(
      within(section()).getByText(/The 2 busiest of the 9 records that changed/),
    ).toBeTruthy();
  });

  it('makes every record it names reachable, at its own Activity view', async () => {
    /*
     * THE DEAD END THIS REFUSES is the one an Impeccable pass over the Activity
     * panel already caught once (`d308b827` — "the count named 150 facts a reader
     * could not reach"). A count that advertises content with no control to reach
     * it is not a finished surface, and the destination is the record's OWN
     * history, which is the source of truth this section only counts.
     */
    renderStatistics(statisticsRoutes());
    await settled();
    const first = within(section()).getByRole('link', { name: FIRST_ROW_TITLE });
    expect(first.getAttribute('href')).toBe(ROUTES.recordView(FIRST_ROW_ID, 'activity'));
    const links = within(section())
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'));
    expect(links).toContain(ROUTES.recordView(SECOND_ROW_ID, 'activity'));
  });

  it('states the unattributed actor in words and renders NO number of people', async () => {
    /*
     * `ACT-005` is blocked on `EXT-01`, so a headcount would be structurally `0` —
     * and `0` there is a claim about the PEOPLE where the true statement is about
     * the DEPLOYMENT. The sentence is `LABELS.activityActorUnattributed`, the SAME
     * string the record's own Activity panel shows, so there is one claim and not
     * a second copy of it.
     */
    renderStatistics(statisticsRoutes());
    await settled();
    const text = section().textContent ?? '';
    expect(text).toContain(LABELS.activityActorUnattributed);
    expect(text).not.toMatch(/collaborator/i);
    // Nor a bare zero dressed as a figure about anybody.
    expect(within(section()).queryByText('Distinct Collaborators')).toBeNull();
    /*
     * "person" is deliberately NOT banned, and the first draft of this test banned
     * it and failed — correctly. The honest sentence this section renders is
     * *"Entries are not attributed to a person"*, so a ban on the word would have
     * forbidden the very disclosure the rule requires. What must be absent is a
     * FIGURE about people, which is what the two assertions above pin.
     */
    expect(text).toMatch(/not attributed to a person/);
  });

  it('carries no event content, so it cannot stand in for the history', async () => {
    /*
     * `DEC-44`, asserted over what is ABSENT. The route's own shape refuses to
     * serve an event id or a `before`/`after` pair; this pins that the section
     * renders no value, no field path and no act — only counts and addresses.
     */
    renderStatistics(statisticsRoutes());
    await settled();
    const text = section().textContent ?? '';
    expect(text).not.toMatch(/was not set|was empty|changed to/);
    expect(text).not.toMatch(/\bseq\b/);
    // And no bare snake_case token survives the humanizer.
    expect(text).not.toMatch(/\b[a-z]+_[a-z]+\b/);
  });

  it('humanizes the server vocabularies, including the initialism', async () => {
    /*
     * `mcp` must read `MCP`, not `Mcp`. CASING ONLY — every output word is an
     * input word, so no name is invented. Measured on this surface before the
     * initialism map existed: the channel row read "Mcp".
     */
    renderStatistics(statisticsRoutes());
    await settled();
    const text = section().textContent ?? '';
    expect(text).toContain('Field Answered');
    expect(text).toContain('MCP');
    expect(text).not.toContain('Mcp');
  });

  it('agrees on singular and plural rather than saying "1 changes"', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    /*
     * READ OFF THE ELEMENT, not off the section's concatenated `textContent`. The
     * unit noun is an `sr-only` sibling of the count, so the two run together as
     * `1change` in a text dump and a regex over the dump would pass vacuously —
     * which is how the first draft of this assertion behaved.
     */
    const nouns = [...section().querySelectorAll('.stats-mini-item')].map((item) => ({
      count: item.querySelector('.stats-mini-n')?.textContent?.trim(),
      noun: item.querySelector('.sr-only')?.textContent?.trim(),
    }));
    expect(nouns.length).toBeGreaterThan(0);
    for (const { count, noun } of nouns) {
      expect(noun).toBe(count === '1' ? 'change' : 'changes');
    }
    // And the fixture really does exercise BOTH arms, so this is not vacuous.
    expect(nouns.some((n) => n.count === '1')).toBe(true);
    expect(nouns.some((n) => n.count !== '1')).toBe(true);
  });

  it('discloses the two kinds of unreadable separately, and neither as the other', async () => {
    /*
     * A stored entry the model could not read AT ALL, and a readable event whose
     * TIMESTAMP could not be parsed, are different facts with different
     * consequences: the second is inside the all-time total and in neither window
     * bucket. Folding them would make one figure wrong by an undisclosed amount.
     */
    renderStatistics(statisticsRoutes());
    await settled();
    const text = section().textContent ?? '';
    expect(text).toMatch(/2 stored entries could not be read/);
    expect(text).toMatch(/1 recorded acts carry a time this build could not read/);
  });

  it('says so when the summary covered fewer records than the workspace holds', async () => {
    renderWithSummary({
      scope: {
        ...activitySummaryFixture.scope,
        experiments_in_scope: 900,
        experiments_summarized: 500,
        truncated: true,
      },
    });
    await settled();
    expect(
      within(section()).getByText(
        /These figures cover the 500 most recently created of the 900 records in this workspace/,
      ),
    ).toBeTruthy();
  });

  it('states its coverage even when nothing was truncated', async () => {
    /* The scope line is not conditional on truncation: a figure whose denominator
       is stated only sometimes is a figure a reader has to remember to ask about. */
    renderStatistics(statisticsRoutes());
    await settled();
    expect(
      within(section()).getByText(/These figures cover all 3 records in this workspace/),
    ).toBeTruthy();
  });

  it('answers an empty workspace with a sentence, not a grid of zeros', async () => {
    /*
     * "No records" and "records that have never been touched" are DIFFERENT
     * answers, and rendering zeros for the first states a fact about activity when
     * the fact is about records.
     */
    renderWithSummary({
      scope: {
        ...activitySummaryFixture.scope,
        experiments_in_scope: 0,
        experiments_summarized: 0,
      },
    });
    await settled();
    expect(
      within(section()).getByText(/This workspace holds no records yet/),
    ).toBeTruthy();
    expect(within(section()).queryByText('Changes in the Last 7 Days')).toBeNull();
  });

  it('reports a failed read as its own unavailability, and never blanks the page', async () => {
    renderStatistics(statisticsRoutes({ activity: { status: 500, body: {} } }));
    await settled();
    expect(
      within(section()).getByText(
        /The workspace's recorded activity could not be read, so no counts are shown/,
      ),
    ).toBeTruthy();
    expect(within(section()).getByRole('button', { name: 'Retry' })).toBeTruthy();
    // The rest of the Overview tab is untouched — one dead read degrades one
    // section, which is the page's partial-failure design.
    expect(screen.getByRole('region', { name: 'Recent Work' })).toBeTruthy();
    expect(screen.getByRole('region', { name: 'Workspace at a Glance' })).toBeTruthy();
  });

  it('lives on the Overview tab and NOT on My Stats', async () => {
    /*
     * `MyStats.tsx`'s first of six traps is "no workspace total presented as
     * personal", and every figure here is a workspace total. Asserted as a
     * placement, not as a comment: the section is a named region, so its absence
     * from that panel is checkable.
     */
    renderStatistics(statisticsRoutes());
    await settled();
    expect(section()).toBeTruthy();
    screen.getByRole('tab', { name: 'My Stats' }).click();
    await waitFor(() => expect(screen.queryByRole('region', { name: SECTION })).toBeNull());
  });
});

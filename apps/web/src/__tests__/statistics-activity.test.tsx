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
    // And the caption says what it is showing, rather than letting 2 read as 9 —
    // naming the window, because the row counts are window-scoped too.
    expect(
      within(section()).getByText(
        /The 2 busiest of the 9 records that changed in the last 7 days/,
      ),
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

  it('says no record changed, naming the window, when none did', async () => {
    renderWithSummary({
      changed_records: { ...activitySummaryFixture.changed_records, rows: [], total: 0, returned: 0 },
    });
    await settled();
    expect(
      within(section()).getByText('No record changed in the last 7 days.'),
    ).toBeTruthy();
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

  it('discloses the two kinds of unreadable separately, and neither as the other — AND NOW ASSERTS THE OPPOSITE OF WHAT IT FIRST PINNED about the singular', async () => {
    /*
     * ── THE SUBJECT, WHICH IS UNCHANGED ──────────────────────────────────────
     *
     * A stored entry the model could not read AT ALL, and a readable event whose
     * TIMESTAMP could not be parsed, are different facts with different
     * consequences: the second is inside the all-time total and in neither window
     * bucket. Folding them would make one figure wrong by an undisclosed amount.
     *
     * ── WHAT WAS INVERTED, AND WHY IT IS RECORDED HERE ───────────────────────
     *
     * The second assertion used to read
     * `toMatch(/1 recorded acts carry a time this build could not read/)` — and the
     * fixture ships `events_with_unreadable_timestamp: 1`, so this suite REQUIRED
     * the ungrammatical string. It pinned a defect the same slice's own `plural()`
     * docstring had already named as a defect ("`1 changes` is the kind of small
     * wrongness that makes a surface read as generated rather than written"), which
     * is the worst version of this: a guard holding a surface to a standard the
     * author had written down and not applied.
     *
     * It is INVERTED rather than deleted — this repository's established remedy —
     * so the subject survives and the assertion is now the opposite one. The
     * singular sentence moves the verb, the pronoun AND the possessive, so all
     * three are asserted rather than just the noun.
     */
    renderStatistics(statisticsRoutes());
    await settled();
    const text = section().textContent ?? '';
    expect(text).toMatch(/2 stored entries could not be read/);
    // WAS REQUIRED, NOW BANNED.
    expect(text).not.toMatch(/1 recorded acts carry/);
    expect(text).toMatch(/1 recorded act carries a time this build could not read/);
    expect(text).toMatch(/It is in the all-time total and in neither window figure/);
  });

  it('agrees on number in all four disclosure sentences, at one and at many', async () => {
    /*
     * The four sentences an independent review found un-pluralized. Each is
     * exercised at BOTH arms, because a sentence that is only ever rendered at one
     * count is a sentence whose agreement nothing has checked — which is how all
     * four shipped.
     *
     * `attributed_events` is structurally 0 in this build (`ACT-005` is blocked on
     * `EXT-01`), so its sentence is unreachable in the product and is exercised here
     * anyway: the day that seam is wired is the day it renders.
     */
    renderWithSummary({
      totals: {
        events_in_window: 9,
        events_all_time: 12,
        events_with_unreadable_timestamp: 1,
        unreadable_entries: 1,
      },
      attribution: { ...activitySummaryFixture.attribution, attributed_events: 1 },
    });
    await settled();
    const singular = section().textContent ?? '';
    expect(singular).toMatch(/1 stored entry could not be read and is counted in none/);
    expect(singular).toMatch(/It is kept in its record untouched/);
    expect(singular).toMatch(/1 recorded act carries a time/);
    expect(singular).toMatch(/1 of these changes does carry an actor/);
    expect(singular).not.toMatch(/1 (stored entries|recorded acts|of these changes do carry)/);

    cleanup();
    renderWithSummary({
      totals: {
        events_in_window: 9,
        events_all_time: 12,
        events_with_unreadable_timestamp: 3,
        unreadable_entries: 2,
      },
      attribution: { ...activitySummaryFixture.attribution, attributed_events: 4 },
    });
    await settled();
    const many = section().textContent ?? '';
    expect(many).toMatch(/2 stored entries could not be read and are counted in none/);
    expect(many).toMatch(/They are kept in their records untouched/);
    expect(many).toMatch(/3 recorded acts carry a time/);
    expect(many).toMatch(/4 of these changes do carry an actor/);
  });

  it('names the window on the BREAKDOWNS too, not only on the first figure', async () => {
    /*
     * ── THE DEFECT, REPRODUCED BEFORE IT WAS FIXED ───────────────────────────
     *
     * `by_action` and `by_channel` are incremented only for events INSIDE the
     * window, so both breakdowns are window-scoped — and they render immediately
     * beneath `Recorded Acts, All Time`. With 5,000 acts on the record and 3 this
     * week, an unlabelled breakdown summing to 3 reads as a description of the
     * 5,000. Both numbers are true; the sentence they assemble is false.
     *
     * The asymmetry was the sharp part: the EMPTY branch already named the window
     * ("No record changed in the last 7 days"), so the screen named it precisely
     * when the answer was zero and omitted it when there was data.
     */
    renderWithSummary({
      totals: {
        events_in_window: 3,
        events_all_time: 5000,
        events_with_unreadable_timestamp: 0,
        unreadable_entries: 0,
      },
      ranked_actions: [{ name: 'field_answered', count: 3 }],
      actions_with_events: 1,
      ranked_channels: [{ name: 'web', count: 3 }],
      channels_with_events: 1,
    });
    await settled();
    expect(figureValue('Recorded Acts, All Time')).toBe('5000');
    // Both breakdown labels name the window EXPLICITLY, not by reference to each
    // other: a truth claim that depends on two elements staying adjacent is one
    // refactor away from being false.
    expect(within(section()).getByText('What Changed in the Last 7 Days')).toBeTruthy();
    expect(
      within(section()).getByText('Through Which Surface, in the Last 7 Days'),
    ).toBeTruthy();
    // And the label follows the payload's window, not a literal.
    cleanup();
    renderWithSummary({
      window: {
        days: 30,
        since_utc: '2099-06-08T00:00:00Z',
        computed_at_utc: '2099-07-08T00:00:00Z',
      },
    });
    await settled();
    expect(within(section()).getByText('What Changed in the Last 30 Days')).toBeTruthy();
    expect(
      within(section()).getByText('Through Which Surface, in the Last 30 Days'),
    ).toBeTruthy();
  });

  it('chooses the empty-list sentence from the server TOTAL, never from the rows it got', async () => {
    /*
     * At `record_rows = 0` the section used to render three contradictory statements
     * at once — `Records Changed 7`, *No record changed in the last 7 days*, and
     * *The 0 busiest of the 7 records that changed* — because the branch was chosen
     * by `rows.length`. Latent (the server's `RECORD_ROWS` is 5 and the route
     * exposes no parameter), but it was guarded by a CONSTANT rather than by the
     * predicate, and the honest predicate is `total`.
     */
    renderWithSummary({
      changed_records: { rows: [], total: 7, returned: 0, limit: 0 },
    });
    await settled();
    const text = section().textContent ?? '';
    expect(figureValue('Records Changed')).toBe('7');
    // NOT "no record changed" — seven did.
    expect(text).not.toMatch(/No record changed/);
    expect(text).not.toMatch(/The 0 busiest/);
    expect(text).toMatch(/7 records changed in the last 7 days, and none are listed here/);
  });

  it('discloses a surface it could not show, instead of dropping it silently', async () => {
    /*
     * The channel breakdown had no "and N more" line, and was safe only because
     * `ACTIVITY_CHANNELS` has exactly four members and the display cap is four — the
     * precise defect the actions row already had a guard for. `DEC-44` fixes the
     * vocabulary at four so this is expected never to render in the product; it is
     * asserted here so the section does not depend on two unrelated constants
     * agreeing.
     */
    renderWithSummary({
      ranked_channels: [
        { name: 'web', count: 7 },
        { name: 'mcp', count: 2 },
        { name: 'historical_import', count: 1 },
        { name: 'system', count: 1 },
      ],
      channels_with_events: 5,
    });
    await settled();
    expect(within(section()).getByText('1 further surface is not listed.')).toBeTruthy();
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

/**
 * The Overview dashboard's two activity widgets (2026-11-02): **Activity**, a
 * trend of changes per day from the summary's `by_day` buckets, and **Kinds of
 * Change**, the ranked actions as bars.
 *
 * What they must keep from the widget they replaced (`ACT-004`): every figure is
 * the SERVER's — the window label from `window.days`, Records Changed from
 * `changed_records.total`, never from a list length — the summary never stands in
 * for the history (no event content reaches the page), and no number of people is
 * ever stated, because no event in this build carries an actor.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { ROUTES } from '../lib/routes';
import { activityTrend } from '../screens/statistics/OverviewWidgets';
import type { ApiActivitySummary } from '../lib/types';
import {
  activitySummaryFixture,
  statisticsRoutes,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';

afterEach(cleanup);

/* ---- what the fixture implies, derived by hand ------------------------- */

const EVENTS_IN_WINDOW = '9';
const RECORDS_CHANGED = '2';

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

const activity = (): HTMLElement => screen.getByRole('region', { name: 'Activity' });
const kinds = (): HTMLElement => screen.getByRole('region', { name: 'Kinds of Change' });

function headlineValue(root: HTMLElement, label: string): string {
  const card = within(root).getByText(label).closest('dl.stat-card');
  expect(card, `no headline labelled "${label}"`).not.toBeNull();
  return card!.querySelector('.stat-card-value')?.textContent?.trim() ?? '';
}

/** The chart's data table, as `[label, value]` rows. */
function tableRows(root: HTMLElement): [string, string][] {
  return [...root.querySelectorAll('.stats-chart-table tbody tr')].map((tr) => [
    tr.querySelector('th')?.textContent?.trim() ?? '',
    tr.querySelector('td')?.textContent?.trim() ?? '',
  ]);
}

describe('Activity — the trend of recorded changes', () => {
  it('states the window count and Records Changed from the server', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    expect(headlineValue(activity(), 'Changes, Last 7 Days')).toBe(EVENTS_IN_WINDOW);
    expect(headlineValue(activity(), 'Records Changed')).toBe(RECORDS_CHANGED);
  });

  it('labels the window from the PAYLOAD, so the figure and its label cannot disagree', async () => {
    renderWithSummary({
      window: { days: 30, since_utc: '2099-06-08T00:00:00Z', computed_at_utc: '2099-07-08T00:00:00Z' },
    });
    await settled();
    expect(within(activity()).getByText('Changes, Last 30 Days')).toBeTruthy();
    expect(within(activity()).queryByText('Changes, Last 7 Days')).toBeNull();
  });

  it('takes Records Changed from the server total, NEVER from the rows it received', async () => {
    renderWithSummary({
      changed_records: { ...activitySummaryFixture.changed_records, total: 7, returned: 2 },
    });
    await settled();
    expect(headlineValue(activity(), 'Records Changed')).toBe('7');
  });

  it('draws one point per served day, oldest first, and the points sum to the window count', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    const rows = tableRows(activity());
    expect(rows).toEqual([
      ['Jul 1', '0'],
      ['Jul 2', '1'],
      ['Jul 3', '0'],
      ['Jul 4', '2'],
      ['Jul 5', '3'],
      ['Jul 6', '0'],
      ['Jul 7', '3'],
      ['Jul 8', '0'],
    ]);
    expect(rows.reduce((sum, [, v]) => sum + Number(v), 0)).toBe(Number(EVENTS_IN_WINDOW));
    expect(activity().querySelector('svg.stats-chart-line polyline')).not.toBeNull();
    // The axis names the first and last day; the full set is in the table.
    expect(activity().querySelector('.stats-trend-axis')?.textContent).toContain('Jul 1');
    expect(activity().querySelector('.stats-trend-axis')?.textContent).toContain('Jul 8');
  });

  it('draws no chart, and says so, when the server sends no per-day breakdown', async () => {
    const { by_day: _omit, ...older } = activitySummaryFixture;
    renderStatistics(statisticsRoutes({ activity: { body: older } }));
    await settled();
    expect(within(activity()).getByText('No per-day breakdown was returned.')).toBeTruthy();
    expect(activity().querySelector('.stats-chart')).toBeNull();
    // The headline still stands: it does not depend on the buckets.
    expect(headlineValue(activity(), 'Changes, Last 7 Days')).toBe(EVENTS_IN_WINDOW);
  });

  it('states the unattributed actor in words and renders NO number of people', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    expect(within(activity()).getByText(/Entries are not attributed to a person\./)).toBeTruthy();
    expect(activity().textContent ?? '').not.toMatch(/\b\d+\s+(people|persons|users|collaborators|contributors)\b/i);
  });

  it('carries no event content, so it cannot stand in for the history', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    const text = activity().textContent ?? '';
    for (const row of activitySummaryFixture.changed_records.rows) {
      expect(text).not.toContain(row.title);
      expect(text).not.toContain(row.experiment_id);
    }
  });

  it('discloses entries it could not date rather than charting them', async () => {
    renderWithSummary({
      totals: { ...activitySummaryFixture.totals, unreadable_entries: 2, events_with_unreadable_timestamp: 1 },
    });
    await settled();
    expect(within(activity()).getByText(/3 stored entries could not be dated and are not charted\./)).toBeTruthy();
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
    expect(within(activity()).getByText(/Covers the 500 most recently created of 900 records\./)).toBeTruthy();
  });

  it('reports a failed read as its own unavailability, and never blanks the page', async () => {
    renderStatistics(statisticsRoutes({ activity: { status: 500, body: {} } }));
    await settled();
    expect(within(activity()).getByText('The activity could not be read.')).toBeTruthy();
    expect(within(activity()).getByRole('button', { name: 'Retry' })).toBeTruthy();
    expect(within(kinds()).getByText('The activity could not be read.')).toBeTruthy();
    // The record-derived widgets read a different source and are untouched.
    expect(headlineValue(screen.getByRole('region', { name: 'Records' }), 'Total Records')).not.toBe('');
  });
});

describe('Activity — the range control', () => {
  it('reads the default span with NO parameter, and offers 7 · 30 · 365 days as a radiogroup', async () => {
    const { calls } = renderStatistics(statisticsRoutes());
    await settled();
    expect(calls).toContain('GET /api/activity/summary');
    expect(calls.some((c) => c.includes('window_days'))).toBe(false);

    const group = within(activity()).getByRole('radiogroup', { name: 'Time Range' });
    const radios = within(group).getAllByRole('radio');
    expect(radios.map((r) => r.textContent)).toEqual(['7 Days', '30 Days', '365 Days']);
    expect(radios.map((r) => r.getAttribute('aria-checked'))).toEqual(['true', 'false', 'false']);
    expect(radios.map((r) => r.tabIndex)).toEqual([0, -1, -1]);
  });

  it('re-reads with window_days and labels both widgets from the PAYLOAD', async () => {
    const thirty = {
      ...activitySummaryFixture,
      window: { ...activitySummaryFixture.window, days: 30 },
      totals: { ...activitySummaryFixture.totals, events_in_window: 11 },
    };
    const { calls } = renderStatistics({
      ...statisticsRoutes(),
      'GET /api/activity/summary?window_days=30': { body: thirty },
    });
    await settled();

    fireEvent.click(within(activity()).getByRole('radio', { name: '30 Days' }));
    await waitFor(() => expect(within(activity()).getByText('Changes, Last 30 Days')).toBeTruthy());
    expect(calls).toContain('GET /api/activity/summary?window_days=30');
    expect(headlineValue(activity(), 'Changes, Last 30 Days')).toBe('11');
    expect(kinds().querySelector('figcaption')?.textContent).toBe('Changes by kind, last 30 days');
  });

  it('labels from the response even when the server answers for a DIFFERENT span', async () => {
    renderStatistics({
      ...statisticsRoutes(),
      'GET /api/activity/summary?window_days=30': { body: activitySummaryFixture },
    });
    await settled();
    fireEvent.click(within(activity()).getByRole('radio', { name: '30 Days' }));
    await waitFor(() =>
      expect(within(activity()).getByRole('radio', { name: '30 Days' })).toHaveAttribute(
        'aria-checked',
        'true',
      ),
    );
    await settled();
    expect(headlineValue(activity(), 'Changes, Last 7 Days')).toBe(EVENTS_IN_WINDOW);
    expect(within(activity()).queryByText('Changes, Last 30 Days')).toBeNull();
  });

  it('moves with the arrow keys, roving the tab stop', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    const seven = within(activity()).getByRole('radio', { name: '7 Days' });
    seven.focus();
    fireEvent.keyDown(seven, { key: 'ArrowRight' });
    const thirty = within(activity()).getByRole('radio', { name: '30 Days' });
    expect(thirty).toHaveAttribute('aria-checked', 'true');
    expect(thirty).toHaveFocus();
  });
});

describe('Kinds of Change', () => {
  it('ranks the server’s kinds as bars, humanized, in the server’s order', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    expect(tableRows(kinds())).toEqual([
      ['Field Answered', '5'],
      ['Run Added', '2'],
      ['Note Captured', '1'],
      ['Proposal Reviewed', '1'],
    ]);
  });

  it('names how many further kinds it did not draw, from the server’s own count', async () => {
    const ranked = Array.from({ length: 8 }, (_, i) => ({ name: `kind_${i}`, count: 8 - i }));
    renderWithSummary({ ranked_actions: ranked, actions_with_events: 9 });
    await settled();
    expect(tableRows(kinds())).toHaveLength(6);
    expect(within(kinds()).getByText('3 more kinds.')).toBeTruthy();
  });

  it('says plainly when nothing changed in the window, and draws no axis', async () => {
    renderWithSummary({ ranked_actions: [], actions_with_events: 0 });
    await settled();
    expect(within(kinds()).getByText('No changes in the last 7 days.')).toBeTruthy();
    expect(kinds().querySelector('.stats-chart')).toBeNull();
  });
});

describe('activityTrend — bucketing the served days', () => {
  function summaryWithDays(n: number): ApiActivitySummary {
    const start = Date.UTC(2099, 0, 1);
    const by_day = Array.from({ length: n }, (_, i) => ({
      date: new Date(start + i * 86_400_000).toISOString().slice(0, 10),
      count: 1,
    }));
    return { ...(activitySummaryFixture as unknown as ApiActivitySummary), by_day };
  }

  it('keeps one point per day up to a month', () => {
    const trend = activityTrend(summaryWithDays(31));
    expect(trend?.period).toBe('day');
    expect(trend?.rows).toHaveLength(31);
  });

  it('sums whole weeks back from the last day beyond a month, losing no change', () => {
    const trend = activityTrend(summaryWithDays(366));
    expect(trend?.period).toBe('week');
    expect(trend?.rows).toHaveLength(53);
    expect(trend?.rows.reduce((sum, r) => sum + r.value, 0)).toBe(366);
    // The latest point is a whole week; only the oldest may be partial.
    expect(trend?.rows[trend.rows.length - 1].value).toBe(7);
    expect(trend?.rows[0].value).toBe(366 - 52 * 7);
  });

  it('returns nothing to draw when the server sent no buckets', () => {
    expect(activityTrend({ ...summaryWithDays(1), by_day: [] })).toBeNull();
    expect(activityTrend({ ...summaryWithDays(1), by_day: undefined })).toBeNull();
  });
});

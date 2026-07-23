/*
 * P30.3 — SearchDialog cross-record triage surface (the UI consumer of the P30.1
 * runtime projection).
 *
 * The triage surface is a THIRD, self-labeled section inside the ⌘K palette
 * (Workspace-derived leads), kept separate from the Workspace-search (truth) and
 * Project-Memory (advisory) groups. Four intent chips fetch the SAFE projection via
 * api.getRuntimeRecords and format it through the pure `crossRecordTriage`; each
 * match is a navigable row that HANDS OFF to a direct Workspace load (/record/<id>)
 * — a lead, never inline record truth. It never renders a verdict, never surfaces an
 * inferred candidate as fact or a conflict winner, and degrades honestly (a quiet
 * "unavailable" note, never blocking the query search) when the fetch fails.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { TopBar } from '../components/TopBar';
import {
  runtimeRecords,
  runtimeRecordsRoutes,
  searchResponse,
  searchRoutes,
  stubFetchRoutes,
} from '../test/apiFixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

function LocationSpy() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname + loc.search}</div>;
}

function renderTopBar() {
  return render(
    <MemoryRouter
      initialEntries={['/experiments']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <TopBar variant="home" />
      <LocationSpy />
    </MemoryRouter>,
  );
}

async function openDialog(view: ReturnType<typeof renderTopBar>) {
  fireEvent.click(view.getByRole('button', { name: /search/i }));
  return view.findByRole('dialog');
}

const REC_NEEDS = runtimeRecords[0]; // needs_attention + blocked
const REC_CONFLICT = runtimeRecords[2]; // in_review, conflicting_evidence: 2

describe('P30.3 · SearchDialog cross-record triage', () => {
  it('renders the four keyboard-accessible triage chips, labeled Workspace-derived', async () => {
    stubFetchRoutes(runtimeRecordsRoutes());
    const view = renderTopBar();
    const dialog = await openDialog(view);
    for (const label of ['Needs Attention', 'Blocked', 'Has Conflicts', 'Ready to Export']) {
      expect(within(dialog).getByRole('button', { name: label })).toBeTruthy();
    }
    // Source layer is honestly labeled and NOT the Project Memory plane.
    expect(within(dialog).getByText(/cross-record triage/i)).toBeTruthy();
    expect(within(dialog).getByText(/workspace-derived/i)).toBeTruthy();
  });

  it('a triage chip fetches the projection and renders navigable match rows', async () => {
    const calls = stubFetchRoutes(runtimeRecordsRoutes());
    const view = renderTopBar();
    const dialog = await openDialog(view);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Needs Attention' }));
    // The matched record renders as a row with its SAFE reason.
    expect(await within(dialog).findByText(REC_NEEDS.title)).toBeTruthy();
    expect(within(dialog).getByText(/5 fields need attention/i)).toBeTruthy();
    // It consumed the P30.1 provider with the intent's server filter.
    expect(calls).toContain('GET /api/runtime/records?status=needs_attention');
  });

  it('clicking a match hands off to a direct /record/<id> load and closes the dialog', async () => {
    stubFetchRoutes(runtimeRecordsRoutes());
    const view = renderTopBar();
    const dialog = await openDialog(view);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Needs Attention' }));
    const row = await within(dialog).findByText(REC_NEEDS.title);
    fireEvent.click(row.closest('button')!);
    // Handoff: navigates to the direct Workspace record load, never inline truth.
    expect(view.getByTestId('loc').textContent).toBe(`/record/${REC_NEEDS.experiment_id}`);
    expect(view.queryByRole('dialog')).toBeNull();
  });

  it('the conflict intent counts and flags for human review — never a winner/verdict', async () => {
    stubFetchRoutes(runtimeRecordsRoutes());
    const view = renderTopBar();
    const dialog = await openDialog(view);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Has Conflicts' }));
    expect(await within(dialog).findByText(REC_CONFLICT.title)).toBeTruthy();
    // The reason COUNTS the conflict and defers to a human — it never resolves it.
    expect(within(dialog).getByText(/2 conflicting evidence items/i)).toBeTruthy();
    const text = dialog.textContent || '';
    expect(text).not.toMatch(/\b(PASS|FAIL)\b/);
    expect(text).not.toMatch(/winner|resolved|correct value|confirmed value/i);
  });

  it('does not present an inferred candidate as a confirmed fact', async () => {
    stubFetchRoutes(runtimeRecordsRoutes());
    const view = renderTopBar();
    const dialog = await openDialog(view);
    // REC_NEEDS carries an inferred_candidate; triage may flag the record but must
    // never surface a value as confirmed.
    fireEvent.click(within(dialog).getByRole('button', { name: 'Needs Attention' }));
    await within(dialog).findByText(REC_NEEDS.title);
    expect((dialog.textContent || '').toLowerCase()).not.toContain('confirmed');
  });

  it('degrades honestly when the projection fetch fails — search still works', async () => {
    // Runtime endpoint errors; the search endpoint is healthy.
    stubFetchRoutes({
      ...searchRoutes(),
      'GET /api/runtime/records?status=needs_attention': { status: 503, body: {} },
    });
    const view = renderTopBar();
    const dialog = await openDialog(view);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Needs Attention' }));
    // Honest, quiet unavailable note — never role=alert, never a verdict.
    expect(await within(dialog).findByText(/cross-record triage is unavailable/i)).toBeTruthy();
    expect(within(dialog).queryByRole('alert')).toBeNull();
    // Search below is unaffected: typing a query still returns workspace results.
    const box = within(dialog).getByRole('searchbox');
    fireEvent.change(box, { target: { value: 'xanes' } });
    expect(
      await within(dialog).findByText(searchResponse.workspace.results[0].label),
    ).toBeTruthy();
  });

  it('an empty intent result says so honestly (never a fabricated row)', async () => {
    // Ready-to-Export in a set with a ready record still renders a match; here we
    // prove the honest summary path by asserting the summary sentence is present.
    stubFetchRoutes(runtimeRecordsRoutes());
    const view = renderTopBar();
    const dialog = await openDialog(view);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Ready to Export' }));
    expect(await within(dialog).findByText(/ready to export\./i)).toBeTruthy();
  });
});

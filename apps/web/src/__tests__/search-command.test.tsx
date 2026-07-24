/*
 * P26.5 — SearchDialog (⌘K command palette) behavior + honesty contract.
 *
 * The dialog is a self-contained TopBar affordance: a visible "Search ⌘K" trigger
 * plus a focus-trapped role="dialog" that queries GET /api/search (via api.search)
 * and renders TWO clearly separated, self-labeled groups — Workspace (truth) and
 * Project Memory (advisory leads). It never fabricates a row, never renders a
 * verdict, and honestly reports a degraded memory plane while workspace results
 * still show. Navigation deep-links via each result's server-supplied navigate_to
 * and closes the dialog.
 *
 * These tests are the frozen contract for the feature; the two legacy "no-search"
 * files are rewritten in the same (P26.5+P26.6) commit to assert search is now
 * PRESENT and functional while keeping decorative/fake search forbidden.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { TopBar } from '../components/TopBar';
import {
  searchResponse,
  searchResponseMemoryDown,
  searchRoutes,
  stubFetchRoutes,
  stubFetchDown,
} from '../test/apiFixtures';

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Shows the live router location so navigation can be asserted from a TopBar-only render. */
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

const WS = searchResponse.workspace.results[0];
const MEM = searchResponse.memory.results[0];

async function openAndType(view: ReturnType<typeof renderTopBar>, query = 'xanes') {
  // Open via the visible trigger, then type into the searchbox.
  const trigger = view.getByRole('button', { name: /search/i });
  fireEvent.click(trigger);
  const dialog = await view.findByRole('dialog');
  const box = within(dialog).getByRole('searchbox');
  fireEvent.change(box, { target: { value: query } });
  return { dialog, box, trigger };
}

describe('P26.5 · SearchDialog — visible trigger + ⌘K', () => {
  it('renders a visible "Search" trigger with a ⌘K hint in the TopBar', () => {
    const view = renderTopBar();
    const trigger = view.getByRole('button', { name: /search/i });
    expect(trigger).toBeTruthy();
    expect(view.getByText(/⌘K/)).toBeTruthy();
  });

  it('⌘K (metaKey) opens the dialog', async () => {
    const view = renderTopBar();
    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    expect(await view.findByRole('dialog')).toBeTruthy();
  });

  it('Ctrl-K opens the dialog', async () => {
    const view = renderTopBar();
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    expect(await view.findByRole('dialog')).toBeTruthy();
  });

  it('the dialog is an accessible, labeled, modal searchbox', async () => {
    const view = renderTopBar();
    fireEvent.click(view.getByRole('button', { name: /search/i }));
    const dialog = await view.findByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const labelledby = dialog.getAttribute('aria-labelledby');
    expect(labelledby).toBeTruthy();
    expect(document.getElementById(labelledby!)).toBeTruthy();
    expect(within(dialog).getByRole('searchbox')).toBeTruthy();
  });

  it('Escape closes the dialog and returns focus to the trigger', async () => {
    const view = renderTopBar();
    const trigger = view.getByRole('button', { name: /search/i });
    trigger.focus();
    fireEvent.click(trigger);
    await view.findByRole('dialog');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(view.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('traps Tab within the dialog', async () => {
    const view = renderTopBar();
    const { dialog } = await openAndType(view);
    const box = within(dialog).getByRole('searchbox') as HTMLElement;
    box.focus();
    // Tab is contained (preventDefault ran => fireEvent returns false).
    expect(fireEvent.keyDown(box, { key: 'Tab' })).toBe(false);
    expect(dialog.contains(document.activeElement)).toBe(true);
  });
});

describe('P26.5 · SearchDialog — grouped, plane-labeled, honest results', () => {
  it('typing a query renders BOTH the Workspace and Project Memory groups', async () => {
    stubFetchRoutes(searchRoutes());
    const view = renderTopBar();
    const { dialog } = await openAndType(view);
    // Workspace (truth) group + its result "why matched"
    expect(await within(dialog).findByText(WS.label)).toBeTruthy();
    expect(within(dialog).getByText(new RegExp(WS.match.reason, 'i'))).toBeTruthy();
    // Project Memory (advisory) group + the leads-not-verdict note
    expect(within(dialog).getByText(MEM.label)).toBeTruthy();
    expect(within(dialog).getByText(new RegExp(searchResponse.memory.note))).toBeTruthy();
    // both plane labels visible, clearly separated
    expect(within(dialog).getByText(/workspace/i)).toBeTruthy();
    expect(within(dialog).getByText(/project memory/i)).toBeTruthy();
  });

  it('a workspace result navigates via its server navigate_to and closes the dialog', async () => {
    stubFetchRoutes(searchRoutes());
    const view = renderTopBar();
    const { dialog } = await openAndType(view);
    const hit = await within(dialog).findByText(WS.label);
    fireEvent.click(hit.closest('a, button') ?? hit);
    expect(view.getByTestId('loc').textContent).toBe(WS.navigate_to);
    expect(view.queryByRole('dialog')).toBeNull();
  });

  it('a memory result navigates to its /memory?concept= deep link and closes', async () => {
    stubFetchRoutes(searchRoutes());
    const view = renderTopBar();
    const { dialog } = await openAndType(view);
    const hit = await within(dialog).findByText(MEM.label);
    fireEvent.click(hit.closest('a, button') ?? hit);
    expect(view.getByTestId('loc').textContent).toBe(MEM.navigate_to);
    expect(view.queryByRole('dialog')).toBeNull();
  });

  it('never renders verdict language in results', async () => {
    stubFetchRoutes(searchRoutes());
    const view = renderTopBar();
    const { dialog } = await openAndType(view);
    await within(dialog).findByText(WS.label);
    expect(dialog.textContent || '').not.toMatch(/\b(PASS|FAIL|invalid|valid against)\b/i);
  });

  it('shows an honest, non-error memory-unavailable note while workspace results still render', async () => {
    stubFetchRoutes(searchRoutes({ body: searchResponseMemoryDown }));
    const view = renderTopBar();
    const { dialog } = await openAndType(view);
    // workspace still works
    expect(await within(dialog).findByText(WS.label)).toBeTruthy();
    // memory group is honestly unavailable (a note, not an error/alert), no fabricated rows
    expect(within(dialog).getByText(/project memory/i)).toBeTruthy();
    expect(within(dialog).queryByText(MEM.label)).toBeNull();
    expect(within(dialog).queryByRole('alert')).toBeNull();
  });

  it('empty valid-query with zero hits says so honestly (never a fabricated row)', async () => {
    const empty = {
      ...searchResponse,
      workspace: { ...searchResponse.workspace, total: 0, returned: 0, results: [] },
      memory: { ...searchResponse.memory, total: 0, returned: 0, results: [] },
    };
    stubFetchRoutes(searchRoutes({ query: 'zzzznope', body: empty }));
    const view = renderTopBar();
    const { dialog } = await openAndType(view, 'zzzznope');
    expect(await within(dialog).findByText(/no matches/i)).toBeTruthy();
  });

  it('a query shorter than 2 chars shows a hint and never calls the backend', async () => {
    // No route stubbed: if the dialog fetched for "a", the stub would throw.
    stubFetchRoutes(searchRoutes());
    const view = renderTopBar();
    const { dialog } = await openAndType(view, 'a');
    expect(await within(dialog).findByText(/at least 2 characters/i)).toBeTruthy();
    expect(within(dialog).queryByText(WS.label)).toBeNull();
  });

  it('surfaces the backend-down state when the API is unreachable', async () => {
    stubFetchDown();
    const view = renderTopBar();
    const { dialog } = await openAndType(view);
    expect(await within(dialog).findByText(/backend|not running|not reachable/i)).toBeTruthy();
  });

  it('renders a distinct snippet with <mark> highlighting (offset path)', async () => {
    const withSnippet = {
      ...searchResponse,
      workspace: {
        ...searchResponse.workspace,
        results: [
          {
            ...WS,
            label: 'Alpha Experiment',
            match: {
              field: 'draft.system.facility.value',
              snippet: 'beamline cu k-edge',
              reason: 'matched draft field value',
              tier: 'substring' as const,
              offsets: [[9, 11]] as [number, number][], // marks "cu"
            },
          },
        ],
      },
    };
    stubFetchRoutes(searchRoutes({ query: 'cu', body: withSnippet }));
    const view = renderTopBar();
    const { dialog } = await openAndType(view, 'cu');
    expect(await within(dialog).findByText('Alpha Experiment')).toBeTruthy();
    const mark = dialog.querySelector('mark');
    expect(mark).not.toBeNull();
    expect(mark!.textContent).toBe('cu');
  });

  it('filters a snippet that carries verdict language (defensive honesty)', async () => {
    const verdictSnippet = {
      ...searchResponse,
      workspace: {
        ...searchResponse.workspace,
        results: [
          {
            ...WS,
            label: 'Beta Experiment',
            match: {
              field: 'draft.note.value',
              snippet: 'this record is INVALID against the schema',
              reason: 'matched draft field value',
              tier: 'substring' as const,
              offsets: [[0, 4]] as [number, number][],
            },
          },
        ],
      },
    };
    stubFetchRoutes(searchRoutes({ query: 'cu', body: verdictSnippet }));
    const view = renderTopBar();
    const { dialog } = await openAndType(view, 'cu');
    // The row (label + why-matched) still renders...
    expect(await within(dialog).findByText('Beta Experiment')).toBeTruthy();
    // ...but the verdict-laden snippet is suppressed, never shown as a <mark>.
    expect(within(dialog).queryByText(/INVALID against/i)).toBeNull();
    expect(dialog.textContent || '').not.toMatch(/\bINVALID\b/i);
  });
});

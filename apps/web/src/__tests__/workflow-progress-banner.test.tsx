import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { WorkflowProgressBanner } from '../components/WorkflowProgressBanner';
import { fixtureWorkflow } from '../test/apiFixtures';
import { ROUTE_PATTERNS } from '../lib/routes';
import type { ApiWorkflow } from '../lib/types';

/*
 * The banner surfaces the single next workflow step as a compact CTA — but
 * ONLY when that step differs from the surface already being viewed (no
 * duplicate call-to-action) and isn't a step this surface already covers
 * with its own resident banner (excludeSteps). current_step is backend-
 * derived (mirrored here via fixtureWorkflow, the same helper the screen
 * suites use) — the component renders it verbatim and never re-derives it.
 */

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

function renderAt(path: string, ui: ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]} future={FUTURE}>
      {ui}
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('WorkflowProgressBanner · content per current_step', () => {
  it('complete_metadata, N=1: singular heading/body + "Review Items" action', () => {
    const wf = fixtureWorkflow({ pending_count: 1, draft_ok: false, ready: false, exported: false, rev: 1 });
    const { getByText, getByRole } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={1} />,
    );
    expect(getByText('1 item needs your attention')).toBeInTheDocument();
    expect(
      getByText('Confirm or complete the remaining item before this record can be exported.'),
    ).toBeInTheDocument();
    expect(getByRole('button', { name: /Review Items/ })).toBeInTheDocument();
  });

  it('complete_metadata, N=3: plural heading/body', () => {
    const wf = fixtureWorkflow({ pending_count: 3, draft_ok: false, ready: false, exported: false, rev: 1 });
    const { getByText } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={3} />,
    );
    expect(getByText('3 items need your attention')).toBeInTheDocument();
    expect(
      getByText('Confirm or complete the remaining items before this record can be exported.'),
    ).toBeInTheDocument();
  });

  it('review_evidence: "Evidence review needed" + Review Evidence action', () => {
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: false, ready: false, exported: false, rev: 1 });
    const { getByText, getByRole } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={0} />,
    );
    expect(getByText('Evidence review needed')).toBeInTheDocument();
    expect(getByRole('button', { name: /Review Evidence/ })).toBeInTheDocument();
  });

  it('review_export_readiness: "Not ready to export yet" — NOT a "complete" message', () => {
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: false, exported: false, rev: 1 });
    const { getByText, getByRole, queryByText } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={0} />,
    );
    expect(getByText('Not ready to export yet')).toBeInTheDocument();
    expect(queryByText(/^complete$/i)).toBeNull();
    expect(queryByText(/all fields resolved/i)).toBeNull();
    expect(getByRole('button', { name: /Review Export Readiness/ })).toBeInTheDocument();
  });

  it('review_export_readiness: does NOT blame the official ISAAC schema', () => {
    /* THE BODY USED TO SAY the record "doesn't pass the official ISAAC schema check
       yet", and no state reaching this step supports that. `review_export_readiness`
       is derived from `Experiment.export_ready()` -> `_all_units_pass_dry_run()` ->
       `export_draft`, which refuses on THREE gates: the no-guessing draft validator,
       ISAAC's own anchored-pattern exactness gate, and the official schema. For the
       first two `export.py` returns `official_report=None` — the official validator
       never ran — so the banner named a verdict that did not exist.

       CLAUDE.md §1 makes the schema upstream-owned; §12 records a surface shipping
       this same conflation once before. This banner renders on four record screens,
       which made it the widest instance of it. Pinned in BOTH directions so a copy
       edit cannot restore the blame or drop the pointer. */
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: false, exported: false, rev: 1 });
    const { getByText, container } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={0} />,
    );
    const text = container.textContent ?? '';
    // NEGATIVE: no source is named, and no schema verdict is claimed.
    expect(text).not.toMatch(/official ISAAC schema/i);
    expect(text).not.toMatch(/ISAAC v1\.05/);
    expect(text).not.toMatch(/schema (check|error|verdict)/i);
    // POSITIVE: it still says something actionable and still routes onward.
    expect(getByText(/does not pass the export checks yet/i)).toBeInTheDocument();
    expect(text).toMatch(/Review export readiness/i);
  });

  it('export: "Ready to export"', () => {
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: false, rev: 1 });
    const { getByText, getByRole } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={0} />,
    );
    expect(getByText('Ready to export')).toBeInTheDocument();
    expect(getByRole('button', { name: /Continue to Export/ })).toBeInTheDocument();
  });
});

describe('WorkflowProgressBanner · suppression rules', () => {
  it('renders nothing when workflow is null', () => {
    const { container } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={null} recordId="rec1" pendingCount={5} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when current_step is null (everything satisfied/exported)', () => {
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: true, rev: 1 });
    expect(wf.current_step).toBeNull();
    const { container } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={0} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when current_step is excluded via excludeSteps', () => {
    const wf = fixtureWorkflow({ pending_count: 2, draft_ok: false, ready: false, exported: false, rev: 1 });
    const { container } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner
        workflow={wf}
        recordId="rec1"
        pendingCount={2}
        excludeSteps={['complete_metadata']}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when already at the destination the step would navigate to (no duplicate CTA)', () => {
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: false, rev: 1 });
    // export -> ROUTES.export('rec1') === '/record/rec1/export'
    const { container } = renderAt(
      '/record/rec1/export',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={0} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for a step id with no defined destination/copy (never fabricates copy)', () => {
    // load_record is always satisfied in practice, but the component must stay
    // defensive rather than invent a heading for it.
    const wf: ApiWorkflow = {
      ordered_steps: [
        {
          id: 'load_record',
          label: 'Load Record',
          state: 'current',
          current: true,
          reopened: false,
          blocked: false,
          reason: null,
        },
      ],
      current_step: 'load_record',
      record_rev: 1,
    };
    const { container } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={0} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('WorkflowProgressBanner · action button', () => {
  it('is a real, named, keyboard-focusable <button type="button">', () => {
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: false, ready: false, exported: false, rev: 1 });
    const { getByRole } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={0} />,
    );
    const btn = getByRole('button', { name: /Review Evidence/ });
    expect(btn.tagName).toBe('BUTTON');
    expect(btn.getAttribute('type')).toBe('button');
    btn.focus();
    expect(document.activeElement).toBe(btn);
    // A native <button> is Enter/Space-activatable by the browser by
    // construction; the same click handler backs both pointer and keyboard
    // activation, exercised below.
    fireEvent.click(btn);
  });

  it('triggers no fetch/api call — the banner only navigates', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: false, ready: false, exported: false, rev: 1 });
    const { getByRole } = renderAt(
      '/record/rec1',
      <WorkflowProgressBanner workflow={wf} recordId="rec1" pendingCount={0} />,
    );
    fireEvent.click(getByRole('button', { name: /Review Evidence/ }));
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// --- push-not-replace navigation, exercised through a real two-route setup ---

function DestinationPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const focusMain = Boolean((location.state as { focusMain?: boolean } | null)?.focusMain);
  return (
    <div>
      <span data-testid="dest-path">{location.pathname}</span>
      <span data-testid="dest-focus">{String(focusMain)}</span>
      <button type="button" onClick={() => navigate(-1)}>
        Go Back
      </button>
    </div>
  );
}

function SourcePage({ workflow, pendingCount }: { workflow: ApiWorkflow; pendingCount: number }) {
  return (
    <div>
      <span data-testid="source">source</span>
      <WorkflowProgressBanner workflow={workflow} recordId="rec1" pendingCount={pendingCount} />
    </div>
  );
}

function renderNavHarness(workflow: ApiWorkflow, pendingCount: number) {
  return render(
    <MemoryRouter initialEntries={['/record/rec1']} future={FUTURE}>
      <Routes>
        <Route path={ROUTE_PATTERNS.record} element={<SourcePage workflow={workflow} pendingCount={pendingCount} />} />
        <Route path={ROUTE_PATTERNS.evidence} element={<DestinationPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('WorkflowProgressBanner · navigation', () => {
  it('activating the action navigates to the correct app-relative destination and PUSHES (back preserved)', () => {
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: false, ready: false, exported: false, rev: 1 });
    const { getByRole, getByTestId, queryByTestId } = renderNavHarness(wf, 0);

    expect(getByTestId('source')).toBeInTheDocument();
    fireEvent.click(getByRole('button', { name: /Review Evidence/ }));

    // Landed on the correct destination for this recordId.
    expect(getByTestId('dest-path').textContent).toBe('/record/rec1/evidence');
    expect(queryByTestId('source')).toBeNull();

    // A history entry was ADDED (not replaced): Back returns to the source.
    fireEvent.click(getByRole('button', { name: /go back/i }));
    expect(getByTestId('source')).toBeInTheDocument();
  });

  it('requests focus movement: navigates carrying state.focusMain === true', () => {
    const wf = fixtureWorkflow({ pending_count: 0, draft_ok: false, ready: false, exported: false, rev: 1 });
    const { getByRole, getByTestId } = renderNavHarness(wf, 0);

    fireEvent.click(getByRole('button', { name: /Review Evidence/ }));

    // The banner asks the destination shell to move focus to <main> so keyboard/
    // screen-reader users land on the new surface. AppShell consumes and clears
    // this flag; here (no AppShell) it persists so we can assert it was sent.
    expect(getByTestId('dest-path').textContent).toBe('/record/rec1/evidence');
    expect(getByTestId('dest-focus').textContent).toBe('true');
  });
});

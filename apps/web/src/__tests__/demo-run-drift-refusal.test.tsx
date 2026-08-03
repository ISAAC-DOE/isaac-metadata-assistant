import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import {
  EXP_ID,
  demoRunDraftOnly,
  resetDemoRoutes,
  stubFetchDown,
  stubFetchRoutes,
} from '../test/apiFixtures';

/*
 * S2 · Run Synthetic Demo — the protective 409 refusal.
 *
 * `POST /api/demo/run` used to re-seed its canonical target unconditionally,
 * destroying a user's confirmed answers. The backend now REFUSES instead, with
 * HTTP 409 and `{"error":"demo_target_drifted", ...}`, mutating nothing.
 *
 * The defect these tests pin is a copy-honesty one, not a crash: every ApiError
 * on this screen fell into one state that renders `BackendDown` — so a healthy
 * server that had just protected the user's work reported itself as "Backend Not
 * Running". These tests hold the line in both directions: the 409 gets its own
 * truthful state, and NOTHING else does.
 *
 * Fixtures are synthetic; the truth core is never involved.
 */

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

/** The 409 body the backend sends. Prose is the server's; only the shape is contractual. */
const driftedBody = {
  error: 'demo_target_drifted',
  experiment_id: EXP_ID,
  message:
    'The demo scenario has been edited. Re-running the demo would discard those edits; ' +
    'POST /api/demo/reset to restore the baseline deliberately.',
};

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="pathname">{loc.pathname}</div>;
}

function renderLoad() {
  return render(
    <MemoryRouter initialEntries={['/load']} future={FUTURE}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  );
}

/** Render /load with one stubbed outcome for the demo run, then click Run Demo. */
function runDemoWith(
  outcome: { status?: number; body: unknown },
  extraRoutes: Record<string, { status?: number; body: unknown }> = {},
) {
  stubFetchRoutes({ 'POST /api/demo/run': outcome, ...extraRoutes });
  const view = renderLoad();
  fireEvent.click(view.getByText(LABELS.actionRunDemoShort));
  return view;
}

/** The refusal panel, queried the way a screen reader reaches it. */
function refusal(view: ReturnType<typeof renderLoad>) {
  return view.queryByRole('alert', { name: new RegExp(LABELS.demoDriftedTitle, 'i') });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('S2 · demo run — the pristine path is unchanged', () => {
  it('a 200 still renders the pipeline steps, with no refusal and no down state', async () => {
    const view = runDemoWith({ body: demoRunDraftOnly });

    expect(await view.findByText('Build Draft')).toBeInTheDocument();
    expect(view.getByText('Open the Record →')).toBeInTheDocument();
    expect(refusal(view)).toBeNull();
    expect(view.queryByText(LABELS.demoDriftedTitle)).toBeNull();
    expect(view.queryByText('Backend Not Running')).toBeNull();
  });
});

describe('S2 · demo run — 409 demo_target_drifted is a refusal, not a failure', () => {
  it('renders the refusal and never the backend-down state', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });

    expect(await view.findByText(LABELS.demoDriftedTitle)).toBeInTheDocument();
    // the exact false statement this slice exists to prevent
    expect(view.queryByText('Backend Not Running')).toBeNull();
    expect(view.queryByText('ISAAC Is Not Responding')).toBeNull();
    expect(view.queryByText('ISAAC Returned an Error')).toBeNull();
    // and no half-run pipeline is drawn
    expect(view.queryByText('Build Draft')).toBeNull();
    expect(view.queryByText('Open the Record →')).toBeNull();
  });

  it('states that nothing ran, why, and that Reset Workspace is the deliberate way back', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });
    await view.findByText(LABELS.demoDriftedTitle);
    const text = (refusal(view) as HTMLElement).textContent ?? '';

    expect(text).toMatch(/nothing ran/i); // it did not run
    expect(text).toMatch(/nothing changed/i); // and it changed nothing
    expect(text).toMatch(/edited/i); // why
    // The remedy must name the reset control by the label that control actually
    // renders. Asserted through LABELS rather than as a literal so a future
    // rename of the button cannot leave this copy pointing at a control that no
    // longer exists — the exact way the pre-P1 wording went stale.
    expect(text).toContain(LABELS.actionResetDemo); // the deliberate remedy
    // …and it must not misdescribe a healthy server or invent a loss
    expect(text).not.toMatch(/not running|unreachable|not responding|offline|down/i);
    expect(text).not.toMatch(/lost|deleted|corrupt/i);
  });

  it('names the scenario the server refused for, when the body carries one', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });
    await view.findByText(LABELS.demoDriftedTitle);
    expect(within(refusal(view) as HTMLElement).getByText(EXP_ID)).toBeInTheDocument();
  });

  it('still refuses honestly when the body omits the optional experiment_id', async () => {
    const view = runDemoWith({ status: 409, body: { error: 'demo_target_drifted' } });
    expect(await view.findByText(LABELS.demoDriftedTitle)).toBeInTheDocument();
    expect(view.queryByText('Backend Not Running')).toBeNull();
    expect(within(refusal(view) as HTMLElement).queryByText(EXP_ID)).toBeNull();
  });
});

describe('S2 · demo run — every other failure keeps its existing state', () => {
  it('a 500 still renders the existing error state, not the refusal', async () => {
    const view = runDemoWith({ status: 500, body: { detail: 'boom' } });

    expect(await view.findByText('Backend Not Running')).toBeInTheDocument();
    expect(refusal(view)).toBeNull();
    expect(view.queryByText(LABELS.demoDriftedTitle)).toBeNull();
  });

  it('an unreachable backend still renders the existing error state', async () => {
    stubFetchDown();
    const view = renderLoad();
    fireEvent.click(view.getByText(LABELS.actionRunDemoShort));

    expect(await view.findByText('Backend Not Running')).toBeInTheDocument();
    expect(refusal(view)).toBeNull();
  });

  it('a 409 carrying a DIFFERENT error code is not claimed as a drift refusal', async () => {
    const view = runDemoWith({ status: 409, body: { error: 'something_else' } });

    expect(await view.findByText('Backend Not Running')).toBeInTheDocument();
    expect(refusal(view)).toBeNull();
  });
});

describe('S2 · demo run — the refusal is announced and actionable', () => {
  it('is an alert region named by its visible title', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });
    await view.findByText(LABELS.demoDriftedTitle);

    const region = refusal(view);
    expect(region).not.toBeNull();
    const labelledby = region!.getAttribute('aria-labelledby');
    expect(labelledby).toBeTruthy();
    expect(document.getElementById(labelledby!)!.textContent).toContain(LABELS.demoDriftedTitle);
  });

  it('offers a keyboard-reachable control that routes to where Reset Demo lives', async () => {
    // the destination is stubbed too, so the assertion is that the control lands
    // on a LIVE My Experiments (where the real Reset Demo control renders), not
    // merely that a pathname string changed
    const view = runDemoWith({ status: 409, body: driftedBody }, resetDemoRoutes().routes);
    await view.findByText(LABELS.demoDriftedTitle);

    const go = within(refusal(view) as HTMLElement).getByRole('button', {
      name: LABELS.actionGoToExperiments,
    }) as HTMLButtonElement;
    expect(go.tagName).toBe('BUTTON'); // natively focusable, no tabindex needed
    expect(go.disabled).toBe(false);
    go.focus();
    expect(document.activeElement).toBe(go);

    fireEvent.click(go);
    expect(view.getByTestId('pathname').textContent).toBe('/experiments');
    expect(await view.findByRole('button', { name: LABELS.actionResetDemo })).toBeInTheDocument();
  });

  it('leaves Run Demo enabled so the refusal is not a dead end', async () => {
    const view = runDemoWith({ status: 409, body: driftedBody });
    await view.findByText(LABELS.demoDriftedTitle);
    const run = view.getByText(LABELS.actionRunDemoShort) as HTMLButtonElement;
    expect(run.disabled).toBe(false);
  });
});

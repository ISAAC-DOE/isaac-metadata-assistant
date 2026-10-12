import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { setTutorialScope } from '../lib/api';
import { __bootTutorialStore, getTutorialState } from '../lib/tutorialController';
import { EXAMPLE_RECORD_IDS } from '../lib/exampleRecords';
import {
  TUTORIAL_SESSION_ID,
  bundleRoutes,
  demoRunDraftOnly,
  stubFetchRoutes,
  tutorialSessionRoutes,
} from '../test/apiFixtures';

/*
 * B-05 / B-06 — the two worked-example controls that led somewhere that could not work.
 *
 *  B-05  /load's primary "Run the Worked Example" answered `409 tutorial_scope_required`
 *        EVERY time outside a worked-example session, and explained itself only after
 *        the press. Outside a session the card now offers the control that works.
 *  B-06  The walkthrough bar's "Open the Worked Example" navigated to /load (not to a
 *        record), where the tutorial card then said "Not on this screen". It now opens
 *        the worked-example record the run produces.
 */

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="pathname">{loc.pathname}</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={FUTURE}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  );
}

function enterWorkedExample(): void {
  // The two module bodies a page load evaluates — see `create-experiment.test.tsx`.
  setTutorialScope(TUTORIAL_SESSION_ID);
  __bootTutorialStore();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('B-05 · /load outside a worked-example session', () => {
  it('offers Launch Guided Demo and NO run button, so no press is a guaranteed refusal', async () => {
    const calls = stubFetchRoutes({});
    renderAt('/load');
    expect(
      await screen.findByRole('button', { name: LABELS.actionLaunchGuidedDemo }),
    ).toBeEnabled();
    expect(screen.queryByRole('button', { name: LABELS.actionRunDemoShort })).toBeNull();
    // The cause is stated BEFORE any press, scoped to this tab, and the audited
    // disclosure of what launching does is the same text My Experiments shows.
    const body = document.querySelector('.onramp.emphasis')?.textContent ?? '';
    expect(body).toContain(LABELS.demoRunsInsideGuidedDemo);
    expect(body).toContain(LABELS.launchGuidedDemoBody);
    expect(LABELS.demoRunsInsideGuidedDemo).toMatch(/this browser tab/i);
    // Rendering it asked the server for nothing.
    expect(calls.filter((k) => k.includes('/demo/run'))).toEqual([]);
  });

  it('the launch control is described by the disclosure, and pressing it opens a session — never the refused run', async () => {
    const calls = stubFetchRoutes({
      ...tutorialSessionRoutes(),
      'POST /api/demo/run': { status: 409, body: { error: 'tutorial_scope_required' } },
    });
    renderAt('/load');
    const launch = await screen.findByRole('button', { name: LABELS.actionLaunchGuidedDemo });
    const hint = document.getElementById(launch.getAttribute('aria-describedby') ?? '');
    expect(hint?.textContent).toContain(LABELS.launchGuidedDemoBody);

    fireEvent.click(launch);
    await waitFor(() => expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID));
    expect(calls).toContain('POST /api/tutorial/sessions');
    expect(calls.filter((k) => k.includes('/demo/run'))).toEqual([]);
  });

  it('is disabled while a session is opening, so a second press cannot orphan one', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const routes = tutorialSessionRoutes();
    stubFetchRoutes({
      ...routes,
      'POST /api/tutorial/sessions': async () => {
        await gate;
        return (routes['POST /api/tutorial/sessions'] as never);
      },
    } as never);
    renderAt('/load');
    const launch = await screen.findByRole('button', { name: LABELS.actionLaunchGuidedDemo });
    fireEvent.click(launch);
    await waitFor(() => expect(launch).toBeDisabled());
    release();
  });
});

describe('B-05 · /load inside a worked-example session', () => {
  it('keeps the run button, and it works', async () => {
    enterWorkedExample();
    stubFetchRoutes({ 'POST /api/demo/run': { body: demoRunDraftOnly } });
    renderAt('/load');
    expect(screen.queryByRole('button', { name: LABELS.actionLaunchGuidedDemo })).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionRunDemoShort }));
    expect(await screen.findByText('Open the Record →')).toBeInTheDocument();
  });
});

describe('B-06 · the worked-example bar opens the record', () => {
  it('"Open the Worked Example" lands on the worked-example record, not on /load', async () => {
    enterWorkedExample();
    stubFetchRoutes({
      ...bundleRoutes(EXAMPLE_RECORD_IDS[0]),
      ...tutorialSessionRoutes(),
    } as never);
    renderAt('/experiments');
    fireEvent.click(await screen.findByRole('button', { name: LABELS.actionRunDemo }));
    await waitFor(() =>
      expect(screen.getByTestId('pathname').textContent).toBe(
        `/record/${EXAMPLE_RECORD_IDS[0]}`,
      ),
    );
  });
});

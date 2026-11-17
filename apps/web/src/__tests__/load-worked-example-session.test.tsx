import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { setTutorialScope } from '../lib/api';
import { __bootTutorialStore } from '../lib/tutorialController';
import { EXAMPLE_RECORD_IDS } from '../lib/exampleRecords';
import {
  TUTORIAL_SESSION_ID,
  bundleRoutes,
  stubFetchRoutes,
  tutorialSessionRoutes,
} from '../test/apiFixtures';

/*
 * B-05 / B-06 — the two worked-example controls that led somewhere that could not work.
 *
 *  B-05  /load's primary "Run the Worked Example" answered `409 tutorial_scope_required`
 *        outside a worked-example session. ~~Pinned here~~ until 2026-11-16, when `/load`
 *        became a redirect to My Experiments.
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

// ~~B-05 · /load outside and inside a worked-example session~~ — removed 2026-11-16:
// `/load` redirects to My Experiments (`historical-import-guide.test.tsx` pins that).

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

import { describe, it, expect } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { AppShell } from '../components/AppShell';

/*
 * AppShell's focus-on-navigation contract. A WorkflowProgressBanner action
 * navigates with `state: { focusMain: true }`; AppShell moves focus to the
 * <main id="main"> landmark (top of the destination surface) so keyboard and
 * screen-reader users don't get stranded on the old surface, then clears the
 * one-shot flag with a replace navigation so a later render / back-forward
 * visit never re-steals focus.
 */

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

/** Renders the current location.state so the test can assert the focusMain flag
 * is consumed-and-cleared by AppShell's effect. */
function LocationStateProbe() {
  const location = useLocation();
  return <span data-testid="loc-state">{JSON.stringify(location.state ?? null)}</span>;
}

describe('AppShell · focus-on-navigation', () => {
  it('moves focus to <main> when navigated with state.focusMain, then clears the flag', async () => {
    const { container, getByTestId } = render(
      <MemoryRouter
        initialEntries={[{ pathname: '/record/rec1/evidence', state: { focusMain: true } }]}
        future={FUTURE}
      >
        <AppShell variant="record" topBar={null}>
          <h1>Destination heading</h1>
          <LocationStateProbe />
        </AppShell>
      </MemoryRouter>,
    );

    const main = container.querySelector('#main');
    expect(main).not.toBeNull();
    // Focus landed on the main landmark (top of the destination surface).
    expect(document.activeElement).toBe(main);
    // The one-shot flag was cleared via the replace navigation — a later
    // render / back-forward visit will not re-steal focus.
    await waitFor(() => {
      const parsed = JSON.parse(getByTestId('loc-state').textContent ?? 'null');
      expect(parsed?.focusMain).toBeFalsy();
    });
  });

  it('does NOT move focus to <main> on a normal navigation (no focusMain flag)', () => {
    const { container } = render(
      <MemoryRouter initialEntries={[{ pathname: '/record/rec1/evidence' }]} future={FUTURE}>
        <AppShell variant="record" topBar={null}>
          <h1>Destination heading</h1>
        </AppShell>
      </MemoryRouter>,
    );
    const main = container.querySelector('#main');
    expect(document.activeElement).not.toBe(main);
  });
});

/*
 * "GO TO FIELD" HANDS FOCUS OFF ONCE PER ARRIVAL — independent review of the QA
 * A-09/A-11 slice, IMPORTANT 1.
 *
 * Measured by the reviewer: Go to Field → choose Environment → type "298" in
 * Temperature, and Temperature held "29" with focus back on the Environment select.
 * The focus effect depended on `focusedRun`, which is a NEW object after every
 * autosave and feed refresh, while `?at=field:…` stays in the URL — so every save
 * re-ran it and pulled the caret back to the linked field mid-typing.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { AUTOSAVE_DEBOUNCE_MS, __resetRunAutosaveStore } from '../lib/runAutosaveStore';
import { bundleRoutes, runFixture, runsPage, stubFetchRoutes } from '../test/apiFixtures';

configure({ asyncUtilTimeout: 5_000 });
vi.setConfig({ testTimeout: 30_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;
const RUN = runFixture({ id: 'RUNAAA', label: 'Run 1', ordinal: 1, version: 'ra.0' });

beforeEach(() => __resetRunAutosaveStore());
afterEach(() => vi.unstubAllGlobals());

describe('Go to Field focuses the linked field once, not after every save', () => {
  it('a later autosave of ANOTHER field does not pull focus back to the linked one', async () => {
    let saves = 0;
    stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}/runs`]: { body: runsPage([RUN]) },
      [`GET ${BASE}/runs/RUNAAA`]: { body: { run: RUN } },
      [`PATCH ${BASE}/runs/RUNAAA`]: () => {
        saves += 1;
        // A NEW run object, exactly as every save returns one.
        return {
          body: {
            run: {
              ...RUN,
              version: `ra.${saves}`,
              rev: saves,
              fields: {
                'context.temperature_K': { value: 298, status: 'verified', evidence: [] },
              },
            },
          },
        };
      },
    } as never);
    render(
      <MemoryRouter
        initialEntries={[`/record/${ID}?view=runs&run=RUNAAA&at=field:context.environment`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );

    // The arrival itself lands on the linked field.
    await waitFor(() =>
      expect(document.activeElement?.getAttribute('data-run-field-path')).toBe(
        'context.environment',
      ),
    );

    // The reader moves on and types elsewhere; the save returns a new run object.
    const temperature = screen.getByLabelText('Temperature (K)') as HTMLInputElement;
    await act(async () => {
      temperature.focus();
      fireEvent.change(temperature, { target: { value: '298' } });
    });
    await waitFor(() => expect(saves).toBe(1), { timeout: AUTOSAVE_DEBOUNCE_MS + 4_000 });
    // Let the adopted run re-render every effect that depends on it.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 300));
    });

    expect(document.activeElement).toBe(temperature);
  });

  it('…and does not scroll the page back to the linked field after every save', async () => {
    /* The SAME dependency drove the mark-and-scroll effect: each save re-ran
       `scrollIntoView` on the linked address, yanking the page away from the field the
       reader was typing in. Scrolling is once per arrival; the mark stays. */
    const scrolled: Element[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this);
    } as typeof Element.prototype.scrollIntoView;
    try {
      let saves = 0;
      stubFetchRoutes({
        ...bundleRoutes(ID),
        [`GET ${BASE}/runs`]: { body: runsPage([RUN]) },
        [`GET ${BASE}/runs/RUNAAA`]: { body: { run: RUN } },
        [`PATCH ${BASE}/runs/RUNAAA`]: () => {
          saves += 1;
          return { body: { run: { ...RUN, version: `ra.${saves}`, rev: saves } } };
        },
      } as never);
      render(
        <MemoryRouter
          initialEntries={[`/record/${ID}?view=runs&run=RUNAAA&at=field:context.environment`]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <AppRoutes />
        </MemoryRouter>,
      );
      const linked = () =>
        scrolled.filter((el) => el.getAttribute('data-address') === 'field:context.environment')
          .length;
      await waitFor(() => expect(linked()).toBe(1));
      const temperature = screen.getByLabelText('Temperature (K)') as HTMLInputElement;
      await act(async () => {
        temperature.focus();
        fireEvent.change(temperature, { target: { value: '298' } });
      });
      await waitFor(() => expect(saves).toBe(1), { timeout: AUTOSAVE_DEBOUNCE_MS + 4_000 });
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 300));
      });
      expect(linked()).toBe(1);
      // The mark is still there — only the SCROLL is once.
      expect(
        document.querySelector('[data-address="field:context.environment"]')?.getAttribute(
          'data-linked-address',
        ),
      ).toBe('true');
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it('an arrival at an INHERITED row lands on the row’s action, not the run heading', async () => {
    /* A record-level value on a run has no run-editor control; the place a value is
       entered there is the row's Override control (review minor: focus had stayed on
       the run's heading). `runFixture` carries an overridable row at
       `sample.material.name`. */
    const inheritedRun = runFixture({ id: 'RUNAAA', label: 'Run 1', ordinal: 1, version: 'ra.0' });
    stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}/runs`]: { body: runsPage([inheritedRun]) },
      [`GET ${BASE}/runs/RUNAAA`]: { body: { run: inheritedRun } },
    } as never);
    render(
      <MemoryRouter
        initialEntries={[`/record/${ID}?view=runs&run=RUNAAA&at=field:sample.material.name`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(document.activeElement?.textContent ?? '').toMatch(/Override for this run/),
    );
  });
});

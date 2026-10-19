/*
 * A RUN OVERRIDE AT A CLOSED-LIST FIELD IS A CHOICE, NOT A TEXT BOX — QA A-10
 * (2026-10-12), measured in Chromium: the run override for `system.technique` was a
 * free-text input, and "ZZ-not-a-technique" was recorded (the override route stores
 * what it is sent; that server permissiveness is pre-existing and recorded in
 * `apps/api/tests/test_system_enum_fields.py`). The schema closes the field with a
 * fixed list, so the form now offers exactly that list — READ from `GET /api/schema`,
 * never transcribed — and a field the schema leaves open keeps its text box.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import { RunInheritedPanel } from '../components/RunInheritedPanel';
import { stubFetchRoutes, type RouteEntry } from '../test/apiFixtures';
import type { ApiRunView } from '../lib/types';

const EXP = 'demo';
const RUN = 'RUNAAA';
const OVERRIDES = `POST /api/experiments/${EXP}/runs/${RUN}/overrides`;
const TECHNIQUE = 'field:system.technique';
const MATERIAL = 'field:sample.material.name';

const SCHEMA = {
  schema_version: '1.05',
  schema: {
    properties: {
      system: { properties: { technique: { type: 'string', enum: ['XAS', 'XES', 'RIXS'] } } },
      sample: { properties: { material: { properties: { name: { type: 'string' } } } } },
    },
  },
};

const envelope = (value: unknown) => ({ value, status: 'verified', evidence: [] });

function runView(): ApiRunView {
  return {
    id: RUN,
    experiment_id: EXP,
    label: 'Run 1',
    ordinal: 1,
    created_utc: '2099-04-02T09:05:00Z',
    updated_utc: '2099-04-02T09:05:00Z',
    rev: 3,
    version: 'ra.3',
    record_id: null,
    fields: {},
    inherited: {
      [TECHNIQUE]: {
        state: 'inherited',
        payload: envelope('XAS'),
        inherited_payload: envelope('XAS'),
        overridable: true,
      },
      [MATERIAL]: {
        state: 'inherited',
        payload: envelope('Synthetic CuO powder'),
        inherited_payload: envelope('Synthetic CuO powder'),
        overridable: true,
      },
    },
  } as ApiRunView;
}

afterEach(() => vi.unstubAllGlobals());

const rowFor = (address: string) =>
  document.querySelector(`[data-address="${address}"]`) as HTMLElement;

async function openOverride(address: string) {
  await act(async () => {
    fireEvent.click(
      within(rowFor(address)).getByRole('button', { name: /Override for this run/ }),
    );
  });
}

describe('an override at a field the schema closes with a list', () => {
  it('offers the schema’s own list, preselects nothing, and records the chosen member', async () => {
    const seen: Record<string, unknown>[] = [];
    const routes: Record<string, RouteEntry> = {
      'GET /api/schema': { body: SCHEMA },
      [OVERRIDES]: async (init?: RequestInit) => {
        seen.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return {
          body: {
            run: runView(),
            override: { address: TECHNIQUE, recorded_utc: '2099-04-02T10:00:00Z' },
          },
        };
      },
    };
    stubFetchRoutes(routes);
    render(<RunInheritedPanel experimentId={EXP} run={runView()} onRun={vi.fn()} />);

    await openOverride(TECHNIQUE);
    const select = (await within(rowFor(TECHNIQUE)).findByRole('combobox')) as HTMLSelectElement;
    expect(within(rowFor(TECHNIQUE)).queryByRole('textbox')).toBeNull();
    expect(select.value).toBe('');
    expect(Array.from(select.options).map((o) => o.value)).toEqual(['', 'XAS', 'XES', 'RIXS']);

    await act(async () => {
      fireEvent.change(select, { target: { value: 'XES' } });
    });
    await act(async () => {
      fireEvent.click(within(rowFor(TECHNIQUE)).getByRole('checkbox'));
    });
    await act(async () => {
      fireEvent.click(within(rowFor(TECHNIQUE)).getByRole('button', { name: /Record override/ }));
    });
    await waitFor(() => expect(seen).toHaveLength(1));
    expect((seen[0].payload as { value: unknown }).value).toBe('XES');
  });

  it('a field the schema leaves open keeps its text box', async () => {
    stubFetchRoutes({ 'GET /api/schema': { body: SCHEMA } });
    render(<RunInheritedPanel experimentId={EXP} run={runView()} onRun={vi.fn()} />);
    await openOverride(MATERIAL);
    await waitFor(() => expect(within(rowFor(MATERIAL)).getByRole('textbox')).toBeTruthy());
    expect(within(rowFor(MATERIAL)).queryByRole('combobox')).toBeNull();
  });

  it('with no readable schema it falls back to the text box rather than inventing a list', async () => {
    stubFetchRoutes({ 'GET /api/schema': { status: 500, body: {} } });
    render(<RunInheritedPanel experimentId={EXP} run={runView()} onRun={vi.fn()} />);
    await openOverride(TECHNIQUE);
    await waitFor(() => expect(within(rowFor(TECHNIQUE)).getByRole('textbox')).toBeTruthy());
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('REVIEW I-2: keyboard focus follows the box when the list replaces it', async () => {
    /* The form opens with focus in the text box, the schema read then swaps it for a
       select — and focus was left on <body> (measured: INPUT → BODY with an 800 ms
       schema delay). The select takes focus when it replaces a focused box. */
    let release: (value: unknown) => void = () => {};
    stubFetchRoutes({
      'GET /api/schema': () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    } as never);
    render(<RunInheritedPanel experimentId={EXP} run={runView()} onRun={vi.fn()} />);
    await openOverride(TECHNIQUE);
    await waitFor(() =>
      expect(document.activeElement).toBe(within(rowFor(TECHNIQUE)).getByRole('textbox')),
    );
    await act(async () => {
      release({ body: SCHEMA });
    });
    const select = await within(rowFor(TECHNIQUE)).findByRole('combobox');
    await waitFor(() => expect(document.activeElement).toBe(select));
  });

  it('REVIEW I-3: a STORED value outside the list is shown as such and is never re-confirmed', async () => {
    /* "Change this run's value" prefills the box with the run's own stored override.
       The override route stores off-enum values (and the old text box could create
       one), so the select showed "Choose a value…" while holding "ZZ-not-a-technique"
       — and Record override POSTed it with a fresh confirmation the reader never saw. */
    const seen: unknown[] = [];
    const overridden = runView();
    overridden.inherited[TECHNIQUE] = {
      state: 'overridden',
      payload: envelope('ZZ-not-a-technique'),
      inherited_payload: envelope('XAS'),
      displaced_payload: envelope('XAS'),
      overridable: true,
    };
    stubFetchRoutes({
      'GET /api/schema': { body: SCHEMA },
      [OVERRIDES]: (init?: RequestInit) => {
        seen.push(init?.body);
        return { body: { run: overridden, override: { address: TECHNIQUE, recorded_utc: 'x' } } };
      },
    } as never);
    render(<RunInheritedPanel experimentId={EXP} run={overridden} onRun={vi.fn()} />);
    await act(async () => {
      fireEvent.click(
        within(rowFor(TECHNIQUE)).getByRole('button', { name: /Change this run's value/ }),
      );
    });
    const select = (await within(rowFor(TECHNIQUE)).findByRole('combobox')) as HTMLSelectElement;
    // What the control DISPLAYS is what it holds, and it says what that is.
    expect(select.value).toBe('ZZ-not-a-technique');
    const shown = select.options[select.selectedIndex];
    expect(shown.textContent).toBe('ZZ-not-a-technique — not an allowed value');
    expect(shown.disabled).toBe(true);
    await act(async () => {
      fireEvent.click(within(rowFor(TECHNIQUE)).getByRole('checkbox'));
    });
    await act(async () => {
      fireEvent.click(within(rowFor(TECHNIQUE)).getByRole('button', { name: /Record override/ }));
    });
    expect(seen).toHaveLength(0);
    expect(rowFor(TECHNIQUE).textContent).toMatch(/Choose one of the values the official schema allows/);
  });
});

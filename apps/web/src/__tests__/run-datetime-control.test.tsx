/**
 * THE ACQUISITION-TIMESTAMP CONTROLS, ON A REAL RUN CARD.
 *
 * `run-datetime.test.ts` pins the conversions; this pins what a scientist meets:
 * which control is primary, what the zone claim is, when the ISO text path opens
 * by itself, and — the one that matters most — that the PATCH body is the same
 * string it always was.
 *
 * WHAT IS DELIBERATELY NOT ASSERTED HERE: that `start <= end`. `runFields.ts`
 * records that as an open decision with the measurement behind it (an inverted
 * window PATCHes 200, Check Run reports nothing about either path, and official
 * validation passes `ok: true` with zero errors). A picker makes an inverted
 * window EASIER to produce, and closing it in this one writer would be silent
 * for every other. The last test below states that plainly rather than leaving
 * the absence to be read as an oversight.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, cleanup, configure, render, fireEvent, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { __resetRunAutosaveStore } from '../lib/runAutosaveStore';
import {
  bundleRoutes,
  runFixture,
  runsPage,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';

configure({ asyncUtilTimeout: 5_000 });
vi.setConfig({ testTimeout: 30_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

const envelope = (value: unknown) => ({ value, status: 'verified', evidence: [] });

const START = 'timestamps.acquired_start_utc';

function run(fields: Record<string, unknown>) {
  return runFixture({ id: 'RUNAAA', label: 'Run 1', version: 'ra.0', fields });
}

beforeEach(() => {
  __resetRunAutosaveStore();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function showRun(fields: Record<string, unknown>, extra: Record<string, RouteEntry> = {}) {
  stubFetchRoutes({
    ...bundleRoutes(ID),
    [`GET ${BASE}/runs`]: { body: runsPage([run(fields)]) },
    ...extra,
  });
  render(
    <MemoryRouter
      initialEntries={[`/record/${ID}?view=runs`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
  await screen.findByRole('button', { name: /Add Run/ });
  /* Open the ONE run, the way a reader does — the compact row's own header is
     the open control (`RunsSection`'s master-detail). Its accessible name
     carries an `.sr-only` "Open " ahead of the run's label. */
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /^Open Run \d/ }));
  });
  const card = document.querySelector('[data-run-id="RUNAAA"]');
  if (card === null) throw new Error('no run card');
  return { card: card as HTMLElement };
}

const picker = (card: HTMLElement) =>
  card.querySelector(`[data-run-field-path="${START}"]`) as HTMLInputElement;
const isoBox = (card: HTMLElement) =>
  card.querySelector(`[data-run-field-iso-path="${START}"]`) as HTMLInputElement;
const disclosure = (card: HTMLElement) =>
  isoBox(card).closest('details') as HTMLDetailsElement;

describe('the picker is the primary control, and it says which clock it is', () => {
  it('is a datetime control, seeded from the stored value', async () => {
    const { card } = await showRun({ [START]: envelope('2026-01-31T09:00:00Z') });
    expect(picker(card).type).toBe('datetime-local');
    // jsdom's own value sanitization drops the seconds it was given (it
    // implements no `step`); what matters is that the DATE and CLOCK survive
    // and that the stored string is unchanged — asserted below.
    expect(picker(card).value.startsWith('2026-01-31T09:00')).toBe(true);
    // The field's NAME is untouched, which is why every surface, test and
    // script that addresses it by name still does.
    expect(within(card).getByLabelText('Acquisition start')).toBe(picker(card));
  });

  it('MUTATION-GUARDED: the zone is stated, not assumed', async () => {
    /*
     * MUTATION: dropping the `UTC` marker and the hint makes this RED — and
     * leaves a genuinely ambiguous field, because `datetime-local` has no
     * timezone of its own and the value is being stored with a `Z` regardless.
     */
    const { card } = await showRun({});
    const field = picker(card).closest('.run-field') as HTMLElement;
    expect(within(field).getByText('UTC')).toBeTruthy();
    expect(field.textContent).toMatch(/Entered and stored as UTC/);
    expect(field.textContent).toMatch(/never converts/i);
  });

  it('reads the stored value back in both spellings', async () => {
    const { card } = await showRun({ [START]: envelope('2026-01-31T09:00:00Z') });
    const readback = (card.querySelector('.run-field-readback') as HTMLElement).textContent ?? '';
    expect(readback).toContain('Jan 31, 2026 · 09:00 UTC');
    // …and the exact string the record holds, so the reader never has to trust
    // that the picker and the record agree.
    expect(readback).toContain('2026-01-31T09:00:00Z');
  });

  it('shows no read-back on an empty field, rather than a rendering of nothing', async () => {
    const { card } = await showRun({});
    expect(card.querySelector('.run-field-readback')).toBeNull();
  });
});

describe('the picker sends the string the text box always sent', () => {
  async function patchAfter(act_: () => void, seed: Record<string, unknown> = {}) {
    const bodies: Record<string, unknown>[] = [];
    const { card } = await showRun(
      seed,
      {
        [`PATCH ${BASE}/runs/RUNAAA`]: (init?: RequestInit) => {
          bodies.push(JSON.parse(String(init?.body ?? '{}')));
          return { body: { run: run({}) } };
        },
      },
    );
    vi.useFakeTimers();
    await act(async () => {
      act_();
      await vi.runAllTimersAsync();
    });
    return { bodies, card };
  }

  it('MUTATION-GUARDED: a picked minute becomes the official seconds-and-Z string', async () => {
    /*
     * THE CONTRACT. MUTATION: sending `e.target.value` straight through, or
     * dropping the `Z`, makes this RED — and PATCHes a string this record has
     * never held, past a gate (`parseRunField`) that would have refused it.
     */
    const { bodies } = await patchAfter(() => {
      const el = document.querySelector(`[data-run-field-path="${START}"]`) as HTMLInputElement;
      fireEvent.change(el, { target: { value: '2026-01-31T09:00' } });
    });
    expect(bodies).toEqual([
      { confirmed_by_user: true, fields: { [START]: '2026-01-31T09:00:00Z' } },
    ]);
  });

  it('an emptied picker clears the field, which is `null` on the wire', async () => {
    /* Seeded, because clearing a box that was already empty is not a change and
       React fires no event for it — the test would pass vacuously. */
    const { bodies } = await patchAfter(
      () => {
        const el = document.querySelector(`[data-run-field-path="${START}"]`) as HTMLInputElement;
        fireEvent.change(el, { target: { value: '' } });
      },
      { [START]: envelope('2026-01-31T09:00:00Z') },
    );
    expect(bodies).toEqual([{ confirmed_by_user: true, fields: { [START]: null } }]);
  });
});

describe('the ISO text path is there for what the picker cannot hold', () => {
  it('is present, named, and closed by default on a value the picker CAN show', async () => {
    const { card } = await showRun({ [START]: envelope('2026-01-31T09:00:00Z') });
    expect(isoBox(card)).not.toBeNull();
    expect(within(card).getByLabelText('Acquisition start — ISO 8601 text')).toBe(isoBox(card));
    expect(disclosure(card).open).toBe(false);
    // It carries the stored string verbatim, which is the point of it.
    expect(isoBox(card).value).toBe('2026-01-31T09:00:00Z');
  });

  it('MUTATION-GUARDED: an OFFSET value opens the text path and disables the picker', async () => {
    /*
     * MUTATION: letting the picker show the wall clock of a `+02:00` value
     * makes this RED — and ships the worst defect available here: an edit would
     * re-serialize `09:00` as `09:00Z`, moving the recorded instant by two
     * hours with nothing on screen saying so.
     */
    const { card } = await showRun({ [START]: envelope('2026-01-31T09:00:00+02:00') });
    expect(disclosure(card).open).toBe(true);
    expect(picker(card).disabled).toBe(true);
    // An empty picker beside a filled record would read as an empty field, so
    // the pane says which of the two the record holds.
    expect((disclosure(card).textContent ?? '')).toMatch(/timezone offset/);
    expect(isoBox(card).value).toBe('2026-01-31T09:00:00+02:00');
    // And the read-back still names the offset rather than converting it.
    expect((card.querySelector('.run-field-readback') as HTMLElement).textContent).toContain(
      'Jan 31, 2026 · 09:00 +02:00',
    );
  });

  it('a value with no zone at all also opens the text path — no `Z` is invented', async () => {
    const { card } = await showRun({ [START]: envelope('2026-01-31T09:00:00') });
    expect(disclosure(card).open).toBe(true);
    expect(isoBox(card).value).toBe('2026-01-31T09:00:00');
  });

  it('the reader’s own choice wins over the default', async () => {
    const { card } = await showRun({ [START]: envelope('2026-01-31T09:00:00+02:00') });
    expect(disclosure(card).open).toBe(true);
    await act(async () => {
      // jsdom fires no `toggle` from a click on `<summary>`, so the state is
      // driven the way the browser would leave it and the handler is exercised
      // directly — which is the handler under test here.
      disclosure(card).open = false;
      fireEvent(disclosure(card), new Event('toggle'));
    });
    expect(disclosure(card).open).toBe(false);
  });
});

describe('no start/end ordering gate is added, and that is recorded not implied', () => {
  it('an inverted window is sent, exactly as the text box always sent it', async () => {
    /*
     * `runFields.ts` measured this: a PATCH carrying a start AFTER its end
     * returns 200 and stores both verbatim, Check Run reports nothing about
     * either path, and a record that validated `ok: true` still does with zero
     * errors once the window is inverted.
     *
     * THE PICKER MAKES IT EASIER TO PRODUCE — two clicks rather than two typed
     * strings — and this test exists so that is a DISCLOSED property rather
     * than a surprise. Whether an inverted window is an error, a legitimate
     * encoding of something, or a question to ask is a scientific-validity
     * judgement, and a gate added only in a browser would be silent for every
     * other writer.
     */
    const bodies: Record<string, unknown>[] = [];
    const { card } = await showRun(
      {},
      {
        [`PATCH ${BASE}/runs/RUNAAA`]: (init?: RequestInit) => {
          bodies.push(JSON.parse(String(init?.body ?? '{}')));
          return { body: { run: run({}) } };
        },
      },
    );
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(picker(card), { target: { value: '2026-01-31T12:00' } });
      await vi.runAllTimersAsync();
    });
    await act(async () => {
      const end = document.querySelector(
        '[data-run-field-path="timestamps.acquired_end_utc"]',
      ) as HTMLInputElement;
      fireEvent.change(end, { target: { value: '2026-01-01T00:00' } });
      await vi.runAllTimersAsync();
    });
    expect(bodies).toEqual([
      { confirmed_by_user: true, fields: { [START]: '2026-01-31T12:00:00Z' } },
      {
        confirmed_by_user: true,
        fields: { 'timestamps.acquired_end_utc': '2026-01-01T00:00:00Z' },
      },
    ]);
    // Nothing on the card calls it wrong, because nothing in this build knows
    // whether it is.
    expect(card.textContent ?? '').not.toMatch(/before|after|order|invalid window/i);
  });
});

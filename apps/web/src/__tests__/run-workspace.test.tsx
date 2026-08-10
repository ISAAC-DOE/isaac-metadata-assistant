/*
 * THE RUN WORKSPACE — Add Run, the collapsible card, autosave, and Check Run.
 *
 * WHAT THIS FILE IS FOR, and the reason it is written the way it is: this repo
 * has shipped green tests that protected nothing, including a disclosure test
 * that passed with INVERTED polarity. So the three load-bearing assertions here
 * — autosave never lies about `Saved`, a 412 becomes `Conflict`, and two runs
 * stay isolated — were each verified by BREAKING the component in the exact way
 * the test claims to catch and confirming the test fails. The mutations and the
 * failure output are recorded in the slice report.
 *
 * TIMER DISCIPLINE. The initial record load runs on REAL timers (it is a
 * six-endpoint bundle and nothing about it is being tested here); fake timers
 * are installed only once the screen is up, so the debounce window is the one
 * thing under the test's control.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, render, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { AppRoutes } from '../App';
import { AUTOSAVE_DEBOUNCE_MS, AUTOSAVE_RETRY_BASE_MS } from '../lib/useRunAutosave';
import {
  bundleRoutes,
  runFixture,
  stubFetchRoutes,
  VERSION_FIELDS,
  type RouteEntry,
} from '../test/apiFixtures';

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

const RUN_A = runFixture({ id: 'RUNAAA', label: 'Run 1', ordinal: 1, version: 'ra.0' });
const RUN_B = runFixture({
  id: 'RUNBBB',
  label: 'Run 2',
  ordinal: 2,
  version: 'rb.0',
  fields: {
    'context.environment': { value: 'ex_situ', status: 'verified', evidence: [] },
    'context.temperature_K': { value: 77, status: 'verified', evidence: [] },
  },
});

function runsBody(runs: unknown[]) {
  return { runs, experiment_version: VERSION_FIELDS.version };
}

function renderRecord(extra: Record<string, RouteEntry>): string[] {
  const calls = stubFetchRoutes({ ...bundleRoutes(ID), ...extra });
  render(
    <MemoryRouter
      initialEntries={[`/record/${ID}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
  return calls;
}

/** The card element for one run id. */
function cardFor(runId: string): HTMLElement {
  const el = document.querySelector(`[data-run-id="${runId}"]`);
  if (!el) throw new Error(`no run card rendered for ${runId}`);
  return el as HTMLElement;
}

/** The accordion header button of one run card. */
function headerOf(runId: string): HTMLButtonElement {
  return within(cardFor(runId)).getByRole('button', { name: /Run \d/ }) as HTMLButtonElement;
}

async function expand(runId: string) {
  await act(async () => {
    fireEvent.click(headerOf(runId));
  });
}

/** A promise a test can settle by hand, so a response can be held open. */
function gate<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** PATCH calls, with the parsed body and the If-Match header of each. */
function patchLog() {
  const seen: { url: string; body: unknown; ifMatch: string | undefined }[] = [];
  return {
    seen,
    record(url: string, init?: RequestInit) {
      seen.push({
        url,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
        ifMatch: (init?.headers as Record<string, string> | undefined)?.['If-Match'],
      });
    },
  };
}

beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// 1 — Add Run
// ---------------------------------------------------------------------------

describe('Add Run', () => {
  it('creates a run through POST /runs and renders it, with focus on the new card', async () => {
    const created = runFixture({ id: 'RUNNEW', label: 'Run 1', version: 'rn.0', fields: {} });
    const calls = renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([]) },
      [`POST ${BASE}/runs`]: {
        status: 201,
        body: { run: created, experiment_version: '1.1' },
      },
    });

    await screen.findByRole('button', { name: /Add Run/ });
    expect(screen.getByText('No runs yet. Add one for the first set of conditions you measured.')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Add Run/ }));
    });

    // It rendered.
    await waitFor(() => expect(document.querySelector('[data-run-id="RUNNEW"]')).not.toBeNull());
    expect(within(cardFor('RUNNEW')).getByText('Run 1')).toBeInTheDocument();

    // It carried the EXPERIMENT's If-Match, not a run's.
    expect(calls).toContain(`POST ${BASE}/runs`);
    const stub = globalThis.fetch as unknown as { mock: { calls: [string, RequestInit][] } };
    const post = stub.mock.calls.find(([, init]) => init?.method === 'POST' && String(init?.body) === '{}');
    expect((post?.[1].headers as Record<string, string>)['If-Match']).toBe(`"${VERSION_FIELDS.version}"`);

    // Focus moved to the new card's header.
    expect(document.activeElement).toBe(headerOf('RUNNEW'));
  });

  it('surfaces a create refusal instead of silently doing nothing', async () => {
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([]) },
      [`POST ${BASE}/runs`]: { status: 412, body: { error: 'stale_write' } },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Add Run/ }));
    });
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/changed somewhere else/i);
    expect(document.querySelectorAll('[data-run-id]')).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// 2 — accordion semantics
// ---------------------------------------------------------------------------

describe('run card accordion semantics', () => {
  it('is a real accordion: button + aria-expanded + aria-controls over a labelled region', async () => {
    renderRecord({ [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) } });
    await screen.findByRole('button', { name: /Add Run/ });

    const header = headerOf('RUN' + 'AAA');
    expect(header.tagName).toBe('BUTTON');
    expect(header).toHaveAttribute('aria-expanded', 'false');
    const panelId = header.getAttribute('aria-controls');
    expect(panelId).toBeTruthy();
    // Collapsed: the panel is not in the document.
    expect(document.getElementById(panelId!)).toBeNull();

    await expand('RUNAAA');
    expect(header).toHaveAttribute('aria-expanded', 'true');
    const panel = document.getElementById(panelId!);
    expect(panel).not.toBeNull();
    expect(panel).toHaveAttribute('role', 'region');
    expect(panel).toHaveAttribute('aria-labelledby', header.id);

    // Every control in the panel has an accessible name.
    for (const label of ['Environment', 'Temperature (K)', 'Acquisition start']) {
      expect(within(panel as HTMLElement).getByLabelText(label)).toBeInTheDocument();
    }

    await expand('RUNAAA');
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(document.getElementById(panelId!)).toBeNull();
  });

  it('shows the inherited experiment values as inherited, and gives them no controls', async () => {
    renderRecord({ [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) } });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');

    const inherited = within(cardFor('RUNAAA')).getByRole('region', {
      name: 'Values inherited from the experiment',
    });
    expect(within(inherited).getByText('sample.material.name')).toBeInTheDocument();
    expect(within(inherited).getByText('Synthetic CuO powder')).toBeInTheDocument();
    expect(within(inherited).getAllByText('Inherited from Experiment').length).toBeGreaterThan(0);
    // Read-only by construction: no input, select or textarea lives in there.
    expect(inherited.querySelectorAll('input, select, textarea')).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// 3 — autosave
// ---------------------------------------------------------------------------

describe('autosave', () => {
  it('debounces rapid edits into exactly ONE PATCH', async () => {
    const log = patchLog();
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: (init) => {
        log.record(`${BASE}/runs/RUNAAA`, init);
        return { body: { run: { ...RUN_A, version: 'ra.1' } } };
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const temp = screen.getByLabelText('Temperature (K)');

    vi.useFakeTimers();
    for (const value of ['3', '30', '305']) {
      await act(async () => {
        fireEvent.change(temp, { target: { value } });
        // A keystroke every 100 ms — well inside the debounce window.
        await vi.advanceTimersByTimeAsync(100);
      });
    }
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });

    expect(log.seen).toHaveLength(1);
    expect(log.seen[0].body).toEqual({
      confirmed_by_user: true,
      fields: { 'context.temperature_K': 305 },
    });
    // The RUN's token, not the experiment's.
    expect(log.seen[0].ifMatch).toBe('"ra.0"');
  });

  it('says Saving… while the request is open and Saved ONLY after it resolves', async () => {
    const g = gate<void>();
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: async () => {
        await g.promise;
        return { body: { run: { ...RUN_A, version: 'ra.1' } } };
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');
    const temp = within(card).getByLabelText('Temperature (K)');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(temp, { target: { value: '305' } });
    });
    // Queued, not yet sent: the reader already has an unacknowledged edit.
    expect(within(card).getByText('Saving…')).toBeInTheDocument();
    expect(within(card).queryByText('Saved')).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    // In flight, response held open.
    expect(within(card).getByText('Saving…')).toBeInTheDocument();
    expect(within(card).queryByText('Saved')).toBeNull();

    // THE NEGATIVE CONTROL, in behaviour: no amount of TIME produces `Saved`.
    // Only the response can, and it has not arrived.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(within(card).queryByText('Saved')).toBeNull();
    expect(within(card).getByText('Saving…')).toBeInTheDocument();

    await act(async () => {
      g.resolve();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(within(card).getByText('Saved')).toBeInTheDocument();
    expect(within(card).queryByText('Saving…')).toBeNull();
  });

  it('renders `Saved` from exactly one place, inside the resolve handler', () => {
    // A STRUCTURAL guard beside the behavioural one above. The behavioural test
    // proves the current code does not lie; this proves a future edit cannot
    // introduce a SECOND place that sets it — an optimistic one, a timer one —
    // which is precisely the change the behavioural test would keep passing
    // through if the optimistic path happened to be slower than the mock.
    // Resolved from the vitest root (`apps/web`), not from `import.meta.url` —
    // the module URL is not a `file:` URL under the test transform.
    const source = readFileSync(resolve('src/lib/useRunAutosave.ts'), 'utf8');
    const occurrences = source.split("setStatus('saved')").length - 1;
    expect(occurrences).toBe(1);
    const at = source.indexOf("setStatus('saved')");
    const thenAt = source.indexOf('.then((res) => {');
    const catchAt = source.indexOf('.catch((err: unknown) => {');
    expect(thenAt).toBeGreaterThan(-1);
    expect(at).toBeGreaterThan(thenAt);
    expect(at).toBeLessThan(catchAt);
  });

  it('turns a 412 into Conflict — never Saved — and offers a refresh that adopts the server run', async () => {
    const refreshed = runFixture({
      id: 'RUNAAA',
      label: 'Run 1',
      version: 'ra.9',
      fields: {
        'context.environment': { value: 'operando', status: 'verified', evidence: [] },
        'context.temperature_K': { value: 500, status: 'verified', evidence: [] },
      },
    });
    let patches = 0;
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`GET ${BASE}/runs/RUNAAA`]: { body: { run: refreshed } },
      [`PATCH ${BASE}/runs/RUNAAA`]: () => {
        patches += 1;
        return {
          status: 412,
          body: { error: 'stale_write', current_version: 'ra.9', current_rev: 9 },
        };
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Temperature (K)'), { target: { value: '305' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });

    // Both the collapsed-header indicator and the live status region say it —
    // that is the conflict indicator the card is required to carry, so the
    // assertion is on the count and on the live region, not on uniqueness.
    expect(within(card).getAllByText('Conflict').length).toBe(2);
    expect(within(card).getByRole('status').textContent).toBe('Conflict');
    expect(within(card).queryByText('Saved')).toBeNull();
    expect(patches).toBe(1);

    // It does not retry a refusal, and it does not keep sending a stale token.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(patches).toBe(1);

    // Further typing is held, never sent, while the conflict stands.
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Temperature (K)'), { target: { value: '306' } });
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(patches).toBe(1);

    // The refresh adopts the SERVER's values, replacing what was typed.
    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: 'Refresh This Run' }));
      await vi.advanceTimersByTimeAsync(10);
    });
    expect((within(card).getByLabelText('Temperature (K)') as HTMLInputElement).value).toBe('500');
    expect((within(card).getByLabelText('Environment') as HTMLSelectElement).value).toBe('operando');
    expect(within(card).queryByText('Conflict')).toBeNull();
    expect(within(card).queryByText('Saved')).toBeNull();
  });

  it('turns a 500 into Save failed and retries with backoff', async () => {
    let patches = 0;
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: () => {
        patches += 1;
        return { status: 500, body: { error: 'boom' } };
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Temperature (K)'), { target: { value: '305' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    // Two places say it, exactly as `Conflict` does: the collapsed-header
    // indicator and the live region. The count is the assertion, not
    // uniqueness — the header one is what a reader who has collapsed the card
    // sees, and it is required to be there.
    expect(within(card).getAllByText('Save failed')).toHaveLength(2);
    expect(within(card).getByRole('status').textContent).toBe('Save failed');
    expect(within(card).queryByText('Saved')).toBeNull();
    expect(patches).toBe(1);

    // First backoff.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_RETRY_BASE_MS + 50);
    });
    expect(patches).toBe(2);

    // Second backoff is longer than the first — it does not hammer.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_RETRY_BASE_MS + 50);
    });
    expect(patches).toBe(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_RETRY_BASE_MS * 2);
    });
    expect(patches).toBe(3);

    // And it stops rather than retrying for ever.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600_000);
    });
    expect(patches).toBe(4);
    expect(within(card).getAllByText('Save failed')).toHaveLength(2);
  });

  it('does not retry a refusal that is not a 412', async () => {
    let patches = 0;
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: () => {
        patches += 1;
        return { status: 422, body: { error: 'not_run_level' } };
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Temperature (K)'), { target: { value: '305' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    expect(within(card).getAllByText('Save failed')).toHaveLength(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600_000);
    });
    expect(patches).toBe(1);
  });

  it('refuses to send a malformed value, and says which box and why', async () => {
    let patches = 0;
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: () => {
        patches += 1;
        return { body: { run: RUN_A } };
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');
    const temp = within(card).getByLabelText('Temperature (K)');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(temp, { target: { value: 'warm' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    expect(patches).toBe(0);
    expect(temp).toHaveAttribute('aria-invalid', 'true');
    expect(within(card).getByText('Enter a number.')).toBeInTheDocument();
  });

  it('announces the save status in a live region', async () => {
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: { body: { run: { ...RUN_A, version: 'ra.1' } } },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');
    const status = within(card).getByRole('status');
    expect(status.textContent).toBe('');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Temperature (K)'), { target: { value: '305' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    expect(status.textContent).toBe('Saved');
  });
});

// ---------------------------------------------------------------------------
// 4 — isolation
// ---------------------------------------------------------------------------

describe('two runs on one screen', () => {
  /*
   * THE SECOND RUN IS THE ONE THAT GETS EDITED, and that is the whole strength
   * of this test rather than an arbitrary choice.
   *
   * The first draft of it edited Run 1. A deliberate mutation of
   * `RunsSection.replaceRun` — replacing the run at INDEX 0 instead of the run
   * with the matching id — PASSED that version, because Run 1 is at index 0 and
   * the two behaviours are indistinguishable there. Driving Run 2 makes them
   * distinguishable: a by-position replacement writes Run 2's server response
   * into Run 1's slot, which the assertions below catch.
   */
  it('stay isolated: editing the SECOND run neither writes to nor re-renders the first', async () => {
    const log = patchLog();
    const savedB = {
      ...RUN_B,
      version: 'rb.1',
      fields: {
        ...RUN_B.fields,
        'context.temperature_K': { value: 78, status: 'verified', evidence: [] },
      },
    };
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A, RUN_B]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: (init) => {
        log.record('RUNAAA', init);
        return { body: { run: { ...RUN_A, version: 'ra.1' } } };
      },
      [`PATCH ${BASE}/runs/RUNBBB`]: (init) => {
        log.record('RUNBBB', init);
        return { body: { run: savedB } };
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    await expand('RUNBBB');

    expect((within(cardFor('RUNAAA')).getByLabelText('Temperature (K)') as HTMLInputElement).value).toBe('300');
    expect((within(cardFor('RUNBBB')).getByLabelText('Temperature (K)') as HTMLInputElement).value).toBe('77');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(within(cardFor('RUNBBB')).getByLabelText('Temperature (K)'), {
        target: { value: '78' },
      });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });

    // Exactly one write, and it went to Run 2 carrying RUN 2's token.
    expect(log.seen.map((c) => c.url)).toEqual(['RUNBBB']);
    expect(log.seen[0].ifMatch).toBe('"rb.0"');

    // Both cards are still there under their own ids — a by-position
    // replacement would have put Run 2's object in Run 1's slot.
    expect(document.querySelectorAll('[data-run-id="RUNAAA"]')).toHaveLength(1);
    expect(document.querySelectorAll('[data-run-id="RUNBBB"]')).toHaveLength(1);

    const a = cardFor('RUNAAA');
    const b = cardFor('RUNBBB');

    // Run 1's own values are untouched…
    expect(within(a).getByText('Run 1')).toBeInTheDocument();
    expect((within(a).getByLabelText('Temperature (K)') as HTMLInputElement).value).toBe('300');
    expect((within(a).getByLabelText('Environment') as HTMLSelectElement).value).toBe('in_situ');
    // …and Run 1 is not claiming anything about a save it did not make.
    expect(within(a).getByRole('status').textContent).toBe('');

    // Run 2 is, and it adopted the value the SERVER returned.
    expect(within(b).getByText('Run 2')).toBeInTheDocument();
    expect(within(b).getByRole('status').textContent).toBe('Saved');
    expect((within(b).getByLabelText('Temperature (K)') as HTMLInputElement).value).toBe('78');
    expect((within(b).getByLabelText('Environment') as HTMLSelectElement).value).toBe('ex_situ');
  });

  it('collapses and expands independently', async () => {
    renderRecord({ [`GET ${BASE}/runs`]: { body: runsBody([RUN_A, RUN_B]) } });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    expect(headerOf('RUNAAA')).toHaveAttribute('aria-expanded', 'true');
    expect(headerOf('RUNBBB')).toHaveAttribute('aria-expanded', 'false');
  });
});

// ---------------------------------------------------------------------------
// 5 — teardown
// ---------------------------------------------------------------------------

describe('leaving the screen mid-save', () => {
  it('flushes the pending edit, warns about nothing, and leaves no timer behind', async () => {
    const log = patchLog();
    const calls = stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: (init) => {
        log.record('RUNAAA', init);
        return { body: { run: { ...RUN_A, version: 'ra.1' } } };
      },
    });
    const view = render(
      <MemoryRouter
        initialEntries={[`/record/${ID}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');

    const warn = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(screen.getByLabelText('Temperature (K)'), { target: { value: '305' } });
      // Deliberately INSIDE the debounce window: nothing has been sent yet.
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(log.seen).toHaveLength(0);

    const before = calls.length;
    await act(async () => {
      view.unmount();
    });

    // The edit was flushed rather than dropped. The assertion is synchronous on
    // purpose: the flush issues its `fetch` inside the unmount, so if it were
    // deferred to some later tick this would fail rather than quietly wait.
    expect(log.seen).toHaveLength(1);
    expect(log.seen[0].body).toEqual({
      confirmed_by_user: true,
      fields: { 'context.temperature_K': 305 },
    });

    // …no timer survived the unmount…
    const after = calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600_000);
    });
    expect(calls.length).toBe(after);
    expect(after).toBeGreaterThan(before);

    // …and nothing was logged: no "state update on an unmounted component",
    // and no navigation-blocking prompt (there is no beforeunload handler to
    // fire, which is the point — a flush replaces a warning).
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  /*
   * THE CASE THE CONTROL ABOVE CANNOT REACH, and the reason it needs its own
   * test rather than an extra assertion on that one.
   *
   * The control unmounts with NOTHING in flight, so a teardown that flushes
   * only when the socket is idle passes it. The edit that gets destroyed is the
   * one typed AFTER a request has already left: `send` empties the pending map
   * before dispatching, so that edit is not in the open request's body, and the
   * resolve handler bails out on `!mounted` before it can schedule a second
   * one. Unmounting mid-flight is one click away — the Runs section lives in
   * the `fields` tabpanel, so switching to Graph unmounts every card.
   *
   * ONE CLICK REACHES IT, and it is silent: no message, no status, no request.
   */
  it('sends an edit typed WHILE a save was in flight, carrying the token that save returned', async () => {
    const log = patchLog();
    const g = gate<void>();
    stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: async (init) => {
        log.record('RUNAAA', init);
        // The FIRST request is held open; later ones answer immediately.
        if (log.seen.length === 1) await g.promise;
        return { body: { run: { ...RUN_A, version: `ra.${log.seen.length}` } } };
      },
    });
    const view = render(
      <MemoryRouter
        initialEntries={[`/record/${ID}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');
    const warn = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    vi.useFakeTimers();
    // Edit one leaves and is held open.
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Temperature (K)'), { target: { value: '305' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    expect(log.seen).toHaveLength(1);
    expect(log.seen[0].body).toEqual({
      confirmed_by_user: true,
      fields: { 'context.temperature_K': 305 },
    });
    expect(log.seen[0].ifMatch).toBe('"ra.0"');

    // Edit two is typed while that request is still open, so it is NOT in it.
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Environment'), { target: { value: 'operando' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    expect(within(card).getByRole('status').textContent).toBe('Saving…');
    expect(log.seen).toHaveLength(1);

    // The reader switches tab / leaves the screen.
    await act(async () => {
      view.unmount();
    });

    // Nothing can be sent YET: the token edit two must carry is the one the
    // open response is about to establish. Sending now would be a 412.
    expect(log.seen).toHaveLength(1);

    await act(async () => {
      g.resolve();
      await vi.advanceTimersByTimeAsync(0);
    });

    // It was sent, exactly once, with the NEW token — a flush that reused
    // `ra.0` would earn a 412 and lose the edit just as silently.
    expect(log.seen).toHaveLength(2);
    expect(log.seen[1].body).toEqual({
      confirmed_by_user: true,
      fields: { 'context.environment': 'operando' },
    });
    expect(log.seen[1].ifMatch).toBe('"ra.1"');

    // No further traffic and no timer left behind.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600_000);
    });
    expect(log.seen).toHaveLength(2);
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it('sends the edits an in-flight save FAILED with, rather than stranding them', async () => {
    const log = patchLog();
    const g = gate<void>();
    stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: async (init) => {
        log.record('RUNAAA', init);
        if (log.seen.length === 1) {
          await g.promise;
          return { status: 500, body: { error: 'boom' } };
        }
        return { body: { run: { ...RUN_A, version: 'ra.1' } } };
      },
    });
    const view = render(
      <MemoryRouter
        initialEntries={[`/record/${ID}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Temperature (K)'), { target: { value: '305' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Environment'), { target: { value: 'operando' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    expect(log.seen).toHaveLength(1);

    await act(async () => {
      view.unmount();
    });
    await act(async () => {
      g.resolve();
      await vi.advanceTimersByTimeAsync(0);
    });

    // BOTH edits go: the failed request's fields go back into the pending map
    // under anything newer, and the whole map is handed to the network once.
    // The token is unchanged — a 500 established no new version.
    expect(log.seen).toHaveLength(2);
    expect(log.seen[1].body).toEqual({
      confirmed_by_user: true,
      fields: { 'context.temperature_K': 305, 'context.environment': 'operando' },
    });
    expect(log.seen[1].ifMatch).toBe('"ra.0"');
  });

  it('sends NOTHING more after a 412, because every send would carry the refused token', async () => {
    const log = patchLog();
    const g = gate<void>();
    stubFetchRoutes({
      ...bundleRoutes(ID),
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`PATCH ${BASE}/runs/RUNAAA`]: async (init) => {
        log.record('RUNAAA', init);
        if (log.seen.length === 1) await g.promise;
        return { status: 412, body: { error: 'stale_write', current_version: 'ra.9' } };
      },
    });
    const view = render(
      <MemoryRouter
        initialEntries={[`/record/${ID}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Temperature (K)'), { target: { value: '305' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    await act(async () => {
      fireEvent.change(within(card).getByLabelText('Environment'), { target: { value: 'operando' } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    await act(async () => {
      view.unmount();
    });
    await act(async () => {
      g.resolve();
      await vi.advanceTimersByTimeAsync(600_000);
    });

    // The run moved on somewhere else. Replaying the held edits over the top of
    // whatever moved it is the silent overwrite this state exists to prevent.
    expect(log.seen).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// 5b — a refused save on a COLLAPSED card
// ---------------------------------------------------------------------------

/*
 * THE SECOND RUN IS THE ONE THAT FAILS, for the same reason section 4 edits the
 * second run: a card-level indicator hung off the wrong card, or off the list
 * rather than the card, is indistinguishable from a correct one when only one
 * card exists or when the edited card is at index 0.
 */
describe('a save refused while the card is collapsed', () => {
  async function failWhileCollapsed() {
    let patches = 0;
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A, RUN_B]) },
      [`PATCH ${BASE}/runs/RUNBBB`]: () => {
        patches += 1;
        // A considered refusal: not retried, so the state settles on `failed`.
        return { status: 422, body: { error: 'not_run_level' } };
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNBBB');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.change(within(cardFor('RUNBBB')).getByLabelText('Temperature (K)'), {
        target: { value: '78' },
      });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DEBOUNCE_MS + 50);
    });
    // Collapse it, the way a reader who has finished typing would.
    await act(async () => {
      fireEvent.click(headerOf('RUNBBB'));
    });
    expect(headerOf('RUNBBB')).toHaveAttribute('aria-expanded', 'false');
    return { patches: () => patches };
  }

  it('says so on the collapsed card, in words, on the right card', async () => {
    await failWhileCollapsed();
    const b = cardFor('RUNBBB');
    const a = cardFor('RUNAAA');

    // The refusal is on the card, in words, with the card collapsed. Both the
    // header indicator and the live region carry it — the same pairing the
    // `conflict` state already had.
    expect(within(b).getAllByText('Save failed')).toHaveLength(2);
    expect(within(b).getByRole('status').textContent).toBe('Save failed');
    expect(b.textContent ?? '').toMatch(/Save failed/);

    // Reaching the collapsed header by keyboard alone announces it: the words
    // are part of the header's accessible name, not a colour on a chip.
    expect(headerOf('RUNBBB')).toHaveAccessibleName(/Save failed/);
    // Both indicators are a glyph PLUS words, and the glyph is decorative — the
    // failure is never carried by colour or by a shape alone.
    for (const el of within(b).getAllByText('Save failed')) {
      const indicator = el.closest('.chip, .run-save-status') as HTMLElement;
      expect(indicator).not.toBeNull();
      expect(indicator.querySelectorAll('svg[aria-hidden="true"]').length).toBeGreaterThan(0);
      expect(indicator.textContent).toContain('Save failed');
    }

    // And the run that was NOT edited claims nothing.
    expect(within(a).queryByText('Save failed')).toBeNull();
    expect(within(a).getByRole('status').textContent).toBe('');
    expect(headerOf('RUNAAA')).not.toHaveAccessibleName(/Save failed/);
  });

  it('keeps Retry Save reachable without expanding the card first', async () => {
    const { patches } = await failWhileCollapsed();
    expect(patches()).toBe(1);
    const b = cardFor('RUNBBB');

    const retry = within(b).getByRole('button', { name: 'Retry Save' });
    await act(async () => {
      fireEvent.click(retry);
      await vi.advanceTimersByTimeAsync(50);
    });
    // It re-sent the held edit — the card is still collapsed.
    expect(patches()).toBe(2);
    expect(headerOf('RUNBBB')).toHaveAttribute('aria-expanded', 'false');
    // Run 1 was never written to.
    expect(within(cardFor('RUNAAA')).queryByRole('button', { name: 'Retry Save' })).toBeNull();
  });

  it('offers no Retry Save when there is nothing refused to retry', async () => {
    renderRecord({ [`GET ${BASE}/runs`]: { body: runsBody([RUN_A, RUN_B]) } });
    await screen.findByRole('button', { name: /Add Run/ });
    for (const id of ['RUNAAA', 'RUNBBB']) {
      expect(within(cardFor(id)).queryByRole('button', { name: 'Retry Save' })).toBeNull();
      // The live region exists before it has anything to say — a region added
      // to the DOM at the same moment it is populated is not reliably read.
      expect(within(cardFor(id)).getByRole('status').textContent).toBe('');
    }
  });
});

// ---------------------------------------------------------------------------
// 6 — Check Run
// ---------------------------------------------------------------------------

describe('Check Run', () => {
  it('renders the findings, mutates nothing, and claims nothing about export', async () => {
    const calls = renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`POST ${BASE}/runs/RUNAAA/check`]: {
        body: {
          ok: false,
          draft: { ok: false, errors: [{ path: 'context.temperature_K', message: 'no evidence' }] },
          official: { ok: false, errors: [{ path: 'timestamps', message: "'acquired_start_utc' is required" }] },
          blockers: ['Acquisition start is not recorded.'],
          checked_run_version: 'ra.0',
        },
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');

    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: 'Check Run' }));
    });

    const result = await within(card).findByRole('region', { name: 'Check result' });
    expect(within(result).getByText('Acquisition start is not recorded.')).toBeInTheDocument();
    expect(within(result).getByText('no evidence')).toBeInTheDocument();
    expect(within(result).getByText("'acquired_start_utc' is required")).toBeInTheDocument();
    expect(within(result).getByText(/Read-only check of run version ra\.0/)).toBeInTheDocument();

    // It never claims the record went anywhere.
    expect(result.textContent ?? '').toMatch(/Nothing was written, submitted or exported/);
    expect(result.textContent ?? '').not.toMatch(/submitted successfully|exported successfully/i);

    // And it mutated nothing: the only write-shaped call in the whole session is
    // the check itself.
    const writes = calls.filter(
      (c) => c.startsWith('PATCH ') || (c.startsWith('POST ') && !c.endsWith('/check')),
    );
    expect(writes.filter((c) => c.includes('/runs'))).toHaveLength(0);
    expect(calls.filter((c) => c === `POST ${BASE}/runs/RUNAAA/check`)).toHaveLength(1);
  });

  it('renders a finding it cannot describe rather than dropping it', async () => {
    renderRecord({
      [`GET ${BASE}/runs`]: { body: runsBody([RUN_A]) },
      [`POST ${BASE}/runs/RUNAAA/check`]: {
        body: {
          ok: false,
          draft: { ok: true },
          official: { ok: true },
          blockers: [{ code: 'SOMETHING_NEW' }],
          checked_run_version: 'ra.0',
        },
      },
    });
    await screen.findByRole('button', { name: /Add Run/ });
    await expand('RUNAAA');
    const card = cardFor('RUNAAA');
    await act(async () => {
      fireEvent.click(within(card).getByRole('button', { name: 'Check Run' }));
    });
    const result = await within(card).findByRole('region', { name: 'Check result' });
    expect(within(result).getByText('Blocking · 1')).toBeInTheDocument();
    expect(
      within(result).getByText('The server reported a finding this build cannot describe.'),
    ).toBeInTheDocument();
  });
});

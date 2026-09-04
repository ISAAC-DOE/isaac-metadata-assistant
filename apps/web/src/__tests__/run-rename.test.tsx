/*
 * RENAMING ONE RUN — a backend that had no control.
 *
 * ── What was measured ───────────────────────────────────────────────────────
 *
 * `PATCH /api/experiments/{id}/runs/{run_id}` has always documented itself as writing a
 * run's fields "and optionally renaming it", and `api.updateRun`'s body type has carried
 * `label?: string` for as long as it has existed. Measured before this slice: NEITHER
 * caller passed it — `lib/runAutosaveStore.ts` sends `{ fields }` and
 * `TranscriptCapturePanel` sends `{ fields }` — so the capability was reachable only by
 * a person writing the request by hand, and every run added through this screen kept the
 * server-assigned `Run N` for good.
 *
 * Measured over HTTP against a created record with one run:
 *
 *     {"confirmed_by_user": true, "fields": {}, "label": "300 K"}  -> 200, label changed
 *     label ""     -> 422 invalid_label      label "   " -> 422 invalid_label
 *     label 7      -> 422 invalid_label      no label, {} -> 422 unrecognized_field
 *     label of 500 characters                -> 200, stored verbatim (NO length limit)
 *
 * The last line is why this file asserts NO character-limit copy: the route declares
 * none, and stating one would be inventing a rule the server does not have. (The
 * experiment rename panel states one because `RenameExperimentRequest` declares
 * `max_length` — the two are deliberately different and must not be made to match.)
 *
 * ── The assertions that matter ──────────────────────────────────────────────
 *
 * That the request carries the RUN's `If-Match` and not the record's; that a blank is
 * refused before it is sent rather than after; and that a 412 is never presented as a
 * success and never silently retried with the server's newer token, which would apply a
 * name to a run whose current state the reader has not seen.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, configure, render, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { __resetRunAutosaveStore } from '../lib/runAutosaveStore';
import { bundleRoutes, runFixture, runsPage, stubFetchRoutes, type RouteEntry } from '../test/apiFixtures';

configure({ asyncUtilTimeout: 5_000 });
/* A HARNESS limit, not a performance claim — see `run-workspace.test.tsx:67-112`. */
vi.setConfig({ testTimeout: 30_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;
const RUN_ID = 'RUNAAA';
const RUN_VERSION = 'ra.1';

const RUN = runFixture({ id: RUN_ID, label: 'Run 1', version: RUN_VERSION, fields: {} });

function renderRecord(extra: Record<string, RouteEntry> = {}) {
  stubFetchRoutes({
    ...bundleRoutes(ID),
    [`GET ${BASE}/runs`]: { body: runsPage([RUN]) },
    ...extra,
  });
  render(
    <MemoryRouter
      initialEntries={[`/record/${ID}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

function card(): HTMLElement {
  const el = document.querySelector(`[data-run-id="${RUN_ID}"]`);
  if (!el) throw new Error(`no run card rendered for ${RUN_ID}`);
  return el as HTMLElement;
}

/** Mount, expand the run card, and open the rename section. */
async function openRename(): Promise<HTMLElement> {
  await screen.findByRole('button', { name: /Add Run/ });
  await act(async () => {
    // ANCHORED ON THE VERB, NOT THE LABEL (fix round, review finding m-8).
    // The compact row's own open control carries an `.sr-only` "Open " prefix
    // ahead of the run's label (I-3), so its accessible name begins
    // `Open Run 1 …` rather than `Run 1 …`. `.run-card-header` alone would
    // also match the FOCUSED editor's own heading once this run is open (it
    // is a plain `<h3 class="run-card-header run-card-header-static">`,
    // never a button — see `RunCard.tsx`'s m-2 note), so a raw class query
    // here could silently resolve to the wrong element on a re-render; role
    // + name pins it to the one `<button>` that exists before this click.
    fireEvent.click(within(card()).getByRole('button', { name: /^Open Run \d/ }));
  });
  await act(async () => {
    fireEvent.click(within(card()).getByRole('button', { name: /Name for this run/ }));
  });
  await act(async () => {
    fireEvent.click(within(card()).getByRole('button', { name: `Rename run Run 1` }));
  });
  return card();
}

beforeEach(() => {
  vi.useRealTimers();
  __resetRunAutosaveStore();
});

afterEach(() => {
  vi.restoreAllMocks();
  __resetRunAutosaveStore();
});

describe('the control that did not exist', () => {
  it('sends the label to PATCH /runs/{id} with the RUN’s If-Match', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    renderRecord({
      [`PATCH ${BASE}/runs/${RUN_ID}`]: {
        body: { run: { ...RUN, label: '300 K, in situ', version: 'ra.2', rev: 2 } },
      },
    });
    const originalFetch = globalThis.fetch;
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      calls.push({ url: String(input), init: init as RequestInit });
      return originalFetch(input as RequestInfo, init);
    });

    const el = await openRename();
    const input = within(el).getByLabelText('Run name') as HTMLInputElement;
    // Pre-filled with the current name, so a correction is an edit rather than a retype.
    expect(input.value).toBe('Run 1');

    await act(async () => {
      fireEvent.change(input, { target: { value: '300 K, in situ' } });
    });
    await act(async () => {
      fireEvent.click(within(el).getByRole('button', { name: 'Save name' }));
    });

    const write = calls.find((c) => c.init?.method === 'PATCH');
    expect(write, 'no PATCH was made').toBeTruthy();
    expect(JSON.parse(String(write!.init!.body))).toEqual({
      confirmed_by_user: true,
      fields: {},
      label: '300 K, in situ',
    });
    // THE RUN'S TOKEN. Sending the record's would be a 412 the reader would be told to
    // fix by refreshing something that was never stale — `api.updateRun`'s own trap.
    expect((write!.init!.headers as Record<string, string>)['If-Match']).toBe(`"${RUN_VERSION}"`);
  });

  it('adopts the renamed run the server returned, and says the rename landed', async () => {
    renderRecord({
      [`PATCH ${BASE}/runs/${RUN_ID}`]: {
        body: { run: { ...RUN, label: '300 K, in situ', version: 'ra.2', rev: 2 } },
      },
    });
    const el = await openRename();
    await act(async () => {
      fireEvent.change(within(el).getByLabelText('Run name'), {
        target: { value: '300 K, in situ' },
      });
    });
    await act(async () => {
      fireEvent.click(within(el).getByRole('button', { name: 'Save name' }));
    });

    await waitFor(() => {
      expect(card().querySelector('.run-card-name')?.textContent).toBe('300 K, in situ');
    });
    expect(card().querySelector('.run-rename-status')?.textContent).toContain('Run name saved.');
  });

  it('refuses a blank before sending it, and sends nothing', async () => {
    const calls: string[] = [];
    renderRecord();
    const originalFetch = globalThis.fetch;
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      if ((init as RequestInit | undefined)?.method === 'PATCH') calls.push(String(input));
      return originalFetch(input as RequestInfo, init);
    });

    const el = await openRename();
    await act(async () => {
      fireEvent.change(within(el).getByLabelText('Run name'), { target: { value: '   ' } });
    });
    await act(async () => {
      fireEvent.click(within(el).getByRole('button', { name: 'Save name' }));
    });

    expect(within(el).getByRole('alert').textContent).toContain('A run needs a name');
    expect(calls).toEqual([]);
  });

  it('never presents a stale write as a success, and never silently re-sends', async () => {
    const bodies: unknown[] = [];
    renderRecord({
      [`PATCH ${BASE}/runs/${RUN_ID}`]: {
        status: 412,
        body: { error: 'stale_write', current_version: 'ra.9' },
      },
    });
    const originalFetch = globalThis.fetch;
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      if ((init as RequestInit | undefined)?.method === 'PATCH') {
        bodies.push(JSON.parse(String((init as RequestInit).body)));
      }
      return originalFetch(input as RequestInfo, init);
    });

    const el = await openRename();
    await act(async () => {
      fireEvent.change(within(el).getByLabelText('Run name'), { target: { value: '300 K' } });
    });
    await act(async () => {
      fireEvent.click(within(el).getByRole('button', { name: 'Save name' }));
    });

    await waitFor(() => {
      expect(within(el).getByRole('alert').textContent).toMatch(/not saved and nothing was written/);
    });
    // ONE attempt. Re-sending with the server's `current_version` would apply a name to
    // a run whose current state the reader has not seen.
    expect(bodies).toHaveLength(1);
    // The card keeps its old name — the refusal is not painted as a rename.
    expect(card().querySelector('.run-card-name')?.textContent).toBe('Run 1');
    expect(card().querySelector('.run-rename-status')?.textContent ?? '').not.toContain('saved');
    // And the reader's text survives, so the retry is a retry and not a re-entry.
    expect((within(el).getByLabelText('Run name') as HTMLInputElement).value).toBe('300 K');
    // Save is withheld while the held token is still the rejected one — pressing it
    // again could only produce the same refusal.
    expect((within(el).getByRole('button', { name: 'Save name' }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it('states no character limit, because the route declares none', async () => {
    renderRecord();
    const el = await openRename();
    const section = el.querySelector('.run-rename') as HTMLElement;
    expect(section.textContent).not.toMatch(/\d+\s*characters?/);
    expect((within(el).getByLabelText('Run name') as HTMLInputElement).maxLength).toBe(-1);
  });

  it('names the run in the control’s accessible name, and keeps the visible word in it', async () => {
    /* Fifty cards each offering a control called "Rename" is fifty identically named
       controls in a screen reader's list — the same argument Focus, Compare and Remove
       already make on this card. WCAG 2.5.3 still holds because the accessible name
       CONTAINS the visible word. */
    renderRecord();
    await screen.findByRole('button', { name: /Add Run/ });
    await act(async () => {
      // Role + name, anchored on the verb — see `openRename`'s own note.
      fireEvent.click(within(card()).getByRole('button', { name: /^Open Run \d/ }));
    });
    await act(async () => {
      fireEvent.click(within(card()).getByRole('button', { name: /Name for this run/ }));
    });

    const trigger = within(card()).getByRole('button', { name: 'Rename run Run 1' });
    expect(trigger.getAttribute('aria-label')).toContain(trigger.textContent);
  });
});

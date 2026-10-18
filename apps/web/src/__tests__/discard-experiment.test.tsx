/*
 * B-08 / A-31 — THERE WAS NO DISCARD CONTROL.
 *
 * `POST /api/experiments/{id}/discard` shipped in `d93b896` with a full contract (which
 * records may be discarded, `confirmed_by_user`, a required `If-Match`, six typed 409
 * refusals, two typed 503s) and NOTHING in `apps/web` called it — while Settings
 * promised "Deliberate removal reaches … one unsubmitted, unexported record at a time".
 * A scientist who created a record by mistake owned it forever.
 *
 * WHAT WOULD FAIL BEFORE EACH BEHAVIOUR. These are the ways a discard control can be
 * built that renders fine and still loses work, lies, or traps the reader:
 *
 *   1. It exists but nothing mounts it — so it is asserted on the REAL screen.
 *   2. It destroys without asking, or asks without saying what goes.
 *   3. The destructive button takes focus on open (one Enter from data loss).
 *   4. It sends `If-Match: *` or no precondition — the route refuses both.
 *   5. A server refusal is replaced by generic copy, so "this was submitted" reads as
 *      "something went wrong". The server's OWN message is shown verbatim.
 *   6. A refusal also navigates away or closes the dialog, hiding the reason.
 *   7. A double-click sends two destructive requests.
 *   8. It is offered on a built-in example or an exported record, where it can only fail.
 *   9. Success leaves the reader on a record that no longer exists.
 *
 * Every fixture is synthetic; no test reaches a backend.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { DiscardExperimentPanel } from '../components/DiscardExperimentPanel';
import { AppRoutes } from '../App';
import { api, ApiError } from '../lib/api';
import { LABELS } from '../lib/labels';
import { appendMessage, loadSession } from '../lib/assistantSession';
import { EXAMPLE_RECORD_IDS } from '../lib/exampleRecords';
import {
  bundleRoutes,
  experimentDetail,
  experimentSummary,
  stubFetchRoutes,
} from '../test/apiFixtures';
import type { ApiExperimentDetail } from '../lib/types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;
const TITLE = 'Cu K-edge, mistaken duplicate';

function detail(over: Partial<ApiExperimentDetail> = {}): ApiExperimentDetail {
  return { ...experimentDetail, id: 'demo', title: TITLE, run_count: 2, ...over } as ApiExperimentDetail;
}

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="pathname">{loc.pathname}</div>;
}

/** The panel inside a router, with a probe, a place to go, and its section open. */
function renderPanel(props: Partial<Parameters<typeof DiscardExperimentPanel>[0]> = {}) {
  const onSaved = props.onSaved ?? vi.fn();
  const utils = render(
    <MemoryRouter initialEntries={['/record/demo']} future={FUTURE}>
      <Routes>
        <Route
          path="/record/:id"
          element={<DiscardExperimentPanel detail={props.detail ?? detail()} onSaved={onSaved} />}
        />
        <Route path="/experiments" element={<div>My Experiments stub</div>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: new RegExp(LABELS.discardSectionLabel) }));
  return { ...utils, onSaved };
}

function openDialog() {
  const opener = screen.getByRole('button', { name: LABELS.discardAction });
  fireEvent.click(opener);
  return { opener, dialog: screen.getByRole('alertdialog') };
}

const OK = {
  discarded_experiment_id: 'demo',
  discarded_title: TITLE,
  discarded_run_count: 2,
  durable_rows_removed: 0,
};

// =============================================================================
// the client method — what goes over the wire
// =============================================================================

describe('api.discardExperiment', () => {
  it('POSTs the confirmation and the record’s own validator, and never `*`', async () => {
    const calls = stubFetchRoutes({ 'POST /api/experiments/demo/discard': { body: OK } });
    await api.discardExperiment('demo', '1.0');
    expect(calls).toEqual(['POST /api/experiments/demo/discard']);
    const init = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock
      .calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ confirmed_by_user: true });
    expect((init.headers as Record<string, string>)['If-Match']).toBe('"1.0"');
  });

  it('a blank version sends NO If-Match, so the server names the missing precondition', async () => {
    stubFetchRoutes({ 'POST /api/experiments/demo/discard': { body: OK } });
    await api.discardExperiment('demo', '');
    const init = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock
      .calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string> | undefined)?.['If-Match']).toBeUndefined();
  });

  it('a 409 carries the server’s typed error and message on the ApiError', async () => {
    const refusal = { error: 'submitted', message: 'This record has been submitted. Nothing was removed.' };
    stubFetchRoutes({ 'POST /api/experiments/demo/discard': { status: 409, body: refusal } });
    const err = (await api.discardExperiment('demo', '1.0').catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.body).toEqual(refusal);
  });

  it('a 503 body is read too — it is a fact about the server and says nothing was removed', async () => {
    const body = { error: 'submission_history_unreadable', message: 'Could not read history. Nothing was removed.' };
    stubFetchRoutes({ 'POST /api/experiments/demo/discard': { status: 503, body } });
    const err = (await api.discardExperiment('demo', '1.0').catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(503);
    expect(err.reason).toBe('submission_history_unreadable');
    expect(err.body).toEqual(body);
  });
});

// =============================================================================
// 1. reachable on the real screen
// =============================================================================

describe('the control is reachable', () => {
  it('the record screen mounts it, collapsed on arrival', async () => {
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'GET /api/experiments/demo': { body: { ...experimentDetail, id: 'demo', title: TITLE } },
    });
    render(
      <MemoryRouter initialEntries={['/record/demo']} future={FUTURE}>
        <AppRoutes />
      </MemoryRouter>,
    );
    const header = await screen.findByRole('button', { name: new RegExp(LABELS.discardSectionLabel) });
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: LABELS.discardAction })).not.toBeInTheDocument();
    fireEvent.click(header);
    expect(await screen.findByRole('button', { name: LABELS.discardAction })).toBeInTheDocument();
  }, 20000);
});

// =============================================================================
// 2–3. the confirmation says what goes, and does not default to destroying
// =============================================================================

describe('the confirmation dialog', () => {
  it('is an alertdialog that names the record and says exactly what goes and that there is no undo', () => {
    renderPanel();
    const { dialog } = openDialog();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName(LABELS.discardDialogTitle);
    expect(dialog).toHaveTextContent(TITLE);
    expect(dialog).toHaveTextContent('2 runs');
    expect(dialog).toHaveTextContent(LABELS.discardWhatGoes);
    expect(LABELS.discardWhatGoes).toMatch(/its runs, its answers, its notes and its assets/);
    expect(LABELS.discardWhatGoes).toMatch(/no undo/i);
    // The description the dialog is announced with carries the same text.
    const described = document.getElementById(dialog.getAttribute('aria-describedby') ?? '');
    expect(described?.textContent).toContain(LABELS.discardWhatGoes);
  });

  it('sends nothing on open, and focus lands on the SAFE button, not the destructive one', () => {
    const calls = stubFetchRoutes({ 'POST /api/experiments/demo/discard': { body: OK } });
    renderPanel();
    openDialog();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: LABELS.discardKeep }));
    expect(calls).toEqual([]);
  });

  it('Keep, and Escape, close it without a request and return focus to the control that opened it', async () => {
    const calls = stubFetchRoutes({ 'POST /api/experiments/demo/discard': { body: OK } });
    renderPanel();
    let { opener } = openDialog();
    fireEvent.click(screen.getByRole('button', { name: LABELS.discardKeep }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(opener));

    ({ opener } = openDialog());
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(opener));
    expect(calls).toEqual([]);
  });

  it('Tab and Shift+Tab cannot leave the dialog', () => {
    renderPanel();
    openDialog();
    const keep = screen.getByRole('button', { name: LABELS.discardKeep });
    const discard = screen.getByRole('button', { name: LABELS.discardConfirm });
    discard.focus();
    fireEvent.keyDown(discard, { key: 'Tab' });
    expect(document.activeElement).toBe(keep);
    fireEvent.keyDown(keep, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(discard);
  });
});

// =============================================================================
// 9. success
// =============================================================================

describe('confirming', () => {
  it('discards with the record’s validator, clears its assistant conversation, and leaves the record', async () => {
    appendMessage('demo', { role: 'user', text: 'what is missing?' } as never);
    expect(loadSession('demo').messages.length).toBeGreaterThan(0);
    const calls = stubFetchRoutes({ 'POST /api/experiments/demo/discard': { body: OK } });
    renderPanel();
    openDialog();
    fireEvent.click(screen.getByRole('button', { name: LABELS.discardConfirm }));

    await waitFor(() => expect(screen.getByTestId('pathname').textContent).toBe('/experiments'));
    expect(calls).toEqual(['POST /api/experiments/demo/discard']);
    const init = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock
      .calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)['If-Match']).toBe(`"${experimentDetail.version}"`);
    expect(loadSession('demo').messages).toHaveLength(0);
  });

  it('a double-click sends ONE destructive request', async () => {
    const calls = stubFetchRoutes({ 'POST /api/experiments/demo/discard': { body: OK } });
    renderPanel();
    openDialog();
    const go = screen.getByRole('button', { name: LABELS.discardConfirm });
    fireEvent.click(go);
    fireEvent.click(go);
    await waitFor(() => expect(screen.getByTestId('pathname').textContent).toBe('/experiments'));
    expect(calls.filter((c) => c.startsWith('POST'))).toHaveLength(1);
  });

  it('hands the destination the title and run count, as router state', async () => {
    stubFetchRoutes({ 'POST /api/experiments/demo/discard': { body: OK } });
    let seen: unknown;
    function StateProbe() {
      seen = useLocation().state;
      return null;
    }
    render(
      <MemoryRouter initialEntries={['/record/demo']} future={FUTURE}>
        <Routes>
          <Route
            path="/record/:id"
            element={<DiscardExperimentPanel detail={detail()} onSaved={vi.fn()} />}
          />
          <Route path="/experiments" element={<div>My Experiments stub</div>} />
        </Routes>
        <StateProbe />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: new RegExp(LABELS.discardSectionLabel) }));
    fireEvent.click(screen.getByRole('button', { name: LABELS.discardAction }));
    fireEvent.click(screen.getByRole('button', { name: LABELS.discardConfirm }));
    await screen.findByText('My Experiments stub');
    expect(seen).toEqual({ discarded: { title: TITLE, runCount: 2 } });
  });
});

describe('My Experiments after a discard', () => {
  function renderHome(state: unknown) {
    stubFetchRoutes({
      'GET /api/experiments': { body: { experiments: [experimentSummary] } },
      'GET /api/health': { body: { mode: 'synthetic-only' } },
    });
    let latest: unknown = 'unset';
    function StateProbe() {
      latest = useLocation().state;
      return null;
    }
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/experiments', state }]}
        future={FUTURE}
      >
        <AppRoutes />
        <StateProbe />
      </MemoryRouter>,
    );
    return () => latest;
  }

  it('says what was discarded, in a live region, and replaces the router state so it is said once', async () => {
    const latest = renderHome({ discarded: { title: TITLE, runCount: 2 } });
    await waitFor(() => expect(document.querySelector('.discard-notice')).not.toBeNull());
    const notice = document.querySelector('.discard-notice') as HTMLElement;
    expect(notice).toHaveAttribute('role', 'status');
    expect(notice.textContent).toBe(`${LABELS.discardDoneBefore}${TITLE}${LABELS.discardDoneAfter}`);
    // The title is set as TEXT inside the sentence, never as markup.
    expect(notice.querySelector('strong')?.textContent).toBe(TITLE);
    await waitFor(() => expect(latest()).toBeNull());
    // …and still on screen after the state that carried it is gone.
    expect(document.querySelector('.discard-notice')).not.toBeNull();
  });

  it('moves focus to the notice so it is actually announced (it is not a tab stop)', async () => {
    renderHome({ discarded: { title: TITLE, runCount: 2 } });
    await waitFor(() => expect(document.querySelector('.discard-notice')).not.toBeNull());
    const notice = document.querySelector('.discard-notice') as HTMLElement;
    await waitFor(() => expect(document.activeElement).toBe(notice));
    expect(notice).toHaveAttribute('tabindex', '-1');
  });

  it('says nothing when it was reached any other way', async () => {
    renderHome(null);
    await waitFor(() => expect(document.querySelector('.exp-row')).not.toBeNull());
    expect(document.querySelector('.discard-notice')).toBeNull();
  });

  it('ignores router state that does not have the shape this screen wrote', async () => {
    renderHome({ discarded: { title: 42 } });
    await waitFor(() => expect(document.querySelector('.exp-row')).not.toBeNull());
    expect(document.querySelector('.discard-notice')).toBeNull();
  });
});

// =============================================================================
// 5–6. refusals: the server's own words, and the dialog stays
// =============================================================================

describe('a server refusal', () => {
  const REFUSALS: Array<[string, number, { error: string; message: string }]> = [
    ['submitted', 409, { error: 'submitted', message: 'This record has been submitted, so it cannot be discarded. Nothing was removed.' }],
    ['runs_exported', 409, { error: 'runs_exported', message: 'At least one run of this record has produced an official ISAAC record. Nothing was removed.' }],
    ['published_artifacts_present', 409, { error: 'published_artifacts_present', message: 'An official ISAAC record is present on disk under this experiment. Nothing was removed.' }],
    ['history unreadable (503)', 503, { error: 'submission_history_unreadable', message: 'This deployment could not read submission history just now. Nothing was removed.' }],
  ];

  for (const [name, status, body] of REFUSALS) {
    it(`${name}: shows the server's own message verbatim and keeps the dialog open`, async () => {
      stubFetchRoutes({ 'POST /api/experiments/demo/discard': { status, body } });
      renderPanel();
      const { dialog } = openDialog();
      fireEvent.click(screen.getByRole('button', { name: LABELS.discardConfirm }));
      const alert = await within(dialog).findByRole('alert');
      expect(alert.textContent).toBe(body.message);
      // Nothing navigated, and the dialog is still the way to keep the record.
      expect(screen.getByTestId('pathname').textContent).toBe('/record/demo');
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: LABELS.discardKeep })).toBeEnabled();
      // INVERTED (review): this asserted the destructive button live again after EVERY refusal. A 409 now turns it off (own test below); only the 503 leaves a retry meaningful.
    });
  }

  it('a 412 says nothing was removed, refreshes the record silently, and blocks a retry on the old token', async () => {
    stubFetchRoutes({
      'POST /api/experiments/demo/discard': {
        status: 412,
        body: { error: 'stale_write', current_version: '2.0' },
      },
    });
    const { onSaved } = renderPanel();
    openDialog();
    fireEvent.click(screen.getByRole('button', { name: LABELS.discardConfirm }));
    expect(await screen.findByText(LABELS.discardStale)).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: LABELS.discardConfirm })).toBeDisabled();
    expect(screen.getByTestId('pathname').textContent).toBe('/record/demo');
  });

  it('a record that changes while the dialog is OPEN makes it stale: the press must not confirm a view the reader never saw', async () => {
    const calls = stubFetchRoutes({ 'POST /api/experiments/demo/discard': { body: OK } });
    const view = renderPanel();
    openDialog();
    // the silent refresh lands a new version (a colleague renamed it / added a run)
    view.rerender(
      <MemoryRouter initialEntries={['/record/demo']} future={FUTURE}>
        <Routes>
          <Route
            path="/record/:id"
            element={<DiscardExperimentPanel detail={detail({ version: '2.0', title: 'Renamed by a colleague' })} onSaved={vi.fn()} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(LABELS.discardStale)).toBeInTheDocument();
    const go = screen.getByRole('button', { name: LABELS.discardConfirm });
    expect(go).toBeDisabled();
    fireEvent.click(go);
    expect(calls).toEqual([]);
  });

  it('a confirmation sends the version captured when the dialog OPENED', async () => {
    stubFetchRoutes({ 'POST /api/experiments/demo/discard': { body: OK } });
    renderPanel();
    openDialog();
    fireEvent.click(screen.getByRole('button', { name: LABELS.discardConfirm }));
    await waitFor(() => expect(screen.getByTestId('pathname').textContent).toBe('/experiments'));
    const init = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)['If-Match']).toBe(`"${experimentDetail.version}"`);
  });

  it('after a domain 409 the destructive button is OFF — a retry cannot succeed — and the reason stays', async () => {
    stubFetchRoutes({
      'POST /api/experiments/demo/discard': {
        status: 409,
        body: { error: 'submitted', message: 'This record has been submitted. Nothing was removed.' },
      },
    });
    renderPanel();
    const { dialog } = openDialog();
    fireEvent.click(screen.getByRole('button', { name: LABELS.discardConfirm }));
    await within(dialog).findByText('This record has been submitted. Nothing was removed.');
    expect(screen.getByRole('button', { name: LABELS.discardConfirm })).toBeDisabled();
    expect(screen.getByRole('button', { name: LABELS.discardKeep })).toBeEnabled();
  });

  it('a 404 says the record is already gone and offers a way back, rather than a retry', async () => {
    stubFetchRoutes({
      'POST /api/experiments/demo/discard': { status: 404, body: { error: 'experiment_not_found' } },
    });
    renderPanel();
    const { dialog } = openDialog();
    fireEvent.click(screen.getByRole('button', { name: LABELS.discardConfirm }));
    expect(await within(dialog).findByText(LABELS.discardGone, { exact: false })).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: LABELS.discardBackToExperiments })).toHaveAttribute(
      'href',
      '/experiments',
    );
    expect(screen.getByRole('button', { name: LABELS.discardConfirm })).toBeDisabled();
  });

  it('an unreachable backend claims NEITHER outcome — it cannot know whether the record went', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('connect ECONNREFUSED');
      }),
    );
    renderPanel();
    const { dialog } = openDialog();
    fireEvent.click(screen.getByRole('button', { name: LABELS.discardConfirm }));
    const alert = await within(dialog).findByRole('alert');
    expect(alert.textContent).toBe(LABELS.discardUnknownOutcome);
    expect(alert.textContent).not.toMatch(/nothing was removed/i);
  });
});

// =============================================================================
// 8. only offered where the server would allow it — or says why not
// =============================================================================

describe('where it is not offered', () => {
  it('a built-in worked example says why, and has no discard control', () => {
    renderPanel({ detail: detail({ id: EXAMPLE_RECORD_IDS[0] }) });
    expect(screen.queryByRole('button', { name: LABELS.discardAction })).not.toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent(LABELS.discardBlockedExample);
  });

  it('an exported record says why, and has no discard control', () => {
    renderPanel({ detail: detail({ exported: true, record_id: '01SYNTHREC' }) });
    expect(screen.queryByRole('button', { name: LABELS.discardAction })).not.toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent(LABELS.discardBlockedExported);
  });

  it('an ordinary unexported record is offered the control', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: LABELS.discardAction })).toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });
});

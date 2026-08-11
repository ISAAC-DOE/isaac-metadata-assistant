/*
 * MY EXPERIMENTS — "this list may be short", and the guard against saying so when
 * it is not.
 *
 * WHY THIS EXISTS. `GET /api/experiments` restores working copies from the
 * deployment's database before it enumerates them, and it DEGRADES rather than
 * fails when that restore does not finish — deliberately, because a reader with
 * three readable records should still see three. The cost of degrading is that a
 * short list is indistinguishable from a small workspace, so the server now says
 * when it may be short and this screen has to show it. A disclosure the UI drops
 * is the same defect as no disclosure at all.
 *
 * THE MODE THAT MAKES THIS NECESSARY. When the DATABASE is unreachable,
 * `/api/health` also reports it and the durability line on this very screen
 * changes. When the database ANSWERS and the restore fails anyway (a full
 * `emptyDir`), health correctly still reports `durable` — so this notice is the
 * only thing on the screen, or in the product, that says anything is wrong.
 *
 * FOUR PROPERTIES ARE PINNED:
 *   1. a whole list renders NO notice — a warning that is always on is noise;
 *   2. each degraded mode renders the SERVER's own sentence, not a rewrite;
 *   3. an unrecognised `reason` renders a true fallback heading rather than
 *      crashing on a direct-indexed lookup (`CHIP_META[...]` -> `undefined.label`);
 *   4. no count is ever rendered, in any state.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { __resetTutorialStore } from '../lib/tutorialController';
import { __resetHealthCache } from '../lib/useHealth';
import {
  aboutResponse,
  graphStatusUnavailable,
  healthSynthetic,
  openApiFixture,
  stubFetchRoutes,
} from '../test/apiFixtures';

afterEach(() => {
  vi.unstubAllGlobals();
  __resetTutorialStore();
  __resetHealthCache();
  sessionStorage.clear();
  localStorage.clear();
});

const DURABLE = { configured: true, backend: 'postgres', durable: true, state: 'durable' };
const UNAVAILABLE = {
  configured: true,
  backend: 'postgres',
  durable: false,
  state: 'unavailable',
};

/** The server's own fixed sentences, transcribed from `workspace.py`. */
const STORE_UNAVAILABLE_MESSAGE =
  'This deployment stores experiments in its own database, and that database could not be ' +
  'read just now, so this list shows only the working copies this server already had. ' +
  'Experiments stored durably may be missing from it. Nothing has been deleted, and this is ' +
  'usually temporary — try again.';
const RESTORE_FAILED_MESSAGE =
  'This deployment stores experiments in its own database, and this server could not finish ' +
  'restoring its own working copies of what is stored there, so this list may be missing ' +
  'experiments. Nothing has been deleted. Retrying may not clear this on its own — if the ' +
  'list stays short, it needs a server-side fix.';

const row = {
  id: '01KZ0READABLERECORD0000001',
  title: 'A record this read could see',
  status: 'needs_attention',
  created_utc: '2026-08-10T00:00:00Z',
  pending_count: 2,
  evidenced_field_count: 1,
  exported: false,
  record_id: null,
  scenario: null,
};

function routes(listBody: unknown, storage = DURABLE) {
  return {
    'GET /api/health': { body: { ...healthSynthetic, experiment_storage: storage } },
    'GET /api/experiments': { body: listBody },
    'GET /api/graph/status': { body: graphStatusUnavailable },
    'GET /api/about': { body: aboutResponse },
    'GET /api/openapi': { body: openApiFixture },
  };
}

function renderHome() {
  return render(
    <MemoryRouter
      initialEntries={['/experiments']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

function notice(): HTMLElement | null {
  return document.querySelector<HTMLElement>('.queue-incomplete');
}

describe('My Experiments · the list-completeness disclosure', () => {
  /*
   * THE GUARD FIRST, because it is the one a well-meaning change breaks. A notice
   * that renders on a healthy deployment trains every reader to ignore it, and it
   * would then be ignored in the one state it exists for.
   */
  it('renders NO notice when the server makes no completeness claim', async () => {
    stubFetchRoutes(routes({ experiments: [row] }) as never);
    renderHome();
    await screen.findByText(row.title);
    expect(notice()).toBeNull();
  });

  it('renders NO notice on a healthy EMPTY list either', async () => {
    // The empty state is where a spurious warning would do the most damage: it
    // would tell a reader with genuinely no experiments that some are missing.
    stubFetchRoutes(routes({ experiments: [] }) as never);
    renderHome();
    await screen.findByRole('heading', { name: LABELS.emptyExperimentsTitle });
    expect(notice()).toBeNull();
  });

  it('shows the server sentence, verbatim, when the DATABASE did not answer', async () => {
    stubFetchRoutes(
      routes(
        {
          experiments: [row],
          incomplete: {
            reason: 'store_unavailable',
            missing_count: null,
            message: STORE_UNAVAILABLE_MESSAGE,
          },
        },
        UNAVAILABLE,
      ) as never,
    );
    renderHome();
    const alert = await screen.findByRole('alert');

    expect(alert.className).toContain('queue-incomplete');
    expect(alert.getAttribute('data-reason')).toBe('store_unavailable');
    expect(alert.textContent).toContain('This list may be incomplete');
    expect(alert.textContent).toContain('the experiment database did not answer');
    // VERBATIM. Re-wording the server's sentence here risks claiming something the
    // backend did not — it is a fixed literal there for exactly that reason.
    expect(alert.textContent).toContain(STORE_UNAVAILABLE_MESSAGE);
    // The rows that DID arrive are still shown. Degrading visibly, not fatally.
    expect(screen.getByText(row.title)).toBeTruthy();
  });

  /*
   * THE MODE NOTHING ELSE DISCLOSES. `experiment_storage` is `durable` here — the
   * database is genuinely healthy — so every other honesty surface in the product
   * correctly says nothing is wrong. If this notice does not render, the reader
   * has no way at all to learn the list is short.
   */
  it('shows the notice when the database is HEALTHY and the restore failed', async () => {
    stubFetchRoutes(
      routes(
        {
          experiments: [],
          incomplete: {
            reason: 'restore_failed',
            missing_count: null,
            message: RESTORE_FAILED_MESSAGE,
          },
        },
        DURABLE,
      ) as never,
    );
    renderHome();
    const alert = await screen.findByRole('alert');

    expect(alert.getAttribute('data-reason')).toBe('restore_failed');
    expect(alert.textContent).toContain('restoring stored experiments did not finish');
    expect(alert.textContent).toContain(RESTORE_FAILED_MESSAGE);
    // The premise, asserted: nothing else on the screen is claiming a problem.
    expect(document.querySelector('.queue-empty-storage')?.textContent ?? '').not.toMatch(
      /not being stored|unavailable/i,
    );
  });

  /*
   * THE DIRECT-INDEX TRAP. `INCOMPLETE_HEADINGS[reason]` for a label this build
   * has never seen is `undefined`; rendering `undefined.label`-style output, or
   * an empty heading, on the app's primary screen — at the exact moment the
   * server is correctly reporting a NEW degraded mode — is the worst possible
   * failure. The fallback must be TRUE of any reason, so it names no cause.
   */
  it('falls back to a true heading for a reason this build has never seen', async () => {
    stubFetchRoutes(
      routes({
        experiments: [row],
        incomplete: {
          reason: 'invented_by_a_later_server',
          missing_count: null,
          message: 'Something this client cannot interpret happened.',
        },
      }) as never,
    );
    renderHome();
    const alert = await screen.findByRole('alert');

    expect(alert.textContent).toContain('This list may be incomplete');
    expect(alert.textContent).not.toContain('undefined');
    // It must NOT borrow either known cause — that would be a guess.
    expect(alert.textContent).not.toContain('database did not answer');
    expect(alert.textContent).not.toContain('did not finish');
    // The server's own sentence still renders, which is the only thing this
    // client actually knows about the cause.
    expect(alert.textContent).toContain('Something this client cannot interpret happened.');
    expect(screen.getByText(row.title)).toBeTruthy();
  });

  it('never renders a count, even when a server sends one', async () => {
    stubFetchRoutes(
      routes({
        experiments: [row],
        // A later server sending a number must not make this screen state one:
        // the contract says the figure is unknown, and rendering it would put an
        // invented total in front of a scientist.
        incomplete: {
          reason: 'restore_failed',
          missing_count: 12,
          message: RESTORE_FAILED_MESSAGE,
        },
      }) as never,
    );
    renderHome();
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).not.toContain('12');
  });

  it('a malformed incomplete block raises no notice at all', async () => {
    // An edge intercept, a proxy error page, a future shape — none of them is a
    // server SAYING the list is short, so none may warn a reader that it is.
    stubFetchRoutes(routes({ experiments: [row], incomplete: true }) as never);
    renderHome();
    await screen.findByText(row.title);
    expect(notice()).toBeNull();
  });

  it('Retry re-reads the list, and the notice goes when the server stops claiming it', async () => {
    let short = true;
    stubFetchRoutes({
      'GET /api/health': { body: { ...healthSynthetic, experiment_storage: DURABLE } },
      'GET /api/experiments': {
        body: () =>
          short
            ? {
                experiments: [],
                incomplete: {
                  reason: 'restore_failed',
                  missing_count: null,
                  message: RESTORE_FAILED_MESSAGE,
                },
              }
            : { experiments: [row] },
      },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/about': { body: aboutResponse },
      'GET /api/openapi': { body: openApiFixture },
    } as never);
    renderHome();
    await screen.findByRole('alert');

    short = false;
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => expect(notice()).toBeNull());
    expect(screen.getByText(row.title)).toBeTruthy();
  });
});

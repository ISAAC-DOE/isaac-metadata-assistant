/*
 * THE PRIMARY RECORD READ DECIDES WHETHER A RECORD SCREEN SAYS "NOT FOUND" —
 * found read-only on hosted (2026-09-23).
 *
 * `/record/<nonexistent id>` showed "ISAAC Returned an Error — … HTTP 503" instead of
 * "Record Not Found". Every read in the screen's bundle answered
 * `404 experiment_not_found` except one `GET …/evidence`, which answered 503 (a
 * backend race, fixed separately). Each bundle is one `Promise.all`, which rejects
 * with WHICHEVER read rejects first — so the 503 won the race and masked the answer
 * the record read itself gave.
 *
 * The rule pinned here: when the bundle fails, the PRIMARY read's outcome decides —
 * if `GET /api/experiments/{id}` failed, ITS error is the one the screen renders
 * (so a primary 404 reads "Record Not Found" however a secondary failed, and a
 * primary 503 reads as the error it is, never as "not found"). When the primary
 * read SUCCEEDED, a secondary failure is reported exactly as before.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { APP_TITLE } from '../lib/documentTitle';
import { api, primaryReadWins } from '../lib/api';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const ID = 'NOPE123';
const PRIMARY = `/api/experiments/${ID}`;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * The hosted network log, reproduced: `failFast` answers AT ONCE with its own status,
 * every other read answers LATER. So under a plain `Promise.all` the fast failure is
 * the one that wins the race.
 */
function stubRace(opts: {
  primary: { status: number; body: unknown };
  others: { status: number; body: unknown };
  failFast: { match: (path: string) => boolean; status: number; body: unknown };
}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, 'http://localhost').pathname;
      if (opts.failFast.match(path)) return json(opts.failFast.status, opts.failFast.body);
      await sleep(40);
      if (path === PRIMARY) return json(opts.primary.status, opts.primary.body);
      return json(opts.others.status, opts.others.body);
    }),
  );
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

const NOT_FOUND = { error: 'experiment_not_found' };
const UNAVAILABLE = { detail: 'this read is temporarily unavailable' };

describe('a primary 404 is "Record Not Found", whatever a secondary read did', () => {
  it.each([
    ['the record workbench', `/record/${ID}`, `${PRIMARY}/evidence`],
    ['Export Readiness', `/record/${ID}/export`, `${PRIMARY}/warnings`],
    ['Complete Metadata', `/record/${ID}/complete`, `${PRIMARY}/pending`],
    ['the Evidence Trail', `/record/${ID}/evidence`, `${PRIMARY}/evidence`],
  ])(
    'MUTATION-GUARDED — %s: primary 404 + one secondary 503 answering FIRST reads "Record Not Found"',
    async (_name, route, fastPath) => {
      stubRace({
        primary: { status: 404, body: NOT_FOUND },
        others: { status: 404, body: NOT_FOUND },
        failFast: { match: (path) => path === fastPath, status: 503, body: UNAVAILABLE },
      });
      renderAt(route);
      expect(await screen.findByRole('heading', { name: 'Record Not Found', level: 2 })).toBeTruthy();
      await waitFor(() => expect(document.title).toBe(`Record Not Found · ${APP_TITLE}`));
      expect(screen.queryByText('ISAAC Returned an Error')).toBeNull();
    },
  );
});

describe('a primary 503 is the error it is, never "Record Not Found"', () => {
  it('primary 503 + every other read 404 answering FIRST reads as an error, not as a missing record', async () => {
    stubRace({
      primary: { status: 503, body: UNAVAILABLE },
      others: { status: 404, body: NOT_FOUND },
      // Every secondary read fails fast with the not-found answer.
      failFast: { match: (path) => path !== PRIMARY, status: 404, body: NOT_FOUND },
    });
    renderAt(`/record/${ID}`);
    // The 503's own copy. This test runs as a LOCAL build, where `downCopy` titles a
    // 5xx "Backend Not Running"; the hosted build titles the same error "ISAAC
    // Returned an Error" (its `http_error` branch). Either way it is the PRIMARY
    // read's error — measured on the current code, a secondary 404 won the race and
    // this screen claimed "Record Not Found" about a record whose read had failed.
    expect(await screen.findByRole('heading', { name: 'Backend Not Running', level: 2 })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Record Not Found' })).toBeNull();
    expect(document.title).not.toMatch(/^Record Not Found/);
  });
});

describe('when the primary read SUCCEEDS, a secondary failure is reported as before', () => {
  it('the bundle rejects with the secondary’s own error', async () => {
    const detail = { experiment_id: ID, title: 'A synthetic record' };
    vi.spyOn(api, 'getExperiment').mockResolvedValue(detail as never);
    vi.spyOn(api, 'getPending').mockRejectedValue(new Error('pending read failed'));
    vi.spyOn(api, 'validate').mockResolvedValue({} as never);
    vi.spyOn(api, 'audit').mockResolvedValue({} as never);
    vi.spyOn(api, 'getWarnings').mockResolvedValue({} as never);
    vi.spyOn(api, 'getGraphStatus').mockResolvedValue({} as never);
    vi.spyOn(api, 'getArtifacts').mockResolvedValue({} as never);
    await expect(api.getExportReadiness(ID)).rejects.toThrow('pending read failed');
  });
});

describe('primaryReadWins itself', () => {
  const late = <T,>(value: T, ms = 20) => new Promise<T>((resolve) => setTimeout(() => resolve(value), ms));
  const lateReject = (reason: unknown, ms = 20) =>
    new Promise<never>((_resolve, reject) => setTimeout(() => reject(reason), ms));

  it('a primary that fails LATE still decides, over a secondary that failed first', async () => {
    const primary = lateReject(new Error('primary 404'));
    const secondary = Promise.reject(new Error('secondary 503'));
    await expect(primaryReadWins(primary, Promise.all([primary, secondary]))).rejects.toThrow(
      'primary 404',
    );
  });

  it('a primary that succeeds leaves the secondary’s own error in place', async () => {
    const primary = late('record');
    const secondary = Promise.reject(new Error('secondary 503'));
    await expect(primaryReadWins(primary, Promise.all([primary, secondary]))).rejects.toThrow(
      'secondary 503',
    );
  });

  it('with nothing failing it is exactly the bundle', async () => {
    const primary = late('record');
    await expect(primaryReadWins(primary, Promise.all([primary, late(2)]))).resolves.toEqual([
      'record',
      2,
    ]);
  });
});

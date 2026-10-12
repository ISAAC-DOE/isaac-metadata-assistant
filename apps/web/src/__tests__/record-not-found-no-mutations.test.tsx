/*
 * B-23 — A NONEXISTENT RECORD ID FIRED EIGHT REQUESTS, TWO OF THEM POSTS.
 *
 * Measured in Chromium on `/record/<id that does not exist>`: eight requests, including
 * `POST …/validate` and `POST …/audit`; Retry fired all eight again; the page had no way
 * back to My Experiments; and its `<h1>` read "Review Record" above a panel reading
 * "Record Not Found". Both POSTs are read-only checks, but a request that runs the export
 * gate over a record that does not exist is work the server should never be asked to do,
 * and every Retry repeated it.
 *
 * THE FIX IS ORDERING, NOT A SECOND REQUEST: the two POSTs are started only once the
 * PRIMARY read (`GET /experiments/{id}`) has resolved. A primary 404 — or any primary
 * failure — therefore issues none of them, and the primary-read-wins rule still decides
 * what the failure means. The cost is one primary round trip on the common path, before
 * the two slowest reads begin; it is disclosed at the call site.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { api } from '../lib/api';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const ID = 'NOPE123';
const NOT_FOUND = { error: 'experiment_not_found', id: ID };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** Every request this test's fetch received, as `METHOD /path`, in order. */
function stubMissingRecord(): string[] {
  const seen: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      seen.push(`${init?.method ?? 'GET'} ${new URL(url, 'http://localhost').pathname}`);
      return json(404, NOT_FOUND);
    }),
  );
  return seen;
}

const posts = (seen: string[]) => seen.filter((k) => k.startsWith('POST '));

describe('B-23 · a missing record issues no POST', () => {
  it.each([
    ['getRecordBundle', () => api.getRecordBundle(ID)],
    ['getExportReadiness', () => api.getExportReadiness(ID)],
    ['getExperimentGraphBundle', () => api.getExperimentGraphBundle(ID)],
  ])('MUTATION-GUARDED — %s: a primary 404 starts neither validate nor audit', async (_name, read) => {
    const seen = stubMissingRecord();
    await expect(read()).rejects.toMatchObject({ status: 404 });
    expect(posts(seen)).toEqual([]);
    // …and the primary read really was made, so this is not an empty-suite pass.
    expect(seen).toContain(`GET /api/experiments/${ID}`);
  });

  it('a primary that FAILS for any other reason starts neither POST either', async () => {
    const seen: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        seen.push(`${init?.method ?? 'GET'} ${new URL(url, 'http://localhost').pathname}`);
        return json(503, { detail: 'unavailable' });
      }),
    );
    await expect(api.getRecordBundle(ID)).rejects.toMatchObject({ status: 503 });
    expect(posts(seen)).toEqual([]);
  });

  it('when the primary SUCCEEDS both POSTs are made, exactly once each, AFTER it answered', async () => {
    const order: string[] = [];
    vi.spyOn(api, 'getExperiment').mockImplementation(async () => {
      order.push('primary:start');
      await new Promise((r) => setTimeout(r, 15));
      order.push('primary:end');
      return { id: ID } as never;
    });
    vi.spyOn(api, 'validate').mockImplementation(async () => {
      order.push('validate');
      return {} as never;
    });
    vi.spyOn(api, 'audit').mockImplementation(async () => {
      order.push('audit');
      return {} as never;
    });
    vi.spyOn(api, 'getDraftGroups').mockResolvedValue({} as never);
    vi.spyOn(api, 'getPending').mockResolvedValue([] as never);
    vi.spyOn(api, 'getWarnings').mockResolvedValue({} as never);
    vi.spyOn(api, 'getEvidence').mockResolvedValue({} as never);
    vi.spyOn(api, 'getGraphStatus').mockResolvedValue({} as never);
    vi.spyOn(api, 'getArtifacts').mockResolvedValue({} as never);

    const bundle = await api.getRecordBundle(ID);
    expect(bundle.detail).toEqual({ id: ID });
    expect(order.filter((o) => o === 'validate')).toHaveLength(1);
    expect(order.filter((o) => o === 'audit')).toHaveLength(1);
    const end = order.indexOf('primary:end');
    expect(order.indexOf('validate')).toBeGreaterThan(end);
    expect(order.indexOf('audit')).toBeGreaterThan(end);
  });
});

describe('B-23 · the screen for a missing record', () => {
  function renderAt(path: string) {
    return render(
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
  }

  it('its page heading says "Record Not Found", not "Review Record"', async () => {
    stubMissingRecord();
    renderAt(`/record/${ID}`);
    const h1 = await screen.findByRole('heading', { level: 1, name: 'Record Not Found' });
    expect(h1).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 1, name: 'Review Record' })).toBeNull();
  });

  it('offers a link back to My Experiments', async () => {
    stubMissingRecord();
    renderAt(`/record/${ID}`);
    const alert = await screen.findByRole('alert');
    const link = within(alert).getByRole('link', { name: 'My Experiments' });
    expect(link).toHaveAttribute('href', '/experiments');
  });

  it('Retry repeats the reads but never a POST', async () => {
    const seen = stubMissingRecord();
    renderAt(`/record/${ID}`);
    await screen.findByRole('heading', { level: 2, name: 'Record Not Found' });
    const before = seen.length;
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(seen.length).toBeGreaterThan(before));
    expect(posts(seen)).toEqual([]);
  });

  it('a record that is NOT absent keeps its own page heading on a non-404 error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(503, { detail: 'unavailable' })),
    );
    renderAt(`/record/${ID}`);
    await screen.findByRole('alert');
    expect(await screen.findByRole('heading', { level: 1, name: 'Review Record' })).toBeInTheDocument();
  });
});

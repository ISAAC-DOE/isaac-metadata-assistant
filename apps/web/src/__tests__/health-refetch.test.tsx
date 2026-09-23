/*
 * `refetchHealth` — the re-read a person asks for with "Reload" beside a capability
 * the server reported unavailable (owner QA P2, 2026-09-22: the proposals panel's
 * acceptance notice).
 *
 * What is pinned: the shared, cached health read is still ONE request for a session
 * until someone asks again; asking again issues exactly one new request; and every
 * mounted `useHealthState` consumer sees the new answer — so a "Reload" that found
 * acceptance enabled unlocks the Accept controls without a page reload. A failed
 * re-read resolves to `undefined`, exactly as the first read does, and never throws.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { __resetHealthCache, refetchHealth, useHealthState } from '../lib/useHealth';
import { healthSynthetic, stubFetchRoutes } from '../test/apiFixtures';

beforeEach(() => {
  __resetHealthCache();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function Probe() {
  const { settled, health } = useHealthState();
  const acceptance = health?.proposal_acceptance;
  return (
    <p data-testid="probe">
      {!settled
        ? 'loading'
        : acceptance === undefined
          ? 'absent'
          : acceptance.available
            ? 'available'
            : `unavailable:${acceptance.reason}`}
    </p>
  );
}

describe('refetchHealth', () => {
  it('re-reads once and every consumer sees the new answer', async () => {
    let reads = 0;
    stubFetchRoutes({
      'GET /api/health': () => {
        reads += 1;
        return {
          body: {
            ...healthSynthetic,
            proposal_acceptance:
              reads === 1
                ? { available: false, reason: 'no_verifier_configured' }
                : { available: true, reason: null },
          },
        };
      },
    });
    render(
      <>
        <Probe />
        <Probe />
      </>,
    );
    await waitFor(() =>
      expect(screen.getAllByTestId('probe').map((p) => p.textContent)).toEqual([
        'unavailable:no_verifier_configured',
        'unavailable:no_verifier_configured',
      ]),
    );
    // ONE request for two consumers — the cache is unchanged by this slice.
    expect(reads).toBe(1);

    await act(async () => {
      await refetchHealth();
    });
    expect(reads).toBe(2);
    await waitFor(() =>
      expect(screen.getAllByTestId('probe').map((p) => p.textContent)).toEqual([
        'available',
        'available',
      ]),
    );
  });

  it('a failed re-read resolves to undefined rather than throwing', async () => {
    let reads = 0;
    stubFetchRoutes({
      'GET /api/health': () => {
        reads += 1;
        return reads === 1
          ? { body: { ...healthSynthetic, proposal_acceptance: { available: true, reason: null } } }
          : { status: 503, body: { error: 'down' } };
      },
    });
    render(<Probe />);
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('available'));
    let result: unknown = 'unset';
    await act(async () => {
      result = await refetchHealth();
    });
    expect(result).toBeUndefined();
    // The consumer is told too — an absent block, never a stale "available".
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('absent'));
  });
});

describe('a re-read that answers BEFORE the first read (PR #277 review, minor)', () => {
  it('MUTATION-GUARDED: the late first read does not overwrite the newer answer', async () => {
    let releaseFirst: (() => void) | null = null;
    let reads = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        reads += 1;
        const body =
          reads === 1
            ? { ...healthSynthetic, proposal_acceptance: { available: false, reason: 'no_verifier_configured' } }
            : { ...healthSynthetic, proposal_acceptance: { available: true, reason: null } };
        if (reads === 1) {
          // Hold the FIRST read open until the re-read has answered.
          await new Promise<void>((resolve) => {
            releaseFirst = resolve;
          });
        }
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        });
      }),
    );
    render(<Probe />);
    expect(screen.getByTestId('probe').textContent).toBe('loading');
    await act(async () => {
      await refetchHealth();
    });
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('available'));
    // Now the stale first read lands.
    await act(async () => {
      (releaseFirst as unknown as () => void)();
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(screen.getByTestId('probe').textContent).toBe('available');
    expect(reads).toBe(2);
  });
});

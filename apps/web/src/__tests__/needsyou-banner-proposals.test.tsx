/*
 * THE "N FIELDS NEED YOUR CONFIRMATION" BANNER, AND THE PROPOSALS IT USED TO IGNORE
 * — QA C-24 (2026-10-12). With proposals waiting, the shell-level banner listed only
 * the record's open questions, so the one thing on the screen telling a scientist
 * "this needs you" said nothing about the queue of values waiting for their judgement.
 *
 * THE COUNT IS THE SERVER'S `capture_summary.proposals_open`, counted over the whole
 * record (`ApiCaptureSummary`); nothing here counts a fetched array. Zero proposals
 * says nothing, and the Proposals view — where the queue already is — says nothing.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { AppRoutes } from '../App';
import { bundleRoutes, captureDetail, stubFetchRoutes } from '../test/apiFixtures';

// A whole record screen per test: the same raised budgets every mount-heavy suite here
// uses (see `run-workspace.test.tsx` for the measurement) — a ceiling, not a delay.
configure({ asyncUtilTimeout: 5_000 });
vi.setConfig({ testTimeout: 30_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

function Address() {
  const loc = useLocation();
  return <span data-testid="address">{`${loc.pathname}${loc.search}`}</span>;
}

function renderAt(path: string, proposalsOpen: number) {
  stubFetchRoutes({
    ...bundleRoutes(ID),
    [`GET ${BASE}`]: { body: { ...captureDetail({ proposals_open: proposalsOpen }), id: ID } },
  } as never);
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Address />
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the needs-you banner names waiting proposals (QA C-24)', () => {
  it('says how many proposals wait, from the server’s count, and opens Proposals', async () => {
    renderAt(`/record/${ID}`, 2);
    await screen.findByText(/Fields Need Your Confirmation/);
    const line = await screen.findByText(/2 proposals are waiting for your review/);
    expect(line.closest('.needsyou-banner')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Review Proposals' }));
    await waitFor(() =>
      expect(screen.getByTestId('address').textContent).toContain('view=proposals'),
    );
  });

  it('one proposal is singular', async () => {
    renderAt(`/record/${ID}`, 1);
    await screen.findByText(/1 proposal is waiting for your review/);
  });

  it('says nothing about proposals when none are open', async () => {
    renderAt(`/record/${ID}`, 0);
    await screen.findByText(/Fields Need Your Confirmation/);
    expect(screen.queryByText(/waiting for your review/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Review Proposals' })).toBeNull();
  });

  it('is not repeated on the Proposals view, where the queue already is', async () => {
    renderAt(`/record/${ID}?view=proposals`, 2);
    const title = await screen.findByText(/Fields Need Your Confirmation/);
    const banner = title.closest('.needsyou-banner') as HTMLElement;
    expect(banner.textContent).not.toMatch(/waiting for your review/);
    expect(banner.querySelector('.needsyou-proposals')).toBeNull();
  });
});

/*
 * Export Readiness reads BLOCKERS FIRST, one banner for one fact, and advisories once
 * (review #277, I-7). Every fixture is synthetic; nothing here reaches a backend.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { bundleRoutes, stubFetchRoutes } from '../test/apiFixtures';

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

afterEach(() => vi.unstubAllGlobals());

describe('Export Readiness, while fields still block export', () => {
  it('shows ONE banner and ONE call to action for the blocked fields', async () => {
    stubFetchRoutes(bundleRoutes('demo')); // 5 pending, dry-run fails
    const { findByText, container } = renderAt('/record/demo/export');
    await findByText('5 fields still block export');
    // The workflow banner's "N items need your attention" was the same fact twice.
    expect(container.textContent).not.toMatch(/items? need(s)? your attention/i);
    expect(container.querySelectorAll('.preexport-gate')).toHaveLength(1);
  });

  it('lists what blocks export INSIDE the gate, ahead of the advisory card', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo/export');
    await findByText('5 fields still block export');
    const gate = container.querySelector('.preexport-gate') as HTMLElement;
    await waitFor(() => expect(gate.querySelectorAll('.blocker-item').length).toBeGreaterThan(0));
    // The validator's own sentence, verbatim.
    expect(gate.textContent).toMatch(/assets is a required property/);
    const advisory = container.querySelector('.advisory') as HTMLElement;
    expect(
      gate.compareDocumentPosition(advisory) & Node.DOCUMENT_POSITION_FOLLOWING,
      'the advisory card comes AFTER the blockers',
    ).toBeTruthy();
  });

  it('an advisory reads as a plain sentence, the code one `?` away', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo/export');
    await findByText('5 fields still block export');
    const item = container.querySelector('.advisory .advisory-item-title') as HTMLElement;
    expect(item).not.toBeNull();
    // The visible sentence carries no code and no backticks…
    const visible = Array.from(item.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent)
      .join('');
    expect(visible).not.toMatch(/`|\[[A-Z_]+\]/);
    // …and the code is still in the tip, for a curator.
    const code = item.querySelector('.helptip-panel code');
    expect(code?.textContent).toMatch(/^\[[A-Z_]+\]$/);
  });
});

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { bundleRoutes, stubFetchRoutes } from '../test/apiFixtures';

/*
 * P33 Human-QA #5 — on an ordinary initial record-workbench load, EVERY metadata
 * group starts collapsed (a calm entry, not a wall of fields). Expanding a group
 * works; multiple may be open at once (NOT a one-open-at-a-time accordion); and a
 * user-expanded group must NOT collapse because of an unrelated assistant
 * interaction. Missing-field / workflow computation is unaffected (the banner
 * still reports the same count).
 */

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('P33 HQA#5 — metadata groups default to collapsed', () => {
  it('every group header is collapsed (aria-expanded=false) on initial load', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    const headers = Array.from(container.querySelectorAll('.fg-header'));
    expect(headers.length).toBeGreaterThanOrEqual(2);
    for (const h of headers) {
      expect(h.getAttribute('aria-expanded')).toBe('false');
    }
    // no group body is rendered while all are collapsed
    expect(container.querySelector('.fg-body')).toBeNull();
  });

  it('expanding a group works and does not collapse the others (not an accordion)', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    const headers = Array.from(container.querySelectorAll('.fg-header')) as HTMLButtonElement[];
    fireEvent.click(headers[0]);
    expect(headers[0].getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(headers[1]);
    // first stays open — independent per-group toggles
    expect(headers[0].getAttribute('aria-expanded')).toBe('true');
    expect(headers[1].getAttribute('aria-expanded')).toBe('true');
  });

  it('a user-expanded group survives an assistant interaction (no reset)', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, container } = renderAt('/record/demo');
    await findByText('5 Fields Need Your Confirmation');
    const headers = Array.from(container.querySelectorAll('.fg-header')) as HTMLButtonElement[];
    fireEvent.click(headers[0]);
    expect(headers[0].getAttribute('aria-expanded')).toBe('true');

    // interact with the assistant rail: click a suggested question pill
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const pill = within(assistant).getAllByRole('button').find((b) => b.className.includes('assistant-prompt'));
    if (pill) fireEvent.click(pill);

    // the manually-expanded group is unchanged by the assistant interaction
    const after = Array.from(container.querySelectorAll('.fg-header')) as HTMLButtonElement[];
    expect(after[0].getAttribute('aria-expanded')).toBe('true');
  });
});

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TopBar } from '../components/TopBar';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  graphStatusAvailable,
  memoryConceptsAvailable,
  memoryFilesAvailable,
  searchRoutes,
  stubFetchRoutes,
} from '../test/apiFixtures';

function renderTopBar() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TopBar variant="home" />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/*
 * P22D — remove fake/noop UI, make Help real.
 *  - Help is a real, working, honest popover (Decision 2)
 *  - the fake "Ada Lovelace · SSRL" user chip is gone (Decision 3)
 *  - Project Memory never claims a hardcoded "fresh" status (Decision 4)
 *
 * P26 supersedes P22D Decision 1: the decorative "⌘K" promise that P22D deleted
 * has been replaced by a REAL, API-backed, keyboard-driven search command
 * palette (SearchDialog). The old "no search" invariant is therefore RETIRED and
 * replaced below by a functional-search assertion. The anti-fake principle is
 * preserved intact: the affordance must be PRESENT *and* open a real dialog that
 * queries the backend — never a dead decorative input.
 */
describe('P26 · TopBar search affordance is real and functional', () => {
  it('renders the search landmark, the .topbar-search trigger, and a ⌘K hint', () => {
    const { container, getByText, getByRole } = renderTopBar();
    expect(container.querySelector('[role="search"]')).not.toBeNull();
    expect(container.querySelector('.topbar-search')).not.toBeNull();
    expect(getByText(/⌘K/)).toBeInTheDocument();
    expect(getByRole('button', { name: /search/i })).toBeInTheDocument();
  });

  it('opens a real, backend-querying search dialog (not a dead decorative input)', async () => {
    stubFetchRoutes(searchRoutes());
    const view = renderTopBar();
    fireEvent.click(view.getByRole('button', { name: /search/i }));

    const dialog = await view.findByRole('dialog');
    const box = within(dialog).getByRole('searchbox');
    expect(box).toBeInTheDocument();

    // Typing drives a real query and renders the server-supplied Workspace group.
    fireEvent.change(box, { target: { value: 'xanes' } });
    expect(await within(dialog).findByText(/workspace/i)).toBeInTheDocument();
  });
});

describe('P22D · TopBar has no fake user identity', () => {
  it('renders no fake user identity chip', () => {
    const { queryByText, container } = renderTopBar();
    expect(queryByText(/Ada Lovelace/)).toBeNull();
    expect(container.querySelector('.account')).toBeNull();
    expect(container.querySelector('.avatar')).toBeNull();
  });
});

describe('P22D · Help is a real, working popover', () => {
  it('is closed by default and opens a labeled dialog on click', () => {
    const { getByRole, queryByRole } = renderTopBar();
    expect(queryByRole('dialog')).toBeNull();

    const helpButton = getByRole('button', { name: 'Help' });
    expect(helpButton.getAttribute('aria-haspopup')).toBe('dialog');
    expect(helpButton.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(helpButton);

    const dialog = getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog.getAttribute('aria-labelledby')).toBeTruthy();
    expect(helpButton.getAttribute('aria-expanded')).toBe('true');
  });

  it('content explains the no-guessing policy and separates validation from advisory', () => {
    const { getByRole, getByText } = renderTopBar();
    fireEvent.click(getByRole('button', { name: 'Help' }));

    expect(getByText(/filled only from evidence or your explicit confirmation/i)).toBeInTheDocument();
    expect(getByText(/"I don't know" is always a safe answer/)).toBeInTheDocument();
    expect(getByText(/the only signal that gates export/i)).toBeInTheDocument();
    expect(getByText(/never blocks or authorizes anything/i)).toBeInTheDocument();
    // Was `/synthetic demo data only/i`, from the sentence "This prototype runs
    // on synthetic demo data only — no real experiment data." That was a flat
    // guarantee the app cannot make: it enforces the runtime MODE, and there is
    // no real-vs-synthetic detector anywhere in the backend. Help now says what
    // the code actually does, and this assertion pins both halves.
    expect(
      getByText(/configured for synthetic-only operation/i),
    ).toBeInTheDocument();
    expect(
      getByText(/not the contents of what it is handed/i),
    ).toBeInTheDocument();
  });

  it('closes on Escape and returns focus to the Help button', () => {
    const { getByRole, queryByRole } = renderTopBar();
    const helpButton = getByRole('button', { name: 'Help' });
    fireEvent.click(helpButton);
    expect(getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(queryByRole('dialog')).toBeNull();
    expect(helpButton.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(helpButton);
  });

  it('closes on click outside the panel', () => {
    const { getByRole, queryByRole } = renderTopBar();
    fireEvent.click(getByRole('button', { name: 'Help' }));
    expect(getByRole('dialog')).toBeInTheDocument();

    fireEvent.mouseDown(document.body);

    expect(queryByRole('dialog')).toBeNull();
  });

  it('closes via the explicit close button', () => {
    const { getByRole, queryByRole } = renderTopBar();
    const helpButton = getByRole('button', { name: 'Help' });
    fireEvent.click(helpButton);

    fireEvent.click(getByRole('button', { name: 'Close help' }));

    expect(queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(helpButton);
  });
});

describe('P22D · Project Memory never fabricates a freshness claim', () => {
  it('renders the real graph status from the endpoint, not a hardcoded "fresh" string', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusAvailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
    });
    const { findByText, container } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ProjectMemory />
      </MemoryRouter>,
    );
    await findByText('Memory Available');
    expect(container.textContent).not.toMatch(/project memory: fresh/i);
  });

  it('degrades honestly when the backend is unreachable — never implies freshness', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('connect ECONNREFUSED 127.0.0.1:8000');
      }),
    );
    const { findByText, container } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ProjectMemory />
      </MemoryRouter>,
    );
    await findByText('Backend Not Running');
    expect(container.textContent).not.toMatch(/project memory: fresh/i);
  });
});

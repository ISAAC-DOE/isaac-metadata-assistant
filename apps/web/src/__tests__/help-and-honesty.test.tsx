import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TopBar } from '../components/TopBar';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  graphStatusAvailable,
  memoryConceptsAvailable,
  memoryFilesAvailable,
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
 *  - the decorative search + the "⌘K" promise are gone (Decision 1)
 *  - Help is a real, working, honest popover (Decision 2)
 *  - the fake "Ada Lovelace · SSRL" user chip is gone (Decision 3)
 *  - Project Memory never claims a hardcoded "fresh" status (Decision 4)
 */
describe('P22D · TopBar has no fake/noop UI', () => {
  it('renders no search UI and no ⌘K promise', () => {
    const { container, queryByText } = renderTopBar();
    expect(container.querySelector('[role="search"]')).toBeNull();
    expect(container.querySelector('.topbar-search')).toBeNull();
    expect(queryByText(/⌘K/)).toBeNull();
    expect(queryByText(/Search records/i)).toBeNull();
  });

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
    expect(getByText(/synthetic demo data only/i)).toBeInTheDocument();
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
    await findByText('Memory: Available');
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

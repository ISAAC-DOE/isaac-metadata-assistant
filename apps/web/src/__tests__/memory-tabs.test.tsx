import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter, useNavigate } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  stubFetchRoutes,
  graphStatusAvailable,
  memoryFilesAvailable,
  memoryConceptsAvailable,
} from '../test/apiFixtures';

/*
 * P33 S3 (D6) — Project Memory internal tabs + right-rail assistant. The screen
 * is reorganised into Overview · Sources · Concepts local page tabs (NOT the
 * global LeftNav). Overview carries the memory health/status; the Source Index
 * moves behind Sources, the Concept Lookup behind Concepts. The grounded
 * assistant moves to the right rail so it is visible across ALL three tabs.
 * `?file=` / `?concept=` deep links pre-select the owning tab. This slice is
 * presentation/IA only — no fetch/availability/deep-link/assistant logic changed.
 */

const availableRoutes = {
  'GET /api/graph/status': { body: graphStatusAvailable },
  'GET /api/memory/files': { body: memoryFilesAvailable },
  'GET /api/memory/concepts': { body: memoryConceptsAvailable },
};

function renderAt(path = '/memory') {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('P33 S3 (D6) · Project Memory tabs — tablist', () => {
  it('exposes an accessible tablist with Overview, Sources, and Concepts tabs', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, getByRole } = renderAt();
    await findByText('Memory Available');

    expect(getByRole('tablist', { name: /Project Memory sections/i })).toBeInTheDocument();
    expect(getByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    expect(getByRole('tab', { name: 'Sources' })).toBeInTheDocument();
    expect(getByRole('tab', { name: 'Concepts' })).toBeInTheDocument();

    // Overview is the default selected tab
    expect(getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(getByRole('tab', { name: 'Sources' })).toHaveAttribute('aria-selected', 'false');
  });
});

describe('P33 S3 (D6) · Project Memory tabs — content routing', () => {
  it('Overview shows the status axes but NOT the Source Index / Concept Lookup content', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, queryByText } = renderAt();
    await findByText('Memory Available');

    // Overview carries the memory health/status axes…
    expect(await findByText('Snapshot Integrity')).toBeInTheDocument();
    // …but not the Source Index or Concept Lookup cards.
    expect(queryByText('Source Index')).toBeNull();
    expect(queryByText('Concept Lookup')).toBeNull();
  });

  it('clicking Sources reveals the Source Index (and hides Overview status axes)', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, getByRole, queryByText } = renderAt();
    await findByText('Memory Available');

    fireEvent.click(getByRole('tab', { name: 'Sources' }));

    expect(await findByText('Source Index')).toBeInTheDocument();
    expect(getByRole('tab', { name: 'Sources' })).toHaveAttribute('aria-selected', 'true');
    // Overview-only content is no longer mounted
    expect(queryByText('Snapshot Integrity')).toBeNull();
    expect(queryByText('Concept Lookup')).toBeNull();
  });

  it('clicking Concepts reveals the Concept Lookup', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, getByRole, queryByText } = renderAt();
    await findByText('Memory Available');

    fireEvent.click(getByRole('tab', { name: 'Concepts' }));

    expect(await findByText('Concept Lookup')).toBeInTheDocument();
    expect(getByRole('tab', { name: 'Concepts' })).toHaveAttribute('aria-selected', 'true');
    expect(queryByText('Source Index')).toBeNull();
  });
});

describe('P33 S3 (D6) · Project Memory tabs — assistant persists across tabs', () => {
  it('the grounded assistant is present on every tab', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, getByRole, container } = renderAt();
    await findByText('Memory Available');

    // Overview
    expect(container.querySelector('.assistant')).not.toBeNull();
    // Sources
    fireEvent.click(getByRole('tab', { name: 'Sources' }));
    await findByText('Source Index');
    expect(container.querySelector('.assistant')).not.toBeNull();
    // Concepts
    fireEvent.click(getByRole('tab', { name: 'Concepts' }));
    await findByText('Concept Lookup');
    expect(container.querySelector('.assistant')).not.toBeNull();
  });
});

describe('P33 S3 (D6) · Project Memory tabs — deep links pre-select the owning tab', () => {
  it('?file= opens the Sources tab with the Source Index visible', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, getByRole } = renderAt(
      `/memory?file=${encodeURIComponent(memoryFilesAvailable.files[0].path)}`,
    );
    await findByText('Source Index');
    expect(getByRole('tab', { name: 'Sources' })).toHaveAttribute('aria-selected', 'true');
    expect(getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'false');
  });

  it('?concept= opens the Concepts tab with the Concept Lookup visible', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, getByRole } = renderAt(
      `/memory?concept=${encodeURIComponent(memoryConceptsAvailable.concepts[0].id)}`,
    );
    await findByText('Concept Lookup');
    expect(getByRole('tab', { name: 'Concepts' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('P33 S3 (D6) · Project Memory tabs — IN-PAGE deep link (⌘K jump, no remount)', () => {
  // A ⌘K jump navigates /memory → /memory?concept=… — the SAME route, so
  // ProjectMemory is NOT remounted and the once-per-mount initializer cannot
  // react. This harness keeps ProjectMemory mounted and navigates in-page,
  // reproducing the SearchDialog flow. The owning tab must still auto-select.
  function InPageHarness({ target }: { target: string }) {
    const navigate = useNavigate();
    return (
      <>
        <button type="button" onClick={() => navigate(target)}>
          jump
        </button>
        <ProjectMemory />
      </>
    );
  }

  it('navigating to ?concept= while already on /memory (Overview) selects the Concepts tab and reveals the card', async () => {
    stubFetchRoutes(availableRoutes);
    const conceptId = memoryConceptsAvailable.concepts[0].id;
    const { findByText, getByRole, queryByText } = render(
      <MemoryRouter
        initialEntries={['/memory']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <InPageHarness target={`/memory?concept=${encodeURIComponent(conceptId)}`} />
      </MemoryRouter>,
    );
    await findByText('Memory Available');

    // starts on Overview — Concept Lookup is not mounted
    expect(getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(queryByText('Concept Lookup')).toBeNull();

    // in-page navigation to the same route with a new param (no remount)
    fireEvent.click(getByRole('button', { name: 'jump' }));

    expect(await findByText('Concept Lookup')).toBeInTheDocument();
    expect(getByRole('tab', { name: 'Concepts' })).toHaveAttribute('aria-selected', 'true');
  });

  it('navigating to ?file= in-page selects the Sources tab and reveals the card', async () => {
    stubFetchRoutes(availableRoutes);
    const filePath = memoryFilesAvailable.files[0].path;
    const { findByText, getByRole, queryByText } = render(
      <MemoryRouter
        initialEntries={['/memory']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <InPageHarness target={`/memory?file=${encodeURIComponent(filePath)}`} />
      </MemoryRouter>,
    );
    await findByText('Memory Available');
    expect(queryByText('Source Index')).toBeNull();

    fireEvent.click(getByRole('button', { name: 'jump' }));

    expect(await findByText('Source Index')).toBeInTheDocument();
    expect(getByRole('tab', { name: 'Sources' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('P33 S3 (D6) · Project Memory tabs — keyboard navigation', () => {
  it('ArrowRight moves selection and focus to the next tab', async () => {
    stubFetchRoutes(availableRoutes);
    const { findByText, getByRole } = renderAt();
    await findByText('Memory Available');

    const overview = getByRole('tab', { name: 'Overview' });
    overview.focus();
    fireEvent.keyDown(overview, { key: 'ArrowRight' });

    const sources = getByRole('tab', { name: 'Sources' });
    expect(sources).toHaveAttribute('aria-selected', 'true');
    expect(sources).toHaveFocus();
    expect(await findByText('Source Index')).toBeInTheDocument();
  });
});

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  stubFetchRoutes,
  stubFetchDown,
  graphStatusAvailable,
  graphStatusPreRegen,
  graphStatusMalformed,
  graphStatusUnavailable,
  memoryFilesAvailable,
  memoryFilesUnavailable,
  memoryConceptsUnavailable,
} from '../test/apiFixtures';

/*
 * P24.10 — the Project Memory status detail card under the SEPARATED-freshness
 * contract. The old single conflated `status` verdict is gone; the screen now
 * reads `availability` to decide available vs degraded, and renders the three
 * individually-honest axes (Snapshot Integrity / Memory Policy / Indexed
 * Sources) with scope-accurate microcopy. Every assertion is driven by a
 * stubbed GET /api/graph/status response (no-fake-data invariant).
 */

function renderScreen() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ProjectMemory />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('P24.10 · status card — available, fully current', () => {
  it('renders the Available chip, real counts, and the three separated axes with approved wording', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusAvailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, getByText, container } = renderScreen();

    await findByText('Memory: Available');

    // counts come only from the API overview
    expect(getByText('2296')).toBeInTheDocument();
    expect(getByText('3447')).toBeInTheDocument();
    expect(getByText('214')).toBeInTheDocument();
    expect(getByText('190')).toBeInTheDocument(); // Indexed files = file_count
    expect(getByText('19')).toBeInTheDocument();

    // the three separated axes, each individually honest
    expect(getByText('Snapshot Integrity')).toBeInTheDocument();
    expect(getByText('Memory Policy')).toBeInTheDocument();
    expect(getByText('Indexed Sources')).toBeInTheDocument();
    expect(getByText('Verified')).toBeInTheDocument(); // integrity
    // policy + indexed sources both "Current" (two pills carry the same label)
    expect(container.querySelectorAll('.memory-axis-state').length).toBe(3);
    expect(container.textContent).toMatch(/Current/);

    // indexed-sources scope caveat is stated honestly (proven only over served files)
    expect(getByText(/only the files already in the snapshot/i)).toBeInTheDocument();
    expect(getByText(/re-index/i)).toBeInTheDocument();

    // never a verdict / validity claim on the memory plane
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });

  it('describes what memory indexes honestly, without inventing counts the API did not return', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusAvailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText } = renderScreen();
    await findByText(/source code, docs, schema, and test fixtures/i);
  });

  it('renders a derived relative age only when graph_mtime is present', async () => {
    const NOW = new Date('2026-07-16T12:00:00Z');
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    const withAge = { ...graphStatusAvailable, graph_mtime: NOW.getTime() / 1000 - 3 * 3600 };
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: withAge },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, getByText } = renderScreen();
    await findByText('Memory: Available');
    expect(getByText('built 3 hours ago')).toBeInTheDocument();
  });
});

describe('P24.10 · status card — pre-regen snapshot (available, currency not yet provable)', () => {
  it('renders Available with real counts, integrity Verified, policy + indexed sources Unknown, and no stale warning', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusPreRegen },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, getByText, queryByText, container } = renderScreen();

    await findByText('Memory: Available');

    // available → real counts render (Indexed files comes from file_count = 9)
    expect(getByText('42')).toBeInTheDocument();
    expect(getByText('17')).toBeInTheDocument();
    expect(getByText('9')).toBeInTheDocument();
    expect(getByText('3')).toBeInTheDocument();

    // integrity is proven; policy + indexed-sources currency is honestly Unknown
    expect(getByText('Verified')).toBeInTheDocument();
    // two axes read "Unknown" — quiet/neutral, never an "out of date" warning
    expect(container.querySelectorAll('.memory-axis-state.axis-quiet').length).toBe(2);
    expect(queryByText(/out of date/i)).toBeNull();

    // the indexed-sources scope caveat is still shown
    expect(getByText(/only the files already in the snapshot/i)).toBeInTheDocument();

    // served_file_count is null (pre-regen) — no broken/empty "served" figure,
    // and no fabricated age (graph_mtime null, so never a 1970 epoch artifact)
    expect(container.textContent).not.toMatch(/served files/i);
    expect(container.textContent).not.toMatch(/1970/);
    expect(container.textContent).not.toMatch(/\bAge\b/);

    // available, so NOT the degraded/unavailable panel
    expect(queryByText(/artifacts are not present/i)).toBeNull();
    expect(container.querySelector('.memory-figures')).not.toBeNull();

    expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });
});

describe('P24.10 · status card — malformed snapshot (unavailable + integrity malformed)', () => {
  it('degrades quietly, surfaces Snapshot Integrity Malformed, shows no counts, and no error styling', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusMalformed },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { findByText, getByText, container } = renderScreen();

    await findByText('Memory: Unavailable');

    // the malformed integrity axis is surfaced, honestly explained
    expect(getByText('Snapshot Integrity')).toBeInTheDocument();
    expect(getByText('Malformed')).toBeInTheDocument();
    expect(getByText(/present but malformed/i)).toBeInTheDocument();

    // no counts, and never the error / verdict visual language
    expect(container.querySelector('.memory-figures')).toBeNull();
    expect(container.querySelector('.fetch-state.error')).toBeNull();
    expect(container.querySelector('.verdict-fail')).toBeNull();
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });
});

describe('P24.10 · status card — unavailable (no artifact present)', () => {
  it('renders an honest unavailable panel with hosted + future-wiring copy, no counts, no error styling', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { findByText, container } = renderScreen();

    await findByText('Memory: Unavailable');
    expect(
      await findByText(/memory graph artifacts are not present/i),
    ).toBeInTheDocument();
    expect(container.textContent).toMatch(/hosted demo does not currently ship/i);
    expect(container.textContent).toMatch(/wired later to an approved source/i);

    // no counts / figures rendered, and never the error/verdict visual language
    expect(container.querySelector('.memory-figures')).toBeNull();
    expect(container.querySelector('.fetch-state.error')).toBeNull();
    expect(container.querySelector('.verdict-fail')).toBeNull();
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });
});

describe('P24.10 · status card — backend down', () => {
  it('renders BackendDown with a retry action when the fetch is unreachable', async () => {
    stubFetchDown();
    const { findByText, getByRole } = renderScreen();
    await findByText('Backend Not Running');
    expect(getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('P24.10 · no fake search input on Project Memory', () => {
  it('has no search input or searchbox role anywhere on the screen', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { container, queryByRole, findByText } = renderScreen();
    await findByText('Memory: Unavailable');
    expect(container.querySelector('input[type="search"]')).toBeNull();
    expect(queryByRole('searchbox')).toBeNull();
  });
});

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  stubFetchRoutes,
  stubFetchDown,
  graphStatusMissing,
  memoryFilesAvailable,
  memoryFilesUnavailable,
  memoryConceptsUnavailable,
} from '../test/apiFixtures';

/*
 * P24.3 — the real Project Memory status detail card. Every assertion here is
 * driven by a stubbed GET /api/graph/status response; nothing in the screen
 * may show a figure the fixture did not provide (no-fake-data invariant).
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

describe('P24.3 · status detail card — available (fresh)', () => {
  const NOW = new Date('2026-07-16T12:00:00Z');
  const freshStatus = {
    status: 'fresh' as const,
    plane: 'memory' as const,
    note: 'Graphify is a memory/query layer — never a validator.',
    built_at_commit: 'ab12cd34ef567890',
    node_count: 2296,
    edge_count: 3447,
    community_count: 214,
    file_count: 190,
    concept_count: 19,
    graph_mtime: NOW.getTime() / 1000 - 3 * 3600, // 3 hours before the mocked "now"
  };

  beforeEach(() => {
    // Only fake `Date` — leaving real timers intact so testing-library's
    // internal `waitFor` polling (findByText) still advances normally.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
  });

  it('renders every real figure, the short commit sha, and the derived relative age — no verdict language', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: freshStatus },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, getByText, container } = renderScreen();

    await findByText('Memory: Fresh');
    expect(getByText('2296')).toBeInTheDocument();
    expect(getByText('3447')).toBeInTheDocument();
    expect(getByText('214')).toBeInTheDocument();
    expect(getByText('190')).toBeInTheDocument();
    expect(getByText('19')).toBeInTheDocument();
    expect(getByText('ab12cd3')).toBeInTheDocument(); // short (7-char) sha, .mono
    expect(getByText('built 3 hours ago')).toBeInTheDocument();

    expect(container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });

  it('describes what memory indexes honestly, without inventing counts the API did not return', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: freshStatus },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText } = renderScreen();
    await findByText(/source code, docs, schema, and test fixtures/i);
  });

  it('does not show the stale advisory caption when fresh', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: freshStatus },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, queryByText } = renderScreen();
    await findByText('Memory: Fresh');
    expect(queryByText(/may be out of date/i)).toBeNull();
  });
});

describe('P24.3 · status detail card — stale', () => {
  const staleStatus = {
    status: 'stale' as const,
    plane: 'memory' as const,
    note: 'Graphify is a memory/query layer — never a validator.',
    built_at_commit: 'fedcba9876543210',
    node_count: 100,
    edge_count: 50,
    community_count: 5,
    file_count: 30,
    concept_count: 4,
    graph_mtime: 1784252084.842,
  };

  it('shows the Stale chip, an advisory re-verify caption, and still renders real figures', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: staleStatus },
      'GET /api/memory/files': { body: memoryFilesAvailable },
    });
    const { findByText, getByText } = renderScreen();

    await findByText('Memory: Stale');
    expect(getByText(/may be out of date/i)).toBeInTheDocument();
    expect(getByText(/re-verify against the cited files/i)).toBeInTheDocument();
    expect(getByText('100')).toBeInTheDocument();
    expect(getByText('50')).toBeInTheDocument();
  });
});

describe('P24.3 · status detail card — unavailable (missing)', () => {
  it('renders an honest unavailable panel with hosted + future-wiring copy, no counts, no error styling', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusMissing },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { findByText, container } = renderScreen();

    await findByText('Memory: Missing');
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

describe('P24.3 · status detail card — backend down', () => {
  it('renders BackendDown with a retry action when the fetch is unreachable', async () => {
    stubFetchDown();
    const { findByText, getByRole } = renderScreen();
    await findByText('Backend Not Running');
    expect(getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('P24.3 · no fake search input on Project Memory', () => {
  it('has no search input or searchbox role anywhere on the screen', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusMissing },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { container, queryByRole, findByText } = renderScreen();
    await findByText('Memory: Missing');
    expect(container.querySelector('input[type="search"]')).toBeNull();
    expect(queryByRole('searchbox')).toBeNull();
  });
});

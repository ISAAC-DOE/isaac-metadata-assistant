import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryFilesUnavailable,
  memoryConceptsUnavailable,
} from '../test/apiFixtures';

/*
 * P24.8 Item 2 — the Project Memory intro copy must not claim it surfaces
 * "related records" (that word implies runtime ISAAC records/experiments,
 * which this plane never touches). It surfaces related FILES and CONCEPTS
 * (per the Source Index / Concept Lookup cards), never records. This test
 * renders the real intro paragraph regardless of fetch state — a degraded
 * (unavailable) graph/memory response is enough to reach the text.
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

describe('P24.8 · Project Memory intro copy — no "related records" claim', () => {
  it('never claims to surface "related records", and does claim related files and concepts', async () => {
    stubFetchRoutes({
      'GET /api/memory/concepts': { body: memoryConceptsUnavailable },
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/files': { body: memoryFilesUnavailable },
    });
    const { findByText, container } = renderScreen();

    await findByText('Memory: Unavailable');

    expect(container.textContent).not.toMatch(/related records/i);
    expect(container.textContent).toMatch(/related files/i);
  });
});

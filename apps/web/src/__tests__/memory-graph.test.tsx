import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryGraphAvailable,
  memoryGraphUnavailable,
  memoryFilesAvailable,
  memoryFileDetailWithLeads,
  memoryConceptsAvailable,
  memoryConceptDetailWithLeads,
} from '../test/apiFixtures';

/*
 * P36.2 — the Project Memory "Graph" tab: a deterministic, capped, served-
 * file REFERENCE projection from GET /api/memory/graph. Tests stub ONLY the
 * routes each scenario needs — stubFetchRoutes throws on any unstubbed call,
 * so an accidental extra network request fails the test loudly.
 */

function renderScreen(initialEntry = '/memory') {
  const view = render(
    <MemoryRouter
      initialEntries={[initialEntry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
    </MemoryRouter>,
  );
  fireEvent.click(view.getByRole('tab', { name: 'Graph' }));
  return view;
}

const filePath = (p: string) => `GET /api/memory/file?path=${encodeURIComponent(p)}`;
const conceptPath = (id: string) => `GET /api/memory/concepts/${encodeURIComponent(id)}`;

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- 1. tab appears + mounts ------------------------------------------------

describe('P36.2 · Graph tab — appears and mounts', () => {
  it('is a tab (not a LeftNav item) and mounts the Graph card with exactly one new fetch', async () => {
    const calls = stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, getByRole } = renderScreen();

    expect(getByRole('tab', { name: 'Graph' })).toBeInTheDocument();
    await findByText('Graph', { selector: 'h2' });
    expect(getByRole('tab', { name: 'Graph' })).toHaveAttribute('aria-selected', 'true');

    expect(calls).toContain('GET /api/memory/graph');
    // No other memory endpoint was ever touched — the Graph tab is ONE fetch,
    // and nothing beyond the stubbed routes was ever requested.
    expect(calls).not.toContain('GET /api/memory/files');
    expect(calls).not.toContain('GET /api/memory/concepts');
  });
});

// --- 2. counts + honest "not embedded" disclosure ---------------------------

describe('P36.2 · Graph tab — counts and disclosure', () => {
  it('shows the rendered counts and the honest un-embedded-source-graph disclosure', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, container } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    const text = container.textContent ?? '';
    expect(text).toMatch(/3 files/);
    expect(text).toMatch(/2 concepts/);
    expect(text).toMatch(/1 reference\b/);
    expect(text).toMatch(/2 communities shown/);
    // The un-embedded source graph's real, larger counts (2988 nodes / 4465
    // edges / 257 communities) are disclosed, never hidden or confused with
    // the rendered projection's own (much smaller) counts.
    expect(text).toMatch(/2988 nodes/);
    expect(text).toMatch(/4465 edges/);
    expect(text).toMatch(/257 communities/);
    expect(text).toMatch(/not embedded/i);
    expect(text).not.toMatch(/knowledge graph/i);
    expect(text).not.toMatch(/ontology/i);
  });
});

// --- 3. search filters deterministically ------------------------------------

describe('P36.2 · Graph tab — search', () => {
  it('filters the textual node list client-side as the query changes', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, getByLabelText, queryByText, getByText } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    expect(getByText('src/fake_mod.py')).toBeInTheDocument();
    expect(getByText('src/other_mod.py')).toBeInTheDocument();

    fireEvent.change(getByLabelText('Search graph nodes'), { target: { value: 'other' } });

    expect(getByText('src/other_mod.py')).toBeInTheDocument();
    expect(queryByText('src/fake_mod.py')).toBeNull();
    expect(queryByText('docs/fake-note.md')).toBeNull();
    expect(queryByText('Provenance')).toBeNull();
  });
});

// --- 4. node-type + community filters ---------------------------------------

describe('P36.2 · Graph tab — filters', () => {
  it('the node-type filter narrows to files-only or concepts-only', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, getByLabelText, queryByText, getByText } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    fireEvent.change(getByLabelText('Show'), { target: { value: 'concept' } });
    expect(queryByText('src/fake_mod.py')).toBeNull();
    expect(getByText('Provenance')).toBeInTheDocument();

    fireEvent.change(getByLabelText('Show'), { target: { value: 'file' } });
    expect(getByText('src/fake_mod.py')).toBeInTheDocument();
    expect(queryByText('Provenance')).toBeNull();
  });

  it('the community filter narrows to nodes in that community', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, getByLabelText } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    fireEvent.change(getByLabelText('Community'), { target: { value: '131' } });

    // Scope to the textual LIST pane: selecting a specific community also
    // switches the SVG canvas to that community's view, which renders the
    // SAME labels a second time as inline SVG <text> — query only the list.
    const list = within(document.querySelector('.memory-graph-list') as HTMLElement);
    expect(list.getByText('src/fake_mod.py')).toBeInTheDocument(); // community 131
    expect(list.getByText('Provenance')).toBeInTheDocument(); // community 131
    expect(list.queryByText('src/other_mod.py')).toBeNull(); // community 55
    expect(list.queryByText('docs/fake-note.md')).toBeNull(); // no community
  });
});

// --- 5. selecting a node (list AND SVG keyboard) opens the detail panel ----

describe('P36.2 · Graph tab — node selection and detail panel', () => {
  it('selecting a node from the textual list opens the detail panel with kind/community/connected nodes + collapsed raw JSON', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, getByText } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    fireEvent.click(getByText('src/fake_mod.py'));

    const detail = document.querySelector('.memory-graph-detail');
    expect(detail).not.toBeNull();
    const scoped = within(detail as HTMLElement);

    expect(scoped.getByText('File')).toBeInTheDocument(); // Kind
    expect(scoped.getByText('Export Pipeline')).toBeInTheDocument(); // Community
    expect(scoped.getByText('131')).toBeInTheDocument(); // Community ID
    expect(scoped.getByText('42')).toBeInTheDocument(); // Nodes
    // fake_mod.py's fixture on_disk is true — an honest "present locally" note,
    // never an actionable "open" affordance either way.
    expect(scoped.getByText(/present locally on this backend/)).toBeInTheDocument();

    // Connected nodes: the one real edge (relation "imports"), as a button.
    const connected = scoped.getByRole('button', { name: /src\/other_mod\.py/ });
    expect(connected).toHaveTextContent('imports');

    // Collapsed raw JSON of the SELECTED node only.
    const details = scoped.getByText('Raw node data').closest('details');
    expect(details).not.toHaveAttribute('open');
    const pre = details?.querySelector('pre');
    expect(pre?.textContent).toContain('"id": "src/fake_mod.py"');
    expect(pre?.textContent).not.toContain('other_mod'); // only the SELECTED node's JSON
  });

  it('honestly reports "not present on this backend" for an on_disk:false node', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, getByText } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    fireEvent.click(getByText('docs/fake-note.md')); // on_disk:false in the fixture
    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    expect(within(detail).getByText(/not present on this backend — cannot open/)).toBeInTheDocument();
  });

  it('selecting a node via keyboard Enter on an SVG node opens/updates the detail panel', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, getByText } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    // Select fake_mod first (via the list) so its ego network — including the
    // neighbor other_mod.py — is what's actually rendered in the SVG.
    fireEvent.click(getByText('src/fake_mod.py'));

    const svg = document.querySelector('.memory-graph-svg') as HTMLElement;
    expect(svg).not.toBeNull();
    const svgScoped = within(svg);
    const otherModNode = svgScoped.getByRole('button', { name: /src\/other_mod\.py/ });
    expect(otherModNode).toHaveAttribute('tabindex');

    otherModNode.focus();
    fireEvent.keyDown(otherModNode, { key: 'Enter' });

    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    const scoped = within(detail);
    expect(scoped.getByText('src/other_mod.py')).toBeInTheDocument();
  });
});

// --- 6. source navigation sets ?file= / ?concept= ----------------------------

describe('P36.2 · Graph tab — source navigation', () => {
  it('"View in Sources" sets ?file= and reopens the Sources tab at that row', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
      [filePath('src/fake_mod.py')]: { body: memoryFileDetailWithLeads },
    });
    const { findByText, getByRole, getByText } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    fireEvent.click(getByText('src/fake_mod.py'));
    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    fireEvent.click(within(detail).getByRole('button', { name: 'View in Sources' }));

    expect(await findByText('Source Index')).toBeInTheDocument();
    expect(getByRole('tab', { name: 'Sources' })).toHaveAttribute('aria-selected', 'true');
    // The deep link auto-opens the matching row's provenance panel.
    expect(await findByText('Deterministic, doubly-gated export transform.')).toBeInTheDocument();
  });

  it('"View in Concepts" sets ?concept= and reopens the Concepts tab at that row', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, getByText } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    fireEvent.click(getByText('Provenance'));
    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    fireEvent.click(within(detail).getByRole('button', { name: 'View in Concepts' }));

    expect(await findByText('Concept Lookup')).toBeInTheDocument();
    expect(getByRole('tab', { name: 'Concepts' })).toHaveAttribute('aria-selected', 'true');
    expect(await findByText('anchor source')).toBeInTheDocument();
  });
});

// --- 7. keyboard reachability + roles/aria ----------------------------------

describe('P36.2 · Graph tab — a11y', () => {
  it('every control has an accessible name; SVG nodes carry role=button + tabindex + aria-label', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, getByLabelText, getByRole } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    expect(getByLabelText('Search graph nodes')).toBeInTheDocument();
    expect(getByLabelText('Show')).toBeInTheDocument();
    expect(getByLabelText('Community')).toBeInTheDocument();
    expect(getByRole('button', { name: 'Fit graph to view' })).toBeInTheDocument();
    expect(getByRole('button', { name: 'Zoom in' })).toBeInTheDocument();
    expect(getByRole('button', { name: 'Zoom out' })).toBeInTheDocument();
    expect(getByRole('button', { name: 'Reset view' })).toBeInTheDocument();

    // No SVG is rendered before any node/community is selected (bounded —
    // never the full graph at once); select one to reach the SVG's a11y tree.
    fireEvent.click(getByRole('button', { name: /src\/fake_mod\.py/ }));

    const svg = document.querySelector('.memory-graph-svg') as HTMLElement;
    expect(svg).toHaveAttribute('role', 'group');
    expect(svg.getAttribute('aria-label')).toBeTruthy();

    const nodeButtons = within(svg).getAllByRole('button');
    expect(nodeButtons.length).toBeGreaterThan(0);
    for (const btn of nodeButtons) {
      expect(btn).toHaveAttribute('tabindex');
      expect(btn.getAttribute('aria-label')).toBeTruthy();
    }
    // Roving tabindex: exactly one node is in the tab sequence at a time.
    const rovingCount = nodeButtons.filter((b) => b.getAttribute('tabindex') === '0').length;
    expect(rovingCount).toBe(1);
  });
});

// --- 8. narrow-screen fallback: the list works with the canvas irrelevant --

describe('P36.2 · Graph tab — narrow-screen fallback', () => {
  it('the textual list is fully populated and selectable independent of the canvas state', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    const { findByText, getByText, queryByText } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    // Before any selection the canvas is in its empty ("none") state — the
    // list must already be fully usable regardless.
    expect(queryByText(/Select a file or concept/)).toBeInTheDocument();
    for (const path of ['src/fake_mod.py', 'src/other_mod.py', 'docs/fake-note.md']) {
      expect(getByText(path)).toBeInTheDocument();
    }
    for (const label of ['Provenance', 'Governance allowlist']) {
      expect(getByText(label)).toBeInTheDocument();
    }
    fireEvent.click(getByText('docs/fake-note.md'));
    const detail = document.querySelector('.memory-graph-detail');
    expect(detail).not.toBeNull();
  });
});

// --- 9. available:false -> honest degraded panel, zero nodes ----------------

describe('P36.2 · Graph tab — unavailable', () => {
  it('renders an honest degraded panel with zero fabricated nodes when available:false', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphUnavailable },
    });
    const { findByText, container } = renderScreen();

    await findByText(/Graph tab is unavailable/);
    expect(container.querySelectorAll('.memory-graph-list-row').length).toBe(0);
    expect(container.querySelectorAll('.memory-graph-node').length).toBe(0);
    expect(container.querySelector('.memory-graph-svg')).toBeNull();
    // Never the red/error styling class the rest of the app reserves for hard
    // failures (BackendDown's `.fetch-state.error`).
    expect(container.querySelector('.fetch-state.error')).toBeNull();
  });
});

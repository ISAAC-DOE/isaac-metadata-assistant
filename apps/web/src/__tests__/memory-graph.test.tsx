import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import { HUB_LABEL_COUNT, LABEL_LIMIT, MAX_RENDER_NODES, edgeKey } from '../lib/graphModel';
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
 * The Project Memory "Graph" tab — a deterministic, capped, served-file
 * REFERENCE projection from GET /api/memory/graph.
 *
 * P36R S3 redesigned the surface into TWO permanent modes over one payload and
 * one state model (lib/graphModel.ts, unit-tested in graph-model.test.ts):
 *   Explore — a bounded dark canvas, the default on wide viewports.
 *   Browse  — the textual, keyboard-first list. Permanent, not a fallback.
 * The P36.2 assertions that used to read the list straight off the mounted tab
 * now switch to Browse first; the capability being asserted is unchanged.
 *
 * Tests stub ONLY the routes each scenario needs — stubFetchRoutes throws on
 * any unstubbed call, so an accidental extra network request fails loudly.
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

/** jsdom has no matchMedia, so the tab opens in Explore; this is the switch. */
const toBrowse = (view: RenderResult) => fireEvent.click(view.getByRole('radio', { name: 'Browse' }));

/**
 * A synthetic chain of `n` files in the real payload shape — the same shape
 * graph-model.test.ts exercises as a unit, mounted here through the real tab so
 * the render cap's USER-VISIBLE consequences (the honest notice, and Browse
 * reachability of the capped nodes) are guarded too.
 */
function chainGraph(n: number) {
  const id = (i: number) => `synthetic/chain-${String(i).padStart(4, '0')}.py`;
  return {
    ...memoryGraphAvailable,
    nodes: Array.from({ length: n }, (_, i) => ({
      id: id(i),
      kind: 'file' as const,
      label: id(i),
      file_type: 'code',
      community_id: null,
      community_name: null,
      node_count: 1,
      on_disk: true,
    })),
    edges: Array.from({ length: Math.max(0, n - 1) }, (_, i) => ({
      source: id(i),
      target: id(i + 1),
      relations: ['imports'],
    })),
    communities: [],
    meta: {
      ...memoryGraphAvailable.meta,
      counts: {
        ...memoryGraphAvailable.meta.counts,
        files: n,
        concepts: 0,
        reference_edges: Math.max(0, n - 1),
        communities_rendered: 0,
      },
    },
  };
}

const filePath = (p: string) => `GET /api/memory/file?path=${encodeURIComponent(p)}`;
const conceptPath = (id: string) => `GET /api/memory/concepts/${encodeURIComponent(id)}`;
const graphRoutes = {
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/graph': { body: memoryGraphAvailable },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- 1. tab appears + mounts ------------------------------------------------

describe('Graph tab — appears and mounts', () => {
  it('is a tab (not a LeftNav item) and mounts the Graph card with exactly one new fetch', async () => {
    const calls = stubFetchRoutes(graphRoutes);
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

  it('opts the Graph tab (and only the Graph tab) into the full-width mode', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    expect(view.container.querySelector('main')?.getAttribute('data-width')).toBe('full');

    fireEvent.click(view.getByRole('tab', { name: 'Concepts' }));
    expect(view.container.querySelector('main')?.getAttribute('data-width')).toBe('wide');
  });

  it('offers both permanent modes, with Explore selected by default here', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    expect(view.getByRole('radio', { name: 'Explore' })).toHaveAttribute('aria-checked', 'true');
    expect(view.getByRole('radio', { name: 'Browse' })).toHaveAttribute('aria-checked', 'false');
    expect(document.querySelector('.memory-graph-svg')).not.toBeNull();
    expect(document.querySelector('.memory-graph-list')).toBeNull();

    toBrowse(view);
    expect(view.getByRole('radio', { name: 'Browse' })).toHaveAttribute('aria-checked', 'true');
    expect(document.querySelector('.memory-graph-list')).not.toBeNull();
    expect(document.querySelector('.memory-graph-svg')).toBeNull();
  });
});

// --- 2. counts + honest layered disclosure ---------------------------------

describe('Graph tab — counts and disclosure', () => {
  it('shows the rendered counts and the honest un-embedded-source-graph disclosure', async () => {
    stubFetchRoutes(graphRoutes);
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

  it('spells out the four layers between the source graph and what is shown', async () => {
    stubFetchRoutes(graphRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Graph', { selector: 'h2' });

    const layers = container.querySelector('.memory-graph-layers');
    expect(layers).not.toBeNull();
    const items = (layers as HTMLElement).querySelectorAll('li');
    expect(items.length).toBe(4);
    const text = (layers as HTMLElement).textContent ?? '';
    expect(text).toMatch(/Full Graphify source graph/);
    expect(text).toMatch(/Served-file projection/);
    expect(text).toMatch(/Concepts/);
    expect(text).toMatch(/Clusters/);
    expect(text).toMatch(/advisory only/);
  });

  it('never uses verdict language on this advisory surface', async () => {
    stubFetchRoutes(graphRoutes);
    const { findByText, container } = renderScreen();
    await findByText('Graph', { selector: 'h2' });
    // Scoped to the graph card: the surrounding page legitimately says
    // "never a validation verdict", which is the opposite of a verdict claim.
    const card = container.querySelector('.memory-graph-card') as HTMLElement;
    const text = card.textContent ?? '';
    for (const claim of [
      /\bis valid\b/i,
      /\bis invalid\b/i,
      /passes validation/i,
      /fails validation/i,
      /\bconfirms\b/i,
      /\bproves\b/i,
      /\bguarantee/i,
      /schema[- ]compliant/i,
    ]) {
      expect(text, `verdict language in the graph card: ${claim}`).not.toMatch(claim);
    }
    expect(text).toMatch(/leads to verify, never a validation verdict/);
    expect(text).toMatch(/advisory/i);
  });
});

// --- 3. search filters deterministically ------------------------------------

describe('Graph tab — search', () => {
  it('filters the textual node list client-side as the query changes', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);
    const { getByLabelText, queryByText, getByText } = view;

    expect(getByText('src/fake_mod.py')).toBeInTheDocument();
    expect(getByText('src/other_mod.py')).toBeInTheDocument();

    fireEvent.change(getByLabelText('Search graph nodes'), { target: { value: 'other' } });

    expect(getByText('src/other_mod.py')).toBeInTheDocument();
    expect(queryByText('src/fake_mod.py')).toBeNull();
    expect(queryByText('docs/fake-note.md')).toBeNull();
    expect(queryByText('Provenance')).toBeNull();
  });

  it('the same search narrows the Explore canvas — one state model, two views', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const svg = () => document.querySelector('.memory-graph-svg') as HTMLElement;
    expect(within(svg()).getAllByRole('button').length).toBe(5);

    fireEvent.change(view.getByLabelText('Search graph nodes'), { target: { value: 'other' } });
    expect(within(svg()).getAllByRole('button').length).toBe(1);
    expect(view.container.textContent).toMatch(/1 of 5 nodes shown/);
  });
});

// --- 4. node-type + community + relationship filters ------------------------

describe('Graph tab — filters', () => {
  it('the node-type filter narrows to files-only or concepts-only', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);
    const { getByLabelText, queryByText, getByText } = view;

    fireEvent.change(getByLabelText('Show'), { target: { value: 'concept' } });
    expect(queryByText('src/fake_mod.py')).toBeNull();
    expect(getByText('Provenance')).toBeInTheDocument();

    fireEvent.change(getByLabelText('Show'), { target: { value: 'file' } });
    expect(getByText('src/fake_mod.py')).toBeInTheDocument();
    expect(queryByText('Provenance')).toBeNull();
  });

  it('the community filter narrows to nodes in that community', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);

    fireEvent.change(view.getByLabelText('Cluster'), { target: { value: '131' } });

    const list = within(document.querySelector('.memory-graph-list') as HTMLElement);
    expect(list.getByText('src/fake_mod.py')).toBeInTheDocument(); // community 131
    expect(list.getByText('Provenance')).toBeInTheDocument(); // community 131
    expect(list.queryByText('src/other_mod.py')).toBeNull(); // community 55
    expect(list.queryByText('docs/fake-note.md')).toBeNull(); // no community
  });

  it('presents clusters honestly — sorted, filterable, singletons labelled as such', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const select = view.getByLabelText('Cluster') as HTMLSelectElement;
    // Both fixture clusters hold one file, so both land in the honest group.
    expect(select.querySelector('optgroup[label*="Single-file"]')).not.toBeNull();
    expect(view.container.textContent).toMatch(
      /Clusters are derived automatically by the upstream graph builder/,
    );
    expect(view.container.textContent).toMatch(/not as categories/);

    // The cluster list itself is filterable rather than a flat wall of options.
    fireEvent.change(view.getByLabelText('Find a cluster'), { target: { value: 'export' } });
    const options = [...select.querySelectorAll('option')].map((o) => o.textContent ?? '');
    expect(options.some((o) => o.includes('Export Pipeline'))).toBe(true);
    expect(options.some((o) => o.includes('unnamed cluster'))).toBe(false);
  });

  it('the relationship filter hides those references without inventing others', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    expect(document.querySelectorAll('.memory-graph-edge').length).toBe(1);
    fireEvent.click(view.getByRole('checkbox', { name: 'imports' }));
    expect(document.querySelectorAll('.memory-graph-edge').length).toBe(0);
    fireEvent.click(view.getByRole('checkbox', { name: 'imports' }));
    expect(document.querySelectorAll('.memory-graph-edge').length).toBe(1);
  });
});

// --- 5. no invented edges ---------------------------------------------------

describe('Graph tab — no invented edges', () => {
  it('every DRAWN edge exists in the fetched payload', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const payloadKeys = new Set(memoryGraphAvailable.edges.map((e) => edgeKey(e.source, e.target)));
    const drawn = [...document.querySelectorAll('.memory-graph-edge')].map((l) =>
      l.getAttribute('data-edge'),
    );
    expect(drawn.length).toBeGreaterThan(0);
    for (const key of drawn) expect(payloadKeys.has(key ?? '')).toBe(true);
    // 5 nodes, exactly 1 payload edge: no ring, no completion, no inference.
    expect(drawn.length).toBe(memoryGraphAvailable.edges.length);
  });

  it('does not claim a render bound it is not hitting', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    expect(view.container.textContent).not.toMatch(/draws at most/);
    expect(view.container.textContent).toMatch(/5 of 5 nodes shown/);
  });
});

// --- 5b. the default Explore view: whole graph, bounded, legible -------------

/*
 * Contract (orchestrator decision R8, 2026-07-25): the DEFAULT Explore view is
 * the whole-graph overview — every node up to MAX_RENDER_NODES, nothing
 * pre-filtered — AND it is legible at rest AND the bound is reported honestly
 * when it bites. A change that silently unbounds the canvas, one that silently
 * truncates it, and one that leaves it with no text must each fail here.
 */
describe('Graph tab — the default Explore view', () => {
  it('mounts EVERY node and edge in the payload, with nothing pre-filtered', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const svg = document.querySelector('.memory-graph-svg') as HTMLElement;
    expect(within(svg).getAllByRole('button').length).toBe(memoryGraphAvailable.nodes.length);
    expect(document.querySelectorAll('.memory-graph-edge').length).toBe(
      memoryGraphAvailable.edges.length,
    );
    // No search-first empty canvas: no query, no node pre-selected.
    expect((view.getByLabelText('Search graph nodes') as HTMLInputElement).value).toBe('');
    expect(document.querySelector('.memory-graph-detail')).toBeNull();
    expect(view.container.textContent).toMatch(/5 of 5 nodes shown/);
  });

  it('labels every visible node while the visible set is under the all-labels limit', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    expect(document.querySelectorAll('.memory-graph-node-label').length).toBe(
      memoryGraphAvailable.nodes.length,
    );
  });

  it('is still legible ABOVE that limit — the overview is never left with zero labels', async () => {
    const n = LABEL_LIMIT + 25;
    stubFetchRoutes({ ...graphRoutes, 'GET /api/memory/graph': { body: chainGraph(n) } });
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    expect(document.querySelectorAll('.memory-graph-node').length).toBe(n);
    // The whole point of this guard: NOT zero. Up to HUB_LABEL_COUNT landmarks
    // stay labelled so the canvas can be read at rest; the placement pass may
    // drop a candidate whose label would collide with one already placed, so
    // the bound is "some, at most HUB_LABEL_COUNT", never "none".
    const labels = document.querySelectorAll('.memory-graph-node-label').length;
    expect(labels).toBeGreaterThan(0);
    expect(labels).toBeLessThanOrEqual(HUB_LABEL_COUNT);
  });

  it('over the cap: draws exactly the cap, SAYS so, and keeps the rest reachable in Browse', async () => {
    const n = MAX_RENDER_NODES + 40;
    stubFetchRoutes({ ...graphRoutes, 'GET /api/memory/graph': { body: chainGraph(n) } });
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    expect(document.querySelectorAll('.memory-graph-node').length).toBe(MAX_RENDER_NODES);
    expect(view.container.textContent).toMatch(
      new RegExp(`draws at most ${MAX_RENDER_NODES} of ${n} nodes`),
    );
    expect(view.container.textContent).toMatch(
      new RegExp(`${MAX_RENDER_NODES} of ${n} nodes shown on the canvas`),
    );

    // The chain's degree-1 end loses the cap — off the canvas, still in Browse.
    const svg = document.querySelector('.memory-graph-svg') as HTMLElement;
    expect(within(svg).queryAllByRole('button', { name: /chain-0000\.py/ }).length).toBe(0);

    toBrowse(view);
    expect(view.getByText('synthetic/chain-0000.py')).toBeInTheDocument();
    expect(view.container.textContent).toMatch(new RegExp(`${n} of ${n} nodes shown`));
  });

  it('explains the outer ring rather than letting its geometry imply structure', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    // 3 of the 5 fixture nodes carry no edge at all.
    expect(view.container.textContent).toMatch(
      /no recorded reference at all and sit on the outer rings/,
    );
    expect(view.container.textContent).toMatch(/not a relationship between them/);
  });
});

// --- 5c. legend ---------------------------------------------------------------

describe('Graph tab — legend', () => {
  it('names EXACTLY the clusters the canvas colours', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const legend = document.querySelector('.graph-legend') as HTMLElement;
    const legendSlots = [...legend.querySelectorAll('.graph-legend-swatch')]
      .flatMap((el) => [...el.classList])
      .filter((c) => /^c\d+$/.test(c))
      .sort();
    const canvasSlots = [
      ...new Set(
        [...document.querySelectorAll('.memory-graph-node')]
          .flatMap((el) => [...el.classList])
          .map((c) => /^memory-graph-node-(c\d+)$/.exec(c)?.[1])
          .filter((c): c is string => Boolean(c)),
      ),
    ].sort();
    // Both fixture clusters hold ONE file — precisely the case a separate
    // singleton filter dropped from the legend while the canvas still coloured
    // them, silently attributing coloured nodes to the neutral swatch.
    expect(canvasSlots.length).toBeGreaterThan(0);
    expect(legendSlots).toEqual(canvasSlots);
  });

  it('labels a cluster as "name · N files", never with two adjacent parentheticals', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const text = (document.querySelector('.graph-legend') as HTMLElement).textContent ?? '';
    expect(text).toContain('Export Pipeline · 1 file');
    expect(text).not.toMatch(/\)\s*\(/);
  });
});

// --- 6. selecting a node (list AND canvas) opens the detail panel -----------

describe('Graph tab — node selection and detail panel', () => {
  it('selecting a node from the textual list opens the detail panel with kind/community/connected nodes + collapsed raw JSON', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);

    fireEvent.click(view.getByText('src/fake_mod.py'));

    const detail = document.querySelector('.memory-graph-detail');
    expect(detail).not.toBeNull();
    const scoped = within(detail as HTMLElement);

    expect(scoped.getByText('File')).toBeInTheDocument(); // Kind
    expect(scoped.getByText('Export Pipeline')).toBeInTheDocument(); // Community
    expect(scoped.getByText('131')).toBeInTheDocument(); // Community ID
    expect(scoped.getByText('42')).toBeInTheDocument(); // Nodes
    // fake_mod.py's fixture on_disk is true — the SHARED `on_disk` sentence
    // (P36R S10: identical in meaning on Sources, Concepts and here), never an
    // actionable "open" affordance either way, and never a snapshot claim.
    expect(
      scoped.getByText('This deployment carries the file itself — it is not opened or read here.'),
    ).toBeInTheDocument();

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

  it('reports the shared "does not carry the file itself" sentence for an on_disk:false node', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);

    fireEvent.click(view.getByText('docs/fake-note.md')); // on_disk:false in the fixture
    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    expect(
      within(detail).getByText(
        'This deployment does not carry the file itself — open it in the project to read it.',
      ),
    ).toBeInTheDocument();
    // `on_disk` says nothing about snapshot membership (R9) — this node IS in
    // the served projection, which is how it is rendered at all.
    expect(detail.textContent).not.toMatch(/snapshot/i);
  });

  it('selecting a node via keyboard Enter on a canvas node opens/updates the detail panel', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const svg = document.querySelector('.memory-graph-svg') as HTMLElement;
    expect(svg).not.toBeNull();
    const otherModNode = within(svg).getByRole('button', { name: /src\/other_mod\.py/ });
    expect(otherModNode).toHaveAttribute('tabindex');

    otherModNode.focus();
    fireEvent.keyDown(otherModNode, { key: 'Enter' });

    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    expect(within(detail).getByText('src/other_mod.py')).toBeInTheDocument();
  });

  it('a detail panel is present in BOTH modes and carries the same node', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const svg = document.querySelector('.memory-graph-svg') as HTMLElement;
    fireEvent.keyDown(within(svg).getByRole('button', { name: /src\/fake_mod\.py/ }), {
      key: 'Enter',
    });
    const exploreDetail = document.querySelector('.memory-graph-detail') as HTMLElement;
    expect(within(exploreDetail).getByText('src/fake_mod.py')).toBeInTheDocument();

    toBrowse(view);
    const browseDetail = document.querySelector('.memory-graph-detail') as HTMLElement;
    expect(within(browseDetail).getByText('src/fake_mod.py')).toBeInTheDocument();
    expect(within(browseDetail).getByRole('button', { name: /src\/other_mod\.py/ })).toBeInTheDocument();
  });
});

// --- 7. neighbourhood + path ------------------------------------------------

describe('Graph tab — neighbourhood and path', () => {
  it('1-hop and 2-hop neighbourhood expansion is reachable from the detail panel', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);
    fireEvent.click(view.getByText('src/fake_mod.py'));

    fireEvent.click(view.getByRole('button', { name: 'Show 1-hop neighbourhood' }));
    expect(view.container.textContent).toMatch(/1-hop neighbourhood of src\/fake_mod\.py/);
    expect(view.container.textContent).toMatch(/2 of 5 nodes shown/);
    const list = within(document.querySelector('.memory-graph-list') as HTMLElement);
    expect(list.getByText('src/other_mod.py')).toBeInTheDocument();
    expect(list.queryByText('docs/fake-note.md')).toBeNull();

    fireEvent.click(view.getByRole('button', { name: 'Show 2-hop neighbourhood' }));
    expect(view.container.textContent).toMatch(/2-hop neighbourhood of src\/fake_mod\.py/);

    fireEvent.click(view.getByRole('button', { name: 'Clear' }));
    expect(view.container.textContent).toMatch(/5 of 5 nodes shown/);
  });

  it('finds a path, shows it as ordered steps, and calls it a navigational lead', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    fireEvent.change(view.getByLabelText('Path from'), { target: { value: 'src/fake_mod.py' } });
    fireEvent.change(view.getByLabelText('Path to'), { target: { value: 'src/other_mod.py' } });
    fireEvent.click(view.getByRole('button', { name: 'Find path' }));

    expect(view.container.textContent).toMatch(/Found a 1-step route/);
    const steps = document.querySelectorAll('.memory-graph-path-list li');
    expect([...steps].map((li) => li.textContent)).toEqual(['src/fake_mod.py', 'src/other_mod.py']);
    expect(view.container.textContent).toMatch(/navigational lead/);
    expect(view.container.textContent).toMatch(/not a\s+semantic or scientific connection/);
  });

  it('says so honestly when there is NO path, and invents nothing', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    fireEvent.change(view.getByLabelText('Path from'), { target: { value: 'src/fake_mod.py' } });
    fireEvent.change(view.getByLabelText('Path to'), { target: { value: 'docs/fake-note.md' } });
    fireEvent.click(view.getByRole('button', { name: 'Find path' }));

    expect(view.container.textContent).toMatch(/No path connects/);
    expect(document.querySelector('.memory-graph-path-list')).toBeNull();
    // and nothing was silently filtered away as a consolation
    expect(view.container.textContent).toMatch(/5 of 5 nodes shown/);
  });

  it('refuses an ambiguous token and offers bounded candidates instead of guessing', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    fireEvent.change(view.getByLabelText('Path from'), { target: { value: 'mod' } });
    fireEvent.change(view.getByLabelText('Path to'), { target: { value: 'docs/fake-note.md' } });
    fireEvent.click(view.getByRole('button', { name: 'Find path' }));

    expect(view.container.textContent).toMatch(/matches 2 nodes, so no\s+identity was assumed/);
    const candidates = document.querySelectorAll('.memory-graph-candidate-btn');
    expect([...candidates].map((b) => b.textContent)).toEqual([
      'src/fake_mod.py',
      'src/other_mod.py',
    ]);
  });

  it('reports an unknown token as not found rather than substituting a near match', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    fireEvent.change(view.getByLabelText('Path from'), { target: { value: 'nope/missing.py' } });
    fireEvent.change(view.getByLabelText('Path to'), { target: { value: 'src/fake_mod.py' } });
    fireEvent.click(view.getByRole('button', { name: 'Find path' }));

    expect(view.container.textContent).toMatch(/No node in this projection matches/);
    expect(document.querySelector('.memory-graph-detail')).toBeNull(); // nothing selected
  });
});

// --- 8. viewport controls ---------------------------------------------------

describe('Graph tab — viewport', () => {
  it('zoom in / out / reset move the reported zoom level and restore it', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    expect(view.container.textContent).toMatch(/zoom 100%/);
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    expect(view.container.textContent).toMatch(/zoom 125%/);
    fireEvent.click(view.getByRole('button', { name: 'Zoom out' }));
    expect(view.container.textContent).toMatch(/zoom 100%/);
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    fireEvent.click(view.getByRole('button', { name: 'Reset view' }));
    expect(view.container.textContent).toMatch(/zoom 100%/);
  });

  it('fit changes the viewBox without changing the node set', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const svg = () => document.querySelector('.memory-graph-svg') as SVGSVGElement;
    const before = svg().getAttribute('viewBox');
    fireEvent.click(view.getByRole('button', { name: 'Fit graph to view' }));
    expect(svg().getAttribute('viewBox')).not.toBe(before);
    expect(within(svg() as unknown as HTMLElement).getAllByRole('button').length).toBe(5);
  });

  it('arrow keys pan the canvas from the keyboard alone', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const svg = document.querySelector('.memory-graph-svg') as SVGSVGElement;
    const before = svg.getAttribute('viewBox');
    fireEvent.keyDown(svg, { key: 'ArrowRight' });
    expect(svg.getAttribute('viewBox')).not.toBe(before);
  });
});

// --- 9. source navigation sets ?file= / ?concept= ---------------------------

describe('Graph tab — source navigation', () => {
  it('"View in Sources" sets ?file= and reopens the Sources tab at that row', async () => {
    stubFetchRoutes({
      ...graphRoutes,
      'GET /api/memory/files': { body: memoryFilesAvailable },
      [filePath('src/fake_mod.py')]: { body: memoryFileDetailWithLeads },
    });
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);

    fireEvent.click(view.getByText('src/fake_mod.py'));
    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    fireEvent.click(within(detail).getByRole('button', { name: 'View in Sources' }));

    expect(await view.findByText('Source Index')).toBeInTheDocument();
    expect(view.getByRole('tab', { name: 'Sources' })).toHaveAttribute('aria-selected', 'true');
    // The deep link auto-opens the matching row's provenance panel.
    expect(await view.findByText('Deterministic, doubly-gated export transform.')).toBeInTheDocument();
  });

  it('"View in Concepts" sets ?concept= and reopens the Concepts tab at that row', async () => {
    stubFetchRoutes({
      ...graphRoutes,
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);

    fireEvent.click(within(document.querySelector('.memory-graph-list') as HTMLElement).getByText('Provenance'));
    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    fireEvent.click(within(detail).getByRole('button', { name: 'View in Concepts' }));

    expect(await view.findByText('Concept Lookup')).toBeInTheDocument();
    expect(view.getByRole('tab', { name: 'Concepts' })).toHaveAttribute('aria-selected', 'true');
    expect(await view.findByText('anchor source')).toBeInTheDocument();
  });
});

// --- 10. keyboard reachability + roles/aria ---------------------------------

describe('Graph tab — a11y', () => {
  it('every control has an accessible name; canvas nodes carry role=button + tabindex + aria-label', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    const { getByLabelText, getByRole } = view;

    expect(getByLabelText('Search graph nodes')).toBeInTheDocument();
    expect(getByLabelText('Show')).toBeInTheDocument();
    expect(getByLabelText('Cluster')).toBeInTheDocument();
    expect(getByLabelText('Find a cluster')).toBeInTheDocument();
    expect(getByLabelText('Path from')).toBeInTheDocument();
    expect(getByLabelText('Path to')).toBeInTheDocument();
    expect(getByRole('button', { name: 'Fit graph to view' })).toBeInTheDocument();
    expect(getByRole('button', { name: 'Zoom in' })).toBeInTheDocument();
    expect(getByRole('button', { name: 'Zoom out' })).toBeInTheDocument();
    expect(getByRole('button', { name: 'Reset view' })).toBeInTheDocument();
    expect(getByRole('radiogroup', { name: 'Graph view mode' })).toBeInTheDocument();
    expect(getByRole('group', { name: 'Relationships' })).toBeInTheDocument();

    const svg = document.querySelector('.memory-graph-svg') as HTMLElement;
    expect(svg).toHaveAttribute('role', 'group');
    expect(svg.getAttribute('aria-label')).toBeTruthy();
    expect(svg).toHaveAttribute('tabindex', '0');

    const nodeButtons = within(svg).getAllByRole('button');
    expect(nodeButtons.length).toBeGreaterThan(0);
    for (const btn of nodeButtons) {
      expect(btn).toHaveAttribute('tabindex');
      expect(btn.getAttribute('aria-label')).toBeTruthy();
    }
    // Roving tabindex: exactly one node is in the tab sequence at a time.
    expect(nodeButtons.filter((b) => b.getAttribute('tabindex') === '0').length).toBe(1);
  });

  it('arrow keys move the roving focus between canvas nodes', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const svg = document.querySelector('.memory-graph-svg') as HTMLElement;
    const nodes = within(svg).getAllByRole('button');
    const first = nodes.find((n) => n.getAttribute('tabindex') === '0') as HTMLElement;
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(document.activeElement).not.toBe(first);
    expect((document.activeElement as HTMLElement).getAttribute('role')).toBe('button');
  });

  it('keeps exactly one polite live region on this surface', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    const card = document.querySelector('.memory-graph-card') as HTMLElement;
    expect(card.querySelectorAll('[aria-live="polite"]').length).toBe(1);
  });

  it('announces RESULTS, not the per-keystroke count line', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    const card = document.querySelector('.memory-graph-card') as HTMLElement;
    const live = () => card.querySelector('[aria-live="polite"]') as HTMLElement;

    // The count line is visible, but outside the live region: it changes on
    // every keystroke, which announced it six times while typing one word.
    expect(view.container.textContent).toMatch(/5 of 5 nodes shown/);
    expect(live().textContent ?? '').not.toMatch(/nodes shown/);
    fireEvent.change(view.getByLabelText('Search graph nodes'), { target: { value: 'other' } });
    expect(live().textContent ?? '').not.toMatch(/nodes shown/);

    // A path/neighbourhood result IS announced there, and there is still one.
    fireEvent.change(view.getByLabelText('Path from'), { target: { value: 'src/fake_mod.py' } });
    fireEvent.change(view.getByLabelText('Path to'), { target: { value: 'docs/fake-note.md' } });
    fireEvent.click(view.getByRole('button', { name: 'Find path' }));
    expect(card.querySelectorAll('[aria-live="polite"]').length).toBe(1);
    expect(live().textContent ?? '').toMatch(/No path connects/);
  });

  it('zoom / fit / reset keys work while a canvas NODE holds focus, as the help promises', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const svg = document.querySelector('.memory-graph-svg') as SVGSVGElement;
    const initialViewBox = svg.getAttribute('viewBox');
    const node = within(svg as unknown as HTMLElement)
      .getAllByRole('button')
      .find((b) => b.getAttribute('tabindex') === '0') as HTMLElement;
    node.focus();

    fireEvent.keyDown(node, { key: '+' });
    expect(view.container.textContent).toMatch(/zoom 125%/);
    fireEvent.keyDown(node, { key: '-' });
    expect(view.container.textContent).toMatch(/zoom 100%/);
    fireEvent.keyDown(node, { key: 'f' });
    expect(svg.getAttribute('viewBox')).not.toBe(initialViewBox);
    fireEvent.keyDown(node, { key: '0' });
    expect(svg.getAttribute('viewBox')).toBe(initialViewBox);
    // …and the node still has focus: these keys never steal the selection.
    expect(document.activeElement).toBe(node);
  });
});

// --- 11. Browse mode is a complete, pointer-free experience ------------------

describe('Graph tab — Browse mode', () => {
  it('the textual list is fully populated and every node is selectable there', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);

    for (const path of ['src/fake_mod.py', 'src/other_mod.py', 'docs/fake-note.md']) {
      expect(view.getByText(path)).toBeInTheDocument();
    }
    for (const label of ['Provenance', 'Governance allowlist']) {
      expect(view.getByText(label)).toBeInTheDocument();
    }
    fireEvent.click(view.getByText('docs/fake-note.md'));
    expect(document.querySelector('.memory-graph-detail')).not.toBeNull();
  });

  it('every list row is a real button, reachable and activatable from the keyboard', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);

    const rows = [...document.querySelectorAll('.memory-graph-list-row-btn')] as HTMLElement[];
    expect(rows.length).toBe(5);
    for (const row of rows) {
      expect(row.tagName).toBe('BUTTON');
      expect(row).toHaveAttribute('aria-pressed');
      expect(row.hasAttribute('disabled')).toBe(false);
    }
    rows[0].focus();
    expect(document.activeElement).toBe(rows[0]);
    fireEvent.click(rows[0]);
    expect(rows[0]).toHaveAttribute('aria-pressed', 'true');
  });

  it('can group the list by cluster, not only by file type', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);

    const headings = () =>
      [...document.querySelectorAll('.memory-graph-list-group-heading')].map(
        (h) => h.textContent ?? '',
      );
    expect(headings().some((h) => h.startsWith('Code'))).toBe(true);

    fireEvent.change(view.getByLabelText('Group by'), { target: { value: 'community' } });
    expect(headings().some((h) => h.startsWith('Export Pipeline'))).toBe(true);
    expect(headings().some((h) => h.startsWith('No cluster'))).toBe(true);
  });

  it('offers the SAME graph capabilities as Explore, with no canvas mounted', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);

    expect(document.querySelector('.memory-graph-svg')).toBeNull();
    // search / type / cluster / relationship / path — all still present
    expect(view.getByLabelText('Search graph nodes')).toBeInTheDocument();
    expect(view.getByLabelText('Show')).toBeInTheDocument();
    expect(view.getByLabelText('Cluster')).toBeInTheDocument();
    expect(view.getByRole('checkbox', { name: 'imports' })).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Find path' })).toBeInTheDocument();
    // …and the per-node capabilities, via the shared detail panel
    fireEvent.click(view.getByText('src/fake_mod.py'));
    expect(view.getByRole('button', { name: 'Show 1-hop neighbourhood' })).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Show 2-hop neighbourhood' })).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Use as path start' })).toBeInTheDocument();
    expect(view.getByText('Raw node data')).toBeInTheDocument();
  });
});

// --- 12. graph help (Slice 6) -----------------------------------------------

describe('Graph tab — help drawer', () => {
  it('opens from the i control, traps focus, closes on Escape and restores focus', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const trigger = view.getByRole('button', { name: 'About this graph' });
    expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(trigger);
    const dialog = view.getByRole('dialog', { name: 'About this graph' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(document.activeElement).toBe(dialog);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(view.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('closes from the explicit close control and restores focus too', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });

    const trigger = view.getByRole('button', { name: 'About this graph' });
    fireEvent.click(trigger);
    fireEvent.click(view.getByRole('button', { name: 'Close graph help' }));
    expect(view.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('explains what the graph is, is NOT, and every control it documents', async () => {
    stubFetchRoutes(graphRoutes);
    const view = renderScreen();
    await view.findByText('Graph', { selector: 'h2' });
    fireEvent.click(view.getByRole('button', { name: 'About this graph' }));

    const text = (view.getByRole('dialog').textContent ?? '').toLowerCase();
    for (const topic of [
      'what it does not represent',
      'node shapes',
      'cluster colours',
      'relationship types',
      'finding things',
      'moving around the canvas',
      'keyboard',
      'explore vs browse',
      'snapshot',
      'command syntax',
    ]) {
      expect(text).toContain(topic);
    }
    expect(text).toContain('circle');
    expect(text).toContain('diamond');
    // The 71-node unconnected belt is explained where a user can see it, not
    // only in a code comment: a perfect ring reads as meaning otherwise.
    expect(text).toContain('outer rings');
    expect(text).toContain('imports'); // the payload's own relation values
    expect(text).toContain('caab1d0'); // the snapshot fingerprint
    expect(text).toContain('advisory');
    expect(text).toMatch(/not a record|not a validation/);
  });

  it('is not offered when there is no graph to explain', async () => {
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusUnavailable },
      'GET /api/memory/graph': { body: memoryGraphUnavailable },
    });
    const view = renderScreen();
    await view.findByText(/Graph tab is unavailable/);
    expect(view.queryByRole('button', { name: 'About this graph' })).toBeNull();
  });
});

// --- 13. available:false -> honest degraded panel, zero nodes ---------------

describe('Graph tab — unavailable', () => {
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
    expect(container.querySelector('.memory-graph-edge')).toBeNull();
    // Never the red/error styling class the rest of the app reserves for hard
    // failures (BackendDown's `.fetch-state.error`).
    expect(container.querySelector('.fetch-state.error')).toBeNull();
  });
});

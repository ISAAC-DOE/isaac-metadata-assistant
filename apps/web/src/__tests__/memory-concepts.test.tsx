import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { ProjectMemory, conceptGraphSearch, describeConcept } from '../screens/ProjectMemory';
import { decodeGraphActions, GRAPH_URL_PARAMS } from '../lib/graphCommands';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryFilesUnavailable,
  memoryConceptsAvailable,
  memoryConceptsUnavailable,
  memoryConceptDetailWithLeads,
  memoryConceptDetailEmptyLeads,
  memoryConceptDetailWithheldAnchor,
  memoryGraphUnavailable,
} from '../test/apiFixtures';

/*
 * P24.5 — the Concept Lookup card: the curated concepts Graphify anchored in
 * project docs, from GET /api/memory/concepts, plus a lazy per-concept
 * provenance detail from GET /api/memory/concepts/{id}. Concepts are
 * navigation anchors, not findings — every assertion checks leads, never a
 * verdict. Source Index is stubbed unavailable in every test here (its own
 * card renders independently; these tests only exercise Concept Lookup).
 *
 * P36R Slice 7 rebuilt the card as a MASTER-DETAIL browser: search, two
 * category filters, a compact keyboard-navigable list, one detail region, a
 * plain-language description assembled ONLY from returned fields, source
 * navigation, and the two graph actions — which reuse the Slice-4 bounded
 * graph URL contract rather than inventing a parameter.
 */

/** A probe inside the router, so a test can read the link an action produced. */
let probeSearch = '';
function RouterProbe() {
  probeSearch = useLocation().search;
  return null;
}

function renderScreen(initialEntry = '/memory') {
  const view = render(
    <MemoryRouter
      initialEntries={[initialEntry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
      <RouterProbe />
    </MemoryRouter>,
  );
  // P33 S3 (D6): the Concept Lookup lives behind the "Concepts" internal tab.
  // These tests exercise the SAME card through the tabbed IA — the tablist
  // renders immediately (independent of the graph fetch), so open it here. The
  // ?concept= deep-link test passes its own entry and auto-selects the tab.
  if (!initialEntry.includes('concept=')) {
    fireEvent.click(view.getByRole('tab', { name: 'Concepts' }));
  }
  return view;
}

/** The single detail region of the master-detail layout (P36R S7). Replaces the
 *  P24.5 per-row accordion panel, which no longer exists. */
function detailPane(container: HTMLElement): HTMLElement {
  const pane = container.querySelector('.concept-lookup-detailpane');
  if (!pane) throw new Error('concept detail pane not found');
  return pane as HTMLElement;
}

const conceptPath = (id: string) => `GET /api/memory/concepts/${encodeURIComponent(id)}`;

const baseRoutes = {
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/files': { body: memoryFilesUnavailable },
  'GET /api/memory/concepts': { body: memoryConceptsAvailable },
  // Only reached when a graph action navigates to the Graph tab; stubbed so the
  // assertion about the LINK is not entangled with an unrouted fetch.
  'GET /api/memory/graph': { body: memoryGraphUnavailable },
};

/**
 * A local, wider list so a filter can be proven to select MORE than one row.
 * Built here rather than in the shared fixture module so no other suite's
 * expectations move. Two concepts share `docs/fake-note.md` and cluster 55.
 */
const conceptsForFiltering = {
  ...memoryConceptsAvailable,
  concepts: [
    ...memoryConceptsAvailable.concepts,
    {
      id: 'concept-sidecar',
      label: 'Sidecar audit trail',
      community_id: '55',
      community_name: null,
      source_file: 'docs/fake-note.md',
      on_disk: false,
    },
  ],
};

/**
 * The shape that made the aggregate missing-file note false: every anchored
 * concept's file is absent from this deployment, PLUS one concept whose anchor
 * the backend withheld — which names no document at all and can therefore never
 * be "a document you will need to open".
 */
const conceptsAllAnchorsAbsent = {
  ...memoryConceptsAvailable,
  concepts: [
    {
      id: 'concept-alpha',
      label: 'Alpha lead',
      community_id: null,
      community_name: null,
      source_file: 'docs/fake-alpha.md',
      on_disk: false,
    },
    {
      id: 'concept-beta',
      label: 'Beta lead',
      community_id: null,
      community_name: null,
      source_file: 'docs/fake-beta.md',
      on_disk: false,
    },
    {
      id: 'concept-withheld',
      label: 'Withheld anchor',
      community_id: null,
      community_name: null,
      source_file: null,
      on_disk: false,
    },
  ],
};

const rowButtons = (container: HTMLElement): HTMLElement[] =>
  Array.from(container.querySelectorAll<HTMLElement>('.concept-lookup-row-btn'));

afterEach(() => {
  vi.unstubAllGlobals();
  probeSearch = '';
});

describe('P24.5 · Concept Lookup — list', () => {
  it('renders exactly the stubbed concepts, with labels and community context (name or honest fallback)', async () => {
    stubFetchRoutes(baseRoutes);
    const { findByText, getByText, container } = renderScreen();
    await findByText('Concept Lookup');

    expect(rowButtons(container)).toHaveLength(memoryConceptsAvailable.concepts.length);

    for (const c of memoryConceptsAvailable.concepts) {
      expect(getByText(c.label)).toBeInTheDocument();
    }

    // community: real name, honest id-fallback, never invented
    expect(getByText('Export Pipeline')).toBeInTheDocument();
    expect(getByText('community 55')).toBeInTheDocument();

    // standing caption + honest subtitle
    expect(getByText('leads — open the cited file to verify')).toBeInTheDocument();
    expect(
      getByText('Concepts Graphify anchored in project docs — memory leads, not scientific conclusions.'),
    ).toBeInTheDocument();
  });

  it('shows an honest "N of M" count and no detail until something is selected', async () => {
    stubFetchRoutes(baseRoutes);
    const { findByText, getByText, container } = renderScreen();
    await findByText('Concept Lookup');

    expect(getByText('3 of 3')).toBeInTheDocument();
    expect(getByText('Select a concept to see where it is anchored.')).toBeInTheDocument();
    // Nothing was fetched for a concept nobody asked for.
    expect(container.querySelector('.concept-lookup-detail')).toBeNull();
  });
});

describe('P36R S7 · Concept Lookup — search', () => {
  it('narrows the master list by label and by id, and says so honestly when nothing matches', async () => {
    stubFetchRoutes(baseRoutes);
    const { findByText, getByRole, getByText, container } = renderScreen();
    await findByText('Concept Lookup');
    expect(rowButtons(container)).toHaveLength(3);

    const search = getByRole('searchbox', { name: /Search concepts/i });

    fireEvent.change(search, { target: { value: 'govern' } }); // label match
    expect(rowButtons(container)).toHaveLength(1);
    expect(getByText('Governance allowlist')).toBeInTheDocument();
    expect(getByText('1 of 3')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'concept-two' } }); // id match
    expect(rowButtons(container)).toHaveLength(1);
    expect(getByText('Two-layer architecture')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'zzz-nothing' } });
    expect(rowButtons(container)).toHaveLength(0);
    expect(getByText(/No concept matches the current search and filters/)).toBeInTheDocument();

    fireEvent.change(search, { target: { value: '' } });
    expect(rowButtons(container)).toHaveLength(3);
  });
});

describe('P36R S7 · Concept Lookup — category filters', () => {
  it('the cluster filter and the anchor-document filter each narrow the list to the real members', async () => {
    stubFetchRoutes({ ...baseRoutes, 'GET /api/memory/concepts': { body: conceptsForFiltering } });
    const { findByText, getByRole, getByText, container } = renderScreen();
    await findByText('Concept Lookup');
    expect(rowButtons(container)).toHaveLength(4);

    const cluster = getByRole('combobox', { name: /Cluster/i });
    // Cluster 55 holds two of the four concepts — the count in the option label
    // is the real membership, not a guess.
    expect(getByRole('option', { name: 'community 55 (2)' })).toBeInTheDocument();
    fireEvent.change(cluster, { target: { value: '55' } });
    expect(rowButtons(container)).toHaveLength(2);
    expect(getByText('2 of 4')).toBeInTheDocument();

    // "no cluster" is a real, honest bucket — never folded into a made-up one.
    fireEvent.change(cluster, { target: { value: '__no_cluster__' } });
    expect(rowButtons(container)).toHaveLength(1);
    expect(getByText('Two-layer architecture')).toBeInTheDocument();
    fireEvent.change(cluster, { target: { value: 'all' } });
    expect(rowButtons(container)).toHaveLength(4);

    const doc = getByRole('combobox', { name: /Anchor source/i });
    fireEvent.change(doc, { target: { value: 'docs/fake-note.md' } });
    expect(rowButtons(container)).toHaveLength(2);
    fireEvent.change(doc, { target: { value: 'README.md' } });
    expect(rowButtons(container)).toHaveLength(1);
  });
});

describe('P36R S7 · Concept Lookup — the aggregate missing-file note is true of the rows below it', () => {
  const AGGREGATE_NOTE =
    'This deployment does not carry any of the documents cited below — open them in the project to read them.';

  it('states the fact once when every VISIBLE anchored concept is absent, and withdraws it when the visible rows cite no document at all', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      'GET /api/memory/concepts': { body: conceptsAllAnchorsAbsent },
    });
    const { findByText, getByRole, getByText, queryByText, container } = renderScreen();
    await findByText('Concept Lookup');
    expect(rowButtons(container)).toHaveLength(3);

    // All three rows are visible; two cite a document and neither is carried
    // here, so the aggregate sentence is true of the documents cited below it.
    // (The third cites nothing, which is why the sentence is scoped to cited
    // documents rather than to "every concept below".)
    expect(getByText(AGGREGATE_NOTE)).toBeInTheDocument();

    // Filtering to the withheld-anchor concept leaves ZERO cited documents on
    // screen. The old note claimed "every concept below names a document you
    // will need to open in the project itself" — false for every visible row.
    // It must now be absent rather than false.
    // P36R S10 renamed the sentinel `__withheld__` → `__unlinked__` with the
    // option label "no linked source (N)": a null `source_file` also covers the
    // graph naming no source at all, so "anchor withheld" overclaimed.
    fireEvent.change(getByRole('combobox', { name: /Anchor source/i }), {
      target: { value: '__unlinked__' },
    });
    expect(rowButtons(container)).toHaveLength(1);
    expect(getByText('Withheld anchor')).toBeInTheDocument();
    expect(queryByText(AGGREGATE_NOTE)).toBeNull();
    // …and nothing else on screen makes the claim in other words.
    expect(container.textContent).not.toMatch(/every concept below/i);
    expect(container.textContent).not.toMatch(/snapshot/i);
  });

  it('does not show the aggregate note at all when the list is genuinely mixed', async () => {
    stubFetchRoutes(baseRoutes);
    const { findByText, queryByText } = renderScreen();
    await findByText('Concept Lookup');
    expect(queryByText(AGGREGATE_NOTE)).toBeNull();
  });
});

describe('P24.5 · Concept Lookup — detail (real leads)', () => {
  it('selecting a concept fetches its provenance and renders the anchor, community, related files, and related concepts', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');

    const row = getByRole('button', { name: /Provenance/ });
    expect(row).not.toHaveAttribute('aria-current');

    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-current', 'true');

    await findByText('src/other_mod.py');
    const scoped = within(detailPane(container));

    expect(scoped.getByRole('heading', { name: 'Provenance' })).toBeInTheDocument();
    expect(scoped.getByText('src/fake_mod.py')).toBeInTheDocument(); // anchor source_file
    expect(scoped.getByText('Export Pipeline')).toBeInTheDocument(); // community
    expect(scoped.getByText('concept-provenance')).toBeInTheDocument(); // concept id
    expect(scoped.getByText('src/other_mod.py')).toBeInTheDocument(); // related.files path
    expect(scoped.getByText('imports')).toBeInTheDocument(); // file relation
    expect(scoped.getByText('code')).toBeInTheDocument(); // file_type
    expect(scoped.getByText('Governance allowlist')).toBeInTheDocument(); // related.concepts label
    expect(scoped.getByText('relates_to')).toBeInTheDocument(); // concept relation
  });

  it('the plain-language description is assembled ONLY from returned fields — anchor, cluster, lead count', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /Provenance/ }));
    await findByText('src/other_mod.py');

    const scoped = within(detailPane(container));
    expect(
      scoped.getByText(
        `Project memory anchored this concept in src/fake_mod.py while indexing this project's own files. ` +
          `The graph groups it with the "Export Pipeline" cluster. ` +
          `2 related leads are recorded for it in the current graph.`,
      ),
    ).toBeInTheDocument();
  });

  it('describeConcept states an absent anchor / absent cluster / zero leads instead of filling them in', () => {
    expect(
      describeConcept(
        {
          id: 'x',
          label: 'X',
          community_id: null,
          community_name: null,
          source_file: null,
          on_disk: false,
        },
        0,
      ),
    ).toBe(
      // A null `source_file` covers BOTH "the graph node named no source" and
      // "the source it named is not served here" (memory.py::
      // _served_source_file), so the sentence must not assert that a withheld
      // source exists.
      'Project memory names no source document for this concept — the graph either recorded none or pointed at one this deployment does not serve. ' +
        'The graph puts it in no cluster. ' +
        'No related leads are recorded for it in the current graph.',
    );
  });

  it('does not repeat a cluster name back when upstream named the cluster after the concept itself', () => {
    expect(
      describeConcept(
        {
          id: 'c',
          label: 'Evidence sidecar',
          community_id: '130',
          community_name: 'Evidence sidecar',
          source_file: 'docs/notes.md',
          on_disk: false,
        },
        0,
      ),
    ).toContain('Its cluster in the graph carries the same name as the concept itself.');
  });
});

describe('P24.5 · Concept Lookup — empty-leads honesty', () => {
  it('shows the honest empty note when related is empty, still rendering the anchor provenance — never invented leads', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-governance')]: { body: memoryConceptDetailEmptyLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');

    fireEvent.click(getByRole('button', { name: /Governance allowlist/ }));

    await findByText('docs/fake-note.md'); // anchor source_file still renders
    const scoped = within(detailPane(container));

    expect(scoped.getByText('docs/fake-note.md')).toBeInTheDocument();
    // P36R S7 copy fix (corrected in review): user-facing language AND accurate
    // to what `on_disk` is — a backend FILESYSTEM existence check
    // (`memory.py::_on_disk`), never a statement about snapshot membership. The
    // surface must not claim a file is missing from the snapshot when the very
    // same snapshot is what serves its provenance.
    expect(
      scoped.getByText(
        'This deployment does not carry the file itself — open it in the project to read it.',
      ),
    ).toBeInTheDocument();
    expect(detailPane(container).textContent).not.toMatch(/snapshot/i);
    expect(
      scoped.getByText('no recorded leads for this concept in the current graph'),
    ).toBeInTheDocument();
    // never invented: no related-file/related-concept content in this panel
    expect(scoped.queryByText('Files')).toBeNull();
    expect(scoped.queryByText('Concepts')).toBeNull();
    // and no click that would lead nowhere is offered
    expect(scoped.queryByRole('button', { name: 'Browse connected items' })).toBeNull();
    expect(
      scoped.getByText(/The current graph records no references to or from it/),
    ).toBeInTheDocument();
  });
});

describe('P24.9 · Concept Lookup — null-anchor honesty', () => {
  // P36R S10: a null `source_file` has TWO shapes behind it
  // (`memory.py::_served_source_file`) — the graph named no source at all, or it
  // named one that is unsafe / not governance-served. The old copy ("anchor
  // withheld (excluded source)") asserted the second, i.e. that an excluded
  // source exists. The note must be true of either shape.
  it('renders an honest "no linked source" note (not an empty mono span, and never asserting an excluded source exists)', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-governance')]: { body: memoryConceptDetailWithheldAnchor },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');

    fireEvent.click(getByRole('button', { name: /Governance allowlist/ }));

    await findByText('no linked source');
    const pane = detailPane(container);
    const scoped = within(pane);

    // The honest null-anchor note is present...
    expect(scoped.getByText('no linked source')).toBeInTheDocument();
    // ...and it never asserts that an excluded source exists.
    expect(pane.textContent).not.toMatch(/withheld|excluded source/i);
    // ...and no empty mono span was rendered for the withheld anchor.
    expect(pane.querySelectorAll('.concept-lookup-anchor .mono')).toHaveLength(0);
    // The missing-file note is suppressed when there is no anchor path.
    expect(
      scoped.queryByText(
        'This deployment does not carry the file itself — open it in the project to read it.',
      ),
    ).toBeNull();
    // M5: with nothing citable, the boundary paragraph does not tell the reader
    // to open a source that was never named.
    expect(
      scoped.getByText(
        'A concept is a pointer into project documents — never a definition of the term, and never a scientific conclusion.',
      ),
    ).toBeInTheDocument();
    // No "open in Source Index" action for a path that was withheld.
    expect(scoped.queryByText('open in Source Index')).toBeNull();
  });
});

describe('P36R S7 · Concept Lookup — graph actions reuse the Slice-4 URL contract', () => {
  it('"Show in Graph Explore" produces ?tab=graph&gmode=explore&gnode=<id>, which decodes to a real select action', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /Provenance/ }));
    await findByText('src/other_mod.py');

    fireEvent.click(within(detailPane(container)).getByRole('button', { name: 'Show in Graph Explore' }));

    expect(probeSearch).toBe('?tab=graph&gmode=explore&gnode=concept-provenance');

    // Every graph parameter it emits is on the Slice-4 allowlist — no ad-hoc key.
    const emitted = new URLSearchParams(probeSearch);
    for (const key of emitted.keys()) {
      if (key === 'tab') continue;
      expect(GRAPH_URL_PARAMS as readonly string[]).toContain(key);
    }
    // …and the SHARED decoder turns it into the same actions a typed command would.
    expect(decodeGraphActions((k) => emitted.get(k))).toEqual([
      { kind: 'setMode', mode: 'explore' },
      { kind: 'select', nodeId: 'concept-provenance' },
    ]);
  });

  it('offers NO neighbourhood action even for a concept that has recorded leads — the projection has no concept edges — and says so instead of promising one', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /Provenance/ }));
    await findByText('src/other_mod.py');

    const scoped = within(detailPane(container));
    // This concept reports two leads, so the OLD behaviour offered "Browse
    // connected items" → ?gnbr=<conceptId>&gdepth=1. That link could never be
    // honoured: memory_graph.py::_build_edges builds edges ONLY from a file
    // summary's related.files[], never from a concept's related, so a concept
    // node has zero edges by construction and its 1-hop neighbourhood is always
    // empty. The action is withheld rather than annotated.
    expect(scoped.queryByRole('button', { name: 'Browse connected items' })).toBeNull();
    expect(scoped.queryByText(/1-hop neighbourhood/)).toBeNull();
    expect(
      scoped.getByText(
        /The graph's reference projection records no edges for concepts.*the leads below come from this concept's own record, not from that projection/,
      ),
    ).toBeInTheDocument();

    // The leads themselves are still real and still navigable — they are listed
    // in the panel, they are simply not edges of the graph projection.
    fireEvent.click(scoped.getByRole('button', { name: /src\/other_mod\.py/ }));
    expect(probeSearch).toBe('?file=src%2Fother_mod.py');
  });

  it('conceptGraphSearch emits only allowlisted graph parameters', () => {
    const sp = new URLSearchParams(conceptGraphSearch('some-concept'));
    for (const key of sp.keys()) {
      if (key === 'tab') continue;
      expect(GRAPH_URL_PARAMS as readonly string[]).toContain(key);
    }
    expect(sp.get('tab')).toBe('graph');
    // No neighbourhood parameters are produced for a concept at all.
    expect(sp.get('gnbr')).toBeNull();
    expect(sp.get('gdepth')).toBeNull();
  });

  it('the anchor source navigates into the Source Index for that file', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /Provenance/ }));
    await findByText('src/other_mod.py');

    fireEvent.click(within(detailPane(container)).getByRole('button', { name: /src\/fake_mod\.py/ }));
    expect(probeSearch).toBe('?file=src%2Ffake_mod.py');
  });
});

describe('P24.5 · Concept Lookup — unavailable', () => {
  it('renders a compact honest unavailable note, zero concept rows, no error/red styling', async () => {
    stubFetchRoutes({ ...baseRoutes, 'GET /api/memory/concepts': { body: memoryConceptsUnavailable } });
    const { findByText, container, queryByRole } = renderScreen();

    await findByText(/Concept lookup is unavailable/i);
    expect(rowButtons(container)).toHaveLength(0);
    expect(container.querySelector('.fetch-state.error')).toBeNull();
    expect(container.querySelector('.verdict-fail')).toBeNull();
    expect(container.textContent).not.toMatch(/\b(PASS|FAIL)\b/);
    // The degraded state offers no search/filter over a list that does not exist.
    expect(queryByRole('searchbox')).toBeNull();
    expect(container.querySelector('.concept-lookup-detailpane')).toBeNull();
  });
});

describe('P24.5 · Concept Lookup — keyboard accessibility', () => {
  it('arrow keys move the roving cursor WITHOUT selecting; activation is the native button click; a bare keydown selects nothing', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');

    expect(getByRole('heading', { name: 'Concept Lookup' })).toBeInTheDocument();

    const rows = rowButtons(container);
    expect(rows[0]).toHaveAccessibleName();
    // Roving tabindex: exactly one row is in the tab order.
    expect(rows.filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1);
    expect(rows[0]).toHaveAttribute('tabindex', '0');

    rows[0].focus();
    fireEvent.keyDown(rows[0], { key: 'ArrowDown' });
    expect(document.activeElement).toBe(rows[1]);
    expect(rows[1]).toHaveAttribute('tabindex', '0');
    // Moving the cursor is NOT selecting — nothing was fetched, nothing opened.
    expect(rows[1]).not.toHaveAttribute('aria-current');
    expect(container.querySelector('.concept-lookup-detail')).toBeNull();

    fireEvent.keyDown(rows[1], { key: 'End' });
    expect(document.activeElement).toBe(rows[rows.length - 1]);
    fireEvent.keyDown(rows[rows.length - 1], { key: 'Home' });
    expect(document.activeElement).toBe(rows[0]);

    // A raw Enter keydown must NOT select — that would prove a duplicate
    // handler exists beside the native button activation.
    fireEvent.keyDown(rows[0], { key: 'Enter' });
    expect(rows[0]).not.toHaveAttribute('aria-current');

    // The honest jsdom equivalent of real-browser Enter/Space activation on a
    // focused native <button> is focus + the browser-synthesized click.
    const provenance = getByRole('button', { name: /Provenance/ });
    provenance.focus();
    expect(document.activeElement).toBe(provenance);
    fireEvent.click(provenance);
    expect(provenance).toHaveAttribute('aria-current', 'true');
    await findByText('src/other_mod.py');
  });

  it('the search field is a real, labelled control that actually filters — not a decorative box', async () => {
    stubFetchRoutes(baseRoutes);
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');

    // P26 pinned "no INLINE search input on this screen" because the only search
    // then was the global ⌘K palette and a local box would have been decorative.
    // P36R S7 gives Concept Lookup a REAL search, so the invariant is restated
    // as what it always protected: any search input here must be labelled and
    // must genuinely narrow the list.
    const search = getByRole('searchbox', { name: /Search concepts/i });
    expect(search).toHaveAccessibleName();
    fireEvent.change(search, { target: { value: 'two-layer' } });
    expect(rowButtons(container)).toHaveLength(1);
  });
});

describe('P26.5 · Concept Lookup — search-palette deep link', () => {
  it('auto-selects the concept named by ?concept= on mount (memory-search navigation lands here)', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const view = renderScreen('/memory?concept=concept-provenance');

    const row = await view.findByRole('button', { name: /Provenance/ });
    expect(row).toHaveAttribute('aria-current', 'true'); // auto-selected from the URL param
    await view.findByText('src/other_mod.py'); // its provenance detail auto-fetched
  });
});

describe('P24.5 · Concept Lookup — no verdict or scientific-authority language', () => {
  it('never renders PASS/FAIL/valid/invalid, across available and unavailable states', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const available = renderScreen();
    await available.findByText('Concept Lookup');
    fireEvent.click(available.getByRole('button', { name: /Provenance/ }));
    await available.findByText('src/other_mod.py');
    expect(available.container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
    available.unmount();
    vi.unstubAllGlobals();

    stubFetchRoutes({ ...baseRoutes, 'GET /api/memory/concepts': { body: memoryConceptsUnavailable } });
    const unavailable = renderScreen();
    await unavailable.findByText(/Concept lookup is unavailable/i);
    expect(unavailable.container.textContent).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });

  it('never implies a concept is defined, confirmed, established or proven by this surface, and states the boundary', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /Provenance/ }));
    await findByText('src/other_mod.py');

    // The boundary sentence itself NEGATES two of these phrases ("never a
    // definition of the term"), so it is asserted separately and removed before
    // the scan — otherwise the disclaimer would trip the guard it exists for.
    const boundary =
      'A concept is a pointer into project documents — never a definition of the term, and never a ' +
      'scientific conclusion. Open the cited source to judge it yourself.';
    expect(within(detailPane(container)).getByText(boundary)).toBeInTheDocument();

    const text = (container.textContent ?? '').replace(boundary, '');
    // No AFFIRMATIVE claim of scientific authority anywhere else on the surface.
    expect(text).not.toMatch(
      /\b(definition of|defined as|means that|established|proven|confirmed finding|scientifically)\b/i,
    );
  });
});

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { ProjectMemory, conceptGraphSearch, describeConcept } from '../screens/ProjectMemory';
import { conceptDisplayTitle } from '../lib/displayLabels';
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
 *
 * P36V slice A refines it further, and this file now pins the refinements:
 *   · the master row and the detail heading show a DERIVED readable title
 *     (`lib/displayLabels.ts`) — presentation only, so the raw graph label is
 *     still what search matches and is still on screen verbatim inside the
 *     detail pane's Technical Details disclosure. Every assertion that used to
 *     pin the verbatim label now pins BOTH halves of that contract, which is
 *     strictly more than it pinned before.
 *   · Technical Details is collapsed by default and holds every raw identifier
 *     the pane knows — nothing was removed from the surface to make room for it.
 *   · a VISIBLE Clear Filters control finally backs the empty state's standing
 *     instruction to "clear the filters".
 *   · two duplicated sentences were removed (the standing "leads — open the
 *     cited file to verify" caption, and the restated cluster advisory). This
 *     file guards that their surviving claims are still made.
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

/*
 * Labels lifted VERBATIM from the committed snapshot's `concepts` array
 * (apps/api/isaac_api/data/memory-snapshot.json), so the derived-title contract
 * is exercised against REAL data shapes and not only against the tidy synthetic
 * labels above. `REAL_CODE_QUALIFIER` carries a code-only trailing group the
 * display title drops; `REAL_PROSE_QUALIFIER` carries a group that mixes an
 * identifier with prose and must therefore survive word for word;
 * `REAL_LONGEST` is the longest of the 19 (68 characters).
 */
const REAL_CODE_QUALIFIER = 'AI scientific consistency review (review.py NoOpReviewer)';
const REAL_PROSE_QUALIFIER = 'Export transform (export.py, deterministic, doubly gated)';
const REAL_LONGEST = 'Extraction interface seam (src/isaac_records/extract, Phase 2 stubs)';

const conceptsWithRealLabels = {
  ...memoryConceptsAvailable,
  concepts: [
    {
      id: 'docs_proposal_v2_ai_scientific_review',
      label: REAL_CODE_QUALIFIER,
      community_id: '128',
      community_name: REAL_CODE_QUALIFIER,
      source_file: 'docs/fake-proposal.md',
      on_disk: false,
    },
    {
      id: 'concept-export-transform',
      label: REAL_PROSE_QUALIFIER,
      community_id: '129',
      community_name: 'Export Pipeline',
      source_file: 'docs/fake-note.md',
      on_disk: false,
    },
    {
      id: 'concept-extract-seam',
      label: REAL_LONGEST,
      community_id: null,
      community_name: null,
      source_file: null,
      on_disk: false,
    },
  ],
};

const realConceptDetail = (index: 0 | 1 | 2) => ({
  plane: 'memory' as const,
  note: memoryConceptDetailWithLeads.note,
  available: true,
  concept: conceptsWithRealLabels.concepts[index],
  related: { files: [], concepts: [] },
});

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

    // P36V S-A: each row shows the DERIVED readable title of its own label.
    // These three fixture labels carry no code qualifier, so the derivation is
    // pure Title Case — the row text is still one-for-one with a real concept.
    for (const c of memoryConceptsAvailable.concepts) {
      expect(getByText(conceptDisplayTitle(c.label))).toBeInTheDocument();
    }
    expect(getByText('Governance Allowlist')).toBeInTheDocument();
    expect(getByText('Two-Layer Architecture')).toBeInTheDocument();

    // community: real name, honest id-fallback, never invented
    expect(getByText('Export Pipeline')).toBeInTheDocument();
    expect(getByText('community 55')).toBeInTheDocument();

    // honest subtitle — the ONE page-level explanation of what a concept is here
    expect(
      getByText('Concepts Graphify anchored in project docs — memory leads, not scientific conclusions.'),
    ).toBeInTheDocument();
    // P36V S-A concision: the standing caption said the same thing a third time
    // (the subtitle above and the detail pane's boundary note each still make the
    // claim), so it is gone — and no reworded stand-in took its place.
    expect(container.textContent).not.toMatch(/leads — open the cited file to verify/);
    expect(container.textContent).not.toMatch(/open the cited file/i);
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
    expect(getByText('Governance Allowlist')).toBeInTheDocument();
    expect(getByText('1 of 3')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'concept-two' } }); // id match
    expect(rowButtons(container)).toHaveLength(1);
    expect(getByText('Two-Layer Architecture')).toBeInTheDocument();

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
    expect(getByText('Two-Layer Architecture')).toBeInTheDocument();
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
    expect(getByText('Withheld Anchor')).toBeInTheDocument();
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
    // P36V S-A: the anchor path and the cluster name are each stated TWICE now —
    // once in their own labelled section, once raw inside Technical Details. The
    // count is pinned so a silent third copy (or a silent deletion) fails here.
    expect(scoped.getAllByText('src/fake_mod.py')).toHaveLength(2); // anchor source_file + raw
    expect(scoped.getAllByText('Export Pipeline')).toHaveLength(2); // cluster + raw cluster name
    expect(scoped.getByText('concept-provenance')).toBeInTheDocument(); // concept id (raw)
    expect(scoped.getByRole('button', { name: /src\/fake_mod\.py/ })).toBeInTheDocument();
    expect(scoped.getByText('src/other_mod.py')).toBeInTheDocument(); // related.files path
    // P36V PR2 slice B — the graph's own relation vocabulary now reads through
    // the closed five-value display map on this tab too, so `imports` shows as
    // "Imports" with the backend's exact string kept in the title. The concept↔
    // concept value below (`relates_to`) is OUTSIDE that measured set and is
    // therefore rendered verbatim — the fallthrough, proved on a real surface.
    const fileRelation = scoped.getByText('Imports');
    expect(fileRelation).toBeInTheDocument();
    expect(fileRelation).toHaveAttribute('title', 'imports');
    expect(scoped.queryByText('imports')).toBeNull();
    expect(scoped.getByText('code')).toBeInTheDocument(); // file_type
    // A related-lead CONCEPT label uses the SAME derivation as the row and the
    // detail heading. Rendering it verbatim made one concept read two ways on one
    // surface: the lead said "Governance allowlist", and activating it produced
    // the heading "Governance Allowlist". Both halves are pinned so neither the
    // derivation nor the old verbatim form can come back silently.
    expect(scoped.getByText('Governance Allowlist')).toBeInTheDocument(); // related.concepts label
    expect(scoped.queryByText('Governance allowlist')).toBeNull();
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
    const { findByText, findAllByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');

    fireEvent.click(getByRole('button', { name: /Governance Allowlist/ }));

    await findAllByText('docs/fake-note.md'); // anchor source_file still renders
    const scoped = within(detailPane(container));

    // Twice by design (P36V S-A): the Anchor Source link plus the raw path in
    // Technical Details. Pinned as a count so neither copy can vanish silently.
    expect(scoped.getAllByText('docs/fake-note.md')).toHaveLength(2);
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

    fireEvent.click(getByRole('button', { name: /Governance Allowlist/ }));

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
        /The graph's reference projection records no edges for concepts.*the leads above come from this concept's own record, not from that projection/,
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

// ---------------------------------------------------------------------------
// P36V slice A
// ---------------------------------------------------------------------------

/** The Technical Details disclosure of the resolved detail pane. */
function technicalDisclosure(container: HTMLElement): HTMLDetailsElement {
  const el = detailPane(container).querySelector('details.concept-lookup-technical');
  if (!el) throw new Error('Technical Details disclosure not found');
  return el as HTMLDetailsElement;
}

/** The `<dd>` beside a Technical Details `<dt>` label. */
function technicalValue(container: HTMLElement, label: string): string {
  const dt = Array.from(technicalDisclosure(container).querySelectorAll('dt')).find(
    (node) => node.textContent === label,
  );
  if (!dt) throw new Error(`Technical Details has no "${label}" row`);
  const dd = dt.parentElement?.querySelector('dd');
  if (!dd) throw new Error(`Technical Details "${label}" row has no value`);
  return dd.textContent ?? '';
}

describe('P36V S-A · Concepts — readable titles derived from real graph labels', () => {
  it('the master row and the detail heading show the derived title, not the raw graph label', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      'GET /api/memory/concepts': { body: conceptsWithRealLabels },
      [conceptPath('docs_proposal_v2_ai_scientific_review')]: { body: realConceptDetail(0) },
    });
    const { findByText, getByText, queryByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');

    // Code-only trailing group dropped …
    expect(getByText('AI Scientific Consistency Review')).toBeInTheDocument();
    expect(queryByText(REAL_CODE_QUALIFIER)).toBeNull(); // not in the list
    // … prose-bearing group KEPT word for word (deleting it would delete meaning).
    expect(getByText('Export Transform (export.py, deterministic, doubly gated)')).toBeInTheDocument();
    // … and the longest real label, group intact because "Phase 2 stubs" is prose.
    expect(
      getByText('Extraction Interface Seam (src/isaac_records/extract, Phase 2 stubs)'),
    ).toBeInTheDocument();

    fireEvent.click(getByRole('button', { name: /AI Scientific Consistency Review/ }));
    const heading = await findByText('AI Scientific Consistency Review', { selector: 'h3' });
    expect(heading).toBeInTheDocument();
    // The detail region's accessible name is the derived title.
    expect(detailPane(container)).toHaveAccessibleName('AI Scientific Consistency Review');
  });

  it('the RAW graph label survives verbatim in Technical Details — nothing was deleted, only relocated', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      'GET /api/memory/concepts': { body: conceptsWithRealLabels },
      [conceptPath('docs_proposal_v2_ai_scientific_review')]: { body: realConceptDetail(0) },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /AI Scientific Consistency Review/ }));
    await findByText('Technical Details');

    // The no-data-loss guarantee: the exact string the graph stores is on screen.
    expect(technicalValue(container, 'Graph Label')).toBe(REAL_CODE_QUALIFIER);
    // Twice, because this concept's cluster is named after the concept itself —
    // Graph Label and Cluster Name are legitimately the same string here.
    expect(within(technicalDisclosure(container)).getAllByText(REAL_CODE_QUALIFIER)).toHaveLength(2);
    // …together with every other raw identifier the pane knows.
    expect(technicalValue(container, 'Concept ID')).toBe('docs_proposal_v2_ai_scientific_review');
    expect(technicalValue(container, 'Source File')).toBe('docs/fake-proposal.md');
    expect(technicalValue(container, 'Cluster Name')).toBe(REAL_CODE_QUALIFIER);
    expect(technicalValue(container, 'Cluster ID')).toBe('128');
  });

  it('search still matches the RAW label — a fragment the derived title hides still finds the row', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      'GET /api/memory/concepts': { body: conceptsWithRealLabels },
    });
    const { findByText, getByRole, getByText, container } = renderScreen();
    await findByText('Concept Lookup');

    const search = getByRole('searchbox', { name: /Search concepts/i });
    // "NoOpReviewer" exists ONLY in the raw label — the row shows the derived
    // title. If the derivation had been written into state, this would find zero.
    fireEvent.change(search, { target: { value: 'NoOpReviewer' } });
    expect(rowButtons(container)).toHaveLength(1);
    expect(getByText('AI Scientific Consistency Review')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'review.py' } });
    expect(rowButtons(container)).toHaveLength(1);
  });

  it('renders the longest real label with no nowrap constraint anywhere in the Concepts styles', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      'GET /api/memory/concepts': { body: conceptsWithRealLabels },
      [conceptPath('concept-extract-seam')]: { body: realConceptDetail(2) },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');

    const longTitle = 'Extraction Interface Seam (src/isaac_records/extract, Phase 2 stubs)';
    fireEvent.click(getByRole('button', { name: new RegExp('Extraction Interface Seam') }));
    await findByText('Technical Details');
    expect(await findByText(longTitle, { selector: 'h3' })).toBeInTheDocument();

    // jsdom has no layout engine, so overflow is guarded structurally: the row
    // label, the detail heading and every mono raw value must be free to wrap,
    // and no Concepts rule may pin `white-space: nowrap` (the one declaration
    // that would force a 68-character label to push <main> sideways at 375px).
    const label = container.querySelector('.concept-lookup-label');
    expect(label).not.toBeNull();
    for (const el of [
      label as Element,
      detailPane(container).querySelector('.concept-lookup-detail-heading') as Element,
      technicalDisclosure(container).querySelector('dd') as Element,
    ]) {
      expect(getComputedStyle(el).whiteSpace).not.toBe('nowrap');
    }
  });
});

describe('P36V S-A · Concepts — Technical Details disclosure', () => {
  it('is collapsed by default, natively keyboard-operable, and named by its own summary', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /Provenance/ }));
    await findByText('Technical Details');

    const details = technicalDisclosure(container);
    expect(details.open).toBe(false);
    expect(details).not.toHaveAttribute('open');

    // A native <summary> as the FIRST child is what makes it reachable by Tab
    // and operable by Enter/Space with no JS and no ARIA of ours.
    const summary = details.firstElementChild as HTMLElement;
    expect(summary.tagName).toBe('SUMMARY');
    expect(summary.textContent).toBe('Technical Details'); // Title Case
    expect(details.querySelectorAll('summary')).toHaveLength(1);

    // Opening it reveals the raw values (they are in the DOM either way, which is
    // why the row values are asserted by <dt> pairing rather than by visibility).
    fireEvent.click(summary);
    expect(details.open).toBe(true);
    expect(technicalValue(container, 'Concept ID')).toBe('concept-provenance');
  });

  it('states an absent raw value as "—" rather than an empty row, and never as an invented one', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-governance')]: { body: memoryConceptDetailWithheldAnchor },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /Governance Allowlist/ }));
    await findByText('Technical Details');

    expect(technicalValue(container, 'Source File')).toBe('—');
    expect(technicalValue(container, 'Cluster Name')).toBe('—');
    expect(technicalValue(container, 'Cluster ID')).toBe('55');
    expect(technicalValue(container, 'Graph Label')).toBe('Governance allowlist');
  });

  it('the detail pane reads title → description → Anchor Source → Cluster → Related Leads → graph action → Technical Details', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /Provenance/ }));
    await findByText('Technical Details');

    const pane = detailPane(container);
    const order = Array.from(
      pane.querySelectorAll('h3, .concept-lookup-description, h4, .concept-lookup-actions, summary'),
    ).map((el) => {
      if (el.tagName === 'H3') return 'TITLE';
      if (el.classList.contains('concept-lookup-description')) return 'DESCRIPTION';
      if (el.classList.contains('concept-lookup-actions')) return 'ACTIONS';
      return el.textContent ?? '';
    });

    expect(order).toEqual([
      'TITLE',
      'DESCRIPTION',
      'Anchor Source',
      'Cluster',
      'Related Leads',
      'ACTIONS',
      'Technical Details',
    ]);
    expect(within(pane).getByRole('button', { name: 'Show in Graph Explore' })).toBeInTheDocument();
    // Section labels are Title Case; the description stays sentence case.
    for (const name of ['Anchor Source', 'Cluster', 'Related Leads']) {
      expect(within(pane).getByRole('heading', { name, level: 4 })).toBeInTheDocument();
    }
  });
});

describe('P36V S-A · Concepts — visible Clear Filters', () => {
  const clearName = { name: 'Clear Filters' } as const;

  it('appears only while something is narrowing the list, and resets search + both filters without changing filter semantics', async () => {
    stubFetchRoutes({ ...baseRoutes, 'GET /api/memory/concepts': { body: conceptsForFiltering } });
    const { findByText, getByRole, queryByRole, getByText, container } = renderScreen();
    await findByText('Concept Lookup');

    // Nothing active → no control (it would have nothing to do).
    expect(queryByRole('button', clearName)).toBeNull();
    expect(rowButtons(container)).toHaveLength(4);

    const search = getByRole('searchbox', { name: /Search concepts/i });
    fireEvent.change(search, { target: { value: 'govern' } });
    expect(getByRole('button', clearName)).toBeInTheDocument();
    expect(rowButtons(container)).toHaveLength(1);

    fireEvent.click(getByRole('button', clearName));
    expect(rowButtons(container)).toHaveLength(4);
    expect((search as HTMLInputElement).value).toBe('');
    expect(queryByRole('button', clearName)).toBeNull();

    // A filter alone shows it too, and one click clears BOTH selects at once.
    const cluster = getByRole('combobox', { name: /Cluster/i });
    const doc = getByRole('combobox', { name: /Anchor source/i });
    fireEvent.change(cluster, { target: { value: '55' } });
    fireEvent.change(doc, { target: { value: 'docs/fake-note.md' } });
    expect(getByRole('button', clearName)).toBeInTheDocument();
    expect(rowButtons(container)).toHaveLength(2);

    fireEvent.click(getByRole('button', clearName));
    expect((cluster as HTMLSelectElement).value).toBe('all');
    expect((doc as HTMLSelectElement).value).toBe('all');
    expect(rowButtons(container)).toHaveLength(4);
    expect(getByText('4 of 4')).toBeInTheDocument();
  });

  it('closes the empty state’s dead end — the instruction to clear the filters now has a control beside it', async () => {
    stubFetchRoutes(baseRoutes);
    const { findByText, getByRole, getByText, container } = renderScreen();
    await findByText('Concept Lookup');

    fireEvent.change(getByRole('searchbox', { name: /Search concepts/i }), {
      target: { value: 'zzz-nothing' },
    });
    expect(rowButtons(container)).toHaveLength(0);
    expect(getByText(/widen the search or clear the filters/)).toBeInTheDocument();

    const clear = getByRole('button', clearName);
    expect(clear).toBeInTheDocument();
    fireEvent.click(clear);
    expect(rowButtons(container)).toHaveLength(3);
  });

  it('hands focus to the search box instead of dropping it, since the button unmounts itself', async () => {
    stubFetchRoutes(baseRoutes);
    const { findByText, getByRole, queryByRole } = renderScreen();
    await findByText('Concept Lookup');

    const search = getByRole('searchbox', { name: /Search concepts/i });
    fireEvent.change(search, { target: { value: 'zzz-nothing' } });

    const clear = getByRole('button', clearName);
    clear.focus();
    expect(document.activeElement).toBe(clear);
    fireEvent.click(clear);

    // The control removed its own subtree. Without a deliberate move,
    // `document.activeElement` becomes <body> and a keyboard user is dumped at
    // the top of the document.
    expect(queryByRole('button', clearName)).toBeNull();
    expect(document.activeElement).toBe(search);
    expect(document.activeElement).not.toBe(document.body);
  });
});

describe('P36V S-A · Concepts — concision without deleting a claim', () => {
  it('states the cluster advisory ONCE, keeping the unique on-screen singleton count', async () => {
    stubFetchRoutes({ ...baseRoutes, 'GET /api/memory/concepts': { body: conceptsForFiltering } });
    const { findByText, getByText, container } = renderScreen();
    await findByText('Concept Lookup');

    // The unique fact (how many of the clusters ON SCREEN hold one concept) and
    // the advisory qualifier now live in one sentence instead of two.
    expect(
      getByText(
        '1 of the 2 clusters represented here hold a single concept — advisory groupings from the upstream graph builder, not schema categories.',
      ),
    ).toBeInTheDocument();
    // The long restatement that MemoryGraphCard and GraphHelp already carry in
    // full on the Graph tab of this same screen is gone from Concepts.
    expect(container.textContent).not.toMatch(/Clusters are derived automatically/);
    expect(container.querySelectorAll('.concept-lookup-filter-note')).toHaveLength(1);
    // …and the claim itself is not lost: it is still made here, once.
    expect(container.textContent).toMatch(/advisory groupings/);
  });

  it('makes each surviving advisory claim exactly once on the resolved surface', async () => {
    stubFetchRoutes({
      ...baseRoutes,
      [conceptPath('concept-provenance')]: { body: memoryConceptDetailWithLeads },
    });
    const { findByText, getByRole, container } = renderScreen();
    await findByText('Concept Lookup');
    fireEvent.click(getByRole('button', { name: /Provenance/ }));
    await findByText('Technical Details');

    const text = container.textContent ?? '';
    const count = (needle: string) => text.split(needle).length - 1;
    expect(count('memory leads, not scientific conclusions')).toBe(1); // page-level
    expect(count('never a definition of the term')).toBe(1); // advisory note
    expect(count('Open the cited source to judge it yourself')).toBe(1);
    expect(count('leads — open the cited file to verify')).toBe(0); // removed
  });
});

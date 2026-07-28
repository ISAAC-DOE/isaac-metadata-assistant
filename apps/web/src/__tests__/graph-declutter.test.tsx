import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  buildGraphIndex,
  filteredNodeIds,
  initialGraphViewState,
  visibleEdges,
  visibleNodeIds,
  type GraphIndex,
  type GraphViewState,
} from '../lib/graphModel';
import { RELATION_DISPLAY_LABELS } from '../lib/displayLabels';
import {
  hiddenFilterCount,
  hiddenRelationTypes,
  relationToggleAction,
} from '../screens/graph/GraphFilters';
import type { ApiMemoryGraphResponse } from '../lib/types';
import { stubFetchRoutes, graphStatusUnavailable, memoryGraphAvailable } from '../test/apiFixtures';

/*
 * P36V PR2 slice B — graph decluttering: progressive disclosure, active-filter
 * chips, the Find a Path tool, and the humanisation boundary.
 *
 * The contract this file pins, in order of how much it would cost to get wrong:
 *
 *  1. FILTER SEMANTICS ARE UNCHANGED. The controls moved behind a disclosure and
 *     grew a chip row; what they DO is byte-for-byte the same. Every case below
 *     compares the set of nodes the mounted surface actually renders against the
 *     set `lib/graphModel.ts` computes for the equivalent state — so a rewiring
 *     that quietly changes which nodes survive a filter fails here, and cannot
 *     be papered over by also changing the expectation (the expectation is
 *     derived from the model, not written out by hand).
 *  2. NOTHING WAS DELETED. A full control inventory: every control that existed
 *     on the surface before this slice is still reachable, by name.
 *  3. THE CHIPS CANNOT LIE. A collapsed Filters panel must never hide a narrowed
 *     view: whatever is on has a chip, each chip removes exactly its own filter,
 *     and Clear All Filters restores the default view including the search box.
 *     Two invariants make "cannot lie" checkable rather than aspirational, and
 *     both are pinned against a FIVE-relation payload (the real projection's own
 *     vocabulary) because the earlier one- and two-relation fixtures could not
 *     tell "chips the hidden set" apart from "chips the kept set":
 *       (a) the number of non-search chips EQUALS the number on the Filters
 *           trigger, always;
 *       (b) every X in the row WIDENS the visible set — a row whose controls
 *           narrow is a row that means the opposite of what it says.
 *  4. THE GRAPH DATA IS NOT TOUCHED. The fetched payload is byte-identical after
 *     mounting, filtering, charting a path and clearing.
 *
 * The five real relation values and the verbatim fallthrough are unit-pinned in
 * display-labels.test.ts; this file checks they reach the surface.
 */

function renderGraphTab(body: unknown = memoryGraphAvailable) {
  const view = render(
    <MemoryRouter
      initialEntries={['/memory']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
    </MemoryRouter>,
  );
  fireEvent.click(view.getByRole('tab', { name: 'Graph' }));
  void body;
  return view;
}

const routes = (body: unknown = memoryGraphAvailable) => ({
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/graph': { body },
});

const toBrowse = (view: RenderResult) => fireEvent.click(view.getByRole('radio', { name: 'Browse' }));
const openFilters = (view: RenderResult) =>
  fireEvent.click(view.getByRole('button', { name: /^Filters/ }));
const openPath = (view: RenderResult) =>
  fireEvent.click(view.getByRole('button', { name: 'Find a Path' }));

/** The labels the Browse list is currently rendering, in DOM order. */
const browseLabels = (): string[] =>
  [...document.querySelectorAll('.memory-graph-list-label')].map((el) => el.textContent ?? '');

/** The chip labels currently shown, in DOM order. */
const chipLabels = (): string[] =>
  [...document.querySelectorAll('.memory-graph-chip-label')].map((el) => el.textContent ?? '');

/** The accessible name of every chip remove control, in DOM order. */
const chipRemoveLabels = (): string[] =>
  [...document.querySelectorAll('.memory-graph-chip-remove')].map(
    (el) => el.getAttribute('aria-label') ?? '',
  );

const chipCount = () => document.querySelectorAll('.memory-graph-chip').length;

const edgeCount = () => document.querySelectorAll('.memory-graph-edge').length;

/** The `data-edge` keys the canvas is currently drawing. */
const drawnEdges = (): Set<string> =>
  new Set(
    [...document.querySelectorAll('.memory-graph-edge')].map((l) => l.getAttribute('data-edge') ?? ''),
  );

/** The count line's own figure — how many nodes the surface says it is showing. */
const shownNodeCount = (): number => {
  const text = document.querySelector('.memory-graph-list-summary')?.textContent ?? '';
  return Number(/^(\d+) of/.exec(text)?.[1] ?? NaN);
};

/** The number on the Filters trigger (0 when it reports none). */
const triggerCount = (view: RenderResult): number => {
  const text = view.getByRole('button', { name: /^Filters/ }).textContent ?? '';
  return Number(/(\d+)/.exec(text)?.[1] ?? 0);
};

/** Chips that are NOT the search chip — the ones the trigger's count covers. */
const nonSearchChipCount = (): number =>
  [...document.querySelectorAll('.memory-graph-chip-label')].filter(
    (el) => !(el.textContent ?? '').startsWith('Search:'),
  ).length;

/**
 * A two-relation fixture. The shipped one carries a single relation value, which
 * cannot distinguish "the chip row lists each selected type" from "the chip row
 * prints the whole vocabulary".
 */
const twoRelationGraph: ApiMemoryGraphResponse = {
  ...(memoryGraphAvailable as unknown as ApiMemoryGraphResponse),
  edges: [
    { source: 'src/fake_mod.py', target: 'src/other_mod.py', relations: ['imports'] },
    { source: 'src/fake_mod.py', target: 'docs/fake-note.md', relations: ['references'] },
  ],
};

/**
 * The REAL projection's relation vocabulary, all five values, spread over three
 * edges: `references 389 · imports 382 · calls 160 · imports_from 69 ·
 * shares_data_with 2` in the committed snapshot.
 *
 * Every fixture before this one carried one or two relation types, and with one
 * or two types "chip the hidden set" and "chip the kept set" produce the same
 * single chip. That is precisely how a chip row that named the FOUR kept types
 * while claiming "Filters 1 active" — and whose every X removed hundreds more
 * edges — passed a full green suite.
 */
const fiveRelationGraph: ApiMemoryGraphResponse = {
  ...(memoryGraphAvailable as unknown as ApiMemoryGraphResponse),
  edges: [
    { source: 'src/fake_mod.py', target: 'src/other_mod.py', relations: ['imports', 'calls'] },
    { source: 'src/fake_mod.py', target: 'docs/fake-note.md', relations: ['references'] },
    {
      source: 'src/other_mod.py',
      target: 'docs/fake-note.md',
      relations: ['imports_from', 'shares_data_with'],
    },
  ],
};

/** The five display labels, in `index.relationTypes` (sorted) order. */
const FIVE_LABELS = ['Calls', 'Imports', 'Imports From', 'References', 'Shares Data With'];
const FIVE_RAW = ['calls', 'imports', 'imports_from', 'references', 'shares_data_with'];

/** The model's own answer for a state — the expectation is DERIVED, never typed out. */
function modelIndex(payload: unknown = memoryGraphAvailable): GraphIndex {
  return buildGraphIndex(payload as ApiMemoryGraphResponse);
}
function modelVisibleLabels(index: GraphIndex, partial: Partial<GraphViewState>): string[] {
  const state: GraphViewState = { ...initialGraphViewState('browse'), ...partial };
  return filteredNodeIds(state, index).map((id) => index.byId.get(id)?.label ?? id);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- 1. filter semantics are unchanged --------------------------------------

describe('graph filters — same inputs, same visible sets', () => {
  it('node type / cluster / search / combined all match the model exactly', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);
    openFilters(view);
    const index = modelIndex();

    // baseline: nothing filtered
    expect(browseLabels().sort()).toEqual(modelVisibleLabels(index, {}).sort());

    // node type
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'concept' } });
    expect(browseLabels().sort()).toEqual(
      modelVisibleLabels(index, { typeFilter: 'concept' }).sort(),
    );
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'all' } });

    // cluster
    fireEvent.change(view.getByLabelText('Cluster'), { target: { value: '131' } });
    expect(browseLabels().sort()).toEqual(
      modelVisibleLabels(index, { communityFilter: '131' }).sort(),
    );

    // cluster AND node type together — they combine, they do not replace
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });
    expect(browseLabels().sort()).toEqual(
      modelVisibleLabels(index, { communityFilter: '131', typeFilter: 'file' }).sort(),
    );

    // search, on top of both
    fireEvent.change(view.getByLabelText('Search graph nodes'), { target: { value: 'fake' } });
    expect(browseLabels().sort()).toEqual(
      modelVisibleLabels(index, {
        communityFilter: '131',
        typeFilter: 'file',
        search: 'fake',
      }).sort(),
    );
  });

  it('the relationship filter removes exactly the edges the model removes', async () => {
    stubFetchRoutes(routes(twoRelationGraph));
    const view = renderGraphTab(twoRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);
    const index = modelIndex(twoRelationGraph);

    const modelEdges = (relationFilter: string[] | null) => {
      const state: GraphViewState = { ...initialGraphViewState('explore'), relationFilter };
      return visibleEdges(state, index, new Set(visibleNodeIds(state, index))).length;
    };

    expect(edgeCount()).toBe(modelEdges(null));
    fireEvent.click(view.getByRole('checkbox', { name: 'Imports' }));
    expect(edgeCount()).toBe(modelEdges(['references']));
    fireEvent.click(view.getByRole('checkbox', { name: 'References' }));
    expect(edgeCount()).toBe(modelEdges([]));
    expect(edgeCount()).toBe(0); // an explicit "no types" honestly draws none
  });

  it('the panel is a disclosure only — closing it changes no filter', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);
    openFilters(view);
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'concept' } });
    const filtered = browseLabels();

    openFilters(view); // collapse
    expect(view.queryByLabelText('Node Type')).toBeNull();
    expect(browseLabels()).toEqual(filtered);
    openFilters(view); // re-open: the control still shows the active value
    expect((view.getByLabelText('Node Type') as HTMLSelectElement).value).toBe('concept');
  });
});

// --- 2. nothing was deleted -------------------------------------------------

describe('graph toolbar — progressive disclosure without deletion', () => {
  it('the primary toolbar carries exactly the always-visible controls', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });

    // Immediately visible, no disclosure needed.
    expect(view.getByRole('radio', { name: 'Explore' })).toBeInTheDocument();
    expect(view.getByRole('radio', { name: 'Browse' })).toBeInTheDocument();
    expect(view.getByLabelText('Search graph nodes')).toBeInTheDocument();
    expect(view.getByRole('button', { name: /^Filters/ })).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Find a Path' })).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'About This Graph' })).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Fit to View' })).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'Reset View' })).toBeInTheDocument();
    expect(document.querySelector('.graph-cmd-input')).not.toBeNull();

    // …and both disclosures start CLOSED, so the row is not thirteen deep.
    for (const name of [/^Filters/, /^Find a Path$/]) {
      expect(view.getByRole('button', { name })).toHaveAttribute('aria-expanded', 'false');
    }
    expect(view.queryByLabelText('Node Type')).toBeNull();
    expect(view.queryByLabelText('Cluster')).toBeNull();
    expect(view.queryByLabelText('Find a Cluster')).toBeNull();
    expect(view.queryByLabelText('From')).toBeNull();
    expect(view.queryByLabelText('To')).toBeNull();
    expect(view.queryByRole('group', { name: 'Relationship Types' })).toBeNull();
  });

  it('every pre-slice control is still reachable — the full inventory', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);
    openFilters(view);
    openPath(view);

    /*
     * BEFORE this slice the surface carried these thirteen controls, all mounted
     * at once: Explore, Browse, search, "Show" (node type), "Find a cluster",
     * "Cluster", "Group by" (Browse only), one checkbox per relation type,
     * "Path from", "Path to", "Find path", "Clear filters", and the command bar
     * — plus the canvas toolbar's Fit / Zoom in / Zoom out / Reset.
     *
     * AFTER: the same controls, renamed to Title Case and split between the
     * primary toolbar and two disclosures. NONE was removed. `Clear filters`
     * became `Clear All Filters` and moved out of the path form, where it never
     * belonged, into the chip row — so it is asserted with a filter on.
     */
    for (const label of ['Search graph nodes', 'Node Type', 'Find a Cluster', 'Cluster', 'Group By', 'From', 'To']) {
      expect(view.getByLabelText(label), `missing labelled control: ${label}`).toBeInTheDocument();
    }
    for (const name of ['Explore', 'Browse']) {
      expect(view.getByRole('radio', { name })).toBeInTheDocument();
    }
    for (const name of ['Find Path', 'About This Graph', /^Filters/, 'Find a Path']) {
      expect(view.getByRole('button', { name }), `missing button: ${String(name)}`).toBeInTheDocument();
    }
    expect(view.getByRole('checkbox', { name: 'Imports' })).toBeInTheDocument();
    expect(document.querySelector('.graph-cmd-input')).not.toBeNull();

    // Clear All Filters: present as soon as anything is filtering.
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });
    expect(view.getByRole('button', { name: 'Clear All Filters' })).toBeInTheDocument();
  });

  it('the Filters button reports how many filters are on', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    const trigger = () => view.getByRole('button', { name: /^Filters/ });
    expect(trigger().textContent).toBe('Filters');

    openFilters(view);
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });
    expect(trigger().textContent).toContain('1');
    fireEvent.change(view.getByLabelText('Cluster'), { target: { value: '131' } });
    expect(trigger().textContent).toContain('2');
    fireEvent.click(view.getByRole('checkbox', { name: 'Imports' }));
    expect(trigger().textContent).toContain('3');
    // The count is announced, not colour-only.
    expect(trigger().getAttribute('aria-expanded')).toBe('true');
    expect(view.getByRole('button', { name: /Filters 3 active/ })).toBeInTheDocument();

    // Search is NOT counted: its box never left the toolbar, so counting it
    // would claim a hidden filter that is in plain sight.
    fireEvent.change(view.getByLabelText('Search graph nodes'), { target: { value: 'fake' } });
    expect(trigger().textContent).toContain('3');
  });
});

// --- 3. the chips cannot lie ------------------------------------------------

describe('graph active-filter chips', () => {
  it('are absent when nothing is filtering', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    expect(document.querySelector('.memory-graph-chips')).toBeNull();
    expect(view.queryByRole('button', { name: 'Clear All Filters' })).toBeNull();
  });

  it('name every active filter readably, with the raw value kept on the chip', async () => {
    stubFetchRoutes(routes(twoRelationGraph));
    const view = renderGraphTab(twoRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);

    fireEvent.change(view.getByLabelText('Search graph nodes'), { target: { value: 'fake' } });
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });
    fireEvent.change(view.getByLabelText('Cluster'), { target: { value: '131' } });
    fireEvent.click(view.getByRole('checkbox', { name: 'References' }));

    expect(chipLabels()).toEqual([
      'Search: fake',
      'Files Only',
      // The cluster name VERBATIM — never re-cased, never rewritten.
      'Cluster: Export Pipeline · 1 file',
      // Unticking References HIDES references — so that, and not the still-shown
      // `imports`, is what the chip names.
      'Hiding: References',
    ]);
    // The raw underlying values stay on the chips.
    const titles = [...document.querySelectorAll('.memory-graph-chip')].map((c) =>
      c.getAttribute('title'),
    );
    expect(titles).toEqual(['fake', 'file', '131', 'references']);
  });

  it('says so honestly when NO relationship type is selected', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);
    fireEvent.click(view.getByRole('checkbox', { name: 'Imports' })); // the only type
    // The chip names the type being WITHHELD, and the row states in words the one
    // thing a list of "Hiding: …" chips cannot state by itself.
    expect(chipLabels()).toEqual(['Hiding: Imports']);
    expect(document.querySelector('.memory-graph-chips-note')?.textContent).toMatch(
      /No references are drawn — every relationship type is hidden\./,
    );
    expect(edgeCount()).toBe(0);
    // The note is prose, not a control: it has nothing to remove.
    expect(chipCount()).toBe(1);
  });

  it('all five types unticked: five chips, each naming a hidden type, each X restoring one', async () => {
    stubFetchRoutes(routes(fiveRelationGraph));
    const view = renderGraphTab(fiveRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);

    for (const label of FIVE_LABELS) fireEvent.click(view.getByRole('checkbox', { name: label }));

    expect(chipLabels()).toEqual(FIVE_LABELS.map((l) => `Hiding: ${l}`));
    expect(chipRemoveLabels()).toEqual(FIVE_LABELS.map((l) => `Show ${l} references again`));
    expect(triggerCount(view)).toBe(5);
    expect(nonSearchChipCount()).toBe(5);
    expect(edgeCount()).toBe(0);
    expect(document.querySelector('.memory-graph-chips-note')).not.toBeNull();

    // …and the all-hidden state is not a dead end: one X widens out of it.
    fireEvent.click(view.getByRole('button', { name: 'Show Imports references again' }));
    expect(edgeCount()).toBeGreaterThan(0);
    expect(chipLabels()).not.toContain('Hiding: Imports');
    expect(triggerCount(view)).toBe(4);
    expect(document.querySelector('.memory-graph-chips-note')).toBeNull();
  });

  it('removing one chip removes exactly that filter and nothing else', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);
    openFilters(view);
    const index = modelIndex();

    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });
    fireEvent.change(view.getByLabelText('Cluster'), { target: { value: '131' } });
    expect(browseLabels().sort()).toEqual(
      modelVisibleLabels(index, { typeFilter: 'file', communityFilter: '131' }).sort(),
    );

    fireEvent.click(view.getByRole('button', { name: 'Clear the cluster filter' }));
    // The cluster filter is gone; the node-type filter is untouched.
    expect(chipLabels()).toEqual(['Files Only']);
    expect(browseLabels().sort()).toEqual(modelVisibleLabels(index, { typeFilter: 'file' }).sort());
    expect((view.getByLabelText('Cluster') as HTMLSelectElement).value).toBe('all');
    expect((view.getByLabelText('Node Type') as HTMLSelectElement).value).toBe('file');

    fireEvent.click(view.getByRole('button', { name: 'Clear the node type filter' }));
    expect(document.querySelector('.memory-graph-chips')).toBeNull();
    expect(browseLabels().sort()).toEqual(modelVisibleLabels(index, {}).sort());
  });

  it('removing a relationship chip RE-TICKS exactly that type', async () => {
    stubFetchRoutes(routes(twoRelationGraph));
    const view = renderGraphTab(twoRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);

    fireEvent.click(view.getByRole('checkbox', { name: 'References' }));
    expect(chipLabels()).toEqual(['Hiding: References']);
    fireEvent.click(view.getByRole('button', { name: 'Show References references again' }));
    // Back to no relationship filter at all: both types ticked, no chip left.
    expect(chipLabels()).toEqual([]);
    expect((view.getByRole('checkbox', { name: 'Imports' }) as HTMLInputElement).checked).toBe(true);
    expect((view.getByRole('checkbox', { name: 'References' }) as HTMLInputElement).checked).toBe(
      true,
    );
  });

  it('Clear All Filters restores the default view, search box included', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);
    openFilters(view);
    openPath(view);
    const index = modelIndex();

    fireEvent.change(view.getByLabelText('Search graph nodes'), { target: { value: 'fake' } });
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });
    fireEvent.change(view.getByLabelText('Cluster'), { target: { value: '131' } });
    fireEvent.change(view.getByLabelText('Find a Cluster'), { target: { value: 'export' } });
    fireEvent.change(view.getByLabelText('From'), { target: { value: 'src/fake_mod.py' } });

    fireEvent.click(view.getByRole('button', { name: 'Clear All Filters' }));

    expect(document.querySelector('.memory-graph-chips')).toBeNull();
    expect((view.getByLabelText('Search graph nodes') as HTMLInputElement).value).toBe('');
    expect((view.getByLabelText('Node Type') as HTMLSelectElement).value).toBe('all');
    expect((view.getByLabelText('Cluster') as HTMLSelectElement).value).toBe('all');
    expect((view.getByLabelText('Find a Cluster') as HTMLInputElement).value).toBe('');
    expect((view.getByLabelText('From') as HTMLInputElement).value).toBe('');
    expect(browseLabels().sort()).toEqual(modelVisibleLabels(index, {}).sort());
  });
});

// --- 3b. the chip row describes what is HIDDEN, and only ever widens --------

describe('graph chip row — the five-relation payload', () => {
  it('chips the HIDDEN types, never the kept ones, and the count always agrees', async () => {
    stubFetchRoutes(routes(fiveRelationGraph));
    const view = renderGraphTab(fiveRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);
    const index = modelIndex(fiveRelationGraph);
    // The real projection's exact vocabulary, in the index's own sorted order.
    expect(index.relationTypes).toEqual(FIVE_RAW);

    // Unticking ONE of five: exactly ONE chip, naming the type that is hidden.
    fireEvent.click(view.getByRole('checkbox', { name: 'Calls' }));
    expect(chipLabels()).toEqual(['Hiding: Calls']);
    expect(chipRemoveLabels()).toEqual(['Show Calls references again']);
    // …and NOT the four types still shown. This is the whole defect: iterating
    // `relationFilter` drew Imports / Imports From / References / Shares Data
    // With here, none of which was filtering anything.
    for (const kept of ['Imports', 'Imports From', 'References', 'Shares Data With']) {
      expect(chipLabels()).not.toContain(`Hiding: ${kept}`);
      expect(chipRemoveLabels()).not.toContain(`Show ${kept} references again`);
    }
    // The trigger and the row cannot contradict each other.
    expect(triggerCount(view)).toBe(1);
    expect(nonSearchChipCount()).toBe(1);
    expect(view.getByRole('button', { name: /Filters 1 active/ })).toBeInTheDocument();

    // Three of five hidden: three chips, counter three — no collapse into an
    // inverted single chip, and the two kept types are still unnamed.
    fireEvent.click(view.getByRole('checkbox', { name: 'Imports' }));
    fireEvent.click(view.getByRole('checkbox', { name: 'References' }));
    expect(chipLabels()).toEqual(['Hiding: Calls', 'Hiding: Imports', 'Hiding: References']);
    expect(triggerCount(view)).toBe(3);
    expect(nonSearchChipCount()).toBe(3);
    // Every chip's raw title is the backend's own value, never the label.
    expect([...document.querySelectorAll('.memory-graph-chip')].map((c) => c.getAttribute('title'))).toEqual(
      ['calls', 'imports', 'references'],
    );

    // The derivation itself, in one line: the chip row is the complement of the
    // ticked set, and the counter is its size.
    const state = { ...initialGraphViewState('explore'), relationFilter: ['imports_from', 'shares_data_with'] };
    expect(hiddenRelationTypes(state, index)).toEqual(['calls', 'imports', 'references']);
    expect(hiddenFilterCount(state, index)).toBe(3);
  });

  it('every X in the chip row WIDENS the view — never narrows it', async () => {
    stubFetchRoutes(routes(fiveRelationGraph));
    const view = renderGraphTab(fiveRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);

    // Everything on at once: search, node type, cluster, two hidden relations.
    fireEvent.change(view.getByLabelText('Search graph nodes'), { target: { value: 'mod' } });
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });
    fireEvent.change(view.getByLabelText('Cluster'), { target: { value: '131' } });
    fireEvent.click(view.getByRole('checkbox', { name: 'Calls' }));
    fireEvent.click(view.getByRole('checkbox', { name: 'References' }));

    expect(chipLabels()).toEqual([
      'Search: mod',
      'Files Only',
      'Cluster: Export Pipeline · 1 file',
      'Hiding: Calls',
      'Hiding: References',
    ]);
    expect(triggerCount(view)).toBe(4); // type + cluster + 2 relations; search is not counted
    expect(nonSearchChipCount()).toBe(4);

    // Remove them one at a time, in row order. The visible set may only GROW —
    // and the drawn edges may only be added to, never taken away. A row whose
    // X's narrow (the shipped behaviour for relations) fails on the first
    // relation chip.
    let nodes = shownNodeCount();
    let edges = drawnEdges();
    while (chipCount() > 0) {
      const labels = chipRemoveLabels();
      fireEvent.click(view.getByRole('button', { name: labels[0] }));
      const nextNodes = shownNodeCount();
      const nextEdges = drawnEdges();
      expect(nextNodes, `${labels[0]} narrowed the node set`).toBeGreaterThanOrEqual(nodes);
      for (const key of edges) {
        expect([...nextEdges], `${labels[0]} removed edge ${key}`).toContain(key);
      }
      // The counter tracks the row at every single step.
      expect(triggerCount(view)).toBe(nonSearchChipCount());
      nodes = nextNodes;
      edges = nextEdges;
    }

    // Removing every chip leaves the default, unfiltered view.
    const index = modelIndex(fiveRelationGraph);
    expect(triggerCount(view)).toBe(0);
    expect(shownNodeCount()).toBe(index.counts.total);
    expect(drawnEdges().size).toBe(fiveRelationGraph.edges.length);
  });

  it('re-ticking every type returns to the NO-filter state, not a full-set filter', async () => {
    stubFetchRoutes(routes(fiveRelationGraph));
    const view = renderGraphTab(fiveRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);
    const index = modelIndex(fiveRelationGraph);

    /*
     * `relationToggleAction` collapses a fully-re-ticked set back to `null`
     * ("no relationship filter") instead of a non-null array naming every type.
     * The two states draw the SAME nodes and edges, which is why nothing caught
     * the difference — but they are not the same claim: a non-null filter makes
     * GraphDetail tell the reader that a node's connections were restricted by
     * the relationship filter when nothing was, and it puts a redundant relation
     * parameter into every shared link.
     */
    for (const label of FIVE_LABELS) fireEvent.click(view.getByRole('checkbox', { name: label }));
    for (const label of FIVE_LABELS) fireEvent.click(view.getByRole('checkbox', { name: label }));

    expect(view.getByRole('button', { name: /^Filters/ }).textContent).toBe('Filters');
    expect(triggerCount(view)).toBe(0);
    expect(chipLabels()).toEqual([]);
    expect(drawnEdges().size).toBe(fiveRelationGraph.edges.length);

    // The user-visible difference between `null` and a full set: a concept node
    // carries no edges at all in this projection, and the reason given for that
    // must be "none recorded", not "none of the selected types".
    toBrowse(view);
    fireEvent.click(view.getByText('Provenance'));
    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    expect(detail.textContent).toContain('no recorded connections for this node in the rendered graph');
    expect(detail.textContent).not.toContain('no connections of the selected relationship types');

    // And the collapse itself, directly on the shared action builder.
    const oneLeft = {
      ...initialGraphViewState('explore'),
      relationFilter: FIVE_RAW.filter((r) => r !== 'calls'),
    };
    expect(relationToggleAction('calls', oneLeft, index)).toEqual({
      kind: 'filterRelation',
      relations: null,
    });
  });
});

// --- 3c. a control that removes itself must hand focus somewhere real -------

describe('graph chip row — focus is moved deliberately', () => {
  const filtersTrigger = (view: RenderResult) => view.getByRole('button', { name: /^Filters/ });

  it("Clear All Filters hands focus to the Filters trigger, not to <body>", async () => {
    stubFetchRoutes(routes(fiveRelationGraph));
    const view = renderGraphTab(fiveRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });

    const clear = view.getByRole('button', { name: 'Clear All Filters' });
    clear.focus();
    expect(document.activeElement).toBe(clear);
    fireEvent.click(clear);

    // The button unmounted itself with the row. Focus must not fall to <body>,
    // which drops a keyboard user at the top of the document.
    expect(document.querySelector('.memory-graph-chips')).toBeNull();
    expect(document.activeElement).toBe(filtersTrigger(view));
    expect(document.activeElement).not.toBe(document.body);
  });

  it("a chip's X hands focus to the next chip, and the last one to the Filters trigger", async () => {
    stubFetchRoutes(routes(fiveRelationGraph));
    const view = renderGraphTab(fiveRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });
    fireEvent.click(view.getByRole('checkbox', { name: 'Calls' }));

    // Two chips: "Files Only", then "Hiding: Calls".
    expect(chipLabels()).toEqual(['Files Only', 'Hiding: Calls']);
    const first = view.getByRole('button', { name: 'Clear the node type filter' });
    first.focus();
    fireEvent.click(first);
    // The X that was pressed is gone; focus is on the NEXT chip's X.
    expect(document.activeElement).toBe(
      view.getByRole('button', { name: 'Show Calls references again' }),
    );

    // The last remaining chip has no next chip, so focus goes to the trigger.
    fireEvent.click(document.activeElement as HTMLElement);
    expect(document.querySelector('.memory-graph-chips')).toBeNull();
    expect(document.activeElement).toBe(filtersTrigger(view));
  });

  it('gives both chip-row controls a 24×24 pressable area', async () => {
    // WCAG 2.2 2.5.8: the drawn X is 16×16 and Clear All Filters ~20px tall, so
    // each extends its hit area with a pseudo-element rather than growing.
    const css = Object.values(
      import.meta.glob('../screens/graph/graph.css', {
        query: '?raw',
        import: 'default',
        eager: true,
      }) as Record<string, string>,
    ).join('\n');
    const remove = /\.memory-graph-chip-remove::before \{([^}]*)\}/.exec(css)?.[1] ?? '';
    expect(remove).toMatch(/width:\s*24px/);
    expect(remove).toMatch(/height:\s*24px/);
    expect(remove).toMatch(/position:\s*absolute/);
    const clear = /\.memory-graph-chips-clear::before \{([^}]*)\}/.exec(css)?.[1] ?? '';
    expect(clear).toMatch(/height:\s*24px/);
    expect(clear).toMatch(/position:\s*absolute/);
    // A hit area only works from a positioned ancestor.
    for (const sel of ['.memory-graph-chip-remove', '.memory-graph-chips-clear']) {
      const block = new RegExp(`\\${sel} \\{([^}]*)\\}`).exec(css)?.[1] ?? '';
      expect(block, sel).toMatch(/position:\s*relative/);
    }
  });
});

// --- 4. Find a Path --------------------------------------------------------

describe('graph Find a Path tool', () => {
  it('no longer carries the stranded Clear filters button', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    openPath(view);
    const form = document.querySelector('.memory-graph-pathform') as HTMLElement;
    const names = [...form.querySelectorAll('button')].map((b) => b.textContent);
    expect(names).toEqual(['Find Path']);
    expect(view.queryByRole('button', { name: 'Clear filters' })).toBeNull();
  });

  it('charts a route, then clears its own fields and the result', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    openPath(view);

    fireEvent.change(view.getByLabelText('From'), { target: { value: 'src/fake_mod.py' } });
    fireEvent.change(view.getByLabelText('To'), { target: { value: 'src/other_mod.py' } });
    fireEvent.click(view.getByRole('button', { name: 'Find Path' }));
    expect(document.querySelectorAll('.memory-graph-path-list li').length).toBe(2);

    fireEvent.click(view.getByRole('button', { name: 'Clear Path' }));
    expect(document.querySelector('.memory-graph-path-list')).toBeNull();
    expect((view.getByLabelText('From') as HTMLInputElement).value).toBe('');
    expect((view.getByLabelText('To') as HTMLInputElement).value).toBe('');
  });

  it('refuses an unknown name and an ambiguous one, and guesses at neither', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    openPath(view);

    fireEvent.change(view.getByLabelText('From'), { target: { value: 'nope/missing.py' } });
    fireEvent.change(view.getByLabelText('To'), { target: { value: 'src/fake_mod.py' } });
    fireEvent.click(view.getByRole('button', { name: 'Find Path' }));
    expect(view.container.textContent).toMatch(/No node in this projection matches/);
    expect(document.querySelector('.memory-graph-path-list')).toBeNull();
    expect(document.querySelector('.memory-graph-detail')).toBeNull(); // nothing selected

    fireEvent.change(view.getByLabelText('From'), { target: { value: 'mod' } });
    fireEvent.click(view.getByRole('button', { name: 'Find Path' }));
    expect(view.container.textContent).toMatch(/matches 2 nodes, so no\s+identity was assumed/);
    expect(document.querySelector('.memory-graph-path-list')).toBeNull();

    // The tool states the contract where the user is typing, not only in help.
    expect(document.querySelector('.memory-graph-pathnote')?.textContent).toMatch(
      /never guessed at/,
    );
  });

  it('"Use as path start" opens the tool it fills in', async () => {
    stubFetchRoutes(routes());
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    toBrowse(view);
    fireEvent.click(view.getByText('src/fake_mod.py'));

    expect(view.queryByLabelText('From')).toBeNull(); // the tool is shut
    const detail = document.querySelector('.memory-graph-detail') as HTMLElement;
    fireEvent.click(within(detail).getByRole('button', { name: 'Use as path start' }));

    // Otherwise the click writes into a collapsed field and looks like a no-op.
    expect((view.getByLabelText('From') as HTMLInputElement).value).toBe('src/fake_mod.py');
    expect(view.getByRole('button', { name: 'Find a Path' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });
});

// --- 5. the humanisation boundary, on the surface --------------------------

describe('graph humanisation boundary', () => {
  it('relabels the closed relation vocabulary and renames NO cluster name', async () => {
    // The longest real cluster name in the committed snapshot, plus the two
    // shapes a mechanical snake_case → Title Case rule would destroy.
    const longest = 'ISAAC Metadata Assistant — Extraction Design (XANES / characterization path)';
    const payload: ApiMemoryGraphResponse = {
      ...(memoryGraphAvailable as unknown as ApiMemoryGraphResponse),
      nodes: (memoryGraphAvailable.nodes as ApiMemoryGraphResponse['nodes']).map((n, i) =>
        i === 0
          ? { ...n, community_id: '9001', community_name: longest }
          : i === 1
            ? { ...n, community_id: '9002', community_name: 'SHE_work_function_eV' }
            : n,
      ),
      communities: [
        { id: '9001', name: longest, file_count: 1 },
        { id: '9002', name: 'SHE_work_function_eV', file_count: 1 },
      ],
    };
    stubFetchRoutes(routes(payload));
    const view = renderGraphTab(payload);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);

    // The legend renders both names EXACTLY as the upstream builder wrote them.
    const legendNames = [...document.querySelectorAll('.graph-legend-name')].map(
      (n) => n.textContent,
    );
    expect(legendNames).toContain(longest);
    expect(legendNames).toContain('SHE_work_function_eV');
    // The readings a mechanical rule would have fabricated.
    const surface = view.container.textContent ?? '';
    expect(surface).not.toContain('She Work Function Ev');
    expect(surface).not.toContain('Extraction design');

    // The relation vocabulary IS relabelled — the closed, measured five.
    expect(view.getByRole('checkbox', { name: 'Imports' })).toBeInTheDocument();
    expect(view.queryByRole('checkbox', { name: 'imports' })).toBeNull();
  });

  it('a cluster chip carries the long name verbatim, in a wrapping container', async () => {
    const longest = 'ISAAC Metadata Assistant — Extraction Design (XANES / characterization path)';
    const payload: ApiMemoryGraphResponse = {
      ...(memoryGraphAvailable as unknown as ApiMemoryGraphResponse),
      communities: [{ id: '131', name: longest, file_count: 1 }],
    };
    stubFetchRoutes(routes(payload));
    const view = renderGraphTab(payload);
    await view.findByText('Graph', { selector: 'h2' });
    openFilters(view);
    fireEvent.change(view.getByLabelText('Cluster'), { target: { value: '131' } });

    expect(chipLabels()).toEqual([`Cluster: ${longest} · 1 file`]);
    // jsdom applies no layout, so overflow is pinned STRUCTURALLY: the long
    // strings live in containers the stylesheet lets break, and the chip row
    // itself wraps. A rule change that makes them nowrap fails here.
    const css = Object.values(
      import.meta.glob('../screens/graph/graph.css', {
        query: '?raw',
        import: 'default',
        eager: true,
      }) as Record<string, string>,
    ).join('\n');
    for (const selector of ['.memory-graph-chip-label', '.graph-legend-name']) {
      const block = new RegExp(`\\${selector} \\{([^}]*)\\}`).exec(css)?.[1] ?? '';
      expect(block, selector).toMatch(/overflow-wrap:\s*anywhere/);
      expect(block, selector).toMatch(/min-width:\s*0/);
    }
    expect(/\.memory-graph-chips \{([^}]*)\}/.exec(css)?.[1] ?? '').toMatch(/flex-wrap:\s*wrap/);
    // The ONLY `nowrap` in this stylesheet belongs to the visually-hidden
    // utility (a screen-reader clip, not a layout choice). Anything else would
    // be a rule that can push a 76-character cluster name off screen.
    const nowrapOwners = [...css.matchAll(/([.#][\w-]+)[^{}]*\{[^}]*white-space:\s*nowrap[^}]*\}/g)]
      .map((m) => m[1]);
    expect(nowrapOwners).toEqual(['.memory-graph-visually-hidden']);
  });

  it('pairs every legend relation with the backend value it stands for', async () => {
    stubFetchRoutes(routes(fiveRelationGraph));
    const view = renderGraphTab(fiveRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });

    // Explore's legend: one entry per relation, the readable label visible and
    // the backend's exact value on `title` — the same pairing a cluster entry
    // makes with `cluster <id>`. The removed `.graph-legend-raw` line printed all
    // five values again as one unlabelled mono string, attached to nothing.
    const entries = [...document.querySelectorAll('.graph-legend-relation')];
    expect(entries.map((e) => e.textContent)).toEqual(FIVE_LABELS);
    expect(entries.map((e) => e.getAttribute('title'))).toEqual(FIVE_RAW);
    expect(document.querySelector('.graph-legend-raw')).toBeNull();
  });

  it('exposes exactly the five measured relation labels and nothing invented', () => {
    expect(Object.keys(RELATION_DISPLAY_LABELS).sort()).toEqual([
      'calls',
      'imports',
      'imports_from',
      'references',
      'shares_data_with',
    ]);
  });
});

// --- 6. the graph data itself is untouched ---------------------------------

describe('graph data is never mutated by the redesign', () => {
  it('the fetched payload is byte-identical after mounting, filtering and pathing', async () => {
    const payload = JSON.parse(JSON.stringify(memoryGraphAvailable)) as ApiMemoryGraphResponse;
    const before = JSON.stringify(payload);
    stubFetchRoutes(routes(payload));
    const view = renderGraphTab(payload);
    await view.findByText('Graph', { selector: 'h2' });

    openFilters(view);
    fireEvent.change(view.getByLabelText('Node Type'), { target: { value: 'file' } });
    fireEvent.change(view.getByLabelText('Cluster'), { target: { value: '131' } });
    fireEvent.click(view.getByRole('checkbox', { name: 'Imports' }));
    fireEvent.click(view.getByRole('checkbox', { name: 'Imports' }));
    openPath(view);
    fireEvent.change(view.getByLabelText('From'), { target: { value: 'src/fake_mod.py' } });
    fireEvent.change(view.getByLabelText('To'), { target: { value: 'src/other_mod.py' } });
    fireEvent.click(view.getByRole('button', { name: 'Find Path' }));
    fireEvent.click(view.getByRole('button', { name: 'Clear All Filters' }));

    // P36V.1 Unit F — Find Path fits the route, which lands past the first
    // level-of-detail threshold, and clearing the focus then lets the canvas ask
    // for the lazily fetched symbol layer. This scenario deliberately does not
    // stub that route (it is about payload immutability), so the surface must
    // degrade honestly instead of drawing anything in its place. Awaited so the
    // resulting state update is observed rather than left dangling.
    expect(
      await view.findByText(/Symbol-level detail is unavailable in this deployment/),
    ).toBeInTheDocument();

    // No relabelling, no chip, no legend row wrote back into the payload.
    expect(JSON.stringify(payload)).toBe(before);
  });

  it('every drawn edge still comes from the payload, and only from there', async () => {
    stubFetchRoutes(routes(twoRelationGraph));
    const view = renderGraphTab(twoRelationGraph);
    await view.findByText('Graph', { selector: 'h2' });

    const index = modelIndex(twoRelationGraph);
    const drawn = [...document.querySelectorAll('.memory-graph-edge')].map((l) =>
      l.getAttribute('data-edge'),
    );
    expect(drawn.length).toBe(twoRelationGraph.edges.length);
    for (const key of drawn) expect(index.edgeKeys.has(key ?? '')).toBe(true);
  });
});

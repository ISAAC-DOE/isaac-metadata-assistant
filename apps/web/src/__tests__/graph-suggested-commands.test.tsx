import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, render, fireEvent, waitFor, within, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  DIRECTLY_RUNNABLE_SUGGESTIONS,
  MAX_SUGGESTED_COMMANDS,
  SUGGESTED_FIND_TOPICS,
  parseGraphCommand,
  suggestedGraphCommands,
  type GraphSuggestedCommand,
} from '../lib/graphCommands';
import {
  applyGraphAction,
  buildGraphIndex,
  filteredNodeIds,
  initialGraphViewState,
  type GraphIndex,
  type GraphViewState,
} from '../lib/graphModel';
import { decodeDeepGraph } from '../lib/graphDeep';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryGraphAvailable,
} from '../test/apiFixtures';
import { memoryGraphDetailAvailable } from '../test/graphDeepFixture';

/*
 * P36V.1 Unit G Slice 9 — Suggested Commands beside the graph command bar.
 *
 * The contract under test:
 *   · every suggestion is a line of the ONE existing grammar, and every one of
 *     them actually parses AND resolves on the live state (§5);
 *   · a click INSERTS the exact canonical command and waits for Run — it never
 *     applies a filter, focus, path or selection by itself (§3);
 *   · direct execution is reachable only for the viewport-only allowlist (§4);
 *   · the set is context-aware — it follows the base selection, follows Unit F's
 *     pinned DEEP mark instead when there is one, and returns to the general set
 *     the moment the selection clears (§2, §6);
 *   · it is keyboard-operable and its accessible names carry the
 *     insert-vs-run distinction, not just a visual tag (§7).
 */

// --- fixtures ----------------------------------------------------------------

const file = (id: string, community: string | null, name: string | null) => ({
  id,
  kind: 'file' as const,
  label: id,
  file_type: 'code',
  community_id: community,
  community_name: name,
  node_count: 4,
  on_disk: true,
});

/**
 * The base fixture plus three files whose PATHS carry two of the real topic
 * words, and a two-edge chain — so the `find` suggestions and the depth-2
 * suggestion have something real to resolve against. Nothing here is a special
 * case in the code: the suggestions are derived from whatever the payload holds.
 */
const richGraph = {
  ...memoryGraphAvailable,
  nodes: [
    ...memoryGraphAvailable.nodes,
    file('src/isaac_records/export.py', '131', 'Export Pipeline'),
    file('src/isaac_records/validation_stack.py', '131', 'Export Pipeline'),
    file('src/isaac_records/audit.py', '131', 'Export Pipeline'),
  ],
  edges: [
    ...memoryGraphAvailable.edges,
    {
      source: 'src/isaac_records/export.py',
      target: 'src/isaac_records/validation_stack.py',
      relations: ['imports'],
    },
    {
      source: 'src/isaac_records/validation_stack.py',
      target: 'src/isaac_records/audit.py',
      relations: ['calls'],
    },
  ],
  communities: [
    { id: '131', name: 'Export Pipeline', file_count: 4 },
    { id: '55', name: null, file_count: 1 },
  ],
};

const routes = {
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/graph': { body: richGraph },
};
const deepRoute = 'GET /api/memory/graph/detail';

function renderGraph(entry = '/memory?tab=graph', extra: Record<string, { body: unknown }> = {}) {
  const calls = stubFetchRoutes({ ...routes, ...extra });
  const view = render(
    <MemoryRouter
      initialEntries={[entry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
    </MemoryRouter>,
  );
  return { view, calls };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- DOM helpers -------------------------------------------------------------

const area = () => document.querySelector('.graph-cmd-suggest') as HTMLElement | null;
const chips = () => [...document.querySelectorAll('.graph-cmd-suggest-btn')] as HTMLButtonElement[];
const labels = () =>
  chips().map((b) => (b.querySelector('.graph-cmd-suggest-label')?.textContent ?? '').trim());
const commands = () =>
  chips().map((b) => (b.querySelector('.graph-cmd-suggest-cmd')?.textContent ?? '').trim());
const bar = (view: RenderResult) =>
  view.getByRole('combobox', { name: 'Graph command' }) as HTMLInputElement;
const nodeCount = () => document.querySelectorAll('.memory-graph-node').length;
const selected = () => document.querySelector('.memory-graph-node.selected');
const live = () =>
  (document.querySelector('.memory-graph-live') as HTMLElement | null)?.textContent ?? '';

const chipNamed = (label: string): HTMLButtonElement => {
  const found = chips().find(
    (b) => (b.querySelector('.graph-cmd-suggest-label')?.textContent ?? '').trim() === label,
  );
  if (!found) throw new Error(`no suggestion labelled "${label}" — have: ${labels().join(' | ')}`);
  return found;
};

// --- 1. the initial (nothing selected) set ----------------------------------

describe('graph suggested commands — the initial set', () => {
  it('offers real search topics, a real cluster, a real reference type and Fit to View', async () => {
    const { view } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });

    expect(area()).not.toBeNull();
    expect(area()!.textContent).toContain('Suggested Commands');
    // Human-readable, Title Case labels — never a raw command as the label.
    expect(labels()).toEqual([
      'Find Validation',
      'Find Export',
      'Show the Export Pipeline Cluster',
      'Show Only Imports References',
      'Fit to View',
    ]);
    // …with the exact command visible as the secondary line.
    expect(commands()).toEqual([
      'find validation',
      'find export',
      'community Export Pipeline',
      'relation imports',
      'fit',
    ]);
    expect(chips().length).toBeLessThanOrEqual(MAX_SUGGESTED_COMMANDS);
  });

  it('never offers a topic the projection has no match for', async () => {
    // The plain fixture's paths contain NONE of the topic words. The row is
    // therefore shorter — a suggestion that filters to nothing is not offered.
    const { view } = renderGraph('/memory?tab=graph', {
      'GET /api/memory/graph': { body: memoryGraphAvailable },
    });
    await view.findByText('Graph', { selector: 'h2' });
    for (const topic of SUGGESTED_FIND_TOPICS) {
      expect(commands()).not.toContain(`find ${topic}`);
    }
    expect(labels()).toEqual([
      'Show the Export Pipeline Cluster',
      'Show Only Imports References',
      'Fit to View',
    ]);
  });

  it('offers Clear Filters only once something is actually filtering', async () => {
    const { view } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    expect(labels()).not.toContain('Clear Filters');

    fireEvent.change(view.getByLabelText('Search graph nodes'), { target: { value: 'export' } });
    await waitFor(() => expect(labels()).toContain('Clear Filters'));
    expect(commands()).toContain('clear filters');
    // …and the topic it now duplicates is dropped, not offered twice.
    expect(commands()).not.toContain('find export');
  });
});

// --- 2. the context-aware (node selected) set -------------------------------

describe('graph suggested commands — a selected node changes the set', () => {
  const withSelection = () =>
    renderGraph('/memory?tab=graph&gnode=src%2Fisaac_records%2Fexport.py');

  it('offers the node-scoped commands, each naming the selected node', async () => {
    const { view } = withSelection();
    await view.findByText('Graph', { selector: 'h2' });
    await waitFor(() => expect(selected()).not.toBeNull());

    expect(labels()).toEqual([
      'Show 1-Hop Neighbors',
      'Show 2-Hop Neighbors',
      'Show This Cluster',
      'Start a Path From Here',
      'Clear the Selection',
      'View Technical Details',
    ]);
    expect(commands()).toEqual([
      'neighbors src/isaac_records/export.py',
      'neighbors src/isaac_records/export.py depth 2',
      'community 131',
      'path src/isaac_records/export.py -> …',
      'select none',
      'about this graph',
    ]);
    // None of the general suggestions is still on screen.
    expect(labels()).not.toContain('Fit to View');
  });

  it('omits a 2-hop suggestion that would draw exactly the 1-hop set', async () => {
    // `src/fake_mod.py` ↔ `src/other_mod.py` is a closed pair, so depth 2 adds
    // nothing. A suggestion whose result is identical to its neighbour's is not
    // offered at all.
    const { view } = renderGraph('/memory?tab=graph&gnode=src%2Ffake_mod.py');
    await view.findByText('Graph', { selector: 'h2' });
    await waitFor(() => expect(selected()).not.toBeNull());
    expect(labels()).toContain('Show 1-Hop Neighbors');
    expect(labels()).not.toContain('Show 2-Hop Neighbors');
  });

  it('omits the neighbourhood suggestions entirely for a node with no references', async () => {
    const { view } = renderGraph('/memory?tab=graph&gnode=docs%2Ffake-note.md');
    await view.findByText('Graph', { selector: 'h2' });
    await waitFor(() => expect(selected()).not.toBeNull());
    expect(labels()).not.toContain('Show 1-Hop Neighbors');
    expect(labels()).not.toContain('Show 2-Hop Neighbors');
    // …and a node in no cluster is not offered a cluster filter.
    expect(labels()).not.toContain('Show This Cluster');
    expect(labels()).toEqual([
      'Start a Path From Here',
      'Clear the Selection',
      'View Technical Details',
    ]);
  });

  it('RESETS to the general set as soon as the selection clears', async () => {
    const { view } = withSelection();
    await view.findByText('Graph', { selector: 'h2' });
    await waitFor(() => expect(labels()).toContain('Show 1-Hop Neighbors'));

    // Through the suggestion itself: insert `select none`, then Run.
    fireEvent.click(chipNamed('Clear the Selection'));
    expect(bar(view).value).toBe('select none');
    fireEvent.click(view.getByRole('button', { name: 'Run' }));

    await waitFor(() => expect(selected()).toBeNull());
    expect(labels()).toEqual([
      'Find Validation',
      'Find Export',
      'Show the Export Pipeline Cluster',
      'Show Only Imports References',
      'Fit to View',
    ]);
    expect(labels()).not.toContain('Show 1-Hop Neighbors');
  });
});

// --- 3. interaction model: insert, never silent execution -------------------

describe('graph suggested commands — a click inserts, it does not apply', () => {
  it('puts the EXACT canonical command in the bar and changes nothing until Run', async () => {
    const { view } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    const before = nodeCount();

    fireEvent.click(chipNamed('Find Validation'));
    // Exact, character for character — the same line a user could type.
    expect(bar(view).value).toBe('find validation');
    // NOTHING was applied: no filter, no announcement, no history entry.
    expect(nodeCount()).toBe(before);
    expect(live()).toBe('');
    expect(document.querySelector('.graph-cmd-history')).toBeNull();
    expect(new URLSearchParams(window.location.search).get('gq')).toBeNull();

    // The user's explicit Run is what applies it.
    fireEvent.click(view.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(nodeCount()).toBe(1));
    expect(view.container.querySelector('.graph-cmd-history')?.textContent).toContain(
      'find validation',
    );
  });

  it('a complex filter, focus or path suggestion is NEVER run by the click', async () => {
    const { view } = renderGraph('/memory?tab=graph&gnode=src%2Fisaac_records%2Fexport.py');
    await view.findByText('Graph', { selector: 'h2' });
    await waitFor(() => expect(selected()).not.toBeNull());
    const before = nodeCount();

    for (const label of [
      'Show 1-Hop Neighbors',
      'Show 2-Hop Neighbors',
      'Show This Cluster',
      'Start a Path From Here',
    ]) {
      const chip = chipNamed(label);
      fireEvent.click(chip);
      // The command landed in the bar…
      expect(bar(view).value.length).toBeGreaterThan(0);
      // …and the graph is untouched: same node count, no focus chip, no notice.
      expect(nodeCount()).toBe(before);
      expect(document.querySelector('.memory-graph-focuschip')).toBeNull();
      expect(live()).toBe('');
    }
  });

  it('hovering a suggestion runs nothing at all', async () => {
    const { view } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    const before = nodeCount();
    for (const chip of chips()) {
      fireEvent.pointerEnter(chip);
      fireEvent.mouseOver(chip);
      fireEvent.focus(chip);
    }
    expect(bar(view).value).toBe('');
    expect(nodeCount()).toBe(before);
    expect(live()).toBe('');
  });

  it('an unfinished path suggestion opens real completions for the missing token', async () => {
    const { view } = renderGraph('/memory?tab=graph&gnode=src%2Fisaac_records%2Fexport.py');
    await view.findByText('Graph', { selector: 'h2' });
    await waitFor(() => expect(selected()).not.toBeNull());

    fireEvent.click(chipNamed('Start a Path From Here'));
    // The trailing space is part of the canonical prefix — the destination token
    // comes from the index, never from this row guessing one.
    expect(bar(view).value).toBe('path src/isaac_records/export.py -> ');
    const list = await view.findByRole('listbox', { name: 'Command completions' });
    const options = [...list.querySelectorAll('[role="option"]')].map((o) => o.textContent ?? '');
    expect(options.length).toBeGreaterThan(0);
    for (const option of options) {
      expect(option).toContain('path src/isaac_records/export.py -> ');
    }
    // Completing it from the list and pressing Run produces a real route.
    fireEvent.keyDown(bar(view), { key: 'ArrowDown' });
    fireEvent.keyDown(bar(view), { key: 'Enter' });
    fireEvent.keyDown(bar(view), { key: 'Enter' });
    await waitFor(() => expect(live()).not.toBe(''));
    expect(live()).toMatch(/route|No path connects/);
  });
});

// --- 4. direct execution is allowlisted, and labelled --------------------------

describe('graph suggested commands — direct execution is a narrow, labelled exception', () => {
  it('Fit to View runs on the click, and says so in its name and on its face', async () => {
    const { view } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    const chip = chipNamed('Fit to View');
    expect(chip.getAttribute('aria-label')).toBe(
      'Fit to View — runs the view command "fit" straight away — it only reframes the viewport',
    );
    expect(chip.textContent).toContain('runs now');
    expect(chip).toHaveClass('is-view');

    fireEvent.click(chip);
    // It went through the SAME parser and reducer a typed `fit` goes through:
    // the outcome is announced and recorded exactly like a typed command.
    await waitFor(() => expect(live()).toMatch(/Framed the visible nodes/));
    expect(view.container.querySelector('.graph-cmd-history')?.textContent).toContain('fit');
    // A view action only: no filter, no selection, no focus.
    expect(selected()).toBeNull();
    expect(document.querySelector('.memory-graph-focuschip')).toBeNull();
    expect(bar(view).value).toBe('');
  });

  it('the allowlist is exactly the viewport-only verb, and every other chip inserts', async () => {
    expect([...DIRECTLY_RUNNABLE_SUGGESTIONS]).toEqual(['fit']);
    const { view } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    for (const chip of chips()) {
      const isView = chip.classList.contains('is-view');
      const label = chip.getAttribute('aria-label') ?? '';
      if (isView) expect(label).toMatch(/runs the view command "fit"/);
      else expect(label).toMatch(/puts the (unfinished )?command ".+" in the command bar/);
      expect(chip.textContent).toMatch(isView ? /runs now/ : /fills the bar|opens help/);
    }
  });

  it('View Technical Details only opens the dialog — no command, no graph change', async () => {
    const { view } = renderGraph('/memory?tab=graph&gnode=src%2Fisaac_records%2Fexport.py');
    await view.findByText('Graph', { selector: 'h2' });
    await waitFor(() => expect(selected()).not.toBeNull());
    const before = nodeCount();
    const chip = chipNamed('View Technical Details');
    expect(chip.getAttribute('aria-label')).toBe(
      'View Technical Details — opens About This Graph at Technical Details',
    );

    // Focused first: a real pointer press focuses the button, and jsdom's
    // synthetic click does not — the focus-restoration contract is about which
    // control the user was actually on.
    act(() => chip.focus());
    fireEvent.click(chip);
    const dialog = await view.findByRole('dialog', { name: 'About This Graph' });
    // Opened AT Technical Details — expanded, not merely present.
    expect((dialog.querySelector('.graph-help-technical') as HTMLDetailsElement).open).toBe(true);
    expect(nodeCount()).toBe(before);
    expect(bar(view).value).toBe('');
    expect(document.querySelector('.graph-cmd-history')).toBeNull();

    // Focus returns to the chip that opened it.
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(view.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(chip);
  });
});

// --- 5. every suggestion parses AND resolves ---------------------------------

describe('graph suggested commands — nothing is offered that cannot resolve', () => {
  /** Fold a command through the real parser and the real reducer. */
  function runOnState(
    command: string,
    index: GraphIndex,
    state: GraphViewState = initialGraphViewState(),
  ): GraphViewState {
    const parsed = parseGraphCommand(command);
    expect(parsed.status, `\`${command}\` did not parse`).toBe('actions');
    if (parsed.status !== 'actions') throw new Error('unreachable');
    let next = state;
    for (const action of parsed.actions) next = applyGraphAction(next, action, index);
    return next;
  }

  const check = (
    suggestions: GraphSuggestedCommand[],
    index: GraphIndex,
    state: GraphViewState = initialGraphViewState(),
  ) => {
    expect(suggestions.length).toBeGreaterThan(0);
    for (const s of suggestions) {
      if (s.effect === 'help') {
        expect(s.command).toBeNull();
        continue;
      }
      expect(s.command, `${s.label} has no command`).toBeTruthy();
      if (s.partial) {
        // An unfinished line is EXPECTED to be a syntax error on its own; the
        // completed form is what has to resolve.
        expect(parseGraphCommand(s.command!).status).toBe('error');
        const completed = `${s.command}${index.nodes[index.nodes.length - 1].id}`;
        const next = runOnState(completed, index, state);
        expect(next.notice?.kind, `${s.label} could not resolve its own start node`).not.toBe(
          'not_found',
        );
        continue;
      }
      const next = runOnState(s.command!, index, state);
      // No refusal notice, and something is left on screen.
      for (const refusal of [
        'not_found',
        'ambiguous',
        'community_not_found',
        'community_ambiguous',
        'relation_unknown',
        'no_path',
      ]) {
        expect(next.notice?.kind, `\`${s.command}\` was refused as ${refusal}`).not.toBe(refusal);
      }
      expect(filteredNodeIds(next, index).length, `\`${s.command}\` shows nothing`).toBeGreaterThan(
        0,
      );
    }
  };

  it('holds for the general set, for every node, and for every cluster filter', () => {
    const index = buildGraphIndex(richGraph as never);
    check(suggestedGraphCommands(index, { state: initialGraphViewState() }), index);

    for (const node of index.nodes) {
      const state = { ...initialGraphViewState(), selectedId: node.id };
      check(suggestedGraphCommands(index, { state }), index, state);
    }
    for (const entry of index.communitiesBySize) {
      const state = { ...initialGraphViewState(), communityFilter: entry.id };
      check(suggestedGraphCommands(index, { state }), index, state);
    }
    for (const search of ['export', 'validation', 'zzz-no-match']) {
      const state = { ...initialGraphViewState(), search };
      check(suggestedGraphCommands(index, { state }), index, state);
    }
  });

  it('holds for the plain fixture, whose vocabulary matches no topic at all', () => {
    const index = buildGraphIndex(memoryGraphAvailable as never);
    check(suggestedGraphCommands(index, { state: initialGraphViewState() }), index);
  });

  it('holds for every pinned DEEP mark, and never names a symbol the grammar cannot resolve', () => {
    const index = buildGraphIndex(richGraph as never);
    const deep = decodeDeepGraph(memoryGraphDetailAvailable)!;
    expect(deep).not.toBeNull();
    const state = initialGraphViewState();
    const symbolIds = deep.nodes.map((n) => n.id);
    for (const deepSelectedId of [...symbolIds, ...deep.clusterByKey.keys()]) {
      const suggestions = suggestedGraphCommands(index, { state, deep, deepSelectedId });
      check(suggestions, index, state);
      for (const s of suggestions) {
        // A deep suggestion may only ever name the mark's FILE (or its cluster
        // id) — never the symbol id or label, which `resolveNode` cannot resolve.
        if (!s.command) continue;
        expect(symbolIds.some((id) => s.command!.includes(id))).toBe(false);
      }
    }
  });

  it('offers at most the bound, with no duplicate command, in every state above', () => {
    const index = buildGraphIndex(richGraph as never);
    const states = [
      initialGraphViewState(),
      { ...initialGraphViewState(), selectedId: 'src/isaac_records/export.py' },
      { ...initialGraphViewState(), search: 'export', typeFilter: 'file' as const },
    ];
    for (const state of states) {
      const suggestions = suggestedGraphCommands(index, { state });
      expect(suggestions.length).toBeLessThanOrEqual(MAX_SUGGESTED_COMMANDS);
      const seen = suggestions.filter((s) => s.command).map((s) => s.command);
      expect(new Set(seen).size).toBe(seen.length);
      // Labels are readable prose, never the raw command line.
      for (const s of suggestions) {
        expect(s.label).toMatch(/^[A-Z]/);
        expect(s.label).not.toBe(s.command);
        expect(s.detail.length).toBeGreaterThan(10);
      }
    }
  });
});

// --- 6. the deep (symbol-level) context -------------------------------------

describe('graph suggested commands — a pinned symbol is a different kind of thing', () => {
  const withDeep = { [deepRoute]: { body: memoryGraphDetailAvailable } };
  const deepMarks = () => [...document.querySelectorAll('.memory-graph-deep-node')];

  async function pinASymbol(view: RenderResult) {
    await view.findByText('Graph', { selector: 'h2' });
    const svg = document.querySelector('.memory-graph-svg') as unknown as HTMLElement;
    fireEvent.keyDown(within(svg).getByRole('button', { name: /^src\/fake_mod\.py, file/ }), {
      key: 'Enter',
    });
    fireEvent.click(view.getByRole('button', { name: 'Reveal Detail' }));
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    fireEvent.click(view.getByRole('button', { name: 'Reveal Detail' }));
    await waitFor(() =>
      expect(deepMarks().every((m) => m.getAttribute('data-deep-kind') === 'symbol')).toBe(true),
    );
    const mark = deepMarks().find((m) =>
      (m.getAttribute('aria-label') ?? '').startsWith('export_record'),
    ) as SVGGElement;
    act(() => fireEvent.keyDown(mark, { key: 'Enter' }));
    await waitFor(() =>
      expect(document.querySelector('.memory-graph-deep-detail')).not.toBeNull(),
    );
  }

  it('re-expresses the suggestions in terms of the symbol’s FILE and cluster', async () => {
    const { view } = renderGraph('/memory?tab=graph', withDeep);
    await pinASymbol(view);

    expect(labels()).toEqual([
      'Select the File It Is In',
      "Show Its File's Neighbors",
      'Show This Cluster',
      'Start a Path From Its File',
      'View Technical Details',
    ]);
    expect(commands()).toEqual([
      'select src/fake_mod.py',
      'neighbors src/fake_mod.py',
      'community 131',
      'path src/fake_mod.py -> …',
      'about this graph',
    ]);
    // NOT the symbol's own name: `resolveNode` addresses files and concepts, so
    // `select export_record` would honestly answer "no node matches".
    for (const command of commands()) {
      expect(command).not.toContain('export_record');
      expect(command).not.toContain('fake/export_fn');
    }
    // And the label says which, rather than leaving the reader to discover it.
    expect(chipNamed('Select the File It Is In').getAttribute('title')).toMatch(
      /Commands address files and concepts, not symbol names/,
    );
  });

  it('drops a cluster the file projection does not carry', async () => {
    const { view } = renderGraph('/memory?tab=graph', withDeep);
    await pinASymbol(view);
    // Pin `validate_draft`, whose community (77, "Draft Validator") exists only
    // in the deep payload. A `community 77` suggestion would resolve to nothing.
    const other = deepMarks().find((m) =>
      (m.getAttribute('aria-label') ?? '').startsWith('validate_draft'),
    ) as SVGGElement;
    act(() => fireEvent.keyDown(other, { key: 'Enter' }));
    await waitFor(() => expect(commands()).not.toContain('community 131'));
    expect(commands()).not.toContain('community 77');
    expect(labels()).not.toContain('Show This Cluster');
  });

  it('states that a focus will drop the canvas back to the file projection', async () => {
    const { view } = renderGraph('/memory?tab=graph', withDeep);
    await pinASymbol(view);
    expect(chipNamed("Show Its File's Neighbors").getAttribute('title')).toMatch(
      /returns the canvas to the file projection/,
    );
  });
});

// --- 7. keyboard + screen reader ---------------------------------------------

describe('graph suggested commands — keyboard-operable and honestly named', () => {
  it('is a labelled list of real buttons, reachable and operable from the keyboard', async () => {
    const { view } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });

    const list = view.getByRole('list', { name: 'Suggested Commands' });
    expect(list.querySelectorAll(':scope > li').length).toBe(chips().length);
    for (const chip of chips()) {
      expect(chip.tagName).toBe('BUTTON');
      expect(chip.getAttribute('type')).toBe('button');
      // Natively focusable, in document order — no roving tabindex to get wrong.
      expect(chip.hasAttribute('tabindex')).toBe(false);
      expect((chip.getAttribute('aria-label') ?? '').length).toBeGreaterThan(10);
    }

    // Focus + Enter is the whole interaction; it inserts, exactly like a click.
    const chip = chipNamed('Find Export');
    act(() => chip.focus());
    expect(document.activeElement).toBe(chip);
    fireEvent.click(chip); // Enter on a <button> dispatches click
    expect(bar(view).value).toBe('find export');
    // Focus moved into the input the command is now sitting in.
    expect(document.activeElement).toBe(bar(view));
  });

  it('explains the insert-vs-run distinction in words, next to the row', async () => {
    const { view } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    const note = document.querySelector('.graph-cmd-suggest-note') as HTMLElement;
    expect(note.textContent).toMatch(/puts its exact command in the bar above; you press Run/);
    expect(note.textContent).toMatch(/Only runs now acts on the click/);
  });

  it('adds no second live region, and writes nothing to storage', async () => {
    const { view } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    fireEvent.click(chipNamed('Find Validation'));
    fireEvent.click(view.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(nodeCount()).toBe(1));

    const card = view.container.querySelector('.memory-graph-card') as HTMLElement;
    expect(card.querySelectorAll('[aria-live]').length).toBe(1);
    expect(area()!.querySelector('[aria-live]')).toBeNull();
    expect(JSON.stringify({ ...window.localStorage })).not.toContain('find validation');
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain('find validation');
  });

  it('makes no extra network request of its own', async () => {
    const { view, calls } = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    fireEvent.click(chipNamed('Show the Export Pipeline Cluster'));
    fireEvent.click(view.getByRole('button', { name: 'Run' }));
    // Cluster 131 holds the four `Export Pipeline` files plus one concept.
    await waitFor(() => expect(nodeCount()).toBe(5));
    expect(calls.filter((c) => c.includes('/api/memory/graph')).length).toBe(1);
    expect(calls.some((c) => c.includes('assistant'))).toBe(false);
  });
});

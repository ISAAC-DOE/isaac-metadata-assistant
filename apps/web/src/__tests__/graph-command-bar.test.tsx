import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor, type RenderResult } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryGraphAvailable,
} from '../test/apiFixtures';

/*
 * P36R Slice 4 — the graph command bar, mounted through the real screen.
 *
 * The grammar itself is unit-tested in graph-commands.test.ts. What is guarded
 * HERE is the wiring: a typed command drives the SAME canonical state the
 * filters and clicks drive, a syntax error changes nothing and is announced in
 * the SAME single live region, the history is ephemeral, and the URL is a
 * bounded, shareable, back/forward-correct encoding of the view.
 */

const routes = {
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/graph': { body: memoryGraphAvailable },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * A probe inside the router: it exposes the live location and the real
 * `navigate` so a test can read the encoded link and press the browser's back
 * and forward buttons (`navigate(-1)` / `navigate(1)`) exactly as a user would.
 * A data router (`createMemoryRouter`) would be the other way to do this, but it
 * builds a `Request` per navigation, which fights the stubbed global fetch.
 */
let probeSearch = '';
let probeNavigate: NavigateFunction | null = null;
function RouterProbe() {
  probeSearch = useLocation().search;
  probeNavigate = useNavigate();
  return null;
}

interface GraphView extends RenderResult {
  calls: string[];
  search: () => string;
  back: () => void;
  forward: () => void;
}

async function renderGraph(initialEntry = '/memory'): Promise<GraphView> {
  const calls = stubFetchRoutes(routes);
  const view = render(
    <MemoryRouter
      initialEntries={[initialEntry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
      <RouterProbe />
    </MemoryRouter>,
  );
  if (!initialEntry.includes('tab=graph')) {
    fireEvent.click(await view.findByRole('tab', { name: 'Graph' }));
  }
  await view.findByText('Graph', { selector: 'h2' });
  return Object.assign(view, {
    calls,
    search: () => probeSearch,
    back: () => probeNavigate?.(-1),
    forward: () => probeNavigate?.(1),
  });
}

const bar = (view: RenderResult) =>
  view.getByRole('combobox', { name: 'Graph command' }) as HTMLInputElement;

function type(view: RenderResult, text: string) {
  fireEvent.change(bar(view), { target: { value: text } });
}

function submit(view: RenderResult, text: string): void {
  type(view, text);
  fireEvent.keyDown(bar(view), { key: 'Enter' });
}

const nodeCount = () => document.querySelectorAll('.memory-graph-node').length;
const edgeCount = () => document.querySelectorAll('.memory-graph-edge').length;
const live = () => (document.querySelector('.memory-graph-live') as HTMLElement | null)?.textContent ?? '';

// --- 1. every supported command drives the canonical state -------------------

describe('graph command bar — commands drive the canonical state', () => {
  it('`find` filters the same nodes the search box filters', async () => {
    const view = await renderGraph();
    expect(nodeCount()).toBe(5);

    submit(view, 'find other');
    await waitFor(() => expect(nodeCount()).toBe(1));
    // The visible search control reflects the SAME state — one model, not two.
    expect((view.getByPlaceholderText('Search files and concepts…') as HTMLInputElement).value).toBe(
      'other',
    );
  });

  it('`type` and `community` filter, and `clear filters` restores everything', async () => {
    const view = await renderGraph();
    submit(view, 'type concept');
    await waitFor(() => expect(nodeCount()).toBe(2));

    submit(view, 'type all');
    await waitFor(() => expect(nodeCount()).toBe(5));

    submit(view, 'community Export Pipeline');
    await waitFor(() => expect(nodeCount()).toBe(2));

    submit(view, 'clear filters');
    await waitFor(() => expect(nodeCount()).toBe(5));
  });

  it('`select` selects, and the detail panel follows', async () => {
    const view = await renderGraph();
    submit(view, 'select src/other_mod.py');
    await waitFor(() =>
      expect(document.querySelector('.memory-graph-node.selected')).not.toBeNull(),
    );
    expect(view.container.textContent).toContain('src/other_mod.py');
  });

  it('`neighbors … depth 2` focuses a bounded neighbourhood and announces it', async () => {
    const view = await renderGraph();
    submit(view, 'neighbors src/fake_mod.py depth 2');
    await waitFor(() => expect(nodeCount()).toBe(2));
    expect(edgeCount()).toBe(1);
    expect(live()).toMatch(/2-hop neighbourhood of src\/fake_mod\.py/);
  });

  it('`path a -> b` focuses a real route; a disconnected pair is refused honestly', async () => {
    const view = await renderGraph();
    submit(view, 'path src/fake_mod.py -> src/other_mod.py');
    await waitFor(() => expect(nodeCount()).toBe(2));
    expect(live()).toMatch(/Found a 1-step route/);

    submit(view, 'path src/fake_mod.py -> docs/fake-note.md');
    await waitFor(() => expect(live()).toMatch(/No path connects/));
    // Nothing was invented to satisfy the request.
    expect(live()).toMatch(/separate components/);
  });

  it('`relation none` draws no lines and `relation all` restores them', async () => {
    const view = await renderGraph();
    expect(edgeCount()).toBe(1);
    submit(view, 'relation none');
    await waitFor(() => expect(edgeCount()).toBe(0));
    submit(view, 'relation all');
    await waitFor(() => expect(edgeCount()).toBe(1));
  });

  it('`reset` returns the viewport to its default', async () => {
    const view = await renderGraph();
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    await waitFor(() => expect(view.container.textContent).toContain('zoom 125%'));
    submit(view, 'reset');
    await waitFor(() => expect(view.container.textContent).toContain('zoom 100%'));
  });

  it('`help` opens the syntax panel, which documents the whole grammar', async () => {
    const view = await renderGraph();
    submit(view, 'help');
    const dialog = await view.findByRole('dialog');
    expect(dialog.textContent).toContain('Command syntax');
    expect(dialog.textContent).toContain('path <node-a> -> <node-b>');
    expect(dialog.textContent).toContain('neighbors <node> [depth 1|2]');
  });
});

// --- 2. errors and ambiguity change nothing ---------------------------------

describe('graph command bar — honest failure', () => {
  it('a syntax error is announced and leaves the canvas untouched', async () => {
    const view = await renderGraph();
    const before = nodeCount();
    submit(view, 'frobnicate everything');
    await waitFor(() => expect(live()).toMatch(/Unknown command `frobnicate`/));
    expect(nodeCount()).toBe(before);
    expect(edgeCount()).toBe(1);
    expect(document.querySelector('.memory-graph-node.selected')).toBeNull();
  });

  it('a bad enum value names what was wrong and runs nothing', async () => {
    const view = await renderGraph();
    submit(view, 'type files');
    await waitFor(() => expect(live()).toMatch(/accepts file, concept, or all — got `files`/));
    expect(nodeCount()).toBe(5);
  });

  it('an ambiguous token lists bounded candidates and selects nothing', async () => {
    const view = await renderGraph();
    submit(view, 'select mod');
    await waitFor(() => expect(live()).toMatch(/matches 2 nodes/));
    expect(document.querySelector('.memory-graph-node.selected')).toBeNull();
    const candidates = document.querySelectorAll('.memory-graph-candidate-btn');
    expect(candidates.length).toBe(2);
    // Picking one is the user's decision, never the parser's.
    fireEvent.click(candidates[0]);
    await waitFor(() =>
      expect(document.querySelector('.memory-graph-node.selected')).not.toBeNull(),
    );
  });

  it('an ambiguous CLUSTER lists readable cluster labels, not bare numeric ids', async () => {
    // A command can surface eight clusters at once; a row of `41 55 48` names
    // nothing a reader can choose between.
    const many = {
      ...memoryGraphAvailable,
      communities: [
        ...memoryGraphAvailable.communities,
        { id: '900', name: 'Export Pipeline A', file_count: 4 },
        { id: '901', name: 'Export Pipeline B', file_count: 3 },
      ],
    };
    vi.unstubAllGlobals();
    stubFetchRoutes({ ...routes, 'GET /api/memory/graph': { body: many } });
    const view = render(
      <MemoryRouter
        initialEntries={['/memory?tab=graph']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <ProjectMemory />
      </MemoryRouter>,
    );
    await view.findByText('Graph', { selector: 'h2' });

    submit(view, 'community Pipeline');
    await waitFor(() => expect(live()).toMatch(/matches 3 clusters/));
    const labels = [...document.querySelectorAll('.memory-graph-candidate-btn')].map(
      (b) => b.textContent,
    );
    expect(labels).toEqual([
      'Export Pipeline A · 4 files',
      'Export Pipeline B · 3 files',
      'Export Pipeline · 1 file',
    ]);
  });

  it('a missing node is reported as missing', async () => {
    const view = await renderGraph();
    submit(view, 'select nowhere/at/all.py');
    await waitFor(() => expect(live()).toMatch(/No node in this projection matches/));
    expect(document.querySelector('.memory-graph-node.selected')).toBeNull();
  });

  it('hostile input is rejected as a syntax error, never executed', async () => {
    const view = await renderGraph();
    for (const hostile of ['eval(1+1)', '<script>alert(1)</script>', 'require("fs")']) {
      submit(view, hostile);
      await waitFor(() => expect(live()).toMatch(/Unknown command/));
      expect(nodeCount()).toBe(5);
    }
    expect((globalThis as Record<string, unknown>).__pwned).toBeUndefined();
    // And a hostile string inside a legal argument is inert data.
    submit(view, 'find <img onerror=alert(1)>');
    await waitFor(() => expect(nodeCount()).toBe(0));
    expect(document.querySelector('img')).toBeNull();
  });

  it('announces EVERY successful command in the one live region', async () => {
    // Seven of the eleven verbs announced nothing at all: `find`, `type`,
    // `community`, `relation`, `fit`, `clear` and `select` leave the reducer's
    // notice null, so a screen-reader user got silence for every filter and
    // selection they ran. All eleven now route an outcome through the SAME
    // region — no second live region was added.
    const view = await renderGraph();
    const spoken: Record<string, string> = {};
    const cases: [string, RegExp][] = [
      ['find other', /find other — 1 of 5 nodes shown/],
      ['type file', /type file — 1 of 5 nodes shown/],
      ['community all', /community all — 1 of 5 nodes shown/],
      ['relation imports', /relation imports — 1 of 5 nodes shown/],
      ['fit', /Framed the visible nodes — 1 of 5 nodes shown/],
      ['clear filters', /Filters cleared — 5 of 5 nodes shown/],
      ['select src/other_mod.py', /Selected src\/other_mod\.py\. 5 of 5 nodes shown/],
      ['neighbors src/fake_mod.py', /1-hop neighbourhood of src\/fake_mod\.py — 2 nodes shown/],
      ['path src/fake_mod.py -> src/other_mod.py', /Found a 1-step route/],
      ['reset', /Viewport reset and node drags undone — 2 of 5 nodes shown/],
      ['help', /Opened the command syntax/],
    ];
    for (const [command, expected] of cases) {
      submit(view, command);
      await waitFor(() => expect(live(), `no announcement for \`${command}\``).toMatch(expected));
      spoken[command] = live();
    }
    // Every one of the eleven said something.
    expect(Object.keys(spoken).length).toBe(11);
    for (const [command, text] of Object.entries(spoken)) {
      expect(text.trim(), `\`${command}\` announced nothing`).not.toBe('');
    }
    // And the surface still has exactly one polite region.
    const card = view.container.querySelector('.memory-graph-card') as HTMLElement;
    expect(card.querySelectorAll('[aria-live]').length).toBe(1);
  });

  it('a new command replaces the previous announcement rather than leaving it standing', async () => {
    const view = await renderGraph();
    submit(view, 'neighbors src/fake_mod.py');
    await waitFor(() => expect(live()).toMatch(/1-hop neighbourhood/));
    submit(view, 'fit');
    // Before this, `fit` re-announced the neighbourhood as if it were what had
    // just happened.
    await waitFor(() => expect(live()).toMatch(/Framed the visible nodes/));
    expect(live()).not.toMatch(/neighbourhood/);
  });

  it('exposes exactly ONE polite live region on the surface', async () => {
    const view = await renderGraph();
    submit(view, 'frobnicate');
    await waitFor(() => expect(live()).toMatch(/Unknown command/));
    // Scoped to the graph card: the Assistant rail legitimately owns its own
    // single polite region, and the command bar adds none of its own.
    const card = view.container.querySelector('.memory-graph-card') as HTMLElement;
    const polite = card.querySelectorAll('[aria-live]');
    expect(polite.length).toBe(1);
    expect(polite[0]).toHaveClass('memory-graph-live');
    expect(view.container.querySelector('.graph-cmd')?.querySelector('[aria-live]')).toBeNull();
  });
});

// --- 3. completions + keyboard ----------------------------------------------

describe('graph command bar — keyboard-first', () => {
  it('offers completions and accepts the active one with Enter without running it', async () => {
    const view = await renderGraph();
    type(view, 'select mo');
    const list = await view.findByRole('listbox', { name: 'Command completions' });
    expect([...list.querySelectorAll('[role="option"]')].map((o) => o.textContent)).toEqual([
      expect.stringContaining('src/fake_mod.py'),
      expect.stringContaining('src/other_mod.py'),
    ]);

    fireEvent.keyDown(bar(view), { key: 'ArrowDown' });
    expect(list.querySelectorAll('[role="option"]')[0]).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(bar(view), { key: 'Enter' });
    // Accepted into the input; NOT run — the user still has to confirm.
    expect(bar(view).value).toBe('select src/fake_mod.py');
    expect(document.querySelector('.memory-graph-node.selected')).toBeNull();

    fireEvent.keyDown(bar(view), { key: 'Enter' });
    await waitFor(() =>
      expect(document.querySelector('.memory-graph-node.selected')).not.toBeNull(),
    );
  });

  it('recalls previous commands with ArrowUp when no completion list is open', async () => {
    const view = await renderGraph();
    submit(view, 'type file');
    await waitFor(() => expect(nodeCount()).toBe(3));
    expect(bar(view).value).toBe('');

    fireEvent.keyDown(bar(view), { key: 'ArrowUp' });
    expect(bar(view).value).toBe('type file');
    fireEvent.keyDown(bar(view), { key: 'ArrowDown' });
    expect(bar(view).value).toBe('');
  });

  it('returns focus to the control that OPENED the syntax panel', async () => {
    const view = await renderGraph();
    // Typed `help`: focus belongs back in the command input the user was in,
    // not on the "About this graph" trigger they never touched.
    bar(view).focus();
    submit(view, 'help');
    await view.findByRole('dialog');
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(view.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(bar(view));

    // The "Syntax" button next to the bar returns to itself.
    const syntax = view.getByRole('button', { name: 'Graph command syntax' });
    syntax.focus();
    fireEvent.click(syntax);
    await view.findByRole('dialog');
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(view.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(syntax);

    // …and the card's own trigger still returns to the card's own trigger.
    const trigger = view.getByRole('button', { name: /About this graph/ });
    trigger.focus();
    fireEvent.click(trigger);
    await view.findByRole('dialog');
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(view.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  it('Escape closes the completion list, then clears the input', async () => {
    const view = await renderGraph();
    type(view, 'sel');
    await view.findByRole('listbox', { name: 'Command completions' });
    fireEvent.keyDown(bar(view), { key: 'Escape' });
    expect(view.queryByRole('listbox', { name: 'Command completions' })).toBeNull();
    fireEvent.keyDown(bar(view), { key: 'Escape' });
    expect(bar(view).value).toBe('');
  });
});

// --- 4. the results history is ephemeral ------------------------------------

describe('graph command bar — ephemeral history', () => {
  it('records what each command did, and says plainly that it is not saved', async () => {
    const view = await renderGraph();
    submit(view, 'neighbors src/fake_mod.py');
    await waitFor(() => expect(nodeCount()).toBe(2));
    const history = view.container.querySelector('.graph-cmd-history') as HTMLElement;
    expect(history.textContent).toContain('this session only, never saved');
    expect(history.textContent).toContain('neighbors src/fake_mod.py');
    expect(history.textContent).toMatch(/1-hop neighbourhood/);
  });

  it('never writes the command text to storage, a cookie, or the backend', async () => {
    const view = await renderGraph();
    const calls = view.calls;
    submit(view, 'find secret-looking-token');
    await waitFor(() => expect(view.container.textContent).toContain('secret-looking-token'));

    expect(JSON.stringify({ ...window.localStorage })).not.toContain('secret-looking-token');
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain('secret-looking-token');
    expect(document.cookie).not.toContain('secret-looking-token');
    // The graph surface makes exactly the ONE fetch it made before the bar existed.
    expect(calls.filter((c) => c.includes('/api/memory/graph')).length).toBe(1);
    expect(calls.some((c) => c.includes('assistant'))).toBe(false);
  });

  it('clears on request, and the graph state is untouched by clearing', async () => {
    const view = await renderGraph();
    submit(view, 'type file');
    await waitFor(() => expect(nodeCount()).toBe(3));
    fireEvent.click(view.getByRole('button', { name: /Clear$/ }));
    expect(view.container.querySelector('.graph-cmd-history')).toBeNull();
    expect(nodeCount()).toBe(3);
  });
});

// --- 5. URL state ------------------------------------------------------------

describe('graph command bar — bounded URL state', () => {
  it('writes a bounded, shareable link after a command — and nothing else', async () => {
    const view = await renderGraph();
    submit(view, 'neighbors src/fake_mod.py depth 2');
    await waitFor(() => expect(nodeCount()).toBe(2));

    const params = new URLSearchParams(view.search());
    expect(params.get('tab')).toBe('graph');
    expect(params.get('gnbr')).toBe('src/fake_mod.py');
    expect(params.get('gdepth')).toBe('2');
    expect(params.get('gmode')).toBe('explore');
    // Bounded: only the documented keys, never a serialized blob.
    expect([...params.keys()].sort()).toEqual(['gdepth', 'gmode', 'gnbr', 'tab']);
  });

  it('a viewport change is NOT pushed — a link is state, not a scroll position', async () => {
    const view = await renderGraph();
    submit(view, 'type file');
    await waitFor(() => expect(nodeCount()).toBe(3));
    const before = view.search();
    fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
    fireEvent.change(view.getByPlaceholderText('Search files and concepts…'), {
      target: { value: 'other' },
    });
    await waitFor(() => expect(nodeCount()).toBe(1));
    expect(view.search()).toBe(before);
  });

  it('reloading the link reproduces the same state', async () => {
    const first = await renderGraph();
    submit(first, 'neighbors src/fake_mod.py depth 2');
    await waitFor(() => expect(nodeCount()).toBe(2));
    const link = `/memory${first.search()}`;
    first.unmount();

    // A "reload" is a fresh mount at exactly that location.
    const reloaded = await renderGraph(link);
    expect(reloaded.getAllByRole('tab', { selected: true })[0].textContent).toBe('Graph');
    expect(reloaded.container.querySelectorAll('.memory-graph-node').length).toBe(2);
    expect(reloaded.container.textContent).toMatch(/2-hop neighbourhood of src\/fake_mod\.py/);
  });

  it('restores filters and a selection from a link', async () => {
    const view = await renderGraph('/memory?tab=graph&gmode=explore&gtype=file&gq=other');
    expect(
      (view.getByPlaceholderText('Search files and concepts…') as HTMLInputElement).value,
    ).toBe('other');
    expect(view.container.querySelectorAll('.memory-graph-node').length).toBe(1);
    view.unmount();

    const selected = await renderGraph('/memory?tab=graph&gnode=src%2Fother_mod.py');
    expect(selected.container.querySelector('.memory-graph-node.selected')).not.toBeNull();
  });

  it('bounds the search input so a link can never be wider than the view it came from', async () => {
    const view = await renderGraph();
    // The encoder DROPS an over-long `gq` (a truncated query is a broader
    // filter). Bounding the input is what makes that branch unreachable from
    // the UI, so a shared link always carries the search the author had.
    expect(view.getByPlaceholderText('Search files and concepts…')).toHaveAttribute(
      'maxlength',
      '120',
    );
  });

  it('a `gdepth` outside {1,2} drops the neighbourhood instead of showing depth 1', async () => {
    const view = await renderGraph('/memory?tab=graph&gnbr=src%2Ffake_mod.py&gdepth=99');
    // The link asked for something the grammar does not have. Coercing it to 1
    // would have produced a real, plausible, WRONG view.
    expect(view.container.querySelector('.memory-graph-focuschip')).toBeNull();
    expect(view.container.querySelectorAll('.memory-graph-node').length).toBe(5);
  });

  it('an unusable link parameter is refused honestly, never guessed', async () => {
    const view = await renderGraph('/memory?tab=graph&gnode=does%2Fnot%2Fexist.py');
    expect(view.container.querySelector('.memory-graph-node.selected')).toBeNull();
    expect(view.container.textContent).toMatch(/No node in this projection matches/);
    view.unmount();

    const bogusEnum = await renderGraph('/memory?tab=graph&gtype=executable&gmode=evil');
    // Dropped at the boundary: the default view, no crash, no partial state.
    expect(bogusEnum.container.querySelectorAll('.memory-graph-node').length).toBe(5);
  });

  it('browser back and forward move between the states the commands created', async () => {
    const view = await renderGraph();
    submit(view, 'type file');
    await waitFor(() => expect(nodeCount()).toBe(3));
    submit(view, 'type concept');
    await waitFor(() => expect(nodeCount()).toBe(2));

    view.back();
    await waitFor(() => expect(nodeCount()).toBe(3));
    expect(new URLSearchParams(view.search()).get('gtype')).toBe('file');

    view.forward();
    await waitFor(() => expect(nodeCount()).toBe(2));
    expect(new URLSearchParams(view.search()).get('gtype')).toBe('concept');
  });
});

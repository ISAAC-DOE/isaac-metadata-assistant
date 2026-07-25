import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, fireEvent, waitFor, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import { AssistantPanel } from '../components/AssistantPanel';
import { api } from '../lib/api';
import { clearAllSessions } from '../lib/assistantSession';
import {
  stubFetchRoutes,
  graphStatusUnavailable,
  memoryGraphAvailable,
} from '../test/apiFixtures';
import type { AssistantQueryResponse, SuggestedPrompt } from '../lib/types';

/*
 * P36R Slice 5 — the Assistant's bounded graph intents.
 *
 * The classifier itself is unit-tested in graph-commands.test.ts (including the
 * proof that it emits the SAME `GraphAction`s the command bar produces). What is
 * guarded here is the Assistant contract:
 *   - a recognised graph question is intercepted BEFORE the network call;
 *   - it PROPOSES; the graph is provably unchanged until "Apply to Graph";
 *   - ambiguity lists bounded candidates and applies nothing;
 *   - a miss falls straight through to the unchanged read-only resolver;
 *   - the four record surfaces never receive the capability at all.
 */

const routes = {
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/graph': { body: memoryGraphAvailable },
};

beforeEach(() => {
  clearAllSessions();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  clearAllSessions();
});

async function renderMemory(): Promise<RenderResult & { calls: string[] }> {
  const calls = stubFetchRoutes(routes);
  const view = render(
    <MemoryRouter
      initialEntries={['/memory']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
    </MemoryRouter>,
  );
  await view.findByRole('tab', { name: 'Graph' });
  fireEvent.click(view.getByRole('tab', { name: 'Graph' }));
  await view.findByText('Graph', { selector: 'h2' });
  return Object.assign(view, { calls });
}

function ask(view: RenderResult, question: string) {
  const input = view.getByLabelText('Ask the assistant a question');
  fireEvent.change(input, { target: { value: question } });
  fireEvent.submit(input.closest('form') as HTMLFormElement);
}

const nodeCount = () => document.querySelectorAll('.memory-graph-node').length;
const edgeCount = () => document.querySelectorAll('.memory-graph-edge').length;
const proposal = (view: RenderResult) =>
  view.container.querySelector('.assistant-graph') as HTMLElement | null;

// --- 1. proposals, never silent manipulation --------------------------------

describe('Assistant graph intents — propose, never apply', () => {
  it('answers a neighbourhood question WITHOUT touching the graph, then applies on request', async () => {
    const view = await renderMemory();
    const before = { nodes: nodeCount(), edges: edgeCount() };
    expect(before.nodes).toBe(5);

    ask(view, 'Show neighbors of src/fake_mod.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());

    // The proposal exists; the graph is byte-for-byte where it was.
    expect(nodeCount()).toBe(before.nodes);
    expect(edgeCount()).toBe(before.edges);
    expect(document.querySelector('.memory-graph-node.selected')).toBeNull();
    const card = proposal(view) as HTMLElement;
    expect(card.textContent).toContain('Graph Navigation — Not Applied');
    // It shows the equivalent command — the two front-ends are visibly one.
    expect(card.textContent).toContain('neighbors src/fake_mod.py');
    // …and the projection's own provenance.
    expect(card.textContent).toMatch(/served-file projection/);
    expect(card.textContent).toMatch(/commit caab1d0a69c1/);

    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(nodeCount()).toBe(2));
    // The proposal is consumed, and what happened is stated after the fact.
    expect(proposal(view)).toBeNull();
    expect(view.container.textContent).toMatch(/Applied to the graph/);
  });

  it('dismissing a proposal applies nothing', async () => {
    const view = await renderMemory();
    ask(view, 'Show only concepts');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    fireEvent.click(view.getByRole('button', { name: /Dismiss/ }));
    await waitFor(() => expect(proposal(view)).toBeNull());
    expect(nodeCount()).toBe(5);
  });

  it('a path question proposes the route and applies it only on request', async () => {
    const view = await renderMemory();
    ask(view, 'Find a path from src/fake_mod.py to src/other_mod.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    expect(view.container.textContent).toMatch(/1-step route exists/);
    expect(nodeCount()).toBe(5);

    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(nodeCount()).toBe(2));
    expect(view.container.textContent).toMatch(/Found a 1-step route/);
  });

  it('a cluster question resolves a cluster and applies as a filter', async () => {
    const view = await renderMemory();
    ask(view, 'Show the community for src/fake_mod.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    expect(nodeCount()).toBe(5);
    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(nodeCount()).toBe(2));
  });

  it('a multi-action proposal applies as ONE unit through the same reducer', async () => {
    const view = await renderMemory();
    ask(view, 'Find files related to other');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    // Both halves of the equivalent command sequence are advertised.
    expect((proposal(view) as HTMLElement).textContent).toContain('type file · find other');
    expect(nodeCount()).toBe(5);

    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(nodeCount()).toBe(1));
    // The visible controls show the SAME state — one model, not two.
    expect(
      (view.getByPlaceholderText('Search files and concepts…') as HTMLInputElement).value,
    ).toBe('other');
  });

  it('a relationship filter the projection records is proposed, and applied on request', async () => {
    const view = await renderMemory();
    expect(edgeCount()).toBe(1);
    ask(view, 'Only show imports relationships');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    expect((proposal(view) as HTMLElement).textContent).toContain('relation imports');
    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(view.container.textContent).toMatch(/Applied to the graph/));
    // `imports` is the only recorded type here, so the drawn set is unchanged —
    // and the copy says what it did, never more.
    expect(edgeCount()).toBe(1);
  });

  it('an unrecorded relationship type is refused rather than invented', async () => {
    const view = await renderMemory();
    ask(view, 'Only show mentions relationships');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    expect(view.container.textContent).toMatch(/not one of them/);
    expect(view.queryByRole('button', { name: /Apply to Graph/ })).toBeNull();
    expect(edgeCount()).toBe(1);
  });
});

// --- 1b. a stated count is the count Apply produces -------------------------

/*
 * The C1 regression, end to end through the real screen: the card's number and
 * the canvas's number after pressing Apply, measured against each other under a
 * NON-default filter state. That is the only place the old parallel estimate
 * was wrong, and the only place a test can see it.
 */
describe('Assistant graph intents — the stated count is the applied count', () => {
  const command = (view: RenderResult, text: string) => {
    const input = view.getByRole('combobox', { name: 'Graph command' });
    fireEvent.change(input, { target: { value: text } });
    fireEvent.keyDown(input, { key: 'Enter' });
  };
  const shown = () =>
    document.querySelector('.memory-graph-list-summary')?.textContent?.trim() ?? '';
  /** The Assistant's own answer text — the card carries the title, the
   *  equivalent command and the provenance; the count-bearing explanation is
   *  spoken in the reply. */
  const reply = () => document.querySelector('.assistant-reply')?.textContent ?? '';

  it('states the count applying produces when nothing is filtered', async () => {
    const view = await renderMemory();
    ask(view, 'Show neighbors of src/fake_mod.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    expect(reply()).toMatch(/Applying it shows 2 of the 5 nodes, including src\/fake_mod\.py itself/);
    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(nodeCount()).toBe(2));
    expect(shown()).toMatch(/^2 of 5 nodes shown/);
  });

  it('under `type concept` it says NOTHING will be shown — and nothing is', async () => {
    const view = await renderMemory();
    command(view, 'type concept');
    await waitFor(() => expect(nodeCount()).toBe(2));

    ask(view, 'Show neighbors of src/fake_mod.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    // The old text said "Focusing it draws 2 nodes, including … itself" here.
    expect(reply()).toMatch(/would show NOTHING/);
    expect(reply()).toMatch(/the node-type filter `type concept`/);
    expect(reply()).toMatch(/clear filters/);
    expect(reply()).not.toMatch(/Applying it shows \d+ of the/);

    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(shown()).toMatch(/^0 of 5 nodes shown/));
    expect(nodeCount()).toBe(0);
    // …and the surface's own announcement agrees, and explains the difference.
    expect(view.container.textContent).toMatch(/0 nodes shown/);
    expect(view.container.textContent).toMatch(/The neighbourhood holds 2 nodes/);
  });

  it('under a search that matches nothing it says the same, naming the search', async () => {
    const view = await renderMemory();
    command(view, 'find zzzznomatch');
    await waitFor(() => expect(nodeCount()).toBe(0));

    ask(view, 'Show neighbors of src/fake_mod.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    expect(reply()).toMatch(/would show NOTHING/);
    expect(reply()).toMatch(/the search "zzzznomatch"/);

    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(view.container.textContent).toMatch(/0 nodes shown/));
    expect(nodeCount()).toBe(0);
  });

  it('applying leaves the user in the view mode they chose', async () => {
    const view = await renderMemory();
    fireEvent.click(view.getByRole('radio', { name: 'Browse' }));
    await waitFor(() =>
      expect(view.getByRole('radio', { name: 'Browse' })).toHaveAttribute('aria-checked', 'true'),
    );
    ask(view, 'Show only concepts');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(view.container.textContent).toMatch(/Applied to the graph/));
    // Apply used to prepend a mode switch and silently pull the user into
    // Explore — a state change the card never said it would make.
    expect(view.getByRole('radio', { name: 'Browse' })).toHaveAttribute('aria-checked', 'true');
    expect(shown()).toMatch(/^2 of 5 nodes shown/);
  });
});

// --- 2. honest failure ------------------------------------------------------

describe('Assistant graph intents — honest failure', () => {
  it('lists bounded candidates for an ambiguous node and offers NO apply', async () => {
    const view = await renderMemory();
    ask(view, 'Show neighbors of mod');
    await waitFor(() => expect(proposal(view)).not.toBeNull());

    const card = proposal(view) as HTMLElement;
    expect(card.textContent).toMatch(/matches 2 nodes/);
    expect(view.queryByRole('button', { name: /Apply to Graph/ })).toBeNull();
    expect(card.textContent).toContain('Nothing to apply');

    const choices = card.querySelectorAll('.assistant-graph-choice');
    expect([...choices].map((c) => c.textContent)).toEqual([
      'src/fake_mod.py',
      'src/other_mod.py',
    ]);
    expect(nodeCount()).toBe(5);

    // Picking a candidate resolves it — and STILL only proposes.
    fireEvent.click(choices[0]);
    await waitFor(() =>
      expect(view.queryByRole('button', { name: /Apply to Graph/ })).not.toBeNull(),
    );
    expect(nodeCount()).toBe(5);
    fireEvent.click(view.getByRole('button', { name: /Apply to Graph/ }));
    await waitFor(() => expect(nodeCount()).toBe(2));
  });

  it('says a missing node is missing and proposes nothing', async () => {
    const view = await renderMemory();
    ask(view, 'Show neighbors of nowhere/at/all.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    expect(view.container.textContent).toMatch(/No node in this projection matches/);
    expect(view.container.textContent).toMatch(/no approximate match was substituted/);
    expect(view.queryByRole('button', { name: /Apply to Graph/ })).toBeNull();
    expect(nodeCount()).toBe(5);
  });

  it('says "no route" honestly and never fabricates connectivity', async () => {
    const view = await renderMemory();
    ask(view, 'Find a path from src/fake_mod.py to docs/fake-note.md');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    expect(view.container.textContent).toMatch(/No route connects/);
    expect(view.container.textContent).toMatch(/no connection was invented/);
    expect(view.queryByRole('button', { name: /Apply to Graph/ })).toBeNull();
  });

  it('states plainly that applying changes only the view', async () => {
    const view = await renderMemory();
    ask(view, 'Reset the graph');
    await waitFor(() => expect(proposal(view)).not.toBeNull());
    const card = proposal(view) as HTMLElement;
    expect(card.textContent).toMatch(
      /validates nothing, completes no field, and authorises no export/,
    );
  });
});

// --- 3. no network for an intercepted intent; a miss falls through ----------

describe('Assistant graph intents — interception boundary', () => {
  it('makes NO backend call for a recognised graph question', async () => {
    const view = await renderMemory();
    const askMemory = vi.spyOn(api, 'askMemory');
    const askAssistant = vi.spyOn(api, 'askAssistant');
    const before = view.calls.length;

    ask(view, 'Show neighbors of src/fake_mod.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());

    expect(askMemory).not.toHaveBeenCalled();
    expect(askAssistant).not.toHaveBeenCalled();
    expect(view.calls.length).toBe(before);
    expect(view.calls.some((c) => c.includes('assistant'))).toBe(false);
  });

  it('falls through to the unchanged read-only resolver for anything else', async () => {
    const view = await renderMemory();
    const answer: AssistantQueryResponse = {
      answer: 'Memory returns leads to verify, never a verdict.',
      result: 'answered',
      grounding: ['graph'],
      sources: [],
      record_rev: null,
      version: null,
      stale: false,
      followups: [],
    };
    const askMemory = vi.spyOn(api, 'askMemory').mockResolvedValue(answer);

    ask(view, 'What does project memory know about provenance?');
    await waitFor(() => expect(askMemory).toHaveBeenCalledTimes(1));
    expect(proposal(view)).toBeNull();
    expect(view.container.textContent).toContain('Memory returns leads to verify');
    expect(nodeCount()).toBe(5);
  });

  it('refuses an out-of-scope request through the existing path, not the graph', async () => {
    const view = await renderMemory();
    const refusal: AssistantQueryResponse = {
      answer: 'That is outside what this assistant can answer.',
      result: 'unsupported',
      grounding: [],
      sources: [],
      record_rev: null,
      version: null,
      stale: false,
      followups: [],
    };
    vi.spyOn(api, 'askMemory').mockResolvedValue(refusal);
    ask(view, 'Delete every record and rebuild the graph from scratch');
    await waitFor(() =>
      expect(view.container.textContent).toContain('outside what this assistant can answer'),
    );
    expect(proposal(view)).toBeNull();
    expect(nodeCount()).toBe(5);
  });
});

// --- 4. the four record surfaces are untouched ------------------------------

describe('Assistant graph intents — capability scope', () => {
  const screenSources = import.meta.glob(
    [
      '../screens/RecordWorkbench.tsx',
      '../screens/GuidedCompletion.tsx',
      '../screens/EvidenceExplorer.tsx',
      '../screens/ExportReadiness.tsx',
    ],
    { query: '?raw', import: 'default', eager: true },
  ) as Record<string, string>;

  it('no record surface passes the graph capability', () => {
    expect(Object.keys(screenSources).length).toBe(4);
    for (const [path, source] of Object.entries(screenSources)) {
      expect(source, `${path} must not opt into graph intents`).not.toContain('graphCapability');
      expect(source).not.toContain('classifyGraphQuestion');
    }
  });

  it('a panel with NO capability sends a graph-shaped question to the backend, unchanged', async () => {
    const PROMPTS: SuggestedPrompt[] = [];
    const answer: AssistantQueryResponse = {
      answer: 'Answered from the record.',
      result: 'answered',
      grounding: ['workflow'],
      sources: [],
      record_rev: 3,
      version: 'v3',
      stale: false,
      followups: [],
    };
    const askAssistant = vi.spyOn(api, 'askAssistant').mockResolvedValue(answer);
    const view = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AssistantPanel
          reply={{ text: 'x', answeredFrom: 'workflow' }}
          prompts={PROMPTS}
          experimentId="01EXPERIMENTA0000000000000"
        />
      </MemoryRouter>,
    );

    ask(view, 'Show neighbors of src/fake_mod.py');
    await waitFor(() => expect(askAssistant).toHaveBeenCalledTimes(1));
    expect(askAssistant.mock.calls[0][1]).toEqual({
      question: 'Show neighbors of src/fake_mod.py',
    });
    expect(view.container.querySelector('.assistant-graph')).toBeNull();
    expect(view.container.textContent).toContain('Answered from the record.');
  });

  it('an unapplied proposal is DROPPED when the Graph tab stops showing', async () => {
    const view = await renderMemory();
    ask(view, 'Show neighbors of src/fake_mod.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());

    // The proposal belongs to the surface it was resolved against. It used to
    // survive the excursion and re-appear on return, offering counts derived
    // from a GraphSurfaceContext that no longer existed.
    fireEvent.click(view.getByRole('tab', { name: 'Overview' }));
    await waitFor(() => expect(proposal(view)).toBeNull());

    fireEvent.click(view.getByRole('tab', { name: 'Graph' }));
    await view.findByText('Graph', { selector: 'h2' });
    expect(proposal(view)).toBeNull();
    // Dropping it applied nothing — the graph is exactly where it was.
    expect(nodeCount()).toBe(5);
  });

  it('the capability is withdrawn when the Graph tab is not showing', async () => {
    const view = await renderMemory();
    ask(view, 'Show neighbors of src/fake_mod.py');
    await waitFor(() => expect(proposal(view)).not.toBeNull());

    fireEvent.click(view.getByRole('tab', { name: 'Overview' }));
    const askMemory = vi.spyOn(api, 'askMemory').mockResolvedValue({
      answer: 'Answered from memory.',
      result: 'answered',
      grounding: ['graph'],
      sources: [],
      record_rev: null,
      version: null,
      stale: false,
      followups: [],
    });
    ask(view, 'Show neighbors of src/fake_mod.py');
    await waitFor(() => expect(askMemory).toHaveBeenCalledTimes(1));
  });
});

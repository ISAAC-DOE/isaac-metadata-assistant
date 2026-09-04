import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor, within, type RenderResult } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import axe from 'axe-core';
import { AppRoutes } from '../App';
import { ExperimentGraphPanel } from '../screens/graph/ExperimentGraphPanel';
import { bundleRoutes, stubFetchRoutes } from '../test/apiFixtures';
import {
  GRAPH_EXP_ID,
  experimentGraphBundle,
  experimentGraphRoutes,
  exportedExperimentGraphBundle,
  stressExperimentGraphBundle,
} from '../test/experimentGraphFixtures';
import type { ExperimentGraphBundle } from '../lib/types';

/*
 * The EXPERIMENT-SCOPED graph, rendered.
 *
 * What this file is here to hold in place:
 *
 *  · the graph is reachable from INSIDE a record, where a scientist already is
 *    — not from Project Memory, which is a graph of the repository;
 *  · the view is deep-linkable, so a graph can be shared;
 *  · the first paint is a neighbourhood, not the whole graph;
 *  · every relationship on screen can say WHY it exists;
 *  · the absence of links is stated, never filled in;
 *  · a graph read in one workspace never renders in another.
 */

/*
 * THE HARNESS DEADLINE, raised so that the BUDGET is what adjudicates.
 *
 * The defect this removes: vitest's default deadline is 5,000 ms and
 * `vite.config.ts` declares no `testTimeout` of its own, so the 12,000 ms budget
 * asserted at the foot of this file could never decide anything. Under 5 s it was
 * satisfied trivially; between 5 s and 12 s the test failed by HARNESS TIMEOUT —
 * reporting "Test timed out in 5000ms", which names neither the budget nor the
 * surface — and past 12 s the harness still got there first. A declared budget
 * that is either vacuous or pre-empted has never tested the property it states.
 *
 * The observable symptom was an intermittent failure of this file and its two
 * neighbours on diffs touching no frontend file at all, which undermines the
 * exact-SHA CI gate every merge here depends on. In isolation these tests run in
 * well under 2 s; the 6.8–10.2 s durations that tripped the deadline were measured
 * under parallel-worker contention, not against a slower product. Nothing under
 * `screens/`, `components/` or `lib/` is touched by this change.
 *
 * 30,000 ms is the value this repository already uses for its other mount-heavy
 * suites (`tutorial-session-lifecycle`, `workspace-scope-invalidation`). It is a
 * HARNESS limit, NOT a performance claim: at 2.5× the declared budget, the budget
 * is now the first thing to fail. `vi.setConfig` is file-scoped — proven rather
 * than assumed: a file that does not call it still times out at 5,000 ms inside
 * the same worker — so the strict default stands everywhere else in the suite.
 */
vi.setConfig({ testTimeout: 30000 });

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="href">{`${loc.pathname}${loc.search}`}</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  );
}

function routesFor(bundle: ExperimentGraphBundle) {
  return { ...bundleRoutes(GRAPH_EXP_ID), ...experimentGraphRoutes(GRAPH_EXP_ID, bundle) };
}

/*
 * THE SWITCHER IS THE SIDEBAR'S WORKSPACE LIST, NOT A TAB BAR.
 *
 * The record screen's `.section-tabs` strip is retired: its two entries folded
 * into `RecordWorkspaceNav` when the record gained four destinations, so one
 * place answers "where can I go from here" instead of a sidebar and a tab bar
 * answering overlapping questions. The `?view=` deep-link mechanism these tests
 * are actually about is UNCHANGED — same parameter, same fallback — so only the
 * control being clicked moved: `role="tab"` + `aria-selected` became a real
 * `<Link>` with `aria-current="page"`.
 */
const workspaceLink = (view: RenderResult, name: string) =>
  view.getByRole('link', { name });

/** Open the record, switch to the Graph workspace, and wait for it to load. */
async function openGraph(bundle: ExperimentGraphBundle = experimentGraphBundle()) {
  stubFetchRoutes(routesFor(bundle));
  const view = renderAt(`/record/${GRAPH_EXP_ID}`);
  const tab = await view.findByRole('link', { name: 'Graph' });
  fireEvent.click(tab);
  await view.findByRole('heading', { name: 'Experiment Graph' });
  return view;
}

const nodeButton = (view: RenderResult, name: string | RegExp) =>
  view.getByRole('button', { name });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the graph lives inside the record, and is linkable', () => {
  it('is a view of the Review Record screen, with the field workbench as the default', async () => {
    stubFetchRoutes(routesFor(experimentGraphBundle()));
    const view = renderAt(`/record/${GRAPH_EXP_ID}`);

    const fieldsTab = await view.findByRole('link', { name: 'Record Fields' });
    expect(fieldsTab).toHaveAttribute('aria-current', 'page');
    expect(workspaceLink(view, 'Graph')).not.toHaveAttribute('aria-current');
    // The graph has NOT been fetched yet: it is opt-in, not a page-load cost.
    expect(view.queryByRole('heading', { name: 'Experiment Graph' })).toBeNull();
  });

  it('deep-links: ?view=graph opens the graph directly', async () => {
    stubFetchRoutes(routesFor(experimentGraphBundle()));
    const view = renderAt(`/record/${GRAPH_EXP_ID}?view=graph`);
    expect(await view.findByRole('heading', { name: 'Experiment Graph' })).toBeInTheDocument();
    expect(workspaceLink(view, 'Graph')).toHaveAttribute('aria-current', 'page');
  });

  it('switching the view writes it to the URL, so the graph can be shared', async () => {
    const view = await openGraph();
    await waitFor(() =>
      expect(view.getByTestId('href').textContent).toBe(`/record/${GRAPH_EXP_ID}?view=graph`),
    );
  });

  it('an unrecognised view falls back to the fields, never to a dead screen', async () => {
    stubFetchRoutes(routesFor(experimentGraphBundle()));
    const view = renderAt(`/record/${GRAPH_EXP_ID}?view=constellation`);
    expect(await view.findByRole('link', { name: 'Record Fields' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('adds NO new backend route — it reads seven endpoints that already existed', async () => {
    const calls = stubFetchRoutes(routesFor(experimentGraphBundle()));
    const view = renderAt(`/record/${GRAPH_EXP_ID}?view=graph`);
    await view.findByRole('heading', { name: 'Experiment Graph' });
    const base = `/api/experiments/${GRAPH_EXP_ID}`;
    const registered = Object.keys(routesFor(experimentGraphBundle()));
    /* THE ONE ENDPOINT THIS SURFACE MAY READ WITH A PARAMETER. `useRecordSession` asks
       for a bounded page of the open questions (`…/pending?limit=50`) rather than the
       complete list, which is the same ROUTE with a parameter on it — this test is about
       routes, and registering the query form as a second key would say the opposite: that
       a parameter makes a new endpoint.

       IT USED TO BE STRIPPED FROM EVERY CALL, which let a query through on EVERY
       endpoint: a future `…/evidence?since=…` or `…/runs?limit=…` would have matched a
       bare registered key and passed unnoticed. Measured, exactly one of the nineteen
       calls this surface makes carries a query, so the allowance is written as the
       single endpoint it is. */
    const BOUNDED_READ = `GET ${base}/pending`;
    for (const call of calls) {
      const [path, query] = call.split('?');
      if (query !== undefined) {
        expect(
          path,
          `${call} carries a query string, and only ${BOUNDED_READ} may`,
        ).toBe(BOUNDED_READ);
      }
      expect(registered).toContain(path);
    }
    expect(calls).toContain(`GET ${base}/artifacts`);
    expect(calls).toContain(`GET ${base}/evidence-classification`);
    expect(calls.some((c) => c.includes('/memory/graph'))).toBe(false);
  });
});

describe('the graph draws an experiment, and explains itself', () => {
  it('anchors on the experiment and shows its producer in the detail pane', async () => {
    const view = await openGraph();
    const detail = view.getByLabelText('Selected node');
    expect(
      within(detail).getByRole('heading', {
        name: 'Synthetic XANES — CuO (Cu K-edge) graph fixture',
      }),
    ).toBeInTheDocument();
    expect(within(detail).getByText(/Where this came from/)).toBeInTheDocument();
    expect(
      within(detail).getByText(/Experiment\.id \/ Experiment\.title/),
    ).toBeInTheDocument();
  });

  it('draws a NEIGHBOURHOOD first, not everything at once', async () => {
    const view = await openGraph();
    const counts = view.getByTestId('expgraph-counts').textContent ?? '';
    const [, drawn, total] = /(\d+) of (\d+) nodes drawn/.exec(counts) ?? [];
    expect(Number(drawn)).toBeGreaterThan(1);
    expect(Number(drawn)).toBeLessThan(Number(total));
  });

  it('expands on demand — a field appears only after its section is opened', async () => {
    const view = await openGraph();
    expect(view.queryByRole('button', { name: /^Formula, Field/ })).toBeNull();

    // Click the section node once to select it, once more to open it.
    const section = nodeButton(view, /^Sample, Section/);
    fireEvent.pointerDown(section);
    fireEvent.pointerDown(section);

    await waitFor(() =>
      expect(view.getByRole('button', { name: /^Formula, Field/ })).toBeInTheDocument(),
    );
  });

  it('every connection in the detail pane carries a WHY sentence', async () => {
    const view = await openGraph();
    fireEvent.pointerDown(nodeButton(view, /^Sample, Section/));
    const detail = view.getByLabelText('Selected node');
    await waitFor(() =>
      expect(within(detail).getByRole('heading', { name: 'Sample' })).toBeInTheDocument(),
    );
    expect(
      within(detail).getByText(/Defined by schema field sample\.material\.formula/),
    ).toBeInTheDocument();
    expect(within(detail).getByText(/one of the stable draft sections/)).toBeInTheDocument();
  });

  it('names the evidence source, the file and the locator — never a bare code', async () => {
    const view = await openGraph();
    fireEvent.change(view.getByLabelText('Search within this experiment'), {
      target: { value: 'system.technique' },
    });
    fireEvent.click(await view.findByRole('option', { name: /Technique/ }));

    const detail = view.getByLabelText('Selected node');
    await waitFor(() =>
      expect(
        within(detail).getByText(
          /Supported by evidence read from the campaign spreadsheet from mock_campaign\.csv/,
        ),
      ).toBeInTheDocument(),
    );
  });

  it('states that no links are declared instead of drawing one', async () => {
    const view = await openGraph();
    expect(view.getByText(/This record declares no links/)).toBeInTheDocument();
    expect(
      view.getByText(/a shared formula, sample id, beamline or proposal is not a relationship/),
    ).toBeInTheDocument();
  });

  it('draws a DECLARED link with its relationship and its basis', async () => {
    const view = await openGraph(exportedExperimentGraphBundle());
    expect(view.queryByText(/This record declares no links/)).toBeNull();
    const linked = nodeButton(view, /^01SYNTHGRAPHLINKED\d+, Linked Record/);
    fireEvent.pointerDown(linked);
    const detail = view.getByLabelText('Selected node');
    await waitFor(() =>
      expect(within(detail).getByText('same_sample_as')).toBeInTheDocument(),
    );
    expect(within(detail).getByText('shared_material_batch')).toBeInTheDocument();
  });

  it('renders a STALE exported artifact as stale rather than as current', async () => {
    const view = await openGraph(exportedExperimentGraphBundle('stale'));
    expect(view.getByText(/The exported artifact is STALE/)).toBeInTheDocument();
    const detail = view.getByLabelText('Selected node');
    expect(within(detail).getByText(/does not describe the current draft/)).toBeInTheDocument();
  });

  it('offers a jump from a node to the real editor location', async () => {
    const view = await openGraph();
    const detail = view.getByLabelText('Selected node');
    fireEvent.click(within(detail).getByRole('button', { name: 'Open This Record' }));
    await waitFor(() =>
      expect(view.getByTestId('href').textContent).toBe(`/record/${GRAPH_EXP_ID}`),
    );
  });
});

describe('search within this experiment', () => {
  it('finds a node and reveals it', async () => {
    const view = await openGraph();
    fireEvent.change(view.getByLabelText('Search within this experiment'), {
      target: { value: 'mock_campaign' },
    });
    const options = await view.findAllByRole('option');
    const option = options.find(
      (o) => o.querySelector('.expgraph-result-kind')?.textContent === 'Source File',
    );
    expect(option).toBeDefined();
    fireEvent.click(option!);
    const detail = view.getByLabelText('Selected node');
    await waitFor(() =>
      expect(
        within(detail).getByRole('heading', { name: 'mock_campaign.csv' }),
      ).toBeInTheDocument(),
    );
  });

  it('refuses a near match rather than offering one', async () => {
    const view = await openGraph();
    fireEvent.change(view.getByLabelText('Search within this experiment'), {
      target: { value: 'mock_campain' },
    });
    expect(await view.findByText(/No near match is offered/)).toBeInTheDocument();
  });
});

describe('view controls', () => {
  it('fit, reset, zoom and category visibility are all present and operable', async () => {
    const view = await openGraph();
    for (const name of ['Zoom In', 'Zoom Out', 'Fit View', 'Reset View']) {
      fireEvent.click(view.getByRole('button', { name }));
    }
    const chip = view.getByRole('button', { name: /^Section/ });
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(chip);
    await waitFor(() => expect(chip).toHaveAttribute('aria-pressed', 'false'));
    // The anchor survives every filter — a reader cannot hide the subject.
    expect(nodeButton(view, /graph fixture, Experiment/)).toBeInTheDocument();
  });

  it('reset returns to the anchor neighbourhood after an expansion', async () => {
    const view = await openGraph();
    const section = nodeButton(view, /^Sample, Section/);
    fireEvent.pointerDown(section);
    fireEvent.pointerDown(section);
    await waitFor(() =>
      expect(view.getByRole('button', { name: /^Formula, Field/ })).toBeInTheDocument(),
    );
    fireEvent.click(view.getByRole('button', { name: 'Reset View' }));
    await waitFor(() => expect(view.queryByRole('button', { name: /^Formula, Field/ })).toBeNull());
  });
});

describe('tutorial isolation, at the surface', () => {
  it('refuses to render a graph read in a worked-example session in the ordinary workspace', () => {
    const view = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ExperimentGraphPanel
          bundle={experimentGraphBundle()}
          readInScope="fixtureSessionId0000000"
          currentScope={null}
        />
      </MemoryRouter>,
    );
    expect(view.getByText(/read in a different workspace/)).toBeInTheDocument();
    // Nothing from the session's record reaches the DOM.
    expect(view.queryByText(/graph fixture/)).toBeNull();
    expect(view.queryByTestId('expgraph-counts')).toBeNull();
  });

  it('renders normally when the scope has not changed', () => {
    const view = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ExperimentGraphPanel
          bundle={experimentGraphBundle()}
          readInScope="fixtureSessionId0000000"
          currentScope="fixtureSessionId0000000"
        />
      </MemoryRouter>,
    );
    expect(view.getByTestId('expgraph-counts')).toBeInTheDocument();
  });
});

describe('a large but plausible experiment stays usable', () => {
  it('renders a bounded view and says so, without freezing', async () => {
    const started = performance.now();
    const view = await openGraph(stressExperimentGraphBundle());
    const ms = performance.now() - started;
    const counts = view.getByTestId('expgraph-counts').textContent ?? '';
    const [, drawn, total] = /(\d+) of (\d+) nodes drawn/.exec(counts) ?? [];
    expect(Number(drawn)).toBeLessThanOrEqual(240);
    expect(Number(total)).toBeGreaterThan(Number(drawn));
    expect(ms).toBeLessThan(12000);
  });
});

describe('accessibility', () => {
  async function structuralViolations(container: HTMLElement): Promise<string[]> {
    const results = await axe.run(container, {
      runOnly: {
        type: 'rule',
        values: [
          'button-name',
          'definition-list',
          'dlitem',
          'list',
          'listitem',
          'aria-required-children',
          'aria-required-parent',
          'aria-valid-attr-value',
          'label',
          'form-field-multiple-labels',
        ],
      },
      resultTypes: ['violations'],
    });
    return results.violations.map((v) => `${v.id} × ${v.nodes.length}`);
  }

  it('the scanner is proven on a defect — an unnamed control fails it', async () => {
    const { container } = render(
      <div>
        <button type="button" />
      </div>,
    );
    expect(await structuralViolations(container)).toEqual(['button-name × 1']);
  });

  it('reports no structural violation with the graph on screen', async () => {
    const view = await openGraph(exportedExperimentGraphBundle());
    expect(await structuralViolations(view.container)).toEqual([]);
  });

  it('every drawn node is a named, keyboard-reachable control', async () => {
    const view = await openGraph();
    const nodes = view.container.querySelectorAll('.expgraph-node');
    expect(nodes.length).toBeGreaterThan(1);
    let roving = 0;
    nodes.forEach((n) => {
      expect(n.getAttribute('aria-label')).toBeTruthy();
      if (n.getAttribute('tabindex') === '0') roving += 1;
    });
    // ONE tab stop for the whole canvas (roving tabindex), not one per node.
    expect(roving).toBe(1);
  });

  it('arrow keys move between nodes and Enter opens one', async () => {
    const view = await openGraph();
    const anchor = nodeButton(view, /graph fixture, Experiment/);
    fireEvent.keyDown(anchor, { key: 'ArrowRight' });
    await waitFor(() =>
      expect(view.container.querySelectorAll('.expgraph-node.selected').length).toBe(1),
    );
    const selected = view.container.querySelector('.expgraph-node.selected') as Element;
    const before = view.container.querySelectorAll('.expgraph-node').length;
    fireEvent.keyDown(selected, { key: 'Enter' });
    await waitFor(() =>
      expect(view.container.querySelectorAll('.expgraph-node').length).toBeGreaterThanOrEqual(
        before,
      ),
    );
  });
});

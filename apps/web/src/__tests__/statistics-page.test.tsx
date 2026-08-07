import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AppRoutes } from '../App';
import { SchemaBrowser } from '../components/SchemaBrowser';
import { ProjectMemory } from '../screens/ProjectMemory';
import { StatisticsPage } from '../screens/statistics/StatisticsPage';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { TUTORIAL_SESSION_HEADER } from '../lib/api';
import {
  __resetTutorialStore,
  dismissTutorial,
  getTutorialState,
  startTutorial,
} from '../lib/tutorialController';
import {
  STATISTICS_ROUTE_KEYS,
  TUTORIAL_SESSION_ID,
  aboutResponse,
  graphStatusAvailable,
  graphStatusPreRegen,
  graphStatusUnavailable,
  healthSynthetic,
  memoryConceptsAvailable,
  memoryFilesAvailable,
  openApiFixture,
  resetDemoRoutes,
  schemaBrowserFixture,
  statisticsRecordsBody,
  statisticsRoutes,
  statisticsRuntimeRecords,
  stubFetchDown,
  stubFetchRoutes,
  tutorialSessionRoutes,
  type RouteEntry,
} from '../test/apiFixtures';

/**
 * The RENDERED Statistics dashboard.
 *
 * `lib/statisticsModel.ts` already has its own suite, and this file deliberately
 * does not re-test those pure functions. What it pins is everything that lives
 * between them and the reader: which number reaches which labelled slot, what
 * the page says when a figure is absent, what it must never say at all, the six
 * independent fetch states, and the fact that Refresh is five GETs and nothing
 * more.
 *
 * Three deliberate choices about HOW this file asserts:
 *
 *  1. EVERY element is resolved by role or by its own visible label — never by
 *     array index or DOM position. Each of the six regions is a `<section
 *     aria-labelledby>`, i.e. a named `region` landmark, so `regionOf('Project
 *     Memory')` scopes a lookup to one section without depending on section
 *     order; a figure is then found from the text of its own `<dt>`. The one
 *     place an ordered read is used is where ORDER IS THE ASSERTION (canonical
 *     workflow order, evidence severity precedence), and there the whole list is
 *     read once and compared as a list — the form that cannot pass for a
 *     different order.
 *
 *  2. Expected figures are TRANSCRIBED LITERALS, not recomputed from the model.
 *     Recomputing with `deriveWorkspaceTotals` et al. would make every
 *     assertion here tautological: the page would agree with the model even if
 *     both were wrong, and a swap of two labels would still pass. The literals
 *     below are derived by hand from the fixture and stated once, at the top.
 *
 *  3. The truthfulness guards scan the rendered text of a SUCCESSFUL page.
 *     Failure states legitimately render `API Base` (which is
 *     `http://127.0.0.1:8000/api` in a local build) and a request path, so
 *     scanning them for an IP-shaped string would fail on the honest
 *     diagnostics box rather than on any invented figure.
 */

// --- what the fixture implies ------------------------------------------------

/*
 * `statisticsRuntimeRecords` = the four `runtimeRecords` rows + one more
 * needs-attention row (see its fixture comment). Every literal below is derived
 * from those five rows by hand:
 *
 *   status:      2 needs_attention · 1 ready_to_export · 1 in_review · 1 done
 *   current_step: complete_metadata, review_evidence, review_export_readiness,
 *                 export, null(all complete) — one each, load_record EMPTY
 *   evidence:    supported 3+9+5+9+4 = 30 · inferred 1+0+0+0+2 = 3 ·
 *                insufficient 0+0+1+0+1 = 2 · conflicting 0+0+2+0+0 = 2 ·
 *                unknown 2+0+0+0+1 = 3 · total 40 fields over 5 records
 *   gate:        exported 1 · ready 1 · in_review 1 · needs_attention 2 ·
 *                stale artifacts 1 (the exported row's artifact_state)
 */
const RECORD_COUNT = 5;

/** The workflow axis, in canonical order, with the zero bucket included. */
const WORKFLOW_BARS: [string, string][] = [
  ['Load Record', '0'],
  ['Complete Metadata', '1'],
  ['Review Evidence', '1'],
  ['Review Export Readiness', '1'],
  ['Export', '1'],
  ['All Steps Complete', '1'],
];

/** The five evidence classes in SEVERITY precedence (not by count). */
const EVIDENCE_CHIPS: [string, string][] = [
  ['Supported', '30'],
  ['Inferred Candidate', '3'],
  ['Insufficient Evidence', '2'],
  ['Conflicting Evidence', '2'],
  ['Unknown', '3'],
];

/* `openApiFixture` documents 7 operations across 6 groups: 4 GET
   (health, about, experiments/{id}, search) and 3 POST (answers, uploads,
   validate/record). Groups: Health & Meta, Experiments, Drafts & Answers,
   Uploads, Validation, Other Operations. */
const OPERATION_COUNT = '7';
const GROUP_COUNT = '6';
const METHOD_BARS: [string, string][] = [
  ['GET', '4'],
  ['POST', '3'],
];

/** The literal the page uses wherever a figure genuinely was not returned. */
const UNAVAILABLE = 'Not Available';

// --- harness ------------------------------------------------------------------

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderStatistics(routes: Record<string, RouteEntry>) {
  const calls = stubFetchRoutes(routes);
  const view = render(
    <MemoryRouter
      initialEntries={[ROUTES.statistics]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
  return { ...view, calls };
}

/**
 * Wait until no section is loading any more. Works for success AND failure
 * rounds, because `LoadingPanel` is the only `role="status"` fetch state
 * (`BackendDown` is `role="alert"`), so this settles a round without the caller
 * having to know which of the five sources answered.
 */
async function settled(): Promise<void> {
  await waitFor(() =>
    expect(document.querySelectorAll('.fetch-state[role="status"]')).toHaveLength(0),
  );
}

/** One of the six regions, by its own heading text. */
const regionOf = (name: string): HTMLElement => screen.getByRole('region', { name });

/** A `StatCard`'s displayed value, resolved by the card's own visible label. */
function cardValue(region: string, label: string): string {
  const card = within(regionOf(region)).getByText(label).closest('dl.stat-card');
  expect(card, `no stat card labelled "${label}" in ${region}`).not.toBeNull();
  return card!.querySelector('.stat-card-value')?.textContent?.trim() ?? '';
}

/** A `FigureList` row's displayed value, resolved by the row's own visible label. */
function figureValue(region: string, label: string): string {
  const row = within(regionOf(region)).getByText(label).closest('.stats-figure');
  expect(row, `no figure row labelled "${label}" in ${region}`).not.toBeNull();
  return row!.querySelector('dd')?.textContent?.trim() ?? '';
}

/** Every figure row in a region, as label → displayed value. */
function figuresIn(region: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const row of regionOf(region).querySelectorAll('.stats-figure')) {
    out[row.querySelector('dt')?.textContent?.trim() ?? ''] =
      row.querySelector('dd')?.textContent?.trim() ?? '';
  }
  return out;
}

/** One chart `<figure>`, resolved by its own visible caption. */
function chartFigure(region: string, caption: string): HTMLElement {
  const figure = within(regionOf(region))
    .getByText(caption, { selector: 'figcaption' })
    .closest('figure');
  expect(figure, `no chart figure captioned "${caption}" in ${region}`).not.toBeNull();
  return figure as HTMLElement;
}

/**
 * The [label, count] pairs of one ROW-BASED chart, read from its VISIBLE spans
 * (never from an aria attribute), in DOM order — order is the assertion here.
 *
 * Covers `StatsBarChart` (`.stats-chart-row`) and `StatsComparisonRows`
 * (`.stats-chart-comparerow`); both render the category name and the value as
 * real HTML text beside the mark, which is what makes those charts readable with
 * every fill removed.
 */
function chartRows(region: string, caption: string): [string, string][] {
  const figure = chartFigure(region, caption);
  return [...figure.querySelectorAll('.stats-chart-row, .stats-chart-comparerow')].map((row) => [
    row.querySelector('.stats-chart-row-label')?.textContent?.trim() ?? '',
    row.querySelector('.stats-chart-row-value')?.textContent?.trim() ?? '',
  ]);
}

/**
 * The [row header, first data cell] pairs of a chart's DATA TABLE, in DOM order.
 *
 * The form-independent reader, and the only one that works for the column chart
 * — whose category names sit under the marks and whose values are deliberately
 * NOT all direct-labelled (only the sole maximum is). Using it is also a real
 * assertion about the table alternative rather than an assertion about the
 * picture, which is the point of the table existing.
 */
function chartTableRows(region: string, caption: string): [string, string][] {
  const figure = chartFigure(region, caption);
  const table = figure.querySelector('table.stats-chart-table');
  expect(table, `no data table in the chart captioned "${caption}"`).not.toBeNull();
  return [...table!.querySelectorAll('tbody tr')].map((row) => [
    row.querySelector('th')?.textContent?.trim() ?? '',
    row.querySelector('td')?.textContent?.trim() ?? '',
  ]);
}

/** The screen-reader summary sentence a chart figure carries. */
function chartSummaryText(region: string, caption: string): string {
  return chartFigure(region, caption).querySelector('.sr-only')?.textContent?.trim() ?? '';
}

/** The chip + count pairs of a `MiniBreakdown`, in DOM order. */
function chipRows(region: string): [string, string][] {
  return [...regionOf(region).querySelectorAll('.stats-mini-item')].map((item) => [
    item.querySelector('.chip span')?.textContent?.trim() ?? '',
    item.querySelector('.stats-mini-n')?.textContent?.trim() ?? '',
  ]);
}

/**
 * The rendered text of a subtree, with every text NODE separated by a space.
 *
 * Deliberately not `textContent`: that concatenates adjacent elements with no
 * separator, so `…Reading From the API` + `Refresh` becomes `…the APIRefresh`
 * and a `\b`-anchored guard below silently stops matching. A telemetry label
 * rendered flush against its value (`Uptime` + `4 days` → `Uptime4 days`) would
 * have slipped through the forbidden-term scan for exactly that reason — the
 * mutation check that caught it is kept as `finds a word that IS on the page`.
 */
function textOf(root: HTMLElement): string {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  while (walker.nextNode()) parts.push(walker.currentNode.textContent ?? '');
  return parts.join(' ').replace(/\s+/g, ' ').trim();
}

/** The whole rendered page as one normalised string. */
const pageText = (container: HTMLElement): string => textOf(container);

/** The meta row's single `<time>` — the page's one displayed read timestamp. */
function metaTime(container: HTMLElement): HTMLTimeElement {
  const node = container.querySelector('.stats-meta-read time');
  expect(node, 'the meta row must render a <time>').not.toBeNull();
  return node as HTMLTimeElement;
}

/** The meta row's label — which of the three read states the page is claiming. */
function metaLabel(container: HTMLElement): string {
  return container.querySelector('.stats-meta-label')?.textContent?.trim() ?? '';
}

/**
 * A route that answers its FIRST call with `body` and every later call with a
 * dead backend.
 *
 * That is the routine hosted case the honesty of the read clock turns on: the
 * page loaded, then the backend became unreachable before Refresh was pressed.
 * `stubFetchRoutes` invokes a function route entry once per fetch, and a throw
 * inside it rejects that one `fetch` exactly as a network failure does — so the
 * other routes are untouched and each failure is per-call, not per-route.
 */
function firstCallOnly(body: unknown): RouteEntry {
  let calls = 0;
  return () => {
    calls += 1;
    if (calls > 1) throw new TypeError('connect ECONNREFUSED 127.0.0.1:8000');
    return { body };
  };
}

/** The rendered page with the matching elements removed first. */
function pageTextWithout(container: HTMLElement, selector: string): string {
  const clone = container.cloneNode(true) as HTMLElement;
  for (const node of clone.querySelectorAll(selector)) node.remove();
  return textOf(clone);
}

const NO_ANALYTICS_SECTION = 'section[aria-labelledby="stats-no-analytics"]';
/** That section's heading — the accessible name `regionOf` resolves it by. */
const NO_ANALYTICS_HEADING = 'This Application Collects No Analytics';

/*
 * THE LEAD SENTENCE NAMES A WORKSPACE, so it names a scope after what is in it, and
 * is pinned in BOTH scopes.
 *
 * It used to read "the current example workspace" unconditionally. The five
 * built-in example records are created only inside a worked-example session, and the
 * ordinary workspace is never auto-seeded, so on every ordinary screen that sentence
 * named this scope after content this build never puts there — the same defect the
 * mode chip was corrected for, and `mode-chip.test.tsx` pins that correction the
 * same way.
 *
 * PHRASED AS WHAT THE BUILD DOES. This comment used to conclude "that sentence
 * asserted contents that are not there", which is itself a claim about CONTENTS and
 * is not measured anywhere: there is no startup migration, so a workspace that
 * already held the five still lists them.
 *
 * Asserted on three axes per scope, because a single-scope test cannot catch the
 * defect: what the sentence says, what it must NOT say, and (for the ordinary
 * scope) that the retired phrase is gone from the whole page rather than moved.
 */
describe('the lead sentence is truthful in each workspace scope', () => {
  /**
   * A held scope always means a running walkthrough — `startTutorial` and
   * `resumeTutorialSession` are the only things that set `sessionId`, and both set
   * `phase: 'running'`. So the session case does not manufacture a scope: it starts
   * the walkthrough, mounts on the surface step one lives on, and then walks to
   * Statistics the way a reader does. The overlay navigates ONCE PER STEP, so that
   * navigation sticks (see `workspace-scope-invalidation.test.tsx` · D2).
   */
  async function renderIn(scope: 'ordinary' | 'session') {
    const routes = {
      ...statisticsRoutes(),
      ...tutorialSessionRoutes(),
      // Chrome the shell mounts in a session: the mode chip reads health, and the
      // overlay resolves its target records from the experiment list.
      'GET /api/health': { body: healthSynthetic },
      'GET /api/experiments': { body: { experiments: [] } },
    } as Record<string, RouteEntry>;
    if (scope === 'ordinary') {
      const view = renderStatistics(routes);
      await settled();
      return view;
    }
    stubFetchRoutes(routes);
    await act(async () => {
      await startTutorial(null);
    });
    expect(getTutorialState().sessionId).not.toBeNull();
    let view!: ReturnType<typeof render>;
    await act(async () => {
      view = render(
        <MemoryRouter
          initialEntries={[ROUTES.experiments]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <AppRoutes />
        </MemoryRouter>,
      );
    });
    const toStatistics = await screen.findByRole('link', { name: LABELS.navStatistics });
    await act(async () => {
      fireEvent.click(toStatistics);
    });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Statistics' }),
    ).toBeInTheDocument();
    await settled();
    return view;
  }

  afterEach(() => {
    __resetTutorialStore();
    sessionStorage.clear();
  });

  it('ordinary scope: names the workspace without claiming it holds examples', async () => {
    const { container } = await renderIn('ordinary');

    expect(
      screen.getByText(
        'A read-only view of this workspace, workflow readiness, open questions, evidence, ' +
          'the official record schema, Project Memory, and the API surface — and, for ' +
          'platform-wide figures, why none is stated.',
      ),
    ).toBeInTheDocument();
    // The retired claim is gone from the PAGE, not relocated within it.
    expect(pageText(container)).not.toContain('example workspace');
    expect(pageText(container)).not.toMatch(/read-only view of the current/i);
  });

  it('worked-example scope: names the scope that really does hold the examples', async () => {
    await renderIn('session');

    expect(
      screen.getByText(
        'A read-only view of the open worked-example workspace, workflow readiness, open questions, ' +
          'evidence, the official record schema, Project Memory, and the API surface — and, for ' +
          'platform-wide figures, why none is stated.',
      ),
    ).toBeInTheDocument();
    // The neutral ordinary wording must not leak into the scope that has examples.
    expect(screen.queryByText(/A read-only view of this workspace/)).toBeNull();
  });
});

/*
 * WHICH WORKSPACE THE RECORD READ ADDRESSES — asserted as REQUESTS, because no
 * assertion about rendered copy can see it.
 *
 * WHY THIS BLOCK EXISTS, stated plainly because it is a review finding rather than a
 * new feature. `StatisticsPage` keys `GET /api/runtime/records` on the workspace
 * scope, and its own comment says what an empty dependency list cost: "opening or
 * leaving a session left every record-derived figure on it describing a workspace
 * that was no longer being addressed". That key had ZERO coverage. Reverting
 * `[scope]` to `[]` reinstated the defect verbatim and the whole frontend suite —
 * including the two lead-sentence tests directly above, which render in both scopes
 * and so read as if they cover this — still passed. A page whose numbers are its
 * entire purpose was one character away from silently describing the wrong workspace.
 *
 * SO THESE TESTS ASSERT THE READ, NOT THE COPY. The lead sentence is derived from
 * `useWorkspaceScope()` directly and would keep telling the truth about the scope
 * while every FIGURE beneath it described the other one — which is precisely the
 * shape of defect that made the gap invisible.
 *
 * TWO PROPERTIES, and the second is the one that makes this falsifiable:
 *   1. a read is ISSUED on entering a session and again on leaving; and
 *   2. each read carries the RIGHT SCOPE — the session header when one is held,
 *      none when it is not. A test that only counted requests would pass on a page
 *      that refetched the ordinary workspace three times.
 *
 * THE SURFACE IS MOUNTED UNDER A CATCH-ALL ROUTE ON PURPOSE. The walkthrough
 * navigates once per step when it starts, so mounting this page through `AppRoutes`
 * would unmount it at the exact moment the scope changed, and the test would prove
 * nothing about the dependency. A catch-all keeps ONE mounted `StatisticsPage`
 * across that navigation, so what is measured is the scope change and not a route
 * change. Everything else is the real thing: the real store API opens and discards
 * the session, and the page's own `useFetch` issues the reads.
 */
describe('the record read follows the workspace scope', () => {
  const RECORDS_READ = 'GET /api/runtime/records';

  const countReads = (calls: string[]) => calls.filter((k) => k === RECORDS_READ).length;

  /**
   * The session header on every `/api/runtime/records` read, in order —
   * `undefined` for a read that carried none (the ordinary workspace).
   *
   * Read from the `fetch` mock rather than from `stubFetchRoutes`'s key list,
   * because the key records method+path only and the SCOPE lives in a header.
   */
  function recordReadScopes(): (string | undefined)[] {
    const mock = (globalThis.fetch as unknown as { mock: { calls: [unknown, RequestInit?][] } })
      .mock;
    return mock.calls
      .filter(([input]) => String(input).endsWith('/api/runtime/records'))
      .map(
        ([, init]) =>
          (init?.headers as Record<string, string> | undefined)?.[TUTORIAL_SESSION_HEADER],
      );
  }

  async function renderSurface(routes: Record<string, RouteEntry>) {
    const calls = stubFetchRoutes(routes);
    let view!: ReturnType<typeof render>;
    // Wrapped because the five reads resolve during mount: without it React warns
    // about the settle-time `setState` in the page's own round tracker.
    await act(async () => {
      view = render(
        <MemoryRouter
          initialEntries={[ROUTES.statistics]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route path="*" element={<StatisticsPage />} />
          </Routes>
        </MemoryRouter>,
      );
    });
    return { ...view, calls };
  }

  afterEach(() => {
    __resetTutorialStore();
    sessionStorage.clear();
    localStorage.clear();
  });

  it('re-reads the records when a session is entered, and again when it is left', async () => {
    const { calls } = await renderSurface({
      ...statisticsRoutes(),
      ...tutorialSessionRoutes(),
      'GET /api/health': { body: healthSynthetic },
      'GET /api/experiments': { body: { experiments: [] } },
    });
    await settled();
    expect(countReads(calls)).toBe(1);

    await act(async () => {
      await startTutorial(null);
    });
    expect(getTutorialState().sessionId).toBe(TUTORIAL_SESSION_ID);
    await waitFor(() => expect(countReads(calls)).toBe(2));

    await act(async () => {
      await dismissTutorial('skip');
    });
    expect(getTutorialState().sessionId).toBeNull();
    await waitFor(() => expect(countReads(calls)).toBe(3));

    // The three reads addressed the ordinary workspace, then the session, then the
    // ordinary workspace again. This is the assertion an unkeyed fetch cannot pass,
    // and it is also the one a fetch keyed on the wrong thing cannot pass.
    expect(recordReadScopes()).toEqual([undefined, TUTORIAL_SESSION_ID, undefined]);
  });

  /*
   * A RESET does not change the scope — same session, different records — so the
   * scope key above cannot cover it. This is the staleness the review found: the
   * guarded reset lives in the worked-example bar, `AppShell` mounts that bar on
   * every surface INCLUDING this one, and pressing it left every figure here
   * describing the records it had just discarded. The queue subscribed to the
   * rebuild signal; this page did not.
   *
   * Driven through the REAL control — the trigger in the bar on this very screen,
   * the preview, the typed gate, the execute — rather than by calling
   * `notifyWorkspaceRebuilt()` directly, so it also pins that the control is
   * reachable from here at all.
   */
  it('re-reads the records after a reset rebuilds the workspace', async () => {
    const { calls } = await renderSurface({
      ...statisticsRoutes(),
      ...tutorialSessionRoutes(),
      ...resetDemoRoutes().routes,
    });
    await settled();
    await act(async () => {
      await startTutorial(null);
    });
    const trigger = await screen.findByRole('button', { name: LABELS.actionResetDemo });
    expect(trigger.closest('.tutorial-session-bar')).not.toBeNull();
    await act(async () => {
      fireEvent.click(trigger);
    });
    const d = await screen.findByRole('dialog', {
      name: new RegExp(LABELS.resetDialogTitle, 'i'),
    });
    fireEvent.change(within(d).getByRole('textbox'), { target: { value: 'RESET' } });

    /*
     * Measured as an INCREASE captured AFTER the session was entered, so the
     * scope-change read cannot satisfy it — the same strengthening
     * `reset-demo.test.tsx` applies to the queue's refetch, for the same reason.
     */
    const before = countReads(calls);
    await act(async () => {
      fireEvent.click(within(d).getByRole('button', { name: LABELS.resetConfirmAction }));
    });

    await waitFor(() => expect(countReads(calls)).toBeGreaterThan(before));
    // The reset did not leave the session, so the refetch still addressed it.
    const scopes = recordReadScopes();
    expect(scopes[scopes.length - 1]).toBe(TUTORIAL_SESSION_ID);
  });
});

// --- Workspace at a Glance -----------------------------------------------

describe('Workspace at a Glance', () => {
  it('the four record cards state the counts the fixture implies', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(cardValue('Workspace at a Glance', 'Need Attention')).toBe('2');
    expect(cardValue('Workspace at a Glance', 'Ready to Export')).toBe('1');
    expect(cardValue('Workspace at a Glance', 'Exported')).toBe('1');

    // Every row's status is one of the four, so the surfaced-unknown card must
    // NOT appear — it is emitted only when a record carries an unplaceable status.
    expect(
      within(regionOf('Workspace at a Glance')).queryByText('Unrecognized Status'),
    ).toBeNull();
    // …and nothing claims the page saw fewer records than the API reported.
    expect(screen.queryByText(/This page received/)).toBeNull();
  });

  /*
   * THESE TWO CARDS MOVED, and the assertion moved with them rather than being
   * dropped. They are facts about the BUILD, not about the workspace, and they
   * sat in Workspace at a Glance only because they arrived in the same round of
   * reads; they now live in the `Runtime` region inside Technical Details. What is
   * pinned is unchanged: the value comes from `/api/about` and only its
   * capitalisation changes.
   */
  it('Runtime Mode and Persistence render from /api/about, in Title Case', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    // The API sends `synthetic-only` / `ephemeral`; only capitalisation changes.
    expect(aboutResponse.runtime_mode).toBe('synthetic-only');
    expect(aboutResponse.persistence).toBe('ephemeral');
    expect(cardValue('Runtime', 'Runtime Mode')).toBe('Synthetic-Only');
    expect(cardValue('Runtime', 'Persistence')).toBe('Ephemeral');

    // …and they are NOT still in the glance row, so the move is real rather than
    // a copy: the glance section reads exactly one endpoint now.
    const glance = regionOf('Workspace at a Glance');
    expect(within(glance).queryByText('Runtime Mode')).toBeNull();
    expect(within(glance).queryByText('Persistence')).toBeNull();
  });

  /*
   * A MALFORMED /api/about must not take the whole app down.
   *
   * There is no ErrorBoundary anywhere in this app (`main.tsx` renders `<App/>`
   * bare), so a throw during render blanks the entire SPA — not just the card
   * that threw. The two runtime cards Title-Case their value, and that ran
   * `.replace()` straight on `about.data.runtime_mode` / `persistence`: a body
   * where either is `null` (or a number, which JSON permits and the TypeScript
   * type does not model) threw a TypeError mid-render. `runtime_mode: null` here
   * with a NUMERIC `persistence` covers both shapes in one render.
   */
  it('a malformed /api/about degrades its two cards instead of blanking the app', async () => {
    const { container } = renderStatistics(
      statisticsRoutes({
        about: { body: { ...aboutResponse, runtime_mode: null, persistence: 7 } },
      }),
    );
    await settled();

    // The page is still there: its heading, all six regions, and the figures that
    // came from the OTHER three reads.
    expect(screen.getByRole('heading', { level: 1, name: 'Statistics' })).toBeInTheDocument();
    for (const region of [
      'Workspace at a Glance',
      'Workflow Distribution',
      'Evidence and Validation',
      NO_ANALYTICS_HEADING,
      'Runtime',
      'Project Memory',
      'API Surface',
    ]) {
      expect(regionOf(region), `${region} must still render`).toBeInTheDocument();
    }
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(figureValue('Project Memory', 'Nodes')).toBe(String(graphStatusAvailable.node_count));
    expect(figureValue('API Surface', 'Documented Operations')).toBe(OPERATION_COUNT);

    // Neither malformed fact is stated, and neither is replaced by a plausible
    // default — "Synthetic-Only" would be a guess, and this app must not guess.
    expect(cardValue('Runtime', 'Runtime Mode')).toBe(UNAVAILABLE);
    expect(cardValue('Runtime', 'Persistence')).toBe(UNAVAILABLE);
    expect(pageText(container)).not.toMatch(/Synthetic-Only|Ephemeral/);

    // Absence, not failure: the neutral not-available tone, and no alarm.
    const runtime = regionOf('Runtime');
    for (const label of ['Runtime Mode', 'Persistence']) {
      const card = within(runtime).getByText(label).closest('dl.stat-card');
      expect(card?.getAttribute('data-tone')).toBe('quiet');
    }
    expect(within(runtime).queryByRole('alert')).toBeNull();
  });
});

// --- Workflow Distribution ------------------------------------------------

describe('Workflow Distribution', () => {
  it('renders every canonical bucket with its count as real text, zeros included, in canonical order', async () => {
    const { container } = renderStatistics(statisticsRoutes());
    await settled();

    // ONE ordered read of the visible spans. `Load Record` is at zero in this
    // fixture and must still draw its row: a distribution that silently omits
    // an empty bucket reshapes its own axis as records move.
    const caption = `Records by current workflow step, out of ${RECORD_COUNT} counted`;
    expect(chartRows('Workflow Distribution', caption)).toEqual(WORKFLOW_BARS);

    // The counts are VISIBLE, not only spoken: strip every aria-hidden subtree —
    // which is the whole drawn SVG — and the labels and numbers are still there.
    const visible = pageTextWithout(container, '[aria-hidden="true"]');
    for (const [label, count] of WORKFLOW_BARS) {
      expect(visible).toContain(label);
      expect(new RegExp(`${label}\\s*${count}`).test(visible)).toBe(true);
    }

    /*
     * TWO TEXT EQUIVALENTS, not one, and they are asserted separately because
     * they do different jobs. The summary sentence is a real `<p>` present on
     * every render — never an `aria-label`, and never inside the collapsed
     * disclosure — so a screen reader gets the whole distribution without walking
     * a grid. The data table then carries every figure for everyone.
     */
    const summary = chartSummaryText('Workflow Distribution', caption);
    for (const [label, count] of WORKFLOW_BARS) {
      expect(summary).toContain(`${label}: ${count}`);
    }
    expect(summary).toContain(`Total ${RECORD_COUNT} records.`);
    expect(chartTableRows('Workflow Distribution', caption)).toEqual(WORKFLOW_BARS);

    // The picture itself claims nothing: the SVG is hidden from assistive
    // technology, so it cannot state a figure the text equivalents do not.
    const svg = chartFigure('Workflow Distribution', caption).querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
  });
});

// --- Evidence and Validation ---------------------------------------------

describe('Evidence and Validation', () => {
  it('renders the five evidence classes in severity precedence, NOT sorted by count', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(chipRows('Evidence and Validation')).toEqual(EVIDENCE_CHIPS);

    // The discriminator: this fixture's counts (30,3,2,2,3) are NOT in
    // descending order, so a page that re-sorted by count would read
    // 30,3,3,2,2 and fail the list comparison above. Stated explicitly so the
    // property is not an accident of the numbers.
    const counts = EVIDENCE_CHIPS.map(([, n]) => Number(n));
    expect([...counts].sort((a, b) => b - a)).not.toEqual(counts);
  });

  it('labels every evidence count in FIELDS, never in records', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    const region = regionOf('Evidence and Validation');

    expect(within(region).getByText('Fields by Evidence-Support Class')).toBeInTheDocument();
    // Each chip's count carries its unit for a screen reader, so the badge is
    // never a bare number.
    const nouns = [...region.querySelectorAll('.stats-mini-item .sr-only')].map((n) =>
      n.textContent?.trim(),
    );
    expect(nouns).toHaveLength(EVIDENCE_CHIPS.length);
    for (const noun of nouns) expect(['field', 'fields']).toContain(noun);

    expect(figureValue('Evidence and Validation', 'Total Fields Counted')).toBe('40');
    expect(figureValue('Evidence and Validation', 'Records Counted')).toBe(String(RECORD_COUNT));
    expect(
      within(region).getByText(/counts FIELDS across the records counted, not records/),
    ).toBeInTheDocument();
  });

  it('renders the export-gate rows', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(figureValue('Evidence and Validation', 'Exported')).toBe('1');
    expect(figureValue('Evidence and Validation', 'Ready Now')).toBe('1');
    expect(figureValue('Evidence and Validation', 'Blocked by the Export Gate')).toBe('1');
    expect(figureValue('Evidence and Validation', 'Blocked by Open Questions')).toBe('2');
    expect(figureValue('Evidence and Validation', 'Stale Artifacts')).toBe('1');
  });

  it('states that evidence support and schema validation are separate signals', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(
      within(regionOf('Evidence and Validation')).getByText(
        'Evidence support and schema validation are separate signals.',
      ),
    ).toBeInTheDocument();
  });
});

// --- Project Memory (inside the collapsed Technical Details region) ----------

describe('Project Memory', () => {
  it('renders the snapshot figures from /api/graph/status', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(figuresIn('Project Memory')).toMatchObject({
      'Served Files (Path Set)': String(graphStatusAvailable.file_count),
      Concepts: String(graphStatusAvailable.concept_count),
      Communities: String(graphStatusAvailable.community_count),
      Nodes: String(graphStatusAvailable.node_count),
      Edges: String(graphStatusAvailable.edge_count),
      // `v1`, not `1` — the same rendering Project Memory gives this field, so a
      // schema version in a column of counts cannot be read as a count.
      'Snapshot Schema Version': `v${graphStatusAvailable.snapshot_schema_version}`,
    });
    expect(screen.getByRole('link', { name: 'Open Project Memory' })).toHaveAttribute(
      'href',
      ROUTES.memory,
    );
  });

  it('labels the served-files figure with its SCOPE, and reads the path set rather than the content manifest', async () => {
    /* The two counts in this response are different sets (CLAUDE.md §17). This
       body is the discriminator: `file_count` is 9 while `served_file_count` is
       null, so a page reading the manifest count would print the unavailable
       literal here. */
    expect(graphStatusPreRegen.file_count).toBe(9);
    expect(graphStatusPreRegen.served_file_count).toBeNull();

    renderStatistics(statisticsRoutes({ graph: { body: graphStatusPreRegen } }));
    await settled();

    expect(figureValue('Project Memory', 'Served Files (Path Set)')).toBe('9');
  });

  it('states a differing source commit as point-in-time, showing BOTH commits', async () => {
    expect(graphStatusAvailable.source_graph_commit).not.toBe(
      graphStatusAvailable.deployed_app_commit,
    );

    renderStatistics(statisticsRoutes());
    await settled();
    const region = regionOf('Project Memory');

    expect(within(region).getByText('Point-in-Time Snapshot')).toBeInTheDocument();
    expect(figureValue('Project Memory', 'Source Graph Commit')).toBe(
      graphStatusAvailable.source_graph_commit,
    );
    expect(figureValue('Project Memory', 'Deployed App Commit')).toBe(
      graphStatusAvailable.deployed_app_commit,
    );
    // Not a currency claim.
    expect(within(region).queryByText('Built From This Commit')).toBeNull();
  });

  it('with no deployed commit, does NOT claim the snapshot is current', async () => {
    expect(graphStatusPreRegen.deployed_app_commit).toBeNull();

    const { container } = renderStatistics(statisticsRoutes({ graph: { body: graphStatusPreRegen } }));
    await settled();
    const region = regionOf('Project Memory');

    expect(
      within(region).getByText(/cannot be determined in this environment/),
    ).toBeInTheDocument();
    expect(within(region).getByText(/not a claim that the snapshot is current/)).toBeInTheDocument();

    // No currency claim anywhere on the page, in any of its wordings.
    expect(within(region).queryByText('Built From This Commit')).toBeNull();
    expect(pageText(container)).not.toMatch(/matches the commit this build reports/);
    // …and no comparison figure is invented for a comparison that never ran.
    expect(figuresIn('Project Memory')['Deployed App Commit']).toBeUndefined();
  });

  it('with no snapshot overview, every figure is the unavailable literal and never 0', async () => {
    const { container } = renderStatistics(
      statisticsRoutes({ graph: { body: graphStatusUnavailable } }),
    );
    await settled();
    const region = regionOf('Project Memory');

    const figures = figuresIn('Project Memory');
    for (const label of [
      'Served Files (Path Set)',
      'Concepts',
      'Communities',
      'Nodes',
      'Edges',
      'Snapshot Schema Version',
    ]) {
      expect(figures[label], `${label} must state absence, not a number`).toBe(UNAVAILABLE);
    }
    // Zero is a FIGURE; absence is not. No value in this region may read as one.
    expect(Object.values(figures)).not.toContain('0');
    expect(within(region).getByText(/served no snapshot overview/)).toBeInTheDocument();
    expect(within(region).getByText(/none is shown as zero/)).toBeInTheDocument();
    // The absence is stated, never dressed as a failure.
    expect(within(region).queryByRole('alert')).toBeNull();
    expect(pageText(container)).not.toMatch(/Memory Offline|Graph Error/);
  });
});

// --- one number, one name, across the two screens that state it ---------------

/*
 * `/api/graph/status` carries TWO similar file counts — `file_count` (the served
 * PATH SET) and `served_file_count` (the served CONTENT MANIFEST, smaller by one)
 * — and CLAUDE.md §17 exists because conflating them is easy. Both screens read
 * `file_count`, but they labelled it differently: "Served Files (Path Set)" here
 * and "Indexed files" on Project Memory. Two names for one number invite a reader
 * to believe they are two metrics, which on THIS endpoint is a live confusion
 * rather than a hypothetical one.
 *
 * Rendered on both screens from the SAME response, so the guard is a comparison
 * and not two transcriptions that could drift apart independently.
 */
describe('the served-file count is stated under ONE name on both screens', () => {
  const SERVED_LABEL = 'Served Files (Path Set)';

  /** The label → value map of a `.memory-figures` / `.stats-figures` list. */
  function figureMap(root: HTMLElement, rowSelector: string): Record<string, string> {
    const out: Record<string, string> = {};
    for (const row of root.querySelectorAll(rowSelector)) {
      out[row.querySelector('dt')?.textContent?.trim() ?? ''] =
        row.querySelector('dd')?.textContent?.trim() ?? '';
    }
    return out;
  }

  it('Project Memory and Statistics use the same label and the same value for file_count', async () => {
    // --- Statistics
    const stats = renderStatistics(statisticsRoutes());
    await settled();
    expect(figureValue('Project Memory', SERVED_LABEL)).toBe(String(graphStatusAvailable.file_count));
    const statsFigures = figureMap(regionOf('Project Memory'), '.stats-figure');
    stats.unmount();
    vi.unstubAllGlobals();

    // --- Project Memory, from the SAME graph/status body
    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusAvailable },
      'GET /api/memory/files': { body: memoryFilesAvailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
    });
    const memory = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ProjectMemory />
      </MemoryRouter>,
    );
    await memory.findByText('Memory Available');
    const memoryFigures = figureMap(memory.container, '.memory-figure');

    // The one name, and the one number, on both screens.
    expect(memoryFigures[SERVED_LABEL]).toBe(String(graphStatusAvailable.file_count));
    expect(memoryFigures[SERVED_LABEL]).toBe(statsFigures[SERVED_LABEL]);
    // The superseded name is gone — a second name for this number is the defect.
    expect(memory.container.textContent).not.toMatch(/Indexed files/);
    expect(Object.keys(memoryFigures)).not.toContain('Indexed files');

    // Same treatment for the snapshot schema version: one label, one rendering.
    expect(memoryFigures['Snapshot Schema Version']).toBe(
      `v${graphStatusAvailable.snapshot_schema_version}`,
    );
    expect(memoryFigures['Snapshot Schema Version']).toBe(statsFigures['Snapshot Schema Version']);

    /* The one DELIBERATE difference that remains: Project Memory abbreviates the
       source commit to 7 chars while Statistics states it in full. Kept, because
       each is labelled for the form it shows — the short one says so — so neither
       can be read as the other. */
    expect(memoryFigures['Source Graph Commit (Short)']).toBe(
      graphStatusAvailable.source_graph_commit.slice(0, 7),
    );
    expect(statsFigures['Source Graph Commit']).toBe(graphStatusAvailable.source_graph_commit);
    expect(Object.keys(memoryFigures)).not.toContain('Source Graph Commit');
  });

  /*
   * The discriminator the shared name needs. In `graphStatusAvailable` both
   * counts are 190, so a screen that switched to `served_file_count` would still
   * agree with the other. `graphStatusPreRegen` sets them apart — `file_count` is
   * 9 while `served_file_count` is null — so this pins that the row Project
   * Memory now labels with the PATH-SET scope really does read the path set.
   * (The same body is asserted against Statistics further up.)
   */
  it('Project Memory’s scope-labelled row reads the path set, not the content manifest', async () => {
    expect(graphStatusPreRegen.file_count).toBe(9);
    expect(graphStatusPreRegen.served_file_count).toBeNull();

    stubFetchRoutes({
      'GET /api/graph/status': { body: graphStatusPreRegen },
      'GET /api/memory/files': { body: memoryFilesAvailable },
      'GET /api/memory/concepts': { body: memoryConceptsAvailable },
    });
    const memory = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ProjectMemory />
      </MemoryRouter>,
    );
    await memory.findByText('Memory Available');

    expect(figureMap(memory.container, '.memory-figure')[SERVED_LABEL]).toBe('9');
  });
});

// --- API Surface (inside the collapsed Technical Details region) -------------

describe('API Surface', () => {
  it('states the operation and group counts the served contract documents', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(figureValue('API Surface', 'Documented Operations')).toBe(OPERATION_COUNT);
    expect(figureValue('API Surface', 'Groups')).toBe(GROUP_COUNT);
  });

  /*
   * READ FROM THE DATA TABLE, deliberately. This breakdown is a COLUMN chart: its
   * category names sit under the marks and only the sole maximum is direct-
   * labelled, because a number on every mark goes unread. So the table is where
   * every exact figure lives — and asserting it here is an assertion about the
   * alternative every chart on this surface is required to carry.
   */
  it('breaks the operations down by UPPERCASED HTTP method', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    const caption = 'Documented operations by HTTP method';
    expect(chartTableRows('API Surface', caption)).toEqual(METHOD_BARS);
    // The method names are also visible text under the columns, not SVG glyphs.
    expect(
      [...chartFigure('API Surface', caption).querySelectorAll('.stats-chart-cat')].map((c) =>
        c.textContent?.trim(),
      ),
    ).toEqual(METHOD_BARS.map(([method]) => method));
  });

  it('groups the operations in the contract’s own tag order', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(
      chartRows(
        'API Surface',
        "Documented operations by group, in the contract's own tag order",
      ).map(([group]) => group),
    ).toEqual([
      'Health & Meta',
      'Experiments',
      'Drafts & Answers',
      'Uploads',
      'Validation',
      'Other Operations',
    ]);
  });

  it('the Endpoint Explorer link is the /settings?tab=explorer deep link', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(screen.getByRole('link', { name: 'Open Endpoint Explorer' })).toHaveAttribute(
      'href',
      ROUTES.settingsTab('explorer'),
    );
    expect(ROUTES.settingsTab('explorer')).toBe('/settings?tab=explorer');
  });
});

// --- No analytics (kept in the MAIN flow, uncollapsed) ----------------------

describe('analytics are not collected', () => {
  it('renders the no-telemetry disclosure as information, not as a failure', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    const region = regionOf(NO_ANALYTICS_HEADING);

    const sentence = within(region).getByText(
      /ships no analytics SDK, no tracking pixel, and makes no third-party network request/,
    );
    expect(sentence).toBeInTheDocument();

    // Absence of telemetry is a privacy FEATURE: it must not be announced as an
    // alert, nor carry the app's error styling, nor sit inside anything that does.
    expect(within(region).queryByRole('alert')).toBeNull();
    expect(sentence.closest('[role="alert"]')).toBeNull();
    expect(sentence.className).not.toMatch(/error|warn|danger/);
    expect(region.className).not.toMatch(/error|warn|danger/);
    expect(region.querySelector('.fetch-state.error')).toBeNull();

    // …and it still explains why the page shows no traffic figures.
    expect(within(region).getByText(/no such figure exists in this app to read/)).toBeInTheDocument();
  });

  /**
   * The scope guard. The sentence this section used to render — "This preview
   * does not track visits, users, source IPs, request history, or behavioral
   * analytics" — was false for the deployment: `Dockerfile` starts `uvicorn`
   * with default settings, so an access line carrying the client address,
   * method, path and status is written for EVERY request, and
   * `apps/api/isaac_api/routes.py` writes ~16 metadata-only per-operation
   * outcome lines. Neither is the app's to deny, and the identity gateway in
   * front of a hosted deployment is not even visible to the browser.
   *
   * So this pins BOTH halves: every claim is scoped to the application, and the
   * server-side logging the app cannot deny is named rather than denied.
   */
  it('scopes every claim to the app, and denies neither the access log nor the operation log', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    const text = pageText(regionOf(NO_ANALYTICS_HEADING));

    // The retracted claims, in the wordings that made them false.
    expect(text).not.toMatch(/source IPs?/i);
    expect(text).not.toMatch(/request history/i);
    expect(text).not.toMatch(/does not track/i);

    // What is actually true of the application.
    expect(text).toMatch(/ships no analytics SDK/);
    expect(text).toMatch(/no tracking pixel/);
    expect(text).toMatch(/no third-party network request/);
    expect(text).toMatch(/stores no per-user or per-operation metric/);

    // Server-side logging is disclosed, not denied — including that the page
    // cannot speak for the gateway in front of a hosted deployment.
    expect(text).toMatch(/outcome line per operation/);
    expect(text).toMatch(/access line per request/);
    expect(text).toMatch(/identity gateway/);
    expect(text).toMatch(/the browser cannot see them/);

    // The vetted Settings wording is linked rather than re-authored.
    expect(
      within(regionOf(NO_ANALYTICS_HEADING)).getByRole('link', {
        name: 'Open Data & Privacy Settings',
      }),
    ).toHaveAttribute('href', ROUTES.settingsTab('privacy'));
  });
});

// --- truthfulness guards ------------------------------------------------------

describe('truthfulness — the page states nothing it cannot know', () => {
  /**
   * Forbidden anywhere OUTSIDE the privacy disclosure. The disclosure itself
   * legitimately names the figures that do not exist ("no figure for visits,
   * traffic or request volume"), so scanning the whole page for `visits` would
   * flag the very sentence that makes the promise. The next test pins that the
   * ONLY occurrence is inside that disclosure.
   */
  const FORBIDDEN: [string, RegExp][] = [
    ['a stored "not run" verdict', /\bnot run\b/i],
    ['a PASSED verdict', /\bpassed\b/i],
    ['a FAILED verdict', /\bfailed\b/i],
    ['a database health claim', /\bdatabase\s+online\b/i],
    ['an uptime figure', /\buptime\b/i],
    ['a latency figure', /\blatenc(y|ies)\b/i],
    ['a visit count', /\bvisits?\b/i],
    ['a request-rate figure', /\brequests?\s+per\b/i],
    ['a distinct-user figure', /\bdistinct users\b/i],
  ];

  const SCANNED: [string, Record<string, RouteEntry>][] = [
    ['a fully answered backend', statisticsRoutes()],
    [
      'a backend serving no snapshot overview',
      statisticsRoutes({ graph: { body: graphStatusUnavailable } }),
    ],
    [
      'a truncated records body',
      statisticsRoutes({ records: { body: { records: statisticsRuntimeRecords, total: 9 } } }),
    ],
  ];

  it.each(SCANNED)('renders no invented verdict, health or telemetry figure — %s', async (_case, routes) => {
    const { container } = renderStatistics(routes);
    await settled();

    const text = pageTextWithout(container, NO_ANALYTICS_SECTION);
    /* A scan of an empty string passes every guard below, so prove the scan has
       something to scan: the page rendered, and only the disclosure was removed. */
    expect(text).toContain('Workspace at a Glance');
    expect(text).toContain('API Surface');
    expect(text).not.toContain(NO_ANALYTICS_HEADING);
    /* …and prove a `\b`-anchored pattern can actually FIND a word the page
       renders. Without this, a scan whose word boundaries were swallowed by
       adjacent markup would report every forbidden term as absent. */
    expect(/\brefresh\b/i.test(text), 'the scan must find a word that IS on the page').toBe(true);

    for (const [what, pattern] of FORBIDDEN) {
      expect(pattern.test(text), `${what} appeared: ${pattern}`).toBe(false);
    }
  });

  it('the only mention of telemetry vocabulary is the disclosure that denies collecting it', async () => {
    const { container } = renderStatistics(statisticsRoutes());
    await settled();

    const whole = pageText(container);
    expect(whole.match(/\bvisits\b/g)).toHaveLength(1);
    expect(pageText(regionOf(NO_ANALYTICS_HEADING))).toMatch(/\bvisits\b/);
  });
});

// --- fetch states -------------------------------------------------------------

describe('loading', () => {
  it('each section shows its OWN labelled loading state before the reads settle', async () => {
    /* Asserted synchronously, before any microtask runs: `render` flushes
       effects but not the stub's promises, so this is the first paint. */
    renderStatistics(statisticsRoutes());

    const expected: [string, string][] = [
      ['Workspace at a Glance', 'Loading the workspace summary…'],
      // Inside Technical Details now — a different region, same labelled state.
      ['Runtime', 'Loading the runtime mode and persistence…'],
      ['Workflow Distribution', 'Loading the workflow distribution…'],
      ['Open Questions', 'Loading the open-question counts…'],
      ['Record Schema', 'Loading the official record schema…'],
      ['Evidence and Validation', 'Loading evidence and export-gate counts…'],
      ['Project Memory', 'Loading Project Memory provenance…'],
      ['API Surface', 'Loading the API contract…'],
    ];
    for (const [region, label] of expected) {
      expect(within(regionOf(region)).getByText(label)).toBeInTheDocument();
    }
    // No figure is shown while none has been received.
    expect(screen.queryByText('Total Records')).toBeNull();
    // The meta row states that a read is in progress rather than inventing a time.
    expect(screen.getByText('Reading From the API')).toBeInTheDocument();

    await settled();
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
  });
});

describe('partial failure — one dead source degrades only what reads it', () => {
  const dead: RouteEntry = { status: 500, body: { detail: 'synthetic failure' } };

  it('runtime/records down — Project Memory, API Surface and the privacy note still render', async () => {
    renderStatistics(statisticsRoutes({ records: dead }));
    await settled();

    expect(figureValue('Project Memory', 'Nodes')).toBe(String(graphStatusAvailable.node_count));
    expect(figureValue('API Surface', 'Documented Operations')).toBe(OPERATION_COUNT);
    expect(
      within(regionOf(NO_ANALYTICS_HEADING)).getByText(/ships no analytics SDK/),
    ).toBeInTheDocument();
    // The two runtime cards read /api/about, which is still alive.
    expect(cardValue('Runtime', 'Runtime Mode')).toBe('Synthetic-Only');
    // No record figure is substituted for the ones that were not received.
    expect(screen.queryByText('Total Records')).toBeNull();

    // Every region that reads the dead source offers the recourse.
    for (const region of ['Workspace at a Glance', 'Workflow Distribution', 'Evidence and Validation']) {
      expect(
        within(regionOf(region)).getByRole('button', { name: 'Retry' }),
        `${region} must offer a Retry`,
      ).toBeInTheDocument();
    }
  });

  it('about down — the four record cards still render', async () => {
    renderStatistics(statisticsRoutes({ about: dead }));
    await settled();

    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(cardValue('Workspace at a Glance', 'Need Attention')).toBe('2');
    // Neither runtime fact is stated, and neither is guessed.
    const runtime = regionOf('Runtime');
    expect(within(runtime).queryByText('Runtime Mode')).toBeNull();
    expect(within(runtime).queryByText('Persistence')).toBeNull();
    expect(within(runtime).getByText(/runtime mode and persistence could not be read/)).toBeInTheDocument();
    expect(within(runtime).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('graph/status down — sections 1, 2, 3 and 5 still render', async () => {
    renderStatistics(statisticsRoutes({ graph: dead }));
    await settled();

    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(chartRows('Workflow Distribution', `Records by current workflow step, out of ${RECORD_COUNT} counted`)).toEqual(
      WORKFLOW_BARS,
    );
    expect(chipRows('Evidence and Validation')).toEqual(EVIDENCE_CHIPS);
    expect(figureValue('API Surface', 'Documented Operations')).toBe(OPERATION_COUNT);

    expect(figuresIn('Project Memory')).toEqual({});
    expect(within(regionOf('Project Memory')).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('openapi down — sections 1 to 4 still render', async () => {
    renderStatistics(statisticsRoutes({ openapi: dead }));
    await settled();

    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(chartRows('Workflow Distribution', `Records by current workflow step, out of ${RECORD_COUNT} counted`)).toEqual(
      WORKFLOW_BARS,
    );
    expect(figureValue('Evidence and Validation', 'Total Fields Counted')).toBe('40');
    expect(figureValue('Project Memory', 'Nodes')).toBe(String(graphStatusAvailable.node_count));

    expect(figuresIn('API Surface')).toEqual({});
    expect(within(regionOf('API Surface')).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  /*
   * ONE ALARM PER FAILED SOURCE — the rule `SectionUnavailable`'s docstring
   * states, pinned here so the code and that comment cannot drift apart again.
   *
   * With records + graph + openapi all dead, three alarms is the CORRECT count:
   * three independent sources failed, and one panel could not say which. What the
   * rule forbids is repeating the SAME source's alarm at every section that reads
   * it — records is read by three sections and must alarm at the first only. And
   * `/api/about` is the deliberate quiet exception: its two cards sit beside the
   * record cards, so it never renders a full alarm panel at all.
   */
  it('alarms ONCE PER DEAD SOURCE — not once per section, and not once per page', async () => {
    renderStatistics(statisticsRoutes({ records: dead, graph: dead, openapi: dead }));
    await settled();

    // Three dead sources, three alarms — not one per reading section (records
    // alone is read by four), and not one (which would hide which are down).
    expect(screen.getAllByRole('alert')).toHaveLength(3);

    // The records alarm is at the FIRST section that reads records; the other two
    // sections reading it get the compact, neutral note instead.
    expect(within(regionOf('Workspace at a Glance')).getByRole('alert')).toBeInTheDocument();
    for (const region of ['Workflow Distribution', 'Open Questions', 'Evidence and Validation']) {
      expect(within(regionOf(region)).queryByRole('alert'), `${region} must not re-alarm`).toBeNull();
      expect(regionOf(region).querySelector('.stats-unavailable')).not.toBeNull();
    }
    // The two sources with a single reader each alarm there, once.
    expect(within(regionOf('Project Memory')).getAllByRole('alert')).toHaveLength(1);
    expect(within(regionOf('API Surface')).getAllByRole('alert')).toHaveLength(1);

    // Every affected section still offers the recourse.
    for (const region of [
      'Workspace at a Glance',
      'Workflow Distribution',
      'Open Questions',
      'Evidence and Validation',
      'Project Memory',
      'API Surface',
    ]) {
      expect(
        within(regionOf(region)).getAllByRole('button', { name: 'Retry' }).length,
      ).toBeGreaterThan(0);
    }
  });

  it('a dead /api/about alarms nowhere — it degrades two cards beside four that are fine', async () => {
    renderStatistics(statisticsRoutes({ about: dead }));
    await settled();

    // The quiet exception: no alarm anywhere on the page for this source.
    expect(screen.queryAllByRole('alert')).toHaveLength(0);
    const runtime = regionOf('Runtime');
    expect(runtime.querySelector('.stats-unavailable')).not.toBeNull();
    expect(within(runtime).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    // …and the record cards on the main flow are unaffected.
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
  });
});

describe('total failure', () => {
  it('renders ONE page-level error rather than five stacked copies, and keeps the h1', async () => {
    stubFetchDown();
    const { container } = render(
      <MemoryRouter
        initialEntries={[ROUTES.statistics]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { level: 1, name: 'Statistics' })).toBeInTheDocument();
    await settled();

    expect(screen.getAllByRole('alert')).toHaveLength(1);
    expect(container.querySelectorAll('.fetch-state.error')).toHaveLength(1);
    // Every section is replaced by the one failure, not decorated with it.
    expect(screen.queryByRole('region', { name: 'Workspace at a Glance' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'API Surface' })).toBeNull();
    // The recourse is still offered once.
    expect(screen.getAllByRole('button', { name: 'Retry' })).toHaveLength(1);
  });
});

describe('empty workspace', () => {
  it('says so plainly, links to My Experiments, and draws NO zero-filled rows', async () => {
    renderStatistics(statisticsRoutes({ records: { body: { records: [], total: 0 } } }));
    await settled();

    expect(within(regionOf('Workspace at a Glance')).getByText('No Records Yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to My Experiments' })).toHaveAttribute(
      'href',
      ROUTES.experiments,
    );

    // No grid of zeros, no zero-height bars, no five-chip zero row. The glance
    // section now holds NO card at all in this state: the two /api/about cards it
    // used to keep moved into the `Runtime` region, which still has them.
    expect(regionOf('Workspace at a Glance').querySelectorAll('dl.stat-card')).toHaveLength(0);
    expect(regionOf('Runtime').querySelectorAll('dl.stat-card')).toHaveLength(2);
    // No chart is drawn, and no empty axis either — not one row, not one tick,
    // not one table. Scoped to `.stats-chart` rather than to the region, because
    // the section's own decorative heading glyph is an `<svg>` too and it is not
    // a plot.
    expect(regionOf('Workflow Distribution').querySelectorAll('.stats-chart-row')).toHaveLength(0);
    expect(regionOf('Workflow Distribution').querySelectorAll('figure.stats-chart')).toHaveLength(0);
    expect(regionOf('Workflow Distribution').querySelectorAll('.stats-chart svg')).toHaveLength(0);
    expect(regionOf('Workflow Distribution').querySelectorAll('table')).toHaveLength(0);
    expect(chipRows('Evidence and Validation')).toEqual([]);
    expect(figuresIn('Evidence and Validation')).toEqual({});
    expect(within(regionOf('Workflow Distribution')).getByText(/No bar is drawn rather than a row of zeros/)).toBeInTheDocument();
    expect(within(regionOf('Evidence and Validation')).getByText(/no fields were classified and no count is stated/)).toBeInTheDocument();
    expect(within(regionOf('Evidence and Validation')).getByText(/no export-gate position to state/)).toBeInTheDocument();
  });
});

describe('truncated body', () => {
  const truncated = () =>
    statisticsRoutes({ records: { body: { records: statisticsRuntimeRecords, total: 9 } } });

  it('surfaces the mismatch instead of presenting the subset as the whole workspace', async () => {
    renderStatistics(truncated());
    await settled();

    // The server's own denominator is shown as the total…
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe('9');
    // …and the page says which counts are the subset, naming the ONE that is not.
    expect(
      screen.getByText(
        /This page received 5 of the 9 records the API reports\. Total Records below is the API’s own workspace total; every other count on this page — the cards beside it and every breakdown further down — describes only the 5 records received\./,
      ),
    ).toBeInTheDocument();
    // The breakdowns keep counting what actually arrived — 5, not 9.
    expect(figureValue('Evidence and Validation', 'Records Counted')).toBe('5');
    expect(chartRows('Workflow Distribution', 'Records by current workflow step, out of 5 counted')).toEqual(
      WORKFLOW_BARS,
    );
  });

  /*
   * The caveat must cover the CARDS, not just the sections further down.
   *
   * `Need Attention`, `Ready to Export` and `Exported` are subset counts sitting
   * in the same grid as a workspace-wide `Total Records`. The note used to render
   * AFTER that grid and to say "every breakdown below" — wording that excluded
   * the three counts most likely to be misread, and that pointed past them. Both
   * halves are asserted: the note now precedes the grid in document order, and
   * it does not word itself as applying only to what follows it.
   */
  it('places the caveat BEFORE the cards it qualifies, and words it to include them', async () => {
    const { container } = renderStatistics(truncated());
    await settled();

    const note = container.querySelector('.stats-block-lead .stats-unavailable');
    const grid = container.querySelector('.statistics .stats-cards');
    expect(note, 'the truncation caveat must render').not.toBeNull();
    expect(grid, 'the glance grid must render').not.toBeNull();
    // Node.DOCUMENT_POSITION_FOLLOWING === 4: the grid follows the note.
    expect(note!.compareDocumentPosition(grid!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    const text = textOf(note as HTMLElement);
    // Names the exception rather than excluding the cards it sits above.
    expect(text).toContain('Total Records below is the API’s own workspace total');
    expect(text).toContain('the cards beside it');
    expect(text).not.toMatch(/every breakdown below describes only/);

    // The three subset cards really are inside the grid the note precedes, which
    // is what makes the wording load-bearing rather than decorative.
    for (const label of ['Need Attention', 'Ready to Export', 'Exported']) {
      expect(within(grid as HTMLElement).getByText(label)).toBeInTheDocument();
    }
  });
});

// --- Refresh ------------------------------------------------------------------

describe('Refresh', () => {
  const refreshButton = () => screen.getByRole('button', { name: 'Refresh' });

  it('re-issues EXACTLY the five GETs and no other request', async () => {
    const { calls } = renderStatistics(statisticsRoutes());
    await settled();

    expect([...calls].sort()).toEqual([...STATISTICS_ROUTE_KEYS].sort());
    const afterLoad = calls.length;
    expect(afterLoad).toBe(5);

    fireEvent.click(refreshButton());
    await waitFor(() => expect(calls.length).toBe(afterLoad + 5));

    expect(calls.slice(afterLoad).sort()).toEqual([...STATISTICS_ROUTE_KEYS].sort());
    // Nothing outside the five, in either round.
    for (const key of calls) expect(STATISTICS_ROUTE_KEYS).toContain(key);
  });

  it('issues no POST, PUT, PATCH or DELETE — the page mutates nothing', async () => {
    const { calls } = renderStatistics(statisticsRoutes());
    await settled();

    fireEvent.click(refreshButton());
    await waitFor(() => expect(calls.length).toBe(10));

    for (const key of calls) expect(key.startsWith('GET ')).toBe(true);
    expect(calls.some((key) => /^(POST|PUT|PATCH|DELETE) /.test(key))).toBe(false);
  });

  it('is a real keyboard-operable <button>, and announces completion in a live region present from first render', async () => {
    const { container } = renderStatistics(statisticsRoutes());

    // The live region exists BEFORE the click, and is empty: a region that
    // appears together with its message is not reliably announced.
    const live = container.querySelector('p.sr-only[role="status"]');
    expect(live, 'the announcement region must be present on first render').not.toBeNull();
    expect(live?.textContent).toBe('');

    await settled();

    const button = refreshButton();
    expect(button.tagName).toBe('BUTTON');
    expect(button).toHaveAttribute('type', 'button');
    // Focusable and operable by keyboard: a native button with no tabindex trap.
    expect(button.hasAttribute('disabled')).toBe(false);
    expect(button.getAttribute('tabindex')).toBeNull();
    button.focus();
    expect(document.activeElement).toBe(button);

    fireEvent.click(button);
    // The SAME region's text changed — nothing new mounted to say it.
    await waitFor(() => expect(live?.textContent).toMatch(/^Refresh finished\./));
    expect(container.querySelector('p.sr-only[role="status"]')).toBe(live);
    expect(live?.textContent).toContain('last read the API at');
  });

  /*
   * A FAILED Refresh must not become a read that never happened.
   *
   * `refreshAll` uses `reloadSilent()`, which on rejection deliberately keeps the
   * previous data and stays in the `data` state so the page does not blank. The
   * consequence is that a failed Refresh leaves every figure on screen at its old
   * value — which is fine, and is the design — but ONLY if the page still says
   * so. It must not stamp the old figures with the current time, and it must not
   * announce a reading that did not occur.
   *
   * The two rounds below are the two shapes of that failure: a partial round,
   * where the disclosure is the only signal available (four reads DID succeed,
   * so the clock legitimately advances and no timestamp comparison can
   * discriminate), and a total round, where the clock must visibly not move.
   */
  it('a Refresh where ONE of the five reads fails says so, and never reads as a clean success', async () => {
    const { container } = renderStatistics(
      statisticsRoutes({ records: firstCallOnly(statisticsRecordsBody) }),
    );
    await settled();
    const live = container.querySelector('p.sr-only[role="status"]');
    expect(live).not.toBeNull();
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));

    fireEvent.click(refreshButton());
    await waitFor(() => expect(live?.textContent).toMatch(/^Refresh finished/));

    /* The announcement names how many reads failed and dates the figures to the
       last read that actually returned a body. The second assertion is the
       discriminator: the pre-fix page announced exactly this clean sentence with
       the CURRENT time, for a round in which a read had failed. */
    expect(live?.textContent).toMatch(
      /^Refresh finished, but 1 of 5 reads failed — the figures shown were last read at /,
    );
    expect(live?.textContent).not.toMatch(/^Refresh finished\. The page last read the API at/);

    // Stated on SCREEN as well, not only to a screen reader.
    expect(screen.getByText(/1 of 5 reads failed on the most recent attempt/)).toBeInTheDocument();
    expect(
      screen.getByText(/either absent or older than the last-read time above/),
    ).toBeInTheDocument();

    /* The timestamp still comes from a read that returned: the label is the one
       reserved for a real reading, and its value cannot be later than the moment
       the round finished settling. */
    expect(metaLabel(container)).toBe('Last Read From the API');
    expect(new Date(metaTime(container).dateTime).getTime()).toBeLessThanOrEqual(Date.now());

    // The stale figure is still the one on screen — kept, disclosed, not blanked.
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));

    /* The SAME live region spoke: the on-screen failure note mounts between the
       meta row and the region, and that must not remount the region — a live
       region that appears together with its message is not reliably announced
       (see components/FetchStates.tsx). */
    expect(container.querySelector('p.sr-only[role="status"]')).toBe(live);
  });

  it('a Refresh where ALL FIVE reads fail leaves the timestamp at the last successful read', async () => {
    const { container } = renderStatistics({
      'GET /api/runtime/records': firstCallOnly(statisticsRecordsBody),
      'GET /api/graph/status': firstCallOnly(graphStatusAvailable),
      'GET /api/about': firstCallOnly(aboutResponse),
      'GET /api/openapi': firstCallOnly(openApiFixture),
      /* ALL FIVE, which the title always claimed and the fixture did not supply:
         `/api/schema` had no route here, so it failed on the INITIAL load too and
         this was really "four succeeded then five failed". It passed the no-alarm
         assertion below only because a dead `/api/schema` used to render a note
         with no `role` — the very defect this slice fixed. With the fifth route
         present, every section has data to keep and the round is genuinely 5→5. */
      'GET /api/schema': firstCallOnly(schemaBrowserFixture),
    });
    await settled();
    const live = container.querySelector('p.sr-only[role="status"]');
    expect(live).not.toBeNull();
    const loadedAt = metaTime(container).dateTime;

    /* A real gap, so "did the clock move?" is a question with an answer: without
       it the load and the Refresh could share a millisecond and the comparison
       below would pass vacuously. */
    await act(async () => {
      await new Promise((resolve) => {
        setTimeout(resolve, 25);
      });
    });
    const clickedAt = Date.now();

    fireEvent.click(refreshButton());
    await waitFor(() => expect(live?.textContent).toMatch(/^Refresh finished/));

    expect(live?.textContent).toMatch(
      /^Refresh finished, but 5 of 5 reads failed — the figures shown were last read at /,
    );
    expect(live?.textContent).not.toContain('The page last read the API at');

    // The clock did not move: the same instant as the load, and strictly earlier
    // than the moment Refresh was pressed.
    expect(metaTime(container).dateTime).toBe(loadedAt);
    expect(new Date(loadedAt).getTime()).toBeLessThan(clickedAt);
    expect(metaLabel(container)).toBe('Last Read From the API');

    // Stated on screen, once, as information rather than as an alert.
    expect(screen.getByText(/5 of 5 reads failed on the most recent attempt/)).toBeInTheDocument();
    expect(screen.queryAllByRole('alert')).toHaveLength(0);

    // Every figure is still the one that was actually read, unchanged and
    // un-substituted — the page keeps its data instead of blanking.
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(figureValue('API Surface', 'Documented Operations')).toBe(OPERATION_COUNT);
    expect(figureValue('Project Memory', 'Nodes')).toBe(String(graphStatusAvailable.node_count));
    // …the fifth read included, which is what makes the no-alarm assertion above
    // mean "every section kept its data" rather than "one section never had any".
    expect(figureValue('Record Schema', 'Top-Level Fields')).toBe('6');

    // Still the same live region, with the failure note mounted above it.
    expect(container.querySelector('p.sr-only[role="status"]')).toBe(live);
  });

  it('never polls — no request arrives unprompted', async () => {
    const { calls } = renderStatistics(statisticsRoutes());
    await settled();
    const afterLoad = calls.length;

    await act(async () => {
      await new Promise((resolve) => {
        setTimeout(resolve, 250);
      });
    });

    expect(calls.length).toBe(afterLoad);
  });
});

// --- privacy ------------------------------------------------------------------

describe('privacy — nothing identifying reaches the DOM', () => {
  it('renders no address, no credential, and no record content', async () => {
    const { container } = renderStatistics(statisticsRoutes());
    await settled();
    const text = pageText(container);

    /* The page legitimately renders git commit SHAs (`ab12cd34ef567890`) and
       endpoint paths (`/api/health`), so those are allowed by keeping the
       patterns narrow rather than by loosening them. */
    expect(text).toMatch(/ab12cd34ef567890/); // the allowed provenance string
    expect(text).not.toMatch(/\b\d{1,3}(\.\d{1,3}){3}\b/); // no IP-shaped string
    expect(text).not.toMatch(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/); // no email
    expect(text).not.toMatch(/@/); // and no bare @-token at all

    for (const secret of ['Bearer', 'authorization', 'cookie', 'token', 'secret', 'session']) {
      expect(new RegExp(secret, 'i').test(text), `"${secret}" appeared`).toBe(false);
    }

    // No record content: not a title, not an id, not a per-record value.
    for (const record of statisticsRuntimeRecords) {
      expect(text).not.toContain(record.title);
      expect(text).not.toContain(record.experiment_id);
      expect(text).not.toContain(record.navigate_to);
    }
    expect(text).not.toMatch(/XANES|CuO|K-edge|\.xdi/);
  });
});

// --- the metrics wired from already-available reads ---------------------------

/*
 * `statisticsRuntimeRecords` carries pending_count 5 · 0 · 0 · 0 · 2 and
 * workflow flags blocked on the first row, reopened on the third. Transcribed
 * by hand from the fixture, per choice 2 at the head of this file.
 */
describe('Open Questions', () => {
  it('states the question total, the record tallies, and the maximum', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(figuresIn('Open Questions')).toEqual({
      'Total Open Questions': '7',
      'Records With Open Questions': '2',
      'Most on One Record': '5',
      'Records With a Blocked Step': '1',
      'Records With a Reopened Step': '1',
    });
  });

  it('names the unit of every figure, and forbids adding the five together', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    const text = textOf(regionOf('Open Questions'));
    expect(text).toMatch(/counts QUESTIONS across the 5 records received/);
    /* The three record-counting rows are NAMED rather than referred to by
       position: "the three beneath it" was true and unreadable, because a
       maximum sits among them. */
    expect(text).toMatch(
      /Records With Open Questions, Records With a Blocked Step and Records With a Reopened Step count RECORDS/,
    );
    expect(text).toMatch(/Most on One Record is the largest single record’s question count/);
    expect(text).toMatch(/none of these five may be added together/);
  });

  it('reads no question text, field name or answer — no record string reaches the page', async () => {
    const { container } = renderStatistics(statisticsRoutes());
    await settled();

    const text = textOf(regionOf('Open Questions'));
    for (const record of statisticsRuntimeRecords) {
      expect(text).not.toContain(record.title);
      expect(text).not.toContain(record.experiment_id);
    }
    // …and the section adds no link into a record from a question count.
    expect(regionOf('Open Questions').querySelectorAll('a')).toHaveLength(0);
    expect(pageText(container)).toContain('Total Open Questions');
  });

  it('an empty workspace states that there is nothing to count, and no zero', async () => {
    renderStatistics(statisticsRoutes({ records: { body: { records: [], total: 0 } } }));
    await settled();

    const text = textOf(regionOf('Open Questions'));
    expect(text).toContain('No records were returned, so there is no open-question count to state.');
    expect(text).not.toMatch(/\b\d+\b/);
  });

  it('discloses records whose question count could not be read, rather than zeroing them', async () => {
    const broken = statisticsRuntimeRecords.map((r, i) =>
      i === 0 ? { ...r, pending_count: null as unknown as number } : r,
    );
    renderStatistics(statisticsRoutes({ records: { body: { records: broken, total: broken.length } } }));
    await settled();

    // The 5 that row carried is gone from the total, and the shortfall is stated.
    expect(figureValue('Open Questions', 'Total Open Questions')).toBe('2');
    expect(
      within(regionOf('Open Questions')).getByText(
        /1 of the 5 records received carried no usable question count/,
      ),
    ).toBeInTheDocument();
  });
});

/*
 * `schemaBrowserFixture` — the SAME document the Schema Reference suite browses.
 * Its counts are derived by hand in `statistics-model.test.ts`, which states the
 * derivation; the literals here are what must reach the labelled slots.
 */
describe('Record Schema (inside Technical Details)', () => {
  it('states the schema counts in their labelled slots', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(figuresIn('Record Schema')).toEqual({
      'Schema Title': 'ISAAC AI-Ready Scientific Record v1.05 (fixture)',
      'Schema Version': '1.05',
      // "Fields", not "Sections": on the real schema 5 of the 6 the root requires
      // are scalar strings, and the model's own field names say `topLevelFields`.
      'Top-Level Fields': '6',
      'Fields at Every Depth': '12',
      'Required Top-Level Fields': '3',
      'Fields With Enumerated Values': '1',
      'Conditional Rules': '2',
      'Vocabulary Files': '1',
      'Vocabulary Terms': '4',
    });
  });

  it('breaks the fields down by section, in the document\'s own order', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(
      chartRows('Record Schema', "Fields by top-level section, in the schema's own declaration order"),
    ).toEqual([
      ['isaac_record_version', '1'],
      ['record_id', '1'],
      ['record_type', '1'],
      ['descriptors', '4'],
      ['sample', '4'],
      ['tags', '1'],
    ]);
  });

  it('qualifies what "required" means and what the term count is a property of', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    const text = textOf(regionOf('Record Schema'));
    expect(text).toMatch(/counts what the schema’s own root requires/);
    expect(text).toMatch(/required only once that section is present/);
    expect(text).toMatch(/a property of those files, not a measurement of any stored data/);
    /* …AND WHAT THE FIELD TOTAL DOES NOT REACH. `buildSchemaFieldTree` descends
       `properties` and `items.properties` only, so on the real schema three fields
       inside the `oneOf` at `descriptors.outputs[].descriptors[].relative_to` are
       not listed and `Fields at Every Depth` is 271 rather than 274. The traversal
       is shared with the Schema Reference browser and is deliberately unchanged —
       the two screens agree — so the note is what makes the boundary honest. */
    expect(text).toMatch(/fields declared only inside a\s+oneOf\s+alternative are not listed/);
    expect(text).toMatch(/the fields this view can enumerate/);
  });

  it('links to the browser that renders the same document field by field', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(
      within(regionOf('Record Schema')).getByRole('link', { name: 'Open Schema Reference' }),
    ).toHaveAttribute('href', '/governance?tab=schema');
  });

  /*
   * THE CROSS-SCREEN CLAIM, RENDERED ON BOTH SCREENS.
   *
   * `SchemaBody`'s note tells the reader, in product copy, "The Schema Reference
   * browser walks the document the same way, so the two screens state the same
   * number." That was a claim about ANOTHER SCREEN backed by nothing that rendered
   * it: `statistics-model.test.ts` compares this module's total against a direct
   * call of the shared traversal, which proves there is ONE walker — not that the
   * browser puts that walker's result on screen, nor that it puts it where a
   * reader would compare it. Both screens are rendered here, from the one fixture,
   * and the two DISPLAYED strings are compared.
   *
   * Sequential rather than side by side: `screen` is document-wide, and both
   * surfaces render a `Fields`-labelled count, so mounting them together would
   * make each lookup ambiguous.
   */
  it('states the same field total the Schema Reference browser displays', async () => {
    renderStatistics(statisticsRoutes());
    await settled();
    const onStatistics = figureValue('Record Schema', 'Fields at Every Depth');
    // …and it really did read a number, or the comparison below could pass on ''.
    expect(onStatistics).toMatch(/^\d+$/);

    cleanup();
    stubFetchRoutes({ 'GET /api/schema': { body: schemaBrowserFixture as never } });
    const browser = render(<SchemaBrowser />);
    const paneCount = async () => {
      const el = await waitFor(() => {
        const found = browser.container.querySelector('#schema-fields-list-heading .schema-pane-count');
        expect(found, 'the Fields pane must state a count').not.toBeNull();
        return found as HTMLElement;
      });
      return el.textContent?.trim() ?? '';
    };

    // Unfiltered, the pane states the bare total — the same quantity Statistics
    // labels `Fields at Every Depth`.
    expect(await paneCount()).toBe(onStatistics);
  });

  /*
   * IT ALARMS, and until this slice it did not.
   *
   * `RecordSchemaFacts` rendered `SectionUnavailable` — the compact note the page
   * reserves for a source whose alarm has ALREADY been stated at an earlier section.
   * `/api/schema` has exactly one reader, so nothing had stated it: the note carries
   * no `role`, so a dead schema announced nothing to a screen reader while the
   * banner above said "1 of 5 reads failed". Its two siblings in the same collapsed
   * region — Project Memory and API Surface — have always rendered `BackendDown`
   * (`role="alert"`) for exactly the same situation.
   *
   * The ALARM COUNT is asserted, not just the message, because a message assertion
   * is precisely what passed while the role was missing.
   */
  it('a dead /api/schema alarms ONCE, like its two siblings in this region', async () => {
    renderStatistics(statisticsRoutes({ schema: { status: 500, body: { detail: 'synthetic failure' } } }));
    await settled();

    const region = regionOf('Record Schema');
    // One alarm here, and one on the whole page: this is the only reader.
    expect(within(region).getAllByRole('alert')).toHaveLength(1);
    expect(screen.getAllByRole('alert')).toHaveLength(1);
    // The recourse is still offered, exactly as the compact note offered it.
    expect(within(region).getByRole('button', { name: 'Retry' })).toBeInTheDocument();

    /*
     * AND STILL NOTHING ABOUT THE SCHEMA. Every figure slot is empty, and no number
     * is stated outside the alarm panel. Measured outside it because `BackendDown`'s
     * local-build copy carries the run command, which contains a host and a port —
     * not a figure about the schema, and the same text its two siblings already show.
     */
    expect(figuresIn('Record Schema')).toEqual({});
    const alarmText = textOf(within(region).getByRole('alert'));
    expect(textOf(region).replace(alarmText, '')).not.toMatch(/\b\d+\b/);

    // Everything else still renders.
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(figureValue('API Surface', 'Documented Operations')).toBe(OPERATION_COUNT);
  });
});

describe('Platform Metrics — the inactive adapter boundary', () => {
  it('states that it is not connected, and states no figure at all', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    const region = regionOf('Platform Metrics');
    expect(within(region).getByText('Not Connected')).toBeInTheDocument();
    expect(
      within(region).getByText(/Platform-wide record figures are not connected for this deployment/),
    ).toBeInTheDocument();
    // No digit anywhere in the section: not a total, not a zero, not a date.
    expect(textOf(region)).not.toMatch(/\d/);
  });

  it('says the absence is an absence, not a withholding and not a zero', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    const text = textOf(regionOf('Platform Metrics'));
    expect(text).toMatch(/Nothing is being hidden and no figure is zero/);
    expect(text).toMatch(/this application has no source to read one from/);
    // It must not blame a decision, a permission, or a person.
    expect(text).not.toMatch(/permission|denied|governance|approval|administrator|Dean/i);
  });

  it('lists the six planned views, each naming what it would count', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    const titles = [...regionOf('Platform Metrics').querySelectorAll('.stats-plan-title')].map(
      (n) => n.textContent?.trim() ?? '',
    );
    expect(titles).toEqual([
      'Records Across the Platform',
      'Records by Scientific Domain',
      'Records by Experiment Type',
      'Records by Schema Version',
      'Schema Validation Outcomes',
      'Records Added Over Time',
    ]);
  });

  it('adds NO request to the page — the five reads are unchanged by its presence', async () => {
    const { calls } = renderStatistics(statisticsRoutes());
    await settled();

    expect([...calls].sort()).toEqual([...STATISTICS_ROUTE_KEYS].sort());
    expect(calls.filter((c) => /portal|metrics|platform/i.test(c))).toEqual([]);
  });

  it('draws no chart, no axis and no empty plot', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    const panel = regionOf('Platform Metrics');
    expect(panel.querySelector('figure.stats-chart')).toBeNull();
    expect(panel.querySelector('.stats-chart-track')).toBeNull();
    expect(panel.querySelector('.stats-chart-grid')).toBeNull();
  });
});

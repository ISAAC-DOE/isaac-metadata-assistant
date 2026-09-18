import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';

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
  activitySummaryFixture,
  STATISTICS_VERIFICATION_ROUTE_KEY,
  TUTORIAL_SESSION_ID,
  aboutResponse,
  graphStatusAvailable,
  graphStatusPreRegen,
  graphStatusUnavailable,
  importListFixture,
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
  ['Record Created', '0'],
  ['Complete Metadata', '1'],
  ['Review Evidence', '1'],
  ['Review Export Readiness', '1'],
  ['Export', '1'],
  ['All Steps Complete', '1'],
];

/** The six evidence classes in SEVERITY precedence (not by count).
 *  `Evidence Unreadable` is a read failure, never folded into `Unknown` — and it
 *  is listed at 0 here because these fixtures carry no unreadable entry; the
 *  non-zero exercise of the class lives in `statistics-model.test.ts`. */
const EVIDENCE_CHIPS: [string, string][] = [
  ['Supported', '30'],
  ['Inferred Candidate', '3'],
  ['Insufficient Evidence', '2'],
  ['Conflicting Evidence', '2'],
  ['Unknown', '3'],
  ['Evidence Unreadable', '0'],
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
 * The same render, landed on the BUILD tab.
 *
 * ── WHY HALF THIS FILE NOW USES IT ────────────────────────────────────────
 *
 * The 2026-09-15 redesign split the one `general` tab in two. Record
 * Verification, Verification Safeguards, Platform Metrics, the four prose
 * disclosures and the whole Technical Details region (Runtime · Record Schema ·
 * Project Memory · API Surface) moved to `?tab=build`; the workspace figures
 * stayed on `general`. Nothing was deleted and no assertion below was
 * weakened — the cases that read those sections are re-pointed at the tab the
 * section is now on, and they assert exactly what they asserted before.
 *
 * It uses `ROUTES.statisticsTab('build')` rather than a literal, so the helper
 * and the page cannot disagree about the parameter name.
 *
 * THE READS ARE UNCHANGED BY THE TAB. All six are issued on mount whichever tab
 * is showing (the page's own header states that as a rule and
 * `switching tabs costs no round trip` pins it), so a routes map that satisfies
 * `renderStatistics` satisfies this one too.
 */
function renderStatisticsBuild(routes: Record<string, RouteEntry>) {
  const calls = stubFetchRoutes(routes);
  const view = render(
    <MemoryRouter
      initialEntries={[ROUTES.statisticsTab('build')]}
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
/**
 * A ROUTER NAVIGATION the test can trigger, for the one case that needs it.
 *
 * The worked-example scope must mount on `/experiments` so the guided
 * walkthrough's per-step navigation claim is spent there (see `renderIn`), then
 * move. Rendered only inside that branch's tree.
 */
function ScopeProbe() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      data-testid="scope-probe-to-statistics"
      onClick={() => navigate(ROUTES.statistics)}
    >
      to statistics
    </button>
  );
}

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
    /*
     * STILL MOUNTS ON `/experiments`, THEN NAVIGATES — and the mount route is
     * load-bearing for a reason worth recording, because two wrong fixes were
     * tried before it was measured.
     *
     * This block used to reach Statistics by clicking the `Statistics` item in
     * the PRIMARY NAVIGATION. That item no longer exists: Statistics was demoted
     * out of the primary list (`UX-017`, 2026-09-13) and is now reached from
     * `Settings & API → Overview`.
     *
     * ── WHY MOUNTING DIRECTLY ON `/statistics` DOES NOT WORK ────────────────
     *
     * **Wrong fix 1** was `initialEntries={[ROUTES.statistics]}`. It rendered
     * **My Experiments** — measured, by dumping every `<h1>`: `['My
     * Experiments']`. **Wrong fix 2** was reordering `settled()`, on the theory
     * that `findByRole`'s 1,000 ms budget had expired at 1,061 ms. It had, but
     * that was a symptom.
     *
     * The cause is product behaviour, not test scaffolding:
     * `GuidedTutorial.tsx:182-193` navigates to the current step's `targetPath`
     * **once per step**, spending a one-time claim (`claimStepNavigation`). When
     * the router opens ALREADY on the target, `markStepArrived` spends the claim
     * without moving; when it opens anywhere else, the tutorial routes the
     * reader to the step — which is exactly what a guided walkthrough should do.
     * The first step targets `/experiments`, so mounting there spends the claim
     * and a subsequent navigation sticks. Mounting on `/statistics` leaves it
     * unspent and gets steered.
     *
     * So the navigation is kept, and it is deliberately a ROUTER navigation
     * rather than a click: this file's subject is the lead sentence's wording
     * per workspace scope, not wayfinding. The replacement navigation PATH is
     * covered where it belongs — `statistics-nav.test.tsx`'s Back/Forward walk
     * clicks the real `Settings → Statistics` link.
     */
    await act(async () => {
      view = render(
        <MemoryRouter
          initialEntries={[ROUTES.experiments]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <AppRoutes />
          <ScopeProbe />
        </MemoryRouter>,
      );
    });
    await screen.findByRole('heading', { level: 1, name: LABELS.screenExperiments });
    await act(async () => {
      fireEvent.click(screen.getByTestId('scope-probe-to-statistics'));
    });
    await settled();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Statistics' }),
    ).toBeInTheDocument();
    return view;
  }

  afterEach(() => {
    __resetTutorialStore();
    sessionStorage.clear();
  });

  /*
   * ── THE EXPECTED SENTENCE CHANGED ON 2026-09-15; THE PROPERTY DID NOT ────
   *
   * ~~'Record verification first, then a read-only view of {workspace},
   * workflow readiness, open questions, evidence, the official record schema,
   * Project Memory, and the API surface — and, for platform-wide figures, why
   * none is stated.'~~
   *
   * The redesign replaced that six-topic table of contents with the question
   * the tab answers, and moved four of its named topics to `?tab=build`. The
   * literal is updated in place and the old one struck, because this file's
   * whole purpose here is that a rewording of the lead FAILS rather than
   * drifts — and it has now caught two.
   *
   * WHAT IS STILL ASSERTED, AND IS THE ONLY REASON THESE TWO CASES EXIST: the
   * lead names a WORKSPACE, it names the right one for the scope, and the
   * retired "example workspace" claim is absent from the page in the ordinary
   * scope. That is unchanged, and it is the defect that produced this block.
   */
  it('ordinary scope: names the workspace without claiming it holds examples', async () => {
    const { container } = await renderIn('ordinary');

    expect(
      screen.getByText(
        'How much is recorded in this workspace, how much is ready, and how much needs ' +
          'attention.',
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
        'How much is recorded in the open worked-example workspace, how much is ready, and ' +
          'how much needs attention.',
      ),
    ).toBeInTheDocument();
    // The neutral ordinary wording must not leak into the scope that has examples.
    expect(screen.queryByText(/recorded in this workspace/)).toBeNull();
  });

  /*
   * ── INVERTED IN PLACE, 2026-09-15, AND THE INVERSION IS THE POINT ────────
   *
   * ~~'names record verification, and names it before the workspace clause'~~
   *
   * That assertion was CORRECT for the page it was written against and is
   * struck rather than deleted, because the REASONING behind it is still live
   * and is what makes the new assertion the right one. Its rule was: a lead
   * sitting directly above a panel reads as a promise about that panel,
   * whatever it is technically a summary of — so when Record Verification
   * became the first section, the lead had to name it first.
   *
   * THE SAME RULE NOW FORBIDS EXACTLY WHAT IT USED TO REQUIRE. Record
   * Verification is no longer on this tab at all; it is on `?tab=build`. A
   * lead that still named it would promise an engineering QA program above a
   * panel of workspace figures — the same defect, pointing the other way.
   *
   * SO THE PROPERTY IS ASSERTED IN BOTH DIRECTIONS, ON BOTH TABS, which is
   * what makes it falsifiable: the Overview lead must NOT name verification
   * and must name the workspace; the Build lead must name verification and
   * must NOT name a workspace. A single-tab assertion would pass for a page
   * that used one lead everywhere.
   *
   * `safeguard` stays banned on both, for the reason the struck version gave
   * and which is unchanged: `Verification Safeguards` renders only when a
   * readable report is on screen, so naming it would promise a heading that is
   * legitimately absent in four of the section's runtime states.
   */
  it('the Overview lead names the workspace and NOT the verification program', async () => {
    await renderIn('ordinary');
    const lead = document.querySelector('.placeholder > p')!.textContent ?? '';

    expect(lead).not.toMatch(/verification/i);
    expect(lead).not.toMatch(/safeguard/i);
    expect(lead).toMatch(/this workspace/i);
  });

  it('the Build lead names the verification program and NOT a workspace', async () => {
    renderStatisticsBuild(statisticsRoutes());
    await settled();
    const lead = document.querySelector('.placeholder > p')!.textContent ?? '';

    expect(lead).toMatch(/record verification/i);
    expect(lead).not.toMatch(/safeguard/i);
    // It must not claim to describe the reader's records — that is the whole
    // reason this tab exists separately.
    expect(lead).not.toMatch(/this workspace|worked-example workspace/i);
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
  /*
   * ~~'the four record cards…'~~ — SIX now, and the two added tiles are
   * asserted here rather than in a case of their own, because what this test
   * exists to pin is that each headline figure lands in ITS OWN labelled slot.
   * A separate case for the new pair would leave the row's completeness
   * unasserted, which is how a mislabelled tile passes.
   *
   * The `Need Attention` label became `Needs Attention` — it now comes from
   * `LABELS.groupNeedsAttention`, the same string My Experiments' facet uses,
   * so the page and the queue name one set one way. The literal is updated
   * rather than loosened.
   *
   * `Open Questions` is 5 + 0 + 0 + 0 + 2 = 7 over the five fixture rows (the
   * same total the Open Questions section states, transcribed from the fixture
   * by hand per choice 2 at the head of this file), and `Historical Imports` is
   * `importListFixture.total`.
   */
  it('the six headline cards state the counts the fixture implies', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(cardValue('Workspace at a Glance', 'Needs Attention')).toBe('2');
    expect(cardValue('Workspace at a Glance', 'Ready to Export')).toBe('1');
    expect(cardValue('Workspace at a Glance', 'Exported')).toBe('1');
    expect(cardValue('Workspace at a Glance', 'Open Questions')).toBe('7');
    expect(cardValue('Workspace at a Glance', 'Historical Imports')).toBe('2');

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
    /* The `Runtime` region moved to `?tab=build` with the rest of Technical
       Details; the glance half of the assertion is unaffected, because the two
       tabs are rendered by one component tree and `regionOf('Workspace at a
       Glance')` is simply absent here — which is why that half is re-expressed
       below as a page-text absence rather than a region query. */
    renderStatisticsBuild(statisticsRoutes());
    await settled();

    // The API sends `synthetic-only` / `ephemeral`; only capitalisation changes.
    expect(aboutResponse.runtime_mode).toBe('synthetic-only');
    expect(aboutResponse.persistence).toBe('ephemeral');
    expect(cardValue('Runtime', 'Runtime Mode')).toBe('Synthetic-Only');
    expect(cardValue('Runtime', 'Persistence')).toBe('Ephemeral');

    // …and they are NOT in the glance row, so the move is real rather than a
    // copy. Asserted on the Overview tab, where the glance row actually is:
    // a `queryByText` on THIS tab would pass simply because the row is absent.
    cleanup();
    renderStatistics(statisticsRoutes());
    await settled();
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
    const { container } = renderStatisticsBuild(
      statisticsRoutes({
        about: { body: { ...aboutResponse, runtime_mode: null, persistence: 7 } },
      }),
    );
    await settled();

    // The page is still there: its heading, every region ON THIS TAB, and the
    // figures that came from the other reads. The region list is split by tab
    // rather than shortened — the Overview half is asserted at the end.
    expect(screen.getByRole('heading', { level: 1, name: 'Statistics' })).toBeInTheDocument();
    for (const region of ['Runtime', 'Project Memory', 'API Surface']) {
      expect(regionOf(region), `${region} must still render`).toBeInTheDocument();
    }
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

    // The Overview tab is unharmed by the same malformed body: it reads none of
    // `/api/about`, so every workspace figure on it still renders.
    cleanup();
    renderStatistics(
      statisticsRoutes({
        about: { body: { ...aboutResponse, runtime_mode: null, persistence: 7 } },
      }),
    );
    await settled();
    for (const region of [
      'Workspace at a Glance',
      'Workflow Distribution',
      'Evidence and Validation',
      NO_ANALYTICS_HEADING,
    ]) {
      expect(regionOf(region), `${region} must still render`).toBeInTheDocument();
    }
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
  });
});

// --- Workflow Distribution ------------------------------------------------

describe('Workflow Distribution', () => {
  it('renders every canonical bucket with its count as real text, zeros included, in canonical order', async () => {
    const { container } = renderStatistics(statisticsRoutes());
    await settled();

    // ONE ordered read of the visible spans. `Record Created` is at zero in this
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
  it('renders the six evidence classes in severity precedence, NOT sorted by count', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    expect(chipRows('Evidence and Validation')).toEqual(EVIDENCE_CHIPS);

    // The discriminator: this fixture's counts (30,3,2,2,3,0) are NOT in
    // descending order, so a page that re-sorted by count would read
    // 30,3,3,2,2,0 and fail the list comparison above. Stated explicitly so the
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
    renderStatisticsBuild(statisticsRoutes());
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

    renderStatisticsBuild(statisticsRoutes({ graph: { body: graphStatusPreRegen } }));
    await settled();

    expect(figureValue('Project Memory', 'Served Files (Path Set)')).toBe('9');
  });

  it('states a differing source commit as point-in-time, showing BOTH commits', async () => {
    expect(graphStatusAvailable.source_graph_commit).not.toBe(
      graphStatusAvailable.deployed_app_commit,
    );

    renderStatisticsBuild(statisticsRoutes());
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

    const { container } = renderStatisticsBuild(statisticsRoutes({ graph: { body: graphStatusPreRegen } }));
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
    const { container } = renderStatisticsBuild(
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
    // --- Statistics (the `Project Memory` region is on `?tab=build`)
    const stats = renderStatisticsBuild(statisticsRoutes());
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
    renderStatisticsBuild(statisticsRoutes());
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
    renderStatisticsBuild(statisticsRoutes());
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
    renderStatisticsBuild(statisticsRoutes());
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
    renderStatisticsBuild(statisticsRoutes());
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
   *
   * ── THE SECOND HALF MOVED, AND THIS TEST MOVED WITH IT ────────────────────
   *
   * The visual-first reorganisation reduced this section to ONE sentence plus the
   * Settings link: Statistics is not where this app's privacy policy is
   * explained, and the owner's brief was to stop repeating it here. The
   * server-side-logging paragraph is the one thing that could NOT simply be cut,
   * because it is the correction of a claim this section shipped falsely — so it
   * is relocated, verbatim, into the `Known Limitations` disclosure.
   *
   * THE ASSERTIONS ARE THEREFORE SPLIT RATHER THAN DELETED, and the split is the
   * point: this test now checks the paragraph is IN Known Limitations AND that
   * the no-analytics section points there. Deleting these four patterns — the
   * cheap way to make a reorganisation pass — would have left the narrow claim
   * standing on a page with nothing to scope it, which is the state the original
   * defect was corrected out of.
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

    // ONE sentence of body copy, which is the reduction the brief asked for.
    // Counted on the section's own `.stats-note` paragraphs, so the supporting
    // line and the link line are not mistaken for body prose.
    expect(regionOf(NO_ANALYTICS_HEADING).querySelectorAll('p.stats-note')).toHaveLength(1);

    // …and the scope is still disclosed AT the claim, in the section's own
    // supporting line, naming where the full statement is.
    expect(text).toMatch(/Server-side logs belong to whoever operates the deployment/);
    expect(text).toMatch(/Known Limitations/);

    /*
     * ── THE POINTER IS NOW ASSERTED AS A LINK, AND THAT IS A STRENGTHENING ──
     *
     * `Known Limitations` moved to `?tab=build`, so the supporting line's old
     * word "below" became false. The section now names the tab AND offers a
     * real anchor to it, and this case pins the anchor rather than only the
     * words — because the words alone are what would drift if the target moved
     * again. Without this, a reader could be pointed at a disclosure with no
     * way to reach it, which is worse than the state the original defect was
     * corrected out of.
     */
    expect(text).toMatch(/on the Build & Verification tab/);
    expect(
      within(regionOf(NO_ANALYTICS_HEADING)).getByRole('link', { name: 'Read Known Limitations' }),
    ).toHaveAttribute('href', ROUTES.statisticsTab('build'));

    // The vetted Settings wording is linked rather than re-authored. Asserted
    // BEFORE the tab switch below, because this link is the Overview section's.
    expect(
      within(regionOf(NO_ANALYTICS_HEADING)).getByRole('link', {
        name: 'Open Data & Privacy Settings',
      }),
    ).toHaveAttribute('href', ROUTES.settingsTab('privacy'));

    // The server-side logging paragraph itself: relocated, not dropped — and it
    // is now one tab away, so it is read on the tab it lives on. Resolved
    // through the disclosure's own heading id, so a rename cannot make this
    // vacuous — `closest('details')` on a missing element would throw.
    cleanup();
    const build = renderStatisticsBuild(statisticsRoutes());
    await settled();
    const limitations = build.container.querySelector('#stats-limitations')!.closest('details');
    expect(limitations, 'the Known Limitations disclosure must render').not.toBeNull();
    const limitationsText = pageText(limitations as HTMLElement);
    expect(limitationsText).toMatch(/outcome line per operation/);
    expect(limitationsText).toMatch(/access line per request/);
    expect(limitationsText).toMatch(/identity gateway/);
    expect(limitationsText).toMatch(/the browser cannot see them/);

  });
});

/*
 * ── THE VISUAL-FIRST ORDER, AND THE RULE THAT DECIDES WHAT MAY BE COLLAPSED ──
 *
 * Record Verification was the FIFTH h2 on this tab, roughly 1,700px down. Every
 * item the brief named as above-the-fold material — the corpus that ran, the
 * report's age, the four headline counts, the two validators side by side, the
 * mutation harness, the protected distributions — is inside it, so the fix was
 * to promote the section rather than to compress the page.
 *
 * Supporting PROSE went the other way, into four new closed disclosures beside
 * `Technical Details`. The rule the split was made on is asserted here rather
 * than only written down, because it is the one that can be violated silently:
 * A DISCLOSURE MAY HOLD PROSE AND MUST NOT HOLD A MEASUREMENT. A closed
 * `<details>` is not scanned by axe, is skipped by a reader scanning headings,
 * and reads as optional — so collapsing a finding is hiding it.
 *
 * `Technical Details` is deliberately exempt from that assertion and is checked
 * separately: it holds build-internal FIGURES on purpose and always has.
 */
describe('the visual-first order', () => {
  /** Every section element, in document order, by its accessible name. */
  function sectionNames(container: HTMLElement): string[] {
    return [...container.querySelectorAll('section[aria-labelledby]')].map(
      (s) => container.querySelector(`#${s.getAttribute('aria-labelledby')}`)?.textContent ?? '',
    );
  }

  /*
   * ── INVERTED IN PLACE, 2026-09-15, AND BOTH HALVES ARE NOW ASSERTED ──────
   *
   * ~~'opens with Record Verification and its safeguards, before any workspace
   * figure' -> ['Record Verification', 'Verification Safeguards',
   * 'Workspace at a Glance']~~
   *
   * That ORDER was the whole point of the visual-first reorganisation and the
   * expectation is struck rather than deleted, because it records a decision
   * that has now been superseded by a later one rather than found wrong.
   *
   * WHAT SUPERSEDED IT. Putting an engineering QA program over a corpus of
   * official records ABOVE a scientist's own workspace figures is exactly the
   * mixing the 2026-09-15 redesign undoes; the section is 3,049 px of a
   * 6,993 px tab, measured, and it was the entire first viewport. So the tab a
   * scientist lands on now opens with `Workspace at a Glance`, and Record
   * Verification opens a tab of its own.
   *
   * THE PROPERTY IS ASSERTED ON BOTH TABS, which is what keeps it falsifiable:
   * Overview must open with the glance and must not contain the verification
   * sections at all; Build must still open with Record Verification and its
   * safeguards in that order. A one-tab assertion would pass for a page that
   * rendered everything twice.
   */
  it('Overview opens with the workspace figures, and holds no verification section', async () => {
    const { container } = renderStatistics(statisticsRoutes());
    await settled();

    const names = sectionNames(container);
    // Vacuity guard: an empty or mis-rooted scan would satisfy every comparison
    // below without having read anything.
    expect(names.length, 'the scan found no sections at all').toBeGreaterThan(5);
    expect(names[0]).toBe('Workspace at a Glance');
    expect(names).not.toContain('Record Verification');
    expect(names).not.toContain('Verification Safeguards');
    expect(names).not.toContain('Platform Metrics');
  });

  it('Build still opens with Record Verification and its safeguards, in that order', async () => {
    const { container } = renderStatisticsBuild(statisticsRoutes());
    await settled();

    const names = sectionNames(container);
    expect(names.length, 'the scan found no sections at all').toBeGreaterThan(2);
    expect(names.slice(0, 2)).toEqual(['Record Verification', 'Verification Safeguards']);
    // …and the workspace figures are not duplicated onto this tab.
    expect(names).not.toContain('Workspace at a Glance');
  });

  it('renders the four prose disclosures, closed, in the documented order', async () => {
    const { container } = renderStatisticsBuild(statisticsRoutes());
    await settled();

    const prose = [...container.querySelectorAll('details.stats-disclosure')];
    expect(prose.map((d) => d.querySelector('h2')?.textContent)).toEqual([
      'How Verification Works',
      'How to Interpret Results',
      'Mutation Methodology',
      'Known Limitations',
    ]);
    for (const d of prose) {
      expect(d.hasAttribute('open'), 'a supporting disclosure must arrive closed').toBe(false);
    }
    // The build-internals region keeps its own class, and stays the ONLY one
    // carrying it: three e2e helpers address `details.stats-technical` through
    // strict-mode locators, one of them asserting exactly one match.
    expect(container.querySelectorAll('details.stats-technical')).toHaveLength(1);
  });

  /*
   * WIDENED, NOT RE-POINTED. The four prose disclosures are on `?tab=build`,
   * and the Overview tab gained TWO of its own when the distillation moved the
   * restatements of two caveats behind a `<summary>`. Scanning only one tab
   * would leave the new pair — the more recently authored, so the likelier to
   * carry a figure — unguarded. Both tabs are scanned, with the expected count
   * asserted on each so neither can pass by rendering nothing.
   */
  it('puts NO measurement inside a prose disclosure — on EITHER tab', async () => {
    const build = renderStatisticsBuild(statisticsRoutes());
    await settled();
    assertNoMeasurementInProse(build.container, 4);
    cleanup();

    const overview = renderStatistics(statisticsRoutes());
    await settled();
    assertNoMeasurementInProse(overview.container, 2);
  });

  function assertNoMeasurementInProse(container: HTMLElement, expected: number): void {
    const prose = [...container.querySelectorAll('details.stats-disclosure')];
    expect(prose.length, 'no prose disclosure rendered, so this asserts nothing').toBe(expected);
    for (const d of prose) {
      const figures = d.querySelectorAll(
        '.stat-card, .stats-figure, figure.stats-chart, .stats-verify-safeguard, .stats-mini-item',
      );
      expect(
        [...figures].map((n) => n.className),
        `${d.querySelector('h2')?.textContent} holds a measurement; a closed disclosure is ` +
          'not scanned by axe and is skipped by a reader, so a figure inside one is a hidden figure',
      ).toEqual([]);
    }
    // The negative control: the guard's own selector really does match the
    // figures this page draws, so an empty result means "none here" rather than
    // "the selector is broken".
    expect(
      container.querySelectorAll(
        '.stat-card, .stats-figure, figure.stats-chart, .stats-verify-safeguard, .stats-mini-item',
      ).length,
    ).toBeGreaterThan(20);
  }

  /*
   * The six tri-state safeguards are MEASUREMENTS, so the block that renders
   * them was promoted to a visible `h2` section rather than folded into a fifth
   * disclosure. Pinned in both directions: it is a real section with that
   * accessible name, and it is inside no `<details>` at all.
   */
  it('keeps Verification Safeguards visible, with its "does not apply" sentence intact', async () => {
    const { container } = renderStatisticsBuild(statisticsRoutes());
    await settled();

    const safeguards = regionOf('Verification Safeguards');
    expect(safeguards.closest('details')).toBeNull();
    expect(safeguards.querySelectorAll('.stats-verify-safeguard').length).toBe(6);
    expect(pageText(safeguards)).toMatch(
      /A safeguard that does not apply is not a safeguard that held\./,
    );
    // …and it is a SIBLING of Record Verification, not nested inside it.
    expect(
      container.querySelector('section[aria-labelledby="stats-verification"]')!.contains(safeguards),
    ).toBe(false);
  });

  /*
   * C7 — TWO CLOCKS, and they are never merged. The page's own
   * `Last Read From the API` is a CLIENT instant captured when one of its five
   * reads returned a body; `Report Generated` / `Report Age` are SERVER values
   * the verification report carries about the program run. The freshness strip
   * moved the report clock up beside the figures it dates; the page clock did
   * not move and did not change label.
   */
  it('keeps the page clock and the report clock apart', async () => {
    const { container } = renderStatisticsBuild(statisticsRoutes());
    await settled();

    // The page clock, still in the meta row above the tab panel body.
    expect(metaLabel(container)).toBe('Last Read From the API');

    // The report clock, now in Record Verification's freshness strip — and
    // stated exactly once, so the two rows cannot disagree with each other.
    const verification = container.querySelector(
      'section[aria-labelledby="stats-verification"]',
    ) as HTMLElement;
    const strip = verification.querySelector('.stats-verify-freshness') as HTMLElement;
    expect(strip, 'the freshness strip must render').not.toBeNull();
    expect(pageText(strip)).toMatch(/Report Generated/);
    expect(pageText(strip)).toMatch(/Report Age/);
    expect(pageText(verification).match(/Report Generated/g)).toHaveLength(1);
    expect(pageText(verification).match(/Report Age/g)).toHaveLength(1);

    // The report clock is NOT on the page meta row, and the page clock is not
    // inside the verification section.
    expect(pageText(container.querySelector('.stats-meta') as HTMLElement)).not.toMatch(
      /Report (Generated|Age)/,
    );
    expect(pageText(verification)).not.toMatch(/Last Read From the API/);
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

  /*
   * SCANNED ON BOTH TABS SINCE 2026-09-15, and that is a widening rather than
   * a re-pointing: `API Surface`, `Record Schema`, `Project Memory`, Platform
   * Metrics and the verification report all moved to `?tab=build`, and every
   * one of them is a likelier home for an invented verdict or health figure
   * than the workspace counts that stayed. Scanning one tab would have left
   * the more dangerous half unguarded while still reading as a page-wide scan.
   *
   * The per-tab vacuity anchors are named per tab for the same reason: a scan
   * that anchored on `Workspace at a Glance` while reading the Build tab would
   * fail loudly, which is the point — the anchor must prove THIS tab rendered.
   */
  it.each(SCANNED)('renders no invented verdict, health or telemetry figure — %s', async (_case, routes) => {
    const overview = renderStatistics(routes);
    await settled();
    assertNoInventedFigure(overview.container, 'Workspace at a Glance');
    cleanup();

    const build = renderStatisticsBuild(routes);
    await settled();
    assertNoInventedFigure(build.container, 'API Surface');
  });

  function assertNoInventedFigure(container: HTMLElement, anchor: string): void {
    const text = pageTextWithout(container, NO_ANALYTICS_SECTION);
    /* A scan of an empty string passes every guard below, so prove the scan has
       something to scan: the page rendered, and only the disclosure was removed. */
    expect(text).toContain(anchor);
    expect(text).not.toContain(NO_ANALYTICS_HEADING);
    /* …and prove a `\b`-anchored pattern can actually FIND a word the page
       renders. Without this, a scan whose word boundaries were swallowed by
       adjacent markup would report every forbidden term as absent. */
    expect(/\brefresh\b/i.test(text), 'the scan must find a word that IS on the page').toBe(true);

    for (const [what, pattern] of FORBIDDEN) {
      expect(pattern.test(text), `${what} appeared: ${pattern}`).toBe(false);
    }
  }

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

    /* The eight regions are now split across two tabs, so the expectation is
       split with them rather than shortened. Every label is the one it was:
       a section's loading state did not change because the tab did. */
    const onOverview: [string, string][] = [
      ['Workspace at a Glance', 'Loading the workspace summary…'],
      ['Workflow Distribution', 'Loading the workflow distribution…'],
      ['Open Questions', 'Loading the open-question counts…'],
      ['Evidence and Validation', 'Loading evidence and export-gate counts…'],
      ['Recent Work', 'Loading the most recent updates…'],
      ['Historical Imports', 'Loading the import sessions…'],
    ];
    for (const [region, label] of onOverview) {
      expect(within(regionOf(region)).getByText(label)).toBeInTheDocument();
    }
    // No figure is shown while none has been received.
    expect(screen.queryByText('Total Records')).toBeNull();
    // The meta row states that a read is in progress rather than inventing a time.
    expect(screen.getByText('Reading From the API')).toBeInTheDocument();

    await settled();
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    cleanup();

    renderStatisticsBuild(statisticsRoutes());
    const onBuild: [string, string][] = [
      // Inside Technical Details — a different region, same labelled state.
      ['Runtime', 'Loading the runtime mode and persistence…'],
      ['Record Schema', 'Loading the official record schema…'],
      ['Project Memory', 'Loading Project Memory provenance…'],
      ['API Surface', 'Loading the API contract…'],
    ];
    for (const [region, label] of onBuild) {
      expect(within(regionOf(region)).getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('Reading From the API')).toBeInTheDocument();
    await settled();
  });
});

describe('partial failure — one dead source degrades only what reads it', () => {
  const dead: RouteEntry = { status: 500, body: { detail: 'synthetic failure' } };

  it('runtime/records down — Project Memory, API Surface and the privacy note still render', async () => {
    renderStatistics(statisticsRoutes({ records: dead }));
    await settled();

    expect(
      within(regionOf(NO_ANALYTICS_HEADING)).getByText(/ships no analytics SDK/),
    ).toBeInTheDocument();
    // The import figures read /api/imports, which is still alive.
    expect(figureValue('Historical Imports', 'Import Sessions')).toBe('2');
    // No record figure is substituted for the ones that were not received.
    expect(screen.queryByText('Total Records')).toBeNull();

    // Every region that reads the dead source offers the recourse.
    for (const region of [
      'Workspace at a Glance',
      'Workflow Distribution',
      'Evidence and Validation',
      'Recent Work',
    ]) {
      expect(
        within(regionOf(region)).getByRole('button', { name: 'Retry' }),
        `${region} must offer a Retry`,
      ).toBeInTheDocument();
    }

    // …and the Build tab, which reads none of `/api/runtime/records`, is whole.
    cleanup();
    renderStatisticsBuild(statisticsRoutes({ records: dead }));
    await settled();
    expect(figureValue('Project Memory', 'Nodes')).toBe(String(graphStatusAvailable.node_count));
    expect(figureValue('API Surface', 'Documented Operations')).toBe(OPERATION_COUNT);
    // The two runtime cards read /api/about, which is still alive.
    expect(cardValue('Runtime', 'Runtime Mode')).toBe('Synthetic-Only');
  });

  /*
   * THE SIXTH SOURCE, ADDED WITH THE HISTORICAL IMPORTS FIGURES. It is the
   * mirror of the case above and exists for the same reason: a new read must
   * degrade only what reads it, and its tile must not print `0`.
   */
  it('imports down — every record figure still renders, and the tile states the absence', async () => {
    renderStatistics(statisticsRoutes({ imports: dead }));
    await settled();

    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    // NOT `0`, which would claim the workspace holds no import session.
    expect(cardValue('Workspace at a Glance', 'Historical Imports')).toBe(UNAVAILABLE);
    const tile = within(regionOf('Workspace at a Glance'))
      .getByText('Historical Imports')
      .closest('dl.stat-card');
    expect(tile?.getAttribute('data-tone')).toBe('quiet');

    // One alarm, at the section that reads it, with the recourse.
    const section = regionOf('Historical Imports');
    expect(within(section).getAllByRole('alert')).toHaveLength(1);
    expect(within(section).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.getAllByRole('alert')).toHaveLength(1);
  });

  it('about down — the record cards still render', async () => {
    renderStatistics(statisticsRoutes({ about: dead }));
    await settled();

    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(cardValue('Workspace at a Glance', 'Needs Attention')).toBe('2');

    cleanup();
    renderStatisticsBuild(statisticsRoutes({ about: dead }));
    await settled();
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

    cleanup();
    renderStatisticsBuild(statisticsRoutes({ graph: dead }));
    await settled();
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

    cleanup();
    renderStatisticsBuild(statisticsRoutes({ openapi: dead }));
    await settled();
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
  /*
   * ASSERTED PER TAB SINCE 2026-09-15, and the rule is UNCHANGED — which is the
   * reason this case is split rather than loosened. `once per dead source` was
   * always a claim about the sections that READ a source, and the sections that
   * read records are now on one tab while the sections that read the graph and
   * the contract are on another. A single-tab count would be a different
   * assertion wearing the same name: it would pass while a source alarmed twice
   * on the tab it was not measured on.
   */
  it('alarms ONCE PER DEAD SOURCE — not once per section, and not once per tab', async () => {
    renderStatistics(statisticsRoutes({ records: dead, graph: dead, openapi: dead }));
    await settled();

    // On Overview exactly ONE source is read of the three that are dead, so
    // exactly one alarm — not one per reading section (records is read by five).
    expect(screen.getAllByRole('alert')).toHaveLength(1);

    // The records alarm is at the FIRST section that reads records; every other
    // section reading it gets the compact, neutral note instead.
    expect(within(regionOf('Workspace at a Glance')).getByRole('alert')).toBeInTheDocument();
    for (const region of [
      'Workflow Distribution',
      'Open Questions',
      'Evidence and Validation',
      'Recent Work',
    ]) {
      expect(within(regionOf(region)).queryByRole('alert'), `${region} must not re-alarm`).toBeNull();
      expect(regionOf(region).querySelector('.stats-unavailable')).not.toBeNull();
    }

    // Every affected section still offers the recourse.
    for (const region of [
      'Workspace at a Glance',
      'Workflow Distribution',
      'Open Questions',
      'Evidence and Validation',
      'Recent Work',
    ]) {
      expect(
        within(regionOf(region)).getAllByRole('button', { name: 'Retry' }).length,
      ).toBeGreaterThan(0);
    }

    // On Build the other two dead sources each have a single reader, so each
    // alarms there exactly once — two alarms, not one and not three.
    cleanup();
    renderStatisticsBuild(statisticsRoutes({ records: dead, graph: dead, openapi: dead }));
    await settled();
    expect(screen.getAllByRole('alert')).toHaveLength(2);
    expect(within(regionOf('Project Memory')).getAllByRole('alert')).toHaveLength(1);
    expect(within(regionOf('API Surface')).getAllByRole('alert')).toHaveLength(1);
    for (const region of ['Project Memory', 'API Surface']) {
      expect(
        within(regionOf(region)).getAllByRole('button', { name: 'Retry' }).length,
      ).toBeGreaterThan(0);
    }
  });

  it('a dead /api/about alarms nowhere — it degrades two cards and nothing else', async () => {
    renderStatisticsBuild(statisticsRoutes({ about: dead }));
    await settled();

    // The quiet exception: no alarm anywhere on this tab for this source.
    expect(screen.queryAllByRole('alert')).toHaveLength(0);
    const runtime = regionOf('Runtime');
    expect(runtime.querySelector('.stats-unavailable')).not.toBeNull();
    expect(within(runtime).getByRole('button', { name: 'Retry' })).toBeInTheDocument();

    // …and the record cards on the Overview tab are unaffected, and alarm-free.
    cleanup();
    renderStatistics(statisticsRoutes({ about: dead }));
    await settled();
    expect(screen.queryAllByRole('alert')).toHaveLength(0);
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
    // section holds NO card at all in this state — including the two tiles added
    // in 2026-09-15 (`Open Questions`, `Historical Imports`), which are inside
    // the same grid and so are absent with it. A zero here would be a figure
    // nobody measured.
    expect(regionOf('Workspace at a Glance').querySelectorAll('dl.stat-card')).toHaveLength(0);
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
    // The new sections state the absence too, and neither draws a zero row.
    expect(
      within(regionOf('Recent Work')).getByText(/No records were returned, so there is nothing recent to list\./),
    ).toBeInTheDocument();
    expect(regionOf('Recent Work').querySelectorAll('.stats-recent-row')).toHaveLength(0);

    // …and the two /api/about cards it used to keep are in the `Runtime` region
    // on the Build tab, which still has them: the move is real, not a deletion.
    cleanup();
    renderStatisticsBuild(statisticsRoutes({ records: { body: { records: [], total: 0 } } }));
    await settled();
    expect(regionOf('Runtime').querySelectorAll('dl.stat-card')).toHaveLength(2);
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
    /*
     * SCOPED TO THE GLANCE REGION, not to the first `.stats-cards` on the page.
     *
     * It used to be `container.querySelector('.statistics .stats-cards')`, which
     * was the glance grid ONLY because that section happened to be first. Record
     * Verification now opens the tab and draws its own four-card KPI row, so the
     * unscoped query resolves to a grid this caveat says nothing about.
     *
     * BE PRECISE ABOUT WHAT THAT DID, because an earlier version of this comment
     * was not, and a review caught it. It claimed the stale assertion was "both
     * true and worthless" — i.e. that the rescope merely tightened something
     * already passing. That is FALSE and the flattering version of events. The
     * Record Verification grid renders BEFORE this caveat, so
     * `note.compareDocumentPosition(rvGrid) & DOCUMENT_POSITION_FOLLOWING` is 0:
     * the old assertion would have gone RED, and the rescope was REQUIRED to make
     * the reorganisation pass.
     *
     * That distinction is the whole point of writing these comments. "I tightened
     * a weak assertion" and "I changed an assertion that my change broke" carry
     * very different burdens of proof, and only the second one obliges the author
     * to show the new assertion is as strong as the old. It is: the old form
     * pinned the caveat against whichever grid came first, which after this
     * change is a grid in another section; this form pins it against the grid it
     * actually qualifies, resolved from the same region.
     */
    const grid = regionOf('Workspace at a Glance').querySelector('.stats-cards');
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
    for (const label of ['Needs Attention', 'Ready to Export', 'Exported']) {
      expect(within(grid as HTMLElement).getByText(label)).toBeInTheDocument();
    }
  });
});

// --- Refresh ------------------------------------------------------------------

describe('Refresh', () => {
  const refreshButton = () => screen.getByRole('button', { name: 'Refresh' });

  /*
   * ~~five~~ SIX tracked GETs since 2026-09-15: `GET /api/imports` joined them
   * with the Historical Imports figures. The COUNTS are read from
   * `STATISTICS_ROUTE_KEYS.length` rather than restated as literals, which is
   * the change that matters here — the previous version hard-coded `6` and `5`,
   * so adding a read made this test fail with an arithmetic message instead of
   * telling anyone which read was new.
   *
   * THE DESIGN THIS PINS IS UNCHANGED: the verification read is NOT re-issued
   * by Refresh, whatever the tracked count is.
   */
  it('re-issues EXACTLY the tracked GETs, and does NOT re-read verification', async () => {
    const { calls } = renderStatistics(statisticsRoutes());
    await settled();

    // On mount: every tracked read plus Record Verification's untracked one.
    expect([...calls].sort()).toEqual(
      [...STATISTICS_ROUTE_KEYS, STATISTICS_VERIFICATION_ROUTE_KEY].sort(),
    );
    const afterLoad = calls.length;
    expect(afterLoad).toBe(STATISTICS_ROUTE_KEYS.length + 1);

    fireEvent.click(refreshButton());
    // The tracked reads, and NOT the verification one. This is the assertion
    // that pins the design: the verification report is a cached artifact of a
    // program run that states its own age, not a live view of this workspace,
    // so Refresh leaves it alone. Re-reading it here would also make the
    // "N of M reads failed" notice describe a denominator it does not count.
    await waitFor(() => expect(calls.length).toBe(afterLoad + STATISTICS_ROUTE_KEYS.length));

    expect(calls.slice(afterLoad).sort()).toEqual([...STATISTICS_ROUTE_KEYS].sort());
    expect(calls.slice(afterLoad)).not.toContain(STATISTICS_VERIFICATION_ROUTE_KEY);
    // Nothing outside the six, in either round.
    const allowed = [...STATISTICS_ROUTE_KEYS, STATISTICS_VERIFICATION_ROUTE_KEY];
    for (const key of calls) expect(allowed).toContain(key);
  });

  it('issues no POST, PUT, PATCH or DELETE — the page mutates nothing', async () => {
    const { calls } = renderStatistics(statisticsRoutes());
    await settled();

    fireEvent.click(refreshButton());
    // Every tracked read plus verification on mount, then the tracked reads
    // again. Derived, not a literal — see the test above.
    await waitFor(() =>
      expect(calls.length).toBe(STATISTICS_ROUTE_KEYS.length * 2 + 1),
    );

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
  it('a Refresh where ONE of the tracked reads fails says so, and never reads as a clean success', async () => {
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
      /^Refresh finished, but 1 of 7 reads failed — the figures shown were last read at /,
    );
    expect(live?.textContent).not.toMatch(/^Refresh finished\. The page last read the API at/);

    // Stated on SCREEN as well, not only to a screen reader.
    expect(screen.getByText(/1 of 7 reads failed on the most recent attempt/)).toBeInTheDocument();
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

  it('a Refresh where ALL SEVEN reads fail leaves the timestamp at the last successful read', async () => {
    const allSevenOnce = {
      'GET /api/runtime/records': firstCallOnly(statisticsRecordsBody),
      'GET /api/graph/status': firstCallOnly(graphStatusAvailable),
      'GET /api/about': firstCallOnly(aboutResponse),
      'GET /api/openapi': firstCallOnly(openApiFixture),
      /* ALL of them, which the title always claimed and the fixture did not
         supply: `/api/schema` had no route here, so it failed on the INITIAL
         load too and this was really "four succeeded then five failed". It
         passed the no-alarm assertion below only because a dead `/api/schema`
         used to render a note with no `role` — the very defect that slice
         fixed. `/api/imports` is the sixth, added 2026-09-15, and it is here
         for exactly the same reason: without it the round would be 5→6 and
         one section would never have had data to keep. `/api/activity/summary`
         is the SEVENTH, added 2026-09-18 with `ACT-004`, and it is here for the
         same reason a third time: the round's denominator is COUNTED, so a read
         missing from this map would make the sentence below describe a smaller
         round than the page actually ran. */
      'GET /api/schema': firstCallOnly(schemaBrowserFixture),
      'GET /api/imports': firstCallOnly(importListFixture),
      'GET /api/activity/summary': firstCallOnly(activitySummaryFixture),
    };
    const { container } = renderStatistics(allSevenOnce);
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
      /^Refresh finished, but 7 of 7 reads failed — the figures shown were last read at /,
    );
    expect(live?.textContent).not.toContain('The page last read the API at');

    // The clock did not move: the same instant as the load, and strictly earlier
    // than the moment Refresh was pressed.
    expect(metaTime(container).dateTime).toBe(loadedAt);
    expect(new Date(loadedAt).getTime()).toBeLessThan(clickedAt);
    expect(metaLabel(container)).toBe('Last Read From the API');

    // Stated on screen, once, as information rather than as an alert.
    expect(screen.getByText(/7 of 7 reads failed on the most recent attempt/)).toBeInTheDocument();
    expect(screen.queryAllByRole('alert')).toHaveLength(0);

    // Every figure is still the one that was actually read, unchanged and
    // un-substituted — the page keeps its data instead of blanking.
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(figureValue('Historical Imports', 'Import Sessions')).toBe('2');

    // Still the same live region, with the failure note mounted above it.
    expect(container.querySelector('p.sr-only[role="status"]')).toBe(live);

    /* THE BUILD TAB'S FIGURES ARE CHECKED ON THE BUILD TAB, in a second round
       with its own `firstCallOnly` routes — a fresh pair, because those thunks
       are stateful and the ones above are already spent. This is what keeps
       "every section kept its data" meaning that, rather than "the sections I
       could still see kept theirs". */
    cleanup();
    const build = renderStatisticsBuild({
      'GET /api/runtime/records': firstCallOnly(statisticsRecordsBody),
      'GET /api/graph/status': firstCallOnly(graphStatusAvailable),
      'GET /api/about': firstCallOnly(aboutResponse),
      'GET /api/openapi': firstCallOnly(openApiFixture),
      'GET /api/schema': firstCallOnly(schemaBrowserFixture),
      'GET /api/imports': firstCallOnly(importListFixture),
      'GET /api/activity/summary': firstCallOnly(activitySummaryFixture),
    });
    await settled();
    fireEvent.click(refreshButton());
    await waitFor(() =>
      expect(
        build.container.querySelector('p.sr-only[role="status"]')?.textContent ?? '',
      ).toMatch(/^Refresh finished, but 7 of 7 reads failed/),
    );
    expect(figureValue('API Surface', 'Documented Operations')).toBe(OPERATION_COUNT);
    expect(figureValue('Project Memory', 'Nodes')).toBe(String(graphStatusAvailable.node_count));
    expect(figureValue('Record Schema', 'Top-Level Fields')).toBe('6');
    expect(screen.queryAllByRole('alert')).toHaveLength(0);
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
  /*
   * ══ THIS GUARD WAS NARROWED ON 2026-09-15, DELIBERATELY, AND THE SCOPE IT
   *    LOST IS NAMED HERE RATHER THAN QUIETLY DROPPED ═══════════════════════
   *
   * WHAT IT USED TO ASSERT: that NO record title, experiment id or record route
   * appeared anywhere on the Statistics page. `Recent Work` renders exactly
   * those three — a record's title, linked to its own route, which contains its
   * id — so that clause is no longer true of the page and could not be left
   * standing.
   *
   * WHY THE NARROWING IS DEFENSIBLE, stated as an argument rather than as a
   * convenience:
   *
   *   1. THERE IS NO ACCESS BOUNDARY BEING CROSSED. This build has no trusted
   *      user identity and no per-record ownership, so there is no reader who
   *      may see the count but not the name. The three fields come from the SAME
   *      safe projection (`runtime_records.py`), by the same route, to the same
   *      reader, and are ALREADY rendered by My Experiments, the search dialog
   *      and the cross-record triage chips (`lib/crossRecordTriage.ts` puts
   *      `title` and `navigate_to` into every `TriageMatch`).
   *   2. NO USER-FACING CLAIM BECOMES FALSE. Nothing this page renders promises
   *      that no record is named. `Open Questions` promises that no question
   *      text, field name or answer is read — still true, and still asserted, in
   *      its own section. `Record Verification` promises that no individual
   *      record of the verification CORPUS is named — a different set, on a
   *      different tab, unchanged.
   *   3. THE PART THAT PROTECTED SOMETHING IS KEPT AND STRENGTHENED. What the
   *      old clause really guarded was that a per-record VALUE never leaks into
   *      a page of aggregates. That is asserted below, unchanged in strength,
   *      with the scientific-vocabulary scan kept — plus a new positive
   *      assertion that `Recent Work` renders ONLY a title, a status word and a
   *      time, and nothing else about a record.
   *
   * THE AGGREGATE SECTIONS ARE STILL SCANNED WHOLE. The exclusion is exactly
   * `.stats-recent`, so a title appearing in the glance grid, a chart, a figure
   * list or a caveat still fails — which is the leak this guard was written for.
   */
  it('renders no address, no credential, and no record content outside Recent Work', async () => {
    const { container } = renderStatistics(statisticsRoutes());
    await settled();
    const text = pageText(container);
    const aggregates = pageTextWithout(container, '.stats-recent');

    expect(text).not.toMatch(/\b\d{1,3}(\.\d{1,3}){3}\b/); // no IP-shaped string
    expect(text).not.toMatch(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/); // no email
    expect(text).not.toMatch(/@/); // and no bare @-token at all

    for (const secret of ['Bearer', 'authorization', 'cookie', 'token', 'secret']) {
      expect(new RegExp(secret, 'i').test(text), `"${secret}" appeared`).toBe(false);
    }

    /*
     * ── `session` IS SPLIT IN TWO, AND THE CREDENTIAL HALF IS STRONGER ─────
     *
     * The bare word `session` used to be banned page-wide with the five terms
     * above. `Historical Imports` counts IMPORT SESSIONS — the API's own noun
     * for a working area (`GET /api/imports`, `POST /api/imports`), the word
     * the Historical Import screen uses, and a word that has nothing to do
     * with a credential. Banning it page-wide would force a fifth vocabulary
     * for one concept, which is a worse outcome than scoping the ban.
     *
     * So it is asserted as TWO claims, and the first is strictly stronger than
     * the bare word it replaces: no credential-SHAPED session reference
     * anywhere at all, and no bare `session` in any phrase other than
     * `import session(s)`. A session id, token, key, cookie or header now
     * fails even inside the Historical Imports section, which the old
     * bare-word ban would have caught only by accident of wording.
     *
     * THE EXEMPTION IS TWO NAMED SELECTORS, and two earlier attempts at it are
     * recorded because each looked right and was not. Scoping it to the
     * Historical Imports region alone missed the glance tile, which carries
     * the noun in its own note (`import sessions — working areas, never
     * records`) — a caveat that must stay beside the figure. Exempting the
     * PHRASE `import session(s)` missed the section's own figure labels
     * (`Sessions With a Source Recorded`) and its closing caveat (`These count
     * SESSIONS, never records`), which use the bare noun correctly.
     *
     * So the two places that legitimately render the noun are named, and
     * everywhere else still fails on the bare word. Adding the noun to a third
     * place is what this guard now catches — which is the right thing for it to
     * catch, because a credential would not arrive labelled `Import Sessions`.
     */
    expect(
      /session[\s_-]*(id|ids|token|tokens|key|keys|cookie|header)/i.test(text),
      'a credential-shaped session reference appeared',
    ).toBe(false);
    const SESSION_NOUN_HOMES = 'section[aria-labelledby="stats-imports"], .stats-cards-glance';
    expect(
      /\bsession/i.test(pageTextWithout(container, SESSION_NOUN_HOMES)),
      '"session" appeared outside the two places that render the import-session noun',
    ).toBe(false);
    /* The negative control: the exemption is not vacuous — the noun really is
       rendered in both of the exempted homes, so an empty exclusion would be
       caught rather than read as a clean pass. */
    expect(/\bimport sessions?\b/i.test(textOf(regionOf('Historical Imports')))).toBe(true);
    expect(
      /\bimport sessions?\b/i.test(textOf(container.querySelector('.stats-cards-glance') as HTMLElement)),
    ).toBe(true);

    // No record content in the AGGREGATE sections: not a title, not an id, not
    // a per-record value. This is the clause the narrowing scopes, and the
    // scope is one selector rather than a loosened pattern.
    for (const record of statisticsRuntimeRecords) {
      expect(aggregates).not.toContain(record.title);
      expect(aggregates).not.toContain(record.experiment_id);
      expect(aggregates).not.toContain(record.navigate_to);
    }
    // Scientific vocabulary is forbidden EVERYWHERE, Recent Work included: a
    // title is a name the reader gave, a value is a measurement.
    expect(text).not.toMatch(/CuO|K-edge|\.xdi/);

    /* The positive half. Recent Work renders a title, a status word and a time,
       and nothing else about a record — no pending count, no evidence class, no
       revision, no artifact state, no export verdict. Asserted as an allowlist
       over each row's own text, so a field added to the row fails here. */
    const rows = [...container.querySelectorAll('.stats-recent-row')];
    expect(rows.length, 'no Recent Work row rendered, so this asserts nothing').toBeGreaterThan(0);
    for (const row of rows) {
      const title = row.querySelector('.stats-recent-title')?.textContent ?? '';
      const state = row.querySelector('.stats-recent-state')?.textContent ?? '';
      const when = row.querySelector('.stats-recent-when')?.textContent ?? '';
      expect(textOf(row as HTMLElement)).toBe([title, state, when].join(' ').trim());
    }
  });

  /*
   * THE PROVENANCE STRING THE OLD CASE ALLOWED, kept and moved to the tab that
   * renders it. `ab12cd34ef567890` is a git commit SHA, not identifying
   * content, and the old case asserted its PRESENCE as a positive control that
   * the scan was reading a rendered page. That control is worth keeping, so it
   * is asserted where the commit now is rather than deleted with the tab split.
   */
  it('the allowed provenance string still renders, on the tab that states it', async () => {
    const { container } = renderStatisticsBuild(statisticsRoutes());
    await settled();

    expect(pageText(container)).toMatch(/ab12cd34ef567890/);
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

  /*
   * ── THE CAVEAT IS NOW IN TWO PLACES, AND BOTH ARE ASSERTED ───────────────
   *
   * The 2026-09-15 distillation left the OPERATIVE sentence visible and moved
   * the restatement into a disclosure. This case is widened rather than
   * re-pointed, and the widening is the point: it asserts (a) that the
   * non-addability caveat is readable WITHOUT opening anything, because a
   * caveat behind a `<summary>` leaves the visible figures reading as
   * complete, and (b) that the full explanation is still present, verbatim,
   * one activation away. Dropping either half would let the next distillation
   * hide the caveat entirely and still pass.
   *
   * ~~'counts QUESTIONS across the 5 records received'~~ — the disclosure
   * deliberately no longer carries that FIGURE, because a closed `<details>` is
   * not scanned by axe and is skipped by a reader, so a measurement inside one
   * is a hidden measurement (the rule `puts NO measurement inside a prose
   * disclosure` enforces). The unit claim survives without the number.
   */
  it('keeps the non-addability caveat VISIBLE, with the full explanation disclosed', async () => {
    renderStatistics(statisticsRoutes());
    await settled();

    const region = regionOf('Open Questions');
    const disclosure = region.querySelector('details.stats-disclosure');
    expect(disclosure, 'the reading-rules disclosure must render').not.toBeNull();
    expect(disclosure!.hasAttribute('open'), 'it must arrive closed').toBe(false);

    // (a) the operative caveat, outside the disclosure — read from a clone with
    // the disclosure removed, so this cannot pass on the disclosed copy.
    const visible = pageTextWithout(region, 'details.stats-disclosure');
    expect(visible).toMatch(/Total Open Questions counts QUESTIONS; the other four count RECORDS/);
    expect(visible).toMatch(/None of the five may be added together/);

    // (b) the full explanation, inside it, unchanged.
    const disclosed = textOf(disclosure as HTMLElement);
    expect(disclosed).toMatch(/counts QUESTIONS across the records received/);
    /* The three record-counting rows are NAMED rather than referred to by
       position: "the three beneath it" was true and unreadable, because a
       maximum sits among them. */
    expect(disclosed).toMatch(
      /Records With Open Questions, Records With a Blocked Step and Records With a Reopened Step count RECORDS/,
    );
    expect(disclosed).toMatch(/Most on One Record is the largest single record’s question count/);
    expect(disclosed).toMatch(/none of these five may be added together/);
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
    renderStatisticsBuild(statisticsRoutes());
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

  /*
   * THIS ASSERTION USED TO PIN THE RAW PROPERTY NAMES — `isaac_record_version`,
   * `record_id`, `record_type` — as the visible chart labels, and so it pinned
   * the defect rather than the intent. Those tokens rendered in the PROSE face,
   * under a column headed "Section", and were read out verbatim in the chart's
   * `sr-only` summary sentence.
   *
   * `SCHEMA_SECTION_LABELS` maps them for display only. The wire/model value is
   * unchanged: `SchemaSectionCount.section` still carries the property name
   * verbatim, it is still the row `key`, the Schema Reference browser still
   * shows the exact token in the mono face, and an unmapped property still falls
   * back to its own name rather than to an invented phrase.
   *
   * THE ORDER IS THE POINT OF THIS TEST AND IS UNCHANGED — declaration order,
   * not alphabetical, not by count.
   */
  it('breaks the fields down by section, in the document\'s own order', async () => {
    renderStatisticsBuild(statisticsRoutes());
    await settled();

    expect(
      chartRows('Record Schema', "Fields by top-level section, in the schema's own declaration order"),
    ).toEqual([
      ['ISAAC Record Version', '1'],
      ['Record Identifier', '1'],
      ['Record Type', '1'],
      ['Descriptors', '4'],
      ['Sample', '4'],
      ['Tags', '1'],
    ]);
  });

  it('qualifies what "required" means and what the term count is a property of', async () => {
    renderStatisticsBuild(statisticsRoutes());
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
    renderStatisticsBuild(statisticsRoutes());
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
    renderStatisticsBuild(statisticsRoutes());
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
    renderStatisticsBuild(statisticsRoutes({ schema: { status: 500, body: { detail: 'synthetic failure' } } }));
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

    // Everything else on this tab still renders...
    expect(figureValue('API Surface', 'Documented Operations')).toBe(OPERATION_COUNT);
    // ...and the Overview tab, which reads none of `/api/schema`, is untouched
    // and alarm-free.
    cleanup();
    renderStatistics(statisticsRoutes({ schema: { status: 500, body: { detail: 'synthetic failure' } } }));
    await settled();
    expect(cardValue('Workspace at a Glance', 'Total Records')).toBe(String(RECORD_COUNT));
    expect(screen.queryAllByRole('alert')).toHaveLength(0);
  });
});

describe('Platform Metrics — the inactive adapter boundary', () => {
  it('states that it is not connected, and states no figure at all', async () => {
    renderStatisticsBuild(statisticsRoutes());
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
    renderStatisticsBuild(statisticsRoutes());
    await settled();

    const text = textOf(regionOf('Platform Metrics'));
    expect(text).toMatch(/Nothing is being hidden and no figure is zero/);
    expect(text).toMatch(/this application has no source to read one from/);
    // It must not blame a decision, a permission, or a person.
    expect(text).not.toMatch(/permission|denied|governance|approval|administrator|Dean/i);
  });

  it('lists the six planned views, each naming what it would count', async () => {
    renderStatisticsBuild(statisticsRoutes());
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

  it('adds NO request to the page — the mount reads are unchanged by its presence', async () => {
    const { calls } = renderStatisticsBuild(statisticsRoutes());
    await settled();

    // The five tracked reads plus Record Verification's, and nothing else. The
    // verification read belongs to a different section; it is listed here so the
    // set stays EXACT rather than being relaxed to a subset check.
    expect([...calls].sort()).toEqual(
      [...STATISTICS_ROUTE_KEYS, STATISTICS_VERIFICATION_ROUTE_KEY].sort(),
    );
    expect(calls.filter((c) => /portal|metrics|platform/i.test(c))).toEqual([]);
  });

  it('draws no chart, no axis and no empty plot', async () => {
    renderStatisticsBuild(statisticsRoutes());
    await settled();

    const panel = regionOf('Platform Metrics');
    expect(panel.querySelector('figure.stats-chart')).toBeNull();
    expect(panel.querySelector('.stats-chart-track')).toBeNull();
    expect(panel.querySelector('.stats-chart-grid')).toBeNull();
  });
});

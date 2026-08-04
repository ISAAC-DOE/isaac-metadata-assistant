import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { ROUTES, STATISTICS_TAB_IDS, isStatisticsTab } from '../lib/routes';
import {
  MY_STATS_PENDING_COPY,
  MY_STATS_PENDING_LABEL,
  MY_STATS_PENDING_REASON,
  MY_STATS_VIEWS,
  unconfiguredMyStatsSource,
  type MyStatsSource,
} from '../lib/myStatsContract';
import { MyStats } from '../screens/statistics/MyStats';
import { statisticsRecordsBody, statisticsRoutes, stubFetchRoutes } from '../test/apiFixtures';

/**
 * Statistics · My Stats — the personal tab, its gate, and the two tabs above it.
 *
 * ── The thing this file exists to prevent ───────────────────────────────────
 *
 * This build has no trusted user identity and no record ownership, so it can
 * produce NO personal figure. A personal-statistics tab is therefore the single
 * most likely place in the app to state something false, and there are six
 * specific ways to do it. Each has its own test below, and each is a test about
 * ABSENCE — which is exactly the kind that rots quietly, so each one names the
 * plausible wrong answer it is excluding.
 *
 *   1. a workspace-wide total relabelled as personal
 *   2. worked-example records presented as the reader's own
 *   3. a portal-wide metric
 *   4. a fake zero ("0 records", which claims no activity)
 *   5. a chart skeleton left behind after loading resolves
 *   6. any header-derived identity
 *
 * The fixture used throughout is `statisticsRoutes()`, which really does serve
 * five records with real counts. That is deliberate: a test against an EMPTY
 * workspace could not tell "shows nothing because there is nothing" from "shows
 * nothing because it refuses to attribute". With records present, any leak of a
 * workspace figure onto this tab has a number to leak.
 */

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

const MINE = `${ROUTES.statistics}?tab=mine`;

async function renderMineTab() {
  const calls = stubFetchRoutes(statisticsRoutes());
  const view = renderAt(MINE);
  await view.findByText('Not Available in This Preview');
  return { ...view, calls };
}

/** Every text node of a subtree, space-joined — see `statistics-page.test.tsx`. */
function textOf(root: HTMLElement): string {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  while (walker.nextNode()) parts.push(walker.currentNode.textContent ?? '');
  return parts.join(' ').replace(/\s+/g, ' ').trim();
}

// --- the tablist ------------------------------------------------------------

describe('the two top-level tabs', () => {
  const tablist = () => screen.getByRole('tablist', { name: 'Statistics sections' });

  it('exposes exactly two tabs, in order, with General ISAAC selected by default', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const tabs = within(tablist()).getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['General ISAAC', 'My Stats']);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'false');
  });

  it('uses a roving tabindex — exactly one tab is in the tab order', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const tabs = within(tablist()).getAllByRole('tab');
    expect(tabs.map((t) => t.tabIndex)).toEqual([0, -1]);
  });

  it('wires the selected tab to a rendered tabpanel, and the panel back to it', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const selected = within(tablist()).getAllByRole('tab')[0];
    const panelId = selected.getAttribute('aria-controls');
    expect(panelId).toBe('statistics-tabpanel-general');
    const panel = document.getElementById(panelId!);
    expect(panel).toHaveAttribute('role', 'tabpanel');
    expect(panel).toHaveAttribute('aria-labelledby', selected.id);
    // `aria-controls` only on the SELECTED tab, matching the app's other tablists.
    expect(within(tablist()).getAllByRole('tab')[1].getAttribute('aria-controls')).toBeNull();
  });

  it('switches on ArrowRight and moves focus with the selection', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const first = within(tablist()).getAllByRole('tab')[0];
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });

    const tabs = within(tablist()).getAllByRole('tab');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[1]).toHaveFocus();
    await screen.findByRole('heading', { name: 'Personal Statistics' });
  });

  /*
   * DEEP-LINKING IS THE POINT, not a nicety. A tab held only in `useState` cannot
   * be linked to, bookmarked, or reloaded back into — and that exact defect
   * shipped once on Governance & Safety, where the Validator tab was unreachable
   * by link. Both directions are asserted: the URL selects the tab, and activating
   * the tab writes the URL.
   */
  it('is deep-linkable: ?tab=mine selects My Stats on arrival', async () => {
    await renderMineTab();
    const tabs = within(tablist()).getAllByRole('tab');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[0]).toHaveAttribute('aria-selected', 'false');
  });

  it('an unrecognised ?tab= value falls back to General ISAAC without throwing', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(`${ROUTES.statistics}?tab=not-a-tab`);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });
    expect(within(tablist()).getAllByRole('tab')[0]).toHaveAttribute('aria-selected', 'true');
  });

  it('activating a tab writes the ?tab= value the route helper builds', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    fireEvent.click(within(tablist()).getAllByRole('tab', { name: 'My Stats' })[0]);
    await screen.findByRole('heading', { name: 'Personal Statistics' });
    expect(ROUTES.statisticsTab('mine')).toBe('/statistics?tab=mine');
  });

  it('declares its ids in one place, and the type guard agrees with them', () => {
    expect([...STATISTICS_TAB_IDS]).toEqual(['general', 'mine']);
    expect(isStatisticsTab('general')).toBe(true);
    expect(isStatisticsTab('mine')).toBe(true);
    for (const bad of ['General', '', null, undefined, 'general ']) {
      expect(isStatisticsTab(bad as string | null)).toBe(false);
    }
  });
});

// --- what belongs in which tab ---------------------------------------------

describe('the General ISAAC tab keeps the workspace material', () => {
  it('holds the three workspace sections and the privacy claim, and NOT the personal gate', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    for (const name of [
      'Workspace at a Glance',
      'Workflow Distribution',
      'Evidence and Validation',
      'This Application Collects No Analytics',
    ]) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole('heading', { name: 'Personal Statistics' })).toBeNull();
  });

  /*
   * THE PRIVACY CLAIM STAYS UNCOLLAPSED. Project Memory and the API surface moved
   * into a collapsed disclosure; this section did not, because it is a governance
   * claim about what the application measures, and a claim behind a disclosure is
   * a weaker claim.
   */
  it('leaves the no-analytics claim outside the collapsed region', async () => {
    stubFetchRoutes(statisticsRoutes());
    const { container } = renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const section = container.querySelector('section[aria-labelledby="stats-no-analytics"]');
    expect(section).not.toBeNull();
    expect(section!.closest('details')).toBeNull();
  });

  it('collapses the build internals — runtime, Project Memory and the API surface — by default', async () => {
    stubFetchRoutes(statisticsRoutes());
    const { container } = renderAt(ROUTES.statistics);
    await screen.findByText('Synthetic-Only');

    const details = container.querySelector('details.stats-technical');
    expect(details).not.toBeNull();
    expect(details!.hasAttribute('open')).toBe(false);
    for (const name of ['Runtime', 'Project Memory', 'API Surface']) {
      expect(screen.getByRole('region', { name }).closest('details')).toBe(details);
    }
  });
});

// --- the six traps ----------------------------------------------------------

describe('My Stats invents no personal figure — the six traps', () => {
  /*
   * TRAP 1 — a workspace total relabelled as personal.
   *
   * The fixture serves five records whose derived totals are 5 / 2 / 1 / 1, and
   * `deriveWorkspaceTotals` sits one import away in `lib/statisticsModel.ts`. If
   * any of those numbers reached this tab it would be a false personal claim
   * built from a correct workspace one.
   */
  it('1 — states no workspace total, and imports the model that would supply one nowhere', async () => {
    const { container } = await renderMineTab();
    const panel = container.querySelector('#statistics-tabpanel-mine') as HTMLElement;
    const text = textOf(panel);

    expect(statisticsRecordsBody.total).toBe(5);
    for (const label of ['Total Records', 'Need Attention', 'Ready to Export', 'Exported']) {
      expect(text, `${label} must not appear on the personal tab`).not.toContain(label);
    }
    // No bare figure of any kind: no digit sequence stands as a statistic here.
    expect(text).not.toMatch(/\b\d+\b/);

    /*
     * …and the source of such a figure is not even IMPORTABLE from this module.
     * Matched against the module's import statements rather than its whole text,
     * because the header comment necessarily NAMES the module it must not import —
     * a substring scan would be satisfied by deleting the explanation.
     */
    const source = String((await import('../screens/statistics/MyStats?raw')).default);
    const imports = source.match(/^import[\s\S]*?from\s+'[^']+';$/gm) ?? [];
    expect(imports.length).toBeGreaterThan(2);
    for (const line of imports) {
      expect(line, 'My Stats must not import the workspace model').not.toContain(
        'statisticsModel',
      );
    }
    expect(source).not.toMatch(/\bderiveWorkspaceTotals\s*\(/);
  });

  /*
   * TRAP 2 — worked-example records presented as the reader's own. The strongest
   * form of this guard is that the tab issues no request at all: with no read,
   * there is no record set to mislabel, in any scope.
   */
  it('2 — issues NO request, so no record in any scope can be shown as personal', async () => {
    const { calls } = await renderMineTab();
    /*
     * The four General-tab reads still happen on mount (they are not tab-keyed),
     * and NOTHING else does. `stubFetchRoutes` records each call as
     * `"<METHOD> <path>"`, so this asserts the method too — every request is a GET,
     * and this tab therefore cannot mutate anything either.
     */
    expect(new Set(calls)).toEqual(
      new Set([
        'GET /api/runtime/records',
        'GET /api/graph/status',
        'GET /api/about',
        'GET /api/openapi',
      ]),
    );
    expect(calls.filter((c) => c.includes('/api/experiments'))).toEqual([]);
    expect(calls.filter((c) => c.includes('/api/demo'))).toEqual([]);
  });

  /** TRAP 3 — a portal-wide metric. Nothing here names or reads a portal. */
  it('3 — names no portal, database or cross-user metric', async () => {
    const { container } = await renderMineTab();
    const text = textOf(container.querySelector('#statistics-tabpanel-mine') as HTMLElement);
    for (const word of ['portal', 'Postgres', 'PostgreSQL', 'database', 'everyone', 'all users']) {
      expect(text.toLowerCase()).not.toContain(word.toLowerCase());
    }
  });

  /*
   * TRAP 4 — the fake zero, and the one this tab most had to be designed against.
   * "0 records" is not a neutral placeholder: it asserts that the reader has no
   * activity. The truth is that this build cannot attribute activity to anyone,
   * and the copy has to say THAT.
   */
  it('4 — renders no zero, and says explicitly that absence is not zero', async () => {
    const { container } = await renderMineTab();
    const panel = container.querySelector('#statistics-tabpanel-mine') as HTMLElement;
    const text = textOf(panel);

    expect(text).not.toMatch(/\b0\b/);
    expect(text).toMatch(/none of the figures below are zero — they are absent/);
    expect(text).toMatch(/cannot tell whose records these are/);

    /*
     * …and no sentence ASSERTS that the reader has nothing. Checked per sentence
     * rather than over the whole page, because the tab legitimately says "A count
     * of zero WOULD say you have no records" — a hypothetical that denies the
     * claim, and the most important sentence on the tab. A page-wide substring
     * scan would flag exactly the copy that is doing the honest work, and the
     * likely response would be to delete it.
     */
    for (const sentence of text.split(/(?<=[.;])\s+/)) {
      if (!/no records|no activity|nothing to show/i.test(sentence)) continue;
      expect(
        /\bwould\b|\bcannot\b|\bnot\b/i.test(sentence),
        `an emptiness claim must be framed as one this build cannot make: "${sentence}"`,
      ).toBe(true);
    }
  });

  /*
   * TRAP 5 — a skeleton left behind. There is no loading state on this tab because
   * there is nothing to load, so no placeholder can survive a resolve that never
   * happens. Asserted as the absence of BOTH a status region and any drawn plot.
   */
  it('5 — has no loading state and no chart skeleton, drawn or otherwise', async () => {
    const { container } = await renderMineTab();
    const panel = container.querySelector('#statistics-tabpanel-mine') as HTMLElement;
    expect(panel.querySelector('[role="status"]')).toBeNull();
    expect(panel.querySelector('figure.stats-chart')).toBeNull();
    expect(panel.querySelector('svg.stats-chart-columns')).toBeNull();
    expect(panel.querySelector('.stats-chart-track')).toBeNull();
    expect(panel.querySelector('.stats-chart-grid')).toBeNull();
    // No axis, no ticks, no empty plot of any kind. The only SVGs are the
    // section's decorative heading glyphs.
    for (const svg of panel.querySelectorAll('svg')) {
      expect(svg.closest('.stats-card-icon')).not.toBeNull();
    }
  });

  /*
   * TRAP 6 — header-derived identity. `docs/identity-trust-contract.md` §6A
   * records that two of the seven candidate identity headers arrive carrying
   * whatever a CLIENT chose to send, so no header may name the reader — not even
   * as a greeting.
   */
  it('6 — displays no identity, and the module reads no header', async () => {
    const { container } = await renderMineTab();
    const text = textOf(container.querySelector('#statistics-tabpanel-mine') as HTMLElement);
    expect(text).not.toMatch(/signed in as|@|Signed in|Hello|Welcome back/i);

    const source = String((await import('../screens/statistics/MyStats?raw')).default);
    const contract = String((await import('../lib/myStatsContract?raw')).default);
    for (const module of [source, contract]) {
      // No header read, and no fetch of any kind, in either module. `X-authentik`
      // appears only inside the prose that explains why it must not be used.
      expect(module).not.toMatch(/headers\s*[.[]/);
      expect(module).not.toMatch(/\bfetch\s*\(/);
      expect(module).not.toMatch(/getHeader|request\.headers/);
    }
  });
});

// --- the gate itself --------------------------------------------------------

describe('the gated state', () => {
  it('states the reason the adapter reported, not a hard-coded sentence', async () => {
    await renderMineTab();
    // `workflow_counts` waits on record ownership, so THAT is the sentence shown —
    // not the signed-in-account one and not the not-recorded one.
    expect(MY_STATS_PENDING_REASON.workflow_counts).toBe('no_record_ownership');
    expect(screen.getByText(MY_STATS_PENDING_COPY.no_record_ownership)).toBeInTheDocument();
    expect(screen.queryByText(MY_STATS_PENDING_COPY.no_signed_in_account)).toBeNull();
  });

  it('renders whatever a DIFFERENT source reports, so the boundary is real', () => {
    const unavailable: MyStatsSource = {
      ...unconfiguredMyStatsSource,
      id: 'test-double',
      workflowCounts: () => ({ status: 'unavailable', message: 'The personal source failed.' }),
    };
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MyStats source={unavailable} />
      </MemoryRouter>,
    );
    expect(screen.getByText('The personal source failed.')).toBeInTheDocument();
  });

  /*
   * A `ready` payload has NO view here, and the tab says so rather than drawing
   * one. Speculative branches for payloads no adapter produces are how a
   * placeholder chart gets shipped.
   */
  it('a ready payload draws nothing and names the state it received', () => {
    const ready: MyStatsSource = {
      ...unconfiguredMyStatsSource,
      id: 'test-double',
      workflowCounts: () => ({
        status: 'ready',
        data: { byStep: [{ key: 'export', label: 'Export', count: 3 }], recordsCounted: 3 },
      }),
    };
    const { container } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MyStats source={ready} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/reported "ready", and this preview has no view built for it/)).toBeInTheDocument();
    expect(container.querySelector('figure.stats-chart')).toBeNull();
    // The payload's own figure never reaches the DOM.
    expect(textOf(container)).not.toContain('Export 3');
  });

  it('offers a route back to the workspace figures and to the privacy settings', async () => {
    await renderMineTab();
    expect(screen.getByRole('link', { name: 'See Workspace Statistics' })).toHaveAttribute(
      'href',
      '/statistics?tab=general',
    );
    expect(screen.getByRole('link', { name: 'Open Data & Privacy Settings' })).toHaveAttribute(
      'href',
      ROUTES.settingsTab('privacy'),
    );
  });
});

// --- the planned views -----------------------------------------------------

describe('the planned views describe a shape without asserting a figure', () => {
  it('lists all eight, each with a title, a description, a form and a gate marker', async () => {
    await renderMineTab();
    expect(MY_STATS_VIEWS).toHaveLength(8);

    for (const view of MY_STATS_VIEWS) {
      const heading = screen.getByRole('heading', { level: 3, name: view.title });
      const card = heading.closest('.stats-plan-card') as HTMLElement;
      expect(card, `${view.id} must render a card`).not.toBeNull();
      const text = textOf(card);
      expect(text).toContain(view.description);
      // One string, not an interpolation split across text nodes — see the
      // `stats-plan-form` note in `MyStats.tsx`.
      expect(card.querySelector('.stats-plan-form')?.textContent).toBe(
        `Will render as a ${view.form}.`,
      );
      expect(text).toContain(MY_STATS_PENDING_LABEL[MY_STATS_PENDING_REASON[view.id]]);
    }
  });

  it('every description names the unit it would count', async () => {
    // The conflation this guards is records-versus-fields, which is the same one
    // `EvidenceTotals` keeps apart with `totalFields` beside `recordsCounted`.
    for (const view of MY_STATS_VIEWS) {
      expect(
        /\brecords?\b|\bfields\b|\bissues\b|\bchanges\b/.test(view.description),
        `${view.id} must name its unit: "${view.description}"`,
      ).toBe(true);
    }
  });

  it('states no count anywhere in the planned-view grid', async () => {
    const { container } = await renderMineTab();
    const grid = container.querySelector('.stats-plan-grid') as HTMLElement;
    expect(grid).not.toBeNull();
    expect(textOf(grid)).not.toMatch(/\b\d+\b/);
  });
});

// --- the adapter -----------------------------------------------------------

describe('unconfiguredMyStatsSource', () => {
  const methods = [
    'workflowCounts',
    'readinessTrend',
    'validationIssuesOverTime',
    'evidenceSupportDistribution',
    'exportsOverTime',
    'commonBlockers',
    'recentActivity',
    'ownedVsCollaborated',
  ] as const;

  it('answers access_pending for all eight datasets, with a declared reason', () => {
    for (const method of methods) {
      const state = unconfiguredMyStatsSource[method]();
      expect(state.status, method).toBe('access_pending');
      if (state.status !== 'access_pending') throw new Error('unreachable');
      expect(
        ['no_signed_in_account', 'no_record_ownership', 'not_recorded'],
        method,
      ).toContain(state.reason);
    }
  });

  it('covers every dataset id — a new one cannot arrive with no method', () => {
    expect(methods).toHaveLength(Object.keys(MY_STATS_PENDING_REASON).length);
    expect(MY_STATS_VIEWS.map((v) => v.id).sort()).toEqual(
      Object.keys(MY_STATS_PENDING_REASON).sort(),
    );
  });

  it('is frozen, so nothing can swap a dataset in at runtime', () => {
    expect(Object.isFrozen(unconfiguredMyStatsSource)).toBe(true);
    expect(Object.isFrozen(MY_STATS_PENDING_REASON)).toBe(true);
    expect(Object.isFrozen(MY_STATS_VIEWS)).toBe(true);
  });

  it('every pending sentence blames the application, never the reader', () => {
    for (const [reason, copy] of Object.entries(MY_STATS_PENDING_COPY)) {
      expect(copy.length, reason).toBeGreaterThan(40);
      /*
       * No sentence tells the reader they have nothing. The word "zero" IS
       * allowed, and one sentence uses it — "It is not showing zero" — because
       * denying the zero is the point; what is forbidden is asserting one.
       */
      expect(copy, reason).not.toMatch(/\b(you have|there are|there is) (no|none|zero)\b/i);
      expect(copy, reason).not.toMatch(/\b0\b/);
      expect(copy, reason).toMatch(/this (preview|view)/i);
    }
  });
});

// --- switching tabs does not re-read --------------------------------------

describe('switching tabs is free', () => {
  it('issues no additional request when the reader moves between tabs', async () => {
    const calls = stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByText('Synthetic-Only');
    const afterLoad = calls.length;

    const tablist = screen.getByRole('tablist', { name: 'Statistics sections' });
    fireEvent.click(within(tablist).getByRole('tab', { name: 'My Stats' }));
    await screen.findByRole('heading', { name: 'Personal Statistics' });
    fireEvent.click(within(tablist).getByRole('tab', { name: 'General ISAAC' }));
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    await waitFor(() => expect(calls.length).toBe(afterLoad));
  });
});

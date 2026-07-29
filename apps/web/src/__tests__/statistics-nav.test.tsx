import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import {
  aboutResponse,
  experimentSummary,
  graphStatusAvailable,
  openApiFixture,
  stubFetchDown,
  stubFetchRoutes,
} from '../test/apiFixtures';

/**
 * Statistics destination + the `Settings & API` rename.
 *
 * Two things here are easy to get wrong silently, so both are pinned:
 *
 *   1. `App.tsx` ends in a `path="*"` catch-all that REDIRECTS to /experiments.
 *      A missing route registration therefore looks like a redirect, not a 404 —
 *      the surface simply becomes My Experiments and every "the app still works"
 *      assertion passes. So /statistics is asserted to actually render the
 *      Statistics surface, by its own <h1> AND by the sidebar's active item
 *      (which only My Experiments would claim if the catch-all had swallowed it).
 *
 *   2. `labels.ts navSettings` is the SINGLE authored string behind both the nav
 *      label and the Settings page <h1>, and the route `/settings` plus its
 *      `?tab=` deep links are deliberately UNCHANGED by the rename. The rename
 *      and the route are asserted separately so a future "tidy-up" that renames
 *      the route to match the label fails here.
 *
 * The nav-structure cases mount /governance: it is the one top-level surface
 * that issues no fetch, so the sidebar assertions are about the sidebar and
 * nothing else. /statistics mounts under `stubFetchDown` — its page-level header
 * and the shell chrome are rendered outside every fetch branch (the idiom at
 * `SettingsPage.tsx:128` and `GovernancePage.tsx:104`), so a dead backend still
 * proves the ROUTE resolved, without this file having to track which endpoints
 * the dashboard body reads.
 */

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

/**
 * A probe inside the router, exposing the live location and the real `navigate`
 * so a test can press the browser's Back and Forward buttons (`navigate(-1)` /
 * `navigate(1)`) exactly as a user would. Same instrument, for the same reason,
 * as `settings-page.test.tsx:69-100`.
 */
let probePath = '';
let probeNavigate: NavigateFunction | null = null;
function RouterProbe() {
  probePath = useLocation().pathname;
  probeNavigate = useNavigate();
  return null;
}

function renderWithProbeAt(path: string) {
  probePath = '';
  probeNavigate = null;
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
      <RouterProbe />
    </MemoryRouter>,
  );
}

const back = () => act(() => probeNavigate?.(-1));
const forward = () => act(() => probeNavigate?.(1));

/** The sidebar's destination links, in DOM order. */
function navLinks(container: HTMLElement): HTMLAnchorElement[] {
  return Array.from(
    container.querySelectorAll<HTMLAnchorElement>('nav[aria-label="Primary"] a.nav-item'),
  );
}

/** The three page-level fetches `SettingsPage` issues at mount. */
const settingsRoutes = () => ({
  'GET /api/about': { body: aboutResponse },
  'GET /api/openapi': { body: openApiFixture },
  'GET /api/graph/status': { body: graphStatusAvailable },
});

const experimentsRoutes = () => ({
  'GET /api/experiments': { body: { experiments: [experimentSummary] } },
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- sidebar structure --------------------------------------------------------

describe('sidebar destinations', () => {
  it('renders exactly the five destinations, in the specified order', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');

    // One ordered read of the rendered DOM — not five independent lookups, which
    // would pass for any order at all.
    expect(navLinks(container).map((a) => a.textContent)).toEqual([
      'My Experiments',
      'Project Memory',
      'Governance & Safety',
      'Statistics',
      'Settings & API',
    ]);
  });

  it('places Statistics immediately before Settings & API', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const labels = navLinks(container).map((a) => a.textContent);

    const statistics = labels.indexOf('Statistics');
    expect(statistics).toBeGreaterThanOrEqual(0);
    expect(labels[statistics + 1]).toBe('Settings & API');
  });

  it('every destination is a real <a href> — keyboard reachable, not a click handler', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const links = navLinks(container);

    expect(links).toHaveLength(5);
    for (const link of links) {
      expect(link.tagName).toBe('A');
      expect(link).toHaveAttribute('href');
      expect(link.getAttribute('href')).not.toBe('');
    }
  });

  it('the hrefs are router-relative — no destination hard-codes the /krish base path', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const hrefs = navLinks(container).map((a) => a.getAttribute('href'));

    // The basename is applied ONCE, by the <BrowserRouter> in App.tsx; under
    // MemoryRouter there is none, so a '/krish' here could only be a literal.
    expect(hrefs).toEqual([
      ROUTES.experiments,
      ROUTES.memory,
      ROUTES.governance,
      ROUTES.statistics,
      ROUTES.settings,
    ]);
    for (const href of hrefs) {
      expect(href).not.toContain('/krish');
    }
  });

  it('the Statistics icon is aria-hidden and the item still has an accessible text name', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const statistics = navLinks(container).find((a) => a.textContent === 'Statistics');

    expect(statistics).toBeDefined();
    const icon = statistics!.querySelector('svg');
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute('aria-hidden', 'true');
    // The glyph is decorative; the name comes from the text beside it.
    expect(statistics!).toHaveAccessibleName('Statistics');
  });
});

// --- the Settings & API rename ------------------------------------------------

describe('the Settings destination reads "Settings & API"', () => {
  it('the sidebar label and the page <h1> both read it, from the one authored string', async () => {
    expect(LABELS.navSettings).toBe('Settings & API');

    stubFetchRoutes(settingsRoutes());
    const { container } = renderAt(ROUTES.settings);

    const settings = navLinks(container).find((a) => a.getAttribute('href') === ROUTES.settings);
    expect(settings).toBeDefined();
    expect(settings!.textContent).toBe('Settings & API');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Settings & API' }),
    ).toBeInTheDocument();
  });

  it('keeps the About This Build eyebrow and the five tab labels unchanged', async () => {
    stubFetchRoutes(settingsRoutes());
    renderAt(ROUTES.settings);

    expect(await screen.findByText('About This Build')).toBeInTheDocument();
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'Overview',
      'Data & Privacy',
      'About',
      'API Access',
      'Endpoint Explorer',
    ]);
  });
});

// --- routing ------------------------------------------------------------------

describe('routing', () => {
  it('/statistics renders the Statistics surface — it is NOT swallowed by the path="*" redirect', async () => {
    stubFetchDown();
    const { container } = renderAt(ROUTES.statistics);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Statistics' }),
    ).toBeInTheDocument();

    // The catch-all redirects to /experiments, which would mount My Experiments
    // and mark ITS nav item current. Reading the active item proves which route
    // actually matched, independent of any text the page happens to share.
    await waitFor(() => {
      const current = navLinks(container).filter((a) => a.getAttribute('aria-current') === 'page');
      expect(current.map((a) => a.textContent)).toEqual(['Statistics']);
    });
    expect(
      screen.queryByRole('heading', { level: 1, name: LABELS.screenExperiments }),
    ).toBeNull();
  });

  it('/settings still loads at its unchanged path', async () => {
    stubFetchRoutes(settingsRoutes());
    renderAt('/settings');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Settings & API' }),
    ).toBeInTheDocument();
    // The rename is cosmetic: the route literal did not move with the label.
    expect(ROUTES.settings).toBe('/settings');
  });

  it('/settings?tab=explorer still deep-links to the Endpoint Explorer tab', async () => {
    stubFetchRoutes(settingsRoutes());
    renderAt(ROUTES.settingsTab('explorer'));

    const explorer = await screen.findByRole('tab', { name: 'Endpoint Explorer' });
    expect(explorer).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute(
      'aria-selected',
      'false',
    );
    // Scoped by accessible name, not `getByRole('tabpanel')`: once the contract
    // has loaded, the Explorer's detail pane carries its OWN code-sample tablist,
    // so the page has more than one panel in the tree.
    expect(screen.getByRole('tabpanel', { name: 'Endpoint Explorer' })).toHaveAttribute(
      'id',
      'settings-tabpanel-explorer',
    );
  });

  it('an unrecognised ?tab= value still falls back to Overview', async () => {
    stubFetchRoutes(settingsRoutes());
    renderAt('/settings?tab=not-a-tab');

    const overview = await screen.findByRole('tab', { name: 'Overview' });
    expect(overview).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Overview' })).toHaveAttribute(
      'id',
      'settings-tabpanel-overview',
    );
  });
});

// --- active state -------------------------------------------------------------

describe('active destination', () => {
  it('on /statistics only the Statistics link is aria-current="page"', async () => {
    stubFetchDown();
    const { container } = renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { level: 1, name: 'Statistics' });

    const links = navLinks(container);
    const current = links.filter((a) => a.getAttribute('aria-current') === 'page');
    expect(current.map((a) => a.textContent)).toEqual(['Statistics']);
    for (const link of links.filter((a) => a.textContent !== 'Statistics')) {
      expect(link).not.toHaveAttribute('aria-current');
    }
  });

  it('on /settings only the Settings & API link is aria-current="page"', async () => {
    stubFetchRoutes(settingsRoutes());
    const { container } = renderAt(ROUTES.settings);
    await screen.findByRole('heading', { level: 1, name: 'Settings & API' });

    const links = navLinks(container);
    const current = links.filter((a) => a.getAttribute('aria-current') === 'page');
    expect(current.map((a) => a.textContent)).toEqual(['Settings & API']);
    for (const link of links.filter((a) => a.textContent !== 'Settings & API')) {
      expect(link).not.toHaveAttribute('aria-current');
    }
  });
});

// --- Back / Forward -----------------------------------------------------------

describe('Back / Forward across the new destination', () => {
  it('walks /experiments → /statistics → Back → Forward, rendering the right surface each time', async () => {
    // Only the experiments list is stubbed; the Statistics body's own reads fall
    // through to per-section error states, which is irrelevant here — this test
    // is about which SURFACE the history entry resolves to.
    stubFetchRoutes(experimentsRoutes());
    const { container } = renderWithProbeAt(ROUTES.experiments);

    await screen.findByRole('heading', { level: 1, name: LABELS.screenExperiments });
    expect(probePath).toBe(ROUTES.experiments);

    const statisticsLink = navLinks(container).find((a) => a.textContent === 'Statistics');
    expect(statisticsLink).toBeDefined();
    fireEvent.click(statisticsLink!);

    await screen.findByRole('heading', { level: 1, name: 'Statistics' });
    expect(probePath).toBe(ROUTES.statistics);

    back();
    await screen.findByRole('heading', { level: 1, name: LABELS.screenExperiments });
    expect(probePath).toBe(ROUTES.experiments);
    expect(screen.queryByRole('heading', { level: 1, name: 'Statistics' })).toBeNull();

    forward();
    await screen.findByRole('heading', { level: 1, name: 'Statistics' });
    expect(probePath).toBe(ROUTES.statistics);
    expect(
      screen.queryByRole('heading', { level: 1, name: LABELS.screenExperiments }),
    ).toBeNull();
  });
});

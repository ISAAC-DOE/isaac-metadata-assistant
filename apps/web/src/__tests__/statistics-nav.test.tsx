import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from 'react-router-dom';

import { AppRoutes } from '../App';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import {
  aboutResponse,
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

/*
 * ~~`experimentsRoutes`~~ — REMOVED, and the reason is recorded because a
 * deleted fixture looks like lost coverage. Its only consumer was the
 * Back/Forward walk, which used to start on `/experiments` and click the
 * `Statistics` item in the primary navigation. That item was demoted
 * (`UX-017`), so the walk now starts on `/settings` and clicks the
 * advanced-surfaces link — the path a scientist now actually takes — and needs
 * `settingsRoutes()` instead.
 *
 * **`experimentSummary` went with it, and the first version of this comment
 * asserted it was "still imported and used by the routing assertions below" —
 * which `tsc -b` immediately measured FALSE (`TS6133`).** Recorded rather than
 * quietly corrected: an unused-fixture note is exactly the kind of claim that
 * gets copied forward, and this one was wrong the moment it was written.
 */

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- sidebar structure --------------------------------------------------------

describe('sidebar destinations', () => {
  /*
   * *** THE PRIMARY LIST IS THREE, NOT FIVE, SINCE 2026-09-13 — and these
   * assertions are INVERTED IN PLACE rather than deleted, because this file's
   * own five-destination expectations are what a future session would otherwise
   * read as the intended design. ***
   *
   * ~~'renders exactly the five destinations, in the specified order' →
   *   ['My Experiments', 'Project Memory', 'Governance & Safety', 'Statistics',
   *    'Settings & API']~~
   * ~~'places Statistics immediately before Settings & API'~~
   * ~~'every destination is a real <a href>' → expect(links).toHaveLength(5)~~
   * ~~hrefs → [experiments, memory, governance, statistics, settings]~~
   * ~~'the Statistics icon is aria-hidden…' (the item is no longer in this list)~~
   *
   * **Project Memory (`UX-015`/DEC-19) and Statistics (`UX-017`) were DEMOTED,
   * not deleted.** Both routes, both screens and all of their tests are
   * unchanged — including Project Memory's 578 test cases. What moved is which
   * destinations a scientist is offered first. `LeftNav.tsx` carries the
   * measurements; §19's sequencing rule required the replacement home to exist
   * FIRST, which is what the `reachable from Settings` block below asserts.
   *
   * **Governance & Safety deliberately stays**, and that is a decision rather
   * than an omission: the authorizing direction enumerates the surfaces to
   * demote and Governance is in neither that list nor the three named top-level
   * destinations, so removing it would be a product decision nobody took.
   */
  it('renders exactly the three primary destinations, in the specified order', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');

    // One ordered read of the rendered DOM — not three independent lookups,
    // which would pass for any order at all.
    expect(navLinks(container).map((a) => a.textContent)).toEqual([
      'My Experiments',
      'Governance & Safety',
      'Settings & API',
    ]);
  });

  it('no longer offers Project Memory or Statistics as primary destinations', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const labels = navLinks(container).map((a) => a.textContent);

    expect(labels).not.toContain('Project Memory');
    expect(labels).not.toContain('Statistics');
  });

  it('places Settings & API last', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const labels = navLinks(container).map((a) => a.textContent);

    expect(labels[labels.length - 1]).toBe('Settings & API');
  });

  it('every destination is a real <a href> — keyboard reachable, not a click handler', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const links = navLinks(container);

    expect(links).toHaveLength(3);
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
    expect(hrefs).toEqual([ROUTES.experiments, ROUTES.governance, ROUTES.settings]);
    for (const href of hrefs) {
      expect(href).not.toContain('/krish');
    }
  });

  it('every destination icon is aria-hidden and every item has an accessible text name', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');

    // Asserted over the WHOLE list rather than over one named item: the original
    // version of this test named `Statistics`, so demoting that one destination
    // would have removed the only coverage of the property.
    for (const link of navLinks(container)) {
      const icon = link.querySelector('svg');
      expect(icon).not.toBeNull();
      expect(icon).toHaveAttribute('aria-hidden', 'true');
      // The glyph is decorative; the name comes from the text beside it.
      expect(link).toHaveAccessibleName(link.textContent ?? '');
    }
  });
});

describe('the two demoted destinations are still reachable', () => {
  /*
   * §19's SEQUENCING RULE, ASSERTED. The rule for a demotion is: provide the
   * capability elsewhere FIRST, verify nothing becomes inaccessible, and only
   * then remove it from primary navigation. Without this block the demotion
   * above would be indistinguishable from a removal, and a green suite would
   * report a regression as a simplification.
   */
  it('Settings & API → Overview links to both of them, as real anchors', async () => {
    stubFetchRoutes(settingsRoutes());
    renderAt(ROUTES.settings);

    const group = await screen.findByRole('navigation', {
      name: 'Advanced and developer surfaces',
    });
    const links = Array.from(group.querySelectorAll<HTMLAnchorElement>('a'));

    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      ROUTES.memory,
      ROUTES.statistics,
    ]);
    for (const link of links) {
      // A <button> here would be unopenable in a new tab and unlinkable — these
      // navigate to another ROUTE, not to another tab of this page.
      expect(link.tagName).toBe('A');
      expect(link.getAttribute('href')).not.toContain('/krish');
    }
  });

  it('both routes still render their own screen', async () => {
    stubFetchDown();
    const memory = renderAt(ROUTES.memory);
    expect(
      await screen.findByRole('heading', { level: 1, name: LABELS.navMemory }),
    ).toBeInTheDocument();
    memory.unmount();

    stubFetchDown();
    renderAt(ROUTES.statistics);
    expect(
      await screen.findByRole('heading', { level: 1, name: LABELS.navStatistics }),
    ).toBeInTheDocument();
  });

  it('marks Settings as the ANCESTOR on a demoted route — and never claims it is the page', () => {
    stubFetchDown();
    const { container } = renderAt(ROUTES.memory);
    const links = navLinks(container);
    const settings = links.find((a) => a.getAttribute('href') === ROUTES.settings);

    expect(settings).toBeDefined();
    expect(settings!.className).toContain('ancestor');
    /*
     * THE HONESTY HALF, and it is the reason `NAV_PARENT` exists rather than
     * just reusing `active`. `aria-current="page"` means *this link points at
     * the page you are on*; on Project Memory the Settings link does not. A
     * screen-reader user must not be told they are somewhere they are not.
     */
    expect(settings!).not.toHaveAttribute('aria-current');
    expect(links.filter((a) => a.hasAttribute('aria-current'))).toHaveLength(0);
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

  it('keeps the About This Build eyebrow, and the tab labels, unchanged', async () => {
    stubFetchRoutes(settingsRoutes());
    renderAt(ROUTES.settings);

    expect(await screen.findByText('About This Build')).toBeInTheDocument();
    /* R0 appended Help & Tutorial, and Connect Your Agent was later inserted
       before it. The FIVE tabs this guard was written for are unchanged in
       label and in order, which is the whole point of it: this test belongs to
       the `Settings & API` rename slice and exists to catch that rename
       reaching the tab strip. Tabs added afterwards are listed here so the
       assertion stays an equality — a weaker `toContain` would stop catching a
       rename of the five, which is the one thing it is here to catch. */
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'Overview',
      'Data & Privacy',
      'About',
      'API Access',
      'Endpoint Explorer',
      'Connect Your Agent',
      'Help & Tutorial',
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

    /*
     * WHICH ROUTE ACTUALLY MATCHED, read off the navigation rather than off page
     * text — and the mechanism had to change when Statistics was demoted.
     *
     * ~~Previously: `aria-current="page"` is on the `Statistics` link.~~ There
     * is no Statistics link now, and a demoted route deliberately marks NO link
     * as the current page (see `LeftNav`'s `NAV_PARENT`). The discriminator is
     * the ANCESTOR marking instead, and it is still route-specific: the
     * catch-all redirects to `/experiments`, which marks its own link
     * `aria-current="page"` and marks no ancestor at all. So "Settings is the
     * ancestor and nothing is the current page" is reachable only from a
     * demoted route.
     */
    await waitFor(() => {
      const links = navLinks(container);
      const ancestors = links.filter((a) => a.className.includes('ancestor'));
      expect(ancestors.map((a) => a.textContent)).toEqual(['Settings & API']);
      expect(links.filter((a) => a.hasAttribute('aria-current'))).toHaveLength(0);
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
  /*
   * ~~'on /statistics only the Statistics link is aria-current="page"'~~ —
   * INVERTED IN PLACE. Statistics left the primary list (`UX-017`), so the
   * correct claim is the opposite one, and it is the claim that carries the
   * honesty property: a demoted route marks NO link as the page you are on,
   * because none of the three links points at it. The sibling assertion for
   * `/memory` lives in `the two demoted destinations are still reachable`
   * above; both are kept, because a single one would leave the other route's
   * marking unpinned.
   */
  it('on /statistics NO link is aria-current — Settings is only the ancestor', async () => {
    stubFetchDown();
    const { container } = renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { level: 1, name: 'Statistics' });

    const links = navLinks(container);
    expect(links.filter((a) => a.hasAttribute('aria-current'))).toHaveLength(0);
    const settings = links.find((a) => a.getAttribute('href') === ROUTES.settings);
    expect(settings!.className).toContain('ancestor');
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
  /*
   * ~~'walks /experiments → /statistics → Back → Forward'~~ — the WALK IS
   * REROUTED, not weakened, and the property under test is unchanged: a real
   * link click makes a history entry, and Back/Forward resolve each entry to
   * the right surface.
   *
   * It used to click the `Statistics` item in the primary navigation. That item
   * no longer exists (`UX-017`), so the walk now starts where a scientist now
   * actually starts — `Settings & API` → the advanced-surfaces group — which
   * makes this ALSO the end-to-end proof that §19's replacement path works by
   * clicking rather than by asserting an `href`.
   */
  it('walks /settings → /statistics → Back → Forward, rendering the right surface each time', async () => {
    // The Statistics body's own reads fall through to per-section error states,
    // which is irrelevant here — this test is about which SURFACE the history
    // entry resolves to.
    stubFetchRoutes(settingsRoutes());
    renderWithProbeAt(ROUTES.settings);

    await screen.findByRole('heading', { level: 1, name: 'Settings & API' });
    expect(probePath).toBe(ROUTES.settings);

    const group = await screen.findByRole('navigation', {
      name: 'Advanced and developer surfaces',
    });
    const statisticsLink = Array.from(
      group.querySelectorAll<HTMLAnchorElement>('a'),
    ).find((a) => a.getAttribute('href') === ROUTES.statistics);
    expect(statisticsLink).toBeDefined();
    fireEvent.click(statisticsLink!);

    await screen.findByRole('heading', { level: 1, name: 'Statistics' });
    expect(probePath).toBe(ROUTES.statistics);

    back();
    await screen.findByRole('heading', { level: 1, name: 'Settings & API' });
    expect(probePath).toBe(ROUTES.settings);
    expect(screen.queryByRole('heading', { level: 1, name: 'Statistics' })).toBeNull();

    forward();
    await screen.findByRole('heading', { level: 1, name: 'Statistics' });
    expect(probePath).toBe(ROUTES.statistics);
    expect(screen.queryByRole('heading', { level: 1, name: 'Settings & API' })).toBeNull();
  });
});

/* ── the Settings description of Statistics must not promise personal figures ── */

describe('the Advanced surfaces description of Statistics', () => {
  /*
   * FOUND BY INDEPENDENT REVIEW, 2026-09-13. The description read "Counts over the
   * records in this workspace, **and over your own activity in it**".
   *
   * That second clause was FALSE. `MyStats.tsx` renders `ChartAccessPending` on
   * EVERY branch — its own header says "there is no personal figure in this build to
   * appear" — because all three reasons in `lib/myStatsContract.ts`
   * (`no_signed_in_account`, `no_record_ownership`, `not_recorded`) are downstream of
   * the absent trusted authentication boundary. A scientist following that sentence
   * would have gone looking for their own figures and found a gated panel.
   *
   * Pinned as a BAN rather than as an exact string, because the defect is the CLAIM
   * and not its wording: any phrasing that promises per-person figures from this
   * description is the same defect. §15's "build nothing that implies any of it
   * exists" governs a DESCRIPTION of a destination as much as the destination.
   */
  const PERSONAL_CLAIM_PHRASINGS = [
    /your own activity/i,
    /your activity/i,
    /\byour\b[^.]{0,40}\b(figures|statistics|stats|records|contributions)\b/i,
    /per-person/i,
    /who did what/i,
    /activity (?:by|per) (?:user|person|scientist|you)/i,
  ];

  it('never promises per-person figures, in any of six phrasings', async () => {
    stubFetchRoutes(settingsRoutes());
    const { container } = renderAt(ROUTES.settings);
    await screen.findByRole('heading', { level: 1, name: 'Settings & API' });

    const group = await screen.findByRole('navigation', {
      name: 'Advanced and developer surfaces',
    });
    // The whole Overview panel, not just the group: the description sits in a
    // sibling list, and scoping too tightly is how this kind of guard goes vacuous.
    const panel = group.closest('.settings-panel') ?? container;
    const text = (panel.textContent ?? '').replace(/\s+/g, ' ');

    // The honest half must still be there, or this test would pass on a panel that
    // simply stopped describing Statistics at all.
    expect(text).toMatch(/Counts over the records in this workspace/);

    for (const pattern of PERSONAL_CLAIM_PHRASINGS) {
      expect(
        text,
        `the Statistics description promises per-person figures (${pattern}), but ` +
          `MyStats renders ChartAccessPending on every branch — there is no personal ` +
          `figure in this build to show`
      ).not.toMatch(pattern);
    }
  });
});

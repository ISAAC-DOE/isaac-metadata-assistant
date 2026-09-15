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
  /*
   * *** THREE BECAME FOUR ON 2026-09-13, AND THAT IS NOT THE LIST GROWING BACK.
   * The assertion is corrected in place, with the previous expectation struck,
   * because a stale expectation here reads as the intended design. ***
   *
   * ~~['My Experiments', 'Governance & Safety', 'Settings & API']~~
   *
   * `Historical Import` was ADDED, and it is the SECOND of the three top-level
   * destinations the authorizing direction names (`Experiments`,
   * `Historical Import`, `Settings`). `LeftNav.tsx` had deliberately withheld it
   * — its own comment said so, and the reason was correct: §15's "build nothing
   * that implies any of it exists" forbids offering the slot before the
   * destination exists. The destination now exists (`HIST-001`, `HIST-004`,
   * `HIST-003a`), so the condition the decline named is met, and that comment is
   * struck in place there rather than deleted.
   *
   * SO THE COUNT IS FOUR AND NOT THREE, for the reason the block above already
   * gives: `Governance & Safety` stays. Three of the four are the direction's own
   * three; the fourth is a scientist-facing honesty surface the direction
   * enumerates in neither list, and removing it would still be a product decision
   * nobody took.
   *
   * ORDER IS THE PRODUCT'S: the two scientist-facing pillars first, then
   * Governance, then Settings last (asserted separately below).
   */
  /*
   * *** THE LIST CHANGED AGAIN ON 2026-09-15, BY THE PROJECT OWNER'S DECISION,
   * AND THE TWO MEMBERS SWAPPED RATHER THAN THE COUNT MOVING. It is still FOUR.
   * The previous expectation is struck in place, for the same reason the
   * previous correction struck the one before it: a stale expectation in this
   * file reads as the intended design. ***
   *
   * ~~['My Experiments', 'Historical Import', 'Governance & Safety', 'Settings & API']~~
   *
   * `Statistics` came BACK and `Governance & Safety` went DOWN, and the two
   * moves have different authorities, so they are recorded separately:
   *
   *   * `Statistics` is a direct owner instruction ("Return Statistics to the
   *     primary sidebar"), which SUPERSEDES the `UX-017` demotion. That
   *     demotion is not retracted and its measurement still stands — the page
   *     was 3,820 px and 422 visible text elements — but a measurement of a
   *     SCREEN was never an answer about a DESTINATION, and the destination is
   *     the owner's call.
   *   * `Governance & Safety` goes down by the same reasoning the block above
   *     used to KEEP it, applied to a direction that now reaches it. The old
   *     comment's ground was that the authorizing direction enumerated it in
   *     neither list, so removing it would be "a product decision nobody took".
   *     The 2026-09-15 direction takes that decision explicitly — it names the
   *     target list, and it asks that Governance be evaluated for Settings
   *     rather than held as a primary scientist destination.
   *
   * NOTHING ABOUT GOVERNANCE'S CAPABILITY MOVED, and that is asserted rather
   * than asserted-about: the route still resolves, and the reachable-from-
   * Settings block below is extended to cover it, so the demotion cannot leave
   * it stranded. §19's sequencing rule — the replacement home exists FIRST —
   * is the same rule Project Memory's demotion obeyed.
   */
  it('renders exactly the four primary destinations, in the specified order', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');

    // One ordered read of the rendered DOM — not four independent lookups,
    // which would pass for any order at all.
    expect(navLinks(container).map((a) => a.textContent)).toEqual([
      'My Experiments',
      'Historical Import',
      'Statistics',
      'Settings',
    ]);
  });

  /*
   * INVERTED IN PLACE for `Statistics`, UNCHANGED for `Project Memory`, and the
   * asymmetry is the whole point of keeping this case rather than deleting it:
   * the owner's 2026-09-15 direction promotes ONE of the two 2026-09-13
   * demotions and explicitly re-affirms the other ("Do NOT return Project Memory
   * to the primary scientist sidebar"). A test that dropped both would stop
   * guarding the half that is still a live decision.
   */
  it('still keeps Project Memory out of primary navigation, and now offers Statistics', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const labels = navLinks(container).map((a) => a.textContent);

    expect(labels).not.toContain('Project Memory');
    expect(labels).toContain('Statistics');
  });

  /*
   * THE NEW DEMOTION, PINNED ON ITS OWN. Governance leaving the primary list is
   * the claim most likely to be silently reverted by someone who reads the
   * struck comment above and not the correction under it.
   */
  it('no longer offers Governance & Safety as a primary destination', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');

    expect(navLinks(container).map((a) => a.textContent)).not.toContain('Governance & Safety');
  });

  it('places Settings last', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const labels = navLinks(container).map((a) => a.textContent);

    expect(labels[labels.length - 1]).toBe('Settings');
  });

  it('every destination is a real <a href> — keyboard reachable, not a click handler', () => {
    stubFetchDown();
    const { container } = renderAt('/governance');
    const links = navLinks(container);

    expect(links).toHaveLength(4);
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
      ROUTES.imports,
      ROUTES.statistics,
      ROUTES.settings,
    ]);
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

describe('every demoted destination is still reachable', () => {
  /*
   * §19's SEQUENCING RULE, ASSERTED. The rule for a demotion is: provide the
   * capability elsewhere FIRST, verify nothing becomes inaccessible, and only
   * then remove it from primary navigation. Without this block the demotion
   * above would be indistinguishable from a removal, and a green suite would
   * report a regression as a simplification.
   *
   * *** THE MEMBERSHIP CHANGED ON 2026-09-15 AND THE RULE DID NOT. Statistics
   * was promoted out of this set and Governance & Safety was demoted into it,
   * so the count is still two — but they are reached from DIFFERENT places and
   * are therefore asserted separately rather than in one list:
   *
   *   * `Project Memory` -> Settings' advanced-surfaces group (below).
   *   * `Governance & Safety` -> Settings' Data & Privacy tab, which already
   *     carried a reciprocal link to it before the demotion. That link stopped
   *     being a convenience and became the sequencing rule's "provide the
   *     capability elsewhere FIRST" the moment the nav slot was withdrawn,
   *     which is why it now has an assertion of its own. ***
   */
  it('Settings → Overview links to Project Memory, as a real anchor', async () => {
    stubFetchRoutes(settingsRoutes());
    renderAt(ROUTES.settings);

    const group = await screen.findByRole('navigation', {
      name: 'Advanced and developer surfaces',
    });
    const links = Array.from(group.querySelectorAll<HTMLAnchorElement>('a'));

    expect(links.map((a) => a.getAttribute('href'))).toEqual([ROUTES.memory]);
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

// --- the Settings destination's name ------------------------------------------

/*
 * *** RENAMED A SECOND TIME, 2026-09-15: `Settings & API` -> `Settings`, by the
 * project owner's direction. The assertions below are updated in place and the
 * previous expectation is struck rather than deleted, because this file's whole
 * purpose is to make a rename fail loudly rather than drift. ***
 *
 * ~~describe('the Settings destination reads "Settings & API"')~~
 *
 * The `& API` was naming the page's CONTENTS in the DESTINATION's label, and
 * those contents are what is being reorganised — API Access and the Endpoint
 * Explorer are developer surfaces, and a primary slot advertising them tells a
 * scientist the page is not for them.
 *
 * WHAT THIS FILE'S ORIGINAL POINT (2) PROTECTED IS UNCHANGED AND STILL TESTED:
 * `labels.ts navSettings` remains the SINGLE authored string behind both the
 * nav label and the page <h1>, and the route `/settings` plus its `?tab=` deep
 * links are again deliberately NOT moved by the rename. The rename and the
 * route are still asserted separately, so a future tidy-up that renames the
 * route to match the label still fails here. That guard has now caught two
 * renames, which is the argument for keeping it.
 */
describe('the Settings destination reads "Settings"', () => {
  it('the sidebar label and the page <h1> both read it, from the one authored string', async () => {
    expect(LABELS.navSettings).toBe('Settings');

    stubFetchRoutes(settingsRoutes());
    const { container } = renderAt(ROUTES.settings);

    const settings = navLinks(container).find((a) => a.getAttribute('href') === ROUTES.settings);
    expect(settings).toBeDefined();
    expect(settings!.textContent).toBe('Settings');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Settings' }),
    ).toBeInTheDocument();
  });

  it('keeps the About This Build eyebrow, and the tab labels, unchanged', async () => {
    stubFetchRoutes(settingsRoutes());
    renderAt(ROUTES.settings);

    expect(await screen.findByText('About This Build')).toBeInTheDocument();
    /* R0 appended Help & Tutorial, and Connect Your Agent was later inserted
       before it. The FIVE tabs this guard was written for are unchanged in
       label and in order, which is the whole point of it: this test belongs to
       the `Settings` rename slice and exists to catch that rename
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
     * text — and the mechanism has now changed TWICE, in opposite directions.
     *
     * ~~(1) `aria-current="page"` is on the `Statistics` link.~~
     * ~~(2) There is no Statistics link now, so the discriminator is the
     *      ANCESTOR marking: Settings is the ancestor and nothing is current.~~
     *
     * BOTH ARE KEPT STRUCK AND THE FIRST IS NOW TRUE AGAIN, because the
     * sequence is the useful record: (1) held while Statistics was primary,
     * (2) held while it was demoted under Settings, and the 2026-09-15
     * promotion restores (1). A reader who saw only the latest form would
     * reasonably assume this assertion had never moved.
     *
     * It is still route-specific, which is the only property that matters
     * here: the `path="*"` catch-all redirects to `/experiments`, which marks
     * ITS OWN link `aria-current="page"`. So a Statistics link carrying
     * `aria-current` is reachable only when `/statistics` actually matched.
     */
    await waitFor(() => {
      const links = navLinks(container);
      const current = links.filter((a) => a.hasAttribute('aria-current'));
      expect(current.map((a) => a.textContent)).toEqual(['Statistics']);
      expect(links.filter((a) => a.className.includes('ancestor'))).toHaveLength(0);
    });
    expect(
      screen.queryByRole('heading', { level: 1, name: LABELS.screenExperiments }),
    ).toBeNull();
  });

  it('/settings still loads at its unchanged path', async () => {
    stubFetchRoutes(settingsRoutes());
    renderAt('/settings');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Settings' }),
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
   * ~~INVERTED IN PLACE. Statistics left the primary list (`UX-017`), so the
   * correct claim is the opposite one…~~ — **INVERTED BACK, 2026-09-15.**
   * Statistics is a primary destination again, so `/statistics` marks its own
   * link `aria-current="page"` and marks no ancestor.
   *
   * THE HONESTY PROPERTY THE STRUCK VERSION CARRIED IS NOT LOST, and that is
   * why this case is rewritten rather than dropped: it moves to `/memory`,
   * which is still demoted. `a demoted route marks NO link as the page you are
   * on` is asserted there, in `every demoted destination is still reachable`,
   * and now also for `/governance` — so the property is pinned on both demoted
   * routes instead of on one promoted one.
   */
  it('on /statistics the Statistics link is aria-current="page" — no ancestor marking', async () => {
    stubFetchDown();
    const { container } = renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { level: 1, name: 'Statistics' });

    const links = navLinks(container);
    const current = links.filter((a) => a.getAttribute('aria-current') === 'page');
    expect(current.map((a) => a.textContent)).toEqual(['Statistics']);
    expect(links.filter((a) => a.className.includes('ancestor'))).toHaveLength(0);
  });

  /*
   * THE NEWLY DEMOTED ROUTE, carrying the honesty property the case above used
   * to carry. `/governance` is reached from Settings → Data & Privacy, so
   * Settings is its ancestor and nothing on the list is the page you are on.
   */
  it('on /governance NO link is aria-current — Settings is only the ancestor', async () => {
    stubFetchDown();
    const { container } = renderAt(ROUTES.governance);

    const links = navLinks(container);
    expect(links.filter((a) => a.hasAttribute('aria-current'))).toHaveLength(0);
    const settings = links.find((a) => a.getAttribute('href') === ROUTES.settings);
    expect(settings).toBeDefined();
    expect(settings!.className).toContain('ancestor');
  });

  it('on /settings only the Settings link is aria-current="page"', async () => {
    stubFetchRoutes(settingsRoutes());
    const { container } = renderAt(ROUTES.settings);
    await screen.findByRole('heading', { level: 1, name: 'Settings' });

    const links = navLinks(container);
    const current = links.filter((a) => a.getAttribute('aria-current') === 'page');
    expect(current.map((a) => a.textContent)).toEqual(['Settings']);
    for (const link of links.filter((a) => a.textContent !== 'Settings')) {
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
   * ~~It used to click the `Statistics` item in the primary navigation. That
   * item no longer exists (`UX-017`), so the walk now starts where a scientist
   * now actually starts — `Settings & API` → the advanced-surfaces group.~~
   *
   * **REROUTED A SECOND TIME, 2026-09-15, BACK TO WHERE IT BEGAN.** Statistics
   * is a primary destination again, so the walk clicks the sidebar item — which
   * is once more where a scientist actually starts. Both reroutes are kept
   * struck because the property under test never changed and the PATH did,
   * twice; a reader seeing only the current form would not know this case has
   * been the canary for two navigation decisions.
   *
   * The §19 replacement-path proof that the struck version carried has NOT been
   * dropped: it now lives on `/memory`, whose reachability from the
   * advanced-surfaces group is asserted in
   * `every demoted destination is still reachable`.
   */
  it('walks /settings → /statistics → Back → Forward, rendering the right surface each time', async () => {
    // The Statistics body's own reads fall through to per-section error states,
    // which is irrelevant here — this test is about which SURFACE the history
    // entry resolves to.
    stubFetchRoutes(settingsRoutes());
    const { container } = renderWithProbeAt(ROUTES.settings);

    await screen.findByRole('heading', { level: 1, name: 'Settings' });
    expect(probePath).toBe(ROUTES.settings);

    const statisticsLink = navLinks(container).find(
      (a) => a.getAttribute('href') === ROUTES.statistics,
    );
    expect(statisticsLink).toBeDefined();
    fireEvent.click(statisticsLink!);

    await screen.findByRole('heading', { level: 1, name: 'Statistics' });
    expect(probePath).toBe(ROUTES.statistics);

    back();
    await screen.findByRole('heading', { level: 1, name: 'Settings' });
    expect(probePath).toBe(ROUTES.settings);
    expect(screen.queryByRole('heading', { level: 1, name: 'Statistics' })).toBeNull();

    forward();
    await screen.findByRole('heading', { level: 1, name: 'Statistics' });
    expect(probePath).toBe(ROUTES.statistics);
    expect(screen.queryByRole('heading', { level: 1, name: 'Settings' })).toBeNull();
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

  /*
   * *** THE GUARD MOVED SURFACE ON 2026-09-15, AND WIDENED RATHER THAN
   * NARROWED. Statistics was promoted back to primary navigation, so the
   * Settings advanced-surfaces DESCRIPTION it used to read no longer exists —
   * a destination in the sidebar is not described in Settings. ***
   *
   * DELETING THE CASE WAS THE WRONG ANSWER, and stating why is the point: the
   * banned CLAIM is not "a paragraph in Settings is wrong", it is "this
   * product tells a scientist it has per-person figures when
   * `MyStats.tsx` renders `ChartAccessPending` on every branch". Promotion
   * makes that claim MORE reachable, not less — the destination is now one
   * click from every screen.
   *
   * So the ban is re-pointed at the Statistics SCREEN itself, which is where
   * such a promise would now be made. The `.toMatch` positive control is
   * re-pointed with it: it asserts the screen's own <h1>, so a Statistics page
   * that failed to render cannot pass this test by having no text to ban —
   * which is the vacuity failure the struck version's own comment warned about.
   */
  it('never promises per-person figures, in any of six phrasings', async () => {
    stubFetchDown();
    const { container } = renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { level: 1, name: 'Statistics' });

    const text = (container.textContent ?? '').replace(/\s+/g, ' ');

    // The positive control: this test must be reading a rendered Statistics
    // surface, not an empty container. Without it the ban passes vacuously.
    expect(text).toMatch(/Statistics/);

    for (const pattern of PERSONAL_CLAIM_PHRASINGS) {
      expect(
        text,
        `the Statistics surface promises per-person figures (${pattern}), but ` +
          `MyStats renders ChartAccessPending on every branch — there is no personal ` +
          `figure in this build to show`
      ).not.toMatch(pattern);
    }
  });
});

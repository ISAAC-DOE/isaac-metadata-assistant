import { describe, it, expect, afterEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, fireEvent, within, act, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from 'react-router-dom';

import { SettingsPage } from '../screens/SettingsPage';
import { titleCase } from '../lib/labels';
import {
  SETTINGS_TAB_ALIASES,
  SETTINGS_TAB_IDS,
  ROUTES,
  isSettingsTab,
  isSettingsTabAlias,
  resolveSettingsTab,
} from '../lib/routes';
import {
  ABOUT_RESPONSE_FIELDS,
  API_ACCESS_COPY,
  API_ACCESS_ROWS,
  API_KEY_REQUIREMENTS,
  GOVERNANCE_POLICY,
  OVERVIEW_SAFETY_ROWS,
  PRIVACY_QUESTIONS,
  REPO_DOCS,
  SETTINGS_SOURCE_ENDPOINTS,
  settingsAboutCopy,
  settingsConcepts,
  settingsFactsFrom,
  syntheticWorkspaceRow,
} from '../lib/settingsContent';
import {
  stubFetchRoutes,
  stubFetchDown,
  aboutResponse,
  aboutResponseNoCommit,
  graphStatusAvailable,
  openApiFixture,
  assistantCompanionUnconfigured,
} from '../test/apiFixtures';

/**
 * P36.4 gave Settings two functional sections; P36R Slice 9 reorganised the
 * surface into four local page tabs — Overview · Data & Privacy · About · API —
 * and turned the API section into a master-detail browser over `GET /api/openapi`
 * (the app's real generated contract: no CDN, no Swagger UI / ReDoc).
 *
 * P36V PR3 slice B deduplicated the copy: six claims were authored two or three
 * times across the tabs (two of them character-for-character), so every
 * canonical definition now lives once in `lib/settingsContent.ts` and Overview
 * renders only ONE-LINE summaries of them. The anti-regression guard for that
 * whole slice is the "appears exactly once" suite at the bottom of this file —
 * it counts each canonical string across all tabs and requires exactly 1.
 *
 * P36V-1 slices 11–13 changed the tab STRUCTURE, and this file asserts the new
 * contract rather than the old one:
 *
 *   · FIVE page tabs. `API` became `API Access`, and the endpoint browser was
 *     promoted out of a nested `keys | docs` sub-tablist into its own top-level
 *     `Endpoint Explorer` tab. The sub-tablist is GONE, and a guard below fails
 *     if any second tablist reappears on the page.
 *   · The active tab is DERIVED from `?tab=`, exactly as GovernancePage derives
 *     its own, so every tab is deep-linkable, survives a refresh, and is walked
 *     by Back/Forward. `useState` is gone, and a guard below fails if selecting a
 *     tab stops writing the URL.
 *   · The API-access copy joined `lib/settingsContent.ts`, so the "appears
 *     exactly once" suite now counts those strings too — across five surfaces.
 *
 * The two counts above are what P36V-1 left, and they are left standing as the
 * record of that slice rather than edited to match today. Since then R0 added
 * `Help & Tutorial` and this slice added `Connect Your Agent`, so the page now
 * has SEVEN tabs and `SURFACES` walks SIX of them — Help is deliberately absent
 * from `SURFACES`, being the one tab a reader acts on rather than reads. Read
 * `SETTINGS_TABS` and `SURFACES` for the current numbers; do not read them here.
 *
 * Guards preserved from P36.4/P36R/P36V: the honest `not set` build-commit
 * branch, the truth-vs-memory + no-guessing copy, the repository doc names
 * rendered as inert `<code>`, the HTTP method conveyed by TEXT, the honest
 * `No parameters.` state, and — unweakened — the forbidden-infrastructure
 * substring list.
 */

/** The page-level tablist's `aria-label` (`SettingsPage`'s `SettingsSectionTabs`). */
const SETTINGS_TABLIST_NAME = 'Settings sections';

const ABOUT_URL = 'GET /api/about';
const OPENAPI_URL = 'GET /api/openapi';
const GRAPH_STATUS_URL = 'GET /api/graph/status';

/**
 * A probe inside the router. It exposes the live location and the real
 * `navigate`, so a test can read what the tab selection wrote to the URL and
 * press the browser's Back and Forward buttons (`navigate(-1)` / `navigate(1)`)
 * exactly as a user would. Same instrument as `graph-command-bar.test.tsx`,
 * for the same reason: a data router builds a `Request` per navigation, which
 * fights the stubbed global `fetch`.
 */
let probeSearch = '';
let probeNavigate: NavigateFunction | null = null;
function RouterProbe() {
  probeSearch = useLocation().search;
  probeNavigate = useNavigate();
  return null;
}

function renderSettings(entry = '/settings') {
  probeSearch = '';
  probeNavigate = null;
  return render(
    <MemoryRouter
      initialEntries={[entry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <SettingsPage />
      <RouterProbe />
    </MemoryRouter>,
  );
}

const search = () => probeSearch;
const back = () => act(() => probeNavigate?.(-1));
const forward = () => act(() => probeNavigate?.(1));

function fullRoutes() {
  return {
    [ABOUT_URL]: { body: aboutResponse },
    [OPENAPI_URL]: { body: openApiFixture },
    // Copy Diagnostics' memory-provenance rows (About tab). Page-level, like the
    // other two, so a tab switch never re-hits it — see the fetch-count test.
    [GRAPH_STATUS_URL]: { body: graphStatusAvailable },
    /* The companion-link read (Connect Your Agent tab). NOT page-level: the route
       re-reads the environment per request so an operator's change is never
       reported from a cached value, so the section issues it where it renders.
       Stubbed with the DEFAULT state — `unconfigured` — so this file's
       forbidden-substring sweep and heading-outline checks run over the state
       the overwhelming majority of deployments are in, rather than over the
       failed-read branch an unstubbed route would produce. */
    'GET /api/runtime/assistant-companion': { body: assistantCompanionUnconfigured },
  };
}

const tab = (name: string) => screen.getByRole('tab', { name });

/** Let every stubbed read settle (the stubs resolve on the next tick). */
async function flushReads() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30));
  });
}

/** Rendered text and authored strings compared on equal terms: JSX collapses a
 *  wrapped literal to single spaces, so both sides are normalized the same way. */
const norm = (s: string) => s.replace(/\s+/g, ' ').trim();

function countOccurrences(haystack: string, needle: string): number {
  let count = 0;
  let from = 0;
  for (;;) {
    const at = haystack.indexOf(needle, from);
    if (at < 0) return count;
    count += 1;
    from = at + needle.length;
  }
}

/** Switch tabs the way a user does — by activating the tab button. */
function openTab(name: string) {
  fireEvent.click(tab(name));
}

/** The page-level tablist, resolved by its accessible name. */
const pageTablist = () => screen.getByRole('tablist', { name: SETTINGS_TABLIST_NAME });

/**
 * The label of the currently selected PAGE tab.
 *
 * Every settings panel is `aria-labelledby` its own tab, so this string is also
 * that panel's accessible name — which is how the guards below resolve the
 * panel. Read from the one tab whose `aria-selected` is `true`, never from a
 * position and never from a hand-copied label list that could drift from
 * `SETTINGS_TABS`.
 *
 * The `within(pageTablist())` scope is load-bearing, not decoration: a loaded
 * Endpoint Explorer also renders the Code Examples language tablist, whose own
 * `cURL` tab is `aria-selected="true"` too — so an unscoped search for "the
 * selected tab" finds TWO.
 */
function selectedTabLabel(): string {
  const selected = within(pageTablist())
    .getAllByRole('tab')
    .filter((t) => t.getAttribute('aria-selected') === 'true');
  expect(selected, 'exactly one selected page tab').toHaveLength(1);
  return accessibleTextOf(selected[0]);
}

/**
 * A tab's name-from-content, which is NOT its `textContent`.
 *
 * The first tab of the Advanced group carries a visible `aria-hidden` group
 * marker, so its `textContent` reads "AdvancedAPI Access" while its accessible
 * name is "API Access" — and the panel is `aria-labelledby` the tab, so the
 * panel's name is the accessible one. Reading `textContent` here made this
 * helper hand `getByRole('tabpanel', { name })` a string no panel has.
 */
function accessibleTextOf(el: Element): string {
  const clone = el.cloneNode(true) as HTMLElement;
  clone.querySelectorAll('[aria-hidden="true"]').forEach((n) => n.remove());
  return clone.textContent ?? '';
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- tab structure ------------------------------------------------------------

describe('Settings — tabs', () => {
  /*
   * FOUR TABS SINCE 2026-10-12 (`DEC-28`'s regroup, built). The seven-tab row —
   * Overview · Data & Privacy · About · Help & Tutorial · [Advanced] API Access ·
   * Endpoint Explorer · Connect Your Agent — measured 9,168 words with the same
   * build facts on two tabs and the same boundaries on three. Its material now
   * sits in four tabs of question widgets, and every retired id is an ALIAS
   * (asserted in the deep-link suite below), so no URL a reader holds went dead.
   *
   * Asserted on the ACCESSIBLE name, as before, so a decorative node inside a
   * tab could never be pinned into its name.
   */
  it('renders exactly the four specified tabs, with Overview selected by default', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map(accessibleTextOf)).toEqual([
      'Overview',
      'Privacy & Governance',
      'Integrations',
      'Advanced',
    ]);
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'settings-tabpanel-overview');
    // Every retired tab label is gone from the row — the material moved, the tabs went.
    for (const retired of [
      'API',
      'API Keys',
      'Documentation',
      'Data & Privacy',
      'About',
      'Help & Tutorial',
      'API Access',
      'Endpoint Explorer',
      'Connect Your Agent',
    ]) {
      expect(screen.queryByRole('tab', { name: retired }), retired).toBeNull();
    }
  });

  /*
   * THE "ADVANCED" GROUP MARKER IS RETIRED, AND THESE ASSERTIONS ARE ITS
   * INVERSION RATHER THAN ITS DELETION. Until 2026-10-12 three of seven tabs
   * carried a visible "Advanced" group label (generated content on the first
   * grouped tab) and an `aria-describedby` description on all three, because
   * the group was a LABEL on a flat tablist. Advanced is now a TAB, so a group
   * label would name a tab after itself. What this pins is that the scaffolding
   * went with the row and did not linger as an orphan.
   */
  it('carries no group marker, description, or orphaned group node — Advanced is a tab now', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(pageTablist().querySelectorAll('[data-group]')).toHaveLength(0);
    expect(pageTablist().querySelector('.section-tab-group-start')).toBeNull();
    expect(document.getElementById('settings-tab-group-advanced')).toBeNull();
    for (const t of screen.getAllByRole('tab')) {
      expect(t, `${t.textContent}: no group description`).not.toHaveAttribute('aria-describedby');
      /* The label exactly — nothing to run into it. Since 2026-10-18 a tab may
         carry a SHORT form for a narrow row beside its full label; the short form
         is `aria-hidden`, so the full label alone is still the tab's name. */
      const full = t.querySelector('.section-tab-label-full');
      const short = t.querySelector('.section-tab-label-short');
      expect(short === null || short.getAttribute('aria-hidden') === 'true', 'short label hidden').toBe(true);
      expect((full ?? t).textContent).toBe(accessibleTextOf(t));
    }
    // The retired generated-content rule is gone from the stylesheet too, not
    // merely unreferenced.
    const css = readFileSync(resolve(__dirname, '..', 'screens/screens.css'), 'utf8');
    expect(css).not.toMatch(/\.section-tab-group-start::before/);
  });

  it('the tablist owns exactly four tabs and nothing else', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    /* Asserted over the DOM children: `role="tablist"` may only own `role="tab"`
       children (`aria-required-children`), which a name assertion would not see. */
    const children = Array.from(pageTablist().children);
    expect(children).toHaveLength(4);
    for (const child of children) {
      expect(child.getAttribute('role'), `${child.textContent}: a tablist child is a tab`).toBe('tab');
    }
  });

  /*
   * ~~The count above holds only while the stubbed fetches are still
   * unresolved~~ — FIXED 2026-10-18 (independent review), and the old comment
   * is the defect it describes: this test counted BEFORE the reads resolved, so
   * it passed vacuously while the loaded Advanced tab carried a second, nested
   * tablist (the Endpoint Explorer's Code Examples). That switch is now a toggle
   * group, and this test waits for every read — and for the Explorer's detail
   * pane, where Code Examples render — before it counts. `getAllByRole` counts
   * a tablist inside a CLOSED `<details>` too only if it is in the accessibility
   * tree, so the count is also taken over the DOM, which cannot miss one.
   */
  it('has exactly ONE tablist on every tab, once every read has resolved', async () => {
    for (const id of [...SETTINGS_TAB_IDS, ...Object.keys(SETTINGS_TAB_ALIASES)]) {
      stubFetchRoutes(fullRoutes());
      const view = renderSettings(`/settings?tab=${id}`);
      await flushReads();
      if (id === 'advanced' || id === 'explorer') {
        await screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 });
        expect(view.container.querySelector('details.api-samples'), `${id}: Code Examples mounted`).not.toBeNull();
      }
      const lists = screen.getAllByRole('tablist');
      expect(lists, `${id}: expected one tablist`).toHaveLength(1);
      expect(view.container.querySelectorAll('[role="tablist"]'), `${id}: DOM tablists`).toHaveLength(1);
      expect(lists[0], `${id}: the one tablist is the page's`).toBe(pageTablist());
      view.unmount();
    }
  });

  /*
   * THE WIDGETS' VIEW SWITCHES ARE TOGGLE GROUPS, and that is the property that
   * lets them exist at all on a page that refuses a second tablist. Pinned once
   * the data has loaded, when every switch on every tab is mounted.
   */
  /* Re-pointed 2026-10-18 from the retired local `.settings-switch` to the shared
     widget switch (`.widget-views`) — and given a FLOOR per tab, because a
     selector that matches nothing makes every assertion in the loop vacuous,
     which is exactly how this test would have survived the rename silently. */
  it('every in-widget view switch is a group of aria-pressed buttons, never a tablist', async () => {
    const floor: Record<string, number> = { overview: 1, privacy: 0, integrations: 2, advanced: 1 };
    for (const id of SETTINGS_TAB_IDS) {
      stubFetchRoutes(fullRoutes());
      const view = renderSettings(`/settings?tab=${id}`);
      await flushReads();
      if (id === 'advanced') await screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 });
      const groups = Array.from(view.container.querySelectorAll('.widget-views'));
      expect(groups.length, `${id}: view switches found`).toBeGreaterThanOrEqual(floor[id]);
      for (const group of groups) {
        expect(group.getAttribute('role'), `${id}: a switch is a group`).toBe('group');
        expect(group.getAttribute('aria-label'), `${id}: the switch is named`).toBeTruthy();
        for (const option of Array.from(group.children)) {
          expect(option.tagName).toBe('BUTTON');
          expect(option.getAttribute('role')).toBeNull();
          expect(['true', 'false']).toContain(option.getAttribute('aria-pressed'));
          // Every option names the panel it shows, and that panel is mounted.
          const controls = option.getAttribute('aria-controls');
          expect(controls && document.getElementById(controls), `${id}: panel mounted`).toBeTruthy();
        }
      }
      view.unmount();
    }
  });

  /*
   * WCAG 2.4.11 at 320px (re-review, 2026-10-18), SOLVED BY LAYOUT, NOT BY
   * SCROLLING. The narrow tab row used to scroll sideways, and `?tab=advanced`
   * left the selected tab off-screen; a `scrollIntoView` fixed that, and then CI's
   * layout sweep refused the sideways-scrolling region outright (on CI's font the
   * row measured ~317px against a 312px box at 390). So the row now always FITS:
   * one row of short labels down to 441px, two rows of two below. jsdom computes
   * no layout, so the rules that guarantee it are what is pinned — and the
   * absence of the scroll machinery, so a horizontal scroller cannot creep back.
   */
  it('keeps the narrow tab row from ever scrolling sideways', () => {
    const css = readFileSync(resolve(__dirname, '..', 'screens/settings/settings-widgets.css'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '');
    const rulesFor = (selector: string) =>
      [...css.matchAll(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{([^}]*)\\}`, 'g'))]
        .map((m) => m[1])
        .join('\n');
    const tabRow = rulesFor('.settings-section-tabs');
    expect(tabRow).not.toMatch(/overflow-x\s*:\s*(auto|scroll)/);
    expect(tabRow).toMatch(/display\s*:\s*grid/);
    expect(tabRow).toMatch(/grid-template-columns\s*:\s*repeat\(2,/);
    expect(css).toMatch(/@media \(max-width: 440px\)/);
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=advanced');
    expect(pageTablist()).not.toHaveAttribute('data-overflowing');
  });

  it('uses a roving tabindex: only the selected tab is in the tab order', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(tab('Overview')).toHaveAttribute('tabindex', '0');
    expect(tab('Integrations')).toHaveAttribute('tabindex', '-1');
    expect(tab('Advanced')).toHaveAttribute('tabindex', '-1');
    expect(screen.getAllByRole('tab').filter((t) => t.getAttribute('tabindex') === '0')).toHaveLength(1);
  });

  it('only the selected tab points at a panel via aria-controls', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(tab('Overview')).toHaveAttribute('aria-controls', 'settings-tabpanel-overview');
    expect(tab('Privacy & Governance')).not.toHaveAttribute('aria-controls');
    expect(tab('Advanced')).not.toHaveAttribute('aria-controls');
  });

  it('every tab renders exactly one panel, labelled by its own tab', () => {
    for (const id of SETTINGS_TAB_IDS) {
      stubFetchRoutes(fullRoutes());
      const view = renderSettings(ROUTES.settingsTab(id));
      const panels = screen.getAllByRole('tabpanel');
      expect(panels, `${id}: expected one panel`).toHaveLength(1);
      /* Resolve the SETTINGS panel by its accessible name — each panel is
         `aria-labelledby` its own tab — rather than positionally: once the
         Endpoint Explorer has its contract, its Code Examples section renders a
         nested tabpanel of its own. */
      const panel = screen.getByRole('tabpanel', { name: selectedTabLabel() });
      expect(panel, `${id}: panel resolved by name`).toHaveAttribute(
        'id',
        `settings-tabpanel-${id}`,
      );
      expect(panel).toHaveAttribute('aria-labelledby', `settings-tab-${id}`);
      view.unmount();
    }
  });

  it('clicking a tab switches the rendered panel', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Privacy & Governance');
    expect(tab('Privacy & Governance')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'settings-tabpanel-privacy');
  });

  it('Arrow / Home / End move the selection (automatic activation)', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();

    fireEvent.keyDown(tab('Overview'), { key: 'ArrowRight' });
    expect(tab('Privacy & Governance')).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(tab('Privacy & Governance'), { key: 'End' });
    expect(tab('Advanced')).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(tab('Advanced'), { key: 'Home' });
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');

    // Wraps from the first tab to the last…
    fireEvent.keyDown(tab('Overview'), { key: 'ArrowLeft' });
    expect(tab('Advanced')).toHaveAttribute('aria-selected', 'true');

    // …and walks back through all four, so the wrap is over the real list.
    fireEvent.keyDown(tab('Advanced'), { key: 'ArrowLeft' });
    expect(tab('Integrations')).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(tab('Integrations'), { key: 'ArrowLeft' });
    expect(tab('Privacy & Governance')).toHaveAttribute('aria-selected', 'true');
  });

  it('keyboard selection moves focus with it, so the arrow keys stay usable', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    tab('Overview').focus();
    fireEvent.keyDown(tab('Overview'), { key: 'End' });
    expect(tab('Advanced')).toHaveFocus();
    expect(tab('Advanced')).toHaveAttribute('tabindex', '0');
  });

  it('states plainly that there is nothing to configure (no invented settings)', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(screen.getByText(/no user-adjustable settings/i)).toBeInTheDocument();
    // Nothing on this page is an input except the API search field.
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});

// --- deep-linkable tabs (`?tab=`) ---------------------------------------------

/**
 * P36V-1 slice 12. Both tab levels used to be plain `useState`: nothing was
 * linkable and everything reset on refresh. The page now derives the active tab
 * from `?tab=`, the SAME mechanism GovernancePage uses — a query VALUE, so the
 * router basename ('' locally, '/krish' deployed) is honoured automatically and
 * no screen writes a base path.
 */
describe('Settings — deep-linkable tabs (?tab=)', () => {
  it('opens the tab named by ?tab=, for every tab id', () => {
    for (const id of SETTINGS_TAB_IDS) {
      stubFetchRoutes(fullRoutes());
      const view = renderSettings(ROUTES.settingsTab(id));
      const selected = screen.getAllByRole('tab').filter(
        (t) => t.getAttribute('aria-selected') === 'true',
      );
      expect(selected, `${id}: exactly one selected tab`).toHaveLength(1);
      expect(selected[0]).toHaveAttribute('id', `settings-tab-${id}`);
      view.unmount();
    }
  });

  /*
   * EVERY RETIRED TAB ID STILL RESOLVES (2026-10-12). Seven ids became four tabs,
   * and the five that no longer name a tab are URLs a reader may hold — the
   * walkthrough prints `?tab=help`, the voice-capture view links `?tab=mcp`,
   * Statistics links `?tab=explorer`. Each must land on the tab holding that
   * material AND bring the widget it named into view; "lands on a tab" alone
   * would pass with the reader parked two widgets away from what they clicked.
   */
  it.each([
    ['about', 'overview', 'This Build'],
    ['help', 'overview', 'Guided Walkthrough'],
    ['api', 'integrations', 'API Access'],
    ['mcp', 'integrations', 'Connect Your Agent'],
    ['explorer', 'advanced', 'Endpoint Explorer'],
  ] as const)('the retired id ?tab=%s lands on %s and scrolls its widget into view', async (alias, canonical, widget) => {
    const scrolled: Element[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this);
    };
    try {
      stubFetchRoutes(fullRoutes());
      renderSettings(`/settings?tab=${alias}`);
      expect(isSettingsTabAlias(alias)).toBe(true);
      expect(resolveSettingsTab(alias).tab).toBe(canonical);
      expect(screen.getByRole('tabpanel')).toHaveAttribute('id', `settings-tabpanel-${canonical}`);
      const region = screen.getByRole('region', { name: widget });
      await waitFor(() => expect(scrolled).toContain(region));
      // Nothing is rewritten: the URL a reader followed is the URL they keep.
      expect(search()).toBe(`?tab=${alias}`);
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it('?tab=api opens Integrations with the key state as a STATE, not a disabled button', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=api');
    expect(tab('Integrations')).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(API_ACCESS_COPY.statusHeading)).toBeInTheDocument();
    // INVERTED, 2026-10-12. This test used to require a `disabled` Create API
    // Key button. An absent capability is now stated, never offered as a control
    // that cannot be pressed — so the button must NOT exist.
    expect(screen.queryByRole('button', { name: /Create API Key/i })).toBeNull();
  });

  it('?tab=explorer opens Advanced with the contract rendered', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=explorer');
    expect(tab('Advanced')).toHaveAttribute('aria-selected', 'true');
    expect(
      await screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 }),
    ).toBeInTheDocument();
    expect(screen.getByText(`${ENDPOINT_COUNT} of ${ENDPOINT_COUNT} endpoints`)).toBeInTheDocument();
  });

  it.each([
    ['no query at all', '/settings'],
    ['an empty value', '/settings?tab='],
    ['an unrecognised value', '/settings?tab=not-a-tab'],
    ['the retired sub-tab value', '/settings?tab=docs'],
    ['a value differing only in case', '/settings?tab=API'],
  ])('falls back to Overview for %s, with no dead route', (_what, entry) => {
    stubFetchRoutes(fullRoutes());
    renderSettings(entry);
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'settings-tabpanel-overview');
    // A fallback, not an error: the page renders its normal content.
    expect(screen.getByText(/no user-adjustable settings/i)).toBeInTheDocument();
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });

  it('the tab id guard accepts exactly the four ids, and the alias guard exactly the five retired ones', () => {
    for (const id of SETTINGS_TAB_IDS) expect(isSettingsTab(id)).toBe(true);
    expect([...SETTINGS_TAB_IDS]).toEqual(['overview', 'privacy', 'integrations', 'advanced']);
    expect(Object.keys(SETTINGS_TAB_ALIASES).sort()).toEqual(['about', 'api', 'explorer', 'help', 'mcp']);
    for (const alias of Object.keys(SETTINGS_TAB_ALIASES)) {
      expect(isSettingsTab(alias), `${alias} is an alias, not a tab`).toBe(false);
      expect(isSettingsTabAlias(alias)).toBe(true);
    }
    for (const bad of ['', 'API', 'docs', 'keys', 'overview ', 'toString', null, undefined]) {
      expect(isSettingsTab(bad), `must reject ${JSON.stringify(bad)}`).toBe(false);
      expect(isSettingsTabAlias(bad), `must not alias ${JSON.stringify(bad)}`).toBe(false);
    }
  });

  /**
   * `ROUTES.settingsTab` has NO in-page consumer by design (see `lib/routes.ts`):
   * the page switches tabs with `setSearchParams` over a copy of the current
   * params, which preserves any other query parameter. This is the anti-drift
   * guard: the helper and the real mechanism produce the same query string for
   * EVERY tab.
   */
  it('the link helper and the page’s own tab mechanism agree for every tab', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    for (const [id, label] of [
      ['privacy', 'Privacy & Governance'],
      ['integrations', 'Integrations'],
      ['advanced', 'Advanced'],
      ['overview', 'Overview'],
    ] as const) {
      openTab(label);
      // A query VALUE, never a path segment...
      expect(search()).toBe(`?tab=${id}`);
      // ...and byte-identical to what the deep-link helper builds for that tab.
      expect(`/settings${search()}`).toBe(ROUTES.settingsTab(id));
      // Neither hard-codes a base path: a deployed basename must not appear.
      expect(search()).not.toContain('/krish');
    }
  });

  it('Back and Forward walk the tabs, because selecting one PUSHES', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');

    openTab('Privacy & Governance');
    openTab('Integrations');
    expect(tab('Integrations')).toHaveAttribute('aria-selected', 'true');

    back();
    expect(tab('Privacy & Governance')).toHaveAttribute('aria-selected', 'true');
    expect(search()).toBe('?tab=privacy');

    back();
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');

    forward();
    expect(tab('Privacy & Governance')).toHaveAttribute('aria-selected', 'true');
    forward();
    expect(tab('Integrations')).toHaveAttribute('aria-selected', 'true');
  });

  it('a deep-linked tab survives a refresh (a fresh mount at the same URL)', async () => {
    stubFetchRoutes(fullRoutes());
    const first = renderSettings('/settings?tab=advanced');
    await screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 });
    first.unmount();

    // Re-mounting at the same entry is what a reload does: no client state
    // carries over, so the tab can only come back from the URL.
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=advanced');
    expect(tab('Advanced')).toHaveAttribute('aria-selected', 'true');
    expect(
      await screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 }),
    ).toBeInTheDocument();
  });

  it('an in-app deep link into one tab preserves every other query parameter', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?keep=me&tab=about');
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');
    openTab('Integrations');
    expect(search()).toContain('keep=me');
    expect(search()).toContain('tab=integrations');
  });

  /** Every page-level fetch is issued ONCE, so the tabs are pure client state:
   *  no tab switch, and no Back/Forward, may re-hit the backend. */
  it('switching tabs never re-hits the backend', async () => {
    const hits = stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    const initial = [...hits];
    expect(initial.filter((h) => h === ABOUT_URL)).toHaveLength(1);
    expect(initial.filter((h) => h === OPENAPI_URL)).toHaveLength(1);
    expect(initial.filter((h) => h === GRAPH_STATUS_URL)).toHaveLength(1);

    for (const name of ['Privacy & Governance', 'Advanced', 'Overview']) {
      openTab(name);
    }
    await screen.findByText('0.1.0');
    back();
    forward();

    // Integrations is opened on its own and its one SECTION-level read — the
    // companion link, re-read per mount by design (see `AssistantCompanion.tsx`)
    // — is the only request any tab switch may add.
    const pageLevel = (list: string[]) =>
      list.filter((h) => h !== 'GET /api/runtime/assistant-companion');
    expect(pageLevel(hits)).toEqual(pageLevel(initial));
  });
});

// --- Overview -----------------------------------------------------------------

describe('Settings — Overview', () => {
  it('shows a loading state before the fetch resolves', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    // Both widgets that wait on `/api/about` say so, each inside itself.
    expect(screen.getAllByText('Loading app info…').length).toBeGreaterThan(0);
  });

  it('summarizes the runtime from the live endpoint, never a hardcoded claim', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(await screen.findByText('0.1.0')).toBeInTheDocument();
    expect(screen.getByText('v1.05')).toBeInTheDocument();
    expect(screen.getByText('ephemeral')).toBeInTheDocument();
    expect(screen.getByText('isaac_records')).toBeInTheDocument();
    // runtime_mode and data_regime are distinct fields that happen to share a value.
    expect(screen.getAllByText('synthetic-only')).toHaveLength(2);
    // P36V PR3: Build Commit joined the runtime snapshot — SHORT sha only.
    expect(screen.getByText('fakecommit00')).toBeInTheDocument();
  });

  /**
   * Overview is a SUMMARY, and since 2026-10-12 a narrower one. It used to carry
   * all twelve boundary summaries ("Boundaries at a Glance"); Privacy & Governance
   * now shows every one of them as a visible row, so Overview's Data Safety widget
   * carries only the four question-level lines `OVERVIEW_SAFETY_ROWS` names —
   * each a concept summary, never a new sentence — and renders no definition.
   * INVERTED from "every boundary on Overview": that requirement was the second
   * copy the redesign exists to remove.
   */
  it('carries the four Data Safety lines — vetted summaries only — and no definition', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await screen.findByText('0.1.0');

    const concepts = settingsConcepts(settingsFactsFrom(aboutResponse));
    const byId = new Map(concepts.map((c) => [c.id, c]));
    const rows = Array.from(container.querySelectorAll('.settings-row'));
    expect(rows.map((r) => r.querySelector('dt')?.textContent)).toEqual(
      OVERVIEW_SAFETY_ROWS.map((r) => r.label),
    );
    rows.forEach((row, i) => {
      const expected = OVERVIEW_SAFETY_ROWS[i].items
        .map((item) =>
          'concept' in item ? byId.get(item.concept)!.summary : GOVERNANCE_POLICY[item.policy].summary,
        )
        .join(' ');
      expect(norm(row.querySelector('dd')?.textContent ?? '')).toBe(norm(expected));
    });
    const text = norm(container.textContent ?? '');
    for (const concept of concepts) {
      expect(text, `Overview must NOT define "${concept.heading}"`).not.toContain(norm(concept.detail));
    }
    // Nor does it carry a governance paragraph in full — only its one-line form.
    for (const id of ['reviewTools', 'diagnostic'] as const) {
      expect(text, `Overview must NOT carry the full ${id} paragraph`).not.toContain(
        norm(GOVERNANCE_POLICY[id].text),
      );
    }
    // And it points at the canonical home rather than restating the rest.
    const link = screen.getByRole('link', { name: 'All Boundaries' });
    expect(link.getAttribute('href')).toBe('/settings?tab=privacy');
  });

  /*
   * HONESTY BY OMISSION, closed 2026-10-18 (independent review). Under the
   * question "What Leaves", a row that named only telemetry and model calls read
   * as "nothing leaves" — while a downloaded export is, by the canonical
   * Exporting a Record boundary, beyond this app, and the read-only diagnostic
   * returns aggregate output. Under "What Enters", a row that named only the
   * refused upload read as "no file is read" — while the Validator and CSV
   * reconciliation DO read a file the reader chooses. Each question must name
   * every path its answer is true or false of, in its one-line form.
   */
  it('What Enters names the two review tools that read a chosen file', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await screen.findByText('0.1.0');
    const row = Array.from(container.querySelectorAll('.settings-row')).find(
      (r) => r.querySelector('dt')?.textContent === 'What Enters',
    )!;
    const text = row.querySelector('dd')?.textContent ?? '';
    expect(text).toMatch(/upload route refuses every request/i);
    expect(text).toMatch(/\bValidator\b/);
    expect(text).toMatch(/CSV reconciliation/i);
    expect(text).toMatch(/read a file you pick or text you paste/i);
    expect(text).toMatch(/only the outcome/i);
  });

  it('What Leaves names the download and the diagnostic, not only what does NOT leave', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await screen.findByText('0.1.0');
    const row = Array.from(container.querySelectorAll('.settings-row')).find(
      (r) => r.querySelector('dt')?.textContent === 'What Leaves',
    )!;
    const text = row.querySelector('dd')?.textContent ?? '';
    // The export: what crosses out of the app, said in the canonical boundary's words.
    expect(text).toMatch(/downloading one happens in your browser and puts the copy beyond this app/i);
    // The diagnostic's aggregate output, with every bound a reader needs beside it.
    expect(text).toMatch(/protected, read-only diagnostic/i);
    expect(text).toMatch(/sanitized aggregates only/i);
    expect(text).toMatch(/no record displayed/i);
    expect(text).toMatch(/nothing sent to a model/i);
    // ...and still the two negatives it had.
    expect(text).toMatch(/measures and transmits nothing about your session/i);
    expect(text).toMatch(/No language model at all/i);
  });

  /**
   * Anti-overstatement guards. Each of these sentences replaced a claim the
   * backend falsifies, so they are asserted here to keep the stronger, false
   * version from coming back:
   *   - persistence is a FILESYSTEM workspace, not process memory (Overview says
   *     the workspace is files rather than a database, and the filesystem detail
   *     lives in Data & Privacy). Slice 2A (I5) sweep: the summary used to open
   *     "No database —", a flat claim about the deployment that stopped being
   *     true once an isolated SLAC test database could be configured for the
   *     protected read-only diagnostic. The needle below pins the same
   *     files-not-a-database point in the re-scoped wording — the guard is
   *     unchanged in force, only the sentence it quotes moved;
   *   - `ApiKeyAuthMiddleware` is live in-application auth, so restriction is
   *     not necessarily external and this screen cannot tell either way;
   *   - there is NO real-vs-synthetic detector anywhere in the backend.
   */
  it('does not claim a restart clears state, nor that access restriction is always external', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');

    expect(
      screen.getByText(/the workspace is files on the server, not a database/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/gone when it restarts/i)).not.toBeInTheDocument();
    // The filesystem-lifetime detail is Data & Privacy's, and only its.
    expect(
      screen.queryByText(/restarting the backend process does not by itself clear it/i),
    ).not.toBeInTheDocument();

    expect(screen.queryByText(/outside the application/i)).not.toBeInTheDocument();
    // The access caveat is the Authentication Boundary row's, on Privacy &
    // Governance — Overview no longer carries that row (see the test above).
    openTab('Privacy & Governance');
    expect(
      screen.getByText(/this screen cannot report whether access is restricted/i),
    ).toBeInTheDocument();
  });

  /**
   * Authentication has no STATUS row and never will: the shared key is
   * configured where the browser cannot see it, so Overview states the
   * uncertainty instead of an "active"/"inactive" claim it cannot verify.
   */
  it('never claims authentication is active or inactive', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await screen.findByText('0.1.0');

    /* Read from `.settings-figure-label`, not from the whole `<dt>`: each row
       now carries a visible PROVENANCE word beside its label ("read per
       request" / "fixed for this build"), so `dt.textContent` is the label and
       the qualifier concatenated. The assertion is unchanged in what it
       checks — which status rows exist, and in what order — and the provenance
       is asserted on its own immediately below, so nothing is lost by scoping
       this one to the label. */
    const labels = Array.from(container.querySelectorAll('.settings-figure-label')).map(
      (el) => el.textContent,
    );
    // The same seven rows, now in This Build's two views (Build, then Runtime).
    expect(labels).toEqual([
      'App Version',
      'Build Commit',
      'Record Schema',
      'Core',
      'Runtime Mode',
      'Data Regime',
      'Persistence',
    ]);

    /*
     * THE PROVENANCE OF EVERY ROW, ASSERTED — which is the point of moving it
     * out of the card's supporting sentence. That sentence had to enumerate
     * which rows were live and which were fixed, and it has been WRONG TWICE
     * (see `OverviewTab`'s header). A per-row mark is checkable, and this is
     * the check: `Build Commit`, `Runtime Mode` and `Persistence` are resolved
     * per request; the other four are fixed for a given image.
     *
     * `Build Commit` being LIVE is the half most likely to be "corrected" back
     * to `build` by someone reading its name: `routes._build_commit()` reads
     * `ISAAC_BUILD_COMMIT` from the environment on every request, so the same
     * image redeployed with a different value reports the different value.
     */
    const provenance = Array.from(container.querySelectorAll('.settings-figure')).map((row) => [
      row.querySelector('.settings-figure-label')?.textContent,
      row.querySelector('.settings-figure-source')?.textContent ?? null,
    ]);
    expect(provenance).toEqual([
      ['App Version', 'fixed for this build'],
      ['Build Commit', 'read per request'],
      ['Record Schema', 'fixed for this build'],
      ['Core', 'fixed for this build'],
      ['Runtime Mode', 'read per request'],
      ['Data Regime', 'fixed for this build'],
      ['Persistence', 'read per request'],
    ]);
    /* THE PRESENTATION OF THE PROVENANCE CHANGED, NOT ITS DECISION (2026-10-12).
       The seven visible sublabels became one clock mark on each live row, with
       the legend in the widget's info; the words remain for assistive
       technology. So: every live row — and only a live row — carries the mark. */
    for (const row of Array.from(container.querySelectorAll('.settings-figure'))) {
      const live = row.querySelector('.settings-figure-source')?.textContent === 'read per request';
      expect(row.querySelector('.settings-provenance-mark') !== null, row.textContent ?? '').toBe(live);
      expect(row.querySelector('.settings-figure-source')).toHaveClass('sr-only');
    }
    const text = norm(container.textContent ?? '').toLowerCase();
    expect(text).not.toContain('authentication: active');
    expect(text).not.toContain('authentication is active');
    expect(text).not.toContain('access is restricted by');
    expect(text).not.toContain('unrestricted');
  });

  it('says the app enforces the mode, not the contents, and cannot detect real data', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    expect(screen.getByText(/cannot tell real data from synthetic/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/refused before anything is read or extracted/i),
    ).not.toBeInTheDocument();
  });

  it('falls back to naming the reported value rather than repeating a claim the API contradicts', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: { ...aboutResponse, data_regime: 'mixed-somehow' } },
      [OPENAPI_URL]: { body: openApiFixture },
      [GRAPH_STATUS_URL]: { body: graphStatusAvailable },
      'GET /api/runtime/assistant-companion': { body: assistantCompanionUnconfigured },
    });
    renderSettings();
    expect(
      await screen.findByText(/reports the data regime as "mixed-somehow"/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/only unmistakably synthetic data is in scope/i)).not.toBeInTheDocument();
  });

  /*
   * REPLACED, AND THE REPLACEMENT IS THE POINT OF THE WHOLE SLICE.
   *
   * This test used to render `persistence: 'durable'` and assert the WEAK
   * FALLBACK — `reports persistence as "durable"` — which was the right
   * assertion while `durable` was an unreachable value that the copy therefore
   * had nothing to say about. It is reachable: `GET /api/about` served
   * `"ephemeral"` as a hardcoded literal while `GET /api/health` in the same
   * hosted process reported `experiment_storage.state: "durable"`
   * (`docs/evidence/hosted-qa-2026-08-27.md` §3). So a passing version of this
   * test coexisted with the defect, and would have kept passing after a fix that
   * only changed the backend.
   *
   * Two things are asserted now, and the SECOND is what the defect was:
   *   1. the durable arm renders instead of the fallback;
   *   2. it separates RECORD storage from the WORKSPACE DIRECTORY, rather than
   *      swapping one false composite for the opposite one. A durable
   *      deployment's exported artifacts really are lost on a restart, and the
   *      copy must keep saying so.
   */
  it('states record durability and workspace impermanence separately when persistence is durable', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: { ...aboutResponse, persistence: 'durable' } },
      [OPENAPI_URL]: { body: openApiFixture },
      [GRAPH_STATUS_URL]: { body: graphStatusAvailable },
      'GET /api/runtime/assistant-companion': { body: assistantCompanionUnconfigured },
    });
    renderSettings();
    fireEvent.click(tab('Privacy & Governance'));
    const resets = await screen.findByText(/Experiment records survive a restart/i);
    const text = resets.textContent ?? '';
    // (1) the durable arm, not the fallback.
    expect(text).toMatch(/reports persistence as durable/i);
    expect(screen.queryByText(/reports persistence as "durable"/i)).not.toBeInTheDocument();
    // (2) the two facts, both stated, neither collapsed into the other.
    expect(text).toMatch(/written to this deployment's own database/i);
    expect(text).toMatch(/the workspace is not stored in a database/i);
    expect(text).toMatch(/are not in the database/i);
    expect(text).toMatch(/reports that artifact as stale/i);
    // The retired ephemeral assertions must not survive into this state.
    expect(text).not.toMatch(/reports that storage as ephemeral/i);
    expect(screen.queryByText(/there is no database/i)).not.toBeInTheDocument();
  });

  it('names an unrecognised persistence value instead of picking the nearest branch', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: { ...aboutResponse, persistence: 'somehow-else' } },
      [OPENAPI_URL]: { body: openApiFixture },
      [GRAPH_STATUS_URL]: { body: graphStatusAvailable },
      'GET /api/runtime/assistant-companion': { body: assistantCompanionUnconfigured },
    });
    renderSettings();
    fireEvent.click(tab('Privacy & Governance'));
    // Both the visible row (the summary) and the definition name the value.
    expect(
      (await screen.findAllByText(/reports persistence as "somehow-else"/i)).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/Experiment records survive a restart/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/reports that storage as ephemeral/i)).not.toBeInTheDocument();
  });

  /**
   * THIS TEST PINNED A DEFECT AND IS INVERTED RATHER THAN DELETED, which is the
   * established remedy in this repository for a test that defends a false
   * sentence.
   *
   * It required `/creating an experiment fails outright/`. That is true of ONE of
   * `unavailable`'s two causes and false of the other: when the `PGDATABASE` gate
   * refuses the configured name, `_postgres_available()` is false, the filesystem
   * repository is selected, and `POST /api/experiments` answers **201** into a
   * working directory that is not durable (measured over HTTP with outbound
   * connections stubbed to raise; `state: "unavailable"`, `backend:
   * "filesystem"`). The old assertion therefore made the copy defect
   * unfixable-without-failing, which is the worst property a test can have.
   *
   * ~~WHAT IT NOW PINS IS THE INVARIANT THAT HOLDS UNDER BOTH CAUSES — that
   * nothing created in this state is durable~~ — STRUCK AND INVERTED AGAIN
   * 2026-08-28, one commit later, because that "invariant" is not one. Two
   * CAUSES are not two OUTCOMES: `repository()` selects the backend from
   * `_postgres_available()` alone and never consults `storage_failure()`, so
   * `state: "unavailable"` with `backend: "postgres"` leaves the Postgres
   * repository running over a failure that may be stale (a READ path, a
   * `_not_provisioned` table, or a database that has since recovered). A write
   * that then succeeds is IN PostgreSQL and IS durable. So there is a third
   * outcome, "nothing … is durable" is false under it, and "the two ways"
   * enumerated two of three. This test asserted both of those, so it had once
   * again made the copy defect unfixable-without-failing — the second time in
   * two commits, which is why the guard below stopped pinning sentences and
   * started pinning the shape of the claim.
   *
   * WHAT IT PINS NOW is what the screen ESTABLISHES rather than what is: the bad
   * news is still delivered before the button is pressed, and no durability
   * verdict is asserted in either direction. `/api/about` publishes `persistence`
   * (the state) and not `backend` (which is what separates the causes), so this
   * module still cannot tell them apart and still must not pretend to.
   */
  it('claims no durability verdict, and does not claim the create fails, when a configured database is not taking records', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: { ...aboutResponse, persistence: 'unavailable' } },
      [OPENAPI_URL]: { body: openApiFixture },
      [GRAPH_STATUS_URL]: { body: graphStatusAvailable },
      'GET /api/runtime/assistant-companion': { body: assistantCompanionUnconfigured },
    });
    renderSettings();
    fireEvent.click(tab('Privacy & Governance'));
    const resets = await screen.findByText(/reports persistence as unavailable/i);
    const text = resets.textContent ?? '';
    // The bad news, still stated before the reader acts — but as a RECORDED
    // OBSERVATION, not as a live fact. The literal that used to be pinned here
    // ("...and they are not reaching it") was itself false under outcome (c),
    // where the recorded failure is stale and records ARE reaching the database.
    // Pinning it had re-created the "unfixable-without-failing" property this
    // file's own docstring calls the worst a test can have — one level down.
    expect(text).toMatch(/to hold experiment records and the backend has recorded/i);
    // The unhedged PRESENT-TENSE antecedent must not come back, in either voice.
    expect(text).not.toMatch(/records? (?:are|is) not reaching it/i);
    expect(text).not.toMatch(/and they are not reaching it/i);
    expect(text).toMatch(/creating one may fail outright/i);
    // What the screen establishes, rather than what is.
    expect(text).toMatch(
      /nothing this screen has read establishes that a record created now is stored durably/i,
    );
    // The two retired false claims must not return.
    expect(text).not.toMatch(/fails outright rather than/i);
    expect(text).not.toMatch(/nothing you create here is durable/i);
    expect(text).not.toMatch(/which of the two ways/i);
    expect(text).not.toMatch(/experiment records survive a restart/i);
  });

  /*
   * THE INVARIANT GUARD, over the whole card set rather than over one card.
   *
   * The two sentence-level guards above were each written to defend one
   * corrected string, and each was then found to be defending a false one. The
   * SHAPE that keeps recurring is what this pins instead, across EVERY concept
   * `settingsConcepts` produces under `unavailable` — summary, detail and the
   * `more` disclosure alike — so a fourth site added later is covered without
   * anyone remembering to extend a list:
   *
   *  1. no absolute non-durability claim. False under outcome (c), the
   *     stale-or-recovered failure, where the write lands in PostgreSQL.
   *  2. no promised FATE for a record created in this state, unless hedged. The
   *     screen is given `persistence` and not `backend`, so it cannot know
   *     whether a success went to the workspace or to the database.
   *  3. no enumeration of exactly two outcomes. There are three.
   *
   * ~~(2) IS DELIBERATELY NOT A KEYWORD BAN ... which catches novel phrasings
   * rather than the ones someone happened to think of.~~ **STRUCK 2026-08-29.**
   * The first version of rule (2) WAS still a keyword ban — it merely had two
   * hand-written alternations instead of one, and an independent review drove
   * four false claims of the retired class through it green. The vocabulary gate
   * is now gone (see the note on its removal below), and rule (2) is
   * unconditional within this arm: any sentence about creating a record must
   * carry a hedge. The workspace and walkthrough sentences are unaffected — they
   * are true regardless of the outcome of a create, and they do not mention one,
   * which is why the check is per SENTENCE and not per string.
   *
   * Asserted over the pure content function, not the rendered page, because the
   * defect is in the copy and a renderer change must not be able to hide it.
   * Every matcher below was individually driven RED by a temporary mutation of
   * `settingsContent.ts` before this was committed; vitest stops at the first
   * failing assertion, so a matcher never exercised alone is a matcher never
   * tested.
   */
  it('never asserts an absolute non-durability, an unhedged fate, or two outcomes under `unavailable`', () => {
    const concepts = settingsConcepts({
      dataRegime: 'synthetic-only',
      persistence: 'unavailable',
      recordSchemaVersion: '1.05',
    });
    expect(concepts.length).toBeGreaterThan(0);

    const strings = concepts.flatMap((c) =>
      [c.summary, c.detail, c.more?.text ?? ''].filter(Boolean),
    );
    // The FOUR `unavailable` sites are all present in that set. Three were
    // enumerated in the brief for this change; the fourth (`how-long-it-is-kept`)
    // was found by this guard, having evaded the text sweep that found the
    // others because it said "outlasts the working directory" rather than
    // "durable" — which is the whole argument for a shape guard over a list.
    expect(strings.filter((t) => /were not reaching it/i.test(t))).toHaveLength(4);

    /** A clause that talks about a record being created in this state. */
    const CREATE_RECORD =
      /creating one|creating an experiment|you create\b|a record created|created here|created in this state|it succeeds/i;
    /*
     * ~~A second gate, `FATE`, used to narrow rule (2) to sentences that also used
     * location/permanence vocabulary.~~ REMOVED 2026-08-29 by independent review,
     * which drove FOUR false claims of the retired class through it GREEN:
     *
     *   · "It succeeds into the working directory above and goes when it does."
     *        — `FATE` listed `workspace` but NOT `working directory`, which is the
     *          exact phrase the retired `how-long-it-is-kept` copy used.
     *   · "Anything you create now is gone the next time this deployment is
     *     rolled out."            — `gone`/`rolled out` were in neither list.
     *   · "A record created now will not be here tomorrow."
     *                             — no `FATE` token at all.
     *   · "There are exactly two possibilities and this screen is not told which."
     *                             — reworded past rule (3)'s two patterns.
     *
     * The claim that the conditional structure "catches novel phrasings rather
     * than the ones someone happened to think of" was OVERSTATED: it improved
     * precision, not recall, and the one novel phrasing it had been tested against
     * happened to contain two `FATE` tokens. That is exactly the shape of error
     * this test exists to catch, made by the test.
     *
     * THE GATE IS GONE. In the `unavailable` arm — the only arm scanned here —
     * EVERY sentence that talks about creating a record must carry a hedge, with
     * no vocabulary condition to evade. That is a true invariant of this arm
     * rather than a wider ban: this screen is given `persistence` and not
     * `backend`, so it cannot know the fate of ANY record created in this state,
     * and a sentence about creating one therefore has nothing unhedged to say.
     * It is checked per sentence, so the workspace and walkthrough clauses —
     * which are true regardless of a create and do not mention one — are
     * unaffected.
     */
    /** The hedges that make such a clause honest under all three outcomes. */
    const HEDGE = /may fail outright|nothing this screen has read establishes/i;

    for (const text of strings) {
      // (1) an absolute verdict about durability, in any of its phrasings.
      expect(text).not.toMatch(
        /nothing (?:you )?create[ds]? (?:here|in this state) is (?:not )?durable/i,
      );
      // (3) a two-outcome enumeration. Four forms now: the two it has taken, plus
      // the two an independent review reworded past them.
      expect(text).not.toMatch(/(?:which of )?the two ways/i);
      expect(text).not.toMatch(/either .* or it succeeds/i);
      expect(text).not.toMatch(/exactly two|one of two|two (?:possibilities|outcomes|ways)/i);
      // The specific promised destination the retired copy made.
      expect(text).not.toMatch(/succeeds into the workspace/i);

      // (2) sentence by sentence, so a true workspace clause beside a create
      // clause does not have to carry the create clause's hedge.
      for (const sentence of text.split(/(?<=[.;])\s+/)) {
        if (CREATE_RECORD.test(sentence)) {
          expect(sentence).toMatch(HEDGE);
        }
      }
    }

    // And the corrected claim is actually there — so deleting the sentence
    // outright cannot pass this test in place of correcting it.
    expect(
      strings.filter((t) => /nothing this screen has read establishes/i.test(t)),
    ).toHaveLength(4);
  });

  /**
   * THE JUMP NAV IS RETIRED (2026-10-12), and this is its inversion. Overview
   * ended in four jump buttons into the deeper tabs, beside a tablist that
   * already offered all of them — a second navigation for the same four places.
   * The one onward move that is part of a question stays, as a real link inside
   * the widget that raises it.
   */
  it('has no jump-button navigation; Data Safety links to the canonical home instead', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    expect(screen.queryByRole('navigation', { name: 'More settings detail' })).toBeNull();
    fireEvent.click(screen.getByRole('link', { name: 'All Boundaries' }));
    expect(tab('Privacy & Governance')).toHaveAttribute('aria-selected', 'true');
    expect(search()).toBe('?tab=privacy');
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
    expect(alerts[0]).toHaveTextContent(/not running|unreachable/i);
  });
});

// --- Data & Privacy -----------------------------------------------------------

describe('Settings — Privacy & Governance', () => {
  it('covers storage, reset, telemetry, models, memory, truth, and access — in Title Case', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Privacy & Governance');
    await screen.findByText(/two things are stored/i);

    const concepts = settingsConcepts(settingsFactsFrom(aboutResponse));
    expect(concepts.map((c) => c.heading)).toEqual([
      // Slice 2A (I5) sweep: was 'Synthetic Data Only'. That heading is a flat
      // scope claim about the whole build, and it rendered directly above the
      // already-corrected 'No Real Experiment Data in the Workspace' card — one
      // tab, two contradictory promises. The card is about the runtime MODE, so
      // the heading now says so; the concept `id` is unchanged.
      'Synthetic-Only Mode',
      // Slice 2A (I5): was 'No Real Experiment Data'. That heading was a flat,
      // whole-deployment promise, and the deployment may now run a protected
      // read-only diagnostic over an isolated test database of
      // production-derived records. The heading states the scope it can keep.
      'No Real Experiment Data in the Workspace',
      'What Is Stored',
      'What Resets',
      // P2 FOLLOW-UP — the SIXTH of those six, and the last one missing.
      // `screens/GovernancePage.tsx` sends the reader here for what the build
      // "retains", and behind that pointer there was no concept, no heading and
      // no duration. Its position is asserted, like the two below it: it belongs
      // between where state resets and how it is deliberately removed, because
      // "how long does this last?" is the question a reader carries out of
      // `What Resets` and into `Reset and Deletion`.
      'How Long It Is Kept',
      // P2 (privacy consolidation) — two ADDITIONS, not renames. This tab is
      // meant to answer "what is collected, stored, retained, reset, exported?"
      // in one place, and it answered five of those six: deletion appeared on no
      // settings surface at all, and export appeared only as one item inside
      // `What Is Stored`'s collapsed disclosure. The list is asserted in order,
      // so both sit beside the storage/retention cards a reader reaches them
      // from rather than at the end of the tab.
      'Reset and Deletion',
      'Exporting a Record',
      'No Telemetry or Analytics',
      'No External Model Calls',
      'Project Memory Boundary',
      'Record Truth Boundary',
      'Authentication Boundary',
    ]);
    const merged = new Set<string>(PRIVACY_QUESTIONS.flatMap((q) => q.merged ?? []));
    for (const concept of concepts) {
      /* The canonical definition is HERE, under its own heading, exactly once.
         A concept shown as part of the merged Synthetic-Only Mode row
         (2026-10-18) has no visible row heading of its own — its definition's
         <h4> is in Details, which `getByRole` does not reach while closed — so
         its heading is asserted on the definition instead. */
      if (merged.has(concept.id)) {
        const def = Array.from(document.querySelectorAll('.settings-definition-heading')).filter(
          (h) => h.textContent === concept.heading,
        );
        expect(def, concept.heading).toHaveLength(1);
      } else {
        const heading = screen.getByRole('heading', { name: concept.heading });
        expect(heading).toBeInTheDocument();
        expect(heading.tagName).toBe('H3');
      }
      expect(screen.getByText(concept.detail)).toBeInTheDocument();
    }
  });

  /*
   * "WHAT IS STORED" MUST COUNT BOTH PLACES, not just the workspace.
   *
   * The retired copy said the workspace is the only thing stored ("Just the example
   * workspace" / "Only the example workspace is stored"). That was true while the
   * five built-in examples were materialised into the ordinary workspace on every
   * read. Since the examples moved into a per-session scope the server ALSO creates
   * a temporary directory for each worked-example session — `workspace.py`'s
   * `scope_root` returns `workspace_root()/_tutorial/<session_id>` for one — writes
   * that session's own copies of the five examples into it
   * (`create_tutorial_session` → `ensure_tutorial_seeded`), and keeps every answer,
   * edit and exported artifact made inside it there (`Experiment.dir` /
   * `records_dir` are rooted at the scope). It is removed on
   * `DELETE /api/tutorial/sessions/{id}`, or swept once expired.
   *
   * This test replaces a needle that was only a settle point. It is strictly
   * stronger than what it replaces on two counts: it pins each clause of the new
   * truth by name, and it FORBIDS the retired only-one-place claim from returning
   * in either the summary or the definition — which the old assertion, being a
   * substring match on that very claim, could not do.
   */
  it('counts the per-walkthrough directory as well as the workspace', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Privacy & Governance');
    await screen.findByText(/two things are stored/i);

    const stored = screen.getByText(/two things are stored/i).textContent ?? '';
    // Both places, and that neither is shared between deployments.
    expect(stored).toMatch(/both as files on the server for this deployment/i);
    expect(stored).toMatch(/neither is shared between deployments/i);
    expect(stored).toMatch(/the workspace itself/i);
    expect(stored).toMatch(
      /a temporary directory the server creates for each worked-example walkthrough/i,
    );
    // What is written into it, and that it is written there INSTEAD of the workspace.
    expect(stored).toMatch(/its own copy of the five built-in example records/i);
    expect(stored).toMatch(
      /every answer, edit and exported artifact you produce inside it is written there rather than into the workspace/i,
    );
    // When it goes away — both arms, and no promised deletion time. The first arm
    // is deliberately hedged: `tutorialController`'s DELETE is best effort and a
    // failure is swallowed, so the copy must not promise the removal outright.
    expect(stored).toMatch(/the app discards that directory when the walkthrough ends/i);
    expect(stored).toMatch(/if that request does not reach the server/i);
    expect(stored).toMatch(/an expired one is removed the next time a walkthrough is opened/i);

    // The retired claim must not survive anywhere on this tab, in either register:
    // it asserted that the workspace is the only thing stored.
    const tabText = norm(document.body.textContent ?? '');
    expect(tabText).not.toContain(norm('Only the example workspace is stored'));
    expect(tabText).not.toContain(norm('Just the example workspace'));
  });

  /** Data & Privacy owns the paragraphs Overview used to duplicate verbatim or
   *  paraphrase: the synthetic-data claim, telemetry, and authentication. */
  it('is the one canonical home of the definitions Overview only summarizes', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Privacy & Governance');
    await screen.findByText(/two things are stored/i);

    // Slice 2A (I5) sweep. Both needles named copy that has been retired for
    // being untrue of the deployment, and both are replaced by a needle from
    // the SAME concept's new definition — not softened into a tautology:
    //   · /only unmistakably synthetic data is in scope/ → the mode sentence
    //     that replaced it. `synthetic-data-only` still owns a definition here.
    //   · /there is no database/ → the workspace-scoped storage sentence.
    // Each string is still asserted to be rendered on Data & Privacy exactly as
    // `settingsContent.ts` authors it; only the wording being pinned moved.
    //
    // MOVED AGAIN, 2026-09-12, and for a reason rather than a reword. The needle
    // was `/this deployment runs in synthetic-only mode: file upload is refused/`
    // — the UNSCOPED refusal, which was false of a build shipping two controls
    // that read a user-picked file. The card now scopes it to the upload ROUTE
    // (`upload-claim-parity.test.tsx` §7 holds that, with the polarity proven on
    // the exact retired string). The needle deliberately includes the scoping
    // noun, so this render check cannot pass on a future unscoped reword.
    expect(
      screen.getByText(
        /this deployment runs in synthetic-only mode: the upload route refuses every request/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/the workspace is not stored in a database/i)).toBeInTheDocument();
    expect(screen.getByText(/no analytics, no usage tracking/i)).toBeInTheDocument();
    // Was `/no accounts, no sign-in, and no user profiles/i`. That sentence read
    // as "this deployment is open", which is the opposite of how it is operated:
    // the hosted deployment sits behind an institutional single-sign-on edge.
    // The definition now separates app-managed identity from edge access, and
    // this assertion pins the app-managed half by name.
    expect(
      screen.getByText(
        /ISAAC itself does not manage user accounts, profiles, or application roles/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/decided only by the official isaac v1\.05 schema/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no advisory surface — not the assistant, not project memory/i),
    ).toBeInTheDocument();
  });

  /** Progressive disclosure is for EDGE CASES only — never for a caveat that
   *  keeps the visible sentence from overstating what the code does. */
  it('puts only secondary edge cases behind collapsed disclosures', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('Privacy & Governance');
    await screen.findByText(/two things are stored/i);

    const disclosures = Array.from(
      container.querySelectorAll('details.settings-more'),
    ) as HTMLDetailsElement[];
    expect(disclosures.map((d) => d.querySelector('summary')?.textContent)).toEqual([
      'What the Workspace Contains',
      'Assistant Conversations',
      // P2 FOLLOW-UP — the retention card's browser half, and it belongs in a
      // drawer under this rule rather than in spite of it. Nothing in the
      // always-visible retention copy makes a claim about the browser, and
      // localStorage has no maximum age either, so shutting this disclosure
      // cannot turn "one stated maximum age" into an overstatement. The visible
      // paragraph still ends by pointing at it, so a shut drawer is never read
      // as "the server is the whole story".
      'What the Browser Keeps',
      'About That Shared Key',
    ]);
    disclosures.forEach((d) => expect(d.open).toBe(false));

    // The honesty caveats stay in the ALWAYS-VISIBLE paragraph, not in a drawer.
    const hidden = norm(disclosures.map((d) => d.textContent ?? '').join(' '));
    expect(hidden).not.toContain('cannot tell real data from synthetic');
    expect(hidden).not.toContain('to judge whether it is real');
    expect(hidden).not.toContain('no way to report whether either restriction is active');
  });

  /*
   * ── THE TWO LAYERS, RE-CUT 2026-10-12 — AN INVERSION OF THE 2026-09-16 TEST ──
   *
   * The 2026-09-16 layer put each concept's whole `detail` behind its own
   * `details.settings-concept`, whose `<summary>` was the heading and nothing else
   * — and this test pinned that shape. Privacy & Governance now shows each
   * concept as a VISIBLE ROW (heading + `summary`, `DEC-35`: a privacy state is
   * never behind a disclosure) and keeps every `detail` in its question widget's
   * Details. What that test protected is unchanged and is what is asserted here:
   *
   *   1. no `summary` line is ever the LABEL of a disclosure (the Details trigger
   *      reads "Full Definitions" — a topic, not a claim);
   *   2. every definition is present, verbatim, under its own heading;
   *   3. every concept appears in exactly ONE widget, once as a row and once as
   *      a definition, so nothing is duplicated and nothing is dropped.
   */
  it('shows every concept once as a visible row and once as a definition in its widget', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('Privacy & Governance');
    await screen.findByText(/two things are stored/i);

    const concepts = settingsConcepts(settingsFactsFrom(aboutResponse));
    // The four widgets hold all twelve, each exactly once.
    const placed = PRIVACY_QUESTIONS.flatMap((q) => q.concepts);
    expect(new Set(placed).size).toBe(placed.length);
    expect([...placed].sort()).toEqual(concepts.map((c) => c.id).sort());

    const rowHeadings = Array.from(container.querySelectorAll('.settings-point-heading')).map(
      (h) => h.textContent,
    );
    const defHeadings = Array.from(container.querySelectorAll('.settings-definition-heading')).map(
      (h) => h.textContent,
    );
    /* MERGED ROWS (2026-10-18, review): Synthetic-Only Mode and No Real
       Experiment Data in the Workspace stated one boundary twice, one above the
       other, and are ONE visible row — `syntheticWorkspaceRow`'s sentence, which
       names both concepts in `data-concepts`. Each keeps its own definition. */
    const mergedIds = PRIVACY_QUESTIONS.flatMap((q) => q.merged ?? []);
    expect(mergedIds).toEqual(['synthetic-data-only', 'no-real-experiment-data']);
    const mergedRow = container.querySelector('.settings-point[data-concepts]')!;
    expect(mergedRow.getAttribute('data-concepts')).toBe(mergedIds.join(' '));
    expect(mergedRow.closest('[hidden]')).toBeNull();
    const mergedCopy = syntheticWorkspaceRow(settingsFactsFrom(aboutResponse));
    expect(mergedRow.querySelector('.settings-point-heading')?.textContent).toBe(mergedCopy.heading);
    expect(mergedRow.querySelector('.settings-point-text')?.textContent).toBe(mergedCopy.text);
    // Each concept's load-bearing caveat survives the merge, visibly.
    expect(mergedCopy.text).toMatch(/upload route refuses every request outright/i);
    expect(mergedCopy.text).toMatch(/cannot tell real data from synthetic/i);
    expect(mergedCopy.text).toMatch(/whoever operates it/i);

    for (const concept of concepts) {
      expect(defHeadings.filter((h) => h === concept.heading), concept.heading).toHaveLength(1);
      if (mergedIds.includes(concept.id)) {
        // Its definition is in the merged row's widget's Details, verbatim.
        const def = Array.from(container.querySelectorAll('.settings-definition')).find(
          (el) => el.querySelector('.settings-definition-heading')?.textContent === concept.heading,
        )!;
        expect(def.querySelector('.settings-definition-text')?.textContent).toBe(concept.detail);
        expect(def.closest('section.widget')).toBe(mergedRow.closest('section.widget'));
        continue;
      }
      expect(rowHeadings.filter((h) => h === concept.heading), concept.heading).toHaveLength(1);
      const row = Array.from(container.querySelectorAll('.settings-point')).find(
        (el) => el.querySelector('.settings-point-heading')?.textContent === concept.heading,
      )!;
      // The row is VISIBLE (no closed disclosure, nothing `hidden` above it)…
      expect(row.closest('[hidden]'), `${concept.heading}: row hidden`).toBeNull();
      expect(row.querySelector('.settings-point-text')?.textContent).toBe(concept.summary);
      // …and its definition is in the same widget's Details, verbatim.
      const def = Array.from(container.querySelectorAll('.settings-definition')).find(
        (el) => el.querySelector('.settings-definition-heading')?.textContent === concept.heading,
      )!;
      expect(def.querySelector('.settings-definition-text')?.textContent).toBe(concept.detail);
      expect(def.closest('section.widget')).toBe(row.closest('section.widget'));
      expect(def.closest('.disclosure-body'), `${concept.heading}: definition is in Details`).not.toBeNull();
    }
    // Every Details trigger is the same topic label — never a claim.
    const triggers = Array.from(container.querySelectorAll('.widget-details .disclosure-trigger'));
    expect(triggers).toHaveLength(PRIVACY_QUESTIONS.length);
    for (const trigger of triggers) {
      expect(trigger.querySelector('.disclosure-summary')?.textContent).toBe('Full Definitions');
      for (const concept of concepts) {
        expect(norm(trigger.textContent ?? '')).not.toContain(norm(concept.summary));
      }
    }
  });

  /*
   * GOVERNANCE & SAFETY → POLICY MOVED HERE (2026-10-12). The two paragraphs that
   * carry a STATE are visible rows; Workspace Scope is a definition. The
   * diagnostic paragraph is the one place every bound of the diagnostic is
   * stated in a single visible block, which is why it is a row.
   */
  /* ~~two visible rows carrying the full paragraphs~~ — 2026-10-18 (review):
     each visible row carries the paragraph's ONE-LINE form, and the paragraph,
     verbatim, is in the same widget's Details. The diagnostic's line must keep
     every bound a reader needs at a glance visible (`DEC-35`). */
  it('carries the governance policy: two visible one-line rows, their paragraphs and one definition in Details', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('Privacy & Governance');
    await screen.findByText(/two things are stored/i);
    for (const id of ['reviewTools', 'diagnostic'] as const) {
      const row = container.querySelector(`.settings-point[data-policy="${id}"]`)!;
      expect(row, id).not.toBeNull();
      expect(row.closest('[hidden]'), `${id}: visible`).toBeNull();
      expect(row.querySelector('h3')?.textContent).toBe(GOVERNANCE_POLICY[id].heading);
      expect(row.querySelector('p')?.textContent).toBe(GOVERNANCE_POLICY[id].summary);
      const full = container.querySelector(`.settings-definition[data-policy="${id}"]`)!;
      expect(full.querySelector('p')?.textContent).toBe(GOVERNANCE_POLICY[id].text);
      expect(full.closest('.disclosure-body'), `${id}: paragraph in Details`).not.toBeNull();
      expect(full.closest('section.widget')).toBe(row.closest('section.widget'));
    }
    const diagnosticLine = GOVERNANCE_POLICY.diagnostic.summary;
    expect(diagnosticLine).toMatch(/read-only/i);
    expect(diagnosticLine).toMatch(/aggregates only/i);
    expect(diagnosticLine).toMatch(/no record displayed/i);
    expect(diagnosticLine).toMatch(/nothing sent to a model/i);
    const scope = container.querySelector('.settings-definition[data-policy="workspaceScope"]')!;
    expect(scope.querySelector('p')?.textContent).toBe(GOVERNANCE_POLICY.workspaceScope.text);
    // The wayfinding phrase that stopped being true in the move is gone.
    expect(container.textContent).not.toMatch(/the Validator on the next tab/i);
    // …and the clause the move found FALSE is gone: this application's own
    // tables may be in PostgreSQL since durable Create Experiment persistence.
    expect(container.textContent).not.toMatch(/PostgreSQL is used only by that diagnostic path/i);
    // The reader can get to the Validator the review-tools row names.
    expect(screen.getByRole('link', { name: 'Open the Validator' }).getAttribute('href')).toBe(
      '/governance?tab=validator',
    );
  });

  it('never promotes a concept summary line into a disclosure summary', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('Privacy & Governance');
    await screen.findByText(/two things are stored/i);

    const concepts = settingsConcepts(settingsFactsFrom(aboutResponse));
    // EVERY `<summary>` on the tab, not only the concept rows — the `more`
    // drawers are covered too, so neither layer can acquire a claim.
    const summaries = Array.from(container.querySelectorAll('summary')).map((s) =>
      norm(s.textContent ?? ''),
    );
    expect(summaries.length).toBeGreaterThan(0);

    const allowed = new Set<string>([
      ...concepts.map((c) => c.heading),
      ...concepts.flatMap((c) => (c.more ? [c.more.label] : [])),
    ]);
    // Stated as a set difference rather than a per-item loop so an entirely new
    // summary — one belonging to no concept at all — also fails.
    expect(summaries.filter((s) => !allowed.has(s))).toEqual([]);
    concepts.forEach((c) => {
      expect(summaries).not.toContain(norm(c.summary));
    });
  });

  it('says there is no language model and nothing typed leaves the app', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Privacy & Governance');
    expect(
      await screen.findByText(/there is no language model in this build/i),
    ).toBeInTheDocument();
    // The Assistant-conversation privacy claim, pinned to what the code ACTUALLY
    // does. `lib/assistantSession.ts::writeStorage` persists the transcript to
    // `sessionStorage`, so the old copy ("never written down or logged") was a false
    // privacy claim. This is strictly stronger than the assertion it replaces: it
    // pins the true statement AND forbids the false one from coming back.
    expect(
      screen.getByText(/the transcript is written to sessionStorage in that tab/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/survives a page reload and is erased when the tab closes/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/never written down/i)).not.toBeInTheDocument();
  });

  /** The Data & Privacy half of the same three anti-overstatement guards. */
  it('states only what the code enforces about uploads, storage lifetime, and access', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Privacy & Governance');
    await screen.findByText(/two things are stored/i);

    // Governance: refusal is a blanket upload block, NOT real-data detection —
    // the CSV preview and record validator really do read what they are given.
    expect(
      screen.getByText(/nothing in the app inspects that text to judge whether it is real/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/real-looking upload is intercepted/i),
    ).not.toBeInTheDocument();

    // Persistence: filesystem workspace, not process memory.
    expect(
      screen.getByText(/restarting the backend process does not by itself clear it/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/gone when it restarts/i)).not.toBeInTheDocument();

    // Auth: an in-application shared key is possible, so no categorical "any".
    expect(
      screen.getByText(/no way to report whether either restriction is active/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/it stores no\s+credentials/i)).not.toBeInTheDocument();
  });

  it('keeps Project Memory advisory and the schema authoritative', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Privacy & Governance');
    expect(
      await screen.findByText(/never a correctness ruling — and it cannot mark a record valid/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/decided only by the official isaac v1\.05 schema/i)).toBeInTheDocument();
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    openTab('Privacy & Governance');
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });
});

// --- This Build + Technical Details (was About) --------------------------------

/**
 * ABOUT IS RETIRED AS A TAB (2026-10-12) — and was the second copy of four of
 * Overview's seven build facts. Its material moved, and each guard below follows
 * it rather than being dropped:
 *
 *   · identity rows → This Build's Build view (Overview);
 *   · Truth vs. Memory, No-Guessing and the identity caption → This Build's info;
 *   · the raw values (full SHA, response fields, source endpoints, doc paths) →
 *     Advanced → Technical Details, a developer surface (`DEC-56`);
 *   · `?tab=about` → Overview, scrolled to This Build.
 */
describe('Settings — This Build and Technical Details (was About)', () => {
  it('This Build splits the seven facts into a Build view (identity) and a Runtime view', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    expect(await screen.findByText('0.1.0')).toBeInTheDocument();
    const build = screen.getByRole('region', { name: 'This Build' });
    const views = Array.from(build.querySelectorAll('.widget-view-panel'));
    const labelsIn = (el: Element) =>
      Array.from(el.querySelectorAll('.settings-figure-label')).map((l) => l.textContent);
    expect(labelsIn(views[0])).toEqual(['App Version', 'Build Commit', 'Record Schema', 'Core']);
    expect(labelsIn(views[1])).toEqual(['Runtime Mode', 'Data Regime', 'Persistence']);
    // Build is shown; Runtime is one press away, mounted but hidden.
    expect(views[0]).not.toHaveAttribute('hidden');
    expect(views[1]).toHaveAttribute('hidden');
    fireEvent.click(within(build).getByRole('button', { name: 'Runtime' }));
    expect(views[1]).not.toHaveAttribute('hidden');
    expect(views[0]).toHaveAttribute('hidden');
    expect(within(build).getByRole('button', { name: 'Runtime' })).toHaveAttribute('aria-pressed', 'true');
    // The headline states the identity a reader came for, once.
    expect(build.querySelector('.widget-headline .widget-figure')?.textContent).toBe('ISAAC 0.1.0');
    expect(build.querySelector('.widget-headline .widget-figure-unit')?.textContent).toBe('Schema v1.05');
    expect(container.querySelectorAll('.settings-figure')).toHaveLength(7);
  });

  /**
   * The short sha is on Overview; the FULL sha renders in exactly one place on
   * the whole page — inside Technical Details' collapsed Details on Advanced.
   */
  it('shows the short commit on Overview and the full SHA only inside Technical Details', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    const short = screen.getByText('fakecommit00');
    expect(short.closest('.disclosure-body, details')).toBeNull();
    expect(screen.queryByText('fakecommit0000settingsp364')).toBeNull();

    openTab('Advanced');
    const technical = screen.getByRole('region', { name: 'Technical Details' });
    const full = screen.getAllByText('fakecommit0000settingsp364');
    expect(full).toHaveLength(1);
    const body = full[0].closest('.disclosure-body') as HTMLElement;
    expect(body).not.toBeNull();
    expect(technical.contains(body)).toBe(true);
    expect(body).toHaveAttribute('hidden');
    // Title Case trigger, collapsed by default.
    const trigger = within(technical).getByRole('button', { name: 'Raw Values' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('Technical Details carries the raw field names, source endpoints, and doc paths', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=advanced');
    const technical = screen.getByRole('region', { name: 'Technical Details' });
    const labels = Array.from(technical.querySelectorAll('dt')).map((dt) => dt.textContent);
    expect(labels).toEqual([
      'Build Commit (Full)',
      'Response Fields',
      'Source Endpoints',
      'Repository Documentation',
    ]);
    for (const field of [...ABOUT_RESPONSE_FIELDS, ...SETTINGS_SOURCE_ENDPOINTS, ...REPO_DOCS]) {
      const el = within(technical).getByText(field);
      // Raw identifiers render verbatim as inert <code>, never re-cased or linked.
      expect(el.tagName).toBe('CODE');
      expect(el.closest('a')).toBeNull();
    }
    expect(within(technical).getByText(/not served as pages by this app/i)).toBeInTheDocument();
  });

  it('This Build keeps the provenance claim, behind its info toggle', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    const build = screen.getByRole('region', { name: 'This Build' });
    const info = build.querySelector('.widget-info') as HTMLElement;
    expect(info).toHaveAttribute('hidden');
    expect(info.textContent).toMatch(/rendered verbatim — this screen computes none of these values/i);
    fireEvent.click(within(build).getByRole('button', { name: 'About This Build' }));
    expect(info).not.toHaveAttribute('hidden');
  });

  it('renders an honest "not set" state when no build commit was injected (never fabricates one)', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: aboutResponseNoCommit },
      [OPENAPI_URL]: { body: openApiFixture },
      [GRAPH_STATUS_URL]: { body: graphStatusAvailable },
      'GET /api/runtime/assistant-companion': { body: assistantCompanionUnconfigured },
    });
    renderSettings();
    expect(await screen.findByText(/not set \(no build identity injected\)/i)).toBeInTheDocument();
  });

  it('states the truth-vs-memory authority boundary and the no-guessing policy', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    const copy = settingsAboutCopy(settingsFactsFrom(aboutResponse));
    expect(screen.getByText('Truth vs. Memory.')).toBeInTheDocument();
    expect(screen.getByText(norm(copy.truthVsMemory))).toBeInTheDocument();
    expect(screen.getByText('No-Guessing.')).toBeInTheDocument();
    expect(screen.getByText(/nothing scientific is invented/i)).toBeInTheDocument();
    // It names the two PLANES; it does not restate Privacy & Governance's rulings.
    expect(screen.getByText(/is the truth plane/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/decided only by the official isaac v1\.05 schema/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/never a correctness ruling — and it cannot mark a record valid/i),
    ).not.toBeInTheDocument();
  });

  it('lists in-repo documentation as plain references, not fetched/rendered content', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=advanced');
    expect(screen.getByText('CLAUDE.md')).toBeInTheDocument();
    expect(screen.getByText('AGENTS.md')).toBeInTheDocument();
    // Inert names: no links, and the doc names are not anchors.
    expect(screen.getByText('CLAUDE.md').tagName).toBe('CODE');
    expect(screen.getByText(/not served as pages by this app/i)).toBeInTheDocument();
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings('/settings?tab=about');
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });
});

// --- API browser --------------------------------------------------------------

/**
 * P36V PR3 slice C split the API tab into two sub-surfaces — API Keys (an honest
 * unavailable state) and Documentation (Quick Start + Endpoint Explorer +
 * Connect an Agent) — and replaced the path-segment group inference with the
 * document's REAL `tags`. P36V-1 slice 12 then promoted the browser out of that
 * nested sub-tab into its own top-level, deep-linkable tab. The suite below
 * keeps every P36R/P36V guard and tightens the grouping one: the group names and
 * their ORDER asserted here are obtainable only from the document's `tags`
 * array, so a revert to segment inference fails.
 *
 * The API-Access surface, Quick Start, the generated code samples and Connect an
 * Agent have their own file: `settings-api.test.tsx`.
 */
const ENDPOINT_COUNT = 7;

/** Open the Endpoint Explorer — the Advanced tab's main widget since 2026-10-12. */
async function openApiDocs() {
  openTab('Advanced');
  return screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 });
}

/** The endpoint list, scoped: several paths also appear in Quick Start. */
const endpointList = () => document.querySelector('.api-browser-list') as HTMLElement;

const groupNames = () =>
  Array.from(document.querySelectorAll('.api-browser-group-heading')).map((h) =>
    (h.firstChild?.textContent ?? '').trim(),
  );

describe('Settings — API browser', () => {
  it('shows a loading state before the fetch resolves', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Advanced');
    expect(screen.getByText('Loading the API contract…')).toBeInTheDocument();
  });

  it('groups the endpoints by the document’s REAL tags, with the method as TEXT', async () => {
    const hits = stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    // `/api/about` is the first row of the first registered tag, so it is the
    // default selection and appears twice: once in the list, once in the detail.
    expect(screen.getAllByText('/api/about')).toHaveLength(2);
    expect(within(endpointList()).getByText('/api/experiments/{id}')).toBeInTheDocument();
    expect(within(endpointList()).getByText('/api/experiments/{id}/answers')).toBeInTheDocument();

    // Group headings are the registered tag NAMES, in the document's own
    // registration order — which is deliberately not alphabetical.
    expect(groupNames()).toEqual([
      'Health & Meta',
      'Experiments',
      'Drafts & Answers',
      'Uploads',
      'Validation',
      'Other Operations',
    ]);
    expect([...groupNames()].sort()).not.toEqual(groupNames());
    // The path segments the previous helper inferred appear nowhere.
    for (const stale of ['health', 'about', 'experiments', 'answers', 'uploads', 'validate']) {
      expect(groupNames(), `stale inferred group: ${stale}`).not.toContain(stale);
    }
    // A registered tag no operation carries creates no group.
    expect(groupNames()).not.toContain('Schema & Vocabulary');

    // Method conveyed by TEXT, not color alone.
    expect(screen.getAllByText('GET').length).toBeGreaterThan(0);
    expect(screen.getAllByText('POST').length).toBeGreaterThan(0);
    expect(hits).toEqual(expect.arrayContaining([ABOUT_URL, OPENAPI_URL]));
  });

  it('renders the total endpoint count in its own explicit polite live region', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();
    const count = screen.getByText(`${ENDPOINT_COUNT} of ${ENDPOINT_COUNT} endpoints`);
    expect(count).toBeInTheDocument();
    expect(count).toHaveAttribute('aria-live', 'polite');
    // Exactly one `aria-live` region, plus exactly one shared `role="status"`
    // for every copy button on the surface — never one live region per button.
    expect(document.querySelectorAll('[aria-live]')).toHaveLength(1);
    expect(document.querySelectorAll('[role="status"]')).toHaveLength(1);
  });

  /**
   * The provenance claim is unchanged, but the two halves now live on the two
   * API tabs, so each is asserted where it renders instead of both being read
   * off one combined sub-tab. The contract IDENTITY line is Quick Start's (it is
   * the contract's own `openapi`/`info` values, joined by `quickStartFacts`);
   * the "generated contract" attribution is the Explorer detail pane's.
   */
  it('shows the OpenAPI contract identity verbatim, never a hand-written duplicate', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Integrations');
    expect(
      await screen.findByText(
        /OpenAPI 3\.1\.0 · ISAAC Metadata Assistant API · v0\.1\.0/,
      ),
    ).toBeInTheDocument();

    await openApiDocs();
    expect(screen.getByText(/this app's own\s+generated contract/i)).toBeInTheDocument();
    expect(
      screen.getByText(/read from the OpenAPI document the app generates for itself/i),
    ).toBeInTheDocument();
  });

  it('the search box filters endpoints by path/summary/group, client-side, deterministically', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    const search = screen.getByLabelText('Search endpoints') as HTMLInputElement;
    expect(search.tagName).toBe('INPUT');
    expect(search).toHaveAttribute('type', 'search');

    fireEvent.change(search, { target: { value: 'answers' } });

    expect(await screen.findByText(`1 of ${ENDPOINT_COUNT} endpoints`)).toBeInTheDocument();
    // The one survivor becomes the selection, so it renders in the master list
    // AND in the detail pane; the filtered-out paths render nowhere in the list.
    expect(screen.getAllByText('/api/experiments/{id}/answers')).toHaveLength(2);
    expect(within(endpointList()).queryByText('/api/health')).not.toBeInTheDocument();
    expect(screen.queryByText('/api/about')).not.toBeInTheDocument();
  });

  it('an unmatched search shows an honest empty state, never fabricated rows', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.change(screen.getByLabelText('Search endpoints'), {
      target: { value: 'nonexistent-route-xyz' },
    });

    expect(await screen.findByText(/no endpoints match/i)).toBeInTheDocument();
    expect(screen.getByText(`0 of ${ENDPOINT_COUNT} endpoints`)).toBeInTheDocument();
  });

  it('is master-detail: one detail pane, not every endpoint expanded at once', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    const detail = document.getElementById('settings-api-detail') as HTMLElement;
    expect(detail).not.toBeNull();
    expect(detail).toHaveAttribute('role', 'region');
    expect(detail).toHaveAttribute('tabindex', '-1');
    expect(detail).toHaveAttribute('aria-labelledby', 'settings-api-detail-name');

    // The first visible endpoint is selected by default, and ONLY its detail
    // renders — every other path appears once, in the master list.
    expect(within(detail).getByText('/api/about')).toBeInTheDocument();
    expect(screen.getAllByText('/api/experiments/{id}')).toHaveLength(1);
    // Nothing renders a per-row <details> accordion any more.
    expect(
      // The Explorer is a widget since 2026-10-12, not a `.settings-card`.
      detail.closest('section.widget')?.querySelectorAll('.api-browser-row details'),
    ).toHaveLength(0);
  });

  it('selecting an endpoint renders its detail: summary, purpose, and parameters', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/experiments/{id}'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;

    expect(within(detail).getByText('Get Experiment')).toBeInTheDocument();
    expect(within(detail).getByText(/fetch one experiment detail by id/i)).toBeInTheDocument();
    expect(within(detail).getByRole('heading', { name: 'Purpose' })).toBeInTheDocument();
    expect(within(detail).getByText('id')).toBeInTheDocument();
    expect(within(detail).getByText('path')).toBeInTheDocument();
    expect(within(detail).getByText('Yes')).toBeInTheDocument();
    // The parameter's own description, not a re-worded one.
    expect(within(detail).getByText('The id of an experiment.')).toBeInTheDocument();
  });

  it('an endpoint with no parameters says so honestly rather than showing an empty table', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/health'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;
    expect(within(detail).getByText('No parameters.')).toBeInTheDocument();
    expect(within(detail).queryByRole('table')).not.toBeInTheDocument();
  });

  it('renders request body and responses when the contract supplies them, collapsed by default', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/experiments/{id}/answers'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;

    expect(within(detail).getByRole('heading', { name: 'Request Body' })).toBeInTheDocument();
    expect(within(detail).getByText('Required.')).toBeInTheDocument();
    expect(within(detail).getByRole('heading', { name: 'Responses' })).toBeInTheDocument();
    expect(within(detail).getByRole('heading', { name: 'Error States' })).toBeInTheDocument();
    expect(within(detail).getByText('200')).toBeInTheDocument();
    expect(within(detail).getByText('422')).toBeInTheDocument();
    expect(within(detail).getByText('Validation Error')).toBeInTheDocument();

    // Schemas/examples/samples are collapsible and start closed — no JSON wall,
    // and the raw schema is explicitly labelled TECHNICAL so it never leads.
    const disclosures = Array.from(detail.querySelectorAll('details')) as HTMLDetailsElement[];
    expect(disclosures.length).toBeGreaterThanOrEqual(5); // req schema+example, 200, 422, samples
    disclosures.forEach((d) => expect(d.open).toBe(false));

    const schemaSummary = within(detail).getAllByText('Technical Schema')[0];
    expect(within(detail).queryByText('Schema')).not.toBeInTheDocument();
    fireEvent.click(schemaSummary);
    expect((schemaSummary.closest('details') as HTMLDetailsElement).open).toBe(true);
    expect(within(detail).getByText(/SyntheticAnswersBody/)).toBeInTheDocument();
    expect(within(detail).getAllByText('Example').length).toBeGreaterThan(0);
  });

  it('resolves a local $ref one level and names what it resolved', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/experiments/{id}/answers'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;
    expect(within(detail).getByText('SyntheticFixtureError')).toBeInTheDocument();
  });

  it('shows an unresolvable $ref verbatim instead of inventing a shape for it', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    fireEvent.click(within(endpointList()).getByText('/api/experiments/{id}/answers'));
    const detail = document.getElementById('settings-api-detail') as HTMLElement;

    // The 404 response names a schema that is absent from `components`.
    const raw = Array.from(detail.querySelectorAll('pre'))
      .map((p) => p.textContent ?? '')
      .find((t) => t.includes('SyntheticFixtureAbsentTarget'));
    expect(raw).toBeDefined();
    expect(JSON.parse(raw as string)).toEqual({
      $ref: '#/components/schemas/SyntheticFixtureAbsentTarget',
    });

    // ...and it is NOT labelled as a resolved reference, unlike the 422.
    const tags = Array.from(detail.querySelectorAll('.api-browser-reftag')).map(
      (t) => t.textContent,
    );
    expect(tags).toContain('SyntheticFixtureError');
    expect(tags).not.toContain('SyntheticFixtureAbsentTarget');
  });

  it('the endpoint list is a roving-tabindex list: exactly one row is tabbable', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();

    const rows = Array.from(
      document.querySelectorAll('.api-browser-rowbtn'),
    ) as HTMLButtonElement[];
    expect(rows).toHaveLength(ENDPOINT_COUNT);
    expect(rows.filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1);
    expect(rows[0]).toHaveAttribute('tabindex', '0');

    fireEvent.keyDown(rows[0], { key: 'ArrowDown' });
    const after = Array.from(
      document.querySelectorAll('.api-browser-rowbtn'),
    ) as HTMLButtonElement[];
    expect(after[1]).toHaveAttribute('tabindex', '0');
    expect(after.filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1);
    // Moving the cursor must NOT change the selection.
    expect(after[0]).toHaveAttribute('aria-current', 'true');
  });

  it('rows are native buttons wired to the detail pane', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();
    const rows = Array.from(
      document.querySelectorAll('.api-browser-rowbtn'),
    ) as HTMLButtonElement[];
    rows.forEach((r) => {
      expect(r.tagName).toBe('BUTTON');
      expect(r).toHaveAttribute('aria-controls', 'settings-api-detail');
    });
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    openTab('Advanced');
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });

  /**
   * P36V-1 slice 13 — CONCISION. The detail pane used to re-render a
   * two-sentence authentication paragraph for every one of the seven endpoints;
   * the per-operation fact is a single flag. The flag is now compact metadata,
   * its meaning is stated ONCE for the tab, and both assertions below are
   * stronger than the prose ones they replace because they also pin the count.
   */
  it('states the authentication rule once for the tab, not once per endpoint', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await openApiDocs();

    expect(
      countOccurrences(norm(container.textContent ?? ''), norm(API_ACCESS_COPY.authMarkerLegend)),
    ).toBe(1);
    // The retired per-endpoint paragraphs appear nowhere at all.
    expect(container.textContent).not.toMatch(
      /A credential is required when this deployment enables authentication/i,
    );
    expect(container.textContent).not.toMatch(
      /so it stays reachable without a credential even where authentication is enabled/i,
    );
  });

  /**
   * P36V.1 — the Auth flag states the CONTRACT FACT (`401 documented`), not a
   * deployment claim (`Credential required`). This page says, three tabs away and
   * pinned above, that it "cannot report whether access is restricted"; a bare
   * `Credential required` asserted exactly that unknowable. The conditional lives
   * in the tab-level legend, which the flag references via `aria-describedby`.
   */
  it('marks each operation’s auth requirement as compact metadata, in TEXT', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await openApiDocs();
    const detail = () => document.getElementById('settings-api-detail') as HTMLElement;

    // GET /api/about documents a 401; GET /api/health is the only one that does not.
    const meta = (label: string) => {
      const item = Array.from(detail().querySelectorAll('.api-browser-meta-item')).find(
        (el) => el.querySelector('dt')?.textContent === label,
      ) as HTMLElement;
      return item?.querySelector('dd')?.textContent;
    };
    expect(meta('Auth')).toBe('401 documented');
    expect(meta('Parameters')).toBe('None');
    expect(meta('Request Body')).toBe('None declared');

    fireEvent.click(within(endpointList()).getByText('/api/health'));
    expect(meta('Auth')).toBe('No 401 documented');

    fireEvent.click(within(endpointList()).getByText('/api/experiments/{id}/answers'));
    expect(meta('Auth')).toBe('401 documented');
    expect(meta('Parameters')).toBe('2');
    expect(meta('Request Body')).toBe('Required');

    // The flag is tied to the legend that supplies the conditional it omits.
    const legend = document.querySelector('.api-browser-legend') as HTMLElement;
    const flag = detail().querySelector('.api-browser-meta-flag') as HTMLElement;
    expect(flag.getAttribute('aria-describedby')).toBe(legend.id);
  });

  /** The flag must not re-assert what this page says it cannot know. */
  it('never claims a credential IS required, on either API tab', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await openApiDocs();
    expect(container.textContent).not.toMatch(/\bCredential required\b/);
    expect(container.textContent).not.toMatch(/\bNo credential required\b/);
  });
});

// --- safety: no sensitive infrastructure detail, no external URL --------------

/** The SAME forbidden list `apps/api/tests/test_about_and_openapi.py` enforces
 *  on `GET /api/about` — re-asserted here so the client copy cannot reintroduce
 *  what the backend deliberately withholds. Naming a provider or a host in
 *  client copy discloses infrastructure topology.
 *
 *  Slice C note: `API Key` with a space is fine; `api_key` / `apikey` are not,
 *  which is why no surface prints the deployment's own environment-variable name
 *  and the generated samples use `$ISAAC_API_CREDENTIAL` instead. */
const FORBIDDEN = [
  'authentik',
  'ingress',
  'k8s',
  'kubernetes',
  'railway.app',
  'vercel.app',
  '127.0.0.1',
  'localhost',
  'secret',
  'password',
  'token',
  'api_key',
  'apikey',
  '/Users/',
  '/home/',
  'C:\\',
];

/**
 * Every distinct Settings surface, with something that only resolves once that
 * surface's own content has rendered. There are FIVE since slice 12: the API tab
 * split into two top-level tabs rather than two sub-tabs, and each is opened
 * here the way a user opens it — by activating its page tab.
 *
 * `settle` is a thunk rather than a string because the Endpoint Explorer's own
 * name is also its tab's label, so it has to be found by ROLE to avoid matching
 * the tab button.
 */
const SURFACES: { name: string; open: () => void; settle: () => Promise<unknown> }[] = [
  {
    name: 'Overview',
    open: () => openTab('Overview'),
    settle: () => screen.findByText('0.1.0'),
  },
  {
    name: 'Privacy & Governance',
    open: () => openTab('Privacy & Governance'),
    settle: () => screen.findByText(/two things are stored/i),
  },
  /*
   * Integrations holds what were two tabs — API Access and Connect Your Agent —
   * and stays in SURFACES for the reason Connect Your Agent was added: that copy
   * describes an authentication model and an authorization boundary, which is
   * exactly the copy most likely to reach for the name of the identity layer in
   * front of a deployment or for the word for a bearer credential. It settles on
   * the contract-derived Quick Start view, so the whole widget pair is mounted.
   */
  {
    name: 'Integrations',
    open: () => openTab('Integrations'),
    settle: () => screen.findByText(/OpenAPI 3\.1\.0 · ISAAC Metadata Assistant API/),
  },
  {
    name: 'Advanced',
    open: () => openTab('Advanced'),
    settle: () => screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 }),
  },
];

describe('Settings — no sensitive infrastructure detail is rendered', () => {
  it.each(SURFACES.map((s) => [s.name, s] as const))(
    'the %s surface leaks none of the backend-forbidden substrings',
    async (_name, surface) => {
      stubFetchRoutes(fullRoutes());
      const { container } = renderSettings();
      surface.open();
      await surface.settle();

      const text = (container.textContent ?? '').toLowerCase();
      for (const needle of FORBIDDEN) {
        expect(text.includes(needle.toLowerCase()), `unexpected leak: ${needle}`).toBe(false);
      }
    },
  );

  it('renders no external/CDN URL anywhere (no Swagger UI, no ReDoc, no script tag)', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await screen.findByText('0.1.0');
    openTab('Advanced');
    await screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 });

    expect(container.querySelectorAll('script')).toHaveLength(0);
    expect(container.querySelectorAll('iframe')).toHaveLength(0);
    for (const el of Array.from(container.querySelectorAll('[href], [src]'))) {
      const url = el.getAttribute('href') ?? el.getAttribute('src') ?? '';
      expect(/^(https?:)?\/\//.test(url), `external URL rendered: ${url}`).toBe(false);
    }
    expect((container.textContent ?? '').toLowerCase()).not.toContain('swagger');
    expect((container.textContent ?? '').toLowerCase()).not.toContain('redoc');
    expect((container.textContent ?? '').toLowerCase()).not.toContain('unpkg');
  });
});

// --- P36V PR3: single-source contract ----------------------------------------

/** Normalized rendered text of each surface, mounted one at a time (only the
 *  active panel is ever in the DOM, so cross-surface duplication has to be
 *  counted this way rather than read off a single render).
 *
 *  MEASURED ONCE AND SHARED (2026-10-12). Every `it.each` row below used to
 *  re-render every surface, which is 40-odd rows × the surfaces — and at seven
 *  tabs it was timing out at vitest's 5 s per-test deadline on a loaded host
 *  (two rows did at `8eab31ca`, before this change). The text of a surface does
 *  not depend on which canonical string is being counted, so it is computed once
 *  and each row counts against the same four strings. */
let surfaceTextOnce: Promise<string[]> | null = null;
function textOfEverySurface(): Promise<string[]> {
  if (surfaceTextOnce === null) {
    surfaceTextOnce = (async () => {
      const out: string[] = [];
      for (const surface of SURFACES) {
        stubFetchRoutes(fullRoutes());
        const view = renderSettings();
        surface.open();
        await surface.settle();
        out.push(norm(view.container.textContent ?? ''));
        view.unmount();
      }
      return out;
    })();
  }
  return surfaceTextOnce;
}

/**
 * THE anti-regression guard for the deduplication slice, re-stated for four tabs
 * (2026-10-12). Claims used to be authored two or three times across the tabs —
 * two of them character-for-character. Every canonical string is counted across
 * every surface:
 *
 *   · every DEFINITION, every `more` drawer, the about-copy, and every API-access
 *     string must appear EXACTLY ONCE;
 *   · every concept SUMMARY must appear exactly once on Privacy & Governance —
 *     its canonical home, where every boundary is a visible row — and on Overview
 *     ONLY if it is one of the four Data Safety lines, and then exactly once.
 *
 * The second rule is the old "exactly once" rule narrowed on purpose, and the
 * narrowing is the whole design: Overview's Data Safety widget is a glance at
 * four questions, built from the vetted summaries rather than from new
 * sentences, and it links to the canonical home for the rest. It may carry no
 * other summary and no definition at all.
 */
describe('Settings — every canonical string appears exactly once across the tabs', () => {
  const facts = settingsFactsFrom(aboutResponse);
  const concepts = settingsConcepts(facts);
  const about = settingsAboutCopy(facts);
  const overviewIds = new Set<string>(
    OVERVIEW_SAFETY_ROWS.flatMap((r) => r.items.flatMap((i) => ('concept' in i ? [i.concept] : []))),
  );
  const overviewPolicies = new Set<string>(
    OVERVIEW_SAFETY_ROWS.flatMap((r) => r.items.flatMap((i) => ('policy' in i ? [i.policy] : []))),
  );
  /* Concepts shown on Privacy as ONE merged row (2026-10-18): their own summary
     lines are not rendered there; the merged sentence is, once. */
  const mergedIds = new Set<string>(PRIVACY_QUESTIONS.flatMap((q) => q.merged ?? []));

  const canonical: { what: string; text: string }[] = [
    ...concepts.map((c) => ({ what: `${c.heading} — definition`, text: c.detail })),
    ...concepts
      .filter((c) => c.more)
      .map((c) => ({ what: `${c.heading} — ${c.more!.label}`, text: c.more!.text })),
    ...Object.values(GOVERNANCE_POLICY).map((p) => ({ what: `Policy — ${p.heading}`, text: p.text })),
    { what: 'About — truth vs. memory', text: about.truthVsMemory },
    { what: 'About — no-guessing', text: about.noGuessing },
    { what: 'About — identity caption', text: about.identityCaption },
    /* P36V-1 slice 13 — the API surfaces joined the guard. Before it, the
       key-unavailable reason was authored in FOUR places. The 2026-10-12 widget
       retired three of the strings (the disabled button's reason and the empty
       list's title and body) with the controls they described. */
    ...Object.entries(API_ACCESS_COPY).map(([key, text]) => ({
      what: `API Access — ${key}`,
      text,
    })),
    ...API_ACCESS_ROWS.map((row) => ({ what: `API Access — ${row.term}`, text: row.detail })),
    ...API_KEY_REQUIREMENTS.map((text, i) => ({ what: `API Access — requirement ${i + 1}`, text })),
  ];

  it.each(canonical.map((c) => [c.what, c.text]))('%s is rendered exactly once', async (_what, text) => {
    const perSurface = await textOfEverySurface();
    const counts = perSurface.map((t) => countOccurrences(t, norm(text as string)));
    const total = counts.reduce((a, b) => a + b, 0);
    expect(
      total,
      `rendered ${total}x — per surface [${SURFACES.map((s, i) => `${s.name}:${counts[i]}`).join(', ')}]`,
    ).toBe(1);
  });

  it.each(concepts.map((c) => [c.heading, c]))(
    '%s — summary: once on Privacy & Governance, and on Overview only as a Data Safety line',
    async (_heading, concept) => {
      const [overview, privacy, integrations, advanced] = await textOfEverySurface();
      const needle = norm(concept.summary);
      expect(countOccurrences(privacy, needle), 'Privacy & Governance').toBe(
        mergedIds.has(concept.id) ? 0 : 1,
      );
      expect(countOccurrences(overview, needle), 'Overview').toBe(overviewIds.has(concept.id) ? 1 : 0);
      expect(countOccurrences(integrations, needle), 'Integrations').toBe(0);
      expect(countOccurrences(advanced, needle), 'Advanced').toBe(0);
    },
  );

  it('the merged Synthetic-Only Mode row is rendered once, on Privacy & Governance only', async () => {
    const [overview, privacy, integrations, advanced] = await textOfEverySurface();
    const needle = norm(syntheticWorkspaceRow(facts).text);
    expect(mergedIds.size).toBe(2);
    expect(countOccurrences(privacy, needle)).toBe(1);
    expect(countOccurrences(overview, needle) + countOccurrences(integrations, needle)).toBe(0);
    expect(countOccurrences(advanced, needle)).toBe(0);
  });

  it.each(
    (['reviewTools', 'diagnostic'] as const).map((id) => [id, GOVERNANCE_POLICY[id].summary]),
  )('policy %s — its one-line form: once on Privacy, and on Overview only as a Data Safety line', async (id, summary) => {
    const [overview, privacy, integrations, advanced] = await textOfEverySurface();
    const needle = norm(summary as string);
    expect(countOccurrences(privacy, needle), 'Privacy & Governance').toBe(1);
    expect(countOccurrences(overview, needle), 'Overview').toBe(overviewPolicies.has(id as string) ? 1 : 0);
    expect(countOccurrences(integrations, needle) + countOccurrences(advanced, needle)).toBe(0);
  });

  it('the full commit SHA is rendered exactly once, in Advanced → Technical Details', async () => {
    const perSurface = await textOfEverySurface();
    const counts = perSurface.map((t) => countOccurrences(t, aboutResponse.build_commit));
    // One entry per SURFACES row, in order; the 1 is Technical Details.
    expect(counts).toEqual([0, 0, 0, 1]);
  });

  it('Overview renders no definition', async () => {
    const [overview] = await textOfEverySurface();
    for (const concept of concepts) {
      expect(overview, `Overview leaked "${concept.heading}"`).not.toContain(norm(concept.detail));
    }
  });

  it('every card/label heading in the content module is Title Case', () => {
    for (const concept of concepts) {
      expect(titleCase(concept.heading)).toBe(concept.heading);
      if (concept.more) expect(titleCase(concept.more.label)).toBe(concept.more.label);
    }
    expect(titleCase(about.truthVsMemoryLabel)).toBe(about.truthVsMemoryLabel);
    expect(titleCase(about.noGuessingLabel)).toBe(about.noGuessingLabel);
    for (const q of PRIVACY_QUESTIONS) expect(titleCase(q.title), q.title).toBe(q.title);
    for (const r of OVERVIEW_SAFETY_ROWS) expect(titleCase(r.label), r.label).toBe(r.label);
  });

  /* INVERTED 2026-10-18 (re-review, Overview trims), not deleted: it required the
     intro sentence "View this build's runtime status, data boundaries, provenance,
     and API access." — which the four tab labels directly beneath it already say.
     What it also pinned is kept: the eyebrow is accurate, the retired
     "Local Configuration" stays gone, and the "nothing to configure" claim still
     renders — now as the first line of This Build's info. */
  it('the page needs no introduction sentence, and keeps an accurate eyebrow and the no-settings claim', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(
      screen.queryByText("View this build's runtime status, data boundaries, provenance, and API access."),
    ).toBeNull();
    expect(screen.getByText('About This Build')).toBeInTheDocument();
    expect(screen.queryByText('Local Configuration')).not.toBeInTheDocument();
    const claim = screen.getByText(/no user-adjustable settings/i);
    expect(claim.closest('.widget-info'), 'the claim is This Build’s info').not.toBeNull();
  });

  /** Each API-access claim belongs to ONE tab. Counting only the total would
   *  pass if a string moved to the wrong surface, so the surface is pinned too. */
  it('the API-access copy renders on Integrations and nowhere else', async () => {
    const [overview, privacy, integrations, advanced] = await textOfEverySurface();
    const onIntegrations = [
      API_ACCESS_COPY.statusHeading,
      API_ACCESS_COPY.statusBody,
      API_ACCESS_COPY.credentialLine,
      API_ACCESS_COPY.requirementsNote,
      ...API_ACCESS_ROWS.map((r) => r.detail),
      ...API_KEY_REQUIREMENTS,
    ];
    for (const text of onIntegrations) {
      expect(integrations, `Integrations must own: ${text.slice(0, 48)}`).toContain(norm(text));
      for (const [name, other] of [
        ['Overview', overview],
        ['Privacy & Governance', privacy],
        ['Advanced', advanced],
      ] as const) {
        expect(other, `${name} leaked: ${text.slice(0, 48)}`).not.toContain(norm(text));
      }
    }
    // The Auth legend is the mirror case: the Explorer's alone.
    expect(advanced).toContain(norm(API_ACCESS_COPY.authMarkerLegend));
    expect(integrations).not.toContain(norm(API_ACCESS_COPY.authMarkerLegend));
  });

  it('the heading outline never skips a level on any surface', async () => {
    for (const surface of SURFACES) {
      stubFetchRoutes(fullRoutes());
      const view = renderSettings();
      surface.open();
      await surface.settle();
      const levels = Array.from(
        view.container.querySelectorAll('h1, h2, h3, h4, h5, h6'),
      ).map((h) => Number(h.tagName[1]));
      expect(levels.length, `${surface.name}: no headings`).toBeGreaterThan(0);
      for (let i = 1; i < levels.length; i += 1) {
        expect(levels[i] - levels[i - 1], `${surface.name}: ${levels.join(',')}`).toBeLessThanOrEqual(1);
      }
      view.unmount();
    }
  });
});

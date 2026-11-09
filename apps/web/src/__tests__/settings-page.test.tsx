import { describe, it, expect, afterEach, vi } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { render, screen, fireEvent, within, act, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from 'react-router-dom';

import { SettingsPage } from '../screens/SettingsPage';
import {
  SETTINGS_CARD_ANCHORS,
  SETTINGS_TAB_ALIASES,
  SETTINGS_TAB_IDS,
  ROUTES,
  isSettingsCardAnchor,
  isSettingsTab,
  isSettingsTabAlias,
  resolveSettingsTab,
} from '../lib/routes';
import {
  ABOUT_RESPONSE_FIELDS,
  API_ACCESS_COPY,
  NO_GUESSING,
  REPO_DOCS,
  SETTINGS_SOURCE_ENDPOINTS,
  dataRows,
  BROWSER_STORAGE_KEYS,
  BROWSER_STORAGE_SENTENCE,
  settingsFactsFrom,
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
  it('renders exactly the three specified tabs, with Overview selected by default', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map(accessibleTextOf)).toEqual(['Overview', 'Integrations', 'Advanced']);
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
      // Retired 2026-11-02 (owner's direction: no standing disclaimers).
      'Privacy & Governance',
      'Privacy',
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

  it('the tablist owns exactly three tabs and nothing else', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    /* Asserted over the DOM children: `role="tablist"` may only own `role="tab"`
       children (`aria-required-children`), which a name assertion would not see. */
    const children = Array.from(pageTablist().children);
    expect(children).toHaveLength(3);
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
      if (id === 'explorer') {
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
    // 2026-11-02: This Build's Build | Runtime switch and the Integrations view
    // buttons were retired (Runtime is a `<details>`; each Integrations card is one
    // disclosure), so only the open Endpoint Explorer may carry a switch.
    const floor: Record<string, number> = { overview: 0, integrations: 0, explorer: 0 };
    for (const id of ['overview', 'integrations', 'explorer']) {
      stubFetchRoutes(fullRoutes());
      const view = renderSettings(`/settings?tab=${id}`);
      await flushReads();
      if (id === 'explorer') await screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 });
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
   * WCAG 2.4.11 at 320px — RULED 2026-11-02 (Task 2 review, Important 4): the row is
   * NOT relied on to fit. ~~"Solved by layout, not by scrolling"~~ held only while
   * this host's font left 5.5px of slack, which CI's wider face does not. The row is
   * one line at every width that scrolls inside its own box, the layout sweep names
   * it (`ALLOW-SETTINGS-TABS-SCROLL`), and the selected tab is scrolled into view —
   * so no selected tab can sit off-screen. jsdom computes no layout, so the rules are
   * pinned from the stylesheet, and the scroll-into-view from a measured row.
   */
  it('keeps the tab row on one line that scrolls sideways inside its own box', () => {
    const css = readFileSync(resolve(__dirname, '..', 'screens/settings/settings-widgets.css'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '');
    const rulesFor = (selector: string) =>
      [...css.matchAll(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{([^}]*)\\}`, 'g'))]
        .map((m) => m[1])
        .join('\n');
    const tabRow = rulesFor('.settings-section-tabs');
    expect(tabRow).toMatch(/overflow-x\s*:\s*auto/);
    expect(tabRow).toMatch(/flex-wrap\s*:\s*nowrap/);
    expect(tabRow).not.toMatch(/display\s*:\s*grid/);
    // The layout sweep knows about it, so the deliberate scroller is declared.
    const allow = readFileSync(resolve(__dirname, '..', '..', 'e2e/layout-allowlist.ts'), 'utf8');
    expect(allow).toMatch(/id: 'ALLOW-SETTINGS-TABS-SCROLL',\s*match: '\.settings-section-tabs'/);
  });

  it('scrolls the selected tab into view when the row overflows', () => {
    const proto = HTMLElement.prototype;
    const saved = ['scrollWidth', 'clientWidth', 'offsetLeft', 'offsetWidth', 'offsetParent', 'scrollLeft'].map(
      (k) => [k, Object.getOwnPropertyDescriptor(proto, k)] as const,
    );
    const scrolled = new WeakMap<Element, number>();
    const isRow = (el: Element) => el.getAttribute('role') === 'tablist';
    const tabIndexOf = (el: Element) => Array.from(el.parentElement?.children ?? []).indexOf(el);
    Object.defineProperty(proto, 'scrollWidth', { configurable: true, get() { return isRow(this) ? 600 : 0; } });
    Object.defineProperty(proto, 'clientWidth', { configurable: true, get() { return isRow(this) ? 240 : 0; } });
    Object.defineProperty(proto, 'offsetWidth', { configurable: true, get() { return this.getAttribute('role') === 'tab' ? 200 : 0; } });
    Object.defineProperty(proto, 'offsetLeft', { configurable: true, get() { return this.getAttribute('role') === 'tab' ? tabIndexOf(this) * 200 : 0; } });
    Object.defineProperty(proto, 'offsetParent', { configurable: true, get() { return this.closest('[role="tablist"]'); } });
    Object.defineProperty(proto, 'scrollLeft', {
      configurable: true,
      get() { return scrolled.get(this) ?? 0; },
      set(v: number) { scrolled.set(this, v); },
    });
    try {
      stubFetchRoutes(fullRoutes());
      renderSettings('/settings?tab=advanced');
      // Advanced is the third tab, at 400–600px in a 240px-wide row: the row must
      // scroll so its right edge is in view.
      expect(pageTablist().scrollLeft).toBe(600 - 240);
    } finally {
      for (const [k, d] of saved) {
        if (d) Object.defineProperty(proto, k, d);
        else delete (proto as unknown as Record<string, unknown>)[k];
      }
    }
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
    expect(tab('Integrations')).not.toHaveAttribute('aria-controls');
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
    openTab('Integrations');
    expect(tab('Integrations')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'settings-tabpanel-integrations');
  });

  it('Arrow / Home / End move the selection (automatic activation)', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();

    fireEvent.keyDown(tab('Overview'), { key: 'ArrowRight' });
    expect(tab('Integrations')).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(tab('Integrations'), { key: 'End' });
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
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');
  });

  it('keyboard selection moves focus with it, so the arrow keys stay usable', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    tab('Overview').focus();
    fireEvent.keyDown(tab('Overview'), { key: 'End' });
    expect(tab('Advanced')).toHaveFocus();
    expect(tab('Advanced')).toHaveAttribute('tabindex', '0');
  });

  // ~~"states plainly that there is nothing to configure"~~ — that sentence was
  // retired 2026-11-02; what stays pinned is that no setting is INVENTED.
  it('invents no settings: no input control on Overview', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
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
    ['privacy', 'overview', 'Data'],
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

  /*
   * A CARD ANCHOR: `?tab=data` is where Statistics' "Open Data Settings" goes. It
   * opens Overview, scrolls the Data card into view and moves focus to its
   * heading, so the reader lands ON the card. Not a retired alias, and no alias
   * moves focus (the walkthrough's `?tab=help` manages focus itself).
   */
  it('?tab=data opens Overview, scrolls the Data card into view and focuses its heading', async () => {
    const scrolled: Element[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this);
    };
    try {
      stubFetchRoutes(fullRoutes());
      renderSettings(ROUTES.settingsTab('data'));
      expect(Object.keys(SETTINGS_CARD_ANCHORS)).toEqual(['data']);
      expect(isSettingsCardAnchor('data')).toBe(true);
      expect(isSettingsTabAlias('data')).toBe(false);
      expect(isSettingsTab('data')).toBe(false);
      expect(resolveSettingsTab('data')).toEqual({ tab: 'overview', widget: 'settings-data-heading', focus: true });
      expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');
      const region = screen.getByRole('region', { name: 'Data' });
      const heading = within(region).getByRole('heading', { name: 'Data' });
      await waitFor(() => expect(scrolled).toContain(region));
      expect(document.activeElement).toBe(heading);
      expect(heading).toHaveAttribute('tabindex', '-1'); // focusable from script, not a Tab stop
      expect(search()).toBe('?tab=data');
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it('a retired alias scrolls its widget into view but leaves focus where it was', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=privacy');
    const region = screen.getByRole('region', { name: 'Data' });
    await screen.findAllByText(dataRows(settingsFactsFrom(aboutResponse))[0].text);
    expect(region.contains(document.activeElement)).toBe(false);
  });

  it('?tab=api opens Integrations with the key state as a STATE, not a disabled button', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=api');
    expect(tab('Integrations')).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(API_ACCESS_COPY.stateLine)).toBeInTheDocument();
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
    expect(screen.getByRole('region', { name: 'Data' })).toBeInTheDocument();
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });

  it('the tab id guard accepts exactly the three ids, and the alias guard exactly the six retired ones', () => {
    for (const id of SETTINGS_TAB_IDS) expect(isSettingsTab(id)).toBe(true);
    expect([...SETTINGS_TAB_IDS]).toEqual(['overview', 'integrations', 'advanced']);
    expect(Object.keys(SETTINGS_TAB_ALIASES).sort()).toEqual([
      'about',
      'api',
      'explorer',
      'help',
      'mcp',
      'privacy',
    ]);
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

    openTab('Integrations');
    openTab('Advanced');
    expect(tab('Advanced')).toHaveAttribute('aria-selected', 'true');

    back();
    expect(tab('Integrations')).toHaveAttribute('aria-selected', 'true');
    expect(search()).toBe('?tab=integrations');

    back();
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');

    forward();
    expect(tab('Integrations')).toHaveAttribute('aria-selected', 'true');
    forward();
    expect(tab('Advanced')).toHaveAttribute('aria-selected', 'true');
  });

  it('a deep-linked tab survives a refresh (a fresh mount at the same URL)', async () => {
    stubFetchRoutes(fullRoutes());
    const first = renderSettings('/settings?tab=explorer');
    await screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 });
    first.unmount();

    // Re-mounting at the same entry is what a reload does: no client state
    // carries over, so the tab can only come back from the URL.
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=explorer');
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

    for (const name of ['Integrations', 'Advanced', 'Overview']) {
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
    stubFetchRoutes({ ...fullRoutes(), [ABOUT_URL]: () => new Promise(() => {}) } as never);
    renderSettings();
    expect(screen.getAllByRole('status').some((s) => /Loading app info/.test(s.textContent ?? ''))).toBe(true);
  });

  /*
   * THE DATA CARD (2026-11-02) — the facts the retired Privacy & Governance tab
   * carried that a reader needs (where records live, what an export writes, how a
   * walkthrough is kept, what the browser keeps), as four plain rows written from the
   * reported persistence. No caveats; no claim the code does not make.
   */
  it('renders the Data card as four plain rows, from the live persistence value', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    const card = await screen.findByRole('region', { name: 'Data' });
    await within(card).findByText('Experiment Records');
    const labels = within(card).getAllByRole('term').map((t) => t.textContent);
    expect(labels).toEqual(dataRows(settingsFactsFrom(aboutResponse)).map((r) => r.label));
    expect(labels.length).toBeLessThanOrEqual(4);
    for (const row of dataRows(settingsFactsFrom(aboutResponse))) {
      expect(card.textContent).toContain(row.text);
    }
  });

  it.each([
    ['durable', /database/i],
    ['ephemeral', /files on this server/i],
    ['unavailable', /not reaching it/i],
  ])('the Experiment Records row follows persistence=%s', (persistence, pattern) => {
    const row = dataRows({ dataRegime: 'synthetic-only', persistence, recordSchemaVersion: '1.05' })[0];
    expect(row.label).toBe('Experiment Records');
    expect(row.text).toMatch(pattern);
  });

  it('names an unrecognised persistence value instead of picking the nearest branch', () => {
    const row = dataRows({ dataRegime: 'synthetic-only', persistence: 'archival', recordSchemaVersion: '1.05' })[0];
    expect(row.text).toContain('archival');
    expect(row.text).not.toMatch(/survive a restart|files on this server|not reaching/i);
  });

  it('carries none of the retired standing disclaimers', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByRole('region', { name: 'Data' });
    await flushReads();
    const text = document.body.textContent ?? '';
    for (const retired of [
      'Data Safety',
      'Is this workspace safe for my data?',
      'Synthetic Workspace',
      'All Boundaries',
      'This build has no user-adjustable settings.',
      'About This Build',
    ]) {
      expect(text, retired).not.toContain(retired);
    }
  });

  it('?tab=privacy lands on Overview and brings the Data card into view', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=privacy');
    expect(selectedTabLabel()).toBe('Overview');
    expect(await screen.findByRole('region', { name: 'Data' })).toBeInTheDocument();
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    expect((await screen.findAllByRole('alert')).length).toBeGreaterThan(0);
  });
});

// --- Data & Privacy -----------------------------------------------------------


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
  it('This Build shows its Build rows, with Runtime one press away in a disclosure', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    expect(await screen.findByText('0.1.0')).toBeInTheDocument();
    const build = screen.getByRole('region', { name: 'This Build' });
    const labelsIn = (el: Element) =>
      Array.from(el.querySelectorAll(':scope > dl .settings-figure-label, :scope > .settings-figure .settings-figure-label')).map(
        (l) => l.textContent,
      );
    // The app's chevron `Disclosure`, not a native `<details>` (2026-11-02).
    const runtime = build.querySelector('.disclosure.settings-runtime') as HTMLElement;
    expect(runtime).not.toBeNull();
    expect(build.querySelector('details.settings-runtime')).toBeNull();
    const trigger = runtime.querySelector('.disclosure-trigger') as HTMLButtonElement;
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger.textContent).toBe('Runtime');
    expect(runtime.querySelector('.disclosure-body')).toHaveAttribute('hidden');
    expect(Array.from(runtime.querySelectorAll('.settings-figure-label')).map((l) => l.textContent)).toEqual([
      'Runtime Mode',
      'Data Regime',
      'Persistence',
    ]);
    const buildRows = Array.from(build.querySelectorAll('.settings-figure-label'))
      .filter((l) => !runtime.contains(l))
      .map((l) => l.textContent);
    expect(buildRows).toEqual(['App Version', 'Build Commit', 'Record Schema', 'Core']);
    // No in-widget view switch any more.
    expect(build.querySelector('.widget-views')).toBeNull();
    expect(labelsIn).toBeTypeOf('function');
    expect(build.querySelector('.widget-headline .widget-figure')?.textContent).toBe('ISAAC 0.1.0');
    expect(build.querySelector('.widget-headline .widget-figure-unit')?.textContent).toBe('Schema v1.05');
    expect(container.querySelectorAll('.settings-figure')).toHaveLength(7);
  });

  it('shows the short commit on Overview and the full SHA only inside Technical Details', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    const short = screen.getByText('fakecommit00');
    expect(short.closest('details')).toBeNull();
    expect(screen.queryByText('fakecommit0000settingsp364')).toBeNull();

    openTab('Advanced');
    // The app's chevron `Disclosure` since 2026-11-02, not a native `<details>`.
    const technical = document.querySelector('.disclosure.settings-technical') as HTMLElement;
    expect(technical).not.toBeNull();
    expect(document.querySelector('details.settings-technical')).toBeNull();
    const trigger = technical.querySelector('.disclosure-trigger') as HTMLButtonElement;
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger.textContent).toBe('Technical Details');
    const full = screen.getAllByText('fakecommit0000settingsp364');
    expect(full).toHaveLength(1);
    expect(technical.contains(full[0])).toBe(true);
  });

  it('Technical Details carries the raw field names, source endpoints, and doc paths', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=advanced');
    const technical = document.querySelector('.disclosure.settings-technical') as HTMLElement;
    const labels = Array.from(technical.querySelectorAll('dt')).map((dt) => dt.textContent);
    expect(labels).toEqual([
      'Build Commit (Full)',
      'Response Fields',
      'Source Endpoints',
      'Repository Documentation',
    ]);
    for (const field of [...ABOUT_RESPONSE_FIELDS, ...SETTINGS_SOURCE_ENDPOINTS, ...REPO_DOCS]) {
      const el = within(technical).getByText(field);
      expect(el.tagName).toBe('CODE');
      expect(el.closest('a')).toBeNull();
    }
    expect(within(technical).getByText(/not served as pages by this app/i)).toBeInTheDocument();
  });

  it('This Build keeps the provenance legend and the no-guessing principle behind its info toggle', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    const build = screen.getByRole('region', { name: 'This Build' });
    const info = build.querySelector('.widget-info') as HTMLElement;
    expect(info).toHaveAttribute('hidden');
    expect(info.textContent).toMatch(/marked with the clock is read per request/i);
    expect(info.textContent).toContain(NO_GUESSING.text);
    // The retired caveats are gone.
    expect(info.textContent).not.toMatch(/no user-adjustable settings|this screen computes none|truth plane/i);
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
    expect(await screen.findByText('not set')).toBeInTheDocument();
    expect(screen.queryByText(/[0-9a-f]{12}/)).toBeNull();
  });

  it('lists in-repo documentation as plain references, not fetched/rendered content', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=advanced');
    expect(screen.getByText('CLAUDE.md')).toBeInTheDocument();
    expect(screen.getByText('AGENTS.md')).toBeInTheDocument();
    expect(screen.getByText('CLAUDE.md').tagName).toBe('CODE');
    expect(screen.getByText(/not served as pages by this app/i)).toBeInTheDocument();
  });

  it('Advanced is a Related Tools link list, not three launcher cards', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=advanced');
    const related = screen.getByRole('region', { name: 'Related Tools' });
    const links = within(related).getAllByRole('link').map((a) => a.textContent);
    expect(links).toEqual(['Project Memory', 'Validator', 'Schema Reference']);
    for (const retired of ['settings-memory-heading', 'settings-validator-heading', 'settings-schema-heading']) {
      expect(document.getElementById(retired), retired).toBeNull();
    }
    expect(document.body.textContent).not.toMatch(/None of these is part of recording an experiment/);
  });

  it('the Endpoint Explorer is behind a closed disclosure on Advanced, and opens on ?tab=explorer', async () => {
    stubFetchRoutes(fullRoutes());
    const view = renderSettings('/settings?tab=advanced');
    const trigger = screen.getByRole('button', { name: 'Browse Every Operation' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(view.container.querySelector('.api-browser-list')).toBeNull();
    view.unmount();

    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=explorer');
    expect(screen.getByRole('button', { name: 'Browse Every Operation' })).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByRole('heading', { name: 'Browse Endpoints', level: 3 })).toBeInTheDocument();
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
  // The explorer sits behind a closed disclosure since 2026-11-02.
  fireEvent.click(screen.getByRole('button', { name: 'Browse Every Operation' }));
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
    fireEvent.click(screen.getByRole('button', { name: 'Browse Every Operation' }));
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
    fireEvent.click(screen.getByRole('button', { name: 'Browse Every Operation' }));
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
    open: () => {
      openTab('Advanced');
      fireEvent.click(screen.getByRole('button', { name: 'Browse Every Operation' }));
    },
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
    fireEvent.click(screen.getByRole('button', { name: 'Browse Every Operation' }));
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

/*
 * ~~"every canonical string appears exactly once across the tabs"~~ — that describe
 * counted the twelve concept summaries and definitions, retired 2026-11-02. The
 * duplication guard it carried still applies to what replaced them: each Data row,
 * the API Access state line and the full commit SHA render exactly once.
 */
describe('Settings — no fact is stated twice across the tabs', () => {
  it.each([
    ...dataRows(settingsFactsFrom(aboutResponse)).map((r) => [r.label, r.text] as const),
    ['API Access state line', API_ACCESS_COPY.stateLine] as const,
    ['the full commit SHA', 'fakecommit0000settingsp364'] as const,
  ])('%s is rendered exactly once', async (_what, text) => {
    const all = (await textOfEverySurface()).join('\n');
    expect(countOccurrences(all, norm(text))).toBe(1);
  });
});


// --- the Data card's "In Your Browser" row is the whole list -----------------

/*
 * REVIEW 2026-11-02 (Important 2). The row named two of the seven things this app
 * keeps in the browser — and left out a name the reader types. It is now one
 * sentence over a key registry, and this scan keeps the registry honest: every
 * `isaac.*` key in a source file that touches `localStorage`/`sessionStorage` must
 * be listed, and every listed key must still exist in the source.
 */
describe('Settings — the Data card says everything the browser keeps', () => {
  const SRC = resolve(__dirname, '..');
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) return name === '__tests__' || name === 'test' ? [] : files(path);
      return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
    });
  const sourceKeys = () => {
    const keys = new Set<string>();
    for (const path of files(SRC)) {
      if (path.endsWith(join('lib', 'settingsContent.ts'))) continue;
      const text = readFileSync(path, 'utf8');
      if (!/localStorage|sessionStorage/.test(text)) continue;
      for (const m of text.matchAll(/['`](isaac\.[A-Za-z0-9._-]+)['`]/g)) keys.add(m[1]!);
    }
    return keys;
  };

  it('lists every storage key the source uses, and none it no longer uses', () => {
    const found = sourceKeys();
    // Precondition: the scan reaches the known stores, so an empty pass cannot.
    expect(found.has('isaac.localImports.by')).toBe(true);
    expect(found.has('isaac.tutorial.session.v1')).toBe(true);
    const listed = new Set(BROWSER_STORAGE_KEYS.map((k) => k.key));
    expect([...found].filter((k) => !listed.has(k)), 'stored but not on the Data card').toEqual([]);
    expect([...listed].filter((k) => !found.has(k)), 'on the Data card but no longer stored').toEqual([]);
  });

  it('renders that sentence as the In Your Browser row, naming the personal datum', () => {
    const row = dataRows({ dataRegime: 'synthetic-only', persistence: 'ephemeral', recordSchemaVersion: '1.05' }).find(
      (r) => r.label === 'In Your Browser',
    );
    expect(row?.text).toBe(BROWSER_STORAGE_SENTENCE);
    expect(BROWSER_STORAGE_SENTENCE).toMatch(/name you enter for Local Imports/);
    expect(BROWSER_STORAGE_SENTENCE).toMatch(/up to 50 records/);
    expect(BROWSER_STORAGE_SENTENCE).toMatch(/walkthrough/);
    expect(BROWSER_STORAGE_SENTENCE).toMatch(/Assistant conversations/);
  });

  it('on a durable deployment, says exports live outside the database (Minor 1)', () => {
    const rows = (persistence: string) =>
      dataRows({ dataRegime: 'synthetic-only', persistence, recordSchemaVersion: '1.05' });
    const exports = (p: string) => rows(p).find((r) => r.label === 'Exports')!.text;
    expect(exports('durable')).toMatch(/outside the database/);
    for (const p of ['durable', 'ephemeral', 'unavailable']) {
      expect(exports(p)).not.toMatch(/in your browser/i);
    }
  });
});

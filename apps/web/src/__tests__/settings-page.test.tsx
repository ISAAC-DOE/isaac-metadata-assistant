import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, within, act } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from 'react-router-dom';

import { SettingsPage } from '../screens/SettingsPage';
import { titleCase } from '../lib/labels';
import { SETTINGS_TAB_IDS, ROUTES, isSettingsTab } from '../lib/routes';
import {
  ABOUT_RESPONSE_FIELDS,
  API_ACCESS_COPY,
  API_ACCESS_ROWS,
  API_KEY_REQUIREMENTS,
  REPO_DOCS,
  SETTINGS_SOURCE_ENDPOINTS,
  settingsAboutCopy,
  settingsConcepts,
  settingsFactsFrom,
} from '../lib/settingsContent';
import {
  stubFetchRoutes,
  stubFetchDown,
  aboutResponse,
  aboutResponseNoCommit,
  graphStatusAvailable,
  openApiFixture,
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
const SETTINGS_TABLIST_NAME = 'Settings & API sections';

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
  };
}

const tab = (name: string) => screen.getByRole('tab', { name });

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
  return selected[0].textContent ?? '';
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- tab structure ------------------------------------------------------------

describe('Settings — tabs', () => {
  it('renders exactly the seven specified tabs, with Overview selected by default', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();

    /* R0 added Help & Tutorial. It is last on purpose: every tab before it
       reports what this build is, and it is the one thing on the page a reader
       ACTS on (replaying the guided walkthrough), so it does not belong in the
       middle of a readout.

       Connect Your Agent is the SEVENTH tab and sits BEFORE Help, at position
       six: it reports a deployment state and offers no action, so it belongs
       with the readout tabs, and specifically next to the two other tabs about
       reaching this build as a program. */
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual([
      'Overview',
      'Data & Privacy',
      'About',
      'API Access',
      'Endpoint Explorer',
      'Connect Your Agent',
      'Help & Tutorial',
    ]);
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'settings-tabpanel-overview');
    // The renamed tab and the retired nested sub-tablist are both gone.
    expect(screen.queryByRole('tab', { name: 'API' })).toBeNull();
    expect(screen.queryByRole('tab', { name: 'API Keys' })).toBeNull();
    expect(screen.queryByRole('tab', { name: 'Documentation' })).toBeNull();
  });

  /**
   * The `keys | docs` sub-tablist is deleted, not hidden. Asserting the tablist
   * COUNT on every tab is stronger than asserting the two old labels are absent:
   * it fails for any nested page-level tablist, whatever it is called.
   *
   * The count is a PRE-LOAD fact, though. The code-sample language tabs inside
   * the Endpoint Explorer sit behind a collapsed `<details>` — hidden in a real
   * browser, but jsdom applies no such UA style, so once the contract has loaded
   * they ARE in the accessibility tree and this page has two tablists. Hence the
   * name-scoped resolution below.
   */
  it('has exactly ONE tablist on every tab — the nested sub-tablist is gone', () => {
    for (const id of SETTINGS_TAB_IDS) {
      stubFetchRoutes(fullRoutes());
      const view = renderSettings(ROUTES.settingsTab(id));
      const lists = screen.getAllByRole('tablist');
      expect(lists, `${id}: expected one tablist`).toHaveLength(1);
      /* Resolve the PAGE tablist by its accessible name, not as `lists[0]`.
         The count above holds only while the stubbed fetches are still
         unresolved: once the Endpoint Explorer has its contract, the detail
         pane's Code Examples section renders a SECOND, nested (non-page-level)
         tablist of its own. Positional indexing would then silently assert about
         whichever tablist happened to come first in the DOM, so this guard would
         read as "the page tablist is named correctly" while actually only
         meaning "there happens to be one tablist right now". Do not simplify it
         back to `lists[0]`. */
      expect(pageTablist(), `${id}: page tablist resolved by name`).toBeInTheDocument();
      view.unmount();
    }
  });

  it('uses a roving tabindex: only the selected tab is in the tab order', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(tab('Overview')).toHaveAttribute('tabindex', '0');
    expect(tab('API Access')).toHaveAttribute('tabindex', '-1');
    expect(tab('Endpoint Explorer')).toHaveAttribute('tabindex', '-1');
    expect(screen.getAllByRole('tab').filter((t) => t.getAttribute('tabindex') === '0')).toHaveLength(1);
  });

  it('only the selected tab points at a panel via aria-controls', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(tab('Overview')).toHaveAttribute('aria-controls', 'settings-tabpanel-overview');
    expect(tab('About')).not.toHaveAttribute('aria-controls');
    expect(tab('Endpoint Explorer')).not.toHaveAttribute('aria-controls');
  });

  it('every tab renders exactly one panel, labelled by its own tab', () => {
    for (const id of SETTINGS_TAB_IDS) {
      stubFetchRoutes(fullRoutes());
      const view = renderSettings(ROUTES.settingsTab(id));
      const panels = screen.getAllByRole('tabpanel');
      expect(panels, `${id}: expected one panel`).toHaveLength(1);
      /* Resolve the SETTINGS panel by its accessible name — each panel is
         `aria-labelledby` its own tab, so the name is that tab's label — rather
         than as `panels[0]` or an unscoped `getByRole('tabpanel')`. The count
         above is only true pre-load: once the Endpoint Explorer has its
         contract, the detail pane's Code Examples section renders its own nested
         tabpanel, at which point an unscoped query is ambiguous and a positional
         one can resolve the wrong element. Name-scoping is what makes this guard
         assert the thing it claims. */
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
    openTab('About');
    expect(tab('About')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'settings-tabpanel-about');
  });

  it('Arrow / Home / End move the selection (automatic activation)', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();

    fireEvent.keyDown(tab('Overview'), { key: 'ArrowRight' });
    expect(tab('Data & Privacy')).toHaveAttribute('aria-selected', 'true');

    // End is the LAST tab — Help & Tutorial, now seventh rather than sixth.
    fireEvent.keyDown(tab('Data & Privacy'), { key: 'End' });
    expect(tab('Help & Tutorial')).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(tab('Help & Tutorial'), { key: 'Home' });
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(tab('Overview'), { key: 'ArrowLeft' });
    expect(tab('Help & Tutorial')).toHaveAttribute('aria-selected', 'true');

    // ArrowLeft from the last tab reaches the one before it, so the wrap is
    // walking all seven entries rather than a stale shorter array.
    fireEvent.keyDown(tab('Help & Tutorial'), { key: 'ArrowLeft' });
    expect(tab('Connect Your Agent')).toHaveAttribute('aria-selected', 'true');
  });

  it('keyboard selection moves focus with it, so the arrow keys stay usable', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    tab('Overview').focus();
    fireEvent.keyDown(tab('Overview'), { key: 'End' });
    expect(tab('Help & Tutorial')).toHaveFocus();
    expect(tab('Help & Tutorial')).toHaveAttribute('tabindex', '0');
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

  it('?tab=api opens API Access with its real content, not an empty panel', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=api');
    expect(tab('API Access')).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(API_ACCESS_COPY.emptyTitle)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create API Key/i })).toBeDisabled();
  });

  it('?tab=explorer opens the Endpoint Explorer with the contract rendered', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=explorer');
    expect(tab('Endpoint Explorer')).toHaveAttribute('aria-selected', 'true');
    expect(
      await screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 }),
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

  it('the tab id guard accepts exactly the five ids and nothing else', () => {
    for (const id of SETTINGS_TAB_IDS) expect(isSettingsTab(id)).toBe(true);
    for (const bad of ['', 'API', 'docs', 'keys', 'overview ', null, undefined]) {
      expect(isSettingsTab(bad), `must reject ${JSON.stringify(bad)}`).toBe(false);
    }
  });

  /**
   * `ROUTES.settingsTab` has NO in-app consumer by design (see `lib/routes.ts`):
   * the page switches tabs with `setSearchParams` over a copy of the current
   * params, which preserves any other query parameter, whereas navigating to a URL
   * built by the helper would drop them. This test is the anti-drift guard that
   * arrangement requires — the helper and the real mechanism must produce the same
   * query string for EVERY tab, so the helper cannot rot into a stale convention.
   */
  it('the link helper and the page’s own tab mechanism agree for every tab', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    for (const [id, label] of [
      ['privacy', 'Data & Privacy'],
      ['about', 'About'],
      ['api', 'API Access'],
      ['explorer', 'Endpoint Explorer'],
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

    openTab('Data & Privacy');
    openTab('API Access');
    expect(tab('API Access')).toHaveAttribute('aria-selected', 'true');

    back();
    expect(tab('Data & Privacy')).toHaveAttribute('aria-selected', 'true');
    expect(search()).toBe('?tab=privacy');

    back();
    expect(tab('Overview')).toHaveAttribute('aria-selected', 'true');

    forward();
    expect(tab('Data & Privacy')).toHaveAttribute('aria-selected', 'true');
    forward();
    expect(tab('API Access')).toHaveAttribute('aria-selected', 'true');
  });

  it('a deep-linked tab survives a refresh (a fresh mount at the same URL)', async () => {
    stubFetchRoutes(fullRoutes());
    const first = renderSettings('/settings?tab=explorer');
    await screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 });
    first.unmount();

    // Re-mounting at the same entry is what a reload does: no client state
    // carries over, so the tab can only come back from the URL.
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?tab=explorer');
    expect(tab('Endpoint Explorer')).toHaveAttribute('aria-selected', 'true');
    expect(
      await screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 }),
    ).toBeInTheDocument();
  });

  it('an in-app deep link into one tab preserves every other query parameter', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings('/settings?keep=me&tab=about');
    expect(tab('About')).toHaveAttribute('aria-selected', 'true');
    openTab('API Access');
    expect(search()).toContain('keep=me');
    expect(search()).toContain('tab=api');
  });

  /** Every page-level fetch is issued ONCE, so the five tabs are pure client
   *  state: no tab switch, and no Back/Forward, may re-hit the backend. */
  it('switching tabs never re-hits the backend', async () => {
    const hits = stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    const initial = [...hits];
    expect(initial.filter((h) => h === ABOUT_URL)).toHaveLength(1);
    expect(initial.filter((h) => h === OPENAPI_URL)).toHaveLength(1);
    // The graph status is issued once at mount too. The `hits` equality below
    // catches a re-fetch on a tab switch, but NOT a double-issue at mount —
    // that would already be in `initial`. Pin it explicitly, as for the other
    // two page-level fetches.
    expect(initial.filter((h) => h === GRAPH_STATUS_URL)).toHaveLength(1);

    for (const name of ['Data & Privacy', 'About', 'API Access', 'Endpoint Explorer', 'Overview']) {
      openTab(name);
    }
    await screen.findByText('0.1.0');
    back();
    forward();

    expect(hits).toEqual(initial);
  });
});

// --- Overview -----------------------------------------------------------------

describe('Settings — Overview', () => {
  it('shows a loading state before the fetch resolves', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(screen.getByText('Loading app info…')).toBeInTheDocument();
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
   * P36V PR3 — Overview is a SUMMARY. Each boundary appears as its one-line
   * `summary`, and the canonical definitions (asserted in the Data & Privacy
   * suite, and counted in the "appears exactly once" suite) render nowhere here.
   */
  it('names every boundary as a one-line summary, not a second copy of the definition', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    await screen.findByText('0.1.0');

    const concepts = settingsConcepts(settingsFactsFrom(aboutResponse));
    const text = norm(container.textContent ?? '');
    for (const concept of concepts) {
      expect(text, `Overview must summarize "${concept.heading}"`).toContain(norm(concept.summary));
      expect(text, `Overview must NOT define "${concept.heading}"`).not.toContain(
        norm(concept.detail),
      );
    }
    // Every boundary is labelled, so a summary is never an orphan sentence.
    for (const concept of concepts) {
      expect(screen.getByText(concept.heading)).toBeInTheDocument();
    }
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

    expect(
      screen.getByText(/this screen cannot report whether access is restricted/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/outside the application/i)).not.toBeInTheDocument();
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

    const labels = Array.from(container.querySelectorAll('.settings-figure dt')).map(
      (dt) => dt.textContent,
    );
    expect(labels).toEqual([
      'App Version',
      'Build Commit',
      'Record Schema',
      'Runtime Mode',
      'Data Regime',
      'Persistence',
      'Core',
    ]);
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
    });
    renderSettings();
    expect(
      await screen.findByText(/reports the data regime as "mixed-somehow"/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/only unmistakably synthetic data is in scope/i)).not.toBeInTheDocument();
  });

  it('drops the ephemeral-storage sentence when the backend reports another persistence', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: { ...aboutResponse, persistence: 'durable' } },
      [OPENAPI_URL]: { body: openApiFixture },
      [GRAPH_STATUS_URL]: { body: graphStatusAvailable },
    });
    renderSettings();
    expect(await screen.findByText(/reports persistence as "durable"/i)).toBeInTheDocument();
    expect(screen.queryByText(/there is no database/i)).not.toBeInTheDocument();
  });

  /**
   * The jump nav now has FOUR entries because there are four deeper tabs, and
   * each one is asserted to land on its own tab AND to write its own `?tab=`
   * value — stronger than the single "browse the api" click it replaces, which
   * only checked that one button changed one `aria-selected`.
   */
  it.each([
    ['Data & Privacy Detail', 'privacy', 'Data & Privacy'],
    ['Version & Provenance', 'about', 'About'],
    ['API Access', 'api', 'API Access'],
    ['Endpoint Explorer', 'explorer', 'Endpoint Explorer'],
  ])('links into the deeper tabs: %s', async (label, id, tabName) => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    await screen.findByText('0.1.0');
    const nav = screen.getByRole('navigation', { name: 'More settings detail' });
    fireEvent.click(within(nav).getByRole('button', { name: label }));
    expect(tab(tabName)).toHaveAttribute('aria-selected', 'true');
    expect(search()).toBe(`?tab=${id}`);
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

describe('Settings — Data & Privacy', () => {
  it('covers storage, reset, telemetry, models, memory, truth, and access — in Title Case', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Data & Privacy');
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
    for (const concept of concepts) {
      // The canonical definition is HERE, under its own heading, exactly once.
      const heading = screen.getByRole('heading', { name: concept.heading });
      expect(heading).toBeInTheDocument();
      expect(heading.tagName).toBe('H3');
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
    openTab('Data & Privacy');
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
    openTab('Data & Privacy');
    await screen.findByText(/two things are stored/i);

    // Slice 2A (I5) sweep. Both needles named copy that has been retired for
    // being untrue of the deployment, and both are replaced by a needle from
    // the SAME concept's new definition — not softened into a tautology:
    //   · /only unmistakably synthetic data is in scope/ → the mode sentence
    //     that replaced it. `synthetic-data-only` still owns a definition here.
    //   · /there is no database/ → the workspace-scoped storage sentence.
    // Each string is still asserted to be rendered on Data & Privacy exactly as
    // `settingsContent.ts` authors it; only the wording being pinned moved.
    expect(
      screen.getByText(/this deployment runs in synthetic-only mode: file upload is refused/i),
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
    openTab('Data & Privacy');
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

  it('says there is no language model and nothing typed leaves the app', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('Data & Privacy');
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
    openTab('Data & Privacy');
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
    openTab('Data & Privacy');
    expect(
      await screen.findByText(/never a correctness ruling — and it cannot mark a record valid/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/decided only by the official isaac v1\.05 schema/i)).toBeInTheDocument();
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    openTab('Data & Privacy');
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });
});

// --- About --------------------------------------------------------------------

describe('Settings — About', () => {
  /**
   * P36V PR3: About is IDENTITY and PROVENANCE only. Runtime Mode / Data Regime
   * / Persistence used to be repeated here as three of six identical rows —
   * they are runtime status, so they now live on Overview alone.
   */
  it('renders identity only: version, short commit, schema, core — no runtime status', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('About');
    expect(await screen.findByText('0.1.0')).toBeInTheDocument();
    expect(screen.getByText('v1.05')).toBeInTheDocument();
    expect(screen.getByText('isaac_records')).toBeInTheDocument();

    expect(
      Array.from(container.querySelectorAll('.settings-figure dt')).map((dt) => dt.textContent),
    ).toEqual(['App Version', 'Build Commit', 'ISAAC Record Schema', 'Core']);
    // The runtime values Overview owns are not restated here.
    expect(screen.queryAllByText('synthetic-only')).toHaveLength(0);
    expect(screen.queryByText('ephemeral')).not.toBeInTheDocument();
  });

  /**
   * The short sha is prominent; the FULL sha renders in exactly one place on the
   * whole page — inside this collapsed disclosure. Rendering it inline again
   * fails this test.
   */
  it('shows the short commit inline and the full SHA only inside Technical Details', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('About');
    await screen.findByText('0.1.0');

    const short = screen.getByText('fakecommit00');
    expect(short.closest('details')).toBeNull();

    const full = screen.getAllByText('fakecommit0000settingsp364');
    expect(full).toHaveLength(1);
    const drawer = container.querySelector('details.settings-technical') as HTMLDetailsElement;
    expect(drawer).not.toBeNull();
    expect(drawer.open).toBe(false);
    expect(drawer.querySelector('summary')?.textContent).toBe('Technical Details'); // Title Case
    expect(full[0].closest('details')).toBe(drawer);
  });

  it('Technical Details carries the raw field names, source endpoints, and doc paths', async () => {
    stubFetchRoutes(fullRoutes());
    const { container } = renderSettings();
    openTab('About');
    await screen.findByText('0.1.0');

    const drawer = container.querySelector('details.settings-technical') as HTMLElement;
    const labels = Array.from(drawer.querySelectorAll('dt')).map((dt) => dt.textContent);
    expect(labels).toEqual([
      'Build Commit (Full)',
      'Response Fields',
      'Source Endpoints',
      'Repository Documentation',
    ]);
    for (const field of [...ABOUT_RESPONSE_FIELDS, ...SETTINGS_SOURCE_ENDPOINTS, ...REPO_DOCS]) {
      const el = within(drawer).getByText(field);
      // Raw identifiers render verbatim as inert <code>, never re-cased or linked.
      expect(el.tagName).toBe('CODE');
      expect(el.closest('a')).toBeNull();
    }
    // The visible surface keeps the provenance CLAIM; only the raw path moved.
    expect(
      screen.getByText(/rendered verbatim — this screen computes none of these values/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/not served as pages by this app/i)).toBeInTheDocument();
  });

  it('renders an honest "not set" state when no build commit was injected (never fabricates one)', async () => {
    stubFetchRoutes({
      [ABOUT_URL]: { body: aboutResponseNoCommit },
      [OPENAPI_URL]: { body: openApiFixture },
      [GRAPH_STATUS_URL]: { body: graphStatusAvailable },
    });
    renderSettings();
    openTab('About');
    expect(await screen.findByText(/not set \(no build identity injected\)/i)).toBeInTheDocument();
  });

  it('states the truth-vs-memory authority boundary and the no-guessing policy', async () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    openTab('About');
    await screen.findByText('0.1.0');
    const copy = settingsAboutCopy(settingsFactsFrom(aboutResponse));
    expect(screen.getByText('Truth vs. Memory.')).toBeInTheDocument();
    expect(screen.getByText(norm(copy.truthVsMemory))).toBeInTheDocument();
    expect(screen.getByText('No-Guessing.')).toBeInTheDocument();
    expect(screen.getByText(/nothing scientific is invented/i)).toBeInTheDocument();
    // About names the two PLANES; it does not restate Data & Privacy's rulings.
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
    renderSettings();
    openTab('About');
    await screen.findByText('0.1.0');
    expect(screen.getByText('CLAUDE.md')).toBeInTheDocument();
    expect(screen.getByText('AGENTS.md')).toBeInTheDocument();
    // Inert names: no links, and the doc names are not anchors.
    expect(screen.getByText('CLAUDE.md').tagName).toBe('CODE');
    expect(screen.getByText(/not served as pages by this app/i)).toBeInTheDocument();
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderSettings();
    openTab('About');
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

/** Open the Endpoint Explorer tab. It is one click now, not two. */
async function openApiDocs() {
  openTab('Endpoint Explorer');
  return screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 });
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
    openTab('Endpoint Explorer');
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
    openTab('API Access');
    expect(
      await screen.findByText(
        /OpenAPI 3\.1\.0 · ISAAC Metadata Assistant API · v0\.1\.0/,
      ),
    ).toBeInTheDocument();

    openTab('Endpoint Explorer');
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
      detail.closest('.settings-card')?.querySelectorAll('.api-browser-row details'),
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
    openTab('Endpoint Explorer');
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
    name: 'Data & Privacy',
    open: () => openTab('Data & Privacy'),
    settle: () => screen.findByText(/two things are stored/i),
  },
  { name: 'About', open: () => openTab('About'), settle: () => screen.findByText('0.1.0') },
  {
    name: 'API Access',
    open: () => openTab('API Access'),
    settle: () => screen.findByText(API_ACCESS_COPY.emptyTitle),
  },
  {
    name: 'Endpoint Explorer',
    open: () => openTab('Endpoint Explorer'),
    settle: () => screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 }),
  },
  /*
   * Connect Your Agent joined the list rather than being left out of it. The
   * forbidden-substring guard below is the reason: that tab describes an
   * authentication model and an authorization boundary, which is exactly the
   * copy most likely to reach for the name of the identity layer in front of a
   * deployment or for the word for a bearer credential. A new Settings surface
   * that is not in SURFACES is a surface nothing checks.
   */
  {
    name: 'Connect Your Agent',
    open: () => openTab('Connect Your Agent'),
    settle: () =>
      screen.findByRole('heading', { name: 'Requires organization configuration', level: 3 }),
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
    openTab('Endpoint Explorer');
    await screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 });

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
 *  counted this way rather than read off a single render). */
async function textOfEverySurface(): Promise<string[]> {
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
}

/**
 * THE anti-regression guard for the deduplication slice. Six claims used to be
 * authored two or three times across these tabs — two of them character-for-
 * character. Every canonical string is now counted across every surface and must
 * appear exactly once: copying a definition back into Overview or About, or
 * paraphrasing one into a second tab (including either API sub-tab) under a
 * different heading, fails here.
 */
describe('Settings — every canonical string appears exactly once across the tabs', () => {
  const facts = settingsFactsFrom(aboutResponse);
  const concepts = settingsConcepts(facts);
  const about = settingsAboutCopy(facts);

  const canonical: { what: string; text: string }[] = [
    ...concepts.map((c) => ({ what: `${c.heading} — summary`, text: c.summary })),
    ...concepts.map((c) => ({ what: `${c.heading} — definition`, text: c.detail })),
    ...concepts
      .filter((c) => c.more)
      .map((c) => ({ what: `${c.heading} — ${c.more!.label}`, text: c.more!.text })),
    { what: 'About — truth vs. memory', text: about.truthVsMemory },
    { what: 'About — no-guessing', text: about.noGuessing },
    { what: 'About — identity caption', text: about.identityCaption },
    /* P36V-1 slice 13 — the API surfaces joined the guard. Before it, the
       key-unavailable reason was authored in FOUR places (the API-Keys lead, an
       access row, Quick Start's authentication note and Connect an Agent) and
       the browser-session / headless-credential boundary in two of them. */
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

  it('the full commit SHA is rendered exactly once, on About', async () => {
    const perSurface = await textOfEverySurface();
    const counts = perSurface.map((t) => countOccurrences(t, aboutResponse.build_commit));
    // One entry per SURFACES row, in order; the 1 is About's Technical Details.
    expect(counts).toEqual([0, 0, 1, 0, 0, 0]);
  });

  it('Overview renders no definition, and About renders no data/privacy definition', async () => {
    const [overview, , about_] = await textOfEverySurface();
    for (const concept of concepts) {
      expect(overview, `Overview leaked "${concept.heading}"`).not.toContain(norm(concept.detail));
      expect(about_, `About leaked "${concept.heading}"`).not.toContain(norm(concept.detail));
    }
  });

  it('every card/label heading in the content module is Title Case', () => {
    for (const concept of concepts) {
      expect(titleCase(concept.heading)).toBe(concept.heading);
      if (concept.more) expect(titleCase(concept.more.label)).toBe(concept.more.label);
    }
    expect(titleCase(about.truthVsMemoryLabel)).toBe(about.truthVsMemoryLabel);
    expect(titleCase(about.noGuessingLabel)).toBe(about.noGuessingLabel);
  });

  it('the page introduction is the single agreed sentence, under an accurate eyebrow', () => {
    stubFetchRoutes(fullRoutes());
    renderSettings();
    expect(
      screen.getByText(
        "View this build's runtime status, data boundaries, provenance, and API access.",
      ),
    ).toBeInTheDocument();
    // Slice C: the eyebrow no longer promises configuration this page does not
    // offer — the "nothing to configure" claim below is what the page really is.
    expect(screen.getByText('About This Build')).toBeInTheDocument();
    expect(screen.queryByText('Local Configuration')).not.toBeInTheDocument();
    // The "nothing to configure" claim was not deleted — it moved into Overview.
    expect(screen.getByText(/no user-adjustable settings/i)).toBeInTheDocument();
  });

  /** Each API-access claim belongs to ONE tab. Counting only the total would
   *  pass if a string moved to the wrong surface, so the surface is pinned too. */
  it('the API-access copy renders on the API tabs and nowhere else', async () => {
    const [overview, privacy, about_, apiAccess, explorer, connectAgent] =
      await textOfEverySurface();
    const onApiAccess = [
      API_ACCESS_COPY.statusHeading,
      API_ACCESS_COPY.statusBody,
      API_ACCESS_COPY.createDisabledReason,
      API_ACCESS_COPY.requirementsNote,
      API_ACCESS_COPY.emptyTitle,
      API_ACCESS_COPY.emptyBody,
      ...API_ACCESS_ROWS.map((r) => r.detail),
      ...API_KEY_REQUIREMENTS,
    ];
    for (const text of onApiAccess) {
      expect(apiAccess, `API Access must own: ${text.slice(0, 48)}`).toContain(norm(text));
      for (const [name, other] of [
        ['Overview', overview],
        ['Data & Privacy', privacy],
        ['About', about_],
        ['Endpoint Explorer', explorer],
        ['Connect Your Agent', connectAgent],
      ] as const) {
        expect(other, `${name} leaked: ${text.slice(0, 48)}`).not.toContain(norm(text));
      }
    }
    // The Auth legend is the mirror case: Explorer's alone.
    expect(explorer).toContain(norm(API_ACCESS_COPY.authMarkerLegend));
    expect(apiAccess).not.toContain(norm(API_ACCESS_COPY.authMarkerLegend));
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

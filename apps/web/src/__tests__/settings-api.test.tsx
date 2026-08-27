import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { SettingsPage } from '../screens/SettingsPage';
import {
  PURPOSE_DISCLOSURE_MIN_CHARS,
  isBoundaryCaveat,
  splitPurpose,
} from '../screens/settings/ApiDocs';
import { flattenOpenApi, quickStartFacts } from '../lib/apiDocsModel';
import { API_ACCESS_COPY, API_ACCESS_ROWS, API_KEY_REQUIREMENTS } from '../lib/settingsContent';
import { ROUTES } from '../lib/routes';
import type { ApiOpenApiResponse } from '../lib/types';
import {
  REAL_CONTRACT_DESCRIPTIONS,
  stubFetchRoutes,
  aboutResponse,
  openApiFixture,
} from '../test/apiFixtures';

/**
 * Settings → API Access and Settings → Endpoint Explorer: the honest
 * key-unavailable state and its two-column layout, Quick Start, the endpoint
 * browser's detail pane, the generated code examples, and Connect an Agent.
 *
 * P36V PR3 slice C built these as two SUB-tabs of a single `API` page tab.
 * P36V-1 slices 11–13 changed three things, and this file asserts the new
 * contract rather than the old one:
 *
 *   · slice 12 — the browser is its own top-level, deep-linkable tab, and the
 *     nested `keys | docs` tablist is DELETED. Nothing here clicks a sub-tab;
 *     each surface is opened by its `?tab=` deep link, which is also how a
 *     reader reaches it. `settings-page.test.tsx` owns the routing contract
 *     itself (fallbacks, Back/Forward, refresh, no second tablist).
 *   · slice 11 — API Access is a full-width status banner, a two-column
 *     access/create grid and a full-width key list. jsdom performs no layout, so
 *     the STRUCTURE is asserted here on the DOM and the DECLARATIONS are
 *     asserted against the stylesheet source, the same split
 *     `layout-width-modes.test.tsx` uses. Neither is a claim about pixels.
 *   · slice 13 — every claim has one home. The strings live in
 *     `lib/settingsContent.ts` and `settings-page.test.tsx` counts each one
 *     across all five tabs; this file asserts they render in the right PLACE and
 *     that the retired duplicates are gone for good.
 *
 * The two hardest things this file pins down are truthfulness claims that no
 * amount of rendering correctness would catch on its own:
 *
 *  1. API KEYS ARE UNAVAILABLE, and the screen says so. `apps/api/isaac_api/
 *     auth.py` is one process-wide shared credential read from the environment;
 *     grepping `apps/api` finds no operation that creates, lists, revokes or
 *     rotates one, and the generated contract the Explorer renders lists every
 *     operation the API has. So there is nothing to manage — and this suite
 *     fails if a key is ever generated, masked, stored, or implied.
 *  2. GROUPING COMES FROM THE DOCUMENT'S REAL TAGS. The predecessor inferred a
 *     group from the path segment after `/api/` while asserting in a docstring
 *     that the backend assigned no tags. It now does. The group names and their
 *     ORDER asserted below are obtainable only from the document's `tags` array,
 *     so a revert to segment inference fails here.
 *
 * The forbidden-infrastructure-substring guard for both tabs lives in
 * `settings-page.test.tsx`, alongside the same guard for the other three tabs.
 */

const ABOUT_URL = 'GET /api/about';
const OPENAPI_URL = 'GET /api/openapi';

const fixture = openApiFixture as unknown as ApiOpenApiResponse;
const ROWS = flattenOpenApi(fixture);
const FACTS = quickStartFacts(fixture, ROWS);

/* Stylesheet source. `vite.config.ts` sets `test.css: true`, so the sheet IS
   attached in jsdom and `getComputedStyle` on a RENDERED element is the stronger
   instrument — that is what the layout assertions below use, because a substring
   in a file proves only that a declaration was written, never that it reaches the
   element. (The two-column fix shipped with `max-width: 74ch` still resolving on
   the left column's `dd`s: source assertions passed while the surface was wrong.)

   Source reading is kept for the ONE thing jsdom cannot do — it never evaluates
   `@media`, so a responsive rule is invisible to `getComputedStyle` at any window
   size. Comments are stripped so a guard cannot be satisfied by prose.

   TWO jsdom limits worth stating, because they bound what the computed assertions
   below can mean:
     · jsdom resolves the cascade by SOURCE ORDER and ignores specificity, so a
       later low-specificity rule beats an earlier high-specificity one here but
       not in a browser. `screens.css` therefore keeps
       `.api-access-banner .api-keys-lead` after `.api-keys-lead`, so the two
       agree.
     · jsdom performs no layout: `ch`/`fr` are returned as authored, never
       resolved to pixels. Nothing here is a claim about pixels. */
const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;
const screensCss = (
  Object.entries(cssFiles).find(([path]) => path.endsWith('/screens.css'))?.[1] ?? ''
).replace(/\/\*[\s\S]*?\*\//g, '');

/* At-rule bodies removed, so `cssRule` can never silently read a
   `@media (max-width: …)` override as if it were the base rule. */
const screensCssTopLevel = screensCss.replace(
  /@[a-zA-Z-]+[^{]*\{(?:[^{}]*\{[^{}]*\})*\s*\}/g,
  '',
);

/**
 * Every top-level declaration block whose selector list CONTAINS `selector`,
 * concatenated. Comma-split and whitespace-normalised on both sides, so a grouped
 * selector or a Prettier reflow cannot break the match, and all matches are
 * returned rather than only the first — the predecessor read `.foo` from the first
 * block it found and was keyed to exact newline placement inside the selector.
 */
function cssRule(selector: string): string {
  const want = selector.replace(/\s+/g, ' ').trim();
  return [...screensCssTopLevel.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter((m) => m[1].split(',').some((s) => s.replace(/\s+/g, ' ').trim() === want))
    .map((m) => m[2].replace(/\s+/g, ' ').trim())
    .join(' ');
}

/** Computed style of the FIRST rendered match — the real cascade result in jsdom. */
function computed(selector: string): CSSStyleDeclaration {
  const el = document.querySelector(selector);
  if (!el) throw new Error(`no rendered element for ${selector}`);
  return getComputedStyle(el);
}

function routes() {
  return { [ABOUT_URL]: { body: aboutResponse }, [OPENAPI_URL]: { body: openApiFixture } };
}

function renderSettings(entry: string) {
  return render(
    <MemoryRouter
      initialEntries={[entry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <SettingsPage />
    </MemoryRouter>,
  );
}

/** Open Settings on the API Access tab, by the deep link a reader would follow. */
async function openApiAccess(extraRoutes: Record<string, unknown> = {}) {
  stubFetchRoutes({ ...routes(), ...extraRoutes } as Parameters<typeof stubFetchRoutes>[0]);
  const view = renderSettings(ROUTES.settingsTab('api'));
  await screen.findByRole('heading', { name: 'Quick Start' });
  return view;
}

/** Open Settings on the Endpoint Explorer tab. */
async function openExplorer(extraRoutes: Record<string, unknown> = {}) {
  stubFetchRoutes({ ...routes(), ...extraRoutes } as Parameters<typeof stubFetchRoutes>[0]);
  const view = renderSettings(ROUTES.settingsTab('explorer'));
  await screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 });
  return view;
}

const apiAccessPanel = () => document.getElementById('settings-tabpanel-api') as HTMLElement;
const explorerPanel = () => document.getElementById('settings-tabpanel-explorer') as HTMLElement;
/** The key/access half of the API Access tab — the surface that must never show
 *  key material. Quick Start's generated samples are deliberately outside it. */
const keysRegion = () => document.querySelector('.api-access') as HTMLElement;
const detailPane = () => document.getElementById('settings-api-detail') as HTMLElement;

const groupHeadings = () =>
  Array.from(document.querySelectorAll('.api-browser-group-heading')).map((h) =>
    (h.firstChild?.textContent ?? '').trim(),
  );

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

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// --- the two API tabs ---------------------------------------------------------

describe('Settings → the two API tabs', () => {
  /**
   * Replaces "adds exactly two sub-tabs inside the API tab". The sub-tabs are
   * gone; what has to stay true is that the endpoint browser and the key/access
   * surface are on DIFFERENT tabs and neither leaks into the other. That is a
   * stronger statement than the two labels the old assertion listed.
   */
  it('separates the key/access surface from the endpoint browser', async () => {
    const view = await openApiAccess();
    expect(keysRegion()).toBeInTheDocument();
    expect(within(apiAccessPanel()).getByRole('heading', { name: 'Quick Start' })).toBeInTheDocument();
    // The browser is NOT here: no endpoint list, no detail pane, no search box.
    expect(apiAccessPanel().querySelector('.api-browser-list')).toBeNull();
    expect(apiAccessPanel().querySelector('#settings-api-detail')).toBeNull();
    expect(within(apiAccessPanel()).queryByLabelText('Search endpoints')).toBeNull();
    view.unmount();

    const explorer = await openExplorer();
    expect(explorerPanel().querySelector('.api-browser-list')).not.toBeNull();
    // ...and the key/access surface and Quick Start are NOT on the browser tab.
    expect(explorerPanel().querySelector('.api-access')).toBeNull();
    expect(within(explorerPanel()).queryByRole('heading', { name: 'Quick Start' })).toBeNull();
    expect(
      within(explorerPanel()).queryByRole('button', { name: /Create API Key/i }),
    ).toBeNull();
    explorer.unmount();
  });

  it('the key sections need no data, so they render while the contract is still loading', () => {
    stubFetchRoutes(routes());
    renderSettings(ROUTES.settingsTab('api'));
    // Synchronously, before any fetch resolves:
    expect(screen.getByText(API_ACCESS_COPY.emptyTitle)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create API Key/i })).toBeDisabled();
    // ...and the contract-derived half honestly says it is still loading.
    expect(screen.getByText('Loading the API contract…')).toBeInTheDocument();
  });

  it('the endpoint browser waits for the contract rather than rendering an empty list', () => {
    stubFetchRoutes(routes());
    renderSettings(ROUTES.settingsTab('explorer'));
    expect(screen.getByText('Loading the API contract…')).toBeInTheDocument();
    expect(document.querySelector('.api-browser-list')).toBeNull();
    expect(screen.queryByText(/0 of 0 endpoints/)).toBeNull();
  });
});

// --- API Access: the honest unavailable state ---------------------------------

describe('Settings → API Access — an honest unavailable state', () => {
  it('renders all four regions, visually complete rather than broken', async () => {
    await openApiAccess();
    // The key/access surface, in reading order. "What Would Be Required" is no
    // longer a fourth always-visible section — slice 11 moved it into a
    // collapsed disclosure, asserted separately below.
    expect(Array.from(keysRegion().querySelectorAll('h3')).map((h) => h.textContent)).toEqual([
      API_ACCESS_COPY.statusHeading,
      'How Access Works Today',
      'Create API Key',
      'Your API Keys',
    ]);
    // The whole tab is those four plus the two contract-derived sections.
    expect(Array.from(apiAccessPanel().querySelectorAll('h3')).map((h) => h.textContent)).toEqual([
      API_ACCESS_COPY.statusHeading,
      'How Access Works Today',
      'Create API Key',
      'Your API Keys',
      'Quick Start',
      'Connect an Agent',
    ]);
    // Not an error state and not a fake loading failure: no alert anywhere on
    // the tab, and the key/access surface never claims something went wrong or
    // invites a retry. (The copy DOES say "nothing failed to load" — that is the
    // opposite claim, so the negatives below are phrased to catch a real failure
    // claim, not that reassurance. The scope is the key surface, exactly as
    // before: Connect an Agent legitimately discusses retrying a refused call.)
    expect(within(apiAccessPanel()).queryByRole('alert')).not.toBeInTheDocument();
    expect(keysRegion().textContent).not.toMatch(
      /something went wrong|could not load|try again|retry|temporarily unavailable/i,
    );
  });

  /**
   * The status is stated ONCE, at the top, and it is the region every other
   * section defers to. The old surface said it in four places (this lead, an
   * access row, Quick Start's authentication note, and Connect an Agent) — the
   * count assertions here are what stop that from coming back on this tab, and
   * `settings-page.test.tsx` counts it across all five.
   */
  it('states the unavailability once, in a full-width banner at the top', async () => {
    await openApiAccess();
    const banner = keysRegion().querySelector('.api-access-banner') as HTMLElement;
    expect(banner).not.toBeNull();
    // First child of the surface: nothing precedes the status.
    expect(keysRegion().firstElementChild).toBe(banner);
    // Its heading is in the OUTLINE (an h3), not an accessible name on the
    // section: this surface had five nested `region` landmarks on one tab, which
    // makes a landmark list useless for navigation. The heading is how a
    // screen-reader user finds the status within the panel.
    expect(within(banner).getByRole('heading', { level: 3 }).textContent).toBe(
      API_ACCESS_COPY.statusHeading,
    );
    expect(banner).not.toHaveAttribute('aria-labelledby');
    expect(within(banner).getByText(API_ACCESS_COPY.statusBody)).toBeInTheDocument();

    const text = norm(apiAccessPanel().textContent ?? '');
    expect(countOccurrences(text, norm(API_ACCESS_COPY.statusBody))).toBe(1);
    // The retired restatements are gone from the whole tab, not just moved.
    expect(text).not.toMatch(/Unavailable\. This API has no operation that creates/i);
    expect(text).not.toMatch(/No key can be issued from this app/i);
    expect(text).not.toMatch(/API keys are unavailable here/i);
    expect(text).not.toMatch(/see API Keys/i);
  });

  it('answers the capability questions once each, classifying key management as unavailable', async () => {
    await openApiAccess();
    expect(
      Array.from(keysRegion().querySelectorAll('.api-keys-row dt')).map((dt) => dt.textContent),
    ).toEqual([
      'Current Access Model',
      'What an API Key Would Enable',
      'External Agent Access',
      // Added when the client-side bearer seam was removed. Every row above says
      // what the DEPLOYMENT may require; none said what this page actually
      // sends, and the answer — nothing — is a decision worth stating rather
      // than an absence a reader has to infer.
      'What This Interface Sends',
      'Hosted Authentication Boundary',
    ]);
    const text = norm(apiAccessPanel().textContent ?? '');
    for (const row of API_ACCESS_ROWS) {
      expect(within(keysRegion()).getByText(row.detail)).toBeInTheDocument();
      expect(countOccurrences(text, norm(row.detail)), `${row.term} duplicated`).toBe(1);
    }
    // The four specific claims the authorizing brief requires answered.
    expect(
      within(keysRegion()).getByText(/One credential belonging to the whole deployment/i),
    ).toBeInTheDocument();
    expect(
      within(keysRegion()).getByText(/Not through anything you can obtain here/i),
    ).toBeInTheDocument();
    // The hosted-session boundary moved HERE from Connect an Agent, in full.
    expect(
      within(keysRegion()).getByText(
        /Signing in through a deployment's identity layer with a browser is not the same thing as headless authentication/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(keysRegion()).getByText(
        /an interactive session, not a credential a program can present on its own/i,
      ),
    ).toBeInTheDocument();
    // It never claims keys are available.
    expect(text).not.toMatch(/your key is|key created|copy your key/i);
    // Provider-neutral wherever that boundary is stated: no vendor, no protocol.
    const lower = (apiAccessPanel().textContent ?? '').toLowerCase();
    for (const needle of ['authentik', 'ingress', 'k8s', 'kubernetes', 'vercel', 'railway', 'oauth', 'saml', 'sso']) {
      expect(lower.includes(needle), `named provider or protocol: ${needle}`).toBe(false);
    }
  });

  it('the Create control is really disabled and announces WHY', async () => {
    await openApiAccess();
    const create = screen.getByRole('button', { name: /Create API Key/i });
    expect(create).toBeDisabled();

    const describedBy = create.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    const reason = document.getElementById(describedBy as string) as HTMLElement;
    expect(reason).not.toBeNull();
    expect(reason.textContent).toBe(API_ACCESS_COPY.createDisabledReason);
    // `disabled` is never the only signal: the reason is always visible too, and
    // the full explanation it defers to is the banner, on the same screen.
    expect(reason.closest('details')).toBeNull();
    expect(reason.textContent).toMatch(/there is no operation for this button to call/i);
    expect(within(keysRegion()).getByText(API_ACCESS_COPY.statusBody)).toBeInTheDocument();
  });

  /**
   * Slice 11 — "What Would Be Required" was a five-item always-visible list; it
   * is now a collapsed disclosure. Nothing was deleted: every requirement is
   * still asserted, and the disclosure must really contain them.
   */
  it('keeps the backend/security requirements collapsed, and loses none of them', async () => {
    await openApiAccess();
    const drawer = keysRegion().querySelector('details.api-keys-technical') as HTMLDetailsElement;
    expect(drawer).not.toBeNull();
    expect(drawer.open).toBe(false);
    expect(drawer.querySelector('summary')?.textContent).toBe('Technical Requirements');
    // The old always-visible heading is gone as a heading.
    expect(
      within(apiAccessPanel()).queryByRole('heading', { name: 'What Would Be Required' }),
    ).toBeNull();

    const items = Array.from(drawer.querySelectorAll('.api-keys-requirements li')).map(
      (li) => li.textContent ?? '',
    );
    expect(items).toEqual([...API_KEY_REQUIREMENTS]);
    expect(items).toHaveLength(5);
    expect(items.join(' ')).toMatch(/holding a hash rather than the value/i);
    expect(items.join(' ')).toMatch(/Per-key identity/i);
    expect(items.join(' ')).toMatch(/Revocation and expiry/i);
    expect(items.join(' ')).toMatch(/Scopes/i);
    expect(
      within(drawer).getByText(/belong to a later, separately authorized phase/i),
    ).toBeInTheDocument();

    fireEvent.click(drawer.querySelector('summary') as HTMLElement);
    expect(drawer.open).toBe(true);
  });

  it('generates no key, masks no key, and offers nothing to reveal or copy', async () => {
    await openApiAccess();
    const text = keysRegion().textContent ?? '';

    // No key-shaped string anywhere (no 24+ run of credential characters).
    expect(text).not.toMatch(/[A-Za-z0-9_-]{24,}/);
    // No masked placeholder standing in for a real value.
    expect(text).not.toMatch(/[•*·]{4,}/);
    expect(text).not.toMatch(/sk-|\bBearer\s+\S/);
    // Nothing to reveal, regenerate, or copy — those controls do not exist.
    expect(keysRegion().querySelectorAll('input')).toHaveLength(0);
    expect(keysRegion().querySelectorAll('pre')).toHaveLength(0);
    expect(
      within(keysRegion()).queryByRole('button', { name: /copy|reveal|show|regenerate|rotate|revoke/i }),
    ).not.toBeInTheDocument();
    // The only controls on this surface are the disabled one and the nav link.
    expect(within(keysRegion()).getAllByRole('button').map((b) => b.textContent?.trim())).toEqual([
      'Endpoint Explorer',
      'Create API Key',
    ]);

    // Across the WHOLE tab — Quick Start's generated samples included — the only
    // credential token displayed is the ENVIRONMENT VARIABLE NAME the sample
    // reads from, never a value and never a mask.
    const all = apiAccessPanel().textContent ?? '';
    expect(all).not.toMatch(/[•*·]{4,}/);
    expect(all).not.toMatch(/sk-/);
    expect(all).toContain('$ISAAC_API_CREDENTIAL');
  });

  it('writes nothing to browser storage or cookies', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    const removeItem = vi.spyOn(Storage.prototype, 'removeItem');
    const cookieBefore = document.cookie;

    await openApiAccess();
    // ...and after interacting with everything interactive on the surface.
    fireEvent.click(screen.getByRole('button', { name: /Create API Key/i }));
    fireEvent.click(
      keysRegion().querySelector('details.api-keys-technical summary') as HTMLElement,
    );

    expect(setItem).not.toHaveBeenCalled();
    expect(removeItem).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(document.cookie).toBe(cookieBefore);
  });

  it('shows a polished empty state that says the list is empty BY DESIGN', async () => {
    await openApiAccess();
    const list = keysRegion().querySelector('.api-access-full') as HTMLElement;
    expect(within(list).getByRole('heading', { name: 'Your API Keys' })).toBeInTheDocument();
    expect(within(list).getByText(API_ACCESS_COPY.emptyTitle)).toBeInTheDocument();
    expect(
      within(list).getByText(/empty by design, not by circumstance — nothing failed to load/i),
    ).toBeInTheDocument();
    // The claim the retired second paragraph made — that there is nowhere a key
    // could be created or kept — is still made, once, by the status banner.
    expect(
      within(keysRegion()).getByText(
        /there is never a key here to reveal, copy, or store/i,
      ),
    ).toBeInTheDocument();
    // An empty state, not a table with zero rows.
    expect(list.querySelector('table')).toBeNull();
  });

  it('links into the Endpoint Explorer tab from the status banner', async () => {
    await openApiAccess();
    const banner = keysRegion().querySelector('.api-access-banner') as HTMLElement;
    fireEvent.click(within(banner).getByRole('button', { name: 'Endpoint Explorer' }));
    expect(screen.getByRole('tab', { name: 'Endpoint Explorer' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(
      await screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 }),
    ).toBeInTheDocument();
  });
});

// --- API Access: the layout the wide measure is spent on ----------------------

/**
 * Slice 11, plan §2.7: `width="wide"` publishes `--content-max: 1200px`, but
 * every text block was capped at 62–74ch with no cap on its own box, so roughly
 * half the card was empty. jsdom does no layout, so this suite asserts the two
 * halves of the fix that CAN be asserted deterministically — the DOM structure
 * React renders, and the declarations in the stylesheet — and claims nothing
 * about measured pixels.
 */
describe('Settings → API Access — layout', () => {
  it('renders the banner / two-column grid / full-width list structure', async () => {
    await openApiAccess();
    const surface = keysRegion();
    expect(Array.from(surface.children).map((el) => el.className.split(' ')[0])).toEqual([
      'api-access-banner',
      'api-access-grid',
      'api-access-full',
    ]);

    // The grid holds exactly the two columns, in the required order.
    const grid = surface.querySelector('.api-access-grid') as HTMLElement;
    const columns = Array.from(grid.querySelectorAll(':scope > .api-access-col'));
    expect(columns).toHaveLength(2);
    expect(columns[0].querySelector('h3')?.textContent).toBe('How Access Works Today');
    expect(columns[1].querySelector('h3')?.textContent).toBe('Create API Key');
    // Left column: the metadata rows. Right column: the control and the
    // collapsed requirements — and NO field, because none could work.
    expect(columns[0].querySelectorAll('.api-keys-row')).toHaveLength(API_ACCESS_ROWS.length);
    expect(columns[1].querySelector('.api-keys-create-btn')).not.toBeNull();
    expect(columns[1].querySelector('details.api-keys-technical')).not.toBeNull();
    expect(columns[1].querySelectorAll('input, select, textarea')).toHaveLength(0);
    // The banner's trailing edge carries the action, so the full measure holds
    // content rather than whitespace.
    expect(
      surface.querySelector('.api-access-banner .api-access-banner-action button'),
    ).not.toBeNull();
  });

  /**
   * Asserted on the RENDERED elements, not on the stylesheet text. The previous
   * version of this test read `screens.css` as a string and passed while
   * `.api-keys-row > dd { max-width: 74ch }` was still resolving on the left
   * column — roughly a fifth of the widest column blank, the same defect the grid
   * was introduced to remove, surviving one level in. A substring in a file cannot
   * detect that; the cascade result can.
   */
  it('caps each box, not only the text inside it, and every cap reaches the element', async () => {
    await openApiAccess();

    // Two columns at the wide measure, each free to shrink to 0 so a long token
    // cannot push the grid wider than the page.
    const grid = computed('.api-access-grid');
    expect(grid.display).toBe('grid');
    expect(grid.gridTemplateColumns).toBe('minmax(0, 1.4fr) minmax(0, 1fr)');
    expect(computed('.api-access-col').minWidth).toMatch(/^0(px)?$/);
    expect(computed('.api-access-full').minWidth).toMatch(/^0(px)?$/);

    // The banner's prose box carries its own cap; the action is pushed away from
    // it; and the lead inside it is NOT re-capped at the narrower row measure, so
    // no gap opens between the last word and the action.
    expect(computed('.api-access-banner-body').maxWidth).toBe('90ch');
    expect(computed('.api-access-banner-action').marginLeft).toBe('auto');
    expect(computed('.api-access-banner .api-keys-lead').maxWidth).toBe('none');

    // The access rows: the COLUMN is the measure now. 74ch (~490–535px at 12px)
    // inside a ~660px track left a fifth of it permanently blank; 92ch fills the
    // track and still bounds the line if `--content-max` grows.
    expect(computed('.api-keys-row > dd').maxWidth).toBe('92ch');

    // The empty state is a left-aligned row, not a narrow centred island inside a
    // full-measure dashed box (`max-width: 62ch` + `margin: … auto`, ~740px blank).
    const empty = computed('.api-keys-empty');
    expect(empty.display).toBe('flex');
    expect(empty.textAlign).toBe('left');
    const emptyBody = computed('.api-keys-empty-body');
    expect(emptyBody.marginLeft).toBe('0px');
    expect(emptyBody.maxWidth).toBe('100ch');
  });

  /** The `.settings-provenance-note` precedent this surface follows still exists
   *  and is unchanged. It lives on the About tab, so it is read from the sheet
   *  rather than rendered here — this test is about the API Access tab. */
  it('still follows the .settings-provenance-note box-cap precedent', () => {
    expect(cssRule('.settings-provenance-note')).toMatch(/max-width: 80ch/);
  });

  /**
   * SOURCE-based on purpose, and the one place in this file that has to be: jsdom
   * never evaluates `@media`, so a responsive declaration is invisible to
   * `getComputedStyle` at any window size — there is no rendered value to read.
   * The at-rule bodies are parsed out explicitly here rather than reached through
   * `cssRule`, which deliberately cannot see inside an at-rule.
   */
  it('collapses to ONE column at tablet width, and the control goes full width below that', () => {
    const rules = [...screensCss.matchAll(/@media([^{]+)\{((?:[^{}]*\{[^{}]*\})*)\s*\}/g)].map(
      (m) => ({ query: m[1].replace(/\s+/g, ' ').trim(), body: m[2].replace(/\s+/g, ' ') }),
    );
    const tablet = rules.find((r) => r.query === '(max-width: 900px)');
    expect(tablet, 'no (max-width: 900px) block').toBeDefined();
    expect(tablet!.body).toMatch(
      /\.api-access-grid\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\)/,
    );
    // The banner action stops being pushed to a trailing edge that no longer exists.
    expect(tablet!.body).toMatch(/\.api-access-banner-action\s*\{[^}]*margin-left: 0/);

    const narrow = rules.find((r) => r.query === '(max-width: 720px)');
    expect(narrow, 'no (max-width: 720px) block').toBeDefined();
    expect(narrow!.body).toMatch(/\.api-keys-create-btn\s*\{[^}]*width: 100%/);

    // Nothing on this surface can scroll the page sideways: it renders no table
    // and no code block, and the two containers that could overflow may shrink.
    expect(screensCss).not.toMatch(/\.api-access[^{]*\{[^}]*overflow-x: scroll/);
  });

  /** Dead CSS is how a retired layer gets rebuilt by accident, so the rules for
   *  the flat API-Keys stack and for the deleted `keys | docs` sub-tablist are
   *  asserted gone — not merely unused. */
  it('the retired flat-section and sub-tablist CSS is gone, not just unreferenced', () => {
    for (const dead of [
      '.api-keys-section',
      '.api-keys-jump',
      '.api-subtabs',
      '.api-subtabs-tab',
      '.api-subpanel',
    ]) {
      expect(screensCss, `dead rule still present: ${dead}`).not.toContain(dead);
    }
  });
});

// --- Quick Start --------------------------------------------------------------

describe('Settings → API Access — Quick Start', () => {
  it('reports the base URL as a RELATIVE path, never an origin', async () => {
    await openApiAccess();
    const rows = Array.from(document.querySelectorAll('.api-quickstart-row'));
    const baseRow = rows.find((r) => r.querySelector('dt')?.textContent === 'Base URL') as HTMLElement;
    expect(baseRow).toBeTruthy();
    expect(within(baseRow).getByText('/api')).toBeInTheDocument();
    expect(FACTS.basePath).toBe('/api');
    expect(baseRow.textContent).toMatch(/Relative to the origin serving this page/i);
    // No scheme or host literal anywhere on the whole tab.
    expect(apiAccessPanel().textContent ?? '').not.toMatch(/https?:\/\//);
  });

  it('reports only values the running app can actually report', async () => {
    await openApiAccess();
    const rows = Array.from(document.querySelectorAll('.api-quickstart-row')).map((r) => ({
      label: r.querySelector('dt')?.textContent,
      text: r.textContent ?? '',
    }));
    expect(rows.map((r) => r.label)).toEqual([
      'Base URL',
      'API Version',
      'Authentication',
      'Content Type',
    ]);
    expect(rows[1].text).toContain(`v${FACTS.apiVersion}`);
    expect(rows[1].text).toContain(FACTS.openApiVersion);
    expect(rows[2].text).toContain('Authorization: Bearer');
    expect(rows[2].text).toContain(
      `${FACTS.authRequiredCount} of ${FACTS.operationCount} operations document a 401`,
    );
    expect(rows[3].text).toContain('application/json');
    // Provenance: the contract's own identity line, verbatim.
    expect(screen.getByText(FACTS.contractLine)).toBeInTheDocument();
  });

  /**
   * Slice 13 — the 401 count is Quick Start's, and Quick Start's only. Connect an
   * Agent used to state it a second time on this same tab from the same facts
   * object, which is why `ConnectAnAgentFacts` no longer carries the two count
   * fields at all. This is the guard that keeps it from returning; the previous
   * version asserted the sentence inside Connect an Agent, which locked the
   * duplication in.
   */
  it('states the 401 count exactly once on the tab, and points at the Explorer for which', async () => {
    await openApiAccess();
    const claim = `${FACTS.authRequiredCount} of ${FACTS.operationCount} operations document a 401`;
    const text = norm(apiAccessPanel().textContent ?? '');
    expect(countOccurrences(text, claim)).toBe(1);
    expect(text).toMatch(/the Endpoint Explorer tab marks which/i);
    // The stale positional phrasing is gone from both modules.
    expect(text).not.toMatch(/Endpoint Explorer above/i);
    expect(text).not.toMatch(/Explorer marks which/i);
  });

  it('proposes a first request the reader can actually make, and says why that one', async () => {
    await openApiAccess();
    const first = document.querySelector('.api-quickstart-first') as HTMLElement;
    expect(first).toBeTruthy();
    expect(within(first).getByText('/api/health')).toBeInTheDocument();
    expect(within(first).getByText('GET')).toBeInTheDocument();
    expect(first.querySelector('pre')?.textContent).toBe('curl "$ISAAC_BASE_URL/api/health"');
    expect(first.textContent).toMatch(/contract documents no 401 for it/i);
    expect(first.textContent).toMatch(/stands for the origin serving this page/i);
  });

  it('the first-request sample is copyable, with an accessible name and a spoken confirmation', async () => {
    await openApiAccess();
    const first = document.querySelector('.api-quickstart-first') as HTMLElement;
    const copy = within(first).getByRole('button', { name: 'Copy the first-request sample' });
    fireEvent.click(copy);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      'curl "$ISAAC_BASE_URL/api/health"',
    );
    // Non-visual signal: a polite status region, not colour or an icon alone.
    const status = document.querySelector('[role="status"]') as HTMLElement;
    expect(status.textContent).toBe('Copied the first-request sample.');
    // Visual signal too.
    expect(within(first).getByRole('button', { name: 'Copied the first-request sample' })).toBeInTheDocument();
  });

  /**
   * Replaces "links to API Keys and opens Connect an Agent". An "API Keys" jump
   * would now be a link to the page you are already on — that content is the
   * status banner at the top of this tab — so the nav's first entry goes to the
   * Endpoint Explorer TAB instead, and both destinations are asserted to
   * actually arrive rather than only to be clickable.
   */
  it('offers the two places to go next, and both work', async () => {
    await openApiAccess();
    const nav = screen.getByRole('navigation', { name: 'More API detail' });
    expect(within(nav).getAllByRole('button').map((b) => b.textContent?.trim())).toEqual([
      'Browse Every Endpoint',
      'Connect an Agent',
    ]);
    // No stale link to a surface that is no longer a destination.
    expect(within(nav).queryByRole('button', { name: 'API Keys' })).toBeNull();

    const connect = document.querySelector('details.api-connect') as HTMLDetailsElement;
    expect(connect.open).toBe(false);
    fireEvent.click(within(nav).getByRole('button', { name: 'Connect an Agent' }));
    expect((document.querySelector('details.api-connect') as HTMLDetailsElement).open).toBe(true);

    fireEvent.click(within(nav).getByRole('button', { name: 'Browse Every Endpoint' }));
    expect(screen.getByRole('tab', { name: 'Endpoint Explorer' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(
      await screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 }),
    ).toBeInTheDocument();
  });
});

// --- Endpoint Explorer: tag grouping + detail ---------------------------------

describe('Settings → Endpoint Explorer', () => {
  it('groups by the document’s REAL tags, in the document’s registration order', async () => {
    await openExplorer();
    expect(groupHeadings()).toEqual([
      'Health & Meta',
      'Experiments',
      'Drafts & Answers',
      'Uploads',
      'Validation',
      'Other Operations',
    ]);
    // A registered tag carried by no operation creates no group.
    expect(groupHeadings()).not.toContain('Schema & Vocabulary');
    // The stale path-segment groups appear nowhere.
    for (const stale of ['health', 'about', 'experiments', 'answers', 'uploads', 'validate']) {
      expect(groupHeadings()).not.toContain(stale);
    }
    // Registration order is not alphabetical, so this can only come from `tags`.
    expect([...groupHeadings()].sort()).not.toEqual(groupHeadings());
  });

  it('counts every operation and reports the number of groups', async () => {
    await openExplorer();
    expect(screen.getByText(`${ROWS.length} of ${ROWS.length} endpoints`)).toBeInTheDocument();
    expect(screen.getByText('6 groups')).toBeInTheDocument();
  });

  it('search matches path, summary, group and method', async () => {
    await openExplorer();
    const search = screen.getByLabelText('Search endpoints') as HTMLInputElement;

    fireEvent.change(search, { target: { value: 'drafts' } });
    expect(await screen.findByText(`1 of ${ROWS.length} endpoints`)).toBeInTheDocument();
    expect(groupHeadings()).toEqual(['Drafts & Answers']);

    fireEvent.change(search, { target: { value: 'liveness' } });
    expect(await screen.findByText(`1 of ${ROWS.length} endpoints`)).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'nothing-here-xyz' } });
    expect(await screen.findByText(/no endpoints match/i)).toBeInTheDocument();
    expect(screen.getByText(`0 of ${ROWS.length} endpoints`)).toBeInTheDocument();
  });

  it('names the selected operation’s group and renders that tag’s registered description', async () => {
    await openExplorer();
    // Default selection is the first row: GET /api/about, in Health & Meta.
    expect(within(detailPane()).getByText('Health & Meta')).toBeInTheDocument();
    expect(
      within(detailPane()).getByText(/Liveness, deployment identity, and this API/i),
    ).toBeInTheDocument();

    // A registered tag with NO description renders the chip and invents nothing.
    fireEvent.click(screen.getByText('/api/experiments/{id}'));
    expect(within(detailPane()).getByText('Experiments')).toBeInTheDocument();
    expect(detailPane().querySelector('.api-browser-detail-groupdesc')).toBeNull();
  });

  it('renders Purpose, compact metadata, parameters and both response groups', async () => {
    await openExplorer();
    fireEvent.click(screen.getByText('/api/experiments/{id}'));
    const detail = detailPane();

    // Slice 13 — `Authentication` is no longer a per-endpoint SECTION; the flag
    // is compact metadata and its meaning is stated once for the tab.
    expect(Array.from(detail.querySelectorAll('h5')).map((h) => h.textContent)).toEqual([
      'Purpose',
      'Parameters',
      'Request Body',
      'Responses',
      'Error States',
    ]);
    expect(within(detail).getByText(/fetch one experiment detail by id/i)).toBeInTheDocument();

    // Parameters still carry the contract's own descriptions.
    const paramHeaders = Array.from(detail.querySelectorAll('th')).map((th) => th.textContent);
    expect(paramHeaders).toEqual(['Name', 'In', 'Required', 'Description']);
    expect(within(detail).getByText('The id of an experiment.')).toBeInTheDocument();

    // 200 under Responses; 401/404 under Error States — never mixed.
    const sections = Array.from(detail.querySelectorAll('.api-browser-section'));
    const responses = sections.find((s) => s.querySelector('h5')?.textContent === 'Responses');
    const errors = sections.find((s) => s.querySelector('h5')?.textContent === 'Error States');
    expect(Array.from(responses!.querySelectorAll('.api-browser-status')).map((s) => s.textContent)).toEqual(['200']);
    expect(Array.from(errors!.querySelectorAll('.api-browser-status')).map((s) => s.textContent)).toEqual(['401', '404']);
  });

  /**
   * Replaces the two per-endpoint authentication paragraphs. Those asserted the
   * WORDING of a warning that was re-rendered on every one of the seven
   * endpoints; this asserts the same distinction (401 documented vs. not) as a
   * per-operation flag AND that the explanation is stated exactly once for the
   * whole tab — which the old pair could not detect at all.
   *
   * P36V.1 — the flag reads `401 documented`, NOT `Credential required`. This app
   * cannot know whether a deployment enables authentication: the shared key is
   * configured where the browser cannot see it, which is why Settings' own
   * Authentication Boundary says "this screen cannot report whether access is
   * restricted" (pinned in `settings-page.test.tsx`). A bare
   * `Credential required` asserted exactly that unknowable, and the previous
   * version of THIS assertion regression-guarded the overstatement. The flag now
   * states only the contract fact, and the conditional is reachable from it via
   * `aria-describedby` → the tab-level legend.
   */
  it('marks each operation’s auth requirement as the CONTRACT FACT, explained once for the tab', async () => {
    const view = await openExplorer();
    const legend = norm(API_ACCESS_COPY.authMarkerLegend);
    expect(countOccurrences(norm(view.container.textContent ?? ''), legend)).toBe(1);
    const legendEl = explorerPanel().querySelector('.api-browser-legend') as HTMLElement;
    expect(legendEl.textContent).toBe(API_ACCESS_COPY.authMarkerLegend);
    // The legend supplies the conditional the flag deliberately does not assert.
    expect(legendEl.textContent).toMatch(/Where a deployment enables authentication/);

    const authFlag = () =>
      Array.from(detailPane().querySelectorAll('.api-browser-meta-item'))
        .find((el) => el.querySelector('dt')?.textContent === 'Auth')
        ?.querySelector('dd');

    // GET /api/about documents a 401.
    expect(authFlag()?.textContent).toBe('401 documented');
    expect(authFlag()?.className).toContain('required');
    // ...and it is programmatically tied to the legend that qualifies it, so a
    // reader who lands in the detail pane is not left with a bare marker.
    expect(authFlag()?.getAttribute('aria-describedby')).toBe(legendEl.id);
    expect(legendEl.id).toBeTruthy();

    // GET /api/health is the one operation that documents none.
    fireEvent.click(within(document.querySelector('.api-browser-list') as HTMLElement).getByText('/api/health'));
    expect(authFlag()?.textContent).toBe('No 401 documented');
    expect(authFlag()?.className).not.toContain('required');

    // The retired paragraphs are gone from the whole tab...
    const text = view.container.textContent ?? '';
    expect(text).not.toMatch(/A credential is required when this deployment enables authentication/i);
    expect(text).not.toMatch(/stays reachable without a credential even where authentication is enabled/i);
    // ...and so is the unqualified claim the flag itself used to make.
    expect(text).not.toMatch(/\bNo credential required\b/);
    expect(text).not.toMatch(/^Credential required$/m);
  });

  it('says a write operation declares NO request-body schema instead of inventing one', async () => {
    await openExplorer();
    fireEvent.click(screen.getByText('/api/validate/record'));
    const detail = detailPane();
    expect(
      within(detail).getByText(
        /The contract declares no request body for this operation\. Where one is expected, it is described under Purpose rather than as a schema/i,
      ),
    ).toBeInTheDocument();
    // No fabricated media type or schema disclosure for it.
    expect(detail.querySelectorAll('.api-browser-mediatype')).toHaveLength(0);
    // ...and the metadata row says the same thing rather than guessing.
    const body = Array.from(detail.querySelectorAll('.api-browser-meta-item')).find(
      (el) => el.querySelector('dt')?.textContent === 'Request Body',
    );
    expect(body?.querySelector('dd')?.textContent).toBe('None declared');
  });

  it('renders a documented-but-never-produced 200 in the contract’s own words', async () => {
    await openExplorer();
    fireEvent.click(screen.getByText('/api/uploads'));
    const detail = detailPane();
    // The 200 is listed, and its description says it never happens. No heading
    // anywhere calls it a success.
    expect(
      within(detail).getByText(/Not produced by this operation — every request is refused with the 403\./i),
    ).toBeInTheDocument();
    expect(within(detail).getByText(/This is the only outcome\./i)).toBeInTheDocument();
    expect(Array.from(detail.querySelectorAll('h5')).map((h) => h.textContent)).not.toContain('Success');
    expect(detail.textContent).not.toMatch(/successful response/i);
  });

  it('keeps raw JSON behind a Technical Schema disclosure, collapsed', async () => {
    await openExplorer();
    fireEvent.click(screen.getByText('/api/experiments/{id}/answers'));
    const detail = detailPane();

    const disclosures = Array.from(detail.querySelectorAll('details')) as HTMLDetailsElement[];
    expect(disclosures.length).toBeGreaterThanOrEqual(4);
    disclosures.forEach((d) => expect(d.open).toBe(false));

    const schema = within(detail).getAllByText('Technical Schema')[0];
    expect(within(detail).queryByText('Schema')).not.toBeInTheDocument();
    fireEvent.click(schema);
    expect((schema.closest('details') as HTMLDetailsElement).open).toBe(true);
    expect(within(detail).getByText(/SyntheticAnswersBody/)).toBeInTheDocument();
  });

  /* --- Purpose: what may and may not be collapsed (P36V.1) ------------------
   *
   * Slice 13 put every paragraph after the lead behind a `Full Description`
   * disclosure the moment a description contained ANY blank line, with no length
   * threshold. Measured over the real generated contract that collapsed 31 of 35
   * operations and hid 8,568 of 18,314 description characters — 47% — and what it
   * hid was precisely the boundary copy that keeps the visible lead from
   * overstating the code: "There is no language model … refused honestly rather
   * than answered", the graph structural-staleness disclosure, "never a
   * correctness ruling. Read-only." That inverts the rule the sibling Data &
   * Privacy suite enshrines: progressive disclosure is for EDGE CASES only.
   *
   * No test could catch it, because `openApiFixture` contains no multi-paragraph
   * description at all. These four tests close that: three synthetic cases pin the
   * RULE at its boundaries, and the fourth runs the REAL contract's 35
   * descriptions through it. */

  /** A description faithfully derived from the real contract: an 78-character lead
   *  followed by a 316-character boundary paragraph. Under the old behaviour the
   *  caveat was hidden behind a disclosure that cost more chrome than the lead. */
  const shortLeadWithCaveat = REAL_CONTRACT_DESCRIPTIONS.find(
    (d) => d.op === 'GET /api/memory/concepts/{concept_id}',
  )!.description;

  function localContract(description: string) {
    return {
      openapi: '3.1.0',
      info: { title: 'Synthetic Local Contract', version: '0.0.0' },
      paths: {
        '/api/fake/one': {
          post: {
            tags: ['Synthetic'],
            summary: 'A Synthetic Operation With A Docstring',
            description,
            responses: { '200': { description: 'Fine.' } },
          },
        },
      },
    };
  }

  async function purposeSection(description?: string) {
    if (description === undefined) await openExplorer();
    else await openExplorer({ [OPENAPI_URL]: { body: localContract(description) } });
    return Array.from(detailPane().querySelectorAll('.api-browser-section')).find(
      (s) => s.querySelector('h5')?.textContent === 'Purpose',
    ) as HTMLElement;
  }

  it('renders a MEDIUM description in full — no disclosure, nothing one keystroke away', async () => {
    const purpose = await purposeSection(
      'The lead paragraph states the purpose.\n\nThe second paragraph\n   wraps in the source and carries operational detail.\n\nThe third sentence adds one more line of ordinary operational wording.',
    );
    // 108 characters of remainder: below the threshold, so all three paragraphs
    // are visible at once and there is no `<details>` to open.
    expect(purpose.querySelector('details')).toBeNull();
    for (const text of [
      'The lead paragraph states the purpose.',
      // A soft-wrapped source line is joined with a space, never truncated.
      'The second paragraph wraps in the source and carries operational detail.',
      'The third sentence adds one more line of ordinary operational wording.',
    ]) {
      expect(within(purpose).getByText(text).closest('details')).toBeNull();
    }
  });

  it('NEVER collapses a boundary caveat, however long the description', async () => {
    // A remainder well over the threshold whose first paragraph is a real
    // boundary claim from this API's own contract. Length alone would collapse it.
    const caveat =
      'There is no language model. A question outside the catalog, or one too ambiguous to route, is refused honestly rather than answered.';
    const filler =
      'This paragraph is ordinary operational wording that exists only to push the remainder well past the four-hundred-character disclosure threshold, so that length cannot be the reason the disclosure is absent. It repeats no claim and carries no caveat of its own, and it is long enough on its own to trip a purely length-based rule several times over.';
    expect(caveat.length + filler.length).toBeGreaterThan(PURPOSE_DISCLOSURE_MIN_CHARS);

    const purpose = await purposeSection(`The lead states the purpose.\n\n${caveat}\n\n${filler}`);
    expect(purpose.querySelector('details')).toBeNull();
    expect(within(purpose).getByText(caveat)).toBeInTheDocument();
    expect(within(purpose).getByText(filler)).toBeInTheDocument();
  });

  it('collapses only a LONG, caveat-free remainder — and loses nothing when it does', async () => {
    // Ordinary mechanics only: this wording is checked below to be free of every
    // marker in `BOUNDARY_CAVEAT_MARKERS`, which is what makes it collapsible.
    const second =
      'This second paragraph carries operational detail and nothing else, describing how a caller supplies the request, which header it sends alongside the body, and how the result is read back out again once the call returns.';
    const third =
      'This third paragraph continues in exactly the same register, listing ordinary request mechanics at enough length that the two of them together clear the disclosure threshold comfortably.';
    expect(isBoundaryCaveat(second)).toBe(false);
    expect(isBoundaryCaveat(third)).toBe(false);
    expect(second.length + third.length).toBeGreaterThan(PURPOSE_DISCLOSURE_MIN_CHARS);

    const purpose = await purposeSection(`The lead states the purpose.\n\n${second}\n\n${third}`);
    // The lead is visible and is NOT inside a disclosure.
    expect(within(purpose).getByText('The lead states the purpose.').closest('details')).toBeNull();
    // The remainder is collapsed, counted honestly, and complete.
    const more = purpose.querySelector('details') as HTMLDetailsElement;
    expect(more.open).toBe(false);
    expect(more.querySelector('summary')?.textContent).toBe('Full Description2 more paragraphs');
    expect(within(more).getByText(second)).toBeInTheDocument();
    expect(within(more).getByText(third)).toBeInTheDocument();
    // The count chip has its OWN class: `.api-browser-reftag` means "resolved
    // schema reference" everywhere else, and `settings-page.test.tsx` reads it
    // that way.
    expect(more.querySelector('.api-browser-morecount')).not.toBeNull();
    expect(more.querySelector('.api-browser-reftag')).toBeNull();
  });

  it('shows a SHORT lead plus its boundary paragraph together, from the real contract', async () => {
    const purpose = await purposeSection(shortLeadWithCaveat);
    expect(purpose.querySelector('details')).toBeNull();
    // The availability-before-identity caveat, visible without any interaction.
    expect(purpose.textContent).toMatch(
      /availability is reported before identity, because the set of valid ids cannot be known without a graph/,
    );
    expect(purpose.textContent).toMatch(/leads to verify, never a verdict/);
  });

  it('a single-paragraph description adds no disclosure at all', async () => {
    const purpose = await purposeSection();
    expect(purpose.querySelector('details')).toBeNull();
    expect(purpose.textContent).toContain('Non-sensitive app/provenance metadata for Settings.');
  });
});

// --- the REAL contract, run through the disclosure rule -----------------------

/**
 * The rule (`splitPurpose`) exercised over the descriptions the app actually
 * renders, not over a hand-built fixture. This is the only instrument that could
 * have caught the defect: `openApiFixture` carries no multi-paragraph description,
 * so every rendering assertion in this suite passed while 47% of the contract's
 * prose was hidden by default.
 *
 * HONEST LIMIT: `REAL_CONTRACT_DESCRIPTIONS` is a point-in-time copy of the
 * generated document (see its docstring) — CI does not regenerate it, so a NEW
 * backend docstring is not covered until someone re-runs the generator. What is
 * established here is that the rule holds over this API's real prose; the rule
 * itself, not this copy, is what protects a description added later.
 */
describe('the Full Description rule over the REAL generated contract', () => {
  /*
   * THE NUMBER IN THIS TITLE DRIFTED ONCE, AND A TITLE CANNOT FAIL.
   *
   * The prose-truth pass (#119) moved the assertion below from 90 to 91 and left this
   * name reading "90 post-lead paragraphs". Nothing caught it, because a test NAME is
   * not an assertion — it is prose that happens to sit next to one, and it stated a
   * figure the test itself disproved on the next screenful. It was found only when a
   * later merge conflicted on the same two lines.
   *
   * Both numbers are re-measured from `create_app().openapi()` on every change (the
   * figure quoted here used to be a bare "92", which had itself gone stale).
   * If you change the assertion, change the test NAME in the same edit — that is the
   * whole lesson of the paragraph above, and it is easier to forget than the number.
   *
   * 2026-08-16: Unmapped Notes took this to 51 operations / 109 paragraphs / 51,498
   * characters, and the submission slice took it to 48 / 105 / 49,238 — each counting
   * from the same base on its own branch. THE MERGE IS NONE OF THOSE NUMBERS, and it
   * is not their arithmetic either: it MEASURES 52 / 119 / 55,611. Adding the deltas
   * would have given 110 paragraphs, which is wrong by nine, because each branch also
   * re-transcribed shared operations whose paragraph counts moved. Two branches
   * incrementing one counter is invisible to a three-way merge when they agree and
   * merely noisy when they disagree; either way the only safe answer is to re-measure
   * the merged document, which is what these three figures are.
   */
  it('describes the contract it claims to: 69 operations, MEASURED on the merged tree', () => {
    // FOUR slices have now raised this from 52 for real, different additions — the
    // asset slice, the transcript slice, run removal, and the two CONFLICT
    // RESOLUTION operations. Both sides of this merge conflict carried a number
    // correct for its own branch and wrong for the merge; neither was kept.
    // Re-measured on the merged tree by the paragraph rule transcribed into Python
    // over `create_app().openapi()`.
    // 66 -> 68 operations, 79,892 -> 81,416 characters, 172 -> 176 paragraphs: the two
    // RUN-LEVEL WRITE operations, `POST .../runs/{run_id}/answers` and `.../edit`.
    // They exist because a spectrum, a QC verdict, a descriptor and an asset hash
    // belong to the run that measured them: the record's own `/answers` now refuses
    // them with `409 belongs_to_a_run` once runs exist, because before it did, the
    // answer was accepted, reported as applied, and published nothing. Net +1,524
    // characters across the two new operations; NO existing description changed, and
    // `test_contract_description_parity.py` proves that rather than leaving it asserted
    // here. Re-measured over the transcribed array by the same paragraph rule.
    const total = REAL_CONTRACT_DESCRIPTIONS.reduce(
      (n, d) => n + splitPurpose(d.description).lead.length + rest(d).join('').length,
      0,
    );
    // 18,314 -> 18,481: the captured copy of `GET /api/experiments` was refreshed to
    // match the backend description again (it had gone stale when that docstring
    // gained the derived `scenario` sentence), which is +167 characters.
    //
    // 18,481 -> 20,915 and 35 -> 36 operations: the backend now publishes
    // `GET /api/runtime/database/recon`. The hosted screen renders from the LIVE
    // `/api/openapi`, so a caption still claiming 35 would be visibly false. The
    // captured `GET /api/health` copy was refreshed in the same pass — it had gone
    // stale when that docstring gained the database-block paragraph.
    //
    // 20,915 -> 21,270 and 43 -> 44 paragraphs: `POST /api/demo/run` gained a
    // paragraph stating that it never overwrites your work — it refuses with 409
    // when the canonical target has drifted, rather than silently discarding a
    // confirmed edit (W1). The old description asserted the opposite ("overwriting
    // it in place"), so leaving this pinned at 20,915 would have kept a caption
    // describing behaviour the API no longer has.
    //
    // 21,270 -> 21,266: P1 (product-facing language) re-synced the captured copy
    // for the five operations whose OpenAPI prose it reworded — `POST /api/demo/run`,
    // `POST /api/demo/reset`, `GET /api/experiments`, `.../pending` and
    // `.../source-preview`. Development jargon rendered verbatim in the Endpoint
    // Explorer ("synthetic demo", "seeded fixture", "synthetic fixture") became
    // product language ("built-in example", "reference file"), for a net -4
    // characters. Operation and paragraph counts are unchanged: no paragraph was
    // added or removed, only rewritten.
    // 21,266 -> 21,909: the export-recovery slice extended four operation
    // descriptions, because it made four artifact readers tolerate an unreadable
    // exported artifact and the contract text would otherwise have been false —
    // `POST .../validate`, `GET|POST .../warnings` and `GET .../evidence`. Each now
    // states what it does when the written artifact cannot be read. Net +643
    // characters, and the POST-lead paragraph count moves 44 -> 45: `POST
    // .../validate` gained a paragraph rather than extending an existing one,
    // because its fail-closed behaviour is a separate statement from its verdict
    // contract. Operation count is unchanged at 36. (An earlier draft of this
    // note claimed the paragraph count was unchanged; it was not, and the
    // assertion below caught that.)
    //
    // A NOTE FOR WHOEVER MOVES THIS NEXT: this figure went stale twice in one
    // session because `REAL_CONTRACT_DESCRIPTIONS` was a hand-transcribed copy of
    // the generated spec with no parity check — the drift was caught by a human
    // reading a diff, not by a test. `apps/api/tests/test_contract_description_parity.py`
    // now asserts the copy matches `create_app().openapi()` in both directions, so
    // this constant should only ever move together with a deliberate contract edit.
    // 21,909 -> 22,576: R1 made the Example-Workspace reset refuse to run against a
    // classification the operator approved but that no longer holds, so
    // `POST /api/demo/reset` documents a new precondition (`plan_digest`, 428 when
    // omitted / 412 when stale) and a derived summary of the confirmed work a reset
    // would discard. Net +667 characters in ONE operation, and the post-lead
    // paragraph count moves 45 -> 46: the precondition is a separate statement from
    // what the operation does, and folding it into the lead would have buried the one
    // sentence that explains why an execute can be refused. Operation count is
    // unchanged at 36.
    // 22,576 -> 23,850 and 36 -> 38 operations, 46 -> 49 paragraphs: the built-in
    // examples moved out of the ordinary workspace and into an isolated
    // worked-example session, so the contract publishes that session's lifecycle —
    // `POST /api/tutorial/sessions` (3 paragraphs) and
    // `DELETE /api/tutorial/sessions/{session_id}` (2 paragraphs). Net +1,274
    // characters across the two new operations; no existing description changed, and
    // the parity test named below proves that rather than leaving it asserted here.
    //
    // 23,850 -> 24,623 and 49 -> 51 paragraphs: `POST /api/demo/run` and
    // `POST /api/demo/reset` each gained a LEADING paragraph stating the
    // `X-Isaac-Tutorial-Session` REQUIREMENT, which until now appeared only inside each
    // operation's `409` sub-description — so a reader consulting the operation to learn
    // how to call it saw no precondition at all and could only discover it by reading a
    // failure case. `/demo/reset` additionally stopped saying "the workspace" for a
    // scope it cannot reach: it refuses when `scope is None`, and
    // `reset_to_canonical_seed(session_id=scope)` only ever addresses
    // `scope_root(scope)`, so "Restores the workspace to exactly the five canonical
    // built-in example records" described a destructive act on the ordinary workspace
    // that this endpoint has no path to perform. Net +773 characters in TWO operations;
    // operation count unchanged at 38. The paragraph count moves by exactly 2 because a
    // new FIRST paragraph makes the requirement the lead and pushes each old lead into
    // `rest` — it is one added `\n\n` per operation, not a reflow.
    // 24,623 -> 25,500 and 38 -> 39 operations, 51 -> 54 paragraphs: the record
    // verification slice added `GET /api/runtime/verification`, whose description
    // is a lead plus three paragraphs (+877 characters in ONE new operation; no
    // existing description changed, which the parity test named above proves
    // rather than leaving asserted here).
    //
    // NOTE WHICH LENGTH THIS IS, because two plausible ones differ by exactly 108
    // here and picking the wrong one wastes a debugging cycle: `total` above sums
    // `lead.length + rest.join('').length`, i.e. the text AFTER `splitPurpose`
    // has consumed the blank-line separators. Summing `d.description.length`
    // instead gives 25,608 — the same text plus the 54 `\n\n` separators (54 x 2).
    //
    // THESE THREE NUMBERS WENT STALE IN THE COMMIT THAT ADDED THAT OPERATION, and
    // the failure was misattributed before it was fixed — read as a concurrent
    // backend worker's, because the surrounding comments discuss `apps/api`
    // docstrings. They do not: this test reads a STATIC COMMITTED ARRAY in
    // `test/apiFixtures.ts` plus `splitPurpose` from `ApiDocs.tsx`, and touches no
    // `apps/api` file at runtime, so no backend change can move it. (The test that
    // does react to `apps/api` is `apps/api/tests/test_contract_description_parity.py`,
    // which compares that array against the served document — a different test, in
    // a different suite.) `git log -- src/test/apiFixtures.ts` settles the question
    // in one command and should be the first thing run when this fails.
    // 25,500 -> 26,223 (+723): `GET /api/runtime/verification` gained the `mode`
    // disclosure. That route now serves TWO corpora rather than one, and its
    // description had to say so -- it previously read "over the ten public
    // upstream ISAAC example records" and "this operation does not connect to any
    // database", both of which became false the moment the authorized private
    // mode was made reachable. The re-transcription is mechanical: it was copied
    // from `create_app().openapi()`, not written by hand, and
    // `apps/api/tests/test_contract_description_parity.py` is what proves the
    // copy still matches the server.
    //
    // A note for whoever re-transcribes next: dump the string with
    // `ensure_ascii=False`. The parser in that parity test unescapes `\n`, `\"`,
    // `\'` and `\\` and NOT `\uXXXX`, so an ASCII-escaped em dash reads as six
    // literal characters and the two sides differ in a way the diff renders
    // identically. That cost a debugging round here.
    // 26,223 -> 27,188 (+965): the review follow-up on the same operation. The
    // `mode` disclosure had shipped with two statements that measurement
    // contradicts, and correcting prose is longer than asserting it. (1) It said
    // the private mode "is refused rather than attempted when its environment
    // gates are unmet, and reports `unavailable` when the driver is absent" --
    // but only the `PGDATABASE` pin refuses; a missing `PGHOST`/`PGUSER`/
    // `PGPASSWORD` reports `unavailable`, as does an unimportable driver. An
    // operator reading the old text of a pod saying `unavailable` would hunt for
    // a missing driver instead of an unset host. Each word is now paired with
    // its own cause, and `apps/api/tests/test_verification_route_wiring.py`
    // measures both under real environments. (2) It said the connection is
    // opened "from the pod", which is where the deployment puts the process, not
    // anything this code checks -- now stated as configuration rather than
    // enforcement. Two smaller edits: "always named in the report itself" became
    // false for pending envelopes (they carry no `metadata`), and the public
    // bullet now names `public_reference` inside the sentence that makes the
    // no-database claim, so the claim is scoped where it is read. NO paragraph
    // was added or removed -- the count below stays 56, and that is asserted
    // rather than assumed. One wording constraint is worth knowing before
    // editing that description again: the credential libpq variable is
    // DESCRIBED, not named, because `apps/api/tests/test_about_and_openapi.py`
    // scans the whole generated document for the substring "password" with no
    // exception list, and spelling the variable out fails it.
    //
    // 27,188 -> "32,174" -> 29,052, and 39 -> "42" -> 40 operations. READ THE
    // MIDDLE NUMBER AS A DEFECT, NOT AS A STEP. It is the only entry in this log
    // that records a measurement of something that was never true.
    //
    // WHAT HAPPENED. `origin/main` and the create-experiment branch each added
    // operations to `REAL_CONTRACT_DESCRIPTIONS`. The merge was resolved by
    // KEEPING BOTH SIDES, which left `GET /api/runtime/verification` and
    // `GET /api/health` in the array TWICE each — 42 entries describing 40
    // operations. The three numbers here were then RAISED TO MATCH the broken
    // array: 42 / 32,174 / 67 were each produced by running this assertion and
    // transcribing what it reported, which is the correct procedure applied to an
    // input nobody had checked. The comment that shipped alongside them claimed
    // every entry had been re-transcribed from `create_app().openapi()`. It had
    // not. Two whole descriptions were counted twice.
    //
    // WHY NOTHING CAUGHT IT, which is the part worth carrying forward. Both
    // directions of `apps/api/tests/test_contract_description_parity.py` are blind
    // to a duplicate: one iterates the entries and looks each up in the spec (a
    // duplicate matches, twice, happily), the other compares SETS. And "I measured
    // it" felt like verification while it was only transcription — measuring a
    // corrupt input reproduces the corruption with a fresh-looking number beside
    // it. The `contains each operation exactly once` test below is the missing
    // control, and it is one line.
    //
    // 29,052 / 61 is the corrected measurement, after deleting the two duplicate
    // rows and re-transcribing all 40 entries from `create_app().openapi()` with
    // `json.dumps(..., ensure_ascii=False)`. It was cross-checked independently in
    // Python (sum of `len(description)` = 29,174 raw, minus 2 per `\n\n`
    // separator = 29,052) rather than only by re-running the assertion that had
    // just been wrong.
    //
    // It also includes two deliberate contract edits made in the same pass:
    // `GET /api/health`'s third paragraph was CORRECTED (it claimed
    // `experiment_storage` was "derived from configuration alone", which is what
    // let a pod report `durable: true` while every write against it failed), and
    // `POST /api/experiments` gained a paragraph documenting its `503`.
    //
    // 29,052 -> 29,460 and 61 -> 62 paragraphs (C2). `POST /api/demo/reset` gained a
    // paragraph, and one sentence in the paragraph above it was CORRECTED rather than
    // extended. The reset now re-checks the `plan_digest` per record, inside that
    // record's own lock, immediately before touching it — so a write that lands
    // between the first check and the mutation is refused rather than destroyed. That
    // made the old sentence "A missing digest is `428`, a stale one is `412`, and
    // neither mutates anything" false: a `412` from the per-record check is the one
    // refusal that can leave earlier records already reset. The `412` response
    // description says so too, though that block is not part of this measurement.
    //
    // Cross-checked in Python rather than only by re-running this assertion, exactly
    // as the corrected 29,052 was: the re-transcribed entry is 2,047 characters where
    // the old one was 1,637 (+410), and it holds one more `\n\n` separator, which this
    // sum drops (+410 - 2 = +408).
    //
    // 29,460 -> 30,677 and 62 -> 64 paragraphs (export fan-out). One operation
    // changed: `POST /api/experiments/{experiment_id}/export`. Under contract §1 D1
    // an experiment with runs now exports ONE record PER RUN, so the old description
    // was not merely thin, it was wrong for that case — it promised a single
    // `record_id` and a single `artifact_refs` pair, and a fan-out returns neither.
    // The re-transcribed entry adds two paragraphs: what a record with runs returns
    // (and that a record with NO runs, which is every record this API can currently
    // create, is unchanged), and what is actually guaranteed if the export fails
    // part-way — validation is all-or-nothing, the state is saved once at the end,
    // and it is NOT atomic across the individual file writes. That last sentence is
    // the one worth protecting: the honest guarantee is weaker than "atomic", and
    // the description says so rather than implying a stronger one.
    //
    // Cross-checked in Python rather than only by re-running this assertion, as
    // every corrected total above was: the re-transcribed entry is 1,867 characters
    // where the old one was 646 (+1,221) and holds two more `\n\n` separators, which
    // this sum drops (+1,221 - 4 = +1,217). Independently, the whole array
    // re-measured from the file: 40 operations, 40 unique, raw sum 30,805, 64
    // separators, 30,805 - 128 = 30,677.
    //
    // 30,677 -> 31,236 and 64 -> 66 paragraphs (fan-out review fixes). TWO
    // operations changed, each gaining exactly one paragraph:
    //
    //   `POST .../validate` used to fall into its dry-run branch for a record with
    //   runs and validate the experiment-level half — which is never exported —
    //   returning a schema-invalid verdict about a set of records that had just
    //   passed official validation. It is now checked per run, and says so,
    //   including that the top-level `dry_run` is true if any run's verdict came
    //   from an in-memory candidate.
    //
    //   `GET .../artifacts` returns four nulls for such a record, because it serves
    //   the record's OWN pair and there is none. Beside a fan-out-aware
    //   `artifact.state` of `current` that read as "current, but there is nothing",
    //   so the operation now states why and that the per-run files are not listed
    //   here yet.
    //
    // Cross-checked in Python rather than transcribed from the assertion that
    // reported it: 40 operations, 40 unique, raw sum 31,368, 66 separators,
    // 31,368 - 132 = 31,236.
    //
    // 31,236 -> 33,010 and 66 -> 69 paragraphs (the SECOND fan-out review). THREE
    // operations changed — one export, and the two equivalent warnings forms that
    // share one description constant:
    //
    //   `POST .../export` gained two paragraphs. One states what happens to the
    //   records of runs that have been REMOVED, and it exists because the response
    //   now separates three outcomes an empty `pruned_record_ids` used to conflate:
    //   nothing was orphaned, an orphan is kept because a surviving record still
    //   links to it (`protected_record_ids` — the NORMAL case for runs sharing a
    //   sample id, previously invisible), and a kept record could not be read so
    //   nothing was examined at all (`prune_declined`). The other adds the
    //   `sibling_link_conflict` refusal: an export that would rewrite a record an
    //   already-exported record links to as sharing its sample id, with a different
    //   sample id, is refused, because the link could not be corrected afterwards
    //   and one of the two records would be false.
    //
    //   `GET`/`POST .../warnings` each gained one paragraph. For a record with runs
    //   the advice is now computed per run — it used to be computed from the
    //   experiment-level half, which is never exported and holds no measurement, and
    //   it therefore advised `NO_MEASUREMENT_SERIES` about records that all carry a
    //   measurement block. `runs[]` carries each run's own warnings and `dry_run`;
    //   the top level is the deduplicated union, which is safe here precisely
    //   because this channel carries no verdict.
    //
    // Cross-checked in Python from the file rather than transcribed from the
    // assertion that reported it. Per entry: export 1,867 -> 2,865 (+998) with one
    // more separator; each warnings entry 600 -> 991 (+391) with one more separator.
    // Raw sum 31,368 + 998 + 2x391 = 33,148; separators 66 + 3 = 69; 33,148 - 138 =
    // 33,010. Whole array re-measured independently: 40 operations, 40 unique, raw
    // sum 33,148, 69 separators.
    //
    // 33,010 -> 36,699, 40 -> 45 operations and 69 -> 79 paragraphs (the Run HTTP
    // API). FIVE operations were ADDED, none was edited: list, add, read, edit and
    // check one run. The Run domain model already existed in `workspace` — one run
    // exports one official ISAAC record — and nothing in it was reachable over
    // HTTP; these five expose it.
    //
    // ONE OF THE FIVE WAS REWORDED BECAUSE THIS SUITE CAUGHT IT, and that is worth
    // recording, because the `hides ZERO characters` test below is the only thing
    // that could have. `POST .../runs` shipped a 483-character, caveat-bearing
    // remainder ("no scientific value is copied into it and none is invented",
    // "there is no limit on how many runs") that matched NOT ONE
    // `BOUNDARY_CAVEAT_MARKERS` entry, so length alone collapsed it behind the
    // disclosure — exactly the failure mode that list's own comment predicts for a
    // boundary paragraph written in new words. The description was corrected to say
    // what it means in the vocabulary the rule recognises ("record-level values are
    // never copied down into it"), rather than the marker list being widened to
    // admit prose nobody had checked.
    //
    // A second pass on the same slice moved it 36,699 -> 36,846 with the operation
    // and paragraph counts UNCHANGED: `POST .../runs/{run_id}/check` gained one
    // sentence, extending an existing paragraph rather than adding one, after the
    // frontend workstream reported that the `blockers[]` element shape was
    // unspecified and it had had to guess. Every element now carries a non-empty
    // `message`, derived from what the blocking question already records, and the
    // contract says so.
    //
    // A third pass moved it 36,846 -> 37,168, again with the operation and
    // paragraph counts UNCHANGED. An independent adversarial review found that
    // `PATCH .../runs/{run_id}` accepted arbitrary invented field paths —
    // `context.typo_K`, `context.`, `timestamps.acquired_start_utc.evil` — because
    // `field_level()` is a segment-aware PREFIX test and never checked the key was
    // a real path, so one typo permanently blocked that run's official export. The
    // route's description already PROMISED the strict behaviour, so the code was
    // brought to the documentation rather than the other way round, and the
    // description now names the closed writable set it actually enforces.
    //
    // Cross-checked in Python from the generated contract rather than transcribed
    // from the assertion that reported it: 45 operations, raw sum 37,685, 79
    // separators, 37,685 - 158 = 37,527.
    //
    // 37,168 -> 37,527 (+359) across the two review-fix passes, from exactly TWO
    // operation descriptions: `POST /api/experiments/{id}/validate` 1,141 -> 1,450
    // (+309), which now documents the `unavailable` flag it was already serving, and
    // `POST .../runs` +50, which now names the lone-surrogate label refusal it
    // enforces.
    //
    // AN EARLIER REVISION ATTRIBUTED THE +309 TO "three descriptions", WHICH CANNOT BE
    // TRUE OF THIS NUMBER. `total` sums `op.description` only, and the other two edits
    // in that pass were a REQUEST BODY description (`PATCH .../runs/{run_id}`, +105)
    // and a RESPONSE description (`POST .../runs/{run_id}/check`, +287) — neither of
    // which this figure counts. Three operation descriptions growing by those amounts
    // would have given +701.
    //
    // AND THAT EXPOSES A REAL GAP, recorded rather than quietly left. NEITHER this total
    // NOR `test_contract_description_parity.py` covers anything but operation
    // descriptions, so the other two edited strings have no drift guard at all. Their
    // exact homes, because "requestBody.description" was the first guess and is wrong:
    // the PATCH string lives at
    // `requestBody.content['application/json'].schema.description` — that operation's
    // `requestBody` has only `content` and `required` — and reaches the screen as raw
    // JSON inside the collapsed Technical Schema `<pre>` (`ApiDocs.tsx:888,893`); the
    // check string is a RESPONSE description. Extending the parity fixture to both fields
    // is the fix; it is named here so the next reader does not rediscover the asymmetry.
    //
    // NOT 45 unique — 44. `GET` and `POST /api/experiments/{id}/warnings`
    // deliberately share one description, and they did so before this slice
    // existed. An earlier revision of this comment asserted "45 unique"; that was
    // never true and is corrected here rather than left to be re-derived by
    // whoever next changes this number. Nothing asserts uniqueness, which is why
    // the false count survived being written down.
    //
    // TWO BRANCHES MOVED THIS NUMBER FROM 37,527 AT THE SAME TIME, and the merged
    // value is NEITHER of theirs. Both entries are kept below, because each records a
    // real contract edit; what neither of them records is the tree this file now sits
    // in. The merge entry after them is the only one that describes it, and it was
    // MEASURED rather than obtained by adding the two deltas — see its note.
    //
    // (a) `origin/main`, via #106 — 37,527 -> 37,757 (+230) from ONE operation
    // description: `POST /api/experiments/{id}/edit` 490 -> 722 raw characters (+232
    // raw; this figure counts 230 of them, because `total` sums the split lead plus the
    // joined sections and drops the paragraph separators). It now states that only an
    // already-answered field can be corrected there — an asset whose hash is still an
    // open question belongs to the answers operation — and that a recognised field
    // carrying an unstorable value is refused before any mutation. Both were already
    // true of the served behaviour; neither was written down. The post-lead paragraph
    // count moved 79 -> 80 on that branch: the `/edit` description gained a third
    // paragraph. Measured on that branch, not derived:
    // `npx vitest run src/__tests__/settings-api.test.tsx` reported
    // `expected 37757 to be 37527` before its line was changed.
    //
    // (b) this branch, #109 — 37,527 -> 41,067 and 45 -> 47 operations: the backend now
    // publishes the two run OVERRIDE operations — recording that one run holds its own
    // value at one record-level address, and clearing it so the run inherits again. The
    // override machinery already existed in the domain model and had no HTTP caller at
    // all. The post-lead paragraph count moved 79 -> 87 on this branch: five paragraphs
    // on the override operation (what is not copied down; what IS and is NOT recorded,
    // since no actor is stored; the preconditions; the address and payload gates; the
    // idempotence) and three on the clear (what inheriting again means; the
    // preconditions; that clearing nothing is a success). Every one of the eight is
    // post-lead and every one renders INLINE — the `collapsedOps: 0` assertion below is
    // what proves that, and it was green on the first run rather than being made green.
    //
    // (c) THE MERGE — 41,297, 47 operations, 88 post-lead paragraphs. MEASURED, NOT
    // ADDED. (a) and (b) are two measurements of the same array taken from two trees
    // that each lacked the other's edit, so neither survives the merge and summing
    // their deltas would be a guess that happens to look like arithmetic. The number
    // was obtained by running the real rule over the real merged array — the same
    // `splitPurpose` and the same `rest` this assertion uses — and cross-checked in two
    // independent ways, exactly as every corrected total above was:
    //
    //   · from the SERVED document, not the copy: `create_app().openapi()` yields 47
    //     documented operations, and the splitPurpose paragraph rule transcribed into
    //     Python over those descriptions gives total 41,297 and 88 post-lead
    //     paragraphs. The captured array is what this file reads, but the server is
    //     what the screen renders, so the copy is not permitted to be the only witness.
    //   · internal consistency: raw sum of `d.description.length` = 41,473; this figure
    //     drops the 88 `\n\n` separators, and 41,473 - 176 = 41,297.
    //
    // The two branches touched DISJOINT operations — `/edit` on one side, the two new
    // override operations on the other — which is why nothing had to be reconciled in
    // `apiFixtures.ts` beyond keeping both. `apps/api/tests/test_contract_description_parity.py`
    // is what proves the merged copy still matches the server in both directions, and
    // the `contains each operation exactly once` test below is what proves the merge
    // did not duplicate a row — the exact defect the "42 / 32,174 / 67" entry above
    // records, which arose from resolving this same file by keeping both sides.
    //
    // (d) 41,297 -> 42,371 and 88 -> 90 post-lead paragraphs, from a PROSE-TRUTH pass
    // over three descriptions that were false or incomplete about the behaviour they
    // describe. This entry exists to record that a green assertion here proved nothing
    // about truth: it pins that the copy MATCHES the server, and the server was the
    // thing that was wrong.
    //
    //   · `POST .../export` +75, paragraphs unchanged. "A record with no runs, which is
    //     every record this API can currently create" was true when written (`f7c286c`)
    //     and false hours later when `POST .../runs` shipped (`3ce946e`). A client CAN
    //     create a record and add runs to it, so the fan-out branch it called
    //     unreachable is reachable.
    //   · `GET /api/experiments` +1649, +2 paragraphs. It claimed one row per experiment
    //     in the workspace and its response line said "Every experiment as a summary
    //     row" — a completeness claim the implementation deliberately cannot keep:
    //     `workspace._hydrate_ordinary_scope` swallows a durable-storage outage and the
    //     list degrades to the working copies on disk, which its own docstring calls
    //     INCOMPLETE. The degradation is now described, along with where it is
    //     disclosed (`/api/health`) and why a single-record read answers 503 instead.
    //
    //     THE FIRST CORRECTION OF IT WAS ITSELF FALSE, and that is the point of this
    //     sub-entry. It read "every one of them whenever durable storage is answering",
    //     which an independent review REFUTED BY EXECUTION: let the `SELECT` succeed —
    //     storage IS answering — and let one working-copy WRITE fail part-way through
    //     hydration (a full `emptyDir`). The restore loop's `except Exception` swallows
    //     it, every row after the failure is never restored, `/api/health` still says
    //     `durable`, and a read by id of an unrestored record answers `404`. That is
    //     the "your work is gone" claim #113 exists to prevent, in a mode nothing
    //     discloses. The description now names that second mode as an undisclosed hole
    //     instead of asserting a completeness it cannot keep. A slice whose whole
    //     purpose is removing false completeness claims introduced one; it took an
    //     adversarial reviewer running the code, not reading it, to catch that.
    //   · `POST /api/validate/record` +354, +1 paragraph. The description enumerated the
    //     response as ok/summary/errors/schema_version; the route has also returned
    //     advisory `warnings` since R2 added the advisory tier to it. The tier is now
    //     described, including that `ok` is computed from the schema verdict alone.
    //
    // MEASURED, and cross-checked the two ways every corrected total above was:
    //   · from the SERVED document, not the copy: the `splitPurpose` paragraph rule
    //     transcribed into Python over `create_app().openapi()` gives 47 operations,
    //     total 43,375 and 91 post-lead paragraphs — identical to the same rule run
    //     over this captured array.
    //   · internal consistency: raw sum of `d.description.length` = 43,557; this figure
    //     drops the 91 `\n\n` separators, and 43,557 - 182 = 43,375.
    // A third witness, before either line was changed: `npx vitest run` reported
    // `expected 43375 to be 42371`.
    // (f) THE LIST DEGRADATION IS NOW DISCLOSED IN BAND, so the description that
    //     NAMED an undisclosed hole had to stop naming it — leaving a contract
    //     advertising a defect that no longer exists is the same class of false
    //     claim as the completeness claim entry (d) removed, only inverted.
    //
    //     `GET /api/experiments` — net -30 characters, +1 post-lead paragraph, ONE
    //     operation touched. The second-mode paragraph ("unlike the first it is
    //     NOT disclosed anywhere … a read by id of an unrestored record answers
    //     404, not 503") is gone, because both statements are now false: the
    //     response carries an `incomplete` block in that mode, and the by-id read
    //     answers 503. What replaces it documents the block itself — when it is
    //     present, its two `reason` values, and why `missing_count` is always
    //     null. It is deliberately SHORTER than the hole it described.
    //
    // MEASURED the same two independent ways every corrected total above was, and
    // NOT by adding -30 to 45126:
    //
    //   · from the SERVED document: the splitPurpose paragraph rule transcribed
    //     into Python over `create_app().openapi()`'s 47 descriptions gives total
    //     45,096 and 95 post-lead paragraphs.
    //   · internal consistency: raw sum of `d.description.length` = 45,286; this
    //     figure drops the 95 `\n\n` separators, and 45,286 - 190 = 45,096.
    // (g) THE SAME OPERATION AGAIN, ONE REVIEW LATER, and the correction is that
    //     entry (f) described `restore_failed` as one failure when it is three.
    //     A reviewer measured a fourth degraded mode the branch had not closed —
    //     a hydration pass that FINISHES having refused a row filed under an id
    //     its own document does not carry — and closing it made `restore_failed`
    //     the label for every way a restore can fail to represent a stored row:
    //     an unwritable working copy, an unplaceable row, or a store that could
    //     not be resolved. The description said "the database answered and this
    //     server could not finish writing its own working copies", which is now
    //     true of only one of the three, so it names the residue instead. It also
    //     stops implying that a retry clears it: for a full disk or an
    //     unplaceable row it does not, and the served body no longer says so
    //     either.
    //
    //     `GET /api/experiments` — net +160 characters, ONE operation touched,
    //     paragraph count UNCHANGED at 95 (this edit rewrote a sentence inside an
    //     existing paragraph and added none).
    //
    // MEASURED the same two independent ways, and NOT by adding +160 to 45,096:
    //
    //   · from the SERVED document: the splitPurpose paragraph rule transcribed
    //     into Python over `create_app().openapi()` gives 47 operations, total
    //     45,256 and 95 post-lead paragraphs.
    //   · internal consistency: raw sum of `d.description.length` = 45,446; this
    //     figure drops the 95 `\n\n` separators, and 45,446 - 190 = 45,256.
    //
    // 45,256 -> 45,861 and 95 -> 96 paragraphs: SERVER-SIDE RUN SEARCH AND FILTERING.
    // `GET /api/experiments/{experiment_id}/runs` gained `q`, `overrides` and
    // `exported`, and one NEW paragraph saying what they do — that they narrow the
    // list ON THE SERVER, that `matched` and `total` mean different things, and that
    // `q` is literal text over identifiers and never a search of scientific values.
    // +605 characters, +1 paragraph, ONE operation touched.
    //
    // The paragraph is here rather than only on the parameters because the Endpoint
    // Explorer renders the OPERATION's prose first, and an operation described only
    // as an unbounded read would understate what the endpoint now does.
    //
    // MEASURED the same two independent ways, and NOT by adding +605 to 45,256:
    //
    //   · from the SERVED document: the splitPurpose paragraph rule transcribed
    //     into Python over `create_app().openapi()`, restricted to the 47 operations
    //     this array names, gives total 45,861 and 96 post-lead paragraphs.
    //   · internal consistency: raw sum of `d.description.length` = 46,053; this
    //     figure drops the 96 `\n\n` separators, and 46,053 - 192 = 45,861.
    //
    // 45,861 -> 45,974, paragraph count UNCHANGED at 96: the `q` prose was corrected,
    // not extended. An adversarial review measured that a SUBSTRING match against a
    // run id returned every run in the record -- ULIDs share a ~10-character timestamp
    // prefix -- so ids now match WHOLE, and the description had to stop saying
    // "substring search over each run's label, id and record id", which was now false
    // in the published contract. +113 characters, ONE operation touched, no new
    // paragraph.
    //
    // MEASURED the same two independent ways, and NOT by adding +113 to 45,861:
    //
    //   . from the SERVED document: the splitPurpose rule re-implemented in Python
    //     over `create_app().openapi()`, restricted to these 47 operations, gives
    //     total 45,974 and 96 post-lead paragraphs.
    //   . internal consistency: raw sum of `d.description.length` = 46,166; this drops
    //     the 96 `\n\n` separators, and 46,166 - 192 = 45,974.
    //
    // 45,974 -> 51,498, 47 -> 51 operations, 96 -> 109 post-lead paragraphs: the
    // Unmapped Notes slice publishes FOUR new operations --
    // `GET|POST /api/experiments/{id}/notes`, `GET .../notes/{note_id}` and
    // `POST .../notes/{note_id}/review`. They are long because the thing they have
    // to state is a set of refusals: that dismissal is a state and no operation
    // deletes a note, that `candidate_field_path` is null rather than a
    // plausible-looking guess when nothing proposed one, and that the four
    // not-a-value constants are constants of the shape rather than fields a request
    // can set. +5,524 characters over four operations, +13 paragraphs (3 + 2 + 4 + 4).
    //
    // MEASURED the same two independent ways, and NOT by adding +5,524 to 45,974:
    //
    //   . from the SERVED document: the splitPurpose paragraph rule re-implemented
    //     in Python over `create_app().openapi()`, restricted to the 51 documented
    //     operations this array names, gives total 51,498 and 109 post-lead
    //     paragraphs.
    //   . internal consistency: raw sum of `d.description.length` = 51,716; this
    //     figure drops the 109 `\n\n` separators, and 51,716 - 218 = 51,498.
    //
    // 51,498 -> 52,347, 109 -> 110 post-lead paragraphs, operations UNCHANGED at 51:
    // A REFUSAL THAT WAS FALSE ABOUT THE OFFICIAL SCHEMA. `mappable_field_paths` is
    // derived from this build's extractor map -- 25 paths -- and the three notes
    // operations described it as "a real official field path", so a refusal read as
    // "the official schema has no such field" for `sample.sample_id`,
    // `measurement.qc`, `attribution.uploaded_by`, `links`, `tags` and more, all of
    // which the vendored schema defines. CLAUDE.md §1 makes the schema not ours to
    // speak for. The three descriptions now say the enforced set is a SUBSET and that
    // a refusal against it is not a statement about the schema. The same pass split
    // `unreadable_entries` into its own paragraph -- the ONE new paragraph -- because
    // that count covers two different facts (an entry the model refused, and an entry
    // repeating another note's id, which this build reads perfectly well) and the
    // single sentence had asserted the first of them about both.
    // +849 characters over three operations, +1 paragraph, no operation added.
    //
    // MEASURED the same two independent ways, and NOT by adding +849 to 51,498:
    //
    //   . from the SERVED document: the splitPurpose paragraph rule re-implemented
    //     in Python over `create_app().openapi()`, restricted to the 51 documented
    //     operations this array names, gives total 52,347 and 110 post-lead
    //     paragraphs.
    //   . internal consistency: raw sum of `d.description.length` = 52,567; this
    //     figure drops the 110 `\n\n` separators, and 52,567 - 220 = 52,347.
    // MEASURED AFTER THE MERGE, from the served document, and NOT by adding the
    // two branches' deltas.
    //
    // RE-MEASURED OVER THE WHOLE ARRAY on the merged tree, not added to either
    // side's figure — which is the lesson every note above this line records. Four
    // slices have moved these numbers from the same base for real, different
    // reasons, and both sides of this merge conflict held a number that was right
    // for its own branch and wrong here.
    //
    // Measured THREE ways after the merge, all agreeing:
    //
    //   . the splitPurpose paragraph rule over this array gives 79,892 / 172.
    //   . independently, the same rule transcribed into Python over
    //     `create_app().openapi()` gives 66 operations, 79,892 and 172 — which also
    //     proves this captured array matches the served backend.
    //
    // 79,564 -> 79,892, paragraph count UNCHANGED at 172: the resolve operation's
    // description was corrected after an independent review measured that its
    // "re-submitting an identical decision is a no-op" claim is false once the
    // competing set has moved (the same body is then a recorded RE-AFFIRMATION). The
    // sentence gained `revise_resolution`'s own "and the same competing set" clause,
    // which its wire copy had dropped. Re-measured, not adjusted by the length of
    // the new text.
    // 81,416 -> 82,439 and 176 -> 180 paragraphs: `POST .../runs` had its description
    // corrected. It claimed *"The new run starts empty: record-level values are never
    // copied down into it"*, which stopped being true when the first run began adopting
    // the record's per-run content — and the sentence was live in the PUBLISHED contract
    // and in the committed wire fixture, so an independent review found the Endpoint
    // Explorer rendering a false statement about what adding a run does. The replacement
    // states the asymmetry (first run adopts, later runs do not, and why), the six
    // unclassified fields neither carries, and the `409` refusal on an already-exported
    // record. Net +1,023 characters and +4 paragraphs in ONE operation; no other
    // description changed, and `test_contract_description_parity.py` proves that rather
    // than leaving it asserted here.
    // 82,439 -> 84,501 and 68 -> 69 operations, 180 -> 185 post-lead paragraphs: the
    // backend now publishes `POST /api/assistant/ask`, the ASSISTANT SEAM's HTTP
    // consumer. `providers/assistant.py` was a fully built, fully tested seam with no
    // route at all, so "does this deployment have a native assistant?" was answerable
    // only by reading Python. Net +2,062 characters and +5 paragraphs in ONE new
    // operation; no existing description changed, and
    // `test_contract_description_parity.py` proves that rather than leaving it
    // asserted here.
    //
    // IT IS NOT `POST /api/assistant/memory/query`, and the Endpoint Explorer will
    // now show both. That one is the shipped deterministic Q&A and involves no
    // provider; this one answers `501` in every deployment, because
    // `validate_provider_config_or_raise` refuses to boot an application that names
    // the test double. Its own description says so in those terms, which is the
    // reason the paragraph count moves by five rather than by one.
    // 70 -> 71: `POST /api/experiments/{experiment_id}/discard`. Until it existed,
    // `POST /api/experiments` could create a record and no operation could take one
    // away. It is a narrow domain operation, not a generic delete: it refuses,
    // writing nothing, any record that has ever been submitted, has exported, has an
    // exported run, has a published artifact on disk, or is a built-in worked
    // example. RE-MEASURED from the served document, not incremented.
    expect(REAL_CONTRACT_DESCRIPTIONS).toHaveLength(71);
    // 84,501 -> 84,584 (+83): the assistant seam's own description was corrected, in
    // ONE operation and with the paragraph count unchanged. It read "so every request
    // is answered `501`" while the paragraph two below it documented the `422` — a
    // description contradicting itself, found by an independent review. It now reads
    // "every request that REACHES the seam", because the four validation refusals run
    // BEFORE the provider is resolved, so a malformed request is `422` in every
    // deployment and never reaches the seam at all.
    // 84,584 -> 84,757 (+173): `POST .../runs/{run_id}/answers` had its description
    // corrected, in ONE operation. It read "An answer that names no open question on
    // THIS run is ignored rather than invented" — true of an UNRECOGNISED key, and
    // false of a recognised key whose question is already CLOSED, which this branch
    // now refuses with `422 already_answered` rather than absorbing into a `200` that
    // reported no change over a value it had discarded. (THE "true of an UNRECOGNISED
    // key" HALF EXPIRED ON 2026-08-25 and this entry is left as the historical record
    // it is: a body naming ONLY unrecognised keys is now `422 unrecognized_field`, and
    // only a RIDE-ALONG unrecognised key is still ignored. See the 91,780 entry below.)
    // The replacement states both
    // halves and names the correcting operation the refusal redirects to. Re-measured
    // from `create_app().openapi()`, not adjusted by the length of the new text, and
    // `test_contract_description_parity.py` proves the captured copy matches what the
    // server serves rather than leaving it asserted here.
    // 84,757 -> 86,556 (+1,799): TWO operation descriptions were corrected in one
    // pass — `POST .../validate` and `POST .../runs/{run_id}/check`. Both said the
    // `official` block carries "the official-schema verdict" unqualified, and an
    // independent truthfulness review measured that false: `_validate_unit`'s dry-run
    // branch returns `export_draft`'s result, and `export.py` returns
    // `official_report=None` on TWO paths BEFORE `validate_official` is called — a
    // failed no-guessing report, and ISAAC's own anchored-pattern exactness gate,
    // whose findings it folds into `draft_report`. The route then stamps
    // `official["schema"] = "ISAAC v1.05"` over them. Measured on a run whose
    // descriptor name carries a trailing newline: `draft {"ok": true, "errors": []}`
    // beside `official {"ok": false, "dry_run": true, "schema": "ISAAC v1.05"}` whose
    // sole error is the exactness gate's own text. CLAUDE.md §12: "the gate is
    // ISAAC's, not upstream's". Both now say the verdict is the official schema's
    // WHERE THE OFFICIAL VALIDATOR RAN, name the exactness gate, note that `schema`
    // is stamped unconditionally and is not a provenance claim, and point at
    // `POST /api/validate/record`, which reports the two gates separately.
    // Re-measured from `create_app().openapi()`, not adjusted by the length of the
    // new text, and `test_contract_description_parity.py` proves the captured copy
    // matches what the server serves.
    // 86,556 -> 90,213 (+3,657) and 187 -> 192 post-lead paragraphs (+5), operations
    // UNCHANGED at 69: THE PENDING LIST BECAME BOUNDABLE. Five operation descriptions
    // moved, and they moved because the contract did:
    //
    //   · `GET .../pending` gained a paragraph. It answers completely by default and
    //     now accepts `run_id`, `offset` and `limit`; a description that documented
    //     only the unbounded read would understate what a caller may ask for, and —
    //     worse — would not say that a bounded response carries `pending_page`.
    //   · The FOUR mutation operations (`POST .../answers`, `.../edit` and the two
    //     run-level ones) each gained the SAME paragraph, written once in `routes.py`
    //     as `_BOUNDED_PENDING_PARAGRAPH` and interpolating `serialize.PENDING_WINDOW`
    //     rather than retyping it. Their `pending` list is now a window rather than
    //     the whole record — measured at 1,000 runs, that response was 1,773,294 bytes
    //     — and a bounded response that did not say so in the published contract would
    //     be exactly the silent truncation the bound exists to prevent.
    //
    // MEASURED three independent ways and NOT by adding the length of the new text:
    //
    //   · the splitPurpose paragraph rule transcribed into Python over
    //     `create_app().openapi()`, restricted to the 69 operations this array names,
    //     gives total 90,213 and 192 post-lead paragraphs;
    //   · the same rule over the transcribed array gives the same two numbers;
    //   · internal consistency: raw sum of `d.description.length` = 90,597, minus 2
    //     per `\n\n` separator (192 x 2 = 384) = 90,213.
    //
    // All five entries were RE-TRANSCRIBED from `create_app().openapi()` with
    // `json.dumps(..., ensure_ascii=False)`, never hand-edited, and
    // `test_contract_description_parity.py` proves the copy matches the served
    // document rather than leaving it asserted here.
    //
    // 90,213 -> 91,780 and 192 -> 193 post-lead paragraphs (2026-08-25). THREE entries
    // moved, and the operation count did not: `POST .../answers` and
    // `POST .../runs/{run_id}/answers` each state the two refusals they now perform
    // instead of promising that an unrecognised key is ignored, and
    // `GET .../evidence` states that a block-level confirmation carries `value: null`
    // — the entries it had been omitting entirely for a record created through this
    // API. The paragraph count moves by exactly ONE because only the evidence
    // description APPENDED a paragraph; the two answers descriptions rewrote existing
    // ones in place.
    //
    // RE-MEASURED the same three ways, not incremented:
    //
    //   · the splitPurpose rule in Python over `create_app().openapi()`, restricted to
    //     the 69 operations this array names: total 91,780, paragraphs 193;
    //   · the same rule over the transcribed array: the same two numbers;
    //   · internal consistency: raw sum of `d.description.length` = 92,166, minus 2 per
    //     `\n\n` separator (193 x 2 = 386) = 91,780.
    //
    // 91,780 -> 92,916 and 193 -> 194 post-lead paragraphs (2026-08-25, review fixes to
    // the slice above). TWO entries moved, operations UNCHANGED at 69, and both moves
    // are corrections to text this same PR published rather than new features:
    //
    //   · `POST .../runs/{run_id}/answers` had its unrecognised-key paragraph SCOPED.
    //     It said the key is "now REFUSED with `422 unrecognized_field`, exactly as on
    //     the record" without saying that refusal fires only where NOTHING in the body
    //     is recognised — so a ride-along key is still dropped on a `200`. The scope is
    //     now stated. Text was inserted INTO an existing paragraph, so this entry adds
    //     no paragraph.
    //   · `GET .../evidence` APPENDED one paragraph. Its block-level sentence named
    //     `qc:`, `series:` and `descriptors:` and called them scientist confirmations;
    //     the reader also serves `attribution:` (two entries per seeded record, the
    //     largest single namespace it added) and can serve `links:`, and those are
    //     source-document citations, not confirmations. Five namespaces, and two of
    //     them are not confirmations — that is the added paragraph.
    //
    // The paragraph count moves by exactly ONE for that reason, and the direction is
    // the tell: a scope correction that reflows an existing paragraph must not move it.
    //
    // RE-MEASURED the same three ways, not incremented:
    //
    //   · the splitPurpose rule in Python over `create_app().openapi()`, restricted to
    //     the 69 operations this array names: total 92,916, paragraphs 194;
    //   · the same rule over the transcribed array: the same two numbers;
    //   · internal consistency: raw sum of `d.description.length` = 93,304, minus 2 per
    //     `\n\n` separator (194 x 2 = 388) = 92,916.
    //
    // Both entries were RE-TRANSCRIBED from `create_app().openapi()` by script, never
    // hand-edited, and `test_contract_description_parity.py` proves the copy matches
    // the served document.
    // 92,916 -> 93,478 (+562): `GET .../pending`'s description was corrected, in ONE
    // operation. It said "Send any of the three and the response gains a `pending_page`
    // block" — false for `offset: 0`, which is the route's own default, so a request
    // sending only it is the UNBOUNDED read and carries no page block. An independent
    // review measured it over the real MCP dispatch: `{'offset': 0}` -> no `pending_page`,
    // `{'offset': 1}` -> yes. Not a truncation lie (the response really is complete), but
    // an agent told to page will plausibly open with `offset: 0` and find no
    // `record_total`/`withheld` to act on. The replacement names the non-zero condition,
    // adds `record_total` to the reported keys, and carries the `complete` IS RELATIVE TO
    // THE FILTER qualification `serialize.py` says it needs. Re-measured from
    // `create_app().openapi()`, not adjusted by the length of the new text.
    // 93,478 -> 94,773 (+1,295): TWO notes operations were corrected, in one change.
    // `GET .../notes` and `POST .../notes/{note_id}/review` both told a scientist that
    // after mapping a note "a value still has to be entered and confirmed on the field
    // itself" — measured over HTTP against every write route the API has, that is FALSE
    // for 7 of the 25 mappable paths (the six `system.configuration.*` and
    // `timestamps.created_utc`), each of which is refused by all five with a typed 422.
    // The listing operation gained the paragraph describing the new
    // `value_writable_field_paths` key; the review operation's `map` paragraph was
    // corrected IN PLACE. Both were re-transcribed from `create_app().openapi()` by
    // script rather than hand-edited, and `test_contract_description_parity.py` proves
    // the copy matches the served document.
    // RE-MEASURED 2026-08-26 after the rename operation merged with the notes-copy
    // corrections. 93,478 -> 94,773 (notes) -> 96,161 (rename): the figure is
    // re-measured from the served document at every merge, never arithmetic over the
    // two branches' deltas — adding them would have given 96,159 and been wrong by the
    // bytes the merge itself moved.
    // RE-MEASURED 2026-08-27 after the discard operation merged. 98,335 -> 100,212
    // (+1,877): ONE new operation, `POST .../discard`; no existing description
    // changed, and `test_contract_description_parity.py` proves that rather than
    // leaving it asserted here. Re-measured from the served document, never
    // arithmetic over a branch's delta.
    expect(total).toBe(100212);
    // 185 -> 187 (+2): the same two corrected descriptions each gained one
    // post-lead paragraph — the sentence naming `POST /api/validate/record` as the
    // operation that separates the gates. No other description moved, and
    // `test_contract_description_parity.py` proves that rather than leaving it
    // asserted here.
    // 187 -> 192 (+5): one added paragraph in each of the five operations named
    // above. Re-measured, not incremented — and note that the count moves by exactly
    // five because each is an APPENDED paragraph (one added `\n\n`), not a reflow of
    // an existing one.
    // 193 -> 194 (+1): only `GET .../evidence` APPENDED a paragraph (the five block
    // namespaces, two of which are not confirmations). The scope correction to
    // `POST .../runs/{run_id}/answers` was written INTO an existing paragraph and
    // therefore must not move this count — which is why it is asserted separately from
    // the character total rather than inferred from it.
    // 202 -> 206 (+4): `POST .../discard` is ONE new operation carrying a lead plus
    // four post-lead paragraphs. No existing description moved, and
    // `test_contract_description_parity.py` proves that rather than leaving it
    // asserted here. RE-MEASURED from the served document, not incremented.
    expect(REAL_CONTRACT_DESCRIPTIONS.reduce((n, d) => n + rest(d).length, 0)).toBe(206);
    // 194 -> 195 (+1): the pending description gained ONE post-lead paragraph — the
    // `offset=0` bounds nothing / `complete` is relative to the filter block. No other
    // description moved, and `test_contract_description_parity.py` proves that rather
    // than leaving it asserted here.
    // 195 -> 196 (+1): TWO notes descriptions were corrected and the count moves by
    // exactly ONE, which is the tell this assertion exists for. `GET .../notes`
    // APPENDED a paragraph for the new `value_writable_field_paths` key (+1); the
    // `map` correction in `POST .../notes/{note_id}/review` was written INTO an
    // existing paragraph and therefore must not move it (+0). A change that moved this
    // by two would mean the review correction had been appended rather than woven in.

    // 45,974 -> 49,238 and 47 -> 48 operations, 96 -> 105 post-lead paragraphs: the
    // backend now publishes `POST /api/experiments/{experiment_id}/submit`, the
    // scientist's submission. Two entries moved, not one: the new operation and
    // `GET /api/health`, whose captured copy was re-transcribed in the same pass
    // because that docstring gained a paragraph about the new `submission` block.
    // Neither was hand-edited — both came out of `create_app().openapi()`, which is
    // why `test_contract_description_parity.py` is green in both directions.
    //
    // THE FIRST LINE OF THIS NOTE USED TO READ "45,974 -> 48,364 … 96 -> 103" WHILE
    // THE BULLETS BELOW IT SAID 48,833 AND 104 (review item M7). It was a stale
    // first measurement left standing above a later one, and the assertions used
    // the bullets — so the headline figure was the only wrong number on the screen,
    // which is the hardest kind to notice. Both are now the same measurement, and
    // the per-entry deltas that used to appear here have been DROPPED rather than
    // recomputed: they were the arithmetic that made the discrepancy invisible.
    //
    // MEASURED the same two independent ways every corrected total above was, and
    // NOT by adding a delta to the previous figure:
    //
    //   · from the SERVED document: the splitPurpose paragraph rule transcribed
    //     into Python over `create_app().openapi()`, restricted to the 48 operations
    //     this array names, gives total 49,238 and 105 post-lead paragraphs.
    //   · internal consistency: raw sum of `d.description.length` = 49,448; this
    //     figure drops the 105 `\n\n` separators, and 49,448 - 210 = 49,238.
    //
    // The submit description moved twice after the first measurement, and the
    // numbers were RE-MEASURED each time rather than adjusted by a delta. First:
    // reviewing the real-engine proof surfaced that an already-exported record is
    // never republished, so a submission over an edited draft names records holding
    // something else — the operation now says so and reports
    // `published_artifact_state`. Second (review item M5): the operation used to
    // claim its gate was "exactly the export gate and nothing more", which
    // overstates it by one condition — `POST .../export` has no `pending_count()`
    // check at all — so a qualifying paragraph was added.
    // (e) THE SIXTH EVIDENCE CLASS. the evidence-support
    //     histogram gained a SIXTH class, `unreadable`, so
    //     `GET /api/experiments/{id}/evidence-classification` now names six classes
    //     in its lead and carries one NEW paragraph saying what `unreadable` means
    //     and that it is deliberately not `unknown`. +214 characters, +1 paragraph,
    //     one operation touched. MEASURED the same way as (c) — the paragraph rule
    //     re-implemented in Python over `create_app().openapi()`, restricted to the
    //     47 operations this array names, not read off the captured copy:
    //         total 41,511 · post-lead 89 · raw sum of descriptions 41,689
    //         internal consistency: 41,689 - (2 x 89 separators) = 41,511.
    // (e) THE ANCHORED-PATTERN EXACTNESS GATE.
    // One description grew: `POST /api/validate/record`. It had said the standalone and
    // per-experiment validators "agree by construction", full stop, which the ISAAC
    // anchored-pattern exactness gate made FALSE of the top-level `ok` — the two really
    // do diverge, measured, on a record whose tag ends in a newline. The corrected text
    // scopes the parity claim to the schema verdict, documents `schema_ok` and
    // `exactness_errors`, and keeps the superseded sentence visible with the reason, so
    // it is two paragraphs longer. The fixture was NOT hand-edited: it was
    // re-transcribed from `create_app().openapi()`, which is why
    // `test_contract_description_parity.py` is green in both directions.
    //
    // MEASURED the same two independent ways every corrected total above was:
    //
    //   · from the SERVED document: the splitPurpose paragraph rule transcribed into
    //     Python over `create_app().openapi()`'s 47 descriptions gives total 42,491 and
    //     90 post-lead paragraphs.
    //   · internal consistency: raw sum of `d.description.length` = 42,671; this figure
    //     drops the 90 `\n\n` separators, and 42,671 - 180 = 42,491.
    //
    // Neither number was arrived at by adding a delta to the previous one.
    // Every operation has a lead: none of them renders "states no purpose".
    for (const d of REAL_CONTRACT_DESCRIPTIONS) {
      expect(splitPurpose(d.description).lead.length, d.op).toBeGreaterThan(0);
    }
  });

  /*
   * THE ASSERTION THAT WOULD HAVE STOPPED ALL OF THE ABOVE, and it is one line.
   *
   * Neither parity direction in `test_contract_description_parity.py` can see a
   * duplicate: one iterates the entries and looks each up in the spec (a duplicate
   * matches happily, twice), and the other compares SETS. So a duplicated row is
   * invisible to every existing guard, is counted twice by the totals above, and
   * makes those totals look freshly measured while describing a contract that does
   * not exist.
   */
  it('contains each operation exactly once', () => {
    const seen = new Map<string, number>();
    for (const d of REAL_CONTRACT_DESCRIPTIONS) {
      seen.set(d.op, (seen.get(d.op) ?? 0) + 1);
    }
    const duplicated = [...seen].filter(([, n]) => n > 1).map(([op, n]) => `${op} x${n}`);
    expect(duplicated, 'REAL_CONTRACT_DESCRIPTIONS has duplicate entries').toEqual([]);
    expect(seen.size).toBe(REAL_CONTRACT_DESCRIPTIONS.length);
  });

  /** All paragraphs after the lead, whether they render inline or collapsed. */
  function rest(d: { description: string }): string[] {
    const { inline, collapsed } = splitPurpose(d.description);
    return [...inline, ...collapsed];
  }

  it('hides ZERO characters of the real contract, and collapses ZERO of its operations', () => {
    let collapsedOps = 0;
    let hiddenChars = 0;
    for (const d of REAL_CONTRACT_DESCRIPTIONS) {
      const { collapsed } = splitPurpose(d.description);
      if (collapsed.length > 0) collapsedOps += 1;
      hiddenChars += collapsed.join('').length;
    }
    // Before the fix: 31 operations and 8,568 characters (47%).
    expect({ collapsedOps, hiddenChars }).toEqual({ collapsedOps: 0, hiddenChars: 0 });
  });

  it('never collapses a paragraph carrying boundary/honesty vocabulary', () => {
    for (const d of REAL_CONTRACT_DESCRIPTIONS) {
      for (const paragraph of splitPurpose(d.description).collapsed) {
        expect(isBoundaryCaveat(paragraph), `${d.op}: collapsed a caveat`).toBe(false);
      }
    }
  });

  /** The three specific paragraphs the review named. Each is post-lead, each was
   *  collapsed by the threshold-free version, and each must be visible. */
  it.each([
    [
      'POST /api/experiments/{experiment_id}/assistant/query',
      'There is no language model. A question outside the catalog',
    ],
    ['GET /api/memory/graph/detail', 'This is a point-in-time index, not a map of today'],
    [
      'GET /api/graph/status',
      'Project Memory provides leads and provenance to confirm against the cited files, never a correctness ruling. Read-only.',
    ],
  ])('renders %s’s boundary paragraph inline, never behind the disclosure', (op, needle) => {
    const entry = REAL_CONTRACT_DESCRIPTIONS.find((d) => d.op === op);
    expect(entry, `no such operation in the captured contract: ${op}`).toBeDefined();
    const { lead, inline, collapsed } = splitPurpose(entry!.description);
    // It is genuinely post-lead — otherwise this test would prove nothing.
    expect(lead).not.toContain(needle);
    expect(inline.some((p) => p.includes(needle)), `${op}: not rendered inline`).toBe(true);
    expect(collapsed.some((p) => p.includes(needle))).toBe(false);
  });

  /** The threshold has to be doing real work: a caveat-free remainder above it
   *  still collapses, so the fix is a threshold plus a caveat rule, not the silent
   *  removal of the disclosure. */
  it('keeps the disclosure functional for a long, caveat-free remainder', () => {
    const ordinary = 'x'.repeat(PURPOSE_DISCLOSURE_MIN_CHARS + 1);
    expect(isBoundaryCaveat(ordinary)).toBe(false);
    const { inline, collapsed } = splitPurpose(`A lead.\n\n${ordinary}`);
    expect(collapsed).toEqual([ordinary]);
    expect(inline).toEqual([]);
    // ...and exactly at the threshold it does not.
    const atLimit = 'x'.repeat(PURPOSE_DISCLOSURE_MIN_CHARS);
    expect(splitPurpose(`A lead.\n\n${atLimit}`).collapsed).toEqual([]);
  });
});

// --- generated code examples ---------------------------------------------------

describe('Settings → Endpoint Explorer — code examples', () => {
  async function openSamples() {
    await openExplorer();
    fireEvent.click(screen.getByText('/api/experiments/{id}/answers'));
    const details = detailPane().querySelector('details.api-samples') as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(details.querySelector('summary') as HTMLElement);
    return details;
  }

  /** The language tablist is `RovingTabs` from `settings/apiShared.tsx`. Slice 12
   *  deleted the API sub-tab layer that was its other consumer, so this is now
   *  the helper's only caller — and this suite is what keeps it honest rather
   *  than letting it rot as an unused export. */
  it('is collapsed by default and offers three compact language tabs', async () => {
    const samples = await openSamples();
    const list = within(samples).getByRole('tablist', { name: 'Code example language' });
    expect(within(list).getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'cURL',
      'Python',
      'JavaScript',
    ]);
    expect(within(list).getAllByRole('tab').filter((t) => t.getAttribute('tabindex') === '0')).toHaveLength(1);
    expect(within(list).getByRole('tab', { name: 'cURL' })).toHaveAttribute('aria-selected', 'true');
  });

  it('the language tabs answer Arrow / Home / End, like every other tablist here', async () => {
    const samples = await openSamples();
    const list = within(samples).getByRole('tablist', { name: 'Code example language' });
    const at = (name: string) => within(list).getByRole('tab', { name });

    fireEvent.keyDown(at('cURL'), { key: 'ArrowRight' });
    expect(at('Python')).toHaveAttribute('aria-selected', 'true');
    expect(at('Python')).toHaveFocus();
    fireEvent.keyDown(at('Python'), { key: 'End' });
    expect(at('JavaScript')).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(at('JavaScript'), { key: 'Home' });
    expect(at('cURL')).toHaveAttribute('aria-selected', 'true');
    expect(within(list).getAllByRole('tab').filter((t) => t.getAttribute('tabindex') === '0')).toHaveLength(1);
  });

  it('shows one language at a time, generated from the endpoint contract', async () => {
    const samples = await openSamples();
    const code = () => samples.querySelector('pre')?.textContent ?? '';

    expect(code()).toContain('curl -X POST "$ISAAC_BASE_URL/api/experiments/{id}/answers"');
    expect(code()).toContain('-H "Authorization: Bearer $ISAAC_API_CREDENTIAL"');
    expect(code()).toContain('-H "Content-Type: application/json"');
    expect(code()).toContain('--data "$ISAAC_REQUEST_BODY"');

    fireEvent.click(within(samples).getByRole('tab', { name: 'Python' }));
    expect(code()).toContain('import urllib.request');
    expect(code()).toContain('/api/experiments/{id}/answers');
    expect(code()).not.toContain('curl');

    fireEvent.click(within(samples).getByRole('tab', { name: 'JavaScript' }));
    expect(code()).toContain('await fetch(url');
    expect(code()).not.toContain('import urllib.request');
  });

  it('references no SDK, no dependency, and no host', async () => {
    const samples = await openSamples();
    for (const label of ['cURL', 'Python', 'JavaScript']) {
      fireEvent.click(within(samples).getByRole('tab', { name: label }));
      const code = samples.querySelector('pre')?.textContent ?? '';
      expect(code).not.toMatch(/pip install|npm install|axios|requests\.|isaac[-_]client|@isaac/);
      expect(code).not.toMatch(/https?:\/\/|127\.0\.0\.1/);
      expect(code.toLowerCase()).not.toContain('localhost');
    }
    expect(samples.textContent).toMatch(/Standard library only — no client library exists for this API/i);
  });

  it('the code panel is a real tabpanel wired to its tab', async () => {
    const samples = await openSamples();
    const panel = within(samples).getByRole('tabpanel');
    const tab = within(samples).getByRole('tab', { name: 'cURL' });
    expect(tab).toHaveAttribute('aria-controls', panel.id);
    expect(panel).toHaveAttribute('aria-labelledby', tab.id);
    // Only ONE panel exists, so only the SELECTED tab may claim to control one.
    // `RovingTabs` (apiShared.tsx) implements this; restored here after the slice-12
    // rewrite kept the positive half of the pair and dropped the negative half.
    for (const name of ['Python', 'JavaScript']) {
      expect(within(samples).getByRole('tab', { name })).not.toHaveAttribute('aria-controls');
    }
    expect(within(samples).getAllByRole('tabpanel')).toHaveLength(1);
  });

  it('copies the shown sample, naming it, with a spoken confirmation', async () => {
    const samples = await openSamples();
    fireEvent.click(within(samples).getByRole('tab', { name: 'Python' }));
    const copy = within(samples).getByRole('button', { name: 'Copy the Python sample' });
    fireEvent.click(copy);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('import urllib.request'),
    );
    expect((document.querySelector('[role="status"]') as HTMLElement).textContent).toBe(
      'Copied the Python sample.',
    );
  });

  it('adds no second live region per copy button', async () => {
    await openSamples();
    // One `aria-live` (the result count) plus ONE shared `role="status"`.
    expect(document.querySelectorAll('[aria-live]')).toHaveLength(1);
    expect(document.querySelectorAll('[role="status"]')).toHaveLength(1);
  });
});

// --- Connect an Agent ----------------------------------------------------------

describe('Settings → API Access — Connect an Agent', () => {
  async function openConnect() {
    await openApiAccess();
    const connect = document.querySelector('details.api-connect') as HTMLDetailsElement;
    fireEvent.click(connect.querySelector('summary') as HTMLElement);
    return connect;
  }

  it('is a collapsed disclosure whose summary keeps the real heading', async () => {
    await openApiAccess();
    const connect = document.querySelector('details.api-connect') as HTMLDetailsElement;
    expect(connect.open).toBe(false);
    const heading = screen.getByRole('heading', { name: 'Connect an Agent' });
    expect(heading.tagName).toBe('H3');
    expect(heading.closest('summary')).not.toBeNull();
  });

  it('carries exactly the eight required sections, in order', async () => {
    const connect = await openConnect();
    expect(
      Array.from(connect.querySelectorAll('h4')).map((h) => h.textContent),
    ).toEqual([
      'Choose an Endpoint',
      'Set the Base URL',
      'Configure Authentication',
      'Send Structured Requests',
      'Respect Read and Write Boundaries',
      'Validate Responses',
      'Handle Errors',
      'Protect Credentials',
    ]);
  });

  /**
   * Slice 12 — the guide said "the Endpoint Explorer above" twice. The browser
   * moved to its own tab, so that was false. It now names the TAB and carries a
   * real control that goes there. The old assertions never checked the word
   * "above" at all, so this is new coverage of a defect the suite let through.
   */
  it('names the Endpoint Explorer TAB, never "above", and offers a control that goes there', async () => {
    const connect = await openConnect();
    const text = norm(connect.textContent ?? '');
    expect(text).not.toMatch(/above/i);
    expect(text).toMatch(/Start on the Endpoint Explorer tab/i);
    expect(text).toMatch(/exactly as the Endpoint Explorer tab lists them/i);

    fireEvent.click(within(connect).getByRole('button', { name: 'Open the Endpoint Explorer' }));
    expect(screen.getByRole('tab', { name: 'Endpoint Explorer' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(
      await screen.findByRole('heading', { name: 'Endpoint Explorer', level: 3 }),
    ).toBeInTheDocument();
  });

  it('states the advisory / authoritative / memory boundaries accurately', async () => {
    const connect = await openConnect();
    const text = norm(connect.textContent ?? '');
    expect(text).toMatch(/official ISAAC schema and the deterministic validators are the only authority/i);
    expect(text).toMatch(/Assistant operations are advisory/i);
    expect(text).toMatch(/Project Memory returns leads to confirm against the cited files, and is not record truth/i);
    expect(text).toMatch(/Writes change a record and require explicit user intent/i);
  });

  it('states the credential-hygiene rules', async () => {
    const connect = await openConnect();
    const text = norm(connect.textContent ?? '');
    expect(text).toMatch(/Never place it in a prompt, in source control, in a log line, or in a screenshot/i);
    expect(text).toMatch(/never echo it back in output/i);
    // This guide is the ONE canonical home of the hygiene rules; the reason keys
    // are unavailable belongs to the status banner, and this guide points there
    // instead of restating it (slice 13).
    expect(text).toMatch(/This app never displays a credential, and this screen has none to give/i);
    expect(text).not.toMatch(/API keys are unavailable here/i);
  });

  /**
   * Replaces the assertion that this guide states the hosted-access caveat. The
   * caveat is unchanged and still asserted in full — it is now the API Access
   * row's, ONE tab-level home instead of two — and this pins the guide's side of
   * that move, which the old test could not.
   */
  it('does not restate the hosted-access caveat the access rows own', async () => {
    const connect = await openConnect();
    const text = norm(connect.textContent ?? '');
    expect(text).not.toMatch(/Signing in through a deployment's identity layer/i);
    expect(text).not.toMatch(/an interactive session, not a credential a program can present/i);
    // It routes the reader to where that boundary IS stated, on this same tab.
    expect(text).toMatch(/the access rows at the top of this tab/i);
    // ...and the caveat is genuinely there, exactly once on the tab.
    const tabText = norm(apiAccessPanel().textContent ?? '');
    const caveat = API_ACCESS_ROWS.find((r) => r.term === 'Hosted Authentication Boundary')!.detail;
    expect(countOccurrences(tabText, norm(caveat))).toBe(1);
  });

  it('derives its error and media-type facts from the contract', async () => {
    const connect = await openConnect();
    const text = norm(connect.textContent ?? '');
    expect(text).toContain(FACTS.errorCodes.join(', '));
    expect(text).toContain(FACTS.requestMediaTypes.join(', '));
    // It renders no COUNT: that fact is Quick Start's, from the same document.
    expect(text).not.toMatch(/\d+ of \d+ operations document a 401/);
  });

  it('states no universal rule about unnamed request-body fields', async () => {
    // P36V — this clause used to say an unnamed key "is dropped rather than
    // interpreted". FALSE for a mutating operation: `DemoResetRequest` sets
    // extra="forbid", so POST /api/demo/reset rejects an unnamed key with 422,
    // and that operation's own generated description — rendered on the Endpoint
    // Explorer tab — says "Any other field is rejected." Extra-field handling
    // varies per model and the document exposes no signal a caller could read
    // off, so the guide must not generalise.
    const connect = await openConnect();
    const text = norm(connect.textContent ?? '');
    expect(text).not.toMatch(/is dropped rather than interpreted/i);
    expect(text).not.toMatch(/unnamed (key|field)s? (is|are) (dropped|ignored)\b/i);
    // …and it must still tell the reader where the real answer lives.
    expect(text).toMatch(/reject an unnamed key outright and others ignore it/i);
    expect(text).toMatch(/Endpoint Explorer is the authority/i);
  });

  it('invents no capability this build lacks', async () => {
    const connect = await openConnect();
    const lower = (connect.textContent ?? '').toLowerCase();
    for (const needle of ['sdk', 'rate limit', 'scope', 'streaming', 'webhook', 'refresh']) {
      expect(lower.includes(needle), `invented capability: ${needle}`).toBe(false);
    }
  });
});

// --- accessibility of both API tabs -------------------------------------------

describe('Settings → the API tabs — accessibility', () => {
  const OPENERS = [
    ['API Access', openApiAccess],
    ['Endpoint Explorer', openExplorer],
  ] as const;

  it.each(OPENERS)('never skips a heading level on %s', async (_name, open) => {
    const view = await open();
    const levels = Array.from(view.container.querySelectorAll('h1, h2, h3, h4, h5, h6')).map(
      (h) => Number(h.tagName[1]),
    );
    expect(levels.length).toBeGreaterThan(0);
    for (let i = 1; i < levels.length; i += 1) {
      expect(levels[i] - levels[i - 1], `outline: ${levels.join(',')}`).toBeLessThanOrEqual(1);
    }
    view.unmount();
  });

  it.each(OPENERS)('renders no external URL, script, or iframe on %s', async (_name, open) => {
    const view = await open();
    expect(view.container.querySelectorAll('script')).toHaveLength(0);
    expect(view.container.querySelectorAll('iframe')).toHaveLength(0);
    for (const el of Array.from(view.container.querySelectorAll('[href], [src]'))) {
      const url = el.getAttribute('href') ?? el.getAttribute('src') ?? '';
      expect(/^(https?:)?\/\//.test(url), `external URL: ${url}`).toBe(false);
    }
    const lower = (view.container.textContent ?? '').toLowerCase();
    for (const needle of ['swagger', 'redoc', 'unpkg']) expect(lower).not.toContain(needle);
    view.unmount();
  });

  /** Every section on both tabs is NAMED, so a screen-reader user can list them
   *  instead of hearing an unlabelled region. */
  it.each(OPENERS)('names every landmark region on %s', async (_name, open) => {
    const view = await open();
    for (const el of Array.from(view.container.querySelectorAll('[aria-labelledby]'))) {
      const id = el.getAttribute('aria-labelledby') as string;
      expect(document.getElementById(id), `dangling aria-labelledby: ${id}`).not.toBeNull();
      expect(document.getElementById(id)?.textContent?.trim()).toBeTruthy();
    }
    // No `aria-describedby` may dangle either — the disabled control depends on it.
    for (const el of Array.from(view.container.querySelectorAll('[aria-describedby]'))) {
      const id = el.getAttribute('aria-describedby') as string;
      expect(document.getElementById(id), `dangling aria-describedby: ${id}`).not.toBeNull();
    }
    view.unmount();
  });

  /**
   * Landmark inflation is its own accessibility defect: a landmark list that names
   * five nested regions on one tab is no more navigable than none. API Access had
   * exactly that — a banner, two grid columns and a key list, all inside the tab's
   * own `settings-card` region. The four inner `<section>`s keep their sectioning
   * role and their `<h3>`s but no accessible name, so they are not landmarks.
   */
  it('does not inflate landmarks: the API Access tab exposes TWO regions, not six', async () => {
    const view = await openApiAccess();
    const regions = Array.from(view.container.querySelectorAll('section[aria-labelledby]'));
    // The card that names the tab, plus Quick Start — the one subsection a reader
    // navigates to directly (both jump controls and Connect an Agent point at it).
    // The banner, the two access/create columns and the key list are NOT landmarks.
    expect(regions.map((r) => r.className.split(' ').slice(-1)[0])).toEqual([
      'settings-card',
      'api-quickstart',
    ]);
    expect(keysRegion().querySelectorAll('[aria-labelledby]')).toHaveLength(0);
    // The headings survive: this is a name change, not a structure loss.
    expect(
      Array.from(keysRegion().querySelectorAll('h3')).map((h) => h.textContent),
    ).toEqual([
      API_ACCESS_COPY.statusHeading,
      'How Access Works Today',
      'Create API Key',
      'Your API Keys',
    ]);
  });

  /** No meaning is carried by colour alone: the method, the auth flag and the
   *  copy confirmation each carry their own TEXT. */
  it('conveys the HTTP method and the auth flag as text, not colour', async () => {
    await openExplorer();
    const badges = Array.from(document.querySelectorAll('.api-docs-method')).map(
      (b) => b.textContent,
    );
    expect(badges.length).toBeGreaterThan(0);
    for (const badge of badges) expect(badge).toMatch(/^(GET|POST|PUT|PATCH|DELETE)$/);
    const flag = detailPane().querySelector('.api-browser-meta-flag') as HTMLElement;
    expect(flag.textContent).toMatch(/^(401 documented|No 401 documented)$/);
  });

  it('the endpoint list keeps its roving tabindex across the tag groups', async () => {
    await openExplorer();
    const rows = () => Array.from(document.querySelectorAll('.api-browser-rowbtn')) as HTMLButtonElement[];
    expect(rows()).toHaveLength(ROWS.length);
    expect(rows().filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1);
    expect(rows()[0]).toHaveAttribute('tabindex', '0');

    fireEvent.keyDown(rows()[0], { key: 'End' });
    expect(rows()[ROWS.length - 1]).toHaveAttribute('tabindex', '0');
    expect(rows().filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1);
    // Moving the cursor across a group boundary still does not select.
    expect(rows()[0]).toHaveAttribute('aria-current', 'true');
  });

  /** The disabled Create control must be DISCOVERABLE, not just disabled: it is
   *  found by role, it is named, and its reason is both visible and associated. */
  it('the disabled Create control is discoverable and explains itself', async () => {
    await openApiAccess();
    const create = screen.getByRole('button', { name: /Create API Key/i });
    expect(create).toBeDisabled();
    expect(create.tagName).toBe('BUTTON');
    expect(create).toHaveAccessibleName('Create API Key');
    expect(create).toHaveAccessibleDescription(API_ACCESS_COPY.createDisabledReason);
  });
});

// --- the deployment condition, on every claim that needs it -------------------

/**
 * The 2026-08-08 capability audit (`docs/settings-api-capability-audit.md` §5)
 * found no false sentence on this tab and a false AFFORDANCE anyway. The
 * governing fact none of the copy carried:
 *
 *  · `ISAAC_UI_API_KEY` is unset in the deployment (`docs/deployment.md`), so
 *    `auth.py`'s middleware returns `call_next` immediately and requires the
 *    credential on ZERO operations; the edge is the sole control.
 *  · That edge answers browser sessions only — `docs/developer-guide-k8s.md`:
 *    "Scripted access (curl) to the deployed URL won't work without a browser
 *    session; test against a local run or `docker run` instead."
 *
 * So on the hosted deployment no program can call this API, with or without a
 * key. Four claims stated the unconditional half of that and the fifth
 * (Connect an Agent) gave eight steps for doing it.
 *
 * These guards pin the CONDITION, not the sentence. Each asserts both branches,
 * because the failure mode this replaces has an equal and opposite twin: the
 * API, the contract and the bearer seam are real, and a locally run deployment
 * does answer a program directly. "This API cannot be called" would be as
 * wrong as "a key would let you call it".
 */
describe('Settings → API Access — the deployment condition is carried, both ways', () => {
  const row = (term: string) => API_ACCESS_ROWS.find((r) => r.term === term)!.detail;

  /** FINDING C. */
  it('Current Access Model states BOTH branches, and neither unconditionally', async () => {
    const detail = row('Current Access Model');
    // The unconditional form is gone: "…before the app starts AND required on
    // every operation" was the exact shape that made this false in production.
    expect(detail).not.toMatch(/before the app starts and required on every operation/i);
    // Branch 1 — a deployment that sets one.
    expect(detail).toMatch(
      /sets one requires it on every operation except the liveness check/i,
    );
    // Branch 2 — a deployment that sets none. This is the deployed build.
    expect(detail).toMatch(/sets none requires it on no operation at all/i);
    // The epistemic limit was not dropped while the modality was fixed.
    expect(detail).toMatch(/this screen cannot see which/i);
    await openApiAccess();
    expect(within(keysRegion()).getByText(detail)).toBeInTheDocument();
  });

  /** FINDING A. */
  it('What an API Key Would Enable names the deployment it would NOT enable', async () => {
    const detail = row('What an API Key Would Enable');
    // The capability is still stated — this must not become a flat denial.
    expect(detail).toMatch(/could call the operations listed on the Endpoint Explorer tab/i);
    // …but no longer as the first clause of the sentence, unqualified.
    expect(detail).toMatch(/^On a deployment that answers a program directly,/);
    // And the other branch is stated, in the same row, not one component away.
    expect(detail).toMatch(/answers only browser sessions/i);
    expect(detail).toMatch(/a key would enable none of that/i);
    expect(detail).toMatch(/whether or not it carries a credential/i);
    await openApiAccess();
    expect(within(keysRegion()).getByText(detail)).toBeInTheDocument();
  });

  /** FINDING B — the precondition is INSIDE the guide it disqualifies. */
  it('Connect an Agent states the precondition before its eight steps', async () => {
    await openApiAccess();
    const connect = document.querySelector('details.api-connect') as HTMLDetailsElement;
    fireEvent.click(connect.querySelector('summary') as HTMLElement);

    const prerequisite = within(connect).getByText(API_ACCESS_COPY.connectPrerequisite);
    expect(prerequisite).toBeInTheDocument();
    // Reading order: it precedes every step, so it cannot be read as a footnote
    // to instructions already followed.
    const firstStep = connect.querySelector('.api-connect-heading') as HTMLElement;
    expect(
      prerequisite.compareDocumentPosition(firstStep) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // The disqualifying fact itself, in the guide — the audit's finding was that
    // it lived only in a sibling component this disclosure can be opened without.
    const text = norm(connect.textContent ?? '');
    expect(text).toMatch(/answers only browser sessions/i);
    expect(text).toMatch(/no agent can connect to it/i);
    // Not the inverted over-claim: the steps still apply somewhere real.
    expect(text).toMatch(/does answer a program directly, such as one run locally/i);
    // Still exactly eight sections — the precondition is a lead, not a ninth step.
    expect(connect.querySelectorAll('h4')).toHaveLength(8);
    // Said once on the tab, like every other canonical string here.
    expect(
      countOccurrences(
        norm(apiAccessPanel().textContent ?? ''),
        norm(API_ACCESS_COPY.connectPrerequisite),
      ),
    ).toBe(1);
  });

  /** FINDING D — Quick Start's auth row hedges the way the Explorer legend does. */
  it("Quick Start's authentication row no longer asserts the credential is always sent", async () => {
    await openApiAccess();
    const rows = Array.from(document.querySelectorAll('.api-quickstart-row')).map((r) =>
      norm(r.textContent ?? ''),
    );
    const auth = rows.find((r) => r.includes('Authorization: Bearer'))!;
    expect(auth).toMatch(/sent on every call that needs it — where a deployment sets one/i);
    expect(auth).toMatch(/Where none is set, no operation refuses a call for want of it/i);
    // The contract-derived count is untouched: it was always honest, because it
    // reports what the DOCUMENT says, not what a deployment does.
    expect(auth).toMatch(/\d+ of \d+ operations document a 401/);
  });

  /** FINDING E — the requirement that is not the application's to build. */
  it('Technical Requirements says the five app-owned items are not sufficient', async () => {
    await openApiAccess();
    const drawer = keysRegion().querySelector('details.api-keys-technical') as HTMLElement;
    const boundary = within(drawer).getByText(API_ACCESS_COPY.requirementsBoundary);
    expect(boundary).toBeInTheDocument();
    // It is a note, not a sixth requirement: the list is still the five
    // app-owned contracts and nothing else.
    expect(drawer.querySelectorAll('.api-keys-requirements li')).toHaveLength(
      API_KEY_REQUIREMENTS.length,
    );
    expect(API_ACCESS_COPY.requirementsBoundary).toMatch(/One requirement is not ours/i);
    expect(API_ACCESS_COPY.requirementsBoundary).toMatch(/answers only browser sessions/i);
  });

  /** The overcorrection guard. None of the five may claim the API is unusable
   *  everywhere, or that the bearer seam is fake. */
  it('never claims the API itself is unreachable or the credential mechanism unreal', async () => {
    await openApiAccess();
    const connect = document.querySelector('details.api-connect') as HTMLDetailsElement;
    fireEvent.click(connect.querySelector('summary') as HTMLElement);
    const text = norm(apiAccessPanel().textContent ?? '');
    for (const pattern of [
      /cannot be called at all/i,
      /no program can (ever )?call this API\b/i,
      /the (API|credential|bearer).{0,24}\b(is|are) (not real|fake|pretend|a placeholder)/i,
      /authentication is not implemented/i,
    ]) {
      expect(text, `overcorrected: ${pattern}`).not.toMatch(pattern);
    }
    // The conditional is genuinely conditional: the enabling branch survives.
    expect(text).toMatch(/On a deployment that answers a program directly/i);
  });

  /** Still provider-neutral after all six edits — the same withheld list the
   *  backend enforces on `GET /api/about`. Re-asserted here because every one of
   *  these fixes is about the identity layer, which is the thing this copy may
   *  never name. */
  it('names no identity product or protocol while saying all of this', async () => {
    await openApiAccess();
    const connect = document.querySelector('details.api-connect') as HTMLDetailsElement;
    fireEvent.click(connect.querySelector('summary') as HTMLElement);
    const drawer = keysRegion().querySelector('details.api-keys-technical') as HTMLElement;
    fireEvent.click(drawer.querySelector('summary') as HTMLElement);
    const lower = (apiAccessPanel().textContent ?? '').toLowerCase();
    for (const needle of [
      'authentik',
      'ingress',
      'k8s',
      'kubernetes',
      'oauth',
      'saml',
      'sso',
      'single sign-on',
      'forward auth',
    ]) {
      expect(lower.includes(needle), `named provider or protocol: ${needle}`).toBe(false);
    }
  });
});

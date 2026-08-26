import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { SettingsPage } from '../screens/SettingsPage';
import { SourcePreview } from '../components/SourcePreview';
import { aboutResponse, openApiFixture, stubFetchRoutes } from '../test/apiFixtures';
import type { ApiSourcePreview, EvidenceTrailEntry } from '../lib/types';

/**
 * FOUR RECORDED ACCESSIBILITY FINDINGS, CLOSED — A11Y-04, A11Y-05, A11Y-06 and
 * the `.section-tab` contrast item (A16 in the baseline completion matrix).
 *
 * ── WHY THESE ARE UNIT TESTS AND NOT AXE RUNS ───────────────────────────────
 *
 * The authoritative instrument for all four is the Playwright `browser-a11y`
 * job, and its numbers come from LINUX CI. This file is not a substitute for it
 * and does not claim to be. What it does is pin the PROPERTY each fix
 * establishes — a tab stop, a heading, two distinct landmark names, a token
 * whose ratio clears 4.5:1 — so that a revert fails in the fast frontend job
 * (~3 min) rather than in the ~26-minute browser job, and so that the property
 * is stated in one place rather than inferred from a node count going to zero.
 *
 * Each `it()` below was verified to FAIL on the pre-fix source. That is recorded
 * per test, with the failure it produced, because a test written after a fix and
 * never run against the defect is an assertion about nothing.
 */

afterEach(() => {
  vi.unstubAllGlobals();
});

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={FUTURE}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

function renderSettings(entry: string) {
  stubFetchRoutes({
    'GET /api/about': { body: aboutResponse },
    'GET /api/openapi': { body: openApiFixture },
  });
  return render(
    <MemoryRouter initialEntries={[entry]} future={FUTURE}>
      <SettingsPage />
    </MemoryRouter>,
  );
}

/**
 * The accessible name of a landmark, computed the two ways a landmark may get
 * one. Deliberately NOT the full accname algorithm: a landmark named by its
 * subtree text is not a case this app has, and pretending to implement the whole
 * specification would make the helper look more authoritative than it is.
 */
function landmarkName(el: Element): string {
  const label = el.getAttribute('aria-label');
  if (label !== null && label.trim() !== '') return label.trim();
  const ids = (el.getAttribute('aria-labelledby') ?? '').split(/\s+/).filter(Boolean);
  return ids
    .map((id) => el.ownerDocument.getElementById(id)?.textContent?.trim() ?? '')
    .filter(Boolean)
    .join(' ');
}

/* ── A11Y-04 · scrollable regions can be reached by keyboard ─────────────── */

const PREVIEW: ApiSourcePreview = {
  name: 'cuo_k_edge_2099.txt',
  media_type: 'text/plain',
  lines: [
    { n: 1, text: '# synthetic fixture — not a real measurement' },
    { n: 2, text: 'energy_eV,mu' },
  ] as ApiSourcePreview['lines'],
  cited_lines: [2],
};

const ENTRY: EvidenceTrailEntry = {
  key: 'measurement.series',
  label: 'Series',
  status: 'verified',
  sourceTypes: [],
  evidence: [],
  namespaced: false,
  resolved: true,
};

describe('A11Y-04 · a scrollable region a keyboard user can actually scroll', () => {
  /*
   * BEFORE: `div.preview-lines.scroll-x` was `overflow-x: auto` with every
   * `.preview-line` on `white-space: nowrap`, and had no `tabindex`. A reader
   * using only a keyboard could SEE that a source line ran past the right edge
   * and had no way to move the box: the container took no focus, so no arrow
   * key, no Home/End and no scroll gesture was available to them. A mouse or
   * trackpad was the only way to read the rest of the line.
   *
   * AFTER: the container is a focusable, named `group`, so Tab reaches it and
   * the arrow keys scroll it.
   *
   * VERIFIED TO FAIL PRE-FIX: `expected null to be '0'`.
   */
  it('the Evidence source-line viewer is focusable and named', () => {
    const { container } = render(
      <SourcePreview
        entry={ENTRY}
        provenance="synthetic fixture"
        preview={PREVIEW}
        citedLines={[2]}
        recordJson={null}
        sidecarJson={null}
      />,
    );
    const lines = container.querySelector('.preview-lines');
    expect(lines, 'the source-line viewer must render').not.toBeNull();
    expect(lines!.getAttribute('tabindex')).toBe('0');
    expect(landmarkName(lines!)).toContain(PREVIEW.name);
  });

  /*
   * The same defect on the other measured surface. `pre.api-samples-code` is
   * `overflow: auto` + `white-space: pre` with a 280px cap, so a long curl
   * command scrolls sideways and a long sample scrolls down;
   * `e2e/helpers/layout.ts` records a case showing 227px of a 2000px command.
   *
   * VERIFIED TO FAIL PRE-FIX: `expected null to be '0'`.
   */
  it('the API Access code sample is focusable and named', async () => {
    const { container } = renderSettings('/settings?tab=api');
    await waitFor(() => {
      expect(container.querySelector('pre.api-samples-code')).not.toBeNull();
    });
    const sample = container.querySelector('pre.api-samples-code')!;
    expect(sample.getAttribute('tabindex')).toBe('0');
    expect(landmarkName(sample)).not.toBe('');
  });

  /*
   * NEGATIVE CONTROL for the widening. The fix deliberately went past the two
   * elements axe had measured, to every leaf scroll container of the same shape
   * in the same two components — the `.preview-json` panes and the Endpoint
   * Explorer's JSON disclosures, which axe has never scanned because their tab
   * or `<details>` is closed during the sweep. This asserts the RULE rather than
   * the two instances, so a sixth one added later without a tab stop fails here.
   */
  it('every .scroll-x leaf in the source preview takes a tab stop', () => {
    const { container } = render(
      <SourcePreview
        entry={ENTRY}
        provenance="synthetic fixture"
        preview={PREVIEW}
        citedLines={[2]}
        recordJson={'{"synthetic": true}'}
        sidecarJson={'{"synthetic": true}'}
      />,
    );
    const scrollers = Array.from(container.querySelectorAll('.scroll-x'));
    expect(scrollers.length, 'the source tab must render its scroller').toBeGreaterThan(0);
    for (const el of scrollers) {
      expect(el.getAttribute('tabindex'), `${el.className} needs a tab stop`).toBe('0');
    }
  });
});

/* ── A11Y-05 · /load has a top-level heading ─────────────────────────────── */

describe('A11Y-05 · Load Materials has exactly one <h1>', () => {
  /*
   * BEFORE: `/load` rendered no heading of ANY level. A screen-reader user
   * landing there got an empty heading list; "go to the first heading" and the
   * `1` quick-key both did nothing, and the page announced no name of its own —
   * only the breadcrumb chrome shared with every other screen.
   *
   * AFTER: one `<h1>`, visually hidden so the on-ramp's visual design is
   * unchanged, carrying the same name the navigation uses.
   *
   * VERIFIED TO FAIL PRE-FIX: `expected [] to have a length of 1 but got +0`.
   */
  it('renders a single top-level heading naming the screen', () => {
    const { container } = renderAt('/load');
    const h1s = Array.from(container.querySelectorAll('h1'));
    expect(h1s).toHaveLength(1);
    expect(h1s[0].textContent).toBe('Load Materials');
  });

  /*
   * The heading must not be reachable ONLY by sight or ONLY by assistive
   * technology — `sr-only` hides it visually while leaving it in the
   * accessibility tree, and `display: none` / `aria-hidden` would remove it from
   * both. This pins the difference, because "add an <h1>" is satisfiable in a
   * way that closes the axe rule and helps nobody.
   */
  it('the heading is visually hidden but NOT hidden from assistive technology', () => {
    const { container } = renderAt('/load');
    const h1 = container.querySelector('h1')!;
    expect(h1.className).toContain('sr-only');
    expect(h1.getAttribute('aria-hidden')).toBeNull();
    expect(h1.hasAttribute('hidden')).toBe(false);
  });
});

/* ── A11Y-06 · the two search landmarks are told apart ───────────────────── */

describe('A11Y-06 · every role="search" landmark carries its own name', () => {
  /*
   * BEFORE: Settings → Endpoint Explorer rendered TWO `role="search"` landmarks
   * — the TopBar trigger and the endpoint filter — and NEITHER had a name. A
   * screen reader's landmark list showed "search" twice with nothing to choose
   * between them, so a reader jumping by landmark could not tell whether they
   * had arrived at the global palette or at the filter for this table. The
   * `aria-label` added for A11Y-02 does not help: it is on the `<button>`
   * INSIDE the first landmark, and a landmark is named only by a label on the
   * landmark element itself.
   *
   * AFTER: "Site search" and "Search endpoints", distinct and both non-empty.
   *
   * VERIFIED TO FAIL PRE-FIX: `expected [ '', '' ] not to contain ''`.
   */
  it('the Endpoint Explorer has two search landmarks with distinct names', async () => {
    const { container } = renderSettings('/settings?tab=explorer');
    await waitFor(() => {
      expect(container.querySelectorAll('[role="search"]').length).toBe(2);
    });
    const names = Array.from(container.querySelectorAll('[role="search"]')).map(landmarkName);
    expect(names, 'an unnamed landmark is indistinguishable in a landmark list').not.toContain('');
    expect(new Set(names).size, `two landmarks share the name ${names[0]}`).toBe(names.length);
  });

  /*
   * THE LANDMARK'S NAME IS ITS OWN, AND NOT THE INPUT'S.
   *
   * The first version of the fix pointed `aria-labelledby` at the visible
   * "Search endpoints" label, on the reasoning that reusing the copy leaves one
   * string to keep true. It made that one string the accessible name of the
   * region AND of the text box inside it, so every name-based lookup resolved to
   * both — three existing tests failed with `Found multiple elements with the
   * text of: Search endpoints`, and a reader searching by name would have hit
   * the same ambiguity. This pins the corrected shape so the tidier-looking
   * version cannot come back.
   */
  it('the filter landmark is named separately from the input inside it', async () => {
    const { container, getByLabelText } = renderSettings('/settings?tab=explorer');
    await waitFor(() => {
      expect(container.querySelector('.settings-search')).not.toBeNull();
    });
    const region = container.querySelector('.settings-search')!;
    expect(region.getAttribute('aria-labelledby')).toBeNull();
    expect(landmarkName(region)).toBe('Endpoint search');
    // "Search endpoints" still resolves to exactly one thing: the text box.
    expect((getByLabelText('Search endpoints') as HTMLElement).tagName).toBe('INPUT');
  });
});

/* ── A16 · the inactive section tab clears WCAG 1.4.3 ────────────────────── */

/*
 * WCAG 2.x relative luminance and contrast ratio. Same six lines as
 * `stats-charts.test.tsx` uses; duplicated rather than shared because the two
 * files test unrelated surfaces and a shared helper module for eight lines would
 * be the worse trade. Reproduces the two figures this repository already
 * records: #78838f on #ffffff = 3.86:1, #5b6570 on #ffffff = 5.93:1.
 */
const srgbOf = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
const luminance = (hex: string) =>
  srgbOf(hex)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    .reduce((acc, c, i) => acc + [0.2126, 0.7152, 0.0722][i] * c, 0);
const contrastRatio = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** A stylesheet with comments stripped, so prose can never satisfy a guard. */
function sheet(endsWith: string): string {
  const found = Object.entries(cssFiles).find(([path]) => path.endsWith(endsWith));
  if (!found) throw new Error(`no stylesheet ending ${endsWith}`);
  return found[1].replace(/\/\*[\s\S]*?\*\//g, '');
}

function declaredHex(token: string): string {
  const found = new RegExp(`${token}\\s*:\\s*(#[0-9a-fA-F]{6})`).exec(sheet('/tokens.css'));
  if (!found) throw new Error(`${token} is not declared as a 6-digit hex`);
  return found[1].toLowerCase();
}

/** The `color:` token of a top-level rule whose selector list contains `selector`. */
function colorTokenOf(selector: string, sheetName: string): string {
  const topLevel = sheet(sheetName).replace(
    /@[a-zA-Z-]+[^{]*\{(?:[^{}]*\{[^{}]*\})*\s*\}/g,
    '',
  );
  const want = selector.replace(/\s+/g, ' ').trim();
  const block = [...topLevel.matchAll(/([^{}]+)\{([^{}]*)\}/g)].find((m) =>
    m[1].split(',').some((s) => s.replace(/\s+/g, ' ').trim() === want),
  );
  if (!block) throw new Error(`no top-level rule for ${selector}`);
  const token = /(?:^|[\s;])color\s*:\s*var\((--[a-z-]+)\)/.exec(block[2]);
  if (!token) throw new Error(`${selector} declares no color token`);
  return token[1];
}

describe('A16 · the inactive .section-tab label clears 4.5:1', () => {
  /*
   * BEFORE: `.section-tab` painted every UNSELECTED tab label at
   * `--text-tertiary` #78838f, 12.5px/500. That is 3.86:1 on the white card —
   * below the 4.5:1 WCAG 1.4.3 requires under 18.66px bold. On the seven-tab
   * Settings strip, the Evidence list/graph strip, Record Detail and Statistics,
   * every tab a reader had NOT selected was the hardest text on the screen to
   * read, which is precisely backwards: the unselected tabs are the ones you are
   * scanning to decide where to go.
   *
   * AFTER: `--text-muted` #5b6570, 5.93:1 on the same ground.
   *
   * THE TOKEN'S VALUE IS UNCHANGED. `styles/tokens.css:3-5` forbids editing
   * values there, and A3 — the app-wide 1,610-node contrast failure, five of
   * whose cases are `opacity` composites that darkening cannot fix — needs a
   * palette decision that is the owner's, not a slice's. Only the token this one
   * component ASKS FOR changed.
   *
   * VERIFIED TO FAIL PRE-FIX: `.section-tab uses --text-tertiary #78838f, which
   * is 3.86:1 on #ffffff`.
   */
  it('is painted with a token that passes on every ground it sits on', () => {
    const token = colorTokenOf('.section-tab', '/screens.css');
    const fg = declaredHex(token);
    // The three card/screen grounds a `.section-tabs` strip is drawn on.
    for (const bg of ['--surface', '--surface-subtle', '--screen-base'].map(declaredHex)) {
      const ratio = contrastRatio(fg, bg);
      expect(
        ratio,
        `.section-tab uses ${token} ${fg}, which is ${ratio.toFixed(2)}:1 on ${bg} — ` +
          `below the 4.5:1 WCAG 1.4.3 requires for text under 18.66px bold`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  /*
   * VACUITY GUARD. The test above is only meaningful if the ratio it computes
   * can fail, and if the size threshold it invokes actually applies. Both are
   * asserted here from the stylesheet rather than assumed: the old token really
   * does fail, and `.section-tab` really is below the WCAG large-text boundary,
   * so 4.5:1 and not 3:1 is the right bar.
   */
  it('the discarded token really did fail, and the size threshold really applies', () => {
    expect(contrastRatio(declaredHex('--text-tertiary'), declaredHex('--surface'))).toBeLessThan(
      4.5,
    );
    const block = /\.section-tab\s*\{([^}]*)\}/.exec(sheet('/screens.css'))![1];
    const size = Number(/font-size:\s*([\d.]+)px/.exec(block)![1]);
    const weight = Number(/font-weight:\s*(\d+)/.exec(block)![1]);
    expect(size).toBeLessThan(18.66);
    expect(weight).toBeLessThan(700);
  });
});

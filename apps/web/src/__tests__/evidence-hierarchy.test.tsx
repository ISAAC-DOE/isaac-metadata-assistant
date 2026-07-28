/*
 * P36V1 — Slice 6 (shared top content gutter) + Slice 7 (Evidence readability
 * and hierarchy).
 *
 * S6 defect: `.screen-main` had no top padding and only `.screen-main.pad` got
 * any (22px). EvidenceExplorer's LOADED branch is the single `mainPad="none"`
 * mount in the app, so its WorkflowProgressBanner sat flush against the 60px
 * TopBar — while the SAME file's loading / no-evidence branches (`mainPad="pad"`)
 * got 22px. The fix is a shared shell token, `--main-top-gutter`, consumed once
 * by each of the three padding presets — NOT a margin bolted onto one banner.
 *
 * S7 defect: the Evidence Support panel was a single field of 12–12.5px gray —
 * the section heading (15px) barely outranked the row text, the counts were
 * quieter than their own labels, and the info control was an invisible glyph.
 *
 * HONESTY NOTE, read before adding to this file: jsdom applies NO layout and no
 * stylesheet cascade. Nothing here measures a rendered pixel, and no test below
 * claims to. Each assertion is one of exactly two kinds, and its name says which:
 *   - "CSS source:" — a declaration read out of the stylesheet with ?raw (the
 *     same idiom as no-vertical-rail.test.ts / layout-width-modes.test.tsx).
 *     It proves the rule is WRITTEN, not that it renders.
 *   - everything else — a DOM/behaviour assertion against what React renders.
 * The two are paired deliberately: the CSS side pins the declaration, the DOM
 * side pins that the element the selector targets is actually produced.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { EvidenceClassificationPanel } from '../components/EvidenceClassificationPanel';
import {
  bundleRoutes,
  evidenceBundleRoutes,
  evidenceClassificationResponse,
  exportReadyRoutes,
  stubFetchRoutes,
} from '../test/apiFixtures';

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const cssByName = (name: string): string =>
  Object.entries(cssFiles).find(([path]) => path.endsWith(`/${name}`))?.[1] ?? '';

/** Strip comments so a guard can never be satisfied by prose quoting a rule. */
const stripComments = (source: string): string => source.replace(/\/\*[\s\S]*?\*\//g, '');

const squash = (source: string): string => stripComments(source).replace(/\s+/g, ' ');

/** Flat {selector, body} rules; at-rule wrappers are stepped over so rules
 *  INSIDE `@media` blocks are yielded too. */
function cssRules(source: string): { selector: string; body: string }[] {
  return [...stripComments(source).matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim(),
    body: m[2],
  }));
}

const ruleFor = (file: string, selector: string) =>
  cssRules(cssByName(file)).find((r) => r.selector === selector);

const px = (body: string | undefined, prop: string): number | undefined => {
  const m = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*(-?[\\d.]+)px`).exec(body ?? '');
  return m ? Number(m[1]) : undefined;
};

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

afterEach(() => {
  vi.unstubAllGlobals();
});

// ===========================================================================
// SLICE 6 — the shared top content gutter
// ===========================================================================

describe('S6 · CSS source: the top gutter is ONE shared shell token', () => {
  const chrome = cssByName('chrome.css');
  const chromeFlat = squash(chrome);

  it('CSS source: --main-top-gutter is declared on .screen-main at a desktop value of 24–32px', () => {
    const main = ruleFor('chrome.css', '.screen-main');
    expect(main, 'chrome.css must declare .screen-main').toBeDefined();
    const value = px(main?.body, '--main-top-gutter');
    expect(value, '--main-top-gutter must be declared on .screen-main itself').toBeDefined();
    expect(value!).toBeGreaterThanOrEqual(24);
    expect(value!).toBeLessThanOrEqual(32);
  });

  /*
   * The whole point of the slice: three padding presets, ONE answer. A preset
   * that hard-coded its own literal again would reintroduce exactly the
   * inconsistency this fixed, and would pass a test that only checked the token
   * exists somewhere.
   */
  it('CSS source: every mainPad preset takes its top gutter from that token', () => {
    // pad  → main's own padding-top (first value of the 3-value shorthand)
    expect(chromeFlat).toContain(
      '.screen-main.pad { padding: var(--main-top-gutter) var(--main-gutter) 22px; }',
    );
    // none → the :not() rule; this is the mount that had NO gutter at all
    expect(chromeFlat).toContain(
      '.screen-main:not(.pad):not(.centered) { padding-top: var(--main-top-gutter); }',
    );
    // centered → the column owns it, because <main> is the flex CONTAINER there
    expect(chromeFlat).toContain('padding: var(--main-top-gutter) var(--main-gutter) 24px;');
  });

  /*
   * No-double-gutter guard. `.screen-main.centered` must NOT also carry a
   * padding-top, or the New Record / Guided Completion screens would get the
   * gutter twice (once on main, once on `.centered-col`).
   */
  it('CSS source: .screen-main.centered adds no padding of its own (the column owns it)', () => {
    const centered = ruleFor('chrome.css', '.screen-main.centered');
    expect(centered).toBeDefined();
    expect(centered!.body).not.toMatch(/padding/);
  });

  it('CSS source: responsive equivalents redeclare the SAME token, smaller, at ≤1024px and ≤640px', () => {
    const declarations = cssRules(chrome)
      .filter((r) => r.selector === '.screen-main')
      .map((r) => px(r.body, '--main-top-gutter'))
      .filter((v): v is number => v !== undefined);
    // desktop + two narrower breakpoints, monotonically decreasing
    expect(declarations.length).toBe(3);
    expect(declarations[0]).toBeGreaterThan(declarations[1]);
    expect(declarations[1]).toBeGreaterThan(declarations[2]);
    // never collapses to nothing on a phone
    expect(declarations[2]).toBeGreaterThanOrEqual(12);
  });
});

describe('S6 · CSS source: the horizontal inset is shared and does not double up', () => {
  it('CSS source: .main-inset lives in the SHELL stylesheet and sets no vertical margin', () => {
    const inset = ruleFor('chrome.css', '.main-inset');
    expect(inset, '.main-inset must be declared in chrome.css, not per-component').toBeDefined();
    // exactly `margin: 0 <n>px` — a top margin here would be a second gutter
    expect(inset!.body).toMatch(/margin\s*:\s*0\s+\d+px\s*;/);
  });

  /*
   * `.main-inset` (the banner/notice wrapper) and `.evclass` (the first panel
   * below it) must agree, or the banner would visibly step in or out relative
   * to the stack beneath it. Asserted as an EQUALITY rather than two literals,
   * so changing one alone fails here instead of only in a screenshot.
   */
  it('CSS source: .main-inset margin matches the evidence panel inset, so the stack lines up', () => {
    const insetX = Number(/margin\s*:\s*0\s+(\d+)px/.exec(ruleFor('chrome.css', '.main-inset')!.body)![1]);
    const panel = ruleFor('classification.css', '.evclass')!.body;
    const panelX = Number(/padding\s*:\s*[\d.]+(?:px)?\s+(\d+)px/.exec(panel)![1]);
    expect(insetX).toBe(panelX);
  });

  it('CSS source: the one-off .wf-progress-banner-inset is gone from every stylesheet and every screen', () => {
    const offenders = Object.entries(cssFiles)
      .filter(([, source]) => stripComments(source).includes('.wf-progress-banner-inset'))
      .map(([path]) => path);
    expect(offenders, `orphaned one-off inset class:\n${offenders.join('\n')}`).toEqual([]);

    const tsx = import.meta.glob('../**/*.tsx', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>;
    const users = Object.entries(tsx)
      .filter(([, source]) => source.includes('wf-progress-banner-inset'))
      .map(([path]) => path);
    expect(users).toEqual([]);
  });

  it('CSS source: the banner itself declares no top margin (the shell owns that distance)', () => {
    const banner = ruleFor('workflow-progress-banner.css', '.wf-progress-banner');
    expect(banner).toBeDefined();
    expect(banner!.body).not.toMatch(/margin-top\s*:/);
    // and its shorthand margin only ever sets the bottom
    expect(banner!.body).toMatch(/margin-bottom\s*:/);
  });
});

describe('S6 · the Evidence LOADED branch actually receives the shared gutter', () => {
  /*
   * Asserted as the exact COMPOUND the stylesheet is written against
   * (`.screen-main:not(.pad):not(.centered)`) rather than "has no .pad class":
   * if the preset-to-class mapping in AppShell ever changed, a looser assertion
   * would still pass while the declaration silently stopped matching.
   */
  it('renders <main> as main.screen-main:not(.pad):not(.centered) — the selector the gutter rule targets', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/evidence');
    await findByText('Evidence Support'); // the LOADED branch, not the fallback

    expect(
      container.querySelector('main.screen-main:not(.pad):not(.centered)'),
      'the loaded evidence <main> must match the gutter rule in chrome.css',
    ).not.toBeNull();
  });

  it('the same file’s fallback branch uses the padded preset — one page, one contract', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    const { container, getByRole } = renderAt('/record/demo/evidence');
    expect(getByRole('status')).toBeInTheDocument(); // LoadingPanel — the fallback branch
    expect(container.querySelector('main.screen-main.pad')).not.toBeNull();
  });

  /*
   * Source-level audit of the ONE screen that owns three shells. A DOM test
   * cannot reach the no-evidence branch without a bespoke fixture, and a screen
   * that simply omitted `mainPad` would silently fall back to the default —
   * which is exactly the unpadded preset. Every branch must state its preset.
   */
  it('source: all three EvidenceExplorer shells declare a preset explicitly', () => {
    const tsx = import.meta.glob('../screens/EvidenceExplorer.tsx', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>;
    const source = Object.values(tsx)[0] ?? '';
    expect(source, 'EvidenceExplorer.tsx must be readable').not.toBe('');

    const shells = source.match(/<AppShell/g) ?? [];
    const presets = source.match(/mainPad="(?:pad|centered|none)"/g) ?? [];
    expect(shells.length, 'loading/error + no-evidence + loaded').toBe(3);
    expect(presets.length).toBe(shells.length);
    expect(presets.filter((p) => p.includes('"pad"')).length).toBe(2);
    expect(presets.filter((p) => p.includes('"none"')).length).toBe(1);
  });

  /*
   * Cross-check on the other record-workflow surfaces: each lands on exactly
   * one preset, asserted on the LOADED shell (the StatusBar and
   * `.centered-col.narrow` exist only there — the same waits
   * layout-width-modes.test.tsx uses).
   */
  it('Export Readiness lands on the padded preset', async () => {
    stubFetchRoutes(exportReadyRoutes('demo'));
    const { container } = renderAt('/record/demo/export');
    await waitFor(() => expect(container.querySelector('.statusbar')).not.toBeNull());
    const main = container.querySelector('main')!;
    expect(main.classList.contains('pad')).toBe(true);
    expect(main.classList.contains('centered')).toBe(false);
  });

  it('Guided Completion lands on the centered preset, where the column owns the gutter', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container } = renderAt('/record/demo/complete');
    await waitFor(() => expect(container.querySelector('.centered-col.narrow')).not.toBeNull());
    const main = container.querySelector('main')!;
    expect(main.classList.contains('centered')).toBe(true);
    expect(main.classList.contains('pad')).toBe(false);
  });
});

describe('S6 · no double margin when the banner and the live-sync note are absent', () => {
  it('mounts ONE shared inset wrapper holding both transient notices', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/evidence');
    await findByText('Evidence Support');

    const insets = container.querySelectorAll('main > .main-inset');
    expect(insets.length, 'exactly one inset wrapper, shared by both notices').toBe(1);
  });

  /*
   * The three first-child states in the brief (live-sync note / banner /
   * `.evclass`) are all handled by the SAME structure, which is what makes the
   * no-double-gutter property fixture-independent: the wrapper holds only the
   * two transient notices, both of which render null when they have nothing to
   * say, and it carries no vertical margin (asserted in CSS source above). So
   * whichever combination is live, exactly one gutter — main's padding-top —
   * separates the TopBar from the first thing with content.
   */
  it('the wrapper holds only the two transient notices, and `.evclass` follows it directly', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/evidence');
    await findByText('Evidence Support');

    const inset = container.querySelector('main > .main-inset')!;
    for (const child of Array.from(inset.children)) {
      expect(
        child.classList.contains('livesync-degraded') ||
          child.classList.contains('wf-progress-banner'),
        `unexpected child in the inset wrapper: ${child.className}`,
      ).toBe(true);
    }
    // nothing sits between the wrapper and the first panel
    expect(inset.nextElementSibling?.classList.contains('evclass')).toBe(true);
  });

  it('CSS source: .evclass declares no top padding, so it never stacks a second gutter', () => {
    const evclass = ruleFor('classification.css', '.evclass')!;
    // 3-value shorthand whose FIRST value (top) is 0
    expect(evclass.body).toMatch(/padding\s*:\s*0\s+\d+px\s+\d+px\s*;/);
    expect(evclass.body).not.toMatch(/padding-top\s*:/);
  });
});

// ===========================================================================
// SLICE 7 — readability and hierarchy
// ===========================================================================

const panel = (stale = false) =>
  render(
    <EvidenceClassificationPanel
      classification={evidenceClassificationResponse}
      stale={stale}
      onRefresh={() => {}}
    />,
  );

describe('S7 · CSS source: four distinguishable levels of typographic hierarchy', () => {
  const sizeOf = (selector: string) => px(ruleFor('classification.css', selector)?.body, 'font-size');
  const weightOf = (selector: string) =>
    Number(/font-weight\s*:\s*(\d+)/.exec(ruleFor('classification.css', selector)?.body ?? '')?.[1]);

  it('CSS source: the section heading is 20–24px and semibold-or-bolder', () => {
    expect(sizeOf('.evclass-title')!).toBeGreaterThanOrEqual(20);
    expect(sizeOf('.evclass-title')!).toBeLessThanOrEqual(24);
    expect(weightOf('.evclass-title')).toBeGreaterThanOrEqual(600);
    expect(ruleFor('classification.css', '.evclass-title')!.body).toContain(
      'color: var(--text-heading)',
    );
  });

  it('CSS source: heading > note > row text, and the heading has clear bottom spacing', () => {
    const title = sizeOf('.evclass-title')!;
    const note = sizeOf('.evclass-note')!;
    const explanation = sizeOf('.evclass-explanation')!;
    expect(title).toBeGreaterThan(note);
    expect(note).toBeLessThanOrEqual(explanation); // note is supporting, not body-dominant
    expect(px(ruleFor('classification.css', '.evclass-head')?.body, 'margin-bottom')!)
      .toBeGreaterThanOrEqual(14);
  });

  it('CSS source: the note keeps a readable measure and a comfortable line height', () => {
    const body = ruleFor('classification.css', '.evclass-note')!.body;
    expect(body).toMatch(/max-width\s*:\s*\d+ch/);
    expect(Number(/line-height\s*:\s*([\d.]+)/.exec(body)![1])).toBeGreaterThanOrEqual(1.5);
  });

  /*
   * Contrast, stated honestly: jsdom computes nothing, so this checks the
   * COLOR ROLE, not a measured ratio. The panel's body text must not sit on the
   * two faintest ink tokens — that (12px --text-tertiary everywhere) was the
   * "it all blends together" defect.
   */
  it('CSS source: no panel text uses the two faintest ink tokens', () => {
    const faint = /color\s*:\s*var\(--text-(?:quaternary|faint|disabled)\)/;
    const offenders = cssRules(cssByName('classification.css'))
      .filter((r) => faint.test(r.body))
      .map((r) => r.selector);
    expect(offenders, `faint ink in the Evidence panel:\n${offenders.join('\n')}`).toEqual([]);
  });
});

describe('S7 · the status summary reads as counts of semantic statuses', () => {
  it('CSS source: the count badge is heavier and darker than the chip label beside it', () => {
    const count = ruleFor('classification.css', '.evclass-count-n')!.body;
    const chip = ruleFor('signals.css', '.chip')!.body;
    const countWeight = Number(/font-weight\s*:\s*(\d+)/.exec(count)![1]);
    const chipWeight = Number(/font-weight\s*:\s*(\d+)/.exec(chip)![1]);
    expect(countWeight).toBeGreaterThan(chipWeight);
    expect(count).toContain('color: var(--text-heading)');
    // tabular figures so a row of badges aligns
    expect(count).toMatch(/font-variant-numeric\s*:\s*tabular-nums/);
  });

  it('every summary entry pairs a semantic chip with its own count', () => {
    const { container } = panel();
    const entries = container.querySelectorAll('.evclass-summary .evclass-count');
    expect(entries.length).toBeGreaterThan(0);
    entries.forEach((entry) => {
      expect(entry.querySelector('.chip'), 'chip carries the semantics').not.toBeNull();
      expect(entry.querySelector('.evclass-count-n')?.textContent).toMatch(/^\d+$/);
    });
  });

  it('announces a noun for the count without repeating a visible word per pill', () => {
    const { container } = panel();
    const first = container.querySelector('.evclass-summary .evclass-count')!;
    const hidden = first.querySelector('.sr-only');
    expect(hidden?.textContent).toMatch(/^fields?$/);
    // it is screen-reader-only, so the visible pill stays "chip + number"
    expect(hidden?.className).toBe('sr-only');
  });
});

describe('S7 · classification semantics are PRESERVED (presentation-only slice)', () => {
  /*
   * The chip palette + the dashed-border convention are the load-bearing part:
   * an inferred candidate and an unknown must never be able to read as an
   * established fact. This slice restyled everything AROUND them; these guards
   * fail if a future "polish" pass flattens them.
   */
  it.each([
    ['supported', 'chip-ev-supported', 'Supported'],
    ['inferred_candidate', 'chip-ev-candidate', 'Inferred Candidate'],
    ['insufficient_evidence', 'chip-ev-insufficient', 'Insufficient Evidence'],
    ['conflicting_evidence', 'chip-ev-conflicting', 'Conflicting Evidence'],
    ['unknown', 'chip-ev-unknown', 'Unknown'],
  ])('%s → .%s, labelled "%s", icon + text (never colour alone)', (cls, chipClass, label) => {
    const { container } = panel();
    const row = container.querySelector(`.evclass-row[data-class="${cls}"]`)!;
    expect(row, `a row for ${cls} must render`).not.toBeNull();
    const chip = row.querySelector('.chip')!;
    expect(chip.className).toContain(chipClass);
    expect(chip.textContent).toContain(label);
    expect(chip.querySelector('svg'), 'icon present — the signal is never colour alone').not.toBeNull();
  });

  it.each([
    ['chip-ev-candidate', true],
    ['chip-ev-unknown', true],
    ['chip-ev-supported', false],
    ['chip-ev-insufficient', false],
    ['chip-ev-conflicting', false],
  ])('CSS source: .%s dashed-border convention === %s', (chipClass, dashed) => {
    const rule = ruleFor('signals.css', `.${chipClass}`);
    expect(rule, `signals.css must declare .${chipClass}`).toBeDefined();
    expect(/border-style\s*:\s*dashed/.test(rule!.body)).toBe(dashed);
  });

  /*
   * CLASS_ORDER is severity-first and is a SEMANTIC choice, not styling — this
   * slice must not have reordered it. Asserted as a subsequence so the guard
   * holds for any fixture (a class with a zero count is filtered out of the
   * summary), while still failing if two classes swap places.
   */
  it('keeps the severity-first display order (highest concern first)', () => {
    const { container } = panel();
    const severityFirst = [
      'Conflicting Evidence',
      'Insufficient Evidence',
      'Inferred Candidate',
      'Unknown',
      'Supported',
    ];
    const rendered = [...container.querySelectorAll('.evclass-summary .evclass-count .chip')].map(
      (c) => (c.textContent ?? '').trim(),
    );
    expect(rendered.length).toBeGreaterThan(1);
    expect(rendered).toEqual(severityFirst.filter((label) => rendered.includes(label)));
  });
});

describe('S7 · field rows separate path · status · explanation · source', () => {
  it('CSS source: the field path is a distinct, heavier level than the explanation', () => {
    const field = ruleFor('classification.css', '.evclass-field')!.body;
    const explanation = ruleFor('classification.css', '.evclass-explanation')!.body;
    expect(Number(/font-weight\s*:\s*(\d+)/.exec(field)![1])).toBeGreaterThanOrEqual(600);
    expect(field).toContain('color: var(--text-heading)');
    expect(explanation).toContain('color: var(--text-secondary)');
    expect(/font-weight/.test(explanation), 'the explanation stays normal body text').toBe(false);
  });

  it('renders all four parts in one row, in order', () => {
    const { container } = panel();
    const row = container.querySelector('.evclass-row[data-class="supported"]')!;
    expect(row.querySelector('.evclass-field')?.textContent).toBeTruthy();
    expect(row.querySelector('.chip')).not.toBeNull();
    expect(row.querySelector('.evclass-explanation')?.textContent).toBeTruthy();
    expect(row.querySelector('.evclass-source')).not.toBeNull();
  });

  it('CSS source: the source reference is a readable single chip, not a nested box', () => {
    const source = ruleFor('classification.css', '.evclass-row .evclass-source')!.body;
    // restrained blue: the app's existing selected-row tint + selected border
    expect(source).toContain('background: var(--selected-row-bg)');
    expect(source).toContain('border: 1px solid var(--action-selected-border)');
    // the inner source-type token drops its own box so the two never nest…
    const inner = ruleFor('classification.css', '.evclass-row .evclass-source .src-token')!.body;
    expect(inner).toMatch(/border\s*:\s*0/);
    // …and is bumped above the 10.5px it inherited from .src-token
    expect(px(inner, 'font-size')!).toBeGreaterThan(
      px(ruleFor('evidence.css', '.src-token')?.body, 'font-size')!,
    );
    // the locator is the readable blue half of the chip
    expect(ruleFor('classification.css', '.evclass-locator')!.body).toContain(
      'color: var(--action-hover)',
    );
  });

  it('renders each source as ONE chip containing its type token and locator', () => {
    const { container } = panel();
    const source = container.querySelector('.evclass-source')!;
    expect(source.querySelector('.src-token')).not.toBeNull();
    expect(source.querySelector('.src-token svg'), 'source type is icon + text').not.toBeNull();
  });
});

describe('S7 · the info control is visibly interactive and accessible', () => {
  const btn = ruleFor('classification.css', '.evclass-info-btn')!.body;

  it('CSS source: resting state is an outlined ISAAC-blue control, not a faint glyph', () => {
    expect(btn).toContain('color: var(--action)');
    expect(btn).toMatch(/border\s*:\s*1px solid var\(--border-input\)/);
    expect(btn).toContain('background: var(--surface)');
    expect(btn).toContain('cursor: pointer');
  });

  it.each([
    [':hover', /background:\s*var\(--action-tint\)/],
    [':active', /background:\s*var\(--action-selected-border\)/],
    [':focus-visible', /outline:\s*2px solid var\(--action\)/],
    ["[aria-expanded='true']", /border-color:\s*var\(--action\)/],
  ])('CSS source: .evclass-info-btn%s has a distinct treatment', (state, pattern) => {
    const rule = ruleFor('classification.css', `.evclass-info-btn${state}`);
    expect(rule, `.evclass-info-btn${state} must be declared`).toBeDefined();
    expect(rule!.body).toMatch(pattern);
  });

  it('CSS source: its transition is disabled under prefers-reduced-motion', () => {
    const reduced = squash(cssByName('classification.css')).match(
      /@media \(prefers-reduced-motion: reduce\) \{([\s\S]*?)\}\s*\}/,
    );
    expect(reduced, 'a reduced-motion block must exist').not.toBeNull();
    expect(reduced![1]).toContain('.evclass-info-btn');
    expect(reduced![1]).toContain('transition: none');
  });

  it('is a real button that toggles guidance and exposes the state non-visually', () => {
    const { container } = panel();
    const button = container.querySelector<HTMLButtonElement>('.evclass-info-btn')!;
    expect(button.tagName).toBe('BUTTON');
    button.focus();
    expect(document.activeElement).toBe(button);
    expect(button.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(button);
    // the CSS keys its held state off exactly this attribute
    expect(button.matches("[aria-expanded='true']")).toBe(true);
    expect(container.querySelector('.evclass-info')).not.toBeNull();
  });
});

describe('S7 · overflow, wrapping and heading structure', () => {
  it('CSS source: long field paths and locators wrap instead of widening the page', () => {
    for (const selector of ['.evclass-field', '.evclass-locator']) {
      const body = ruleFor('classification.css', selector)!.body;
      expect(body, `${selector} must wrap`).toContain('overflow-wrap: anywhere');
      expect(body, `${selector} must be shrinkable inside its flex row`).toContain('min-width: 0');
      // break-all splits mid-token even when unnecessary — replaced deliberately
      expect(body).not.toMatch(/word-break\s*:\s*break-all/);
    }
  });

  it('CSS source: a narrow-viewport rule exists and tracks the shell inset', () => {
    const narrow = cssRules(cssByName('classification.css')).find((r) => r.selector === '.evclass' && /14px/.test(r.body));
    expect(narrow, 'classification.css must re-inset .evclass at ≤640px').toBeDefined();
    expect(squash(cssByName('classification.css'))).toContain('@media (max-width: 640px)');
  });

  /*
   * 200%-zoom-relevant STRUCTURE (not a measurement — jsdom has no layout):
   * nothing in the panel pins a height or forces a single line, so the content
   * reflows rather than clipping when text doubles in size.
   */
  it('CSS source: no fixed height or nowrap anywhere in the panel (reflow, never clip)', () => {
    const offenders = cssRules(cssByName('classification.css'))
      .filter((r) => /(?:^|;)\s*(?:height|max-height)\s*:\s*\d/.test(r.body) || /white-space\s*:\s*nowrap/.test(r.body))
      // the 26px round info button is intentionally a fixed square icon target
      .filter((r) => !r.selector.startsWith('.evclass-info-btn'))
      .map((r) => r.selector);
    expect(offenders, `fixed sizing blocks reflow:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('keeps the sr-only <h1> as the only h1, with Evidence Support as an h2 beneath it', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/evidence');
    await findByText('Evidence Support');

    expect(container.querySelectorAll('h1').length).toBe(1);
    expect(container.querySelector('h1')!.className).toBe('sr-only');
    const h2 = [...container.querySelectorAll('h2')].find(
      (h) => h.textContent === 'Evidence Support',
    );
    expect(h2, 'the section heading must stay an h2 — no second h1').toBeDefined();
    expect(h2!.className).toBe('evclass-title');
  });

  /*
   * Copy discipline: the "separate axis" framing belongs to the panel note, at
   * page level. Scoped to `.evclass` rather than the whole document so this
   * stays a statement about THIS panel and is not coupled to unrelated copy
   * elsewhere on the screen.
   */
  it('says "a separate axis" once, in the page-level note — never repeated per row', () => {
    const { container } = panel();
    const scope = container.querySelector('.evclass')!;
    const occurrences = (scope.textContent ?? '').match(/a separate axis/g) ?? [];
    expect(occurrences.length).toBe(1);
    expect(container.querySelector('.evclass-note')!.textContent).toContain('a separate axis');
    container.querySelectorAll('.evclass-row').forEach((row) => {
      expect(row.textContent).not.toContain('a separate axis');
    });
  });
});

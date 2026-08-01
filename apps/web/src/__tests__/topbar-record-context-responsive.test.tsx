/*
 * C1 (top-bar occlusion on record sub-routes) + I4 (the record title was not
 * rendered at all at phone width).
 *
 * THE MEASURED DEFECT, at 375x812 in Chromium against the production build —
 * every number below was read off the running app, none is inferred:
 *
 *   · `.record-context` was allotted 69px (the whole remainder of the bar after
 *     brand 82.6 + search 36 + mode chip 105.3 + gaps) and is `overflow:
 *     visible`, so its children painted OUTSIDE it: `.record-surface` ran
 *     143.6→302.9 and `span.chip.chip-draft` ran to 386.4 — past the 375px
 *     viewport. `document.elementFromPoint` sampled across the leaf crumb at
 *     0.1/0.3/0.5/0.7/0.9 returned span.record-surface, span.record-surface,
 *     svg, span.mode-chip, span.mode-chip: 3 of 5 points were genuinely
 *     occluded, i.e. crumb text was painting over the mode chip.
 *   · `.record-title` had clientWidth 0 against scrollWidth 395 (evidence /
 *     complete) or 250 (record detail). At clientWidth 0 Chromium paints zero
 *     glyphs — not even the ellipsis — so the record title was invisible.
 *
 * AFTER, same viewport and build: `.record-context` 23→352 (w 329,
 * `overflow: hidden`, zero overhanging children), `.record-title` clientWidth
 * 329 / scrollWidth 395 with all 5 sample points hitting the title itself,
 * `.record-surface` 23→164.7 with all 5 points hitting itself, and no topbar
 * control covered or outside the viewport. 320x568 behaves the same (context
 * w 274).
 *
 * WHY THE LEAF CRUMB IS NOT SIMPLY HIDDEN. It does not duplicate a visible page
 * heading: measured, the page's own <h1> on /evidence, /export and /record is
 * `h1.sr-only` (clientWidth 1). Hiding the crumb would delete the surface name
 * from every VISIBLE location, so it is stacked and de-emphasised instead.
 *
 * THE BAND IS ≤1024px, NOT ≤640px. Scoping the treatment to phone widths left
 * 641–1024 uncovered, and the defect is fully alive there. Measured at 768 on
 * the same build, BEFORE this correction:
 *     /evidence   title clientWidth   0 / scrollWidth 395   ctx 350/455 (overflows)
 *                 plus `span.record-file` hanging 105.3px past the context
 *     /complete   title   0/395   ctx 350/377, file +26.8
 *     /export     title  28/422   — below the 40px critical-fragment threshold
 *     /record     title  70/250
 * AFTER: 710/710 on all four at 768, and 966/966 at 1024 (it was 141/395 there).
 * One row cannot hold this crumb at 768: its content demands ~792px of a 350px
 * box. Non-record surfaces are unaffected — their bar still measures exactly
 * 60px at 768, 1024 and 1280, because their content fits one row.
 *
 * HONESTY NOTE. jsdom applies no layout and evaluates no media query, so nothing
 * here measures a pixel and no assertion below claims to. Each test is either
 * "CSS source:" (the declaration is read out of the stylesheet with ?raw — it
 * proves the rule is WRITTEN) or a DOM assertion about what React renders. The
 * geometry above is the browser evidence; these tests are the regression lock.
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { TopBar } from '../components/TopBar';

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const cssByName = (name: string): string =>
  Object.entries(cssFiles).find(([path]) => path.endsWith(`/${name}`))?.[1] ?? '';

/** Comments are stripped first, so no guard can ever be satisfied by prose that
 *  merely quotes a rule. */
const stripComments = (source: string): string => source.replace(/\/\*[\s\S]*?\*\//g, '');

/** The bodies of EVERY top-level at-rule matching `query`, concatenated, by
 *  brace matching — so a rule can be pinned to the breakpoint it must live in,
 *  not merely to the file. All blocks, because a stylesheet may (and screens.css
 *  does) open the same breakpoint more than once; taking only the first would
 *  silently miss the rule. */
function mediaBlock(source: string, query: string): string {
  const src = stripComments(source);
  const bodies: string[] = [];
  let from = 0;
  for (;;) {
    const start = src.indexOf(`@media ${query}`, from);
    if (start < 0) break;
    const open = src.indexOf('{', start);
    let depth = 0;
    for (let i = open; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1;
      else if (src[i] === '}') {
        depth -= 1;
        if (depth === 0) {
          bodies.push(src.slice(open + 1, i));
          from = i;
          break;
        }
      }
    }
    if (depth !== 0) break;
  }
  return bodies.join('\n');
}

function rulesIn(block: string): { selector: string; body: string }[] {
  return [...block.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim().replace(/\s+/g, ' '),
    body: m[2],
  }));
}

const ruleIn = (block: string, selector: string): string | undefined =>
  rulesIn(block).find((r) => r.selector === selector)?.body;

const chrome = cssByName('chrome.css');
/** The COMPACT band. The treatment lives at ≤1024px, not ≤640px: measured, the
 *  one-row bar cannot hold this crumb at 768 either (see the header note). */
const compact = mediaBlock(chrome, '(max-width: 1024px)');
/** Phone-only additions (a smaller gutter, the icon-only search trigger, the
 *  dropped mono filename). */
const phone = mediaBlock(chrome, '(max-width: 640px)');
const baseRules = (() => {
  // everything outside any at-rule
  const src = stripComments(chrome);
  let out = '';
  for (let i = 0; i < src.length; i += 1) {
    if (src[i] !== '@') {
      out += src[i];
      continue;
    }
    const open = src.indexOf('{', i);
    if (open < 0) break;
    let depth = 0;
    let j = open;
    for (; j < src.length; j += 1) {
      if (src[j] === '{') depth += 1;
      else if (src[j] === '}') {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    i = j;
  }
  return out;
})();
const baseRule = (selector: string): string | undefined =>
  rulesIn(baseRules).find((r) => r.selector === selector)?.body;

const RECORD_TITLE = 'Synthetic XANES — CuO (Cu K-edge) · Partially Completed';
const SURFACE = 'Evidence & File Preview';

function renderRecordBar() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TopBar
        variant="record"
        recordId="01SYNTHXANESSEED0000000002"
        title={RECORD_TITLE}
        surface={SURFACE}
        stateChip="draft"
      />
    </MemoryRouter>,
  );
}

describe('C1 · the record breadcrumb can no longer paint over the top-bar controls', () => {
  it('CSS source: both responsive bands exist', () => {
    expect(compact, 'chrome.css must declare a (max-width: 1024px) block').not.toBe('');
    expect(phone, 'chrome.css must declare a (max-width: 640px) block').not.toBe('');
  });

  it('CSS source: .record-context clips its own content at EVERY width', () => {
    // The occlusion defect was `overflow: visible`. At 768 the box measured
    // clientWidth 350 against scrollWidth 455 and the excess painted across the
    // bar, so the containment is unconditional, not per-breakpoint.
    const base = baseRule('.record-context');
    expect(base, 'chrome.css must declare .record-context').toBeDefined();
    expect(base!).toMatch(/overflow:\s*hidden/);
    expect(base!).toMatch(/min-width:\s*0/);
  });

  it('CSS source: .record-context takes a full row instead of a 69px remainder', () => {
    const body = ruleIn(compact, '.record-context')!;
    // `flex: 1 1 100%` is what makes it a row of its own; `order: 1` puts that
    // row below the controls rather than above them.
    expect(body).toMatch(/flex:\s*1 1 100%/);
    expect(body).toMatch(/order:\s*1/);
  });

  it('CSS source: the bar may actually grow a second row (a fixed 60px could not)', () => {
    const bar = ruleIn(compact, '.topbar');
    expect(bar, '.topbar must be re-declared at ≤1024px').toBeDefined();
    expect(bar!).toMatch(/flex-wrap:\s*wrap/);
    expect(bar!).toMatch(/height:\s*auto/);
    expect(bar!).toMatch(/min-height:\s*60px/);
    // …and the desktop bar is untouched: still a fixed 60px row.
    const desktop = rulesIn(stripComments(chrome)).find((r) => r.selector === '.topbar')!;
    expect(desktop.body).toMatch(/height:\s*60px/);
    expect(desktop.body).not.toMatch(/flex-wrap/);
  });

  it('CSS source: the leaf crumb truncates instead of overflowing', () => {
    const body = ruleIn(compact, '.record-surface');
    expect(body, '.record-surface must be re-declared at ≤1024px').toBeDefined();
    expect(body!).toMatch(/min-width:\s*0/);
    expect(body!).toMatch(/overflow:\s*hidden/);
    expect(body!).toMatch(/text-overflow:\s*ellipsis/);
  });

  it('CSS source: nothing in the record context is hidden outright', () => {
    // The contract is explicit: record context may truncate or simplify, but no
    // information may be hidden from every location. The only `display: none`
    // permitted in this block on that subtree is the pair of DECORATIVE
    // chevrons (proved aria-hidden by the DOM test below).
    const hidden = rulesIn(compact)
      .filter((r) => /display:\s*none/.test(r.body))
      .map((r) => r.selector);
    expect(hidden).toContain('.record-context > svg');
    expect(hidden).not.toContain('.record-surface');
    expect(hidden).not.toContain('.record-title');
    expect(hidden).not.toContain('.record-context');
    expect(hidden).not.toContain('.mode-chip');
    expect(hidden).not.toContain('button.topbar-search');
  });

  it('DOM: the chevrons the phone rule hides carry no information', () => {
    const { container } = renderRecordBar();
    const chevrons = [...container.querySelectorAll('.record-context > svg')];
    expect(chevrons.length).toBeGreaterThan(0);
    for (const svg of chevrons) expect(svg.getAttribute('aria-hidden')).toBe('true');
  });

  it('DOM: reading order is unchanged — `order: 1` is presentation only', () => {
    const { container } = renderRecordBar();
    const context = container.querySelector('.record-context')!;
    const right = container.querySelector('.topbar-right')!;
    // The crumb still PRECEDES the controls in the DOM, so the accessibility
    // tree, the tab sequence and screen-reader order are exactly what they were
    // before the wrap; only the painted position moved.
    expect(context.compareDocumentPosition(right) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('DOM: both crumbs are still rendered — the fix removes no text', () => {
    const { container } = renderRecordBar();
    expect(container.querySelector('.record-title')!.textContent).toBe(RECORD_TITLE);
    expect(container.querySelector('.record-surface')!.textContent).toBe(SURFACE);
    // the leaf is still the current page, and the title is still the link back
    expect(container.querySelector('.record-surface')!.getAttribute('aria-current')).toBe('page');
    expect(container.querySelector('.record-title')!.tagName).toBe('A');
  });
});

describe('I4 · the record title has a width to render into', () => {
  it('CSS source: .record-title is given the row and allowed to shrink', () => {
    const body = ruleIn(compact, '.record-title');
    expect(body, '.record-title must be re-declared at ≤1024px').toBeDefined();
    // `min-width: 0` is not enough on its own — that is what produced
    // clientWidth 0. It needs a basis to fill.
    expect(body!).toMatch(/flex:\s*1 1 100%/);
    expect(body!).toMatch(/min-width:\s*0/);
  });

  it('CSS source: the ellipsis mechanism it depends on is still declared', () => {
    const base = rulesIn(stripComments(chrome)).find((r) => r.selector === '.record-title')!;
    expect(base.body).toMatch(/white-space:\s*nowrap/);
    expect(base.body).toMatch(/overflow:\s*hidden/);
    expect(base.body).toMatch(/text-overflow:\s*ellipsis/);
  });

  it('CSS source: the clipped context keeps a visible focus ring on the title link', () => {
    // `.record-context { overflow: hidden }` would otherwise clip the 2px
    // OUTSET ring base.css draws around the title link.
    const body = ruleIn(compact, '.record-title-link:focus-visible');
    expect(body, 'the focus ring must be re-offset inside the clipped context').toBeDefined();
    expect(body!).toMatch(/outline-offset:\s*-2px/);
  });

  it('DOM: the title is rendered as a single element bearing the whole string', () => {
    const { container } = renderRecordBar();
    const title = container.querySelector('.record-title')!;
    // One node, one string: what the ellipsis truncates VISUALLY is still fully
    // present in the accessibility tree and in the link's accessible name.
    expect(title.childElementCount).toBe(0);
    expect(title.textContent).toBe(RECORD_TITLE);
  });
});

describe('I4 (wider bands) · the title survives 768, 1024 and everything above', () => {
  it('CSS source: the responsive treatment is NOT confined to phone widths', () => {
    // THE REGRESSION THIS FILE EXISTS TO PREVENT. Every declaration that gives
    // the crumb its own row must live in the ≤1024px band; if one is moved back
    // to ≤640px, 768 silently returns to a zero-width title.
    for (const selector of [
      '.record-context',
      '.record-context > svg',
      '.record-title',
      '.record-surface',
      '.record-title-link:focus-visible',
    ]) {
      expect(ruleIn(compact, selector), `${selector} must be declared at ≤1024px`).toBeDefined();
      expect(
        ruleIn(phone, selector),
        `${selector} must NOT be re-declared at ≤640px — that is where the 768px gap came from`,
      ).toBeUndefined();
    }
    // `.topbar` IS legitimately re-declared on phones (a tighter gap and side
    // padding), but the WRAP — the part that lets a second row exist at all —
    // must be declared once, in the wider band.
    const compactBar = ruleIn(compact, '.topbar')!;
    expect(compactBar).toMatch(/flex-wrap:\s*wrap/);
    expect(compactBar).toMatch(/min-height:\s*60px/);
    const phoneBar = ruleIn(phone, '.topbar') ?? '';
    for (const prop of ['flex-wrap', 'min-height', 'height', 'align-content']) {
      expect(phoneBar, `${prop} must not be re-declared at ≤640px`).not.toMatch(
        new RegExp(`${prop}\\s*:`),
      );
    }
  });

  it('CSS source: the ≤640px band keeps only what is genuinely phone-specific', () => {
    // The mono filename is dropped on phones but KEPT at 641–1024, where the
    // crumb's second row has room for it (row 2 measures 335px of 710 at 768).
    expect(ruleIn(phone, '.record-file')).toMatch(/display:\s*none/);
    expect(ruleIn(compact, '.record-file')).toBeUndefined();
    expect(ruleIn(phone, '.topbar-search-label, .topbar-search-kbd')).toMatch(/display:\s*none/);
  });

  it('CSS source: the title has an unconditional floor, above the critical threshold', () => {
    // Above the ≤1024 band the bar stays one row and the title is the shrink
    // sink — `overflow: hidden` makes its automatic minimum size 0, which is
    // exactly how it reached clientWidth 0. The floor is the guard, and it must
    // clear the browser probe's 40px critical-label threshold with room to
    // spare. Measured narrowest allocation in that band: 130px at 1025.
    const base = baseRule('.record-title');
    expect(base, 'chrome.css must declare .record-title').toBeDefined();
    const floor = /min-width:\s*(\d+)px/.exec(base!);
    expect(floor, '.record-title must declare a min-width floor').not.toBeNull();
    expect(Number(floor![1])).toBeGreaterThanOrEqual(40);
    // and the ≤1024 band deliberately releases it, because there the title owns
    // a full row and must be free to fill it
    expect(ruleIn(compact, '.record-title')!).toMatch(/min-width:\s*0/);
  });

  it('CSS source: the floor and the containment are declared together', () => {
    // A floor without containment would trade a lost title for painted-over
    // controls; containment without a floor is what 768 already was. Both, or
    // neither — so they are asserted as a pair.
    expect(baseRule('.record-title')!).toMatch(/min-width:\s*\d+px/);
    expect(baseRule('.record-context')!).toMatch(/overflow:\s*hidden/);
  });

  it('DOM: the elements those rules target are the ones the record bar renders', () => {
    const { container } = renderRecordBar();
    expect(container.querySelector('.record-context')).not.toBeNull();
    expect(container.querySelector('.record-title')).not.toBeNull();
    expect(container.querySelector('.record-surface')).not.toBeNull();
    // the file crumb is the one the phone band hides — it must exist for that
    // rule to be doing anything, and it must NOT be the title
    const { container: withFile } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <TopBar
          variant="record"
          recordId="01SYNTHXANESSEED0000000002"
          title={RECORD_TITLE}
          surface={SURFACE}
          filename="synthetic_scan_0001.xdi"
        />
      </MemoryRouter>,
    );
    const file = withFile.querySelector('.record-file')!;
    expect(file.textContent).toBe('synthetic_scan_0001.xdi');
    expect(file.classList.contains('record-title')).toBe(false);
  });
});

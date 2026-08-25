/*
 * RESPONSIVE LAYOUT DEFECTS — the CSS half of the contract.
 *
 * Five defects found by a programmatic responsive sweep of the running app.
 * Every number quoted below was MEASURED in headless Chromium ON DARWIN, so per
 * `e2e/a11y-baseline.ts`'s standing rule it is indicative and CI's Linux column
 * is the authority. What these tests pin is not a pixel count — it is the CSS
 * DECLARATION that makes the geometry impossible, which is platform-independent.
 *
 * ── Why this is a source-text test and not a rendering test ──────────────────
 *
 * jsdom applies no CSS and lays nothing out, so a rendered assertion here would
 * be vacuous. The live geometry belongs to `e2e/specs/layout-widths.spec.ts`,
 * which owns the width sweep and where the F1 mechanism now has an
 * injected-geometry regression case running against these very stylesheets.
 * This file is the fast half: it fails in the `frontend` job in milliseconds if
 * a declaration is deleted, instead of after a ~30-minute browser job.
 *
 * Same technique as `interaction-states.test.ts` and `no-vertical-rail.test.ts`:
 * stylesheets are pulled in as raw strings through Vite's `import.meta.glob`, so
 * no `node:fs` and no `@types/node`.
 */

import { describe, it, expect } from 'vitest';

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

interface Rule {
  /** The selector list, whitespace-normalised. */
  selector: string;
  /** The declaration block, comments stripped. */
  body: string;
  /** The at-rule preludes this rule is nested inside, outermost first. */
  atRules: string[];
  /** Which stylesheet it came from, as the glob key. */
  file: string;
}

/**
 * Brace-matching rule extractor that RECORDS the at-rule context rather than
 * flattening it. F4's whole contract is "inside `@media (max-width: 1024px)`" —
 * a checker that could not tell nested from top-level would pass on a
 * declaration that applied at every width, which is the opposite of the fix.
 */
function extractRules(source: string, file: string): Rule[] {
  const out: Rule[] = [];
  const walk = (text: string, atRules: string[]): void => {
    let buf = '';
    let i = 0;
    while (i < text.length) {
      const ch = text[i];
      if (ch === '{') {
        const selector = buf.trim().replace(/\s+/g, ' ');
        let depth = 1;
        let j = i + 1;
        const start = j;
        while (j < text.length && depth > 0) {
          if (text[j] === '{') depth++;
          else if (text[j] === '}') depth--;
          j++;
        }
        const inner = text.slice(start, j - 1);
        if (selector.startsWith('@')) walk(inner, [...atRules, selector]);
        else out.push({ selector, body: stripComments(inner), atRules, file });
        buf = '';
        i = j;
        continue;
      }
      if (ch === '}') {
        buf = '';
        i++;
        continue;
      }
      buf += ch;
      i++;
    }
  };
  walk(stripComments(source), []);
  return out;
}

const stripComments = (s: string): string => s.replace(/\/\*[\s\S]*?\*\//g, '');

const ALL_RULES: Rule[] = Object.entries(cssFiles).flatMap(([path, src]) => extractRules(src, path));

/** Every rule whose selector list contains `selector` as a comma-separated part. */
function rulesFor(selector: string): Rule[] {
  return ALL_RULES.filter((r) =>
    r.selector
      .split(',')
      .map((s) => s.trim())
      .includes(selector)
  );
}

/** The last winning value of `prop` across every rule matching `selector`. */
function declaredValue(selector: string, prop: string, inAtRule?: RegExp): string | null {
  const matches = rulesFor(selector).filter(
    (r) => inAtRule === undefined || r.atRules.some((a) => inAtRule.test(a))
  );
  let value: string | null = null;
  for (const rule of matches) {
    const re = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`, 'g');
    for (const m of rule.body.matchAll(re)) value = m[1].trim();
  }
  return value;
}

describe('F1 · Compare Runs no longer makes the whole page scroll sideways', () => {
  /*
   * MEASURED, darwin, at 390 and at 320: `documentElement.scrollWidth` was 417
   * against a `clientWidth` of 390 (and of 320), while `document.body`
   * measured the viewport exactly — the overflow was on `html`, and the strip
   * the user could scroll into was empty. Culprit:
   * `td.rc-cell > a.rc-open > span.sr-only`, `position: absolute` with
   * `offsetParent: body`, laid out at left 416 / right 417.
   *
   * `.rc-tablewrap` is `overflow-x: auto`, and `overflow` alone does NOT
   * establish a containing block, so the accessible-name spans resolved
   * against `body` and escaped the scroller that exists for the table.
   *
   * Isolated in-page proof, both states measured in one `evaluate()` at 390px:
   * with the wrap `static`, `documentElement` 662 / 390 and `offsetParent BODY`;
   * with `position: relative`, 390 / 390 and the wrap as `offsetParent`. The
   * span's own right edge is 662 either way — it stops being the document's
   * overflow, it is not moved.
   */
  it('.rc-tablewrap establishes a containing block for its absolute descendants', () => {
    expect(declaredValue('.rc-tablewrap', 'position')).toBe('relative');
  });

  it('and still scrolls, so the fix did not trade the overflow for a clip', () => {
    expect(declaredValue('.rc-tablewrap', 'overflow-x')).toBe('auto');
  });

  it('the accessible-name spans are still rendered — hiding them was the rejected fix', () => {
    // `.sr-only` carries the only text distinguishing one "Open" link from
    // another. `display: none` or `content-visibility: hidden` would take the
    // overflow away by taking the accessible name away.
    const body = rulesFor('.sr-only')
      .map((r) => r.body)
      .join(';');
    expect(body).toMatch(/position\s*:\s*absolute/);
    expect(body).not.toMatch(/display\s*:\s*none/);
  });
});

describe('F2 · Load Materials reflows to one column instead of scrolling sideways', () => {
  /*
   * MEASURED, darwin @320: `.onramps` scrollWidth 468 in a clientWidth of 242,
   * cards at x 39→261 and 275→507, and the overflow landing on
   * `main#main.screen-main.centered` (496 / 298) — which is also the vertical
   * scroller, so it offered no horizontal affordance. The page measured a clean
   * 320 == 320, which is why the document-level probe never reported it. WCAG
   * 1.4.10 Reflow.
   */
  it('.onramps no longer hard-codes two columns', () => {
    const tracks = declaredValue('.onramps', 'grid-template-columns');
    expect(tracks).not.toBeNull();
    expect(tracks).not.toBe('1fr 1fr');
  });

  it('and states a minimum readable card width, so the track count follows the container', () => {
    const tracks = declaredValue('.onramps', 'grid-template-columns')!;
    expect(tracks).toMatch(/repeat\(\s*auto-fit\s*,\s*minmax\(/);
    const floor = /minmax\(\s*(\d+)px/.exec(tracks);
    expect(floor).not.toBeNull();
    // Two 240px tracks plus the 14px gap need 494px, so 390 and 320 collapse to
    // one column while 640 and up keep the two columns they already had.
    expect(Number(floor![1])).toBeGreaterThanOrEqual(200);
  });
});

describe('F3 · the Governance & Safety banner wraps instead of shrinking to one word a line', () => {
  /*
   * MEASURED on Load Materials, darwin. `.gov-body` was `flex: 1 1 0%` while the
   * icon (18px) and the "Read Policy" action (83px) were both `flex: none`, so
   * the paragraph absorbed all of the shrink:
   *
   *   1280 → 825 x 94px    5 lines
   *    768 → 531 x 150px   8 lines
   *    640 → 403 x 206px  11 lines
   *    390 → 153 x 544px  29 lines
   *    320 →  83 x 1125px 60 lines
   *
   * A load-bearing honesty disclosure rendering as a 1,125px ribbon.
   */
  it('.gov-banner wraps', () => {
    expect(declaredValue('.gov-banner', 'flex-wrap')).toBe('wrap');
  });

  it('.gov-body has a real flex basis, not the zero basis that let it be crushed', () => {
    const flex = declaredValue('.gov-banner .gov-body', 'flex');
    expect(flex).not.toBeNull();
    // `flex: 1` is `1 1 0%`. The third component must be a real length.
    const basis = /^\s*\d+\s+\d+\s+(\d+)px\s*$/.exec(flex!);
    expect(basis, `expected a "<grow> <shrink> <basis>px" triple, got ${JSON.stringify(flex)}`).not.toBeNull();
    expect(Number(basis![1])).toBeGreaterThan(0);
  });

  it('the basis keeps the icon and the paragraph on one line at 320px', () => {
    // The banner's content box measured 208px at a 320px viewport. The icon
    // costs 18px and one 12px gap, so a basis above 178px would push the
    // paragraph onto its own line and orphan the icon.
    const basis = Number(/(\d+)px/.exec(declaredValue('.gov-banner .gov-body', 'flex')!)![1]);
    expect(basis).toBeLessThanOrEqual(178);
  });
});

describe('F4 · the fixed Assistant trigger no longer sits on top of the status bar', () => {
  /*
   * MEASURED, darwin, on Review Record. The trigger is `position: fixed`, 38px
   * tall, 16px off the bottom — it owns the bottom 54px at every width ≤1024.
   * `footer.statusbar` is `position: static`, 52px tall, and the LAST child of
   * `div.screen-card`; the DOCUMENT is the scroller at these widths (`main`
   * measured scrollHeight == clientHeight). Scrolling to the end put the footer
   * at viewport y 760..812 under a trigger at 758..796, and the occlusion probe
   * reported `span.statusbar-right` ("local dev · no telemetry") covered on 3 to
   * 5 of 5 sampled points on all five record surfaces at 1024 and at 768.
   *
   * It survived `scrollIntoView` for one reason: there was nothing below the
   * footer to scroll into. So the reserve is space AFTER the card, not padding
   * inside `main` — the footer comes after `main`, and `main` is not the
   * scroller here.
   */
  const NARROW = /max-width:\s*1024px/;

  it('a reserve is declared, and only inside the band where the trigger floats', () => {
    const reserve = declaredValue(':root', '--assistant-trigger-reserve', NARROW);
    expect(reserve, 'expected --assistant-trigger-reserve inside @media (max-width: 1024px)').not.toBeNull();
    const px = Number(/(\d+)px/.exec(reserve!)![1]);
    // 38px trigger + 16px offset = 54px occupied. Anything less is not a reserve.
    expect(px).toBeGreaterThanOrEqual(54);

    // And NOT at every width: an unconditional reserve would put dead space
    // under the card on the desktop layout, where the trigger is `display: none`.
    expect(declaredValue(':root', '--assistant-trigger-reserve')).toBe(reserve);
    const unconditional = rulesFor(':root').filter(
      (r) => r.atRules.length === 0 && /--assistant-trigger-reserve/.test(r.body)
    );
    expect(unconditional).toEqual([]);
  });

  it('.screen-card leaves that much room after itself', () => {
    expect(declaredValue('.screen-card', 'margin-bottom', NARROW)).toBe('var(--assistant-trigger-reserve)');
  });

  it('and gives the same amount back out of its min-height, so short pages gain no scrollbar', () => {
    /*
     * `.screen-card`'s base floor is `calc(100vh - 32px)` (the 32px is `.app`'s
     * 16px padding on both sides). A 64px margin on top of that would make EVERY
     * page 64px taller than the viewport and give a screen whose content fits a
     * permanent vertical scrollbar. Trading an occlusion for a scrollbar is not
     * a fix, so the floor is reduced by exactly the reserve.
     */
    const minHeight = declaredValue('.screen-card', 'min-height', NARROW);
    expect(minHeight).not.toBeNull();
    expect(minHeight).toMatch(/calc\(/);
    expect(minHeight).toMatch(/100vh/);
    expect(minHeight).toContain('var(--assistant-trigger-reserve)');
    expect(minHeight, 'the reserve must be SUBTRACTED from the floor, not added to it').toMatch(
      /-\s*var\(--assistant-trigger-reserve\)/
    );
  });
});

describe('F5 · pointer targets clear the WCAG 2.5.8 floor of 24px', () => {
  /*
   * Every selector below was measured under 24px tall, on darwin, at 1280 and
   * 390, across the whole `e2e/surfaces.ts` catalogue. The two run-card controls
   * were reported at 23px — one pixel short — by the sweep that commissioned
   * this work; they are not in the list this suite can reach, because no seeded
   * example record has a run, so no catalogued surface renders a run card.
   */
  const FLOORED: readonly [string, string][] = [
    ['.btn', 'the shared button family (a floor, not a finding — it measures ~35px)'],
    ['.run-card-focus', '52.0 x 23.0 — "Focus run …"'],
    ['.run-card-compare', '69.5 x 23.0 — "Compare run …"'],
    ['.gov-banner .gov-action', '82.9 x 17.0 — "Read Policy"'],
    ['.guided-dontknow', '252.4 x 17.0 — "I don\'t know — leave honestly missing"'],
    ['.memory-graph-help-trigger', '133.5 x 21.0 — "About This Graph"'],
    ['.graph-cmd-help', '77.0 x 23.0'],
    ['.api-copy-btn', '63.6 x 21.0'],
    ['.api-samples-tabs-tab', '50.8 x 21.0'],
    ['.record-title-link', 'x 21.7 — the breadcrumb record title'],
  ];

  for (const [selector, measured] of FLOORED) {
    it(`${selector} has a 24px floor (measured ${measured})`, () => {
      const value = declaredValue(selector, 'min-height');
      expect(value, `no min-height reaches ${selector}`).not.toBeNull();
      expect(Number(/(\d+(?:\.\d+)?)px/.exec(value!)![1])).toBeGreaterThanOrEqual(24);
    });
  }

  it('the four measured `summary` toggles are LEFT OPEN, and the reason is recorded in the CSS', () => {
    /*
     * Four `<summary>` disclosure toggles measured 17.3 to 20.1px tall: the
     * Validator's "When to use this", `.stats-chart-table-toggle`,
     * `.api-connect-summary` and `.api-samples-summary`.
     *
     * `summary { padding-block: 4px }` clears all four. It was written, measured,
     * and removed: growing those boxes moved previously-unresolvable nodes into
     * axe's `violations` bucket on the Endpoint Explorer (`settings-explorer`
     * color-contrast +1 at desktop-1280x800, +1 at mobile-375x812, +2 at
     * zoom-200), and removing the rule returned all three pairs to their prior
     * numbers exactly. That is the same incomplete-to-violations mechanism
     * `e2e/a11y-baseline.ts` records for `guided-completion`.
     *
     * This test asserts the DELIBERATE ABSENCE together with the written
     * reasoning, so the gap cannot be quietly closed by someone who has not
     * measured what it uncovers — and cannot rot into an unexplained omission
     * either. If the API browser's contrast debt is fixed first, delete this test
     * and add `summary` to the floor above.
     */
    expect(
      declaredValue('summary', 'padding-block'),
      'if a `summary` floor is being added, the Endpoint Explorer contrast nodes it exposes ' +
        'have to be dealt with in the same change — see the comment in styles/base.css'
    ).toBeNull();
    expect(declaredValue('summary', 'min-height')).toBeNull();

    const base = Object.entries(cssFiles).find(([p]) => p.endsWith('styles/base.css'))![1];
    expect(base).toContain('FOUR MEASURED VIOLATIONS DELIBERATELY LEFT OPEN');
    expect(base, 'the recorded reason must name the surface the fix would regress').toContain(
      'settings-explorer'
    );
  });

  it('.record-title-link is not turned into a flex container, which would drop its ellipsis', () => {
    // It carries `.record-title`'s `text-overflow: ellipsis`. A flex container
    // stops applying that silently, which would turn a target-size fix into
    // content loss on exactly the label `layout-widths.spec.ts` case T1 exists
    // to protect.
    const display = declaredValue('.record-title-link', 'display');
    expect(display === null || !/flex|grid/.test(display)).toBe(true);
  });

  it('the visually-hidden file inputs are left alone — their label is the target', () => {
    // Measured 1.0 x 1.0. Giving these a 24px floor would put a visible box
    // where the design deliberately has none.
    for (const selector of ['.csv-recon-visually-hidden', '.rec-val-visually-hidden']) {
      expect(declaredValue(selector, 'min-height')).toBeNull();
    }
  });
});

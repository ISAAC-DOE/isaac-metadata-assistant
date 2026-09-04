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

/**
 * THE AT-RULE SCOPE A DECLARATION MUST BE IN TO COUNT — and it is REQUIRED,
 * because it used to be optional and that made four of these five suites blind.
 *
 * REVIEW FINDING I5, MEASURED: `declaredValue`'s third argument was
 * `inAtRule?: RegExp`, and only F4 ever passed it. So F1, F2, F3 and F5 counted
 * a declaration nested inside ANY `@media` as though it were top-level. Proof,
 * reproduced against the real stylesheets: revert `components/runner.css`'s
 * `.onramps` grid to the defective `1fr 1fr` and put the `repeat(auto-fit, …)`
 * fix inside `@media (min-width: 3000px)` — a band no user is ever in — and this
 * file went **24/24 green with the defect fully restored in the product**.
 *
 * `TOP_LEVEL` is the honest question for F1/F2/F3/F5: every declaration they
 * pin is one that must apply AT EVERY WIDTH, and all of them are in fact
 * top-level today (measured across the whole `src/**\/*.css` glob). A RegExp
 * scope is the honest question for F4, whose whole contract is "inside
 * `@media (max-width: 1024px)` and nowhere else".
 *
 * There is deliberately NO "any context" option here. Absence assertions — the
 * only place any-context is the STRICTER question — get their own named
 * function, `declaredAnywhere`, so a presence assertion cannot reach the lax
 * lookup by passing a sentinel.
 */
const TOP_LEVEL = Symbol('top-level: applies at every width');
type Scope = RegExp | typeof TOP_LEVEL;

const inScope = (rule: Rule, scope: Scope): boolean =>
  scope === TOP_LEVEL
    ? rule.atRules.length === 0
    : rule.atRules.some((a) => (scope as RegExp).test(a));

/** Every rule whose selector list contains `selector` as a comma-separated part. */
function rulesFor(selector: string, rules: Rule[] = ALL_RULES): Rule[] {
  return rules.filter((r) =>
    r.selector
      .split(',')
      .map((s) => s.trim())
      .includes(selector)
  );
}

const lastValue = (matches: Rule[], prop: string): string | null => {
  let value: string | null = null;
  for (const rule of matches) {
    const re = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`, 'g');
    for (const m of rule.body.matchAll(re)) value = m[1].trim();
  }
  return value;
};

/**
 * The last winning value of `prop` across every rule matching `selector` **that
 * sits in `scope`**. `scope` is required; see the note on {@link TOP_LEVEL}.
 */
function declaredValue(
  selector: string,
  prop: string,
  scope: Scope,
  rules: Rule[] = ALL_RULES
): string | null {
  return lastValue(
    rulesFor(selector, rules).filter((r) => inScope(r, scope)),
    prop
  );
}

/**
 * The last winning value of `prop` in ANY at-rule context.
 *
 * FOR ABSENCE ASSERTIONS ONLY. "This declaration exists nowhere" is a stronger
 * claim than "it exists nowhere at top level", so any-context is the correct —
 * and stricter — lookup for a `toBeNull()`. Never use it to assert a value is
 * PRESENT: that is exactly the blindness I5 measured.
 */
function declaredAnywhere(selector: string, prop: string, rules: Rule[] = ALL_RULES): string | null {
  return lastValue(rulesFor(selector, rules), prop);
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
    expect(declaredValue('.rc-tablewrap', 'position', TOP_LEVEL)).toBe('relative');
  });

  it('and still scrolls, so the fix did not trade the overflow for a clip', () => {
    expect(declaredValue('.rc-tablewrap', 'overflow-x', TOP_LEVEL)).toBe('auto');
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
    const tracks = declaredValue('.onramps', 'grid-template-columns', TOP_LEVEL);
    expect(tracks).not.toBeNull();
    expect(tracks).not.toBe('1fr 1fr');
  });

  it('and states a minimum readable card width, so the track count follows the container', () => {
    const tracks = declaredValue('.onramps', 'grid-template-columns', TOP_LEVEL)!;
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
    expect(declaredValue('.gov-banner', 'flex-wrap', TOP_LEVEL)).toBe('wrap');
  });

  it('.gov-body has a real flex basis, not the zero basis that let it be crushed', () => {
    const flex = declaredValue('.gov-banner .gov-body', 'flex', TOP_LEVEL);
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
    const basis = Number(/(\d+)px/.exec(declaredValue('.gov-banner .gov-body', 'flex', TOP_LEVEL)!)![1]);
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
    // Asked two ways on purpose — the token must not resolve at top level, and no
    // top-level `:root` rule may so much as mention it.
    expect(
      declaredValue(':root', '--assistant-trigger-reserve', TOP_LEVEL),
      'the reserve must exist ONLY inside the narrow band, never unconditionally'
    ).toBeNull();
    const unconditional = rulesFor(':root').filter(
      (r) => r.atRules.length === 0 && /--assistant-trigger-reserve/.test(r.body)
    );
    expect(unconditional).toEqual([]);
    // The value the narrow band declares is also the last one declared anywhere,
    // so no wider band silently overrides the one this suite measured.
    expect(declaredAnywhere(':root', '--assistant-trigger-reserve')).toBe(reserve);
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
   * 390, across the whole `e2e/surfaces.ts` catalogue. The run-card control was
   * reported at 23px — one pixel short — by the sweep that commissioned this
   * work; it is not in the list this suite can reach, because no seeded example
   * record has a run, so no catalogued surface renders a run card.
   *
   * `.run-card-focus` was a SECOND such control and is gone, not merely fixed
   * (fix round, PR-C, review finding I-3): a compact row's own open button did
   * the same act beside it, which was the defect — two 52×24 targets for one
   * act, and 73px of extra row height once they wrapped at 320px.
   */
  const FLOORED: readonly [string, string][] = [
    ['.btn', 'the shared button family (a floor, not a finding — it measures ~35px)'],
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
      const value = declaredValue(selector, 'min-height', TOP_LEVEL);
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
      declaredAnywhere('summary', 'padding-block'),
      'if a `summary` floor is being added, the Endpoint Explorer contrast nodes it exposes ' +
        'have to be dealt with in the same change — see the comment in styles/base.css'
    ).toBeNull();
    expect(declaredAnywhere('summary', 'min-height')).toBeNull();

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
    const display = declaredAnywhere('.record-title-link', 'display');
    expect(display === null || !/flex|grid/.test(display)).toBe(true);
  });

  it('the visually-hidden file inputs are left alone — their label is the target', () => {
    // Measured 1.0 x 1.0. Giving these a 24px floor would put a visible box
    // where the design deliberately has none.
    for (const selector of ['.csv-recon-visually-hidden', '.rec-val-visually-hidden']) {
      expect(declaredAnywhere(selector, 'min-height')).toBeNull();
    }
  });
});

/*
 * ── I5's NEGATIVE CONTROL: the guard must be able to go RED ──────────────────
 *
 * Every assertion above is a `toBe`/`not.toBe` over source text, so it can be
 * satisfied by a declaration that never applies to a real viewport. That is not
 * hypothetical — it is exactly what an independent review MEASURED on this file:
 * with `declaredValue`'s at-rule filter optional and unused by F1/F2/F3/F5,
 * moving `.onramps`'s reflow fix into `@media (min-width: 3000px)` and restoring
 * `1fr 1fr` at top level left all 24 assertions GREEN with the defect fully
 * restored in the product.
 *
 * The control below rebuilds that exact stylesheet as a string and asserts both
 * halves: the scoped lookup this file now uses REPORTS THE DEFECT (so the suite
 * would fail), and the unscoped lookup — the old behaviour — reports the fix (so
 * the failure mode is reproduced rather than merely described).
 *
 * It runs on a synthetic stylesheet rather than by mutating a real one, because
 * a test that edits `components/runner.css` would race every other suite reading
 * it through the same `import.meta.glob`.
 */
describe("I5 · the at-rule filter is required, and a fix hidden in an unreachable @media reads as the defect", () => {
  const UNREACHABLE = `
    .onramps { display: grid; gap: 14px; grid-template-columns: 1fr 1fr; }
    .rc-tablewrap { overflow-x: auto; position: static; }
    .gov-banner { display: flex; flex-wrap: nowrap; }
    .btn { padding: 6px 10px; }
    @media (min-width: 3000px) {
      .onramps { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
      .rc-tablewrap { position: relative; }
      .gov-banner { flex-wrap: wrap; }
      .btn { min-height: 24px; }
    }
  `;
  const rules = extractRules(UNREACHABLE, 'synthetic/unreachable.css');

  const CASES: readonly [string, string, string, string][] = [
    // selector, property, the defect at top level, the fix hidden in the @media
    ['.onramps', 'grid-template-columns', '1fr 1fr', 'repeat(auto-fit, minmax(240px, 1fr))'],
    ['.rc-tablewrap', 'position', 'static', 'relative'],
    ['.gov-banner', 'flex-wrap', 'nowrap', 'wrap'],
  ];

  for (const [selector, prop, defect, hiddenFix] of CASES) {
    it(`${selector} { ${prop} } — TOP_LEVEL sees the defect, the unscoped lookup sees the fix`, () => {
      expect(
        declaredValue(selector, prop, TOP_LEVEL, rules),
        'the scoped lookup must report what a real viewport gets — the defect'
      ).toBe(defect);
      expect(
        declaredAnywhere(selector, prop, rules),
        'and the unscoped lookup must report the hidden fix, which is the blindness I5 measured'
      ).toBe(hiddenFix);
    });
  }

  it('a min-height that exists only above 3000px does not satisfy the 2.5.8 floor', () => {
    // The F5 shape. `declaredAnywhere` would find `24px` and pass; the scoped
    // lookup finds nothing, which is the truth for every user.
    expect(declaredValue('.btn', 'min-height', TOP_LEVEL, rules)).toBeNull();
    expect(declaredAnywhere('.btn', 'min-height', rules)).toBe('24px');
  });

  it("the reviewer's reproduction, on the REAL stylesheet's bytes and without touching disk", () => {
    /*
     * The synthetic cases above are the mechanism. This one is the actual
     * finding: `components/runner.css` as committed, with its `.onramps` fix
     * MOVED into `@media (min-width: 3000px)` by a string transform. Nothing is
     * written — mutating the file on disk would race every other suite reading
     * the same `import.meta.glob`, and would race the Playwright job reading it
     * through the dev server.
     */
    const [, runner] = Object.entries(cssFiles).find(([path]) =>
      path.endsWith('components/runner.css')
    )!;
    const FIX = 'repeat(auto-fit, minmax(240px, 1fr))';
    // The DECLARATION, not the comment above it that quotes the same string.
    const DECLARED = `grid-template-columns: ${FIX};`;
    expect(runner, 'the committed fix must be present for this transform to mean anything').toContain(
      DECLARED
    );
    const sabotaged =
      runner.replace(DECLARED, 'grid-template-columns: 1fr 1fr;') +
      `\n@media (min-width: 3000px) { .onramps { grid-template-columns: ${FIX}; } }\n`;
    const rules3000 = extractRules(sabotaged, 'components/runner.css');

    // What F2 asks now: RED, because a real viewport gets two hard columns.
    expect(declaredValue('.onramps', 'grid-template-columns', TOP_LEVEL, rules3000)).toBe('1fr 1fr');
    // What F2 asked before I5: GREEN, on a product with the defect restored.
    expect(declaredAnywhere('.onramps', 'grid-template-columns', rules3000)).toBe(FIX);
  });

  it('and a fix in a band users ARE in is still seen, so the filter is not just a blanket refusal', () => {
    const reachable = extractRules(
      '.onramps { grid-template-columns: 1fr 1fr; }\n' +
        '@media (max-width: 640px) { .onramps { grid-template-columns: 1fr; } }',
      'synthetic/reachable.css'
    );
    expect(declaredValue('.onramps', 'grid-template-columns', /max-width:\s*640px/, reachable)).toBe(
      '1fr'
    );
  });
});

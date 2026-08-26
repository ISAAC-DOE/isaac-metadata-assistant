/*
 * THE STICKY DOCK PUSHED AN INTERACTIVE CONTROL PAST THE FOLD AND HELD IT THERE.
 *
 * ── What was measured, and where the numbers come from ──────────────────────
 *
 * Headless Chromium, this dev build, `/record/<id>` inside a worked-example
 * session, the ≤1024px slide-over drawer. All figures DARWIN. They are recorded
 * here rather than in `e2e/a11y-baseline.ts` or `e2e/layout-baseline.ts`
 * precisely because a px reading taken on macOS is not authoritative — CI's
 * Linux column is — and nothing below is a ratchet.
 *
 *   viewport           `.assistant-foot`   "What Can I Ask?" trigger, unscrolled
 *   1280x800  DPR1              483.5     430.5..455.5   in view
 *   320x568   DPR1              425.8     251.5..276.5   in view
 *   640x400   DPR2              339.0     189..214       in view
 *   1280x450  DPR1              371.5     282..307       in view
 *   1440x400  DPR1              355.5     282..307       in view
 *   768x1024  DPR1              538.7     456.5..481.5   in view
 *   384x512   DPR2              391.3     227.7..252.7   in view
 *   187x406   DPR2              502.4     255..293       in view
 *   160x284   DPR2              545.9     321..359       BELOW THE FOLD
 *
 * 160x284 at DPR 2 is 320x568 at 200% browser zoom, emulated exactly the way
 * `playwright.config.ts`'s header documents it: halve the layout viewport,
 * double the device pixel ratio.
 *
 * ── The part that is arithmetic, and the part that was a bug ────────────────
 *
 * A 545.9px dock cannot fit a 284px viewport. Something in it is always off
 * screen, that is not fixable by a rule, and it PRE-DATES this change (the dock
 * already exceeded that viewport by 122.5% before the no-model claim was added).
 *
 * What was fixable is WHICH part, and whether scrolling reaches it. Sweeping the
 * drawer's entire scroll range (scrollTop 0..430) in 41 steps, asking at each
 * step whether the trigger's rect is FULLY inside the viewport:
 *
 *   position: sticky   fully visible for scrollTop 75..312, and at the BOTTOM
 *                      of the scroll — the resting position a reader reaches by
 *                      scrolling to the end — clipped at -22.9..15.1.
 *   position: relative fully visible for scrollTop 194..430, INCLUDING the
 *                      bottom of the scroll, where it sits at 1..39.
 *
 * Sticky drags the dock up by a clamped 110px and so holds its tail off the TOP
 * edge exactly where a reader stops. Dropping it hands the tail back. The
 * composer is in view at scrollTop 0 either way, so nothing is traded for it.
 *
 * ── RELEASING THE DOCK WAS NECESSARY AND NOT SUFFICIENT ─────────────────────
 *
 * The `1..39` above is ONE PIXEL of slack, and Linux CI spent it: the browser
 * spec measured `-17.5..22.5` in the `zoom-200` project, red. The dock is
 * taller there because this app ships no webfont and the 92-character claim
 * wraps at a different word under DejaVu/Liberation, and the extra line lands
 * BELOW the trigger, in the tail.
 *
 * The arithmetic, so the residue is not mistaken for noise. At the end of the
 * scroll the drawer's last content pixel IS the viewport's last pixel — the
 * container already scrolls its content fully, measured: `.assistant-foot`
 * ends at 283.9 in a 284px scrollport. So the trigger's top sits at
 * `284 - 38 - tail`, and the tail below it is `90.9 + 2 + 142 + 10 = 245`.
 * Nothing about the scroll RANGE is short (bottom padding in the band makes it
 * worse: scrollHeight and max scrollTop grow together and every box above the
 * tail moves further up), and the only other lever is shrinking the tail,
 * which is a content change.
 *
 * SO THE TRIGGER IS PINNED RATHER THAN SCROLLED PAST — `position: sticky;
 * top: 0` on `.assistant-capabilities`, in the same band. Measured on darwin
 * at the end of the scroll: `1..39` before, `16..54` after (16 is the drawer's
 * own top padding, where `top: 0` pins). With the tail inflated by 40px to
 * stand in for the Linux wrap: `-39..-1` before, `16..54` after — UNMOVED,
 * which is the property. The only height in it is the trigger's own 38 against
 * the viewport's 284, so it does not depend on which face wraps the caption.
 *
 * IT IS A TRADE AND THE COST IS MEASURED. A pinned box is displaced downward
 * out of flow, so at max scroll it overlays 13px of `.assistant-agent-actions`
 * on darwin (12 of them that block's own top padding, 1 touching its "Agent
 * Actions" eyebrow) and 53px with the tail inflated 40px — the eyebrow, and
 * none of the buttons, which start 61.6px down. Recoverable by scrolling up a
 * few px, which un-pins it; a control unreachable at the resting position is
 * recoverable by nothing. That is why the pin carries the dock's own opaque
 * tint: something IS painted behind it, and an earlier revision of this file
 * argued the background away on the theory that nothing was.
 *
 * ── Alternatives measured or refused, so they are not re-proposed ───────────
 *
 *   * raising `.record-right .assistant`'s `max-height` at short viewports was
 *     MEASURED WORSE: the panel grows to 1046px and the trigger starts at 799;
 *   * collapsing the no-model claim behind a control is the `voiceSeamUnreported`
 *     defect `assistant-model-claim-parity.test.tsx` §1 exists to refuse;
 *   * shortening the claim is refused by that file's §2 — 92 characters is the
 *     minimum pair and both clauses are load-bearing;
 *   * putting the trigger above the composer is a control-order change with a
 *     much wider blast radius than one CSS property.
 *
 * ── Honest scope of THIS file ───────────────────────────────────────────────
 *
 * jsdom evaluates no media query, lays nothing out and rasterises nothing. Every
 * assertion below is a CSS-SOURCE assertion. It proves the declarations exist
 * and that they are bounded; it does not prove pixels. The pixels are the table
 * above and `e2e/specs/assistant-dock-short-viewport.spec.ts`.
 */

import { describe, expect, it } from 'vitest';

import { ASSISTANT_NO_MODEL_CLAIM } from '../lib/assistant';

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const assistantCss =
  Object.entries(cssFiles).find(([path]) => path.endsWith('/assistant.css'))?.[1] ?? '';

/** `playwright.config.ts` as raw source — see the projects assertion below. */
const PLAYWRIGHT_CONFIG = (
  import.meta.glob('../../playwright.config.ts', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>
)['../../playwright.config.ts'] ?? '';

const stripComments = (source: string): string => source.replace(/\/\*[\s\S]*?\*\//g, '');

/** The exact media query the fix is scoped to. */
const SHORT_AND_NARROW = '@media (max-width: 480px) and (max-height: 480px)';

/**
 * Every `@media` block in the stylesheet, as `{ query, body }`, brace-balanced
 * so a nested rule cannot truncate the body. Comments are stripped first: this
 * file's own prose mentions `@media` and every selector it discusses.
 */
function mediaBlocks(source: string): { query: string; body: string }[] {
  const src = stripComments(source);
  const out: { query: string; body: string }[] = [];
  const re = /@media([^{]*)\{/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    const open = m.index + m[0].length - 1;
    let depth = 0;
    let close = -1;
    for (let i = open; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1;
      else if (src[i] === '}') {
        depth -= 1;
        if (depth === 0) {
          close = i;
          break;
        }
      }
    }
    if (close < 0) break;
    out.push({ query: `@media${m[1]}`.replace(/\s+/g, ' ').trim(), body: src.slice(open + 1, close) });
    re.lastIndex = close;
  }
  return out;
}

/** The FIRST `sel { … }` body in a source fragment (the base rule, in file order). */
function ruleBody(source: string, sel: string): string {
  const re = new RegExp(`(^|[,}\\s])${sel.replace(/\./g, '\\.')}\\s*(,[^{]*)?\\{([^}]*)\\}`, 'm');
  return re.exec(stripComments(source))?.[3] ?? '';
}

/** Declarations, as `prop: value` pairs, from a rule body. */
function declarations(body: string): [string, string][] {
  return body
    .split(';')
    .map((d) => d.trim())
    .filter(Boolean)
    .map((d) => {
      const at = d.indexOf(':');
      return [d.slice(0, at).trim(), d.slice(at + 1).trim()] as [string, string];
    });
}

describe('the composer dock un-sticks on a short, narrow viewport', () => {
  it('assistant.css is loadable', () => {
    expect(assistantCss.length).toBeGreaterThan(0);
  });

  /*
   * The base contract is UNCHANGED and is asserted here as well as in
   * `assistant-layout.test.tsx` / `assistant-shell-layout.test.tsx`, because a
   * fix that "solved" the fold by deleting the sticky dock everywhere would pass
   * every assertion in this file and be a different, worse change.
   */
  it('the DEFAULT dock is still the opaque sticky dock, everywhere else', () => {
    const foot = ruleBody(assistantCss, '.assistant-foot');
    expect(foot).toMatch(/position:\s*sticky/);
    expect(foot).toMatch(/bottom:\s*0/);
    expect(foot).toMatch(/z-index:\s*1/);
    expect(foot).toMatch(/background:\s*var\(--assist-tint\)/);
    expect(foot).toMatch(/flex:\s*none/);
  });

  it('a short AND narrow viewport releases the dock into normal flow', () => {
    const block = mediaBlocks(assistantCss).find((b) => b.query === SHORT_AND_NARROW);
    expect(
      block,
      `assistant.css must carry a "${SHORT_AND_NARROW}" block that un-sticks the dock`,
    ).toBeDefined();
    const foot = ruleBody(block!.body, '.assistant-foot');
    expect(foot.length, 'that block must contain an .assistant-foot rule').toBeGreaterThan(0);
    expect(foot).toMatch(/position:\s*relative/);
  });

  /*
   * `relative`, not `static`. `bottom: 0` is inert under relative positioning
   * (a zero offset), while `z-index: 1` keeps applying — and the dock's
   * background is opaque on purpose, so its paint order is not something to
   * hand back to source order as a side effect of a fold fix.
   */
  it('the override keeps the dock a POSITIONED box, so its z-index survives', () => {
    const block = mediaBlocks(assistantCss).find((b) => b.query === SHORT_AND_NARROW)!;
    const foot = ruleBody(block.body, '.assistant-foot');
    expect(foot).not.toMatch(/position:\s*static/);
  });

  /*
   * ONE property. The override exists to stop the dock sticking; it is not a
   * place to hide a narrow-viewport restyle, a height cap, or a `display: none`.
   */
  it('the override changes NOTHING but `position`', () => {
    const block = mediaBlocks(assistantCss).find((b) => b.query === SHORT_AND_NARROW)!;
    const props = declarations(ruleBody(block.body, '.assistant-foot')).map(([p]) => p);
    expect(props).toEqual(['position']);
  });

  /*
   * THE BOUND IS THE POINT, and this is the assertion that keeps it honest.
   *
   * `e2e/a11y-baseline.ts` and `e2e/layout-baseline.ts` record EXACT per-instance
   * numbers measured at the five projects in `playwright.config.ts` — 1280x800,
   * 1024x768, 768x1024, 375x812 and 640x400@DPR2. Every one of those is outside
   * a (max-width: 480px) and (max-height: 480px) band: the four tall ones fail
   * the height test, and zoom-200 fails the width test at 640. So this rule
   * cannot move a recorded count, and a future widening of it to `640px` — which
   * would reach zoom-200 — must be a deliberate act that turns this test red
   * first rather than a silent baseline drift discovered in CI.
   */
  it('the override cannot reach any viewport a recorded baseline was measured at', () => {
    const block = mediaBlocks(assistantCss).find((b) => b.query === SHORT_AND_NARROW)!;
    const width = /max-width:\s*(\d+)px/.exec(block.query);
    const height = /max-height:\s*(\d+)px/.exec(block.query);
    expect(width, 'the un-sticking rule must be width-bounded').not.toBeNull();
    expect(height, 'the un-sticking rule must be height-bounded').not.toBeNull();
    const maxW = Number(width![1]);
    const maxH = Number(height![1]);

    /* THE PROJECTS ARE READ OUT OF `playwright.config.ts`, NOT LISTED HERE.
       They were listed here, and the list was the hole: a SIXTH project added
       inside the band — which is exactly the size a future "small phone at
       200% zoom" project would be — would not have turned this red, because
       this test only ever checked the five it already knew.

       The config is parsed as SOURCE rather than imported: importing it
       re-evaluates `defineConfig` and pulls in `e2e/env.ts`'s `process.env`
       reads, and its own header warns against importing it from a spec. The
       `viewportProject(name, w, h, dpr, grep)` call is the one place a project
       is declared, so a regex over it sees every one. */
    const PROJECTS = [...PLAYWRIGHT_CONFIG.matchAll(
      /viewportProject\(\s*'([^']+)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,/g,
    )].map((m) => [m[1], Number(m[2]), Number(m[3])] as [string, number, number]);
    // A regex that silently matched nothing would make every assertion below
    // vacuous, which is the failure mode of deriving instead of listing.
    expect(
      PROJECTS.length,
      'no viewportProject(...) declarations were found in playwright.config.ts',
    ).toBeGreaterThanOrEqual(5);
    for (const [name, w, h] of PROJECTS) {
      expect(w <= maxW && h <= maxH, `${name} (${w}x${h}) must NOT match ${block.query}`).toBe(
        false,
      );
    }

    // …and it must still reach the viewport the defect was measured at.
    expect(160 <= maxW && 284 <= maxH, '160x284 must match the rule').toBe(true);
  });

  /*
   * THE SECOND HALF OF THE FIX, and the half CI was red on. Releasing the dock
   * leaves the trigger one pixel inside the viewport on darwin and ~17.5px
   * outside it on Linux; pinning it at the scrollport's top edge takes the
   * tail's height out of the question entirely. See the header block.
   */
  it('the band ALSO pins the capabilities trigger, so the tail cannot push it out', () => {
    const block = mediaBlocks(assistantCss).find((b) => b.query === SHORT_AND_NARROW)!;
    const caps = ruleBody(block.body, '.assistant-capabilities');
    expect(
      caps.length,
      `${SHORT_AND_NARROW} must carry an .assistant-capabilities rule that pins the trigger`,
    ).toBeGreaterThan(0);
    expect(caps).toMatch(/position:\s*sticky/);
    // TOP, not bottom. A bottom-sticky box is held off the BOTTOM edge; this
    // control leaves through the TOP, which is why the release alone was not it.
    expect(caps).toMatch(/top:\s*0/);
    expect(caps).not.toMatch(/bottom:/);
  });

  /*
   * THREE declarations and no fourth. The pin exists to stop the trigger being
   * scrolled past; like the dock's own override it is not a place to hide a
   * narrow-viewport restyle, a height cap or a `display: none`.
   *
   * The background is one of the three because the pin overlays the dock's
   * tail while it is pinned — measured, 13px on darwin and 53px with the tail
   * inflated 40px — and two texts printing over each other is not a fix. It is
   * the DOCK's own tint (`.assistant-foot { background: var(--assist-tint) }`),
   * so at rest the declaration is invisible.
   */
  it('the trigger pin changes NOTHING but `position`, `top` and the dock tint', () => {
    const block = mediaBlocks(assistantCss).find((b) => b.query === SHORT_AND_NARROW)!;
    const decls = declarations(ruleBody(block.body, '.assistant-capabilities'));
    expect(decls.map(([p]) => p)).toEqual(['position', 'top', 'background']);
    // The dock's own tint, not a new colour invented for a narrow viewport.
    expect(Object.fromEntries(decls).background).toBe('var(--assist-tint)');
  });

  /*
   * The three alternatives the review refused. None of them is a thing this fix
   * could have quietly done instead, and each has a mechanical signature.
   */
  it('the claim was not shortened and the dock did not gain a height cap', () => {
    expect(ASSISTANT_NO_MODEL_CLAIM.length).toBe(92);

    const block = mediaBlocks(assistantCss).find((b) => b.query === SHORT_AND_NARROW)!;
    // no rule in the band caps or hides the disclosure or the dock
    for (const sel of ['.assistant-foot', '.assistant-no-model']) {
      const body = ruleBody(block.body, sel);
      expect(body).not.toMatch(/max-height/);
      expect(body).not.toMatch(/display:\s*none/);
      expect(body).not.toMatch(/overflow(-y)?:\s*hidden/);
      expect(body).not.toMatch(/font-size/);
    }
  });
});

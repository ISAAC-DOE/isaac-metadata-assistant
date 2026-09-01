/**
 * WCAG 2.x relative luminance and contrast ratio — ONE implementation.
 *
 * ── Why this file exists ────────────────────────────────────────────────────
 *
 * The repository had THREE byte-similar copies of these eight lines, in
 * `__tests__/a11y-landmarks-headings-and-tabs.test.tsx`,
 * `__tests__/stats-charts.test.tsx` and
 * `__tests__/evidence-selection-state-affordance.test.tsx`. The first of them
 * carries a note explaining the duplication — *"duplicated rather than shared
 * because the two files test unrelated surfaces and a shared helper module for
 * eight lines would be the worse trade"* — and that judgement was reasonable
 * for two files testing two components.
 *
 * It stops being reasonable at the point where a test asserts a claim about the
 * WHOLE PALETTE, because then the formula is no longer incidental to one
 * component: it is the thing the claim rests on. A fourth private copy would
 * mean the palette guard could disagree with the component guards and nothing
 * would notice. So the extraction is deliberately narrow — the arithmetic only,
 * with no stylesheet parsing, no token knowledge and no opinion about
 * thresholds, all of which stay with the test that needs them.
 *
 * ── Provenance of the numbers ───────────────────────────────────────────────
 *
 * The formula is unchanged from those copies, character for character in the
 * expression, so it cannot silently disagree with figures already recorded
 * elsewhere in this repository. `palette-contrast.test.tsx` re-derives the two
 * figures `CLAUDE.md` §11 and `a11y-baseline.ts` both publish — #78838f on
 * #ffffff = 3.86:1 and #5b6570 on #ffffff = 5.93:1 — and fails if either moves,
 * which is what makes every OTHER ratio this module returns trustworthy rather
 * than merely plausible.
 *
 * Input must be a 6-digit `#rrggbb`. Shorthand and alpha are deliberately not
 * accepted: every colour in `tokens.css` is 6-digit, and silently mis-parsing a
 * 4-digit value would understate a failure.
 */

/** The three sRGB channels of `#rrggbb`, each in 0..1. */
const srgbOf = (hex: string): number[] =>
  [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);

/** WCAG 2.x relative luminance. */
export const relativeLuminance = (hex: string): number =>
  srgbOf(hex)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    .reduce((acc, c, i) => acc + [0.2126, 0.7152, 0.0722][i] * c, 0);

/** WCAG 2.x contrast ratio. Order-independent: (L1 + 0.05) / (L2 + 0.05). */
export const contrastRatio = (a: string, b: string): number => {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

/**
 * The colour a foreground COMPOSITES to when an ancestor carries `opacity`.
 *
 * Not used to assert a pass anywhere — it exists so a test can state, with a
 * number, that darkening a token does not reach text under an ancestor
 * `opacity` WITHOUT DESTROYING THE RAMP. That is cause (b) of FINDING A11Y-01
 * in `e2e/a11y-baseline.ts`, and it is the half of the debt a palette change
 * cannot close.
 *
 * THE QUALIFICATION IS NOT A HEDGE, AND IT IS A CORRECTION. This docstring, and
 * three other sites, used to say flatly that "darkening a token cannot reach
 * them". That is arithmetically FALSE and was published without being checked.
 * Composited on white, a neutral grey still clears 4.5:1 at `opacity: .72` up
 * to #414141, at .82 up to #585858 and at .85 up to #5e5e5e — all three
 * re-derived BY SEARCH and asserted in `palette-contrast.test.ts`. So a dark
 * enough tertiary DOES reach them. What it cannot do is remain a tertiary: all
 * three of those values are darker than `--text-muted` #5b6570, the rung
 * IMMEDIATELY above the tertiary, and the .72 one is darker than
 * `--text-secondary` #46515f, two rungs above. The token would have to sit BELOW
 * the tiers it exists to sit below, and the hierarchy would be gone. The opacity
 * is what has to go — but for that reason, not for an impossibility that does
 * not hold.
 *
 * THIS IS AN APPROXIMATION AND MUST BE LABELLED AS ONE WHEREVER IT IS QUOTED.
 * It composites in sRGB with a round-to-nearest per channel. A browser's actual
 * composite differs by a channel step or two: `a11y-baseline.ts` records axe
 * reporting `#8e98a2` for `--text-tertiary` #78838f at `opacity: .82`, where
 * this function returns `#9099a3`. Close enough to prove a ratio still fails;
 * NOT close enough to transcribe into a `foregrounds` list.
 */
export const compositeOver = (fg: string, alpha: number, bg: string): string =>
  '#' +
  [1, 3, 5]
    .map((i) => {
      const f = parseInt(fg.slice(i, i + 2), 16);
      const b = parseInt(bg.slice(i, i + 2), 16);
      return Math.round(f * alpha + b * (1 - alpha))
        .toString(16)
        .padStart(2, '0');
    })
    .join('');

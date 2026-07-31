/**
 * Focus-indicator detection, shared by `keyboard.spec.ts` and proved
 * non-vacuous by `self-check.spec.ts`.
 *
 * ── Why this is a DIFFERENCE test, not a "is something painted" test ────────
 *
 * The first version asked only `getComputedStyle(el).boxShadow !== 'none'`.
 * That is not a focus indicator — it is a box-shadow, and this app paints
 * plenty of them at rest (`screens.css:825`, `workflow.css:62`,
 * `schema-browser.css:244`, `assistant.css:1472`, every raised card and every
 * selected row). Any of those components could add `outline: none` tomorrow,
 * lose its focus ring entirely, and still be reported as "visible".
 *
 * So the probe now measures the element TWICE — once focused, once not — and
 * requires that focusing actually CHANGED one of the properties a sighted
 * keyboard user could perceive as a ring: outline, box-shadow, border,
 * background colour, or text decoration.
 *
 * ── How the unfocused reading is taken, and why that is safe ────────────────
 *
 * Same element, same DOM position, same ancestors: `el.blur()`, read, then
 * `el.focus({ preventScroll: true })` — all three synchronous, inside ONE
 * `page.evaluate`. That matters:
 *
 *   * React 18 batches state updates from the resulting focusout/focusin into
 *     a microtask, so the DOM cannot change underneath the measurement;
 *   * `document.activeElement` is restored before the caller regains control,
 *     so the caller's next `Tab` continues from the right place;
 *   * scroll position is untouched, so no layout probe downstream is disturbed.
 *
 * A cloned "resting proxy" was considered and rejected: `:nth-child`,
 * `:first-child` and sibling-combinator rules make a clone a different element
 * as far as the cascade is concerned, and a proxy that differs for unrelated
 * reasons would report a ring that is not there — the exact failure being fixed.
 *
 * `:focus-visible` is NOT re-established by the programmatic re-focus, and does
 * not need to be: the focused reading was already taken. Callers must still
 * ARRIVE by pressing Tab — only real keyboard focus engages `:focus-visible`,
 * which is where this app's global ring lives (`src/styles/base.css:79`).
 *
 * Honest limit: this proves a focus indicator EXISTS and is caused by focus. It
 * does not measure WCAG 2.4.11/1.4.11 contrast or area of that indicator.
 */

import type { Page } from '@playwright/test';

/** The computed properties a focus indicator can plausibly live in. */
const INDICATOR_PROPS = [
  'outlineStyle',
  'outlineWidth',
  'outlineColor',
  'outlineOffset',
  'boxShadow',
  'borderTopWidth',
  'borderRightWidth',
  'borderBottomWidth',
  'borderLeftWidth',
  'borderTopStyle',
  'borderRightStyle',
  'borderBottomStyle',
  'borderLeftStyle',
  'borderTopColor',
  'borderRightColor',
  'borderBottomColor',
  'borderLeftColor',
  'backgroundColor',
  'textDecorationLine',
  'textDecorationColor',
] as const;

export interface FocusInfo {
  /** Stable-ish identity for reporting duplicates. */
  key: string;
  /** True when focusing this element demonstrably changes how it is PAINTED. */
  visible: boolean;
  /**
   * Which of `INDICATOR_PROPS` differ between the focused and resting states —
   * raw diagnostics. Not the same as `indicators`: this app's global
   * `:focus-visible` rule sets `outline-offset: 2px`, so a control that kills
   * the outline with `outline: none` still shows an `outlineOffset` diff while
   * painting nothing at all.
   */
  changed: string[];
  /**
   * The PERCEPTIBLE indicators — the subset of `changed` that a sighted user
   * could actually see. `visible` is `indicators.length > 0`.
   */
  indicators: string[];
  /** Human-readable focused-vs-resting rendering, for failure messages. */
  outline: string;
  /** Human-readable focused-vs-resting rendering, for failure messages. */
  boxShadow: string;
  /**
   * `false` when the resting reading could not be taken because blurring the
   * element removed it from the document (a menu that closes on focusout). The
   * verdict then falls back to "an outline is painted", and says so.
   */
  restingMeasured: boolean;
}

export async function activeElementFocusInfo(page: Page): Promise<FocusInfo | null> {
  return page.evaluate((PROPS: readonly string[]) => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body || el === document.documentElement) return null;

    const snapshot = (node: HTMLElement): Record<string, string> => {
      const st = getComputedStyle(node);
      const out: Record<string, string> = {};
      for (const p of PROPS) out[p] = String((st as unknown as Record<string, unknown>)[p] ?? '');
      return out;
    };

    const transparent = (c: string) => /rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*0\s*\)/.test(c) || c === 'transparent';
    const outlinePainted = (s: Record<string, string>) =>
      s.outlineStyle !== 'none' && parseFloat(s.outlineWidth || '0') > 0 && !transparent(s.outlineColor);
    const describeOutline = (s: Record<string, string>) => `${s.outlineStyle} ${s.outlineWidth} ${s.outlineColor}`;

    const focused = snapshot(el);

    // Take the resting reading on the SAME element, synchronously, and put
    // focus straight back.
    let resting: Record<string, string> | null = null;
    const restore = document.activeElement === el;
    el.blur();
    if (el.isConnected) resting = snapshot(el);
    if (restore && el.isConnected) el.focus({ preventScroll: true });

    const changed = resting ? PROPS.filter((p) => focused[p] !== resting![p]) : [];

    /*
     * A raw diff is not enough: it counts changes that paint nothing. The
     * global rule `src/styles/base.css:79` sets `outline-offset: 2px` alongside
     * the outline, so a control that does `outline: none` on focus still
     * reports an `outlineOffset` diff while showing the user nothing. Each
     * indicator below therefore has to be BOTH different and painted.
     */
    const borderSig = (s: Record<string, string>) =>
      ['Top', 'Right', 'Bottom', 'Left']
        .map((side) => `${s[`border${side}Width`]} ${s[`border${side}Style`]} ${s[`border${side}Color`]}`)
        .join(' | ');
    const borderPainted = (s: Record<string, string>) =>
      ['Top', 'Right', 'Bottom', 'Left'].some(
        (side) => s[`border${side}Style`] !== 'none' && parseFloat(s[`border${side}Width`] || '0') > 0
      );

    const indicators: string[] = [];
    if (resting) {
      if (outlinePainted(focused) && (!outlinePainted(resting) || describeOutline(focused) !== describeOutline(resting)))
        indicators.push('outline');
      if (focused.boxShadow !== 'none' && focused.boxShadow !== resting.boxShadow) indicators.push('box-shadow');
      if (borderPainted(focused) && borderSig(focused) !== borderSig(resting)) indicators.push('border');
      if (focused.backgroundColor !== resting.backgroundColor && !transparent(focused.backgroundColor))
        indicators.push('background');
      if (
        focused.textDecorationLine !== 'none' &&
        (focused.textDecorationLine !== resting.textDecorationLine ||
          focused.textDecorationColor !== resting.textDecorationColor)
      )
        indicators.push('text-decoration');
    } else if (outlinePainted(focused)) {
      // No resting reading available. Fall back to "an outline is painted" —
      // weaker, and flagged by `restingMeasured: false`.
      indicators.push('outline (unverified: no resting reading)');
    }

    const visible = indicators.length > 0;

    const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    return {
      key: `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''}${el.id ? '#' + el.id : ''}:${(
        el.getAttribute('aria-label') ??
        el.textContent ??
        ''
      )
        .trim()
        .slice(0, 30)}`,
      visible,
      changed: changed as string[],
      indicators,
      outline: resting
        ? `focused "${describeOutline(focused)}" vs resting "${describeOutline(resting)}"`
        : `focused "${describeOutline(focused)}" (resting reading unavailable)`,
      boxShadow: resting
        ? focused.boxShadow === resting.boxShadow
          ? `"${focused.boxShadow}" — UNCHANGED by focus, so it is a resting shadow, not a focus ring`
          : `focused "${focused.boxShadow}" vs resting "${resting.boxShadow}"`
        : `"${focused.boxShadow}" (resting reading unavailable)`,
      restingMeasured: resting !== null,
    };
  }, INDICATOR_PROPS as readonly string[]);
}

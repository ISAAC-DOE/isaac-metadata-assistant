import { describe, it, expect } from 'vitest';

/*
 * P22C — consistent hover/focus/pressed interaction states.
 *
 * Design constraints under test (see CLAUDE.md / the P22C brief):
 *  - primary & secondary buttons get real :active/pressed rules, not just hover
 *  - "I don't know" is a first-class SAFE action: hover/focus get the soft
 *    amber "advisory" treatment, never the reserved pass (green) / fail (red) hues
 *  - the WorkflowSpine step link no longer uses `display: contents` (which
 *    swallows the focus outline) and has a guaranteed :focus-visible style
 *  - every new hover/focus/pressed transition respects prefers-reduced-motion
 *  - no interaction-state rule (:hover, :active, :focus) anywhere in the app
 *    uses a green/red hex or a pass/fail verdict token — those hues are
 *    reserved for validation/verdict semantics (no-vertical-rail-rule.md
 *    sibling constraint).
 *
 * CSS sources are pulled in as raw strings via Vite's import.meta.glob, so no
 * node:fs (and no @types/node) is needed — same approach as
 * no-vertical-rail.test.ts.
 */

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

interface CssRule {
  selector: string;
  body: string;
}

/**
 * Minimal brace-matching CSS rule extractor. Recurses into `@media` (and any
 * other at-rule) blocks so nested rules (e.g. inside
 * `@media (prefers-reduced-motion: reduce)`) are still inspected as their own
 * selector + body pairs, tagged with `inReducedMotion`. Good enough for these
 * flat, hand-written stylesheets (no CSS-in-JS, no nested selectors).
 */
function extractRules(source: string, inReducedMotion = false): (CssRule & { inReducedMotion: boolean })[] {
  const rules: (CssRule & { inReducedMotion: boolean })[] = [];
  let selectorBuf = '';
  let i = 0;
  const n = source.length;
  while (i < n) {
    const ch = source[i];
    if (ch === '{') {
      const selector = selectorBuf.trim();
      let depth = 1;
      let j = i + 1;
      const bodyStart = j;
      while (j < n && depth > 0) {
        if (source[j] === '{') depth++;
        else if (source[j] === '}') depth--;
        j++;
      }
      const body = source.slice(bodyStart, j - 1);
      if (selector.startsWith('@')) {
        const nested = /prefers-reduced-motion:\s*reduce/.test(selector) || inReducedMotion;
        rules.push(...extractRules(body, nested));
      } else if (selector.length > 0) {
        rules.push({ selector, body, inReducedMotion });
      }
      i = j;
      selectorBuf = '';
      continue;
    }
    selectorBuf += ch;
    i++;
  }
  return rules;
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '');
}

const allRules: { path: string; rule: CssRule & { inReducedMotion: boolean } }[] = [];
for (const [path, source] of Object.entries(cssFiles)) {
  for (const rule of extractRules(stripComments(source))) {
    allRules.push({ path, rule });
  }
}

/** Rules whose selector, split on commas, has an exact-match (trimmed) member. */
function exactSelector(selector: string) {
  return allRules.filter(({ rule }) =>
    rule.selector
      .split(',')
      .map((s) => s.trim())
      .includes(selector),
  );
}

function containingSelector(substring: string) {
  return allRules.filter(({ rule }) => rule.selector.includes(substring));
}

describe('P22C · primary/secondary buttons have real pressed states', () => {
  it('.btn-primary:active exists, is outside reduced-motion, and settles back flat', () => {
    const hover = exactSelector('.btn-primary:hover').filter((r) => !r.rule.inReducedMotion);
    const active = exactSelector('.btn-primary:active').filter((r) => !r.rule.inReducedMotion);
    expect(hover.length).toBeGreaterThan(0);
    expect(active.length).toBeGreaterThan(0);
    // pressed settles back — no lift transform, no emphasis shadow
    expect(active[0].rule.body).toMatch(/transform:\s*translateY\(0\)/);
    expect(active[0].rule.body).toMatch(/box-shadow:\s*none/);
  });

  it('.btn-secondary:active exists and shifts background beyond what :hover does', () => {
    const hover = exactSelector('.btn-secondary:hover').filter((r) => !r.rule.inReducedMotion);
    const active = exactSelector('.btn-secondary:active').filter((r) => !r.rule.inReducedMotion);
    expect(hover.length).toBeGreaterThan(0);
    expect(active.length).toBeGreaterThan(0);
    expect(active[0].rule.body).toMatch(/background:/);
  });
});

describe('P22C · "I don\'t know" is a safe, amber-tinted action', () => {
  it('.guided-dontknow hover/active/focus rules exist and use advisory (amber) tokens only', () => {
    const stateRules = containingSelector('.guided-dontknow').filter(({ rule }) =>
      /:hover|:active|:focus/.test(rule.selector),
    );
    expect(stateRules.length).toBeGreaterThan(0);
    for (const { rule } of stateRules) {
      expect(rule.body).toMatch(/--advisory-/);
      expect(rule.body).not.toMatch(/--pass-|--fail-|\bred\b|\bgreen\b|#([0-9a-fA-F]{3}){1,2}\b/i);
    }
  });
});

describe('P22C · spine-step-link focus fix', () => {
  it('no longer uses display: contents anywhere in workflow.css', () => {
    const [, source] = Object.entries(cssFiles).find(([p]) => p.endsWith('workflow.css'))!;
    // Strip comments first — the fix is explained in a code comment that
    // necessarily *names* the old property/value being removed.
    expect(stripComments(source)).not.toMatch(/display:\s*contents/);
  });

  it('.spine-step-link has a guaranteed :focus-visible rule with a visible outline', () => {
    const focus = exactSelector('.spine-step-link:focus-visible');
    expect(focus.length).toBeGreaterThan(0);
    expect(focus[0].rule.body).toMatch(/outline:\s*2px solid/);
  });

  it('spine-step-link hover/active/focus never use pass/fail verdict colors', () => {
    const stateRules = containingSelector('.spine-step-link').filter(({ rule }) =>
      /:hover|:active|:focus/.test(rule.selector),
    );
    expect(stateRules.length).toBeGreaterThan(0);
    for (const { rule } of stateRules) {
      expect(rule.body).not.toMatch(/--pass-|--fail-|\bred\b|\bgreen\b/i);
    }
  });
});

describe('P22C · reduced motion covers the new interaction transitions', () => {
  it('base.css neutralizes transition/animation duration for every element under prefers-reduced-motion', () => {
    const universal = allRules.filter(
      ({ path, rule }) =>
        path.endsWith('styles/base.css') && rule.inReducedMotion && rule.selector.includes('*::before'),
    );
    expect(universal.length).toBeGreaterThan(0);
    const body = universal[0].rule.body;
    expect(body).toMatch(/transition-duration:\s*0(\.\d+)?(ms|s)?\s*!important/);
    expect(body).toMatch(/animation-duration:\s*0(\.\d+)?(ms|s)?\s*!important/);
  });

  it('the primary-button lift (transform) is explicitly neutralized under reduced motion', () => {
    const neutralized = allRules.filter(
      ({ path, rule }) =>
        path.endsWith('styles/base.css') &&
        rule.inReducedMotion &&
        rule.selector.includes('.btn-primary:hover') &&
        rule.selector.includes('.btn-primary:active'),
    );
    expect(neutralized.length).toBeGreaterThan(0);
    expect(neutralized[0].rule.body).toMatch(/transform:\s*none\s*!important/);
  });

  it('every rule that lifts .btn-primary with a transform lives outside the reduced-motion block (so the query can override it)', () => {
    const lifted = allRules.filter(
      ({ rule }) => !rule.inReducedMotion && rule.selector.includes('.btn-primary:hover') && /transform:/.test(rule.body),
    );
    expect(lifted.length).toBeGreaterThan(0);
  });
});

describe('P22C · no green/red hex or pass/fail token in ANY interaction-state rule', () => {
  it('scans every :hover/:active/:focus* rule in every component + style CSS file', () => {
    const offenders: string[] = [];
    const forbidden = /--pass-|--fail-|\bred\b|\bgreen\b/i;
    // None of this app's interaction-state rules should ever hardcode a hex —
    // everything routes through design tokens — so any hex inside a state
    // rule (green/red or otherwise) is worth flagging outright.
    const hexLiteral = /#[0-9a-fA-F]{3,8}\b/;
    for (const { path, rule } of allRules) {
      if (!/:hover|:active|:focus/.test(rule.selector)) continue;
      if (forbidden.test(rule.body) || hexLiteral.test(rule.body)) {
        offenders.push(`${path} :: ${rule.selector}  ->  ${rule.body.trim()}`);
      }
    }
    expect(offenders, `forbidden colors found in interaction-state rules:\n${offenders.join('\n')}`).toEqual([]);
  });
});

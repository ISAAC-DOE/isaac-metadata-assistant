/**
 * A3 / FINDING A11Y-01 — THE NEUTRAL INK PALETTE CLEARS WCAG AA, AND THE
 * EXCEPTIONS ARE ENUMERATED RATHER THAN ASSUMED.
 *
 * ── What was wrong ──────────────────────────────────────────────────────────
 *
 * `--text-tertiary` was #78838f (3.86:1 on white, 3.28:1 on the assistant
 * panel) and `--text-quaternary` was #9aa4af (2.53:1 / 2.15:1). Between them
 * they carried 291 declarations, of which 253 were ordinary text under 18.66px
 * and 8 more were input placeholders. Not a decorative-grey problem: the
 * failing set included an experiment id, a schema field path, a record's
 * filename, the app version, evidence provenance keys, a blocked workflow
 * step's label and a 10.5px/600 subsection HEADING. `e2e/a11y-baseline.ts`
 * records the app-wide consequence as 1,610 failing axe nodes.
 *
 * ── What this file guards, and why each guard is shaped the way it is ───────
 *
 * The obvious test — "assert two hexes are dark enough" — is worth almost
 * nothing: it passes if the tokens are renamed, if nothing uses them, if a new
 * lighter token appears beside them, or if a darker fill appears underneath
 * them. Each `it` below closes one of those escapes:
 *
 *   1. the CLASSIFICATION is total — every `--text-*` token declared in
 *      `tokens.css` is registered as informational or non-informational, by set
 *      equality, so a rename or an addition fails here rather than silently
 *      widening the palette;
 *   2. every INFORMATIONAL token clears 4.5:1 on every ground it can be painted
 *      on — and the ground list is itself re-derived from the stylesheets, so a
 *      new fill cannot appear un-assessed;
 *   3. every NON-INFORMATIONAL token is used only at enumerated sites, again by
 *      set equality, and each site's exemption BASIS is verified mechanically —
 *      `:disabled`/`not-allowed` for an inactive control, `aria-hidden="true"`
 *      in the markup for a decorative mark;
 *   4. vacuity guards: the arithmetic reproduces two figures this repository
 *      already publishes, the discarded literals really do fail, the token
 *      under test really is used, and no usage relies on the large-text
 *      threshold;
 *   5. the residue this change CANNOT close is asserted as still open, with
 *      numbers, so nobody records A11Y-01 as finished.
 *
 * ── One theme ───────────────────────────────────────────────────────────────
 *
 * "Every theme that exists" is one theme. That is asserted rather than assumed
 * (`no second theme exists`, below) — if a dark theme is ever added, that guard
 * fails and the ratios here must be re-derived for it.
 */

import { describe, expect, it } from 'vitest';
import { compositeOver, contrastRatio, relativeLuminance } from '../test/contrast';

/* ── stylesheet access ─────────────────────────────────────────────────────── */

const cssModules = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** Path relative to `src/` -> source with comments blanked, so prose never satisfies a guard. */
const SHEETS: ReadonlyMap<string, string> = new Map(
  Object.entries(cssModules).map(([p, src]) => [
    p.replace(/^\.\.\//, ''),
    src.replace(/\/\*[\s\S]*?\*\//g, ' '),
  ]),
);

const TOKENS_SHEET = (() => {
  const s = SHEETS.get('styles/tokens.css');
  if (s === undefined) throw new Error('styles/tokens.css was not globbed');
  return s;
})();

interface Rule {
  readonly file: string;
  readonly selector: string;
  readonly decls: string;
}

/** Every top-level or at-rule-nested declaration block, across every stylesheet. */
const RULES: readonly Rule[] = [...SHEETS.entries()].flatMap(([file, src]) =>
  [...src.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    file,
    selector: m[1].replace(/\s+/g, ' ').trim(),
    decls: m[2],
  })),
);

/** A token's authored value in `tokens.css`, verbatim. */
function declaredValue(token: string): string {
  const m = new RegExp(`${token}\\s*:\\s*([^;]+);`).exec(TOKENS_SHEET);
  if (m === null) throw new Error(`${token} is not declared in styles/tokens.css`);
  return m[1].trim();
}

/**
 * A token's resolved 6-digit hex, following at most one chain of single-`var()`
 * aliases. `--text-quaternary` is deliberately such an alias, and resolving it
 * here is what lets the ratio guard cover it WITHOUT the value being repeated
 * in two places where the two copies could drift apart.
 */
function declaredHex(token: string, seen: readonly string[] = []): string {
  if (seen.includes(token)) throw new Error(`${token} aliases in a cycle: ${seen.join(' -> ')}`);
  const value = declaredValue(token);
  if (/^#[0-9a-f]{6}$/i.test(value)) return value.toLowerCase();
  const alias = /^var\((--[a-z0-9-]+)\)$/.exec(value);
  if (alias !== null) return declaredHex(alias[1], [...seen, token]);
  throw new Error(
    `${token} resolves to "${value}", which is neither a 6-digit hex nor a single var() alias`,
  );
}

/* ── registry 1 · the ink tokens, classified ───────────────────────────────── */

/**
 * INFORMATIONAL INK — may carry meaning, and therefore owes WCAG 1.4.3's 4.5:1
 * on every ground it can be painted on. `--text-quaternary` is in this list
 * because that is what its 71 declarations DO; it reaches the value through an
 * alias rather than a hex of its own.
 */
const INFORMATIONAL_INK = [
  '--text-heading',
  '--text-primary',
  '--text-strong',
  '--text-secondary',
  '--text-muted',
  '--text-slate',
  '--text-tertiary',
  '--text-quaternary',
] as const;

/**
 * NON-INFORMATIONAL INK — exempt from 1.4.3 because of what it is used FOR.
 * Each entry's `basis` is CHECKED below, not taken on trust, and the sites are
 * enumerated in `EXEMPT_SITES`.
 */
const NON_INFORMATIONAL_INK = [
  {
    token: '--text-inactive',
    why:
      'The value `--text-quaternary` used to carry (#9aa4af). WCAG 1.4.3 exempts text that is ' +
      'part of an INACTIVE user-interface component, which is exactly what a `:disabled` button ' +
      'with `cursor: not-allowed` is. It exists as a separate name so that the exemption is ' +
      'claimed explicitly at two sites rather than inherited silently by 71.',
  },
  {
    token: '--text-faint',
    why:
      'An `aria-hidden="true"` workflow-spine disc for a blocked or not-yet-reached step. The ' +
      'step NAME beside it is `--text-tertiary`; the disc carries no information of its own.',
  },
  {
    token: '--text-disabled',
    why:
      'Two classes, both exempt: `aria-hidden="true"` chevrons and step discs whose meaning is ' +
      'carried by the adjacent label, and inactive controls. NOTE that `e2e/a11y-baseline.ts` ' +
      'still describes this token as painting the Evidence preview `.ln` line numbers as TEXT ' +
      'at 11.5px — that is STALE: `evidence.css` moved `.preview-line .ln` to `--text-slate` ' +
      'before this change, and the site set below is re-derived rather than quoted.',
  },
] as const;

/* ── registry 2 · the grounds ──────────────────────────────────────────────── */

/**
 * Every LIGHT fill (relative luminance >= 0.6) that any stylesheet paints, split
 * into the ones text can land on and the ones it cannot. `the ground registry
 * accounts for every light fill` asserts this split is TOTAL by set equality, so
 * a new tint added anywhere fails here until it is classified.
 *
 * Dark fills are deliberately outside the split: `.graph-canvas` is the app's
 * one dark surface and it uses its own `--gc-*` scale, verified separately by
 * `no shared ink token is painted inside the dark graph canvas`.
 */
const TEXT_GROUNDS = [
  '--surface',
  '--surface-subtle',
  '--screen-base',
  '--selected-row-bg',
  '--assist-panel-bg',
  '--assist-tint',
  '--action-tint',
  '--cited-line-bg',
  '--border-faint',
  '--border-hair',
  '--cover-bg',
  '--missing-bg',
  '--inferred-bg',
  '--confirmed-bg',
  '--verified-bg',
  '--pass-bg',
  '--fail-bg',
  '--advisory-bg',
  '--needsyou-bg',
] as const;

/**
 * Light fills that are NOT text grounds. #626c77 fails 4.5:1 on all five, so
 * these justifications are load-bearing rather than decorative — each one is the
 * reason a measured failure is not a defect. Re-verified at this commit.
 */
const NON_TEXT_FILLS = [
  {
    token: '--app-canvas',
    why:
      '`.app` paints it and `.screen-card` covers `.app` entirely except for 16px of padding; ' +
      '`body` paints it beneath that. No rule renders text against it.',
  },
  {
    token: '--border-input',
    why: 'Three rules, all of them a 1px separator or the 5px `.progress-seg` track.',
  },
  {
    token: '--border',
    why: 'One rule: the 14x8px `.tutorial-arrow` pointer.',
  },
  {
    token: '--border-strong',
    why: 'Two rules: the 2px `.spine-step` connector rail and the 12x12px chart legend swatch.',
  },
  {
    token: '--action-selected-border',
    why:
      'Only `:active` fills of action-tinted buttons, whose text is `--action-pressed` (action ' +
      'blue), never neutral ink. Asserted below rather than asserted here.',
  },
] as const;

/* ── registry 3 · the exempt sites ─────────────────────────────────────────── */

type ExemptionBasis = 'inactive-control' | 'aria-hidden-mark';

interface ExemptSite {
  readonly file: string;
  readonly selector: string;
  readonly token: string;
  readonly basis: ExemptionBasis;
  /** For `aria-hidden-mark`: the class whose every JSX tag must carry `aria-hidden`. */
  readonly mark?: string;
  readonly why: string;
}

/**
 * EVERY use of a non-informational token in the application, enumerated with a
 * justification. `every non-informational token is used only at an enumerated
 * site` compares this against what the stylesheets actually do, by set equality
 * in both directions — a new use fails, and so does a stale entry.
 */
const EXEMPT_SITES: readonly ExemptSite[] = [
  {
    file: 'styles/base.css',
    selector: '.btn-action:disabled',
    token: '--text-inactive',
    basis: 'inactive-control',
    why: 'Disabled action button. 2.15:1 at worst, and 1.4.3 exempts an inactive component.',
  },
  {
    file: 'styles/base.css',
    selector: '.btn-danger-quiet:disabled',
    token: '--text-inactive',
    basis: 'inactive-control',
    why: 'Disabled destructive trigger. Same exemption as the row above.',
  },
  {
    file: 'screens/screens.css',
    selector: '.api-keys-create-btn',
    token: '--text-disabled',
    basis: 'inactive-control',
    why:
      'Permanently inactive: `cursor: not-allowed` and a dashed border, with no enabled state ' +
      'anywhere in the stylesheet. Not marked `:disabled`, which is why the basis check accepts ' +
      '`cursor: not-allowed` as well as the pseudo-class.',
  },
  {
    file: 'screens/graph/evidence-graph.css',
    selector: '.evgraph-btn:disabled',
    token: '--text-disabled',
    basis: 'inactive-control',
    why: 'Disabled pagination control on the evidence graph.',
  },
  {
    file: 'screens/graph/experiment-graph.css',
    selector: '.expgraph-btn:disabled',
    token: '--text-disabled',
    basis: 'inactive-control',
    why: 'Disabled pagination control on the experiment graph.',
  },
  {
    file: 'components/assistant.css',
    selector: '.assistant-prompt .chev',
    token: '--text-disabled',
    basis: 'aria-hidden-mark',
    mark: 'chev',
    why: 'Decorative disclosure chevron beside its own label.',
  },
  {
    file: 'components/queue.css',
    selector: '.exp-chevron',
    token: '--text-disabled',
    basis: 'aria-hidden-mark',
    mark: 'exp-chevron',
    why: 'Decorative row chevron; the row is a link with its own accessible name.',
  },
  {
    file: 'components/schema-browser.css',
    selector: '.schema-field-chevron',
    token: '--text-disabled',
    basis: 'aria-hidden-mark',
    mark: 'schema-field-chevron',
    why: 'Decorative field-row chevron.',
  },
  {
    file: 'screens/screens.css',
    selector: '.source-index-chevron',
    token: '--text-disabled',
    basis: 'aria-hidden-mark',
    mark: 'source-index-chevron',
    why: 'Decorative source-index chevron.',
  },
  {
    file: 'screens/screens.css',
    selector: '.concept-lookup-chevron',
    token: '--text-disabled',
    basis: 'aria-hidden-mark',
    mark: 'concept-lookup-chevron',
    why: 'Decorative concept-row chevron.',
  },
  {
    file: 'components/runner.css',
    selector: '.stage.upcoming .stage-disc',
    token: '--text-disabled',
    basis: 'aria-hidden-mark',
    mark: 'stage-disc',
    why:
      'The numeral inside a not-yet-reached pipeline step disc. The disc is `aria-hidden`; the ' +
      'step name beside it is `--text-secondary` and carries the meaning.',
  },
  {
    file: 'components/workflow.css',
    selector: '.spine-step.blocked .spine-disc, .spine-step.skeleton .spine-disc',
    token: '--text-faint',
    basis: 'aria-hidden-mark',
    mark: 'spine-disc',
    why: 'Blocked / skeleton workflow-spine disc, `aria-hidden`; the label carries the meaning.',
  },
];

/* ── helpers over the parsed stylesheets ───────────────────────────────────── */

/** Every rule that assigns `token` to any property. */
function rulesUsing(token: string): readonly Rule[] {
  const re = new RegExp(`(?:^|[\\s;])[-a-z]+\\s*:\\s*[^;]*var\\(${token}\\)`);
  return RULES.filter((r) => re.test(r.decls));
}

/** Every token named in any `background` / `background-color` value. */
function backgroundTokens(): ReadonlySet<string> {
  const out = new Set<string>();
  for (const rule of RULES) {
    for (const m of rule.decls.matchAll(/background(?:-color)?\s*:\s*([^;}]*)/g)) {
      for (const v of m[1].matchAll(/var\((--[a-z0-9-]+)/g)) out.add(v[1]);
    }
  }
  return out;
}

const tsxSources = import.meta.glob('../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** Every JSX opening tag in the app's TS/TSX sources. */
const JSX_TAGS: readonly string[] = Object.values(tsxSources).flatMap((src) =>
  [...src.matchAll(/<[A-Za-z][^>]*>/g)].map((m) => m[0]),
);

/* ── 1 · the classification is total ───────────────────────────────────────── */

describe('A3 · every ink token is classified', () => {
  it('registers every --text-* token declared in tokens.css, and nothing else', () => {
    const declared = [...TOKENS_SHEET.matchAll(/(--text-[a-z0-9-]+)\s*:/g)].map((m) => m[1]);
    // Vacuity: a palette that lost its tokens must not pass by having nothing to check.
    expect(declared.length, 'tokens.css declares no --text-* tokens — the scan is broken')
      .toBeGreaterThanOrEqual(11);
    const registered = [...INFORMATIONAL_INK, ...NON_INFORMATIONAL_INK.map((e) => e.token)];
    expect(
      [...new Set(declared)].sort(),
      'a --text-* token was added, removed or renamed without being classified as ' +
        'informational (owes 4.5:1) or non-informational (owes an enumerated exemption)',
    ).toEqual([...registered].sort());
  });

  it('resolves every registered token to a 6-digit hex', () => {
    for (const token of [...INFORMATIONAL_INK, ...NON_INFORMATIONAL_INK.map((e) => e.token)]) {
      expect(declaredHex(token), `${token} must resolve to a hex`).toMatch(/^#[0-9a-f]{6}$/);
    }
  });
});

/* ── 2 · the ratios ────────────────────────────────────────────────────────── */

describe('A3 · informational ink clears WCAG AA on every ground it can sit on', () => {
  it('the ground registry accounts for every light fill in the application', () => {
    const light = [...backgroundTokens()].filter((t) => {
      let hex: string;
      try {
        hex = declaredHex(t);
      } catch {
        return false; // component-scoped token, not part of the shared palette
      }
      return relativeLuminance(hex) >= 0.6;
    });
    // Vacuity: the sweep must actually be finding fills.
    expect(light.length, 'no light background fill was found — the background scan is broken')
      .toBeGreaterThanOrEqual(15);
    const classified = [...TEXT_GROUNDS, ...NON_TEXT_FILLS.map((f) => f.token)];
    expect(
      light.sort(),
      'a light background fill is neither registered as a text ground nor justified as a ' +
        'non-text fill. Classify it: if text can land on it, add it to TEXT_GROUNDS and the ' +
        'ratio guard below will judge it.',
    ).toEqual([...classified].sort());
  });

  it('every informational token clears 4.5:1 on every text ground', () => {
    // Vacuity: both sides of the cross-product must be non-trivial.
    expect(INFORMATIONAL_INK.length).toBeGreaterThanOrEqual(8);
    expect(TEXT_GROUNDS.length).toBeGreaterThanOrEqual(15);

    for (const token of INFORMATIONAL_INK) {
      const fg = declaredHex(token);
      for (const groundToken of TEXT_GROUNDS) {
        const bg = declaredHex(groundToken);
        const ratio = contrastRatio(fg, bg);
        expect(
          ratio,
          `${token} ${fg} on ${groundToken} ${bg} is ${ratio.toFixed(2)}:1 — below the 4.5:1 ` +
            'WCAG 1.4.3 requires for text under 18.66px bold. Every declaration using this ' +
            'token renders meaningful text, so the large-text threshold does not apply.',
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it('the two A3 tokens resolve to the same value, and cannot drift apart', () => {
    // The alias is the mechanism, and it is asserted as such: a future edit that
    // replaces it with a repeated hex would let the two names diverge silently.
    expect(
      declaredValue('--text-quaternary'),
      '--text-quaternary must remain a single var() alias of --text-tertiary, not a repeated ' +
        'hex — two copies of one value are two things that can drift',
    ).toBe('var(--text-tertiary)');
    expect(declaredHex('--text-quaternary')).toBe(declaredHex('--text-tertiary'));
  });

  it('no shared ink token is painted inside the dark graph canvas', () => {
    // The one dark surface uses its own `--gc-*` scale. Darkening a shared ink
    // token would REDUCE contrast there, so this asserts the isolation the fix
    // relies on rather than assuming it.
    const leaks = RULES.filter(
      (r) => /graph-canvas(?![-a-z])/.test(r.selector) && /var\(--text-/.test(r.decls),
    );
    expect(
      leaks.map((r) => `${r.file} ${r.selector}`),
      'a rule scoped INSIDE the dark graph canvas uses a shared light-theme ink token',
    ).toEqual([]);
  });
});

/* ── 2b · the tinted status pairs ──────────────────────────────────────────── */

/**
 * Each status/evidence motif declares its own ink and its own tint, and the ink
 * is only ever painted on that tint. This is in scope because A3 changed one of
 * them: `--missing-text` carried the SAME failing #78838f as `--text-tertiary`
 * (3.62:1 on `--missing-bg`) and is now #626c77 (5.02:1). Guarding the whole set
 * rather than just that one is what stops the fix being a coincidence.
 */
const TINTED_PAIRS = [
  ['--verified-text', '--verified-bg'],
  ['--confirmed-text', '--confirmed-bg'],
  ['--inferred-text', '--inferred-bg'],
  ['--missing-text', '--missing-bg'],
  ['--needsyou-text', '--needsyou-bg'],
  ['--advisory-text', '--advisory-bg'],
  ['--pass-text', '--pass-bg'],
  ['--fail-text', '--fail-bg'],
  ['--cover-text', '--cover-bg'],
  ['--assist-text', '--assist-tint'],
] as const;

/**
 * The ONE tinted pair below 4.5:1, named with its measured ratio rather than
 * skipped. It is cause (c) of FINDING A11Y-01 — a saturated CATEGORY colour, not
 * a neutral ink — and `e2e/a11y-baseline.ts` records it with 265 instances.
 * Deliberately NOT fixed here: A3 is the neutral palette, and re-hueing the
 * "verified" teal is a motif decision with its own blast radius. Recorded so it
 * cannot be quietly forgotten, and bounded so a SECOND failure cannot join it.
 */
const TINTED_EXCEPTIONS: ReadonlyMap<string, number> = new Map([['--verified-text', 4.21]]);

describe('A3 · tinted status ink clears AA on its own tint', () => {
  it('every pair passes, except the one recorded exception', () => {
    expect(TINTED_PAIRS.length).toBeGreaterThanOrEqual(10);
    for (const [ink, tint] of TINTED_PAIRS) {
      const ratio = contrastRatio(declaredHex(ink), declaredHex(tint));
      const expected = TINTED_EXCEPTIONS.get(ink);
      if (expected !== undefined) {
        // A ratchet, not a waiver: the number may improve, but it must not get
        // worse, and if it starts passing the exception must be retired.
        expect(
          ratio,
          `${ink} on ${tint} is ${ratio.toFixed(2)}:1 — worse than the ${expected}:1 recorded ` +
            'for this known A11Y-01 cause-(c) exception',
        ).toBeGreaterThanOrEqual(expected - 0.01);
        continue;
      }
      expect(
        ratio,
        `${ink} on ${tint} is ${ratio.toFixed(2)}:1 — below 4.5:1. Either fix it or add it to ` +
          'TINTED_EXCEPTIONS with its measured ratio and a reason.',
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('the missing-value chip really was on the same failing value A3 discarded', () => {
    // Vacuity + provenance: #78838f is what `--missing-text` carried, and it
    // failed on the chip's own tint. Written out so no token edit can silence it.
    expect(contrastRatio('#78838f', declaredHex('--missing-bg'))).toBeLessThan(4.5);
    expect(declaredHex('--missing-text')).not.toBe('#78838f');
    expect(declaredHex('--missing-text')).toBe(declaredHex('--text-tertiary'));
  });

  it('the recorded exception list is not silently empty or over-wide', () => {
    expect([...TINTED_EXCEPTIONS.keys()]).toEqual(['--verified-text']);
  });
});

/* ── 3 · the exemptions ────────────────────────────────────────────────────── */

describe('A3 · non-informational ink is used only where an exemption applies', () => {
  it('is used at exactly the enumerated sites', () => {
    const actual = NON_INFORMATIONAL_INK.flatMap((e) =>
      rulesUsing(e.token).map((r) => `${r.file} | ${r.selector} | ${e.token}`),
    ).sort();
    // Vacuity: an empty actual set would otherwise agree with an empty registry.
    expect(actual.length, 'no non-informational-ink usage found — the rule scan is broken')
      .toBeGreaterThanOrEqual(10);
    const enumerated = EXEMPT_SITES.map((s) => `${s.file} | ${s.selector} | ${s.token}`).sort();
    expect(
      actual,
      'a sub-AA token is used somewhere it is not justified, or a justification is stale. ' +
        'These tokens fail 4.5:1 by design; a new use must state which WCAG 1.4.3 exemption ' +
        'it claims, and must never be given information to say.',
    ).toEqual(enumerated);
  });

  it('every exemption basis holds mechanically, not by assertion', () => {
    for (const site of EXEMPT_SITES) {
      if (site.basis === 'inactive-control') {
        const rule = RULES.find((r) => r.file === site.file && r.selector === site.selector);
        expect(rule, `${site.file} ${site.selector} not found`).toBeDefined();
        const inactive =
          /:disabled|\[disabled\]|aria-disabled/.test(site.selector) ||
          /cursor\s*:\s*not-allowed/.test(rule!.decls);
        expect(
          inactive,
          `${site.selector} claims the inactive-control exemption but is neither :disabled ` +
            'nor `cursor: not-allowed`',
        ).toBe(true);
        continue;
      }
      const mark = site.mark;
      expect(mark, `${site.selector} claims the aria-hidden exemption but names no class`)
        .toBeTruthy();
      const tags = JSX_TAGS.filter((t) =>
        new RegExp(`["'\\s{]${mark!.replace(/-/g, '\\-')}["'\\s}]`).test(t),
      );
      expect(
        tags.length,
        `no JSX tag carries the class "${mark}" — the exemption cannot be verified`,
      ).toBeGreaterThanOrEqual(1);
      const visible = tags.filter((t) => !/aria-hidden/.test(t));
      expect(
        visible.map((t) => t.replace(/\s+/g, ' ').slice(0, 120)),
        `every element with the class "${mark}" must be aria-hidden — otherwise it is exposed ` +
          `text painted at a sub-AA ratio, not a decorative mark`,
      ).toEqual([]);
    }
  });

  it('the action-tinted pressed fill never carries neutral ink', () => {
    // This is `NON_TEXT_FILLS['--action-selected-border']`'s justification, checked.
    const painted = RULES.filter((r) =>
      /background(?:-color)?\s*:\s*[^;}]*var\(--action-selected-border\)/.test(r.decls),
    );
    expect(painted.length).toBeGreaterThanOrEqual(3);
    for (const rule of painted) {
      expect(
        rule.selector.endsWith(':active'),
        `${rule.file} ${rule.selector} paints --action-selected-border outside an :active ` +
          'state, so it may now be a resting ground and needs a contrast assessment',
      ).toBe(true);
    }
  });
});

/* ── 4 · vacuity guards ────────────────────────────────────────────────────── */

describe('A3 · the guards above can actually fail', () => {
  it('reproduces the two ratios this repository already publishes', () => {
    // CLAUDE.md §11 and e2e/a11y-baseline.ts both carry these. If the arithmetic
    // ever disagrees with them, every other number in this file is suspect.
    expect(contrastRatio('#78838f', '#ffffff')).toBeCloseTo(3.86, 2);
    expect(contrastRatio('#5b6570', '#ffffff')).toBeCloseTo(5.93, 2);
  });

  it('the discarded literals really did fail', () => {
    // Asserted over LITERALS, not over the tokens: if these were written as
    // `declaredHex('--text-tertiary')` the guard would be silenced by the very
    // edit it exists to justify. That is what happened to the `.section-tab`
    // guard in `a11y-landmarks-headings-and-tabs.test.tsx`, which asserted
    // `contrastRatio(declaredHex('--text-tertiary'), ...) < 4.5` and had to be
    // inverted by this change rather than deleted.
    expect(contrastRatio('#78838f', '#ffffff')).toBeLessThan(4.5); // old --text-tertiary
    expect(contrastRatio('#9aa4af', '#ffffff')).toBeLessThan(4.5); // old --text-quaternary
    // And on the ground that actually decided the new value.
    expect(contrastRatio('#646e79', declaredHex('--assist-tint'))).toBeLessThan(4.5);
  });

  it('the tokens under test are actually used, and heavily', () => {
    // A palette guard over a dead token is worth nothing.
    const tertiary = rulesUsing('--text-tertiary').length;
    const quaternary = rulesUsing('--text-quaternary').length;
    expect(tertiary, '--text-tertiary is barely used — re-check that this guard still matters')
      .toBeGreaterThanOrEqual(100);
    expect(quaternary, '--text-quaternary is barely used — the alias may now be removable')
      .toBeGreaterThanOrEqual(40);
  });

  it('no usage of the two A3 tokens relies on the large-text threshold', () => {
    // 3:1 applies at >= 24px, or >= 18.66px bold. If any usage were large text,
    // the 4.5:1 bar asserted above would be stricter than WCAG requires and the
    // justification in the failure messages would be wrong.
    const sizes: number[] = [];
    for (const token of ['--text-tertiary', '--text-quaternary']) {
      for (const rule of rulesUsing(token)) {
        const m = /font-size:\s*([\d.]+)px/.exec(rule.decls);
        if (m !== null) sizes.push(Number(m[1]));
      }
    }
    expect(sizes.length, 'no font-size was found beside these tokens — the scan is broken')
      .toBeGreaterThanOrEqual(20);
    expect(
      Math.max(...sizes),
      'a rule using an A3 token now sets a font-size at or above the WCAG large-text boundary; ' +
        'the 3:1 threshold may apply there and this file assumes 4.5:1 everywhere',
    ).toBeLessThan(18.66);
  });

  it('no second theme exists, so "every theme" is the one measured here', () => {
    const themed = [...SHEETS.entries()].filter(([, src]) =>
      /prefers-color-scheme|\[data-theme/.test(src),
    );
    expect(
      themed.map(([f]) => f),
      'a theme variant appeared. Every ratio in this file was measured for the single light ' +
        'palette; a second theme needs its own ground set and its own measurements.',
    ).toEqual([]);
  });
});

/* ── 5 · the residue this change cannot close ──────────────────────────────── */

describe('A3 · the opacity residue is still open, and says so with numbers', () => {
  /*
   * Cause (b) of FINDING A11Y-01. Three rules put an ancestor `opacity` over
   * text, and compositing drags a PASSING token below AA. Darkening the token
   * cannot reach it — the arithmetic below shows the new #626c77 still failing —
   * so this is asserted as OPEN rather than quietly counted as fixed.
   *
   * The composites are FORMULA-COMPUTED, not browser-measured; `compositeOver`
   * documents why they must not be transcribed into `a11y-baseline.ts`. If the
   * opacity is ever removed, this test fails and the record gets updated, which
   * is the intended behaviour of a ratchet.
   */
  const OPACITY_SITES = [
    { file: 'components/queue.css', selector: '.exp-row.done', alpha: 0.82 },
    { file: 'components/assistant.css', selector: '.upcoming-row', alpha: 0.72 },
    { file: 'components/signals.css', selector: '.advisory-nongating', alpha: 0.85 },
  ] as const;

  it('all three ancestor-opacity rules are still present at the recorded strength', () => {
    for (const site of OPACITY_SITES) {
      const rule = RULES.find((r) => r.file === site.file && r.selector === site.selector);
      expect(rule, `${site.file} ${site.selector} not found`).toBeDefined();
      const m = /(?:^|[\s;])opacity:\s*([\d.]+)/.exec(rule!.decls);
      expect(m, `${site.selector} no longer sets an opacity`).not.toBeNull();
      expect(
        Number(m![1]),
        `${site.selector}'s opacity changed. Re-measure the composited foregrounds in a ` +
          'browser and update e2e/a11y-baseline.ts `foregrounds`.',
      ).toBe(site.alpha);
    }
  });

  it('darkening the token does NOT lift the composited text over 4.5:1', () => {
    const white = declaredHex('--surface');
    const ink = declaredHex('--text-tertiary');
    for (const alpha of [0.82, 0.72]) {
      const composited = compositeOver(ink, alpha, white);
      expect(
        contrastRatio(composited, white),
        `${ink} at opacity ${alpha} composites to ${composited}, which would PASS — if that is ` +
          'real, cause (b) of A11Y-01 is closed and this guard should be retired deliberately ' +
          'rather than left asserting a defect that no longer exists',
      ).toBeLessThan(4.5);
    }
  });
});

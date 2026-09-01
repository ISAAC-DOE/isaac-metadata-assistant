/**
 * A3 / FINDING A11Y-01 — THE NEUTRAL INK PALETTE CLEARS WCAG AA, AND THE
 * EXCEPTIONS ARE ENUMERATED RATHER THAN ASSUMED.
 *
 * ── What was wrong ──────────────────────────────────────────────────────────
 *
 * `--text-tertiary` was #78838f (3.86:1 on white, 3.28:1 on the assistant
 * panel) and `--text-quaternary` was #9aa4af (2.53:1 / 2.15:1). Between them
 * they carried 293 references across 30 stylesheets, of which 284 were `color`
 * declarations — 276 ordinary text under 18.66px and 8 input placeholders — the
 * other 9 being borders and one background. Not a decorative-grey problem: the
 * failing set included an experiment id, a schema field path, a record's
 * filename, the app version, evidence provenance keys, a blocked workflow
 * step's label and a 10.5px/600 subsection HEADING. `e2e/a11y-baseline.ts`
 * records the app-wide consequence as 1,610 failing axe nodes.
 *
 * THOSE FIGURES READ "291 declarations, of which 253 were ordinary text under
 * 18.66px and 8 more were input placeholders" AND WERE NOT REPRODUCIBLE. 253
 * reproduces under no parse tried here; 8 does. They are corrected in place
 * rather than replaced, because the point of the paragraph is the SIZE of the
 * problem and a figure nobody can re-derive cannot establish it. An independent
 * review, parsing differently, measured 291 references and 283 `color` rules —
 * within two of the numbers above, which is the honest precision of this
 * measurement and is why the exact command is given rather than the number
 * alone. Re-derive, from the pre-A3 tree (`f201e78`, or `bebf4e2` — apps/web is
 * identical in both), with comments blanked exactly as `SHEETS` blanks them:
 *
 *     python3 - <<'EOF'
 *     import subprocess, re
 *     REF = 'f201e78'
 *     ls = ['git', 'ls-tree', '-r', '--name-only', REF, 'apps/web/src/']
 *     files = [f for f in subprocess.run(ls, capture_output=True, text=True)
 *              .stdout.split() if f.endswith('.css')]
 *     refs = colors = 0
 *     for f in files:
 *         src = subprocess.run(['git', 'show', f'{REF}:{f}'],
 *                              capture_output=True, text=True).stdout
 *         src = re.sub(r'/[*][\s\S]*?[*]/', ' ', src)
 *         A = r'var\((?:--text-tertiary|--text-quaternary)\)'
 *         refs += len(re.findall(A, src))
 *         colors += len(re.findall(r'(?<![-a-z])color\s*:\s*' + A + r'\s*;', src))
 *     print(refs, colors)   # 293 284
 *     EOF
 *
 * The same script over the working tree, with `--text-quaternary` alone and
 * without the `git show`, prints the alias's own live count (70); the file count
 * is `grep -rl --include='*.css' 'var(--text-quaternary)' apps/web/src | wc -l`
 * (16). `tokens.css` cites both and cannot quote the regex itself, because a
 * CSS comment cannot contain the sequence that ends a CSS comment.
 *
 * ── What this file guards, and why each guard is shaped the way it is ───────
 *
 * The obvious test — "assert two hexes are dark enough" — is worth almost
 * nothing: it passes if the tokens are renamed, if nothing uses them, if a new
 * lighter token appears beside them, or if a darker fill appears underneath
 * them. Each `it` below closes one of those escapes:
 *
 *   1. the CLASSIFICATION is total over VALUE AND USE — every token that
 *      resolves to a hex and is painted by any `color` declaration in any
 *      stylesheet is registered in exactly one usage class, by set equality, so
 *      a rename or an addition fails here rather than silently widening the
 *      palette. A SECOND, NARROWER guard additionally requires every `--text-*`
 *      token DECLARED in `tokens.css` to be classified even if nothing paints
 *      it, so a dead lighter grey cannot sit in the palette waiting to be used;
 *
 *      THE FIRST GUARD USED TO BE THE SECOND ONE ALONE, and the escape it left
 *      is the reason this file is worth reading. An independent review added
 *      `--ink-whisper: #b5bcc4` to `tokens.css`, painted it as 11px text, and
 *      every test here passed. (Its ratio on white is 1.92:1, re-measured here.
 *      The review reported 2.51:1; that does not reproduce, and 2.53:1 is the
 *      retired `--text-quaternary` #9aa4af, so the two figures look transposed.
 *      Which one is right does not change the escape — nothing measured it.) The docstring's own wording —
 *      "every `--text-*` token" — was literally true; the prose around it ("the
 *      CLASSIFICATION is total", "the split is the contract", "the distinction
 *      cannot decay back into a lighter grey") claimed a coverage a NAMESPACE
 *      cannot give. A guard keyed on a naming convention is a guard the next
 *      token can decline to join. This one keys on what a value IS and what a
 *      stylesheet DOES with it;
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
 * EVERY custom-property declaration in EVERY stylesheet, name -> authored values.
 *
 * Deliberately not `tokens.css` only, and that scope is the fix to a real
 * escape rather than a tidy-up. `declaredHex` used to read the palette sheet
 * alone and THROW for anything else, and the ground guard below swallowed the
 * throw with a `catch { return false }` commented "component-scoped token, not
 * part of the shared palette". A component-scoped BACKGROUND is exactly where
 * shared ink lands un-assessed: an independent review declared a light fill
 * inside a component rule, painted it with shared `--text-tertiary`, and the
 * whole suite stayed green. Resolution is now global, so a fill is judged by
 * WHAT IT IS rather than by which file happens to declare it.
 */
const DECLARATIONS: ReadonlyMap<string, readonly { file: string; value: string }[]> = (() => {
  const out = new Map<string, { file: string; value: string }[]>();
  for (const [file, src] of SHEETS) {
    for (const m of src.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;{}]+)[;}]/g)) {
      const list = out.get(m[1]) ?? [];
      list.push({ file, value: m[2].trim() });
      out.set(m[1], list);
    }
  }
  return out;
})();

/**
 * A token's resolved 6-digit hex, or `null` when it does not have one — because
 * nothing declares it, or because its value is not a colour (`16px`, a shadow,
 * a font stack), or because it aliases something that is not a colour either.
 *
 * A token declared with TWO DIFFERENT hex values throws rather than picking one.
 * Two copies of one colour are two things that can drift, and silently choosing
 * the first would make the ratio this file reports depend on file order.
 */
function resolveHex(token: string, seen: readonly string[] = []): string | null {
  if (seen.includes(token)) return null;
  const decls = DECLARATIONS.get(token);
  if (decls === undefined) return null;
  const hexes = new Set(
    decls.filter((d) => /^#[0-9a-f]{6}$/i.test(d.value)).map((d) => d.value.toLowerCase()),
  );
  if (hexes.size > 1) {
    throw new Error(
      `${token} is declared with ${hexes.size} different hex values (${[...hexes].join(', ')}) ` +
        `in ${[...new Set(decls.map((d) => d.file))].join(', ')} — one colour, two values`,
    );
  }
  if (hexes.size === 1) return [...hexes][0];
  const aliases = new Set(
    decls
      .map((d) => /^var\((--[a-z0-9-]+)\)$/.exec(d.value)?.[1])
      .filter((t): t is string => t !== undefined),
  );
  if (aliases.size === 1) return resolveHex([...aliases][0], [...seen, token]);
  return null;
}

/**
 * A token's resolved 6-digit hex, following chains of single-`var()` aliases,
 * throwing when there is none. `--text-quaternary` is deliberately such an
 * alias, and resolving it here is what lets the ratio guard cover it WITHOUT the
 * value being repeated in two places where the two copies could drift apart.
 */
function declaredHex(token: string): string {
  const hex = resolveHex(token);
  if (hex === null) {
    throw new Error(
      `${token} does not resolve to a 6-digit hex in any stylesheet — it is either undeclared, ` +
        'or declared with a value that is not a colour',
    );
  }
  return hex;
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

/* ── registry 1b · the semantic colours that are also ink ──────────────────── */

/**
 * NOT ALL INK IS NEUTRAL INK, and the guard above used to behave as though it
 * were. Fifteen tokens outside the `--text-*` namespace and outside
 * `TINTED_PAIRS` are painted by a `color` declaration somewhere in the app —
 * action blue, the assistant indigo, the evidence source-type strokes, the
 * status greens and ambers, white-on-solid inverse ink, and the dark graph
 * canvas's own two greys. They are enumerated here so that the totality guard
 * has something true to be total OVER.
 *
 * EACH ENTRY CARRIES THE BAR ITS USE ACTUALLY OWES, and the roles are the
 * point of the registry rather than decoration:
 *
 *   `text-anywhere`     — 4.5:1 (WCAG 1.4.3) on EVERY ground in `TEXT_GROUNDS`.
 *                         The strongest claim available, and the four action /
 *                         assistant colours all meet it, so no ground has to be
 *                         guessed for them.
 *   `graphic-anywhere`  — 3:1 (WCAG 1.4.11, non-text contrast) on every ground
 *                         in `TEXT_GROUNDS`. Claimed only where every use is an
 *                         `svg` stroke or an `aria-hidden` mark whose meaning is
 *                         carried by adjacent text; the sites are named in `why`
 *                         and were read off the markup, not assumed.
 *   `text`              — 4.5:1 on the ENUMERATED grounds only. Used where the
 *                         token does not clear the whole cross-product and the
 *                         grounds it is really painted on are declared in the
 *                         rules that paint it.
 *   `inverse-on-solid`  — white ink; 4.5:1 on the solid fills it is painted on.
 *   `dark-canvas`       — the `--gc-*` scale; 4.5:1 on its own dark fills.
 *   `inactive-control`  — no ratio bar; 1.4.3 exempts an inactive component.
 *
 * THE HONEST LIMIT, stated because the registry would otherwise read stronger
 * than it is: for the two `text` entries and the two ground-listing roles, the
 * grounds are ENUMERATED from a reading of the rules that paint the token, not
 * DERIVED the way `TEXT_GROUNDS` is. What this registry enforces mechanically is
 * the CLASSIFICATION — no hex-valued token can be painted as `color` without
 * appearing here — and the ratio on the grounds named. It does not prove the
 * named grounds are the only ones.
 *
 * NO FAILURE IS MANUFACTURED HERE. Every entry clears its own bar as measured
 * at this commit, with ONE exception, `--src-derivation`, which is not a new
 * finding but cause (c) of A11Y-01, already recorded in `e2e/a11y-baseline.ts`
 * at 4.25:1 over 15 occurrences.
 */
type SemanticRole =
  | 'text-anywhere'
  | 'graphic-anywhere'
  | 'text'
  | 'inverse-on-solid'
  | 'dark-canvas'
  | 'inactive-control';

interface SemanticInk {
  readonly token: string;
  readonly role: SemanticRole;
  /** Required for `text`, `inverse-on-solid` and `dark-canvas`; forbidden otherwise. */
  readonly grounds?: readonly string[];
  readonly why: string;
}

const SEMANTIC_INK: readonly SemanticInk[] = [
  {
    token: '--action',
    role: 'text-anywhere',
    why:
      'Action blue. 41 `color` declarations — links, `summary` disclosures, quiet buttons, the ' +
      'ready-state banner icon. Worst case 4.70:1 on `--assist-tint`, so no ground is guessed.',
  },
  {
    token: '--action-hover',
    role: 'text-anywhere',
    why: 'The hover/active rung of the same ramp, and the `.btn-action` resting label. 6.39:1 worst.',
  },
  {
    token: '--action-pressed',
    role: 'text-anywhere',
    why: 'The pressed rung. Two declarations, both `.btn-action` states. 7.72:1 worst.',
  },
  {
    token: '--assist',
    role: 'text-anywhere',
    why:
      'Assistant indigo: the `aria-hidden` panel icon plus the graph-navigation eyebrow, the ' +
      'candidate buttons and the dismiss control, which are TEXT. 5.05:1 worst, so the text ' +
      'uses are covered by the strongest bar rather than by an argument.',
  },
  {
    token: '--advisory-icon',
    role: 'graphic-anywhere',
    why:
      'Amber icon stroke, six declarations, EVERY one a graphical object: the `.guided-dontknow` ' +
      'svg in three states, `.wf-progress-icon` and `.needsyou-icon` (both `aria-hidden="true"` ' +
      'lucide icons), and `.spine-step.reopened .spine-disc`, whose numeral is `aria-hidden` with ' +
      'the step name beside it. All six sit on `--advisory-bg` (3.21:1); the 3:1 bar holds on ' +
      'every ground in the app, worst 3.07:1. It does NOT clear 4.5:1 anywhere — 3.61:1 on white ' +
      '— which is exactly why the role is recorded rather than the token being called text.',
  },
  {
    token: '--pass-solid',
    role: 'graphic-anywhere',
    why:
      'Green check/record mark. `.artifact-icon.record` and `.answered-check` are ' +
      '`aria-hidden="true"`; `.edit-impact` colours only its `aria-hidden` `<Check>` (its two ' +
      'text children set their own colour); `.trail-resolved` is a lucide `<Check>` with ' +
      '`aria-label="resolved"`, i.e. a labelled graphical object. 3.87:1 worst.',
  },
  {
    token: '--src-filelisting',
    role: 'graphic-anywhere',
    why: 'Evidence source-type stroke, `.src-filelisting svg` only, on the `--missing-bg` chip. 3.92:1 worst.',
  },
  {
    token: '--src-spreadsheet',
    role: 'graphic-anywhere',
    why: 'Evidence source-type stroke, `.src-spreadsheet svg` only. 3.60:1 worst — over 3:1, under 4.5:1.',
  },
  {
    token: '--src-userconf',
    role: 'graphic-anywhere',
    why:
      'Evidence source-type stroke plus `.artifact-icon.sidecar`, which is `aria-hidden="true"`. ' +
      'Both sit on `--confirmed-bg`. 4.09:1 worst.',
  },
  {
    token: '--src-derivation',
    role: 'text',
    grounds: ['--surface', '--surface-subtle', '--screen-base'],
    why:
      'The ONE entry here that fails its bar, and it is not a new finding. Two declarations: ' +
      '`.src-derivation svg` (a graphical object, fine at 3:1) and `.sidecar-obj .k`, which is ' +
      'the KEY of a rendered JSON object — text a scientist reads. `.sidecar-obj` declares no ' +
      'fill, so the grounds are the three neutral surfaces it can sit on: 4.61 / 4.49 / 4.26. ' +
      'This is cause (c) of FINDING A11Y-01, which `e2e/a11y-baseline.ts` records axe-measuring ' +
      'at 4.25:1 over 15 occurrences — consistent with the 4.26 computed here on `--screen-base`. ' +
      'Deliberately NOT fixed by A3: re-hueing a source-type motif is a motif decision.',
  },
  {
    token: '--pass-text-soft',
    role: 'text',
    grounds: ['--surface', '--surface-subtle', '--screen-base'],
    why:
      'Text, at three sites: `.sidecar-obj .s` (a JSON string value), `.hash-field .hash` (on ' +
      'the `--surface-subtle` fill the rule itself declares) and the saved run-status line. ' +
      '5.06 / 4.93 / 4.67 — it clears AA on all three. It does NOT clear the whole cross-product ' +
      '(4.30:1 on `--assist-tint`), which is why the grounds are enumerated rather than ' +
      'the `text-anywhere` role claimed; no rule paints it on that panel.',
  },
  {
    token: '--fail-border',
    role: 'inactive-control',
    why:
      'One declaration, `.btn-danger:disabled`. 1.56:1 on white, and it stays: WCAG 1.4.3 ' +
      'exempts text that is part of an inactive user-interface component.',
  },
  {
    token: '--surface',
    role: 'inverse-on-solid',
    grounds: ['--action', '--assist', '--assist-text', '--stats-ramp-1', '--stats-ramp-2'],
    why:
      'White, used as INK on four solid fills: the primary tutorial button (`--action`), the ' +
      'graph command Run button hovered (`--assist`) and pressed (`--assist-text`), and the ' +
      'in-bar chart labels on the two darkest ramp steps. 5.53 / 5.95 / 8.37 / 9.09 / 6.24. It ' +
      'is in `TEXT_GROUNDS` as well, which is not a contradiction: it is the app\'s lightest ' +
      'ground AND its inverse ink, and the two roles are measured separately.',
  },
  {
    token: '--gc-text',
    role: 'dark-canvas',
    grounds: ['--gc-bg', '--gc-panel'],
    why:
      'The dark graph canvas has its own scale, declared in `graph.css` rather than `tokens.css` ' +
      '— which is why it was invisible until resolution went global. 15.70 / 14.07.',
  },
  {
    token: '--gc-text-dim',
    role: 'dark-canvas',
    grounds: ['--gc-bg', '--gc-panel'],
    why:
      'The canvas\'s secondary grey. 8.86 / 7.94. `no shared ink token is painted inside the ' +
      'dark graph canvas` asserts the isolation from the other direction.',
  },
];

/**
 * The one semantic entry below its bar, recorded with its measured worst case
 * rather than skipped — a ratchet, exactly like `TINTED_EXCEPTIONS`. It may
 * improve; if it starts passing, the exception must be retired deliberately.
 */
const SEMANTIC_EXCEPTIONS: ReadonlyMap<string, number> = new Map([['--src-derivation', 4.26]]);

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
  /**
   * For `inactive-control`: the class whose every JSX tag must carry `disabled`.
   * Optional, because a selector that already says `:disabled` needs no markup
   * evidence — this is for the case where the CSS cannot say it and the markup can.
   */
  readonly disabledMark?: string;
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
    disabledMark: 'api-keys-create-btn',
    why:
      'Permanently inactive. The SELECTOR is not `:disabled` — it is a bare class with ' +
      '`cursor: not-allowed`, a dashed border and no enabled state anywhere in the stylesheet — ' +
      'and that is why the basis check accepts `cursor: not-allowed` as well as the pseudo-class. ' +
      'BUT THE EXEMPTION DOES NOT REST ON THE CURSOR. The ELEMENT is genuinely inactive: ' +
      '`screens/settings/ApiKeys.tsx` renders it with a bare, unconditional `disabled` attribute, ' +
      'so WCAG 1.4.3\'s inactive-component exception applies to the control itself and not merely ' +
      'to how it is painted. That is checked mechanically through `disabledMark`, so nobody can ' +
      'later weaken the basis — by dropping `cursor: not-allowed`, or by making the attribute ' +
      'conditional — while believing the exemption still holds.',
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

/**
 * Every token named in any `color` value — and NOT in `background-color`,
 * `border-color` or any other `-color` longhand, which the leading
 * `(?:^|[\s;])` excludes because `-` is neither whitespace nor a semicolon.
 */
function colorTokens(): ReadonlySet<string> {
  const out = new Set<string>();
  for (const rule of RULES) {
    for (const m of rule.decls.matchAll(/(?:^|[\s;])color\s*:\s*([^;}]*)/g)) {
      for (const v of m[1].matchAll(/var\((--[a-z0-9-]+)/g)) out.add(v[1]);
    }
  }
  return out;
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

/**
 * Every JSX opening tag in one source, scanned rather than regexed.
 *
 * This was `/<[A-Za-z][^>]*>/g`, which TRUNCATES at the first `>` it meets — and
 * `=>` inside an attribute value contains one. A tag written
 * `<span onClick={() => x} className="chev">` matched only as far as
 * `<span onClick={() =>`, so the class never appeared in it and the
 * `aria-hidden` guard below would have found ZERO tags for that mark and said
 * so. There are no such cases today; the point is that there would have been no
 * warning if there were, because the guard's own vacuity check (`>= 1` tag
 * carrying the class) is satisfied by any OTHER element with the same class.
 *
 * The scanner tracks quotes and brace depth, so `>` only ends a tag when it is
 * outside both. `<` at depth 0 abandons the candidate: it was a comparison or a
 * generic, not a tag.
 */
function jsxTags(src: string): string[] {
  const out: string[] = [];
  for (let i = 0; i < src.length; i += 1) {
    if (src[i] !== '<' || !/[A-Za-z]/.test(src[i + 1] ?? '')) continue;
    let depth = 0;
    let quote: string | null = null;
    for (let j = i + 1; j < src.length; j += 1) {
      const c = src[j];
      if (quote !== null) {
        if (c === quote) quote = null;
        continue;
      }
      if (c === '"' || c === "'" || c === '`') quote = c;
      else if (c === '{') depth += 1;
      else if (c === '}') depth -= 1;
      else if (c === '<' && depth === 0) break;
      else if (c === '>' && depth === 0) {
        out.push(src.slice(i, j + 1));
        i = j;
        break;
      }
    }
  }
  return out;
}

/** Every JSX opening tag in the app's TS/TSX sources. */
const JSX_TAGS: readonly string[] = Object.values(tsxSources).flatMap((src) => jsxTags(src));

/* ── the undeclared-custom-property scan ───────────────────────────────────── */

interface VarReference {
  readonly file: string;
  readonly token: string;
  /** The text after the first top-level comma, or `null` when there is none. */
  readonly fallback: string | null;
}

/** Every `var()` reference in every stylesheet, with its fallback text if any. */
const VAR_REFERENCES: readonly VarReference[] = (() => {
  const out: VarReference[] = [];
  for (const [file, src] of SHEETS) {
    for (let i = src.indexOf('var('); i !== -1; i = src.indexOf('var(', i + 4)) {
      let depth = 0;
      let end = -1;
      for (let j = i + 3; j < src.length; j += 1) {
        if (src[j] === '(') depth += 1;
        else if (src[j] === ')') {
          depth -= 1;
          if (depth === 0) {
            end = j;
            break;
          }
        }
      }
      if (end === -1) continue;
      const inner = src.slice(i + 4, end);
      let comma = -1;
      let d = 0;
      for (let k = 0; k < inner.length; k += 1) {
        const c = inner[k];
        if (c === '(') d += 1;
        else if (c === ')') d -= 1;
        else if (c === ',' && d === 0) {
          comma = k;
          break;
        }
      }
      const token = (comma === -1 ? inner : inner.slice(0, comma)).trim();
      const fallback = comma === -1 ? null : inner.slice(comma + 1).trim();
      if (/^--[a-z0-9-]+$/.test(token)) out.push({ file, token, fallback });
    }
  }
  return out;
})();

/**
 * Can this reference produce a value at all?
 *
 * `var(--x)` where nothing declares `--x` is invalid at computed-value time: an
 * inherited property falls back to `inherit` and everything else to its initial
 * value, so `background` becomes transparent and a `border` shorthand becomes
 * `none`. A fallback rescues it — but only if the fallback itself resolves, which
 * is why `var(--text-link, var(--text-body))` does NOT count as rescued when
 * `--text-body` is undeclared too.
 */
function referenceIsSatisfiable(ref: VarReference): boolean {
  if (DECLARATIONS.has(ref.token)) return true;
  if (ref.fallback === null || ref.fallback === '') return false;
  const names = [...ref.fallback.matchAll(/--[a-z0-9-]+/g)].map((m) => m[0]);
  return names.every((n) => DECLARATIONS.has(n));
}

/**
 * NAMED, DATED, AND DELIBERATELY NARROW. `components/transcriptCapture.css`
 * paints with five custom properties that NOTHING in this repository declares —
 * 21 references with no fallback at all (`--text-body` x11, `--surface-raised`
 * x5, `--border-subtle` x4, `--surface-base` x1) plus `--text-link`, whose
 * fallback is `var(--text-body)` and so resolves no better.
 *
 * The panel is SHIPPED AND UNGATED — `screens/RecordWorkbench.tsx` mounts
 * `TranscriptCapturePanel` with no flag — so this is live, not dead code. Every
 * one of those declarations is invalid at computed-value time: the backgrounds
 * render transparent, the borders render none, and the text colours inherit
 * whatever the panel's ancestor set. It is PRE-EXISTING, introduced with the
 * panel itself in `72e2206` (2026-08-17) and present at `bebf4e2`, and it is
 * NOT caused by the A3 palette change, which touched no file under
 * `components/`.
 *
 * It is recorded rather than fixed because fixing it is a VISUAL decision, not a
 * token-level one: choosing which shared token each of the five should have been
 * is choosing what the panel looks like, and nothing in the repository says. It
 * needs its own slice. What this exemption buys is that the defect can no longer
 * be re-introduced silently anywhere else, and that this one cannot widen — the
 * second test below fails if a sixth property joins it OR if these five are
 * fixed and the exemption is left standing.
 */
const UNDECLARED_EXEMPTIONS: readonly {
  readonly file: string;
  readonly tokens: readonly string[];
  readonly recorded: string;
}[] = [
  {
    file: 'components/transcriptCapture.css',
    tokens: [
      '--border-subtle',
      '--surface-base',
      '--surface-raised',
      '--text-body',
      '--text-link',
    ],
    recorded: '2026-09-01',
  },
];

/* ── 1 · the classification is total ───────────────────────────────────────── */

/**
 * Every token this file classifies, in any of the four registries. A FUNCTION and
 * not a `const`: `TINTED_PAIRS` is declared further down the file, and a
 * module-level array would read it inside its temporal dead zone.
 */
const registeredInk = (): readonly string[] => [
  ...INFORMATIONAL_INK,
  ...NON_INFORMATIONAL_INK.map((e) => e.token),
  ...TINTED_PAIRS.map(([ink]) => ink),
  ...SEMANTIC_INK.map((e) => e.token),
];

describe('A3 · every ink token is classified', () => {
  it('registers every hex-valued token that any stylesheet paints as `color`', () => {
    // THE GUARD THE `--text-*` NAMESPACE SCAN COULD NOT BE. It keys on value and
    // use: if a token resolves to a hex ANYWHERE and a `color` declaration
    // ANYWHERE names it, it must appear in one of the four registries. A new
    // `--ink-whisper: #b5bcc4` painted as 11px text fails here, whatever it is
    // called and whichever stylesheet declares it.
    const painted = [...colorTokens()].filter((t) => resolveHex(t) !== null);
    // Vacuity: the sweep must actually be finding painted tokens.
    expect(painted.length, 'no hex-valued token is painted as `color` — the scan is broken')
      .toBeGreaterThanOrEqual(30);
    expect(
      [...new Set(painted)].sort(),
      'a token that resolves to a hex is painted as `color` without being classified. Register ' +
        'it: informational ink (owes 4.5:1 on every ground), non-informational ink (owes an ' +
        'enumerated exemption), a TINTED_PAIRS status ink, or SEMANTIC_INK with the usage role ' +
        'whose bar it actually owes. A colour nobody classified is a colour nobody measured.',
    ).toEqual([...new Set(registeredInk())].sort());
  });

  it('registers every --text-* token declared in tokens.css, even an unused one', () => {
    // The NARROWER guard, kept beside the wider one rather than replaced by it.
    // The wide guard sees only what is PAINTED; this one sees what is DECLARED,
    // so a dead lighter grey cannot sit in the palette waiting for its first use.
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

  it('resolves every registered token to a 6-digit hex, and registers each one once', () => {
    const registered = registeredInk();
    for (const token of registered) {
      expect(declaredHex(token), `${token} must resolve to a hex`).toMatch(/^#[0-9a-f]{6}$/);
    }
    // A token classified twice would let two different bars both claim to apply,
    // and the set-equality guard above would still pass.
    const seen = registered.filter((t, i) => registered.indexOf(t) !== i);
    expect(seen, 'a token is registered in more than one usage class').toEqual([]);
  });
});

/* ── 2 · the ratios ────────────────────────────────────────────────────────── */

describe('A3 · informational ink clears WCAG AA on every ground it can sit on', () => {
  it('the ground registry accounts for every light fill in the application', () => {
    // NO `try`/`catch` HERE ANY MORE, and its removal is the fix rather than a
    // simplification. This used to swallow a resolution failure with
    // `catch { return false }` commented "component-scoped token, not part of the
    // shared palette" — which quietly excused exactly the case that matters, a
    // light fill declared inside a component rule and then painted with SHARED
    // ink. `resolveHex` reads every stylesheet, so a component-scoped fill is now
    // judged like any other. It still returns `null` for a custom property
    // NOTHING declares; that class cannot be assessed at all and has its own test
    // below, with a named, dated exemption for the one file that has them.
    const light = [...backgroundTokens()].filter((t) => {
      const hex = resolveHex(t);
      return hex !== null && relativeLuminance(hex) >= 0.6;
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

/* ── 2a · the semantic colours that are also ink ───────────────────────────── */

describe('A3 · semantic ink meets the bar its own usage owes', () => {
  const BAR: Record<SemanticRole, number | null> = {
    'text-anywhere': 4.5,
    'graphic-anywhere': 3,
    text: 4.5,
    'inverse-on-solid': 4.5,
    'dark-canvas': 4.5,
    'inactive-control': null,
  };

  it('every entry declares grounds exactly when its role needs them', () => {
    // A role with no grounds where grounds are required would silently measure
    // nothing, and the loop below would pass by iterating an empty list.
    expect(SEMANTIC_INK.length).toBeGreaterThanOrEqual(15);
    for (const entry of SEMANTIC_INK) {
      const needsGrounds = ['text', 'inverse-on-solid', 'dark-canvas'].includes(entry.role);
      expect(
        (entry.grounds ?? []).length > 0,
        `${entry.token} has role ${entry.role}, which ${needsGrounds ? 'requires' : 'forbids'} ` +
          'an enumerated ground list',
      ).toBe(needsGrounds);
      expect(entry.why.length, `${entry.token} must say why its role is the right one`)
        .toBeGreaterThan(40);
    }
  });

  it('clears its bar on every ground its role names', () => {
    for (const entry of SEMANTIC_INK) {
      const bar = BAR[entry.role];
      if (bar === null) continue; // inactive-control: checked as a site, not as a ratio
      const fg = declaredHex(entry.token);
      const grounds =
        entry.role === 'text-anywhere' || entry.role === 'graphic-anywhere'
          ? TEXT_GROUNDS
          : (entry.grounds as readonly string[]);
      expect(grounds.length, `${entry.token} is measured against no ground at all`)
        .toBeGreaterThanOrEqual(1);
      const recorded = SEMANTIC_EXCEPTIONS.get(entry.token);
      for (const groundToken of grounds) {
        const ratio = contrastRatio(fg, declaredHex(groundToken));
        if (recorded !== undefined) {
          // A ratchet, not a waiver.
          expect(
            ratio,
            `${entry.token} on ${groundToken} is ${ratio.toFixed(2)}:1 — worse than the ` +
              `${recorded}:1 recorded for this known A11Y-01 cause-(c) exception`,
          ).toBeGreaterThanOrEqual(recorded - 0.01);
          continue;
        }
        expect(
          ratio,
          `${entry.token} ${fg} on ${groundToken} is ${ratio.toFixed(2)}:1 — below the ${bar}:1 ` +
            `its recorded role "${entry.role}" owes. Either fix the value, or correct the role ` +
            'to the one its use actually claims, or record it in SEMANTIC_EXCEPTIONS with the ' +
            'measured number and a reason.',
        ).toBeGreaterThanOrEqual(bar);
      }
    }
  });

  it('the recorded semantic exception is exactly the one already disclosed', () => {
    // Bounded, so a SECOND failure cannot quietly join the one A11Y-01 already
    // names. `--src-derivation` is cause (c); nothing else may be added without
    // a deliberate edit here.
    expect([...SEMANTIC_EXCEPTIONS.keys()]).toEqual(['--src-derivation']);
  });

  it('the graphic-anywhere entries really are below the text bar, not merely above 3:1', () => {
    // Vacuity + honesty. If one of these actually cleared 4.5:1 everywhere, the
    // 3:1 role would be understating it and the `why` would be doing work the
    // arithmetic does not need. Two of the five clear 4.5:1 on white but not on
    // the app's darkest ground, which is the case the role exists for.
    const white = declaredHex('--surface');
    const darkest = declaredHex('--assist-tint');
    for (const entry of SEMANTIC_INK.filter((e) => e.role === 'graphic-anywhere')) {
      const fg = declaredHex(entry.token);
      expect(
        contrastRatio(fg, darkest),
        `${entry.token} clears 4.5:1 even on ${darkest} — it does not need the 1.4.11 bar, and ` +
          'claiming a weaker one understates it',
      ).toBeLessThan(4.5);
      expect(contrastRatio(fg, white), `${entry.token} must still clear 3:1 on white`)
        .toBeGreaterThanOrEqual(3);
    }
  });

  it('the inactive-control entry is used only on a genuinely inactive selector', () => {
    for (const entry of SEMANTIC_INK.filter((e) => e.role === 'inactive-control')) {
      const rules = rulesUsing(entry.token).filter((r) =>
        new RegExp(`(?:^|[\\s;])color\\s*:\\s*[^;]*var\\(${entry.token}\\)`).test(r.decls),
      );
      expect(rules.length, `${entry.token} is not painted as color anywhere`)
        .toBeGreaterThanOrEqual(1);
      for (const rule of rules) {
        expect(
          /:disabled|\[disabled\]|aria-disabled/.test(rule.selector) ||
            /cursor\s*:\s*not-allowed/.test(rule.decls),
          `${rule.file} ${rule.selector} paints ${entry.token} without being an inactive ` +
            'control, so the 1.4.3 exemption it claims does not apply',
        ).toBe(true);
      }
    }
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

/* ── 2c · properties that resolve to nothing at all ────────────────────────── */

describe('A3 · nothing paints with a custom property the repository never declares', () => {
  const unsatisfiable = (): readonly string[] => [
    ...new Set(
      VAR_REFERENCES.filter((r) => !referenceIsSatisfiable(r)).map((r) => `${r.file} | ${r.token}`),
    ),
  ];

  it('finds no unexcused undeclared property', () => {
    // Vacuity: the scanner must be finding references at all.
    expect(VAR_REFERENCES.length, 'no var() reference was found — the scan is broken')
      .toBeGreaterThanOrEqual(1000);
    const exempt = new Set(
      UNDECLARED_EXEMPTIONS.flatMap((e) => e.tokens.map((t) => `${e.file} | ${t}`)),
    );
    expect(
      unsatisfiable().filter((k) => !exempt.has(k)).sort(),
      'a stylesheet paints with a custom property that nothing declares and no fallback ' +
        'rescues. At computed-value time that is not "a slightly wrong colour": an inherited ' +
        'property falls back to `inherit` and every other one to its initial value, so a ' +
        '`background` renders transparent and a `border` shorthand renders none. Declare the ' +
        'property, point the rule at a token that exists, or give it a fallback that resolves.',
    ).toEqual([]);
  });

  it('the recorded exemption is exactly as wide as the defect, in both directions', () => {
    // A ratchet on the exemption itself. It fails if a SIXTH property joins the
    // list, and it fails if the five are fixed and the exemption is left behind
    // asserting a defect that no longer exists.
    const declared = UNDECLARED_EXEMPTIONS.flatMap((e) => e.tokens.map((t) => `${e.file} | ${t}`));
    expect(
      [...unsatisfiable()].sort(),
      'the undeclared-property exemption no longer matches what is measured. If the defect was ' +
        'fixed, RETIRE the exemption in the same change; if it grew, the new one needs its own ' +
        'named, dated entry and its own reason.',
    ).toEqual([...declared].sort());
  });

  it('the exempted file is still shipped, so the exemption is about live code', () => {
    // If the panel were ever un-mounted the honest record would be different, and
    // the reason to fix it would be weaker. Asserted rather than assumed.
    const mounts = JSX_TAGS.filter((t) => /TranscriptCapturePanel/.test(t));
    expect(
      mounts.length,
      'TranscriptCapturePanel is no longer mounted — re-read the undeclared-property exemption, ' +
        'which is written on the basis that the defect is live',
    ).toBeGreaterThanOrEqual(1);
    for (const entry of UNDECLARED_EXEMPTIONS) {
      expect(entry.recorded, `${entry.file} exemption must carry the date it was recorded`)
        .toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
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
        if (site.disabledMark !== undefined) {
          // The CSS cannot say the element is disabled; the markup can, and does.
          const tags = JSX_TAGS.filter((t) =>
            new RegExp(`["'\\s{]${site.disabledMark!.replace(/-/g, '\\-')}["'\\s}]`).test(t),
          );
          expect(
            tags.length,
            `no JSX tag carries the class "${site.disabledMark}" — the inactive-control basis ` +
              'cannot be verified from the markup',
          ).toBeGreaterThanOrEqual(1);
          const enabled = tags.filter((t) => !/(?:^|\s)disabled(?=[\s/>=])/.test(t));
          expect(
            enabled.map((t) => t.replace(/\s+/g, ' ').slice(0, 160)),
            `every element with the class "${site.disabledMark}" must carry a \`disabled\` ` +
              'attribute. Without it the control is not inactive, and a sub-AA colour on an ' +
              'ACTIVE control is a 1.4.3 failure however the cursor is styled.',
          ).toEqual([]);
        }
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

  it('the JSX scan survives an arrow function inside an attribute', () => {
    // The `aria-hidden` and `disabled` guards are only as good as the tag scan
    // that feeds them, and a truncated scan fails SILENTLY: it produces a tag
    // that does not contain the class, so the class simply is not found on that
    // element and any OTHER element with the same class satisfies the check.
    const probe = '<button onClick={() => setOpen(true)} className="chev" aria-hidden="true">';
    expect(jsxTags(probe), 'the scanner must return the whole tag').toEqual([probe]);
    // ...and the form this replaced really did truncate, so the hardening is
    // load-bearing rather than defensive. If this ever stops truncating, the
    // regex was changed and `jsxTags` may no longer be needed.
    expect(/<[A-Za-z][^>]*>/.exec(probe)![0]).toBe('<button onClick={() =>');
    expect(JSX_TAGS.length, 'no JSX opening tag was found — the tag scan is broken')
      .toBeGreaterThanOrEqual(2000);
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
   * text, and compositing drags a PASSING colour below AA.
   *
   * EACH SITE NOW CARRIES ITS OWN INK AND ITS OWN BACKDROP, and that is a
   * correction rather than a refinement. The list used to be three selectors
   * measured against ONE token on ONE ground, and `.advisory-nongating` is
   * neither: it sets `color: var(--advisory-text)` itself, and it sits inside
   * `.advisory`, whose fill is `--advisory-bg`. So the third site was named as
   * one of the three while its number was published nowhere, and the loop below
   * iterated `[0.82, 0.72]` — the other two — as though it had covered it.
   *
   * The composites are FORMULA-COMPUTED, not browser-measured; `compositeOver`
   * documents why they must not be transcribed into `a11y-baseline.ts`. If an
   * opacity is ever removed, these tests fail and the record gets updated, which
   * is the intended behaviour of a ratchet.
   */
  const OPACITY_SITES = [
    {
      file: 'components/queue.css',
      selector: '.exp-row.done',
      alpha: 0.82,
      ink: '--text-tertiary',
      backdrop: '--surface',
      composite: '#7e868f',
      why: '`.exp-row` declares `background: var(--surface)`, so the row composites onto white.',
    },
    {
      file: 'components/assistant.css',
      selector: '.upcoming-row',
      alpha: 0.72,
      ink: '--text-tertiary',
      backdrop: '--surface',
      composite: '#8e959d',
      why:
        '`.upcoming-row` declares no fill of its own. `--surface` is the lightest ground it can ' +
        'sit on and therefore the most FAVOURABLE assumption available — the site fails even ' +
        'there, which is what makes the residue claim safe rather than lucky.',
    },
    {
      file: 'components/signals.css',
      selector: '.advisory-nongating',
      alpha: 0.85,
      ink: '--advisory-text',
      backdrop: '--advisory-bg',
      composite: '#9b793d',
      why:
        'NOT a neutral-ink site at all: the rule sets `color: var(--advisory-text)` #8a6420, and ' +
        'its container `.advisory` declares `background: var(--advisory-bg)`. Uncomposited it ' +
        'clears AA on that tint at 4.76:1; at `opacity: .85` it composites to 3.59:1. A palette ' +
        'change to the neutral ramp cannot touch it in either direction.',
    },
  ] as const;

  it('all three ancestor-opacity rules are still present at the recorded strength', () => {
    expect(OPACITY_SITES.length).toBe(3);
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

  it('every site still paints the ink this file measured for it', () => {
    // Without this, a rule could be re-pointed at another token and the ratios
    // below would go on describing a colour the site no longer uses.
    for (const site of OPACITY_SITES) {
      const rule = RULES.find((r) => r.file === site.file && r.selector === site.selector);
      if (site.selector === '.advisory-nongating') {
        expect(
          new RegExp(`color\\s*:\\s*var\\(${site.ink}\\)`).test(rule!.decls),
          `${site.selector} no longer sets ${site.ink} itself`,
        ).toBe(true);
        continue;
      }
      // The two neutral sites colour their CHILDREN, not themselves; assert the
      // ink is still used somewhere in the same stylesheet rather than inventing
      // a containment check this parser cannot do.
      expect(
        rulesUsing(site.ink).some((r) => r.file === site.file),
        `${site.file} no longer paints anything with ${site.ink}`,
      ).toBe(true);
    }
  });

  it('every site still fails AA once composited, on its own backdrop', () => {
    for (const site of OPACITY_SITES) {
      const bg = declaredHex(site.backdrop);
      const composited = compositeOver(declaredHex(site.ink), site.alpha, bg);
      expect(
        composited,
        `${site.selector}: the composite of ${site.ink} at ${site.alpha} over ${site.backdrop} ` +
          'moved. Re-derive the ratio below before trusting it.',
      ).toBe(site.composite);
      const ratio = contrastRatio(composited, bg);
      expect(
        ratio,
        `${site.selector}: ${site.ink} at opacity ${site.alpha} composites to ${composited}, ` +
          `which is ${ratio.toFixed(2)}:1 on ${site.backdrop} — a PASS. If that is real, this ` +
          'site of cause (b) is closed and the guard should be retired deliberately rather than ' +
          'left asserting a defect that no longer exists.',
      ).toBeLessThan(4.5);
    }
  });

  it('darkening the ink WOULD reach two of them, and that is why the wording matters', () => {
    /*
     * THE CLAIM THIS FILE USED TO MAKE — "darkening the token cannot reach
     * them" — IS ARITHMETICALLY FALSE, and it was published in four places
     * before anyone checked it. Composited on white, a neutral grey still
     * clears 4.5:1 at .72 up to #414141, at .82 up to #585858 and at .85 up to
     * #5e5e5e. Those three thresholds are re-derived here by search rather than
     * quoted, so the correction cannot itself go stale.
     *
     * What is TRUE is the qualified form: darkening cannot reach them WITHOUT
     * DESTROYING THE RAMP. All three of those values are darker than
     * `--text-muted` #5b6570, the rung IMMEDIATELY above the tertiary, and the
     * .72 one (#414141) is darker than `--text-secondary` #46515f, two rungs
     * above. A compliant "tertiary" would therefore have to be darker than the
     * tiers it exists to sit below, and the tier would no longer mean anything.
     * The opacity has to go, for that reason and not for an impossibility.
     */
    const white = declaredHex('--surface');
    const THRESHOLDS = [
      [0.72, '#414141'],
      [0.82, '#585858'],
      [0.85, '#5e5e5e'],
    ] as const;
    for (const [alpha, expected] of THRESHOLDS) {
      let lightest: string | null = null;
      for (let g = 255; g >= 0; g -= 1) {
        const h = `#${g.toString(16).padStart(2, '0').repeat(3)}`;
        if (contrastRatio(compositeOver(h, alpha, white), white) >= 4.5) {
          lightest = h;
          break;
        }
      }
      expect(
        lightest,
        `at opacity ${alpha} the lightest neutral grey still clearing 4.5:1 composited on white ` +
          'moved — the "cannot reach them without destroying the ramp" wording rests on this',
      ).toBe(expected);
      // ...and it is darker than `--text-muted`, the rung IMMEDIATELY above the
      // tertiary — so a compliant tertiary would have to be darker than the tier
      // it is supposed to sit below, which is what "destroying the ramp" means.
      expect(
        relativeLuminance(lightest!),
        `${lightest} is LIGHTER than --text-muted, so a compliant tertiary at opacity ${alpha} ` +
          'would fit between the rungs after all and would NOT have destroyed the ramp — the ' +
          'wording in tokens.css and src/test/contrast.ts has to be re-derived',
      ).toBeLessThanOrEqual(relativeLuminance(declaredHex('--text-muted')));
      if (alpha === 0.72) {
        // The strongest of the three, and the one the prose quotes: at .72 the
        // needed value is darker than `--text-secondary`, two rungs above.
        expect(
          relativeLuminance(lightest!),
          `${lightest} is LIGHTER than --text-secondary — the .72 claim in tokens.css names ` +
            'that token specifically and must be corrected',
        ).toBeLessThanOrEqual(relativeLuminance(declaredHex('--text-secondary')));
      }
    }
  });

  it('the shipped tertiary is not dark enough for any of the three', () => {
    // The other half of the same claim, over the value actually shipped.
    const white = declaredHex('--surface');
    const ink = declaredHex('--text-tertiary');
    for (const alpha of [0.85, 0.82, 0.72]) {
      const composited = compositeOver(ink, alpha, white);
      expect(
        contrastRatio(composited, white),
        `${ink} at opacity ${alpha} composites to ${composited}, which would PASS`,
      ).toBeLessThan(4.5);
    }
  });
});

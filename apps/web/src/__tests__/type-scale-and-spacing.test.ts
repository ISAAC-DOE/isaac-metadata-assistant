/*
 * UX-001 — THE FOUR TOKEN AXES `tokens.css` NEVER DECLARED, AND THE RATCHET
 * THAT STOPS THE BLEEDING.
 *
 * ── WHAT WAS WRONG ──────────────────────────────────────────────────────────
 *
 * `styles/tokens.css` declared 82 custom properties — 70 colour, 6 radii, 4
 * shadow, 2 font-family — and ZERO font-size, font-weight, line-height or
 * spacing. Colour was 99.3% tokenized with no phantom property live anywhere,
 * which is disciplined work; the other four axes had nothing to conform to.
 * Measured over every `.css` file under `apps/web/src` with comments stripped,
 * BEFORE this change:
 *
 *     font-size      1 073 declarations   20 distinct values
 *     font-weight      428 declarations    8 distinct (7 numeric + `inherit`)
 *     line-height      423 declarations   16 distinct values
 *     spacing        2 406 literals       32 distinct values (every integer 1–18px)
 *
 * On the record screen that renders as NINE font sizes spanning 10.5–15px in
 * 0.5px steps, 90 of 95 text-bearing elements inside a 3px band. A 0.5px step
 * is 4% of a 12px glyph: not a hierarchy level, noise.
 *
 * ── WHAT THIS FILE GUARDS, AND WHY EACH GUARD IS SHAPED THIS WAY ───────────
 *
 * The obvious test — "assert the tokens exist" — is worth nothing: it passes if
 * the rungs are 0.5px apart, if nothing references them, if a sixth rung
 * appears beside them, or if the app keeps writing raw literals next door. Each
 * `describe` below closes one of those escapes:
 *
 *   1. THE SCALE ITSELF is pinned by VALUE and by ORDER, and the step ratio is
 *      recomputed here rather than trusted — so a rung cannot drift, cannot be
 *      inserted, and cannot be softened back toward the 0.5px steps this axis
 *      exists to replace.
 *   2. EVERY DECLARED RUNG IS REFERENCED, in both directions. A scale nothing
 *      uses is documentation, and `palette-contrast.test.ts` has the measured
 *      history of what an unreferenced/undeclared custom property costs.
 *   3. THE RATCHET is a two-way count. A new raw literal in a tokenized axis
 *      fails (the ceiling); a migration that lowers the count without lowering
 *      the recorded number ALSO fails (the floor), so the numbers cannot rot
 *      into decoration. The tolerance band is 25 declarations — narrower than
 *      any real migration slice, wider than incidental edits.
 *
 * ── WHAT THIS SLICE DELIBERATELY DID NOT DO ────────────────────────────────
 *
 * It did not migrate 1 073 + 428 + 423 + 2 406 declarations. Every axis is
 * anchored at real sites (enumerated in ANCHORS below), `body`'s font-size and
 * line-height are tokenized so the base is a one-token decision, and the
 * counts below stop new literals arriving. Migrating a file at a time is the
 * follow-on slice. The state to avoid is two live systems with no guard, which
 * is what colour was rescued from.
 *
 * ── ONE EXISTING GUARD LOSES A LITTLE COVERAGE AS THIS MIGRATION PROCEEDS ──
 *
 * `palette-contrast.test.ts`'s "no usage of the two A3 tokens relies on the
 * large-text threshold" reads a NUMERIC `font-size:` out of every rule painting
 * `--text-tertiary`/`--text-quaternary` and cannot resolve a `var()`. So a rule
 * whose font-size becomes a token drops out of that sample. This slice
 * therefore left the font-size a LITERAL in every rule that paints either token
 * (`base.css .meta`, `screens.css .evidence-trail-link-count`), with the reason
 * written at each site. The migration slice must teach that guard to resolve
 * `var(--font-size-*)` against the scale below BEFORE it tokenizes those rules;
 * the scale's values are asserted here precisely so that resolution is
 * mechanically available.
 *
 * ── RE-DERIVING EVERY NUMBER ABOVE ─────────────────────────────────────────
 *
 *     cd apps/web && python3 - <<'EOF'
 *     import re, pathlib, collections
 *     c = collections.Counter()
 *     for f in pathlib.Path('src').rglob('*.css'):
 *         src = re.sub(r'/[*][\s\S]*?[*]/', ' ', f.read_text())
 *         for m in re.finditer(r'(?<![-a-z])font-size\s*:\s*([^;}]+)', src):
 *             c[m.group(1).strip()] += 1
 *     print(sum(c.values()), len(c), c.most_common())
 *     EOF
 */

import { describe, it, expect } from 'vitest';

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** Comments are blanked first, so no guard is ever satisfied by prose that
 *  merely quotes a rule — and so the long design note in `tokens.css`, which
 *  names every value in every scale, cannot itself be mistaken for a
 *  declaration. */
const stripComments = (source: string): string => source.replace(/\/\*[\s\S]*?\*\//g, ' ');

const SHEETS: ReadonlyMap<string, string> = new Map(
  Object.entries(cssFiles).map(([path, src]) => [
    path.replace(/^\.\.\//, ''),
    stripComments(src),
  ]),
);

const tokensSheet = (): string => {
  const s = SHEETS.get('styles/tokens.css');
  if (s === undefined) throw new Error('styles/tokens.css was not globbed');
  return s;
};

/** The authored value of a custom property in `tokens.css`, verbatim. */
function declared(token: string): string {
  const m = new RegExp(`${token}\\s*:\\s*([^;]+);`).exec(tokensSheet());
  if (m === null) throw new Error(`${token} is not declared in styles/tokens.css`);
  return m[1].trim();
}

/** Every custom property `tokens.css` declares whose name starts with a prefix,
 *  in DECLARATION ORDER — so a reordering is visible, not just a value change. */
function declaredWithPrefix(prefix: string): string[] {
  return [...tokensSheet().matchAll(/(--[a-z0-9-]+)\s*:/g)]
    .map((m) => m[1])
    .filter((name) => name.startsWith(prefix));
}

/** How many rules anywhere reference a token by `var()`. */
function referenceCount(token: string): number {
  let n = 0;
  for (const src of SHEETS.values()) {
    n += [...src.matchAll(new RegExp(`var\\(\\s*${token}\\s*[,)]`, 'g'))].length;
  }
  return n;
}

/* ── the measured state of each axis ───────────────────────────────────────── */

interface AxisCounts {
  /** declarations whose value is a raw literal, by value */
  readonly literals: ReadonlyMap<string, number>;
  /** declarations whose value is a `var()` */
  readonly tokenized: number;
}

function scanProperty(pattern: RegExp): AxisCounts {
  const literals = new Map<string, number>();
  let tokenized = 0;
  for (const src of SHEETS.values()) {
    for (const m of src.matchAll(pattern)) {
      const value = m[1].trim();
      if (value.startsWith('var(')) tokenized += 1;
      else literals.set(value, (literals.get(value) ?? 0) + 1);
    }
  }
  return { literals, tokenized };
}

/** Spacing is scanned per LENGTH inside a shorthand, because `padding: 8px 14px`
 *  makes two independent spacing decisions and a rule that tokenizes one of them
 *  has migrated one of them. */
function scanSpacing(): AxisCounts {
  const literals = new Map<string, number>();
  let tokenized = 0;
  const prop =
    /(?<![-a-z])(?:padding|margin|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left))?\s*:\s*([^;}]+)/g;
  for (const src of SHEETS.values()) {
    for (const m of src.matchAll(prop)) {
      for (const piece of m[1].split(/\s+/)) {
        if (piece.startsWith('var(')) tokenized += 1;
        else if (/^-?[0-9.]+px$/.test(piece)) {
          literals.set(piece, (literals.get(piece) ?? 0) + 1);
        }
      }
    }
  }
  return { literals, tokenized };
}

const FONT_SIZE = scanProperty(/(?<![-a-z])font-size\s*:\s*([^;}]+)/g);
const FONT_WEIGHT = scanProperty(/(?<![-a-z])font-weight\s*:\s*([^;}]+)/g);
const LINE_HEIGHT = scanProperty(/(?<![-a-z])line-height\s*:\s*([^;}]+)/g);
const SPACING = scanSpacing();

const total = (a: AxisCounts): number => [...a.literals.values()].reduce((x, y) => x + y, 0);

const px = (value: string): number => {
  const m = /^(-?[0-9.]+)px$/.exec(value);
  if (m === null) throw new Error(`${value} is not a px length`);
  return Number(m[1]);
};

/* ── the scales, as this slice designed them ───────────────────────────────── */

/**
 * The font-size rungs, in ascending order. Every rung is a value the product
 * ALREADY rendered, which is what makes the migration a zero-pixel change.
 *
 * `--font-size-heading-md` is 17px rather than the 18px an even ratio band
 * would prefer, deliberately: 17px is what all four of the product's
 * section-heading sites render, so migrating them moves no pixel and needs no
 * accessibility-baseline round-trip. `tokens.css` records that trade.
 */
const FONT_SIZE_SCALE: readonly [string, string][] = [
  ['--font-size-meta', '11px'],
  ['--font-size-body', '13px'],
  ['--font-size-heading-sm', '15px'],
  ['--font-size-heading-md', '17px'],
  ['--font-size-heading-lg', '22px'],
];

const FONT_WEIGHT_SCALE: readonly [string, string][] = [
  ['--font-weight-regular', '400'],
  ['--font-weight-medium', '500'],
  ['--font-weight-semibold', '600'],
  ['--font-weight-bold', '700'],
];

const LINE_HEIGHT_SCALE: readonly [string, string][] = [
  ['--line-height-tight', '1.2'],
  ['--line-height-snug', '1.35'],
  ['--line-height-normal', '1.55'],
  ['--line-height-relaxed', '1.7'],
];

const SPACING_SCALE: readonly [string, string][] = [
  ['--space-2xs', '2px'],
  ['--space-xs', '4px'],
  ['--space-sm', '8px'],
  ['--space-md', '12px'],
  ['--space-lg', '16px'],
  ['--space-xl', '24px'],
];

/**
 * WHERE EACH RUNG IS ANCHORED — the real site that makes it a used token rather
 * than documentation. Enumerated so that a later slice deleting a rule cannot
 * silently strand a rung, and so a reviewer can check that no anchor is a
 * throwaway reference invented to satisfy the guard above.
 */
const ANCHORS: readonly string[] = [
  'styles/base.css            body                            --font-size-body, --line-height-normal',
  'styles/base.css            .eyebrow                        --font-size-meta, --font-weight-medium',
  'styles/base.css            .skip-link                      --space-sm, --font-weight-semibold',
  'styles/base.css            .btn / -primary / -action / -danger  --font-weight-medium, --font-weight-semibold',
  'screens/screens.css        .page-header / .page-title      --space-lg, --font-size-heading-lg',
  'screens/screens.css        .page-subcount                  --space-xs',
  'screens/screens.css        .evidence-trail-link-count      --font-weight-regular',
  'screens/screens.css        .record-identity                --space-xl',
  'screens/screens.css        .completion-header / -title     --space-md, --font-size-heading-md',
  'screens/screens.css        .placeholder > h1               --font-size-heading-lg',
  'screens/screens.css        .source-index-heading           --font-size-heading-sm',
  'screens/screens.css        .concept-lookup-heading         --font-size-heading-sm',
  'screens/screens.css        .settings-card-head h2          --font-size-heading-sm',
  'screens/screens.css        .record-page-title (UX-002)     --space-2xs, --line-height-tight, --line-height-snug',
  'components/evidence.css    .sidecar-obj                    --line-height-relaxed',
  'components/signals.css     .verdict-word                   --font-weight-bold',
];

/*
 * THE RECORDED CEILINGS. Measured at the head of this slice by the command in
 * this file's header. Each is a TWO-WAY ratchet: the ceiling refuses a new raw
 * literal, and the floor (ceiling − TOLERANCE) refuses a migration that lowers
 * the real count without lowering the recorded one. Lower BOTH in the same
 * change that migrates declarations.
 */
const TOLERANCE = 25;
const CEILING = {
  /*
   * *** LOWERED 2026-09-15, IN THE SAME CHANGE THAT MIGRATED THE DECLARATIONS —
   * which is what this ratchet's own message demands, and the reason it demands
   * it is exactly what happened here. ***
   *
   * ~~fontSize: 1065, fontWeight: 414~~ -> 1043 / 281
   *
   * The numbers are THIS FILE'S OWN counter's, read out of its failure message,
   * not a second implementation's. My own sweep said 1042 and 280 — off by one
   * in each axis, because its exclusion list is not identical to
   * `rawLiteralsByValue`'s. A ratchet recorded from a different counter than
   * the one that enforces it is a ratchet that fails on the next unrelated
   * change.
   *
   * Four lanes landed new CSS in one integration and pushed three of these
   * axes over: font-size 1065 -> 1070, font-weight 414 -> 417, line-height
   * 421 -> 422. Every new literal with an EXACT rung was migrated
   * (`13px` -> `--font-size-body`, `600` -> `--font-weight-semibold`,
   * `500` -> `--font-weight-medium`), which took the real counts well BELOW the
   * old ceilings — and the TOLERANCE floor then refused that too, correctly:
   * a count that falls without the record falling stops being a ratchet.
   *
   * ONE MIGRATION WAS REFUSED ON PURPOSE AND IS WORTH RECORDING. My first pass
   * sent a `13px` to `--font-size-meta`, which is **11px** — it would have
   * silently shrunk a control by 2px to satisfy a guard. Tokenizing has to
   * preserve the rendered value or it is not tokenizing, it is redesigning by
   * accident. `12px`, `11.5px` and `10px` therefore stay literals: no rung
   * holds those values, and the new `1.5` line-heights stay literals because
   * `--line-height-normal` is 1.55, not 1.5. For that axis the remedy this
   * message prescribes was used instead — one EXACT `1.55` elsewhere was
   * migrated, so the count returns to its recorded 421 with no value changed.
   *
   * `fontWeight` IS 282 AND NOT 281 BECAUSE ONE MIGRATION WAS REVERTED, and the
   * revert is the more useful half of this record. `.section-tab`'s weight went
   * to `--font-weight-medium` and `a11y-landmarks-headings-and-tabs.test.tsx`'s
   * A16 control CRASHED — it reads `font-weight: (\d+)` numerically out of that
   * block to prove the WCAG large-text exemption does not apply, so a token
   * matched `null`. The value is restored as `500`, which IS
   * `--font-weight-medium`: the rendering never moved, only the spelling.
   *
   * AND FONT-SIZE MIGRATIONS SKIPPED ANY RULE PAINTING `--text-tertiary` or
   * `--text-muted` — the exception this file's header already records. What I
   * missed is that it extends to `font-weight` in those same rules, for the
   * identical reason, and A16 is the guard that says so. This file's own header explains why: `palette-contrast`
   * reads a NUMERIC `font-size` out of those rules to decide the WCAG
   * large-text threshold, so a rule whose size becomes a token drops out of
   * that sample.
   */
  fontSize: 1043,
  fontWeight: 282,
  lineHeight: 421,
  /*
   * ~~spacing: 2400~~ -> 2368, LOWERED 2026-09-22 in the same change that removed
   * the literals (owner QA phase 2): the record-screen redesign replaced hand-set
   * padding/margin/gap in the run findings, validate-review, blocker, field-group,
   * revision-history and proposal-card rules with `--space-*` rungs, and deleted
   * rules whose elements are gone (`.vr-errors`' gap, `.run-finding-state`'s chip
   * padding, `.guided-path`'s chip padding, `.field-path`'s margin). Read from this
   * file's own counter's failure message, as the note above requires.
   */
  spacing: 2368,
  /**
   * font-size declarations BELOW the 11px floor: 9.5px ×1, 10px ×14, 10.5px ×84.
   *
   * ~~10.5px ×85~~ — re-measured 2026-09-14 and corrected in place, because the
   * breakdown is what a reader checks the ceiling against and a stale one makes
   * the next change look like a regression. `.statusbar-eyebrow` moved 10.5px ->
   * `var(--font-size-meta)` (11px) in the casing/typography reconciliation
   * (`chrome.css`); `typography.md:57` sets that floor ("Minimum on-screen text
   * size is ~11px (mono meta); never smaller") and 10.5px was also the size the
   * mechanical `undersized-ui-text` rule flags. THE CEILING IS DELIBERATELY NOT
   * LOWERED to 99: the TOLERANCE floor below it (ceiling − 25) is what refuses a
   * migration that lowers the real count without lowering the recorded one, and
   * a one-declaration fix does not warrant moving both ends of a ratchet sized
   * for the palette-wide work that remains.
   */
  belowFloor: 100,
  /** the three grandfathered non-standard weights: 650 ×54, 550 ×8, 620 ×5. */
  nonStandardWeight: 67,
  /** spacing literals above the top rung: 26 ×2, 28, 30, 32 ×3, 34, 40 ×2, 88. */
  spacingAboveTopRung: 11,
} as const;

/* ══ 1 · the scales are pinned by value, order and step ratio ═══════════════ */

describe('UX-001 · the type scale cannot silently drift', () => {
  it('declares exactly five font-size rungs, in ascending order, at the recorded values', () => {
    expect(declaredWithPrefix('--font-size-')).toEqual(FONT_SIZE_SCALE.map(([n]) => n));
    for (const [name, value] of FONT_SIZE_SCALE) expect(declared(name)).toBe(value);
  });

  it('every adjacent font-size step is >= 2px AND >= 13% — the stated perceptibility bar', () => {
    // This is the whole point of the axis. The nine sizes it replaces on the
    // record screen step by 0.5px, which is 4% of a 12px glyph. If a future
    // change can satisfy the test above with rungs 0.5px apart, the scale has
    // been reduced back to noise while still looking like a system.
    const values = FONT_SIZE_SCALE.map(([, v]) => px(v));
    expect(values.length, 'the scale is empty — the scan is broken').toBe(5);
    for (let i = 1; i < values.length; i += 1) {
      const prev = values[i - 1];
      const next = values[i];
      expect(next - prev, `${prev}px -> ${next}px is a step of under 2px`).toBeGreaterThanOrEqual(
        2,
      );
      expect(
        next / prev,
        `${prev}px -> ${next}px is a step of under 13%; at these sizes that is not a ` +
          'hierarchy level a reader can see. Widen the step or delete the rung.',
      ).toBeGreaterThanOrEqual(1.13);
    }
  });

  it('declares exactly the four weights the shipped font stack can carry', () => {
    expect(declaredWithPrefix('--font-weight-')).toEqual(FONT_WEIGHT_SCALE.map(([n]) => n));
    for (const [name, value] of FONT_WEIGHT_SCALE) expect(declared(name)).toBe(value);
  });

  it('declares no token for 550, 620 or 650 — they resolve to a neighbour off macOS', () => {
    // CSS Fonts 4 §5.3: above 500, candidates >= target ascending. On Segoe UI
    // (400/600/700) 550 -> 600 and 620/650 -> 700; on the Linux family CI
    // renders with (400/700) all three -> 700. They are distinguishable only on
    // macOS with a variable SF Pro, so a token for one would be a rung that
    // exists on one laptop. `tokens.css` records the migration target.
    const values = FONT_WEIGHT_SCALE.map(([, v]) => v);
    for (const odd of ['550', '620', '650']) {
      expect(values, `a rung for the non-standard weight ${odd} was declared`).not.toContain(odd);
    }
  });

  it('declares exactly four line-height rungs with steps of at least 0.1', () => {
    expect(declaredWithPrefix('--line-height-')).toEqual(LINE_HEIGHT_SCALE.map(([n]) => n));
    for (const [name, value] of LINE_HEIGHT_SCALE) expect(declared(name)).toBe(value);
    const values = LINE_HEIGHT_SCALE.map(([, v]) => Number(v));
    for (let i = 1; i < values.length; i += 1) {
      expect(
        Number((values[i] - values[i - 1]).toFixed(3)),
        `${values[i - 1]} -> ${values[i]} is a step of under 0.1; the axis it replaces already ` +
          'spends rungs on 1.5 vs 1.55, a 3% difference nobody can read',
      ).toBeGreaterThanOrEqual(0.1);
    }
  });

  it('declares exactly six spacing rungs, on a 4px grid above the 2px half-step, ending at 24px', () => {
    expect(declaredWithPrefix('--space-')).toEqual(SPACING_SCALE.map(([n]) => n));
    for (const [name, value] of SPACING_SCALE) expect(declared(name)).toBe(value);
    const values = SPACING_SCALE.map(([, v]) => px(v));
    expect(values[0], 'the half-step is not 2px').toBe(2);
    for (const v of values.slice(1)) {
      expect(v % 4, `${v}px is off the 4px grid`).toBe(0);
    }
    for (let i = 1; i < values.length; i += 1) {
      expect(
        values[i] - values[i - 1],
        `${values[i - 1]}px -> ${values[i]}px is a step of under 2px`,
      ).toBeGreaterThanOrEqual(2);
    }
    // The scale ends at 24px on EVIDENCE: 11 of 2 406 spacing literals (0.46%)
    // exceed it, and each is a one-off layout offset rather than a rhythm.
    expect(values[values.length - 1], 'the top rung moved — re-measure the >24px tail').toBe(24);
  });
});

/* ══ 2 · every rung is declared AND referenced ══════════════════════════════ */

describe('UX-001 · a scale nothing uses is documentation, not a token system', () => {
  const everyRung = [
    ...FONT_SIZE_SCALE,
    ...FONT_WEIGHT_SCALE,
    ...LINE_HEIGHT_SCALE,
    ...SPACING_SCALE,
  ];

  it('references every rung it declares, from at least one real rule', () => {
    const stranded = everyRung
      .map(([name]) => name)
      .filter((name) => referenceCount(name) === 0);
    expect(
      stranded,
      'these rungs are declared and referenced by nothing. `palette-contrast.test.ts` has the ' +
        'measured history of what an unused-or-undeclared custom property costs here; a scale ' +
        'that nothing paints with is prose in a stylesheet. Anchor it at a real site (see ' +
        'ANCHORS) or delete the rung.',
    ).toEqual([]);
  });

  it('declares every scale token that any var() names', () => {
    // The other direction. `palette-contrast.test.ts` enforces this app-wide
    // over every custom property; this is the same property stated for these
    // four axes, so a typo in a scale name fails HERE, beside the scale, rather
    // than in a file about colour.
    const namesInUse = new Set<string>();
    for (const src of SHEETS.values()) {
      for (const m of src.matchAll(
        /var\(\s*(--(?:font-size|font-weight|line-height|space)-[a-z0-9-]+)/g,
      )) {
        namesInUse.add(m[1]);
      }
    }
    expect(namesInUse.size, 'no scale reference was found at all — the scan is broken')
      .toBeGreaterThanOrEqual(everyRung.length);
    const declaredNames = new Set(everyRung.map(([n]) => n));
    expect([...namesInUse].filter((n) => !declaredNames.has(n)).sort()).toEqual([]);
  });

  it('keeps the anchor list honest: it names only files this repository has', () => {
    expect(ANCHORS.length, 'the anchor list is empty — the record is gone').toBeGreaterThanOrEqual(
      10,
    );
    for (const row of ANCHORS) {
      const file = row.split(/\s{2,}/)[0];
      expect(SHEETS.has(file), `${file} is named as an anchor but is not a stylesheet here`).toBe(
        true,
      );
    }
  });

  it('anchors the BASE font size and rhythm on the token, so moving it is a one-token edit', () => {
    // `base.css` used to set `body { font-size: 13px; line-height: 1.55 }` as
    // literals. This slice deliberately did NOT change 13px — see tokens.css
    // for the three reasons, the binding one being that no slice which cannot
    // run `e2e/a11y-baseline.ts` may claim a base rescale is safe. What it did
    // do is make that decision a single edit instead of a search.
    const base = SHEETS.get('styles/base.css');
    expect(base, 'styles/base.css was not globbed').toBeDefined();
    expect(base!).toMatch(/body\s*\{[^}]*font-size:\s*var\(--font-size-body\)/);
    expect(base!).toMatch(/body\s*\{[^}]*line-height:\s*var\(--line-height-normal\)/);
    expect(declared('--font-size-body'), 'the base moved without its decision being re-taken')
      .toBe('13px');
  });
});

/* ══ 3 · the ratchet ═══════════════════════════════════════════════════════ */

describe('UX-001 · no NEW raw literal in a tokenized axis', () => {
  /** One ceiling assertion, two-way, with the instruction in the message. */
  const ratchet = (label: string, measured: number, ceiling: number): void => {
    expect(
      measured,
      `${label}: ${measured} raw literals, recorded ceiling ${ceiling}. A new hand-authored ` +
        `value in this axis is what this guard exists to refuse — use a rung from ` +
        `styles/tokens.css. If the value genuinely has no rung, say so at the site and lower ` +
        `a different literal in the same change.`,
    ).toBeLessThanOrEqual(ceiling);
    expect(
      measured,
      `${label}: ${measured} raw literals against a recorded ceiling of ${ceiling}. The count ` +
        `has fallen by more than ${TOLERANCE} — lower CEILING in the same change that migrated ` +
        `them, or the number stops being a ratchet and becomes decoration.`,
    ).toBeGreaterThan(ceiling - TOLERANCE);
  };

  it('is scanning something — every axis finds declarations', () => {
    // Vacuity first: every assertion below is a count, and a broken scan
    // produces zero and reads as a clean sweep.
    expect(total(FONT_SIZE)).toBeGreaterThan(500);
    expect(total(FONT_WEIGHT)).toBeGreaterThan(200);
    expect(total(LINE_HEIGHT)).toBeGreaterThan(200);
    expect(total(SPACING)).toBeGreaterThan(1000);
    // …and it is seeing the migrated sites, so "0 literals" could never be
    // produced by a scan that simply matches nothing.
    expect(FONT_SIZE.tokenized).toBeGreaterThanOrEqual(9);
    expect(FONT_WEIGHT.tokenized).toBeGreaterThanOrEqual(15);
    expect(LINE_HEIGHT.tokenized).toBeGreaterThanOrEqual(4);
    expect(SPACING.tokenized).toBeGreaterThanOrEqual(8);
  });

  it('font-size literals do not grow', () => {
    ratchet('font-size', total(FONT_SIZE), CEILING.fontSize);
  });

  it('adds no font-size below the 11px floor', () => {
    const below = [...FONT_SIZE.literals.entries()]
      .filter(([v]) => /px$/.test(v) && px(v) < 11)
      .reduce((n, [, c]) => n + c, 0);
    expect(
      below,
      `${below} font-size declarations sit below the 11px floor (was ${CEILING.belowFloor}). ` +
        'The floor is a rung AND a bar: 11px is the smallest size this scale admits. Raising ' +
        'the floor further is one decision with raising the 13px base, per tokens.css.',
    ).toBeLessThanOrEqual(CEILING.belowFloor);
  });

  it('admits exactly two off-scale font-sizes above the top rung — the enumerated verdict pair', () => {
    // `.verdict-word` renders 27px, and 30px when the verdict is FAIL: a
    // distinction encoded by SIZE over a 1.11 ratio, below this scale's own
    // perceptibility bar. Collapsing it would delete a shipped distinction on
    // the validation surface, which is not a token slice's decision. It is
    // named here so it stays TWO declarations and does not become a habit.
    const above = [...FONT_SIZE.literals.entries()]
      .filter(([v]) => /px$/.test(v) && px(v) > 22)
      .sort(([a], [b]) => px(a) - px(b));
    expect(above).toEqual([
      ['27px', 1],
      ['30px', 1],
    ]);
  });

  it('font-weight literals do not grow', () => {
    ratchet('font-weight', total(FONT_WEIGHT), CEILING.fontWeight);
  });

  it('admits no FOURTH non-standard font-weight, and does not grow the three recorded ones', () => {
    const standard = new Set(['400', '500', '600', '700', 'inherit', 'normal', 'bold']);
    const odd = [...FONT_WEIGHT.literals.entries()].filter(([v]) => !standard.has(v));
    expect(
      odd.map(([v]) => v).sort(),
      'a font-weight outside {400,500,600,700} that is not one of the three grandfathered ' +
        'values appeared. On the shipped stack it resolves to a standard neighbour everywhere ' +
        'except macOS with a variable SF Pro, so it is a rung that exists on one laptop.',
    ).toEqual(['550', '620', '650']);
    const n = odd.reduce((x, [, c]) => x + c, 0);
    expect(
      n,
      `${n} declarations use 550/620/650 (recorded ${CEILING.nonStandardWeight}). These are ` +
        'grandfathered, not blessed: migrate 550 -> semibold and 620/650 -> bold, which is ' +
        'what a non-macOS reader already sees.',
    ).toBeLessThanOrEqual(CEILING.nonStandardWeight);
  });

  it('line-height literals do not grow', () => {
    ratchet('line-height', total(LINE_HEIGHT), CEILING.lineHeight);
  });

  it('spacing literals do not grow', () => {
    ratchet('spacing', total(SPACING), CEILING.spacing);
  });

  it('keeps the >24px tail at the recorded one-off layout offsets', () => {
    const n = [...SPACING.literals.entries()]
      .filter(([v]) => px(v) > 24)
      .reduce((x, [, c]) => x + c, 0);
    expect(
      n,
      `${n} spacing literals exceed the top rung (recorded ${CEILING.spacingAboveTopRung}). The ` +
        'scale ends at 24px because 0.46% of spacing exceeded it and each of those was a ' +
        'one-off layout offset. A growing tail means the scale needs another rung — declare ' +
        'one deliberately rather than letting the tail absorb the rhythm.',
    ).toBeLessThanOrEqual(CEILING.spacingAboveTopRung);
  });
});

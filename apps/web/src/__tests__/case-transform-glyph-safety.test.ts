/*
 * CSS `text-transform: uppercase` / `capitalize` CASE-MAPS CODEPOINTS. IT DOES NOT KNOW
 * WHICH ONES CARRY MEANING.
 *
 * ── THE DEFECT THIS GUARDS ───────────────────────────────────────────────────
 *
 * An independent design review measured, in a running instance, that the descriptor
 * form's uncertainty label — source text `Uncertainty (σ)` (U+03C3, GREEK SMALL LETTER
 * SIGMA, standard deviation) — rendered as `UNCERTAINTY (Σ)` (U+03A3, GREEK CAPITAL
 * LETTER SIGMA, summation) because `.structured-label` carried `text-transform:
 * uppercase`. `innerText` — what a screen reader announces — was the wrong symbol. The
 * fix (this branch) removed the transform and authored the label in Title Case
 * directly, and `structured-value-entry.test.tsx` pins that one label by name.
 *
 * THIS FILE generalizes the finding: the app had 49 OTHER selectors applying the same
 * transform at the time of the review (2026-09), none of which were the reported
 * defect. Reading each one's JSX by hand found none currently render a Greek letter,
 * a micro sign, or an A-with-ring in either case — but "currently" is exactly the
 * word a static one-time audit cannot keep true. This guard re-derives the same
 * check on every run instead of trusting that audit's date.
 *
 * ── WHAT IT DOES ─────────────────────────────────────────────────────────────
 *
 * 1. Parses every `.css` file under `apps/web/src` with a brace-depth walk (not a
 *    single non-nested regex — several of these rules are the only nesting-safe way
 *    to find a selector inside an `@media` block, and none currently are, but the
 *    parser does not get to assume that). For every rule whose body sets
 *    `text-transform` to `uppercase` or `capitalize`, it collects every `.class` token
 *    named in that rule's selector.
 * 2. Parses every production `.ts`/`.tsx` file (excluding `__tests__` and `.d.ts`) and,
 *    for each collected class name that appears in it, checks a bounded window of text
 *    following that class name for a character whose uppercase form is a DIFFERENT,
 *    meaning-bearing symbol: the Greek block (covers σ/Σ and the rest of the alphabet
 *    physics/chemistry borrows — α, β, δ, Δ, μ, Ω, …), the micro sign µ (U+00B5, a
 *    distinct codepoint from Greek mu), and Å/å (ångström vs. the Scandinavian letter).
 * 3. Fails, naming the file, the class, and the character, if any such pairing exists.
 *
 * A found pairing is not automatically wrong the way the sigma defect was — Δ is
 * already uppercase (the transform is then a no-op on it) and a comparison operator
 * like `×` is not a letter at all, so neither can be case-corrupted. The guard still
 * flags every hazard-block character within the window and asks a human to look,
 * because "already uppercase today" is a fact about today's copy, not a property the
 * class name promises to keep — the ROOT CAUSE here was authoring meaning-bearing
 * glyphs inside ANY class carrying this transform, not one specific label.
 *
 * ── WHY A WINDOW, NOT A JSX-AWARE PARSE ──────────────────────────────────────
 *
 * A full JSX/AST-aware "what text renders under this class" resolver would be more
 * precise, but the codebase does not otherwise carry one and building it correctly for
 * every combinator this stylesheet uses (`.a > b`, `.a b`, `.a, .b, .c`) is a
 * disproportionate build for a guard whose job is to catch a class name and its
 * rendered text sitting a few dozen characters apart, which is what actually happened
 * (`<span className="structured-label">Uncertainty (σ)</span>`). The window is
 * deliberately short (200 characters) so it cannot bridge into an unrelated sibling
 * element several lines away — verified empirically against this codebase's two
 * classes that share a file with a σ-bearing string elsewhere
 * (`guided-owner-label` / `guided-verdict-legend` in `GuidedPrompt.tsx`, which also
 * renders `answerValuePreview`'s `· σ …` suffix ~30–110 lines further down): the
 * window does not reach it, and the assertion below would fail loudly if it ever did.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

/** Locate `apps/web/src`. Duplicated from `source-is-greppable.test.ts` rather than
 *  shared, for the same reason that file gives: `import.meta.url` is an http URL under
 *  jsdom, not a file one, so the next author should not have to know that to reuse it. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC = locateSrcDir();
const REPO_ROOT = join(SRC, '..', '..', '..');

/** Every path `git ls-files` reports under a given repo-relative prefix. */
function trackedUnder(prefix: string, ...extensions: string[]): string[] {
  const out = execFileSync('git', ['ls-files', '-z', '--', prefix], {
    cwd: REPO_ROOT,
    maxBuffer: 64 * 1024 * 1024,
  });
  return out
    .toString('utf8')
    .split('\0')
    .filter((rel) => rel !== '' && extensions.some((ext) => rel.endsWith(ext)));
}

/**
 * A brace-depth walk, not a single-level `/([^{}]+)\{([^}]*)\}/g` regex: the latter
 * cannot find a selector nested inside `@media { … }`, and while nothing in this
 * stylesheet currently nests a `text-transform` rule that way, the parser should not
 * assume that stays true. Returns every {selector, body} pair for every brace block,
 * including nested ones; at-rule "selectors" (`@media …`) are returned too and
 * filtered by the caller.
 */
function parseCssBlocks(css: string): Array<{ selector: string; body: string }> {
  const blocks: Array<{ selector: string; body: string }> = [];
  const stack: Array<{ selectorStart: number }> = [];
  let selectorStart = 0;
  for (let i = 0; i < css.length; i += 1) {
    const ch = css[i];
    if (ch === '{') {
      const selector = css.slice(selectorStart, i).trim();
      stack.push({ selectorStart });
      // Body scanning starts fresh from just past this brace.
      selectorStart = i + 1;
      blocks.push({ selector, body: '' }); // body filled in on matching '}'
      (blocks[blocks.length - 1] as { bodyStart?: number }).bodyStart = i + 1;
      continue;
    }
    if (ch === '}') {
      stack.pop();
      // Find the most recently opened, not-yet-closed block (the last one pushed
      // whose body is still empty placeholder) — since we process linearly and each
      // '{' immediately records a placeholder, the last pushed entry with an unset
      // body is the one this '}' closes.
      for (let b = blocks.length - 1; b >= 0; b -= 1) {
        const rec = blocks[b] as { selector: string; body: string; bodyStart?: number; closed?: boolean };
        if (rec.bodyStart !== undefined && !rec.closed) {
          rec.body = css.slice(rec.bodyStart, i);
          rec.closed = true;
          break;
        }
      }
      selectorStart = i + 1;
    }
  }
  return blocks;
}

/** `.class` tokens named anywhere in a selector, e.g. `.a, .b > span` -> ['a', 'b']. */
function classTokens(selector: string): string[] {
  const matches = selector.match(/\.[-\w]+/g) ?? [];
  return matches.map((m) => m.slice(1));
}

/** Greek block + extended, the micro sign, and A-with-ring (both cases). Every one of
 *  these has an upper/lower pair where at least one member is a specific scientific
 *  symbol distinct in meaning from the other case. */
const HAZARD_RE = /[Ͱ-Ͽἀ-῿µÅå]/gu;

/** Strip CSS block comments before parsing. Without this, a comment mentioning a
 *  selector in prose (e.g. `graph.css`'s own note comparing itself to `.placeholder
 *  p`'s specificity) gets swallowed into the NEXT rule's "selector" text by
 *  `parseCssBlocks`, which only looks at the text since the last brace — and
 *  produced exactly that false positive (".placeholder" flagged as hazard-adjacent)
 *  the first time this guard ran. */
function stripCssComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '');
}

function collectUppercaseClasses(): Map<string, Array<{ file: string; selector: string }>> {
  const byClass = new Map<string, Array<{ file: string; selector: string }>>();
  for (const rel of trackedUnder('apps/web/src/', '.css')) {
    const abs = join(REPO_ROOT, rel);
    if (!existsSync(abs)) continue;
    const css = stripCssComments(readFileSync(abs, 'utf8'));
    for (const { selector, body } of parseCssBlocks(css)) {
      if (selector.startsWith('@')) continue;
      if (!/text-transform:\s*(uppercase|capitalize)/.test(body)) continue;
      for (const cls of classTokens(selector)) {
        const list = byClass.get(cls) ?? [];
        list.push({ file: rel, selector });
        byClass.set(cls, list);
      }
    }
  }
  return byClass;
}

const WINDOW = 200;

describe('no case-transformed label renders a meaning-bearing non-Latin glyph', () => {
  it('finds at least one uppercase/capitalize rule, and the known-safe ones, so the ' +
    'scan really ran', () => {
    const byClass = collectUppercaseClasses();
    expect(byClass.size).toBeGreaterThan(10);
    expect(byClass.has('eyebrow')).toBe(true);
    expect(byClass.has('structured-label')).toBe(false); // fixed by this branch
  });

  it('no production source file pairs a hazard glyph with one of those classes ' +
    'within a short window', () => {
    const byClass = collectUppercaseClasses();
    const classNames = [...byClass.keys()];

    const sourceFiles = trackedUnder('apps/web/src/', '.ts', '.tsx').filter(
      (rel) => !rel.includes('/__tests__/') && !rel.endsWith('.d.ts') && !rel.endsWith('.test.ts') && !rel.endsWith('.test.tsx'),
    );
    // A floor, so a broken tracked-path call cannot pass this test by scanning nothing.
    expect(sourceFiles.length).toBeGreaterThan(50);

    const offenders: string[] = [];
    for (const rel of sourceFiles) {
      const abs = join(REPO_ROOT, rel);
      if (!existsSync(abs) || !statSync(abs).isFile()) continue;
      const text = readFileSync(abs, 'utf8');
      // Only occurrences of a class name INSIDE an actual `className=` attribute
      // count — a bare word match found `.placeholder` (a real class) against the
      // unrelated JSX prop `placeholder="..."` that appears throughout this codebase
      // and flagged every such input as a false positive. `className=` is followed
      // by a quoted string, a template literal, or a `{…}` expression (e.g.
      // `clsx(...)`); each form is captured by its own closing delimiter so the
      // window below starts at the END of the attribute, in the element's children,
      // not inside an unrelated string elsewhere in the file.
      for (const attrMatch of text.matchAll(/className\s*=\s*(["'`{])/g)) {
        const openChar = attrMatch[1];
        const startOfValue = (attrMatch.index ?? 0) + attrMatch[0].length;
        let endOfValue: number;
        if (openChar === '{') {
          let depth = 1;
          let i = startOfValue;
          for (; i < text.length && depth > 0; i += 1) {
            if (text[i] === '{') depth += 1;
            else if (text[i] === '}') depth -= 1;
          }
          endOfValue = i;
        } else {
          const closeIdx = text.indexOf(openChar, startOfValue);
          endOfValue = closeIdx === -1 ? text.length : closeIdx + 1;
        }
        const attrValue = text.slice(startOfValue, endOfValue);
        const matchedClasses = classNames.filter((cls) =>
          new RegExp(`\\b${cls.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`).test(attrValue),
        );
        if (matchedClasses.length === 0) continue;
        const window = text.slice(endOfValue, endOfValue + WINDOW);
        const hazard = window.match(HAZARD_RE);
        if (hazard) {
          for (const cls of matchedClasses) {
            offenders.push(
              `${rel}: class "${cls}" within ${WINDOW} chars after its className attribute closes, near ${JSON.stringify([...new Set(hazard)])}`,
            );
          }
        }
      }
    }

    expect(
      [...new Set(offenders)],
      'a case-transform rule is being applied near a Greek letter, µ, or Å/å — check ' +
        'whether the transform would change what the symbol means (see StructuredValueEntry.tsx / assistant.css .structured-label for the fixed example)',
    ).toEqual([]);
  });
});

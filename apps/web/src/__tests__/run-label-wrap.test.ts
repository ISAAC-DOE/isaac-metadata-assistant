/*
 * RUN LABELS WRAP, NEVER CLIP — final review of #279, P2.
 *
 * An imported record's runs carry long labels ("Legacy 3 · 02 · SYN2 · base ·
 * after1500Cycles…"), and two of them can differ only in their LAST token. On a
 * phone the list clipped them: `.run-card-name` was `flex: none`, so it could not
 * shrink and ran out of the card (measured scrollWidth 521 at 390px), cutting off
 * the very token that told two "Legacy 3" runs apart.
 *
 * jsdom computes no layout, so this pins the STRUCTURE that makes wrapping
 * possible on every surface that names a run: the list row and the focused
 * heading (`.run-card-name`), the Record Map header (`.rsm-subject`), and the
 * compare view's labels. The layout itself is verified in a real browser at
 * 390/320 with a long synthetic label (see the review-fix report).
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = resolve(__dirname, '..');

/** Every declaration block whose selector list contains `selector` exactly. */
function blocksFor(css: string, selector: string): string[] {
  const out: string[] = [];
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const re = /([^{}]+)\{([^}]*)\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(stripped)) !== null) {
    const selectors = m[1].split(',').map((part) => part.trim());
    if (selectors.includes(selector)) out.push(m[2]);
  }
  return out;
}

function declares(blocks: string[], property: string, value: string): boolean {
  const re = new RegExp(`(?:^|;)\\s*${property}\\s*:\\s*${value}\\s*(?:;|$)`);
  return blocks.some((body) => re.test(body));
}

const SURFACES: readonly (readonly [file: string, selector: string])[] = [
  ['components/runs.css', '.run-card-name'],
  ['components/run-schema-mirror.css', '.rsm-subject'],
  ['components/run-compare.css', '.rc-side-label'],
  ['components/run-compare.css', '.rc-context-label'],
  ['components/run-compare.css', '.rc-detail-label'],
  ['components/run-compare.css', '.rc-verdict-label'],
  ['components/run-compare.css', '.rc-table th'],
];

describe('every surface that names a run lets a long label wrap', () => {
  it.each(SURFACES)('%s %s may shrink (min-width: 0) and break anywhere', (file, selector) => {
    const css = readFileSync(join(SRC, file), 'utf8');
    const blocks = blocksFor(css, selector);
    expect(blocks.length, `${selector} has no rule in ${file}`).toBeGreaterThan(0);
    expect(declares(blocks, 'min-width', '0'), `${selector}: min-width: 0`).toBe(true);
    expect(declares(blocks, 'overflow-wrap', 'anywhere'), `${selector}: overflow-wrap: anywhere`).toBe(
      true,
    );
  });

  it('MUTATION-GUARDED: the run name is no longer `flex: none` — the declaration that clipped it', () => {
    const css = readFileSync(join(SRC, 'components/runs.css'), 'utf8');
    expect(declares(blocksFor(css, '.run-card-name'), 'flex', 'none')).toBe(false);
  });
});

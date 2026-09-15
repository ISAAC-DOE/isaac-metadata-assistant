/**
 * THE SETTINGS FIGURE GRID'S FINAL-ROW RULE IS COLUMN-COUNT DEPENDENT, and a
 * guard is the only thing that keeps the two halves in step.
 *
 * `.settings-figure` carries a `border-bottom` as a row separator.
 * `screens.css` drops it from both cells of the LAST ROW so the table does not
 * end in a rule that stops halfway across:
 *
 *     .settings-figure:last-child,
 *     .settings-figure:nth-last-child(2):nth-child(odd) { border-bottom: none }
 *
 * The second selector means "the left-hand cell of the final row", and it only
 * means that while the grid has TWO columns. Inside
 * `@media (max-width: 640px)` the grid becomes `grid-template-columns: 1fr`,
 * and an odd-indexed second-to-last cell is then the second-to-last ROW --
 * so dropping its border deletes a separator from the middle of the list.
 *
 * That shipped for one commit and was found by independent review, not by any
 * test, which is why this file exists. It asserts the PAIRING rather than
 * either rule: whatever media query makes the grid single-column must also
 * restore the neighbour's border.
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(
  join(resolve(__dirname, '..'), 'screens/screens.css'),
  'utf8',
);

/** Comments stripped, so prose describing a rule cannot satisfy a check. */
const BARE = CSS.replace(/\/\*[\s\S]*?\*\//g, '');

/** The body of every `@media` block, keyed by its condition text. */
function mediaBlocks(css: string): { condition: string; body: string }[] {
  const out: { condition: string; body: string }[] = [];
  const re = /@media([^{]+)\{/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(css)) !== null) {
    // Walk braces from the block's opening one to find its matching close.
    let depth = 1;
    let i = re.lastIndex;
    while (i < css.length && depth > 0) {
      if (css[i] === '{') depth += 1;
      else if (css[i] === '}') depth -= 1;
      i += 1;
    }
    out.push({ condition: m[1].trim(), body: css.slice(re.lastIndex, i - 1) });
  }
  return out;
}

const SINGLE_COLUMN = /\.settings-figures\s*\{[^}]*grid-template-columns:\s*1fr/;
const NEIGHBOUR = /\.settings-figure:nth-last-child\(2\):nth-child\(odd\)\s*\{([^}]*)\}/;

describe('the settings figure grid keeps its separators at every width', () => {
  it('is not vacuous — the base rule and a single-column media block both exist', () => {
    expect(
      NEIGHBOUR.test(BARE),
      'the final-row neighbour rule is gone; this guard has nothing to protect',
    ).toBe(true);
    const collapsing = mediaBlocks(BARE).filter((b) => SINGLE_COLUMN.test(b.body));
    expect(
      collapsing.length,
      'no media query makes `.settings-figures` single-column — has the layout changed?',
    ).toBeGreaterThan(0);
  });

  it('MUTATION-GUARDED: every single-column block restores the neighbour border', () => {
    /*
     * MUTATION: deleting the `.settings-figure:nth-last-child(2):nth-child(odd)`
     * restore from inside `@media (max-width: 640px)` makes this RED and names
     * the condition. That deletion is exactly the state that shipped.
     */
    const offenders: string[] = [];
    for (const block of mediaBlocks(BARE)) {
      if (!SINGLE_COLUMN.test(block.body)) continue;
      const restore = NEIGHBOUR.exec(block.body);
      if (restore === null || !/border-bottom:\s*1px/.test(restore[1])) {
        offenders.push(block.condition);
      }
    }
    expect(
      offenders,
      'a media query collapses `.settings-figures` to one column without restoring ' +
        '`.settings-figure:nth-last-child(2):nth-child(odd)`\'s border. At one column that ' +
        'selector is the second-to-last ROW, not the final row\'s left cell, so the base ' +
        'rule deletes a separator from the middle of the list.',
    ).toEqual([]);
  });

  it('the last row itself is never restored — a list must not close with a rule', () => {
    /*
     * The complement, so a future "fix" cannot over-correct by restoring both.
     * `:last-child` losing its border is about the last ROW and is correct at
     * every column count.
     */
    for (const block of mediaBlocks(BARE)) {
      if (!SINGLE_COLUMN.test(block.body)) continue;
      const lastChild = /\.settings-figure:last-child\s*\{([^}]*)\}/.exec(block.body);
      if (lastChild !== null) {
        expect(
          lastChild[1],
          'a single-column block restored `:last-child`\'s border, closing the list with a rule',
        ).not.toMatch(/border-bottom:\s*1px/);
      }
    }
  });
});

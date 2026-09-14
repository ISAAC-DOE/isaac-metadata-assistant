/**
 * THE RECORD SIDEBAR HAS ONE GUTTER, AND A SPLIT LANDMARK LOST IT.
 *
 * Found by the project owner looking at the screen, not by any test. Promoting
 * capture out of `.workspace-nav` into its own `<nav>` (so it could render above
 * the workflow spine) took that rule's `12px` horizontal padding with it and
 * replaced it with nothing. Measured in a browser before the fix:
 *
 *     .capture-nav-link      17–229     <- flush to both inner edges
 *     .workspace-nav-list a  29–217
 *     .spine-steps           29–217
 *     .evidence-trail-link   29–217
 *
 * The promoted card was 24px wider than every neighbour and touched the
 * sidebar's border. After: all four at 29–217.
 *
 * WHY THIS TEST READS CSS INSTEAD OF MEASURING. jsdom computes no layout, so
 * `getBoundingClientRect` is all zeroes here and the geometry above can only be
 * checked in a real browser. What CAN be checked cheaply, on every run, is the
 * INVARIANT the geometry follows from: every block-level container in this
 * column declares the same horizontal padding. That is the thing a future split
 * would forget again.
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = resolve(__dirname, '..');

function horizontalPadding(body: string): string {
  const m = /(?:^|;)\s*padding:\s*([^;]+)/.exec(body);
  if (m === null) throw new Error(`no padding declaration in: ${body.trim().slice(0, 80)}`);
  const parts = m[1].trim().split(/\s+/);
  // CSS shorthand: 1 = all, 2 = v h, 3 = t h b, 4 = t r b l
  if (parts.length === 1) return parts[0];
  if (parts.length === 2 || parts.length === 3) return parts[1];
  return `${parts[3]}/${parts[1]}`;
}

describe('the record sidebar has ONE gutter', () => {
  it('the two nav landmarks share ONE padding rule, so they cannot diverge', () => {
    /*
     * STRONGER THAN THE FIRST VERSION OF THIS TEST, which compared two separate
     * rules and asserted the values matched. They can only match if someone
     * keeps them matching — and the defect this file exists for is precisely
     * that they stopped: splitting the capture row into its own landmark took
     * `.workspace-nav`'s 12px with it and left nothing behind, rendering the
     * card 24px wider than every neighbour and flush to the sidebar border.
     *
     * One selector list cannot come apart that way, so the invariant is now
     * structural and this test guards the STRUCTURE rather than a coincidence.
     * (It also removed three hand-authored literals — `type-scale-and-spacing`
     * caps those, and duplicating the declaration had pushed it over.)
     */
    const css = readFileSync(join(SRC, 'components/record-workspaces.css'), 'utf8');
    const shared = /^\.workspace-nav,\s*\n\.capture-nav\s*\{([^}]*)\}/m.exec(css);
    expect(
      shared,
      'the capture landmark and the workspace list no longer share one padding rule. ' +
        'They had identical padding and were split once before, which is how the capture ' +
        'card ended up 24px wider than every neighbour. Keep them in one selector list.',
    ).not.toBeNull();
    expect(horizontalPadding(shared![1])).toBe('12px');

    /*
     * …and neither declares its OWN competing padding elsewhere. The shared
     * rule is removed from the text first: its second line IS `.capture-nav {`,
     * so a naive search finds the very rule it is meant to protect — which is
     * what the first version of this assertion did.
     */
    const withoutShared = css.replace(shared![0], '');
    expect(
      /^\.capture-nav\s*\{[^}]*padding:/m.test(withoutShared),
      '`.capture-nav` declares its own padding again, which re-opens the divergence the ' +
        'shared rule closes.',
    ).toBe(false);
  });

  it('the FIRST eyebrow draws no divider, because it separates nothing', () => {
    /*
     * `.workspace-nav-eyebrow` carries a `border-top` to divide two lists. The
     * capture eyebrow is now the first element in the sidebar, so that hairline
     * ran across the top of the column with nothing above it.
     */
    const css = readFileSync(join(SRC, 'components/record-workspaces.css'), 'utf8');
    expect(
      /\.capture-nav\s+\.workspace-nav-eyebrow\s*\{[^}]*border-top:\s*0/.test(css),
      'the capture eyebrow draws a border-top again. It is the first element in the sidebar, ' +
        'so that line separates nothing — remove it there and leave the Workspaces one alone.',
    ).toBe(true);
    // The Workspaces eyebrow MUST keep its divider: it really does divide two lists.
    expect(
      /^\.workspace-nav-eyebrow\s*\{[^}]*border-top:\s*1px/m.test(css),
      'the Workspaces eyebrow lost its divider, which is the one that does separate two lists.',
    ).toBe(true);
  });
});

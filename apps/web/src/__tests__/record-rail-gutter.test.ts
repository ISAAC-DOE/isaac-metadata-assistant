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

function ruleBody(file: string, selector: string): string {
  const css = readFileSync(join(SRC, file), 'utf8');
  // The rule as authored: `selector {` … `}` at the start of a line.
  const re = new RegExp(`^\\${selector.startsWith('.') ? '' : ''}${selector.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}\\s*\\{([^}]*)\\}`, 'm');
  const m = re.exec(css);
  if (m === null) throw new Error(`no rule for ${selector} in ${file}`);
  return m[1];
}

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
  it('every container in the column declares the same horizontal padding', () => {
    const gutters = {
      '.capture-nav': horizontalPadding(ruleBody('components/record-workspaces.css', '.capture-nav')),
      '.workspace-nav': horizontalPadding(ruleBody('components/record-workspaces.css', '.workspace-nav')),
    };
    expect(
      new Set(Object.values(gutters)).size,
      'the capture landmark and the workspace list declare DIFFERENT horizontal padding, so ' +
        'one of them will not line up with the spine and the Evidence Trail card. Measured ' +
        `gutters: ${JSON.stringify(gutters)}`,
    ).toBe(1);
    // …and it is the value the rest of the column uses, not merely a shared one.
    expect(Object.values(gutters)[0]).toBe('12px');
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

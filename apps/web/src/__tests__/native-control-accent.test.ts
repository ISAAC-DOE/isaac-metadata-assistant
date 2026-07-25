import { describe, it, expect } from 'vitest';

/*
 * Native checkboxes and radios must never be left at `accent-color: auto`.
 *
 * `auto` paints the control in the VIEWER'S OS accent — crimson in a default
 * Chromium. tokens.css reserves saturated red for the validation verdict
 * ("signal 1 — validation verdict (RESERVED, hard gate)"), so an advisory
 * control rendering itself red is a failure marker the design system never
 * authorised, and the colour changes from machine to machine.
 *
 * Rule: every source file that renders a native checkbox/radio must be covered
 * by an explicit `accent-color` declaration whose selector names a class that
 * file uses. Sources are read as raw strings via import.meta.glob, exactly like
 * no-vertical-rail.test.ts — no node:fs, no @types/node.
 */

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const tsxFiles = import.meta.glob('../**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const NATIVE_CONTROL = /type=["'](?:checkbox|radio)["']/;

/** Comments explain the rule and would otherwise trip the scan reading it —
 *  blanked (not deleted) so line numbers still point at the real source line. */
const stripComments = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, ' '));

/** Class tokens that appear in a selector carrying an explicit accent-color. */
function accentStyledClasses(): Set<string> {
  const out = new Set<string>();
  for (const source of Object.values(cssFiles)) {
    for (const block of stripComments(source).split('}')) {
      const brace = block.indexOf('{');
      if (brace === -1) continue;
      if (!/accent-color\s*:/.test(block.slice(brace))) continue;
      for (const m of block.slice(0, brace).matchAll(/\.([A-Za-z0-9_-]+)/g)) out.add(m[1]);
    }
  }
  return out;
}

describe('native form controls carry an explicit accent colour', () => {
  it('no stylesheet leaves accent-color at the OS default', () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(cssFiles)) {
      stripComments(source)
        .split('\n')
        .forEach((line, i) => {
          if (/accent-color\s*:\s*auto\b/.test(line)) offenders.push(`${path}:${i + 1}`);
        });
    }
    expect(offenders, `accent-color: auto found:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('every file rendering a native checkbox/radio is covered by an accent-color rule', () => {
    const styled = accentStyledClasses();
    const withControls = Object.entries(tsxFiles).filter(([, s]) => NATIVE_CONTROL.test(s));
    // Not vacuous: the app really does render at least one native control.
    expect(withControls.length).toBeGreaterThan(0);
    expect(styled.size).toBeGreaterThan(0);

    const offenders = withControls
      .filter(([, source]) => ![...styled].some((cls) => source.includes(cls)))
      .map(([path]) => path);
    expect(
      offenders,
      `native checkbox/radio with no accent-color rule:\n${offenders.join('\n')}`,
    ).toEqual([]);
  });
});

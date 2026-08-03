/*
 * R1b · the verdict card must not render terminal output the app never produced.
 *
 * WHAT SHIPPED. `components/VerdictCard.tsx` rendered, in a monospace
 * command-styled block, `isaac validate --official · exit {result.exitCode}` — on
 * the single highest-trust surface in the product, the verdict that gates export.
 *
 * NO CLI IS EVER INVOKED. There is no subprocess anywhere in the frontend, and
 * the backend routes the verdict comes from call the Python function
 * `isaac_records.official.validate_official` in-process. `exitCode` was fabricated
 * client-side in three places, each a literal `ok ? 0 : 1`:
 *   lib/adapt.ts (toValidationResult), screens/ExportReadiness.tsx (post-export),
 *   components/RecordValidator.tsx (toValidationResult).
 * A displayed exit code that no process exited with is a fabricated observation,
 * not a rounding error — the same class of defect as a fabricated count.
 *
 * WHAT IS STILL LEGITIMATE, and deliberately asserted here so a later slice does
 * not "fix" it away: the card may say the verdict is the SAME schema gate that
 * backs export. That is true by construction — both paths call the one
 * `validate_official` over the one vendored schema. Naming the CLI as a PARITY
 * claim in prose ("the same gate `isaac validate --official` runs", which
 * `RecordValidator` says about itself) is also fine. What is banned is rendering
 * a command line plus an exit code as if they were captured output.
 *
 * WHAT THIS CANNOT CATCH. It scans for the shapes that shipped — a `.verdict-cmd`
 * node, a command-with-exit-code string, and any surviving `exitCode` producer. A
 * newly invented fake transcript ("$ isaac export → wrote 2 files") in a different
 * class would pass. Review remains the backstop.
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';

import { VerdictCard } from '../components/VerdictCard';
import type { ValidationResult } from '../lib/types';

const PASS: ValidationResult = {
  verdict: 'pass',
  ok: true,
  schemaVersion: 'v1.05',
  errors: [],
};

const FAIL: ValidationResult = {
  verdict: 'fail',
  ok: false,
  schemaVersion: 'v1.05',
  errors: [{ path: 'record.sample', message: 'is a required property' }],
};

// --- the rendered card -------------------------------------------------------

/** A command line the app did not run, or an exit code no process produced. */
const FABRICATED_TRANSCRIPT: [string, RegExp][] = [
  ['a rendered `isaac` command line', /\bisaac\s+\w+(\s+--\w+)?\s*·/i],
  ['an exit code', /\bexit\s+\d+\b/i],
  ['a shell prompt', /(^|\s)\$\s+\w/],
];

describe('R1b · VerdictCard renders no fabricated CLI transcript', () => {
  it.each([
    ['PASS', PASS],
    ['FAIL', FAIL],
  ])('the %s card has no command-styled transcript node', (_verdict, result) => {
    const { container } = render(<VerdictCard result={result} />);
    expect(container.querySelector('.verdict-cmd')).toBeNull();
  });

  it.each([
    ['PASS', PASS],
    ['FAIL', FAIL],
  ])('the %s card renders no command line and no exit code', (_verdict, result) => {
    const { container } = render(<VerdictCard result={result} />);
    const text = container.textContent ?? '';
    for (const [what, pattern] of FABRICATED_TRANSCRIPT) {
      expect(text, `the verdict must not render ${what}`).not.toMatch(pattern);
    }
  });

  it('still states the deterministic verdict and the schema it was checked against', () => {
    // Removing the fake transcript must not take the real claim with it.
    const { container } = render(<VerdictCard result={PASS} />);
    const text = container.textContent ?? '';
    expect(text).toMatch(/PASS/);
    expect(text).toMatch(/official ISAAC schema v1\.05/i);
  });

  it('may still say it is the same gate that backs export — that claim is true', () => {
    const { container } = render(<VerdictCard result={PASS} />);
    expect(container.textContent ?? '').toMatch(/same gate that backs export/i);
  });
});

// --- no surviving producer ---------------------------------------------------

function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();
const NOT_PRODUCT_CODE = new Set(['__tests__', 'test']);

function frontendSourceFiles(dir: string = SRC_DIR): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!NOT_PRODUCT_CODE.has(entry.name)) found.push(...frontendSourceFiles(full));
    } else if (/\.tsx?$/.test(entry.name) && !entry.name.endsWith('.d.ts') && !/\.test\.tsx?$/.test(entry.name)) {
      found.push(relative(SRC_DIR, full).split(sep).join('/'));
    }
  }
  return found.sort();
}

describe('R1b · nothing fabricates an exit code any more', () => {
  const files = frontendSourceFiles();

  it('scans the real sources', () => {
    expect(files.length).toBeGreaterThan(40);
    for (const covered of [
      'components/RecordValidator.tsx',
      'components/VerdictCard.tsx',
      'lib/adapt.ts',
      'lib/types.ts',
      'screens/ExportReadiness.tsx',
    ]) {
      expect(files).toContain(covered);
    }
  });

  /** Comments are stripped, so the prose RECORDING the retired field (in
   *  `VerdictCard.tsx` and `lib/types.ts`) is not counted as the field. That is
   *  the same trade the sibling honesty guards make: a note about a defect must
   *  never read as the defect, at the cost of saying nothing about comments. */
  function code(path: string): string {
    return readFileSync(join(SRC_DIR, path), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1');
  }

  it('no source file produces or reads an exit code any more', () => {
    const offenders = files.filter((path) => /exitCode/.test(code(path)));
    expect(offenders).toEqual([]);
  });

  it('`ValidationResult` no longer declares the field, so it cannot come back by accident', () => {
    const types = code('lib/types.ts');
    const iface = /export interface ValidationResult \{[\s\S]*?\n\}/.exec(types);
    expect(iface, 'ValidationResult must still exist').not.toBeNull();
    expect(iface![0]).not.toMatch(/exitCode/);
    // ...and the fields that carry the REAL, server-derived verdict stay.
    expect(iface![0]).toMatch(/verdict/);
    expect(iface![0]).toMatch(/schemaVersion/);
  });
});

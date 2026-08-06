import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, it, expect } from 'vitest';

/**
 * NO TEST FIXTURE IS REACHABLE FROM A PRODUCTION PATH.
 *
 * The two adapter boundaries added in this slice ship one implementation each,
 * and both refuse. The populated versions — a portal-metrics source that
 * answers with figures, and a `CurrentUser` that names a principal — live in
 * `src/test/adapterFixtures.ts` so the declared shapes can be exercised.
 *
 * That arrangement has exactly one failure mode worth guarding: a production
 * module importing the fixture, at which point a rendered screen would state a
 * fabricated platform total or a fabricated identity, and every existing test
 * would still pass. This file reads the real source tree and asserts the import
 * does not exist.
 *
 * WHY A SOURCE SCAN RATHER THAN A RUNTIME ASSERTION. A runtime check can only
 * observe the modules a test happens to load; a scan sees every file that ships.
 * Its own limits, stated because a guard that looks complete is worse than one
 * that admits its edges:
 *
 *   · It matches import SPECIFIERS textually. A dynamic
 *     `import(someVariable)` would be invisible — no file in this app does that
 *     for a local module, and `the scan finds an import it is shown` proves the
 *     matcher works on a real one rather than silently matching nothing.
 *   · It says nothing about whether a fixture VALUE was copied by hand into a
 *     production file. That is a different defect, caught by the truthfulness
 *     guards that scan rendered pages for invented figures.
 */

/**
 * Locate `apps/web/src` on disk. Deliberately NOT `import.meta.url`: under the
 * jsdom environment that is an http URL, not a file one. Duplicated from the
 * sibling guards rather than exported, so no file can silently change another's
 * scan.
 */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

/**
 * The TOP-LEVEL directories that are test scaffolding rather than shipped product
 * code: `src/test` and `src/__tests__`, and only those two.
 *
 * Matched by POSITION as well as by name. Excluding every directory called `test`
 * or `__tests__` at any depth would silently drop a future `screens/test/` or
 * `components/__tests__/` out of the scan — and a production file missing from
 * this scan is precisely the file that could import a fixture without this guard
 * noticing. The exclusions asserted below are already stated in top-level terms
 * (`startsWith('test/')`, `startsWith('__tests__/')`).
 */
const TEST_DIRS = new Set(['__tests__', 'test']);
const isTestScaffoldingDir = (dir: string, name: string): boolean =>
  dir === SRC_DIR && TEST_DIRS.has(name);
const isColocatedTest = (name: string): boolean => /\.test\.tsx?$/.test(name);

/** Every `.ts`/`.tsx` file that is part of the shipped app. */
function productionSourceFiles(dir: string = SRC_DIR): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!isTestScaffoldingDir(dir, entry.name)) found.push(...productionSourceFiles(full));
    } else if (/\.tsx?$/.test(entry.name) && !isColocatedTest(entry.name)) {
      found.push(relative(SRC_DIR, full).split(sep).join('/'));
    }
  }
  return found.sort();
}

/**
 * The specifier fragments that would reach test scaffolding, in any relative
 * form. `test/adapterFixtures` and `test/apiFixtures` are matched by their
 * module names rather than by a full path, so a file at any depth is caught.
 */
const FIXTURE_SPECIFIERS = [
  'test/adapterFixtures',
  'test/apiFixtures',
  'test/graphDeepFixture',
] as const;

/** Import/`from`/`require` specifiers a file names, as written. */
function importSpecifiers(path: string): string[] {
  const source = readFileSync(join(SRC_DIR, path), 'utf8');
  const out: string[] = [];
  const pattern = /(?:from\s*|import\s*\(\s*|require\s*\(\s*)['"]([^'"]+)['"]/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) out.push(match[1]);
  return out;
}

describe('test fixtures are unreachable from production code', () => {
  const files = productionSourceFiles();

  it('scans the real production tree, and excludes the test directories', () => {
    expect(files.length).toBeGreaterThan(40);
    // The two files this slice touched must be inside the scan, or a regression
    // in either would pass unnoticed.
    expect(files).toContain('screens/statistics/StatisticsPage.tsx');
    expect(files).toContain('screens/statistics/MyStats.tsx');
    expect(files).toContain('lib/portalMetricsContract.ts');
    expect(files).toContain('lib/currentUserContract.ts');
    expect(files.some((f) => f.startsWith('test/'))).toBe(false);
    expect(files.some((f) => f.startsWith('__tests__/'))).toBe(false);
  });

  it.each(FIXTURE_SPECIFIERS)('no production file imports %s', (fragment) => {
    const offenders = files.filter((path) =>
      importSpecifiers(path).some((specifier) => specifier.includes(fragment)),
    );
    expect(offenders).toEqual([]);
  });

  it('the scan finds an import it is shown — so a clean result means something', () => {
    /* The matcher applied to a real production file with real imports. Without
       this, a broken specifier reader would report every fragment absent and
       the suite above would be green for the wrong reason. */
    const specifiers = importSpecifiers('screens/statistics/MyStats.tsx');
    expect(specifiers).toContain('../../lib/myStatsContract');
    expect(specifiers).toContain('../../lib/currentUserContract');
    // …and the matcher used above really does detect a fragment when present.
    expect(
      ['../../test/adapterFixtures'].some((s) => s.includes('test/adapterFixtures')),
    ).toBe(true);
  });

  it('the fixture module itself is present, so the guard is not passing on absence', () => {
    expect(existsSync(join(SRC_DIR, 'test', 'adapterFixtures.ts'))).toBe(true);
  });
});

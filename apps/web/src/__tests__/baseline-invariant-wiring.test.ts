/**
 * THE WIRING THAT MAKES THE FAST BASELINE INVARIANTS RUN AT ALL.
 *
 * `e2e/invariants/baseline-aggregate.invariant.test.ts` moved the baseline
 * consistency check out of the ~30-minute `browser-a11y` job and into the fast
 * `frontend` job. The whole of that protection rests on ONE glob in
 * `vite.config.ts` matching ONE file.
 *
 * That is a single point of failure whose failure mode is SILENCE. Rename the
 * file, move `e2e/invariants/` under `e2e/mutation/`, or edit the pattern, and
 * `npm test` stays green with zero invariant tests running — vitest's
 * `passWithNoTests` only fires when the WHOLE run finds nothing, and `src/**`
 * always matches well over a hundred files. The repository would revert to the
 * 30-minute-only state without a single red result anywhere.
 *
 * This repo has the scar already: `e2e/tsconfig.json`'s own `//include` note
 * records `playwright.bench.config.ts` being invisible to `tsc` for exactly this
 * reason, found only by `tsc --listFiles`.
 *
 * So the glob is asserted, and the file it must match is asserted to exist.
 *
 * IT ALSO PINS THE ONE CLAIM THE WIRING'S SAFETY ARGUMENT RESTS ON — that
 * nothing in the invariant file's dependency chain imports `@playwright/test`
 * AS A VALUE. The chain does REFERENCE it (`e2e/surfaces.ts` types a locator
 * role through `Parameters<import('@playwright/test').Page['getByRole']>`), and
 * an earlier comment claimed otherwise. A type-only inline `import(...)` is
 * erased at transform time and costs nothing; a value import would drag
 * Playwright's runtime into the jsdom suite. The difference is the whole
 * argument, so it is measured here rather than asserted in prose.
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/** Repo-relative to `apps/web`, which is vitest's `root` for this project. */
const WEB_ROOT = process.cwd();
const INVARIANT_GLOB = 'e2e/**/*.invariant.test.ts';
const INVARIANT_DIR = join(WEB_ROOT, 'e2e', 'invariants');

/** The modules the invariant suite pulls in, in dependency order. */
const CHAIN = [
  'e2e/baseline-aggregate.ts',
  'e2e/a11y-baseline.ts',
  'e2e/layout-baseline.ts',
  'e2e/surfaces.ts',
  'e2e/env.ts',
];

describe('the fast baseline invariants are actually collected', () => {
  it('vite.config.ts still includes the invariant glob', () => {
    const config = readFileSync(join(WEB_ROOT, 'vite.config.ts'), 'utf8');
    expect(
      config.includes(`'${INVARIANT_GLOB}'`),
      `vite.config.ts no longer includes '${INVARIANT_GLOB}' in test.include. Without it the ` +
        `baseline aggregate consistency check runs ONLY in the ~30-minute browser-a11y job again, ` +
        `and nothing would have gone red to say so.`
    ).toBe(true);
  });

  it('at least one file actually matches that glob', () => {
    expect(existsSync(INVARIANT_DIR), `${INVARIANT_DIR} does not exist`).toBe(true);
    const matches = readdirSync(INVARIANT_DIR).filter((f) => f.endsWith('.invariant.test.ts'));
    expect(
      matches.length,
      `no *.invariant.test.ts file exists under e2e/invariants/, so the glob in vite.config.ts ` +
        `matches nothing and npm test is green while checking nothing`
    ).toBeGreaterThan(0);
  });

  it('the aggregate invariant file specifically is present', () => {
    expect(existsSync(join(INVARIANT_DIR, 'baseline-aggregate.invariant.test.ts'))).toBe(true);
  });
});

describe('nothing in the invariant dependency chain imports @playwright/test as a value', () => {
  /*
   * A VALUE import is `import ... from '@playwright/test'` or `require(...)`.
   * A TYPE-ONLY reference is `import type ... from`, or an inline
   * `import('@playwright/test')` used in a type position — both erased by
   * esbuild, so neither reaches the jsdom runtime.
   *
   * The distinction is drawn by pattern rather than by parsing, and the patterns
   * are deliberately conservative: a `import('@playwright/test')` that is NOT in
   * a type position (a genuine dynamic import) would be missed. That case is
   * called out rather than silently tolerated — it would also be a bizarre thing
   * to write in a data module, and the positive check below (the chain imports
   * cleanly under vitest at all) is what would actually catch it.
   */
  const VALUE_IMPORT = /(^|\n)\s*import\s+(?!type\b)[^;\n]*from\s*['"]@playwright\/test['"]/;
  const REQUIRE = /require\(\s*['"]@playwright\/test['"]\s*\)/;

  for (const rel of CHAIN) {
    it(`${rel} has no value import of @playwright/test`, () => {
      const src = readFileSync(join(WEB_ROOT, rel), 'utf8');
      expect(VALUE_IMPORT.test(src), `${rel} value-imports @playwright/test`).toBe(false);
      expect(REQUIRE.test(src), `${rel} requires @playwright/test`).toBe(false);
    });
  }

  it('the one @playwright/test reference in the chain is surfaces.ts, and it is type-only', () => {
    // Asserted POSITIVELY so the test cannot pass by the reference quietly
    // disappearing and the negative checks above becoming vacuous.
    const src = readFileSync(join(WEB_ROOT, 'e2e/surfaces.ts'), 'utf8');
    expect(
      src.includes("import('@playwright/test')"),
      `e2e/surfaces.ts no longer carries the inline type-only import('@playwright/test'). That is ` +
        `not a problem in itself — but this test documents WHICH reference exists, so if it moved ` +
        `or changed shape, re-check that it is still type-only and update this assertion.`
    ).toBe(true);
  });

  /*
   * THE RUNTIME PROOF IS DELIBERATELY NOT MADE HERE, and the reason is worth
   * recording because the first version of this file got it wrong.
   *
   * It originally did `await import('../../e2e/baseline-aggregate')` as an
   * end-to-end check that the chain loads outside a browser. That import
   * BROKE `npm run build`: `tsconfig.app.json` has `include: ["src"]`, so
   * reaching into `e2e/` from a `src` file drags `e2e/*.ts` into the production
   * program, and `tsc -b` fails with TS6307 on three files. Adding `e2e` to that
   * include would be worse — `e2e/tsconfig.json`'s own header says the
   * production build "must not depend on Playwright types being installed".
   *
   * The proof was not lost, only relocated to where it costs nothing:
   * `e2e/invariants/baseline-aggregate.invariant.test.ts` imports the entire
   * chain at module scope and runs under the same jsdom vitest environment. If
   * any link value-imported `@playwright/test`, or touched a browser global at
   * module scope, that file would fail to load and its 34 tests would go red.
   * The static checks above are what make the reason legible when it happens.
   */
});

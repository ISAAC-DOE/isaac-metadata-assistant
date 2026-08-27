/*
 * A RAISED QUERY BUDGET THAT CANNOT BE SPENT IS NOT A RAISED BUDGET.
 *
 * ── The defect, which is already diagnosed in this repository ───────────────
 *
 * `configure({ asyncUtilTimeout: N })` raises how long testing-library will poll a
 * single `findBy*`/`waitFor`. It says nothing about how long VITEST will let the test
 * live. `vite.config.ts` declares no `testTimeout`, so the harness deadline is the
 * framework default of 5,000 ms — and a file that raises `asyncUtilTimeout` to exactly
 * 5,000 ms has therefore raised nothing: the harness kills the test at the same instant
 * the query would have given up, and the failure reads
 *
 *     Test timed out in 5000ms.
 *
 * which names neither the query nor the DOM. The legible failure the raise existed to
 * produce is exactly the one it cannot produce. `run-workspace.test.tsx:67-112` records
 * the measurement, the CI evidence and the scaled proof in full.
 *
 * ── Why a GUARD and not just five more fixes ────────────────────────────────
 *
 * The fix reached one file and sat there. Five other files raised the same budget the
 * same way and none of them raised the deadline, and nothing anywhere could see it:
 * every one of them is green until a loaded machine crosses the line, and then the
 * failure blames the product. That is the shape this file exists to close — not the
 * five files, which are a symptom, but the fact that the pairing was expressible only
 * in prose.
 *
 * ── What it checks, and what it deliberately does not ───────────────────────
 *
 * It is a SOURCE SCAN, not a runtime probe, because the two values live in different
 * layers: `asyncUtilTimeout` is testing-library's module state and `testTimeout` is the
 * harness's, and no assertion inside a running test can observe the deadline it is
 * running under. Reading the files is the only way to compare them.
 *
 * The rule is strictly ordered, not merely "both present": `testTimeout` must be
 * GREATER than `asyncUtilTimeout`. Equal is the defect — it is what five files had.
 *
 * It does NOT require any file to raise either value. The strict 5,000 ms default is
 * correct for the ~170 files that do not mount an app, and forcing a raise everywhere
 * would be the opposite mistake. The obligation attaches only to a file that opts in.
 *
 * It does NOT check `hookTimeout`, and that is a stated gap rather than an oversight: a
 * slow `beforeEach` is a different failure with a different message, and no file here
 * currently raises a hook budget.
 */

import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

/*
 * `apps/web/src/__tests__`.
 *
 * Resolved from `process.cwd()`, which vitest sets to its config root (`apps/web`).
 * `new URL('.', import.meta.url).pathname` was tried first and is WRONG here: under the
 * jsdom environment vitest rewrites `import.meta.url` to a server-relative URL, so it
 * yields the bare `/src/__tests__` and the scan reads nothing. The "finds files to check
 * at all" case below exists so a path that resolves nowhere fails loudly instead of
 * making every other assertion vacuously true.
 */
const TEST_DIR = resolve(process.cwd(), 'src/__tests__');

/** `configure({ asyncUtilTimeout: 5_000 })`, with or without digit separators. */
const ASYNC_UTIL = /asyncUtilTimeout\s*:\s*([\d_]+)/;
/** `vi.setConfig({ testTimeout: 30_000 })`, likewise. */
const TEST_TIMEOUT = /testTimeout\s*:\s*([\d_]+)/;

const asNumber = (raw: string): number => Number(raw.replace(/_/g, ''));

interface Budgets {
  readonly file: string;
  readonly asyncUtilTimeout: number | null;
  readonly testTimeout: number | null;
}

/*
 * THIS FILE EXCLUDES ITSELF, and the reason is worth stating because it was nearly
 * missed. The negative controls below contain the literal `asyncUtilTimeout: 5000`, so
 * the scan matches its own source and reads this file as a raiser. It happens to pass —
 * the first `testTimeout: NNNNN` in the source is the `30_000` inside a suggestion
 * string — which is exactly the kind of accidental green that makes a guard look
 * healthy while measuring the wrong thing. Excluded explicitly rather than left to luck.
 */
const SELF = 'async-timeout-budget-parity.test.ts';

function readBudgets(): readonly Budgets[] {
  return readdirSync(TEST_DIR)
    .filter((name) => /\.(test|spec)\.(ts|tsx)$/.test(name))
    .filter((name) => name !== SELF)
    .sort()
    .map((name) => {
      const source = readFileSync(join(TEST_DIR, name), 'utf8');
      const async_ = ASYNC_UTIL.exec(source);
      const harness = TEST_TIMEOUT.exec(source);
      return {
        file: name,
        asyncUtilTimeout: async_ === null ? null : asNumber(async_[1]),
        testTimeout: harness === null ? null : asNumber(harness[1]),
      };
    });
}

describe('a raised query budget comes with a harness deadline above it', () => {
  it('finds files to check at all', () => {
    // A scan that silently matched nothing would satisfy every assertion below.
    const budgets = readBudgets();
    expect(budgets.length).toBeGreaterThan(100);
    expect(budgets.filter((b) => b.asyncUtilTimeout !== null).length).toBeGreaterThan(0);
  });

  it('no file raises asyncUtilTimeout without raising testTimeout above it', () => {
    const offenders = readBudgets()
      .filter((b): b is Budgets & { asyncUtilTimeout: number } => b.asyncUtilTimeout !== null)
      .filter((b) => b.testTimeout === null || b.testTimeout <= b.asyncUtilTimeout)
      .map(
        (b) =>
          `${b.file}: asyncUtilTimeout ${b.asyncUtilTimeout}, testTimeout ` +
          `${b.testTimeout === null ? 'UNSET (vitest default 5000)' : b.testTimeout}` +
          ' — the query can never spend its budget, so a slow run fails with' +
          ' "Test timed out in 5000ms" instead of naming the query and dumping the DOM.' +
          ' Add `vi.setConfig({ testTimeout: 30_000 })` under the `configure(...)` call' +
          ' and see run-workspace.test.tsx:67-112 for why.',
      );
    expect(offenders).toEqual([]);
  });

  /*
   * NEGATIVE CONTROLS. Asserting `[]` proves nothing if the predicate can never be
   * true, and this predicate reads real files, so it is worth showing on synthetic
   * input that each half of the rule bites.
   */
  const offending = (b: Budgets): boolean =>
    b.asyncUtilTimeout !== null && (b.testTimeout === null || b.testTimeout <= b.asyncUtilTimeout);

  it('flags an unset harness deadline', () => {
    expect(offending({ file: 'x', asyncUtilTimeout: 5000, testTimeout: null })).toBe(true);
  });

  it('flags an EQUAL harness deadline — the exact defect five files had', () => {
    expect(offending({ file: 'x', asyncUtilTimeout: 5000, testTimeout: 5000 })).toBe(true);
  });

  it('flags a harness deadline BELOW the query budget', () => {
    expect(offending({ file: 'x', asyncUtilTimeout: 5000, testTimeout: 4000 })).toBe(true);
  });

  it('accepts a harness deadline above the query budget', () => {
    expect(offending({ file: 'x', asyncUtilTimeout: 5000, testTimeout: 30000 })).toBe(false);
  });

  it('leaves a file that raises neither budget alone', () => {
    expect(offending({ file: 'x', asyncUtilTimeout: null, testTimeout: null })).toBe(false);
  });

  it('parses digit separators, which every raise in this repository uses', () => {
    expect(asNumber('30_000')).toBe(30000);
    expect(asNumber('5_000')).toBe(5000);
    expect(asNumber('5000')).toBe(5000);
  });

  /*
   * The six files that opt in today, named so a reviewer can see the guard is
   * describing something real. It is a floor, not an exact set: a seventh file may
   * legitimately raise the budget, and that must not fail this test.
   */
  it('the six files that raise the query budget all carry a deadline above it', () => {
    const raisers = readBudgets().filter((b) => b.asyncUtilTimeout !== null);
    expect(raisers.map((b) => b.file)).toEqual(
      expect.arrayContaining([
        'record-view-input-survival.test.tsx',
        'run-browser.test.tsx',
        'run-compare.test.tsx',
        'run-relevance.test.tsx',
        'run-removal.test.tsx',
        'run-workspace.test.tsx',
      ]),
    );
    for (const raiser of raisers) {
      expect(raiser.testTimeout).not.toBeNull();
      expect(raiser.testTimeout as number).toBeGreaterThan(raiser.asyncUtilTimeout as number);
    }
  });
});

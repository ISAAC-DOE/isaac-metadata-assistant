/**
 * BASELINE AGGREGATE CONSISTENCY — the fast half of the accessibility baseline.
 *
 * This is a `vitest` file, not a Playwright spec, and the distinction is the
 * whole point of it. `specs/a11y-axe.spec.ts` needs a browser, a seeded
 * backend, a built frontend and five viewport projects; it costs ~30 minutes in
 * the `browser-a11y` CI job. The checks BELOW need none of that — they are
 * arithmetic and string shape over two committed data files — so they run in
 * the `frontend` job in milliseconds, on every pull request and on every push
 * to `main`.
 *
 * Everything here was previously enforced ONLY inside that 30-minute job, which
 * meant an inconsistent baseline was merged first and discovered afterwards.
 * See `../baseline-aggregate.ts` for the exact merge mechanism that made a
 * hand-maintained total go stale without a git conflict.
 *
 * Naming: `*.invariant.test.ts`, deliberately NOT `*.spec.ts`. Both Playwright
 * configs discover tests with `testMatch: /.*\.spec\.ts$/`, so this file is
 * invisible to them and can never be collected into a browser run.
 */

import { describe, expect, it } from 'vitest';

import {
  A11Y_BASELINE,
  A11Y_BASELINE_TOTAL_NODES,
  BASELINE_PLATFORMS,
  PROJECT_IDS,
  SCAN_PROJECT_IDS,
  type BaselineEntry,
  type PlatformCount,
} from '../a11y-baseline';
import {
  LAYOUT_BASELINE,
  LAYOUT_BASELINE_TOTAL_INSTANCES,
  LAYOUT_SWEEP_WIDTH_IDS,
  type LayoutFinding,
} from '../layout-baseline';
import {
  a11yBaselineKeys,
  auditAggregate,
  auditBaselineAggregates,
  layoutBaselineKeys,
  splitBaselineKey,
  sumA11yNodes,
  sumLayoutInstances,
} from '../baseline-aggregate';
import { SURFACES } from '../surfaces';

describe('declared baseline totals equal the entries they total', () => {
  it('reports no mismatch for the committed baselines, on either platform', () => {
    const mismatches = auditBaselineAggregates(A11Y_BASELINE_TOTAL_NODES, LAYOUT_BASELINE_TOTAL_INSTANCES);
    expect(mismatches.map((m) => m.message).join('\n\n')).toBe('');
    expect(mismatches).toEqual([]);
  });

  // Stated separately from the combined audit above so a failure names WHICH
  // baseline drifted without the reader parsing a joined message.
  it('A11Y_BASELINE_TOTAL_NODES equals the sum of every recorded node count', () => {
    const computed = sumA11yNodes(A11Y_BASELINE);
    for (const platform of BASELINE_PLATFORMS) {
      expect(
        computed[platform],
        `A11Y_BASELINE_TOTAL_NODES.${platform} = ${A11Y_BASELINE_TOTAL_NODES[platform]}, entries sum to ${computed[platform]}`
      ).toBe(A11Y_BASELINE_TOTAL_NODES[platform]);
    }
  });

  it('LAYOUT_BASELINE_TOTAL_INSTANCES equals the sum of every recorded offender', () => {
    const computed = sumLayoutInstances(LAYOUT_BASELINE);
    for (const platform of BASELINE_PLATFORMS) {
      expect(computed[platform]).toBe(LAYOUT_BASELINE_TOTAL_INSTANCES[platform]);
    }
  });

  /*
   * The layout total is DERIVED in `layout-baseline.ts` (`totalInstancesOn`),
   * so the assertion above compares a derivation against an independent
   * re-derivation. That is worth keeping rather than dismissing as circular:
   * the two walk the `instances` shape by different code, and this is what
   * would catch the derivation being changed to skip per-platform objects —
   * exactly the bug `platformInstances` exists to prevent.
   */
  it('the two totals are not accidentally equal, so neither test can pass by coincidence', () => {
    expect(A11Y_BASELINE_TOTAL_NODES.darwin).not.toBe(LAYOUT_BASELINE_TOTAL_INSTANCES.darwin);
  });
});

/*
 * ── NEGATIVE CONTROLS ───────────────────────────────────────────────────────
 *
 * A consistency check that has only ever been run against a consistent input
 * has not been shown to detect anything. Each control below feeds the SAME
 * function the suite uses a deliberately broken input and asserts the exact
 * defect is reported — including the specific two-branch merge that motivated
 * this file.
 */
describe('the aggregate checker detects the failures it claims to', () => {
  // `PlatformCount`, not `number`: two of the controls below feed a genuine
  // `{ darwin, linux }` pair, which is the shape most likely to be summed by
  // array position or by the wrong column.
  const entry = (rule: string, counts: Record<string, PlatformCount>): BaselineEntry => ({
    rule,
    impact: 'serious',
    note: 'Synthetic entry used only by the negative controls in this file; it describes no real defect.',
    targetPattern: '^synthetic$',
    counts,
  });

  it('THE MERGE COLLISION: two branches, two disjoint additions, one increment', () => {
    // `main` before either branch: one entry, three nodes, total 3.
    const base = [entry('color-contrast', { 'alpha@desktop-1280x800': 3 })];
    const baseTotal = sumA11yNodes(base);
    expect(baseTotal.darwin).toBe(3);

    // Branch A adds one node on a NEW pair and raises the total 3 -> 4.
    // Branch B adds one node on a DIFFERENT new pair and also writes 4 —
    // the same literal, for an unrelated reason.
    const declaredByBothBranches = { darwin: 4, linux: 4 };

    // git merges the identical one-line change without a conflict, and the two
    // entry additions touch different keys so they merge cleanly too. The
    // merged file holds BOTH additions and ONE increment.
    const merged = [
      entry('color-contrast', {
        'alpha@desktop-1280x800': 3,
        'beta@desktop-1280x800': 1, // from branch A
        'gamma@desktop-1280x800': 1, // from branch B
      }),
    ];

    const mismatches = auditAggregate('A11Y_BASELINE_TOTAL_NODES', declaredByBothBranches, sumA11yNodes(merged));

    // Both platforms are wrong by exactly one — the increment that was lost.
    expect(mismatches).toHaveLength(BASELINE_PLATFORMS.length);
    for (const m of mismatches) {
      expect(m.declared).toBe(4);
      expect(m.computed).toBe(5);
      expect(m.drift).toBe(1);
      // The message must name the merge, because a reader who has just seen a
      // clean merge will not otherwise suspect one.
      expect(m.message).toContain('MERGE');
      expect(m.message).toContain('Raise the total to 5');
    }
  });

  it('detects a total left BEHIND its entries (debt added, number not updated)', () => {
    const mismatches = auditAggregate(
      'A11Y_BASELINE_TOTAL_NODES',
      { darwin: 10, linux: 10 },
      sumA11yNodes([entry('color-contrast', { 'alpha@desktop-1280x800': 12 })])
    );
    expect(mismatches.map((m) => m.drift)).toEqual([2, 2]);
  });

  it('detects a total left AHEAD of its entries (defect fixed, number not lowered)', () => {
    const mismatches = auditAggregate(
      'A11Y_BASELINE_TOTAL_NODES',
      { darwin: 10, linux: 10 },
      sumA11yNodes([entry('color-contrast', { 'alpha@desktop-1280x800': 7 })])
    );
    expect(mismatches.map((m) => m.drift)).toEqual([-3, -3]);
    for (const m of mismatches) expect(m.message).toContain('Set the total to 7');
  });

  it('detects a drift on ONE platform only, and names that platform alone', () => {
    const mismatches = auditAggregate(
      'A11Y_BASELINE_TOTAL_NODES',
      { darwin: 5, linux: 5 },
      sumA11yNodes([entry('color-contrast', { 'alpha@desktop-1280x800': { darwin: 5, linux: 6 } })])
    );
    expect(mismatches).toHaveLength(1);
    expect(mismatches[0].platform).toBe('linux');
    expect(mismatches[0].drift).toBe(1);
  });

  it('counts per-platform pairs on the right side of the pair, not by array position', () => {
    const totals = sumA11yNodes([
      entry('color-contrast', {
        'alpha@desktop-1280x800': { darwin: 2, linux: 9 },
        'beta@desktop-1280x800': 1,
      }),
    ]);
    expect(totals).toEqual({ darwin: 3, linux: 10 });
  });

  it('sums layout offenders by LIST LENGTH per platform, including per-platform lists', () => {
    const findings: LayoutFinding[] = [
      {
        id: 'SYNTHETIC-01',
        kind: 'clipped',
        selector: 'synthetic',
        note: 'Synthetic finding used only by the negative controls in this file.',
        instances: {
          'alpha@desktop-1280x800': ['a', 'b'],
          'beta@desktop-1280x800': { darwin: ['a'], linux: ['a', 'b', 'c'] },
        },
      },
    ];
    expect(sumLayoutInstances(findings)).toEqual({ darwin: 3, linux: 5 });
  });
});

/*
 * ── SHAPE CHECKS THAT NEEDED NO BROWSER AND WERE WAITING FOR ONE ────────────
 *
 * These duplicate nothing: `specs/a11y-axe.spec.ts` validates keys against the
 * scan grid, but only inside the browser job. A typo'd surface id is a data
 * error in a committed file and there is no reason its rejection should cost
 * half an hour. The browser test keeps its own copies — it must, because it is
 * the thing that runs the scan — and these run first and fail sooner.
 */
describe('every baseline key names a real surface and a real scan project', () => {
  const surfaceIds = new Set(SURFACES.map((s) => s.id));
  // The two grids, kept apart on purpose — see `a11yBaselineKeys` for why a
  // union would be a check that cannot fail.
  const a11yProjects = new Set<string>(SCAN_PROJECT_IDS);
  const layoutProjects = new Set<string>([...PROJECT_IDS, ...LAYOUT_SWEEP_WIDTH_IDS]);

  const allKeys = () => [...a11yBaselineKeys(), ...layoutBaselineKeys()];

  const badSurfaces = (keys: readonly string[]) =>
    keys
      .map((key) => ({ key, parts: splitBaselineKey(key) }))
      .filter(({ parts }) => parts && !surfaceIds.has(parts.surfaceId))
      .map(({ key }) => key);

  const badProjects = (keys: readonly string[], legal: ReadonlySet<string>) =>
    keys
      .map((key) => ({ key, parts: splitBaselineKey(key) }))
      .filter(({ parts }) => parts && !legal.has(parts.projectId))
      .map(({ key }) => key);

  it('parses every key into a surface half and a project half', () => {
    for (const key of allKeys()) {
      expect(splitBaselineKey(key), `"${key}" is not a valid surfaceId@projectId key`).not.toBeNull();
    }
  });

  it('names only surfaces that e2e/surfaces.ts actually scans', () => {
    expect(
      badSurfaces(allKeys()),
      `these baseline keys name a surface id that does not exist in e2e/surfaces.ts, so they can ` +
        `never be reached by a scan and silently tolerate nothing while looking like coverage`
    ).toEqual([]);
  });

  it('keys the a11y baseline only against projects the axe sweep runs', () => {
    expect(
      badProjects(a11yBaselineKeys(), a11yProjects),
      `SCAN_PROJECT_IDS is the axe grid: the five Playwright projects plus width-390 and ` +
        `width-320. A key naming any other width belongs to the layout sweep, not here.`
    ).toEqual([]);
  });

  it('keys the layout baseline only against projects or widths the layout sweep runs', () => {
    expect(
      badProjects(layoutBaselineKeys(), layoutProjects),
      `The layout grid is the five Playwright projects (layout-responsive.spec.ts) plus ` +
        `LAYOUT_SWEEP_WIDTH_IDS (layout-widths.spec.ts).`
    ).toEqual([]);
  });

  it('the two grids genuinely differ, so neither check can pass by sharing the other s list', () => {
    // Five width ids are legal for LAYOUT and for nothing else. Three of them
    // (1280/1024/768) are widths the axe sweep also covers, but under its
    // PROJECT names (`desktop-1280x800`, …) — which is precisely the collision
    // the `width-` namespacing exists to prevent, so they are correctly absent
    // from the axe grid. 375 and 640 are swept for layout alone.
    //
    // If this list ever empties, the two checks above have collapsed into one
    // and stopped distinguishing the mistake they exist to catch.
    expect([...layoutProjects].filter((p) => !a11yProjects.has(p)).sort()).toEqual([
      'width-1024',
      'width-1280',
      'width-375',
      'width-640',
      'width-768',
    ]);
  });

  it('keeps the scan grid the two extra narrow widths wide', () => {
    // Mirrors the tail of the browser well-formedness test. If a sixth
    // viewport project is added, every recorded count needs a reading for it
    // and this fails immediately rather than after a full sweep.
    expect(SCAN_PROJECT_IDS.length).toBe(PROJECT_IDS.length + 2);
  });
});

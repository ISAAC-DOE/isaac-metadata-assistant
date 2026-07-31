/**
 * Automated accessibility scan — axe-core, every surface, every viewport.
 * @responsive
 *
 * Covers, via axe: accessible names, ARIA attribute/role validity, landmark
 * uniqueness, heading-one presence, form labels, keyboard access to scrollable
 * regions, and AUTOMATED COLOUR CONTRAST.
 *
 * Failure policy, in one sentence: a scan must reproduce the EXACT per-surface,
 * per-viewport node counts recorded in `../a11y-baseline.ts`, with the same
 * target elements and (for contrast) the same foreground colours. One extra
 * failing node anywhere fails the build; one fewer fails it too, so the
 * recorded numbers stay true. No rule is ever disabled and no whole rule is
 * ever exempted — see `../a11y-baseline.ts` for why the first version of this
 * file effectively did exempt one, and what replaced it.
 */

import {
  A11Y_BASELINE,
  A11Y_BASELINE_TOTAL_NODES,
  PROJECT_IDS,
  allScanPairs,
  applicableEntries,
  baselineKey,
  baselineVerdict,
  expectedNodeCount,
  isBaselined,
} from '../a11y-baseline';
import { auditScan, scan } from '../helpers/axe';
import { expect, test } from '../fixtures';
import { SURFACES } from '../surfaces';

for (const surface of SURFACES) {
  test(`@responsive a11y scan: ${surface.name}`, async ({ page, app }, testInfo) => {
    await app.open(surface);

    const project = testInfo.project.name;
    // If a sixth viewport project is ever added, its scans have no recorded
    // counts and everything would read as "new". Fail loudly and immediately
    // rather than burying that in 18 confusing violation reports.
    expect(
      PROJECT_IDS as readonly string[],
      `project "${project}" is not listed in PROJECT_IDS in e2e/a11y-baseline.ts; ` +
        `add it and record its measured counts before running the sweep.`
    ).toContain(project);

    const results = await scan(page);
    const failures = auditScan(results, surface.id, project);

    const totalNodes = results.violations.reduce((n, v) => n + v.nodes.length, 0);
    const expectedTotal = applicableEntries(surface.id, project).reduce(
      (n, e) => n + (e.counts[baselineKey(surface.id, project)] ?? 0),
      0
    );
    testInfo.annotations.push({
      type: 'a11y',
      description:
        `${surface.id} @ ${project}: ${results.violations.length} rule(s) firing, ` +
        `${totalNodes} failing node(s) — baseline expects ${expectedTotal}; ` +
        `${results.passes.length} rule(s) passed.`,
    });

    expect(
      failures.map((f) => `${f.kind}:${f.rule}`),
      failures.length
        ? `Accessibility baseline mismatch on "${surface.name}" (${surface.path}) at ${project}.\n\n` +
            failures.map((f) => f.message).join('\n\n')
        : undefined
    ).toEqual([]);
  });
}

/**
 * The baseline file itself, checked for the failure modes that made the first
 * version dishonest.
 *
 * This test used to ASSERT that `button-name` and `color-contrast` were scoped
 * to every surface — it ratified the suppression it was supposed to catch. It
 * is now inverted: it proves that no entry can bless an instance that was never
 * measured, and that every recorded instance is one node away from red.
 */
test('@responsive a11y baseline file is well-formed and cannot silently exempt a rule', async () => {
  const surfaceIds = new Set(SURFACES.map((s) => s.id));
  const projectIds = new Set<string>(PROJECT_IDS);
  const seenRules = new Set<string>();
  let total = 0;

  for (const entry of A11Y_BASELINE) {
    expect(entry.rule, 'every baseline entry names an axe rule').toMatch(/^[a-z0-9-]+$/);
    expect(seenRules.has(entry.rule), `duplicate baseline entry for "${entry.rule}"`).toBe(false);
    seenRules.add(entry.rule);
    expect(entry.note.length, `baseline entry "${entry.rule}" must carry a real explanation`).toBeGreaterThan(60);

    // An entry with no counts tolerates nothing, which means it is dead weight
    // pretending to document something.
    const keys = Object.keys(entry.counts);
    expect(keys.length, `baseline entry "${entry.rule}" records no (surface, project) pair`).toBeGreaterThan(0);

    // Identity guard: a count alone cannot tell "the same 31 buttons" from
    // "31 different elements", so every entry must pin one or the other.
    expect(
      Boolean(entry.targetPattern) || Boolean(entry.foregrounds?.length),
      `baseline entry "${entry.rule}" must pin WHICH nodes fail — a targetPattern or, for ` +
        `color-contrast, the exact set of failing foreground colours. A bare count would let a ` +
        `different element fail the same rule the same number of times and stay green.`
    ).toBe(true);
    if (entry.targetPattern) expect(() => new RegExp(entry.targetPattern!)).not.toThrow();
    for (const c of entry.foregrounds ?? []) expect(c, 'foregrounds are lower-case hex').toMatch(/^#[0-9a-f]{6}$/);

    for (const key of keys) {
      const [surfaceId, projectId] = key.split('@');
      expect(surfaceIds.has(surfaceId), `"${entry.rule}" baselines unknown surface "${surfaceId}"`).toBe(true);
      expect(projectIds.has(projectId), `"${entry.rule}" baselines unknown project "${projectId}"`).toBe(true);

      const n = entry.counts[key];
      expect(Number.isInteger(n) && n >= 1, `"${entry.rule}" @ ${key}: count must be a positive integer`).toBe(true);
      total += n;

      // THE INVERSION. For every recorded instance, the policy must be exactly
      // one node wide on each side.
      expect(baselineVerdict(entry.rule, surfaceId, projectId, n), `${entry.rule} @ ${key}: ${n} must be ok`).toBe('ok');
      expect(
        baselineVerdict(entry.rule, surfaceId, projectId, n + 1),
        `${entry.rule} @ ${key}: ${n + 1} nodes MUST fail — that is the whole point of the baseline`
      ).toBe('grew');
      expect(
        baselineVerdict(entry.rule, surfaceId, projectId, n - 1),
        `${entry.rule} @ ${key}: ${n - 1} nodes must read as "improved", so a partially-fixed ` +
          `defect updates this file instead of rotting`
      ).toBe('improved');
    }

    // …and no entry may tolerate anything on a pair it did not record.
    for (const { surfaceId, projectId } of allScanPairs()) {
      if (entry.counts[baselineKey(surfaceId, projectId)] !== undefined) continue;
      expect(
        baselineVerdict(entry.rule, surfaceId, projectId, 1),
        `${entry.rule} is not recorded at ${surfaceId}@${projectId}, so one node there MUST read as new`
      ).toBe('new');
      expect(isBaselined(entry.rule, surfaceId, projectId)).toBe(false);
      expect(expectedNodeCount(entry.rule, surfaceId, projectId)).toBe(0);
    }
  }

  // The single number that says how much automated-a11y debt this app carries.
  // It can only move by editing this file, which is the point.
  expect(
    total,
    `A11Y_BASELINE_TOTAL_NODES is stale: the entries now sum to ${total}. Update the constant in ` +
      `e2e/a11y-baseline.ts so the recorded debt stays visible in one place.`
  ).toBe(A11Y_BASELINE_TOTAL_NODES);

  // Sanity: the grid the counts are keyed against is the grid the suite scans.
  expect(allScanPairs().length).toBe(SURFACES.length * PROJECT_IDS.length);
});

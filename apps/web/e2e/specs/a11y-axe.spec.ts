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
 *
 * Ten of the 149 recorded triples hold a separate exact number for macOS and
 * for Linux, because there is no webfont and the system face changes where text
 * wraps. The scan enforces the CURRENT platform's number, exactly; the
 * well-formedness test below checks BOTH columns. **CI (Linux) is the
 * authority** — a green macOS run does not predict a green CI run.
 */

import {
  A11Y_BASELINE,
  A11Y_BASELINE_TOTAL_NODES,
  BASELINE_PLATFORMS,
  PROJECT_IDS,
  allScanPairs,
  applicableEntries,
  baselineKey,
  baselineVerdict,
  currentPlatform,
  expectedNodeCount,
  isBaselined,
  platformCount,
  type BaselinePlatform,
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

    // Which column of the baseline is in force. Throws, loudly and with an
    // explanation, on a platform nobody has measured — see `resolvePlatform`.
    const platform = currentPlatform();

    const results = await scan(page);
    const failures = auditScan(results, surface.id, project, platform);

    const totalNodes = results.violations.reduce((n, v) => n + v.nodes.length, 0);
    const expectedTotal = applicableEntries(surface.id, project, platform).reduce(
      (n, e) => n + platformCount(e.counts[baselineKey(surface.id, project)], platform),
      0
    );
    testInfo.annotations.push({
      type: 'a11y',
      description:
        `${surface.id} @ ${project} on ${platform}: ${results.violations.length} rule(s) firing, ` +
        `${totalNodes} failing node(s) — baseline expects ${expectedTotal}; ` +
        `${results.passes.length} rule(s) passed.`,
    });

    expect(
      failures.map((f) => `${f.kind}:${f.rule}`),
      failures.length
        ? `Accessibility baseline mismatch on "${surface.name}" (${surface.path}) at ${project} ` +
            `against the "${platform}" column of e2e/a11y-baseline.ts.\n` +
            (platform === 'darwin'
              ? `NOTE: CI runs on linux and is the authority. Fixing the darwin column does not ` +
                `make CI green, and a green macOS run does not predict one.\n`
              : '') +
            `\n` +
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
  // Per platform, so the column this machine will never execute is checked as
  // hard as the one it will. Without this a typo'd `linux:` number — or a
  // per-platform object missing a platform entirely — would sit undetected
  // until CI, which is precisely the failure this change exists to prevent.
  const total: Record<BaselinePlatform, number> = { darwin: 0, linux: 0 };

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

      const raw = entry.counts[key];
      // A per-platform count must carry EVERY platform. A partial object would
      // silently read `undefined` on the missing one and, through
      // `platformCount`, become a `NaN` comparison that never says "grew".
      if (typeof raw !== 'number') {
        for (const p of BASELINE_PLATFORMS) {
          expect(
            Object.prototype.hasOwnProperty.call(raw, p),
            `"${entry.rule}" @ ${key} is a per-platform count but has no "${p}" number. Every ` +
              `platform in BASELINE_PLATFORMS must be measured, or the count must be a bare number ` +
              `meaning "identical on all of them".`
          ).toBe(true);
        }
        expect(
          (raw as Record<string, number>).darwin !== (raw as Record<string, number>).linux,
          `"${entry.rule}" @ ${key} is written per-platform but both numbers are the same. Write a ` +
            `bare number instead — a per-platform pair should mark a real measured difference.`
        ).toBe(true);
      }

      for (const platform of BASELINE_PLATFORMS) {
        const n = platformCount(raw, platform);
        expect(
          Number.isInteger(n) && n >= 1,
          `"${entry.rule}" @ ${key} [${platform}]: count must be a positive integer, got ${n}`
        ).toBe(true);
        total[platform] += n;

        // THE INVERSION. For every recorded instance, on every platform, the
        // policy must be exactly one node wide on each side. No ranges, no
        // tolerance: the ±1 that font metrics produce is recorded as a second
        // exact number, never as slack around the first.
        expect(
          baselineVerdict(entry.rule, surfaceId, projectId, n, platform),
          `${entry.rule} @ ${key} [${platform}]: ${n} must be ok`
        ).toBe('ok');
        expect(
          baselineVerdict(entry.rule, surfaceId, projectId, n + 1, platform),
          `${entry.rule} @ ${key} [${platform}]: ${n + 1} nodes MUST fail — that is the whole point of the baseline`
        ).toBe('grew');
        expect(
          baselineVerdict(entry.rule, surfaceId, projectId, n - 1, platform),
          `${entry.rule} @ ${key} [${platform}]: ${n - 1} nodes must read as "improved", so a ` +
            `partially-fixed defect updates this file instead of rotting`
        ).toBe('improved');
      }
    }

    // …and no entry may tolerate anything on a pair it did not record, on
    // either platform.
    for (const { surfaceId, projectId } of allScanPairs()) {
      if (entry.counts[baselineKey(surfaceId, projectId)] !== undefined) continue;
      for (const platform of BASELINE_PLATFORMS) {
        expect(
          baselineVerdict(entry.rule, surfaceId, projectId, 1, platform),
          `${entry.rule} is not recorded at ${surfaceId}@${projectId}, so one node there MUST read ` +
            `as new on ${platform}`
        ).toBe('new');
        expect(isBaselined(entry.rule, surfaceId, projectId, platform)).toBe(false);
        expect(expectedNodeCount(entry.rule, surfaceId, projectId, platform)).toBe(0);
      }
    }
  }

  // The two numbers that say how much automated-a11y debt this app carries.
  // They can only move by editing this file, which is the point.
  for (const platform of BASELINE_PLATFORMS) {
    expect(
      total[platform],
      `A11Y_BASELINE_TOTAL_NODES.${platform} is stale: the entries now sum to ${total[platform]}. ` +
        `Update the constant in e2e/a11y-baseline.ts so the recorded debt stays visible in one place.`
    ).toBe(A11Y_BASELINE_TOTAL_NODES[platform]);
  }

  // Sanity: the grid the counts are keyed against is the grid the suite scans.
  expect(allScanPairs().length).toBe(SURFACES.length * PROJECT_IDS.length);
});

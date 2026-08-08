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
 * Ten of the 103 recorded triples hold a separate exact number for macOS and
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

/**
 * How many `details.stats-disclosure` each surface mounts.
 *
 * DECLARED PER SURFACE, not counted and accepted, so that a disclosure appearing
 * or disappearing names itself here instead of moving a scan count that nobody
 * can then explain. Anything absent from this map must mount none.
 *
 * The four are the Statistics General tab's supporting-copy disclosures — How
 * Verification Works, How to Interpret Results, Mutation Methodology, Known
 * Limitations. `statistics-mine` is the My Stats tab, which renders none of them
 * and no `details.stats-technical` either.
 */
const PROSE_DISCLOSURES: Readonly<Record<string, number>> = Object.freeze({
  statistics: 4,
  'statistics-example': 4,
});

/**
 * Open EVERY disclosure on a surface that NO `SURFACES` entry can reach, so
 * their contents are scanned rather than silently exempt.
 *
 * ── Why this exists ─────────────────────────────────────────────────────────
 *
 * A `<details>` has no URL state, so a surface's `path` cannot open one; and axe
 * does not scan a closed disclosure. When the Statistics slice moved the two
 * `/api/about` cards into a collapsed `Technical Details` region, their two
 * `.stat-card-note` `color-contrast` failures stopped being counted — and the
 * baseline recorded the drop as a coverage gap, with a note claiming the
 * unmeasured instances were only those two and that "not one is a chart".
 *
 * Both halves of that claim were false. Measured by an independent reviewer and
 * reproduced here, opening the region on `statistics-example` raised the failing
 * node count from 9 to 12: the third node was a CHART AXIS TICK, at
 * `--text-tertiary` #78838f / 10.5px — a new WCAG 1.4.3 failure shipping
 * invisibly behind a note asserting it did not exist. (The token has since been
 * darkened to `--text-muted`, which is why the tick no longer appears in the
 * counts; the coverage this restores is what made it visible.)
 *
 * ── AND FOUR MORE, ADDED BY THE VISUAL-FIRST REORGANISATION ─────────────────
 *
 * That slice moved Record Verification to the top of the Statistics General tab
 * and moved its supporting PROSE into four new closed disclosures beside
 * Technical Details. Every one of them is unreachable by URL for exactly the
 * reason above, so they are opened here too.
 *
 * THE RULE THIS ENFORCES IS THE ONE THE HISTORY ABOVE ESTABLISHED: a baseline
 * number that drops because content is now hidden is a COVERAGE LOSS, not an
 * accessibility win. Four disclosures' worth of copy going unscanned while the
 * counts stayed flat would be that same defect at four times the size — and it
 * would look like nothing had happened, which is what makes it worth a helper
 * rather than a comment.
 *
 * ── What it deliberately does NOT open ──────────────────────────────────────
 *
 * Each chart's own data-table `<details class="stats-chart-table-wrap">` stays
 * closed. Those are a per-figure text equivalent whose default state is closed
 * for every reader, and opening four tables at five viewports would move counts
 * for a reason unrelated to this gap. They remain unscanned, which is a real and
 * still-open limitation and is stated here rather than left to be discovered.
 */
async function openUnreachableDisclosures(
  page: import('@playwright/test').Page,
  surfaceId: string
): Promise<void> {
  const technical = page.locator('details.stats-technical');
  const mounted = await technical.count();
  /*
   * ONE, ASSERTED. `technical.locator('> summary').click()` resolves through a
   * strict-mode locator, so a second `details.stats-technical` on any surface
   * would throw "resolved to 2 elements" from inside a helper whose job is
   * coverage — an opaque failure in every a11y scan at every viewport, naming
   * neither the surface nor the cause. Asserted here so the second mount names
   * itself.
   *
   * IT IS STILL ONE, and that is why the four prose disclosures carry their own
   * class (`details.stats-disclosure`, see `StatsCharts.tsx` →
   * `TechnicalDetailsProps.variant`): giving them this class would have turned
   * this locator — and the `toHaveCount(1)` in `statistics-states.spec.ts`, and
   * `openTechnicalDetails` in `charts.spec.ts` — into that same opaque failure.
   */
  if (mounted > 0) {
    expect(mounted, 'a surface must mount exactly one details.stats-technical').toBe(1);
    await technical.locator('> summary').click();
    await expect(technical).toHaveAttribute('open', '');
  }

  /*
   * The prose disclosures, opened one at a time by index — `.nth(i)` rather than
   * a bare locator, because there are legitimately several and a strict-mode
   * click would throw on the second.
   *
   * The count is DECLARED (`PROSE_DISCLOSURES`) and asserted, not measured and
   * accepted: an unopened fifth disclosure would silently exempt its contents
   * from every scan at every viewport, which is precisely the coverage gap this
   * helper exists to close.
   */
  const prose = page.locator('details.stats-disclosure');
  const expectedProse = PROSE_DISCLOSURES[surfaceId] ?? 0;
  const proseCount = await prose.count();
  expect(
    proseCount,
    `surface "${surfaceId}" mounts ${proseCount} details.stats-disclosure; ` +
      `PROSE_DISCLOSURES in this file declares ${expectedProse}. A disclosure that is not ` +
      'opened here is not scanned by axe at any viewport — update the map in the same ' +
      'change that adds or removes one.'
  ).toBe(expectedProse);
  for (let i = 0; i < proseCount; i++) {
    const one = prose.nth(i);
    await one.locator('> summary').click();
    await expect(one).toHaveAttribute('open', '');
  }
}

for (const surface of SURFACES) {
  test(`@responsive a11y scan: ${surface.name}`, async ({ page, app }, testInfo) => {
    await app.open(surface);
    await openUnreachableDisclosures(page, surface.id);

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

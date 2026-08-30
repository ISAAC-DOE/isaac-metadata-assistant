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
 * ~~Ten of the 103 recorded triples hold a separate exact number for macOS and
 * for Linux~~ — ~~**RE-COUNTED 2026-08-29: EIGHT of 161.**~~ **RE-COUNTED AGAIN
 * 2026-08-30: FIVE of 161.** Eight was this branch's figure and the MERGE moved it:
 * `c7b9db6` took the linux halves CI measured at `6958459` and five splits collapsed
 * to scalars. Both earlier figures were right when written and neither is now.
 * Neither of the first two figures was right
 * when it was written and the sentence has been stale for weeks in both halves, so it
 * is struck rather than silently renumbered. Derive it rather than trusting this
 * comment: `e2e/a11y-baseline.ts` is the only source, and the count moves whenever a
 * cell is added, deleted or transcribed. What the sentence was FOR is unchanged and is
 * the part to keep: some cells hold a separate exact number per platform, because
 * there is no webfont and the system face changes where text wraps — and, since
 * 2026-08-29, because one column can also simply be older than the other. The scan
 * enforces the CURRENT platform's number, exactly; the well-formedness test below
 * checks BOTH columns. **CI (Linux) is the authority** — a green macOS run does not
 * predict a green CI run.
 */

import {
  A11Y_BASELINE,
  A11Y_BASELINE_TOTAL_NODES,
  PROJECT_IDS,
  applicableEntries,
  baselineKey,
  currentPlatform,
  platformCount,
} from '../a11y-baseline';
import { auditA11yWellFormedness, auditAggregate, sumA11yNodes } from '../baseline-aggregate';
import { auditScan, scan } from '../helpers/axe';
import { openUnreachableDisclosures } from '../helpers/disclosures';
import { expect, test } from '../fixtures';
import { SURFACES } from '../surfaces';

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
  // THE CHECKS THEMSELVES LIVE IN `../baseline-aggregate`, AND THAT IS THE POINT.
  //
  // Every assertion this test used to make inline is pure: it reads two
  // committed data files and does arithmetic and string matching. None of it
  // needs a browser, a backend or a viewport — yet all of it was reachable only
  // by paying for the ~30-minute `browser-a11y` job, so a typo'd surface id or a
  // per-platform count missing a platform cost half an hour to reject.
  //
  // They now run in the fast `frontend` job too, via
  // `../invariants/baseline-aggregate.invariant.test.ts`, against this SAME
  // function. One implementation, two runners — rather than two copies that can
  // drift, which is the failure `sumA11yNodes` was extracted to prevent and
  // which an independent review pointed out this file had only half-fixed.
  //
  // It is kept here as well, deliberately. This is the suite that knows the
  // baseline is about to be enforced against real axe output, and a data file
  // that is malformed should fail before 90 scans are run against it.
  expect(
    auditA11yWellFormedness(),
    'e2e/a11y-baseline.ts is malformed — see `auditA11yWellFormedness` in e2e/baseline-aggregate.ts'
  ).toEqual([]);

  // The two numbers that say how much automated-a11y debt this app carries.
  // They can only move by editing `e2e/a11y-baseline.ts`, which is the point:
  // per-cell ratchets catch growth on a MEASURED cell, and only this total
  // catches growth by ADDITION. See that file's note on the two-branch merge
  // that used to make it go stale without a git conflict.
  expect(
    auditAggregate(
      'A11Y_BASELINE_TOTAL_NODES',
      A11Y_BASELINE_TOTAL_NODES,
      sumA11yNodes(A11Y_BASELINE)
    ).map((m) => m.message),
    'the declared total must equal the sum of the entries it totals'
  ).toEqual([]);
});

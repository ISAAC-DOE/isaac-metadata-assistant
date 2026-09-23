/**
 * M-11 · THE IMPORT SESSION HAS NEVER BEEN ACCESSIBILITY-SCANNED.
 *
 * `e2e/surfaces.ts`'s `imports` entry says so in its own words: it sweeps "the
 * first-run state — the empty list, the workflow strip, the durability sentence
 * and the Start control", and "WHAT THIS SURFACE DELIBERATELY DOES NOT COVER: an
 * OPEN session. Reaching one needs a POST … and this suite is read-only by
 * construction". That was an honest boundary, not an oversight — and it left the
 * larger half of the screen unmeasured by axe. The component tests
 * (`src/__tests__/historical-import.test.tsx`) cover behaviour; jsdom computes no
 * colours, resolves no stacking and runs no accessibility engine.
 *
 * SO THE SCAN LIVES HERE, in the suite that is allowed to POST — the same shape
 * `run-overrides.spec.ts` already uses for the override form: scan the subtree the
 * read-only sweep cannot reach, and assert CLEAN rather than record a baseline.
 *
 * WHY CLEAN AND NOT A BASELINE ENTRY. A baseline exists to hold a pre-existing
 * defect still and stop it growing. There is no recorded defect here to hold — the
 * state has never been measured — so the honest first measurement is "is it
 * clean?", and if it is not, the answer is to fix it or to record it deliberately
 * with a reason. Adding `imports-session` to `SURFACES` instead would enrol it in
 * THIRTEEN sweeps across seven viewport projects, all of which need a POST the
 * read-only config forbids.
 *
 * WHAT IS SCANNED: `main`, in the session view, at EVERY step an import passes
 * through — the empty Sources step, Sources with a real entry in its table, after
 * the sources have been read, and after candidates have been reconstructed. Each
 * is driven through the UI against a real backend, so each is the state a
 * scientist actually meets.
 *
 * Scanning only the first step would have been the easy version and is explicitly
 * not what this does: the populated table, the per-entry "Read?" disclosure and
 * the candidate list are the parts of this screen with the most structure, and
 * they are exactly the parts jsdom cannot judge.
 *
 * SINCE 2026-09-22 (owner QA H1) THE SESSION IS SIX STAGE TABS WITH ONE PANEL SHOWN,
 * and a candidate is a collapsed row. axe skips a `hidden` subtree and a closed
 * disclosure's body, so this spec VISITS every stage and OPENS every disclosure in
 * it before scanning — otherwise the cleaner-looking stage flow would have quietly
 * removed most of the screen from every scan.
 */
import type { Page } from '@playwright/test';
import { formatViolation, scan } from '../helpers/axe';
import { expect, test } from './own-session-fixtures';

/**
 * Scan `main` and require it CLEAN, naming the step in the failure.
 *
 * The step name is not decoration: four scans that all failed with the same
 * message would leave a reader guessing which state broke, and this screen's
 * steps look alike in a screenshot.
 */
async function expectClean(page: Page, step: string) {
  /*
   * RETRY THE SCAN, DO NOT MERELY WAIT BEFORE IT. Added 2026-09-16.
   *
   * `scan` is scoped to `main`, and axe throws `No elements found for include in
   * page Context` when that selector matches nothing at the instant it runs. This
   * screen re-renders on every workflow action, so `main` is briefly detached
   * while React swaps the subtree.
   *
   * A `waitFor({ state: 'attached' })` BEFORE the scan does not close it: a wait
   * and a scan are two steps, and `main` can be attached when the wait resolves
   * and gone by the time axe walks the frame. A wait cannot close a race whose
   * window is after it. So the SCAN retries.
   *
   * **THE ASSERTION IS DELIBERATELY OUTSIDE THE RETRY.** Inside, it would retry a
   * GENUINE VIOLATION too — burning the timeout and then reporting it, or worse
   * passing if some later render happened to be clean. Only the transient
   * DOM-swap failure is retried; a real violation fails on the first scan that
   * completes.
   *
   * ── AND THE RETRY IS HOW A HARD CRASH WAS TOLD APART FROM A FLAKE ───────────
   *
   * With it in place the archive test failed on EVERY local run instead of
   * occasionally, because that one was never a race: pressing `Reconstruct
   * Candidates` CRASHED THE WHOLE SCREEN, so `main` genuinely did not exist for
   * the full 15 seconds. **The retry did not fix that** — the disagreement-row
   * contract in `bl15.reconstruct` did. A flaky-looking symptom and a hard crash
   * present identically through this helper, and the retry is what separated
   * them by turning one into a reproducible failure.
   *
   * It is kept for the case it does address: the first full-suite failure was in
   * the FIXTURE-path test, which that crash cannot reach.
   */
  let results!: Awaited<ReturnType<typeof scan>>;
  await expect(async () => {
    results = await scan(page, { include: 'main' });
  }).toPass({ timeout: 15_000 });
  expect(
    results.violations.map(formatViolation).join('\n\n'),
    `the import session has an accessibility violation at: ${step}. This state had NEVER ` +
      'been axe-scanned before this spec (M-11) — the read-only sweep stops at the empty ' +
      'list, and jsdom runs no accessibility engine. Fix it, or record it here with a reason.',
  ).toBe('');
}

/**
 * Put a stage in focus by pressing its tab, and wait until its panel is the one shown.
 *
 * ADDED 2026-09-22 (owner QA H1). The session became six stage tabs with ONE panel
 * shown; the other five stay mounted but `hidden`, and axe does not scan a hidden
 * subtree. So every stage is scanned by visiting it — a scan that never left the
 * default stage would pass while five-sixths of the screen went unexamined.
 */
async function openStage(page: Page, title: string) {
  const tab = page.getByRole('tab', { name: new RegExp(title.replace(/[&?]/g, '.')) });
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
  const panelId = await tab.getAttribute('aria-controls');
  await expect(page.locator(`[id="${panelId}"]`)).toBeVisible();
}

/**
 * Open every disclosure in the stage in focus — the shared `Disclosure`, each
 * measurement's legacy-cell toggle, and each conflict kind's `Show N more` (the rows
 * past the first five are `hidden` until it is pressed) — so axe scans what they hold. Nested ones
 * appear only once their parent is open, hence the bounded rounds. Returns how many
 * it opened, so a caller can assert the stage was not vacuous.
 */
async function openEverything(page: Page): Promise<number> {
  let total = 0;
  for (let round = 0; round < 4; round++) {
    const opened = await page.evaluate(() => {
      const panel = document.querySelector('[role="tabpanel"]:not([hidden])');
      if (!panel) return 0;
      const closed = [
        ...panel.querySelectorAll<HTMLButtonElement>(
          'button.hi-show-more[aria-expanded="false"], button.disclosure-trigger[aria-expanded="false"], button.bl15-unit-toggle[aria-expanded="false"]',
        ),
      ];
      closed.forEach((b) => b.click());
      return closed.length;
    });
    total += opened;
    if (opened === 0) break;
  }
  return total;
}

test.describe('the import session state, which the read-only sweep cannot reach', () => {
  test('an open import session carries no axe violation, at every stage', async ({ page }) => {
    await page.goto('/imports');

    // The list's own `<h2>`, not the page `<h1>` — the `<h1>` renders outside the
    // fetch branch, so gating on it would race the loading panel. Same reasoning
    // `surfaces.ts` gives for the read-only entry.
    await expect(page.getByRole('heading', { name: 'Imports', level: 2 })).toBeVisible();

    const start = page.getByRole('button', { name: 'Start an Import' });
    await expect(start).toBeVisible();
    await start.click();

    /*
     * A REAL SESSION ON A REAL BACKEND. `Back to imports` only exists in the
     * session view, so waiting on it proves the POST landed and the view
     * switched — rather than proving a spinner rendered. A new session opens on
     * the Source Bundle stage.
     */
    await expect(page.getByRole('button', { name: 'Back to imports' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Source Bundle' })).toBeVisible();
    await expectClean(page, 'Source Bundle, empty');

    /*
     * ── AND ON THROUGH THE STAGES ─────────────────────────────────────────
     *
     * Each step is reached by pressing the control a reader would press, and
     * each is waited on by something only the NEXT state renders — never by a
     * timeout, and never by a spinner, which would let the scan measure a
     * skeleton and report it as the step.
     */
    await page.getByRole('button', { name: 'Add an Example Source', exact: true }).click();
    // The table only exists once a source is in the bundle.
    await expect(page.getByRole('table')).toBeVisible();
    await openEverything(page);
    await expectClean(page, 'Source Bundle, one entry in the table, every disclosure open');

    await openStage(page, 'What ISAAC Read');
    await page.getByRole('button', { name: 'Read the Sources' }).click();
    // A parsed source's own row exists only after the read.
    await expect(page.locator('.hi-parsed-list > li').first()).toBeVisible();
    expect(await openEverything(page), 'the read stage opened nothing — nothing was read').toBeGreaterThan(0);
    await expectClean(page, 'What ISAAC Read, after the sources are read, every disclosure open');

    /*
     * ── THE WAIT THAT WAS VACUOUS ONCE, KEPT HONEST ───────────────────────
     *
     * The first version of this spec waited on a heading present BEFORE the
     * click, so it measured the previous state. `Candidate values` renders only
     * after reconstruction, and the negative control asserts it is absent
     * beforehand — so if it ever renders early this goes red instead of quietly
     * measuring the wrong thing.
     */
    await openStage(page, 'Runs & Candidates');
    await expect(
      page.getByRole('heading', { name: 'Candidate values' }),
      'the post-reconstruction heading is already present BEFORE reconstructing, so the ' +
        'wait below would be satisfied by the previous state — pick a different marker',
    ).toHaveCount(0);
    await page.getByRole('button', { name: 'Reconstruct Candidates' }).click();
    await expect(page.getByRole('heading', { name: 'Candidate values' })).toBeVisible();
    expect(await openEverything(page)).toBeGreaterThan(0);
    await expectClean(page, 'Runs & Candidates, after reconstruction, every candidate open');

    for (const stage of ['Conflicts', 'Review', 'Add to Experiment']) {
      await openStage(page, stage);
      await openEverything(page);
      await expectClean(page, `${stage}, every disclosure open`);
    }
  });

  test('VACUITY GUARD — the scan actually examined the session, not an empty page', async ({
    page,
  }) => {
    /*
     * Without this, the assertion above passes on a blank `<main>` — which is
     * exactly what it would do if `Start an Import` silently failed, or if the
     * include selector stopped matching. It asserts the SESSION is on screen and
     * that axe looked at a non-trivial number of nodes.
     */
    await page.goto('/imports');
    await page.getByRole('button', { name: 'Start an Import' }).click();
    await expect(page.getByRole('button', { name: 'Back to imports' })).toBeVisible();

    const results = await scan(page, { include: 'main' });
    const examined =
      results.passes.reduce((n, r) => n + r.nodes.length, 0) +
      results.violations.reduce((n, r) => n + r.nodes.length, 0) +
      results.incomplete.reduce((n, r) => n + r.nodes.length, 0);
    expect(examined, 'axe examined almost nothing — the scan is not seeing the session').toBeGreaterThan(50);

    // And the stage flow really is what is on screen: six tabs, one panel shown.
    await expect(page.getByRole('tab')).toHaveCount(6);
    await expect(page.locator('[role="tabpanel"]:visible')).toHaveCount(1);
    await expect(page.getByRole('heading', { name: 'Source Bundle' })).toBeVisible();
  });

  /*
   * ── THE CORPUS REVIEW, WHICH NOTHING REACHED UNTIL 2026-09-16 ─────────────
   *
   * The test above walks a session built from an EXAMPLE SOURCE. The corpus review
   * renders only for a session holding an ARCHIVE. This is the test that fails if
   * any link in that chain breaks again, and it is in the MUTATION suite for the
   * reason `surfaces.ts` gives: reaching a session needs a POST the read-only
   * config forbids. Since 2026-09-22 it scans EVERY stage of the archive session —
   * the overview, the measurements table with every measurement opened, every
   * conflict's four layers, Review and Add — because each is a different shape.
   */
  test('an archive session renders the corpus review, axe-clean at every stage', async ({ page }) => {
    await page.goto('/imports');
    await expect(page.getByRole('heading', { name: 'Imports', level: 2 })).toBeVisible();
    await page.getByRole('button', { name: 'Start an Import' }).click();
    await expect(page.getByRole('button', { name: 'Back to imports' })).toBeVisible();

    // NEGATIVE CONTROL FIRST: the review must not exist before an archive does, or
    // the scans below would prove nothing about the archive at all.
    await expect(page.locator('.bl15-highlights')).toHaveCount(0);

    await page.getByRole('button', { name: 'Add an Archive', exact: true }).click();
    await expect(page.getByRole('table')).toBeVisible();
    await expectClean(page, 'an archive in the bundle, before reading');

    await openStage(page, 'What ISAAC Read');
    await page.getByRole('button', { name: 'Read the Sources' }).click();
    /*
     * THE REVIEW APPEARS AT THE READ, not at the reconstruction: `corpus_review` is
     * served as soon as an archive reading exists. Waited on by the headline counts,
     * which only it renders.
     */
    await expect(page.locator('.bl15-highlights')).toBeVisible();
    expect(await openEverything(page)).toBeGreaterThan(0);
    await expectClean(page, 'What ISAAC Read — the corpus overview, every disclosure open');

    await openStage(page, 'Runs & Candidates');
    await expect(page.locator('.bl15-runs table').first()).toBeVisible();
    expect(await openEverything(page), 'no measurement opened — the table is empty').toBeGreaterThan(0);
    await expectClean(page, 'Runs & Candidates — every measurement and candidate open');

    /*
     * Pressing Reconstruct is still exercised: a bundle may hold an archive AND
     * example sources, and it must not take the review away.
     */
    await page.getByRole('button', { name: 'Reconstruct Candidates' }).click();
    await expect(page.locator('.bl15-runs table').first()).toBeVisible();

    await openStage(page, 'Conflicts');
    await expect(page.locator('.hi-conflict').first()).toBeVisible();
    // EVERY KIND IS COUNTED ON THE SURFACE with everything collapsed: a header with
    // its count is visible for each kind before anything is opened.
    const heads = page.locator('.hi-conflict-group-head');
    expect(await heads.count()).toBeGreaterThan(0);
    for (let i = 0; i < (await heads.count()); i++) {
      await expect(heads.nth(i).locator('.hi-count')).toBeVisible();
    }
    expect(await openEverything(page)).toBeGreaterThan(0);
    // After opening everything, no conflict row is left hidden behind Show more.
    await expect(page.locator('[role="tabpanel"]:not([hidden]) li.hi-conflict[hidden]')).toHaveCount(0);
    await expectClean(page, 'Conflicts — every conflict’s four layers open');

    for (const stage of ['Review', 'Add to Experiment']) {
      await openStage(page, stage);
      await openEverything(page);
      await expectClean(page, `${stage} (archive), every disclosure open`);
    }
  });

  test('VACUITY GUARD — the corpus review scan examined a real archive reading', async ({
    page,
  }) => {
    /*
     * A review rendered from an EMPTY archive would scan clean too, and would pass
     * while proving nothing about the thing this feature is for. So it asserts the
     * headline counts are measured, not zeros.
     */
    await page.goto('/imports');
    await page.getByRole('button', { name: 'Start an Import' }).click();
    await expect(page.getByRole('button', { name: 'Back to imports' })).toBeVisible();
    await page.getByRole('button', { name: 'Add an Archive', exact: true }).click();
    await openStage(page, 'What ISAAC Read');
    await page.getByRole('button', { name: 'Read the Sources' }).click();
    await expect(page.locator('.bl15-highlights')).toBeVisible();

    const values = (await page.locator('.bl15-highlight dd').allInnerTexts()).map((t) =>
      Number(t.replace(/,/g, '')),
    );
    expect(
      values.some((n) => n > 1),
      'no headline count exceeds 1, so the archive walk found nothing and the axe scans ' +
        'above examined an empty review',
    ).toBe(true);

    // And there are FEWER measurements than files walked — the whole point of the
    // feature; one unit per file would be the banned 1,192-row table renamed.
    const byLabel = Object.fromEntries(
      await page.locator('.bl15-highlight').evaluateAll((els) =>
        els.map((el) => [el.querySelector('dt')?.textContent ?? '', Number((el.querySelector('dd')?.textContent ?? '0').replace(/,/g, ''))]),
      ),
    ) as Record<string, number>;
    const sources = Object.entries(byLabel).find(([k]) => /source|file/i.test(k))?.[1] ?? 0;
    const measurements = Object.entries(byLabel).find(([k]) => /measurement/i.test(k))?.[1] ?? 0;
    expect(measurements).toBeGreaterThan(0);
    expect(measurements).toBeLessThan(sources);
  });
});

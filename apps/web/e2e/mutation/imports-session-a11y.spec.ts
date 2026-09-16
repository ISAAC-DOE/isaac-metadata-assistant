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
   * WAIT FOR THE SCOPE TO EXIST BEFORE SCANNING IT. Added 2026-09-16.
   *
   * `scan` is scoped to `main`, and axe throws `No elements found for include in
   * page Context` when that selector matches nothing at the moment it runs. This
   * screen re-renders on every workflow action, and a `toBeVisible()` on some
   * inner heading can resolve in a paint where `main` itself is between renders —
   * so the wait that preceded each call was on the wrong element.
   *
   * IT IS A PRE-EXISTING FLAKE, not one the archive tests introduced: two
   * consecutive full-suite runs failed in DIFFERENT tests, the first of them one
   * this spec already had. Adding more scans made it likelier to show, which is
   * how it surfaced. Fixed in the shared helper rather than at a call site,
   * because every scan here has the same exposure.
   *
   * `attached` rather than `visible`: `main` is the scope, not the subject, and a
   * scope that exists is exactly what axe needs.
   */
  await page.locator('main').first().waitFor({ state: 'attached' });
  const results = await scan(page, { include: 'main' });
  expect(
    results.violations.map(formatViolation).join('\n\n'),
    `the import session has an accessibility violation at: ${step}. This state had NEVER ` +
      'been axe-scanned before this spec (M-11) — the read-only sweep stops at the empty ' +
      'list, and jsdom runs no accessibility engine. Fix it, or record it here with a reason.',
  ).toBe('');
}

test.describe('the import session state, which the read-only sweep cannot reach', () => {
  test('an open import session carries no axe violation', async ({ page }) => {
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
     * switched — rather than proving a spinner rendered.
     */
    await expect(page.getByRole('button', { name: 'Back to imports' })).toBeVisible();

    await expectClean(page, 'Sources, empty');

    /*
     * ── AND ON THROUGH THE WORKFLOW ────────────────────────────────────────
     *
     * Each step is reached by pressing the control a reader would press, and
     * each is waited on by something only the NEXT state renders — never by a
     * timeout, and never by a spinner, which would let the scan measure a
     * skeleton and report it as the step.
     */
    await page.getByRole('button', { name: 'Add an Example Source' }).click();
    // The table only exists once a source is in the bundle.
    await expect(page.getByRole('table')).toBeVisible();
    await expectClean(page, 'Sources, one entry in the table');

    await page.getByRole('button', { name: 'Read the Sources' }).click();
    await expect(page.getByRole('button', { name: 'Reconstruct Candidates' })).toBeEnabled();
    await expectClean(page, 'after the sources are read');

    /*
     * ── THE WAIT THAT WAS VACUOUS, AND HOW IT WAS CAUGHT ──────────────────
     *
     * The first version waited on `heading /Candidates/i`. That matched
     * **"Reconstruct Candidates"** — the step's own heading, present BEFORE the
     * click — so the wait was satisfied instantly and this scan measured the
     * PREVIOUS state while claiming to measure the reconstruction. Found by a
     * throwaway probe that printed every heading at every step, not by a
     * failing test: the suite was green with the vacuous wait in place.
     *
     * The three headings below appear ONLY after reconstruction, and the
     * negative control asserts the first one is absent beforehand — so if a
     * future change makes it render early, this goes red instead of quietly
     * measuring the wrong thing again.
     */
    await expect(
      page.getByRole('heading', { name: 'Ready for your review' }),
      'the post-reconstruction heading is already present BEFORE reconstructing, so the ' +
        'wait below would be satisfied by the previous state — pick a different marker',
    ).toHaveCount(0);

    await page.getByRole('button', { name: 'Reconstruct Candidates' }).click();
    await expect(page.getByRole('heading', { name: 'Ready for your review' })).toBeVisible();
    // All three outcome groups render together, and each is a different shape:
    // accepted candidates, ones with no schema home, and unrecognised text.
    await expect(page.getByRole('heading', { name: 'Read, with nowhere to write' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Read, but not recognised' })).toBeVisible();
    await expectClean(page, 'after candidates are reconstructed');
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

    // And the Sources step really is what is on screen.
    await expect(page.getByRole('heading', { name: /Sources/i }).first()).toBeVisible();
  });

  /*
   * ── THE CORPUS REVIEW, WHICH NOTHING REACHED UNTIL 2026-09-16 ─────────────
   *
   * The test above walks a session built from an EXAMPLE SOURCE, and that is the
   * only kind the screen offered. The corpus review renders only for a session
   * holding an ARCHIVE, so it was unreachable — and independent review found the
   * two halves had been built against different shapes and never joined at all.
   *
   * The chain had three broken links and each looked like the others' fault:
   * `grep -rn corpus_review apps/api/` returned zero (the route emitted nothing),
   * the client type did not declare the member, and no control created an archive
   * source even though the server had always served `available_archives`. Fixing
   * any one alone would have left the surface as unreachable as before.
   *
   * This is the test that fails if any link breaks again, and it is in the MUTATION
   * suite for the reason `surfaces.ts` gives: reaching a session needs a POST the
   * read-only config forbids.
   */
  test('an archive session renders the corpus review, axe-clean', async ({ page }) => {
    await page.goto('/imports');
    await expect(page.getByRole('heading', { name: 'Imports', level: 2 })).toBeVisible();
    await page.getByRole('button', { name: 'Start an Import' }).click();
    await expect(page.getByRole('button', { name: 'Back to imports' })).toBeVisible();

    // NEGATIVE CONTROL FIRST: the review must not be on screen before an archive
    // exists, or the scan below would prove nothing about the archive at all.
    await expect(page.getByRole('heading', { name: /What this archive contains/i })).toHaveCount(
      0,
    );

    await page.getByRole('button', { name: 'Add an Archive' }).click();
    await expect(page.getByRole('table')).toBeVisible();
    await expectClean(page, 'an archive in the bundle, before reading');

    await page.getByRole('button', { name: 'Read the Sources' }).click();
    await expect(page.getByRole('button', { name: 'Reconstruct Candidates' })).toBeEnabled();

    /*
     * THE REVIEW APPEARS AT THE READ, not at the reconstruction: `corpus_review`
     * is served as soon as an archive reading exists. Waited on by a heading only
     * it renders — never a timeout, and never a spinner.
     */
    const digest = page.getByRole('heading', { name: /What this archive contains/i });
    await expect(digest).toBeVisible();
    await expectClean(page, 'the corpus review, after the archive is read');

    /*
     * ── AND A PRODUCT FACT THIS TEST ESTABLISHED, worth stating ──────────────
     *
     * `Ready for your review` is the FIXTURE path's heading, rendered from
     * `data.reconstruction` — the provider's reconstruction over `parsed`. An
     * archive has none of that: `read_archive` runs the whole chain at the READ,
     * so its candidates are already in `corpus_review` and `parsed` stays empty.
     * Asserting that heading here would be asserting the wrong surface, and it is
     * how this test first failed.
     *
     * Pressing the control is still exercised, because a bundle may hold an
     * archive AND example sources, and it must not take the review away.
     */
    await page.getByRole('button', { name: 'Reconstruct Candidates' }).click();
    await expect(digest).toBeVisible();
    await expectClean(page, 'the corpus review, after reconstruction is pressed');
  });

  test('VACUITY GUARD — the corpus review scan examined a real archive reading', async ({
    page,
  }) => {
    /*
     * The sibling guard above exists because a scan of an empty page is clean. This
     * one exists because a scan of a review rendered from an EMPTY archive would be
     * clean too, and would pass while proving nothing about the thing this feature
     * is for. So it asserts the digest carries measured counts, not zeros.
     */
    await page.goto('/imports');
    await page.getByRole('button', { name: 'Start an Import' }).click();
    await expect(page.getByRole('button', { name: 'Back to imports' })).toBeVisible();
    await page.getByRole('button', { name: 'Add an Archive' }).click();
    await page.getByRole('button', { name: 'Read the Sources' }).click();
    await expect(page.getByRole('heading', { name: /What this archive contains/i })).toBeVisible();

    // The digest rows are the feature's own numbers. At least one must be nonzero,
    // or the walk found nothing and the clean scan above is vacuous.
    const body = await page.locator('body').innerText();
    const numbers = [...body.matchAll(/\b(\d+)\b/g)].map((m) => Number(m[1]));
    expect(
      numbers.some((n) => n > 1),
      'no count on the corpus review exceeds 1, so the archive walk found nothing ' +
        'and the axe scan above examined an empty review',
    ).toBe(true);

    // And the measurement units really are fewer than the files walked — the whole
    // point of the feature, and a review showing one unit per file would be the
    // banned 1,192-row table under another name.
    await expect(page.getByText(/Measurements reconstructed/i)).toBeVisible();
  });
});

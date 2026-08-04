/**
 * The guided walkthrough, driven through the REAL UI against the REAL API.
 * @interaction
 *
 * Runs at 1280x800 AND at 375x812 (the `@interaction` projects), because the
 * `max-width: 640px` breakpoint changes the chrome the coach mark and the
 * worked-example bar live in, and because the mark is absolutely positioned
 * against a measured control.
 *
 * ── Nothing here is mocked ──────────────────────────────────────────────────
 *
 * Session creation, session disposal, the record list, the coach-mark anchors
 * and the chip all come from the running app and the running backend. The only
 * `page.route` in the file aborts a request to produce a TRANSPORT failure the
 * real backend cannot be asked for on demand, and it is labelled where it is
 * used. No response body is ever synthesised.
 *
 * ── How this stays safe beside the read-only projects ───────────────────────
 *
 * Every test here starts its OWN walkthrough, so the backend mints a session
 * that belongs to this test alone; the `tutorial` fixture records every session
 * id the page caused to exist and disposes all of them afterwards, whether or
 * not the test reached an exit path. The shared session that `global-setup.ts`
 * opened — the one the surface sweeps measure in five parallel projects — is
 * never entered, never mutated and never disposed here. And the ORDINARY
 * workspace stays empty throughout, which several tests re-assert rather than
 * assume.
 *
 * ── What is deliberately NOT here ──────────────────────────────────────────
 *
 * Reset, completion (and the cleanup that follows it) and replay live in the
 * MUTATION suite (`e2e/mutation/tutorial-lifecycle.spec.ts`), which owns its
 * own backend and its own workspace. They are the scenarios that write, and the
 * read-only suite's contract is that it does not.
 */

import { API_BASE, SEED } from '../env';
import { expect, test } from '../fixtures';
import { SURFACES } from '../surfaces';
import { enterWorkedExampleAsTheAppDoes } from '../worked-example';

const experiments = SURFACES.find((s) => s.id === 'experiments')!;

/** Well-formed (`^[A-Za-z0-9_-]{16,64}$`) but naming no session — what a
 *  reader's `sessionStorage` holds after their session expired or was swept. */
const EXPIRED_SESSION_ID = 'e2eExpiredSession-0001';

const bar = (page: import('@playwright/test').Page) =>
  page.getByRole('complementary', { name: 'Worked example session' });
const mark = (page: import('@playwright/test').Page) => page.locator('.tutorial-mark');
const chip = (page: import('@playwright/test').Page) => page.locator('span.mode-chip');

/** Start the walkthrough from the first-run offer and wait until step one is up. */
async function startFromOffer(page: import('@playwright/test').Page) {
  await page.getByRole('button', { name: 'Start Tutorial' }).click();
  await expect(bar(page)).toBeVisible({ timeout: 20_000 });
  await expect(mark(page)).toBeVisible({ timeout: 20_000 });
  await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'experiments-overview');
}

test.describe('@interaction the first-run offer', () => {
  test('is offered on My Experiments, and offers exactly two choices', async ({ page, app }) => {
    await app.open(experiments);

    const offer = page.getByRole('region', { name: 'Take the Guided Walkthrough' });
    await expect(offer.or(page.locator('section.tutorial-offer')).first()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Take the Guided Walkthrough' })).toBeVisible();
    // The copy must not promise a change: the walkthrough only reads.
    await expect(page.locator('section.tutorial-offer')).toContainText(/only reads/i);
    await expect(page.getByRole('button', { name: 'Start Tutorial' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Skip for Now' })).toBeEnabled();
  });

  test('"Skip for Now" hides the offer and creates NO session', async ({ page, app, tutorial }) => {
    await app.open(experiments);
    await page.getByRole('button', { name: 'Skip for Now' }).click();

    await expect(page.locator('section.tutorial-offer')).toHaveCount(0);
    // The distinction that matters: declining the OFFER is not the same event as
    // leaving a running walkthrough. Nothing server-side happened at all.
    expect(
      tutorial.sessionsCreated(),
      'declining the offer must not open a worked-example session'
    ).toEqual([]);
    await expect(bar(page)).toHaveCount(0);
    await expect(chip(page)).toHaveText('Workspace');

    // And it is "not now", not "never": a fresh visit offers it again, because
    // dismissal is session-scoped and deliberately unpersisted.
    await app.open(experiments);
    await expect(page.getByRole('heading', { name: 'Take the Guided Walkthrough' })).toBeVisible();
  });

  test('is not offered to a browser that already finished it', async ({ page, app, tutorial }) => {
    await tutorial.markCompleted();
    await app.open(experiments);
    await expect(page.locator('section.tutorial-offer')).toHaveCount(0);
    // …and the permanent home of the replay control is where the empty state
    // points, not a card in the primary workflow.
    await expect(page.getByRole('button', { name: 'Replay Tutorial' })).toBeVisible();
  });
});

test.describe('@interaction starting the walkthrough', () => {
  test('mints exactly one session, and the examples appear only inside it', async ({
    page,
    app,
    tutorial,
    request,
  }) => {
    await app.open(experiments);
    // Precondition, measured rather than assumed: the ordinary queue is empty.
    await expect(page.locator('.exp-row')).toHaveCount(0);

    await startFromOffer(page);

    const sessions = tutorial.sessionsCreated();
    expect(sessions.length, `starting must open exactly one session, got ${sessions.length}`).toBe(1);

    // The five examples are now on screen — on the same route that was empty a
    // moment ago, because the scope changed rather than the workspace.
    await expect(page.locator('.exp-row')).toHaveCount(5);
    await expect(page.locator('.queue-empty-state')).toHaveCount(0);

    // Independently: they are in the SESSION, and the ordinary scope is still
    // empty. This is the claim the whole design rests on, so it is checked at
    // the API rather than inferred from the screen.
    const inSession = await tutorial.listInSession(sessions[0]);
    expect(inSession.status).toBe(200);
    expect(inSession.ids.slice().sort()).toEqual(Object.values(SEED).slice().sort());
    const ordinary = await request.get(`${API_BASE}/experiments`);
    expect(((await ordinary.json()) as { experiments?: unknown[] }).experiments ?? []).toEqual([]);
  });

  test('the mode chip names the scope, and its accessible name states what is in it', async ({ page, app }) => {
    await app.open(experiments);
    await expect(chip(page)).toHaveText('Workspace');

    await startFromOffer(page);

    await expect(chip(page)).toHaveText('Worked Example');
    const name = await chip(page).getAttribute('aria-label');
    expect(name!.startsWith('Worked Example')).toBe(true);
    // In THIS scope there are records, and the chip says what they are and that
    // they go away — the claims the ordinary branch must not make.
    expect(name).toMatch(/belong to this walkthrough only/i);
    expect(name).toMatch(/discarded when the walkthrough ends/i);
    // The two unconditional claims survive in both scopes.
    expect(name).toMatch(/file upload is refused/i);
    expect(name).toMatch(/no official institutional record is shown/i);
  });

  test('the worked-example bar states the scope and holds the two example controls', async ({ page, app }) => {
    await app.open(experiments);
    await startFromOffer(page);

    const region = bar(page);
    await expect(region).toBeVisible();
    // It makes three structural claims; all three are true of a session, and a
    // reader is told them in visible text rather than only in an aria-label.
    await expect(region).toContainText(/this walkthrough/i);
    await expect(region.getByRole('button', { name: 'Open the Worked Example' })).toBeVisible();
    await expect(region.getByRole('button', { name: /Reset Worked Example/i })).toBeVisible();
  });
});

test.describe('@interaction the coach marks', () => {
  test('point at a REAL control, on the surface that control lives on', async ({ page, app }) => {
    await app.open(experiments);
    await startFromOffer(page);

    // Step 1 — `data-tutorial-step-available="true"` is the component's own
    // statement that it resolved an anchor rather than degrading to an
    // explanation, and the highlight attribute is on the live element.
    await expect(mark(page)).toHaveAttribute('data-tutorial-step-available', 'true');
    const highlighted = page.locator('[data-tutorial-highlight="true"]');
    await expect(highlighted).toHaveCount(1);
    // It is a control the PRODUCT renders, identified by the anchor contract —
    // not a decorative stand-in the walkthrough drew for itself.
    await expect(highlighted).toHaveAttribute('data-tutorial-anchor', 'experiments-queue');

    // The ring is drawn around that element's box, and is decorative.
    const ring = page.getByTestId('tutorial-ring');
    await expect(ring).toBeVisible();
    await expect(ring).toHaveAttribute('aria-hidden', 'true');
    const boxes = await page.evaluate(() => {
      const a = document.querySelector('[data-tutorial-highlight="true"]')!.getBoundingClientRect();
      const r = document.querySelector('[data-testid="tutorial-ring"]')!.getBoundingClientRect();
      return { a: { x: a.x, y: a.y }, r: { x: r.x, y: r.y } };
    });
    // The ring is inset by 4px on each side by construction.
    expect(Math.abs(boxes.r.x - (boxes.a.x - 4))).toBeLessThanOrEqual(2);
    expect(Math.abs(boxes.r.y - (boxes.a.y - 4))).toBeLessThanOrEqual(2);

    // The step is announced as well as drawn, and the announcement carries the
    // position — the dialog node is reused between steps, so its label alone
    // would not be re-read.
    await expect(page.locator('.sr-only[role="status"]')).toContainText(/Step 1 of \d+/i);

    // It is a dialog, and deliberately NOT a modal one: the control it describes
    // has to stay operable while it is described.
    await expect(mark(page)).toHaveAttribute('role', 'dialog');
    expect(await mark(page).getAttribute('aria-modal')).toBeNull();
  });

  test('Next advances and navigates; Back returns without losing the session', async ({ page, app, tutorial }) => {
    await app.open(experiments);
    await startFromOffer(page);
    const session = tutorial.sessionsCreated()[0];

    // Back is disabled on step one — there is nowhere behind it.
    await expect(page.getByRole('button', { name: 'Back', exact: true })).toBeDisabled();

    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'open-example');
    await expect(page.locator('[data-tutorial-highlight="true"]')).toHaveAttribute(
      'data-tutorial-anchor',
      'experiment-row'
    );

    // Step three lives on a record surface, so the walkthrough navigates there —
    // and the record resolves, which it could only do inside the session.
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'record-readiness');
    await expect(page).toHaveURL(/\/record\/01SYNTHXANESSEED000000000\d$/);
    await expect(page.getByRole('heading', { name: 'Review Record' })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);

    // Back returns to the previous step, and back to its surface.
    await page.getByRole('button', { name: 'Back', exact: true }).click();
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'open-example');
    await expect(page).toHaveURL(/\/experiments$/);

    // Throughout, one session and only one.
    expect(tutorial.sessionsCreated()).toEqual([session]);
    await expect(bar(page)).toBeVisible();
  });

  test('progresses by keyboard alone, and focus lands in the mark on every step', async ({ page, app }) => {
    await app.open(experiments);
    await startFromOffer(page);

    // Focus is moved INTO the mark when a step becomes visible (not trapped
    // there — the described control must stay reachable).
    await expect(mark(page)).toBeFocused();

    // Tab from the mark to its own Next button and activate it with the
    // keyboard. No mouse is used in this test after the start click.
    const next = page.getByRole('button', { name: 'Next', exact: true });
    await next.focus();
    await expect(next).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'open-example');
    // Re-focused on the new step, because the announcement and the focus move
    // are keyed on the step id rather than on the (reused) DOM node.
    await expect(mark(page)).toBeFocused();

    // Space activates a button too — asserted because a div-with-onClick would
    // pass the Enter check and fail this one.
    await next.focus();
    await page.keyboard.press('Space');
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'record-readiness');
  });

  test('stays inside the viewport at this width', async ({ page, app }) => {
    await app.open(experiments);
    await startFromOffer(page);

    // Meaningful at 375 in particular: the mark is absolutely positioned against
    // a measured control and clamped to the viewport, so a mis-clamp shows up as
    // page-level horizontal scrolling or a box hanging off the right edge.
    const geometry = await page.evaluate(() => {
      const el = document.querySelector('.tutorial-mark')!.getBoundingClientRect();
      return {
        right: el.right,
        left: el.left,
        vw: document.documentElement.clientWidth,
        docScroll: document.documentElement.scrollWidth,
        docClient: document.documentElement.clientWidth,
      };
    });
    expect(geometry.left).toBeGreaterThanOrEqual(0);
    expect(geometry.right, 'the coach mark overflows the viewport').toBeLessThanOrEqual(geometry.vw + 1);
    expect(geometry.docScroll, 'the coach mark makes the page scroll sideways').toBeLessThanOrEqual(
      geometry.docClient + 1
    );
  });

  test('under reduced motion the mark is positioned immediately, not after an animation', async ({ page, app }) => {
    // The context reports `prefers-reduced-motion: reduce` (set in
    // `playwright.config.ts`), which is the real user setting rather than a
    // simulation of one. `GuidedTutorial` reads it to choose `scrollIntoView`
    // behaviour and to collapse its reposition delay to 0ms.
    //
    // HONEST LIMIT: this does not prove no animation is painted — the shared
    // fixture also injects a stylesheet that zeroes durations, so a CSS
    // transition assertion here would be vacuous. What it proves is the
    // FUNCTIONAL consequence: the ring is aligned with the control on the very
    // first measurement, with no settling wait.
    expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);

    await app.open(experiments);
    await startFromOffer(page);

    const aligned = await page.evaluate(() => {
      const a = document.querySelector('[data-tutorial-highlight="true"]')!.getBoundingClientRect();
      const r = document.querySelector('[data-testid="tutorial-ring"]')!.getBoundingClientRect();
      return Math.abs(r.width - (a.width + 8)) <= 2 && Math.abs(r.height - (a.height + 8)) <= 2;
    });
    expect(aligned, 'the ring did not match the anchor box on the first measurement').toBe(true);
  });
});

test.describe('@interaction leaving the walkthrough', () => {
  test('Close discards the session, and the examples go with it', async ({ page, app, tutorial }) => {
    await app.open(experiments);
    await startFromOffer(page);
    const session = tutorial.sessionsCreated()[0];
    await expect(page.locator('.exp-row')).toHaveCount(5);

    const deletes: string[] = [];
    page.on('request', (r) => {
      if (r.method() === 'DELETE') deletes.push(new URL(r.url()).pathname);
    });

    await page.getByRole('button', { name: 'Close Tutorial' }).click();

    // The overlay and the chrome go.
    await expect(mark(page)).toHaveCount(0);
    await expect(bar(page)).toHaveCount(0);
    await expect(chip(page)).toHaveText('Workspace');

    // The examples are gone from the screen, because the scope they lived in is
    // gone — the ordinary queue is empty again, on the same route.
    await expect(page.locator('.exp-row')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'No experiments yet' })).toBeVisible();

    // Cleanup was a real request, and the session really stopped existing.
    await expect
      .poll(() => deletes.filter((p) => p.includes('/tutorial/sessions/')).length, { timeout: 15_000 })
      .toBeGreaterThan(0);
    await expect
      .poll(async () => (await tutorial.listInSession(session)).status, { timeout: 15_000 })
      .toBe(404);
  });

  test('Escape leaves it exactly as Close does, and does NOT mark it complete', async ({ page, app, tutorial }) => {
    await app.open(experiments);
    await startFromOffer(page);
    const session = tutorial.sessionsCreated()[0];

    await page.keyboard.press('Escape');

    await expect(mark(page)).toHaveCount(0);
    await expect(bar(page)).toHaveCount(0);
    await expect
      .poll(async () => (await tutorial.listInSession(session)).status, { timeout: 15_000 })
      .toBe(404);

    // Not completed: leaving is not finishing. `localStorage` is the durable
    // record of completion, and it must be untouched.
    expect(
      await page.evaluate(() => localStorage.getItem('isaac.tutorial.v1')),
      'Escape must not record the walkthrough as completed'
    ).toBeNull();

    // The offer is hidden for the rest of THIS session so the reader is not
    // interrupted twice…
    await expect(page.locator('section.tutorial-offer')).toHaveCount(0);
    // …and offered again on a fresh visit, because "not now" was not turned into
    // "never".
    await app.open(experiments);
    await expect(page.getByRole('heading', { name: 'Take the Guided Walkthrough' })).toBeVisible();
  });

  test('"Skip Tutorial" in the mark also discards the session', async ({ page, app, tutorial }) => {
    await app.open(experiments);
    await startFromOffer(page);
    const session = tutorial.sessionsCreated()[0];

    await page.getByRole('button', { name: 'Skip Tutorial' }).click();

    await expect(mark(page)).toHaveCount(0);
    await expect(bar(page)).toHaveCount(0);
    await expect
      .poll(async () => (await tutorial.listInSession(session)).status, { timeout: 15_000 })
      .toBe(404);
    await expect(page.locator('.exp-row')).toHaveCount(0);
  });
});

test.describe('@interaction reloading', () => {
  test('a refresh mid-walkthrough RESUMES the same step in the same session', async ({ page, app, tutorial }) => {
    await app.open(experiments);
    await startFromOffer(page);
    const session = tutorial.sessionsCreated()[0];

    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'record-readiness');

    await page.reload({ waitUntil: 'domcontentloaded' });

    // Same step — the stored index is what makes this a resume rather than a
    // restart — and the record is still reachable, so the scope was re-entered
    // before the screen's first fetch.
    await expect(mark(page)).toBeVisible({ timeout: 20_000 });
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'record-readiness');
    await expect(page.getByRole('heading', { name: 'Review Record' })).toBeVisible();
    await expect(bar(page)).toBeVisible();
    await expect(chip(page)).toHaveText('Worked Example');

    // And NO second session: a reload must not mint one, or a reader who
    // refreshed twice would be paying for three sessions.
    expect(tutorial.sessionsCreated(), 'a reload must not open another session').toEqual([session]);
  });

  test('after leaving, a refresh comes back to the ordinary empty workspace', async ({ page, app }) => {
    await app.open(experiments);
    await startFromOffer(page);
    await page.getByRole('button', { name: 'Close Tutorial' }).click();
    await expect(bar(page)).toHaveCount(0);

    await page.reload({ waitUntil: 'domcontentloaded' });

    // The persisted pointer was cleared on the way out, so the reload does not
    // resurrect the discarded session (which would 404 everything) and does not
    // show the expired notice either.
    await expect(page.getByRole('heading', { name: 'No experiments yet' })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-tutorial-notice]')).toHaveCount(0);
    await expect(bar(page)).toHaveCount(0);
    await expect(chip(page)).toHaveText('Workspace');
  });

  test('an EXPIRED session is recovered from honestly, not silently', async ({ page, app, tutorial }) => {
    // The state a reader is in when their session was swept (or discarded in
    // another tab) while the pointer to it survived the reload. Installed the way
    // the app itself stores it — `sessionStorage`, read by `lib/api.ts` at module
    // load — with a well-formed id that names no session.
    await enterWorkedExampleAsTheAppDoes(page, EXPIRED_SESSION_ID, 4);
    await app.goto('/experiments');

    // Said out loud, with `role="alert"`, because there is no overlay left to
    // carry the message and the reader did not do anything wrong.
    const notice = page.locator('[data-tutorial-notice="expired"]');
    await expect(notice).toBeVisible({ timeout: 20_000 });
    await expect(notice).toHaveAttribute('role', 'alert');
    await expect(notice).toContainText(/expired/i);

    // The scope was LEFT, not clung to: the ordinary empty workspace is what is
    // shown, the chip agrees, and no walkthrough opened pointing at records that
    // would 404.
    await expect(page.getByRole('heading', { name: 'No experiments yet' })).toBeVisible();
    await expect(mark(page)).toHaveCount(0);
    await expect(bar(page)).toHaveCount(0);
    await expect(chip(page)).toHaveText('Workspace');

    // The pointer is forgotten, so the notice does not recur on every navigation.
    expect(await page.evaluate(() => sessionStorage.getItem('isaac.tutorial.session.v1'))).toBeNull();

    // Nothing was created to recover: an expired session is not re-minted behind
    // the reader's back, and it is certainly not recorded as a completed
    // walkthrough.
    expect(tutorial.sessionsCreated()).toEqual([]);
    expect(await page.evaluate(() => localStorage.getItem('isaac.tutorial.v1'))).toBeNull();

    // Dismissing it retries nothing and leaves the app usable.
    await page.getByRole('button', { name: 'Dismiss' }).click();
    await expect(notice).toHaveCount(0);
  });
});

test.describe('@interaction a step whose target is missing', () => {
  test('explains itself instead of pointing at nothing — and manufactures nothing', async ({
    page,
    tutorial,
    request,
  }) => {
    /*
     * LABELLED TRANSPORT FAILURE, not a mocked response. The walkthrough resolves
     * its three target records with ONE `GET /api/experiments`. Aborting that
     * request (the exact collection path, so `/experiments/{id}` is untouched) is
     * a condition the real backend cannot be asked to produce on demand, and it
     * is the same technique `specs/states.spec.ts` uses for the error states. No
     * body is synthesised and no session call is intercepted: the session is
     * really created, by the real button.
     *
     * Started from Settings → Help & Tutorial rather than from the offer, because
     * the offer renders only on My Experiments' LOADED branch and that branch
     * needs the very request this test breaks.
     */
    await page.route(
      (url) => url.pathname === '/api/experiments',
      (route) => route.abort('failed')
    );

    await page.goto('/settings?tab=help', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Replay Tutorial' }).click();

    await expect(mark(page)).toBeVisible({ timeout: 25_000 });
    expect(tutorial.sessionsCreated().length, 'the session itself is real').toBe(1);

    // Step 2 needs "any record" and the list could not be read, so the step is
    // knowable-unavailable without waiting on the DOM.
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'open-example');
    await expect(mark(page)).toHaveAttribute('data-tutorial-step-available', 'false');

    const explanation = page.locator('.tutorial-unavailable');
    await expect(explanation).toBeVisible();
    // Two things the copy must say: WHY, and that nothing was changed to force
    // the state. A walkthrough that quietly skips is indistinguishable from a
    // walkthrough that is broken.
    await expect(explanation).toContainText(/Not shown on this visit/i);
    await expect(explanation).toContainText(/Nothing was created to stand in for one/i);

    // Nothing was highlighted, so no stale control from a previous surface is
    // being presented as this step's subject.
    await expect(page.locator('[data-tutorial-highlight="true"]')).toHaveCount(0);
    await expect(page.getByTestId('tutorial-ring')).toHaveCount(0);

    // And the walkthrough is still navigable — an unavailable step is not a dead
    // end.
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'record-readiness');

    // The ordinary workspace is untouched by all of it.
    const ordinary = await request.get(`${API_BASE}/experiments`);
    expect(((await ordinary.json()) as { experiments?: unknown[] }).experiments ?? []).toEqual([]);
  });
});

test.describe('@interaction the walkthrough is quiet', () => {
  test('logs no console error and issues no unexpected write', async ({ page, app, consoleErrors, tutorial }) => {
    const writes: string[] = [];
    page.on('request', (r) => {
      const method = r.method();
      if (method === 'GET' || method === 'OPTIONS') return;
      writes.push(`${method} ${new URL(r.url()).pathname}`);
    });

    await app.open(experiments);
    await startFromOffer(page);
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'record-readiness');

    /*
     * The console is asserted HERE, at the deepest point of the walkthrough,
     * rather than after leaving it — and that boundary is deliberate.
     *
     * Closing the walkthrough from a record surface disposes the session while the
     * browser is still ON a record URL, so the record genuinely stops existing and
     * the app's next fetch is a REAL 404 that lands in the console. Asserting an
     * empty console across that exit would either fail (as it did) or force an
     * allowlist that would also swallow an unrelated 404. So the quiet-console
     * claim is made about the walkthrough itself, and what the exit does is
     * asserted below as behaviour instead of measured as noise.
     */
    expect(
      consoleErrors,
      `console errors while walking the tutorial:\n${consoleErrors.join('\n')}`
    ).toEqual([]);

    await page.getByRole('button', { name: 'Close Tutorial' }).click();
    await expect(bar(page)).toHaveCount(0);

    expect(tutorial.sessionsCreated().length).toBe(1);

    /*
     * WHAT COUNTS AS A WRITE, and why this is not "no POSTs".
     *
     * The first version of this assertion allowed only the two session calls and
     * failed — on `POST /api/experiments/{id}/validate` and
     * `POST /api/experiments/{id}/audit`, which the RECORD SURFACE issues as soon
     * as the walkthrough navigates to it. Neither mutates: `routes.py` documents
     * validate as "Read-only in both cases" (the pre-export verdict is a
     * dry run computed in memory) and audit as "Read-only" (it globs the exported
     * artifacts). They are POST-shaped reads because they carry a body / a
     * candidate record, not because they change anything.
     *
     * So the assertion pins the thing that actually matters — no MUTATION — by
     * naming the mutating endpoints rather than by proxying for them with the HTTP
     * verb. `/answers`, `/export`, `/demo/run`, `/demo/reset` and `/uploads` are
     * exactly the operations that would let the walkthrough manufacture a state it
     * is only supposed to describe.
     */
    const MUTATING = /\/(answers|export|demo\/run|demo\/reset|uploads|ingestion)\b/;
    const mutations = writes.filter((w) => MUTATING.test(w));
    expect(
      mutations,
      `the walkthrough performed a mutation it is never allowed to perform: ${mutations.join(', ')}`
    ).toEqual([]);

    // Exactly one session opened and one discarded, and no OTHER session traffic.
    expect(writes.filter((w) => /^POST \/api\/tutorial\/sessions$/.test(w)).length).toBe(1);
    expect(writes.filter((w) => /^DELETE \/api\/tutorial\/sessions\//.test(w)).length).toBe(1);

    // Everything else that went out is on the read-only allowlist above. Listed
    // rather than counted, so a NEW endpoint appearing here has to be classified
    // by a human instead of quietly joining the total.
    const unclassified = writes.filter(
      (w) =>
        !/^POST \/api\/tutorial\/sessions$/.test(w) &&
        !/^DELETE \/api\/tutorial\/sessions\//.test(w) &&
        !/^POST \/api\/experiments\/[A-Z0-9]+\/(validate|audit)$/.test(w)
    );
    expect(
      unclassified,
      `unclassified non-GET traffic during the walkthrough — check whether it writes: ${unclassified.join(', ')}`
    ).toEqual([]);
  });

  test('closing from a record surface still discards the session and leaves the ordinary workspace', async ({
    page,
    app,
    tutorial,
  }) => {
    /*
     * The exit case the console assertion above stops short of.
     *
     * A DEFECT WAS FOUND HERE AND IS DELIBERATELY NOT PINNED. Closing on step
     * three disposes the session while the browser is on `/record/<id>`, and that
     * record only ever existed inside the session — so it is gone. The record
     * surface nevertheless KEEPS RENDERING the full record: the h1, the "5 Fields
     * Need Your Confirmation" panel with its five real field paths, every field
     * group, and the workflow spine. Only the Assistant notices, and it says so
     * ("I cannot verify the current record state right now"); two background
     * fetches 404 in the console. So the screen presents a record that no longer
     * exists as current, and does not state the not-found condition it has
     * already discovered.
     *
     * This test therefore asserts ONLY what must hold under any correct design,
     * and does not assert the stale render — writing `expect(stale content)` would
     * turn a defect into a requirement, and whoever fixes it would have to delete
     * a passing test to do so. Reported instead.
     */
    await app.open(experiments);
    await startFromOffer(page);
    const session = tutorial.sessionsCreated()[0];
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await expect(mark(page)).toHaveAttribute('data-tutorial-step', 'record-readiness');
    await expect(page).toHaveURL(/\/record\//);

    await page.getByRole('button', { name: 'Close Tutorial' }).click();

    // The walkthrough chrome goes, and the chip stops claiming the example scope.
    await expect(mark(page)).toHaveCount(0);
    await expect(bar(page)).toHaveCount(0);
    await expect(chip(page)).toHaveText('Workspace');

    // The session really was discarded, checked at the API rather than inferred
    // from the screen — which is the point, since the screen is still showing it.
    await expect
      .poll(async () => (await tutorial.listInSession(session)).status, { timeout: 15_000 })
      .toBe(404);

    // And My Experiments is the ordinary empty workspace again — the examples did
    // not survive the session that held them.
    await app.open(experiments);
    await expect(page.getByRole('heading', { name: 'No experiments yet' })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('.exp-row')).toHaveCount(0);
  });
});

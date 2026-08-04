/**
 * The two workspace scopes, asserted as the app and the backend actually behave.
 * @interaction
 *
 * WHAT CHANGED UNDER THIS SUITE, in one paragraph, because every test below
 * exists because of it. The five built-in example records used to be
 * materialised into the ordinary workspace by `ensure_seeded()` on every read.
 * They are not. They exist only inside a worked-example session
 * (`POST /api/tutorial/sessions`), the ordinary workspace is permanently EMPTY,
 * and every record route resolves the scope from `X-Isaac-Tutorial-Session`:
 * absent → ordinary, malformed → 422, unknown → 404 and NEVER a fall back to
 * the ordinary scope.
 *
 * Nothing here mutates either scope. The two example-workspace operations are
 * exercised UNSCOPED, where their whole contract is that they refuse and write
 * nothing — which is asserted by re-reading the ordinary list afterwards rather
 * than by trusting the status code.
 */

import { API_BASE, SEED } from '../env';
import { TUTORIAL_SESSION_HEADER, readWorkedExampleSession } from '../worked-example';
import { expect, test } from '../fixtures';
import { SURFACES } from '../surfaces';

const ordinaryExperiments = SURFACES.find((s) => s.id === 'experiments')!;

/** A well-formed session id (`^[A-Za-z0-9_-]{16,64}$`) that names no session.
 *  Well-formed on purpose: a malformed id is rejected earlier, by shape, and
 *  would prove nothing about the unknown-session branch. */
const UNKNOWN_SESSION_ID = 'e2eUnknownSession-0000';
/** Wrong SHAPE (too short, and it contains a dot), so it names no session at all. */
const MALFORMED_SESSION_ID = 'nope.';

test.describe('@interaction the ordinary workspace', () => {
  test('renders its real empty state — no rows, and no promise it cannot keep', async ({ page, app }) => {
    await app.open(ordinaryExperiments);

    // NOT a placeholder and not a loading state: the permanent condition of this
    // deployment. Asserted as the reader's own words rather than by a CSS class
    // alone, so replacing the copy with something that over-promises fails here.
    await expect(page.getByRole('heading', { name: 'No experiments yet' })).toBeVisible();
    await expect(page.locator('.queue-empty-state')).toContainText(
      /cannot yet create or import a record/i
    );

    // Zero rows, and zero group headings. `.exp-row` is the queue's row element;
    // if a single one renders here, the seed has leaked back into the shared
    // scope and half this suite's ordinary-scope assertions become meaningless.
    await expect(page.locator('.exp-row')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /Needs Attention|Ready to Export/i })).toHaveCount(0);

    // The subcount states zero rather than being omitted.
    await expect(page.locator('.page-subcount')).toContainText(/0 experiments/i);

    // The two things a reader CAN do instead are offered and operable.
    await expect(page.getByRole('button', { name: 'Open Validator' })).toBeEnabled();
    /*
     * RE-POINTED, AND THE DESTINATION IS ASSERTED RATHER THAN THE LABEL ALONE.
     *
     * This control was labelled "Replay Tutorial" — the exact name of the button in
     * Settings that starts the walkthrough — while it only navigated, and navigated to
     * `/settings` with no `?tab=`, which `SettingsPage` resolves to `overview`: a tab
     * with no tutorial control on it. The label now names navigation
     * (`actionGoToHelpAndTutorial`, the same pair `LoadMaterials`'s refusal state
     * already used) and the landing is checked, because a name-only assertion is what
     * let the wrong destination ship.
     */
    const go = page.getByRole('button', { name: 'Go to Help & Tutorial' });
    await expect(go).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Replay Tutorial' })).toHaveCount(0);
    await go.click();
    await expect(page.getByRole('tab', { name: 'Help & Tutorial' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    await expect(page.getByRole('button', { name: 'Replay Tutorial' })).toBeVisible();
  });

  test('names itself "Workspace" in the mode chip, and claims nothing about records', async ({ page, app }) => {
    await app.open(ordinaryExperiments);

    const chip = page.locator('span.mode-chip');
    await expect(chip).toHaveCount(1);
    // The visible text. `Example workspace` is GONE: it asserted contents that
    // are not in this scope. A test that accepted either string would not have
    // caught that, so this is exact.
    await expect(chip).toHaveText('Workspace');

    // WCAG 2.5.3: the accessible name opens with the visible text, and it still
    // carries the two claims that hold unconditionally — plus, in this scope,
    // the honest statement that there are no records here.
    const name = await chip.getAttribute('aria-label');
    expect(name, 'the mode chip must have an accessible name').toBeTruthy();
    expect(name!.startsWith('Workspace'), `accessible name must open with the visible text: ${name}`).toBe(true);
    // RE-POINTED: `holds no records of its own` was an emptiness claim derived from
    // `sessionId === null` and measured by nothing — `list_experiments(None)` enumerates
    // whatever is on disk, and there is no startup migration, so a workspace that
    // survived this deploy holding the previously-seeded five would list them while the
    // chip denied it. The enforced claim is that the built-in examples cannot be in this
    // scope: `_materialise_seed` requires a `session_id` and has no normal-scope form.
    expect(name).toMatch(/the built-in example records are not in this workspace/i);
    expect(name).not.toMatch(/holds no records of its own/i);
    expect(name).toMatch(/file upload is refused/i);
    expect(name).toMatch(/no official institutional record is shown/i);
  });

  test('shows no worked-example chrome — not a disabled control, not a hint of one', async ({ page, app }) => {
    await app.open(ordinaryExperiments);

    // The bar is the ONE home of the two example-workspace controls, and it
    // renders only while a session is open.
    await expect(page.locator('aside.tutorial-session-bar')).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Reset Worked Example/i })).toHaveCount(0);
    // "Open the Worked Example" navigated to /load from this header and became a
    // dead control when `/demo/run` started requiring a session. It is gone from
    // here; `/load`'s own "Run the Worked Example" button is a different control
    // and is asserted separately.
    await expect(page.getByRole('button', { name: 'Open the Worked Example' })).toHaveCount(0);
  });

  test('a canonical example id is a real 404 here — the scope boundary, not a bug', async ({ page, app }) => {
    // This is the load-bearing consequence of the change: an id that resolves
    // inside a session must NOT resolve outside one. The app states it as the
    // "record not found" state rather than inventing a record or falling back.
    await app.goto(`/record/${SEED.partial}`);
    const alert = page.getByRole('alert');
    await expect(alert).toBeVisible({ timeout: 20_000 });
    await expect(alert).toContainText(/Record Not Found/i);
  });

  test('the same canonical id DOES resolve inside the worked-example session', async ({ page, app }) => {
    // The other half of the pair. Without it, the test above would be satisfied
    // by a build in which the record simply does not exist anywhere.
    await app.gotoExample(`/record/${SEED.partial}`);
    await expect(page.getByRole('heading', { name: 'Review Record' })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole('alert')).toHaveCount(0);
  });
});

test.describe('@interaction the scope header, at the API', () => {
  test('absent → the ordinary scope, which is empty', async ({ request }) => {
    const res = await request.get(`${API_BASE}/experiments`);
    expect(res.ok()).toBeTruthy();
    const body = (await res.json()) as { experiments?: unknown[] };
    expect(body.experiments ?? []).toEqual([]);
  });

  test('a live session → exactly the five built-in examples', async ({ request }) => {
    const { sessionId } = readWorkedExampleSession();
    const res = await request.get(`${API_BASE}/experiments`, {
      headers: { [TUTORIAL_SESSION_HEADER]: sessionId },
    });
    expect(res.ok()).toBeTruthy();
    const ids = (((await res.json()) as { experiments?: { id: string }[] }).experiments ?? []).map((e) => e.id);
    expect(ids.sort()).toEqual(Object.values(SEED).slice().sort());
  });

  test('unknown → 404, and NOT the ordinary workspace answered under a different name', async ({ request }) => {
    const res = await request.get(`${API_BASE}/experiments`, {
      headers: { [TUTORIAL_SESSION_HEADER]: UNKNOWN_SESSION_ID },
      failOnStatusCode: false,
    });
    // 404 rather than 200-with-nothing. The distinction is the whole point: a
    // silent fall back to the ordinary scope would let a client that lost its
    // session keep working, believing it was still inside one.
    expect(res.status(), 'an unknown but well-formed session must fail closed').toBe(404);
    const body = (await res.json()) as { error?: string };
    expect(body.error).toBe('tutorial_session_not_found');
  });

  test('malformed → 422, a different failure from "unknown"', async ({ request }) => {
    const res = await request.get(`${API_BASE}/experiments`, {
      headers: { [TUTORIAL_SESSION_HEADER]: MALFORMED_SESSION_ID },
      failOnStatusCode: false,
    });
    expect(res.status()).toBe(422);
    const body = (await res.json()) as { error?: string };
    expect(body.error).toBe('invalid_tutorial_session');
  });

  test('a disposed session stops resolving — 404, immediately', async ({ request }) => {
    // Its OWN session, created and destroyed here, so nothing shared is touched.
    const created = await request.post(`${API_BASE}/tutorial/sessions`);
    expect(created.status()).toBe(201);
    const id = ((await created.json()) as { session_id: string }).session_id;

    const before = await request.get(`${API_BASE}/experiments`, {
      headers: { [TUTORIAL_SESSION_HEADER]: id },
    });
    expect(before.ok()).toBeTruthy();

    const gone = await request.delete(`${API_BASE}/tutorial/sessions/${id}`);
    expect(gone.status()).toBe(204);

    const after = await request.get(`${API_BASE}/experiments`, {
      headers: { [TUTORIAL_SESSION_HEADER]: id },
      failOnStatusCode: false,
    });
    expect(after.status(), 'a disposed session must be indistinguishable from one that never existed').toBe(404);

    // IDEMPOTENT: discarding it again succeeds, because the postcondition the
    // caller asked for already holds.
    const again = await request.delete(`${API_BASE}/tutorial/sessions/${id}`);
    expect(again.status()).toBe(204);
  });
});

test.describe('@interaction the example-workspace operations refuse outside a session', () => {
  for (const op of ['run', 'reset'] as const) {
    test(`POST /api/demo/${op} → 409 tutorial_scope_required, and writes nothing`, async ({ request }) => {
      const res = await request.post(`${API_BASE}/demo/${op}`, {
        headers: { 'content-type': 'application/json' },
        data: op === 'run' ? { mode: 'draft_only' } : { mode: 'preview' },
        failOnStatusCode: false,
      });
      expect(res.status()).toBe(409);
      const body = (await res.json()) as { error?: string };
      // The typed discriminator, not just "a 4xx". `demo_target_drifted` is a
      // different 409 with a different meaning and a different remedy.
      expect(body.error).toBe('tutorial_scope_required');

      // The refusal's real claim is "nothing was written", and a status code
      // cannot establish that. Re-read the scope.
      const after = await request.get(`${API_BASE}/experiments`);
      expect(((await after.json()) as { experiments?: unknown[] }).experiments ?? []).toEqual([]);
    });
  }

  test('Load Materials keeps the ordinary workspace empty when its example button is pressed', async ({
    page,
    app,
    request,
  }) => {
    /*
     * WHAT THIS DELIBERATELY DOES NOT ASSERT, and why the gap is recorded here
     * rather than pinned as correct.
     *
     * `POST /api/demo/run` answers 409 `tutorial_scope_required` outside a
     * session. `LoadMaterials.startDemo` recognises exactly ONE 409 —
     * `demo_target_drifted` — and everything else falls through to
     * `{ name: 'error' }`, which renders `BackendDown`. So pressing this button
     * in the ordinary workspace currently shows "Backend Not Running" about a
     * backend that answered correctly and instantly. That is a UI honesty gap
     * (reported, not fixed here), and a spec that asserted the "Backend Not
     * Running" text would ratify it — the next person to fix the copy would
     * then have to delete a passing test to do so.
     *
     * What IS asserted is the invariant that must hold whatever the screen says:
     * the refusal wrote nothing, so the ordinary workspace is still empty.
     */
    await app.goto('/load');
    const run = page.getByRole('button', { name: 'Run the Worked Example' });
    await expect(run).toBeEnabled();
    await run.click();

    // Something is stated — the screen does not sit silently as though the
    // press did nothing. (Which state it is, is the gap described above.)
    await expect(page.getByRole('alert').first()).toBeVisible({ timeout: 20_000 });

    const after = await request.get(`${API_BASE}/experiments`);
    expect(
      ((await after.json()) as { experiments?: unknown[] }).experiments ?? [],
      'the refused example run must not have written into the ordinary workspace'
    ).toEqual([]);
  });
});

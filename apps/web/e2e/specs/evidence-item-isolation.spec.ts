/**
 * ONE unreadable evidence item must degrade to ITSELF, in a real browser.
 * @interaction
 *
 * WHICH SUITE THIS IS IN, AND WHY. The read-only suite, tagged `@interaction`
 * (so it runs at 1280x800 and 375x812, not five times), because it MUTATES
 * NOTHING: the malformed entry is injected into the browser's own response for
 * ONE request via `page.route`, exactly as `specs/states.spec.ts` produces its
 * failure states. No record is answered, exported, reset or written, so the five
 * viewport projects sharing this backend and this worked-example session are
 * unaffected. It is deliberately NOT in the mutation suite: nothing here needs a
 * private workspace, and putting it there would cost a second backend to prove a
 * rendering contract.
 *
 * WHAT IT PROVES THAT THE UNIT TESTS CANNOT. The jsdom tests assert the same
 * contract, but the failure being guarded against is a REAL React unmount with
 * no ErrorBoundary — measured on `77820bf` as an empty `document.body` in a real
 * page, and separately as the "Backend Not Running" alert appearing because one
 * entry in one record could not be iterated. Both are whole-screen outcomes, and
 * a whole screen is what a browser is for.
 */

import { API_BASE, SEED } from '../env';
import { expect, test } from '../fixtures';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';

const RECORD = SEED.partial;
const EVIDENCE_URL = `${API_BASE}/experiments/${RECORD}/evidence`;
const EVIDENCE_PATH = `/record/${RECORD}/evidence`;

/**
 * Serve the REAL evidence trail for this record with `extra` appended.
 *
 * The request is refetched from the live backend (carrying the worked-example
 * scope header explicitly, because this handler ends the route chain), so every
 * VALID entry the assertions below check is genuine server-derived data — the
 * spec fakes exactly one thing, which is the malformed item under test.
 */
async function appendEntry(
  page: import('@playwright/test').Page,
  sessionId: string,
  extra: Record<string, unknown>
) {
  await page.route(EVIDENCE_URL, async (route) => {
    const response = await route.fetch({
      headers: { ...route.request().headers(), [TUTORIAL_SESSION_HEADER]: sessionId },
    });
    const body = (await response.json()) as { evidence: unknown[] };
    await route.fulfill({
      response,
      json: { ...body, evidence: [...body.evidence, extra] },
    });
  });
}

test('@interaction an unreadable evidence entry is shown as unavailable, and the rest of the trail is not', async ({
  page,
  app,
}) => {
  const sessionId = await app.enterExampleScope();
  // Registered AFTER the scope handler, so it runs first and ends the chain.
  await appendEntry(page, sessionId, {
    // Exactly the shape the backend serves for a sidecar entry whose stored
    // payload is not a list (`serialize._trail_entry`). The path is deliberately
    // one this record does NOT already carry: a duplicate key would be selected
    // by the screen's `find(e => e.key === selectedKey)` on the FIRST match, and
    // the spec would silently assert against the healthy twin.
    path: 'system.facility.unreadable_probe',
    value: null,
    status: 'unavailable',
    evidence: [],
    unavailable: true,
    unavailable_reason:
      'the stored evidence for this entry is a number, not a list of evidence entries',
  });

  await page.goto(EVIDENCE_PATH, { waitUntil: 'domcontentloaded' });

  // 1. The screen is THERE. It used to be an empty document or an error panel.
  //    The TRAIL is waited for rather than the heading: `EvidenceExplorer`
  //    renders the same `sr-only` h1 in its loading branch, so a heading
  //    assertion alone passes before any data has landed.
  const trail = page.locator('aside.trail');
  await expect(trail).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Evidence & File Preview' })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Backend Not Running');

  // 2. The valid entries are all still listed — measured against the trail this
  //    record really has, not a hard-coded number.
  await expect(trail.locator('.trail-entry.unavailable')).toHaveCount(1);
  const total = await trail.locator('.trail-key').count();
  expect(total).toBeGreaterThan(1);
  // Every other row rendered normally: no unavailable badge, and their keys are
  // present. (`total - 1` valid rows, so nothing was dropped to make room.)
  await expect(trail.locator('.trail-entry:not(.unavailable)')).toHaveCount(total - 1);

  // 3. The failed one is visible under its own key, and says so in TEXT.
  const badRow = trail.locator('.trail-entry.unavailable');
  await expect(badRow).toContainText('system.facility.unreadable_probe');
  await expect(badRow).toContainText('unavailable');

  // 4. Selecting it states the real cause — never a generic failure, and never a
  //    fabricated citation in place of the one that could not be read.
  await badRow.click();
  const detail = page.locator('.sidecar-entry');
  await expect(detail).toContainText(
    'the stored evidence for this entry is a number, not a list of evidence entries'
  );
  await expect(detail).not.toContainText('No citations recorded.');
  await expect(detail.locator('.sidecar-ev')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText(/something went wrong/i);

  // 5. And a VALID entry still works after the bad one — selection, provenance
  //    and the source preview are unaffected by its neighbour.
  const firstValid = trail.locator('.trail-entry:not(.unavailable)').first();
  const validKey = (await firstValid.locator('.trail-key').textContent())!.trim();
  await firstValid.click();
  await expect(page.locator('.preview-prov-key')).toHaveText(validKey);
  await expect(page.locator('.preview-prov-text')).not.toContainText('unavailable');
});

test('@interaction a wrong-shaped entry the client has never seen does not blank the screen', async ({
  page,
  app,
}) => {
  // The rawest form of the measured defect: an entry whose `evidence` is not a
  // list at all, and a source type this build does not enumerate. On `77820bf`
  // the first produced the "Backend Not Running" alert (the bundle promise
  // rejected inside `citedSourceFiles`) and the second produced an EMPTY DOM
  // (React: "Element type is invalid"). No backend marking helps here — the
  // client has to survive the shape on its own.
  const sessionId = await app.enterExampleScope();
  await appendEntry(page, sessionId, {
    path: 'system.raw_malformed',
    value: 'still readable',
    status: 'verified',
    evidence: 7,
  });

  await page.goto(EVIDENCE_PATH, { waitUntil: 'domcontentloaded' });

  const trail = page.locator('aside.trail');
  await expect(trail).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Evidence & File Preview' })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(trail.locator('.trail-key', { hasText: 'system.raw_malformed' })).toHaveCount(1);
  await expect(trail.locator('.trail-entry.unavailable')).toHaveCount(1);
  // Its readable half is kept: the value was never the unreadable part.
  await expect(trail.locator('.trail-entry.unavailable')).toContainText('system.raw_malformed');
});

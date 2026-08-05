/**
 * R4 · VALIDATION through the real UI against the real validator.
 *
 * The surface under test is the Standalone Validator on Governance & Safety. It is
 * the one place a reader hands the app a document and is given a verdict, and it
 * calls `POST /api/validate/record`, which runs the SAME `validate_official` over
 * the SAME vendored schema that gates export. So a defect here is a defect in how
 * this app reports the gate.
 *
 * WHY THIS SPEC OPTS OUT OF THE SCOPE FIXTURES. It writes nothing — no record, no
 * workspace, no session — so it imports `test` straight from `@playwright/test`.
 * Neither `fixtures.ts`'s shared session nor `own-session-fixtures.ts`'s private one
 * would give it anything, and taking a scope it does not need would hide the fact
 * that this route touches no workspace at all (the server's own contract: the body
 * "is never written anywhere and its content is never logged").
 *
 * The candidate documents below are SYNTHETIC and unmistakably so — a 2099
 * timestamp and a record id from the committed synthetic seed range.
 */

import { expect, test, type Page } from '@playwright/test';

// --- the candidate documents ------------------------------------------------
//
// ONE record, in two states: `BROKEN_ONE_ERROR` is `REPAIRED` with the descriptor's
// `uncertainty` removed. That is deliberate — the repair test must change exactly
// the thing the validator complained about and nothing else, or "repairing the
// reported error fixed it" is not what was demonstrated.

const DESCRIPTOR = {
  name: 'xanes_inflection_point_energy',
  kind: 'absolute',
  source: 'manual',
  value: 9001.2,
  unit: 'eV',
};

const UNCERTAINTY = { sigma: 0.01, unit: 'eV', basis: 'reported' };

function candidate(descriptor: Record<string, unknown>): Record<string, unknown> {
  return {
    isaac_record_version: '1.05',
    record_id: '01SYNTHXANESSEED0000000099',
    record_type: 'evidence',
    record_domain: 'characterization',
    source_type: 'facility',
    timestamps: { created_utc: '2099-03-05T20:15:00Z' },
    descriptors: {
      outputs: [
        {
          label: 'synthetic_probe',
          generated_utc: '2099-03-05T21:00:00Z',
          generated_by: { agent: 'isaac-browser-spec', version: '0.1' },
          descriptors: [descriptor],
        },
      ],
    },
  };
}

const BROKEN_ONE_ERROR = candidate(DESCRIPTOR);
const REPAIRED = candidate({ ...DESCRIPTOR, uncertainty: UNCERTAINTY });

/** Six errors, every one of them at the same `$` path — the case that would expose
 *  a list keyed on path alone. */
const BROKEN_SIX_ERRORS = { isaac_record_version: '1.05' };

/** A different six-error document, for the "no stale rows" check. */
const BROKEN_SIX_ERRORS_ALT = { isaac_record_version: '1.05', record_id: 'not-a-ulid' };

const json = (value: unknown) => JSON.stringify(value, null, 2);

async function openValidator(page: Page) {
  await page.goto('/governance?tab=validator');
  await expect(page.getByRole('heading', { name: 'Standalone Validator' })).toBeVisible();
}

const textarea = (page: Page) => page.getByLabel('Candidate record (JSON)');
const validateButton = (page: Page) => page.getByRole('button', { name: 'Validate', exact: true });
const verdict = (page: Page) => page.locator('.verdict');
const errorRows = (page: Page) => page.locator('.schema-error-row');

/** Count POSTs the PAGE actually made to the validator route. */
function countValidatorPosts(page: Page): () => number {
  let n = 0;
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().includes('/validate/record')) n += 1;
  });
  return () => n;
}

test.describe('R4 · standalone validation', () => {
  test('Validate sends a real request and renders the ONE reported error with its own path', async ({
    page,
  }) => {
    const posts = countValidatorPosts(page);
    await openValidator(page);

    // Nothing has been checked yet, and the screen says exactly that rather than
    // showing a stale or default verdict.
    await expect(page.locator('.rec-val-empty')).toBeVisible();
    await expect(verdict(page)).toHaveCount(0);

    await textarea(page).fill(json(BROKEN_ONE_ERROR));
    await validateButton(page).click();

    // A real request left the page — a client-side check would prove nothing about
    // the schema this app actually gates on.
    await expect.poll(posts, { message: 'no POST to /validate/record was observed' }).toBe(1);

    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation FAIL');
    // The error is rendered AS A PAIR — the locating path and the message — because a
    // message without its path cannot be acted on.
    await expect(errorRows(page)).toHaveCount(1);
    await expect(errorRows(page).first()).toContainText('descriptors.outputs.0.descriptors.0');
    await expect(errorRows(page).first()).toContainText("'uncertainty' is a required property");
  });

  test('repairing exactly the reported error and re-running turns FAIL into PASS', async ({ page }) => {
    const posts = countValidatorPosts(page);
    await openValidator(page);

    await textarea(page).fill(json(BROKEN_ONE_ERROR));
    await validateButton(page).click();
    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation FAIL');

    // The repair adds `uncertainty` and changes nothing else.
    await textarea(page).fill(json(REPAIRED));
    await validateButton(page).click();

    await expect.poll(posts).toBe(2);
    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation PASS');
    await expect(verdict(page)).toContainText('Valid against official ISAAC schema v1.05.');
    await expect(errorRows(page), 'a PASS must carry no schema errors').toHaveCount(0);
    await expect(page.locator('.rec-val-schema-line')).toContainText(
      'Checked against official ISAAC schema v1.05'
    );
  });

  test('advisory notes are shown on a PASS and state that they do not change the verdict', async ({
    page,
  }) => {
    /*
     * The property, and the reason it is asserted on a PASS rather than a FAIL: the
     * advisory tier is NON-GATING, and the only way to demonstrate that is a document
     * the schema accepts while the advisory tier still has something to say. If a
     * warning could turn a PASS into a FAIL this test fails; so would a build that
     * quietly stopped rendering advisories, which is the state the route was in
     * before the tier was added here (a record with no measurement block came back an
     * unqualified PASS).
     */
    await openValidator(page);
    await textarea(page).fill(json(REPAIRED));
    await validateButton(page).click();

    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation PASS');

    const advisory = page.locator('.rec-val-advisory');
    await expect(advisory).toBeVisible();
    await expect(advisory.getByRole('heading')).toContainText('do not affect the verdict');

    // A SET of the places advised about, not a count: a count cannot tell "the tier
    // reported less" from "the screen rendered less".
    const where = await advisory.locator('.rec-val-advisory-where').allTextContents();
    expect(new Set(where.map((w) => w.trim()))).toEqual(new Set(['links', 'measurement']));
    await expect(advisory).toContainText('contains no measured data');
  });

  test('six errors sharing one path all render — none is collapsed away', async ({ page }) => {
    /*
     * `VerdictCard` keys its error rows on `err.path`, and this document produces SIX
     * errors whose path is all `$`. A list keyed on a non-unique value is the classic
     * way for issues to disappear silently, and disappearing schema errors on the
     * surface that reports the export gate would be the worst kind of quiet.
     */
    await openValidator(page);
    await textarea(page).fill(json(BROKEN_SIX_ERRORS));
    await validateButton(page).click();

    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation FAIL');
    await expect(verdict(page)).toContainText('6 errors');

    const rendered = (await errorRows(page).allTextContents()).map((t) => t.trim());
    // The SET of properties named, which is what a reader needs, rather than the row
    // count on its own.
    const named = new Set(
      rendered.map((t) => /'([a-z_]+)' is a required property/.exec(t)?.[1]).filter(Boolean)
    );
    expect(named).toEqual(
      new Set(['record_id', 'record_type', 'record_domain', 'source_type', 'timestamps', 'descriptors'])
    );
    expect(rendered).toHaveLength(6);
  });

  test('two runs over the same candidate report the same errors in the same order', async ({
    page,
  }) => {
    await openValidator(page);
    await textarea(page).fill(json(BROKEN_SIX_ERRORS));
    await validateButton(page).click();
    await expect(errorRows(page)).toHaveCount(6);
    const first = (await errorRows(page).allTextContents()).map((t) => t.replace(/\s+/g, ' ').trim());

    // Re-run the identical candidate. (Re-typing the same text is what a reader does;
    // it also proves the second run is a fresh request rather than a cached render.)
    await textarea(page).fill(json(BROKEN_SIX_ERRORS));
    await validateButton(page).click();
    await expect(errorRows(page)).toHaveCount(6);
    const second = (await errorRows(page).allTextContents()).map((t) => t.replace(/\s+/g, ' ').trim());

    expect(second, 'the validator must be deterministic in content AND in order').toEqual(first);
  });

  test('editing the candidate clears the previous verdict instead of leaving it standing', async ({
    page,
  }) => {
    await openValidator(page);
    await textarea(page).fill(json(BROKEN_ONE_ERROR));
    await validateButton(page).click();
    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation FAIL');

    // One keystroke is enough: the verdict on screen is now about a document that is
    // no longer the one in the box.
    await textarea(page).press('End');
    await textarea(page).press('Space');

    await expect(verdict(page), 'a verdict must not outlive the document it judged').toHaveCount(0);
    await expect(errorRows(page)).toHaveCount(0);
    await expect(page.locator('.rec-val-empty')).toBeVisible();
  });

  test('a re-run over a DIFFERENT candidate replaces every error row — no row survives from the last run', async ({
    page,
  }) => {
    await openValidator(page);
    await textarea(page).fill(json(BROKEN_SIX_ERRORS));
    await validateButton(page).click();
    await expect(errorRows(page)).toHaveCount(6);
    await expect(errorRows(page).filter({ hasText: "'record_id' is a required property" })).toHaveCount(1);

    await textarea(page).fill(json(BROKEN_SIX_ERRORS_ALT));
    await validateButton(page).click();

    // The second document HAS a `record_id`, so that error must be gone rather than
    // reused — the case duplicate React keys over the shared `$` path could get wrong.
    await expect(
      errorRows(page).filter({ hasText: "'record_id' is a required property" }),
      'an error from the previous candidate is still on screen'
    ).toHaveCount(0);
    await expect(errorRows(page).filter({ hasText: 'does not match' })).toHaveCount(1);
  });

  test('an error message quoting the candidate is rendered as TEXT — no markup runs, no server path leaks', async ({
    page,
  }) => {
    /*
     * The validator echoes the offending value back inside the message. That is
     * useful and it is also the injection surface: the string travels from the
     * reader's textarea, through Python, into the DOM. Both halves are asserted —
     * that the payload is visible as characters, and that it did not become an
     * element or run.
     */
    const payload = '<img src=x onerror="window.__isaacXss=1">';
    await openValidator(page);
    await textarea(page).fill(json({ ...BROKEN_ONE_ERROR, record_id: payload }));
    await validateButton(page).click();

    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation FAIL');
    const row = errorRows(page).filter({ hasText: 'record_id' });
    await expect(row).toHaveCount(1);
    await expect(row, 'the offending value must be shown so it can be recognised').toContainText(payload);

    expect(await page.locator('img[src="x"]').count(), 'the payload became an element').toBe(0);
    expect(await page.evaluate(() => (window as unknown as { __isaacXss?: number }).__isaacXss)).toBeUndefined();

    // And nothing internal rode along with the message.
    const shown = await page.locator('.rec-val-result').innerText();
    for (const marker of ['Traceback', 'routes.py', 'official.py', 'site-packages', '/Users/', '/private/tmp', '/app/']) {
      expect(shown, `${marker} leaked into a validator message`).not.toContain(marker);
    }
  });

  test('a candidate that is not a JSON object is refused with a typed message, not a verdict', async ({
    page,
  }) => {
    /*
     * The refusal has to be distinguishable from a FAIL. A JSON array is well-formed
     * JSON, so the client-side parse succeeds and the server answers 422 — and the
     * screen must NOT render that as "invalid against the official schema", which
     * would be a verdict nobody computed.
     */
    await openValidator(page);
    await textarea(page).fill('[1, 2, 3]');
    await validateButton(page).click();

    const rejected = page.locator('.rec-val-rejected');
    await expect(rejected).toBeVisible();
    await expect(rejected).toContainText('must be a JSON object');
    await expect(verdict(page), 'a refusal is not a verdict').toHaveCount(0);
    await expect(errorRows(page)).toHaveCount(0);
  });

  test('malformed JSON is refused in the browser and never reaches the validator', async ({ page }) => {
    const posts = countValidatorPosts(page);
    await openValidator(page);
    await textarea(page).fill('{ "isaac_record_version": "1.05", }');
    await validateButton(page).click();

    await expect(page.locator('.rec-val-rejected')).toContainText("isn't valid JSON");
    await expect(verdict(page)).toHaveCount(0);
    expect(posts(), 'unparseable input must not be sent to the server at all').toBe(0);
  });
});

/**
 * RECORD INFO + RELATIONSHIPS, in a real browser, against the real backend.
 * @interaction
 *
 * WHICH SUITE THIS IS IN, AND WHY IT IS NOT THE MUTATION ONE. The read-only
 * suite, tagged `@interaction` so it runs at 1280x800 and 375x812 rather than
 * five times. It WRITES NOTHING: both sections are read surfaces, the only
 * gesture here is expanding a collapsed card, and the only requests the page
 * makes are the record bundle's own GETs. It would not belong in
 * `playwright.mutation.config.ts` even if that were free — nothing here needs a
 * private workspace, and the read-only suite's five projects share this backend
 * and this worked-example session precisely because no spec in it changes them.
 *
 * (It could not have been a link WRITE in any suite: no operation in this API
 * writes a record's `links`. That is the finding this slice reports rather than
 * works around, and the last assertion below pins the product's own statement of
 * it.)
 *
 * WHAT IT PROVES THAT THE JSDOM TESTS CANNOT. The unit tests drive both panels
 * with hand-built artifact payloads. This one reads the REAL exported record of
 * the seeded `done` experiment through the real `/artifacts` route, so it proves
 * the two things a stub cannot: that the values a live official record actually
 * carries land in the rows addressed to them, and that a scientist can reach the
 * section from the keyboard.
 */

import { SEED } from '../env';
import { expect, test } from '../fixtures';

const EXPORTED = `/record/${SEED.done}`;
const DRAFT = `/record/${SEED.partial}`;

/** The section card for one header title. */
const section = (page: import('@playwright/test').Page, name: RegExp) =>
  page.locator('section.field-group').filter({ has: page.getByRole('button', { name }) });

test('@interaction an exported record shows its own identity, and the stamp offers no editor', async ({
  page,
  app,
}) => {
  await app.enterExampleScope();
  await page.goto(EXPORTED, { waitUntil: 'domcontentloaded' });

  const card = section(page, /^Record Info/);
  const header = card.getByRole('button', { name: /^Record Info/ });
  await expect(header).toBeVisible();

  // Collapsed on arrival — progressive disclosure, and the body is not merely
  // hidden, it is not in the document.
  await expect(header).toHaveAttribute('aria-expanded', 'false');
  await expect(card.locator('[data-record-info-path]')).toHaveCount(0);

  // Reachable and operable from the keyboard, not only by pointer.
  await header.focus();
  await page.keyboard.press('Enter');
  await expect(header).toHaveAttribute('aria-expanded', 'true');

  // The six rows the official schema requires, all present and addressed.
  await expect(card.locator('[data-record-info-path]')).toHaveCount(6);

  // Real values from the real exported record. `isaac_record_version` is a
  // schema `const`, so it is the one value that can be asserted exactly without
  // this spec restating the fixture's science.
  const version = card.locator('[data-record-info-path="isaac_record_version"]');
  await expect(version).toContainText('1.05');
  await expect(version).toContainText('Record stamp');

  const id = card.locator('[data-record-info-path="record_id"]');
  await expect(id).toContainText(SEED.done);

  // The created stamp reads as a stamp, and there is NO control to change it —
  // not a disabled one, none. `timestamps.created_utc` is written by the
  // exporter (`export.py` `setdefault`), and inviting an edit would misdescribe
  // who owns the value.
  const created = card.locator('[data-record-info-path="timestamps.created_utc"]');
  await expect(created).toContainText('Record stamp');
  await expect(created).toContainText('Written by the exporter');
  await expect(created.locator('input, textarea, select, button')).toHaveCount(0);

  // The classification trio is read from the record here, so it is NOT wearing
  // the pre-export "not read on this screen" state.
  await expect(card.locator('[data-record-info-path="record_type"]')).not.toContainText(
    'not read on this screen'
  );
});

test('@interaction a draft says what is not written yet without claiming anything is missing', async ({
  page,
  app,
}) => {
  await app.enterExampleScope();
  await page.goto(DRAFT, { waitUntil: 'domcontentloaded' });

  const card = section(page, /^Record Info/);
  await card.getByRole('button', { name: /^Record Info/ }).click();

  await expect(card.locator('[data-record-info-path="record_id"]')).toContainText(
    'not written yet'
  );
  // A different claim, deliberately: the value is real on the draft, and this
  // client simply does not fetch it.
  await expect(card.locator('[data-record-info-path="record_type"]')).toContainText(
    'not read on this screen'
  );
});

test('@interaction Relationships states what it can see, and that links cannot be authored here', async ({
  page,
  app,
}) => {
  await app.enterExampleScope();
  await page.goto(DRAFT, { waitUntil: 'domcontentloaded' });

  const card = section(page, /^Relationships/);
  const header = card.getByRole('button', { name: /^Relationships/ });
  await expect(header).toHaveAttribute('aria-expanded', 'false');
  await header.click();

  // An unexported record's relationships are unknown, and that is said as
  // unknown — never as "this record declares none".
  await expect(card).toContainText('not the same as the record declaring none');

  // The authoring boundary is stated in words, and there is no dead control
  // beside it: the header is the only button in the card.
  await expect(card).toContainText('no operation in this API writes a record’s');
  await expect(card.getByRole('button')).toHaveCount(1);
  await expect(card.locator('input, textarea, select')).toHaveCount(0);
});

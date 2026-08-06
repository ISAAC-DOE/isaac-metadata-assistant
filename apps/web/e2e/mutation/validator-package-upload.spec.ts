/**
 * The COMMITTED validator QA package, driven through the real UPLOAD control.
 *
 * ── What this covers that nothing else does ─────────────────────────────────
 *
 * Two artifacts already guard `qa/validator-upload-package/`, and both stop short
 * of the thing an operator actually does:
 *
 *   · `tests/test_validator_qa_package.py` re-measures `validate_official` over
 *     the loose files and cross-checks MANIFEST.json against UPLOAD-GUIDE.md. Its
 *     own docstring is explicit that it "says nothing about what the UI renders"
 *     and never exercises `POST /api/validate/record`.
 *   · `validation.spec.ts` (this directory) drives the validator through the real
 *     route, but every one of its ten tests types into the TEXTAREA. The file
 *     input, the `accept` filter, re-selecting the same file, and switching files
 *     are untouched there — and the documents it uses are three hand-built
 *     objects, not the eighteen files a human is handed.
 *
 * So this spec is the missing join: the eighteen COMMITTED files, through the
 * real file input, against the real backend, asserting what the SCREEN renders.
 * If MANIFEST.json promises an operator a verdict, this proves the app delivers
 * that verdict on that file.
 *
 * ── Why it is in the MUTATION suite, given the validator mutates nothing ────
 *
 * It genuinely mutates nothing — `POST /api/validate/record` takes the candidate
 * in the body, writes nowhere, and this spec (like `validation.spec.ts`) takes no
 * scope fixture. On contract alone it would belong in the read-only suite. Three
 * measured reasons put it here instead:
 *
 *   1. The read-only suite runs FIVE viewport projects off ONE shared backend and
 *      `fullyParallel: true`. An eighteen-file sweep is eighteen serial uploads
 *      plus sixteen round trips; multiplying that by the projects a `@responsive`
 *      or `@interaction` tag selects buys no signal, because a verdict is not
 *      viewport-dependent. The one property here that IS width-dependent is
 *      asserted directly, by resizing inside its own test.
 *   2. That suite's a11y ratchet is an EXACT per-`surface@project` node count.
 *      The `validator` surface already exists in `e2e/surfaces.ts`, so the
 *      Validator is already swept by axe at all five widths — this spec adds no
 *      surface and therefore must not, and does not, move
 *      `A11Y_BASELINE_TOTAL_NODES`.
 *   3. Validator browser coverage already lives here. Splitting it across two
 *      suites would mean a future change to `RecordValidator.tsx` has two
 *      unrelated places to look.
 *
 * ── The eighteen files are not real data, and that is verified, not assumed ──
 *
 * All eighteen — the seventeen records and the `.txt` — state in their own text
 * that they were "Constructed by hand for validator exercise" and "carry no
 * measurement provenance", pinned by
 * `test_every_shipped_fixture_states_its_own_provenance_in_its_own_text`. The
 * optional `attribution` block is absent from all eighteen, pinned by
 * `test_no_qa_record_carries_an_attribution_block`. Both live in
 * `tests/test_validator_qa_package.py`.
 *
 * Two things this does NOT claim. It was 17 of 18 until the `.txt` was rewritten:
 * that file read as a genuine logbook transcription and carried no note at all,
 * and nothing failed, because the note convention was unasserted until the test
 * named above existed. And the values themselves are unverifiable by any test —
 * "illustrative" is a statement the files make, not a property a machine can
 * confirm. What IS mechanically true here: nothing in this suite reads a database,
 * and MANIFEST.json records `production_derived_content: "none"`.
 *
 * ── The sweep is DATA-DRIVEN, so it is guarded against becoming vacuous ─────
 *
 * The per-file tests are generated from MANIFEST.json. A manifest that lost
 * entries would silently generate fewer tests, and a green run would mean less
 * than it did before — the classic way a data-driven suite rots. `EXPECTED_FILES`
 * below is an independent, literal SET of the eighteen names, and the first test
 * asserts the manifest still describes exactly that set. Break the manifest and
 * that test names what went missing instead of the suite quietly shrinking.
 */

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { expect, test, type Page } from '@playwright/test';

// --- locating the committed package ------------------------------------------
//
// Walked up from the working directory rather than derived from `import.meta.url`
// so it holds whether Playwright is invoked from `apps/web` (the documented way)
// or from the repository root (the way CI does it). A miss THROWS: a spec that
// silently found no package would report success for zero coverage.

function findPackageDir(): string {
  const relative = join('qa', 'validator-upload-package');
  let dir = resolve(process.cwd());
  for (;;) {
    const candidate = join(dir, relative);
    if (existsSync(join(candidate, 'MANIFEST.json'))) return candidate;
    const parent = dirname(dir);
    if (parent === dir) {
      throw new Error(
        `could not find ${relative}/MANIFEST.json in any ancestor of ${process.cwd()}. ` +
          'This spec drives the COMMITTED QA package; without it there is nothing to test.'
      );
    }
    dir = parent;
  }
}

const PACKAGE_DIR = findPackageDir();

/** The subset of MANIFEST.json this spec reads. Narrow on purpose — a wider type
 *  would invite asserting fields the manifest does not promise to keep. */
interface ManifestEntry {
  readonly id: number;
  readonly filename: string;
  readonly intended_outcome: string;
  readonly measured_matches_intent?: boolean;
  readonly measured_validator_result: {
    readonly parsed: boolean;
    readonly ok: boolean | null;
    readonly error_count?: number | null;
    readonly first_error_path?: string | null;
    readonly first_error_message?: string | null;
    readonly advisory_warnings?: readonly string[];
  };
}

const MANIFEST = JSON.parse(
  readFileSync(join(PACKAGE_DIR, 'MANIFEST.json'), 'utf8')
) as { files: readonly ManifestEntry[] };

const ENTRIES = MANIFEST.files;

/**
 * The eighteen names this spec claims to cover, written out rather than counted.
 *
 * A SET, not a length: `toHaveLength(18)` would stay green if a file were
 * swapped for a different one, which is exactly the drift that would leave an
 * operator following a row for a file nobody exercises.
 */
const EXPECTED_FILES = new Set([
  'complete-valid-record.json',
  'missing-required-information.json',
  'missing-nested-information.json',
  'missing-conditional-information.json',
  'invalid-date-time.json',
  'empty-measurement-series.json',
  'missing-evidence.json',
  'missing-confirmation.json',
  'invalid-controlled-value.json',
  'invalid-field-type.json',
  'unknown-field.json',
  'multiple-issues.json',
  'unicode-and-escaping.json',
  'large-valid-record.json',
  'malformed-json.json',
  'unsupported-file.txt',
  'duplicate-of-complete-valid-record.json',
  'repairable-record.json',
]);

/** Files the SCREEN can obtain a verdict for — the ones that parse client-side. */
const PARSEABLE = ENTRIES.filter((e) => e.measured_validator_result.parsed);
/** Files the screen refuses before any request leaves the browser. */
const UNPARSEABLE = ENTRIES.filter((e) => !e.measured_validator_result.parsed);

const filePath = (name: string) => join(PACKAGE_DIR, name);
const fileText = (name: string) => readFileSync(filePath(name), 'utf8');

/**
 * Markers that must never ride along with a validator message. The offending
 * VALUE is echoed back on purpose (an operator has to recognise it); the server's
 * internals are a different matter. Checked on every one of the sixteen real
 * files, not on a single crafted payload.
 */
const LEAK_MARKERS = [
  'Traceback',
  'routes.py',
  'official.py',
  'site-packages',
  '/Users/',
  '/private/tmp',
  '/app/',
];

// --- locators -----------------------------------------------------------------

const textarea = (page: Page) => page.getByLabel('Candidate record (JSON)');
const fileInput = (page: Page) => page.getByLabel('Upload a candidate ISAAC record (JSON)');
const uploadButton = (page: Page) => page.getByRole('button', { name: 'Upload JSON File' });
const validateButton = (page: Page) => page.getByRole('button', { name: 'Validate', exact: true });
const verdict = (page: Page) => page.locator('.verdict');
const errorRows = (page: Page) => page.locator('.schema-error-row');
const rejection = (page: Page) => page.locator('.rec-val-rejected');
const advisory = (page: Page) => page.locator('.rec-val-advisory');

async function openValidator(page: Page) {
  await page.goto('/governance?tab=validator');
  await expect(page.getByRole('heading', { name: 'Standalone Validator' })).toBeVisible();
  await expect(page.locator('.rec-val-empty')).toBeVisible();
}

/** Choose a package file through the real file input and wait for it to load. */
async function upload(page: Page, name: string) {
  await fileInput(page).setInputFiles(filePath(name));
  // The component reads the file asynchronously, so the assertion is on the box
  // having actually received the bytes rather than on the input having been set.
  await expect(textarea(page)).not.toHaveValue('');
}

/** Count POSTs the PAGE really made to the validator route. */
function countValidatorPosts(page: Page): () => number {
  let n = 0;
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().includes('/validate/record')) n += 1;
  });
  return () => n;
}

// --- the sweep ----------------------------------------------------------------

test.describe('the committed validator QA package, through the upload control', () => {
  test('MANIFEST.json still describes exactly the eighteen files this spec covers', () => {
    /*
     * Guards the sweep below against becoming vacuous. Every per-file test is
     * generated from the manifest, so a manifest that lost, renamed or gained an
     * entry would change what this file tests WITHOUT any test turning red. This
     * one turns red, and names the difference.
     */
    const described = new Set(ENTRIES.map((e) => e.filename));
    expect(described, 'MANIFEST.json no longer describes the set this spec sweeps').toEqual(
      EXPECTED_FILES
    );

    const missingOnDisk = [...described].filter((n) => !existsSync(filePath(n)));
    expect(missingOnDisk, 'the manifest names files that are not in the package').toEqual([]);

    // Both partitions must be non-empty, or one whole branch of the sweep is gone.
    expect(
      PARSEABLE.map((e) => e.filename).length,
      'no parseable files — the verdict sweep would generate no tests'
    ).toBeGreaterThan(0);
    expect(new Set(UNPARSEABLE.map((e) => e.filename)), 'the refusal cases changed').toEqual(
      new Set(['malformed-json.json', 'unsupported-file.txt'])
    );
  });

  for (const entry of PARSEABLE) {
    const measured = entry.measured_validator_result;
    const expectPass = measured.ok === true;

    test(`${entry.filename} uploads and renders the ${expectPass ? 'PASS' : 'FAIL'} MANIFEST.json promises`, async ({
      page,
    }) => {
      const posts = countValidatorPosts(page);
      await openValidator(page);
      await upload(page, entry.filename);

      // The upload really transferred the file: the box holds the file's own text,
      // byte for byte, rather than anything this spec typed.
      expect(await textarea(page).inputValue()).toBe(fileText(entry.filename));

      await validateButton(page).click();
      await expect
        .poll(posts, { message: 'no POST to /validate/record was observed' })
        .toBe(1);

      await expect(verdict(page)).toHaveAttribute(
        'aria-label',
        expectPass ? 'Validation PASS' : 'Validation FAIL'
      );

      if (expectPass) {
        await expect(verdict(page)).toContainText('Valid against official ISAAC schema v1.05.');
        await expect(errorRows(page), 'a PASS must carry no schema errors').toHaveCount(0);
      } else {
        // The count the operator is told to expect, and the first row's PAIR —
        // a message without its locating path cannot be acted on.
        const count = measured.error_count ?? 0;
        await expect(errorRows(page)).toHaveCount(count);
        await expect(verdict(page)).toContainText(`${count} error${count === 1 ? '' : 's'}`);
        await expect(verdict(page)).toContainText('Export blocked.');
        const first = errorRows(page).first();
        await expect(first).toContainText(measured.first_error_path ?? '');
        await expect(first).toContainText(measured.first_error_message ?? '');
      }

      // The advisory tier is NON-GATING: its presence is asserted against the
      // manifest, and never against the verdict above.
      const warnings = measured.advisory_warnings ?? [];
      if (warnings.length > 0) {
        await expect(advisory(page)).toBeVisible();
        await expect(advisory(page).getByRole('heading')).toContainText(
          `Advisory notes (${warnings.length}) — these do not affect the verdict`
        );
      } else {
        await expect(advisory(page)).toHaveCount(0);
      }

      // Nothing internal rode along, on any of the real files.
      const shown = await page.locator('.rec-val-result').innerText();
      for (const marker of LEAK_MARKERS) {
        expect(shown, `${marker} leaked into the result for ${entry.filename}`).not.toContain(
          marker
        );
      }
    });
  }

  for (const entry of UNPARSEABLE) {
    test(`${entry.filename} is refused in the browser and never reaches the validator`, async ({
      page,
    }) => {
      /*
       * `unsupported-file.txt` is the FORCED-THROUGH path UPLOAD-GUIDE.md
       * describes: `accept` is a chooser hint, so `setInputFiles` bypasses it
       * exactly as the macOS "all files" option does. The chooser filter itself is
       * a separate assertion, below — the two halves of that file's behaviour are
       * tested separately because only one of them is reachable from a script.
       */
      const posts = countValidatorPosts(page);
      await openValidator(page);
      await upload(page, entry.filename);

      await validateButton(page).click();

      await expect(rejection(page)).toContainText("isn't valid JSON");
      await expect(verdict(page), 'an unreadable document is not a verdict').toHaveCount(0);
      await expect(errorRows(page)).toHaveCount(0);
      expect(posts(), 'unparseable input must not be sent to the server at all').toBe(0);
    });
  }

  // --- the two recorded DEFECTS ----------------------------------------------

  test('the two files whose names promise a failure still PASS — a recorded DEFECT, not an endorsement', async ({
    page,
  }) => {
    /*
     * `invalid-date-time.json` carries a required `timestamps.created_utc` of
     * "not-a-date"; `empty-measurement-series.json` carries `measurement.series:
     * []`. Both are schema-valid today, for reasons MANIFEST.json's
     * `known_divergences` records: `format` is not enforced (no `format_checker`,
     * and `date-time` is not a registered checker without `rfc3339-validator`),
     * and `measurement.series` has no `minItems`.
     *
     * This test pins the DEFECT, not a desired behaviour. Format enforcement is
     * Dean-blocked (Q20) and is deliberately not changed here. When it lands, this
     * test SHOULD fail — and when it does, the fix is to rewrite MANIFEST.json,
     * UPLOAD-GUIDE.md's per-file row AND quick-reference table, README.md's
     * "expected to PASS" section, and ENGINEERING-NOTES.md. Do not flip an
     * expectation and move on.
     */
    for (const name of ['invalid-date-time.json', 'empty-measurement-series.json']) {
      const entry = ENTRIES.find((e) => e.filename === name);
      expect(entry, `${name} vanished from MANIFEST.json`).toBeDefined();
      expect(
        entry?.intended_outcome,
        `${name} is only a divergence because its INTENT is "invalid"`
      ).toBe('invalid');
      expect(
        entry?.measured_matches_intent,
        `${name} must stay flagged as contradicting its own name`
      ).toBe(false);

      await openValidator(page);
      await upload(page, name);
      await validateButton(page).click();
      await expect(
        verdict(page),
        `${name} no longer PASSES — the defect it documents may have been fixed`
      ).toHaveAttribute('aria-label', 'Validation PASS');
      await expect(errorRows(page)).toHaveCount(0);
    }
  });

  test('an empty measurement series is DISCLOSED on the pass rather than passing silently', async ({
    page,
  }) => {
    /*
     * The schema divergence is unchanged and open; what changed is that the pass
     * is no longer silent. Asserted as the SET of places advised about, because a
     * count cannot tell "the tier reported less" from "the screen rendered less".
     */
    await openValidator(page);
    await upload(page, 'empty-measurement-series.json');
    await validateButton(page).click();

    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation PASS');
    const where = await advisory(page).locator('.rec-val-advisory-where').allTextContents();
    expect(new Set(where.map((w) => w.trim()))).toEqual(new Set(['links', 'measurement.series']));
    await expect(advisory(page)).toContainText('contains no measured data');
  });

  // --- the upload control's own behaviour ------------------------------------

  test('re-choosing the SAME file loads it again and re-validates to the same verdict', async ({
    page,
  }) => {
    /*
     * `onFileChange` clears `input.value` after reading. Without that, choosing the
     * same file twice fires no `change` event and the second selection is a silent
     * no-op — the operator presses Upload, sees nothing happen, and cannot tell a
     * broken control from a file that was already loaded. This is the guard for it.
     */
    const posts = countValidatorPosts(page);
    await openValidator(page);

    await upload(page, 'repairable-record.json');
    await validateButton(page).click();
    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation FAIL');
    const firstRows = (await errorRows(page).allTextContents()).map((t) =>
      t.replace(/\s+/g, ' ').trim()
    );

    // Same file, second selection. Choosing a file clears the previous outcome,
    // so the stale FAIL must be gone BEFORE anything is re-validated.
    await fileInput(page).setInputFiles(filePath('repairable-record.json'));
    await expect(
      verdict(page),
      'a verdict from the previous run outlived a new file selection'
    ).toHaveCount(0);
    await expect(page.locator('.rec-val-empty')).toBeVisible();
    await expect(textarea(page)).toHaveValue(fileText('repairable-record.json'));

    await validateButton(page).click();
    await expect.poll(posts).toBe(2);
    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation FAIL');
    const secondRows = (await errorRows(page).allTextContents()).map((t) =>
      t.replace(/\s+/g, ' ').trim()
    );
    expect(secondRows, 'the same document must validate to the same errors').toEqual(firstRows);
  });

  test('switching from a failing file to a passing one leaves no row of the first behind', async ({
    page,
  }) => {
    await openValidator(page);

    await upload(page, 'multiple-issues.json');
    await validateButton(page).click();
    await expect(errorRows(page)).toHaveCount(3);
    await expect(
      errorRows(page).filter({ hasText: "'record_domain' is a required property" })
    ).toHaveCount(1);

    await upload(page, 'complete-valid-record.json');
    await validateButton(page).click();

    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation PASS');
    await expect(
      errorRows(page),
      'an error from the previous file survived the switch'
    ).toHaveCount(0);
  });

  test('the file chooser is restricted to JSON', async ({ page }) => {
    /*
     * The other half of `unsupported-file.txt`. This attribute is why the .txt is
     * not offered in the chooser's default listing — the refusal that happens
     * BEFORE the one the refusal test above measures. It is asserted rather than
     * described because a script cannot open a native file dialog, and because
     * `setInputFiles` bypasses `accept` entirely, so no other test in this file
     * would notice if it were dropped.
     */
    await openValidator(page);
    await expect(fileInput(page)).toHaveAttribute('accept', 'application/json,.json');
    await expect(fileInput(page)).toHaveAttribute('type', 'file');
  });

  test('the 177 KB record is accepted without a size refusal', async ({ page }) => {
    /*
     * `large-valid-record.json` is 181,163 bytes against a 512 KB client-side
     * bound. The sweep already asserts its PASS; what is asserted here is the
     * NEGATIVE — that the size pre-check did not fire — because a bound applied
     * too eagerly would refuse the file before any request, and a refusal is not a
     * verdict this screen would otherwise distinguish for the reader.
     */
    await openValidator(page);
    await upload(page, 'large-valid-record.json');
    await expect(rejection(page), 'the size pre-check refused a file inside the bound').toHaveCount(
      0
    );
    await validateButton(page).click();
    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation PASS');
  });

  test('multi-byte text survives the upload and reaches the box unmangled', async ({ page }) => {
    /*
     * `unicode-and-escaping.json` is written as real UTF-8, not `\u` escapes, so
     * the file → FileReader → textarea path really carries multi-byte characters.
     * The whole-file equality is the strong assertion; the individual characters
     * are named so a failure says WHAT was mangled rather than only that something
     * was.
     */
    await openValidator(page);
    await upload(page, 'unicode-and-escaping.json');

    const loaded = await textarea(page).inputValue();
    expect(loaded).toBe(fileText('unicode-and-escaping.json'));
    for (const sample of ['é', '氧', '«', '—']) {
      expect(loaded, `${sample} did not survive the upload`).toContain(sample);
    }

    await validateButton(page).click();
    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation PASS');
  });

  // --- keyboard --------------------------------------------------------------

  test('the screen is operable from the keyboard, and the hidden file input is not a tab stop', async ({
    page,
  }) => {
    /*
     * The file input is visually hidden with `tabIndex={-1}`; the "Upload JSON
     * File" button is the real control. If that `tabIndex` were dropped, a keyboard
     * reader would land on an invisible input — focus would vanish. So the tab
     * ORDER is asserted (textarea → Upload → Validate, with nothing between Upload
     * and Validate), and then the verdict is obtained with no mouse click at all.
     */
    await openValidator(page);

    await textarea(page).focus();
    await page.keyboard.insertText(fileText('repairable-record.json'));

    await page.keyboard.press('Tab');
    await expect(uploadButton(page), 'Tab from the box must reach Upload').toBeFocused();

    await page.keyboard.press('Tab');
    await expect(
      validateButton(page),
      'the hidden file input became a tab stop between Upload and Validate'
    ).toBeFocused();

    await page.keyboard.press('Enter');
    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation FAIL');
    await expect(errorRows(page).first()).toContainText('measurement.qc.status');
  });

  // --- narrow viewport -------------------------------------------------------

  test('at 375px the verdict and every error row stay readable without sideways scroll', async ({
    page,
  }) => {
    /*
     * The one property here that IS width-dependent, which is why it resizes in
     * place rather than asking for a second viewport project. The multi-error file
     * is used because three rows of long schema messages is the case most likely
     * to push the page wider than the phone it is on — and a validator whose error
     * list can only be read by scrolling sideways has not reported anything.
     */
    await page.setViewportSize({ width: 375, height: 812 });
    await openValidator(page);
    await upload(page, 'multiple-issues.json');
    await validateButton(page).click();

    await expect(verdict(page)).toHaveAttribute('aria-label', 'Validation FAIL');
    await expect(errorRows(page)).toHaveCount(3);
    for (let i = 0; i < 3; i += 1) {
      await expect(errorRows(page).nth(i)).toBeVisible();
    }

    const overflow = await page.evaluate(() => {
      const el = document.documentElement;
      return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
    });
    expect(
      overflow.scrollWidth,
      `the page scrolls sideways at 375px (${overflow.scrollWidth} > ${overflow.clientWidth})`
    ).toBeLessThanOrEqual(overflow.clientWidth);
  });
});

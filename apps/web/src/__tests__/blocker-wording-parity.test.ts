/**
 * The three internal blocker identifiers are never shown to a scientist as
 * machine keys — and the website and the assistant call each field the SAME
 * thing.
 *
 * WHAT WAS WRONG. `experiment_repository.py:769,778,786` mints `reduced_spectrum`,
 * `qc_status` and `required_for_evidence_record` as a pending entry's `blocker`
 * key; `serialize._blocker_about` puts the first string of `uri`/`blocker` into
 * the served `about`; and four surfaces then rendered that verbatim. Measured in
 * a real browser (`CLAUDE.md` §11, 2026-09-13), the `fields` workspace showed all
 * three to a scientist, and the assistant answered
 *
 *     "3 fields still need you: reduced_spectrum, qc_status,
 *      required_for_evidence_record."
 *
 * WHY THE USUAL EXEMPTION DOES NOT APPLY, and why this file exists rather than a
 * shrug: `UX-014`'s rule protects a SCHEMA PATH, on the stated ground that "it is
 * how a curator maps a field". These are not schema paths — `grep -rao` over
 * `schema/` and `vocabulary/` returns **0 hits for all three**, re-measured on
 * this branch. A key that appears nowhere in the schema maps nothing, so the rule
 * does not reach it. §11 records that an earlier exemption claim rested on
 * exactly that miscitation and was withdrawn.
 *
 * THE PARITY IS THE POINT. `assistant_query._blocker_display` (Python) and
 * `blockerDisplayName` (here) apply the same predicate and produce the same
 * words, because the assistant names these fields in a sentence while the
 * screens name them in a row. The expectations below are duplicated verbatim in
 * `apps/api/tests/test_blocker_wording.py`, which names this file in turn — two
 * languages cannot share a constant, so they share a pinned table instead.
 */

import { describe, expect, it } from 'vitest';
import { blockerDisplayName, isBareBlockerKey, pendingSummary } from '../lib/adapt';

/** The exact table `apps/api/tests/test_blocker_wording.py` asserts. */
const HUMANIZED: [string, string][] = [
  ['reduced_spectrum', 'Reduced Spectrum'],
  ['qc_status', 'QC Status'],
  ['required_for_evidence_record', 'Required For Evidence Record'],
];

/** Every real-locator shape this repository actually serves. Verbatim, all of them. */
const LOCATORS_VERBATIM = [
  'sample.material.formula',
  'assets:sha256',
  'ssrl-archive://BL15-2/2099_run_000/x.xdi',
  "Sheet 'Campaign Info', field=technique",
  'line 16, ssrl-archive://BL15-2/2099_run_000/notebooks/',
];

describe('blocker wording · the three internal keys', () => {
  it('humanizes each one to the words the parity test in Python asserts', () => {
    for (const [key, shown] of HUMANIZED) {
      expect(blockerDisplayName(key), key).toBe(shown);
    }
  });

  it('never rewrites a real locator', () => {
    for (const locator of LOCATORS_VERBATIM) {
      expect(isBareBlockerKey(locator), locator).toBe(false);
      expect(blockerDisplayName(locator), locator).toBe(locator);
    }
  });

  it('recognises exactly the bare-identifier shape, and nothing adjacent to it', () => {
    for (const [key] of HUMANIZED) expect(isBareBlockerKey(key)).toBe(true);
    // Each of these differs from a bare identifier in ONE way, so a predicate
    // that drifted would fail here rather than on a shape nobody serves.
    for (const near of [
      'Reduced_Spectrum', // upper case
      'reduced spectrum', // a space
      'reduced.spectrum', // a dot
      'reduced-spectrum', // a hyphen
      '_reduced', // leading underscore
      'reduced__spectrum', // doubled underscore
      '2reduced', // leading digit
      '', // empty
    ]) {
      expect(isBareBlockerKey(near), near).toBe(false);
    }
    expect(blockerDisplayName(null)).toBeNull();
    expect(blockerDisplayName('   ')).toBeNull();
  });
});

describe('blocker wording · the Needs You row', () => {
  /** The shape `serialize.pending_to_list` serves for a created record's series question. */
  const seriesItem = {
    id: 'series',
    kind: 'series',
    question: 'Provide/point to the reduced spectrum so measurement.series can be built.',
    about: 'reduced_spectrum',
  } as never;

  const assetItem = {
    id: 'ssrl-archive://BL15-2/2099_run_000/x.xdi',
    kind: 'asset',
    question: 'Provide the sha256 for this asset.',
    about: 'ssrl-archive://BL15-2/2099_run_000/x.xdi',
  } as never;

  it('drops the mono locator when it is the internal key, keeping the human label', () => {
    const summary = pendingSummary(seriesItem);
    // The label already names the field, in the product's own words...
    expect(summary.label).toBe('Reduced Spectrum');
    // ...so the same words in machine casing are not rendered a second time.
    expect(summary.locator).toBeNull();
  });

  it('keeps the locator on an asset question, which is what the token is FOR', () => {
    const summary = pendingSummary(assetItem);
    expect(summary.label).toBe('Asset Hash');
    expect(summary.locator).toBe('ssrl-archive://BL15-2/2099_run_000/x.xdi');
  });
});

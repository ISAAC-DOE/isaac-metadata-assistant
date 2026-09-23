/**
 * AN ADVISORY, IN ONE PLAIN SENTENCE — the code and the server's own message stay one
 * `?` away (review #277, I-7: no backticked `links` / `measurement` in the visible
 * sentence).
 *
 * Each title restates ONLY what the server's check observes (`portal_warnings.py`),
 * never a judgement it does not make: NO_MEASUREMENT_SERIES says there is no measured
 * data, not that the record is wrong. A code this build has not been taught is shown
 * as a humanized version of the code itself rather than a guessed meaning.
 */
const ADVISORY_TITLES: Readonly<Record<string, string>> = {
  NO_LINKS: 'No relationships to other records are declared.',
  NO_MEASUREMENT_SERIES: 'The record holds no measured data.',
  QC_NONVALID_WITHOUT_EVIDENCE: 'A QC verdict other than valid has no evidence recorded.',
};

export function advisoryTitle(code: string): string {
  const known = ADVISORY_TITLES[code];
  if (known !== undefined) return known;
  const words = code.toLowerCase().split('_').filter((word) => word !== '');
  if (words.length === 0) return code;
  const sentence = words.join(' ');
  return `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.`;
}

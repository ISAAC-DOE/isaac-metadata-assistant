/**
 * A `qc` pending item is called "QC Verdict" everywhere a summary names it — and
 * the full question still reaches the reader where they answer it.
 *
 * WHAT WAS WRONG, measured on a record created through `POST /api/experiments`
 * (the path a scientist actually takes) before this guard existed:
 *
 *   pendingItemToBlocker(qc).label   "Qc"     <- titleCase('qc'), the fallback
 *   pendingSummary(qc).label         105 chars, the entire question verbatim
 *
 * `KIND_LABEL` carried `asset`, `series`, `descriptor` and `edge` but not `qc`,
 * even though `qc` is as structured as any of them — dedicated verdict control,
 * closed enum, its own answer shape in `complete.py`. Nothing caught it because no
 * frontend fixture carries a `qc` pending item, which is also why this file builds
 * its own.
 *
 * THE VISIBLE COST. The needs-you banner listed three items of one list at 16, 105
 * and 21 characters, and the answered list called the field "Qc" — neither a word
 * nor the term this product uses in its own prose.
 *
 * FOUR CONSUMERS, and they are asserted rather than assumed: the needs-you summary
 * (`RecordWorkbench`), the answered-list label and its `Edit {label}` accessible
 * name (`GuidedCompletion`), and `GuidedPrompt`'s `aria-label`. All four read one
 * of the two functions below, so both are pinned here.
 */

import { describe, expect, it } from 'vitest';
import { pendingItemToBlocker, pendingSummary } from '../lib/adapt';

/** The shape `serialize.pending_to_list` serves for a created record's qc question. */
const QC_ITEM = {
  id: 'qc',
  kind: 'qc',
  question:
    'What is the QC verdict for this measurement (valid/compromised/failed/pending) and how was it determined?',
  about: 'qc_status',
} as never;

const EXPECTED = 'QC Verdict';

describe('a qc blocker is named, not title-cased or quoted whole', () => {
  it('names it in the answered list and in both accessible names', () => {
    // `blocker.label` is what `GuidedCompletion`'s `.answered-label`, its
    // `Edit {label}` and `GuidedPrompt`'s `aria-label` all render.
    expect(pendingItemToBlocker(QC_ITEM).label).toBe(EXPECTED);
  });

  it('names it in the needs-you summary, instead of quoting the whole question', () => {
    const summary = pendingSummary(QC_ITEM);
    expect(summary.label).toBe(EXPECTED);
    // The defect this replaces, stated as a bound rather than as a story: a
    // summary row is a LABEL, and 105 characters is a sentence.
    expect(summary.label.length).toBeLessThan(32);
  });

  it('lists three LABELS, not two labels and a paragraph', () => {
    /*
     * The three blockers a created record owes, as one list. Before the fix these
     * measured 16 / 105 / 21 characters — which is what made the banner read as two
     * labels and a paragraph.
     *
     * MY FIRST VERSION OF THIS ASSERTION WAS WRONG AND IS RECORDED RATHER THAN
     * QUIETLY REPLACED. It required `max < 2 * min`, and failed at `expected 21 to
     * be less than 20`: the labels are "Reduced Spectrum" (16), "QC Verdict" (10)
     * and "Scientific Descriptor" (21), so a 2:1 spread between two perfectly good
     * labels tripped it. A ratio was a proxy for the thing I meant, and it measured
     * the wrong thing — "QC Verdict" being SHORTER than its siblings is not a
     * defect.
     *
     * The property a reader actually sees is that every row is a LABEL. 32 is the
     * bound: long enough for "Scientific Descriptor" and anything of that shape,
     * far short of a sentence.
     */
    const siblings = [
      { id: 'series', kind: 'series', question: 'Provide/point to the reduced spectrum.' },
      QC_ITEM,
      { id: 'descriptor', kind: 'descriptor', question: 'Provide at least one descriptor.' },
    ] as never[];
    for (const item of siblings) {
      const label = pendingSummary(item).label;
      expect(label.length, `${label} is a sentence, not a label`).toBeLessThan(32);
      expect(label.endsWith('?'), `${label} is a question, not a label`).toBe(false);
    }
  });

  it('does NOT shorten the question itself — the act keeps the allowed values', () => {
    /*
     * The reason a short label is safe. `GuidedPrompt` renders
     * `<h2 className="guided-question">{blocker.question}</h2>`, so the enum the
     * scientist must choose from survives verbatim; only the SUMMARY is concise.
     * If a future change ever routed the label into that heading, this fails.
     */
    const blocker = pendingItemToBlocker(QC_ITEM);
    expect(blocker.question).toContain('valid/compromised/failed/pending');
    expect(blocker.question).not.toBe(blocker.label);
  });

  it('introduces no name: every word of the label appears in the product prose', () => {
    // "QC verdict" is what `experiment_repository.py:780` and
    // `inferability.py:798` already say to a scientist. A label may not invent a
    // term, and this one does not.
    for (const word of EXPECTED.toLowerCase().split(' ')) {
      expect(QC_ITEM['question' as keyof typeof QC_ITEM].toLowerCase()).toContain(word);
    }
  });
});

/**
 * ONE SCROLLPORT PER REGION — the defect this Assistant hit TWICE in one day.
 *
 * ── WHAT WAS MEASURED, BOTH TIMES ──────────────────────────────────────────
 *
 * 1. In the rail. At the shipped width the panel stacked two independently
 *    scrolling control regions and BOTH were clipped: `.assistant-empty`
 *    hiding 85px and `.assistant-agent-actions` hiding 65px. A reader met two
 *    half-lists, each with its own scrollbar, neither finishable.
 *
 * 2. In the popover, AFTER the fix. Moving `.assistant-agent-actions` into
 *    "What Can I Ask?" moved its `max-height: 32vh; overflow-y: auto` with it —
 *    so the list scrolled INSIDE the catalog's own scrollport, and still hid
 *    65px. The constraint had been right where it was and became the same
 *    defect one level down.
 *
 * *** THE LESSON, AND WHY THIS FILE EXISTS: when a block moves, its scroll
 * constraint moves with it, and a constraint that was correct in one container
 * is not automatically correct in the next. *** Neither instance was caught by
 * a test — the first by the owner looking at the screen, the second by a
 * browser measurement taken only because the first had just happened.
 *
 * ── WHY A CSS SCAN ─────────────────────────────────────────────────────────
 *
 * jsdom computes no layout, so "is this element clipped?" is unanswerable here;
 * it is answered in the browser, by the sweeps. What IS answerable on every run
 * is which selectors DECLARE a scrollport, and that list should change only
 * deliberately. An allowlist makes adding one an explicit act with a reason.
 */
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(
  join(resolve(__dirname, '..'), 'components/assistant.css'),
  'utf8',
);

/**
 * The selectors allowed to scroll, each with the reason it is the ONE
 * scrollport of its region.
 */
const ALLOWED_SCROLLPORTS: Readonly<Record<string, string>> = {
  '.assistant-memory': 'a bounded memory readout; nothing else scrolls inside it',
  '.assistant-body': 'the rail\'s own scrollport — the region the conversation lives in',
  '.assistant-empty': 'the resting state; it now holds one short line, and the rule is kept so a future empty state cannot overflow the rail',
  '.assistant-conversation': 'the transcript, which is the thing a reader scrolls',
  '.assistant-more-body': 'a native <details> body, opened deliberately by the reader',
  '.assistant-capabilities-panel': 'the popover shell',
  '.assistant-capabilities-list': 'the ONE scrollport inside the popover — suggested questions, agent actions and the capability catalog all flow through it',
};

/** Every selector in `assistant.css` whose own rule declares a vertical scrollport. */
function declaredScrollports(): string[] {
  const found: string[] = [];
  // `selector {  … }` at the start of a line, non-greedy to the first close.
  for (const m of CSS.matchAll(/^(\.[A-Za-z0-9_-]+)\s*\{([^}]*)\}/gm)) {
    const [, selector, body] = m;
    // strip comments so a rule DESCRIBING a removed overflow is not counted —
    // exactly the trap that made an earlier sweep in this repo report four
    // phantom custom properties that were only mentioned in prose.
    const decls = body.replace(/\/\*[\s\S]*?\*\//g, '');
    if (/(?:^|;)\s*overflow(?:-y)?\s*:\s*(auto|scroll)/.test(decls)) found.push(selector);
  }
  return found;
}

describe('the Assistant declares one scrollport per region', () => {
  it('no selector scrolls without being on the allowlist, with a stated reason', () => {
    const unexpected = declaredScrollports().filter((s) => !(s in ALLOWED_SCROLLPORTS));
    expect(
      unexpected,
      'a new scrolling region appeared in the Assistant. If it is nested inside another ' +
        'scrollport it is the defect this file records twice: the reader gets a half-list ' +
        'with its own scrollbar inside a thing that already scrolls. Either let it flow, or ' +
        'add it to ALLOWED_SCROLLPORTS with the reason it is the ONE scrollport of its region.',
    ).toEqual([]);
  });

  it('the two blocks that caused the defect do NOT scroll', () => {
    /*
     * Named explicitly rather than left to the allowlist, because "absent from
     * a list" is a weaker statement than "measured absent", and these two are
     * the ones that actually shipped clipped.
     */
    for (const selector of ['.assistant-agent-actions', '.assistant-agent-prompts']) {
      expect(
        declaredScrollports(),
        `${selector} scrolls again. In the rail it clipped 65px; moved into the catalog it ` +
          'clipped 65px inside another scrollport. It must flow.',
      ).not.toContain(selector);
    }
  });

  it('VACUITY GUARD — the scan actually finds the scrollports that exist', () => {
    // Without this, a regex that matched nothing would pass the first test
    // forever. The allowlist is the measured set, so the scan must find it.
    const found = declaredScrollports();
    expect(found.length).toBeGreaterThanOrEqual(5);
    expect(found).toContain('.assistant-capabilities-list');
    expect(found).toContain('.assistant-body');
  });
});

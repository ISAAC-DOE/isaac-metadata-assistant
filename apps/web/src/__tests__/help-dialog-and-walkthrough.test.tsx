/**
 * A11Y-02 + UX-021 — the Help popover's focus containment, and its pointer to the
 * guided walkthrough.
 *
 * WHAT IS PROVEN HERE, stated in this file's house style: nothing below measures a
 * pixel or a real browser's native Tab behaviour. jsdom does not move focus on a
 * `Tab` keydown by itself, which is precisely why these assertions are meaningful —
 * the only thing that can move focus in this environment is the component's own
 * handler, so an assertion that focus landed on a specific element IS an assertion
 * that the containment code ran and chose that element.
 */

import { afterEach, describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelpPanel } from '../components/HelpPanel';
import { LABELS } from '../lib/labels';
import { __bootTutorialStore, __resetTutorialStore } from '../lib/tutorialController';
import { markTutorialCompleted } from '../lib/tutorialPreference';
import { setTutorialScope } from '../lib/api';

function openHelp() {
  const view = render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <HelpPanel />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Help' }));
  return { ...view, dialog: screen.getByRole('dialog') };
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])';

function focusables(dialog: HTMLElement): HTMLElement[] {
  return Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
}

describe('A11Y-02 · the Help dialog contains focus', () => {
  it('declares aria-modal, which the trap is what makes TRUE', () => {
    /*
     * The pairing is the point. `aria-modal="true"` tells assistive technology that
     * everything outside this element is inert; asserting it WITHOUT the containment
     * below would be pinning a false claim. So this test and the two after it are one
     * finding in three parts, and none of them should be deleted without the others.
     */
    const { dialog } = openHelp();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('role')).toBe('dialog');
  });

  it('MUTATION-GUARDED — Tab from the LAST focusable wraps to the first instead of leaving', () => {
    const { dialog } = openHelp();
    const items = focusables(dialog);
    // Vacuity guard: a wraparound assertion over fewer than two items is satisfiable
    // by a component that does nothing at all.
    expect(items.length).toBeGreaterThanOrEqual(2);

    items[items.length - 1]!.focus();
    expect(document.activeElement).toBe(items[items.length - 1]);
    const notPrevented = fireEvent.keyDown(document, { key: 'Tab' });
    expect(notPrevented, 'Tab was not prevented — a real browser would leave the dialog').toBe(
      false,
    );
    expect(
      document.activeElement,
      'Tab from the last control left the dialog — the page behind it is covered, so a ' +
        'keyboard user would be editing something they cannot see',
    ).toBe(items[0]);
  });

  it('MUTATION-GUARDED — Shift+Tab is CONTAINED too, and this test is honest about what it cannot prove', () => {
    /*
     * *** THIS TEST WAS WRITTEN AS A DIRECTION ASSERTION AND THAT VERSION WAS TRUE BY
     * CONSTRUCTION. Kept as a corrected test rather than deleted, because the reason is
     * worth carrying: measured, the open dialog holds EXACTLY TWO focusables — the close
     * button and the walkthrough link (`FOCUSABLE_COUNT=2 :: BUTTON.help-panel-close |
     * A`). At n = 2, `(idx + 1) % 2` and `(idx - 1 + 2) % 2` are THE SAME INDEX, so
     * forward and backward wraparound are mathematically indistinguishable and no
     * assertion in this file can separate them.
     *
     * Proved by mutation: replacing `const delta = e.shiftKey ? -1 : 1` with
     * `const delta = 1` (a forward-only trap) left all seven tests GREEN. The original
     * version of this test claimed to catch exactly that mutant and could not.
     *
     * SO IT ASSERTS THE PROPERTY THAT IS REAL AND IS THE ONE A11Y-02 IS ABOUT: focus
     * does not LEAVE, in either direction. Whether it lands on the first or the last
     * item is not a user-visible distinction when there are two of them. The
     * count guard below is the ratchet: if a third focusable is ever added to this
     * panel, direction becomes observable and this test should be strengthened rather
     * than left passing. ***
     */
    const { dialog } = openHelp();
    const items = focusables(dialog);
    expect(
      items.length,
      'the focusable count changed. At 3+ items forward vs backward wraparound becomes ' +
        'distinguishable, so replace this containment check with a real direction assertion ' +
        '(and re-run the `delta = 1` mutant to prove the new one fires).',
    ).toBe(2);

    items[0]!.focus();
    const notPrevented = fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });

    /*
     * `defaultPrevented` IS THE ASSERTION, AND THE SECOND CORRECTION TO THIS TEST.
     * "Focus is still inside the dialog" was ALSO true by construction: jsdom never
     * implements native Tab traversal, so with the handler removed nothing moves focus
     * and the element stays where the test put it — inside the dialog. Measured: with
     * the whole Tab branch deleted, a containment-only version of this test passed.
     *
     * `preventDefault()` is the mechanism that actually stops the browser walking out,
     * and it is the one thing in this environment that differs between trapped and
     * untrapped. `fireEvent` returns `!event.defaultPrevented`, so `false` here means
     * the handler claimed the keystroke.
     */
    expect(
      notPrevented,
      'Shift+Tab was NOT prevented, so a real browser would walk focus out of the ' +
        'dialog and into the page it is covering. jsdom cannot show that directly — ' +
        'this is the observable that stands in for it.',
    ).toBe(false);
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it('Escape still closes and returns focus to the Help trigger', () => {
    // The pre-existing behaviour, asserted because the Escape handler was MOVED into
    // the same effect as the new Tab handler — a refactor that drops it would
    // otherwise be invisible here.
    openHelp();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Help' }));
  });
});

describe('UX-021 · Help offers the guided walkthrough — in place, true for every reader', () => {
  /*
   * INVERTED 2026-10-12, AND THE CORRECTNESS POINT IS KEPT, NOT DROPPED.
   *
   * These tests pinned a LINK to Settings → Help & Tutorial ("Go to Help &
   * Tutorial"), for one reason: the obvious alternative — pointing at My
   * Experiments' first-run offer — is FALSE for a reader who has finished the
   * walkthrough, because that control disappears for good on completion. The point
   * was that Help must only offer what is true for EVERY reader.
   *
   * The clutter audit moved the walkthrough to the END of the popover as a control
   * of its own ("Replay last"). It meets the same requirement more directly: it is
   * named by this browser's own completion state — Start when unfinished, Replay
   * when finished — so it is true for every reader without sending anyone anywhere.
   * Asserted both ways below, plus the guard against offering a second start while
   * a walkthrough is already open.
   */
  afterEach(() => {
    __resetTutorialStore();
    window.localStorage.clear();
  });

  it('offers Start to a reader who has not finished it, as the LAST control', () => {
    __resetTutorialStore();
    const { dialog } = openHelp();
    const start = within(dialog).getByRole('button', { name: LABELS.actionStartTutorial });
    const all = focusables(dialog);
    expect(all[all.length - 1]).toBe(start);
    expect(within(dialog).queryByRole('button', { name: LABELS.actionReplayTutorial })).toBeNull();
  });

  it('MUTATION-GUARDED — offers Replay, not Start, to a reader who HAS finished it', () => {
    markTutorialCompleted();
    __resetTutorialStore();
    const { dialog } = openHelp();
    expect(within(dialog).getByRole('button', { name: LABELS.actionReplayTutorial })).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: LABELS.actionStartTutorial })).toBeNull();
  });

  it('the row promises only what the control delivers', () => {
    const { dialog } = openHelp();
    const text = dialog.textContent ?? '';
    // No pointer sentence claims the walkthrough starts somewhere else, or teaches
    // anything this build cannot do; `help-claim-parity.test.tsx` owns the sweep.
    expect(text).not.toMatch(/launch|start the (guided )?walkthrough now/i);
    expect(dialog.querySelector('a[href*="tab=help"]')).toBeNull();
  });

  it('states that a walkthrough is open instead of offering a second start', () => {
    setTutorialScope('session-open-in-this-tab');
    __bootTutorialStore();
    const { dialog } = openHelp();
    expect(within(dialog).queryByRole('button', { name: LABELS.actionStartTutorial })).toBeNull();
    expect(within(dialog).queryByRole('button', { name: LABELS.actionReplayTutorial })).toBeNull();
    expect(dialog.textContent).toContain(LABELS.helpWalkthroughOpen);
    setTutorialScope(null);
  });
});

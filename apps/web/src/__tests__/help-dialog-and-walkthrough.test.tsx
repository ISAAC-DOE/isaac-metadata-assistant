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

import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelpPanel } from '../components/HelpPanel';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';

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

describe('UX-021 · Help points at the guided walkthrough', () => {
  it('renders a real link to the walkthrough', () => {
    const { dialog } = openHelp();
    const link = Array.from(dialog.querySelectorAll('a')).find(
      (a) => a.textContent === LABELS.actionGoToHelpAndTutorial,
    );
    expect(link, 'Help offers no route to the guided walkthrough').toBeDefined();
    // A real anchor with an href, so it is middle-clickable and bookmarkable rather
    // than a button that only works on left-click.
    expect(link!.getAttribute('href')).toBeTruthy();
  });

  it('MUTATION-GUARDED — the destination is the PERMANENT home of the walkthrough, not My Experiments', () => {
    /*
     * THE CORRECTNESS POINT OF THE WHOLE SLICE, and the reason this is a separate
     * assertion rather than a detail of the one above.
     *
     * The obvious destination — My Experiments, where `Launch Guided Demo` lives — is
     * FALSE for any reader who has already finished the walkthrough: that control is
     * gated on the queue and, per `ExperimentsHome.tsx`'s own note, "disappears for
     * good once the walkthrough is finished". `lib/routes.ts` calls the Settings
     * `help` tab "the one permanent home of the guided walkthrough".
     *
     * A Help surface is exactly where a first-time-only claim does the most damage,
     * so pointing it at `ROUTES.experiments` is the mutation this guards.
     */
    const { dialog } = openHelp();
    const link = Array.from(dialog.querySelectorAll('a')).find(
      (a) => a.textContent === LABELS.actionGoToHelpAndTutorial,
    )!;
    expect(link.getAttribute('href')).toBe(ROUTES.settingsTab('help'));
    expect(link.getAttribute('href')).not.toBe(ROUTES.experiments);
  });

  it('the pointer promises only what the destination delivers', () => {
    // It must not claim the walkthrough starts HERE, or that it teaches anything this
    // build cannot do. `help-claim-parity.test.tsx` owns the banned-claim sweep over
    // the whole panel; this is the narrower check that the new sentence is a POINTER.
    const { dialog } = openHelp();
    const text = dialog.textContent ?? '';
    expect(text).toContain('worked example');
    expect(text).not.toMatch(/launch|start the (guided )?walkthrough now/i);
  });
});

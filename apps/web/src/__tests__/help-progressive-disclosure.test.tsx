/**
 * UX-021b — the Help popover is FOUR top-level items, and the other three
 * sections moved behind a disclosure rather than being deleted.
 *
 * WHY THIS GUARD EXISTS AND WHAT IT IS FOR. The ledger entry that asked for the
 * reduction said "the 7→4 reduction wants progressive disclosure, not
 * deletion", and the reason that distinction is load-bearing rather than
 * stylistic is that four of the seven sections carry claims other suites pin as
 * honesty guarantees: `upload-claim-parity.test.tsx` §6 requires the "Where
 * values come from" section to name BOTH file-reading controls and never to
 * state the upload refusal unscoped, and `help-claim-parity.test.tsx` pins the
 * gate and signal wording against three separately-retired false versions.
 * Shortening this surface by removing any of it would be a disclosure
 * regression dressed as polish — so this file asserts BOTH halves: the count
 * came down AND every section is still there.
 *
 * MEASURED IN A REAL BROWSER, recorded here because jsdom computes no layout
 * and so nothing below is evidence of it: with the disclosure closed the
 * popover's `scrollHeight` is 962px at 1280/768 and 1115px at 320, against
 * 1695/1983 with everything open — a 43-44% reduction in what a first-time
 * reader has to scroll past. The panel's bottom edge is inside the viewport at
 * all three widths, and each of the four sections behind the disclosure renders
 * with a real height and width when it is opened (283/120/178/139 px at 1280),
 * which is the check the 320px empty-catalog defect earlier in this branch
 * taught: a container that fits is not the same as contents that render.
 */

import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelpPanel } from '../components/HelpPanel';

function openHelp() {
  const view = render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <HelpPanel />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Help' }));
  return view;
}

/** Every section heading in the popover, in document order. */
function allHeadings(container: HTMLElement): string[] {
  return [...container.querySelectorAll('.help-section h3')].map((h) =>
    (h.textContent ?? '').trim(),
  );
}

/** The top-level items of the popover body: sections plus the disclosure. */
function topLevelLabels(container: HTMLElement): string[] {
  const body = container.querySelector('.help-panel-body');
  expect(body, 'the popover has no body').not.toBeNull();
  return [...body!.children].map((child) => {
    if (child.tagName === 'DETAILS') {
      return (child.querySelector('summary')?.textContent ?? '').trim();
    }
    return (child.querySelector('h3')?.textContent ?? '').trim();
  });
}

const BEHIND_THE_DISCLOSURE = [
  'Where values come from',
  'Three separate signals',
  'Three gates on export',
  'Where evidence lives',
];

const STAYS_OPEN = ['How it works', 'No guessing', 'Synthetic workspace'];

describe('UX-021b · Help is four top-level items', () => {
  it('shows exactly four, and the fourth is the disclosure', () => {
    const { container } = openHelp();
    const top = topLevelLabels(container);
    expect(top).toHaveLength(4);
    expect(top.slice(0, 3)).toEqual(STAYS_OPEN);
    // Named rather than matched loosely: the summary has to say what is behind
    // it, or the reduction hides the claims instead of deferring them.
    expect(top[3]).toBe('How values, signals and gates work');
  });

  it('deleted nothing: all seven sections are still in the DOM', () => {
    const { container } = openHelp();
    // The exact set, so removing a section fails here rather than quietly
    // shrinking a count nobody reads.
    expect(new Set(allHeadings(container))).toEqual(
      new Set([...STAYS_OPEN, ...BEHIND_THE_DISCLOSURE]),
    );
    expect(allHeadings(container)).toHaveLength(7);
  });

  it('puts exactly the four mechanism sections behind the disclosure', () => {
    const { container } = openHelp();
    const more = container.querySelector('details.help-more');
    expect(more, 'the disclosure is missing').not.toBeNull();
    const inside = [...more!.querySelectorAll('.help-section h3')].map((h) =>
      (h.textContent ?? '').trim(),
    );
    expect(inside).toEqual(BEHIND_THE_DISCLOSURE);
  });

  it('is a NATIVE details, closed by default, carrying no ARIA of its own', () => {
    const { container } = openHelp();
    const more = container.querySelector('details.help-more') as HTMLDetailsElement;
    expect(more.tagName).toBe('DETAILS');
    // Closed: the whole point is that a first-time reader is not handed all
    // seven. `open` absent is what the accessibility sweep then opens.
    expect(more.open).toBe(false);
    // A native disclosure needs no `role`, no `aria-expanded` and no
    // `aria-controls` — and adding them is how a correct control acquires a
    // wrong announcement. The repo idiom is `FetchStates`/`SchemaBrowser`.
    for (const attr of ['role', 'aria-expanded', 'aria-controls', 'aria-hidden']) {
      expect(more.getAttribute(attr), `details.help-more must not set ${attr}`).toBeNull();
    }
    const summary = more.querySelector('summary')!;
    for (const attr of ['role', 'aria-expanded', 'tabindex']) {
      expect(summary.getAttribute(attr), `the summary must not set ${attr}`).toBeNull();
    }
  });

  it('the pinned claims are reachable through the collapsed disclosure', () => {
    // The guarantee the other suites depend on: their queries run over the
    // rendered DOM, and a closed `<details>` still contains its children. If
    // that ever stopped being true, those suites would fail for a reason that
    // looked like a copy change, so it is asserted here where it is visible.
    const { container } = openHelp();
    const more = container.querySelector('details.help-more') as HTMLDetailsElement;
    expect(more.open).toBe(false);
    const values = [...container.querySelectorAll('.help-section')].find(
      (el) => el.querySelector('h3')?.textContent === 'Where values come from',
    );
    expect(values, 'upload-claim-parity §6 finds this section by exactly this query').toBeTruthy();
    expect(values!.textContent).toMatch(/upload route\s+refuses every request/i);
  });
});

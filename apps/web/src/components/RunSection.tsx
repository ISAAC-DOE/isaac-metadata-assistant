/*
 * ONE COLLAPSIBLE SECTION INSIDE AN EXPANDED RUN CARD.
 *
 * WHY THIS EXISTS. An expanded run card used to be one flat list: five field
 * controls, then fourteen inherited rows with two controls each — measured against the
 * committed seed draft, which resolves one more address than the thirteen that are
 * actually overridable (`RunCard`'s header names that exception). Nothing in
 * it could be put away, so the reader who wanted the run's own conditions scrolled
 * past everything the record supplied, and the reader checking what is inherited
 * scrolled past the form. This is the disclosure that lets each half be put away —
 * and NOTHING ELSE. It decides no content, filters no field and classifies nothing:
 * it is handed a title, a summary and children.
 *
 * IT IS THE ARIA DISCLOSURE PATTERN, NOT A SECOND ACCORDION IMPLEMENTATION, and it
 * deliberately mirrors the one `RunCard` already uses for the card itself:
 * `h4 > button[aria-expanded][aria-controls]` over a container carrying that id.
 * Two differences from the card's, each measured rather than stylistic:
 *
 *   * NO `role="region"`. The card's own body is a region named after the run, so it
 *     is unique per card; a section named "Conditions for this run" is NOT — every
 *     run card on the screen would contribute one, and axe's `landmark-unique` reads
 *     repeated landmark name/role pairs as a defect. A disclosure needs no role at
 *     all: the button's `aria-expanded` and `aria-controls` are the whole contract.
 *   * THE BODY STAYS MOUNTED AND IS HIDDEN WITH `hidden`, where the card unmounts
 *     its panel. Collapsing a section must not destroy what is inside it: the
 *     inherited panel holds an open override form, an entered value and a ticked
 *     confirmation, and unmounting would silently discard a half-finished, audited
 *     act. `hidden` removes the subtree from the accessibility tree and from
 *     `getByRole`, so a collapsed section is genuinely not reachable — it is not a
 *     visual-only collapse.
 *
 * THE SUMMARY IS INSIDE THE BUTTON ON PURPOSE, so it lands in the button's
 * accessible name: a reader arriving by keyboard on a collapsed section hears what
 * is in it ("Inherited from the record, 12 inherited · 1 overridden on this run")
 * rather than only that something is there. It is the caller's job to make that
 * string a count of something actually enumerated — see `RunCard`, which derives
 * both of its summaries from the same two lists it renders.
 *
 * NOTHING IS CONVEYED BY COLOUR. The state is carried by `aria-expanded`, by the
 * chevron's direction, and by whether the body is present to a reader at all.
 */

import './runs.css';
import { useId, useState } from 'react';
import { ChevronDown, ChevronRight } from './icons';

export function RunSection({
  title,
  summary,
  defaultOpen = true,
  children,
}: {
  title: string;
  /**
   * A short, GROUNDED line about what is inside — a count of something the caller
   * enumerated, never a completion figure. Part of the button's accessible name.
   */
  summary: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const baseId = useId();
  const bodyId = `${baseId}-body`;
  const [open, setOpen] = useState(defaultOpen);
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <section className="run-section" data-open={open}>
      <h4 className="run-section-heading">
        <button
          type="button"
          className="run-section-header"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((prev) => !prev)}
        >
          <Chevron className="run-section-chevron" size={14} strokeWidth={2} aria-hidden="true" />
          <span className="run-section-title">{title}</span>
          <span className="run-section-summary">{summary}</span>
        </button>
      </h4>
      {/* See the header note: mounted in both states, hidden rather than removed. */}
      <div className="run-section-body" id={bodyId} hidden={!open}>
        {children}
      </div>
    </section>
  );
}

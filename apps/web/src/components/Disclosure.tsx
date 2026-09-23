import './disclosure.css';
import { useId, useState, type ReactNode } from 'react';
import { ChevronRight } from './icons';

/**
 * A DISCLOSURE WHOSE WHOLE ROW IS THE TARGET (2026-09-22, owner QA F4).
 *
 * The owner's finding: on accordions across the record screen the only affordance
 * was an 11px triangle or chevron. This is the replacement pattern — the WAI-ARIA
 * disclosure: one full-width `<button>` carrying `aria-expanded` and
 * `aria-controls`, with a real hover, a `:focus-visible` ring, an expanded state
 * and a chevron that turns (the turn is a `transition`, which `base.css`
 * neutralises under `prefers-reduced-motion`).
 *
 * `headingLevel` wraps the button in a heading, so a disclosure that titles a
 * section still appears in the document outline (the accordion pattern).
 *
 * CLOSED CONTENT IS `hidden`, NOT UNMOUNTED. It leaves the layout and the
 * accessibility tree, and it stays in the DOM, so state inside it (a recorder, a
 * half-typed box) survives a collapse, and every guard in this repository that
 * reads the DOM still reaches the text inside.
 *
 * WHAT MUST NEVER GO INSIDE ONE (DEC-35): a blocking error, a scientific
 * uncertainty, a destructive consequence, a privacy state or a required action.
 */
export function Disclosure({
  summary,
  meta,
  children,
  defaultOpen = false,
  open: controlledOpen,
  onOpenChange,
  headingLevel,
  className,
}: {
  /** The row's label. */
  summary: ReactNode;
  /** Optional trailing text on the row (a count, a state) — part of its name. */
  meta?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  /** Controlled open state; pass with `onOpenChange`. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  headingLevel?: 2 | 3 | 4;
  className?: string;
}) {
  const bodyId = useId();
  const [uncontrolled, setUncontrolled] = useState(defaultOpen);
  const controlled = controlledOpen !== undefined && onOpenChange !== undefined;
  const open = controlled ? controlledOpen! : uncontrolled;
  const toggle = () => {
    if (controlled) onOpenChange!(!open);
    else setUncontrolled(!open);
  };

  const trigger = (
    <button
      type="button"
      className="disclosure-trigger"
      aria-expanded={open}
      aria-controls={bodyId}
      onClick={toggle}
    >
      <ChevronRight className="disclosure-chevron" size={16} strokeWidth={2} aria-hidden="true" />
      <span className="disclosure-summary">{summary}</span>
      {meta !== undefined && meta !== null && <span className="disclosure-meta">{meta}</span>}
    </button>
  );
  const Heading = headingLevel ? (`h${headingLevel}` as const) : null;

  return (
    <div className={`disclosure${open ? ' is-open' : ''}${className ? ` ${className}` : ''}`}>
      {Heading ? <Heading className="disclosure-heading">{trigger}</Heading> : trigger}
      <div id={bodyId} className="disclosure-body" hidden={!open}>
        {children}
      </div>
    </div>
  );
}

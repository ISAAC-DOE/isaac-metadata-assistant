import { useState, type ReactNode } from 'react';
import { Disclosure } from './Disclosure';

/**
 * A DISCLOSURE WHOSE BODY IS MOUNTED ON FIRST OPEN, and kept mounted after (2026-10-18).
 *
 * For per-item DETAIL only — a candidate's full engineering rationale under "Why, in
 * detail", one per row. The shared `Disclosure` keeps every body in the DOM, which is right
 * for a caveat a guard must reach; 161 rationale bodies made the opened Runs stage 13,625
 * elements and an axe scan of it slower than the suite's budget. What a reader must see —
 * the short reason — stays outside this, visible.
 *
 * NEVER for a DEC-35 class (a blocking error, an uncertainty, a consequence, a privacy
 * state, a required action): those must be in the DOM whether or not the row is open.
 */
export function LazyDisclosure({
  summary,
  className,
  children,
}: {
  summary: ReactNode;
  className?: string;
  children: () => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  return (
    <Disclosure
      className={className}
      summary={summary}
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setMounted(true);
      }}
    >
      {mounted ? children() : null}
    </Disclosure>
  );
}

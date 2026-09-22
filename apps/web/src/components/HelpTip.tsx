import './help-tip.css';
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { CircleHelp } from './icons';

/**
 * AN ACCESSIBLE `?` — a short definition behind a button, never behind hover.
 *
 * The owner's brief (2026-09-22): explanation moves behind an accessible `?` or a
 * short disclosure, so a normal section shows state, value and action first. This
 * is the `?` half. Its rules, each one tested:
 *
 *  - OPENED BY A PRESS, NEVER BY HOVER ALONE. Pointer, keyboard (Enter/Space are the
 *    button's native activation) and touch all reach it the same way.
 *  - NAMED. The trigger's accessible name is "About <subject>", and it carries
 *    `aria-expanded` + `aria-controls` pointing at the panel.
 *  - ESCAPE CLOSES AND RETURNS FOCUS to the trigger; a press outside closes it.
 *  - CLAMPED TO THE VIEWPORT. The panel is `position: fixed` and placed from the
 *    trigger's rect, so no scrolling ancestor (the sticky Record Map scrolls
 *    internally at desktop) can clip it, and it is shifted to stay 8px inside
 *    both viewport edges.
 *
 * WHAT IT MUST NEVER HOLD: a blocking error, a scientific uncertainty, a
 * destructive consequence, a privacy state or a conflict (DEC-35). Those stay
 * visible on the surface; this holds definitions — "what is this field", "where
 * does it go" — and only statements the schema or API supports.
 */
export function HelpTip({
  subject,
  children,
}: {
  /** What the tip is about — "Temperature". The trigger reads "About Temperature". */
  subject: string;
  /** The definition. Keep it to one to three short sentences. */
  children: ReactNode;
}) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const place = useCallback(() => {
    const trigger = triggerRef.current;
    if (trigger === null) return;
    const rect = trigger.getBoundingClientRect();
    const viewport = document.documentElement.clientWidth || window.innerWidth;
    const gutter = 8;
    const width = Math.min(288, Math.max(160, viewport - gutter * 2));
    const left = Math.min(Math.max(gutter, rect.left + rect.width / 2 - width / 2), viewport - gutter - width);
    setPos({ top: rect.bottom + 6, left, width });
  }, []);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target === null) return;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      setOpen(false);
      triggerRef.current?.focus();
    };
    // Capture phase: a scroll in ANY ancestor moves the trigger, and a fixed
    // panel that did not follow would point at nothing.
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, place]);

  return (
    <span className="helptip">
      <button
        ref={triggerRef}
        type="button"
        className="helptip-trigger"
        aria-label={`About ${subject}`}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
      >
        <CircleHelp size={14} strokeWidth={2} aria-hidden="true" />
      </button>
      {/* Rendered while closed too (hidden), so `aria-controls` never dangles and
          the definition is reachable by every DOM-reading guard. */}
      <div
        ref={panelRef}
        id={panelId}
        className="helptip-panel"
        role="note"
        hidden={!open}
        style={pos === null ? undefined : { top: pos.top, left: pos.left, width: pos.width }}
      >
        {children}
      </div>
    </span>
  );
}

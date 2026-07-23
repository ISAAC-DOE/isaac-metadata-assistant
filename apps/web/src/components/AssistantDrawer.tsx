import './assistant-drawer.css';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { MessageSquare, X } from './icons';
import { LABELS } from '../lib/labels';

interface AssistantDrawerProps {
  /**
   * The rail class the panel wears on DESKTOP (e.g. "record-right narrow" or
   * "memory-right"). It is preserved verbatim so the desktop layout is
   * byte-identical to the pre-drawer aside; the drawer behaviour is layered on
   * top and only takes visual effect at narrow widths (see assistant-drawer.css).
   */
  railClassName: string;
  /** Accessible name for the region / slide-over dialog. */
  label?: string;
  children: ReactNode;
}

/**
 * P33 S6 (RESP-1) — the Assistant right rail, responsive.
 *
 * DESKTOP (≥1024px): renders exactly as before — a static `<aside>` region with
 * the given rail class + accessible name. The trigger, backdrop, and close
 * button are CSS-hidden, so the desktop appearance is unchanged.
 *
 * NARROW (≤1024px): the rail collapses behind a clearly labelled "Assistant"
 * control that opens the panel as a slide-over dialog — role="dialog" +
 * aria-modal while open, aria-expanded on the trigger, a focus trap, Escape to
 * close, and focus restoration to the trigger. The open/close behaviour is pure
 * JS (viewport-independent); the switch between "static rail" and "slide-over"
 * is pure CSS. Because the trigger is CSS-hidden at desktop, `open` is only ever
 * true at narrow widths, so the dialog semantics never apply on desktop.
 */
export function AssistantDrawer({ railClassName, label = LABELS.assistant, children }: AssistantDrawerProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  const panelId = useId();

  // Escape closes; Tab / Shift+Tab are contained within the panel while open.
  // Capture phase so the drawer handles the keys first (mirrors SearchDialog).
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setOpen(false);
        return;
      }
      if (e.key !== 'Tab' || !panel) return;
      // Contain Tab inside the panel (preventDefault so focus can never leave),
      // cycling with wraparound over the focusable items.
      e.preventDefault();
      const items = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (items.length === 0) {
        panel.focus();
        return;
      }
      const last = items.length - 1;
      const active = document.activeElement as HTMLElement | null;
      const idx = active ? items.indexOf(active) : -1;
      // When focus is on the panel itself (idx === -1, e.g. the just-opened
      // panel), Tab lands on the FIRST focusable and Shift+Tab on the LAST —
      // rather than letting the modular arithmetic pick a mid-list item.
      let next: HTMLElement;
      if (idx === -1) {
        next = e.shiftKey ? items[last] : items[0];
      } else {
        const delta = e.shiftKey ? -1 : 1;
        next = items[(idx + delta + items.length) % items.length] ?? items[0];
      }
      next.focus();
    }

    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [open]);

  // Desktop-safety hygiene (not a layout rule): `open` is JS state independent
  // of viewport, so opening the drawer at ≤1024px and then widening to ≥1024px
  // would otherwise leave role="dialog"/aria-modal + the Tab-trap/Escape listener
  // active on desktop (where the slide-over is CSS-hidden). Force it closed the
  // moment the viewport crosses to desktop, so desktop can never carry the
  // dialog semantics. Guarded for environments without matchMedia.
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia('(min-width: 1024px)');
    const closeIfDesktop = () => {
      if (mql.matches) setOpen(false);
    };
    closeIfDesktop(); // initial check
    mql.addEventListener('change', closeIfDesktop);
    return () => mql.removeEventListener('change', closeIfDesktop);
  }, []);

  // Move focus into the panel on open; return it to the trigger on close.
  useEffect(() => {
    if (open) {
      panelRef.current?.focus();
    } else if (wasOpen.current) {
      triggerRef.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="assistant-drawer-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        <MessageSquare size={16} strokeWidth={2} aria-hidden="true" />
        {label}
      </button>

      <div
        className="assistant-drawer-backdrop"
        data-open={open}
        aria-hidden="true"
        onClick={() => setOpen(false)}
      />

      <aside
        ref={panelRef}
        id={panelId}
        className={`${railClassName} assistant-drawer-panel`}
        data-open={open}
        aria-label={label}
        role={open ? 'dialog' : undefined}
        aria-modal={open ? true : undefined}
        tabIndex={open ? -1 : undefined}
      >
        <button
          type="button"
          className="assistant-drawer-close"
          aria-label="Close assistant"
          onClick={() => setOpen(false)}
        >
          <X size={16} strokeWidth={2} aria-hidden="true" />
        </button>
        {children}
      </aside>
    </>
  );
}

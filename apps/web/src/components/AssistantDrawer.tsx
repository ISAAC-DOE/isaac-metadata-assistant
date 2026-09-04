import './assistant-drawer.css';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight, MessageSquare, X } from './icons';
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
 * PR-E — the desktop rail-collapse preference, remembered per browser. A
 * SEPARATE localStorage key per mount would mean a reader who collapses the
 * rail on a record has to redo it on Project Memory; one shared key treats
 * "hide the assistant rail" as one decision, which is how every other
 * mount-spanning preference in this app (tutorial completion, content-width
 * mode) already behaves. try/catch guarded — a browser that refuses storage
 * (private mode, disabled site data) simply gets the default (open) every
 * visit, never a thrown error.
 */
const RAIL_COLLAPSE_STORAGE_KEY = 'isaac.assistant-rail-collapsed';

function readStoredRailCollapsed(): boolean {
  try {
    return window.localStorage.getItem(RAIL_COLLAPSE_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function writeStoredRailCollapsed(next: boolean): void {
  try {
    window.localStorage.setItem(RAIL_COLLAPSE_STORAGE_KEY, next ? '1' : '0');
  } catch {
    /* the preference simply does not persist; nothing here mutates a record */
  }
}

/**
 * P33 S6 (RESP-1), extended PR-E — the Assistant right rail, responsive.
 *
 * M-6 (independent review, 2026-09-03) — PROVENANCE OF THE DESKTOP CHANGE,
 * recorded because a reader who only has the frozen design brief would read
 * the opposite. `ia-brief.md` §9 ("Assistant Responsive Behaviour") says
 * "Desktop (>=1024px): unchanged". The desktop collapse/expand feature below
 * is not an extension of that brief's own scope — it is a SEPARATE, LATER
 * instruction: the orchestrator's PR-E slice brief ("Assistant rail:
 * collapsible at desktop, drawer below" — section 1 of the prompt that
 * authorized this slice) explicitly asks for it. The two documents disagree
 * because they are from different moments, not because this file overrides
 * a design decision on its own authority.
 *
 * DESKTOP (≥1024px): a static `<aside>` region with the given rail class +
 * accessible name, PLUS (PR-E) a collapse/expand toggle so the rail can be
 * dismissed without losing it: collapsing shrinks the rail to a slim, still
 * VISIBLE, still LABELLED strip (`.assistant-rail-toggle`, the one control
 * that both collapses and re-expands) rather than removing it from the
 * layout entirely — a reader can always find it again without hunting. The
 * mobile trigger/backdrop/close stay CSS-hidden at this width exactly as
 * before, so the ≤1024px behaviour below is unchanged by any of this.
 *
 * NARROW (≤1024px): the rail collapses behind a clearly labelled "Assistant"
 * control that opens the panel as a slide-over dialog — role="dialog" +
 * aria-modal while open, aria-expanded on the trigger, a focus trap, Escape to
 * close, and focus restoration to the trigger. The open/close behaviour is pure
 * JS (viewport-independent); the switch between "static rail" and "slide-over"
 * is pure CSS. Because the trigger is CSS-hidden at desktop, `open` is only ever
 * true at narrow widths, so the dialog semantics never apply on desktop. The
 * desktop `collapsed` state below is like-wise inert at this width — the
 * toggle button and the `.assistant-drawer-content` hiding rule are both
 * scoped to the desktop-only `(min-width: 1025px)` band in
 * assistant-drawer.css, so a reader who collapses the rail on a wide window
 * and then narrows it always gets the ordinary slide-over, never a
 * permanently-hidden panel.
 *
 * `children` (the `AssistantPanel`) is ALWAYS rendered — collapsing hides it
 * with CSS only (`display: none` inside that one media band), it is never
 * conditionally mounted. The conversation, any staged proposal, and whatever
 * the reader has typed into the composer all survive a collapse/expand cycle
 * for exactly that reason: there is only ever one mount of the panel, for the
 * lifetime of this component.
 */
export function AssistantDrawer({ railClassName, label = LABELS.assistant, children }: AssistantDrawerProps) {
  const [open, setOpen] = useState(false);
  // PR-E — desktop rail collapse. Starts `false` (open) on every render,
  // including the FIRST one, so server-rendered/pre-hydration markup and the
  // first client paint agree; the stored preference (if any) is applied in
  // the effect below, after mount, exactly like the tutorial-completion and
  // other per-browser preferences already read localStorage in this app.
  const [collapsed, setCollapsed] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const railToggleRef = useRef<HTMLButtonElement | null>(null);
  const wasOpen = useRef(false);
  const panelId = useId();
  // M-1 (independent review, 2026-09-03) — a SECOND id, distinct from
  // `panelId`. The desktop rail-collapse toggle's `aria-controls` must name
  // the element whose visibility IT actually toggles — `.assistant-drawer-content`
  // (CSS-hidden only in the desktop-collapsed band) — not the whole `<aside>`
  // (`panelId`), which is what the ≤1024px trigger's `aria-controls` already
  // and correctly points to (it opens/closes the WHOLE dialog). Reusing
  // `panelId` for both would have one id standing in for two different
  // controls relationships.
  const contentId = useId();

  useEffect(() => {
    setCollapsed(readStoredRailCollapsed());
  }, []);

  function handleRailToggle() {
    const next = !collapsed;
    setCollapsed(next);
    writeStoredRailCollapsed(next);
    if (!next) {
      // Expanding: move focus to the panel's own heading, once the content is
      // visible again. A microtask/rAF delay is not needed for the DOM query
      // itself (the content was always mounted — only `display` changes), but
      // giving the browser one frame keeps the focus move behind the CSS
      // unhide rather than racing it.
      requestAnimationFrame(() => {
        panelRef.current?.querySelector<HTMLElement>('.assistant-label')?.focus();
      });
    }
    // Collapsing returns focus to THIS control — it is the one button that
    // performs both directions and it stays visible (as the slim affordance)
    // in both states, so focus never has anywhere else to go.
  }

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
      // C-1 (independent review, 2026-09-03) — FILTER OUT WHAT CSS ACTUALLY
      // HIDES. `querySelectorAll` matches `.assistant-rail-toggle` regardless
      // of viewport: that control is a real, enabled, non-`disabled`,
      // non-`tabindex=-1` <button> at every width, and only
      // `assistant-drawer.css`'s CSS (`display: none` outside the desktop
      // `(min-width: 1025px)` band) removes it from the ≤1024px slide-over.
      // The selector-only list therefore collected it into the trap's item
      // list at narrow widths, `.focus()` on a `display:none` element is a
      // no-op, and this handler ALSO calls `e.preventDefault()` unconditionally
      // above, so the browser's native Tab (which would have moved focus
      // regardless) was already suppressed. MEASURED: six sequential Tab
      // presses from the close button at 768px never left it — the composer
      // and every Suggested Question / Agent Action pill were unreachable by
      // keyboard on every tablet/phone width. THIS jsdom test file cannot
      // reproduce that measurement (jsdom's `.focus()` does not appear to
      // respect `display: none`); the real-browser proof is
      // `e2e/specs/keyboard.spec.ts`'s "the assistant drawer trap moves
      // focus to the composer at 768px".
      //
      // `getComputedStyle(el).display !== 'none'`, NOT a rendered-geometry
      // check (`getClientRects()`/`offsetParent`/`getBoundingClientRect()`),
      // and this distinction was itself measured rather than assumed: jsdom
      // has no layout engine at all, so EVERY element's `getClientRects()`
      // is empty there regardless of its actual CSS — a geometry filter
      // would have correctly excluded the hidden toggle in a real browser
      // while also incorrectly excluding every genuinely-visible item in
      // this project's own vitest/jsdom suite, collapsing the trap's item
      // list to zero and breaking the existing focus tests. Computed
      // `display` resolves the SAME `@media` cascade jsdom's CSS engine
      // already evaluates correctly (confirmed directly: a `display: none`
      // element reports `display: 'none'` there), so this check is accurate
      // in both a real browser and this component's own test environment.
      // `visibility: hidden` is checked for the same class of reason
      // `helpers/layout.ts`'s own `rendered()` helper checks it, applied to
      // application code rather than to a test probe.
      //
      // N-2 (re-review, 2026-09-03) — ANCESTOR-AWARE, NOT JUST THE ELEMENT
      // ITSELF. `display` is not an inherited CSS property: a real,
      // enabled `<button>` sitting inside a `display: none` WRAPPER still
      // reports its OWN computed `display` as e.g. `inline-block` —
      // `getComputedStyle` returns the used value from the element's own
      // rules, not "none" merely because an ancestor is not rendered. A
      // single-element check therefore passes exactly the C-1 shape of bug
      // one level removed (a hidden wrapper around an otherwise-focusable
      // control), and `.focus()` on it is still a no-op in a real browser.
      // `isReachableFocusTarget` below walks from the candidate up to (but
      // not past) the panel itself, so a hiding ancestor anywhere in that
      // chain excludes it.
      const isReachableFocusTarget = (el: HTMLElement): boolean => {
        for (let node: HTMLElement | null = el; node; node = node.parentElement) {
          const st = getComputedStyle(node);
          if (st.display === 'none' || st.visibility === 'hidden' || st.visibility === 'collapse') {
            return false;
          }
          if (node === panel) break;
        }
        return true;
      };
      const items = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter(isReachableFocusTarget);
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
        data-collapsed={collapsed}
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

        {/* PR-E — desktop-only collapse/expand. CSS-hidden at ≤1024px (the
            slide-over has its own close button above); CSS-repositioned
            between "inline in the rail header" (expanded) and "the whole
            slim rail" (collapsed) at desktop — see assistant-drawer.css. The
            accessible name states the RESULT of pressing it, per this rail's
            own convention for `.assistant-clear` etc.: visible text IS the
            accessible name, so there is no separate aria-label to drift from
            it. */}
        <button
          ref={railToggleRef}
          type="button"
          className="assistant-rail-toggle"
          aria-expanded={!collapsed}
          aria-controls={contentId}
          onClick={handleRailToggle}
        >
          {collapsed ? (
            <ChevronLeft size={14} strokeWidth={2} aria-hidden="true" />
          ) : (
            <ChevronRight size={14} strokeWidth={2} aria-hidden="true" />
          )}
          <span className="assistant-rail-toggle-label">
            {collapsed ? `Expand ${label}` : `Collapse ${label}`}
          </span>
        </button>

        <div id={contentId} className="assistant-drawer-content">{children}</div>
      </aside>
    </>
  );
}

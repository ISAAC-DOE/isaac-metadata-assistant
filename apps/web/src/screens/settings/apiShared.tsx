/**
 * Small pieces shared by the API tab's two sub-surfaces (P36V PR3 slice C).
 *
 * Kept in one place so the method badge, the copy affordance and the sub-tab
 * contract cannot drift between API Keys and Documentation.
 */
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';

import { Check, Copy } from '../../components/icons';
import type { OpenApiMethod } from '../../lib/types';

/** The HTTP method, carried by the TEXT itself; the tint is secondary only. */
export function MethodBadge({ method }: { method: OpenApiMethod }) {
  return (
    <span className={`api-docs-method api-docs-method-${method}`}>{method.toUpperCase()}</span>
  );
}

/**
 * Copy-to-clipboard with TWO independent success signals:
 *   · visible — the glyph and the label change to "Copied";
 *   · non-visual — the parent's single `role="status"` region announces it
 *     (`onCopied`), so the result is never colour- or icon-only.
 *
 * The accessible name always names WHAT is copied ("Copy cURL sample") and
 * contains the visible label, so speech input can target it by what it says.
 */
export function CopyButton({
  what,
  value,
  onCopied,
}: {
  /** Human name of the thing copied — part of the accessible name. */
  what: string;
  value: string;
  onCopied: (what: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  // P36V — the reset timer is tracked and cleared on unmount. Left dangling it is
  // harmless under React 18, but a panel unmounted mid-copy leaves a stray 1500 ms
  // timer that then calls setState on a gone component.
  const resetTimer = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    },
    [],
  );
  const copy = () => {
    void navigator.clipboard?.writeText(value);
    setCopied(true);
    onCopied(what);
    if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      type="button"
      className="api-copy-btn"
      aria-label={copied ? `Copied ${what}` : `Copy ${what}`}
      onClick={copy}
    >
      {copied ? (
        <Check size={12} strokeWidth={2.4} aria-hidden="true" />
      ) : (
        <Copy size={12} strokeWidth={2} aria-hidden="true" />
      )}
      <span aria-hidden="true">{copied ? 'Copied' : 'Copy'}</span>
    </button>
  );
}

/**
 * The one polite region the API tab uses to announce a copy. Rendered once per
 * panel and shared by every copy button, so adding a copy affordance never adds
 * another live region.
 */
export function CopyAnnouncer({ message }: { message: string }) {
  return (
    <p className="sr-only" role="status">
      {message}
    </p>
  );
}

/**
 * A generic roving-tabindex tablist — the SAME contract as `SettingsSectionTabs`
 * and `GovernanceSectionTabs` (automatic activation, Arrow/Home/End, exactly one
 * tab in the tab order, `aria-controls` on the selected tab only), reused rather
 * than reimplemented for the API sub-navigation and the code-sample tabs.
 */
export function RovingTabs<T extends string>({
  className,
  label,
  tabs,
  active,
  onSelect,
  tabId,
  panelId,
}: {
  className: string;
  label: string;
  tabs: { id: T; label: string }[];
  active: T;
  onSelect: (id: T) => void;
  tabId: (id: T) => string;
  panelId: (id: T) => string;
}) {
  function onKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (index + 1) % tabs.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp')
      next = (index - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = tabs.length - 1;
    if (next === null) return;
    e.preventDefault();
    const target = tabs[next];
    onSelect(target.id);
    (document.getElementById(tabId(target.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <div className={className} role="tablist" aria-label={label}>
      {tabs.map((t, i) => {
        const selected = active === t.id;
        return (
          <button
            key={t.id}
            id={tabId(t.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={selected ? panelId(t.id) : undefined}
            tabIndex={selected ? 0 : -1}
            className={`${className}-tab${selected ? ' active' : ''}`}
            onClick={() => onSelect(t.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

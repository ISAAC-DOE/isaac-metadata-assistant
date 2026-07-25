import './chrome.css';
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

type ShellVariant = 'full' | 'record' | 'evidence';

interface AppShellProps {
  variant: ShellVariant;
  topBar: ReactNode;
  /** LeftNav (full) or WorkflowSpine (record) or EvidenceTrailPanel (evidence). */
  sidebar?: ReactNode;
  /** Right panel on record surfaces (Evidence over Assistant). */
  rightPanel?: ReactNode;
  /** StatusBar on record/evidence surfaces. */
  statusBar?: ReactNode;
  /** Padding preset for <main>. */
  mainPad?: 'pad' | 'centered' | 'none';
  children: ReactNode;
}

/**
 * The frame every screen sits in — app canvas → screen card → routed regions.
 * AppShell owns the chrome layout; screens are pure content. StatusBar and the
 * WorkflowSpine mount only on record surfaces. No colored vertical rails.
 */
export function AppShell({
  variant,
  topBar,
  sidebar,
  rightPanel,
  statusBar,
  mainPad = 'none',
  children,
}: AppShellProps) {
  const mainClass =
    mainPad === 'pad' ? 'screen-main pad' : mainPad === 'centered' ? 'screen-main centered' : 'screen-main';

  // A WorkflowProgressBanner action navigates with `state: { focusMain: true }`
  // so keyboard/screen-reader users land somewhere sensible after jumping
  // surfaces, instead of focus silently staying wherever the old button was.
  // tabIndex={-1} makes <main> a valid programmatic focus target (also
  // sharpens the existing #main skip-link) WITHOUT adding it to the Tab
  // order. The flag is cleared with a replace navigation right after — so it
  // fires once and never re-focuses on a later render/back-forward visit.
  const mainRef = useRef<HTMLElement>(null);
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const state = location.state as { focusMain?: boolean } | null;
    if (!state?.focusMain) return;
    mainRef.current?.focus();
    navigate(`${location.pathname}${location.search}${location.hash}`, { replace: true, state: {} });
    // `navigate` is stable across renders (react-router-dom); only `location`
    // identity should retrigger this effect.
  }, [location, navigate]);

  return (
    <div className="app">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <div className="screen-card" data-variant={variant}>
        {topBar}
        <div className={`screen-body ${variant}`}>
          {sidebar}
          <main id="main" ref={mainRef} tabIndex={-1} className={mainClass}>
            {children}
          </main>
          {rightPanel}
        </div>
        {statusBar}
      </div>
    </div>
  );
}

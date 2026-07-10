import './chrome.css';
import type { ReactNode } from 'react';

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
  return (
    <div className="app">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <div className="screen-card" data-variant={variant}>
        {topBar}
        <div className={`screen-body ${variant}`}>
          {sidebar}
          <main id="main" className={mainClass}>
            {children}
          </main>
          {rightPanel}
        </div>
        {statusBar}
      </div>
    </div>
  );
}

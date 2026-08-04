import './chrome.css';
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { GuidedTutorial } from './GuidedTutorial';
import { TutorialSessionBar } from './TutorialSessionBar';

type ShellVariant = 'full' | 'record' | 'evidence';

/**
 * Opt-in content-width mode (P36R S1). The mode publishes a `--content-max`
 * custom property on <main> (chrome.css); every wrapper that owns a measure —
 * `.placeholder`, `.centered-col`, `.governance-panel` (screens.css) and the
 * component-level caps `.rec-val`, `.schema-browser`, `.settings-card` —
 * consumes it via `var(--content-max, <their historic value>)`.
 *
 *   readable → 760px   wide → 1200px   full → none (uncapped)
 *
 * Scope of the change, stated precisely: a screen that does NOT pass a width
 * keeps its historic MEASURE (max-width) exactly — no `--content-max` is
 * published, so every consumer resolves to its literal fallback. Its outer
 * GUTTER did change: `.screen-main.pad` was standardised from `22px 26px` to
 * `22px var(--main-gutter)` = 28px on BOTH sides for every `mainPad="pad"`
 * mount, opted in or not (consistent outer gutters are the point of the
 * slice). That is a 2px inset per side; `box-sizing: border-box` is global, so
 * it changes no element's border-box width.
 *
 * `full` is not a no-op: it publishes `--content-max: none`, which every
 * DESCENDANT consumer inherits. Any measured wrapper or card dropped inside a
 * `full` <main> therefore loses its own cap. Use it only for surfaces that
 * genuinely must run edge-to-edge, and never as a decorative default.
 */
export type ContentWidth = 'readable' | 'wide' | 'full';

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
  /** Content-measure preset for <main>. Omit to keep the screen's historic width. */
  width?: ContentWidth;
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
  width,
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
        {/*
          The persistent worked-example bar. Renders NOTHING unless a worked-example
          session is open, so in the ordinary application this is a no-op — no
          reserved space, no disabled control, no hint that one exists.

          Placed HERE, between the top bar and the screen body, for the same reason
          `GuidedTutorial` is mounted in this component: the session outlives every
          route change the walkthrough performs, and the two controls that act on the
          session's records must be reachable from every surface it visits. It is a
          `flex: none` sibling of `.screen-body`, so it displaces content downward
          rather than overlaying it — a destructive control must never sit on top of
          the thing it might destroy.
        */}
        <TutorialSessionBar />
        <div className={`screen-body ${variant}`}>
          {sidebar}
          {/* `width` is optional: React omits the attribute entirely when it is
              undefined, so a screen that opts out never publishes --content-max
              and its wrappers fall back to their historic max-widths. */}
          <main id="main" ref={mainRef} tabIndex={-1} className={mainClass} data-width={width}>
            {children}
          </main>
          {rightPanel}
        </div>
        {statusBar}
      </div>

      {/*
        The guided walkthrough's overlay. Mounted HERE — in the one component
        every screen renders — because the walkthrough crosses routes: it points
        at a control on My Experiments, then at one on a record, then at one in
        Settings, and React Router unmounts the whole screen at each of those
        moves. Its state therefore lives in a module store
        (`lib/tutorialController.ts`), not in this component, so remounting is
        free and loses nothing.

        Mounting it costs nothing while idle: it renders null, issues no request
        and reads no storage until a reader actually starts it. It is
        deliberately NOT wrapped in a provider around `AppRoutes` — that would
        force every test that renders a screen directly to grow a provider it has
        no interest in.
      */}
      <GuidedTutorial />
    </div>
  );
}

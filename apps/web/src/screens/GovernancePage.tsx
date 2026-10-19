import './screens.css';
import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { Navigate, useLocation, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { RecordValidator } from '../components/RecordValidator';
import { SchemaBrowser } from '../components/SchemaBrowser';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';

/**
 * Governance & Safety — the P36.3 standalone schema Validator and the read-only
 * Schema Reference browser, as LOCAL page tabs (Validator / Schema Reference) —
 * never added to the global LeftNav (which keeps its single
 * `active="governance"` entry). Same tablist pattern (CSS classes +
 * roving-tabindex keyboard nav) as Project Memory's internal tabs
 * (`ProjectMemory.tsx`'s `SectionTabs`; screens.css `.section-tabs`/`.section-tab`)
 * — not a new UI paradigm.
 *
 * ── THE POLICY TAB MOVED TO SETTINGS, 2026-10-12 ────────────────────────────
 *
 * This page used to open on a third tab, Policy, whose own first sentence said
 * Settings › Data & Privacy was "the canonical home for what this build collects,
 * stores, retains, resets, and exports" — and then restated much of it. A measured
 * audit counted the same boundaries three times across the two pages. `DEC-28`
 * had already named the destination, `Privacy & Governance`, so the policy text
 * now lives there verbatim (`lib/settingsContent.ts` → `GOVERNANCE_POLICY`), and:
 *
 *   · `/governance?tab=policy` — and a bare `/governance`, which always meant the
 *     policy because Policy was the default tab — REDIRECT there
 *     ({@link GovernanceRoute}), so every link minted before this still lands on
 *     the text it was for. `replace`, so Back does not bounce through a redirect.
 *   · `?tab=validator` and `?tab=schema` are unchanged.
 *
 * P36R S8 renamed the third tab from "Schema & Vocabulary" to "Schema
 * Reference" (plan §R7). The vocabulary is NOT empty — it is one of the three
 * subviews inside that tab (Fields · Conditional Rules · Vocabulary), so the
 * shorter name describes the surface without dropping anything from it.
 */
type GovernanceTab = 'validator' | 'schema';

const GOVERNANCE_TABS: { id: GovernanceTab; label: string }[] = [
  { id: 'validator', label: 'Validator' },
  { id: 'schema', label: 'Schema Reference' },
];

const tabId = (id: GovernanceTab) => `governance-tab-${id}`;
const panelId = (id: GovernanceTab) => `governance-tabpanel-${id}`;

/**
 * P36V S-B — the `?tab=` deep-link parameter. The active tab is DERIVED from the
 * URL (it used to be `useState`, so the Validator was unreachable by link), which
 * is what lets the Assistant's Open Validator action land on the Validator tab
 * with the tab genuinely selected.
 */
const TAB_PARAM = 'tab';

function isGovernanceTab(value: string | null): value is GovernanceTab {
  return GOVERNANCE_TABS.some((t) => t.id === value);
}

/** The Validator's own heading (`RecordValidator`'s `<h2 id>`), the focus target. */
const VALIDATOR_HEADING_ID = 'rec-val-heading';

/**
 * The `/governance` route element. A `?tab=` naming one of this page's two tabs
 * renders the page; anything else — `policy`, no value, an unrecognised value,
 * which all used to open the Policy tab — goes to the policy's new home, Settings
 * › Privacy & Governance. Kept OUT of `GovernancePage` itself so that rendering
 * the page directly (as its tests do) can never redirect-loop: a page that
 * redirected to itself on an unknown tab would re-render forever under a router
 * with no `<Routes>`.
 */
export function GovernanceRoute() {
  const [searchParams] = useSearchParams();
  if (!isGovernanceTab(searchParams.get(TAB_PARAM))) {
    return <Navigate to={ROUTES.settingsTab('privacy')} replace />;
  }
  return <GovernancePage />;
}

export function GovernancePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();

  const requestedTab = searchParams.get(TAB_PARAM);
  /* Rendered through `GovernanceRoute`, an unrecognised tab never reaches here.
     Rendered directly, it falls back to the first tab without throwing. */
  const activeTab: GovernanceTab = isGovernanceTab(requestedTab) ? requestedTab : 'validator';

  // An IN-PAGE tab activation must not have its focus stolen: the tablist's
  // roving tabindex deliberately moves focus to the newly selected TAB. This flag
  // marks a change that originated here so the arrival-focus effect below skips
  // it — arriving from elsewhere (a link, or the Assistant's Open Validator
  // action) still focuses the Validator.
  const inPageSelectRef = useRef(false);

  function selectTab(tab: GovernanceTab) {
    inPageSelectRef.current = true;
    const next = new URLSearchParams(searchParams);
    next.set(TAB_PARAM, tab);
    // `replace` for a within-page tab click: switching tabs is not a destination,
    // and pushing each one would bury the screen the reader arrived from behind a
    // stack of Back presses. The ARRIVING navigation (below / from the Assistant)
    // is the PUSH, so one Back returns there.
    setSearchParams(next, { replace: true });
  }

  // Arrival focus. `location.key` changes on EVERY navigation — including a
  // repeat navigation to the identical URL — so activating Open Validator while
  // already on the Validator tab still moves focus and scrolls the surface into
  // view (the control is never perceptibly dead). Focus goes to the Validator's
  // own heading; nothing here runs a validation or touches the record.
  useEffect(() => {
    if (inPageSelectRef.current) {
      inPageSelectRef.current = false;
      return;
    }
    if (activeTab !== 'validator') return;
    const heading = document.getElementById(VALIDATOR_HEADING_ID);
    if (!heading) return;
    /*
     * NO RING ON A PLAIN PAGE LOAD (2026-10-12). Chrome matches `:focus-visible`
     * for a programmatic focus on a document nobody has interacted with yet, so a
     * typed or bookmarked `?tab=validator` drew a full focus ring around the
     * heading on arrival — an indicator for a keyboard move nobody made. The
     * FIRST entry of the history (`location.key === 'default'`) is exactly that
     * case, and only there is the ring suppressed (`focusVisible: false`, measured
     * honoured by Chromium 151). An IN-APP arrival — the Assistant's Open
     * Validator, a launcher link — keeps the browser's own heuristic, so a
     * keyboard reader who pressed something still sees where focus landed
     * (WCAG 2.4.7). Focus itself moves in both cases.
     */
    const options = location.key === 'default' ? ({ focusVisible: false } as FocusOptions) : undefined;
    heading.focus(options);
    // jsdom does not implement scrollIntoView — call it only where it exists.
    heading.scrollIntoView?.({ block: 'start' });
  }, [location.key, activeTab]);

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="governance" />}
      mainPad="pad"
      width="wide"
    >
      <div className="placeholder">
        <span className="eyebrow">Data Governance</span>
        <h1>{LABELS.navGovernance}</h1>

        <GovernanceSectionTabs active={activeTab} onSelect={selectTab} />
      </div>

      {activeTab === 'validator' && (
        <div
          className="governance-panel"
          id={panelId('validator')}
          role="tabpanel"
          aria-labelledby={tabId('validator')}
          tabIndex={0}
        >
          <RecordValidator />
        </div>
      )}

      {activeTab === 'schema' && (
        <div
          className="governance-panel"
          id={panelId('schema')}
          role="tabpanel"
          aria-labelledby={tabId('schema')}
          tabIndex={0}
        >
          <SchemaBrowser />
        </div>
      )}
    </AppShell>
  );
}

// --- local page tabs (mirrors ProjectMemory.tsx's SectionTabs pattern) -----
// A local tablist — Validator · Schema Reference — NOT part of the
// global LeftNav. Roving tabindex + arrow/Home/End keyboard navigation
// (automatic activation); native buttons carry Enter/Space activation.

function GovernanceSectionTabs({
  active,
  onSelect,
}: {
  active: GovernanceTab;
  onSelect: (tab: GovernanceTab) => void;
}) {
  function onKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      nextIndex = (index + 1) % GOVERNANCE_TABS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      nextIndex = (index - 1 + GOVERNANCE_TABS.length) % GOVERNANCE_TABS.length;
    } else if (e.key === 'Home') {
      nextIndex = 0;
    } else if (e.key === 'End') {
      nextIndex = GOVERNANCE_TABS.length - 1;
    }
    if (nextIndex === null) return;
    e.preventDefault();
    const next = GOVERNANCE_TABS[nextIndex];
    onSelect(next.id);
    // Move focus to the newly selected tab (roving tabindex).
    (document.getElementById(tabId(next.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <div className="section-tabs" role="tablist" aria-label="Governance & Safety sections">
      {GOVERNANCE_TABS.map((tab, i) => {
        const selected = active === tab.id;
        return (
          <button
            key={tab.id}
            id={tabId(tab.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={selected ? panelId(tab.id) : undefined}
            tabIndex={selected ? 0 : -1}
            className={`section-tab${selected ? ' active' : ''}`}
            onClick={() => onSelect(tab.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

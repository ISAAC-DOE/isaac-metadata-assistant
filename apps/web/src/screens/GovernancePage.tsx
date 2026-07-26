import './screens.css';
import { useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { GovernanceBanner } from '../components/GovernanceBanner';
import { RecordValidator } from '../components/RecordValidator';
import { SchemaBrowser } from '../components/SchemaBrowser';
import { LABELS } from '../lib/labels';

/**
 * Governance & Safety — the synthetic-only policy, the P36.3 standalone schema
 * Validator, and the read-only Schema Reference browser, organized as LOCAL
 * page tabs (Policy / Validator / Schema Reference) — never added to the global
 * LeftNav (which keeps its single `active="governance"` entry). Same tablist
 * pattern (CSS classes + roving-tabindex keyboard nav) as Project Memory's
 * internal tabs (`ProjectMemory.tsx`'s `SectionTabs`; screens.css
 * `.section-tabs`/`.section-tab`) — not a new UI paradigm.
 *
 * P36R S8 renamed the third tab from "Schema & Vocabulary" to "Schema
 * Reference" (plan §R7). The vocabulary is NOT empty — it is one of the three
 * subviews inside that tab (Fields · Conditional Rules · Vocabulary), so the
 * shorter name describes the surface without dropping anything from it.
 */
type GovernanceTab = 'policy' | 'validator' | 'schema';

const GOVERNANCE_TABS: { id: GovernanceTab; label: string }[] = [
  { id: 'policy', label: 'Policy' },
  { id: 'validator', label: 'Validator' },
  { id: 'schema', label: 'Schema Reference' },
];

const tabId = (id: GovernanceTab) => `governance-tab-${id}`;
const panelId = (id: GovernanceTab) => `governance-tabpanel-${id}`;

export function GovernancePage() {
  const [activeTab, setActiveTab] = useState<GovernanceTab>('policy');

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

        <GovernanceSectionTabs active={activeTab} onSelect={setActiveTab} />
      </div>

      {activeTab === 'policy' && (
        <div
          className="placeholder"
          id={panelId('policy')}
          role="tabpanel"
          aria-labelledby={tabId('policy')}
          tabIndex={0}
        >
          <p>
            This prototype is synthetic-only by default. Real SLAC/SSRL or private artifacts require
            written data-governance approval before they can be read, indexed, or sent to any model.
            Nothing is uploaded to a model or index without that approval — a real-looking file is
            intercepted here and nothing is extracted.
          </p>
          <div style={{ marginTop: 18 }}>
            <GovernanceBanner />
          </div>
        </div>
      )}

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
// A local tablist — Policy · Validator · Schema Reference — NOT part of the
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

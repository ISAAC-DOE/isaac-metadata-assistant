import './chrome.css';
import { Link } from 'react-router-dom';
import { AudioWaveform, Shield, ChevronRight } from './icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { StatusChip } from './StatusChip';
import { HelpPanel } from './HelpPanel';
import { SearchDialog } from './SearchDialog';
import { useHealth } from '../lib/useHealth';
import type { ChipKind } from '../lib/status';

/** Map the backend health.mode to the chip label. "synthetic-only" is the only
 * expected mode → the friendly "Synthetic" label. A missing/failed health check
 * degrades to "Synthetic" too — this is a synthetic-only app, so an ABSENT signal
 * must never vanish or imply non-synthetic. But an UNEXPECTED non-empty mode (a
 * real value we did not anticipate) is surfaced honestly as a visibly distinct
 * label, never masked as "Synthetic". */
function modeLabel(mode: string | undefined): string {
  if (mode === 'synthetic-only' || !mode) return LABELS.modeSynthetic;
  // Anomalous mode: show it truthfully (capitalize the raw value, safe on any
  // string) rather than hide it behind the synthetic label.
  return mode.charAt(0).toUpperCase() + mode.slice(1);
}

// Driven by the backend health.mode (via the shared, cached useHealth) rather
// than a hardcoded label. On backend-down the chip still shows the synthetic
// indicator — it never vanishes and never implies non-synthetic.
function SyntheticChip() {
  const health = useHealth();
  return (
    <span className="mode-chip" aria-label="Synthetic mode — demo data only">
      <Shield size={13} strokeWidth={2} aria-hidden="true" />
      {modeLabel(health?.mode)}
    </span>
  );
}

// The identity mark doubles as the home crumb — a real link back to the queue,
// so no surface is a dead end from the top-left.
function Brand() {
  return (
    <Link to={ROUTES.experiments} className="brand" aria-label={`${LABELS.brand} — ${LABELS.navExperiments}`}>
      <span className="brand-tile" aria-hidden="true">
        <AudioWaveform size={17} strokeWidth={2.2} />
      </span>
      {LABELS.brand}
    </Link>
  );
}

interface TopBarProps {
  variant: 'home' | 'record' | 'breadcrumb';
  breadcrumb?: string;
  title?: string;
  filename?: string;
  stateChip?: ChipKind;
  /** Record id — when present on a record sub-surface, the record title becomes a
   * breadcrumb link back to Review Record (/record/:id). */
  recordId?: string;
  /** Leaf crumb naming the current sub-surface (e.g. "Evidence & File Preview").
   * Rendered as the current, non-link crumb after the linked record title. */
  surface?: string;
}

/** Identity, context/breadcrumb, the persistent Synthetic mode chip, Help, and
 * the ⌘K search command palette. The mode chip is always mounted — it is
 * load-bearing. Search is real (P26): the SearchDialog affordance is mounted on
 * every variant so ⌘K opens the API-backed palette from any surface. */
export function TopBar({ variant, breadcrumb, title, filename, stateChip, recordId, surface }: TopBarProps) {
  return (
    <header className="topbar">
      <Brand />

      {variant === 'home' && (
        <>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SearchDialog />
            <SyntheticChip />
            <HelpPanel />
          </div>
        </>
      )}

      {variant === 'breadcrumb' && (
        <>
          <span className="breadcrumb" aria-current="page">
            <ChevronRight size={14} strokeWidth={2} aria-hidden="true" />
            {breadcrumb}
          </span>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SearchDialog />
            <SyntheticChip />
          </div>
        </>
      )}

      {variant === 'record' && (
        <>
          <div className="record-context">
            <ChevronRight size={14} strokeWidth={2} aria-hidden="true" style={{ color: 'var(--text-disabled)' }} />
            {recordId ? (
              // Sub-surface: the record title is an ancestor crumb linking back to
              // Review Record. The current sub-surface is the leaf below.
              <Link to={ROUTES.record(recordId)} className="record-title record-title-link">
                {title}
              </Link>
            ) : (
              // No sub-surface context: this title IS the current page (leaf).
              <span className="record-title" aria-current="page">
                {title}
              </span>
            )}
            {surface && (
              <>
                <ChevronRight
                  size={14}
                  strokeWidth={2}
                  aria-hidden="true"
                  style={{ color: 'var(--text-disabled)' }}
                />
                <span className="record-surface" aria-current="page">
                  {surface}
                </span>
              </>
            )}
            {stateChip && <StatusChip kind={stateChip} />}
            {filename && <span className="record-file">{filename}</span>}
          </div>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SearchDialog />
            <SyntheticChip />
          </div>
        </>
      )}
    </header>
  );
}

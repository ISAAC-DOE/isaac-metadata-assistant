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
import type { ApiHealth, ApiHealthDatabase } from '../lib/types';

/** Map the backend health.mode to the chip's BASE label. "synthetic-only" is the
 * only expected mode → the friendly "Synthetic workspace" label. A missing/failed
 * health check degrades to it too — the workspace is synthetic, so an ABSENT
 * signal must never vanish or imply non-synthetic. But an UNEXPECTED non-empty
 * mode (a real value we did not anticipate) is surfaced honestly as a visibly
 * distinct label, never masked as synthetic. */
function modeLabel(mode: string | undefined): string {
  if (mode === 'synthetic-only' || !mode) return LABELS.modeSynthetic;
  // Anomalous mode: show it truthfully (capitalize the raw value, safe on any
  // string) rather than hide it behind the synthetic label.
  return mode.charAt(0).toUpperCase() + mode.slice(1);
}

/**
 * Slice 2A — the chip's SECOND axis, independent of `mode`.
 *
 * The deployment may be configured to run a protected, read-only diagnostic
 * against an isolated test database holding production-derived records. That is
 * NOT visible anywhere else in the UI, so an unqualified "Synthetic" chip was
 * under-stating what the deployment does. The qualifier states it — and nothing
 * more.
 *
 * `none` is the ONLY state for an absent/failed health check: we then know
 * nothing about the database, and inventing either qualifier would be a guess.
 */
type DbChipState = 'none' | 'diagnostics' | 'failed';

/**
 * WHY "check failed" AND NOT "unavailable" — do not "improve" this back.
 *
 * GET /api/health performs ZERO I/O in its `database` block (it is the
 * Kubernetes readiness-probe target, so a sick database must never be able to
 * fail a probe). `last_recon` is therefore a memo of the last diagnostic RUN in
 * the server process: it may be minutes old, and it is absent entirely until
 * something runs a scan. "Unavailable" would assert PRESENT unreachability that
 * nothing has measured. "check failed" says only what is true — the last
 * recorded check did not complete. Approved by Krish (I5).
 *
 * By the same reasoning `configured: true` means "set up to run the
 * diagnostic", never "a database is currently reachable", so the diagnostics
 * qualifier is deliberately a capability statement and not a liveness one.
 *
 * A status outside {refused, error} — including a future/unknown value — is not
 * treated as a failure: only an outcome we know to be a failure may claim one.
 */
function databaseChipState(database: ApiHealthDatabase | undefined): DbChipState {
  if (!database?.configured) return 'none';
  const status = database.last_recon?.status;
  return status === 'refused' || status === 'error' ? 'failed' : 'diagnostics';
}

/** The chip's VISIBLE text: the mode base, plus the database qualifier when the
 *  deployment has one. Never renders a host, database name, user, secret name,
 *  connection detail, record count, or any record content — the only inputs are
 *  `mode` and two booleans-worth of database state. */
function chipText(health: ApiHealth | undefined): string {
  const base = modeLabel(health?.mode);
  const state = databaseChipState(health?.database);
  if (state === 'none') return base;
  const qualifier =
    state === 'failed' ? LABELS.modeTestDbCheckFailed : LABELS.modeTestDbDiagnostics;
  return `${base} · ${qualifier}`;
}

/** The accessible name always OPENS with the exact visible text (WCAG 2.5.3
 *  label-in-name), then spells out the same distinction the qualifier makes. */
const CHIP_ARIA_DETAIL: Record<DbChipState, string> = {
  none: 'example data only',
  diagnostics:
    'example data only. This deployment is also configured to run a protected, ' +
    'read-only diagnostic against an isolated test database; it returns ' +
    'sanitized aggregate results only, and no database records are displayed.',
  failed:
    'example data only. The most recent protected, read-only test-database ' +
    'diagnostic recorded by this deployment did not complete; it returns ' +
    'sanitized aggregate results only, and no database records are displayed.',
};

function chipAriaLabel(health: ApiHealth | undefined): string {
  return `${chipText(health)} — ${CHIP_ARIA_DETAIL[databaseChipState(health?.database)]}`;
}

// Driven by the backend health (via the shared, cached useHealth) rather than a
// hardcoded label — `mode` for the base, `database` for the qualifier. No extra
// fetch, no polling, no call to the reconnaissance endpoint itself. On
// backend-down the chip still shows the synthetic indicator — it never vanishes
// and never implies non-synthetic.
function SyntheticChip() {
  const health = useHealth();
  return (
    <span className="mode-chip" aria-label={chipAriaLabel(health)}>
      <Shield size={13} strokeWidth={2} aria-hidden="true" />
      {chipText(health)}
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

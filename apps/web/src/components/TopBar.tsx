import './chrome.css';
import { AudioWaveform, Search, CircleHelp, Shield, ChevronRight } from './icons';
import { LABELS } from '../lib/labels';
import { StatusChip } from './StatusChip';
import type { ChipKind } from '../lib/status';

function SyntheticChip() {
  return (
    <span className="mode-chip" aria-label="Synthetic mode — demo data only">
      <Shield size={13} strokeWidth={2} aria-hidden="true" />
      {LABELS.modeSynthetic}
    </span>
  );
}

function Brand() {
  return (
    <span className="brand">
      <span className="brand-tile" aria-hidden="true">
        <AudioWaveform size={17} strokeWidth={2.2} />
      </span>
      {LABELS.brand}
    </span>
  );
}

interface TopBarProps {
  variant: 'home' | 'record' | 'breadcrumb';
  breadcrumb?: string;
  title?: string;
  filename?: string;
  stateChip?: ChipKind;
}

/** Identity, context/breadcrumb, global search, and the persistent Synthetic
 * mode chip. The mode chip is always mounted — it is load-bearing. */
export function TopBar({ variant, breadcrumb, title, filename, stateChip }: TopBarProps) {
  return (
    <header className="topbar">
      <Brand />

      {variant === 'home' && (
        <>
          <span className="account">
            <span className="avatar" aria-hidden="true">
              AL
            </span>
            Ada Lovelace · SSRL
          </span>
          <div className="topbar-search">
            <div className="search" role="search">
              <Search size={15} strokeWidth={2} aria-hidden="true" />
              <span>Search records, evidence &amp; project memory…</span>
              <span className="kbd">⌘K</span>
            </div>
          </div>
          <div className="topbar-right">
            <SyntheticChip />
            <button type="button" className="icon-btn" aria-label="Help">
              <CircleHelp size={16} strokeWidth={2} />
            </button>
          </div>
        </>
      )}

      {variant === 'breadcrumb' && (
        <>
          <span className="breadcrumb">
            <ChevronRight size={14} strokeWidth={2} aria-hidden="true" />
            {breadcrumb}
          </span>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SyntheticChip />
          </div>
        </>
      )}

      {variant === 'record' && (
        <>
          <div className="record-context">
            <ChevronRight size={14} strokeWidth={2} aria-hidden="true" style={{ color: 'var(--text-disabled)' }} />
            <span className="record-title">{title}</span>
            {stateChip && <StatusChip kind={stateChip} />}
            {filename && <span className="record-file">{filename}</span>}
          </div>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SyntheticChip />
          </div>
        </>
      )}
    </header>
  );
}

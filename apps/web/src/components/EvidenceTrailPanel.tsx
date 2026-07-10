import './evidence.css';
import { SOURCE_ICON, Check } from './icons';
import { LABELS } from '../lib/labels';
import type { EvidenceTrailEntry } from '../lib/types';

interface EvidenceTrailPanelProps {
  entries: EvidenceTrailEntry[];
  directTotal: number;
  selectedKey: string;
  onSelect: (key: string) => void;
  meta: { schema_version: string; generated_utc: string };
}

/**
 * The evidence sidecar as a browsable Evidence Trail — always labeled an
 * assistant convention, not an official ISAAC standard. Direct Fields map to the
 * N/N coverage set; Namespaced entries are explicitly outside that count.
 */
export function EvidenceTrailPanel({
  entries,
  directTotal,
  selectedKey,
  onSelect,
  meta,
}: EvidenceTrailPanelProps) {
  const direct = entries.filter((e) => !e.namespaced);
  const namespaced = entries.filter((e) => e.namespaced);

  return (
    <aside className="trail" aria-label="Evidence Trail">
      <h2 className="trail-head">
        <span aria-hidden="true" style={{ color: 'var(--text-slate)', display: 'inline-flex' }}>
          {(() => {
            const Icon = SOURCE_ICON.file_listing;
            return <Icon size={16} strokeWidth={2} />;
          })()}
        </span>
        {LABELS.evidenceTrail}
      </h2>

      <div className="trail-flag">{LABELS.sidecarConvention}</div>

      <div className="trail-meta">
        <span>schema_version {meta.schema_version}</span>
        <span>generated_utc {meta.generated_utc}</span>
      </div>

      <div className="trail-section-head">
        <span className="trail-section-label">{LABELS.directFields}</span>
        <span className="trail-section-note">
          {direct.length} of {directTotal}
        </span>
      </div>
      <div role="list">
        {direct.map((entry) => (
          <TrailEntryRow
            key={entry.key}
            entry={entry}
            selected={entry.key === selectedKey}
            onSelect={onSelect}
          />
        ))}
      </div>

      <div className="trail-section-head">
        <span className="trail-section-label">{LABELS.namespaced}</span>
        <span className="trail-section-note">not in coverage count</span>
      </div>
      <div role="list">
        {namespaced.map((entry) => (
          <TrailEntryRow
            key={entry.key}
            entry={entry}
            selected={entry.key === selectedKey}
            onSelect={onSelect}
          />
        ))}
      </div>
    </aside>
  );
}

function TrailEntryRow({
  entry,
  selected,
  onSelect,
}: {
  entry: EvidenceTrailEntry;
  selected: boolean;
  onSelect: (key: string) => void;
}) {
  const LeadIcon = SOURCE_ICON[entry.sourceTypes[0] ?? 'file_listing'];
  return (
    <button
      type="button"
      role="listitem"
      className={`trail-entry${selected ? ' selected' : ''}`}
      aria-pressed={selected}
      onClick={() => onSelect(entry.key)}
    >
      <LeadIcon size={14} strokeWidth={2} aria-hidden="true" style={{ color: 'var(--text-tertiary)', flex: 'none' }} />
      <span className="trail-key">{entry.key}</span>
      {entry.namespaced ? (
        <span className="trail-dots" aria-hidden="true">
          {entry.sourceTypes.map((st) => (
            <span key={st} className={`trail-dot ${st}`} />
          ))}
        </span>
      ) : (
        entry.resolved && <Check className="trail-resolved" size={14} strokeWidth={2.4} aria-label="resolved" />
      )}
    </button>
  );
}

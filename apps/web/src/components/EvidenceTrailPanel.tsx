import './evidence.css';
import { SOURCE_ICON, sourceIcon, Check, CircleAlert } from './icons';
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

/**
 * FINDING A11Y-03 (A2) fix. This row used to be a single
 * `<button role="listitem" aria-pressed>`. `role="listitem"` OVERRODE the
 * button's implicit role, so the control stopped being a button to assistive
 * technology, and `aria-pressed` is not an allowed attribute on `listitem` —
 * which meant the selected/unselected state was exposed to nobody.
 *
 * The list semantics and the button semantics now live on separate elements:
 * the `role="listitem"` wrapper is the child of the `role="list"` container,
 * and the interactive element is a plain `<button>` that keeps its implicit
 * role and its valid `aria-pressed` state.
 *
 * `aria-pressed` is kept rather than switched to `aria-current`: exactly one
 * entry is selected at all times (`EvidenceExplorer` falls back to
 * `entries[0]`), and `aria-pressed` announces BOTH states, so a keyboard user
 * tabbing the trail hears "not pressed" on the other entries. `aria-current`
 * is simply absent on the unselected ones, which would leave the very state
 * A11Y-03 says is missing still missing for 30 of the 31 rows.
 *
 * Keyboard behaviour is deliberately the native one — Tab reaches each entry,
 * Enter and Space activate it. A `listbox`/`option` pattern with
 * `aria-selected` was considered and rejected: the trail is TWO lists (Direct
 * Fields and Namespaced) sharing ONE selection, so it would have to become two
 * listboxes, one of which would always claim to have no selection, and it
 * would require a roving tabindex and arrow-key handling that this surface
 * does not have today.
 */
function TrailEntryRow({
  entry,
  selected,
  onSelect,
}: {
  entry: EvidenceTrailEntry;
  selected: boolean;
  onSelect: (key: string) => void;
}) {
  // `sourceIcon` rather than a direct `SOURCE_ICON[...]` index: an entry citing a
  // source type this build does not list used to make this component render
  // `undefined` as an element type, which took the whole screen down. See
  // `icons.tsx :: sourceIcon`.
  const LeadIcon = entry.unavailable
    ? CircleAlert
    : sourceIcon(entry.sourceTypes[0] ?? 'file_listing');
  return (
    <div role="listitem" className="trail-item">
      <button
        type="button"
        className={`trail-entry${selected ? ' selected' : ''}${entry.unavailable ? ' unavailable' : ''}`}
        aria-pressed={selected}
        onClick={() => onSelect(entry.key)}
      >
        <LeadIcon size={14} strokeWidth={2} aria-hidden="true" style={{ color: 'var(--text-tertiary)', flex: 'none' }} />
        <span className="trail-key">{entry.key}</span>
        {/* The failed entry stays in the list and says so in TEXT, not by colour
            or glyph alone — it is not dropped, hidden, or quietly re-labelled as
            a normal entry with no citations. */}
        {entry.unavailable ? (
          <span className="trail-unavailable">unavailable</span>
        ) : entry.namespaced ? (
          <span className="trail-dots" aria-hidden="true">
            {entry.sourceTypes.map((st) => (
              <span key={st} className={`trail-dot ${st}`} />
            ))}
          </span>
        ) : (
          entry.resolved && <Check className="trail-resolved" size={14} strokeWidth={2.4} aria-label="resolved" />
        )}
      </button>
    </div>
  );
}

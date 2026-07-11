import './chrome.css';
import { Network } from './icons';
import type { GraphFreshness } from '../lib/types';

interface GraphStatusChipProps {
  status: GraphFreshness;
  /** The memory-plane note from GET /api/graph/status (never implies validation). */
  note?: string;
}

// fresh / stale / missing are the three surfaced states; `unavailable` degrades to
// Missing. Missing is quiet (neutral), NEVER an error — the memory plane is optional.
const LABEL: Record<GraphFreshness, string> = {
  fresh: 'Fresh',
  stale: 'Stale',
  missing: 'Missing',
  unavailable: 'Missing',
};

const KIND: Record<GraphFreshness, string> = {
  fresh: 'fresh',
  stale: 'stale',
  missing: 'missing',
  unavailable: 'missing',
};

/**
 * The Graphify memory-plane freshness indicator. Advisory only: it reports whether
 * the optional project-memory graph is Fresh / Stale / Missing and carries the
 * memory-plane note. It never implies Graphify validates anything, and a missing
 * graph degrades quietly rather than reading as an error.
 */
export function GraphStatusChip({ status, note }: GraphStatusChipProps) {
  const label = LABEL[status];
  return (
    <span
      className={`graph-chip graph-${KIND[status]}`}
      title={note}
      aria-label={`Project memory: ${label} — memory plane, never a validator`}
    >
      <Network size={13} strokeWidth={2} aria-hidden="true" />
      <span className="graph-chip-label">Memory: {label}</span>
      <span className="graph-chip-plane">memory plane</span>
    </span>
  );
}

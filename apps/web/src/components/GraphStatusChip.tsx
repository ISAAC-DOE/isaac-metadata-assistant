import './chrome.css';
import { Network } from './icons';
import type { MemoryAvailability } from '../lib/types';

interface GraphStatusChipProps {
  /** The primary memory-plane axis (P24.10): is the graph available to serve leads. */
  availability: MemoryAvailability;
  /** The memory-plane note from GET /api/graph/status (never implies validation). */
  note?: string;
}

// The primary chip reports the memory plane's AVAILABILITY only — the finer
// axes (Snapshot Integrity / Memory Policy / Indexed Sources) live on the
// Project Memory screen. Only the two REAL backend states exist; unavailable
// degrades quietly (neutral, never an error): the memory plane is optional and
// advisory. The state is ONE Title-Case text node — carried by text, never
// colour alone (the green is confirmation, not the signal).
const LABEL: Record<MemoryAvailability, string> = {
  available: 'Memory Available',
  unavailable: 'Memory Unavailable',
};

/**
 * The Graphify memory-plane availability indicator. Advisory only: it reports
 * whether the optional project-memory graph is Available or Unavailable and
 * carries the memory-plane note. It never implies Graphify validates anything,
 * and an unavailable graph degrades quietly rather than reading as an error.
 */
export function GraphStatusChip({ availability, note }: GraphStatusChipProps) {
  const label = LABEL[availability];
  return (
    <span
      className={`graph-chip graph-${availability}`}
      title={note}
      aria-label={`Project memory ${availability} — memory plane, advisory only, never a validator`}
    >
      <Network size={13} strokeWidth={2} aria-hidden="true" />
      <span className="graph-chip-label">{label}</span>
    </span>
  );
}
